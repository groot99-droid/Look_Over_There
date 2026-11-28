"""Dresses and lights the hotel atrium (`atrium`, docs/BLENDER_AREAS.md section 1), bakes it at night, and exports world/atrium.glb and world/atrium.json.

Re-runnable, from the repo root:

    blender -b --factory-startup --python tools/blender/build_atrium.py -- --stage art     (the art, the layout objects and the kit, saves blender/scenes/atrium.blend)
    blender -b blender/scenes/atrium.blend --python tools/blender/build_atrium.py -- --stage layout   (world/atrium.json through export_scene.py)
    blender -b blender/scenes/atrium.blend --python tools/blender/build_atrium.py -- --stage check    (tools/blender/check_layout.py: the Art and the kit)
    blender -b blender/scenes/atrium.blend --python tools/blender/build_atrium.py -- --stage bake [--samples 384]
    python tools/blender/build_atrium.py --tone [--work <dir>]                     (no Blender: the bake's raw light -> the lightmap PNGs, by CURVE)
    blender -b blender/scenes/atrium.blend --python tools/blender/build_atrium.py -- --stage export
    blender -b blender/scenes/atrium.blend --python tools/blender/build_atrium.py -- --stage axes     (the marker-cube axes check)
    blender -b blender/scenes/atrium.blend --python tools/blender/build_atrium.py -- --stage render [--render-samples 128] [--only 1_arrival]
    python tools/blender/pack_scene.py atrium --work work/atrium                           (WebP lightmaps and textures -> world/)

The layout is the greybox's: tools/blender/build_hotel_greybox.py `atrium()` (imported here; no coordinate is copied by hand) gives every collider,
door, link, marker and spot, and this build puts the art round them under the same names, so tools/blender/export_scene.py writes the same
world/atrium.json as the greybox model (`build_hotel_greybox.py --preview`). The elevator is the connector kit's (blender/kit/README.md):
tools/blender/kit_place.py places its layout at the four stops (at (0, y, -14), yaw 180); the car (at the ground stop) and the landings are
appended as stand-ins only (the Kit collection: in the bake, the layout check and the stills, never in the GLB): the page draws world/kit/elevator.glb
at each stop and moves the car.

The look: a vast, liminal hotel atrium at night, under a skylight lit by the city's glow. Four galleries, each with its floor's character:
the sub floor (y 0) white tile, damp toward the pool doors; floor 1 (y 4) the motel: two-tone vinyl walls, red carpet, numbered room doors;
floor 2 (y 8) green carpet and green damask paper over dark wood; floor 3 (y 12) the apartments: cream paint over white panelling, tan carpet, apartment
doors. Brass-railed balustrades with globe lamps on their posts, ivy troughs hung over the void, hanging baskets from the skylight, a quiet fountain and
four palms on the floor, wall sconces (Lamp_Emit) on every gallery, EXIT signs (Emergency_Emit) over the stairs, a few lamps dead.
The facade doors on the upper galleries are flush panels that do not open (places for later features, as the lobby's); the real doors are the greybox's.
Light: one night set (`lightmap`, `lightmap_intensity`): the sconces, the rail lamps and the skylight's city glow. Lamp_Emit and Emergency_Emit are on in it.
"""
import json
import math
import os
import sys
from pathlib import Path

try:
    import bpy
    import bmesh
    from mathutils import Matrix, Vector
except ImportError:          # the --tone step runs in plain Python
    bpy = None
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import build_hotel_greybox as G          # noqa: E402  the layout model (pure Python)

SCENE = "atrium"
TEX = ROOT / f"blender/textures/{SCENE}"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"
MARGIN_PX = 8

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 384, int)
DEVICE = arg("--device", "auto")

GB = G.atrium()
BOX = {b["name"]: b for b in GB.boxes}
A = G.ATR                    # 18: the walls' inner faces at x, z = +-18
GL = A - G.GAL               # 14: the galleries' void edge
T = G.T
H = G.ATR_H                  # 16
LEVELS = list(G.LEVELS)      # 0, 4, 8, 12
BANDS = {0.0: "Wall_Sub", 4.0: "Wall_Motel", 8.0: "Wall_Green", 12.0: "Wall_Apart"}
CARPET = {4.0: "Carpet_Motel", 8.0: "Carpet_Green", 12.0: "Carpet_Apart"}
SPAWN = next(e for e in GB.empties if e["name"] == "Marker_Spawn")["pos"]
ARRIVE_LOBBY = next(e for e in GB.empties if e["name"] == "Arrive_lobby")
SHAFT_Z0 = -GL               # -14: the shaft's front (north) face
HALL_X1 = 28.0
SKY_Y = 17.6                 # the sky panel over the skylight's light well
KIT_AT = [(0.0, y, SHAFT_Z0) for y in LEVELS]


def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


def level_of(y):
    return max(lv for lv in LEVELS if lv <= y + 1e-6)


# ---------------------------------------------------------------- materials
IMG_CACHE, MATS, TILES = {}, {}, {}
LAMP_EMIT = 6.0              # Lamp_Emit's exported strength (the glow of every lamp's shade or globe)
EXIT_EMIT = 2.0              # Emergency_Emit's (the EXIT signs)
SKY_SHOW = 1.0               # the skylight's sky panel, as the page shows it
SKY_BAKE = 3.0               # and as it lights the bake and the stills (the city's glow on the clouds)


def image(fn, srgb=True):
    key = (fn, srgb)
    if key not in IMG_CACHE:
        im = bpy.data.images.load(str(TEX / fn))
        im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
        IMG_CACHE[key] = im
    return IMG_CACHE[key]


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, diff=None, img=None, tint=None, emit=None, emit_img=None, alpha=None, tile=None,
             two_sided=False):
    """A Principled material. `tint` multiplies the diffuse texture (written by the glTF exporter as baseColorFactor). `tile`: metres per repeat
    (u, v) of the box projection."""
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
        if emit_img is not None:
            n = nt.nodes.new("ShaderNodeTexImage")
            n.image = emit_img
            nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
            nt.links.new(n.outputs["Color"], bsdf.inputs["Emission Color"])
            bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
    if alpha is not None:
        bsdf.inputs["Alpha"].default_value = alpha
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    m.use_backface_culling = not two_sided
    t = tile or 1.0
    TILES[name] = (t, t) if not isinstance(t, tuple) else t
    MATS[name] = m
    return m


def make_materials(gen):
    material("Floor_Tile", img=gen["floor_tile"], rough=0.3, tile=1.2)
    material("Floor_Tile_Damp", img=gen["floor_damp"], rough=0.3, tile=1.2)
    material("Floor_Tile_Wet", img=gen["floor_wet"], rough=0.15, tile=1.2)
    for lv, name in BANDS.items():                      # each band's wall picture spans the band: 2 m along, 4 m up (see wall_uv)
        material(name, img=gen[name], rough=0.7, tile=(2.0, 4.0))
    material("Carpet_Motel", img=gen["carpet_motel"], rough=1.0, tile=1.6)
    material("Carpet_Green", img=gen["carpet_green"], rough=1.0, tile=1.6)
    material("Carpet_Apart", img=gen["carpet_apart"], rough=1.0, tile=1.6)
    material("Ceiling_Plaster", diff="plastered_wall_04_diff_1k.jpg", tint=(0.90, 0.88, 0.84), rough=0.95, tile=2.5)
    material("Fascia", img=gen["fascia"], rough=0.6, tile=(2.0, 0.3))
    material("Column_Plaster", diff="plastered_wall_04_diff_1k.jpg", tint=(0.86, 0.83, 0.76), rough=0.9, tile=1.5)
    material("Marble", diff="marble_01_diff_1k.jpg", tint=(0.92, 0.90, 0.86), rough=0.25, tile=1.2)
    material("Brass", color=(0.60, 0.44, 0.19), rough=0.35, metal=0.9)
    material("Iron_Black", color=(0.035, 0.035, 0.035), rough=0.5, metal=0.6)
    material("Shaft_Steel", diff="painted_metal_shutter_diff_1k.jpg", tint=(0.34, 0.44, 0.40), rough=0.5, tile=2.0)
    material("Shaft_Inner", color=(0.08, 0.08, 0.08), rough=0.8)
    material("Hall_Wall", diff="beige_wall_001_diff_1k.jpg", tint=(0.86, 0.80, 0.68), rough=0.9, tile=2.0)
    material("Hall_Floor", diff="herringbone_parquet_diff_1k.jpg", tint=(0.70, 0.58, 0.46), rough=0.5, tile=1.6)
    material("Wood_Dark", diff="dark_wood_diff_1k.jpg", tint=(0.80, 0.72, 0.66), rough=0.45, tile=1.0)
    material("Trim_White", color=(0.80, 0.78, 0.72), rough=0.6)
    material("Doors", img=gen["doors"], rough=0.5, tile=1.0)
    material("Sign_Paint", img=gen["signs"], rough=0.6, tile=1.0)
    material("Planter", color=(0.10, 0.20, 0.17), rough=0.35)
    material("Soil", color=(0.07, 0.05, 0.035), rough=1.0)
    material("Plant_Leaf", color=(0.09, 0.22, 0.07), rough=0.6, two_sided=True)
    material("Palm_Trunk", color=(0.30, 0.24, 0.16), rough=0.9)
    material("Water_Still", color=(0.04, 0.09, 0.10), rough=0.05)
    material("Bulb_Dead", color=(0.30, 0.28, 0.25), rough=0.2)
    material("Lamp_Emit", color=(1.0, 0.92, 0.78), rough=0.5, emit=((1.0, 0.78, 0.52), LAMP_EMIT))
    material("Emergency_Emit", color=(0.0, 0.0, 0.0), rough=0.5, emit=((1, 1, 1), EXIT_EMIT), emit_img=gen["exit"])
    material("Skylight_Sky", color=(0.0, 0.0, 0.0), rough=1.0, emit=((1, 1, 1), SKY_SHOW), emit_img=gen["sky"])
    material("Glass_Skylight", color=(0.55, 0.62, 0.60), rough=0.1, alpha=0.18, two_sided=True)


EMITS = ("Lamp_Emit", "Emergency_Emit", "Skylight_Sky")
UNBAKED = EMITS + ("Glass_Skylight",)


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
    """UV0: box projection in metres / tile (u, v) from world positions, so a texture runs on across pieces."""
    tu, tv = tile
    uvl = bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y
            u, v = ((gz, gy) if ax == 0 else (gx, gy) if ax == 1 else (gx, gz))
            lp[uvl].uv = (u / tu, v / tv)


def wall_uv(bm, y0):
    """A band's wall picture: u along the wall (2 m a repeat, read the right way round from inside), v from the band's floor (0) to its top (1)."""
    uvl = bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y
            if ax == 0:                  # faces x (Blender x): the W and E walls; along game z
                u = (-gz if n.x > 0 else gz)
            elif ax == 1:                # faces game z: the N and S walls; along game x
                u = (gx if n.y < 0 else -gx)
            else:
                u = gx
            lp[uvl].uv = (u / 2.0, (gy - y0) / 4.0)


ART = KIT_C = DOORS_C = LAYOUT_C = None


def finish(name, bm, mat, coll=None, smooth=False, keep_uv=False, uv_fn=None, recalc=True):
    for e in bm.edges:
        e.smooth = smooth and len(e.link_faces) == 2 and e.calc_face_angle(0.0) < math.radians(40)
    for f in bm.faces:
        f.smooth = smooth
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if not bm.loops.layers.uv.get("UVMap"):
        bm.loops.layers.uv.new("UVMap")
    if not keep_uv:
        bm.normal_update()
        uv_fn(bm) if uv_fn else box_uv(bm, TILES[mat])
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


def boxes_of(name, mat, bxs, **kw):
    """One object of axis boxes [(min, max)] in game space."""
    return part(name, mat, lambda bm: [cube(bm, mn, mx) for mn, mx in bxs], **kw)


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
WALLS = {"N": ("+z", -A), "S": ("-z", A), "W": ("+x", -A), "E": ("-x", A)}      # side: (inward normal, the inner face's coordinate)


def on_wall(side, a, y, d):
    """A game point in front of wall `side`: a along it (x for N/S, z for W/E), height y, d metres into the room."""
    n, face = WALLS[side]
    off = face + (1 if n[0] == "+" else -1) * d
    return (off, y, a) if n[1] == "x" else (a, y, off)


def wall_box(bm, side, a0, a1, y0, y1, d0, d1):
    p, q = on_wall(side, a0, y0, d0), on_wall(side, a1, y1, d1)
    cube(bm, [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)])


# ---------------------------------------------------------------- generated pictures (numpy, own work, fixed seeds)
GLYPHS = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"], "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"], "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"], "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"], "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"], "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"], "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"], "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"], "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"], "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"], "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    " ": ["00000"] * 7, "<": ["00010", "00100", "01000", "10000", "01000", "00100", "00010"], ">": ["01000", "00100", "00010", "00001", "00010", "00100", "01000"],
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


