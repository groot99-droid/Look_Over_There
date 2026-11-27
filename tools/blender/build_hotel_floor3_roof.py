"""Dresses and lights two hotel scenes (docs/BLENDER_AREAS.md section 1): floor 3, the apartments (`floor_3`), and the roof (`roof`), bakes each at
night and exports world/<scene>.glb and world/<scene>.json.

Re-runnable, from the repo root (one scene a run):

    blender -b --factory-startup --python tools/blender/build_hotel_floor3_roof.py -- --scene floor_3 --stage art     (the art, the layout objects
                                                                                    and the kit; saves blender/scenes/floor_3.blend; then layout, check)
    blender -b blender/scenes/floor_3.blend --python tools/blender/build_hotel_floor3_roof.py -- --scene floor_3 --stage layout   (world/floor_3.json)
    blender -b blender/scenes/floor_3.blend --python tools/blender/build_hotel_floor3_roof.py -- --scene floor_3 --stage check    (the layout check)
    blender -b blender/scenes/floor_3.blend --python tools/blender/build_hotel_floor3_roof.py -- --scene floor_3 --stage bake [--samples 768]
    blender -b blender/scenes/floor_3.blend --python tools/blender/build_hotel_floor3_roof.py -- --scene floor_3 --stage export
    blender -b blender/scenes/floor_3.blend --python tools/blender/build_hotel_floor3_roof.py -- --scene floor_3 --stage render [--render-samples 128]
    python tools/blender/build_hotel_floor3_roof.py --scene floor_3 --stage encode --work work/floor_3   (the raw bake -> lightmap PNGs, no Blender)
    python tools/blender/pack_scene.py floor_3 --work work/floor_3                                       (WebP lightmaps and textures -> world/)

The same for `--scene roof`. The layout is the greybox's: tools/blender/build_hotel_greybox.py (`floor_3` and `roof()`, imported here, so no
coordinate of the layout is typed in) gives every collider, door, link, marker and spot. The connector kit (blender/kit/README.md) is placed with
tools/blender/kit_place.py: on floor 3 the elevator at (-20, 0, 0), yaw 90, and the stair door at the two stair doors; on the roof the stair door at
the bulkhead and the safe house at (-8, 0, -5.8), yaw 0. Its layout objects are the ones the greybox model lists; its art is appended as stand-ins
(the Kit collection: in the bake, the layout check and the stills, never in this scene's GLB: the page draws world/kit/<piece>.glb).

floor_3: a quiet, well-kept apartment corridor at night. A wine runner on an oak floor, a painted wainscot under faded paper, a plaster ceiling with a
cornice, ten numbered doors with brass numbers, mail slots, peepholes and welcome mats, two-arm sconces (Lamp_Emit), framed prints, radiators, an exit
sign over the stair door, and the stairwell up to the roof. Baked at night: the sconces and the stairwell's lamps.
roof: a flat roof at night, 24 m square: gravel ballast with tar patches and a paver path, a brick parapet with a concrete coping, the stair bulkhead
with the kit's stair door, a timber water tank on a steel stand, two HVAC units, antennas with a red beacon, wall-pack lamps. Lit by the moon and the
city's glow; the safe house's outside walls (`SH_Outside`) are this scene's own, a skin 1 cm outside the kit's, lit by this bake.
"""
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

try:
    import bpy
    import bmesh
    from mathutils import Matrix, Vector
except ImportError:                       # the encode stage runs in plain Python (numpy and Pillow)
    bpy = None

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import build_hotel_greybox as G          # noqa: E402  the layout model (pure Python)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


SCENE = arg("--scene", "floor_3")
assert SCENE in ("floor_3", "roof"), SCENE
STAGE = arg("--stage", "art")
SAMPLES = arg("--samples", 768, int)
DEVICE = arg("--device", "auto")
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"
MARGIN_PX = 8
T = G.T


def stage_work():
    d = Path(arg("--work", str(ROOT / f"work/{SCENE}")))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- brightness: how the page shows the maps
# The page draws a baked material unlit, with no tone mapping: texture x base colour x texel x intensity / pi. The bake's light L (Cycles' diffuse
# pass, without colour) is written with a shoulder: texel = G L / (C + G L), and intensity = pi C, so the page shows texture x G L where the light is
# ordinary and rolls off toward texture x C beside a lamp, never clipping. G lifts the whole set (the encode stage re-writes the PNGs from the raw
# bake, so G can be tuned without baking again); C and CAP (one material's factor) are in the GLB.
CURVE = {"floor_3": (26.0, 1.5), "roof": (50.0, 1.5)}
CAP = {"floor_3": {"Signs": 0.7, "Paint_Palette": 0.75, "Brass": 0.7, "Prints": 0.85}, "roof": {}}


def srgb_encode(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def encode(rgb, scene):
    G_, C_ = CURVE[scene]
    return srgb_encode(G_ * rgb / (C_ + G_ * rgb))


def stage_encode():
    """The raw bakes (<work>/<scene>_<n>_raw.npy, rows bottom to top) -> <work>/<scene>_<n>.png with the curve above; plain Python."""
    from PIL import Image
    w = stage_work()
    G_ = arg("--gain", None, float)
    if G_ is not None:
        CURVE[SCENE] = (G_, CURVE[SCENE][1])
    for f in sorted(w.glob(f"{SCENE}_[0-9]_raw.npy")):
        n = f.name.split("_")[-2]
        rgb = np.load(f).astype(np.float32)
        out = (encode(rgb, SCENE) * 255 + 0.5).astype(np.uint8)
        Image.fromarray(np.flipud(out)).save(w / f"{SCENE}_{n}.png")
        print("ENCODED", f"{SCENE}_{n}.png", rgb.shape, "curve", CURVE[SCENE])


if bpy is None:
    if STAGE == "encode":
        stage_encode()
    else:
        print("without Blender only --stage encode runs")
    sys.exit(0)


# ================================================================ Blender from here on
GB = G.build(SCENE)
BOX = {b["name"]: b for b in GB.boxes}
DOORS = {d["name"]: d for d in GB.doors}
GB_EMPTIES = {e["name"]: e for e in GB.empties}


def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


# ---------------------------------------------------------------- materials
IMG_CACHE, MATS, TILES = {}, {}, {}


def image(fn, srgb=True):
    key = (fn, srgb)
    if key not in IMG_CACHE:
        im = bpy.data.images.load(str(ROOT / fn))
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


LAMP_EMIT = 6.0           # Lamp_Emit's exported strength: every lamp's glow (shades, lenses); the page switches it; on in the bake
EMITS = ("Lamp_Emit", "Exit_Emit", "Beacon_Emit")
TEXA = "blender/textures/apartment/"
TEXK = "blender/textures/kit/"
TEXG = "blender/textures/galleries/"
TEXF = "blender/textures/factory_floor/"


def make_materials(gen):
    if SCENE == "floor_3":
        material("Floor_Oak", diff=TEXA + "old_wood_floor_diff_1k.jpg", tint=(0.78, 0.66, 0.52), rough=0.5, tile=1.6)
        material("Floor_Runner", img=gen["runner"], rough=1.0, tile=1.3)
        material("Wall_Paper", img=gen["paper"], rough=0.9, tile=0.8)
        material("Wall_Wainscot", diff=TEXG + "plastered_wall_04_diff_1k.jpg", tint=(0.66, 0.70, 0.62), rough=0.6, tile=2.0)  # sage gloss paint
        material("Ceiling_Plaster", diff=TEXG + "plastered_wall_04_diff_1k.jpg", tint=(0.93, 0.91, 0.86), rough=0.95, tile=2.5)
        material("Trim_Paint", diff=TEXG + "plastered_wall_04_diff_1k.jpg", tint=(0.88, 0.85, 0.77), rough=0.55, tile=1.5)    # cream gloss: rails, casings
        material("Stair_Wall", diff=TEXA + "beige_wall_001_diff_1k.jpg", tint=(0.92, 0.90, 0.84), rough=0.9, tile=2.0)
        material("Stair_Concrete", diff=TEXK + "concrete_floor_02_diff_1k.jpg", tint=(0.78, 0.76, 0.72), rough=0.85, tile=1.5)
        material("Steel_Paint", diff=TEXK + "painted_metal_shutter_diff_1k.jpg", tint=(0.50, 0.56, 0.52), rough=0.5, tile=1.0)
        material("Radiator_Paint", diff=TEXK + "painted_metal_shutter_diff_1k.jpg", tint=(0.92, 0.90, 0.84), rough=0.45, tile=0.6)
        material("Brass", color=(0.62, 0.46, 0.20), rough=0.35, metal=0.9)
        material("Metal_Dark", color=(0.05, 0.05, 0.05), rough=0.5, metal=0.6)
        material("Doors", img=gen["doors"], rough=0.5, tile=1.0)
        material("Prints", img=gen["prints"], rough=0.4, tile=1.0)
        material("Frame_Wood", diff=TEXA + "dark_wood_diff_1k.jpg", tint=(0.80, 0.70, 0.60), rough=0.45, tile=0.5)
        material("Paint_Palette", img=gen["palette"], rough=0.8, tile=1.0)
        material("Signs", img=gen["signs"], rough=0.5, tile=1.0)
        material("Exit_Emit", img=gen["signs"], rough=0.4, emit=((0.30, 1.0, 0.45), 2.0))
        material("Lamp_Emit", color=(1.0, 0.93, 0.80), rough=0.5, emit=((1.0, 0.80, 0.56), LAMP_EMIT))
    else:
        material("Roof_Gravel", img=gen["gravel"], rough=1.0, tile=1.2)
        material("Roof_Tar", img=gen["tar"], rough=0.5, tile=2.0)
        material("Roof_Pavers", img=gen["pavers"], tint=(0.80, 0.79, 0.77), rough=0.9, tile=1.2)
        material("Brick", diff=TEXF + "brick_diff.jpg", tint=(0.86, 0.74, 0.66), rough=0.9, tile=2.0)
        material("Coping", diff=TEXK + "concrete_floor_02_diff_1k.jpg", tint=(0.82, 0.80, 0.76), rough=0.85, tile=1.2)
        material("Render_Paint", diff=TEXK + "plastered_wall_04_diff_1k.jpg", tint=(0.70, 0.70, 0.66), rough=0.9, tile=2.0)
        material("SH_Outside", diff=TEXK + "plastered_wall_04_diff_1k.jpg", tint=(0.58, 0.60, 0.56), rough=0.9, tile=2.2)   # the kit's, lit here
        material("Steel_Paint", diff=TEXK + "painted_metal_shutter_diff_1k.jpg", tint=(0.52, 0.56, 0.54), rough=0.5, tile=1.0)
        material("Steel_Galv", diff=TEXK + "painted_metal_shutter_diff_1k.jpg", tint=(0.66, 0.68, 0.68), rough=0.45, metal=0.3, tile=1.5)
        material("HVAC_Sheet", diff=TEXF + "roof_sheet_diff.jpg", tint=(0.78, 0.78, 0.74), rough=0.5, metal=0.2, tile=1.2)
        material("Tank_Wood", diff=TEXA + "dark_wood_diff_1k.jpg", tint=(1.05, 0.98, 0.90), rough=0.8, tile=1.4)
        material("Iron_Black", color=(0.06, 0.06, 0.06), rough=0.55, metal=0.5)
        material("Metal_Dark", color=(0.10, 0.10, 0.11), rough=0.45, metal=0.6)
        material("Doors", img=gen["doors"], rough=0.5, tile=1.0)
        material("Signs", img=gen["signs"], rough=0.5, tile=1.0)
        material("Stair_Wall", diff=TEXK + "beige_wall_001_diff_1k.jpg", tint=(0.86, 0.84, 0.78), rough=0.9, tile=2.0)
        material("Stair_Concrete", diff=TEXK + "concrete_floor_02_diff_1k.jpg", tint=(0.74, 0.72, 0.68), rough=0.85, tile=1.5)
        material("Lamp_Emit", color=(1.0, 0.93, 0.80), rough=0.5, emit=((1.0, 0.74, 0.46), LAMP_EMIT))
        material("Beacon_Emit", color=(1.0, 0.1, 0.08), rough=0.4, emit=((1.0, 0.06, 0.04), 8.0))


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


ART = KIT_C = DOORS_C = LAYOUT_C = None


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
    if mat in EMITS:
        ob.visible_shadow = False
    return ob


def part(name, mat, build, **kw):
    bm = bmesh.new()
    build(bm)
    if not bm.faces:
        bm.free()
        return None
    return finish(name, bm, mat, **kw)


def set_uv_rect(bm, faces, rect, axes):
    """Planar UV for `faces` over a game-space rectangle: axes = (iu, iv) game axis indices; rect = (u0, v0, u1, v1) in metres -> 0..1."""
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    u0, v0, u1, v1 = rect
    for f in faces:
        for lp in f.loops:
            p = lp.vert.co
            g = (p.x, p.z, -p.y)
            lp[uvl].uv = ((g[axes[0]] - u0) / (u1 - u0), (g[axes[1]] - v0) / (v1 - v0))


def panel(name, mat, centre, normal, w, h, uv=(0, 0, 1, 1), coll=None, bm=None):
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


# the palette: 8 x 8 flat swatches in one small image; a piece of a palette object takes one swatch (all its UVs at the swatch's centre)
PAL = {
    "mat_brown": (0.20, 0.13, 0.08), "mat_green": (0.10, 0.18, 0.12), "mat_red": (0.32, 0.08, 0.07), "mat_grey": (0.22, 0.21, 0.20),
    "mat_blue": (0.10, 0.13, 0.24), "mat_tan": (0.45, 0.36, 0.24), "coir": (0.52, 0.38, 0.20), "rubber": (0.06, 0.06, 0.06),
    "phone_black": (0.03, 0.03, 0.03), "paper": (0.86, 0.84, 0.78), "plant": (0.10, 0.24, 0.08), "pot": (0.48, 0.24, 0.14),
    "smoke": (0.92, 0.92, 0.90), "mirror": (0.55, 0.60, 0.62), "valve": (0.55, 0.12, 0.10), "white": (0.90, 0.90, 0.88),
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


# ---------------------------------------------------------------- generated pictures (numpy, own work, fixed seeds)
GLYPHS = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"], "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"], "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"], "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"], "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"], "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"], "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"], "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"], "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"], "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"], "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"], "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"], " ": ["00000"] * 7,
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"], ">": ["01000", "00100", "00010", "00001", "00010", "00100", "01000"],
    "<": ["00010", "00100", "01000", "10000", "01000", "00100", "00010"], ".": ["00000"] * 6 + ["00100"],
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


def text_mask(text, h, w, fill=0.62, maxw=0.9):
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
    return np.clip((blur(m, k, 2) - 0.5) * 4 + 0.5, 0, 1)


def sign_board(text, h, w, bg, fg, rng, fill=0.5, border=None, maxw=0.86):
    row = np.zeros((h, w, 3), np.float32)
    row[:] = bg
    m = text_mask(text, h, w, fill=fill, maxw=maxw)
    row = row * (1 - m[..., None]) + np.array(fg) * m[..., None]
    row = row * (0.92 + 0.12 * vnoise(h, w, rng, 4, 6)[..., None])
    if border is not None:
        row[:4] = row[-4:] = row[:, :4] = row[:, -4:] = border
    return row


def palette_pixels():
    img = np.zeros((128, 128, 3), np.float32)
    for i, k in enumerate(PAL_KEYS):
        r, c = i // 8, i % 8
        img[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16] = PAL[k]
    return img


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


# ================================================================ floor 3: the pictures
def runner_pixels():
    """The runner: a wine-red field, a cream-and-gold border band near each edge with a thin black line, and a small dark medallion every half
    repeat. v runs across the runner (one image is its whole 1.3 m width), u along it (one repeat is 1.3 m; it tiles along u)."""
    S = 1024
    rng = np.random.default_rng(301)
    vv, uu = (np.mgrid[0:S, 0:S] + 0.5) / S                    # rows = v (across), cols = u (along)
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.34, 0.06, 0.07)
    e = np.minimum(vv, 1 - vv)                                   # distance from the nearer edge (0..0.5)
    img[e < 0.075] = (0.20, 0.05, 0.05)
    img[(e > 0.03) & (e < 0.065)] = (0.72, 0.58, 0.32)
    img[(e > 0.042) & (e < 0.052)] = (0.30, 0.08, 0.07)
    img[(e > 0.083) & (e < 0.09)] = (0.06, 0.04, 0.04)
    fu = (uu * 2) % 1.0
    cu, cv = fu - 0.5, (vv - 0.5) * 1.6
    d = np.abs(cu) + np.abs(cv)
    img[(d < 0.20) & (e > 0.1)] = (0.22, 0.05, 0.06)
    img[(np.abs(d - 0.20) < 0.012) & (e > 0.1)] = (0.64, 0.50, 0.28)
    img[np.sqrt(cu ** 2 + cv ** 2) < 0.035] = (0.70, 0.56, 0.30)
    n = vnoise(S, S, rng, 6, 4, wrap=True)
    pile = vnoise(S, S, rng, 2, 128, wrap=True)
    img = img * (0.84 + 0.24 * n[..., None]) * (0.93 + 0.09 * pile[..., None])
    return np.clip(img, 0, 1).astype(np.float32)


def paper_pixels():
    """Faded paper above the wainscot: a dusty grey-blue ground, thin cream stripes in pairs and a small cream sprig between them. Repeat 0.8 m."""
    S = 1024
    rng = np.random.default_rng(303)
    yy, xx = (np.mgrid[0:S, 0:S] + 0.5) / S
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.50, 0.55, 0.58)
    fx = (xx * 4) % 1.0
    img[(np.abs(fx - 0.04) < 0.012) | (np.abs(fx - 0.10) < 0.006)] = (0.78, 0.76, 0.66)
    cx, cy = fx - 0.55, ((yy * 5) % 1.0) - 0.5
    r = np.sqrt((cx * 2.2) ** 2 + cy ** 2)
    th = np.arctan2(cy, cx)
    sprig = (r < 0.16 + 0.05 * np.cos(5 * th)) & (r > 0.05)
    img[sprig] = img[sprig] * 0.6 + np.array([0.76, 0.74, 0.64]) * 0.4
    n = vnoise(S, S, rng, 6, 4, wrap=True)
    img = img * (0.88 + 0.18 * n[..., None]) * np.array([1.0, 0.99, 0.95])
    return np.clip(img, 0, 1).astype(np.float32)


