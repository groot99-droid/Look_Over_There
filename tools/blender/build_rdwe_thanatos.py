"""Builds Right Door, Wrong Exit's god room Thanatos, "The Quiet Nave" (`rdwe_god_thanatos`), in Blender: the reduced game copies of the
owner's Thanatos furniture set and two bought props, the long moonlit nave of banded columns with the bedchamber apse at its end, the set piece
(the apse that slides away from a walker in a hurry while the nave grows in front of it, and the butterflies), the night bake, and
world/rdwe_god_thanatos.glb with its lightmaps.

Re-runnable, from the repo root (docs/BLENDER.md, docs/BLENDER_AREAS.md section 7):

    blender -b --factory-startup --python tools/blender/build_rdwe_thanatos.py -- --stage copies --src <folder>   (the 13 originals and 2 props -> reduced copies)
    blender -b --factory-startup --python tools/blender/build_rdwe_thanatos.py -- --stage art                     (the room; saves blender/scenes/rdwe_god_thanatos.blend)
    blender -b --factory-startup blender/scenes/rdwe_god_thanatos.blend --python tools/blender/build_rdwe_thanatos.py -- --stage bake [--samples 512] [--device cpu]
    blender -b --factory-startup blender/scenes/rdwe_god_thanatos.blend --python tools/blender/build_rdwe_thanatos.py -- --stage export
    blender -b --factory-startup blender/scenes/rdwe_god_thanatos.blend --python tools/blender/build_rdwe_thanatos.py -- --stage render [--render-samples 128]
    (--stage bake,export,render runs several in one go; --stage views writes view sheets of the copies)
    then, in plain Python (Pillow): each lightmap PNG -> world/lightmaps/rdwe_god_thanatos_<n>.webp (q90), and
    python tools/webp_glb.py blender/work/farway_rdwe_god_thanatos/rdwe_god_thanatos_raw.glb world/rdwe_god_thanatos.glb <q>
    (docs/renders/rdwe_god_thanatos/README.md has the exact steps; the work folder is blender/work/farway_rdwe_god_thanatos, git-ignored)

The structure is the Nyx room's (tools/blender/build_rdwe_nyx.py) by way of the Hypnos room's: the same copies stage, bake (R1, the exposure
rule --target / --clip-cap), export (Draco, then tools/webp_glb.py) and stills. Stage `copies` reads the originals (never writes them). The
exporter's objects (COL_, DoorLeaf_, Marker_, Link_, Arrive_, Zone_, Spot_) are kept in the `Layout` collection for
tools/blender/export_scene.py, which is not on main yet, so no world/rdwe_god_thanatos.json is written here.

Axes: Blender metres, x east, y north, z up, the nave's axis on x = 0, the floor at z = 0. The glTF exporter's +Y up turns Blender (x, y, z)
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
SCENE = "rdwe_god_thanatos"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
COPIES = ROOT / "blender/models/rdwe_thanatos"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"
MARGIN_PX = 8
SET = "Thanatos"

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 512, int)
DEVICE = arg("--device", "auto")
SRC = Path(arg("--src", str(ROOT / "blender/work/thanatos_source")))
ONLY = arg("--only", "all")


def work():
    d = Path(arg("--work", str(ROOT / f"blender/work/farway_{SCENE}")))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- the pieces (manifest: Thanatos_collection_manifest.csv; budgets: PLAN section 5)
# code, original file, short name, triangle budget, base colour size (px)
PIECES = [
    ("TH-00", "TH-00_Thanatos_Lamp.glb", "lamp", 15000, 1024),
    ("TH-01", "TH-01_Thanatos_Bedside_Table.glb", "bedside_table", 15000, 1024),
    ("TH-02", "TH-02_Thanatos_Armchair.glb", "armchair", 18000, 1024),
    ("TH-03", "TH-03_Thanatos_Dresser.glb", "dresser", 18000, 1024),
    ("TH-04", "TH-04_Thanatos_Tall_Cabinet.glb", "tall_cabinet", 18000, 1024),
    ("TH-05", "TH-05_Thanatos_Bed.glb", "bed", 24000, 2048),
    ("TH-06", "TH-06_Thanatos_Wall_Mirror.glb", "wall_mirror", 15000, 1024),
    ("TH-07", "TH-07_Thanatos_Writing_Desk.glb", "writing_desk", 18000, 1024),
    ("TH-08", "TH-08_Thanatos_Clock.glb", "clock", 15000, 512),
    ("TH-09", "TH-09_Thanatos_Hourglass.glb", "hourglass", 15000, 512),
    ("TH-10", "TH-10_Thanatos_Vase.glb", "vase", 15000, 512),
    ("TH-11", "TH-11_Thanatos_Rug.glb", "rug", 2000, 1024),             # a flat 12 mm slab: 2k triangles hold its edge; the texture is the rug
    ("TH-12", "TH-12_Thanatos_Textiles.glb", "textiles", 15000, 1024),
    # the Higgsfield props PLAN section 7 gives Thanatos (normalised by the generator; `size` is the plan's W x H x D in metres)
    ("P5", "P5.glb", "thanatos_statue", 15000, 1024),
    ("P13", "P13.glb", "torchere", 5000, 512),       # placed six times and every copy is drawn: 5k each (the plan's 10k would be 60k drawn)
]
PROP_SIZE = {"P5": (1.1, 2.5, 0.8), "P13": (0.45, 1.8, 0.45)}
PER_AXIS = set()
FIX_UV = set()        # pieces given the stricter sliver cut and no island averaging up front (any piece whose UVs pack to almost nothing gets it anyway)
BY_WIDTH = set()


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
            bpy.data.objects.remove(o)             # any punctual light in a source goes too: the room sets its own lamp light
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


def uv_cover(me):
    """The share of the UV square the islands cover (a healthy pack is 0.4 to 0.7)."""
    uv = me.uv_layers[0].data
    tot = 0.0
    for p in me.polygons:
        pts = [uv[i].uv for i in p.loop_indices]
        n = len(pts)
        tot += abs(sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))) / 2
    return tot


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
    cover = uv_cover(me)
    if cover < 0.20 and code not in FIX_UV:
        # Hypnos's P10 lesson: slivers left by the collapse (flowers, tassels) blow up the island averaging and every real island packs to
        # almost nothing, so the piece bakes black. Cut the slivers harder and pack again without the averaging.
        print(f"  {code} UV cover {cover:.3f}: the sliver fix")
        bm = bmesh.new()
        bm.from_mesh(me)
        tiny = [f for f in bm.faces if f.calc_area() < (diag * 1e-4) ** 2]
        if tiny:
            bmesh.ops.delete(bm, geom=tiny, context="FACES")
        bm.to_mesh(me)
        bm.free()
        select_only([cp])
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.002, scale_to_bounds=False)
        bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=3.0 / px, shape_method="CONCAVE")
        bpy.ops.object.mode_set(mode="OBJECT")
        cover = uv_cover(me)
    print(f"  {code} UV cover {cover:.3f}")
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


# ================================================================ the room (PLAN section 4.6)
NAVE_HW = 2.0                              # the nave: 4 m wide
NAVE_Y0, NAVE_Y1 = -11.0, 5.0              # 16 m long: four 4 m bays
SPRING = 3.0                               # the nave's walls; a semicircular barrel vault of radius 2 above them, to 5 m
VAULT_R = NAVE_HW
APSE_HW = 4.0                              # the apse: 8 m wide ...
APSE_Y0, APSE_Y1 = 5.0, 12.0               # ... and 7 m deep
APSE_T = 0.3                               # its front wall (the arch wall), y 5.0 to 5.3
APSE_IN = APSE_Y0 + APSE_T
APSE_WALL_H = 4.8                          # walls to 4.8 m, then a shallow dome to 6 m
DOME_TOP = 6.0
ARCH_SPRING = 2.7                          # the arch into the apse: the nave's 4 m width, a round head to 4.7 m
EXT_SEGS, EXT_SEG = 6, 2.0                 # the hall that grows: 12 m more of nave where the apse stands, in 2 m segments
SLIDE_MAX = EXT_SEGS * EXT_SEG
WALL_T = 0.2
EYE = 0.95                                 # the RDWE walker's eye at RDWE_SCALE 1.7 (controls.js: 1.62 / 1.7)
DOOR_W, DOOR_H = 0.94, 2.16
SPAWN = Vector((0.0, -10.0, 0.0))
COL_R, COL_IN = 0.20, 0.05                 # the banded columns: radius; their axis this far inside the wall line (engaged)
NAVE_COLS = [NAVE_Y0 + 0.18, -7.0, -3.0, 1.0, NAVE_Y1 - 0.18]
EXT_COLS = [9.0, 13.0, NAVE_Y1 + SLIDE_MAX - 0.18]
APSE_COLS = [(-3.95, APSE_IN + 0.05), (3.95, APSE_IN + 0.05), (-3.95, APSE_Y1 - 0.05), (3.95, APSE_Y1 - 0.05),
             (-0.85, APSE_Y1 - 0.05), (0.85, APSE_Y1 - 0.05)]
WIN_HW, WIN_Z0, WIN_ZS = 0.40, 1.45, 2.05  # the high windows: half width, sill, springing of the round head (apex 2.45)
VAL_LOW, VAL_CUSP, VAL_TOP = 2.62, 2.74, 2.98   # the teal valances: the scallops' lowest point, the cusps, the top rail
SCALLOP = 0.5
VEST_HW, VEST_D, VEST_H = 0.70, 1.20, 2.60      # the small vestibule behind the exit door, where the morning light is
WALL_TILE_U, WALL_TILE_V = 2.0, 5.0        # the wall picture covers 2 m of wall and 5 m of height
FLOOR_TILE = 2.0                           # the floor picture: 2 x 2 m (four 1 m squares)
LM_ROOM = ("Floor_Checker", "Wall_Cream", "Vault_Coffer", "Column_Band", "Valance_Teal", "Gold_Trim", "Black_Stone")

COMPASS = {"E": 0, "NE": 45, "N": 90, "NW": 135, "W": 180, "SW": 225, "S": 270, "SE": 315}
# which way each copy faces as made (read by eye from the copies' view sheets): the compass angle its front points to in Blender.
NATIVE_FRONT = {f"TH-{i:02d}": 0 for i in range(13)}
NATIVE_FRONT.update({"P5": 270, "P13": 270})
# the walls pieces stand against: outward normal, the wall's inner face along that normal
WALLPLANE = {"W": (Vector((-1, 0, 0)), APSE_HW), "E": (Vector((1, 0, 0)), APSE_HW), "N": (Vector((0, 1, 0)), APSE_Y1),
             "nW": (Vector((-1, 0, 0)), NAVE_HW), "nE": (Vector((1, 0, 0)), NAVE_HW)}

# placement (PLAN 4.6), all in the apse but the torcheres: code, object name, (x, y), facing, how:
# ("floor"), ("wall", plane, gap), ("hang", plane, gap, z), ("on", support, (dx, dy))
PLACE = [
    ("TH-11", "TH-11_rug", (0.0, 8.3), "E", ("floor",)),
    ("TH-05", "TH-05_bed", (-2.85, 8.5), "E", ("wall", "W", 0.03)),
    ("TH-01", "TH-01_bedside_table_N", (-3.75, 9.7), "E", ("wall", "W", 0.04)),
    ("TH-01", "TH-01_bedside_table_S", (-3.75, 7.3), "E", ("wall", "W", 0.04)),
    ("TH-03", "TH-03_dresser", (3.6, 8.0), "W", ("wall", "E", 0.03)),
    ("TH-06", "TH-06_wall_mirror", (3.9, 8.0), "W", ("hang", "E", 0.02, 1.05)),
    ("TH-04", "TH-04_tall_cabinet", (3.4, 6.0), "W", ("wall", "E", 0.04)),
    ("TH-07", "TH-07_writing_desk", (3.3, 10.2), "W", ("wall", "E", 0.03)),
    ("TH-02", "TH-02_armchair", (2.4, 10.2), "E", ("floor",)),
    ("P5", "P5_thanatos_statue", (-1.6, 11.2), "S", ("floor",)),
    # the smalls, on the furniture
    ("TH-00", "TH-00_lamp", (0.0, 0.0), "E", ("on", "TH-01_bedside_table_N")),
    ("TH-10", "TH-10_vase", (0.0, 0.0), "E", ("on", "TH-01_bedside_table_S")),
    ("TH-08", "TH-08_clock", (0.0, -0.28), "W", ("on", "TH-03_dresser")),
    ("TH-09", "TH-09_hourglass", (0.0, 0.30), "W", ("on", "TH-07_writing_desk")),
    ("TH-12", "TH-12_textiles", (0.62, 0.0), "E", ("on", "TH-05_bed")),
]
TORCH_Y = [NAVE_COLS[0] + 0.75, -7.0 + 0.75, -3.0 + 0.75]       # the six torcheres, just north of the first three column pairs (clear of the windows' light)
for _i, _y in enumerate(TORCH_Y):
    PLACE.append(("P13", f"P13_torchere_W{_i}", (-1.7, _y), "E", ("wall", "nW", 0.06)))
    PLACE.append(("P13", f"P13_torchere_E{_i}", (1.7, _y), "W", ("wall", "nE", 0.06)))

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
GLYPHS["Q"] = ["01110", "10001", "10001", "10001", "10101", "10010", "01101"]
GLYPHS["K"] = ["10001", "10010", "10100", "11000", "10100", "10010", "10001"]


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


GOLD_S = (0.86, 0.66, 0.30)       # sRGB gold for the painted lines
TEAL_S = (0.08, 0.44, 0.46)
CREAM_S = (0.84, 0.79, 0.68)
BLACK_S = (0.05, 0.05, 0.055)


def marble(shape, seed, base, vein, r=24, amount=0.5):
    """A seamless marble: a base colour with soft cloud and thin wandering veins."""
    n1 = noise(shape, r, seed)
    n2 = noise(shape, max(2, r // 6), seed + 1)
    img = np.ones(shape + (3,), np.float32) * np.array(base, np.float32)
    img *= (0.90 + 0.16 * n1 + 0.05 * n2)[..., None]
    v = np.abs(((n1 * 6.0 + n2 * 1.2) % 1.0) - 0.5)
    vv = np.clip(1 - v / 0.025, 0, 1) * (n2 > 0.35) * amount
    return img * (1 - vv[..., None]) + np.array(vein, np.float32) * vv[..., None]


def floor_pixels():
    """The floor, a 2 x 2 m tile: 1 m squares of cream marble and dark slate in a checker (the nave in HY-06's mirror), fine joints."""
    S = 1024
    ppm = S / FLOOR_TILE
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32) / ppm
    chk = (np.floor(xx) + np.floor(yy)) % 2
    cream = marble((S, S), 3, (0.82, 0.78, 0.69), (0.62, 0.56, 0.46), 30, 0.45)
    slate = marble((S, S), 5, (0.40, 0.40, 0.42), (0.62, 0.62, 0.62), 22, 0.55)
    img = np.where(chk[..., None] > 0.5, cream, slate)
    j = np.minimum(np.abs(xx - np.round(xx)), np.abs(yy - np.round(yy))) < 0.004
    img[j] *= 0.65
    return np.clip(img, 0, 1).astype(np.float32)