def vnoise(h, w, rng, octaves=5, base=4, wrap=False, base_w=None):
    out, amp, tot = np.zeros((h, w)), 1.0, 0.0
    for k in range(octaves):
        n = base * 2 ** k
        m = (base_w or base) * 2 ** k
        g = rng.random((n + 1, m + 1))
        if wrap:
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


def lerp(img, mask, col, k=1.0):
    return img * (1 - k * mask[..., None]) + np.array(col) * (k * mask)[..., None]


def tiles(S, n, grout_px, base, rng, var=0.04, grout=(0.55, 0.56, 0.53)):
    """n x n square tiles over S px, each a slightly different white, with grout lines."""
    yy, xx = np.mgrid[0:S, 0:S]
    p = S // n
    ti, tj = yy // p, xx // p
    shade = rng.normal(1.0, var, (n, n))[ti, tj]
    img = np.ones((S, S, 3), np.float32) * np.array(base) * shade[..., None]
    g = ((xx % p) < grout_px) | ((yy % p) < grout_px)
    img[g] = grout
    return img, g


def floor_tile_pixels(kind):
    """The sub floor: 15 cm white tiles (8 x 8 a repeat, 1.2 m), grey grout. damp: the grout darker, greyer tiles, grime blooms; wet: darker still,
    with shallow puddles that catch the light (lighter, smoother patches)."""
    S = 1024
    rng = np.random.default_rng({"clean": 3, "damp": 4, "wet": 5}[kind])
    img, g = tiles(S, 8, 4, (0.84, 0.85, 0.83), rng, 0.025, (0.50, 0.50, 0.47))
    n = vnoise(S, S, rng, 6, 3, wrap=True)
    img *= (0.93 + 0.1 * n[..., None])
    if kind in ("damp", "wet"):
        grime = np.clip((vnoise(S, S, rng, 5, 2, wrap=True) - 0.45) * 3, 0, 1)
        img = lerp(img, grime, (0.48, 0.50, 0.44), 0.45)
        img[g] = img[g] * 0.62 * np.array([0.92, 0.98, 0.9])
    if kind == "wet":
        img *= 0.82
        pud = np.clip((vnoise(S, S, rng, 4, 2, wrap=True) - 0.55) * 6, 0, 1)
        img = lerp(img, pud, (0.36, 0.40, 0.40), 0.55)
    return np.clip(img, 0, 1).astype(np.float32)


def band_pixels(name):
    """A gallery's wall, one picture for the whole band: 2 m along (1024 px) and 4 m up (2048 px; row 0 is the band's top)."""
    W, Hh = 1024, 2048
    rng = np.random.default_rng({"Wall_Sub": 7, "Wall_Motel": 8, "Wall_Green": 9, "Wall_Apart": 10}[name])
    yy, xx = np.mgrid[0:Hh, 0:W]
    ym = (Hh - 1 - yy) / Hh * 4.0                                   # metres above the band's floor
    xm = xx / W * 2.0
    n = vnoise(Hh, W, rng, 6, 8, wrap=True, base_w=4)
    img = np.zeros((Hh, W, 3), np.float32)
    if name == "Wall_Sub":                                            # white glazed tile to 3.4 m (20 cm tiles), a green band at 1.2 m, damp rising
        p = W // 10
        tj, ti = xx // p, (Hh - 1 - yy) // p
        shade = rng.normal(1.0, 0.03, (41, 11))[np.clip(ti, 0, 40), np.clip(tj, 0, 10)]
        img[:] = np.array([0.86, 0.87, 0.85]) * shade[..., None]
        green = (ym >= 1.2) & (ym < 1.4)
        img[green] = np.array([0.10, 0.30, 0.24]) * shade[green][..., None]
        cove = ym < 0.12
        img[cove] = (0.60, 0.62, 0.58)
        grout = (((xx % p) < 3) | (((Hh - 1 - yy) % p) < 3)) & (ym < 3.4)
        img[grout] = (0.52, 0.52, 0.49)
        top = ym >= 3.4                                              # painted plaster above the tiles, stained
        img[top] = np.array([0.80, 0.79, 0.74]) * (0.92 + 0.1 * n[top][..., None])
        img[(ym >= 3.38) & (ym < 3.42)] = (0.70, 0.70, 0.66)
        tide = 0.45 + 0.35 * vnoise(1, W, rng, 4, 1, wrap=True, base_w=6)[0]       # the damp's tide line, up to about 0.8 m
        damp = np.clip((tide[None, :] - ym) / 0.25, 0, 1) * (0.6 + 0.4 * n)
        img = lerp(img, damp, (0.50, 0.52, 0.44), 0.5)
        streak = np.clip((vnoise(Hh, W, rng, 3, 1, wrap=True, base_w=24) - 0.62) * 5, 0, 1) * np.clip((3.4 - ym) / 1.0, 0, 1) * (ym > 2.0)
        img = lerp(img, streak, (0.55, 0.52, 0.44), 0.35)
    elif name == "Wall_Motel":                                        # two-tone vinyl: brown below a wood chair rail at 0.9 m, ochre above
        img[:] = np.array([0.62, 0.52, 0.36]) * (0.94 + 0.08 * n[..., None])
        lo = ym < 0.9
        img[lo] = np.array([0.30, 0.20, 0.13]) * (0.92 + 0.1 * n[lo][..., None])
        grain = vnoise(Hh, W, rng, 3, 64, wrap=True, base_w=2)
        img[lo] *= (0.94 + 0.1 * grain[lo][..., None])
        img[(ym >= 0.9) & (ym < 0.98)] = (0.38, 0.24, 0.13)
        img[(ym >= 0.97) & (ym < 0.985)] = (0.52, 0.36, 0.2)
        img[ym < 0.1] = (0.14, 0.09, 0.06)
        stripe = (((xm * 10) % 1.0) < 0.06) & ~lo
        img[stripe] *= 0.92
        img[ym > 3.82] = np.array([0.72, 0.66, 0.54]) * (0.95 + 0.05 * n[ym > 3.82][..., None])
        stain = np.clip((vnoise(Hh, W, rng, 4, 2, wrap=True) - 0.6) * 4, 0, 1) * (ym > 2.6)
        img = lerp(img, stain, (0.48, 0.38, 0.24), 0.3)
    elif name == "Wall_Green":                                        # green damask over dark wood panelling to 1.0 m, a brass-coloured rail
        img[:] = (0.36, 0.52, 0.38)
        fx = np.abs(((xm / 0.5) % 1) - 0.5) * 2
        fy = (ym / 0.7) % 1
        r = np.sqrt((fx * 0.9) ** 2 + ((fy - 0.5) * 1.3) ** 2)
        th = np.arctan2(fy - 0.5, fx + 1e-3)
        leaf = np.clip(((0.32 + 0.1 * np.cos(3 * th) + 0.05 * np.cos(7 * th)) - r) / 0.02, 0, 1) * np.clip((r - 0.08) / 0.02, 0, 1)
        img = lerp(img, leaf, (0.50, 0.64, 0.48), 0.55)
        img *= (0.9 + 0.14 * n[..., None])
        lo = ym < 1.0
        p = 0.5
        pan = (np.abs(((xm / p) % 1) - 0.5) < 0.42) & (ym > 0.18) & (ym < 0.86)
        wood = np.array([0.40, 0.25, 0.15]) * (0.9 + 0.14 * n[..., None])
        img[lo] = wood[lo]
        img[lo & pan] *= 0.86
        img[(ym >= 1.0) & (ym < 1.05)] = (0.50, 0.38, 0.17)
        img[ym < 0.12] = (0.12, 0.07, 0.04)
        img[ym > 3.84] = (0.24, 0.15, 0.09)
    else:                                                             # Wall_Apart: cream paint over white panelling (wainscot to 0.95 m)
        img[:] = np.array([0.80, 0.75, 0.62]) * (0.95 + 0.07 * n[..., None])
        lo = ym < 0.95
        img[lo] = (0.82, 0.81, 0.77)
        pan = (np.abs(((xm / 0.66) % 1) - 0.5) < 0.40) & (ym > 0.18) & (ym < 0.80)
        edge = pan & ~((np.abs(((xm / 0.66) % 1) - 0.5) < 0.38) & (ym > 0.2) & (ym < 0.78))
        img[edge] = (0.66, 0.65, 0.61)
        img[(ym >= 0.95) & (ym < 1.0)] = (0.86, 0.85, 0.81)
        img[ym < 0.14] = (0.84, 0.83, 0.79)
        img[(ym >= 0.13) & (ym < 0.145)] = (0.62, 0.61, 0.57)
        img[ym > 3.86] = (0.86, 0.85, 0.80)
        scuff = np.clip((vnoise(Hh, W, rng, 4, 4, wrap=True) - 0.6) * 4, 0, 1) * (ym < 1.4)
        img = lerp(img, scuff, (0.62, 0.58, 0.50), 0.3)
    return np.clip(img, 0, 1).astype(np.float32)


def carpet_pixels(kind):
    """The galleries' carpets, 1.6 m a repeat: motel red with an orange-and-brown hex lattice; deep green with small gold fleurons; tan apartments'
    carpet with a faint check."""
    S = 1024
    rng = np.random.default_rng({"motel": 21, "green": 22, "apart": 23}[kind])
    yy, xx = (np.mgrid[0:S, 0:S] + 0.5) / S
    img = np.zeros((S, S, 3), np.float32)
    if kind == "motel":
        img[:] = (0.52, 0.13, 0.10)
        fx, fy = (xx * 4) % 1.0, (yy * 4) % 1.0
        d = np.maximum(np.abs(fx - 0.5) * 1.15 + np.abs(fy - 0.5) * 0.6, np.abs(fy - 0.5) * 1.2)
        img = lerp(img, np.clip(1 - np.abs(d - 0.48) / 0.03, 0, 1), (0.62, 0.30, 0.10))
        img = lerp(img, np.clip(1 - np.abs(d - 0.36) / 0.015, 0, 1), (0.20, 0.08, 0.05))
        img = lerp(img, np.clip((0.12 - np.hypot(fx - 0.5, fy - 0.5)) / 0.02, 0, 1), (0.70, 0.46, 0.16))
    elif kind == "green":
        img[:] = (0.17, 0.38, 0.21)
        fx, fy = (xx * 5) % 1.0, (yy * 5) % 1.0
        r = np.hypot(fx - 0.5, fy - 0.5)
        th = np.arctan2(fy - 0.5, fx - 0.5)
        fl = np.clip(((0.10 + 0.05 * np.cos(4 * th)) - r) / 0.015, 0, 1)
        img = lerp(img, fl, (0.70, 0.58, 0.28))
        bx = (np.abs(fx - 0.5) > 0.47) | (np.abs(fy - 0.5) > 0.47)
        img[bx] = (0.12, 0.29, 0.15)
    else:
        img[:] = (0.50, 0.42, 0.31)
        chk = ((xx * 8).astype(int) + (yy * 8).astype(int)) % 2 == 0
        img[chk] *= 0.94
    n = vnoise(S, S, rng, 6, 4, wrap=True)
    pile = vnoise(S, S, rng, 2, 128, wrap=True)
    img = img * (0.84 + 0.24 * n[..., None]) * (0.92 + 0.1 * pile[..., None])
    return np.clip(img, 0, 1).astype(np.float32)


def fascia_pixels():
    """The galleries' slab edge, 0.3 m high, 2 m a repeat: a cream painted band between two mouldings, a brass line, dentils below."""
    W, Hh = 1024, 160
    rng = np.random.default_rng(31)
    yy, xx = np.mgrid[0:Hh, 0:W]
    img = np.zeros((Hh, W, 3), np.float32)
    img[:] = (0.80, 0.76, 0.66)
    img[:14] = (0.66, 0.62, 0.53)
    img[14:18] = (0.62, 0.48, 0.22)
    img[-30:] = (0.70, 0.66, 0.57)
    dent = ((xx % 32) < 18) & (yy > Hh - 26) & (yy < Hh - 8)
    img[dent] = (0.78, 0.74, 0.65)
    img[-4:] = (0.5, 0.47, 0.4)
    img *= (0.9 + 0.14 * vnoise(Hh, W, rng, 4, 2, wrap=True, base_w=8)[..., None])
    return np.clip(img, 0, 1).astype(np.float32)


# the sign atlas: 4 columns x 16 rows of 256 x 64 px cells
SIGN_CELLS = [f"POOL {k}" for k in range(1, 12)] + ["STAIRS", "ESCALATORS", "LOBBY", "FLOOR 1", "FLOOR 2", "FLOOR 3", "SUB FLOOR"] + \
             [f"{100 * f + k}" for f in (1, 2) for k in range(1, 9)] + [f"3{c}" for c in "ABCDEFGH"]


def sign_cell_uv(text):
    i = SIGN_CELLS.index(text)
    r, c = i // 4, i % 4
    return (c / 4, 1 - (r + 1) / 16, (c + 1) / 4, 1 - r / 16)


