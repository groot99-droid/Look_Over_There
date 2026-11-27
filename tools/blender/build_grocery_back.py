"""Dresses and lights the grocery's restricted staff areas, `back_of_house` and `basement` (docs/BLENDER_AREAS.md section 2), in Blender, bakes a
day set and a night set for each, and exports world/<scene>.glb and world/<scene>.json.

Re-runnable, from the repo root (every stage takes --scene back_of_house or --scene basement):

    blender -b --python tools/blender/build_grocery_back.py -- --scene <id> --stage art      (the art and the layout objects; saves blender/scenes/<id>.blend,
                                                                                              writes world/<id>.json and runs the layout check)
    blender -b blender/scenes/<id>.blend --python tools/blender/build_grocery_back.py -- --scene <id> --stage bake [--samples 512] [--night-samples 1024]
    blender -b blender/scenes/<id>.blend --python tools/blender/build_grocery_back.py -- --scene <id> --stage export
    blender -b blender/scenes/<id>.blend --python tools/blender/build_grocery_back.py -- --scene <id> --stage axes
    blender -b blender/scenes/<id>.blend --python tools/blender/build_grocery_back.py -- --scene <id> --stage render [--set night] [--only 1_arrival]
    python tools/blender/pack_scene.py <id> --work work/<id>                                  (WebP lightmaps and textures -> world/)

The layout is the greybox's: tools/blender/build_grocery_greybox.py `back_of_house()` and `basement()` (imported here, no coordinate copied by hand)
give every collider, door, link, marker, zone, camera and spot. This build puts the art round them and writes the same names (COL_, DoorLeaf_,
Link_/Arrive_, Marker_, SecCam_, Zone_, Spot_) into the .blend, so tools/blender/export_scene.py writes the same world/<id>.json as the greybox
model does (`build_grocery_greybox.py --preview`).

The look: the staff side of part 1's main_floor, off and empty but seemingly normal. Bare concrete floors, painted block walls with a mid-grey dado and
a safety-yellow band, steel pallet racking stacked with cartons, three shut roller dock doors, a break room, grey lockers, the manager's office with
a bank of CRT camera monitors that stay lit, the freight lift with its heavy gate and the keycard reader (the way to Secret Operations). Below: two
walk-in freezers glowing cold, a plant room (boilers, a chiller, pumps, pipes, the breaker board), pallet stacks, a sump and bare bulbs.
Light: day = the working fluorescents (and the basement's bulbs); night = abandoned: only the freezers' glow, the emergency lights, the exit signs,
the monitors and the reader. Both sets bake to the same lightmap UVs: `lightmap` (day) and `lightmap_night` (night), as the mall entrance does.
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
import build_grocery_greybox as G          # noqa: E402  the layout model (pure Python)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


SCENE = arg("--scene", "back_of_house")
assert SCENE in ("back_of_house", "basement"), SCENE
STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 512, int)
NIGHT_SAMPLES = arg("--night-samples", None, int) or 2 * SAMPLES
DEVICE = arg("--device", "auto")
BOH = SCENE == "back_of_house"

TEXDIR = ROOT / "blender/textures"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"
MARGIN_PX = 8

GB = G.back_of_house() if BOH else G.basement()
BOX = {b["name"]: b for b in GB.boxes}
COLS = [b for b in GB.boxes if b["col"]]
T = G.T
X0, X1 = G.BX0, G.BX1
Z0, Z1 = (G.BZ0, G.BZ1) if BOH else (G.KZ0, G.KZ1)
H = G.BH if BOH else G.KH
LOW, BAND = 0.95, 1.2            # the walls: mid-grey block to 0.95 m, the safety-yellow band to 1.2 m, light grey block above
SPAWN = next(e for e in GB.empties if e["name"] == "Marker_Spawn")["pos"]
ARRIVE = next(e for e in GB.empties if e["name"] == ("Arrive_main_floor" if BOH else "Arrive_freight_up"))
EMPT = {e["name"]: e for e in GB.empties}


def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


def lin(c):
    """sRGB display value -> linear"""
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


def srgb(c):
    return tuple(v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055 for v in c)


# ---------------------------------------------------------------- materials
IMG_CACHE, MATS, TILES = {}, {}, {}


def image(fn, srgb_=True):
    key = (fn, srgb_)
    if key not in IMG_CACHE:
        im = bpy.data.images.load(str(TEXDIR / fn))
        im.colorspace_settings.name = "sRGB" if srgb_ else "Non-Color"
        IMG_CACHE[key] = im
    return IMG_CACHE[key]


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, diff=None, img=None, tint=None, emit=None, emit_img=None, tile=None, two_sided=False):
    """A Principled material. `tint` multiplies the diffuse texture (a Mix node set to Multiply: the glTF exporter writes it as baseColorFactor).
    emit = (colour, strength); emit_img = (image, strength): the image drives the emission colour (an emissive texture)."""
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
    if emit_img:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = emit_img[0]
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        nt.links.new(n.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emit_img[1]
        bsdf.inputs["Base Color"].default_value = (0.02, 0.02, 0.02, 1)
    m.use_backface_culling = not two_sided
    TILES[name] = tile or 1.0
    MATS[name] = m
    return m


# the toggled and the steady glows (no lightmap on any of them)
LAMP_EMIT = 8.0          # Lamp_Emit: the fluorescent tubes, the troffers and the basement's bulbs; on by day, off at night (abandoned)
EMERG_EMIT = 6.0         # Emergency_Emit: the emergency lights' heads; on at night only
EXIT_EMIT = 2.5          # Exit_Glow: the maintained EXIT signs, on at every hour
CRT_EMIT = 1.4           # Screen_CRT: the camera monitors, on at every hour (the page may put the SecCam_ feeds on them)
READER_EMIT = 5.0        # Reader_Glow: the keycard reader's ring and screen, on at every hour
FREEZER_EMIT = 3.5       # Freezer_Glow: the freezers' door windows, their status lamps and their lights inside, on at every hour
EMISSIVE = ("Lamp_Emit", "Emergency_Emit", "Exit_Glow", "Screen_CRT", "Reader_Glow", "Freezer_Glow")


def make_materials(gen):
    material("Floor_Concrete", diff="factory_floor/concrete_floor_diff.jpg", tint=(1.0, 0.98, 0.95), rough=0.8, tile=3.2)
    material("Floor_Vinyl", diff="laboratory/floor_vinyl_diff.jpg", tint=(0.80, 0.84, 0.82), rough=0.5, tile=2.0)
    material("Floor_Frost", img=gen["frost"], tint=(0.86, 0.92, 0.98), rough=0.4, tile=1.6)
    material("Floor_Plate", img=gen["plate"], tint=(0.62, 0.63, 0.64), rough=0.4, metal=0.6, tile=0.3)
    material("Floor_Paint", color=lin((0.86, 0.68, 0.10)), rough=0.6)                                    # the yellow floor lines
    material("Wall_Block", img=gen["block"], tint=(0.84, 0.84, 0.81), rough=0.9, tile=2.0)
    material("Wall_Lower", img=gen["block"], tint=(0.30, 0.32, 0.33), rough=0.8, tile=2.0)
    material("Wall_Band", img=gen["block"], tint=(0.92, 0.62, 0.02), rough=0.7, tile=2.0)
    material("Ceiling_Soffit", img=gen["soffit"], tint=(0.80, 0.80, 0.78), rough=0.95, tile=2.4)
    material("Ceiling_Tile", diff="main_floor/ceiling_tile_diff.jpg", rough=0.95, tile=1.2)
    material("Freezer_Panel", img=gen["panel"], tint=(0.86, 0.88, 0.88), rough=0.5, tile=1.2)
    material("Frost_Panel", img=gen["frost"], tint=(0.84, 0.90, 0.96), rough=0.45, tile=1.6)
    material("Steel_Blue", diff="factory_floor/paint_grime_diff.jpg", tint=(0.06, 0.16, 0.42), rough=0.5, metal=0.3, tile=1.2)
    material("Steel_Orange", diff="factory_floor/paint_grime_diff.jpg", tint=(0.80, 0.26, 0.03), rough=0.5, metal=0.3, tile=1.2)
    material("Steel_Grey", diff="factory_floor/paint_grime_diff.jpg", tint=(0.34, 0.36, 0.37), rough=0.5, metal=0.3, tile=1.2)
    material("Steel_Galv", diff="factory_floor/paint_grime_diff.jpg", tint=(0.50, 0.51, 0.51), rough=0.4, metal=0.7, tile=1.2)
    material("Steel_Yellow", diff="factory_floor/paint_grime_diff.jpg", tint=(0.85, 0.56, 0.02), rough=0.5, metal=0.2, tile=1.2)
    material("Steel_Dark", color=(0.04, 0.04, 0.045), rough=0.5, metal=0.6)
    material("Rubber_Black", color=(0.025, 0.025, 0.025), rough=0.9)
    material("Hazard", img=gen["hatch"], rough=0.6, tile=0.6)
    material("Shutter", img=gen["shutter"], tint=(0.74, 0.78, 0.82), rough=0.45, metal=0.5, tile=1.0)
    material("Pallet_Wood", img=gen["pine"], rough=0.8, tile=1.0)
    material("Wood_Light", img=gen["pine"], tint=(0.98, 0.90, 0.78), rough=0.5, tile=1.6)
    material("Carton_Load", img=gen["load"], rough=0.85, tile=1.2)
    material("Wrap_Load", img=gen["wrap"], rough=0.3, tile=1.2)
    material("Carton", img=gen["cartons"], rough=0.85)
    material("Locker_Front", img=gen["locker"], rough=0.45, metal=0.3)
    material("Doors", img=gen["doors"], rough=0.5)
    material("Signs", img=gen["signs"], rough=0.6)
    material("Paint_Palette", img=gen["palette"], rough=0.6)
    material("Lamp_Emit", color=(1.0, 1.0, 1.0), rough=0.4, emit=((0.95, 0.98, 1.0), LAMP_EMIT))
    material("Emergency_Emit", color=(1.0, 1.0, 0.95), rough=0.4, emit=((1.0, 0.95, 0.85), EMERG_EMIT))
    material("Exit_Glow", emit_img=(gen["signs"], EXIT_EMIT))
    material("Screen_CRT", emit_img=(gen["feeds"], CRT_EMIT), rough=0.15)
    material("Reader_Glow", color=(0.1, 0.0, 0.0), rough=0.3, emit=((1.0, 0.10, 0.06), READER_EMIT))
    material("Freezer_Glow", color=(0.8, 0.9, 1.0), rough=0.3, emit=((0.62, 0.84, 1.0), FREEZER_EMIT))


# ---------------------------------------------------------------- geometry helpers (world space, identity transforms)
def cube(bm, gmin, gmax):
    a, b = B(gmin), B(gmax)
    c = (a + b) / 2
    s = Vector((abs(a.x - b.x), abs(a.y - b.y), abs(a.z - b.z)))
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((s.x, s.y, s.z, 1.0)))


def box(bm, x0, x1, y0, y1, z0, z1):
    cube(bm, (min(x0, x1), min(y0, y1), min(z0, z1)), (max(x0, x1), max(y0, y1), max(z0, z1)))


def cyl(bm, p0, p1, r0, r1=None, seg=12, cap=True):
    a, b = B(p0), B(p1)
    d = b - a
    q = d.to_track_quat("Z", "Y")
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                          matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())


def sphere(bm, p, r, seg=10, squash=1.0):
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(4, seg // 2 + 1), radius=r,
                              matrix=Matrix.Translation(B(p)) @ Matrix.Diagonal((1, 1, squash, 1)))


def quad(bm, p0, p1, p2, p3):
    return bm.faces.new([bm.verts.new(B(p)) for p in (p0, p1, p2, p3)])


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


def finish(name, bm, mat, coll=None, smooth=False, tile=None, keep_uv=False, recalc=True):
    for e in bm.edges:
        if smooth and len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) < math.radians(35)
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


# a box built face by face with its own UV rectangles: rects = {"px","nx","pz","nz","py","ny": (u0, v0, u1, v1)}; a face without a rect is left out
FACES = {
    "nz": lambda x0, x1, y0, y1, z0, z1: [(x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0)],
    "pz": lambda x0, x1, y0, y1, z0, z1: [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
    "px": lambda x0, x1, y0, y1, z0, z1: [(x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1)],
    "nx": lambda x0, x1, y0, y1, z0, z1: [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)],
    "py": lambda x0, x1, y0, y1, z0, z1: [(x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)],
    "ny": lambda x0, x1, y0, y1, z0, z1: [(x1, y0, z1), (x0, y0, z1), (x0, y0, z0), (x1, y0, z0)],
}


def uvquad(bm, pts, rect):
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    f = quad(bm, *pts)
    u0, v0, u1, v1 = rect
    for lp, (s, t) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = (u0 + (u1 - u0) * s, v0 + (v1 - v0) * t)
    return f


def uvbox(bm, g0, g1, rects):
    x0, y0, z0 = g0
    x1, y1, z1 = g1
    for k, r in rects.items():
        if r is not None:
            uvquad(bm, FACES[k](x0, x1, y0, y1, z0, z1), r)


def pt_uv(bm, faces_before, uv):
    """Every face added since `faces_before` takes the single UV point `uv` (a flat swatch)."""
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        if f not in faces_before:
            for lp in f.loops:
                lp[uvl].uv = uv


# the palette: 8 x 8 flat swatches in one small image (display values)
PAL = {
    "white": (0.86, 0.86, 0.84), "black": (0.05, 0.05, 0.05), "beige": (0.74, 0.70, 0.60), "beige_dark": (0.52, 0.49, 0.42),
    "grey": (0.45, 0.46, 0.46), "grey_dark": (0.22, 0.22, 0.23), "steel": (0.62, 0.63, 0.63), "chrome": (0.80, 0.80, 0.80),
    "red": (0.62, 0.08, 0.06), "blue": (0.12, 0.26, 0.52), "green": (0.10, 0.38, 0.18), "yellow": (0.90, 0.68, 0.06),
    "orange": (0.88, 0.40, 0.08), "cream": (0.90, 0.86, 0.74), "brown": (0.36, 0.22, 0.12), "mug_blue": (0.25, 0.45, 0.70),
    "pipe_red": (0.55, 0.08, 0.06), "pipe_blue": (0.10, 0.28, 0.55), "pipe_green": (0.16, 0.42, 0.22), "lagging": (0.72, 0.73, 0.74),
    "boiler": (0.82, 0.80, 0.74), "pump_blue": (0.08, 0.24, 0.50), "motor_grey": (0.40, 0.42, 0.44), "copper": (0.62, 0.36, 0.20),
    "paper": (0.90, 0.88, 0.82), "paper_yellow": (0.92, 0.84, 0.46), "cork": (0.62, 0.45, 0.28), "plastic_dark": (0.10, 0.10, 0.11),
    "fridge": (0.88, 0.88, 0.86), "microwave": (0.80, 0.80, 0.78), "glass_dark": (0.08, 0.10, 0.11), "vending": (0.55, 0.06, 0.06),
    "chair_blue": (0.14, 0.22, 0.38), "chair_seat": (0.24, 0.28, 0.32), "jacket": (0.18, 0.22, 0.20), "hivis": (0.82, 0.86, 0.10),
    "bin_green": (0.12, 0.30, 0.16), "tape": (0.70, 0.55, 0.30), "crt_beige": (0.70, 0.67, 0.58), "vcr_black": (0.08, 0.08, 0.09),
    "cable": (0.04, 0.04, 0.04), "keyboard": (0.62, 0.60, 0.54), "lamp_shade": (0.15, 0.18, 0.16), "ext_red": (0.70, 0.06, 0.04),
    "cage": (0.30, 0.30, 0.30), "bulb_off": (0.75, 0.72, 0.62), "label_white": (0.92, 0.92, 0.90), "rust": (0.42, 0.20, 0.10),
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
        pt_uv(s.bm, old, pal_uv(key))

    def done(s, name, coll=None, smooth=False):
        if not s.bm.faces:
            s.bm.free()
            return None
        return finish(name, s.bm, "Paint_Palette", coll, smooth=smooth, keep_uv=True)


def panel(name, mat, centre, normal, w, h, uv=(0, 0, 1, 1), bm=None, coll=None):
    """A flat quad facing `normal` ("+x", "-x", "+z", "-z"), w wide, h tall, its UV the rectangle uv, the picture upright."""
    r = Vector({"+x": (0, 0, -1), "-x": (0, 0, 1), "+z": (1, 0, 0), "-z": (-1, 0, 0)}[normal])
    up = Vector((0, 1, 0))
    c = Vector(centre)
    pts = [tuple(c - r * w / 2 - up * h / 2), tuple(c + r * w / 2 - up * h / 2), tuple(c + r * w / 2 + up * h / 2), tuple(c - r * w / 2 + up * h / 2)]
    own = bm is None
    bm = bm or bmesh.new()
    uvquad(bm, pts, uv)
    if own:
        return finish(name, bm, mat, coll, keep_uv=True, recalc=False)


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


# ---------------------------------------------------------------- generated pictures (numpy, own work, fixed seeds; display values)
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
    "<": ["00010", "00100", "01000", "10000", "01000", "00100", "00010"], "!": ["00100", "00100", "00100", "00100", "00100", "00000", "00100"],
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
        if wrap:
            g[-1, :] = g[0, :]
            g[:, -1] = g[:, 0]
        out += amp * rs(g, h, w)
        tot += amp
        amp *= 0.5
    return out / tot


def text_mask(text, h, w, fill=0.62, maxw=0.9):
    adv = 6
    units = max(1, len(text) * adv - 1)
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
    return np.clip((blur(m, k, 2) - 0.5) * 4 + 0.5, 0, 1)


def put_text(img, text, r0, r1, c0, c1, fg, fill=0.6, maxw=0.9):
    m = text_mask(text, r1 - r0, c1 - c0, fill, maxw)
    sub = img[r0:r1, c0:c1]
    img[r0:r1, c0:c1] = sub * (1 - m[..., None]) + np.array(fg) * m[..., None]


def block_pixels():
    """Painted concrete block, 0.4 x 0.2 m in running bond, struck joints; one repeat is 2 m (1024 px)."""
    S = 1024
    rng = np.random.default_rng(3)
    px = S / 2.0
    yy, xx = np.mgrid[0:S, 0:S] + 0.5
    row = np.floor(yy / (0.2 * px)).astype(int)
    off = (row % 2) * 0.2 * px
    bx, by = (xx + off) % (0.4 * px), yy % (0.2 * px)
    col = np.floor((xx + off) / (0.4 * px)).astype(int) % 5
    joint = np.minimum(np.minimum(bx, 0.4 * px - bx), np.minimum(by, 0.2 * px - by))
    j = np.clip(1 - (joint - 2.0) / 3.0, 0, 1)
    ids = (row % 10) * 5 + col
    per = rng.random(50)[ids]
    n = vnoise(S, S, rng, 6, 4, wrap=True)
    pores = (rng.random((S, S)) > 0.995).astype(np.float32)
    pores = blur(pores, 1, 1) * 6
    v = 0.88 + 0.05 * (per - 0.5) + 0.08 * (n - 0.5) - 0.25 * j - 0.15 * np.clip(pores, 0, 1)
    img = np.stack([v, v, v * 0.98], -1)
    return np.clip(img, 0, 1).astype(np.float32)


def soffit_pixels():
    """A painted concrete soffit: board-marked strips 0.3 m wide (one repeat 2.4 m), mottled."""
    S = 1024
    rng = np.random.default_rng(5)
    yy, xx = np.mgrid[0:S, 0:S] + 0.5
    strip = np.floor(xx / (S / 8)).astype(int)
    per = rng.random(8)[strip]
    edge = np.abs(((xx / (S / 8)) % 1) - 0.5) > 0.49
    n = vnoise(S, S, rng, 6, 4, wrap=True)
    v = 0.82 + 0.06 * (per - 0.5) + 0.12 * (n - 0.5) - 0.12 * edge
    return np.clip(np.stack([v, v, v * 0.98], -1), 0, 1).astype(np.float32)


def shutter_pixels():
    """Roller shutter slats: ten 0.1 m slats a repeat (1 m, 512 px), each rounded, with a dark joint; streaked."""
    S = 512
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:S, 0:S] + 0.5
    t = (yy / (S / 10)) % 1
    prof = 0.72 + 0.22 * np.sin(math.pi * t) - 0.35 * (t < 0.06)
    streak = vnoise(S, S, rng, 3, 64, wrap=True)
    n = vnoise(S, S, rng, 5, 4, wrap=True)
    v = prof * (0.9 + 0.12 * n) * (0.95 + 0.08 * streak)
    return np.clip(np.stack([v, v, v], -1), 0, 1).astype(np.float32)


def pine_pixels():
    """Pallet pine: pale, grain along u, knots; one repeat 1 m."""
    S = 512
    rng = np.random.default_rng(9)
    def wrapped(h, w):
        a = rng.random((h + 1, w + 1))
        a[-1, :], a[:, -1] = a[0, :], a[:, 0]
        return rs(a, S, S)
    g = wrapped(48, 4)
    fine = wrapped(160, 3)
    t = 0.6 * g + 0.4 * fine
    lo, hi = np.array([0.62, 0.46, 0.28]), np.array([0.84, 0.70, 0.50])
    img = lo + (hi - lo) * t[..., None]
    yy, xx = np.mgrid[0:S, 0:S]
    for _ in range(4):
        cy, cx = rng.integers(0, S, 2)
        d = np.sqrt(((yy - cy + S / 2) % S - S / 2) ** 2 * 4 + ((xx - cx + S / 2) % S - S / 2) ** 2)
        img *= (1 - 0.45 * np.clip(1 - d / 14, 0, 1))[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def frost_pixels():
    """Frost: a blue-white field of crystals and rime, one repeat 1.6 m."""
    S = 512
    rng = np.random.default_rng(11)
    n = vnoise(S, S, rng, 6, 4, wrap=True)
    spark = blur((rng.random((S, S)) > 0.985).astype(np.float32), 1, 1)
    v = 0.84 + 0.12 * (n - 0.5) + 0.25 * np.clip(spark * 4, 0, 1)
    img = np.stack([v * 0.94, v * 0.98, v], -1)
    return np.clip(img, 0, 1).astype(np.float32)


def panel_pixels():
    """Insulated freezer panel: white, a seam every 1.2 m (one repeat), faint ribs every 0.15 m."""
    S = 512
    rng = np.random.default_rng(13)
    yy, xx = np.mgrid[0:S, 0:S] + 0.5
    rib = 0.03 * np.cos(2 * math.pi * xx / (S / 8))
    seam = np.clip(1 - np.minimum(xx, S - xx) / 3.0, 0, 1)
    n = vnoise(S, S, rng, 5, 4, wrap=True)
    v = 0.9 + rib + 0.05 * (n - 0.5) - 0.45 * seam
    return np.clip(np.stack([v, v, v * 0.99], -1), 0, 1).astype(np.float32)


def plate_pixels():
    """Steel tread plate: raised lugs in alternating directions, one repeat 0.3 m (256 px)."""
    S = 256
    rng = np.random.default_rng(15)
    yy, xx = (np.mgrid[0:S, 0:S] + 0.5) / S * 4
    cx, cy = xx % 1 - 0.5, yy % 1 - 0.5
    alt = ((np.floor(xx) + np.floor(yy)) % 2) * 2 - 1
    a, b = (cx + alt * cy) / 1.414, (cx - alt * cy) / 1.414
    lug = np.clip(1 - (np.abs(a) / 0.32) ** 2 - (np.abs(b) / 0.07) ** 2, 0, 1)
    n = vnoise(S, S, rng, 5, 4, wrap=True)
    v = 0.62 + 0.25 * lug + 0.12 * (n - 0.5)
    return np.clip(np.stack([v, v, v], -1), 0, 1).astype(np.float32)


def hatch_pixels():
    """Hazard hatching: yellow and black at 45 degrees, worn; one repeat 0.6 m (256 px), four stripes."""
    S = 256
    rng = np.random.default_rng(17)
    yy, xx = np.mgrid[0:S, 0:S] + 0.5
    t = ((xx + yy) / (S / 2)) % 1
    yel = t < 0.5
    img = np.where(yel[..., None], np.array([0.92, 0.70, 0.06]), np.array([0.07, 0.07, 0.07]))
    n = vnoise(S, S, rng, 5, 4, wrap=True)
    wear = np.clip((n - 0.62) * 4, 0, 1)
    img = img * (1 - 0.4 * wear[..., None]) + np.array([0.45, 0.44, 0.42]) * 0.4 * wear[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def carton_face(h, w, rng, kind):
    """One carton side (h x w px): kraft or white board, its print, taped seams."""
    kraft = np.array([0.66, 0.50, 0.32])
    white = np.array([0.86, 0.85, 0.80])
    img = np.zeros((h, w, 3), np.float32)
    base = white if kind in ("white", "frozen", "white_top") else kraft
    img[:] = base
    n = vnoise(h, w, rng, 4, 4)
    img *= (0.92 + 0.12 * n)[..., None]
    if kind == "kraft_arrows":
        for cx in (0.25, 0.75):
            c0 = int(w * cx)
            img[int(h * 0.18):int(h * 0.42), c0 - 3:c0 + 3] = (0.08, 0.07, 0.06)
            for k in range(10):
                img[int(h * 0.18) + k, c0 - k:c0 + k + 1] = (0.08, 0.07, 0.06)
        img[int(h * 0.6):int(h * 0.82), int(w * 0.55):int(w * 0.9)] = (0.90, 0.89, 0.84)
        for k in range(4):
            img[int(h * 0.64) + k * 6:int(h * 0.64) + k * 6 + 2, int(w * 0.58):int(w * 0.86)] = (0.2, 0.2, 0.2)
    elif kind == "kraft_red":
        img[int(h * 0.30):int(h * 0.52)] = (0.62, 0.10, 0.08)
        put_text(img, "FARWAY", int(h * 0.30), int(h * 0.52), 0, w, (0.92, 0.88, 0.76), 0.7, 0.7)
    elif kind == "kraft_blue":
        img[int(h * 0.2):int(h * 0.7), int(w * 0.12):int(w * 0.42)] = (0.14, 0.24, 0.48)
        put_text(img, "TINS", int(h * 0.55), int(h * 0.8), int(w * 0.45), w, (0.12, 0.10, 0.08), 0.6, 0.8)
    elif kind == "white":
        img[int(h * 0.62):int(h * 0.8)] = (0.16, 0.46, 0.22)
        put_text(img, "FRESH", int(h * 0.2), int(h * 0.5), 0, w, (0.16, 0.36, 0.20), 0.6, 0.7)
    elif kind == "frozen":
        img[int(h * 0.58):int(h * 0.82)] = (0.14, 0.32, 0.62)
        put_text(img, "FROZEN", int(h * 0.18), int(h * 0.48), 0, w, (0.14, 0.30, 0.58), 0.6, 0.75)
    if kind.endswith("_top"):
        img[:, int(w * 0.44):int(w * 0.56)] = (0.72, 0.58, 0.36) if kind == "kraft_top" else (0.80, 0.78, 0.72)
        img[int(h * 0.49):int(h * 0.51)] *= 0.8
    else:
        img[:int(h * 0.08), int(w * 0.40):int(w * 0.60)] = (0.70, 0.56, 0.34) if base is kraft else (0.78, 0.76, 0.70)
    img[:2] *= 0.8
    img[-2:] *= 0.8
    img[:, :2] *= 0.8
    img[:, -2:] *= 0.8
    return img


CARTON_KINDS = ["kraft_arrows", "kraft_red", "kraft_blue", "kraft_plain", "white", "frozen", "kraft_top", "white_top"]


def cartons_pixels():
    """The carton atlas: 4 x 2 cells of 256 x 256 (CARTON_KINDS, row by row), in the top half; the rest is left plain kraft."""
    S = 1024
    rng = np.random.default_rng(19)
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.62, 0.47, 0.30)
    for i, k in enumerate(CARTON_KINDS):
        r, c = i // 4, i % 4
        img[r * 256:(r + 1) * 256, c * 256:(c + 1) * 256] = carton_face(256, 256, rng, k)
    return np.clip(img, 0, 1).astype(np.float32)


def carton_uv(kind):
    i = CARTON_KINDS.index(kind)
    r, c = i // 4, i % 4
    e = 3 / 1024
    return (c / 4 + e, 1 - (r + 1) / 4 + e, (c + 1) / 4 - e, 1 - r / 4 - e)


def load_pixels(wrap=False):
    """A pallet load's side: cartons 0.4 m wide and 0.3 m tall in a 1.2 m repeat (1024 px), stacked in bond, some with print; or the same under
    shrink-wrap (paler, glossy streaks)."""
    S = 1024
    rng = np.random.default_rng(23 if not wrap else 29)
    img = np.zeros((S, S, 3), np.float32)
    ch, cw = S // 4, S // 3
    for r in range(4):
        for c in range(4):
            off = (r % 2) * cw // 2
            kind = ["kraft_arrows", "kraft_red", "kraft_blue", "kraft_plain", "white"][int(rng.integers(0, 5))]
            face = carton_face(ch, cw, rng, kind)
            x0 = c * cw - off
            for k in range(cw):
                img[r * ch:(r + 1) * ch, (x0 + k) % S] = face[:, k]
    if wrap:
        n = vnoise(S, S, rng, 4, 4, wrap=True)
        streak = vnoise(S, S, rng, 2, 32, wrap=True)
        img = img * 0.55 + 0.38 + 0.08 * (n - 0.5)[..., None] + 0.08 * np.clip(streak - 0.6, 0, 1)[..., None] * 4
    return np.clip(img, 0, 1).astype(np.float32)


def locker_pixels():
    """One locker column (0.33 m x 1.9 m, 256 x 1024 px; repeats along the bank): two doors, louvres, a number plate, a hasp; grey steel."""
    h, w = 1024, 256
    rng = np.random.default_rng(31)
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (0.56, 0.58, 0.58)
    for d0, d1 in ((8, 508), (516, 1016)):
        img[d0:d1, 6:w - 6] = (0.60, 0.62, 0.62)
        img[d0:d0 + 3, 6:w - 6] = (0.72, 0.74, 0.74)
        img[d1 - 3:d1, 6:w - 6] = (0.36, 0.37, 0.37)
        for k in range(6):
            y = d0 + 30 + k * 14
            img[y:y + 6, 70:w - 70] = (0.18, 0.18, 0.19)
            img[y + 6:y + 8, 70:w - 70] = (0.74, 0.75, 0.75)
        img[d0 + 150:d0 + 180, 90:w - 90] = (0.85, 0.84, 0.80)
        img[d0 + 250:d0 + 300, w - 50:w - 30] = (0.25, 0.25, 0.26)
    img[:, :6] = img[:, w - 6:] = (0.22, 0.22, 0.23)
    img[0:8] = img[508:516] = img[1016:] = (0.22, 0.22, 0.23)
    n = vnoise(h, w, rng, 5, 4)
    img *= (0.9 + 0.14 * n)[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def door_pic(h, w, rng, kind):
    img = np.zeros((h, w, 3), np.float32)
    if kind == "staff":                                        # main_floor's staff doors: blue-grey, a steel kick plate, a small dark window, a push plate
        img[:] = srgb((0.30, 0.38, 0.44))
        img[int(h * 0.20):int(h * 0.38), int(w * 0.30):int(w * 0.70)] = (0.07, 0.08, 0.09)
        img[int(h * 0.48):int(h * 0.58), int(w * 0.70):int(w * 0.86)] = (0.75, 0.75, 0.74)
        img[int(h * 0.88):, :] = (0.66, 0.66, 0.65)
    elif kind == "stair":                                      # grey steel, wired glass, a push bar line, a kick plate
        img[:] = (0.52, 0.54, 0.54)
        r0, r1, c0, c1 = int(h * 0.12), int(h * 0.42), int(w * 0.25), int(w * 0.75)
        img[r0:r1, c0:c1] = (0.20, 0.24, 0.26)
        yy, xx = np.mgrid[r0:r1, c0:c1]
        img[r0:r1, c0:c1][((yy % 12) < 1) | ((xx % 12) < 1)] = (0.5, 0.5, 0.5)
        img[int(h * 0.5):int(h * 0.53), int(w * 0.1):int(w * 0.9)] = (0.75, 0.75, 0.74)
        img[int(h * 0.88):, :] = (0.66, 0.66, 0.65)
    elif kind == "room":                                       # pale grey laminate, a kick plate
        img[:] = (0.70, 0.70, 0.66)
        img[int(h * 0.88):, :] = (0.66, 0.66, 0.65)
    elif kind == "plant":                                      # dark grey steel, a louvred grille low down
        img[:] = (0.32, 0.33, 0.34)
        for k in range(8):
            y = int(h * 0.70) + k * 8
            img[y:y + 4, int(w * 0.2):int(w * 0.8)] = (0.10, 0.10, 0.11)
    elif kind == "freezer":                                    # white insulated, steel kick plate (the window is its own glowing part)
        img[:] = (0.88, 0.89, 0.88)
        img[int(h * 0.86):, :] = (0.66, 0.66, 0.65)
        img[int(h * 0.15):int(h * 0.45), int(w * 0.25):int(w * 0.75)] = (0.55, 0.56, 0.56)
    elif kind == "lift":                                       # a heavy steel gate: ribbed slats, a mesh band, hazard stripes at the foot
        yy, xx = np.mgrid[0:h, 0:w]
        img[:] = (0.34, 0.35, 0.36)
        img[(yy % 32) < 4] = (0.20, 0.20, 0.21)
        img[(yy % 32) == 4] = (0.52, 0.53, 0.53)
        r0, r1 = int(h * 0.18), int(h * 0.40)
        band = img[r0:r1]
        m = (((yy[r0:r1] + xx[r0:r1]) % 18) < 3) | (((yy[r0:r1] - xx[r0:r1]) % 18) < 3)
        band[:] = (0.05, 0.05, 0.06)
        band[m] = (0.46, 0.47, 0.47)
        stripe = (((xx + yy) // 40) % 2 == 0)
        foot = yy > h * 0.9
        img[foot & stripe] = (0.92, 0.70, 0.06)
        img[foot & ~stripe] = (0.07, 0.07, 0.07)
        img[:, :10] = img[:, -10:] = (0.24, 0.24, 0.25)
    n = vnoise(h, w, rng, 5, 4)
    img *= (0.9 + 0.14 * n)[..., None]
    img[:3] *= 0.7
    img[-3:] *= 0.7
    img[:, :3] *= 0.7
    img[:, -3:] *= 0.7
    return img


DOOR_CELLS = {"staff": (0, 512, 0, 256), "stair": (0, 512, 256, 512), "room": (0, 512, 512, 768), "plant": (0, 512, 768, 1024),
              "freezer": (512, 1024, 0, 256), "lift": (512, 1024, 256, 768)}
DOOR_SWATCH = {"steel": (512, 576, 768, 832), "rubber": (576, 640, 768, 832), "chrome": (640, 704, 768, 832), "frame": (704, 768, 768, 832)}


def doors_pixels():
    S = 1024
    rng = np.random.default_rng(37)
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.5, 0.5, 0.5)
    for k, (r0, r1, c0, c1) in DOOR_CELLS.items():
        img[r0:r1, c0:c1] = door_pic(r1 - r0, c1 - c0, rng, k)
    for k, col in (("steel", (0.62, 0.63, 0.63)), ("rubber", (0.05, 0.05, 0.05)), ("chrome", (0.80, 0.80, 0.80)), ("frame", (0.30, 0.30, 0.30))):
        r0, r1, c0, c1 = DOOR_SWATCH[k]
        img[r0:r1, c0:c1] = col
    return np.clip(img, 0, 1).astype(np.float32)


def rect_uv(r0, r1, c0, c1, S=1024, e=0.0):
    """UV rect for atlas rows r0..r1 (top down) and columns c0..c1."""
    return ((c0 + e) / S, 1 - (r1 - e) / S, (c1 - e) / S, 1 - (r0 + e) / S)


def swatch_uv(key):
    r0, r1, c0, c1 = DOOR_SWATCH[key]
    return ((c0 + c1) / 2 / 1024, 1 - (r0 + r1) / 2 / 1024)


RED, CREAM, YEL, BLK, WHT, NAVY, GRN = (0.50, 0.06, 0.06), (0.92, 0.88, 0.76), (0.92, 0.70, 0.06), (0.06, 0.06, 0.06), (0.92, 0.92, 0.90), (0.10, 0.16, 0.32), (0.04, 0.42, 0.16)
SIGN_SLOTS = [("SHOP FLOOR", RED, CREAM), ("LOADING DOCK 1", BLK, YEL), ("LOADING DOCK 2", BLK, YEL), ("LOADING DOCK 3", BLK, YEL),
              ("BREAK ROOM", NAVY, WHT), ("LOCKERS", NAVY, WHT), ("MANAGER", NAVY, WHT), ("STAIRS", NAVY, WHT),
              ("FREIGHT LIFT", YEL, BLK), ("KEYCARD ONLY", RED, WHT), ("NO SMOKING", WHT, RED), ("COLD STORE 1", (0.08, 0.26, 0.50), WHT),
              ("COLD STORE 2", (0.08, 0.26, 0.50), WHT), ("PLANT ROOM", NAVY, WHT), ("DANGER 415 V", YEL, BLK), ("BASEMENT", NAVY, WHT)]
SIGN_IDX = {t: i for i, (t, _, _) in enumerate(SIGN_SLOTS)}
NOTICE = (512, 832, 0, 512)
BREAKER = (512, 1024, 512, 768)
EXIT = (512, 640, 768, 1024)
READER = (640, 800, 768, 896)
CLOCK = (640, 768, 896, 1024)
CALENDAR = (800, 1024, 768, 1024)
TEMP = (832, 896, 0, 256)          # the freezers' readout: -22 C
LIFTPANEL = (832, 1024, 256, 384)  # the lift car's buttons
ROTA = (896, 1024, 0, 256)


def sign_uv(text):
    i = SIGN_IDX[text]
    r, c = i // 2, i % 2
    return rect_uv(r * 64, (r + 1) * 64, c * 512, (c + 1) * 512, e=1)


def signs_pixels():
    S = 1024
    rng = np.random.default_rng(41)
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.3, 0.3, 0.3)
    for i, (t, bg, fg) in enumerate(SIGN_SLOTS):
        r, c = i // 2, i % 2
        sub = np.zeros((64, 512, 3), np.float32)
        sub[:] = bg
        put_text(sub, t, 0, 64, 0, 512, fg, 0.56, 0.86)
        sub *= (0.92 + 0.1 * vnoise(64, 512, rng, 4, 6))[..., None]
        sub[:3] = sub[-3:] = sub[:, :3] = sub[:, -3:] = tuple(v * 0.6 for v in bg)
        img[r * 64:(r + 1) * 64, c * 512:(c + 1) * 512] = sub
    # the noticeboard: cork in an aluminium frame, pinned notices, the staff rota, a fire notice
    r0, r1, c0, c1 = NOTICE
    nb = np.zeros((r1 - r0, c1 - c0, 3), np.float32)
    nb[:] = (0.60, 0.43, 0.26)
    nb *= (0.85 + 0.25 * vnoise(r1 - r0, c1 - c0, rng, 6, 6))[..., None]
    for k in range(9):
        y, x = int(rng.integers(14, 200)), int(rng.integers(14, 420))
        hh, ww = int(rng.integers(60, 110)), int(rng.integers(60, 90))
        col = [(0.92, 0.90, 0.84), (0.94, 0.86, 0.48), (0.80, 0.88, 0.94), (0.94, 0.80, 0.82)][k % 4]
        nb[y:y + hh, x:x + ww] = col
        for ln in range(6):
            yl = y + 14 + ln * 12
            if yl < y + hh - 6:
                nb[yl:yl + 3, x + 8:x + ww - int(rng.integers(8, 30))] = (0.35, 0.35, 0.38)
        nb[y + 3:y + 9, x + ww // 2 - 3:x + ww // 2 + 3] = [(0.8, 0.1, 0.1), (0.1, 0.3, 0.8), (0.1, 0.6, 0.2)][k % 3]
    put_text(nb, "STAFF NOTICES", 4, 34, 120, 400, (0.1, 0.1, 0.1), 0.7, 0.9)
    nb[:6] = nb[-6:] = nb[:, :6] = nb[:, -6:] = (0.70, 0.70, 0.70)
    img[r0:r1, c0:c1] = nb
    # the staff rota (a grid) and the freezer readout
    r0, r1, c0, c1 = ROTA
    img[r0:r1, c0:c1] = (0.94, 0.93, 0.90)
    for k in range(1, 8):
        img[r0 + k * 16:r0 + k * 16 + 1, c0:c1] = (0.3, 0.3, 0.3)
        img[r0:r1, c0 + k * 32:c0 + k * 32 + 1] = (0.3, 0.3, 0.3)
    r0, r1, c0, c1 = TEMP
    img[r0:r1, c0:c1] = (0.02, 0.06, 0.10)
    put_text(img, "-22 C", r0, r1, c0, c1, (0.55, 0.85, 1.0), 0.6, 0.8)
    # the breaker board: grey steel, four columns of black breakers with white labels, a red main switch
    r0, r1, c0, c1 = BREAKER
    bb = np.zeros((r1 - r0, c1 - c0, 3), np.float32)
    bb[:] = (0.56, 0.58, 0.58)
    for col in range(4):
        for row in range(12):
            y, x = 60 + row * 34, 20 + col * 58
            bb[y:y + 26, x:x + 22] = (0.08, 0.08, 0.08)
            bb[y + 8:y + 18, x + 6:x + 16] = (0.20, 0.20, 0.20) if rng.random() < 0.85 else (0.75, 0.12, 0.08)
            bb[y:y + 26, x + 26:x + 50] = (0.90, 0.90, 0.88)
    bb[4:50, 70:186] = (0.72, 0.10, 0.08)
    put_text(bb, "MAIN", 10, 44, 70, 186, (0.95, 0.95, 0.95), 0.6, 0.8)
    bb *= (0.9 + 0.14 * vnoise(r1 - r0, c1 - c0, rng, 5, 4))[..., None]
    img[r0:r1, c0:c1] = bb
    # the exit sign (a running man and EXIT, white on green: it glows)
    r0, r1, c0, c1 = EXIT
    ex = np.zeros((r1 - r0, c1 - c0, 3), np.float32)
    ex[:] = (0.04, 0.55, 0.20)
    put_text(ex, "EXIT >", 8, 120, 10, 250, (0.95, 0.98, 0.95), 0.62, 0.9)
    img[r0:r1, c0:c1] = ex
    # the keycard reader's face: black, a card outline and an arrow, ACCESS
    r0, r1, c0, c1 = READER
    rd = np.zeros((r1 - r0, c1 - c0, 3), np.float32)
    rd[:] = (0.06, 0.06, 0.07)
    rd[20:24, 30:98] = rd[96:100, 30:98] = (0.75, 0.75, 0.75)
    rd[20:100, 30:34] = rd[20:100, 94:98] = (0.75, 0.75, 0.75)
    rd[40:60, 40:64] = (0.80, 0.66, 0.20)
    put_text(rd, "ACCESS", 110, 150, 6, 122, (0.85, 0.85, 0.85), 0.6, 0.9)
    img[r0:r1, c0:c1] = rd
    # a wall clock at ten to four, and a calendar left on last month
    r0, r1, c0, c1 = CLOCK
    yy, xx = (np.mgrid[0:128, 0:128] + 0.5 - 64) / 64
    rr = np.sqrt(xx ** 2 + yy ** 2)
    ck = np.zeros((128, 128, 3), np.float32)
    ck[:] = (0.12, 0.12, 0.12)
    ck[rr < 0.94] = (0.94, 0.94, 0.92)
    ang = np.arctan2(xx, -yy)
    ck[(rr > 0.76) & (rr < 0.88) & (np.abs(((ang / (2 * math.pi) * 12) % 1) - 0.5) > 0.46)] = (0.1, 0.1, 0.1)
    for a, ln, wd in ((3.83 / 12 * 2 * math.pi, 0.5, 0.06), (0.83 * 2 * math.pi, 0.75, 0.04)):
        ux, uy = math.sin(a), -math.cos(a)
        t = xx * ux + yy * uy
        ck[(t > -0.08) & (t < ln) & (np.abs(xx * uy - yy * ux) < wd)] = (0.05, 0.05, 0.05)
    img[r0:r1, c0:c1] = ck
    r0, r1, c0, c1 = CALENDAR
    img[r0:r1, c0:c1] = (0.94, 0.93, 0.90)
    img[r0:r0 + 90, c0 + 8:c1 - 8] = (0.42, 0.56, 0.66)
    for k in range(5):
        for j in range(7):
            y, x = r0 + 100 + k * 22, c0 + 12 + j * 34
            img[y:y + 16, x:x + 28] = (0.80, 0.80, 0.78)
    # the lift car's button panel: brushed steel, two big buttons, an alarm button, a key switch
    r0, r1, c0, c1 = LIFTPANEL
    lp = np.zeros((r1 - r0, c1 - c0, 3), np.float32)
    lp[:] = (0.62, 0.63, 0.63)
    lp *= (0.9 + 0.1 * vnoise(r1 - r0, c1 - c0, rng, 3, 32))[..., None]
    for k, col in enumerate(((0.85, 0.85, 0.80), (0.85, 0.85, 0.80), (0.85, 0.65, 0.10))):
        y = 30 + k * 46
        lp[y:y + 30, 44:84] = col
    lp[170:186, 56:72] = (0.15, 0.15, 0.15)
    img[r0:r1, c0:c1] = lp
    return np.clip(img, 0, 1).astype(np.float32)


FEED_ROWS, FEED_COLS = 6, 4


def feeds_pixels():
    """The camera monitors' pictures: 4 x 6 feeds (256 x 170 px each, 4:3), grey-green and grainy, each a room drawn in perspective, CAM nn and a
    time; two show NO SIGNAL on blue and one is snow. Own work."""
    S = 1024
    rng = np.random.default_rng(43)
    img = np.zeros((S, S, 3), np.float32)
    ch = S // FEED_ROWS
    cw = S // FEED_COLS
    k = 0
    for r in range(FEED_ROWS):
        for c in range(FEED_COLS):
            k += 1
            f = np.zeros((ch, cw), np.float32)
            yy, xx = np.mgrid[0:ch, 0:cw] / np.array([ch, cw])[:, None, None]
            if k in (7, 18):
                rgb = np.zeros((ch, cw, 3), np.float32)
                rgb[:] = (0.06, 0.12, 0.62)
                put_text(rgb, "NO SIGNAL", ch // 3, 2 * ch // 3, 0, cw, (0.85, 0.85, 0.9), 0.5, 0.8)
                img[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw] = rgb
                continue
            if k == 13:
                f = rng.random((ch, cw)).astype(np.float32) * 0.8
            else:
                vx, vy = 0.5 + rng.uniform(-0.2, 0.2), 0.42 + rng.uniform(-0.08, 0.08)
                f[:] = 0.30
                floor = yy > vy + (np.abs(xx - vx)) * 0.2
                f[floor] = 0.45 - 0.2 * (1 - yy[floor])
                for j in range(int(rng.integers(2, 5))):
                    side = -1 if j % 2 else 1
                    x0 = vx + side * rng.uniform(0.12, 0.4)
                    w = rng.uniform(0.04, 0.12)
                    lo = min(x0, x0 + side * w)
                    hi = max(x0, x0 + side * w)
                    top = vy - rng.uniform(0.1, 0.35)
                    m = (xx > lo) & (xx < hi) & (yy > top) & (yy < vy + 0.3)
                    f[m] = 0.18 + 0.05 * j
                lamp = np.exp(-(((xx - vx) * 5) ** 2 + ((yy - 0.1) * 12) ** 2))
                f += 0.35 * lamp
                f += 0.06 * (rng.random((ch, cw)) - 0.5)
            f *= 1 - 0.35 * (((xx - 0.5) * 2) ** 2 + ((yy - 0.5) * 2) ** 2) / 2
            f[::3] *= 0.75
            rgb = np.stack([f * 0.78, f * 1.0, f * 0.84], -1)
            put_text(rgb, f"CAM {k:02d}", 4, 26, 4, 110, (0.9, 0.95, 0.9), 0.7, 0.95)
            put_text(rgb, "03:1" + str(k % 10), ch - 26, ch - 4, cw - 110, cw - 4, (0.9, 0.95, 0.9), 0.7, 0.95)
            img[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw] = rgb
    return np.clip(img, 0, 1).astype(np.float32)


def feed_uv(i):
    i %= FEED_ROWS * FEED_COLS
    r, c = i // FEED_COLS, i % FEED_COLS
    ch, cw = 1024 // FEED_ROWS, 1024 // FEED_COLS
    return rect_uv(r * ch + 4, (r + 1) * ch - 4, c * cw + 4, (c + 1) * cw - 4)


def palette_pixels():
    img = np.zeros((128, 128, 3), np.float32)
    for i, k in enumerate(PAL_KEYS):
        r, c = i // 8, i % 8
        img[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16] = PAL[k]
    return img


def stage_work():
    d = Path(arg("--work", str(ROOT / f"work/{SCENE}")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def mk_image(name, arr, srgb_=True):
    """A packed image from a float array (rows top to bottom), written as a PNG first (a generated image forgets its pixels when the file is saved)."""
    h, w = arr.shape[:2]
    im = bpy.data.images.new(name + "_gen", w, h, alpha=False)
    im.colorspace_settings.name = "sRGB" if srgb_ else "Non-Color"
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
    out.colorspace_settings.name = "sRGB" if srgb_ else "Non-Color"
    out.pack()
    for ref in [out] + list(out.packed_files):
        attr = "filepath_raw" if ref is out else "filepath"
        setattr(ref, attr, "_" * 1000)
        setattr(ref, attr, f"//generated/{name}.png")
    return out


def make_generated():
    return {"block": mk_image("Block_Paint", block_pixels()), "soffit": mk_image("Soffit", soffit_pixels()), "shutter": mk_image("Shutter_Slats", shutter_pixels()),
            "pine": mk_image("Pallet_Pine", pine_pixels()), "frost": mk_image("Frost", frost_pixels()), "panel": mk_image("Freezer_Panel", panel_pixels()),
            "plate": mk_image("Tread_Plate", plate_pixels()), "hatch": mk_image("Hazard_Hatch", hatch_pixels()), "cartons": mk_image("Cartons", cartons_pixels()),
            "load": mk_image("Carton_Load", load_pixels()), "wrap": mk_image("Wrap_Load", load_pixels(True)), "locker": mk_image("Locker_Front", locker_pixels()),
            "doors": mk_image("Back_Doors", doors_pixels()), "signs": mk_image("Back_Signs", signs_pixels()), "feeds": mk_image("Camera_Feeds", feeds_pixels()),
            "palette": mk_image("Back_Palette", palette_pixels())}


# ---------------------------------------------------------------- lights (declared by the dressing; made in add_lights)
LIGHTS = []        # dict(sets, kind, pos, w, color, size, aim, cone, shape)
COOL = (0.92, 0.96, 1.0)
WARM = (1.0, 0.82, 0.62)
EMERG = (1.0, 0.94, 0.84)
ICE = (0.62, 0.82, 1.0)


def light(sets, kind, pos, w, color=COOL, size=0.1, aim=(0, -1, 0), cone=120.0, shape=None):
    LIGHTS.append({"sets": sets, "kind": kind, "pos": tuple(pos), "w": w, "color": color, "size": size, "aim": aim, "cone": cone, "shape": shape})


# ---------------------------------------------------------------- the shell: floors, walls, ceilings (from the colliders)
def wall_bands(name, b, mats=("Wall_Lower", "Wall_Band", "Wall_Block"), cuts=(LOW, BAND)):
    """A wall collider's art twin, cut into the mid-grey dado, the yellow band and the light block above (one object per band)."""
    y0, y1 = b["min"][1], b["max"][1]
    ys = [y0] + [c for c in cuts if y0 < c < y1] + [y1]
    for ya, yb in zip(ys, ys[1:]):
        k = sum(1 for c in cuts if c <= ya + 1e-6)
        mat = mats[min(k, len(mats) - 1)]
        part(f"Wall_{name}_{mat.split('_')[1]}", mat, lambda bm, ya=ya, yb=yb: cube(bm, (b["min"][0], ya, b["min"][2]), (b["max"][0], yb, b["max"][2])))


