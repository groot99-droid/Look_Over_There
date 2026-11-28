"""Builds Right Door, Wrong Exit's god room Selene, "The Moon Gallery" (`rdwe_god_selene`), in Blender: the reduced game copies of the owner's
Selene furniture set, the marble gallery under a coffered vault with an oculus, its reflection (the same room mirrored about the north wall,
y = 5.5, held in the file once), the mirror-door trick, the night bake, and world/rdwe_god_selene.glb with its lightmaps.

Re-runnable, from the repo root (docs/BLENDER.md, docs/BLENDER_AREAS.md section 7). Built on tools/blender/build_rdwe_nyx.py, the first god room:

    blender -b --factory-startup --python tools/blender/build_rdwe_selene.py -- --stage copies --src <folder>   (the 13 originals and 3 props -> reduced copies)
    blender -b --factory-startup --python tools/blender/build_rdwe_selene.py -- --stage art                     (the room; saves blender/scenes/rdwe_god_selene.blend)
    blender -b --factory-startup blender/scenes/rdwe_god_selene.blend --python tools/blender/build_rdwe_selene.py -- --stage bake [--samples 512] [--device cpu]
    blender -b --factory-startup blender/scenes/rdwe_god_selene.blend --python tools/blender/build_rdwe_selene.py -- --stage export
    blender -b --factory-startup blender/scenes/rdwe_god_selene.blend --python tools/blender/build_rdwe_selene.py -- --stage render [--render-samples 128]
    (--stage bake,export,render runs several in one go; --stage views writes view sheets of the copies)
    then, in plain Python (Pillow): each lightmap PNG -> world/lightmaps/rdwe_god_selene_<n>.webp (q90), and
    python tools/webp_glb.py blender/work/farway_rdwe_god_selene/rdwe_god_selene_raw.glb world/rdwe_god_selene.glb 85
    (docs/renders/rdwe_god_selene/README.md has the exact steps; the work folder is blender/work/farway_rdwe_god_selene, git-ignored)

Stage `copies` reads the originals (never writes them): each piece is imported, a copy of it is welded and decimated (Collapse) to its budget,
given a fresh UV, and the original's base colour is baked onto the copy (Cycles, selected to active, emission, so gold and marble keep their
colour). The pier mirror P3 loses the flat panel in its opening first (it is the door the walker goes through). The copies go to
blender/models/rdwe_selene/ with a ledger. The exporter's objects (COL_, DoorLeaf_, Marker_, Link_, Arrive_, Zone_, Spot_) are kept in the
`Layout` collection for tools/blender/export_scene.py, which is not on main yet, so no world/rdwe_god_selene.json is written here.

Axes: Blender metres, x east, y north, z up, the real room's centre at the origin, the floor at z = 0. The glTF exporter's +Y up turns Blender
(x, y, z) into game (x, z, -y), so game north is -z, as everywhere in Farway. The reflection is the node `grp_reflection` (Blender location
(0, 11, 0), scale (1, -1, 1)): its children are second nodes of the real room's meshes, so the file holds every mesh once.
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
SCENE = "rdwe_god_selene"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
COPIES = ROOT / "blender/models/rdwe_selene"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"
MARGIN_PX = 8

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 512, int)
DEVICE = arg("--device", "auto")
SRC = Path(arg("--src", str(ROOT / "blender/work/selene_source")))
ONLY = arg("--only", "all")


def work():
    d = Path(arg("--work", str(ROOT / f"blender/work/farway_{SCENE}")))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- the pieces (manifest: Selene_collection_manifest.csv; budgets: Nyx's ledger)
# code, original file, short name, triangle budget, base colour size (px)
PIECES = [
    ("SE-00", "SE-00_Selene_Lamp.glb", "lamp", 15000, 1024),
    ("SE-01", "SE-01_Selene_Bedside_Table.glb", "bedside_table", 15000, 1024),
    ("SE-02", "SE-02_Selene_Armchair.glb", "armchair", 18000, 1024),
    ("SE-03", "SE-03_Selene_Dresser.glb", "dresser", 18000, 1024),
    ("SE-04", "SE-04_Selene_Tall_Cabinet.glb", "tall_cabinet", 18000, 1024),
    ("SE-05", "SE-05_Selene_Bed.glb", "bed", 24000, 2048),
    ("SE-06", "SE-06_Selene_Wall_Mirror.glb", "wall_mirror", 15000, 1024),
    ("SE-07", "SE-07_Selene_Writing_Desk.glb", "writing_desk", 18000, 1024),
    ("SE-08", "SE-08_Selene_Clock.glb", "clock", 15000, 512),
    ("SE-09", "SE-09_Selene_Hourglass.glb", "hourglass", 15000, 512),
    ("SE-10", "SE-10_Selene_Vase.glb", "moon_flask", 15000, 512),
    ("SE-11", "SE-11_Selene_Rug.glb", "rug", 2000, 1024),           # a flat 12 mm slab: 2k triangles hold its edge; the texture is the rug
    ("SE-12", "SE-12_Selene_Textiles.glb", "textiles", 15000, 1024),
    # the Higgsfield props PLAN section 7 gives Selene (normalised to 1.9 m by the generator; `size` is the plan's W x H x D in metres)
    ("P3", "P3.glb", "pier_mirror", 12000, 1024),
    ("P8", "P8.glb", "statue_selene", 12000, 1024),
    ("P19", "P19.glb", "chariot_relief", 8000, 1024),
]
PROP_SIZE = {"P3": (1.3, 2.7, 0.25), "P8": (1.0, 2.5, 0.8), "P19": (2.2, 0.9, 0.12)}
FIT_WIDTH = {"P19"}         # the relief is fitted to its width (2.2 m) and keeps its proportions; the others take the plan's height

# The pier mirror's opening, in the original's own units (Blender axes after import: x across, z up, y through the frame), read from the
# original's faces: the flat panel fills x -0.245 .. 0.345 under an arch whose top is z 0.79; the plinth's top is z -0.90. The panel is cut
# out up to the crescent's inner edge (P3_EDGE, read from the original's front view); the wall's opening behind is the box x -0.25 .. 0.335
# under the arch, and the crescent covers its west part.
P3_CUT_X0 = -0.25
P3_EDGE = ((-0.95, -0.16), (-0.75, -0.175), (-0.5, -0.22), (-0.2, -0.245), (0.2, -0.245), (0.45, -0.22), (0.6, -0.19), (0.75, -0.15), (0.9, -0.1))


def p3_edge(z):
    """The crescent's inner edge x at height z (the original's units)."""
    return float(np.interp(z, [p[0] for p in P3_EDGE], [p[1] for p in P3_EDGE])) + 0.004
P3_CUT_X1 = 0.335
P3_CUT_SPRING = 0.55
P3_CUT_TOP = 0.77


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


def cut_mirror_panel(me):
    """P3: delete the flat panel in the pier mirror's opening (faces whose centre lies inside the arch, in the frame's mid-plane), so the
    opening is open; the walker goes through it into the reflection. The original keeps its panel and is only read."""
    bm = bmesh.new()
    bm.from_mesh(me)
    cx = (P3_CUT_X0 + P3_CUT_X1) / 2
    a = (P3_CUT_X1 - P3_CUT_X0) / 2
    b = P3_CUT_TOP - P3_CUT_SPRING
    gone = []
    for f in bm.faces:
        c = f.calc_center_median()
        if abs(c.y) > 0.035 or c.z < -0.86 or not (p3_edge(c.z) < c.x < P3_CUT_X1):
            continue
        if c.z > P3_CUT_SPRING and ((c.x - cx) / a) ** 2 + ((c.z - P3_CUT_SPRING) / b) ** 2 > 1.0:
            continue
        gone.append(f)
    bmesh.ops.delete(bm, geom=gone, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(me)
    bm.free()
    print(f"  P3: cut {len(gone)} panel faces out of the opening")


def drop_fragments(me):
    """SE-09: the manifest notes a thin grey sliver and a small fragment left under the base; drop every loose part outside the main part's box."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    seen, parts = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, comp = [v], []
        seen.add(v.index)
        while stack:
            w = stack.pop()
            comp.append(w)
            for e in w.link_edges:
                o = e.other_vert(w)
                if o.index not in seen:
                    seen.add(o.index)
                    stack.append(o)
        parts.append(comp)
    parts.sort(key=len, reverse=True)
    main = parts[0]
    lo = Vector([min(v.co[i] for v in main) for i in range(3)])
    hi = Vector([max(v.co[i] for v in main) for i in range(3)])
    pad = (hi - lo) * 0.02
    lo, hi = lo - pad, hi + pad
    drop = []
    for comp in parts[1:]:
        c = sum((v.co for v in comp), Vector()) / len(comp)
        if not (all(lo[i] <= c[i] <= hi[i] for i in range(3)) and c.z > lo.z + 0.01):
            drop += comp
    bmesh.ops.delete(bm, geom=drop, context="VERTS")
    bm.to_mesh(me)
    bm.free()
    print(f"  dropped {len(drop)} vertices of loose fragments ({len(parts)} parts)")


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
    if code == "P3":
        cut_mirror_panel(me)
    if code == "SE-09":
        drop_fragments(me)
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
    mat = bpy.data.materials.new(f"Selene_{code}_{name}")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    bsdf.inputs["Roughness"].default_value = 0.7
    bsdf.inputs["Metallic"].default_value = 0.0
    mat.use_backface_culling = code != "P3"          # the mirror frame's rim is thin and open: both sides
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


