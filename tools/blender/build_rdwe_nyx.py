"""Builds Right Door, Wrong Exit's god room Nyx, "The Vault of Night" (`rdwe_god_nyx`), in Blender: the reduced game copies of the owner's Nyx
furniture set, the octagonal star-domed bedchamber, its constellation-door trick, the night bake, and world/rdwe_god_nyx.glb with its lightmaps.

Re-runnable, from the repo root (docs/BLENDER.md, docs/BLENDER_AREAS.md section 7):

    blender -b --factory-startup --python tools/blender/build_rdwe_nyx.py -- --stage copies --src <folder>   (the 13 originals and 4 props -> reduced copies)
    blender -b --factory-startup --python tools/blender/build_rdwe_nyx.py -- --stage art                     (the room; saves blender/scenes/rdwe_god_nyx.blend)
    blender -b --factory-startup blender/scenes/rdwe_god_nyx.blend --python tools/blender/build_rdwe_nyx.py -- --stage bake [--samples 512] [--device cpu]
    blender -b --factory-startup blender/scenes/rdwe_god_nyx.blend --python tools/blender/build_rdwe_nyx.py -- --stage export
    blender -b --factory-startup blender/scenes/rdwe_god_nyx.blend --python tools/blender/build_rdwe_nyx.py -- --stage render [--render-samples 128]
    (--stage bake,export,render runs several in one go; --stage views writes view sheets of the copies)
    then, in plain Python (Pillow): each lightmap PNG -> world/lightmaps/rdwe_god_nyx_<n>.webp (q90), and
    python tools/webp_glb.py blender/work/farway_rdwe_god_nyx/rdwe_god_nyx_raw.glb world/rdwe_god_nyx.glb 85
    (docs/renders/rdwe_god_nyx/README.md has the exact steps; the work folder is blender/work/farway_rdwe_god_nyx, git-ignored)

Stage `copies` reads the originals (never writes them): each piece is imported, a copy of it is welded and decimated (Collapse) to its budget,
given a fresh UV, and the original's base colour is baked onto the copy (Cycles, selected to active, emission, so gold and metal keep their colour).
The copies go to blender/models/rdwe_nyx/ with a ledger. Blender-first scene: the layout comes from this file (PLAN section 4.1), and the
exporter's objects (COL_, DoorLeaf_, Marker_, Link_, Arrive_, Zone_, Spot_) are kept in the `Layout` collection for tools/blender/export_scene.py,
which is not on main yet, so no world/rdwe_god_nyx.json is written here.

Axes: Blender metres, x east, y north, z up, the room's centre at the origin, the floor at z = 0. The glTF exporter's +Y up turns Blender (x, y, z)
into game (x, z, -y), so game north is -z, as everywhere in Farway.
"""
import csv
import json
import math
import os
import random
import struct
import sys
import time
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[2]
SCENE = "rdwe_god_nyx"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
COPIES = ROOT / "blender/models/rdwe_nyx"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"
MARGIN_PX = 8

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 512, int)
DEVICE = arg("--device", "auto")
SRC = Path(arg("--src", str(ROOT / "blender/work/nyx_source")))
ONLY = arg("--only", "all")


def work():
    d = Path(arg("--work", str(ROOT / f"blender/work/farway_{SCENE}")))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- the pieces (manifest: Nyx_collection_manifest.csv; budgets: PLAN section 5)
# code, original file, short name, triangle budget, base colour size (px)
PIECES = [
    ("NX-00", "NX-00_Nyx_Lamp.glb", "lamp", 15000, 1024),
    ("NX-01", "NX-01_Nyx_Bedside_Table.glb", "bedside_table", 15000, 1024),
    ("NX-02", "NX-02_Nyx_Armchair.glb", "armchair", 18000, 1024),
    ("NX-03", "NX-03_Nyx_Dresser.glb", "dresser", 18000, 1024),
    ("NX-04", "NX-04_Nyx_Tall_Cabinet.glb", "tall_cabinet", 18000, 1024),
    ("NX-05", "NX-05_Nyx_Bed.glb", "bed", 24000, 2048),
    ("NX-06", "NX-06_Nyx_Wall_Mirror.glb", "wall_mirror", 15000, 1024),
    ("NX-07", "NX-07_Nyx_Writing_Desk.glb", "writing_desk", 18000, 1024),
    ("NX-08", "NX-08_Nyx_Clock.glb", "clock", 15000, 512),
    ("NX-09", "NX-09_Nyx_Hourglass.glb", "hourglass", 15000, 512),
    ("NX-10", "NX-10_Nyx_Vase.glb", "vase", 15000, 512),
    ("NX-11", "NX-11_Nyx_Runner.glb", "runner", 2000, 1024),          # a flat 12 mm slab: 2k triangles hold its edge; the texture is the rug
    ("NX-12", "NX-12_Nyx_Textiles.glb", "textiles", 15000, 1024),
    # the Higgsfield props PLAN section 7 gives Nyx (normalised to 1.9 m tall by the generator; `size` is the plan's W x H x D in metres)
    ("P4", "P4.glb", "statue_nyx", 15000, 1024),
    ("P9", "P9.glb", "star_orrery", 12000, 1024),
    ("P18", "P18.glb", "world_egg", 8000, 512),
    ("P20", "P20.glb", "veil_canopy", 10000, 1024),
]
PROP_SIZE = {"P4": (1.0, 2.6, 0.8), "P9": (1.2, 1.5, 1.2), "P18": (0.6, 1.1, 0.6), "P20": (2.4, 3.2, 2.4)}
PER_AXIS = {"P20"}          # the canopy is fitted to its footprint; the others keep their proportions and take the plan's height


def copy_path(code, name):
    return COPIES / f"{code}_{name}_game.glb"


def clear_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.lights, bpy.data.cameras, bpy.data.collections):
        for d in list(coll):
            coll.remove(d)


def select_only(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def setup_cycles(samples, bake=False):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = samples
    cy.use_adaptive_sampling = False
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces, cy.transmission_bounces, cy.transparent_max_bounces = 10, 6, 4, 8, 16
    cy.use_denoising = not bake
    prefs = bpy.context.preferences.addons["cycles"].preferences
    gpu = False
    if DEVICE != "cpu":
        for t in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
            try:
                prefs.compute_device_type = t
                prefs.refresh_devices()
            except Exception:
                continue
            devs = [d for d in prefs.devices if d.type != "CPU"]
            if devs:
                for d in prefs.devices:
                    d.use = d.type != "CPU"
                gpu = True
                break
    cy.device = "GPU" if gpu else "CPU"
    print("CYCLES device:", cy.device, [d.name for d in prefs.devices if d.use] if gpu else "CPU")
    return gpu


def smooth_by_angle(me, deg=35):
    bm = bmesh.new()
    bm.from_mesh(me)
    for e in bm.edges:
        e.smooth = len(e.link_faces) == 2 and e.calc_face_angle(0.0) < math.radians(deg)
    for f in bm.faces:
        f.smooth = True
    bm.to_mesh(me)
    bm.free()


# ---------------------------------------------------------------- stage copies: the reduced game copies (the originals are only read)
def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    select_only(meshes)
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    mw = ob.matrix_world.copy()                    # unparent and bake the node transforms into the vertices
    ob.parent = None
    ob.matrix_world = mw
    select_only([ob])
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for o in list(bpy.data.objects):
        if o is not ob and o.type != "MESH":
            bpy.data.objects.remove(o)
    return ob


def emission_from_base(mat):
    """Bake source: the original's base colour (its texture times its factor) straight into an Emission shader, so the bake reads the colour
    itself, whatever the metal and the roughness say (a diffuse-colour bake would give black on the gilt)."""
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    sock = bsdf.inputs["Base Color"]
    if sock.is_linked:
        nt.links.new(sock.links[0].from_socket, em.inputs["Color"])
    else:
        em.inputs["Color"].default_value = sock.default_value
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])


def view_sheet(ob, code):
    """Four small orthographic views of the copy, from +X, -X, +Y, -Y (Blender), to read which way the piece faces."""
    sc = bpy.context.scene
    setup_cycles(16)
    w = sc.world or bpy.data.worlds.new("views")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
    sc.render.resolution_x = sc.render.resolution_y = 256
    sc.render.film_transparent = False
    dims = ob.dimensions
    size = max(dims) * 1.15
    c = sum((ob.matrix_world @ Vector(b) for b in ob.bound_box), Vector()) / 8
    cam = bpy.data.objects.new("viewcam", bpy.data.cameras.new("viewcam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = size
    sc.collection.objects.link(cam)
    sc.camera = cam
    out = []
    for tag, d in (("px", (1, 0, 0)), ("nx", (-1, 0, 0)), ("py", (0, 1, 0)), ("ny", (0, -1, 0)), ("top", (0, 0, 1))):
        cam.location = c + Vector(d) * (size * 2)
        cam.rotation_euler = (-Vector(d)).to_track_quat("-Z", "Y" if tag != "top" else "Y").to_euler()
        p = work() / "views" / f"{code}_{tag}.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        sc.render.filepath = str(p)
        sc.render.image_settings.file_format = "PNG"
        bpy.ops.render.render(write_still=True)
        out.append(p.name)
    bpy.data.objects.remove(cam)
    return out


def make_copy(code, fname, name, budget, px):
    t0 = time.time()
    clear_scene()
    src = SRC / fname
    orig = import_glb(src)
    orig.name = f"orig_{code}"
    src_tris = tri_count(orig)
    for m in orig.data.materials:
        emission_from_base(m)
    # the copy: its own mesh, no UVs, no custom normals, welded, so the collapse works on a closed surface
    me = orig.data.copy()
    me.name = f"{code}_{name}"
    for uv in list(me.uv_layers):
        me.uv_layers.remove(uv)
    for a in [a for a in me.attributes if a.name.startswith("COLOR") or a.name.startswith("Col")]:
        me.attributes.remove(a)
    me.materials.clear()
    cp = bpy.data.objects.new(f"{code}_{name}", me)
    bpy.context.scene.collection.objects.link(cp)
    select_only([cp])
    try:
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    except Exception as e:
        print("  no custom normals to clear", e)
    diag = Vector(cp.dimensions).length
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=diag * 2e-6)
    bm.to_mesh(me)
    bm.free()
    # scale: the props come normalised to 1.9 m tall; the furniture is at its manifest size already
    s = Vector((1, 1, 1))
    if code in PROP_SIZE:
        w, h, d = PROP_SIZE[code]
        dx, dy, dz = cp.dimensions
        if code in PER_AXIS:
            s = Vector((w / dx, d / dy, h / dz))
        else:
            k = h / dz
            s = Vector((k, k, k))
        for o in (cp, orig):
            o.scale = s
        select_only([cp, orig])
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    # decimate, in passes (a single 1 % collapse is less faithful)
    for target_ratio in (0.12, None):
        n = tri_count(cp)
        r = budget / n if target_ratio is None else max(target_ratio, budget / n)
        if r >= 0.999:
            continue
        mod = cp.modifiers.new("dec", "DECIMATE")
        mod.decimate_type = "COLLAPSE"
        mod.ratio = r
        mod.use_collapse_triangulate = True
        select_only([cp])
        bpy.ops.object.modifier_apply(modifier=mod.name)
        print(f"  {code} decimate {n} -> {tri_count(cp)}")
    smooth_by_angle(me, 40)
    # fresh UV0
    uvl = me.uv_layers.new(name="UVMap")
    select_only([cp])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.002, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=3.0 / px, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    # the bake target
    img = bpy.data.images.new(f"{code}_{name}_base", px, px, alpha=False)
    mat = bpy.data.materials.new(f"Nyx_{code}_{name}")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    bsdf.inputs["Roughness"].default_value = 0.7
    bsdf.inputs["Metallic"].default_value = 0.0
    if code == "P20":
        mat.use_backface_culling = False                   # the veil is a thin sheet, seen from both sides
    else:
        mat.use_backface_culling = True
    nt.nodes.active = tex
    me.materials.append(mat)
    setup_cycles(1, bake=True)
    sc = bpy.context.scene
    sc.render.bake.use_selected_to_active = True
    sc.render.bake.cage_extrusion = max(0.003, 0.008 * diag)
    sc.render.bake.max_ray_distance = max(0.01, 0.03 * diag)
    sc.render.bake.margin = 6
    sc.render.bake.margin_type = "EXTEND"
    select_only([orig, cp])
    bpy.context.view_layer.objects.active = cp
    bpy.ops.object.bake(type="EMIT", use_clear=True, margin=6)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])     # linked only now: during the bake it would read itself
    # centre on the floor: xy centre at the origin, the lowest point at z = 0 (the offset goes in the ledger)
    lo = Vector([min(v.co[i] for v in me.vertices) for i in range(3)])
    hi = Vector([max(v.co[i] for v in me.vertices) for i in range(3)])
    off = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    me.transform(Matrix.Translation(-off))
    img.filepath_raw = str(work() / f"{code}_{name}_base.jpg")
    img.file_format = "JPEG"
    sc.render.image_settings.quality = 90
    img.save()
    baked = bpy.data.images.load(str(work() / f"{code}_{name}_base.jpg"))     # the saved JPEG, packed, in place of the generated image
    baked.pack()
    tex.image = baked
    bpy.data.images.remove(img)
    bpy.data.objects.remove(orig)
    COPIES.mkdir(parents=True, exist_ok=True)
    out = copy_path(code, name)
    select_only([cp])
    scrub_private()
    bpy.ops.export_scene.gltf(filepath=str(out), export_format="GLB", use_selection=True, export_yup=True, export_apply=True, export_texcoords=True,
                              export_normals=True, export_materials="EXPORT", export_image_format="JPEG", export_jpeg_quality=90, export_extras=False,
                              export_cameras=False, export_lights=False, export_animations=False)
    views = view_sheet(cp, code)
    dims = [round(v, 3) for v in cp.dimensions]
    row = {"code": code, "piece": name, "source_file": fname, "source_tris": src_tris, "game_tris": tri_count(cp), "base_px": px,
           "dims_m_xyz": "x".join(str(v) for v in dims), "offset_m": ",".join(f"{v:.4f}" for v in off), "scale": ",".join(f"{v:.4f}" for v in s),
           "glb_bytes": out.stat().st_size, "seconds": round(time.time() - t0)}
    print("COPY", row)
    return row


