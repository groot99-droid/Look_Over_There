"""Builds the Farway mall atrium (`entrance`) in Blender, lights and bakes it twice (day and the emergency set), and exports world/entrance.glb
(docs/BLENDER.md, "6. entrance (the mall atrium)").

Re-runnable, from the repo root:

    blender -b --python tools/blender/build_entrance.py                       (every stage, in one run)
    blender -b --python tools/blender/build_entrance.py -- --stage art        (build the art, save blender/scenes/entrance.blend)
    blender -b blender/scenes/entrance.blend --python tools/blender/build_entrance.py -- --stage bake [--samples 256] [--night-samples 384] [--device cpu]
    blender -b blender/scenes/entrance.blend --python tools/blender/build_entrance.py -- --stage export
    blender -b blender/scenes/entrance.blend --python tools/blender/build_entrance.py -- --stage axes     (the marker-cube axes check)
    blender -b blender/scenes/entrance.blend --python tools/blender/build_entrance.py -- --stage render [--render-samples 128] [--only 1_arrival] [--set night]

Stages: art (geometry, materials, lights, stand-ins) -> bake (merge by material, lightmap UV, two Cycles bakes per map: the day set and the
emergency set; OIDN denoise; 8-bit PNGs in the work folder) -> export (GLB; tools/blender/pack_scene.py then makes the WebP lightmaps and the
WebP textures) -> render (the review stills).

The structure is the apartment pilot's (tools/blender/build_apartment.py) and the galleries' (scrub_private, strip_jpeg_comments, fixed lightmap pages).
No coordinate of the layout is typed in here: the atrium, the colliders, the fountain, the benches, the door, the arrival point and the shop names come from
blender/layout/entrance.json (node tools/blender/dump_layout.mjs entrance). A game point (x, y, z) is Blender (x, -z, y). What the layout does not name
(the shopfronts' places, the gallery, the skylight, the scaffold) is placed relative to those numbers: the shopfronts follow the blockout's rule (four on
the north wall at x = +-hx/4 and +-(hx - 5), two on each side wall at z = -hz/2 and +hz/3), the skylight sits over the fountain.

The page draws nothing of its own in this scene (docs/BLENDER.md, contract 4: `entrance`: "Nothing"), so the shop names are painted here, and the page adds no lamp:
the bakes light the atrium fully. Day: the sun and the sky through the skylight and the gallery's soffit downlights (`Lamp_Emit`, off while the mall is locked).
Night: the emergency fittings alone (`Emergency_Emit`, on only while the mall is locked), on the same materials as `lightmap_night`.
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
SCENE = "entrance"
LAYOUT = ROOT / f"blender/layout/{SCENE}.json"
TEX = ROOT / f"blender/textures/{SCENE}"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"      # the path the page reads from the material's `lightmap` / `lightmap_night` custom property
MARGIN_PX = 8

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 256, int)
NIGHT_SAMPLES = arg("--night-samples", None, int) or SAMPLES
DEVICE = arg("--device", "auto")
ENGINE = arg("--engine", "CYCLES")

L = json.loads(LAYOUT.read_text())
K = L["constants"]
COLLIDERS = {c["s"]: c for c in L["world"]["colliders"]}
HX, HZ = K["half"]
H = K["h"]
FOUNT = K["fountain"]
BENCHES = K["benches"]
SHOPS = K["shops"]
DOOR = K["door"]["at"]
CEIL_TOP = COLLIDERS["Ceiling_Mall"]["max"][1]
WALL_T = COLLIDERS["Wall_N"]["max"][2] - COLLIDERS["Wall_N"]["min"][2]       # the walls' thickness (0.2)

FX0, FX1 = FOUNT["min"][0], FOUNT["max"][0]
FZ0, FZ1 = FOUNT["min"][2], FOUNT["max"][2]
FH = FOUNT["max"][1]
FCX, FCZ = (FX0 + FX1) / 2, (FZ0 + FZ1) / 2

# what the layout does not name, derived from it
SHOP_W, SHOP_H = 4.8, 3.2                     # a lower shopfront's opening (the blockout's shutter: 4.8 x 3.2)
SIGN_Y0, SIGN_Y1 = 3.30, 3.82                 # the painted fascia sign over each shop
DECK_Y0, DECK_Y1 = 3.95, 4.25                 # the gallery deck: soffit and walking surface
DECK_D = 2.2                                  # how far the gallery deck reaches out from the walls
RAIL_H = 1.05                                 # the balustrade
UP_W, UP_Y0, UP_Y1 = 4.4, DECK_Y1 + 0.05, DECK_Y1 + 2.45      # an upper shopfront (over each lower one)
SKY_X = 6.0                                   # the skylight's opening: x in [-SKY_X, SKY_X], z over the fountain +-6
SKY_Z0, SKY_Z1 = FCZ - 6.0, FCZ + 6.0
LANTERN_UP = 0.8                              # the lantern's glazed upstand over the ceiling slab, then a pitched roof
LANTERN_RIDGE = 1.6                           # the ridge's height over the upstand
ENTRY_W, ENTRY_H, DOOR_LEAF_H = 6.0, 3.6, 2.8 # the glazed entrance in the south wall (a 3.2 m double door, side lights, a transom), centred on door.at's x
BENCH_TOP = BENCHES[0]["max"][1]
KERB_IN = 0.03                                # the fountain's kerb stands this far inside its collider, under the cap's overhang (the floor band reaches it)


def shop_slots():
    """(wall normal, along, name) for the eight lower shops, by the blockout's rule (index.html mallProps)."""
    return [("+z", -(HX - 5), SHOPS[0]), ("+z", -HX / 4, SHOPS[1]), ("+z", HX / 4, SHOPS[2]), ("+z", HX - 5, SHOPS[3]),
            ("+x", -HZ / 2, SHOPS[4]), ("+x", HZ / 3, SHOPS[5]), ("-x", -HZ / 2, SHOPS[6]), ("-x", HZ / 3, SHOPS[7])]


RENOVATION = 3                                 # the shop whose front is a plywood hoarding instead of a shutter ("CLOSED FOR RENOVATION")


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


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, diff=None, img=None, tint=None, emit=None, alpha=None, tile=None):
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
        if img is not None and emit[0] is None:
            pass
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
    """An emissive material showing a picture (the EXIT sign)."""
    m = material(name, color=(0, 0, 0), rough=0.4, tile=tile)
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    uv = nt.nodes["UV Map"]
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = img
    nt.links.new(uv.outputs["UV"], tx.inputs["Vector"])
    nt.links.new(tx.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = strength
    return m


LAMP_EMIT = 10.0          # Lamp_Emit's exported strength (the soffit downlights' lenses, the scaffold's work lamp): on by day, off while locked
EMERG_EMIT = 6.0          # Emergency_Emit's exported strength (the emergency heads): on only while the mall is locked


def make_materials(gen):
    material("Floor_Terrazzo", diff="terrazzo_tiles_diff_1k.jpg", tint=(0.92, 0.88, 0.84), rough=0.4, tile=2.0)
    material("Floor_Border", diff="terrazzo_tiles_diff_1k.jpg", tint=(0.42, 0.38, 0.36), rough=0.4, tile=2.0)
    material("Wall_Plaster", diff="beige_wall_001_diff_1k.jpg", tint=(0.92, 0.88, 0.80), rough=0.9, tile=2.4)
    material("Wall_Upper", diff="beige_wall_001_diff_1k.jpg", tint=(0.80, 0.78, 0.72), rough=0.9, tile=2.4)          # the gallery level, a shade darker
    material("Ceiling_Paint", diff="beige_wall_001_diff_1k.jpg", tint=(0.96, 0.95, 0.92), rough=0.95, tile=3.0)
    material("Deck_Concrete", diff="concrete_floor_02_diff_1k.jpg", tint=(1.0, 0.98, 0.94), rough=0.9, tile=4.5)
    material("Trim_Paint", color=(0.62, 0.60, 0.55), rough=0.55)                        # pilasters, fascia cladding, the door's frame, skirting
    material("Shutter_Metal", diff="painted_metal_shutter_diff_1k.jpg", tint=(0.80, 0.80, 0.80), rough=0.5, metal=0.2, tile=2.0)
    material("Hoarding_Ply", diff="plywood_diff_1k.jpg", tint=(0.95, 0.92, 0.88), rough=0.8, tile=1.2)
    material("Scaffold_Board", diff="plywood_diff_1k.jpg", tint=(0.62, 0.55, 0.45), rough=0.85, tile=0.9)
    material("Fountain_Stone", diff="concrete_floor_02_diff_1k.jpg", tint=(0.78, 0.76, 0.72), rough=0.6, tile=1.6)
    material("Fountain_Basin", diff="concrete_floor_02_diff_1k.jpg", tint=(0.55, 0.52, 0.47), rough=0.9, tile=1.4)
    material("Bench_Wood", diff="dark_wood_diff_1k.jpg", tint=(0.95, 0.85, 0.75), rough=0.6, tile=0.9)
    material("Cloth_Sheet", diff="rough_linen_diff_512.jpg", tint=(0.95, 0.93, 0.88), rough=1.0, tile=0.8)
    material("Metal_Dark", color=(0.05, 0.05, 0.055), rough=0.45, metal=0.7)
    material("Metal_Steel", color=(0.42, 0.43, 0.44), rough=0.45, metal=0.85)          # scaffold tubes, balustrade posts and rails, door frames
    material("Plastic_White", color=(0.70, 0.70, 0.67), rough=0.5)                      # the emergency fittings' bodies
    material("Clutter_Paint", color=(0.55, 0.50, 0.42), rough=0.7)                      # cement bags, plasterboard, a bucket
    material("Glass_Whitewash", img=gen["whitewash"], rough=0.3, tile=3.0)             # the entrance's glass, whitewashed for the works: opaque, baked
    material("Sign_Paint", img=gen["signs"], rough=0.7, tile=1.0)                      # the painted shop signs (one atlas, a row each)
    material("Directory_Board", img=gen["directory"], rough=0.6, tile=1.0)
    material("Skylight_Glass", img=gen["skyglass"], rough=0.2, tile=1.5)                # the lantern's panes: dirty wired glass, its lightmap is the sky (see stage_bake)
    material("Decal_Dust", img=gen["dust"], alpha="texture", rough=1.0, tile=1.0)       # soft dust drifts along the walls (alpha decals on the floor)
    material("Decal_Stain", img=gen["stain"], alpha="texture", rough=1.0, tile=1.0)     # the dried puddle under the skylight
    material("Lamp_Emit", color=(1.0, 0.92, 0.80), rough=0.4, emit=((1.0, 0.90, 0.74), LAMP_EMIT))
    material("Emergency_Emit", color=(0.9, 0.95, 1.0), rough=0.3, emit=((0.85, 0.93, 1.0), EMERG_EMIT))
    emissive_image("Sign_Exit", gen["exit"], 3.0)
    material("Glass_Clear", color=(0.75, 0.85, 0.85), rough=0.05, alpha=0.18)          # the balustrade's panels: transparent, never baked


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


def disc(bm, p, r, seg=16):
    """A flat disc facing down (a lamp's rim or lens on a soffit)."""
    vs = [bm.verts.new(B((p[0] + r * math.cos(2 * math.pi * k / seg), p[1], p[2] - r * math.sin(2 * math.pi * k / seg)))) for k in range(seg)]
    f = bm.faces.new(vs)
    f.normal_update()                      # a new face has no normal until it is computed
    if f.normal.z > 0:                     # Blender z is game y: it must face down
        f.normal_flip()


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


def finish(name, bm, mat, coll, smooth=False, tile=None, sharp_deg=35, keep_uv=False, keep_normals=False):
    for e in bm.edges:
        if smooth and len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) < math.radians(sharp_deg)
        else:
            e.smooth = not (len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(1))
    for f in bm.faces:
        f.smooth = smooth
    if not (keep_uv or keep_normals):                 # an open sheet or a lone panel keeps the winding it was built with (it faces the room)
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


