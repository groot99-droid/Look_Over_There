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

Version 2 takes its look from the owner's Chronicle Museum (Earth_Worldbuild, _Museum: web/js/procroom.js, doors.js, matlib.js, build_layout.py): its moulding
profiles (skirting, dado, picture rail, cornice), wall and trim colours, salon-grid hang with bevelled frames chosen by era, picture lights, door sconces,
chandeliers and laylights, block pedestals, the Doric pediment door, and its Poly Haven chandelier and bench (CC0, copied into blender/models/galleries/).

The wing (2026-11-24): two doorways in the middle bay of the long walls (z = -10) lead to the side galleries, scene `galleries_wing`
(tools/blender/build_galleries_wing.py): a Doric doorway in the west wall to the natural-history hall, an arched one in the east wall to the history
gallery. They are cut into the walls here: Wall_W and Wall_E of the collision file are each split around a 1.8 by 2.6 m (Doric) or 1.8 by 2.1 m
(arched, under a fixed tympanum) opening, and the two pairs of closed leaves (DoorLeaf_wing_w_A/B, DoorLeaf_wing_e_A/B, their own nodes in the
GLB, origin at the hinge) are written to the file's `doors`. `--stage export` writes world/galleries.json: the layout's file with exactly those two
changes. Link_/Arrive_ empties (the `Layout` collection) mark where the page's links should start and arrive; they are not in the file.
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
SIDE_Z = ROWS[1] - STEP / 2                   # the wing's doorways: the middle bay of the long walls (z = -10)
SIDE_W = 1.8                                  # each a pair of 0.9 m leaves, as the wing's side of the same doorway
SIDE_DOORS = [("+x", "doric", "wing_w", 2.6, "NATURAL HISTORY"), ("-x", "arch", "wing_e", 2.1, "HISTORY GALLERY")]   # (wall, style, door id, leaves' top, plaque)
SIDE_GAP = SIDE_W / 2 + 0.22 + 0.12 + 0.32    # the mouldings and the wainscot panels stop this far either side of a doorway's centre (its pilasters' outer edge)


def hall_colliders():
    """The layout's colliders with the two doorways cut: Wall_W and Wall_E each become the piece south of the opening (keeping the name), the piece
    north of it (_N) and the head over it (_Head). Everything else is the layout's, in its order."""
    out = []
    for c in L["world"]["colliders"]:
        door = [d for d in SIDE_DOORS if c["s"] == "Wall_" + ("W" if d[0] == "+x" else "E")]
        if not door:
            out.append(c)
            continue
        top = door[0][3]
        a0, a1 = SIDE_Z - SIDE_W / 2, SIDE_Z + SIDE_W / 2
        mn, mx = c["min"], c["max"]
        out.append({"s": c["s"], "min": [mn[0], mn[1], a1], "max": [mx[0], mx[1], mx[2]]})
        out.append({"s": c["s"] + "_N", "min": [mn[0], mn[1], mn[2]], "max": [mx[0], mx[1], a0]})
        out.append({"s": c["s"] + "_Head", "min": [mn[0], top, a0], "max": [mx[0], mx[1], a1]})
    return out


HALL_COLLIDERS = hall_colliders()
COLLIDERS = {c["s"]: c for c in HALL_COLLIDERS}


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
        im = bpy.data.images.load(str(TEX / fn if "/" not in fn else ROOT / fn))      # a bare name is in TEX; a path is from the repo root
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


CHANDELIER = "blender/models/galleries/ph-chandelier-02/Chandelier_02_1k.gltf"          # Poly Haven, CC0 (the Chronicle Museum's hall chandelier)
BENCH = "blender/models/galleries/ph-bench/painted_wooden_bench_1k.gltf"   # Poly Haven, CC0 (the Chronicle Museum's hall bench)


def make_materials():
    """The Chronicle Museum's palette (Earth_Worldbuild _Museum, web/js/matlib.js and build_layout.ROOM_STYLE), on this hall's CC0 textures: a classical red wall
    (its Classical Antiquity room, lifted a little for a night bake), cream painted trim (#efe6d6), a white ceiling, dark marble skirting and plinth dies under white
    marble lips, gilt (#f0c56a), brass (#d3a35d), dark wood and black lacquer frames."""
    material("Floor_Parquet", diff="herringbone_parquet_diff_1k.jpg", tint=(0.80, 0.70, 0.60), rough=0.6, tile=3.4)
    material("Floor_Marble", diff="marble_01_diff_1k.jpg", tint=(0.80, 0.80, 0.78), rough=0.25, tile=1.5)
    material("Wall_Paint", diff="plastered_wall_04_diff_1k.jpg", tint=(0.60, 0.19, 0.12), rough=0.9, tile=3.2)
    material("Ceiling_Paint", diff="plastered_wall_04_diff_1k.jpg", tint=(1.0, 0.97, 0.90), rough=0.95, tile=3.2)
    material("Wainscot_Wood", diff="dark_wood_diff_1k.jpg", tint=(0.85, 0.78, 0.74), rough=0.5, tile=0.9)
    material("Door_Wood", diff="dark_wood_diff_1k.jpg", rough=0.5, tile=0.9)
    material("Trim_Paint", diff="plastered_wall_04_diff_1k.jpg", tint=(0.95, 0.88, 0.76), rough=0.6, tile=1.0)
    material("Skirting_Marble", diff="marble_01_diff_1k.jpg", tint=(0.11, 0.095, 0.09), rough=0.3, tile=1.0)
    material("Marble_Dark", diff="marble_01_diff_1k.jpg", tint=(0.12, 0.10, 0.095), rough=0.3, tile=1.0)
    material("Marble_White", diff="marble_01_diff_1k.jpg", tint=(0.95, 0.93, 0.89), rough=0.3, tile=1.0)
    material("Frame_Gold", color=(0.87, 0.56, 0.14), rough=0.32, metal=0.9)
    material("Frame_Wood", diff="dark_wood_diff_1k.jpg", tint=(0.75, 0.62, 0.55), rough=0.45, tile=0.6)
    material("Frame_Black", color=(0.014, 0.013, 0.013), rough=0.25)
    material("Metal_Dark", color=(0.03, 0.03, 0.035), rough=0.4, metal=0.8)
    material("Metal_Brass", color=(0.65, 0.37, 0.11), rough=0.38, metal=0.9)
    material("Chandelier_Gilt", diff=CHANDELIER.rsplit("/", 1)[0] + "/textures/Chandelier_02_diff_1k.jpg", rough=0.35, metal=0.8)
    material("Bench_Paint", diff=BENCH.rsplit("/", 1)[0] + "/textures/painted_wooden_bench_diff_1k.jpg", rough=0.6)
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


def finish(name, bm, mat, coll, smooth=False, tile=None, sharp_deg=35, keep_uv=False, recalc=True):
    for e in bm.edges:
        if smooth and len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) < math.radians(sharp_deg)
        else:
            e.smooth = not (len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(1))
    for f in bm.faces:
        f.smooth = smooth
    if recalc and not keep_uv:                        # a lone panel (or an open sweep) keeps the winding it was built with (it faces the room)
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


def part(name, mat, build, smooth=False, tile=None, coll=None, recalc=True):
    bm = bmesh.new()
    build(bm)
    return finish(name, bm, mat, coll or ART, smooth, tile, recalc=recalc)


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
        part(s, "Wall_Paint", lambda bm: cube(bm, (mn[0], max(DADO, mn[1]), mn[2]), (mx[0], mx[1], mx[2])))
        if mn[1] < DADO:                                                                        # a doorway's head piece is all paint
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


def ceil_ring(bm, x0, x1, z0, z1, t, y0, y1):
    """A rectangular band under the ceiling, outer edges x0..x1, z0..z1, `t` wide, from y0 to y1: the long sides full length, the short ones between them
    (no two boxes share a face, so nothing flickers)."""
    cube(bm, (x0, y0, z0), (x1, y1, z0 + t))
    cube(bm, (x0, y0, z1 - t), (x1, y1, z1))
    cube(bm, (x0, y0, z0 + t), (x0 + t, y1, z1 - t))
    cube(bm, (x1 - t, y0, z0 + t), (x1, y1, z1 - t))


