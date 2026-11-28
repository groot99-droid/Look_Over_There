"""Dresses and bakes the Overworld scenes on the greybox's layout (docs/BLENDER_AREAS.md, "4. The Overworld"; step 2, "Dress and light").

    python tools/blender/overworld_textures.py                                      (the textures, plain Python; once)
    blender -b --factory-startup --python tools/blender/dress_overworld.py -- --scene tree_house [--stage all] [--samples 512] [--render-samples 128]
    python tools/blender/pack_scene.py tree_house --work work/ow_tree_house                    (WebP: world/tree_house.glb and its AO map)

Scenes: tree_house, road, endless_hills. Every coordinate comes from tools/blender/build_overworld_greybox.py's model (imported here, never
retyped), so the colliders, doors, links, spots and edges stay exactly where the greybox put them: the run writes the layout through
tools/blender/export_scene.py to the work folder and fails unless it equals world/<scene>.json byte for byte.

Each greybox box that has art becomes one dressed object of the same name whose world box is the box (a trunk is a tapered cylinder that
touches its box's faces, a railing is posts and rails filling it, a hedge is a rounded box), so tools/blender/check_layout.py's rules hold;
the extra dressing (crowns, flowers, roofs, windows, kerbs, the hills' puzzle props) is named decor_ and is passable.

Stages (all by default, in one run): art (builds, saves blender/scenes/<scene>.blend, writes the layout and runs the layout check) -> bake
(merges by material into the Export collection, a shared second UV set, a Cycles AO bake, OIDN; work/ow_<scene>/<scene>_0.png) -> export
(work/ow_<scene>/<scene>_raw.glb) -> render (docs/renders/<scene>/1_arrival.jpg, 2_wide.jpg, 3_detail.jpg).

Light (docs/BLENDER.md R1, AO-only scenes): the Overworld is open air under the page's sun and four skies, so nothing is baked but ambient
occlusion: each baked material carries `aomap` (world/lightmaps/<scene>_0.webp, linear grey, on TEXCOORD_1) and `aomap_intensity`, and the
page keeps it lit. Lamp_Emit (the road's lamps, the tree house lantern) and Window_Lit (the tree house's and the facades' windows) are the
page's toggled materials. Coordinates: game (x, y, z) = Blender (x, -z, y).
"""
import json
import math
import os
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_overworld_greybox as GB      # noqa: E402  (the model: pure Python)
import export_scene                       # noqa: E402
import check_layout                       # noqa: E402

ROOT = HERE.parents[1]
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


SCENE = arg("--scene", "tree_house")
STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 512, int)
RSAMPLES = arg("--render-samples", 128, int)
TEX = ROOT / "blender/textures/overworld"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
WORK = ROOT / f"work/ow_{SCENE}"
STILLS = ROOT / f"docs/renders/{SCENE}"
AO_URL = f"world/lightmaps/{SCENE}_0.webp"
MARGIN_PX = 8
TARGET_PXM = {"tree_house": 24.0, "road": 10.0, "endless_hills": 9.0}.get(SCENE, 12.0)
AO_DIST = 2.5
S = GB.build(SCENE)
RNG = np.random.default_rng({"tree_house": 11, "road": 12, "endless_hills": 13}.get(SCENE, 1))


def G(p):
    return Vector((p[0], -p[2], p[1]))


def lin(c):
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


# ---------------------------------------------------------------- materials
# name: (texture or None, sRGB colour, tile in metres (one repeat), roughness, emission strength, AO-baked)
MAT = {
    "Grass": ("grass", (1, 1, 1), 4.0, 0.9, 0, True), "Hedge": ("hedge", (1, 1, 1), 2.0, 0.85, 0, True),
    "Bark": ("bark", (1, 1, 1), 2.0, 0.85, 0, True), "Deck": ("deck", (1, 1, 1), 2.0, 0.7, 0, True),
    "Siding": ("siding", (1, 1, 1), 1.5, 0.6, 0, True), "Shingles": ("shingles", (1, 1, 1), 2.0, 0.7, 0, True),
    "Asphalt": ("asphalt", (1, 1, 1), 4.0, 0.9, 0, True), "Concrete": ("concrete", (1, 1, 1), 2.0, 0.85, 0, True),
    "Plaster_Pink": ("plaster", (1, 1, 1), 3.0, 0.7, 0, True), "Plaster_Blue": ("plaster_blue", (1, 1, 1), 3.0, 0.7, 0, True),
    "Plaster_Yellow": ("plaster_yellow", (1, 1, 1), 3.0, 0.7, 0, True),
    "Leaf_Pink": ("leaf_pink", (1, 1, 1), 3.0, 0.55, 0, True), "Leaf_Mint": ("leaf_mint", (1, 1, 1), 3.0, 0.55, 0, True),
    "Leaf_Lilac": ("leaf_lilac", (1, 1, 1), 3.0, 0.55, 0, True),
    "Sign_Forest": ("sign_forest", (1, 1, 1), None, 0.6, 0, True), "Sign_Lot": ("sign_lot", (1, 1, 1), None, 0.6, 0, True),
    "Sign_Back": ("sign_back", (1, 1, 1), None, 0.6, 0, True), "More_To_Come": ("more_to_come", (1, 1, 1), None, 0.5, 0, True),
    "Fake_Door": ("fake_door", (1, 1, 1), None, 0.6, 0, True), "Puzzle_Board": ("puzzle_board", (1, 1, 1), None, 0.7, 0, True),
    "Door_Wood": ("door_wood", (1, 1, 1), 1.0, 0.6, 0, False),
    "Window_Lit": ("window_lit", (1, 1, 1), None, 0.2, 1.2, False), "Lamp_Emit": (None, (1.0, 0.94, 0.80), 1.0, 0.3, 4.0, False),
    "Gap_Glow": (None, (0.98, 0.80, 0.90), 1.0, 0.5, 1.1, False),
    "Steel": (None, (0.62, 0.66, 0.74), 1.0, 0.35, 0, True), "Paint_White": (None, (0.90, 0.90, 0.86), 1.0, 0.6, 0, True),
    "Line_Yellow": (None, (0.95, 0.82, 0.30), 1.0, 0.6, 0, True), "Trim_White": (None, (0.92, 0.90, 0.86), 1.0, 0.5, 0, True),
    "Stone": (None, (0.72, 0.68, 0.80), 1.0, 0.6, 0, True), "Mushroom_Cap": (None, (0.92, 0.42, 0.50), 1.0, 0.4, 0, True),
    "Mushroom_Stem": (None, (0.95, 0.90, 0.80), 1.0, 0.6, 0, True),
    "Flower_Pink": (None, (0.98, 0.60, 0.78), 1.0, 0.5, 0, False), "Flower_Yellow": (None, (0.98, 0.88, 0.42), 1.0, 0.5, 0, False),
    "Flower_White": (None, (0.94, 0.94, 0.92), 1.0, 0.5, 0, False), "Flower_Blue": (None, (0.60, 0.72, 0.98), 1.0, 0.5, 0, False),
    "Flower_Stem": (None, (0.36, 0.66, 0.34), 1.0, 0.7, 0, False),
}
_mats = {}


