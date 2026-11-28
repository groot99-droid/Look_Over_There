"""Builds Right Door, Wrong Exit's god room Morpheus, "The Shaping Hall" (`rdwe_god_morpheus`), in Blender: the reduced game copies of the owner's
Morpheus furniture set, the forced-perspective hall, its wardrobe-at-the-end trick, the bake, and world/rdwe_god_morpheus.glb with its lightmaps.
Made from tools/blender/build_rdwe_nyx.py (the first god room), with the same stages and the same exposure rule.

Re-runnable, from the repo root (docs/BLENDER.md, docs/BLENDER_AREAS.md section 7):

    blender -b --factory-startup --python tools/blender/build_rdwe_morpheus.py -- --stage copies --src <folder>   (the 13 originals and 2 props -> reduced copies)
    blender -b --factory-startup --python tools/blender/build_rdwe_morpheus.py -- --stage art                     (the hall; saves blender/scenes/rdwe_god_morpheus.blend)
    blender -b --factory-startup blender/scenes/rdwe_god_morpheus.blend --python tools/blender/build_rdwe_morpheus.py -- --stage bake [--samples 512]
    blender -b --factory-startup blender/scenes/rdwe_god_morpheus.blend --python tools/blender/build_rdwe_morpheus.py -- --stage export
    blender -b --factory-startup blender/scenes/rdwe_god_morpheus.blend --python tools/blender/build_rdwe_morpheus.py -- --stage render
    (--stage bake,export,render runs several in one go; --stage views writes view sheets of the copies)
    then, in plain Python (Pillow): each lightmap PNG -> world/lightmaps/rdwe_god_morpheus_<n>.webp (q90), and
    python tools/webp_glb.py blender/work/farway_rdwe_god_morpheus/rdwe_god_morpheus_raw.glb world/rdwe_god_morpheus.glb 85
    (docs/renders/rdwe_god_morpheus/README.md has the exact steps; the work folder is blender/work/farway_rdwe_god_morpheus, git-ignored)

The hall (PLAN section 4.4) is a forced-perspective cone: every cross-section is the same 6 x 3.2 m room scaled by s(y) = (y + 21) / 12 about a
vanishing point 12 m behind the door (y = -21), so the half-width is 3 + 0.25 (y + 9) and the ceiling 3.2 + 0.267 (y + 9). The script draws
everything in "normal room" coordinates (X across, Y the depth, Z up; Y = 12 ln s) and maps them with P(X, Y, Z) = (X s, 12 s - 21, Z s), a
conformal map: the panels, the floor squares, the mouldings, the columns, the sconces and the masks all grow with distance and keep their shape.

Axes: Blender metres, x east, y north, z up, the hall's centre at the origin, the floor at z = 0. The glTF exporter's +Y up turns Blender
(x, y, z) into game (x, z, -y), so game north is -z, as everywhere in Farway.
"""
import csv
import json
import math
import os
import random
import sys
import time
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[2]
SCENE = "rdwe_god_morpheus"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
COPIES = ROOT / "blender/models/rdwe_morpheus"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"
MARGIN_PX = 8
SET = "Morpheus"

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 512, int)
DEVICE = arg("--device", "auto")
SRC = Path(arg("--src", str(ROOT / "blender/work/morpheus_source")))
ONLY = arg("--only", "all")