# ================================================================ the room (PLAN section 4.2)
HALF_W = 4.0                               # x -4 .. 4
HALF_L = 5.5                               # y -5.5 .. 5.5
WALL_H = 4.2
VAULT_TOP = 6.0
RISE = VAULT_TOP - WALL_H
VAULT_R = (HALF_W ** 2 + RISE ** 2) / (2 * RISE)      # the segmental barrel vault's radius (5.34 m); its axis runs north-south
VAULT_Z0 = VAULT_TOP - VAULT_R
OCULUS_R = 0.75
SKY_Z = 6.9                                # the oculus shaft's top, where the sky disc is
REFL = 2 * HALF_L                          # the reflection: a point (x, y) of the real room is (x, REFL - y) in it
EYE = 0.95                                 # the RDWE walker's eye at RDWE_SCALE 1.7 (controls.js: 1.62 / 1.7)
SPAWN = Vector((0.0, -4.6, 0.0))
DOOR_W, DOOR_H = 0.94, 2.16
PAINTED = Vector((HALF_W, -2.5, 0.0))      # the painted door on the east wall; its real twin in the reflection is at (4, 13.5)
REAL_DOOR = Vector((HALF_W, REFL - PAINTED.y, 0.0))
SKIRT_Z, DADO_Z, CORNICE_Z = 0.15, 1.0, 4.05
PILASTERS_Y = (-4.4, -0.8, 3.5)            # the Ionic half-columns on the long walls (and the vault's transverse ribs over them)
COMPASS = {"E": 0, "N": 90, "W": 180, "S": 270}
WALLS = {"S": ((0, -1), HALF_L), "N": ((0, 1), HALF_L), "W": ((-1, 0), HALF_W), "E": ((1, 0), HALF_W)}

# the mirror's opening in the room (metres): the P3 copy is scaled by P3_K and centred, then moved west by P3_SHIFT so the opening is centred
P3_SRC_X = (-0.457432, 0.455454)          # the original's x extent (its own units)
P3_SRC_Z0 = -0.950712                      # its lowest point
P3_K = 2.7 / (0.947545 - P3_SRC_Z0)        # the plan's 2.7 m over the original's height
P3_SRC_CX = (P3_SRC_X[0] + P3_SRC_X[1]) / 2
P3_SHIFT = -P3_K * ((P3_CUT_X0 + P3_CUT_X1) / 2 - P3_SRC_CX)     # where the copy's centre goes, so the opening's centre is at x = 0
OPEN_A = P3_K * (P3_CUT_X1 - P3_CUT_X0) / 2                     # the opening's half-width (0.36 m)
OPEN_SPRING = P3_K * (P3_CUT_SPRING - P3_SRC_Z0)                # 2.13 m
OPEN_RISE = P3_K * (P3_CUT_TOP - P3_CUT_SPRING)                 # 0.31 m: the arch's top at 2.45 m

# which way each copy faces as made (read from view sheets of the copies): the compass angle its front points to in Blender.
# The set's multi-view pieces face +X; the props face -Y
NATIVE_FRONT = {"SE-00": 0, "SE-01": 0, "SE-02": 0, "SE-03": 0, "SE-04": 0, "SE-05": 0, "SE-06": 0, "SE-07": 0, "SE-08": 0, "SE-09": 0,
                "SE-10": 0, "SE-11": 0, "SE-12": 0, "P3": 270, "P8": 270, "P19": 270}