def stage_copies():
    rows = []
    led = work() / "copies_ledger.json"
    old = json.loads(led.read_text()) if led.exists() else {}
    for code, fname, name, budget, px in PIECES:
        if ONLY != "all" and code not in ONLY.split(","):
            if code in old:
                rows.append(old[code])
            continue
        rows.append(make_copy(code, fname, name, budget, px))
    led.write_text(json.dumps({r["code"]: r for r in rows}, indent=1))
    with open(COPIES / "ledger.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("LEDGER", COPIES / "ledger.csv")


# ---------------------------------------------------------------- privacy (the build_main_floor.py scrub)
KEEP_PROPS = {"lightmap", "lightmap_intensity"}
SYS_KEEP = ("cycles", "eevee")


def scrub_ui_paths():
    for sc in bpy.data.screens:
        for a in sc.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"_" * 1000
                    sp.params.directory = b"//"


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private():
    kinds = ("scenes", "worlds", "objects", "meshes", "materials", "collections", "cameras", "lights", "images", "node_groups", "screens",
             "window_managers", "workspaces")
    dropped = 0
    for kind in kinds:
        for idb in getattr(bpy.data, kind):
            stores = [idb]
            sysget = getattr(idb, "bl_system_properties_get", None)
            if sysget:
                s = sysget()
                if s is not None:
                    stores.append(s)
            for st in stores:
                for k in list(st.keys()):
                    if kind == "materials" and st is idb and k in KEEP_PROPS:
                        continue
                    if kind == "objects" and st is idb and k in LAYOUT_PROPS:
                        continue
                    if st is not idb and k.startswith(SYS_KEEP):
                        continue
                    try:
                        del st[k]
                        dropped += 1
                    except Exception as e:
                        print("  could not drop custom property", idb.name, k, e)
    print("SCRUB dropped", dropped, "custom properties")
    for sc in bpy.data.scenes:
        set_path(sc.render, "filepath", "//")
        for p in sc.render.bl_rna.properties:
            if p.identifier.startswith("use_stamp") and not p.is_readonly:
                setattr(sc.render, p.identifier, False)
    base = BLEND.parent
    for im in bpy.data.images:
        if im.packed_file or im.source != "FILE" or not im.filepath:
            continue
        p = Path(bpy.path.abspath(im.filepath))
        try:
            rel = "//" + os.path.relpath(p, base).replace("\\", "/")
        except ValueError:
            rel = "//" + p.name
        set_path(im, "filepath", rel)
    scrub_ui_paths()


LAYOUT_PROPS = {"kind", "to_scene", "to_arrive", "hinge", "swing_deg", "state", "note"}     # the exporter's properties on the Layout objects (no paths)


# ================================================================ the room (PLAN section 4.1)
APO = 5.0                                  # the octagon's apothem: 10 m across its flats
RC = APO / math.cos(math.radians(22.5))    # centre to corner
WALL_H = 4.0
DOME_TOP = 7.5
WALL_T = 0.2
RAIL_Z = 2.7                               # the gilt rail between the damask and the night-blue upper wall
EYE = 0.95                                 # the RDWE walker's eye at RDWE_SCALE 1.7 (controls.js: 1.62 / 1.7)
SPOT = Vector((-1.5, -3.2, 0.0))           # the black-egg medallion: the one place the stars make a door
DOOR_C = Vector((5.0, 1.2, 0.0))           # the star door on the east wall (its centre at the floor)
DOOR_W, DOOR_H = 0.94, 2.16
SPAWN = Vector((0.0, -4.3, 0.0))
FLATS = {"E": 0, "NE": 45, "N": 90, "NW": 135, "W": 180, "SW": 225, "S": 270, "SE": 315}    # each wall's inward-facing side, by the compass angle of its outward normal
COMPASS = {"E": 0, "NE": 45, "N": 90, "NW": 135, "W": 180, "SW": 225, "S": 270, "SE": 315}
N_STARS_FIXED = 340
N_STARS_FREE = 24
N_STARS_DOOR = 36

# which way each copy faces as made (read by eye from view sheets of the copies): the compass angle its front points to in Blender.
# The set's multi-view pieces face +X (the clock's face, the bed's foot); the props face -Y
NATIVE_FRONT = {"NX-00": 0, "NX-01": 0, "NX-02": 0, "NX-03": 0, "NX-04": 0, "NX-05": 0, "NX-06": 0, "NX-07": 0, "NX-08": 0, "NX-09": 0, "NX-10": 0,
                "NX-11": 0, "NX-12": 0, "P4": 270, "P9": 270, "P18": 270, "P20": 270}

# placement (PLAN 4.1): code, object name, (x, y), facing, how: ("floor"), ("wall", flat, gap), ("on", support object, (x, y) offset or None)
PLACE = [
    ("NX-11", "NX-11_runner", (0.0, -2.8), "N", ("floor",)),
    ("NX-05", "NX-05_bed", (0.0, 3.85), "S", ("wall", "N", 0.03)),
    ("NX-01", "NX-01_bedside_table_W", (-1.42, 4.6), "S", ("wall", "N", 0.04)),
    ("NX-01", "NX-01_bedside_table_E", (1.42, 4.6), "S", ("wall", "N", 0.04)),
    ("NX-03", "NX-03_dresser", (-4.7, 0.3), "E", ("wall", "W", 0.03)),
    ("NX-06", "NX-06_wall_mirror", (-4.95, 0.3), "E", ("hang", "W", 0.02, 1.0)),
    ("NX-04", "NX-04_tall_cabinet", (-3.3, 3.0), "SE", ("wall", "NW", 0.04)),
    ("NX-07", "NX-07_writing_desk", (4.7, -0.6), "W", ("wall", "E", 0.03)),
    ("NX-02", "NX-02_armchair", (3.75, -0.6), "E", ("floor",)),
    ("P20", "P20_veil_canopy", (0.0, 3.8), "S", ("wall", "N", 0.02)),
    ("P4", "P4_statue_nyx", (3.25, 3.25), "SW", ("wall", "NE", 0.12)),
    ("P9", "P9_star_orrery", (2.4, -3.0), "NW", ("floor",)),
    ("P18", "P18_world_egg", (-3.3, -2.4), "NE", ("floor",)),
    # the smalls, on the furniture
    ("NX-00", "NX-00_lamp", (0.0, 0.0), "S", ("on", "NX-01_bedside_table_W")),
    ("NX-10", "NX-10_vase", (0.0, 0.0), "S", ("on", "NX-01_bedside_table_E")),
    ("NX-08", "NX-08_clock", (0.0, 0.32), "E", ("on", "NX-03_dresser")),
    ("NX-09", "NX-09_hourglass", (0.0, -0.4), "W", ("on", "NX-07_writing_desk")),
    ("NX-12", "NX-12_textiles", (0.15, -0.72), "S", ("on", "NX-05_bed")),
]

# ---------------------------------------------------------------- generated images (own work, numpy, fixed seeds)
GLYPHS = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"], "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"], "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"], "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"], "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"], "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"], "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"], "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"], "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"], "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"], " ": ["00000"] * 7,
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"], "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"], "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
}


def blur(a, r, passes=3):
    n = 2 * r + 1
    for ax in (0, 1):
        for _ in range(passes):
            pad = [(0, 0)] * a.ndim
            pad[ax] = (r + 1, r)
            c = np.cumsum(np.pad(a, pad, mode="edge"), axis=ax)
            Ln = c.shape[ax]
            a = (np.take(c, range(n, Ln), axis=ax) - np.take(c, range(0, Ln - n), axis=ax)) / n
    return a


def wrap_blur(a, r, passes=3):
    """A blur that wraps round the edges, so a tile stays seamless."""
    p = 4 * r + 2
    big = np.pad(a, [(p, p), (p, p)] + [(0, 0)] * (a.ndim - 2), mode="wrap")
    return blur(big, r, passes)[p:-p, p:-p]


def draw_text(img, text, box, fg, fill=0.7):
    r0, r1, c0, c1 = box
    cols = len(text) * 6 - 1
    s = max(1, int(min((c1 - c0) * fill / cols, (r1 - r0) * fill / 7)))
    y = r0 + ((r1 - r0) - 7 * s) // 2
    x = c0 + ((c1 - c0) - cols * s) // 2
    for ch in text:
        for r, row in enumerate(GLYPHS[ch]):
            for c, v in enumerate(row):
                if v == "1":
                    img[y + r * s:y + (r + 1) * s, x + c * s:x + (c + 1) * s] = fg
        x += 6 * s


def line(img, p0, p1, col, w=1.5):
    """An anti-aliased line of width w px from p0 to p1 (row, col), drawn over its bounding box."""
    (r0, c0), (r1, c1) = p0, p1
    lo_r, hi_r = int(max(0, min(r0, r1) - w - 2)), int(min(img.shape[0], max(r0, r1) + w + 3))
    lo_c, hi_c = int(max(0, min(c0, c1) - w - 2)), int(min(img.shape[1], max(c0, c1) + w + 3))
    yy, xx = np.mgrid[lo_r:hi_r, lo_c:hi_c].astype(np.float32)
    d = np.array([r1 - r0, c1 - c0], np.float32)
    L2 = max(float(d @ d), 1e-6)
    t = np.clip(((yy - r0) * d[0] + (xx - c0) * d[1]) / L2, 0, 1)
    dist = np.hypot(yy - (r0 + t * d[0]), xx - (c0 + t * d[1]))
    a = np.clip(w / 2 + 0.5 - dist, 0, 1)[..., None]
    img[lo_r:hi_r, lo_c:hi_c] = img[lo_r:hi_r, lo_c:hi_c] * (1 - a) + np.array(col) * a


