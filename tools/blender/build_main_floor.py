"""Builds the Farway grocery (`main_floor`) in Blender, lights and bakes it by day, and exports world/main_floor.glb (docs/BLENDER.md, "5. main_floor").

Re-runnable, from the repo root:

    blender -b --python tools/blender/build_main_floor.py -- --stage textures --src <folder>  (the three CC0 maps -> blender/textures/main_floor/)
    blender -b --python tools/blender/build_main_floor.py                       (art, bake, export, axes, render: every stage in one run)
    blender -b --python tools/blender/build_main_floor.py -- --stage art        (build the art, save blender/scenes/main_floor.blend)
    blender -b blender/scenes/main_floor.blend --python tools/blender/build_main_floor.py -- --stage bake [--samples 512] [--device cpu]
    blender -b blender/scenes/main_floor.blend --python tools/blender/build_main_floor.py -- --stage export
    blender -b blender/scenes/main_floor.blend --python tools/blender/build_main_floor.py -- --stage axes     (the marker-cube axes check)
    blender -b blender/scenes/main_floor.blend --python tools/blender/build_main_floor.py -- --stage render [--render-samples 128] [--only 1_arrival]

Stages: art (geometry, materials, lights, stand-ins) -> bake (merge by material, lightmap UV, Cycles bake, OIDN denoise, 8-bit PNGs in the work
folder) -> export (GLB; tools/blender/pack_scene.py then makes the WebP lightmaps and the WebP textures) -> render (the review stills).

The structure is the apartment pilot's (tools/blender/build_apartment.py), with the galleries build's privacy scrub and fixed lightmap pages.
No coordinate of the layout is typed in here: the hall, the colliders, the four shelf units (GROCERY.shelves), the checkout, the cart corral,
the door, the arrival point and the security camera come from blender/layout/main_floor.json (node tools/blender/dump_layout.mjs main_floor).
A game point (x, y, z) is Blender (x, -z, y). The art the layout does not name (the storefront windows, the coolers on the north wall, the strip
lights over the aisles, the staff door) is placed relative to those numbers.

What the page draws itself is left out (docs/BLENDER.md, contract 4): the food on the shelves, the three carts in the corral, the camera's head and
its red light, and the price sign over each shelf. The food and the carts are here as hidden stand-ins (the `Standins` collection) so the bake has
their contact shadows; the camera head and the signs are stand-ins for the review stills only. None of them is exported.
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
SCENE = "main_floor"
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
SAMPLES = arg("--samples", 512, int)
DEVICE = arg("--device", "auto")
ENGINE = arg("--engine", "CYCLES")

L = json.loads(LAYOUT.read_text())
K = L["constants"]
COLLIDERS = {c["s"]: c for c in L["world"]["colliders"]}
HX, HZ = K["half"]
H = K["h"]
SHELVES = K["shelves"]
CO = K["checkout"]
CART = K["cart"]
DOOR = K["door"]["at"]
CAM = L["camera"]["at"]
WALL_T = COLLIDERS["Wall_S"]["max"][2] - COLLIDERS["Wall_S"]["min"][2]       # the walls' thickness (0.2)

# the art the layout does not name, placed relative to it
BAND = 1.2                       # the painted lower band of the walls and its rail
DOOR_HALF, DOOR_H = 1.2, 2.5     # the entrance: a pair of glass sliding doors, centred on door.at's x, in the south wall
PIER = 0.6                       # solid wall between the door and each storefront window
WIN_Y = (0.75, 2.75)             # the storefront windows' sill and head
WIN_END = 0.8                    # solid wall at each end of the storefront
STRIP_Y = 3.55                   # the underside of the strip lights
STRIP_Z = HZ - 0.8               # the strips run z -STRIP_Z .. STRIP_Z
COOLER = {"doors": 8, "w": 0.95, "gap": 2.0, "y": (0.18, 2.22)}        # two banks of glass-door coolers on the north wall, either side of the camera
STAFF = {"z": (-6.3, -4.7), "h": 2.2}                                    # the staff door (closed, never opens) on the east wall
BACKDROP_Z, BACKDROP_W, BACKDROP_H = HZ + 15.0, 90.0, 32.0             # the street across the road, seen through the storefront


def aisles():
    """The middle of each aisle (between the walls and the shelf units), for the strip lights."""
    edges = [-HX] + [v for s in sorted(SHELVES, key=lambda s: s["min"][0]) for v in (s["min"][0], s["max"][0])] + [HX]
    return [(edges[i] + edges[i + 1]) / 2 for i in range(0, len(edges), 2)]


STRIPS = aisles()


def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


def G(v):
    """Blender (x, y, z) -> game (x, y, z)"""
    return (v[0], v[2], -v[1])


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


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, diff=None, img=None, tint=None, emit=None, alpha=None, tile=None):
    """A Principled material. `tint` multiplies the diffuse texture by a constant colour (a Mix node set to Multiply), which the glTF exporter
    writes as baseColorFactor, so the page shows texture x factor x lightmap. `img` is a generated (packed) image in place of a file."""
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
        n.image = image(diff, True) if diff else img
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        if tint:
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs[0].default_value = 1.0
            nt.links.new(n.outputs["Color"], mix.inputs[6])
            mix.inputs[7].default_value = (*tint, 1)
            nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        elif emit is None:
            nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
        if emit is not None and not isinstance(emit, tuple):         # an emissive picture: the texture is the emission, strength `emit`
            bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
            nt.links.new(n.outputs["Color"], bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = emit
    if isinstance(emit, tuple):
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


def srgb_hex(h):
    """A three.js colour (sRGB hex) as linear RGB, for the stand-ins that copy the page's blockout colours."""
    c = [((h >> s) & 255) / 255 for s in (16, 8, 0)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


FOOD_COLOR = {"apple": 0xd84a3a, "bread": 0xd8b070, "soup": 0xc8c8c8, "meal": 0x4a8ad8}     # index.html FOOD_COLOR (the page's own food boxes)


def make_materials(gen):
    material("Floor_Tile", diff="floor_tiles_diff.jpg", rough=0.35, tile=1.2)                     # 0.3 m checker tiles, cream and grey-green
    material("Ceiling_Tile", diff="ceiling_tile_diff.jpg", rough=0.95, tile=1.2)                  # 0.6 x 1.2 m lay-in tiles on a white grid
    material("Wall_Paint", diff="wall_paint_diff.jpg", tint=(0.86, 0.84, 0.76), rough=0.9, tile=2.6)
    material("Wall_Lower", diff="wall_paint_diff.jpg", tint=(0.42, 0.53, 0.45), rough=0.7, tile=2.6)    # the sage band below the rail
    material("Trim_Steel", color=(0.62, 0.62, 0.60), rough=0.35, metal=0.7)
    material("Shelf_Paint", color=(0.80, 0.80, 0.78), rough=0.45, metal=0.2)
    material("Shelf_Back", img=gen["pegboard"], rough=0.6, tile=0.4)
    material("Shelf_Kick", color=(0.10, 0.10, 0.11), rough=0.6)
    material("EndCap_Red", color=(0.50, 0.05, 0.05), rough=0.5)
    material("Price_Rail", color=(0.82, 0.76, 0.48), rough=0.5)
    material("Counter_Laminate", color=(0.40, 0.37, 0.33), rough=0.55)
    material("Counter_Top", color=(0.66, 0.66, 0.64), rough=0.3, metal=0.8)
    material("Belt_Rubber", color=(0.025, 0.025, 0.028), rough=0.8)
    material("Plastic_Black", color=(0.03, 0.03, 0.035), rough=0.35)
    material("Rail_Steel", color=(0.70, 0.70, 0.70), rough=0.25, metal=0.9)
    material("Frame_Alu", color=(0.14, 0.13, 0.12), rough=0.4, metal=0.6)
    material("Cooler_Frame", color=(0.05, 0.05, 0.055), rough=0.4, metal=0.3)
    material("Staff_Door", color=(0.30, 0.38, 0.44), rough=0.5)
    material("Mat_Rubber", color=(0.08, 0.09, 0.10), rough=0.95)
    material("Light_Housing", color=(0.82, 0.82, 0.80), rough=0.5, metal=0.2)
    material("Metal_Dark", color=(0.05, 0.05, 0.055), rough=0.45, metal=0.8)
    material("Sign_Dept", img=gen["dept"], rough=0.6)
    material("Lamp_Emit", color=(1.0, 1.0, 1.0), rough=0.4, emit=((0.96, 0.98, 1.0), 9.0))       # the strip lights' diffusers
    material("Window_Glass", color=(0.80, 0.90, 0.95), rough=0.05, alpha=0.12)
    material("Cooler_Lit", img=gen["cooler"], emit=1.2, tile=1.0)
    material("Sign_Glow", img=gen["glow"], emit=2.0)
    material("Screen_Glow", color=(0.0, 0.0, 0.0), emit=((0.25, 0.55, 0.45), 1.5))
    material("Backdrop_Street", img=gen["street"], emit=1.25)
    for food, h in FOOD_COLOR.items():                                                              # stand-ins only (never exported)
        material(f"Standin_{food}", color=srgb_hex(h), rough=0.7)
    material("Standin_Cart", color=srgb_hex(0xc83a32), rough=0.5)
    material("Standin_Grey", color=srgb_hex(0x8a8a8a), rough=0.5)
    material("Standin_Camera", color=srgb_hex(0xd8d8d8), rough=0.5)
    material("Standin_LED", color=(0, 0, 0), emit=((1.0, 0.02, 0.02), 4.0))
    material("Standin_Sign", img=gen["signs"], emit=1.0)


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


def quad(bm, p0, p1, p2, p3):
    vs = [bm.verts.new(B(p)) for p in (p0, p1, p2, p3)]
    return bm.faces.new(vs)


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
WALLS = {"+x": ("z", -HX), "-x": ("z", HX), "+z": ("x", -HZ), "-z": ("x", HZ)}
RIGHT = {"+x": (0, 0, -1), "-x": (0, 0, 1), "+z": (1, 0, 0), "-z": (-1, 0, 0)}   # looking at a surface whose normal is +x, ...: the game direction of your right hand


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


def panel(name, mat, centre, normal, w, h, uv=(0, 0, 1, 1), coll=None):
    """A flat quad facing `normal` (a game axis such as "+x"), w wide, h tall; its UV is the rectangle `uv` (u0, v0, u1, v1) with the picture upright."""
    r = Vector(RIGHT[normal])
    up = Vector((0, 1, 0))
    c = Vector(centre)
    pts = [c - r * w / 2 - up * h / 2, c + r * w / 2 - up * h / 2, c + r * w / 2 + up * h / 2, c - r * w / 2 + up * h / 2]
    bm = bmesh.new()
    f = quad(bm, *[tuple(p) for p in pts])
    uvl = bm.loops.layers.uv.new("UVMap")
    u0, v0, u1, v1 = uv
    for lp, t in zip(f.loops, ((u0, v0), (u1, v0), (u1, v1), (u0, v1))):
        lp[uvl].uv = t
    return finish(name, bm, mat, coll or ART, keep_uv=True)


# ---------------------------------------------------------------- the shell
def openings_s():
    """The south wall's holes, as (x0, x1, y0, y1): the entrance and the two storefront windows."""
    dx = DOOR[0]
    return [(dx - DOOR_HALF, dx + DOOR_HALF, 0.0, DOOR_H),
            (-HX + WIN_END, dx - DOOR_HALF - PIER, WIN_Y[0], WIN_Y[1]),
            (dx + DOOR_HALF + PIER, HX - WIN_END, WIN_Y[0], WIN_Y[1])]


def wall_cells(c, holes, y0, y1):
    """The solid cells of a wall collider c between heights y0 and y1, minus `holes` (x0, x1, y0, y1): a grid of boxes through the wall's thickness."""
    mn, mx = c["min"], c["max"]
    xs = sorted({mn[0], mx[0], *[v for h in holes for v in (h[0], h[1]) if mn[0] < v < mx[0]]})
    ys = sorted({y0, y1, *[v for h in holes for v in (h[2], h[3]) if y0 < v < y1]})
    out = []
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
            if any(h[0] < cx < h[1] and h[2] < cy < h[3] for h in holes):
                continue
            out.append(((xs[i], ys[j], mn[2]), (xs[i + 1], ys[j + 1], mx[2])))
    return out


def build_shell():
    """Floor, walls and ceiling from the collision file's boxes (Floor_*, Ceiling_*, Wall_*), so art and colliders agree. Each wall is a sage band
    below the rail and cream paint above it; the south wall has the entrance and the two storefront windows cut out of it."""
    for s, c in COLLIDERS.items():
        mn, mx = c["min"], c["max"]
        if s.startswith("Floor"):
            part(s, "Floor_Tile", lambda bm: cube(bm, mn, mx))
        elif s.startswith("Ceiling"):
            part(s, "Ceiling_Tile", lambda bm: cube(bm, mn, mx))
        elif s == "Wall_S":
            holes = openings_s()
            part(s, "Wall_Paint", lambda bm: [cube(bm, a, b) for a, b in wall_cells(c, holes, BAND, mx[1])])
            part(s + "_Lower", "Wall_Lower", lambda bm: [cube(bm, a, b) for a, b in wall_cells(c, holes, mn[1], BAND)])
        elif s.startswith("Wall_"):
            part(s, "Wall_Paint", lambda bm: cube(bm, (mn[0], BAND, mn[2]), (mx[0], mx[1], mx[2])))
            part(s + "_Lower", "Wall_Lower", lambda bm: cube(bm, (mn[0], mn[1], mn[2]), (mx[0], BAND, mx[2])))


def wall_runs(normal, y, extra=()):
    """Where a trim at height y runs along a wall: its length, less the openings of the south wall at that height, the staff door and `extra` spans."""
    ax, _ = WALLS[normal]
    half = HX if ax == "x" else HZ
    cut = list(extra)
    if normal == "-z":
        cut += [(h[0], h[1]) for h in openings_s() if h[2] < y < h[3]]
    if normal == "-x" and y < STAFF["h"]:
        cut += [STAFF["z"]]
    runs, a = [], -half
    for c0, c1 in sorted(cut):
        runs.append((a, c0))
        a = c1
    runs.append((a, half))
    return [(a0, a1) for a0, a1 in runs if a1 - a0 > 0.01]


def cooler_spans():
    w = COOLER["doors"] * COOLER["w"]
    g = COOLER["gap"]
    return [(-g - w, -g), (g, g + w)]


def build_trim():
    """A steel rail on the band's top edge and a steel kick plate along every wall (not across the doorways); the rail stops at the coolers and
    at the storefront windows, which come down below it."""
    def rail(bm):
        for n in ("+x", "-x", "+z", "-z"):
            for a0, a1 in wall_runs(n, BAND, cooler_spans() if n == "+z" else ()):
                wall_box(bm, n, a0, a1, BAND - 0.03, BAND + 0.03, 0.0, 0.02)
    part("Trim_Rail", "Trim_Steel", rail)

    def kick(bm):
        for n in ("+x", "-x", "+z", "-z"):
            for a0, a1 in wall_runs(n, 0.075):
                wall_box(bm, n, a0, a1, 0.0, 0.15, 0.0, 0.012)
    part("Trim_Kick", "Trim_Steel", kick)


def build_storefront():
    """The south wall's glass: aluminium storefront frames with six panes each side, a sill ledge, the closed sliding doors, a door sensor, the EXIT sign,
    and the mat inside the door. The street beyond is a backdrop (decor_backdrop*)."""
    z0, z1 = HZ, HZ + WALL_T
    zm = (z0 + z1) / 2
    door, wl, wr = openings_s()
    f = 0.05

    def frames(bm):
        for x0, x1, y0, y1 in (wl, wr):
            cube(bm, (x0, y0, zm - 0.05), (x1, y0 + f, zm + 0.05))                 # sill member
            cube(bm, (x0, y1 - f, zm - 0.05), (x1, y1, zm + 0.05))                 # head
            n = 6
            for i in range(n + 1):
                x = x0 + (x1 - x0) * i / n
                cube(bm, (max(x0, x - f / 2), y0, zm - 0.05), (min(x1, x + f / 2), y1, zm + 0.05))
        x0, x1, y0, y1 = door
        cube(bm, (x0, 0, z0 + 0.02), (x0 + 0.06, y1, z1 - 0.02))                   # door jambs and head
        cube(bm, (x1 - 0.06, 0, z0 + 0.02), (x1, y1, z1 - 0.02))
        cube(bm, (x0, y1 - 0.06, z0 + 0.02), (x1, y1, z1 - 0.02))
        cube(bm, (x0, 0, z0 + 0.03), (x1, 0.008, z1 - 0.03))                       # threshold
        xm = (x0 + x1) / 2
        for (a, b), dz in (((x0 + 0.06, xm + 0.03), -0.025), ((xm - 0.03, x1 - 0.06), 0.025)):     # two leaves, one behind the other
            zz = zm + dz
            cube(bm, (a, 0.008, zz - 0.02), (a + 0.06, y1 - 0.06, zz + 0.02))
            cube(bm, (b - 0.06, 0.008, zz - 0.02), (b, y1 - 0.06, zz + 0.02))
            cube(bm, (a, y1 - 0.14, zz - 0.02), (b, y1 - 0.06, zz + 0.02))
            cube(bm, (a, 0.008, zz - 0.02), (b, 0.16, zz + 0.02))
    part("Storefront_Frames", "Frame_Alu", frames)
    part("Door_Sensor", "Frame_Alu", lambda bm: cube(bm, (DOOR[0] - 0.3, door[3] + 0.04, z0 - 0.06), (DOOR[0] + 0.3, door[3] + 0.12, z0)))   # over the opening, inside, 2.54 m up
    part("Window_Sill", "Frame_Alu", lambda bm: [cube(bm, (x0, y0 - 0.03, z0 - 0.08), (x1, y0, z0 + 0.03)) for x0, x1, y0, y1 in (wl, wr)])

    def glass(bm):
        for x0, x1, y0, y1 in (wl, wr):
            quad(bm, (x0, y0 + f, zm), (x1, y0 + f, zm), (x1, y1 - f, zm), (x0, y1 - f, zm))
        x0, x1, y0, y1 = door
        xm = (x0 + x1) / 2
        for (a, b), dz in (((x0 + 0.06, xm + 0.03), -0.025), ((xm - 0.03, x1 - 0.06), 0.025)):
            quad(bm, (a + 0.06, 0.16, zm + dz), (b - 0.06, 0.16, zm + dz), (b - 0.06, y1 - 0.14, zm + dz), (a + 0.06, y1 - 0.14, zm + dz))
    part("Storefront_Glass", "Window_Glass", glass, tile=1.0)

    # the EXIT sign over the door: a dark box on the wall, its face lit (Sign_Glow, the atlas's top half)
    xm = DOOR[0]
    y = DOOR_H + 0.42
    part("Exit_Housing", "Plastic_Black", lambda bm: wall_box(bm, "-z", xm - 0.24, xm + 0.24, y - 0.1, y + 0.1, 0.0, 0.07))
    panel("Exit_Face", "Sign_Glow", on_wall("-z", xm, y, 0.0705), "-z", 0.44, 0.16, uv=(0, 0.5, 1, 1))
    part("decor_mat", "Mat_Rubber", lambda bm: cube(bm, (xm - 1.6, 0.0, HZ - 1.5), (xm + 1.6, 0.012, HZ)))


def build_shelves():
    """The four gondolas, each exactly its collider: a dark base, three shelves a side at the page's food heights (tops at 0.35, 0.95 and 1.55 m, as the
    blockout's boards, so the page's food sits on them), a pegboard spine with uprights, a price rail on each shelf's front edge, red end panels."""
    TOPS = (0.35, 0.95, 1.55)
    for sh in SHELVES:
        x0, _, z0 = sh["min"]
        x1, y1, z1 = sh["max"]
        xc = (x0 + x1) / 2
        sp = 0.07                                   # half the spine's thickness
        e = 0.025                                   # the end panels' thickness
        nm = sh["food"]

        part(f"Shelf_{nm}_Base", "Shelf_Kick", lambda bm: cube(bm, (x0 + 0.02, 0, z0 + e), (x1 - 0.02, TOPS[0] - 0.04, z1 - e)))

        def boards(bm):
            for t in TOPS:
                cube(bm, (x0, t - 0.04, z0 + e), (xc - sp, t, z1 - e))
                cube(bm, (xc + sp, t - 0.04, z0 + e), (x1, t, z1 - e))
            cube(bm, (xc - sp - 0.03, y1 - 0.04, z0 + e), (xc + sp + 0.03, y1, z1 - e))          # the spine's cap
            n = int(round(z1 - z0))                                                              # an upright every metre
            for i in range(n + 1):
                z = z0 + e + (z1 - z0 - 2 * e) * i / n
                cube(bm, (xc - sp - 0.006, TOPS[0] - 0.04, max(z0 + e, z - 0.02)), (xc + sp + 0.006, y1 - 0.04, min(z1 - e, z + 0.02)))
        part(f"Shelf_{nm}_Boards", "Shelf_Paint", boards)
        part(f"Shelf_{nm}_Spine", "Shelf_Back", lambda bm: cube(bm, (xc - sp, TOPS[0] - 0.04, z0 + e), (xc + sp, y1 - 0.04, z1 - e)))

        def rails(bm):
            for t in TOPS:
                cube(bm, (x0, t - 0.065, z0 + e), (x0 + 0.015, t + 0.012, z1 - e))
                cube(bm, (x1 - 0.015, t - 0.065, z0 + e), (x1, t + 0.012, z1 - e))
        part(f"Shelf_{nm}_Rails", "Price_Rail", rails)

        def ends(bm):
            cube(bm, (x0, 0, z0), (x1, y1, z0 + e))
            cube(bm, (x0, 0, z1 - e), (x1, y1, z1))
        part(f"Shelf_{nm}_Ends", "EndCap_Red", ends)


def build_checkout():
    """The checkout counter in its collider: a laminate body on a dark kick, a steel top, the belt with its guide rails, the scanner, the register
    (cash drawer, the cashier's screen facing south, a small customer display and a card reader facing the shopper), and the lane light."""
    x0, _, z0 = CO["min"]
    x1, top, z1 = CO["max"]
    part("Checkout_Body", "Counter_Laminate", lambda bm: cube(bm, (x0, 0.08, z0), (x1, top - 0.05, z1)))
    part("Checkout_Kick", "Shelf_Kick", lambda bm: cube(bm, (x0 + 0.04, 0, z0 + 0.06), (x1 - 0.04, 0.08, z1 - 0.06)))
    part("Checkout_Band", "EndCap_Red", lambda bm: cube(bm, (x0, 0.62, z0 - 0.006), (x1, 0.76, z0 + 0.01)))          # a red band on the shopper's side
    part("Checkout_Top", "Counter_Top", lambda bm: cube(bm, (x0, top - 0.05, z0), (x1, top, z1)))
    bx0, bx1 = x0 + 0.12, x0 + (x1 - x0) * 0.62
    bz0, bz1 = z0 + 0.08, z1 - 0.28
    part("Checkout_Belt", "Belt_Rubber", lambda bm: cube(bm, (bx0, top, bz0), (bx1, top + 0.008, bz1)))

    def guides(bm):
        cube(bm, (bx0, top, bz0 - 0.03), (bx1, top + 0.045, bz0 - 0.012))
        cube(bm, (bx0, top, bz1 + 0.012), (bx1, top + 0.045, bz1 + 0.03))
        cyl(bm, (bx0 + 0.5, top + 0.03, bz0 + 0.02), (bx0 + 0.5, top + 0.03, bz1 - 0.02), 0.018, seg=8)        # a divider bar left on the belt
    part("Checkout_Guides", "Rail_Steel", guides)
    sx0, sx1 = bx1 + 0.12, bx1 + 0.5
    part("Checkout_Scanner", "Belt_Rubber", lambda bm: cube(bm, (sx0, top, z0 + 0.12), (sx1, top + 0.004, z0 + 0.48)))

    def register(bm):
        cube(bm, (sx0, top, z0 + 0.5), (sx1, top + 0.22, z0 + 0.56))                                       # the scanner's tower
        rx0, rx1 = x1 - 0.9, x1 - 0.25
        cube(bm, (rx0, top, z0 + 0.15), (rx1, top + 0.12, z0 + 0.65))                                      # cash drawer
        cube(bm, (rx0 + 0.1, top + 0.28, z1 - 0.32), (rx0 + 0.5, top + 0.53, z1 - 0.25))                  # the cashier's screen
        cube(bm, (rx0 + 0.05, top + 0.12, z0 + 0.04), (rx0 + 0.3, top + 0.26, z0 + 0.09))                  # customer display
        cube(bm, (sx0 - 0.2, top, z0 + 0.03), (sx0 - 0.08, top + 0.14, z0 + 0.1))                          # card reader
    part("Checkout_Register", "Plastic_Black", register)
    rx0 = x1 - 0.9

    def poles(bm):
        cyl(bm, (rx0 + 0.3, top + 0.12, z1 - 0.285), (rx0 + 0.3, top + 0.30, z1 - 0.285), 0.018, seg=8)
        cyl(bm, (x1 - 0.15, top, z1 - 0.1), (x1 - 0.15, 2.3, z1 - 0.1), 0.025, seg=12)                    # the lane light's pole
    part("Checkout_Poles", "Metal_Dark", poles)
    lx, ly, lz = x1 - 0.15, 2.45, z1 - 0.1
    part("Lane_Light_Box", "Plastic_Black", lambda bm: cube(bm, (lx - 0.16, ly - 0.15, lz - 0.05), (lx + 0.16, ly + 0.15, lz + 0.05)))
    panel("Lane_Light_N", "Sign_Glow", (lx, ly, lz - 0.0505), "-z", 0.28, 0.26, uv=(0.0, 0.0, 0.5, 0.5))      # faces the shopper (north)
    panel("Lane_Light_S", "Sign_Glow", (lx, ly, lz + 0.0505), "+z", 0.28, 0.26, uv=(0.0, 0.0, 0.5, 0.5))
    panel("Checkout_Screen", "Screen_Glow", (rx0 + 0.3, top + 0.405, z1 - 0.2495), "+z", 0.36, 0.21)          # the cashier's side (south)
    panel("Checkout_Display", "Screen_Glow", (rx0 + 0.175, top + 0.19, z0 + 0.0395), "-z", 0.21, 0.1)        # the shopper's side


def build_corral():
    """The cart corral: a steel tube rail round three sides of its collider, open to the east where the page's carts have their handles."""
    x0, _, z0 = CART["min"]
    x1, y1, z1 = CART["max"]
    r = 0.022

    xw = x0 - r                                     # the west rail stands just outside the collider: the page's first cart starts on its west edge
    POSTS = ((xw, z0 + r), (xw, z1 - r), (x1 - r, z0 + r), (x1 - r, z1 - r))

    def rails(bm):
        for x, z in POSTS:
            cyl(bm, (x, 0, z), (x, y1 - r, z), r, seg=10)
        for y in (0.5, y1 - r):
            cyl(bm, (xw, y, z0 + r), (xw, y, z1 - r), r, seg=10)
            cyl(bm, (xw, y, z0 + r), (x1 - r, y, z0 + r), r, seg=10)
            cyl(bm, (xw, y, z1 - r), (x1 - r, y, z1 - r), r, seg=10)
    part("Corral_Rails", "Rail_Steel", rails, smooth=True)
    part("Corral_Feet", "Rail_Steel", lambda bm: [cyl(bm, (x, 0, z), (x, 0.012, z), 0.05, seg=12) for x, z in POSTS], smooth=True)    # the floor flanges: 12 mm, their own piece


def build_coolers():
    """Two banks of glass-door coolers flat on the north wall (they stand out of it by at most 5 cm, so they need no collider): a black frame, the lit
    interior behind the glass (a picture, Cooler_Lit, 0.5 cm off the wall), a handle on each door, and a header."""
    y0, y1 = COOLER["y"]
    w = COOLER["w"]
    for i, (a0, a1) in enumerate(cooler_spans()):
        def frame(bm):
            wall_box(bm, "+z", a0, a1, y0, y0 + 0.1, 0.0, 0.035)
            wall_box(bm, "+z", a0, a1, y1 - 0.1, y1 + 0.18, 0.0, 0.035)
            for k in range(COOLER["doors"] + 1):
                a = a0 + k * w
                wall_box(bm, "+z", max(a0, a - 0.025), min(a1, a + 0.025), y0 + 0.1, y1 - 0.1, 0.0, 0.035)
        part(f"Cooler_{i}_Frame", "Cooler_Frame", frame)

        def handles(bm):
            for k in range(COOLER["doors"]):
                a = a0 + (k + 1) * w - 0.08
                wall_box(bm, "+z", a - 0.012, a + 0.012, 0.95, 1.55, 0.038, 0.048)
                for yy in (0.97, 1.53):
                    wall_box(bm, "+z", a - 0.008, a + 0.008, yy - 0.01, yy + 0.01, 0.02, 0.038)
        part(f"Cooler_{i}_Handles", "Rail_Steel", handles)
        panel(f"Cooler_{i}_Inside", "Cooler_Lit", on_wall("+z", (a0 + a1) / 2, (y0 + y1) / 2, 0.005), "+z", a1 - a0, y1 - y0 - 0.2, uv=(0, 0, COOLER["doors"], 1))
        part(f"Cooler_{i}_Glass", "Window_Glass", lambda bm: quad(bm, on_wall("+z", a0, y0 + 0.1, 0.025), on_wall("+z", a1, y0 + 0.1, 0.025),
                                                                     on_wall("+z", a1, y1 - 0.1, 0.025), on_wall("+z", a0, y1 - 0.1, 0.025)), tile=1.0)


def build_staff_door():
    """A closed pair of staff doors on the east wall (the way to the back of house, BLENDER_AREAS: not built yet; it does not open): a frame, two leaves
    with steel kick plates and small dark windows, and a STAFF ONLY board. All within 5 cm of the wall."""
    a0, a1 = STAFF["z"]
    h = STAFF["h"]
    am = (a0 + a1) / 2

    def frame(bm):
        wall_box(bm, "-x", a0 - 0.08, a0, 0, h + 0.08, 0.0, 0.03)
        wall_box(bm, "-x", a1, a1 + 0.08, 0, h + 0.08, 0.0, 0.03)
        wall_box(bm, "-x", a0, a1, h, h + 0.08, 0.0, 0.03)
    part("Staff_Frame", "Frame_Alu", frame)
    part("Staff_Leaves", "Staff_Door", lambda bm: [wall_box(bm, "-x", s0, s1, 0.01, h, 0.0, 0.02) for s0, s1 in ((a0 + 0.005, am - 0.003), (am + 0.003, a1 - 0.005))])
    part("Staff_Kick", "Trim_Steel", lambda bm: [wall_box(bm, "-x", s0 + 0.02, s1 - 0.02, 0.02, 0.28, 0.0, 0.025) for s0, s1 in ((a0, am), (am, a1))])
    part("Staff_Windows", "Plastic_Black", lambda bm: [wall_box(bm, "-x", c - 0.12, c + 0.12, 1.35, 1.75, 0.0, 0.022) for c in ((a0 + am) / 2, (am + a1) / 2)])


SIGNS = [("PRODUCE", "+x", 0.0), ("DAIRY", "+z", None), ("FROZEN", "+z", None), ("STAFF ONLY", "-x", None)]


def build_signs():
    """Painted boards for the departments, flat on the walls above head height: PRODUCE (west), DAIRY and FROZEN (over the coolers), STAFF ONLY."""
    (c0a, c0b), (c1a, c1b) = cooler_spans()
    shelf_z = (SHELVES[0]["min"][2] + SHELVES[0]["max"][2]) / 2
    places = {"PRODUCE": ("+x", shelf_z, 2.95, 3.4, 0.62), "DAIRY": ("+z", (c0a + c0b) / 2, 2.95, 2.6, 0.55), "FROZEN": ("+z", (c1a + c1b) / 2, 2.95, 2.6, 0.55),
              "STAFF ONLY": ("-x", sum(STAFF["z"]) / 2, STAFF["h"] + 0.36, 1.5, 0.3)}
    rows = len(DEPT_WORDS)
    boards = []
    for word, (n, a, y, w, h) in places.items():
        i = DEPT_WORDS.index(word)
        boards.append((n, a, y, w, h))
        panel(f"Sign_{word.replace(' ', '_')}", "Sign_Dept", on_wall(n, a, y, 0.0255), n, w, h, uv=(0, 1 - (i + 1) / rows, 1, 1 - i / rows))
    part("Sign_Boards", "EndCap_Red", lambda bm: [wall_box(bm, n, a - w / 2 - 0.02, a + w / 2 + 0.02, y - h / 2 - 0.02, y + h / 2 + 0.02, 0.0, 0.025) for n, a, y, w, h in boards])


def build_ceiling():
    """Strip lights over the middle of each aisle, hung on rods (Light_Housing, the diffuser Lamp_Emit), air diffusers in the tiles, the hangers of
    the page's price signs, and the security camera's wall bracket (the page draws the camera's head and its red light, which sweep)."""
    def housings(bm):
        for x in STRIPS:
            cube(bm, (x - 0.09, STRIP_Y, -STRIP_Z), (x + 0.09, STRIP_Y + 0.09, STRIP_Z))
    part("Strip_Housings", "Light_Housing", housings)

    def diffusers(bm):
        for x in STRIPS:
            quad(bm, (x - 0.07, STRIP_Y - 0.001, -STRIP_Z + 0.05), (x + 0.07, STRIP_Y - 0.001, -STRIP_Z + 0.05), (x + 0.07, STRIP_Y - 0.001, STRIP_Z - 0.05), (x - 0.07, STRIP_Y - 0.001, STRIP_Z - 0.05))
    part("Strip_Diffusers", "Lamp_Emit", diffusers)

    def rods(bm):
        for x in STRIPS:
            n = 8
            for i in range(n + 1):
                z = -STRIP_Z + 0.3 + (2 * STRIP_Z - 0.6) * i / n
                cyl(bm, (x, STRIP_Y + 0.09, z), (x, H, z), 0.006, seg=6, cap=False)
        for sh in SHELVES:                                                     # the price signs' hangers: the page hangs a 2.2 x 0.42 m sign at y 2.5, 2 cm past the shelf's south end
            xc = (sh["min"][0] + sh["max"][0]) / 2
            for dx in (-0.9, 0.9):
                cyl(bm, (xc + dx, 2.5 + 0.21, sh["max"][2] + 0.02), (xc + dx, H, sh["max"][2] + 0.02), 0.004, seg=6, cap=False)
        # the camera bracket: a wall plate, an arm out to the camera's pivot, a short drop to the top of the page's camera body (0.2 m tall, centred on CAMERA.at)
        cx, cy, cz = CAM
        cube(bm, (cx - 0.08, cy + 0.22, -HZ), (cx + 0.08, cy + 0.46, -HZ + 0.015))
        cube(bm, (cx - 0.025, cy + 0.31, -HZ + 0.015), (cx + 0.025, cy + 0.37, cz + 0.03))
        cyl(bm, (cx, cy + 0.105, cz), (cx, cy + 0.31, cz), 0.02, seg=10)
        cyl(bm, (cx, cy + 0.10, cz), (cx, cy + 0.12, cz), 0.045, seg=12)
    part("Ceiling_Rods_Bracket", "Metal_Dark", rods)

    def vents(bm):
        for sh in SHELVES:
            xc = (sh["min"][0] + sh["max"][0]) / 2
            for z in (sh["min"][2] + 1.5, sh["max"][2] + 3.5):
                cube(bm, (xc - 0.3, H - 0.012, z - 0.3), (xc + 0.3, H, z + 0.3))
                cube(bm, (xc - 0.2, H - 0.03, z - 0.2), (xc + 0.2, H - 0.012, z + 0.2))
                cube(bm, (xc - 0.1, H - 0.045, z - 0.1), (xc + 0.1, H - 0.03, z + 0.1))
    part("Ceiling_Vents", "Light_Housing", vents)


def build_backdrop():
    """The street across the road (Hallam Row, by day), seen through the storefront: a picture on a plane BACKDROP_Z out, and the pavement and road in
    front of it on a ground plane. Both emissive, no lightmap, passable (decor_)."""
    zb = BACKDROP_Z
    gv = GROUND_V
    panel("decor_backdrop", "Backdrop_Street", (0.0, BACKDROP_H / 2, zb), "-z", BACKDROP_W, BACKDROP_H, uv=(0, gv, 1, 1))
    bm = bmesh.new()
    z0 = HZ + WALL_T
    f = quad(bm, (BACKDROP_W / 2, 0.0, z0), (-BACKDROP_W / 2, 0.0, z0), (-BACKDROP_W / 2, 0.0, zb), (BACKDROP_W / 2, 0.0, zb))
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp, t in zip(f.loops, ((0, 0), (1, 0), (1, gv), (0, gv))):              # u runs to -x, as on the street plane seen from the store
        lp[uvl].uv = t
    bm.normal_update()
    if f.normal.z < 0:                                                                      # face up (Blender +z)
        f.normal_flip()
    finish("decor_backdrop_ground", bm, "Backdrop_Street", ART, keep_uv=True)


# ---------------------------------------------------------------- generated images (own work, numpy, fixed seeds)
GLYPHS = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"], "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"], "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"], "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"], "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"], "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"], "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"], "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"], "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"], "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"], "$": ["00100", "01111", "10100", "01110", "00101", "11110", "00100"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"], "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"], "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    " ": ["00000"] * 7,
}
DEPT_WORDS = ["PRODUCE", "DAIRY", "FROZEN", "STAFF ONLY"]
GROUND_V = 0.2          # the street picture's bottom fifth is the ground in front of it (pavement, kerb, road), the rest the far side


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


