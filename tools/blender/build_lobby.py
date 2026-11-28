"""Dresses and lights the hotel lobby (`lobby`, docs/BLENDER_AREAS.md section 1) in Blender, bakes a day set and a night set, and exports world/lobby.glb
and world/lobby.json.

Re-runnable, from the repo root:

    blender -b --python tools/blender/build_lobby.py -- --stage art          (build the art and the layout objects, save blender/scenes/lobby.blend)
    blender -b blender/scenes/lobby.blend --python tools/blender/build_lobby.py -- --stage layout   (world/lobby.json through export_scene.py)
    blender -b blender/scenes/lobby.blend --python tools/blender/build_lobby.py -- --stage check    (tools/blender/check_layout.py on the Art collection)
    blender -b blender/scenes/lobby.blend --python tools/blender/build_lobby.py -- --stage bake [--samples 512] [--night-samples 768]
    blender -b blender/scenes/lobby.blend --python tools/blender/build_lobby.py -- --stage export
    blender -b blender/scenes/lobby.blend --python tools/blender/build_lobby.py -- --stage axes     (the marker-cube axes check)
    blender -b blender/scenes/lobby.blend --python tools/blender/build_lobby.py -- --stage render [--render-samples 128] [--only 1_arrival] [--set night]
    python tools/blender/pack_scene.py lobby --work work/lobby                                     (WebP lightmaps and textures -> world/)

The layout is the greybox's: tools/blender/build_hotel_greybox.py `lobby()` (imported here, no coordinate copied by hand) gives every collider, door,
link, marker and spot; this build puts the art round them and writes the same names (COL_, DoorLeaf_, Link_/Arrive_, Marker_, Spot_) into the .blend,
so tools/blender/export_scene.py writes the same world/lobby.json as the greybox model does (`build_hotel_greybox.py --preview`).

The look: a peaceful, liminal old hotel lobby. Patterned carpet, dark wood panelling to 2.4 m with sage damask paper above, a coffered plaster ceiling,
brass, a tired chandelier (two bulbs dead), house plants, frosted windows to the street with velvet drapes, a reception desk with the key board and
three clocks, a deli under the loft, two shops (news and books; gifts and sundries) and three facade doors that do not open.
Light: day = the sun and the sky through the east (street) windows plus the warm lamps; night = the lamps and the sodium glow of the street.
Both sets bake to the same lightmap UVs: `lightmap` (day) and `lightmap_night` (night), as the mall entrance does. `Lamp_Emit` (every lamp's
glow) is on in both sets. The page draws the dealers, the receptionist and every moving part; their spots stay clear.
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import build_hotel_greybox as G          # noqa: E402  the layout model (pure Python)

SCENE = "lobby"
TEX = ROOT / f"blender/textures/{SCENE}"
MODELS = ROOT / f"blender/models/{SCENE}"
CHANDELIER = ROOT / "blender/models/galleries/ph-chandelier-02/Chandelier_02_1k.gltf"     # Poly Haven, CC0 (already in the repo for the galleries)
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"
MARGIN_PX = 8

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 512, int)
NIGHT_SAMPLES = arg("--night-samples", None, int) or SAMPLES
DEVICE = arg("--device", "auto")

GB = G.lobby()
BOX = {b["name"]: b for b in GB.boxes}
FL = BOX["Lobby_Floor"]
X0, X1 = FL["min"][0] + G.T, FL["max"][0] - G.T
Z0, Z1 = FL["min"][2] + G.T, FL["max"][2] - G.T
H = BOX["Lobby_Ceiling"]["min"][1]
T = G.T
BAND = 2.4                                   # the panelling's top (the dado rail)
LOFT = BOX["Loft_Slab"]                      # x -27.8..-21, z -22..-8.2, y 2.75..3.0
LX1, LZ0 = LOFT["max"][0], LOFT["min"][2]
LOFT_Y0, LOFT_Y = LOFT["min"][1], LOFT["max"][1]
WIN_Y = (1.0, 4.4)                           # the street windows (east wall): sill and head
WIN_Z = [(-28.4, -26.2), (-25.0, -22.8), (-15.2, -13.0), (-11.8, -9.6)]
FRONT = [d for d in GB.doors if d["name"].startswith("DoorLeaf_front")]
FD_Z0 = min(d["hinge"][2] for d in FRONT)
FD_Z1 = max(d["hinge"][2] for d in FRONT)
FD_H = FRONT[0]["props"]["height"]
TRANSOM = (FD_Z0, FD_Z1, FD_H + 0.22, WIN_Y[1])
BACK = next(d for d in GB.doors if d["name"] == "DoorLeaf_back_hall")
BD_Z0, BD_H = BACK["hinge"][2], BACK["props"]["height"]
BD_Z1 = BD_Z0 + BACK["props"]["width"]
ARRIVE = next(e for e in GB.empties if e["name"] == "Arrive_street")
SPAWN = ARRIVE["pos"]
FACE = ARRIVE["face"]
CHAND = (-15.0, -19.0)
STAIR_X0, STAIR_X1 = BOX["Step_loft_00"]["min"][0], BOX["Step_loft_00"]["max"][0]                       # over the planter, in the middle coffer


def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


# ---------------------------------------------------------------- materials
IMG_CACHE, MATS, TILES = {}, {}, {}


def image(fn, srgb=True):
    key = (fn, srgb)
    if key not in IMG_CACHE:
        p = ROOT / fn if "/" in fn else TEX / fn
        im = bpy.data.images.load(str(p))
        im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
        IMG_CACHE[key] = im
    return IMG_CACHE[key]


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, diff=None, img=None, tint=None, emit=None, alpha=None, tile=None, two_sided=False):
    """A Principled material. `tint` multiplies the diffuse texture (a Mix node set to Multiply, written by the glTF exporter as baseColorFactor)."""
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
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    if diff or img is not None:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = img if img is not None else image(diff, True)
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        if tint:
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs[0].default_value = 1.0
            nt.links.new(n.outputs["Color"], mix.inputs[6])
            mix.inputs[7].default_value = (*tint, 1)
            nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        else:
            nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    if alpha is not None:
        bsdf.inputs["Alpha"].default_value = alpha
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    m.use_backface_culling = not two_sided
    TILES[name] = tile or 1.0
    MATS[name] = m
    return m


LAMP_EMIT = 6.0           # Lamp_Emit's exported strength: every lamp's glow (bulbs, shades, lenses); on in both light sets


def make_materials(gen):
    material("Floor_Carpet", img=gen["carpet"], rough=1.0, tile=2.4)
    material("Floor_Marble", diff="marble_01_diff_1k.jpg", tint=(0.92, 0.90, 0.86), rough=0.3, tile=1.4)
    material("Floor_Tile", img=gen["tile"], rough=0.4, tile=0.6)
    material("Floor_Parquet", diff="herringbone_parquet_diff_1k.jpg", tint=(0.80, 0.68, 0.56), rough=0.5, tile=1.6)
    material("Wall_Panel", img=gen["wood"], rough=0.5, tile=1.4)
    material("Wall_Paper", img=gen["paper"], rough=0.9, tile=0.9)
    material("Ceiling_Plaster", diff="plastered_wall_04_diff_1k.jpg", tint=(0.93, 0.90, 0.84), rough=0.95, tile=2.5)
    material("Trim_Wood", img=gen["wood"], tint=(0.72, 0.70, 0.68), rough=0.45, tile=0.9)
    material("Trim_Paint", color=(0.78, 0.74, 0.64), rough=0.7)
    material("Wood_Furniture", img=gen["wood"], tint=(0.80, 0.74, 0.70), rough=0.45, tile=0.8)
    material("Marble_Top", diff="marble_01_diff_1k.jpg", tint=(0.95, 0.93, 0.90), rough=0.25, tile=0.9)
    material("Brass", color=(0.62, 0.46, 0.20), rough=0.35, metal=0.9)
    material("Metal_Dark", color=(0.05, 0.05, 0.05), rough=0.5, metal=0.6)
    material("Paint_Palette", img=gen["palette"], rough=0.7, tile=1.0)
    material("Sign_Paint", img=gen["signs"], rough=0.6, tile=1.0)
    material("Key_Board", img=gen["keys"], rough=0.6, tile=1.0)
    material("Doors", img=gen["doors"], rough=0.5, tile=1.0)
    material("Fabric_Drape", diff="rough_linen_diff_512.jpg", tint=(0.42, 0.07, 0.08), rough=1.0, tile=0.7, two_sided=True)
    material("Sofa_Fabric", diff="blender/models/lobby/ph-sofa-01/textures/Sofa_01_diff_1k.jpg", tint=(0.86, 0.60, 0.30), rough=0.8)       # mustard velvet
    material("Armchair_Fabric", diff="blender/models/lobby/ph-armchair-01/textures/Armchair_01_diff_1k.jpg", tint=(0.80, 0.70, 0.55), rough=0.8)
    material("Chandelier_Gilt", diff="blender/models/galleries/ph-chandelier-02/textures/Chandelier_02_diff_1k.jpg", rough=0.4, metal=0.8)
    material("Plant_Leaf", color=(0.10, 0.24, 0.08), rough=0.6, two_sided=True)
    material("Plant_Pot", color=(0.10, 0.22, 0.24), rough=0.3)
    material("Bulb_Dead", color=(0.30, 0.28, 0.25), rough=0.2)
    material("Window_Glass", img=gen["frost"], rough=0.3, tile=1.0)
    material("Lamp_Emit", color=(1.0, 0.92, 0.78), rough=0.5, emit=((1.0, 0.78, 0.52), LAMP_EMIT))
    material("Glass_Clear", color=(0.80, 0.88, 0.88), rough=0.05, alpha=0.16)


# ---------------------------------------------------------------- geometry helpers (world space, identity transforms)
def cube(bm, gmin, gmax):
    a, b = B(gmin), B(gmax)
    c = (a + b) / 2
    s = Vector((abs(a.x - b.x), abs(a.y - b.y), abs(a.z - b.z)))
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((s.x, s.y, s.z, 1.0)))


def box(bm, x0, x1, y0, y1, z0, z1):
    cube(bm, (min(x0, x1), min(y0, y1), min(z0, z1)), (max(x0, x1), max(y0, y1), max(z0, z1)))


def cyl(bm, p0, p1, r0, r1=None, seg=16, cap=True):
    a, b = B(p0), B(p1)
    d = b - a
    q = d.to_track_quat("Z", "Y")
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                          matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())


def sphere(bm, p, r, seg=10, squash=1.0):
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(4, seg // 2 + 1), radius=r,
                              matrix=Matrix.Translation(B(p)) @ Matrix.Diagonal((1, 1, squash, 1)))


def ring(bm, c, r, t, y0, y1, seg=24):
    """A flat ring (tube) round a vertical axis: an open cylinder of radius r and wall t."""
    cyl(bm, (c[0], y0, c[1]), (c[0], y1, c[1]), r, r, seg, cap=False)
    cyl(bm, (c[0], y0, c[1]), (c[0], y1, c[1]), r - t, r - t, seg, cap=False)


def face_toward(bm, gdir):
    """Turn every face of `bm` to face the game direction gdir."""
    bm.normal_update()
    want = B(gdir)
    for f in bm.faces:
        if f.normal.dot(want) < 0:
            f.normal_flip()


def quad(bm, p0, p1, p2, p3):
    return bm.faces.new([bm.verts.new(B(p)) for p in (p0, p1, p2, p3)])


def tri(bm, p0, p1, p2):
    return bm.faces.new([bm.verts.new(B(p)) for p in (p0, p1, p2)])


def box_uv(bm, tile):
    """UV0: box projection in metres / tile from world positions, so a texture runs on across pieces."""
    uvl = bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y
            u, v = ((gz, gy) if ax == 0 else (gx, gy) if ax == 1 else (gx, gz))
            lp[uvl].uv = (u / tile, v / tile)


ART = STANDIN = DOORS_C = LAYOUT_C = None


def finish(name, bm, mat, coll=None, smooth=False, tile=None, sharp_deg=35, keep_uv=False, recalc=True):
    for e in bm.edges:
        if smooth and len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) < math.radians(sharp_deg)
        else:
            e.smooth = not (len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(1))
    for f in bm.faces:
        f.smooth = smooth
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if not bm.loops.layers.uv.get("UVMap"):
        bm.loops.layers.uv.new("UVMap")
    if not keep_uv:
        bm.normal_update()
        box_uv(bm, tile or TILES[mat])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(name, me)
    (coll or ART).objects.link(ob)
    return ob


def part(name, mat, build, **kw):
    bm = bmesh.new()
    build(bm)
    if not bm.faces:
        bm.free()
        return None
    return finish(name, bm, mat, **kw)


# the palette: 8 x 8 flat swatches in one small image; a piece of a palette object takes one swatch (all its UVs at the swatch's centre)
PAL = {
    "book_red": (0.45, 0.08, 0.07), "book_green": (0.10, 0.25, 0.14), "book_blue": (0.10, 0.15, 0.33), "book_tan": (0.66, 0.55, 0.38),
    "book_black": (0.07, 0.07, 0.07), "book_ochre": (0.62, 0.42, 0.10), "book_cream": (0.86, 0.82, 0.70), "book_plum": (0.30, 0.10, 0.22),
    "paper": (0.88, 0.86, 0.80), "newsprint": (0.70, 0.69, 0.64), "soil": (0.10, 0.07, 0.05), "stem": (0.30, 0.22, 0.12),
    "salami": (0.55, 0.12, 0.10), "cheese": (0.88, 0.70, 0.30), "olive": (0.30, 0.34, 0.10), "bread": (0.66, 0.42, 0.20),
    "ham": (0.85, 0.52, 0.48), "tray": (0.80, 0.80, 0.78), "jar_glass": (0.60, 0.66, 0.60), "lid_red": (0.60, 0.10, 0.08),
    "tin_blue": (0.18, 0.30, 0.52), "tin_yellow": (0.85, 0.72, 0.20), "bottle_green": (0.08, 0.22, 0.10), "bottle_brown": (0.28, 0.14, 0.05),
    "box_pink": (0.78, 0.50, 0.52), "box_teal": (0.20, 0.48, 0.46), "box_white": (0.85, 0.84, 0.80), "lamp_green": (0.05, 0.30, 0.14),
    "ledger": (0.32, 0.06, 0.06), "rug": (0.30, 0.08, 0.10), "mat": (0.12, 0.10, 0.08), "till": (0.18, 0.18, 0.20),
    "key_black": (0.04, 0.04, 0.04), "vase": (0.75, 0.72, 0.60), "flower": (0.75, 0.20, 0.25), "card_yellow": (0.90, 0.80, 0.40),
    "card_blue": (0.40, 0.55, 0.80), "enamel_cream": (0.86, 0.82, 0.68), "cord": (0.08, 0.07, 0.06), "trunk": (0.36, 0.28, 0.18),
}
PAL_KEYS = list(PAL)


def pal_uv(key):
    i = PAL_KEYS.index(key)
    return ((i % 8 + 0.5) / 8, 1 - (i // 8 + 0.5) / 8)


class Painter:
    """Builds one palette mesh from many pieces, each piece painted one swatch."""
    def __init__(s):
        s.bm = bmesh.new()
        s.uvl = s.bm.loops.layers.uv.new("UVMap")

    def add(s, key, fn, *a, **kw):
        old = set(s.bm.faces)
        fn(s.bm, *a, **kw)
        uv = pal_uv(key)
        for f in s.bm.faces:
            if f not in old:
                for lp in f.loops:
                    lp[s.uvl].uv = uv

    def done(s, name, coll=None, smooth=False):
        if not s.bm.faces:
            s.bm.free()
            return None
        return finish(name, s.bm, "Paint_Palette", coll, smooth=smooth, keep_uv=True)


def set_uv_rect(bm, faces, rect, axes):
    """Planar UV for `faces` over a game-space rectangle: axes = (iu, iv) game axis indices; rect = (u0, v0, u1, v1) in metres -> 0..1."""
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    u0, v0, u1, v1 = rect
    for f in faces:
        for lp in f.loops:
            p = lp.vert.co
            g = (p.x, p.z, -p.y)
            lp[uvl].uv = ((g[axes[0]] - u0) / (u1 - u0), (g[axes[1]] - v0) / (v1 - v0))


def panel(name, mat, centre, normal, w, h, uv=(0, 0, 1, 1), coll=None, d=0.0, bm=None):
    """A flat quad facing `normal` ("+x", "-x", "+z", "-z"), w wide, h tall, its UV the rectangle uv (u0, v0, u1, v1), the picture upright."""
    r = Vector(RIGHT[normal])
    up = Vector((0, 1, 0))
    c = Vector(centre)
    pts = [c - r * w / 2 - up * h / 2, c + r * w / 2 - up * h / 2, c + r * w / 2 + up * h / 2, c - r * w / 2 + up * h / 2]
    own = bm is None
    bm = bm or bmesh.new()
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    f = quad(bm, *[tuple(p) for p in pts])
    u0, v0, u1, v1 = uv
    for lp, (s, t) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = (u0 + (u1 - u0) * s, v0 + (v1 - v0) * t)
    if own:
        return finish(name, bm, mat, coll, keep_uv=True, recalc=False)
    return f


RIGHT = {"+x": (0, 0, -1), "-x": (0, 0, 1), "+z": (1, 0, 0), "-z": (-1, 0, 0)}
NORMAL = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}
WALL_OF = {"N": "+z", "S": "-z", "W": "+x", "E": "-x"}          # a wall by its inward normal
WALL_FACE = {"+z": Z0, "-z": Z1, "+x": X0, "-x": X1}


def on_wall(normal, a, y, d):
    """A game point on the wall whose inward normal is `normal`: a along it, height y, d metres into the room."""
    face = WALL_FACE[normal]
    off = face + (1 if normal[0] == "+" else -1) * d
    return (off, y, a) if normal[1] == "x" else (a, y, off)


def wall_box(bm, normal, a0, a1, y0, y1, d0, d1):
    p, q = on_wall(normal, a0, y0, d0), on_wall(normal, a1, y1, d1)
    cube(bm, [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)])


def dedupe_inner(bm):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.verts.index_update()
    seen = {}
    for f in bm.faces:
        seen.setdefault(frozenset(v.index for v in f.verts), []).append(f)
    inner = [f for fs in seen.values() if len(fs) > 1 for f in fs]
    bmesh.ops.delete(bm, geom=inner, context="FACES_ONLY")
    bmesh.ops.delete(bm, geom=[e for e in bm.edges if not e.link_faces], context="EDGES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")


def holed_box(bm, axis, lo, hi, y0, y1, c0, c1, holes):
    """A box from lo..hi along `axis` ("x" or "z"), y0..y1 high, c0..c1 across, with rectangular holes [(a0, a1, ya, yb)] right through it."""
    cuts_a = sorted({lo, hi} | {h[i] for h in holes for i in (0, 1) if lo < h[i] < hi})
    cuts_y = sorted({y0, y1} | {h[i] for h in holes for i in (2, 3) if y0 < h[i] < y1})
    for a0, a1 in zip(cuts_a, cuts_a[1:]):
        for ya, yb in zip(cuts_y, cuts_y[1:]):
            am, ym = (a0 + a1) / 2, (ya + yb) / 2
            if any(h[0] < am < h[1] and h[2] < ym < h[3] for h in holes):
                continue
            if axis == "x":
                cube(bm, (a0, ya, c0), (a1, yb, c1))
            else:
                cube(bm, (c0, ya, a0), (c1, yb, a1))
    dedupe_inner(bm)


# ---------------------------------------------------------------- generated pictures (numpy, own work, fixed seeds)
GLYPHS = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"], "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"], "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"], "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"], "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"], "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"], "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"], "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"], "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"], "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"], "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"], "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"], "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"], "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    " ": ["00000"] * 7, "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"], ".": ["00000"] * 6 + ["00100"],
    "&": ["01100", "10010", "10100", "01000", "10101", "10010", "01101"], ">": ["01000", "00100", "00010", "00001", "00010", "00100", "01000"],
    ":": ["00000", "00100", "00000", "00000", "00000", "00100", "00000"], "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    "0": ["01110", "10011", "10101", "10101", "11001", "10001", "01110"], "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00110", "01000", "10000", "11111"], "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["10010", "10010", "10010", "11111", "00010", "00010", "00010"], "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["01110", "10000", "11110", "10001", "10001", "10001", "01110"], "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"], "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
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


def rs(a, h, w):
    ys, xs = np.linspace(0, a.shape[0] - 1, h), np.linspace(0, a.shape[1] - 1, w)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, a.shape[0] - 1), np.minimum(x0 + 1, a.shape[1] - 1)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    return a[y0][:, x0] * (1 - fy) * (1 - fx) + a[y0][:, x1] * (1 - fy) * fx + a[y1][:, x0] * fy * (1 - fx) + a[y1][:, x1] * fy * fx


def vnoise(h, w, rng, octaves=5, base=4, wrap=False):
    out, amp, tot = np.zeros((h, w)), 1.0, 0.0
    for k in range(octaves):
        n = base * 2 ** k
        g = rng.random((n + 1, n + 1))
        if wrap:                                   # a tile that repeats without a seam
            g[-1, :] = g[0, :]
            g[:, -1] = g[:, 0]
        out += amp * rs(g, h, w)
        tot += amp
        amp *= 0.5
    return out / tot


def text_mask(text, h, w, rng, fill=0.62, maxw=0.9, painted=False):
    adv = 6
    units = len(text) * adv - 1
    s = max(1, int(min(w * maxw / units, h * fill / 7)))
    m = np.zeros((h, w), np.float32)
    x = (w - units * s) // 2
    y0 = (h - 7 * s) // 2
    for ch in text:
        g = GLYPHS.get(ch, GLYPHS[" "])
        for r, row in enumerate(g):
            for c, v in enumerate(row):
                if v == "1":
                    m[y0 + r * s:y0 + (r + 1) * s, x + c * s:x + (c + 1) * s] = 1
        x += adv * s
    k = max(1, s // 4)
    m = np.clip((blur(m, k, 2) - 0.5) * 4 + 0.5, 0, 1)
    return m


def carpet_pixels():
    """The lobby carpet: a burgundy ground, a gold diamond lattice with a teal-and-cream rosette at every crossing and a small star in every diamond,
    worn paler along the walking lines (wear is the texture's own noise: it tiles). One repeat is 1.6 m."""
    S = 1024
    rng = np.random.default_rng(5)
    yy, xx = (np.mgrid[0:S, 0:S] + 0.5) / S
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.36, 0.07, 0.08)
    for (cx, cy) in ((0, 0), (1, 0), (0, 1), (1, 1), (0.5, 0.5)):
        pass
    fx, fy = (xx * 2) % 1.0, (yy * 2) % 1.0                       # 2 x 2 cells a repeat
    d = np.abs(fx - 0.5) + np.abs(fy - 0.5)                       # 0 at a cell's centre, 0.5 on its diamond, 1 at its corners
    lattice = np.clip(1 - np.abs(d - 0.5) / 0.022, 0, 1)
    lattice2 = np.clip(1 - np.abs(d - 0.46) / 0.008, 0, 1)
    img = img * (1 - lattice[..., None]) + np.array([0.72, 0.54, 0.22]) * lattice[..., None]
    img = img * (1 - lattice2[..., None]) + np.array([0.18, 0.30, 0.28]) * lattice2[..., None]
    # rosettes at the corners (the lattice's crossings) and a star at each centre
    cx, cy = np.minimum(fx, 1 - fx), np.minimum(fy, 1 - fy)
    r = np.sqrt(cx ** 2 + cy ** 2)
    th = np.arctan2(cy, cx)
    petal = 0.10 + 0.035 * np.cos(8 * th * 2)
    ros = np.clip((petal - r) / 0.01, 0, 1)
    inner = np.clip((0.05 - r) / 0.008, 0, 1)
    img = img * (1 - ros[..., None]) + np.array([0.16, 0.36, 0.34]) * ros[..., None]
    img = img * (1 - inner[..., None]) + np.array([0.86, 0.78, 0.58]) * inner[..., None]
    sx, sy = fx - 0.5, fy - 0.5
    rr = np.sqrt(sx ** 2 + sy ** 2)
    st = np.arctan2(sy, sx)
    star = np.clip(((0.06 + 0.03 * np.cos(4 * st)) - rr) / 0.008, 0, 1)
    img = img * (1 - star[..., None]) + np.array([0.80, 0.62, 0.28]) * star[..., None]
    dots = np.clip(1 - (np.abs(((fx * 8) % 1) - 0.5) + np.abs(((fy * 8) % 1) - 0.5)) / 0.12, 0, 1) * (np.abs(d - 0.25) < 0.08)
    img = img * (1 - 0.6 * dots[..., None]) + np.array([0.55, 0.20, 0.16]) * 0.6 * dots[..., None]
    n = vnoise(S, S, rng, 6, 4, wrap=True)
    pile = vnoise(S, S, rng, 2, 128, wrap=True)
    img = img * (0.82 + 0.28 * n[..., None]) * (0.92 + 0.1 * pile[..., None])
    return np.clip(img, 0, 1).astype(np.float32)