def wall_pixels():
    """The walls, 2 m wide and 5 m tall from the floor: cream ashlar in 0.5 m courses, a black marble skirting with a gold line, a teal dado
    band between gold lines at 0.9 m."""
    Wd, Hd = 256, 640
    ppm = Hd / WALL_TILE_V
    base = marble((Hd, Wd), 11, (0.84, 0.78, 0.66), (0.70, 0.64, 0.52), 14, 0.25)
    z = (Hd - 1 - np.arange(Hd)) / ppm
    u = np.arange(Wd) / ppm
    course = np.floor(z / 0.5)
    off = (course % 2) * 0.5
    blocks = noise((Hd, Wd), 3, 12)
    shade = 0.94 + 0.08 * ((course[:, None] * 7.3 + np.floor((u[None, :] + off[:, None]) / 1.0) * 3.1) % 1.0)
    img = base * shade[..., None] * (0.97 + 0.05 * blocks)[..., None]
    hj = (np.abs(z / 0.5 - np.round(z / 0.5)) * 0.5 < 0.006)[:, None] & np.ones((1, Wd), bool)
    vj = np.abs(((u[None, :] + off[:, None]) / 1.0) - np.round((u[None, :] + off[:, None]) / 1.0)) < 0.006
    img[hj | vj] *= 0.80

    def rows(z0, z1):
        return (z >= z0) & (z < z1)
    sk = rows(0, 0.18)
    img[sk] = marble((int(sk.sum()), Wd), 15, (0.06, 0.06, 0.065), (0.40, 0.40, 0.40), 6, 0.4)
    img[rows(0.18, 0.20)] = GOLD_S
    img[rows(0.86, 0.95)] = np.array(TEAL_S) * (0.92 + 0.12 * noise((Hd, Wd), 2, 16)[rows(0.86, 0.95)])[..., None]
    for z0 in (0.85, 0.95):
        img[rows(z0, z0 + 0.012)] = GOLD_S
    return np.clip(img, 0, 1).astype(np.float32)


def vault_pixels():
    """The nave's barrel vault, a 1 x 1 m tile: a coffer of pale grey-teal plaster in a cream frame, a gold rosette in each."""
    S = 256
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32) / S
    d = np.minimum(np.minimum(xx, 1 - xx), np.minimum(yy, 1 - yy))
    img = np.ones((S, S, 3), np.float32) * np.array([0.44, 0.55, 0.58], np.float32)
    img *= (0.93 + 0.1 * noise((S, S), 10, 21))[..., None]
    frame = d < 0.10
    img[frame] = np.array(CREAM_S) * (0.95 + 0.08 * noise((S, S), 4, 22)[frame])[..., None]
    bevel = (d >= 0.10) & (d < 0.14)
    img[bevel] *= 0.78
    img[(d > 0.095) & (d < 0.105)] = GOLD_S
    c = (S / 2, S / 2)
    for k in range(8):
        a = 2 * math.pi * k / 8
        dot(img, (c[0] + math.sin(a) * S * 0.07, c[1] + math.cos(a) * S * 0.07), GOLD_S, S * 0.035)
    dot(img, c, (0.62, 0.44, 0.16), S * 0.04)
    return np.clip(wrap_blur(img, 1, 1), 0, 1).astype(np.float32)


DOME_W, DOME_D = 2 * APSE_HW, APSE_Y1 - APSE_IN


def dome_pixels():
    """The apse's shallow dome, one picture over it (planar from above): warm cream, a gold sunburst in the middle (the morning), a teal band
    with a gold laurel garland round it, teal butterflies between."""
    S = 1024
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    X = (xx / S - 0.5) * DOME_W
    Y = (0.5 - yy / S) * DOME_D
    rr = np.hypot(X / (DOME_W / 2), Y / (DOME_D / 2))
    img = np.ones((S, S, 3), np.float32) * np.array([0.86, 0.80, 0.68], np.float32)
    img *= (0.93 + 0.1 * noise((S, S), 20, 31, wrap=False))[..., None]
    sun = np.clip(1 - rr / 0.28, 0, 1)
    ang = np.arctan2(Y, X)
    rays = (np.cos(ang * 24) > 0.6) & (rr < 0.42) & (rr > 0.12)
    img = img * (1 - 0.6 * sun[..., None]) + np.array([0.95, 0.80, 0.48]) * 0.6 * sun[..., None]
    img[rays] = img[rays] * 0.7 + np.array(GOLD_S) * 0.3
    band = (rr > 0.62) & (rr < 0.74)
    img[band] = TEAL_S
    for r0 in (0.62, 0.74):
        img[np.abs(rr - r0) < 0.006] = GOLD_S
    # the laurel garland: leaf pairs along the band's middle
    for k in range(64):
        a = 2 * math.pi * k / 64
        cx, cy = math.cos(a) * 0.68 * DOME_W / 2, math.sin(a) * 0.68 * DOME_D / 2
        pr, pc = (0.5 - cy / DOME_D) * S, (cx / DOME_W + 0.5) * S
        t = a + math.pi / 2
        for side in (-1, 1):
            q = (pr - math.sin(t + side * 0.6) * 14, pc + math.cos(t + side * 0.6) * 14)
            line(img, (pr, pc), q, GOLD_S, 5)
    rng = np.random.default_rng(33)
    for k in range(10):
        a = 2 * math.pi * (k + rng.random() * 0.5) / 10
        r = 0.86 + rng.random() * 0.06
        pr, pc = (0.5 - math.sin(a) * r * 0.5) * S, (math.cos(a) * r * 0.5 + 0.5) * S
        for side in (-1, 1):
            dot(img, (pr - 6, pc + side * 9), TEAL_S, 9)
            dot(img, (pr + 7, pc + side * 6), (0.06, 0.32, 0.34), 6)
        line(img, (pr - 10, pc), (pr + 10, pc), BLACK_S, 3)
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def column_pixels():
    """The banded column shafts (the set's striped drums), a 1 m tall tile: black marble, cream marble and ochre-gold marble drums
    between gold rings."""
    Wd, Hd = 64, 256
    ppm = Hd / 1.0
    z = (Hd - 1 - np.arange(Hd)) / ppm
    blk = marble((Hd, Wd), 41, (0.05, 0.05, 0.055), (0.55, 0.55, 0.55), 8, 0.5)
    crm = marble((Hd, Wd), 43, (0.86, 0.81, 0.70), (0.66, 0.60, 0.48), 8, 0.4)
    och = marble((Hd, Wd), 45, (0.74, 0.56, 0.28), (0.90, 0.78, 0.50), 8, 0.4)
    img = np.zeros((Hd, Wd, 3), np.float32)
    for z0, z1, src in ((0.0, 0.30, blk), (0.34, 0.64, crm), (0.68, 0.96, och)):
        m = (z >= z0) & (z < z1)
        img[m] = src[m]
    for z0, z1 in ((0.30, 0.34), (0.64, 0.68), (0.96, 1.0)):
        m = (z >= z0) & (z < z1)
        rows_ = np.nonzero(m)[0]
        img[rows_] = np.array(GOLD_S) * (0.80 + 0.35 * np.sin(np.linspace(0, math.pi, len(rows_))))[:, None, None]
    return np.clip(img, 0, 1).astype(np.float32)


