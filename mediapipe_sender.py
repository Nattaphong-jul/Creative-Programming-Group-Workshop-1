"""
mediapipe_sender.py
───────────────────
Run this in your terminal (outside Blender):
    python mediapipe_sender.py

Gestures → Blender actions
──────────────────────────
  ✌️  Two fingers (index+middle up)         →  Edit Mode
  👍  Thumb up                              →  Snap to Camera View
  ☝️  One finger  (index up)               →  Object Mode
  ✊  Fist                                  →  Bevel high (Edit Mode only)
  👌  OK (thumb≈index, others extended)    →  Grab & move object
  👉  Point right                           →  Select next object
  👈  Point left                            →  Select previous object

Controls
────────
  Q  →  quit
"""

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import socket
import json
import math
import time
import urllib.request
import os

# ── Config ────────────────────────────────────────────────────────────────────
UDP_IP          = "127.0.0.1"
UDP_PORT        = 5005
PINCH_THRESHOLD = 0.06
# Minimum seconds between UDP packets sent to Blender.
# 0.1 = 10 packets/sec — enough for smooth grab movement without
# flooding Blender's main thread. Raise to 0.15 if it still stutters.
SEND_INTERVAL   = 0.033  # ~30 packets/sec, matches webcam framerate
MOVE_THRESHOLD  = 0.005  # lower threshold for more responsive grab movement
CONFIRM_SECONDS  = 2.0    # seconds to hold a gesture before it confirms
RESTART_SECONDS  = 5.0    # seconds to hold open hand before game restarts
MODEL_PATH      = "hand_landmarker.task"
MODEL_URL       = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)

# ── Download model if needed ──────────────────────────────────────────────────
if not os.path.exists(MODEL_PATH):
    print("Downloading hand landmarker model")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("Model downloaded")

# ── UDP socket ────────────────────────────────────────────────────────────────
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# ── Landmark index constants ──────────────────────────────────────────────────
#
#  Wrist  : 0
#  Thumb  : CMC=1  MCP=2  IP=3   TIP=4
#  Index  : MCP=5  PIP=6  DIP=7  TIP=8
#  Middle : MCP=9  PIP=10 DIP=11 TIP=12
#  Ring   : MCP=13 PIP=14 DIP=15 TIP=16
#  Pinky  : MCP=17 PIP=18 DIP=19 TIP=20

WRIST = 0

def dist2d(a, b) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)


def finger_curled(lm, tip_idx: int, pip_idx: int) -> bool:
    """True when the fingertip is closer to the wrist than the PIP joint."""
    return dist2d(lm[tip_idx], lm[WRIST]) < dist2d(lm[pip_idx], lm[WRIST])


def thumb_pointing_up(lm) -> bool:
    """
    Three conditions must ALL be true to avoid confusion with a fist:

      1. Thumb tip is clearly above the WRIST  (large gap — fist thumb never gets here)
      2. Thumb tip is above the INDEX MCP      (thumb is raised past the knuckle line)
      3. Thumb tip is above the THUMB MCP      (thumb is actually extended, not folded)

    In a normal fist the thumb rests across the fingers or to the side —
    it only satisfies condition 3 at best, never all three together.
    Image Y increases downward, so "above" means a smaller Y value.
    """
    thumb_tip  = lm[4]
    thumb_mcp  = lm[2]
    index_mcp  = lm[5]
    wrist      = lm[0]

    above_wrist     = thumb_tip.y < wrist.y     - 0.10   # well above the wrist
    above_index_mcp = thumb_tip.y < index_mcp.y - 0.04   # past the knuckle line
    above_thumb_mcp = thumb_tip.y < thumb_mcp.y - 0.04   # thumb itself extended

    return above_wrist and above_index_mcp and above_thumb_mcp


def index_direction(lm) -> str:
    """
    Return the dominant direction the index finger is pointing:
    'up', 'right', or 'left'.
    Uses the MCP→TIP vector so wrist rotation doesn't affect it.
    """
    dx = lm[8].x - lm[5].x   # positive = right (after mirror flip)
    dy = lm[8].y - lm[5].y   # positive = down
    if abs(dx) > abs(dy):
        return "right" if dx > 0 else "left"
    return "up"


# ── Gesture classifier ────────────────────────────────────────────────────────
#
# Priority order (most specific → least specific):
#
#  1. thumb_up    — all 4 fingers curled AND thumb clearly raised
#  2. fist        — all 4 fingers curled (thumb not raised)
#  3. ok          — thumb≈index tip AND middle/ring/pinky EXTENDED
#  4. two_fingers — index + middle up, ring + pinky curled
#  5. point_right — only index up AND pointing right
#  6. point_left  — only index up AND pointing left
#  7. one_finger  — only index up AND pointing upward
#  8. none        — everything else