def material(name):
    if name in _mats:
        return _mats[name]
    tex, col, tile, rough, emit, _ao = MAT[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = rough
    c = (*lin(col), 1.0)
    bsdf.inputs["Base Color"].default_value = c
    img = None
    if tex:
        p = TEX / f"{tex}.jpg"
        img = bpy.data.images.load(str(p), check_existing=True)
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = img
        n.name = "BASE"
        nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
    if emit:
        key = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
        if img is not None:
            nt.links.new(nt.nodes["BASE"].outputs["Color"], bsdf.inputs[key])
        else:
            bsdf.inputs[key].default_value = c
        bsdf.inputs["Emission Strength"].default_value = emit
    m.diffuse_color = c
    _mats[name] = m
    return m


# ---------------------------------------------------------------- geometry, in game coordinates
class Geo:
    """Vertices and faces in game coordinates, one material per Geo; uv: 'box' (world-scale box projection) or 'fit' (each face's texture fits its box)."""

    def __init__(s):
        s.v, s.f = [], []
        s.smooth = []

    def add(s, verts, faces, smooth=False):
        b = len(s.v)
        s.v += [tuple(float(c) for c in p) for p in verts]
        s.f += [tuple(b + i for i in f) for f in faces]
        s.smooth += [smooth] * len(faces)
        return s


CUBE_F = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]


def box_v(mn, mx):
    return [(x, y, z) for x in (mn[0], mx[0]) for y in (mn[1], mx[1]) for z in (mn[2], mx[2])]


def gbox(g, mn, mx):
    # vertex index = 4*ix + 2*iy + iz
    return g.add(box_v(mn, mx), [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])


def gcyl(g, cx, cz, y0, y1, r0, r1, seg=12, cap=True, smooth=True, rings=None):
    """A tapered cylinder (or a profile of rings [(y, r)]) about the vertical through (cx, cz)."""
    rings = rings or [(y0, r0), (y1, r1)]
    verts, faces = [], []
    for y, r in rings:
        for k in range(seg):
            a = 2 * math.pi * k / seg
            verts.append((cx + r * math.cos(a), y, cz + r * math.sin(a)))
    for j in range(len(rings) - 1):
        for k in range(seg):
            a, b = j * seg + k, j * seg + (k + 1) % seg
            faces.append((a, b, b + seg, a + seg))
    g.add(verts, faces, smooth)
    if cap:
        base = len(g.v) - len(verts)
        g.add([], [])
        g.f.append(tuple(base + (seg - 1 - k) for k in range(seg)))
        g.f.append(tuple(base + (len(rings) - 1) * seg + k for k in range(seg)))
        g.smooth += [False, False]
    return g


def gsphere(g, c, r, sub=2):
    """An ellipsoid (r: (rx, ry, rz)) from an icosphere."""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0)
    verts = [(c[0] + v.co.x * r[0], c[1] + v.co.z * r[1], c[2] + v.co.y * r[2]) for v in bm.verts]
    faces = [tuple(v.index for v in f.verts) for f in bm.faces]
    bm.free()
    return g.add(verts, faces, True)


def gquad_y(g, x0, x1, z0, z1, y):
    return g.add([(x0, y, z0), (x0, y, z1), (x1, y, z1), (x1, y, z0)], [(0, 1, 2, 3)])


# ---------------------------------------------------------------- objects
ART, LAYOUT = None, None


def to_object(name, g, mat, uv="box", tile=None, bevel=0.0, coll=None, origin=None):
    tile = tile if tile is not None else (MAT[mat][2] or 1.0)
    bm = bmesh.new()
    vs = [bm.verts.new(G(p) - (origin or Vector())) for p in g.v]
    bm.verts.ensure_lookup_table()
    for f, sm in zip(g.f, g.smooth):
        try:
            face = bm.faces.new([vs[i] for i in f])
            face.smooth = sm
        except ValueError:
            pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if bevel > 0:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=2, affect="EDGES", clamp_overlap=True, profile=0.6)
    uvl = bm.loops.layers.uv.new("UVMap")
    lo = Vector((min(v.co.x for v in bm.verts), min(v.co.y for v in bm.verts), min(v.co.z for v in bm.verts)))
    hi = Vector((max(v.co.x for v in bm.verts), max(v.co.y for v in bm.verts), max(v.co.z for v in bm.verts)))
    d = hi - lo
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for l in f.loops:
            p = l.vert.co
            if uv == "fit":
                if ax == 0:
                    u = (p.y - lo.y) / max(d.y, 1e-6)
                    u = u if n.x > 0 else 1 - u
                    v = (p.z - lo.z) / max(d.z, 1e-6)
                elif ax == 1:
                    u = (p.x - lo.x) / max(d.x, 1e-6)
                    u = 1 - u if n.y > 0 else u
                    v = (p.z - lo.z) / max(d.z, 1e-6)
                else:
                    u, v = (p.x - lo.x) / max(d.x, 1e-6), (p.y - lo.y) / max(d.y, 1e-6)
            else:
                q = p + (origin or Vector())
                if ax == 0:
                    u, v = q.y / tile, q.z / tile
                elif ax == 1:
                    u, v = q.x / tile, q.z / tile
                else:
                    u, v = q.x / tile, q.y / tile
            l[uvl].uv = (u, v)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(material(mat))
    ob = bpy.data.objects.new(name, me)
    if origin is not None:
        ob.location = origin
    (coll or ART).objects.link(ob)
    return ob


def mn_mx(b):
    return b["min"], b["max"]


# ---------------------------------------------------------------- dressing one greybox box
def crown_mat(b):
    if b["mat"] == "leaf":
        return "Leaf_Mint"
    k = sum(map(ord, b["name"]))
    return ("Leaf_Pink", "Leaf_Lilac")[k % 2]


def blobs(b, mat, n=7):
    """A crown: soft blobs filling its box (decor: passable, overhead)."""
    mn, mx = mn_mx(b)
    c = [(mn[i] + mx[i]) / 2 for i in range(3)]
    h = [(mx[i] - mn[i]) / 2 for i in range(3)]
    ells = [(c, (h[0] * 0.78, h[1] * 1.15, h[2] * 0.78))]          # a little taller than its box: the stacked crowns join
    rng = np.random.default_rng(sum(map(ord, b["name"])))
    for k in range(n):
        a = 2 * math.pi * k / n + rng.uniform(-0.3, 0.3)
        rr = rng.uniform(0.35, 0.5)
        r = (h[0] * rr, min(h[1] * 1.1, h[0] * rr * 0.8), h[2] * rr)
        p = (c[0] + math.cos(a) * (h[0] - r[0]), c[1] + rng.uniform(-0.4, 0.4) * h[1], c[2] + math.sin(a) * (h[2] - r[2]))
        ells.append((p, r))
    g = Geo()
    for i, (p, r) in enumerate(ells):                              # a face wholly inside another blob is never seen: left out
        one = gsphere(Geo(), p, r, sub=3)
        inside = lambda q: any(sum(((q[a] - pc[a]) / rc[a]) ** 2 for a in range(3)) < 0.995 for j, (pc, rc) in enumerate(ells) if j != i)
        ins = [inside(q) for q in one.v]
        g.add(one.v, [f for f in one.f if not all(ins[k] for k in f)], True)
    to_object(b["name"], g, mat)