def draw_text(img, text, box, fg, fill=0.7):
    """Pixel-font text centred in box (r0, r1, c0, c1) of img, as large as fits `fill` of the box."""
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


def dept_pixels():
    """The department boards: cream letters on the store's deep red, one word a row."""
    W, R = 1024, 160
    img = np.zeros((R * len(DEPT_WORDS), W, 3), np.float32)
    img[:] = (0.42, 0.05, 0.05)
    for i, w in enumerate(DEPT_WORDS):
        draw_text(img, w, (i * R, (i + 1) * R, 0, W), (0.92, 0.86, 0.70), 0.78)
        img[i * R:i * R + 6] = img[(i + 1) * R - 6:(i + 1) * R] = (0.30, 0.03, 0.03)
    rng = np.random.default_rng(21)
    return np.clip(blur(img, 1, 1) * (0.94 + 0.08 * blur(rng.random(img.shape[:2]).astype(np.float32), 3, 2))[..., None], 0, 1).astype(np.float32)


def glow_pixels():
    """The lit signs: EXIT (top half, green) and the checkout's lane number 1 (bottom left, white on red)."""
    img = np.zeros((256, 512, 3), np.float32)
    img[:128] = (0.02, 0.45, 0.16)
    draw_text(img, "EXIT", (0, 128, 0, 512), (0.95, 1.0, 0.95), 0.62)
    img[128:, :256] = (0.6, 0.04, 0.04)
    draw_text(img, "1", (128, 256, 0, 256), (1.0, 0.97, 0.9), 0.7)
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def signs_pixels():
    """Stand-ins of the page's price signs (index.html signTexture: cream on #1a1a1e), for the review stills only."""
    from_page = [("APPLES $1", "apple"), ("BREAD $2", "bread"), ("CANNED SOUP $3", "soup"), ("READY MEAL $6", "meal")]
    img = np.zeros((96 * 4, 512, 3), np.float32)
    img[:] = srgb_hex(0x1a1a1e)
    for i, (t, _) in enumerate(from_page):
        draw_text(img, t, (i * 96, (i + 1) * 96, 0, 512), srgb_hex(0xe8e0c0), 0.8)
    return img