def paper_pixels():
    """Sage damask paper: two-tone stripes with a mirrored leaf-and-scroll motif, faded and yellowed. One repeat is 0.9 m."""
    S = 1024
    rng = np.random.default_rng(11)
    yy, xx = (np.mgrid[0:S, 0:S] + 0.5) / S
    img = np.zeros((S, S, 3), np.float32)
    stripe = (np.abs(((xx * 4) % 1) - 0.5) < 0.25)
    img[:] = (0.50, 0.55, 0.42)
    img[stripe] = (0.57, 0.61, 0.48)
    fx = np.abs(((xx * 2) % 1) - 0.5) * 2                        # mirrored about each motif's axis
    fy = (yy * 2) % 1
    r = np.sqrt((fx * 0.9) ** 2 + ((fy - 0.5) * 1.3) ** 2)
    th = np.arctan2(fy - 0.5, fx + 1e-3)
    leaf = np.clip(((0.30 + 0.10 * np.cos(3 * th) + 0.05 * np.cos(7 * th)) - r) / 0.02, 0, 1) * np.clip((r - 0.08) / 0.02, 0, 1)
    vein = np.clip(1 - np.abs(r - 0.18) / 0.008, 0, 1) * (np.cos(5 * th) > 0)
    img = img * (1 - 0.35 * leaf[..., None]) + np.array([0.70, 0.70, 0.56]) * 0.35 * leaf[..., None]
    img = img * (1 - 0.4 * vein[..., None]) + np.array([0.42, 0.46, 0.34]) * 0.4 * vein[..., None]
    n = vnoise(S, S, rng, 6, 4, wrap=True)
    img = img * (0.88 + 0.2 * n[..., None])
    img = img * np.array([1.0, 0.98, 0.92])
    return np.clip(img, 0, 1).astype(np.float32)