def trunk(b):
    mn, mx = mn_mx(b)
    cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
    R = min(mx[0] - mn[0], mx[2] - mn[2]) / 2
    h = mx[1] - mn[1]
    g = Geo()
    if b["name"] == "BigTree_Trunk":                                # thick up through the platform and the house, so the floor meets it
        rings = [(mn[1], R), (mn[1] + 0.5, R * 0.96), (6.8, R * 0.95), (mx[1], R * 0.75)]
    else:
        rings = [(mn[1], R), (mn[1] + 0.35, R * 0.82), (mn[1] + 0.9, R * 0.7), (mn[1] + h * 0.7, R * 0.6), (mx[1], R * 0.5)]
    gcyl(g, cx, cz, 0, 0, 0, 0, seg=24 if b["name"] == "BigTree_Trunk" else 14, rings=rings)
    to_object(b["name"], g, "Bark")


def railing(b, mat="Deck"):
    mn, mx = mn_mx(b)
    along = 0 if (mx[0] - mn[0]) >= (mx[2] - mn[2]) else 2
    L = mx[along] - mn[along]
    g = Geo()
    t = 0.06
    gbox(g, (mn[0], mx[1] - 0.08, mn[2]), (mx[0], mx[1], mx[2]))              # the top rail
    mid = [mn[0], mn[1] + 0.45, mn[2]]
    midx = [mx[0], mn[1] + 0.52, mx[2]]
    gbox(g, mid, midx)
    n = max(2, int(math.ceil(L / 1.1)) + 1)
    for k in range(n):
        a = mn[along] + (L - 2 * t) * k / (n - 1)
        lo, hi = list(mn), [mx[0], mx[1] - 0.08, mx[2]]
        lo[along], hi[along] = a, a + 2 * t
        gbox(g, lo, hi)
    to_object(b["name"], g, mat)


def bench_geo(b):
    mn, mx = mn_mx(b)
    g = Geo()
    along = 2 if (mx[2] - mn[2]) > (mx[0] - mn[0]) else 0
    cross = 2 - along
    for k in range(3):                                          # three slats
        lo, hi = list(mn), list(mx)
        w = (mx[cross] - mn[cross]) / 3
        lo[cross], hi[cross] = mn[cross] + k * w + 0.01, mn[cross] + (k + 1) * w - 0.01
        lo[1] = mx[1] - 0.06
        gbox(g, lo, hi)
    for e in (0, 1):                                            # two legs, the full depth
        lo, hi = list(mn), list(mx)
        if e == 0:
            hi[along] = mn[along] + 0.08
        else:
            lo[along] = mx[along] - 0.08
        hi[1] = mx[1] - 0.06
        gbox(g, lo, hi)
    to_object(b["name"], g, "Deck", bevel=0.01)


def post(b, mat="Deck"):
    mn, mx = mn_mx(b)
    cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
    R = min(mx[0] - mn[0], mx[2] - mn[2]) / 2
    g = Geo()
    gcyl(g, cx, cz, mn[1], mx[1], R, R * 0.9, seg=10)
    to_object(b["name"], g, mat)


def sign_mat(name):
    if SCENE == "endless_hills":
        return "Sign_Back"
    return "Sign_Forest" if "Forest" in name else "Sign_Lot"


FACADE_MATS = ["Plaster_Pink", "Plaster_Blue", "Plaster_Yellow"]


def lamp_head(b):
    mn, mx = mn_mx(b)
    cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
    r = (mx[0] - mn[0]) / 2
    g = Geo()
    gcyl(g, cx, cz, 0, 0, 0, 0, seg=16, rings=[(mn[1] + 0.04, r * 0.55), (mn[1] + 0.12, r), (mx[1] - 0.04, r * 0.7), (mx[1], r * 0.2)])
    to_object(b["name"], g, "Steel")
    gl = Geo()
    gcyl(gl, cx, cz, mn[1], mn[1] + 0.06, r * 0.5, r * 0.5, seg=16)
    to_object(b["name"].replace("decor_", "decor_Glow_"), gl, "Lamp_Emit")


def lantern(b):
    mn, mx = mn_mx(b)
    c = [(mn[i] + mx[i]) / 2 for i in range(3)]
    g = Geo()
    gsphere(g, c, ((mx[0] - mn[0]) * 0.42, (mx[1] - mn[1]) * 0.45, (mx[2] - mn[2]) * 0.45), sub=1)
    to_object(b["name"], g, "Lamp_Emit")
    f = Geo()
    gbox(f, (mn[0], mx[1] - 0.04, mn[2]), (mx[0], mx[1], mx[2]))
    gbox(f, (c[0] - 0.01, mx[1], c[2] - 0.01), (c[0] + 0.01, mx[1] + 0.3, c[2] + 0.01))
    to_object(b["name"].replace("decor_", "decor_Frame_"), f, "Steel")


def dress_box(b):
    n, m = b["name"], b["mat"]
    mn, mx = mn_mx(b)
    if n.startswith("Ground_"):
        g = Geo()
        x0, y0, z0 = mn
        x1, y1, z1 = mx
        g.add([(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y0, z0), (x0, y0, z1), (x1, y0, z1), (x1, y0, z0)],
              [(0, 1, 2, 3), (4, 0, 3, 7), (5, 6, 2, 1), (4, 5, 1, 0), (7, 3, 2, 6)])              # the top and a skirt, no bottom
        to_object(n, g, "Grass")
    elif m == "hedge":
        to_object(n, gbox(Geo(), mn, mx), "Hedge", bevel=min(0.35, (mx[0] - mn[0]) / 2.5, (mx[2] - mn[2]) / 2.5, (mx[1] - mn[1]) / 3))
    elif m == "bark":
        trunk(b)
    elif "Crown" in n:
        blobs(b, crown_mat(b))
    elif m == "timber":
        if "Rail" in n and not n.startswith("decor_"):
            railing(b)
        elif n.startswith("Bench_"):
            bench_geo(b)
        elif n.startswith("Signpost_") or n.startswith("Platform_Post"):
            post(b)
        elif n == "decor_Stair_Rail_N":
            pass                                                # replaced by decor_Stair_Handrails (extra_tree_house)
        elif n.startswith("House_Wall"):
            to_object(n, gbox(Geo(), mn, mx), "Siding", bevel=0.02)
        else:
            to_object(n, gbox(Geo(), mn, mx), "Deck", bevel=0.015)
    elif m == "roof":
        to_object(n, gbox(Geo(), mn, mx), "Deck", bevel=0.02)
    elif m == "sign":
        mat = "Puzzle_Board" if n.startswith("decor_Puzzle") else "More_To_Come" if "Facade" in n else sign_mat(n)
        to_object(n, gbox(Geo(), mn, mx), mat, uv="fit", bevel=0.01)
    elif m == "lamp":
        if "Gap_Glow" in n:
            to_object(n, gbox(Geo(), mn, mx), "Gap_Glow")
        elif "Lantern" in n:
            lantern(b)
        else:
            lamp_head(b)
    elif m == "steel":
        post(b, "Steel")
    elif m == "facade":
        k = int(n.split("_")[1]) if n.split("_")[1].isdigit() else 1
        to_object(n, gbox(Geo(), mn, mx), FACADE_MATS[(k - 1) % 3], bevel=0.05)
    elif m == "fake_door":
        to_object(n, gbox(Geo(), mn, mx), "Fake_Door", uv="fit")
    elif m == "window":
        to_object(n, gbox(Geo(), mn, mx), "Window_Lit", uv="fit")
    elif m == "asphalt":
        to_object(n, gbox(Geo(), mn, mx), "Asphalt")
    elif m == "line":
        dashes(b)
    elif m == "grass":
        to_object(n, gbox(Geo(), mn, mx), "Grass")
    else:
        to_object(n, gbox(Geo(), mn, mx), "Paint_White", bevel=0.01)


