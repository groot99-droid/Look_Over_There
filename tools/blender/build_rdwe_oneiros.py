"""Builds Right Door, Wrong Exit's god room Oneiros, "The Gates of Horn and Ivory" (`rdwe_god_oneiros`), in Blender: the reduced game copies of
the owner's Oneiros furniture set and the two gates, the pearl bedchamber under an opal ribbed vault, the two-gates trick, the night bake, and
world/rdwe_god_oneiros.glb with its lightmaps.

Re-runnable, from the repo root (docs/BLENDER.md, docs/BLENDER_AREAS.md section 7). Built on tools/blender/build_rdwe_selene.py and
tools/blender/build_rdwe_nyx.py, the first god rooms:

    blender -b --factory-startup --python tools/blender/build_rdwe_oneiros.py -- --stage copies --src <folder>   (the 13 originals and 5 props -> reduced copies)
    blender -b --factory-startup --python tools/blender/build_rdwe_oneiros.py -- --stage art                     (the room; saves blender/scenes/rdwe_god_oneiros.blend)
    blender -b --factory-startup blender/scenes/rdwe_god_oneiros.blend --python tools/blender/build_rdwe_oneiros.py -- --stage bake [--samples 512] [--device cpu]
    blender -b --factory-startup blender/scenes/rdwe_god_oneiros.blend --python tools/blender/build_rdwe_oneiros.py -- --stage export
    blender -b --factory-startup blender/scenes/rdwe_god_oneiros.blend --python tools/blender/build_rdwe_oneiros.py -- --stage render [--render-samples 128]
    (--stage bake,export,render runs several in one go; --stage all runs art, bake, export and render; --stage views writes view sheets of the copies)
    then, in plain Python (Pillow): each lightmap PNG -> world/lightmaps/rdwe_god_oneiros_<n>.webp (q90), and
    python tools/webp_glb.py blender/work/farway_rdwe_god_oneiros/rdwe_god_oneiros_raw.glb world/rdwe_god_oneiros.glb 85
    (docs/renders/rdwe_god_oneiros/README.md has the exact steps; the work folder is blender/work/farway_rdwe_god_oneiros, git-ignored)

Stage `copies` reads the originals (never writes them): each piece is imported, a copy of it is welded and decimated (Collapse) to its budget,
given a fresh UV, and the original's base colour is baked onto the copy (Cycles, selected to active, emission, so bronze, pearl and horn keep
their colour). The copies go to blender/models/rdwe_oneiros/ with a ledger. The exporter's objects (COL_, DoorLeaf_, Marker_, Link_, Arrive_,
Zone_, Spot_) are kept in the `Layout` collection for tools/blender/export_scene.py, which is not on main yet, so no world/rdwe_god_oneiros.json
is written here.

Axes: Blender metres, x east, y north, z up, the room's centre at the origin, the floor at z = 0. The glTF exporter's +Y up turns Blender
(x, y, z) into game (x, z, -y), so game north is -z, as everywhere in Farway. The furniture hangs under the node `grp_furniture` (at the origin,
identity) so the scene code can mirror it about x = 0 for the ivory gate's first wrong room.
"""
import csv
import json
import math
import os
import sys
import time
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[2]
SCENE = "rdwe_god_oneiros"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
COPIES = ROOT / "blender/models/rdwe_oneiros"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"
MARGIN_PX = 8
PFX = "Oneiros_"                           # the furniture's and the props' materials

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 512, int)
DEVICE = arg("--device", "auto")
SRC = Path(arg("--src", str(ROOT / "blender/work/oneiros_source")))
ONLY = arg("--only", "all")