def build_skylights():
    """Four skylights over the middle aisle, between the plinth rows, dressed as the Chronicle Museum's laylights (its FX laylight: a lit pane in a painted trim
    frame): a cream coffer of two stepped bands round each opening, a dark metal frame lining it, glazing bars, and a frosted pane (Skylight_Glass: transparent and
    faintly lit, no lightmap). The moon of the bake shines in through them."""
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

    def coffers(bm):
        for zc in BAYS:
            ceil_ring(bm, -s - 0.34, s + 0.34, zc - s - 0.34, zc + s + 0.34, 0.20, y0 - 0.035, y0)       # the outer flat band
            ceil_ring(bm, -s - 0.14, s + 0.14, zc - s - 0.14, zc + s + 0.14, 0.14, y0 - 0.08, y0)        # the inner, deeper step, flush with the opening
    part("Laylight_Coffers", "Trim_Paint", coffers)


# ---------------------------------------------------------------- mouldings (the Chronicle Museum's profiles, procroom.js PROFILES, scaled to a 5 m hall)
# A profile is a closed polygon of (u, y): u metres out from the wall face, y the height. It is swept along a wall run and mitred at the corners.
SKIRT_P = [(0, 0), (0.035, 0), (0.035, 0.2), (0.025, 0.215), (0.032, 0.245), (0.02, 0.27), (0, 0.28)]
DADO_P = [(0, DADO - 0.05), (0.04, DADO - 0.05), (0.055, DADO - 0.025), (0.04, DADO + 0.025), (0, DADO + 0.03)]
RAIL_P = [(0, RAIL - 0.07), (0.035, RAIL - 0.07), (0.048, RAIL - 0.04), (0.03, RAIL), (0, RAIL)]
_CORNICE_7M = [(0, 6.5), (0.03, 6.5), (0.03, 6.58), (0.08, 6.63), (0.08, 6.7), (0.15, 6.76), (0.17, 6.84), (0.3, 6.93), (0.36, 7.0), (0, 7.0)]
CORNICE_P = [(u * 0.8, H - (7.0 - v) * 0.8) for u, v in _CORNICE_7M]          # the room cornice (6.5 to 7 m there): 0.4 m tall, 0.29 m deep here
PILASTER_X = DOOR_W / 2 + 0.22 + 0.12                                          # inner edge of the door's flat pilasters, from the door's centre
PILASTER_W = 0.32
MOULD_GAP = PILASTER_X + PILASTER_W                                            # the skirting, dado and wainscot stop at the pilasters' outer edges


def wall_runs(gap, side=False):
    """The hall's wall runs for a sweep: (p0, p1, inward normal, normal of the wall at p0's corner or None, the same at p1), plan points (x, z) on the inner faces.
    With `gap` the south wall is cut at the door (from door.at's x - gap to + gap); with `side` the long walls are cut at the wing's doorways (SIDE_GAP)."""
    W, N, E, S = (1, 0), (0, 1), (-1, 0), (0, -1)
    if side:
        g = SIDE_GAP
        runs = [((-HX, Z1), (-HX, SIDE_Z + g), W, S, None), ((-HX, SIDE_Z - g), (-HX, Z0), W, None, N), ((-HX, Z0), (HX, Z0), N, W, E),
                ((HX, Z0), (HX, SIDE_Z - g), E, N, None), ((HX, SIDE_Z + g), (HX, Z1), E, None, S)]
    else:
        runs = [((-HX, Z1), (-HX, Z0), W, S, N), ((-HX, Z0), (HX, Z0), N, W, E), ((HX, Z0), (HX, Z1), E, N, S)]
    if gap:
        dx = DOOR[0]
        runs += [((HX, Z1), (dx + gap, Z1), S, E, None), ((dx - gap, Z1), (-HX, Z1), S, None, W)]
    else:
        runs.append(((HX, Z1), (-HX, Z1), S, E, W))
    return runs


def sweep_run(bm, run, profile):
    """Sweep a closed profile along one wall run, mitred where the run meets another wall (the offset there runs along both normals), capped at both ends."""
    p0, p1, n, a0, a1 = run
    rings = []
    for (px, pz), adj in ((p0, a0), (p1, a1)):
        off = (n[0] + adj[0], n[1] + adj[1]) if adj else n
        rings.append([bm.verts.new(B((px + u * off[0], y, pz + u * off[1]))) for u, y in profile])
    a, b = rings
    m = len(profile)
    for j in range(m):
        k = (j + 1) % m
        bm.faces.new((a[j], b[j], b[k], a[k]))
    bm.faces.new(a)
    bm.faces.new(list(reversed(b)))


def build_mouldings():
    """The Chronicle Museum's room mouldings: a dark marble skirting (its hall's), a cream dado rail capping a panelled dark wood wainscot, a cream picture rail, and
    its stepped room cornice. Each is a profile swept along the walls and mitred at the corners. The skirting and the wainscot panels reach above 0.2 m, so they are
    one piece per wall (each lies within 5 cm of its wall); the rails and the cornice are one piece each (lower than 0.2 m, or overhead)."""
    for i, run in enumerate(wall_runs(MOULD_GAP, side=True)):
        part(f"Skirting_{i}", "Skirting_Marble", lambda bm: sweep_run(bm, run, SKIRT_P))
    part("Trim_Dado", "Trim_Paint", lambda bm: [sweep_run(bm, r, DADO_P) for r in wall_runs(MOULD_GAP, side=True)])
    part("Trim_PictureRail", "Trim_Paint", lambda bm: [sweep_run(bm, r, RAIL_P) for r in wall_runs(None)])
    part("Cornice", "Trim_Paint", lambda bm: [sweep_run(bm, r, CORNICE_P) for r in wall_runs(None)])
    part("Cornice_Frieze", "Trim_Paint", lambda bm: [sweep_run(bm, r, [(0, H - 0.52), (0.022, H - 0.52), (0.022, H - 0.46), (0, H - 0.46)]) for r in wall_runs(None)])

    # the wainscot's raised panels: bolection rings 1.5 cm proud between the skirting and the dado, about 1.25 m apart
    dx = DOOR[0]
    lo_y, hi_y = 0.36, DADO - 0.10
    for n in WALLS:
        ax, _ = WALLS[n]
        lo, hi = (Z0, Z1) if ax == "z" else (-HX, HX)
        spans = [(lo, hi)] if n != "-z" else [(lo, dx - MOULD_GAP), (dx + MOULD_GAP, hi)]
        if n in ("+x", "-x"):                                                                   # the wing's doorways
            spans = [(lo, SIDE_Z - SIDE_GAP), (SIDE_Z + SIDE_GAP, hi)]

        def panels(bm, spans=spans, n=n):
            for s0, s1 in spans:
                k = max(1, round((s1 - s0) / 1.25))
                w = (s1 - s0) / k
                for i in range(k):
                    a0, a1 = s0 + i * w + 0.09, s0 + (i + 1) * w - 0.09
                    t = 0.045
                    wall_box(bm, n, a0, a1, lo_y, lo_y + t, 0.0, 0.015)
                    wall_box(bm, n, a0, a1, hi_y - t, hi_y, 0.0, 0.015)
                    wall_box(bm, n, a0, a0 + t, lo_y + t, hi_y - t, 0.0, 0.015)
                    wall_box(bm, n, a1 - t, a1, lo_y + t, hi_y - t, 0.0, 0.015)
        part(f"Wainscot_Panels_{WALL_NAME[n]}", "Wainscot_Wood", panels)


def prism(bm, normal, a, w, y0, h, d0, d1):
    """A triangular prism on a wall (a pediment): base `w` wide centred on `a` at height y0, apex h above, from d0 to d1 into the room."""
    pts = [(a - w / 2, y0), (a + w / 2, y0), (a, y0 + h)]
    f = [bm.verts.new(B(on_wall(normal, x, y, d1))) for x, y in pts]
    b = [bm.verts.new(B(on_wall(normal, x, y, d0))) for x, y in pts]
    bm.faces.new(f)
    bm.faces.new(list(reversed(b)))
    for i in range(3):
        j = (i + 1) % 3
        bm.faces.new((f[i], b[i], b[j], f[j]))


