"""Builds the Farway museum hall (`galleries`) in Blender, lights and bakes it at night, and exports world/galleries.glb (docs/BLENDER.md, "2. galleries").

Re-runnable, from the repo root:

    blender -b --python tools/blender/build_galleries.py                       (every stage, in one run)
    blender -b --python tools/blender/build_galleries.py -- --stage art        (build the art, save blender/scenes/galleries.blend)
    blender -b blender/scenes/galleries.blend --python tools/blender/build_galleries.py -- --stage bake [--samples 256] [--device cpu]
    blender -b blender/scenes/galleries.blend --python tools/blender/build_galleries.py -- --stage export
    blender -b blender/scenes/galleries.blend --python tools/blender/build_galleries.py -- --stage axes     (the marker-cube axes check)
    blender -b blender/scenes/galleries.blend --python tools/blender/build_galleries.py -- --stage render [--render-samples 128] [--only 1_arrival]

Stages: art (geometry, materials, lights, stand-ins) -> bake (merge by material, lightmap UV, Cycles bake, OIDN denoise, 8-bit PNGs in the
work folder) -> export (GLB; tools/blender/pack_scene.py then makes the WebP lightmaps and the WebP textures) -> render (the review stills).

The structure is the apartment pilot's (tools/blender/build_apartment.py). No coordinate of the layout is typed in here: the hall, the colliders,
the plinths (MUSEUM.homes, MUSEUM.plinth), the door and the arrival point come from blender/layout/galleries.json
(node tools/blender/dump_layout.mjs galleries). A game point (x, y, z) is Blender (x, -z, y). The art the layout does not name (frames, skylights,
the gallery spots) is placed relative to those numbers: the skylights and the frames sit halfway between the plinth rows.

What the page draws itself is left out (docs/BLENDER.md, contract 4): the six statues and their name plates. The statues are here only as hidden
stand-ins (the `Standins` collection), so the spots' bake has their shadows on the plinths; they are never exported.
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
SCENE = "galleries"
LAYOUT = ROOT / f"blender/layout/{SCENE}.json"
TEX = ROOT / f"blender/textures/{SCENE}"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"      # the path the page reads from the material's `lightmap` custom property
MARGIN_PX = 8

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 256, int)
DEVICE = arg("--device", "auto")
ENGINE = arg("--engine", "CYCLES")

L = json.loads(LAYOUT.read_text())
K = L["constants"]
COLLIDERS = {c["s"]: c for c in L["world"]["colliders"]}
HX, HZ = K["half"]
CZ = K["cz"]
H = K["h"]
Z0, Z1 = CZ - HZ, CZ + HZ                    # the hall's north and south inner faces (game z)
P = K["plinth"]                               # half-width of a plinth
HOMES = K["homes"]
PLINTH_H = max(c["max"][1] for s, c in COLLIDERS.items() if s.startswith("Plinth"))
ROWS = sorted({z for _, z in HOMES})          # the plinth rows' z
STEP = ROWS[1] - ROWS[0]
BAYS = [z - STEP / 2 for z in ROWS] + [ROWS[-1] + STEP / 2]     # halfway between the rows (and one past each end): skylights and frames
DOOR = K["door"]["at"]
DOOR_W, DOOR_H = 2.4, 2.6                     # the blockout's door (index.html museumProps), centred on door.at's x in the south wall
TRACK_X = HX - 3.4                            # the two lighting tracks, parallel to the long walls
SKY_HALF = 1.3                                # a skylight is 2.6 m square
DADO, RAIL = 0.95, 4.1                        # dado rail and picture rail heights


def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


# ---------------------------------------------------------------- materials
IMG_CACHE = {}
MATS = {}
TILES = {}


def image(fn, srgb=True):
    key = (fn, srgb)
    if key not in IMG_CACHE:
        im = bpy.data.images.load(str(TEX / fn))
        im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
        IMG_CACHE[key] = im
    return IMG_CACHE[key]


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, diff=None, tint=None, rough_img=None, emit=None, alpha=None, tile=None):
    """A Principled material. `tint` multiplies the diffuse texture by a constant colour (a Mix node set to Multiply), which the glTF exporter
    writes as baseColorFactor, so the page shows texture x factor x lightmap."""
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

    def tex(fn, srgb):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image(fn, srgb)
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        return n

    if diff:
        n = tex(diff, True)
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
    if rough_img:
        n = tex(rough_img, False)
        nt.links.new(n.outputs["Color"], bsdf.inputs["Roughness"])
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
    TILES[name] = tile or 1.0
    MATS[name] = m
    return m


def make_materials():
    material("Floor_Parquet", diff="herringbone_parquet_diff_1k.jpg", tint=(0.78, 0.70, 0.62), rough=0.6, tile=3.4)
    material("Floor_Marble", diff="marble_01_diff_1k.jpg", tint=(0.80, 0.80, 0.78), rough=0.25, tile=1.5)
    material("Wall_Paint", diff="plastered_wall_04_diff_1k.jpg", tint=(0.62, 0.17, 0.15), rough=0.9, tile=3.2)
    material("Ceiling_Paint", diff="plastered_wall_04_diff_1k.jpg", tint=(1.0, 0.97, 0.90), rough=0.95, tile=3.2)
    material("Wainscot_Wood", diff="dark_wood_diff_1k.jpg", tint=(0.85, 0.80, 0.78), rough=0.5, tile=0.9)
    material("Door_Wood", diff="dark_wood_diff_1k.jpg", rough=0.5, tile=0.9)
    material("Trim_Paint", color=(0.56, 0.53, 0.47), rough=0.55)
    material("Plinth_Paint", diff="plastered_wall_04_diff_1k.jpg", tint=(0.40, 0.39, 0.38), rough=0.7, tile=1.6)
    material("Frame_Gold", color=(0.50, 0.34, 0.11), rough=0.35, metal=0.9)
    material("Metal_Dark", color=(0.03, 0.03, 0.035), rough=0.4, metal=0.8)
    material("Metal_Brass", color=(0.55, 0.38, 0.12), rough=0.35, metal=0.9)
    material("Lamp_Emit", color=(1.0, 0.85, 0.62), rough=0.4, emit=((1.0, 0.80, 0.55), 14.0))
    material("Skylight_Glass", color=(0.05, 0.07, 0.10), rough=0.2, emit=((0.10, 0.14, 0.26), 0.6), alpha=0.6)
    material("Standin_Stone", color=(0.48, 0.46, 0.42), rough=0.8)


# ---------------------------------------------------------------- geometry helpers (all built in world space, identity object transforms)
def cube(bm, gmin, gmax):
    a, b = B(gmin), B(gmax)
    c = (a + b) / 2
    s = Vector((abs(a.x - b.x), abs(a.y - b.y), abs(a.z - b.z)))
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((s.x, s.y, s.z, 1.0)))


def cyl(bm, p0, p1, r0, r1=None, seg=16, cap=True):
    a, b = B(p0), B(p1)
    d = b - a
    q = d.to_track_quat("Z", "Y")
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                          matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())


def sphere(bm, p, r, seg=12):
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2 + 1, radius=r, matrix=Matrix.Translation(B(p)))


def quad(bm, p0, p1, p2, p3):
    vs = [bm.verts.new(B(p)) for p in (p0, p1, p2, p3)]
    bm.faces.new(vs)


def box_uv(bm, tile):
    """UV0: box projection in metres / tile, from world positions, so a texture runs on across the pieces of a wall."""
    uvl = bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y            # back to game axes
            if ax == 0:
                u, v = gz, gy
            elif ax == 1:
                u, v = gx, gy
            else:
                u, v = gx, gz
            lp[uvl].uv = (u / tile, v / tile)


def finish(name, bm, mat, coll, smooth=False, tile=None, sharp_deg=35, keep_uv=False):
    for e in bm.edges:
        if smooth and len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) < math.radians(sharp_deg)
        else:
            e.smooth = not (len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(1))
    for f in bm.faces:
        f.smooth = smooth
    if not keep_uv:                                   # a lone panel keeps the winding it was built with (it faces the room)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if not bm.loops.layers.uv.get("UVMap"):
        bm.loops.layers.uv.new("UVMap")
    if not keep_uv:
        box_uv(bm, tile or TILES[mat])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


ART = STANDIN = None


def part(name, mat, build, smooth=False, tile=None, coll=None):
    bm = bmesh.new()
    build(bm)
    return finish(name, bm, mat, coll or ART, smooth, tile)


# wall frames: a wall is named by its inward normal; ALONG is the game axis that runs along it, OUT the coordinate of its inner face
WALLS = {"+x": ("z", -HX), "-x": ("z", HX), "+z": ("x", Z0), "-z": ("x", Z1)}
WALL_NAME = {"+x": "W", "-x": "E", "+z": "N", "-z": "S"}


def on_wall(normal, a, y, d):
    """A game point on the wall whose inward normal is `normal`: `a` along the wall, height `y`, `d` metres into the room."""
    ax, face = WALLS[normal]
    sign = 1 if normal[0] == "+" else -1
    off = face + sign * d
    return (off, y, a) if ax == "z" else (a, y, off)


def wall_box(bm, normal, a0, a1, y0, y1, d0, d1):
    """A box against a wall: from a0 to a1 along it, y0 to y1 high, d0 to d1 into the room."""
    p, q = on_wall(normal, a0, y0, d0), on_wall(normal, a1, y1, d1)
    cube(bm, [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)])


# ---------------------------------------------------------------- the art
def build_shell():
    """Floor, walls and ceiling, from the collision file's boxes (Floor_*, Ceiling_*, Wall_*), so art and colliders agree. The floor is a parquet field
    inside a marble border; each wall is wainscot below the dado rail and paint above it; the ceiling has the skylights' openings."""
    f = COLLIDERS["Floor_Museum"]
    mn, mx = f["min"], f["max"]
    b = 0.45                                                                                    # the marble border, from the walls' inner faces
    part("Floor_Museum", "Floor_Parquet", lambda bm: cube(bm, (-HX + b, mn[1], Z0 + b), (HX - b, mx[1], Z1 - b)))

    def border(bm):
        cube(bm, (mn[0], mn[1], mn[2]), (mx[0], mx[1], Z0 + b))
        cube(bm, (mn[0], mn[1], Z1 - b), (mx[0], mx[1], mx[2]))
        cube(bm, (mn[0], mn[1], Z0 + b), (-HX + b, mx[1], Z1 - b))
        cube(bm, (HX - b, mn[1], Z0 + b), (mx[0], mx[1], Z1 - b))
    part("Floor_Border", "Floor_Marble", border)

    for s, c in COLLIDERS.items():
        if not s.startswith("Wall_"):
            continue
        mn, mx = c["min"], c["max"]
        part(s, "Wall_Paint", lambda bm: cube(bm, (mn[0], DADO, mn[2]), (mx[0], mx[1], mx[2])))
        part(s + "_Lower", "Wainscot_Wood", lambda bm: cube(bm, (mn[0], mn[1], mn[2]), (mx[0], DADO, mx[2])))

    c = COLLIDERS["Ceiling_Museum"]
    mn, mx = c["min"], c["max"]

    def ceiling(bm):
        cube(bm, (mn[0], mn[1], mn[2]), (-SKY_HALF, mx[1], mx[2]))
        cube(bm, (SKY_HALF, mn[1], mn[2]), (mx[0], mx[1], mx[2]))
        z = mn[2]
        for zc in BAYS:
            cube(bm, (-SKY_HALF, mn[1], z), (SKY_HALF, mx[1], zc - SKY_HALF))
            z = zc + SKY_HALF
        cube(bm, (-SKY_HALF, mn[1], z), (SKY_HALF, mx[1], mx[2]))
    part("Ceiling_Museum", "Ceiling_Paint", ceiling)