# placement (PLAN 4.2): code, object name, (x, y), facing, how: ("floor"), ("wall", wall, gap), ("hang", wall, gap, z), ("on", support, (dx, dy))
PLACE = [
    ("SE-11", "SE-11_rug", (0.0, 0.0), "N", ("floor",)),
    ("SE-05", "SE-05_bed", (-2.85, 1.5), "E", ("wall", "W", 0.04)),
    ("SE-01", "SE-01_bedside_table_N", (-3.8, 2.75), "E", ("wall", "W", 0.04)),
    ("SE-01", "SE-01_bedside_table_S", (-3.8, 0.25), "E", ("wall", "W", 0.04)),
    ("SE-03", "SE-03_dresser", (3.75, 1.8), "W", ("wall", "E", 0.03)),
    ("SE-06", "SE-06_wall_mirror", (3.9, 1.8), "W", ("hang", "E", 0.02, 1.02)),
    ("SE-04", "SE-04_tall_cabinet", (3.7, 4.6), "W", ("wall", "E", 0.04)),
    ("SE-07", "SE-07_writing_desk", (-3.75, -3.2), "E", ("wall", "W", 0.03)),
    ("SE-02", "SE-02_armchair", (-2.85, -3.2), "W", ("floor",)),
    ("P3", "P3_pier_mirror", (P3_SHIFT, 5.3), "S", ("wall", "N", 0.0)),
    ("P8", "P8_statue_selene", (-2.6, -5.0), "N", ("wall", "S", 0.1)),
    ("P19", "P19_chariot_relief", (-3.95, 1.5), "E", ("hang", "W", 0.01, 2.15)),
    # the smalls, on the furniture
    ("SE-00", "SE-00_lamp", (0.0, 0.0), "E", ("on", "SE-01_bedside_table_N")),
    ("SE-10", "SE-10_moon_flask", (0.0, 0.0), "E", ("on", "SE-01_bedside_table_S")),
    ("SE-09", "SE-09_hourglass", (0.0, -0.38), "W", ("on", "SE-03_dresser")),
    ("SE-08", "SE-08_clock", (0.0, 0.2), "E", ("on", "SE-07_writing_desk")),
    ("SE-12", "SE-12_textiles", (0.55, -0.3), "E", ("on", "SE-05_bed")),
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


def dot(img, p, col, r):
    lo_r, hi_r = int(max(0, p[0] - r - 2)), int(min(img.shape[0], p[0] + r + 3))
    lo_c, hi_c = int(max(0, p[1] - r - 2)), int(min(img.shape[1], p[1] + r + 3))
    yy, xx = np.mgrid[lo_r:hi_r, lo_c:hi_c].astype(np.float32)
    a = np.clip(r + 0.5 - np.hypot(yy - p[0], xx - p[1]), 0, 1)[..., None]
    img[lo_r:hi_r, lo_c:hi_c] = img[lo_r:hi_r, lo_c:hi_c] * (1 - a) + np.array(col) * a


GOLD_S = (0.86, 0.66, 0.30)       # sRGB gold for the painted lines


def marble_field(S, seed, scale=24):
    rng = np.random.default_rng(seed)
    n1 = wrap_blur(rng.random((S, S)).astype(np.float32), scale, 2)
    n2 = wrap_blur(rng.random((S, S)).astype(np.float32), max(2, scale // 4), 2)
    n1 = (n1 - n1.min()) / (n1.max() - n1.min())
    n2 = (n2 - n2.min()) / (n2.max() - n2.min())
    f = n1 * 7.0 + n2 * 1.4
    v = np.abs((f % 1.0) - 0.5)
    vein = np.clip(1 - v / 0.02, 0, 1) * (n2 > 0.4)
    return n1, vein


def floor_pixels():
    """The floor tile (FLOOR_TILE metres): a chequer of white marble and pale moon-grey marble, grey veins, a fine joint. Seamless."""
    S = 1024
    n1, vein = marble_field(S, 41, 30)
    u, v = np.meshgrid((np.arange(S) + 0.5) / S, (np.arange(S) + 0.5) / S)
    cheq = ((u < 0.5) ^ (v < 0.5))
    white = np.array([0.90, 0.89, 0.87])
    moon = np.array([0.74, 0.78, 0.84])
    img = np.where(cheq[..., None], moon, white).astype(np.float32)
    img *= (0.93 + 0.1 * n1)[..., None]
    img = img * (1 - 0.45 * vein[..., None]) + np.array([0.52, 0.54, 0.58]) * 0.45 * vein[..., None]
    joint = (np.minimum(np.abs(u - 0.5), np.minimum(u, 1 - u)) < 0.0025) | (np.minimum(np.abs(v - 0.5), np.minimum(v, 1 - v)) < 0.0025)
    img[joint] *= 0.72
    return np.clip(img, 0, 1).astype(np.float32)


def granite_pixels():
    """Dark granite (the furniture's plinths): black and grey flecks. Seamless tile."""
    S = 512
    rng = np.random.default_rng(13)
    a = wrap_blur(rng.random((S, S)).astype(np.float32), 1, 1)
    b = wrap_blur(rng.random((S, S)).astype(np.float32), 6, 2)
    b = (b - b.min()) / (b.max() - b.min())
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.36, 0.36, 0.38)                               # sRGB: dark grey, not black (it is drawn unlit on the page)
    img *= (0.75 + 0.5 * a)[..., None] * (0.85 + 0.3 * b)[..., None]
    fleck = rng.random((S, S)) > 0.985
    img[fleck] = (0.72, 0.72, 0.73)
    return np.clip(img, 0, 1).astype(np.float32)


def white_marble_pixels():
    """White marble for the dado, the cornice, the columns and the ribs: faint grey-blue veins. Seamless tile."""
    S = 512
    n1, vein = marble_field(S, 5, 18)
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.92, 0.91, 0.89)
    img *= (0.95 + 0.07 * n1)[..., None]
    img = img * (1 - 0.35 * vein[..., None]) + np.array([0.60, 0.64, 0.70]) * 0.35 * vein[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def plaster_pixels():
    """The walls between the pilasters: pale moon-blue plaster, a soft cloud in it. Seamless tile."""
    S = 512
    rng = np.random.default_rng(9)
    n = wrap_blur(rng.random((S, S)).astype(np.float32), 20, 2)
    n = (n - n.min()) / (n.max() - n.min())
    f = wrap_blur(rng.random((S, S)).astype(np.float32), 2, 1)
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.62, 0.71, 0.84)
    img *= (0.9 + 0.16 * n)[..., None] * (0.97 + 0.06 * f)[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def coffer_pixels():
    """One coffer of the vault (COFFER metres square): a white marble frame, stepped down to a moon-blue sunk panel with a gilt rosette (a
    small eight-rayed star). Seamless (the frame is split across the tile's edges)."""
    S = 512
    u, v = np.meshgrid((np.arange(S) + 0.5) / S, (np.arange(S) + 0.5) / S)
    d = np.maximum(np.abs(u - 0.5), np.abs(v - 0.5))           # 0 at the centre, 0.5 at the edge
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.90, 0.89, 0.87)                                # the frame
    step1 = d < 0.36
    step2 = d < 0.30
    img[step1] = (0.80, 0.80, 0.80)
    img[step2] = (0.55, 0.65, 0.82)                            # the sunk panel
    sh = step1 & ~step2 & ((v - 0.5 < -np.abs(u - 0.5)) | (u - 0.5 < -np.abs(v - 0.5)))   # a shade on two inner edges: reads as depth
    img[sh] *= 0.78
    rim = (np.abs(d - 0.36) < 0.004) | (np.abs(d - 0.30) < 0.004)
    img[rim] = GOLD_S
    r = np.hypot(u - 0.5, v - 0.5)
    th = np.arctan2(v - 0.5, u - 0.5)
    star = r < (0.035 + 0.06 * np.abs(np.cos(4 * th)) ** 6)
    img[star] = GOLD_S
    n1, vein = marble_field(S, 21, 16)
    img *= (0.96 + 0.06 * n1)[..., None]
    return np.clip(wrap_blur(img, 1, 1), 0, 1).astype(np.float32)


def placard_pixels():
    """The museum placard by the entrance (PLAN 2.2): dark letters on white marble, a gold rule."""
    W, H = 768, 512
    img = np.zeros((H, W, 3), np.float32)
    img[:] = (0.86, 0.86, 0.85)
    img[18:24, 30:W - 30] = img[H - 24:H - 18, 30:W - 30] = GOLD_S
    draw_text(img, "SELENE", (40, 170, 0, W), (0.08, 0.10, 0.16), 0.85)
    draw_text(img, "MOON - THE MOON GALLERY", (190, 270, 0, W), (0.55, 0.40, 0.14), 0.92)
    draw_text(img, "NINETY-NINE NOCTURNE SUITE", (290, 370, 0, W), (0.14, 0.16, 0.22), 0.92)
    draw_text(img, "XIII PIECES. MARBLE. GILT. GLASS.", (380, 460, 0, W), (0.30, 0.32, 0.38), 0.92)
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def painted_door_pixels():
    """The door that is only paint (decor_painted_door): a white panelled door with gilt mouldings and a brass knob, painted flat, with painted
    shadows and no light at its foot. Column 0 is the door's south edge (the knob's side), row 0 its top."""
    W, H = 470, 1080
    img = np.zeros((H, W, 3), np.float32)
    img[:] = (0.90, 0.90, 0.87)
    rows = lambda z: int((1 - z / DOOR_H) * H)
    cols = lambda u: int(u / DOOR_W * W)
    for (u0, u1, z0, z1) in ((0.14, 0.80, 1.20, 2.00), (0.14, 0.80, 0.18, 1.05)):
        r0, r1, c0, c1 = rows(z1), rows(z0), cols(u0), cols(u1)
        img[r0:r1, c0:c1] = (0.84, 0.84, 0.82)
        img[r0:r0 + 6, c0:c1] = (0.62, 0.62, 0.60)              # painted shadow under the top moulding
        img[r0:r1, c0:c0 + 6] = (0.66, 0.66, 0.64)
        img[r1 - 4:r1, c0:c1] = (0.97, 0.97, 0.95)               # painted light on the lower edge
        img[r0:r1, c1 - 4:c1] = (0.97, 0.97, 0.95)
        img[r0 - 3:r0, c0 - 3:c1 + 3] = GOLD_S
        img[r1:r1 + 3, c0 - 3:c1 + 3] = GOLD_S
        img[r0 - 3:r1 + 3, c0 - 3:c0] = GOLD_S
        img[r0 - 3:r1 + 3, c1:c1 + 3] = GOLD_S
    dot(img, (rows(1.02), cols(0.075)), (0.30, 0.22, 0.08), 15)   # the knob's painted shadow
    dot(img, (rows(1.05), cols(0.07)), (0.80, 0.62, 0.28), 13)
    dot(img, (rows(1.06), cols(0.065)), (0.98, 0.88, 0.60), 4)
    img[H - 10:H] = (0.30, 0.30, 0.32)                           # a painted shadow at the foot: no light under this door
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def sky_pixels(full):
    """The oculus's sky disc: night blue with stars, and the moon, a crescent (the real room) or full (the reflection)."""
    S = 512
    rng = np.random.default_rng(3 if full else 2)
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.020, 0.035, 0.09)
    r = np.hypot(yy - S / 2, xx - S / 2) / (S / 2)
    img *= (1.3 - 0.4 * r)[..., None]
    for _ in range(90):
        dot(img, (rng.uniform(0, S), rng.uniform(0, S)), (0.8, 0.82, 0.9), rng.uniform(0.6, 1.6))
    c = (S * 0.5, S * 0.52)
    R = S * 0.23
    dist = np.hypot(yy - c[0], xx - c[1])
    moon = dist < R
    halo = np.clip(1 - (dist - R) / (S * 0.18), 0, 1) ** 2 * 0.35
    if not full:
        cut = np.hypot(yy - c[0] + R * 0.12, xx - c[1] - R * 0.42) < R * 0.92
        moon = moon & ~cut
        halo *= 0.6
    img = img + np.array([0.45, 0.50, 0.62]) * halo[..., None]
    rng2 = np.random.default_rng(8)
    maria = wrap_blur(rng2.random((S, S)).astype(np.float32), 14, 2)
    maria = (maria - maria.min()) / (maria.max() - maria.min())
    mcol = np.array([0.96, 0.95, 0.88])[None, None, :] * (0.82 + 0.18 * (maria > 0.45))[..., None]
    img = np.where(moon[..., None], mcol, img)
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


