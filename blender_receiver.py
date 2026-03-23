"""
blender_receiver.py
────────────────────
Paste this into Blender's Text Editor and press Run Script.

Gesture → Blender action map
─────────────────────────────
  ✌️  two_fingers   →  Switch to Edit Mode
  👍  thumb_up      →  Snap to Camera View  (Numpad 0)
  ☝️  one_finger    →  Switch to Object Mode
  👌  ok  (4s hold) →  Unlock grab; then move object freely
  👉  point_right   →  Select next mesh object
  👈  point_left    →  Select previous mesh object

Requirements
────────────
  Blender 3.x / 4.x — standard bpy only.
  Press ESC in the viewport to stop the operator.
"""

import bpy
import socket
import json

# ── Config ────────────────────────────────────────────────────────────────────
UDP_PORT   = 5005
GRAB_SCALE = 10.0   # how strongly hand XY delta maps to world units


# ── Blender operation helpers ─────────────────────────────────────────────────

def get_view3d_area():
    """Return the first VIEW_3D area on screen, or None."""
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            return area
    return None


def mesh_objects_in_scene():
    """Return all visible mesh objects, excluding internal helpers."""
    return [
        o for o in bpy.context.scene.objects
        if o.type == "MESH"
    ]


def set_mode(mode: str):
    obj = bpy.context.active_object
    if obj is None:
        return
    try:
        bpy.ops.object.mode_set(mode=mode)
        print(f"[blender_receiver] Mode → {mode}")
    except Exception as e:
        print(f"[blender_receiver] mode_set error: {e}")


def snap_to_camera_view():
    area = get_view3d_area()
    if area is None:
        return
    try:
        region = next(r for r in area.regions if r.type == "WINDOW")
        space  = next(s for s in area.spaces  if s.type == "VIEW_3D")
        with bpy.context.temp_override(area=area, region=region, space_data=space):
            bpy.ops.view3d.view_camera()
        print("[blender_receiver] Snapped to camera view")
    except Exception as e:
        print(f"[blender_receiver] Camera view error: {e}")


def apply_bevel():
    """
    Bevel the active mesh with a high offset and many segments so a default
    cube becomes a sphere-like shape.

    offset=1.0  — half the side length of Blender's default 2×2×2 cube,
                   which rounds every edge all the way to the centre.
    segments=10 — enough loops to produce a smooth, near-spherical result.
    clamp_overlap=True — prevents faces from collapsing on smaller objects.

    Only runs in Edit Mode. If the user is in Object Mode, prints a warning
    and does nothing — they must switch with the two_fingers gesture first.
    """
    obj = bpy.context.active_object
    if obj is None or obj.type != "MESH":
        print("[blender_receiver] Bevel: no active mesh object")
        return

    if obj.mode != "EDIT":
        print("[blender_receiver] Bevel: must be in Edit Mode — use ✌️ two fingers first")
        return

    # Select all geometry so every edge gets bevelled
    bpy.ops.mesh.select_all(action="SELECT")

    try:
        bpy.ops.mesh.bevel(
            offset        = 1.0,
            segments      = 10,
            clamp_overlap = True,
        )
        print("[blender_receiver] Bevel applied (offset=1.0, 10 seg) — cube → sphere")
    except Exception as e:
        print(f"[blender_receiver] Bevel error: {e}")



def cycle_selected_object(direction: int):
    """direction: +1 = next, -1 = previous."""
    # Must be in Object Mode to change selection
    obj = bpy.context.active_object
    if obj is not None and obj.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
            print("[blender_receiver] Cycle: switched to Object Mode")
        except Exception as e:
            print(f"[blender_receiver] Cycle: could not switch mode — {e}")
            return

    objects = mesh_objects_in_scene()
    if not objects:
        return

    active  = bpy.context.active_object
    idx     = objects.index(active) if active in objects else 0
    new_obj = objects[(idx + direction) % len(objects)]

    bpy.ops.object.select_all(action="DESELECT")
    new_obj.select_set(True)
    bpy.context.view_layer.objects.active = new_obj
    print(f"[blender_receiver] Selected → {new_obj.name}")


# ── Modal Operator ────────────────────────────────────────────────────────────

