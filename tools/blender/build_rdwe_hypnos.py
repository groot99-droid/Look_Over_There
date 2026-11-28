"""Builds Right Door, Wrong Exit's god room Hypnos, "The Drowsing Room" (`rdwe_god_hypnos`), in Blender: the reduced game copies of the owner's
Hypnos furniture set and three bought props, the verdigris-panelled bedchamber with its four looping doors, the drowsing set piece (haze cards,
leaning pieces, a clock whose hands the code slows), the night bake, and world/rdwe_god_hypnos.glb with its lightmaps.

Re-runnable, from the repo root (docs/BLENDER.md, docs/BLENDER_AREAS.md section 7):

    blender -b --factory-startup --python tools/blender/build_rdwe_hypnos.py -- --stage copies --src <folder>   (the 13 originals and 3 props -> reduced copies)
    blender -b --factory-startup --python tools/blender/build_rdwe_hypnos.py -- --stage art                     (the room; saves blender/scenes/rdwe_god_hypnos.blend)
    blender -b --factory-startup blender/scenes/rdwe_god_hypnos.blend --python tools/blender/build_rdwe_hypnos.py -- --stage bake [--samples 512] [--device cpu]
    blender -b --factory-startup blender/scenes/rdwe_god_hypnos.blend --python tools/blender/build_rdwe_hypnos.py -- --stage export
    blender -b --factory-startup blender/scenes/rdwe_god_hypnos.blend --python tools/blender/build_rdwe_hypnos.py -- --stage render [--render-samples 128]
    (--stage bake,export,render runs several in one go; --stage views writes view sheets of the copies)
    then, in plain Python (Pillow): each lightmap PNG -> world/lightmaps/rdwe_god_hypnos_<n>.webp (q90), and
    python tools/webp_glb.py blender/work/farway_rdwe_god_hypnos/rdwe_god_hypnos_raw.glb world/rdwe_god_hypnos.glb 85
    (docs/renders/rdwe_god_hypnos/README.md has the exact steps; the work folder is blender/work/farway_rdwe_god_hypnos, git-ignored)

The structure is the Nyx room's (tools/blender/build_rdwe_nyx.py): the same copies stage, bake (R1, the exposure rule --target / --clip-cap),
export (Draco, then tools/webp_glb.py) and stills. Stage `copies` reads the originals (never writes them). The exporter's objects (COL_,
DoorLeaf_, Marker_, Link_, Arrive_, Zone_, Spot_) are kept in the `Layout` collection for tools/blender/export_scene.py, which is not on main
yet, so no world/rdwe_god_hypnos.json is written here.

Axes: Blender metres, x east, y north, z up, the room's centre at the origin, the floor at z = 0. The glTF exporter's +Y up turns Blender (x, y, z)
into game (x, z, -y), so game north is -z, as everywhere in Farway.
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
SCENE = "rdwe_god_hypnos"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
COPIES = ROOT / "blender/models/rdwe_hypnos"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"
MARGIN_PX = 8
SET = "Hypnos"

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 512, int)
DEVICE = arg("--device", "auto")
SRC = Path(arg("--src", str(ROOT / "blender/work/hypnos_source")))
ONLY = arg("--only", "all")


def work():
    d = Path(arg("--work", str(ROOT / f"blender/work/farway_{SCENE}")))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- the pieces (manifest: Hypnos_collection_manifest.csv; budgets: PLAN section 5)
# code, original file, short name, triangle budget, base colour size (px)
PIECES = [
    ("HY-00", "HY-00_Hypnos_Lamp.glb", "lamp", 15000, 1024),
    ("HY-01", "HY-01_Hypnos_Bedside_Table.glb", "bedside_table", 15000, 1024),
    ("HY-02", "HY-02_Hypnos_Armchair.glb", "armchair", 18000, 1024),
    ("HY-03", "HY-03_Hypnos_Dresser.glb", "dresser", 18000, 1024),
    ("HY-04", "HY-04_Hypnos_Tall_Cabinet.glb", "tall_cabinet", 18000, 1024),
    ("HY-05", "HY-05_Hypnos_Bed.glb", "bed", 24000, 2048),
    ("HY-06", "HY-06_Hypnos_Wall_Mirror.glb", "wall_mirror", 15000, 1024),
    ("HY-07", "HY-07_Hypnos_Writing_Desk.glb", "writing_desk", 18000, 1024),
    ("HY-08", "HY-08_Hypnos_Clock.glb", "clock", 15000, 512),
    ("HY-09", "HY-09_Hypnos_Hourglass.glb", "hourglass", 15000, 512),
    ("HY-10", "HY-10_Hypnos_Vase.glb", "vase", 15000, 512),
    ("HY-11", "HY-11_Hypnos_Rug.glb", "rug", 2000, 1024),             # a flat 12 mm slab: 2k triangles hold its edge; the texture is the rug
    ("HY-12", "HY-12_Hypnos_Textiles.glb", "textiles", 15000, 1024),
    # the Higgsfield props PLAN section 7 gives Hypnos (normalised by the generator; `size` is the plan's W x H x D in metres)
    ("P7", "P7.glb", "hypnos_head", 10000, 1024),
    ("P10", "P10.glb", "poppy_urn", 12000, 512),
    ("P11", "P11.glb", "lethe_basin", 12000, 1024),
]
PROP_SIZE = {"P7": (0.45, 1.6, 0.45), "P10": (0.6, 0.95, 0.6), "P11": (1.4, 0.9, 1.4)}
PER_AXIS = set()
FIX_UV = {"P10"}      # its decimated flowers leave slivers that wreck the island scaling: a stricter sliver cut, no island averaging
BY_WIDTH = {"P11"}         # the basin came out wide and low: it keeps its proportions and takes the plan's 1.4 m width (so it is lower than 0.9)


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
            bpy.data.objects.remove(o)             # HY-00's own punctual light goes too: the room sets its own lamp light
    return ob


def emission_from_base(mat):
    """Bake source: the original's base colour (its texture times its factor) straight into an Emission shader, so the bake reads the colour
    itself, whatever the metal and the roughness say (a diffuse-colour bake would give black on the gilt)."""
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.0
    if bsdf is None:
        em.inputs["Color"].default_value = (0.5, 0.5, 0.5, 1)
    else:
        sock = bsdf.inputs["Base Color"]
        if sock.is_linked:
            nt.links.new(sock.links[0].from_socket, em.inputs["Color"])
        else:
            em.inputs["Color"].default_value = sock.default_value
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])


def view_sheet(ob, code):
    """Small orthographic views of the copy, from +X, -X, +Y, -Y (Blender) and the top, to read which way the piece faces."""
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
        if m and m.node_tree:
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
    # scale: the props come normalised; the furniture is at its manifest size already
    s = Vector((1, 1, 1))
    if code in PROP_SIZE:
        w, h, d = PROP_SIZE[code]
        dx, dy, dz = cp.dimensions
        if code in PER_AXIS:
            s = Vector((w / dx, d / dy, h / dz))
        elif code in BY_WIDTH:
            k = w / max(dx, dy)
            s = Vector((k, k, k))
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
    # zero-area slivers (P10's flowers left many): they would blow up average_islands_scale and shrink every real island to nothing
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.dissolve_degenerate(bm, dist=diag * 1e-5, edges=bm.edges)
    tiny = [f for f in bm.faces if f.calc_area() < (diag * (1e-4 if code in FIX_UV else 1e-5)) ** 2]
    if tiny:
        bmesh.ops.delete(bm, geom=tiny, context="FACES")
    bm.to_mesh(me)
    bm.free()
    smooth_by_angle(me, 40)
    # fresh UV0
    me.uv_layers.new(name="UVMap")
    select_only([cp])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.002, scale_to_bounds=False)
    if code not in FIX_UV:
        bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=3.0 / px, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    # the bake target
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


# ================================================================ the room (PLAN section 4.3)
HX, HY = 3.5, 4.0                          # the room's half sizes: 7 x 8 m
WALL_H = 3.4                               # a low flat ceiling
WALL_T = 0.2
DADO_Z = 0.9                               # the gilt dado rail
FRIEZE_Z0, FRIEZE_Z1 = 2.78, 3.18          # the gold-leaf frieze (painted in the wall picture, gilt beads at its edges)
EYE = 0.95                                 # the RDWE walker's eye at RDWE_SCALE 1.7 (controls.js: 1.62 / 1.7)
DOOR_W, DOOR_H = 0.94, 2.16
SPAWN = Vector((0.0, -3.3, 0.0))
# the four doors: name -> (centre on the wall's inner face, outward normal, the leaf's hinge side as +1/-1 along the tangent t = (-n.y, n.x))
DOORS = {
    "In": (Vector((0.0, -HY, 0.0)), Vector((0, -1, 0)), -1),      # south, the way in from Selene; hinge on its west jamb (t = (1, 0))
    "N": (Vector((0.0, HY, 0.0)), Vector((0, 1, 0)), +1),         # hinge on the west jamb (t = (-1, 0))
    "E": (Vector((HX, 1.6, 0.0)), Vector((1, 0, 0)), +1),         # hinge on the north jamb (t = (0, 1))
    "W": (Vector((-HX, 1.6, 0.0)), Vector((-1, 0, 0)), -1),       # hinge on the north jamb (t = (0, -1))
}
PASS_W, PASS_H, PASS_D = 1.2, 2.5, 1.3     # each door opens into a short passage (from the wall's inner face to its back wall)
VEIL_D = 0.75                              # the navy veil hangs across the passage this far out from the wall's inner face: crossing it loops
LOOPS = {"N": "In", "In": "N", "E": "W", "W": "E"}     # crossing door A's veil outward puts you just inside door B's veil, facing on, yaw kept
FLATS = {"E": Vector((1, 0, 0)), "W": Vector((-1, 0, 0)), "N": Vector((0, 1, 0)), "S": Vector((0, -1, 0))}
HALF = {"E": HX, "W": HX, "N": HY, "S": HY}
COMPASS = {"E": 0, "NE": 45, "N": 90, "NW": 135, "W": 180, "SW": 225, "S": 270, "SE": 315}

# which way each copy faces as made (read by eye from the copies' view sheets): the compass angle its front points to in Blender.
# The set's pieces face +X (the clock's face, the bed's foot); the props face -Y
NATIVE_FRONT = {f"HY-{i:02d}": 0 for i in range(13)}
NATIVE_FRONT.update({"P7": 270, "P10": 270, "P11": 270})

# placement (PLAN 4.3): code, object name, (x, y), facing, how: ("floor"), ("wall", flat, gap), ("hang", flat, gap, z), ("on", support, (dx, dy))
PLACE = [
    ("HY-11", "HY-11_rug", (0.0, -0.6), "E", ("floor",)),
    ("HY-05", "HY-05_bed", (2.37, -2.0), "W", ("wall", "E", 0.03)),
    ("HY-01", "HY-01_bedside_table_N", (3.25, -0.80), "W", ("wall", "E", 0.04)),
    ("HY-01", "HY-01_bedside_table_S", (3.25, -3.20), "W", ("wall", "E", 0.04)),
    ("HY-03", "HY-03_dresser", (-3.2, -2.2), "E", ("wall", "W", 0.03)),
    ("HY-06", "HY-06_wall_mirror", (-3.45, -2.2), "E", ("hang", "W", 0.02, 1.02)),
    ("HY-04", "decor_lean_cabinet", (-3.0, 3.3), "E", ("wall", "W", 0.04)),
    ("HY-07", "HY-07_writing_desk", (2.85, 3.0), "W", ("wall", "E", 0.03)),
    ("HY-02", "HY-02_armchair", (1.95, 3.0), "E", ("floor",)),
    ("P11", "P11_lethe_basin", (0.0, 1.7), "S", ("floor",)),
    ("P10", "P10_poppy_urn_W", (-1.1, 3.6), "S", ("wall", "N", 0.07)),
    ("P10", "P10_poppy_urn_E", (1.1, 3.6), "S", ("wall", "N", 0.07)),
    ("P7", "decor_lean_column", (-3.05, -0.3), "E", ("wall", "W", 0.10)),
    # the smalls, on the furniture
    ("HY-00", "HY-00_lamp", (0.0, 0.0), "W", ("on", "HY-01_bedside_table_N")),
    ("HY-10", "HY-10_vase", (0.0, 0.0), "W", ("on", "HY-01_bedside_table_S")),
    ("HY-08", "HY-08_clock", (0.0, -0.33), "E", ("on", "HY-03_dresser")),
    ("HY-09", "HY-09_hourglass", (0.0, 0.40), "W", ("on", "HY-07_writing_desk")),
    ("HY-12", "HY-12_textiles", (-0.62, 0.0), "W", ("on", "HY-05_bed")),
]
LEAN = {"decor_lean_cabinet": "E", "decor_lean_column": "E"}   # leaning pieces: pivot on the front edge of the foot, top tips this way

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
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
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


def noise(shape, r, seed, passes=2, wrap=True):
    rng = np.random.default_rng(seed)
    n = (wrap_blur if wrap else blur)(rng.random(shape).astype(np.float32), r, passes)
    return (n - n.min()) / max(1e-6, n.max() - n.min())


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
    if hi_r <= lo_r or hi_c <= lo_c:
        return
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
    if hi_r <= lo_r or hi_c <= lo_c:
        return
    yy, xx = np.mgrid[lo_r:hi_r, lo_c:hi_c].astype(np.float32)
    a = np.clip(r + 0.5 - np.hypot(yy - p[0], xx - p[1]), 0, 1)[..., None]
    img[lo_r:hi_r, lo_c:hi_c] = img[lo_r:hi_r, lo_c:hi_c] * (1 - a) + np.array(col) * a


def poppy(img, c, r, col, centre_col, petals=4, rot=0.0):
    """A stylised poppy seen from above: round overlapping petals and a dark seed head."""
    H, W = img.shape[:2]
    lo_r, hi_r = int(max(0, c[0] - r * 1.1 - 2)), int(min(H, c[0] + r * 1.1 + 3))
    lo_c, hi_c = int(max(0, c[1] - r * 1.1 - 2)), int(min(W, c[1] + r * 1.1 + 3))
    if hi_r <= lo_r or hi_c <= lo_c:
        return
    yy, xx = np.mgrid[lo_r:hi_r, lo_c:hi_c].astype(np.float32)
    dy, dx = yy - c[0], xx - c[1]
    m = np.zeros_like(dy)
    for k in range(petals):
        a = rot + 2 * math.pi * k / petals
        py, px = math.sin(a) * r * 0.45, math.cos(a) * r * 0.45
        m = np.maximum(m, np.clip(r * 0.6 + 0.5 - np.hypot(dy - py, dx - px), 0, 1))
    img[lo_r:hi_r, lo_c:hi_c] = img[lo_r:hi_r, lo_c:hi_c] * (1 - m[..., None]) + np.array(col) * m[..., None]
    dot(img, c, centre_col, r * 0.22)


GOLD_S = (0.86, 0.66, 0.30)       # sRGB gold for the painted lines
COPPER_S = (0.70, 0.42, 0.26)
NAVY_S = (0.15, 0.21, 0.42)
FLOOR_SPAN = 2 * HY + 0.2         # the floor picture covers this square (metres), centred on the room


def floor_pixels():
    """The floor, one picture over the room: pale cream limestone and grey-green marble laid on the diagonal (0.55 m squares), a navy and
    copper border band round the walls, and a gold ring of seed heads round the basin."""
    S = 2048
    ppm = S / FLOOR_SPAN
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    X = xx / ppm - FLOOR_SPAN / 2
    Y = FLOOR_SPAN / 2 - yy / ppm
    n1 = noise((S, S), 20, 3)
    n2 = noise((S, S), 4, 4)
    a, b = (X + Y) / 0.55, (X - Y) / 0.55
    chk = (np.floor(a) + np.floor(b)) % 2
    cream = np.array([0.80, 0.75, 0.64])
    green = np.array([0.56, 0.64, 0.59])
    img = np.where(chk[..., None] > 0.5, cream, green).astype(np.float32)
    img *= (0.90 + 0.16 * n1 + 0.06 * n2)[..., None]
    joint = (np.minimum(np.abs(a - np.round(a)), np.abs(b - np.round(b))) * 0.55) < 0.004
    img[joint] = img[joint] * 0.72
    v = np.abs(((n1 * 7.0 + n2 * 1.3) % 1.0) - 0.5)
    vein = np.clip(1 - v / 0.02, 0, 1) * (chk < 0.5) * (n2 > 0.4)
    img = img * (1 - 0.35 * vein[..., None]) + np.array([0.86, 0.88, 0.84]) * 0.35 * vein[..., None]
    # the border: 0.32 m of navy with copper lines, 0.10 m in from the walls
    d = np.minimum(HX - np.abs(X), HY - np.abs(Y))
    band = (d > 0.10) & (d < 0.42)
    img[band] = np.array(NAVY_S) * (0.92 + 0.12 * n2[band])[..., None]
    for d0 in (0.10, 0.42):
        img[np.abs(d - d0) < 0.012] = COPPER_S
    img[np.abs(d - 0.26) < 0.006] = GOLD_S
    rr = np.hypot(X - 0.0, Y - 1.7)
    for R0 in (1.02, 1.10):
        img[np.abs(rr - R0) < 0.011] = GOLD_S
    for k in range(16):
        ang = 2 * math.pi * k / 16
        cx, cy = 1.06 * math.cos(ang), 1.7 + 1.06 * math.sin(ang)
        dot(img, ((FLOOR_SPAN / 2 - cy) * ppm, (cx + FLOOR_SPAN / 2) * ppm), GOLD_S, 5)
    for sx in (-1, 1):
        for sy in (-1, 1):
            c = ((FLOOR_SPAN / 2 - sy * (HY - 0.26)) * ppm, (sx * (HX - 0.26) + FLOOR_SPAN / 2) * ppm)
            poppy(img, c, 0.12 * ppm, (0.72, 0.18, 0.12), (0.10, 0.08, 0.10), 4, 0.3)
    return np.clip(img, 0, 1).astype(np.float32)


WALL_TILE_U, WALL_TILE_V = 1.0, 3.6        # the wall picture covers 1.0 m of wall and 3.6 m of height (one panel bay, floor to above the ceiling)


def wall_pixels():
    """One panel bay of the walls (1.0 m wide, from the floor up): a copper skirting, a verdigris dado panel, a tall verdigris panel in a copper
    frame, and the gold-leaf frieze of poppies and seed heads under the cornice. Patinated copper: blue-green with the metal showing through."""
    Wd, Hd = 256, 920
    ppm = Hd / WALL_TILE_V
    nb = noise((Hd, Wd), 10, 13)
    nf = noise((Hd, Wd), 2, 14)
    verd = np.array([0.42, 0.66, 0.60])
    verd2 = np.array([0.30, 0.52, 0.50])
    img = verd * (1 - nb[..., None]) + verd2 * nb[..., None]
    copper = np.clip(nb * 1.6 - 0.95, 0, 1)                  # copper showing through the patina here and there
    img = img * (1 - copper[..., None]) + np.array(COPPER_S) * copper[..., None]
    img *= (0.92 + 0.14 * nf)[..., None]
    z = (Hd - 1 - np.arange(Hd)) / ppm                         # row -> height in metres (row 0 is the top)
    u = np.arange(Wd) / ppm

    def rows(z0, z1):
        return (z >= z0) & (z < z1)
    img[rows(0, 0.16)] = np.array(COPPER_S) * 0.75 * (0.9 + 0.2 * nf[rows(0, 0.16)])[..., None]
    for z0, z1 in ((0.22, 0.82), (1.0, 2.62)):
        inside = rows(z0, z1)[:, None] & ((u > 0.08) & (u < 0.92))[None, :]
        rim = rows(z0 - 0.03, z1 + 0.03)[:, None] & ((u > 0.05) & (u < 0.95))[None, :] & ~inside
        img[rim] = np.array(COPPER_S) * 0.95
        img[inside] *= 1.06
        edge = rows(z0, z0 + 0.012)[:, None] & ((u > 0.08) & (u < 0.92))[None, :]
        img[edge] = np.array(GOLD_S) * 0.9
    fz = rows(FRIEZE_Z0, FRIEZE_Z1)
    img[fz] = np.array(NAVY_S) * (0.95 + 0.1 * nf[fz])[..., None]
    for z0 in (FRIEZE_Z0, FRIEZE_Z1 - 0.02):
        img[rows(z0, z0 + 0.02)] = GOLD_S
    zc = (FRIEZE_Z0 + FRIEZE_Z1) / 2
    rc = (Hd - 1) - zc * ppm
    for cx, kind in ((0.25, "p"), (0.75, "s")):
        if kind == "p":
            poppy(img, (rc, cx * ppm), 0.11 * ppm, GOLD_S, (0.25, 0.18, 0.08), 5, 0.2)
        else:
            dot(img, (rc, cx * ppm), GOLD_S, 0.06 * ppm)
            line(img, (rc - 0.06 * ppm, cx * ppm), (rc - 0.10 * ppm, cx * ppm), GOLD_S, 3)
            for k in range(6):
                line(img, (rc, cx * ppm), (rc + 0.05 * ppm * math.sin(k), cx * ppm + 0.05 * ppm * math.cos(k)), (0.25, 0.18, 0.08), 1.5)
        line(img, (rc, (cx - 0.25) * ppm + 2), (rc, (cx - 0.15) * ppm), GOLD_S, 2)
    img[z >= FRIEZE_Z1] = np.array(NAVY_S)
    return np.clip(img, 0, 1).astype(np.float32)


CEIL_TILE = 1.6


def ceiling_pixels():
    """The low ceiling: navy plaster with gold poppies and seed heads, a seamless tile (CEIL_TILE metres)."""
    S = 512
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.17, 0.24, 0.46)
    img *= (0.9 + 0.2 * noise((S, S), 12, 21))[..., None]
    for (r, c, rad) in ((S * 0.25, S * 0.25, 0.10), (S * 0.75, S * 0.75, 0.10), (S * 0.25, S * 0.75, 0.05), (S * 0.75, S * 0.25, 0.05)):
        big = rad > 0.07
        for oy in (-S, 0, S):
            for ox in (-S, 0, S):
                cc = (r + oy, c + ox)
                if big:
                    poppy(img, cc, rad * S, GOLD_S, (0.30, 0.10, 0.08), 5, 0.4)
                else:
                    dot(img, cc, GOLD_S, rad * S * 0.6)
                    dot(img, cc, (0.17, 0.24, 0.46), rad * S * 0.3)
    for k in range(4):
        a = k * math.pi / 2 + math.pi / 4
        line(img, (S * 0.5, S * 0.5), (S * 0.5 + S * 0.18 * math.sin(a), S * 0.5 + S * 0.18 * math.cos(a)), GOLD_S, 2)
    dot(img, (S * 0.5, S * 0.5), GOLD_S, 6)
    return np.clip(wrap_blur(img, 1, 1), 0, 1).astype(np.float32)


def leaf_pixels(kind):
    """The four door leaves (0.94 x 2.16 m, a 256 x 588 picture each): In verdigris copper panels; N navy lacquer with six gilt panels;
    E burnished copper with rivets; W navy with a gilt poppy."""
    Wd, Hd = 256, 588
    nf = noise((Hd, Wd), 3, 31 + len(kind), wrap=False)
    nb = noise((Hd, Wd), 14, 41 + len(kind), wrap=False)
    img = np.zeros((Hd, Wd, 3), np.float32)
    sx, sy = Wd / DOOR_W, Hd / DOOR_H

    def rect(x0, z0, x1, z1, col, w=3):
        r0, r1 = Hd - z1 * sy, Hd - z0 * sy
        c0, c1 = x0 * sx, x1 * sx
        for p, q in (((r0, c0), (r0, c1)), ((r1, c0), (r1, c1)), ((r0, c0), (r1, c0)), ((r0, c1), (r1, c1))):
            line(img, p, q, col, w)
    if kind == "In":
        img[:] = np.array([0.40, 0.64, 0.58])
        img *= (0.85 + 0.25 * nb)[..., None]
        for z0, z1 in ((0.18, 0.95), (1.15, 1.98)):
            rect(0.12, z0, 0.82, z1, COPPER_S, 5)
    elif kind == "N":
        img[:] = NAVY_S
        img *= (0.9 + 0.15 * nf)[..., None]
        for z0, z1 in ((0.15, 0.70), (0.85, 1.40), (1.55, 2.00)):
            for x0, x1 in ((0.10, 0.44), (0.50, 0.84)):
                rect(x0, z0, x1, z1, GOLD_S, 3)
    elif kind == "E":
        img[:] = (0.72, 0.44, 0.28)
        img *= (0.80 + 0.30 * nb)[..., None]
        pat = np.clip(nb * 1.8 - 1.0, 0, 1)
        img = img * (1 - pat[..., None]) + np.array([0.40, 0.64, 0.58]) * pat[..., None]
        for z in (0.12, 0.7, 1.4, 2.04):
            for x in np.linspace(0.08, 0.86, 7):
                dot(img, (Hd - z * sy, x * sx), (0.45, 0.26, 0.15), 3.5)
        rect(0.06, 0.06, 0.88, 2.10, (0.45, 0.26, 0.15), 4)
    else:
        img[:] = (0.13, 0.18, 0.36)
        img *= (0.9 + 0.15 * nf)[..., None]
        rect(0.08, 0.08, 0.86, 2.08, GOLD_S, 4)
        c = (Hd - 1.35 * sy, 0.47 * sx)
        line(img, c, (Hd - 0.25 * sy, 0.47 * sx), GOLD_S, 5)
        line(img, (Hd - 0.75 * sy, 0.47 * sx), (Hd - 0.95 * sy, 0.30 * sx), GOLD_S, 4)
        poppy(img, c, 0.22 * sx, GOLD_S, (0.30, 0.16, 0.06), 5, 0.1)
    return np.clip(img, 0, 1).astype(np.float32)


def placard_pixels():
    """The museum placard by the entrance (PLAN 2.2): cream letters on black, a gold rule."""
    W, H = 768, 512
    img = np.zeros((H, W, 3), np.float32)
    img[:] = (0.035, 0.03, 0.035)
    img[18:24, 30:W - 30] = img[H - 24:H - 18, 30:W - 30] = GOLD_S
    draw_text(img, "HYPNOS", (40, 170, 0, W), (0.93, 0.88, 0.74), 0.85)
    draw_text(img, "SLEEP - THE DROWSING ROOM", (190, 270, 0, W), (0.86, 0.66, 0.30), 0.92)
    draw_text(img, "NINETY-NINE NOCTURNE SUITE", (290, 370, 0, W), (0.80, 0.76, 0.66), 0.92)
    draw_text(img, "XIII PIECES. COPPER. NAVY. VERDIGRIS.", (380, 460, 0, W), (0.62, 0.58, 0.52), 0.92)
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def dial_pixels():
    """The mantel clock's dial (a disc over the copy's own painted face, so the code's hands are the only hands): navy enamel, a gold ring,
    twelve gold ticks."""
    S = 256
    img = np.zeros((S, S, 3), np.float32)
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    rr = np.hypot(yy - S / 2, xx - S / 2) / (S / 2)
    img[:] = (0.10, 0.15, 0.34)
    img *= (0.9 + 0.2 * noise((S, S), 6, 51, wrap=False))[..., None]
    img[(rr > 0.88)] = GOLD_S
    img[(rr > 0.80) & (rr < 0.83)] = GOLD_S
    for k in range(12):
        a = 2 * math.pi * k / 12
        r0, r1 = (0.58 if k % 3 == 0 else 0.66), 0.78
        line(img, (S / 2 - math.cos(a) * r0 * S / 2, S / 2 + math.sin(a) * r0 * S / 2),
             (S / 2 - math.cos(a) * r1 * S / 2, S / 2 + math.sin(a) * r1 * S / 2), GOLD_S, 5 if k % 3 == 0 else 3)
    dot(img, (S / 2, S / 2), GOLD_S, 7)
    return np.clip(img, 0, 1).astype(np.float32)


def nave_pixels():
    """What HY-06's glass shows (PLAN 4.3): not this room but a still of the Thanatos nave, Hypnos's twin. A one-point perspective of a long
    moonlit hall of black, cream and gold banded columns with teal valances, a warm glow at the far end. Painted with numpy, own work."""
    S = 512
    img = np.zeros((S, S, 3), np.float32)
    f = S * 0.42
    cy, cx = S * 0.58, S * 0.5
    eye = 1.5
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    up = yy < cy
    t = np.abs(yy - cy) / S
    img[up] = (np.array([0.10, 0.13, 0.22]) * (1 - t[up] * 1.2)[:, None] + np.array([0.02, 0.03, 0.06]) * (t[up] * 1.2)[:, None])
    img[~up] = (np.array([0.30, 0.30, 0.34]) * (0.4 + 1.2 * t[~up])[:, None])
    Z = np.where(~up, eye * f / np.maximum(yy - cy, 1e-3), 1e9)
    Xw = (xx - cx) * Z / f
    slab = ((np.floor(Z / 1.0) + np.floor(Xw / 1.0)) % 2 == 0) & ~up & (Z < 40)
    img[slab] *= 0.45
    for k in range(9, -1, -1):
        Zc = 2.6 + 4.0 * k
        for side in (-1, 1):
            xs = cx + f * side * 1.7 / Zc
            w = f * 0.30 / Zc
            fade = math.exp(-Zc / 18.0)
            for b in range(13):
                z0, z1 = 5.0 * b / 13, 5.0 * (b + 1) / 13
                col = [(0.03, 0.03, 0.035), (0.80, 0.76, 0.66), (0.86, 0.66, 0.30)][b % 3]
                r0, r1 = int(cy - f * (z1 - eye) / Zc), int(cy - f * (z0 - eye) / Zc)
                img[max(0, r0):max(0, r1), max(0, int(xs - w)):max(0, int(xs + w))] = np.array(col) * (0.25 + 0.75 * fade)
            vr = int(cy - f * (4.2 - eye) / Zc)
            vh = max(2, int(f * 0.5 / Zc))
            x0, x1 = int(min(xs, cx + side * f * 0.15 / Zc)), int(max(xs, cx + side * f * 0.15 / Zc))
            img[max(0, vr):max(0, vr + vh), max(0, x0):max(0, x1)] = np.array([0.10, 0.42, 0.44]) * (0.3 + 0.7 * fade)
    shaft = np.clip(1 - np.abs((xx - cx) * 0.9 + (yy - cy) * 0.6 - 30) / 60, 0, 1) * (yy > cy * 0.4)
    img += np.array([0.10, 0.12, 0.18]) * shaft[..., None] * 0.6
    glow = np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (S * 0.05) ** 2))
    img += np.array([0.9, 0.7, 0.45]) * glow[..., None] * 0.7
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def haze_pixels():
    """A haze card's picture: a pale blue-grey mist, its alpha a soft round falloff broken by slow noise."""
    S = 256
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    rr = np.hypot(yy - S / 2, xx - S / 2) / (S / 2)
    n = noise((S, S), 16, 61, wrap=False)
    a = np.clip(1 - rr, 0, 1) ** 1.6 * (0.55 + 0.9 * n)
    out = np.ones((S, S, 4), np.float32)
    out[..., :3] = (0.80, 0.86, 0.93)
    out[..., 3] = np.clip(a, 0, 1)
    return out


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


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, img=None, emit=None, double=False, emit_img=False, alpha=None):
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
        if emit_img:
            nt.links.new(n.outputs["Color"], bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = 1.0
        else:
            nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
        if alpha is not None:
            mul = nt.nodes.new("ShaderNodeMath")
            mul.operation = "MULTIPLY"
            mul.inputs[1].default_value = alpha
            nt.links.new(n.outputs["Alpha"], mul.inputs[0])
            nt.links.new(mul.outputs[0], bsdf.inputs["Alpha"])
    if emit is not None:
        bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    if alpha is not None:
        m.surface_render_method = "BLENDED"
    m.use_backface_culling = not double
    MATS[name] = m
    return m


def make_materials(gen):
    material("Floor_Stone", img=gen["floor"], rough=0.35)
    material("Wall_Verdigris", img=gen["wall"], rough=0.6)
    material("Ceiling_Poppy", img=gen["ceiling"], rough=0.9)
    material("Gold_Trim", color=(0.40, 0.27, 0.09), rough=0.35, metal=0.9)          # antique gilt: the page draws it unlit, so not too light
    material("Copper_Trim", color=(0.36, 0.15, 0.07), rough=0.4, metal=0.8)
    material("Passage_Navy", color=(0.035, 0.05, 0.13), rough=0.9)
    material("Veil_Navy", color=(0.03, 0.045, 0.14), rough=0.95, double=True)
    material("Placard", img=gen["placard"], rough=0.5)
    material("Clock_Dial", img=gen["dial"], rough=0.3)
    for k in ("In", "N", "E", "W"):
        material(f"Leaf_{k}", img=gen[f"leaf_{k}"], rough=0.5)
    # not lightmapped
    material("Mirror_Thanatos", color=(0.0, 0.0, 0.0), rough=0.05, img=gen["nave"], emit_img=True)   # the glass shows the twin's nave, at its own light
    material("Haze", color=(0.78, 0.84, 0.92), rough=1.0, img=gen["haze"], alpha=0.30, emit=((0.55, 0.62, 0.75), 0.25), double=True)
    material("Hand_Gilt", color=(0.62, 0.42, 0.14), rough=0.35, metal=0.9)       # the clock's hands, which the code turns
    material("Sconce_Copper", color=(0.55, 0.30, 0.16), rough=0.35, metal=0.9)   # not baked: inches from its own bulb
    material("Lamp_Emit", color=(1.0, 0.85, 0.6), emit=((1.0, 0.62, 0.30), 8.0))
    material("Picture_Light_Emit", color=(1.0, 0.9, 0.7), emit=((1.0, 0.85, 0.6), 4.0))


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


def quad(bm, pts, facing):
    """A quad from four points, flipped to face `facing`."""
    f = bm.faces.new([bm.verts.new(p) for p in pts])
    f.normal_update()
    if f.normal.dot(facing) < 0:
        f.normal_flip()
    return f


def wall_spans(flat):
    """The wall `flat`: (start corner, end corner, inward normal, tangent along it, door spans (u0, u1) along it, half length)."""
    n = FLATS[flat]
    t = Vector((-n.y, n.x, 0))
    L = HY if flat in ("E", "W") else HX
    c = n * HALF[flat]
    holes = []
    for name, (dc, dn, _) in DOORS.items():
        if (dn - n).length < 1e-6:
            u = (dc - c).dot(t)
            holes.append((u - DOOR_W / 2, u + DOOR_W / 2))
    return c - t * L, c + t * L, -n, t, sorted(holes), L


def wall_faces(bm, flat, z0, z1):
    """The wall's inner face between z0 and z1, its door openings left out up to the door heads."""
    a, b, inward, t, holes, L = wall_spans(flat)
    mid = (a + b) / 2
    cuts = [-L] + [u for h in holes for u in h] + [L]
    for i in range(0, len(cuts) - 1):
        u0, u1 = cuts[i], cuts[i + 1]
        p0, p1 = mid + t * u0, mid + t * u1
        lo = max(z0, DOOR_H) if i % 2 == 1 else z0
        if lo >= z1:
            continue
        quad(bm, [(p0.x, p0.y, lo), (p1.x, p1.y, lo), (p1.x, p1.y, z1), (p0.x, p0.y, z1)], inward)


def wall_strip(bm, flat, z0, z1, depth, skip_doors=True):
    """A moulding along one wall: its face `depth` proud of the wall, with top, bottom and end faces; broken at the door openings."""
    a, b, inward, t, holes, L = wall_spans(flat)
    cuts = [-L] + ([u for h in holes for u in (h[0] - 0.09, h[1] + 0.09)] if skip_doors else []) + [L]
    mid = (a + b) / 2
    for i in range(0, len(cuts) - 1, 2):
        u0, u1 = cuts[i], cuts[i + 1]
        p0, p1 = mid + t * u0, mid + t * u1
        q0, q1 = p0 + inward * depth, p1 + inward * depth
        quad(bm, [(q0.x, q0.y, z0), (q1.x, q1.y, z0), (q1.x, q1.y, z1), (q0.x, q0.y, z1)], inward)
        quad(bm, [(p0.x, p0.y, z1), (p1.x, p1.y, z1), (q1.x, q1.y, z1), (q0.x, q0.y, z1)], Vector((0, 0, 1)))
        quad(bm, [(p0.x, p0.y, z0), (p1.x, p1.y, z0), (q1.x, q1.y, z0), (q0.x, q0.y, z0)], Vector((0, 0, -1)))
        for p, q, s in ((p0, q0, -1), (p1, q1, 1)):
            quad(bm, [(p.x, p.y, z0), (q.x, q.y, z0), (q.x, q.y, z1), (p.x, p.y, z1)], t * s)


def wall_uv(bm):
    """The wall picture: u along the wall (WALL_TILE_U metres a repeat), v the height over WALL_TILE_V."""
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        n = f.normal
        h = Vector((-n.y, n.x, 0)).normalized() if Vector((n.x, n.y, 0)).length > 1e-6 else Vector((1, 0, 0))
        for lp in f.loops:
            p = lp.vert.co
            lp[uvl].uv = (p.dot(h) / WALL_TILE_U + 0.5, p.z / WALL_TILE_V)


def build_shell():
    # floor: one rectangle with the picture over it, and the passages' floors (the same picture, wrapping)
    bm = bmesh.new()
    quad(bm, [(-HX, -HY, 0), (HX, -HY, 0), (HX, HY, 0), (-HX, HY, 0)], Vector((0, 0, 1)))
    for name, (dc, n, _) in DOORS.items():
        t = Vector((-n.y, n.x, 0))
        p0, p1 = dc + t * (PASS_W / 2), dc - t * (PASS_W / 2)
        quad(bm, [p0, p1, p1 + n * (PASS_D + 0.01), p0 + n * (PASS_D + 0.01)], Vector((0, 0, 1)))
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for lp in f.loops:
            lp[uvl].uv = ((lp.vert.co.x + FLOOR_SPAN / 2) / FLOOR_SPAN, (lp.vert.co.y + FLOOR_SPAN / 2) / FLOOR_SPAN)
    mesh_obj("Floor", bm, "Floor_Stone")
    bm = bmesh.new()
    for flat in FLATS:
        wall_faces(bm, flat, 0.0, WALL_H)
    wall_uv(bm)
    mesh_obj("Walls", bm, "Wall_Verdigris")
    bm = bmesh.new()
    quad(bm, [(-HX, -HY, WALL_H), (HX, -HY, WALL_H), (HX, HY, WALL_H), (-HX, HY, WALL_H)], Vector((0, 0, -1)))
    box_uv(bm, CEIL_TILE)
    mesh_obj("Ceiling", bm, "Ceiling_Poppy")
    # gilt: the dado rail, a bead at the frieze's foot, the cornice's lip; the cornice itself copper
    bm = bmesh.new()
    for flat in FLATS:
        wall_strip(bm, flat, DADO_Z - 0.025, DADO_Z + 0.025, 0.03)
        wall_strip(bm, flat, FRIEZE_Z0 - 0.015, FRIEZE_Z0 + 0.015, 0.015, skip_doors=False)
        wall_strip(bm, flat, WALL_H - 0.06, WALL_H - 0.04, 0.10, skip_doors=False)
    box_uv(bm, 1.0)
    mesh_obj("Gilt_Mouldings", bm, "Gold_Trim")
    bm = bmesh.new()
    for flat in FLATS:
        wall_strip(bm, flat, FRIEZE_Z1, WALL_H - 0.06, 0.09, skip_doors=False)
    box_uv(bm, 1.0)
    mesh_obj("Cornice", bm, "Copper_Trim")


def door_frame(name):
    """A door's opening: the reveal through the wall, the passage behind (walls, ceiling, back wall; the floor is in Floor), and a gilt
    architrave on the room side."""
    dc, n, hinge = DOORS[name]
    t = Vector((-n.y, n.x, 0))
    hw, pw = DOOR_W / 2, PASS_W / 2
    bm = bmesh.new()
    for s in (-1, 1):
        p0, p1 = dc + t * (s * hw), dc + t * (s * hw) + n * WALL_T
        quad(bm, [(p0.x, p0.y, 0), (p1.x, p1.y, 0), (p1.x, p1.y, DOOR_H), (p0.x, p0.y, DOOR_H)], -t * s)
    p0, p1 = dc - t * hw, dc + t * hw
    quad(bm, [(p0.x, p0.y, DOOR_H), (p1.x, p1.y, DOOR_H), (p1.x + n.x * WALL_T, p1.y + n.y * WALL_T, DOOR_H),
              (p0.x + n.x * WALL_T, p0.y + n.y * WALL_T, DOOR_H)], Vector((0, 0, -1)))
    w0 = dc + n * WALL_T
    for s in (-1, 1):
        a, b = w0 + t * (s * hw), w0 + t * (s * pw)
        quad(bm, [(a.x, a.y, 0), (b.x, b.y, 0), (b.x, b.y, PASS_H), (a.x, a.y, PASS_H)], n)
    a, b = w0 - t * hw, w0 + t * hw
    quad(bm, [(a.x, a.y, DOOR_H), (b.x, b.y, DOOR_H), (b.x, b.y, PASS_H), (a.x, a.y, PASS_H)], n)
    back = dc + n * PASS_D
    for s in (-1, 1):
        a, b = w0 + t * (s * pw), back + t * (s * pw)
        quad(bm, [(a.x, a.y, 0), (b.x, b.y, 0), (b.x, b.y, PASS_H), (a.x, a.y, PASS_H)], -t * s)
    a, b = back - t * pw, back + t * pw
    quad(bm, [(a.x, a.y, 0), (b.x, b.y, 0), (b.x, b.y, PASS_H), (a.x, a.y, PASS_H)], -n)
    c0, c1 = w0 - t * pw, w0 + t * pw
    quad(bm, [(c0.x, c0.y, PASS_H), (c1.x, c1.y, PASS_H), (c1.x + n.x * (PASS_D - WALL_T), c1.y + n.y * (PASS_D - WALL_T), PASS_H),
              (c0.x + n.x * (PASS_D - WALL_T), c0.y + n.y * (PASS_D - WALL_T), PASS_H)], Vector((0, 0, -1)))
    box_uv(bm, 1.0)
    mesh_obj(f"Passage_{name}", bm, "Passage_Navy")
    bm = bmesh.new()
    yaw = math.atan2(t.y, t.x)
    for s in (-1, 1):
        add_box(bm, dc + t * (s * (hw + 0.045)) - n * 0.02 + Vector((0, 0, (DOOR_H + 0.09) / 2)), (0.09, 0.04, DOOR_H + 0.09), yaw)
    add_box(bm, dc - n * 0.025 + Vector((0, 0, DOOR_H + 0.09)), (DOOR_W + 0.30, 0.05, 0.06), yaw)
    add_box(bm, dc - n * 0.035 + Vector((0, 0, DOOR_H + 0.14)), (DOOR_W + 0.40, 0.07, 0.04), yaw)
    box_uv(bm, 1.0)
    mesh_obj(f"Architrave_{name}", bm, "Gold_Trim")


def build_leaf(name):
    """DoorLeaf_Hypnos_<name>: a 0.94 x 2.16 x 0.045 m leaf, origin on its hinge edge at the floor, standing open at 90 degrees into the room
    (as baked). Local +X runs from the hinge across the leaf; the picture is on both faces."""
    dc, n, hinge = DOORS[name]
    t = Vector((-n.y, n.x, 0))
    th = 0.045
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    corners = [(0, -th / 2), (DOOR_W, -th / 2), (DOOR_W, th / 2), (0, th / 2)]
    v = {}
    for i, (x, y) in enumerate(corners):
        v[(i, 0)] = bm.verts.new((x, y, 0))
        v[(i, 1)] = bm.verts.new((x, y, DOOR_H))
    faces = [([v[(0, 0)], v[(1, 0)], v[(1, 1)], v[(0, 1)]], "front"), ([v[(2, 0)], v[(3, 0)], v[(3, 1)], v[(2, 1)]], "back"),
             ([v[(1, 0)], v[(2, 0)], v[(2, 1)], v[(1, 1)]], "edge"), ([v[(3, 0)], v[(0, 0)], v[(0, 1)], v[(3, 1)]], "edge"),
             ([v[(0, 1)], v[(1, 1)], v[(2, 1)], v[(3, 1)]], "edge"), ([v[(3, 0)], v[(2, 0)], v[(1, 0)], v[(0, 0)]], "edge")]
    for vs, kind in faces:
        f = bm.faces.new(vs)
        for lp in f.loops:
            co = lp.vert.co
            if kind == "front":
                lp[uvl].uv = (co.x / DOOR_W, co.z / DOOR_H)
            elif kind == "back":
                lp[uvl].uv = (1 - co.x / DOOR_W, co.z / DOOR_H)
            else:
                lp[uvl].uv = (0.02 + 0.01 * (co.x / DOOR_W), 0.5 + 0.01 * co.z)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = mesh_obj(f"DoorLeaf_Hypnos_{name}", bm, f"Leaf_{name}")
    hinge_pt = dc + t * (hinge * DOOR_W / 2) - n * 0.03 - t * (hinge * (th / 2 + 0.005))
    ob.location = (hinge_pt.x, hinge_pt.y, 0.0)
    ob.rotation_euler = (0, 0, math.atan2(-n.y, -n.x))          # open into the room: local +X along the inward normal
    return ob


def build_veils():
    """decor_veil_<door>: a pleated navy velvet veil across each passage, VEIL_D out from the wall's inner face; no collider. Walking through
    a veil is where the scene teleports the walker to the matching veil (LOOPS), so the room is all one sees on the far side."""
    for name, (dc, n, _) in DOORS.items():
        t = Vector((-n.y, n.x, 0))
        bm = bmesh.new()
        nx, nz = 28, 6
        verts = []
        for j in range(nz + 1):
            row = []
            for i in range(nx + 1):
                u = i / nx
                off = 0.04 * math.sin(u * math.pi * 14) * (0.5 + 0.5 * j / nz)
                p = dc + n * (VEIL_D + off) + t * ((u - 0.5) * (PASS_W - 0.02))
                row.append(bm.verts.new((p.x, p.y, 0.01 + (PASS_H - 0.03) * j / nz)))
            verts.append(row)
        for j in range(nz):
            for i in range(nx):
                qf = bm.faces.new([verts[j][i], verts[j][i + 1], verts[j + 1][i + 1], verts[j + 1][i]])
                qf.normal_update()
                if qf.normal.dot(-n) < 0:
                    qf.normal_flip()
        box_uv(bm, 1.0)
        mesh_obj(f"decor_veil_{name}", bm, "Veil_Navy", smooth=True)


def build_placard():
    bm = bmesh.new()
    c = Vector((1.15, -HY + 0.012, 1.0))
    w, h = 0.42, 0.28
    f = bm.faces.new([bm.verts.new(c + Vector(d)) for d in ((-w / 2, 0, -h / 2), (w / 2, 0, -h / 2), (w / 2, 0, h / 2), (-w / 2, 0, h / 2))])
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = uv
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
    mesh_obj("Placard_Light", bm, "Sconce_Copper", smooth=True)
    bm = bmesh.new()
    add_box(bm, head + Vector((0, -0.004, -0.023)), (0.30, 0.012, 0.004))
    box_uv(bm, 1.0)
    mesh_obj("Placard_Light_Glow", bm, "Picture_Light_Emit")
    return c


SCONCES = [("N", -2.3), ("N", 2.3), ("S", -2.3), ("S", 2.3), ("W", -3.25)]     # (wall, position along the wall's tangent t = (-n.y, n.x))
SCONCE_Z = 2.05


def sconce_points():
    out = []
    for flat, u in SCONCES:
        n = FLATS[flat]
        t = Vector((-n.y, n.x, 0))
        out.append((flat, n * HALF[flat] + t * u, n, t))
    return out


def build_sconces():
    """Copper sconces: a wall plate, a curved arm, a dish and a glowing bulb."""
    met, bulbs = bmesh.new(), bmesh.new()
    for flat, w, n, t in sconce_points():
        base = w + Vector((0, 0, SCONCE_Z))
        plate = base - n * 0.012
        m = Matrix.Translation(plate) @ Matrix.Rotation(math.atan2(n.y, n.x), 4, "Z") @ Matrix.Diagonal((0.024, 0.10, 0.24, 1))
        bmesh.ops.create_cube(met, size=1.0, matrix=m)
        pts = []
        for i in range(9):
            s = i / 8
            pts.append(plate - n * (0.04 + 0.16 * s) + Vector((0, 0, 0.09 * math.sin(s * math.pi) - 0.05)))
        for i in range(8):
            add_cyl(met, pts[i], pts[i + 1], 0.013, seg=8)
        cup = pts[-1]
        add_cyl(met, cup + Vector((0, 0, -0.02)), cup + Vector((0, 0, 0.025)), 0.02, 0.06, seg=12)
        bc = cup + Vector((0, 0, 0.07))
        bmesh.ops.create_uvsphere(bulbs, u_segments=10, v_segments=6, radius=1.0, matrix=Matrix.Translation(bc) @ Matrix.Diagonal((0.03, 0.03, 0.05, 1)))
    box_uv(met, 1.0)
    mesh_obj("Sconces", met, "Sconce_Copper", smooth=True)
    box_uv(bulbs, 1.0)
    mesh_obj("Sconce_Bulbs", bulbs, "Lamp_Emit", smooth=True)


HAZE = [   # decor_haze_*: centre, size (w, h), yaw (deg), tilt (deg; 90 = lying flat), unused density note
    ((0.0, 1.7, 0.55), (3.0, 3.0), 0, 90),
    ((0.2, 1.5, 0.95), (3.6, 3.4), 30, 90),
    ((0.0, 1.7, 0.9), (2.6, 1.5), 0, 0),
    ((0.0, 1.7, 0.9), (2.6, 1.5), 60, 0),
    ((0.0, 1.7, 0.9), (2.6, 1.5), 120, 0),
    ((-0.6, -0.8, 0.35), (4.0, 3.2), 15, 90),
    ((1.2, -2.0, 0.6), (3.0, 1.2), 90, 0),
    ((-1.6, 2.2, 0.5), (3.0, 1.0), 20, 0),
]


def build_haze():
    """The Lethe basin's mist (PLAN 4.3): soft alpha cards round and over the basin and low over the floor. Each its own node, so the code can
    thicken them per pass (they are not in the bake). Their picture's alpha is the falloff; the material's alpha factor is the density."""
    for i, (c, (w, h), yaw, tilt) in enumerate(HAZE):
        bm = bmesh.new()
        uvl = bm.loops.layers.uv.new("UVMap")
        f = bm.faces.new([bm.verts.new((x * w / 2, 0, z * h / 2)) for x, z in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
        for lp, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
            lp[uvl].uv = uv
        ob = mesh_obj(f"decor_haze_{i:02d}", bm, "Haze")
        ob.location = c
        ob.rotation_euler = (math.radians(tilt), 0, math.radians(yaw))
        ob.visible_shadow = False


# ---------------------------------------------------------------- the furniture
def yaw_for(code, facing):
    return math.radians(COMPASS[facing] - NATIVE_FRONT[code])


def load_copy(code, objname):
    path = next(COPIES.glob(f"{code}_*_game.glb"))
    if f"{code}_mesh" in bpy.data.meshes:
        me = bpy.data.meshes[f"{code}_mesh"].copy()          # its own mesh: the second of a pair needs its own lightmap texels
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


def bbox(ob):
    vs = world_verts(ob)
    return Vector([min(v[i] for v in vs) for i in range(3)]), Vector([max(v[i] for v in vs) for i in range(3)])


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
            n = FLATS[how[1]]
            gap = how[2]
            reach = max(v.dot(n) for v in world_verts(ob))
            ob.location = Vector(ob.location) + n * (HALF[how[1]] - gap - reach)
            if how[0] == "hang":
                ob.location.z = how[3]
        elif how[0] == "on":
            sup = placed[how[1]]
            bpy.context.view_layer.update()
            lo, hi = bbox(sup)
            tgt = Vector(((lo.x + hi.x) / 2 + xy[0], (lo.y + hi.y) / 2 + xy[1], 0))
            hit = bvh_of(sup).ray_cast(Vector((tgt.x, tgt.y, 5.0)), Vector((0, 0, -1)))
            top = hit[0].z if hit[0] is not None else hi.z
            ob.location = (tgt.x, tgt.y, top - 0.003)
        bpy.context.view_layer.update()
        placed[objname] = ob
        lo, hi = bbox(ob)
        print(f"PLACE {objname}: ({lo.x:.2f}, {lo.y:.2f}, {lo.z:.2f}) .. ({hi.x:.2f}, {hi.y:.2f}, {hi.z:.2f})")
    # the leaning pieces: the transform into the mesh, the origin on the front edge of the foot (the code tips them about it)
    for nm, toward in LEAN.items():
        ob = placed[nm]
        lo, hi = bbox(ob)
        d = FLATS[toward]
        piv = Vector(((hi.x if d.x > 0 else lo.x) if d.x else (lo.x + hi.x) / 2, (hi.y if d.y > 0 else lo.y) if d.y else (lo.y + hi.y) / 2, 0.0))
        ob.data.transform(ob.matrix_world)
        ob.matrix_world = Matrix.Identity(4)
        ob.data.transform(Matrix.Translation(-piv))
        ob.location = piv
        ob.rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()
    return placed


CLOCK_FACE = (0.41, 0.26, 0.044)      # HY-08's face: centre height and radius (fractions of the clock's height), offset across (of its width)
MIRROR_GLASS = (0.53, 0.215, 0.195)   # HY-06's glass: centre height, half height, half width (fractions of the mirror's height)


def build_clock(placed):
    """The clock's dial and hands. The dial covers the copy's painted face (CLOCK_FACE, read from the copy's view sheet) so only the code's
    hands show: decor_clock_hand_min / _hour, origin at the dial's centre, turned about the dial's normal (Blender +X: the clock faces east)."""
    ck = placed["HY-08_clock"]
    lo, hi = bbox(ck)
    H = hi.z - lo.z
    zc = lo.z + CLOCK_FACE[0] * H
    yc = (lo.y + hi.y) / 2 + CLOCK_FACE[2] * (hi.y - lo.y)
    r = CLOCK_FACE[1] * H
    hit = bvh_of(ck).ray_cast(Vector((hi.x + 0.3, yc, zc)), Vector((-1, 0, 0)))
    fx = hit[0].x if hit[0] is not None else hi.x
    c = Vector((fx + 0.003, yc, zc))
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    seg = 32
    ring = [bm.verts.new(c + Vector((0, r * math.cos(2 * math.pi * i / seg), r * math.sin(2 * math.pi * i / seg)))) for i in range(seg)]
    f = bm.faces.new(ring)
    for lp in f.loops:
        d = lp.vert.co - c
        lp[uvl].uv = (0.5 + d.y / (2 * r), 0.5 + d.z / (2 * r))       # seen from the east (looking west), +y is to the viewer's right
    f.normal_update()
    if f.normal.x < 0:
        f.normal_flip()
    bmesh.ops.triangulate(bm, faces=[f])
    mesh_obj("Clock_Dial", bm, "Clock_Dial")
    for nm, length, width, ang, dx in (("decor_clock_hand_min", 0.74, 0.07, 0.0, 0.006), ("decor_clock_hand_hour", 0.50, 0.10, 60.0, 0.002)):
        bm = bmesh.new()
        add_box(bm, Vector((0.0, 0, r * length / 2 - r * 0.08)), (0.003, r * width, r * length + r * 0.16))
        bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=10, radius1=r * 0.09, radius2=r * 0.09, depth=0.004,
                              matrix=Matrix.Rotation(math.pi / 2, 4, "Y"))
        box_uv(bm, 1.0)
        ob = mesh_obj(nm, bm, "Hand_Gilt")
        ob.location = c + Vector((dx, 0, 0))
        ob.rotation_euler = (math.radians(ang), 0, 0)
    return c, r


def build_mirror_still(placed):
    """HY-06's glass shows the Thanatos nave (PLAN 4.3): an oval just proud of the copy's glass, its own emissive picture (no lightmap)."""
    mi = placed["HY-06_wall_mirror"]
    lo, hi = bbox(mi)
    H = hi.z - lo.z
    zc, ry, rz = lo.z + MIRROR_GLASS[0] * H, MIRROR_GLASS[2] * H, MIRROR_GLASS[1] * H
    yc = (lo.y + hi.y) / 2
    hit = bvh_of(mi).ray_cast(Vector((hi.x + 0.3, yc, zc)), Vector((-1, 0, 0)))
    fx = hit[0].x if hit[0] is not None else hi.x
    c = Vector((fx + 0.004, yc, zc))
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    seg = 40
    ring = [bm.verts.new(c + Vector((0, ry * math.cos(2 * math.pi * i / seg), rz * math.sin(2 * math.pi * i / seg)))) for i in range(seg)]
    f = bm.faces.new(ring)
    for lp in f.loops:
        d = lp.vert.co - c
        lp[uvl].uv = (0.5 + d.y / (2 * rz), 0.5 + d.z / (2 * rz))
    f.normal_update()
    if f.normal.x < 0:
        f.normal_flip()
    bmesh.ops.triangulate(bm, faces=[f])
    ob = mesh_obj("Mirror_Still", bm, "Mirror_Thanatos")
    ob.visible_shadow = False
    return c


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


def yaw_facing(d):
    """An Arrive_'s -Y axis is the way you face (as in the Nyx room): the yaw that turns -Y to the direction d."""
    return math.atan2(d.x, -d.y)


def veil_point(name, d):
    dc, n, _ = DOORS[name]
    return dc + n * d


ARRIVE_TAG = {"In": "S", "N": "N", "E": "E", "W": "W"}


def build_layout(placed, bed_spot):
    """COL_ boxes: the floor, each wall as boxes round its door, each passage's sides and back, a box per standing piece. Markers, links,
    zones and spots as PLAN 4.3, with the loops through the veils (LOOPS)."""
    col_box("COL_floor", (-HX - 1.5, -HY - 1.5, -0.2), (HX + 1.5, HY + 1.5, 0.0))
    for flat in FLATS:
        a, b, inward, t, holes, L = wall_spans(flat)
        n = -inward
        mid = (a + b) / 2
        cuts = [-L - WALL_T] + [u for h in holes for u in h] + [L + WALL_T]
        for i in range(0, len(cuts) - 1):
            u0, u1 = cuts[i], cuts[i + 1]
            p0, p1 = mid + t * u0, mid + t * u1
            q0, q1 = p0 + n * WALL_T, p1 + n * WALL_T
            lo = (min(p0.x, p1.x, q0.x, q1.x), min(p0.y, p1.y, q0.y, q1.y))
            hi = (max(p0.x, p1.x, q0.x, q1.x), max(p0.y, p1.y, q0.y, q1.y))
            if i % 2 == 0:
                col_box(f"COL_wall_{flat}_{i // 2}", (*lo, 0), (*hi, WALL_H))
            else:
                col_box(f"COL_wall_{flat}_head", (*lo, DOOR_H), (*hi, WALL_H))
    for name, (dc, n, _) in DOORS.items():
        t = Vector((-n.y, n.x, 0))
        for s in (-1, 1):
            p0 = dc + n * WALL_T + t * (s * PASS_W / 2)
            p1 = dc + n * (PASS_D + 0.15) + t * (s * (PASS_W / 2 + 0.15))
            col_box(f"COL_pass_{ARRIVE_TAG[name]}_{'a' if s < 0 else 'b'}", (min(p0.x, p1.x), min(p0.y, p1.y), 0), (max(p0.x, p1.x), max(p0.y, p1.y), PASS_H))
        p0 = dc + n * PASS_D - t * (PASS_W / 2)
        p1 = dc + n * (PASS_D + 0.15) + t * (PASS_W / 2)
        col_box(f"COL_pass_{ARRIVE_TAG[name]}_back", (min(p0.x, p1.x), min(p0.y, p1.y), 0), (max(p0.x, p1.x), max(p0.y, p1.y), PASS_H))
    for nm, ob in placed.items():
        if nm.startswith(("HY-00", "HY-08", "HY-09", "HY-10", "HY-12", "HY-11", "HY-06")):
            continue                                   # on the furniture, on the wall, or flat on the floor
        lo, hi = bbox(ob)
        col_box(f"COL_{nm}", lo, hi)
    north = Vector((0, 1, 0))
    empty("Marker_Spawn", (SPAWN.x, SPAWN.y, 0), "Spawn", yaw=yaw_facing(north))
    empty("Marker_Entrance", (0, -HY + 0.3, 0), "Entrance", yaw=yaw_facing(north))
    empty("Marker_Exit", bed_spot, "Exit", yaw=yaw_facing(Vector((1, 0, 0))), note="the bed: the way out is to lie down (Spot_bed)")
    empty("Arrive_Hypnos_In", (SPAWN.x, SPAWN.y, 0), yaw=yaw_facing(north), note="where the walker stands coming in from Selene's painted door")
    for src, dst in LOOPS.items():
        p = veil_point(src, VEIL_D)
        q = veil_point(dst, VEIL_D)
        d_in = -DOORS[dst][1]
        shift = q - p
        q_arr = veil_point(dst, VEIL_D - 0.05)
        link = f"Link_Hypnos_{ARRIVE_TAG[src]}"
        arr = f"Arrive_Hypnos_{ARRIVE_TAG[dst]}"
        empty(link, (p.x, p.y, 0), to_scene=SCENE, to_arrive=arr,
              note=f"crossing this veil outward: add ({shift.x:.2f}, {shift.y:.2f}) m (Blender x, y) to the walker, keep the yaw")
        empty(arr, (q_arr.x, q_arr.y, 0), yaw=yaw_facing(d_in), note="just inside the veil, facing into the room")
        dc, n, _ = DOORS[src]
        t = Vector((-n.y, n.x, 0))
        a = dc + n * VEIL_D - t * (PASS_W / 2)
        b = dc + n * PASS_D + t * (PASS_W / 2)
        col_box(f"Zone_trigger_{ARRIVE_TAG[src]}", (min(a.x, b.x), min(a.y, b.y), 0), (max(a.x, b.x), max(a.y, b.y), PASS_H))
    empty("Spot_bed", bed_spot, note="play.js target 'Lie down', live after the third pass; its use() ends the room (exitPath onto the pillow)")
    empty("Link_Hypnos_Bed", bed_spot, to_scene="rdwe_god_morpheus", to_arrive="Arrive_Morpheus_In")
    bed = placed["HY-05_bed"]
    lo, hi = bbox(bed)
    col_box("Zone_use_bed", (lo.x - 0.6, lo.y - 0.3, 0), (lo.x + 0.4, hi.y + 0.3, 2.0))
    for name in DOORS:
        leaf = bpy.data.objects[f"DoorLeaf_Hypnos_{name}"]
        leaf["hinge"] = {"In": "west jamb", "N": "west jamb", "E": "north jamb", "W": "north jamb"}[name]
        leaf["swing_deg"] = 90
        leaf["state"] = "open into the room (as baked)"


# ---------------------------------------------------------------- lights (for the bake and the stills; never exported)
SCONCE_W = 10.0          # each sconce's bulb (W)
PLACARD_W = 0.09         # the placard's picture light
LAMP_W = 9.0             # the bedside lamp (HY-00), under its shade
BASIN_W = 60.0           # the Lethe glow: a cool disc light over the basin, the mist's light
FILL_W = 220.0           # the drowsy fill: a large soft panel under the ceiling, pointing down (the even part of the light)


def add_lights(placard_c):
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
        light(f"Sconce_{i}", "POINT", w - n * 0.20 + Vector((0, 0, SCONCE_Z + 0.02)), SCONCE_W, (1.0, 0.68, 0.40), 0.03)
    lamp = bpy.data.objects.get("HY-00_lamp")
    if lamp:
        lo, hi = bbox(lamp)
        H = hi.z - lo.z
        c = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z + LAMP_BULB_Z * H))
        light("Lamp_Bulb", "POINT", c, LAMP_W, (1.0, 0.62, 0.34), 0.03)
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.025, matrix=Matrix.Translation(c + Vector((0, 0, 0.01))))
        box_uv(bm, 1.0)
        mesh_obj("Lamp_Glow", bm, "Lamp_Emit", smooth=True)
    pc = placard_c + Vector((0, 0.16, 0.14 + 0.06 + 0.05 - 0.03))
    ob, d = light("Placard_Light", "AREA", pc, PLACARD_W, (1.0, 0.85, 0.65), 0.0)
    d.shape, d.size, d.size_y = "RECTANGLE", 0.28, 0.02
    ob.rotation_euler = (placard_c - pc).to_track_quat("-Z", "Y").to_euler()
    ob, d = light("Basin_Glow", "AREA", (0, 1.7, 1.6), BASIN_W, (0.62, 0.74, 1.0), 0.0)
    d.shape, d.size = "DISK", 1.2
    ob, d = light("Fill", "AREA", (0, 0, WALL_H - 0.25), FILL_W, (0.80, 0.84, 1.0), 0.0)
    d.shape, d.size, d.size_y = "RECTANGLE", 5.0, 6.0