def signs_pixels():
    S = 1024
    rng = np.random.default_rng(17)
    img = np.zeros((S, S, 3), np.float32)
    brass, dark, cream, gold = (0.66, 0.50, 0.22), (0.10, 0.09, 0.08), (0.88, 0.84, 0.72), (0.80, 0.62, 0.28)
    for i, t in enumerate(SIGN_CELLS):
        r, c = i // 4, i % 4
        if t.startswith("POOL") or t.isdigit() or (len(t) == 2 and t[0] == "3"):
            bg, fg, b = brass, (0.12, 0.08, 0.04), (0.45, 0.33, 0.12)
        elif t.startswith(("FLOOR", "SUB")):
            bg, fg, b = (0.80, 0.76, 0.66), (0.30, 0.22, 0.10), (0.62, 0.48, 0.22)
        else:
            bg, fg, b = dark, cream, gold
        cell = np.zeros((64, 256, 3), np.float32)
        cell[:] = bg
        m = text_mask(t, 64, 256, fill=0.55, maxw=0.86)
        cell = lerp(cell, m, fg)
        cell *= (0.9 + 0.16 * vnoise(64, 256, rng, 4, 2, base_w=8)[..., None])
        cell[:3] = cell[-3:] = cell[:, :3] = cell[:, -3:] = b
        img[r * 64:(r + 1) * 64, c * 256:(c + 1) * 256] = cell
    return np.clip(img, 0, 1).astype(np.float32)


def exit_pixels():
    """The EXIT sign's face (an emission map): white letters and a running arrow on green."""
    h, w = 128, 384
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (0.0, 0.55, 0.18)
    m = text_mask("EXIT >", h, w, fill=0.6, maxw=0.82)
    img = lerp(img, m, (0.95, 1.0, 0.95))
    img[:6] = img[-6:] = img[:, :6] = img[:, -6:] = (0.0, 0.30, 0.10)
    return img