def dot(img, p, col, r):
    lo_r, hi_r = int(max(0, p[0] - r - 2)), int(min(img.shape[0], p[0] + r + 3))
    lo_c, hi_c = int(max(0, p[1] - r - 2)), int(min(img.shape[1], p[1] + r + 3))
    yy, xx = np.mgrid[lo_r:hi_r, lo_c:hi_c].astype(np.float32)
    a = np.clip(r + 0.5 - np.hypot(yy - p[0], xx - p[1]), 0, 1)[..., None]
    img[lo_r:hi_r, lo_c:hi_c] = img[lo_r:hi_r, lo_c:hi_c] * (1 - a) + np.array(col) * a


GOLD_S = (0.86, 0.66, 0.30)       # sRGB gold for the painted lines


def floor_pixels():
    """The floor, one picture over the whole octagon (FLOOR_SPAN metres square): polished black marble with grey-white and gold veins, and
    gold constellations inlaid round the room (stars joined by lines), a ring of gold round the room's centre."""
    S = 2048
    rng = np.random.default_rng(41)
    n1 = wrap_blur(rng.random((S, S)).astype(np.float32), 24, 2)
    n2 = wrap_blur(rng.random((S, S)).astype(np.float32), 6, 2)
    n1 = (n1 - n1.min()) / (n1.max() - n1.min())
    n2 = (n2 - n2.min()) / (n2.max() - n2.min())
    img = np.zeros((S, S, 3), np.float32)
    img[:] = np.array([0.13, 0.12, 0.14])                     # black marble, but not so black that the unlit page shows nothing
    img *= (0.75 + 0.5 * n1)[..., None]
    # veins: thin bands where a warped field crosses levels
    f = n1 * 9.0 + n2 * 1.6
    v = np.abs((f % 1.0) - 0.5)
    vein = np.clip(1 - v / 0.018, 0, 1) * (n2 > 0.45)
    img = img * (1 - 0.6 * vein[..., None]) + np.array([0.50, 0.48, 0.46]) * 0.6 * vein[..., None]
    gold = np.clip(1 - np.abs(((n1 * 4.0 + n2 * 0.7) % 1.0) - 0.5) / 0.006, 0, 1) * (n1 > 0.55)
    img = img * (1 - 0.8 * gold[..., None]) + np.array(GOLD_S) * 0.8 * gold[..., None]
    ppm = S / FLOOR_SPAN

    def px(x, y):                  # Blender (x, y) -> (row, col)
        return ((FLOOR_SPAN / 2 - y) * ppm, (x + FLOOR_SPAN / 2) * ppm)

    # constellations: eight, one by each wall, made up (no real sky)
    for k in range(8):
        a = math.radians(22.5 + 45 * k)
        cx, cy = 3.3 * math.cos(a), 3.3 * math.sin(a)
        pts = [(cx + rng.uniform(-0.9, 0.9), cy + rng.uniform(-0.9, 0.9)) for _ in range(int(rng.integers(4, 8)))]
        pts.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
        for i in range(len(pts) - 1):
            line(img, px(*pts[i]), px(*pts[i + 1]), GOLD_S, 2.2)
        for p in pts:
            dot(img, px(*p), (1.0, 0.85, 0.5), rng.uniform(4, 7))
    # a gold ring and a compass star at the centre, under the runner's far end
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    rr = np.hypot(yy - S / 2, xx - S / 2) / ppm
    for R0 in (1.15, 1.25):
        img[np.abs(rr - R0) < 0.012] = GOLD_S
    for k in range(8):
        a = math.radians(45 * k)
        line(img, px(0, 0), px(1.1 * math.cos(a), 1.1 * math.sin(a)), GOLD_S, 2.5 if k % 2 == 0 else 1.5)
    return np.clip(img, 0, 1).astype(np.float32)


def damask_pixels():
    """Deep red silk damask, a seamless tile (DAMASK_TILE metres): a mirrored ogee lattice with a fleuron in each cell, satin on matte."""
    S = 512
    u, v = np.meshgrid((np.arange(S) + 0.5) / S, (np.arange(S) + 0.5) / S)
    ux = np.abs(u - 0.5) * 2                                  # mirror across the tile's centre line
    lattice = np.abs(np.sin(math.pi * (v * 2 + 0.5 * np.cos(math.pi * ux)))) < 0.10
    cy = (v * 2) % 1.0
    r = np.hypot(ux * 0.9, (cy - 0.5) * 1.3)
    th = np.arctan2(cy - 0.5, ux + 1e-6)
    petals = r < (0.30 + 0.10 * np.cos(5 * th))
    inner = r < 0.10
    stem = (ux < 0.05) & (np.abs(cy - 0.5) < 0.42)
    motif = (lattice | petals | stem) & ~inner
    base = np.array([0.42, 0.04, 0.06])
    sheen = np.array([0.64, 0.10, 0.12])
    img = np.where(motif[..., None], sheen, base).astype(np.float32)
    rng = np.random.default_rng(7)
    weave = wrap_blur(rng.random((S, S)).astype(np.float32), 1, 1)
    img *= (0.9 + 0.2 * weave)[..., None]
    return np.clip(wrap_blur(img, 1, 1), 0, 1).astype(np.float32)


def upper_pixels():
    """The upper wall: night blue plaster, a faint gold dust."""
    S = 512
    rng = np.random.default_rng(9)
    n = wrap_blur(rng.random((S, S)).astype(np.float32), 12, 2)
    n = (n - n.min()) / (n.max() - n.min())
    img = np.zeros((S, S, 3), np.float32)
    img[:] = np.array([0.08, 0.10, 0.22])
    img *= (0.85 + 0.3 * n)[..., None]
    dust = rng.random((S, S)) > 0.9985
    img[dust] = (0.7, 0.55, 0.28)
    return np.clip(img, 0, 1).astype(np.float32)


def placard_pixels():
    """The museum placard by the entrance (PLAN 2.2): cream letters on black, a gold rule."""
    W, H = 768, 512
    img = np.zeros((H, W, 3), np.float32)
    img[:] = (0.035, 0.03, 0.035)
    img[18:24, 30:W - 30] = img[H - 24:H - 18, 30:W - 30] = GOLD_S
    draw_text(img, "NYX", (40, 170, 0, W), (0.93, 0.88, 0.74), 0.85)
    draw_text(img, "NIGHT - THE VAULT OF NIGHT", (190, 270, 0, W), (0.86, 0.66, 0.30), 0.92)
    draw_text(img, "NINETY-NINE NOCTURNE SUITE", (290, 370, 0, W), (0.80, 0.76, 0.66), 0.92)
    draw_text(img, "XIII PIECES. VELVET. GILT. ONYX.", (380, 460, 0, W), (0.62, 0.58, 0.52), 0.92)
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


FLOOR_SPAN = 2 * RC + 0.1
DAMASK_TILE = 0.75


def mk_image(name, arr, srgb=True):
    h, w = arr.shape[:2]
    im = bpy.data.images.new(name + "_gen", w, h, alpha=False)
    im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :3] = arr
    im.pixels.foreach_set(np.flipud(rgba).ravel())
    gen = work() / "gen"
    gen.mkdir(parents=True, exist_ok=True)
    path = gen / f"{name}.png"
    im.filepath_raw = str(path)
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)
    out = bpy.data.images.load(str(path))
    out.name = name
    out.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    out.pack()
    for ref in [out] + list(out.packed_files):
        attr = "filepath_raw" if ref is out else "filepath"
        setattr(ref, attr, "_" * 1000)
        setattr(ref, attr, f"//generated/{name}.png")
    return out


# ---------------------------------------------------------------- materials
MATS = {}


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, img=None, emit=None, double=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if img is not None:
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "UVMap"
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = img
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
    if emit is not None:
        bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    m.use_backface_culling = not double
    MATS[name] = m
    return m


def make_materials(gen):
    material("Floor_Marble", img=gen["floor"], rough=0.25)
    material("Wall_Damask", img=gen["damask"], rough=0.6)
    material("Wall_Upper", img=gen["upper"], rough=0.85)
    material("Dome_Night", color=(0.0070, 0.0110, 0.0610), rough=0.9)          # #151d45: the plan's #0b1030 lifted, for the unlit page
    material("Gold_Trim", color=(0.40, 0.27, 0.09), rough=0.35, metal=0.9)          # antique gilt: the page draws it unlit, so not too light
    material("Trim_Black", color=(0.012, 0.010, 0.012), rough=0.4)
    material("Velvet_Curtain", color=(0.20, 0.012, 0.02), rough=0.9)
    material("Medallion_Egg", color=(0.006, 0.006, 0.008), rough=0.1)         # the scene code may light it (Zone_hint_align)
    material("Placard", img=gen["placard"], rough=0.5)
    material("Star_Emit", color=(1.0, 0.8, 0.45), emit=((1.0, 0.78, 0.40), 6.0))
    material("Star_Wire", color=(0.30, 0.22, 0.10), rough=0.4, emit=((0.9, 0.7, 0.4), 0.25))     # the fine wires the stars hang on
    material("Picture_Light_Emit", color=(1.0, 0.9, 0.7), emit=((1.0, 0.85, 0.6), 4.0))    # the placard light's strip: seen, but it lights nothing in the bake
    material("Sconce_Gilt", color=(0.62, 0.42, 0.14), rough=0.35, metal=0.9)                     # not baked: inches from its own bulb
    material("Star_Door", color=(0.02, 0.02, 0.04), emit=((1.0, 0.82, 0.48), 3.0))
    material("Lamp_Emit", color=(1.0, 0.85, 0.6), emit=((1.0, 0.62, 0.30), 8.0))


# ---------------------------------------------------------------- geometry helpers (Blender coordinates)
ART = LAYOUT = STAND = None


def flat_n(name):
    a = math.radians(FLATS[name])
    return Vector((math.cos(a), math.sin(a), 0.0))


def corner(k):
    a = math.radians(22.5 + 45 * k)
    return Vector((RC * math.cos(a), RC * math.sin(a), 0.0))


def oct_dist(p):
    """How far a point is from the centre in the octagon's own measure (the apothem on a wall)."""
    return max(p.x * math.cos(math.radians(a)) + p.y * math.sin(math.radians(a)) for a in range(0, 360, 45))


def mesh_obj(name, bm, mat, coll=None, smooth=False):
    me = bpy.data.meshes.new(name)
    if not bm.loops.layers.uv.get("UVMap"):
        bm.loops.layers.uv.new("UVMap")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = smooth
    if mat:
        me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(name, me)
    (coll or ART).objects.link(ob)
    return ob


def box_uv(bm, tile):
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            if ax == 2:
                u, v = p.x, p.y
            else:
                h = Vector((-n.y, n.x, 0)).normalized() if Vector((n.x, n.y, 0)).length > 1e-6 else Vector((1, 0, 0))
                u, v = p.dot(h), p.z
            lp[uvl].uv = (u / tile, v / tile)


def add_box(bm, c, size, rot=0.0):
    m = Matrix.Translation(c) @ Matrix.Rotation(rot, 4, "Z") @ Matrix.Diagonal((*size, 1.0))
    bmesh.ops.create_cube(bm, size=1.0, matrix=m)


def add_cyl(bm, p0, p1, r0, r1=None, seg=12, cap=True):
    a, b = Vector(p0), Vector(p1)
    d = b - a
    q = d.to_track_quat("Z", "Y")
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                          matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())


def wall_band(bm, z0, z1, inset=0.0, skip=None):
    """The eight walls' inner faces between heights z0 and z1, `inset` metres into the room; `skip` maps a flat to a (u0, u1) span to leave open."""
    for k in range(8):
        a, b = corner(k - 1), corner(k)               # flat k's ends (corners at 22.5 + 45k), wall normal angle 45k
        n = Vector((math.cos(math.radians(45 * k)), math.sin(math.radians(45 * k)), 0))
        sc = (APO - inset) / APO
        a, b = a * sc, b * sc
        spans = [(0.0, 1.0)]
        name = [f for f, ang in FLATS.items() if ang == 45 * k][0]
        if skip and name in skip:
            L = (b - a).length
            u0, u1 = skip[name]
            spans = [(0.0, (L / 2 + u0) / L), ((L / 2 + u1) / L, 1.0)]
        for s0, s1 in spans:
            p0, p1 = a.lerp(b, s0), a.lerp(b, s1)
            vs = [bm.verts.new((p0.x, p0.y, z0)), bm.verts.new((p0.x, p0.y, z1)), bm.verts.new((p1.x, p1.y, z1)), bm.verts.new((p1.x, p1.y, z0))]
            f = bm.faces.new(vs)
            f.normal_update()
            if f.normal.dot(n) > 0:                    # must face the room (inward = -n)
                f.normal_flip()