FLOOR_TILE = 1.5
MARBLE_TILE = 1.2
PLASTER_TILE = 1.6
COFFER = 2 * VAULT_R * math.asin(HALF_W / VAULT_R) / 8      # eight coffers across the vault (about 1.13 m)


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


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, img=None, emit=None, double=False, alpha=None, emit_img=None):
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
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        nt.links.new(n.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emit_img[1]
        bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
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
    material("Floor_Marble", img=gen["floor"], rough=0.2)
    material("Granite", img=gen["granite"], rough=0.35)
    material("White_Marble", img=gen["marble"], rough=0.3)
    material("Wall_Plaster", img=gen["plaster"], rough=0.85)
    material("Vault_Coffers", img=gen["coffer"], rough=0.8)
    material("Column_Marble", img=gen["marble"], rough=0.3)
    material("Gold_Trim", color=(0.55, 0.38, 0.12), rough=0.35, metal=0.9)          # gilt: the page draws it unlit, so not too light
    material("Door_White", color=(0.80, 0.80, 0.76), rough=0.5)
    material("Painted_Door", img=gen["painted"], rough=0.6)
    material("Reveal_Dark", color=(0.02, 0.022, 0.03), rough=0.9)
    material("Placard", img=gen["placard"], rough=0.5)
    material("Door_Glow", color=(1.0, 0.92, 0.75), emit=((1.0, 0.90, 0.70), 4.0))            # the light beyond the real door
    material("Picture_Light_Emit", color=(1.0, 0.9, 0.7), emit=((1.0, 0.85, 0.6), 4.0))     # the placard light's strip: seen, but it lights nothing
    material("Sconce_Gilt", color=(0.62, 0.42, 0.14), rough=0.35, metal=0.9)                 # not baked: inches from its own bulb
    material("Lamp_Emit", color=(1.0, 0.88, 0.7), emit=((1.0, 0.80, 0.55), 6.0))
    material("Moon_Crescent", emit_img=(gen["sky_crescent"], 1.0))
    material("Moon_Full", emit_img=(gen["sky_full"], 1.0))
    material("Mirror_Glass", color=(0.80, 0.85, 0.95), rough=0.05, emit=((0.70, 0.76, 0.88), 0.06), alpha=0.10)
    material("Moon_Shaft", color=(0.0, 0.0, 0.0), emit=((0.62, 0.72, 1.0), 0.35), alpha=0.07, double=True)
    material("Moon_Pool", color=(0.0, 0.0, 0.0), emit=((0.80, 0.86, 1.0), 1.0), alpha=0.45)


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


def prism(bm, pts, off, caps=True):
    """A planar loop `pts` extruded by `off` (centred on the loop), its faces outward: the loop is made counter-clockwise seen from +off, so each
    side face (bot i, bot i+1, top i+1, top i) faces out."""
    nrm = off.normalized()
    e1 = (pts[1] - pts[0]).normalized()
    e2 = nrm.cross(e1)
    area = sum((pts[i] - pts[0]).dot(e1) * (pts[(i + 1) % len(pts)] - pts[0]).dot(e2) - (pts[(i + 1) % len(pts)] - pts[0]).dot(e1) * (pts[i] - pts[0]).dot(e2)
               for i in range(len(pts)))
    if area < 0:
        pts = pts[::-1]
    top = [bm.verts.new(p + off / 2) for p in pts]
    bot = [bm.verts.new(p - off / 2) for p in pts]
    k = len(pts)
    for i in range(k):
        bm.faces.new([bot[i], bot[(i + 1) % k], top[(i + 1) % k], top[i]])
    if caps:
        f1 = bm.faces.new(top)
        f2 = bm.faces.new(bot[::-1])
        bmesh.ops.triangulate(bm, faces=[f1, f2], ngon_method="EAR_CLIP")


def arch_pts(uc, a, spring, rise, n=16):
    """An elliptic arch from its left foot to its right foot (u, z)."""
    return [(uc - a * math.cos(math.pi * i / n), spring + rise * math.sin(math.pi * i / n)) for i in range(n + 1)]


def openings(name):
    """The openings per wall: (u0, u1, spring, rise). The north wall's is the mirror's arch."""
    if name == "S":
        return [(-DOOR_W / 2, DOOR_W / 2, DOOR_H, 0.0)]
    if name == "N":
        return [(-OPEN_A, OPEN_A, OPEN_SPRING, OPEN_RISE)]
    if name == "E":
        return [(PAINTED.y - DOOR_W / 2, PAINTED.y + DOOR_W / 2, DOOR_H, 0.0)]
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


def vault_z(x):
    return VAULT_Z0 + math.sqrt(max(0.0, VAULT_R ** 2 - x * x))


def vault_s(x):
    """Arc length along the vault from its crown to x."""
    return VAULT_R * math.asin(max(-1.0, min(1.0, x / VAULT_R)))


def crescent_outline(R, r, d, n=24):
    """A crescent in 2D: inside the circle (0, 0, R), outside the circle (d, 0, r); horns toward +x. Points round its outline."""
    xi = (R * R - r * r + d * d) / (2 * d)              # the circles meet at x = xi
    yi = math.sqrt(max(1e-9, R * R - xi * xi))
    a0 = math.atan2(yi, xi)
    outer = [(R * math.cos(a), R * math.sin(a)) for a in np.linspace(a0, 2 * math.pi - a0, n)]
    b0 = math.atan2(yi, xi - d)
    inner = [(d + r * math.cos(b), r * math.sin(b)) for b in np.linspace(2 * math.pi - b0, b0, n)][1:-1]
    return outer + inner


def build_shell():
    # the floor: one rectangle under the chequered marble tile
    bm = bmesh.new()
    poly(bm, [Vector((-HALF_W, -HALF_L, 0)), Vector((HALF_W, -HALF_L, 0)), Vector((HALF_W, HALF_L, 0)), Vector((-HALF_W, HALF_L, 0))], Vector((0, 0, 1)))
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for lp in f.loops:
            lp[uvl].uv = ((lp.vert.co.x + 0.75) / FLOOR_TILE, (lp.vert.co.y + 0.75) / FLOOR_TILE)
    mesh_obj("Floor", bm, "Floor_Marble")
    # a granite border round the floor, 0.3 m wide, a hair above it
    bm = bmesh.new()
    w = 0.3
    for x0, y0, x1, y1 in ((-HALF_W, -HALF_L, HALF_W, -HALF_L + w), (-HALF_W, HALF_L - w, HALF_W, HALF_L),
                           (-HALF_W, -HALF_L + w, -HALF_W + w, HALF_L - w), (HALF_W - w, -HALF_L + w, HALF_W, HALF_L - w)):
        poly(bm, [Vector((x0, y0, 0.002)), Vector((x1, y0, 0.002)), Vector((x1, y1, 0.002)), Vector((x0, y1, 0.002))], Vector((0, 0, 1)))
    box_uv(bm, 1.0)
    mesh_obj("Floor_Border", bm, "Granite")
    # the walls: granite skirting, a white marble dado, moon-blue plaster up to the cornice
    for mat, z0, z1, tile in (("Granite", 0.0, SKIRT_Z, 1.0), ("White_Marble", SKIRT_Z, DADO_Z, MARBLE_TILE), ("Wall_Plaster", DADO_Z, CORNICE_Z, PLASTER_TILE)):
        bm = bmesh.new()
        for name in WALLS:
            wall_band(bm, name, z0, z1)
        box_uv(bm, tile)
        mesh_obj(f"Wall_{mat}", bm, mat)
    # mouldings: the white marble cornice and the dado rail's cap; gilt beads on the rail and under the cornice
    bm = bmesh.new()
    for name in WALLS:
        wall_strip(bm, name, CORNICE_Z, WALL_H, 0.10)
        wall_strip(bm, name, CORNICE_Z - 0.16, CORNICE_Z - 0.03, 0.05)
        wall_strip(bm, name, DADO_Z - 0.05, DADO_Z + 0.01, 0.035)
    box_uv(bm, MARBLE_TILE)
    mesh_obj("Mouldings_Marble", bm, "White_Marble")
    bm = bmesh.new()
    for name in WALLS:
        wall_strip(bm, name, DADO_Z + 0.01, DADO_Z + 0.04, 0.03)
        wall_strip(bm, name, CORNICE_Z - 0.03, CORNICE_Z, 0.065)
    box_uv(bm, 1.0)
    mesh_obj("Mouldings_Gilt", bm, "Gold_Trim")
    # the lunettes: the short walls above the cornice, up to the vault
    bm = bmesh.new()
    for y, toward in ((-HALF_L, Vector((0, 1, 0))), (HALF_L, Vector((0, -1, 0)))):
        poly(bm, [Vector((x, y, vault_z(x))) for x in np.linspace(-HALF_W, HALF_W, 25)], toward)
    box_uv(bm, PLASTER_TILE)
    mesh_obj("Lunettes", bm, "Wall_Plaster")
    build_vault()


def build_vault():
    """The coffered barrel vault, its axis north-south, from the cornice (4.2 m) to the crown (6.0 m), with a round oculus over the room's
    centre: the faces round the oculus are left out and a broad gilt ring under the vault hides the cut. The coffers are the texture; marble ribs
    cross the vault over each pair of pilasters."""
    nx, ny = 24, 44
    xs = np.linspace(-HALF_W, HALF_W, nx + 1)
    ys = np.linspace(-HALF_L, HALF_L, ny + 1)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    V = [[bm.verts.new((x, y, vault_z(x))) for x in xs] for y in ys]
    for j in range(ny):
        for i in range(nx):
            quad = [V[j][i], V[j][i + 1], V[j + 1][i + 1], V[j + 1][i]]
            if min(Vector((v.co.x, v.co.y)).length for v in quad) < OCULUS_R + 0.02:
                continue
            f = bm.faces.new(quad)
            cx = (xs[i] + xs[i + 1]) / 2
            face_toward(f, Vector((-cx, 0, VAULT_Z0 - vault_z(cx))))
            for lp in f.loops:
                p = lp.vert.co
                lp[uvl].uv = (vault_s(p.x) / COFFER + 0.5, p.y / COFFER + 0.5)
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    mesh_obj("Vault", bm, "Vault_Coffers", smooth=True)
    # the ribs: a band 0.34 m wide hanging 0.09 m under the vault, over each pair of pilasters
    bm = bmesh.new()
    for y0 in PILASTERS_Y:
        prev = None
        for x in xs:
            z = vault_z(x)
            nrm = Vector((-x, 0, VAULT_Z0 - z)).normalized()          # toward the vault's axis (into the room)
            ring = [Vector((x, y0 - 0.17, z)), Vector((x, y0 - 0.17, z)) + nrm * 0.09, Vector((x, y0 + 0.17, z)) + nrm * 0.09, Vector((x, y0 + 0.17, z))]
            cur = [bm.verts.new(p) for p in ring]
            if prev:
                for k, toward in ((0, Vector((0, -1, 0))), (1, nrm), (2, Vector((0, 1, 0)))):
                    f = bm.faces.new([prev[k], cur[k], cur[k + 1], prev[k + 1]])
                    face_toward(f, toward)
            prev = cur
    box_uv(bm, MARBLE_TILE)
    mesh_obj("Vault_Ribs", bm, "Column_Marble")
    # the oculus: a broad gilt ring under the vault (it hides the stepped edge of the cut), a plaster shaft up to the sky disc
    seg = 48
    r0, r1 = OCULUS_R, OCULUS_R + 0.48
    bm = bmesh.new()
    inner = [bm.verts.new((r0 * math.cos(2 * math.pi * i / seg), r0 * math.sin(2 * math.pi * i / seg), vault_z(r0 * math.cos(2 * math.pi * i / seg)) - 0.05)) for i in range(seg)]
    outer = [bm.verts.new((r1 * math.cos(2 * math.pi * i / seg), r1 * math.sin(2 * math.pi * i / seg), vault_z(r1 * math.cos(2 * math.pi * i / seg)) - 0.02)) for i in range(seg)]
    for i in range(seg):
        f = bm.faces.new([inner[i], outer[i], outer[(i + 1) % seg], inner[(i + 1) % seg]])
        face_toward(f, Vector((0, 0, -1)))
    box_uv(bm, 1.0)
    mesh_obj("Oculus_Ring", bm, "Gold_Trim", smooth=True)
    bm = bmesh.new()
    lo = [bm.verts.new(v.co) for v in []]
    lo = [bm.verts.new((r0 * math.cos(2 * math.pi * i / seg), r0 * math.sin(2 * math.pi * i / seg), vault_z(r0 * math.cos(2 * math.pi * i / seg)) - 0.05)) for i in range(seg)]
    hi = [bm.verts.new((r0 * math.cos(2 * math.pi * i / seg), r0 * math.sin(2 * math.pi * i / seg), SKY_Z)) for i in range(seg)]
    for i in range(seg):
        f = bm.faces.new([lo[i], lo[(i + 1) % seg], hi[(i + 1) % seg], hi[i]])
        c = f.calc_center_median()
        face_toward(f, -Vector((c.x, c.y, 0)))
    box_uv(bm, PLASTER_TILE)
    mesh_obj("Oculus_Shaft", bm, "Wall_Plaster", smooth=True)


def sky_disc(name, y, mat):
    bm = bmesh.new()
    seg = 48
    pts = [Vector((OCULUS_R * 1.02 * math.cos(2 * math.pi * i / seg), y + OCULUS_R * 1.02 * math.sin(2 * math.pi * i / seg), SKY_Z - 0.01)) for i in range(seg)]
    f = poly(bm, pts, Vector((0, 0, -1)), tri=False)
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp in f.loops:
        p = lp.vert.co
        lp[uvl].uv = (0.5 + p.x / (2.1 * OCULUS_R), 0.5 + (p.y - y) / (2.1 * OCULUS_R))
    bmesh.ops.triangulate(bm, faces=[f], ngon_method="EAR_CLIP")
    return mesh_obj(name, bm, mat)


MOON_POOL_R = 0.8


def build_moon():
    """The trick's moons. The real room's oculus shows a crescent (decor_moon_crescent); the reflection's, a full moon (decor_moon_full). Under
    each, a faint shaft of moonlight and its pool on the rug take the moon's shape: a crescent here, a full disc in the glass. Each is its own
    node, outside the reflection's instancing."""
    sky_disc("decor_moon_crescent", 0.0, "Moon_Crescent")
    sky_disc("decor_moon_full", REFL, "Moon_Full")
    R = MOON_POOL_R
    shapes = (("crescent", 0.0, crescent_outline(R, R * 0.9, R * 0.45, 28)),
              ("full", REFL, [(R * math.cos(a), R * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 48, endpoint=False)]))
    for tag, y, outline in shapes:
        # the pool, on the rug (12 mm) under the oculus; the crescent's horns toward the east wall's painted door
        bm = bmesh.new()
        poly(bm, [Vector((x, y + yy, 0.016)) for x, yy in outline], Vector((0, 0, 1)))
        box_uv(bm, 2.0)
        mesh_obj(f"decor_moonpool_{tag}", bm, "Moon_Pool")
        # the shaft: the same outline, straight up to the oculus (sides only; seen from both sides)
        bm = bmesh.new()
        top_z = vault_z(0) - 0.1
        prism(bm, [Vector((x, y + yy, (0.02 + top_z) / 2)) for x, yy in outline], Vector((0, 0, top_z - 0.02)), caps=False)
        box_uv(bm, 2.0)
        mesh_obj(f"decor_moonshaft_{tag}", bm, "Moon_Shaft")


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
    ob.data.materials.append(MATS["Gold_Trim"])
    ob.location = loc
    return ob


def casing(bm, name, u0, u1, top, w=0.14, d=0.05):
    """A white marble architrave round a door opening (jambs and head), proud of the wall by d."""
    n, t, dist, L = wall_frame(name)
    for uu in (u0 - w / 2, u1 + w / 2):
        add_box(bm, wall_pt(name, uu, (top + w) / 2, d / 2), (abs(t.x) * w + abs(n.x) * d, abs(t.y) * w + abs(n.y) * d, top + w))
    span = u1 - u0 + 2 * w
    add_box(bm, wall_pt(name, (u0 + u1) / 2, top + w / 2, d / 2), (abs(t.x) * span + abs(n.x) * d, abs(t.y) * span + abs(n.y) * d, w))


def build_doors():
    """The way in (DoorLeaf_Selene_In, south wall), the painted door (decor_painted_door, east wall: flat paint over an opening), and its
    real twin in the reflection (DoorLeaf_Selene_Painted at (4, 13.5)): a leaf with a knob and light under it, the exit to Hypnos."""
    bm = bmesh.new()
    casing(bm, "S", -DOOR_W / 2, DOOR_W / 2, DOOR_H)
    casing(bm, "E", PAINTED.y - DOOR_W / 2, PAINTED.y + DOOR_W / 2, DOOR_H)
    box_uv(bm, MARBLE_TILE)
    mesh_obj("Door_Casings", bm, "White_Marble")
    # the reveals behind both openings: dark boxes seen from inside, open toward the room
    bm = bmesh.new()
    for c, size, axis in ((Vector((0, -HALF_L - 0.18, DOOR_H / 2)), (DOOR_W, 0.36, DOOR_H), 1), (Vector((HALF_W + 0.18, PAINTED.y, DOOR_H / 2)), (0.36, DOOR_W, DOOR_H), 0)):
        before = set(bm.faces)
        add_box(bm, c, size)
        new = [f for f in bm.faces if f not in before]
        drop = []
        for f in new:
            fc = f.calc_center_median()
            face_toward(f, c - fc)
            if abs(fc[axis]) < abs(c[axis]) - 0.17:
                drop.append(f)                         # the face toward the room: the opening
        bmesh.ops.delete(bm, geom=drop, context="FACES_ONLY")
    box_uv(bm, 1.0)
    mesh_obj("Door_Reveals", bm, "Reveal_Dark")
    bm = bmesh.new()
    x = HALF_W + 0.35
    y0, y1 = PAINTED.y - DOOR_W / 2, PAINTED.y + DOOR_W / 2
    poly(bm, [Vector((x, y0, 0)), Vector((x, y1, 0)), Vector((x, y1, DOOR_H)), Vector((x, y0, DOOR_H))], Vector((-1, 0, 0)))
    poly(bm, [Vector((HALF_W + 0.01, y0, 0.001)), Vector((x, y0, 0.001)), Vector((x, y1, 0.001)), Vector((HALF_W + 0.01, y1, 0.001))], Vector((0, 0, 1)))
    box_uv(bm, 1.0)
    mesh_obj("Door_Glow", bm, "Door_Glow")
    # the way in: hinge on the west edge, the room to the north
    door_leaf("DoorLeaf_Selene_In", "Door_White", Vector((-DOOR_W / 2, -HALF_L + 0.03, 0.0)), (1, 0, 0), (0, 1, 0))
    # the painted door: a flat panel over the east opening, the paint toward the room
    bm = bmesh.new()
    f = poly(bm, [Vector((HALF_W - 0.004, y0, 0)), Vector((HALF_W - 0.004, y1, 0)), Vector((HALF_W - 0.004, y1, DOOR_H)), Vector((HALF_W - 0.004, y0, DOOR_H))],
             Vector((-1, 0, 0)), tri=False)
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp in f.loops:
        p = lp.vert.co
        lp[uvl].uv = ((p.y - y0) / DOOR_W, p.z / DOOR_H)
    mesh_obj("decor_painted_door", bm, "Painted_Door")
    # its real twin in the reflection: hinge on the south edge, the knob on the north (the painted knob, mirrored), the room to the west
    door_leaf("DoorLeaf_Selene_Painted", "Door_White", Vector((HALF_W - 0.03, REAL_DOOR.y - DOOR_W / 2, 0.0)), (0, 1, 0), (-1, 0, 0))


PLACARD_C = Vector((1.25, -HALF_L + 0.012, 1.25))


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


def build_pilasters():
    """Ionic half-columns on the long walls (PLAN: Blender Ionic columns): a granite plinth, a marble torus, a fluted shaft, a gilt capital
    (echinus, two volutes, abacus). Half of each round, engaged in the wall."""
    marble, gold, granite = bmesh.new(), bmesh.new(), bmesh.new()
    R = 0.17
    seg = 32
    flutes = 8
    for wall in ("W", "E"):
        n, t, dist, L = wall_frame(wall)
        for y in PILASTERS_Y:
            base = Vector((n.x * dist, y, 0.0))
            inward = -n
            side = Vector((0, 1, 0))
            add_box(granite, base + inward * 0.11 + Vector((0, 0, 0.15)), (0.22, 0.46, 0.30))

            def ring(z, r, fl):
                out = []
                for i in range(seg + 1):
                    a = math.pi * i / seg - math.pi / 2           # -90 .. 90 degrees, 0 = straight into the room
                    rr = r * (1 - (0.07 * math.sin(flutes * (a + math.pi / 2)) ** 2 if fl else 0.0))
                    out.append(base + inward * (rr * math.cos(a)) + side * (rr * math.sin(a)) + Vector((0, 0, z)))
                return out

            prof = [(0.30, R + 0.05, False), (0.34, R + 0.06, False), (0.40, R + 0.04, False), (0.44, R, False), (0.47, R, True),
                    (2.1, R * 0.97, True), (3.66, R * 0.92, True), (3.70, R * 0.92, False), (3.74, R * 0.98, False)]
            rings = [[marble.verts.new(p) for p in ring(z, r, fl)] for z, r, fl in prof]
            for a, b in zip(rings[:-1], rings[1:]):
                for i in range(seg):
                    f = marble.faces.new([a[i], a[i + 1], b[i + 1], b[i]])
                    c = f.calc_center_median()
                    face_toward(f, Vector((c.x - base.x, c.y - base.y, 0)))
            add_cyl(gold, base + Vector((0, 0, 3.74)), base + Vector((0, 0, 3.86)), R * 0.98, R * 1.18, seg=16)
            for s in (-1, 1):
                add_cyl(gold, base + side * (s * 0.2) + Vector((0, 0, 3.84)), base + side * (s * 0.2) + inward * 0.26 + Vector((0, 0, 3.84)), 0.065, seg=12)
            add_box(gold, base + inward * 0.12 + Vector((0, 0, 3.93)), (0.26, 0.52, 0.06))
            add_box(gold, base + inward * 0.10 + Vector((0, 0, 3.99)), (0.22, 0.46, 0.06))
    box_uv(marble, MARBLE_TILE)
    mesh_obj("Pilasters", marble, "Column_Marble", smooth=True)
    box_uv(gold, 1.0)
    mesh_obj("Pilaster_Capitals", gold, "Gold_Trim", smooth=True)
    box_uv(granite, 1.0)
    mesh_obj("Pilaster_Plinths", granite, "Granite")


def build_floor_crescents():
    """A ring of twelve gilt crescents inlaid in the floor round the rug (PLAN: a ring of gilt crescents round the rug)."""
    bm = bmesh.new()
    out = crescent_outline(0.15, 0.13, 0.07, 14)
    for k in range(12):
        a = 2 * math.pi * k / 12
        c = Vector((1.38 * math.cos(a), 1.38 * math.sin(a), 0.003))
        rot = Matrix.Rotation(a, 3, "Z")
        poly(bm, [c + rot @ Vector((x, y, 0)) for x, y in out], Vector((0, 0, 1)))
    box_uv(bm, 1.0)
    mesh_obj("Floor_Crescents", bm, "Gold_Trim")


CRESCENT_PLINTH = Vector((2.6, -4.85, 0.0))


def build_crescent_plinth():
    """Where the plan put Poly Haven's horse head (nothing was downloaded for this room), a granite block with a white marble crescent moon
    standing on it, horns up, facing the room."""
    c = CRESCENT_PLINTH
    bm = bmesh.new()
    add_box(bm, c + Vector((0, 0, 0.5)), (0.56, 0.56, 1.0))
    box_uv(bm, 1.0)
    mesh_obj("Crescent_Plinth", bm, "Granite")
    bm = bmesh.new()
    o = c + Vector((0, 0, 1.06 + 0.34))
    prism(bm, [o + Vector((0, 0, 1)) * x + Vector((-1, 0, 0)) * y for x, y in crescent_outline(0.34, 0.30, 0.16, 24)], Vector((0, 0.12, 0)))
    box_uv(bm, MARBLE_TILE)
    mesh_obj("Crescent_Sculpture", bm, "Column_Marble")
    bm = bmesh.new()
    add_box(bm, c + Vector((0, 0, 1.03)), (0.3, 0.2, 0.06))
    box_uv(bm, 1.0)
    mesh_obj("Crescent_Foot", bm, "Gold_Trim")


# the crescent sconces: (wall, the coordinate along it in world terms: y on E/W, x on N/S)
SCONCES = [("W", -3.7), ("W", -1.6), ("E", -3.7), ("E", -1.3), ("N", -1.5), ("N", 1.5)]
SCONCE_Z = 2.45


def sconce_points():
    out = []
    for wall, s in SCONCES:
        n, t, dist, L = wall_frame(wall)
        p = Vector((n.x * dist, s, 0)) if wall in ("E", "W") else Vector((s, n.y * dist, 0))
        out.append((wall, p, n, t))
    return out


def build_sconces():
    """Crescent sconces: a gilt wall plate, an arm out from the wall, a gilt crescent cup holding a frosted globe."""
    gold, bulbs = bmesh.new(), bmesh.new()
    up = Vector((0, 0, 1))
    for wall, w, n, t in sconce_points():
        plate = w - n * 0.012 + up * SCONCE_Z
        m = Matrix.Translation(plate) @ Matrix.Rotation(math.atan2(n.y, n.x), 4, "Z") @ Matrix.Diagonal((0.024, 0.10, 0.24, 1))
        bmesh.ops.create_cube(gold, size=1.0, matrix=m)
        tip = plate - n * 0.22 - up * 0.06
        add_cyl(gold, plate - n * 0.01 - up * 0.08, tip, 0.012, seg=8)
        o = tip + up * 0.07
        prism(gold, [o + up * x + t * y for x, y in crescent_outline(0.075, 0.066, 0.03, 12)], n * 0.014)
        bmesh.ops.create_uvsphere(bulbs, u_segments=12, v_segments=8, radius=0.055, matrix=Matrix.Translation(tip + up * 0.11))
    box_uv(gold, 1.0)
    mesh_obj("Sconces", gold, "Sconce_Gilt", smooth=True)
    box_uv(bulbs, 1.0)
    mesh_obj("Sconce_Bulbs", bulbs, "Lamp_Emit", smooth=True)


MIRROR_GLASS_Y = HALF_L - 0.165          # the pier mirror's mid-plane, where its panel was


def build_mirror_glass():
    """decor_mirror: the faint glass in the pier mirror's opening. No collider: the walker goes through it."""
    bm = bmesh.new()
    pts = [(-OPEN_A, 0.0)] + arch_pts(0.0, OPEN_A, OPEN_SPRING, OPEN_RISE, 20) + [(OPEN_A, 0.0)]
    f = poly(bm, [Vector((u, MIRROR_GLASS_Y, z)) for u, z in pts], Vector((0, -1, 0)), tri=False)
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp in f.loops:
        p = lp.vert.co
        lp[uvl].uv = (p.x / (2 * OPEN_A) + 0.5, p.z / (OPEN_SPRING + OPEN_RISE))
    bmesh.ops.triangulate(bm, faces=[f], ngon_method="EAR_CLIP")
    mesh_obj("decor_mirror", bm, "Mirror_Glass")


# ---------------------------------------------------------------- the furniture
def yaw_for(code, facing):
    return math.radians(COMPASS[facing] - NATIVE_FRONT[code])


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


def mirror_y(lo, hi):
    return (lo[0], REFL - hi[1], lo[2]), (hi[0], REFL - lo[1], hi[2])


def build_layout(placed):
    """COL_ boxes for the real room, then the reflection's as real mirrored boxes (COL_r_*, applied, invisible): its far wall is solid (the
    reflected way in is only a picture) and so is its east wall (the real door is reached through Zone_trigger_painted in front of it). The
    mirror's opening has none. Markers, links, zones and spots as PLAN 4.2."""
    T = 0.3
    real = []

    def box(name, lo, hi):
        real.append((name, lo, hi))

    box("COL_floor", (-HALF_W, -HALF_L, -0.2), (HALF_W, HALF_L, 0.0))
    box("COL_wall_W", (-HALF_W - T, -HALF_L, 0), (-HALF_W, HALF_L, WALL_H))
    box("COL_wall_E", (HALF_W, -HALF_L, 0), (HALF_W + T, HALF_L, WALL_H))
    box("COL_wall_S_a", (-HALF_W, -HALF_L - T, 0), (-DOOR_W / 2, -HALF_L, WALL_H))
    box("COL_wall_S_b", (DOOR_W / 2, -HALF_L - T, 0), (HALF_W, -HALF_L, WALL_H))
    box("COL_wall_S_head", (-DOOR_W / 2, -HALF_L - T, DOOR_H), (DOOR_W / 2, -HALF_L, WALL_H))
    box("COL_door_in", (-DOOR_W / 2, -HALF_L - T, 0), (DOOR_W / 2, -HALF_L, DOOR_H))          # the way in stays shut behind the walker
    for nm, ob in placed.items():
        if nm.startswith(("SE-00", "SE-08", "SE-09", "SE-10", "SE-12", "SE-11", "SE-06", "P19", "P3")):
            continue                                   # on the furniture, on the wall, or flat on the floor; the mirror frame is in the wall's boxes
        vs = world_verts(ob)
        box(f"COL_{nm}", tuple(min(v[i] for v in vs) for i in range(3)), tuple(max(v[i] for v in vs) for i in range(3)))
    for wall in ("W", "E"):
        n, t, dist, L = wall_frame(wall)
        for y in PILASTERS_Y:
            x0, x1 = sorted((n.x * dist, n.x * (dist - 0.24)))
            box(f"COL_pilaster_{wall}_{'s' if y < 0 else 'n'}{abs(y):.1f}".replace(".", "_"), (x0, y - 0.23, 0), (x1, y + 0.23, WALL_H))
    c = CRESCENT_PLINTH
    box("COL_crescent_plinth", (c.x - 0.28, c.y - 0.28, 0), (c.x + 0.28, c.y + 0.28, 1.75))
    for nm, lo, hi in real:
        col_box(nm, lo, hi)
        col_box(nm.replace("COL_", "COL_r_", 1), *mirror_y(lo, hi))
    # the mirror wall (y = 5.5, shared by both halves): boxes either side of the opening and over it, deep enough to hold both frames
    d = 0.36
    col_box("COL_wall_N_a", (-HALF_W, HALF_L - d, 0), (-OPEN_A, HALF_L + d, WALL_H))
    col_box("COL_wall_N_b", (OPEN_A, HALF_L - d, 0), (HALF_W, HALF_L + d, WALL_H))
    col_box("COL_wall_N_head", (-OPEN_A, HALF_L - d, OPEN_SPRING + OPEN_RISE), (OPEN_A, HALF_L + d, WALL_H))
    face_n = math.radians(180)                         # an Arrive_'s -Y axis is the way you face: yaw 180 faces +Y (north)
    empty("Marker_Spawn", (SPAWN.x, SPAWN.y, 0), "Spawn", yaw=face_n)
    empty("Marker_Entrance", (0, -HALF_L + 0.3, 0), "Entrance", yaw=face_n)
    empty("Marker_Exit", (HALF_W - 0.3, REAL_DOOR.y, 0), "Exit", yaw=math.radians(90))
    empty("Arrive_Selene_In", (SPAWN.x, SPAWN.y, 0), yaw=face_n, note="just inside the south door (from rdwe_god_nyx's star door)")
    empty("Link_Selene_Painted", (HALF_W - 0.35, REAL_DOOR.y, 0), to_scene="rdwe_god_hypnos", to_arrive="Arrive_Hypnos_In")
    empty("Spot_painted_door", (HALF_W - 0.35, PAINTED.y, 0), note="the painted door: flat paint, no knob to turn, no light under it")
    empty("Spot_mirror", (0, HALF_L - 0.6, 0), note="the pier mirror: decor_mirror is the glass; beyond it the reflection is real space, no teleport")
    col_box("Zone_trigger_mirror", (-OPEN_A, HALF_L - 0.2, 0), (OPEN_A, HALF_L + 0.2, OPEN_SPRING))
    col_box("Zone_trigger_painted", (HALF_W - 0.45, REAL_DOOR.y - DOOR_W / 2 + 0.05, 0), (HALF_W, REAL_DOOR.y + DOOR_W / 2 - 0.05, DOOR_H))
    col_box("Zone_reflection", (-HALF_W, HALF_L, 0), (HALF_W, REFL + HALF_L, VAULT_TOP))
    leaf_in = bpy.data.objects["DoorLeaf_Selene_In"]
    leaf_in["hinge"] = "west edge"
    leaf_in["swing_deg"] = 0
    leaf_in["state"] = "closed"
    leaf = bpy.data.objects["DoorLeaf_Selene_Painted"]
    leaf["hinge"] = "south edge"
    leaf["swing_deg"] = -90
    leaf["state"] = "closed; swings out (east) on the exit"


# ---------------------------------------------------------------- lights (for the bake and the stills; never exported)
SCONCE_W = 12.0          # each crescent sconce's globe (W)
PLACARD_W = 0.09         # the placard's picture light
LAMP_W = 10.0            # the crescent lamp on the north bedside table
MOON_W = 900.0           # the moonlight down the oculus, a spot on the rug
GLOW_W = 260.0           # the vault's cool glow: an area light under the crown pointing down, the even part of the light


def add_lights(coll_name="Lights", mirror=False):
    lights = bpy.data.collections.new(coll_name)
    bpy.context.scene.collection.children.link(lights)

    def M(p):
        p = Vector(p)
        return Vector((p.x, REFL - p.y, p.z)) if mirror else p

    def light(name, kind, loc, energy, color, size=0.05):
        d = bpy.data.lights.new(name, kind)
        d.energy, d.color = energy, color
        d.shadow_soft_size = size
        ob = bpy.data.objects.new(name, d)
        ob.location = M(loc)
        lights.objects.link(ob)
        return ob, d

    for i, (wall, w, n, t) in enumerate(sconce_points()):
        light(f"Sconce_{i}", "POINT", w - n * 0.232 + Vector((0, 0, SCONCE_Z + 0.05)), SCONCE_W, (1.0, 0.78, 0.52), 0.05)
    lamp = bpy.data.objects.get("SE-00_lamp")
    if lamp:
        vs = world_verts(lamp)
        z0 = min(v.z for v in vs)
        H = max(v.z for v in vs) - z0
        band = [v for v in vs if z0 + 0.72 * H < v.z < z0 + 0.95 * H]          # the crescent at the top
        c = sum(band, Vector()) / len(band) + Vector((0.1, 0, -0.02))
        light("Lamp_Bulb", "POINT", c, LAMP_W, (1.0, 0.72, 0.42), 0.03)
        if not mirror:
            bm = bmesh.new()
            bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.025, matrix=Matrix.Translation(c))
            box_uv(bm, 1.0)
            mesh_obj("Lamp_Glow", bm, "Lamp_Emit", smooth=True)
    pc = PLACARD_C + Vector((0, 0.16, 0.14 + 0.06 + 0.05 - 0.03))
    ob, d = light("Placard_Light", "AREA", pc, PLACARD_W, (1.0, 0.85, 0.65), 0.0)
    d.shape, d.size, d.size_y = "RECTANGLE", 0.28, 0.02
    ob.rotation_euler = (M(PLACARD_C - Vector((0, 0.012, 0))) - ob.location).to_track_quat("-Z", "Y").to_euler()
    ob, d = light("Moonlight", "SPOT", (0, 0, SKY_Z - 0.15), MOON_W, (0.70, 0.80, 1.0), 0.3)
    d.spot_size = math.radians(30)
    d.spot_blend = 0.5
    ob, d = light("Vault_Glow", "AREA", (0, 0, VAULT_TOP - 0.45), GLOW_W, (0.62, 0.72, 1.0), 0.0)
    d.shape, d.size, d.size_y = "RECTANGLE", 5.0, 9.0
    return lights


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("Night")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
    bg.inputs["Strength"].default_value = 0.0