def work():
    d = Path(arg("--work", str(ROOT / f"blender/work/farway_{SCENE}")))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- the pieces (manifest: Oneiros_collection_manifest.csv; budgets: Nyx's ledger)
# code, original file, short name, triangle budget, base colour size (px)
PIECES = [
    ("ON-00", "ON-00_Oneiros_Lamp.glb", "lamp", 15000, 1024),
    ("ON-01", "ON-01_Oneiros_Bedside_Table.glb", "bedside_table", 15000, 1024),
    ("ON-02", "ON-02_Oneiros_Armchair.glb", "armchair", 18000, 1024),
    ("ON-03", "ON-03_Oneiros_Dresser.glb", "dresser", 18000, 1024),
    ("ON-04", "ON-04_Oneiros_Tall_Cabinet.glb", "tall_cabinet", 18000, 1024),
    ("ON-05", "ON-05_Oneiros_Bed.glb", "bed", 24000, 2048),
    ("ON-06", "ON-06_Oneiros_Wall_Mirror.glb", "wall_mirror", 15000, 1024),
    ("ON-07", "ON-07_Oneiros_Writing_Desk.glb", "writing_desk", 18000, 1024),
    ("ON-08", "ON-08_Oneiros_Clock.glb", "clock", 15000, 512),
    ("ON-09", "ON-09_Oneiros_Hourglass.glb", "hourglass", 15000, 512),
    ("ON-10", "ON-10_Oneiros_Vase.glb", "seed_pod_vase", 15000, 512),
    ("ON-11", "ON-11_Oneiros_Rug.glb", "runner", 2000, 1024),          # a flat 12 mm slab: 2k triangles hold its edge; the texture is the rug
    ("ON-12", "ON-12_Oneiros_Textiles.glb", "textiles", 15000, 1024),
    # the Higgsfield props PLAN section 7 gives Oneiros (normalised to 1.9 m by the generator; `size` is the plan's W x H x D in metres)
    ("P1", "P1.glb", "gate_horn", 12000, 1024),
    ("P1L", "P1L.glb", "gate_horn_leaf", 4000, 1024),
    ("P2", "P2.glb", "gate_ivory", 12000, 1024),
    ("P2L", "P2L.glb", "gate_ivory_leaf", 4000, 1024),
    ("P15", "P15.glb", "brazier", 9000, 1024),
]
# both gates at one height (3.3 m) so they read as a pair; the leaves at 2.4 m here and fitted to their gate's opening in the art stage
PROP_SIZE = {"P1": (2.4, 3.3, 0.5), "P2": (2.4, 3.3, 0.5), "P1L": (0.8, 2.4, 0.08), "P2L": (0.8, 2.4, 0.08), "P15": (0.7, 1.1, 0.7)}
FIT_WIDTH = set()


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
    itself, whatever the metal and the roughness say (a diffuse-colour bake would give black on the bronze)."""
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
    """Five small orthographic views of the copy, from +X, -X, +Y, -Y (Blender) and the top, to read which way the piece faces."""
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
        cam.rotation_euler = (-Vector(d)).to_track_quat("-Z", "Y").to_euler()
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
    # scale: the props come normalised to 1.9 m; the furniture is at its manifest size already
    s = Vector((1, 1, 1))
    if code in PROP_SIZE:
        w, h, d = PROP_SIZE[code]
        dx, dy, dz = cp.dimensions
        k = w / dx if code in FIT_WIDTH else h / dz
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
    me.uv_layers.new(name="UVMap")
    select_only([cp])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.002, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=3.0 / px, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    # the bake target
    img = bpy.data.images.new(f"{code}_{name}_base", px, px, alpha=False)
    mat = bpy.data.materials.new(f"{PFX}{code}_{name}")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    bsdf.inputs["Roughness"].default_value = 0.7
    bsdf.inputs["Metallic"].default_value = 0.0
    mat.use_backface_culling = code not in ("P1", "P2", "P1L", "P2L")     # the gates' thin vines and leaves: both sides
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
    view_sheet(cp, code)
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
LAYOUT_PROPS = {"kind", "to_scene", "to_arrive", "hinge", "swing_deg", "state", "note"}     # the exporter's properties on the Layout objects (no paths)


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


# ================================================================ the room (PLAN section 4.5)
HALF_W = 5.0                               # x -5 .. 5
HALF_L = 4.5                               # y -4.5 .. 4.5
WALL_H = 3.8
VAULT_TOP = 5.5
RISE = VAULT_TOP - WALL_H
EYE = 0.95                                 # the RDWE walker's eye at RDWE_SCALE 1.7 (controls.js: 1.62 / 1.7)
SPAWN = Vector((0.0, -3.9, 0.0))
DOOR_W, DOOR_H = 0.94, 2.16
SKIRT_Z, DADO_Z, FRIEZE_Z, CORNICE_Z = 0.15, 0.95, 3.38, 3.68
PASS_D = 1.5                               # the passages behind the gates
LEAF_OPEN = 72.0                           # degrees: the gates' leaves stand open into the room
IVORY_X, HORN_X = -2.3, 2.45               # the gates' centres on the north wall (the plan's +-2.2, moved so the wider horn gate clears the cabinet)
COMPASS = {"E": 0, "N": 90, "W": 180, "S": 270}
WALLS = {"S": ((0, -1), HALF_L), "N": ((0, 1), HALF_L), "W": ((-1, 0), HALF_W), "E": ((1, 0), HALF_W)}
GATES = {}                                 # measured in the art stage: name -> dict(cx, a, spring, rise, y_mid, y_front, ...)

# which way each copy faces as made (read from view sheets of the copies): the compass angle its front points to in Blender.
# The set's multi-view pieces face +X; the props face -Y
NATIVE_FRONT = {c: 0 for c in ("ON-00", "ON-01", "ON-02", "ON-03", "ON-04", "ON-05", "ON-06", "ON-07", "ON-08", "ON-09", "ON-10", "ON-11", "ON-12")}
NATIVE_FRONT.update({"P1": 270, "P1L": 270, "P2": 270, "P2L": 270, "P15": 270})
RUNNER_YAW = 90 - math.degrees(math.atan2(HORN_X - 0.6, 4.0 + 2.4))     # the runner's long axis points at the horn gate (about 16 degrees east of north)

# placement (PLAN 4.5): code, object name, (x, y), facing (compass letter or degrees), how:
# ("floor"), ("wall", wall, gap), ("hang", wall, gap, z), ("on", support, (dx, dy))
PLACE = [
    ("ON-11", "ON-11_runner", (0.6, -2.4), RUNNER_YAW, ("floor",)),
    ("ON-05", "ON-05_bed", (-3.87, -0.4), "E", ("wall", "W", 0.04)),
    ("ON-01", "ON-01_bedside_table_N", (-4.8, 0.75), "E", ("wall", "W", 0.04)),
    ("ON-01", "ON-01_bedside_table_S", (-4.8, -1.55), "E", ("wall", "W", 0.04)),
    ("ON-03", "ON-03_dresser", (4.7, -0.8), "W", ("wall", "E", 0.03)),
    ("ON-06", "ON-06_wall_mirror", (4.9, -0.8), "W", ("hang", "E", 0.02, 1.08)),
    ("ON-04", "ON-04_tall_cabinet", (4.6, 3.55), "W", ("wall", "E", 0.04)),
    ("ON-07", "ON-07_writing_desk", (4.65, -3.2), "W", ("wall", "E", 0.03)),
    ("ON-02", "ON-02_armchair", (3.75, -3.2), "E", ("floor",)),
    ("P2", "P2_gate_ivory", (IVORY_X, 4.0), "S", ("wall", "N", 0.0)),
    ("P1", "P1_gate_horn", (HORN_X, 4.0), "S", ("wall", "N", 0.0)),
    ("P15", "P15_brazier", (0.0, 3.0), "S", ("floor",)),
    # the smalls, on the furniture
    ("ON-00", "ON-00_lamp", (0.0, 0.0), "E", ("on", "ON-01_bedside_table_N")),
    ("ON-10", "ON-10_seed_pod_vase", (0.0, 0.0), "E", ("on", "ON-01_bedside_table_S")),
    ("ON-08", "decor_clock", (0.0, 0.28), "W", ("on", "ON-03_dresser")),
    ("ON-09", "ON-09_hourglass", (0.0, 0.32), "W", ("on", "ON-07_writing_desk")),
    ("ON-12", "ON-12_textiles", (0.55, -0.3), "E", ("on", "ON-05_bed")),
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
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
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


def dot(img, p, col, r):
    lo_r, hi_r = int(max(0, p[0] - r - 2)), int(min(img.shape[0], p[0] + r + 3))
    lo_c, hi_c = int(max(0, p[1] - r - 2)), int(min(img.shape[1], p[1] + r + 3))
    yy, xx = np.mgrid[lo_r:hi_r, lo_c:hi_c].astype(np.float32)
    a = np.clip(r + 0.5 - np.hypot(yy - p[0], xx - p[1]), 0, 1)[..., None]
    img[lo_r:hi_r, lo_c:hi_c] = img[lo_r:hi_r, lo_c:hi_c] * (1 - a) + np.array(col) * a


BRONZE_S = (0.62, 0.48, 0.26)     # sRGB bronze for the painted lines
COPPER_S = (0.70, 0.40, 0.25)     # terracotta copper
IVORY_S = (0.93, 0.89, 0.79)


def norm01(a):
    return (a - a.min()) / max(1e-9, a.max() - a.min())


def noise(S, seed, r, passes=2):
    rng = np.random.default_rng(seed)
    return norm01(wrap_blur(rng.random((S, S)).astype(np.float32), r, passes))


def iridescence(S, seed, amp, scale=40):
    """A seamless pastel shimmer: a slow hue field turned into a small tint that cycles pink, green, blue."""
    h = noise(S, seed, scale) * 2.2 + noise(S, seed + 1, scale // 3) * 0.5
    ph = np.stack([np.cos(2 * math.pi * (h + k / 3.0)) for k in range(3)], axis=-1)
    return amp * ph.astype(np.float32)


def floor_pixels():
    """The floor tile (FLOOR_TILE metres): warm cream marble with tan veins, a fine joint, and a terracotta-copper roundel with an ivory ring
    where four tiles meet (PLAN: terracotta-copper floor medallions). Seamless."""
    S = 1024
    n1 = noise(S, 41, 30)
    n2 = noise(S, 42, 7)
    f = n1 * 7.0 + n2 * 1.4
    vein = np.clip(1 - np.abs((f % 1.0) - 0.5) / 0.02, 0, 1) * (n2 > 0.45)
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.86, 0.80, 0.70)
    img *= (0.93 + 0.1 * n1)[..., None]
    img = img * (1 - 0.4 * vein[..., None]) + np.array([0.66, 0.56, 0.44]) * 0.4 * vein[..., None]
    u, v = np.meshgrid((np.arange(S) + 0.5) / S, (np.arange(S) + 0.5) / S)
    du, dv = np.minimum(u, 1 - u), np.minimum(v, 1 - v)
    joint = (du < 0.0025) | (dv < 0.0025)
    img[joint] *= 0.70
    d = np.hypot(du, dv)                                  # distance to the nearest tile corner
    th = np.arctan2(dv, du)
    img[d < 0.105] = BRONZE_S
    img[d < 0.098] = IVORY_S
    scallop = 0.084 + 0.006 * np.abs(np.cos(8 * th))
    img[d < scallop] = BRONZE_S
    img[d < scallop - 0.004] = COPPER_S
    img[(d < 0.03)] = BRONZE_S
    return np.clip(img, 0, 1).astype(np.float32)


def verdigris_pixels():
    """Dark green marble (the furniture's plinths): green with pale veins, lifted so the page's unlit draw is not black. Seamless tile."""
    S = 512
    n1 = noise(S, 13, 14)
    n2 = noise(S, 14, 4)
    f = n1 * 5.0 + n2 * 1.2
    vein = np.clip(1 - np.abs((f % 1.0) - 0.5) / 0.03, 0, 1)
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.26, 0.42, 0.36)
    img *= (0.85 + 0.3 * n1)[..., None]
    img = img * (1 - 0.5 * vein[..., None]) + np.array([0.62, 0.74, 0.66]) * 0.5 * vein[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def pearl_pixels():
    """The walls: pearl white with an iridescent sheen (soft pink, green and blue clouds) and a faint silk grain. Seamless tile."""
    S = 512
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.89, 0.87, 0.86)
    img += iridescence(S, 9, 0.018, 70)
    grain = wrap_blur(np.random.default_rng(10).random((S, S)).astype(np.float32), 1, 1)
    img *= (0.97 + 0.05 * grain)[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def ivory_pixels():
    """Ivory for the dado, the mouldings, the pilasters, the casings: warm cream with a faint lengthwise grain. Seamless tile."""
    S = 512
    rng = np.random.default_rng(5)
    g = wrap_blur(rng.random((S, S)).astype(np.float32), 1, 1)
    streak = norm01(wrap_blur(rng.random((S, S)).astype(np.float32), 3, 2))
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.93, 0.88, 0.77)
    img *= (0.95 + 0.06 * streak + 0.03 * g)[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def scallop_field(u, v, n_u, row_h):
    """Rows of scallop shells (fish scales): the distance to each cell's shell centre and the angle, for a shell pattern."""
    cu = u * n_u
    rv = v / row_h
    row = np.floor(rv)
    cu = cu + 0.5 * (row % 2)
    fu = cu - np.floor(cu) - 0.5
    fv = rv - row
    return np.hypot(fu, fv * row_h * n_u), np.arctan2(fv, fu)


def opal_pixels():
    """The vault: opal, pearl with a stronger shimmer, and faint ivory scale lines (the furniture's scallops). Seamless tile."""
    S = 1024
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.84, 0.85, 0.91)
    img += iridescence(S, 21, 0.03, 110)
    u, v = np.meshgrid((np.arange(S) + 0.5) / S, (np.arange(S) + 0.5) / S)
    d, th = scallop_field(u, v, 8, 1 / 8)
    line = np.abs(d - 0.5) < 0.012
    img[line] = img[line] * 0.85 + np.array(IVORY_S) * 0.15 - 0.03
    fl = np.random.default_rng(22).random((S, S)) > 0.997
    img[fl] += 0.08
    return np.clip(wrap_blur(img, 1, 1), 0, 1).astype(np.float32)


def frieze_pixels():
    """The frieze under the cornice (one tile = FRIEZE_TILE metres of wall, the band's height): an ivory scallop shell on pearl, ribbed,
    with a bronze line along the foot."""
    W, H = 512, 256
    img = np.zeros((H, W, 3), np.float32)
    img[:] = (0.86, 0.84, 0.86)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2, H * 0.86
    r = np.hypot((xx - cx) / W, (yy - cy) / W)
    th = np.arctan2(cy - yy, xx - cx)
    shell = (r < 0.40) & (yy < cy)
    rib = 0.80 + 0.2 * np.abs(np.cos(9 * th)) ** 0.6
    img[shell] = (np.array(IVORY_S)[None, :] * rib[shell][:, None])
    edge = (np.abs(r - 0.40) < 0.008) & (yy < cy)
    img[edge] = BRONZE_S
    img[int(H * 0.86):int(H * 0.9)] = BRONZE_S
    img[int(H * 0.9):] = IVORY_S
    img[:int(H * 0.05)] = BRONZE_S
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def medallion_pixels():
    """The great floor medallion before the gates: an eight-petal opal flower on terracotta copper, an ivory scallop ring, bronze bands."""
    S = 1024
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    r = np.hypot(yy - S / 2, xx - S / 2) / (S / 2)
    th = np.arctan2(yy - S / 2, xx - S / 2)
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.86, 0.80, 0.70)
    img[r < 1.0] = BRONZE_S
    img[r < 0.97] = IVORY_S
    sc = 0.86 + 0.035 * np.abs(np.cos(16 * th))
    img[r < sc] = BRONZE_S
    img[r < sc - 0.015] = COPPER_S
    img[r < 0.52] = BRONZE_S
    img[r < 0.50] = (0.60, 0.33, 0.21)
    petal = r < 0.46 * (0.55 + 0.45 * np.abs(np.cos(4 * th)) ** 1.5)
    ir = iridescence(S, 31, 0.06, 50)
    img[petal] = (np.array([0.92, 0.90, 0.93]) + ir[petal])
    img[r < 0.08] = BRONZE_S
    rings = (np.abs(r - 0.68) < 0.006) | (np.abs(r - 0.78) < 0.006)
    img[rings] = BRONZE_S
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def placard_pixels():
    """The museum placard by the entrance (PLAN 2.2): dark letters on ivory, a bronze rule."""
    W, H = 768, 512
    img = np.zeros((H, W, 3), np.float32)
    img[:] = (0.90, 0.87, 0.80)
    img[18:24, 30:W - 30] = img[H - 24:H - 18, 30:W - 30] = BRONZE_S
    draw_text(img, "ONEIROS", (40, 170, 0, W), (0.10, 0.10, 0.12), 0.85)
    draw_text(img, "DREAMS - THE GATES OF HORN AND IVORY", (190, 270, 0, W), (0.50, 0.30, 0.16), 0.94)
    draw_text(img, "NINETY-NINE NOCTURNE SUITE", (290, 370, 0, W), (0.16, 0.18, 0.20), 0.92)
    draw_text(img, "XIII PIECES. OPAL. BRONZE. HORN.", (380, 460, 0, W), (0.30, 0.30, 0.32), 0.92)
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def glow_pixels(ivory):
    """The light at the end of each passage. Ivory: a bright pearl haze swirling pink and green. Horn: a dim amber dusk."""
    S = 512
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    r = np.hypot(yy - S * 0.55, (xx - S / 2) * 1.3) / (S / 2)
    if ivory:
        img = np.zeros((S, S, 3), np.float32)
        img[:] = (1.0, 0.97, 0.95)
        img += iridescence(S, 51, 0.10, 30)
        img *= np.clip(1.15 - 0.45 * r, 0.55, 1.1)[..., None]
    else:
        img = np.zeros((S, S, 3), np.float32)
        img[:] = (0.62, 0.42, 0.22)
        n = noise(S, 52, 24)
        img *= (0.7 + 0.4 * n)[..., None] * np.clip(1.0 - 0.5 * r, 0.3, 1.0)[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def smoke_pixels():
    """One card of the brazier's opal smoke: a soft wisp, pastel and shifting, transparent at its edges (RGBA)."""
    W, H = 256, 512
    v, u = np.mgrid[0:H, 0:W].astype(np.float32)
    v = 1 - v / H
    u = u / W
    cx = 0.5 + 0.13 * np.sin(v * 2 * math.pi * 1.3 + 0.7) + 0.05 * np.sin(v * 2 * math.pi * 3.1)
    width = 0.07 + 0.16 * v
    a = np.exp(-((u - cx) / width) ** 2) * np.clip(v / 0.12, 0, 1) * np.clip((1 - v) / 0.45, 0, 1)
    rng = np.random.default_rng(61)
    n = norm01(blur(rng.random((H, W)).astype(np.float32), 6, 2))
    a *= 0.55 + 0.6 * n
    rgba = np.zeros((H, W, 4), np.float32)
    hue = v * 1.6 + 0.4 * n
    for k in range(3):
        rgba[..., k] = 0.86 + 0.12 * np.cos(2 * math.pi * (hue + k / 3.0))
    rgba[..., 3] = np.clip(a * 0.75, 0, 1)
    return rgba


FLOOR_TILE = 1.5
MARBLE_TILE = 1.0
PEARL_TILE = 1.6
OPAL_TILE = 2.5
FRIEZE_TILE = 0.6


def mk_image(name, arr, srgb=True):
    h, w = arr.shape[:2]
    alpha = arr.shape[2] == 4
    im = bpy.data.images.new(name + "_gen", w, h, alpha=alpha)
    im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :arr.shape[2]] = arr
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


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, img=None, emit=None, double=False, alpha=None, emit_img=None, alpha_img=None):
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
    if emit_img is not None:
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "UVMap"
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = emit_img[0]
        n.name = "EMIT_IMG"
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        nt.links.new(n.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emit_img[1]
        bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
    if alpha_img is not None:                    # base colour, alpha and emission from one RGBA image
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "UVMap"
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = alpha_img[0]
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
        nt.links.new(n.outputs["Alpha"], bsdf.inputs["Alpha"])
        nt.links.new(n.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = alpha_img[1]
    if alpha is not None or alpha_img is not None:
        if alpha is not None:
            bsdf.inputs["Alpha"].default_value = alpha
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except Exception:
                pass
    m.use_backface_culling = not double
    MATS[name] = m
    return m


def make_materials(gen):
    material("Floor_Stone", img=gen["floor"], rough=0.25)
    material("Verdigris_Marble", img=gen["verdigris"], rough=0.3)
    material("Wall_Pearl", img=gen["pearl"], rough=0.5)
    material("Ivory", img=gen["ivory"], rough=0.45)
    material("Scallop_Frieze", img=gen["frieze"], rough=0.45)
    material("Vault_Opal", img=gen["opal"], rough=0.45)
    material("Medallion", img=gen["medallion"], rough=0.3)
    material("Bronze", color=(0.52, 0.40, 0.22), rough=0.4, metal=0.85)              # drawn unlit on the page: kept light enough to read
    material("Copper", color=(0.62, 0.32, 0.18), rough=0.45, metal=0.8)
    material("Vine_Verdigris", color=(0.30, 0.44, 0.32), rough=0.5, metal=0.5)
    material("Vine_Leaf", color=(0.36, 0.48, 0.30), rough=0.5, metal=0.4, double=True)
    material("Door_Ivory", color=(0.82, 0.77, 0.66), rough=0.5)
    material("Reveal_Dark", color=(0.02, 0.02, 0.025), rough=0.9)
    material("Placard", img=gen["placard"], rough=0.5)
    material("Passage_Ivory", img=gen["pearl"], rough=0.5)
    material("Passage_Horn", color=(0.34, 0.22, 0.12), rough=0.6)
    material("Glow_Ivory", emit_img=(gen["glow_ivory"], 2.5))           # the light beyond the ivory gate: bright, beautiful
    material("Glow_Horn", emit_img=(gen["glow_horn"], 0.8))             # and beyond the horn gate: dull
    material("Picture_Light_Emit", color=(1.0, 0.9, 0.7), emit=((1.0, 0.85, 0.6), 4.0))     # the placard light's strip: seen, but it lights nothing
    material("Sconce_Bronze", color=(0.55, 0.42, 0.22), rough=0.4, metal=0.9, double=True)              # not baked: inches from its own bulb
    material("Lamp_Emit", color=(1.0, 0.94, 0.90), emit=((1.0, 0.86, 0.72), 5.0))           # the sconces' opal buds
    material("Lamp_Bulb_Emit", color=(1.0, 0.92, 0.85), emit=((1.0, 0.84, 0.66), 5.0))      # the bud of the lamp ON-00 (moves with the furniture)
    material("Smoke_Opal", alpha_img=(gen["smoke"], 0.9), double=True)
    material("Brazier_Glow", color=(0.9, 0.88, 1.0), emit=((0.92, 0.86, 1.0), 2.5))
    material("Mirror_View", emit_img=(gen["mirror_wait"], 0.9))         # the wall mirror's picture of the room (rendered after the bake)
    material("Sand_Glow", color=(0.90, 0.76, 0.46), emit=((0.95, 0.80, 0.50), 1.2))


# ---------------------------------------------------------------- geometry helpers (Blender coordinates)
ART = LAYOUT = None


def wall_frame(name):
    """A wall's outward normal n, its tangent t (u runs along t: S +x, N -x, E +y, W -y), its distance from the centre, its length."""
    (nx, ny), dist = WALLS[name]
    n = Vector((nx, ny, 0.0))
    t = Vector((-n.y, n.x, 0.0))
    L = 2 * (HALF_W if name in ("N", "S") else HALF_L)
    return n, t, dist, L


def wall_pt(name, u, z, inset=0.0):
    n, t, dist, L = wall_frame(name)
    return n * (dist - inset) + t * u + Vector((0, 0, z))


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


def face_toward(f, d):
    """Flip f so its normal points along d."""
    f.normal_update()
    if f.normal.dot(d) < 0:
        f.normal_flip()


def poly(bm, pts, toward, tri=True):
    f = bm.faces.new([bm.verts.new(p) for p in pts])
    face_toward(f, toward)
    if tri and len(pts) > 4:
        bmesh.ops.triangulate(bm, faces=[f], quad_method="BEAUTY", ngon_method="EAR_CLIP")
    return f


def arch_pts(uc, a, spring, rise, n=16):
    """An elliptic arch from its left foot to its right foot (u, z)."""
    return [(uc - a * math.cos(math.pi * i / n), spring + rise * math.sin(math.pi * i / n)) for i in range(n + 1)]


def tube(bm, pts, r, sides=4):
    """A thin tube along a polyline (the vines): rings of `sides` vertices, joined by quads."""
    rings = []
    for i, p in enumerate(pts):
        t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
        ref = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
        n1 = t.cross(ref).normalized()
        n2 = t.cross(n1).normalized()
        rings.append([bm.verts.new(p + (n1 * math.cos(2 * math.pi * k / sides) + n2 * math.sin(2 * math.pi * k / sides)) * r) for k in range(sides)])
    for a, b in zip(rings[:-1], rings[1:]):
        for k in range(sides):
            f = bm.faces.new([a[k], a[(k + 1) % sides], b[(k + 1) % sides], b[k]])
            c = f.calc_center_median()
            face_toward(f, c - (a[k].co + a[(k + 2) % sides].co) / 2)


def leaf(bm, base, out, along, size=0.11):
    """A bronze vine leaf: a pointed quad from `base` outward."""
    up = Vector((0, 0, 1))
    tip = base + out * size + up * size * 0.3
    mid = base + out * size * 0.5 + up * size * 0.12
    s = along.normalized() * size * 0.32
    bm.faces.new([bm.verts.new(base), bm.verts.new(mid + s), bm.verts.new(tip), bm.verts.new(mid - s)])


def openings(name):
    """The openings per wall: (u0, u1, spring, rise). The north wall's are the two gates' arches (measured in place_gates)."""
    if name == "S":
        return [(-DOOR_W / 2, DOOR_W / 2, DOOR_H, 0.0)]
    if name == "N":
        return [(-g["cx"] - g["aw"], -g["cx"] + g["aw"], g["spring"], g["rise_w"]) for g in GATES.values()]
    return []


def wall_band(bm, name, z0, z1, inset=0.0):
    """The wall's inner face between heights z0 and z1, `inset` metres into the room, with its openings left out (all start at the floor)."""
    n, t, dist, L = wall_frame(name)
    ops = [o for o in openings(name) if z0 < o[2] + o[3]]
    spans, u = [], -L / 2
    for a, b in sorted((o[0], o[1]) for o in ops):
        spans.append((u, a))
        u = b
    spans.append((u, L / 2))
    for a, b in spans:
        if b - a > 1e-6:
            poly(bm, [wall_pt(name, a, z0, inset), wall_pt(name, b, z0, inset), wall_pt(name, b, z1, inset), wall_pt(name, a, z1, inset)], -n)
    for (u0, u1, spring, rise) in ops:
        if spring >= z1:
            continue                                   # the opening fills this band's span
        if rise == 0.0:
            poly(bm, [wall_pt(name, u0, spring, inset), wall_pt(name, u1, spring, inset), wall_pt(name, u1, z1, inset), wall_pt(name, u0, z1, inset)], -n)
            continue
        assert spring + rise < z1 and spring > z0, "an arched opening's head must sit inside one band"
        pts = [wall_pt(name, uu, zz, inset) for uu, zz in arch_pts((u0 + u1) / 2, (u1 - u0) / 2, spring, rise, 20)]
        pts += [wall_pt(name, u1, z1, inset), wall_pt(name, u0, z1, inset)]
        poly(bm, pts, -n)


def wall_strip(bm, name, z0, z1, depth):
    """A moulding along one wall, its face `depth` proud, with top and bottom faces; broken at the openings it crosses."""
    n, t, dist, L = wall_frame(name)
    cuts = sorted((o[0] - 0.02, o[1] + 0.02) for o in openings(name) if o[2] + o[3] > z0)
    spans, u = [], -L / 2
    for a, b in cuts:
        spans.append((u, a))
        u = b
    spans.append((u, L / 2))
    for a, b in spans:
        if b - a < 1e-6:
            continue
        poly(bm, [wall_pt(name, a, z0, depth), wall_pt(name, b, z0, depth), wall_pt(name, b, z1, depth), wall_pt(name, a, z1, depth)], -n)
        poly(bm, [wall_pt(name, a, z1, 0), wall_pt(name, b, z1, 0), wall_pt(name, b, z1, depth), wall_pt(name, a, z1, depth)], Vector((0, 0, 1)))
        poly(bm, [wall_pt(name, a, z0, 0), wall_pt(name, b, z0, 0), wall_pt(name, b, z0, depth), wall_pt(name, a, z0, depth)], Vector((0, 0, -1)))


# ---------------------------------------------------------------- the vault: a cloister vault (z rises from the four walls to a crown) with ribs
def vault_z(m):
    """Height of the vault on the ring m (0 at the crown, 1 at the walls): an elliptic section, upright where it meets the walls."""
    return WALL_H + RISE * math.sqrt(max(0.0, 1 - m * m))


def ring_pt(m, s):
    """The point at perimeter parameter s (0..4, starting at the south-west corner, counter-clockwise) on the vault's ring m."""
    s = s % 4.0
    side, f = int(s), s - int(s)
    a, b = HALF_W * m, HALF_L * m
    x, y = [(-a + 2 * a * f, -b), (a, -b + 2 * b * f), (a - 2 * a * f, b), (-a, b - 2 * b * f)][side]
    return Vector((x, y, vault_z(m)))


def build_vault():
    K, nside = 18, 12
    ms = [math.sin(math.pi / 2 * k / K) for k in range(K + 1)]          # dense near the walls, where the section curves fast
    bm = bmesh.new()
    rings = [[bm.verts.new(ring_pt(m, i / nside)) for i in range(4 * nside)] for m in ms[1:]]
    crown = bm.verts.new((0, 0, VAULT_TOP))
    nr = len(rings[0])
    for i in range(nr):
        f = bm.faces.new([crown, rings[0][i], rings[0][(i + 1) % nr]])
        face_toward(f, Vector((0, 0, -1)))
    for a, b in zip(rings[:-1], rings[1:]):
        for i in range(nr):
            f = bm.faces.new([a[i], b[i], b[(i + 1) % nr], a[(i + 1) % nr]])
            c = f.calc_center_median()
            face_toward(f, Vector((-c.x, -c.y, WALL_H - c.z)))
    box_uv(bm, OPAL_TILE)
    mesh_obj("Vault", bm, "Vault_Opal", smooth=True)
    # the ribs: bronze bands under the vault from each corner and each wall's middle to the crown
    bm = bmesh.new()
    for s0 in (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5):
        prev = None
        for k in range(K + 1):
            m = max(0.02, ms[K - k])
            p = ring_pt(m, s0)
            g = Vector((p.x / HALF_W ** 2, p.y / HALF_L ** 2, (p.z - WALL_H) / RISE ** 2))
            inward = -g.normalized()
            tang = (ring_pt(max(0.0, m - 0.02), s0) - p)
            side = inward.cross(tang).normalized() if tang.length > 1e-6 else Vector((1, 0, 0))
            w = 0.11
            ring = [p - side * w, p - side * w + inward * 0.08, p + side * w + inward * 0.08, p + side * w]
            cur = [bm.verts.new(q) for q in ring]
            if prev:
                for j, toward in ((0, -side), (1, inward), (2, side)):
                    f = bm.faces.new([prev[j], cur[j], cur[j + 1], prev[j + 1]])
                    face_toward(f, toward)
            prev = cur
    box_uv(bm, 1.0)
    mesh_obj("Vault_Ribs", bm, "Bronze")
    # the crown boss: a terracotta-copper dome hanging under the crown, in a bronze ring
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=0.34, matrix=Matrix.Translation((0, 0, VAULT_TOP - 0.05)))
    drop = [v for v in bm.verts if v.co.z > VAULT_TOP - 0.04]
    bmesh.ops.delete(bm, geom=drop, context="VERTS")
    box_uv(bm, 1.0)
    mesh_obj("Vault_Boss", bm, "Copper", smooth=True)
    bm = bmesh.new()
    add_cyl(bm, (0, 0, VAULT_TOP - 0.13), (0, 0, VAULT_TOP - 0.02), 0.45, 0.45, seg=24)
    box_uv(bm, 1.0)
    mesh_obj("Vault_Boss_Ring", bm, "Bronze", smooth=True)


def build_shell():
    # the floor: one rectangle under the cream marble tile with its roundels
    bm = bmesh.new()
    poly(bm, [Vector((-HALF_W, -HALF_L, 0)), Vector((HALF_W, -HALF_L, 0)), Vector((HALF_W, HALF_L, 0)), Vector((-HALF_W, HALF_L, 0))], Vector((0, 0, 1)))
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for lp in f.loops:
            lp[uvl].uv = ((lp.vert.co.x + 0.75) / FLOOR_TILE, (lp.vert.co.y + 0.75) / FLOOR_TILE)
    mesh_obj("Floor", bm, "Floor_Stone")
    # a verdigris marble border round the floor, 0.3 m wide, a hair above it
    bm = bmesh.new()
    w = 0.3
    for x0, y0, x1, y1 in ((-HALF_W, -HALF_L, HALF_W, -HALF_L + w), (-HALF_W, HALF_L - w, HALF_W, HALF_L),
                           (-HALF_W, -HALF_L + w, -HALF_W + w, HALF_L - w), (HALF_W - w, -HALF_L + w, HALF_W, HALF_L - w)):
        poly(bm, [Vector((x0, y0, 0.002)), Vector((x1, y0, 0.002)), Vector((x1, y1, 0.002)), Vector((x0, y1, 0.002))], Vector((0, 0, 1)))
    box_uv(bm, 1.0)
    mesh_obj("Floor_Border", bm, "Verdigris_Marble")
    # the walls: verdigris skirting, an ivory dado, pearl up to the frieze, the scallop frieze, the ivory cornice
    for mat, z0, z1, tile in (("Verdigris_Marble", 0.0, SKIRT_Z, 1.0), ("Ivory", SKIRT_Z, DADO_Z, MARBLE_TILE), ("Wall_Pearl", DADO_Z, FRIEZE_Z, PEARL_TILE)):
        bm = bmesh.new()
        for name in WALLS:
            wall_band(bm, name, z0, z1)
        box_uv(bm, tile)
        mesh_obj(f"Wall_{mat}", bm, mat)
    bm = bmesh.new()
    for name in WALLS:
        wall_band(bm, name, FRIEZE_Z, CORNICE_Z, 0.0)
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        n = f.normal
        h = Vector((-n.y, n.x, 0)).normalized()
        for lp in f.loops:
            p = lp.vert.co
            lp[uvl].uv = (p.dot(h) / FRIEZE_TILE, (p.z - FRIEZE_Z) / (CORNICE_Z - FRIEZE_Z))
    mesh_obj("Wall_Frieze", bm, "Scallop_Frieze")
    bm = bmesh.new()
    for name in WALLS:
        wall_band(bm, name, CORNICE_Z, WALL_H, 0.0)
        wall_strip(bm, name, CORNICE_Z, WALL_H, 0.09)
        wall_strip(bm, name, DADO_Z - 0.04, DADO_Z + 0.01, 0.03)
    box_uv(bm, MARBLE_TILE)
    mesh_obj("Mouldings_Ivory", bm, "Ivory")
    bm = bmesh.new()
    for name in WALLS:
        wall_strip(bm, name, FRIEZE_Z - 0.03, FRIEZE_Z, 0.05)
        wall_strip(bm, name, DADO_Z + 0.01, DADO_Z + 0.035, 0.025)
    box_uv(bm, 1.0)
    mesh_obj("Mouldings_Bronze", bm, "Bronze")
    build_vault()


def build_pilasters():
    """Ivory pilasters in the four corners and at the middle of the north wall, between the gates, each wound with two twisting verdigris
    bronze vines with leaves, up to a bronze capital where the vault's ribs spring (PLAN: bronze vine pilasters twisting up to the ribs).
    Bronze corbels with a copper seed pod carry the ribs at the middle of the other three walls."""
    ivory, bronze, granite, vines, leaves, copper = (bmesh.new() for _ in range(6))
    posts = [(Vector((sx * (HALF_W - 0.13), sy * (HALF_L - 0.13), 0)), (0.36, 0.36), Vector((-sx, -sy, 0)).normalized()) for sx in (-1, 1) for sy in (-1, 1)]
    posts.append((Vector((0, HALF_L - 0.09, 0)), (0.36, 0.18), Vector((0, -1, 0))))
    for c, (sx, sy), din in posts:
        perp = Vector((-din.y, din.x, 0))
        reach = 0.27 if abs(din.x) > 0.1 and abs(din.y) > 0.1 else 0.12        # the post's face toward the room, from its centre
        add_box(granite, c + Vector((0, 0, 0.15)), (sx + 0.1, sy + 0.1, 0.30))
        add_box(ivory, c + Vector((0, 0, (0.30 + WALL_H - 0.14) / 2)), (sx, sy, WALL_H - 0.14 - 0.30))
        add_box(bronze, c + Vector((0, 0, WALL_H - 0.07)), (sx + 0.12, sy + 0.12, 0.14))
        for ph in (0.0, math.pi):
            pts = []
            n = 54
            for i in range(n + 1):
                z = 0.32 + (WALL_H - 0.5) * i / n
                a = ph + 2 * math.pi * 3.2 * i / n
                # two stems twisting round each other as they climb the post's room side: a weave across it, in and out
                pts.append(c + din * (reach + 0.035 + 0.03 * math.cos(a)) + perp * (0.15 * math.sin(a)) + Vector((0, 0, z)))
            tube(vines, pts, 0.022, 4)
            for i in range(3, n, 4):
                out = (din * 0.6 + perp * (1 if math.cos(ph + 2 * math.pi * 3.2 * i / n) > 0 else -1)).normalized()
                leaf(leaves, pts[i], out, pts[i + 1] - pts[i - 1])
    for wall in ("S", "E", "W"):
        n, t, dist, L = wall_frame(wall)
        p = n * dist + Vector((0, 0, 0))
        add_box(bronze, p - n * 0.11 + Vector((0, 0, WALL_H - 0.25)), (abs(t.x) * 0.34 + abs(n.x) * 0.22, abs(t.y) * 0.34 + abs(n.y) * 0.22, 0.5))
        add_cyl(copper, p - n * 0.14 + Vector((0, 0, WALL_H - 0.5)), p - n * 0.14 + Vector((0, 0, WALL_H - 0.78)), 0.09, 0.0, seg=10)
    for bm, nm, mat, tile, smooth in ((ivory, "Pilasters", "Ivory", MARBLE_TILE, False), (bronze, "Pilaster_Capitals", "Bronze", 1.0, False),
                                      (granite, "Pilaster_Plinths", "Verdigris_Marble", 1.0, False), (vines, "Vines", "Vine_Verdigris", 1.0, True),
                                      (leaves, "Vine_Leaves", "Vine_Leaf", 1.0, False), (copper, "Corbel_Pods", "Copper", 1.0, True)):
        box_uv(bm, tile)
        mesh_obj(nm, bm, mat, smooth=smooth)


def door_leaf(name, mat, loc, along, out):
    """A panelled door leaf 0.93 x 2.13 x 0.05 m, its origin on its hinge edge at the floor. `along` runs from the hinge to the knob's edge,
    `out` is the room's side (a knob on both faces)."""
    along, out = Vector(along), Vector(out)
    up = Vector((0, 0, 1))
    R = Matrix((along, out, up)).transposed().to_4x4()        # local x = along, y = out, z = up
    bm = bmesh.new()
    W, H, T = DOOR_W - 0.01, DOOR_H - 0.03, 0.05

    def P(u, z, d):
        return along * u + up * z + out * d

    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(P(W / 2, H / 2 + 0.02, 0)) @ R @ Matrix.Diagonal((W, T, H, 1)))
    for side in (1, -1):
        for (u0, u1, z0, z1) in ((0.14, 0.80, 1.20, 2.00), (0.14, 0.80, 0.18, 1.05)):
            c = P((u0 + u1) / 2, (z0 + z1) / 2, side * (T / 2 + 0.008))
            bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ R @ Matrix.Diagonal((u1 - u0, 0.016, z1 - z0, 1)))
    bm.faces.ensure_lookup_table()
    n0 = len(bm.faces)
    ku = W - 0.075
    for side in (1, -1):
        add_cyl(bm, P(ku, 1.05, side * T / 2), P(ku, 1.05, side * (T / 2 + 0.06)), 0.012, seg=8)
        bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.03, matrix=Matrix.Translation(P(ku, 1.05, side * (T / 2 + 0.07))))
    bm.faces.ensure_lookup_table()
    for f in bm.faces[n0:]:
        f.material_index = 1
    box_uv(bm, 1.0)
    ob = mesh_obj(name, bm, mat)
    ob.data.materials.append(MATS["Bronze"])
    ob.location = loc
    return ob