def valance_pixels():
    """The teal scalloped valances, 1 m along the length: teal velvet in soft folds, a gold braid along the scalloped hem, a gold band at the top."""
    Wd, Hd = 512, 128
    u = np.arange(Wd) / Wd
    v = (Hd - 1 - np.arange(Hd)) / (Hd - 1)
    fold = 0.86 + 0.16 * np.cos(2 * math.pi * u / 0.125)
    img = np.ones((Hd, Wd, 3), np.float32) * np.array(TEAL_S, np.float32)
    img *= fold[None, :, None] * (0.94 + 0.1 * noise((Hd, Wd), 3, 51))[..., None]
    img[v < 0.10] = GOLD_S
    img[(v >= 0.10) & (v < 0.13)] *= 0.55
    img[v > 0.90] = GOLD_S
    return np.clip(img, 0, 1).astype(np.float32)


def leaf_pixels(kind):
    """The two door leaves (0.94 x 2.16 m, 256 x 588): In, walnut with two gilt-edged panels; Exit, black lacquer with a gold border and a gold
    laurel wreath round two teal butterflies."""
    Wd, Hd = 256, 588
    nb = noise((Hd, Wd), 14, 61 + len(kind), wrap=False)
    sx, sy = Wd / DOOR_W, Hd / DOOR_H
    img = np.zeros((Hd, Wd, 3), np.float32)

    def rect(x0, z0, x1, z1, col, w=3):
        r0, r1 = Hd - z1 * sy, Hd - z0 * sy
        c0, c1 = x0 * sx, x1 * sx
        for p, q in (((r0, c0), (r0, c1)), ((r1, c0), (r1, c1)), ((r0, c0), (r1, c0)), ((r0, c1), (r1, c1))):
            line(img, p, q, col, w)
    if kind == "In":
        img[:] = (0.36, 0.22, 0.12)
        grain = noise((Hd, Wd), 2, 71, wrap=False)
        img *= (0.80 + 0.25 * nb + 0.12 * np.sin(np.arange(Wd)[None, :] / 3.0 + grain * 6))[..., None]
        for z0, z1 in ((0.18, 0.95), (1.15, 1.98)):
            rect(0.12, z0, 0.82, z1, GOLD_S, 4)
    else:
        img[:] = (0.04, 0.04, 0.045)
        img *= (0.9 + 0.2 * nb)[..., None]
        rect(0.06, 0.06, 0.88, 2.10, GOLD_S, 4)
        rect(0.12, 0.12, 0.82, 2.04, GOLD_S, 2)
        c = (Hd - 1.30 * sy, 0.47 * sx)
        for k in range(26):
            a = math.pi * (0.62 + 1.76 * k / 25)
            p = (c[0] - math.sin(a) * 0.24 * sy, c[1] + math.cos(a) * 0.24 * sx)
            t = a + math.pi / 2
            for side in (-1, 1):
                line(img, p, (p[0] - math.sin(t + side * 0.7) * 16, p[1] + math.cos(t + side * 0.7) * 16), GOLD_S, 5)
        for side in (-1, 1):
            dot(img, (c[0] - 8, c[1] + side * 13), TEAL_S, 12)
            dot(img, (c[0] + 10, c[1] + side * 9), (0.06, 0.32, 0.34), 8)
        line(img, (c[0] - 16, c[1]), (c[0] + 14, c[1]), GOLD_S, 3)
    return np.clip(img, 0, 1).astype(np.float32)


def placard_pixels():
    """The museum placard by the entrance (PLAN 2.2): cream letters on black, a gold rule."""
    W, H = 768, 512
    img = np.zeros((H, W, 3), np.float32)
    img[:] = (0.035, 0.03, 0.035)
    img[18:24, 30:W - 30] = img[H - 24:H - 18, 30:W - 30] = GOLD_S
    draw_text(img, "THANATOS", (40, 170, 0, W), (0.93, 0.88, 0.74), 0.85)
    draw_text(img, "STILLNESS - THE QUIET NAVE", (190, 270, 0, W), (0.86, 0.66, 0.30), 0.92)
    draw_text(img, "NINETY-NINE NOCTURNE SUITE", (290, 370, 0, W), (0.80, 0.76, 0.66), 0.92)
    draw_text(img, "XIII PIECES. BLACK. CREAM. GOLD. TEAL.", (380, 460, 0, W), (0.62, 0.58, 0.52), 0.92)
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def window_pixels():
    """A high window's glass (0.8 x 1.0 m): moonlit pale blue, lighter at the top, in a lattice of thin lead diamonds."""
    Wd, Hd = 128, 160
    yy, xx = np.mgrid[0:Hd, 0:Wd].astype(np.float32)
    t = yy / Hd
    img = np.array([0.66, 0.76, 0.92]) * (1 - t)[..., None] + np.array([0.40, 0.50, 0.72]) * t[..., None]
    img = img * (0.94 + 0.1 * noise((Hd, Wd), 6, 81, wrap=False))[..., None]
    a, b = (xx + yy) / 32.0, (xx - yy) / 32.0
    lead = (np.abs(a - np.round(a)) < 0.05) | (np.abs(b - np.round(b)) < 0.05)
    img[lead] = (0.10, 0.11, 0.14)
    return np.clip(img, 0, 1).astype(np.float32)


def butterfly_pixels():
    """A butterfly's two wings (left half: the left wing, its body edge at u = 0.5; the right wing mirrors it): teal with a black margin and
    veins, gold spots, alpha the wing's outline."""
    Wd, Hd = 256, 128
    yy, xx = np.mgrid[0:Hd, 0:Wd].astype(np.float32)
    x = np.abs(xx - Wd / 2) / (Wd / 2)               # 0 at the body, 1 at the wing tip
    y = (Hd / 2 - yy) / (Hd / 2)                     # +1 front edge, -1 rear
    fore = ((x - 0.50) / 0.50) ** 2 + ((y - 0.30) / 0.62) ** 2 < 1.0
    hind = ((x - 0.36) / 0.36) ** 2 + ((y + 0.45) / 0.52) ** 2 < 1.0
    wing = (fore | hind) & (x > 0.03)
    dist = np.where(fore, np.sqrt(((x - 0.50) / 0.50) ** 2 + ((y - 0.30) / 0.62) ** 2), np.sqrt(((x - 0.36) / 0.36) ** 2 + ((y + 0.45) / 0.52) ** 2))
    out = np.zeros((Hd, Wd, 4), np.float32)
    col = np.array([0.10, 0.66, 0.70]) * (1 - 0.5 * x)[..., None] + np.array([0.05, 0.30, 0.36]) * (0.5 * x)[..., None]
    col[dist > 0.80] = BLACK_S
    ang = np.arctan2(y, x)
    vein = (np.abs(np.sin(ang * 7)) < 0.10) & (dist < 0.85)
    col[vein] = col[vein] * 0.35
    out[..., :3] = col
    for (sx_, sy_) in ((0.80, 0.55), (0.88, 0.25), (0.70, 0.78), (0.55, -0.70)):
        for side in (-1, 1):
            cc = (Hd / 2 - sy_ * Hd / 2, Wd / 2 + side * sx_ * Wd / 2)
            dot(out[..., :3], cc, GOLD_S, 3.5)
    body = (x < 0.04) & (np.abs(y) < 0.55)
    out[..., 3] = np.where(wing | body, 1.0, 0.0)
    out[body, :3] = BLACK_S
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
    material("Floor_Checker", img=gen["floor"], rough=0.3)
    material("Wall_Cream", img=gen["wall"], rough=0.6)
    material("Vault_Coffer", img=gen["vault"], rough=0.9)
    material("Dome_Laurel", img=gen["dome"], rough=0.9)
    material("Column_Band", img=gen["column"], rough=0.25)
    material("Valance_Teal", img=gen["valance"], rough=0.95, double=True)
    material("Gold_Trim", color=(0.46, 0.33, 0.12), rough=0.35, metal=0.9)        # antique gilt: the page draws it unlit, so not too light
    material("Black_Stone", color=(0.035, 0.035, 0.04), rough=0.2)
    material("Laurel_Gilt", color=(0.42, 0.36, 0.13), rough=0.4, metal=0.8)
    material("Dawn_Plaster", color=(0.86, 0.78, 0.62), rough=0.8)               # the vestibule behind the exit door
    material("Placard", img=gen["placard"], rough=0.5)
    material("Leaf_In", img=gen["leaf_In"], rough=0.5)
    material("Leaf_Exit", img=gen["leaf_Exit"], rough=0.3)
    for name in LM_ROOM:                     # the growing hall's own copies (their own lightmap, baked with the apse slid away)
        m = MATS[name].copy()
        m.name = "Ext_" + name
        MATS[m.name] = m
    # not lightmapped
    material("Window_Moon", color=(0.0, 0.0, 0.0), rough=0.1, img=gen["window"], emit_img=True)     # the moonlit glass, at its own light
    material("Butterfly", color=(0.1, 0.6, 0.65), rough=0.6, img=gen["butterfly"], alpha=1.0, emit=((0.06, 0.30, 0.33), 0.6), double=True)
    material("Brass_Fixture", color=(0.62, 0.44, 0.18), rough=0.35, metal=0.9)     # the placard light's brass, PBR
    material("Lamp_Emit", color=(1.0, 0.85, 0.6), emit=((1.0, 0.62, 0.30), 8.0))
    material("Picture_Light_Emit", color=(1.0, 0.9, 0.7), emit=((1.0, 0.85, 0.6), 4.0))
    material("Dawn_Emit", color=(1.0, 0.9, 0.7), emit=((1.0, 0.80, 0.55), 3.0))   # the morning behind the exit door


# ---------------------------------------------------------------- geometry helpers (Blender coordinates)
ART = ART_APSE = LAYOUT = None
ART_EXT = []


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


def plain_uv(bm, fn):
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for lp in f.loops:
            lp[uvl].uv = fn(lp.vert.co, f.normal)


def wall_uv(bm):
    """The wall picture: u along the wall (WALL_TILE_U metres a repeat), v the height over WALL_TILE_V."""
    def fn(p, n):
        h = Vector((-n.y, n.x, 0)).normalized() if Vector((n.x, n.y, 0)).length > 1e-6 else Vector((1, 0, 0))
        return (p.dot(h) / WALL_TILE_U, p.z / WALL_TILE_V)
    plain_uv(bm, fn)


def add_lathe(bm, cx, cy, prof, seg=12, circ=1.0):
    """A surface of revolution about the vertical through (cx, cy): prof is [(z, r)] from the bottom up. UV: u round the girth (metres over
    `circ`), v = z, so a band picture tiles up the shaft."""
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    rings = [[bm.verts.new((cx + r * math.cos(2 * math.pi * i / seg), cy + r * math.sin(2 * math.pi * i / seg), z)) for i in range(seg)]
             for z, r in prof]
    for k in range(len(prof) - 1):
        for i in range(seg):
            j = (i + 1) % seg
            f = bm.faces.new([rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]])
            for lp, (ii, kk) in zip(f.loops, ((i, k), (i + 1, k), (i + 1, k + 1), (i, k + 1))):
                lp[uvl].uv = (ii / seg * 2 * math.pi * COL_R / circ, prof[kk][0])