NUMBERS = [f"{n}" for n in range(301, 311)]
DOOR_APT_UV = (0.0, 0.0, 448 / 1024, 1.0)
DOOR_STAIR_UV = (448 / 1024, 0.0, 896 / 1024, 1.0)
PLATE_X0 = 896


def plate_uv(k):
    """UV rect of plate k (0..9: 301..310; 10: ROOF; 11: STAIRS) in the doors atlas's right-hand column."""
    h = 1024 // 12
    y0, y1 = k * h, (k + 1) * h
    return (PLATE_X0 / 1024, 1 - y1 / 1024, 1.0, 1 - y0 / 1024)


PAINT_PIX = (0.006, 0.994)                # the apartment door's paint (top-left corner)
STEEL_PIX = (0.444, 0.994)                # the stair door's paint
BRASS_PIX = (0.20, 0.006)                 # brass (the kick plate's middle)


def doors_pixels():
    """The doors atlas, 1024 x 1024. Left (x 0..448): an apartment door, deep green paint, a short top panel and two pairs of fielded panels, a
    brass kick plate. Middle (x 448..896): a stair door in green-grey steel, a wired-glass vision panel, a push plate, a kick plate. Right column
    (x 896..1024): twelve plates, the brass numbers 301 to 310, ROOF and STAIRS."""
    S = 1024
    rng = np.random.default_rng(307)
    img = np.zeros((S, S, 3), np.float32)
    green, brass = np.array([0.08, 0.20, 0.16]), np.array([0.66, 0.50, 0.22])
    A = img[:, :448]
    A[:] = green
    panels = [(40, 230, 40, 408), (270, 640, 40, 204), (270, 640, 244, 408), (680, 900, 40, 204), (680, 900, 244, 408)]
    for (y0, y1, x0, x1) in panels:
        A[y0:y1, x0:x1] = green * 0.9
        A[y0:y0 + 10, x0:x1] = green * 1.25
        A[y1 - 10:y1, x0:x1] = green * 0.65
        A[y0:y1, x0:x0 + 10] = green * 1.15
        A[y0:y1, x1 - 10:x1] = green * 0.72
    A[930:1010, 16:432] = brass * 0.9
    A *= (0.9 + 0.14 * vnoise(S, 448, rng, 6, 6)[..., None])
    M = img[:, 448:896]
    steel = np.array([0.30, 0.36, 0.33])
    M[:] = steel
    M[90:390, 120:328] = (0.62, 0.68, 0.70)                     # the vision panel's wired glass
    gy, gx = np.mgrid[0:300, 0:208]
    wire = ((gy % 24) < 2) | ((gx % 24) < 2)
    M[90:390, 120:328][wire] = (0.40, 0.44, 0.45)
    M[84:396, 114:120] = steel * 0.6
    M[84:396, 328:334] = steel * 0.6
    M[84:90, 114:334] = steel * 0.6
    M[390:396, 114:334] = steel * 0.6
    M[470:560, 330:420] = (0.62, 0.64, 0.62)                    # the push plate
    M[910:1010, 16:432] = steel * 0.78
    M *= (0.88 + 0.16 * vnoise(S, 448, rng, 6, 6)[..., None])
    h = S // 12
    for k, t in enumerate(NUMBERS + ["ROOF", "STAIRS"]):
        y0 = k * h
        if k < 10:
            img[y0:y0 + h, PLATE_X0:] = sign_board(t, h, S - PLATE_X0, (0.70, 0.54, 0.24), (0.08, 0.05, 0.02), rng, fill=0.62, border=(0.45, 0.33, 0.12))
        else:
            img[y0:y0 + h, PLATE_X0:] = sign_board(t, h, S - PLATE_X0, (0.80, 0.78, 0.70), (0.06, 0.08, 0.07), rng, fill=0.5, border=(0.2, 0.2, 0.2))
    img[0:12, 0:12] = green
    img[0:12, 448:460] = steel
    img[S - 12:S, 196:216] = brass
    return np.clip(img, 0, 1).astype(np.float32)


def prints_pixels():
    """Four prints, 512 x 512 each, made here (no source): a sea at dusk with a lighthouse, hills under a pale moon, a lake with a jetty, and a field
    of reeds; soft and faded, as old hotel prints are."""
    S = 1024
    rng = np.random.default_rng(311)
    img = np.zeros((S, S, 3), np.float32)
    yy, xx = (np.mgrid[0:512, 0:512] + 0.5) / 512

    def sky(top, bot):
        t = yy[..., None]
        return np.array(top) * (1 - t) + np.array(bot) * t
    a = sky((0.36, 0.42, 0.55), (0.86, 0.68, 0.52))                         # 1: the sea and a lighthouse
    sea = yy > 0.62
    a[sea] = np.array([0.20, 0.28, 0.36]) * (0.9 + 0.2 * np.sin(yy[sea] * 180)[..., None])
    a[(yy > 0.56 - 0.06 * np.exp(-((xx - 0.80) / 0.10) ** 2)) & (xx > 0.60) & (yy <= 0.66)] = (0.14, 0.14, 0.12)
    a[(np.abs(xx - 0.80) < 0.022) & (yy > 0.30) & (yy < 0.52)] = (0.86, 0.84, 0.78)
    a[(np.abs(xx - 0.80) < 0.03) & (yy > 0.27) & (yy < 0.31)] = (0.98, 0.90, 0.60)
    img[0:512, 0:512] = a
    a = sky((0.18, 0.22, 0.34), (0.48, 0.50, 0.58))                         # 2: hills and a moon
    for k, (h0, col) in enumerate(((0.55, (0.26, 0.30, 0.32)), (0.66, (0.20, 0.24, 0.22)), (0.78, (0.14, 0.18, 0.15)))):
        ridge = h0 + 0.05 * np.sin(xx * (5 + k * 2) + k) + 0.03 * np.sin(xx * 13 + k * 3)
        a[yy > ridge] = col
    a[np.sqrt((xx - 0.3) ** 2 + (yy - 0.25) ** 2) < 0.06] = (0.94, 0.92, 0.82)
    img[0:512, 512:1024] = a
    a = sky((0.62, 0.70, 0.74), (0.90, 0.86, 0.76))                         # 3: a lake and a jetty
    lake = yy > 0.5
    a[lake] = np.array([0.48, 0.58, 0.62]) * (0.95 + 0.08 * np.sin(yy[lake] * 120)[..., None])
    a[(yy > 0.42 + 0.04 * np.abs(np.sin(xx * 40))) & (yy < 0.5)] = (0.22, 0.30, 0.22)
    a[(yy > 0.62) & (yy < 0.64) & (xx > 0.2) & (xx < 0.6)] = (0.30, 0.22, 0.14)
    for px in np.linspace(0.22, 0.58, 6):
        a[(np.abs(xx - px) < 0.004) & (yy > 0.63) & (yy < 0.70)] = (0.22, 0.16, 0.10)
    img[512:1024, 0:512] = a
    a = sky((0.80, 0.74, 0.58), (0.92, 0.88, 0.74))                         # 4: reeds
    a[yy > 0.7] = (0.55, 0.48, 0.30)
    for i in range(90):
        x0 = rng.random()
        h0 = 0.35 + 0.3 * rng.random()
        a[(np.abs(xx - x0 - (1 - yy) * 0.03) < 0.0035) & (yy > h0)] = (0.36, 0.30, 0.16)
        a[(np.abs(xx - x0 - (1 - yy) * 0.03) < 0.008) & (np.abs(yy - h0) < 0.03)] = (0.30, 0.22, 0.12)
    img[512:1024, 512:1024] = a
    img = img * (0.92 + 0.1 * vnoise(S, S, rng, 5, 4)[..., None])
    img = img * 0.85 + 0.15 * img.mean(axis=2, keepdims=True)                 # faded
    return np.clip(img, 0, 1).astype(np.float32)


def print_uv(k):
    r, c = k // 2, k % 2
    return (c * 0.5, 1 - (r + 1) * 0.5, (c + 1) * 0.5, 1 - r * 0.5)


def signs_pixels():
    """The signs, 1024 x 512: FLOOR 3 and ROOF on top, 301 - 310 and STAIRS below. (The exit sign is its own picture.)"""
    W, H = 1024, 512
    rng = np.random.default_rng(313)
    img = np.zeros((H, W, 3), np.float32)
    brass, dark, card, ink = (0.66, 0.50, 0.22), (0.10, 0.07, 0.03), (0.84, 0.82, 0.74), (0.08, 0.10, 0.09)
    img[0:256, 0:512] = sign_board("FLOOR 3", 256, 512, brass, dark, rng, 0.4, border=(0.42, 0.30, 0.12))
    img[0:256, 512:1024] = sign_board("ROOF", 256, 512, card, ink, rng, 0.45, border=(0.25, 0.25, 0.25))
    img[256:512, 0:512] = sign_board("301 - 310", 256, 512, brass, dark, rng, 0.32, border=(0.42, 0.30, 0.12))
    img[256:512, 512:1024] = sign_board("STAIRS", 256, 512, card, ink, rng, 0.4, border=(0.25, 0.25, 0.25))
    return np.clip(img, 0, 1).astype(np.float32)


def exit_pixels():
    rng = np.random.default_rng(317)
    return np.clip(sign_board("EXIT", 128, 256, (0.02, 0.45, 0.16), (0.92, 1.0, 0.94), rng, 0.62, border=(0.01, 0.25, 0.08)), 0, 1).astype(np.float32)


SIGN_UV = {"floor": (0.0, 0.5, 0.5, 1.0), "roof": (0.5, 0.5, 1.0, 1.0), "apts": (0.0, 0.0, 0.5, 0.5), "stairs": (0.5, 0.0, 1.0, 0.5)}