def wall_strip(bm, z0, z1, depth, inset=0.0):
    """A moulding running round all eight walls: its face `depth` proud of the wall, with top and bottom faces."""
    for k in range(8):
        a, b = corner(k - 1), corner(k)
        s_in = (APO - inset - depth) / APO
        s_wall = (APO - inset) / APO
        A, B = a * s_in, b * s_in
        Aw, Bw = a * s_wall, b * s_wall
        face = [(A, z0), (A, z1), (B, z1), (B, z0)]
        f = bm.faces.new([bm.verts.new((p.x, p.y, z)) for p, z in face])
        n = -Vector((math.cos(math.radians(45 * k)), math.sin(math.radians(45 * k)), 0))
        f.normal_update()
        if f.normal.dot(n) < 0:
            f.normal_flip()
        for z, up in ((z1, 1), (z0, -1)):
            g = bm.faces.new([bm.verts.new((p.x, p.y, z)) for p in (Aw, A, B, Bw)])
            g.normal_update()
            if g.normal.z * up < 0:
                g.normal_flip()


def build_shell():
    # floor: one octagon, the picture over the whole of it
    bm = bmesh.new()
    vs = [bm.verts.new((corner(k).x, corner(k).y, 0.0)) for k in range(8)]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.z < 0:
        f.normal_flip()
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp in f.loops:
        lp[uvl].uv = ((lp.vert.co.x + FLOOR_SPAN / 2) / FLOOR_SPAN, (lp.vert.co.y + FLOOR_SPAN / 2) / FLOOR_SPAN)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    mesh_obj("Floor", bm, "Floor_Marble")
    # walls: damask below the rail, night blue above; the south door's opening is left for the curtain's frame
    door_gap = {"S": (-0.62, 0.62)}
    bm = bmesh.new()
    wall_band(bm, 0.15, RAIL_Z, skip=door_gap)
    over = [bm.verts.new((x, -APO, z)) for x, z in ((-0.62, 2.45), (0.62, 2.45), (0.62, RAIL_Z), (-0.62, RAIL_Z))]   # over the door's head
    f = bm.faces.new(over)
    f.normal_update()
    if f.normal.y < 0:
        f.normal_flip()
    box_uv(bm, DAMASK_TILE)
    mesh_obj("Wall_Damask", bm, "Wall_Damask")
    bm = bmesh.new()
    wall_band(bm, RAIL_Z, WALL_H)
    box_uv(bm, 1.5)
    mesh_obj("Wall_Upper", bm, "Wall_Upper")
    bm = bmesh.new()
    wall_band(bm, 0.0, 0.15, skip=door_gap)
    box_uv(bm, 1.0)
    mesh_obj("Skirting", bm, "Trim_Black")
    # gilt: the rail, the cornice at the dome's spring
    bm = bmesh.new()
    wall_strip(bm, RAIL_Z - 0.03, RAIL_Z + 0.03, 0.025)
    wall_strip(bm, WALL_H - 0.16, WALL_H, 0.06)
    box_uv(bm, 1.0)
    mesh_obj("Gilt_Mouldings", bm, "Gold_Trim")
    # the dome: an octagonal cloister vault, elliptic in section, from the cornice to the apex
    rings = 14
    bm = bmesh.new()
    grid = []
    for i in range(rings + 1):
        th = math.radians(90) * i / rings
        s = math.cos(th)
        z = WALL_H + (DOME_TOP - WALL_H) * math.sin(th)
        if i == rings:
            grid.append([bm.verts.new((0, 0, DOME_TOP))])
        else:
            grid.append([bm.verts.new((corner(k).x * s, corner(k).y * s, z)) for k in range(8)])
    for i in range(rings):
        for k in range(8):
            if i == rings - 1:
                f = bm.faces.new([grid[i][k], grid[i][(k + 1) % 8], grid[i + 1][0]])
            else:
                f = bm.faces.new([grid[i][k], grid[i][(k + 1) % 8], grid[i + 1][(k + 1) % 8], grid[i + 1][k]])
            f.normal_update()
            c = f.calc_center_median()
            if f.normal.dot(c - Vector((0, 0, WALL_H))) > 0:
                f.normal_flip()
    box_uv(bm, 2.0)
    mesh_obj("Dome", bm, "Dome_Night", smooth=True)


def dome_z(x, y):
    s = min(oct_dist(Vector((x, y, 0))) / APO, 1.0)
    return WALL_H + (DOME_TOP - WALL_H) * math.sqrt(max(0.0, 1 - s * s))


def build_entrance():
    """The way in: a gilt frame on the south wall round a pleated oxblood velvet curtain (DoorLeaf_Nyx_In, origin on its west edge)."""
    bm = bmesh.new()
    y = -APO
    for x in (-0.565, 0.565):
        add_box(bm, Vector((x, y + 0.03, 1.2)), (0.12, 0.08, 2.40))
    add_box(bm, Vector((0, y + 0.03, 2.40)), (1.30, 0.10, 0.10))
    box_uv(bm, 1.0)
    mesh_obj("Door_Frame_In", bm, "Gold_Trim")
    # the reveal behind the curtain: night blue, so nothing shows through a gap
    bm = bmesh.new()
    add_box(bm, Vector((0, y - 0.11, 1.22)), (1.30, 0.02, 2.44))
    box_uv(bm, 1.0)
    mesh_obj("Door_Reveal_In", bm, "Trim_Black")
    # the curtain: a pleated sheet 0.94 x 2.16 (a door leaf in the exporter's terms), hinge at its west edge
    bm = bmesh.new()
    nx, nz = 24, 6
    verts = []
    for j in range(nz + 1):
        row = []
        for i in range(nx + 1):
            u = i / nx
            px = u * DOOR_W
            py = 0.035 * math.sin(u * math.pi * 12) * (0.6 + 0.4 * j / nz)
            row.append(bm.verts.new((px, py, j / nz * DOOR_H)))
        verts.append(row)
    for j in range(nz):
        for i in range(nx):
            f = bm.faces.new([verts[j][i], verts[j][i + 1], verts[j + 1][i + 1], verts[j + 1][i]])
            f.normal_update()
            if f.normal.y < 0:
                f.normal_flip()
    box_uv(bm, 1.0)
    ob = mesh_obj("DoorLeaf_Nyx_In", bm, "Velvet_Curtain", smooth=True)
    ob.location = (-DOOR_W / 2, y + 0.05, 0.0)


def build_medallion():
    """The black world egg inlaid in the floor where the stars line up (Spot_puzzle_align), in a gold ring."""
    bm = bmesh.new()
    seg = 40
    egg = [Vector((SPOT.x + 0.20 * math.cos(2 * math.pi * i / seg), SPOT.y + 0.27 * math.sin(2 * math.pi * i / seg) * (1 + 0.12 * math.sin(2 * math.pi * i / seg)), 0.004)) for i in range(seg)]
    f = bm.faces.new([bm.verts.new(p) for p in egg])
    bmesh.ops.triangulate(bm, faces=[f])
    box_uv(bm, 1.0)
    mesh_obj("Medallion_Egg", bm, "Medallion_Egg")
    bm = bmesh.new()
    inner = [bm.verts.new(SPOT + (p - SPOT) * 1.0 + Vector((0, 0, 0.0))) for p in egg]
    outer = [bm.verts.new(SPOT + (p - SPOT) * 1.22 + Vector((0, 0, 0.0))) for p in egg]
    for i in range(seg):
        bm.faces.new([inner[i], outer[i], outer[(i + 1) % seg], inner[(i + 1) % seg]])
    for f in bm.faces:
        f.normal_update()
        if f.normal.z < 0:
            f.normal_flip()
    box_uv(bm, 1.0)
    mesh_obj("Medallion_Ring", bm, "Gold_Trim")


def build_placard():
    bm = bmesh.new()
    c = Vector((1.05, -APO + 0.012, 1.0))
    w, h = 0.42, 0.28
    vs = [bm.verts.new(c + Vector(d)) for d in ((-w / 2, 0, -h / 2), (w / 2, 0, -h / 2), (w / 2, 0, h / 2), (-w / 2, 0, h / 2))]
    f = bm.faces.new(vs)
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp, t in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = t
    f.normal_update()
    if f.normal.y < 0:
        f.normal_flip()
        for lp in f.loops:
            pass
    mesh_obj("Placard", bm, "Placard")
    bm = bmesh.new()
    add_box(bm, c + Vector((0, -0.004, 0)), (w + 0.03, 0.008, h + 0.03))
    box_uv(bm, 1.0)
    mesh_obj("Placard_Frame", bm, "Gold_Trim")
    # a small brass picture light over it (its bulb strip is Lamp_Emit; the light itself is PLACARD_W in add_lights)
    bm = bmesh.new()
    top = c + Vector((0, 0, h / 2 + 0.06))
    add_cyl(bm, top + Vector((0, -0.004, 0)), top + Vector((0, 0.16, 0.05)), 0.008, seg=8)              # the arm, out from the wall
    head = top + Vector((0, 0.16, 0.05))
    add_cyl(bm, head - Vector((0.17, 0, 0)), head + Vector((0.17, 0, 0)), 0.022, seg=10)                 # the hood
    box_uv(bm, 1.0)
    mesh_obj("Placard_Light", bm, "Sconce_Gilt", smooth=True)
    bm = bmesh.new()
    add_box(bm, head + Vector((0, -0.004, -0.023)), (0.30, 0.012, 0.004))
    box_uv(bm, 1.0)
    mesh_obj("Placard_Light_Glow", bm, "Picture_Light_Emit")


SCONCES = [("N", -2.3), ("N", 2.3), ("W", -1.7), ("E", -2.6), ("SW", 0.0), ("SE", 0.0)]
SCONCE_Z = 2.25


def sconce_points():
    out = []
    for flat, u in SCONCES:
        n = flat_n(flat)
        t = Vector((-n.y, n.x, 0))
        out.append((flat, n * APO + t * u, n, t))
    return out


def build_sconces():
    """Swan-neck gilt sconces (the furniture's motif): a wall plate, a neck curving out and down to a cup, and a glowing teardrop bulb."""
    gold, bulbs = bmesh.new(), bmesh.new()
    for flat, w, n, t in sconce_points():
        base = w + Vector((0, 0, SCONCE_Z))
        add_box(gold, base - n * 0.015 + Vector((0, 0, -0.05)), (0.0, 0.0, 0.0))
        plate = base - n * 0.012
        m = Matrix.Translation(plate) @ Matrix.Rotation(math.atan2(n.y, n.x), 4, "Z") @ Matrix.Diagonal((0.024, 0.09, 0.22, 1))
        bmesh.ops.create_cube(gold, size=1.0, matrix=m)
        pts = []
        for i in range(9):
            s = i / 8
            out_d = 0.05 + 0.20 * math.sin(s * math.pi * 0.75)
            up = 0.10 * math.sin(s * math.pi) - 0.06 * s
            pts.append(plate - n * out_d + Vector((0, 0, up - 0.05)))
        for i in range(8):
            add_cyl(gold, pts[i], pts[i + 1], 0.014 - 0.004 * i / 8, 0.014 - 0.004 * (i + 1) / 8, seg=8)
        cup = pts[-1] + Vector((0, 0, 0.0))
        add_cyl(gold, cup + Vector((0, 0, -0.02)), cup + Vector((0, 0, 0.03)), 0.022, 0.035, seg=10)
        bc = cup + Vector((0, 0, 0.085))
        bmesh.ops.create_uvsphere(bulbs, u_segments=10, v_segments=6, radius=1.0,
                                  matrix=Matrix.Translation(bc) @ Matrix.Diagonal((0.03, 0.03, 0.055, 1)))
    box_uv(gold, 1.0)
    mesh_obj("Sconces", gold, "Sconce_Gilt", smooth=True)
    box_uv(bulbs, 1.0)
    mesh_obj("Sconce_Bulbs", bulbs, "Lamp_Emit", smooth=True)