def build_column(bms, cx, cy, H):
    """A banded column standing to H: a black plinth, a gilt base, the banded shaft, a gilt capital that flares to the arch."""
    add_box(bms["Black_Stone"], Vector((cx, cy, 0.11)), (0.50, 0.50, 0.22))
    add_lathe(bms["Gold_Trim"], cx, cy, [(0.22, 0.25), (0.26, 0.255), (0.30, 0.215)])
    add_lathe(bms["Column_Band"], cx, cy, [(0.30, COL_R), (H - 0.20, COL_R)])
    add_lathe(bms["Gold_Trim"], cx, cy, [(H - 0.20, 0.215), (H - 0.16, 0.24), (H - 0.11, 0.22), (H, 0.31)])


def build_rib(bm, yc, seg=16, w=0.30, depth=0.10):
    """A gilt transverse arch under the vault over a column pair."""
    pts = [(math.cos(math.pi * k / seg), math.sin(math.pi * k / seg)) for k in range(seg + 1)]
    for k in range(seg):
        (c0, s0), (c1, s1) = pts[k], pts[k + 1]
        ri, ro = VAULT_R - depth, VAULT_R - 0.002
        a = lambda c, s, r, y: (c * r, y, SPRING + s * r)
        quad(bm, [a(c0, s0, ri, yc - w / 2), a(c1, s1, ri, yc - w / 2), a(c1, s1, ri, yc + w / 2), a(c0, s0, ri, yc + w / 2)],
             Vector((-(c0 + c1), 0, -(s0 + s1))))
        for sy in (-1, 1):
            quad(bm, [a(c0, s0, ri, yc + sy * w / 2), a(c1, s1, ri, yc + sy * w / 2), a(c1, s1, ro, yc + sy * w / 2), a(c0, s0, ro, yc + sy * w / 2)],
                 Vector((0, sy, 0)))


def build_vault(bm, y0, y1, seg=16):
    """The barrel vault over the nave from y0 to y1 (faces down, toward the axis). UV: six coffers across, 1 m along."""
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    for k in range(seg):
        t0, t1 = math.pi * k / seg, math.pi * (k + 1) / seg
        P = lambda t, y: (VAULT_R * math.cos(t), y, SPRING + VAULT_R * math.sin(t))
        f = quad(bm, [P(t0, y0), P(t1, y0), P(t1, y1), P(t0, y1)], Vector((-math.cos(t0 + math.pi / seg), 0, -math.sin(t0 + math.pi / seg))))
        for lp in f.loops:
            co = lp.vert.co
            t = math.atan2(co.z - SPRING, co.x)
            lp[uvl].uv = (t / (math.pi / 6), co.y)


def build_valance(bmv, bmg, s, ya, yb, ystart):
    """A teal scalloped valance on the wall at side s (-1 west, +1 east) from ya to yb, its scallops in phase from ystart, with a gilt top rail
    and a gold teardrop at each cusp."""
    uvl = bmv.loops.layers.uv.get("UVMap") or bmv.loops.layers.uv.new("UVMap")
    n = max(2, int(round((yb - ya) / 0.04)))

    def zb(y):
        f = ((y - ystart) / SCALLOP) % 1.0
        return VAL_LOW + (VAL_CUSP - VAL_LOW) * (1 - math.sin(math.pi * f))
    rows = []
    for j in range(3):
        row = []
        for i in range(n + 1):
            y = ya + (yb - ya) * i / n
            z0 = zb(y)
            z = z0 + (VAL_TOP - z0) * j / 2
            d = 0.07 + 0.04 * (1 - j / 2)
            row.append((bmv.verts.new((s * (NAVE_HW - d), y, z)), y))
        rows.append(row)
    for j in range(2):
        for i in range(n):
            f = bmv.faces.new([rows[j][i][0], rows[j][i + 1][0], rows[j + 1][i + 1][0], rows[j + 1][i][0]])
            f.normal_update()
            if f.normal.x * s > 0:
                f.normal_flip()
            for lp in f.loops:
                vv = lp.vert
                jj = next(jx for jx in range(3) for ix in range(n + 1) if rows[jx][ix][0] is vv)
                lp[uvl].uv = ((vv.co.y - ystart) / 1.0, jj / 2)
    add_box(bmg, Vector((s * (NAVE_HW - 0.055), (ya + yb) / 2, VAL_TOP + 0.015)), (0.05, yb - ya, 0.04))
    k0 = math.ceil((ya - ystart) / SCALLOP - 1e-6)
    k = k0
    while ystart + k * SCALLOP < yb - 1e-6:
        y = ystart + k * SCALLOP
        if k > 0:
            bmesh.ops.create_uvsphere(bmg, u_segments=6, v_segments=4, radius=1.0,
                                      matrix=Matrix.Translation((s * (NAVE_HW - 0.11), y, VAL_CUSP - 0.06)) @ Matrix.Diagonal((0.022, 0.022, 0.04, 1)))
        k += 1


def window_outline():
    pts = [(-WIN_HW, WIN_Z0), (WIN_HW, WIN_Z0)]
    for k in range(13):
        a = math.pi * k / 12
        pts.append((WIN_HW * math.cos(a), WIN_ZS + WIN_HW * math.sin(a)))
    return pts


def build_window(bmw, bmg, bmb, s, yc):
    """A high window on the wall at side s, centred at yc: a round-headed moonlit glass (its own light), a gilt frame round it, a black sill."""
    face_x = s * (NAVE_HW - 0.012)
    sgn = 1 if s < 0 else -1                       # u along the wall as the viewer facing the wall reads it (left to right)
    W = lambda u, z, off=0.0: (s * (NAVE_HW - 0.012 - off), yc + sgn * u, z)
    pts = window_outline()
    uvl = bmw.loops.layers.uv.get("UVMap") or bmw.loops.layers.uv.new("UVMap")
    f = bmw.faces.new([bmw.verts.new(W(u, z)) for u, z in pts])
    f.normal_update()
    if f.normal.x * s > 0:
        f.normal_flip()
    for lp in f.loops:
        u = (lp.vert.co.y - yc) * sgn
        lp[uvl].uv = (u / (2 * WIN_HW) + 0.5, (lp.vert.co.z - WIN_Z0) / (WIN_ZS + WIN_HW - WIN_Z0))
    bmesh.ops.triangulate(bmw, faces=[f])
    # the gilt frame: a band 0.06 m wide round the outline, 0.02 m proud
    outer = []
    for u, z in pts:
        if z <= WIN_ZS + 1e-6 and abs(z - WIN_Z0) < 1e-6:
            outer.append((u + math.copysign(0.06, u), z - 0.06))
        else:
            if z > WIN_ZS + 1e-6:
                d = Vector((u, z - WIN_ZS)).normalized()
            else:
                d = Vector((math.copysign(1, u), 0))
            outer.append((u + d.x * 0.06, z + d.y * 0.06))
    m = len(pts)
    for i in range(m):
        j = (i + 1) % m
        quad(bmg, [W(*pts[i], 0.02), W(*pts[j], 0.02), W(*outer[j], 0.02), W(*outer[i], 0.02)], Vector((-s, 0, 0)))
    add_box(bmb, Vector((s * (NAVE_HW - 0.06), yc, WIN_Z0 - 0.06)), (0.12, 2 * WIN_HW + 0.24, 0.05))
    return face_x


def build_span(coll, tag, pre, y0, y1, fz, cols, val_bays, windows):
    """A stretch of the nave from y0 to y1: floor (at fz), both walls with their cornice, the vault, the columns and gilt ribs at `cols`, the
    valances (val_bays: (ya, yb, ystart) per side), the windows at `windows`. Each material its own object in `coll`; the lightmapped ones
    take the prefix `pre` (the growing hall has its own lightmap)."""
    bms = {}

    def B(m):
        if m not in bms:
            bms[m] = bmesh.new()
        return bms[m]
    quad(B("Floor_Checker"), [(-NAVE_HW, y0, fz), (NAVE_HW, y0, fz), (NAVE_HW, y1, fz), (-NAVE_HW, y1, fz)], Vector((0, 0, 1)))
    for s in (-1, 1):
        x = s * NAVE_HW
        quad(B("Wall_Cream"), [(x, y0, 0), (x, y1, 0), (x, y1, SPRING), (x, y0, SPRING)], Vector((-s, 0, 0)))
        add_box(B("Black_Stone"), Vector((s * (NAVE_HW - 0.04), (y0 + y1) / 2, SPRING + 0.03)), (0.08, y1 - y0, 0.07))
    build_vault(B("Vault_Coffer"), y0, y1)
    for cy in cols:
        for s in (-1, 1):
            build_column({"Black_Stone": B("Black_Stone"), "Gold_Trim": B("Gold_Trim"), "Column_Band": B("Column_Band")},
                         s * (NAVE_HW - COL_IN), cy, SPRING)
        build_rib(B("Gold_Trim"), cy)
    for ya, yb, ystart in val_bays:
        for s in (-1, 1):
            build_valance(B("Valance_Teal"), B("Gold_Trim"), s, ya, yb, ystart)
    for yc in windows:
        for s in (-1, 1):
            build_window(B("Window_Moon"), B("Gold_Trim"), B("Black_Stone"), s, yc)
    plain_uv(B("Floor_Checker"), lambda p, n: (p.x / FLOOR_TILE, p.y / FLOOR_TILE))
    wall_uv(B("Wall_Cream"))
    for m in ("Black_Stone", "Gold_Trim"):
        box_uv(B(m), 1.0)
    out = []
    for m, bm in bms.items():
        mat = (pre + m) if m in LM_ROOM else m
        out.append(mesh_obj(f"{tag}_{m}", bm, mat, coll, smooth=m in ("Column_Band", "Vault_Coffer", "Valance_Teal")))
    return out


def nave_bays(cols):
    return [(cols[i], cols[i + 1]) for i in range(len(cols) - 1)]


def build_nave():
    """The static nave (y -11 to 5) and the growing hall (y 5 to 17, six 2 m segments, each its own group the code shows as the apse slides)."""
    bays = nave_bays(NAVE_COLS)
    build_span(ART, "Nave", "", NAVE_Y0, NAVE_Y1, 0.0, NAVE_COLS, [(a + 0.3, b - 0.3, a + 0.3) for a, b in bays], [(a + b) / 2 for a, b in bays])
    ebays = nave_bays([NAVE_COLS[-1]] + EXT_COLS)
    for i in range(EXT_SEGS):
        s0, s1 = NAVE_Y1 + EXT_SEG * i, NAVE_Y1 + EXT_SEG * (i + 1)
        cols = [c for c in EXT_COLS if s0 <= c < s1 + (0.01 if i == EXT_SEGS - 1 else 0)]
        vals = []
        for a, b in ebays:
            ya, yb = max(a + 0.3, s0), min(b - 0.3, s1)
            if ya < yb - 1e-6:
                vals.append((ya, yb, a + 0.3))
        wins = [(a + b) / 2 for a, b in ebays if s0 <= (a + b) / 2 - 0.01 < s1]
        build_span(ART_EXT[i], f"Ext{i}", "Ext_", s0, s1, -0.003, cols, vals, wins)


def profile_strips(bm, y, facing, xs, zbot, ztop):
    """A vertical wall face at y, as strips between the x samples `xs`, from zbot(x) to ztop(x) (both taken at the strip's edges)."""
    for x0, x1 in zip(xs[:-1], xs[1:]):
        xm = (x0 + x1) / 2
        b0, b1 = zbot(x0, xm), zbot(x1, xm)
        t0, t1 = ztop(x0), ztop(x1)
        if max(t0 - b0, t1 - b1) < 1e-4:
            continue
        quad(bm, [(x0, y, b0), (x1, y, b1), (x1, y, t1), (x0, y, t0)], facing)