def make_generated():
    if SCENE == "floor_3":
        return {"runner": mk_image("F3_Runner", runner_pixels()), "paper": mk_image("F3_Wallpaper", paper_pixels()),
                "doors": mk_image("F3_Doors", doors_pixels()), "prints": mk_image("F3_Prints", prints_pixels()),
                "signs": mk_image("F3_Signs", signs_pixels()), "exit": mk_image("F3_Exit", exit_pixels()), "palette": mk_image("F3_Palette", palette_pixels())}
    return {"gravel": mk_image("Roof_Gravel", gravel_pixels()), "tar": mk_image("Roof_Tar", tar_pixels()), "pavers": mk_image("Roof_Pavers", pavers_pixels()),
            "doors": mk_image("Roof_Doors", doors_pixels()), "signs": mk_image("Roof_Signs", signs_pixels()), "palette": mk_image("Roof_Palette", palette_pixels())}


def link_emission_texture(mname, img, strength):
    """An emissive sign whose emission colour is its own picture (the glTF exporter writes it as the emissive texture), so its letters show."""
    m = MATS[mname]
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tx = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
    tx.image = img
    nt.links.new(tx.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = strength


# ================================================================ shared pieces: walls from the colliders, door leaves, the layout, the kit
def banded_box(name, b, classify, cut_ys=(), coll=None):
    """The art of one collider box b: the box cut into bands at the heights cut_ys, and each face given a material by classify(centre, normal),
    which returns a material name or None (no face there). One object per material, named <name>_<material>."""
    mn, mx = b["min"], b["max"]
    ys = sorted({mn[1], mx[1], *[y for y in cut_ys if mn[1] < y < mx[1]]})
    per = {}
    for y0, y1 in zip(ys, ys[1:]):
        c = [(mn[0], y0, mn[2]), (mx[0], y1, mx[2])]
        x0, x1, z0, z1 = c[0][0], c[1][0], c[0][2], c[1][2]
        faces = [((x1, (y0 + y1) / 2, (z0 + z1) / 2), (1, 0, 0), [(x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0)]),
                 ((x0, (y0 + y1) / 2, (z0 + z1) / 2), (-1, 0, 0), [(x0, y0, z1), (x0, y0, z0), (x0, y1, z0), (x0, y1, z1)]),
                 (((x0 + x1) / 2, (y0 + y1) / 2, z1), (0, 0, 1), [(x1, y0, z1), (x0, y0, z1), (x0, y1, z1), (x1, y1, z1)]),
                 (((x0 + x1) / 2, (y0 + y1) / 2, z0), (0, 0, -1), [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)])]
        if y1 == mx[1]:
            faces.append((((x0 + x1) / 2, y1, (z0 + z1) / 2), (0, 1, 0), [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)]))
        if y0 == mn[1]:
            faces.append((((x0 + x1) / 2, y0, (z0 + z1) / 2), (0, -1, 0), [(x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0)]))
        for cen, nrm, pts in faces:
            m = classify(cen, nrm)
            if m is None:
                continue
            bm = per.setdefault(m, bmesh.new())
            f = quad(bm, *pts)
            f.normal_update()
            if f.normal.dot(B(nrm)) < 0:
                f.normal_flip()
    out = []
    for m, bm in per.items():
        out.append(finish(f"{name}_{m}", bm, m, coll, recalc=False))
    return out


def leaf_mesh(w, h, front_uv, edge_pix, plate=None, knob=(0.08, 1.0), slot=None, peep=None, push=False):
    """A door leaf in its own frame: local x from the hinge along the leaf (0..w), y across (-0.025..0.025), z up (0..h). Both faces show the picture
    `front_uv` (mirrored on the back so the hinge side matches); the edges take one flat pixel. The corridor side is local -y. plate: (uv rect, z,
    w, h) a number plate on the corridor side; knob: (inset from the free edge, z); slot: z of a brass letter flap; peep: z of a peephole."""
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

    def add(fn, uv):
        old = set(bm.faces)
        fn()
        for f in bm.faces:
            if f not in old:
                for lp in f.loops:
                    lp[uvl].uv = uv
    if plate:
        (pu0, pv0, pu1, pv1), pz, pw, ph = plate
        old = set(bm.faces)
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, -t - 0.003, pz)) @ Matrix.Diagonal((pw, 0.006, ph, 1)))
        for f in bm.faces:
            if f in old:
                continue
            f.normal_update()
            if f.normal.y < -0.9:
                for lp in f.loops:
                    x, z = lp.vert.co.x, lp.vert.co.z
                    lp[uvl].uv = (pu0 + (pu1 - pu0) * ((x - (w / 2 - pw / 2)) / pw), pv0 + (pv1 - pv0) * ((z - (pz - ph / 2)) / ph))
            else:
                for lp in f.loops:
                    lp[uvl].uv = BRASS_PIX
    kx, kz = w - knob[0], knob[1]
    for sgn in (-1, 1):
        if push and sgn > 0:
            add(lambda: bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.016, radius2=0.016, depth=w * 0.72,
                                              matrix=Matrix.Translation((w * 0.5, sgn * (t + 0.06), kz)) @ Matrix.Rotation(math.pi / 2, 4, "Y")), BRASS_PIX)
            for xx in (w * 0.16, w * 0.84):
                add(lambda xx=xx: bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.012, radius2=0.012, depth=0.06,
                                                        matrix=Matrix.Translation((xx, sgn * (t + 0.03), kz)) @ Matrix.Rotation(math.pi / 2, 4, "X")), BRASS_PIX)
            continue
        add(lambda: bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.03, matrix=Matrix.Translation((kx, sgn * (t + 0.055), kz))), BRASS_PIX)
        add(lambda: bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.01, radius2=0.01, depth=0.05,
                                          matrix=Matrix.Translation((kx, sgn * (t + 0.025), kz)) @ Matrix.Rotation(math.pi / 2, 4, "X")), BRASS_PIX)
        add(lambda: bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.028, radius2=0.028, depth=0.006,
                                          matrix=Matrix.Translation((kx, sgn * (t + 0.003), kz)) @ Matrix.Rotation(math.pi / 2, 4, "X")), BRASS_PIX)
    if slot:
        add(lambda: bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, -t - 0.004, slot)) @ Matrix.Diagonal((0.28, 0.008, 0.07, 1))), BRASS_PIX)
    if peep:
        add(lambda: bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.012, radius2=0.012, depth=0.012,
                                          matrix=Matrix.Translation((w / 2, -t - 0.006, peep)) @ Matrix.Rotation(math.pi / 2, 4, "X")), BRASS_PIX)
    return bm


def leaf_object(d, bm, mat="Doors"):
    for f in bm.faces:
        f.smooth = False
    me = bpy.data.meshes.new(d["name"])
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(d["name"], me)
    ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
    for k, v in d["props"].items():
        ob[k] = v
    DOORS_C.objects.link(ob)
    return ob


# the connector kit (blender/kit/README.md), placed with tools/blender/kit_place.py: (piece, suffix, at, yaw, art, {kit door: the scene's door id})
KIT = {
    "floor_3": [("elevator", "F3", (-20.0, 0.0, 0.0), 90.0, True, {"lift": "lift"}),
                ("stair_door", "F3", (20.0, 0.0, 0.0), -90.0, False, {"stair": "stairwell"}),
                ("stair_door", "F3_top", (26.6, 3.2, 0.0), -90.0, False, {"stair": "roof"})],
    "roof": [("stair_door", "roof_stair", (6.0, 0.0, 8.0), -90.0, False, {"stair": "floor_3"}),
             ("safe_house", "roof", (-8.0, 0.0, -5.8), 0.0, True, {})],
}
LAYOUT_PREFIX = ("COL_", "DoorLeaf_", "Link_", "Arrive_", "Spot_", "Zone_", "Marker_")
OWN_LEAVES = set()          # the door ids whose leaf this scene builds (the kit's record is replaced by the leaf, with the same properties)


def gb_names():
    n = {"COL_" + b["name"] for b in GB.boxes if b["col"]} | {b["name"] for b in GB.boxes if b.get("zone")}
    return n | {e["name"] for e in GB.empties} | {d["name"] for d in GB.doors}


def place_kit():
    """Each kit piece: its layout objects that the greybox model lists go into Layout (a kit door renamed to the scene's door id); the rest of its
    layout (the kit's own links, markers, the colliders of its landing and hallway) is dropped; its art (when used) goes into Kit as stand-ins."""
    import kit_place
    want = gb_names()
    for piece, suffix, at, yaw, art, doors in KIT[SCENE]:
        made = kit_place.place(piece, suffix=suffix, at=at, yaw_deg=yaw, art=art, collection=KIT_C)
        ren = {f"DoorLeaf_{k}_{suffix}": f"DoorLeaf_{v}" for k, v in doors.items()}
        for nm in made:
            ob = bpy.data.objects[nm]
            if nm.startswith(LAYOUT_PREFIX):
                new = ren.get(nm, nm)
                if new not in want or new[len("DoorLeaf_"):] in OWN_LEAVES:
                    bpy.data.objects.remove(ob)
                    continue
                ob.name = new
                KIT_C.objects.unlink(ob)
                LAYOUT_C.objects.link(ob)
                e = GB_EMPTIES.get(new)
                if e is not None and ob.type == "EMPTY":          # the greybox model is the source: a kit spot it moves (see _f3) moves here too
                    ob.location = B(e["pos"])
            elif ob.type != "MESH":
                bpy.data.objects.remove(ob)
        if art:
            kit_lights(piece, at, yaw)


KIT_LIGHTS_DROP = ("Corridor_Lamp",)    # the elevator kit's stand-in corridor light: this scene has its own corridor


def kit_lights(piece, at, yaw):
    """The kit piece's own lamps (its Lights collection), moved and turned as kit_place moves its art, into this scene's Lights_Kit."""
    path = ROOT / f"blender/kit/{piece}.blend"
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.collections = [c for c in src.collections if c == "Lights"]
    m = Matrix.Translation(Vector((at[0], -at[2], at[1]))) @ Matrix.Rotation(math.radians(yaw), 4, "Z")
    tgt = bpy.data.collections.get("Lights_Kit") or bpy.data.collections.new("Lights_Kit")
    if tgt.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(tgt)
    for coll in dst.collections:
        for ob in list(coll.objects):
            if ob.name.startswith(KIT_LIGHTS_DROP):
                bpy.data.objects.remove(ob)
                continue
            ob.name = f"Kit_{piece}_{ob.name}"
            ob.matrix_world = m @ ob.matrix_basis.copy()          # appended, in no scene yet: its matrix_world is not evaluated
            tgt.objects.link(ob)
        bpy.data.collections.remove(coll)


def build_layout():
    """The layout objects the kit did not bring, as the greybox names them: COL_ boxes (hidden), zones, the empties (Link_, Arrive_, Marker_, Spot_).
    The leaves are in Doors (build_leaves)."""
    have = {o.name for o in bpy.data.objects}
    for b in GB.boxes:
        nm = "COL_" + b["name"] if b["col"] else b["name"] if b.get("zone") else None
        if nm is None or nm in have:
            continue
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
        if e["name"] in have:
            continue
        ob = bpy.data.objects.new(e["name"], None)
        ob.location = B(e["pos"])
        if e["face"]:
            ob.rotation_euler = (0, 0, math.atan2(e["face"][0], e["face"][1]))
        for k, v in e["props"].items():
            ob[k] = v
        ob.empty_display_size = 0.3
        LAYOUT_C.objects.link(ob)
    missing = gb_names() - {o.name for o in bpy.data.objects}
    assert not missing, f"layout objects missing: {sorted(missing)}"


# ================================================================ floor 3: the art
CZ = G.CORR_Z                 # the corridor's half width (1.1)
CX = G.CORR_X                 # its half length (20)
CH = G.CORR_H                 # its height (2.8)
WAIN = 0.95                   # the wainscot's top (the chair rail)
RUN_Z = 0.65                  # the runner's half width
RUN_X = (-18.6, 19.5)         # where the runner starts and ends (oak at the lift's landing stone and at the stair door)
LIGHTS = []                   # (kind, game pos, watts, colour, radius, aim (game dir) or None, cone deg)
WARM = (1.0, 0.76, 0.50)
BAYS = (-12.0, -4.0, 4.0, 12.0)
SCONCES = [("N", x) for x in (-18.3, -13.5, -10.5, -2.5, 2.5, 5.5, 10.5, 13.5, 18.3)] + \
          [("S", x) for x in (-18.3, -13.5, -10.5, -5.5, 2.5, 5.5, 10.5, 13.5, 18.3)]
PRINTS = [("N", -12.0, 0), ("S", -12.0, 1), ("N", 4.0, 2), ("S", 12.0, 3)]
RADIATORS = [("S", -12.0), ("N", 4.0)]
MATS_AT = {301: "coir", 302: "mat_red", 304: "mat_green", 306: "mat_grey", 307: "coir", 309: "mat_blue", 310: "mat_brown"}


def lamp_light(pos, watts, radius=0.06, kind="POINT", aim=None, cone=120.0, color=WARM):
    LIGHTS.append((kind, pos, watts, color, radius, aim, cone))


def f3_class(bname):
    """The material of each face of a floor-3 box, from where it is."""
    def cls(c, n):
        x, y, z = c
        if bname.startswith(("Corridor_Ceiling", "Alcove_Ceiling", "Stairwell_Ceiling")):
            return "Ceiling_Plaster"
        if bname.startswith(("Stairwell_Floor", "Landing_Top")):
            return "Stair_Concrete"
        if bname.startswith("Alcove_Floor"):
            return "Floor_Oak"
        if n[1] < -0.5:
            return "Trim_Paint"                                    # the soffit of a door or alcove head
        if bname.startswith(("Corridor_Wall_N", "Corridor_Wall_S")) and abs(n[0]) > 0.5:
            return "Trim_Paint"                                    # a door's or an alcove's reveal
        if bname.startswith(("Corridor_Wall_W", "Corridor_Wall_E", "Stairwell_Wall_E")) and abs(n[2]) > 0.5:
            return "Trim_Paint"
        if bname.startswith("Stairwell_") or x > CX + T - 1e-3:
            return "Stair_Wall"
        return "Wall_Wainscot" if y < WAIN else "Wall_Paper"
    return cls