def dashes(b):
    mn, mx = mn_mx(b)
    g = Geo()
    z = mx[2] - 0.5
    while z - 3.0 > mn[2]:
        gbox(g, (mn[0], mn[1], z - 3.0), (mx[0], mx[1], z))
        z -= 9.0
    to_object(b["name"], g, "Line_Yellow")


# ---------------------------------------------------------------- the extra dressing (decor_, passable)
def flowers(name, pts, y_of=lambda x, z: 0.0, size=1.0):
    """Small flowers: a stem and a five-petal head each, one object per colour (decor_: you walk through them)."""
    cols = ["Flower_Pink", "Flower_Yellow", "Flower_White", "Flower_Blue"]
    heads = {c: Geo() for c in cols}
    stems = Geo()
    for i, (x, z) in enumerate(pts):
        y = y_of(x, z)
        h = float(RNG.uniform(0.12, 0.28)) * size
        r = float(RNG.uniform(0.05, 0.09)) * size
        c = cols[int(RNG.integers(0, 4))]
        a0 = float(RNG.uniform(0, 2 * math.pi))
        stems.add([(x - 0.008, y - 0.02, z), (x + 0.008, y - 0.02, z), (x, y + h, z)], [(0, 1, 2)])
        ring = [(x + r * math.cos(a0 + 2 * math.pi * k / 5), y + h + 0.01 * (k % 2), z + r * math.sin(a0 + 2 * math.pi * k / 5)) for k in range(5)]
        heads[c].add([(x, y + h + 0.015, z)] + ring, [(0, 1 + k, 1 + (k + 1) % 5) for k in range(5)])
    for c, g in heads.items():
        if g.f:
            to_object(f"decor_{name}_{c}", g, c)
    to_object(f"decor_{name}_Stems", stems, "Flower_Stem")


def scatter(n, x0, x1, z0, z1, keep_out=(), clump=6, spread=1.2):
    out = []
    while len(out) < n:
        cx, cz = RNG.uniform(x0, x1), RNG.uniform(z0, z1)
        for _ in range(clump):
            x, z = cx + RNG.normal(0, spread), cz + RNG.normal(0, spread)
            if x0 <= x <= x1 and z0 <= z <= z1 and not any(a <= x <= b and c <= z <= d for a, b, c, d in keep_out):
                out.append((float(x), float(z)))
    return out[:n]


def rect_keepouts(pad=0.4, below=3.0):
    """Every standing collider's floor plan, widened: the flowers keep off them."""
    return [(b["min"][0] - pad, b["max"][0] + pad, b["min"][2] - pad, b["max"][2] + pad) for b in S.boxes
            if b["col"] and b["min"][1] < below and b["max"][1] > 0.05 and not b["name"].startswith(("Ground_", "Edge_"))]