def arch_xs(hw, seg=16):
    return [hw * math.cos(math.pi * (seg - k) / seg) for k in range(seg + 1)]


def build_south_wall():
    """The nave's south end: the wall under the vault's lunette with the entrance door (closed behind the walker), its gilt architrave, the
    door leaf and the placard."""
    bm = bmesh.new()
    xs = sorted(set([round(x, 6) for x in arch_xs(NAVE_HW)] + [-DOOR_W / 2, DOOR_W / 2]))
    vault_top = lambda x: SPRING + math.sqrt(max(0.0, VAULT_R ** 2 - x * x))
    profile_strips(bm, NAVE_Y0, Vector((0, 1, 0)), xs, lambda x, xm: DOOR_H if abs(xm) < DOOR_W / 2 else 0.0, vault_top)
    for s in (-1, 1):                              # the door's reveal
        x = s * DOOR_W / 2
        quad(bm, [(x, NAVE_Y0, 0), (x, NAVE_Y0 - WALL_T, 0), (x, NAVE_Y0 - WALL_T, DOOR_H), (x, NAVE_Y0, DOOR_H)], Vector((-s, 0, 0)))
    quad(bm, [(-DOOR_W / 2, NAVE_Y0, DOOR_H), (DOOR_W / 2, NAVE_Y0, DOOR_H), (DOOR_W / 2, NAVE_Y0 - WALL_T, DOOR_H), (-DOOR_W / 2, NAVE_Y0 - WALL_T, DOOR_H)],
         Vector((0, 0, -1)))
    wall_uv(bm)
    mesh_obj("Nave_South_Wall", bm, "Wall_Cream", ART)
    bm = bmesh.new()
    door_architrave(bm, Vector((0, NAVE_Y0, 0)), Vector((0, -1, 0)))
    add_box(bm, Vector((0, NAVE_Y0 + 0.04, SPRING + 0.03)), (2 * NAVE_HW, 0.08, 0.07))
    box_uv(bm, 1.0)
    mesh_obj("Nave_South_Trim", bm, "Gold_Trim", ART)
    build_leaf("In", "Leaf_In", Vector((-DOOR_W / 2, NAVE_Y0 - 0.06, 0)), 0.0, ART)


def door_architrave(bm, dc, n):
    """A gilt architrave round a door in the wall whose outward normal is n (the room side is -n)."""
    t = Vector((-n.y, n.x, 0))
    yaw = math.atan2(t.y, t.x)
    hw = DOOR_W / 2
    for s in (-1, 1):
        add_box(bm, dc + t * (s * (hw + 0.045)) - n * 0.02 + Vector((0, 0, (DOOR_H + 0.09) / 2)), (0.09, 0.04, DOOR_H + 0.09), yaw)
    add_box(bm, dc - n * 0.025 + Vector((0, 0, DOOR_H + 0.09)), (DOOR_W + 0.30, 0.05, 0.06), yaw)
    add_box(bm, dc - n * 0.035 + Vector((0, 0, DOOR_H + 0.14)), (DOOR_W + 0.40, 0.07, 0.04), yaw)


def build_leaf(name, mat, hinge_pt, yaw, coll):
    """DoorLeaf_Thanatos_<name>: a 0.94 x 2.16 x 0.045 m leaf, origin on its hinge edge at the floor, closed in its opening (as baked).
    Local +X runs from the hinge across the leaf; the picture is on both faces, read the right way round from either side."""
    th = 0.045
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    corners = [(0, -th / 2), (DOOR_W, -th / 2), (DOOR_W, th / 2), (0, th / 2)]
    v = {}
    for i, (x, y) in enumerate(corners):
        v[(i, 0)] = bm.verts.new((x, y, 0.012))
        v[(i, 1)] = bm.verts.new((x, y, DOOR_H - 0.005))
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
    ob = mesh_obj(f"DoorLeaf_Thanatos_{name}", bm, mat, coll)
    ob.location = hinge_pt
    ob.rotation_euler = (0, 0, yaw)
    return ob


def build_placard():
    bm = bmesh.new()
    c = Vector((1.12, NAVE_Y0 + 0.012, 1.0))
    w, h = 0.42, 0.28
    f = bm.faces.new([bm.verts.new(c + Vector(d)) for d in ((-w / 2, 0, -h / 2), (w / 2, 0, -h / 2), (w / 2, 0, h / 2), (-w / 2, 0, h / 2))])
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp, uv in zip(f.loops, ((1, 0), (0, 0), (0, 1), (1, 1))):     # read from the north: +x is to the reader's left
        lp[uvl].uv = uv
    f.normal_update()
    if f.normal.y < 0:
        f.normal_flip()
    mesh_obj("Placard", bm, "Placard", ART)
    bm = bmesh.new()
    add_box(bm, c + Vector((0, -0.004, 0)), (w + 0.03, 0.008, h + 0.03))
    box_uv(bm, 1.0)
    mesh_obj("Placard_Frame", bm, "Gold_Trim", ART)
    bm = bmesh.new()
    top = c + Vector((0, 0, h / 2 + 0.06))
    add_cyl(bm, top + Vector((0, -0.004, 0)), top + Vector((0, 0.16, 0.05)), 0.008, seg=8)
    head = top + Vector((0, 0.16, 0.05))
    add_cyl(bm, head - Vector((0.17, 0, 0)), head + Vector((0.17, 0, 0)), 0.022, seg=10)
    box_uv(bm, 1.0)
    mesh_obj("Placard_Light", bm, "Brass_Fixture", ART, smooth=True)
    bm = bmesh.new()
    add_box(bm, head + Vector((0, -0.004, -0.023)), (0.30, 0.012, 0.004))
    box_uv(bm, 1.0)
    mesh_obj("Placard_Light_Glow", bm, "Picture_Light_Emit", ART)
    return c


def dome_z(x, y):
    yc = (APSE_IN + APSE_Y1) / 2
    return APSE_WALL_H + (DOME_TOP - APSE_WALL_H) * max(0.0, 1 - (x / APSE_HW) ** 2) * max(0.0, 1 - ((y - yc) / (DOME_D / 2)) ** 2)


def build_apse():
    """The apse (y 5 to 12), all in Art_Apse (exported under grp_apse, which the code slides north): its floor, the arch wall, the walls,
    the shallow dome, a gilt cornice, six banded columns, the exit door under a laurel wreath, and the lit vestibule behind it."""
    C = ART_APSE
    bm = bmesh.new()
    quad(bm, [(-APSE_HW, APSE_Y0, 0), (APSE_HW, APSE_Y0, 0), (APSE_HW, APSE_Y1, 0), (-APSE_HW, APSE_Y1, 0)], Vector((0, 0, 1)))
    quad(bm, [(-DOOR_W / 2, APSE_Y1, 0), (DOOR_W / 2, APSE_Y1, 0), (DOOR_W / 2, APSE_Y1 + WALL_T, 0), (-DOOR_W / 2, APSE_Y1 + WALL_T, 0)], Vector((0, 0, 1)))
    plain_uv(bm, lambda p, n: (p.x / FLOOR_TILE, p.y / FLOOR_TILE))
    mesh_obj("Apse_Floor", bm, "Floor_Checker", C)
    # walls
    bm = bmesh.new()
    arch = lambda x: ARCH_SPRING + math.sqrt(max(0.0, NAVE_HW ** 2 - x * x))
    vault_top = lambda x: SPRING + math.sqrt(max(0.0, VAULT_R ** 2 - x * x))
    axs = arch_xs(NAVE_HW)
    profile_strips(bm, APSE_Y0, Vector((0, -1, 0)), axs, lambda x, xm: arch(x), vault_top)          # the nave side, over the arch
    xs = [-APSE_HW] + axs + [APSE_HW]
    profile_strips(bm, APSE_IN, Vector((0, 1, 0)), xs, lambda x, xm: arch(x) if abs(xm) < NAVE_HW else 0.0, lambda x: APSE_WALL_H)
    outline = [(-NAVE_HW, 0.0)] + [(x, arch(x)) for x in axs] + [(NAVE_HW, 0.0)]
    for (xa, za), (xb, zb) in zip(outline[:-1], outline[1:]):          # the arch's soffit through the wall
        mid = Vector(((xa + xb) / 2, 0, (za + zb) / 2 - ARCH_SPRING if (za + zb) / 2 > ARCH_SPRING else 0))
        inward = Vector((-mid.x, 0, -mid.z)) if mid.length > 1e-6 else Vector((0, 0, -1))
        quad(bm, [(xa, APSE_Y0, za), (xb, APSE_Y0, zb), (xb, APSE_IN, zb), (xa, APSE_IN, za)], inward)
    for s in (-1, 1):
        x = s * APSE_HW
        quad(bm, [(x, APSE_IN, 0), (x, APSE_Y1, 0), (x, APSE_Y1, APSE_WALL_H), (x, APSE_IN, APSE_WALL_H)], Vector((-s, 0, 0)))
    nxs = [-APSE_HW, -DOOR_W / 2, DOOR_W / 2, APSE_HW]
    profile_strips(bm, APSE_Y1, Vector((0, -1, 0)), nxs, lambda x, xm: DOOR_H if abs(xm) < DOOR_W / 2 else 0.0, lambda x: APSE_WALL_H)
    for s in (-1, 1):                              # the exit door's reveal
        x = s * DOOR_W / 2
        quad(bm, [(x, APSE_Y1, 0), (x, APSE_Y1 + WALL_T, 0), (x, APSE_Y1 + WALL_T, DOOR_H), (x, APSE_Y1, DOOR_H)], Vector((-s, 0, 0)))
    quad(bm, [(-DOOR_W / 2, APSE_Y1, DOOR_H), (DOOR_W / 2, APSE_Y1, DOOR_H), (DOOR_W / 2, APSE_Y1 + WALL_T, DOOR_H), (-DOOR_W / 2, APSE_Y1 + WALL_T, DOOR_H)],
         Vector((0, 0, -1)))
    wall_uv(bm)
    mesh_obj("Apse_Walls", bm, "Wall_Cream", C)
    # the dome
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    nx, ny = 24, 20
    grid = [[bm.verts.new((-APSE_HW + 2 * APSE_HW * i / nx, APSE_IN + DOME_D * j / ny, 0)) for i in range(nx + 1)] for j in range(ny + 1)]
    for row in grid:
        for v in row:
            v.co.z = dome_z(v.co.x, v.co.y)
    for j in range(ny):
        for i in range(nx):
            f = bm.faces.new([grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]])
            f.normal_update()
            if f.normal.z > 0:
                f.normal_flip()
            for lp in f.loops:
                lp[uvl].uv = ((lp.vert.co.x + APSE_HW) / DOME_W, (lp.vert.co.y - APSE_IN) / DOME_D)
    mesh_obj("Apse_Dome", bm, "Dome_Laurel", C, smooth=True)
    # gilt cornice, the exit's architrave, the columns
    bms = {"Black_Stone": bmesh.new(), "Gold_Trim": bmesh.new(), "Column_Band": bmesh.new()}
    g = bms["Gold_Trim"]
    zc = APSE_WALL_H - 0.05
    for s in (-1, 1):
        add_box(g, Vector((s * (APSE_HW - 0.04), (APSE_IN + APSE_Y1) / 2, zc)), (0.08, APSE_Y1 - APSE_IN, 0.10))
    add_box(g, Vector((0, APSE_Y1 - 0.04, zc)), (2 * APSE_HW, 0.08, 0.10))
    add_box(g, Vector((0, APSE_IN + 0.04, zc)), (2 * APSE_HW, 0.08, 0.10))
    door_architrave(g, Vector((0, APSE_Y1, 0)), Vector((0, 1, 0)))
    for cx, cy in APSE_COLS:
        build_column(bms, cx, cy, APSE_WALL_H - 0.10)
    for m, bm in bms.items():
        if m != "Column_Band":
            box_uv(bm, 1.0)
        mesh_obj(f"Apse_{m}", bm, m, C, smooth=m == "Column_Band")
    build_wreath()
    build_vestibule()
    build_leaf("Exit", "Leaf_Exit", Vector((-DOOR_W / 2, APSE_Y1 + 0.06, 0)), 0.0, C)


