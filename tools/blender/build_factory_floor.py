"""Builds the Farway factory floor in Blender, lights and bakes it, and exports world/factory_floor.glb (docs/BLENDER.md, "4. factory_floor").

Re-runnable, from the repo root:

    blender -b --python tools/blender/build_factory_floor.py                       (every stage, in one run)
    blender -b --python tools/blender/build_factory_floor.py -- --stage art        (build the art, save blender/scenes/factory_floor.blend)
    blender -b blender/scenes/factory_floor.blend --python tools/blender/build_factory_floor.py -- --stage bake [--samples 256] [--device cpu]
    blender -b blender/scenes/factory_floor.blend --python tools/blender/build_factory_floor.py -- --stage export
    blender -b blender/scenes/factory_floor.blend --python tools/blender/build_factory_floor.py -- --stage axes     (the marker-cube axes check)
    blender -b blender/scenes/factory_floor.blend --python tools/blender/build_factory_floor.py -- --stage render [--samples 128] [--only 1_arrival]
    blender -b --python tools/blender/build_factory_floor.py -- --stage textures --src <folder of the Poly Haven downloads>   (re-derive the textures)

Stages: art (geometry, materials, lights, stand-ins) -> bake (merge by material, lightmap UV, Cycles bake, OIDN denoise, 8-bit PNGs in the work
folder) -> export (GLB; tools/blender/pack_scene.py then makes world/factory_floor.glb with WebP textures and world/lightmaps/factory_floor_<n>.webp)
-> axes -> render (the three review stills and a plan view).

No coordinate of the layout is typed in here: the hall, its colliders, the belt, the three bins and the door come from
blender/layout/factory_floor.json (node tools/blender/dump_layout.mjs factory_floor). A game point (x, y, z) is Blender (x, -z, y). Only the art the
layout does not name (a truss, a lamp, a roller) is placed here, relative to those boxes. The page keeps drawing the moving parts, the belt's top
surface (its top 6 cm) and the sign over each bin (docs/BLENDER.md, contract 4): the art leaves those spots clear, and the art stage checks that
(KEEPOUT below).
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

SCENE = "factory_floor"
ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / f"blender/layout/{SCENE}.json"
TEX = ROOT / f"blender/textures/{SCENE}"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"    # the path the page reads from the material's `lightmap` custom property
MARGIN_PX = 8

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 256, int)
DEVICE = arg("--device", "auto")
ENGINE = arg("--engine", "CYCLES")

L = json.loads(LAYOUT.read_text()) if LAYOUT.exists() else None
if L is None and STAGE != "textures":
    raise SystemExit(f"no {LAYOUT.relative_to(ROOT)}: run `node tools/blender/dump_layout.mjs {SCENE}` first")
K = L["constants"] if L else {}
COLLIDERS = {c["s"]: c for c in L["world"]["colliders"]} if L else {}
if L is not None and not all(k in K for k in ("half", "h", "belt", "bins", "door")):
    raise SystemExit(f"{LAYOUT.relative_to(ROOT)} lacks constants (half, h, belt, bins, door): re-run `node tools/blender/dump_layout.mjs {SCENE}`")
HX, HZ = K["half"] if L else (0, 0)
H = K["h"] if L else 0

# What the page draws (index.html factoryProps): the belt's top surface, a slab from belt.top - 0.06 to belt.top over the belt collider's x span and
# the belt's width less 5 cm a side; the parts on it (0.4 x 0.3 x 0.4 boxes sitting on belt.top); the sign over each bin, a 1.6 x 0.36 m plane at
# y 1.5 over the bin's centre, facing +z. The art keeps out of these boxes (game coordinates); the art stage prints a PASS/FAIL line per box.
BELT_SKIN = 0.06
SIGN_Y, SIGN_W, SIGN_H = 1.5, 1.6, 0.36


def keepout_boxes():
    b, c = K["belt"], COLLIDERS["Belt"]
    out = [("belt top surface and the parts on it", (c["min"][0] - 0.01, b["top"] - BELT_SKIN, b["z"] - b["w"] / 2 + 0.05), (c["max"][0] + 0.01, b["top"] + 0.32, b["z"] + b["w"] / 2 - 0.05))]
    for bn in K["bins"]:
        out.append((f"sign {bn['kind']}", (bn["x"] - SIGN_W / 2 - 0.05, SIGN_Y - SIGN_H / 2 - 0.05, bn["z"] - 0.06), (bn["x"] + SIGN_W / 2 + 0.05, SIGN_Y + SIGN_H / 2 + 0.05, bn["z"] + 0.06)))
    return out


def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


def srgb_lin(hexcol):
    """an sRGB hex colour (as the page's KINDS give them) -> linear RGB for a Blender material"""
    c = [((hexcol >> s) & 255) / 255 for s in (16, 8, 0)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


# KINDS in shared/factory.js (not exported to the layout file): the page colours its parts and the blockout's bins with them.
KIND_HEX = {"gears": 0xc8a040, "bolts": 0x7a8aa0, "springs": 0x50a060}

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


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, diff=None, factor=None, emit=None, img=None, emit_img=None, alpha=None, tile=None):
    """`factor` multiplies a texture (the glTF exporter writes it as baseColorFactor), so one neutral texture serves several paints."""
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

    def tex(im):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = im
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        return n

    src = None
    if diff:
        src = tex(image(diff)).outputs["Color"]
    if img is not None:
        src = tex(img).outputs["Color"]
    if src is not None:
        if factor is not None:
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = 1.0
            nt.links.new(src, mix.inputs[6])
            mix.inputs[7].default_value = (*factor, 1)
            nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        else:
            nt.links.new(src, bsdf.inputs["Base Color"])
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    if emit_img is not None:
        bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
        nt.links.new(tex(emit_img).outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emit_img.get("strength", 1.0)
    if alpha is not None:
        if isinstance(alpha, float):
            bsdf.inputs["Alpha"].default_value = alpha
        else:
            nt.links.new(tex(alpha).outputs["Alpha"], bsdf.inputs["Alpha"])
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    TILES[name] = tile or 1.0
    MATS[name] = m
    return m


SODIUM = (1.0, 0.55, 0.20)
DAYLIGHT = (0.78, 0.86, 1.0)


def make_materials(gen):
    # the shell (lightmap 0)
    material("Floor_Concrete", diff="concrete_floor_diff.jpg", rough=0.85, tile=2.0)
    material("Wall_Brick", diff="brick_diff.jpg", rough=0.9, tile=1.5)
    material("Wall_Dado", diff="brick_diff.jpg", factor=(0.16, 0.30, 0.20), rough=0.5, tile=1.5)       # the brick, painted works green to 1.3 m
    material("Roof_Sheet", diff="roof_sheet_diff.jpg", rough=0.6, metal=0.3, tile=1.12)
    material("Floor_Paint", color=(0.80, 0.55, 0.03), rough=0.6)
    material("Floor_Hazard", img=gen["hazard"], rough=0.6, tile=0.4)
    material("Decal_Grime", img=gen["stain"], alpha=gen["stain"], rough=0.9)
    material("Decal_Print", img=gen["atlas"], rough=0.6)
    material("Shutter_Steel", diff="roof_sheet_diff.jpg", factor=(0.30, 0.34, 0.38), rough=0.5, metal=0.3)
    # the structure and the machines (lightmap 1)
    material("Steel_Green", diff="paint_green_diff.jpg", rough=0.55, tile=1.0)
    material("Steel_Dark", color=(0.035, 0.037, 0.04), rough=0.5, metal=0.6)
    material("Steel_Galv", diff="paint_grime_diff.jpg", factor=(0.55, 0.57, 0.58), rough=0.4, metal=0.7, tile=1.0)
    material("Paint_Yellow", diff="paint_grime_diff.jpg", factor=(0.85, 0.52, 0.02), rough=0.5, tile=1.0)
    material("Paint_Red", diff="paint_grime_diff.jpg", factor=(0.42, 0.06, 0.05), rough=0.5, tile=1.0)
    material("Motor_Paint", diff="paint_grime_diff.jpg", factor=(0.10, 0.17, 0.26), rough=0.45, tile=1.0)
    material("Panel_Grey", diff="paint_grime_diff.jpg", factor=(0.45, 0.46, 0.44), rough=0.5, tile=1.0)
    material("Rubber_Black", color=(0.025, 0.025, 0.025), rough=0.85)
    material("Wood_Pallet", diff="wood_diff.jpg", factor=(1.3, 1.15, 0.9), rough=0.8, tile=0.9)
    for k in K["bins"]:
        material(f"Bin_{k['kind'].capitalize()}", diff="paint_grime_diff.jpg", factor=srgb_lin(KIND_HEX[k["kind"]]), rough=0.5, tile=1.0)
    material("Paint_White", color=(0.75, 0.75, 0.72), rough=0.5)
    # not baked: what glows (the page shows them as exported)
    material("Lamp_Emit", color=(1.0, 0.7, 0.4), rough=0.4, emit=(SODIUM, 10.0))
    material("Glass_Daylight", color=(0.6, 0.65, 0.7), rough=0.3, emit=(DAYLIGHT, arg("--day", 3.0, float)))
    material("Exit_Sign_Emit", emit_img=gen["exit"], rough=0.4)
    material("Indicator_Green", color=(0.0, 0.2, 0.05), rough=0.3, emit=((0.1, 1.0, 0.25), 5.0))


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


def bar(bm, p0, p1, w, h=None):
    """A box of section w x h from game point p0 to p1 (a truss member, a brace)."""
    a, b = B(p0), B(p1)
    d = b - a
    x = d.normalized()
    ref = Vector((0, 0, 1)) if abs(x.z) < 0.95 else Vector((0, 1, 0))
    y = ref.cross(x).normalized()
    z = x.cross(y)
    M = Matrix(((x.x * d.length, y.x * w, z.x * (h or w), 0), (x.y * d.length, y.y * w, z.y * (h or w), 0), (x.z * d.length, y.z * w, z.z * (h or w), 0), (0, 0, 0, 1)))
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((a + b) / 2) @ M)


def quad(bm, p0, p1, p2, p3):
    vs = [bm.verts.new(B(p)) for p in (p0, p1, p2, p3)]
    return bm.faces.new(vs)


def frustum(bm, y0, y1, c, s0, s1):
    """An open-topped square funnel: s0 x s0 (x, z) at y0, s1 x s1 at y1, centred on c = (x, z); a rim at the top."""
    def ring(y, s):
        return [bm.verts.new(B((c[0] + dx * s / 2, y, c[1] + dz * s / 2))) for dx, dz in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    lo, hi = ring(y0, s0), ring(y1, s1)
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))


def box_uv(bm, tile):
    """UV0: box projection in metres / tile, from world positions, so a texture runs on across the pieces of a wall."""
    uvl = bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y             # back to game axes
            if ax == 0:
                u, v = gz, gy
            elif ax == 1:
                u, v = gx, gy
            else:
                u, v = gx, gz
            lp[uvl].uv = (u / tile, v / tile)


ART = STANDIN = None


def finish(name, bm, mat, coll, smooth=False, tile=None, sharp_deg=35, keep_uv=False):
    for e in bm.edges:
        if smooth and len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) < math.radians(sharp_deg)
        else:
            e.smooth = not (len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(1))
    for f in bm.faces:
        f.smooth = smooth
    if not keep_uv:
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


def part(name, mat, build, smooth=False, tile=None, coll=None):
    bm = bmesh.new()
    build(bm)
    return finish(name, bm, mat, coll or ART, smooth, tile)