def plain(name, b, mat):
    part(name, mat, lambda bm: cube(bm, b["min"], b["max"]))


def floor_cells(cells, hole=None):
    """The floor slab's top in cells [(x0, x1, z0, z1, mat)], each a thin box whose top is at y 0 (cull keeps only the tops)."""
    by = {}
    for x0, x1, z0, z1, m in cells:
        by.setdefault(m, []).append((x0, x1, z0, z1))
    for m, cs in by.items():
        def bld(bm, cs=cs):
            for x0, x1, z0, z1 in cs:
                box(bm, x0, x1, -G.SLAB, 0.0, z0, z1)
        part(f"Floor_{m.split('_')[1]}", m, bld)


def grid_cells(xs, zs, pick, skip=None):
    out = []
    for xa, xb in zip(xs, xs[1:]):
        for za, zb in zip(zs, zs[1:]):
            xm, zm = (xa + xb) / 2, (za + zb) / 2
            if skip and skip(xm, zm):
                continue
            out.append((xa, xb, za, zb, pick(xm, zm)))
    return out


def hline(p, x0, x1, z, w=0.1):
    """A painted floor line along x (flat, 3 mm)."""
    p.append((min(x0, x1), max(x0, x1), z - w / 2, z + w / 2))


def vline(p, x, z0, z1, w=0.1):
    """A painted floor line along z."""
    p.append((x - w / 2, x + w / 2, min(z0, z1), max(z0, z1)))