def f3_shell():
    for n, b in BOX.items():
        if not b["col"] or n.startswith(("Step_", "Car_", "Landing_F3", "Landing_Floor", "Landing_Head", "Landing_Jamb", "Corridor_Floor")):
            continue
        cuts = (WAIN,) if n.startswith(("Corridor_Wall", "Alcove_Back", "Alcove_Side")) else ()
        banded_box(n, b, f3_class(n), cuts)
    # the corridor's floor: oak along the walls and at both ends, the runner down the middle
    fl = BOX["Corridor_Floor"]
    xs = [fl["min"][0], RUN_X[0], RUN_X[1], fl["max"][0]]
    zs = [fl["min"][2], -RUN_Z, RUN_Z, fl["max"][2]]
    oak, run = bmesh.new(), bmesh.new()
    for xa, xb in zip(xs, xs[1:]):
        for za, zb in zip(zs, zs[1:]):
            middle = RUN_X[0] < (xa + xb) / 2 < RUN_X[1] and abs((za + zb) / 2) < RUN_Z
            box(run if middle else oak, xa, xb, -G.SLAB, 0.0, za, zb)
    finish("Corridor_Floor_Oak", oak, "Floor_Oak")
    run.normal_update()
    if not run.loops.layers.uv.get("UVMap"):
        run.loops.layers.uv.new("UVMap")
    set_uv_rect(run, list(run.faces), (0.0, -RUN_Z, 2 * RUN_Z, RUN_Z), (0, 2))
    finish("Corridor_Floor_Runner", run, "Floor_Runner", keep_uv=True)
    # the runner's brass stair rods at its two ends
    part("decor_runner_rods", "Brass", lambda bm: [cyl(bm, (x, 0.008, -RUN_Z - 0.02), (x, 0.008, RUN_Z + 0.02), 0.008, 0.008, 8) for x in (RUN_X[0] + 0.03, RUN_X[1] - 0.03)])


def wall_runs():
    """The corridor's two long walls as runs of solid wall between openings: (side, x0, x1) on the corridor face (z = -CZ north, +CZ south)."""
    out = []
    for side in ("N", "S"):
        for n, b in BOX.items():
            if n.startswith(f"Corridor_Wall_{side}_") and b["min"][1] < 0.01:
                out.append((side, max(b["min"][0], -CX), min(b["max"][0], CX)))
    return out


def f3_trim():
    """Skirting, the chair rail and the cornice along both long walls (not across the openings), the ends' too; casings round every door."""
    sk, rail, corn = bmesh.new(), bmesh.new(), bmesh.new()
    for side, x0, x1 in wall_runs():
        s = -1 if side == "N" else 1
        zf = s * CZ
        box(sk, x0, x1, 0.0, 0.14, zf, zf - s * 0.018)
        box(rail, x0, x1, WAIN - 0.03, WAIN + 0.03, zf, zf - s * 0.022)
    for side in ("N", "S"):
        s = -1 if side == "N" else 1
        zf = s * CZ
        box(corn, -CX, CX, CH - 0.09, CH, zf, zf - s * 0.05)
        box(corn, -CX, CX, CH - 0.03, CH, zf - s * 0.05, zf - s * 0.08)
    for x, sgn in ((-CX, 1), (CX, -1)):                                       # the end walls, beside their openings
        for za, zb in ((-CZ, -0.68 if sgn > 0 else -0.62), (0.68 if sgn > 0 else 0.62, CZ)):
            box(sk, x, x + sgn * 0.018, 0.0, 0.14, za, zb)
            box(rail, x, x + sgn * 0.022, WAIN - 0.03, WAIN + 0.03, za, zb)
        box(corn, x, x + sgn * 0.05, CH - 0.09, CH, -CZ, CZ)
    finish("decor_skirting", sk, "Trim_Paint")
    finish("decor_chair_rail", rail, "Trim_Paint")
    finish("decor_cornice", corn, "Trim_Paint")
    cas = bmesh.new()
    for d in GB.doors:
        if not d["name"].startswith("DoorLeaf_room_"):
            continue
        a = d["props"]["room_x"]
        s = -1 if d["props"]["room_z"] < 0 else 1
        zf, hw, h = s * CZ, G.DOOR_W / 2, G.DOOR_H
        for xa, xb in ((a - hw - 0.075, a - hw), (a + hw, a + hw + 0.075)):
            box(cas, xa, xb, 0.0, h + 0.075, zf, zf - s * 0.02)
        box(cas, a - hw - 0.075, a + hw + 0.075, h, h + 0.075, zf, zf - s * 0.02)
    sw = 0.55                                                                  # the stair door (the kit's 1.1 m opening) on the corridor's east wall
    for za, zb in ((-sw - 0.075, -sw), (sw, sw + 0.075)):
        box(cas, CX, CX - 0.02, 0.0, G.DOOR_H + 0.075, za, zb)
    box(cas, CX, CX - 0.02, G.DOOR_H, G.DOOR_H + 0.075, -sw - 0.075, sw + 0.075)
    finish("decor_casings", cas, "Trim_Paint")


def f3_leaves():
    for d in GB.doors:
        nm = d["name"]
        p = d["props"]
        w, h = p["width"], p["height"]
        if nm.startswith("DoorLeaf_room_"):
            k = int(p["room"]) - 301
            bm = leaf_mesh(w, h, DOOR_APT_UV, PAINT_PIX, plate=(plate_uv(k), 1.58, 0.17, 0.085), knob=(0.08, 1.0), slot=1.05, peep=1.45)
            leaf_object(d, bm)
        elif p.get("kind") == "stair door":
            bm = leaf_mesh(w, h, DOOR_STAIR_UV, STEEL_PIX, knob=(0.09, 1.02))
            # the ROOF plate on the landing side (local +y for a stair door: its landing is toward -x)
            old = set(bm.faces)
            uvl = bm.loops.layers.uv["UVMap"]
            pu0, pv0, pu1, pv1 = plate_uv(10)
            bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, 0.028, 1.62)) @ Matrix.Diagonal((0.22, 0.006, 0.09, 1)))
            for f in bm.faces:
                if f in old:
                    continue
                f.normal_update()
                for lp in f.loops:
                    if f.normal.y > 0.9:
                        x, z = lp.vert.co.x, lp.vert.co.z
                        lp[uvl].uv = (pu0 + (pu1 - pu0) * (1 - (x - (w / 2 - 0.11)) / 0.22), pv0 + (pv1 - pv0) * ((z - 1.575) / 0.09))
                    else:
                        lp[uvl].uv = STEEL_PIX
            leaf_object(d, bm)
            OWN_LEAVES.add(nm[len("DoorLeaf_"):])


def f3_stairs():
    """The flight up to the roof: each step a concrete tread and a body under it, both under 0.2 m tall (the layout check tests art taller than that
    for a collider standing on the floor; the steps' own colliders start in the air). A steel handrail on the south wall (decor_)."""
    steps = sorted((n, b) for n, b in BOX.items() if n.startswith("Step_"))
    for n, b in steps:
        x0, x1, y0, y1, z0, z1 = b["min"][0], b["max"][0], b["min"][1], b["max"][1], b["min"][2], b["max"][2]
        part(f"Stair_{n}_tread", "Stair_Concrete", lambda bm, b=b: box(bm, x0 - 0.02, x1, y1 - 0.05, y1, z0, z1))
        part(f"Stair_{n}_body", "Stair_Concrete", lambda bm, b=b: box(bm, x0, x1, y0, y1 - 0.05, z0, z1))
    xs0, xs1 = steps[0][1]["min"][0], steps[-1][1]["max"][0]
    ytop = steps[-1][1]["max"][1]
    rise = steps[0][1]["max"][1] - steps[0][1]["min"][1]

    def rail(bm):
        z = 1.0 - 0.07
        a, b_ = (xs0 - 0.3, 0.9 + rise), (xs1 + 0.2, ytop + 0.9)
        cyl(bm, (a[0], a[1], z), (b_[0], b_[1], z), 0.022, 0.022, 10)
        cyl(bm, (b_[0], b_[1], z), (26.4, ytop + 0.9, z), 0.022, 0.022, 10)
        for t in (0.05, 0.35, 0.65, 0.95):
            x = a[0] + (b_[0] - a[0]) * t
            y = a[1] + (b_[1] - a[1]) * t
            cyl(bm, (x, y, z), (x, y, 1.0), 0.01, 0.01, 6)
    part("decor_stair_handrail", "Steel_Paint", rail, smooth=True, sharp_deg=50)
    # the stairwell's lamps: a bulkhead fitting on the ceiling over the flight and one over the roof door
    part("decor_stair_fittings", "Metal_Dark", lambda bm: [cyl(bm, (23.2, 5.93, 0.0), (23.2, 6.0, 0.0), 0.16, 0.16, 16),
                                                           box(bm, 26.6, 26.52, 5.55, 5.8, -0.14, 0.14)])
    part("decor_stair_lenses", "Lamp_Emit", lambda bm: [cyl(bm, (23.2, 5.88, 0.0), (23.2, 5.93, 0.0), 0.13, 0.11, 16),
                                                        box(bm, 26.52, 26.50, 5.58, 5.77, -0.11, 0.11)])
    lamp_light((23.2, 5.8, 0.0), 70.0, 0.12)
    lamp_light((26.42, 5.66, 0.0), 22.0, 0.06)
    lamp_light((20.9, 2.55, 0.0), 10.0, 0.08)                          # the glow from the corridor's exit sign side, on the stairwell's lower wall
    # the signs: ROOF over the top door, STAIRS by the bottom one (stairwell side)
    panel("decor_stair_sign_roof", "Signs", (26.59, 5.46, 0.0), "-x", 0.36, 0.17, SIGN_UV["roof"])
    panel("decor_stair_sign_floor", "Signs", (20.21, 1.62, -0.78), "+x", 0.36, 0.18, SIGN_UV["floor"])


def f3_sconces():
    """A single-arm brass sconce with a pleated linen shade (the shade glows: Lamp_Emit) at 1.85 m, two to a bay on each wall, and two at each end."""
    bmb, bms = bmesh.new(), bmesh.new()
    for side, x in SCONCES:
        s = -1 if side == "N" else 1
        zf = s * CZ
        cyl(bmb, (x, 1.80, zf), (x, 1.80, zf - s * 0.02), 0.055, 0.055, 14)
        cyl(bmb, (x, 1.80, zf - s * 0.015), (x, 1.88, zf - s * 0.15), 0.009, 0.009, 6)
        cyl(bmb, (x, 1.86, zf - s * 0.15), (x, 1.92, zf - s * 0.15), 0.02, 0.016, 10)
        cyl(bms, (x, 1.88, zf - s * 0.15), (x, 2.04, zf - s * 0.15), 0.10, 0.07, 16, cap=False)
        lamp_light((x, 1.97, zf - s * 0.15), 19.0, 0.06)
    finish("decor_sconce_brass", bmb, "Brass", smooth=True, sharp_deg=50)
    finish("decor_sconce_shades", bms, "Lamp_Emit", smooth=True, sharp_deg=50)
    # the two alcoves: a small flush light in each ceiling
    al = [(b["min"][0] + b["max"][0]) / 2 for n, b in BOX.items() if n.startswith("Alcove_Ceiling")]
    zs = [(b["min"][2] + b["max"][2]) / 2 for n, b in BOX.items() if n.startswith("Alcove_Ceiling")]
    part("decor_alcove_lights", "Lamp_Emit", lambda bm: [cyl(bm, (x, 2.37, z), (x, 2.4, z), 0.1, 0.1, 16) for x, z in zip(al, zs)])
    for x, z in zip(al, zs):
        lamp_light((x, 2.32, z), 9.0, 0.06)


def f3_prints():
    """Framed prints over the wainscot (made here: prints_pixels), radiators under two of them and one in the north alcove, and the alcoves' prints."""
    fr, pic, rad = bmesh.new(), bmesh.new(), bmesh.new()
    items = [(side, x, -1 if side == "N" else 1, k, 1.62) for side, x, k in PRINTS]
    alc = [(b["min"][0] + b["max"][0]) / 2 for n, b in sorted(BOX.items()) if n.startswith("Alcove_Back")]
    backs = [b for n, b in sorted(BOX.items()) if n.startswith("Alcove_Back")]
    for b, k in zip(backs, (1, 0)):
        north = b["max"][2] < 0
        zf = b["max"][2] if north else b["min"][2]
        items.append(("A", (b["min"][0] + b["max"][0]) / 2, -1 if north else 1, k, 1.70, zf))
    for it in items:
        side, x, s, k, yc = it[:5]
        zf = it[5] if len(it) > 5 else s * CZ
        w = h = 0.56
        box(fr, x - w / 2 - 0.045, x + w / 2 + 0.045, yc - h / 2 - 0.045, yc + h / 2 + 0.045, zf, zf - s * 0.035)
        nrm = "+z" if s < 0 else "-z"
        u0, v0, u1, v1 = print_uv(k)
        if s > 0:
            u0, u1 = u0, u1
        panel(None, "Prints", (x, yc, zf - s * 0.037), nrm, w, h, (u0, v0, u1, v1), bm=pic)
    for side, x in RADIATORS + [("A", None)]:
        if side == "A":
            b = backs[0]
            x, s, zf = (b["min"][0] + b["max"][0]) / 2, -1, b["max"][2]
            length = 0.9
        else:
            s = -1 if side == "N" else 1
            zf, length = s * CZ, 1.1
        n = int(length / 0.09)
        for i in range(n):
            xi = x - length / 2 + (i + 0.5) * length / n
            box(rad, xi - 0.03, xi + 0.03, 0.14, 0.78, zf - s * 0.04, zf - s * 0.12)
        box(rad, x - length / 2, x + length / 2, 0.18, 0.22, zf - s * 0.05, zf - s * 0.11)
        box(rad, x - length / 2, x + length / 2, 0.70, 0.74, zf - s * 0.05, zf - s * 0.11)
        for xa in (x - length / 2 + 0.04, x + length / 2 - 0.04):
            box(rad, xa - 0.025, xa + 0.025, 0.0, 0.16, zf - s * 0.06, zf - s * 0.10)
    finish("decor_print_frames", fr, "Frame_Wood")
    finish("decor_prints", pic, "Prints", keep_uv=True, recalc=False)
    finish("decor_radiators", rad, "Radiator_Paint")
    for side, x in RADIATORS:                                             # their valves
        pass