def casing(bm, name, u0, u1, top, w=0.14, d=0.05):
    """An ivory architrave round a door opening (jambs and head), proud of the wall by d."""
    n, t, dist, L = wall_frame(name)
    for uu in (u0 - w / 2, u1 + w / 2):
        add_box(bm, wall_pt(name, uu, (top + w) / 2, d / 2), (abs(t.x) * w + abs(n.x) * d, abs(t.y) * w + abs(n.y) * d, top + w))
    span = u1 - u0 + 2 * w
    add_box(bm, wall_pt(name, (u0 + u1) / 2, top + w / 2, d / 2), (abs(t.x) * span + abs(n.x) * d, abs(t.y) * span + abs(n.y) * d, w))


def build_door_in():
    """The way in (DoorLeaf_Oneiros_In, south wall) with its casing and a dark reveal behind."""
    bm = bmesh.new()
    casing(bm, "S", -DOOR_W / 2, DOOR_W / 2, DOOR_H)
    box_uv(bm, MARBLE_TILE)
    mesh_obj("Door_Casings", bm, "Ivory")
    bm = bmesh.new()
    c, size = Vector((0, -HALF_L - 0.18, DOOR_H / 2)), (DOOR_W, 0.36, DOOR_H)
    add_box(bm, c, size)
    drop = []
    for f in bm.faces:
        fc = f.calc_center_median()
        face_toward(f, c - fc)
        if abs(fc.y) < abs(c.y) - 0.17:
            drop.append(f)
    bmesh.ops.delete(bm, geom=drop, context="FACES_ONLY")
    box_uv(bm, 1.0)
    mesh_obj("Door_Reveal", bm, "Reveal_Dark")
    door_leaf("DoorLeaf_Oneiros_In", "Door_Ivory", Vector((-DOOR_W / 2, -HALF_L + 0.03, 0.0)), (1, 0, 0), (0, 1, 0))