def lines_part(name, rects, mat="Floor_Paint", y=0.003):
    part(name, mat, lambda bm: [box(bm, a, b, 0.0, y, c, d) for a, b, c, d in rects])


# ---------------------------------------------------------------- fittings shared by both scenes
def batten(p, pos, length=1.5, along="x", drop=0.5, top=None, w=40.0, sets="day"):
    """A twin-tube fluorescent batten hanging on two chains: white housing, the tubes' diffuser (Lamp_Emit) underneath, an area light."""
    x, y, z = pos
    hl = length / 2
    dx, dz = (hl, 0.06) if along == "x" else (0.06, hl)
    p["housing"].append(((x - dx, y, z - dz), (x + dx, y + 0.08, z + dz)))
    p["tube"].append(((x - dx + 0.03, y - 0.012, z - dz + 0.012), (x + dx - 0.03, y, z + dz - 0.012)))
    if top is not None and top > y + 0.1:
        for s in (-0.6, 0.6):
            cx, cz = (x + s * hl, z) if along == "x" else (x, z + s * hl)
            p["chain"].append(((cx, y + 0.08, cz), (cx, top, cz)))
    light(sets, "AREA", (x, y - 0.02, z), w, COOL, shape=(2 * dx - 0.06, 2 * dz - 0.02) if along == "x" else (2 * dx - 0.02, 2 * dz - 0.06))


def troffer(p, x, y, z, w=60.0, sets="day", along="z"):
    """A recessed 0.6 x 1.2 m troffer in a lay-in ceiling (its face 5 mm below the tiles)."""
    hx, hz = (0.3, 0.6) if along == "z" else (0.6, 0.3)
    p["housing"].append(((x - hx, y - 0.01, z - hz), (x + hx, y, z + hz)))
    p["tube"].append(((x - hx + 0.04, y - 0.014, z - hz + 0.04), (x + hx - 0.04, y - 0.01, z + hz - 0.04)))
    light(sets, "AREA", (x, y - 0.03, z), w, COOL, shape=(2 * hx - 0.08, 2 * hz - 0.08))


def bulb(p, x, y, z, top, w=35.0):
    """A bare bulb on its flex in a wire cage (the basement's)."""
    p["cable"].append(((x, y + 0.12, z), (x, top, z)))
    p["holder"].append((x, y + 0.06, z))
    p["bulb"].append((x, y, z))
    p["cage"].append((x, y, z))
    light("day", "POINT", (x, y - 0.14, z), w, WARM, size=0.05)                 # under the cage (inside the glass it would be shut in)


def make_fittings(p, tag):
    part(f"Light_Housing_{tag}", "Paint_Palette", lambda bm: _pal_boxes(bm, p["housing"], "white"), keep_uv=True)
    part(f"Light_Tubes_{tag}", "Lamp_Emit", lambda bm: [cube(bm, a, b) for a, b in p["tube"]])
    if p["chain"]:
        part(f"Light_Chains_{tag}", "Steel_Dark", lambda bm: [cyl(bm, a, b, 0.006, seg=4) for a, b in p["chain"]])
    if p["cable"]:
        part(f"Bulb_Flex_{tag}", "Steel_Dark", lambda bm: [cyl(bm, a, b, 0.005, seg=4) for a, b in p["cable"]])
        part(f"Bulb_Holder_{tag}", "Steel_Dark", lambda bm: [cyl(bm, (x, y - 0.03, z), (x, y + 0.06, z), 0.018, seg=8) for x, y, z in p["holder"]])
        part(f"Bulb_Glow_{tag}", "Lamp_Emit", lambda bm: [sphere(bm, (x, y - 0.02, z), 0.035, 10) for x, y, z in p["bulb"]], smooth=True)
        def cage(bm):
            for x, y, z in p["cage"]:
                for k in range(4):
                    a = k * math.pi / 4
                    dx, dz = 0.07 * math.cos(a), 0.07 * math.sin(a)
                    cyl(bm, (x - dx, y - 0.1, z - dz), (x + dx, y - 0.1, z + dz), 0.003, seg=3)
                cyl(bm, (x, y - 0.1, z), (x, y + 0.04, z), 0.072, seg=10, cap=False)
        part(f"Bulb_Cage_{tag}", "Steel_Dark", cage)


def _pal_boxes(bm, boxes, key):
    old = set(bm.faces)
    for a, b in boxes:
        cube(bm, a, b)
    pt_uv(bm, old, pal_uv(key))


def fittings():
    return {"housing": [], "tube": [], "chain": [], "cable": [], "holder": [], "bulb": [], "cage": []}


EMERG_UNITS = []      # (pos on the wall, normal "+x".. , aim) -> twin-head emergency lights (night only)
EXITS = []            # (centre, normal) EXIT signs


def emergency(pos, normal, aim_down=0.55, w=60.0):
    """A twin-spot emergency light on a wall: a small box, two round heads (Emergency_Emit), and two spot lights (night only)."""
    EMERG_UNITS.append((pos, normal))
    n = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}[normal]
    r = {"+x": (0, 0, -1), "-x": (0, 0, 1), "+z": (1, 0, 0), "-z": (-1, 0, 0)}[normal]
    for s in (-1, 1):
        aim = (n[0] * 0.8 + r[0] * s * 0.6, -aim_down * 1.4, n[2] * 0.8 + r[2] * s * 0.6)
        al = math.sqrt(sum(v * v for v in aim))
        hp = tuple(c + 0.08 * a / al for c, a in zip((pos[0] + n[0] * 0.12 + r[0] * s * 0.13, pos[1] - 0.02, pos[2] + n[2] * 0.12 + r[2] * s * 0.13), aim))  # just out of the head
        light("night", "SPOT", hp, w, EMERG, size=0.03, aim=aim, cone=110.0)