def build_door():
    """The door, in the Chronicle Museum's Doric pediment surround (doors.js, `doric-pediment`: white marble casing, gilt accents, columns and a pediment). Below head
    height everything stays within 5 cm of the wall, so its columns are flat pilasters here; the entablature and the pediment above the door project 12 cm. The leaves
    are a closed double door (the page's prompt at door.at is unchanged), and the EXIT sign sits on the frieze."""
    dx = DOOR[0]
    x0, x1 = dx - DOOR_W / 2, dx + DOOR_W / 2
    cw = 0.22

    def casing(bm):
        wall_box(bm, "-z", x0 - cw, x0, 0.0, DOOR_H + cw, 0.0, 0.03)
        wall_box(bm, "-z", x1, x1 + cw, 0.0, DOOR_H + cw, 0.0, 0.03)
        wall_box(bm, "-z", x0 - cw, x1 + cw, DOOR_H, DOOR_H + cw, 0.0, 0.03)
    part("Door_Casing", "Marble_White", casing)

    def pilasters(bm):
        for k in (-1, 1):
            a0, a1 = sorted((dx + k * PILASTER_X, dx + k * (PILASTER_X + PILASTER_W)))
            wall_box(bm, "-z", a0 - 0.03, a1 + 0.03, 0.0, 0.30, 0.0, 0.045)                       # the base block
            wall_box(bm, "-z", a0, a1, 0.30, DOOR_H + 0.02, 0.0, 0.032)                           # the shaft
            for f in range(3):                                                                    # three flutes, as raised fillets between them
                c = a0 + (f + 1) * (a1 - a0) / 4
                wall_box(bm, "-z", c - 0.012, c + 0.012, 0.42, DOOR_H - 0.10, 0.032, 0.040)
    part("Door_Pilasters", "Marble_White", pilasters)

    def capitals(bm):
        for k in (-1, 1):
            a0, a1 = sorted((dx + k * PILASTER_X, dx + k * (PILASTER_X + PILASTER_W)))
            wall_box(bm, "-z", a0 - 0.04, a1 + 0.04, DOOR_H + 0.02, DOOR_H + 0.12, 0.0, 0.05)
            wall_box(bm, "-z", a0 - 0.06, a1 + 0.06, DOOR_H + 0.12, DOOR_H + 0.22, 0.0, 0.06)
    part("Door_Capitals", "Frame_Gold", capitals)

    ew = PILASTER_X + PILASTER_W + 0.12                     # the entablature's half-width
    y = DOOR_H + 0.22

    def entablature(bm):
        wall_box(bm, "-z", dx - ew, dx + ew, y, y + 0.12, 0.0, 0.075)                             # architrave
        wall_box(bm, "-z", dx - ew, dx + ew, y + 0.12, y + 0.32, 0.0, 0.06)                       # frieze
        wall_box(bm, "-z", dx - ew - 0.05, dx + ew + 0.05, y + 0.32, y + 0.40, 0.0, 0.13)         # cornice
        prism(bm, "-z", dx, 2 * ew + 0.1, y + 0.40, 0.58, 0.0, 0.13)                              # the pediment
    part("Door_Entablature", "Marble_White", entablature)
    part("Door_Tympanum", "Trim_Paint", lambda bm: prism(bm, "-z", dx, 2 * ew - 0.45, y + 0.47, 0.42, 0.13, 0.135))

    def leaves(bm):
        for a0, a1 in ((x0, dx - 0.004), (dx + 0.004, x1)):
            wall_box(bm, "-z", a0, a1, 0.0, DOOR_H, 0.0, 0.035)
            for (yy0, yy1) in ((0.18, 1.05), (1.25, DOOR_H - 0.18)):                              # two raised fields per leaf
                wall_box(bm, "-z", a0 + 0.14, a1 - 0.14, yy0, yy1, 0.035, 0.045)
    part("Door_Leaves", "Door_Wood", leaves)

    def hardware(bm):
        for a in (dx - 0.06, dx + 0.035):
            wall_box(bm, "-z", a, a + 0.025, 0.85, 1.25, 0.035, 0.048)                             # pull handles
        for a0, a1 in ((x0 + 0.2, dx - 0.2), (dx + 0.2, x1 - 0.2)):
            wall_box(bm, "-z", a0, a1, 0.0, 0.22, 0.035, 0.04)                                    # kick plates
    part("Door_Hardware", "Metal_Brass", hardware)


# ---------------------------------------------------------------- the wing's two doorways
DOORS_C = LAYOUT_C = None
NVEC = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}       # into the hall
ADIR = {"+x": (0, 0, 1), "-x": (0, 0, 1), "+z": (1, 0, 0), "-z": (1, 0, 0)}         # the way `a` (along the wall) runs


def door_leaf(normal, a0, a1, top, hinge_end, name):
    """One leaf of a side doorway: its own object (the Doors collection) with its origin at the hinge, so the page can find it by name and swing it;
    3.5 cm proud of the wall with two raised fields. Custom properties for the collision file's `doors` (closed_yaw_deg: the leaf's local +X runs
    from the hinge along it, as the page reads it; swing_deg turns it into the hall)."""
    bm = bmesh.new()
    wall_box(bm, normal, a0, a1, 0.0, top, 0.0, 0.035)
    for yy0, yy1 in ((0.18, top * 0.38), (top * 0.45, top - 0.18)):
        wall_box(bm, normal, a0 + 0.12, a1 - 0.12, yy0, yy1, 0.035, 0.045)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    meet = a1 - 0.06 if hinge_end == 0 else a0 + 0.035                          # a wooden pull by the meeting edge: part of the leaf, so it swings with it
    wall_box(bm, normal, meet, meet + 0.025, 0.95, 1.3, 0.045, 0.058)
    bm.loops.layers.uv.new("UVMap")
    box_uv(bm, TILES["Door_Wood"])
    hinge = on_wall(normal, a0 if hinge_end == 0 else a1, 0.0, 0.0)
    runs_dir = Vector(ADIR[normal]) * (1 if hinge_end == 0 else -1)            # game direction from the hinge along the leaf
    th = math.atan2(-runs_dir.z, runs_dir.x)                                     # three.js: local +X -> (cos th, -sin th)
    into = Vector(NVEC[normal])
    swing = 95.0 if math.sin(math.atan2(-into.z, into.x) - th) > 0 else -95.0    # turning by +95 from th must head into the hall
    M = Matrix.Translation(B(hinge)) @ Matrix.Rotation(th, 4, "Z")
    bmesh.ops.transform(bm, matrix=M.inverted(), verts=bm.verts)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS["Door_Wood"])
    ob = bpy.data.objects.new(name, me)
    ob.matrix_world = M
    DOORS_C.objects.link(ob)
    ob["width"] = round(a1 - a0, 3)
    ob["height"] = round(top, 3)
    ob["closed_yaw_deg"] = round(math.degrees(th), 1)
    ob["swing_deg"] = swing
    ob["state"] = "closed"
    return ob


def layout_empty(name, pos, face=None):
    ob = bpy.data.objects.new(name, None)
    ob.location = B(pos)
    if face:
        ob.rotation_euler = (0, 0, math.atan2(face[0], face[1]))                 # its -Y axis looks the game way `face`
    ob.empty_display_size = 0.3
    LAYOUT_C.objects.link(ob)
    return ob