def panel(name, mat, centre, normal, up, w, h, uv=(0, 0, 1, 1), rot=False, coll=None):
    """A flat quad facing `normal` (a game vector), `up` its picture's up (a game vector), w x h metres, its UV0 the rect uv=(u0, v0, u1, v1);
    rot turns the picture a quarter (the shutter's ribs run across)."""
    n, u = Vector(normal).normalized(), Vector(up).normalized()
    r = (-n).cross(u)                                     # a viewer looking at the face (along -n) has this on their right
    c = Vector(centre)
    pts = [c - r * w / 2 - u * h / 2, c + r * w / 2 - u * h / 2, c + r * w / 2 + u * h / 2, c - r * w / 2 + u * h / 2]
    bm = bmesh.new()
    f = quad(bm, *[tuple(p) for p in pts])
    uvl = bm.loops.layers.uv.new("UVMap")
    u0, v0, u1, v1 = uv
    corners = ((u0, v0), (u1, v0), (u1, v1), (u0, v1)) if not rot else ((u0, v1), (u0, v0), (u1, v0), (u1, v1))
    for lp, t in zip(f.loops, corners):
        lp[uvl].uv = t
    return finish(name, bm, mat, coll or ART, keep_uv=True)


def disc(name, mat, centre, normal, up, r, uv_rect, seg=32, coll=None):
    """A flat round face (the clock's dial) with its UVs mapped into uv_rect of an atlas."""
    n, u = Vector(normal).normalized(), Vector(up).normalized()
    rt = (-n).cross(u)
    c = Vector(centre)
    bm = bmesh.new()
    pts = [c + rt * r * math.cos(2 * math.pi * i / seg) + u * r * math.sin(2 * math.pi * i / seg) for i in range(seg)]
    f = bm.faces.new([bm.verts.new(B(tuple(p))) for p in pts])
    uvl = bm.loops.layers.uv.new("UVMap")
    u0, v0, u1, v1 = uv_rect
    for i, lp in enumerate(f.loops):
        a = 2 * math.pi * i / seg
        lp[uvl].uv = (u0 + (u1 - u0) * (0.5 + 0.5 * math.cos(a)), v0 + (v1 - v0) * (0.5 + 0.5 * math.sin(a)))
    return finish(name, bm, mat, coll or ART, keep_uv=True)


def wpt(wall, s, y, t):
    """a point on a wall: `s` along it (z on the west and east walls, x on the north and south), `t` out from its face into the room"""
    return {"W": (-HX + t, y, s), "E": (HX - t, y, s), "N": (s, y, -HZ + t), "S": (s, y, HZ - t)}[wall]


def wbox(bm, wall, a, b):
    p, q = wpt(wall, *a), wpt(wall, *b)
    cube(bm, tuple(min(p[i], q[i]) for i in range(3)), tuple(max(p[i], q[i]) for i in range(3)))


WALL_N = {"N": (0, 0, 1), "S": (0, 0, -1), "W": (1, 0, 0), "E": (-1, 0, 0)}     # each wall's inward normal (game)


# ---------------------------------------------------------------- the layout's derived numbers
BELT = {}
TRUSS_X = []          # the roof trusses (and the wall columns under them): every 4 m, the gable walls carry the ends
DOOR_W, DOOR_H = 2.4, 2.8             # the way out: a pair of steel leaves in the south wall at the door spot's x (the blockout's is 2.4 x 2.6 m)
SHUTTER = {}


def derive():
    b, c = K["belt"], COLLIDERS["Belt"]
    BELT.update(x0=c["min"][0], x1=c["max"][0], z0=c["min"][2], z1=c["max"][2], zc=b["z"], top=b["top"], frame=b["top"] - BELT_SKIN,
                feed=b["x0"], end=b["x1"])
    n = int(round(2 * HX / 4.0))
    TRUSS_X[:] = [-HX + 2 * HX * i / n for i in range(1, n)]
    SHUTTER.update(z0=-0.5, z1=3.5, h=4.2)                       # a closed loading door in the west wall, clear of the belt's west end
    # where the shutter goes is art only (no collider): it must not reach the belt's or a bin's spot
    assert SHUTTER["z0"] > BELT["z1"] + 1.0


# ---------------------------------------------------------------- the shell
def build_shell():
    """The hall's six slabs, straight from the collision file's boxes (Floor_*, Ceiling_*, Wall_*), so art and colliders agree."""
    for s, c in COLLIDERS.items():
        mn, mx = c["min"], c["max"]
        if s.startswith("Floor"):
            part(s, "Floor_Concrete", lambda bm: cube(bm, mn, mx))
        elif s.startswith("Ceiling"):
            part(s, "Roof_Sheet", lambda bm: cube(bm, mn, mx))
        elif s.startswith("Wall_"):
            part(s, "Wall_Brick", lambda bm: cube(bm, mn, mx))


def wall_runs(y0, y1, depth, gaps):
    """Boxes along the four walls' inner faces from y0 to y1, `depth` proud, skipping each gap (wall, a, b): a range along the wall."""
    out = []
    for wall in "NSWE":
        lo, hi = (-HX, HX) if wall in "NS" else (-HZ + depth, HZ - depth)
        spans = [(lo, hi)]
        for gw, a, b in gaps:
            if gw == wall:
                spans = [p for s0, s1 in spans for p in ((s0, min(s1, a)), (max(s0, b), s1)) if p[1] - p[0] > 0.01]
        for a, b in spans:
            out.append((wall, (a, y0, 0.0), (b, y1, depth)))
    return out


def build_walls():
    """The painted dado (the brick painted green to 1.3 m, with a black line), the wall columns under each truss, the crane's corbels."""
    gaps = [("S", K["door"]["at"][0] - DOOR_W / 2 - 0.1, K["door"]["at"][0] + DOOR_W / 2 + 0.1), ("W", SHUTTER["z0"] - 0.12, SHUTTER["z1"] + 0.12)]
    dado = wall_runs(0.0, 1.30, 0.003, gaps)
    line = wall_runs(1.30, 1.36, 0.004, gaps)
    for wall in "NSWE":
        rr = [(a, b) for w, a, b in dado if w == wall]
        part(f"Wall_Dado_{wall}", "Wall_Dado", lambda bm: [wbox(bm, wall, a, b) for a, b in rr])
        rr2 = [(a, b) for w, a, b in line if w == wall]
        part(f"Wall_DadoLine_{wall}", "Steel_Dark", lambda bm: [wbox(bm, wall, a, b) for a, b in rr2])
    # steel stanchions set into the long walls under each truss: an H column, its flange 4.5 cm proud of the brick (the wall's plan + 5 cm)
    for wall in "NS":
        for i, x in enumerate(TRUSS_X):
            def col(bm, x=x, wall=wall):
                wbox(bm, wall, (x - 0.16, 0.0, 0.0), (x + 0.16, H - 0.1, 0.012))           # the flange
                wbox(bm, wall, (x - 0.012, 0.0, 0.0), (x + 0.012, H - 0.1, 0.045))         # the web's edge
                wbox(bm, wall, (x - 0.16, 0.0, 0.030), (x + 0.16, H - 0.1, 0.045))         # the front flange
                wbox(bm, wall, (x - 0.24, 0.0, 0.0), (x + 0.24, 0.025, 0.045))             # the base plate
            part(f"Column_{wall}{i}", "Steel_Green", col)
            part(f"Column_{wall}{i}_Bolts", "Steel_Dark", lambda bm, x=x, wall=wall: [wbox(bm, wall, (x + dx - 0.02, 0.025, 0.0), (x + dx + 0.02, 0.06, 0.04)) for dx in (-0.19, 0.19)])
            part(f"Corbel_{wall}{i}", "Steel_Green", lambda bm, x=x, wall=wall: (wbox(bm, wall, (x - 0.12, CRANE_Y - 0.35, 0.045), (x + 0.12, CRANE_Y, 0.42)),
                                                                                 bar(bm, wpt(wall, x, CRANE_Y - 0.9, 0.045), wpt(wall, x, CRANE_Y - 0.3, 0.38), 0.08)))


# ---------------------------------------------------------------- the roof: trusses, purlins, the crane, the lamps
BOT_Y, TOP_Y = H - 1.12, H - 0.12      # the trusses' bottom and top chords (centre lines); the purlins sit on the top chord, under the roof sheets
CHORD = 0.13
CRANE_Y = 4.3                          # the crane runway's underside on the corbels


def truss(bm, x):
    zs = np.linspace(-HZ, HZ, 11)
    bar(bm, (x, BOT_Y, -HZ), (x, BOT_Y, HZ), CHORD, CHORD)
    bar(bm, (x, TOP_Y, -HZ), (x, TOP_Y, HZ), CHORD, CHORD)
    for z in zs[1:-1]:
        bar(bm, (x, BOT_Y, z), (x, TOP_Y, z), 0.08, 0.08)
    for k in range(len(zs) - 1):
        za, zb = zs[k], zs[k + 1]
        if (za + zb) / 2 < 0:                          # Pratt: the diagonals fall toward the middle
            bar(bm, (x, TOP_Y, za), (x, BOT_Y, zb), 0.07, 0.07)
        else:
            bar(bm, (x, BOT_Y, za), (x, TOP_Y, zb), 0.07, 0.07)
    for z in (-HZ + 0.05, HZ - 0.05):                  # the bearing on the column
        cube(bm, (x - 0.18, BOT_Y - 0.12, z - 0.05 if z < 0 else z - 0.25), (x + 0.18, TOP_Y + 0.06, z + 0.25 if z < 0 else z + 0.05))