def make_emergency():
    def body(bm):
        for (x, y, z), n in EMERG_UNITS:
            if n in ("+x", "-x"):
                s = 1 if n == "+x" else -1
                box(bm, x, x + s * 0.1, y - 0.07, y + 0.07, z - 0.18, z + 0.18)
            else:
                s = 1 if n == "+z" else -1
                box(bm, x - 0.18, x + 0.18, y - 0.07, y + 0.07, z, z + s * 0.1)
    part("Emergency_Box", "Paint_Palette", lambda bm: (lambda old: (body(bm), pt_uv(bm, old, pal_uv("white"))))(set(bm.faces)), keep_uv=True)

    def heads(bm):
        for (x, y, z), n in EMERG_UNITS:
            nv = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}[n]
            rv = {"+x": (0, 0, -1), "-x": (0, 0, 1), "+z": (1, 0, 0), "-z": (-1, 0, 0)}[n]
            for s in (-1, 1):
                c = (x + nv[0] * 0.12 + rv[0] * s * 0.13, y - 0.02, z + nv[2] * 0.12 + rv[2] * s * 0.13)
                sphere(bm, c, 0.045, 8)
    part("Emergency_Heads", "Emergency_Emit", heads, smooth=True)


def exit_sign(centre, normal, w=0.36, h=0.16):
    """A maintained EXIT sign: a white box with the glowing face (Exit_Glow, the signs atlas), and a faint green light (both sets)."""
    EXITS.append((centre, normal))
    n = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}[normal]
    light("both", "POINT", (centre[0] + n[0] * 0.3, centre[1] - 0.1, centre[2] + n[2] * 0.3), 1.2, (0.3, 1.0, 0.45), size=0.1)


def make_exits():
    if not EXITS:
        return
    bm = bmesh.new()
    old = set(bm.faces)
    for (x, y, z), n in EXITS:
        if n in ("+x", "-x"):
            s = 1 if n == "+x" else -1
            box(bm, x, x + s * 0.06, y - 0.1, y + 0.1, z - 0.2, z + 0.2)
        else:
            s = 1 if n == "+z" else -1
            box(bm, x - 0.2, x + 0.2, y - 0.1, y + 0.1, z, z + s * 0.06)
    pt_uv(bm, old, pal_uv("white"))
    finish("Exit_Box", bm, "Paint_Palette", keep_uv=True)
    bm = bmesh.new()
    for (x, y, z), n in EXITS:
        nv = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}[n]
        c = (x + nv[0] * 0.062, y, z + nv[2] * 0.062)
        panel(None, None, c, n, 0.36, 0.15, rect_uv(*EXIT, e=2), bm=bm)
    finish("Exit_Face", bm, "Exit_Glow", keep_uv=True, recalc=False)


def wall_sign(bm, text, centre, normal, w, h):
    panel(None, None, centre, normal, w, h, sign_uv(text), bm=bm)


def cam_mounts():
    """Each SecCam_: a ceiling rod and a plate (the page draws the camera's head at the empty)."""
    ceil_at = {}
    for c in [e for e in GB.empties if e["name"].startswith("SecCam_")]:
        x, y, z = c["pos"]
        top = (3.0 if (BOH and z > G.ROOMS_Z) else H) if BOH else H
        ceil_at[c["name"]] = (x, y, z, top)
    p = Painter()
    for x, y, z, top in ceil_at.values():
        p.add("grey_dark", cyl, (x, y + 0.1, z), (x, top, z), 0.02, seg=6)
        p.add("grey_dark", box, x - 0.08, x + 0.08, top - 0.02, top, z - 0.08, z + 0.08)
    p.done("Cam_Mounts")


# ---------------------------------------------------------------- pallets, loads and cartons
RNG = np.random.default_rng(101)


def pallet(bm, x0, x1, z0, z1, y0=0.0, along="x"):
    """A pallet (0.144 m tall), kept to five boxes (the lightmap packs one island a face, and the racks hold a hundred pallets): the top deck,
    three bearers under it with the fork openings between them, and the bottom boards' front edge."""
    box(bm, x0, x1, y0 + 0.1, y0 + 0.144, z0, z1)
    if along == "x":
        for zc in (z0 + 0.05, (z0 + z1) / 2, z1 - 0.05):
            box(bm, x0, x1, y0, y0 + 0.1, zc - 0.05, zc + 0.05)
    else:
        for xc in (x0 + 0.05, (x0 + x1) / 2, x1 - 0.05):
            box(bm, xc - 0.05, xc + 0.05, y0, y0 + 0.1, z0, z1)


def load(loads, wraps, x0, x1, z0, z1, y0, top, rng=RNG, wrap_p=0.25):
    """A pallet load from y0 to `top`: one block (box-mapped carton faces), now and then a short top layer, sometimes shrink-wrapped."""
    if top - y0 < 0.25:
        return
    inset = 0.02
    full = y0 + max(0.3, math.floor((top - y0) / 0.3) * 0.3)
    full = min(full, top)
    tgt = wraps if rng.random() < wrap_p else loads
    tgt.append(((x0 + inset, y0, z0 + inset), (x1 - inset, full, z1 - inset)))
    if top - full > 0.12 and rng.random() < 0.7:
        fx = rng.uniform(0.4, 0.8)
        tgt.append(((x0 + inset, full, z0 + inset), (x0 + inset + (x1 - x0 - 2 * inset) * fx, min(top, full + 0.3), z1 - inset)))


def carton(bm, x0, x1, y0, y1, z0, z1, kind=None, top=True):
    kind = kind or ["kraft_arrows", "kraft_red", "kraft_blue", "kraft_plain"][int(RNG.integers(0, 4))]
    side = carton_uv(kind)
    tp = carton_uv("white_top" if kind in ("white", "frozen") else "kraft_top")
    uvbox(bm, (x0, y0, z0), (x1, y1, z1), {"px": side, "nx": side, "pz": side, "nz": side, "py": tp if top else None})


def make_loads(tag, pallets, loads, wraps, cartons=None):
    if pallets:
        part(f"Pallets_{tag}", "Pallet_Wood", lambda bm: [pallet(bm, *p) for p in pallets])
    if loads:
        part(f"Loads_{tag}", "Carton_Load", lambda bm: [cube(bm, a, b) for a, b in loads])
    if wraps:
        part(f"Wraps_{tag}", "Wrap_Load", lambda bm: [cube(bm, a, b) for a, b in wraps])
    if cartons:
        part(f"Cartons_{tag}", "Carton", lambda bm: [carton(bm, *c) for c in cartons], keep_uv=True, recalc=False)


def pallet_stack(name, b, rng, along="x", empty_stack=False):
    """A greybox Pallet collider: a pallet and its load to the collider's height (or a stack of empty pallets)."""
    x0, y0, z0 = b["min"]
    x1, y1, z1 = b["max"]
    pal, loads, wraps = [], [], []
    if empty_stack or y1 - y0 < 0.3 or (y1 - y0 < 0.7 and rng.random() < 0.6):
        n = max(1, int(round((y1 - y0) / 0.144)))
        for k in range(n):
            pal.append((x0 + 0.01, x1 - 0.01, z0 + 0.01, z1 - 0.01, k * (y1 - y0) / n, along))
    else:
        pal.append((x0 + 0.01, x1 - 0.01, z0 + 0.01, z1 - 0.01, 0.0, along))
        load(loads, wraps, x0, x1, z0, z1, 0.144, y1, rng, 0.35)
        if loads or wraps:
            lst = loads or wraps
            a, bb = lst[0]
            lst[0] = ((a[0], a[1], a[2]), (bb[0], max(bb[1], y1 - 0.01) if len(lst) == 1 else bb[1], bb[2]))
    return pal, loads, wraps


# ---------------------------------------------------------------- door leaves
def leaf_mesh(w, h, kind, thick=0.05):
    """A door leaf in its own frame: local x from the hinge along the leaf (0..w), y across, z up (0..h). Both faces show the atlas picture."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    t = thick / 2
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, 0, h / 2)) @ Matrix.Diagonal((w, 2 * t, h, 1)))
    u0, v0, u1, v1 = rect_uv(*DOOR_CELLS[kind], e=2)
    edge = swatch_uv("frame")
    for f in bm.faces:
        f.normal_update()
        if abs(f.normal.y) > 0.9:
            for lp in f.loops:
                x, z = lp.vert.co.x, lp.vert.co.z
                s = x / w if f.normal.y < 0 else 1 - x / w
                lp[uvl].uv = (u0 + (u1 - u0) * s, v0 + (v1 - v0) * z / h)
        else:
            for lp in f.loops:
                lp[uvl].uv = edge
    old = set(bm.faces)
    if kind in ("room", "plant", "stair"):                     # a lever handle each side
        for sg in (-1, 1):
            bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w - 0.08, sg * (t + 0.03), 1.0)) @ Matrix.Diagonal((0.03, 0.06, 0.03, 1)))
            bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w - 0.16, sg * (t + 0.06), 1.0)) @ Matrix.Diagonal((0.16, 0.02, 0.022, 1)))
    if kind == "freezer":                                      # chunky chrome hinges and a big latch on the outside (local -y faces the corridor)
        for zc in (0.35, 1.8):
            bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0.08, -(t + 0.03), zc)) @ Matrix.Diagonal((0.2, 0.06, 0.12, 1)))
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w - 0.12, -(t + 0.04), 1.05)) @ Matrix.Diagonal((0.08, 0.08, 0.3, 1)))
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w - 0.2, -(t + 0.07), 1.05)) @ Matrix.Diagonal((0.18, 0.03, 0.04, 1)))
    if kind == "lift":                                         # the gate's handle bar
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w - 0.2, -(t + 0.05), 1.1)) @ Matrix.Diagonal((0.05, 0.05, 0.9, 1)))
    for f in bm.faces:
        if f not in old:
            for lp in f.loops:
                lp[uvl].uv = swatch_uv("chrome")
    return bm


def build_door_leaves():
    """Each leaf its own object (the Doors collection), origin at the hinge, with the greybox door's properties, so export_scene.py writes the
    same `doors` and the page can swing them by name. The freezer doors carry a second part: their glowing window (Freezer_Glow)."""
    for d in GB.doors:
        p = d["props"]
        w, h = p["width"], p["height"]
        n = d["name"]
        kind = ("staff" if "staff" in n else "lift" if "freight" in n else "freezer" if "freezer" in n else "plant" if "plant" in n
                else "stair" if ("stairs" in n or n == "DoorLeaf_back_of_house") else "room")
        bm = leaf_mesh(w, h, kind, thick=0.1 if kind == "freezer" else 0.07 if kind == "lift" else 0.05)
        for f in bm.faces:
            f.smooth = False
        me = bpy.data.meshes.new(n)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(MATS["Doors"])
        if kind == "freezer":                                  # the window: a glowing pane on both faces
            me.materials.append(MATS["Freezer_Glow"])
            bm = bmesh.new()
            bm.from_mesh(me)
            uvl = bm.loops.layers.uv["UVMap"]
            for sg in (-1, 1):
                r = bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, sg * 0.051, 1.55)) @ Matrix.Diagonal((0.42, 0.004, 0.5, 1)))
                for v in r["verts"]:
                    for f in v.link_faces:
                        f.material_index = 1
                        for lp in f.loops:
                            lp[uvl].uv = (0.5, 0.5)
            bm.to_mesh(me)
            bm.free()
        ob = bpy.data.objects.new(n, me)
        ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
        for k, v in p.items():
            ob[k] = v
        DOORS_C.objects.link(ob)


def door_frame(bm, axis, c, a0, a1, h, face, y0=0.0, wdt=0.06, d=0.03):
    """A door's frame on the wall face: jambs and a head, `d` proud of the face. axis 'x': the wall runs along x at z = c (face +1/-1 its side)."""
    if axis == "x":
        zs = (c, c + face * d)
        box(bm, a0 - wdt, a0, y0, y0 + h + wdt, *zs)
        box(bm, a1, a1 + wdt, y0, y0 + h + wdt, *zs)
        box(bm, a0, a1, y0 + h, y0 + h + wdt, *zs)
    else:
        xs = (c, c + face * d)
        box(bm, *xs, y0, y0 + h + wdt, a0 - wdt, a0)
        box(bm, *xs, y0, y0 + h + wdt, a1, a1 + wdt)
        box(bm, *xs, y0 + h, y0 + h + wdt, a0, a1)


# ================================================================ back_of_house
def boh_shell():
    sw = (G.STAIR["x0"], G.STAIR["x1"], G.STAIR["top"] + 0.15, Z1)       # the stair well behind the rail: the floor is open there
    xs = [X0 - T, 20.1, 25.1, 32.1, G.STAIR["x0"], G.STAIR["x1"], X1 + T]
    zs = [Z0 - T, G.ROOMS_Z + 0.1, G.STAIR["top"] + 0.15, Z1 + T]

    def pick(xm, zm):
        return "Floor_Vinyl" if zm > G.ROOMS_Z + 0.1 and xm < 32.1 else "Floor_Concrete"
    floor_cells(grid_cells(xs, zs, pick, skip=lambda xm, zm: sw[0] < xm < sw[1] and zm > sw[2]))
    for b in COLS:
        n = b["name"]
        if n.startswith(("BOH_Wall_", "Rooms_Wall_N", "Rooms_Partition")):
            wall_bands(n, b)
        elif n.startswith("Lift_Wall_N"):
            wall_bands(n, b)
        elif n == "BOH_Ceiling":
            plain("Ceil_Soffit", b, "Ceiling_Soffit")
        elif n == "Rooms_Ceiling":
            plain("Ceil_Rooms", b, "Ceiling_Tile")
        elif n == "BOH_Floor":
            pass
    # the bulkhead over the staff rooms' front, from their 3 m ceiling to the hall's 4.5 m (art only, overhead)
    part("Wall_Bulkhead_Block", "Wall_Block", lambda bm: box(bm, X0, X1, 3.0, H, G.ROOMS_Z, G.ROOMS_Z + T))
    # the steel frame under the soffit: four beams across, a sprinkler main and its drops
    p = Painter()
    for x in (18.0, 24.0, 30.0, 36.0):
        p.add("grey_dark", box, x - 0.1, x + 0.1, H - 0.4, H, Z0, G.ROOMS_Z)
        p.add("grey_dark", box, x - 0.012, x + 0.012, H - 0.4, H, Z0, G.ROOMS_Z)
    for z in (-6.5, -2.8, 0.9, 5.1):
        p.add("pipe_red", cyl, (X0, H - 0.25, z + 0.9), (X1, H - 0.25, z + 0.9), 0.04, seg=8)
        for x in np.arange(14.0, 42.0, 3.0):
            p.add("pipe_red", cyl, (x, H - 0.25, z + 0.9), (x, H - 0.45, z + 0.9), 0.012, seg=5)
    p.add("lagging", box, X0 + 1.0, X1, H - 0.45, H - 0.15, G.ROOMS_Z - 0.6, G.ROOMS_Z - 0.2)          # a ventilation duct along the rooms' front
    p.done("Overhead_Steel")
    # floor lines: the walkway from the staff door, the edges of the forklift aisle, the racking's ends, boxes in front of the dock doors
    rects = []
    for zc in (-6.3 - 0.1, -4.7 + 0.1):
        hline(rects, X0 + 1.6, G.RACK_X[0] - 0.3, zc)
    vline(rects, G.RACK_X[0] - 0.3, -8.9, 3.4)
    vline(rects, G.RACK_X[1] + 0.3, -8.9, 3.4)
    hline(rects, X0 + 0.3, X1 - 3.4, 3.6)
    hline(rects, X0 + 0.3, X1 - 0.3, 6.6)
    for zd in (-6.5, -1.5, 3.5):
        hline(rects, X1 - 3.4, X1 - 2.3, zd - 1.5)
        hline(rects, X1 - 3.4, X1 - 2.3, zd + 1.5)
        vline(rects, X1 - 3.4, zd - 1.5, zd + 1.5)
    lines_part("decor_floor_lines", rects)


def boh_staff_door():
    """The staff door from main_floor, seen from behind: the same blue-grey pair in an aluminium frame (the leaves), a push-bar line, and over it
    SHOP FLOOR on main_floor's deep red board, an EXIT sign and an emergency light."""
    za, zb, zh = G.MF["staff"]
    part("Staff_Frame", "Paint_Palette", lambda bm: (lambda old: (door_frame(bm, "z", X0, za, zb, zh, +1), pt_uv(bm, old, pal_uv("grey_dark"))))(set(bm.faces)), keep_uv=True)
    bm = bmesh.new()
    wall_sign(bm, "SHOP FLOOR", (X0 + 0.012, zh + 0.5, (za + zb) / 2), "+x", 1.6, 0.2)
    wall_sign(bm, "NO SMOKING", (X0 + 0.012, 1.6, za - 0.7), "+x", 0.6, 0.075)
    finish("Signs_Staff", bm, "Signs", keep_uv=True, recalc=False)
    exit_sign((X0, zh + 0.22, (za + zb) / 2), "+x")
    emergency((X0, 3.1, (za + zb) / 2), "+x")


def boh_racking():
    """Four rows of pallet racking: blue upright frames every 2.88 m with bracing, orange beams at 1.6 and 3.2 m, wire decks, pallets and loads."""
    up, br, beam, deck = [], [], [], []
    pal, loads, wraps = [], [], []
    rng = np.random.default_rng(202)
    xs = list(np.linspace(G.RACK_X[0], G.RACK_X[1], 6))
    for k, (r0, r1) in enumerate(G.RACK_ROWS, 1):
        for x in xs:
            xa = min(max(x - 0.045, G.RACK_X[0]), G.RACK_X[1] - 0.09)
            for za in (r0, r1 - 0.09):
                up.append(((xa, 0.0, za), (xa + 0.09, 4.0, za + 0.09)))
                up.append(((xa - 0.04, 0.0, za - 0.02), (xa + 0.13, 0.01, za + 0.11)))            # the foot plate
            for j in range(3):                                                               # the frame's bracing: a zigzag in the frame's plane
                ya, yb = 0.15 + j * 1.24, 0.15 + (j + 1) * 1.24
                zz = (r0 + 0.09, r1 - 0.09) if j % 2 == 0 else (r1 - 0.09, r0 + 0.09)
                br.append(((xa + 0.045, ya, zz[0]), (xa + 0.045, yb, zz[1])))
        for i in range(5):
            xa, xb = xs[i] + 0.045, xs[i + 1] - 0.045
            for y in (1.6, 3.2):
                beam.append(((xa, y, r0), (xb, y + 0.15, r0 + 0.05)))
                beam.append(((xa, y, r1 - 0.05), (xb, y + 0.15, r1)))
                deck.append(((xa, y + 0.13, r0 + 0.05), (xb, y + 0.15, r1 - 0.05)))
            for lvl, (ybase, ytop) in enumerate(((0.0, 1.5), (1.75, 3.1), (3.35, 4.0))):
                if rng.random() < (0.12 if lvl == 0 else 0.22):
                    continue                                                                 # an empty bay
                for s in (0, 1):
                    if rng.random() < 0.1:
                        continue
                    pw = (xb - xa - 0.15) / 2
                    px0 = xa + 0.05 + s * (pw + 0.05)
                    pal.append((px0, px0 + pw, r0 + 0.04, r1 - 0.04, ybase, "x"))
                    top = ybase + 0.144 + rng.uniform(0.45, 1.0) * (ytop - ybase - 0.144)
                    load(loads, wraps, px0, px0 + pw, r0 + 0.04, r1 - 0.04, ybase + 0.144, top, rng)
    part("Rack_Uprights", "Steel_Blue", lambda bm: [cube(bm, a, b) for a, b in up])
    part("Rack_Bracing", "Steel_Blue", lambda bm: [cyl(bm, a, b, 0.012, seg=4) for a, b in br])
    part("Rack_Beams", "Steel_Orange", lambda bm: [cube(bm, a, b) for a, b in beam])
    part("Rack_Decks", "Steel_Galv", lambda bm: [cube(bm, a, b) for a, b in deck])
    make_loads("Rack", pal, loads, wraps)
    # row ends: a yellow column guard at each end of the free-standing rows, and a load notice
    p = Painter()
    for k, (r0, r1) in enumerate(G.RACK_ROWS):
        for x, s in ((G.RACK_X[0], 1), (G.RACK_X[1], -1)):
            p.add("yellow", box, x + s * 0.0, x + s * 0.3, 0.0, 0.4, r0, r0 + 0.12)
            p.add("yellow", box, x + s * 0.0, x + s * 0.3, 0.0, 0.4, r1 - 0.12, r1)
    p.done("Rack_Guards")