def doric_side(normal, a, w, h, tag):
    """The Doric pediment surround of the main door (build_door), on a long wall, around a w x h opening; the pediment stays under the picture rail."""
    pil_x = w / 2 + 0.22 + 0.12
    cw = 0.22

    def casing(bm):
        wall_box(bm, normal, a - w / 2 - cw, a - w / 2, 0.0, h + cw, 0.0, 0.03)
        wall_box(bm, normal, a + w / 2, a + w / 2 + cw, 0.0, h + cw, 0.0, 0.03)
        wall_box(bm, normal, a - w / 2 - cw, a + w / 2 + cw, h, h + cw, 0.0, 0.03)
    part(f"Door_{tag}_Casing", "Marble_White", casing)

    def pilasters(bm):
        for k in (-1, 1):
            a0, a1 = sorted((a + k * pil_x, a + k * (pil_x + PILASTER_W)))
            wall_box(bm, normal, a0 - 0.03, a1 + 0.03, 0.0, 0.30, 0.0, 0.045)
            wall_box(bm, normal, a0, a1, 0.30, h + 0.02, 0.0, 0.032)
            for f in range(3):
                c = a0 + (f + 1) * (a1 - a0) / 4
                wall_box(bm, normal, c - 0.012, c + 0.012, 0.42, h - 0.10, 0.032, 0.040)
    part(f"Door_{tag}_Pilasters", "Marble_White", pilasters)

    def capitals(bm):
        for k in (-1, 1):
            a0, a1 = sorted((a + k * pil_x, a + k * (pil_x + PILASTER_W)))
            wall_box(bm, normal, a0 - 0.04, a1 + 0.04, h + 0.02, h + 0.12, 0.0, 0.05)
            wall_box(bm, normal, a0 - 0.06, a1 + 0.06, h + 0.12, h + 0.22, 0.0, 0.06)
    part(f"Door_{tag}_Capitals", "Frame_Gold", capitals)
    ew = pil_x + PILASTER_W + 0.12
    y = h + 0.22

    def entablature(bm):
        wall_box(bm, normal, a - ew, a + ew, y, y + 0.12, 0.0, 0.075)
        wall_box(bm, normal, a - ew, a + ew, y + 0.12, y + 0.32, 0.0, 0.06)
        wall_box(bm, normal, a - ew - 0.05, a + ew + 0.05, y + 0.32, y + 0.40, 0.0, 0.13)
        prism(bm, normal, a, 2 * ew + 0.1, y + 0.40, 0.50, 0.0, 0.13)
    part(f"Door_{tag}_Entablature", "Marble_White", entablature)
    part(f"Door_{tag}_Tympanum", "Trim_Paint", lambda bm: prism(bm, normal, a, 2 * ew - 0.45, y + 0.47, 0.36, 0.13, 0.135))
    return y + 0.22                                                              # the frieze's middle: the plaque's height


def arch_ring(bm, normal, a, spr, r0, r1, d0, d1, seg=20):
    """A semicircular ring on a wall (centre a, springing line spr, radii r0..r1, d0..d1 into the hall): one closed block per segment."""
    for i in range(seg):
        t0, t1 = math.pi * i / seg, math.pi * (i + 1) / seg
        pts = []
        for d in (d0, d1):
            for rr, t in ((r0, t0), (r1, t0), (r1, t1), (r0, t1)):
                pts.append(bm.verts.new(B(on_wall(normal, a + rr * math.cos(t), spr + rr * math.sin(t), d))))
        b, f = pts[:4], pts[4:]
        bm.faces.new(b)
        bm.faces.new(f)
        for k in range(4):
            j = (k + 1) % 4
            bm.faces.new((b[k], b[j], f[j], f[k]))


def arch_side(normal, a, w, crown, tag):
    """The Chronicle Museum's round-arch-keystone door (doors.js), as the wing's history gallery has it: marble jambs to the springing line, a marble
    arch ring, an outer dark marble order and a keystone; the leaves stop at the springing line under a fixed wooden tympanum."""
    cw, r = 0.22, w / 2
    spr = crown - r

    def jambs(bm):                                                               # below head height: 4.5 cm proud at most (the layout check's rule)
        wall_box(bm, normal, a - r - cw, a - r, 0.0, spr - 0.12, 0.0, 0.045)
        wall_box(bm, normal, a + r, a + r + cw, 0.0, spr - 0.12, 0.0, 0.045)
    part(f"Door_{tag}_Jambs", "Marble_White", jambs)

    def arch(bm):                                                                # the imposts and the ring: overhead (from 1.98 m)
        wall_box(bm, normal, a - r - cw - 0.04, a - r + 0.02, spr - 0.12, spr, 0.0, 0.07)
        wall_box(bm, normal, a + r - 0.02, a + r + cw + 0.04, spr - 0.12, spr, 0.0, 0.07)
        arch_ring(bm, normal, a, spr, r, r + cw, 0.0, 0.06)
    part(f"Door_{tag}_Arch", "Marble_White", arch)

    def outer(bm):
        arch_ring(bm, normal, a, spr, r + cw, r + cw + 0.14, 0.0, 0.035)
        wall_box(bm, normal, a - 0.17, a + 0.17, crown + cw - 0.32, crown + cw + 0.18, 0.0, 0.11)
    part(f"Door_{tag}_Order", "Marble_Dark", outer)

    def tympanum(bm):
        seg = 16
        c = bm.verts.new(B(on_wall(normal, a, spr, 0.03)))
        rim = [bm.verts.new(B(on_wall(normal, a + r * math.cos(math.pi * i / seg), spr + r * math.sin(math.pi * i / seg), 0.03))) for i in range(seg + 1)]
        for i in range(seg):
            f = bm.faces.new((c, rim[i], rim[i + 1]))
            f.normal_update()
            if f.normal.dot(B(NVEC[normal])) < 0:
                f.normal_flip()
    part(f"Door_{tag}_Tympanum", "Door_Wood", tympanum, recalc=False)
    return crown + cw + 0.46                                                     # the plaque's height, over the keystone


def build_side_doors():
    """The wing's two doorways: the surround, two closed leaves, the reveal linings of the opening (its jambs and head, 3 cm thick, so nothing stands
    where the wall pieces are not), a plaque naming the gallery, two sconces, and the Link_/Arrive_ empties. The openings themselves are the gaps
    between the wall pieces of HALL_COLLIDERS."""
    rows = len(SIDE_DOORS)
    atlas = np.zeros((96 * rows, 1024, 3), np.float32)
    for i, d in enumerate(SIDE_DOORS):
        atlas[i * 96:(i + 1) * 96] = text_pixels(d[4], 1024, 96, (0.10, 0.07, 0.05), (0.92, 0.80, 0.52), border=4)
    textured("Plaque_Wing", mk_image("Plaque_Wing", atlas))
    for i, (normal, style, door, top, label) in enumerate(SIDE_DOORS):
        wn = "W" if normal == "+x" else "E"
        tag = f"Wing_{wn}"
        a = SIDE_Z
        if style == "doric":
            py = doric_side(normal, a, SIDE_W, top, tag)
        else:
            py = arch_side(normal, a, SIDE_W, top + SIDE_W / 2, tag)
        door_leaf(normal, a - SIDE_W / 2, a - 0.004, top, 0, f"DoorLeaf_{door}_A")
        door_leaf(normal, a + 0.004, a + SIDE_W / 2, top, 1, f"DoorLeaf_{door}_B")


        def reveal(bm):
            e, t = 0.03, 0.2                                                     # into the wall: d from -t to 0
            wall_box(bm, normal, a - SIDE_W / 2, a - SIDE_W / 2 + e, 0.0, top, -t, 0.0)
            wall_box(bm, normal, a + SIDE_W / 2 - e, a + SIDE_W / 2, 0.0, top, -t, 0.0)
            wall_box(bm, normal, a - SIDE_W / 2, a + SIDE_W / 2, top - e, top, -t, 0.0)
        part(f"Door_{tag}_Reveal", "Marble_White", reveal)
        pw = 1.3 if style == "doric" else 1.5
        ph = pw * 96 / 1024
        d0 = 0.06 if style == "doric" else 0.0                                   # the Doric frieze is 6 cm proud
        part(f"Door_{tag}_Plaque_Back", "Metal_Brass",
             lambda bm: wall_box(bm, normal, a - pw / 2 - 0.03, a + pw / 2 + 0.03, py - ph / 2 - 0.03, py + ph / 2 + 0.03, d0, d0 + 0.012))
        v0 = 1 - (i + 1) / rows
        panel_uv(f"Door_{tag}_Plaque", "Plaque_Wing", on_wall(normal, a, py, d0 + 0.0125), normal, pw, ph, v0, v0 + 1 / rows)
        sx = SIDE_GAP + 0.45
        new = [on_wall(normal, a + k * sx, 2.62, 0.30) for k in (-1, 1)]
        SCONCES.extend(new)

        def brass(bm):
            for p in new:
                aa = p[2]
                cyl(bm, on_wall(normal, aa, 2.52, 0.0), on_wall(normal, aa, 2.52, 0.02), 0.09, 0.09, 16)
                cyl(bm, on_wall(normal, aa, 2.52, 0.02), on_wall(normal, aa, 2.52, 0.28), 0.018, 0.018, 10)
                cyl(bm, (p[0], 2.50, p[2]), (p[0], 2.60, p[2]), 0.035, 0.06, 14)
        part(f"Sconce_{tag}_Brass", "Metal_Brass", brass, smooth=True)
        part(f"Sconce_{tag}_Bulbs", "Lamp_Emit", lambda bm: [sphere(bm, p, 0.05, 12) for p in new], smooth=True)
        into = NVEC[normal]
        layout_empty(f"Link_{door}", on_wall(normal, a, 0.0, 0.7))
        layout_empty(f"Arrive_{door}", on_wall(normal, a, 0.0, 1.4), face=(into[0], into[2]))