LAMP_BULB_Z = 0.80          # the lamp's bulb under its mushroom shade, as a fraction of the lamp's height


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("Night")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
    bg.inputs["Strength"].default_value = 0.0


NOSHADOW = ("Lamp_Emit", "Sconce_Copper", "Picture_Light_Emit", "Haze", "Hand_Gilt", "Mirror_Thanatos")


def build_all():
    global ART, LAYOUT
    clear_scene()
    MATS.clear()
    ART = bpy.data.collections.new("Art")
    LAYOUT = bpy.data.collections.new("Layout")
    sc = bpy.context.scene
    sc.collection.children.link(ART)
    sc.collection.children.link(LAYOUT)
    gen = {"floor": mk_image("Hypnos_Floor", floor_pixels()), "wall": mk_image("Hypnos_Wall", wall_pixels()),
           "ceiling": mk_image("Hypnos_Ceiling", ceiling_pixels()), "placard": mk_image("Hypnos_Placard", placard_pixels()),
           "dial": mk_image("Hypnos_Dial", dial_pixels()), "nave": mk_image("Hypnos_Mirror_Nave", nave_pixels()),
           "haze": mk_image("Hypnos_Haze", haze_pixels())}
    for k in ("In", "N", "E", "W"):
        gen[f"leaf_{k}"] = mk_image(f"Hypnos_Leaf_{k}", leaf_pixels(k))
    make_materials(gen)
    build_shell()
    for name in DOORS:
        door_frame(name)
        build_leaf(name)
    build_veils()
    pc = build_placard()
    build_sconces()
    build_haze()
    placed = place_all()
    build_clock(placed)
    build_mirror_still(placed)
    bed = placed["HY-05_bed"]
    lo, hi = bbox(bed)
    hit = bvh_of(bed).ray_cast(Vector((hi.x - 0.45, (lo.y + hi.y) / 2, 5.0)), Vector((0, 0, -1)))
    bed_spot = Vector((hi.x - 0.45, (lo.y + hi.y) / 2, hit[0].z if hit[0] is not None else 0.7))
    build_layout(placed, bed_spot)
    add_lights(pc)
    setup_world()
    sc.unit_settings.system = "METRIC"
    for o in ART.objects:
        if o.type == "MESH" and o.data.materials and o.data.materials[0].name in NOSHADOW:
            o.visible_shadow = False


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    scrub_private()
    bpy.ops.wm.save_mainfile()


