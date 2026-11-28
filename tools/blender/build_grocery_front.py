"""Dresses and lights the grocery's `aisles` and `second_floor` (docs/BLENDER_AREAS.md, section 2, step 2), bakes a day set and a night set for
each, and exports world/<scene>.glb and world/<scene>.json.

Re-runnable, from the repo root (one scene a run, `--scene aisles` or `--scene second_floor`):

    blender -b --python tools/blender/build_grocery_front.py -- --scene aisles --stage art         (build, save blender/scenes/aisles.blend,
                                                                                                    write world/aisles.json, run the layout check)
    blender -b blender/scenes/aisles.blend --python tools/blender/build_grocery_front.py -- --scene aisles --stage bake [--samples 512] [--night-samples 768]
    blender -b blender/scenes/aisles.blend --python tools/blender/build_grocery_front.py -- --scene aisles --stage export
    blender -b blender/scenes/aisles.blend --python tools/blender/build_grocery_front.py -- --scene aisles --stage axes
    blender -b blender/scenes/aisles.blend --python tools/blender/build_grocery_front.py -- --scene aisles --stage render [--set night] [--only 1_arrival]
    python tools/blender/pack_scene.py aisles --work work/aisles                                  (WebP lightmaps and textures -> world/)

`--stage` takes a comma list (art,bake,export,axes,render). The work folder is work/<scene> (`--work` changes it; not committed).

The layout is the greybox's: tools/blender/build_grocery_greybox.py `aisles()` and `second_floor()` (imported here; no coordinate of the layout is
typed in) give every collider, door, link, marker and spot. This build puts the art round them and writes the same names (COL_, DoorLeaf_,
Link_/Arrive_, Marker_, Spot_) into the .blend, so tools/blender/export_scene.py writes the same world/<scene>.json as the greybox model does.

The look is main_floor's (tools/blender/build_main_floor.py, read only), so the three rooms read as one store: the cream and grey-green checker
tiles, the sage band under a steel rail, white gondolas with pegboard spines, price rails and red end panels, fluorescent strips on rods, the
lay-in ceiling, glass-door coolers. The same three textures are read from blender/textures/main_floor/ (not copied, not changed).

- aisles: the bigger, repeating room. Long gondolas with shelves at the page's food heights (0.35, 0.95, 1.55 m), wall shelving on the north and
  east walls, dairy coolers on the south wall and freezers on the west wall (under the mezzanine), aisle number boards hung overhead, the red-cart
  clearing left open, the cart corral by the opening, the mezzanine's underside (soffit, beams, columns), its glazed front, the stairs and the
  escalator (stopped: steps, balustrades) up to the landing, the camera heads' brackets, emergency fittings and the EXIT sign.
- second_floor: the mezzanine. Homeware gondolas (lamps, cushions, plates, kitchenware), two display tables, the closed cafe (shutter down,
  chairs up on the tables, a drinks fridge), the glass balustrade and glazed front with its two glass doors, the railed landing over the
  stairs and the escalator, and the view down over the aisles (art only, decor_below_*: the hall 5 m below, as the aisles are dressed).

Light: day = the fluorescent strips (`Lamp_Emit`), the coolers and freezers, the EXIT signs; night = the coolers' and freezers' glow and the
emergency heads (`Emergency_Emit`) alone, as `lightmap_night` (the mall entrance's and the hotel lobby's way). The page turns `Lamp_Emit` off at
night and `Emergency_Emit` on. The page draws the food, the carts, the checkout, the camera heads and the night threats: their spots stay clear.
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


SCENE = arg("--scene", "aisles")
assert SCENE in ("aisles", "second_floor"), SCENE
STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 512, int)
NIGHT_SAMPLES = arg("--night-samples", None, int) or 768
DEVICE = arg("--device", "auto")
TEX = ROOT / "blender/textures/main_floor"          # main_floor's three textures, read as they are
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"
MARGIN_PX = 8

GB = G.SCENES[SCENE]()
GA = G.aisles()                                       # the aisles' model: second_floor's view down is built from it, 5 m lower
BOX = {b["name"]: b for b in GB.boxes}
BOXA = {b["name"]: b for b in GA.boxes}
T = G.T
BAND = 1.2                                            # main_floor's sage band and its steel rail
MEZ, LAND = G.MEZ, G.LAND
DY = -MEZ["y"]                                        # second_floor's view down: the aisles are 5 m below


def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


class Room:
    """A room's inner faces (x0..x1, z0..z1, floor y 0 .. h), shifted by oy (the view down), its pieces' name prefix."""
    def __init__(s, x0, x1, z0, z1, h, oy=0.0, pre="", openings=()):
        s.x0, s.x1, s.z0, s.z1, s.h, s.oy, s.pre = x0, x1, z0, z1, h, oy, pre
        s.openings = list(openings)                   # (x0, x1, y0, y1, z0, z1) cut through a wall: inside for the culling

    def face(s, normal):
        return {"+x": s.x0, "-x": s.x1, "+z": s.z0, "-z": s.z1}[normal]


OPEN_S = (G.MF["opening"][0], G.MF["opening"][1], 0.0, G.MF["opening"][2], G.AZ1 - 0.01, G.AZ1 + T + 0.01)
RA = Room(G.AX0, G.AX1, G.AZ0, G.AZ1, G.AH, openings=[OPEN_S])                         # the aisles hall
RB = Room(G.AX0, G.AX1, G.AZ0, G.AZ1, G.AH, oy=DY, pre="decor_below_")                # the same hall, seen from second_floor
RS = Room(MEZ["x0"], MEZ["x1"] - T, MEZ["z0"], MEZ["z1"], MEZ["h"])                   # the mezzanine (its front glass on x -4.2..-4.0)
ROOM = RA if SCENE == "aisles" else RS


# ---------------------------------------------------------------- materials
IMG_CACHE, MATS, TILES = {}, {}, {}


def image(fn, srgb=True):
    key = (fn, srgb)
    if key not in IMG_CACHE:
        im = bpy.data.images.load(str(TEX / fn))
        im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
        IMG_CACHE[key] = im
    return IMG_CACHE[key]


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, diff=None, img=None, tint=None, emit=None, alpha=None, tile=None):
    """A Principled material (main_floor's). `tint` multiplies the diffuse texture (a Mix node set to Multiply: the glTF baseColorFactor);
    emit = (colour, strength), or a number with `img`: the picture is the emission."""
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
        elif emit is None or isinstance(emit, tuple):
            nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
        if emit is not None and not isinstance(emit, tuple):
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


LAMP_EMIT = 9.0           # Lamp_Emit (the strips' diffusers), main_floor's strength: on by day, the page turns it off at night
EMERG_EMIT = 6.0          # Emergency_Emit (the emergency heads' lenses): on at night
COOLER_EMIT = 1.2         # the coolers' and freezers' lit insides (main_floor's): always on
NOLM = ("Lamp_Emit", "Emergency_Emit", "Window_Glass", "Cooler_Lit", "Freezer_Lit", "Sign_Glow", "Rod_Steel")


def make_materials(gen):
    # main_floor's, unchanged
    material("Floor_Tile", diff="floor_tiles_diff.jpg", rough=0.35, tile=1.2)
    material("Ceiling_Tile", diff="ceiling_tile_diff.jpg", rough=0.95, tile=1.2)
    material("Wall_Paint", diff="wall_paint_diff.jpg", tint=(0.86, 0.84, 0.76), rough=0.9, tile=2.6)
    material("Wall_Lower", diff="wall_paint_diff.jpg", tint=(0.42, 0.53, 0.45), rough=0.7, tile=2.6)
    material("Trim_Steel", color=(0.62, 0.62, 0.60), rough=0.35, metal=0.7)
    material("Shelf_Paint", color=(0.80, 0.80, 0.78), rough=0.45, metal=0.2)
    material("Shelf_Back", img=gen["pegboard"], rough=0.6, tile=0.4)
    material("Shelf_Kick", color=(0.10, 0.10, 0.11), rough=0.6)
    material("EndCap_Red", color=(0.50, 0.05, 0.05), rough=0.5)
    material("Price_Rail", color=(0.82, 0.76, 0.48), rough=0.5)
    material("Rail_Steel", color=(0.70, 0.70, 0.70), rough=0.25, metal=0.9)
    material("Frame_Alu", color=(0.14, 0.13, 0.12), rough=0.4, metal=0.6)
    material("Cooler_Frame", color=(0.05, 0.05, 0.055), rough=0.4, metal=0.3)
    material("Light_Housing", color=(0.82, 0.82, 0.80), rough=0.5, metal=0.2)
    material("Metal_Dark", color=(0.05, 0.05, 0.055), rough=0.45, metal=0.8)
    material("Plastic_Black", color=(0.03, 0.03, 0.035), rough=0.35)
    material("Sign_Dept", img=gen["signs"], rough=0.6)
    material("Lamp_Emit", color=(1.0, 1.0, 1.0), rough=0.4, emit=((0.96, 0.98, 1.0), LAMP_EMIT))
    material("Window_Glass", color=(0.80, 0.90, 0.95), rough=0.05, alpha=0.12)
    material("Cooler_Lit", img=gen["cooler"], emit=COOLER_EMIT)
    material("Sign_Glow", img=gen["glow"], emit=2.0)
    # this build's own
    material("Wall_High", diff="wall_paint_diff.jpg", tint=(0.86, 0.84, 0.76), rough=0.9, tile=2.6)          # Wall_Paint above 3.6 m (a lower texel density)
    material("Soffit_Paint", diff="wall_paint_diff.jpg", tint=(0.80, 0.80, 0.78), rough=0.9, tile=2.6)       # the mezzanine's underside, the landing's
    material("Freezer_Lit", img=gen["freezer"], emit=COOLER_EMIT)
    material("Emergency_Emit", color=(0.9, 0.95, 1.0), rough=0.3, emit=((0.85, 0.93, 1.0), EMERG_EMIT))
    material("Plastic_White", color=(0.78, 0.78, 0.76), rough=0.4)
    material("Rod_Steel", color=(0.40, 0.40, 0.40), rough=0.35, metal=0.6)          # rods, handles, tube rails: no lightmap (too thin to hold texels)
    material("Handrail_Black", color=(0.025, 0.025, 0.028), rough=0.5)
    material("Stair_Tread", color=(0.16, 0.16, 0.17), rough=0.8)
    if SCENE == "aisles":
        material("Esc_Tread", img=gen["tread"], rough=0.4, metal=0.5, tile=1.0)
        material("Esc_Riser", img=gen["riser"], rough=0.45, metal=0.5, tile=1.0)
        material("Esc_Clad", color=(0.62, 0.62, 0.60), rough=0.3, metal=0.7)
        material("Comb_Yellow", color=(0.70, 0.52, 0.06), rough=0.5)
    else:
        material("Paint_Palette", img=gen["palette"], rough=0.6, tile=1.0)
        material("Cafe_Wall", diff="wall_paint_diff.jpg", tint=(0.66, 0.40, 0.28), rough=0.85, tile=2.6)
        material("Wood_Light", color=(0.42, 0.26, 0.14), rough=0.5)
        material("Counter_Laminate", color=(0.40, 0.37, 0.33), rough=0.55)                                # main_floor's
        material("Counter_Top", color=(0.66, 0.66, 0.64), rough=0.3, metal=0.8)                             # main_floor's
        material("Shutter_Steel", img=gen["shutter"], rough=0.4, metal=0.6, tile=1.0)
        material("Below_Floor", diff="floor_tiles_diff.jpg", rough=0.35, tile=1.2)                           # the view down: the aisles' own surfaces,
        material("Below_Wall", diff="wall_paint_diff.jpg", tint=(0.86, 0.84, 0.76), rough=0.9, tile=2.6)     # at a lower texel density
        material("Below_Lower", diff="wall_paint_diff.jpg", tint=(0.42, 0.53, 0.45), rough=0.7, tile=2.6)
        material("Below_Ceiling", diff="ceiling_tile_diff.jpg", rough=0.95, tile=1.2)
        material("Below_Stock", img=gen["stock"], rough=0.6, tile=1.0)                                       # stocked shelves, seen from above
        material("Esc_Tread", color=(0.45, 0.45, 0.44), rough=0.4, metal=0.5)
        material("Esc_Clad", color=(0.62, 0.62, 0.60), rough=0.3, metal=0.7)


# ---------------------------------------------------------------- geometry helpers (world space, identity transforms)
OCC_CUR, OCC = [], {}      # every box a piece is built from (Blender coords), by object: the bake drops faces buried inside another box


def cube(bm, gmin, gmax):
    a, b = B(gmin), B(gmax)
    OCC_CUR.append((tuple(min(a[i], b[i]) for i in range(3)), tuple(max(a[i], b[i]) for i in range(3))))
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


def prism(bm, ring_a, ring_b):
    """A solid between two 4-point rings (game points, same order): its two caps and four sides."""
    va = [bm.verts.new(B(p)) for p in ring_a]
    vb = [bm.verts.new(B(p)) for p in ring_b]
    bm.faces.new(va)
    bm.faces.new(list(reversed(vb)))
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new([va[i], vb[i], vb[j], va[j]])


def box_uv(bm, tile):
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
CULL = {}            # object name -> how its unseen faces are dropped before the bake ("up", "down", "wall", "prop", "below", "keep")


def finish(name, bm, mat, coll=None, smooth=False, tile=None, keep_uv=False, recalc=True, cull="prop"):
    for e in bm.edges:
        e.smooth = smooth and len(e.link_faces) == 2 and e.calc_face_angle(0.0) < math.radians(35)
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
    OCC[ob.name] = list(OCC_CUR)
    OCC_CUR.clear()
    CULL[ob.name] = "below" if name.startswith("decor_below_") and cull == "prop" else cull
    return ob


def part(name, mat, build, **kw):
    OCC_CUR.clear()
    bm = bmesh.new()
    build(bm)
    if not bm.faces:
        bm.free()
        return None
    return finish(name, bm, mat, **kw)


RIGHT = {"+x": (0, 0, -1), "-x": (0, 0, 1), "+z": (1, 0, 0), "-z": (-1, 0, 0)}
NORMAL = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}


def panel_face(bm, centre, normal, w, h, uv=(0, 0, 1, 1)):
    r = Vector(RIGHT[normal])
    up = Vector((0, 1, 0))
    c = Vector(centre)
    pts = [c - r * w / 2 - up * h / 2, c + r * w / 2 - up * h / 2, c + r * w / 2 + up * h / 2, c - r * w / 2 + up * h / 2]
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    f = quad(bm, *[tuple(p) for p in pts])
    u0, v0, u1, v1 = uv
    for lp, (s, t) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = (u0 + (u1 - u0) * s, v0 + (v1 - v0) * t)
    return f


def panel(name, mat, centre, normal, w, h, uv=(0, 0, 1, 1), coll=None, cull="keep"):
    """A flat quad facing `normal` ("+x", "-x", "+z", "-z"), w wide, h tall; its UV the rectangle uv, the picture upright."""
    bm = bmesh.new()
    panel_face(bm, centre, normal, w, h, uv)
    return finish(name, bm, mat, coll, keep_uv=True, recalc=False, cull=cull)


def panels(name, mat, items, coll=None, cull="keep"):
    """Several flat quads in one object: items = [(centre, normal, w, h, uv)]."""
    bm = bmesh.new()
    for it in items:
        panel_face(bm, *it)
    return finish(name, bm, mat, coll, keep_uv=True, recalc=False, cull=cull)


def on_wall(R, normal, a, y, d):
    """A game point on R's wall whose inward normal is `normal`: a along it, height y above R's floor, d metres into the room."""
    off = R.face(normal) + (1 if normal[0] == "+" else -1) * d
    return (off, y + R.oy, a) if normal[1] == "x" else (a, y + R.oy, off)


def wall_box(bm, R, normal, a0, a1, y0, y1, d0, d1):
    p, q = on_wall(R, normal, a0, y0, d0), on_wall(R, normal, a1, y1, d1)
    cube(bm, [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)])


def shift(b, oy):
    return [b["min"][0], b["min"][1] + oy, b["min"][2]], [b["max"][0], b["max"][1] + oy, b["max"][2]]


# the palette: 8 x 8 flat swatches; a piece of a palette mesh takes one swatch (its UVs at the swatch's centre)
PAL = {
    "plate_white": (0.86, 0.86, 0.82), "plate_blue": (0.20, 0.32, 0.55), "plate_sage": (0.48, 0.58, 0.48), "plate_terra": (0.66, 0.34, 0.22),
    "mug_yellow": (0.88, 0.70, 0.22), "mug_teal": (0.18, 0.48, 0.48), "mug_red": (0.62, 0.12, 0.10), "mug_cream": (0.86, 0.80, 0.66),
    "cush_mustard": (0.78, 0.56, 0.16), "cush_rose": (0.76, 0.46, 0.48), "cush_navy": (0.14, 0.18, 0.36), "cush_grey": (0.52, 0.52, 0.50),
    "cush_green": (0.24, 0.40, 0.26), "cush_cream": (0.84, 0.80, 0.70), "cush_rust": (0.58, 0.24, 0.12), "cush_teal": (0.16, 0.42, 0.44),
    "shade_linen": (0.86, 0.82, 0.72), "shade_white": (0.90, 0.90, 0.88), "shade_green": (0.30, 0.46, 0.34), "lamp_brass": (0.62, 0.48, 0.22),
    "lamp_black": (0.05, 0.05, 0.05), "lamp_ceramic": (0.70, 0.74, 0.72), "vase_blue": (0.26, 0.38, 0.60), "vase_amber": (0.66, 0.44, 0.14),
    "towel_white": (0.88, 0.88, 0.86), "towel_grey": (0.56, 0.56, 0.54), "towel_sage": (0.56, 0.64, 0.54), "box_kraft": (0.62, 0.48, 0.32),
    "pan_black": (0.07, 0.07, 0.07), "pan_copper": (0.62, 0.34, 0.20), "glass_clear": (0.72, 0.78, 0.78), "jar_cork": (0.56, 0.44, 0.30),
    "cart_red": (0.62, 0.06, 0.05), "cart_grey": (0.36, 0.36, 0.36), "cart_black": (0.04, 0.04, 0.04), "card_white": (0.88, 0.86, 0.80),
    "card_red": (0.60, 0.08, 0.06), "chair_seat": (0.42, 0.26, 0.14), "napkin": (0.80, 0.78, 0.72), "frame_oak": (0.50, 0.36, 0.20),
}
PAL_KEYS = list(PAL)


def pal_uv(key):
    i = PAL_KEYS.index(key)
    return ((i % 8 + 0.5) / 8, 1 - (i // 8 + 0.5) / 8)


class Painter:
    """One palette mesh from many pieces, each piece painted one swatch."""
    def __init__(s):
        OCC_CUR.clear()
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

    def done(s, name, coll=None, smooth=False, cull="prop"):
        if not s.bm.faces:
            s.bm.free()
            return None
        return finish(name, s.bm, "Paint_Palette", coll, smooth=smooth, keep_uv=True, cull=cull)


# ---------------------------------------------------------------- generated images (own work, numpy, fixed seeds)
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
    "&": ["01100", "10010", "10100", "01000", "10101", "10010", "01101"], ":": ["00000", "00100", "00000", "00000", "00000", "00100", "00000"],
    "0": ["01110", "10011", "10101", "10101", "11001", "10001", "01110"], "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00110", "01000", "10000", "11111"], "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["10010", "10010", "10010", "11111", "00010", "00010", "00010"], "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["01110", "10000", "11110", "10001", "10001", "10001", "01110"], "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"], "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    "^": ["00100", "01110", "10101", "00100", "00100", "00100", "00100"],
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


def vnoise(h, w, rng, octaves=5, base=4):
    out, amp, tot = np.zeros((h, w)), 1.0, 0.0
    for k in range(octaves):
        n = base * 2 ** k
        out += amp * rs(rng.random((n + 1, n + 1)), h, w)
        tot += amp
        amp *= 0.5
    return out / tot


def draw_text(img, text, box_, fg, fill=0.7, maxw=0.9):
    """Pixel-font text centred in box (r0, r1, c0, c1) of img, as large as fits."""
    r0, r1, c0, c1 = box_
    cols = len(text) * 6 - 1
    s = max(1, int(min((c1 - c0) * maxw / cols, (r1 - r0) * fill / 7)))
    y = r0 + ((r1 - r0) - 7 * s) // 2
    x = c0 + ((c1 - c0) - cols * s) // 2
    for ch in text:
        for r, row in enumerate(GLYPHS[ch]):
            for c, v in enumerate(row):
                if v == "1":
                    img[y + r * s:y + (r + 1) * s, x + c * s:x + (c + 1) * s] = fg
        x += 6 * s


def pegboard_pixels():
    """main_floor's pegboard: 0.4 m a repeat, a hole every 25 mm."""
    S, step = 256, 16
    img = np.zeros((S, S, 3), np.float32)
    img[:] = (0.80, 0.79, 0.76)
    yy, xx = np.mgrid[0:S, 0:S]
    d = np.hypot((yy % step) - step / 2 + 0.5, (xx % step) - step / 2 + 0.5)
    hole = np.clip(3.6 - d, 0, 1)[..., None]
    return (img * (1 - hole) + np.array([0.08, 0.08, 0.08]) * hole).astype(np.float32)


def cooler_pixels():
    """main_floor's cooler door interior, lit: pale walls, LED strips at the sides, five wire shelves, a few cartons left."""
    Wd, Hd = 256, 512
    rng = np.random.default_rng(17)
    img = np.zeros((Hd, Wd, 3), np.float32)
    x = np.linspace(-1, 1, Wd)[None, :, None]
    img[:] = np.array([0.62, 0.68, 0.72]) * (0.75 + 0.25 * (1 - x ** 2))
    img[:, :10] = img[:, -10:] = (1.0, 1.0, 0.98)
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
        img[s + 6:s + 14] *= 0.55
    img[shelves[-1] + 14:] *= 0.6
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def freezer_pixels():
    """A freezer door's interior: blue-white and frosted, LED strips at the sides, four shelves of frozen boxes, frost creeping in at the edges."""
    Wd, Hd = 256, 512
    rng = np.random.default_rng(19)
    img = np.zeros((Hd, Wd, 3), np.float32)
    x = np.linspace(-1, 1, Wd)[None, :, None]
    img[:] = np.array([0.55, 0.66, 0.80]) * (0.7 + 0.3 * (1 - x ** 2))
    img[:, :10] = img[:, -10:] = (0.92, 0.97, 1.0)
    pal = [(0.85, 0.88, 0.95), (0.20, 0.30, 0.70), (0.75, 0.20, 0.25), (0.92, 0.78, 0.30), (0.30, 0.55, 0.75), (0.95, 0.95, 0.95)]
    shelves = [int(Hd * f) for f in (0.22, 0.45, 0.68, 0.91)]
    for s in shelves:
        c = 18
        while c < Wd - 40:
            w = int(rng.uniform(22, 40))
            if rng.random() < 0.55:
                h = int(rng.uniform(30, 62))
                col = np.array(pal[rng.integers(len(pal))]) * rng.uniform(0.7, 1.0)
                img[s - h:s, c:c + w] = col
                img[s - h:s - h + 3, c:c + w] = img[s - h:s - h + 3, c:c + w] * 0.6 + 0.4
            c += w + 4
        img[s:s + 5] = (0.80, 0.84, 0.88)
        img[s + 5:s + 12] *= 0.6
    frost = np.clip(1.0 - np.minimum.outer(np.minimum(np.arange(Hd), Hd - 1 - np.arange(Hd)), np.minimum(np.arange(Wd), Wd - 1 - np.arange(Wd))) / 40.0, 0, 1)
    frost = frost * (0.6 + 0.4 * vnoise(Hd, Wd, rng, 4, 6))
    img = img * (1 - 0.55 * frost[..., None]) + 0.55 * frost[..., None] * np.array([0.92, 0.96, 1.0])
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


AISLE_ROWS = [("1", "FROZEN"), ("2", "BREAKFAST"), ("3", "BAKING"), ("4", "PASTA & RICE"), ("5", "TINS & JARS"), ("6", "SNACKS"),
              ("7", "DRINKS"), ("8", "HOUSEHOLD"), ("9", "PET FOOD"), ("10", "WORLD FOODS"), ("11", "PAPER GOODS")]
WALL_ROWS = ["FROZEN FOODS", "DAIRY & CHILLED", "GROCERY", "HOUSEHOLD", "HOMEWARE & CAFE ^", "HOMEWARE", "CAFE", "LIGHTING", "CUSHIONS",
             "TABLEWARE", "KITCHEN", "SORRY - CLOSED"]
SIGN_ROW_PX = 144
SIGN_ROWS = len(AISLE_ROWS) + len(WALL_ROWS)


def signs_pixels():
    """The store's painted boards, main_floor's style (cream letters on its deep red): the aisle boards (a cream square with the aisle's number,
    the aisle's goods beside it), then one word a row for the wall boards and the cards. 768 wide, SIGN_ROW_PX a row (about 5:1, the boards' shape)."""
    W, R = 768, SIGN_ROW_PX
    img = np.zeros((R * SIGN_ROWS, W, 3), np.float32)
    img[:] = (0.42, 0.05, 0.05)
    cream, red = (0.92, 0.86, 0.70), (0.42, 0.05, 0.05)
    for i, (num, word) in enumerate(AISLE_ROWS):
        r0 = i * R
        img[r0 + 8:r0 + R - 8, 10:10 + R - 16] = cream
        draw_text(img, num, (r0 + 8, r0 + R - 8, 10, 10 + R - 16), red, 0.62, 0.8)
        draw_text(img, word, (r0, r0 + R, R + 10, W - 10), cream, 0.6, 0.95)
    for k, word in enumerate(WALL_ROWS):
        r0 = (len(AISLE_ROWS) + k) * R
        draw_text(img, word, (r0, r0 + R, 0, W), cream, 0.66, 0.92)
    for i in range(SIGN_ROWS):
        img[i * R:i * R + 5] = img[(i + 1) * R - 5:(i + 1) * R] = (0.30, 0.03, 0.03)
    rng = np.random.default_rng(21)
    return np.clip(blur(img, 1, 1) * (0.94 + 0.08 * blur(rng.random(img.shape[:2]).astype(np.float32), 3, 2))[..., None], 0, 1).astype(np.float32)


def sign_uv(row):
    """The atlas rectangle of a row (top to bottom)."""
    return (0.0, 1 - (row + 1) / SIGN_ROWS, 1.0, 1 - row / SIGN_ROWS)


def wall_row(word):
    return len(AISLE_ROWS) + WALL_ROWS.index(word)


def glow_pixels():
    """main_floor's lit signs: EXIT (top half, green)."""
    img = np.zeros((256, 512, 3), np.float32)
    img[:128] = (0.02, 0.45, 0.16)
    draw_text(img, "EXIT", (0, 128, 0, 512), (0.95, 1.0, 0.95), 0.62)
    img[128:] = (0.02, 0.45, 0.16)
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def tread_pixels():
    """An escalator step's tread, 1.0 m across (u) by 0.27 m along (v): aluminium cleats every 6 mm, yellow edges, scuffed (the hotel's escalators' way)."""
    Hh, W = 256, 1024
    rng = np.random.default_rng(301)
    X = (np.arange(W) + 0.5)[None, :] / W * 1.2
    Y = (np.arange(Hh) + 0.5)[:, None] / Hh * 0.27
    cleat = 0.5 + 0.5 * np.cos(2 * np.pi * X / 0.006)
    t = np.clip((cleat - 0.25) / 0.4, 0, 1)[..., None]
    img = np.array([0.16, 0.16, 0.17]) * (1 - t) + np.array([0.62, 0.62, 0.60]) * t
    yel = ((X < 0.04) | (X > 1.16) | (Y < 0.04)) * np.ones_like(Y)
    ycol = np.array([0.26, 0.21, 0.06]) * (1 - t) + np.array([0.80, 0.62, 0.12]) * t
    img = np.where(yel[..., None] > 0, ycol, img)
    img *= (0.82 + 0.3 * vnoise(Hh, W, rng, 5, 3))[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def riser_pixels():
    Hh, W = 128, 1024
    rng = np.random.default_rng(302)
    X = (np.arange(W) + 0.5)[None, :] / W * 1.2
    cleat = 0.5 + 0.5 * np.cos(2 * np.pi * X / 0.006)
    t = np.clip((cleat - 0.3) / 0.4, 0, 1)[..., None] * np.ones((Hh, 1, 1))
    img = np.array([0.10, 0.10, 0.11]) * (1 - t) + np.array([0.45, 0.45, 0.44]) * t
    img *= (0.85 + 0.25 * vnoise(Hh, W, rng, 4, 3))[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def palette_pixels():
    img = np.zeros((64, 64, 3), np.float32)
    for i, k in enumerate(PAL_KEYS):
        r, c = i // 8, i % 8
        img[r * 8:(r + 1) * 8, c * 8:(c + 1) * 8] = PAL[k]
    return img


def shutter_pixels():
    """A steel roller shutter, 1 m square: slats 75 mm high, a dark groove between them, light streaks, a little grime low down."""
    S = 256
    rng = np.random.default_rng(41)
    yy = (np.arange(S) + 0.5)[:, None] / S
    slat = (yy % 0.075) / 0.075
    shade = 0.62 + 0.22 * np.sin(np.pi * slat) - 0.35 * (slat > 0.9)
    img = np.ones((S, S, 3)) * np.array([0.66, 0.67, 0.68]) * shade[..., None]
    streak = blur(rng.random((S, S)), 1, 1)
    streak = rs(rng.random((4, 64)), S, S)
    img *= (0.9 + 0.14 * streak)[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def stock_pixels():
    """A stocked gondola's side as seen from the mezzanine (the view down only): 2 m wide by 1.9 m tall, a dark kick, three shelves with their
    price rails, rows of packets and tins in the page's colours and others between, pegboard above."""
    W, Hh = 512, 512
    rng = np.random.default_rng(53)
    img = np.ones((Hh, W, 3)) * np.array([0.80, 0.79, 0.76])
    def row(y):                                     # metres -> pixel row (0 at the top)
        return int((1.9 - y) / 1.9 * Hh)
    img[row(0.31):] = (0.10, 0.10, 0.11)
    pal = [(0.85, 0.29, 0.23), (0.85, 0.69, 0.44), (0.78, 0.78, 0.78), (0.29, 0.54, 0.85), (0.92, 0.82, 0.30), (0.30, 0.55, 0.30),
           (0.92, 0.92, 0.88), (0.55, 0.20, 0.45), (0.95, 0.55, 0.15)]
    for top in (0.35, 0.95, 1.55):
        b = row(top)
        img[b:b + 6] = (0.82, 0.82, 0.80)
        img[b + 6:b + 12] = (0.82, 0.76, 0.48)
        c = 2
        while c < W - 2:
            w = int(rng.uniform(14, 30))
            h = int(rng.uniform(0.18, 0.40) / 1.9 * Hh)
            col = np.array(pal[rng.integers(len(pal))]) * rng.uniform(0.75, 1.0)
            img[b - h:b, c:c + w] = col
            img[b - h:b - h + 3, c:c + w] *= 1.15
            c += w + int(rng.uniform(1, 4))
    img *= (0.92 + 0.12 * vnoise(Hh, W, rng, 4, 4))[..., None]
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


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
    g = {"pegboard": mk_image("Pegboard", pegboard_pixels()), "cooler": mk_image("Cooler_Inside", cooler_pixels()),
         "freezer": mk_image("Freezer_Inside", freezer_pixels()), "signs": mk_image("Grocery_Signs", signs_pixels()),
         "glow": mk_image("Glow_Signs", glow_pixels())}
    if SCENE == "aisles":
        g.update({"tread": mk_image("Esc_Tread", tread_pixels()), "riser": mk_image("Esc_Riser", riser_pixels())})
    else:
        g.update({"palette": mk_image("Homeware_Palette", palette_pixels()), "shutter": mk_image("Shutter", shutter_pixels()),
                  "stock": mk_image("Stocked_Shelf", stock_pixels())})
    return g


# ================================================================ the shared pieces
def shell_walls(R, model_boxes, prefix, lower="Wall_Lower", paint="Wall_Paint", high=None, high_y=3.6):
    """The walls named <prefix>Wall_*: a sage band below the rail, cream above (and `high` above high_y, the same look at a lower density)."""
    for b in model_boxes:
        n = b["name"]
        if not n.startswith(prefix + "Wall_"):
            continue
        mn, mx = shift(b, R.oy)
        y0, y1 = b["min"][1], b["max"][1]
        cuts = [y0] + [v for v in (BAND, high_y if high else None) if v is not None and y0 < v < y1] + [y1]
        for a, c in zip(cuts, cuts[1:]):
            mat = lower if c <= BAND + 1e-6 else (high if high and a >= high_y - 1e-6 else paint)
            tag = "Lower" if mat == lower else ("High" if mat == high else "Upper")
            part(f"{R.pre}Shell_{n}_{tag}", mat, lambda bm, a=a, c=c: cube(bm, (mn[0], a + R.oy, mn[2]), (mx[0], c + R.oy, mx[2])), cull="wall")


def trims(R, cuts):
    """main_floor's steel rail on the band's top edge and the steel kick plate, along every wall of R; cuts = {normal: [(a0, a1, y_top)]} spans
    where something stands against the wall up to y_top (coolers, shelving, the opening)."""
    def runs(normal, y):
        lo, hi = (R.z0, R.z1) if normal[1] == "x" else (R.x0, R.x1)
        cs = sorted((a, b) for a, b, top in cuts.get(normal, []) if top > y)
        out, a = [], lo
        for c0, c1 in cs:
            if c0 > a:
                out.append((a, c0))
            a = max(a, c1)
        if hi > a:
            out.append((a, hi))
        return [(p, q) for p, q in out if q - p > 0.01]

    def rail(bm):
        for n in ("+x", "-x", "+z", "-z"):
            for a0, a1 in runs(n, BAND):
                wall_box(bm, R, n, a0, a1, BAND - 0.03, BAND + 0.03, 0.0, 0.02)
    part(f"{R.pre}Trim_Rail", "Trim_Steel", rail)

    def kick(bm):
        for n in ("+x", "-x", "+z", "-z"):
            for a0, a1 in runs(n, 0.075):
                wall_box(bm, R, n, a0, a1, 0.0, 0.15, 0.0, 0.012)
    part(f"{R.pre}Trim_Kick", "Trim_Steel", kick)


TOPS = (0.35, 0.95, 1.55)       # the page's food heights: the boards' tops (main_floor's)


def gondola(R, b, tops=TOPS, top_shelf=False, name=None):
    """main_floor's gondola in its collider b (running along z): a dark base, boards both sides at `tops`, a pegboard spine with uprights every metre,
    a price rail on each board's front edge. Its ends are the Endcap_ boxes. top_shelf: a full-width board on top (homeware)."""
    nm = R.pre + (name or b["name"])
    (x0, _, z0), (x1, y1, z1) = shift(b, R.oy)
    yb = R.oy
    xc = (x0 + x1) / 2
    sp = 0.07
    part(f"{nm}_Base", "Shelf_Kick", lambda bm: cube(bm, (x0 + 0.02, yb, z0), (x1 - 0.02, yb + tops[0] - 0.04, z1)), cull="shelf")

    def boards(bm):
        for t in tops:
            cube(bm, (x0, yb + t - 0.04, z0), (xc - sp, yb + t, z1))
            cube(bm, (xc + sp, yb + t - 0.04, z0), (x1, yb + t, z1))
        if top_shelf:
            cube(bm, (x0, y1 - 0.04, z0), (x1, y1, z1))
        else:
            cube(bm, (xc - sp - 0.03, y1 - 0.04, z0), (xc + sp + 0.03, y1, z1))
        n = max(1, int(round(z1 - z0)))
        for i in range(n + 1):
            z = z0 + (z1 - z0) * i / n
            cube(bm, (xc - sp - 0.006, yb + tops[0] - 0.04, max(z0, z - 0.02)), (xc + sp + 0.006, y1 - 0.04, min(z1, z + 0.02)))
    part(f"{nm}_Boards", "Shelf_Paint", boards, cull="shelf")
    part(f"{nm}_Spine", "Shelf_Back", lambda bm: cube(bm, (xc - sp, yb + tops[0] - 0.04, z0), (xc + sp, y1 - 0.04, z1)), cull="shelf")

    def rails(bm):
        for t in tops:
            cube(bm, (x0, yb + t - 0.065, z0), (x0 + 0.015, yb + t + 0.012, z1))
            cube(bm, (x1 - 0.015, yb + t - 0.065, z0), (x1, yb + t + 0.012, z1))
    part(f"{nm}_Rails", "Price_Rail", rails, cull="shelf")


def endcap(R, b, name=None):
    """The red end panel in its collider (main_floor's red ends, as deep as the greybox's end caps): a red box, a white cap, a dark kick."""
    nm = R.pre + (name or b["name"])
    (x0, y0, z0), (x1, y1, z1) = shift(b, R.oy)
    part(f"{nm}_Panel", "EndCap_Red", lambda bm: cube(bm, (x0, y0 + 0.1, z0), (x1, y1 - 0.02, z1)), cull="shelf")
    part(f"{nm}_Cap", "Shelf_Paint", lambda bm: cube(bm, (x0, y1 - 0.02, z0), (x1, y1, z1)), cull="shelf")
    part(f"{nm}_Kick", "Shelf_Kick", lambda bm: cube(bm, (x0 + 0.01, y0, z0 + 0.01), (x1 - 0.01, y0 + 0.1, z1 - 0.01)), cull="shelf")


def wall_shelving(R, b, normal, name=None):
    """One-sided wall shelving in its collider b against R's wall `normal`: a pegboard back, boards at the food heights and one more at 1.95 m,
    price rails, white side panels and a top canopy."""
    nm = R.pre + (name or b["name"])
    (x0, y0, z0), (x1, y1, z1) = shift(b, R.oy)
    along_z = normal[1] == "x"
    a0, a1 = (z0, z1) if along_z else (x0, x1)
    depth = (x1 - x0) if along_z else (z1 - z0)
    yb = R.oy

    def W(bm, aa0, aa1, ya, yc, d0, d1):
        wall_box(bm, R, normal, aa0, aa1, ya - R.oy, yc - R.oy, d0, d1)
    tops = TOPS + (1.95,)
    part(f"{nm}_Base", "Shelf_Kick", lambda bm: W(bm, a0, a1, yb, yb + 0.31, 0.0, depth - 0.02), cull="shelf")
    part(f"{nm}_Back", "Shelf_Back", lambda bm: W(bm, a0, a1, yb + 0.31, y1 - 0.06, 0.0, 0.08), cull="shelf")

    def boards(bm):
        for t in tops:
            W(bm, a0 + 0.025, a1 - 0.025, yb + t - 0.04, yb + t, 0.08, depth)
        W(bm, a0, a1, y1 - 0.06, y1, 0.0, depth)                                  # the canopy
        W(bm, a0, a0 + 0.025, yb, y1 - 0.06, 0.0, depth)                          # the side panels
        W(bm, a1 - 0.025, a1, yb, y1 - 0.06, 0.0, depth)
        n = max(1, int(round((a1 - a0) / 1.25)))
        for i in range(1, n):
            a = a0 + (a1 - a0) * i / n
            W(bm, a - 0.02, a + 0.02, yb + 0.31, y1 - 0.06, 0.08, 0.12)
    part(f"{nm}_Boards", "Shelf_Paint", boards, cull="shelf")
    part(f"{nm}_Rails", "Price_Rail", lambda bm: [W(bm, a0 + 0.025, a1 - 0.025, yb + t - 0.065, yb + t + 0.012, depth - 0.015, depth) for t in tops], cull="shelf")


COOLER_W = 0.95
COOLERS = []            # (room, normal, a0, a1, y0, y1, material): for the lights


def cooler_bank(R, tag, normal, a0, ndoors, lit="Cooler_Lit", y=(0.18, 2.22), cull="prop"):
    """main_floor's glass-door coolers, flat on R's wall (within 5 cm, no collider): a black frame, the lit inside (a picture 0.5 cm off the wall),
    a handle on each door, a header. lit: Cooler_Lit (dairy) or Freezer_Lit (frozen)."""
    a1 = a0 + ndoors * COOLER_W
    y0, y1 = y
    nm = R.pre + tag

    def frame(bm):
        wall_box(bm, R, normal, a0, a1, y0, y0 + 0.1, 0.0, 0.035)
        wall_box(bm, R, normal, a0, a1, y1 - 0.1, y1 + 0.18, 0.0, 0.035)
        for k in range(ndoors + 1):
            a = a0 + k * COOLER_W
            wall_box(bm, R, normal, max(a0, a - 0.025), min(a1, a + 0.025), y0 + 0.1, y1 - 0.1, 0.0, 0.035)
    part(f"{nm}_Frame", "Cooler_Frame", frame, cull=cull)

    def handles(bm):
        for k in range(ndoors):
            a = a0 + (k + 1) * COOLER_W - 0.08
            wall_box(bm, R, normal, a - 0.012, a + 0.012, 0.95, 1.55, 0.038, 0.048)
            for yy in (0.97, 1.53):
                wall_box(bm, R, normal, a - 0.008, a + 0.008, yy - 0.01, yy + 0.01, 0.02, 0.038)
    part(f"{nm}_Handles", "Rod_Steel", handles, cull=cull)
    panel(f"{nm}_Inside", lit, on_wall(R, normal, (a0 + a1) / 2, (y0 + y1) / 2, 0.005), normal, a1 - a0, y1 - y0 - 0.2, uv=(0, 0, ndoors, 1))
    part(f"{nm}_Glass", "Window_Glass", lambda bm: quad(bm, on_wall(R, normal, a0, y0 + 0.1, 0.025), on_wall(R, normal, a1, y0 + 0.1, 0.025),
                                                        on_wall(R, normal, a1, y1 - 0.1, 0.025), on_wall(R, normal, a0, y1 - 0.1, 0.025)), tile=1.0, cull="keep")
    COOLERS.append((R, normal, a0, a1, y0, y1, lit))
    return a1


STRIPS = []             # (x, y (diffuser), z0, z1): for the lights


def strips(R, tag, xs, z0, z1, y, ceil_y, rod_step=4.5):
    """main_floor's strip lights over the aisles: a housing, the diffuser underneath (Lamp_Emit), hung on rods from ceil_y (none if ceil_y is None)."""
    yy, cy = y + R.oy, (ceil_y + R.oy if ceil_y is not None else None)
    part(f"{R.pre}{tag}_Housings", "Light_Housing", lambda bm: [cube(bm, (x - 0.09, yy, z0), (x + 0.09, yy + 0.09, z1)) for x in xs])
    part(f"{R.pre}{tag}_Diffusers", "Lamp_Emit", lambda bm: [quad(bm, (x - 0.07, yy - 0.001, z0 + 0.05), (x + 0.07, yy - 0.001, z0 + 0.05),
                                                                 (x + 0.07, yy - 0.001, z1 - 0.05), (x - 0.07, yy - 0.001, z1 - 0.05)) for x in xs], cull="keep")
    if cy is not None and cy - yy > 0.12:
        def rods(bm):
            for x in xs:
                n = max(1, int(round((z1 - z0) / rod_step)))
                for i in range(n + 1):
                    z = z0 + 0.3 + (z1 - z0 - 0.6) * i / n
                    cyl(bm, (x, yy + 0.09, z), (x, cy, z), 0.006, seg=6, cap=False)
        part(f"{R.pre}{tag}_Rods", "Rod_Steel", rods, cull="keep")
    for x in xs:
        STRIPS.append((x, yy, z0, z1))


EMERG = []              # (game point of a head, aim): for the night's lights


def emergency(R, tag, spots, y):
    """Twin-head emergency fittings on R's walls (the mall entrance's): a white body, two heads whose lenses are Emergency_Emit, aimed down and out.
    spots = [(normal, a)]."""
    yb = y
    heads = []

    def bodies(bm):
        for n, a in spots:
            wall_box(bm, R, n, a - 0.22, a + 0.22, yb - 0.06, yb + 0.06, 0.0, 0.09)
            for k in (-1, 1):
                cyl(bm, on_wall(R, n, a + k * 0.16, yb + 0.06, 0.06), on_wall(R, n, a + k * 0.16, yb + 0.12, 0.06), 0.012, 0.012, 6)
    part(f"{R.pre}{tag}_Bodies", "Plastic_White", bodies)
    for n, a in spots:
        for k in (-1, 1):
            p = Vector(on_wall(R, n, a + k * 0.16, yb + 0.15, 0.07))
            aim = Vector(on_wall(R, n, a + k * 2.5, 0.0, 4.5))
            heads.append((tuple(p), tuple((aim - p).normalized())))
    part(f"{R.pre}{tag}_Heads", "Plastic_White", lambda bm: [cyl(bm, tuple(Vector(p) - Vector(d) * 0.06), tuple(Vector(p) + Vector(d) * 0.03), 0.045, 0.055, 12)
                                                           for p, d in heads], smooth=True)
    part(f"{R.pre}{tag}_Lenses", "Emergency_Emit", lambda bm: [cyl(bm, tuple(Vector(p) + Vector(d) * 0.03), tuple(Vector(p) + Vector(d) * 0.036), 0.046, 0.046, 12)
                                                             for p, d in heads], cull="keep")
    EMERG.extend(heads)


EXITS = []              # (game centre of the lit face, facing normal): the green glow


def exit_sign(R, tag, normal, a, y, d=0.0, hang=None):
    """main_floor's EXIT sign: a dark box, its face lit (Sign_Glow, the atlas's top half). On R's wall, or hung `d` m out from it on rods up to `hang`."""
    def housing(bm):
        wall_box(bm, R, normal, a - 0.24, a + 0.24, y - 0.1, y + 0.1, d, d + 0.07)
        if hang is not None:
            for k in (-0.18, 0.18):
                cyl(bm, on_wall(R, normal, a + k, y + 0.1, d + 0.035), on_wall(R, normal, a + k, hang, d + 0.035), 0.005, seg=6, cap=False)
    part(f"{R.pre}{tag}_Housing", "Plastic_Black", housing)
    c = on_wall(R, normal, a, y, d + 0.0705)
    panel(f"{R.pre}{tag}_Face", "Sign_Glow", c, normal, 0.44, 0.16, uv=(0, 0.5, 1, 1))
    if hang is not None:
        back = on_wall(R, normal, a, y, d - 0.0005)
        opp = {"+x": "-x", "-x": "+x", "+z": "-z", "-z": "+z"}[normal]
        panel(f"{R.pre}{tag}_Back", "Sign_Glow", back, opp, 0.44, 0.16, uv=(0, 0.5, 1, 1))
    EXITS.append((c, normal))


def wall_sign(R, tag, normal, a, y, w, h, row):
    """A painted board flat on R's wall (main_floor's department boards): the red board and its face from the atlas row."""
    part(f"{R.pre}{tag}_Board", "EndCap_Red", lambda bm: wall_box(bm, R, normal, a - w / 2 - 0.02, a + w / 2 + 0.02, y - h / 2 - 0.02, y + h / 2 + 0.02, 0.0, 0.025))
    panel(f"{R.pre}{tag}_Face", "Sign_Dept", on_wall(R, normal, a, y, 0.0255), normal, w, h, uv=sign_uv(row))


def hanging_boards(R, tag, items, top_y):
    """Boards hung on two rods from top_y (the ceiling or the soffit), both faces painted: items = [(x, z, y_centre, w, h, row, normal)];
    normal "+z"/"-z" for a board across an aisle running north to south."""
    yt = top_y + R.oy
    faces = []

    def boards(bm):
        for x, z, y, w, h, row, n in items:
            yy = y + R.oy
            if n[1] == "z":
                cube(bm, (x - w / 2 - 0.02, yy - h / 2 - 0.02, z - 0.02), (x + w / 2 + 0.02, yy + h / 2 + 0.02, z + 0.02))
            else:
                cube(bm, (x - 0.02, yy - h / 2 - 0.02, z - w / 2 - 0.02), (x + 0.02, yy + h / 2 + 0.02, z + w / 2 + 0.02))
    part(f"{R.pre}{tag}_Boards", "EndCap_Red", boards)
    for x, z, y, w, h, row, n in items:
        yy = y + R.oy
        opp = {"+x": "-x", "-x": "+x", "+z": "-z", "-z": "+z"}[n]
        for nn in (n, opp):
            off = Vector(NORMAL[nn]) * 0.0205
            faces.append(((x + off.x, yy, z + off.z), nn, w, h, sign_uv(row)))
    panels(f"{R.pre}{tag}_Faces", "Sign_Dept", faces)

    def rods(bm):
        for x, z, y, w, h, row, n in items:
            yy = y + R.oy + h / 2 + 0.02
            for k in (-w * 0.38, w * 0.38):
                px, pz = (x + k, z) if n[1] == "z" else (x, z + k)
                cyl(bm, (px, yy, pz), (px, yt, pz), 0.005, seg=6, cap=False)
    part(f"{R.pre}{tag}_Rods", "Rod_Steel", rods, cull="keep")


def glass_balustrade(R, b, name=None, post_step=1.5):
    """A glass balustrade in its collider b (a rail box, thin across x or z): steel posts through its thickness, a steel handrail on top, a glass
    infill 0.1 m thick (so the collider is covered within 5 cm)."""
    nm = R.pre + (name or b["name"])
    (x0, y0, z0), (x1, y1, z1) = shift(b, R.oy)
    along_x = (x1 - x0) >= (z1 - z0)
    lo, hi = (x0, x1) if along_x else (z0, z1)
    c0, c1 = (z0, z1) if along_x else (x0, x1)
    cm, th = (c0 + c1) / 2, (c1 - c0)

    def B3(a0, a1, ya, yb, d0, d1):
        return ((a0, ya, d0), (a1, yb, d1)) if along_x else ((d0, ya, a0), (d1, yb, a1))

    def posts(bm):
        n = max(1, int(math.ceil((hi - lo) / post_step)))
        for i in range(n + 1):
            a = lo + (hi - lo) * i / n
            p, q = B3(max(lo, a - 0.025), min(hi, a + 0.025), y0, y1 - 0.05, c0 + 0.02, c1 - 0.02)
            cube(bm, p, q)
    part(f"{nm}_Posts", "Rail_Steel", posts)
    p, q = B3(lo, hi, y1 - 0.05, y1, c0, c1)
    part(f"{nm}_Handrail", "Rail_Steel", lambda bm: cube(bm, p, q))
    p2, q2 = B3(lo, hi, y0 + 0.04, y1 - 0.05, cm, cm)                       # one pane (the posts and the rail cover the collider)
    part(f"{nm}_Glass", "Window_Glass", lambda bm: quad(bm, p2, (q2[0], p2[1], q2[2]), q2, (p2[0], q2[1], p2[2])) if along_x else
         quad(bm, p2, (p2[0], p2[1], q2[2]), q2, (q2[0], q2[1], p2[2])), cull="keep")
    p3, q3 = B3(lo, hi, y0, y0 + 0.04, c0 + 0.01, c1 - 0.01)
    part(f"{nm}_Shoe", "Frame_Alu", lambda bm: cube(bm, p3, q3))


def glazing(R, b, name=None, step=1.5):
    """A glazed screen in its collider b (thin across x): aluminium mullions every `step`, a head and a sill, glass 0.1 m thick."""
    nm = R.pre + (name or b["name"])
    (x0, y0, z0), (x1, y1, z1) = shift(b, R.oy)

    def frames(bm):
        n = max(1, int(math.ceil((z1 - z0) / step)))
        for i in range(n + 1):
            z = z0 + (z1 - z0) * i / n
            cube(bm, (x0, y0, max(z0, z - 0.025)), (x1, y1, min(z1, z + 0.025)))
        cube(bm, (x0, y1 - 0.06, z0), (x1, y1, z1))
        cube(bm, (x0, y0, z0), (x1, y0 + 0.05, z1))
    part(f"{nm}_Frame", "Frame_Alu", frames)
    xm = (x0 + x1) / 2
    part(f"{nm}_Glass", "Window_Glass", lambda bm: quad(bm, (xm, y0 + 0.05, z0), (xm, y0 + 0.05, z1), (xm, y1 - 0.06, z1), (xm, y1 - 0.06, z0)), cull="keep")


def door_frames(R, y0):
    """Aluminium linings round the two glass doors' openings in the mezzanine's front (x -4.2..-4.0)."""
    yb = y0 + R.oy
    for k, zc in enumerate((G.OPEN_STAIR, G.OPEN_ESC)):
        for j, z in enumerate((zc - 0.5, zc + 0.5)):
            part(f"{R.pre}Front_Door_{k}_Jamb_{j}", "Frame_Alu", lambda bm, z=z: cube(bm, (-4.2, yb, z - 0.03), (-4.0, yb + G.DOOR_H, z + 0.03)))
        part(f"{R.pre}Front_Door_{k}_Head", "Frame_Alu", lambda bm, zc=zc: cube(bm, (-4.2, yb + G.DOOR_H - 0.02, zc - 0.5), (-4.0, yb + G.DOOR_H + 0.06, zc + 0.5)))
        part(f"{R.pre}Front_Door_{k}_Sill", "Frame_Alu", lambda bm, zc=zc: cube(bm, (-4.2, yb, zc - 0.5), (-4.0, yb + 0.008, zc + 0.5)))


def leaf_mesh(w, h):
    """A glass door leaf in its own frame (local x from the hinge along the leaf, y across, z up): aluminium stiles and rails, a glass pane, a steel
    push bar both sides. Two materials: Frame_Alu (baked) and Window_Glass."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    t = 0.025
    pieces = []

    def bx(xa, xb, ya, yb, za, zb, mi):
        old = set(bm.faces)
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(((xa + xb) / 2, (ya + yb) / 2, (za + zb) / 2)) @ Matrix.Diagonal((xb - xa, yb - ya, zb - za, 1)))
        for f in bm.faces:
            if f not in old:
                f.material_index = mi
                pieces.append(f)
    s, top, bot = 0.07, 0.10, 0.20
    bx(0, s, -t, t, 0, h, 0)
    bx(w - s, w, -t, t, 0, h, 0)
    bx(s, w - s, -t, t, h - top, h, 0)
    bx(s, w - s, -t, t, 0, bot, 0)
    for sg in (-1, 1):
        bx(0.15, w - 0.15, sg * (t + 0.035), sg * (t + 0.06), 1.0, 1.035, 0)
        for xx in (0.17, w - 0.17):
            bx(xx - 0.012, xx + 0.012, sg * t, sg * (t + 0.035), 1.005, 1.03, 0)
    bx(s, w - s, -0.006, 0.006, bot, h - top, 1)
    bm.normal_update()
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            u, v = ((p.y, p.z) if ax == 0 else (p.x, p.z) if ax == 1 else (p.x, p.y))
            lp[uvl].uv = (u, v)
    return bm


def build_door_leaves():
    """The two glass leaves, each its own object (the Doors collection), origin at the hinge, with the greybox door's properties, so export_scene.py
    writes the same `doors` and the page can swing them by name."""
    for d in GB.doors:
        p = d["props"]
        bm = leaf_mesh(p["width"], p["height"])
        me = bpy.data.meshes.new(d["name"])
        bm.to_mesh(me)
        bm.free()
        me.materials.append(MATS["Frame_Alu"])
        me.materials.append(MATS["Window_Glass"])
        ob = bpy.data.objects.new(d["name"], me)
        ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
        for k, v in p.items():
            ob[k] = v
        DOORS_C.objects.link(ob)


def cam_bracket(R, tag, spot, normal):
    """The bracket a camera head (the page's) hangs from: a plate on R's wall `normal`, an arm out over the spot, a short drop to the head's top."""
    x, _, z = spot["pos"]
    mh = spot["props"]["mount_height"]
    ax = "x" if normal[1] == "x" else "z"
    wall = R.face(normal)

    def build(bm):
        if ax == "x":
            sg = 1 if normal[0] == "+" else -1
            cube(bm, (wall, mh + 0.2, z - 0.08), (wall + sg * 0.015, mh + 0.44, z + 0.08))
            cube(bm, (min(wall, x), mh + 0.29, z - 0.025), (max(wall, x), mh + 0.35, z + 0.025))
        else:
            sg = 1 if normal[0] == "+" else -1
            cube(bm, (x - 0.08, mh + 0.2, wall), (x + 0.08, mh + 0.44, wall + sg * 0.015))
            cube(bm, (x - 0.025, mh + 0.29, min(wall, z)), (x + 0.025, mh + 0.35, max(wall, z)))
        cyl(bm, (x, mh + 0.105, z), (x, mh + 0.29, z), 0.02, seg=10)
        cyl(bm, (x, mh + 0.10, z), (x, mh + 0.12, z), 0.045, seg=12)
    part(f"{R.pre}{tag}", "Metal_Dark", build)


def step_line(fl, s):
    """A flight's nosing line (game y above its floor) at distance s along its travel (s = 0 at the first step's front)."""
    return fl["rise"] + fl["rise"] / fl["tread"] * min(max(s, 0.0), fl["tread"] * (fl["n"] - 1))


def flight_info(model, name):
    f = next(f for f in model.flights if f["name"] == name)
    steps = sorted([b for b in model.boxes if b["name"].startswith(f"Step_{name}_")], key=lambda b: b["name"])
    s0 = steps[0]["max"][2]                         # the first step's front (the flights rise north: -z)
    return {"n": f["n"], "rise": f["rise"], "tread": f["tread"], "z0": s0, "x0": steps[0]["min"][0], "x1": steps[0]["max"][0], "steps": steps}


def band(bm, fl, R, x0, x1, lo, hi, s0, s1):
    """A solid band across x [x0, x1] along a flight from s0 to s1, between y = lo(s) and hi(s) (cut at the line's knees)."""
    knots = sorted({s0, s1, *[k for k in (0.0, fl["tread"] * (fl["n"] - 1)) if s0 < k < s1]})
    for a, b in zip(knots, knots[1:]):
        za, zb = fl["z0"] - a, fl["z0"] - b
        ring_a = [(x0, lo(a) + R.oy, za), (x0, hi(a) + R.oy, za), (x0, hi(b) + R.oy, zb), (x0, lo(b) + R.oy, zb)]
        ring_b = [(x1, lo(a) + R.oy, za), (x1, hi(a) + R.oy, za), (x1, hi(b) + R.oy, zb), (x1, lo(b) + R.oy, zb)]
        prism(bm, ring_a, ring_b)


def build_stairs(R, model):
    """The stairs up the mezzanine's front: per step a rubber tread with a steel nosing and a dark body (each under 0.2 m, since the steps'
    colliders hang in the air); steel stringers, a sloped soffit and a steel handrail on posts, all passable art (decor_)."""
    fl = flight_info(model, "stairs_up")
    pre = R.pre
    for b in fl["steps"]:
        (x0, y0, z0), (x1, y1, z1) = shift(b, R.oy)
        part(f"{pre}{b['name']}_Tread", "Stair_Tread", lambda bm: cube(bm, (x0, y1 - 0.07, z0), (x1, y1, z1)))
        part(f"{pre}{b['name']}_Nosing", "Trim_Steel", lambda bm: cube(bm, (x0, y1 - 0.05, z1 - 0.04), (x1, y1 + 0.003, z1 + 0.004)))
        part(f"{pre}{b['name']}_Body", "Metal_Dark", lambda bm: cube(bm, (x0 + 0.01, y0, z0), (x1 - 0.01, y1 - 0.07, z1 - 0.01)))
    S_END = fl["tread"] * fl["n"]
    L = lambda s: step_line(fl, s)
    dp = "decor_" if not pre else pre
    xs = (fl["x0"], fl["x1"])
    part(f"{dp}Stairs_Stringers", "Esc_Clad" if "Esc_Clad" in MATS else "Trim_Steel", lambda bm: [
        band(bm, fl, R, xa, xb, lambda s: max(0.0, L(s) - 0.42), lambda s: L(s) + 0.06, -0.02, S_END) for xa, xb in ((xs[0] - 0.05, xs[0]), (xs[1], xs[1] + 0.05))])
    part(f"{dp}Stairs_Soffit", "Soffit_Paint" if "Soffit_Paint" in MATS else "Trim_Steel",
         lambda bm: band(bm, fl, R, xs[0], xs[1], lambda s: max(0.0, L(s) - 0.42), lambda s: max(0.0, L(s) - 0.40), 0.6, S_END))

    def rail(bm):
        x = xs[0] - 0.025
        n = 7
        for i in range(n + 1):
            s = 0.15 + (S_END - 0.3) * i / n
            z = fl["z0"] - s
            cyl(bm, (x, L(s) + R.oy, z), (x, L(s) + 0.9 + R.oy, z), 0.02, seg=8)
        cyl(bm, (x, L(0.15) + 0.92 + R.oy, fl["z0"] - 0.15), (x, L(S_END - 0.15) + 0.92 + R.oy, fl["z0"] - S_END + 0.15), 0.025, seg=10)
    part(f"{dp}Stairs_Handrail", "Rod_Steel", rail, smooth=True)


def build_escalator(R, model):
    """The escalator beside the stairs, stopped: per step a grooved tread with yellow edges and a cleated riser (each under 0.2 m); comb and floor
    plates at both ends; balustrades either side (a steel skirt, a glass panel, a black handrail, the clad truss below), passable art (decor_)."""
    fl = flight_info(model, "escalator_up")
    pre = R.pre
    for b in fl["steps"]:
        (x0, y0, z0), (x1, y1, z1) = shift(b, R.oy)

        def tread(bm, x0=x0, x1=x1, y1=y1, z0=z0, z1=z1):
            cube(bm, (x0, y1 - 0.06, z0), (x1, y1, z1))
        ob = part(f"{pre}{b['name']}_Tread", "Esc_Tread", tread)
        if not pre:                                  # the tread picture once over the step's top (u across, v along)
            uvl = ob.data.uv_layers["UVMap"].data
            for poly in ob.data.polygons:
                for li in poly.loop_indices:
                    co = ob.data.vertices[ob.data.loops[li].vertex_index].co
                    gx, gz = co.x, -co.y
                    uvl[li].uv = ((gx - x0) / (x1 - x0), (z1 - gz) / (z1 - z0)) if poly.normal.z > 0.9 else (0.02, 0.98)
            part(f"{pre}{b['name']}_Riser", "Esc_Riser", lambda bm: cube(bm, (x0 + 0.005, y0, z1 - 0.012), (x1 - 0.005, y1 - 0.06, z1)), tile=1.2)
            part(f"{pre}{b['name']}_Body", "Metal_Dark", lambda bm: cube(bm, (x0 + 0.01, y0, z0), (x1 - 0.01, y1 - 0.06, z1 - 0.012)))
    S_END = fl["tread"] * fl["n"]
    L = lambda s: step_line(fl, s)
    N0, N1 = -0.9, S_END + 0.6
    dp = "decor_" if not pre else pre
    x0, x1 = fl["x0"], fl["x1"]
    y_top = fl["rise"] * fl["n"]
    for side, inner, sg in (("W", x0, -1), ("E", x1, 1)):
        xs = lambda a, b, inner=inner, sg=sg: tuple(sorted((inner + sg * a, inner + sg * b)))
        top = lambda s: L(s) + 0.95
        floor_lo = lambda s: 0.0 if s < 0.5 else (y_top if s > S_END - 0.01 else max(0.0, L(s) - 1.1))
        part(f"{dp}Esc_{side}_Skirt", "Esc_Clad", lambda bm: band(bm, fl, R, *xs(0.0, 0.02), lambda s: max(0.0, L(s) - 0.3) if s >= 0 else 0.0, lambda s: L(s) + 0.12, N0, N1))
        part(f"{dp}Esc_{side}_Glass", "Window_Glass", lambda bm: band(bm, fl, R, *xs(0.06, 0.08), lambda s: L(s) + 0.12, lambda s: top(s) - 0.05, N0 + 0.1, N1 - 0.1), cull="keep")
        part(f"{dp}Esc_{side}_Handrail", "Handrail_Black", lambda bm: band(bm, fl, R, *xs(0.03, 0.11), lambda s: top(s) - 0.05, top, N0, N1))
        part(f"{dp}Esc_{side}_Deck", "Esc_Clad", lambda bm: band(bm, fl, R, *xs(0.02, 0.14), lambda s: L(s) + 0.02, lambda s: L(s) + 0.12, N0, N1))
        part(f"{dp}Esc_{side}_Clad", "Esc_Clad", lambda bm: band(bm, fl, R, *xs(0.14, 0.2), floor_lo, lambda s: L(s) + 0.12, N0, N1))
        part(f"{dp}Esc_{side}_Newels", "Handrail_Black", lambda bm: (band(bm, fl, R, *xs(0.02, 0.14), lambda s: L(s) + 0.12, top, N0 - 0.06, N0),
                                                                    band(bm, fl, R, *xs(0.02, 0.14), lambda s: L(s) + 0.12, top, N1, N1 + 0.06)))
    part(f"{dp}Esc_Truss", "Esc_Clad", lambda bm: band(bm, fl, R, x0, x1, lambda s: max(0.0, L(s) - 1.1), lambda s: max(0.0, L(s) - 1.08), 1.0, S_END))
    if not pre:
        z0 = fl["z0"]
        part("Esc_Plates", "Esc_Clad", lambda bm: (cube(bm, (x0, 0.0, z0), (x1, 0.008, z0 - N0)),))
        part("Esc_Comb_Bottom", "Comb_Yellow", lambda bm: cube(bm, (x0, 0.0, z0 - 0.02), (x1, 0.02, z0 + 0.05)))
        part("Esc_Comb_Top", "Comb_Yellow", lambda bm: cube(bm, (x0, y_top, z0 - S_END - 0.05), (x1, y_top + 0.02, z0 - S_END)))


# ================================================================ aisles
def a_shell():
    R = RA
    for b in GA.boxes:
        n = b["name"]
        if n == "Aisles_Floor":
            part("Shell_Aisles_Floor", "Floor_Tile", lambda bm, b=b: cube(bm, b["min"], b["max"]), cull="up")
        elif n == "Aisles_Ceiling":
            part("Shell_Aisles_Ceiling", "Ceiling_Tile", lambda bm, b=b: cube(bm, b["min"], b["max"]), cull="down")
    shell_walls(R, GA.boxes, "Aisles_", high="Wall_High")
    ox0, ox1, oh = G.MF["opening"]

    part("Opening_Lining_W", "Trim_Steel", lambda bm: (cube(bm, (ox0, 0.0, G.AZ1), (ox0 + 0.012, oh, G.AZ1 + T)),
                                                      cube(bm, (ox0 - 0.06, 0.0, G.AZ1 - 0.012), (ox0, oh + 0.06, G.AZ1))), cull="keep")
    part("Opening_Lining_E", "Trim_Steel", lambda bm: (cube(bm, (ox1 - 0.012, 0.0, G.AZ1), (ox1, oh, G.AZ1 + T)),
                                                      cube(bm, (ox1, 0.0, G.AZ1 - 0.012), (ox1 + 0.06, oh + 0.06, G.AZ1))), cull="keep")
    part("Opening_Lining_Head", "Trim_Steel", lambda bm: (cube(bm, (ox0, oh - 0.012, G.AZ1), (ox1, oh, G.AZ1 + T)),
                                                         cube(bm, (ox0, oh, G.AZ1 - 0.012), (ox1, oh + 0.06, G.AZ1))), cull="keep")


S_COOLERS = [(-21.6, 9), (-12.45, 9), (8.2, 9), (17.3, 6)]           # the south wall's dairy coolers: (west end x, doors); not behind the corral
W_FREEZERS = [(-43.2, 9), (-33.4, 9), (-23.6, 9)]                     # the west wall's freezers, under the mezzanine: (north end z, doors)


def a_coolers():
    for i, (a0, n) in enumerate(S_COOLERS):
        cooler_bank(RA, f"Cooler_S{i}", "-z", a0, n)
    for i, (a0, n) in enumerate(W_FREEZERS):
        cooler_bank(RA, f"Freezer_W{i}", "+x", a0, n, lit="Freezer_Lit")


def a_trim_cuts(R):
    cuts = {"-z": [(a0, a0 + n * COOLER_W, 2.4) for a0, n in S_COOLERS] + [(G.MF["opening"][0], G.MF["opening"][1], G.MF["opening"][2])],
            "+x": [(a0, a0 + n * COOLER_W, 2.4) for a0, n in W_FREEZERS]}
    ws = {b["name"]: b for b in GA.boxes}
    e, nn = ws["Wall_Shelving_E"], ws["Wall_Shelving_N"]
    cuts["-x"] = [(e["min"][2], e["max"][2], 2.2)]
    cuts["+z"] = [(nn["min"][0], nn["max"][0], 2.2)]
    return cuts


def a_fixtures(R, model):
    """The gondolas, their end caps and the wall shelving, from the model's boxes (R: the aisles, or the view down)."""
    for b in model.boxes:
        n = b["name"]
        if n.startswith("Gondola_"):
            gondola(R, b)
        elif n.startswith("Endcap_"):
            endcap(R, b)
        elif n == "Wall_Shelving_E":
            wall_shelving(R, b, "-x")
        elif n == "Wall_Shelving_N":
            wall_shelving(R, b, "+z")


def a_corral(R, model):
    b = next(b for b in model.boxes if b["name"] == "Cart_Corral")
    (x0, y0, z0), (x1, y1, z1) = shift(b, R.oy)
    r = 0.022
    posts = ((x0 + r, z0 + r), (x1 - r, z0 + r), (x0 + r, z1 - r), (x1 - r, z1 - r))

    def rails(bm):
        for x, z in posts:
            cyl(bm, (x, y0, z), (x, y1 - r, z), r, seg=10)
        for y in (y0 + 0.5, y1 - r):
            cyl(bm, (x0 + r, y, z1 - r), (x1 - r, y, z1 - r), r, seg=10)            # along the wall (its open side is north, toward the carts)
            cyl(bm, (x0 + r, y, z0 + r), (x0 + r, y, z1 - r), r, seg=10)
            cyl(bm, (x1 - r, y, z0 + r), (x1 - r, y, z1 - r), r, seg=10)
    part(f"{R.pre}Cart_Corral_Rails", "Rod_Steel", rails, smooth=True)


def a_clearing(R):
    """The red-cart clearing (IMG_3027 is a label only): a painted red border and ring on the floor, where the page parks its eight red carts."""
    c = G.CLEAR
    cx, cz = (c["x0"] + c["x1"]) / 2, (c["z0"] + c["z1"]) / 2
    y = R.oy + 0.002

    def paint(bm):
        h, w = 4.6, 0.12
        for (a0, a1, b0, b1) in ((-h, h, -h, -h + w), (-h, h, h - w, h), (-h, -h + w, -h + w, h - w), (h - w, h, -h + w, h - w)):
            quad(bm, (cx + a0, y, cz + b0), (cx + a1, y, cz + b0), (cx + a1, y, cz + b1), (cx + a0, y, cz + b1))
        n = 48
        for k in range(n):
            a, b = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
            for r0, r1 in ((2.15, 2.27),):
                p = [(cx + r * math.cos(t), y, cz + r * math.sin(t)) for r, t in ((r0, a), (r1, a), (r1, b), (r0, b))]
                quad(bm, *p)
    part(f"{'decor_' if not R.pre else R.pre}Clearing_Paint", "EndCap_Red", paint, cull="keep")


def a_signs(R):
    """The aisle number boards, hung over each aisle's both ends (both faces painted); and the wall boards."""
    ge, gw, gwid = G.G_EAST, G.G_WEST, G.GW
    under = [(G.AX0 + 0.1, gw[0] - gwid / 2)] + [(gw[i] + gwid / 2, gw[i + 1] - gwid / 2) for i in range(len(gw) - 1)]
    east = [(ge[i] + gwid / 2, ge[i + 1] - gwid / 2) for i in range(len(ge) - 1)] + [(ge[-1] + gwid / 2, G.AX1 - 0.6)]
    items_w, items_e = [], []
    for k, (a, b) in enumerate(under):
        x = (a + b) / 2
        for z, n in ((MEZ["z1"] - 0.8, "-z"), (MEZ["z0"] + 0.8, "+z")):
            items_w.append((x, z, 3.3, 1.9, 0.48, k, n))
    for k, (a, b) in enumerate(east):
        x = (a + b) / 2
        for z, n in ((G.GZ1 - 0.9, "-z"), (G.GZ0 + 0.9, "+z")):
            items_e.append((x, z, 3.3, 1.9, 0.48, 5 + k, n))
    if not R.pre:
        hanging_boards(R, "Aisle_Signs_Under", items_w, MEZ["y"] - G.SLAB)
    hanging_boards(R, "Aisle_Signs", items_e, G.AH)
    if not R.pre:
        wall_sign(R, "Sign_Frozen", "+x", (W_FREEZERS[0][0] + W_FREEZERS[-1][0] + W_FREEZERS[-1][1] * COOLER_W) / 2, 3.0, 3.6, 0.6, wall_row("FROZEN FOODS"))
    if not R.pre:
        wall_sign(R, "Sign_Dairy_W", "-z", -12.45 + 0.2, 3.0, 3.6, 0.6, wall_row("DAIRY & CHILLED"))
    wall_sign(R, "Sign_Dairy_E", "-z", 15.0, 3.0, 3.6, 0.6, wall_row("DAIRY & CHILLED"))
    wall_sign(R, "Sign_Grocery", "+z", 9.5, 3.1, 3.6, 0.6, wall_row("GROCERY"))
    wall_sign(R, "Sign_Household", "-x", -29.0, 3.1, 3.6, 0.6, wall_row("HOUSEHOLD"))


def a_strips(R):
    ge = G.G_EAST
    xs_e = [-0.0] + [(ge[i] + ge[i + 1]) / 2 for i in range(len(ge) - 1)] + [(ge[-1] + G.GW / 2 + G.AX1 - 0.6) / 2]
    xs_e[0] = (G.ESC_LANE[1] + 0.2 + ge[0] - G.GW / 2) / 2
    strips(R, "Strips", xs_e, G.AZ0 + 1.6, G.AZ1 - 1.2, 4.4, G.AH)
    if not R.pre:
        gw = G.G_WEST
        xs_w = [(G.AX0 + gw[0] - G.GW / 2) / 2] + [(gw[i] + gw[i + 1]) / 2 for i in range(len(gw) - 1)] + [(gw[-1] + G.GW / 2 - 4.4) / 2]
        strips(R, "Strips_Under", xs_w, MEZ["z0"] + 0.6, MEZ["z1"] - 0.6, 4.25, MEZ["y"] - G.SLAB, rod_step=3.0)


def a_mezzanine():
    """The mezzanine's underside and front, as seen from the aisles: the slab (a painted soffit, a tiled top, a steel fascia), steel beams over the
    column lines, the columns (sage band, cream, the steel rail), the glass balustrade and the glazed front with the two glass doors' frames, a
    drop ceiling and strips behind the glass (art only: the second floor is its own scene)."""
    sl = BOX["Mezzanine_Slab"]
    (x0, y0, z0), (x1, y1, z1) = sl["min"], sl["max"]
    part("Mezzanine_Slab", "Soffit_Paint", lambda bm: cube(bm, (x0, y0, z0), (x1, y1 - 0.03, z1)))
    part("Mezzanine_Slab_Top", "Floor_Tile", lambda bm: cube(bm, (x0, y1 - 0.03, z0), (x1, y1, z1)), cull="up")
    part("Mezzanine_Fascia", "Trim_Steel", lambda bm: cube(bm, (x1, y0 - 0.05, z0), (x1 + 0.02, y1, z1)), cull="keep")

    def beams(bm):
        for xc in (-13.8, -4.2):
            cube(bm, (xc - 0.1, y0 - 0.35, z0), (xc + 0.1, y0, z1))
        for zc in (-18.0, -29.2, -40.4):
            cube(bm, (x0, y0 - 0.3, zc - 0.08), (x1, y0, zc + 0.08))
    part("Mezzanine_Beams", "Shelf_Paint", beams)
    for b in GA.boxes:
        if b["name"].startswith("Mezz_Column"):
            (cx0, _, cz0), (cx1, cy1, cz1) = b["min"], b["max"]
            part(f"{b['name']}_Lower", "Wall_Lower", lambda bm, b=b: cube(bm, (cx0, 0.0, cz0), (cx1, BAND, cz1)))
            part(f"{b['name']}_Upper", "Wall_Paint", lambda bm, b=b: cube(bm, (cx0, BAND, cz0), (cx1, cy1, cz1)))
            part(f"{b['name']}_Trim", "Trim_Steel", lambda bm, b=b: (cube(bm, (cx0 - 0.012, BAND - 0.03, cz0 - 0.012), (cx1 + 0.012, BAND + 0.03, cz1 + 0.012)),
                                                                    cube(bm, (cx0 - 0.012, 0.0, cz0 - 0.012), (cx1 + 0.012, 0.15, cz1 + 0.012))))
        elif b["name"].startswith("Mezz_Front_Rail"):
            glass_balustrade(RA, b)
        elif b["name"].startswith("Mezz_Front_Glass"):
            glazing(RA, b)
    door_frames(RA, MEZ["y"])
    # behind the glass: the second floor's ceiling and strips (art only)
    yc = MEZ["y"] + MEZ["h"]
    part("decor_Mezz_Ceiling", "Ceiling_Tile", lambda bm: cube(bm, (x0, yc, z0), (-4.2, yc + 0.05, z1)), cull="down")
    strips(Room(x0, -4.2, z0, z1, yc, pre="decor_mezz_"), "Strips", [-20.4, -15.6, -11.0, -6.4], z0 + 0.8, z1 - 0.8, yc - 0.12, None)
    wall_sign(Room(-4.0, G.AX1, G.AZ0, G.AZ1, G.AH), "Sign_Upstairs", "+x", -32.0, 5.55, 3.4, 0.5, wall_row("HOMEWARE & CAFE ^"))


def a_landing():
    """The landing at the top of the stairs and the escalator: a soffit under a tiled top, a steel edge, glass balustrades on its north and east."""
    b = BOX["Landing"]
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    part("Landing_Slab", "Soffit_Paint", lambda bm: cube(bm, (x0, y0, z0), (x1, y1 - 0.03, z1)))
    part("Landing_Top", "Floor_Tile", lambda bm: cube(bm, (x0, y1 - 0.03, z0), (x1, y1, z1)), cull="up")
    part("Landing_Edge", "Trim_Steel", lambda bm: (cube(bm, (x0, y0 - 0.03, z1), (x1, y1, z1 + 0.012)), cube(bm, (x1, y0 - 0.03, z0), (x1 + 0.012, y1, z1))), cull="keep")
    for n in ("Landing_Rail_N", "Landing_Rail_E"):
        glass_balustrade(RA, BOX[n])


def a_emergency():
    sp = [("+z", -16.0), ("+z", -1.5), ("+z", 3.5), ("+z", 16.5), ("-z", -20.0), ("-z", 21.5), ("-x", -42.0), ("-x", -20.0), ("-x", -12.5)]
    emergency(RA, "Emergency", sp, 3.0)
    emergency(RA, "Emergency_W", [("+x", -38.0), ("+x", -19.0)], 3.4)
    cols = Room(-4.0, 24.0, -49.2, -9.2, G.AH)                        # heads on the front columns' east faces, aimed into the aisles
    emergency(cols, "Emergency_Cols", [("+x", -20.0), ("+x", -36.0)], 3.2)
    exit_sign(RA, "Exit_Opening", "-z", 0.0, G.MF["opening"][2] + 0.4)


def a_brackets(R, model):
    face = {"camhead_1": "+z", "camhead_2": "-x", "camhead_3": "+x"}
    for e in model.empties:
        if e["name"].startswith("Spot_camhead_"):
            cam_bracket(R, f"Cam_Bracket_{e['name'][13:]}", e, face["camhead_" + e["name"][13:]])


def build_aisles():
    a_shell()
    trims(RA, a_trim_cuts(RA))
    a_coolers()
    a_fixtures(RA, GA)
    a_corral(RA, GA)
    a_clearing(RA)
    a_signs(RA)
    a_strips(RA)
    a_mezzanine()
    a_landing()
    build_stairs(RA, GA)
    build_escalator(RA, GA)
    a_emergency()
    a_brackets(RA, GA)


# ================================================================ second_floor
HOMEWARE = {1: "LIGHTING", 2: "CUSHIONS", 3: "TABLEWARE", 4: "KITCHEN"}


def s_shell():
    R = RS
    for b in GB.boxes:
        n = b["name"]
        if n in ("Mezzanine_Floor", "Front_Floor"):
            part(f"Shell_{n}", "Floor_Tile", lambda bm, b=b: cube(bm, b["min"], b["max"]), cull="up")
        elif n == "Mezzanine_Ceiling":
            part("Shell_Mezzanine_Ceiling", "Ceiling_Tile", lambda bm, b=b: cube(bm, b["min"], b["max"]), cull="down")
    shell_walls(R, GB.boxes, "Mezzanine_")
    trims(R, {"-x": [(R.z0, R.z1, 3.2)], "+x": [(-21.9, -21.9 + 2 * COOLER_W, 2.4)]})
    for b in GB.boxes:
        n = b["name"]
        if n.startswith("Front_Rail"):
            glass_balustrade(R, b)
        elif n.startswith("Front_Glass"):
            glazing(R, b)
        elif n.startswith("Landing_Rail"):
            glass_balustrade(R, b)
    door_frames(R, 0.0)
    b = BOX["Landing"]
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    part("Landing_Slab", "Soffit_Paint", lambda bm: cube(bm, (x0, y0, z0), (x1, y1 - 0.03, z1)))
    part("Landing_Top", "Floor_Tile", lambda bm: cube(bm, (x0, y1 - 0.03, z0), (x1, y1, z1)), cull="up")
    part("Landing_Edge", "Trim_Steel", lambda bm: (cube(bm, (x0, y0 - 0.03, z1), (x1, y1, z1 + 0.012)), cube(bm, (x1, y0 - 0.03, z0), (x1 + 0.012, y1, z1))), cull="keep")
    part("Front_Fascia", "Trim_Steel", lambda bm: cube(bm, (-4.0, -0.35, R.z0), (-3.98, 0.0, -24.0)), cull="keep")
    part("Front_Fascia_2", "Trim_Steel", lambda bm: cube(bm, (-4.0, -0.35, -21.2), (-3.98, 0.0, R.z1)), cull="keep")


def lamp(p, x, y, z, r_base, h, shade_r, base_key, shade_key):
    """A table lamp standing at (x, y, z): a base, a stem, a drum shade (unlit: the store is closed)."""
    p.add(base_key, cyl, (x, y, z), (x, y + h * 0.35, z), r_base, r_base * 0.7, 12)
    p.add("lamp_brass", cyl, (x, y + h * 0.35, z), (x, y + h * 0.7, z), 0.008, None, 6)
    p.add(shade_key, cyl, (x, y + h * 0.6, z), (x, y + h, z), shade_r, shade_r * 0.72, 16)


def plates(p, x, y, z, r, n, key):
    p.add(key, cyl, (x, y, z), (x, y + 0.012 * n, z), r, r, 16)
    p.add("plate_white", cyl, (x, y + 0.012 * n, z), (x, y + 0.012 * n + 0.002, z), r * 0.7, r * 0.7, 16)


def cushion(p, x, y, z, w, d, h, key):
    p.add(key, cube, (x - w / 2, y, z - d / 2), (x + w / 2, y + h, z + d / 2))
    p.add(key, cube, (x - w / 2 + 0.02, y + h, z - d / 2 + 0.02), (x + w / 2 - 0.02, y + h + 0.03, z + d / 2 - 0.02))


def s_homeware():
    """Four low homeware gondolas (lighting, cushions, tableware, kitchen) with their goods, the end caps with header cards, two display tables."""
    rng = np.random.default_rng(77)
    for b in GB.boxes:
        n = b["name"]
        if n.startswith("Homeware_Gondola_"):
            gondola(RS, b, tops=(0.35, 0.95), top_shelf=True)
        elif n.startswith("Homeware_Endcap_"):
            endcap(RS, b)
            k = int(n.split("_")[-1])
            (x0, _, z0), (x1, y1, z1) = b["min"], b["max"]
            part(f"{n}_Header_Post", "Rod_Steel", lambda bm: cyl(bm, ((x0 + x1) / 2, y1, (z0 + z1) / 2), ((x0 + x1) / 2, y1 + 0.18, (z0 + z1) / 2), 0.008, seg=6))
            part(f"{n}_Header_Board", "EndCap_Red", lambda bm: cube(bm, (x0 + 0.02, y1 + 0.18, z1 - 0.17), (x1 - 0.02, y1 + 0.42, z1 - 0.13)))
            panels(f"{n}_Header_Faces", "Sign_Dept", [(((x0 + x1) / 2, y1 + 0.30, z1 - 0.1295), "+z", 1.1, 0.2, sign_uv(wall_row(HOMEWARE[k]))),
                                                      (((x0 + x1) / 2, y1 + 0.30, z1 - 0.1705), "-z", 1.1, 0.2, sign_uv(wall_row(HOMEWARE[k])))])
    for b in GB.boxes:
        n = b["name"]
        if not n.startswith("Homeware_Gondola_"):
            continue
        k = int(n.split("_")[-1])
        (x0, _, z0), (x1, y1, z1) = b["min"], b["max"]
        xc = (x0 + x1) / 2
        p = Painter()
        levels = [0.35, 0.95, y1]
        for side in (-1, 1):
            xf = xc + side * 0.33                                   # the goods' row on a side's boards
            for lv in levels:
                z = z0 + 0.35
                while z < z1 - 0.3:
                    gap = rng.random() < 0.12                       # a few gaps: the stock is running down
                    if k == 1:
                        if not gap and lv > 0.4:
                            lamp(p, xf, lv, z, 0.07, 0.42 if lv < 1.0 else 0.5, 0.16, rng.choice(["lamp_ceramic", "lamp_black", "lamp_brass"]),
                                 rng.choice(["shade_linen", "shade_white", "shade_green"]))
                        elif not gap:
                            p.add("box_kraft", cube, (xf - 0.2, lv, z - 0.18), (xf + 0.2, lv + 0.32, z + 0.18))
                        z += 0.55
                    elif k == 2:
                        if not gap:
                            hh = 0.0
                            for _ in range(int(rng.integers(1, 4)) if lv < y1 else 1):
                                cushion(p, xf, lv + hh, z, 0.42, 0.42, 0.11, rng.choice(["cush_mustard", "cush_rose", "cush_navy", "cush_grey", "cush_green",
                                                                                       "cush_cream", "cush_rust", "cush_teal"]))
                                hh += 0.14
                        z += 0.5
                    elif k == 3:
                        if not gap:
                            plates(p, xf, lv, z, 0.13, int(rng.integers(4, 12)), rng.choice(["plate_white", "plate_blue", "plate_sage", "plate_terra"]))
                            if rng.random() < 0.5:
                                p.add("mug_cream", cyl, (xf - side * 0.15, lv, z + 0.18), (xf - side * 0.15, lv + 0.1, z + 0.18), 0.045, 0.045, 10)
                        z += 0.38
                    else:
                        if not gap:
                            kind = rng.integers(3)
                            if kind == 0:
                                p.add(rng.choice(["mug_yellow", "mug_teal", "mug_red", "mug_cream"]), cyl, (xf, lv, z), (xf, lv + 0.1, z), 0.045, 0.045, 10)
                                p.add(rng.choice(["mug_yellow", "mug_teal", "mug_red"]), cyl, (xf, lv, z + 0.13), (xf, lv + 0.1, z + 0.13), 0.045, 0.045, 10)
                            elif kind == 1:
                                p.add(rng.choice(["pan_black", "pan_copper"]), cyl, (xf, lv, z), (xf, lv + 0.07, z), 0.12, 0.13, 16)
                            else:
                                p.add(rng.choice(["vase_blue", "vase_amber", "glass_clear", "jar_cork"]), cyl, (xf, lv, z), (xf, lv + 0.24, z), 0.06, 0.04, 12)
                        z += 0.34
        p.done(f"{n}_Goods")
    # the display tables: a light wood top on a white base, cushions, a lamp, a stack of plates and a folded throw
    for b in GB.boxes:
        n = b["name"]
        if not n.startswith("Display_Table_"):
            continue
        (x0, _, z0), (x1, y1, z1) = b["min"], b["max"]
        xc, zc = (x0 + x1) / 2, (z0 + z1) / 2
        part(f"{n}_Top", "Wood_Light", lambda bm: cube(bm, (x0, y1 - 0.05, z0), (x1, y1, z1)))
        part(f"{n}_Base", "Shelf_Paint", lambda bm: cube(bm, (x0 + 0.04, 0.0, z0 + 0.04), (x1 - 0.04, y1 - 0.05, z1 - 0.04)))
        p = Painter()
        if n.endswith("_1"):
            lamp(p, xc - 0.45, y1, zc - 0.45, 0.09, 0.62, 0.22, "lamp_ceramic", "shade_linen")
            for i, key in enumerate(("cush_mustard", "cush_teal", "cush_rose")):
                cushion(p, xc + 0.3, y1 + 0.14 * i, zc + 0.2, 0.45, 0.45, 0.11, key)
            plates(p, xc - 0.4, y1, zc + 0.45, 0.14, 8, "plate_sage")
        else:
            lamp(p, xc + 0.45, y1, zc + 0.4, 0.08, 0.55, 0.2, "lamp_brass", "shade_green")
            for i, key in enumerate(("plate_blue", "plate_white")):
                plates(p, xc - 0.35 + 0.35 * i, y1, zc - 0.4, 0.13, 6, key)
            p.add("towel_sage", cube, (xc - 0.5, y1, zc + 0.1), (xc + 0.1, y1 + 0.08, zc + 0.55))
            p.add("towel_grey", cube, (xc - 0.48, y1 + 0.08, zc + 0.12), (xc + 0.08, y1 + 0.14, zc + 0.53))
        p.done(f"{n}_Goods")
    hanging_boards(RS, "Sign_Homeware", [(-15.6, -29.6, 2.55, 2.4, 0.5, wall_row("HOMEWARE"), "-z")], RS.h)


def chair_up(p, x, y, z, yaw):
    """A cafe chair turned upside down on a table: its seat on the top, the legs and the back pointing up."""
    c, s = math.cos(yaw), math.sin(yaw)

    def P(u, v, h):
        return (x + u * c - v * s, y + h, z + u * s + v * c)
    w = 0.40
    p.add("chair_seat", lambda bm: prism(bm, [P(-w / 2, -w / 2, 0.0), P(w / 2, -w / 2, 0.0), P(w / 2, w / 2, 0.0), P(-w / 2, w / 2, 0.0)],
                                           [P(-w / 2, -w / 2, 0.035), P(w / 2, -w / 2, 0.035), P(w / 2, w / 2, 0.035), P(-w / 2, w / 2, 0.035)]))
    for u, v in ((-0.17, -0.17), (0.17, -0.17), (-0.17, 0.17), (0.17, 0.17)):
        p.add("cart_black", cyl, P(u, v, 0.035), P(u * 1.1, v * 1.1, 0.47), 0.013, 0.011, 6)
    for u in (-0.17, 0.17):                                     # the stretchers between the legs, near their (upturned) feet
        p.add("cart_black", cyl, P(u * 1.08, -0.18, 0.38), P(u * 1.08, 0.18, 0.38), 0.008, None, 6)


def s_cafe():
    """The closed cafe in the south-west corner: terracotta walls, the counter with its roller shutter down (CAFE over it, a SORRY - CLOSED card),
    a drinks fridge still lit on the west wall, five tables with the chairs up on them, a glass screen along the barrier."""
    for n in ("Cafe_Wall_N", "Cafe_Wall_E"):
        b = BOX[n]
        part(n, "Cafe_Wall", lambda bm, b=b: cube(bm, b["min"], b["max"]))
        part(f"{n}_Kick", "Trim_Steel", lambda bm, b=b: cube(bm, (b["min"][0] - 0.012, 0.0, b["min"][2] - 0.012), (b["max"][0] + 0.012, 0.15, b["max"][2] + 0.012)))
    c = BOX["Cafe_Counter"]
    (x0, _, z0), (x1, y1, z1) = c["min"], c["max"]
    part("Cafe_Counter_Body", "Counter_Laminate", lambda bm: cube(bm, (x0, 0.08, z0), (x1, y1 - 0.04, z1)))
    part("Cafe_Counter_Kick", "Shelf_Kick", lambda bm: cube(bm, (x0 + 0.03, 0.0, z0 + 0.03), (x1 - 0.03, 0.08, z1 - 0.03)))
    part("Cafe_Counter_Top", "Counter_Top", lambda bm: cube(bm, (x0 - 0.02, y1 - 0.04, z0 - 0.02), (x1 + 0.02, y1, z1 + 0.02)))
    part("Cafe_Counter_Band", "Wood_Light", lambda bm: cube(bm, (x0, 0.3, z1), (x1, 0.9, z1 + 0.012)))
    s = BOX["Cafe_Shutter"]
    (sx0, sy0, sz0), (sx1, sy1, sz1) = s["min"], s["max"]
    ob = part("Cafe_Shutter", "Shutter_Steel", lambda bm: cube(bm, (sx0 + 0.04, sy0, sz0 + 0.03), (sx1 - 0.04, sy1, sz1 - 0.03)))
    uvl = ob.data.uv_layers["UVMap"].data
    for poly in ob.data.polygons:
        for li in poly.loop_indices:
            co = ob.data.vertices[ob.data.loops[li].vertex_index].co
            uvl[li].uv = (co.x, co.z) if abs(poly.normal.y) > 0.9 else (0.1, 0.5)
    part("Cafe_Shutter_Guides", "Metal_Dark", lambda bm: (cube(bm, (sx0, sy0, sz0), (sx0 + 0.04, sy1, sz1)), cube(bm, (sx1 - 0.04, sy0, sz0), (sx1, sy1, sz1)),
                                                        cube(bm, (sx0, sy0, sz1 - 0.06), (sx1, sy0 + 0.04, sz1))))
    part("Cafe_Shutter_Box", "Metal_Dark", lambda bm: cube(bm, (sx0 - 0.05, sy1, sz0 - 0.05), (sx1 + 0.05, sy1 + 0.32, sz1 + 0.06)))
    panel("Cafe_Sign", "Sign_Dept", ((sx0 + sx1) / 2, sy1 + 0.16, sz1 + 0.0605), "+z", 2.4, 0.26, uv=sign_uv(wall_row("CAFE")))
    part("Cafe_Card_Board", "Shelf_Paint", lambda bm: cube(bm, (-21.1, 1.62, sz1 - 0.03), (-20.1, 1.81, sz1 - 0.02)))
    panel("Cafe_Card", "Sign_Dept", (-20.6, 1.715, sz1 - 0.0195), "+z", 0.96, 0.17, uv=sign_uv(wall_row("SORRY - CLOSED")))
    cooler_bank(RS, "Cafe_Fridge", "+x", -21.9, 2, y=(0.18, 2.0))
    w = BOX["Cafe_Wall_E"]                                   # CAFE on the partition's east face, for whoever comes in through the glass doors
    part("Cafe_Sign_E_Board", "EndCap_Red", lambda bm: cube(bm, (w["max"][0], 2.05, -23.2), (w["max"][0] + 0.025, 2.55, -20.6)))
    panel("Cafe_Sign_E", "Sign_Dept", (w["max"][0] + 0.0255, 2.3, -21.9), "+x", 2.5, 0.42, uv=sign_uv(wall_row("CAFE")))
    bar = BOX["Cafe_Barrier"]
    glass_balustrade(RS, bar, post_step=1.0)
    for k in range(1, 6):
        t = BOX[f"Cafe_Table_{k}"]
        (tx0, _, tz0), (tx1, ty1, tz1) = t["min"], t["max"]
        xc, zc = (tx0 + tx1) / 2, (tz0 + tz1) / 2
        p = Painter()                                   # one object a table, so its box covers the collider
        p.add("chair_seat", cube, (tx0, ty1 - 0.03, tz0), (tx1, ty1, tz1))
        p.add("cart_black", cyl, (xc, 0.0, zc), (xc, ty1 - 0.03, zc), 0.03, None, 10)
        p.add("cart_black", cube, (tx0 + 0.02, 0.0, zc - 0.04), (tx1 - 0.02, 0.03, zc + 0.04))
        p.add("cart_black", cube, (xc - 0.04, 0.0, tz0 + 0.02), (xc + 0.04, 0.03, tz1 - 0.02))
        p.done(f"Cafe_Table_{k}_Art")
        q = Painter()
        chair_up(q, xc - 0.2, ty1, zc, 0.0)
        chair_up(q, xc + 0.2, ty1, zc, math.pi)
        q.done(f"decor_Cafe_Chairs_Up_{k}")


def s_below():
    """The view down over the aisles (art only, decor_below_*): the hall 5 m below as the aisles are dressed, simplified where it is far."""
    R = RB
    x0 = MEZ["x1"]
    for b in GA.boxes:
        n = b["name"]
        if n == "Aisles_Floor":
            part("decor_below_Shell_Floor", "Below_Floor", lambda bm, b=b: cube(bm, (x0, b["min"][1] + DY, b["min"][2]), (b["max"][0], b["max"][1] + DY, b["max"][2])), cull="up")
        elif n == "Aisles_Ceiling":
            part("decor_below_Shell_Ceiling", "Below_Ceiling", lambda bm, b=b: cube(bm, (x0 - 0.2, b["min"][1] + DY, b["min"][2]), (b["max"][0], b["max"][1] + DY, b["max"][2])), cull="down")
        elif n.startswith("Aisles_Wall_") and n not in ("Aisles_Wall_W_1",):
            mn, mx = shift(b, DY)
            lo = max(mn[0], x0 - 0.2)
            if mx[0] <= lo:
                continue
            for a, c, mat in ((b["min"][1], min(b["max"][1], BAND), "Below_Lower"), (max(b["min"][1], BAND), b["max"][1], "Below_Wall")):
                if c > a:
                    part(f"decor_below_Shell_{n}_{mat}", mat, lambda bm, a=a, c=c, mn=mn, mx=mx, lo=lo: cube(bm, (lo, a + DY, mn[2]), (mx[0], c + DY, mx[2])), cull="wall")
    for b in GA.boxes:
        n = b["name"]
        if n.startswith("Gondola_E"):
            (gx0, gy0, gz0), (gx1, gy1, gz1) = shift(b, DY)
            part(f"decor_below_{n}_Body", "Shelf_Paint", lambda bm: cube(bm, (gx0 + 0.02, gy0, gz0), (gx1 - 0.02, gy1, gz1)), cull="below_body")
            panels(f"decor_below_{n}_Stock", "Below_Stock", [((gx0 - 0.001, (gy0 + gy1) / 2, (gz0 + gz1) / 2), "-x", gz1 - gz0, gy1 - gy0, (0, 0, (gz1 - gz0) / 2.0, 1)),
                                                             ((gx1 + 0.001, (gy0 + gy1) / 2, (gz0 + gz1) / 2), "+x", gz1 - gz0, gy1 - gy0, (0, 0, (gz1 - gz0) / 2.0, 1))])
        elif n.startswith("Endcap_E"):
            endcap(R, b)
        elif n in ("Wall_Shelving_E", "Wall_Shelving_N"):
            (wx0, wy0, wz0), (wx1, wy1, wz1) = shift(b, DY)
            part(f"decor_below_{n}_Body", "Shelf_Paint", lambda bm: cube(bm, (wx0, wy0, wz0), (wx1, wy1, wz1)))
            if n.endswith("E"):
                panels(f"decor_below_{n}_Stock", "Below_Stock", [((wx0 - 0.001, wy0 + 0.95, (wz0 + wz1) / 2), "-x", wz1 - wz0, 1.9, (0, 0, (wz1 - wz0) / 2.0, 1))])
            else:
                panels(f"decor_below_{n}_Stock", "Below_Stock", [(((wx0 + wx1) / 2, wy0 + 0.95, wz1 + 0.001), "+z", wx1 - wx0, 1.9, (0, 0, (wx1 - wx0) / 2.0, 1))])
    for i, (a0, n) in enumerate(S_COOLERS):
        if a0 > x0:
            cooler_bank(R, f"Cooler_S{i}", "-z", a0, n)
    a_corral(R, GA)
    a_clearing(R)
    a_signs(R)
    a_strips(R)
    build_stairs(R, GA)
    build_escalator(R, GA)
    emergency(R, "Emergency", [("-x", -42.0), ("-x", -20.0), ("-x", -12.5), ("+z", 3.5), ("+z", 16.5), ("-z", 21.5)], 3.0)
    exit_sign(R, "Exit_Opening", "-z", 0.0, G.MF["opening"][2] + 0.4)
    # the carts the page parks in the clearing and the corral, as plain red carts (the view down only)
    p = Painter()
    cx, cz = (G.CLEAR["x0"] + G.CLEAR["x1"]) / 2, (G.CLEAR["z0"] + G.CLEAR["z1"]) / 2
    spots = [(cx + 3.2 * math.cos(2 * math.pi * k / 8), cz + 3.2 * math.sin(2 * math.pi * k / 8), 2 * math.pi * k / 8 + math.pi / 2) for k in range(8)]
    spots += [(x, -11.0, 0.0) for x in (4.6, 5.5, 6.4)]
    for x, z, yaw in spots:
        cart(p, x, DY, z, yaw)
    p.done("decor_below_Carts")


def cart(p, x, y, z, yaw):
    """A plain shopping cart (the view down only): a red wire basket on a grey chassis, four black wheels, a handle."""
    c, s = math.cos(yaw), math.sin(yaw)

    def P(u, v, h):
        return (x + u * c - v * s, y + h, z + u * s + v * c)

    def slab(key, u0, u1, v0, v1, h0, h1):
        p.add(key, lambda bm: prism(bm, [P(u0, v0, h0), P(u1, v0, h0), P(u1, v1, h0), P(u0, v1, h0)], [P(u0, v0, h1), P(u1, v0, h1), P(u1, v1, h1), P(u0, v1, h1)]))
    slab("cart_red", -0.28, 0.28, -0.45, 0.45, 0.42, 0.45)
    for u0, u1, v0, v1 in ((-0.28, 0.28, -0.45, -0.43), (-0.28, 0.28, 0.43, 0.45), (-0.28, -0.26, -0.45, 0.45), (0.26, 0.28, -0.45, 0.45)):
        slab("cart_red", u0, u1, v0, v1, 0.45, 0.85)
    slab("cart_grey", -0.24, 0.24, -0.42, 0.42, 0.12, 0.14)
    for u in (-0.2, 0.2):
        slab("cart_grey", u - 0.015, u + 0.015, 0.42, 0.47, 0.12, 0.95)
    slab("cart_black", -0.26, 0.26, 0.46, 0.5, 0.95, 0.99)
    for u, v in ((-0.2, -0.36), (0.2, -0.36), (-0.2, 0.36), (0.2, 0.36)):
        slab("cart_black", u - 0.02, u + 0.02, v - 0.05, v + 0.05, 0.0, 0.12)


def s_fittings():
    strips(RS, "Strips", [-22.6, -19.2, -15.6, -12.0, -8.4, -5.8], RS.z0 + 0.9, RS.z1 - 0.9, RS.h - 0.12, RS.h)
    emergency(RS, "Emergency", [("+x", -36.0), ("+x", -27.0), ("+x", -18.0), ("+z", -20.0), ("+z", -8.0), ("-z", -10.0), ("-z", -6.0), ("-z", -20.0)], 2.55)
    exit_sign(RS, "Exit_Doors", "-x", (G.OPEN_STAIR + G.OPEN_ESC) / 2, 2.45, d=0.3, hang=RS.h)
    for e in GB.empties:
        if e["name"] == "Spot_camhead_1":
            cam_bracket(RS, "Cam_Bracket_1", e, "+x")
    wall_sign(RS, "Sign_Homeware_W", "+x", -40.5, 2.45, 2.8, 0.46, wall_row("HOMEWARE"))


def build_second_floor():
    s_shell()
    s_homeware()
    s_cafe()
    s_fittings()
    s_below()


# ---------------------------------------------------------------- the layout objects
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


# ---------------------------------------------------------------- lights, light sets
STRIP_WPM = 20.0          # each strip light: an area light the length of the strip, pointing down, W per metre
EMERG_W = 120.0           # each emergency head (a spot)
COOLER_WPM = 14.0         # each cooler or freezer bank's glow (an area light over its glass), W per metre
EXIT_W = 3.0
MEZZ_UP_W = 120.0         # aisles: the second floor's strips behind the glass (art only), by day


def orient(ob, gdir, gtan):
    """Point a light down game direction gdir (its local -Z), its rectangle's local x along game direction gtan."""
    z = -B(gdir).normalized()
    x = B(gtan).normalized()
    y = z.cross(x)
    ob.rotation_euler = Matrix((x, y, z)).transposed().to_euler()


TANGENT = {"+x": (0, 0, 1), "-x": (0, 0, 1), "+z": (1, 0, 0), "-z": (1, 0, 0)}


def add_lights():
    cols = {}
    for name in ("Lights_Day", "Lights_Night", "Lights_Always"):
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        cols[name] = c

    def light(coll, name, kind, pos, energy, color, size):
        d = bpy.data.lights.new(name, kind)
        d.energy, d.color = energy, color
        d.shadow_soft_size = size
        ob = bpy.data.objects.new(name, d)
        ob.location = B(pos)
        cols[coll].objects.link(ob)
        return ob, d
    for i, (x, y, z0, z1) in enumerate(STRIPS):
        if y > 5.0 + 3.0 and SCENE == "aisles":            # the second floor's strips behind the glass
            ob, d = light("Lights_Day", f"Strip_{i:02d}", "AREA", (x, y - 0.004, (z0 + z1) / 2), MEZZ_UP_W, (0.96, 0.98, 1.0), 0.0)
        else:
            ob, d = light("Lights_Day", f"Strip_{i:02d}", "AREA", (x, y - 0.004, (z0 + z1) / 2), STRIP_WPM * (z1 - z0), (0.96, 0.98, 1.0), 0.0)
        d.shape, d.size, d.size_y = "RECTANGLE", 0.14, z1 - z0 - 0.1
    for i, (p, dd) in enumerate(EMERG):
        ob, d = light("Lights_Night", f"Emergency_{i:02d}", "SPOT", tuple(Vector(p) + Vector(dd) * 0.045), EMERG_W, (0.86, 0.93, 1.0), 0.03)
        d.spot_size, d.spot_blend = math.radians(80), 0.45
        ob.rotation_euler = B(dd).to_track_quat("-Z", "Y").to_euler()
    for i, (R, n, a0, a1, y0, y1, lit) in enumerate(COOLERS):
        c = on_wall(R, n, (a0 + a1) / 2, (y0 + y1) / 2, 0.06)
        col = (0.84, 0.94, 1.0) if lit == "Cooler_Lit" else (0.72, 0.86, 1.0)
        ob, d = light("Lights_Always", f"Cooler_{i:02d}", "AREA", c, COOLER_WPM * (a1 - a0), col, 0.0)
        d.shape, d.size, d.size_y = "RECTANGLE", a1 - a0, y1 - y0 - 0.2
        orient(ob, NORMAL[n], TANGENT[n])
    for i, (c, n) in enumerate(EXITS):
        ob, d = light("Lights_Always", f"Exit_{i}", "AREA", tuple(Vector(c) + Vector(NORMAL[n]) * 0.01), EXIT_W, (0.3, 1.0, 0.45), 0.0)
        d.shape, d.size, d.size_y = "RECTANGLE", 0.44, 0.16
        orient(ob, NORMAL[n], TANGENT[n])


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("Dark")
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
    """day: the strips (Lamp_Emit on, Emergency_Emit off), the coolers, the EXIT signs; night: the emergency heads, the coolers, the EXIT signs;
    export: both toggled materials at the strength the page switches on."""
    for c, on in (("Lights_Day", name == "day"), ("Lights_Night", name == "night"), ("Lights_Always", True)):
        if c in bpy.data.collections:
            bpy.data.collections[c].hide_render = not on
    set_emit("Lamp_Emit", LAMP_EMIT if name in ("day", "export") else 0.0)
    set_emit("Emergency_Emit", EMERG_EMIT if name in ("night", "export") else 0.0)


def ensure_marker():
    st = bpy.data.collections["Standins"]
    ob = bpy.data.objects.get("standin_arrival_marker")
    if ob is None:
        a = next(e for e in GB.empties if e["name"] == "Marker_Spawn")["pos"]
        me = bpy.data.meshes.new("standin_arrival_marker")
        bm = bmesh.new()
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
    a = next(e for e in GB.empties if e["name"] == "Marker_Spawn")["pos"]
    want = [a[0], a[1] + 0.1, a[2]]
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
    for d in (IMG_CACHE, MATS, TILES, CULL):
        d.clear()
    for l in (STRIPS, EMERG, COOLERS, EXITS):
        l.clear()
    sc = bpy.context.scene
    ART, STANDIN, DOORS_C, LAYOUT_C = (bpy.data.collections.new(n) for n in ("Art", "Standins", "Doors", "Layout"))
    for c in (ART, STANDIN, DOORS_C, LAYOUT_C):
        sc.collection.children.link(c)
    make_materials(make_generated())
    if SCENE == "aisles":
        build_aisles()
    else:
        build_second_floor()
    build_door_leaves()
    build_layout()
    add_lights()
    setup_world()
    apply_light_set("day")
    ensure_marker()
    LAYOUT_C.hide_render = True
    for ob in ART.objects:                                  # the cull mode rides on the object until the bake (dropped by the scrub before export)
        ob["cull"] = CULL.get(ob.name, "prop")
        ob["occ"] = [v for mn, mx in OCC.get(ob.name, []) for v in (*mn, *mx)]
    tris = sum(len(p.vertices) - 2 for o in ART.objects for p in o.data.polygons)
    print(f"ART {len(ART.objects)} objects, about {tris} triangles; {len(STRIPS)} strips, {len(EMERG)} emergency heads, {len(COOLERS)} cooler banks")


def stage_layout():
    import export_scene
    export_scene.write(SCENE, ROOT / f"world/{SCENE}.json")


def stage_check():
    import check_layout
    code = check_layout.main(["--scene", SCENE, "--collection", "Art"])
    print("CHECK_LAYOUT exit", code)


# ---------------------------------------------------------------- bake
if SCENE == "aisles":
    GROUPS = [["Floor_Tile", "Ceiling_Tile", "Wall_Paint", "Wall_Lower", "Wall_High", "Trim_Steel", "Soffit_Paint"],
              ["Shelf_Paint", "Shelf_Back", "Shelf_Kick", "EndCap_Red", "Price_Rail", "Rail_Steel", "Frame_Alu", "Cooler_Frame", "Light_Housing",
               "Metal_Dark", "Plastic_Black", "Plastic_White", "Sign_Dept", "Handrail_Black", "Stair_Tread", "Esc_Tread", "Esc_Riser", "Esc_Clad",
               "Comb_Yellow"]]
    UV_SCALE = {"Ceiling_Tile": 0.35, "Wall_High": 0.6, "Soffit_Paint": 0.7, "Light_Housing": 0.5, "Metal_Dark": 0.6, "Shelf_Kick": 0.6,
                "Esc_Riser": 0.7, "Plastic_White": 0.7,
                "Shelf_Back": 0.6, "Price_Rail": 0.6, "Shelf_Paint": 0.85, "EndCap_Red": 0.8}
    SEEN_UP = 99.0
else:
    GROUPS = [["Floor_Tile", "Ceiling_Tile", "Wall_Paint", "Wall_Lower", "Trim_Steel", "Cafe_Wall", "Soffit_Paint", "Below_Floor", "Below_Wall",
               "Below_Lower", "Below_Ceiling"],
              ["Shelf_Paint", "Shelf_Back", "Shelf_Kick", "EndCap_Red", "Price_Rail", "Rail_Steel", "Frame_Alu", "Cooler_Frame", "Light_Housing",
               "Metal_Dark", "Plastic_Black", "Plastic_White", "Sign_Dept", "Handrail_Black", "Stair_Tread", "Paint_Palette", "Wood_Light",
               "Counter_Laminate", "Counter_Top", "Shutter_Steel", "Below_Stock", "Esc_Tread", "Esc_Clad"]]
    UV_SCALE = {"Ceiling_Tile": 0.6, "Below_Floor": 0.3, "Below_Wall": 0.3, "Below_Lower": 0.4, "Below_Ceiling": 0.2, "Below_Stock": 0.5,
                "Light_Housing": 0.5, "Metal_Dark": 0.6, "Shelf_Kick": 0.6, "Paint_Palette": 0.8, "Shelf_Back": 0.7, "Price_Rail": 0.7, "Esc_Tread": 0.5, "Esc_Clad": 0.5, "Stair_Tread": 0.6}
    SEEN_UP = 2.0
PAGES = [2048, 2048]
MARGINS = [8, 4]          # px between islands: the props' many small islands get a narrower margin
NIGHT_OFFSET = 2
HIDE_IN_BAKE = ("Window_Glass",)
REF_MAT = "Wall_Paint"     # the auto exposure: G is set so this material's median texel shows at TARGET
CURVE_C = 1.15             # the shoulder's top: the page shows texture x C at most, so a white surface (albedo 0.8) stays under 0.95
TARGET = {"day": 0.80, "night": 0.40}       # G x (the reference wall's median light): texel G L / (C + G L)


def cull(bm, mode, R):
    """Drop faces never seen, before the lightmap UVs: the shell keeps its room-facing faces; a prop loses its bottom on the floor, its faces flush
    against a wall, and (second_floor) faces looking up from above SEEN_UP; the view down loses faces looking down or away from the mezzanine."""
    if mode == "keep":
        return
    e = 2e-3
    bad = []
    for f in bm.faces:
        c, n = f.calc_center_median(), f.normal
        gx, gy, gz = c.x, c.z, -c.y
        nx, ny, nz = n.x, n.z, -n.y
        ly = gy - R.oy
        if mode == "up":
            out = not (ny > 0.9)
        elif mode == "down":
            out = not (ny < -0.9)
        elif mode == "wall":
            p = (gx + nx * 0.02, ly + ny * 0.02, gz + nz * 0.02)
            inside = R.x0 - e <= p[0] <= R.x1 + e and R.z0 - e <= p[2] <= R.z1 + e and -e <= p[1] <= R.h + e
            inside = inside or any(o[0] - e <= p[0] <= o[1] + e and o[2] - e <= p[1] <= o[3] + e and o[4] <= p[2] <= o[5] for o in R.openings)
            out = not inside or (abs(ny) > 0.9 and (ly < e or ly > R.h - e or abs(ly - BAND) < e or abs(ly - 3.6) < e))
        else:
            out = (ny < -0.9 and ly < 0.02) or (nx < -0.9 and gx <= R.x0 + e) or (nx > 0.9 and gx >= R.x1 - e) \
                or (nz < -0.9 and gz <= R.z0 + e) or (nz > 0.9 and gz >= R.z1 - e)
            if mode == "shelf":                               # shelving: nobody looks up at a board's underside for long
                out = out or ny < -0.5
            if mode == "below_body":                          # its long sides are under the stock pictures
                out = out or ny < -0.5 or abs(nx) > 0.9
            if mode == "below":
                out = out or ny < -0.5 or (nx > 0.9 and gx > MEZ["x1"])
            elif ny > 0.9 and ly > SEEN_UP:
                out = True
        if out:
            bad.append(f)
    bmesh.ops.delete(bm, geom=bad, context="FACES")


def drop_buried(bm, boxes):
    """Drop the faces that lie flat inside another piece's box (a tread's underside on its step's body, a slab's top under its tiles): their
    corners and centre, 4 mm out along the normal, all inside one box."""
    if not len(boxes):
        return 0
    mn, mx = boxes[:, :3] + 1e-4, boxes[:, 3:] - 1e-4
    bad = []
    for f in bm.faces:
        c, n = f.calc_center_median(), f.normal
        pts = np.array([tuple(c + (v.co - c) * 0.98 + n * 0.004) for v in f.verts] + [tuple(c + n * 0.004)])
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        if np.any(np.all(mn <= lo, axis=1) & np.all(mx >= hi, axis=1)):
            bad.append(f)
    bmesh.ops.delete(bm, geom=bad, context="FACES")
    return len(bad)


def room_of(oname):
    if oname.startswith("decor_below_"):
        return RB
    return ROOM


def make_export_objects():
    art = bpy.data.collections["Art"]
    if "Export" in bpy.data.collections:
        for o in list(bpy.data.collections["Export"].objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(bpy.data.collections["Export"])
    exp = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(exp)
    boxes, owner = [], []
    for i, ob in enumerate(art.objects):
        if ob.data.materials[0].name in NOLM or "occ" not in ob:
            continue
        v = list(ob["occ"])
        for k in range(0, len(v), 6):
            boxes.append(v[k:k + 6])
            owner.append(i)
    boxes = np.array(boxes, np.float64).reshape(-1, 6)
    owner = np.array(owner)
    buried = 0
    by_mat = {}
    for i, ob in enumerate(art.objects):
        assert len(ob.data.materials) == 1, ob.name
        mname = ob.data.materials[0].name
        bm = by_mat.setdefault(mname, bmesh.new())
        tmp = bmesh.new()
        tmp.from_mesh(ob.data)
        tmp.normal_update()
        if mname not in NOLM:
            cull(tmp, ob.get("cull", "prop"), room_of(ob.name))
            buried += drop_buried(tmp, boxes[owner != i])
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
    print(f"  {buried} buried faces dropped")
    for n in [m for g in GROUPS for m in g]:
        assert n not in NOLM
    left = [m for m in out if m not in NOLM and not any(m in g for g in GROUPS)]
    assert not left, f"materials in no lightmap group: {left}"
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


THIN = 0.05                # a face narrower than this gets no island of its own (see lightmap_uv)


def lightmap_uv(objs, page, margin=MARGIN_PX):
    """One atlas for `objs`: smart-project islands at equal texel density (UV_SCALE scales a material down), packed with `margin` px. Thin faces
    are left out of the pack and laid on the edge of the broad face beside them (they take that edge's light), since each island costs its margin."""
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
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        if o.name in UV_SCALE:
            d = o.data.uv_layers["lightmap"].data
            us = np.array([x.uv for x in d]) * UV_SCALE[o.name]
            d.foreach_set("uv", us.ravel())
    remap = {}
    for o in objs:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.faces.ensure_lookup_table()

        def thin(f):
            return min(e.calc_length() for e in f.edges) < THIN and f.calc_area() > 0
        fl = {}
        for f in bm.faces:
            f.select = True
            if len(f.verts) != 4 or not thin(f):
                continue
            best = None
            for e in sorted(f.edges, key=lambda e: -e.calc_length()):
                for g in e.link_faces:
                    if g is not f and not thin(g):
                        best = (e, g)
                        break
                if best:
                    break
            if best:
                e, g = best
                f.select = False
                fl[f.index] = (g.index, {v.index: (v.index if v in e.verts else min(e.verts, key=lambda w: (w.co - v.co).length).index) for v in f.verts})
        bm.to_mesh(o.data)
        bm.free()
        remap[o.name] = fl
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=margin / page, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    nthin = 0
    for o in objs:
        me = o.data
        uv = me.uv_layers["lightmap"].data
        for fi, (gi, vmap) in remap[o.name].items():
            guv = {me.loops[li].vertex_index: uv[li].uv.copy() for li in me.polygons[gi].loop_indices}
            for li in me.polygons[fi].loop_indices:
                w = vmap.get(me.loops[li].vertex_index)
                if w in guv:
                    uv[li].uv = guv[w]
            nthin += 1
    print(f"  {nthin} thin faces laid on their neighbours' edges")
    plain = [o for o in objs if o.name not in UV_SCALE and o.type == "MESH"]
    a3 = sum(area3d(o) for o in plain)
    au = sum(uv_area(o, "lightmap") for o in plain)
    dens = page * math.sqrt(au / a3) if a3 else 0.0
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


def uv_mask(ob, S):
    """The texels an object covers in its lightmap (rows bottom to top)."""
    m = np.zeros((S, S), bool)
    uv = ob.data.uv_layers["lightmap"].data
    for p in ob.data.polygons:
        pts = [np.array(uv[i].uv) * S for i in p.loop_indices]
        for k in range(1, len(pts) - 1):
            a, b, c = pts[0], pts[k], pts[k + 1]
            x0, x1 = int(max(0, math.floor(min(a[0], b[0], c[0])))), int(min(S - 1, math.ceil(max(a[0], b[0], c[0]))))
            y0, y1 = int(max(0, math.floor(min(a[1], b[1], c[1])))), int(min(S - 1, math.ceil(max(a[1], b[1], c[1]))))
            yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1] + 0.5

            def side(p, q):
                return (q[0] - p[0]) * (yy - p[1]) - (q[1] - p[1]) * (xx - p[0])
            s1, s2, s3 = side(a, b), side(b, c), side(c, a)
            inside = ((s1 >= 0) & (s2 >= 0) & (s3 >= 0)) | ((s1 <= 0) & (s2 <= 0) & (s3 <= 0))
            m[y0:y1 + 1, x0:x1 + 1] |= inside
    return m


def bake_set(n, objs, S, light_set, samples, margin=MARGIN_PX):
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
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=margin, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
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
    setup_cycles(SAMPLES, bake=True)
    for m in HIDE_IN_BAKE:
        if m in exp:
            exp[m].hide_render = True
    report, gain = {}, {}
    for n, mats in enumerate(GROUPS):
        objs = [exp[m] for m in mats if m in exp] + (leaves if n == 1 else [])
        print(f"lightmap {n}: {[o.name for o in objs]}")
        S, dens, small = lightmap_uv(objs, PAGES[n], MARGINS[n])
        ref = uv_mask(exp[REF_MAT], S) if n == 0 else None
        for light_set, idx, samples in (("day", n, SAMPLES), ("night", n + NIGHT_OFFSET, NIGHT_SAMPLES)):
            t0 = time.time()
            rgb = bake_set(n, objs, S, light_set, samples, MARGINS[n])
            peak = rgb.max(axis=2)
            sel = peak > 1e-6
            pc = np.percentile(peak[sel], [50, 90, 99, 99.5, 100]) if sel.any() else [1.0] * 5
            if n == 0:
                med = float(np.median(peak[ref & sel])) if (ref & sel).any() else float(pc[0])
                gain[light_set] = TARGET[light_set] / max(med, 1e-6)
                print(f"  {light_set}: the reference wall's median light {med:.4f} -> G {gain[light_set]:.3f}")
            Gn, C = gain[light_set], CURVE_C
            tex = Gn * rgb / (C + Gn * rgb)                      # the shoulder: the page shows texture x C x tex; never clips
            out = np.ones((S, S, 4), np.float32)
            out[..., :3] = srgb_encode(tex)
            png = bpy.data.images.new(f"LM_{idx}_png", S, S, alpha=False)
            png.colorspace_settings.name = "Non-Color"
            png.pixels.foreach_set(out.ravel())
            png.filepath_raw = str(stage_work() / f"{SCENE}_{idx}.png")
            png.file_format = "PNG"
            png.save()
            bpy.data.images.remove(png)
            report[idx] = {"map": n, "set": light_set, "size": S, "curve_G_C": [round(Gn, 4), C], "px_per_m": round(dens, 1), "px_per_m_scaled": small,
                           "p50_p90_p99_p995_max": [round(float(v), 4) for v in pc], "samples": samples, "device": bpy.context.scene.cycles.device,
                           "seconds": round(time.time() - t0), "materials": [o.name for o in objs]}
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


def set_intensities():
    """Each baked material carries its map's path and pi x C (the page shows texture x texel x intensity / pi)."""
    rep = json.loads((stage_work() / "lightmaps.json").read_text())
    for idx, r in rep.items():
        idx = int(idx)
        key, kkey = ("lightmap", "lightmap_intensity") if r["set"] == "day" else ("lightmap_night", "lightmap_night_intensity")
        for nm in r["materials"]:
            ob = bpy.data.objects.get(nm)
            mats = [s.material for s in ob.material_slots] if ob else []
            for m in mats:
                if m is None or m.name in NOLM:
                    continue
                m[key] = LM_URL.format(idx)
                m[kkey] = round(math.pi * r["curve_G_C"][1], 4)


def scrub_ui_paths():
    for sc in bpy.data.screens:
        for a in sc.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"_" * 1000
                    sp.params.directory = b"//"


KEEP_PROPS = {"lightmap", "lightmap_intensity", "lightmap_night", "lightmap_night_intensity"}
LAYOUT_PREFIX = ("DoorLeaf_", "Spot_", "Marker_", "Link_", "Arrive_")
SYS_KEEP = ("cycles", "eevee")


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private(keep_layout=True, keep_cull=True):
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
                    if kind == "objects" and st is idb and keep_cull and k in ("cull", "occ"):
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
    cam.clip_start, cam.clip_end = 0.05, 250
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
    if SCENE == "aisles":
        a = next(e for e in GB.empties if e["name"] == "Arrive_main_floor")
        p, f = a["pos"], a["face"]
        return {
            "1_arrival": look_cam("arrival", (p[0], 1.6, p[2]), (p[0] + f[0] * 3, 1.6, p[2] + f[1] * 3), 75.0),
            "2_wide": look_cam("wide", (22.6, 3.3, -47.6), (-4.0, 0.6, -22.0), 70.0),
            "3_detail": look_cam("detail", (3.4, 1.6, -11.6), (-2.6, 2.6, -19.5), 70.0),
            "4_clearing": look_cam("clearing", (14.4, 1.6, -24.2), (4.0, 0.6, -31.5), 70.0),
            "5_under": look_cam("under", (-5.3, 1.6, -11.6), (-12.0, 1.4, -30.0), 70.0),
        }
    a = next(e for e in GB.empties if e["name"] == "Arrive_stairs_down")
    p, f = a["pos"], a["face"]
    return {
        "1_arrival": look_cam("arrival", (p[0], 1.6, p[2]), (p[0] + f[0] * 3, 1.6, p[2] + f[1] * 3), 75.0),
        "2_wide": look_cam("wide", (-5.0, 2.3, -43.4), (-15.5, 0.6, -24.0), 75.0),
        "3_detail": look_cam("detail", (-14.6, 1.6, -15.0), (-20.6, 1.2, -22.4), 68.0),
        "4_view": look_cam("view", (-4.9, 1.6, -30.0), (8.0, -4.6, -30.0), 75.0),
    }


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
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    expo = arg("--exposure", 0.0, float)
    which = arg("--only", "all")
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    cams = shots()
    R = ROOM
    ymax = 2.4
    plan = look_cam("plan", ((R.x0 + R.x1) / 2, 30.0, (R.z0 + R.z1) / 2), None, ortho=max(R.x1 - R.x0, R.z1 - R.z0) * 1.04)
    arts = list(bpy.data.collections["Art"].objects) + list(bpy.data.collections["Doors"].objects)

    def lowest(o):
        return min((o.matrix_world @ Vector(c)).z for c in o.bound_box)
    cut_plan = [o for o in arts if lowest(o) >= ymax or "Ceiling" in o.name or o.name.startswith("decor_below_Shell_Ceiling")]
    W_, H_ = 1500, int(1500 * (R.z1 - R.z0) / (R.x1 - R.x0))
    if SCENE == "second_floor":
        W_, H_ = 1100, 1600
    todo = [(k, v, (1920, 1080)) for k, v in cams.items()] + [("9_plan", plan, (W_, H_))]
    suffix = "" if light_set == "day" else "_" + light_set
    for key, cam, (w, h) in todo:
        if which not in ("all", key) and not (which == "review" and key in ("1_arrival", "2_wide", "3_detail")):
            continue
        sc.camera = cam
        sc.view_settings.exposure = expo + (0.6 if key == "9_plan" else 0.0)
        for o in arts:
            o.visible_camera = True
        for o in {"9_plan": cut_plan}.get(key, []):
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
    ST = set(STAGE.split(","))
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
