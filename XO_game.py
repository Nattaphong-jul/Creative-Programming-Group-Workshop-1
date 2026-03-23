import bpy
from math import radians
import bmesh

# Reset to Object Mode
if bpy.ops.object.mode_set.poll():
    bpy.ops.object.mode_set(mode='OBJECT')

# Delete all objects
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

def clear_selection(obj): # Clear all selections in the mesh
    for v in obj.data.vertices: v.select = False
    for e in obj.data.edges: e.select = False
    for f in obj.data.polygons: f.select = False

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

def add_solidify(obj, thickness=0.5):
    """Adds a Solidify modifier to the given object."""
    if obj and obj.type == 'MESH':
        # Add the modifier
        mod = obj.modifiers.new(name="MySolidify", type='SOLIDIFY')
        
        # Set the thickness
        mod.thickness = thickness
        
        # Offset
        mod.offset = -1 
        return mod
    return None

def shade_smooth(obj):
    # Make sure the object is a mesh
    if obj.type != 'MESH':
        return
        
    # Smooth polygons
    for poly in obj.data.polygons:
        poly.use_smooth = True
            
    # Update mesh data
    obj.data.update()

# Apply All
def ApplyAll():
    bpy.ops.object.convert(target='MESH')

def add_loop_cut(obj, edge_indices, cuts=1, offset=0.0):
    bpy.ops.object.mode_set(mode='EDIT')
    
    bm = bmesh.from_edit_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    
    try:
        edges_to_cut = [bm.edges[i] for i in edge_indices]
    except IndexError:
        print("Error: One or more edge indices are out of range.")
        bpy.ops.object.mode_set(mode='OBJECT')
        return
        
    edge_data = []
    reference_vector = None
    
    if offset != 0.0 and cuts == 1:
        for e in edges_to_cut:
            v1, v2 = e.verts
            vec = v2.co - v1.co
            if reference_vector is None:
                reference_vector = vec
            elif vec.dot(reference_vector) < 0:
                vec = -vec
            edge_data.append({
                "midpoint": (v1.co + v2.co) / 2.0,
                "vector": vec
            })
    
    bmesh.ops.subdivide_edgering(
        bm,
        edges=edges_to_cut,
        cuts=cuts,
        profile_shape='LINEAR',
        profile_shape_factor=0.0
    )
    
    if offset != 0.0 and cuts == 1:
        offset = max(-1.0, min(1.0, offset))
        for v in bm.verts:
            for data in edge_data:
                if (v.co - data["midpoint"]).length < 0.001:
                    v.co += data["vector"] * (offset / 2.0)
                    break
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')


def bevel_vertices_ops(obj, vertex_indices, offset=0.5, segments=10):
    # Make sure it is OBJECT mode
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Clear All Selection
    clear_selection(obj)
    
    # Select all assigned edges
    for idx in vertex_indices:
        obj.data.vertices[idx].select = True
        
    # Change to EDIT Mode
    bpy.ops.object.mode_set(mode='EDIT')
    
    # Ensure Blender is in Vertex Selection Mode
    bpy.ops.mesh.select_mode(type='VERT')
    
    # Bevel Edge
    bpy.ops.mesh.bevel(
        offset=offset, 
        segments=segments, 
        affect='EDGES'
    )
    
    # Switch back to OBJECT Mode
    bpy.ops.object.mode_set(mode='OBJECT')

# Add camera at 0, 0, 40 pointing down
bpy.ops.object.camera_add(location=(0, 0, 40))
camera = bpy.context.object
camera.name = "Camera"

# Rotate camera to point down (90 degrees rotation on X-axis)
camera.rotation_euler = (0, 0, radians(90))

# Set as active camera
bpy.context.scene.camera = camera

# Show vertex index
def index_overlay(b: bool = True):
    bpy.context.preferences.view.show_developer_ui = True

    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.overlay.show_extra_indices = b
    return b

main_arena = create_plane("MainArena", location=(0, 0, 0), scale=(5, 5))
add_solidify(main_arena, thickness=0.5)
ApplyAll()
add_loop_cut(main_arena, edge_indices=[0, 2, 4, 6], cuts=2, offset=0.0)
add_loop_cut(main_arena, edge_indices=[1, 24, 25, 3, 5, 23, 22, 7], cuts=2, offset=0.0)
index_overlay(True)