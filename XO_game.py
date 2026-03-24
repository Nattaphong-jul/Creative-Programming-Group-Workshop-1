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

def create_torus(name, location, scale, major_segments=48, minor_segments=12):
    # Add Torus
    bpy.ops.mesh.primitive_torus_add(
        location=location,
        major_segments=major_segments,
        minor_segments=minor_segments
    )
    
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

def transform(obj, location=None, rotation=None, scale=None):
    if location:
        obj.location = location
    if rotation:
        obj.rotation_euler[0] = radians(rotation[0])
        obj.rotation_euler[1] = radians(rotation[1])
        obj.rotation_euler[2] = radians(rotation[2])
    if scale:
        obj.scale = scale
    return obj

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

def apply_color(target_obj, mat_name="Color", color=(1.0, 1.0, 1.0, 1.0), metallic=0.0, roughness=0.5, emit_strength=0.0):
    
    # Create New Material
    myMat = bpy.data.materials.new(name=mat_name)
    myMat.use_nodes = True
    
    # Get Principled BSDF node
    bsdf = myMat.node_tree.nodes.get("Principled BSDF")
    
    # Set the values directly
    if bsdf:
        bsdf.inputs['Base Color'].default_value = color
        bsdf.inputs['Metallic'].default_value = metallic
        bsdf.inputs['Roughness'].default_value = roughness
        
        # Emission
        emit_socket = 'Emission Color' if 'Emission Color' in bsdf.inputs else 'Emission'
        bsdf.inputs[emit_socket].default_value = color 
        
        # Emission Strength
        if 'Emission Strength' in bsdf.inputs:
            bsdf.inputs['Emission Strength'].default_value = emit_strength

    # Clear existing materials and assign the new one
    target_obj.data.materials.clear()
    target_obj.data.materials.append(myMat)
    
    return myMat

def extrude(obj, mode, index, direction, distance):
    # Ensure we are in OBJECT mode
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Clear all selections
    clear_selection(obj)
    
    # Selection mode
    if mode == 'VERT':
        obj.data.vertices[index].select = True
    elif mode == 'EDGE':
        obj.data.edges[index].select = True
    elif mode == 'FACE':
        obj.data.polygons[index].select = True
    else:
        print("Invalid mode. Use 'VERT', 'EDGE', or 'FACE'.")
        return
    
    # Switch to EDIT mode
    bpy.ops.object.mode_set(mode='EDIT')
    
    # Set the pivot point to individual origins
    bpy.context.scene.tool_settings.transform_pivot_point = 'INDIVIDUAL_ORIGINS'
    
    # Extrude the selection
    bpy.ops.mesh.extrude_context()
    
    # Move in the specified direction
    if direction == 'UP':
        bpy.ops.transform.translate(value=(0, 0, distance))
    elif direction == 'DOWN':
        bpy.ops.transform.translate(value=(0, 0, -distance))
    elif direction == 'LEFT':
        bpy.ops.transform.translate(value=(-distance, 0, 0))
    elif direction == 'RIGHT':
        bpy.ops.transform.translate(value=(distance, 0, 0))
    elif direction == 'FORWARD':
        bpy.ops.transform.translate(value=(0, distance, 0))
    elif direction == 'BACKWARD':
        bpy.ops.transform.translate(value=(0, -distance, 0))
    
    # Switch back to OBJECT mode
    bpy.ops.object.mode_set(mode='OBJECT')

def bevel_edges(obj, offset=0.1, segments=1):
    if not obj or obj.type != 'MESH':
        return

    # Switch to EDIT mode and select all edges
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.select_mode(type='EDGE')

    # Bevel
    bpy.ops.mesh.bevel(
        offset=offset,
        segments=segments,
        affect='EDGES'
    )

    bpy.ops.object.mode_set(mode='OBJECT')

# Add camera at 0, 0, 40 pointing down
bpy.ops.object.camera_add(location=(0, 0, 40))
camera = bpy.context.object
camera.name = "Camera"

# Rotate camera to point down (90 degrees rotation on X-axis)
camera.rotation_euler = (0, 0, radians(360))

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

board = create_plane("Board", location=(0, 0, 1), scale=(5, 5))
add_solidify(board, thickness=0.5)
ApplyAll()
add_loop_cut(board, edge_indices=[0, 2, 4, 6], cuts=2, offset=0.0)
add_loop_cut(board, edge_indices=[1, 24, 25, 3, 5, 23, 22, 7], cuts=2, offset=0.0)
index_overlay(True)
bevel_edges(board, offset=0.03, segments=3)

extrude(board, mode='FACE', index=452, direction='DOWN', distance=0.14)
extrude(board, mode='FACE', index=473, direction='DOWN', distance=0.14)
extrude(board, mode='FACE', index=458, direction='DOWN', distance=0.14)
extrude(board, mode='FACE', index=476, direction='DOWN', distance=0.14)
extrude(board, mode='FACE', index=474, direction='DOWN', distance=0.14)
extrude(board, mode='FACE', index=475, direction='DOWN', distance=0.14)
extrude(board, mode='FACE', index=457, direction='DOWN', distance=0.14)
extrude(board, mode='FACE', index=469, direction='DOWN', distance=0.14)
extrude(board, mode='FACE', index=461, direction='DOWN', distance=0.14)

apply_color(board, mat_name="BoardMat", color=(0.1, 0.3, 0.8, 1.0), metallic=0.0, roughness=0.5, emit_strength=0)

color_plane = create_plane("ColorPlane", location=(0, 0, 1 - 0.12), scale=(4.9, 4.9))
apply_color(color_plane, mat_name="ColorPlaneMat", color=(0.05, 0.15, 0.5, 1.0), metallic=0.0, roughness=0.5, emit_strength=0)

# Lock the board so it cannot be selected unless manually unlocked
board.hide_select = True
color_plane.hide_select = True

# Monkeys and Circles
for i in range(4):
    monkey = create_monkey(f"Monkey{i}", location=(8, 5 - (i * 3), 2), scale=(1, 1, 1))
    transform(monkey, rotation=(-90, 0, 0))
    apply_color(monkey, mat_name=f"MonkeyMat{i}", color=(1.0, 0.5, 0.0, 1.0), metallic=0.5, roughness=0.3, emit_strength=0)

    torus = create_torus(f"Torus{i}", location=(-8, 5 - (i * 3), 2), scale=(1, 1, 1), major_segments=100, minor_segments=100)
    transform(torus, rotation=(0, 0, 0))
    apply_color(torus, mat_name=f"TorusMat{i}", color=(0.9, 0.2, 0.2, 1.0), metallic=0.5, roughness=0.3, emit_strength=0)