def sky_pixels():
    """The night sky over the skylight: low cloud lit from below by the city's sodium glow, brightest toward the south-east (the street side), a few
    breaks of dark blue."""
    S = 1024
    rng = np.random.default_rng(41)
    yy, xx = (np.mgrid[0:S, 0:S] + 0.5) / S
    cl = vnoise(S, S, rng, 7, 3)
    glow = 0.55 + 0.45 * np.clip(xx * 0.6 + yy * 0.6, 0, 1)
    dense = np.clip((cl - 0.35) * 2.2, 0, 1)
    amber, blue = np.array([0.42, 0.24, 0.12]), np.array([0.02, 0.03, 0.07])
    img = blue + (amber - blue) * (dense * glow)[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


# the doors atlas: 2048 x 1024, seven columns of 292 px, one door each: 0 pool, 1 fire, 2 dark wood, 3 cream panel; the facades 4 motel, 5 floor 2, 6 apartment
DOOR_COLS = {"pool": 0, "fire": 1, "wood": 2, "panel": 3, "motel": 4, "green": 5, "apart": 6}
DW, DH = 2048, 1024
CW = DW // 7


def door_uv(kind):
    c = DOOR_COLS[kind]
    return (c * CW / DW, 0.0, (c + 1) * CW / DW, 1.0)


EDGE_PIX = {"brass": (2040 / DW, 1 - 4 / DH), "steel": (2040 / DW, 1 - 12 / DH), "cream": (2040 / DW, 1 - 20 / DH)}


def doors_pixels():
    rng = np.random.default_rng(43)
    img = np.zeros((DH, DW, 3), np.float32)
    W_M, H_M = 0.94, 2.16

    def col(kind):
        c = DOOR_COLS[kind]
        return img[:, c * CW:(c + 1) * CW]

    yy, xx = np.mgrid[0:DH, 0:CW]
    um, vm = xx / CW * W_M, (DH - 1 - yy) / DH * H_M          # metres across and up the leaf
    n = vnoise(DH, CW, rng, 5, 8, base_w=2)

    def panels(c, base, rects, lo=0.88, hi=1.08):
        c[:] = np.array(base) * (0.9 + 0.12 * n[..., None])
        for (u0, v0, u1, v1) in rects:
            ins = (um > u0) & (um < u1) & (vm > v0) & (vm < v1)
            c[ins] *= 0.93
            c[(um > u0) & (um < u1) & (np.abs(vm - v1) < 0.012)] *= hi
            c[(um > u0) & (um < u1) & (np.abs(vm - v0) < 0.012)] *= lo
            c[(vm > v0) & (vm < v1) & (np.abs(um - u0) < 0.012)] *= hi
            c[(vm > v0) & (vm < v1) & (np.abs(um - u1) < 0.012)] *= lo
    c = col("pool")                                            # white painted, a frosted porthole, a steel kick plate
    c[:] = np.array([0.82, 0.83, 0.80]) * (0.9 + 0.12 * n[..., None])
    r = np.hypot(um - W_M / 2, vm - 1.55)
    c[r < 0.19] = (0.50, 0.50, 0.46)
    c[r < 0.165] = np.array([0.72, 0.78, 0.78]) * (0.95 + 0.06 * n[r < 0.165][..., None])
    c[vm < 0.25] = (0.55, 0.56, 0.55)
    c = col("fire")                                            # grey steel, a wired-glass slit, a kick plate
    c[:] = np.array([0.38, 0.40, 0.40]) * (0.92 + 0.1 * n[..., None])
    slit = (np.abs(um - W_M / 2) < 0.1) & (vm > 1.25) & (vm < 1.85)
    c[slit] = (0.55, 0.60, 0.60)
    wire = slit & (((um * 40) % 1 < 0.08) | ((vm * 40) % 1 < 0.08))
    c[wire] = (0.30, 0.32, 0.32)
    c[vm < 0.28] = (0.30, 0.31, 0.31)
    c = col("wood")                                            # dark stained wood, plain; the maze's
    c[:] = np.array([0.18, 0.10, 0.06]) * (0.85 + 0.2 * vnoise(DH, CW, rng, 3, 64, base_w=2)[..., None])
    panels(col("panel"), (0.80, 0.76, 0.64), [(0.1, 1.15, 0.84, 2.0), (0.1, 0.2, 0.84, 1.0)])
    c = col("motel")                                           # teak-look laminate, a peephole, a number plate (a separate sign)
    c[:] = np.array([0.42, 0.25, 0.13]) * (0.88 + 0.16 * vnoise(DH, CW, rng, 3, 64, base_w=2)[..., None])
    c[np.hypot(um - W_M / 2, vm - 1.55) < 0.015] = (0.6, 0.48, 0.24)
    panels(col("green"), (0.24, 0.13, 0.08), [(0.1, 1.45, 0.42, 2.0), (0.52, 1.45, 0.84, 2.0), (0.1, 0.8, 0.42, 1.3), (0.52, 0.8, 0.42 + 0.42, 1.3),
                                               (0.1, 0.15, 0.42, 0.65), (0.52, 0.15, 0.84, 0.65)])
    panels(col("apart"), (0.84, 0.83, 0.79), [(0.12, 1.1, 0.82, 1.98), (0.12, 0.18, 0.82, 0.95)])
    c = col("apart")
    c[np.hypot(um - W_M / 2, vm - 1.55) < 0.014] = (0.6, 0.48, 0.24)
    img[0:8, DW - 12:DW] = (0.66, 0.50, 0.22)
    img[8:16, DW - 12:DW] = (0.38, 0.40, 0.40)
    img[16:24, DW - 12:DW] = (0.82, 0.80, 0.74)
    return np.clip(img, 0, 1).astype(np.float32)


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
    g = {"floor_tile": mk_image("Sub_Floor_Tile", floor_tile_pixels("clean")), "floor_damp": mk_image("Sub_Floor_Damp", floor_tile_pixels("damp")),
         "floor_wet": mk_image("Sub_Floor_Wet", floor_tile_pixels("wet")),
         "carpet_motel": mk_image("Carpet_Motel", carpet_pixels("motel")), "carpet_green": mk_image("Carpet_Green", carpet_pixels("green")),
         "carpet_apart": mk_image("Carpet_Apart", carpet_pixels("apart")), "fascia": mk_image("Gallery_Fascia", fascia_pixels()),
         "doors": mk_image("Atrium_Doors", doors_pixels()), "signs": mk_image("Atrium_Signs", signs_pixels()),
         "exit": mk_image("Exit_Sign", exit_pixels()), "sky": mk_image("Night_Sky", sky_pixels())}
    for name in BANDS.values():
        g[name] = mk_image(name, band_pixels(name))
    return g


# ---------------------------------------------------------------- the shell: the floor, the walls (a band per gallery), the galleries, the ceiling
WET = []                     # (x0, x1, z0, z1) of the wet patches in front of the pool doors


def pool_doors():
    return [d for d in GB.doors if d["name"].startswith("DoorLeaf_pool_")]


def door_centre(d):
    """(side, a): the wall a door is in and its middle along that wall."""
    hx, _, hz = d["hinge"]
    w = d["props"]["width"]
    yaw = math.radians(d["props"]["closed_yaw_deg"])
    cx, cz = hx + math.cos(yaw) * w / 2, hz - math.sin(yaw) * w / 2
    if abs(cz + A) < 0.3:
        return "N", cx
    if abs(cz - A) < 0.3:
        return "S", cx
    if abs(cx + A) < 0.3:
        return "W", cz
    if abs(cx - A) < 0.3:
        return "E", cz
    return None, (cx, cz)


def build_floor():
    """The ground floor in cells of three tiles: clean in the void and the east, damp under the north, west and south galleries (toward the
    pools), wet in front of every pool door."""
    fl = BOX["Atrium_Floor"]
    for d in pool_doors():
        side, a = door_centre(d)
        if side == "N":
            WET.append((a - 1.2, a + 1.2, -A, -A + 2.4))
        elif side == "S":
            WET.append((a - 1.2, a + 1.2, A - 2.4, A))
        else:
            WET.append((-A, -A + 2.4, a - 1.2, a + 1.2))
    xs = sorted({fl["min"][0], -GL, GL, fl["max"][0]} | {v for w in WET for v in w[:2]})
    zs = sorted({fl["min"][2], -GL, GL, fl["max"][2]} | {v for w in WET for v in w[2:]})
    cells = {"Floor_Tile": [], "Floor_Tile_Damp": [], "Floor_Tile_Wet": []}
    for x0, x1 in zip(xs, xs[1:]):
        for z0, z1 in zip(zs, zs[1:]):
            cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
            if any(w[0] < cx < w[1] and w[2] < cz < w[3] for w in WET):
                m = "Floor_Tile_Wet"
            elif (cz < -GL or cx < -GL or cz > GL) and cx < GL:
                m = "Floor_Tile_Damp"
            else:
                m = "Floor_Tile"
            cells[m].append(((x0, fl["min"][1], z0), (x1, fl["max"][1], z1)))
    for m, bx in cells.items():
        boxes_of(m, m, bx)


def build_walls():
    """Every greybox wall piece as its own box, cut at the galleries' floors into bands of their floor's wall picture."""
    for name, b in BOX.items():
        if not b["col"] or not name.startswith("Atrium_Wall_"):
            continue
        y0, y1 = b["min"][1], b["max"][1]
        cuts = [y0] + [lv for lv in LEVELS if y0 < lv < y1] + [y1]
        for ya, yb in zip(cuts, cuts[1:]):
            lv = level_of(ya)
            m = BANDS[lv]
            boxes_of(f"{name}_b{int(lv)}", m, [((b["min"][0], ya, b["min"][2]), (b["max"][0], yb, b["max"][2]))], uv_fn=lambda bm, lv=lv: wall_uv(bm, lv))


def build_galleries():
    """Each gallery's slab: its carpet on top (2 cm), the plaster soffit under it, and the fascia band on the void's edge (2 cm proud)."""
    for lv in LEVELS[1:]:
        L = int(lv)
        for side in "NSWE":
            b = BOX[f"Gallery_{L}_{side}"]
            mn, mx = b["min"], b["max"]
            boxes_of(f"Gallery_{L}_{side}_carpet", CARPET[lv], [((mn[0], mx[1] - 0.02, mn[2]), (mx[0], mx[1], mx[2]))])
            boxes_of(f"Gallery_{L}_{side}_soffit", "Ceiling_Plaster", [((mn[0], mn[1], mn[2]), (mx[0], mx[1] - 0.02, mx[2]))])
        f0, f1 = lv - G.SLAB, lv
        e = 0.02                                                           # 2 cm proud of the slab's edge, into the void; the north one parted by the shaft
        runs = [("x", -GL, -1.3, -GL, -GL + e), ("x", 1.3, GL, -GL, -GL + e), ("x", -GL, GL, GL - e, GL), ("z", -GL, GL, -GL, -GL + e), ("z", -GL, GL, GL - e, GL)]
        segs = []                                                          # in 2 m lengths with hairline gaps: each its own lightmap island
        for ax, a0, a1, c0, c1 in runs:
            n = max(1, math.ceil((a1 - a0) / 2.0))
            for i in range(n):
                s0, s1 = a0 + (a1 - a0) * i / n + (0.0005 if i else 0.0), a0 + (a1 - a0) * (i + 1) / n
                cf = c1 if c0 < 0 else c0                          # the face toward the void
                segs.append(((s0, f0, cf), (s1, f1, cf)) if ax == "x" else ((cf, f0, s0), (cf, f1, s1)))

        def fascia(bm, segs=segs):                                 # the void-side faces only (the 2 cm band's ends and top are never seen)
            for p0, p1 in segs:
                if p0[0] == p1[0]:
                    quad(bm, (p0[0], p0[1], p0[2]), (p0[0], p0[1], p1[2]), (p0[0], p1[1], p1[2]), (p0[0], p1[1], p0[2]))
                else:
                    quad(bm, (p0[0], p0[1], p0[2]), (p1[0], p0[1], p0[2]), (p1[0], p1[1], p0[2]), (p0[0], p1[1], p0[2]))
            bm.normal_update()
            for f in bm.faces:                                     # face the void's middle
                c = f.calc_center_median()
                if f.normal.dot(Vector((0, 0, c.z)) - c) < 0:
                    f.normal_flip()
        part(f"Fascia_{L}", "Fascia", fascia, recalc=False, uv_fn=lambda bm, f0=f0: fascia_uv(bm, f0))


def fascia_uv(bm, y0):
    uvl = bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y
            u = gx if abs(n.y) > abs(n.x) else gz
            lp[uvl].uv = (u / 2.0, (gy - y0) / G.SLAB)


def build_ceiling():
    """The ceiling round the skylight (over floor 3's gallery), the skylight's iron grid and glass over the void, its light well and the sky."""
    c = BOX["Atrium_Ceiling"]
    y0, y1 = c["min"][1], c["max"][1]
    x0, x1, z0, z1 = c["min"][0], c["max"][0], c["min"][2], c["max"][2]
    boxes_of("Ceiling_Ring", "Ceiling_Plaster", [((x0, y0, z0), (x1, y1, -GL)), ((x0, y0, GL), (x1, y1, z1)), ((x0, y0, -GL), (-GL, y1, GL)),
                                                  ((GL, y0, -GL), (x1, y1, GL))])
    # coffer beams under the ring, over floor 3's gallery: every 3 m, across the ring
    beams = []
    for k in range(-5, 6):
        a = k * 3.0
        beams += [((a - 0.12, y0 - 0.3, -A), (a + 0.12, y0, -GL)), ((a - 0.12, y0 - 0.3, GL), (a + 0.12, y0, A)),
                  ((-A, y0 - 0.3, a - 0.12), (-GL, y0, a + 0.12)), ((GL, y0 - 0.3, a - 0.12), (A, y0, a + 0.12))]
    boxes_of("Ceiling_Beams", "Ceiling_Plaster", beams)
    # the skylight: an iron grid of 2 m bays (T-bars), a brass rim, glass in the grid
    grid = []
    for k in range(-7, 8):
        a = k * 2.0
        grid.append(((a - 0.04, y0, -GL), (a + 0.04, y0 + 0.18, GL)))
        grid.append(((-GL, y0, a - 0.04), (GL, y0 + 0.18, a + 0.04)))
    boxes_of("Skylight_Grid", "Iron_Black", grid)
    boxes_of("Skylight_Rim", "Brass", [((-GL - 0.1, y0 - 0.12, -GL - 0.1), (GL + 0.1, y0, -GL + 0.05)), ((-GL - 0.1, y0 - 0.12, GL - 0.05), (GL + 0.1, y0, GL + 0.1)),
                                       ((-GL - 0.1, y0 - 0.12, -GL + 0.05), (-GL + 0.05, y0, GL - 0.05)), ((GL - 0.05, y0 - 0.12, -GL + 0.05), (GL + 0.1, y0, GL - 0.05))])
    part("Skylight_Glass", "Glass_Skylight", lambda bm: quad(bm, (-GL, y0 + 0.1, GL), (GL, y0 + 0.1, GL), (GL, y0 + 0.1, -GL), (-GL, y0 + 0.1, -GL)))
    # the light well above the glass (seen only through it) and the sky panel at its top
    def well(bm):                                          # four inward faces only: nothing else of it is ever seen
        for a, b in (((-GL, -GL), (GL, -GL)), ((GL, -GL), (GL, GL)), ((GL, GL), (-GL, GL)), ((-GL, GL), (-GL, -GL))):
            quad(bm, (a[0], y1, a[1]), (b[0], y1, b[1]), (b[0], SKY_Y, b[1]), (a[0], SKY_Y, a[1]))
        bm.normal_update()
        for f in bm.faces:                                 # face the well's middle
            c = f.calc_center_median()
            if f.normal.dot(Vector((0, 0, c.z)) - c) < 0:
                f.normal_flip()
    part("decor_Skylight_Well", "Ceiling_Plaster", well, recalc=False)

    def sky(bm):
        uvl = bm.loops.layers.uv.new("UVMap")
        f = quad(bm, (-GL, SKY_Y, -GL), (GL, SKY_Y, -GL), (GL, SKY_Y, GL), (-GL, SKY_Y, GL))
        for lp, st in zip(f.loops, ((0, 1), (1, 1), (1, 0), (0, 0))):
            lp[uvl].uv = st
        face_down(bm)
    part("decor_Skylight_Sky", "Skylight_Sky", sky, keep_uv=True, recalc=False)


def face_down(bm):
    bm.normal_update()
    for f in bm.faces:
        if f.normal.z > 0:
            f.normal_flip()


def build_columns():
    """The four columns in the void's corners: a marble plinth, a plaster shaft, a brass ring at every gallery and a moulded capital under the ceiling."""
    for name, b in BOX.items():
        if not name.startswith("Column"):
            continue
        mn, mx = b["min"], b["max"]
        e = 0.04
        boxes_of(f"{name}_shaft", "Column_Plaster", [(mn, mx)])
        boxes_of(f"{name}_plinth", "Marble", [((mn[0] - e, 0.0, mn[2] - e), (mx[0] + e, 0.55, mx[2] + e))])
        rings = [((mn[0] - 0.03, lv - 0.34, mn[2] - 0.03), (mx[0] + 0.03, lv - 0.30, mx[2] + 0.03)) for lv in LEVELS[1:]]
        rings += [((mn[0] - 0.03, lv + 1.0, mn[2] - 0.03), (mx[0] + 0.03, lv + 1.05, mx[2] + 0.03)) for lv in LEVELS]
        boxes_of(f"{name}_rings", "Brass", rings)
        boxes_of(f"{name}_capital", "Marble", [((mn[0] - 0.08, H - 0.35, mn[2] - 0.08), (mx[0] + 0.08, H, mx[2] + 0.08))])


def build_shaft():
    """The elevator shaft: each greybox wall box as dark green painted steel outside and a dark lining inside, brass bands at each gallery."""
    for name, b in BOX.items():
        if not name.startswith("Shaft_"):
            continue
        mn, mx = list(b["min"]), list(b["max"])
        # the inner 5 cm (toward the shaft's middle, x 0, z -12.7) is the lining
        cxs, czs = 0.0, -12.7
        inner, outer = [list(mn), list(mx)], [list(mn), list(mx)]
        dx, dz = mx[0] - mn[0], mx[2] - mn[2]
        if dx < dz:                       # a wall along z (W or E): thin across x
            if (mn[0] + mx[0]) / 2 < cxs:
                inner[0][0] = mx[0] - 0.05
                outer[1][0] = mx[0] - 0.05
            else:
                inner[1][0] = mn[0] + 0.05
                outer[0][0] = mn[0] + 0.05
        else:                             # along x (N or S): thin across z
            if (mn[2] + mx[2]) / 2 < czs:
                inner[0][2] = mx[2] - 0.05
                outer[1][2] = mx[2] - 0.05
            else:
                inner[1][2] = mn[2] + 0.05
                outer[0][2] = mn[2] + 0.05
        boxes_of(f"{name}_steel", "Shaft_Steel", [tuple(map(tuple, outer))])
        boxes_of(f"{name}_lining", "Shaft_Inner", [tuple(map(tuple, inner))])
    bands = []
    for lv in LEVELS[1:] + [H]:
        y = lv - 0.4
        bands += [((-1.33, y, SHAFT_Z0 - 0.03), (1.33, y + 0.1, SHAFT_Z0)), ((-1.33, y, -11.4), (1.33, y + 0.1, -11.37)),
                  ((-1.33, y, SHAFT_Z0), (-1.3, y + 0.1, -11.4)), ((1.3, y, SHAFT_Z0), (1.33, y + 0.1, -11.4))]
    boxes_of("Shaft_Bands", "Brass", bands)
    # the shaft's guide rails inside (seen when the doors open)
    boxes_of("Shaft_Rail_W", "Iron_Black", [((-1.1, 0.0, -12.78), (-1.06, H, -12.62))])
    boxes_of("Shaft_Rail_E", "Iron_Black", [((1.06, 0.0, -12.78), (1.1, H, -12.62))])


def build_hall():
    """The narrow hall from the lobby: beige walls, parquet, a plaster ceiling, a dado rail."""
    for name, b in BOX.items():
        if not name.startswith("Hall_") or not b["col"]:
            continue
        m = {"Hall_Floor": "Hall_Floor", "Hall_Ceiling": "Ceiling_Plaster"}.get(name, "Hall_Wall")
        boxes_of(f"{name}_art", m, [(b["min"], b["max"])])
    x0 = A + T
    boxes_of("Hall_Dado", "Wood_Dark", [((x0, 0.9, -0.8), (HALL_X1, 0.96, -0.78)), ((x0, 0.9, 0.78), (HALL_X1, 0.96, 0.8))])
    boxes_of("Hall_Skirting", "Wood_Dark", [((x0, 0.0, -0.8), (HALL_X1, 0.12, -0.785)), ((x0, 0.0, 0.785), (HALL_X1, 0.12, 0.8))])


# ---------------------------------------------------------------- the balustrades, their lamps, the ivy troughs
POST_STEP = 7.0


def rails():
    """[(name, box, axis, outward sign)] of the greybox's rail boxes: axis "x" runs along x; outward: the void's side (+1 / -1 along the thin axis)."""
    out = []
    for name, b in BOX.items():
        if not name.startswith("Rail_"):
            continue
        dx, dz = b["max"][0] - b["min"][0], b["max"][2] - b["min"][2]
        axis = "x" if dx > dz else "z"
        c = (b["min"][2] + b["max"][2]) / 2 if axis == "x" else (b["min"][0] + b["max"][0]) / 2
        out.append((name, b, axis, 1 if c < 0 else -1))
    return out


def along(b, axis):
    return (b["min"][0], b["max"][0]) if axis == "x" else (b["min"][2], b["max"][2])


def build_balustrades():
    """On every rail box: an iron base rail and square balusters every 15 cm, a brass handrail on top, iron posts every 7 m or so, each with a
    globe lamp (Lamp_Emit), and a planter trough hung on the void side with ivy trailing over the fascia (decor_: over the void)."""
    rng = np.random.default_rng(51)
    for name, b, axis, out in rails():
        y = b["min"][1]
        a0, a1 = along(b, axis)
        c0, c1 = (b["min"][2], b["max"][2]) if axis == "x" else (b["min"][0], b["max"][0])
        cm = (c0 + c1) / 2

        def P(a, yy, c):
            return (a, yy, c) if axis == "x" else (c, yy, a)

        def bx(bm, a0_, a1_, y0_, y1_, c0_, c1_):
            p, q = P(a0_, y0_, c0_), P(a1_, y1_, c1_)
            cube(bm, [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)])
        n = max(2, int(round((a1 - a0) / 0.15)))
        posts = [a0 + 0.05, a1 - 0.05] + [a for a in np.arange(a0 + POST_STEP, a1 - 2.0, POST_STEP)]

        def iron(bm):
            bx(bm, a0, a1, y, y + 0.08, cm - 0.04, cm + 0.04)
            bx(bm, a0, a1, y + 0.86, y + 0.9, cm - 0.02, cm + 0.02)
            for i in range(1, n):
                a = a0 + (a1 - a0) * i / n
                if any(abs(a - p) < 0.08 for p in posts):
                    continue
                bx(bm, a - 0.012, a + 0.012, y + 0.08, y + 0.86, cm - 0.012, cm + 0.012)
            for p in posts:
                bx(bm, p - 0.045, p + 0.045, y, y + 0.94, cm - 0.045, cm + 0.045)
        def no_ends(bm):                                   # the balusters' ends are inside the rails: never seen
            iron(bm)
            bm.normal_update()
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if abs(f.normal.z) > 0.9 and f.calc_area() < 0.001], context="FACES")
        part(f"{name}_iron", "Iron_Black", no_ends)

        def brass(bm):
            p, q = P(a0, y + 0.965, cm), P(a1, y + 0.965, cm)
            cyl(bm, p, q, 0.035, 0.035, seg=10)
        part(f"{name}_brass", "Brass", brass, smooth=True)
        lamp_posts = posts[2:] if len(posts) > 2 else []
        if (a1 - a0) > 6:
            lamp_posts = lamp_posts or [(a0 + a1) / 2]
        for k, p in enumerate(lamp_posts):
            top = P(p, y + 1.0, cm)
            part(f"decor_{name}_lampstem_{k}", "Brass", lambda bm, top=top: (cyl(bm, top, (top[0], top[1] + 0.32, top[2]), 0.018, 0.018, 8),
                                                                              cyl(bm, (top[0], top[1] + 0.3, top[2]), (top[0], top[1] + 0.36, top[2]), 0.05, 0.04, 12)))
            globe = (top[0], top[1] + 0.5, top[2])
            dead = rng.random() < 0.08
            part(f"decor_{name}_globe_{k}", "Bulb_Dead" if dead else "Lamp_Emit", lambda bm, g=globe: sphere(bm, g, 0.15, 14), smooth=True)
            if not dead:
                LIGHTS.append(("POINT", globe, 22.0, WARM, 0.12))
        # the planter trough over the void, with ivy (skip near the columns and the shaft)
        ext = []
        lo, hi = a0 + 0.9, a1 - 0.9
        if hi - lo > 1.5:
            ext.append((lo, hi))
        cv = (c1 if out > 0 else c0)
        for k, (t0, t1) in enumerate(ext):
            def trough(bm, t0=t0, t1=t1):
                bx(bm, t0, t1, y + 0.55, y + 0.82, cv, cv + out * 0.26) if out > 0 else bx(bm, t0, t1, y + 0.55, y + 0.82, cv - 0.26, cv)
            part(f"decor_{name}_trough_{k}", "Planter", trough)
            ivy(f"decor_{name}_ivy_{k}", t0, t1, y + 0.82, cv + out * 0.13, axis, out, rng)


