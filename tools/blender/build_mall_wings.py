"""Dresses and lights the mall's three concourses (`wing_books`, `wing_cinema`, `wing_entertainment`; docs/BLENDER_AREAS.md section 3) in Blender,
bakes a day set and the emergency set, and exports world/<scene>.glb and world/<scene>.json.

Re-runnable, from the repo root, one scene a run:

    blender -b --python tools/blender/build_mall_wings.py -- --scene wing_books --stage art          (the art and the layout objects; saves the .blend)
    blender -b blender/scenes/wing_books.blend --python tools/blender/build_mall_wings.py -- --scene wing_books --stage layout   (world/<scene>.json)
    blender -b blender/scenes/wing_books.blend --python tools/blender/build_mall_wings.py -- --scene wing_books --stage check    (the layout check)
    blender -b blender/scenes/wing_books.blend --python tools/blender/build_mall_wings.py -- --scene wing_books --stage bake [--samples 512]
    blender -b blender/scenes/wing_books.blend --python tools/blender/build_mall_wings.py -- --scene wing_books --stage export
    blender -b blender/scenes/wing_books.blend --python tools/blender/build_mall_wings.py -- --scene wing_books --stage axes
    blender -b blender/scenes/wing_books.blend --python tools/blender/build_mall_wings.py -- --scene wing_books --stage render [--set night] [--only 1_arrival]
    python tools/blender/pack_scene.py wing_books --work <work>                                    (WebP lightmaps and textures -> world/)

`--stage art,layout,check` runs several stages in one go; `--work <dir>` is the work folder (lightmap PNGs, the raw GLB, the night stills).

The layout is the greybox's: tools/blender/build_mall_greybox.py `wing()` (imported here; no coordinate is copied by hand) gives every collider,
door, link, marker and spot, turned so the wing's north is the mall's. This build makes the art in the wing's own frame (the atrium's doors at the
west end, x -20, the far end at x +20, the long walls at z -7 and +7) and turns it the same way at the end, so art and layout agree; it writes the
same names (COL_, DoorLeaf_, Link_/Arrive_, Marker_, Spot_) into the .blend, and tools/blender/export_scene.py writes the same world/<scene>.json
as the greybox model does.

The look follows part 1's atrium (`entrance`, tools/blender/build_entrance.py, whose textures and part-building code this reuses): terrazzo in
a dark border, beige plaster, painted steel roller shutters with hand-painted fascia signs, plywood hoardings, tube scaffolding with dust sheets,
a glazed skylight strip being repaired; old, abandoned and halfway through a refit nobody finished. Each wing has its theme: books (book and
stationery shops), cinema (a row of poster cases, a ticket kiosk, the RESTROOMS bay to mirror_bathroom, the marquee over the cinema's doors),
entertainment (an arcade front, the SOFT PLAY sign, the food court's entrance).

Light, as in entrance: day = the sun and the sky through the skylight strip and the working ceiling downlights (`Lamp_Emit`, on by day, off
while the mall is locked); night = the emergency fittings alone (`Emergency_Emit`, on only while the mall is locked). Both sets bake to the same
lightmap UVs: `lightmap` and `lightmap_night`. The page draws the mannequins (`Spot_mannequin_<n>`): their places are left clear.
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
import build_mall_greybox as G          # noqa: E402  the layout model (pure Python)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


SCENE = arg("--scene", "wing_books")
assert SCENE in G.WINGS, SCENE
STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 512, int)
NIGHT_SAMPLES = arg("--night-samples", None, int) or int(SAMPLES * 1.5)
DEVICE = arg("--device", "auto")
TEX = ROOT / "blender/textures/mall_wings"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"
MARGIN_PX = 8

CFG = G.WINGS[SCENE]
TURN = CFG["turn"]
GB = G.wing(SCENE, CFG["title"], CFG)                 # the layout as the game reads it (turned)


def _local():
    """The same wing, not turned: the frame the art is built in."""
    keep = G.turn
    G.turn = lambda S, deg: None
    try:
        return G.wing(SCENE, CFG["title"], CFG)
    finally:
        G.turn = keep


LOC = _local()
BOXL = {b["name"]: b for b in LOC.boxes}
WX, WZ, WH, T = G.WX, G.WZ, G.WH, G.T
BAYS = G.BAYS
PILASTERS = (-12.0, -4.0, 4.0, 12.0)
SHOP_H = 3.2                    # the shutters' and the fronts' top (the greybox's)
FASCIA_TOP = 4.3                # the painted fascia over each bay
SIGN_Y0, SIGN_Y1 = 3.45, 4.05   # the sign board (the greybox's Sign_ boxes)
BAND = 4.4                      # the plaster changes shade above the fascias (as entrance's gallery line)
SKX, SKZ = WX - 2.0, 2.5        # the skylight strip's opening (the greybox's Skylight)
LANTERN_UP, LANTERN_RIDGE = 0.45, 0.9
DOOR_H, DOOR_W = G.DOOR_H, G.DOOR_W
SIDE = {"N": "+z", "S": "-z"}
ZC = {"N": -WZ, "S": WZ}
EID, ETO, EW, EKIND = CFG["end"]
EH = 2.6 if EW > 1.5 else DOOR_H

_c, _s = round(math.cos(math.radians(TURN)), 12), round(math.sin(math.radians(TURN)), 12)
ROT = Matrix.Rotation(math.radians(TURN), 4, "Z")


def W(p):
    """A point (or direction) in the wing's own frame -> the scene's (game) frame: the greybox's turn."""
    x, y, z = p
    return (x * _c + z * _s + 0.0, y, -x * _s + z * _c + 0.0)


def L(p):
    """The inverse: a game point -> the wing's own frame."""
    x, y, z = p
    return (x * _c - z * _s + 0.0, y, x * _s + z * _c + 0.0)


def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


def BW(p):
    return B(W(p))


# ---------------------------------------------------------------- each wing's theme
THEMES = {
    "wing_books": {
        "label": "BOOKS & STATIONERY",
        "rename": {},
        "boarded": [("N", 0.0)],                                         # CALENDARS: closed for good, boarded over
        "door_style": {"bookstore": "books", "scene_2909": "shutters", "service_corridor": "staff"},
        "door_sign": {"bookstore": "BOOKSTORE", "scene_2909": "", "service_corridor": "STAFF ONLY"},
        "hanging": ["BOOKS & STATIONERY", "BOOKSTORE  >"],
    },
    "wing_cinema": {
        "label": "CINEMA",
        "rename": {},
        "boarded": [("N", 0.0)],                                         # VIDEO RENTAL
        "door_style": {"mirror_bathroom": "tiles", "scene_3012": "shutters", "service_corridor": "staff"},
        "door_sign": {"mirror_bathroom": "RESTROOMS", "scene_3012": "", "service_corridor": "STAFF ONLY"},
        "hanging": ["CINEMA  >", "<  RESTROOMS"],
    },
    "wing_entertainment": {
        "label": "ENTERTAINMENT",
        "rename": {("S", -16.0): "ARCADE"},                              # the claw-machine bay is the arcade's front
        "boarded": [("N", 16.0)],                                        # KARAOKE
        "door_style": {"scene_2991": "padding", "scene_3008": "shutters", "service_corridor": "staff"},
        "door_sign": {"scene_2991": "SOFT PLAY", "scene_3008": "", "service_corridor": "STAFF ONLY"},
        "hanging": ["ENTERTAINMENT", "FOOD COURT  >"],
    },
}
TH = THEMES[SCENE]
DOORS = [dict(zip(("bx", "side", "did", "to", "w", "kind"), d)) for d in CFG["doors"]]
DOOR_BAYS = {(d["side"], d["bx"]) for d in DOORS}


def bay_name(side, k, bx):
    return TH["rename"].get((side, bx), CFG["names"][side][k])


def shop_bays():
    """(side, k, bx, name) of every shuttered (or boarded) bay."""
    return [(side, k, bx, bay_name(side, k, bx)) for side in ("N", "S") for k, bx in enumerate(BAYS) if (side, bx) not in DOOR_BAYS]


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
    """A Principled material (entrance's): `tint` multiplies the diffuse texture by a constant colour (the exporter writes baseColorFactor)."""
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
        if alpha == "texture":
            nt.links.new(n.outputs["Alpha"], bsdf.inputs["Alpha"])
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    if alpha is not None:
        if alpha != "texture":
            bsdf.inputs["Alpha"].default_value = alpha
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    TILES[name] = tile or 1.0
    MATS[name] = m
    return m


def emissive_image(name, img, strength, tile=1.0):
    m = material(name, color=(0, 0, 0), rough=0.4, tile=tile)
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = img
    nt.links.new(nt.nodes["UV Map"].outputs["UV"], tx.inputs["Vector"])
    nt.links.new(tx.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = strength
    return m


LAMP_EMIT = 10.0          # Lamp_Emit's exported strength (the downlights' lenses, the work lamp, the marquee's and the arcade's bulbs): on by day, off while locked
EMERG_EMIT = 6.0          # Emergency_Emit's exported strength (the emergency heads): on only while the mall is locked


def make_materials(gen):
    # entrance's surfaces, the same textures and tints, so the wings read as the same building
    material("Floor_Terrazzo", diff="terrazzo_tiles_diff_1k.jpg", tint=(0.92, 0.88, 0.84), rough=0.4, tile=2.0)
    material("Floor_Border", diff="terrazzo_tiles_diff_1k.jpg", tint=(0.42, 0.38, 0.36), rough=0.4, tile=2.0)
    material("Wall_Plaster", diff="beige_wall_001_diff_1k.jpg", tint=(0.92, 0.88, 0.80), rough=0.9, tile=2.4)
    material("Wall_Upper", diff="beige_wall_001_diff_1k.jpg", tint=(0.80, 0.78, 0.72), rough=0.9, tile=2.4)
    material("Ceiling_Paint", diff="beige_wall_001_diff_1k.jpg", tint=(0.96, 0.95, 0.92), rough=0.95, tile=3.0)
    material("Trim_Paint", color=(0.62, 0.60, 0.55), rough=0.55)
    material("Shutter_Metal", diff="painted_metal_shutter_diff_1k.jpg", tint=(0.80, 0.80, 0.80), rough=0.5, metal=0.2, tile=2.0)
    material("Hoarding_Ply", diff="plywood_diff_1k.jpg", tint=(0.95, 0.92, 0.88), rough=0.8, tile=1.2)
    material("Scaffold_Board", diff="plywood_diff_1k.jpg", tint=(0.62, 0.55, 0.45), rough=0.85, tile=0.9)
    material("Bench_Wood", diff="dark_wood_diff_1k.jpg", tint=(0.95, 0.85, 0.75), rough=0.6, tile=0.9)
    material("Concrete", diff="concrete_floor_02_diff_1k.jpg", tint=(0.78, 0.76, 0.72), rough=0.8, tile=1.6)
    material("Cloth_Sheet", diff="rough_linen_diff_512.jpg", tint=(1.0, 0.94, 0.82), rough=1.0, tile=0.8)
    material("Metal_Dark", color=(0.05, 0.05, 0.055), rough=0.45, metal=0.7)
    material("Metal_Steel", color=(0.42, 0.43, 0.44), rough=0.45, metal=0.85)
    material("Plastic_White", color=(0.70, 0.70, 0.67), rough=0.5)
    material("Clutter_Paint", color=(0.55, 0.50, 0.42), rough=0.7)
    material("Glass_Whitewash", img=gen["whitewash"], rough=0.3, tile=3.0)
    material("Sign_Paint", img=gen["signs"], rough=0.7)
    material("Poster_Art", img=gen["posters"], rough=0.6)
    material("Door_Leaves", img=gen["doors"], rough=0.6)
    material("Skylight_Glass", img=gen["skyglass"], rough=0.2, tile=1.5)
    material("Decal_Dust", img=gen["dust"], alpha="texture", rough=1.0)
    material("Decal_Stain", img=gen["stain"], alpha="texture", rough=1.0)
    if SCENE == "wing_cinema":
        material("Tile_White", img=gen["tiles"], rough=0.25, tile=0.8)
    if SCENE == "wing_entertainment":
        material("Padding_Vinyl", img=gen["padding"], rough=0.5, tile=1.2)
    material("Lamp_Emit", color=(1.0, 0.92, 0.80), rough=0.4, emit=((1.0, 0.90, 0.74), LAMP_EMIT))
    material("Emergency_Emit", color=(0.9, 0.95, 1.0), rough=0.3, emit=((0.85, 0.93, 1.0), EMERG_EMIT))
    emissive_image("Sign_Exit", gen["exit"], 3.0)


# ---------------------------------------------------------------- geometry helpers (entrance's; built in the wing's own frame, game axes)
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


def sphere(bm, p, r, seg=10):
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2 + 1, radius=r, matrix=Matrix.Translation(B(p)))


def disc(bm, p, r, seg=16):
    """A flat disc facing down (a downlight's rim or lens on the ceiling)."""
    vs = [bm.verts.new(B((p[0] + r * math.cos(2 * math.pi * k / seg), p[1], p[2] - r * math.sin(2 * math.pi * k / seg)))) for k in range(seg)]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.z > 0:
        f.normal_flip()


def quad(bm, p0, p1, p2, p3):
    return bm.faces.new([bm.verts.new(B(p)) for p in (p0, p1, p2, p3)])


def box_uv(bm, tile):
    """UV0: box projection in metres / tile from (wing-frame) world positions, so a texture runs on across the pieces of a wall."""
    uvl = bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y
            u, v = (gz, gy) if ax == 0 else ((gx, gy) if ax == 1 else (gx, gz))
            lp[uvl].uv = (u / tile, v / tile)


ART = STANDIN = DOORS_C = LAYOUT_C = None


def finish(name, bm, mat, coll=None, smooth=False, tile=None, sharp_deg=35, keep_uv=False, keep_normals=False):
    for e in bm.edges:
        if smooth and len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) < math.radians(sharp_deg)
        else:
            e.smooth = not (len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(1))
    for f in bm.faces:
        f.smooth = smooth
    if not (keep_uv or keep_normals):
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
    (coll or ART).objects.link(ob)
    return ob


def part(name, mat, build, smooth=False, tile=None, coll=None, keep_normals=False, keep_uv=False):
    bm = bmesh.new()
    if keep_uv:
        bm.loops.layers.uv.new("UVMap")
    build(bm)
    return finish(name, bm, mat, coll, smooth, tile, keep_normals=keep_normals, keep_uv=keep_uv)


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


def holed_box_xz(bm, xr, zr, y0, y1, holes):
    cx = sorted({xr[0], xr[1]} | {h[i] for h in holes for i in (0, 1) if xr[0] < h[i] < xr[1]})
    cz = sorted({zr[0], zr[1]} | {h[i] for h in holes for i in (2, 3) if zr[0] < h[i] < zr[1]})
    for x0, x1 in zip(cx, cx[1:]):
        for z0, z1 in zip(cz, cz[1:]):
            xm, zm = (x0 + x1) / 2, (z0 + z1) / 2
            if any(h[0] < xm < h[1] and h[2] < zm < h[3] for h in holes):
                continue
            cube(bm, (x0, y0, z0), (x1, y1, z1))
    bm.verts.index_update()
    dedupe_inner(bm)


# a wall is named by its inward normal; it runs along ALONG, its inner face lies at OUT
WALLS = {"+x": ("z", -WX), "-x": ("z", WX), "+z": ("x", -WZ), "-z": ("x", WZ)}
INWARD = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}
RIGHT = {"+x": (0, 0, -1), "-x": (0, 0, 1), "+z": (1, 0, 0), "-z": (-1, 0, 0)}   # facing a surface whose normal is n: your right hand


def on_wall(normal, a, y, d):
    ax, face = WALLS[normal]
    sign = 1 if normal[0] == "+" else -1
    off = face + sign * d
    return (off, y, a) if ax == "z" else (a, y, off)


def wall_box(bm, normal, a0, a1, y0, y1, d0, d1):
    p, q = on_wall(normal, a0, y0, d0), on_wall(normal, a1, y1, d1)
    cube(bm, [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)])


def panel(name, mat, centre, normal, w, h, uv=(0, 0, 1, 1), coll=None):
    """A flat quad facing `normal`, w wide, h tall, its UV the rectangle uv (u0, v0, u1, v1), the picture upright (entrance's)."""
    r = Vector(RIGHT[normal])
    up = Vector((0, 1, 0))
    c = Vector(centre)
    pts = [c - r * w / 2 - up * h / 2, c + r * w / 2 - up * h / 2, c + r * w / 2 + up * h / 2, c - r * w / 2 + up * h / 2]
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    f = quad(bm, *[tuple(p) for p in pts])
    u0, v0, u1, v1 = uv
    for lp, (s, t) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = (u0 + (u1 - u0) * s, v0 + (v1 - v0) * t)
    return finish(name, bm, mat, coll, keep_uv=True)


def orient_faces(ob, toward):
    tb = B(toward)
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    for f in bm.faces:
        if f.normal.dot(tb) < 0:
            f.normal_flip()
    bm.to_mesh(me)
    bm.free()


def corrugated(bm, normal, a0, a1, y0, y1, d, depth=0.012, pitch=0.075, step=0.025, uv=None):
    """A roller shutter's curtain (entrance's): a strip a0..a1 along a wall, y0..y1, at d from the wall's face, rippled by `depth` every `pitch`.
    uv: a rectangle (u0, v0, u1, v1) to stretch over it (a painted shutter), else the box projection."""
    rows = int(math.ceil((y1 - y0) / step))
    vs = []
    for i in range(rows + 1):
        y = y0 + (y1 - y0) * i / rows
        off = d + depth * 0.5 * (1 - math.cos(2 * math.pi * (y - y0) / pitch))
        vs.append((bm.verts.new(B(on_wall(normal, a0, y, off))), bm.verts.new(B(on_wall(normal, a1, y, off))), i / rows))
    uvl = bm.loops.layers.uv.get("UVMap")
    for (p0, p1, t0), (q0, q1, t1) in zip(vs, vs[1:]):
        f = bm.faces.new((p0, p1, q1, q0))
        if uv and uvl:
            u0, v0, u1, v1 = uv
            r = 1 if RIGHT[normal][0] + RIGHT[normal][2] > 0 else 0          # left to right as you face the shutter
            us = (u0, u1) if (a1 > a0) == bool(r) else (u1, u0)
            for lp, (s, t) in zip(f.loops, ((0, t0), (1, t0), (1, t1), (0, t1))):
                lp[uvl].uv = (us[0] + (us[1] - us[0]) * s, v0 + (v1 - v0) * t)