PLACARD_C = Vector((1.3, -HALF_L + 0.012, 1.25))


def build_placard():
    c = PLACARD_C
    w, h = 0.42, 0.28
    bm = bmesh.new()
    f = poly(bm, [c + Vector(d) for d in ((-w / 2, 0, -h / 2), (w / 2, 0, -h / 2), (w / 2, 0, h / 2), (-w / 2, 0, h / 2))], Vector((0, 1, 0)), tri=False)
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp in f.loops:
        p = lp.vert.co
        lp[uvl].uv = ((p.x - c.x) / w + 0.5, (p.z - c.z) / h + 0.5)
    mesh_obj("Placard", bm, "Placard")
    bm = bmesh.new()
    add_box(bm, c + Vector((0, -0.004, 0)), (w + 0.03, 0.008, h + 0.03))
    box_uv(bm, 1.0)
    mesh_obj("Placard_Frame", bm, "Bronze")
    bm = bmesh.new()
    top = c + Vector((0, 0, h / 2 + 0.06))
    add_cyl(bm, top + Vector((0, -0.004, 0)), top + Vector((0, 0.16, 0.05)), 0.008, seg=8)
    head = top + Vector((0, 0.16, 0.05))
    add_cyl(bm, head - Vector((0.17, 0, 0)), head + Vector((0.17, 0, 0)), 0.022, seg=10)
    box_uv(bm, 1.0)
    mesh_obj("Placard_Light", bm, "Sconce_Bronze", smooth=True)
    bm = bmesh.new()
    add_box(bm, head + Vector((0, -0.004, -0.023)), (0.30, 0.012, 0.004))
    box_uv(bm, 1.0)
    mesh_obj("Placard_Light_Glow", bm, "Picture_Light_Emit")