def text_pixels(text, w, h, bg, fg, border=None):
    """Own pixel font (the wing's), gold on dark, centred; the scale is the largest that fits."""
    cols = sum(len(PLAQUE_GLYPHS[ch][0]) + 1 for ch in text) - 1
    s = max(1, min((w - 24) // cols, (h - 16) // 7))
    img = np.zeros((h, w, 3), np.float32)
    img[:] = bg
    x = (w - cols * s) // 2
    y0 = (h - 7 * s) // 2
    for ch in text:
        g = PLAQUE_GLYPHS[ch]
        for r, row in enumerate(g):
            for c, v in enumerate(row):
                if v == "1":
                    img[y0 + r * s:y0 + (r + 1) * s, x + c * s:x + (c + 1) * s] = fg
        x += (len(g[0]) + 1) * s
    if border:
        b = border
        img[b:2 * b, b:-b] = img[-2 * b:-b, b:-b] = fg
        img[b:-b, b:2 * b] = img[b:-b, -2 * b:-b] = fg
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


PLAQUE_GLYPHS = {"N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"], "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
                 "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"], "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
                 "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"], "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
                 "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"], "I": ["111", "010", "010", "010", "010", "010", "111"],
                 "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"], "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
                 "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"], "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"],
                 "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"], " ": ["000"] * 7}


def panel_uv(name, mat, centre, normal, w, h, v0, v1, coll=None):
    """A flat quad like panel(), its UV the band v0..v1 of the image (one row of an atlas)."""
    r = Vector(RIGHT[normal])
    up = Vector((0, 1, 0))
    c = Vector(centre)
    pts = [c - r * w / 2 - up * h / 2, c + r * w / 2 - up * h / 2, c + r * w / 2 + up * h / 2, c - r * w / 2 + up * h / 2]
    bm = bmesh.new()
    quad(bm, *[tuple(p) for p in pts])
    bm.faces.ensure_lookup_table()
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp, uv in zip(bm.faces[0].loops, ((0, v0), (1, v0), (1, v1), (0, v1))):
        lp[uvl].uv = uv
    return finish(name, bm, mat, coll or ART, keep_uv=True)


EXIT_Y = DOOR_H + 0.22 + 0.22                              # the EXIT sign's centre: on the door's frieze


def build_exit_sign():
    """An EXIT sign on the door's frieze (own drawing: a pixel font on green), in a dark box; the sign face is emissive and carries no lightmap."""
    dx = DOOR[0]
    part("Exit_Housing", "Metal_Dark", lambda bm: wall_box(bm, "-z", dx - 0.22, dx + 0.22, EXIT_Y - 0.09, EXIT_Y + 0.09, 0.0, 0.085))
    panel("Exit_Face", "Sign_Exit", on_wall("-z", dx, EXIT_Y, 0.0855), "-z", 0.40, 0.15)


SCONCES = []         # game points of the sconces' bulbs: filled by build_sconces, used by the lights


def build_sconces():
    """The Chronicle Museum's door sconces (procroom.js, `sconce`: a brass wall plate, an arm, a cup and a bulb), one either side of the door at 2.6 m."""
    SCONCES.clear()
    dx = DOOR[0]
    for k in (-1, 1):
        SCONCES.append(on_wall("-z", dx + k * (PILASTER_X + PILASTER_W + 0.62), 2.62, 0.30))

    def brass(bm):
        for p in SCONCES:
            a = p[0]
            cyl(bm, on_wall("-z", a, 2.52, 0.0), on_wall("-z", a, 2.52, 0.02), 0.09, 0.09, 16)    # the plate
            cyl(bm, on_wall("-z", a, 2.52, 0.02), on_wall("-z", a, 2.52, 0.28), 0.018, 0.018, 10)  # the arm
            cyl(bm, (p[0], 2.50, p[2]), (p[0], 2.60, p[2]), 0.035, 0.06, 14)                      # the cup
    part("Sconce_Brass", "Metal_Brass", brass, smooth=True)
    part("Sconce_Bulbs", "Lamp_Emit", lambda bm: [sphere(bm, p, 0.05, 12) for p in SCONCES], smooth=True)


def build_plinths():
    """The six plinths, at MUSEUM.homes, as the Chronicle Museum's block pedestals (procroom.js, a `marble_dark` body under a `marble_white` lip), here with a white
    marble base too: the size of their colliders (0.9 m square, 0.6 m high). The page hangs each statue's name plate on the face toward the hall, so that face is
    plain. (Its column pedestals do not fit here: the page's plate needs a flat face, and a round shaft would leave the collider's corners bare.)"""
    def base(bm, x, z):
        cube(bm, (x - P - 0.02, 0.0, z - P - 0.02), (x + P + 0.02, 0.05, z + P + 0.02))
        cube(bm, (x - P - 0.005, 0.05, z - P - 0.005), (x + P + 0.005, 0.11, z + P + 0.005))

    def cap(bm, x, z):
        cube(bm, (x - P - 0.005, 0.50, z - P - 0.005), (x + P + 0.005, 0.535, z + P + 0.005))
        cube(bm, (x - P - 0.02, 0.535, z - P - 0.02), (x + P + 0.02, PLINTH_H, z + P + 0.02))
    for i, (x, z) in enumerate(HOMES):
        part(f"Plinth_{i}_Base", "Marble_White", lambda bm: base(bm, x, z))
        part(f"Plinth_{i}_Die", "Marble_Dark", lambda bm: cube(bm, (x - P + 0.025, 0.11, z - P + 0.025), (x + P - 0.025, 0.50, z + P - 0.025)))
        part(f"Plinth_{i}_Cap", "Marble_White", lambda bm: cap(bm, x, z))


# ---------------------------------------------------------------- frames: the Chronicle Museum's salon hang and its frame styles by era
# A frame profile is (s, u): s metres in from the frame's outer edge, u out from the wall; it starts and ends on the wall (u = 0). Every one is at most 4.5 cm
# deep, so a frame that reaches below head height stays within 5 cm of its wall (the layout check's rule).
FRAME_STYLES = {
    "gilt-ornate": ("Frame_Gold", [(0, 0), (0, 0.02), (0.012, 0.03), (0.03, 0.041), (0.05, 0.045), (0.068, 0.04), (0.08, 0.03), (0.088, 0.034), (0.096, 0.03),
                                   (0.11, 0.02), (0.125, 0.015), (0.14, 0.011), (0.14, 0)]),
    "gilt-simple": ("Frame_Gold", [(0, 0), (0, 0.02), (0.018, 0.036), (0.042, 0.04), (0.066, 0.03), (0.09, 0.016), (0.09, 0)]),
    "dark-wood": ("Frame_Wood", [(0, 0), (0, 0.03), (0.01, 0.036), (0.058, 0.036), (0.075, 0.02), (0.075, 0)]),
    "black-lacquer": ("Frame_Black", [(0, 0), (0, 0.034), (0.006, 0.04), (0.05, 0.04), (0.05, 0)]),
    "thin-metal": ("Metal_Dark", [(0, 0), (0, 0.028), (0.022, 0.028), (0.022, 0)]),
}
SMALL = {"gilt-ornate": "gilt-simple", "gilt-simple": "dark-wood", "dark-wood": "dark-wood", "black-lacquer": "thin-metal"}     # build_layout.ROOM_STYLE frame_small
BAY_ERA = ["gilt-simple", "gilt-ornate", "dark-wood", "black-lacquer"]   # the bays from the door north: Renaissance, Baroque, 19th century, modern (the Chronicle's order)
SALON = [(0.0, 1.75, 1.6, 1.2, "main"), (-1.45, 1.6, 0.7, 0.9, "small"), (1.45, 1.6, 0.7, 0.9, "small"),        # (along, centre y, w, h, role): the eye row ...
         (-1.2, 2.75 + 0.275, 0.75, 0.55, "small"), (0.0, 2.75 + 0.35, 0.95, 0.7, "main"), (1.2, 2.75 + 0.275, 0.75, 0.55, "small")]   # ... and the row above it,