def drape(bm, base, t, nrm, a0, a1, profile, rng, folds=0.035, nu=18):
    """A cloth sheet hung over something (entrance's): profile [(d, y)] down the sheet, run a0..a1 along t from base; ragged hem."""
    P = [Vector(p) for p in profile]
    seg = [0.0]
    for p, q in zip(P, P[1:]):
        seg.append(seg[-1] + (q - p).length)
    tot = seg[-1]
    nv = max(4, int(tot / 0.12))
    ph = rng.uniform(0, 6.3, 3)
    rows = []
    for j in range(nv + 1):
        s = tot * j / nv
        k = max(i for i in range(len(seg)) if seg[i] <= s + 1e-9) if s < tot else len(seg) - 2
        k = min(k, len(P) - 2)
        f = (s - seg[k]) / max(1e-9, seg[k + 1] - seg[k])
        d, y = P[k] + (P[k + 1] - P[k]) * f
        row = []
        for i in range(nu + 1):
            a = a0 + (a1 - a0) * i / nu
            w = (s / tot) ** 1.3
            fold = folds * w * (math.sin(a * 7.1 + ph[0]) + 0.5 * math.sin(a * 13.7 + ph[1]))
            hem = (0.12 * math.sin(a * 3.3 + ph[2]) + 0.06 * math.sin(a * 9.1)) if j == nv else 0.0
            pt = Vector(base) + Vector(t) * a + Vector(nrm) * (d + fold) + Vector((0, 1, 0)) * (y + hem)
            row.append(bm.verts.new(B(tuple(pt))))
        rows.append(row)
    for r0, r1 in zip(rows, rows[1:]):
        for i in range(nu):
            bm.faces.new((r0[i], r1[i], r1[i + 1], r0[i + 1]))


def drape_box(bm, x0, x1, z0, z1, h, rng, hem=(0.06, 0.22), flare=0.03, folds=0.045, top=0.05, P=96):
    """A dust sheet thrown over a box-shaped thing: a domed top and four skirts falling to a ragged hem, all within x0..x1, z0..z1 (+ flare)."""
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    hx, hz = (x1 - x0) / 2, (z1 - z0) / 2
    ph = rng.uniform(0, 6.3, 6)

    def perim(t, sx, sz):                     # a point on a rectangle's perimeter, t in [0, 1)
        L_ = 2 * (sx + sz)
        s = (t % 1.0) * 2 * L_
        q = 2 * sx, 2 * sz
        if s < q[0]:
            return -sx + s, -sz
        s -= q[0]
        if s < q[1]:
            return sx, -sz + s
        s -= q[1]
        if s < q[0]:
            return sx - s, sz
        s -= q[0]
        return -sx, sz - s
    rings = []
    tops = [0.25, 0.55, 0.8, 0.94]
    for f in tops:                                                          # the top, domed a little
        y = h + top * (1 - f * f)
        rings.append([(cx + perim(i / P, hx * f, hz * f)[0], y, cz + perim(i / P, hx * f, hz * f)[1]) for i in range(P)])
    m = 6
    for j in range(m + 1):                                                  # the skirts
        u = j / m
        ring = []
        for i in range(P):
            t = i / P
            px, pz = perim(t, hx, hz)
            fold = folds * u * (math.sin(t * 37 + ph[0]) + 0.6 * math.sin(t * 83 + ph[1]))
            out = min(flare, max(-0.01, fold + flare * u * 0.5))
            ln = math.hypot(px / max(hx, 1e-6), pz / max(hz, 1e-6)) or 1.0
            nx_, nz_ = (px / hx if abs(abs(px) - hx) < 1e-6 else 0.0), (pz / hz if abs(abs(pz) - hz) < 1e-6 else 0.0)
            hm = hem[0] + (hem[1] - hem[0]) * (0.5 + 0.5 * math.sin(t * 11 + ph[2]) * math.sin(t * 5 + ph[3]))
            y = h - (h - hm) * u
            ring.append((cx + px + nx_ * out, y, cz + pz + nz_ * out))
        rings.append(ring)
    verts = [[bm.verts.new(B(p)) for p in r] for r in rings]
    cv = bm.verts.new(B((cx, h + top, cz)))
    for i in range(P):
        bm.faces.new((cv, verts[0][i], verts[0][(i + 1) % P]))
    for r0, r1 in zip(verts, verts[1:]):
        for i in range(P):
            bm.faces.new((r0[i], r1[i], r1[(i + 1) % P], r0[(i + 1) % P]))
    inside = B((cx, h * 0.3, cz))
    bm.normal_update()
    for f in bm.faces:
        if f.normal.dot(f.calc_center_median() - inside) < 0:
            f.normal_flip()


def flat_decal(bm, x0, x1, z0, z1, y=0.002, uv=(0, 0, 1, 1)):
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    f = quad(bm, (x0, y, z1), (x1, y, z1), (x1, y, z0), (x0, y, z0))
    u0, v0, u1, v1 = uv
    for lp, (s, t) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = (u0 + (u1 - u0) * s, v0 + (v1 - v0) * t)


# ---------------------------------------------------------------- generated pictures (own work, numpy, fixed seeds; the 5 x 7 font is entrance's)
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
    "&": ["01100", "10010", "10100", "01000", "10101", "10010", "01101"], "!": ["00100", "00100", "00100", "00100", "00100", "00000", "00100"],
    "'": ["00100", "00100", "01000", "00000", "00000", "00000", "00000"], "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    ">": ["01000", "00100", "00010", "00001", "00010", "00100", "01000"], "<": ["00010", "00100", "01000", "10000", "01000", "00100", "00010"],
    ",": ["00000"] * 5 + ["00100", "01000"], ":": ["00000", "00100", "00000", "00000", "00000", "00100", "00000"],
    "*": ["00000", "00000", "00000", "00100", "00000", "00000", "00000"],
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
    return (a[y0][:, x0] * (1 - fy) * (1 - fx) + a[y0][:, x1] * (1 - fy) * fx + a[y1][:, x0] * fy * (1 - fx) + a[y1][:, x1] * fy * fx)


def vnoise(h, w, rng, octaves=5, base=4):
    out, amp, tot = np.zeros((h, w)), 1.0, 0.0
    for k in range(octaves):
        n = base * 2 ** k + 1
        out += amp * rs(rng.random((n, n)), h, w)
        tot += amp
        amp *= 0.5
    return out / tot