MEDALLION_C = Vector((0.0, 0.85, 0.0))
MEDALLION_R = 0.85


def build_medallion():
    """The great floor medallion between the runner and the brazier (PLAN: terracotta-copper floor medallions; the small ones are in the tile)."""
    bm = bmesh.new()
    seg = 48
    pts = [MEDALLION_C + Vector((MEDALLION_R * math.cos(2 * math.pi * i / seg), MEDALLION_R * math.sin(2 * math.pi * i / seg), 0.003)) for i in range(seg)]
    f = poly(bm, pts, Vector((0, 0, 1)), tri=False)
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp in f.loops:
        p = lp.vert.co
        lp[uvl].uv = (0.5 + (p.x - MEDALLION_C.x) / (2 * MEDALLION_R), 0.5 + (p.y - MEDALLION_C.y) / (2 * MEDALLION_R))
    bmesh.ops.triangulate(bm, faces=[f], ngon_method="EAR_CLIP")
    mesh_obj("Floor_Medallion", bm, "Medallion")


# the vine sconces: (wall, the coordinate along it in world terms: y on E/W, x on N/S)
SCONCES = [("W", 2.4), ("W", -3.0), ("E", 1.6), ("E", -2.05), ("S", -2.6), ("S", 2.6)]
SCONCE_Z = 2.45


def sconce_points():
    out = []
    for wall, s in SCONCES:
        n, t, dist, L = wall_frame(wall)
        p = Vector((n.x * dist, s, 0)) if wall in ("E", "W") else Vector((s, n.y * dist, 0))
        out.append((wall, p, n, t))
    return out


def build_sconces():
    """Vine sconces: a bronze wall plate, a curling arm out from the wall, two bronze leaves cupping an opal bud (the lamp's bud, small)."""
    gold, bulbs, lv = bmesh.new(), bmesh.new(), bmesh.new()
    up = Vector((0, 0, 1))
    for wall, w, n, t in sconce_points():
        plate = w - n * 0.012 + up * SCONCE_Z
        m = Matrix.Translation(plate) @ Matrix.Rotation(math.atan2(n.y, n.x), 4, "Z") @ Matrix.Diagonal((0.024, 0.10, 0.24, 1))
        bmesh.ops.create_cube(gold, size=1.0, matrix=m)
        tip = plate - n * 0.22 - up * 0.04
        pts = [plate - n * 0.01 - up * 0.08 + (tip - plate + n * 0.01 + up * 0.08) * (i / 6) - up * 0.05 * math.sin(math.pi * i / 6) for i in range(7)]
        tube(gold, pts, 0.012, 4)
        for s in (-1, 1):
            leaf(lv, tip + up * 0.02, (t * s * 0.8 + up * 0.6).normalized(), -n, 0.09)
        m = Matrix.Translation(tip + up * 0.10) @ Matrix.Diagonal((0.05, 0.05, 0.08, 1))
        bmesh.ops.create_uvsphere(bulbs, u_segments=12, v_segments=8, radius=1.0, matrix=m)
    box_uv(gold, 1.0)
    mesh_obj("Sconces", gold, "Sconce_Bronze", smooth=True)
    box_uv(lv, 1.0)
    mesh_obj("Sconce_Leaves", lv, "Sconce_Bronze")
    box_uv(bulbs, 1.0)
    mesh_obj("Sconce_Bulbs", bulbs, "Lamp_Emit", smooth=True)


# ---------------------------------------------------------------- the furniture and the props
def yaw_for(code, facing):
    deg = COMPASS[facing] if isinstance(facing, str) else facing
    return math.radians(deg - NATIVE_FRONT[code])


ROOM_TEX = {"ON-00": 512, "ON-01": 512, "ON-06": 512, "P1L": 512, "P2L": 512}     # small or flat pieces: their base colour at 512 in the room


def load_copy(code, objname):
    path = next(COPIES.glob(f"{code}_*_game.glb"))
    if f"{code}_mesh" in bpy.data.meshes:
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
                    if code in ROOM_TEX and nd.image.size[0] > ROOM_TEX[code]:
                        nd.image.scale(ROOM_TEX[code], ROOM_TEX[code])       # the room's copy only (the GLB budget); the game copy keeps its size
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
        ob = load_copy(code, objname)
        ob.rotation_mode = "XYZ"                     # the glTF importer leaves quaternions
        ob.rotation_euler = (0, 0, yaw_for(code, facing))
        ob.location = (xy[0], xy[1], 0.0)
        bpy.context.view_layer.update()
        if how[0] in ("wall", "hang"):
            n, t, dist, L = wall_frame(how[1])
            reach = max(v.dot(n) for v in world_verts(ob))
            ob.location = Vector(ob.location) + n * (dist - how[2] - reach)
            if how[0] == "hang":
                ob.location.z = how[3]
        elif how[0] == "on":
            sup = placed[how[1]]
            bpy.context.view_layer.update()
            sv = world_verts(sup)
            cx = (min(v.x for v in sv) + max(v.x for v in sv)) / 2
            cy = (min(v.y for v in sv) + max(v.y for v in sv)) / 2
            tgt = Vector((cx + xy[0], cy + xy[1], 0))
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


def measure_gate(name, ob):
    """The gate's opening, read from the placed copy: rays from the room northward through the frame. The clear half-width at 1.2 m, the
    arch's top over the opening's centre, and the arch's height near its foot (0.9 of the half-width out), which fixes an elliptic arch."""
    bvh = bvh_of(ob)
    vs = world_verts(ob)
    y_lo, y_hi = min(v.y for v in vs), max(v.y for v in vs)
    x_lo, x_hi = min(v.x for v in vs), max(v.x for v in vs)
    cx0 = (x_lo + x_hi) / 2

    def blocked(x, z):
        hit = bvh.ray_cast(Vector((x, y_lo - 0.5, z)), Vector((0, 1, 0)), (y_hi - y_lo) + 1.0)
        return hit[0] is not None

    def clear_x(z, step=0.005):
        l = r = cx0
        while not blocked(l - step, z) and l - cx0 > -2:
            l -= step
        while not blocked(r + step, z) and r - cx0 < 2:
            r += step
        return l, r
    lefts, rights = zip(*[clear_x(z) for z in (0.6, 1.0, 1.4)])
    l, r = max(lefts), min(rights)
    cx, a = (l + r) / 2, (r - l) / 2
    top = 1.0
    while not blocked(cx, top + 0.005) and top < 3.4:
        top += 0.005
    z9 = 1.0
    while not blocked(cx + 0.9 * a, z9 + 0.005) and z9 < top:
        z9 += 0.005
    k9 = math.sqrt(1 - 0.81)
    rise = max(0.15, (top - z9) / (1 - k9))
    spring = max(DADO_Z + 0.2, top - rise)
    rise = top - spring
    threshold = blocked(cx, 0.04)
    g = {"cx": cx, "a": a, "top": top, "spring": spring, "rise": rise, "y_front": y_lo, "y_back": y_hi, "y_mid": (y_lo + y_hi) / 2,
         "x_lo": x_lo, "x_hi": x_hi, "z_top": max(v.z for v in vs), "threshold": threshold}
    g["aw"] = a + 0.05                                  # the wall's opening: a little wider and higher, its cut edge hidden behind the posts
    g["rise_w"] = top + 0.05 - spring
    print(f"GATE {name}: opening centre x {cx:.3f}, half-width {a:.3f}, spring {spring:.3f}, top {top:.3f}, frame x {x_lo:.2f}..{x_hi:.2f}, "
          f"y {y_lo:.2f}..{y_hi:.2f}, threshold {threshold}")
    return g


def place_leaves(placed):
    """The gates' leaves (P1L, P2L): each copy fitted to half its gate's opening (width) and to the arch's foot (height), its origin moved to
    the hinge edge (the edge with the hinge straps, +x as made), then placed on the posts' inner faces and swung open LEAF_OPEN degrees into
    the room. The west leaf (_L) is the copy mirrored. Each leaf has its own mesh (its own lightmap texels)."""
    for gname, code, leafname in (("ivory", "P2L", "Ivory"), ("horn", "P1L", "Horn")):
        g = GATES[gname]
        src = load_copy(code, f"tmp_{code}")
        me0 = src.data
        bpy.data.objects.remove(src)
        xs = [v.co.x for v in me0.vertices]
        zs = [v.co.z for v in me0.vertices]
        ys = [v.co.y for v in me0.vertices]
        w = g["a"] - 0.012
        h = g["spring"] - 0.03
        kx, kz = w / (max(xs) - min(xs)), h / (max(zs) - min(zs))
        ky = min(kx, kz) * 1.0
        g["leaf_w"], g["leaf_h"], g["leaf_stretch"] = w, h, kz / kx
        # the hinge edge: the leaf's tall side (its round top falls away to the free edge), read from the copy
        span = max(xs) - min(xs)
        top_hi = max((v.co.z for v in me0.vertices if v.co.x > max(xs) - 0.15 * span), default=0)
        top_lo = max((v.co.z for v in me0.vertices if v.co.x < min(xs) + 0.15 * span), default=0)
        hinge_plus = top_hi >= top_lo
        g["leaf_hinge_as_made"] = "+x" if hinge_plus else "-x"
        for side in ("L", "R"):
            me = me0.copy()
            me.name = f"DoorLeaf_Oneiros_{leafname}_{side}"
            # R: the hinge at the origin, the leaf toward -x; L: its mirror image (toward +x)
            mirror = (side == "L") == hinge_plus
            sx = -kx if mirror else kx
            hx0 = max(xs) if hinge_plus else min(xs)
            me.transform(Matrix.Diagonal((sx, ky, kz, 1.0)) @ Matrix.Translation((-hx0, -(min(ys) + max(ys)) / 2, -min(zs))))
            if mirror:
                bm = bmesh.new()
                bm.from_mesh(me)
                bmesh.ops.reverse_faces(bm, faces=bm.faces)
                bm.to_mesh(me)
                bm.free()
            ob = bpy.data.objects.new(me.name, me)
            ART.objects.link(ob)
            hx = g["cx"] - g["a"] if side == "L" else g["cx"] + g["a"]
            ob.location = (hx, g["y_mid"], 0.0)
            ob.rotation_euler = (0, 0, math.radians(-LEAF_OPEN if side == "L" else LEAF_OPEN))
            placed[me.name] = ob
        bpy.data.meshes.remove(me0)
        print(f"LEAVES {gname}: {w:.3f} x {h:.3f} m each, vertical stretch {kz / kx:.2f}")