def tile_pixels():
    """The deli's floor: 15 cm black and white tiles in a checker (4 x 4 a repeat, 0.6 m), grey grout, scuffed."""
    S = 512
    rng = np.random.default_rng(13)
    yy, xx = np.mgrid[0:S, 0:S]
    c = ((xx // 128) + (yy // 128)) % 2
    img = np.where(c[..., None] == 0, np.array([0.80, 0.79, 0.74]), np.array([0.07, 0.07, 0.07])).astype(np.float32)
    grout = ((xx % 128) < 3) | ((yy % 128) < 3)
    img[grout] = (0.40, 0.39, 0.36)
    n = vnoise(S, S, rng, 6, 4, wrap=True)
    return np.clip(img * (0.85 + 0.25 * n[..., None]), 0, 1).astype(np.float32)


def wood_pixels():
    """Panelling wood: a warm mid-brown with long grain along u (box-mapped, so it runs along the walls) and darker figure; tiles."""
    S = 1024
    rng = np.random.default_rng(29)
    yy, xx = (np.mgrid[0:S, 0:S] + 0.5) / S
    def wrapped(h, w):
        a = rng.random((h + 1, w + 1))
        a[-1, :], a[:, -1] = a[0, :], a[:, 0]
        return rs(a, S, S)
    g = wrapped(64, 8)                                                   # long streaks: 64 across v, 8 along u
    fine = wrapped(256, 4)
    figure = 0.5 + 0.5 * np.sin((yy * 40 + 3 * vnoise(S, S, rng, 4, 4, wrap=True)) * 2 * math.pi)
    t = 0.55 * g + 0.25 * fine + 0.2 * figure
    lo, hi = np.array([0.40, 0.25, 0.14]), np.array([0.62, 0.42, 0.26])
    img = lo + (hi - lo) * t[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def frost_pixels():
    """Frosted glass: a pale, faintly mottled field with a thin etched border line."""
    S = 256
    rng = np.random.default_rng(23)
    n = vnoise(S, S, rng, 5, 4)
    img = np.ones((S, S, 3), np.float32) * np.array([0.86, 0.88, 0.88]) * (0.94 + 0.08 * n[..., None])
    yy, xx = np.mgrid[0:S, 0:S]
    e = (np.minimum(np.minimum(xx, S - 1 - xx), np.minimum(yy, S - 1 - yy)) == 12)
    img[e] *= 0.86
    return np.clip(img, 0, 1).astype(np.float32)


def palette_pixels():
    img = np.zeros((128, 128, 3), np.float32)
    for i, k in enumerate(PAL_KEYS):
        r, c = i // 8, i % 8
        img[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16] = PAL[k]
    return img


SIGN_ROWS = {"RECEPTION": 0, "DELICATESSEN": 1, "NEWS & BOOKS": 2, "GIFTS & SUNDRIES": 3}
PLAQUES = ["OFFICE", "LUGGAGE", "PRIVATE"]         # row 4, thirds
CLOCKS = [("LONDON", 3.1), ("FARWAY", 6.9), ("TOKYO", 11.6)]   # (label, hour shown)
MENU = ["SOUP OF THE DAY", "HAM ON RYE", "CHEESE PLATE", "PICKLES", "COFFEE", "TEA"]


def sign_board(text, h, w, bg, fg, rng, fill=0.5, border=None):
    row = np.zeros((h, w, 3), np.float32)
    row[:] = bg
    m = text_mask(text, h, w, rng, fill=fill, maxw=0.86)
    row = row * (1 - m[..., None]) + np.array(fg) * m[..., None]
    n = vnoise(h, w, rng, 4, 6)
    row = row * (0.9 + 0.16 * n[..., None])
    b = border or tuple(v * 0.6 for v in bg)
    row[:4] = row[-4:] = row[:, :4] = row[:, -4:] = b
    return row


def signs_pixels():
    """The sign atlas, 1024 x 1024: rows 0-3 are the painted fascia signs (1024 x 128 each), row 4 the three brass plaques of the facade doors, row 5
    the back door's sign and the desk's card; the bottom 256 rows are the deli's menu board (512 wide) and the three clock faces with their labels."""
    W = 1024
    rng = np.random.default_rng(17)
    img = np.zeros((W, W, 3), np.float32)
    gold, cream = (0.82, 0.64, 0.28), (0.90, 0.85, 0.72)
    styles = {"RECEPTION": ((0.16, 0.09, 0.05), gold), "DELICATESSEN": ((0.07, 0.20, 0.13), gold),
              "NEWS & BOOKS": ((0.33, 0.07, 0.08), cream), "GIFTS & SUNDRIES": ((0.08, 0.12, 0.26), cream)}
    for text, r in SIGN_ROWS.items():
        bg, fg = styles[text]
        img[r * 128:(r + 1) * 128] = sign_board(text, 128, W, bg, fg, rng, 0.5, border=gold)
    for i, t in enumerate(PLAQUES):
        x0, x1 = i * 341, (i + 1) * 341
        img[512:640, x0:x1] = sign_board(t, 128, x1 - x0, (0.66, 0.50, 0.22), (0.12, 0.08, 0.04), rng, 0.42, border=(0.45, 0.33, 0.12))
    img[640:768, 0:512] = sign_board("ATRIUM >", 128, 512, (0.10, 0.10, 0.10), cream, rng, 0.42, border=gold)
    img[640:768, 512:1024] = sign_board("RING FOR SERVICE", 128, 512, (0.86, 0.82, 0.70), (0.15, 0.10, 0.06), rng, 0.3)
    # the menu board: a blackboard, chalk lines
    mb = np.zeros((256, 512, 3), np.float32)
    mb[:] = (0.08, 0.10, 0.09)
    title = text_mask("DELI", 52, 512, rng, fill=0.75, maxw=0.4)
    mb[6:58] = mb[6:58] * (1 - title[..., None]) + np.array(gold) * title[..., None]
    for i, line in enumerate(MENU):
        m = text_mask(line, 30, 512, rng, fill=0.6, maxw=0.8)
        y = 64 + i * 31
        mb[y:y + 30] = mb[y:y + 30] * (1 - m[..., None]) + np.array([0.86, 0.86, 0.82]) * m[..., None]
    mb = mb * (0.85 + 0.25 * vnoise(256, 512, rng, 5, 6)[..., None])
    mb[:6] = mb[-6:] = mb[:, :6] = mb[:, -6:] = (0.30, 0.20, 0.12)
    img[768:1024, 0:512] = mb
    # the clocks: three faces (160 x 160) and their labels (160 x 96)
    for i, (label, hour) in enumerate(CLOCKS):
        x0 = 512 + i * 170
        yy, xx = (np.mgrid[0:160, 0:160] + 0.5 - 80) / 80
        rr = np.sqrt(xx ** 2 + yy ** 2)
        face = np.zeros((160, 160, 3), np.float32)
        face[:] = (0.20, 0.15, 0.10)
        face[rr < 0.98] = (0.90, 0.87, 0.78)
        ang = np.arctan2(xx, -yy)                                   # 0 at twelve, clockwise
        ticks = (rr > 0.78) & (rr < 0.92) & (np.abs(((ang / (2 * math.pi) * 12) % 1) - 0.5) > 0.47)
        face[ticks] = (0.10, 0.08, 0.06)
        for a, ln, wd in ((hour / 12 * 2 * math.pi, 0.5, 0.06), ((hour % 1) * 2 * math.pi, 0.75, 0.04)):
            ux, uy = math.sin(a), -math.cos(a)
            t = xx * ux + yy * uy
            dist = np.abs(xx * uy - yy * ux)
            face[(t > -0.08) & (t < ln) & (dist < wd)] = (0.06, 0.05, 0.04)
        face[rr < 0.06] = (0.55, 0.40, 0.15)
        img[768:928, x0:x0 + 160] = face
        img[928:1024, x0:x0 + 160] = sign_board(label, 96, 160, (0.16, 0.09, 0.05), gold, rng, 0.36, border=gold)
    return np.clip(img, 0, 1).astype(np.float32)


def sign_uv(r0, r1, c0, c1, S=1024):
    """UV rect for atlas rows r0..r1 (top down) and columns c0..c1."""
    return (c0 / S, 1 - r1 / S, c1 / S, 1 - r0 / S)


def keys_pixels():
    """The key board: 6 rows of 10 pigeonholes in a dark wood frame, each with a brass number plate; most hold a key on a brass tag, some letters."""
    h, w = 512, 1024
    rng = np.random.default_rng(31)
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (0.20, 0.12, 0.07)
    rows, cols = 6, 10
    ch, cw = (h - 40) / rows, (w - 40) / cols
    for r in range(rows):
        for c in range(cols):
            y0, x0 = int(20 + r * ch), int(20 + c * cw)
            y1, x1 = int(y0 + ch - 8), int(x0 + cw - 8)
            img[y0:y1, x0:x1] = (0.06, 0.035, 0.02)
            img[y1 - 16:y1 - 4, x0 + 30:x1 - 30] = (0.70, 0.52, 0.22)                       # the number plate
            k = rng.random()
            if k < 0.7:                                                                  # a key on its tag
                kx = (x0 + x1) // 2 + int(rng.integers(-8, 8))
                img[y0 + 10:y0 + 40, kx - 2:kx + 2] = (0.55, 0.42, 0.18)
                img[y0 + 38:y0 + 62, kx - 9:kx + 9] = (0.72, 0.55, 0.24)
            elif k < 0.82:                                                               # a letter
                img[y1 - 46:y1 - 22, x0 + 14:x1 - 20] = (0.88, 0.85, 0.76)
    n = vnoise(h, w, rng, 5, 6)
    img = img * (0.85 + 0.25 * n[..., None])
    img[:12] = img[-12:] = img[:, :12] = img[:, -12:] = (0.28, 0.18, 0.10)
    return np.clip(img, 0, 1).astype(np.float32)


def doors_pixels():
    """The doors atlas, 1024 x 1024. Left half: the street door's leaf (a brass frame round frosted glass, a kick plate and a push bar). Right half:
    a painted panel door (cream, four fielded panels, a brass kick plate), used by the back door and the facade doors. Two flat swatches for edges and
    handles sit in the corners: brass at (0.01, 0.01), cream paint at (0.99, 0.01)."""
    S = 1024
    rng = np.random.default_rng(41)
    img = np.zeros((S, S, 3), np.float32)
    brass, frost, cream = np.array([0.66, 0.50, 0.22]), np.array([0.84, 0.86, 0.85]), np.array([0.80, 0.76, 0.64])
    L = img[:, :512]
    L[:] = brass
    L[40:-200, 46:-46] = frost
    L[-180:-30, 46:-46] = brass * 0.85                                                        # the kick plate
    L[470:500, 46:-46] = brass * 1.1                                                          # the push bar's line
    n = vnoise(S, 512, rng, 5, 6)
    L *= (0.92 + 0.12 * n[..., None])
    R = img[:, 512:]
    R[:] = cream
    for (y0, y1) in ((60, 440), (520, 880)):
        for (x0, x1) in ((50, 236), (276, 462)):
            R[y0:y1, x0:x1] = cream * 0.93
            R[y0:y0 + 8, x0:x1] = cream * 1.08
            R[y1 - 8:y1, x0:x1] = cream * 0.78
            R[y0:y1, x0:x0 + 8] = cream * 1.04
            R[y0:y1, x1 - 8:x1] = cream * 0.82
    R[920:1000, 20:492] = brass * 0.85
    R[470:500, 440:470] = brass                                                               # the knob's rose
    m = vnoise(S, 512, rng, 6, 6)
    R *= (0.86 + 0.2 * m[..., None])
    img[0:24, 0:24] = brass
    img[0:24, S - 24:S] = cream
    return np.clip(img, 0, 1).astype(np.float32)


DOOR_FRONT_UV = (0.0, 0.0, 0.5, 1.0)
DOOR_PANEL_UV = (0.5, 0.0, 1.0, 1.0)
BRASS_PIX = (0.012, 0.988)
CREAM_PIX = (0.988, 0.988)


def stage_work():
    d = Path(arg("--work", str(ROOT / f"work/{SCENE}")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def mk_image(name, arr, srgb=True):
    """A packed image from a float array (rows top to bottom), written as a PNG first (a generated image forgets its pixels when the file is saved)."""
    h, w = arr.shape[:2]
    im = bpy.data.images.new(name + "_gen", w, h, alpha=False)
    im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :3] = arr[..., :3]
    im.pixels.foreach_set(np.flipud(rgba).ravel())
    gen = stage_work() / "gen"
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


def make_generated():
    return {"carpet": mk_image("Lobby_Carpet", carpet_pixels()), "paper": mk_image("Lobby_Wallpaper", paper_pixels()),
            "tile": mk_image("Deli_Tile", tile_pixels()), "wood": mk_image("Panel_Wood", wood_pixels()), "frost": mk_image("Frosted_Glass", frost_pixels()),
            "palette": mk_image("Lobby_Palette", palette_pixels()), "signs": mk_image("Lobby_Signs", signs_pixels()),
            "keys": mk_image("Key_Board", keys_pixels()), "doors": mk_image("Lobby_Doors", doors_pixels())}


# ---------------------------------------------------------------- the shell: floor, walls, windows, ceiling
def build_floor():
    """The floor slab in cells, one material each: carpet in the hall, marble at the street doors, the deli's tiles under the loft, parquet in the shops."""
    xs = [X0 - T, LX1, -17.1, -13.0, -11.0, X1 + T]
    zs = [Z0 - T, LZ0, -21.0, -17.0, -11.7, Z1 + T]
    cells = {}
    for xa, xb in zip(xs, xs[1:]):
        for za, zb in zip(zs, zs[1:]):
            xm, zm = (xa + xb) / 2, (za + zb) / 2
            if xm < LX1 and zm > LZ0:
                m = "Floor_Tile"
            elif zm > -11.7 and xm > -17.1:
                m = "Floor_Parquet"
            elif xm > -11.0 and -21.0 < zm < -17.0:
                m = "Floor_Marble"
            else:
                m = "Floor_Carpet"
            cells.setdefault(m, []).append((xa, xb, za, zb))
    for m, cs in cells.items():
        def bld(bm, cs=cs):
            for xa, xb, za, zb in cs:
                box(bm, xa, xb, -G.SLAB, 0.0, za, zb)
        part(f"Floor_cells_{m.split('_')[1]}", m, bld)
    # brass strips where the marble meets the carpet, a door mat (passable)
    part("decor_floor_brass", "Brass", lambda bm: [box(bm, -11.02, -10.98, 0.0, 0.004, -21.0, -17.0), box(bm, -11.0, X1, 0.0, 0.004, -21.02, -20.98),
                                                    box(bm, -11.0, X1, 0.0, 0.004, -17.02, -16.98)])
    p = Painter()
    p.add("mat", box, -9.7, X1 - 0.02, 0.0, 0.015, FD_Z0 - 0.2, FD_Z1 + 0.2)
    p.done("decor_door_mat")


def wall_pieces():
    out = []
    for n, b in BOX.items():
        if n.startswith("Lobby_Wall_"):
            side = n.split("_")[2]
            out.append((n, side, b))
    return out


def wall_holes(side, lo, hi):
    """Holes in the art (not in the colliders): the street windows and the transom over the front doors, on the east wall."""
    if side != "E":
        return []
    hs = [(z0, z1, WIN_Y[0], WIN_Y[1]) for z0, z1 in WIN_Z] + [TRANSOM]
    return [h for h in hs if h[0] < hi and h[1] > lo]


def build_walls():
    """Each wall collider gets its art twin, cut at the dado (wood panelling below, the paper above) and holed for the windows. One object per
    collider piece and band, so each stands over its own collider (the layout check reads each object's box)."""
    for n, side, b in wall_pieces():
        axis = "x" if side in "NS" else "z"
        ia, ic = (0, 2) if axis == "x" else (2, 0)
        lo, hi = b["min"][ia], b["max"][ia]
        c0, c1 = b["min"][ic], b["max"][ic]
        y0, y1 = b["min"][1], b["max"][1]
        holes = wall_holes(side, lo, hi)
        for band, ya, yb, mat in (("lo", y0, min(y1, BAND), "Wall_Panel"), ("hi", max(y0, BAND), y1, "Wall_Paper")):
            if yb - ya < 1e-4:
                continue
            part(f"Wall_{n[len('Lobby_Wall_'):]}_{band}", mat, lambda bm, ya=ya, yb=yb: holed_box(bm, axis, lo, hi, ya, yb, c0, c1, holes))


def dress_run(tag, normal, a0, a1, yb, yt, holes=(), panels=True):
    """Panelling details on a wall run: skirting, the dado rail and fielded panel frames (strips at most 2 cm proud), avoiding `holes` (a0, a1, y0, y1)."""
    a0, a1 = min(a0, a1), max(a0, a1)

    def free_spans(lo, hi, yr):
        cuts = sorted([(h[0], h[1]) for h in holes if h[2] < yr[1] and h[3] > yr[0] and h[0] < hi and h[1] > lo])
        spans, x = [], lo
        for h0, h1 in cuts:
            if h0 > x + 1e-3:
                spans.append((x, h0))
            x = max(x, h1)
        if x < hi - 1e-3:
            spans.append((x, hi))
        return spans

    def skirt(bm):
        for s0, s1 in free_spans(a0, a1, (yb, yb + 0.18)):
            wall_box(bm, normal, s0, s1, yb, yb + 0.18, 0.0, 0.02)
            wall_box(bm, normal, s0, s1, yb + 0.18, yb + 0.2, 0.0, 0.012)

    def rail(bm):
        for s0, s1 in free_spans(a0, a1, (yt - 0.09, yt)):
            wall_box(bm, normal, s0, s1, yt - 0.09, yt - 0.03, 0.0, 0.02)
            wall_box(bm, normal, s0, s1, yt - 0.03, yt, 0.0, 0.035)

    def frames(bm):
        py0, py1 = yb + 0.34, yt - 0.24
        for s0, s1 in free_spans(a0, a1, (py0, py1)):
            L = s1 - s0
            k = max(1, int(round(L / 1.15)))
            if L < 0.5:
                continue
            w = L / k
            for i in range(k):
                pa, pb = s0 + i * w + 0.09, s0 + (i + 1) * w - 0.09
                for (u0, u1, v0, v1) in ((pa, pb, py0, py0 + 0.045), (pa, pb, py1 - 0.045, py1), (pa, pa + 0.045, py0, py1), (pb - 0.045, pb, py0, py1)):
                    wall_box(bm, normal, u0, u1, v0, v1, 0.0, 0.018)
    part(f"Trim_skirt_{tag}", "Trim_Wood", skirt)
    part(f"Trim_rail_{tag}", "Trim_Wood", rail)
    if panels:
        part(f"Trim_panels_{tag}", "Trim_Wood", frames)


def build_wall_dressing():
    for n, side, b in wall_pieces():
        if b["min"][1] > 0.1:
            continue                                  # a piece over a door: nothing at the panelling's height
        normal = WALL_OF[side]
        axis_i = 0 if side in "NS" else 2
        lo, hi = max(b["min"][axis_i], X0 if side in "NS" else Z0), min(b["max"][axis_i], X1 if side in "NS" else Z1)
        holes = list(wall_holes(side, lo, hi))
        top = BAND
        if side == "W" or (side == "S" and hi <= LX1 + 1e-6):
            pass
        dress_run(n[len("Lobby_Wall_"):], normal, lo, hi, 0.0, top, holes)
    # the loft's own panelling, on the west and south walls over the loft (overhead from the hall)
    dress_run("loft_W", "+x", LZ0, Z1, LOFT_Y, LOFT_Y + 1.2)
    dress_run("loft_S", "-z", X0, LX1, LOFT_Y, LOFT_Y + 1.2)
    # the cornice and the picture rail, all round (overhead)

    def cornice(bm):
        for nm in ("+z", "-z", "+x", "-x"):
            lo, hi = (X0, X1) if nm[1] == "z" else (Z0, Z1)
            for (ya, yb, d) in ((H - 0.32, H - 0.2, 0.05), (H - 0.2, H - 0.08, 0.10), (H - 0.08, H, 0.16)):
                wall_box(bm, nm, lo, hi, ya, yb, 0.0, d)

    def picture_rail(bm):
        for nm in ("+z", "-z", "+x", "-x"):
            lo, hi = (X0, X1) if nm[1] == "z" else (Z0, Z1)
            for s0, s1 in ((lo, hi),):
                if nm == "-x":
                    x = s0
                    for c0, c1 in sorted(WIN_Z):
                        if c0 - 0.52 > x:
                            wall_box(bm, nm, x, c0 - 0.52, 4.62, 4.66, 0.0, 0.025)
                        x = c1 + 0.52
                    wall_box(bm, nm, x, s1, 4.62, 4.66, 0.0, 0.025)
                else:
                    wall_box(bm, nm, s0, s1, 4.62, 4.66, 0.0, 0.025)
    part("Trim_cornice", "Trim_Paint", cornice)
    part("Trim_picture_rail", "Trim_Wood", picture_rail)


DRAPES = []


def build_windows():
    """The street windows: a wooden frame in the reveal with glazing bars and a transom, frosted panes (opaque: the street is not built; their lightmap
    is filled flat, bright by day and sodium-dim at night), a marble sill, an architrave, velvet drapes and a pelmet."""
    wins = [(z0, z1, WIN_Y[0], WIN_Y[1], True) for z0, z1 in WIN_Z] + [(TRANSOM[0], TRANSOM[1], TRANSOM[2], TRANSOM[3], False)]

    def frames(bm, z0, z1, ya, yb, full):
        if True:
            fw = 0.06
            wall_box(bm, "-x", z0, z1, ya, ya + fw, -0.13, -0.06)
            wall_box(bm, "-x", z0, z1, yb - fw, yb, -0.13, -0.06)
            wall_box(bm, "-x", z0, z0 + fw, ya, yb, -0.13, -0.06)
            wall_box(bm, "-x", z1 - fw, z1, ya, yb, -0.13, -0.06)
            zm = (z0 + z1) / 2
            if full:
                wall_box(bm, "-x", zm - 0.03, zm + 0.03, ya, yb, -0.12, -0.07)          # the mullion
                for yy in (ya + (yb - ya) * 0.36, ya + (yb - ya) * 0.72):
                    wall_box(bm, "-x", z0, z1, yy - 0.025, yy + 0.025, -0.12, -0.07)   # the glazing bars
            else:
                for zz in (z0 + (z1 - z0) / 3, z0 + 2 * (z1 - z0) / 3):
                    wall_box(bm, "-x", zz - 0.02, zz + 0.02, ya, yb, -0.12, -0.07)
    for i, w in enumerate(wins):
        part(f"Window_Frame_{i}", "Trim_Wood", lambda bm, w=w: frames(bm, *w))
        z0, z1, ya, yb, full = w
        bm = bmesh.new()
        uvl = bm.loops.layers.uv.new("UVMap")
        x = X1 + 0.1
        f = quad(bm, (x, ya, z0), (x, yb, z0), (x, yb, z1), (x, ya, z1))
        for lp, uv in zip(f.loops, ((0, 0), (0, 1), (1, 1), (1, 0))):
            lp[uvl].uv = uv
        face_toward(bm, (-1, 0, 0))
        finish(f"Window_Pane_{i}", bm, "Window_Glass", keep_uv=True, recalc=False)
    for i, (z0, z1, ya, yb, full) in enumerate(wins):
        if not full:
            continue
        part(f"Window_Sill_{i}", "Marble_Top", lambda bm, z0=z0, z1=z1: wall_box(bm, "-x", z0 - 0.06, z1 + 0.06, WIN_Y[0] - 0.05, WIN_Y[0], -0.1, 0.04))
        part(f"Window_Arch_{i}", "Trim_Wood", lambda bm, z0=z0, z1=z1: [wall_box(bm, "-x", z0 - 0.1, z0, WIN_Y[0] - 0.05, WIN_Y[1] + 0.1, 0.0, 0.025),
                                                                        wall_box(bm, "-x", z1, z1 + 0.1, WIN_Y[0] - 0.05, WIN_Y[1] + 0.1, 0.0, 0.025),
                                                                        wall_box(bm, "-x", z0 - 0.1, z1 + 0.1, WIN_Y[1], WIN_Y[1] + 0.1, 0.0, 0.025)])
        DRAPES.append((z0, z1))
    # the drapes and pelmets (passable cloth)
    rng = np.random.default_rng(7)

    def drape(bm, za, zb, folds):
        nu, nv = 3 * folds + 1, 14
        ytop, ybot = WIN_Y[1] + 0.32, 0.02
        verts = []
        for j in range(nv):
            y = ytop + (ybot - ytop) * j / (nv - 1)
            spread = 0.75 + 0.25 * (j / (nv - 1))                     # gathered at the top, a little fuller at the floor
            row = []
            for i in range(nu):
                t = i / (nu - 1)
                z = za + (zb - za) * (0.5 + (t - 0.5) * spread)
                d = 0.06 + 0.05 * (0.5 + 0.5 * math.sin(t * folds * 2 * math.pi + rng.random() * 0.3))
                row.append(bm.verts.new(B(on_wall("-x", z, y, d))))
            verts.append(row)
        for j in range(nv - 1):
            for i in range(nu - 1):
                bm.faces.new((verts[j][i], verts[j][i + 1], verts[j + 1][i + 1], verts[j + 1][i]))
    bmd = bmesh.new()
    for z0, z1 in DRAPES:
        drape(bmd, z0 - 0.42, z0 + 0.12, 4)
        drape(bmd, z1 - 0.12, z1 + 0.42, 4)
    bmd.normal_update()
    for f in bmd.faces:
        if f.normal.x > 0:
            f.normal_flip()
    finish("decor_drapes", bmd, "Fabric_Drape", smooth=True, sharp_deg=80, recalc=False)
    part("Window_Pelmets", "Fabric_Drape", lambda bm: [wall_box(bm, "-x", z0 - 0.5, z1 + 0.5, WIN_Y[1] + 0.3, WIN_Y[1] + 0.62, 0.0, 0.16) for z0, z1 in DRAPES])


def build_ceiling():
    """The plaster ceiling with a grid of beams (coffers), the chandelier's medallion in the middle coffer."""
    c = BOX["Lobby_Ceiling"]
    part("Ceiling_Slab", "Ceiling_Plaster", lambda bm: box(bm, c["min"][0], c["max"][0], H, c["max"][1], c["min"][2], c["max"][2]))

    def beams(bm):
        for x in (LX1, -17.5, -12.5):
            box(bm, x - 0.16, x + 0.16, H - 0.28, H, Z0, Z1)
        for z in (-24.0, -14.0):
            box(bm, X0, X1, H - 0.28, H, z - 0.16, z + 0.16)
        cyl(bm, (CHAND[0], H - 0.06, CHAND[1]), (CHAND[0], H, CHAND[1]), 0.75, 0.8, 40)
        cyl(bm, (CHAND[0], H - 0.12, CHAND[1]), (CHAND[0], H - 0.06, CHAND[1]), 0.45, 0.5, 32)
    part("Ceiling_Beams", "Trim_Paint", beams, smooth=True, sharp_deg=40)
    cans = []
    xs, zs = [X0, LX1, -17.5, -12.5, X1], [Z0, -24.0, -14.0, Z1]
    for xa, xb in zip(xs, xs[1:]):
        for za, zb in zip(zs, zs[1:]):
            xm = (xa + xb) / 2
            if zb - za > 8:
                pts = [(xm, za + (zb - za) * 0.2), (xm, zb - (zb - za) * 0.2)] if xa != -17.5 else [(xm, za + 1.4), (xm, zb - 1.4)]
            else:
                pts = [(xm, (za + zb) / 2)]
            for x, z in pts:
                cans.append((x, z))
                lamp_light((x, H - 0.03, z), CAN_W, 0.08, kind="SPOT", aim=(0, -1, 0), cone=120, color=(1.0, 0.86, 0.68))
    part("Ceiling_Cans", "Lamp_Emit", lambda bm: [cyl(bm, (x, H - 0.012, z), (x, H, z), 0.09, 0.09, 16) for x, z in cans])
    part("Ceiling_Can_Rims", "Brass", lambda bm: [cyl(bm, (x, H - 0.015, z), (x, H, z), 0.12, 0.12, 16, cap=False) for x, z in cans])


# ---------------------------------------------------------------- doors: the street doors, the back door, the facade doors
def leaf_mesh(w, h, front_uv, edge_pix, knob=None):
    """A door leaf in its own frame: local x from the hinge along the leaf (0..w), y across (-0.025..0.025), z up (0..h). Both faces show the picture
    `front_uv`; the edges take one flat pixel. knob: (x, z, kind)."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    t = 0.025
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, 0, h / 2)) @ Matrix.Diagonal((w, 2 * t, h, 1)))
    u0, v0, u1, v1 = front_uv
    for f in bm.faces:
        f.normal_update()
        if abs(f.normal.y) > 0.9:
            for lp in f.loops:
                x, z = lp.vert.co.x, lp.vert.co.z
                s = x / w if f.normal.y < 0 else 1 - x / w
                lp[uvl].uv = (u0 + (u1 - u0) * s, v0 + (v1 - v0) * z / h)
        else:
            for lp in f.loops:
                lp[uvl].uv = edge_pix
    if knob:
        kx, kz, kind = knob
        old = set(bm.faces)
        for sgn in (-1, 1):
            if kind == "bar":
                bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.015, radius2=0.015, depth=w * 0.7,
                                      matrix=Matrix.Translation((w * 0.5, sgn * (t + 0.05), kz)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
                for xx in (w * 0.17, w * 0.83):
                    bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.01, radius2=0.01, depth=0.05,
                                          matrix=Matrix.Translation((xx, sgn * (t + 0.025), kz)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
            else:
                bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.032, matrix=Matrix.Translation((kx, sgn * (t + 0.05), kz)))
                bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.01, radius2=0.01, depth=0.05,
                                      matrix=Matrix.Translation((kx, sgn * (t + 0.025), kz)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
        for f in bm.faces:
            if f not in old:
                for lp in f.loops:
                    lp[uvl].uv = BRASS_PIX
    return bm


def build_door_leaves():
    """The three leaves, each its own object (the Doors collection) with its origin at the hinge and the greybox door's properties, so export_scene.py
    writes the same `doors` and the page can swing them by name."""
    for d in GB.doors:
        p = d["props"]
        w, h = p["width"], p["height"]
        if d["name"].startswith("DoorLeaf_front"):
            bm = leaf_mesh(w, h, DOOR_FRONT_UV, BRASS_PIX, knob=(w * 0.5, 1.05, "bar"))
            mat = "Doors"
        else:
            bm = leaf_mesh(w, h, DOOR_PANEL_UV, CREAM_PIX, knob=(w - 0.08, 1.0, "knob"))
            mat = "Doors"
        for f in bm.faces:
            f.smooth = False
        me = bpy.data.meshes.new(d["name"])
        bm.to_mesh(me)
        bm.free()
        me.materials.append(MATS[mat])
        ob = bpy.data.objects.new(d["name"], me)
        ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
        for k, v in p.items():
            ob[k] = v
        DOORS_C.objects.link(ob)


def build_door_surrounds():
    # the street doors: casings either side (each over its own wall piece), the head and the transom's bar (overhead)
    part("Door_Front_Casing_N", "Trim_Wood", lambda bm: wall_box(bm, "-x", FD_Z0 - 0.14, FD_Z0, 0.0, FD_H + 0.22, 0.0, 0.03))
    part("Door_Front_Casing_S", "Trim_Wood", lambda bm: wall_box(bm, "-x", FD_Z1, FD_Z1 + 0.14, 0.0, FD_H + 0.22, 0.0, 0.03))
    part("Door_Front_Head", "Trim_Wood", lambda bm: [wall_box(bm, "-x", FD_Z0 - 0.14, FD_Z1 + 0.14, FD_H, FD_H + 0.22, -0.2, 0.03)])
    part("Door_Front_Brass", "Brass", lambda bm: [wall_box(bm, "-x", FD_Z0, FD_Z1, FD_H - 0.002, FD_H + 0.03, -0.2, 0.0)])
    # the back door under the loft: casings, and the ATRIUM sign over it
    part("Door_Back_Casing_N", "Trim_Wood", lambda bm: wall_box(bm, "+x", BD_Z0 - 0.12, BD_Z0, 0.0, BD_H + 0.12, 0.0, 0.025))
    part("Door_Back_Casing_S", "Trim_Wood", lambda bm: wall_box(bm, "+x", BD_Z1, BD_Z1 + 0.12, 0.0, BD_H + 0.12, 0.0, 0.025))
    part("Door_Back_Head", "Trim_Wood", lambda bm: wall_box(bm, "+x", BD_Z0 - 0.12, BD_Z1 + 0.12, BD_H, BD_H + 0.12, 0.0, 0.025))
    panel("Sign_Atrium", "Sign_Paint", on_wall("+x", (BD_Z0 + BD_Z1) / 2, BD_H + 0.31, 0.022), "+x", 0.8, 0.2, sign_uv(640, 768, 0, 512))
    # the facade doors: painted panel doors that do not open, casings and a brass plaque each
    for i, (n, b) in enumerate(sorted(((n, b) for n, b in BOX.items() if n.startswith("Facade_Door")), key=lambda t: t[1]["min"][0])):
        x0, x1, y1, zf = b["min"][0], b["max"][0], b["max"][1], b["max"][2]
        d = zf - Z0

        def leaf(bm, x0=x0, x1=x1, y1=y1, d=d):
            uvl = bm.loops.layers.uv.new("UVMap")
            wall_box(bm, "+z", x0 + 0.03, x1 - 0.03, 0.0, y1 - 0.03, 0.0, d - 0.015)
            u0, v0, u1, v1 = DOOR_PANEL_UV
            for f in bm.faces:
                f.normal_update()
                for lp in f.loops:
                    if f.normal.y < -0.9:                                   # Blender -y = game +z: the face toward the room
                        lp[uvl].uv = (u0 + (u1 - u0) * (lp.vert.co.x - x0) / (x1 - x0), v0 + (v1 - v0) * lp.vert.co.z / y1)
                    else:
                        lp[uvl].uv = CREAM_PIX
            old = set(bm.faces)
            kx = x1 - 0.12
            sphere(bm, (kx, 1.0, Z0 + d + 0.02), 0.025, 10)
            cyl(bm, (kx, 1.0, Z0 + d - 0.02), (kx, 1.0, Z0 + d + 0.01), 0.012, 0.012, 8)
            for f in bm.faces:
                if f not in old:
                    for lp in f.loops:
                        lp[uvl].uv = BRASS_PIX
        bm = bmesh.new()
        leaf(bm)
        finish(f"Facade_Door_{i}", bm, "Doors", keep_uv=True)
        part(f"Facade_Casing_{i}", "Trim_Wood", lambda bm, x0=x0, x1=x1, y1=y1: [wall_box(bm, "+z", x0 - 0.12, x0 + 0.03, 0.0, y1 + 0.12, 0.0, 0.03),
                                                                                wall_box(bm, "+z", x1 - 0.03, x1 + 0.12, 0.0, y1 + 0.12, 0.0, 0.03),
                                                                                wall_box(bm, "+z", x0 - 0.12, x1 + 0.12, y1 - 0.03, y1 + 0.12, 0.0, 0.03)])
        panel(f"Facade_Plaque_{i}", "Sign_Paint", on_wall("+z", (x0 + x1) / 2, 1.62, d + 0.002), "+z", 0.36, 0.13, sign_uv(512, 640, i * 341, (i + 1) * 341))


# ---------------------------------------------------------------- the loft, its stairs and posts
def build_loft():
    s = LOFT
    part("Loft_Slab", "Ceiling_Plaster", lambda bm: box(bm, s["min"][0], s["max"][0], LOFT_Y0, LOFT_Y - 0.02, s["min"][2], s["max"][2]))
    part("Loft_Carpet", "Floor_Carpet", lambda bm: box(bm, s["min"][0], s["max"][0], LOFT_Y - 0.02, LOFT_Y, s["min"][2], s["max"][2]))
    part("Loft_Fascia", "Trim_Wood", lambda bm: [box(bm, LX1, LX1 + 0.04, LOFT_Y0 - 0.12, LOFT_Y + 0.02, LZ0 - 0.04, Z1),
                                                 box(bm, X0, STAIR_X0, LOFT_Y0 - 0.12, LOFT_Y + 0.02, LZ0 - 0.04, LZ0),
                                                 box(bm, STAIR_X1, LX1 + 0.04, LOFT_Y0 - 0.12, LOFT_Y + 0.02, LZ0 - 0.04, LZ0)])
    panel("Sign_Deli", "Sign_Paint", (LX1 + 0.045, LOFT_Y0 + 0.12, -15.0), "+x", 3.2, 0.36, sign_uv(128, 256, 0, 1024))
    panel("Sign_Deli_N", "Sign_Paint", ((X0 + STAIR_X0) / 2, LOFT_Y0 + 0.12, LZ0 - 0.045), "-z", 2.4, 0.27, sign_uv(128, 256, 0, 1024))
    # the posts under its edge: panelled wood with a brass band and a moulded cap and base
    for n, b in BOX.items():
        if not n.startswith("Loft_Post"):
            continue
        x0, x1, z0, z1 = b["min"][0], b["max"][0], b["min"][2], b["max"][2]
        part(f"{n}_shaft", "Wall_Panel", lambda bm, x0=x0, x1=x1, z0=z0, z1=z1: box(bm, x0 + 0.02, x1 - 0.02, 0.0, LOFT_Y0, z0 + 0.02, z1 - 0.02))
        part(f"{n}_mould", "Trim_Wood", lambda bm, x0=x0, x1=x1, z0=z0, z1=z1: [box(bm, x0, x1, 0.0, 0.22, z0, z1), box(bm, x0, x1, LOFT_Y0 - 0.2, LOFT_Y0, z0, z1)])
        part(f"{n}_brass", "Brass", lambda bm, x0=x0, x1=x1, z0=z0, z1=z1: box(bm, x0 + 0.005, x1 - 0.005, 1.1, 1.16, z0 + 0.005, z1 - 0.005))
    # the balustrade: turned balusters, a handrail and a bottom rail inside each rail collider
    for n, b in BOX.items():
        if not n.startswith("Loft_Rail"):
            continue
        x0, x1, z0, z1, y0, y1 = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["min"][1], b["max"][1]
        along_x = (x1 - x0) > (z1 - z0)
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2

        def rail(bm, x0=x0, x1=x1, z0=z0, z1=z1, y0=y0, y1=y1):
            box(bm, x0, x1, y1 - 0.06, y1, z0 + 0.005, z1 - 0.005) if along_x else box(bm, x0 + 0.005, x1 - 0.005, y1 - 0.06, y1, z0, z1)
            box(bm, x0, x1, y0, y0 + 0.06, z0 + 0.02, z1 - 0.02) if along_x else box(bm, x0 + 0.02, x1 - 0.02, y0, y0 + 0.06, z0, z1)
        part(f"{n}_rails", "Wood_Furniture", rail)

        def balusters(bm, x0=x0, x1=x1, z0=z0, z1=z1, y0=y0, y1=y1, cx=cx, cz=cz, along_x=along_x):
            lo, hi = (x0, x1) if along_x else (z0, z1)
            k = max(1, int((hi - lo) / 0.16))
            for i in range(k + 1):
                a = lo + 0.04 + (hi - lo - 0.08) * i / k
                p0 = (a, y0 + 0.06, cz) if along_x else (cx, y0 + 0.06, a)
                p1 = (a, y1 - 0.06, cz) if along_x else (cx, y1 - 0.06, a)
                cyl(bm, p0, p1, 0.022, 0.018, 8)
        part(f"{n}_balusters", "Wood_Furniture", balusters, smooth=True, sharp_deg=50)
    # newel posts where the rails end
    part("Loft_Newels", "Wood_Furniture", lambda bm: [box(bm, x - 0.05, x + 0.05, LOFT_Y, LOFT_Y + 1.12, z - 0.05, z + 0.05)
                                                      for x, z in ((-24.45, LZ0 + 0.05), (-23.15, LZ0 + 0.05), (LX1 - 0.05, LZ0 + 0.05), (LX1 - 0.05, Z1 - 0.05))])


def build_stairs():
    """Each step is a tread (wood, a carpet runner on it) and a riser board under it, both under 0.2 m tall (the layout check tests art taller than that
    for a collider standing on the floor; the steps' own colliders start in the air). Stringers and balusters are thin and passable: decor_."""
    steps = sorted((n, b) for n, b in BOX.items() if n.startswith("Step_loft_"))
    for n, b in steps:
        x0, x1, y0, y1, z0, z1 = b["min"][0], b["max"][0], b["min"][1], b["max"][1], b["min"][2], b["max"][2]
        part(f"Stair_{n}_tread", "Trim_Wood", lambda bm, b=b: box(bm, x0, x1, y1 - 0.05, y1 - 0.008, z0, z1))
        part(f"Stair_{n}_runner", "Floor_Carpet", lambda bm, b=b: box(bm, x0 + 0.18, x1 - 0.18, y1 - 0.008, y1, z0, z1), tile=2.4)
        part(f"Stair_{n}_body", "Wall_Panel", lambda bm, b=b: box(bm, x0 + 0.01, x1 - 0.01, y0 + 0.012, y1 - 0.05, z0, z1))
    xs0 = steps[0][1]["min"][0]
    xs1 = steps[0][1]["max"][0]
    zs0 = steps[0][1]["min"][2]
    zs1 = steps[-1][1]["max"][2]

    def stringers(bm):
        for x in (xs0 - 0.0, xs1 - 0.05):
            for zc, yc in (((zs0, 0.0), (zs1, LOFT_Y)),):
                pass
            # a sloped beam: a quad strip from the first step's foot to the loft's edge
            p = [(x, -0.0, zs0), (x, 0.26, zs0), (x, LOFT_Y + 0.02, zs1), (x, LOFT_Y - 0.28, zs1)]
            q = [(x + 0.05, v[1], v[2]) for v in p]
            vs = [bm.verts.new(B(v)) for v in p + q]
            for f in ((0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)):
                bm.faces.new([vs[i] for i in f])
    part("decor_stair_stringers", "Wall_Panel", stringers)

    def balust(bm):
        x = xs1 - 0.025
        n = len(steps)
        for i, (nm, b) in enumerate(steps):
            zc = (b["min"][2] + b["max"][2]) / 2
            cyl(bm, (x, b["max"][1], zc), (x, b["max"][1] + 0.9, zc), 0.018, 0.015, 8)
        cyl(bm, (x, steps[0][1]["max"][1] + 0.92, zs0 + 0.15), (x, LOFT_Y + 0.92, zs1), 0.03, 0.03, 10)
        cyl(bm, (x, 0.0, zs0 + 0.05), (x, 1.15, zs0 + 0.05), 0.05, 0.05, 8)               # the newel at the foot
    part("decor_stair_balusters", "Wood_Furniture", balust, smooth=True, sharp_deg=50)


# ---------------------------------------------------------------- furniture and fittings
CAN_W = 160.0      # each coffer's downlight
CHAND_W = 1400.0   # the chandelier
SCONCE_W = 14.0    # each sconce arm
LIGHTS = []        # (kind, game pos, watts, colour, radius, aim (game dir) or None, cone deg)
WARM = (1.0, 0.76, 0.50)


def lamp_light(pos, watts, radius=0.08, kind="POINT", aim=None, cone=120.0, color=WARM):
    LIGHTS.append((kind, pos, watts, color, radius, aim, cone))


def build_reception():
    b = BOX["Reception_Desk"]
    x0, x1, z0, z1, h = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]

    def body(bm):
        box(bm, x0 + 0.02, x1 - 0.02, 0.1, h - 0.05, z0 + 0.02, z1 - 0.02)
        k = 4
        w = (x1 - x0) / k
        for i in range(k):                                     # raised fields on the front (facing +z, the hall)
            box(bm, x0 + i * w + 0.1, x0 + (i + 1) * w - 0.1, 0.25, h - 0.2, z1 - 0.02, z1)
    part("Reception_Body", "Wood_Furniture", body)
    part("Reception_Plinth", "Trim_Wood", lambda bm: box(bm, x0, x1, 0.0, 0.1, z0, z1))
    part("Reception_Top", "Marble_Top", lambda bm: box(bm, x0 - 0.03, x1 + 0.03, h - 0.05, h, z0 - 0.03, z1 + 0.03))
    part("Reception_Brass", "Brass", lambda bm: [box(bm, x0 + 0.01, x1 - 0.01, 0.1, 0.14, z1 - 0.025, z1 + 0.004),
                                                 box(bm, x0 + 0.01, x1 - 0.01, h - 0.08, h - 0.05, z1 - 0.025, z1 + 0.004)])
    # on the desk: the bell, a banker's lamp, the register and its pen, the RING card
    cx = (x0 + x1) / 2
    part("Reception_Bell", "Brass", lambda bm: [cyl(bm, (cx + 0.5, h, z1 - 0.18), (cx + 0.5, h + 0.012, z1 - 0.18), 0.05, 0.05, 16),
                                                sphere(bm, (cx + 0.5, h + 0.012, z1 - 0.18), 0.045, 14, 0.8),
                                                cyl(bm, (cx + 0.5, h + 0.05, z1 - 0.18), (cx + 0.5, h + 0.065, z1 - 0.18), 0.006, 0.006, 6)], smooth=True)
    lx, lz = x0 + 0.45, z0 + 0.25
    part("Reception_Lamp_Base", "Brass", lambda bm: [cyl(bm, (lx, h, lz), (lx, h + 0.025, lz), 0.08, 0.07, 16),
                                                     cyl(bm, (lx, h + 0.025, lz), (lx, h + 0.32, lz), 0.012, 0.012, 8)], smooth=True)
    p = Painter()
    p.add("lamp_green", lambda bm: cyl(bm, (lx - 0.16, h + 0.33, lz), (lx + 0.16, h + 0.33, lz), 0.07, 0.07, 12, cap=False))
    p.add("ledger", box, cx - 0.4, cx + 0.05, h, h + 0.035, z1 - 0.42, z1 - 0.12)
    p.add("paper", box, cx - 0.38, cx + 0.03, h + 0.035, h + 0.04, z1 - 0.41, z1 - 0.13)
    p.add("key_black", lambda bm: cyl(bm, (cx + 0.15, h, z1 - 0.3), (cx + 0.15, h + 0.06, z1 - 0.3), 0.025, 0.02, 8))
    p.done("Reception_Things", smooth=False)
    part("Reception_Lamp_Glow", "Lamp_Emit", lambda bm: cyl(bm, (lx - 0.14, h + 0.29, lz), (lx + 0.14, h + 0.29, lz), 0.03, 0.03, 8))
    lamp_light((lx, h + 0.26, lz), 18.0, 0.04)
    panel("Reception_Card", "Sign_Paint", (cx + 0.28, h + 0.06, z1 - 0.12), "+z", 0.2, 0.06, sign_uv(640, 768, 512, 1024))
    # the key board behind: a cabinet with the pigeonholes' picture on its face
    k = BOX["Key_Board"]
    kx0, kx1, ky1, kz1 = k["min"][0], k["max"][0], k["max"][1], k["max"][2]
    part("Key_Cabinet", "Wood_Furniture", lambda bm: [box(bm, kx0, kx1, 0.0, 0.9, Z0, kz1), box(bm, kx0, kx1, ky1 - 0.12, ky1, Z0, kz1 + 0.03),
                                                     box(bm, kx0, kx0 + 0.06, 0.9, ky1, Z0, kz1), box(bm, kx1 - 0.06, kx1, 0.9, ky1, Z0, kz1),
                                                     box(bm, kx0 - 0.02, kx1 + 0.02, 0.88, 0.92, Z0, kz1 + 0.03)])
    panel("Key_Face", "Key_Board", ((kx0 + kx1) / 2, (0.92 + ky1 - 0.12) / 2, kz1 - 0.06), "+z", kx1 - kx0 - 0.12, ky1 - 0.12 - 0.92)
    # over it: the RECEPTION sign and three clocks with their cities
    panel("Sign_Reception", "Sign_Paint", ((kx0 + kx1) / 2, 2.72, Z0 + 0.03), "+z", 3.4, 0.42, sign_uv(0, 128, 0, 1024))
    part("Sign_Reception_Board", "Trim_Wood", lambda bm: wall_box(bm, "+z", (kx0 + kx1) / 2 - 1.75, (kx0 + kx1) / 2 + 1.75, 2.49, 2.95, 0.0, 0.028))
    for i, (label, hour) in enumerate(CLOCKS):
        cx2 = (kx0 + kx1) / 2 + (i - 1) * 1.25
        c0 = 512 + i * 170
        bmf = bmesh.new()
        uvl = bmf.loops.layers.uv.new("UVMap")
        seg = 32
        cy, r = 3.5, 0.26
        ctr = bmf.verts.new(B((cx2, cy, Z0 + 0.05)))
        rim = [bmf.verts.new(B((cx2 + r * math.sin(2 * math.pi * j / seg), cy + r * math.cos(2 * math.pi * j / seg), Z0 + 0.05))) for j in range(seg)]
        for j in range(seg):
            f = bmf.faces.new((ctr, rim[(j + 1) % seg], rim[j]))
            for lp in f.loops:
                gx, gy = lp.vert.co.x, lp.vert.co.z
                u = (c0 + 80 + (gx - cx2) / r * 80) / 1024
                v = 1 - (768 + 80 - (gy - cy) / r * 80) / 1024
                lp[uvl].uv = (u, v)
        face_toward(bmf, (0, 0, 1))
        finish(f"Clock_Face_{i}", bmf, "Sign_Paint", keep_uv=True, recalc=False)
        part(f"Clock_Rim_{i}", "Brass", lambda bm, cx2=cx2: [ring(bm, (cx2, 3.5), 0.29, 0.035, 0, 0) if False else
                                                             cyl(bm, (cx2, 3.5, Z0), (cx2, 3.5, Z0 + 0.07), 0.295, 0.295, 32, cap=False),
                                                             cyl(bm, (cx2, 3.5, Z0 + 0.07), (cx2, 3.5, Z0 + 0.075), 0.295, 0.26, 32, cap=False)], smooth=True)
        panel(f"Clock_Label_{i}", "Sign_Paint", (cx2, 3.08, Z0 + 0.025), "+z", 0.5, 0.3, sign_uv(928, 1024, c0, c0 + 160))


def chair_bentwood(p, x, z, face_z, y0=0.0):
    """A bistro chair in its 0.44 m square: a round seat, four legs, a hoop back on the side away from `face_z`."""
    def legs(bm):
        for dx in (-0.16, 0.16):
            for dz in (-0.16, 0.16):
                cyl(bm, (x + dx, y0, z + dz), (x + dx * 0.8, y0 + 0.45, z + dz * 0.8), 0.014, 0.014, 6)
        bz = z - 0.17 * face_z
        for dx in (-0.15, 0.15):
            cyl(bm, (x + dx, y0 + 0.45, bz), (x + dx, y0 + 0.88, bz), 0.012, 0.012, 6)
        cyl(bm, (x - 0.16, y0 + 0.86, bz), (x + 0.16, y0 + 0.86, bz), 0.016, 0.016, 6)
        cyl(bm, (x - 0.16, y0 + 0.70, bz), (x + 0.16, y0 + 0.70, bz), 0.012, 0.012, 6)
        cyl(bm, (x, y0 + 0.43, z), (x, y0 + 0.46, z), 0.2, 0.2, 18)
    return legs


def build_deli():
    c = BOX["Deli_Counter"]
    x0, x1, z0, z1, h = c["min"][0], c["max"][0], c["min"][2], c["max"][2], c["max"][1]
    part("Deli_Counter_Body", "Wood_Furniture", lambda bm: [box(bm, x0 + 0.02, x1, 0.12, h - 0.04, z0 + 0.02, z1 - 0.02)])
    part("Deli_Counter_Plinth", "Trim_Wood", lambda bm: box(bm, x0 + 0.04, x1, 0.0, 0.12, z0 + 0.04, z1 - 0.04))
    part("Deli_Counter_Top", "Marble_Top", lambda bm: box(bm, x0, x1 + 0.03, h - 0.04, h, z0, z1))
    # the glass case on top: a brass frame, glass, trays of food
    gx0, gx1 = x0 + 0.06, x1 - 0.02
    part("Deli_Case_Frame", "Brass", lambda bm: [box(bm, gx0, gx1, h + 0.34, h + 0.36, z0 + 0.1, z1 - 0.1)]
         + [box(bm, gx1 - 0.02, gx1, h, h + 0.34, z, z + 0.02) for z in np.linspace(z0 + 0.1, z1 - 0.12, 5)])
    part("Deli_Case_Glass", "Glass_Clear", lambda bm: [box(bm, gx1 - 0.012, gx1 - 0.004, h, h + 0.34, z0 + 0.1, z1 - 0.1),
                                                       box(bm, gx0, gx1, h + 0.33, h + 0.34, z0 + 0.1, z1 - 0.1)])
    p = Painter()
    rng = np.random.default_rng(3)
    foods = ["salami", "cheese", "olive", "ham", "bread", "cheese", "salami", "olive"]
    zz = np.linspace(z0 + 0.2, z1 - 0.2, len(foods) + 1)
    for i, f in enumerate(foods):
        za, zb = zz[i] + 0.03, zz[i + 1] - 0.03
        p.add("tray", box, gx0 + 0.04, gx1 - 0.06, h, h + 0.02, za, zb)
        for j in range(4):
            px = gx0 + 0.1 + (gx1 - gx0 - 0.25) * rng.random()
            pz = za + 0.08 + (zb - za - 0.16) * rng.random()
            p.add(f, sphere, (px, h + 0.05, pz), 0.045 + 0.02 * rng.random(), 8, 0.6)
    p.done("Deli_Case_Food")
    p = Painter()
    # the back shelves on the west wall: jars, tins and bottles
    s = BOX["Deli_Shelf"]
    sx0, sx1, sz0, sz1, sh = s["min"][0], s["max"][0], s["min"][2], s["max"][2], s["max"][1]

    def shelf(bm):
        box(bm, sx0, sx1, 0.0, 0.9, sz0, sz1)
        box(bm, sx0, sx0 + 0.02, 0.9, sh, sz0, sz1)
        for y in (1.3, 1.75, 2.2):
            box(bm, sx0, sx1, y - 0.03, y, sz0, sz1)
        box(bm, sx0, sx1, sh - 0.06, sh, sz0, sz1)
        for z in np.linspace(sz0, sz1 - 0.03, 5):
            box(bm, sx0, sx1, 0.9, sh, z, z + 0.03)
    part("Deli_Shelf_Wood", "Wood_Furniture", shelf)
    p.add("paper", box, sx0 + 0.02, sx1 - 0.01, 0.9, 0.92, sz0 + 0.03, sz1 - 0.03)
    for y in (0.92, 1.3, 1.75):
        z = sz0 + 0.1
        while z < sz1 - 0.12:
            k = rng.random()
            px = (sx0 + sx1) / 2 + 0.02
            if k < 0.45:
                hh = 0.16 + 0.06 * rng.random()
                p.add("jar_glass", cyl, (px, y, z), (px, y + hh, z), 0.055, 0.055, 10)
                p.add("lid_red" if rng.random() < 0.6 else "tin_yellow", cyl, (px, y + hh, z), (px, y + hh + 0.025, z), 0.057, 0.057, 10)
                z += 0.14
            elif k < 0.75:
                hh = 0.1 + 0.03 * rng.random()
                p.add("tin_blue" if rng.random() < 0.5 else "tin_yellow", cyl, (px, y, z), (px, y + hh, z), 0.04, 0.04, 10)
                z += 0.1
            elif k < 0.92:
                p.add("bottle_green" if rng.random() < 0.5 else "bottle_brown", cyl, (px, y, z), (px, y + 0.24, z), 0.035, 0.035, 8)
                p.add("bottle_green", cyl, (px, y + 0.24, z), (px, y + 0.33, z), 0.035, 0.012, 8)
                z += 0.09
            else:
                z += 0.12
    p.done("Deli_Shelf_Goods")
    # two bistro tables, their chairs
    for n in ("Deli_Table", "Deli_Table_2"):
        p = Painter()
        t = BOX[n]
        cx, cz, th = (t["min"][0] + t["max"][0]) / 2, (t["min"][2] + t["max"][2]) / 2, t["max"][1]
        part(f"{n}_top", "Marble_Top", lambda bm, cx=cx, cz=cz, th=th: cyl(bm, (cx, th - 0.03, cz), (cx, th, cz), 0.39, 0.39, 32), smooth=True, sharp_deg=60)
        part(f"{n}_base", "Metal_Dark", lambda bm, cx=cx, cz=cz, th=th: [cyl(bm, (cx - sx * 0.36, 0.015, cz - sz * 0.36), (cx + sx * 0.36, 0.015, cz + sz * 0.36), 0.018, 0.018, 8)
                                                                         for sx, sz in ((1, 1), (1, -1))]
             + [cyl(bm, (cx, 0.0, cz), (cx, 0.05, cz), 0.07, 0.05, 12), cyl(bm, (cx, 0.03, cz), (cx, th - 0.03, cz), 0.03, 0.03, 10)], smooth=True)
        p.add("vase", cyl, (cx + 0.1, th, cz), (cx + 0.1, th + 0.14, cz), 0.03, 0.04, 8)
        p.add("flower", sphere, (cx + 0.1, th + 0.17, cz), 0.035, 8)
        p.done(f"{n}_Vase")
    for n, b in BOX.items():
        if n.startswith("Deli_Chair"):
            cx, cz = (b["min"][0] + b["max"][0]) / 2, (b["min"][2] + b["max"][2]) / 2
            tz = min((-19.0, -16.0), key=lambda v: abs(v - cz))
            part(f"{n}_frame", "Wood_Furniture", chair_bentwood(None, cx, cz, 1 if tz > cz else -1), smooth=True, sharp_deg=50)
    # the menu board hung from the loft, and pendants over the counter and the tables
    mz = (z0 + z1) / 2
    panel("Deli_Menu", "Sign_Paint", (-25.75, 2.32, mz), "+x", 1.6, 0.8, sign_uv(768, 1024, 0, 512))
    part("Deli_Menu_Back", "Trim_Wood", lambda bm: [box(bm, -25.80, -25.76, 1.88, 2.76, mz - 0.86, mz + 0.86)])
    pend = [(x0 + 0.3, z) for z in (-19.4, -17.25, -15.1)] + [(-23.0, -19.0), (-23.0, -16.0)]
    pp = Painter()
    for (px, pz) in pend:
        pp.add("cord", cyl, (px, LOFT_Y0, pz), (px, 2.3, pz), 0.005, 0.005, 6)
        pp.add("enamel_cream", lambda bm, px=px, pz=pz: cyl(bm, (px, 2.15, pz), (px, 2.3, pz), 0.17, 0.04, 16, cap=False))
        lamp_light((px, 2.13, pz), 40.0, 0.05)
    pp.done("Deli_Pendants", smooth=True)
    part("Deli_Pendant_Bulbs", "Lamp_Emit", lambda bm: [sphere(bm, (px, 2.15, pz), 0.045, 10) for px, pz in pend], smooth=True)


def build_shops():
    # the partitions: panelled wood both sides
    for n, b in BOX.items():
        if n.startswith("Shop_Partition"):
            x0, x1, y1, z0, z1 = b["min"][0], b["max"][0], b["max"][1], b["min"][2], b["max"][2]
            part(f"{n}_wall", "Wall_Panel", lambda bm, x0=x0, x1=x1, y1=y1, z0=z0, z1=z1: box(bm, x0, x1, 0.0, y1, z0, z1))
            part(f"{n}_trim", "Trim_Wood", lambda bm, x0=x0, x1=x1, y1=y1, z0=z0, z1=z1: [box(bm, x0 - 0.015, x1 + 0.015, 0.0, 0.18, z0, z1),
                                                                                            box(bm, x0 - 0.02, x1 + 0.02, 0.0, y1, z0 - 0.02, z0 + 0.06)])
    # a canopy over both shops, their fascia signs and downlights
    sx0, sx1 = BOX["Shop_Partition"]["min"][0], X1
    cz0 = BOX["Shop_Partition"]["min"][2]
    part("Shop_Canopy", "Ceiling_Plaster", lambda bm: box(bm, sx0 - 0.1, sx1, 3.0, 3.12, cz0 - 0.1, Z1))
    part("Shop_Fascia", "Trim_Wood", lambda bm: [box(bm, sx0 - 0.12, sx1, 2.62, 3.16, cz0 - 0.16, cz0 - 0.1), box(bm, sx0 - 0.14, sx1, 3.12, 3.18, cz0 - 0.2, Z1)])
    x2 = BOX["Shop_Partition_2"]["min"][0]
    panel("Sign_Shop_1", "Sign_Paint", ((sx0 + x2) / 2 + 0.1, 2.89, cz0 - 0.165), "+z" if False else "-z", 3.6, 0.42, sign_uv(256, 384, 0, 1024))
    panel("Sign_Shop_2", "Sign_Paint", ((x2 + sx1) / 2, 2.89, cz0 - 0.165), "-z", 4.2, 0.42, sign_uv(384, 512, 0, 1024))
    # the counters
    a = BOX["Shop_A_Counter"]
    part("Shop_A_Body", "Wood_Furniture", lambda bm: box(bm, a["min"][0], a["max"][0], 0.0, a["max"][1] - 0.04, a["min"][2], a["max"][2]))
    part("Shop_A_Top", "Marble_Top", lambda bm: box(bm, a["min"][0] - 0.02, a["max"][0] + 0.02, a["max"][1] - 0.04, a["max"][1], a["min"][2] - 0.02, a["max"][2]))
    bb = BOX["Shop_B_Counter"]
    part("Shop_B_Body", "Wood_Furniture", lambda bm: box(bm, bb["min"][0], bb["max"][0], 0.0, 0.85, bb["min"][2], bb["max"][2]))
    part("Shop_B_Frame", "Brass", lambda bm: [box(bm, bb["min"][0], bb["max"][0], 0.85, 0.88, bb["min"][2], bb["max"][2]),
                                              box(bm, bb["min"][0], bb["max"][0], bb["max"][1] - 0.02, bb["max"][1], bb["min"][2], bb["max"][2])]
         + [box(bm, x, x + 0.02, 0.88, bb["max"][1], bb["min"][2], bb["min"][2] + 0.02) for x in np.linspace(bb["min"][0], bb["max"][0] - 0.02, 4)])
    part("Shop_B_Glass", "Glass_Clear", lambda bm: [box(bm, bb["min"][0], bb["max"][0], 0.88, bb["max"][1] - 0.02, bb["min"][2], bb["min"][2] + 0.008),
                                                    box(bm, bb["min"][0], bb["max"][0], bb["max"][1] - 0.03, bb["max"][1] - 0.02, bb["min"][2], bb["max"][2])])
    p = Painter()
    rng = np.random.default_rng(9)
    ay = a["max"][1]
    p.add("till", box, a["min"][0] + 0.3, a["min"][0] + 0.75, ay, ay + 0.22, a["min"][2] + 0.08, a["max"][2] - 0.08)
    for i in range(4):                                                                # newspapers in stacks
        px = a["min"][0] + 1.0 + i * 0.36
        hh = 0.03 + 0.05 * rng.random()
        p.add("newsprint", box, px, px + 0.3, ay, ay + hh, a["min"][2] + 0.06, a["max"][2] - 0.06)
        p.add("paper", box, px + 0.01, px + 0.29, ay + hh, ay + hh + 0.004, a["min"][2] + 0.08, a["max"][2] - 0.08)
    p.done("Shop_A_Things")
    p = Painter()
    for i in range(6):                                                                # boxes and cards in the glass counter
        px = bb["min"][0] + 0.2 + i * 0.55
        p.add(["box_pink", "box_teal", "card_yellow", "card_blue", "box_white", "box_pink"][i], box, px, px + 0.35, 0.88, 0.88 + 0.06 + 0.05 * rng.random(),
              bb["min"][2] + 0.1, bb["max"][2] - 0.1)
    # the back shelves: books in shop 1, boxes and bottles in shop 2
    p.done("Shop_B_Things")
    for n, kind in (("Shop_Shelf", "books"), ("Shop_Shelf_2", "goods")):
        p = Painter()
        s = BOX[n]
        x0, x1, z0, h = s["min"][0], s["max"][0], s["min"][2], s["max"][1]
        levels = [0.08, 0.5, 0.92, 1.34, 1.76]

        def carcass(bm, x0=x0, x1=x1, z0=z0, h=h):
            box(bm, x0, x1, 0.0, 0.08, z0, Z1)
            box(bm, x0, x1, h - 0.06, h, z0, Z1)
            box(bm, x0, x1, 0.0, h, Z1 - 0.02, Z1)
            for y in levels[1:]:
                box(bm, x0, x1, y - 0.025, y, z0, Z1)
            for x in np.linspace(x0, x1 - 0.03, 4):
                box(bm, x, x + 0.03, 0.0, h, z0, Z1)
        part(f"{n}_Carcass", "Wood_Furniture", carcass)
        for y in levels:
            x = x0 + 0.04
            while x < x1 - 0.1:
                if kind == "books":
                    w = 0.025 + 0.03 * rng.random()
                    hh = min(0.36, 0.2 + 0.14 * rng.random())
                    if rng.random() < 0.06:
                        x += 0.1
                        continue
                    key = ["book_red", "book_green", "book_blue", "book_tan", "book_black", "book_ochre", "book_cream", "book_plum"][int(rng.integers(8))]
                    p.add(key, box, x, x + w, y, y + hh, z0 + 0.05 + 0.04 * rng.random(), Z1 - 0.03)
                    x += w + 0.002
                else:
                    k = rng.random()
                    if k < 0.5:
                        w = 0.14 + 0.1 * rng.random()
                        p.add(["box_pink", "box_teal", "box_white", "card_yellow"][int(rng.integers(4))], box, x, x + w, y, y + 0.1 + 0.15 * rng.random(), z0 + 0.06, Z1 - 0.04)
                        x += w + 0.03
                    elif k < 0.85:
                        p.add(["bottle_green", "bottle_brown"][int(rng.integers(2))], cyl, (x + 0.04, y, z0 + 0.17), (x + 0.04, y + 0.25, z0 + 0.17), 0.035, 0.035, 8)
                        x += 0.1
                    else:
                        x += 0.15
        p.done(f"{n}_Goods")
    lens = []
    for x in np.linspace(sx0 + 1.0, sx1 - 1.0, 5):
        lens.append((float(x), cz0 + 1.4))
        lamp_light((float(x), 2.98, cz0 + 1.4), 45.0, 0.05, kind="SPOT", aim=(0, -1, 0), cone=110)
    part("Shop_Downlights", "Lamp_Emit", lambda bm: [cyl(bm, (x, 2.985, z), (x, 3.0, z), 0.07, 0.07, 14) for x, z in lens])


def build_sofas():
    tpl = load_model(MODELS / "ph-sofa-01/Sofa_01_1k.gltf")
    lo, hi = template_bounds(tpl)
    mats = []
    for n in ("Sofa", "Sofa_2"):
        b = BOX[n]
        cz = (b["min"][2] + b["max"][2]) / 2
        faces_south = cz < -19.0                       # the north sofa looks south, the south one north: both look into the aisle
        place(tpl, {"Sofa_01": ("Sofa_Fabric", f"{n}_Model")}, [fit_matrix(lo, hi, b, 0.0 if faces_south else math.pi)])
    # the coffee tables in front of them, a lamp on each
    for n in ("Coffee_Table", "Coffee_Table_2"):
        b = BOX[n]
        x0, x1, z0, z1, h = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]
        part(f"{n}_top", "Marble_Top", lambda bm, b=b: box(bm, x0, x1, h - 0.04, h, z0, z1))
        part(f"{n}_frame", "Wood_Furniture", lambda bm, b=b: [box(bm, x0 + 0.03, x1 - 0.03, h - 0.1, h - 0.04, z0 + 0.03, z1 - 0.03)]
             + [box(bm, x, x + 0.05, 0.0, h - 0.1, z, z + 0.05) for x in (x0 + 0.04, x1 - 0.09) for z in (z0 + 0.04, z1 - 0.09)])
        lx, lz = x1 - 0.2, (z0 + z1) / 2
        part(f"{n}_lamp", "Brass", lambda bm, lx=lx, lz=lz, h=h: [cyl(bm, (lx, h, lz), (lx, h + 0.03, lz), 0.07, 0.07, 12),
                                                                  sphere(bm, (lx, h + 0.12, lz), 0.07, 12, 1.2), cyl(bm, (lx, h + 0.18, lz), (lx, h + 0.36, lz), 0.01, 0.01, 6)],
             smooth=True)
        part(f"{n}_shade", "Lamp_Emit", lambda bm, lx=lx, lz=lz, h=h: cyl(bm, (lx, h + 0.3, lz), (lx, h + 0.5, lz), 0.17, 0.11, 16, cap=False), smooth=True)
        lamp_light((lx, h + 0.4, lz), 30.0, 0.08)


def build_loft_furniture():
    tpl = load_model(MODELS / "ph-armchair-01/ArmChair_01_1k.gltf")
    lo, hi = template_bounds(tpl)
    for n in ("Loft_Armchair", "Loft_Armchair_2"):                                   # facing east, toward the rail
        place(tpl, {"Armchair_01": ("Armchair_Fabric", f"{n}_Model")}, [fit_matrix(lo, hi, BOX[n], math.pi / 2)])
    t = BOX["Loft_Table"]
    cx, cz, th = (t["min"][0] + t["max"][0]) / 2, (t["min"][2] + t["max"][2]) / 2, t["max"][1]
    part("Loft_Table_Wood", "Wood_Furniture", lambda bm: [cyl(bm, (cx, th - 0.03, cz), (cx, th, cz), 0.3, 0.3, 24),
                                                         cyl(bm, (cx, LOFT_Y, cz), (cx, th - 0.03, cz), 0.03, 0.03, 8),
                                                         cyl(bm, (cx, LOFT_Y, cz), (cx, LOFT_Y + 0.03, cz), 0.2, 0.18, 16)], smooth=True, sharp_deg=50)
    part("Loft_Table_Lamp", "Brass", lambda bm: [cyl(bm, (cx, th, cz), (cx, th + 0.35, cz), 0.012, 0.012, 6), cyl(bm, (cx, th, cz), (cx, th + 0.02, cz), 0.07, 0.07, 12)])
    part("Loft_Table_Shade", "Lamp_Emit", lambda bm: cyl(bm, (cx, th + 0.3, cz), (cx, th + 0.48, cz), 0.16, 0.1, 16, cap=False))
    lamp_light((cx, th + 0.38, cz), 30.0, 0.08)
    p = Painter()
    p.add("rug", box, -27.6, -24.0, LOFT_Y, LOFT_Y + 0.008, -19.4, -13.2)
    p.done("decor_loft_rug")


# ---------------------------------------------------------------- plants (procedural: no alpha cards)
def leaf_poly(bm, base, direction, side, length, width, droop=0.25, n=6):
    """A leaf: a lens-shaped strip from `base` along `direction` (game vector), widest a third of the way, bending down, two rows of quads."""
    d = Vector(direction).normalized()
    s = Vector(side).normalized()
    up = d.cross(s).normalized()
    if up.y < 0:
        up = -up
    mid, left, right = [], [], []
    for i in range(n + 1):
        t = i / n
        w = width * math.sin(math.pi * min(1.0, t * 1.15)) ** 0.8
        p = Vector(base) + d * (length * t) - Vector((0, 1, 0)) * (droop * length * t * t)
        mid.append(bm.verts.new(B(p + up * 0.012 * math.sin(math.pi * t))))
        left.append(bm.verts.new(B(p + s * w)))
        right.append(bm.verts.new(B(p - s * w)))
    for i in range(n):
        bm.faces.new((left[i], left[i + 1], mid[i + 1], mid[i]))
        bm.faces.new((mid[i], mid[i + 1], right[i + 1], right[i]))


def plant(tag, cx, cz, y0, kind, height, rng, pot=True):
    """A potted plant: a glazed pot with a brass rim (solid, inside its collider), soil, stems (solid, thin) and leaves (decor_: passable)."""
    if pot:
        part(f"Plant_{tag}_pot", "Plant_Pot", lambda bm: cyl(bm, (cx, y0, cz), (cx, y0 + 0.5, cz), 0.2, 0.27, 20), smooth=True, sharp_deg=50)
        part(f"Plant_{tag}_rim", "Brass", lambda bm: cyl(bm, (cx, y0 + 0.47, cz), (cx, y0 + 0.53, cz), 0.285, 0.285, 20, cap=False), smooth=True)
    top = y0 + (0.48 if pot else 0.0)
    pt = Painter()
    if pot:
        pt.add("soil", cyl, (cx, top - 0.02, cz), (cx, top, cz), 0.26, 0.26, 16)
    bml = bmesh.new()
    if kind == "palm":
        n = int(8 + rng.integers(3))
        for i in range(n):
            th = 2 * math.pi * i / n + rng.random() * 0.4
            el = math.radians(48 + 26 * rng.random())
            L = height * (0.75 + 0.25 * rng.random())
            dh = Vector((math.cos(th), 0, math.sin(th)))
            base = Vector((cx, top, cz)) + dh * 0.03
            pt.add("stem", cyl, tuple(base), tuple(base + Vector((0, height * 0.35, 0)) + dh * 0.05), 0.012, 0.008, 5)
            start = base + Vector((0, height * 0.35, 0)) + dh * 0.05
            pts = []
            for k in range(13):
                t = k / 12
                pts.append(start + dh * (L * t * math.cos(el)) + Vector((0, 1, 0)) * (L * t * math.sin(el) - 0.55 * L * t * t))
            side = Vector((-dh.z, 0, dh.x))
            for k in range(2, 12):
                t = k / 12
                a, b2 = pts[k], pts[k + 1]
                along = (b2 - a).normalized()
                ll = 0.26 * L / 1.3 * (1 - abs(t - 0.45) * 1.2)
                for sg in (-1, 1):
                    dirn = (side * sg * 0.85 + along * 0.35 + Vector((0, -0.25, 0))).normalized()
                    leaf_poly(bml, tuple(a), tuple(dirn), tuple(along), ll, 0.022, 0.2, 3)
            for k in range(12):
                pass
    elif kind == "rubber":
        for sidx in range(3):
            ang = 2 * math.pi * sidx / 3 + rng.random()
            lean = Vector((math.cos(ang), 0, math.sin(ang))) * 0.06
            h = height * (0.75 + 0.25 * rng.random())
            p0 = Vector((cx, top, cz)) + lean * 0.5
            p1 = p0 + Vector((0, h, 0)) + lean * 2
            pt.add("stem", cyl, tuple(p0), tuple(p1), 0.012, 0.009, 6)
            k = 0
            y = 0.25
            while y < h:
                t = y / h
                at = p0 + (p1 - p0) * t
                a = ang + k * 2.4
                dh = Vector((math.cos(a), 0.55 + 0.4 * t, math.sin(a)))
                leaf_poly(bml, tuple(at), tuple(dh), (-math.sin(a), 0, math.cos(a)), 0.26 + 0.1 * (1 - t), 0.085 + 0.03 * (1 - t), 0.15, 4)
                y += 0.075
                k += 1
    else:   # "fern": a low arching clump
        for i in range(int(14 + rng.integers(6))):
            a = rng.random() * 2 * math.pi
            dh = Vector((math.cos(a), 0.9 + 0.6 * rng.random(), math.sin(a)))
            L = height * (0.7 + 0.3 * rng.random())
            leaf_poly(bml, (cx + 0.03 * math.cos(a), top, cz + 0.03 * math.sin(a)), tuple(dh), (-math.sin(a), 0, math.cos(a)), L, 0.05, 0.6, 5)
    pt.done(f"Plant_{tag}_stems")
    finish(f"decor_plant_{tag}_leaves", bml, "Plant_Leaf", smooth=True, sharp_deg=70, recalc=False)


def build_plants():
    rng = np.random.default_rng(21)
    kinds = {"Plant_1": ("palm", 1.5), "Plant_2": ("palm", 1.5), "Plant_3": ("rubber", 1.4), "Plant_4": ("rubber", 1.2), "Plant_5": ("rubber", 1.2),
             "Plant_6": ("fern", 0.6)}
    for n, (kind, h) in kinds.items():
        b = BOX[n]
        plant(n.split("_")[1], (b["min"][0] + b["max"][0]) / 2, (b["min"][2] + b["max"][2]) / 2, b["min"][1], kind, h, rng)
    # the planter in the middle of the hall: marble with a brass rim, a tall palm and ferns round it
    b = BOX["Planter"]
    x0, x1, z0, z1, h = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]
    part("Planter_Box", "Marble_Top", lambda bm: [box(bm, x0 + 0.03, x1 - 0.03, 0.12, h - 0.06, z0 + 0.03, z1 - 0.03)])
    part("Planter_Plinth", "Trim_Wood", lambda bm: box(bm, x0, x1, 0.0, 0.12, z0, z1))
    part("Planter_Rim", "Brass", lambda bm: [box(bm, x0, x1, h - 0.06, h, z0, z0 + 0.06), box(bm, x0, x1, h - 0.06, h, z1 - 0.06, z1),
                                             box(bm, x0, x0 + 0.06, h - 0.06, h, z0, z1), box(bm, x1 - 0.06, x1, h - 0.06, h, z0, z1)])
    pt = Painter()
    pt.add("soil", box, x0 + 0.06, x1 - 0.06, h - 0.1, h - 0.07, z0 + 0.06, z1 - 0.06)
    pt.done("Planter_Soil")
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    plant("planter_palm", cx, cz, h - 0.08, "palm", 2.4, rng, pot=False)
    for i, (dx, dz) in enumerate(((-0.6, -0.6), (0.6, -0.6), (-0.6, 0.6), (0.6, 0.6))):
        plant(f"planter_fern_{i}", cx + dx, cz + dz, h - 0.08, "fern", 0.55, rng, pot=False)


# ---------------------------------------------------------------- lights: the chandelier, sconces, the loft's downlights
def load_model(path):
    """Import a glTF once and keep its meshes as bmesh templates in Blender space, one per material, with the model's own UVs as UVMap."""
    before = (set(bpy.data.objects), set(bpy.data.meshes), set(bpy.data.materials), set(bpy.data.images))
    bpy.ops.import_scene.gltf(filepath=str(path))
    obs = [o for o in bpy.data.objects if o not in before[0]]
    parts = {}
    for o in obs:
        if o.type != "MESH":
            continue
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.transform(o.matrix_world)
        uv = bm.loops.layers.uv.active or bm.loops.layers.uv[0]
        for lay in [lay for lay in bm.loops.layers.uv if lay.name != uv.name]:
            bm.loops.layers.uv.remove(lay)
        for idx in sorted({f.material_index for f in bm.faces}):
            t = bm.copy()
            bmesh.ops.delete(t, geom=[f for f in t.faces if f.material_index != idx], context="FACES")
            for f in t.faces:
                f.material_index = 0
            parts.setdefault(o.data.materials[idx].name, []).append(t)
        bm.free()
    for o in obs:
        bpy.data.objects.remove(o)
    for kind, old in zip((bpy.data.meshes, bpy.data.materials, bpy.data.images), before[1:]):
        for d in [d for d in kind if d not in old]:
            kind.remove(d)
    return parts


def template_bounds(tpl):
    vs = [v.co for ts in tpl.values() for t in ts for v in t.verts]
    return Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs))), Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))


