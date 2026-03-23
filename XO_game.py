import bpy
from math import radians
import bmesh

# Reset to Object Mode
if bpy.ops.object.mode_set.poll():
    bpy.ops.object.mode_set(mode='OBJECT')

# Delete all objects
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

def create_plane(name, location, scale):
    # Add Plain
    bpy.ops.mesh.primitive_plane_add(location=location)
    
    plane = bpy.context.object
    plane.name = name
    
    plane.scale = (scale[0], scale[1], 1)
    
    return plane

def create_torus(name, location, scale):
    # Add Torus
    bpy.ops.mesh.primitive_torus_add(location=location)
    
    torus = bpy.context.object
    torus.name = name
    
    torus.scale = scale
    
    return torus

def create_monkey(name, location, scale):
    # Add Monkey
    bpy.ops.mesh.primitive_monkey_add(location=location)
    
    monkey = bpy.context.object
    monkey.name = name
    
    monkey.scale = scale
    
    return monkey

# Add camera at 0, 0, 40 pointing down
bpy.ops.object.camera_add(location=(0, 0, 40))
camera = bpy.context.object
camera.name = "Camera"

# Rotate camera to point down (90 degrees rotation on X-axis)
camera.rotation_euler = (0, 0, radians(90))

# Set as active camera
bpy.context.scene.camera = camera