def build_passages():
    """Behind each gate the wall is open (the gate's arch, a little larger) onto a short passage, PASS_D deep, ending in light: the ivory
    one bright and pearly (Glow_Ivory), the horn one a dull amber dusk (Glow_Horn). The walker enters the passage to choose."""
    for gname, mat, glow in (("ivory", "Passage_Ivory", "Glow_Ivory"), ("horn", "Passage_Horn", "Glow_Horn")):
        g = GATES[gname]
        prof = [(g["cx"] - g["aw"], 0.0)] + [(x, z) for x, z in arch_pts(g["cx"], g["aw"], g["spring"], g["rise_w"], 20)] + [(g["cx"] + g["aw"], 0.0)]
        y0, y1 = HALF_L, HALF_L + PASS_D
        bm = bmesh.new()
        for (xa, za), (xb, zb) in zip(prof[:-1], prof[1:]):
            f = bm.faces.new([bm.verts.new((xa, y0, za)), bm.verts.new((xb, y0, zb)), bm.verts.new((xb, y1, zb)), bm.verts.new((xa, y1, za))])
            c = f.calc_center_median()
            face_toward(f, Vector((g["cx"] - c.x, 0, g["spring"] * 0.6 - c.z)))
        poly(bm, [Vector((g["cx"] - g["aw"], y0, 0.001)), Vector((g["cx"] + g["aw"], y0, 0.001)), Vector((g["cx"] + g["aw"], y1, 0.001)),
                  Vector((g["cx"] - g["aw"], y1, 0.001))], Vector((0, 0, 1)))
        box_uv(bm, PEARL_TILE)
        mesh_obj(f"Passage_{gname}", bm, mat)
        bm = bmesh.new()
        f = poly(bm, [Vector((x, y1 - 0.01, z)) for x, z in prof], Vector((0, -1, 0)), tri=False)
        uvl = bm.loops.layers.uv.new("UVMap")
        for lp in f.loops:
            p = lp.vert.co
            lp[uvl].uv = (0.5 + (p.x - g["cx"]) / (2 * g["aw"]), p.z / (g["spring"] + g["rise_w"]))
        bmesh.ops.triangulate(bm, faces=[f], ngon_method="EAR_CLIP")
        mesh_obj(f"Passage_{gname}_Glow", bm, glow)


def build_brazier_smoke(placed):
    """The tripod brazier's opal smoke (decor_smoke_*): three crossed soft cards rising from the bowl, and a soft glow in the bowl
    (decor_brazier_glow). Camera-only in the bake; the scene code may drift and turn them."""
    br = placed["P15_brazier"]
    vs = world_verts(br)
    top = max(v.z for v in vs)
    c = Vector(((min(v.x for v in vs) + max(v.x for v in vs)) / 2, (min(v.y for v in vs) + max(v.y for v in vs)) / 2, top))
    for k in range(3):
        a = math.pi * k / 3
        d = Vector((math.cos(a), math.sin(a), 0))
        w, h = 0.62, 1.6
        bm = bmesh.new()
        p0 = c - d * w / 2 + Vector((0, 0, -0.06))
        f = poly(bm, [p0, p0 + d * w, p0 + d * w + Vector((0, 0, h)), p0 + Vector((0, 0, h))], Vector((-d.y, d.x, 0)), tri=False)
        uvl = bm.loops.layers.uv.new("UVMap")
        for lp, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
            lp[uvl].uv = uv
        mesh_obj(f"decor_smoke_{k}", bm, "Smoke_Opal")
    bm = bmesh.new()
    seg = 24
    hit = bvh_of(br).ray_cast(Vector((c.x, c.y, top + 1)), Vector((0, 0, -1)))
    zb = hit[0].z + 0.01 if hit[0] is not None else top - 0.1
    r = 0.16
    poly(bm, [Vector((c.x + r * math.cos(2 * math.pi * i / seg), c.y + r * math.sin(2 * math.pi * i / seg), zb)) for i in range(seg)], Vector((0, 0, 1)))
    box_uv(bm, 1.0)
    mesh_obj("decor_brazier_glow", bm, "Brazier_Glow")
    return Vector((c.x, c.y, zb))


def mirror_glass(placed):
    """The wall mirror ON-06's glass, found by rays from the room (+x): the flat middle round its centre. decor_mirror_view, an oval
    3 mm before it, carries a picture of the room as the mirror sees it (rendered after the bake); the scene code hides it for 'the mirror is
    empty'. Returns the glass's centre, its half-width (y) and half-height (z)."""
    mob = placed["ON-06_wall_mirror"]
    bvh = bvh_of(mob)
    vs = world_verts(mob)
    y_lo, y_hi = min(v.y for v in vs), max(v.y for v in vs)
    z_lo, z_hi = min(v.z for v in vs), max(v.z for v in vs)
    x0 = min(v.x for v in vs) - 0.3
    yc, zc = (y_lo + y_hi) / 2, (z_lo + z_hi) / 2

    def hx(y, z):
        h = bvh.ray_cast(Vector((x0, y, z)), Vector((1, 0, 0)), 1.0)
        return h[0].x if h[0] is not None else None
    xc = hx(yc, zc)
    if xc is None:
        xc = min(v.x for v in vs) + 0.03

    def reach(dy, dz):
        k = 0
        while True:
            k += 1
            x = hx(yc + dy * k * 0.004, zc + dz * k * 0.004)
            if x is None or abs(x - xc) > 0.006 or k > 200:
                return (k - 1) * 0.004
    a = min(reach(1, 0), reach(-1, 0))
    b = min(reach(0, 1), reach(0, -1))
    a, b = max(0.06, a * 0.95), max(0.12, b * 0.95)
    print(f"MIRROR glass at x {xc:.3f}, y {yc:.3f}, z {zc:.3f}: half-width {a:.3f}, half-height {b:.3f}")
    bm = bmesh.new()
    seg = 40
    pts = []
    for i in range(seg):
        t = 2 * math.pi * i / seg
        pts.append(Vector((xc - 0.003, yc + a * math.cos(t), zc + b * math.sin(t))))
    f = poly(bm, pts, Vector((-1, 0, 0)), tri=False)
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp in f.loops:
        p = lp.vert.co
        lp[uvl].uv = (0.5 + (p.y - yc) / (2 * a), 0.5 + (p.z - zc) / (2 * b))
    bmesh.ops.triangulate(bm, faces=[f], ngon_method="EAR_CLIP")
    mesh_obj("decor_mirror_view", bm, "Mirror_View")
    return Vector((xc, yc, zc)), a, b


def build_sand(placed):
    """'The sand in the hourglass is falling up': a thin thread of grains rising out of the hourglass's top (decor_sand_up), for the code to
    drift upward."""
    hg = placed["ON-09_hourglass"]
    vs = world_verts(hg)
    top = max(v.z for v in vs)
    c = Vector(((min(v.x for v in vs) + max(v.x for v in vs)) / 2, (min(v.y for v in vs) + max(v.y for v in vs)) / 2, top))
    rng = np.random.default_rng(77)
    bm = bmesh.new()
    for i in range(16):
        p = c + Vector((rng.normal(0, 0.004), rng.normal(0, 0.004), 0.008 + 0.012 * i + rng.uniform(0, 0.006)))
        bmesh.ops.create_icosphere(bm, subdivisions=0, radius=0.0035, matrix=Matrix.Translation(p))
    box_uv(bm, 1.0)
    mesh_obj("decor_sand_up", bm, "Sand_Glow")


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


def bbox(ob):
    vs = world_verts(ob)
    return tuple(min(v[i] for v in vs) for i in range(3)), tuple(max(v[i] for v in vs) for i in range(3))


STANDING = ("ON-05", "ON-01", "ON-03", "ON-04", "ON-07", "ON-02")