def build_skylights():
    """Four skylights over the middle aisle, between the plinth rows: a dark metal frame lining each opening, glazing bars, and a frosted pane (Skylight_Glass:
    transparent and faintly lit, no lightmap). The moon of the bake shines in through them."""
    y0, y1 = COLLIDERS["Ceiling_Museum"]["min"][1], COLLIDERS["Ceiling_Museum"]["max"][1]
    s, t = SKY_HALF, 0.03

    def frames(bm):
        for zc in BAYS:
            cube(bm, (-s, y0, zc - s), (s, y1, zc - s + t))
            cube(bm, (-s, y0, zc + s - t), (s, y1, zc + s))
            cube(bm, (-s, y0, zc - s), (-s + t, y1, zc + s))
            cube(bm, (s - t, y0, zc - s), (s, y1, zc + s))
            for k in (-1, 1):
                cube(bm, (k * s / 3 - 0.02, y1 - 0.09, zc - s), (k * s / 3 + 0.02, y1 - 0.02, zc + s))       # glazing bars, 3 x 3 panes
                cube(bm, (-s, y1 - 0.09, zc + k * s / 3 - 0.02), (s, y1 - 0.02, zc + k * s / 3 + 0.02))
    part("Skylight_Frame", "Metal_Dark", frames)

    def panes(bm):
        for zc in BAYS:
            quad(bm, (-s, y1 - 0.025, zc + s), (s, y1 - 0.025, zc + s), (s, y1 - 0.025, zc - s), (-s, y1 - 0.025, zc - s))
    part("Skylight_Pane", "Skylight_Glass", panes, tile=1.0)


