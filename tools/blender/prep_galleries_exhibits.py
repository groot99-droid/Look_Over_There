"""Static copies of the owner's character models for the museum hall (scene `galleries`): the T. rex skeleton and two warriors as fixed exhibits, and the
six warriors that become the moving statues as the bake's stand-ins. Each copy is the model in its rest pose with the armature dropped, one mesh, its
texture cut to 1K, written to blender/models/galleries/exhibits/<id>.glb. build_galleries.py reads only those copies.

    blender -b --factory-startup --python tools/blender/prep_galleries_exhibits.py -- --src <folder with the character GLBs> [--preview <dir>]

The sources are models/characters/<id>.glb of the characters job (the owner's Higgsfield models, rigged). With --preview it also renders each copy from
the front and the side (the plinth hides the soles, so the front is what matters) for a look before the build.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "blender/models/galleries/exhibits"
IDS = ["trex", "warrior_british_redcoat", "warrior_mongol_archer", "warrior_egyptian_pharaoh", "warrior_viking_raider", "warrior_qin_terracotta",
       "warrior_medieval_knight", "warrior_japanese_samurai", "warrior_roman_legionary"]
TEX_PX = 1024

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return args[args.index(name) + 1] if name in args else default


def clear():
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.armatures, bpy.data.actions, bpy.data.cameras, bpy.data.lights):
        for d in list(coll):
            coll.remove(d)


def static_copy(src):
    """Import, put every armature in its rest position, take the evaluated mesh (the rest pose) in world space, drop everything else."""
    clear()
    bpy.ops.import_scene.gltf(filepath=str(src))
    for a in [o for o in bpy.data.objects if o.type == "ARMATURE"]:
        a.data.pose_position = "REST"
        a.animation_data_clear()
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    shapes = {pb.custom_shape for a in bpy.data.objects if a.type == "ARMATURE" for pb in a.pose.bones if pb.custom_shape}
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and o not in shapes and o.find_armature() is not None]   # the skinned body, not the bone shapes
    assert meshes, f"{src.name}: no skinned mesh"
    new = []
    for o in meshes:
        ev = o.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
        me.transform(o.matrix_world)
        ob = bpy.data.objects.new(src.stem, me)
        bpy.context.scene.collection.objects.link(ob)
        new.append(ob)
    for o in [o for o in bpy.data.objects if o not in new]:
        bpy.data.objects.remove(o)
    if len(new) > 1:
        bpy.ops.object.select_all(action="DESELECT")
        for o in new:
            o.select_set(True)
        bpy.context.view_layer.objects.active = new[0]
        bpy.ops.object.join()
    ob = bpy.context.scene.objects[0]
    ob.name = src.stem
    ob.vertex_groups.clear()
    ob.shape_key_clear()
    for i, uv in enumerate(ob.data.uv_layers):
        uv.name = "UVMap" if i == 0 else uv.name
    while len(ob.data.uv_layers) > 1:
        ob.data.uv_layers.remove(ob.data.uv_layers[1])
    # put it on the ground (lowest vertex at y = 0), centred over the origin in plan
    vs = [v.co for v in ob.data.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    ob.data.transform(Matrix.Translation((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)))
    for im in bpy.data.images:
        if im.size[0] > TEX_PX:
            im.scale(TEX_PX, TEX_PX * im.size[1] // im.size[0])
    for m in bpy.data.materials:
        m.name = "Exhibit_" + src.stem
    return ob, hi - lo


def strip_jpeg_comments(path):
    """Blender writes JPEG comment segments (its render metadata); the copies are public, so drop them (as build_galleries.py does for the stills)."""
    b = path.read_bytes()
    out, i = bytearray(b[:2]), 2
    while i < len(b) and b[i] == 0xFF and b[i + 1] != 0xDA:
        n = int.from_bytes(b[i + 2:i + 4], "big")
        if b[i + 1] != 0xFE:
            out += b[i:i + 2 + n]
        i += 2 + n
    out += b[i:]
    path.write_bytes(bytes(out))


def export(ob, path):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_yup=True, export_apply=True, export_texcoords=True,
                              export_normals=True, export_materials="EXPORT", export_image_format="JPEG", export_jpeg_quality=88, export_extras=False,
                              export_skins=False, export_animations=False, export_morph=False, export_cameras=False, export_lights=False)


def preview(ob, size, path):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE_NEXT"
    sc.render.resolution_x, sc.render.resolution_y = 1024, 768
    w = sc.world or bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.5, 0.52, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    sc.collection.objects.link(sun)
    h = max(size.z, 0.01)
    span = max(size.x, size.y, size.z)
    for tag, d in (("front", Vector((0, -1, 0))), ("side", Vector((1, 0, 0)))):
        cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = span * 1.15
        sc.collection.objects.link(cam)
        c = Vector((0, 0, h / 2))
        cam.location = c + d * span * 3
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        sc.camera = cam
        sc.render.filepath = str(path.parent / f"{path.stem}_{tag}.png")
        bpy.ops.render.render(write_still=True)
        bpy.data.objects.remove(cam)


def main():
    src = Path(arg("--src"))
    prev = Path(arg("--preview")) if arg("--preview") else None
    OUT.mkdir(parents=True, exist_ok=True)
    info = {}
    for i in IDS:
        ob, size = static_copy(src / f"{i}.glb")
        tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
        info[i] = {"size_xyz_blender": [round(v, 3) for v in size], "tris": tris}
        print("EXHIBIT", i, info[i])
        export(ob, OUT / f"{i}.glb")
        ims = {n.image for m in ob.data.materials for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image}
        assert len(ims) == 1, f"{i}: {len(ims)} textures"
        im = ims.pop()                                   # the base colour, also as a file: build_galleries.py gives the exhibit its own material
        im.filepath_raw = str(OUT / f"{i}_1k.jpg")
        im.file_format = "JPEG"
        bpy.context.scene.render.image_settings.quality = 88
        im.save()
        strip_jpeg_comments(OUT / f"{i}_1k.jpg")
        info[i]["texture"] = list(im.size)
        if prev:
            prev.mkdir(parents=True, exist_ok=True)
            preview(ob, size, prev / f"{i}.png")
    print(json.dumps(info))


main()