def fit_matrix(lo, hi, b, yaw):
    """Scale a model (bounds lo..hi, Blender) to fill collider b's footprint and height (2 cm inside), turned by `yaw` about the vertical."""
    w, d, h = hi.x - lo.x, hi.y - lo.y, hi.z - lo.z
    bw, bd = b["max"][0] - b["min"][0] - 0.04, b["max"][2] - b["min"][2] - 0.04
    if abs(math.sin(yaw)) > 0.5:
        bw, bd = bd, bw
    bh = b["max"][1] - b["min"][1]
    S = Matrix.Diagonal((bw / w, bd / d, bh / h, 1.0))
    c = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    tgt = B(((b["min"][0] + b["max"][0]) / 2, b["min"][1], (b["min"][2] + b["max"][2]) / 2))
    return Matrix.Translation(tgt) @ Matrix.Rotation(yaw, 4, "Z") @ S @ Matrix.Translation(-c)


def place(templates, mats_and_names, matrices, coll=None, split=None):
    out = []
    for key, (mat, name) in mats_and_names.items():
        bm = bmesh.new()
        for M in matrices:
            for t in templates[key]:
                me = bpy.data.meshes.new("tmp")
                t.to_mesh(me)
                me.uv_layers[0].name = "UVMap"
                n0 = len(bm.verts)
                bm.from_mesh(me)
                bpy.data.meshes.remove(me)
                bm.verts.ensure_lookup_table()
                bmesh.ops.transform(bm, matrix=M, verts=bm.verts[n0:])
        out.append(finish(name, bm, mat, coll, smooth=True, sharp_deg=60, keep_uv=True))
    return out