def build_trim():
    """Skirting, the dado rail, the picture rail, the cornice, and the door (a closed double leaf in its architrave: the page's
    door prompt at door.at is unchanged)."""
    dx = DOOR[0]
    gap = (dx - DOOR_W / 2 - 0.25, dx + DOOR_W / 2 + 0.25)            # the door and its architrave on the south wall

    def runs(normal):
        ax, _ = WALLS[normal]
        lo, hi = (Z0, Z1) if ax == "z" else (-HX, HX)
        if normal == "-z":
            return [(lo, gap[0]), (gap[1], hi)]
        return [(lo, hi)]

    def skirt(bm):
        for n in WALLS:
            for a0, a1 in runs(n):
                wall_box(bm, n, a0, a1, 0.0, 0.16, 0.0, 0.022)
    part("Trim_Skirting", "Wainscot_Wood", skirt)

    def dado(bm):
        for n in WALLS:
            for a0, a1 in runs(n):
                wall_box(bm, n, a0, a1, DADO - 0.05, DADO + 0.02, 0.0, 0.04)
    part("Trim_Dado", "Wainscot_Wood", dado)

    def rail(bm):
        for n in WALLS:
            ax, _ = WALLS[n]
            lo, hi = (Z0, Z1) if ax == "z" else (-HX, HX)
            wall_box(bm, n, lo, hi, RAIL - 0.04, RAIL, 0.0, 0.03)
    part("Trim_PictureRail", "Metal_Brass", rail)

    def cornice(bm):
        for n in WALLS:
            ax, _ = WALLS[n]
            lo, hi = (Z0, Z1) if ax == "z" else (-HX, HX)
            wall_box(bm, n, lo, hi, H - 0.30, H, 0.0, 0.04)
            wall_box(bm, n, lo, hi, H - 0.20, H, 0.0, 0.10)
            wall_box(bm, n, lo, hi, H - 0.09, H, 0.0, 0.17)
            wall_box(bm, n, lo, hi, H - 0.36, H - 0.30, 0.0, 0.025)
    part("Cornice", "Trim_Paint", cornice)

    x0, x1 = dx - DOOR_W / 2, dx + DOOR_W / 2

    def architrave(bm):
        wall_box(bm, "-z", x0 - 0.22, x0, 0.0, DOOR_H + 0.22, 0.0, 0.045)
        wall_box(bm, "-z", x1, x1 + 0.22, 0.0, DOOR_H + 0.22, 0.0, 0.045)
        wall_box(bm, "-z", x0 - 0.22, x1 + 0.22, DOOR_H, DOOR_H + 0.22, 0.0, 0.045)
        wall_box(bm, "-z", x0 - 0.30, x1 + 0.30, DOOR_H + 0.22, DOOR_H + 0.30, 0.0, 0.045)      # the head's cap
    part("Door_Architrave", "Door_Wood", architrave)

    def leaves(bm):
        for a0, a1 in ((x0, dx - 0.004), (dx + 0.004, x1)):
            wall_box(bm, "-z", a0, a1, 0.0, DOOR_H, 0.0, 0.035)
            for (yy0, yy1) in ((0.18, 1.05), (1.25, DOOR_H - 0.18)):                         # two raised fields per leaf
                wall_box(bm, "-z", a0 + 0.14, a1 - 0.14, yy0, yy1, 0.035, 0.045)
    part("Door_Leaves", "Door_Wood", leaves)

    def hardware(bm):
        for a in (dx - 0.06, dx + 0.035):
            wall_box(bm, "-z", a, a + 0.025, 0.85, 1.25, 0.035, 0.048)                         # pull handles
        for a0, a1 in ((x0 + 0.2, dx - 0.2), (dx + 0.2, x1 - 0.2)):
            wall_box(bm, "-z", a0, a1, 0.0, 0.22, 0.035, 0.04)                                # kick plates
    part("Door_Hardware", "Metal_Brass", hardware)


def build_plinths():
    """The six plinths, at MUSEUM.homes: a dark painted block on a recessed black toe, the size of their colliders (0.9 m square, 0.6 m high). The page
    hangs each statue's name plate on the face toward the hall, so that face is plain."""
    def body(bm, x, z):
        cube(bm, (x - P, 0.05, z - P), (x + P, PLINTH_H - 0.025, z + P))
        cube(bm, (x - P - 0.012, PLINTH_H - 0.025, z - P - 0.012), (x + P + 0.012, PLINTH_H, z + P + 0.012))   # the top's lip
    for i, (x, z) in enumerate(HOMES):
        part(f"Plinth_{i}_Body", "Plinth_Paint", lambda bm: body(bm, x, z))
        part(f"Plinth_{i}_Toe", "Metal_Dark", lambda bm: cube(bm, (x - P + 0.02, 0.0, z - P + 0.02), (x + P - 0.02, 0.05, z + P - 0.02)))


def ring(bm, normal, a0, a1, y0, y1, t, d0, d1):
    """A rectangular ring on a wall (a frame's moulding): outer edges a0..a1, y0..y1, `t` wide, from d0 to d1 into the room. Its front is one flat ring, so it
    unwraps as one lightmap island, not four bars."""
    outer = [(a0, y0), (a1, y0), (a1, y1), (a0, y1)]
    inner = [(a0 + t, y0 + t), (a1 - t, y0 + t), (a1 - t, y1 - t), (a0 + t, y1 - t)]
    def V(p, d):
        return bm.verts.new(B(on_wall(normal, p[0], p[1], d)))
    of, inf = [V(p, d1) for p in outer], [V(p, d1) for p in inner]
    ob, ib = [V(p, d0) for p in outer], [V(p, d0) for p in inner]
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((of[i], of[j], inf[j], inf[i]))          # the front
        bm.faces.new((ob[i], ob[j], of[j], of[i]))            # the outer side
        bm.faces.new((inf[i], inf[j], ib[j], ib[i]))          # the inner side (the sight edge)