def build_roof():
    for i, x in enumerate(TRUSS_X):
        part(f"Roof_Truss_{i}", "Steel_Green", lambda bm, x=x: truss(bm, x))

    def purlins(bm):
        for z in np.linspace(-HZ + 0.7, HZ - 0.7, 9):
            cube(bm, (-HX, TOP_Y + CHORD / 2, z - 0.04), (HX, H - 0.005, z + 0.04))
    part("Roof_Purlins", "Steel_Green", purlins)
    # the crane: runway beams on the corbels along both long walls, a double-girder bridge, its hoist with the hook raised
    def runway(bm):
        for zf in (-HZ, HZ):
            s = 1 if zf < 0 else -1
            cube(bm, (-HX, CRANE_Y, min(zf + s * 0.12, zf + s * 0.40)), (HX, CRANE_Y + 0.34, max(zf + s * 0.12, zf + s * 0.40)))
    part("Crane_Runway", "Steel_Green", runway)
    part("Crane_Rails", "Steel_Dark", lambda bm: [cube(bm, (-HX, CRANE_Y + 0.34, zf - 0.03), (HX, CRANE_Y + 0.39, zf + 0.03)) for zf in (-HZ + 0.26, HZ - 0.26)])
    cx = (TRUSS_X[len(TRUSS_X) // 2] + TRUSS_X[len(TRUSS_X) // 2 + 1]) / 2 + 0.2 if len(TRUSS_X) > 2 else 0.0     # parked between two trusses

    def bridge(bm):
        for dx in (-0.28, 0.28):
            cube(bm, (cx + dx - 0.09, CRANE_Y + 0.42, -HZ + 0.15), (cx + dx + 0.09, CRANE_Y + 0.95, HZ - 0.15))
        for zf in (-HZ + 0.26, HZ - 0.26):
            cube(bm, (cx - 0.65, CRANE_Y + 0.39, zf - 0.16), (cx + 0.65, CRANE_Y + 0.62, zf + 0.16))        # the end carriages
        tz = 1.2
        cube(bm, (cx - 0.33, CRANE_Y + 0.95, tz - 0.45), (cx + 0.33, CRANE_Y + 1.25, tz + 0.45))           # the hoist trolley
        cube(bm, (cx - 0.12, CRANE_Y - 0.65, tz - 0.16), (cx + 0.12, CRANE_Y - 0.35, tz + 0.16))           # the hook block
    part("Crane_Bridge", "Paint_Yellow", bridge)
    part("Crane_Hook", "Steel_Dark", lambda bm: (cyl(bm, (cx, CRANE_Y - 0.35, 1.08), (cx, CRANE_Y + 0.95, 1.08), 0.012, 0.012, 6, False),
                                                 cyl(bm, (cx, CRANE_Y - 0.35, 1.32), (cx, CRANE_Y + 0.95, 1.32), 0.012, 0.012, 6, False),
                                                 cyl(bm, (cx, CRANE_Y - 0.80, 1.2), (cx, CRANE_Y - 0.65, 1.2), 0.03, 0.03, 8),
                                                 bar(bm, (cx, CRANE_Y - 0.80, 1.2), (cx, CRANE_Y - 0.95, 1.32), 0.05),
                                                 bar(bm, (cx, CRANE_Y - 0.95, 1.32), (cx, CRANE_Y - 0.84, 1.44), 0.05)), smooth=True)
    part("Crane_Hazard", "Floor_Hazard", lambda bm: [cube(bm, (cx + s * 0.371, CRANE_Y + 0.5, -2.0), (cx + s * 0.372 + s * 0.002, CRANE_Y + 0.85, 2.0)) for s in (-1, 1)], tile=0.4)


LAMP_ROWS = []                          # high-bay rows (game z): over the belt and over the bins
LAMP_Y = 4.0                            # the lens's underside


def lamp_spots():
    return [(x, z) for x in TRUSS_X for z in LAMP_ROWS]


def build_lamps():
    def housings(bm):
        for x, z in lamp_spots():
            cyl(bm, (x, LAMP_Y + 0.55, z), (x, BOT_Y - CHORD / 2, z), 0.01, 0.01, 6, False)        # the drop rod
            cyl(bm, (x, LAMP_Y + 0.30, z), (x, LAMP_Y + 0.55, z), 0.15, 0.13, 16)                  # the gear housing
    part("Lamp_Housings", "Steel_Dark", housings, smooth=True)
    part("Lamp_Reflectors", "Steel_Galv", lambda bm: [cyl(bm, (x, LAMP_Y, z), (x, LAMP_Y + 0.30, z), 0.33, 0.14, 24, False) for x, z in lamp_spots()], smooth=True)
    part("Lamp_Lenses", "Lamp_Emit", lambda bm: [cyl(bm, (x, LAMP_Y + 0.02, z), (x, LAMP_Y + 0.05, z), 0.30, 0.30, 24) for x, z in lamp_spots()], smooth=True)


# ---------------------------------------------------------------- the belt: frame and rollers up to the page's surface, the feed, the drive, the chute
def build_belt():
    x0, x1, z0, z1, fr = BELT["x0"], BELT["x1"], BELT["z0"], BELT["z1"], BELT["frame"]
    zi0, zi1 = z0 + 0.04, z1 - 0.04
    # skirt guards along both sides, a hand's width above the surface (outside the page's slab, which stops 5 cm in from the collider's sides)
    part("Belt_Guards", "Steel_Green", lambda bm: (cube(bm, (x0, fr - 0.26, z0), (x1, BELT["top"] + 0.03, zi0)), cube(bm, (x0, fr - 0.26, zi1), (x1, BELT["top"] + 0.03, z1))))
    part("Belt_Stringers", "Steel_Green", lambda bm: (cube(bm, (x0, fr - 0.24, zi0), (x1, fr - 0.10, zi0 + 0.05)), cube(bm, (x0, fr - 0.24, zi1 - 0.05), (x1, fr - 0.10, zi1))))
    legs = np.linspace(x0 + 0.06, x1 - 0.06, 10)            # end posts at both ends, under the drums

    def legs_fn(bm):
        for x in legs:
            for z in (zi0 + 0.04, zi1 - 0.04):
                cube(bm, (x - 0.035, 0.012, z - 0.035), (x + 0.035, fr - 0.24, z + 0.035))
            bar(bm, (x, 0.16, zi0 + 0.04), (x, 0.16, zi1 - 0.04), 0.05)
            bar(bm, (x, 0.18, zi0 + 0.04), (x, fr - 0.26, zi1 - 0.04), 0.035)
    part("Belt_Legs", "Steel_Green", legs_fn)
    part("Belt_Feet", "Steel_Dark", lambda bm: [cube(bm, (x - 0.08, 0.0, z - 0.08), (x + 0.08, 0.012, z + 0.08)) for x in legs for z in (zi0 + 0.04, zi1 - 0.04)])
    # the carrying rollers, their tops 5 mm under the page's surface; the return rollers below
    r = 0.045
    xs = np.arange(x0 + 0.5, x1 - 0.45, 0.4)
    part("Belt_Rollers", "Steel_Galv", lambda bm: ([cyl(bm, (x, fr - 0.005 - r, zi0 + 0.05), (x, fr - 0.005 - r, zi1 - 0.05), r, r, 12) for x in xs] +
                                                   [cyl(bm, (x, 0.30, zi0 + 0.05), (x, 0.30, zi1 - 0.05), 0.04, 0.04, 12) for x in np.arange(x0 + 1.2, x1 - 1.0, 1.8)]), smooth=True)
    # the head and tail drums (the belt wraps them: rubber-lagged), and the return run of the belt under the frame
    dr = 0.20
    dxs = (x0 + dr + 0.02, x1 - dr - 0.02)
    yc = fr - dr

    def drums(bm):
        for x in dxs:
            cyl(bm, (x, yc, zi0 + 0.06), (x, yc, zi1 - 0.06), dr, dr, 24)
        rz0, rz1 = zi0 + 0.08, zi1 - 0.08
        cube(bm, (dxs[0] + 0.5, 0.345, rz0), (dxs[1] - 0.5, 0.355, rz1))
        for xa, xb in ((dxs[0], dxs[0] + 0.5), (dxs[1], dxs[1] - 0.5)):
            bar(bm, (xa, yc - dr - 0.005, (rz0 + rz1) / 2), (xb, 0.35, (rz0 + rz1) / 2), rz1 - rz0, 0.01)
    part("Belt_Drums", "Rubber_Black", drums, smooth=True)
    part("Belt_Shafts", "Steel_Dark", lambda bm: [cyl(bm, (x, yc, z0 + 0.01), (x, yc, z1 - 0.01), 0.035, 0.035, 10) for x in dxs], smooth=True)
    # the drive at the head (east) end: a motor and a gearbox under the frame, a chain guard to the drum's shaft
    hx = dxs[1]
    part("Belt_Motor", "Motor_Paint", lambda bm: (cyl(bm, (hx - 1.25, 0.36, z0 + 0.30), (hx - 0.60, 0.36, z0 + 0.30), 0.14, 0.14, 20),
                                                  cube(bm, (hx - 0.60, 0.18, z0 + 0.10), (hx - 0.15, 0.56, z0 + 0.48)),
                                                  cube(bm, (hx - 1.20, 0.12, z0 + 0.12), (hx - 0.62, 0.20, z0 + 0.48))), smooth=True)
    part("Belt_ChainGuard", "Paint_Yellow", lambda bm: bar(bm, (hx - 0.36, 0.42, z0 + 0.135), (hx, yc, z0 + 0.135), 0.24, 0.05))
    # the feed at the tail (west) end: a hood the parts come out of, under a duct from a hopper hung from the roof
    hx0, hx1, hy = x0 - 0.04, BELT["feed"] - 0.15, BELT["top"] + 0.58

    def hood(bm):
        cube(bm, (hx0, fr, z0), (hx0 + 0.03, hy, z1))                       # its back
        cube(bm, (hx0, BELT["top"] + 0.03, z0), (hx1, hy, zi0))            # its sides, over the guards
        cube(bm, (hx0, BELT["top"] + 0.03, zi1), (hx1, hy, z1))
        cube(bm, (hx0, hy - 0.03, z0), (hx1, hy, z1))                      # its roof
        cube(bm, (hx1 - 0.02, hy - 0.10, z0), (hx1 + 0.01, hy, z1))        # the lip over the mouth
    part("Belt_FeedHood", "Steel_Galv", hood)
    part("Belt_FeedCurtain", "Rubber_Black", lambda bm: [cube(bm, (hx1 - 0.015, BELT["top"] + 0.36, z), (hx1 - 0.005, hy - 0.10, z + 0.1)) for z in np.arange(zi0 + 0.02, zi1 - 0.1, 0.11)])
    dz = BELT["zc"]
    hop = ((hx0 + hx1) / 2 + 0.05, dz)
    part("Belt_FeedDuct", "Steel_Galv", lambda bm: cube(bm, (hop[0] - 0.16, hy, dz - 0.2), (hop[0] + 0.16, 3.2, dz + 0.2)))
    part("Hopper", "Steel_Galv", lambda bm: (frustum(bm, 3.2, 4.0, hop, 0.42, 1.3), cube(bm, (hop[0] - 0.68, 4.0, dz - 0.68), (hop[0] + 0.68, 4.12, dz + 0.68)),
                                              [cyl(bm, (hop[0] + sx * 0.6, 4.12, dz + sz * 0.6), (hop[0] + sx * 0.6, TOP_Y, dz + sz * 0.6), 0.012, 0.012, 6, False) for sx in (-1, 1) for sz in (-1, 1)]))
    # the pull-cord stop along the aisle side, on posts on the guard, and the control box at the feed end
    zs = z1 - 0.02
    part("Belt_CordPosts", "Steel_Dark", lambda bm: [cube(bm, (x - 0.012, BELT["top"] + 0.03, zs - 0.012), (x + 0.012, BELT["top"] + 0.18, zs + 0.012)) for x in np.linspace(x0 + 0.4, x1 - 0.4, 8)])
    part("Belt_Cord", "Paint_Yellow", lambda bm: cyl(bm, (x0 + 0.4, BELT["top"] + 0.17, zs), (x1 - 0.4, BELT["top"] + 0.17, zs), 0.006, 0.006, 6, False))
    cbx = x0 + 0.05
    part("Belt_Control", "Panel_Grey", lambda bm: (cube(bm, (cbx, BELT["top"] + 0.08, z1 - 0.04), (cbx + 0.26, BELT["top"] + 0.40, z1 + 0.045)),
                                                   cube(bm, (cbx + 0.11, BELT["top"] + 0.03, z1 - 0.03), (cbx + 0.15, BELT["top"] + 0.08, z1 + 0.01))))
    part("Belt_Stop", "Paint_Red", lambda bm: cyl(bm, (cbx + 0.13, BELT["top"] + 0.28, z1 + 0.045), (cbx + 0.13, BELT["top"] + 0.28, z1 + 0.07), 0.035, 0.035, 16), smooth=True)
    part("Belt_Run", "Indicator_Green", lambda bm: cyl(bm, (cbx + 0.13, BELT["top"] + 0.16, z1 + 0.045), (cbx + 0.13, BELT["top"] + 0.16, z1 + 0.055), 0.018, 0.018, 12))
    # the reject chute past the head end and the skip it drops into: no collider is there (as in the blockout), so they are passable (decor_)
    sx0, sx1 = x1 + 0.12, min(x1 + 1.25, HX - 0.2)
    cz0, cz1 = dz - 0.42, dz + 0.42

    def chute(bm):
        x1 = BELT["x1"] + 0.015                                           # just past the belt's end (and the page's surface)
        quad(bm, (x1, fr - 0.03, cz0), (x1, fr - 0.03, cz1), (sx0 + 0.55, 0.62, cz1), (sx0 + 0.55, 0.62, cz0))
        quad(bm, (x1, fr - 0.03, cz0), (sx0 + 0.55, 0.62, cz0), (sx0 + 0.55, 0.82, cz0), (x1, fr + 0.12, cz0))
        quad(bm, (x1, fr - 0.03, cz1), (x1, fr + 0.12, cz1), (sx0 + 0.55, 0.82, cz1), (sx0 + 0.55, 0.62, cz1))
        bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=0.012)
    part("decor_reject_chute", "Paint_Red", chute)

    def skip(bm):
        t, sy = 0.03, 0.62
        cube(bm, (sx0, 0.08, cz0 - 0.3), (sx1, 0.12, cz1 + 0.3))
        cube(bm, (sx0, 0.08, cz0 - 0.3), (sx0 + t, sy, cz1 + 0.3))
        cube(bm, (sx1 - t, 0.08, cz0 - 0.3), (sx1, sy, cz1 + 0.3))
        cube(bm, (sx0, 0.08, cz0 - 0.3), (sx1, sy, cz0 - 0.3 + t))
        cube(bm, (sx0, 0.08, cz1 + 0.3 - t), (sx1, sy, cz1 + 0.3))
    part("decor_reject_skip", "Paint_Red", skip)
    part("decor_reject_skip_feet", "Steel_Dark", lambda bm: [cube(bm, (sx0 + 0.05, 0.0, z - 0.05), (sx1 - 0.05, 0.08, z + 0.05)) for z in (cz0 - 0.15, cz1 + 0.15)])
    # three parts that missed their bins, lying in the skip (the page's part boxes are 0.4 x 0.3 x 0.4, in the kinds' colours)
    for k, (kd, px, pz, ang) in enumerate((("gears", sx0 + 0.32, cz0 + 0.05, 12), ("springs", sx0 + 0.75, cz0 + 0.55, -25), ("bolts", sx0 + 0.45, cz1 + 0.05, 40))):
        def lump(bm, px=px, pz=pz, ang=ang, k=k):
            n0 = len(bm.verts)
            cube(bm, (px - 0.2, 0.12, pz - 0.2), (px + 0.2, 0.42, pz + 0.2))
            bm.verts.ensure_lookup_table()
            vs = [bm.verts[i] for i in range(n0, len(bm.verts))]
            bmesh.ops.rotate(bm, cent=B((px, 0.27, pz)), matrix=Matrix.Rotation(math.radians(ang), 3, "Z") @ Matrix.Rotation(math.radians(8 * (k - 1)), 3, "X"), verts=vs)
        part(f"decor_reject_part_{kd}", f"Bin_{kd.capitalize()}", lump)


# ---------------------------------------------------------------- the bins
def build_bins():
    for bn in K["bins"]:
        c = COLLIDERS["Bin_" + bn["kind"]]
        (x0, _, z0), (x1, y1, z1) = c["min"], c["max"]
        mat = f"Bin_{bn['kind'].capitalize()}"
        t = 0.03

        def body(bm):
            cube(bm, (x0 + 0.02, 0.10, z0 + 0.02), (x1 - 0.02, 0.36, z1 - 0.02))                       # the floor of the bin, solid below
            cube(bm, (x0, 0.10, z0), (x1, y1 - 0.03, z0 + t))
            cube(bm, (x0, 0.10, z1 - t), (x1, y1 - 0.03, z1))
            cube(bm, (x0, 0.10, z0), (x0 + t, y1 - 0.03, z1))
            cube(bm, (x1 - t, 0.10, z0), (x1, y1 - 0.03, z1))
        part(f"Bin_{bn['kind']}_Body", mat, body)

        def frame(bm):
            for xx, zz in ((x0, z0), (x1 - 0.06, z0), (x0, z1 - 0.06), (x1 - 0.06, z1 - 0.06)):
                cube(bm, (xx, 0.0, zz), (xx + 0.06, y1, zz + 0.06))                                   # the corner posts
            cube(bm, (x0, y1 - 0.04, z0), (x1, y1, z0 + 0.05))                                         # the top rim
            cube(bm, (x0, y1 - 0.04, z1 - 0.05), (x1, y1, z1))
            cube(bm, (x0, y1 - 0.04, z0), (x0 + 0.05, y1, z1))
            cube(bm, (x1 - 0.05, y1 - 0.04, z0), (x1, y1, z1))
            for zz in (z0 + 0.15, z1 - 0.25):                                                          # the fork skids
                cube(bm, (x0 + 0.02, 0.0, zz), (x1 - 0.02, 0.10, zz + 0.10))
        part(f"Bin_{bn['kind']}_Frame", "Steel_Dark", frame)
        # a pictogram plate on the side that faces the belt (and one on the side that faces the door): no words, the page hangs the sign
        for zf, nz in ((z0 - 0.002, -1), (z1 + 0.002, 1)):
            panel(f"Bin_{bn['kind']}_Plate{'N' if nz < 0 else 'S'}", "Decal_Print", (bn["x"], 0.62, zf), (0, 0, nz), (0, 1, 0), 0.34, 0.34, uv=ATLAS[bn["kind"]])


# ---------------------------------------------------------------- the way out, the loading door, the windows, the services, the dressing
def build_door():
    x, z = K["door"]["at"][0], HZ
    a, b = x - DOOR_W / 2, x + DOOR_W / 2

    def frame(bm):
        wbox(bm, "S", (a - 0.10, 0, 0), (a, DOOR_H + 0.10, 0.045))
        wbox(bm, "S", (b, 0, 0), (b + 0.10, DOOR_H + 0.10, 0.045))
        wbox(bm, "S", (a - 0.10, DOOR_H, 0), (b + 0.10, DOOR_H + 0.10, 0.045))
    part("Door_Frame", "Steel_Dark", frame)

    def leaves(bm):
        wbox(bm, "S", (a, 0.005, 0.0), (x - 0.005, DOOR_H, 0.035))
        wbox(bm, "S", (x + 0.005, 0.005, 0.0), (b, DOOR_H, 0.035))
        for c in ((a + x) / 2, (x + b) / 2):                                               # pressed panels
            for y0, y1 in ((0.25, 1.05), (1.75, 2.6)):
                wbox(bm, "S", (c - 0.45, y0, 0.035), (c + 0.45, y1, 0.042))
    part("Door_Leaves", "Steel_Green", leaves)
    part("Door_Bars", "Steel_Galv", lambda bm: [wbox(bm, "S", (c - 0.42, 1.0, 0.035), (c + 0.42, 1.06, 0.049)) for c in ((a + x) / 2, (x + b) / 2)])
    part("Door_Vision", "Glass_Daylight", lambda bm: [wbox(bm, "S", (c - 0.15, 1.25, 0.034), (c + 0.15, 1.62, 0.036)) for c in ((a + x) / 2, (x + b) / 2)])
    sy = DOOR_H + 0.42
    part("Exit_SignBox", "Paint_White", lambda bm: wbox(bm, "S", (x - 0.26, sy - 0.12, 0.0), (x + 0.26, sy + 0.12, 0.07)))
    panel("Exit_SignFace", "Exit_Sign_Emit", (x, sy, z - 0.071), (0, 0, -1), (0, 1, 0), 0.48, 0.20)
    part("decor_door_mat", "Rubber_Black", lambda bm: cube(bm, (a + 0.1, 0.0, z - 1.0), (b - 0.1, 0.012, z - 0.05)))


def build_shutter():
    z0, z1, h = SHUTTER["z0"], SHUTTER["z1"], SHUTTER["h"]
    w = z1 - z0
    panel("Shutter_Curtain", "Shutter_Steel", (-HX + 0.02, h / 2, (z0 + z1) / 2), (1, 0, 0), (0, 1, 0), w, h, uv=(0, 0, h / 1.12, w / 1.12), rot=True)
    part("Shutter_Guides", "Steel_Dark", lambda bm: [wbox(bm, "W", (s - 0.08, 0.0, 0.0), (s + 0.08, h + 0.1, 0.045)) for s in (z0 - 0.04, z1 + 0.04)])
    part("Shutter_Bottom", "Steel_Dark", lambda bm: wbox(bm, "W", (z0, 0.0, 0.0), (z1, 0.06, 0.04)))
    part("Shutter_Box", "Steel_Galv", lambda bm: wbox(bm, "W", (z0 - 0.15, h + 0.05, 0.0), (z1 + 0.15, h + 0.6, 0.48)))
    part("Shutter_Hazard", "Floor_Hazard", lambda bm: cube(bm, (-HX, 0.0, z0), (-HX + 0.45, 0.002, z1)), tile=0.4)
    part("Shutter_Hazard_Posts", "Floor_Hazard", lambda bm: [wbox(bm, "W", (s - 0.09, 0.0, 0.042), (s + 0.09, 1.2, 0.047)) for s in (z0 - 0.04, z1 + 0.04)], tile=0.4)


WIN_Y0, WIN_Y1 = 2.25, 4.0


def build_windows():
    """Steel-framed works windows high in the north wall, one in each bay between the columns, the frosted glass bright with the day."""
    cols = [-HX] + TRUSS_X + [HX]
    bays = [((a + b) / 2, min(2.6, b - a - 1.0)) for a, b in zip(cols[:-1], cols[1:])]

    def frames(bm, glass=False):
        for cx, w in bays:
            if glass:
                wbox(bm, "N", (cx - w / 2, WIN_Y0, 0.01), (cx + w / 2, WIN_Y1, 0.012))
                continue
            nx, ny = 5, 4
            for i in range(nx + 1):
                s = cx - w / 2 + w * i / nx
                wbox(bm, "N", (s - 0.025, WIN_Y0, 0.0), (s + 0.025, WIN_Y1, 0.05))
            for j in range(ny + 1):
                y = WIN_Y0 + (WIN_Y1 - WIN_Y0) * j / ny
                wbox(bm, "N", (cx - w / 2, y - 0.025, 0.0), (cx + w / 2, y + 0.025, 0.05))
    part("Window_Frames", "Steel_Dark", frames)
    part("Window_Glass", "Glass_Daylight", lambda bm: frames(bm, True))
    part("Window_Sills", "Panel_Grey", lambda bm: [wbox(bm, "N", (cx - w / 2 - 0.05, WIN_Y0 - 0.08, 0.0), (cx + w / 2 + 0.05, WIN_Y0 - 0.03, 0.16)) for cx, w in bays])
    return bays


def build_services():
    """Above head height: pipes on the south and east walls, a cable tray, unit heaters. On the east wall: the switchgear (flat on the wall)."""
    py = 3.4

    def pipes(bm):
        for wall, s0, s1 in (("S", -HX, HX), ("E", -HZ, HZ)):
            for off, r, yy in ((0.14, 0.06, py), (0.12, 0.04, py + 0.22)):
                a, b = wpt(wall, s0, yy, off), wpt(wall, s1, yy, off)
                cyl(bm, a, b, r, r, 14, False)
            for s in np.arange(s0 + 0.6, s1, 2.0):
                wbox(bm, wall, (s - 0.025, py - 0.09, 0.0), (s + 0.025, py + 0.28, 0.2))
    part("Services_Pipes", "Steel_Galv", pipes, smooth=True)
    part("Services_PipeBands", "Paint_Red", lambda bm: [cyl(bm, wpt("S", s, py, 0.14), wpt("S", s + 0.12, py, 0.14), 0.062, 0.062, 14) for s in (-7.6, -1.6, 4.4)], smooth=True)
    # the cable tray along the east wall, and conduits down to the switchgear
    ty = 4.0
    part("Services_Tray", "Steel_Galv", lambda bm: (wbox(bm, "E", (-HZ + 0.3, ty, 0.05), (HZ - 0.3, ty + 0.02, 0.40)), wbox(bm, "E", (-HZ + 0.3, ty, 0.38), (HZ - 0.3, ty + 0.1, 0.40))))
    sg0, sg1 = 0.6, 2.6
    part("Switchgear", "Panel_Grey", lambda bm: (wbox(bm, "E", (sg0, 0.15, 0.0), (sg1, 2.1, 0.045)), wbox(bm, "E", (sg0 - 0.02, 0.0, 0.0), (sg1 + 0.02, 0.15, 0.045))))
    part("Switchgear_Lines", "Steel_Dark", lambda bm: [wbox(bm, "E", (s - 0.004, 0.2, 0.045), (s + 0.004, 2.05, 0.048)) for s in np.linspace(sg0, sg1, 4)[1:-1]] +
         [wbox(bm, "E", (s - 0.02, 1.0, 0.045), (s + 0.02, 1.2, 0.048)) for s in np.linspace(sg0, sg1, 4)[:-1] + 0.55])
    panel("Switchgear_Sign", "Decal_Print", wpt("E", (sg0 + sg1) / 2, 1.75, 0.047), WALL_N["E"], (0, 1, 0), 0.24, 0.24, uv=ATLAS["shock"])
    part("Services_Conduits", "Steel_Galv", lambda bm: [cyl(bm, wpt("E", s, 2.1, 0.03), wpt("E", s, ty, 0.03), 0.016, 0.016, 8, False) for s in np.linspace(sg0 + 0.2, sg1 - 0.2, 4)])
    # unit heaters high on the end walls, angled down
    def heater(bm, wall, s):
        wbox(bm, wall, (s - 0.35, 3.0, 0.15), (s + 0.35, 3.6, 0.6))
        wbox(bm, wall, (s - 0.05, 3.3, 0.0), (s + 0.05, 3.4, 0.15))
    spots = [("E", -4.6), ("E", 4.2), ("W", -4.6), ("W", 5.4)]
    part("Heaters", "Panel_Grey", lambda bm: [heater(bm, w, s) for w, s in spots])
    part("Heaters_Louvres", "Steel_Dark", lambda bm: [wbox(bm, w, (s - 0.32, 3.04 + i * 0.075, 0.601), (s + 0.32, 3.07 + i * 0.075, 0.61)) for w, s in spots for i in range(7)])


def build_floor_marks():
    """Painted lines (2 mm, flat): the safety line round the belt, a box round each bin, the walkway from the door; hazard bands; oil stains."""
    y, lw = 0.002, 0.1
    bx0, bx1 = BELT["x0"] - 0.7, min(BELT["x1"] + 1.45, HX - 0.15)
    bz0, bz1 = BELT["z0"] - 0.7, BELT["z1"] + 0.6

    def lines(bm):
        cube(bm, (bx0, 0, bz0), (bx1, y, bz0 + lw))
        cube(bm, (bx0, 0, bz1 - lw), (bx1, y, bz1))
        cube(bm, (bx0, 0, bz0 + lw), (bx0 + lw, y, bz1 - lw))
        cube(bm, (bx1 - lw, 0, bz0 + lw), (bx1, y, bz1 - lw))
        for bn in K["bins"]:
            c = COLLIDERS["Bin_" + bn["kind"]]
            m = 0.3
            x0, z0, x1, z1 = c["min"][0] - m, c["min"][2] - m, c["max"][0] + m, c["max"][2] + m
            cube(bm, (x0, 0, z0), (x1, y, z0 + lw))
            cube(bm, (x0, 0, z1 - lw), (x1, y, z1))
            cube(bm, (x0, 0, z0 + lw), (x0 + lw, y, z1 - lw))
            cube(bm, (x1 - lw, 0, z0 + lw), (x1, y, z1 - lw))
        dx = K["door"]["at"][0]
        top = max(COLLIDERS["Bin_" + b["kind"]]["max"][2] for b in K["bins"]) + 0.8
        for sx in (-1.6, 1.6):
            cube(bm, (dx + sx - lw / 2, 0, top), (dx + sx + lw / 2, y, HZ - 0.05))
    part("Floor_Lines", "Floor_Paint", lines)
    part("Floor_HazardBands", "Floor_Hazard", lambda bm: (cube(bm, (BELT["x0"] - 0.6, 0, BELT["z0"] - 0.55), (BELT["x0"] - 0.1, y, BELT["z1"] + 0.45)),), tile=0.4)
    e = 0.003
    for i, (x, z, s) in enumerate(((BELT["x1"] - 1.0, BELT["z1"] + 0.3, 1.6), (-3.8, BELT["z1"] + 0.25, 1.1), (BELT["x0"] + 0.5, BELT["z0"] - 0.35, 1.3), (-8.4, 1.6, 1.8), (6.6, 5.1, 1.2), (-2.6, -5.6, 1.4))):
        panel(f"Decal_Oil_{i}", "Decal_Grime", (x, e + i * 0.0002, z), (0, 1, 0), (math.cos(i), 0, math.sin(i)), s, s * 0.8)
    # wall grime: soot over the heaters and damp at the foot of the walls
    for i, (wall, s, yy, w, h) in enumerate((("E", -4.6, 4.4, 1.6, 1.6), ("W", -4.6, 4.4, 1.6, 1.6), ("N", -6.5, 0.6, 2.4, 1.2), ("S", 7.0, 0.7, 2.6, 1.4), ("W", 5.4, 4.4, 1.6, 1.5))):
        panel(f"Decal_Wall_{i}", "Decal_Grime", wpt(wall, s, yy, 0.006), WALL_N[wall], (0, 1, 0), w, h)


def build_pallet(name, x, z, ang=0.0):
    def pal(bm):
        n0 = len(bm.verts)
        for i in range(5):                                       # the top deck: five boards across 0.8 m
            zz = -0.4 + 0.0725 + i * 0.16375
            cube(bm, (-0.6, 0.122, zz - 0.0725), (0.6, 0.144, zz + 0.0725 - 0.03))
        for xx in (-0.6, -0.05, 0.5):
            for zz in (-0.4, -0.05, 0.3):
                cube(bm, (xx, 0.022, zz), (xx + 0.1, 0.10, zz + 0.1))
            cube(bm, (xx, 0.10, -0.4), (xx + 0.1, 0.122, 0.4))
            cube(bm, (xx, 0.0, -0.4), (xx + 0.1, 0.022, 0.4))
        bm.verts.ensure_lookup_table()
        vs = [bm.verts[i] for i in range(n0, len(bm.verts))]
        bmesh.ops.rotate(bm, cent=Vector((0, 0, 0)), matrix=Matrix.Rotation(ang, 3, "Z"), verts=vs)
        bmesh.ops.translate(bm, vec=B((x, 0, z)), verts=vs)
    part(name, "Wood_Pallet", pal)


def build_dressing():
    # a clock and a notice board by the way out, a fire point
    dx = K["door"]["at"][0]
    cx, cy = dx - DOOR_W / 2 - 1.7, 3.3
    part("Clock_Rim", "Paint_White", lambda bm: cyl(bm, (cx, cy, HZ), (cx, cy, HZ - 0.06), 0.24, 0.24, 32), smooth=True)
    disc("Clock_Face", "Decal_Print", (cx, cy, HZ - 0.061), (0, 0, -1), (0, 1, 0), 0.21, ATLAS["clock"])
    nx0, nx1, ny0, ny1 = cx - 0.85, cx + 0.85, 1.15, 1.95
    part("Notice_Frame", "Steel_Galv", lambda bm: wbox(bm, "S", (nx0, ny0, 0.0), (nx1, ny1, 0.02)))
    panel("Notice_Board", "Decal_Print", ((nx0 + nx1) / 2, (ny0 + ny1) / 2, HZ - 0.021), (0, 0, -1), (0, 1, 0), nx1 - nx0 - 0.04, ny1 - ny0 - 0.04, uv=ATLAS["notice"])
    fx = dx + DOOR_W / 2 + 0.8
    part("decor_extinguisher", "Paint_Red", lambda bm: cyl(bm, (fx, 0.10, HZ - 0.12), (fx, 0.66, HZ - 0.12), 0.08, 0.08, 20), smooth=True)
    part("decor_extinguisher_head", "Steel_Dark", lambda bm: (cyl(bm, (fx, 0.66, HZ - 0.12), (fx, 0.76, HZ - 0.12), 0.022, 0.022, 10), cube(bm, (fx - 0.01, 0.40, HZ - 0.02), (fx + 0.01, 0.72, HZ))))
    panel("Sign_FirePoint", "Decal_Print", (fx, 1.05, HZ - 0.004), (0, 0, -1), (0, 1, 0), 0.24, 0.24, uv=ATLAS["fire"])
    panel("Sign_Ears", "Decal_Print", (dx - DOOR_W / 2 - 0.45, 1.6, HZ - 0.004), (0, 0, -1), (0, 1, 0), 0.30, 0.30, uv=ATLAS["ears"])
    panel("Sign_Crane", "Decal_Print", wpt("N", TRUSS_X[0] + 0.5, 1.7, 0.004), WALL_N["N"], (0, 1, 0), 0.34, 0.34, uv=ATLAS["warn"])
    panel("Sign_Forklift", "Decal_Print", wpt("W", SHUTTER["z1"] + 0.6, 1.6, 0.004), WALL_N["W"], (0, 1, 0), 0.34, 0.34, uv=ATLAS["warn"])
    # empty pallets on the floor (14 cm: low enough to step over, no collider needed)
    build_pallet("Pallet_0", -HX + 1.2, SHUTTER["z1"] + 1.3, 0.1)
    build_pallet("Pallet_1", HX - 1.0, HZ - 1.6, math.pi / 2 - 0.06)


# ---------------------------------------------------------------- generated images (own work, numpy, fixed seeds)
def rs(a, h, w):
    ys, xs = np.linspace(0, a.shape[0] - 1, h), np.linspace(0, a.shape[1] - 1, w)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, a.shape[0] - 1), np.minimum(x0 + 1, a.shape[1] - 1)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    if a.ndim == 3:
        fy, fx = fy[..., None], fx[..., None]
    return (a[y0][:, x0] * (1 - fy) * (1 - fx) + a[y0][:, x1] * (1 - fy) * fx + a[y1][:, x0] * fy * (1 - fx) + a[y1][:, x1] * fy * fx)