class MEDIAPIPE_OT_controller(bpy.types.Operator):
    """Receive MediaPipe hand gesture data and control Blender."""

    bl_idname = "mediapipe.controller"
    bl_label  = "MediaPipe Controller"

    _timer = None
    _sock  = None

    # Grab state
    _grab_active     = False
    _grab_hand_start = (0.5, 0.5)
    _grab_obj_start  = None

    def modal(self, context, event):
        if event.type == "ESC":
            return self.cancel(context)
        if event.type == "TIMER":
            self._read_socket()
        return {"PASS_THROUGH"}

    def _read_socket(self):
        try:
            data, _ = self._sock.recvfrom(512)
            payload = json.loads(data.decode())
        except BlockingIOError:
            return
        except Exception as e:
            print(f"[blender_receiver] Socket error: {e}")
            return

        nx          = payload.get("x",                 0.5)
        ny          = payload.get("y",                 0.5)
        gesture     = payload.get("gesture",           "none")
        confirmed   = payload.get("gesture_confirmed", False)  # 4-sec one-shot
        grab_active = payload.get("grab_active",       False)  # OK grab live

        self._dispatch(gesture, confirmed, grab_active, nx, ny)

    def _dispatch(self, gesture: str, confirmed: bool,
                  grab_active: bool, nx: float, ny: float):

        # ── One-shot actions — only fire when confirmed (4-sec hold) ──────
        if gesture == "two_fingers" and confirmed:
            set_mode("EDIT")

        elif gesture == "one_finger" and confirmed:
            set_mode("OBJECT")

        elif gesture == "thumb_up" and confirmed:
            snap_to_camera_view()

        elif gesture == "fist" and confirmed:
            apply_bevel()

        elif gesture == "point_right" and confirmed:
            cycle_selected_object(+1)

        elif gesture == "point_left" and confirmed:
            cycle_selected_object(-1)

        # ── Grab — unlocked after 4-sec OK hold, movement is immediate ───
        elif gesture == "ok" and grab_active:
            self._handle_grab(nx, ny, confirmed)

        # ── Any other gesture — release grab if active ────────────────────
        else:
            if self._grab_active:
                self._grab_active = False
                print("[blender_receiver] Grab released")

    def _handle_grab(self, nx: float, ny: float, confirmed: bool):
        obj = bpy.context.active_object
        if obj is None:
            return

        # Grab only works in Object Mode — force a switch if needed
        if obj.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
                print("[blender_receiver] Grab: switched to Object Mode")
            except Exception as e:
                print(f"[blender_receiver] Grab: could not switch mode — {e}")
                return

        if not self._grab_active:
            # Grab just unlocked (confirmed=True on this frame) — set anchor
            self._grab_active     = True
            self._grab_hand_start = (nx, ny)
            self._grab_obj_start  = obj.location.copy()
            print(f"[blender_receiver] Grab started on '{obj.name}'")
            return

        # Grab is live — move immediately with no delay
        dx = (nx - self._grab_hand_start[0]) *  GRAB_SCALE
        dy = (ny - self._grab_hand_start[1]) * -GRAB_SCALE   # invert Y
        obj.location.x = self._grab_obj_start.x + dx
        obj.location.y = self._grab_obj_start.y + dy

    def execute(self, context):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("127.0.0.1", UDP_PORT))
        self._sock.setblocking(False)

        self._grab_active = False

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.033, window=context.window)
        wm.modal_handler_add(self)

        print("[blender_receiver] Started — press ESC in viewport to stop")
        print("  two_fingers  → Edit Mode")
        print("  one_finger   → Object Mode")
        print("  thumb_up     → Camera View")
        print("  fist         → Bevel to sphere (Edit Mode only)")
        print("  ok  (held)   → Grab & move active object")
        print("  point_right  → Select next mesh object")
        print("  point_left   → Select previous mesh object")
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        if self._sock:
            self._sock.close()
        print("[blender_receiver] Stopped.")
        return {"CANCELLED"}


# ── Registration & auto-run ───────────────────────────────────────────────────

def register():
    bpy.utils.register_class(MEDIAPIPE_OT_controller)


def unregister():
    bpy.utils.unregister_class(MEDIAPIPE_OT_controller)


if __name__ == "__main__":
    register()
    bpy.ops.mediapipe.controller("INVOKE_DEFAULT")