def text_mask(text, h, w, rng, fill=0.62, maxw=0.9, painted=True):
    """A line of capitals in the 5 x 7 pixel font, centred in an h x w mask; `painted` rounds the strokes off like a brush's (entrance's)."""
    adv = 6
    units = max(1, len(text) * adv - 1)
    s = max(1, int(min(w * maxw / units, h * fill / 7)))
    m = np.zeros((h, w), np.float32)
    x = (w - units * s) // 2
    y0 = (h - 7 * s) // 2
    for ch in text:
        g = GLYPHS.get(ch, GLYPHS[" "])
        jy = int(rng.integers(-max(1, s // 5), max(1, s // 5) + 1)) if painted else 0
        for r, row in enumerate(g):
            for c, v in enumerate(row):
                if v == "1":
                    m[max(0, y0 + jy + r * s):max(0, y0 + jy + (r + 1) * s), x + c * s:x + (c + 1) * s] = 1
        x += adv * s
    if painted:
        k = max(1, s // 3)
        m = blur(m, k, 2)
        m = np.clip((m - 0.5) * 6 + (vnoise(h, w, rng, 4, 16) - 0.5) * 1.2 + 0.5, 0, 1)
    return m


def put_text(img, text, y0, y1, x0, x1, col, rng, fill=0.62, maxw=0.9, painted=False):
    m = text_mask(text, y1 - y0, x1 - x0, rng, fill, maxw, painted)
    img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - m[..., None]) + np.array(col) * m[..., None]


def age(img, rng, amount=1.0, chips=0.0, bleach=0.0):
    """Faded, grimy, sun-bleached toward the top; chipped paint showing the primer."""
    h, w = img.shape[:2]
    n = vnoise(h, w, rng, 5, 6)
    img = img * (0.82 + 0.3 * amount * n[..., None])
    if bleach:
        g = img.mean(axis=2, keepdims=True)
        f = (np.linspace(1, 0, h)[:, None, None] * bleach)
        img = img * (1 - f) + (g * 0.9 + 0.12) * f
    if chips:
        c = (vnoise(h, w, rng, 3, 24) > 1 - chips).astype(np.float32)
        img = img * (1 - c[..., None] * 0.7) + np.array([0.55, 0.52, 0.46]) * c[..., None] * 0.7
    return np.clip(img, 0, 1)


SIGN_STYLE = [((0.36, 0.10, 0.12), (0.93, 0.86, 0.70)), ((0.10, 0.16, 0.36), (0.92, 0.92, 0.90)), ((0.12, 0.30, 0.18), (0.98, 0.84, 0.32)),
              ((0.86, 0.84, 0.78), (0.62, 0.10, 0.08)), ((0.10, 0.36, 0.36), (0.95, 0.90, 0.78)), ((0.06, 0.06, 0.07), (0.98, 0.58, 0.18)),
              ((0.40, 0.46, 0.52), (0.96, 0.96, 0.96)), ((0.62, 0.14, 0.10), (0.99, 0.86, 0.22))]     # entrance's eight board colours
SIGN_W, SIGN_R, SIGN_ROWS = 1024, 128, 16          # the sign atlas: 16 rows of 1024 x 128 (8:1, a 4.4 x 0.6 m board)
SIGN_KEYS = []                                     # row -> key, filled by signs_pixels


def sign_list():
    """(key, text, style) for every painted sign in the scene, one row each."""
    out = []
    for i, (side, k, bx, name) in enumerate(shop_bays()):
        out.append((("bay", side, bx), name, i))
    for d in DOORS:
        out.append((("door", d["did"]), TH["door_sign"].get(d["did"], ""), 3 if d["did"] == "service_corridor" else 6))
    out.append((("wing",), TH["label"], 5))
    for k, t in enumerate(TH["hanging"]):
        out.append((("hanging", k), t, 1))
    if SCENE == "wing_books":
        out.append((("hoarding",), "CLOSED FOR RENOVATION", 3))
        out.append((("site",), "SITE ENTRANCE - HARD HATS", 7))
    if SCENE == "wing_cinema":
        out.append((("marquee",), "NOW SHOWING", 5))
        out.append((("marquee2",), "SCREENS 1 - 5", 5))
        out.append((("kiosk",), "TICKETS", 7))
    if SCENE == "wing_entertainment":
        out.append((("foodcourt",), "FOOD COURT", 2))
    assert len(out) <= SIGN_ROWS, len(out)
    return out


def signs_pixels():
    """Every painted sign of the scene, one per row of a 1024 x 2048 atlas: a faded board colour, the name in hand-painted capitals, sun-bleaching
    toward the top, grime and chipped paint (entrance's recipe). An unmarked door's board is blank, its old letters a ghost under new paint.
    The arcade's and the soft play's boards are their own: bulbs round ARCADE, and SOFT PLAY in bright colours letter by letter."""
    W_, R = SIGN_W, SIGN_R
    rng = np.random.default_rng(17 + len(SCENE))
    img = np.zeros((R * SIGN_ROWS, W_, 3), np.float32)
    img[:] = (0.5, 0.5, 0.5)
    SIGN_KEYS.clear()
    for i, (key, text, st) in enumerate(sign_list()):
        SIGN_KEYS.append(key)
        bg, fg = SIGN_STYLE[st % len(SIGN_STYLE)]
        row = np.zeros((R, W_, 3), np.float32)
        row[:] = bg
        if text == "ARCADE":
            row[:] = (0.04, 0.03, 0.10)
            m = text_mask(text, R, W_, rng, fill=0.62, maxw=0.7, painted=False)
            glow = np.clip(blur(m, 4, 2) * 1.6, 0, 1)
            row = row * (1 - glow[..., None] * 0.6) + np.array([0.9, 0.2, 0.7]) * glow[..., None] * 0.6
            row = row * (1 - m[..., None]) + np.array([1.0, 0.85, 0.3]) * m[..., None]
        elif text == "SOFT PLAY":
            row[:] = (0.98, 0.92, 0.55)
            cols = [(0.90, 0.15, 0.15), (0.10, 0.45, 0.85), (0.15, 0.65, 0.25), (0.95, 0.50, 0.05)]
            full = text_mask(text, R, W_, rng, fill=0.66, maxw=0.86, painted=True)
            xs = np.nonzero(full.max(axis=0) > 0.5)[0]
            if len(xs):
                x0, x1 = xs.min(), xs.max()
                band = ((np.arange(W_) - x0) / max(1, (x1 - x0)) * len(text)).astype(int)
                for j in range(len(text)):
                    sel = (band == j)[None, :] * full
                    row = row * (1 - sel[..., None]) + np.array(cols[j % 4]) * sel[..., None]
        elif text:
            m = text_mask(text, R, W_, rng, fill=0.62 if len(text) < 16 else 0.5)
            row = row * (1 - m[..., None]) + np.array(fg) * m[..., None]
        else:                                                                     # painted out: a ghost of the old name under the new coat
            ghost = text_mask("SHOP TO LET", R, W_, rng)
            row = row * (1 - 0.10 * ghost[..., None])
        n = vnoise(R, W_, rng, 5, 6)
        fade = np.linspace(1.12, 0.92, R)[:, None, None]
        row = row * (0.78 + 0.35 * n[..., None]) * fade
        chips = (vnoise(R, W_, rng, 3, 24) > 0.76).astype(np.float32)
        row = row * (1 - chips[..., None] * 0.6) + np.array([0.55, 0.52, 0.46]) * chips[..., None] * 0.6
        row[:3] = row[-3:] = row[:, :3] = row[:, -3:] = np.array(bg) * 0.5
        img[i * R:(i + 1) * R] = row
    return np.clip(img, 0, 1)


def sign_uv(key):
    r = SIGN_KEYS.index(key)
    return (0.0, 1 - (r + 1) / SIGN_ROWS, 1.0, 1 - r / SIGN_ROWS)


# the poster atlas, 2048 x 2048: eight 512 x 768 cells (two rows of four), then four 512 x 512 squares
PW = 2048


def cell_px(i):
    if i < 8:
        return (i % 4) * 512, (i // 4) * 768, 512, 768
    j = i - 8
    return j * 512, 1536, 512, 512


def cell_uv(i, sub=(0, 0, 1, 1)):
    x, y, w, h = cell_px(i)
    s0, t0, s1, t1 = sub
    return ((x + w * s0) / PW, 1 - (y + h * t1) / PW, (x + w * s1) / PW, 1 - (y + h * t0) / PW)


def poster_movie(h, w, rng, title, tagline, c0, c1, motif):
    """An invented film's poster: a two-tone sky, a big disc, a silhouette across the foot, the title in the pixel font, a tagline, faded and creased."""
    yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
    img = np.array(c0) * (1 - yy[..., None]) + np.array(c1) * yy[..., None]
    cx, cy, r = rng.uniform(0.3, 0.7), rng.uniform(0.3, 0.42), rng.uniform(0.08, 0.15)
    d = np.sqrt(((xx - cx) * w / h) ** 2 + (yy - cy) ** 2)
    disc_ = np.clip((r - d) * 60, 0, 1)
    img = img * (1 - disc_[..., None] * 0.85) + np.array([1.0, 0.92, 0.75]) * disc_[..., None] * 0.85
    ridge = 0.72 + 0.1 * (rs(rng.random((1, 9)), 1, w)[0] - 0.5) + 0.04 * (rs(rng.random((1, 33)), 1, w)[0] - 0.5)
    if motif == "city":
        bars = np.repeat(rng.uniform(0.55, 0.75, w // 16 + 1), 16)[:w]
        ridge = np.minimum(ridge, bars)
    elif motif == "hall":
        ridge = 0.6 + 0.25 * np.abs(np.linspace(-1, 1, w))
    sil = (yy > ridge[None, :]).astype(np.float32)
    img = img * (1 - sil[..., None]) + np.array([0.03, 0.03, 0.05]) * sil[..., None]
    if motif == "figure":
        f = (np.abs(xx - 0.5) < 0.035) & (yy > 0.55) & (yy < 0.8) | (np.sqrt(((xx - 0.5) * w / h) ** 2 + (yy - 0.53) ** 2) < 0.03)
        img[f] = (0.02, 0.02, 0.03)
    words = title.split(" ")
    lines = [" ".join(words[:len(words) // 2 + len(words) % 2]), " ".join(words[len(words) // 2 + len(words) % 2:])] if len(title) > 10 else [title]
    for k, ln in enumerate(lines):
        if ln:
            put_text(img, ln, int(h * (0.05 + 0.1 * k)), int(h * (0.15 + 0.1 * k)), 20, w - 20, (0.98, 0.95, 0.85), rng, fill=0.8, maxw=0.92)
    put_text(img, tagline, int(h * 0.86), int(h * 0.92), 30, w - 30, (0.9, 0.88, 0.8), rng, fill=0.7, maxw=0.85)
    put_text(img, "COMING SOON", int(h * 0.93), int(h * 0.975), 80, w - 80, (0.95, 0.75, 0.25), rng, fill=0.8, maxw=0.8)
    img[:6] = img[-6:] = img[:, :6] = img[:, -6:] = (0.92, 0.9, 0.85)
    crease = (np.abs(xx - 0.5) < 0.002) | (np.abs(yy - 0.5) < 0.0015)
    img[crease] *= 0.8
    return age(img, rng, 1.0, 0.0, bleach=0.35)


def notice(h, w, rng, title, lines, paper=(0.92, 0.90, 0.84), ink=(0.55, 0.08, 0.06)):
    """A printed notice taped up: a red title, lines of text, tape at the corners, curled and yellowed."""
    img = np.ones((h, w, 3), np.float32) * np.array(paper)
    put_text(img, title, int(h * 0.06), int(h * 0.2), 20, w - 20, ink, rng, fill=0.7, maxw=0.9)
    img[int(h * 0.22):int(h * 0.225), 30:w - 30] = ink
    y = int(h * 0.28)
    lh = int(h * 0.075)
    for ln in lines:
        put_text(img, ln, y, y + lh, 30, w - 30, (0.15, 0.14, 0.13), rng, fill=0.7, maxw=0.88)
        y += lh
    while y < h * 0.9:                                                      # small print: grey bars
        ww = int(rng.uniform(0.5, 0.85) * (w - 60))
        img[y + lh // 3:y + lh // 3 + 4, 30:30 + ww] = (0.45, 0.44, 0.42)
        y += lh // 2
    for (ty, tx) in ((0, 0), (0, w - 60), (h - 30, 0), (h - 30, w - 60)):
        img[ty:ty + 30, tx:tx + 60] = img[ty:ty + 30, tx:tx + 60] * 0.6 + np.array([0.85, 0.8, 0.6]) * 0.4
    return age(img, rng, 0.8)


def pictogram(h, w, kind):
    """A restroom sign: a white figure on blue (own drawing)."""
    img = np.ones((h, w, 3), np.float32) * np.array([0.10, 0.25, 0.55])
    yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
    head = np.sqrt((xx - 0.5) ** 2 + (yy - 0.2) ** 2) < 0.09
    if kind == "man":
        body = (np.abs(xx - 0.5) < 0.15) & (yy > 0.32) & (yy < 0.62)
        legs = ((np.abs(xx - 0.43) < 0.055) | (np.abs(xx - 0.57) < 0.055)) & (yy >= 0.62) & (yy < 0.9)
        arms = ((np.abs(xx - 0.29) < 0.04) | (np.abs(xx - 0.71) < 0.04)) & (yy > 0.34) & (yy < 0.6)
        fig = head | body | legs | arms
    else:
        dress = (yy > 0.32) & (yy < 0.7) & (np.abs(xx - 0.5) < 0.08 + (yy - 0.32) * 0.5)
        legs = ((np.abs(xx - 0.44) < 0.045) | (np.abs(xx - 0.56) < 0.045)) & (yy >= 0.7) & (yy < 0.9)
        arms = ((np.abs(xx - 0.27) < 0.04) | (np.abs(xx - 0.73) < 0.04)) & (yy > 0.34) & (yy < 0.58)
        fig = head | dress | legs | arms
    img[fig] = (0.96, 0.96, 0.96)
    img[:8] = img[-8:] = img[:, :8] = img[:, -8:] = (0.85, 0.85, 0.85)
    return img


def book_display(h, w, rng):
    """A bookshop window seen through dusty glass: shelves of book spines on a dark back panel, a few faced out, a NEW TITLES card."""
    img = np.ones((h, w, 3), np.float32) * np.array([0.14, 0.09, 0.06])
    shelves = np.linspace(0.08, 0.95, 6)
    for k in range(len(shelves) - 1):
        y0, y1 = int(h * shelves[k]), int(h * shelves[k + 1])
        img[y1 - 10:y1] = (0.32, 0.22, 0.14)
        x = 8
        while x < w - 8:
            if rng.random() < 0.12:                                          # a book faced out
                bw = int(rng.uniform(70, 110))
                bh = int((y1 - y0 - 14) * rng.uniform(0.7, 0.9))
                col = np.array(rng.choice([[0.75, 0.2, 0.15], [0.2, 0.35, 0.6], [0.85, 0.75, 0.3], [0.2, 0.5, 0.35], [0.9, 0.9, 0.85]]))
                img[y1 - 10 - bh:y1 - 10, x:min(w, x + bw)] = col
                img[y1 - 10 - int(bh * 0.7):y1 - 10 - int(bh * 0.6), x + 8:min(w, x + bw - 8)] = col * 0.4 + 0.5
                x += bw + 4
                continue
            bw = int(rng.uniform(8, 22))
            bh = int((y1 - y0 - 14) * rng.uniform(0.6, 0.95))
            col = np.array(rng.choice([[0.55, 0.12, 0.1], [0.12, 0.2, 0.4], [0.2, 0.35, 0.22], [0.7, 0.6, 0.35], [0.82, 0.78, 0.7], [0.15, 0.12, 0.1],
                                       [0.6, 0.3, 0.15], [0.35, 0.15, 0.35]])) * rng.uniform(0.75, 1.1)
            img[y1 - 10 - bh:y1 - 10, x:min(w, x + bw)] = col
            img[y1 - 10 - int(bh * 0.85):y1 - 10 - int(bh * 0.82), x:min(w, x + bw)] = col * 0.5 + 0.35
            x += bw + int(rng.uniform(0, 3))
        if k == 2:
            cx = int(w * 0.55)
            img[y1 - 90:y1 - 12, cx:cx + 170] = (0.95, 0.92, 0.82)
            put_text(img, "NEW", y1 - 86, y1 - 52, cx + 5, cx + 165, (0.6, 0.08, 0.06), rng, fill=0.8)
            put_text(img, "TITLES", y1 - 50, y1 - 16, cx + 5, cx + 165, (0.6, 0.08, 0.06), rng, fill=0.8)
    dust = np.clip(vnoise(h, w, rng, 6, 4) * 0.9 - 0.15 + np.linspace(-0.1, 0.25, h)[:, None], 0, 0.75)
    img = img * (1 - dust[..., None]) + np.array([0.78, 0.76, 0.70]) * dust[..., None]
    return np.clip(img, 0, 1)


def arcade_mural(h, w, rng):
    """The arcade's shutter, painted: a night-blue field, a magenta grid floor, stars, rows of pixel invaders, PLAY and a high score."""
    img = np.ones((h, w, 3), np.float32) * np.array([0.05, 0.05, 0.16])
    yy, xx = np.mgrid[0:h, 0:w]
    stars = rng.random((h, w)) > 0.997
    img[stars] = (0.9, 0.9, 1.0)
    hz = int(h * 0.62)
    for k in range(12):                                                     # the grid floor
        y = int(hz + (h - hz) * (k / 12) ** 1.8)
        img[y:y + 3] = (0.85, 0.2, 0.7)
    for k in range(-10, 11):
        x_top, x_bot = w / 2 + k * w * 0.04, w / 2 + k * w * 0.18
        t = (yy[hz:] - hz) / max(1, h - hz)
        line = np.abs(xx[hz:] - (x_top + (x_bot - x_top) * t)) < 1.5
        img[hz:][line] = (0.85, 0.2, 0.7)
    inv = ["00100000100", "00010001000", "00111111100", "01101110110", "11111111111", "10111111101", "10100000101", "00011011000"]
    s = 7
    for r in range(3):
        for c in range(7):
            x0, y0 = int(w * 0.12 + c * w * 0.11), int(h * 0.12 + r * h * 0.12)
            col = [(0.3, 1.0, 0.4), (1.0, 0.9, 0.2), (0.3, 0.8, 1.0)][r]
            for i, rowp in enumerate(inv):
                for j, v in enumerate(rowp):
                    if v == "1":
                        img[y0 + i * s:y0 + (i + 1) * s, x0 + j * s:x0 + (j + 1) * s] = col
    put_text(img, "PLAY", int(h * 0.46), int(h * 0.62), int(w * 0.3), int(w * 0.7), (1.0, 0.85, 0.25), rng, fill=0.9, maxw=0.9, painted=True)
    put_text(img, "HIGH SCORE 099990", int(h * 0.03), int(h * 0.09), int(w * 0.25), int(w * 0.75), (0.95, 0.95, 0.95), rng, fill=0.8)
    return age(img, rng, 0.9, chips=0.06)


def directory_pixels():
    """The mall directory on the west wall (entrance's board): this wing's shops listed by number."""
    h, w = 768, 512
    rng = np.random.default_rng(19)
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (0.09, 0.11, 0.14)
    put_text(img, "DIRECTORY", 30, 120, 0, w, (0.95, 0.80, 0.35), rng, fill=0.5, maxw=0.8)
    img[128:132, 30:-30] = (0.95, 0.80, 0.35)
    names = [n for _, _, _, n in shop_bays()] + [t for t in TH["door_sign"].values() if t]
    rh = (h - 170) // max(1, len(names))
    for i, name in enumerate(names):
        put_text(img, f"{i + 1} {name}", 150 + i * rh, 150 + (i + 1) * rh, 0, w, (0.90, 0.90, 0.86), rng, fill=0.42, maxw=0.92)
    n = vnoise(h, w, rng, 5, 6)
    img = img * (0.8 + 0.3 * n[..., None])
    img[:6] = img[-6:] = img[:, :6] = img[:, -6:] = (0.35, 0.36, 0.38)
    return np.clip(img, 0, 1)


FILMS = [("THE LONG HALL", "SOME DOORS STAY SHUT", (0.10, 0.12, 0.30), (0.75, 0.35, 0.25), "hall"),
         ("NIGHT SHIFT", "THE MALL CLOSES AT EIGHT", (0.05, 0.05, 0.12), (0.35, 0.10, 0.25), "city"),
         ("PAINTED SKY", "IT WAS NEVER REAL", (0.35, 0.60, 0.90), (0.95, 0.80, 0.55), "figure"),
         ("RETURN TO FARWAY", "YOU NEVER LEFT", (0.20, 0.08, 0.10), (0.90, 0.50, 0.20), "city"),
         ("DEEP END", "THE POOL IS ALWAYS OPEN", (0.05, 0.25, 0.35), (0.15, 0.65, 0.70), "hall"),
         ("SUMMER 99", "THE LAST GOOD YEAR", (0.95, 0.55, 0.30), (0.95, 0.85, 0.45), "figure"),
         ("NO EXIT", "LOOK OVER THERE", (0.08, 0.08, 0.08), (0.55, 0.05, 0.05), "figure"),
         ("THE LAST SCREENING", "TONIGHT ONLY", (0.12, 0.10, 0.25), (0.60, 0.45, 0.75), "city")]


def posters_pixels():
    """The scene's poster atlas: films (cinema), the bookshop's window (books), the arcade's mural and posters (entertainment), notices for all."""
    rng = np.random.default_rng(61 + len(SCENE))
    img = np.zeros((PW, PW, 3), np.float32)
    img[:] = (0.5, 0.5, 0.5)

    def put(i, arr):
        x, y, w, h = cell_px(i)
        img[y:y + h, x:x + w] = rs(arr, h, w) if arr.shape[:2] != (h, w) else arr
    if SCENE == "wing_cinema":
        for i, f in enumerate(FILMS):
            put(i, poster_movie(768, 512, rng, *f))
        put(8, pictogram(512, 512, "man"))
        put(9, pictogram(512, 512, "woman"))
    elif SCENE == "wing_books":
        put(0, book_display(768, 512, rng))
        put(1, book_display(768, 512, rng))
        put(2, notice(768, 512, rng, "BACK TO SCHOOL", ["PENS PAPER", "PLANNERS", "ALL HALF PRICE"], paper=(0.95, 0.88, 0.45), ink=(0.1, 0.15, 0.45)))
        put(3, notice(768, 512, rng, "BOOK SIGNING", ["SATURDAY 2PM", "IN STORE", "ALL WELCOME"]))
        put(4, notice(768, 512, rng, "CLOSING DOWN", ["EVERYTHING", "MUST GO", "THANK YOU"], paper=(0.95, 0.95, 0.92), ink=(0.75, 0.05, 0.05)))
        put(5, notice(768, 512, rng, "NOW OPEN", ["LIBRARY CAFE", "COFFEE & CAKE", "FREE WIFI"], paper=(0.85, 0.92, 0.85), ink=(0.1, 0.35, 0.15)))
    else:
        put(0, notice(768, 512, rng, "BIRTHDAY PARTIES", ["SOFT PLAY", "AGES 2 TO 8", "BOOK NOW"], paper=(0.98, 0.85, 0.30), ink=(0.85, 0.1, 0.1)))
        put(1, notice(768, 512, rng, "BOWLING", ["LANES 1 TO 12", "SHOES FOR HIRE", "LATE NIGHTS"], paper=(0.15, 0.2, 0.45), ink=(0.95, 0.85, 0.3)))
        put(2, notice(768, 512, rng, "PRIZES", ["WIN TICKETS", "SWAP FOR TOYS", "AT THE COUNTER"], paper=(0.85, 0.3, 0.6), ink=(1.0, 0.95, 0.5)))
        put(3, notice(768, 512, rng, "SORRY", ["SOFT PLAY", "CLOSED FOR", "CLEANING"]))
        m = arcade_mural(512, 1024, rng)                                    # cells 8 and 9 together: the shutter's mural
        img[1536:2048, 0:1024] = m
    put(10, notice(512, 512, rng, "PARDON OUR DUST", ["THIS WING IS BEING", "REFURBISHED", "SEE YOU SOON"]))
    put(11, notice(512, 512, rng, "STAFF ONLY", ["NO ENTRY", "BEYOND THIS", "POINT"], paper=(0.95, 0.92, 0.3), ink=(0.1, 0.1, 0.1)))
    if SCENE == "wing_books":
        put(6, notice(768, 512, rng, "HARD HATS", ["MUST BE WORN", "ON THIS SITE"], paper=(0.20, 0.45, 0.80), ink=(0.98, 0.98, 0.98)))
    put(7, directory_pixels())                                              # (the cinema's eighth film gives way to the directory)
    return np.clip(img, 0, 1)


DOOR_CELLS = {"glass": 0, "staff": 1, "restroom": 2, "unmarked": 3, "site": 4}


def doors_pixels():
    """The door leaves' atlas (2048 x 1024, five cells of 400 x 1024): a glass mall door (aluminium frame, whitewashed glass, push plate), a staff
    door (painted steel, STAFF ONLY plate), a restroom door (cream, a blue pictogram plate), an unmarked door (dull paint, scuffs), a site door
    (plywood, a stencilled SITE)."""
    H_, W_ = 1024, 2048
    rng = np.random.default_rng(71)
    img = np.zeros((H_, W_, 3), np.float32)
    cw = 400
    yy, xx = np.mgrid[0:H_, 0:cw] / np.array([H_, cw])[:, None, None]
    for kind, i in DOOR_CELLS.items():
        c = np.zeros((H_, cw, 3), np.float32)
        if kind == "glass":
            c[:] = (0.62, 0.63, 0.64)
            g = (xx > 0.1) & (xx < 0.9) & (yy > 0.06) & (yy < 0.9)
            ww = 0.72 + 0.2 * vnoise(H_, cw, rng, 5, 4)
            c[g] = (np.array([0.88, 0.87, 0.83]) * ww[..., None])[g]
            plate = (xx > 0.15) & (xx < 0.85) & (np.abs(yy - 0.58) < 0.012)
            c[plate] = (0.8, 0.8, 0.8)
        elif kind == "staff":
            c[:] = (0.38, 0.45, 0.42)
            pl = (np.abs(xx - 0.5) < 0.3) & (np.abs(yy - 0.32) < 0.035)
            c[pl] = (0.92, 0.9, 0.85)
            y0, y1 = int(H_ * 0.29), int(H_ * 0.35)
            put_text(c, "STAFF ONLY", y0, y1, int(cw * 0.22), int(cw * 0.78), (0.1, 0.1, 0.1), rng, fill=0.75)
        elif kind == "restroom":
            c[:] = (0.86, 0.82, 0.72)
            pl = (np.abs(xx - 0.5) < 0.16) & (np.abs(yy - 0.33) < 0.07)
            c[pl] = (0.10, 0.25, 0.55)
        elif kind == "unmarked":
            c[:] = (0.62, 0.58, 0.50)
        else:
            n = vnoise(H_, cw, rng, 5, 3)
            grain = 0.5 + 0.5 * np.sin(xx * 90 + n * 8)
            c[:] = np.array([0.74, 0.58, 0.40])[None, None] * (0.85 + 0.15 * grain[..., None])
            put_text(c, "SITE", int(H_ * 0.3), int(H_ * 0.38), 20, cw - 20, (0.75, 0.12, 0.08), rng, fill=0.8, painted=True)
            put_text(c, "KEEP CLOSED", int(H_ * 0.4), int(H_ * 0.44), 30, cw - 30, (0.1, 0.1, 0.1), rng, fill=0.8)
        if kind != "glass":
            kick = yy > 0.93
            c[kick] = c[kick] * 0.6 + 0.15
            scuff = vnoise(H_, cw, rng, 4, 8) > 0.7
            c[scuff & (yy > 0.75)] *= 0.8
        c[:, :6] = c[:, -6:] = c[:6] = c[-6:] = c[:, :6].mean(axis=(0, 1)) * 0.6
        img[:, i * cw:(i + 1) * cw] = age(c, rng, 0.6)
    return np.clip(img, 0, 1)


def door_uv(kind):
    i = DOOR_CELLS[kind]
    return (i * 400 / 2048, 0.0, ((i + 1) * 400 - 1) / 2048, 1.0)


def exit_pixels():
    h, w = 96, 256
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (0.02, 0.45, 0.16)
    m = text_mask("EXIT", h, w, np.random.default_rng(1), fill=0.66, maxw=0.8, painted=False)
    img = img * (1 - m[..., None]) + np.array([0.95, 1.0, 0.95]) * m[..., None]
    img[:4] = img[-4:] = img[:, :4] = img[:, -4:] = (0.01, 0.2, 0.07)
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def whitewash_pixels():
    S = 512
    rng = np.random.default_rng(29)
    yy, xx = np.mgrid[0:S, 0:S] / S
    streak = 0.5 + 0.5 * np.sin((xx * 3.0 + yy * 1.4 + 0.15 * np.sin(yy * 17)) * 2 * math.pi * 6)
    n = vnoise(S, S, rng, 6, 6)
    cover = np.clip(0.72 + 0.22 * streak * n + (n - 0.5) * 0.4, 0, 1)
    img = np.array([0.55, 0.60, 0.60]) * (1 - cover[..., None]) + np.array([0.90, 0.89, 0.84]) * cover[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def skyglass_pixels():
    S = 512
    rng = np.random.default_rng(37)
    yy, xx = np.mgrid[0:S, 0:S]
    wire = ((xx % 32) < 2) | ((yy % 32) < 2)
    img = np.ones((S, S, 3), np.float32) * np.array([0.82, 0.88, 0.90])
    img[wire] *= 0.6
    n = vnoise(S, S, rng, 6, 4)
    streak = rs(blur(rng.random((S, S)).astype(np.float32), 1, 1)[:, ::16], S, S)
    grime = np.clip((n - 0.35) * 1.2 + (streak - 0.5) * 0.4, 0, 1)
    img = img * (1 - 0.45 * grime[..., None]) + np.array([0.35, 0.33, 0.28]) * 0.45 * grime[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def dust_pixels():
    """Dust drifted against a wall's foot: dense at the wall (v = 1), thinning out into the room (v = 0), patchy; it tiles along u."""
    h, w = 128, 512
    rng = np.random.default_rng(43)
    n = rs(np.tile(rng.random((9, 9)), (1, 2))[:, :17], h, w)
    n2 = vnoise(h, w, rng, 4, 8)
    v = np.linspace(0, 1, h)[::-1][:, None]                                 # row 0 (top of the picture) is v = 1: the wall
    a = np.clip(0.5 * v ** 2.2 + (n - 0.5) * 0.25 * v + (n2 - 0.5) * 0.15, 0, 0.5)
    rgba = np.zeros((h, w, 4), np.float32)
    rgba[..., :3] = np.array([0.52, 0.47, 0.40]) * (0.85 + 0.3 * n2[..., None])
    rgba[..., 3] = a
    return rgba


def stain_pixels():
    S = 512
    rng = np.random.default_rng(3)
    yy, xx = (np.mgrid[0:S, 0:S] - S / 2) / (S / 2)
    r = np.sqrt(xx ** 2 + (yy * 1.2) ** 2) + (vnoise(S, S, rng, 5, 4) - 0.5) * 0.8
    inside = np.clip((0.75 - r) * 6, 0, 1)
    edge = np.clip(1 - np.abs(r - 0.75) * 14, 0, 1)
    rgba = np.zeros((S, S, 4), np.float32)
    rgba[..., :3] = np.array([0.30, 0.27, 0.22])
    rgba[..., 3] = np.clip(inside * 0.16 + edge * 0.32, 0, 0.4)
    return rgba


def tile_pixels():
    """Restroom wall tiles: 8 x 8 glazed white squares a picture (10 cm each at 0.8 m), grey grout, a little uneven, the odd dirty or cracked one."""
    S = 512
    rng = np.random.default_rng(53)
    n = 8
    t = S // n
    img = np.ones((S, S, 3), np.float32)
    for i in range(n):
        for j in range(n):
            v = rng.uniform(0.88, 0.97)
            img[i * t:(i + 1) * t, j * t:(j + 1) * t] = (v, v, v * 0.98)
    yy, xx = np.mgrid[0:S, 0:S]
    grout = ((yy % t) < 3) | ((xx % t) < 3)
    img[grout] = (0.55, 0.54, 0.50)
    dirt = vnoise(S, S, rng, 5, 4)
    img = img * (0.92 + 0.1 * dirt[..., None])
    c = rng.integers(0, n, 2)
    yc = c[0] * t + np.arange(t)
    img[yc, np.clip(c[1] * t + (np.arange(t) * 0.7).astype(int), 0, S - 1)] = (0.4, 0.4, 0.38)
    return np.clip(img, 0, 1)


def padding_pixels():
    """Soft-play padding: square vinyl cushions in red, yellow, blue and green with stitched seams and a soft shine (it tiles)."""
    S = 512
    rng = np.random.default_rng(59)
    n = 2
    t = S // n
    cols = [(0.85, 0.12, 0.10), (0.98, 0.78, 0.10), (0.10, 0.38, 0.80), (0.12, 0.62, 0.25)]
    img = np.zeros((S, S, 3), np.float32)
    yy, xx = np.mgrid[0:t, 0:t] / t
    pillow = 1 - 0.25 * ((xx - 0.5) ** 2 + (yy - 0.5) ** 2) * 4
    shine = np.clip(1 - np.sqrt((xx - 0.35) ** 2 + (yy - 0.3) ** 2) * 3, 0, 1) * 0.25
    for i in range(n):
        for j in range(n):
            c = np.array(cols[(i * n + j + i) % 4])
            img[i * t:(i + 1) * t, j * t:(j + 1) * t] = c * pillow[..., None] + shine[..., None]
    seam = (np.mgrid[0:S, 0:S][0] % t < 6) | (np.mgrid[0:S, 0:S][1] % t < 6)
    img[seam] *= 0.45
    stitch = ((np.mgrid[0:S, 0:S][0] % t == 14) | (np.mgrid[0:S, 0:S][1] % t == 14)) & ((np.mgrid[0:S, 0:S].sum(axis=0) // 8) % 2 == 0)
    img[stitch] = img[stitch] * 0.5 + 0.4
    return age(img, rng, 0.6)


def stage_work():
    d = Path(arg("--work", str(Path(os.environ.get("TEMP", "/tmp")) / f"farway_{SCENE}")))
    if not d.is_absolute():
        d = ROOT / d
    d.mkdir(parents=True, exist_ok=True)
    return d


def mk_image(name, arr, srgb=True):
    """A packed image from a float array (rows top to bottom), written as a PNG first (entrance's)."""
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
    for ref in [out] + list(out.packed_files):
        attr = "filepath_raw" if ref is out else "filepath"
        setattr(ref, attr, "_" * 1000)
        setattr(ref, attr, f"//generated/{name}.png")
    return out


def make_generated():
    tag = SCENE.split("_")[1].capitalize()
    g = {"signs": mk_image(f"{tag}_Signs", signs_pixels()), "posters": mk_image(f"{tag}_Posters", posters_pixels()),
         "doors": mk_image("Mall_Door_Leaves", doors_pixels()), "exit": mk_image("Exit_Sign", exit_pixels()),
         "whitewash": mk_image("Glass_Whitewash", whitewash_pixels()), "skyglass": mk_image("Wired_Glass", skyglass_pixels()),
         "dust": mk_image("Wall_Dust", dust_pixels()), "stain": mk_image("Floor_Puddle", stain_pixels())}
    if SCENE == "wing_cinema":
        g["tiles"] = mk_image("Restroom_Tiles", tile_pixels())
    if SCENE == "wing_entertainment":
        g["padding"] = mk_image("SoftPlay_Padding", padding_pixels())
    return g


# ---------------------------------------------------------------- the shell: the floor, the walls (one piece per greybox wall box), the ceiling
SHELL_BOXES = [b for b in LOC.boxes if b["name"].startswith("Wing_")]


def build_floor():
    """Terrazzo in a dark border along the walls, with a dark band across the hall at each pair of pilasters (entrance's floor)."""
    f = BOXL["Wing_Floor"]
    mn, mx = f["min"], f["max"]
    b = 0.6
    bands = [(p - 0.15, p + 0.15, -WZ + b, WZ - b) for p in PILASTERS]
    part("Floor_Field", "Floor_Terrazzo", lambda bm: holed_box_xz(bm, (-WX + b, WX - b), (-WZ + b, WZ - b), mn[1], mx[1], bands))

    def border(bm):
        cube(bm, (mn[0], mn[1], mn[2]), (mx[0], mx[1], -WZ + b))
        cube(bm, (mn[0], mn[1], WZ - b), (mx[0], mx[1], mx[2]))
        cube(bm, (mn[0], mn[1], -WZ + b), (-WX + b, mx[1], WZ - b))
        cube(bm, (WX - b, mn[1], -WZ + b), (mx[0], mx[1], WZ - b))
        for x0, x1, z0, z1 in bands:
            cube(bm, (x0, mn[1], z0), (x1, mx[1], z1))
    part("Floor_Band", "Floor_Border", border)


def build_walls():
    """Each greybox wall box gets its own piece of art (so a door's opening is open in the art as in the colliders): plaster up to BAND, the darker
    upper plaster above it (entrance's two shades)."""
    for b in LOC.boxes:
        n = b["name"]
        if not n.startswith("Wing_Wall_"):
            continue
        mn, mx = b["min"], b["max"]
        along = 0 if mx[0] - mn[0] > mx[2] - mn[2] else 2
        if mn[1] < BAND - 1e-6:
            part(n.replace("Wing_", ""), "Wall_Plaster", lambda bm: grid_box(bm, mn, (mx[0], min(mx[1], BAND), mx[2]), along))
        if mx[1] > BAND + 1e-6:
            part(n.replace("Wing_", "") + "_Upper", "Wall_Upper", lambda bm: cube(bm, (mn[0], max(mn[1], BAND), mn[2]), mx))


WALL_CUTS = sorted({c for bx in BAYS for c in (bx - 2.6, bx + 2.6)} | {c for p in PILASTERS for c in (p - 0.2, p + 0.2)})


def grid_box(bm, mn, mx, along):
    """A wall piece cut where the bays and the pilasters begin and end and at the fascia's top, so the faces hidden behind them can be dropped
    (cull: `covered`) and the wall's own light is measured on what shows."""
    a0, a1 = mn[along], mx[along]
    cuts = ([a0] + [c for c in WALL_CUTS if a0 + 1e-6 < c < a1 - 1e-6] + [a1]) if along == 0 else [a0, a1]
    ys = [mn[1]] + [y for y in (FASCIA_TOP,) if mn[1] + 1e-6 < y < mx[1] - 1e-6] + [mx[1]]
    for u0, u1 in zip(cuts, cuts[1:]):
        for y0, y1 in zip(ys, ys[1:]):
            if along == 0:
                cube(bm, (u0, y0, mn[2]), (u1, y1, mx[2]))
            else:
                cube(bm, (mn[0], y0, u0), (mx[0], y1, u1))
    bm.verts.index_update()
    dedupe_inner(bm)


def covered(gx, gy, gz):
    """Is this point of a long wall's face hidden behind a bay's front and fascia or a pilaster?"""
    if abs(abs(gz) - WZ) > 0.01 or gy > FASCIA_TOP + 1e-3:
        return False
    return any(abs(gx - bx) < 2.6 - 1e-3 for bx in BAYS) or any(abs(gx - p) < 0.2 - 1e-3 for p in PILASTERS)


def build_ceiling():
    c = BOXL["Wing_Ceiling"]
    mn, mx = c["min"], c["max"]
    part("Ceiling_Slab", "Ceiling_Paint", lambda bm: holed_box_xz(bm, (mn[0], mx[0]), (mn[2], mx[2]), mn[1], mx[1], [(-SKX, SKX, -SKZ, SKZ)]))


def free_spans(side, lo=-WX, hi=WX, gap=0.25):
    """The stretches of a long wall not taken by a bay (its front and frame) or a pilaster: [(a0, a1)]."""
    taken = sorted([(bx - 2.6, bx + 2.6) for bx in BAYS] + [(p - gap, p + gap) for p in PILASTERS])
    out, a = [], lo
    for t0, t1 in taken:
        if t0 > a + 0.3:
            out.append((a, min(t0, hi)))
        a = max(a, t1)
    if hi > a + 0.3:
        out.append((a, hi))
    return out


def build_wall_trim():
    """The band at BAND (a painted cornice line), terrazzo skirting along the free wall stretches, and the pilasters on their colliders (a plinth,
    a capital at the fascia line)."""
    def band(bm):
        for n in ("+z", "-z"):
            wall_box(bm, n, -WX, WX, BAND - 0.07, BAND + 0.07, 0.0, 0.045)
        for n in ("+x", "-x"):
            wall_box(bm, n, -WZ, WZ, BAND - 0.07, BAND + 0.07, 0.0, 0.045)
    part("Trim_Band", "Trim_Paint", band)

    for side in ("N", "S"):                                                    # one piece a stretch
        for k, (a0, a1) in enumerate(free_spans(side)):
            part(f"Skirting_{side}{k}", "Floor_Border", lambda bm: wall_box(bm, SIDE[side], a0, a1, 0.0, 0.12, 0.0, 0.015))
    for b in LOC.boxes:
        if not b["name"].startswith("Pilaster"):
            continue
        mn, mx = b["min"], b["max"]
        part(b["name"], "Trim_Paint", lambda bm: cube(bm, mn, mx))
        into = 1 if mn[2] < 0 else -1                                        # the pilaster's room face is at mx z (north wall) or mn z (south)
        face = mx[2] if into > 0 else mn[2]
        part(b["name"] + "_Plinth", "Floor_Border", lambda bm: cube(bm, (mn[0] - 0.03, 0.0, mn[2] if into > 0 else face - 0.03),
                                                                      (mx[0] + 0.03, 0.18, face + 0.03 if into > 0 else mx[2])))
        part(b["name"] + "_Capital", "Trim_Paint", lambda bm: cube(bm, (mn[0] - 0.04, FASCIA_TOP - 0.12, mn[2] if into > 0 else face - 0.04),
                                                                     (mx[0] + 0.04, FASCIA_TOP + 0.08, face + 0.04 if into > 0 else mx[2])))


def build_decals():
    """Dust drifted along the foot of the long walls, and dried puddles under the skylight where the rain came in (alpha decals on the floor)."""
    def strip(bm, side):
        z = ZC[side]
        zi = z + (1.1 if side == "N" else -1.1)
        xs = np.linspace(-WX + 0.05, WX - 0.05, 11)                          # in 4 m lengths (one 40 m quad unwraps badly for the lightmap)
        for k, (xa, xb) in enumerate(zip(xs, xs[1:])):
            ua, ub = (xa + WX) / 4, (xb + WX) / 4
            y = 0.003 + 0.0003 * (k % 2)                                      # alternate heights: the export's weld keeps the lengths apart
            if side == "N":
                flat_decal(bm, xa, xb, z, zi, y, uv=(ua, 0, ub, 1))
            else:
                flat_decal(bm, xa, xb, zi, z, y, uv=(ua, 1, ub, 0))
    for side in ("N", "S"):
        part(f"Decal_Dust_{side}", "Decal_Dust", lambda bm: strip(bm, side), keep_uv=True, keep_normals=True)
    rng = np.random.default_rng(13)
    spots = [(-9.5, -0.8, 1.8, 1.3), (6.5, 0.9, 2.4, 1.6), (14.0, -0.5, 1.4, 1.1)]
    for k, (x, z, a, b) in enumerate(spots):
        part(f"Decal_Puddle_{k}", "Decal_Stain", lambda bm: flat_decal(bm, x - a, x + a, z - b, z + b, 0.004 + 0.0005 * k), keep_uv=True, keep_normals=True)


# ---------------------------------------------------------------- the skylight strip: the opening in the ceiling and a glazed lantern over it
SKY_BOARDS = []


def build_skylight():
    y0 = WH + 0.2
    y1 = y0 + LANTERN_UP
    yr = y1 + LANTERN_RIDGE
    x0, x1, z0, z1 = -SKX, SKX, -SKZ, SKZ
    zc = 0.0
    nb = 18                                                                    # 2 m bays along the strip
    xs = np.linspace(x0, x1, nb + 1)

    def frames(bm):
        t = 0.05
        for xa, xb, za, zb in ((x0, x1, z0, z0 + t), (x0, x1, z1 - t, z1), (x0, x0 + t, z0, z1), (x1 - t, x1, z0, z1)):
            cube(bm, (xa, WH, za), (xb, y0 + 0.1, zb))
        for x in xs:
            for z in (z0, z1):
                cyl(bm, (x, y0, z), (x, y1, z), 0.04, 0.04, 6, cap=False)
            cyl(bm, (x, y1, z0), (x, yr, zc), 0.04, 0.04, 6, cap=False)
            cyl(bm, (x, y1, z1), (x, yr, zc), 0.04, 0.04, 6, cap=False)
        cyl(bm, (x0, yr, zc), (x1, yr, zc), 0.07, 0.07, 8, cap=False)
        for zz in (z0, z1):
            cyl(bm, (x0, y1, zz), (x1, y1, zz), 0.06, 0.06, 8, cap=False)
        for x in xs[::3]:                                                       # tie bars across the opening, at the ceiling
            cyl(bm, (x, WH + 0.1, z0), (x, WH + 0.1, z1), 0.03, 0.03, 6, cap=False)
    part("Skylight_Frame", "Metal_Dark", frames)

    def panes(bm):
        quad(bm, (x0, y1, z0), (x1, y1, z0), (x1, yr, zc), (x0, yr, zc))
        quad(bm, (x0, y1, z1), (x0, yr, zc), (x1, yr, zc), (x1, y1, z1))
        for zz in (z0, z1):
            quad(bm, (x0, y0 + 0.1, zz), (x1, y0 + 0.1, zz), (x1, y1, zz), (x0, y1, zz))
        for xx in (x0, x1):
            quad(bm, (xx, y0 + 0.1, z0), (xx, y0 + 0.1, z1), (xx, y1, z1), (xx, y1, z0))
            bm.faces.new([bm.verts.new(B(p)) for p in ((xx, y1, z0), (xx, y1, z1), (xx, yr, zc))])
    ob = part("Skylight_Panes", "Skylight_Glass", panes, keep_normals=True)
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    c = B((0, WH, zc))
    for f in bm.faces:
        if f.normal.dot(c - f.calc_center_median()) < 0:
            f.normal_flip()
    bm.to_mesh(me)
    bm.free()
    # broken panes boarded from inside with plywood (the repair half done): a few bays, one slope each
    rng = np.random.default_rng(7 + len(SCENE))
    SKY_BOARDS.clear()
    for i in sorted(rng.choice(nb, 4, replace=False)):
        za, zb = (z0, zc) if rng.random() < 0.5 else (zc, z1)
        SKY_BOARDS.append((float(xs[i]) + 0.06, float(xs[i + 1]) - 0.06, za, zb))

    def boards(bm):
        for xa, xb, za, zb in SKY_BOARDS:
            ya = y1 - 0.03
            yb = yr - 0.03
            if za == z0:
                quad(bm, (xa, ya, z0 + 0.05), (xb, ya, z0 + 0.05), (xb, yb, zc - 0.05), (xa, yb, zc - 0.05))
            else:
                quad(bm, (xa, ya, z1 - 0.05), (xa, yb, zc + 0.05), (xb, yb, zc + 0.05), (xb, ya, z1 - 0.05))
    ob = part("Skylight_Boards", "Hoarding_Ply", boards, keep_normals=True)
    orient_faces(ob, (0, -1, 0))


# ---------------------------------------------------------------- ceiling downlights (the day set's lamps; some dead)
DOWN = []


def build_downlights():
    DOWN.clear()
    rng = np.random.default_rng(23 + len(SCENE))
    for z in (-4.75, 4.75):
        for x in np.arange(-18.0, 18.01, 4.0):
            DOWN.append(((float(x), WH, z), rng.random() > 0.3))
    part("Downlight_Rims", "Trim_Paint", lambda bm: [disc(bm, (p[0], WH - 0.004, p[2]), 0.16, 16) for p, _ in DOWN], keep_normals=True)
    part("Downlight_Lenses", "Lamp_Emit", lambda bm: [disc(bm, (p[0], WH - 0.008, p[2]), 0.12, 16) for p, on in DOWN if on], keep_normals=True)
    part("Downlight_Dead", "Metal_Dark", lambda bm: [disc(bm, (p[0], WH - 0.008, p[2]), 0.12, 16) for p, on in DOWN if not on], keep_normals=True)


# ---------------------------------------------------------------- the bays: shuttered or boarded fronts, and the door bays
def fascia(tag, n, a, key, sign_w=4.4):
    """The painted head over a bay (3.2 m to FASCIA_TOP, 4.5 cm proud), its frame either side (each its own piece: a door's opening lies between
    them), the sign board and the painted sign on it."""
    part(f"Fascia_{tag}", "Trim_Paint", lambda bm: wall_box(bm, n, a - 2.6, a + 2.6, SHOP_H, FASCIA_TOP, 0.0, 0.045))
    part(f"Fascia_{tag}_L", "Trim_Paint", lambda bm: wall_box(bm, n, a - 2.6, a - 2.4, 0.0, SHOP_H, 0.0, 0.045))
    part(f"Fascia_{tag}_R", "Trim_Paint", lambda bm: wall_box(bm, n, a + 2.4, a + 2.6, 0.0, SHOP_H, 0.0, 0.045))
    part(f"SignBoard_{tag}", "Metal_Dark", lambda bm: wall_box(bm, n, a - sign_w / 2 - 0.05, a + sign_w / 2 + 0.05, SIGN_Y0 - 0.03, SIGN_Y1 + 0.03, 0.045, 0.075))
    panel(f"Sign_{tag}", "Sign_Paint", on_wall(n, a, (SIGN_Y0 + SIGN_Y1) / 2, 0.0755), n, sign_w, SIGN_Y1 - SIGN_Y0, uv=sign_uv(key))


def shutter(tag, n, a0, a1, y0, y1, uv=None, mat="Shutter_Metal", lock=True):
    """A roller shutter (entrance's): the curtain at 7 cm, the bottom rail, the roller box and its guides; padlocked at the floor."""
    if uv:
        orient_faces(part(f"Shutter_{tag}", mat, lambda bm: corrugated(bm, n, a0, a1, y0 + 0.06, y1 - 0.32, 0.07, uv=uv), keep_normals=True, keep_uv=True), INWARD[n])
    else:
        orient_faces(part(f"Shutter_{tag}", mat, lambda bm: corrugated(bm, n, a0, a1, y0 + 0.06, y1 - 0.32, 0.07), keep_normals=True), INWARD[n])

    def gear(bm):
        wall_box(bm, n, a0, a1, y0, y0 + 0.06, 0.05, 0.10)
        wall_box(bm, n, a0, a1, y1 - 0.34, y1, 0.0, 0.16)
        for s in (a0, a1 - 0.06):
            wall_box(bm, n, s, s + 0.06, y0, y1 - 0.34, 0.0, 0.11)
        if lock:
            c = (a0 + a1) / 2 + 0.7
            wall_box(bm, n, c - 0.05, c + 0.05, y0 + 0.02, y0 + 0.13, 0.09, 0.13)
    part(f"ShutterGear_{tag}", "Metal_Dark", gear)


def boarded(tag, n, a0, a1, y1, notice_cell=10):
    """A front boarded over with plywood sheets (entrance's CLOSED FOR RENOVATION front), battens, and a notice stapled to it."""
    w = (a1 - a0) / 4
    part(f"Hoarding_{tag}", "Hoarding_Ply", lambda bm: [wall_box(bm, n, a0 + k * w + 0.004, a0 + (k + 1) * w - 0.004, 0.0, y1 - 0.004, 0.02, 0.10)
                                                         for k in range(4)])
    part(f"HoardingBack_{tag}", "Metal_Dark", lambda bm: wall_box(bm, n, a0, a1, 0.0, y1, 0.0, 0.02))
    part(f"Battens_{tag}", "Scaffold_Board", lambda bm: [wall_box(bm, n, a0 + 0.05, a1 - 0.05, y - 0.05, y + 0.05, 0.10, 0.12)
                                                          for y in (0.25, y1 / 2, y1 - 0.3)])
    c = on_wall(n, (a0 + a1) / 2 - 0.6, 1.55, 0.1215)
    panel(f"Notice_{tag}", "Poster_Art", c, n, 0.6, 0.6, uv=cell_uv(notice_cell))


def build_shopfronts():
    for side, k, bx, name in shop_bays():
        n = SIDE[side]
        tag = f"{side}{k + 1}"
        a0, a1 = bx - 2.4, bx + 2.4
        if (side, bx) in TH["boarded"]:
            boarded(tag, n, a0, a1, SHOP_H)
        elif name == "ARCADE":
            shutter(tag, n, a0, a1, 0.0, SHOP_H, uv=cell_uv(8, (0, 0, 2, 1)), mat="Poster_Art", lock=True)
        else:
            shutter(tag, n, a0, a1, 0.0, SHOP_H)
        fascia(tag, n, bx, ("bay", side, bx))
        if name == "ARCADE":
            build_bulbs(f"Arcade_{tag}", n, bx, 4.4, SIGN_Y0 - 0.1, SIGN_Y1 + 0.1, 0.09)


BULBS = []


def build_bulbs(tag, n, a, w, y0, y1, d, pitch=0.2, dead=0.25, seed=3):
    """A border of round bulbs (Lamp_Emit), the odd one dead (Metal_Dark), round a sign: the arcade's, the marquee's."""
    rng = np.random.default_rng(seed + len(tag))
    pts = []
    for a_ in np.arange(a - w / 2, a + w / 2 + 1e-6, pitch):
        pts += [(a_, y0), (a_, y1)]
    for y in np.arange(y0 + pitch, y1 - pitch / 2, pitch):
        pts += [(a - w / 2, y), (a + w / 2, y)]
    on = [rng.random() > dead for _ in pts]
    part(f"Bulbs_{tag}", "Lamp_Emit", lambda bm: [sphere(bm, on_wall(n, p[0], p[1], d), 0.035, 8) for p, o in zip(pts, on) if o])
    part(f"BulbsDead_{tag}", "Metal_Dark", lambda bm: [sphere(bm, on_wall(n, p[0], p[1], d), 0.035, 8) for p, o in zip(pts, on) if not o])
    BULBS.extend(on_wall(n, p[0], p[1], d + 0.05) for p, o in zip(pts, on) if o)


def door_pieces(d):
    """The front either side of a door bay's door and the panel over it, as the greybox builds them (along-wall a0, a1, y0, y1)."""
    bx, w = d["bx"], d["w"]
    dh = DOOR_H if w < 1.5 else 2.4
    return [(bx - 2.4, bx - w / 2 - 0.05, 0.0, SHOP_H), (bx + w / 2 + 0.05, bx + 2.4, 0.0, SHOP_H)], (bx - w / 2 - 0.05, bx + w / 2 + 0.05, dh, SHOP_H), dh


def build_door_bays():
    """Each door bay: its front either side of the door (whitewashed glazing, a bookshop window, restroom tiles, soft-play padding, shutters or
    painted steel, by the theme), the shutter rolled up over the door, the door's jambs, the fascia and the sign."""
    for d in DOORS:
        n = SIDE[d["side"]]
        did, w = d["did"], d["w"]
        style = TH["door_style"].get(did, "glass")
        sides, over, dh = door_pieces(d)
        for j, (a0, a1, y0, y1) in enumerate(sides):
            tag = f"{did}_{j}"
            if style in ("glass", "books"):
                def frame(bm):
                    for s in (a0, a1 - 0.06):
                        wall_box(bm, n, s, s + 0.06, y0, y1, 0.0, 0.12)
                    wall_box(bm, n, a0, a1, y0, y0 + 0.14, 0.0, 0.12)
                    wall_box(bm, n, a0, a1, y1 - 0.1, y1, 0.0, 0.12)
                    wall_box(bm, n, a0, a1, 2.55, 2.61, 0.03, 0.10)
                part(f"Front_{tag}_Frame", "Metal_Steel", frame)
                pane_a0, pane_a1 = a0 + 0.06, a1 - 0.06
                if style == "books":
                    cpt = on_wall(n, (pane_a0 + pane_a1) / 2, (0.14 + 2.55) / 2, 0.06)
                    panel(f"Front_{tag}_Window", "Poster_Art", cpt, n, pane_a1 - pane_a0, 2.55 - 0.14, uv=cell_uv(j, (0, 0.05, 1, 1)))
                    cpt = on_wall(n, (pane_a0 + pane_a1) / 2, (2.61 + y1 - 0.1) / 2, 0.06)
                    panel(f"Front_{tag}_Transom", "Glass_Whitewash", cpt, n, pane_a1 - pane_a0, y1 - 0.1 - 2.61)
                    panel(f"Front_{tag}_Poster", "Poster_Art", on_wall(n, (pane_a0 + pane_a1) / 2 + (0.25 if j else -0.25), 1.2, 0.062), n, 0.42, 0.63,
                          uv=cell_uv(2 + j))
                else:
                    cpt = on_wall(n, (pane_a0 + pane_a1) / 2, (0.14 + y1 - 0.1) / 2, 0.06)
                    panel(f"Front_{tag}_Glass", "Glass_Whitewash", cpt, n, pane_a1 - pane_a0, y1 - 0.1 - 0.14)
            elif style == "shutters":
                shutter(tag, n, a0, a1, y0, y1, lock=(j == 0))
            elif style == "staff":
                part(f"Front_{tag}_Panel", "Trim_Paint", lambda bm: wall_box(bm, n, a0, a1, y0, y1, 0.0, 0.10))
                part(f"Front_{tag}_Kick", "Metal_Dark", lambda bm: wall_box(bm, n, a0, a1, y0, y0 + 0.12, 0.10, 0.12))
                if j == 0:
                    panel(f"Front_{tag}_Notice", "Poster_Art", on_wall(n, (a0 + a1) / 2, 1.6, 0.1005), n, 0.5, 0.5, uv=cell_uv(11))
            elif style == "tiles":
                part(f"Front_{tag}_Tiles", "Tile_White", lambda bm: wall_box(bm, n, a0, a1, y0, y1, 0.0, 0.12))
                c = on_wall(n, a1 - 0.45 if j == 0 else a0 + 0.45, 1.75, 0.1205)
                panel(f"Front_{tag}_Picto", "Poster_Art", c, n, 0.42, 0.42, uv=cell_uv(8 + j))
            elif style == "padding":
                part(f"Front_{tag}_Pad", "Padding_Vinyl", lambda bm: wall_box(bm, n, a0, a1, y0, y1, 0.0, 0.12))
                c = on_wall(n, (a0 + a1) / 2, 1.5, 0.1205)
                if j == 0:
                    panel(f"Front_{tag}_Poster", "Poster_Art", c, n, 0.55, 0.82, uv=cell_uv(0))
                else:
                    panel(f"Front_{tag}_Poster", "Poster_Art", c, n, 0.55, 0.82, uv=cell_uv(3))
        a0, a1, y0, y1 = over
        if style in ("glass", "books", "shutters"):
            orient_faces(part(f"Over_{did}", "Shutter_Metal", lambda bm: corrugated(bm, n, a0, a1, y0 + 0.02, y1 - 0.3, 0.07), keep_normals=True), INWARD[n])
            part(f"OverGear_{did}", "Metal_Dark", lambda bm: [wall_box(bm, n, a0, a1, y1 - 0.32, y1, 0.0, 0.16), wall_box(bm, n, a0, a1, y0, y0 + 0.05, 0.05, 0.10)])
        else:
            mat = {"staff": "Trim_Paint", "tiles": "Tile_White", "padding": "Padding_Vinyl"}[style]
            part(f"Over_{did}", mat, lambda bm: wall_box(bm, n, a0, a1, y0, y1, 0.0, 0.12 if style != "staff" else 0.10))
        jm = "Metal_Steel" if style in ("glass", "books") else "Trim_Paint"
        e0, e1 = d["bx"] - w / 2, d["bx"] + w / 2
        part(f"Jamb_{did}_0", jm, lambda bm: wall_box(bm, n, e0 - 0.045, e0 - 0.005, 0.0, dh, 0.0, 0.115))     # inside the front's 5 cm (the layout check)
        part(f"Jamb_{did}_1", jm, lambda bm: wall_box(bm, n, e1 + 0.005, e1 + 0.045, 0.0, dh, 0.0, 0.115))
        part(f"Head_{did}", jm, lambda bm: wall_box(bm, n, e0 - 0.045, e1 + 0.045, dh, dh + 0.06, 0.0, 0.12))
        fascia(did, n, d["bx"], ("door", did))


# ---------------------------------------------------------------- the two ends: the atrium's doors (west) and the wing's big door (east)
def glazed_screen(tag, n, spans, y1, d=0.03):
    """Whitewashed glass flush on an end wall (4.5 cm deep at most), in a steel frame: the screens either side of an end's doors (one piece a
    span, so no piece reaches over the doors' opening)."""
    for j, (a0, a1) in enumerate(spans):
        def frame(bm):
            k = max(1, round((a1 - a0) / 1.2))
            for i in range(k + 1):
                a = a0 + (a1 - a0) * i / k
                wall_box(bm, n, a - 0.03, a + 0.03, 0.0, y1, 0.0, 0.045)
            wall_box(bm, n, a0, a1, 0.0, 0.15, 0.0, 0.045)
            wall_box(bm, n, a0, a1, y1 - 0.06, y1, 0.0, 0.045)
        part(f"Screen_{tag}_{j}_Frame", "Metal_Steel", frame)
        orient_faces(part(f"Screen_{tag}_{j}_Glass", "Glass_Whitewash", lambda bm: quad(bm, on_wall(n, a0, 0.15, d), on_wall(n, a0, y1 - 0.06, d),
                                                                                        on_wall(n, a1, y1 - 0.06, d), on_wall(n, a1, 0.15, d)),
                          keep_normals=True), INWARD[n])


def door_casing(tag, n, a, w, h, mat="Metal_Steel"):
    part(f"Casing_{tag}_0", mat, lambda bm: wall_box(bm, n, a - w / 2 - 0.09, a - w / 2, 0.0, h, 0.0, 0.045))
    part(f"Casing_{tag}_1", mat, lambda bm: wall_box(bm, n, a + w / 2, a + w / 2 + 0.09, 0.0, h, 0.0, 0.045))
    part(f"Casing_{tag}_Head", mat, lambda bm: wall_box(bm, n, a - w / 2 - 0.09, a + w / 2 + 0.09, h, h + 0.1, 0.0, 0.045))


EXITS = []


def exit_sign(tag, n, a, y):
    """An EXIT box over a door, facing into the wing (emissive, always on; in both bakes' light)."""
    part(f"Exit_{tag}_Housing", "Metal_Dark", lambda bm: wall_box(bm, n, a - 0.26, a + 0.26, y - 0.1, y + 0.1, 0.0, 0.08))
    panel(f"Exit_{tag}_Face", "Sign_Exit", on_wall(n, a, y, 0.0805), n, 0.44, 0.16)
    EXITS.append((on_wall(n, a, y, 0.1), INWARD[n]))


def build_west_end():
    """The atrium's glass doors in the west wall: steel casings, whitewashed screens either side (the wing is closed off from the atrium for the
    works), the EXIT sign over them, the directory board."""
    n = "+x"
    door_casing("entrance", n, 0.0, G.WING_DOOR_W, G.WING_DOOR_H)
    glazed_screen("west", n, [(-3.8, -G.WING_DOOR_W / 2 - 0.1), (G.WING_DOOR_W / 2 + 0.1, 3.8)], G.WING_DOOR_H + 0.1)
    part("Screen_west_Head", "Trim_Paint", lambda bm: wall_box(bm, n, -3.9, 3.9, G.WING_DOOR_H + 0.1, G.WING_DOOR_H + 0.9, 0.0, 0.045))
    panel("Sign_west_Wing", "Sign_Paint", on_wall(n, 0.0, G.WING_DOOR_H + 0.5, 0.0455), n, 4.4, 0.6, uv=sign_uv(("wing",)))
    exit_sign("west", n, 0.0, G.WING_DOOR_H + 1.15)
    x = -5.6
    part("Directory_Frame", "Metal_Dark", lambda bm: wall_box(bm, n, x - 0.65, x + 0.65, 0.85, 2.75, 0.0, 0.04))
    panel("Directory_Face", "Poster_Art", on_wall(n, x, 1.8, 0.0405), n, 1.2, 1.8, uv=cell_uv(7))


def build_east_end():
    n = "-x"
    if SCENE == "wing_books":
        # the plywood hoarding across the wing's end (CLOSED FOR RENOVATION), with the site door to the construction zone
        for b in LOC.boxes:
            if not b["name"].startswith("Hoarding_Face"):
                continue
            mn, mx = b["min"], b["max"]
            a0, a1, y0, y1 = mn[2], mx[2], mn[1], mx[1]
            k = max(1, round((a1 - a0) / 1.22))
            w = (a1 - a0) / k
            part(b["name"], "Hoarding_Ply", lambda bm: [wall_box(bm, n, a0 + i * w + 0.004, a0 + (i + 1) * w - 0.004, y0, y1, 0.0, 0.10) for i in range(k)])
            if y0 < 0.5:
                part(b["name"] + "_Battens", "Scaffold_Board", lambda bm: [wall_box(bm, n, a0 + 0.05, a1 - 0.05, y - 0.05, y + 0.05, 0.10, 0.12)
                                                                            for y in (0.3, 1.5, 2.7)])
        panel("Sign_hoarding", "Sign_Paint", on_wall(n, -3.85, 2.1, 0.1215), n, 5.6, 0.76, uv=sign_uv(("hoarding",)))
        panel("Sign_site", "Sign_Paint", on_wall(n, 3.85, 2.25, 0.1215), n, 4.6, 0.58, uv=sign_uv(("site",)))
        panel("Notice_hoarding_0", "Poster_Art", on_wall(n, -1.8, 1.25, 0.1215), n, 0.6, 0.6, uv=cell_uv(10))
        panel("Notice_hoarding_1", "Poster_Art", on_wall(n, 1.7, 1.25, 0.1215), n, 0.5, 0.75, uv=cell_uv(6))
        part("Jamb_construction_0", "Scaffold_Board", lambda bm: wall_box(bm, n, -EW / 2 - 0.045, -EW / 2 - 0.005, 0.0, EH, 0.0, 0.115))
        part("Jamb_construction_1", "Scaffold_Board", lambda bm: wall_box(bm, n, EW / 2 + 0.005, EW / 2 + 0.045, 0.0, EH, 0.0, 0.115))
    elif SCENE == "wing_cinema":
        door_casing("cinema", n, 0.0, EW, EH)
        glazed_screen("east", n, [(-4.4, -EW / 2 - 0.1), (EW / 2 + 0.1, 4.4)], EH + 0.1)
        for b in LOC.boxes:                                                   # the two poster cases by the cinema's doors (greybox colliders)
            if not b["name"].startswith("Poster_Case"):
                continue
            mn, mx = b["min"], b["max"]
            k = 4 if mn[2] < 0 else 5
            part(b["name"], "Metal_Dark", lambda bm: wall_box(bm, n, mn[2], mx[2], mn[1], mx[1], 0.0, WX - mn[0]))
            panel(b["name"] + "_Poster", "Poster_Art", on_wall(n, (mn[2] + mx[2]) / 2, (mn[1] + mx[1]) / 2, WX - mn[0] + 0.001), n,
                  mx[2] - mn[2] - 0.12, mx[1] - mn[1] - 0.12, uv=cell_uv(k))
        build_marquee()
    else:
        door_casing("foodcourt", n, 0.0, EW, EH)
        glazed_screen("east", n, [(-6.4, -EW / 2 - 0.1), (EW / 2 + 0.1, 6.4)], EH + 0.1)
        b = BOXL["decor_FoodCourt_Sign"]
        part("FoodCourt_Board", "Metal_Dark", lambda bm: wall_box(bm, n, b["min"][2], b["max"][2], b["min"][1], b["max"][1], 0.0, 0.08))
        panel("Sign_foodcourt", "Sign_Paint", on_wall(n, 0.0, (b["min"][1] + b["max"][1]) / 2, 0.0805), n, b["max"][2] - b["min"][2] - 0.2,
              b["max"][1] - b["min"][1] - 0.2, uv=sign_uv(("foodcourt",)))
        build_bulbs("FoodCourt", n, 0.0, b["max"][2] - b["min"][2] - 0.1, b["min"][1] + 0.05, b["max"][1] - 0.05, 0.1, pitch=0.25, dead=0.4)


def build_marquee():
    """The cinema's marquee over its doors (the greybox's decor box): a canopy 1.2 m deep, NOW SHOWING on its face, a border of bulbs."""
    b = BOXL["decor_Marquee"]
    mn, mx = b["min"], b["max"]
    part("Marquee_Body", "Trim_Paint", lambda bm: cube(bm, (mn[0], mn[1], mn[2]), (mx[0], mx[1], mx[2])))
    zc = (mn[2] + mx[2]) / 2
    face_d = WX - mn[0] + 0.002
    panel("Marquee_Sign", "Sign_Paint", on_wall("-x", zc, mn[1] + 0.68, face_d), "-x", mx[2] - mn[2] - 0.6, 0.5, uv=sign_uv(("marquee",)))
    panel("Marquee_Sign2", "Sign_Paint", on_wall("-x", zc, mn[1] + 0.25, face_d), "-x", (mx[2] - mn[2]) * 0.6, 0.3, uv=sign_uv(("marquee2",)))
    build_bulbs("Marquee", "-x", zc, mx[2] - mn[2] - 0.15, mn[1] + 0.06, mx[1] - 0.06, face_d + 0.03, pitch=0.25, dead=0.35)
    part("Marquee_Under", "Lamp_Emit", lambda bm: [disc(bm, (mn[0] + 0.5, mn[1] - 0.004, z), 0.07, 12) for z in np.linspace(mn[2] + 0.8, mx[2] - 0.8, 5)],
         keep_normals=True)


# ---------------------------------------------------------------- scaffolding (on the greybox's posts, decks and rails), dust sheets
SCAF_LAMPS = []


def build_scaffolds():
    rng = np.random.default_rng(31 + len(SCENE))
    r = 0.0241
    for sc_ in CFG["scaffolds"]:
        x0, x1, z0, z1, name = sc_[:5]
        opt = sc_[5] if len(sc_) > 5 else {}
        decks, bay, sheet = opt.get("decks", (2.0, 4.0)), opt.get("bay", 2.0), opt.get("sheet", False)
        nposts = max(1, int(round((x1 - x0) / bay)))
        xs = [x0 + (x1 - x0) * i / nposts for i in range(nposts + 1)]
        top = decks[-1] + 1.0
        for i, x in enumerate(xs):                                              # each standard is its own piece (it stands on its own post collider)
            for j, z in enumerate((z0, z1)):
                part(f"Scaffold_{name}_Std_{i}_{j}", "Metal_Steel", lambda bm: cyl(bm, (x, 0.03, z), (x, top, z), r, r, 10, cap=False), smooth=True)
                part(f"Scaffold_{name}_Plate_{i}_{j}", "Metal_Dark", lambda bm: cube(bm, (x - 0.07, 0.0, z - 0.07), (x + 0.07, 0.03, z + 0.07)))

        def tubes(bm):                                                           # ledgers, transoms, guardrails and braces: all at or above the first lift
            for d in decks:
                for z in (z0, z1):
                    cyl(bm, (x0 - 0.15, d - 0.05, z), (x1 + 0.15, d - 0.05, z), r, r, 8, cap=False)
                for x in xs:
                    cyl(bm, (x, d - 0.09, z0 - 0.1), (x, d - 0.09, z1 + 0.1), r, r, 8, cap=False)
                for dy in (0.5,):
                    cyl(bm, (x0, d + dy, z1), (x1, d + dy, z1), r, r, 8, cap=False)
            for d in decks:
                cyl(bm, (x0, d + 0.975, z1), (x1, d + 0.975, z1), r, r, 8, cap=False)       # the guard rail on the greybox's rail collider
            ys = list(decks)
            if len(ys) > 1:
                for xa, xb in zip(xs, xs[1:]):
                    cyl(bm, (xa, ys[0], z1 + 0.06), (xb, ys[1], z1 + 0.06), r, r, 8, cap=False)
            for x in xs[::2]:                                                     # ties back to the wall, high up
                zw = -WZ if z0 < 0 else WZ
                zn = z0 if z0 < 0 else z1
                if abs(zn - zw) < 1.0:
                    cyl(bm, (x, top - 0.4, zn), (x, top - 0.4, zw), r, r, 8, cap=False)
            if len(decks) == 1 and (z1 - z0) > 6:                                  # the cinema's bridge: a lattice beam under each edge of its deck
                for x in (x0, x1):
                    yb = decks[0] - 0.6
                    cyl(bm, (x, yb, z0), (x, yb, z1), r, r, 8, cap=False)
                    zz = np.linspace(z0, z1, 9)
                    for za, zb in zip(zz, zz[1:]):
                        cyl(bm, (x, yb, za), (x, decks[0] - 0.09, zb), r * 0.8, r * 0.8, 6, cap=False)
        part(f"Scaffold_{name}_Tubes", "Metal_Steel", tubes, smooth=True)

        def boards(bm):
            for d in decks:
                cube(bm, (x0 - 0.1, d - 0.06, z0 - 0.1), (x1 + 0.1, d, z1 + 0.1))
                cube(bm, (x0, d, z1 - 0.02), (x1, d + 0.15, z1 + 0.02))
        part(f"Scaffold_{name}_Boards", "Scaffold_Board", boards)
        if sheet:
            prof = [(0.0, top - 0.05), (0.04, top - 0.6), (0.07, decks[0]), (0.1, 0.55)]
            ob = part(f"decor_DustSheet_{name}", "Cloth_Sheet", lambda bm: drape(bm, (0.0, 0.0, z1 + 0.06), (1, 0, 0), (0, 0, 1), x0 + 0.05, x1 - 0.05, prof, rng,
                                                                                 folds=0.05, nu=28), smooth=True, keep_normals=True)
            orient_faces(ob, (0, 0, 1) if z0 < 0 else (0, 0, -1))
        else:                                                                     # a sheet thrown over the top deck's room edge, hanging down its face
            mid = (x0 + x1) / 2
            zr, nr = (z1, (0, 0, 1)) if z0 < 0 else (z0, (0, 0, -1))
            prof = [(-0.6, decks[-1] + 0.02), (-0.05, decks[-1] + 1.0), (0.05, decks[-1] + 0.95), (0.08, decks[-1] - 0.4), (0.1, decks[-1] - 1.3)]
            ob = part(f"decor_RailSheet_{name}", "Cloth_Sheet", lambda bm: drape(bm, (0.0, 0.0, zr), (1, 0, 0), nr, mid - 1.4, mid + 1.0, prof, rng, folds=0.04),
                      smooth=True, keep_normals=True)
            orient_faces(ob, nr)
    # one work lamp clamped high on the first scaffold, aimed at the wall it is working on (Lamp_Emit: on by day)
    sc_ = CFG["scaffolds"][0]
    x0, x1, z0, z1 = sc_[:4]
    decks = (sc_[5] if len(sc_) > 5 else {}).get("decks", (2.0, 4.0))
    lamp = ((x0 + x1) / 2, decks[-1] + 0.9, z1)
    zw = -WZ if z0 < 0 else WZ
    aim = ((x0 + x1) / 2 + 1.0, 2.0, zw)
    dv = (Vector(aim) - Vector(lamp)).normalized()
    SCAF_LAMPS.append((lamp, tuple(dv)))
    part("WorkLamp_Body", "Metal_Dark", lambda bm: [cyl(bm, tuple(Vector(lamp) - dv * 0.12), tuple(Vector(lamp) + dv * 0.04), 0.13, 0.13, 4),
                                                   cyl(bm, (lamp[0], lamp[1] - 0.2, lamp[2]), lamp, 0.015, 0.015, 6)])
    part("WorkLamp_Lens", "Lamp_Emit", lambda bm: cyl(bm, tuple(Vector(lamp) + dv * 0.04), tuple(Vector(lamp) + dv * 0.05), 0.11, 0.11, 4))


# ---------------------------------------------------------------- the things the greybox put under dust sheets; the cinema's kiosk
def build_sheeted():
    rng = np.random.default_rng(37 + len(SCENE))
    for nm, x0, x1, z0, z1, h in CFG["sheeted"]:
        if nm == "TicketKiosk":
            build_kiosk(x0, x1, z0, z1, h)
            continue
        tag = f"{nm}_{x0:+.0f}"
        sh = h
        if nm == "Bench":
            sh = h + 0.02
            part(f"Sheeted_{tag}_Feet", "Metal_Dark", lambda bm: [cube(bm, (xe, 0.0, z0 + 0.06), (xe + 0.06, 0.18, z1 - 0.06)) for xe in (x0 + 0.06, x1 - 0.12)])
        elif nm == "Planter":
            part(f"Sheeted_{tag}_Box", "Floor_Border", lambda bm: cube(bm, (x0, 0.0, z0), (x1, h - 0.05, z1)))         # a tall terrazzo planter
            part(f"Sheeted_{tag}_Soil", "Clutter_Paint", lambda bm: cube(bm, (x0 + 0.06, h - 0.05, z0 + 0.06), (x1 - 0.06, h - 0.02, z1 - 0.06)))

            def twigs(bm):                                                       # a dead ficus: a trunk and bare branches, inside the planter's plan
                cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
                cyl(bm, (cx, h - 0.05, cz), (cx + 0.05, 1.9, cz - 0.04), 0.04, 0.025, 8)
                r2 = np.random.default_rng(5)
                for k in range(9):
                    a = r2.uniform(0, 2 * math.pi)
                    y = r2.uniform(1.2, 1.85)
                    L_ = r2.uniform(0.3, 0.65)
                    p0 = (cx + 0.03, y, cz - 0.02)
                    p1 = (cx + math.cos(a) * L_, y + r2.uniform(0.15, 0.45), cz + math.sin(a) * L_ * 0.9)
                    p1 = (min(max(p1[0], x0 + 0.04), x1 - 0.04), p1[1], min(max(p1[2], z0 + 0.04), z1 - 0.04))
                    cyl(bm, p0, p1, 0.012, 0.006, 5)
            part(f"Sheeted_{tag}_Ficus", "Bench_Wood", twigs)
            ob = part(f"decor_Leaves_{tag}", "Clutter_Paint", lambda bm: [cube(bm, (x, 0.0, z), (x + 0.06, 0.004, z + 0.04)) for x, z in
                                                                          zip(rng.uniform(x0 - 0.5, x1 + 0.5, 24), rng.uniform(z0 - 0.4, z1 + 0.4, 24))])
            continue
        elif nm.startswith("KiddieRide"):
            part(f"Sheeted_{tag}_Base", "Plastic_White", lambda bm: cube(bm, (x0, 0.0, z0), (x1, 0.12, z1)))
        elif nm == "ClawMachine":
            part(f"Sheeted_{tag}_Plinth", "Metal_Dark", lambda bm: cube(bm, (x0 + 0.03, 0.0, z0 + 0.03), (x1 - 0.03, 0.1, z1 - 0.03)))
        elif nm == "PopcornCart":
            for xw in (x0 + 0.2, x1 - 0.2):
                part(f"Sheeted_{tag}_Wheel_{xw:+.1f}", "Metal_Dark", lambda bm: cyl(bm, (xw, 0.16, z0 + 0.02), (xw, 0.16, z0 + 0.08), 0.16, 0.16, 16))
        if nm in ("Bench", "BookCart", "PopcornCart"):                           # a low dark skid the sheet falls round (it fills the collider's foot)
            part(f"Sheeted_{tag}_Skid", "Metal_Dark", lambda bm: cube(bm, (x0 + 0.03, 0.0, z0 + 0.03), (x1 - 0.03, 0.05, z1 - 0.03)))
        part(f"Sheeted_{tag}", "Cloth_Sheet", lambda bm: drape_box(bm, x0 + 0.02, x1 - 0.02, z0 + 0.02, z1 - 0.02, sh, rng,
                                                                    hem=(0.05, 0.2) if nm != "ClawMachine" else (0.12, 0.35)), smooth=True, keep_normals=True)


def build_kiosk(x0, x1, z0, z1, h):
    """The cinema's ticket kiosk on its collider: a wood-clad booth with a counter and a ticket window facing the concourse, a canopy with
    TICKETS on it, a dust sheet thrown over one end of the canopy and hanging down."""
    face = z0                                                                    # the side toward the concourse (the kiosk stands by the south wall)
    part("Kiosk_Body", "Bench_Wood", lambda bm: [cube(bm, (x0 + 0.05, 0.0, z0 + 0.03), (x1 - 0.05, 1.05, z1 - 0.05)),
                                                 cube(bm, (x0 + 0.05, 1.05, z0 + 0.35), (x1 - 0.05, 2.35, z1 - 0.05))])
    part("Kiosk_Counter", "Trim_Paint", lambda bm: cube(bm, (x0 + 0.02, 1.05, z0 + 0.02), (x1 - 0.02, 1.1, z0 + 0.42)))
    part("Kiosk_Plinth", "Metal_Dark", lambda bm: cube(bm, (x0 + 0.04, 0.0, z0 + 0.1), (x1 - 0.04, 0.1, z1 - 0.04)))

    def frame(bm):
        for x in np.linspace(x0 + 0.1, x1 - 0.1, 4):
            cube(bm, (x - 0.03, 1.1, z0 + 0.34), (x + 0.03, 2.35, z0 + 0.38))
        cube(bm, (x0 + 0.1, 2.25, z0 + 0.34), (x1 - 0.1, 2.35, z0 + 0.38))
        cube(bm, (x0 + 0.5, 1.1, z0 + 0.32), (x1 - 0.5, 1.16, z0 + 0.36))
    part("Kiosk_Frame", "Metal_Steel", frame)
    ob = part("Kiosk_Glass", "Glass_Whitewash", lambda bm: quad(bm, (x0 + 0.1, 1.16, z0 + 0.335), (x1 - 0.1, 1.16, z0 + 0.335), (x1 - 0.1, 2.25, z0 + 0.335),
                                                              (x0 + 0.1, 2.25, z0 + 0.335)), keep_normals=True)
    orient_faces(ob, (0, 0, -1))
    part("Kiosk_Canopy", "Trim_Paint", lambda bm: cube(bm, (x0, 2.35, z0), (x1, 2.6, z1)))
    panel("Kiosk_Sign", "Sign_Paint", ((x0 + x1) / 2, 2.475, z0 - 0.002), "-z", x1 - x0 - 0.1, 0.22, uv=sign_uv(("kiosk",)))
    rng = np.random.default_rng(41)
    prof = [(-(x1 - x0) * 0.35, 2.61), (-0.02, 2.62), (0.02, 2.3), (0.03, 1.3), (0.04, 0.35)]
    ob = part("decor_Kiosk_Sheet", "Cloth_Sheet", lambda bm: drape(bm, (x1, 0.0, 0.0), (0, 0, 1), (1, 0, 0), z0 + 0.05, z1 - 0.05, prof, rng, folds=0.02),
              smooth=True, keep_normals=True)
    orient_faces(ob, (1, 0, 0))


# ---------------------------------------------------------------- wall dressing: the cinema's poster cases, notices, hanging signs
def build_poster_row():
    """The cinema's row of poster cases along the south wall's free stretches (4.5 cm proud): a dark frame and a film poster in each."""
    k = 0
    for a0, a1 in free_spans("S"):
        a = (a0 + a1) / 2
        if a1 - a0 < 1.0:
            continue
        n = "-z"
        part(f"PosterCase_{k}", "Metal_Dark", lambda bm: wall_box(bm, n, a - 0.5, a + 0.5, 0.75, 2.35, 0.0, 0.045))
        part(f"PosterCase_{k}_Light", "Lamp_Emit", lambda bm: wall_box(bm, n, a - 0.42, a + 0.42, 2.29, 2.33, 0.045, 0.048))
        panel(f"PosterCase_{k}_Poster", "Poster_Art", on_wall(n, a, 1.53, 0.0455), n, 0.88, 1.4, uv=cell_uv(k % 7))
        k += 1


def build_notices():
    """Paper notices taped to the free wall stretches (PARDON OUR DUST and the wing's own), and a mall map board."""
    picks = {"wing_books": [("N", 0, 10), ("S", 3, 5), ("N", 6, 4), ("S", 7, 2)],
             "wing_cinema": [("N", 0, 10), ("N", 3, 11)],
             "wing_entertainment": [("N", 0, 10), ("N", 4, 1), ("S", 3, 2), ("S", 6, 0)]}[SCENE]
    for side, i, cell in picks:
        spans = free_spans(side)
        if i >= len(spans):
            continue
        a0, a1 = spans[i]
        a = (a0 + a1) / 2
        w, h = (0.5, 0.75) if cell < 8 else (0.55, 0.55)
        panel(f"Notice_{side}_{i}", "Poster_Art", on_wall(SIDE[side], a, 1.55, 0.004), SIDE[side], w, h, uv=cell_uv(cell))


def build_hanging_signs():
    """Blade signs hung from the ceiling either side of the skylight, two-sided, reading along the wing (all overhead)."""
    for k, x in enumerate((-9.0, 9.0)):
        z = -4.0 if k == 0 else 4.0
        y0, y1 = 3.5, 3.95
        part(f"Hanging_{k}_Rods", "Metal_Steel", lambda bm: [cyl(bm, (x, y1, z + dz), (x, WH, z + dz), 0.008, 0.008, 6) for dz in (-1.1, 1.1)])
        part(f"Hanging_{k}_Board", "Metal_Dark", lambda bm: cube(bm, (x - 0.03, y0 - 0.03, z - 1.35), (x + 0.03, y1 + 0.03, z + 1.35)))
        uv = sign_uv(("hanging", k))
        panel(f"Hanging_{k}_FaceW", "Sign_Paint", (x - 0.031, (y0 + y1) / 2, z), "-x", 2.6, y1 - y0, uv=uv)
        panel(f"Hanging_{k}_FaceE", "Sign_Paint", (x + 0.031, (y0 + y1) / 2, z), "+x", 2.6, y1 - y0, uv=uv)


# ---------------------------------------------------------------- the emergency fittings (the night set's only light)
EMERG = []


def build_emergency():
    """Twin-head emergency fittings on every pilaster's face at 3.75 m, aimed up and down the concourse, and one over each end's doors."""
    EMERG.clear()
    spots = []
    for p in PILASTERS:
        for side in ("N", "S"):
            spots.append((SIDE[side], p, 0.3))
    spots += [("+x", 2.4, 0.0), ("-x", -2.4, 0.0)]
    ys = {"+x": 3.75, "-x": 4.7}                                                   # over the far end's marquee or sign

    def bodies(bm):
        for n, a, d in spots:
            yb = ys.get(n, 3.75)
            wall_box(bm, n, a - 0.2, a + 0.2, yb - 0.06, yb + 0.06, d, d + 0.09)
    part("Emergency_Bodies", "Plastic_White", bodies)
    heads = []
    for n, a, d in spots:
        yb = ys.get(n, 3.75)
        for k in (-1, 1):
            p = Vector(on_wall(n, a + k * 0.14, yb + 0.12, d + 0.07))
            aim = Vector(on_wall(n, a + k * 5.0, 0.0, 5.0 if n in ("+z", "-z") else 4.0))
            heads.append((tuple(p), tuple((aim - p).normalized())))
    EMERG.extend(heads)

    def cans(bm):
        for p, dd in heads:
            P, D = Vector(p), Vector(dd)
            cyl(bm, tuple(P - D * 0.06), tuple(P + D * 0.03), 0.045, 0.055, 12)
    part("Emergency_Heads", "Plastic_White", cans, smooth=True)
    part("Emergency_Lenses", "Emergency_Emit", lambda bm: [cyl(bm, tuple(Vector(p) + Vector(dd) * 0.03), tuple(Vector(p) + Vector(dd) * 0.036), 0.046, 0.046, 12)
                                                         for p, dd in heads])


# ---------------------------------------------------------------- clutter on the floor (all low; passable: decor_), kept off the walking lines
def keepout():
    """Rectangles (x0, x1, z0, z1) the floor clutter keeps off: the concourse's middle, each door's approach, every mannequin's place."""
    out = [(-WX, WX, -3.2, 3.2)]
    for d in DOORS:
        zc = ZC[d["side"]]
        out.append((d["bx"] - 1.4, d["bx"] + 1.4, min(zc, -zc * 0.4), max(zc, -zc * 0.4)))
    out.append((-WX, -WX + 3.0, -2.0, 2.0))
    out.append((WX - 3.0, WX, -2.5, 2.5))
    for pos, face, role, what in CFG["mannequins"]:
        out.append((pos[0] - 0.9, pos[0] + 0.9, pos[2] - 0.9, pos[2] + 0.9))
    return out


def clear_of(x0, x1, z0, z1, ko):
    return not any(x0 < k[1] and x1 > k[0] and z0 < k[3] and z1 > k[2] for k in ko)


def build_clutter():
    rng = np.random.default_rng(47 + len(SCENE))
    ko = keepout()

    def cloth_flat(bm, x0, x1, z0, z1, y0, nx=16, nz=10, amp=0.035):
        ph = rng.uniform(0, 6.3, 4)
        vs = []
        for j in range(nz + 1):
            row = []
            for i in range(nx + 1):
                u, v = i / nx, j / nz
                x = x0 + (x1 - x0) * u + 0.06 * math.sin(v * 9 + ph[0]) * (u in (0, 1))
                z = z0 + (z1 - z0) * v + 0.06 * math.sin(u * 7 + ph[1]) * (v in (0, 1))
                y = y0 + amp * (0.5 + 0.5 * math.sin(u * 11 + ph[2]) * math.sin(v * 8 + ph[3])) ** 2
                row.append(bm.verts.new(B((x, y, z))))
            vs.append(row)
        for r0, r1 in zip(vs, vs[1:]):
            for i in range(nx):
                bm.faces.new((r0[i], r0[i + 1], r1[i + 1], r1[i]))
    k = 0
    for sc_ in CFG["scaffolds"]:                                              # a drop cloth under each scaffold, where it clears the walking lines
        x0, x1, z0, z1 = sc_[:4]
        zz0, zz1 = (z0 - 0.1, min(z1 + 0.6, -3.3)) if z0 < 0 else (max(z0 - 0.6, 3.3), z1 + 0.1)
        if zz1 - zz0 < 0.6 or not clear_of(x0 + 0.2, x1 - 0.2, zz0, zz1, ko[1:]):
            zz0, zz1 = (z0, z0 + 0.8) if z0 < 0 else (z1 - 0.8, z1)
        if not clear_of(x0 + 0.2, x1 - 0.2, zz0, zz1, ko[1:]):
            continue
        ob = part(f"decor_DropCloth_{k}", "Cloth_Sheet", lambda bm: cloth_flat(bm, x0 + 0.2, x1 - 0.2, zz0, zz1, 0.004), smooth=True, keep_normals=True)
        orient_faces(ob, (0, 1, 0))
        k += 1
    # paint tins, a plasterboard stack, cement bags and a coiled cable by the scaffolds and the boarded bay
    sc_ = CFG["scaffolds"][0]
    x0, x1, z0, z1 = sc_[:4]
    zs = z0 + 0.4 if z0 < -1 else z1 - 0.4
    tins = [(x0 + 0.5, zs), (x0 + 0.85, zs + 0.1), (x1 - 0.6, zs - 0.05)]
    part("decor_paint_tins", "Metal_Steel", lambda bm: [cyl(bm, (x, 0.005, z), (x, 0.195, z), 0.085, 0.085, 16) for x, z in tins], smooth=True)
    side, bx = TH["boarded"][0]
    zc = ZC[side]
    zi = zc + (1.0 if side == "N" else -1.0)
    zb0, zb1 = sorted((zc + (0.25 if side == "N" else -0.25), zi + (0.4 if side == "N" else -0.4)))
    if clear_of(bx - 1.6, bx + 1.0, zb0, zb1, ko[1:]):
        part("decor_plasterboard", "Clutter_Paint", lambda bm: cube(bm, (bx - 1.6, 0.0, zb0), (bx + 1.0, 0.13, zb1)))

    def bags(bm):
        for j in range(4):
            x = bx + 1.2 + (j % 2) * 0.62
            z = zc + (0.3 + (j // 2) * 0.45) * (1 if side == "N" else -1)
            cube(bm, (x, 0.0, min(z, z + 0.4 * (1 if side == "N" else -1))), (x + 0.58, 0.12, max(z, z + 0.4 * (1 if side == "N" else -1))))
    part("decor_cement_bags", "Cloth_Sheet", bags)

    def cable(bm):
        lamp, _ = SCAF_LAMPS[0]
        zw = -WZ + 0.05 if lamp[2] < 0 else WZ - 0.05
        sx = 1 if lamp[0] < 0 else -1                                             # toward the wing's middle, to a socket on the long wall
        pts = [lamp, (lamp[0] - 0.1, 2.0, lamp[2]), (lamp[0] - 0.2, 0.012, lamp[2] + (0.3 if lamp[2] < 0 else -0.3)),
               (lamp[0] + sx * 2.5, 0.012, zw + (0.2 if zw < 0 else -0.2)), (lamp[0] + sx * 5.5, 0.3, zw)]
        for p, q in zip(pts, pts[1:]):
            cyl(bm, p, q, 0.009, 0.009, 6)
    part("decor_cable", "Metal_Dark", cable)


# ---------------------------------------------------------------- doors (their own objects, origin at the hinge, the greybox's properties)
def leaf_kind(d):
    k = d["props"].get("kind", "")
    if "glass" in k or "shop doors" in k:
        return "glass"
    if "staff" in k:
        return "staff"
    if "restroom" in k:
        return "restroom"
    if "site" in k:
        return "site"
    return "unmarked"


def leaf_mesh(w, h, uvr, edge_uv, knob=None):
    """A door leaf in its own frame: x from the hinge along the leaf (0..w), y across (-0.025..0.025), z up; both faces show the picture."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    t = 0.025
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, 0, h / 2)) @ Matrix.Diagonal((w, 2 * t, h, 1)))
    u0, v0, u1, v1 = uvr
    for f in bm.faces:
        f.normal_update()
        if abs(f.normal.y) > 0.9:
            for lp in f.loops:
                x, z = lp.vert.co.x, lp.vert.co.z
                s = x / w if f.normal.y < 0 else 1 - x / w
                lp[uvl].uv = (u0 + (u1 - u0) * s, v0 + (v1 - v0) * z / h)
        else:
            for lp in f.loops:
                lp[uvl].uv = edge_uv
    if knob:
        old = set(bm.faces)
        kx, kz, kind = knob
        for sgn in (-1, 1):
            if kind == "bar":
                bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.016, radius2=0.016, depth=w * 0.65,
                                      matrix=Matrix.Translation((w * 0.5, sgn * (t + 0.05), kz)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
                for xx in (w * 0.2, w * 0.8):
                    bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.01, radius2=0.01, depth=0.05,
                                          matrix=Matrix.Translation((xx, sgn * (t + 0.025), kz)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
            else:
                bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.012, radius2=0.012, depth=0.12,
                                      matrix=Matrix.Translation((kx - 0.05, sgn * (t + 0.04), kz)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
                bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.01, radius2=0.01, depth=0.04,
                                      matrix=Matrix.Translation((kx, sgn * (t + 0.02), kz)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
        for f in bm.faces:
            if f not in old:
                for lp in f.loops:
                    lp[uvl].uv = (DOOR_CELLS["glass"] * 400 / 2048 + 0.003, 0.97)
    return bm


def build_door_leaves():
    for d in GB.doors:
        p = d["props"]
        w, h = p["width"], p["height"]
        kind = leaf_kind(d)
        uvr = door_uv(kind)
        bm = leaf_mesh(w, h, uvr, (uvr[0] + 0.002, 0.5), knob=(w * 0.5, 1.05, "bar") if kind == "glass" else (w - 0.09, 1.0, "lever"))
        for f in bm.faces:
            f.smooth = False
        me = bpy.data.meshes.new(d["name"])
        bm.to_mesh(me)
        bm.free()
        me.materials.append(MATS["Door_Leaves"])
        ob = bpy.data.objects.new(d["name"], me)
        ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
        for k, v in p.items():
            ob[k] = v
        DOORS_C.objects.link(ob)


# ---------------------------------------------------------------- the layout objects (the greybox's names, turned), and turning the art
def build_layout():
    for b in GB.boxes:
        if b.get("zone"):
            continue
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


def turn_art():
    """Turn everything built in the wing's own frame into the scene's frame (the greybox's turn), vertices only: identity transforms stay."""
    if abs(TURN) < 1e-9:
        return
    for ob in ART.objects:
        ob.data.transform(ROT)


# ---------------------------------------------------------------- lights, world, light sets
SUN_W = 6.0                    # the sun through the skylight (W/m2)
SUN_DIR = (0.42, -0.78, -0.46) # where its light travels (the mall's axes; entrance's): from high in the south-west
SKY_STRENGTH = 4.0             # the sky, seen only through the skylight
DOWN_W = 260.0                 # each working downlight (6 m up)
WORK_W = 300.0                 # the scaffold's work lamp
EMERG_W = 180.0                # each emergency head
EXIT_W = 2.0
BULB_W = 0.0                   # the bulbs glow through their Lamp_Emit (Cycles lights with emission); no extra lamps
POSTER_W = 6.0                 # each poster case's strip light
PANE_GLOW = 6.0


def add_lights():
    cols = {}
    for name in ("Lights_Day", "Lights_Night", "Lights_Always"):
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        cols[name] = c

    def light(coll, name, kind, pos, energy, color, size, aim=None, cone=None):
        d = bpy.data.lights.new(name, kind)
        d.energy, d.color = energy, color
        d.shadow_soft_size = size
        ob = bpy.data.objects.new(name, d)
        ob.location = BW(pos)
        if aim is not None:
            ob.rotation_euler = B(W(aim)).to_track_quat("-Z", "Y").to_euler()
        if cone:
            d.spot_size, d.spot_blend = math.radians(cone[0]), cone[1]
        cols[coll].objects.link(ob)
        return ob, d

    d = bpy.data.lights.new("Sun", "SUN")
    d.energy, d.color, d.angle = SUN_W, (1.0, 0.95, 0.86), math.radians(1.5)
    ob = bpy.data.objects.new("Sun", d)
    ob.location = (0, 0, 30)
    ob.rotation_euler = B(SUN_DIR).to_track_quat("-Z", "Y").to_euler()           # the mall's sun: the same in every wing
    cols["Lights_Day"].objects.link(ob)
    for i, (p, on) in enumerate(DOWN):
        if on:
            light("Lights_Day", f"Down_{i}", "SPOT", (p[0], WH - 0.05, p[2]), DOWN_W, (1.0, 0.88, 0.72), 0.06, aim=(0, -1, 0), cone=(115, 0.6))
    for i, (p, dv) in enumerate(SCAF_LAMPS):
        light("Lights_Day", f"Work_{i}", "SPOT", tuple(Vector(p) + Vector(dv) * 0.07), WORK_W, (1.0, 0.86, 0.66), 0.08, aim=dv, cone=(80, 0.5))
    for i, (p, dv) in enumerate(EMERG):
        light("Lights_Night", f"Emergency_{i}", "SPOT", tuple(Vector(p) + Vector(dv) * 0.045), EMERG_W, (0.86, 0.93, 1.0), 0.03, aim=dv, cone=(75, 0.45))
    for i, (p, nn) in enumerate(EXITS):
        ob, d = light("Lights_Always", f"Exit_{i}", "AREA", p, EXIT_W, (0.3, 1.0, 0.45), 0.0, aim=nn)
        d.shape, d.size, d.size_y = "RECTANGLE", 0.44, 0.16


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("Sky")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.58, 0.66, 0.80, 1)
    bg.inputs["Strength"].default_value = SKY_STRENGTH


def set_emit(mname, strength):
    m = bpy.data.materials.get(mname)
    if m:
        m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = strength


PANE_MAT = "Skylight_Glass"


def apply_light_set(name):
    """day: the sun, the sky and the working lamps (Lamp_Emit on, Emergency_Emit off); night: the emergency heads alone (the mall locked);
    export: both toggled materials at the strength the page switches on and off (entrance's)."""
    day = name == "day"
    for c, on in (("Lights_Day", day), ("Lights_Night", name == "night"), ("Lights_Always", True)):
        if c in bpy.data.collections:
            bpy.data.collections[c].hide_render = not on
    w = bpy.context.scene.world
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = SKY_STRENGTH if day else 0.0
    set_emit("Lamp_Emit", LAMP_EMIT if name in ("day", "export") else 0.0)
    set_emit("Emergency_Emit", EMERG_EMIT if name in ("night", "export") else 0.0)
    set_emit(PANE_MAT, {"day": PANE_GLOW, "night": PANE_GLOW * 0.01}.get(name, 0.0))


def arrive():
    e = next(e for e in GB.empties if e["name"] == "Arrive_entrance")
    return e["pos"], e["face"]


def ensure_marker():
    st = bpy.data.collections["Standins"]
    ob = bpy.data.objects.get("standin_arrival_marker")
    if ob is None:
        me = bpy.data.meshes.new("standin_arrival_marker")
        bm = bmesh.new()
        a, _ = arrive()
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
    a, _ = arrive()
    want = [a[0], a[1] + 0.1, a[2]]
    print(f"AXES glTF centre {tuple(round(v, 3) for v in centre)}, game point {tuple(want)}")
    assert all(abs(centre[i] - want[i]) < 1e-4 for i in range(3)), "the exporter's axes disagree with (x, -z, y)"
    print("AXES PASS: game (x, y, z) = Blender (x, -z, y) = glTF (x, y, z)")
    os.remove(path)


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
    for lst in (DOWN, EMERG, EXITS, BULBS, SCAF_LAMPS, SKY_BOARDS):
        lst.clear()
    sc = bpy.context.scene
    ART, STANDIN, DOORS_C, LAYOUT_C = (bpy.data.collections.new(n) for n in ("Art", "Standins", "Doors", "Layout"))
    for c in (ART, STANDIN, DOORS_C, LAYOUT_C):
        sc.collection.children.link(c)
    make_materials(make_generated())
    build_floor()
    build_walls()
    build_ceiling()
    build_wall_trim()
    build_decals()
    build_skylight()
    build_downlights()
    build_shopfronts()
    build_door_bays()
    build_west_end()
    build_east_end()
    build_scaffolds()
    build_sheeted()
    if SCENE == "wing_cinema":
        build_poster_row()
    build_notices()
    build_hanging_signs()
    build_emergency()
    build_clutter()
    turn_art()
    build_door_leaves()
    build_layout()
    add_lights()
    setup_world()
    apply_light_set("day")
    ensure_marker()
    LAYOUT_C.hide_render = True
    for o in ART.objects:
        if o.data.materials and o.data.materials[0].name == PANE_MAT:
            for attr in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
                setattr(o, attr, False)
    tris = sum(len(p.vertices) - 2 for o in ART.objects for p in o.data.polygons)
    print(f"ART {len(ART.objects)} objects, about {tris} triangles; {len(DOWN)} downlights, {len(EMERG)} emergency heads")


# ---------------------------------------------------------------- layout file and the layout check
def stage_layout():
    import export_scene
    export_scene.write(SCENE, ROOT / f"world/{SCENE}.json")


def stage_check():
    import check_layout
    code = check_layout.main(["--scene", SCENE, "--collection", "Art"])
    print("CHECK_LAYOUT exit", code)
    # the mannequins' places and every link's two points: no solid art within 0.45 m that reaches below head height, no clutter on them
    parts = check_layout.blender_parts("Art")
    world = json.loads((ROOT / f"world/{SCENE}.json").read_text())
    pts = [(s["name"], s["position"]) for s in world["spots"] if s["kind"] == "mannequin"]
    pts += [(f"Link_{l['door']}.at", l["at"]) for l in world["links"]] + [(f"Link_{l['door']}.arrive", l["arrive"]) for l in world["links"]]
    stand = [c for c in world["colliders"] if c["max"][1] > 0.2 and c["min"][1] < 0.5 and not c["s"].startswith("Wing_")]

    def on_layout(q):                       # the art of one of the greybox's own solids (a sheeted ride, a pilaster): the layout's, not the dressing's
        return any(c["min"][0] - 0.05 <= q["min"][0] and q["max"][0] <= c["max"][0] + 0.05 and c["min"][2] - 0.05 <= q["min"][2]
                   and q["max"][2] <= c["max"][2] + 0.05 for c in stand)
    bad = 0
    for name, p in pts:
        hit = [q["name"] for q in parts if not on_layout(q) and q["min"][1] < 1.8 and q["max"][1] > 0.02 and q["min"][0] - 0.45 < p[0] < q["max"][0] + 0.45
               and q["min"][2] - 0.45 < p[2] < q["max"][2] + 0.45]
        print(f"{'PASS' if not hit else 'FAIL'}  KEEP   {name} ({p[0]:.2f}, {p[2]:.2f}): " + ("clear within 0.45 m" if not hit else "art " + ", ".join(hit)))
        bad += bool(hit)
    print(f"KEEP {'PASS' if not bad else 'FAIL'}: {len(pts) - bad} of {len(pts)} places clear")
    if code or bad:
        sys.exit(1)


# ---------------------------------------------------------------- bake
SHELL = ["Floor_Terrazzo", "Floor_Border", "Wall_Plaster", "Wall_Upper", "Ceiling_Paint", "Trim_Paint", "Decal_Dust", "Decal_Stain"]
NO_BAKE = ("Lamp_Emit", "Emergency_Emit", "Sign_Exit")
PAGES = [2048, 2048]
NIGHT_OFFSET = 2
UV_SCALE = {"Skylight_Glass": 0.12, "Ceiling_Paint": 0.55, "Decal_Dust": 0.6}
WHITE_CAP = 8.0
HIDE_IN_BAKE = (PANE_MAT,)
SEEN_UP = 2.2
SEEN_DOWN = 0.8
TWO_SIDED = ("Cloth_Sheet", "Hoarding_Ply")
ENV = ((-WX - T - 1e-3, WX + T + 1e-3), (-G.SLAB - 1e-3, WH + 0.2 + 1e-3), (-WZ - T - 1e-3, WZ + T + 1e-3))


def _inside(p, b, e=1e-4):
    return all(b["min"][i] + e < p[i] < b["max"][i] - e for i in range(3))


def cull(bm, mname, oname):
    """Drop the faces nobody sees, judged in the wing's own frame. Shell pieces (floor, walls, ceiling): a face is kept if the point 1 cm in front
    of it lies in the room or in an opening (a door's or the skylight's reveal), and dropped if that point is inside another shell box or outside
    the shell (the outer skin, the floor's sides and underside, the joints between wall pieces). Everything else: faces flat against a wall, the
    floor or the ceiling facing into it, faces looking up from above SEEN_UP or down from below SEEN_DOWN (two-sided sheets and boards aside)."""
    e = 2e-3
    bad = []
    shell = oname.startswith(("Wall_", "Floor_", "Ceiling_"))
    for f in bm.faces:
        cw, nw = f.calc_center_median(), f.normal
        gx, gy, gz = L((cw.x, cw.z, -cw.y))
        nx, ny, nz = L((nw.x, nw.z, -nw.y))
        if shell:
            q = (gx + nx * 0.01, gy + ny * 0.01, gz + nz * 0.01)
            in_sky = abs(q[0]) < SKX and abs(q[2]) < SKZ and q[1] > WH - 0.01         # the skylight's opening is cut in the art only
            out = not all(ENV[i][0] < q[i] < ENV[i][1] for i in range(3)) or (not in_sky and any(_inside(q, b) for b in SHELL_BOXES))
            out = out or (oname.startswith("Wall_") and covered(gx, gy, gz))
        else:
            out = (nx < -0.9 and gx <= -WX + e) or (nx > 0.9 and gx >= WX - e) or (nz < -0.9 and gz <= -WZ + e) or (nz > 0.9 and gz >= WZ - e) \
                or (ny < -0.9 and gy <= e) or (ny > 0.9 and abs(gy - WH) <= e)
            if mname not in TWO_SIDED and not oname.startswith(("Skylight_", "Hanging_")):
                out = out or (ny > 0.5 and gy > SEEN_UP) or (ny < -0.5 and gy < SEEN_DOWN)
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
    """One atlas for `objs` (entrance's): smart-project islands at equal texel density (UV_SCALE shrinks a few), packed with MARGIN_PX."""
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
        us = np.array([x.uv for x in o.data.uv_layers["lightmap"].data])
        if len(us):
            print(f"    uv {o.name}: extent {np.ptp(us[:, 0]):.4f} x {np.ptp(us[:, 1]):.4f}, uv/3d {math.sqrt(uv_area(o, 'lightmap') / max(1e-9, area3d(o))):.5f}")
    for o in objs:
        sc = UV_SCALE.get(o.name)
        if sc:
            d = o.data.uv_layers["lightmap"].data
            us = np.array([x.uv for x in d]) * sc
            d.foreach_set("uv", us.ravel())
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    # Blender's packer now and then leaves most of the page empty (a long thin island stacks the rest in one column): try each island shape
    # and keep the densest packing
    best = None
    for shape in ("CONCAVE", "CONVEX", "AABB"):
        bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / page, shape_method=shape)
        bpy.ops.object.mode_set(mode="OBJECT")
        au_ = sum(uv_area(o, "lightmap") for o in objs)
        print(f"  pack {shape}: {au_:.4f} of the page")
        if best is None or au_ > best[0] * 1.02:
            best = (au_, shape, {o.name: np.array([x.uv for x in o.data.uv_layers["lightmap"].data]) for o in objs})
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        o.data.uv_layers["lightmap"].data.foreach_set("uv", best[2][o.name].ravel())
    print(f"  kept {best[1]}")
    plain = [o for o in objs if o.name not in UV_SCALE]
    a3 = sum(area3d(o) for o in plain)
    au = sum(uv_area(o, "lightmap") for o in plain)
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


def uv_mask(ob, S, grow=2):
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
    groups = [[m for m in SHELL if m in exp], [m for m in exp if m not in SHELL and m not in NO_BAKE]]
    report = {}
    for n, mats in enumerate(groups):
        objs = [exp[m] for m in mats] + (leaves if n == 1 else [])
        print(f"lightmap {n}: {[o.name for o in objs]}")
        S, dens, small = lightmap_uv(objs, PAGES[n])
        mask = uv_mask(exp[PANE_MAT], S) if PANE_MAT in exp and exp[PANE_MAT] in objs else np.zeros((S, S), bool)
        for light_set, idx, samples in (("day", n, SAMPLES), ("night", n + NIGHT_OFFSET, NIGHT_SAMPLES)):
            t0 = time.time()
            rgb = bake_set(n, objs, S, light_set, samples)
            peak = rgb.max(axis=2)
            sel = (peak > 1e-5) & ~mask
            pc = np.percentile(peak[sel], [50, 90, 99, 99.5, 100]) if sel.any() else [1.0] * 5
            print(f"  {light_set} texel percentiles p50 p90 p99 p99.5 max:", [round(float(v), 4) for v in pc])
            Gc, Cc = CURVE[light_set]
            tex = Gc * rgb / (Cc + Gc * rgb)
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
            np.save(stage_work() / f"{SCENE}_{idx}_raw.npy", rgb.astype(np.float16))
            report[idx] = {"map": n, "set": light_set, "size": S, "curve_G_C": [Gc, Cc], "px_per_m": round(dens, 1), "px_per_m_scaled": small,
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


# ---------------------------------------------------------------- brightness: how the page shows the maps (the hotel lobby's shoulder)
# The page draws a baked material unlit, no tone mapping: texture x base colour x texel x intensity / pi. The bake's light L is written with a
# shoulder, texel = G L / (C + G L), and intensity = pi C: the page shows texture x G L where the light is ordinary and rolls off toward texture x C
# in the sun's patch under the skylight or under a lamp, never clipping. CAP lowers one bright material; the skylight's panes are filled flat.
CURVE = {"day": (5.5, 1.3), "night": (7.0, 1.1)}
CAP = {"day": {}, "night": {}}
PANE_DAY, PANE_NIGHT = (0.97, 0.98, 1.0), (0.05, 0.06, 0.08)
PANE_SHOW = {"day": 0.92, "night": 0.05}


def set_intensities():
    rep = json.loads((stage_work() / "lightmaps.json").read_text())
    for idx, r in rep.items():
        idx = int(idx)
        st = r["set"]
        key, kkey = ("lightmap", "lightmap_intensity") if st == "day" else ("lightmap_night", "lightmap_night_intensity")
        for nm in r["materials"]:
            ob = bpy.data.objects.get(nm)
            mats = [bpy.data.materials.get(nm)] if bpy.data.materials.get(nm) else ([s.material for s in ob.material_slots] if ob else [])
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
LAYOUT_PREFIX = ("DoorLeaf_", "Spot_", "Marker_", "Link_", "Arrive_")
SYS_KEEP = ("cycles", "eevee")


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private(keep_layout=True):
    """The .blend, the GLB and the stills are public: strip other add-ons' custom properties, make image paths relative, clear the operators'
    remembered paths, turn every stamp off (the lobby's)."""
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
    stash = {o.name: {k: o[k] for k in o.keys()} for o in leaves}
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
    """A camera at the wing-frame point loc looking at target (both turned into the scene's frame)."""
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
    ob.location = BW(loc)
    if target is not None:
        ob.rotation_euler = (BW(target) - BW(loc)).to_track_quat("-Z", "Y").to_euler()
    else:
        ob.rotation_euler = (0, 0, math.radians(TURN))
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


DETAIL = {   # (camera, target, fov) in the wing's own frame
    "wing_books": [((-3.6, 1.5, -1.6), (-8.6, 1.9, -7.0), 62.0), ((3.0, 1.55, 2.2), (8.0, 2.2, 7.0), 66.0)],
    "wing_cinema": [((-5.2, 1.5, 0.6), (-12.4, 1.3, 6.2), 64.0), ((-4.6, 1.55, 0.8), (-8.0, 2.0, -7.0), 62.0)],
    "wing_entertainment": [((-10.4, 1.5, 1.2), (-16.0, 2.0, 7.0), 64.0), ((3.6, 1.55, 1.8), (0.0, 2.3, -7.0), 64.0)],
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
    a, f = arrive()
    al = L(a)
    fl = L((f[0], 0.0, f[1]))
    det = DETAIL[SCENE]
    shots = {
        "1_arrival": look_cam("arrival", (al[0], 1.6, al[2]), (al[0] + fl[0] * 3, 1.6, al[2] + fl[2] * 3), 75.0),
        "2_wide": look_cam("wide", (WX - 1.6, 2.0, 5.6), (-6.0, 2.0, -2.2), 80.0),
        "3_detail": look_cam("detail", *det[0]),
        "4_more": look_cam("more", *det[1]),
    }
    plan = look_cam("plan", (0, WH + 10, 0), None, ortho=2 * WX + 1.2)
    arts = list(bpy.data.collections["Art"].objects) + list(bpy.data.collections["Doors"].objects)
    todo = [(k, v, (1920, 1080)) for k, v in shots.items()] + [("5_plan", plan, (1920, 760))]
    suffix = "" if light_set == "day" else "_" + light_set
    for key, cam, (w, h) in todo:
        if which not in ("all", key) and not (which == "review" and key in ("1_arrival", "2_wide", "3_detail")):
            continue
        sc.camera = cam
        sc.view_settings.exposure = expo + (0.8 if key == "5_plan" else 0.0)
        for o in arts:
            o.visible_camera = True
        for o in {"5_plan": [o for o in arts if o.name.startswith(("Ceiling_", "Skylight_", "Downlight_", "Hanging_", "Marquee_"))]}.get(key, []):
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


def stage_relayout():
    """Rebuild only the Layout collection (the COL_ boxes and the empties) from the greybox model in a saved, baked scene: for a change to the
    greybox's layout that leaves the art as it is (no rebake)."""
    global LAYOUT_C
    LAYOUT_C = bpy.data.collections["Layout"]
    for o in list(LAYOUT_C.objects):
        me = o.data if o.type == "MESH" else None
        bpy.data.objects.remove(o)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    build_layout()
    LAYOUT_C.hide_render = True
    save_blend()


if __name__ == "__main__":
    ST = set(STAGE.split(","))
    if ST & {"art", "all"}:
        build_all()
        save_blend()
    if "relayout" in ST:
        stage_relayout()
    if ST & {"layout", "art", "all", "relayout"}:
        stage_layout()
    if ST & {"check", "all"}:
        stage_check()
    if ST & {"bake", "all"}:
        stage_bake()
    if ST & {"export", "all"}:
        stage_export()
    if ST & {"axes", "all"}:
        stage_axes()
    if ST & {"render", "all"}:
        stage_render()