#                                                                                                             bottom-aligned on 2.75 m (build_layout._vertical)


def frame_sweep(bm, normal, a, yc, w, h, profile):
    """A bevelled picture frame: `profile` swept round the w x h rectangle centred on (a, yc) of the wall, mitred at the corners (procroom.js frameGeometry's
    cushion moulding). Open at the back (it lies on the wall); built facing the room."""
    a0, a1, y0, y1 = a - w / 2, a + w / 2, yc - h / 2, yc + h / 2
    rings = []
    for s, u in profile:
        rings.append([bm.verts.new(B(on_wall(normal, p, q, u))) for p, q in ((a0 + s, y0 + s), (a1 - s, y0 + s), (a1 - s, y1 - s), (a0 + s, y1 - s))])
    new = []
    for j in range(len(profile) - 1):
        r, t = rings[j], rings[j + 1]
        for i in range(4):
            k = (i + 1) % 4
            new.append(bm.faces.new((r[i], r[k], t[k], t[i])))
    # make the outer side (the first segment) face away from the frame's centre; everything else then faces the room
    f = new[0]
    f.normal_update()
    c = B(on_wall(normal, a, yc, 0.0))
    if f.normal.dot(f.calc_center_median() - c) < 0:
        bmesh.ops.reverse_faces(bm, faces=new)


FRAMES = []          # (normal, along, centre y, w, h, style, lit): filled by build_frames, used by the lights


def build_frames():
    """The frames, empty (docs/BLENDER.md: "picture rails and empty frames"; the paintings were taken down, and their pale ghosts are on the walls). They hang as the
    Chronicle Museum hangs its works: a salon grid in each bay of the long walls (halfway between the plinths), a large work centred at eye height, smaller ones
    either side and a row above bottom-aligned on a shared line; the frame style follows the era, bay by bay from the door north, as the Chronicle's rooms do
    (gilt simple, gilt ornate, dark wood, black lacquer; the small works in the era's lighter frame). A grand gilt frame and two smaller ones on the north wall, two
    beside the door. The main frames have brass picture lights; the row above hangs on brass wires from the picture rail."""
    FRAMES.clear()
    for n in ("+x", "-x"):
        for era, zb in zip(BAY_ERA, sorted(BAYS, reverse=True)):
            if abs(zb - SIDE_Z) < 1e-6:                   # the wing's doorway has this bay
                continue
            for da, yc, w, h, role in SALON:
                st = era if role == "main" else SMALL[era]
                FRAMES.append((n, zb + da, yc, w, h, st, role == "main" and yc < 2.5))
    dx = DOOR[0]
    for k in (-1, 1):
        FRAMES.append(("-z", dx + k * 4.0, 2.15, 1.25, 0.95, "gilt-simple", True))
    FRAMES.append(("+z", 0.0, 2.7, 3.3, 2.4, "gilt-ornate", True))
    for k in (-1, 1):
        FRAMES.append(("+z", k * 3.4, 2.3, 1.0, 1.3, "gilt-simple", True))

    for i, (n, a, yc, w, h, st, lit) in enumerate(FRAMES):
        mat, prof = FRAME_STYLES[st]
        part(f"Frame_{i}", mat, lambda bm: frame_sweep(bm, n, a, yc, w, h, prof), recalc=False)

    def wires(bm):
        for n, a, yc, w, h, st, lit in FRAMES:
            if yc < 2.5:
                continue
            top = yc + h / 2
            for k in (-1, 1):
                p0 = on_wall(n, a + k * w * 0.32, RAIL - 0.06, 0.02)
                p1 = on_wall(n, a + k * w * 0.18, top, 0.02)
                cyl(bm, p0, p1, 0.002, 0.002, 4, cap=False)
                cyl(bm, on_wall(n, a + k * w * 0.32, RAIL - 0.075, 0.018), on_wall(n, a + k * w * 0.32, RAIL - 0.04, 0.018), 0.008, 0.008, 6)   # the rail hook
    part("Frame_Wires", "Metal_Brass", wires)

    lit = [f for f in FRAMES if f[6]]

    def picture_lights(bm):
        for n, a, yc, w, h, st, _ in lit:
            top = yc + h / 2 + 0.12
            lw = min(0.9, w * 0.45)
            wall_box(bm, n, a - 0.04, a + 0.04, top - 0.03, top + 0.06, 0.0, 0.02)                        # the wall plate
            cyl(bm, on_wall(n, a, top + 0.015, 0.01), on_wall(n, a, top + 0.08, 0.20), 0.009, 0.009, 8)   # the arm
            cyl(bm, on_wall(n, a - lw / 2, top + 0.08, 0.22), on_wall(n, a + lw / 2, top + 0.08, 0.22), 0.032, 0.032, 16)   # the hood
    part("Picture_Lights", "Metal_Brass", picture_lights, smooth=True)

    def bulbs(bm):
        for n, a, yc, w, h, st, _ in lit:
            top = yc + h / 2 + 0.12
            lw = min(0.9, w * 0.45)
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
        SPOTS.append((f"Spot_Plinth_{i}", (k * TRACK_X, yt - 0.22, z), (x, PLINTH_H + 0.85, z), SPOT_W, 34.0))
    for k in (-1, 1):
        SPOTS.append((f"Spot_North_{'E' if k > 0 else 'W'}", (k * TRACK_X, yt - 0.22, Z0 + 1.4), (k * 0.9, 2.7, Z0), SPOT_W * 0.8, 30.0))

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


# ---------------------------------------------------------------- the Poly Haven models: chandeliers and benches
def load_model(path):
    """Import a glTF once and keep its meshes as bmesh templates in Blender space, one per material index, with the model's own UVs as UVMap; the imported
    objects, materials and images are removed again (the build uses its own materials)."""
    before = (set(bpy.data.objects), set(bpy.data.meshes), set(bpy.data.materials), set(bpy.data.images))
    bpy.ops.import_scene.gltf(filepath=str(ROOT / path))
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
                f.material_index = 0                                             # one material per art object (else the exporter splits a primitive off)
            parts.setdefault(o.data.materials[idx].name, []).append(t)          # keyed by the model's material name
        bm.free()
    for o in obs:
        bpy.data.objects.remove(o)
    for kind, old in zip((bpy.data.meshes, bpy.data.materials, bpy.data.images), before[1:]):
        for d in [d for d in kind if d not in old]:
            kind.remove(d)
    return parts


def place(templates, mats_and_names, matrices, coll=None):
    """One art object per material: every template mesh, once per matrix (Blender space), with the model's UVs kept (as UVMap)."""
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
        out.append(finish(name, bm, mat, coll or ART, smooth=True, sharp_deg=60, keep_uv=True))
    return out


CHAIN = 0.85         # from the ceiling to the chandelier's top
CHANDELIERS = []     # game points of each chandelier's lamp ring: filled by build_chandeliers, used by the lights