CHAIN = 0.9


def build_chandelier():
    """Poly Haven's Chandelier_02 (CC0) at twice its size over the planter, on a brass rod from the ceiling's medallion. Tired: two of its bulbs are dead
    (Bulb_Dead), the rest glow (Lamp_Emit); it hangs a degree off true."""
    tpl = load_model(CHANDELIER)
    lo, hi = template_bounds(tpl)
    sc = 2.0
    y_top = H - 0.12 - CHAIN
    M = (Matrix.Translation(B((CHAND[0], y_top, CHAND[1]))) @ Matrix.Rotation(math.radians(1.2), 4, "X") @ Matrix.Diagonal((sc, sc, sc, 1))
         @ Matrix.Translation(-Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, hi.z))))
    bulbs = []
    for t in tpl["Chandelier_02_bulb"]:                               # the bulbs as loose parts
        t.verts.ensure_lookup_table()
        seen = set()
        for v in t.verts:
            if v in seen:
                continue
            stack, comp = [v], set()
            while stack:
                u = stack.pop()
                if u in comp:
                    continue
                comp.add(u)
                stack.extend(e.other_vert(u) for e in u.link_edges)
            seen |= comp
            c = sum((u.co for u in comp), Vector()) / len(comp)
            faces = {f for u in comp for f in u.link_faces}
            bulbs.append((c, t, faces))
    bulbs.sort(key=lambda b: math.atan2(b[0].y, b[0].x))
    dead = {1, len(bulbs) // 2 + 1} if len(bulbs) > 3 else set()
    live_bm, dead_bm = bmesh.new(), bmesh.new()
    for i, (c, t, faces) in enumerate(bulbs):
        tgt = dead_bm if i in dead else live_bm
        t.faces.index_update()
        keep_idx = {f.index for f in faces}
        sub = t.copy()
        sub.faces.index_update()
        bmesh.ops.delete(sub, geom=[f for f in sub.faces if f.index not in keep_idx], context="FACES")
        me = bpy.data.meshes.new("tmp")
        sub.to_mesh(me)
        sub.free()
        n0 = len(tgt.verts)
        tgt.from_mesh(me)
        bpy.data.meshes.remove(me)
        tgt.verts.ensure_lookup_table()
        bmesh.ops.transform(tgt, matrix=M, verts=tgt.verts[n0:])
    place(tpl, {"Chandelier_02": ("Chandelier_Gilt", "Chandelier_Body")}, [M])
    if live_bm.verts:
        finish("Chandelier_Bulbs", live_bm, "Lamp_Emit", smooth=True, keep_uv=True)
    if dead_bm.verts:
        finish("Chandelier_Bulbs_Dead", dead_bm, "Bulb_Dead", smooth=True, keep_uv=True)
    ring_y = sum((b[0] for b in bulbs), Vector()) / max(1, len(bulbs))
    ring_g = M @ ring_y
    lamp_light((CHAND[0], ring_g.z, CHAND[1]), CHAND_W, 0.35)
    part("Chandelier_Rod", "Brass", lambda bm: cyl(bm, (CHAND[0], H - 0.12, CHAND[1]), (CHAND[0], y_top - 0.01, CHAND[1]), 0.015, 0.015, 8), smooth=True)
    print(f"CHANDELIER {len(bulbs)} bulbs ({len(dead)} dead), hangs from {y_top:.2f} to {y_top - (hi.z - lo.z) * sc:.2f} m")
    for ts in tpl.values():
        for t in ts:
            t.free()


SCONCES = []


def build_sconces():
    """Two-arm brass wall sconces with small linen shades (the shades glow: Lamp_Emit), at 2.85 m on the hall's walls and 4.3 m on the loft's."""
    spots = [("-x", z, 2.85) for z in (-25.6, -21.35, -16.65, -12.4)] + [("+z", x, 2.85) for x in (-24.5, -20.6, -13.4, -11.0)]
    spots += [("+x", z, 2.85) for z in (-27.0, -23.6)] + [("-z", -19.1, 2.85)] + [("+x", z, 4.35) for z in (-19.5, -11.5)] + [("-z", -24.5, 4.35)]
    bmb, bms = bmesh.new(), bmesh.new()
    for nm, a, y in spots:
        c = on_wall(nm, a, y, 0.0)
        nv = Vector(NORMAL[nm])
        rv = Vector(RIGHT[nm])
        cyl(bmb, c, tuple(Vector(c) + nv * 0.025), 0.07, 0.07, 14)
        for sg in (-1, 1):
            p0 = Vector(c) + nv * 0.02
            p1 = Vector(c) + nv * 0.15 + rv * 0.16 * sg + Vector((0, 0.05, 0))
            cyl(bmb, tuple(p0), tuple(p1), 0.008, 0.008, 6)
            cyl(bmb, tuple(p1 - Vector((0, 0.02, 0))), tuple(p1 + Vector((0, 0.05, 0))), 0.022, 0.018, 10)
            cyl(bms, tuple(p1 + Vector((0, 0.04, 0))), tuple(p1 + Vector((0, 0.18, 0))), 0.075, 0.045, 14, cap=False)
            SCONCES.append(tuple(p1 + Vector((0, 0.1, 0))))
            lamp_light(tuple(p1 + Vector((0, 0.1, 0))), SCONCE_W, 0.05)
    finish("Sconce_Brass", bmb, "Brass", smooth=True, sharp_deg=50)
    finish("Sconce_Shades", bms, "Lamp_Emit", smooth=True, sharp_deg=50)
    # the loft's soffit downlights over the back door and the deli's west side
    lens = [(-26.3, -12.2), (-23.6, -10.6), (-26.3, -21.2)]
    for x, z in lens:
        lamp_light((x, LOFT_Y0 - 0.02, z), 45.0, 0.05, kind="SPOT", aim=(0, -1, 0), cone=110)
    part("Loft_Downlights", "Lamp_Emit", lambda bm: [cyl(bm, (x, LOFT_Y0 - 0.012, z), (x, LOFT_Y0, z), 0.07, 0.07, 14) for x, z in lens])


def build_layout():
    """The layout objects, as the greybox names them: COL_ boxes (hidden), the empties (Link_, Arrive_, Marker_, Spot_). The leaves are in Doors."""
    for b in GB.boxes:
        if not b["col"]:
            continue
        me = bpy.data.meshes.new("COL_" + b["name"])
        bm = bmesh.new()
        cube(bm, b["min"], b["max"])
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("COL_" + b["name"], me)
        ob.display_type = "WIRE"
        ob.hide_render = True
        LAYOUT_C.objects.link(ob)
    for e in GB.empties:
        ob = bpy.data.objects.new(e["name"], None)
        ob.location = B(e["pos"])
        if e["face"]:
            ob.rotation_euler = (0, 0, math.atan2(e["face"][0], e["face"][1]))
        for k, v in e["props"].items():
            ob[k] = v
        ob.empty_display_size = 0.3
        LAYOUT_C.objects.link(ob)


# ---------------------------------------------------------------- lights, world, light sets
SUN_W = 14.0                   # the sun through the street windows (W/m2): low, from the east-south-east (a morning)
SUN_DIR = (-0.86, -0.36, -0.36)
SKY_COLOR = (0.56, 0.68, 0.92)
SKY_DAY = 10.0
NIGHT_SKY = (0.02, 0.025, 0.05)
NIGHT_STRENGTH = 1.0
STREET_W = 260.0              # each sodium street lamp's glow outside a window (an area light)
STREET_COLOR = (1.0, 0.60, 0.28)
PANE_DAY = (0.97, 0.98, 1.0)                     # the panes' lightmap texels, as a fraction of the map's white point
PANE_NIGHT = (0.40, 0.24, 0.11)


def add_lights():
    cols = {}
    for name in ("Lights_Lamps", "Lights_Day", "Lights_Night"):
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        cols[name] = c

    def light(coll, name, kind, pos, energy, color, size):
        d = bpy.data.lights.new(name, kind)
        d.energy, d.color = energy, color
        if kind != "SUN":
            d.shadow_soft_size = size
        ob = bpy.data.objects.new(name, d)
        ob.location = B(pos)
        cols[coll].objects.link(ob)
        return ob, d
    for i, (kind, pos, w, col, r, aim, cone) in enumerate(LIGHTS):
        ob, d = light("Lights_Lamps", f"Lamp_{i:02d}", kind, pos, w, col, r)
        if kind == "SPOT":
            d.spot_size, d.spot_blend = math.radians(cone), 0.6
            ob.rotation_euler = B(aim).to_track_quat("-Z", "Y").to_euler()
    ob, d = light("Lights_Day", "Sun", "SUN", (0, 20, 0), SUN_W, (1.0, 0.93, 0.82), 0.0)
    d.angle = math.radians(1.0)
    ob.rotation_euler = B(SUN_DIR).to_track_quat("-Z", "Y").to_euler()
    for i, (z0, z1) in enumerate(WIN_Z + [(FD_Z0, FD_Z1)]):
        zc = (z0 + z1) / 2
        ob, d = light("Lights_Night", f"Street_{i}", "AREA", (X1 + 3.5, 5.5, zc + (1.5 if i % 2 else -1.5)), STREET_W, STREET_COLOR, 0.0)
        d.shape, d.size, d.size_y = "RECTANGLE", 1.2, 1.2
        ob.rotation_euler = B((-0.8, -0.6, 0.0)).to_track_quat("-Z", "Y").to_euler()


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("Sky")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*SKY_COLOR, 1)
    bg.inputs["Strength"].default_value = SKY_DAY