def part(name, mat, build, smooth=False, tile=None, coll=None, keep_normals=False):
    bm = bmesh.new()
    build(bm)
    return finish(name, bm, mat, coll or ART, smooth, tile, keep_normals=keep_normals)


def dedupe_inner(bm):
    """After building a slab from touching cells: weld the cells and drop the faces two cells share (they are inside the slab)."""
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
    """A box from lo..hi along `axis` ("x" or "z"), y0..y1 high, c0..c1 across, with rectangular holes [(a0, a1, ya, yb)] cut right through it."""
    cuts_a = sorted({lo, hi} | {h[i] for h in holes for i in (0, 1) if lo < h[i] < hi})
    cuts_y = sorted({y0, y1} | {h[i] for h in holes for i in (2, 3) if y0 < h[i] < y1})
    bm.verts.ensure_lookup_table()
    for a0, a1 in zip(cuts_a, cuts_a[1:]):
        for ya, yb in zip(cuts_y, cuts_y[1:]):
            am, ym = (a0 + a1) / 2, (ya + yb) / 2
            if any(h[0] < am < h[1] and h[2] < ym < h[3] for h in holes):
                continue
            if axis == "x":
                cube(bm, (a0, ya, c0), (a1, yb, c1))
            else:
                cube(bm, (c0, ya, a0), (c1, yb, a1))
    bm.verts.index_update()
    dedupe_inner(bm)


# wall frames: a wall is named by its inward normal; ALONG is the game axis that runs along it, its inner face lies at OUT
WALLS = {"+x": ("z", -HX), "-x": ("z", HX), "+z": ("x", -HZ), "-z": ("x", HZ)}
WALL_OF = {"Wall_W": "+x", "Wall_E": "-x", "Wall_N": "+z", "Wall_S": "-z"}


def on_wall(normal, a, y, d):
    """A game point on the wall whose inward normal is `normal`: `a` along the wall, height `y`, `d` metres into the room (negative: into the wall)."""
    ax, face = WALLS[normal]
    sign = 1 if normal[0] == "+" else -1
    off = face + sign * d
    return (off, y, a) if ax == "z" else (a, y, off)


def wall_box(bm, normal, a0, a1, y0, y1, d0, d1):
    """A box against a wall: from a0 to a1 along it, y0 to y1 high, d0 to d1 into the room."""
    p, q = on_wall(normal, a0, y0, d0), on_wall(normal, a1, y1, d1)
    cube(bm, [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)])


RIGHT = {"+x": (0, 0, -1), "-x": (0, 0, 1), "+z": (1, 0, 0), "-z": (-1, 0, 0)}   # looking at a surface whose normal is +x, -x, ...: the game direction of your right hand


def panel(name, mat, centre, normal, w, h, uv=(0, 0, 1, 1), coll=None):
    """A flat quad facing `normal` (a game axis such as "+x"), w wide, h tall, its UV the rectangle `uv` (u0, v0, u1, v1) with the picture upright."""
    r = Vector(RIGHT[normal])
    up = Vector((0, 1, 0))
    c = Vector(centre)
    pts = [c - r * w / 2 - up * h / 2, c + r * w / 2 - up * h / 2, c + r * w / 2 + up * h / 2, c - r * w / 2 + up * h / 2]
    bm = bmesh.new()
    quad(bm, *[tuple(p) for p in pts])
    bm.faces.ensure_lookup_table()
    uvl = bm.loops.layers.uv.new("UVMap")
    u0, v0, u1, v1 = uv
    for lp, (s, t) in zip(bm.faces[0].loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = (u0 + (u1 - u0) * s, v0 + (v1 - v0) * t)
    return finish(name, bm, mat, coll or ART, keep_uv=True)


def flat_decal(bm, x0, x1, z0, z1, y=0.002):
    """A quad on the floor facing up, UV 0..1 over its rectangle."""
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    f = quad(bm, (x0, y, z1), (x1, y, z1), (x1, y, z0), (x0, y, z0))
    for lp, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = uv


# ---------------------------------------------------------------- the shell: floor, walls with their shop openings, ceiling with the skylight's opening
def openings():
    """{wall normal: [(a0, a1, y0, y1)]}: the lower shopfronts, the upper ones over them, and the entrance in the south wall."""
    out = {n: [] for n in WALLS}
    for n, a, _ in shop_slots():
        out[n].append((a - SHOP_W / 2, a + SHOP_W / 2, 0.0, SHOP_H))
        out[n].append((a - UP_W / 2, a + UP_W / 2, UP_Y0, UP_Y1))
    out["-z"].append((DOOR[0] - ENTRY_W / 2, DOOR[0] + ENTRY_W / 2, 0.0, ENTRY_H))
    return out


def build_shell():
    """Floor, walls and ceiling from the collision file's boxes (Floor_*, Ceiling_*, Wall_*), so art and colliders agree. The floor is a terrazzo field in a
    dark border; each wall is plaster below the gallery and worn plaster above it, with the shop openings cut through; the ceiling has the skylight's opening."""
    f = COLLIDERS["Floor_Mall"]
    mn, mx = f["min"], f["max"]
    b = 0.6                                                                                     # the dark border along the walls
    rb = 0.45                                                                                   # and round the fountain
    part("Floor_Mall", "Floor_Terrazzo", lambda bm: holed_box_xz(bm, (-HX + b, HX - b), (-HZ + b, HZ - b), mn[1], mx[1], [(FX0 - rb, FX1 + rb, FZ0 - rb, FZ1 + rb)]))

    def border(bm):
        cube(bm, (mn[0], mn[1], mn[2]), (mx[0], mx[1], -HZ + b))
        cube(bm, (mn[0], mn[1], HZ - b), (mx[0], mx[1], mx[2]))
        cube(bm, (mn[0], mn[1], -HZ + b), (-HX + b, mx[1], HZ - b))
        cube(bm, (HX - b, mn[1], -HZ + b), (mx[0], mx[1], HZ - b))
        k = KERB_IN                                                                               # the band runs in under the cap's overhang to the kerb's foot
        holed_box_xz(bm, (FX0 - rb, FX1 + rb), (FZ0 - rb, FZ1 + rb), mn[1], mx[1], [(FX0 + k, FX1 - k, FZ0 + k, FZ1 - k)])   # the band round the fountain (inside the kerb: its own basin)
    part("Floor_Band", "Floor_Border", border)                                               # (no floor under the fountain: its basin closes it)

    ops = openings()
    for s, c in COLLIDERS.items():
        if not s.startswith("Wall_"):
            continue
        n = WALL_OF[s]
        ax, _ = WALLS[n]
        mn, mx = c["min"], c["max"]
        i0, i1 = (0, 2) if ax == "x" else (2, 0)
        lo, hi, c0, c1 = mn[i0], mx[i0], mn[i1], mx[i1]
        low = [(a0, a1, y0, min(y1, DECK_Y0)) for a0, a1, y0, y1 in ops[n] if y0 < DECK_Y0]
        up = [(a0, a1, max(y0, DECK_Y0), y1) for a0, a1, y0, y1 in ops[n] if y1 > DECK_Y0]
        part(s, "Wall_Plaster", lambda bm: holed_box(bm, ax, lo, hi, mn[1], DECK_Y0, c0, c1, low))
        part(s + "_Upper", "Wall_Upper", lambda bm: holed_box(bm, ax, lo, hi, DECK_Y0, mx[1], c0, c1, up))

    c = COLLIDERS["Ceiling_Mall"]
    mn, mx = c["min"], c["max"]
    part("Ceiling_Mall", "Ceiling_Paint", lambda bm: holed_box_xz(bm, (mn[0], mx[0]), (mn[2], mx[2]), mn[1], mx[1], [(-SKY_X, SKY_X, SKY_Z0, SKY_Z1)]))


def holed_box_xz(bm, xr, zr, y0, y1, holes):
    """A horizontal slab over x in xr, z in zr, y0..y1, with rectangular holes [(x0, x1, z0, z1)] cut through it."""
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


def build_floor_decals():
    """Dust and grit gathered round the fountain's foot, and the dried puddle under the skylight (alpha decals 3 to 4 mm over the floor)."""
    e = 2.2
    part("Decal_FountainDust", "Decal_Dust", lambda bm: flat_decal(bm, FCX - (FX1 - FX0) / 2 - e, FCX + (FX1 - FX0) / 2 + e, FCZ - (FZ1 - FZ0) / 2 - e, FCZ + (FZ1 - FZ0) / 2 + e, 0.003),
         keep_normals=True)
    finish_uv_keep("Decal_FountainDust")
    part("Decal_Puddle", "Decal_Stain", lambda bm: flat_decal(bm, -SKY_X + 0.5, FX0 - 0.2, SKY_Z0 + 1.0, SKY_Z0 + 4.8, 0.004), keep_normals=True)
    finish_uv_keep("Decal_Puddle")


def finish_uv_keep(name):
    """finish() box-projects UV0; a decal wants the 0..1 it was built with: rebuild it from the quad's corners."""
    me = bpy.data.objects[name].data
    uvl = me.uv_layers["UVMap"].data
    for p in me.polygons:
        for k, li in enumerate(p.loop_indices):
            uvl[li].uv = ((0, 0), (1, 0), (1, 1), (0, 1))[k % 4]


# ---------------------------------------------------------------- shopfronts
INWARD = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}


def corrugated(bm, normal, a0, a1, y0, y1, d, depth=0.012, pitch=0.075, step=0.025):
    """A roller shutter's curtain: a strip from a0 to a1 along a wall, y0..y1, at `d` from the wall's face, rippled in and out by `depth` every `pitch`.
    Faces are wound toward the room afterwards (orient_faces)."""
    rows = int(math.ceil((y1 - y0) / step))
    vs = []
    for i in range(rows + 1):
        y = y0 + (y1 - y0) * i / rows
        off = d + depth * 0.5 * (1 - math.cos(2 * math.pi * (y - y0) / pitch))
        vs.append((bm.verts.new(B(on_wall(normal, a0, y, off))), bm.verts.new(B(on_wall(normal, a1, y, off)))))
    for (p0, p1), (q0, q1) in zip(vs, vs[1:]):
        bm.faces.new((p0, p1, q1, q0))