def pegboard_pixels():
    S, step = 256, 16                           # 0.4 m a repeat: a hole every 25 mm
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.80, 0.79, 0.76)
    yy, xx = np.mgrid[0:S, 0:S]
    d = np.hypot((yy % step) - step / 2 + 0.5, (xx % step) - step / 2 + 0.5)
    hole = np.clip(3.6 - d, 0, 1)[..., None]
    return (img * (1 - hole) + np.array([0.08, 0.08, 0.08]) * hole).astype(np.float32)


def cooler_pixels():
    """One cooler door's interior, lit: pale walls, LED strips at the sides, five wire shelves, a few cartons left (most of it empty)."""
    Wd, Hd = 256, 512
    rng = np.random.default_rng(17)
    img = np.zeros((Hd, Wd, 3), np.float32)
    x = np.linspace(-1, 1, Wd)[None, :, None]
    img[:] = np.array([0.62, 0.68, 0.72]) * (0.75 + 0.25 * (1 - x ** 2))
    img[:, :10] = img[:, -10:] = (1.0, 1.0, 0.98)                    # the LED strips in the mullions
    img[:, 10:22] *= 1.25
    img[:, -22:-10] *= 1.25
    pal = [(0.92, 0.92, 0.88), (0.15, 0.35, 0.75), (0.80, 0.18, 0.12), (0.95, 0.65, 0.15), (0.35, 0.65, 0.30)]
    shelves = [int(Hd * f) for f in (0.18, 0.36, 0.54, 0.72, 0.90)]
    for s in shelves:
        for c in range(24, Wd - 24, 30):
            if rng.random() < 0.3:
                h = int(rng.uniform(40, 70))
                col = np.array(pal[rng.integers(len(pal))]) * rng.uniform(0.75, 1.0)
                img[s - h:s, c:c + 24] = col
                img[s - h:s - h + 4, c:c + 24] *= 1.15
        img[s:s + 6] = (0.85, 0.86, 0.85)
        img[s + 6:s + 14] *= 0.55                                     # the shelf's shadow
    img[shelves[-1] + 14:] *= 0.6
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def street_pixels():
    """Hallam Row by day, across the road: the far side's shopfronts and flats on the upper rows (y 0 .. BACKDROP_H on the plane), and the ground in front
    of the storefront on the bottom GROUND_V of the picture (the near pavement, the kerb, the road with its centre line, the far kerb and pavement)."""
    W, Hh = 2048, 1280
    rng = np.random.default_rng(29)
    img = np.zeros((Hh, W, 3), np.float32)
    fr = int(Hh * (1 - GROUND_V))                                # rows 0..fr: the far side; fr..Hh: the ground
    ppx = W / BACKDROP_W
    ppy = fr / BACKDROP_H
    yy = BACKDROP_H - (np.arange(fr) + 0.5) / ppy                 # each row's height on the plane
    t = np.clip(yy / BACKDROP_H, 0, 1)[:, None, None]
    img[:fr] = np.array([0.80, 0.86, 0.92]) * (1 - t) + np.array([0.42, 0.62, 0.90]) * t
    pal = [(0.50, 0.26, 0.20), (0.62, 0.55, 0.46), (0.45, 0.42, 0.40), (0.58, 0.36, 0.26), (0.70, 0.66, 0.56), (0.40, 0.30, 0.26)]
    x = -BACKDROP_W / 2
    while x < BACKDROP_W / 2:
        w = rng.uniform(6.0, 13.0)
        roof = rng.uniform(8.0, 17.0)
        if rng.random() < 0.1:
            x += rng.uniform(2.0, 4.0)
            continue
        c0, c1 = int((x + BACKDROP_W / 2) * ppx), min(W, int((x + w + BACKDROP_W / 2) * ppx))
        rows = yy < roof
        col = np.array(pal[rng.integers(len(pal))]) * rng.uniform(0.8, 1.0)
        img[:fr][rows, c0:c1] = col
        rtop = int((BACKDROP_H - roof) * ppy)
        img[rtop:rtop + 6, c0:c1] = col * 0.6                    # the parapet's shadow line
        # the shopfront: dark glass between y 0.4 and 3.2, an awning over some
        g0, g1 = int((BACKDROP_H - 3.2) * ppy), int((BACKDROP_H - 0.4) * ppy)
        img[g0:g1, c0 + 6:c1 - 6] = np.array([0.16, 0.19, 0.22]) * rng.uniform(0.8, 1.2)
        img[g0:g0 + 4, c0 + 6:c1 - 6] = (0.2, 0.2, 0.2)
        if rng.random() < 0.6:
            a0 = int((BACKDROP_H - 3.9) * ppy)
            stripe = np.array(pal[rng.integers(len(pal))]) if rng.random() < 0.5 else np.array((0.25, 0.42, 0.32))
            for k in range(c0, c1, 12):
                img[a0:g0, k:k + 6] = stripe
                img[a0:g0, k + 6:k + 12] = (0.88, 0.86, 0.80)
        # the upper floors: rows of windows
        for wy in np.arange(4.6, roof - 1.4, 3.0):
            for wx in np.arange(x + 1.0, x + w - 1.2, 2.2):
                r0, r1 = int((BACKDROP_H - (wy + 1.5)) * ppy), int((BACKDROP_H - wy) * ppy)
                k0, k1 = int((wx + BACKDROP_W / 2) * ppx), int((wx + 1.1 + BACKDROP_W / 2) * ppx)
                if k1 > W:
                    continue
                img[r0:r1, k0:k1] = np.array([0.22, 0.28, 0.34]) * rng.uniform(0.7, 1.3)
                img[r1:r1 + 3, k0 - 2:k1 + 2] = (0.82, 0.80, 0.74)
                if rng.random() < 0.3:
                    img[r0:r0 + (r1 - r0) // 2, k0:k1] = (0.85, 0.82, 0.72)         # a drawn blind
        x += w
    img[int((BACKDROP_H - 0.25) * ppy):fr] = (0.62, 0.62, 0.60)       # the far pavement's edge at the foot of the buildings
    # the ground: v 0 (bottom row) is the storefront's outer face, v GROUND_V (row fr) is the foot of the far side
    gz = HZ + WALL_T + (BACKDROP_Z - HZ - WALL_T) * (1 - (np.arange(fr, Hh) - fr + 0.5) / (Hh - fr))       # each ground row's game z
    road0, road1 = HZ + WALL_T + 3.5, BACKDROP_Z - 3.0
    g = img[fr:]
    near = (gz < road0)[:, None]
    far = (gz > road1)[:, None]
    g[:] = np.where((near | far)[:, :, None], np.array([0.62, 0.61, 0.58]), np.array([0.20, 0.20, 0.21]))
    kerb = ((np.abs(gz - road0) < 0.15) | (np.abs(gz - road1) < 0.15))
    g[kerb] = (0.75, 0.74, 0.70)
    mid = np.abs(gz - (road0 + road1) / 2) < 0.08
    xs = (np.arange(W) + 0.5) / ppx - BACKDROP_W / 2
    dash = ((xs % 6.0) < 3.0)[None, :]
    g[mid[:, None] & dash] = (0.85, 0.80, 0.55)
    joints = ((xs % 1.5) < 0.04)[None, :] & (near | far)
    g[joints] *= 0.8
    n = blur(rng.random((Hh, W)).astype(np.float32), 2, 2)
    img *= (0.9 + 0.2 * n)[..., None]
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


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


# ---------------------------------------------------------------- the textures stage: the CC0 maps -> blender/textures/main_floor/
def stage_textures():
    """From the three Poly Haven diffuse maps (1k JPEG, --src <folder>) make the build's three textures (JPEG q88):
    floor_tiles_06 -> floor_tiles_diff.jpg: the grid moved to the image's edges, the light tiles a warm cream, the dark ones a grey-green, the stone's detail kept, darker grout;
    polystyrene -> ceiling_tile_diff.jpg: a pale tile with two 0.6 x 1.2 m lay-in tiles and their white grid, the foam's grain kept faintly;
    painted_plaster_wall -> wall_paint_diff.jpg: neutral (grey), lifted to near white, so each wall material's colour factor tints it."""
    src = Path(arg("--src", "."))
    TEX.mkdir(parents=True, exist_ok=True)

    def load(fn):
        im = bpy.data.images.load(str(src / fn))
        w, h = im.size
        a = np.empty(w * h * 4, np.float32)
        im.pixels.foreach_get(a)
        bpy.data.images.remove(im)
        return np.flipud(a.reshape(h, w, 4)[..., :3])            # rows top to bottom, sRGB values (a JPEG loads as sRGB bytes / 255)

    def save(arr, fn):
        h, w = arr.shape[:2]
        im = bpy.data.images.new(fn, w, h)
        rgba = np.ones((h, w, 4), np.float32)
        rgba[..., :3] = np.clip(arr, 0, 1)
        im.pixels.foreach_set(np.flipud(rgba).ravel())
        im.filepath_raw = str(TEX / fn)
        im.file_format = "JPEG"
        im.save(filepath=str(TEX / fn), quality=88)                  # Image.save: the pixels as they are (save_render would apply the view transform)
        bpy.data.images.remove(im)
        print("TEXTURE", fn, (TEX / fn).stat().st_size)

    # the floor: the source is a 4 x 4 checker whose grout sits at rows 184 + 256k and columns 4 + 256k; roll it to 0 so the tiles' parity is (x//256 + y//256) % 2
    a = np.roll(load("floor_tiles_06_diff_1k.jpg"), (-184, -4), axis=(0, 1))
    g = a @ np.array([0.299, 0.587, 0.114], np.float32)
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    par = (((xx // 256) + (yy // 256)) % 2 == 0)
    light = par if g[par].mean() > g[~par].mean() else ~par
    out = np.zeros_like(a)
    for m, col in ((light, np.array([0.80, 0.77, 0.69])), (~light, np.array([0.47, 0.50, 0.47]))):
        d = g[m] - np.median(g[m])
        out[m] = col * (1 + d[:, None] * 1.6)
    e = np.minimum(np.minimum(xx % 256, 255 - xx % 256), np.minimum(yy % 256, 255 - yy % 256))
    save(out * (0.62 + 0.38 * np.clip(e / 3.0, 0, 1)[..., None]), "floor_tiles_diff.jpg")

    # the ceiling: two lay-in tiles side by side (u = game x: 0.6 m each), the T-bar 24 mm wide on every edge
    p = load("polystyrene_diff_1k.jpg").mean(axis=2)
    S = p.shape[0]
    img = np.repeat((0.86 + (p - p.mean()) * 0.6)[..., None], 3, axis=2) * np.array([1.0, 0.99, 0.96])
    bar = 10
    for c in (0, S // 2):
        img[:, max(0, c - bar):c + bar] = (0.80, 0.80, 0.79)
    img[:, -bar:] = img[:bar] = img[-bar:] = (0.80, 0.80, 0.79)
    save(img, "ceiling_tile_diff.jpg")

    # the walls: neutral and light
    w = load("painted_plaster_wall_diff_1k.jpg").mean(axis=2, keepdims=True)
    save(np.clip(0.88 + (w - w.mean()) * 0.8, 0, 1) * np.ones(3), "wall_paint_diff.jpg")


# ---------------------------------------------------------------- the page's things, as stand-ins (index.html groceryProps)
def build_standins():
    """What the page draws, built as the blockout builds it: the food boxes on the shelves and the three carts in the corral (in the bake: their contact
    shadows), the camera's head at rest (yaw 0) and the price signs (the review stills only). Never exported."""
    for sh in SHELVES:
        def food(bm):
            for y in (0.35, 0.95, 1.55):
                z = sh["min"][2] + 0.3
                while z < sh["max"][2] - 0.2:
                    for side in (-1, 1):
                        x0 = sh["min"][0] + 0.05 if side < 0 else sh["max"][0] - 0.4
                        x1 = sh["min"][0] + 0.4 if side < 0 else sh["max"][0] - 0.05
                        cube(bm, (x0, y, z), (x1, y + 0.3, z + 0.35))
                    z += 0.55
        part(f"standin_food_{sh['food']}", f"Standin_{sh['food']}", food, coll=STANDIN)

    def carts(bm, handles=False):
        for i in range(3):
            z0 = CART["min"][2] + 0.05 + i * 0.05
            x0 = CART["min"][0] + i * 0.12
            if handles:
                cube(bm, (x0 + 0.85, 0.85, z0), (x0 + 0.9, 1.05, z0 + 0.55))
            else:
                cube(bm, (x0, 0.35, z0), (x0 + 0.9, 0.85, z0 + 0.55))
    part("standin_carts", "Standin_Cart", carts, coll=STANDIN)
    part("standin_cart_handles", "Standin_Grey", lambda bm: carts(bm, True), coll=STANDIN)
    cx, cy, cz = CAM
    part("standin_camera", "Standin_Camera", lambda bm: cube(bm, (cx - 0.11, cy - 0.1, cz - 0.1), (cx + 0.11, cy + 0.1, cz + 0.4)), coll=STANDIN)
    part("standin_camera_led", "Standin_LED", lambda bm: cube(bm, (cx + 0.045, cy + 0.035, cz + 0.4), (cx + 0.095, cy + 0.085, cz + 0.42)), coll=STANDIN)
    for i, sh in enumerate(SHELVES):
        xc = (sh["min"][0] + sh["max"][0]) / 2
        panel(f"standin_sign_{sh['food']}", "Standin_Sign", (xc, 2.5, sh["max"][2] + 0.02), "+z", 2.2, 0.42, uv=(0, 1 - (i + 1) / 4, 1, 1 - i / 4), coll=STANDIN)


STILLS_ONLY = ("standin_camera", "standin_camera_led", "standin_sign_")     # stand-ins hidden in the bake


# ---------------------------------------------------------------- lights, world
STRIP_W = 300.0         # each strip light (an area light the length of the strip, pointing down)
SUN_W = 2.0             # the day's sun, low in the south, through the storefront
WORLD_STRENGTH = 1.0    # the sky, seen through the storefront


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

    for i, x in enumerate(STRIPS):
        ob, d = light(f"Strip_{i}", "AREA", (x, STRIP_Y - 0.004, 0.0), STRIP_W, (0.96, 0.98, 1.0), 0.0)
        d.shape, d.size, d.size_y = "RECTANGLE", 0.14, 2 * STRIP_Z - 0.1          # local x = game x, local y = Blender y = game -z; it shines down (-Blender z)
    ob, d = light("Sun", "SUN", (0, 20, HZ + 10), SUN_W, (1.0, 0.93, 0.82), 0.0)
    d.angle = math.radians(1.0)
    ob.rotation_euler = B((-0.35, -0.45, -0.82)).to_track_quat("-Z", "Y").to_euler()     # from high in the south-east: patches fall on the floor inside the windows


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("Day")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.55, 0.68, 0.90, 1)
    bg.inputs["Strength"].default_value = WORLD_STRENGTH


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
    gen = {"pegboard": mk_image("Pegboard", pegboard_pixels()), "dept": mk_image("Dept_Signs", dept_pixels()), "glow": mk_image("Glow_Signs", glow_pixels()),
           "cooler": mk_image("Cooler_Inside", cooler_pixels()), "street": mk_image("Street_Day", street_pixels()), "signs": mk_image("Price_Signs_Standin", signs_pixels())}
    make_materials(gen)
    build_shell()
    build_trim()
    build_storefront()
    build_shelves()
    build_checkout()
    build_corral()
    build_coolers()
    build_staff_door()
    build_signs()
    build_ceiling()
    build_backdrop()
    build_standins()
    add_lights()
    setup_world()
    ensure_marker()
    for o in ART.objects:
        if o.name.startswith("decor_backdrop"):
            o.visible_shadow = False                 # the sun shines past the street picture onto the storefront


# ---------------------------------------------------------------- bake
GROUPS = [["Floor_Tile", "Mat_Rubber", "Ceiling_Tile"],                                                          # 0: the floor and the ceiling
          ["Wall_Paint", "Wall_Lower", "Trim_Steel", "Sign_Dept", "Staff_Door", "Cooler_Frame"],                  # 1: the walls and what is flat on them
          ["Shelf_Paint", "Shelf_Back", "Shelf_Kick", "EndCap_Red", "Price_Rail", "Counter_Laminate", "Counter_Top",
           "Belt_Rubber", "Plastic_Black", "Rail_Steel", "Frame_Alu"],                                            # 2: the shelves, the checkout, the corral, the storefront
          ["Light_Housing", "Metal_Dark"]]                                                                        # 3: the fittings up by the lights (hotter texels, own scale)
PAGES = [1152, 1024, 1792, 768]        # each map's fixed page size (px): the smallest page of the search that gave >= 30 px/m on the first run. Fixed, because
                                        # Blender's island packer is not exactly repeatable (the galleries build's lesson); --pages auto searches again
if arg("--pages"):
    PAGES = [None] * 4 if arg("--pages") == "auto" else [int(v) for v in arg("--pages").split(",")]
NOLM = ("Lamp_Emit", "Window_Glass", "Cooler_Lit", "Sign_Glow", "Screen_Glow", "Backdrop_Street")
SHELL_PREFIX = ("Wall_", "Floor_", "Ceiling_")
HIDE_IN_BAKE = ("Window_Glass",)       # transparent panes: hidden while baking, so the daylight comes in and the coolers' glow comes out


def in_room(p, e=1e-3):
    return -HX - e <= p[0] <= HX + e and -e <= p[1] <= H + e and -HZ - e <= p[2] <= HZ + e


def in_opening(p):
    return any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 and HZ - 1e-3 <= p[2] <= HZ + WALL_T + 1e-3 for x0, x1, y0, y1 in openings_s())


def trim_unseen(bm, d):
    """Drop the faces that are never seen: a face is kept only when the point `d` in front of it lies inside the store or inside one of the south wall's
    openings. That drops the walls' outer skin, the floor's underside, the ceiling's top, the faces shared inside the cut-up south wall, and every piece's
    faces flat against a wall, the floor or the ceiling. They would cost lightmap texels."""
    bad = []
    for f in bm.faces:
        c, n = f.calc_center_median(), f.normal
        p = [c.x + n.x * d, c.z + n.z * d, -(c.y + n.y * d)]
        if not (in_room(p, 0.0) or in_opening(p)):
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
        if not ob.name.startswith("decor_backdrop") and mname not in ("Window_Glass",):
            trim_unseen(tmp, 0.01 if ob.name.startswith(SHELL_PREFIX) else 0.003)
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
        if mname == "Backdrop_Street":
            ob.visible_shadow = False
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


def stage_bake():
    import time
    stage_work()
    exp = make_export_objects()
    bpy.data.collections["Art"].hide_render = True
    bpy.data.collections["Art"].hide_viewport = True
    hidden = [o for o in bpy.data.collections["Standins"].objects if o.name.startswith(STILLS_ONLY) and not o.hide_render]
    for o in hidden:
        o.hide_render = True
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
        scale = float(pc[3])                                 # the 99.5th percentile of the lit texels maps to white; the few hotter ones (right under a lamp) clip
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
    for o in hidden:
        o.hide_render = False
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
    Strip all of that here, so a re-run on any machine stays clean (the galleries build's scrub, unchanged)."""
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
        except ValueError:
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
    rx = CO["max"][0] - 0.9
    shots = {
        "1_arrival": look_cam("arrival", (arrive[0], 1.6, arrive[2]), (arrive[0] + face[0] * 3, 1.6, arrive[2] + face[1] * 3), 75.0),
        "2_wide": look_cam("wide", (HX - 0.7, H - 0.6, HZ - 0.6), (-4.5, 0.3, -4.5), 70.0),
        "3_detail": look_cam("detail", (CO["at"][0] - 0.3, 1.65, CO["at"][1] - 0.9), (rx + 0.05, 1.05, CO["min"][2] + 0.45), 52.0),     # the till, from where the shopper stands
    }
    plan = look_cam("plan", (0, H + 8, 0), None, ortho=2 * HX + 1.2)
    arts = list(bpy.data.collections["Art"].objects) + list(bpy.data.collections["Standins"].objects)
    cut_plan = [o for o in arts if o.name.startswith(("Ceiling_", "Strip_", "decor_backdrop"))]
    todo = [(k, v, (1920, 1080)) for k, v in shots.items()] + [("4_plan", plan, (1800, int(1800 * (2 * HZ + 1.2) / (2 * HX + 1.2))))]
    for key, cam, (w, h) in todo:
        if which not in ("all", key):
            continue
        sc.camera = cam
        sc.view_settings.exposure = expo
        for o in arts:
            o.visible_camera = True
        for o in {"4_plan": cut_plan}.get(key, []):
            o.visible_camera = False                      # a cut-away view: these stay in the store for the light and the shadows, the camera just does not see them
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
    if STAGE == "textures":
        stage_textures()
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