def classify_gesture(lm) -> str:
    idx_curled = finger_curled(lm,  8,  6)
    mid_curled = finger_curled(lm, 12, 10)
    rng_curled = finger_curled(lm, 16, 14)
    pky_curled = finger_curled(lm, 20, 18)

    all_curled = idx_curled and mid_curled and rng_curled and pky_curled

    thumb_near_index = dist2d(lm[4], lm[8]) < PINCH_THRESHOLD

    # 1 — Thumb up (fist with thumb raised)
    if all_curled and thumb_pointing_up(lm):
        return "thumb_up"

    # 2 — Fist (all four fingers curled, thumb not raised)
    if all_curled:
        return "fist"

    # 3 — OK gesture (thumb≈index AND middle/ring/pinky all open)
    if thumb_near_index and not mid_curled and not rng_curled and not pky_curled:
        return "ok"

    # 3 — Two fingers (index + middle up, ring + pinky down)
    if not idx_curled and not mid_curled and rng_curled and pky_curled:
        return "two_fingers"

    # 4-6 — Single index finger
    if not idx_curled and mid_curled and rng_curled and pky_curled:
        direction = index_direction(lm)
        if direction == "right":
            return "point_right"
        if direction == "left":
            return "point_left"
        return "one_finger"

    # 8 — Open hand (all four fingers extended, no specific gesture)
    if not idx_curled and not mid_curled and not rng_curled and not pky_curled:
        return "open_hand"

    return "none"


# ── On-screen label + colour per gesture ─────────────────────────────────────
GESTURE_UI = {
    "thumb_up"   : ((0,   215, 255), "THUMB UP    - Camera View"),
    "fist"       : ((0,   0,   220), "FIST        - Bevel to Sphere"),
    "ok"         : ((255, 165,   0), "OK          - Grab & Move"),
    "two_fingers": ((220,  80,  80), "TWO FINGERS - Edit Mode"),
    "point_right": ((80,  230, 200), "POINT RIGHT - Next Object"),
    "point_left" : ((80,  230, 200), "POINT LEFT  - Prev Object"),
    "one_finger" : ((180, 180, 255), "ONE FINGER  - Object Mode"),
    "open_hand"  : ((0,   255, 180), "OPEN HAND   - Hold 5s to Restart"),
    "none"       : ((0,   180, 255), "No gesture"),
}


# ── Landmark drawing ──────────────────────────────────────────────────────────

def draw_landmarks_on_frame(frame, hand_landmarks):
    h, w = frame.shape[:2]
    for lm in hand_landmarks:
        cv2.circle(frame, (int(lm.x * w), int(lm.y * h)), 4, (0, 255, 0), -1)
    connections = [
        (0,1),(1,2),(2,3),(3,4),
        (0,5),(5,6),(6,7),(7,8),
        (0,9),(9,10),(10,11),(11,12),
        (0,13),(13,14),(14,15),(15,16),
        (0,17),(17,18),(18,19),(19,20),
        (5,9),(9,13),(13,17),
    ]
    for s, e in connections:
        p1 = (int(hand_landmarks[s].x * w), int(hand_landmarks[s].y * h))
        p2 = (int(hand_landmarks[e].x * w), int(hand_landmarks[e].y * h))
        cv2.line(frame, p1, p2, (0, 200, 100), 1)


# ── Build detector ────────────────────────────────────────────────────────────
base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
options = vision.HandLandmarkerOptions(
    base_options=base_options,
    num_hands=1,
    min_hand_detection_confidence=0.5,
    min_hand_presence_confidence=0.5,
    min_tracking_confidence=0.5,
)
detector = vision.HandLandmarker.create_from_options(options)

cap = cv2.VideoCapture(0)
print("[sender] Starting — press Q to quit")
for _, (_, label) in GESTURE_UI.items():
    print(f"          {label}")

# ── Hold-to-confirm state ─────────────────────────────────────────────────────
last_gesture       = "none"
gesture_hold_start = 0.0    # when the current gesture first appeared
already_confirmed  = False  # prevents re-firing while the gesture is held
grab_active        = False  # True once OK has been held for 4 s
open_hand_start    = 0.0    # tracks open_hand hold start independently
restart_confirmed  = False  # prevents re-firing open_hand restart

# ── Throttle state ────────────────────────────────────────────────────────────
last_send_time = 0.0
last_sent_x    = 0.5
last_sent_y    = 0.5