def boh_dock():
    """The loading dock: three shut roller doors in steel guides under their drum housings, levellers with hazard edges, rubber bumpers, the
    door controls, LOADING DOCK signs, and pallets waiting."""
    sh, guides, housings, bump, plates, hz = [], [], [], [], [], []
    for b in COLS:
        if b["name"].startswith("Dock_Door"):
            x0, y0, z0 = b["min"]
            x1, y1, z1 = b["max"]
            sh.append(((x0 - 0.02, 0.0, z0), (x1, y1, z1)))
            for zg in (z0, z1):
                guides.append(((x0 - 0.04, 0.0, zg - 0.08 if zg == z0 else zg), (x1, y1 + 0.3, zg if zg == z0 else zg + 0.08)))
            housings.append(((x1 - 0.42, y1, z0 - 0.1), (x1, y1 + 0.5, z1 + 0.1)))
            zc = (z0 + z1) / 2
            plates.append(((X1 - 2.2, 0.0, zc - 1.1), (X1 - 0.02, 0.02, zc + 1.1)))
            hz.append(((X1 - 2.3, 0.0, zc - 1.1), (X1 - 2.2, 0.021, zc + 1.1)))
            hz.append(((X1 - 2.2, 0.0, zc - 1.2), (X1 - 0.02, 0.021, zc - 1.1)))
            hz.append(((X1 - 2.2, 0.0, zc + 1.1), (X1 - 0.02, 0.021, zc + 1.2)))
        elif b["name"].startswith("Dock_Bumper"):
            x0, y0, z0 = b["min"]
            x1, y1, z1 = b["max"]
            bump.append((b["min"], b["max"]))
    part("Dock_Shutters", "Shutter", lambda bm: [cube(bm, a, b) for a, b in sh])
    part("Dock_Guides", "Steel_Galv", lambda bm: [cube(bm, a, b) for a, b in guides])
    part("Dock_Housings", "Steel_Galv", lambda bm: [cube(bm, a, b) for a, b in housings])
    part("Dock_Bumpers", "Rubber_Black", lambda bm: [cube(bm, a, b) for a, b in bump])
    part("decor_dock_levellers", "Floor_Plate", lambda bm: [cube(bm, a, b) for a, b in plates])
    part("decor_dock_hazard", "Hazard", lambda bm: [cube(bm, a, b) for a, b in hz])
    p = Painter()
    for zd in (-6.5, -1.5, 3.5):                       # the control box (up / down / stop) by each door, and its conduit
        z = zd + 1.85
        p.add("grey", box, X1 - 0.14, X1, 1.2, 1.55, z - 0.11, z + 0.11)
        for k, col in enumerate(("green", "red", "black")):
            p.add(col, box, X1 - 0.16, X1 - 0.14, 1.46 - k * 0.09, 1.52 - k * 0.09, z - 0.03, z + 0.03)
        p.add("grey_dark", box, X1 - 0.05, X1, 1.55, 3.4, z - 0.015, z + 0.015)
    p.done("decor_dock_controls")
    bm = bmesh.new()
    for k, zd in enumerate((-6.5, -1.5, 3.5), 1):
        wall_sign(bm, f"LOADING DOCK {k}", (X1 - 0.012, 4.05, zd), "-x", 1.8, 0.225)
    finish("Signs_Dock", bm, "Signs", keep_uv=True, recalc=False)
    rng = np.random.default_rng(303)
    pal, loads, wraps = [], [], []
    for b in COLS:
        if b["name"].startswith("Pallet"):
            a, l, w = pallet_stack(b["name"], b, rng, along="x", empty_stack=b["max"][1] < 0.3)
            pal += a
            loads += l
            wraps += w
    make_loads("Dock", pal, loads, wraps)
    # a hand pallet truck left by the doors (passable art: nothing stands where it is)
    p = Painter()
    px, pz = 37.4, -3.9
    for dz in (-0.2, 0.2):
        p.add("orange", box, px - 0.6, px + 0.55, 0.03, 0.08, pz + dz - 0.08, pz + dz + 0.08)
    p.add("orange", box, px + 0.55, px + 0.8, 0.03, 0.35, pz - 0.28, pz + 0.28)
    p.add("orange", cyl, (px + 0.7, 0.35, pz), (px + 1.05, 1.15, pz), 0.02, seg=6)
    p.add("black", box, px + 0.95, px + 1.15, 1.1, 1.2, pz - 0.15, pz + 0.15)
    p.done("decor_pallet_truck")
    for zd in (-6.5, -1.5, 3.5):
        emergency((X1, 3.75, zd + 2.1), "-x")


def boh_break():
    """The break room: a laminate table and four plastic chairs, the counter (cupboards, a sink, a kettle, mugs, the microwave), the fridge, the
    vending machine, the noticeboard and the rota, a clock."""
    b = BOX["Break_Table"]
    x0, _, z0 = b["min"]
    x1, y1, z1 = b["max"]
    part("Break_Table_Top", "Wood_Light", lambda bm: box(bm, x0, x1, y1 - 0.03, y1, z0, z1))
    p = Painter()
    for xl in (x0 + 0.06, x1 - 0.06):
        for zl in (z0 + 0.06, z1 - 0.06):
            p.add("steel", cyl, (xl, 0.0, zl), (xl, y1 - 0.03, zl), 0.022, seg=6)
    for n in ("Break_Chair", "Break_Chair_2", "Break_Chair_3", "Break_Chair_4"):
        c = BOX[n]
        cx0, _, cz0 = c["min"]
        cx1, cy1, cz1 = c["max"]
        back = cz0 if (cz0 + cz1) / 2 < (z0 + z1) / 2 else cz1 - 0.04
        for xl in (cx0 + 0.03, cx1 - 0.03):
            for zl in (cz0 + 0.03, cz1 - 0.03):
                p.add("steel", cyl, (xl, 0.0, zl), (xl, 0.44, zl), 0.01, seg=5)
        p.add("chair_blue", box, cx0, cx1, 0.42, 0.46, cz0, cz1)
        p.add("chair_blue", box, cx0, cx1, 0.46, cy1, back, back + 0.04)
    # mugs, a newspaper, a lunchbox left on the table
    for k, (mx, mz) in enumerate(((15.0, 10.8), (16.4, 11.2), (16.6, 10.7))):
        p.add("mug_blue" if k % 2 else "white", cyl, (mx, y1, mz), (mx, y1 + 0.1, mz), 0.04, seg=10)
    p.add("paper", box, 15.4, 15.9, y1, y1 + 0.01, 10.6, 11.0)
    p.add("red", box, 14.6, 14.9, y1, y1 + 0.08, 11.1, 11.3)
    # the counter: cupboards under a laminate top, a steel sink, a kettle, the microwave, wall cupboards
    c = BOX["Break_Counter"]
    cx0, _, cz0 = c["min"]
    cx1, cy1, cz1 = c["max"]
    p.add("white", box, cx0, cx1 - 0.02, 0.1, cy1 - 0.04, cz0, cz1)
    p.add("black", box, cx0, cx1 - 0.06, 0.0, 0.1, cz0, cz1)
    for k in range(int((cz1 - cz0) / 0.6)):
        zc = cz0 + 0.3 + k * 0.6
        p.add("steel", box, cx1 - 0.025, cx1 - 0.01, 0.7, 0.72, zc - 0.08, zc + 0.08)
    p.add("steel", box, cx0 + 0.15, cx1 - 0.1, cy1 - 0.05, cy1 - 0.035, 9.3, 9.9)
    p.add("chrome", cyl, (cx0 + 0.1, cy1, 9.6), (cx0 + 0.1, cy1 + 0.3, 9.6), 0.015, seg=6)
    p.add("chrome", cyl, (cx0 + 0.1, cy1 + 0.3, 9.6), (cx0 + 0.3, cy1 + 0.28, 9.6), 0.012, seg=6)
    p.add("white", cyl, (cx0 + 0.4, cy1, 10.6), (cx0 + 0.4, cy1 + 0.22, 10.6), 0.08, seg=10)
    p.add("microwave", box, cx0 + 0.02, cx0 + 0.42, cy1, cy1 + 0.3, 12.0, 12.52)
    p.add("glass_dark", box, cx0 + 0.42, cx0 + 0.425, cy1 + 0.05, cy1 + 0.25, 12.05, 12.36)
    p.add("plastic_dark", box, cx0 + 0.42, cx0 + 0.425, cy1 + 0.05, cy1 + 0.25, 12.39, 12.49)
    p.add("white", box, cx0, cx0 + 0.34, 1.5, 2.2, cz0, cz1)                               # the wall cupboards (over the counter's footprint)
    p.add("black", box, cx0, cx0 + 0.32, 1.48, 1.5, cz0, cz1)
    # the fridge (its own collider)
    f = BOX["Break_Fridge"]
    fx0, _, fz0 = f["min"]
    fx1, fy1, fz1 = f["max"]
    p.add("fridge", box, fx0, fx1, 0.02, fy1, fz0, fz1)
    p.add("black", box, fx0, fx1 - 0.01, 0.0, 0.02, fz0, fz1)
    p.add("grey", box, fx1 - 0.002, fx1, 1.18, 1.2, fz0, fz1)
    p.add("chrome", box, fx1, fx1 + 0.03, 1.3, 1.7, fz1 - 0.08, fz1 - 0.05)
    p.add("chrome", box, fx1, fx1 + 0.03, 0.8, 1.1, fz1 - 0.08, fz1 - 0.05)
    p.add("paper_yellow", box, fx1, fx1 + 0.002, 1.4, 1.52, fz0 + 0.2, fz0 + 0.32)
    # the vending machine
    v = BOX["Vending"]
    vx0, _, vz0 = v["min"]
    vx1, vy1, vz1 = v["max"]
    p.add("vending", box, vx0, vx1, 0.0, vy1, vz0 + 0.02, vz1)
    p.add("glass_dark", box, vx0 + 0.08, vx0 + 0.82, 0.55, 1.75, vz0, vz0 + 0.02)
    p.add("plastic_dark", box, vx0 + 0.88, vx1 - 0.08, 0.9, 1.5, vz0, vz0 + 0.02)
    p.add("black", box, vx0 + 0.1, vx0 + 0.8, 0.12, 0.35, vz0, vz0 + 0.02)
    p.done("Break_Furniture")
    part("Break_Vending_Glow", "Lamp_Emit", lambda bm: box(bm, vx0 + 0.1, vx0 + 0.8, 1.76, 1.82, vz0 - 0.005, vz0 + 0.02))
    # the noticeboard and the rota on the room's north wall, a clock
    bm = bmesh.new()
    zw = G.ROOMS_Z + T + 0.012
    panel(None, None, (14.3, 1.55, zw), "+z", 1.6, 1.0, rect_uv(*NOTICE, e=2), bm=bm)
    panel(None, None, (18.4, 1.5, zw), "+z", 0.42, 0.21, rect_uv(*ROTA, e=2), bm=bm)
    panel(None, None, (17.4, 2.45, zw + 0.01), "+z", 0.3, 0.3, rect_uv(*CLOCK, e=1), bm=bm)
    wall_sign(bm, "BREAK ROOM", (16.1, 2.45, G.ROOMS_Z - 0.012), "-z", 1.0, 0.125)
    wall_sign(bm, "LOCKERS", (22.6, 2.45, G.ROOMS_Z - 0.012), "-z", 0.9, 0.11)
    wall_sign(bm, "MANAGER", (28.6, 2.45, G.ROOMS_Z - 0.012), "-z", 0.9, 0.11)
    wall_sign(bm, "STAIRS", (34.1, 2.45, G.ROOMS_Z - 0.012), "-z", 0.9, 0.11)
    wall_sign(bm, "NO SMOKING", (13.0, 1.6, G.ROOMS_Z + T + 0.012), "+z", 0.6, 0.075)
    finish("Signs_Rooms", bm, "Signs", keep_uv=True, recalc=False)
    part("Break_Noticeboard_Frame", "Steel_Galv", lambda bm: box(bm, 13.48, 15.12, 1.03, 2.07, zw - 0.012, zw - 0.002))


def boh_lockers():
    """Grey lockers: two banks of two-tier lockers (0.33 m columns) on a plinth, a slatted bench, a coat or a hi-vis vest left out."""
    for n, face in (("Lockers_W", "+x"), ("Lockers_E", "-x")):
        b = BOX[n]
        x0, _, z0 = b["min"]
        x1, y1, z1 = b["max"]
        part(f"{n}_Body", "Steel_Grey", lambda bm: (box(bm, x0, x1, 0.1, y1, z0, z1), box(bm, x0 + 0.02, x1 - 0.02, 0.0, 0.1, z0, z1)))
        xf = x1 + 0.002 if face == "+x" else x0 - 0.002
        L = z1 - z0
        bm = bmesh.new()
        nl = L / 0.33
        pts = [(xf, 0.1, z1), (xf, 0.1, z0), (xf, y1 - 0.02, z0), (xf, y1 - 0.02, z1)] if face == "+x" else [(xf, 0.1, z0), (xf, 0.1, z1), (xf, y1 - 0.02, z1), (xf, y1 - 0.02, z0)]
        uvquad(bm, pts, (0, 0, nl, 1))
        finish(f"{n}_Fronts", bm, "Locker_Front", keep_uv=True, recalc=False)
    b = BOX["Locker_Bench"]
    x0, _, z0 = b["min"]
    x1, y1, z1 = b["max"]
    part("Locker_Bench_Slats", "Wood_Light", lambda bm: [box(bm, x0 + 0.02 + k * 0.26, x0 + 0.24 + k * 0.26, y1 - 0.04, y1, z0, z1) for k in range(3)])
    p = Painter()
    for zl in (z0 + 0.03, (z0 + z1) / 2, z1 - 0.03):
        p.add("steel", box, x0 + 0.02, x1 - 0.02, 0.0, y1 - 0.04, zl - 0.02, zl + 0.02)
    p.add("hivis", box, 22.3, 22.8, y1, y1 + 0.04, 10.0, 10.6)
    p.add("jacket", box, 22.4, 22.9, y1, y1 + 0.06, 12.4, 12.9)
    p.add("black", box, 22.5, 22.8, 0.0, 0.12, 13.6, 13.9)                                   # a pair of boots under the bench's end (low)
    p.done("Locker_Things")


def boh_office():
    """The manager's office: a steel desk (a lamp, a phone, a logbook, a mug), a pushed-back chair, a grey filing cabinet, and the bank of CRT
    monitors on their console, three rows of nine, each showing a camera (Screen_CRT, lit at every hour), a video recorder stack and tapes."""
    d = BOX["Office_Desk"]
    x0, _, z0 = d["min"]
    x1, y1, z1 = d["max"]
    part("Office_Desk_Top", "Wood_Light", lambda bm: box(bm, x0, x1, y1 - 0.03, y1, z0, z1))
    part("Office_Desk_Body", "Steel_Grey", lambda bm: (box(bm, x0, x0 + 0.45, 0.0, y1 - 0.03, z0 + 0.02, z1 - 0.02), box(bm, x1 - 0.45, x1, 0.0, y1 - 0.03, z0 + 0.02, z1 - 0.02),
                                                      box(bm, x0 + 0.45, x1 - 0.45, 0.3, y1 - 0.03, z0 + 0.02, z0 + 0.05)))
    p = Painter()
    p.add("lamp_shade", cyl, (x0 + 0.3, y1, z0 + 0.25), (x0 + 0.3, y1 + 0.02, z0 + 0.25), 0.08, seg=10)
    p.add("lamp_shade", cyl, (x0 + 0.3, y1, z0 + 0.25), (x0 + 0.35, y1 + 0.38, z0 + 0.3), 0.01, seg=5)
    p.add("lamp_shade", cyl, (x0 + 0.35, y1 + 0.38, z0 + 0.3), (x0 + 0.45, y1 + 0.32, z0 + 0.38), 0.07, 0.03, seg=10)
    p.add("plastic_dark", box, x1 - 0.5, x1 - 0.28, y1, y1 + 0.07, z0 + 0.15, z0 + 0.35)
    p.add("red", box, 27.6, 28.0, y1, y1 + 0.03, 11.2, 11.5)
    p.add("paper", box, 28.2, 28.5, y1, y1 + 0.006, 11.3, 11.6)
    p.add("white", cyl, (28.9, y1, 11.25), (28.9, y1 + 0.1, 11.25), 0.04, seg=10)
    # the console: a long steel cabinet under the bank, a keyboard, a microphone, the recorders
    c = BOX["Monitor_Shelf"]
    cx0, _, cz0 = c["min"]
    cx1, cy1, cz1 = c["max"]
    p.add("grey_dark", box, cx0, cx1, 0.08, cy1, cz0, cz1)
    p.add("black", box, cx0 + 0.02, cx1 - 0.02, 0.0, 0.08, cz0 + 0.04, cz1)
    p.add("keyboard", box, 27.9, 28.6, cy1, cy1 + 0.03, cz0 + 0.02, cz0 + 0.2)
    p.add("black", cyl, (29.0, cy1, cz0 + 0.12), (29.0, cy1 + 0.25, cz0 + 0.12), 0.006, seg=5)
    for k in range(4):                                                                     # the recorder stack at the east end, and tapes
        p.add("vcr_black", box, 31.0, 31.75, cy1 + k * 0.1, cy1 + k * 0.1 + 0.09, cz0 + 0.0, cz0 + 0.38)
    for k in range(6):
        p.add("black", box, 25.5 + k * 0.03, 25.52 + k * 0.03, cy1, cy1 + 0.19, cz0 + 0.05, cz0 + 0.15)
    # the monitor rack (posts and shelves) and the CRTs
    bk = BOX["Monitor_Bank"]
    bx0, by0, bz0 = bk["min"]
    bx1, by1, bz1 = bk["max"]
    for x in np.linspace(bx0 + 0.02, bx1 - 0.02, 4):
        p.add("grey_dark", box, x - 0.02, x + 0.02, by0, by1, bz0 + 0.05, bz0 + 0.09)
        p.add("grey_dark", box, x - 0.02, x + 0.02, by0, by1, cz1 - 0.06, cz1 - 0.02)
    for y in (by0 + 0.52, by0 + 1.06, by1 - 0.02):
        p.add("grey_dark", box, bx0, bx1, y, y + 0.02, bz0 + 0.05, cz1 - 0.02)
    cols = 9
    cw = (bx1 - bx0 - 0.1) / cols
    screens = bmesh.new()
    k = 0
    for row in range(3):
        yb = by0 + 0.02 + row * 0.54
        for c in range(cols):
            xc = bx0 + 0.05 + (c + 0.5) * cw
            w, hh = cw - 0.06, 0.46
            zf = bz0 + 0.02
            p.add("crt_beige", box, xc - w / 2, xc + w / 2, yb, yb + hh, zf, zf + 0.12)
            p.add("crt_beige", box, xc - w * 0.38, xc + w * 0.38, yb + 0.04, yb + hh - 0.06, zf + 0.12, zf + 0.46)
            p.add("plastic_dark", box, xc - w / 2 + 0.035, xc + w / 2 - 0.035, yb + 0.06, yb + hh - 0.035, zf - 0.004, zf)
            p.add("black", box, xc + w / 2 - 0.06, xc + w / 2 - 0.03, yb + 0.02, yb + 0.045, zf - 0.006, zf)
            panel(None, None, (xc, yb + 0.06 + (hh - 0.095) / 2, zf - 0.006), "-z", w - 0.09, hh - 0.11, feed_uv(k), bm=screens)
            k += 1
    finish("Office_Screens", screens, "Screen_CRT", keep_uv=True, recalc=False)
    # the filing cabinet, a waste bin, the pushed-back chair (passable art: it would block the monitor spot)
    f = BOX["Office_Cabinet"]
    fx0, _, fz0 = f["min"]
    fx1, fy1, fz1 = f["max"]
    p.add("grey", box, fx0, fx1, 0.0, fy1, fz0, fz1)
    for k in range(3):
        y = 0.1 + k * 0.4
        p.add("steel", box, fx0 + 0.3 + 0.0, fx0 + 0.9, y + 0.22, y + 0.25, fz1, fz1 + 0.02)
        p.add("grey_dark", box, fx0 + 0.02, fx1 - 0.02, y + 0.36, y + 0.38, fz1, fz1 + 0.003)
    p.done("Office_Furniture")
    p = Painter()
    cxp, czp = 30.1, 12.2
    p.add("chair_seat", box, cxp - 0.24, cxp + 0.24, 0.45, 0.52, czp - 0.24, czp + 0.24)
    p.add("chair_seat", box, cxp - 0.22, cxp + 0.22, 0.6, 1.0, czp + 0.2, czp + 0.26)
    p.add("black", cyl, (cxp, 0.08, czp), (cxp, 0.45, czp), 0.025, seg=6)
    for a in range(5):
        an = a * 2 * math.pi / 5
        p.add("black", cyl, (cxp, 0.07, czp), (cxp + 0.28 * math.cos(an), 0.05, czp + 0.28 * math.sin(an)), 0.015, seg=4)
    p.add("bin_green", cyl, (26.0, 0.0, 8.0), (26.0, 0.35, 8.0), 0.15, 0.17, seg=10)
    p.done("decor_office_chair")
    bm = bmesh.new()
    panel(None, None, (27.0, 2.25, G.ROOMS_Z + T + 0.01), "+z", 0.3, 0.3, rect_uv(*CLOCK, e=1), bm=bm)
    panel(None, None, (31.98, 1.6, 10.6), "-x", 0.5, 0.44, rect_uv(*CALENDAR, e=2), bm=bm)
    finish("Signs_Office", bm, "Signs", keep_uv=True, recalc=False)
    light("both", "AREA", (28.6, 1.6, 12.9), 18.0, (0.62, 0.86, 0.74), aim=(0, 0, -1), shape=(5.6, 1.4))