def extra_tree_house():
    y = 4.0
    # a gable roof over the house's ceiling slab, overhanging by 0.4 m (decor: overhead)
    x0, x1, z0, z1 = -4.0 - 0.6, 2.5 + 0.6, -4.0 - 0.6, 4.0 + 0.6
    yb = y + 2.6 + 0.2
    ridge = yb + 1.6
    g = Geo()
    zc = (z0 + z1) / 2
    g.add([(x0, yb, z0), (x1, yb, z0), (x1, ridge, zc), (x0, ridge, zc), (x0, yb, z1), (x1, yb, z1)],
          [(0, 1, 2, 3), (3, 2, 5, 4), (0, 3, 4), (1, 5, 2), (0, 4, 5, 1)])
    to_object("decor_House_Roof", g, "Shingles")
    gw = Geo()                                                   # the gable ends' boards, the trunk passes through the ridge
    gw.add([(x0 + 0.45, yb, z0 + 0.45), (x0 + 0.45, yb, z1 - 0.45), (x0 + 0.45, ridge - 0.3, zc)], [(0, 2, 1)])
    gw.add([(x1 - 0.45, yb, z0 + 0.45), (x1 - 0.45, yb, z1 - 0.45), (x1 - 0.45, ridge - 0.3, zc)], [(0, 1, 2)])
    to_object("decor_House_Gables", gw, "Siding")
    # windows on the house's outer faces (Window_Lit: the page lights them at night), with white frames
    T = GB.T
    wins = [("N", -2.6, -4.0 - T), ("N", 0.9, -4.0 - T), ("S", -2.6, 4.0 + T), ("S", 0.9, 4.0 + T), ("W", -1.6, -4.0 - T)]
    for k, (side, a, c) in enumerate(wins, 1):
        if side in "NS":
            out = -1 if side == "N" else 1
            lo, hi = (a - 0.5, y + 1.0, c + (0 if out > 0 else -0.03)), (a + 0.5, y + 2.0, c + (0.03 if out > 0 else 0))
            fl, fh = (a - 0.6, y + 0.9, c + (0 if out > 0 else -0.05)), (a + 0.6, y + 2.1, c + (0.05 if out > 0 else 0))
        else:
            lo, hi = (c - 0.03, y + 1.0, a - 0.5), (c, y + 2.0, a + 0.5)
            fl, fh = (c - 0.05, y + 0.9, a - 0.6), (c, y + 2.1, a + 0.6)
        to_object(f"decor_House_Window_{k}", gbox(Geo(), lo, hi), "Window_Lit", uv="fit")
        fr = Geo()
        gbox(fr, fl, (fh[0], fl[1] + 0.1, fh[2]))
        gbox(fr, (fl[0], fh[1] - 0.1, fl[2]), fh)
        to_object(f"decor_House_Window_{k}_Frame", fr, "Trim_White")
    # the platform's hole round the trunk is square, the trunk round: a deck collar fills the corners (decor; the trunk's collider is the square)
    col = Geo()
    seg, R, ri = 24, 1.4, 1.4 * 0.95
    for k in range(seg):
        pts = []
        for a in (2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg):
            ca, sa = math.cos(a), math.sin(a)
            t = R / max(abs(ca), abs(sa))
            pts.append(((ri * ca, ri * sa), (t * ca, t * sa)))
        (i0, o0), (i1, o1) = pts
        col.add([(i0[0], y, i0[1]), (o0[0], y, o0[1]), (o1[0], y, o1[1]), (i1[0], y, i1[1])], [(0, 3, 2, 1)])
        col.add([(i0[0], y - 0.2, i0[1]), (o0[0], y - 0.2, o0[1]), (o1[0], y - 0.2, o1[1]), (i1[0], y - 0.2, i1[1])], [(0, 1, 2, 3)])
    to_object("decor_Platform_Collar", col, "Deck")
    # handrails up both sides of the stairs (decor; the greybox's Stair_Rail_N is the north one's collider-free stand-in)
    hr = Geo()
    for z0 in (1.52, 3.42):
        for k in range(5):
            x = 10.6 - k * 1.15
            yb = max(0.0, (10.8 - x) / 0.3 * 0.25)
            gbox(hr, (x - 0.04, yb, z0), (x + 0.04, yb + 0.95, z0 + 0.06))
        x0, x1 = 10.8, 6.0
        hr.add([(x0, 0.95, z0), (x0, 1.01, z0), (x0, 1.01, z0 + 0.06), (x0, 0.95, z0 + 0.06),
                (x1, y + 0.95, z0), (x1, y + 1.01, z0), (x1, y + 1.01, z0 + 0.06), (x1, y + 0.95, z0 + 0.06)],
               [(0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    to_object("decor_Stair_Handrails", hr, "Deck")
    # stepping stones from the gap to the stairs, flowers and mushrooms in the glade
    st = Geo()
    for k in range(9):
        x = 20.0 - k * 1.15
        z = 1.2 + 0.5 * math.sin(k * 1.3)
        gcyl(st, x, z, 0.0, 0.04, 0.34, 0.3, seg=10, smooth=False)
    to_object("decor_Stepping_Stones", st, "Stone")
    keep = rect_keepouts() + [(10.0, 23.5, -3.0, 3.6), (-6.0, 7.0, -6.0, 6.0)]
    flowers("Glade_Flowers", scatter(900, -21.0, 21.0, -21.0, 21.0, keep_out=keep))
    caps, stems = Geo(), Geo()
    for (tx, tz) in ((-14.0, -14.0), (14.0, -15.0), (-15.0, 13.0), (12.0, 15.0)):
        for k in range(5):
            x, z = tx + RNG.uniform(-2.2, 2.2), tz + RNG.uniform(-2.2, 2.2)
            if abs(x - tx) < 0.9 and abs(z - tz) < 0.9:
                continue
            h = float(RNG.uniform(0.08, 0.18))
            gcyl(stems, x, z, 0.0, h, 0.03, 0.025, seg=6)
            gsphere(caps, (x, h, z), (0.09, 0.05, 0.09), sub=1)
    to_object("decor_Glade_Mushroom_Caps", caps, "Mushroom_Cap")
    to_object("decor_Glade_Mushroom_Stems", stems, "Mushroom_Stem")


def extra_road():
    L = GB.ROAD_L
    kb = Geo()                                                    # kerbs either side of the asphalt (decor: 8 cm)
    for x0, x1 in ((-4.25, -4.0), (4.0, 4.25)):
        gbox(kb, (x0, 0.0, -L), (x1, 0.08, 3.0))
    to_object("decor_Road_Kerbs", kb, "Concrete")
    ed = Geo()                                                    # the white edge lines
    for x0, x1 in ((-3.8, -3.68), (3.68, 3.8)):
        gbox(ed, (x0, 0.012, -L), (x1, 0.016, 3.0))
    to_object("decor_Road_Edge_Lines", ed, "Paint_White")
    keep = rect_keepouts() + [(-4.6, 4.6, -L - 3, 5.0)]
    for k in range(4):
        z0, z1 = -L * (k + 1) / 4, -L * k / 4
        flowers(f"Verge_Flowers_{k + 1}", scatter(700, -11.8, 11.8, z0, z1, keep_out=keep, clump=8, spread=0.9))


def extra_endless_hills():
    hy = GB.hill_h
    keep = rect_keepouts() + [(-2.0, 8.0, -8.0, 6.0)]
    for _, _w, x, z in GB.TOYS:
        keep.append((x - 2.0, x + 2.0, z - 2.0, z + 2.0))
    for _, _w, x, z in GB.PUZZLES:
        keep.append((x - 4.0, x + 4.0, z - 4.0, z + 4.0))
    for k in range(4):                                             # well inside the tile: nothing near an edge, so the seam stays clean
        q = [(-90, 0, -90, 0), (0, 90, -90, 0), (-90, 0, 0, 90), (0, 90, 0, 90)][k]
        flowers(f"Hill_Flowers_{k + 1}", scatter(2200, q[0], q[1], q[2], q[3], keep_out=keep, clump=45, spread=2.8), y_of=hy, size=1.5)
    # the four puzzles' props (decor: the page decides what they do)
    p = {k: (x, z) for k, _w, x, z in GB.PUZZLES}
    x, z = p[1]                                                    # stacking stones
    st = Geo()
    yb = hy(x, z)
    for k, r in enumerate((0.42, 0.34, 0.27, 0.2, 0.14)):
        gsphere(st, (x + 0.02 * k, yb + 0.12 + k * 0.2, z), (r, 0.11, r * 0.9), sub=2)
    for k, r in enumerate((0.3, 0.24, 0.18)):
        xx = x + 1.4 + 0.5 * k
        gsphere(st, (xx, hy(xx, z + 0.8) + 0.08, z + 0.8), (r, 0.09, r), sub=2)
    to_object("decor_Puzzle_Stones", st, "Stone")
    x, z = p[2]                                                    # a ring of mushrooms
    caps, stems = Geo(), Geo()
    for k in range(8):
        a = 2 * math.pi * k / 8
        mx_, mz = x + 2.4 * math.cos(a), z + 2.4 * math.sin(a)
        yy = hy(mx_, mz)
        h = 0.35 + 0.05 * (k % 3)
        gcyl(stems, mx_, mz, yy - 0.05, yy + h, 0.09, 0.07, seg=8)
        gsphere(caps, (mx_, yy + h, mz), (0.3, 0.16, 0.3), sub=2)
    to_object("decor_Puzzle_Mushroom_Caps", caps, "Mushroom_Cap")
    to_object("decor_Puzzle_Mushroom_Stems", stems, "Mushroom_Stem")
    x, z = p[3]                                                    # a door frame standing alone
    yy = min(hy(x - 0.6, z), hy(x + 0.6, z))
    fr = Geo()
    gbox(fr, (x - 0.65, yy - 0.2, z - 0.08), (x - 0.53, yy + 2.3, z + 0.08))
    gbox(fr, (x + 0.53, yy - 0.2, z - 0.08), (x + 0.65, yy + 2.3, z + 0.08))
    gbox(fr, (x - 0.65, yy + 2.18, z - 0.08), (x + 0.65, yy + 2.3, z + 0.08))
    to_object("decor_Puzzle_Door_Frame", fr, "Trim_White", bevel=0.01)
    x, z = p[4]                                                    # a hopscotch grid painted on the grass, following the ground
    hs = Geo()
    cells = [(0, 0), (0, 1), (0, 2), (-0.5, 3), (0.5, 3), (0, 4), (-0.5, 5), (0.5, 5)]
    for cx, r in cells:
        x0, z1 = x + cx * 0.8 - 0.4, z + 2.4 - r * 0.8
        z0 = z1 - 0.8
        for a0, a1, b0, b1 in ((x0, x0 + 0.8, z0, z0 + 0.05), (x0, x0 + 0.8, z1 - 0.05, z1), (x0, x0 + 0.05, z0, z1), (x0 + 0.75, x0 + 0.8, z0, z1)):
            yy = hy((a0 + a1) / 2, (b0 + b1) / 2) + 0.03
            gquad_y(hs, a0, a1, b0, b1, yy)
    to_object("decor_Puzzle_Hopscotch", hs, "Paint_White")


# ---------------------------------------------------------------- the layout (the greybox's names, exactly)
def build_layout():
    unit = bpy.data.meshes.new("COL_unit")
    unit.from_pydata([(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)], [], [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
    unit.update()

    def boxobj(name, b):
        ob = bpy.data.objects.new(name, unit)
        mn, mx = b["min"], b["max"]
        ob.location = (mn[0], -mx[2], mn[1])
        ob.scale = (mx[0] - mn[0], mx[2] - mn[2], mx[1] - mn[1])
        ob.display_type = "WIRE"
        ob.hide_render = True
        LAYOUT.objects.link(ob)
        return ob
    for b in S.boxes:
        if b.get("zone"):
            boxobj(b["name"], b)
        elif b["col"]:
            boxobj("COL_" + b["name"], b)
    for e in S.empties:
        ob = bpy.data.objects.new(e["name"], None)
        ob.location = G(e["pos"])
        if e["face"]:
            ob.rotation_euler = (0, 0, math.atan2(e["face"][0], e["face"][1]))
        for k, val in e["props"].items():
            ob[k] = val
        ob.empty_display_size = 0.3
        LAYOUT.objects.link(ob)
    for d in S.doors:                                             # the leaves: art the page swings, origin at the hinge
        w, h = d["props"]["width"], d["props"]["height"]
        g = Geo()
        gbox(g, (0.0, 0.0, -0.025), (w, h, 0.025))
        rails = Geo()
        for y0 in (0.25 * h, 0.7 * h):
            gbox(rails, (0.06, y0, 0.025), (w - 0.06, y0 + 0.1, 0.035))
        me_ob = to_object(d["name"], g, "Door_Wood", coll=ART, origin=None)
        tr = to_object(d["name"] + "_tmp", rails, "Door_Wood")
        # join the rails into the leaf, then move its origin to the hinge and turn it to its closed yaw
        bm = bmesh.new()
        bm.from_mesh(me_ob.data)
        bm.from_mesh(tr.data)
        bm.to_mesh(me_ob.data)
        bm.free()
        bpy.data.objects.remove(tr)
        me_ob.data.transform(Matrix.Rotation(d["yaw"], 4, "Z") @ Matrix.Translation(-Vector((0, 0, 0))))
        # the leaf was built in game coordinates about the hinge (0, 0, 0): its local +x runs from the hinge along it
        me_ob.location = G(d["hinge"])
        for k, val in d["props"].items():
            me_ob[k] = val


def build_art():
    for b in S.boxes:
        if b.get("zone") or b.get("ctx") or not b.get("art", True):
            continue
        dress_box(b)
    for m in S.meshes:                                              # the hills' surface (decor_Hills_Surface), the greybox's vertices
        g = Geo()
        g.add([tuple(v) for v in m["verts"]], [tuple(f) for f in m["faces"]], True)
        to_object(m["name"], g, "Grass")
    {"tree_house": extra_tree_house, "road": extra_road, "endless_hills": extra_endless_hills}[SCENE]()


def setup_world():
    sc = bpy.context.scene
    w = bpy.data.worlds.new("Sky")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
    # a soft sky: pale at the horizon, a clear pastel blue overhead (the clear-day sky; the page draws the real backdrops)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (*lin((0.93, 0.90, 0.96)), 1)
    ramp.color_ramp.elements[1].position = 0.45
    ramp.color_ramp.elements[1].color = (*lin((0.52, 0.72, 0.98)), 1)
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], ramp.inputs[0])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    w.light_settings.distance = AO_DIST
    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 3.2
    sun.angle = math.radians(2.0)
    sun.color = (1.0, 0.96, 0.90)
    so = bpy.data.objects.new("Sun", sun)
    so.rotation_euler = (math.radians(42), math.radians(8), math.radians(35))
    sc.collection.objects.link(so)


def no_stamps(sc):
    for p in sc.render.bl_rna.properties:
        if p.identifier.startswith("use_stamp") and not p.is_readonly:
            setattr(sc.render, p.identifier, False)
    sc.render.stamp_note_text = ""


def setup_cycles(samples, bake=False):
    sc = bpy.context.scene
    no_stamps(sc)
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = samples
    cy.use_adaptive_sampling = not bake
    cy.use_denoising = not bake
    prefs = bpy.context.preferences.addons["cycles"].preferences
    gpu = False
    for t in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = t
            prefs.refresh_devices()
        except Exception:
            continue
        if [d for d in prefs.devices if d.type != "CPU"]:
            for d in prefs.devices:
                d.use = d.type != "CPU"
            gpu = True
            break
    cy.device = "GPU" if gpu else "CPU"
    print("CYCLES device:", cy.device)
    return gpu


# ---------------------------------------------------------------- privacy and saving
def scrub():
    """The .blend, the GLB (export_extras) and the stills are public: only the materials' aomap extras, the doors', spots' and links'
    own properties go out; no add-on state, no render path, no stamp; every image path relative."""
    keep_mat = ("aomap", "aomap_intensity", "aomap_colorspace")
    for kind in ("scenes", "worlds", "collections", "cameras", "lights", "images", "node_groups", "screens", "window_managers", "workspaces", "meshes"):
        for idb in getattr(bpy.data, kind):
            stores = [idb]
            sg = getattr(idb, "bl_system_properties_get", None)
            if sg:
                s = sg()
                if s is not None:
                    stores.append(s)
            for st in stores:
                for k in list(st.keys()):
                    if st is not idb and k.startswith(("cycles", "eevee")):
                        continue
                    try:
                        del st[k]
                    except Exception:
                        pass
    for m in bpy.data.materials:
        for k in [k for k in m.keys() if k not in keep_mat]:
            del m[k]
    for sc in bpy.data.scenes:
        sc.render.filepath = "//"
        no_stamps(sc)


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    scrub()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), relative_remap=True, compress=True)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile(compress=True)


# ---------------------------------------------------------------- gates run in Blender
def gate_layout():
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / f"{SCENE}_layout.json"
    export_scene.write(SCENE, out)
    same = out.read_text().replace(chr(13), "") == (ROOT / f"world/{SCENE}.json").read_text().replace(chr(13), "")   # a Windows checkout has CRLF
    print(f"GATE export: world/{SCENE}.json from the dressed .blend {'EQUALS' if same else 'DIFFERS FROM'} the greybox's")
    world = json.loads(out.read_text())
    parts = check_layout.blender_parts("Art")
    cols = world["colliders"]
    note = ""
    if SCENE == "endless_hills":
        # The 2500 collision columns sit under one passable surface (decor_Hills_Surface, the greybox's): the surface's vertex at each
        # column's centre must be the column's top. The other colliders take check_layout's rules.
        surf = bpy.data.objects["decor_Hills_Surface"]
        hz = {(round(v.co.x, 3), round(-v.co.y, 3)): v.co.z for v in surf.data.vertices}
        worst = 0.0
        n = 0
        for c in cols:
            if c["s"].startswith("Ground_Hills_"):
                cx, cz = round((c["min"][0] + c["max"][0]) / 2, 3), round((c["min"][2] + c["max"][2]) / 2, 3)
                worst = max(worst, abs(hz[(cx, cz)] - c["max"][1]))
                n += 1
        ok = worst <= 0.005
        print(f"{'PASS' if ok else 'FAIL'}  HILLS  {n} Ground_Hills_ columns: the surface at each column's centre is its top within {worst * 1000:.1f} mm")
        world = dict(world, colliders=[c for c in cols if not c["s"].startswith("Ground_Hills_")])
        note = " (the hills' columns by the HILLS rule above)"
    consts = {"links": {l["door"]: {"arrive": l["arrive"], "at": [l["at"][0], l["at"][2]]} for l in world["links"]}}
    res = check_layout.check(parts, world, consts)
    bad = check_layout.report(res)
    print(f"GATE layout check{note}: {'PASS' if not bad else 'FAIL'}")
    return same and not bad


# ---------------------------------------------------------------- bake
def make_export_objects():
    if "Export" in bpy.data.collections:
        for o in list(bpy.data.collections["Export"].objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(bpy.data.collections["Export"])
    exp = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(exp)
    by_mat = {}
    for ob in ART.objects:
        if ob.type != "MESH" or ob.name.startswith("DoorLeaf_"):
            continue
        mname = ob.data.materials[0].name
        bm = by_mat.setdefault(mname, bmesh.new())
        me = ob.data.copy()
        me.transform(ob.matrix_world)
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    out = {}
    for mname, bm in by_mat.items():
        me = bpy.data.meshes.new("X_" + mname)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(bpy.data.materials[mname])
        ob = bpy.data.objects.new(mname, me)
        exp.objects.link(ob)
        out[mname] = ob
    for ob in ART.objects:                                       # the door leaves go out as themselves (the page swings them)
        if ob.name.startswith("DoorLeaf_"):
            c = ob.copy()
            c.data = ob.data.copy()
            exp.objects.link(c)
            out[ob.name] = c
    return out


def select_only(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def uv_area(ob):
    uv = ob.data.uv_layers["lightmap"].data
    tot = 0.0
    for p in ob.data.polygons:
        pts = [uv[i].uv for i in p.loop_indices]
        n = len(pts)
        tot += abs(sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))) / 2
    return tot


def chop(ob, step=40.0, longest=60.0):
    """Cut a merged mesh that runs longer than `longest` into `step`-metre pieces (split along the cuts), so its AO islands fit the page:
    a 480 m road verge is one island otherwise, and no page holds it at the outdoor texel density. Flat faces only meet at the cuts."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    for axis in (0, 1):
        co = [v.co[axis] for v in bm.verts]
        if not co or max(co) - min(co) <= longest:
            continue
        k = math.floor(min(co) / step) + 1
        while k * step < max(co):
            n = Vector((0, 0, 0))
            n[axis] = 1.0
            res = bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces), plane_co=n * (k * step), plane_no=n)
            cut = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
            if cut:
                bmesh.ops.split_edges(bm, edges=cut)
            k += 1
    bm.to_mesh(ob.data)
    bm.free()


def lightmap_uv(objs):
    for o in objs:
        uvs = o.data.uv_layers
        uvs.new(name="lightmap")
        uvs.active = uvs["lightmap"]
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode="OBJECT")
    a3 = sum(sum(p.area for p in o.data.polygons) for o in objs)

    def pack(Sz):
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / Sz, shape_method="CONCAVE")
        bpy.ops.object.mode_set(mode="OBJECT")
        d = Sz * math.sqrt(sum(uv_area(o) for o in objs) / a3)
        print(f"  page {Sz}: {a3:.0f} m2, {d:.1f} px/m")
        return d
    sizes = (512, 1024, 1536, 2048)
    d = pack(1024)
    Sz = next((s for s in sizes if d * s / 1024 >= TARGET_PXM), 2048)
    dens = pack(Sz) if Sz != 1024 else d
    for o in objs:
        o.data.uv_layers["UVMap"].active_render = True
    return Sz, dens


def denoise_image(img, Sz):
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
    sc.render.resolution_x = sc.render.resolution_y = Sz
    sc.render.resolution_percentage = 100
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 1
    no_stamps(sc)
    sc.render.image_settings.file_format = "OPEN_EXR"
    sc.render.image_settings.color_depth = "32"
    cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    path = str(WORK / "dn.exr")
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=sc.name)
    r = bpy.data.images.load(path)
    a = np.empty(Sz * Sz * 4, np.float32)
    r.pixels.foreach_get(a)
    bpy.data.images.remove(r)
    bpy.data.objects.remove(cam)
    bpy.data.scenes.remove(sc)
    bpy.data.node_groups.remove(ng)
    os.remove(path)
    return a.reshape(Sz, Sz, 4)


GROUND_PAGE = {"road": ("Grass", "Asphalt"), "endless_hills": ("Grass",)}       # scenes whose ground gets an AO page of its own (the rest share the other page)


def stage_bake():
    import time
    t0 = time.time()
    WORK.mkdir(parents=True, exist_ok=True)
    exp = make_export_objects()
    ART.hide_render = True
    setup_cycles(SAMPLES, bake=True)
    objs = [o for n, o in exp.items() if n in MAT and MAT[n][5]]
    if SCENE == "road":
        for o in objs:
            chop(o)
    g0 = GROUND_PAGE.get(SCENE)
    groups = [[o for o in objs if o.name in g0], [o for o in objs if o.name not in g0]] if g0 else [objs]
    pages = []
    for objs_g in groups:                                          # every page unwrapped first (the unwrap works on the selection)
        print("AO page", len(pages), [o.name for o in objs_g])
        pages.append(lightmap_uv(objs_g))
    reps = []
    for n, objs_g in enumerate(groups):
        Sz, dens = pages[n]
        img = bpy.data.images.new(f"AO_{n}", Sz, Sz, alpha=False, float_buffer=True)
        img.colorspace_settings.name = "Non-Color"
        for o in objs_g:
            nt = o.data.materials[0].node_tree
            node = nt.nodes.new("ShaderNodeTexImage")
            node.name = "BAKE_TARGET"
            node.image = img
            nt.nodes.active = node
            o.data.uv_layers.active = o.data.uv_layers["lightmap"]
        select_only(objs_g)
        tb = time.time()
        bpy.ops.object.bake(type="AO", margin=MARGIN_PX, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
        print(f"  AO bake {n}: {Sz}x{Sz} at {SAMPLES} samples took {time.time() - tb:.0f} s")
        a = denoise_image(img, Sz)
        ao = np.clip(a[..., :3].mean(axis=2), 0, 1)
        used = ao > 1e-3                                          # the atlas's empty space stays 0
        pc = [round(float(v), 3) for v in np.percentile(ao[used], [1, 10, 50, 90])]
        out = np.ones((Sz, Sz, 4), np.float32)
        out[..., 0] = out[..., 1] = out[..., 2] = ao                # linear grey: three.js reads aoMap's red channel as data
        png = bpy.data.images.new("AO_png", Sz, Sz, alpha=False)
        png.colorspace_settings.name = "Non-Color"
        png.pixels.foreach_set(out.ravel())
        png.filepath_raw = str(WORK / f"{SCENE}_{n}.png")
        png.file_format = "PNG"
        png.save()
        for o in objs_g:
            m = o.data.materials[0]
            m["aomap"] = f"world/lightmaps/{SCENE}_{n}.webp"
            m["aomap_intensity"] = 1.0
            m["aomap_colorspace"] = "linear"
            nt = m.node_tree
            for nd in [nd for nd in nt.nodes if nd.name.startswith("BAKE_TARGET")]:
                nt.nodes.remove(nd)
        bpy.data.images.remove(img)
        bpy.data.images.remove(png)
        reps.append({"page": n, "size": Sz, "px_per_m": round(dens, 1), "ao_p1_p10_p50_p90": pc, "materials": sorted(o.name for o in objs_g)})
    rep = {"samples": SAMPLES, "ao_distance_m": AO_DIST, "pages": reps, "seconds": round(time.time() - t0), "device": bpy.context.scene.cycles.device}
    print("BAKE", rep)
    (WORK / "bake.json").write_text(json.dumps(rep, indent=1))
    ART.hide_render = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True


def stage_export():
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    ART.hide_viewport = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in exp.objects:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = WORK / f"{SCENE}_raw.glb"
    scrub()
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False, export_animations=False)
    print("EXPORTED", raw.name, raw.stat().st_size)
    ART.hide_viewport = False
    exp.hide_viewport = exp.hide_render = True


# ---------------------------------------------------------------- the review stills
def strip_jpeg_meta(path):
    b = Path(path).read_bytes()
    out, i = bytearray(b[:2]), 2
    while i < len(b):
        m = b[i + 1]
        if m == 0xDA:
            out += b[i:]
            break
        n = int.from_bytes(b[i + 2:i + 4], "big")
        if not (m == 0xFE or 0xE1 <= m <= 0xEF):
            out += b[i:i + 2 + n]
        i += 2 + n
    Path(path).write_bytes(bytes(out))


def look_cam(name, loc, target, fov_v=60.0):
    cam = bpy.data.cameras.new(name)
    cam.sensor_fit = "VERTICAL"
    cam.lens_unit = "FOV"
    cam.angle_y = math.radians(fov_v)
    cam.clip_start, cam.clip_end = 0.05, 1200
    ob = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = G(loc)
    ob.rotation_euler = (G(target) - G(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


def shots():
    L = {l["door"]: l for l in json.loads((ROOT / f"world/{SCENE}.json").read_text())["links"]}
    if SCENE == "tree_house":
        a = L["playground"]
        return {"1_arrival": ((a["arrive"][0], 1.6, a["arrive"][2]), (a["arrive"][0] + a["face"][0] * 5, 2.6, a["arrive"][2] + a["face"][1] * 5), 70),
                "2_wide": ((24.0, 9.0, 22.0), (0.0, 4.5, 0.0), 55), "3_detail": ((1.9, 5.55, 2.9), (-3.9, 5.25, 2.6), 62)}
    if SCENE == "road":
        a = L["lot"]
        return {"1_arrival": ((a["arrive"][0], 1.6, a["arrive"][2]), (0.0, 1.4, -60.0), 65),
                "2_wide": ((11.0, 14.0, -180.0), (-2.0, 0.0, -300.0), 60), "3_detail": ((2.0, 1.6, -GB.ROAD_L + 16.0), (0.0, 3.0, -GB.ROAD_L), 60)}
    a = L["lot"]
    y0 = a["arrive"][1]
    px, pz = GB.PUZZLES[1][2], GB.PUZZLES[1][3]
    return {"1_arrival": ((a["arrive"][0], y0 + 1.6, a["arrive"][2]), (a["arrive"][0] + a["face"][0] * 10, y0 + 1.2, a["arrive"][2] + a["face"][1] * 10), 65),
            "2_wide": ((40.0, 24.0, 60.0), (-20.0, 0.0, -10.0), 60),
            "3_detail": ((px + 5.0, GB.hill_h(px + 5, pz + 4) + 1.7, pz + 4.0), (px, GB.hill_h(px, pz) + 0.2, pz), 55)}


def stage_render():
    import time
    sc = bpy.context.scene
    STILLS.mkdir(parents=True, exist_ok=True)
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
    setup_cycles(RSAMPLES)
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.adaptive_threshold = 0.02
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "None"
    for k, (x, y, z, pw) in enumerate(S.lights):                     # the greybox's room lights, for the stills only (the page lights the room)
        lt = bpy.data.lights.new(f"Still_Light_{k}", "POINT")
        lt.energy = pw
        lt.shadow_soft_size = 0.3
        lo = bpy.data.objects.new(f"Still_Light_{k}", lt)
        lo.location = G((x, y, z))
        sc.collection.objects.link(lo)
    for key, (loc, tgt, fov) in shots().items():
        sc.camera = look_cam(key, loc, tgt, fov)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 1080, 100
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        path = STILLS / f"{key}.jpg"
        sc.render.filepath = str(path)
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 400_000 and q > 40:
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        strip_jpeg_meta(path)
        print("STILL", key, path.stat().st_size, "q", q, f"{time.time() - t0:.0f} s")
        bpy.data.objects.remove(sc.camera)
    for o in [o for o in bpy.data.objects if o.name.startswith("Still_Light_")]:
        bpy.data.objects.remove(o)
    sc.render.filepath = "//"


def collections():
    global ART, LAYOUT
    sc = bpy.context.scene
    for cn in ("Art", "Layout"):
        if cn not in bpy.data.collections:
            c = bpy.data.collections.new(cn)
            sc.collection.children.link(c)
    ART, LAYOUT = bpy.data.collections["Art"], bpy.data.collections["Layout"]


if __name__ == "__main__":
    if STAGE in ("art", "all"):
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        collections()
        build_layout()
        build_art()
        setup_world()
        bpy.context.view_layer.update()
        save_blend()
        ok = gate_layout()
        print("GATES_IN_BLENDER", "PASS" if ok else "FAIL")
    else:
        collections()
    if STAGE in ("bake", "all"):
        stage_bake()
        save_blend()
    if STAGE in ("export", "all"):
        stage_export()
    if STAGE in ("render", "all"):
        stage_render()
        save_blend()
    print("DRESS_OVERWORLD DONE", SCENE, STAGE)