def build_layout(placed):
    """COL_ boxes: the shell, the north wall in pieces round the two gate openings, the passages, the gates' posts and open leaves, the
    brazier, the pilasters. The furniture's boxes come twice: COL_furn_* as built and COL_wrong1_* mirrored about x = 0 (the first wrong room,
    when the scene code mirrors grp_furniture). Markers, links, zones and spots as PLAN 4.5."""
    T = 0.3
    col_box("COL_floor", (-HALF_W, -HALF_L, -0.2), (HALF_W, HALF_L, 0.0))
    col_box("COL_wall_W", (-HALF_W - T, -HALF_L, 0), (-HALF_W, HALF_L, WALL_H))
    col_box("COL_wall_E", (HALF_W, -HALF_L, 0), (HALF_W + T, HALF_L, WALL_H))
    col_box("COL_wall_S_a", (-HALF_W, -HALF_L - T, 0), (-DOOR_W / 2, -HALF_L, WALL_H))
    col_box("COL_wall_S_b", (DOOR_W / 2, -HALF_L - T, 0), (HALF_W, -HALF_L, WALL_H))
    col_box("COL_wall_S_head", (-DOOR_W / 2, -HALF_L - T, DOOR_H), (DOOR_W / 2, -HALF_L, WALL_H))
    col_box("COL_door_in", (-DOOR_W / 2, -HALF_L - T, 0), (DOOR_W / 2, -HALF_L, DOOR_H))          # the way in stays shut behind the walker
    iv, hn = GATES["ivory"], GATES["horn"]
    xs = [-HALF_W, iv["cx"] - iv["aw"], iv["cx"] + iv["aw"], hn["cx"] - hn["aw"], hn["cx"] + hn["aw"], HALF_W]
    for i, (x0, x1) in enumerate(((xs[0], xs[1]), (xs[2], xs[3]), (xs[4], xs[5]))):
        col_box(f"COL_wall_N_{'abc'[i]}", (x0, HALF_L, 0), (x1, HALF_L + T, WALL_H))
    for gname, g in GATES.items():
        x0, x1 = g["cx"] - g["aw"], g["cx"] + g["aw"]
        col_box(f"COL_wall_N_head_{gname}", (x0, HALF_L, g["top"]), (x1, HALF_L + T, WALL_H))
        col_box(f"COL_passage_{gname}_W", (x0 - T, HALF_L, 0), (x0, HALF_L + PASS_D, g["top"]))
        col_box(f"COL_passage_{gname}_E", (x1, HALF_L, 0), (x1 + T, HALF_L + PASS_D, g["top"]))
        col_box(f"COL_passage_{gname}_back", (x0, HALF_L + PASS_D - 0.05, 0), (x1, HALF_L + PASS_D + T, g["top"]))
        col_box(f"COL_gate_{gname}_post_W", (g["x_lo"], g["y_front"], 0), (g["cx"] - g["a"], g["y_back"], g["z_top"]))
        col_box(f"COL_gate_{gname}_post_E", (g["cx"] + g["a"], g["y_front"], 0), (g["x_hi"], g["y_back"], g["z_top"]))
        leafname = "Ivory" if gname == "ivory" else "Horn"
        for side in ("L", "R"):
            lo, hi = bbox(placed[f"DoorLeaf_Oneiros_{leafname}_{side}"])
            col_box(f"COL_leaf_{gname}_{side}", lo, hi)
    for nm, ob in placed.items():
        if nm.startswith(STANDING):
            lo, hi = bbox(ob)
            col_box(f"COL_furn_{nm}", lo, hi)
            col_box(f"COL_wrong1_{nm}", (-hi[0], lo[1], lo[2]), (-lo[0], hi[1], hi[2]))
    lo, hi = bbox(placed["P15_brazier"])
    col_box("COL_brazier", lo, (hi[0], hi[1], 1.1))
    for sx in (-1, 1):
        for sy in (-1, 1):
            c = Vector((sx * (HALF_W - 0.13), sy * (HALF_L - 0.13), 0))
            col_box(f"COL_pilaster_{'N' if sy > 0 else 'S'}{'E' if sx > 0 else 'W'}", (c.x - 0.25, c.y - 0.25, 0), (c.x + 0.25, c.y + 0.25, WALL_H))
    col_box("COL_pilaster_N", (-0.25, HALF_L - 0.25, 0), (0.25, HALF_L, WALL_H))
    face_n = math.radians(180)                         # an Arrive_'s -Y axis is the way you face: yaw 180 faces +Y (north)
    empty("Marker_Spawn", (SPAWN.x, SPAWN.y, 0), "Spawn", yaw=face_n)
    empty("Marker_Entrance", (0, -HALF_L + 0.3, 0), "Entrance", yaw=face_n)
    empty("Marker_Exit", (hn["cx"], HALF_L + 0.6, 0), "Exit", yaw=face_n)
    empty("Arrive_Oneiros_In", (SPAWN.x, SPAWN.y, 0), yaw=face_n, note="just inside the south door (from rdwe_god_morpheus's wardrobe)")
    empty("Arrive_Oneiros_S", (SPAWN.x, SPAWN.y, 0), yaw=face_n, note="the ivory gate's loop lands here, facing north, yaw kept")
    empty("Link_Oneiros_Ivory", (iv["cx"], HALF_L + 0.6, 0), to_scene=SCENE, to_arrive="Arrive_Oneiros_S",
          note="the false dream: loops to the south door and shows the next decor_wrong set")
    empty("Link_Oneiros_Horn", (hn["cx"], HALF_L + 0.6, 0), to_scene="rdwe_god_thanatos", to_arrive="Arrive_Thanatos_In",
          note="the true dream: the exit")
    empty("Spot_gate_ivory", (iv["cx"], iv["y_front"] - 0.8, 0), note="the Gate of Ivory: carved, pearl-set, lit; it lies")
    empty("Spot_gate_horn", (hn["cx"], hn["y_front"] - 0.8, 0), note="the Gate of Horn: plain, dull; it is true")
    empty("Spot_runner", (0.6, -2.4, 0), note="the runner's swirl points to the horn gate")
    hg = placed["ON-09_hourglass"]
    empty("Spot_hourglass", Vector(hg.location), note="the sand falls up (decor_sand_up)")
    empty("Spot_clock", Vector(placed["decor_clock"].location), note="the clock runs backward; its face reversed in the third wrong room")
    for gname, g in GATES.items():
        x0, x1 = g["cx"] - g["aw"] + 0.05, g["cx"] + g["aw"] - 0.05
        col_box(f"Zone_trigger_{gname}", (x0, HALF_L + 0.3, 0), (x1, HALF_L + 0.95, g["spring"]))
    for gname, leafname in (("ivory", "Ivory"), ("horn", "Horn")):
        for side in ("L", "R"):
            leaf = bpy.data.objects[f"DoorLeaf_Oneiros_{leafname}_{side}"]
            leaf["hinge"] = f"the {'west' if side == 'L' else 'east'} post's inner face (the leaf's origin)"
            leaf["swing_deg"] = -LEAF_OPEN if side == "L" else LEAF_OPEN
            leaf["state"] = f"open {LEAF_OPEN:.0f} degrees into the room; rotate about z by {'+' if side == 'L' else '-'}{LEAF_OPEN:.0f} to close"
    leaf_in = bpy.data.objects["DoorLeaf_Oneiros_In"]
    leaf_in["hinge"] = "west edge"
    leaf_in["swing_deg"] = 0
    leaf_in["state"] = "closed"


# ---------------------------------------------------------------- lights (for the bake and the stills; never exported)
SCONCE_W = 9.0           # each vine sconce's bud (W)
PLACARD_W = 0.09         # the placard's picture light
LAMP_W = 12.0            # the opal lamp on the north bedside table
GLOW_W = 420.0           # the vault's glow: an area light under the crown pointing down, the even part of the light
IVORY_W = 55.0           # the ivory passage's light, out through the gate
IVORY_SPOT_W = 55.0      # a spot from the vault onto the ivory gate: it glows
HORN_W = 18.0            # the horn passage's light: dull
BRAZIER_W = 7.0          # the opal glow in the brazier's bowl


def add_lights(coll_name="Lights"):
    lights = bpy.data.collections.new(coll_name)
    bpy.context.scene.collection.children.link(lights)

    def light(name, kind, loc, energy, color, size=0.05):
        d = bpy.data.lights.new(name, kind)
        d.energy, d.color = energy, color
        d.shadow_soft_size = size
        ob = bpy.data.objects.new(name, d)
        ob.location = loc
        lights.objects.link(ob)
        return ob, d

    for i, (wall, w, n, t) in enumerate(sconce_points()):
        light(f"Sconce_{i}", "POINT", w - n * 0.232 + Vector((0, 0, SCONCE_Z + 0.06)), SCONCE_W, (1.0, 0.80, 0.60), 0.05)
    lamp = bpy.data.objects.get("ON-00_lamp")
    if lamp:
        vs = world_verts(lamp)
        z0 = min(v.z for v in vs)
        H = max(v.z for v in vs) - z0
        band = [v for v in vs if z0 + 0.70 * H < v.z < z0 + 0.95 * H]          # the opal bud at the top
        c = sum(band, Vector()) / len(band) + Vector((0.12, 0, 0))
        light("Lamp_Bulb", "POINT", c, LAMP_W, (1.0, 0.76, 0.50), 0.03)
        if "decor_lamp_glow" not in bpy.data.objects:
            bm = bmesh.new()
            bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.025, matrix=Matrix.Translation(c))
            box_uv(bm, 1.0)
            mesh_obj("decor_lamp_glow", bm, "Lamp_Bulb_Emit", smooth=True)
    pc = PLACARD_C + Vector((0, 0.16, 0.14 + 0.06 + 0.05 - 0.03))
    ob, d = light("Placard_Light", "AREA", pc, PLACARD_W, (1.0, 0.85, 0.65), 0.0)
    d.shape, d.size, d.size_y = "RECTANGLE", 0.28, 0.02
    ob.rotation_euler = ((PLACARD_C - Vector((0, 0.012, 0))) - ob.location).to_track_quat("-Z", "Y").to_euler()
    ob, d = light("Vault_Glow", "AREA", (0, 0, VAULT_TOP - 0.5), GLOW_W, (0.86, 0.84, 1.0), 0.0)
    d.shape, d.size, d.size_y = "RECTANGLE", 7.0, 6.0
    iv, hn = GATES["ivory"], GATES["horn"]
    for name, g, w, col in (("Ivory_Light", iv, IVORY_W, (1.0, 0.93, 0.88)), ("Horn_Light", hn, HORN_W, (1.0, 0.66, 0.36))):
        ob, d = light(name, "AREA", (g["cx"], HALF_L + PASS_D - 0.1, g["spring"] * 0.7), w, col, 0.0)
        d.shape, d.size, d.size_y = "RECTANGLE", 2 * g["aw"] * 0.8, g["spring"] * 0.9
        ob.rotation_euler = (-math.pi / 2, 0, 0)            # the area light faces south, out through the gate
    ob, d = light("Ivory_Spot", "SPOT", (iv["cx"] + 0.4, 1.4, 4.3), IVORY_SPOT_W, (1.0, 0.92, 0.84), 0.2)
    d.spot_size = math.radians(42)
    d.spot_blend = 0.6
    ob.rotation_euler = (Vector((iv["cx"], iv["y_front"], 1.8)) - ob.location).to_track_quat("-Z", "Y").to_euler()
    bz = bpy.data.objects.get("decor_brazier_glow")
    if bz:
        vs = world_verts(bz)
        c = sum(vs, Vector()) / len(vs) + Vector((0, 0, 0.08))
        light("Brazier_Glow", "POINT", c, BRAZIER_W, (0.88, 0.84, 1.0), 0.08)
    return lights


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("Night")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
    bg.inputs["Strength"].default_value = 0.0


CAMERA_ONLY = ("Glow_Ivory", "Glow_Horn", "Smoke_Opal", "Mirror_View", "Picture_Light_Emit", "Sand_Glow", "Brazier_Glow")
NO_SHADOW = ("Lamp_Emit", "Lamp_Bulb_Emit", "Sconce_Bronze") + CAMERA_ONLY


def ray_vis(o):
    """The passages' glows, the smoke, the mirror's picture and the little glows show to the camera only: they light and shade nothing."""
    m = o.data.materials[0].name if o.type == "MESH" and o.data.materials else ""
    if m in NO_SHADOW:
        o.visible_shadow = False
    if m in CAMERA_ONLY:
        o.visible_diffuse = o.visible_glossy = o.visible_transmission = False


def build_all():
    global ART, LAYOUT
    clear_scene()
    MATS.clear()
    GATES.clear()
    ART = bpy.data.collections.new("Art")
    LAYOUT = bpy.data.collections.new("Layout")
    sc = bpy.context.scene
    sc.collection.children.link(ART)
    sc.collection.children.link(LAYOUT)
    gen = {"floor": mk_image("Oneiros_Floor", floor_pixels()), "verdigris": mk_image("Oneiros_Verdigris", verdigris_pixels()),
           "pearl": mk_image("Oneiros_Pearl", pearl_pixels()), "ivory": mk_image("Oneiros_Ivory", ivory_pixels()),
           "frieze": mk_image("Oneiros_Frieze", frieze_pixels()), "opal": mk_image("Oneiros_Opal", opal_pixels()),
           "medallion": mk_image("Oneiros_Medallion", medallion_pixels()), "placard": mk_image("Oneiros_Placard", placard_pixels()),
           "glow_ivory": mk_image("Oneiros_Glow_Ivory", glow_pixels(True)), "glow_horn": mk_image("Oneiros_Glow_Horn", glow_pixels(False)),
           "smoke": mk_image("Oneiros_Smoke", smoke_pixels()),
           "mirror_wait": mk_image("Oneiros_Mirror_View", np.full((128, 64, 3), 0.5, np.float32))}
    make_materials(gen)
    placed = place_all()
    for gname, obn in (("ivory", "P2_gate_ivory"), ("horn", "P1_gate_horn")):
        GATES[gname] = measure_gate(gname, placed[obn])
    place_leaves(placed)
    build_shell()
    build_pilasters()
    build_passages()
    build_door_in()
    build_placard()
    build_medallion()
    build_sconces()
    build_brazier_smoke(placed)
    mirror_glass(placed)
    build_sand(placed)
    build_layout(placed)
    add_lights()
    setup_world()
    sc.unit_settings.system = "METRIC"
    (work() / "gates.json").write_text(json.dumps(GATES, indent=1))
    for o in ART.objects:
        ray_vis(o)


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    scrub_private()
    bpy.ops.wm.save_mainfile()


def load_gates():
    if not GATES:
        GATES.update(json.loads((work() / "gates.json").read_text()))


# ================================================================ bake (R1)
def furn(*codes):
    return tuple(f"{PFX}{c}_" for c in codes)