def set_emit(mname, strength):
    m = bpy.data.materials.get(mname)
    if m:
        m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = strength


def apply_light_set(name):
    """day: the sun and the sky through the windows, and the lamps; night: the lamps and the street's sodium glow, a dark sky; export: as day (the
    toggled material at the strength the page switches on)."""
    day = name != "night"
    for c, on in (("Lights_Lamps", True), ("Lights_Day", day), ("Lights_Night", not day)):
        if c in bpy.data.collections:
            bpy.data.collections[c].hide_render = not on
    bg = bpy.context.scene.world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*(SKY_COLOR if day else NIGHT_SKY), 1)
    bg.inputs["Strength"].default_value = SKY_DAY if day else NIGHT_STRENGTH
    set_emit("Lamp_Emit", LAMP_EMIT)
    m = bpy.data.materials.get("Window_Glass")                      # the panes' glow in the stills (light passes them; exported at 0)
    if m:
        bsdf = m.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Emission Color"].default_value = (*((0.95, 0.97, 1.0) if day else STREET_COLOR), 1)
        bsdf.inputs["Emission Strength"].default_value = {"day": 3.0, "night": 0.35}.get(name, 0.0)


def ensure_marker():
    st = bpy.data.collections["Standins"]
    ob = bpy.data.objects.get("standin_arrival_marker")
    if ob is None:
        me = bpy.data.meshes.new("standin_arrival_marker")
        bm = bmesh.new()
        a = SPAWN
        cube(bm, (a[0] - 0.1, a[1], a[2] - 0.1), (a[0] + 0.1, a[1] + 0.2, a[2] + 0.1))
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("standin_arrival_marker", me)
        st.objects.link(ob)
    ob.hide_render = True
    return ob