def build_niche():
    """A gilt arch on the NE wall behind the statue of Nyx (a niche read from the room, flat on the wall)."""
    n = flat_n("NE")
    t = Vector((-n.y, n.x, 0))
    c = n * (APO - 0.012)
    bm = bmesh.new()
    pts = []
    for i in range(17):
        a = math.pi * i / 16
        pts.append(c + t * (0.75 * math.cos(a)) + Vector((0, 0, 2.6 + 0.75 * math.sin(a))))
    for i in range(16):
        add_cyl(bm, pts[i], pts[i + 1], 0.03, seg=6)
    for s in (-0.75, 0.75):
        add_cyl(bm, c + t * s, c + t * s + Vector((0, 0, 2.6)), 0.03, seg=6)
    box_uv(bm, 1.0)
    mesh_obj("Niche_Arch", bm, "Gold_Trim", smooth=True)
    bm = bmesh.new()
    vs = []
    for i in range(17):
        a = math.pi * i / 16
        vs.append(c - n * 0.0 + t * (0.72 * math.cos(a)) + Vector((0, 0, 2.6 + 0.72 * math.sin(a))))
    poly = [c + t * 0.72, *vs, c - t * 0.72]
    poly = [c + t * 0.72 + Vector((0, 0, 0.15))] + vs + [c - t * 0.72 + Vector((0, 0, 0.15))]
    f = bm.faces.new([bm.verts.new(p - n * 0.002) for p in poly])
    bmesh.ops.triangulate(bm, faces=[f])
    for g in bm.faces:
        g.normal_update()
        if g.normal.dot(n) > 0:
            g.normal_flip()
    box_uv(bm, 1.0)
    mesh_obj("Niche_Back", bm, "Wall_Upper")


# ---------------------------------------------------------------- the stars and the trick
def eye():
    return Vector((SPOT.x, SPOT.y, EYE))


SILL = 0.10                                   # the outline's lowest stars: their centres this high, so the largest (r <= 0.06) clear the floor


def door_outline(step=0.13):
    """Points round the star door (on the east wall's face): its two jambs, a round-arched head, and the knob."""
    pts = []
    y0, y1 = DOOR_C.y - DOOR_W / 2, DOOR_C.y + DOOR_W / 2
    spring = DOOR_H - DOOR_W / 2
    x = APO - 0.005
    n = max(2, int(spring / step))
    for i in range(n + 1):
        z = SILL + (spring - SILL) * i / n            # from the sill up: no star of the outline sits below the floor line
        pts += [Vector((x, y0, z)), Vector((x, y1, z))]
    m = max(4, int(math.pi * DOOR_W / 2 / step))
    for i in range(1, m):
        a = math.pi * i / m
        pts.append(Vector((x, DOOR_C.y - math.cos(a) * DOOR_W / 2, spring + math.sin(a) * DOOR_W / 2)))
    pts.append(Vector((x, y0 + 0.12, 1.0)))                  # the knob
    return pts


def star_bm(bm, c, normal, r):
    """A small four-pointed star (8 triangles) at c, facing `normal`."""
    q = normal.to_track_quat("Z", "Y")
    m = Matrix.Translation(c) @ q.to_matrix().to_4x4()
    ring = []
    for i in range(8):
        a = math.pi * i / 4
        rr = r if i % 2 == 0 else r * 0.38
        ring.append(bm.verts.new(m @ Vector((rr * math.cos(a), rr * math.sin(a), 0))))
    ctr = bm.verts.new(m @ Vector((0, 0, 0)))
    for i in range(8):
        bm.faces.new([ctr, ring[i], ring[(i + 1) % 8]])


def door_dirs():
    E = eye()
    return [(p - E).normalized() for p in door_outline()]


def build_stars():
    """About 400 gold stars: fixed ones on the dome and the upper walls (one mesh), and hanging ones on fine wires (each its own node,
    decor_star_*, pivot at the wire's top so the code can sway them). From the medallion, at the walker's eye, the decor_star_door_* line up
    into the star door on the east wall: each is placed on the line from the eye to a point of the door's outline, at a depth of 4 m to the wall."""
    rng = random.Random(1999)
    E = eye()
    ddirs = door_dirs()
    door_cone = math.radians(1.2)

    def near_door(p):
        d = (p - E).normalized()
        return any(d.angle(q) < door_cone for q in ddirs)

    # fixed: the dome (area-weighted by height band) and the upper walls
    bm = bmesh.new()
    n_fixed = 0
    tries = 0
    while n_fixed < N_STARS_FIXED and tries < 20000:
        tries += 1
        if rng.random() < 0.78:
            th = math.asin(rng.random() ** 0.8)                  # more low down, where the dome is wider
            ang = rng.uniform(0, 2 * math.pi)
            s = math.cos(th)
            # a point on the octagonal vault: scale the octagon's boundary at this angle
            dirv = Vector((math.cos(ang), math.sin(ang), 0))
            rb = APO / max(math.cos(ang - math.radians(a)) for a in range(0, 360, 45))
            p = dirv * rb * s * 0.995 + Vector((0, 0, WALL_H + (DOME_TOP - WALL_H) * math.sin(th) - 0.01))
            nrm = (Vector((0, 0, 4.6)) - p).normalized()
        else:
            k = rng.randrange(8)
            a, b = corner(k - 1), corner(k)
            p = a.lerp(b, rng.uniform(0.04, 0.96)) * ((APO - 0.006) / APO)
            p.z = rng.uniform(RAIL_Z + 0.12, WALL_H - 0.22)
            nrm = -Vector((math.cos(math.radians(45 * k)), math.sin(math.radians(45 * k)), 0))
        if near_door(p):
            continue
        star_bm(bm, p, nrm, rng.uniform(0.018, 0.045))
        n_fixed += 1
    box_uv(bm, 1.0)
    mesh_obj("decor_stars_fixed", bm, "Star_Emit")
    # the door's stars: depth 4 m to the wall along each line from the eye
    door_pts = []
    for i, d in enumerate(ddirs):
        tw = (APO - 0.005 - E.x) / d.x                            # where the line meets the east wall
        on_wall = rng.random() < 0.25 or tw < 4.4
        t = tw if on_wall else rng.uniform(4.0, tw - 0.35)
        door_pts.append((E + d * t, on_wall, t))
    free_pts = []
    while len(free_pts) < N_STARS_FREE:
        p = Vector((rng.uniform(-4.2, 4.2), rng.uniform(-4.2, 4.2), rng.uniform(1.0, 3.2)))
        if oct_dist(p) > APO - 0.5 or near_door(p) or (p.xy - SPAWN.xy).length < 0.8:
            continue
        free_pts.append(p)
    wall_bm = bmesh.new()
    n_door = 0
    for tag, pts in (("door", door_pts), ("free", [(p, False, None) for p in free_pts])):
        for i, (p, on_wall, t) in enumerate(pts):
            d = (p - E).normalized()
            r = 0.007 * (t if t else (p - E).length) * (1.0 if tag == "door" else rng.uniform(0.8, 1.4))
            if on_wall:
                star_bm(wall_bm, p, -Vector((1, 0, 0)), r)
                n_door += 1
                continue
            top = Vector((p.x, p.y, dome_z(p.x, p.y) - 0.01))
            bm = bmesh.new()
            star_bm(bm, p - top, -d, r)                           # local to the pivot at the wire's top, facing the eye
            bm.faces.ensure_lookup_table()
            for f in bm.faces:
                f.material_index = 0
            n0 = len(bm.faces)
            add_cyl(bm, Vector((0, 0, 0)), p - top + Vector((0, 0, r * 0.5)), 0.0008, seg=3, cap=False)
            bm.faces.ensure_lookup_table()
            for f in bm.faces[n0:]:
                f.material_index = 1
            box_uv(bm, 1.0)
            ob = mesh_obj(f"decor_star_{tag}_{i:02d}", bm, "Star_Emit")
            ob.data.materials.append(MATS["Star_Wire"])
            ob.location = top
    box_uv(wall_bm, 1.0)
    mesh_obj("decor_stars_door_wall", wall_bm, "Star_Emit")
    print(f"STARS fixed {n_fixed}, door {len(door_pts)} ({n_door} on the wall), free {len(free_pts)}")


def build_star_door():
    """DoorLeaf_Nyx_Star: the door the stars draw, shown by the scene code when the walker stands on the medallion and looks at it. A dark leaf
    with a glowing gold edge, flush on the east wall, hinge on its south edge. Hidden in the bake (it is not there until the trick)."""
    bm = bmesh.new()
    spring = DOOR_H - DOOR_W / 2
    outline = [(0.0, 0.0), (0.0, spring)]
    for i in range(1, 16):
        a = math.pi * i / 16
        outline.append((DOOR_W / 2 - math.cos(a) * DOOR_W / 2, spring + math.sin(a) * DOOR_W / 2))
    outline += [(DOOR_W, spring), (DOOR_W, 0.0)]
    f = bm.faces.new([bm.verts.new((-0.004, u, z)) for u, z in outline])
    bmesh.ops.triangulate(bm, faces=[f])
    for g in bm.faces:
        g.normal_update()
        if g.normal.x > 0:
            g.normal_flip()
    for i in range(len(outline) - 1):
        (u0, z0), (u1, z1) = outline[i], outline[i + 1]
        add_cyl(bm, Vector((-0.008, u0, z0)), Vector((-0.008, u1, z1)), 0.012, seg=6)
    box_uv(bm, 1.0)
    ob = mesh_obj("DoorLeaf_Nyx_Star", bm, "Star_Door")
    ob.location = (APO, DOOR_C.y - DOOR_W / 2, 0.0)
    return ob


# ---------------------------------------------------------------- the furniture
def yaw_for(code, facing):
    return math.radians(COMPASS[facing] - NATIVE_FRONT[code])


def load_copy(code, name, objname):
    path = next(COPIES.glob(f"{code}_*_game.glb"))
    if objname.endswith("_E") and f"{code}_mesh" in bpy.data.meshes:
        me = bpy.data.meshes[f"{code}_mesh"].copy()          # its own mesh: the second bedside table needs its own lightmap texels
        ob = bpy.data.objects.new(objname, me)
        ART.objects.link(ob)
        return ob
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.data.objects if o not in before]
    ob = next(o for o in new if o.type == "MESH")
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        if o is not ob:
            bpy.data.objects.remove(o)
    ART.objects.link(ob)
    ob.name = objname
    ob.data.name = f"{code}_mesh"
    ob.matrix_world = Matrix.Identity(4)
    for m in ob.data.materials:
        if m.node_tree:
            for nd in m.node_tree.nodes:
                if nd.type == "TEX_IMAGE" and nd.image:
                    nd.image.pack()
    return ob


def world_verts(ob):
    mw = ob.matrix_world
    return [mw @ v.co for v in ob.data.vertices]