def vnoise(h, w, rng, octaves=5, base=4):
    out, amp, tot = np.zeros((h, w)), 1.0, 0.0
    for k in range(octaves):
        n = base * 2 ** k + 1
        out += amp * rs(rng.random((n, n)), h, w)
        tot += amp
        amp *= 0.5
    return out / tot


def blur(a, r, passes=3, axes=(0, 1)):
    n = 2 * r + 1
    for ax in axes:
        for _ in range(passes):
            pad = [(0, 0)] * a.ndim
            pad[ax] = (r + 1, r)
            c = np.cumsum(np.pad(a, pad, mode="wrap"), axis=ax)
            Ln = c.shape[ax]
            a = (np.take(c, range(n, Ln), axis=ax) - np.take(c, range(0, Ln - n), axis=ax)) / n
    return a


def hazard_pixels():
    S = 256
    yy, xx = np.mgrid[0:S, 0:S]
    band = ((xx + yy) // (S // 4)) % 2 == 0
    img = np.zeros((S, S, 3), np.float32)
    img[band] = (0.85, 0.58, 0.03)
    img[~band] = (0.04, 0.04, 0.04)
    rng = np.random.default_rng(4)
    wear = vnoise(S, S, rng, 5, 4)
    img = img * (0.85 + 0.2 * wear)[..., None]
    scuff = (vnoise(S, S, rng, 5, 8) > 0.68)[..., None]
    return np.clip(np.where(scuff, img * 0.55 + 0.12, img), 0, 1).astype(np.float32)


def stain_pixels():
    S = 512
    rng = np.random.default_rng(3)
    yy, xx = (np.mgrid[0:S, 0:S] - S / 2) / (S / 2)
    r = np.sqrt(xx ** 2 + (yy * 1.2) ** 2) + (vnoise(S, S, rng, 5, 4) - 0.5) * 0.9
    a = np.clip(1.0 - r, 0, 1) ** 0.7
    alpha = np.clip(a * 0.55, 0, 0.5)
    rgba = np.zeros((S, S, 4), np.float32)
    rgba[..., :3] = np.array([0.05, 0.045, 0.035])
    rgba[..., 3] = alpha
    return rgba


def _poly(img, pts, col, x0, y0):
    """fill a convex polygon (pixel coordinates inside a cell at x0, y0)"""
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    inside = np.ones((h, w), bool)
    n = len(pts)
    for i in range(n):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
        ax, ay, bx, by = ax + x0, ay + y0, bx + x0, by + y0
        inside &= (bx - ax) * (yy - ay) - (by - ay) * (xx - ax) >= 0
    img[inside] = col


def _circle(img, cx, cy, r, col, ring=None):
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot(xx - cx, yy - cy)
    m = d <= r if ring is None else (d <= r) & (d >= r - ring)
    img[m] = col


def _rect(img, x0, y0, x1, y1, col):
    img[int(y0):int(y1), int(x0):int(x1)] = col


ATLAS_PX = 1024
ATLAS_CELLS = {             # name: (column px, row px, width px, height px) in the atlas image, rows from the top
    "warn": (0, 0, 256, 256), "shock": (256, 0, 256, 256), "ears": (512, 0, 256, 256), "fire": (768, 0, 256, 256),
    "gears": (0, 256, 256, 256), "bolts": (256, 256, 256, 256), "springs": (512, 256, 256, 256), "clock": (768, 256, 256, 256),
    "notice": (0, 512, 1024, 500),                                          # the notice board, 1.66 x 0.76 m
}
ATLAS = {}


def _uv(cell, inset=4):
    c, r, w, h = cell
    return ((c + inset) / ATLAS_PX, 1 - (r + h - inset) / ATLAS_PX, (c + w - inset) / ATLAS_PX, 1 - (r + inset) / ATLAS_PX)


def atlas_pixels():
    """One image for every printed thing: safety signs and the bins' plates as pictograms (no words: the page draws the bins' signs), a clock
    face, a cork notice board with papers. Drawn here from simple shapes."""
    S = ATLAS_PX
    rng = np.random.default_rng(9)
    img = np.ones((S, S, 3), np.float32) * 0.9
    white, black, yellow, blue, red = (0.93, 0.93, 0.91), (0.04, 0.04, 0.04), (0.95, 0.72, 0.05), (0.05, 0.25, 0.60), (0.72, 0.05, 0.05)
    # warning triangles: "!" and an electric bolt
    for name in ("warn", "shock"):
        c, r, w, h = ATLAS_CELLS[name]
        _rect(img, c, r, c + w, r + h, white)
        _poly(img, [(128, 22), (238, 222), (18, 222)], black, c, r)
        _poly(img, [(128, 52), (210, 206), (46, 206)], yellow, c, r)
        if name == "warn":
            _poly(img, [(120, 95), (136, 95), (132, 165), (124, 165)], black, c, r)
            _circle(img, c + 128, r + 184, 9, black)
        else:
            _poly(img, [(140, 88), (112, 150), (130, 150)], black, c, r)
            _poly(img, [(126, 140), (146, 140), (116, 196)], black, c, r)
    # mandatory: ear protection (a blue disc, a white headband and two cups)
    c, r, w, h = ATLAS_CELLS["ears"]
    _rect(img, c, r, c + w, r + h, white)
    _circle(img, c + 128, r + 128, 112, blue)
    _circle(img, c + 128, r + 120, 62, white, ring=14)
    _rect(img, c + 58, r + 120, c + 198, r + 190, blue)
    _rect(img, c + 58, r + 118, c + 90, r + 182, white)
    _rect(img, c + 166, r + 118, c + 198, r + 182, white)
    # fire point
    c, r, w, h = ATLAS_CELLS["fire"]
    _rect(img, c, r, c + w, r + h, red)
    _rect(img, c + 98, r + 70, c + 158, r + 226, white)
    _circle(img, c + 128, r + 72, 30, white)
    _rect(img, c + 112, r + 30, c + 144, r + 50, white)
    _rect(img, c + 144, r + 34, c + 196, r + 44, white)
    # the bins' plates: a black pictogram on white with a border in the kind's colour
    for kind in ("gears", "bolts", "springs"):
        c, r, w, h = ATLAS_CELLS[kind]
        col = tuple(((KIND_HEX[kind] >> s) & 255) / 255 for s in (16, 8, 0))
        _rect(img, c, r, c + w, r + h, col)
        _rect(img, c + 16, r + 16, c + w - 16, r + h - 16, white)
        cx, cy = c + 128, r + 128
        if kind == "gears":
            for i in range(10):
                t = 2 * math.pi * i / 10
                dx, dy = math.cos(t), math.sin(t)
                pts = [(128 + dx * 60 - dy * 14, 128 + dy * 60 + dx * 14), (128 + dx * 92 - dy * 11, 128 + dy * 92 + dx * 11),
                       (128 + dx * 92 + dy * 11, 128 + dy * 92 - dx * 11), (128 + dx * 60 + dy * 14, 128 + dy * 60 - dx * 14)]
                _poly(img, pts[::-1], black, c, r)
            _circle(img, cx, cy, 72, black)
            _circle(img, cx, cy, 26, white)
        elif kind == "bolts":
            hexa = [(128 + 52 * math.cos(math.pi / 3 * i + math.pi / 6), 70 + 32 * math.sin(math.pi / 3 * i + math.pi / 6)) for i in range(6)]
            _poly(img, hexa[::-1], black, c, r)
            _rect(img, cx - 22, r + 96, cx + 22, r + 222, black)
            for y in range(r + 110, r + 222, 16):
                _rect(img, cx - 28, y, cx + 28, y + 5, black)
        else:
            for k in range(7):
                y = r + 50 + k * 22
                _poly(img, [(70, y - r), (186, y - r + 14), (186, y - r + 26), (70, y - r + 12)][::-1], black, c, 0)
            _rect(img, cx - 60, r + 40, cx + 60, r + 50, black)
            _rect(img, cx - 60, r + 210, cx + 60, r + 220, black)
    # the clock: a white dial, ticks, two hands
    c, r, w, h = ATLAS_CELLS["clock"]
    _rect(img, c, r, c + w, r + h, white)
    _circle(img, c + 128, r + 128, 126, (0.97, 0.97, 0.96))
    for i in range(60):
        t = 2 * math.pi * i / 60
        r0, r1, hw = (100, 122, 3.5) if i % 5 == 0 else (114, 122, 1.2)
        dx, dy = math.sin(t), -math.cos(t)
        pts = [(128 + dx * r0 - dy * hw, 128 + dy * r0 + dx * hw), (128 + dx * r1 - dy * hw, 128 + dy * r1 + dx * hw),
               (128 + dx * r1 + dy * hw, 128 + dy * r1 - dx * hw), (128 + dx * r0 + dy * hw, 128 + dy * r0 - dx * hw)]
        _poly(img, pts[::-1], black, c, r)
    for ang, ln, hw in ((math.radians(75), 62, 5), (math.radians(200), 92, 3.5)):
        dx, dy = math.sin(ang), -math.cos(ang)
        pts = [(128 - dy * hw, 128 + dx * hw), (128 + dx * ln - dy * hw, 128 + dy * ln + dx * hw), (128 + dx * ln + dy * hw, 128 + dy * ln - dx * hw), (128 + dy * hw, 128 - dx * hw)]
        _poly(img, pts[::-1], black, c, r)
    _circle(img, c + 128, r + 128, 7, red)
    # the notice board: cork, papers, a rota and a shift chart
    c, r, w, h = ATLAS_CELLS["notice"]
    cork = vnoise(h, w, rng, 6, 16)
    speck = (rng.random((h, w)) < 0.08) * 0.12
    img[r:r + h, c:c + w] = np.stack([0.52 + 0.18 * cork - speck, 0.36 + 0.13 * cork - speck, 0.20 + 0.08 * cork - speck], -1)
    _rect(img, c, r, c + w, r + 10, (0.55, 0.56, 0.57))
    _rect(img, c, r + h - 10, c + w, r + h, (0.55, 0.56, 0.57))
    papers = [(40, 40, 230, 330), (300, 60, 520, 360), (580, 30, 800, 300), (850, 70, 990, 260), (600, 330, 980, 480), (60, 370, 330, 480)]
    for i, (x0, y0, x1, y1) in enumerate(papers):
        tint = (0.93, 0.93, 0.90) if i not in (3, 5) else ((0.95, 0.88, 0.45) if i == 3 else (0.75, 0.85, 0.95))
        _rect(img, c + x0 + 4, r + y0 + 5, c + x1 + 4, r + y1 + 5, (0.25, 0.18, 0.10))
        _rect(img, c + x0, r + y0, c + x1, r + y1, tint)
        _rect(img, c + x0 + 14, r + y0 + 14, c + x0 + (x1 - x0) * 0.7, r + y0 + 26, (0.15, 0.15, 0.18))
        if i == 1:
            for gx in range(x0 + 14, x1 - 10, 34):
                _rect(img, c + gx, r + y0 + 40, c + gx + 1, r + y1 - 14, (0.3, 0.3, 0.35))
            for gy in range(y0 + 40, y1 - 10, 22):
                _rect(img, c + x0 + 14, r + gy, c + x1 - 14, r + gy + 1, (0.3, 0.3, 0.35))
        elif i == 4:                                            # a chart of the line's output: bars
            for k, gx in enumerate(range(x0 + 20, x1 - 20, 30)):
                hgt = int(30 + 90 * abs(math.sin(k * 1.7)))
                _rect(img, c + gx, r + y1 - 14 - hgt, c + gx + 18, r + y1 - 14, (0.25, 0.4, 0.6))
        else:
            for y in range(y0 + 40, y1 - 14, 13):
                ln = int((x1 - x0 - 28) * rng.uniform(0.5, 1.0))
                _rect(img, c + x0 + 14, r + y, c + x0 + 14 + ln, r + y + 4, (0.35, 0.35, 0.38))
        _circle(img, c + (x0 + x1) // 2, r + y0 + 8, 7, (0.80, 0.10, 0.10))
    return np.clip(img, 0, 1).astype(np.float32)


def exit_pixels():
    """The exit sign: a green panel with a white door and an arrow (a pictogram, no words)."""
    Wd, Hd = 256, 104
    img = np.zeros((Hd, Wd, 3), np.float32)
    img[:] = (0.02, 0.55, 0.20)
    _rect(img, 6, 6, Wd - 6, Hd - 6, (0.04, 0.62, 0.25))
    _rect(img, 150, 18, 212, 88, (0.95, 0.97, 0.95))
    _rect(img, 158, 26, 204, 88, (0.02, 0.55, 0.20))
    _rect(img, 60, 46, 130, 58, (0.95, 0.97, 0.95))
    _poly(img, [(130, 30), (150, 52), (130, 74)], (0.95, 0.97, 0.95), 0, 0)
    return img


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
    return packed_image(name, path.read_bytes(), "sRGB" if srgb else "Non-Color", alpha=has_a)


def packed_image(name, data, colorspace, fname=None, alpha=False):
    """A new image packed from PNG bytes under a neutral relative name. Built fresh, so neither the image's path nor its packed
    file's path ever holds the work folder (a renamed path would leave the old one in the bytes after the new one's end)."""
    out = bpy.data.images.new(name, 1, 1, alpha=alpha)
    out.filepath_raw = f"//gen/{bpy.path.clean_name(fname or name)}.png"
    out.source = "FILE"
    out.pack(data=data, data_len=len(data))
    out.colorspace_settings.name = colorspace
    if alpha:
        out.alpha_mode = "STRAIGHT"
    return out


def make_generated():
    for k, cellv in ATLAS_CELLS.items():
        ATLAS[k] = _uv(cellv)
    gen = {"atlas": mk_image("Print_Atlas", atlas_pixels()), "hazard": mk_image("Hazard_Img", hazard_pixels()), "stain": mk_image("Stain_Img", stain_pixels())}
    ex = mk_image("Exit_Sign_Img", exit_pixels())
    ex["strength"] = 3.0
    gen["exit"] = ex
    return gen


# ---------------------------------------------------------------- the textures derived from the Poly Haven downloads (stage "textures")
def load_px(path):
    im = bpy.data.images.load(str(path))
    w, h = im.size
    a = np.empty(w * h * im.channels, np.float32)
    im.pixels.foreach_get(a)
    a = np.flipud(a.reshape(h, w, im.channels))[..., :3]
    bpy.data.images.remove(im)
    return a


def save_jpg(arr, path, q=88):
    h, w = arr.shape[:2]
    im = bpy.data.images.new(path.stem, w, h, alpha=False)
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :3] = np.clip(arr, 0, 1)
    im.pixels.foreach_set(np.flipud(rgba).ravel())
    im.filepath_raw = str(path)
    im.file_format = "JPEG"
    im.save(filepath=str(path), quality=q)
    bpy.data.images.remove(im)
    print("TEXTURE", path.relative_to(ROOT), path.stat().st_size)


def stage_textures():
    """brick_diff: factory_brick as it is; concrete_floor_diff: hangar_concrete_floor lifted from near-black to a worn mid grey (its marks kept);
    roof_sheet_diff: corrugated_iron as it is; paint_green_diff: green_metal_rust as it is; paint_grime_diff: green_metal_rust's light and dark
    marks on a neutral light grey, to be tinted by a colour factor (the bins, the crane, the motor). All Poly Haven, CC0. wood_diff: the repo's
    own blender/textures/apartment/dark_wood_diff_1k.jpg (Poly Haven dark_wood, CC0), for the pallets."""
    src = Path(arg("--src"))
    TEX.mkdir(parents=True, exist_ok=True)
    lum = lambda a: a @ np.array([0.299, 0.587, 0.114], np.float32)
    save_jpg(load_px(src / "factory_brick_diff_1k.jpg"), TEX / "brick_diff.jpg")
    c = load_px(src / "hangar_concrete_floor_diff_1k.jpg")
    cl = lum(c)
    n = (cl - cl.mean()) / (cl.std() + 1e-6)
    tint = np.array([0.40, 0.385, 0.36], np.float32)
    save_jpg(tint[None, None, :] * (1 + 0.16 * np.clip(n, -3, 3))[..., None] + 0.25 * (c - c.mean(axis=(0, 1))), TEX / "concrete_floor_diff.jpg")
    save_jpg(load_px(src / "corrugated_iron_diff_1k.jpg"), TEX / "roof_sheet_diff.jpg")
    g = load_px(src / "green_metal_rust_diff_1k.jpg")
    save_jpg(g, TEX / "paint_green_diff.jpg")
    gl = lum(g)
    d = (gl - np.median(gl)) / (gl.std() + 1e-6)
    rust = np.clip((g[..., 0] - g[..., 1]) * 4.0, 0, 1)                    # the rust runs (red over green), kept as warm stains
    base = np.clip(0.86 + 0.06 * d, 0, 1)[..., None] * np.ones(3, np.float32)
    base = base * (1 - 0.6 * rust[..., None]) + rust[..., None] * np.array([0.45, 0.25, 0.10]) * 0.6
    save_jpg(base, TEX / "paint_grime_diff.jpg")
    save_jpg(load_px(ROOT / "blender/textures/apartment/dark_wood_diff_1k.jpg"), TEX / "wood_diff.jpg")


# ---------------------------------------------------------------- lights, world, marker
LAMP_W = arg("--lamp", 1800.0, float)       # watts per high-bay (a spot pointing down)


def add_lights():
    lights = bpy.data.collections.new("Lights")
    bpy.context.scene.collection.children.link(lights)
    for i, (x, z) in enumerate(lamp_spots()):
        d = bpy.data.lights.new(f"HighBay_{i}", "SPOT")
        d.energy, d.color = LAMP_W, SODIUM
        d.shadow_soft_size = 0.2
        d.spot_size, d.spot_blend = math.radians(150), 0.35
        ob = bpy.data.objects.new(f"HighBay_{i}", d)
        ob.location = B((x, LAMP_Y - 0.01, z))
        ob.rotation_euler = (0, 0, 0)                     # a spot looks down Blender -Z: down
        lights.objects.link(ob)


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("Dark")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
    bg.inputs["Strength"].default_value = 0.0


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


def standins():
    """Hidden stand-ins where the page draws (never exported, never rendered), so the .blend shows the spots: the belt's surface, a few parts
    on it, each bin's sign."""
    b, c = K["belt"], COLLIDERS["Belt"]
    for name, mn, mx in [("standin_belt_surface", (c["min"][0], b["top"] - BELT_SKIN, b["z"] - b["w"] / 2 + 0.05), (c["max"][0], b["top"], b["z"] + b["w"] / 2 - 0.05))] + \
            [(f"standin_part_{i}", (x - 0.2, b["top"], b["z"] - 0.2), (x + 0.2, b["top"] + 0.3, b["z"] + 0.2)) for i, x in enumerate((b["x0"], -3.2, 1.6, 6.0))]:
        ob = part(name, "Rubber_Black" if "surface" in name else "Paint_White", lambda bm, mn=mn, mx=mx: cube(bm, mn, mx), coll=STANDIN)
        ob.hide_render = True
    for bn in K["bins"]:
        ob = panel(f"standin_sign_{bn['kind']}", "Paint_White", (bn["x"], SIGN_Y, bn["z"]), (0, 0, 1), (0, 1, 0), SIGN_W, SIGN_H, coll=STANDIN)
        ob.hide_render = True


def check_keepout():
    """Every Art object's box against the page's boxes: none may reach into one."""
    bad = 0
    parts = []
    for ob in bpy.data.collections["Art"].all_objects:
        if ob.name.startswith("Belt_Guards"):
            continue                                       # checked below by its pieces: the guards run either side of the surface, outside it
        pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        g = [(p.x, p.z, -p.y) for p in pts]
        parts.append((ob.name, [min(q[i] for q in g) for i in range(3)], [max(q[i] for q in g) for i in range(3)]))
    gd = bpy.data.objects["Belt_Guards"]
    for side in (0, 1):                                    # the two guards are separate shells in one mesh: test each by its own vertices
        zs = [-(gd.matrix_world @ v.co).y for v in gd.data.vertices]
        mid = (min(zs) + max(zs)) / 2
        vs = [gd.matrix_world @ v.co for v in gd.data.vertices if ((-(gd.matrix_world @ v.co).y) < mid) == (side == 0)]
        g = [(p.x, p.z, -p.y) for p in vs]
        parts.append((f"Belt_Guards[{side}]", [min(q[i] for q in g) for i in range(3)], [max(q[i] for q in g) for i in range(3)]))
    for label, mn, mx in keepout_boxes():
        hit = [n for n, a, b in parts if all(a[i] < mx[i] - 1e-4 and b[i] > mn[i] + 1e-4 for i in range(3)) and n not in COLLIDERS and not n.startswith("Belt_FeedHood")
               and not n.startswith(("Belt_FeedCurtain", "Belt_FeedDuct", "Belt_Control", "Belt_Stop", "Belt_Run", "Belt_Cord"))]
        print(f"KEEPOUT {'PASS' if not hit else 'FAIL'} {label}: x {mn[0]:.2f}..{mx[0]:.2f}, y {mn[1]:.2f}..{mx[1]:.2f}, z {mn[2]:.2f}..{mx[2]:.2f} " + ("clear" if not hit else "reached by " + ", ".join(hit)))
        bad += bool(hit)
    # the feed hood stands over the belt's west end on purpose (the parts come out of it): it must stay west of where a new part appears
    hood = next(p for p in parts if p[0] == "Belt_FeedHood")
    ok = hood[2][0] <= K["belt"]["x0"] - 0.1
    print(f"KEEPOUT {'PASS' if ok else 'FAIL'} feed hood ends at x {hood[2][0]:.2f}, a new part appears centred on x {K['belt']['x0']} (0.4 m long): it comes out of the hood's mouth")
    bad += not ok
    # the pull cord, its posts and the control box stand on the aisle-side guard, outside the surface's z span
    for n, a, b in parts:
        if n.startswith(("Belt_Cord", "Belt_Control", "Belt_Stop", "Belt_Run")):
            ok = a[2] >= K["belt"]["z"] + K["belt"]["w"] / 2 - 0.05 - 1e-4
            if not ok:
                print(f"KEEPOUT FAIL {n} reaches over the belt's surface (z {a[2]:.3f})")
                bad += 1
    return bad


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
    gen = make_generated()
    make_materials(gen)
    build_shell()
    build_walls()
    build_roof()
    build_lamps()
    build_belt()
    build_bins()
    build_door()
    build_shutter()
    build_windows()
    build_services()
    build_floor_marks()
    build_dressing()
    add_lights()
    setup_world()
    ensure_marker()
    standins()
    bpy.context.view_layer.update()
    bad = check_keepout()
    assert not bad, "art reaches into a spot the page draws"


# ---------------------------------------------------------------- bake
SHELL_MATS = ["Floor_Concrete", "Wall_Brick", "Wall_Dado", "Roof_Sheet", "Floor_Paint", "Floor_Hazard", "Decal_Grime", "Decal_Print", "Shutter_Steel"]
NO_BAKE = ["Lamp_Emit", "Glass_Daylight", "Exit_Sign_Emit", "Indicator_Green"]
STRUCT_MATS = ["Steel_Green"]     # the trusses, purlins, columns, crane runway and the belt's frame: thousands of small islands, a page of their own
SHELL_PREFIX = ("Wall_N", "Wall_S", "Wall_W", "Wall_E", "Floor_Factory", "Ceiling_Factory")


def content_mats():
    return [m for m in MATS_ORDER() if m not in SHELL_MATS and m not in NO_BAKE and m not in STRUCT_MATS]


def MATS_ORDER():
    return sorted({ob.data.materials[0].name for ob in bpy.data.collections["Art"].objects})


def trim_outside(bm):
    """Drop the faces of a shell slab that look away from the hall: never seen, and they would cost lightmap texels."""
    centre = Vector((0, 0, H / 2))
    bad = [f for f in bm.faces if f.normal.dot(f.calc_center_median() - centre) > 1e-4]
    bmesh.ops.delete(bm, geom=bad, context="FACES")


def stage_work():
    d = Path(arg("--work", str(Path(os.environ.get("TEMP", "/tmp")) / f"farway_{SCENE}")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def no_stamps(sc):
    """Turn off every metadata stamp, so no rendered file carries the .blend's absolute path (public repo)."""
    for p in sc.render.bl_rna.properties:
        if p.identifier.startswith("use_stamp") and not p.is_readonly:
            setattr(sc.render, p.identifier, False)
    sc.render.stamp_note_text = ""


def strip_jpeg_meta(path):
    """Drop every COM and APP1..APP15 segment from a JPEG (Blender writes its render stats there), keeping the pixels byte for byte."""
    b = Path(path).read_bytes()
    assert b[:2] == b"\xff\xd8", path
    out, i = bytearray(b[:2]), 2
    while i < len(b):
        assert b[i] == 0xFF, (path, i)
        m = b[i + 1]
        if m == 0xDA:
            out += b[i:]
            break
        n = int.from_bytes(b[i + 2:i + 4], "big")
        if not (m == 0xFE or 0xE1 <= m <= 0xEF):
            out += b[i:i + 2 + n]
        i += 2 + n
    Path(path).write_bytes(bytes(out))


def setup_cycles(samples, bake=False):
    sc = bpy.context.scene
    no_stamps(sc)
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = samples
    cy.use_adaptive_sampling = not bake
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces, cy.transmission_bounces, cy.transparent_max_bounces = 8, 6, 3, 6, 8
    cy.use_denoising = not bake
    prefs = bpy.context.preferences.addons["cycles"].preferences
    gpu = False
    if DEVICE != "cpu":
        for t in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
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
        if ob.name in COLLIDERS and ob.name.startswith(SHELL_PREFIX):
            trim_outside(tmp)
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


TARGET = 30.0          # px/m: the smallest page that reaches it is used (docs/BLENDER.md R1: about 32 indoors)


def lightmap_uv(objs):
    """One shared atlas for `objs`: smart-project islands, equal texel density, packed with MARGIN_PX; the smallest square page that gives >= TARGET px/m."""
    for o in objs:
        uvs = o.data.uv_layers
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.new(name="lightmap")
        uvs.active = uvs["lightmap"]
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    print(f"  unwrapping {len(bpy.context.objects_in_mode)} objects")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    a3 = sum(area3d(o) for o in objs)
    sizes = (512, 640, 768, 896, 1024, 1280, 1536, 1792, 2048)

    def pack(S):
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / S, shape_method="CONCAVE")
        bpy.ops.object.mode_set(mode="OBJECT")
        dens = S * math.sqrt(sum(uv_area(o, "lightmap") for o in objs) / a3)
        print(f"  page {S}: {a3:.1f} m2, {dens:.1f} px/m")
        return dens
    d1024 = pack(1024)
    i = next((k for k, S in enumerate(sizes) if d1024 * S / 1024 >= TARGET), len(sizes) - 1)
    tried = {1024: d1024}
    while sizes[i] not in tried:
        tried[sizes[i]] = pack(sizes[i])
        if tried[sizes[i]] >= TARGET or i == len(sizes) - 1:
            break
        i += 1
    while i > 0 and tried.get(sizes[i], 0) >= TARGET and sizes[i - 1] not in tried:
        tried[sizes[i - 1]] = pack(sizes[i - 1])
        if tried[sizes[i - 1]] < TARGET:
            break
        i -= 1
    ok = [S for S in sizes if tried.get(S, 0) >= TARGET]
    S = ok[0] if ok else sizes[-1]
    dens = pack(S) if S != list(tried)[-1] else tried[S]
    if dens < 1e-6:
        raise RuntimeError("the lightmap pack came out empty")
    for o in objs:                                   # UV0 stays the render UV: the lightmap is the second set (TEXCOORD_1)
        o.data.uv_layers["UVMap"].active_render = True
    return S, dens


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
    no_stamps(sc)
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
    t0 = time.time()
    stage_work()
    exp = make_export_objects()
    bpy.data.collections["Art"].hide_render = True
    bpy.data.collections["Art"].hide_viewport = True
    setup_cycles(SAMPLES, bake=True)
    report = {}
    groups = [SHELL_MATS, content_mats(), STRUCT_MATS]
    hidden = [exp[m] for m in ("Lamp_Emit",) if m in exp]
    for o in hidden:
        o.hide_render = True                         # the high-bays' lenses (the spot lights stand for their light); the daylit glass stays and lights the bake
    pages = []
    for n, mats in enumerate(groups):
        objs = [exp[m] for m in mats if m in exp]
        print(f"lightmap {n}: {[o.name for o in objs]}")
        pages.append(lightmap_uv(objs))
    for n, mats in enumerate(groups):
        objs = [exp[m] for m in mats if m in exp]
        S, dens = pages[n]
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
        tb = time.time()
        bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
        print(f"  bake {n}: {S}x{S} at {SAMPLES} samples took {time.time() - tb:.0f} s")
        a = denoise_image(img, S)
        rgb = a[..., :3]
        peak = rgb.max(axis=2)
        pc = np.percentile(peak[peak > 1e-5], [50, 90, 99, 99.5, 100]) if (peak > 1e-5).any() else [1.0] * 5
        scale = float(pc[3])                         # the 99.5th percentile of the lit texels maps to white; the few hotter ones clip
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
                     "mean": round(float(rgb.mean()), 4), "materials": mats}
        print("  baked", report[n])
        bpy.data.images.remove(img)
        bpy.data.images.remove(png)
    for o in hidden:
        o.hide_render = False
    report["seconds"] = round(time.time() - t0)
    report["device"] = bpy.context.scene.cycles.device
    (stage_work() / "lightmaps.json").write_text(json.dumps(report, indent=1))
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Art"].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


def drop_addon_state():
    """The user's own add-ons keep state on the scene and the window manager (some of it local paths); the glTF exporter writes the
    scene's into the GLB's scene extras. Only Cycles' settings are kept."""
    for idb in list(bpy.data.scenes) + list(bpy.data.window_managers):
        g = idb.bl_system_properties_get()
        for k in [k for k in (g.keys() if g else []) if not k.startswith("cycles")]:
            del g[k]


def scrub_paths():
    """The .blend is committed to a public repo: no path into the work folder (the system temp folder by default) may stay in it.
    A packed image keeps its pixels in the file, so its source path is replaced by a neutral relative name; an unpacked image
    must live inside the repo. Every scene's render output path is cleared, the file browsers' folders too, and the state the
    user's own add-ons keep on the scene and the window manager is dropped; only Cycles' is kept."""
    root = str(ROOT.resolve()).lower()
    inside = lambda p: os.path.abspath(bpy.path.abspath(p)).lower().startswith(root)
    for im in list(bpy.data.images):
        if im.source != "FILE" or not im.filepath_raw:
            continue
        if im.packed_file is not None:
            if not inside(im.filepath_raw) or any(not inside(pf.filepath) for pf in im.packed_files):
                name, keep = im.name, dict(im.items())
                new = packed_image(name + "_clean", bytes(im.packed_file.data), im.colorspace_settings.name, fname=name, alpha=im.alpha_mode == "STRAIGHT" and im.channels == 4)
                for k, v in keep.items():
                    new[k] = v
                im.user_remap(new)
                bpy.data.images.remove(im)
                new.name = name
        elif not inside(im.filepath_raw):
            raise SystemExit(f"image {im.name} is neither packed nor inside the repo")
        else:
            wipe(im, "filepath_raw", im.filepath_raw)
    for sc in bpy.data.scenes:
        wipe(sc.render, "filepath", "")
    drop_addon_state()
    for scr in bpy.data.screens:
        for a in scr.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and sp.params:
                    wipe(sp.params, "directory", b"", b"_")


def wipe(owner, attr, value, run="_"):
    """A path field is a fixed buffer: a shorter new value leaves the old one's tail after its end, and that tail is saved. So the
    whole buffer is filled with a neutral run first (the setter cuts it to the buffer's size), then the value is set."""
    setattr(owner, attr, run * 4096)
    setattr(owner, attr, value)


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    bpy.ops.file.make_paths_relative()
    scrub_paths()
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
    drop_addon_state()
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False, export_animations=False)
    print("EXPORTED", raw, raw.stat().st_size)
    bpy.data.collections["Art"].hide_viewport = False
    exp.hide_viewport = exp.hide_render = True


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
    off = j["nodes"][0].get("translation", [0, 0, 0])
    centre = [(acc["min"][i] + acc["max"][i]) / 2 + off[i] for i in range(3)]
    a = K["arrive"]
    want = [a[0], a[1] + 0.1, a[2]]
    bl = sum((v.co for v in ob.data.vertices), Vector()) / len(ob.data.vertices)
    print(f"AXES blender centre {tuple(round(v, 3) for v in bl)} (x, -z, y of the game point {tuple(want)})")
    print(f"AXES glTF centre {tuple(round(v, 3) for v in centre)}, game point {tuple(want)}")
    assert all(abs(centre[i] - want[i]) < 1e-4 for i in range(3)), "the exporter's axes disagree with (x, -z, y)"
    assert abs(bl.x - want[0]) < 1e-4 and abs(bl.y + want[2]) < 1e-4 and abs(bl.z - want[1]) < 1e-4
    print("AXES PASS: game (x, y, z) = Blender (x, -z, y) = glTF (x, y, z)")