CAMERA_ONLY = ("Mirror_Glass", "Moon_Shaft", "Moon_Pool", "Moon_Crescent", "Moon_Full", "Door_Glow", "Picture_Light_Emit")
NO_SHADOW = ("Lamp_Emit", "Sconce_Gilt") + CAMERA_ONLY


def ray_vis(o):
    """The glass, the moon's shafts and pools, the sky discs and the glows show to the camera only: they light and shade nothing in the bake."""
    m = o.data.materials[0].name if o.type == "MESH" and o.data.materials else ""
    if m in NO_SHADOW:
        o.visible_shadow = False
    if m in CAMERA_ONLY:
        o.visible_diffuse = o.visible_glossy = o.visible_transmission = False


def build_all():
    global ART, LAYOUT
    clear_scene()
    MATS.clear()
    ART = bpy.data.collections.new("Art")
    LAYOUT = bpy.data.collections.new("Layout")
    sc = bpy.context.scene
    sc.collection.children.link(ART)
    sc.collection.children.link(LAYOUT)
    gen = {"floor": mk_image("Selene_Floor", floor_pixels()), "granite": mk_image("Selene_Granite", granite_pixels()),
           "marble": mk_image("Selene_Marble", white_marble_pixels()), "plaster": mk_image("Selene_Plaster", plaster_pixels()),
           "coffer": mk_image("Selene_Coffer", coffer_pixels()), "placard": mk_image("Selene_Placard", placard_pixels()),
           "painted": mk_image("Selene_Painted_Door", painted_door_pixels()), "sky_crescent": mk_image("Selene_Sky_Crescent", sky_pixels(False)),
           "sky_full": mk_image("Selene_Sky_Full", sky_pixels(True))}
    make_materials(gen)
    build_shell()
    build_pilasters()
    build_floor_crescents()
    build_doors()
    build_placard()
    build_sconces()
    build_crescent_plinth()
    build_mirror_glass()
    build_moon()
    placed = place_all()
    build_layout(placed)
    add_lights()
    setup_world()
    sc.unit_settings.system = "METRIC"
    for o in ART.objects:
        ray_vis(o)


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    scrub_private()
    bpy.ops.wm.save_mainfile()