def frame_bars(bm, normal, a, yc, w, h, bar, depth):
    """An empty picture frame on a wall: an outer moulding `bar` wide and a raised inner lip, `depth` proud in all."""
    a0, a1, y0, y1 = a - w / 2, a + w / 2, yc - h / 2, yc + h / 2
    ring(bm, normal, a0, a1, y0, y1, bar, 0.0, depth * 0.7)
    i = bar * 0.35
    ring(bm, normal, a0 + i, a1 - i, y0 + i, y1 - i, bar * 0.4, depth * 0.7, depth)


FRAMES = []          # (normal, along, centre y, w, h): filled by build_frames, used by the lights


def build_frames():
    """Empty gilded frames: one in each bay of the long walls (halfway between the plinths), two either side of the door, and a large one on the north wall at the
    end of the hall. Each hangs from the picture rail on two brass wires and has a brass picture light over it. Frames are 4.5 cm deep, so they stay within
    5 cm of the wall (the layout check's rule for art that reaches below head height)."""
    FRAMES.clear()
    for n in ("+x", "-x"):
        for zb in BAYS:
            FRAMES.append((n, zb, 2.3, 1.7, 1.25, 0.11))
    dx = DOOR[0]
    for k in (-1, 1):
        FRAMES.append(("-z", dx + k * (DOOR_W / 2 + 1.55), 2.15, 1.25, 0.95, 0.09))
    FRAMES.append(("+z", 0.0, 2.7, 3.3, 2.4, 0.15))

    for i, (n, a, yc, w, h, bar) in enumerate(FRAMES):
        part(f"Frame_{i}", "Frame_Gold", lambda bm: frame_bars(bm, n, a, yc, w, h, bar, 0.045))

    def wires(bm):
        for n, a, yc, w, h, bar in FRAMES:
            top = yc + h / 2
            for k in (-1, 1):
                p0 = on_wall(n, a + k * w * 0.32, RAIL - 0.03, 0.02)
                p1 = on_wall(n, a + k * w * 0.18, top, 0.02)
                cyl(bm, p0, p1, 0.002, 0.002, 4, cap=False)
                cyl(bm, on_wall(n, a + k * w * 0.32, RAIL - 0.045, 0.018), on_wall(n, a + k * w * 0.32, RAIL - 0.01, 0.018), 0.008, 0.008, 6)   # the rail hook
    part("Frame_Wires", "Metal_Brass", wires)

    def picture_lights(bm):
        for n, a, yc, w, h, bar in FRAMES:
            top = yc + h / 2 + 0.12
            lw = min(0.7, w * 0.4)
            wall_box(bm, n, a - 0.04, a + 0.04, top - 0.03, top + 0.06, 0.0, 0.02)                        # the wall plate
            cyl(bm, on_wall(n, a, top + 0.015, 0.01), on_wall(n, a, top + 0.08, 0.20), 0.009, 0.009, 8)   # the arm
            cyl(bm, on_wall(n, a - lw / 2, top + 0.08, 0.22), on_wall(n, a + lw / 2, top + 0.08, 0.22), 0.032, 0.032, 16)   # the hood
    part("Picture_Lights", "Metal_Brass", picture_lights, smooth=True)

    def bulbs(bm):
        for n, a, yc, w, h, bar in FRAMES:
            top = yc + h / 2 + 0.12
            lw = min(0.7, w * 0.4)
            cyl(bm, on_wall(n, a - lw / 2 + 0.02, top + 0.055, 0.205), on_wall(n, a + lw / 2 - 0.02, top + 0.055, 0.205), 0.012, 0.012, 8)
    part("Picture_Light_Tubes", "Lamp_Emit", bulbs, smooth=True)


SPOTS = []           # (name, pivot (game), aim point (game), power W, cone deg): filled by build_tracks


def build_tracks():
    """Two lighting tracks under the ceiling, parallel to the long walls; a gallery spot on each over every plinth, aimed at its statue's chest, and two at the north
    end aimed at the big frame. The spot heads are art (Metal_Dark, a Lamp_Emit lens); the lights are Blender spots used for the bake and the stills."""
    SPOTS.clear()
    yt = H - 0.03
    part("Track_Rails", "Metal_Dark", lambda bm: [cube(bm, (k * TRACK_X - 0.025, yt - 0.035, Z0 + 0.6), (k * TRACK_X + 0.025, yt, Z1 - 0.6)) for k in (-1, 1)])
    for i, (x, z) in enumerate(HOMES):
        k = 1 if x > 0 else -1
        SPOTS.append((f"Spot_Plinth_{i}", (k * TRACK_X, yt - 0.22, z), (x, PLINTH_H + 0.85, z), 950.0, 34.0))
    for k in (-1, 1):
        SPOTS.append((f"Spot_North_{'E' if k > 0 else 'W'}", (k * TRACK_X, yt - 0.22, Z0 + 1.4), (k * 0.9, 2.7, Z0), 750.0, 30.0))

    def heads(bm):
        for _, piv, aim, _, _ in SPOTS:
            d = (Vector(aim) - Vector(piv)).normalized()
            top = (piv[0], yt - 0.035, piv[2])
            cyl(bm, top, piv, 0.008, 0.008, 6)                                                            # the stem
            sphere(bm, piv, 0.03, 8)                                                                       # the knuckle
            back = Vector(piv) - d * 0.05
            front = Vector(piv) + d * 0.13
            cyl(bm, tuple(back), tuple(front), 0.042, 0.05, 16)                                            # the can
    part("Spot_Heads", "Metal_Dark", heads, smooth=True)

    def lenses(bm):
        for _, piv, aim, _, _ in SPOTS:
            d = (Vector(aim) - Vector(piv)).normalized()
            cyl(bm, tuple(Vector(piv) + d * 0.13), tuple(Vector(piv) + d * 0.136), 0.04, 0.04, 16)
    part("Spot_Lenses", "Lamp_Emit", lenses, smooth=True)


def build_exit_sign():
    """An EXIT sign over the door (own drawing: a pixel font on green), on a dark box; the sign face is emissive and carries no lightmap."""
    dx = DOOR[0]
    y = DOOR_H + 0.55
    part("Exit_Housing", "Metal_Dark", lambda bm: wall_box(bm, "-z", dx - 0.22, dx + 0.22, y - 0.09, y + 0.09, 0.0, 0.07))
    panel("Exit_Face", "Sign_Exit", on_wall("-z", dx, y, 0.0705), "-z", 0.40, 0.15)


# ---------------------------------------------------------------- generated images (own work, numpy, fixed seeds)
GLYPHS = {"E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"], "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
          "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"], "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"]}


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