def f3_fittings():
    """The welcome mats, the exit sign over the stair door, the floor plaques by the lift, smoke detectors."""
    p = Painter()
    for d in GB.doors:
        if not d["name"].startswith("DoorLeaf_room_"):
            continue
        num = int(d["props"]["room"])
        if num not in MATS_AT:
            continue
        a, s = d["props"]["room_x"], (-1 if d["props"]["room_z"] < 0 else 1)
        z0, z1 = sorted((s * CZ - s * 0.02, s * (RUN_Z + 0.01)))
        p.add(MATS_AT[num], box, a - 0.36, a + 0.36, 0.0, 0.012, z0, z1)
    for x in (-10.0, 0.0, 10.0, 23.2 - 1.6):
        y = CH if x < CX else 6.0
        p.add("smoke", cyl, (x, y - 0.035, 0.0), (x, y, 0.0), 0.06, 0.065, 14)
    p.done("decor_mats_and_fittings")
    # the exit sign: a slim box over the stair door, its face lit (Exit_Emit, its own picture)
    part("decor_exit_box", "Metal_Dark", lambda bm: box(bm, CX - 0.07, CX, 2.24, 2.46, -0.2, 0.2))
    bm = bmesh.new()
    panel(None, "Exit_Emit", (CX - 0.071, 2.35, 0.0), "-x", 0.36, 0.18, (0, 0, 1, 1), bm=bm)
    finish("decor_exit_face", bm, "Exit_Emit", keep_uv=True, recalc=False)
    lamp_light((CX - 0.3, 2.35, 0.0), 1.5, 0.1, color=(0.3, 1.0, 0.45))
    # FLOOR 3 and 301 - 310 on the west wall beside the lift (the kit's call button is on the other side)
    panel("decor_plaque_floor", "Signs", (-CX + 0.012, 1.66, 0.86), "+x", 0.30, 0.15, SIGN_UV["floor"])
    panel("decor_plaque_rooms", "Signs", (-CX + 0.012, 1.46, 0.86), "+x", 0.30, 0.15, SIGN_UV["apts"])
    part("decor_plaque_backs", "Brass", lambda bm: [box(bm, -CX, -CX + 0.01, 1.58, 1.74, 0.70, 1.02), box(bm, -CX, -CX + 0.01, 1.38, 1.54, 0.70, 1.02)])


def build_floor3():
    f3_shell()
    f3_trim()
    f3_stairs()
    f3_sconces()
    f3_prints()
    f3_fittings()


# ================================================================ the roof: the pictures
def gravel_pixels():
    """Roof ballast: grey-brown pebbles on a darker bed, in speckled clusters; tiles every 1.2 m."""
    S = 1024
    rng = np.random.default_rng(401)
    base = vnoise(S, S, rng, 5, 8, wrap=True)
    img = np.zeros((S, S, 3), np.float32)
    img[:] = np.array([0.30, 0.28, 0.25])[None, None] * (0.75 + 0.4 * base[..., None])
    for k in range(9000):
        cy, cx = rng.integers(0, S, 2)
        r = rng.integers(3, 8)
        col = np.array([0.42, 0.40, 0.36]) * (0.6 + 0.8 * rng.random()) * np.array([1.0, 0.98 + 0.04 * rng.random(), 0.92 + 0.1 * rng.random()])
        ys, xs = np.ogrid[-r:r + 1, -r:r + 1]
        m = (xs ** 2 + (ys * 1.3) ** 2) <= r * r
        yy, xx = (np.arange(-r, r + 1)[:, None] + cy) % S, (np.arange(-r, r + 1)[None, :] + cx) % S
        sh = 1.0 - 0.35 * (ys + r) / (2 * r + 1)                 # each pebble lit from above, a little darker at its foot
        img[yy, xx] = np.where(m[..., None], col[None, None] * sh[..., None], img[yy, xx])
    return np.clip(img, 0, 1).astype(np.float32)


def tar_pixels():
    """Tar: near-black with grey streaks of old patching and flecks of grit; tiles."""
    S = 512
    rng = np.random.default_rng(403)
    n = vnoise(S, S, rng, 6, 4, wrap=True)
    streak = vnoise(S, S, rng, 3, 2, wrap=True)
    img = np.zeros((S, S, 3), np.float32)
    img[:] = np.array([0.07, 0.07, 0.07])[None, None] * (0.8 + 0.5 * n[..., None]) + np.array([0.06, 0.06, 0.055]) * (streak[..., None] > 0.6)
    fl = rng.random((S, S)) > 0.985
    img[fl] = (0.28, 0.27, 0.25)
    return np.clip(img, 0, 1).astype(np.float32)


def pavers_pixels():
    """Concrete roof pavers, 0.6 m square (2 x 2 a repeat, 1.2 m), weathered, with dark joints."""
    S = 1024
    rng = np.random.default_rng(407)
    yy, xx = np.mgrid[0:S, 0:S]
    cell = (xx // 512) + 2 * (yy // 512)
    tone = np.array([0.62, 0.58, 0.64, 0.60])[cell]
    n = vnoise(S, S, rng, 6, 4, wrap=True)
    img = (np.array([1.0, 0.98, 0.94])[None, None] * (tone * (0.8 + 0.35 * n))[..., None]).astype(np.float32)
    j = ((xx % 512) < 6) | ((yy % 512) < 6)
    img[j] = (0.16, 0.15, 0.14)
    edge = ((xx % 512) < 14) | ((yy % 512) < 14) | ((xx % 512) > 498) | ((yy % 512) > 498)
    img[edge & ~j] *= 0.85
    return np.clip(img, 0, 1).astype(np.float32)


# ================================================================ the roof: the art
A = 12.0                       # the roof's half width inside the parapet
PAR_H = 1.1
BH = BOX["Stair_Bulkhead"] if SCENE == "roof" else None
SH = (-11.2, -4.8, -11.2, -5.8, 3.0)        # the kit safe house's outside (x0, x1, z0, z1, roof top), from its layout (SH_ walls, ceiling)
SKIN = 0.01                    # this scene's SH_Outside skin stands 1 cm outside the kit's
PATHS = [(-8.6, 5.8, 7.4, 8.6), (-8.6, -7.4, -5.8, 7.4), (-7.4, -1.4, -0.6, 0.6), (-1.4, 1.4, -1.4, 1.4)]   # (x0, x1, z0, z1): the paver path
TAR = [(-4.5, 2.5, 1.6, 1.1, 0.3), (3.5, -4.0, 2.2, 1.4, -0.4), (-9.5, 2.5, 1.2, 0.9, 0.9), (9.0, 2.0, 1.8, 1.0, 0.2), (0.5, 9.5, 2.4, 1.2, 1.2),
       (-2.0, -10.0, 1.4, 1.0, -0.8), (10.0, -4.0, 1.0, 1.6, 0.5), (-10.4, 10.4, 1.3, 1.1, 0.0)]                    # (x, z, rx, rz, turn)


def roof_class(bname):
    def cls(c, n):
        x, y, z = c
        if bname.startswith("Parapet_"):
            inner = (n[0] * -x + n[2] * -z) > 0.5                 # faces the roof's middle
            if n[1] > 0.5:
                return "Coping"
            if inner and y < 0.3:
                return "Roof_Tar"                                 # the flashing's upturn at the parapet's foot
            return "Brick"
        return "Brick"
    return cls


def slab_cells(name, mat, cells, y0=-G.SLAB, y1=0.0, tops=True):
    bm = bmesh.new()
    for xa, xb, za, zb in cells:
        box(bm, xa, xb, y0, y1, za, zb)
    if not tops:
        bm.normal_update()
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.normal.z > 0.9], context="FACES")
    return finish(name, bm, mat) if bm.faces else None


def roof_floor():
    """The roof's floor: the slab in cells, gravel everywhere but the paver path; no top under the safe house (the kit's floor) or the bulkhead."""
    fl = BOX["Roof_Floor"]
    xs = sorted({fl["min"][0], fl["max"][0], SH[0], SH[1], BH["min"][0], BH["max"][0], *[v for p in PATHS for v in p[:2]]})
    zs = sorted({fl["min"][2], fl["max"][2], SH[2], SH[3], BH["min"][2], BH["max"][2], *[v for p in PATHS for v in p[2:]]})
    gravel, pav, hid = [], [], []
    for xa, xb in zip(xs, xs[1:]):
        for za, zb in zip(zs, zs[1:]):
            xm, zm = (xa + xb) / 2, (za + zb) / 2
            if SH[0] < xm < SH[1] and SH[2] < zm < SH[3]:
                hid.append((xa, xb, za, zb))
            elif BH["min"][0] < xm < BH["max"][0] and BH["min"][2] < zm < BH["max"][2]:
                continue                                          # the bulkhead's stair shaft
            elif any(p[0] < xm < p[1] and p[2] < zm < p[3] for p in PATHS):
                pav.append((xa, xb, za, zb))
            else:
                gravel.append((xa, xb, za, zb))
    slab_cells("Roof_Floor_Gravel", "Roof_Gravel", gravel)
    slab_cells("Roof_Floor_Pavers", "Roof_Pavers", pav)
    slab_cells("Roof_Floor_Under_SH", "Roof_Tar", hid, tops=False)
    # tar patches on the gravel (flat, passable), and a tar ring round the puzzle's spot
    bm = bmesh.new()
    rng = np.random.default_rng(409)
    for (x, z, rx, rz, th) in TAR:
        n = 14
        c, s = math.cos(th), math.sin(th)
        rad = 0.75 + 0.5 * rng.random(n)
        pts = []
        for i in range(n):
            a = 2 * math.pi * i / n
            u, v = rx * rad[i] * math.cos(a), rz * rad[i] * math.sin(a)
            pts.append((x + u * c - v * s, 0.004, z + u * s + v * c))
        vs = [bm.verts.new(B(p)) for p in pts]
        bm.faces.new(vs)
    bm.normal_update()
    for f in bm.faces:
        if f.normal.z < 0:
            f.normal_flip()
    finish("decor_tar_patches", bm, "Roof_Tar", recalc=False)
    bm = bmesh.new()
    n = 48
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        r0, r1 = 1.15, 1.27
        quad(bm, (r0 * math.cos(a0), 0.004, r0 * math.sin(a0)), (r1 * math.cos(a0), 0.004, r1 * math.sin(a0)),
             (r1 * math.cos(a1), 0.004, r1 * math.sin(a1)), (r0 * math.cos(a1), 0.004, r0 * math.sin(a1)))
    bm.normal_update()
    for f in bm.faces:
        if f.normal.z < 0:
            f.normal_flip()
    finish("decor_puzzle_ring", bm, "Roof_Tar", recalc=False)


def roof_parapet():
    for n, b in BOX.items():
        if n.startswith("Parapet_"):
            banded_box(n, b, roof_class(n), (0.3,))
    # the coping: a concrete cap with a 4 cm drip inward, in 1.2 m lengths (the joints are the boxes' ends)
    bm = bmesh.new()
    for x0 in np.arange(-A - 0.3, A + 0.3 - 1e-6, 1.2):
        x1 = min(x0 + 1.2, A + 0.3)
        box(bm, x0 + 0.004, x1 - 0.004, PAR_H, PAR_H + 0.06, -A - 0.33, -A + 0.04)
        box(bm, x0 + 0.004, x1 - 0.004, PAR_H, PAR_H + 0.06, A - 0.04, A + 0.33)
    for z0 in np.arange(-A + 0.04, A - 0.04 - 1e-6, 1.2):
        z1 = min(z0 + 1.2, A - 0.04)
        box(bm, -A - 0.33, -A + 0.04, PAR_H, PAR_H + 0.06, z0 + 0.004, z1 - 0.004)
        box(bm, A - 0.04, A + 0.33, PAR_H, PAR_H + 0.06, z0 + 0.004, z1 - 0.004)
    finish("Parapet_Coping", bm, "Coping")
    # roof drains (flat cast-iron grates) in the four corners, and short vent stubs (under 0.2 m: the layout check's height for a collider)
    part("decor_drains", "Iron_Black", lambda bm: [box(bm, sx * (A - 0.7), sx * (A - 0.4), 0.0, 0.012, sz * (A - 0.7), sz * (A - 0.4)) for sx in (-1, 1) for sz in (-1, 1)])
    part("Vent_Stubs", "Steel_Galv", lambda bm: [cyl(bm, (x, 0.0, z), (x, 0.18, z), 0.055, 0.055, 12) for x, z in ((-6.0, 5.0), (4.0, -2.5), (-2.5, -4.0), (3.0, 4.5))],
         smooth=True, sharp_deg=50)
    part("Vent_Caps", "Metal_Dark", lambda bm: [cyl(bm, (x, 0.165, z), (x, 0.185, z), 0.075, 0.075, 12) for x, z in ((-6.0, 5.0), (4.0, -2.5), (-2.5, -4.0), (3.0, 4.5))])