WREATH_C = Vector((0.0, APSE_Y1 - 0.02, 2.95))


def build_wreath():
    """The laurel wreath over the exit door (PLAN 7): a black stone disc, a ring of gilt laurel leaves open at the foot, two teal butterflies."""
    C = ART_APSE
    c = WREATH_C
    bm = bmesh.new()
    seg = 32
    ring = [bm.verts.new(c + Vector((0.50 * math.cos(2 * math.pi * i / seg), 0, 0.50 * math.sin(2 * math.pi * i / seg)))) for i in range(seg)]
    f = bm.faces.new(ring)
    f.normal_update()
    if f.normal.y > 0:
        f.normal_flip()
    bmesh.ops.triangulate(bm, faces=[f])
    box_uv(bm, 1.0)
    mesh_obj("Wreath_Disc", bm, "Black_Stone", C)
    bm = bmesh.new()
    n = 40
    for k in range(n):
        a = -math.pi / 2 + 0.35 + (2 * math.pi - 0.7) * k / (n - 1)
        p = c + Vector((0.38 * math.cos(a), -0.02, 0.38 * math.sin(a)))
        t = Vector((-math.sin(a), 0, math.cos(a)))
        r = Vector((math.cos(a), 0, math.sin(a)))
        for side in (-1, 1):
            d = (t * 0.8 + r * side * 0.6).normalized()
            w = Vector((d.z, 0, -d.x)) * 0.022
            tip, base = p + d * 0.11, p
            mid = p + d * 0.055
            vs = [bm.verts.new(base), bm.verts.new(mid + w), bm.verts.new(tip), bm.verts.new(mid - w), bm.verts.new(mid + Vector((0, -0.012, 0)))]
            for a_, b_ in ((0, 1), (1, 2), (2, 3), (3, 0)):
                ff = bm.faces.new([vs[a_], vs[b_], vs[4]])
                ff.normal_update()
                if ff.normal.y > 0:
                    ff.normal_flip()
    box_uv(bm, 1.0)
    mesh_obj("Wreath_Laurel", bm, "Laurel_Gilt", C, smooth=True)
    bm = bmesh.new()
    for sx in (-1, 1):
        butterfly_geo(bm, Matrix.Translation(c + Vector((sx * 0.13, -0.03, 0.06))) @ Matrix.Rotation(math.pi / 2, 4, "X") @ Matrix.Rotation(sx * 0.35, 4, "Z"),
                      0.0, 0.9)
    mesh_obj("Wreath_Butterflies", bm, "Butterfly", C)


def build_vestibule():
    """Behind the exit door: a small vestibule (1.4 x 1.2 m) whose back wall glows with the morning (PLAN 4.6, the log's last line). Only the
    line of light under the closed door shows until the door opens."""
    C = ART_APSE
    y0, y1 = APSE_Y1 + WALL_T, APSE_Y1 + WALL_T + VEST_D
    bm = bmesh.new()
    quad(bm, [(-VEST_HW, y0, 0), (VEST_HW, y0, 0), (VEST_HW, y1, 0), (-VEST_HW, y1, 0)], Vector((0, 0, 1)))
    quad(bm, [(-VEST_HW, y0, VEST_H), (VEST_HW, y0, VEST_H), (VEST_HW, y1, VEST_H), (-VEST_HW, y1, VEST_H)], Vector((0, 0, -1)))
    for s in (-1, 1):
        x = s * VEST_HW
        quad(bm, [(x, y0, 0), (x, y1, 0), (x, y1, VEST_H), (x, y0, VEST_H)], Vector((-s, 0, 0)))
    profile_strips(bm, y0, Vector((0, 1, 0)), [-VEST_HW, -DOOR_W / 2, DOOR_W / 2, VEST_HW], lambda x, xm: DOOR_H if abs(xm) < DOOR_W / 2 else 0.0,
                   lambda x: VEST_H)
    box_uv(bm, 1.0)
    mesh_obj("Vestibule", bm, "Dawn_Plaster", C)
    bm = bmesh.new()
    quad(bm, [(-VEST_HW + 0.1, y1 - 0.01, 0.2), (VEST_HW - 0.1, y1 - 0.01, 0.2), (VEST_HW - 0.1, y1 - 0.01, VEST_H - 0.2), (-VEST_HW + 0.1, y1 - 0.01, VEST_H - 0.2)],
         Vector((0, -1, 0)))
    quad(bm, [(-DOOR_W / 2 + 0.02, APSE_Y1 + 0.09, 0.0005), (DOOR_W / 2 - 0.02, APSE_Y1 + 0.09, 0.0005), (DOOR_W / 2 - 0.02, APSE_Y1 + 0.09, 0.011),
              (-DOOR_W / 2 + 0.02, APSE_Y1 + 0.09, 0.011)], Vector((0, -1, 0)))
    box_uv(bm, 1.0)
    ob = mesh_obj("Dawn_Glow", bm, "Dawn_Emit", C)
    ob.visible_shadow = False


def butterfly_geo(bm, M, open_deg=30.0, scale=1.0):
    """A butterfly: two wing quads hinged on the body line (local Y), each tilted up by open_deg; 0.13 m across at scale 1."""
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    a = math.radians(open_deg)
    span, f0, f1 = 0.065 * scale, 0.045 * scale, -0.040 * scale
    for side in (-1, 1):
        tip = Vector((side * span * math.cos(a), 0, span * math.sin(a)))
        pts = [Vector((0, f1, 0)), Vector((0, f0, 0)), tip + Vector((0, f0, 0)), tip + Vector((0, f1, 0))]
        uvs = [(0.5, 0.0), (0.5, 1.0), (0.5 + side * 0.5, 1.0), (0.5 + side * 0.5, 0.0)]
        f = bm.faces.new([bm.verts.new(M @ p) for p in pts])
        for lp, uv in zip(f.loops, uvs):
            lp[uvl].uv = uv


BUTTERFLIES = 12


def build_butterflies():
    """decor_butterfly_00 .. 11: slow teal butterflies about the nave (PLAN 4.6), each its own node so the code can fly them and, when the
    walker is slow, land them on the walker. Not in the bake."""
    rng = np.random.default_rng(77)
    out = []
    for i in range(BUTTERFLIES):
        x = float(rng.uniform(-1.5, 1.5))
        y = float(NAVE_Y0 + 1.5 + (NAVE_Y1 - NAVE_Y0 - 2.0) * (i + rng.uniform(0.1, 0.9)) / BUTTERFLIES)
        z = float(rng.uniform(1.2, 2.7))
        bm = bmesh.new()
        butterfly_geo(bm, Matrix.Identity(4), float(rng.uniform(15, 55)), 1.0)
        ob = mesh_obj(f"decor_butterfly_{i:02d}", bm, "Butterfly", ART)
        ob.location = (x, y, z)
        ob.rotation_euler = (float(rng.uniform(-0.2, 0.2)), 0, float(rng.uniform(0, 2 * math.pi)))
        ob.visible_shadow = False
        out.append(ob)
    return out


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


def is_apse_piece(objname):
    return not objname.startswith("P13_")


def place_all():
    placed = {}
    for code, objname, xy, facing, how in PLACE:
        ob = load_copy(code, objname)
        ob.rotation_mode = "XYZ"                     # the glTF importer leaves quaternions
        ob.rotation_euler = (0, 0, yaw_for(code, facing))
        ob.location = (xy[0], xy[1], 0.0)
        bpy.context.view_layer.update()
        if how[0] in ("wall", "hang"):
            n, plane = WALLPLANE[how[1]]
            gap = how[2]
            reach = max(v.dot(n) for v in world_verts(ob))
            ob.location = Vector(ob.location) + n * (plane - gap - reach)
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
        if is_apse_piece(objname):
            for c in list(ob.users_collection):
                c.objects.unlink(ob)
            ART_APSE.objects.link(ob)
        lo, hi = bbox(ob)
        print(f"PLACE {objname}: ({lo.x:.2f}, {lo.y:.2f}, {lo.z:.2f}) .. ({hi.x:.2f}, {hi.y:.2f}, {hi.z:.2f})")
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


def yaw_facing(d):
    """An Arrive_'s -Y axis is the way you face (as in the Nyx room): the yaw that turns -Y to the direction d."""
    return math.atan2(d.x, -d.y)