# ================================================================ bake (R1)
def furn(*codes):
    return tuple(f"Selene_{c}_" for c in codes)


GROUPS = [
    ("Floor_Marble", "Granite", "White_Marble", "Wall_Plaster", "Gold_Trim", "Door_White", "Painted_Door", "Reveal_Dark", "Placard"),  # 0 floor, walls, trim
    ("Vault_Coffers", "Column_Marble"),                                                                                                 # 1 vault, ribs, columns
    furn("SE-01", "SE-02", "SE-03", "SE-04", "SE-05", "SE-06", "SE-07", "SE-11"),                                                      # 2 the big furniture
    furn("SE-00", "SE-08", "SE-09", "SE-10", "SE-12", "P3", "P8", "P19"),                                                              # 3 the smalls and the props
]
MIN_DENSITY = [30, 26, 60, 60]          # px per metre wanted on each map (the search takes the smallest page that gives it)
PAGES = [None, None, None, None]        # auto; --pages a,b,c,d pins them
if arg("--pages"):
    PAGES = [None if v == "auto" else int(v) for v in arg("--pages").split(",")]
NOLM = ("Lamp_Emit", "Sconce_Gilt", "Picture_Light_Emit", "Door_Glow", "Mirror_Glass", "Moon_Shaft", "Moon_Pool", "Moon_Crescent", "Moon_Full")
KEEP_NODES = ("DoorLeaf_", "decor_")     # exported as their own nodes (the scene code moves, shows or hides them), not merged by material
# the reflection: these own nodes get no mirrored twin (each half has its own: the painted door and its real twin, the two moons)
NO_TWIN = ("decor_painted_door", "DoorLeaf_Selene_Painted", "decor_moon_", "decor_moonshaft_", "decor_moonpool_")
TWIN_NAME = {"DoorLeaf_Selene_In": "decor_refl_door_in", "decor_mirror": "decor_mirror_refl"}
MAIN = ("Floor_Marble", "Wall_Plaster", "White_Marble", "Vault_Coffers", "Column_Marble", "Selene_")   # held to a displayed p90 <= TARGET
NOT_MAIN = ("Selene_SE-00_lamp",)       # the lamp's own body, inches from its bulb: reported, not held
TARGET_P90 = arg("--target", 0.90, float)
CLIP_CAP = arg("--clip-cap", 0.98, float)     # and no main surface's p99 above this (0 turns the cap off)