def build_shopfronts():
    """Eight lower shopfronts: the opening cut through the wall, a painted steel shutter set back in it (rolled down and padlocked), its box and guides,
    a pilaster either side and the painted fascia sign over it; one ("CLOSED FOR RENOVATION") is boarded with plywood instead. Over each, on the gallery
    level, an upper front: half of them shuttered, half boarded."""
    sh = SIGN_ATLAS_ROWS
    for i, (n, a, name) in enumerate(shop_slots()):
        a0, a1 = a - SHOP_W / 2, a + SHOP_W / 2
        back = -WALL_T + 0.04                                                                  # 4 cm in front of the wall's outer face
        if i == RENOVATION:
            def ply(bm):
                w = SHOP_W / 4
                for k in range(4):
                    wall_box(bm, n, a0 + k * w + 0.004, a0 + (k + 1) * w - 0.004, 0.0, SHOP_H - 0.004, -0.06, -0.04)
            part(f"Shop_{i}_Hoarding", "Hoarding_Ply", ply)
            part(f"Shop_{i}_HoardingBack", "Metal_Dark", lambda bm: wall_box(bm, n, a0, a1, 0.0, SHOP_H, -0.12, -0.08))   # dark behind the boards' joints (else the outside shows)

            def battens(bm):
                for y in (0.25, SHOP_H / 2, SHOP_H - 0.3):
                    wall_box(bm, n, a0 + 0.05, a1 - 0.05, y - 0.05, y + 0.05, -0.04, -0.015)
            part(f"Shop_{i}_Battens", "Scaffold_Board", battens)
        else:
            orient_faces(part(f"Shop_{i}_Shutter", "Shutter_Metal", lambda bm: corrugated(bm, n, a0, a1, 0.06, SHOP_H - 0.32, back), keep_normals=True), INWARD[n])

            def hw(bm):
                wall_box(bm, n, a0, a1, 0.0, 0.06, back - 0.01, back + 0.03)                    # the bottom rail
                wall_box(bm, n, a0, a1, SHOP_H - 0.34, SHOP_H, back - 0.02, back + 0.16)          # the roller's box
                for s in (a0, a1 - 0.06):
                    wall_box(bm, n, s, s + 0.06, 0.0, SHOP_H - 0.34, back - 0.02, back + 0.05)    # the guides
                c = a + (0.9 if i % 2 else -1.3)
                wall_box(bm, n, c - 0.05, c + 0.05, 0.02, 0.13, back + 0.03, back + 0.07)          # a padlock at the floor
            part(f"Shop_{i}_ShutterGear", "Metal_Dark", hw)

        def pilasters(bm):
            for s in (a0 - 0.30, a1):
                wall_box(bm, n, s, s + 0.30, 0.0, DECK_Y0, 0.0, 0.045)
            wall_box(bm, n, a0 - 0.30, a1 + 0.30, SHOP_H, SIGN_Y0 - 0.02, 0.0, 0.045)            # the head over the opening
        part(f"Shop_{i}_Pilasters", "Trim_Paint", pilasters)
        part(f"Shop_{i}_SignBoard", "Metal_Dark", lambda bm: wall_box(bm, n, a0 - 0.15, a1 + 0.15, SIGN_Y0 - 0.02, SIGN_Y1 + 0.02, 0.0, 0.035))
        r = i
        panel(f"Shop_{i}_Sign", "Sign_Paint", on_wall(n, a, (SIGN_Y0 + SIGN_Y1) / 2, 0.0355), n, SHOP_W + 0.2, SIGN_Y1 - SIGN_Y0,
              uv=(0.0, 1 - (r + 1) / sh, 1.0, 1 - r / sh))

        # the upper front over it, on the gallery level: shuttered (even) or boarded (odd)
        u0, u1 = a - UP_W / 2, a + UP_W / 2
        if i % 2 == 0:
            orient_faces(part(f"Shop_{i}_UpperShutter", "Shutter_Metal", lambda bm: corrugated(bm, n, u0, u1, UP_Y0 + 0.05, UP_Y1 - 0.3, back), keep_normals=True), INWARD[n])
            part(f"Shop_{i}_UpperGear", "Metal_Dark", lambda bm: [wall_box(bm, n, u0, u1, UP_Y1 - 0.32, UP_Y1, back - 0.02, back + 0.16),
                                                                 wall_box(bm, n, u0, u1, UP_Y0, UP_Y0 + 0.06, back - 0.01, back + 0.03)])
        else:
            part(f"Shop_{i}_UpperHoarding", "Hoarding_Ply", lambda bm: [wall_box(bm, n, u0 + k * UP_W / 3 + 0.004, u0 + (k + 1) * UP_W / 3 - 0.004, UP_Y0, UP_Y1, -0.06, -0.04) for k in range(3)])
            part(f"Shop_{i}_UpperHoardingBack", "Metal_Dark", lambda bm: wall_box(bm, n, u0, u1, UP_Y0, UP_Y1, -0.12, -0.08))
        part(f"Shop_{i}_UpperFrame", "Trim_Paint", lambda bm: [wall_box(bm, n, s, s + 0.2, UP_Y0, UP_Y1 + 0.2, 0.0, 0.04) for s in (u0 - 0.2, u1)]
             + [wall_box(bm, n, u0 - 0.2, u1 + 0.2, UP_Y1, UP_Y1 + 0.2, 0.0, 0.04)])


def build_entrance():
    """The glazed entrance in the south wall: an aluminium frame, a double door, side lights and a transom, the glass whitewashed for the works (opaque and
    baked: nothing of the street shows through). The door does not open as a mechanism: the page's prompt at door.at is unchanged."""
    dx = DOOR[0]
    x0, x1 = dx - ENTRY_W / 2, dx + ENTRY_W / 2
    leaf = 1.6
    n = "-z"
    g = -WALL_T / 2                                                                             # the glass line: the middle of the wall
    mull = [x0, dx - leaf, dx, dx + leaf, x1]

    def frame(bm):
        for i, a in enumerate(mull):
            w0, w1 = (a, a + 0.08) if i == 0 else ((a - 0.08, a) if i == len(mull) - 1 else (a - 0.04, a + 0.04))
            wall_box(bm, n, w0, w1, 0.0, ENTRY_H, g - 0.05, g + 0.05)
        wall_box(bm, n, x0, x1, ENTRY_H - 0.08, ENTRY_H, g - 0.05, g + 0.05)                  # the head
        wall_box(bm, n, x0, x1, DOOR_LEAF_H, DOOR_LEAF_H + 0.08, g - 0.05, g + 0.05)          # the transom bar
        wall_box(bm, n, x0, dx - leaf, 0.0, 0.25, g - 0.05, g + 0.05)                        # the side lights' bottom rails
        wall_box(bm, n, dx + leaf, x1, 0.0, 0.25, g - 0.05, g + 0.05)
        for a, b_ in ((dx - leaf, dx), (dx, dx + leaf)):                                        # the leaves' rails
            wall_box(bm, n, a + 0.04, b_ - 0.04, 0.0, 0.18, g - 0.03, g + 0.03)
            wall_box(bm, n, a + 0.04, b_ - 0.04, DOOR_LEAF_H - 0.1, DOOR_LEAF_H, g - 0.03, g + 0.03)
            wall_box(bm, n, a + 0.04, a + 0.1, 0.18, DOOR_LEAF_H - 0.1, g - 0.03, g + 0.03)
            wall_box(bm, n, b_ - 0.1, b_ - 0.04, 0.18, DOOR_LEAF_H - 0.1, g - 0.03, g + 0.03)
        for a in (dx - leaf + 0.15, dx + 0.15):                                                 # push bars on the inside
            wall_box(bm, n, a, a + leaf - 0.3, 1.0, 1.05, g + 0.03, g + 0.09)
    part("Entrance_Frame", "Metal_Steel", frame)

    def glass(bm):
        def pane(a0, a1, y0, y1):
            quad(bm, on_wall(n, a0, y0, g), on_wall(n, a0, y1, g), on_wall(n, a1, y1, g), on_wall(n, a1, y0, g))
        pane(x0 + 0.08, dx - leaf - 0.04, 0.25, DOOR_LEAF_H)
        pane(dx + leaf + 0.04, x1 - 0.08, 0.25, DOOR_LEAF_H)
        pane(dx - leaf + 0.1, dx - 0.1, 0.18, DOOR_LEAF_H - 0.1)
        pane(dx + 0.1, dx + leaf - 0.1, 0.18, DOOR_LEAF_H - 0.1)
        pane(x0 + 0.08, x1 - 0.08, DOOR_LEAF_H + 0.08, ENTRY_H - 0.08)
    orient_faces(part("Entrance_Glass", "Glass_Whitewash", glass, keep_normals=True), INWARD[n])
    part("decor_entrance_mat", "Metal_Dark", lambda bm: cube(bm, (dx - 1.4, 0.0, HZ - 1.3), (dx + 1.4, 0.012, HZ - 0.05)))     # the entrance mat (flat, passable)


def build_directory():
    """The mall directory on the south wall, west of the door: a painted board listing the shops (4 cm proud of the wall)."""
    x = DOOR[0] - ENTRY_W / 2 - 2.6
    part("Directory_Frame", "Metal_Dark", lambda bm: wall_box(bm, "-z", x - 0.65, x + 0.65, 0.85, 2.75, 0.0, 0.04))
    panel("Directory_Face", "Directory_Board", on_wall("-z", x, 1.8, 0.0405), "-z", 1.2, 1.8)


# ---------------------------------------------------------------- the gallery: a cantilevered deck round the walls, its balustrade, brackets and soffit lights
def deck_rects():
    """The gallery deck's plan, as four rectangles that do not overlap: (x0, x1, z0, z1)."""
    d = DECK_D
    return [(-HX, HX, -HZ, -HZ + d), (-HX, HX, HZ - d, HZ), (-HX, -HX + d, -HZ + d, HZ - d), (HX - d, HX, -HZ + d, HZ - d)]


def deck_edges():
    """The deck's inner edges: (start, end) game points at deck level, and the inward normal (into the atrium) of each."""
    d = DECK_D
    x0, x1, z0, z1 = -HX + d, HX - d, -HZ + d, HZ - d
    return [((x0, z0), (x1, z0), (0, 1)), ((x1, z1), (x0, z1), (0, -1)), ((x0, z1), (x0, z0), (1, 0)), ((x1, z0), (x1, z1), (-1, 0))]


SOFFIT = []          # (game point of a downlight's lens, working?)