def ivy(name, t0, t1, ytop, cmid, axis, out, rng):
    """A mound of leaves along a trough and strands trailing down over its void side (leaf cards, two-sided)."""
    bm = bmesh.new()

    def P(a, yy, c):
        return (a, yy, c) if axis == "x" else (c, yy, a)

    def leaf(p, s, tilt):
        u = (1, 0, 0) if axis == "z" else (0, 0, 1)
        r = Vector(P(s * math.cos(tilt), 0, 0)) if axis == "x" else Vector((0, 0, s * math.cos(tilt)))
        up = Vector((0, s, 0))
        c = Vector(p)
        d = Vector(P(0, 0, out * s * 0.4))
        quad(bm, tuple(c - r * 0.5), tuple(c + r * 0.5), tuple(c + r * 0.5 + up + d), tuple(c - r * 0.5 + up + d))
    a = t0
    while a < t1:
        for _ in range(2):                                   # the mound
            leaf(P(a + rng.uniform(-0.1, 0.1), ytop - 0.05 + rng.uniform(0, 0.08), cmid + rng.uniform(-0.1, 0.1)), rng.uniform(0.07, 0.11), rng.uniform(0, 3))
        if rng.random() < 0.5:                               # a strand
            ln = rng.uniform(0.8, 2.4)
            cz = cmid + out * 0.16
            for k in range(int(ln / 0.14)):
                yy = ytop - 0.2 - k * 0.14
                leaf(P(a + rng.uniform(-0.05, 0.05), yy, cz + out * (0.02 + 0.03 * math.sin(k * 0.7))), rng.uniform(0.05, 0.08), rng.uniform(0, 3))
        a += rng.uniform(0.18, 0.3)
    finish(name, bm, "Plant_Leaf", recalc=False)


# ---------------------------------------------------------------- the floor of the void: the fountain, the palms, the benches
def build_fountain():
    """A quiet fountain in the greybox's 4 m basin: marble walls and coping, still dark water, a fluted pedestal and a bowl, its water still too."""
    b = BOX["Planter"]
    x0, x1, z0, z1, y1 = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]
    w = 0.25
    boxes_of("Fountain_Basin", "Marble", [((x0, 0, z0), (x1, y1 - 0.06, z0 + w)), ((x0, 0, z1 - w), (x1, y1 - 0.06, z1)),
                                          ((x0, 0, z0 + w), (x0 + w, y1 - 0.06, z1 - w)), ((x1 - w, 0, z0 + w), (x1, y1 - 0.06, z1 - w)),
                                          ((x0 + w, 0, z0 + w), (x1 - w, 0.1, z1 - w))])
    boxes_of("Fountain_Coping", "Marble", [((x0 - 0.04, y1 - 0.06, z0 - 0.04), (x1 + 0.04, y1, z0 + w + 0.04)),
                                           ((x0 - 0.04, y1 - 0.06, z1 - w - 0.04), (x1 + 0.04, y1, z1 + 0.04)),
                                           ((x0 - 0.04, y1 - 0.06, z0 + w + 0.04), (x0 + w + 0.04, y1, z1 - w - 0.04)),
                                           ((x1 - w - 0.04, y1 - 0.06, z0 + w + 0.04), (x1 + 0.04, y1, z1 - w - 0.04))])
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    part("Fountain_Water", "Water_Still", lambda bm: quad(bm, (x0 + w, 0.46, z1 - w), (x1 - w, 0.46, z1 - w), (x1 - w, 0.46, z0 + w), (x0 + w, 0.46, z0 + w)),
         recalc=False)
    part("Fountain_Pedestal", "Marble", lambda bm: (cyl(bm, (cx, 0.1, cz), (cx, 0.5, cz), 0.42, 0.36, 20), cyl(bm, (cx, 0.5, cz), (cx, 1.05, cz), 0.2, 0.16, 16),
                                                    cyl(bm, (cx, 1.05, cz), (cx, 1.25, cz), 0.16, 0.85, 24),
                                                    cyl(bm, (cx, 1.25, cz), (cx, 1.36, cz), 0.85, 0.85, 24, cap=False),
                                                    cyl(bm, (cx, 1.25, cz), (cx, 1.36, cz), 0.79, 0.79, 24, cap=False),
                                                    cyl(bm, (cx, 1.25, cz), (cx, 1.58, cz), 0.12, 0.06, 12), sphere(bm, (cx, 1.65, cz), 0.09, 12)), smooth=True)
    part("Fountain_Bowl_Water", "Water_Still", lambda bm: cyl(bm, (cx, 1.27, cz), (cx, 1.31, cz), 0.79, 0.79, 24))
    LIGHTS.append(("POINT", (cx, 0.35, cz + 1.2), 6.0, (0.55, 0.85, 0.8), 0.2))       # a lamp under the water's surface
    LIGHTS.append(("POINT", (cx, 0.35, cz - 1.2), 6.0, (0.55, 0.85, 0.8), 0.2))


def palm(tag, cx, cz, y0, rng):
    """A kentia palm: a ringed trunk and fourteen arching fronds of leaflets (the fronds are decor_: passable, mostly overhead)."""
    ht = rng.uniform(1.5, 1.9)
    part(f"{tag}_trunk", "Palm_Trunk", lambda bm: [cyl(bm, (cx, y0 + i * ht / 6, cz), (cx, y0 + (i + 1) * ht / 6, cz), 0.1 - i * 0.008, 0.095 - i * 0.008, 10)
                                                   for i in range(6)], smooth=True)
    bm = bmesh.new()
    top = Vector((cx, y0 + ht, cz))
    for k in range(14):
        th = k / 14 * 2 * math.pi + rng.uniform(-0.2, 0.2)
        rise = rng.uniform(0.5, 1.1)
        ln = rng.uniform(1.3, 1.9)
        d = Vector((math.cos(th), 0, math.sin(th)))
        side = Vector((-math.sin(th), 0, math.cos(th)))
        pts = []
        for i in range(9):
            t = i / 8
            pts.append(top + d * (ln * t) + Vector((0, rise * math.sin(t * math.pi * 0.8) - 0.9 * t * t, 0)))
        for i in range(1, 8):
            p = pts[i]
            nxt = pts[i + 1] - pts[i - 1]
            for s in (-1, 1):
                tip = p + side * s * 0.32 * math.sin(i / 8 * math.pi) + nxt.normalized() * 0.12 + Vector((0, -0.12, 0))
                quad(bm, tuple(p - nxt * 0.08), tuple(p + nxt * 0.08), tuple(tip + nxt * 0.04), tuple(tip - nxt * 0.04))
        for i in range(8):
            a, b2 = pts[i], pts[i + 1]
            quad(bm, tuple(a - side * 0.015), tuple(a + side * 0.015), tuple(b2 + side * 0.015), tuple(b2 - side * 0.015))
    finish(f"decor_{tag}_fronds", bm, "Plant_Leaf", recalc=False)