def exit_pixels():
    h, w = 96, 256
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (0.02, 0.45, 0.16)
    s = 9
    x = (w - (4 * 5 + 3 * 2) * s) // 2
    y0 = (h - 7 * s) // 2
    for ch in "EXIT":
        for r, row in enumerate(GLYPHS[ch]):
            for c, v in enumerate(row):
                if v == "1":
                    img[y0 + r * s:y0 + (r + 1) * s, x + c * s:x + (c + 1) * s] = (0.95, 1.0, 0.95)
        x += 7 * s
    img[:4] = img[-4:] = img[:, :4] = img[:, -4:] = (0.01, 0.2, 0.07)
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def ghost_pixels():
    """Where a painting hung: a cleaner, paler rectangle of the wall with a dusty rim (an alpha decal)."""
    S = 256
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:S, 0:S] / (S - 1)
    m = 0.08
    inside = ((xx > m) & (xx < 1 - m) & (yy > m) & (yy < 1 - m)).astype(np.float32)
    soft = blur(inside, 3, 2)
    rim = np.clip(soft * (1 - soft) * 4, 0, 1)
    noise = blur(rng.random((S, S)).astype(np.float32), 4, 2)
    rgba = np.zeros((S, S, 4), np.float32)
    rgba[..., :3] = np.array([0.95, 0.80, 0.74]) * (soft[..., None]) + np.array([0.20, 0.16, 0.12]) * (rim[..., None])
    rgba[..., 3] = np.clip(soft * 0.16 + rim * 0.22 + (noise - 0.5) * 0.05, 0, 0.4)
    return rgba


def mk_image(name, arr, srgb=True):
    """A packed image from a float array (rows top to bottom): written as a PNG first, because a generated image forgets its pixels when the file is saved."""
    h, w = arr.shape[:2]
    has_a = arr.shape[2] == 4
    im = bpy.data.images.new(name + "_gen", w, h, alpha=has_a)
    im.alpha_mode = "STRAIGHT"
    im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :arr.shape[2]] = arr
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
    out.alpha_mode = "STRAIGHT"
    out.pack()
    for ref in [out] + list(out.packed_files):          # packed: overwrite the work folder's path (a fixed buffer) in the image and its packed file ...
        attr = "filepath_raw" if ref is out else "filepath"
        setattr(ref, attr, "_" * 1000)
        setattr(ref, attr, f"//generated/{name}.png")  # ... so it is not kept in the .blend
    return out