def stage_axes():
    import struct
    ob = ensure_marker()
    bpy.ops.object.select_all(action="DESELECT")
    ob.hide_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    path = stage_work() / "axes_marker.glb"
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_yup=True, export_apply=True, export_materials="NONE")
    b = path.read_bytes()
    j = json.loads(b[20:20 + struct.unpack("<I", b[12:16])[0]])
    acc = j["accessors"][j["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    off = j["nodes"][0].get("translation", [0, 0, 0])
    centre = [(acc["min"][i] + acc["max"][i]) / 2 + off[i] for i in range(3)]
    want = [SPAWN[0], SPAWN[1] + 0.1, SPAWN[2]]
    print(f"AXES glTF centre {tuple(round(v, 3) for v in centre)}, game point {tuple(want)}")
    assert all(abs(centre[i] - want[i]) < 1e-4 for i in range(3)), "the exporter's axes disagree with (x, -z, y)"
    print("AXES PASS: game (x, y, z) = Blender (x, -z, y) = glTF (x, y, z)")


def build_all():
    global ART, STANDIN, DOORS_C, LAYOUT_C
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.lights, bpy.data.cameras):
        for d in list(coll):
            coll.remove(d)
    IMG_CACHE.clear()
    MATS.clear()
    TILES.clear()
    LIGHTS.clear()
    sc = bpy.context.scene
    ART, STANDIN, DOORS_C, LAYOUT_C = (bpy.data.collections.new(n) for n in ("Art", "Standins", "Doors", "Layout"))
    for c in (ART, STANDIN, DOORS_C, LAYOUT_C):
        sc.collection.children.link(c)
    make_materials(make_generated())
    build_floor()
    build_walls()
    build_wall_dressing()
    build_windows()
    build_ceiling()
    build_door_leaves()
    build_door_surrounds()
    build_loft()
    build_stairs()
    build_reception()
    build_deli()
    build_shops()
    build_sofas()
    build_loft_furniture()
    build_plants()
    build_chandelier()
    build_sconces()
    build_layout()
    add_lights()
    setup_world()
    apply_light_set("day")
    ensure_marker()
    LAYOUT_C.hide_render = True
    tris = sum(len(p.vertices) - 2 for o in ART.objects for p in o.data.polygons)
    print(f"ART {len(ART.objects)} objects, about {tris} triangles; {len(LIGHTS)} lamps")


# ---------------------------------------------------------------- layout file and the layout check
def stage_layout():
    import export_scene
    export_scene.write(SCENE, ROOT / f"world/{SCENE}.json")


def stage_check():
    import check_layout
    code = check_layout.main(["--scene", SCENE, "--collection", "Art"])
    print("CHECK_LAYOUT exit", code)


# ---------------------------------------------------------------- bake
GROUPS = [["Floor_Carpet", "Floor_Marble", "Floor_Tile", "Floor_Parquet", "Wall_Panel", "Wall_Paper", "Ceiling_Plaster", "Trim_Wood", "Trim_Paint"],
          ["Wood_Furniture", "Marble_Top", "Brass", "Metal_Dark", "Paint_Palette", "Sign_Paint", "Key_Board", "Doors", "Fabric_Drape", "Sofa_Fabric",
           "Armchair_Fabric", "Chandelier_Gilt", "Plant_Leaf", "Plant_Pot", "Bulb_Dead", "Window_Glass"]]
PAGES = [2048, 2048]
NIGHT_OFFSET = 2
PANE_MAT = "Window_Glass"
UV_SCALE = {"Window_Glass": 0.12, "Ceiling_Plaster": 0.5, "Paint_Palette": 0.6, "Plant_Leaf": 0.6, "Trim_Paint": 0.7}
KEEP_UV_LM = {"Chandelier_Gilt": 0.06}
WHITE_CAP = 8.0        # a map's white point is its 99.5th percentile texel, but at most WHITE_CAP x its 90th (the few texels beside a bulb clip)
HIDE_IN_BAKE = ("Glass_Clear", PANE_MAT)
SEEN_UP = 4.7          # an up-facing face higher than this is never seen (the loft's eye is at 4.55 m)
SEEN_DOWN = 0.8
TWO_SIDED = ("Plant_Leaf", "Fabric_Drape")


def cull(bm, mname, oname):
    """Drop faces never seen: on the room's outer planes facing out (the walls' outer skin, the floor's underside, the ceiling's top, ends buried in
    the next wall), the panelling's hidden band joint, faces flush against a wall facing into it, and (props) faces looking up from high or down from low."""
    e = 2e-3
    bad = []
    for f in bm.faces:
        c, n = f.calc_center_median(), f.normal
        gx, gy, gz = c.x, c.z, -c.y
        nx, ny, nz = n.x, n.z, -n.y
        out = (nx < -0.9 and gx <= X0 + e) or (nx > 0.9 and gx >= X1 - e) or (nz < -0.9 and gz <= Z0 + e) or (nz > 0.9 and gz >= Z1 - e) \
            or (ny < -0.9 and gy <= e) or (ny > 0.9 and gy >= H - e)
        if oname.startswith("Floor_"):
            out = not (ny > 0.9 and abs(gy) < e)
        elif oname.startswith("Wall_"):
            out = out or (abs(ny) > 0.9 and abs(gy - BAND) < e)
        elif mname not in TWO_SIDED:
            out = out or (ny > 0.5 and gy > SEEN_UP) or (ny < -0.5 and gy < SEEN_DOWN)
            if mname == "Paint_Palette":                     # goods: their bottoms sit on something; their backs face the wall behind the shelf
                out = out or ny < -0.9 or (nz > 0.9 and gz > Z1 - 0.06) or (nx < -0.9 and gx < X0 + 0.25)
        if out:
            bad.append(f)
    bmesh.ops.delete(bm, geom=bad, context="FACES")


def make_export_objects():
    art = bpy.data.collections["Art"]
    if "Export" in bpy.data.collections:
        for o in list(bpy.data.collections["Export"].objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(bpy.data.collections["Export"])
    exp = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(exp)
    by_mat = {}
    for ob in art.objects:
        assert len(ob.data.materials) == 1, ob.name
        mname = ob.data.materials[0].name
        bm = by_mat.setdefault(mname, bmesh.new())
        tmp = bmesh.new()
        tmp.from_mesh(ob.data)
        tmp.normal_update()
        cull(tmp, mname, ob.name)
        me = bpy.data.meshes.new("tmp")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    out = {}
    for mname, bm in by_mat.items():
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        me = bpy.data.meshes.new(mname)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(bpy.data.materials[mname])
        ob = bpy.data.objects.new(mname, me)
        exp.objects.link(ob)
        out[mname] = ob
    return out


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
            if [d for d in prefs.devices if d.type != "CPU"]:
                for d in prefs.devices:
                    d.use = d.type != "CPU"
                gpu = True
                break
    cy.device = "GPU" if gpu else "CPU"
    print("CYCLES device:", cy.device)
    return gpu


def select_only(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


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


def lightmap_uv(objs, page):
    """One atlas for `objs`: smart-project islands at equal texel density (the panes and the ceiling scaled down), packed with MARGIN_PX; a model
    lightmapped through its own UVs (KEEP_UV_LM) gets a square of the page's right edge instead."""
    keep = [o for o in objs if o.name in KEEP_UV_LM]
    corner = max([KEEP_UV_LM[o.name] for o in keep], default=0.0)
    rest = [o for o in objs if o not in keep]
    for o in objs:
        uvs = o.data.uv_layers
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.new(name="lightmap", do_init=o in keep)
        uvs.active = uvs["lightmap"]
        uvs["lightmap"].active_render = True
    for o in keep:
        d = o.data.uv_layers["lightmap"].data
        us = np.array([x.uv for x in d])
        lo, hi = us.min(axis=0), us.max(axis=0)
        q = KEEP_UV_LM[o.name]
        m = MARGIN_PX / page
        sc = (q - 2 * m) / max(hi - lo)
        us = (us - lo) * sc + np.array([1 - q + m, m])
        d.foreach_set("uv", us.ravel())
    select_only(rest)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in rest:
        if o.name in UV_SCALE:
            d = o.data.uv_layers["lightmap"].data
            us = np.array([x.uv for x in d]) * UV_SCALE[o.name]
            d.foreach_set("uv", us.ravel())
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / page, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    if corner:
        f = 1 - corner
        for o in rest:
            d = o.data.uv_layers["lightmap"].data
            us = np.array([x.uv for x in d]) * f
            d.foreach_set("uv", us.ravel())
    plain = [o for o in rest if o.name not in UV_SCALE]
    a3 = sum(area3d(o) for o in plain)
    au = sum(uv_area(o, "lightmap") for o in plain)
    dens = page * math.sqrt(au / a3)
    small = {o.name: round(page * math.sqrt(uv_area(o, "lightmap") / max(1e-9, area3d(o))), 1) for o in objs if o.name in UV_SCALE or o in keep}
    print(f"  page {page}: {a3:.1f} m2, {dens:.1f} px/m; scaled: {small}")
    return page, dens, small


def srgb_encode(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


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
    path = str(stage_work() / "dn.exr")
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=sc.name)
    r = bpy.data.images.load(path)
    a = np.empty(S * S * 4, np.float32)
    r.pixels.foreach_get(a)
    bpy.data.images.remove(r)
    os.remove(path)
    bpy.data.objects.remove(cam)
    bpy.data.scenes.remove(sc)
    bpy.data.node_groups.remove(ng)
    return a.reshape(S, S, 4)


def uv_mask(ob, S, grow=2):
    """The texels an object covers in its lightmap (rows bottom to top), widened by `grow` px."""
    m = np.zeros((S, S), bool)
    uv = ob.data.uv_layers["lightmap"].data
    for p in ob.data.polygons:
        pts = [np.array(uv[i].uv) * S for i in p.loop_indices]
        for k in range(1, len(pts) - 1):
            a, b, c = pts[0], pts[k], pts[k + 1]
            x0, x1 = int(max(0, math.floor(min(a[0], b[0], c[0])) - grow)), int(min(S - 1, math.ceil(max(a[0], b[0], c[0])) + grow))
            y0, y1 = int(max(0, math.floor(min(a[1], b[1], c[1])) - grow)), int(min(S - 1, math.ceil(max(a[1], b[1], c[1])) + grow))
            yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1] + 0.5

            def side(p, q):
                return (q[0] - p[0]) * (yy - p[1]) - (q[1] - p[1]) * (xx - p[0])
            s1, s2, s3 = side(a, b), side(b, c), side(c, a)
            inside = ((s1 >= 0) & (s2 >= 0) & (s3 >= 0)) | ((s1 <= 0) & (s2 <= 0) & (s3 <= 0))
            m[y0:y1 + 1, x0:x1 + 1] |= inside
    if grow:
        m = m | (blur(m.astype(np.float32), grow, 1) > 0)
    return m


def bake_set(n, objs, S, light_set, samples):
    apply_light_set(light_set)
    bpy.context.scene.cycles.samples = samples
    img = bpy.data.images.new(f"LM_{n}_{light_set}", S, S, alpha=False, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    bake_objs = [o for o in objs if o.name != PANE_MAT]
    for o in bake_objs:
        for slot in o.material_slots:
            nt = slot.material.node_tree
            node = nt.nodes.new("ShaderNodeTexImage")
            node.name = "BAKE_TARGET"
            node.image = img
            nt.nodes.active = node
            node.select = True
    select_only(bake_objs)
    for o in bake_objs:
        o.data.uv_layers.active = o.data.uv_layers["lightmap"]
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
    for o in bake_objs:
        for slot in o.material_slots:
            nt = slot.material.node_tree
            for nd in [nd for nd in nt.nodes if nd.name.startswith("BAKE_TARGET")]:
                nt.nodes.remove(nd)
    a = denoise_image(img, S)
    bpy.data.images.remove(img)
    return a[..., :3].copy()


def stage_bake():
    import time
    stage_work()
    exp = make_export_objects()
    leaves = sorted(bpy.data.collections["Doors"].objects, key=lambda o: o.name)
    bpy.data.collections["Art"].hide_render = True
    bpy.data.collections["Art"].hide_viewport = True
    setup_cycles(SAMPLES, bake=True)
    for m in HIDE_IN_BAKE:
        if m in exp:
            exp[m].hide_render = True
    report = {}
    for n, mats in enumerate(GROUPS):
        objs = [exp[m] for m in mats if m in exp] + (leaves if n == 1 else [])
        print(f"lightmap {n}: {[o.name for o in objs]}")
        S, dens, small = lightmap_uv(objs, PAGES[n])
        mask = uv_mask(exp[PANE_MAT], S) if PANE_MAT in exp and exp[PANE_MAT] in objs else np.zeros((S, S), bool)
        for light_set, idx, samples in (("day", n, SAMPLES), ("night", n + NIGHT_OFFSET, NIGHT_SAMPLES)):
            t0 = time.time()
            rgb = bake_set(n, objs, S, light_set, samples)
            peak = rgb.max(axis=2)
            sel = (peak > 1e-5) & ~mask
            pc = np.percentile(peak[sel], [50, 90, 99, 99.5, 100]) if sel.any() else [1.0] * 5
            scale = float(min(pc[3], WHITE_CAP * pc[1]))
            print(f"  {light_set} texel percentiles p50 p90 p99 p99.5 max:", [round(float(v), 4) for v in pc])
            G, C = CURVE[light_set]
            tex = G * rgb / (C + G * rgb)                         # the shoulder: texel x pi C is what the page shows (x the texture); never clips
            if mask.any():
                tex[mask] = np.array(PANE_DAY if light_set == "day" else PANE_NIGHT)
            out = np.ones((S, S, 4), np.float32)
            out[..., :3] = srgb_encode(tex)
            png = bpy.data.images.new(f"LM_{idx}_png", S, S, alpha=False)
            png.colorspace_settings.name = "Non-Color"
            png.pixels.foreach_set(out.ravel())
            png.filepath_raw = str(stage_work() / f"{SCENE}_{idx}.png")
            png.file_format = "PNG"
            png.save()
            bpy.data.images.remove(png)
            report[idx] = {"map": n, "set": light_set, "size": S, "curve_G_C": [G, C], "px_per_m": round(dens, 1), "px_per_m_scaled": small, "scale": round(scale, 5),
                           "p50_p90_p99_p995_max": [round(float(v), 4) for v in pc], "samples": samples, "device": bpy.context.scene.cycles.device,
                           "seconds": round(time.time() - t0), "materials": mats + ([o.name for o in leaves] if n == 1 else [])}
            print("  baked", report[idx])
    (stage_work() / "lightmaps.json").write_text(json.dumps(report, indent=1))
    for m in HIDE_IN_BAKE:
        if m in exp:
            exp[m].hide_render = False
    apply_light_set("day")
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Art"].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


# ---------------------------------------------------------------- brightness: how the page shows the maps
# The page draws a baked material unlit, with no tone mapping: texture x base colour x texel x intensity / pi. The bake's light L (a texel's
# irradiance as Cycles' diffuse pass gives it) is written with a shoulder: texel = G L / (C + G L), and intensity = pi C. So the page shows
# texture x G L where the light is ordinary and rolls off toward texture x C under a lamp or in a sun patch, never clipping. G lifts a whole set;
# CAP lowers a single bright material. The panes are filled flat: PANE_SHOW is what they show (x their frosted texture).
CURVE = {"day": (5.0, 1.35), "night": (6.0, 1.15)}
CAP = {"day": {"Trim_Paint": 0.95}, "night": {}}
PANE_SHOW = {"day": 0.95, "night": 0.42}


def set_intensities():
    rep = json.loads((stage_work() / "lightmaps.json").read_text())
    for idx, r in rep.items():
        idx = int(idx)
        st = r["set"]
        key, kkey = ("lightmap", "lightmap_intensity") if st == "day" else ("lightmap_night", "lightmap_night_intensity")
        names = r["materials"]
        for nm in names:
            ob = bpy.data.objects.get(nm)
            mats = [bpy.data.materials.get(nm)] if bpy.data.materials.get(nm) else [s.material for s in ob.material_slots] if ob else []
            for m in mats:
                if m is None:
                    continue
                m[key] = LM_URL.format(idx)
                if m.name == PANE_MAT:
                    pane = PANE_DAY if st == "day" else PANE_NIGHT
                    m[kkey] = round(math.pi * PANE_SHOW[st] / max(pane), 4)
                else:
                    m[kkey] = round(math.pi * CURVE[st][1] * CAP[st].get(m.name, 1.0), 4)


def scrub_ui_paths():
    for sc in bpy.data.screens:
        for a in sc.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"_" * 1000
                    sp.params.directory = b"//"


KEEP_PROPS = {"lightmap", "lightmap_intensity", "lightmap_night", "lightmap_night_intensity"}
LAYOUT_PREFIX = ("DoorLeaf_", "Spot_", "Marker_", "Link_", "Arrive_")      # the layout's own custom properties (export_scene.py reads them) stay in the .blend
SYS_KEEP = ("cycles", "eevee")


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private(keep_layout=True):
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
                    if kind == "objects" and st is idb and keep_layout and idb.name.startswith(LAYOUT_PREFIX):
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
        for pf in im.packed_files:                                     # a packed image keeps the path it was packed from: make it relative too
            if pf.filepath and not pf.filepath.startswith("//"):
                try:
                    rel = "//" + os.path.relpath(Path(bpy.path.abspath(pf.filepath)), base).replace("\\", "/")
                except ValueError:
                    rel = "//" + Path(pf.filepath).name
                set_path(pf, "filepath", rel)
        if im.packed_file or im.source != "FILE" or not im.filepath:
            continue
        p = Path(bpy.path.abspath(im.filepath))
        try:
            rel = "//" + os.path.relpath(p, base).replace("\\", "/")
        except ValueError:
            rel = "//" + p.name
        set_path(im, "filepath", rel)
    scrub_ui_paths()
    wm = bpy.context.window_manager                                    # the last-used operators remember their file paths (the import, the export)
    for op in ("import_scene.gltf", "export_scene.gltf", "wm.save_as_mainfile", "wm.save_mainfile", "wm.open_mainfile", "image.save_as"):
        try:
            props = wm.operator_properties_last(op)
        except Exception:
            continue
        for attr in ("filepath", "directory", "filename"):
            if props is not None and hasattr(props, attr):
                try:
                    set_path(props, attr, "")
                except Exception as e:
                    print("  could not clear", op, attr, e)


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    scrub_private()
    bpy.ops.wm.save_mainfile()


# ---------------------------------------------------------------- export
def stage_export():
    set_intensities()
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    bpy.data.collections["Art"].hide_viewport = True
    leaves = sorted(bpy.data.collections["Doors"].objects, key=lambda o: o.name)
    stash = {o.name: {k: o[k] for k in o.keys()} for o in leaves}        # the leaves' layout properties are in world/lobby.json, not in the GLB
    for o in leaves:
        for k in list(o.keys()):
            del o[k]
    apply_light_set("export")
    bpy.ops.object.select_all(action="DESELECT")
    for o in list(exp.objects) + leaves:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = stage_work() / f"{SCENE}_raw.glb"
    scrub_private()
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False, export_animations=False)
    for o in leaves:
        for k, v in stash[o.name].items():
            o[k] = v
    print("EXPORTED", raw, raw.stat().st_size)
    apply_light_set("day")
    bpy.data.collections["Art"].hide_viewport = False
    exp.hide_viewport = exp.hide_render = True
    save_blend()


# ---------------------------------------------------------------- the review stills
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
    cam.clip_start, cam.clip_end = 0.05, 200
    ob = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = B(loc)
    ob.rotation_euler = (B(target) - B(loc)).to_track_quat("-Z", "Y").to_euler() if target is not None else (0, 0, 0)
    return ob


def strip_jpeg_comments(path):
    """Drop the JPEG comment (COM) and APP1 segments Blender writes (render statistics)."""
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
        bpy.data.collections["Export"].hide_viewport = True
    bpy.data.collections["Layout"].hide_render = True
    light_set = arg("--set", "day")
    apply_light_set(light_set)
    setup_cycles(arg("--render-samples", 128, int))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = arg("--noise", 0.03, float)
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = arg("--view", "AgX")
    if sc.view_settings.view_transform == "AgX":
        try:
            sc.view_settings.look = "AgX - Medium High Contrast"
        except TypeError:
            pass
    expo = arg("--exposure", 0.0, float)
    which = arg("--only", "all")
    for o in bpy.data.collections["Art"].objects:
        if o.data.materials and o.data.materials[0].name in HIDE_IN_BAKE:
            for attr in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
                setattr(o, attr, False)
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    a, f = SPAWN, FACE
    shots = {
        "1_arrival": look_cam("arrival", (a[0], 1.6, a[2]), (a[0] + f[0] * 3, 1.6, a[2] + f[1] * 3), 75.0),
        "2_wide": look_cam("wide", (-8.9, 2.1, -28.3), (-20.5, 1.5, -13.5), 80.0),
        "3_detail": look_cam("detail", (-17.0, 1.55, -21.9), (-17.0, 1.75, -29.0), 62.0),
        "4_deli": look_cam("deli", (-19.6, 1.6, -12.6), (-25.2, 1.35, -17.6), 70.0),
    }
    plan = look_cam("plan", ((X0 + X1) / 2, H + 8, (Z0 + Z1) / 2), None, ortho=(Z1 - Z0) * 1.02)
    plan.rotation_euler = (0, 0, 0)
    arts = list(bpy.data.collections["Art"].objects) + list(bpy.data.collections["Doors"].objects)
    cut_plan = [o for o in arts if o.name.startswith(("Ceiling_", "Chandelier_", "Trim_cornice", "Trim_picture", "Shop_Canopy", "Shop_Fascia", "Sign_Shop",
                                                      "Loft_", "decor_loft", "Plant_6", "decor_plant_6", "Sign_Deli", "Deli_Pend", "Deli_Menu", "Window_Pelmets", "Sconce"))]
    todo = [(k, v, (1920, 1080)) for k, v in shots.items()] + [("5_plan", plan, (1500, 1650))]
    suffix = "" if light_set == "day" else "_" + light_set
    for key, cam, (w, h) in todo:
        if which not in ("all", key) and not (which == "review" and key in ("1_arrival", "2_wide", "3_detail")):
            continue
        sc.camera = cam
        sc.view_settings.exposure = expo + (0.6 if key == "5_plan" else 0.0)
        for o in arts:
            o.visible_camera = True
        for o in {"5_plan": cut_plan}.get(key, []):
            o.visible_camera = False
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, arg("--scale", 100, int)
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        to_docs = key in ("1_arrival", "2_wide", "3_detail") and light_set == "day" and not arg("--work-stills")
        path = STILLS / f"{key}.jpg" if to_docs else stage_work() / f"{key}{suffix}.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 400_000 and q > 40 and to_docs:
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        strip_jpeg_comments(path)
        print("STILL", key, path.name, path.stat().st_size, "q", q)
    for o in arts:
        o.visible_camera = True
    apply_light_set("day")


if __name__ == "__main__":
    ST = set(STAGE.split(","))                         # several stages in one run: --stage art,render
    if ST & {"art", "all"}:
        build_all()
        save_blend()
    if ST & {"layout", "art", "all"}:
        stage_layout()
    if ST & {"check", "art", "all"}:
        stage_check()
    if ST & {"bake", "all"}:
        stage_bake()
    if ST & {"export", "all"}:
        stage_export()
    if ST & {"axes", "all"}:
        stage_axes()
    if ST & {"render", "all"}:
        stage_render()