def bvh_of(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    t = BVHTree.FromBMesh(bm)
    bm.free()
    return t


def place_all():
    placed = {}
    for code, objname, xy, facing, how in PLACE:
        ob = load_copy(code, objname, objname)
        ob.rotation_mode = "XYZ"                     # the glTF importer leaves quaternions
        ob.rotation_euler = (0, 0, yaw_for(code, facing))
        ob.location = (xy[0], xy[1], 0.0)
        bpy.context.view_layer.update()
        if how[0] == "wall" or how[0] == "hang":
            n = flat_n(how[1])
            gap = how[2]
            reach = max(v.dot(n) for v in world_verts(ob))
            ob.location = Vector(ob.location) + n * (APO - gap - reach)
            if how[0] == "hang":
                ob.location.z = how[3]
        elif how[0] == "on":
            sup = placed[how[1]]
            bpy.context.view_layer.update()
            sv = world_verts(sup)
            cx = (min(v.x for v in sv) + max(v.x for v in sv)) / 2
            cy = (min(v.y for v in sv) + max(v.y for v in sv)) / 2
            sx, sy = xy
            tgt = Vector((cx + sx, cy + sy, 0))
            hit = bvh_of(sup).ray_cast(Vector((tgt.x, tgt.y, 5.0)), Vector((0, 0, -1)))
            top = hit[0].z if hit[0] is not None else max(v.z for v in sv)
            ob.location = (tgt.x, tgt.y, top - 0.003)
        bpy.context.view_layer.update()
        placed[objname] = ob
        vs = world_verts(ob)
        lo = [min(v[i] for v in vs) for i in range(3)]
        hi = [max(v[i] for v in vs) for i in range(3)]
        print(f"PLACE {objname}: ({lo[0]:.2f}, {lo[1]:.2f}, {lo[2]:.2f}) .. ({hi[0]:.2f}, {hi[1]:.2f}, {hi[2]:.2f})")
    return placed


# ---------------------------------------------------------------- the exporter's objects (BLENDER_AREAS part 2), kept in Layout
def col_box(name, lo, hi):
    bm = bmesh.new()
    add_box(bm, (Vector(lo) + Vector(hi)) / 2, tuple(Vector(hi) - Vector(lo)))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    LAYOUT.objects.link(ob)
    ob.display_type = "WIRE"
    ob.hide_render = True
    return ob


def empty(name, loc, kind=None, yaw=0.0, size=0.3, **props):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_type = "ARROWS"
    ob.empty_display_size = size
    ob.location = loc
    ob.rotation_euler = (0, 0, yaw)
    if kind:
        ob["kind"] = kind
    for k, v in props.items():
        ob[k] = v
    LAYOUT.objects.link(ob)
    return ob


def build_layout(placed):
    """COL_ boxes: the four axis walls as boxes, the four diagonal walls as rows of 0.35 m boxes, the floor, a box per standing piece; the star
    door's opening in the east wall is COL_plug_nyx_star (the scene code removes it). Markers, links, zones and spots as PLAN 4.1."""
    col_box("COL_floor", (-RC, -RC, -0.2), (RC, RC, 0.0))
    for flat in ("N", "S", "W"):
        n = flat_n(flat)
        t = Vector((-n.y, n.x, 0))
        half = APO * math.tan(math.radians(22.5))
        c = n * (APO + WALL_T / 2)
        if flat == "S":
            for s0, s1, nm in ((-half, -0.47, "a"), (0.47, half, "b")):
                p0, p1 = c + t * s0, c + t * s1
                col_box(f"COL_wall_S_{nm}", (min(p0.x, p1.x), c.y - WALL_T / 2, 0), (max(p0.x, p1.x), c.y + WALL_T / 2, WALL_H))
            col_box("COL_wall_S_head", (-0.47, c.y - WALL_T / 2, DOOR_H), (0.47, c.y + WALL_T / 2, WALL_H))
            continue
        p0, p1 = c + t * half, c - t * half
        lo = Vector((min(p0.x, p1.x), min(p0.y, p1.y), 0)) - Vector((WALL_T / 2 if abs(n.x) > 0.5 else 0, WALL_T / 2 if abs(n.y) > 0.5 else 0, 0))
        hi = Vector((max(p0.x, p1.x), max(p0.y, p1.y), WALL_H)) + Vector((WALL_T / 2 if abs(n.x) > 0.5 else 0, WALL_T / 2 if abs(n.y) > 0.5 else 0, 0))
        col_box(f"COL_wall_{flat}", lo, hi)
    half = APO * math.tan(math.radians(22.5))
    y0, y1 = DOOR_C.y - DOOR_W / 2, DOOR_C.y + DOOR_W / 2
    col_box("COL_wall_E_a", (APO, -half, 0), (APO + WALL_T, y0, WALL_H))
    col_box("COL_wall_E_b", (APO, y1, 0), (APO + WALL_T, half, WALL_H))
    col_box("COL_wall_E_head", (APO, y0, DOOR_H), (APO + WALL_T, y1, WALL_H))
    col_box("COL_plug_nyx_star", (APO - 0.02, y0, 0), (APO + WALL_T, y1, DOOR_H))
    for flat in ("NE", "NW", "SW", "SE"):
        k = FLATS[flat] // 45
        a, b = corner(k - 1), corner(k)
        n = flat_n(flat)
        L = (b - a).length
        m = int(math.ceil(L / 0.35))
        for i in range(m):
            p = a.lerp(b, (i + 0.5) / m) + n * 0.26
            s = 0.35 * math.cos(math.radians(45)) + 0.12
            col_box(f"COL_wall_{flat}_{i:02d}", (p.x - s / 2, p.y - s / 2, 0), (p.x + s / 2, p.y + s / 2, WALL_H))
    for nm, ob in placed.items():
        if nm.startswith(("NX-00", "NX-08", "NX-09", "NX-10", "NX-12", "NX-11")):
            continue                                   # on the furniture, or flat on the floor
        vs = world_verts(ob)
        col_box(f"COL_{nm}", [min(v[i] for v in vs) for i in range(3)], [max(v[i] for v in vs) for i in range(3)])
    face_n = math.radians(180)                         # an Arrive_'s -Y axis is the way you face: yaw 180 faces +Y (north)
    empty("Marker_Spawn", (SPAWN.x, SPAWN.y, 0), "Spawn", yaw=face_n)
    empty("Marker_Entrance", (0, -APO + 0.3, 0), "Entrance", yaw=face_n)
    empty("Marker_Exit", (APO - 0.3, DOOR_C.y, 0), "Exit", yaw=math.radians(90))
    empty("Arrive_Nyx_In", (SPAWN.x, SPAWN.y, 0), yaw=face_n, note="where the walker stands after the velvet curtain (from trampoline)")
    empty("Link_Nyx_Star", (APO - 0.35, DOOR_C.y, 0), to_scene="rdwe_god_selene", to_arrive="Arrive_Selene_In")
    empty("Spot_puzzle_align", (SPOT.x, SPOT.y, 0), note=f"eye {EYE} m; look within 8 degrees of the line to the star door's centre")
    for nm, r in (("Zone_hint_align", 0.5), ("Zone_trigger_align", 0.2)):
        z = col_box(nm, (SPOT.x - r, SPOT.y - r, 0), (SPOT.x + r, SPOT.y + r, 2.0))
    col_box("Zone_trigger_star", (APO - 0.25, y0 + 0.05, 0), (APO + WALL_T, y1 - 0.05, DOOR_H))
    leaf_in = bpy.data.objects["DoorLeaf_Nyx_In"]
    leaf_in["hinge"] = "west edge"
    leaf_in["swing_deg"] = 0
    leaf_in["state"] = "closed"
    leaf_star = bpy.data.objects["DoorLeaf_Nyx_Star"]
    leaf_star["hinge"] = "south edge"
    leaf_star["swing_deg"] = 90
    leaf_star["state"] = "hidden until the trick"


# ---------------------------------------------------------------- lights (for the bake and the stills; never exported)
SCONCE_W = 9.0           # each sconce's bulb (W)
PLACARD_W = 0.09         # the placard's picture light (an area light under its hood, aimed at the plate)
LAMP_W = 10.0            # the bedside lamp
STARLIGHT_W = 160.0      # the dome's cool glow, an area light under the apex pointing down: the even part of the light
CANOPY_W = 0.0


def add_lights():
    lights = bpy.data.collections.new("Lights")
    bpy.context.scene.collection.children.link(lights)

    def light(name, kind, loc, energy, color, size=0.05):
        d = bpy.data.lights.new(name, kind)
        d.energy, d.color = energy, color
        d.shadow_soft_size = size
        ob = bpy.data.objects.new(name, d)
        ob.location = loc
        lights.objects.link(ob)
        return ob, d

    for i, (flat, w, n, t) in enumerate(sconce_points()):
        light(f"Sconce_{i}", "POINT", w - n * 0.203 + Vector((0, 0, SCONCE_Z - 0.025)), SCONCE_W, (1.0, 0.66, 0.36), 0.03)
    lamp = bpy.data.objects.get("NX-00_lamp")
    if lamp:
        vs = world_verts(lamp)
        z0 = min(v.z for v in vs)
        H = max(v.z for v in vs) - z0
        band = [v for v in vs if z0 + 0.5 * H < v.z < z0 + 0.8 * H]          # the teardrop shade hangs in this band
        c = sum(band, Vector()) / len(band)
        near = [v.z for v in vs if (v.xy - c.xy).length < 0.05 and v.z > z0 + 0.5 * H]
        bottom = min(near) if near else c.z
        light("Lamp_Bulb", "POINT", (c.x, c.y, bottom - 0.06), LAMP_W, (1.0, 0.6, 0.32), 0.03)
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.022, matrix=Matrix.Translation((c.x, c.y, bottom - 0.025)))
        box_uv(bm, 1.0)
        mesh_obj("Lamp_Glow", bm, "Lamp_Emit", smooth=True)
    pc = Vector((1.05, -APO + 0.012 + 0.16, 1.0 + 0.14 + 0.06 + 0.05 - 0.03))
    ob, d = light("Placard_Light", "AREA", pc, PLACARD_W, (1.0, 0.85, 0.65), 0.0)
    d.shape, d.size, d.size_y = "RECTANGLE", 0.28, 0.02
    ob.rotation_euler = (Vector((1.05, -APO, 1.0)) - pc).to_track_quat("-Z", "Y").to_euler()
    ob, d = light("Starlight", "AREA", (0, 0, DOME_TOP - 0.6), STARLIGHT_W, (0.45, 0.55, 1.0), 0.0)
    d.shape, d.size = "DISK", 4.0


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("Night")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
    bg.inputs["Strength"].default_value = 0.0


def build_all():
    global ART, LAYOUT
    clear_scene()
    MATS.clear()
    ART = bpy.data.collections.new("Art")
    LAYOUT = bpy.data.collections.new("Layout")
    sc = bpy.context.scene
    sc.collection.children.link(ART)
    sc.collection.children.link(LAYOUT)
    gen = {"floor": mk_image("Nyx_Floor", floor_pixels()), "damask": mk_image("Nyx_Damask", damask_pixels()),
           "upper": mk_image("Nyx_Upper", upper_pixels()), "placard": mk_image("Nyx_Placard", placard_pixels())}
    make_materials(gen)
    build_shell()
    build_entrance()
    build_medallion()
    build_placard()
    build_sconces()
    build_niche()
    build_stars()
    build_star_door()
    placed = place_all()
    build_layout(placed)
    add_lights()
    setup_world()
    sc.unit_settings.system = "METRIC"
    for o in ART.objects:
        if o.type == "MESH" and o.data.materials and o.data.materials[0].name in ("Lamp_Emit", "Star_Emit", "Star_Door", "Sconce_Gilt", "Picture_Light_Emit"):
            o.visible_shadow = False                  # the lamps' bulbs hold their point lights; the stars and the wires cast nothing


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    scrub_private()
    bpy.ops.wm.save_mainfile()


# ================================================================ bake (R1)
def furn(*codes):
    return tuple(f"Nyx_{c}_" for c in codes)


GROUPS = [
    ("Floor_Marble", "Wall_Damask", "Wall_Upper", "Gold_Trim", "Trim_Black", "Velvet_Curtain", "Medallion_Egg", "Placard"),  # 0 floor, walls, trim
    ("Dome_Night",),                                                                                                        # 1 the dome
    furn("NX-01", "NX-02", "NX-03", "NX-04", "NX-05", "NX-06", "NX-07", "NX-11"),                                          # 2 the big furniture
    furn("NX-00", "NX-08", "NX-09", "NX-10", "NX-12", "P4", "P9", "P18", "P20"),                                           # 3 the smalls and the props
]
MIN_DENSITY = [30, 24, 60, 60]          # px per metre wanted on each map (the search takes the smallest page that gives it)
PAGES = [1024, 512, 768, 1280]          # the pages the first full bake chose (Blender's packer is not exactly repeatable); --pages a,b,c,d or auto
if arg("--pages"):
    PAGES = [None if v == "auto" else int(v) for v in arg("--pages").split(",")]