def textured(name, im, emit=None, alpha=False, rough=0.9, tile=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out, bsdf, tx, uv = (nt.nodes.new(t) for t in ("ShaderNodeOutputMaterial", "ShaderNodeBsdfPrincipled", "ShaderNodeTexImage", "ShaderNodeUVMap"))
    uv.uv_map = "UVMap"
    tx.image = im
    nt.links.new(uv.outputs["UV"], tx.inputs["Vector"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = rough
    if emit:
        bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
        nt.links.new(tx.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emit
    else:
        nt.links.new(tx.outputs["Color"], bsdf.inputs["Base Color"])
    if alpha:
        nt.links.new(tx.outputs["Alpha"], bsdf.inputs["Alpha"])
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    TILES[name] = tile
    MATS[name] = m
    return m


RIGHT = {"+x": (0, 0, -1), "-x": (0, 0, 1), "+z": (1, 0, 0), "-z": (-1, 0, 0)}   # looking at a surface whose normal is +x, -x, ...: the game direction of your right hand


def panel(name, mat, centre, normal, w, h, coll=None):
    """A flat quad facing `normal` (a game axis such as "+x"), w wide, h tall, UV 0..1 with the picture upright."""
    r = Vector(RIGHT[normal])
    up = Vector((0, 1, 0))
    c = Vector(centre)
    pts = [c - r * w / 2 - up * h / 2, c + r * w / 2 - up * h / 2, c + r * w / 2 + up * h / 2, c - r * w / 2 + up * h / 2]
    bm = bmesh.new()
    quad(bm, *[tuple(p) for p in pts])
    bm.faces.ensure_lookup_table()
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp, uv in zip(bm.faces[0].loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = uv
    return finish(name, bm, mat, coll or ART, keep_uv=True)


def build_ghosts():
    """Paler rectangles over the plinths where paintings were taken down (decals 3 mm off the wall, above head height)."""
    rng = np.random.default_rng(13)
    for i, (x, z) in enumerate(HOMES):
        n = "+x" if x < 0 else "-x"
        w, h = rng.uniform(1.0, 1.5), rng.uniform(0.8, 1.1)
        panel(f"Decal_Ghost_{i}", "Decal_Ghost", on_wall(n, z + rng.uniform(-0.15, 0.15), 3.15, 0.003), n, w, h)


# ---------------------------------------------------------------- the statues, as stand-ins (the page draws them: index.html museumProps)
STATUE = [(0.42, 0.75, 0.26, 0, 0.95), (0.15, 0.58, 0.15, -0.11, 0.29), (0.15, 0.58, 0.15, 0.11, 0.29), (0.11, 0.6, 0.11, -0.28, 0.98), (0.11, 0.6, 0.11, 0.28, 0.98), (0.24, 0.28, 0.24, 0, 1.5)]


def build_standins():
    """The blockout's statue (six boxes, as museumProps builds it) on each plinth, turned to face the hall: in the bake they throw the spots' shadows on the plinths.
    Hidden from the export; seen in the review stills so the plinths read as they will in the game."""
    def statues(bm):
        for x, z in HOMES:
            for w, h, d, ox, oy in STATUE:                    # turned a quarter: the box's width runs along z
                cube(bm, (x - d / 2, PLINTH_H + oy - h / 2, z + ox - w / 2), (x + d / 2, PLINTH_H + oy + h / 2, z + ox + w / 2))
    part("standin_statues", "Standin_Stone", statues, coll=STANDIN)


# ---------------------------------------------------------------- lights, world
def add_lights():
    lights = bpy.data.collections.new("Lights")
    bpy.context.scene.collection.children.link(lights)

    def light(name, kind, pos, energy, color, size):
        d = bpy.data.lights.new(name, kind)
        d.energy, d.color = energy, color
        d.shadow_soft_size = size
        ob = bpy.data.objects.new(name, d)
        ob.location = B(pos)
        lights.objects.link(ob)
        return ob, d

    warm = (1.0, 0.80, 0.58)
    for name, piv, aim, power, cone in SPOTS:
        d3 = (Vector(aim) - Vector(piv)).normalized()
        ob, d = light(name, "SPOT", tuple(Vector(piv) + d3 * 0.14), power, warm, 0.035)
        d.spot_size, d.spot_blend = math.radians(cone), 0.45
        ob.rotation_euler = B(d3).to_track_quat("-Z", "Y").to_euler()
    for i, (n, a, yc, w, h, bar) in enumerate(FRAMES):          # the picture lights: wide, soft, down onto the frame
        top = yc + h / 2 + 0.12
        pos = on_wall(n, a, top + 0.04, 0.21)
        aim = on_wall(n, a, yc - h * 0.25, 0.0)
        d3 = (Vector(aim) - Vector(pos)).normalized()
        ob, d = light(f"Picture_Light_{i}", "SPOT", pos, 90.0 if w < 3 else 180.0, (1.0, 0.74, 0.48), 0.12)
        d.spot_size, d.spot_blend = math.radians(120), 0.8
        ob.rotation_euler = B(d3).to_track_quat("-Z", "Y").to_euler()
    ob, d = light("Moon", "SUN", (0, 20, CZ), MOON_W, (0.62, 0.74, 1.0), 0.0)
    d.angle = math.radians(1.0)
    ob.rotation_euler = B((0.42, -1.0, 0.18)).to_track_quat("-Z", "Y").to_euler()     # from high in the west-south-west: the squares land east of the aisle
    ob, d = light("Exit_Glow", "AREA", on_wall("-z", DOOR[0], DOOR_H + 0.55, 0.09), 1.5, (0.3, 1.0, 0.45), 0.0)
    d.shape, d.size, d.size_y = "RECTANGLE", 0.40, 0.15
    ob.rotation_euler = B((0, 0, -1)).to_track_quat("-Z", "Y").to_euler()


MOON_W = 1.4
WORLD_STRENGTH = 25.0


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("Night")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.012, 0.016, 0.035, 1)
    bg.inputs["Strength"].default_value = WORLD_STRENGTH          # the moonlit sky: seen only through the skylights, a soft cool fill down the aisle


def ensure_marker():
    """A 20 cm marker cube at the arrival point (docs/BLENDER.md, contract 3), kept in Standins and never exported or rendered."""
    st = bpy.data.collections["Standins"]
    ob = bpy.data.objects.get("standin_arrival_marker")
    if ob is None:
        me = bpy.data.meshes.new("standin_arrival_marker")
        bm = bmesh.new()
        a = K["arrive"]
        cube(bm, (a[0] - 0.1, a[1], a[2] - 0.1), (a[0] + 0.1, a[1] + 0.2, a[2] + 0.1))
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("standin_arrival_marker", me)
        st.objects.link(ob)
    ob.hide_render = True
    return ob


def stage_axes():
    """The axes check: export the marker alone through the glTF exporter and read back where it landed. A game point (x, y, z) must come out as (x, y, z)."""
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
    node = j["nodes"][0]
    off = node.get("translation", [0, 0, 0])
    lo = [acc["min"][i] + off[i] for i in range(3)]
    hi = [acc["max"][i] + off[i] for i in range(3)]
    centre = [(lo[i] + hi[i]) / 2 for i in range(3)]
    a = K["arrive"]
    want = [a[0], a[1] + 0.1, a[2]]
    bl = sum((v.co for v in ob.data.vertices), Vector()) / len(ob.data.vertices)
    print(f"AXES blender centre {tuple(round(v, 3) for v in bl)} (x, -z, y of the game point {tuple(want)})")
    print(f"AXES glTF centre {tuple(round(v, 3) for v in centre)}, game point {tuple(want)}")
    assert all(abs(centre[i] - want[i]) < 1e-4 for i in range(3)), "the exporter's axes disagree with (x, -z, y)"
    assert abs(bl.x - want[0]) < 1e-4 and abs(bl.y + want[2]) < 1e-4 and abs(bl.z - want[1]) < 1e-4
    print("AXES PASS: game (x, y, z) = Blender (x, -z, y) = glTF (x, y, z)")


def build_all():
    global ART, STANDIN
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
    ART = bpy.data.collections.new("Art")
    STANDIN = bpy.data.collections.new("Standins")
    sc = bpy.context.scene
    sc.collection.children.link(ART)
    sc.collection.children.link(STANDIN)
    make_materials()
    textured("Sign_Exit", mk_image("Exit_Sign", exit_pixels()), emit=3.0)
    textured("Decal_Ghost", mk_image("Wall_Ghost", ghost_pixels()), alpha=True)
    build_shell()
    build_skylights()
    build_trim()
    build_plinths()
    build_frames()
    build_tracks()
    build_exit_sign()
    build_ghosts()
    build_standins()
    add_lights()
    setup_world()
    ensure_marker()


# ---------------------------------------------------------------- bake
GROUPS = [["Floor_Parquet", "Floor_Marble", "Ceiling_Paint"],                                  # 0: the floor and the ceiling
          ["Wall_Paint", "Wainscot_Wood", "Trim_Paint", "Decal_Ghost"],                          # 1: the walls, their wainscot, skirting, rails and cornice
          ["Plinth_Paint", "Frame_Gold", "Door_Wood"],                                           # 2: the plinths, the frames, the door
          ["Metal_Dark", "Metal_Brass"]]        # 3: tracks, spot heads, picture lights, rails: they sit next to the lights, so their texels run far hotter
                                                #    than the rest and get their own map (and their own lightmap_intensity) instead of crushing the others
PAGES = [896, 1152, 768, 1152]          # each map's fixed page size (px): the smallest page that gave >= 30 px/m. Fixed, because Blender's island
                                        # packer is not exactly repeatable and map 3 sat right on the 30 px/m line (1024 or 1152 from run to run)
SHELL_PREFIX = ("Wall_", "Floor_", "Ceiling_")


def trim_outside(bm, ceiling=False):
    """Drop the faces of a shell slab that are never seen from the hall (the outer skin of the walls, the floor's underside and sides, the ceiling's top): they would
    cost lightmap texels. A face is kept when its centre lies in the hall's inner box (1 mm slack); the ceiling also keeps its openings' sides, but not its top."""
    e = 0.001
    keep_y = COLLIDERS["Ceiling_Museum"]["max"][1] - e if ceiling else H + e
    bad = []
    for f in bm.faces:
        c = f.calc_center_median()
        gx, gy, gz = c.x, c.z, -c.y
        inside = -HX - e <= gx <= HX + e and -e <= gy <= keep_y and Z0 - e <= gz <= Z1 + e
        if not inside or (ceiling and f.normal.z > 0.5):
            bad.append(f)
    bmesh.ops.delete(bm, geom=bad, context="FACES")


def cull_flush(bm):
    """Drop the faces of a piece that lie flat against a wall, the floor or the ceiling and face into it (the back of a frame, the underside of a plinth): never
    seen, and each would be one more lightmap island."""
    e = 1e-3
    bad = []
    for f in bm.faces:
        c, n = f.calc_center_median(), f.normal
        gx, gy, gz = c.x, c.z, -c.y
        nx, ny, nz = n.x, n.z, -n.y
        if (nx > 0.9 and abs(gx - HX) <= e) or (nx < -0.9 and abs(gx + HX) <= e) or (nz > 0.9 and abs(gz - Z1) <= e) or (nz < -0.9 and abs(gz - Z0) <= e)                 or (ny < -0.9 and abs(gy) <= e) or (ny > 0.9 and abs(gy - H) <= e):
            bad.append(f)
    bmesh.ops.delete(bm, geom=bad, context="FACES")


def stage_work():
    d = Path(arg("--work", str(Path(os.environ.get("TEMP", "/tmp")) / f"farway_{SCENE}")))
    d.mkdir(parents=True, exist_ok=True)
    return d


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
        if ob.name.startswith(SHELL_PREFIX):
            trim_outside(tmp, ceiling=ob.name.startswith("Ceiling_"))
        else:
            cull_flush(tmp)
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


def lightmap_uv(objs, page=None):
    """One shared atlas for `objs`: smart-project islands, equal texel density, packed with MARGIN_PX; on `page` px, or else the smallest square
    page that gives >= 30 px/m."""
    for o in objs:
        uvs = o.data.uv_layers
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.new(name="lightmap")
        uvs.active = uvs["lightmap"]
        uvs["lightmap"].active_render = True
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    chosen = None
    for S in ((page,) if page else (512, 640, 768, 896, 1024, 1152, 1280, 1408, 1536, 1792, 2048)):
        bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / S, shape_method="CONCAVE")
        bpy.ops.object.mode_set(mode="OBJECT")
        a3 = sum(area3d(o) for o in objs)
        au = sum(uv_area(o, "lightmap") for o in objs)
        dens = S * math.sqrt(au / a3)
        print(f"  page {S}: {a3:.1f} m2, {dens:.1f} px/m")
        chosen = (S, dens)
        if dens >= 30:
            break
        bpy.ops.object.mode_set(mode="EDIT")
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    return chosen


def srgb_encode(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def denoise_image(img, S):
    """OIDN through the compositor's Denoise node: the image goes in as a float image and comes back as a float array."""
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
    bpy.data.scenes.remove(sc)
    return a.reshape(S, S, 4)


HIDE_IN_BAKE = ("Skylight_Glass",)       # transparent panes: hidden while baking, so the moon shines through the openings


def stage_bake():
    import time
    stage_work()
    exp = make_export_objects()
    bpy.data.collections["Art"].hide_render = True
    bpy.data.collections["Art"].hide_viewport = True
    setup_cycles(SAMPLES, bake=True)
    report = {}
    for n, mats in enumerate(GROUPS):
        t0 = time.time()
        objs = [exp[m] for m in mats if m in exp]
        print(f"lightmap {n}: {[o.name for o in objs]}")
        S, dens = lightmap_uv(objs, PAGES[n])
        img = bpy.data.images.new(f"LM_{n}", S, S, alpha=False, float_buffer=True)
        img.colorspace_settings.name = "Non-Color"
        for o in objs:
            for slot in o.material_slots:
                nt = slot.material.node_tree
                node = nt.nodes.new("ShaderNodeTexImage")
                node.name = "BAKE_TARGET"
                node.image = img
                nt.nodes.active = node
                node.select = True
        for m in HIDE_IN_BAKE:
            if m in exp:
                exp[m].hide_render = True
        select_only(objs)
        for o in objs:
            o.data.uv_layers.active = o.data.uv_layers["lightmap"]
        bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
        for m in HIDE_IN_BAKE:
            if m in exp:
                exp[m].hide_render = False
        a = denoise_image(img, S)
        rgb = a[..., :3]
        peak = rgb.max(axis=2)
        pc = np.percentile(peak[peak > 1e-5], [50, 90, 99, 99.5, 100]) if (peak > 1e-5).any() else [1.0] * 5
        scale = float(pc[3])                                 # the 99.5th percentile of the lit texels maps to white; the few hotter ones (right under a spot) clip
        print('  texel percentiles p50 p90 p99 p99.5 max:', [round(float(v), 3) for v in pc])
        out = np.ones((S, S, 4), np.float32)
        out[..., :3] = srgb_encode(rgb / scale)
        png = bpy.data.images.new(f"LM_{n}_png", S, S, alpha=False)
        png.colorspace_settings.name = "Non-Color"
        png.pixels.foreach_set(out.ravel())
        png.filepath_raw = str(stage_work() / f"{SCENE}_{n}.png")
        png.file_format = "PNG"
        png.save()
        for o in objs:
            for slot in o.material_slots:
                m = slot.material
                m["lightmap"] = LM_URL.format(n)
                m["lightmap_intensity"] = round(math.pi * scale, 4)
                nt = m.node_tree
                for nd in [nd for nd in nt.nodes if nd.name.startswith("BAKE_TARGET")]:
                    nt.nodes.remove(nd)
        report[n] = {"size": S, "px_per_m": round(dens, 1), "scale": round(scale, 4), "p50_p90_p99_p995_max": [round(float(v), 3) for v in pc], "samples": SAMPLES,
                     "device": bpy.context.scene.cycles.device, "seconds": round(time.time() - t0), "mean": round(float(rgb.mean()), 4), "materials": mats}
        print("  baked", report[n])
        bpy.data.images.remove(img)
        bpy.data.images.remove(png)
    (stage_work() / "lightmaps.json").write_text(json.dumps(report, indent=1))
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Art"].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


def scrub_ui_paths():
    """The startup layout's file browser remembers the machine's home folder; the .blend is public, so it keeps "//" instead."""
    for sc in bpy.data.screens:
        for a in sc.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"_" * 1000
                    sp.params.directory = b"//"


KEEP_PROPS = {"lightmap", "lightmap_intensity"}      # the only custom properties this scene carries (on materials, for the page)
SYS_KEEP = ("cycles", "eevee")                       # bundled render engines' add-on settings, never exported, kept


def set_path(owner, attr, value):
    """Blender keeps a path in a fixed buffer: a shorter string leaves the old one's tail behind it in the saved file, so blank it first."""
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private():
    """The .blend, the GLB (export_extras) and the stills are public. Other installed add-ons put their own custom properties on the scene and
    the world (some hold absolute paths of the machine's user folder), and paths of the work folder land in render settings and image paths.
    Strip all of that here, so a re-run on any machine stays clean."""
    kinds = ("scenes", "worlds", "objects", "meshes", "materials", "collections", "cameras", "lights", "images", "node_groups", "screens",
             "window_managers", "workspaces")
    dropped = 0
    for kind in kinds:
        for idb in getattr(bpy.data, kind):
            # Blender 5 keeps add-ons' bpy.props storage apart from the user's custom properties; the glTF exporter writes both as extras
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
                    if st is not idb and k.startswith(SYS_KEEP):      # Cycles' and EEVEE's own settings (light, visibility, sampling) stay
                        continue
                    try:
                        del st[k]
                        dropped += 1
                    except Exception as e:
                        print("  could not drop custom property", idb.name, k, e)
    print("SCRUB dropped", dropped, "custom properties")
    for sc in bpy.data.scenes:
        set_path(sc.render, "filepath", "//")
        for p in sc.render.bl_rna.properties:                    # no stamp metadata (the .blend's own path, the host name) in the stills
            if p.identifier.startswith("use_stamp") and not p.is_readonly:
                setattr(sc.render, p.identifier, False)
    base = BLEND.parent
    for im in bpy.data.images:
        if im.packed_file or im.source != "FILE" or not im.filepath:
            continue
        p = Path(bpy.path.abspath(im.filepath))
        try:
            rel = "//" + os.path.relpath(p, base).replace("\\", "/")
        except ValueError:                                        # another drive: nothing relative to say, so keep only the name
            rel = "//" + p.name
        set_path(im, "filepath", rel)
    scrub_ui_paths()


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0                # no .blend1 backups next to it
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    scrub_private()                                                   # after the first save, so `//` resolves against the .blend
    bpy.ops.wm.save_mainfile()


# ---------------------------------------------------------------- export
def stage_export():
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    bpy.data.collections["Art"].hide_viewport = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in exp.objects:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = stage_work() / f"{SCENE}_raw.glb"
    scrub_private()                                   # export_extras=True: only the materials' lightmap extras may go out
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False, export_animations=False)
    print("EXPORTED", raw, raw.stat().st_size)
    bpy.data.collections["Art"].hide_viewport = False
    exp.hide_viewport = exp.hide_render = True


# ---------------------------------------------------------------- the review stills
def look_cam(name, loc, target, fov_v=75.0, ortho=None, roll=0.0):
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
    if target is not None:
        ob.rotation_euler = (B(target) - B(loc)).to_track_quat("-Z", "Y").to_euler()
    else:
        ob.rotation_euler = (0, 0, roll)
    return ob


def strip_jpeg_comments(path):
    """Blender writes its render metadata (Cycles' timings and sample counts) as JPEG comment segments even with every stamp off; drop them."""
    b = path.read_bytes()
    out, i = bytearray(b[:2]), 2
    while i < len(b) and b[i] == 0xFF and b[i + 1] != 0xDA:            # up to the start of scan
        n = int.from_bytes(b[i + 2:i + 4], "big")
        if b[i + 1] != 0xFE:
            out += b[i:i + 2 + n]
        i += 2 + n
    out += b[i:]
    path.write_bytes(bytes(out))


def stage_render():
    sc = bpy.context.scene
    STILLS.mkdir(parents=True, exist_ok=True)
    scrub_private()                                   # among others: every use_stamp_* off, so the JPEGs carry no Blender:File (a local path)
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
        bpy.data.collections["Export"].hide_viewport = True
    setup_cycles(arg("--render-samples", 128, int))     # the stills' own count, so --stage all can bake at 512 and render at 128
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = arg("--noise", 0.03, float)
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    expo = arg("--exposure", 0.0, float)              # 0, as the pilot: the stills show the light the lightmaps hold
    which = arg("--only", "all")
    if ENGINE.upper().startswith("EEVEE"):
        ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
        sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in ids else "BLENDER_EEVEE_NEXT"
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    arrive, face = K["arrive"], K["face"]
    hx = HOMES[3][0]
    shots = {
        "1_arrival": look_cam("arrival", (arrive[0], 1.6, arrive[2]), (arrive[0] + face[0] * 3, 1.6, arrive[2] + face[1] * 3), 75.0),
        "2_wide": look_cam("wide", (HX - 0.9, H - 0.75, Z1 - 0.6), (-1.6, 0.6, CZ - 6.0), 72.0),
        "3_detail": look_cam("detail", (hx - 2.6, 1.55, HOMES[3][1] + 2.9), (hx + 0.2, 1.25, HOMES[3][1] - 0.6), 55.0),
    }
    plan = look_cam("plan", (0, H + 8, CZ), None, ortho=(Z1 - Z0) + 1.2, roll=-math.pi / 2)
    arts = list(bpy.data.collections["Art"].objects) + list(bpy.data.collections["Standins"].objects)
    cut_plan = [o for o in arts if o.name.startswith(("Ceiling_", "Skylight_", "Track_", "Spot_", "Cornice"))]
    todo = [(k, v, (1920, 1080)) for k, v in shots.items()] + [("4_plan", plan, (1800, 900))]
    for key, cam, (w, h) in todo:
        if which not in ("all", key):
            continue
        sc.camera = cam
        sc.view_settings.exposure = expo + (1.5 if key == "4_plan" else 0.0)      # the plan (the owner's sheet only) is lifted to read on a phone
        for o in arts:
            o.visible_camera = True
        for o in {"4_plan": cut_plan}.get(key, []):
            o.visible_camera = False                      # a cut-away view: these stay in the hall for the light and the shadows, the camera just does not see them
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, arg("--scale", 100, int)
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        path = STILLS / f"{key}.jpg" if key != "4_plan" else stage_work() / "plan.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 400_000 and q > 40 and key != "4_plan":
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        strip_jpeg_comments(path)
        print("STILL", key, path.stat().st_size, "q", q)
    for o in arts:
        o.visible_camera = True


if __name__ == "__main__":
    if STAGE in ("art", "all"):
        build_all()
        save_blend()
    if STAGE in ("bake", "all"):
        stage_bake()
    if STAGE in ("export", "all"):
        stage_export()
    if STAGE in ("axes", "all"):
        stage_axes()
        save_blend()
    if STAGE in ("render", "all"):
        stage_render()