def boh_stairs():
    """The stair room: the landing behind the stair door, a tubular rail, and the stairs going down into the dark behind it (the basement's flight
    seen from above: art only, past the rail)."""
    r = BOX["Stair_Rail"]
    rx0, _, rz0 = r["min"]
    rx1, ry1, rz1 = r["max"]
    p = Painter()
    p.add("yellow", cyl, (rx0, ry1 - 0.03, (rz0 + rz1) / 2), (rx1, ry1 - 0.03, (rz0 + rz1) / 2), 0.03, seg=8)
    p.add("yellow", cyl, (rx0, 0.5, (rz0 + rz1) / 2), (rx1, 0.5, (rz0 + rz1) / 2), 0.02, seg=8)
    for x in np.linspace(rx0 + 0.04, rx1 - 0.04, 5):
        p.add("yellow", cyl, (x, 0.0, (rz0 + rz1) / 2), (x, ry1, (rz0 + rz1) / 2), 0.025, seg=8)
    p.add("grey", box, rx0, rx1, 0.0, 0.12, rz0, rz1)
    p.done("Stair_Rail_Art")
    rise = G.BOH_Y / 15
    st = G.STAIR

    def steps(bm):
        for i in range(14):
            top = rise * (i + 1) - G.BOH_Y
            za, zb = st["foot"] - 0.28 * (i + 1), st["foot"] - 0.28 * i
            box(bm, st["x0"], 34.0, top - rise, top, za, zb)
        box(bm, st["x0"], st["x1"], -G.BOH_Y - 0.3, -G.BOH_Y, rz1, Z1)
    part("Well_Steps", "Floor_Concrete", steps)
    part("Well_Walls", "Wall_Block", lambda bm: (box(bm, st["x0"] - 0.2, st["x0"], -G.BOH_Y, 0.0, rz1, Z1), box(bm, st["x1"], st["x1"] + 0.2, -G.BOH_Y, 0.0, rz1, Z1),
                                                     box(bm, st["x0"], st["x1"], -G.BOH_Y, 0.0, Z1, Z1 + 0.2)))
    part("decor_well_nosing", "Steel_Yellow", lambda bm: [box(bm, st["x0"], 34.0, rise * (i + 1) - G.BOH_Y - 0.02, rise * (i + 1) - G.BOH_Y + 0.003,
                                                                  st["foot"] - 0.28 * (i + 1), st["foot"] - 0.28 * (i + 1) + 0.05) for i in range(14)])
    part("decor_well_edge", "Hazard", lambda bm: box(bm, st["x0"], st["x1"], -0.06, 0.004, rz1, rz1 + 0.08))
    light("day", "POINT", (34.1, -1.0, 12.5), 25.0, WARM, size=0.05)


def boh_lift():
    """The freight lift: the lobby in front of it, the gate's hazard-striped steel frame, FREIGHT LIFT and KEYCARD ONLY over it, a hatched floor box,
    and the keycard reader (steel back plate, the reader with its glowing red ring and screen, a conduit), lit by its own lamp at every hour; the car
    behind the gate (tread-plate floor, steel lining, timber bump rails, the button panel)."""
    L = G.LIFT
    zf = L["z0"]                        # the gate wall's face (it faces -z, the lobby)
    gx0, gx1 = L["door"]
    gh = L["h"]
    # the gate's frame: hazard-striped jambs and head, a heavy steel lintel, bollards
    part("Lift_Gate_Frame", "Hazard", lambda bm: (box(bm, gx0 - 0.22, gx0 - 0.02, 0.0, gh + 0.22, zf - 0.03, zf), box(bm, gx1 + 0.02, gx1 + 0.22, 0.0, gh + 0.22, zf - 0.03, zf),
                                                 box(bm, gx0 - 0.22, gx1 + 0.22, gh + 0.02, gh + 0.22, zf - 0.03, zf)))
    part("Lift_Gate_Guides", "Steel_Galv", lambda bm: (box(bm, gx0 - 0.02, gx0, 0.0, gh, zf - 0.04, zf + 0.2), box(bm, gx1, gx1 + 0.02, 0.0, gh, zf - 0.04, zf + 0.2),
                                                      box(bm, gx0, gx1, gh - 0.02, gh, zf + 0.12, zf + 0.2)))
    part("decor_lift_floor_hatch", "Hazard", lambda bm: box(bm, gx0 - 0.2, gx1 + 0.2, 0.0, 0.003, zf - 1.0, zf))
    p = Painter()
    p.add("grey_dark", box, gx0 - 0.25, gx1 + 0.25, gh + 0.22, gh + 0.3, zf - 0.04, zf)
    p.done("Lift_Lintel")
    bm = bmesh.new()
    wall_sign(bm, "FREIGHT LIFT", ((gx0 + gx1) / 2, 2.89, zf - 0.012), "-z", 1.5, 0.16)
    wall_sign(bm, "KEYCARD ONLY" if BOH else "BASEMENT", (41.05, 1.85, zf - 0.012), "-z", 0.8, 0.1)
    finish("Signs_Lift", bm, "Signs", keep_uv=True, recalc=False)
    if BOH:
        r = BOX["Keycard_Reader"]
        rx0, ry0, rz0 = r["min"]
        rx1, ry1, rz1 = r["max"]
        rc = ((rx0 + rx1) / 2, (ry0 + ry1) / 2)
        part("Keycard_Reader_Plate", "Steel_Galv", lambda bm: box(bm, rx0 - 0.04, rx1 + 0.04, ry0 - 0.12, ry1 + 0.1, zf - 0.045, zf))
        part("decor_keycard_reader", "Paint_Palette", lambda bm: (lambda old: (box(bm, rc[0] - 0.08, rc[0] + 0.08, rc[1] - 0.12, rc[1] + 0.12, zf - 0.1, zf - 0.045),
                                                                             box(bm, rc[0] - 0.012, rc[0] + 0.012, ry1 + 0.1, 2.75, zf - 0.04, zf - 0.016),
                                                                             pt_uv(bm, old, pal_uv("black"))))(set(bm.faces)), keep_uv=True)
        bm = bmesh.new()
        panel(None, None, (rc[0], rc[1] - 0.02, zf - 0.101), "-z", 0.13, 0.16, rect_uv(*READER, e=2), bm=bm)
        finish("decor_keycard_face", bm, "Signs", keep_uv=True, recalc=False)

        def glow(bm):
            for k in range(16):                         # the ring round the card mark, as a polygon of small boxes
                a0 = k * 2 * math.pi / 16
                cx, cy = rc[0] + 0.062 * math.cos(a0), rc[1] + 0.05 + 0.062 * math.sin(a0)
                box(bm, cx - 0.008, cx + 0.008, cy - 0.008, cy + 0.008, zf - 0.106, zf - 0.1)
            box(bm, rc[0] - 0.05, rc[0] + 0.05, rc[1] - 0.105, rc[1] - 0.08, zf - 0.106, zf - 0.1)
        part("decor_keycard_glow", "Reader_Glow", glow)
        light("both", "POINT", (rc[0], rc[1] + 0.02, zf - 0.2), 0.8, (1.0, 0.15, 0.08), size=0.03)
        light("both", "SPOT", (rc[0], 2.6, zf - 0.35), 14.0, (1.0, 0.92, 0.8), size=0.04, aim=(0, -1, 0.15), cone=40.0)
        p = Painter()
        p.add("grey_dark", cyl, (rc[0], 2.62, zf - 0.35), (rc[0], 2.74, zf - 0.35), 0.05, 0.03, seg=10)
        p.add("grey_dark", box, rc[0] - 0.01, rc[0] + 0.01, 2.72, 3.0, zf - 0.36, zf - 0.34)
        p.done("Reader_Lamp")
    # the car: tread plate floor, steel lining with timber bump rails, a lamp, the button panel
    cx0, cx1, cz0, cz1 = L["x0"], L["x1"], L["z0"] + T, L["z1"]
    for n in ("LiftCar_Wall_E_1", "LiftCar_Wall_S_1", "LiftCar_Wall_W_1"):
        plain(f"Car_{n}", BOX[n], "Steel_Galv")
    plain("Car_Ceiling", BOX["LiftCar_Ceiling"], "Steel_Galv")
    part("decor_car_floor", "Floor_Plate", lambda bm: box(bm, cx0, cx1, 0.0, 0.01, cz0, cz1))
    part("Car_Bump_Rails", "Wood_Light", lambda bm: [(box(bm, cx0, cx0 + 0.04, y, y + 0.15, cz0, cz1), box(bm, cx1 - 0.04, cx1, y, y + 0.15, cz0, cz1),
                                                     box(bm, cx0, cx1, y, y + 0.15, cz1 - 0.04, cz1)) for y in (0.35, 0.95)])
    bm = bmesh.new()
    panel(None, None, (cx1 - 0.005, 1.3, cz0 + 0.5), "-x", 0.2, 0.36, rect_uv(*LIFTPANEL, e=2), bm=bm)
    finish("Car_Panel", bm, "Signs", keep_uv=True, recalc=False)
    fp = fittings()
    troffer(fp, (cx0 + cx1) / 2, 2.8, (cz0 + cz1) / 2, w=30.0)
    make_fittings(fp, "Car")
    return fp


def boh_rooms_lights():
    fp = fittings()
    for x, z in ((14.2, 9.4), (17.8, 12.6), (22.6, 9.4), (22.6, 12.8), (26.8, 9.6), (30.0, 9.6), (28.6, 12.4), (34.1, 7.9), (38.0, 8.7), (41.0, 8.7)):
        troffer(fp, x, 3.0, z, w=55.0, along="x" if x > 36 else "z")
    make_fittings(fp, "Rooms")
    fp = fittings()
    for z in (-6.5, -2.85, 0.85, 5.1):
        for x in np.arange(14.6, 41.0, 3.4):
            if z > 4 or x < 31:
                batten(fp, (x, 4.0, z), 1.5, "x", top=H - 0.4 if any(abs(x - bx) < 0.9 for bx in (18.0, 24.0, 30.0, 36.0)) else H, w=55.0)
    for z in (-7.8, -4.2, -0.6, 3.0):
        for x in (32.8, 36.2, 39.6):
            batten(fp, (x, 4.0, z), 1.5, "x", top=H, w=55.0)
    make_fittings(fp, "Hall")


def build_back_of_house():
    boh_shell()
    boh_staff_door()
    boh_racking()
    boh_dock()
    boh_break()
    boh_lockers()
    boh_office()
    boh_stairs()
    boh_lift()
    boh_rooms_lights()
    # door frames on the rooms' front, the stair door's EXIT sign
    def frames(bm):
        for d in GB.doors:
            n = d["name"]
            if n in ("DoorLeaf_break", "DoorLeaf_lockers", "DoorLeaf_office", "DoorLeaf_basement_stairs"):
                a0 = d["hinge"][0]
                door_frame(bm, "x", G.ROOMS_Z, a0, a0 + G.DOOR_W, G.DOOR_H, -1)
                door_frame(bm, "x", G.ROOMS_Z + T, a0, a0 + G.DOOR_W, G.DOOR_H, +1)
    part("Door_Frames", "Paint_Palette", lambda bm: (lambda old: (frames(bm), pt_uv(bm, old, pal_uv("grey_dark"))))(set(bm.faces)), keep_uv=True)
    exit_sign((34.1, 2.75, G.ROOMS_Z), "-z")
    for pos, n in (((22.6, 2.75, G.ROOMS_Z), "-z"), ((39.2, 2.85, G.ROOMS_Z), "-z"), ((12.2, 3.6, -0.5), "+x"), ((31.0, 3.6, Z0), "+z"),
                   ((14.5, 3.6, Z0), "+z"), ((16.1, 2.6, G.ROOMS_Z + T), "+z"), ((28.6, 2.6, G.ROOMS_Z + T), "+z"), ((41.5, 2.6, G.ROOMS_Z + T), "+z")):
        emergency(pos, n)
    # a fire extinguisher and its sign by the staff door; a red fire point by the stairs
    p = Painter()
    p.add("ext_red", cyl, (12.35, 0.35, -3.9), (12.35, 0.95, -3.9), 0.08, seg=10)
    p.add("black", cyl, (12.35, 0.95, -3.9), (12.35, 1.05, -3.9), 0.03, seg=6)
    p.done("decor_extinguisher")


# ================================================================ basement
def bas_shell():
    st = G.STAIR
    sw0, sw1 = st["x0"] - T, st["x1"] + T
    xs = [X0 - T, 18.0, 18.2, 24.0, 24.2, X1 + T]
    zs = [Z0 - T, 2.8, Z1 + T]

    def pick(xm, zm):
        return "Floor_Frost" if (zm < 2.8 and xm < 24.0 and not (18.0 < xm < 18.2)) else "Floor_Concrete"
    floor_cells(grid_cells(xs, zs, pick))
    for b in COLS:
        n = b["name"]
        if n.startswith(("Basement_Wall_", "Stairwell_Wall_", "Plant_Wall_", "Lift_Wall_")):
            wall_bands(n, b)
        elif n.startswith("Basement_Ceiling") or n == "Stairwell_Ceiling":
            plain(f"Ceil_{n}", b, "Ceiling_Soffit")
        elif n.startswith(("Freezer_1_Wall_S", "Freezer_2_Wall_S")) or n in ("Freezer_Divide", "Freezer_Wall_E"):
            # outside: the insulated panel; inside: frost (two skins, each over the collider)
            x0, y0, z0 = b["min"]
            x1, y1, z1 = b["max"]
            if "Wall_S" in n:
                part(f"Freezer_Out_{n}", "Freezer_Panel", lambda bm, b=b: cube(bm, (b["min"][0], b["min"][1], b["min"][2] + 0.1), b["max"]))
                part(f"Freezer_In_{n}", "Frost_Panel", lambda bm, b=b: cube(bm, b["min"], (b["max"][0], b["max"][1], b["min"][2] + 0.1)))
            elif n == "Freezer_Wall_E":
                part(f"Freezer_Out_{n}", "Freezer_Panel", lambda bm, b=b: cube(bm, (b["min"][0] + 0.1, b["min"][1], b["min"][2]), b["max"]))
                part(f"Freezer_In_{n}", "Frost_Panel", lambda bm, b=b: cube(bm, b["min"], (b["min"][0] + 0.1, b["max"][1], b["max"][2])))
            else:
                plain(f"Freezer_In_{n}", b, "Frost_Panel")
        elif n.endswith("_Ceiling") and n.startswith("Freezer"):
            plain(f"Ceil_{n}", b, "Frost_Panel")
    # the freezers' inner skins on the basement's own walls (frost over the block): the north wall and the west wall inside them
    part("Freezer_In_Walls", "Frost_Panel", lambda bm: (box(bm, X0, 24.0, 0.0, 3.0, Z0, Z0 + 0.02), box(bm, X0, X0 + 0.02, 0.0, 3.0, Z0, 2.8)))
    # bulkheads over the freezers (from their 3 m roofs to the 3.7 m ceiling) and the frost-free floor strip in their doorways
    part("Wall_Bulkhead_Block", "Wall_Block", lambda bm: (box(bm, X0, 24.2, 3.0, H, 2.8, 3.0), box(bm, 24.0, 24.2, 3.0, H, Z0, 2.8)))
    # pipes and cable trays under the soffit, along the service corridor
    p = Painter()
    for k, (col, z, r) in enumerate((("pipe_red", 3.5, 0.05), ("pipe_blue", 3.8, 0.06), ("lagging", 4.15, 0.09), ("pipe_green", 4.45, 0.04))):
        p.add(col, cyl, (X0, H - 0.25 - 0.05 * (k % 2), z), (sw0 - 0.05, H - 0.25 - 0.05 * (k % 2), z), r, seg=10)
        p.add(col, cyl, (sw1 + 0.05, H - 0.25 - 0.05 * (k % 2), z), (X1, H - 0.25 - 0.05 * (k % 2), z), r, seg=10)
        for x in np.arange(X0 + 1.0, X1, 3.0):
            if not (sw0 - 0.1 < x < sw1 + 0.1):
                p.add("grey_dark", box, x - 0.02, x + 0.02, H - 0.32, H, z - 0.02, z + 0.02)
    p.add("grey_dark", box, X0, sw0 - 0.05, H - 0.12, H - 0.08, 5.6, 6.0)
    p.add("grey_dark", box, sw1 + 0.05, X1, H - 0.12, H - 0.08, 5.6, 6.0)
    p.done("Overhead_Services")
    # floor lines: the corridor's edges and the pallet bays
    rects = []
    hline(rects, X0 + 0.3, sw0 - 0.3, 6.9)
    hline(rects, X0 + 0.3, 27.8, 3.4)
    hline(rects, sw1 + 0.3, X1 - 0.3, 6.9)
    lines_part("decor_floor_lines", rects)