# ---------------------------------------------------------------- the review stills
def look_cam(name, loc, target, fov_v=75.0, ortho=None):
    cam = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
    cam.sensor_fit = "VERTICAL"
    if ortho:
        cam.type = "ORTHO"
        cam.ortho_scale = ortho
        cam.sensor_fit = "HORIZONTAL"
    else:
        cam.lens_unit = "FOV"
        cam.angle_y = math.radians(fov_v)
    cam.clip_start, cam.clip_end = 0.05, 100
    ob = bpy.data.objects.get(name) or bpy.data.objects.new(name, cam)
    if ob.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(ob)
    ob.location = B(loc)
    ob.rotation_euler = (B(target) - B(loc)).to_track_quat("-Z", "Y").to_euler() if target is not None else (0, 0, 0)
    return ob


def stage_render():
    sc = bpy.context.scene
    STILLS.mkdir(parents=True, exist_ok=True)
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
        bpy.data.collections["Export"].hide_viewport = True
    setup_cycles(arg("--samples", 128, int))
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.adaptive_threshold = 0.02
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = arg("--exposure", 0.0, float)
    which = arg("--only", "all")
    if ENGINE.upper().startswith("EEVEE"):
        ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
        sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in ids else "BLENDER_EEVEE_NEXT"
    arrive, face = K["arrive"], K["face"]
    zc = BELT["zc"]
    shots = {
        "1_arrival": look_cam("arrival", (arrive[0], 1.6, arrive[2]), (arrive[0] + face[0] * 3, 1.6, arrive[2] + face[1] * 3), 75.0),
        "2_wide": look_cam("wide", (HX - 1.4, 4.4, HZ - 0.8), (-3.0, 0.8, -2.0), 70.0),
        "3_detail": look_cam("detail", (BELT["x0"] + 2.6, 1.7, zc + 2.7), (BELT["x0"] + 0.1, 1.05, zc - 0.2), 62.0),
    }
    plan = look_cam("plan", (0, H + 6, 0), None, ortho=2 * HX + 0.8)
    arts = bpy.data.collections["Art"].objects
    cut_plan = [o for o in arts if o.name.startswith(("Ceiling_", "Roof_", "Crane_", "Lamp_", "Hopper", "Services_Tray", "Heaters"))]
    cut_wide = [o for o in arts if o.name.startswith(("Crane_Hook",))]
    todo = [(k, v, (1920, 1080)) for k, v in shots.items()] + [("4_plan", plan, (1600, int(1600 * (2 * HZ + 0.8) / (2 * HX + 0.8))))]
    for key, cam, (w, h) in todo:
        if which not in ("all", key):
            continue
        sc.camera = cam
        for o in arts:
            o.visible_camera = True
        for o in {"4_plan": cut_plan, "2_wide": cut_wide}.get(key, []):
            o.visible_camera = False                      # a cut-away view: these stay for the light and the shadows, the camera just does not see them
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, arg("--scale", 100, int)
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        path = STILLS / f"{key}.jpg" if key != "4_plan" else stage_work() / "plan.jpg"
        sc.render.filepath = str(path)
        import time
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 400_000 and q > 40 and key != "4_plan":
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        strip_jpeg_meta(path)
        print("STILL", key, path.stat().st_size, "q", q, f"{time.time() - t0:.0f} s")
    for o in arts:
        o.visible_camera = True


if __name__ == "__main__":
    if STAGE == "textures":
        stage_textures()
        raise SystemExit(0)
    derive()
    LAMP_ROWS[:] = [K["belt"]["z"], K["bins"][0]["z"] - 0.5]
    if STAGE in ("art", "all"):
        build_all()
        save_blend()
    else:
        for m in bpy.data.materials:
            MATS[m.name] = m
    if STAGE in ("bake", "all"):
        stage_bake()
    if STAGE in ("export", "all"):
        stage_export()
    if STAGE in ("axes", "all"):
        stage_axes()
        save_blend()
    if STAGE in ("render", "all"):
        stage_render()