# ── Progress bar helper ───────────────────────────────────────────────────────
def draw_progress_bar(frame, progress: float, colour):
    """
    Draw a thin horizontal bar at the bottom of the frame.
    progress: 0.0 – 1.0
    """
    h, w = frame.shape[:2]
    bar_h   = 14
    bar_y   = h - bar_h - 6
    bar_x0  = 10
    bar_x1  = w - 10
    filled  = int(bar_x0 + (bar_x1 - bar_x0) * min(progress, 1.0))

    # Background track
    cv2.rectangle(frame, (bar_x0, bar_y), (bar_x1, bar_y + bar_h),
                  (60, 60, 60), -1)
    # Filled portion
    if filled > bar_x0:
        cv2.rectangle(frame, (bar_x0, bar_y), (filled, bar_y + bar_h),
                      colour, -1)
    # Border
    cv2.rectangle(frame, (bar_x0, bar_y), (bar_x1, bar_y + bar_h),
                  (180, 180, 180), 1)

    # Countdown text inside bar
    remaining = max(0.0, CONFIRM_SECONDS * (1.0 - progress))
    text  = "CONFIRMED!" if progress >= 1.0 else f"Hold {remaining:.1f}s"
    cv2.putText(frame, text,
                (bar_x0 + 4, bar_y + bar_h - 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)


# ── Main loop ─────────────────────────────────────────────────────────────────
while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    now = time.time()

    frame    = cv2.flip(frame, 1)
    rgb      = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result   = detector.detect(mp_image)

    gesture = "none"
    x, y    = 0.5, 0.5

    if result.hand_landmarks:
        lm      = result.hand_landmarks[0]
        x       = lm[8].x
        y       = lm[8].y
        gesture = classify_gesture(lm)
        draw_landmarks_on_frame(frame, lm)

    # ── Hold timer ────────────────────────────────────────────────────────
    if gesture != last_gesture:
        # Gesture changed — reset hold timer
        gesture_hold_start = now
        already_confirmed  = False
        # If we were in grab mode and OK was released, exit grab
        if last_gesture == "ok" and gesture != "ok":
            grab_active = False
    last_gesture = gesture

    hold_duration = now - gesture_hold_start if gesture not in ("none", "open_hand") else 0.0
    progress      = min(hold_duration / CONFIRM_SECONDS, 1.0)

    # Track open_hand hold separately with RESTART_SECONDS threshold
    if gesture == "open_hand":
        if open_hand_start == 0.0:
            open_hand_start = now
        open_hand_progress = min((now - open_hand_start) / RESTART_SECONDS, 1.0)
    else:
        open_hand_start   = 0.0
        open_hand_progress = 0.0
        restart_confirmed  = False

    # OK activates grab instantly — no hold required
    if gesture == "ok":
        grab_active = True

    # open_hand fires once at 5-second mark
    gesture_confirmed = False
    if gesture == "open_hand" and open_hand_progress >= 1.0 and not restart_confirmed:
        gesture_confirmed = True
        restart_confirmed = True

    # All other gestures fire once at the confirm mark
    elif gesture not in ("none", "ok", "open_hand") and progress >= 1.0 and not already_confirmed:
        gesture_confirmed = True
        already_confirmed = True

    # ── Overlay ───────────────────────────────────────────────────────────
    colour, label = GESTURE_UI.get(gesture, ((200, 200, 200), gesture))

    # Show GRABBING label once OK is confirmed
    if gesture == "ok" and grab_active:
        label = "OK - GRABBING (move now)"

    cv2.putText(frame, label, (10, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, colour, 2)

    h_px, w_px = frame.shape[:2]
    cv2.circle(frame, (int(x * w_px), int(y * h_px)), 8, colour, -1)

    # Draw progress bar — open_hand uses its own 5s progress
    if gesture == "open_hand":
        if not restart_confirmed:
            draw_progress_bar(frame, open_hand_progress, colour)
        else:
            draw_progress_bar(frame, 1.0, (0, 255, 120))
    elif gesture != "none" and gesture != "ok" and (not already_confirmed or not grab_active):
        draw_progress_bar(frame, progress, colour)
    elif gesture != "none" and already_confirmed:
        draw_progress_bar(frame, 1.0, (0, 255, 120))

    # ── Build payload ─────────────────────────────────────────────────────
    payload = json.dumps({
        "x":                  round(x, 4),
        "y":                  round(y, 4),
        "gesture":            gesture,
        "gesture_confirmed":  gesture_confirmed,   # one-shot trigger at 4 s
        "grab_active":        grab_active,          # True while OK grab is live
    })

    # ── Throttle ──────────────────────────────────────────────────────────
    # • gesture_confirmed   → send immediately (one-shot action)
    # • grab_active         → send every SEND_INTERVAL when hand moves
    #                         (no confirmation needed once grab is live)
    # • everything else     → only send if interval elapsed AND hand moved
    time_ok        = (now - last_send_time) >= SEND_INTERVAL
    position_moved = (abs(x - last_sent_x) > MOVE_THRESHOLD or
                      abs(y - last_sent_y) > MOVE_THRESHOLD)

    should_send = (
        gesture_confirmed                          # confirmed one-shot
        or (grab_active and time_ok and position_moved)  # live grab movement
        or (time_ok and position_moved and not grab_active)  # idle position
    )

    if should_send:
        sock.sendto(payload.encode(), (UDP_IP, UDP_PORT))
        last_send_time = now
        last_sent_x    = x
        last_sent_y    = y

    cv2.imshow("MediaPipe Hand Tracker", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
sock.close()
detector.close()
print("[sender] Stopped.")