def bas_freezers():
    """Two walk-in freezers: frosted wire shelving with frozen cartons, an evaporator under each roof, a cold light inside (Freezer_Glow, on at
    every hour), strip curtains in the doorways; outside, the door trims, the -22 C readout, the status lamp and the COLD STORE signs."""
    rng = np.random.default_rng(404)
    frames, shelves, cart = [], [], []
    for k in (1, 2):
        for side in ("N", "W"):
            b = BOX[f"Freezer_{k}_Shelf_{side}"]
            x0, _, z0 = b["min"]
            x1, y1, z1 = b["max"]
            for y in (0.15, 0.7, 1.25, 1.8):
                shelves.append(((x0, y, z0), (x1, y + 0.03, z1)))
                along = x1 - x0 > z1 - z0
                L = (x1 - x0) if along else (z1 - z0)
                n = int(L / 0.45)
                for j in range(n):
                    if rng.random() < 0.3:
                        continue
                    a = (x0 if along else z0) + 0.05 + j * L / n
                    bw = L / n - 0.06
                    hh = rng.uniform(0.18, 0.42)
                    if along:
                        cart.append((a, a + bw, y + 0.03, y + 0.03 + hh, z0 + 0.04, z1 - 0.06, "frozen" if rng.random() < 0.7 else "white"))
                    else:
                        cart.append((x0 + 0.04, x1 - 0.06, y + 0.03, y + 0.03 + hh, a, a + bw, "frozen" if rng.random() < 0.7 else "white"))
            for (px, pz) in ((x0, z0), (x1 - 0.03, z0), (x0, z1 - 0.03), (x1 - 0.03, z1 - 0.03)):
                frames.append(((px, 0.0, pz), (px + 0.03, y1, pz + 0.03)))
            if b["max"][0] - b["min"][0] > 2:
                for px in np.linspace(x0, x1 - 0.03, 5)[1:-1]:
                    frames.append(((px, 0.0, z0), (px + 0.03, y1, z0 + 0.03)))
                    frames.append(((px, 0.0, z1 - 0.03), (px + 0.03, y1, z1)))
            else:
                for pz in np.linspace(z0, z1 - 0.03, 6)[1:-1]:
                    frames.append(((x0, 0.0, pz), (x0 + 0.03, y1, pz + 0.03)))
                    frames.append(((x1 - 0.03, 0.0, pz), (x1, y1, pz + 0.03)))
            part(f"Freezer_Rack_{k}{side}", "Steel_Galv", lambda bm: [cube(bm, a, b) for a, b in frames + shelves])   # one object a shelf unit
            frames, shelves = [], []
    part("Freezer_Cartons", "Carton", lambda bm: [carton(bm, *c[:6], kind=c[6]) for c in cart], keep_uv=True, recalc=False)
    p = Painter()
    for k, (a0, a1) in enumerate(((X0, 18.0), (18.2, 24.0)), 1):
        xc = (a0 + a1) / 2
        p.add("white", box, xc - 0.7, xc + 0.7, 2.55, 2.98, -3.0, -2.4)                   # the evaporator under the roof
        p.add("grey_dark", box, xc - 0.65, xc + 0.65, 2.6, 2.9, -2.401, -2.398)
        for f in (-0.35, 0.35):
            p.add("black", cyl, (xc + f, 2.75, -2.398), (xc + f, 2.75, -2.39), 0.12, seg=12)
    p.done("Freezer_Evaporators")
    # the lights inside, and their glow
    def lamps(bm):
        for a0, a1 in ((X0, 18.0), (18.2, 24.0)):
            xc = (a0 + a1) / 2
            for zc in (-1.0, 1.4):
                box(bm, xc - 0.6, xc + 0.6, 2.93, 2.98, zc - 0.06, zc + 0.06)
    part("Freezer_Lamps", "Freezer_Glow", lamps)
    for a0, a1 in ((X0, 18.0), (18.2, 24.0)):
        xc = (a0 + a1) / 2
        for zc in (-1.0, 1.4):
            light("both", "AREA", (xc, 2.9, zc), 70.0, ICE, shape=(1.2, 0.12))
    # outside: door trims, the readout, the status lamp, signs, the glow that leaks round the doors
    trims = bmesh.new()
    for d in GB.doors:
        if "freezer" in d["name"]:
            a0 = d["hinge"][0]
            door_frame(trims, "x", 3.0, a0, a0 + 1.2, G.DOOR_H, +1, wdt=0.1, d=0.04)
    finish("Freezer_Door_Trims", trims, "Steel_Galv")
    bm = bmesh.new()
    glowbm = bmesh.new()
    for k, d in enumerate([d for d in GB.doors if "freezer" in d["name"]], 1):
        xc = d["hinge"][0] + 0.6
        wall_sign(bm, f"COLD STORE {k}", (xc, 2.62, 3.012), "+z", 1.2, 0.15)
        panel(None, None, (xc + 0.95, 1.6, 3.012), "+z", 0.28, 0.07, rect_uv(*TEMP, e=2), bm=bm)
        box(glowbm, xc - 0.12, xc + 0.12, 2.32, 2.4, 3.0, 3.05)
        light("both", "AREA", (xc, 2.0, 3.25), 9.0, ICE, aim=(0, -0.6, 1), shape=(0.6, 0.5))
        light("both", "AREA", (xc, 0.05, 3.15), 5.0, ICE, aim=(0, 0.3, 1), shape=(1.1, 0.05))
    finish("Signs_Freezers", bm, "Signs", keep_uv=True, recalc=False)
    finish("Freezer_Status", glowbm, "Freezer_Glow")
    # strip curtains in the doorways, inside (passable)
    def strips(bm):
        for d in GB.doors:
            if "freezer" in d["name"]:
                a0 = d["hinge"][0]
                for j in range(6):
                    x = a0 + 0.02 + j * 0.2
                    box(bm, x, x + 0.19, 0.08, G.DOOR_H, 2.7, 2.705)
    part("decor_strip_curtains", "Steel_Galv", strips)


def bas_plant():
    """The plant room: two boilers (enamelled cases, flues), the chiller (fan grilles), the pump set on its plinth (pumps, valves, gauges), pipes
    on brackets under the soffit with drops to the plant, the breaker board (grey cabinets, one open), DANGER and PLANT ROOM signs, and a sump."""
    p = Painter()
    for n in ("Boiler", "Boiler_2"):
        b = BOX[n]
        x0, _, z0 = b["min"]
        x1, y1, z1 = b["max"]
        p.add("grey", box, x0, x1, 0.0, 0.12, z0, z1)
        p.add("boiler", box, x0 + 0.03, x1 - 0.03, 0.12, y1, z0 + 0.03, z1 - 0.03)
        p.add("grey_dark", box, x0 + 0.3, x1 - 0.3, 1.3, 1.7, z1 - 0.03, z1 - 0.02)
        p.add("red", box, x0 + 0.4, x0 + 0.5, 1.45, 1.55, z1 - 0.02, z1 - 0.015)
        p.add("grey", box, x0 + 0.3, x1 - 0.3, 0.3, 0.32, z1 - 0.03, z1 - 0.02)
        p.add("lagging", cyl, ((x0 + x1) / 2, y1, (z0 + z1) / 2), ((x0 + x1) / 2, H, (z0 + z1) / 2), 0.15, seg=12)
        p.add("pipe_red", cyl, (x1 - 0.3, y1, z1 - 0.3), (x1 - 0.3, H - 0.25, z1 - 0.3), 0.05, seg=8)
        p.add("pipe_blue", cyl, (x0 + 0.3, y1, z1 - 0.3), (x0 + 0.3, H - 0.4, z1 - 0.3), 0.05, seg=8)
    b = BOX["Chiller"]
    x0, _, z0 = b["min"]
    x1, y1, z1 = b["max"]
    p.add("grey", box, x0, x1, 0.0, 0.1, z0, z1)
    p.add("motor_grey", box, x0 + 0.05, x1 - 0.05, 0.1, y1, z0 + 0.05, z1 - 0.05)
    for fx in (x0 + 0.8, x0 + 2.3, x0 + 3.8):
        p.add("black", cyl, (fx, y1, (z0 + z1) / 2), (fx, y1 + 0.01, (z0 + z1) / 2), 0.55, seg=16)
    for k in range(6):
        p.add("grey_dark", box, x0 + 0.2, x1 - 0.2, 0.3 + k * 0.22, 0.34 + k * 0.22, z1 - 0.05, z1 - 0.04)
    p.add("pipe_blue", cyl, (x0 + 0.4, y1, z1 - 0.4), (x0 + 0.4, H - 0.6, z1 - 0.4), 0.07, seg=8)
    p.add("lagging", cyl, (x0 + 0.8, y1, z1 - 0.4), (x0 + 0.8, H - 0.5, z1 - 0.4), 0.09, seg=8)
    b = BOX["Pump_Set"]
    x0, _, z0 = b["min"]
    x1, y1, z1 = b["max"]
    p.add("grey", box, x0, x1, 0.0, 0.2, z0, z1)
    for k, px in enumerate((x0 + 0.6, x0 + 1.4, x0 + 2.2)):
        zc = (z0 + z1) / 2
        p.add("pump_blue", cyl, (px - 0.25, 0.45, zc), (px + 0.05, 0.45, zc), 0.18, seg=12)
        p.add("pump_blue", cyl, (px + 0.05, 0.45, zc), (px + 0.3, 0.45, zc), 0.13, seg=12)
        p.add("pump_blue", box, px - 0.22, px + 0.28, 0.2, 0.3, zc - 0.15, zc + 0.15)
        p.add("pipe_green", cyl, (px - 0.3, 0.45, zc), (px - 0.3, y1 - 0.05, zc), 0.06, seg=8)
        p.add("red", cyl, (px - 0.3, 0.8, zc - 0.1), (px - 0.3, 0.8, zc + 0.1), 0.07, seg=8)
        p.add("white", cyl, (px - 0.3, 0.95, zc - 0.08), (px - 0.3, 0.95, zc - 0.1), 0.04, seg=10)
    p.add("pipe_green", cyl, (x0 + 0.05, y1 - 0.05, (z0 + z1) / 2), (x1 - 0.05, y1 - 0.05, (z0 + z1) / 2), 0.07, seg=10)
    p.add("pipe_green", cyl, (x1 - 0.2, y1 - 0.05, (z0 + z1) / 2), (x1 - 0.2, H - 0.3, (z0 + z1) / 2), 0.07, seg=10)
    # the breaker board: three grey cabinets, the middle one open (its door swung to the wall)
    b = BOX["Electrical_Panels"]
    x0, _, z0 = b["min"]
    x1, y1, z1 = b["max"]
    p.add("grey", box, x0, x1, 0.0, y1, z0, z1)
    p.add("grey_dark", box, x0 - 0.002, x0, 0.0, y1, z0 + 0.86, z0 + 0.88)
    p.add("grey_dark", box, x0 - 0.002, x0, 0.0, y1, z0 + 1.72, z0 + 1.74)
    p.add("grey_dark", box, x0, X1, y1, H, z0 + 0.3, z0 + 0.6)                                # cable trunking up to the soffit
    p.done("Plant_Machines")
    bm = bmesh.new()
    panel(None, None, (x0 - 0.004, 1.15, (z0 + z1) / 2), "-x", 0.8, 1.6, rect_uv(*BREAKER, e=2), bm=bm)
    wall_sign(bm, "DANGER 415 V", (x0 - 0.004, 2.05, z0 + 0.4), "-x", 0.6, 0.075)
    wall_sign(bm, "PLANT ROOM", (28.0 - 0.012, 2.45, 0.5), "-x", 0.9, 0.11)
    wall_sign(bm, "NO SMOKING", (28.0 - 0.012, 1.6, 1.6), "-x", 0.6, 0.075)
    finish("Signs_Plant", bm, "Signs", keep_uv=True, recalc=False)
    # the sump: a pit cover (tread plate in a steel frame) with the pump's riser and its float switch box on the wall (passable art)
    part("decor_sump_cover", "Floor_Plate", lambda bm: box(bm, 38.4, 39.4, 0.0, 0.012, 2.05, 2.85))
    part("decor_sump_frame", "Hazard", lambda bm: (box(bm, 38.3, 39.5, 0.0, 0.01, 1.95, 2.05), box(bm, 38.3, 38.4, 0.0, 0.01, 2.05, 2.95),
                                                  box(bm, 39.4, 39.5, 0.0, 0.01, 2.05, 2.95)))
    p = Painter()
    p.add("pipe_blue", cyl, (39.2, 0.0, 2.92), (39.2, H - 0.3, 2.92), 0.04, seg=8)
    p.add("grey", box, 38.5, 38.8, 1.0, 1.35, 2.9, 3.0)
    p.add("red", box, 38.6, 38.7, 1.2, 1.26, 2.89, 2.9)
    p.done("decor_sump_riser")


def bas_pallets():
    rng = np.random.default_rng(505)
    pal, loads, wraps = [], [], []
    for b in COLS:
        if b["name"].startswith("Pallet"):
            a, l, w = pallet_stack(b["name"], b, rng, along="z", empty_stack=b["max"][1] < 0.7)
            pal += a
            loads += l
            wraps += w
    make_loads("Store", pal, loads, wraps)


def bas_stairs():
    """The stairwell: concrete steps with yellow nosings (each step its own tread and riser, both under 0.2 m tall: the colliders start in the
    air), a sloping soffit under the flight, the landing at y 4, its rail, a handrail on the wall, a bulb and an emergency light."""
    rise = G.BOH_Y / 15
    st = G.STAIR
    for b in COLS:
        n = b["name"]
        if n.startswith("Step_stairs_up_"):
            x0, y0, z0 = b["min"]
            x1, y1, z1 = b["max"]
            ym = (y0 + y1) / 2
            part(f"Stair_{n[-2:]}_Riser", "Floor_Concrete", lambda bm, b=b, ym=ym: cube(bm, b["min"], (b["max"][0], ym, b["max"][2])))
            part(f"Stair_{n[-2:]}_Tread", "Floor_Concrete", lambda bm, b=b, ym=ym: cube(bm, (b["min"][0], ym, b["min"][2]), b["max"]))
            part(f"Stair_{n[-2:]}_Nosing", "Steel_Yellow", lambda bm, b=b: box(bm, b["min"][0], b["max"][0], b["max"][1] - 0.02, b["max"][1] + 0.003, b["min"][2], b["min"][2] + 0.05))
    # the soffit under the flight (passable art: it is in the air)
    def soffit(bm):
        za, zb = st["foot"], st["top"]
        quad(bm, (st["x0"], 0.0, za), (34.0, 0.0, za), (34.0, G.BOH_Y - 0.3, zb), (st["x0"], G.BOH_Y - 0.3, zb))
    part("decor_stair_soffit", "Floor_Concrete", soffit, recalc=False)
    part("decor_stair_stringer", "Floor_Concrete", lambda bm: [box(bm, 33.95, 34.05, rise * i - 0.25, rise * (i + 1), st["foot"] - 0.28 * (i + 1), st["foot"] - 0.28 * i) for i in range(15)])
    b = BOX["Stair_Landing"]
    plain("Stair_Landing_Slab", b, "Floor_Concrete")
    r = BOX["Stair_Rail"]
    rx0, ry0, rz0 = r["min"]
    rx1, ry1, rz1 = r["max"]
    p = Painter()
    zc = (rz0 + rz1) / 2
    p.add("yellow", cyl, (rx0, ry1 - 0.03, zc), (rx1, ry1 - 0.03, zc), 0.03, seg=8)
    p.add("yellow", cyl, (rx0, ry0 + 0.5, zc), (rx1, ry0 + 0.5, zc), 0.02, seg=8)
    for x in np.linspace(rx0 + 0.04, rx1 - 0.04, 4):
        p.add("yellow", cyl, (x, ry0, zc), (x, ry1, zc), 0.025, seg=8)
    p.add("grey", box, rx0, rx1, ry0, ry0 + 0.1, rz0, rz1)
    p.done("Stair_Rail_Art")
    p = Painter()                                                                            # the handrail on the west wall, along the flight
    xh = st["x0"] + 0.06
    p.add("yellow", cyl, (xh, 0.9, st["foot"] + 0.3), (xh, G.BOH_Y + 0.9, st["top"]), 0.022, seg=8)
    for i in range(0, 15, 4):
        zb_ = st["foot"] - 0.28 * i
        p.add("grey_dark", box, st["x0"], xh, rise * i + 0.85, rise * i + 0.9, zb_ - 0.02, zb_ + 0.02)
    p.done("decor_handrail")
    fp = fittings()
    bulb(fp, 34.9, 6.2, 9.4, 7.0, w=30.0)
    bulb(fp, 34.9, 2.9, 13.6, H, w=25.0)
    make_fittings(fp, "Stairs")
    exit_sign((34.1, G.BOH_Y + 2.45, G.ROOMS_Z + T), "+z")
    emergency((st["x1"], G.BOH_Y + 2.6, 9.6), "-x")
    emergency((32.2, 2.85, 14.0), "-x")


def build_basement():
    bas_shell()
    bas_freezers()
    bas_plant()
    bas_pallets()
    bas_stairs()
    boh_lift()
    # the plant room's door frame, the stairwell foot's frame, the lift's call panel
    def frames(bm):
        door_frame(bm, "z", 28.0, 0.0, 1.0, G.DOOR_H, -1)
        door_frame(bm, "z", 28.2, 0.0, 1.0, G.DOOR_H, +1)
        door_frame(bm, "z", 32.2, 13.2, 14.8, G.DOOR_H, -1)
    part("Door_Frames", "Paint_Palette", lambda bm: (lambda old: (frames(bm), pt_uv(bm, old, pal_uv("grey_dark"))))(set(bm.faces)), keep_uv=True)
    p = Painter()
    p.add("steel", box, 40.75, 40.95, 1.05, 1.4, G.LIFT["z0"] - 0.03, G.LIFT["z0"])
    p.add("white", box, 40.82, 40.88, 1.25, 1.31, G.LIFT["z0"] - 0.04, G.LIFT["z0"] - 0.03)
    p.done("Lift_Call")
    # the day's light: battens along the corridor and in the plant room, bulbs over the pallets
    fp = fittings()
    for x in np.arange(14.5, 42.0, 3.4):
        if not (31.5 < x < 37.0):
            batten(fp, (x, H - 0.3, 5.0), 1.5, "x", top=H, w=50.0)
    for x in (30.5, 34.0, 37.5, 41.0):
        for z in (-1.0, 1.6):
            batten(fp, (x, H - 0.3, z), 1.5, "x", top=H, w=50.0)
    for x, z in ((14.8, 9.5), (17.5, 12.5), (21.2, 10.0), (25.5, 12.0), (28.8, 9.5), (25.0, 14.2), (14.5, 14.0)):
        bulb(fp, x, 2.7, z, H, w=40.0)
    make_fittings(fp, "Basement")
    for pos, n in (((X0, 2.8, 5.0), "+x"), ((30.0, 2.9, 3.2), "+z"), ((37.1, 2.9, G.LIFT["z0"]), "-z"),
                   ((28.0, 2.6, 2.0), "-x"), ((X1, 2.8, 5.0), "-x"), ((22.0, 2.8, Z1), "-z"), ((40.5, 2.9, 3.2), "+z")):
        emergency(pos, n)
    exit_sign((32.2, 2.45, 14.0), "-x")


# ---------------------------------------------------------------- the layout objects
def build_layout():
    """The layout objects, as the greybox names them: COL_ boxes and Zone_ boxes (hidden), the empties (Link_, Arrive_, Marker_, Spot_, SecCam_)."""
    for b in GB.boxes:
        if not b["col"] and not b.get("zone"):
            continue
        nm = ("COL_" + b["name"]) if b["col"] else b["name"]
        me = bpy.data.meshes.new(nm)
        bm = bmesh.new()
        cube(bm, b["min"], b["max"])
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(nm, me)
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
def add_lights():
    cols = {}
    for name in ("Lights_Day", "Lights_Night", "Lights_Both"):
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        cols[name] = c
    for i, L in enumerate(LIGHTS):
        d = bpy.data.lights.new(f"L{i:03d}", L["kind"])
        d.energy, d.color = L["w"], L["color"]
        if L["kind"] == "AREA":
            d.shape = "RECTANGLE"
            d.size, d.size_y = L["shape"] or (0.3, 0.3)
        else:
            d.shadow_soft_size = L["size"]
        if L["kind"] == "SPOT":
            d.spot_size, d.spot_blend = math.radians(L["cone"]), 0.5
        ob = bpy.data.objects.new(f"L{i:03d}_{L['sets']}", d)
        ob.location = B(L["pos"])
        if L["kind"] in ("SPOT", "AREA"):
            ob.rotation_euler = B(L["aim"]).to_track_quat("-Z", "Y").to_euler()
        cols["Lights_" + L["sets"].capitalize()].objects.link(ob)


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("World")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
    bg.inputs["Strength"].default_value = 0.0