def work():
    d = Path(arg("--work", str(ROOT / f"blender/work/farway_{SCENE}")))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- the pieces (manifest: Morpheus_collection_manifest.csv; budgets: Nyx's ledger)
# code, original file, short name, triangle budget, base colour size (px)
PIECES = [
    ("MO-00", "MO-00_Morpheus_Lamp.glb", "lamp", 15000, 1024),
    ("MO-01", "MO-01_Morpheus_Bedside_Table.glb", "bedside_table", 15000, 1024),
    ("MO-02", "MO-02_Morpheus_Armchair.glb", "armchair", 18000, 1024),
    ("MO-03", "MO-03_Morpheus_Dresser.glb", "dresser", 18000, 1024),
    ("MO-04", "MO-04_Morpheus_Tall_Cabinet.glb", "tall_cabinet", 18000, 1024),
    ("MO-05", "MO-05_Morpheus_Bed.glb", "bed", 24000, 2048),
    ("MO-06", "MO-06_Morpheus_Wall_Mirror.glb", "wall_mirror", 15000, 1024),
    ("MO-07", "MO-07_Morpheus_Writing_Desk.glb", "writing_desk", 18000, 1024),
    ("MO-08", "MO-08_Morpheus_Clock.glb", "clock", 15000, 512),
    ("MO-09", "MO-09_Morpheus_Hourglass.glb", "hourglass", 15000, 512),
    ("MO-10", "MO-10_Morpheus_Vase.glb", "vase", 15000, 512),
    ("MO-11", "MO-11_Morpheus_Rug.glb", "rug", 2000, 1024),           # a flat 12 mm slab: 2k triangles hold its edge; the texture is the rug
    ("MO-12", "MO-12_Morpheus_Textiles.glb", "textiles", 15000, 1024),
    # the Higgsfield props PLAN section 7 gives Morpheus (normalised to 1.9 m tall by the generator; `size` is the plan's W x H x D in metres)
    ("P6", "P6.glb", "sleeping_morpheus", 15000, 1024),
    ("P12", "P12.glb", "mask", 3500, 512),       # placed six times, each with its own lightmap texels: 3.5k each instead of the plan's 6k
]
PROP_SIZE = {"P6": (1.9, 1.1, 0.9), "P12": (0.35, 0.45, 0.2)}
PER_AXIS = set()


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
    mw = ob.matrix_world.copy()
    ob.parent = None
    ob.matrix_world = mw
    select_only([ob])
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for o in list(bpy.data.objects):
        if o is not ob and o.type != "MESH":
            bpy.data.objects.remove(o)
    return ob


def emission_from_base(mat):
    """Bake source: the original's base colour straight into an Emission shader (a diffuse-colour bake would give black on the gilt)."""
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
    """Small orthographic views of the copy, from +X, -X, +Y, -Y and the top (Blender), to read which way the piece faces."""
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
        diag = Vector(cp.dimensions).length
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
    me.uv_layers.new(name="UVMap")
    select_only([cp])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.002, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=3.0 / px, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    img = bpy.data.images.new(f"{code}_{name}_base", px, px, alpha=False)
    mat = bpy.data.materials.new(f"{SET}_{code}_{name}")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    bsdf.inputs["Roughness"].default_value = 0.7
    bsdf.inputs["Metallic"].default_value = 0.0
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
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    lo = Vector([min(v.co[i] for v in me.vertices) for i in range(3)])
    hi = Vector([max(v.co[i] for v in me.vertices) for i in range(3)])
    off = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    me.transform(Matrix.Translation(-off))
    img.filepath_raw = str(work() / f"{code}_{name}_base.jpg")
    img.file_format = "JPEG"
    sc.render.image_settings.quality = 90
    img.save()
    baked = bpy.data.images.load(str(work() / f"{code}_{name}_base.jpg"))
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
LAYOUT_PROPS = {"kind", "to_scene", "to_arrive", "hinge", "swing_deg", "state", "note", "base_w"}   # base_w: a light's build energy


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


# ================================================================ the hall (PLAN section 4.4)
VP_Y = -21.0                     # the vanishing point: every cross-section is the 6 x 3.2 m room scaled about (0, -21, 0)
HW0, H0 = 3.0, 3.2               # the "normal room": half-width and height at the door, s = 1
Y1 = 12.0 * math.log(2.5)        # the far wall's normalised depth (s = 2.5 at y = 9)
EYE = 0.95                       # the RDWE walker's eye at RDWE_SCALE 1.7 (controls.js: 1.62 / 1.7)
DOOR_W, DOOR_H = 0.94, 2.16
SPAWN = Vector((0.0, -8.3, 0.0))
SPLAY = math.atan(0.25)          # 14.04 degrees
CA, SA = math.cos(SPLAY), math.sin(SPLAY)
FW = math.degrees(SPLAY)         # the west pieces face 14 degrees north of east
FE = 180.0 - FW                  # the east pieces 14 degrees north of west


def s_of(y):
    return (y - VP_Y) / 12.0


def ceil_z(y):
    return H0 * s_of(y)


def P(X, Y, Z):
    """Normalised (X across, Y depth, Z up) -> Blender: the conformal map of the forced perspective."""
    s = math.exp(Y / 12.0)
    return Vector((X * s, 12.0 * s + VP_Y, Z * s))


def S_at(Y):
    return math.exp(Y / 12.0)


# each wall as (outward normal, distance): n . p = c on the wall's inner face
WALLS = {
    "W": (Vector((-CA, -SA, 0.0)), HW0 * CA + 9.0 * SA),
    "E": (Vector((CA, -SA, 0.0)), HW0 * CA + 9.0 * SA),
    "N": (Vector((0.0, 1.0, 0.0)), 9.0),
    "S": (Vector((0.0, -1.0, 0.0)), 9.0),
}

# which way each copy faces as made (read from the view sheets of the copies): the compass angle its front points to in Blender
NATIVE_FRONT = {"MO-00": 0, "MO-01": 0, "MO-02": 0, "MO-03": 0, "MO-04": 0, "MO-05": 0, "MO-06": 0, "MO-07": 0, "MO-08": 0, "MO-09": 0,
                "MO-10": 0, "MO-11": 0, "MO-12": 0, "P6": 270, "P12": 270}
if arg("--fronts"):
    for kv in arg("--fronts").split(","):
        k, v = kv.split("=")
        NATIVE_FRONT[k] = float(v)

# columns, sconces, masks, clerestory windows: normalised depths (evenly spaced in Y = evenly spaced as the eye reads them from the door)
COL_Y = [0.4, 3.8, 7.2, 10.6]                  # s = 1.03, 1.37, 1.82, 2.42 (the plan's 1.0x, 1.4x, 1.9x, 2.5x)
COL_SKIP = {("W", 3.8)}                        # the bed's headboard stands where the west 1.4x column would
SCONCE_Y = [2.1, 5.5]
MASK_Y = [7.95, 8.9, 9.85]
WIN_SIDE = [(7.45, 8.4), (8.65, 9.6), (9.85, 10.8)]
WIN_FAR = [(-2.55, -1.25), (-0.85, 0.85), (1.25, 2.55)]
WIN_SIDE_Z, WIN_FAR_Z = (2.6, 3.0), (2.15, 3.0)

# placement (PLAN 4.4): code, object name, (x, y), facing (compass degrees), how, scale, decimate-to
#   how: ("floor",), ("wall", wall, gap), ("hang", wall, gap, z of the bottom), ("on", support, (dx, dy))
PLACE = [
    ("MO-11", "MO-11_rug", (0.0, -6.2), 90.0, ("floor",), 1.0, None),
    ("MO-05", "MO-05_bed", (-2.91, -4.73), FW, ("wall", "W", 0.05), 1.0, None),
    ("MO-01", "MO-01_bedside_table_N", (-4.10, -3.78), FW, ("wall", "W", 0.05), 1.0, None),
    ("MO-01", "MO-01_bedside_table_S", (-3.51, -6.12), FW, ("wall", "W", 0.05), 1.0, None),
    ("MO-04", "MO-04_tall_cabinet", (-3.17, -6.88), FW, ("wall", "W", 0.05), 1.0, None),
    ("MO-03", "MO-03_dresser", (3.38, -6.12), FE, ("wall", "E", 0.05), 1.0, None),
    ("MO-06", "MO-06_wall_mirror", (3.64, -6.19), FE, ("hang", "E", 0.03, 1.02), 1.0, None),
    ("MO-07", "MO-07_writing_desk", (4.33, -2.53), FE, ("wall", "E", 0.05), 1.0, None),
    ("MO-02", "MO-02_armchair", (3.62, -2.38), FE - 180.0, ("floor",), 1.0, None),
    ("P6", "P6_sleeping_morpheus", (-4.0, -0.8), 0.0, ("floor",), 1.0, None),
    # the far end: copies of the same pieces, scaled (their own meshes, for their own lightmap texels)
    ("MO-04", "Cabinet_Far", (0.0, 8.2), 270.0, ("wall", "N", 0.06), 2.5, None),
    ("MO-03", "MO-03_dresser_far", (-5.65, 3.62), FW, ("wall", "W", 0.05), 1.6, 8000),
    ("MO-10", "MO-10_vase_far", (5.6, 4.6), 180.0, ("floor",), 2.2, 5000),
    # the smalls, on the furniture
    ("MO-00", "MO-00_lamp", (0.0, 0.0), FW, ("on", "MO-01_bedside_table_N", (0.0, 0.0)), 1.0, None),
    ("MO-10", "MO-10_vase", (0.0, 0.0), FW, ("on", "MO-01_bedside_table_S", (0.0, 0.0)), 1.0, None),
    ("MO-08", "MO-08_clock", (0.0, 0.0), FE, ("on", "MO-03_dresser", (0.0, -0.3)), 1.0, None),
    ("MO-09", "MO-09_hourglass", (0.0, 0.0), FE, ("on", "MO-07_writing_desk", (0.0, 0.32)), 1.0, None),
    ("MO-12", "MO-12_textiles", (0.0, 0.0), FW, ("on", "MO-05_bed", (0.55, 0.14)), 1.0, None),
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


def noise01(shape, r, seed, passes=2):
    rng = np.random.default_rng(seed)
    n = wrap_blur(rng.random(shape).astype(np.float32), r, passes)
    return (n - n.min()) / (n.max() - n.min() + 1e-9)


GOLD_S = np.array((0.86, 0.66, 0.30), np.float32)       # sRGB gilt for the painted lines
MAL_LIGHT = np.array((0.36, 0.74, 0.52), np.float32)     # light malachite (sRGB)
MAL_DARK = np.array((0.16, 0.52, 0.34), np.float32)


def malachite(H, W, seed, rings=34.0, light=MAL_LIGHT, dark=MAL_DARK, n_centres=7):
    """Seamless malachite: concentric bands round a few centres (toroidal distance), warped by noise."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    u, v = xx / W, yy / H
    warp = noise01((H, W), max(2, W // 24), seed + 1)
    d = np.full((H, W), 9.0, np.float32)
    for _ in range(n_centres):
        cx, cy = rng.random(), rng.random()
        du = np.minimum(np.abs(u - cx), 1 - np.abs(u - cx))
        dv = np.minimum(np.abs(v - cy), 1 - np.abs(v - cy)) * (H / W)
        d = np.minimum(d, np.hypot(du, dv) * rng.uniform(0.8, 1.2))
    f = d + 0.06 * warp
    band = 0.5 + 0.5 * np.sin(2 * math.pi * rings * f)
    band = band ** 1.6
    fine = noise01((H, W), 1, seed + 2, 1)
    t = np.clip(band * 0.85 + 0.15 * fine, 0, 1)[..., None]
    return dark * (1 - t) + light * t


def rect_line(img, Ufn, Vfn, u0, u1, z0, z1, w, col, rad=0.0):
    """A rounded-rectangle outline in the texture's own units (u across, z up), line width w."""
    H, W = img.shape[:2]
    uu, zz = Ufn, Vfn
    cu, cz = (u0 + u1) / 2, (z0 + z1) / 2
    hu, hz = (u1 - u0) / 2 - rad, (z1 - z0) / 2 - rad
    qx = np.maximum(np.abs(uu - cu) - hu, 0)
    qy = np.maximum(np.abs(zz - cz) - hz, 0)
    inside = np.minimum(np.maximum(np.abs(uu - cu) - hu, np.abs(zz - cz) - hz), 0)
    sd = np.hypot(qx, qy) + inside - rad
    a = np.clip(1 - np.abs(sd) / w, 0, 1)[..., None]
    img[:] = img * (1 - a) + col * a


def disc(img, Ufn, Vfn, cu, cz, r, col, soft=0.004):
    d = np.hypot(Ufn - cu, Vfn - cz)
    a = np.clip((r - d) / soft, 0, 1)[..., None]
    img[:] = img * (1 - a) + col * a


def poppy(img, Ufn, Vfn, cu, cz, r, seed, red=(0.82, 0.12, 0.06)):
    """A poppy: five overlapping round petals, a dark centre."""
    rng = np.random.default_rng(seed)
    a0 = rng.uniform(0, 2 * math.pi)
    for k in range(5):
        a = a0 + 2 * math.pi * k / 5
        disc(img, Ufn, Vfn, cu + 0.45 * r * math.cos(a), cz + 0.45 * r * math.sin(a), 0.62 * r, np.array(red) * rng.uniform(0.85, 1.05))
    disc(img, Ufn, Vfn, cu, cz, 0.24 * r, np.array((0.08, 0.06, 0.05)))


WALL_U, WALL_V = 2.0, 3.2        # the wall tile covers 2.0 m across and the full normalised height


def wall_pixels():
    """The malachite panelling, one bay (2.0 normalised metres) by the full height: skirting, a dado panel, the dado rail, a tall panel in a
    gilt rococo frame, a darker frieze with gilt-ringed poppy roundels (the poppies of the set), the cornice."""
    H, W = 1024, 640
    img = malachite(H, W, 11)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    U = (xx + 0.5) / W * WALL_U
    Z = (1 - (yy + 0.5) / H) * WALL_V
    sk = Z < 0.15
    img[sk] = np.array((0.06, 0.22, 0.14)) * (0.8 + 0.4 * noise01((H, W), 3, 5)[sk][..., None])
    fr = (Z > 2.55) & (Z < 3.05)
    img[fr] = img[fr] * 0.72
    img[(Z >= 0.85) & (Z <= 0.92)] = GOLD_S
    img[Z >= 3.02] = GOLD_S
    rect_line(img, U, Z, 0.12, 1.88, 0.24, 0.76, 0.012, GOLD_S, 0.04)
    rect_line(img, U, Z, 0.16, 1.84, 1.05, 2.45, 0.018, GOLD_S, 0.16)
    rect_line(img, U, Z, 0.24, 1.76, 1.13, 2.37, 0.007, GOLD_S, 0.12)
    for cu in (0.5, 1.5):
        disc(img, U, Z, cu, 2.80, 0.15, GOLD_S)
        disc(img, U, Z, cu, 2.80, 0.13, np.array((0.07, 0.25, 0.16)))
        poppy(img, U, Z, cu, 2.80, 0.10, int(cu * 10))
    for cu in (0.0, 1.0, 2.0):        # a gilt diamond between the roundels
        d = np.abs(U - cu) / 0.10 + np.abs(Z - 2.80) / 0.10
        img[d < 1] = GOLD_S
    return np.clip(img, 0, 1)


def floor_pixels():
    """The floor, a tile of 1.2 x 1.2 normalised metres: a checker of cream marble and malachite squares 0.6 across, with a gilt seam; the
    squares grow toward the far end with the rest of the hall."""
    S = 1024
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    n1 = noise01((S, S), 20, 21)
    n2 = noise01((S, S), 5, 22)
    cream = np.array((0.88, 0.84, 0.74)) * (0.9 + 0.15 * n1)[..., None]
    f = n1 * 7.0 + n2 * 1.4
    vein = np.clip(1 - np.abs((f % 1.0) - 0.5) / 0.02, 0, 1) * (n2 > 0.4)
    cream = cream * (1 - 0.35 * vein[..., None]) + np.array((0.55, 0.52, 0.48)) * 0.35 * vein[..., None]
    mal = malachite(S, S, 23, rings=26.0, light=np.array((0.30, 0.66, 0.46)), dark=np.array((0.09, 0.38, 0.24)))
    chk = ((xx // (S / 2)) + (yy // (S / 2))) % 2 == 0
    img = np.where(chk[..., None], cream, mal).astype(np.float32)
    edge = np.minimum(np.minimum(xx % (S / 2), (S / 2) - xx % (S / 2)), np.minimum(yy % (S / 2), (S / 2) - yy % (S / 2)))
    a = np.clip(1 - (edge - 3) / 2.0, 0, 1)[..., None]
    img = img * (1 - a) + GOLD_S * a
    return np.clip(img, 0, 1)


def ceiling_pixels():
    """The painted ceiling, a tile of 1.7 normalised metres: deep green with a gilt diamond lattice and a poppy at each crossing."""
    S = 512
    img = malachite(S, S, 31, rings=18.0, light=np.array((0.24, 0.50, 0.36)), dark=np.array((0.10, 0.30, 0.20)))
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    U, V = (xx + 0.5) / S, (yy + 0.5) / S
    for d in (U + V, U - V):
        g = np.abs(((d * 2) % 1.0) - 0.5)
        a = np.clip(1 - (0.5 - g) / 0.012, 0, 1)[..., None]
        img = img * (1 - a) + GOLD_S * a
    for cu, cv in ((0, 0), (1, 0), (0, 1), (1, 1), (0.5, 0.5)):
        disc(img, U, V, cu, cv, 0.07, GOLD_S)
        poppy(img, U, V, cu, cv, 0.05, int(cu * 7 + cv * 3))
    return np.clip(img, 0, 1)


def column_pixels():
    return np.clip(malachite(512, 512, 41, rings=22.0, light=np.array((0.24, 0.62, 0.42)), dark=np.array((0.05, 0.30, 0.18))), 0, 1)


def poppy_glass_pixels(H=512, W=512, seed=51, n_poppies=6):
    """Tiffany poppy glass: amber and honey panes in dark leading, red poppies, green stems and leaves."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    U, V = (xx + 0.5) / W, (1 - (yy + 0.5) / H) * (H / W)
    img = np.zeros((H, W, 3), np.float32)
    grad = (yy / H)[..., None]
    img[:] = np.array((1.0, 0.82, 0.42)) * (1 - grad) + np.array((0.95, 0.58, 0.22)) * grad
    pts = rng.random((70, 2)) * np.array((1.0, H / W))
    d1 = np.full((H, W), 9.0, np.float32)
    d2 = np.full((H, W), 9.0, np.float32)
    shade = np.zeros((H, W), np.float32)
    for k, (px, py) in enumerate(pts):
        d = np.hypot(U - px, V - py)
        closer = d < d1
        d2 = np.where(closer, d1, np.minimum(d2, d))
        shade = np.where(closer, rng.uniform(0.82, 1.08), shade)
        d1 = np.where(closer, d, d1)
    img *= shade[..., None]
    for k in range(n_poppies):
        cu, cv = rng.uniform(0.12, 0.88), rng.uniform(0.15, H / W - 0.12)
        r = rng.uniform(0.07, 0.11)
        stem_a = np.clip(1 - np.abs(U - cu - 0.04 * np.sin((V - cv) * 9)) / 0.008, 0, 1) * (V < cv)
        img = img * (1 - stem_a[..., None]) + np.array((0.22, 0.48, 0.16)) * stem_a[..., None]
        for side in (-1, 1):
            disc(img, U, V, cu + side * 0.05, cv - 0.12, 0.035, np.array((0.25, 0.55, 0.20)))
        poppy(img, U, V, cu, cv, r, seed + k)
    lead = np.clip(1 - (d2 - d1) / 0.006, 0, 1)
    img = img * (1 - 0.85 * lead[..., None]) + np.array((0.06, 0.05, 0.04)) * 0.85 * lead[..., None]
    return np.clip(img, 0, 1)


def door_in_pixels():
    """The way in: a malachite door leaf with two gilt panels."""
    H, W = 512, 224
    img = malachite(H, W, 61, rings=20.0)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    U = (xx + 0.5) / W * DOOR_W
    Z = (1 - (yy + 0.5) / H) * DOOR_H
    rect_line(img, U, Z, 0.02, DOOR_W - 0.02, 0.02, DOOR_H - 0.02, 0.012, GOLD_S, 0.0)
    rect_line(img, U, Z, 0.14, DOOR_W - 0.14, 0.15, 0.85, 0.010, GOLD_S, 0.05)
    rect_line(img, U, Z, 0.14, DOOR_W - 0.14, 1.02, 1.98, 0.010, GOLD_S, 0.08)
    disc(img, U, Z, DOOR_W - 0.10, 1.0, 0.025, GOLD_S)
    return np.clip(img, 0, 1)


CAB_LEAF_W, CAB_LEAF_H, CAB_LEAF_Z = 0.6, 2.14, 2.0       # H and Z are set from the placed cabinet (build_cabinet_doors)


def cabinet_leaf_pixels():
    """One of the giant wardrobe's two doors: poppy glass in a gilt frame with two glazing bars."""
    H, W = 1024, 192
    img = poppy_glass_pixels(H, W, 71, 4)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    U = (xx + 0.5) / W * CAB_LEAF_W
    Z = (1 - (yy + 0.5) / H) * CAB_LEAF_H
    frame = (U < 0.05) | (U > CAB_LEAF_W - 0.05) | (Z < 0.06) | (Z > CAB_LEAF_H - 0.06)
    for zb in (CAB_LEAF_H / 3, 2 * CAB_LEAF_H / 3):
        frame |= np.abs(Z - zb) < 0.025
    img[frame] = GOLD_S * (0.85 + 0.25 * noise01((H, W), 2, 72)[frame][..., None])
    return np.clip(img, 0, 1)


def placard_pixels():
    """The museum placard by the entrance (PLAN 2.2): cream letters on malachite-black, a gold rule."""
    W, H = 768, 512
    img = np.zeros((H, W, 3), np.float32)
    img[:] = (0.03, 0.06, 0.045)
    img[18:24, 30:W - 30] = img[H - 24:H - 18, 30:W - 30] = GOLD_S
    draw_text(img, "MORPHEUS", (40, 170, 0, W), (0.93, 0.88, 0.74), 0.85)
    draw_text(img, "DREAMS - THE SHAPING HALL", (190, 270, 0, W), (0.86, 0.66, 0.30), 0.92)
    draw_text(img, "NINETY-NINE NOCTURNE SUITE", (290, 370, 0, W), (0.80, 0.76, 0.66), 0.92)
    draw_text(img, "XIII PIECES. MALACHITE. GILT. POPPY GLASS.", (380, 460, 0, W), (0.62, 0.58, 0.52), 0.95)
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


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


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, img=None, emit=None, emit_img=None, double=False):
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
        if emit_img:
            nt.links.new(n.outputs["Color"], bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = emit_img
    if emit is not None:
        bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    m.use_backface_culling = not double
    MATS[name] = m
    return m


def make_materials(gen):
    material("Floor_Marble", img=gen["floor"], rough=0.3)
    material("Wall_Malachite", img=gen["wall"], rough=0.35)
    material("Ceiling_Painted", img=gen["ceiling"], rough=0.8)
    material("Column_Malachite", img=gen["column"], rough=0.2)
    material("Gold_Trim", color=(0.50, 0.34, 0.11), rough=0.35, metal=0.9)
    material("Trim_Dark", color=(0.012, 0.03, 0.02), rough=0.5)
    material("Door_Malachite", img=gen["door"], rough=0.35)
    material("Cabinet_Door", img=gen["leaf"], rough=0.3)
    material("Placard", img=gen["placard"], rough=0.5)
    material("Poppy_Glass", img=gen["glass"], emit_img=2.2, rough=0.2)        # the clerestory: lit from outside, so it glows
    material("Cabinet_Light", color=(1.0, 0.8, 0.5), emit=((1.0, 0.72, 0.42), 9.0))   # the light inside the wardrobe, through the crack
    material("Picture_Light_Emit", color=(1.0, 0.9, 0.7), emit=((1.0, 0.85, 0.6), 4.0))
    material("Sconce_Gilt", color=(0.62, 0.42, 0.14), rough=0.35, metal=0.9)       # not baked: inches from its own bulb
    material("Lamp_Emit", color=(1.0, 0.85, 0.6), emit=((1.0, 0.62, 0.30), 8.0))


# ---------------------------------------------------------------- geometry helpers (Blender coordinates)
ART = LAYOUT = None


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


def surf(bm, fn, A, B, na, nb, uvfn, want, skip=None):
    """A grid surface: fn(a, b) -> a Blender point; uvfn(a, b) -> UV; `want(centre)` the side the faces must look to."""
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    for i in range(na):
        for j in range(nb):
            a0, a1 = A[0] + (A[1] - A[0]) * i / na, A[0] + (A[1] - A[0]) * (i + 1) / na
            b0, b1 = B[0] + (B[1] - B[0]) * j / nb, B[0] + (B[1] - B[0]) * (j + 1) / nb
            if skip and skip((a0 + a1) / 2, (b0 + b1) / 2):
                continue
            cs = [(a0, b0), (a1, b0), (a1, b1), (a0, b1)]
            vs = [bm.verts.new(fn(a, b)) for a, b in cs]
            f = bm.faces.new(vs)
            f.normal_update()
            if f.normal.dot(want(f.calc_center_median())) < 0:
                f.normal_flip()
            for lp in f.loops:
                lp[uvl].uv = uvfn(*cs[vs.index(lp.vert)])


def weld(bm):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)


SIDE = {"W": -1.0, "E": 1.0}


def build_shell():
    NY = 36
    # floor: the checker in normalised coordinates, so the squares grow with the hall
    bm = bmesh.new()
    surf(bm, lambda X, Y: P(X, Y, 0.0), (-HW0, HW0), (0.0, Y1), 12, NY, lambda X, Y: (X / 1.2, Y / 1.2), lambda c: Vector((0, 0, 1)))
    weld(bm)
    mesh_obj("Floor", bm, "Floor_Marble")
    bm = bmesh.new()
    surf(bm, lambda X, Y: P(X, Y, H0), (-HW0, HW0), (0.0, Y1), 12, NY, lambda X, Y: (X / 1.7, Y / 1.7), lambda c: Vector((0, 0, -1)))
    weld(bm)
    mesh_obj("Ceiling", bm, "Ceiling_Painted")
    # walls: the two splayed walls, the far wall, the near wall round the door
    bm = bmesh.new()
    for side, sx in SIDE.items():
        surf(bm, lambda Y, Z, sx=sx: P(sx * HW0, Y, Z), (0.0, Y1), (0.0, H0), NY, 2, lambda Y, Z: (Y / WALL_U, Z / WALL_V),
             lambda c, sx=sx: Vector((-sx, 0, 0)))
    surf(bm, lambda X, Z: P(X, Y1, Z), (-HW0, HW0), (0.0, H0), 6, 2, lambda X, Z: (X / WALL_U + 0.5, Z / WALL_V), lambda c: Vector((0, -1, 0)))
    for X0, X1, Z0, Z1 in ((-HW0, -0.62, 0.0, H0), (0.62, HW0, 0.0, H0), (-0.62, 0.62, 2.45, H0)):
        surf(bm, lambda X, Z: P(X, 0.0, Z), (X0, X1), (Z0, Z1), max(1, round((X1 - X0) / 0.6)), 2, lambda X, Z: (X / WALL_U + 0.5, Z / WALL_V),
             lambda c: Vector((0, 1, 0)))
    weld(bm)
    mesh_obj("Walls", bm, "Wall_Malachite")
    # gilt mouldings that run round the hall: the dado rail and the cornice, proud of the walls by d (normalised), growing with s
    bm = bmesh.new()
    for Z0, Z1, d in ((0.85, 0.92, 0.025), (3.02, H0, 0.07)):
        for side, sx in SIDE.items():
            Xi = sx * (HW0 - d)
            surf(bm, lambda Y, Z, Xi=Xi: P(Xi, Y, Z), (0.0, Y1), (Z0, Z1), NY, 1, lambda a, b: (a, b), lambda c, sx=sx: Vector((-sx, 0, 0)))
            for Z, up in ((Z1, 1), (Z0, -1)):
                if Z >= H0:
                    continue
                surf(bm, lambda Y, t, Z=Z, sx=sx: P(sx * (HW0 - d * t), Y, Z), (0.0, Y1), (0.0, 1.0), NY, 1, lambda a, b: (a, b),
                     lambda c, up=up: Vector((0, 0, up)))
        surf(bm, lambda X, Z: P(X, Y1 - d, Z), (-HW0, HW0), (Z0, Z1), 6, 1, lambda a, b: (a, b), lambda c: Vector((0, -1, 0)))
        if Z1 < H0:
            for Z, up in ((Z1, 1), (Z0, -1)):
                surf(bm, lambda X, t, Z=Z: P(X, Y1 - d * t, Z), (-HW0, HW0), (0.0, 1.0), 6, 1, lambda a, b: (a, b), lambda c, up=up: Vector((0, 0, up)))
        spans = [(-HW0, -0.68), (0.68, HW0)] if Z1 < 2.5 else [(-HW0, HW0)]
        for X0, X1 in spans:
            surf(bm, lambda X, Z: P(X, d, Z), (X0, X1), (Z0, Z1), 3, 1, lambda a, b: (a, b), lambda c: Vector((0, 1, 0)))
            if Z1 < H0:
                for Z, up in ((Z1, 1), (Z0, -1)):
                    surf(bm, lambda X, t, Z=Z: P(X, d * t, Z), (X0, X1), (0.0, 1.0), 3, 1, lambda a, b: (a, b), lambda c, up=up: Vector((0, 0, up)))
    weld(bm)
    mesh_obj("Gilt_Mouldings", bm, "Gold_Trim")


def wall_in(side):
    """The inward unit normal of a splayed wall."""
    n, _ = WALLS[side]
    return -n


def column_at(side, Y):
    """Where a column stands: its plinth's back on the wall, at normalised depth Y; returns the base point, the scale and the inward normal."""
    sx = SIDE[side]
    k = S_at(Y)
    base = P(sx * (HW0 - 0.21), Y, 0.0)
    return base, k, wall_in(side)


def fluted_shaft(bm, M, z0, z1, r0, r1, n=20):
    rings = []
    for z, r in ((z0, r0), (z1, r1)):
        ring = []
        for i in range(2 * n):
            a = math.pi * i / n
            f = 1.0 if i % 2 == 0 else 0.92
            ring.append(bm.verts.new(M @ Vector((r * f * math.cos(a), r * f * math.sin(a), z))))
        rings.append(ring)
    m = len(rings[0])
    for i in range(m):
        f = bm.faces.new([rings[0][i], rings[0][(i + 1) % m], rings[1][(i + 1) % m], rings[1][i]])
        f.normal_update()
        c = f.calc_center_median()
        ax = M @ Vector((0, 0, (z0 + z1) / 2))
        if f.normal.dot(c - Vector((ax.x, ax.y, c.z))) < 0:
            f.normal_flip()


def build_columns():
    """Ionic columns (P16 in the plan, modelled here): a malachite fluted shaft on a gilt base, a gilt capital with volute bolsters. One unit
    column, 2.55 normalised metres to the top of the abacus, scaled by s where it stands, so the four pairs read as one even colonnade."""
    shafts, gilt = bmesh.new(), bmesh.new()
    placed = []
    for Y in COL_Y:
        for side in SIDE:
            if (side, Y) in COL_SKIP:
                continue
            base, k, n_in = column_at(side, Y)
            yaw = math.atan2(n_in.y, n_in.x)
            M = Matrix.Translation(base) @ Matrix.Rotation(yaw, 4, "Z") @ Matrix.Scale(k, 4)
            fluted_shaft(shafts, M, 0.21, 2.30, 0.16, 0.135)
            add_box(gilt, M @ Vector((0, 0, 0.06)), (0.42 * k, 0.42 * k, 0.12 * k), yaw)
            add_cyl(gilt, M @ Vector((0, 0, 0.12)), M @ Vector((0, 0, 0.17)), 0.19 * k, 0.19 * k, seg=20)
            add_cyl(gilt, M @ Vector((0, 0, 0.17)), M @ Vector((0, 0, 0.21)), 0.17 * k, 0.16 * k, seg=20)
            add_cyl(gilt, M @ Vector((0, 0, 2.30)), M @ Vector((0, 0, 2.38)), 0.14 * k, 0.18 * k, seg=20)
            for sy in (-1, 1):
                add_cyl(gilt, M @ Vector((-0.18, sy * 0.17, 2.42)), M @ Vector((0.20, sy * 0.17, 2.42)), 0.065 * k, seg=12)
                add_cyl(gilt, M @ Vector((0.20, sy * 0.17, 2.42)), M @ Vector((0.215, sy * 0.17, 2.42)), 0.045 * k, seg=12)
            add_box(gilt, M @ Vector((0, 0, 2.49)), (0.42 * k, 0.42 * k, 0.06 * k), yaw)
            placed.append((side, Y, base, k))
    box_uv(shafts, 0.5)
    mesh_obj("Column_Shafts", shafts, "Column_Malachite", smooth=True)
    box_uv(gilt, 1.0)
    mesh_obj("Column_Gilt", gilt, "Gold_Trim", smooth=False)
    return placed


def build_entrance():
    """The way in on the south wall: a gilt frame round a malachite door (DoorLeaf_Morpheus_In, origin on its west edge, closed)."""
    y = -9.0
    bm = bmesh.new()
    for x in (-0.565, 0.565):
        add_box(bm, Vector((x, y + 0.03, 1.2)), (0.12, 0.08, 2.40))
    add_box(bm, Vector((0, y + 0.03, 2.40)), (1.30, 0.10, 0.10))
    box_uv(bm, 1.0)
    mesh_obj("Door_Frame_In", bm, "Gold_Trim")
    bm = bmesh.new()
    add_box(bm, Vector((0, y - 0.11, 1.22)), (1.30, 0.02, 2.44))
    box_uv(bm, 1.0)
    mesh_obj("Door_Reveal_In", bm, "Trim_Dark")
    bm = bmesh.new()
    add_box(bm, Vector((DOOR_W / 2, 0.0, DOOR_H / 2)), (DOOR_W, 0.045, DOOR_H))
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for lp in f.loops:
            lp[uvl].uv = (lp.vert.co.x / DOOR_W, lp.vert.co.z / DOOR_H)
    ob = mesh_obj("DoorLeaf_Morpheus_In", bm, "Door_Malachite")
    ob.location = (-DOOR_W / 2, y + 0.05, 0.0)


PLACARD_C = Vector((1.25, -9.0 + 0.012, 1.0))


def build_placard():
    bm = bmesh.new()
    c = PLACARD_C
    w, h = 0.42, 0.28
    vs = [bm.verts.new(c + Vector(d)) for d in ((-w / 2, 0, -h / 2), (w / 2, 0, -h / 2), (w / 2, 0, h / 2), (-w / 2, 0, h / 2))]
    f = bm.faces.new(vs)
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp, t in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = t
    f.normal_update()
    if f.normal.y < 0:
        f.normal_flip()
    mesh_obj("Placard", bm, "Placard")
    bm = bmesh.new()
    add_box(bm, c + Vector((0, -0.004, 0)), (w + 0.03, 0.008, h + 0.03))
    box_uv(bm, 1.0)
    mesh_obj("Placard_Frame", bm, "Gold_Trim")
    bm = bmesh.new()
    top = c + Vector((0, 0, h / 2 + 0.06))
    add_cyl(bm, top + Vector((0, -0.004, 0)), top + Vector((0, 0.16, 0.05)), 0.008, seg=8)
    head = top + Vector((0, 0.16, 0.05))
    add_cyl(bm, head - Vector((0.17, 0, 0)), head + Vector((0.17, 0, 0)), 0.022, seg=10)
    box_uv(bm, 1.0)
    mesh_obj("Placard_Light", bm, "Sconce_Gilt", smooth=True)
    bm = bmesh.new()
    add_box(bm, head + Vector((0, -0.004, -0.023)), (0.30, 0.012, 0.004))
    box_uv(bm, 1.0)
    mesh_obj("Placard_Light_Glow", bm, "Picture_Light_Emit")


SCONCE_Z = 2.1
SCONCE_BULBS = []


def build_sconces():
    """Gilt rococo sconces, one pair per bay in the near half, scaled by s: a wall plate, an arm curving out and up to a cup, a glowing bulb."""
    gold, bulbs = bmesh.new(), bmesh.new()
    SCONCE_BULBS.clear()
    for Y in SCONCE_Y:
        for side, sx in SIDE.items():
            k = S_at(Y)
            n = WALLS[side][0]
            w = P(sx * HW0, Y, SCONCE_Z)
            plate = w - n * 0.012 * k
            m = Matrix.Translation(plate) @ Matrix.Rotation(math.atan2(n.y, n.x), 4, "Z") @ Matrix.Diagonal((0.024 * k, 0.11 * k, 0.26 * k, 1))
            bmesh.ops.create_cube(gold, size=1.0, matrix=m)
            pts = []
            for i in range(9):
                t = i / 8
                out_d = 0.04 + 0.20 * math.sin(t * math.pi * 0.6)
                up = -0.06 + 0.12 * t * t
                pts.append(plate - n * out_d * k + Vector((0, 0, up * k)))
            for i in range(8):
                add_cyl(gold, pts[i], pts[i + 1], (0.016 - 0.004 * i / 8) * k, (0.016 - 0.004 * (i + 1) / 8) * k, seg=8)
            cup = pts[-1]
            add_cyl(gold, cup + Vector((0, 0, -0.02 * k)), cup + Vector((0, 0, 0.03 * k)), 0.022 * k, 0.04 * k, seg=10)
            bc = cup + Vector((0, 0, 0.085 * k))
            bmesh.ops.create_uvsphere(bulbs, u_segments=10, v_segments=6, radius=1.0,
                                      matrix=Matrix.Translation(bc) @ Matrix.Diagonal((0.03 * k, 0.03 * k, 0.055 * k, 1)))
            SCONCE_BULBS.append((bc, k))
    box_uv(gold, 1.0)
    mesh_obj("Sconces", gold, "Sconce_Gilt", smooth=True)
    box_uv(bulbs, 1.0)
    mesh_obj("Sconce_Bulbs", bulbs, "Lamp_Emit", smooth=True)


WINDOWS = []          # (centre, inward normal, width, height) of each clerestory pane, for the lights


def build_clerestory():
    """The clerestory of poppy glass that lights the far end: three panes high on each splayed wall and three on the far wall, in gilt frames,
    a hair proud of the walls (each pane maps the whole picture)."""
    glass, frame = bmesh.new(), bmesh.new()
    uvl = glass.loops.layers.uv.new("UVMap")
    WINDOWS.clear()

    def pane(fn, A, B, want):
        vs = [glass.verts.new(fn(a, b)) for a, b in ((A[0], B[0]), (A[1], B[0]), (A[1], B[1]), (A[0], B[1]))]
        f = glass.faces.new(vs)
        f.normal_update()
        if f.normal.dot(want) < 0:
            f.normal_flip()
        for lp in f.loops:
            i = vs.index(lp.vert)
            u = 1.0 if i in (1, 2) else 0.0
            v = 1.0 if i in (2, 3) else 0.0
            if want.x > 0.5 or want.y < -0.5:            # the west wall and the far wall see the panes from the other side: keep the picture upright
                pass
            lp[uvl].uv = (u, v)
        c = sum((v.co for v in vs), Vector()) / 4
        WINDOWS.append((c, want.normalized(), (vs[1].co - vs[0].co).length, (vs[3].co - vs[0].co).length))
        # the frame: four bars round the pane
        e = [v.co.copy() for v in vs]
        for i in range(4):
            a, b = e[i], e[(i + 1) % 4]
            k = (c.y + 21.0) / 12.0
            add_cyl(frame, a + want * 0.01 * k, b + want * 0.01 * k, 0.03 * k, seg=6)
    for side, sx in SIDE.items():
        for Ya, Yb in WIN_SIDE:
            pane(lambda Y, Z, sx=sx: P(sx * (HW0 - 0.008), Y, Z), (Ya, Yb), WIN_SIDE_Z, Vector((-sx, 0, 0)))
    for Xa, Xb in WIN_FAR:
        pane(lambda X, Z: P(X, Y1 - 0.008, Z), (Xa, Xb), WIN_FAR_Z, Vector((0, -1, 0)))
    mesh_obj("Clerestory_Glass", glass, "Poppy_Glass")
    box_uv(frame, 1.0)
    mesh_obj("Clerestory_Frames", frame, "Gold_Trim", smooth=True)


# ---------------------------------------------------------------- the furniture
def yaw_for(code, facing):
    return math.radians(facing - NATIVE_FRONT[code])


def load_copy(code, objname):
    key = f"{code}_mesh"
    if key in bpy.data.meshes:
        me = bpy.data.meshes[key].copy()              # its own mesh: each placed piece needs its own lightmap texels
        me.name = f"{objname}_mesh"
        ob = bpy.data.objects.new(objname, me)
        ART.objects.link(ob)
        return ob
    path = next(COPIES.glob(f"{code}_*_game.glb"))
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
    ob.data.name = f"{objname}_mesh"
    ob.matrix_world = Matrix.Identity(4)
    for m in ob.data.materials:
        if m.node_tree:
            for nd in m.node_tree.nodes:
                if nd.type == "TEX_IMAGE" and nd.image:
                    nd.image.pack()
    keep = ob.data.copy()                             # an untouched copy for the later placings (this one may be decimated)
    keep.name = key
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


def decimate_to(ob, target):
    n = tri_count(ob)
    if target >= n:
        return
    mod = ob.modifiers.new("dec", "DECIMATE")
    mod.decimate_type = "COLLAPSE"
    mod.ratio = target / n
    mod.use_collapse_triangulate = True
    select_only([ob])
    bpy.ops.object.modifier_apply(modifier=mod.name)
    print(f"  {ob.name} decimated {n} -> {tri_count(ob)}")


def snap_to_wall(ob, wall, gap):
    n, c = WALLS[wall]
    reach = max(v.dot(n) for v in world_verts(ob))
    ob.location = Vector(ob.location) + n * (c - gap - reach)


def place_all():
    placed = {}
    for code, objname, xy, facing, how, scale, dec in PLACE:
        ob = load_copy(code, objname)
        if dec:
            decimate_to(ob, dec)
        ob.rotation_mode = "XYZ"
        ob.rotation_euler = (0, 0, yaw_for(code, facing))
        ob.scale = (scale, scale, scale)
        ob.location = (xy[0], xy[1], 0.0)
        bpy.context.view_layer.update()
        if how[0] in ("wall", "hang"):
            snap_to_wall(ob, how[1], how[2])
            if how[0] == "hang":
                ob.location.z = how[3]
        elif how[0] == "on":
            sup = placed[how[1]]
            bpy.context.view_layer.update()
            sv = world_verts(sup)
            cx = (min(v.x for v in sv) + max(v.x for v in sv)) / 2
            cy = (min(v.y for v in sv) + max(v.y for v in sv)) / 2
            sx, sy = how[2]
            tgt = Vector((cx + sx, cy + sy, 0))
            hit = bvh_of(sup).ray_cast(Vector((tgt.x, tgt.y, 6.0)), Vector((0, 0, -1)))
            top = hit[0].z if hit[0] is not None else max(v.z for v in sv)
            ob.location = (tgt.x, tgt.y, top - 0.003)
        bpy.context.view_layer.update()
        placed[objname] = ob
        vs = world_verts(ob)
        lo = [min(v[i] for v in vs) for i in range(3)]
        hi = [max(v[i] for v in vs) for i in range(3)]
        print(f"PLACE {objname}: ({lo[0]:.2f}, {lo[1]:.2f}, {lo[2]:.2f}) .. ({hi[0]:.2f}, {hi[1]:.2f}, {hi[2]:.2f})  tris {tri_count(ob)}")
    # the masks (P12): three on each splayed wall between the far columns, scaled by s, eyes closed, facing into the hall
    i = 0
    for side, sx in SIDE.items():
        for Y in MASK_Y:
            k = S_at(Y)
            ob = load_copy("P12", f"decor_mask_{i}")
            ob.rotation_mode = "XYZ"
            n_in = wall_in(side)
            ob.rotation_euler = (0, 0, yaw_for("P12", math.degrees(math.atan2(n_in.y, n_in.x))))
            ob.scale = (k, k, k)
            c = P(sx * HW0, Y, 1.75)
            ob.location = (c.x, c.y, 0.0)
            bpy.context.view_layer.update()
            snap_to_wall(ob, side, 0.0)
            ob.location.z = c.z - 0.225 * k
            bpy.context.view_layer.update()
            placed[ob.name] = ob
            print(f"PLACE {ob.name}: centre ({c.x:.2f}, {c.y:.2f}, {c.z:.2f}) scale {k:.2f}")
            i += 1
    return placed


CAB = {}


def build_cabinet_doors(placed):
    """The giant wardrobe's doors (PLAN 4.4: 1.2 x 3.6 m, two leaves hinged on the cabinet's sides), open a crack, with the light inside
    showing through: DoorLeaf_Morpheus_Cabinet_L / _R, each with its origin on its hinge, and a glowing panel behind them."""
    global CAB_LEAF_Z, CAB_LEAF_H
    cab = placed["Cabinet_Far"]
    vs = world_verts(cab)
    top = max(v.z for v in vs)
    # the leaves go over the cabinet's own glazed doors (its upper section, 0.42 to 0.87 of its height), not over the bombe base below
    CAB_LEAF_Z, CAB_LEAF_H = 0.42 * top, 0.45 * top
    glass = [v for v in vs if CAB_LEAF_Z + 0.3 < v.z < CAB_LEAF_Z + CAB_LEAF_H - 0.3 and abs(v.x) < 0.6]
    front = min(v.y for v in glass) - 0.015
    CAB["front"] = min(v.y for v in vs if v.z < CAB_LEAF_Z and abs(v.x) < 1.0)     # the bombe base's front: the zone and the link are before it
    CAB["leaf_y"] = front
    CAB["back"] = max(v.y for v in vs)
    CAB["half_w"] = (max(v.x for v in vs) - min(v.x for v in vs)) / 2
    CAB["top"] = top
    print(f"CABINET top {top:.2f}, base front {CAB['front']:.2f}, leaves at y {front:.2f}, z {CAB_LEAF_Z:.2f} .. {CAB_LEAF_Z + CAB_LEAF_H:.2f}")
    bm = bmesh.new()
    add_box(bm, Vector((0, front + 0.04, CAB_LEAF_Z + CAB_LEAF_H / 2)), (2 * CAB_LEAF_W - 0.02, 0.02, CAB_LEAF_H))
    box_uv(bm, 1.0)
    glow = mesh_obj("Cabinet_Glow", bm, "Cabinet_Light")
    for tag, sx, ang in (("L", -1, -7.0), ("R", 1, 7.0)):
        bm = bmesh.new()
        add_box(bm, Vector((-sx * CAB_LEAF_W / 2, 0.0, CAB_LEAF_H / 2)), (CAB_LEAF_W, 0.04, CAB_LEAF_H))
        uvl = bm.loops.layers.uv.new("UVMap")
        for f in bm.faces:
            for lp in f.loops:
                u = (lp.vert.co.x + (CAB_LEAF_W if sx > 0 else 0)) / CAB_LEAF_W
                lp[uvl].uv = (u if sx < 0 else u, lp.vert.co.z / CAB_LEAF_H)
        ob = mesh_obj(f"DoorLeaf_Morpheus_Cabinet_{tag}", bm, "Cabinet_Door")
        ob.location = (sx * CAB_LEAF_W, front, CAB_LEAF_Z)
        ob.rotation_euler = (0, 0, math.radians(ang))
    return glow


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


def build_layout(placed, columns):
    """COL_ boxes: the floor; each splayed wall as a row of 0.5 m boxes along its line (as tall as the ceiling there); the far wall; the near
    wall in three round the door; a box per standing piece and per column. Markers, links, zones as PLAN 4.4."""
    col_box("COL_floor", (-7.6, -9.2, -0.2), (7.6, 9.2, 0.0))
    for side, sx in SIDE.items():
        n, c = WALLS[side]
        a = Vector((sx * 3.0, -9.0, 0))
        b = Vector((sx * 7.5, 9.0, 0))
        L = (b - a).length
        m = int(math.ceil(L / 0.5))
        for i in range(m):
            p = a.lerp(b, (i + 0.5) / m) + n * 0.25
            top = ceil_z(min(9.0, p.y + 0.3))
            col_box(f"COL_wall_{side}_{i:02d}", (p.x - 0.25, p.y - 0.25, 0), (p.x + 0.25, p.y + 0.25, top))
    col_box("COL_wall_N", (-7.7, 9.0, 0), (7.7, 9.25, 8.0))
    col_box("COL_wall_S_a", (-3.2, -9.25, 0), (-0.47, -9.0, H0))
    col_box("COL_wall_S_b", (0.47, -9.25, 0), (3.2, -9.0, H0))
    col_box("COL_wall_S_head", (-0.47, -9.25, DOOR_H), (0.47, -9.0, H0))
    skip = ("MO-00", "MO-08", "MO-09", "MO-10_vase", "MO-12", "MO-11", "MO-06", "decor_mask_")
    for nm, ob in placed.items():
        if nm.startswith(skip) and nm != "MO-10_vase_far":
            continue
        vs = world_verts(ob)
        lo = [min(v[i] for v in vs) for i in range(3)]
        hi = [max(v[i] for v in vs) for i in range(3)]
        if nm == "Cabinet_Far":
            lo[1] = CAB["front"] + 0.05                 # the box starts behind the doors: the zone in front of them is reached first
        col_box(f"COL_{nm}", lo, hi)
    for j, (side, Y, base, k) in enumerate(columns):
        r = 0.21 * k
        col_box(f"COL_column_{side}_{j:02d}", (base.x - r, base.y - r, 0), (base.x + r, base.y + r, 2.55 * k))
    face_n = math.radians(180)                         # an Arrive_'s -Y axis is the way you face: yaw 180 faces +Y (north)
    front = CAB["front"]
    empty("Marker_Spawn", (SPAWN.x, SPAWN.y, 0), "Spawn", yaw=face_n)
    empty("Marker_Entrance", (0, -9.0 + 0.3, 0), "Entrance", yaw=face_n)
    empty("Marker_Exit", (0, front - 0.3, 0), "Exit", yaw=face_n)
    empty("Arrive_Morpheus_In", (SPAWN.x, SPAWN.y, 0), yaw=face_n, note="where the walker stands inside the malachite door (from the Hypnos bed)")
    empty("Link_Morpheus_Cabinet", (0, front - 0.25, 0), to_scene="rdwe_god_oneiros", to_arrive="Arrive_Oneiros_In")
    empty("Spot_cabinet", (0, front - 0.6, 0), note="the walker's first close look up at the 4.75 m wardrobe")
    col_box("Zone_trigger_cabinet", (-CAB_LEAF_W, front - 0.45, 0), (CAB_LEAF_W, front + 0.05, CAB_LEAF_Z + CAB_LEAF_H))
    leaf_in = bpy.data.objects["DoorLeaf_Morpheus_In"]
    leaf_in["hinge"] = "west edge"
    leaf_in["swing_deg"] = 0
    leaf_in["state"] = "closed"
    for tag, edge in (("L", "west edge"), ("R", "east edge")):
        lf = bpy.data.objects[f"DoorLeaf_Morpheus_Cabinet_{tag}"]
        lf["hinge"] = edge + " (the cabinet's side)"
        lf["swing_deg"] = 95
        lf["state"] = "ajar 7 degrees"


# ---------------------------------------------------------------- lights (for the bake and the stills; never exported)
SCONCE_W = 14.0          # each sconce's bulb at s = 1 (W); times s squared, as the sconce grows
LAMP_W = 12.0            # the poppy-glass lamp
WINDOW_W = 260.0         # each clerestory pane's light at s = 2 (an area light just inside the pane), times (s / 2) squared
FILL_W = 700.0           # the hall's even part: three broad warm area lights under the ceiling, at s = 1.5, times (s / 1.5) squared
CAB_W = 25.0             # the light through the wardrobe's crack
WASH_W = 320.0           # cove lights washing the splayed walls, three a side, at s = 1.5, times (s / 1.5) squared
WASH_Y = [1.8, 5.2, 8.6]
PLACARD_W = 0.09
FILL_Y = [2.0, 6.0, 9.6]


def add_lights():
    lights = bpy.data.collections.new("Lights")
    bpy.context.scene.collection.children.link(lights)

    def light(name, kind, loc, energy, color, size=0.05):
        d = bpy.data.lights.new(name, kind)
        d.energy, d.color = energy, color
        d.shadow_soft_size = size
        ob = bpy.data.objects.new(name, d)
        ob.location = loc
        ob["base_w"] = energy
        lights.objects.link(ob)
        return ob, d

    for i, (bc, k) in enumerate(SCONCE_BULBS):
        light(f"Sconce_{i}", "POINT", bc, SCONCE_W * k * k, (1.0, 0.68, 0.38), 0.03 * k)
    lamp = bpy.data.objects.get("MO-00_lamp")
    if lamp:
        vs = world_verts(lamp)
        z0 = min(v.z for v in vs)
        Hh = max(v.z for v in vs) - z0
        c = sum(vs, Vector()) / len(vs)
        bz = z0 + 0.66 * Hh
        light("Lamp_Bulb", "POINT", (c.x, c.y, bz), LAMP_W, (1.0, 0.62, 0.32), 0.03)
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.025, matrix=Matrix.Translation((c.x, c.y, bz)))
        box_uv(bm, 1.0)
        mesh_obj("Lamp_Glow", bm, "Lamp_Emit", smooth=True)
    for i, (c, n_in, w, h) in enumerate(WINDOWS):
        k = (c.y + 21.0) / 12.0
        ob, d = light(f"Window_{i}", "AREA", c + n_in * 0.25 * k, WINDOW_W * (k / 2.0) ** 2, (1.0, 0.70, 0.40), 0.0)
        d.shape, d.size, d.size_y = "RECTANGLE", w, h
        aim = n_in + Vector((0, 0, -0.45))
        ob.rotation_euler = aim.to_track_quat("-Z", "Y").to_euler()
    for side, sx in SIDE.items():
        for i, Y in enumerate(WASH_Y):
            k = S_at(Y)
            c = P(sx * (HW0 - 1.1), Y, 2.75)
            ob, d = light(f"Wash_{side}_{i}", "AREA", c, WASH_W * (k / 1.5) ** 2, (1.0, 0.88, 0.74), 0.0)
            d.shape, d.size, d.size_y = "RECTANGLE", 1.8 * k, 0.5 * k
            ob.rotation_euler = (P(sx * HW0, Y, 1.3) - c).to_track_quat("-Z", "Y").to_euler()
    for i, Y in enumerate(FILL_Y):
        k = S_at(Y)
        c = P(0.0, Y, H0 - 0.15)
        ob, d = light(f"Fill_{i}", "AREA", c, FILL_W * (k / 1.5) ** 2, (1.0, 0.86, 0.70), 0.0)
        d.shape, d.size, d.size_y = "RECTANGLE", 3.6 * k, 2.2 * k
    front = CAB["leaf_y"]
    ob, d = light("Cabinet_Crack", "AREA", (0, front - 0.12, CAB_LEAF_Z + CAB_LEAF_H / 2), CAB_W, (1.0, 0.72, 0.42), 0.0)
    d.shape, d.size, d.size_y = "RECTANGLE", 0.16, CAB_LEAF_H * 0.9
    ob.rotation_euler = Vector((0, -1, -0.15)).to_track_quat("-Z", "Y").to_euler()
    pc = PLACARD_C + Vector((0, 0.16, 0.14 + 0.06 + 0.05 - 0.03))
    ob, d = light("Placard_Light", "AREA", pc, PLACARD_W, (1.0, 0.85, 0.65), 0.0)
    d.shape, d.size, d.size_y = "RECTANGLE", 0.28, 0.02
    ob.rotation_euler = (PLACARD_C - pc).to_track_quat("-Z", "Y").to_euler()


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
    gen = {"floor": mk_image("Morpheus_Floor", floor_pixels()), "wall": mk_image("Morpheus_Wall", wall_pixels()),
           "ceiling": mk_image("Morpheus_Ceiling", ceiling_pixels()), "column": mk_image("Morpheus_Column", column_pixels()),
           "glass": mk_image("Morpheus_Poppy_Glass", poppy_glass_pixels()), "door": mk_image("Morpheus_Door", door_in_pixels()),
           "leaf": mk_image("Morpheus_Cabinet_Leaf", cabinet_leaf_pixels()), "placard": mk_image("Morpheus_Placard", placard_pixels())}
    make_materials(gen)
    build_shell()
    columns = build_columns()
    build_entrance()
    build_placard()
    build_sconces()
    build_clerestory()
    placed = place_all()
    build_cabinet_doors(placed)
    build_layout(placed, columns)
    add_lights()
    setup_world()
    sc.unit_settings.system = "METRIC"
    for o in ART.objects:
        if o.type == "MESH" and o.data.materials and o.data.materials[0].name in NOLM:
            o.visible_shadow = False
    tris = sum(tri_count(o) for o in ART.objects if o.type == "MESH")
    print("ART triangles", tris)


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    scrub_private()
    bpy.ops.wm.save_mainfile()


# ================================================================ bake (R1)
def furn(*codes):
    return tuple(f"{SET}_{c}_" for c in codes)


GROUPS = [
    ("Floor_Marble", "Wall_Malachite", "Gold_Trim", "Trim_Dark", "Door_Malachite", "Cabinet_Door", "Placard", "Column_Malachite"),  # 0 the hall
    ("Ceiling_Painted",),                                                                                                       # 1 the ceiling
    furn("MO-01", "MO-02", "MO-03", "MO-04", "MO-05", "MO-06", "MO-07", "MO-11"),                                               # 2 the big furniture
    furn("MO-00", "MO-08", "MO-09", "MO-10", "MO-12", "P6", "P12"),                                                             # 3 the smalls, props, masks
]
MIN_DENSITY = [32, 16, 56, 60]
PAGES = [None, None, None, None]
if arg("--pages"):
    PAGES = [None if v == "auto" else int(v) for v in arg("--pages").split(",")]
NOLM = ("Lamp_Emit", "Poppy_Glass", "Cabinet_Light", "Sconce_Gilt", "Picture_Light_Emit")
KEEP_NODES = ("DoorLeaf_", "decor_mask_", "Cabinet_Far")     # their own nodes (the scene code moves, turns or scales them), not merged
MAIN = ("Floor_Marble", "Wall_Malachite", "Ceiling_Painted", "Column_Malachite", "Door_Malachite", "Cabinet_Door", f"{SET}_")
NOT_MAIN = (f"{SET}_MO-00_lamp", "Cabinet_Door")     # the lamp's body by its bulb; the wardrobe's poppy-glass doors, lit from inside
TARGET_P90 = arg("--target", 0.90, float)
CLIP_CAP = arg("--clip-cap", 0.98, float)


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
    sid = 0
    for ob in art.objects:
        if ob.type != "MESH":
            continue
        assert len(ob.data.materials) == 1, ob.name
        mname = ob.data.materials[0].name
        if ob.name.startswith(KEEP_NODES):
            me = ob.data.copy()
            me.name = ob.name
            loc, rot, sc = ob.matrix_world.decompose()
            me.transform(Matrix.Diagonal((*sc, 1.0)))          # the scale goes into the vertices: the lightmap packer reads true areas
            o2 = bpy.data.objects.new(ob.name + "_x", me)
            o2.matrix_world = Matrix.LocRotScale(loc, rot, None)
            exp.objects.link(o2)
            out[o2.name] = o2
            continue
        bm = by_mat.setdefault(mname, bmesh.new())
        tmp = ob.data.copy()
        tmp.transform(ob.matrix_world)
        a = tmp.attributes.new("srcid", "INT", "FACE")
        a.data.foreach_set("value", [sid] * len(tmp.polygons))
        sid += 1
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
    for mname, bm in by_mat.items():
        tiny = [f for f in bm.faces if f.calc_area() < 1e-9]
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
        if ob.data.materials[0].name in ("Picture_Light_Emit", "Cabinet_Light", "Poppy_Glass"):
            ob.visible_diffuse = ob.visible_glossy = False     # the area lights by them do the lighting; the glowing surfaces only show
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


def uv_islands(me, layer):
    """Face index -> island id: faces joined by an edge whose two ends have the same UVs on both sides."""
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv[layer]
    parent = list(range(len(bm.faces)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for e in bm.edges:
        if len(e.link_faces) != 2:
            continue
        f0, f1 = e.link_faces
        a = {l.vert.index: l[uvl].uv.copy() for l in f0.loops if l.vert in e.verts}
        b = {l.vert.index: l[uvl].uv.copy() for l in f1.loops if l.vert in e.verts}
        if all((a[k] - b[k]).length < 1e-6 for k in a):
            ra, rb = find(f0.index), find(f1.index)
            if ra != rb:
                parent[ra] = rb
    out = [find(i) for i in range(len(bm.faces))]
    bm.free()
    return out


def hall_lightmap_uv(objs, sizes, min_d):
    """The hall's own surfaces: smart-project islands per object (each object alone: Blender's joint multi-object pack collapsed this group
    to nothing), at one density per object, then every island as a rectangle in metres, laid flat (rotated when taller than wide) and
    shelf-packed across the page by height. Long gilt strips pack side by side."""
    rects = []                       # (obj, loops, lo, (w, h) in uv, rotated, metres per uv)
    src = {}
    for o in objs:
        select_only([o])
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
        bpy.ops.uv.average_islands_scale()
        bpy.ops.object.mode_set(mode="OBJECT")
        me = o.data
        a = np.zeros(len(me.loops) * 2, np.float32)
        me.uv_layers["lightmap"].data.foreach_get("uv", a)
        a = a.reshape(-1, 2)
        src[o.name] = a
        m_per_uv = math.sqrt(area3d(o) / max(uv_area(o, "lightmap"), 1e-12))
        isl = uv_islands(me, "lightmap")
        groups = {}
        for p in me.polygons:
            groups.setdefault(isl[p.index], []).extend(range(p.loop_start, p.loop_start + p.loop_total))
        for loops in groups.values():
            loops = np.array(loops)
            lo_, hi_ = a[loops].min(axis=0), a[loops].max(axis=0)
            w, h = (hi_ - lo_) * m_per_uv
            rot = h > w
            rects.append((o, loops, lo_, hi_, (h, w) if rot else (w, h), rot, m_per_uv))
    print(f"  {len(rects)} islands in the atlas")
    order = sorted(range(len(rects)), key=lambda i: -rects[i][4][1])

    def fit(k, gap):
        pos, x, y, row = {}, 0.0, 0.0, 0.0
        for i in order:
            w, h = rects[i][4][0] * k, rects[i][4][1] * k
            if w + 2 * gap > 1.0:
                return None
            if x + w + gap > 1.0:
                x, y, row = 0.0, y + row + gap, 0.0
            if y + h + gap > 1.0:
                return None
            pos[i] = (x + gap, y + gap)
            x += w + gap
            row = max(row, h)
        return pos
    chosen = None
    for S in sizes:
        gap = (MARGIN_PX + 2) / S
        lo, hi = 0.0, 1.0 / max(max(r[4]) for r in rects)
        for _ in range(40):
            mid = (lo + hi) / 2
            if fit(mid, gap):
                lo = mid
            else:
                hi = mid
        chosen = (S, float(S * lo), lo, fit(lo, gap))
        print(f"  page {S}: {sum(area3d(o) for o in objs):.1f} m2, {S * lo:.1f} px/m (island shelf pack)")
        if S * lo >= min_d:
            break
    S, dens, k, pos = chosen
    out = {o.name: np.zeros((len(o.data.loops), 2), np.float32) for o in objs}
    for i, (o, loops, lo_, hi_, wh, rot, mpu) in enumerate(rects):
        uv = src[o.name][loops]
        if rot:                                    # a quarter turn: (u, v) -> (v, hi_u - u)
            local = np.stack([uv[:, 1] - lo_[1], hi_[0] - uv[:, 0]], axis=1)
        else:
            local = uv - lo_
        out[o.name][loops] = local * mpu * k + np.array(pos[i])
    for o in objs:
        o.data.uv_layers["lightmap"].data.foreach_set("uv", out[o.name].ravel())
    return S, dens


def lightmap_uv(objs, page, min_d):
    """As Nyx: the hall's own surfaces get smart-project islands packed by Blender; the furniture and props keep each placed piece's UV0
    layout as one square (the `srcid` face attribute says which piece a face came from), shelf-packed by area."""
    furn_objs = [o for o in objs if o.data.materials[0].name.startswith(f"{SET}_")]
    assert len(furn_objs) in (0, len(objs)), "a lightmap group is either the hall's or the furniture's"
    for o in objs:
        uvs = o.data.uv_layers
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.active = uvs.new(name="lightmap")
    sizes = (page,) if page else (512, 768, 1024, 1280, 1536, 1792, 2048)
    src_layer = "UVMap"
    if not furn_objs:
        return hall_lightmap_uv(objs, sizes, min_d)
    if True:
        src = []
        for o in objs:
            a = np.zeros(len(o.data.loops) * 2, np.float32)
            o.data.uv_layers[src_layer].data.foreach_get("uv", a)
            src.append(a.reshape(-1, 2))
        parts = []
        for o, a in zip(objs, src):
            me = o.data
            bm = bmesh.new()
            bm.from_mesh(me)
            areas = np.array([f.calc_area() for f in bm.faces])
            bm.free()
            npoly = len(me.polygons)
            poly_lstart = np.zeros(npoly, np.int32)
            me.polygons.foreach_get("loop_start", poly_lstart)
            poly_ltot = np.zeros(npoly, np.int32)
            me.polygons.foreach_get("loop_total", poly_ltot)
            keys = np.zeros(npoly, np.int32)
            if furn_objs and "srcid" in me.attributes:      # the hall's merged surfaces stay one square each
                me.attributes["srcid"].data.foreach_get("value", keys)
            for key in sorted(set(keys.tolist())):
                polys = np.nonzero(keys == key)[0]
                loops = np.concatenate([np.arange(poly_lstart[i], poly_lstart[i] + poly_ltot[i]) for i in polys])
                area = float(areas[polys].sum())
                uv = a[loops]
                lo_, hi_ = uv.min(axis=0), uv.max(axis=0)
                uvA = 0.0
                for i in polys:
                    pts = a[poly_lstart[i]:poly_lstart[i] + poly_ltot[i]]
                    uvA += abs(np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - np.roll(pts[:, 0], -1) * pts[:, 1])) / 2
                side = float(max(hi_ - lo_)) * math.sqrt(area / max(uvA, 1e-12))
                parts.append((o, loops, lo_, float(max(hi_ - lo_)), side))
        print(f"  {len(parts)} pieces in the atlas")
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
    """The lights at their build energies (the saved .blend holds them times the last bake's exposure), so a bake is the same from any start."""
    for ob in bpy.data.collections["Lights"].objects:
        if "base_w" in ob.keys():
            ob.data.energy = ob["base_w"]


def stage_bake():
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
        report[n] = {"size": S, "px_per_m": round(float(dens), 1), "scale": round(scale, 5), "p50_p90_p99_p995_max": [round(float(v), 4) for v in pc],
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
    for ob in bpy.data.collections["Lights"].objects:
        ob.data.energy *= k
    (work() / "lightmaps.json").write_text(json.dumps({"maps": report, "exposure_k": round(k, 5), "target_p90": TARGET_P90, "clip_cap_p99": CLIP_CAP, "cap_binds": capped, "displayed": disp}, indent=1))
    for m, d in sorted(disp.items(), key=lambda kv: -kv[1]["p90"]):
        print(f"DISPLAYED {m:34s} map {d['map']}  p50 {d['p50']:.3f}  p90 {d['p90']:.3f}  p99 {d['p99']:.3f}  {'main' if d['main'] else ''}")
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


# ================================================================ export
QPOS = arg("--qpos", 13, int)        # 13 bits over the 18 m hall: 2.2 mm
QNORM = arg("--qnorm", 8, int)       # the baked materials are drawn unlit: their normals only matter for the few PBR ones (the gilt sconces)
QUV = arg("--quv", 12, int)


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
        if "srcid" in o.data.attributes:
            o.data.attributes.remove(o.data.attributes["srcid"])
        if o.name.endswith("_x"):
            want = o.name[:-2]
            clash = bpy.data.objects.get(want)
            if clash is not None and clash is not o:
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
                                  export_draco_mesh_compression_enable=draco, export_draco_mesh_compression_level=10,
                                  export_draco_position_quantization=QPOS, export_draco_normal_quantization=QNORM, export_draco_texcoord_quantization=QUV)
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
        if b[i + 1] not in (0xFE, 0xE1):
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
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = arg("--exposure", 0.0, float)
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    front = bpy.data.objects["Cabinet_Far"]
    fy = min(v.y for v in world_verts(front))
    shots = {
        "1_arrival": (look_cam("arrival", (SPAWN.x, SPAWN.y, EYE), (0.0, 4.0, 1.9), 72.0), (1920, 1080), STILLS),
        "2_wide": (look_cam("wide", (-2.3, -8.7, 2.9), (0.8, 3.0, 1.6), 72.0), (1920, 1080), STILLS),
        "3_bedchamber": (look_cam("bedchamber", (2.0, -1.2, 1.55), (-2.6, -5.4, 0.7), 72.0), (1920, 1080), STILLS),
        "4_wardrobe": (look_cam("wardrobe", (0.8, fy - 2.2, EYE), (0.0, fy + 0.4, 3.0), 78.0), (1920, 1080), STILLS),
        "back": (look_cam("back", (0.0, 6.5, EYE), (0.0, -9.0, 1.4), 72.0), (1280, 720), work()),
        "plan": (look_cam("plan", (0, 0, 30), None, ortho=19.5), (1100, 1400), work()),
    }
    shots["plan"][0].data.sensor_fit = "VERTICAL"
    hide_plan = [o for o in bpy.data.collections["Art"].objects if o.name.startswith(("Ceiling", "Clerestory", "Gilt_Mouldings"))]
    which = arg("--only", "all")
    for key, (cam, (w, h), folder) in shots.items():
        if which != "all" and key not in which.split(","):
            continue
        sc.camera = cam
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
    for o in hide_plan:
        o.visible_camera = True


def stage_views():
    for code, fname, name, budget, px in PIECES:
        clear_scene()
        bpy.ops.import_scene.gltf(filepath=str(copy_path(code, name)))
        ob = next(o for o in bpy.data.objects if o.type == "MESH")
        view_sheet(ob, code)


if __name__ == "__main__":
    ST = STAGE.split(",")
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