def roof_bulkhead():
    """The stair bulkhead: brick walls round the stair head, a tar roof with a concrete lip, the kit's 1.1 m stair door in its west wall; inside, a
    small landing and the flight going down into the dark (seen when the door is open; all inside the bulkhead's one collider)."""
    x0, x1, z0, z1, h = BH["min"][0], BH["max"][0], BH["min"][2], BH["max"][2], BH["max"][1]
    t, ow, oh = 0.2, 0.55, G.DOOR_H
    walls = {"N": (x0, x1, z0, z0 + t), "S": (x0, x1, z1 - t, z1), "E": (x1 - t, x1, z0 + t, z1 - t)}
    e = 1e-3
    def cls(c, n):
        """Outside: brick. The inner planes are left to the shaft's lining (one piece, below); the doorway's reveals and soffit are plaster."""
        on_inner = (n[0] > 0.5 and abs(c[0] - (x0 + t)) < e) or (n[0] < -0.5 and abs(c[0] - (x1 - t)) < e) or \
                   (n[2] > 0.5 and abs(c[2] - (z0 + t)) < e) or (n[2] < -0.5 and abs(c[2] - (z1 - t)) < e)
        if on_inner:
            return None
        if n[1] < -0.5:
            return "Stair_Wall"
        if n[1] > 0.5:
            return "Coping"
        if x0 - e < c[0] < x0 + t + e and abs(n[2]) > 0.5 and z0 + t < c[2] < z1 - t:
            return "Stair_Wall"                                  # the doorway's reveals
        return "Brick"
    for k, (a, b_, c_, d_) in walls.items():
        banded_box(f"Bulkhead_Wall_{k}", {"min": [a, -3.0, c_], "max": [b_, h, d_]}, cls, (0.0,))
    zc = (z0 + z1) / 2
    for nm, (za, zb, ya, yb) in {"W_S": (z0 + t, zc - ow, -3.0, h), "W_N": (zc + ow, z1 - t, -3.0, h), "W_Head": (zc - ow, zc + ow, oh, h)}.items():
        banded_box(f"Bulkhead_Wall_{nm}", {"min": [x0, ya, za], "max": [x0 + t, yb, zb]}, cls, (0.0,))
    # the shaft's lining: the four inner faces from the pit to the roof's soffit, the doorway cut out of the west one (one piece: its box is the
    # bulkhead's inside, which the bulkhead's one collider fills)
    xi0, xi1, zi0, zi1, yb_, yt_ = x0 + t, x1 - t, z0 + t, z1 - t, -3.0, h - 0.2
    def lining(bm):
        quad(bm, (xi0, yb_, zi0), (xi1, yb_, zi0), (xi1, yt_, zi0), (xi0, yt_, zi0))
        quad(bm, (xi1, yb_, zi1), (xi0, yb_, zi1), (xi0, yt_, zi1), (xi1, yt_, zi1))
        quad(bm, (xi1, yb_, zi0), (xi1, yb_, zi1), (xi1, yt_, zi1), (xi1, yt_, zi0))
        for za, zb, ya, yb2 in ((zi0, zc - ow, yb_, yt_), (zc + ow, zi1, yb_, yt_), (zc - ow, zc + ow, oh, yt_), (zc - ow, zc + ow, yb_, -0.25)):
            quad(bm, (xi0, ya, zb), (xi0, ya, za), (xi0, yb2, za), (xi0, yb2, zb))
        bm.normal_update()
        ctr = B(((xi0 + xi1) / 2, (yb_ + yt_) / 2, (zi0 + zi1) / 2))
        for f in bm.faces:
            if f.normal.dot(ctr - f.calc_center_median()) < 0:
                f.normal_flip()
    part("Bulkhead_Shaft", "Stair_Wall", lining, recalc=False)
    # the door's steel frame in the doorway (jambs and head, round the kit's 1.04 m leaf)
    part("Bulkhead_Door_Frame", "Steel_Paint", lambda bm: [box(bm, x0, x0 + t, 0.0, oh, zc - ow, zc - ow + 0.035), box(bm, x0, x0 + t, 0.0, oh, zc + ow - 0.035, zc + ow),
                                                           box(bm, x0, x0 + t, oh - 0.035, oh, zc - ow, zc + ow), box(bm, x0 + 0.02, x0 + t - 0.02, -0.01, 0.012, zc - ow, zc + ow)])
    part("Bulkhead_Roof", "Roof_Tar", lambda bm: box(bm, x0, x1, h - 0.2, h, z0, z1))
    part("Bulkhead_Lip", "Coping", lambda bm: [box(bm, x0 - 0.03, x1 + 0.03, h, h + 0.08, z0 - 0.03, z0 + 0.15), box(bm, x0 - 0.03, x1 + 0.03, h, h + 0.08, z1 - 0.15, z1 + 0.03),
                                               box(bm, x0 - 0.03, x0 + 0.15, h, h + 0.08, z0 + 0.15, z1 - 0.15), box(bm, x1 - 0.15, x1 + 0.03, h, h + 0.08, z0 + 0.15, z1 - 0.15)])
    # inside: the landing, then nine steps down toward the east wall
    part("Bulkhead_Landing", "Stair_Concrete", lambda bm: box(bm, x0 + t, x0 + 1.5, -0.25, 0.0, z0 + t, z1 - t))
    xa, n, tread, rise = x0 + 1.5, 9, 0.25, 0.25
    for i in range(n):
        part(f"Bulkhead_Step_{i}", "Stair_Concrete", lambda bm, i=i: box(bm, xa + i * tread, xa + (i + 1) * tread, -(i + 1) * rise - 0.06, -(i + 1) * rise, z0 + t + 0.9, z1 - t))
    part("Bulkhead_Pit", "Stair_Concrete", lambda bm: box(bm, x0 + 1.5, x1 - t, -3.0, -2.9, z0 + t, z1 - t))
    part("decor_bulkhead_bulb", "Lamp_Emit", lambda bm: sphere(bm, (x0 + 1.0, h - 0.32, zc), 0.05, 10))
    part("decor_bulkhead_cord", "Iron_Black", lambda bm: cyl(bm, (x0 + 1.0, h - 0.2, zc), (x0 + 1.0, h - 0.28, zc), 0.006, 0.006, 6))
    lamp_light((x0 + 1.0, h - 0.36, zc), 12.0, 0.05)
    # the wall packs: over the door (west), on the south and north faces; each a dark housing with a lit lens, aimed down and out
    packs = [((x0, 2.42, zc), (-1, 0, 0)), (((x0 + x1) / 2, 2.38, z1), (0, 0, 1)), (((x0 + x1) / 2, 2.38, z0), (0, 0, -1))]
    hous, lens = bmesh.new(), bmesh.new()
    for (px, py, pz), (nx, ny, nz) in packs:
        r = (abs(nz), 0, abs(nx))
        box(hous, px - r[0] * 0.17, px + nx * 0.16 + r[0] * 0.17, py - 0.13, py + 0.13, pz - r[2] * 0.17, pz + nz * 0.16 + r[2] * 0.17)
        box(lens, px + nx * 0.02 - r[0] * 0.13, px + nx * 0.15 + r[0] * 0.13, py - 0.15, py - 0.13, pz + nz * 0.02 - r[2] * 0.13, pz + nz * 0.15 + r[2] * 0.13)
        lamp_light((px + nx * 0.1, py - 0.2, pz + nz * 0.1), 140.0, 0.1, kind="SPOT", aim=(nx * 0.55, -0.83, nz * 0.55), cone=130.0, color=(1.0, 0.74, 0.46))
    finish("decor_wall_packs", hous, "Metal_Dark")
    finish("decor_wall_pack_lenses", lens, "Lamp_Emit")
    # a STAIRS sign beside the door
    panel("decor_bulkhead_sign", "Signs", (x0 - 0.012, 1.6, zc - 0.95), "-x", 0.36, 0.18, SIGN_UV["stairs"])
    # the antennas: a mast with three dipoles and a red beacon on the bulkhead's roof, a dish beside it
    mx, mz = x1 - 0.6, z1 - 0.6
    def mast(bm):
        cyl(bm, (mx, h, mz), (mx, h + 4.6, mz), 0.045, 0.03, 10)
        for k, y in enumerate((h + 2.2, h + 3.1, h + 3.9)):
            ln = 1.3 - 0.3 * k
            cyl(bm, (mx - ln / 2, y, mz), (mx + ln / 2, y, mz), 0.012, 0.012, 6)
            cyl(bm, (mx, y, mz - ln / 3), (mx, y, mz + ln / 3), 0.012, 0.012, 6)
        cyl(bm, (mx - 0.15, h + 0.08, mz - 0.15), (mx + 0.15, h + 0.08, mz + 0.15), 0.02, 0.02, 6)
        box(bm, mx - 0.18, mx + 0.18, h, h + 0.05, mz - 0.18, mz + 0.18)
        dx, dz = x0 + 0.8, z0 + 0.9
        cyl(bm, (dx, h, dz), (dx, h + 0.7, dz), 0.03, 0.03, 8)
        box(bm, dx - 0.2, dx + 0.2, h, h + 0.04, dz - 0.2, dz + 0.2)
    part("decor_antenna_mast", "Steel_Galv", mast, smooth=True, sharp_deg=50)
    def dish(bm):
        dx, dz = x0 + 0.8, z0 + 0.9
        bmesh.ops.create_uvsphere(bm, u_segments=18, v_segments=8, radius=0.45,
                                  matrix=Matrix.Translation(B((dx - 0.12, h + 0.95, dz + 0.12))) @ Matrix.Rotation(math.radians(-55), 4, "Z")
                                  @ Matrix.Rotation(math.radians(70), 4, "X") @ Matrix.Diagonal((1, 1, 0.22, 1)))
    part("decor_antenna_dish", "Coping", dish, smooth=True, sharp_deg=60)
    part("decor_beacon", "Beacon_Emit", lambda bm: sphere(bm, (mx, h + 4.66, mz), 0.06, 10))
    lamp_light((mx, h + 4.66, mz), 3.0, 0.05, color=(1.0, 0.08, 0.05))


def roof_tank():
    """The water tank: a timber tank bound with iron hoops under a shallow cone roof, on a steel stand with a deck, and a ladder up its south side."""
    b = BOX["Water_Tank"]
    x0, x1, z0, z1, h = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    r, ys, yt = 1.36, 0.95, h - 0.22
    def stand(bm):
        for sx in (-1, 1):
            for sz in (-1, 1):
                px, pz = cx + sx * 1.15, cz + sz * 1.15
                box(bm, px - 0.08, px + 0.08, 0.0, ys, pz - 0.08, pz + 0.08)
                box(bm, px - 0.16, px + 0.16, 0.0, 0.03, pz - 0.16, pz + 0.16)
        for sz in (-1, 1):
            box(bm, cx - 1.23, cx + 1.23, ys - 0.14, ys - 0.02, cz + sz * 1.15 - 0.06, cz + sz * 1.15 + 0.06)
        for sx in (-1, 1):
            box(bm, cx + sx * 1.15 - 0.06, cx + sx * 1.15 + 0.06, ys - 0.14, ys - 0.02, cz - 1.23, cz + 1.23)
        box(bm, cx - 1.3, cx + 1.3, ys - 0.02, ys + 0.03, cz - 1.3, cz + 1.3)
        for sx in (-1, 1):                                         # the cage: four angle posts at the box's corners up to a ring of beams
            for sz in (-1, 1):
                px, pz = cx + sx * (1.5 - 0.035), cz + sz * (1.5 - 0.035)
                box(bm, px - 0.035, px + 0.035, 0.0, h, pz - 0.035, pz + 0.035)
                box(bm, px - 0.05, px + 0.05, 0.0, 0.02, pz - 0.05, pz + 0.05)
        for sz in (-1, 1):
            box(bm, cx - 1.5, cx + 1.5, h - 0.12, h - 0.06, cz + sz * 1.465 - 0.03, cz + sz * 1.465 + 0.03)
            box(bm, cx - 1.5, cx + 1.5, ys - 0.1, ys - 0.04, cz + sz * 1.465 - 0.03, cz + sz * 1.465 + 0.03)
        for sx in (-1, 1):
            box(bm, cx + sx * 1.465 - 0.03, cx + sx * 1.465 + 0.03, h - 0.12, h - 0.06, cz - 1.5, cz + 1.5)
            box(bm, cx + sx * 1.465 - 0.03, cx + sx * 1.465 + 0.03, ys - 0.1, ys - 0.04, cz - 1.5, cz + 1.5)
        for sx in (-1, 1):                                         # cross braces
            cyl(bm, (cx + sx * 1.15, 0.1, cz - 1.15), (cx + sx * 1.15, ys - 0.15, cz + 1.15), 0.02, 0.02, 6)
            cyl(bm, (cx - 1.15, 0.1, cz + sx * 1.15), (cx + 1.15, ys - 0.15, cz + sx * 1.15), 0.02, 0.02, 6)
    part("Tank_Stand", "Steel_Paint", stand)
    def staves(bm):
        cyl(bm, (cx, ys + 0.03, cz), (cx, yt, cz), r, r * 0.97, 36)
    part("Tank_Body", "Tank_Wood", staves, smooth=True, sharp_deg=30)
    def hoops(bm):
        for y in np.linspace(ys + 0.18, yt - 0.12, 5):
            rr = r - (y - ys) / (yt - ys) * r * 0.03 + 0.012
            cyl(bm, (cx, y - 0.025, cz), (cx, y + 0.025, cz), rr, rr, 36, cap=False)
        cyl(bm, (cx, yt + 0.02, cz), (cx, h, cz), r * 0.99, 0.06, 36)
        cyl(bm, (cx + 0.6, h - 0.12, cz), (cx + 0.6, h + 0.05, cz), 0.07, 0.07, 10)
    part("Tank_Hoops_Roof", "Iron_Black", hoops, smooth=True, sharp_deg=40)
    def ladder(bm):
        lz = z1 - 0.06
        for sx in (-1, 1):
            box(bm, cx + sx * 0.22 - 0.015, cx + sx * 0.22 + 0.015, 0.0, yt + 0.5, lz - 0.02, lz + 0.02)
        for y in np.arange(0.3, yt + 0.3, 0.3):
            cyl(bm, (cx - 0.22, y, lz), (cx + 0.22, y, lz), 0.012, 0.012, 6)
        cyl(bm, (cx + 0.5, 0.0, cz + 1.0), (cx + 0.5, ys, cz + 1.0), 0.06, 0.06, 10)     # the outlet pipe down into the roof
    part("Tank_Ladder", "Steel_Galv", ladder, smooth=False)