def set_emit(mname, strength):
    m = bpy.data.materials.get(mname)
    if m:
        m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = strength


def apply_light_set(name):
    """day: the fluorescents and bulbs (Lamp_Emit on), the steady glows; night: abandoned: the emergency lights (Emergency_Emit on) and the steady
    glows only; export: both toggled materials at the strength the page switches on."""
    day = name != "night"
    for c, on in (("Lights_Day", day), ("Lights_Night", not day), ("Lights_Both", True)):
        if c in bpy.data.collections:
            bpy.data.collections[c].hide_render = not on
    set_emit("Lamp_Emit", LAMP_EMIT if name in ("day", "export") else 0.0)
    set_emit("Emergency_Emit", EMERG_EMIT if name in ("night", "export") else 0.0)


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


def split_for_layout():
    """The layout check reads each art object's box: an object standing on the floor must lie over a collider. Objects that gather pieces from
    several colliders are cut into one object per collider (and one for the pieces overhead, one for those on the floor)."""
    stand = [c for c in COLS if c["max"][1] > 0.2 and c["min"][1] < 0.5]
    g = 0.045

    def inplan(c, lo, hi):
        return c["min"][0] - g <= lo[0] and hi[0] <= c["max"][0] + g and c["min"][2] - g <= lo[2] and hi[2] <= c["max"][2] + g

    def stands(lo, hi):
        return (hi[1] - max(lo[1], 0.0)) > 0.2 and lo[1] < 1.8
    n_split = 0
    for ob in list(ART.objects):
        if ob.name.startswith("decor_") or not ob.data.vertices:
            continue
        vs = [(v.co.x, v.co.z, -v.co.y) for v in ob.data.vertices]
        lo = [min(v[i] for v in vs) for i in range(3)]
        hi = [max(v[i] for v in vs) for i in range(3)]
        if not stands(lo, hi) or any(inplan(c, lo, hi) for c in stand):
            continue
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.verts.index_update()
        parent = list(range(len(bm.verts)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for e in bm.edges:
            a, b = find(e.verts[0].index), find(e.verts[1].index)
            if a != b:
                parent[a] = b
        lay = bm.faces.layers.int.new("grp")               # (a new layer moves the faces: make it before holding any)
        comps = {}
        for f in bm.faces:
            comps.setdefault(find(f.verts[0].index), []).append(f)
        keys = {}
        for root, faces in comps.items():
            pts = [(v.co.x, v.co.z, -v.co.y) for f in faces for v in f.verts]
            plo = [min(p[i] for p in pts) for i in range(3)]
            phi = [max(p[i] for p in pts) for i in range(3)]
            if plo[1] >= 1.8:
                k = "high"
            elif phi[1] <= 0.2:
                k = "low"
            else:
                cs = [c for c in stand if inplan(c, plo, phi)]               # the smallest collider that holds it (a shelf before the wall behind it)
                c = min(cs, key=lambda c: (c["max"][0] - c["min"][0]) * (c["max"][2] - c["min"][2])) if cs else None
                k = c["name"] if c else f"free{root}"
            gid = keys.setdefault(k, len(keys))
            for f in faces:
                f[lay] = gid
        if len(keys) == 1:
            bm.free()
            continue
        mat = ob.data.materials[0]
        coll = ob.users_collection[0]
        for k, gid in keys.items():
            t = bm.copy()
            tl = t.faces.layers.int["grp"]
            bmesh.ops.delete(t, geom=[f for f in t.faces if f[tl] != gid], context="FACES")
            t.faces.layers.int.remove(tl)
            me = bpy.data.meshes.new(f"{ob.name}__{k}")
            t.to_mesh(me)
            t.free()
            me.materials.append(mat)
            nob = bpy.data.objects.new(me.name, me)
            coll.objects.link(nob)
        bm.free()
        bpy.data.objects.remove(ob)
        n_split += 1
    print("SPLIT", n_split, "objects cut by collider")


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
    EMERG_UNITS.clear()
    EXITS.clear()
    sc = bpy.context.scene
    ART, STANDIN, DOORS_C, LAYOUT_C = (bpy.data.collections.new(n) for n in ("Art", "Standins", "Doors", "Layout"))
    for c in (ART, STANDIN, DOORS_C, LAYOUT_C):
        sc.collection.children.link(c)
    make_materials(make_generated())
    if BOH:
        build_back_of_house()
    else:
        build_basement()
    make_emergency()
    make_exits()
    cam_mounts()
    split_for_layout()
    build_door_leaves()
    build_layout()
    add_lights()
    setup_world()
    apply_light_set("day")
    ensure_marker()
    LAYOUT_C.hide_render = True
    for o in list(ART.objects) + list(DOORS_C.objects):     # the glowing parts cast no shadow: a lamp's light starts at its lens
        if o.data.materials and o.data.materials[0].name in EMISSIVE:
            o.visible_shadow = False
    tris = sum(len(p.vertices) - 2 for o in ART.objects for p in o.data.polygons)
    print(f"ART {len(ART.objects)} objects, about {tris} triangles; {len(LIGHTS)} lights")


# ---------------------------------------------------------------- layout file and the layout check
def stage_layout():
    import export_scene
    export_scene.write(SCENE, ROOT / f"world/{SCENE}.json")


def stage_check():
    import check_layout
    code = check_layout.main(["--scene", SCENE, "--collection", "Art"])
    print("CHECK_LAYOUT exit", code)


# ---------------------------------------------------------------- bake
SHELL = ["Floor_Concrete", "Floor_Vinyl", "Floor_Frost", "Wall_Block", "Wall_Lower", "Wall_Band", "Ceiling_Soffit", "Ceiling_Tile", "Freezer_Panel", "Frost_Panel"]
PAGES = [2048, 2048]
NIGHT_OFFSET = 2
UV_SCALE = {"Ceiling_Soffit": 0.45, "Ceiling_Tile": 0.6, "Paint_Palette": 0.7, "Floor_Paint": 0.3, "Hazard": 0.8}
SEEN_UP = 1.7          # an up-facing face of a prop higher than this is never seen (the eye is at 1.55 m), except the stairs' and the landing's
CULL_UP = ("Carton_Load", "Wrap_Load", "Carton", "Pallet_Wood", "Steel_Blue", "Steel_Orange", "Steel_Galv", "Paint_Palette", "Steel_Grey", "Locker_Front",
           "Wood_Light", "Rubber_Black", "Shutter", "Hazard", "Signs")


def groups(exp):
    shell = [m for m in SHELL if m in exp]
    props = [m for m in exp if m not in SHELL and m not in EMISSIVE]
    return [shell, props]


def cull(bm, mname, oname):
    """Drop faces never seen: the shell's outer skin, the floor's sides and underside, the walls' tops and bottoms, the ceilings' tops, the bottoms
    of things standing on the floor, and (props) faces looking up from above head height."""
    e = 2e-3
    bad = []
    for f in bm.faces:
        c, n = f.calc_center_median(), f.normal
        gx, gy, gz = c.x, c.z, -c.y
        nx, ny, nz = n.x, n.z, -n.y
        out = (nx < -0.9 and gx <= X0 - T + e) or (nx > 0.9 and gx >= X1 + T - e) or (nz < -0.9 and gz <= Z0 - T + e) or (nz > 0.9 and gz >= Z1 + T - e)
        if oname.startswith("Floor_"):
            out = not (ny > 0.9 and abs(gy) < e)
        elif oname.startswith("Ceil_"):
            out = not ny < -0.9
        elif oname.startswith("Wall_"):
            out = out or ny > 0.9 or (ny < -0.9 and (gy < e or abs(gy - LOW) < e or abs(gy - BAND) < e))   # the bands' joints are inside the wall
        else:
            out = out or (ny < -0.9 and abs(gy) < e)
            out = out or (nx > 0.9 and gx >= X1 - e) or (nx < -0.9 and gx <= X0 + e) or (nz > 0.9 and gz >= Z1 - e) or (nz < -0.9 and gz <= Z0 + e)
            if mname in CULL_UP and not oname.startswith(("Stair", "Well_")):
                out = out or (ny > 0.5 and gy > SEEN_UP)
            if mname in ("Carton", "Carton_Load", "Wrap_Load"):
                out = out or ny < -0.9
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
        if not bm.faces:
            bm.free()
            continue
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


def fix_degenerate(objs):
    """Smart projection sometimes flattens a face to a line (no UV area): such a face is projected again on its own, flat along its normal, at
    the object's usual scale, so the island averaging and the packer never meet a zero-area island."""
    fixed = 0
    for o in objs:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        lay = bm.loops.layers.uv["lightmap"]
        ratios, bad = [], []
        for f in bm.faces:
            a3 = f.calc_area()
            uv = [lp[lay].uv for lp in f.loops]
            n = len(uv)
            au = abs(sum(uv[i][0] * uv[(i + 1) % n][1] - uv[(i + 1) % n][0] * uv[i][1] for i in range(n))) / 2
            if a3 > 1e-8:
                if au < 1e-12 or not math.isfinite(au):
                    bad.append(f)
                else:
                    ratios.append(au / a3)
        if bad:
            k = math.sqrt(float(np.median(ratios))) if ratios else 0.01
            for f in bad:
                nrm = f.normal
                ax = max(range(3), key=lambda i: abs(nrm[i]))
                for lp in f.loops:
                    c = lp.vert.co
                    u, v = ((c.y, c.z) if ax == 0 else (c.x, c.z) if ax == 1 else (c.x, c.y))
                    lp[lay].uv = (u * k, v * k)
            bm.to_mesh(o.data)
            fixed += len(bad)
        bm.free()
    print("  degenerate faces projected again:", fixed)


def lightmap_uv(objs, page):
    """One atlas for `objs`: smart-project islands at equal texel density (a few materials scaled down), packed with MARGIN_PX."""
    for o in objs:
        uvs = o.data.uv_layers
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.new(name="lightmap", do_init=False)
        uvs.active = uvs["lightmap"]
        uvs["lightmap"].active_render = True
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    fix_degenerate(objs)
    for o in objs:                  # smart projection fits each object to the unit square on its own: bring every object back to metres (Blender's
        d = o.data.uv_layers["lightmap"].data       # island averaging over this many objects broke the packer), times UV_SCALE
        k = math.sqrt(max(1e-12, area3d(o)) / max(1e-12, uv_area(o, "lightmap"))) * UV_SCALE.get(o.name, 1.0)
        us = np.array([x.uv for x in d]) * k
        d.foreach_set("uv", us.ravel())
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / page, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    plain_ = [o for o in objs if o.name not in UV_SCALE]
    a3 = sum(area3d(o) for o in plain_)
    au = sum(uv_area(o, "lightmap") for o in plain_)
    dens = page * math.sqrt(au / a3)
    small = {o.name: round(page * math.sqrt(uv_area(o, "lightmap") / max(1e-9, area3d(o))), 1) for o in objs if o.name in UV_SCALE}
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


def bake_set(n, objs, S, light_set, samples):
    apply_light_set(light_set)
    bpy.context.scene.cycles.samples = samples
    img = bpy.data.images.new(f"LM_{n}_{light_set}", S, S, alpha=False, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    for o in objs:
        for slot in o.material_slots:
            nt = slot.material.node_tree
            node = nt.nodes.new("ShaderNodeTexImage")
            node.name = "BAKE_TARGET"
            node.image = img
            nt.nodes.active = node
            node.select = True
    select_only(objs)
    for o in objs:
        o.data.uv_layers.active = o.data.uv_layers["lightmap"]
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
    for o in objs:
        for slot in o.material_slots:
            nt = slot.material.node_tree
            for nd in [nd for nd in nt.nodes if nd.name.startswith("BAKE_TARGET")]:
                nt.nodes.remove(nd)
    a = denoise_image(img, S)
    bpy.data.images.remove(img)
    return a[..., :3].copy()


# ---------------------------------------------------------------- brightness: how the page shows the maps
# The page draws a baked material unlit, with no tone mapping: texture x base colour x texel x intensity / pi. The bake's light L is written with a
# shoulder: texel = G L / (C + G L), and intensity = pi C, so the page shows texture x G L where the light is ordinary and rolls off toward
# texture x C under a lamp, never clipping. G is set per set from the shell map's median light so that a white wall at the median would show
# TARGET; the night's G is held to at most NIGHT_GAIN_CAP x the day's, so the night stays a night.
CURVE_C = {"day": 1.3, "night": 1.1}
TARGET = {"day": 0.9, "night": 0.25}
NIGHT_GAIN_CAP = 30.0
CAP = {"day": {}, "night": {}}


def stage_bake():
    import time
    stage_work()
    exp = make_export_objects()
    leaves = sorted(bpy.data.collections["Doors"].objects, key=lambda o: o.name)
    bpy.data.collections["Art"].hide_render = True
    bpy.data.collections["Art"].hide_viewport = True
    setup_cycles(SAMPLES, bake=True)
    for m in EMISSIVE:
        if m in exp:
            exp[m].visible_shadow = False
    report, gains = {}, {}
    for n, mats in enumerate(groups(exp)):
        objs = [exp[m] for m in mats] + (leaves if n == 1 else [])
        print(f"lightmap {n}: {[o.name for o in objs]}")
        S, dens, small = lightmap_uv(objs, PAGES[n])
        for light_set, idx, samples in (("day", n, SAMPLES), ("night", n + NIGHT_OFFSET, NIGHT_SAMPLES)):
            t0 = time.time()
            rgb = bake_set(n, objs, S, light_set, samples)
            peak = rgb.max(axis=2)
            sel = peak > 1e-6
            pc = np.percentile(peak[sel], [50, 90, 99, 99.5, 100]) if sel.any() else [1.0] * 5
            if light_set not in gains:
                g = TARGET[light_set] / max(1e-6, float(pc[0]))
                if light_set == "night" and "day" in gains:
                    g = min(g, NIGHT_GAIN_CAP * gains["day"])
                gains[light_set] = g
            G_, C = gains[light_set], CURVE_C[light_set]
            np.savez_compressed(stage_work() / f"{SCENE}_{idx}_raw.npz", rgb=rgb.astype(np.float16))
            tex = G_ * rgb / (C + G_ * rgb)
            out = np.ones((S, S, 4), np.float32)
            out[..., :3] = srgb_encode(tex)
            png = bpy.data.images.new(f"LM_{idx}_png", S, S, alpha=False)
            png.colorspace_settings.name = "Non-Color"
            png.pixels.foreach_set(out.ravel())
            png.filepath_raw = str(stage_work() / f"{SCENE}_{idx}.png")
            png.file_format = "PNG"
            png.save()
            bpy.data.images.remove(png)
            report[idx] = {"map": n, "set": light_set, "size": S, "G": round(G_, 4), "C": C, "px_per_m": round(dens, 1), "px_per_m_scaled": small,
                           "p50_p90_p99_p995_max": [round(float(v), 5) for v in pc], "samples": samples, "device": bpy.context.scene.cycles.device,
                           "seconds": round(time.time() - t0), "materials": mats + ([o.name for o in leaves] if n == 1 else [])}
            print("  baked", report[idx])
    (stage_work() / "lightmaps.json").write_text(json.dumps(report, indent=1))
    apply_light_set("day")
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Art"].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


def set_intensities():
    rep = json.loads((stage_work() / "lightmaps.json").read_text())
    for idx, r in rep.items():
        idx = int(idx)
        st = r["set"]
        key, kkey = ("lightmap", "lightmap_intensity") if st == "day" else ("lightmap_night", "lightmap_night_intensity")
        for nm in r["materials"]:
            ob = bpy.data.objects.get(nm)
            mats = [bpy.data.materials.get(nm)] if bpy.data.materials.get(nm) else [s.material for s in ob.material_slots] if ob else []
            for m in mats:
                if m is None or m.name in EMISSIVE:
                    continue
                m[key] = LM_URL.format(idx)
                m[kkey] = round(math.pi * r["C"] * CAP[st].get(m.name, 1.0), 4)


def scrub_ui_paths():
    for sc in bpy.data.screens:
        for a in sc.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"_" * 1000
                    sp.params.directory = b"//"


KEEP_PROPS = {"lightmap", "lightmap_intensity", "lightmap_night", "lightmap_night_intensity"}
LAYOUT_PREFIX = ("DoorLeaf_", "Spot_", "Marker_", "Link_", "Arrive_", "SecCam_", "Zone_")
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
        for pf in im.packed_files:
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
    wm = bpy.context.window_manager
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
    stash = {o.name: {k: o[k] for k in o.keys()} for o in leaves}        # the leaves' layout properties are in world/<scene>.json, not in the GLB
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


def shots():
    a, f = ARRIVE["pos"], ARRIVE["face"]
    s = {"1_arrival": (("arrival", (a[0], 1.6, a[2]), (a[0] + f[0] * 3, 1.6, a[2] + f[1] * 3), 75.0))}
    if BOH:
        s.update({"2_wide": ("wide", (13.0, 3.2, 6.4), (36.0, 0.6, -5.5), 80.0),
                  "3_detail": ("detail", (38.0, 1.6, 7.4), (40.3, 1.35, 10.2), 64.0),
                  "4_office": ("office", (26.0, 1.65, 8.0), (29.4, 1.35, 13.4), 72.0),
                  "5_break": ("break", (19.4, 1.65, 8.0), (13.6, 1.0, 12.6), 72.0),
                  "6_dock": ("dock", (33.0, 1.65, 5.6), (42.0, 1.2, -3.0), 72.0)})
    else:
        s.update({"2_wide": ("wide", (12.9, 2.6, 14.4), (34.0, 0.6, 1.5), 80.0),
                  "3_detail": ("detail", (20.6, 1.6, 7.2), (18.0, 1.2, 2.9), 70.0),
                  "4_plant": ("plant", (29.0, 1.65, 2.5), (38.5, 0.9, -3.0), 72.0),
                  "5_stairs": ("stairs", (34.9, 1.6, 14.5), (33.0, 2.6, 9.4), 72.0),
                  "6_pallets": ("pallets", (26.5, 1.65, 5.0), (15.0, 0.8, 12.5), 72.0)})
    return s


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
    expo = arg("--exposure", 0.0 if light_set == "day" else 1.5, float)
    which = arg("--only", "all")
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    cams = {k: look_cam(*v) for k, v in shots().items()}
    plan = look_cam("plan", ((X0 + X1) / 2, 30.0, (Z0 + Z1) / 2), None, ortho=(X1 - X0) * 1.04)
    plan.rotation_euler = (0, 0, 0)
    arts = list(bpy.data.collections["Art"].objects) + list(bpy.data.collections["Doors"].objects)

    def gmin_y(o):
        return min((o.matrix_world @ Vector(c)).z for c in o.bound_box)
    cut_plan = [o for o in arts if gmin_y(o) > 2.3 or o.name.startswith(("Ceil_", "Car_Ceiling", "Wall_Bulkhead"))]
    todo = [(k, v, (1920, 1080)) for k, v in cams.items()] + [("7_plan", plan, (1800, int(1800 * (Z1 - Z0) / (X1 - X0))))]
    suffix = "" if light_set == "day" else "_" + light_set
    for key, cam, (w, h) in todo:
        if which not in ("all", key) and not (which == "review" and key in ("1_arrival", "2_wide", "3_detail")):
            continue
        sc.camera = cam
        sc.view_settings.exposure = expo + (0.6 if key == "7_plan" else 0.0)
        for o in arts:
            o.visible_camera = True
        if key == "7_plan":
            for o in cut_plan:
                o.visible_camera = False
            if light_set == "day":
                bpy.data.collections["Lights_Day"].hide_render = False
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
    ST = set(STAGE.split(","))                         # several stages in one run: --stage art,bake,export
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