def build_gallery():
    def deck(bm):
        for x0, x1, z0, z1 in deck_rects():
            cube(bm, (x0, DECK_Y0, z0), (x1, DECK_Y1, z1))
    part("Gallery_Deck", "Deck_Concrete", deck)

    def fascia(bm):
        for (a, b_, nn) in deck_edges():
            ex, ez = nn
            # a cladding band on the deck's edge, 3 cm proud, a little taller than the slab
            if ex == 0:
                xa, xb = min(a[0], b_[0]) - 0.03, max(a[0], b_[0]) + 0.03
                z = a[1]
                cube(bm, (xa, DECK_Y0 - 0.06, min(z, z + ez * 0.03)), (xb, DECK_Y1 + 0.04, max(z, z + ez * 0.03)))
            else:
                za, zb = min(a[1], b_[1]) - 0.03, max(a[1], b_[1]) + 0.03
                x = a[0]
                cube(bm, (min(x, x + ex * 0.03), DECK_Y0 - 0.06, za), (max(x, x + ex * 0.03), DECK_Y1 + 0.04, zb))
    part("Gallery_Fascia", "Trim_Paint", fascia)

    # the balustrade: posts, a handrail and a bottom rail (steel), glass panels between the posts
    posts, rails = [], []
    for (a, b_, nn) in deck_edges():
        A, Bv = Vector((a[0], 0, a[1])), Vector((b_[0], 0, b_[1]))
        ln = (Bv - A).length
        k = max(1, round(ln / 1.6))
        inset = Vector((nn[0], 0, nn[1])) * -0.06
        for i in range(k + 1):
            p = A + (Bv - A) * (i / k) + inset
            posts.append((p.x, p.z))
        rails.append((A + inset, Bv + inset))

    def steel(bm):
        for x, z in posts:
            cyl(bm, (x, DECK_Y1, z), (x, DECK_Y1 + RAIL_H, z), 0.024, 0.024, 8, cap=False)
        for A, Bv in rails:
            cyl(bm, (A.x, DECK_Y1 + RAIL_H + 0.02, A.z), (Bv.x, DECK_Y1 + RAIL_H + 0.02, Bv.z), 0.03, 0.03, 12, cap=False)
            cyl(bm, (A.x, DECK_Y1 + 0.12, A.z), (Bv.x, DECK_Y1 + 0.12, Bv.z), 0.015, 0.015, 8, cap=False)
    part("Gallery_Balustrade", "Metal_Steel", steel, smooth=True)

    def glass(bm):
        for A, Bv in rails:
            quad(bm, (A.x, DECK_Y1 + 0.16, A.z), (Bv.x, DECK_Y1 + 0.16, Bv.z), (Bv.x, DECK_Y1 + RAIL_H - 0.05, Bv.z), (A.x, DECK_Y1 + RAIL_H - 0.05, A.z))
    part("Gallery_Glass", "Glass_Clear", glass, keep_normals=True)

    # cantilever brackets under the deck, every 4 m along each wall (an arm under the soffit and a strut down to the wall)
    def brackets(bm):
        for n in WALLS:
            ax, _ = WALLS[n]
            half = HX if ax == "x" else HZ
            for a in np.arange(-half + 2.0, half - 1.0, 4.0):
                a = float(a)
                if any(o[0] - 0.35 < a < o[1] + 0.35 for o in openings()[n] if o[2] < 1.0):   # not over a shopfront or the entrance: the wall plate needs wall
                    continue
                cyl(bm, on_wall(n, a, DECK_Y0 - 0.05, 0.0), on_wall(n, a, DECK_Y0 - 0.05, DECK_D - 0.35), 0.045, 0.045, 8, cap=False)   # the arm under the soffit
                cyl(bm, on_wall(n, a, DECK_Y0 - 1.05, 0.0), on_wall(n, a, DECK_Y0 - 0.1, DECK_D - 0.5), 0.035, 0.035, 8, cap=False)    # the strut
                wall_box(bm, n, a - 0.08, a + 0.08, DECK_Y0 - 1.15, DECK_Y0 - 0.95, 0.0, 0.03)                     # the wall plate
    part("Gallery_Brackets", "Metal_Dark", brackets)

    # soffit downlights: recessed cans 1.1 m from the walls, every 3 m; some are dead (a dark lens). The working ones light the shopfronts by day.
    SOFFIT.clear()
    rng = np.random.default_rng(23)
    for n in WALLS:
        ax, _ = WALLS[n]
        half = HX if ax == "x" else HZ
        for a in np.arange(-half + DECK_D + 0.4, half - DECK_D, 3.0):
            SOFFIT.append((on_wall(n, float(a), DECK_Y0, 1.1), rng.random() > 0.28))

    part("Soffit_Rims", "Trim_Paint", lambda bm: [disc(bm, (p[0], DECK_Y0 - 0.004, p[2]), 0.11, 16) for p, _ in SOFFIT], keep_normals=True)
    part("Soffit_Lenses", "Lamp_Emit", lambda bm: [disc(bm, (p[0], DECK_Y0 - 0.008, p[2]), 0.08, 16) for p, on in SOFFIT if on], keep_normals=True)
    part("Soffit_Dead", "Metal_Dark", lambda bm: [disc(bm, (p[0], DECK_Y0 - 0.008, p[2]), 0.08, 16) for p, on in SOFFIT if not on], keep_normals=True)


def drape(bm, base, t, nrm, a0, a1, profile, rng, folds=0.035, nu=18):
    """A cloth sheet hung over something: `profile` is [(d, y)] (d along `nrm`, y up) down the sheet; it runs from a0 to a1 along `t` from `base`.
    Folds grow toward the hem, the hem is ragged. Faces wind so their normal points along +nrm (toward the atrium) where the sheet hangs."""
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
            hem = 0.0
            if j == nv:
                hem = 0.12 * math.sin(a * 3.3 + ph[2]) + 0.06 * math.sin(a * 9.1)
            pt = Vector(base) + Vector(t) * a + Vector(nrm) * (d + fold) + Vector((0, 1, 0)) * (y + hem)
            row.append(bm.verts.new(B(tuple(pt))))
        rows.append(row)
    for r0, r1 in zip(rows, rows[1:]):
        for i in range(nu):
            bm.faces.new((r0[i], r1[i], r1[i + 1], r0[i + 1]))


def orient_faces(ob, toward):
    """Wind every face of an open sheet so its normal has a positive component along the game direction `toward`."""
    tb = B(toward)
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    for f in bm.faces:
        if f.normal.dot(tb) < 0:
            f.normal_flip()
    bm.to_mesh(me)
    bm.free()


def build_sheets():
    """Dust sheets thrown over the gallery's handrail, hanging down in front of the fascia (passable: decor_, and all above head height)."""
    rng = np.random.default_rng(31)
    spots = [(0, -6.5, 3.2), (0, 4.0, 2.6), (2, -3.5, 2.8), (3, 2.5, 3.4), (1, -9.0, 2.4)]
    for k, (e, a, w) in enumerate(spots):
        (p0, p1, nn) = deck_edges()[e]
        A, Bv = Vector((p0[0], DECK_Y1, p0[1])), Vector((p1[0], DECK_Y1, p1[1]))
        t = (Bv - A).normalized()
        nrm = Vector((nn[0], 0, nn[1]))
        base = A + t * ((Bv - A).length / 2) - Vector((0, DECK_Y1, 0))
        top = RAIL_H + 0.05
        hang = DECK_Y1 - (1.25 + rng.uniform(0, 0.5))            # how far below the deck the hem hangs
        prof = [(-0.75, DECK_Y1 + 0.01), (-0.2, DECK_Y1 + top * 0.8), (-0.06, DECK_Y1 + top + 0.02), (0.06, DECK_Y1 + top - 0.04), (0.10, DECK_Y1 + 0.2),
                (0.12, DECK_Y0 - 0.1), (0.16, hang)]
        ob = part(f"decor_sheet_{k}", "Cloth_Sheet", lambda bm: drape(bm, tuple(base), tuple(t), tuple(nrm), a - w / 2, a + w / 2, prof, rng), smooth=True, keep_normals=True)
        orient_faces(ob, tuple(nrm))


# ---------------------------------------------------------------- the skylight: an opening over the fountain and a glazed lantern over it
SKY_PANES = []


def build_skylight():
    y0 = CEIL_TOP
    y1 = y0 + LANTERN_UP
    yr = y1 + LANTERN_RIDGE
    x0, x1, z0, z1 = -SKY_X, SKY_X, SKY_Z0, SKY_Z1
    zc = (z0 + z1) / 2
    t = 0.05

    def frames(bm):
        # the kerb round the opening, the upstand's posts, the eaves, the ridge, the rafters and glazing bars
        for xa, xb, za, zb in ((x0, x1, z0, z0 + t), (x0, x1, z1 - t, z1), (x0, x0 + t, z0, z1), (x1 - t, x1, z0, z1)):
            cube(bm, (xa, H, za), (xb, y0 + 0.2, zb))                                          # the kerb, up to the upstand's glazing
        for x in np.linspace(x0, x1, 9):
            for z in (z0, z1):
                cyl(bm, (x, y0, z), (x, y1, z), 0.04, 0.04, 6, cap=False)                          # the upstand's posts
            cyl(bm, (x, y1, z0), (x, yr, zc), 0.04, 0.04, 6, cap=False)                         # rafters
            cyl(bm, (x, y1, z1), (x, yr, zc), 0.04, 0.04, 6, cap=False)
        for z in np.linspace(z0, z1, 9)[1:-1]:
            for x in (x0, x1):
                cyl(bm, (x, y0, z), (x, y1, z), 0.04, 0.04, 6, cap=False)
        cyl(bm, (x0, yr, zc), (x1, yr, zc), 0.07, 0.07, 8, cap=False)                             # the ridge
        for zz in (z0, z1):
            cyl(bm, (x0, y1, zz), (x1, y1, zz), 0.06, 0.06, 8, cap=False)                          # the eaves
        for xx in (x0, x1):
            cyl(bm, (xx, y1, z0), (xx, y1, z1), 0.06, 0.06, 8, cap=False)
            for f in (0.25, 0.5, 0.75):                                                          # the gable ends' posts
                z = z0 + (z1 - z0) * f
                top = y1 + LANTERN_RIDGE * (1 - abs(z - zc) / (zc - z0))
                cyl(bm, (xx, y1, z), (xx, top, z), 0.03, 0.03, 6, cap=False)
    part("Skylight_Frame", "Metal_Dark", frames)

    def panes(bm):
        # faces wound to face into the lantern (down / inward): seen from the atrium
        quad(bm, (x0, y1, z0), (x1, y1, z0), (x1, yr, zc), (x0, yr, zc))                       # the south slope (faces down toward +z... set by orient below)
        quad(bm, (x0, y1, z1), (x0, yr, zc), (x1, yr, zc), (x1, y1, z1))
        for zz in (z0, z1):
            quad(bm, (x0, y0 + 0.2, zz), (x1, y0 + 0.2, zz), (x1, y1, zz), (x0, y1, zz))         # the upstand, north and south
        for xx in (x0, x1):
            quad(bm, (xx, y0 + 0.2, z0), (xx, y0 + 0.2, z1), (xx, y1, z1), (xx, y1, z0))         # the upstand, east and west
            bm.faces.new([bm.verts.new(B(p)) for p in ((xx, y1, z0), (xx, y1, z1), (xx, yr, zc))])    # the gables
    ob = part("Skylight_Panes", "Skylight_Glass", panes, keep_normals=True)
    me = ob.data                                                                                # wind every pane toward the lantern's middle (into the room)
    bm = bmesh.new()
    bm.from_mesh(me)
    c = B((0, y0, zc))
    for f in bm.faces:
        if f.normal.dot(c - f.calc_center_median()) < 0:
            f.normal_flip()
    bm.to_mesh(me)
    bm.free()
    for attr in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
        setattr(ob, attr, False)                     # in the stills the camera sees the panes, the light passes them (as in the bake, where they are hidden)