NOLM = ("Star_Emit", "Star_Door", "Lamp_Emit", "Star_Wire", "Sconce_Gilt", "Picture_Light_Emit")
KEEP_NODES = ("DoorLeaf_", "decor_star_")     # exported as their own nodes (the scene code moves or hides them), not merged by material
MAIN = ("Floor_Marble", "Wall_Damask", "Wall_Upper", "Dome_Night", "Velvet_Curtain", "Nyx_")   # the surfaces held to a displayed p90 <= TARGET
NOT_MAIN = ("Nyx_NX-00_lamp",)          # the lamp's own body, inches from its bulb: reported, not held (it may glow white where the bulb is)
TARGET_P90 = arg("--target", 0.90, float)
CLIP_CAP = arg("--clip-cap", 0.98, float)     # and no main surface's p99 above this (0 turns the cap off): the furniture's gilt and marble
                                              # run about twice their p90, so this cap, not the target, can be the one that binds     # the brightest main surface's displayed p90; a night room, so well under the 1.0 that clips


def group_of(mname):
    for n, g in enumerate(GROUPS):
        if any(mname == x or (x.endswith("_") and mname.startswith(x)) for x in g):
            return n
    return None


def make_export_objects():
    art = bpy.data.collections["Art"]
    if "Export" in bpy.data.collections:
        for o in list(bpy.data.collections["Export"].objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(bpy.data.collections["Export"])
    exp = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(exp)
    by_mat, out = {}, {}
    for ob in art.objects:
        if ob.type != "MESH":
            continue
        assert len(ob.data.materials) == 1 or ob.name.startswith(KEEP_NODES), ob.name
        mname = ob.data.materials[0].name
        if ob.name.startswith(KEEP_NODES):
            me = ob.data.copy()
            me.name = ob.name
            o2 = bpy.data.objects.new(ob.name + "_x", me)
            o2.matrix_world = ob.matrix_world.copy()
            exp.objects.link(o2)
            out[o2.name] = o2
            continue
        bm = by_mat.setdefault(mname, bmesh.new())
        tmp = ob.data.copy()
        tmp.transform(ob.matrix_world)
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
    for mname, bm in by_mat.items():
        tiny = [f for f in bm.faces if f.calc_area() < 1e-9]       # zero-area slivers left by the decimation: they would blow up average_islands_scale
        if tiny:
            bmesh.ops.delete(bm, geom=tiny, context="FACES")
            print(f"  {mname}: dropped {len(tiny)} zero-area faces")
        me = bpy.data.meshes.new(mname)
        bm.to_mesh(me)
        bm.free()
        me.materials.clear()
        me.materials.append(bpy.data.materials[mname])
        ob = bpy.data.objects.new(mname + "_x", me)
        exp.objects.link(ob)
        out[ob.name] = ob
    for ob in out.values():
        if ob.data.materials[0].name in NOLM:
            ob.visible_shadow = False
        if ob.data.materials[0].name == "Picture_Light_Emit":
            ob.visible_diffuse = ob.visible_glossy = False     # the area light under the hood is the placard's light; the strip only shows
    return out


def area3d(ob):
    return sum(p.area for p in ob.data.polygons)


def uv_area(ob, layer):
    uv = ob.data.uv_layers[layer].data
    tot = 0.0
    for p in ob.data.polygons:
        pts = [uv[i].uv for i in p.loop_indices]
        n = len(pts)
        tot += abs(sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))) / 2
    return tot


def shelf_pack(sides, gap):
    """Squares of the given sides (in a common unit), packed in shelves into the unit square at the largest common scale that fits, with
    `gap` (in the unit square) round each. Returns the scale and each square's lower-left corner."""
    order = sorted(range(len(sides)), key=lambda i: -sides[i])

    def fit(k):
        pos, x, y, row = {}, 0.0, 0.0, 0.0
        for i in order:
            w = sides[i] * k
            if x + w + gap > 1.0:
                x, y, row = 0.0, y + row + gap, 0.0
            if y + w + gap > 1.0 or w + 2 * gap > 1.0:
                return None
            pos[i] = (x + gap, y + gap)
            x += w + gap
            row = max(row, w)
        return pos
    lo, hi = 0.0, 1.0 / max(sides)
    for _ in range(40):
        mid = (lo + hi) / 2
        if fit(mid):
            lo = mid
        else:
            hi = mid
    return lo, fit(lo)


def lightmap_uv(objs, page, min_d):
    """One shared atlas for `objs`, at about equal texel density, on a page of `page` px (or the smallest of the search that gives `min_d`).
    The room's own pieces: smart-project islands, packed by Blender. The furniture and the props: each piece keeps its own UV0 layout (the
    copies stage's islands, which do not overlap) as one square, and the squares are shelf-packed here, sized by each piece's area; Blender's
    island packer packs ~150k decimated triangles to nothing, so it is not used on them."""
    furn_objs = [o for o in objs if o.data.materials[0].name.startswith("Nyx_")]
    assert len(furn_objs) in (0, len(objs)), "a lightmap group is either the room's or the furniture's"
    for o in objs:
        uvs = o.data.uv_layers
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.active = uvs.new(name="lightmap")
    sizes = (page,) if page else (512, 768, 1024, 1280, 1536, 1792, 2048)
    if furn_objs:
        src = []
        for o in objs:
            a = np.zeros(len(o.data.loops) * 2, np.float32)
            o.data.uv_layers["UVMap"].data.foreach_get("uv", a)
            src.append(a.reshape(-1, 2))
        parts = []
        for o, a in zip(objs, src):
            me = o.data
            bm = bmesh.new()
            bm.from_mesh(me)
            areas = np.array([f.calc_area() for f in bm.faces])
            bm.free()
            # one UV0 square per piece; the merged bedside pair (two pieces, one UV0) splits by its centre x
            poly_lstart = np.zeros(len(me.polygons), np.int32)
            me.polygons.foreach_get("loop_start", poly_lstart)
            poly_ltot = np.zeros(len(me.polygons), np.int32)
            me.polygons.foreach_get("loop_total", poly_ltot)
            cx = np.zeros(len(me.polygons) * 3, np.float32)
            me.polygons.foreach_get("center", cx)
            cx = cx.reshape(-1, 3)[:, 0]
            keys = [0] * len(me.polygons)
            if o.name.startswith("Nyx_NX-01_"):
                keys = [0 if c < 0 else 1 for c in cx]
            for key in sorted(set(keys)):
                polys = [i for i, k in enumerate(keys) if k == key]
                loops = np.concatenate([np.arange(poly_lstart[i], poly_lstart[i] + poly_ltot[i]) for i in polys])
                area = float(areas[polys].sum())
                uv = a[loops]
                lo_, hi_ = uv.min(axis=0), uv.max(axis=0)
                uvA = 0.0
                for i in polys:
                    pts = a[poly_lstart[i]:poly_lstart[i] + poly_ltot[i]]
                    uvA += abs(np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - np.roll(pts[:, 0], -1) * pts[:, 1])) / 2
                side = float(max(hi_ - lo_)) * math.sqrt(area / max(uvA, 1e-12))      # metres the square spans at equal density
                parts.append((o, loops, lo_, float(max(hi_ - lo_)), side))
        chosen = None
        for S in sizes:
            k, pos = shelf_pack([p[4] for p in parts], (MARGIN_PX + 2) / S)
            dens = S * k
            chosen = (S, dens, k, pos)
            print(f"  page {S}: {sum(area3d(o) for o in objs):.1f} m2, {dens:.1f} px/m (shelf pack)")
            if dens >= min_d:
                break
        S, dens, k, pos = chosen
        out = {o.name: np.zeros((len(o.data.loops), 2), np.float32) for o in objs}
        for i, (o, loops, lo_, span, side) in enumerate(parts):
            x0, y0 = pos[i]
            out[o.name][loops] = (src[objs.index(o)][loops] - lo_) / span * side * k + np.array([x0, y0])
        for o in objs:
            o.data.uv_layers["lightmap"].data.foreach_set("uv", out[o.name].ravel())
        return S, dens
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    chosen = None
    for S in sizes:
        bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / S, shape_method="CONCAVE")
        bpy.ops.object.mode_set(mode="OBJECT")
        a3 = sum(area3d(o) for o in objs)
        au = sum(uv_area(o, "lightmap") for o in objs)
        dens = S * math.sqrt(au / a3)
        print(f"  page {S}: {a3:.1f} m2, {dens:.1f} px/m")
        chosen = (S, dens)
        assert dens > 1.0, "the lightmap atlas packed to nothing"
        if dens >= min_d:
            break
        bpy.ops.object.mode_set(mode="EDIT")
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    return chosen