def group_of(mname):
    for n, g in enumerate(GROUPS):
        if any(mname == x or (x.endswith("_") and mname.startswith(x)) for x in g):
            return n
    return None


def make_export_objects():
    art = bpy.data.collections["Art"]
    for cname in ("Export", "Reflection"):
        if cname in bpy.data.collections:
            for o in list(bpy.data.collections[cname].objects):
                bpy.data.objects.remove(o)
            bpy.data.collections.remove(bpy.data.collections[cname])
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
        ray_vis(ob)
    make_reflection(out)
    return out


def make_reflection(out):
    """The reflection: an empty `grp_reflection` at (0, 11, 0) with scale y = -1 (not applied), and under it a second object for each exported
    mesh, sharing that mesh (the glTF holds it once; three.js flips the winding of a negative-determinant node). The painted door, its real twin
    and the moons have no twin (each half has its own). The twins light and shade the bake but are never baked themselves (they share the
    real meshes' lightmap texels: the light is mirrored too)."""
    refl = bpy.data.collections.new("Reflection")
    bpy.context.scene.collection.children.link(refl)
    grp = bpy.data.objects.new("grp_reflection", None)
    grp.location = (0, REFL, 0)
    grp.scale = (1, -1, 1)
    refl.objects.link(grp)
    n = 0
    for name, ob in out.items():
        base = name[:-2]
        if base.startswith(NO_TWIN):
            continue
        tw = bpy.data.objects.new(TWIN_NAME.get(base, "refl_" + base), ob.data)
        refl.objects.link(tw)
        tw.parent = grp
        tw.matrix_parent_inverse = Matrix.Identity(4)
        tw.matrix_basis = ob.matrix_world.copy()
        for a in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission"):
            setattr(tw, a, getattr(ob, a))
        n += 1
    print(f"REFLECTION {n} mirrored nodes under grp_reflection")


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
    furn_objs = [o for o in objs if o.data.materials[0].name.startswith("Selene_")]
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
            if o.name.startswith("Selene_SE-01_"):
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