# ---------------------------------------------------------------- the fountain, dry, with a scaffold tower standing in its basin (for the skylight's repair)
SCAF = {}


def build_fountain():
    """The dry fountain on its collider: a stone kerb 0.7 m high round a dry basin, a two-tier bowl on a column in the middle. A scaffold tower stands in the
    basin (the skylight over it is being repaired), so all of it stands within the fountain's footprint."""
    rim = 0.28
    bf = 0.22                                                                                   # the basin's dry floor

    def kerb(bm):
        holed_box_xz(bm, (FX0 + KERB_IN, FX1 - KERB_IN), (FZ0 + KERB_IN, FZ1 - KERB_IN), 0.0, FH - 0.08, [(FX0 + rim, FX1 - rim, FZ0 + rim, FZ1 - rim)])
    part("Fountain_Kerb", "Fountain_Stone", kerb)

    def cap(bm):
        holed_box_xz(bm, (FX0, FX1), (FZ0, FZ1), FH - 0.08, FH, [(FX0 + rim - 0.03, FX1 - rim + 0.03, FZ0 + rim - 0.03, FZ1 - rim + 0.03)])
    part("Fountain_Cap", "Fountain_Stone", cap)
    part("Fountain_Bed", "Fountain_Basin", lambda bm: cube(bm, (FX0 + rim, 0.0, FZ0 + rim), (FX1 - rim, bf, FZ1 - rim)))

    def column(bm):
        cyl(bm, (FCX, bf, FCZ), (FCX, bf + 0.12, FCZ), 0.45, 0.42, 24)
        cyl(bm, (FCX, bf + 0.12, FCZ), (FCX, 1.12, FCZ), 0.26, 0.2, 24)
        cyl(bm, (FCX, 1.12, FCZ), (FCX, 1.32, FCZ), 0.25, 0.9, 32)                              # the lower bowl
        cyl(bm, (FCX, 1.32, FCZ), (FCX, 1.36, FCZ), 0.9, 0.9, 32)
        cyl(bm, (FCX, 1.36, FCZ), (FCX, 1.78, FCZ), 0.1, 0.08, 16)
        cyl(bm, (FCX, 1.78, FCZ), (FCX, 1.88, FCZ), 0.1, 0.36, 24)                              # the upper bowl
        sphere(bm, (FCX, 1.97, FCZ), 0.08, 12)
    part("Fountain_Column", "Fountain_Stone", column, smooth=True)

    # the scaffold tower: four standards on base plates in the basin, lifts at 2 m steps up to the opening, boards, guardrails, toe boards, braces, a ladder
    sx, sz = 1.9, 1.9
    xs, zs = (FCX - sx, FCX + sx), (FCZ - sz, FCZ + sz)
    lifts = [2.25, 4.25, 6.25]
    top = CEIL_TOP + 0.5
    SCAF.update({"xs": xs, "zs": zs, "lifts": lifts, "bf": bf})
    r = 0.0241                                                                                  # 48.3 mm tube
    def tube(bm, p0, p1, r0, r1=None, seg=16):                                                  # the tower's tubes are open (their ends are never seen)
        return cyl(bm, p0, p1, r0, r1, seg, cap=False)

    def tubes(bm):
        for x in xs:
            for z in zs:
                tube(bm, (x, bf + 0.03, z), (x, top, z), r, r, 10)
        for y in [bf + 0.25] + lifts:
            for z in zs:
                tube(bm, (xs[0] - 0.15, y, z), (xs[1] + 0.15, y, z), r, r, 10)
            for x in xs:
                tube(bm, (x, y - 0.05, zs[0] - 0.15), (x, y - 0.05, zs[1] + 0.15), r, r, 10)
        for y in lifts:                                                                         # guardrails, 0.5 and 1.0 over each lift
            for dy in (0.5, 1.0):
                for z in zs:
                    tube(bm, (xs[0], y + dy, z), (xs[1], y + dy, z), r, r, 10)
                for x in xs:
                    tube(bm, (x, y + dy, zs[0]), (x, y + dy, zs[1]), r, r, 10)
        ys = [bf + 0.25] + lifts
        for ya, yb in zip(ys, ys[1:]):                                                          # face braces, alternating
            for x in xs:
                tube(bm, (x + (0.06 if x < FCX else -0.06), ya, zs[0]), (x + (0.06 if x < FCX else -0.06), yb, zs[1]), r, r, 8)
        for x in (FCX + 0.55, FCX + 1.0):                                                       # the ladder's stiles on the south face
            tube(bm, (x, bf, zs[1] + 0.12), (x, lifts[0] + 1.0, zs[1] + 0.12), 0.02, 0.02, 8)
        for y in np.arange(bf + 0.3, lifts[0] + 0.9, 0.3):
            tube(bm, (FCX + 0.55, y, zs[1] + 0.12), (FCX + 1.0, y, zs[1] + 0.12), 0.014, 0.014, 6)
    part("Scaffold_Tubes", "Metal_Steel", tubes, smooth=True)

    part("Scaffold_Plates", "Metal_Dark", lambda bm: [cube(bm, (x - 0.08, bf, z - 0.08), (x + 0.08, bf + 0.03, z + 0.08)) for x in xs for z in zs])   # base plates

    def boards(bm):
        for y in lifts:
            z1b = zs[1] + 0.15 if y != lifts[0] else zs[1] - 0.55                                # the first lift leaves a trap where the ladder comes up
            cube(bm, (xs[0] - 0.15, y + r, zs[0] - 0.15), (xs[1] + 0.15, y + r + 0.038, z1b))
            for z in zs:                                                                        # toe boards
                cube(bm, (xs[0], y + r + 0.038, z - 0.02 if z == zs[0] else z - 0.02), (xs[1], y + r + 0.19, z + 0.02))
            for x in xs:
                cube(bm, (x - 0.02, y + r + 0.038, zs[0]), (x + 0.02, y + r + 0.19, zs[1]))
    part("Scaffold_Boards", "Scaffold_Board", boards)

    # the work lamp, clamped to the top lift's north-east corner and aimed down into the basin
    lamp = (xs[1] - 0.05, lifts[-1] + 1.15, zs[0] + 0.05)
    SCAF["lamp"] = lamp
    aim = (FCX - 1.0, 0.3, FCZ + 1.2)
    d = (Vector(aim) - Vector(lamp)).normalized()
    SCAF["lamp_dir"] = tuple(d)
    part("Scaffold_LampBody", "Metal_Dark", lambda bm: [cyl(bm, tuple(Vector(lamp) - d * 0.12), tuple(Vector(lamp) + d * 0.04), 0.13, 0.13, 4),
                                                       cyl(bm, (lamp[0], lamp[1] - 0.2, lamp[2]), lamp, 0.015, 0.015, 6)])
    part("Scaffold_LampLens", "Lamp_Emit", lambda bm: cyl(bm, tuple(Vector(lamp) + d * 0.04), tuple(Vector(lamp) + d * 0.05), 0.11, 0.11, 4))

    # a dust sheet hung on the top lift's north guardrail
    rng = np.random.default_rng(5)
    prof = [(0.0, lifts[-1] + 1.02), (0.05, lifts[-1] + 0.6), (0.09, lifts[-1] - 0.5), (0.12, lifts[-1] - 2.3)]
    ob = part("decor_scaffold_sheet", "Cloth_Sheet", lambda bm: drape(bm, (FCX, 0.0, zs[0] - 0.03), (1, 0, 0), (0, 0, -1), -1.7, 1.2, prof, rng, folds=0.05), smooth=True, keep_normals=True)
    orient_faces(ob, (0, 0, -1))


def build_benches():
    """The two benches on their colliders: backless, five hardwood slats on dark steel frames (the page's bench prompt is unchanged)."""
    for i, b in enumerate(BENCHES):
        (x0, _, z0), (x1, y1, z1) = b["min"], b["max"]

        def frame(bm):
            for xe in (x0 + 0.04, x1 - 0.10):                                                    # the end frames, so the art reaches the collider's ends
                cube(bm, (xe, 0.0, z0 + 0.03), (xe + 0.06, y1 - 0.05, z0 + 0.09))
                cube(bm, (xe, 0.0, z1 - 0.09), (xe + 0.06, y1 - 0.05, z1 - 0.03))
                cube(bm, (xe, y1 - 0.1, z0 + 0.03), (xe + 0.06, y1 - 0.05, z1 - 0.03))
                cube(bm, (xe - 0.03, 0.0, z0 + 0.0), (xe + 0.09, 0.012, z1))                      # the feet
            cube(bm, (x0 + 0.15, 0.18, (z0 + z1) / 2 - 0.02), (x1 - 0.15, 0.22, (z0 + z1) / 2 + 0.02))
        part(f"Bench_{i}_Frame", "Metal_Dark", frame)

        def slats(bm):
            n = 5
            w = (z1 - z0) / n
            for k in range(n):
                cube(bm, (x0, y1 - 0.05, z0 + k * w + 0.008), (x1, y1, z0 + (k + 1) * w - 0.008))
        part(f"Bench_{i}_Slats", "Bench_Wood", slats)


# ---------------------------------------------------------------- the emergency fittings, the EXIT sign
EMERG = []          # (game point of a head, aim direction (game))