def build_chandeliers():
    """Three Poly Haven chandeliers (Chandelier_02, CC0: the Chronicle Museum's hall chandelier) down the middle of the hall, one over each pair of plinths, between
    the laylights, on brass chains from ceiling roses. Its brass is one material (Chandelier_Gilt, the model's diffuse map); its bulbs are Lamp_Emit."""
    CHANDELIERS.clear()
    tpl = load_model(CHANDELIER)
    allv = [v.co for ts in tpl.values() for t in ts for v in t.verts]
    top, bot = max(v.z for v in allv), min(v.z for v in allv)
    ring = sum(v.co.z for t in tpl["Chandelier_02_bulb"] for v in t.verts) / sum(len(t.verts) for t in tpl["Chandelier_02_bulb"])   # the bulbs' mean height
    y_top = H - CHAIN
    mats = []
    for z in ROWS:
        mats.append(Matrix.Translation(B((0.0, y_top - top, z))))
        CHANDELIERS.append((0.0, y_top - top + ring, z))
    place(tpl, {"Chandelier_02": ("Chandelier_Gilt", "Chandelier_Body"), "Chandelier_02_bulb": ("Lamp_Emit", "Chandelier_Bulbs")}, mats)
    for ts in tpl.values():
        for t in ts:
            t.free()

    def chains(bm):
        for z in ROWS:
            cyl(bm, (0, H, z), (0, H - 0.05, z), 0.10, 0.08, 20)                       # the ceiling rose
            cyl(bm, (0, H - 0.05, z), (0, y_top - 0.01, z), 0.012, 0.012, 8)          # the chain (a rod)
    part("Chandelier_Chains", "Metal_Brass", chains, smooth=True)
    print(f"CHANDELIER top {top:.3f} bottom {bot:.3f}: hangs from {y_top:.2f} to {y_top - (top - bot):.2f} m")


BENCHES = [(-0.31, -4.0, "+x"), (0.31, -4.0, "-x"), (-0.31, -10.0, "+x"), (0.31, -10.0, "-x")]   # (x, z, the side its back faces): back to back under two laylights


def build_benches():
    """Four Poly Haven benches (painted_wooden_bench, CC0: the Chronicle Museum's hall bench), back to back in pairs in the middle aisle under the second and third
    laylights, facing the salon walls. The collision file has no bench, so they are decor_* (passable): the coordinator may add two bench colliders (README)."""
    tpl = load_model(BENCH)
    vs = [v.co for t in tpl["painted_wooden_bench"] for v in t.verts]
    hi = [v for v in vs if v.z > 0.6]
    back_y = sum(v.y for v in hi) / len(hi)               # the backrest's side of the model (Blender y)
    mats = []
    for x, z, back in BENCHES:
        want = 1 if back == "+x" else -1                  # the Blender x direction the back faces (game x is Blender x)
        # turn the model about z so that its length runs along the hall (Blender y) and its back's side (model y sign) points to `want` on Blender x
        ang = -math.pi / 2 if (back_y > 0) == (want > 0) else math.pi / 2
        mats.append(Matrix.Translation(B((x, 0.0, z))) @ Matrix.Rotation(ang, 4, "Z"))
    place(tpl, {"painted_wooden_bench": ("Bench_Paint", "decor_benches")}, mats)
    for ts in tpl.values():
        for t in ts:
            t.free()


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
    for i, (n, a, yc, w, h, st, lit) in enumerate(FRAMES):     # the picture lights over the lit frames: wide, soft, down onto the frame and its neighbours
        if not lit:
            continue
        top = yc + h / 2 + 0.12
        pos = on_wall(n, a, top + 0.04, 0.21)
        aim = on_wall(n, a, yc - h * 0.25, 0.0)
        d3 = (Vector(aim) - Vector(pos)).normalized()
        ob, d = light(f"Picture_Light_{i}", "SPOT", pos, PICTURE_W * (2.0 if w > 3 else 1.0), (1.0, 0.76, 0.52), 0.12)
        d.spot_size, d.spot_blend = math.radians(130), 0.8
        ob.rotation_euler = B(d3).to_track_quat("-Z", "Y").to_euler()
    for i, p in enumerate(CHANDELIERS):                          # the chandeliers: a warm point light in each lamp ring (the bulbs glow as well)
        ob, d = light(f"Chandelier_Light_{i}", "POINT", p, CHANDELIER_W, (1.0, 0.82, 0.60), 0.22)
    for i, p in enumerate(SCONCES):
        ob, d = light(f"Sconce_Light_{i}", "POINT", (p[0], p[1] + 0.02, p[2]), SCONCE_W, (1.0, 0.78, 0.54), 0.06)
    ob, d = light("Moon", "SUN", (0, 20, CZ), MOON_W, (0.62, 0.74, 1.0), 0.0)
    d.angle = math.radians(1.0)
    ob.rotation_euler = B((0.42, -1.0, 0.18)).to_track_quat("-Z", "Y").to_euler()     # from high in the west-south-west: the squares land east of the aisle
    ob, d = light("Exit_Glow", "AREA", on_wall("-z", DOOR[0], EXIT_Y, 0.10), 1.5, (0.3, 1.0, 0.45), 0.0)
    d.shape, d.size, d.size_y = "RECTANGLE", 0.40, 0.15
    ob.rotation_euler = B((0, 0, -1)).to_track_quat("-Z", "Y").to_euler()


# The light levels. Version 2 is brighter than the first (whose stills read too dark at exposure 0): chandeliers and door sconces as the Chronicle Museum
# lights its rooms, stronger picture lights and spots, and a brighter moon and night sky through the laylights.
SPOT_W = 1100.0
PICTURE_W = 140.0
CHANDELIER_W = 380.0
SCONCE_W = 45.0
MOON_W = 2.6
WORLD_STRENGTH = 40.0


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
    ART = bpy.data.collections.new("Art")
    STANDIN = bpy.data.collections.new("Standins")
    sc = bpy.context.scene
    sc.collection.children.link(ART)
    sc.collection.children.link(STANDIN)
    DOORS_C = bpy.data.collections.new("Doors")                  # the wing doorways' leaves: their own nodes in the GLB
    LAYOUT_C = bpy.data.collections.new("Layout")                # Link_/Arrive_ empties: never rendered or exported
    sc.collection.children.link(DOORS_C)
    sc.collection.children.link(LAYOUT_C)
    make_materials()
    textured("Sign_Exit", mk_image("Exit_Sign", exit_pixels()), emit=3.0)
    textured("Decal_Ghost", mk_image("Wall_Ghost", ghost_pixels()), alpha=True)
    build_shell()
    build_skylights()
    build_mouldings()
    build_door()
    build_plinths()
    build_frames()
    build_tracks()
    build_exit_sign()
    build_sconces()
    build_side_doors()
    build_chandeliers()
    build_benches()
    build_ghosts()
    build_standins()
    add_lights()
    setup_world()
    ensure_marker()
    split_at_doorways()


SPLIT_HEAD = 1.8                        # check_layout.py's HEAD: art that starts above this hangs overhead and is not tested for standing