LIGHT_W = (("Sconce_", SCONCE_W), ("Lamp_Bulb", LAMP_W), ("Moonlight", MOON_W), ("Vault_Glow", GLOW_W), ("Placard_Light", PLACARD_W))


def all_lights():
    return [ob for c in ("Lights", "Lights_Refl") if c in bpy.data.collections for ob in bpy.data.collections[c].objects]


def reset_lights():
    """The lights at the constants' energies (the saved .blend holds them times the last bake's exposure), so a bake is the same from any start.
    The reflection's lights (Lights_Refl, mirrored copies of the room's) are made here if the scene has none."""
    if "Lights_Refl" not in bpy.data.collections:
        add_lights("Lights_Refl", mirror=True)
    for ob in all_lights():
        for prefix, w in LIGHT_W:
            if ob.name.startswith(prefix):
                ob.data.energy = w


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
        print(f"DISPLAYED {m:30s} map {d['map']}  p50 {d['p50']:.3f}  p90 {d['p90']:.3f}  p99 {d['p99']:.3f}  {'main' if d['main'] else ''}")
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


# ================================================================ export
def stage_export():
    exp = bpy.data.collections["Export"]
    refl = bpy.data.collections["Reflection"]
    exp.hide_viewport = exp.hide_render = False
    refl.hide_viewport = refl.hide_render = False
    bpy.data.collections["Art"].hide_viewport = True
    bpy.data.collections["Layout"].hide_viewport = True
    bpy.ops.object.select_all(action="DESELECT")
    objs = list(exp.objects)
    parked = []
    for o in objs + list(refl.objects):
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
    for o in refl.objects:
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


def stage_render():
    sc = bpy.context.scene
    STILLS.mkdir(parents=True, exist_ok=True)
    scrub_private()
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
    if "Reflection" in bpy.data.collections:
        bpy.data.collections["Reflection"].hide_render = False
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
    shots = {
        "1_arrival": (look_cam("arrival", (SPAWN.x, SPAWN.y, EYE), (0, SPAWN.y + 6, EYE + 0.9), 72.0), (1920, 1080), STILLS),
        "2_wide": (look_cam("wide", (3.3, -5.1, 3.6), (-1.0, 2.2, 0.8), 72.0), (1920, 1080), STILLS),
        "3_bedchamber": (look_cam("bed", (1.6, -1.6, EYE + 0.35), (-3.2, 2.4, 1.2), 66.0), (1920, 1080), STILLS),
        "4_mirror": (look_cam("mirror", (0.35, 2.6, EYE), (0.0, 8.0, EYE + 0.55), 66.0), (1920, 1080), STILLS),
        "refl_door": (look_cam("refl_door", (0.6, 11.0, EYE), (HALF_W, REAL_DOOR.y, 1.1), 66.0), (1280, 720), work()),
        "refl_moon": (look_cam("refl_moon", (0.0, 8.4, EYE), (0.0, REFL, SKY_Z), 72.0), (1280, 720), work()),
        "real_moon": (look_cam("real_moon", (0.0, -2.6, EYE), (0.0, 0.0, SKY_Z), 72.0), (1280, 720), work()),
        "painted": (look_cam("painted", (1.6, -2.5, EYE), (HALF_W, PAINTED.y, 1.1), 66.0), (1280, 720), work()),
        "plan": (look_cam("plan", (0, REFL / 2, 30), None, ortho=23.2), (560, 1500), work()),
    }
    shots["plan"][0].data.clip_start = 30 - 4.1             # cut away everything above 4.1 m: the vault, the lunettes, the cornice
    which = arg("--only", "all")
    for key, (cam, (w, h), folder) in shots.items():
        if which != "all" and key not in which.split(","):
            continue
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