def build_emergency():
    """Twin-head emergency fittings on the lower walls between the shops and on the south wall, and single heads on the gallery's fascia: a white body and
    two heads whose lenses are Emergency_Emit. They are the only light while the mall is locked."""
    EMERG.clear()
    yb = SHOP_H + 0.25
    north = sorted([a for n, a, _ in shop_slots() if n == "+z"])
    sides = sorted([a for n, a, _ in shop_slots() if n == "+x"])
    spots = [("+z", (p + q) / 2) for p, q in zip(north, north[1:])]
    spots += [("+x", (sides[0] + sides[1]) / 2), ("-x", (sides[0] + sides[1]) / 2)]
    spots += [("-z", DOOR[0] - ENTRY_W / 2 - 5.0), ("-z", DOOR[0] + ENTRY_W / 2 + 5.0)]

    def bodies(bm):
        for n, a in spots:
            wall_box(bm, n, a - 0.22, a + 0.22, yb - 0.06, yb + 0.06, 0.0, 0.09)
            for k in (-1, 1):
                cyl(bm, on_wall(n, a + k * 0.16, yb + 0.06, 0.06), on_wall(n, a + k * 0.16, yb + 0.12, 0.06), 0.012, 0.012, 6)
    part("Emergency_Bodies", "Plastic_White", bodies)

    heads = []
    for n, a in spots:
        for k in (-1, 1):
            p = Vector(on_wall(n, a + k * 0.16, yb + 0.15, 0.07))
            aim = Vector(on_wall(n, a + k * 2.5, 0.0, 4.5))
            heads.append((tuple(p), tuple((aim - p).normalized())))
    # single heads on the fascia, mid-edge, aimed across the atrium's floor
    for (a, b_, nn) in deck_edges():
        m = ((a[0] + b_[0]) / 2, DECK_Y0 - 0.2, (a[1] + b_[1]) / 2)
        p = Vector(m) + Vector((nn[0], 0, nn[1])) * 0.12
        aim = Vector((m[0] + nn[0] * 6.0, 0.0, m[2] + nn[1] * 6.0))
        heads.append((tuple(p), tuple((aim - p).normalized())))
    EMERG.extend(heads)

    def cans(bm):
        for p, d in heads:
            P, D = Vector(p), Vector(d)
            cyl(bm, tuple(P - D * 0.06), tuple(P + D * 0.03), 0.045, 0.055, 12)
    part("Emergency_Heads", "Plastic_White", cans, smooth=True)
    part("Emergency_Lenses", "Emergency_Emit", lambda bm: [cyl(bm, tuple(Vector(p) + Vector(d) * 0.03), tuple(Vector(p) + Vector(d) * 0.036), 0.046, 0.046, 12) for p, d in heads])

    def brackets(bm):
        for (a, b_, nn) in deck_edges():
            m = ((a[0] + b_[0]) / 2, DECK_Y0 - 0.2, (a[1] + b_[1]) / 2)
            cube(bm, (m[0] - 0.03, DECK_Y0 - 0.25, m[2] - 0.03), (m[0] + 0.03, DECK_Y0 - 0.02, m[2] + 0.03))
    part("Emergency_Brackets", "Metal_Dark", brackets)

    # the EXIT sign, hung from the gallery's soffit in front of the entrance, facing the atrium
    z = HZ - 0.9
    y = DECK_Y0 - 0.55
    dx = DOOR[0]
    part("Exit_Housing", "Metal_Dark", lambda bm: [cube(bm, (dx - 0.24, y - 0.1, z - 0.04), (dx + 0.24, y + 0.1, z + 0.04)),
                                                   cyl(bm, (dx - 0.18, y + 0.1, z), (dx - 0.18, DECK_Y0, z), 0.008, 0.008, 6),
                                                   cyl(bm, (dx + 0.18, y + 0.1, z), (dx + 0.18, DECK_Y0, z), 0.008, 0.008, 6)])
    panel("Exit_Face", "Sign_Exit", (dx, y, z - 0.0405), "-z", 0.44, 0.16)                 # facing the atrium (north)
    SCAF["exit"] = (dx, y, z - 0.06)