def build_floor_furniture():
    rng = np.random.default_rng(61)
    for name, b in BOX.items():
        mn, mx = b["min"], b["max"]
        if name.startswith("Palm_Planter"):
            boxes_of(f"{name}_box", "Planter", [((mn[0], 0, mn[2]), (mx[0], mx[1] - 0.05, mx[2]))])
            e, y0, y1 = 0.02, mx[1] - 0.04, mx[1]               # a brass rim round the top, the soil inside it
            boxes_of(f"{name}_lip", "Brass", [((mn[0] - e, y0, mn[2] - e), (mx[0] + e, y1, mn[2] + 0.06)), ((mn[0] - e, y0, mx[2] - 0.06), (mx[0] + e, y1, mx[2] + e)),
                                              ((mn[0] - e, y0, mn[2] + 0.06), (mn[0] + 0.06, y1, mx[2] - 0.06)), ((mx[0] - 0.06, y0, mn[2] + 0.06), (mx[0] + e, y1, mx[2] - 0.06))])
            boxes_of(f"{name}_soil", "Soil", [((mn[0] + 0.06, mx[1] - 0.08, mn[2] + 0.06), (mx[0] - 0.06, mx[1] - 0.035, mx[2] - 0.06))])
            palm(name.replace("Planter", "Palm"), (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2, mx[1] - 0.05, rng)
        elif name.startswith("Bench_"):
            along_x = (mx[0] - mn[0]) > (mx[2] - mn[2])
            slats = []
            n = 5
            for i in range(n):
                if along_x:
                    w = (mx[2] - mn[2]) / n
                    slats.append(((mn[0], mx[1] - 0.05, mn[2] + i * w + 0.008), (mx[0], mx[1], mn[2] + (i + 1) * w - 0.008)))
                else:
                    w = (mx[0] - mn[0]) / n
                    slats.append(((mn[0] + i * w + 0.008, mx[1] - 0.05, mn[2]), (mn[0] + (i + 1) * w - 0.008, mx[1], mx[2])))
            boxes_of(f"{name}_seat", "Wood_Dark", slats)
            legs = []
            for end in (0, 1):                                      # an iron frame at each end, flush with the seat
                if along_x:
                    a = mn[0] + 0.04 if end == 0 else mx[0] - 0.04
                    legs.append(((a - 0.04, 0, mn[2]), (a + 0.04, mx[1] - 0.05, mx[2])))
                else:
                    a = mn[2] + 0.04 if end == 0 else mx[2] - 0.04
                    legs.append(((mn[0], 0, a - 0.04), (mx[0], mx[1] - 0.05, a + 0.04)))
            boxes_of(f"{name}_frame", "Iron_Black", legs)


# ---------------------------------------------------------------- doors: the leaves, their surrounds and signs; the facade doors on the galleries
def door_kind(name):
    n = name[len("DoorLeaf_"):]
    if n.startswith("pool"):
        return "pool"
    if n.startswith(("stairs", "escalators")) or n == "maze_exit":
        return "fire"
    if n == "maze":
        return "wood"
    return "panel"


LEAF_MESHES = {}
BAKE_LEAF = ("DoorLeaf_pool_02", "DoorLeaf_stairs_L4", "DoorLeaf_maze", "DoorLeaf_lobby", "DoorLeaf_maze_exit")   # one leaf of each mesh is baked


def leaf_mesh(kind, w, h, handle):
    """One leaf mesh per kind (every leaf of a kind reuses it): local x from the hinge along the leaf, y across, z up; both faces show the kind's
    picture, the edges a flat pixel; a brass knob or a push bar (none on the maze exit: it opens from the maze only)."""
    key = (kind, handle)
    if key in LEAF_MESHES:
        return LEAF_MESHES[key]
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    t = 0.025
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, 0, h / 2)) @ Matrix.Diagonal((w, 2 * t, h, 1)))
    u0, v0, u1, v1 = door_uv(kind)
    edge = EDGE_PIX["steel" if kind == "fire" else "cream"]
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
    if handle == "knob":
        for sgn in (-1, 1):
            bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=0.03, matrix=Matrix.Translation((w - 0.08, sgn * (t + 0.05), 1.0)))
            bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.01, radius2=0.01, depth=0.05,
                                  matrix=Matrix.Translation((w - 0.08, sgn * (t + 0.025), 1.0)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
    elif handle == "bar":
        for sgn in (-1, 1):
            bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.016, radius2=0.016, depth=w * 0.7,
                                  matrix=Matrix.Translation((w * 0.5, sgn * (t + 0.05), 1.0)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
            for xx in (w * 0.17, w * 0.83):
                bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.01, radius2=0.01, depth=0.05,
                                      matrix=Matrix.Translation((xx, sgn * (t + 0.025), 1.0)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
    for f in bm.faces:
        if f not in old:
            for lp in f.loops:
                lp[uvl].uv = EDGE_PIX["brass"]
    for f in bm.faces:
        f.smooth = False
    me = bpy.data.meshes.new(f"Leaf_{kind}_{handle}")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS["Doors"])
    LEAF_MESHES[key] = me
    return me


def build_door_leaves():
    """The greybox's 22 hinged doors, each its own object (the Doors collection) with its origin at the hinge and the greybox door's properties, so
    export_scene.py writes the same `doors` and the page can swing them by name. The lift doors are the kit's (DoorLeaf_lift_L*, from kit_place)."""
    for d in GB.doors:
        if d["name"].startswith("DoorLeaf_lift_"):
            continue
        p = d["props"]
        kind = door_kind(d["name"])
        handle = "none" if d["name"] == "DoorLeaf_maze_exit" else ("bar" if kind == "fire" else "knob")
        ob = bpy.data.objects.new(d["name"], leaf_mesh(kind, p["width"], p["height"], handle))
        ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
        for k, v in p.items():
            ob[k] = v
        DOORS_C.objects.link(ob)


def build_door_surrounds():
    """Casings round every door in the atrium's walls; a brass plaque over each pool door, STAIRS and ESCALATORS signs, EXIT signs over the stairs
    and the way to the lobby."""
    cas, plaques, exits = [], [], []
    for d in GB.doors:
        side, a = door_centre(d)
        if side is None:
            continue
        y0 = d["hinge"][1]
        w, h = d["props"]["width"], d["props"]["height"]
        hw = w / 2
        n = d["name"][len("DoorLeaf_"):]
        cas.append((f"{n}_L", side, a - hw - 0.1, a - hw, y0, y0 + h + 0.1))
        cas.append((f"{n}_R", side, a + hw, a + hw + 0.1, y0, y0 + h + 0.1))
        cas.append((f"{n}_H", side, a - hw - 0.1, a + hw + 0.1, y0 + h, y0 + h + 0.1))
        if n.startswith("pool_"):
            plaques.append((side, a, y0 + h + 0.32, f"POOL {int(n[5:])}", 0.6))
        elif n.startswith("stairs_"):
            plaques.append((side, a - 0.9, y0 + 1.6, "STAIRS", 0.56))
            exits.append((side, a, y0 + h + 0.26))
        elif n.startswith("escalators_"):
            plaques.append((side, a + 0.9, y0 + 1.6, "ESCALATORS", 0.6))
    # the hall's opening (no door on this side: the lobby door is at the hall's far end)
    cas += [("hall_L", "E", -0.9, -0.8, 0.0, 2.7), ("hall_R", "E", 0.8, 0.9, 0.0, 2.7), ("hall_H", "E", -0.9, 0.9, 2.6, 2.7)]
    plaques.append(("E", 0.0, 2.95, "LOBBY", 0.62))
    exits.append(("E", 0.0, 3.35))
    for nm, side, a0, a1, y0, y1 in cas:                  # one object a jamb (the layout check reads each object's box)
        m = "Trim_White" if level_of(y0) in (0.0, 12.0) else "Wood_Dark"
        part(f"Casing_{nm}", m, lambda bm, s=side, a0=a0, a1=a1, y0=y0, y1=y1: wall_box(bm, s, a0, a1, y0, y1, 0.0, 0.03))
    for k, (side, a, y, text, wd) in enumerate(plaques):        # one object a sign (the layout check reads each object's box)
        panel(f"Door_Sign_{k:02d}", "Sign_Paint", on_wall(side, a, y, 0.006), WALLS[side][0], wd, wd / 4, sign_cell_uv(text))
    bm = bmesh.new()
    for side, a, y in exits:
        panel(None, "Emergency_Emit", on_wall(side, a, y, 0.062), WALLS[side][0], 0.42, 0.14, (0, 0, 1, 1), bm=bm)
    finish("Exit_Faces", bm, "Emergency_Emit", keep_uv=True, recalc=False)
    part("Exit_Boxes", "Iron_Black", lambda bm: [wall_box(bm, s, a - 0.23, a + 0.23, y - 0.09, y + 0.09, 0.0, 0.06) for s, a, y in exits])
    for side, a, y in exits:
        LIGHTS.append(("POINT", on_wall(side, a, y - 0.15, 0.25), 1.5, (0.3, 1.0, 0.45), 0.1))


FACADE = {4.0: ("motel", "Wood_Dark", lambda i: f"{101 + i}"), 8.0: ("green", "Wood_Dark", lambda i: f"{201 + i}"),
          12.0: ("apart", "Trim_White", lambda i: f"3{'ABCDEFGH'[i]}")}


def facade_slots():
    """Where the upper galleries' facade doors stand: on the north and west walls, where the pool doors are below."""
    out = []
    for d in pool_doors():
        side, a = door_centre(d)
        if side in ("N", "W"):
            out.append((side, a))
    return sorted(out)


def build_facades():
    """The upper galleries' room doors, which do not open: a flush leaf (2 cm proud), its casing and a brass number."""
    for lv, (kind, trim, num) in FACADE.items():
        bm = bmesh.new()
        uvl = bm.loops.layers.uv.new("UVMap")
        cas = []
        nums = []
        for i, (side, a) in enumerate(facade_slots()):
            w, h = G.DOOR_W, G.DOOR_H
            old = set(bm.faces)
            wall_box(bm, side, a - w / 2, a + w / 2, lv, lv + h, 0.0, 0.02)
            u0, v0, u1, v1 = door_uv(kind)
            nrm = Vector(NORMAL[WALLS[side][0]])
            r = Vector(RIGHT[WALLS[side][0]])
            for f in bm.faces:
                if f in old:
                    continue
                f.normal_update()
                g = Vector((f.normal.x, f.normal.z, -f.normal.y))
                for lp in f.loops:
                    p = lp.vert.co
                    gp = Vector((p.x, p.z, -p.y))
                    if g.dot(nrm) > 0.9:
                        s = (gp.dot(r) - (Vector(on_wall(side, a, 0, 0)).dot(r) - w / 2)) / w
                        lp[uvl].uv = (u0 + (u1 - u0) * s, v0 + (v1 - v0) * (gp.y - lv) / h)
                    else:
                        lp[uvl].uv = EDGE_PIX["cream"]
            cas += [(side, a - w / 2 - 0.1, a - w / 2, lv, lv + h + 0.1), (side, a + w / 2, a + w / 2 + 0.1, lv, lv + h + 0.1),
                    (side, a - w / 2 - 0.1, a + w / 2 + 0.1, lv + h, lv + h + 0.1)]
            nums.append((side, a, lv + 1.62, num(i)))
            DECOR_KNOBS.append(on_wall(side, a + w / 2 - 0.09, lv + 1.0, 0.05))
        finish(f"Facade_Doors_{int(lv)}", bm, "Doors", keep_uv=True, recalc=False)
        part(f"Facade_Casings_{int(lv)}", trim, lambda bm, cs=cas: [wall_box(bm, s, a0, a1, y0, y1, 0.0, 0.035) for s, a0, a1, y0, y1 in cs])
        bm = bmesh.new()
        for side, a, y, text in nums:
            panel(None, "Sign_Paint", on_wall(side, a, y, 0.024), WALLS[side][0], 0.2, 0.05, sign_cell_uv(text), bm=bm)
        finish(f"Facade_Numbers_{int(lv)}", bm, "Sign_Paint", keep_uv=True, recalc=False)
    part("Facade_Knobs", "Brass", lambda bm: [sphere(bm, k, 0.028, 8) for k in DECOR_KNOBS], smooth=True)


DECOR_KNOBS = []


def build_fascia_signs():
    """FLOOR 1, FLOOR 2, FLOOR 3 on each gallery's fascia, on all four sides, facing the void (the north one beside the shaft)."""
    bm = bmesh.new()
    for lv in LEVELS[1:]:
        text = {4.0: "FLOOR 1", 8.0: "FLOOR 2", 12.0: "FLOOR 3"}[lv]
        y = lv - G.SLAB / 2
        f = GL - 0.025
        for c, nrm in (((5.0, y, -f), "+z"), ((0.0, y, f), "-z"), ((-f, y, 0.0), "+x"), ((f, y, 0.0), "-x")):
            panel(None, "Sign_Paint", c, nrm, 0.9, 0.225, sign_cell_uv(text), bm=bm)
    finish("Fascia_Signs", bm, "Sign_Paint", keep_uv=True, recalc=False)


# ---------------------------------------------------------------- lamps: sconces on every gallery's walls; hanging baskets from the skylight
WARM = (1.0, 0.70, 0.42)
LIGHTS = []
SCONCE_AS = (-15.0, -9.0, -3.0, 3.0, 9.0, 15.0)
DEAD = {(4.0, "W", -3.0), (8.0, "N", 9.0), (12.0, "E", -9.0), (0.0, "S", 15.0)}


def build_sconces():
    """Tulip sconces on brass backplates, 2.1 m above each gallery's floor, every 6 m along every wall (Lamp_Emit); four are dead."""
    plates, arms, shades, dead = bmesh.new(), bmesh.new(), bmesh.new(), bmesh.new()
    for lv in LEVELS:
        for side in "NSWE":
            for a in SCONCE_AS:
                if side == "E" and lv == 0.0 and abs(a) < 4:
                    continue
                y = lv + 2.1
                wall_box(plates, side, a - 0.07, a + 0.07, y - 0.12, y + 0.12, 0.0, 0.02)
                p0, p1 = on_wall(side, a, y, 0.02), on_wall(side, a, y + 0.06, 0.2)
                cyl(arms, p0, p1, 0.012, 0.012, 8)
                c = on_wall(side, a, y + 0.1, 0.22)
                tgt = dead if (lv, side, a) in DEAD else shades
                cyl(tgt, (c[0], c[1] - 0.02, c[2]), (c[0], c[1] + 0.16, c[2]), 0.035, 0.09, 14, cap=False)
                cyl(tgt, (c[0], c[1] - 0.03, c[2]), (c[0], c[1] - 0.02, c[2]), 0.035, 0.035, 14)
                if tgt is shades:
                    LIGHTS.append(("POINT", (c[0], c[1] + 0.06, c[2]), 38.0, WARM, 0.06))
    finish("Sconce_Plates", plates, "Brass")
    finish("Sconce_Arms", arms, "Brass", smooth=True)
    finish("Sconce_Shades", shades, "Lamp_Emit", smooth=True)
    finish("Sconce_Dead", dead, "Bulb_Dead", smooth=True)


BASKETS = [(-8.0, 9.6, -8.0), (8.0, 10.4, -8.0), (-8.0, 10.8, 8.0), (8.0, 9.2, 8.0), (0.0, 11.4, -8.0), (0.0, 9.8, 8.0), (-8.0, 10.0, 0.0), (8.0, 11.0, 0.0)]


def build_baskets():
    """Hanging baskets on chains from the skylight's grid, over the void (decor_: out of reach), each a mound of leaves with trailing strands."""
    rng = np.random.default_rng(71)
    chains, bowls = bmesh.new(), bmesh.new()
    for (x, y, z) in BASKETS:
        top = H
        for k in range(3):
            th = k / 3 * 2 * math.pi
            cyl(chains, (x, top, z), (x + 0.3 * math.cos(th), y + 0.3, z + 0.3 * math.sin(th)), 0.006, 0.006, 4, cap=False)
        bmesh.ops.create_uvsphere(bowls, u_segments=14, v_segments=6, radius=0.34, matrix=Matrix.Translation(B((x, y + 0.3, z))) @ Matrix.Diagonal((1, 1, 0.75, 1)))
    finish("decor_Basket_Chains", chains, "Iron_Black")
    finish("decor_Basket_Bowls", bowls, "Planter", smooth=True)
    bm = bmesh.new()
    for (x, y, z) in BASKETS:
        for _ in range(40):
            th, r = rng.uniform(0, 2 * math.pi), rng.uniform(0, 0.36)
            p = Vector((x + r * math.cos(th), y + 0.34 + rng.uniform(0, 0.18), z + r * math.sin(th)))
            s = rng.uniform(0.08, 0.13)
            d = Vector((math.cos(th), 0.5, math.sin(th))).normalized()
            sd = Vector((-math.sin(th), 0, math.cos(th)))
            quad(bm, tuple(p - sd * s / 2), tuple(p + sd * s / 2), tuple(p + sd * s / 2 + d * s), tuple(p - sd * s / 2 + d * s))
        for k in range(10):
            th = k / 10 * 2 * math.pi + rng.uniform(-0.2, 0.2)
            ln = rng.uniform(0.8, 2.0)
            for i in range(int(ln / 0.12)):
                p = Vector((x + 0.34 * math.cos(th), y + 0.25 - i * 0.12, z + 0.34 * math.sin(th)))
                s = rng.uniform(0.05, 0.08)
                sd = Vector((-math.sin(th), 0, math.cos(th)))
                quad(bm, tuple(p - sd * s / 2), tuple(p + sd * s / 2), tuple(p + sd * s / 2 + Vector((0, -s, 0))), tuple(p - sd * s / 2 + Vector((0, -s, 0))))
    finish("decor_Basket_Leaves", bm, "Plant_Leaf", recalc=False)


def build_hall_lamp():
    c = ((A + T + HALL_X1) / 2, 2.8, 0.0)
    part("Hall_Lamp_Rose", "Brass", lambda bm: cyl(bm, (c[0], 2.74, 0), (c[0], 2.8, 0), 0.08, 0.08, 12))
    part("Hall_Lamp_Bowl", "Lamp_Emit", lambda bm: sphere(bm, (c[0], 2.62, 0), 0.16, 14, squash=0.5), smooth=True)
    LIGHTS.append(("POINT", (c[0], 2.5, 0.0), 30.0, WARM, 0.1))


# ---------------------------------------------------------------- the layout objects and the kit
def build_layout():
    """The layout objects, as the greybox names them: COL_ boxes (hidden) and the empties (Link_, Arrive_, Marker_, Spot_). The kit's colliders,
    lift door records and call-button spots come from kit_place (place_kit), so they are left out here."""
    kit_names = {b["name"] for b in GB.boxes if b["name"].startswith(("Car_", "Landing_"))}
    for b in GB.boxes:
        if not b["col"] or b["name"] in kit_names:
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
        if e["name"].startswith("Spot_"):
            continue                                   # the only spots are the kit's
        ob = bpy.data.objects.new(e["name"], None)
        ob.location = B(e["pos"])
        if e["face"]:
            ob.rotation_euler = (0, 0, math.atan2(e["face"][0], e["face"][1]))
        for k, v in e["props"].items():
            ob[k] = v
        ob.empty_display_size = 0.3
        LAYOUT_C.objects.link(ob)


CAR_PREFIX = ("Car_", "decor_Car_", "COL_Car_", "Spot_panel_")
KIT_DROP = ("Link_", "Arrive_", "Marker_")


def place_kit():
    """The kit elevator at the four stops (blender/kit/README.md): its layout (the landing's colliders, the lift door record, the call spot; the
    car's colliders and panel spot at the ground stop only, where the car is parked) into Layout; its art into Kit, as stand-ins (the car once)."""
    import kit_place
    stops = {lv: d for lv, d in zip(LEVELS, sorted((d for d in GB.doors if d["name"].startswith("DoorLeaf_lift_")), key=lambda d: d["hinge"][1]))}
    for lv, at in zip(LEVELS, KIT_AT):
        suffix = f"L{int(lv)}"
        made = kit_place.place("elevator", suffix=suffix, at=at, yaw_deg=180.0, art=True, collection=KIT_C)
        for nm in made:
            ob = bpy.data.objects[nm]
            base = nm[:-len(suffix) - 1]
            if nm.startswith(KIT_DROP) or (lv and nm.startswith(CAR_PREFIX)):
                bpy.data.objects.remove(ob)
                continue
            if nm.startswith(("COL_", "DoorLeaf_", "Spot_")):
                KIT_C.objects.unlink(ob)
                LAYOUT_C.objects.link(ob)
                if nm.startswith("DoorLeaf_"):
                    for k, v in stops[lv]["props"].items():          # the greybox's own properties of the stop (its `stop`)
                        if k not in ob.keys():
                            ob[k] = v
            del base


# ---------------------------------------------------------------- lights, world
def add_lights():
    c = bpy.data.collections.new("Lights")
    bpy.context.scene.collection.children.link(c)
    for i, (kind, pos, w, col, r) in enumerate(LIGHTS):
        d = bpy.data.lights.new(f"Lamp_{i:03d}", kind)
        d.energy, d.color = w, col
        d.shadow_soft_size = r
        ob = bpy.data.objects.new(f"Lamp_{i:03d}", d)
        ob.location = B(pos)
        c.objects.link(ob)


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("Night")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.02, 0.02, 0.035, 1)
    bg.inputs["Strength"].default_value = 0.2


def set_emit(mname, strength):
    m = bpy.data.materials.get(mname)
    if m:
        m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = strength


def apply_light_set(name):
    """bake / render: the sky panel lights the atrium (SKY_BAKE); export: every emitter at the strength the page shows."""
    set_emit("Lamp_Emit", LAMP_EMIT)
    set_emit("Emergency_Emit", EXIT_EMIT)
    set_emit("Skylight_Sky", SKY_SHOW if name == "export" else SKY_BAKE)


def ensure_marker():
    st = KIT_C or bpy.data.collections["Kit"]
    ob = bpy.data.objects.get("standin_arrival_marker")
    if ob is None:
        me = bpy.data.meshes.new("standin_arrival_marker")
        bm = bmesh.new()
        a = SPAWN
        cube(bm, (a[0] - 0.1, a[1], a[2] - 0.1), (a[0] + 0.1, a[1] + 0.2, a[2] + 0.1))
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("standin_arrival_marker", me)
        bpy.data.collections["Layout"].objects.link(ob)
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
    global ART, KIT_C, DOORS_C, LAYOUT_C
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.lights, bpy.data.cameras):
        for d in list(coll):
            coll.remove(d)
    for lst in (IMG_CACHE, MATS, TILES):
        lst.clear()
    LIGHTS.clear()
    WET.clear()
    DECOR_KNOBS.clear()
    LEAF_MESHES.clear()
    sc = bpy.context.scene
    ART, KIT_C, DOORS_C, LAYOUT_C = (bpy.data.collections.new(n) for n in ("Art", "Kit", "Doors", "Layout"))
    for c in (ART, KIT_C, DOORS_C, LAYOUT_C):
        sc.collection.children.link(c)
    make_materials(make_generated())
    build_floor()
    build_walls()
    build_galleries()
    build_ceiling()
    build_columns()
    build_shaft()
    build_hall()
    build_balustrades()
    build_fountain()
    build_floor_furniture()
    build_door_leaves()
    build_door_surrounds()
    build_facades()
    build_fascia_signs()
    build_sconces()
    build_baskets()
    build_hall_lamp()
    build_layout()
    place_kit()
    add_lights()
    setup_world()
    apply_light_set("bake")
    ensure_marker()
    LAYOUT_C.hide_render = True
    tris = sum(len(p.vertices) - 2 for o in ART.objects for p in o.data.polygons)
    print(f"ART {len(ART.objects)} objects, about {tris} triangles; {len(LIGHTS)} lamps; kit stand-ins {len(KIT_C.objects)}")