def split_at_doorways():
    """The layout check works one box per object, so a piece that runs past a wing doorway (a wall's wainscot panels, a surround's two jambs, the reveal
    linings) has a box that spans the opening, where no collider stands. Each such Art piece is cut by faces into the part south of the doorway's centre
    (keeping the name), the part north of it (_N) and the part wholly above head height (_Head, over the opening). Only Art is cut: the Export objects
    are merged by material from Art, so the GLB holds the same triangles either way. Also run on its own (`--stage split`) on a saved .blend."""
    art = bpy.data.collections["Art"]
    z0, z1 = SIDE_Z - SIDE_W / 2 + 0.05, SIDE_Z + SIDE_W / 2 - 0.05          # the opening, less the check's 5 cm slack
    done = []
    for ob in list(art.objects):
        if ob.type != "MESH" or ob.name.endswith(("_N", "_Head")):
            continue
        g = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        gx0, gx1 = min(p.x for p in g), max(p.x for p in g)
        gy0, gy1 = min(p.z for p in g), max(p.z for p in g)
        gz0, gz1 = min(-p.y for p in g), max(-p.y for p in g)
        if gy0 >= SPLIT_HEAD or gy1 - gy0 <= 0.2 or not (gz0 < z0 and gz1 > z1) or min(abs(gx0 + HX), abs(gx1 - HX)) > 0.5:
            continue
        mw = ob.matrix_world

        def side(f):
            vs = [mw @ v.co for v in f.verts]
            if min(v.z for v in vs) >= SPLIT_HEAD - 1e-4:
                return "_Head"
            return "_N" if f.calc_center_median().y > -SIDE_Z else ""       # Blender y = -game z: north (game z < SIDE_Z) is Blender y > -SIDE_Z
        pieces = {}
        for suffix in ("", "_N", "_Head"):
            bm = bmesh.new()
            bm.from_mesh(ob.data)
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if side(f) != suffix], context="FACES")
            pieces[suffix] = bm
        if sum(1 for bm in pieces.values() if bm.faces) < 2:
            for bm in pieces.values():
                bm.free()
            continue
        for suffix, bm in pieces.items():
            if not bm.faces:
                bm.free()
                continue
            if suffix == "":
                bm.to_mesh(ob.data)
                bm.free()
                continue
            me = bpy.data.meshes.new(ob.name + suffix)
            bm.to_mesh(me)
            bm.free()
            me.materials.append(ob.data.materials[0])
            nob = bpy.data.objects.new(ob.name + suffix, me)
            nob.matrix_world = mw.copy()
            art.objects.link(nob)
        done.append(ob.name)
    print("SPLIT at the doorways:", done)
    return done


# ---------------------------------------------------------------- bake
GROUPS = [["Floor_Parquet", "Floor_Marble", "Ceiling_Paint"],                                  # 0: the floor and the ceiling
          ["Wall_Paint", "Wainscot_Wood", "Trim_Paint", "Skirting_Marble", "Decal_Ghost"],       # 1: the walls, wainscot, skirting, rails, cornice, coffers
          ["Marble_Dark", "Marble_White", "Frame_Gold", "Frame_Wood", "Frame_Black", "Door_Wood", "Bench_Paint", "Plaque_Wing"],   # 2: plinths, frames,
                                                #    the doors (and the wing doorways' leaves), benches, the wing plaques
          ["Metal_Dark", "Metal_Brass", "Chandelier_Gilt"]]   # 3: tracks, spot heads, picture lights, sconces, chandeliers: they sit next to the lights, so their
                                                #    texels run far hotter than the rest and get their own map (and lightmap_intensity) instead of crushing the others
PAGES = [896, 1536, 1152, 1152]        # each map's fixed page size (px), from a first run with None: the smallest page that gave >= 30 px/m (map 2 went
                                        # from 1024 to 1152 with the wing doorways, at 27 px/m on 1024). Fixed, because
                                        # Blender's island packer is not exactly repeatable
WHITE_CAP = 12.0                        # a map's white point is its 99.5th percentile texel, but at most 12 x its 90th: on the fittings' map the few texels beside
                                        # the bulbs run some 40 x hotter than the rest and would push the rest into the bottom 8-bit levels; they clip instead
KEEP_UV_LM = {"Chandelier_Gilt": 0.16}  # lightmapped through the model's own UVs, in a corner of its map this wide (its 64k triangles would make thousands of
                                        # smart-project islands); the three chandeliers share those texels, as they hang in the same light
SHELL_PREFIX = ("Wall_", "Floor_", "Ceiling_")
FLAT_UV = ("Plaque_",)                  # flat quads lightmapped through their own 0..1 UVs (smart project folds a lone quad into a sliver, which the
                                        # island scaling then blows up until the packer shrinks the rest of the map to nothing)


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
    keep = [o for o in objs if o.name in KEEP_UV_LM]
    corner = max([KEEP_UV_LM[o.name] for o in keep], default=0.0)
    objs = [o for o in objs if o not in keep]
    flat = [o for o in objs if o.name.startswith(FLAT_UV)]
    for o in objs + keep:
        uvs = o.data.uv_layers
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.new(name="lightmap", do_init=o in keep or o in flat)  # the kept ones (and the plaques) start as a copy of UVMap
        uvs.active = uvs["lightmap"]
        uvs["lightmap"].active_render = True
    for o in keep:                                                 # the model's UVs, fitted into the corner square [1 - corner, 1] x [0, corner]
        d = o.data.uv_layers["lightmap"].data
        us = np.array([x.uv for x in d])
        lo, hi = us.min(axis=0), us.max(axis=0)
        sc = (corner - 2 * MARGIN_PX / (page or 2048)) / max(hi - lo)
        us = (us - lo) * sc + np.array([1 - corner + MARGIN_PX / (page or 2048), MARGIN_PX / (page or 2048)])
        d.foreach_set("uv", us.ravel())
    select_only([o for o in objs if o not in flat])
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.average_islands_scale()
    chosen = None
    for S in ((page,) if page else (512, 640, 768, 896, 1024, 1152, 1280, 1408, 1536, 1792, 2048)):
        bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / S, shape_method="CONCAVE")
        bpy.ops.object.mode_set(mode="OBJECT")
        if corner:                                                 # the packed islands shrink into the square beside the kept corner
            f = 1 - corner
            for o in objs:
                d = o.data.uv_layers["lightmap"].data
                us = np.array([x.uv for x in d]) * f
                d.foreach_set("uv", us.ravel())
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
        if "Door_Wood" in mats:                                   # the wing doorways' leaves (own objects) share the door wood's map
            objs += sorted(bpy.data.collections["Doors"].objects, key=lambda o: o.name)
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
        scale = float(min(pc[3], WHITE_CAP * pc[1]))         # the 99.5th percentile of the lit texels maps to white (at most WHITE_CAP x the 90th); hotter ones clip
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
                    if kind == "objects" and st is idb and idb.name.startswith(("DoorLeaf_", "Link_", "Arrive_")):   # the doorways' layout (read by stage_export)
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
    for im in bpy.data.images:                                    # the glTF importer packs the models' textures under their absolute paths:
        if im.packed_file and not im.filepath.replace("\\", "/").startswith("//generated/"):
            im.unpack(method="REMOVE")                            # unpack them (the files are in blender/models/), so the path goes relative below
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
def write_world(leaves):
    """world/galleries.json: the layout's collision file (as tools/make_street.mjs writes it from shared/museum.js) with the two doorways: the wall
    pieces of HALL_COLLIDERS in place of Wall_W and Wall_E, and the four leaves in `doors` (export_scene.py's door entry). Nothing else changes."""
    sys.path.insert(0, str(ROOT / "tools/blender"))
    import export_scene
    names = {o.name for o in leaves}
    doc = dict(L["world"])
    doc["colliders"] = HALL_COLLIDERS
    doc["doors"] = [d for d in export_scene.collect(SCENE)["doors"] if d["name"] in names]
    path = ROOT / f"world/{SCENE}.json"
    path.write_text(json.dumps(doc, separators=(",", ":")))
    print(f"WORLD {path.name}: {len(doc['colliders'])} colliders, {len(doc['doors'])} doors")


def stage_export():
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    bpy.data.collections["Art"].hide_viewport = True
    leaves = sorted(bpy.data.collections["Doors"].objects, key=lambda o: o.name)
    write_world(leaves)
    stash = {o.name: {k: o[k] for k in o.keys()} for o in leaves}    # the leaves' layout properties are in the JSON, not in the GLB's extras
    for o in leaves:
        for k in list(o.keys()):
            del o[k]
    bpy.ops.object.select_all(action="DESELECT")
    for o in list(exp.objects) + leaves:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = stage_work() / f"{SCENE}_raw.glb"
    scrub_private()                                   # export_extras=True: only the materials' lightmap extras may go out
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False, export_animations=False)
    for o in leaves:
        for k, v in stash[o.name].items():
            o[k] = v
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
    cut_plan = [o for o in arts if o.name.startswith(("Ceiling_", "Skylight_", "Track_", "Spot_", "Cornice", "Laylight_", "Chandelier_"))]
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
    if STAGE == "split":                              # a saved .blend built before split_at_doorways: cut its Art pieces (Export, the bake and the GLB are untouched)
        split_at_doorways()
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