def srgb_encode(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def srgb_decode(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def denoise_image(img, S):
    sc = bpy.data.scenes.new("dn")
    ng = bpy.data.node_groups.new("dn", "CompositorNodeTree")
    ni = ng.nodes.new("CompositorNodeImage")
    ni.image = img
    dn = ng.nodes.new("CompositorNodeDenoise")
    go = ng.nodes.new("NodeGroupOutput")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    ng.links.new(ni.outputs[0], dn.inputs["Image"])
    ng.links.new(dn.outputs[0], go.inputs[0])
    sc.compositing_node_group = ng
    sc.render.resolution_x = sc.render.resolution_y = S
    sc.render.resolution_percentage = 100
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 1
    sc.render.image_settings.file_format = "OPEN_EXR"
    sc.render.image_settings.color_depth = "32"
    cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    path = str(work() / "dn.exr")
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=sc.name)
    r = bpy.data.images.load(path)
    a = np.empty(S * S * 4, np.float32)
    r.pixels.foreach_get(a)
    bpy.data.images.remove(r)
    bpy.data.objects.remove(cam)
    bpy.data.scenes.remove(sc)
    bpy.data.node_groups.remove(ng)
    return a.reshape(S, S, 4)


IMG_NP = {}


def base_sampler(mat):
    """The material's base colour (linear) at UV0 points: its texture, or its constant."""
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    sock = bsdf.inputs["Base Color"]
    if not sock.is_linked:
        c = np.array(sock.default_value[:3], np.float32)
        return lambda uv: np.broadcast_to(c, (len(uv), 3))
    node = sock.links[0].from_node
    while node.type != "TEX_IMAGE":
        node = [l.from_node for i in node.inputs for l in i.links][0]
    im = node.image
    if im.name not in IMG_NP:
        w, h = im.size
        a = np.empty(w * h * 4, np.float32)
        im.pixels.foreach_get(a)
        a = a.reshape(h, w, 4)[..., :3]
        if im.colorspace_settings.name == "sRGB" and not im.is_float:
            a = srgb_decode(a)
        IMG_NP[im.name] = a
    a = IMG_NP[im.name]
    h, w = a.shape[:2]

    def f(uv):
        x = np.clip(((uv[:, 0] % 1.0) * w).astype(int), 0, w - 1)
        y = np.clip(((uv[:, 1] % 1.0) * h).astype(int), 0, h - 1)
        return a[y, x]
    return f


def displayed_stats(ob, lm, scale, n_pts=200000):
    """What the page shows (base colour x lightmap x intensity, linear, 1.0 = white, the brightest channel) at random points spread over the
    surface by area. `lm` is the raw bake; the page's copy is clipped at `scale`."""
    me = ob.data
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    uv0 = np.zeros((len(me.loops), 2), np.float32)
    uv1 = np.zeros((len(me.loops), 2), np.float32)
    me.uv_layers["UVMap"].data.foreach_get("uv", uv0.ravel())
    me.uv_layers["lightmap"].data.foreach_get("uv", uv1.ravel())
    loops = np.zeros(n * 3, np.int32)
    me.loop_triangles.foreach_get("loops", loops)
    loops = loops.reshape(n, 3)
    area = np.zeros(n, np.float32)
    me.loop_triangles.foreach_get("area", area)
    rng = np.random.default_rng(5)
    tri = rng.choice(n, size=n_pts, p=area / area.sum())
    w = rng.random((n_pts, 2))
    flip = w.sum(axis=1) > 1
    w[flip] = 1 - w[flip]
    bary = np.stack([1 - w[:, 0] - w[:, 1], w[:, 0], w[:, 1]], axis=1)[..., None]
    c0 = (uv0[loops[tri]] * bary).sum(axis=1)
    c1 = (uv1[loops[tri]] * bary).sum(axis=1)
    S = lm.shape[0]
    x = np.clip((c1[:, 0] * S).astype(int), 0, S - 1)
    y = np.clip((c1[:, 1] * S).astype(int), 0, S - 1)
    light = np.minimum(lm[y, x], scale)
    base = base_sampler(me.materials[0])(c0)
    disp = np.sort((base * light).max(axis=1))
    p = lambda q: float(disp[min(int(q * n_pts), n_pts - 1)])
    return {"p50": p(0.5), "p90": p(0.9), "p99": p(0.99), "area_m2": float(area.sum())}


def reset_lights():
    """The lights at the constants' energies (the saved .blend holds them times the last bake's exposure), so a bake is the same from any start."""
    for ob in bpy.data.collections["Lights"].objects:
        for prefix, w in (("Sconce_", SCONCE_W), ("Lamp_Bulb", LAMP_W), ("Starlight", STARLIGHT_W), ("Placard_Light", PLACARD_W)):
            if ob.name.startswith(prefix):
                ob.data.energy = w


def stage_bake():
    reset_lights()
    exp = make_export_objects()
    bpy.data.collections["Art"].hide_render = True
    exp["DoorLeaf_Nyx_Star_x"].hide_render = True          # not there until the trick
    setup_cycles(SAMPLES, bake=True)
    report, stats, raw = {}, {}, {}
    for n, mats in enumerate(GROUPS):
        t0 = time.time()
        objs = [o for o in exp.values() if group_of(o.data.materials[0].name) == n]
        print(f"lightmap {n}: {[o.name for o in objs]}")
        S, dens = lightmap_uv(objs, PAGES[n], MIN_DENSITY[n])
        img = bpy.data.images.new(f"LM_{n}", S, S, alpha=False, float_buffer=True)
        img.colorspace_settings.name = "Non-Color"
        for m in {o.data.materials[0] for o in objs}:
            nt = m.node_tree
            node = nt.nodes.new("ShaderNodeTexImage")
            node.name = "BAKE_TARGET"
            node.image = img
            nt.nodes.active = node
        select_only(objs)
        for o in objs:
            o.data.uv_layers.active = o.data.uv_layers["lightmap"]
        bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX, margin_type="EXTEND", use_clear=True,
                            target="IMAGE_TEXTURES", use_selected_to_active=False, uv_layer="lightmap")
        a = denoise_image(img, S)
        rgb = a[..., :3].copy()
        peak = rgb.max(axis=2)
        pc = np.percentile(peak[peak > 1e-6], [50, 90, 99, 99.5, 100]) if (peak > 1e-6).any() else [1.0] * 5
        scale = float(pc[3])
        raw[n] = (rgb, scale, S)
        for o in objs:
            m = o.data.materials[0]
            for nd in [nd for nd in m.node_tree.nodes if nd.name.startswith("BAKE_TARGET")]:
                m.node_tree.nodes.remove(nd)
            stats.setdefault(m.name, []).append((o, n))
            o.data.uv_layers.active = o.data.uv_layers["UVMap"]
        report[n] = {"size": S, "px_per_m": round(dens, 1), "scale": round(scale, 5), "p50_p90_p99_p995_max": [round(float(v), 4) for v in pc],
                     "samples": SAMPLES, "device": bpy.context.scene.cycles.device, "seconds": round(time.time() - t0),
                     "materials": sorted({o.data.materials[0].name for o in objs})}
        print("  baked", report[n])
        bpy.data.images.remove(img)
    disp = {}
    for mname, lst in stats.items():
        rows = [displayed_stats(o, raw[n][0], raw[n][1]) for o, n in lst]
        tot = sum(r["area_m2"] for r in rows)
        disp[mname] = {k: sum(r[k] * r["area_m2"] for r in rows) / tot for k in ("p50", "p90", "p99")}
        disp[mname].update({"area_m2": tot, "map": lst[0][1]})
    main = [m for m in disp if m.startswith(MAIN) and m not in NOT_MAIN]
    worst = max(disp[m]["p90"] for m in main)
    worst99 = max(disp[m]["p99"] for m in main)
    k = TARGET_P90 / worst
    capped = bool(CLIP_CAP) and k * worst99 > CLIP_CAP
    if capped:
        k = CLIP_CAP / worst99
    print(f"EXPOSURE k = {k:.4f} (the brightest main surface's p90 {worst:.4f} -> {TARGET_P90}; p99 {worst99:.4f}; "
          f"{'held by the clip cap ' + str(CLIP_CAP) if capped else 'the target binds'})")
    for n, (rgb, scale, S) in raw.items():
        out = np.ones((S, S, 4), np.float32)
        out[..., :3] = srgb_encode(rgb / scale)
        png = bpy.data.images.new(f"LM_{n}_png", S, S, alpha=False)
        png.colorspace_settings.name = "Non-Color"
        png.pixels.foreach_set(out.ravel())
        png.filepath_raw = str(work() / f"{SCENE}_{n}.png")
        png.file_format = "PNG"
        png.save()
        bpy.data.images.remove(png)
        report[n]["lightmap_intensity"] = round(math.pi * scale * k, 4)
        for mname in report[n]["materials"]:
            m = bpy.data.materials[mname]
            m["lightmap"] = LM_URL.format(n)
            m["lightmap_intensity"] = round(math.pi * scale * k, 4)
    for m in disp:
        for q in ("p50", "p90", "p99"):
            disp[m][q] = round(disp[m][q] * k, 4)
        disp[m]["main"] = m in main
        disp[m]["area_m2"] = round(disp[m]["area_m2"], 2)
    for ob in bpy.data.collections["Lights"].objects:      # the lights as the page shows them, so the stills hold the lightmaps' light
        ob.data.energy *= k
    (work() / "lightmaps.json").write_text(json.dumps({"maps": report, "exposure_k": round(k, 5), "target_p90": TARGET_P90, "clip_cap_p99": CLIP_CAP, "cap_binds": capped, "displayed": disp}, indent=1))
    for m, d in sorted(disp.items()):
        print(f"DISPLAYED {m:30s} map {d['map']}  p50 {d['p50']:.3f}  p90 {d['p90']:.3f}  p99 {d['p99']:.3f}  {'main' if d['main'] else ''}")
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


# ================================================================ export
def stage_export():
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    bpy.data.collections["Art"].hide_viewport = True
    bpy.data.collections["Layout"].hide_viewport = True
    bpy.ops.object.select_all(action="DESELECT")
    objs = list(exp.objects)
    parked = []
    for o in objs:
        o.hide_set(False)
        o.hide_render = False
        for k in list(o.keys()):
            del o[k]
        if o.name.endswith("_x"):
            want = o.name[:-2]
            clash = bpy.data.objects.get(want)
            if clash is not None and clash is not o:          # the Art piece of the same name steps aside while the export takes its name
                clash.name = want + "_art"
                parked.append((clash, want))
            o.name = want
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    scrub_private()
    for draco, fn in ((True, f"{SCENE}_raw.glb"), (False, f"{SCENE}_nodraco.glb")):
        path = work() / fn
        bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                                  export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                                  export_cameras=False, export_lights=False, export_animations=False,
                                  export_draco_mesh_compression_enable=draco, export_draco_mesh_compression_level=6,
                                  export_draco_position_quantization=14, export_draco_normal_quantization=10, export_draco_texcoord_quantization=12)
        print("EXPORTED", path.name, path.stat().st_size)
    for o in objs:
        o.name = o.name + "_x"
    for clash, want in parked:
        clash.name = want
    bpy.data.collections["Art"].hide_viewport = False
    bpy.data.collections["Layout"].hide_viewport = False
    exp.hide_viewport = exp.hide_render = True


# ================================================================ the stills
def look_cam(name, loc, target, fov_v=75.0, ortho=None):
    cam = bpy.data.cameras.new(name)
    cam.sensor_fit = "VERTICAL"
    if ortho:
        cam.type = "ORTHO"
        cam.ortho_scale = ortho
        cam.sensor_fit = "HORIZONTAL"
    else:
        cam.lens_unit = "FOV"
        cam.angle_y = math.radians(fov_v)
    cam.clip_start, cam.clip_end = 0.03, 100
    ob = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler() if target is not None else (0, 0, 0)
    return ob


def strip_jpeg_comments(path):
    b = path.read_bytes()
    out, i = bytearray(b[:2]), 2
    while i < len(b) and b[i] == 0xFF and b[i + 1] != 0xDA:
        n = int.from_bytes(b[i + 2:i + 4], "big")
        if b[i + 1] not in (0xFE, 0xE1):                                   # comments (render stats) and APP1 (Blender's tag)
            out += b[i:i + 2 + n]
        i += 2 + n
    out += b[i:]
    path.write_bytes(bytes(out))


def stage_render():
    sc = bpy.context.scene
    STILLS.mkdir(parents=True, exist_ok=True)
    scrub_private()
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Layout"].hide_render = True
    setup_cycles(arg("--render-samples", 128, int))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = "Standard"           # the page draws the bake with no tone mapping: so do the stills
    sc.view_settings.look = "None"
    sc.view_settings.exposure = arg("--exposure", 0.0, float)
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    star = bpy.data.objects["DoorLeaf_Nyx_Star"]
    E = eye()
    door_mid = Vector((APO, DOOR_C.y, DOOR_H * 0.55))
    off = E + Vector((0.2, 0.0, 0.0))
    shots = {
        "1_arrival": (look_cam("arrival", (SPAWN.x, SPAWN.y, EYE), (SPAWN.x, SPAWN.y + 5, EYE + 0.9), 72.0), (1920, 1080), STILLS),
        "2_wide": (look_cam("wide", (-3.2, -3.6, 3.4), (0.8, 2.0, 0.9), 72.0), (1920, 1080), STILLS),
        "3_align": (look_cam("align", E, door_mid, 60.0), (1920, 1080), STILLS),
        "align_off": (look_cam("align_off", off, door_mid + (off - E), 60.0), (1280, 720), work()),
        "align_door": (look_cam("align_door", E, door_mid, 60.0), (1280, 720), work()),
        "plan": (look_cam("plan", (0, 0, 20), None, ortho=2 * RC + 0.6), (1400, 1400), work()),
    }
    hide_plan = [o for o in bpy.data.collections["Art"].objects if o.name.startswith(("Dome", "decor_stars_fixed", "Wall_Upper", "decor_star_", "Gilt", "Niche"))]
    which = arg("--only", "all")
    for key, (cam, (w, h), folder) in shots.items():
        if which != "all" and key not in which.split(","):
            continue
        sc.camera = cam
        star.hide_render = key != "align_door"
        for o in hide_plan:
            o.visible_camera = key != "plan"
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        path = folder / f"{key}.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 400_000 and q > 40:
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        strip_jpeg_comments(path)
        print("STILL", key, path.stat().st_size, "q", q)
    star.hide_render = False
    for o in hide_plan:
        o.visible_camera = True


def stage_views():
    """Textured view sheets of the copies as written (to read which way each faces)."""
    for code, fname, name, budget, px in PIECES:
        clear_scene()
        bpy.ops.import_scene.gltf(filepath=str(copy_path(code, name)))
        ob = next(o for o in bpy.data.objects if o.type == "MESH")
        view_sheet(ob, code)


if __name__ == "__main__":
    ST = STAGE.split(",")                             # one stage, several (bake,export,render), or all
    if "copies" in ST:
        stage_copies()
    if "views" in ST:
        stage_views()
    if "art" in ST or "all" in ST:
        build_all()
        save_blend()
    if "bake" in ST or "all" in ST:
        stage_bake()
    if "export" in ST or "all" in ST:
        stage_export()
    if "render" in ST or "all" in ST:
        stage_render()