def roof_hvac():
    """Two HVAC units, each filling its greybox box: a packaged unit with corrugated louvred sides and two fans on top, a condenser with one big fan."""
    for n in ("HVAC", "HVAC_2"):
        b = BOX[n]
        x0, x1, z0, z1, h = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]
        part(f"{n}_Base", "Steel_Paint", lambda bm, x0=x0, x1=x1, z0=z0, z1=z1: box(bm, x0, x1, 0.0, 0.12, z0, z1))
        part(f"{n}_Body", "HVAC_Sheet", lambda bm, x0=x0, x1=x1, z0=z0, z1=z1, h=h: box(bm, x0 + 0.04, x1 - 0.04, 0.12, h - 0.06, z0 + 0.04, z1 - 0.04))
        part(f"{n}_Top", "Steel_Galv", lambda bm, x0=x0, x1=x1, z0=z0, z1=z1, h=h: box(bm, x0 + 0.02, x1 - 0.02, h - 0.06, h - 0.01, z0 + 0.02, z1 - 0.02))
        fans = [((x0 + x1) / 2 + d, (z0 + z1) / 2) for d in ((-0.72, 0.72) if n == "HVAC" else (0.0,))]
        rad = 0.55 if n == "HVAC" else 0.78
        def grilles(bm, fans=fans, rad=rad, h=h):
            for fx, fz in fans:
                cyl(bm, (fx, h - 0.01, fz), (fx, h + 0.05, fz), rad, rad, 32, cap=False)
                cyl(bm, (fx, h - 0.005, fz), (fx, h + 0.0, fz), rad - 0.02, rad - 0.02, 32)
                for k in range(6):
                    a = k * math.pi / 6
                    cyl(bm, (fx - math.cos(a) * rad, h + 0.04, fz - math.sin(a) * rad), (fx + math.cos(a) * rad, h + 0.04, fz + math.sin(a) * rad), 0.006, 0.006, 4)
        part(f"{n}_Fans", "Metal_Dark", grilles, smooth=True, sharp_deg=50)
        if n == "HVAC":                                           # its electrical box and conduit on the south side
            part(f"{n}_Panel", "Steel_Galv", lambda bm, x0=x0, z1=z1: box(bm, x0 + 0.3, x0 + 0.8, 0.45, 1.0, z1 - 0.04, z1 - 0.0))


def roof_safe_house_skin():
    """The safe house's outside, this scene's own SH_Outside: the kit's skin (its N, W, E, top and south faces round the doorway), 1 cm outside it, so
    this bake lights it and the kit's own skin (lit only by its lantern and the night) is hidden behind it. One piece per wall, so each stands on
    its collider."""
    X0, X1, Z0, Z1, Y1 = SH[0] - SKIN, SH[1] + SKIN, SH[2] - SKIN, SH[3] + SKIN, SH[4] + SKIN
    dx0, dx1, dh = -8.5, -7.5, G.DOOR_H
    faces = {
        "N": [((X0, 0, Z0), (X1, 0, Z0), (X1, Y1, Z0), (X0, Y1, Z0), (0, 0, -1))],
        "W": [((X0, 0, Z0), (X0, 0, Z1), (X0, Y1, Z1), (X0, Y1, Z0), (-1, 0, 0))],
        "E": [((X1, 0, Z0), (X1, 0, Z1), (X1, Y1, Z1), (X1, Y1, Z0), (1, 0, 0))],
        "Top": [((X0, Y1, Z0), (X1, Y1, Z0), (X1, Y1, Z1), (X0, Y1, Z1), (0, 1, 0))],
        "S_W": [((X0, 0, Z1), (dx0, 0, Z1), (dx0, Y1, Z1), (X0, Y1, Z1), (0, 0, 1))],
        "S_E": [((dx1, 0, Z1), (X1, 0, Z1), (X1, Y1, Z1), (dx1, Y1, Z1), (0, 0, 1))],
        "S_Head": [((dx0, dh, Z1), (dx1, dh, Z1), (dx1, Y1, Z1), (dx0, Y1, Z1), (0, 0, 1))],
    }
    for k, fs in faces.items():
        bm = bmesh.new()
        for *pts, nrm in fs:
            f = quad(bm, *pts)
            f.normal_update()
            if f.normal.dot(B(nrm)) < 0:
                f.normal_flip()
        finish(f"SH_Outside_{k}", bm, "SH_Outside", recalc=False)
    # an old aerial on the safe house's roof
    part("decor_sh_aerial", "Steel_Galv", lambda bm: [cyl(bm, (-6.0, Y1, -10.2), (-6.0, Y1 + 1.8, -10.2), 0.025, 0.02, 8)] +
         [cyl(bm, (-6.0 - 0.5 + 0.08 * k, Y1 + 1.4 + 0.08 * k, -10.2), (-6.0 + 0.5 - 0.08 * k, Y1 + 1.4 + 0.08 * k, -10.2), 0.008, 0.008, 4) for k in range(5)])


def roof_leaves():
    d = DOORS["DoorLeaf_floor_3"]
    p = d["props"]
    bm = leaf_mesh(p["width"], p["height"], DOOR_STAIR_UV, STEEL_PIX, knob=(0.09, 1.02))
    old = set(bm.faces)
    uvl = bm.loops.layers.uv["UVMap"]
    w = p["width"]
    pu0, pv0, pu1, pv1 = plate_uv(11)
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, 0.028, 1.62)) @ Matrix.Diagonal((0.24, 0.006, 0.09, 1)))
    for f in bm.faces:
        if f in old:
            continue
        f.normal_update()
        for lp in f.loops:
            if f.normal.y > 0.9:
                x, z = lp.vert.co.x, lp.vert.co.z
                lp[uvl].uv = (pu0 + (pu1 - pu0) * (1 - (x - (w / 2 - 0.12)) / 0.24), pv0 + (pv1 - pv0) * ((z - 1.575) / 0.09))
            else:
                lp[uvl].uv = STEEL_PIX
    leaf_object(d, bm)
    OWN_LEAVES.add("floor_3")


def build_roof():
    roof_floor()
    roof_parapet()
    roof_bulkhead()
    roof_tank()
    roof_hvac()
    roof_safe_house_skin()
    # the kit's lantern by the safe house's door: its light, for this bake (the kit's own lamp data is in its Lights collection)


# ================================================================ lights and the world
MOON_BEARING, MOON_ELEV = 135.0, 34.0          # the moon: south-east (compass degrees from north, toward east), 34 degrees up: the backdrop's moon too
MOON_W = 0.30                                   # its strength (W/m2)
MOON_COLOR = (0.74, 0.82, 1.0)
GLOW = [(0.0, (0.018, 0.014, 0.010)), (0.47, (0.050, 0.036, 0.026)), (0.5, (0.20, 0.115, 0.060)), (0.53, (0.15, 0.090, 0.060)),
        (0.58, (0.070, 0.055, 0.060)), (0.70, (0.026, 0.030, 0.052)), (1.0, (0.009, 0.012, 0.028))]      # the night sky by height: the city's glow low down
GLOW_STRENGTH = 1.0
BACKDROP_NIGHT = ROOT / "world/backdrops/roof_night.webp"


def moon_dir():
    b, e = math.radians(MOON_BEARING), math.radians(MOON_ELEV)
    return (math.cos(e) * math.sin(b), math.sin(e), -math.cos(e) * math.cos(b))     # game, toward the moon


def add_lights():
    c = bpy.data.collections.get("Lights_Lamps") or bpy.data.collections.new("Lights_Lamps")
    if c.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(c)
    for i, (kind, pos, w, col, r, aim, cone) in enumerate(LIGHTS):
        d = bpy.data.lights.new(f"Lamp_{i:02d}", kind)
        d.energy, d.color = w, col
        d.shadow_soft_size = r
        ob = bpy.data.objects.new(f"Lamp_{i:02d}", d)
        ob.location = B(pos)
        if kind == "SPOT":
            d.spot_size, d.spot_blend = math.radians(cone), 0.7
            ob.rotation_euler = B(aim).to_track_quat("-Z", "Y").to_euler()
        c.objects.link(ob)
    if SCENE == "roof":
        d = bpy.data.lights.new("Moon", "SUN")
        d.energy, d.color, d.angle = MOON_W, MOON_COLOR, math.radians(0.6)
        ob = bpy.data.objects.new("Moon", d)
        md = moon_dir()
        ob.rotation_euler = B((-md[0], -md[1], -md[2])).to_track_quat("-Z", "Y").to_euler()
        c.objects.link(ob)


def setup_world():
    sc = bpy.context.scene
    w = bpy.data.worlds.new("Night")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    if SCENE == "floor_3":
        bg.inputs["Color"].default_value = (0.004, 0.004, 0.005, 1)
        bg.inputs["Strength"].default_value = 1.0
        return
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = -1.0, 1.0
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    while len(els) > 1:
        els.remove(els[-1])
    els[0].position, els[0].color = GLOW[0][0], (*GLOW[0][1], 1)
    for pos, col in GLOW[1:]:
        e = els.new(pos)
        e.color = (*col, 1)
    nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
    sky = ramp.outputs["Color"]
    if BACKDROP_NIGHT.exists():                          # the stills see the skyline (the backdrop) behind the roof; the bake sees the glow only
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(str(BACKDROP_NIGHT))
        env.name = "BACKDROP"
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.vector_type = "VECTOR"
        mp.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(-90.0))     # the picture's middle is north (Blender +Y), Blender's is +X
        nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
        lp = nt.nodes.new("ShaderNodeLightPath")
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.name = "CAMERA_SEES"
        nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
        nt.links.new(sky, mix.inputs[6])
        nt.links.new(env.outputs["Color"], mix.inputs[7])
        sky = mix.outputs[2]
    nt.links.new(sky, bg.inputs["Color"])
    bg.inputs["Strength"].default_value = GLOW_STRENGTH


def camera_sees_backdrop(on):
    w = bpy.context.scene.world
    m = w.node_tree.nodes.get("CAMERA_SEES") if w else None
    if m is not None:
        lp = next(n for n in w.node_tree.nodes if n.type == "LIGHT_PATH")
        for l in list(m.inputs[0].links):
            w.node_tree.links.remove(l)
        if on:
            w.node_tree.links.new(lp.outputs["Is Camera Ray"], m.inputs[0])
        else:
            m.inputs[0].default_value = 0.0


def set_emit(mname, strength):
    m = bpy.data.materials.get(mname)
    if m:
        next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Emission Strength"].default_value = strength


HIDE_KIT = ("SH_Exterior_",)                    # the kit's own safe-house skin: this scene's SH_Outside replaces it (bake and stills)


def kit_visibility():
    for o in KIT_C.objects if KIT_C else bpy.data.collections["Kit"].objects:
        if o.name.startswith(HIDE_KIT):
            o.hide_render = True


# ================================================================ build
def build_all():
    global ART, KIT_C, DOORS_C, LAYOUT_C
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.lights, bpy.data.cameras):
        for d in list(coll):
            coll.remove(d)
    sc = bpy.context.scene
    ART, KIT_C, DOORS_C, LAYOUT_C = (bpy.data.collections.new(n) for n in ("Art", "Kit", "Doors", "Layout"))
    for c in (ART, KIT_C, DOORS_C, LAYOUT_C):
        sc.collection.children.link(c)
    gen = make_generated()
    make_materials(gen)
    if SCENE == "floor_3":
        link_emission_texture("Exit_Emit", gen["exit"], 2.0)
        f3_leaves()
        place_kit()
        build_floor3()
    else:
        roof_leaves()
        place_kit()
        build_roof()
    build_layout()
    add_lights()
    setup_world()
    kit_visibility()
    LAYOUT_C.hide_render = True
    tris = sum(len(p.vertices) - 2 for o in ART.objects for p in o.data.polygons)
    print(f"ART {len(ART.objects)} objects, about {tris} triangles; {len(LIGHTS)} lamps; kit stand-ins {len(KIT_C.objects)}; leaves {len(DOORS_C.objects)}")


# ---------------------------------------------------------------- layout file and the layout check
def stage_layout():
    import export_scene
    export_scene.write(SCENE, ROOT / f"world/{SCENE}.json")


def kit_component_parts():
    """The kit's stand-ins as the kit's own layout check reads them (tools/blender/build_kit.py, component_parts): one box per connected piece of
    each mesh, since a kit mesh holds many separate boxes (the car's four walls); its door leaves (Leaf_*, LiftLeaf_*) are left out."""
    out = []
    for ob in bpy.data.collections["Kit"].all_objects:
        if ob.type != "MESH" or ob.hide_render or str(ob.get("node", "")).startswith(("Leaf_", "LiftLeaf_")) or ob.name.startswith(("Leaf_", "LiftLeaf_")):
            continue
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        seen, k = set(), 0
        for v in bm.verts:
            if v.index in seen:
                continue
            stack, isl = [v], []
            seen.add(v.index)
            while stack:
                a = stack.pop()
                isl.append(a)
                for e in a.link_edges:
                    b = e.other_vert(a)
                    if b.index not in seen:
                        seen.add(b.index)
                        stack.append(b)
            g = [(p.x, p.z, -p.y) for p in (ob.matrix_world @ a.co for a in isl)]
            k += 1
            out.append({"name": f"{ob.name}#{k}", "min": [round(min(q[i] for q in g), 4) for i in range(3)], "max": [round(max(q[i] for q in g), 4) for i in range(3)]})
        bm.free()
    return out


def stage_check():
    """tools/blender/check_layout.py's rules on the Art collection and the kit's stand-ins together (the kit's colliders are covered by its own art);
    the kit's sliding leaves (LiftLeaf_*) are doors, as this scene's leaves are (the Doors collection), so they are left out."""
    import check_layout
    world = json.loads((ROOT / f"world/{SCENE}.json").read_text())
    parts = check_layout.blender_parts("Art") + kit_component_parts()
    print(f"layout check: scene {SCENE}, {len(parts)} visible meshes (Art and the kit's stand-ins), {len(world['colliders'])} colliders")
    bad = check_layout.report(check_layout.check(parts, world, {}))
    print("CHECK_LAYOUT exit", 1 if bad else 0)