# ================================================================ bake (R1)
def furn(*codes):
    return tuple(f"{SET}_{c}_" for c in codes)


LEAVES = ("Leaf_In", "Leaf_N", "Leaf_E", "Leaf_W")
GROUPS = [
    ("Floor_Stone", "Wall_Verdigris", "Gold_Trim", "Copper_Trim", "Placard", "Clock_Dial") + LEAVES,                       # 0 floor, walls, trim, leaves
    ("Ceiling_Poppy", "Passage_Navy", "Veil_Navy"),                                                                      # 1 the ceiling and the passages
    furn("HY-01", "HY-02", "HY-03", "HY-04", "HY-05", "HY-06", "HY-07", "HY-11"),                                        # 2 the big furniture
    furn("HY-00", "HY-08", "HY-09", "HY-10", "HY-12", "P7", "P10", "P11"),                                               # 3 the smalls and the props
]
MIN_DENSITY = [40, 24, 60, 60]          # px per metre wanted on each map (the search takes the smallest page that gives it)
PAGES = [None, None, None, None]        # auto; --pages a,b,c,d fixes them
if arg("--pages"):
    PAGES = [None if v == "auto" else int(v) for v in arg("--pages").split(",")]
NOLM = ("Lamp_Emit", "Sconce_Copper", "Picture_Light_Emit", "Mirror_Thanatos", "Haze", "Hand_Gilt")
KEEP_NODES = ("DoorLeaf_", "decor_")    # exported as their own nodes (the scene code moves, tips or thickens them), not merged by material
MAIN = ("Floor_Stone", "Wall_Verdigris", "Ceiling_Poppy", SET + "_")   # the surfaces held to the exposure rule
NOT_MAIN = (f"{SET}_HY-00_lamp",)       # the lamp's own body, inches from its bulb: reported, not held
TARGET_P90 = arg("--target", 0.90, float)
CLIP_CAP = arg("--clip-cap", 0.98, float)     # and no main surface's p99 above this (0 turns the cap off)


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
        assert len(ob.data.materials) == 1, ob.name
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
        tiny = [f for f in bm.faces if f.calc_area() < 1e-9]       # zero-area slivers left by the decimation
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
    copies stage's islands, which do not overlap) as one square, and the squares are shelf-packed here, sized by each piece's area."""
    furn_objs = [o for o in objs if o.data.materials[0].name.startswith(SET + "_")]
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
            poly_lstart = np.zeros(len(me.polygons), np.int32)
            me.polygons.foreach_get("loop_start", poly_lstart)
            poly_ltot = np.zeros(len(me.polygons), np.int32)
            me.polygons.foreach_get("loop_total", poly_ltot)
            cen = np.zeros(len(me.polygons) * 3, np.float32)
            me.polygons.foreach_get("center", cen)
            cen = cen.reshape(-1, 3)
            keys = [0] * len(me.polygons)
            if o.name.startswith(f"{SET}_HY-01_"):
                keys = [0 if c < -2.0 else 1 for c in cen[:, 1]]      # the bedside pair: the south one at y -3.2, the north one at y -0.8
            if o.name.startswith(f"{SET}_P10_"):
                keys = [0 if c < 0 else 1 for c in cen[:, 0]]         # the urn pair, west and east of the north door
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
        for prefix, w in (("Sconce_", SCONCE_W), ("Lamp_Bulb", LAMP_W), ("Basin_Glow", BASIN_W), ("Fill", FILL_W), ("Placard_Light", PLACARD_W)):
            if ob.name.startswith(prefix):
                ob.data.energy = w


def stage_bake():
    reset_lights()
    exp = make_export_objects()
    bpy.data.collections["Art"].hide_render = True
    for o in exp.values():
        if o.name.startswith("decor_haze_"):
            o.hide_render = True                           # the mist is the code's: it neither lights nor shades the bake
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


def set_drowse(level):
    """The set piece's state after `level` passes (PLAN 4.3): the leaning pieces tipped 2 degrees a pass (at most 10), the mist denser, the
    clock's hands as the code would leave them."""
    th = math.radians(min(10.0, 2.0 * level))
    for nm, toward in LEAN.items():
        ob = bpy.data.objects[nm]
        d = FLATS[toward]
        ob.rotation_euler = (-d.y * th, d.x * th, 0)        # the top tips toward d, about the foot's front edge
    m = bpy.data.materials["Haze"]
    mul = next(n for n in m.node_tree.nodes if n.type == "MATH")
    mul.inputs[1].default_value = min(0.95, 0.30 * (1.0 + 0.6 * level))


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
    E = EYE
    shots = {
        "1_arrival": (look_cam("arrival", (SPAWN.x, SPAWN.y, E), (0.0, 2.0, E + 0.25), 72.0), (1920, 1080), STILLS, 0),
        "2_wide": (look_cam("wide", (-3.0, -3.6, 3.0), (0.9, 1.2, 0.8), 72.0), (1920, 1080), STILLS, 0),
        "3_doors": (look_cam("doors", (1.6, -1.4, E), (-1.2, 2.6, E + 0.2), 72.0), (1920, 1080), STILLS, 0),
        "4_drowse": (look_cam("drowse", (2.2, -1.2, E), (-3.0, 2.9, 1.05), 72.0), (1920, 1080), STILLS, 4),
        "pass0": (look_cam("drowse0", (2.2, -1.2, E), (-3.0, 2.9, 1.05), 72.0), (1280, 720), work(), 0),
        "veil_N": (look_cam("veil", (0.0, 2.9, E), (0.0, 6.0, E), 72.0), (1280, 720), work(), 0),
        "bed4": (look_cam("bed", (-0.9, -0.9, E), (2.6, -2.0, E - 0.15), 72.0), (1280, 720), work(), 4),
        "clock": (look_cam("clock", (-1.9, -2.5, 1.25), (-3.2, -2.5, 1.05), 40.0), (1280, 720), work(), 0),
        "plan": (look_cam("plan", (0, 0, 20), None, ortho=2 * (HY + PASS_D) + 0.6), (1400, 1400), work(), 0),
    }
    hide_plan = [o for o in bpy.data.collections["Art"].objects if o.name.startswith(("Ceiling", "Cornice", "Gilt", "decor_haze", "Passage_"))]
    which = arg("--only", "all")
    for key, (cam, (w, h), folder, level) in shots.items():
        if which != "all" and key not in which.split(","):
            continue
        sc.camera = cam
        set_drowse(level)
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
    set_drowse(0)
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