# ---------------------------------------------------------------- layout file and the layout check
def stage_layout():
    import export_scene
    export_scene.write(SCENE, ROOT / f"world/{SCENE}.json")


def kit_parts():
    """The kit's stand-ins as the kit's own check reads them (tools/blender/build_kit.py component_parts): one box per connected piece of each mesh,
    since a kit mesh holds several separate boxes (the car's walls) whose whole box would cover the floor between them. The leaves are left out."""
    out = []
    for ob in bpy.data.collections["Kit"].all_objects:
        if ob.type != "MESH" or ob.hide_render or ob.name.startswith("LiftLeaf_"):
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
            out.append({"name": f"{ob.name}#{k}", "min": [min(q[i] for q in g) for i in range(3)], "max": [max(q[i] for q in g) for i in range(3)]})
        bm.free()
    return out


def stage_check():
    """tools/blender/check_layout.py's rules on the Art collection and the kit's stand-ins together (the kit's colliders are covered by its own art);
    the kit's sliding leaves (LiftLeaf_*) are doors, as the greybox's leaves are (the Doors collection), so they are left out."""
    import check_layout
    world = json.loads((ROOT / f"world/{SCENE}.json").read_text())
    parts = check_layout.blender_parts("Art") + kit_parts()
    print(f"layout check: scene {SCENE}, {len(parts)} visible meshes (Art and the kit's stand-ins), {len(world['colliders'])} colliders")
    bad = check_layout.report(check_layout.check(parts, world, {}))
    print("CHECK_LAYOUT exit", 1 if bad else 0)


# ---------------------------------------------------------------- bake
PAGES = [2048, 2048, 2048, 2048]
UV_SCALE = {"Iron_Black": 0.3, "Brass": 0.35, "Plant_Leaf": 0.2, "Planter": 0.5, "Sign_Paint": 0.5, "Doors": 0.6, "Palm_Trunk": 0.4, "Soil": 0.4,
            "Bulb_Dead": 0.3, "Water_Still": 0.5, "Wood_Dark": 0.6, "Trim_White": 0.6, "Shaft_Inner": 0.4, "Marble": 0.8}
WHITE_CAP = 8.0
TWO_SIDED = ("Plant_Leaf",)
SHELL_BOXES = None


def shell_boxes():
    global SHELL_BOXES
    if SHELL_BOXES is None:
        SHELL_BOXES = [b for b in GB.boxes if b["col"] and b["name"].startswith(("Atrium_", "Gallery_", "Shaft_", "Hall_", "Column"))]   # the structure only
    return SHELL_BOXES