# ---------------------------------------------------------------- bake
GROUPS = {
    "floor_3": [["Floor_Oak", "Floor_Runner", "Wall_Paper", "Wall_Wainscot", "Ceiling_Plaster", "Trim_Paint", "Stair_Wall", "Stair_Concrete"],
                ["Steel_Paint", "Radiator_Paint", "Brass", "Metal_Dark", "Prints", "Frame_Wood", "Paint_Palette", "Signs"]],
    "roof": [["Roof_Gravel", "Roof_Tar", "Roof_Pavers", "Brick", "Coping", "SH_Outside", "Stair_Wall", "Stair_Concrete"],
             ["Steel_Paint", "Steel_Galv", "HVAC_Sheet", "Tank_Wood", "Iron_Black", "Metal_Dark", "Signs"]],
}[SCENE]
PAGES = {"floor_3": [2048, 1024], "roof": [2048, 1024]}[SCENE]
LEAVES_PAGE = 1
UV_SCALE = {"floor_3": {"Ceiling_Plaster": 0.55, "Brass": 0.4, "Metal_Dark": 0.4, "Paint_Palette": 0.4, "Stair_Concrete": 0.8, "Trim_Paint": 0.8},
            "roof": {"Roof_Floor": 1.0, "Roof_Tar": 0.8, "Iron_Black": 0.5, "Metal_Dark": 0.5, "Stair_Wall": 0.35, "Stair_Concrete": 0.35}}[SCENE]
TWO_SIDED = ()
CULL_SKIP = {"floor_3": (), "roof": ("Stair_Bulkhead", "HVAC", "HVAC_2", "Water_Tank")}[SCENE]


def region(P):
    """Is each game point (n, 3) inside the scene's visible volume (where a camera can be, or see)?"""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    e = 1e-3
    if SCENE == "roof":
        shaft = (x >= BH["min"][0] - e) & (x <= BH["max"][0] + e) & (z >= BH["min"][2] - e) & (z <= BH["max"][2] + e) & (y >= -3.0 - e)
        return ((np.abs(x) <= A + 0.3 + e) & (np.abs(z) <= A + 0.3 + e) & (y >= -G.SLAB - e)) | shaft
    corr = (np.abs(x) <= CX + T + e) & (np.abs(z) <= CZ + T + e) & (y >= -G.SLAB - e) & (y <= CH + 0.2 + e)
    stair = (x >= CX - e) & (x <= 26.8 + e) & (np.abs(z) <= 1.2 + e) & (y >= -G.SLAB - e) & (y <= 6.2 + e)
    alc = np.zeros(len(P), bool)
    for n, b in BOX.items():
        if n.startswith("Alcove_Floor"):
            alc |= (x >= b["min"][0] - e) & (x <= b["max"][0] + e) & (z >= b["min"][2] - e) & (z <= b["max"][2] + e) & (y >= -G.SLAB - e) & (y <= 2.6 + e)
    lift = (x >= -22.6) & (x <= -CX) & (np.abs(z) <= 1.3) & (y >= -0.3) & (y <= 2.6)
    return corr | stair | alc | lift


def hidden_points(P):
    bxs = [b for b in GB.boxes if b["col"] and b["name"] not in CULL_SKIP]
    e = 1e-3
    mn = np.array([b["min"] for b in bxs]) + e
    mx = np.array([b["max"] for b in bxs]) - e
    buried = np.concatenate([((Q[:, None, :] > mn[None]) & (Q[:, None, :] < mx[None])).all(-1).any(-1) for Q in np.array_split(P, max(1, len(P) // 20000))])
    return buried | ~region(P)


def cull(bm, mname, oname):
    """Drop faces never seen: a face whose points 1 cm in front of it (its middle and its corners, pulled 5% in) are all hidden: inside a collider,
    or outside the scene's volume (the walls' backs toward the rooms, the slabs' undersides, the ceiling's top)."""
    if mname in TWO_SIDED or not bm.faces:
        return
    bm.normal_update()
    faces = list(bm.faces)
    pts, owner = [], []
    for i, f in enumerate(faces):
        c = f.calc_center_median()
        n = f.normal
        for v in [c] + [c + (lv.co - c) * 0.95 for lv in f.verts]:
            q = v + n * 0.01
            pts.append((q.x, q.z, -q.y))
            owner.append(i)
    hid = hidden_points(np.array(pts))
    own = np.array(owner)
    allh = np.ones(len(faces), bool)
    np.logical_and.at(allh, own, hid)
    bmesh.ops.delete(bm, geom=[f for f, h in zip(faces, allh) if h], context="FACES")


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
        tmp.transform(ob.matrix_world)
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
        o.hide_set(False)
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
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        if o.name in UV_SCALE:
            d = o.data.uv_layers["lightmap"].data
            us = np.array([x.uv for x in d]) * UV_SCALE[o.name]
            d.foreach_set("uv", us.ravel())
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / page, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    plain = [o for o in objs if o.name not in UV_SCALE]
    a3 = sum(area3d(o) for o in plain)
    au = sum(uv_area(o, "lightmap") for o in plain)
    dens = page * math.sqrt(au / max(a3, 1e-9))
    small = {o.name: round(page * math.sqrt(uv_area(o, "lightmap") / max(1e-9, area3d(o))), 1) for o in objs if o.name in UV_SCALE}
    print(f"  page {page}: {a3:.1f} m2, {dens:.1f} px/m; scaled: {small}")
    return page, dens, small


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


def bake_page(n, objs, S, samples):
    bpy.context.scene.cycles.samples = samples
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


def stage_bake():
    import time
    stage_work()
    exp = make_export_objects()
    leaves = sorted(bpy.data.collections["Doors"].objects, key=lambda o: o.name)
    bpy.data.collections["Art"].hide_render = True
    bpy.data.collections["Art"].hide_viewport = True
    bpy.data.collections["Layout"].hide_render = True
    kit_visibility()
    camera_sees_backdrop(False)
    setup_cycles(SAMPLES, bake=True)
    set_emit("Lamp_Emit", LAMP_EMIT)
    report = {}
    for n, mats in enumerate(GROUPS):
        objs = [exp[m] for m in mats if m in exp] + (leaves if n == LEAVES_PAGE else [])
        print(f"lightmap {n}: {[o.name for o in objs]}")
        S, dens, small = lightmap_uv(objs, PAGES[n])
        t0 = time.time()
        rgb = bake_page(n, objs, S, SAMPLES)
        peak = rgb.max(axis=2)
        sel = peak > 1e-5
        pc = np.percentile(peak[sel], [50, 90, 99, 99.5, 100]) if sel.any() else [1.0] * 5
        print(f"  texel percentiles p50 p90 p99 p99.5 max:", [round(float(v), 4) for v in pc])
        np.save(stage_work() / f"{SCENE}_{n}_raw.npy", rgb.astype(np.float16))
        out = np.ones((S, S, 4), np.float32)
        out[..., :3] = encode(rgb, SCENE)
        png = bpy.data.images.new(f"LM_{n}_png", S, S, alpha=False)
        png.colorspace_settings.name = "Non-Color"
        png.pixels.foreach_set(out.ravel())
        png.filepath_raw = str(stage_work() / f"{SCENE}_{n}.png")
        png.file_format = "PNG"
        png.save()
        bpy.data.images.remove(png)
        report[n] = {"map": n, "set": "night", "size": S, "curve_G_C": list(CURVE[SCENE]), "px_per_m": round(dens, 1), "px_per_m_scaled": small,
                     "p50_p90_p99_p995_max": [round(float(v), 4) for v in pc], "samples": SAMPLES, "device": bpy.context.scene.cycles.device,
                     "seconds": round(time.time() - t0), "materials": [m for m in mats if m in exp] + ([o.name for o in leaves] if n == LEAVES_PAGE else [])}
        print("  baked", report[n])
    (stage_work() / "lightmaps.json").write_text(json.dumps(report, indent=1))
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Art"].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    camera_sees_backdrop(True)
    save_blend()


def set_intensities():
    rep = json.loads((stage_work() / "lightmaps.json").read_text())
    for idx, r in rep.items():
        for nm in r["materials"]:
            ob = bpy.data.objects.get(nm)
            mats = [bpy.data.materials.get(nm)] if bpy.data.materials.get(nm) else [s.material for s in ob.material_slots] if ob else []
            for m in mats:
                if m is None:
                    continue
                m["lightmap"] = LM_URL.format(idx)
                m["lightmap_intensity"] = round(math.pi * CURVE[SCENE][1] * CAP[SCENE].get(m.name, 1.0), 4)


# ---------------------------------------------------------------- privacy: the saved file and the GLB carry no paths, names or stamps
KEEP_PROPS = {"lightmap", "lightmap_intensity"}
SYS_KEEP = ("cycles", "eevee")


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


def scrub_private(keep_layout=True):
    kinds = ("scenes", "worlds", "objects", "meshes", "materials", "collections", "cameras", "lights", "images", "node_groups", "screens",
             "window_managers", "workspaces", "libraries")
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
                    if kind == "objects" and st is idb and k == "node":
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
    for lib in bpy.data.libraries:
        p = Path(bpy.path.abspath(lib.filepath))
        try:
            set_path(lib, "filepath", "//" + os.path.relpath(p, base).replace("\\", "/"))
        except ValueError:
            pass
    scrub_ui_paths()
    wm = bpy.context.window_manager
    for op in ("import_scene.gltf", "export_scene.gltf", "wm.save_as_mainfile", "wm.save_mainfile", "wm.open_mainfile", "image.save_as", "wm.append"):
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
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    scrub_private()
    bpy.ops.wm.save_mainfile(compress=True)


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
    set_emit("Lamp_Emit", LAMP_EMIT)
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
    cam.clip_start, cam.clip_end = 0.05, 400
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
    if SCENE == "floor_3":
        a = next(e for e in GB.empties if e["name"] == "Arrive_lift")["pos"]
        return {"1_arrival": ((a[0], 1.55, a[2]), (a[0] + 6, 1.45, a[2]), 72.0),
                "2_wide": ((17.6, 1.6, 0.55), (-6.0, 1.15, -0.3), 64.0),
                "3_detail": ((-9.6, 1.5, 0.7), (-12.6, 1.35, -1.1), 68.0),
                "4_stairs": ((19.2, 1.55, 0.3), (24.5, 3.4, -0.1), 74.0)}, ((0.0, 9.0, 0.0), 46.0)
    a = next(e for e in GB.empties if e["name"] == "Arrive_floor_3")["pos"]
    return {"1_arrival": ((a[0], 1.55, a[2]), (a[0] - 6, 1.6, a[2] - 2.5), 72.0),
            "2_wide": ((10.8, 1.7, 10.8), (-4.0, 1.0, -5.0), 74.0),
            "3_detail": ((-5.2, 1.55, -2.2), (-8.0, 1.4, -6.0), 66.0),
            "4_north": ((0.0, 1.55, 6.0), (0.0, 2.6, -12.0), 76.0)}, ((0.0, 30.0, 0.0), 26.5)


def stage_render():
    sc = bpy.context.scene
    STILLS.mkdir(parents=True, exist_ok=True)
    scrub_private()
    for c in ("Export", "Layout"):
        if c in bpy.data.collections:
            bpy.data.collections[c].hide_render = True
            bpy.data.collections[c].hide_viewport = True
    kit_visibility()
    camera_sees_backdrop(True)
    set_emit("Lamp_Emit", LAMP_EMIT)
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
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    sh, (pc, ortho) = shots()
    cams = {k: look_cam(k, p, t, f) for k, (p, t, f) in sh.items()}
    plan = look_cam("plan", pc, None, ortho=ortho)
    plan.rotation_euler = (0, 0, 0)
    arts = list(bpy.data.collections["Art"].objects) + list(bpy.data.collections["Doors"].objects) + list(bpy.data.collections["Kit"].objects)
    ceilings = [o for o in arts if o.name.startswith(("Corridor_Ceiling", "Alcove_Ceiling", "Stairwell_Ceiling", "decor_cornice", "Bulkhead_Roof", "Bulkhead_Lip",
                                                     "decor_antenna", "decor_beacon", "SH_Outside_Top", "decor_sh_aerial", "decor_alcove_lights", "decor_mats_and"))
                or (o.name.startswith(("Car_Ceiling", "SH_Ceiling")))]
    todo = [(k, v, (1920, 1080)) for k, v in cams.items()] + [("5_plan", plan, (2400, 900) if SCENE == "floor_3" else (1600, 1600))]
    if SCENE == "floor_3":
        plan.data.ortho_scale = 50.0
        plan.location = B((3.3, 9.0, 0.0))
    for key, cam, (w, h) in todo:
        if which not in ("all", key) and not (which == "review" and key in ("1_arrival", "2_wide", "3_detail")):
            continue
        sc.camera = cam
        sc.view_settings.exposure = expo + (1.0 if key == "5_plan" else 0.0)
        for o in arts:
            o.visible_camera = not o.hide_render
        if key == "5_plan":
            for o in ceilings:
                o.visible_camera = False
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, arg("--scale", 100, int)
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        to_docs = key in ("1_arrival", "2_wide", "3_detail") and not arg("--work-stills")
        path = STILLS / f"{key}.jpg" if to_docs else stage_work() / f"{key}.jpg"
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


def open_collections():
    global ART, KIT_C, DOORS_C, LAYOUT_C
    ART, KIT_C, DOORS_C, LAYOUT_C = (bpy.data.collections.get(n) for n in ("Art", "Kit", "Doors", "Layout"))


if __name__ == "__main__":
    ST = set(STAGE.split(","))                         # several stages in one run: --stage art,render
    if ST & {"art"}:
        build_all()
        save_blend()
    else:
        open_collections()
    if ST & {"layout", "art"}:
        stage_layout()
    if ST & {"check", "art"}:
        stage_check()
    if ST & {"bake"}:
        stage_bake()
    if ST & {"export"}:
        stage_export()
    if ST & {"render"}:
        stage_render()