# ---------------------------------------------------------------- clutter on the floor (all low or in the fountain; passable: decor_)
def build_clutter():
    rng = np.random.default_rng(41)
    bf = SCAF["bf"]
    xs, zs = SCAF["xs"], SCAF["zs"]

    def cloth_flat(bm, x0, x1, z0, z1, y0, nx=16, nz=12, amp=0.035):
        ph = rng.uniform(0, 6.3, 4)
        vs = []
        for j in range(nz + 1):
            row = []
            for i in range(nx + 1):
                u, v = i / nx, j / nz
                x = x0 + (x1 - x0) * u + 0.08 * math.sin(v * 9 + ph[0]) * (u in (0, 1))
                z = z0 + (z1 - z0) * v + 0.08 * math.sin(u * 7 + ph[1]) * (v in (0, 1))
                y = y0 + amp * (0.5 + 0.5 * math.sin(u * 11 + ph[2]) * math.sin(v * 8 + ph[3])) ** 2
                row.append(bm.verts.new(B((x, y, z))))
            vs.append(row)
        for r0, r1 in zip(vs, vs[1:]):
            for i in range(nx):
                bm.faces.new((r0[i], r0[i + 1], r1[i + 1], r1[i]))

    # a drop cloth in the basin under the tower, and another by the west wall where GIFTS is being painted
    ob = part("decor_dropcloth_basin", "Cloth_Sheet", lambda bm: cloth_flat(bm, FX0 + 0.35, FX1 - 0.4, FZ0 + 0.35, FZ1 - 0.6, bf + 0.004), smooth=True, keep_normals=True)
    orient_faces(ob, (0, 1, 0))
    gz = shop_slots()[4][1]
    ob = part("decor_dropcloth_west", "Cloth_Sheet", lambda bm: cloth_flat(bm, -HX + 0.25, -HX + 2.9, gz - 2.2, gz + 1.6, 0.004), smooth=True, keep_normals=True)
    orient_faces(ob, (0, 1, 0))

    def tins(bm):
        for (x, z) in ((-HX + 1.2, gz - 1.0), (-HX + 1.55, gz - 0.7), (-HX + 2.3, gz + 0.9), (FCX + 1.3, FCZ - 1.4), (FCX - 1.4, FCZ + 1.3), (FCX + 1.6, FCZ + 1.2)):
            y0 = bf + 0.005 if FX0 < x < FX1 and FZ0 < z < FZ1 else 0.005
            cyl(bm, (x, y0, z), (x, y0 + 0.19, z), 0.085, 0.085, 16)
    part("decor_paint_tins", "Metal_Steel", tins, smooth=True)

    # plasterboard stacked flat and cement bags by the renovation hoarding (north-east), low enough to step past
    n, a, _ = shop_slots()[RENOVATION]
    part("decor_plasterboard", "Clutter_Paint", lambda bm: cube(bm, (a - 1.4, 0.0, -HZ + 1.35), (a + 1.0, 0.13, -HZ + 2.55)))

    def bags(bm):
        for k in range(4):
            x = a + 1.4 + (k % 2) * 0.62
            z = -HZ + 0.7 + (k // 2) * 0.45
            cube(bm, (x, 0.0, z), (x + 0.58, 0.12, z + 0.4))
    part("decor_cement_bags", "Cloth_Sheet", bags)

    # in the basin: a stepladder against the tower, a bucket
    def ladder(bm):
        x0, z = xs[0] + 0.45, zs[0] + 0.35
        for dx in (0.0, 0.45):
            cyl(bm, (x0 + dx, bf, z - 0.3), (x0 + dx, bf + 1.25, z), 0.018, 0.018, 6)
            cyl(bm, (x0 + dx, bf, z + 0.3), (x0 + dx, bf + 1.25, z), 0.018, 0.018, 6)
        for y in np.arange(bf + 0.3, bf + 1.2, 0.28):
            t = (y - bf) / 1.25
            cyl(bm, (x0, y, z - 0.3 * (1 - t)), (x0 + 0.45, y, z - 0.3 * (1 - t)), 0.012, 0.012, 6)
    part("decor_stepladder", "Metal_Steel", ladder, smooth=True)
    part("decor_bucket", "Clutter_Paint", lambda bm: cyl(bm, (FCX + 1.2, bf, FCZ + 0.6), (FCX + 1.2, bf + 0.3, FCZ + 0.6), 0.13, 0.15, 16, cap=True), smooth=True)

    # the work lamp's cable: from the tower, over the kerb, along the floor to a socket on the west wall
    def cable(bm):
        pts = [(xs[0], SCAF["lifts"][0], zs[1]), (xs[0] - 0.1, 1.2, zs[1] + 0.2), (FX0 + 0.12, FH + 0.01, FZ1 - 0.6), (FX0 - 0.25, 0.01, FZ1 - 0.4),
               (-6.0, 0.012, 1.0), (-11.0, 0.012, 2.5), (-HX + 0.05, 0.3, 3.0)]
        for p, q in zip(pts, pts[1:]):
            cyl(bm, p, q, 0.009, 0.009, 6)
    part("decor_cable", "Metal_Dark", cable)


# ---------------------------------------------------------------- generated images (own work, numpy, fixed seeds)
GLYPHS = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"], "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"], "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"], "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"], "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"], "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"], "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"], "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"], "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"], "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"], "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"], "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    " ": ["00000"] * 7, "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"], ".": ["00000"] * 6 + ["00100"],
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
    """A hand-painted line of capitals in the 5 x 7 pixel font, centred in an h x w mask: blurred and re-thresholded so the strokes round off like a brush's,
    with a wobble per letter and ragged edges."""
    adv = 6
    units = len(text) * adv - 1
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
                    m[max(0, y0 + jy + r * s):y0 + jy + (r + 1) * s, x + c * s:x + (c + 1) * s] = 1
        x += adv * s
    if painted:
        k = max(1, s // 3)
        m = blur(m, k, 2)
        m = np.clip((m - 0.5) * 6 + (vnoise(h, w, rng, 4, 16) - 0.5) * 1.2 + 0.5, 0, 1)
    return m


SIGN_ATLAS_ROWS = 8
SIGN_STYLE = [((0.36, 0.10, 0.12), (0.93, 0.86, 0.70)), ((0.10, 0.16, 0.36), (0.92, 0.92, 0.90)), ((0.12, 0.30, 0.18), (0.98, 0.84, 0.32)),
              ((0.86, 0.84, 0.78), (0.62, 0.10, 0.08)), ((0.10, 0.36, 0.36), (0.95, 0.90, 0.78)), ((0.06, 0.06, 0.07), (0.98, 0.58, 0.18)),
              ((0.40, 0.46, 0.52), (0.96, 0.96, 0.96)), ((0.62, 0.14, 0.10), (0.99, 0.86, 0.22))]


def signs_pixels():
    """The eight painted fascia signs, one per row of a 1024 x 1024 atlas (each 1024 x 128, the board's 4.6 x 0.52 m): a faded board colour, the shop's name
    in hand-painted capitals, sun-bleaching toward the top, grime and chipped paint."""
    W, R = 1024, 128
    rng = np.random.default_rng(17)
    img = np.zeros((W, W, 3), np.float32)
    for i, name in enumerate(SHOPS):
        bg, fg = SIGN_STYLE[i % len(SIGN_STYLE)]
        row = np.zeros((R, W, 3), np.float32)
        row[:] = bg
        m = text_mask(name, R, W, rng)
        row = row * (1 - m[..., None]) + np.array(fg) * m[..., None]
        n = vnoise(R, W, rng, 5, 6)
        fade = np.linspace(1.12, 0.92, R)[:, None, None]
        row = row * (0.78 + 0.35 * n[..., None]) * fade
        chips = (vnoise(R, W, rng, 3, 24) > 0.74).astype(np.float32)                              # chipped paint showing the primer
        row = row * (1 - chips[..., None] * 0.7) + np.array([0.55, 0.52, 0.46]) * chips[..., None] * 0.7
        row[:3] = row[-3:] = row[:, :3] = row[:, -3:] = np.array(bg) * 0.5
        img[i * R:(i + 1) * R] = row
    return np.clip(img, 0, 1)


def directory_pixels():
    """The mall directory: a dark board with the shops listed by number, in the pixel font (painted, a little faded)."""
    h, w = 768, 512
    rng = np.random.default_rng(19)
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (0.09, 0.11, 0.14)
    title = text_mask("DIRECTORY", 90, w, rng, fill=0.5, maxw=0.8, painted=False)
    img[30:120] = img[30:120] * (1 - title[..., None]) + np.array([0.95, 0.80, 0.35]) * title[..., None]
    img[128:132, 30:-30] = (0.95, 0.80, 0.35)
    rh = (h - 170) // len(SHOPS)
    for i, name in enumerate(SHOPS):
        label = f"{i + 1} {name}"
        m = text_mask(label, rh, w, rng, fill=0.42, maxw=0.92, painted=False)
        y = 150 + i * rh
        img[y:y + rh] = img[y:y + rh] * (1 - m[..., None]) + np.array([0.90, 0.90, 0.86]) * m[..., None]
    n = vnoise(h, w, rng, 5, 6)
    img = img * (0.8 + 0.3 * n[..., None])
    img[:6] = img[-6:] = img[:, :6] = img[:, -6:] = (0.35, 0.36, 0.38)
    return np.clip(img, 0, 1)


def exit_pixels():
    h, w = 96, 256
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (0.02, 0.45, 0.16)
    m = text_mask("EXIT", h, w, np.random.default_rng(1), fill=0.66, maxw=0.8, painted=False)
    img = img * (1 - m[..., None]) + np.array([0.95, 1.0, 0.95]) * m[..., None]
    img[:4] = img[-4:] = img[:, :4] = img[:, -4:] = (0.01, 0.2, 0.07)
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def whitewash_pixels():
    """Glass whitewashed from the inside for the works: streaky arcs of a wide brush, thinner here and there, a cleared smear at hand height."""
    S = 512
    rng = np.random.default_rng(29)
    yy, xx = np.mgrid[0:S, 0:S] / S
    streak = 0.5 + 0.5 * np.sin((xx * 3.0 + yy * 1.4 + 0.15 * np.sin(yy * 17)) * 2 * math.pi * 6)
    n = vnoise(S, S, rng, 6, 6)
    cover = np.clip(0.72 + 0.22 * streak * n + (n - 0.5) * 0.4, 0, 1)
    base = np.array([0.55, 0.60, 0.60])
    white = np.array([0.90, 0.89, 0.84])
    img = base * (1 - cover[..., None]) + white * cover[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def skyglass_pixels():
    """Dirty wired glass: a pale panel with the wire's square mesh, grime washed down the slope and leaves gathered at the bottom edge."""
    S = 512
    rng = np.random.default_rng(37)
    yy, xx = np.mgrid[0:S, 0:S]
    wire = ((xx % 32) < 2) | ((yy % 32) < 2)
    img = np.ones((S, S, 3), np.float32) * np.array([0.82, 0.88, 0.90])
    img[wire] *= 0.6
    n = vnoise(S, S, rng, 6, 4)
    streak = blur(rng.random((S, S)).astype(np.float32), 1, 1)
    streak = rs(streak[:, ::16], S, S)
    grime = np.clip((n - 0.35) * 1.2 + (streak - 0.5) * 0.4, 0, 1)
    img = img * (1 - 0.45 * grime[..., None]) + np.array([0.35, 0.33, 0.28]) * 0.45 * grime[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def dust_pixels():
    """Dust and grit gathered round the fountain's foot: dense next to the kerb (the middle of the decal is under the fountain) and thinning out, patchy."""
    S = 512
    rng = np.random.default_rng(43)
    yy, xx = np.mgrid[0:S, 0:S] / (S - 1) * 2 - 1
    n = vnoise(S, S, rng, 6, 4)
    r = np.maximum(np.abs(xx), np.abs(yy))                       # the decal is square round a square kerb: 0 in the middle, 1 at its edge
    a = np.clip(0.45 * (1 - np.clip((r - 0.5) / 0.5, 0, 1)) ** 1.8 + (n - 0.5) * 0.3, 0, 0.45)
    rgba = np.zeros((S, S, 4), np.float32)
    rgba[..., :3] = np.array([0.52, 0.47, 0.40]) * (0.85 + 0.3 * n[..., None])
    rgba[..., 3] = a
    return rgba


def stain_pixels():
    """A dried puddle: a pale tide-lined patch of rain that came in through the broken skylight."""
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


def make_generated():
    return {"signs": mk_image("Shop_Signs", signs_pixels()), "directory": mk_image("Mall_Directory", directory_pixels()),
            "exit": mk_image("Exit_Sign", exit_pixels()), "whitewash": mk_image("Glass_Whitewash", whitewash_pixels()),
            "skyglass": mk_image("Wired_Glass", skyglass_pixels()), "dust": mk_image("Floor_Dust", dust_pixels()), "stain": mk_image("Floor_Puddle", stain_pixels())}


# ---------------------------------------------------------------- lights, world
SUN_W = 8.0                    # the sun through the skylight (W/m2)
SUN_DIR = (0.42, -0.78, -0.46) # where its light travels (game axes): from high in the south-west, so the skylight's square falls on the fountain and north-east of it
SKY_STRENGTH = 5.0             # the sky, seen only through the skylight
SOFFIT_W = 150.0               # each working soffit downlight
WORK_W = 300.0                 # the scaffold's work lamp
EMERG_W = 180.0                # each emergency head
EXIT_W = 2.0
PANE_GLOW = 6.0                # the skylight's panes in the stills: the bright sky seen through dirty glass


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

    ob, d = light("Lights_Day", "Sun", "SUN", (0, 20, 0), SUN_W, (1.0, 0.95, 0.86), 0.0)
    d.angle = math.radians(1.5)
    ob.rotation_euler = B(SUN_DIR).to_track_quat("-Z", "Y").to_euler()
    for i, (p, on) in enumerate(SOFFIT):
        if not on:
            continue
        ob, d = light("Lights_Day", f"Soffit_{i}", "SPOT", (p[0], DECK_Y0 - 0.04, p[2]), SOFFIT_W, (1.0, 0.88, 0.72), 0.05)
        d.spot_size, d.spot_blend = math.radians(110), 0.6
        ob.rotation_euler = B((0, -1, 0)).to_track_quat("-Z", "Y").to_euler()
    ob, d = light("Lights_Day", "Work_Lamp", "SPOT", tuple(Vector(SCAF["lamp"]) + Vector(SCAF["lamp_dir"]) * 0.07), WORK_W, (1.0, 0.86, 0.66), 0.08)
    d.spot_size, d.spot_blend = math.radians(80), 0.5
    ob.rotation_euler = B(SCAF["lamp_dir"]).to_track_quat("-Z", "Y").to_euler()
    for i, (p, dd) in enumerate(EMERG):
        ob, d = light("Lights_Night", f"Emergency_{i}", "SPOT", tuple(Vector(p) + Vector(dd) * 0.045), EMERG_W, (0.86, 0.93, 1.0), 0.03)
        d.spot_size, d.spot_blend = math.radians(75), 0.45
        ob.rotation_euler = B(dd).to_track_quat("-Z", "Y").to_euler()
    ob, d = light("Lights_Always", "Exit_Glow", "AREA", SCAF["exit"], EXIT_W, (0.3, 1.0, 0.45), 0.0)
    d.shape, d.size, d.size_y = "RECTANGLE", 0.44, 0.16
    ob.rotation_euler = B((0, 0, -1)).to_track_quat("-Z", "Y").to_euler()


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


def apply_light_set(name):
    """day: the sun, the sky and the working downlights (Lamp_Emit on, Emergency_Emit off); night: the emergency heads alone (the mall locked);
    export: both toggled materials at the strength the page switches on and off."""
    day = name == "day"
    for c, on in (("Lights_Day", day), ("Lights_Night", name == "night"), ("Lights_Always", True)):
        if c in bpy.data.collections:
            bpy.data.collections[c].hide_render = not on
    w = bpy.context.scene.world
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = SKY_STRENGTH if day else 0.0
    set_emit("Lamp_Emit", LAMP_EMIT if name in ("day", "export") else 0.0)
    set_emit("Emergency_Emit", EMERG_EMIT if name in ("night", "export") else 0.0)
    set_emit(PANE_MAT, {"day": PANE_GLOW, "night": PANE_GLOW * 0.01}.get(name, 0.0))   # the panes' sky, for the stills only (the page shows their lightmap; exported at 0)


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
    make_materials(make_generated())
    build_shell()
    build_floor_decals()
    build_shopfronts()
    build_entrance()
    build_directory()
    build_gallery()
    build_sheets()
    build_skylight()
    build_fountain()
    build_benches()
    build_emergency()
    build_clutter()
    add_lights()
    setup_world()
    apply_light_set("day")
    ensure_marker()


# ---------------------------------------------------------------- bake
GROUPS = [["Floor_Terrazzo", "Floor_Border", "Wall_Plaster", "Wall_Upper", "Ceiling_Paint", "Decal_Dust", "Decal_Stain", "Deck_Concrete", "Trim_Paint"],   # 0 (day), 2 (night): the shell, the gallery, trim
          ["Shutter_Metal", "Hoarding_Ply", "Scaffold_Board", "Fountain_Stone", "Fountain_Basin", "Bench_Wood",
           "Cloth_Sheet", "Metal_Dark", "Metal_Steel", "Plastic_White", "Clutter_Paint", "Glass_Whitewash", "Sign_Paint", "Directory_Board",
           "Skylight_Glass"]]                                                                                                     # 1 (day) and 3 (night): everything in it
PAGES = [2048, 2048]          # each map's fixed page size (px), so a rebuild repeats (Blender's island packer is not exactly repeatable)
NIGHT_OFFSET = 2              # the night set of map n is entrance_<n + 2>
SHELL_PREFIX = ("Wall_", "Floor_", "Ceiling_")
PANE_MAT = "Skylight_Glass"   # its lightmap texels are filled with the sky (see fill_panes), so its islands are packed small
UV_SCALE = {"Skylight_Glass": 0.15, "Ceiling_Paint": 0.55}     # islands packed smaller: the panes are filled flat; the ceiling is 7 m overhead
PANE_DAY, PANE_NIGHT = 1.0, 0.03     # the panes' lightmap value as a fraction of each map's white point: by day the bright sky, by night a dull glow
HIDE_IN_BAKE = ("Glass_Clear", PANE_MAT)       # transparent panes and the open skylight: hidden while baking, so the sun and the sky come in


def trim_shell(bm, name):
    """Drop the faces of a shell slab that are never seen from the atrium (the outer skin of the walls, the floor's underside and sides, the ceiling's top):
    they would cost lightmap texels. Openings' reveals are kept."""
    e = 1e-3
    bad = []
    for f in bm.faces:
        c, n = f.calc_center_median(), f.normal
        gx, gy, gz = c.x, c.z, -c.y
        nx, ny, nz = n.x, n.z, -n.y
        if name.startswith("Floor_"):
            keep = ny > 0.9 and abs(gy) < e
        elif name.startswith("Ceiling_"):
            keep = (ny < -0.9 and abs(gy - H) < e) or (abs(ny) < 0.1 and abs(gx) < HX - e and abs(gz) < HZ - e)
        else:
            w = WALL_OF[name.replace("_Upper", "")]
            ax, _ = WALLS[w]
            out = {"+x": (-1, 0), "-x": (1, 0), "+z": (0, -1), "-z": (0, 1)}[w]
            along = gz if ax == "z" else gx
            half = HZ if ax == "z" else HX
            n_out = nx * out[0] + nz * out[1]
            n_along = nz if ax == "z" else nx
            keep = not (n_out > 0.5 or (ny < -0.9 and gy < e) or (ny > 0.9 and gy > H - e) or (abs(n_along) > 0.5 and abs(along) > half - e)
                        or (ny > 0.9 and abs(gy - DECK_Y0) < e) or (ny < -0.9 and abs(gy - DECK_Y0) < e))
        if not keep:
            bad.append(f)
    bmesh.ops.delete(bm, geom=bad, context="FACES")


SEEN_UP = 2.2       # the walker's eye is at 1.6 m: a face that looks up from higher than this, or down from lower than SEEN_DOWN, is never seen in the game
SEEN_DOWN = 0.8


SHEETS = ("Cloth_Sheet",)   # open, two-sided sheets: their back can be seen, so they keep their up- and down-facing faces


def cull_flush(bm, mname=""):
    """Drop the faces of a piece that lie flat against (or behind) a wall, the floor or the ceiling and face into it (the back of a sign, the underside of a
    bench's foot, a shutter's back): never seen, and each would be one more lightmap island."""
    e = 1e-3
    bad = []
    for f in bm.faces:
        c, n = f.calc_center_median(), f.normal
        gx, gy, gz = c.x, c.z, -c.y
        nx, ny, nz = n.x, n.z, -n.y
        if (nx < -0.9 and gx <= -HX + e) or (nx > 0.9 and gx >= HX - e) or (nz < -0.9 and gz <= -HZ + e) or (nz > 0.9 and gz >= HZ - e) \
                or (ny < -0.9 and abs(gy) <= e) or (ny > 0.9 and abs(gy - H) <= e) \
                or (mname not in SHEETS and ((ny > 0.5 and gy > SEEN_UP) or (ny < -0.5 and gy < SEEN_DOWN))):
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
        if ob.name.startswith("Wall_") or ob.name.startswith(("Floor_", "Ceiling_")):
            trim_shell(tmp, ob.name)
        else:
            cull_flush(tmp, mname)
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


def lightmap_uv(objs, page):
    """One shared atlas for `objs`: smart-project islands, equal texel density (the skylight's panes shrunk: their texels are filled flat), packed with
    MARGIN_PX on a `page` px square. Returns the density (px/m) over everything but the panes."""
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
            for l in o.data.uv_layers["lightmap"].data:
                l.uv = l.uv * UV_SCALE[o.name]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / page, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    rest = [o for o in objs if o.name not in UV_SCALE]
    a3 = sum(area3d(o) for o in rest)
    au = sum(uv_area(o, "lightmap") for o in rest)
    dens = page * math.sqrt(au / a3)
    small = {o.name: round(page * math.sqrt(uv_area(o, "lightmap") / area3d(o)), 1) for o in objs if o.name in UV_SCALE}
    print(f"  page {page}: {a3:.1f} m2 (the scaled islands aside), {dens:.1f} px/m; scaled: {small}")
    return page, dens, small


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
    bpy.data.node_groups.remove(ng)
    return a.reshape(S, S, 4)


def pane_mask(ob, S, grow=2):
    """The texels the skylight's panes cover in the lightmap (rows bottom to top, as Blender's pixels), widened by `grow` px."""
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
        g = m.astype(np.float32)
        g = blur(g, grow, 1) > 0
        m = m | g
    return m


def bake_set(n, objs, S, light_set, samples):
    """One bake of map n's objects with the light set `light_set`; returns the denoised float RGB (S x S x 3, rows bottom up)."""
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
    bpy.data.collections["Art"].hide_render = True
    bpy.data.collections["Art"].hide_viewport = True
    setup_cycles(SAMPLES, bake=True)
    for m in HIDE_IN_BAKE:
        if m in exp:
            exp[m].hide_render = True
    report = {}
    for n, mats in enumerate(GROUPS):
        objs = [exp[m] for m in mats if m in exp]
        print(f"lightmap {n}: {[o.name for o in objs]}")
        S, dens, small = lightmap_uv(objs, PAGES[n])
        if PANE_MAT in exp and exp[PANE_MAT] in objs:
            mask = pane_mask(exp[PANE_MAT], S)                    # the panes are neither baked nor occluders: their texels are filled flat
        else:
            mask = np.zeros((S, S), bool)
        for light_set, idx, samples in (("day", n, SAMPLES), ("night", n + NIGHT_OFFSET, NIGHT_SAMPLES)):
            t0 = time.time()
            rgb = bake_set(n, objs, S, light_set, samples)
            peak = rgb.max(axis=2)
            sel = (peak > 1e-5) & ~mask
            pc = np.percentile(peak[sel], [50, 90, 99, 99.5, 100]) if sel.any() else [1.0] * 5
            scale = float(pc[3])                                  # the 99.5th percentile of the lit texels maps to white; the few hotter ones clip
            print(f"  {light_set} texel percentiles p50 p90 p99 p99.5 max:", [round(float(v), 3) for v in pc])
            if mask.any():
                rgb[mask] = scale * (PANE_DAY if light_set == "day" else PANE_NIGHT)
            out = np.ones((S, S, 4), np.float32)
            out[..., :3] = srgb_encode(rgb / scale)
            png = bpy.data.images.new(f"LM_{idx}_png", S, S, alpha=False)
            png.colorspace_settings.name = "Non-Color"
            png.pixels.foreach_set(out.ravel())
            png.filepath_raw = str(stage_work() / f"{SCENE}_{idx}.png")
            png.file_format = "PNG"
            png.save()
            bpy.data.images.remove(png)
            key, kkey = ("lightmap", "lightmap_intensity") if light_set == "day" else ("lightmap_night", "lightmap_night_intensity")
            for o in objs:
                for slot in o.material_slots:
                    slot.material[key] = LM_URL.format(idx)
                    slot.material[kkey] = round(math.pi * scale, 4)
            report[idx] = {"map": n, "set": light_set, "size": S, "px_per_m": round(dens, 1), "px_per_m_scaled": small, "scale": round(scale, 4),
                           "p50_p90_p99_p995_max": [round(float(v), 3) for v in pc], "samples": samples, "device": bpy.context.scene.cycles.device,
                           "seconds": round(time.time() - t0), "mean": round(float(rgb.mean()), 4), "materials": mats}
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


def scrub_ui_paths():
    """The startup layout's file browser remembers the machine's home folder; the .blend is public, so it keeps "//" instead."""
    for sc in bpy.data.screens:
        for a in sc.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"_" * 1000
                    sp.params.directory = b"//"


KEEP_PROPS = {"lightmap", "lightmap_intensity", "lightmap_night", "lightmap_night_intensity"}   # the only custom properties this scene carries (on materials, for the page)
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
    apply_light_set("export")                         # Lamp_Emit and Emergency_Emit both at the strength the page switches on
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
    apply_light_set("day")
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
    light_set = arg("--set", "day")
    apply_light_set(light_set)
    setup_cycles(arg("--render-samples", 128, int))     # the stills' own count, so --stage all can bake at 256 and render at 128
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = arg("--noise", 0.03, float)
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = arg("--view", "AgX")      # "Standard": no tone mapping, as the page draws (a preview of its brightness)
    if sc.view_settings.view_transform == "AgX":
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
    n4, a4, _ = shop_slots()[2]
    shots = {
        "1_arrival": look_cam("arrival", (arrive[0], 1.6, arrive[2]), (arrive[0] + face[0] * 3, 1.6, arrive[2] + face[1] * 3), 75.0),
        "2_wide": look_cam("wide", (HX - DECK_D - 0.9, 1.8, HZ - DECK_D - 0.6), (-HX / 4, 2.6, -HZ / 2), 78.0),        # from the south-east, just clear of the gallery
        "3_detail": look_cam("detail", (FX1 + 3.4, 1.45, FZ1 + 2.6), (FCX + 0.6, 1.5, FZ0 - 1.0), 58.0),
    }
    plan = look_cam("plan", (0, H + 8, 0), None, ortho=2 * HX + 1.2)
    arts = list(bpy.data.collections["Art"].objects) + list(bpy.data.collections["Standins"].objects)
    cut_plan = [o for o in arts if o.name.startswith(("Ceiling_", "Skylight_", "Gallery_", "Soffit_", "decor_sheet", "Emergency_Brackets", "Exit_"))]
    todo = [(k, v, (1920, 1080)) for k, v in shots.items()] + [("4_plan", plan, (1800, 1350))]
    suffix = "" if light_set == "day" else "_" + light_set
    for key, cam, (w, h) in todo:
        if which not in ("all", key):
            continue
        sc.camera = cam
        sc.view_settings.exposure = expo + (1.0 if key == "4_plan" else 0.0)      # the plan (the owner's sheet only) is lifted to read on a phone
        for o in arts:
            o.visible_camera = True
        for o in {"4_plan": cut_plan}.get(key, []):
            o.visible_camera = False                      # a cut-away view: these stay in the atrium for the light and the shadows, the camera just does not see them
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, arg("--scale", 100, int)
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        to_docs = key != "4_plan" and light_set == "day" and not arg("--work-stills")
        path = STILLS / f"{key}.jpg" if to_docs else stage_work() / f"{key}{suffix}.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 400_000 and q > 40 and key != "4_plan":
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        strip_jpeg_comments(path)
        print("STILL", key, path, path.stat().st_size, "q", q)
    for o in arts:
        o.visible_camera = True
    apply_light_set("day")


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