def build_layout(placed):
    """COL_ boxes (static: the floor, the nave's walls and columns, the torcheres; COL_apse_*: the apse's, which move with grp_apse; COL_ext_*:
    the growing hall's, live only while their segment shows), the markers, the link, the zones (PLAN 4.6)."""
    col_box("COL_floor", (-APSE_HW - 1.5, NAVE_Y0 - 1.5, -0.2), (APSE_HW + 1.5, APSE_Y1 + SLIDE_MAX + 2.0, 0.0))
    for s, tag in ((-1, "W"), (1, "E")):
        x0, x1 = sorted((s * NAVE_HW, s * (NAVE_HW + WALL_T)))
        col_box(f"COL_wall_{tag}", (x0, NAVE_Y0 - WALL_T, 0), (x1, NAVE_Y1, SPRING + 2.0))
        for k, cy in enumerate(NAVE_COLS):
            a, b = sorted((s * (NAVE_HW - COL_IN - COL_R), s * NAVE_HW))
            col_box(f"COL_col_{tag}{k}", (a, cy - 0.26, 0), (b, cy + 0.26, SPRING))
        for i in range(EXT_SEGS):
            s0, s1 = NAVE_Y1 + EXT_SEG * i, NAVE_Y1 + EXT_SEG * (i + 1)
            col_box(f"COL_ext_{i}_{tag}", (x0, s0, 0), (x1, s1, SPRING + 2.0))
            for cy in EXT_COLS:
                if s0 <= cy < s1 + (0.01 if i == EXT_SEGS - 1 else 0):
                    a, b = sorted((s * (NAVE_HW - COL_IN - COL_R), s * NAVE_HW))
                    col_box(f"COL_ext_{i}_col_{tag}", (a, cy - 0.26, 0), (b, cy + 0.26, SPRING))
    col_box("COL_wall_S", (-NAVE_HW - WALL_T, NAVE_Y0 - WALL_T, 0), (NAVE_HW + WALL_T, NAVE_Y0, SPRING + 2.0))
    # the apse (moves with grp_apse)
    for s, tag in ((-1, "W"), (1, "E")):
        a, b = sorted((s * NAVE_HW, s * (APSE_HW + WALL_T)))
        col_box(f"COL_apse_front_{tag}", (a, APSE_Y0, 0), (b, APSE_IN, APSE_WALL_H))
        a, b = sorted((s * APSE_HW, s * (APSE_HW + WALL_T)))
        col_box(f"COL_apse_wall_{tag}", (a, APSE_Y0, 0), (b, APSE_Y1 + WALL_T, APSE_WALL_H))
    col_box("COL_apse_wall_N", (-APSE_HW - WALL_T, APSE_Y1, 0), (APSE_HW + WALL_T, APSE_Y1 + WALL_T, APSE_WALL_H))
    for cx, cy in APSE_COLS[4:]:
        col_box(f"COL_apse_col_{'W' if cx < 0 else 'E'}", (cx - 0.26, cy - 0.26, 0), (cx + 0.26, APSE_Y1, APSE_WALL_H))
    for nm, ob in placed.items():
        if nm.startswith(("TH-00", "TH-08", "TH-09", "TH-10", "TH-12", "TH-11", "TH-06")):
            continue                                   # on the furniture, on the wall, or flat on the floor
        lo, hi = bbox(ob)
        col_box(f"COL_apse_{nm}" if is_apse_piece(nm) else f"COL_{nm}", lo, hi)
    north = Vector((0, 1, 0))
    empty("Marker_Spawn", (SPAWN.x, SPAWN.y, 0), "Spawn", yaw=yaw_facing(north))
    empty("Marker_Entrance", (0, NAVE_Y0 + 0.4, 0), "Entrance", yaw=yaw_facing(north))
    empty("Arrive_Thanatos_In", (SPAWN.x, SPAWN.y, 0), yaw=yaw_facing(north), note="where the walker stands coming in through Oneiros's horn gate")
    empty("Marker_Exit", (0, APSE_Y1 - 0.5, 0), "Exit", yaw=yaw_facing(north), note="moves with grp_apse")
    empty("Link_Thanatos_Exit", (0, APSE_Y1 - 0.3, 0), to_scene="grocery", to_arrive="",
          note="the exit door under the laurel; grocery is a code room: arrive at its meta.start. Moves with grp_apse")
    col_box("Zone_trigger_exit", (-0.6, APSE_Y1 - 0.75, 0), (0.6, APSE_Y1, 2.2))
    col_box("Zone_trigger_still", (-NAVE_HW, NAVE_Y0, 0), (NAVE_HW, NAVE_Y1 + SLIDE_MAX, SPRING))
    empty("Spot_apse_home", (0, APSE_Y0, 0), note="grp_apse's place at rest: its offset is 0 here, at most +12 m north (Blender +Y)")
    for nm, hinge, swing, state in (("In", "west jamb", 90, "closed (as baked): the walker arrives already inside"),
                                    ("Exit", "west jamb", 90, "closed (as baked); swings north, away from the room, onto the lit vestibule")):
        leaf = bpy.data.objects[f"DoorLeaf_Thanatos_{nm}"]
        leaf["hinge"] = hinge
        leaf["swing_deg"] = swing
        leaf["state"] = state


# ---------------------------------------------------------------- lights (for the bake and the stills; never exported)
MOON_W = 18.0            # each high window's moonlight (an area light in the window, pointing in and down)
NAVE_FILL_W = 420.0      # the even part: a long soft panel under the vault's crown, pointing down
APSE_GLOW_W = 340.0      # the warm light under the apse's dome
LAMP_W = 10.0            # the bedside lamp (TH-00), under its shade
DAWN_W = 30.0            # the morning in the vestibule behind the exit door
PLACARD_W = 0.09         # the placard's picture light
EXT_FILL_W = 310.0       # the growing hall's own fill (its moon windows are MOON_W)
LIGHT_W = {"Moon_": MOON_W, "ExtMoon_": MOON_W, "Nave_Fill": NAVE_FILL_W, "Ext_Fill": EXT_FILL_W, "Apse_Glow": APSE_GLOW_W, "Lamp_Bulb": LAMP_W,
           "Dawn": DAWN_W, "Placard_Light": PLACARD_W}
LAMP_BULB_Z = 0.80          # the lamp's bulb under its parasol shade, as a fraction of the lamp's height


def add_lights(placard_c, rig):
    sc = bpy.context.scene
    lights = bpy.data.collections.new("Lights")
    sc.collection.children.link(lights)
    lext = bpy.data.collections.new("Lights_Ext")
    sc.collection.children.link(lext)

    def light(name, kind, loc, energy, color, size=0.05, coll=lights, parent=None):
        d = bpy.data.lights.new(name, kind)
        d.energy, d.color = energy, color
        d.shadow_soft_size = size
        ob = bpy.data.objects.new(name, d)
        ob.location = loc
        coll.objects.link(ob)
        if parent is not None:
            ob.parent = parent
        return ob, d

    def moon(name, s, yc, coll):
        c = Vector((s * (NAVE_HW - 0.10), yc, (WIN_Z0 + WIN_ZS + WIN_HW) / 2))
        ob, d = light(name, "AREA", c, MOON_W, (0.70, 0.80, 1.0), 0.0, coll)
        d.shape, d.size, d.size_y = "RECTANGLE", 2 * WIN_HW, 0.9
        aim = Vector((-s, 0, -0.45)).normalized()
        ob.rotation_euler = aim.to_track_quat("-Z", "Y").to_euler()
    for a, b in nave_bays(NAVE_COLS):
        for s in (-1, 1):
            moon(f"Moon_{'W' if s < 0 else 'E'}{a:+.0f}", s, (a + b) / 2, lights)
    for a, b in nave_bays([NAVE_COLS[-1]] + EXT_COLS):
        for s in (-1, 1):
            moon(f"ExtMoon_{'W' if s < 0 else 'E'}{a:+.0f}", s, (a + b) / 2, lext)
    ob, d = light("Nave_Fill", "AREA", (0, (NAVE_Y0 + NAVE_Y1) / 2, SPRING + VAULT_R - 0.25), NAVE_FILL_W, (0.80, 0.86, 1.0), 0.0)
    d.shape, d.size, d.size_y = "RECTANGLE", 1.2, NAVE_Y1 - NAVE_Y0 - 0.4
    ob, d = light("Ext_Fill", "AREA", (0, NAVE_Y1 + SLIDE_MAX / 2, SPRING + VAULT_R - 0.25), EXT_FILL_W, (0.80, 0.86, 1.0), 0.0, lext)
    d.shape, d.size, d.size_y = "RECTANGLE", 1.2, SLIDE_MAX - 0.4
    ob, d = light("Apse_Glow", "AREA", (0, (APSE_IN + APSE_Y1) / 2, DOME_TOP - 0.45), APSE_GLOW_W, (1.0, 0.80, 0.58), 0.0, parent=rig)
    d.shape, d.size = "DISK", 3.0
    lamp = bpy.data.objects.get("TH-00_lamp")
    if lamp:
        lo, hi = bbox(lamp)
        H = hi.z - lo.z
        c = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z + LAMP_BULB_Z * H))
        light("Lamp_Bulb", "POINT", c, LAMP_W, (1.0, 0.62, 0.34), 0.03, parent=rig)
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.03, matrix=Matrix.Translation(c))
        box_uv(bm, 1.0)
        g = mesh_obj("Lamp_Glow", bm, "Lamp_Emit", ART_APSE, smooth=True)
        g.parent = rig
    ob, d = light("Dawn", "AREA", (0, APSE_Y1 + WALL_T + VEST_D - 0.15, 1.3), DAWN_W, (1.0, 0.82, 0.58), 0.0, parent=rig)
    d.shape, d.size, d.size_y = "RECTANGLE", 1.2, 2.2
    ob.rotation_euler = Vector((0, -1, 0)).to_track_quat("-Z", "Y").to_euler()
    pc = placard_c + Vector((0, 0.16, 0.14 + 0.06 + 0.05 - 0.03))
    ob, d = light("Placard_Light", "AREA", pc, PLACARD_W, (1.0, 0.85, 0.65), 0.0)
    d.shape, d.size, d.size_y = "RECTANGLE", 0.28, 0.02
    ob.rotation_euler = (placard_c - pc).to_track_quat("-Z", "Y").to_euler()
    lext.hide_render = True


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("Night")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
    bg.inputs["Strength"].default_value = 0.0


NOSHADOW = ("Lamp_Emit", "Brass_Fixture", "Picture_Light_Emit", "Window_Moon", "Butterfly", "Dawn_Emit")


def build_all():
    global ART, ART_APSE, LAYOUT, ART_EXT
    clear_scene()
    MATS.clear()
    sc = bpy.context.scene
    ART = bpy.data.collections.new("Art")
    LAYOUT = bpy.data.collections.new("Layout")
    sc.collection.children.link(ART)
    sc.collection.children.link(LAYOUT)
    ART_APSE = bpy.data.collections.new("Art_Apse")
    ART.children.link(ART_APSE)
    ext_root = bpy.data.collections.new("Art_Ext")
    ART.children.link(ext_root)
    ART_EXT = []
    for i in range(EXT_SEGS):
        c = bpy.data.collections.new(f"Art_Ext_{i}")
        ext_root.children.link(c)
        ART_EXT.append(c)
    gen = {"floor": mk_image("Thanatos_Floor", floor_pixels()), "wall": mk_image("Thanatos_Wall", wall_pixels()),
           "vault": mk_image("Thanatos_Vault", vault_pixels()), "dome": mk_image("Thanatos_Dome", dome_pixels()),
           "column": mk_image("Thanatos_Column", column_pixels()), "valance": mk_image("Thanatos_Valance", valance_pixels()),
           "placard": mk_image("Thanatos_Placard", placard_pixels()), "window": mk_image("Thanatos_Window", window_pixels()),
           "butterfly": mk_image("Thanatos_Butterfly", butterfly_pixels())}
    for k in ("In", "Exit"):
        gen[f"leaf_{k}"] = mk_image(f"Thanatos_Leaf_{k}", leaf_pixels(k))
    make_materials(gen)
    build_nave()
    build_south_wall()
    pc = build_placard()
    build_apse()
    build_butterflies()
    placed = place_all()
    rig = bpy.data.objects.new("Apse_Rig", None)
    rig.empty_display_type = "ARROWS"
    ART_APSE.objects.link(rig)
    for ob in list(ART_APSE.objects):
        if ob is not rig:
            ob.parent = rig                            # at rest the rig is at the origin, so nothing moves
    build_layout(placed)
    add_lights(pc, rig)
    setup_world()
    sc.unit_settings.system = "METRIC"
    for o in ART.all_objects:
        if o.type == "MESH" and o.data.materials and o.data.materials[0].name in NOSHADOW:
            o.visible_shadow = False
    ext_root.hide_render = True                        # the growing hall shows only while the apse is away (the bake and the stills set it)