def hidden_points(P):
    """For game points P (n, 3): inside a collider (pressed against a wall, a slab, the next box) or outside the building's shell."""
    bxs = shell_boxes()
    e = 1e-3
    mn = np.array([b["min"] for b in bxs]) + e
    mx = np.array([b["max"] for b in bxs]) - e
    buried = np.concatenate([((Q[:, None, :] > mn[None]) & (Q[:, None, :] < mx[None])).all(-1).any(-1) for Q in np.array_split(P, max(1, len(P) // 20000))])
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    atrium = (np.abs(x) <= A + T + e) & (np.abs(z) <= A + T + e) & (y >= -G.SLAB - e) & (y <= H + 0.2 + e)
    hall = (x >= A - e) & (x <= HALL_X1 + T + e) & (np.abs(z) <= 1.0 + e) & (y >= -G.SLAB - e) & (y <= 3.0 + e)
    return buried | ~(atrium | hall)


def cull(bm, mname, oname):
    """Drop faces never seen: a face whose points 1 cm in front of it (its middle and its corners, pulled 5% in) are all hidden: inside a collider,
    or outside the shell (the walls' backs, the slabs' undersides, the ceiling's top). Plants and the skylight keep every face."""
    if mname in TWO_SIDED or oname.startswith(("decor_Skylight", "Skylight_")):      # the skylight sits in the ceiling's slab: all of it is seen
        return
    faces = list(bm.faces)
    if not faces:
        return
    pts = []
    for f in faces:
        c, n = f.calc_center_median(), f.normal
        ps = [c] + [c + (v.co - c) * 0.95 for v in f.verts[:4]]
        ps += [ps[-1]] * (5 - len(ps))
        pts += [(p.x + n.x * 0.01, p.z + n.z * 0.01, -p.y - n.y * 0.01) for p in ps]
    hid = hidden_points(np.array(pts)).reshape(len(faces), 5).all(axis=1)
    bmesh.ops.delete(bm, geom=[f for f, h in zip(faces, hid) if h], context="FACES")


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
        # no welding: each piece stays its own lightmap island (welded, the four sides of a ring become one hollow island the packer boxes whole)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_area() < 1e-7], context="FACES")      # no zero-area faces in the lightmap
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        if not bm.faces:
            bm.free()
            continue
        me = bpy.data.meshes.new(mname)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(bpy.data.materials[mname])
        ob = bpy.data.objects.new(mname, me)
        exp.objects.link(ob)
        if mname in EMITS:
            ob.visible_shadow = False
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
    """One atlas for `objs`: smart-project islands at equal texel density (the small detailed materials scaled down), packed with MARGIN_PX."""
    for o in objs:
        uvs = o.data.uv_layers
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.new(name="lightmap", do_init=False)
        uvs.active = uvs["lightmap"]
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        d = o.data.uv_layers["lightmap"].data
        us = np.array([x.uv for x in d]).reshape(-1, 2)
        bad = ~np.isfinite(us).all(axis=1)
        ok = us[~bad]
        print(f"  uv {o.name}: {len(us)} loops, {int(bad.sum())} not finite, bounds {np.round(ok.min(axis=0), 3) if len(ok) else '-'} "
              f"{np.round(ok.max(axis=0), 3) if len(ok) else '-'}")
        us[bad] = 0.0
        us *= UV_SCALE.get(mat_of(o), 1.0)
        d.foreach_set("uv", us.ravel())
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / page, shape_method="AABB")
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        us = np.array([x.uv for x in o.data.uv_layers["lightmap"].data]).reshape(-1, 2)
        print(f"  packed {o.name}: {np.round(us.min(axis=0), 3)} {np.round(us.max(axis=0), 3)}, uv area {uv_area(o, 'lightmap'):.4f}")
    plain = [o for o in objs if mat_of(o) not in UV_SCALE]
    a3 = sum(area3d(o) for o in plain)
    au = sum(uv_area(o, "lightmap") for o in plain)
    dens = page * math.sqrt(au / max(a3, 1e-9))
    print(f"  page {page}: {sum(area3d(o) for o in objs):.0f} m2, {dens:.1f} px/m on the plain surfaces")
    return page, dens


def mat_of(o):
    return o.data.materials[0].name


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


def grid_uv(objs, S):
    """The cell page: every face of `objs` its own square cell (the leaves, the iron, the dead bulbs: tens of thousands of tiny islands that the packer
    cannot place), the face mapped by its own plane into the cell, a pixel in from the cell's edge."""
    nf = sum(len(o.data.polygons) for o in objs)
    n = math.ceil(math.sqrt(nf))
    c = S // n
    i = 0
    for o in objs:
        uvs = o.data.uv_layers
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        lay = uvs.new(name="lightmap", do_init=False)
        uvs.active = lay
        vs = o.data.vertices
        for p in o.data.polygons:
            pts = [Vector(vs[v].co) for v in p.vertices]
            e0 = (pts[1] - pts[0]).normalized() if (pts[1] - pts[0]).length > 1e-9 else Vector((1, 0, 0))
            e1 = p.normal.cross(e0).normalized()
            q = [((x - pts[0]).dot(e0), (x - pts[0]).dot(e1)) for x in pts]
            u0, u1 = min(a for a, _ in q), max(a for a, _ in q)
            v0, v1 = min(b for _, b in q), max(b for _, b in q)
            cx, cy = (i % n) * c, (i // n) * c
            for li, (a, b) in zip(p.loop_indices, q):
                lay.data[li].uv = ((cx + 1 + (c - 2) * (a - u0) / max(u1 - u0, 1e-9)) / S, (cy + 1 + (c - 2) * (b - v0) / max(v1 - v0, 1e-9)) / S)
            i += 1
    print(f"  cell page {S}: {nf} faces, cells of {c} px")
    return S, float(c)


def bake_page(n, objs, bake_objs, S, samples, margin=MARGIN_PX, cell=0):
    apply_light_set("bake")
    bpy.context.scene.cycles.samples = samples
    img = bpy.data.images.new(f"LM_{n}", S, S, alpha=False, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
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
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=margin, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
    for o in bake_objs:
        for slot in o.material_slots:
            nt = slot.material.node_tree
            for nd in [nd for nd in nt.nodes if nd.name.startswith("BAKE_TARGET")]:
                nt.nodes.remove(nd)
    if cell:                                            # the cell page: each cell filled with its mean (no denoiser smearing across cells)
        a = np.empty(S * S * 4, np.float32)
        img.pixels.foreach_get(a)
        a = a.reshape(S, S, 4)[..., :3]
        m = (S // cell) * cell
        blk = a[:m, :m].reshape(S // cell, cell, S // cell, cell, 3)
        mean = blk[:, 1:-1, :, 1:-1].mean(axis=(1, 3))
        out = np.zeros((S, S, 3), np.float32)
        out[:m, :m] = np.repeat(np.repeat(mean, cell, axis=0), cell, axis=1)
        bpy.data.images.remove(img)
        return out
    a = denoise_image(img, S)
    bpy.data.images.remove(img)
    return a[..., :3].copy()


def page_groups(exp):
    """The baked materials on the four pages: largest first, each onto the page with the least area so far (the leaves' material, Doors, stays one)."""
    mats = sorted((m for m in exp if m not in UNBAKED and m not in GRID), key=lambda m: -area3d(exp[m]) * UV_SCALE.get(m, 1.0) ** 2)
    k = len(PAGES) - 1                                   # the last page is the cell page
    load = [0.0] * k
    groups = [[] for _ in range(k)]
    for m in mats:
        i = min(range(k), key=lambda j: load[j])
        groups[i].append(m)
        load[i] += area3d(exp[m]) * UV_SCALE.get(m, 1.0) ** 2
    return groups + [[m for m in GRID if m in exp]]


GRID = ("Plant_Leaf", "Iron_Black", "Bulb_Dead", "Brass", "Fascia", "Sign_Paint", "Palm_Trunk")   # one cell a face: many tiny or long thin pieces


def stage_bake():
    import time
    work = stage_work()
    exp = make_export_objects()
    leaves = sorted(bpy.data.collections["Doors"].objects, key=lambda o: o.name)
    reps = [o for o in leaves if o.name in BAKE_LEAF]
    assert len({o.data.name for o in reps}) == len({o.data.name for o in leaves}) == len(reps), "every leaf mesh needs one baked leaf"
    bpy.data.collections["Art"].hide_render = True
    bpy.data.collections["Art"].hide_viewport = True
    setup_cycles(SAMPLES, bake=True)
    if "Glass_Skylight" in exp:
        exp["Glass_Skylight"].hide_render = True
    report = {}
    for n, mats in enumerate(page_groups(exp)):
        objs = [exp[m] for m in mats] + (reps if "Doors" in mats else [])
        print(f"lightmap {n}: {mats}")
        cells = all(m in GRID for m in mats)
        S, dens = grid_uv(objs, PAGES[n]) if cells else lightmap_uv(objs, PAGES[n])
        t0 = time.time()
        rgb = bake_page(n, objs, objs, S, SAMPLES, margin=1 if cells else MARGIN_PX, cell=int(dens) if cells else 0)
        np.save(work / f"{SCENE}_{n}_raw.npy", rgb.astype(np.float16))
        report[n] = {"size": S, "px_per_m": round(dens, 1), "samples": SAMPLES, "device": bpy.context.scene.cycles.device, "seconds": round(time.time() - t0),
                     "materials": mats + ([o.name for o in leaves] if "Doors" in mats else [])}
        print("  baked", n, report[n]["seconds"], "s")
    (work / "lightmaps.json").write_text(json.dumps(report, indent=1))
    tone(work)
    if "Glass_Skylight" in exp:
        exp["Glass_Skylight"].hide_render = False
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Art"].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


# ---------------------------------------------------------------- brightness: how the page shows the maps
# The page draws a baked material unlit, with no tone mapping: texture x base colour x texel x intensity / pi. The bake's light L is written with
# a shoulder: texel = G L / (C + G L), and intensity = pi C, so the page shows texture x G L where the light is ordinary and rolls off toward
# texture x C under a lamp, never clipping. G lifts the whole set; CAP scales a single material's intensity (below 1 to calm a bright one,
# above 1 to lift a dark one).
CURVE = (8.0, 1.15)
CAP = {"Wall_Green": 1.4, "Carpet_Green": 1.5, "Hall_Wall": 1.6}     # (over 1: a lift) the dark green paper and carpet, the narrow hall's walls


def tone(work):
    """The lightmap PNGs from the bake's raw light (<work>/atrium_<n>_raw.npy), by CURVE. Runs in Blender at the end of the bake, or alone
    (python tools/blender/build_atrium.py --tone) to re-tone without baking again."""
    rep = json.loads((work / "lightmaps.json").read_text())
    G_, C_ = CURVE
    for n in rep:
        raw = np.load(work / f"{SCENE}_{n}_raw.npy").astype(np.float32)          # rows bottom to top, as Blender's pixels
        tex = G_ * raw / (C_ + G_ * np.maximum(raw, 0))
        enc = srgb_encode(tex)
        path = work / f"{SCENE}_{n}.png"
        if bpy is None:
            from PIL import Image
            Image.fromarray(np.flipud((enc * 255 + 0.5).astype(np.uint8))).save(path)
        else:
            S = enc.shape[0]
            out = np.ones((S, S, 4), np.float32)
            out[..., :3] = enc
            png = bpy.data.images.new(f"LM_{n}_png", S, S, alpha=False)
            png.colorspace_settings.name = "Non-Color"
            png.pixels.foreach_set(out.ravel())
            png.filepath_raw = str(path)
            png.file_format = "PNG"
            png.save()
            bpy.data.images.remove(png)
        peak = raw.max(axis=2)
        sel = peak > 1e-5
        rep[n]["curve_G_C"] = [G_, C_]
        rep[n]["raw_p50_p90_p99_max"] = [round(float(v), 4) for v in np.percentile(peak[sel], [50, 90, 99, 100])] if sel.any() else []
        print("TONE", n, rep[n]["raw_p50_p90_p99_max"])
    (work / "lightmaps.json").write_text(json.dumps(rep, indent=1))


def set_intensities():
    rep = json.loads((stage_work() / "lightmaps.json").read_text())
    C_ = CURVE[1]
    for idx, r in rep.items():
        for nm in r["materials"]:
            m = bpy.data.materials.get(nm)
            if m is None:
                ob = bpy.data.objects.get(nm)
                if ob is None or not ob.material_slots:
                    continue
                m = ob.material_slots[0].material
            m["lightmap"] = LM_URL.format(idx)
            m["lightmap_intensity"] = round(math.pi * C_ * CAP.get(m.name, 1.0), 4)


def scrub_ui_paths():
    for sc in bpy.data.screens:
        for a in sc.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"_" * 1000
                    sp.params.directory = b"//"


KEEP_PROPS = {"lightmap", "lightmap_intensity"}
LAYOUT_PREFIX = ("DoorLeaf_", "Spot_", "Marker_", "Link_", "Arrive_")
SYS_KEEP = ("cycles", "eevee")


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
        if im.packed_file or im.source != "FILE" or not im.filepath:
            continue
        p = Path(bpy.path.abspath(im.filepath))
        try:
            rel = "//" + os.path.relpath(p, base).replace("\\", "/")
        except ValueError:
            rel = "//" + p.name
        set_path(im, "filepath", rel)
    for lib in list(bpy.data.libraries):
        bpy.data.libraries.remove(lib)
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
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    scrub_private()
    bpy.ops.wm.save_mainfile()


# ---------------------------------------------------------------- export
def stage_export():
    set_intensities()
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    bpy.data.collections["Art"].hide_viewport = True
    bpy.data.collections["Kit"].hide_viewport = True
    leaves = sorted(bpy.data.collections["Doors"].objects, key=lambda o: o.name)
    stash = {o.name: {k: o[k] for k in o.keys()} for o in leaves}        # the leaves' layout properties are in world/atrium.json, not in the GLB
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
    apply_light_set("bake")
    bpy.data.collections["Art"].hide_viewport = False
    bpy.data.collections["Kit"].hide_viewport = False
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
    apply_light_set("bake")
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
    expo = arg("--exposure", 0.5, float)
    which = arg("--only", "all")
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    a, f = SPAWN, ARRIVE_LOBBY["face"]
    shots = {
        "1_arrival": look_cam("arrival", (a[0], 1.6, a[2]), (a[0] + f[0] * 3, 1.6, a[2] + f[1] * 3), 70.0),
        "2_wide": look_cam("wide", (5.0, 13.6, 15.0), (-2.5, 1.0, -6.0), 82.0),
        "3_detail": look_cam("detail", (9.5, 5.55, -15.6), (-3.0, 5.2, -16.4), 62.0),
        "4_floor": look_cam("floor", (7.5, 1.6, 9.5), (0.0, 3.2, -13.0), 75.0),
        "5_up": look_cam("up", (-10.5, 1.5, 10.5), (2.0, 13.0, -2.0), 85.0),
    }
    todo = [(k, v, (1920, 1080)) for k, v in shots.items()]
    for key, cam, (w, h) in todo:
        if which not in ("all", key) and not (which == "review" and key in ("1_arrival", "2_wide", "3_detail")):
            continue
        sc.camera = cam
        sc.view_settings.exposure = expo
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


if __name__ == "__main__":
    if bpy is None:
        if "--tone" in sys.argv:
            tone(Path(arg("--work", str(ROOT / f"work/{SCENE}"))))
        else:
            print(__doc__)
        sys.exit(0)
    ST = set(STAGE.split(","))
    if ST & {"art", "all"}:
        build_all()
        save_blend()
    if ST & {"layout", "art", "all"}:
        stage_layout()
    if ST & {"check", "art", "all"}:
        KIT_C = bpy.data.collections.get("Kit")
        stage_check()
    if ST & {"bake", "all"}:
        stage_bake()
    if ST & {"export", "all"}:
        stage_export()
    if ST & {"axes", "all"}:
        stage_axes()
    if ST & {"render", "all"}:
        stage_render()