GROUPS = [
    ("Floor_Stone", "Verdigris_Marble", "Ivory", "Wall_Pearl", "Scallop_Frieze", "Door_Ivory", "Reveal_Dark", "Placard", "Medallion",
     "Passage_Ivory", "Passage_Horn"),                                                                                                 # 0 floor, walls, trim
    ("Vault_Opal", "Bronze", "Copper", "Vine_Verdigris", "Vine_Leaf"),                                                                 # 1 vault, ribs, vines
    furn("ON-01", "ON-02", "ON-03", "ON-04", "ON-05", "ON-06", "ON-07", "ON-11"),                                                      # 2 the big furniture
    furn("ON-00", "ON-08", "ON-09", "ON-10", "ON-12", "P1", "P1L", "P2", "P2L", "P15"),                                              # 3 the smalls and the props
]
MIN_DENSITY = [30, 26, 60, 50]          # px per metre wanted on each map (the search takes the smallest page that gives it)
PAGES = [None, None, None, None]        # auto; --pages a,b,c,d pins them
if arg("--pages"):
    PAGES = [None if v == "auto" else int(v) for v in arg("--pages").split(",")]
NOLM = ("Lamp_Emit", "Lamp_Bulb_Emit", "Sconce_Bronze", "Picture_Light_Emit", "Glow_Ivory", "Glow_Horn", "Smoke_Opal", "Brazier_Glow",
        "Mirror_View", "Sand_Glow")
KEEP_NODES = ("DoorLeaf_", "decor_")     # exported as their own nodes (the scene code moves, shows or hides them), not merged by material
FURN_NODE = ("decor_clock", "decor_mirror_view", "decor_sand_up", "decor_lamp_glow")     # own nodes that hang under grp_furniture
MAIN = ("Floor_Stone", "Wall_Pearl", "Ivory", "Vault_Opal", PFX)   # held to a displayed p90 <= TARGET
NOT_MAIN = (f"{PFX}ON-00_lamp",)        # the lamp's own body, inches from its bulb: reported, not held
TARGET_P90 = arg("--target", 0.90, float)
CLIP_CAP = arg("--clip-cap", 0.98, float)     # and no main surface's p99 above this (0 turns the cap off)


def group_of(mname):
    for n, g in enumerate(GROUPS):
        if any(mname == x or (x.endswith("_") and mname.startswith(x)) for x in g):
            return n
    return None


def in_furniture(name, mname):
    return name.startswith(FURN_NODE) or (mname.startswith(PFX + "ON-") and not mname.startswith(PFX + "ON-11"))


def make_export_objects():
    art = bpy.data.collections["Art"]
    if "Export" in bpy.data.collections:
        for o in list(bpy.data.collections["Export"].objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(bpy.data.collections["Export"])
    exp = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(exp)
    grp = bpy.data.objects.new("grp_furniture", None)
    exp.objects.link(grp)
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
    n = 0
    for name, ob in out.items():
        ray_vis(ob)
        if in_furniture(name, ob.data.materials[0].name):
            mw = ob.matrix_world.copy()
            ob.parent = grp
            ob.matrix_parent_inverse = Matrix.Identity(4)
            ob.matrix_basis = mw
            n += 1
    print(f"GRP_FURNITURE {n} nodes")
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
    copies stage's islands, which do not overlap) as one square, and the squares are shelf-packed here, sized by each piece's area."""
    furn_objs = [o for o in objs if o.data.materials[0].name.startswith(PFX)]
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
            # one UV0 square per piece; the merged bedside pair (two pieces, one UV0) splits by its centre y
            poly_lstart = np.zeros(len(me.polygons), np.int32)
            me.polygons.foreach_get("loop_start", poly_lstart)
            poly_ltot = np.zeros(len(me.polygons), np.int32)
            me.polygons.foreach_get("loop_total", poly_ltot)
            cen = np.zeros(len(me.polygons) * 3, np.float32)
            me.polygons.foreach_get("center", cen)
            cy = cen.reshape(-1, 3)[:, 1]
            keys = [0] * len(me.polygons)
            if o.name.startswith(PFX + "ON-01_"):
                mid = float((cy.min() + cy.max()) / 2)
                keys = [0 if c < mid else 1 for c in cy]
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


LIGHT_W = (("Sconce_", SCONCE_W), ("Lamp_Bulb", LAMP_W), ("Vault_Glow", GLOW_W), ("Placard_Light", PLACARD_W), ("Ivory_Light", IVORY_W),
           ("Ivory_Spot", IVORY_SPOT_W), ("Horn_Light", HORN_W), ("Brazier_Glow", BRAZIER_W))


def all_lights():
    return list(bpy.data.collections["Lights"].objects) if "Lights" in bpy.data.collections else []


def reset_lights():
    """The lights at the constants' energies (the saved .blend holds them times the last bake's exposure), so a bake is the same from any start."""
    for ob in all_lights():
        for prefix, w in LIGHT_W:
            if ob.name.startswith(prefix):
                ob.data.energy = w


MIRROR_PX = (320, 704)


def render_mirror_view():
    """The wall mirror's picture: the lit room rendered from the glass's centre, looking west, the size of the glass (decor_mirror_view's UV
    spans the glass). Seen in the mirror the room's north stays on the viewer's left, as a camera at the glass sees it: no flip."""
    sc = bpy.context.scene
    mv = bpy.data.objects["decor_mirror_view"]
    vs = world_verts(mv)
    c = sum(vs, Vector()) / len(vs)
    a = (max(v.y for v in vs) - min(v.y for v in vs)) / 2
    b = (max(v.z for v in vs) - min(v.z for v in vs)) / 2
    hidden = [o for o in (mv, bpy.data.objects.get("decor_mirror_view_x")) if o]
    for o in hidden:
        o.hide_render = True
    exp = bpy.data.collections["Export"]
    exp.hide_render = True
    bpy.data.collections["Art"].hide_render = False
    cam = bpy.data.cameras.new("mirror_view")
    cam.sensor_fit = "VERTICAL"
    cam.lens_unit = "FOV"
    cam.angle_y = 2 * math.atan(b / 0.55)                 # the glass as a window seen from about half a metre: a wide, mirror-like view
    cam.clip_start = 0.02
    ob = bpy.data.objects.new("mirror_view", cam)
    sc.collection.objects.link(ob)
    ob.location = c + Vector((-0.02, 0, 0))
    ob.rotation_euler = Vector((-1, 0, -0.08)).to_track_quat("-Z", "Y").to_euler()
    sc.camera = ob
    setup_cycles(96)
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0
    sc.render.resolution_x, sc.render.resolution_y = MIRROR_PX[0], int(MIRROR_PX[0] * b / a) if a > 0 else MIRROR_PX[1]
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    path = work() / "mirror_view.png"
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(ob)
    for o in hidden:
        o.hide_render = False
    im = bpy.data.images.get("Oneiros_Mirror_View")
    if im:
        bpy.data.images.remove(im)
    im = bpy.data.images.load(str(path))
    im.name = "Oneiros_Mirror_View"
    im.pack()
    for ref in [im] + list(im.packed_files):
        attr = "filepath_raw" if ref is im else "filepath"
        setattr(ref, attr, "_" * 1000)
        setattr(ref, attr, "//generated/Oneiros_Mirror_View.png")
    MATS_M = bpy.data.materials["Mirror_View"]
    MATS_M.node_tree.nodes["EMIT_IMG"].image = im
    print("MIRROR VIEW", path.name, sc.render.resolution_x, sc.render.resolution_y)


def stage_bake():
    load_gates()
    reset_lights()
    exp = make_export_objects()
    bpy.data.collections["Art"].hide_render = True
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
    for ob in all_lights():      # the lights as the page shows them, so the stills hold the lightmaps' light
        ob.data.energy *= k
    (work() / "lightmaps.json").write_text(json.dumps({"maps": report, "exposure_k": round(k, 5), "target_p90": TARGET_P90, "clip_cap_p99": CLIP_CAP,
                                                       "cap_binds": capped, "displayed": disp}, indent=1))
    for m, d in sorted(disp.items()):
        print(f"DISPLAYED {m:34s} map {d['map']}  p50 {d['p50']:.3f}  p90 {d['p90']:.3f}  p99 {d['p99']:.3f}  {'main' if d['main'] else ''}")
    render_mirror_view()
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
    for o in objs:
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
        bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=False,
                                  export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                                  export_cameras=False, export_lights=False, export_animations=False,
                                  export_draco_mesh_compression_enable=draco, export_draco_mesh_compression_level=6,
                                  export_draco_position_quantization=14, export_draco_normal_quantization=10, export_draco_texcoord_quantization=12)
        print("EXPORTED", path.name, path.stat().st_size)
    for o in objs:
        if o.type == "MESH":
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
        cam.sensor_fit = "AUTO"
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


def furniture_art():
    """The Art objects that hang under grp_furniture in the export (for the 'wrong room' still)."""
    out = []
    for o in bpy.data.collections["Art"].objects:
        if o.type == "MESH" and o.data.materials and in_furniture(o.name, o.data.materials[0].name):
            out.append(o)
    return out


def stage_render():
    load_gates()
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
    iv, hn = GATES["ivory"], GATES["horn"]
    shots = {
        "1_arrival": (look_cam("arrival", (SPAWN.x, SPAWN.y, EYE), (0, SPAWN.y + 6, EYE + 0.75), 72.0), (1920, 1080), STILLS),
        "2_wide": (look_cam("wide", (4.1, -4.1, 3.4), (-1.4, 1.6, 0.9), 72.0), (1920, 1080), STILLS),
        "3_bedchamber": (look_cam("bed", (1.4, -2.2, EYE + 0.35), (-4.2, 0.0, 1.0), 66.0), (1920, 1080), STILLS),
        "4_gates": (look_cam("gates", (0.15, 0.3, EYE), (0.1, HALF_L, 1.75), 72.0), (1920, 1080), STILLS),
        "ivory": (look_cam("ivory", (iv["cx"] + 0.5, 1.6, EYE), (iv["cx"], HALF_L + 1.0, 1.5), 66.0), (1280, 720), work()),
        "horn": (look_cam("horn", (hn["cx"] - 0.5, 1.6, EYE), (hn["cx"], HALF_L + 1.0, 1.5), 66.0), (1280, 720), work()),
        "mirror": (look_cam("mirror", (2.6, -1.2, 1.45), (5.0, -0.8, 1.55), 50.0), (1280, 720), work()),
        "wrong1": (look_cam("wrong1", (SPAWN.x, SPAWN.y, EYE), (0, SPAWN.y + 6, EYE + 0.75), 72.0), (1280, 720), work()),
        "plan": (look_cam("plan", (0, 0.6, 30), None, ortho=12.6), (1120, 1080), work()),
    }
    shots["plan"][0].data.clip_start = 30 - 3.3              # cut away everything above 3.3 m: the vault, the frieze, the gates' arches
    which = arg("--only", "all")
    for key, (cam, (w, h), folder) in shots.items():
        if which != "all" and key not in which.split(","):
            continue
        flipped = []
        if key == "wrong1":                                  # the first wrong room: the furniture mirrored about x = 0, as the scene code does
            M = Matrix.Diagonal((-1, 1, 1, 1))
            for o in furniture_art():
                flipped.append((o, o.matrix_world.copy()))
                o.matrix_world = M @ o.matrix_world
            lt = bpy.data.objects.get("Lamp_Bulb")
            if lt:
                flipped.append((lt, lt.matrix_world.copy()))
                lt.matrix_world = M @ lt.matrix_world
        sc.camera = cam
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
        for o, mw in flipped:
            o.matrix_world = mw
        print("STILL", key, path.stat().st_size, "q", q)


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