def set_slide(d, art=True, export=True):
    """The set piece's state: the apse `d` metres north of its place (0 to 12), the growing hall's segments shown where the apse has left."""
    if art and "Apse_Rig" in bpy.data.objects:
        bpy.data.objects["Apse_Rig"].location.y = d
    if export and "grp_apse_x" in bpy.data.objects:
        bpy.data.objects["grp_apse_x"].location.y = d
    for i in range(EXT_SEGS):
        show = d > EXT_SEG * i + 1e-6
        if art and f"Art_Ext_{i}" in bpy.data.collections:
            bpy.data.collections[f"Art_Ext_{i}"].hide_render = not show
        if art and "Art_Ext" in bpy.data.collections:
            bpy.data.collections["Art_Ext"].hide_render = d <= 1e-6
        if export:
            for o in bpy.data.objects:
                if o.name.startswith(f"ext{i}_") and o.type == "MESH":
                    o.hide_render = not show
    if "Lights_Ext" in bpy.data.collections:
        bpy.data.collections["Lights_Ext"].hide_render = d <= 1e-6
    bpy.context.view_layer.update()


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
    LM_ROOM + ("Dome_Laurel", "Laurel_Gilt", "Dawn_Plaster", "Placard", "Leaf_In", "Leaf_Exit"),   # 0 the nave and the apse
    tuple("Ext_" + m for m in LM_ROOM),                                                              # 1 the growing hall (baked slid)
    furn("TH-01", "TH-02", "TH-03", "TH-04", "TH-05", "TH-06", "TH-07", "TH-11"),                   # 2 the big furniture
    furn("TH-00", "TH-08", "TH-09", "TH-10", "TH-12", "P5", "P13"),                                 # 3 the smalls and the props
]
MIN_DENSITY = [40, 32, 60, 60]          # px per metre wanted on each map (the search takes the smallest page that gives it)
PAGES = [None, None, None, None]        # auto; --pages a,b,c,d fixes them
if arg("--pages"):
    PAGES = [None if v == "auto" else int(v) for v in arg("--pages").split(",")]
NOLM = ("Lamp_Emit", "Brass_Fixture", "Picture_Light_Emit", "Window_Moon", "Butterfly", "Dawn_Emit")
KEEP_NODES = ("DoorLeaf_", "decor_")    # exported as their own nodes (the scene code moves or flies them), not merged by material
MAIN = ("Floor_Checker", "Wall_Cream", "Vault_Coffer", "Dome_Laurel", SET + "_")   # the surfaces held to the exposure rule
NOT_MAIN = (f"{SET}_TH-00_lamp",)       # the lamp's own body, inches from its bulb: reported, not held
TARGET_P90 = arg("--target", 0.90, float)
CLIP_CAP = arg("--clip-cap", 0.98, float)     # and no main surface's p99 above this (0 turns the cap off)
BAKE_PASSES = [("slid", SLIDE_MAX, [1]), ("rest", 0.0, [0, 2, 3])]    # the growing hall is baked as it is seen: with the apse 12 m away


def group_of(mname):
    for n, g in enumerate(GROUPS):
        if any(mname == x or (x.endswith("_") and mname.startswith(x)) for x in g):
            return n
    return None


def art_group(ob):
    names = {c.name for c in ob.users_collection}
    if "Art_Apse" in names:
        return "apse"
    for i in range(EXT_SEGS):
        if f"Art_Ext_{i}" in names:
            return f"ext{i}"
    return "static"


MERGED_SRC = {}     # merged export object -> the centres of the Art pieces in it (a pair of bedside tables, the six torcheres)


def make_export_objects():
    """The Export collection: the Art merged by (group, material), with the lightmap UVs to come. The apse's under an empty grp_apse (the code
    slides it); each growing-hall segment's under grp_nave_ext_<i> (the code shows it once the apse has left it), all under grp_nave_ext."""
    set_slide(0.0, export=False)
    art = bpy.data.collections["Art"]
    if "Export" in bpy.data.collections:
        for o in list(bpy.data.collections["Export"].objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(bpy.data.collections["Export"])
    exp = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(exp)
    roots = {}

    def root(g):
        if g == "static":
            return None
        if g not in roots:
            if g == "apse":
                e = bpy.data.objects.new("grp_apse_x", None)
            else:
                if "ext" not in roots:
                    roots["ext"] = bpy.data.objects.new("grp_nave_ext_x", None)
                    exp.objects.link(roots["ext"])
                e = bpy.data.objects.new(f"grp_nave_ext_{g[3:]}_x", None)
                e.parent = roots["ext"]
            exp.objects.link(e)
            roots[g] = e
        return roots[g]
    by_key, out = {}, {}
    MERGED_SRC.clear()
    for ob in list(art.all_objects):
        if ob is None or ob.type != "MESH":
            continue
        assert len(ob.data.materials) == 1, ob.name
        mname = ob.data.materials[0].name
        g = art_group(ob)
        if ob.name.startswith(KEEP_NODES):
            me = ob.data.copy()
            me.name = ob.name
            o2 = bpy.data.objects.new(ob.name + "_x", me)
            o2.matrix_world = ob.matrix_world.copy()
            exp.objects.link(o2)
            if root(g) is not None:
                o2.parent = root(g)
            out[o2.name] = o2
            continue
        key = (g, mname)
        bm = by_key.setdefault(key, bmesh.new())
        tmp = ob.data.copy()
        tmp.transform(ob.matrix_world)
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
        lo, hi = bbox(ob)
        MERGED_SRC.setdefault(key, []).append((lo + hi) / 2)
    for (g, mname), bm in by_key.items():
        tiny = [f for f in bm.faces if f.calc_area() < 1e-9]       # zero-area slivers left by the decimation
        if tiny:
            bmesh.ops.delete(bm, geom=tiny, context="FACES")
            print(f"  {g} {mname}: dropped {len(tiny)} zero-area faces")
        name = mname if g == "static" else f"{g}_{mname}"
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.materials.clear()
        me.materials.append(bpy.data.materials[mname])
        ob = bpy.data.objects.new(name + "_x", me)
        exp.objects.link(ob)
        if root(g) is not None:
            ob.parent = root(g)
        out[ob.name] = ob
        MERGED_SRC[ob.name] = MERGED_SRC.pop((g, mname))
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
    copies stage's islands, which do not overlap) as one square, and the squares are shelf-packed here, sized by each piece's area; a merged
    object holding several placed copies (the bedside pair, the six torcheres) gives each copy its own square."""
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
            keys = np.zeros(len(me.polygons), np.int64)
            srcs = MERGED_SRC.get(o.name, [])
            if len(srcs) > 1:
                sc_ = np.array([tuple(s) for s in srcs], np.float32)
                keys = np.argmin(((cen[:, None, :] - sc_[None, :, :]) ** 2).sum(axis=2), axis=1)
                print(f"  {o.name}: {len(srcs)} placed copies, faces per copy {np.bincount(keys).tolist()}")
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
    # the room's own pieces: smart project packs them itself, at one scale. (Blender's pack_islands on these merged groups packed every island
    # to a point on the box's Blender 5.2, so it is not used here; the margin is given to smart project for each page size tried.)
    chosen = None
    for S in sizes:
        select_only(objs)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=(MARGIN_PX + 2) / S, scale_to_bounds=False)
        bpy.ops.object.mode_set(mode="OBJECT")
        a3 = sum(area3d(o) for o in objs)
        au = sum(uv_area(o, "lightmap") for o in objs)
        dens = S * math.sqrt(au / a3)
        print(f"  page {S}: {a3:.1f} m2, {dens:.1f} px/m, UV cover {au:.3f}")
        chosen = (S, dens)
        assert dens > 1.0, "the lightmap atlas packed to nothing"
        if dens >= min_d:
            break
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


def light_objects():
    return [ob for c in ("Lights", "Lights_Ext") if c in bpy.data.collections for ob in bpy.data.collections[c].objects]


def reset_lights():
    """The lights at the constants' energies (the saved .blend holds them times the last bake's exposure), so a bake is the same from any start."""
    for ob in light_objects():
        for prefix, w in LIGHT_W.items():
            if ob.name.startswith(prefix):
                ob.data.energy = w


def stage_bake():
    reset_lights()
    exp = make_export_objects()
    bpy.data.collections["Art"].hide_render = True
    setup_cycles(SAMPLES, bake=True)
    report, stats, raw = {}, {}, {}
    for pname, slide, groups in BAKE_PASSES:
        set_slide(slide)
        print(f"bake pass {pname}: the apse {slide} m north")
        for n in groups:
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
                         "samples": SAMPLES, "device": bpy.context.scene.cycles.device, "seconds": round(time.time() - t0), "pass": pname,
                         "materials": sorted({o.data.materials[0].name for o in objs})}
            print("  baked", report[n])
            bpy.data.images.remove(img)
    set_slide(0.0)
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
    for ob in light_objects():      # the lights as the page shows them, so the stills hold the lightmaps' light
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
    set_slide(0.0)
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
    bpy.context.view_layer.objects.active = next(o for o in objs if o.type == "MESH")
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
    set_slide(0.0)


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


PLAN_HIDE = ("Vault_Coffer", "Dome_Laurel", "Valance_Teal", "Gold_Trim", "Black_Stone", "Butterfly")


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
        "1_arrival": (look_cam("arrival", (SPAWN.x, SPAWN.y, E), (0.0, 6.0, E + 0.45), 70.0), (1920, 1080), STILLS, 0.0),
        "2_apse": (look_cam("apse", (1.7, 6.0, 1.5), (-3.0, 9.0, 0.6), 72.0), (1920, 1080), STILLS, 0.0),
        "3_nave": (look_cam("nave", (1.35, -9.6, 1.25), (-1.7, -4.0, 2.2), 72.0), (1920, 1080), STILLS, 0.0),
        "4_slide": (look_cam("slide", (0.0, -6.0, E), (0.0, 18.0, E + 0.35), 70.0), (1920, 1080), STILLS, SLIDE_MAX),
        "rest6": (look_cam("rest6", (0.0, -6.0, E), (0.0, 18.0, E + 0.35), 70.0), (1280, 720), work(), 0.0),
        "half6": (look_cam("half6", (0.0, -6.0, E), (0.0, 18.0, E + 0.35), 70.0), (1280, 720), work(), 5.0),
        "exit": (look_cam("exit", (0.9, 8.4, 1.45), (-0.5, 12.0, 2.0), 70.0), (1280, 720), work(), 0.0),
        "plan": (look_cam("plan", (0, 0.6, 30), None, ortho=9.6), (720, 2000), work(), 0.0),
    }
    hide_plan = [o for o in list(bpy.data.collections["Art"].all_objects) if o is not None and o.type == "MESH" and o.data.materials and o.data.materials[0].name in PLAN_HIDE]
    which = arg("--only", "all")
    for key, (cam, (w, h), folder, slide) in shots.items():
        if which != "all" and key not in which.split(","):
            continue
        sc.camera = cam
        set_slide(slide, export=False)
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
    set_slide(0.0, export=False)
    for o in hide_plan:
        o.visible_camera = True


def stage_views():
    """Textured view sheets of the copies as written (to read which way each faces)."""
    for code, fname, name, budget, px in PIECES:
        clear_scene()
        bpy.ops.import_scene.gltf(filepath=str(copy_path(code, name)))
        ob = next(o for o in bpy.data.objects if o.type == "MESH")
        view_sheet(ob, code)


def main():
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


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        os._exit(1)                                    # a failed stage must fail the run (Blender itself exits 0 after a script error)
