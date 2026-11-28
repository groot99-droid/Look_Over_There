"""Dresses the Overworld's playground and market (docs/BLENDER_AREAS.md section 4: `playground`, `market`), bakes their ambient occlusion and
exports world/<scene>.glb and world/<scene>.json.

Re-runnable, from the repo root. `--scene` takes playground, market or both (playground,market).

    python tools/blender/build_overworld_play.py --stage textures      (the generated textures -> blender/textures/overworld_play/, no Blender)
    blender -b --factory-startup --python tools/blender/build_overworld_play.py -- --scene playground --stage art,bake,export,render [--samples 128]
        art:    the art, the moving parts and the layout objects; saves blender/scenes/<scene>.blend, writes world/<scene>.json, runs the layout check
        bake:   the ambient occlusion, two maps a scene (the ground, and everything standing), into <work>/<scene>_<n>.png
        export: <work>/<scene>_raw.glb (the static art merged by material, and the moving parts as their own nodes)
        render: docs/renders/<scene>/1_arrival.jpg, 2_wide.jpg, 3_detail.jpg and <work>/4_plan.jpg
    python tools/blender/pack_scene.py <scene> --work work/<scene>      (WebP AO maps and textures -> world/)

The layout is the greybox's: tools/blender/build_overworld_greybox.py (`playground()`, `market()`, imported here), so no coordinate of the layout is
typed in here: every collider, link, zone and spot comes from it, and export_scene.py writes the same world/<scene>.json as the greybox. Each
collider's art is built inside its own box (a post becomes a round post, a bench gets slats, a fence run gets pickets, a shelf gets boards), so
the layout check's cover and stray rules hold; what is added on top and can be walked through is decor_.

The moving parts stay the greybox's Play_<equipment>_<part> objects, each its own node with its origin on its pivot and its custom properties
(equipment, part, axis, motion, range_deg, ...) as glTF extras, so the page can swing, tilt, spin and rock them. They are not baked (they move)
and have materials of their own (Play_*). They sit in their own collection, `Play`, which the layout check skips: they have no collider by design.

Only the ambient occlusion is baked (docs/BLENDER.md R1, AO-only scenes, as the street, the meadow and the forest): every baked material carries
`aomap` and `aomap_intensity` (no `lightmap`), on the second UV set; the page keeps these materials lit by its sun and sky. The lamp heads are
`Lamp_Emit`, switched by the page. Every texture is generated here (numpy, own work); no third-party asset is used.

A game point (x, y, z) is Blender (x, -z, y).
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
except ImportError:                       # the textures stage runs in plain Python (numpy and Pillow)
    bpy = None

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import build_overworld_greybox as G      # noqa: E402  the layout model (pure Python)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


ALL = ["playground", "market"]
STAGE = arg("--stage", "art")
SAMPLES = arg("--samples", 128, int)
DEVICE = arg("--device", "auto")
TEXDIR = "blender/textures/overworld_play/"
MARGIN_PX = 8


def scene_list():
    s = arg("--scene", "playground")
    return ALL if s == "all" else s.split(",")


# ================================================================ generated textures (plain Python)
def srgb_encode(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def rs(a, h, w):
    ys, xs = np.linspace(0, a.shape[0] - 1, h), np.linspace(0, a.shape[1] - 1, w)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, a.shape[0] - 1), np.minimum(x0 + 1, a.shape[1] - 1)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    return a[y0][:, x0] * (1 - fy) * (1 - fx) + a[y0][:, x1] * (1 - fy) * fx + a[y1][:, x0] * fy * (1 - fx) + a[y1][:, x1] * fy * fx


def vnoise(h, w, rng, octaves=5, base=4):
    """Value noise that repeats without a seam."""
    out, amp, tot = np.zeros((h, w)), 1.0, 0.0
    for k in range(octaves):
        n = base * 2 ** k
        g = rng.random((n + 1, n + 1))
        g[-1, :] = g[0, :]
        g[:, -1] = g[:, 0]
        out += amp * rs(g, h, w)
        tot += amp
        amp *= 0.5
    return out / tot


def blur(a, r, passes=2):
    n = 2 * r + 1
    for ax in (0, 1):
        for _ in range(passes):
            pad = [(0, 0)] * a.ndim
            pad[ax] = (r + 1, r)
            c = np.cumsum(np.pad(a, pad, mode="wrap"), axis=ax)
            Ln = c.shape[ax]
            a = (np.take(c, range(n, Ln), axis=ax) - np.take(c, range(0, Ln - n), axis=ax)) / n
    return a


def grey(v):
    return np.repeat(np.clip(v, 0, 1)[..., None], 3, axis=2)


def tex_grass(S=512):
    rng = np.random.default_rng(3)
    v = 0.78 + 0.16 * (vnoise(S, S, rng, 5, 4) - 0.5) + 0.10 * (rng.random((S, S)) - 0.5)
    blades = blur(rng.random((S, S)), 1, 1)
    v = v + 0.12 * (blades - 0.5)
    return grey(v * 0.95)


def tex_path(S=512):
    rng = np.random.default_rng(5)
    v = 0.80 + 0.10 * (vnoise(S, S, rng, 5, 8) - 0.5)
    peb = rng.random((S, S)) > 0.985
    v = v - 0.18 * blur(peb.astype(float), 1, 1) * 3 + 0.06 * (rng.random((S, S)) - 0.5)
    return grey(v)


def tex_paving(S=512):
    """2 x 2 square slabs a texture (the texture is 2 m), grout lines, each slab its own shade."""
    rng = np.random.default_rng(7)
    n = 2
    cell = S // n
    v = np.zeros((S, S))
    for i in range(n):
        for j in range(n):
            v[i * cell:(i + 1) * cell, j * cell:(j + 1) * cell] = 0.80 + 0.06 * (rng.random() - 0.5)
    v += 0.07 * (vnoise(S, S, rng, 5, 8) - 0.5)
    g = np.zeros((S, S))
    for k in range(n + 1):
        a = min(k * cell, S - 1)
        for d in range(-4, 5):
            g[np.clip(a + d, 0, S - 1), :] = 1
            g[:, np.clip(a + d, 0, S - 1)] = 1
    g = blur(g, 1, 1)
    return grey(v * (1 - 0.35 * g))


def tex_wood(S=512):
    """Grain along u (boards run along the texture's u)."""
    rng = np.random.default_rng(9)
    y = np.arange(S)[:, None] / S
    x = np.arange(S)[None, :] / S
    warp = vnoise(S, S, rng, 3, 2)
    grain = 0.5 + 0.5 * np.sin(2 * math.pi * (y * 18 + warp * 2.0))
    v = 0.74 + 0.10 * (grain - 0.5) + 0.06 * (vnoise(S, S, rng, 5, 8) - 0.5) + 0.0 * x
    return grey(v)


def tex_hedge(S=512):
    rng = np.random.default_rng(11)
    leaves = blur((rng.random((S, S)) > 0.6).astype(float), 2, 1)
    v = 0.62 + 0.35 * (leaves - 0.5) + 0.20 * (vnoise(S, S, rng, 4, 4) - 0.5)
    return grey(v)


def tex_plaster(S=512):
    rng = np.random.default_rng(13)
    return grey(0.84 + 0.06 * (vnoise(S, S, rng, 6, 4) - 0.5) + 0.02 * (rng.random((S, S)) - 0.5))


# a 5 x 7 pixel font, own work: enough letters for the signs
F57 = {
    "A": "01110 10001 10001 11111 10001 10001 10001", "B": "11110 10001 10001 11110 10001 10001 11110",
    "C": "01111 10000 10000 10000 10000 10000 01111", "D": "11110 10001 10001 10001 10001 10001 11110",
    "E": "11111 10000 10000 11110 10000 10000 11111", "F": "11111 10000 10000 11110 10000 10000 10000",
    "G": "01111 10000 10000 10011 10001 10001 01111", "H": "10001 10001 10001 11111 10001 10001 10001",
    "I": "11111 00100 00100 00100 00100 00100 11111", "K": "10001 10010 10100 11000 10100 10010 10001",
    "L": "10000 10000 10000 10000 10000 10000 11111", "M": "10001 11011 10101 10101 10001 10001 10001",
    "N": "10001 11001 10101 10011 10001 10001 10001", "O": "01110 10001 10001 10001 10001 10001 01110",
    "P": "11110 10001 10001 11110 10000 10000 10000", "R": "11110 10001 10001 11110 10100 10010 10001",
    "S": "01111 10000 10000 01110 00001 00001 11110", "T": "11111 00100 00100 00100 00100 00100 00100",
    "U": "10001 10001 10001 10001 10001 10001 01110", "W": "10001 10001 10001 10101 10101 11011 10001",
    "Y": "10001 10001 01010 00100 00100 00100 00100", "-": "00000 00000 00000 11111 00000 00000 00000",
    " ": "00000 00000 00000 00000 00000 00000 00000",
}
SIGNS = ["WEAPONS", "GEAR", "FOOD", "KEYCARDS", "COSMETICS", "BUY-BACK", "MORE TO COME", "PLAYGROUND", "MARKET",   # rows of 1024 x 128 (16 in all)
         "SPORTS", "RACETRACK", "TENNIS", "BASKETBALL", "FINISH", "PITS"]               # rows 9 to 14: the sports courts and the racetrack
SIGN_COL = [(0.80, 0.16, 0.14), (0.14, 0.34, 0.74), (0.86, 0.58, 0.08), (0.44, 0.22, 0.62), (0.86, 0.36, 0.56), (0.16, 0.56, 0.42),
            (0.10, 0.10, 0.12), (0.14, 0.50, 0.30), (0.80, 0.22, 0.30),
            (0.14, 0.34, 0.74), (0.80, 0.16, 0.14), (0.14, 0.50, 0.30), (0.86, 0.40, 0.08), (0.10, 0.10, 0.12), (0.10, 0.10, 0.12)]


def text_mask(text, h, w, fill=0.62, maxw=0.9):
    adv = 6
    units = len(text) * adv - 1
    s = max(1, int(min(w * maxw / units, h * fill / 7)))
    m = np.zeros((h, w))
    x = (w - units * s) // 2
    y0 = (h - 7 * s) // 2
    for ch in text:
        for r, row in enumerate(F57[ch].split()):
            for c, v in enumerate(row):
                if v == "1":
                    m[y0 + r * s:y0 + (r + 1) * s, x + c * s:x + (c + 1) * s] = 1
        x += adv * s
    return m


def tex_signs():
    img = np.zeros((2048, 1024, 3))
    img[:] = (0.80, 0.76, 0.62)
    for i, t in enumerate(SIGNS):
        slot = np.zeros((128, 1024, 3))
        slot[:] = (0.80, 0.76, 0.62)
        m = text_mask(t, 128, 1024)[..., None]
        col = np.array(SIGN_COL[i]) * 0.5
        slot = slot * (1 - m) + col * m
        slot[:8] = slot[-8:] = slot[:, :8] = slot[:, -8:] = col
        img[i * 128:(i + 1) * 128] = slot
    return img


def sign_uv(text):
    i = SIGNS.index(text)
    return (0.0, 1 - (i + 1) / 16, 1.0, 1 - i / 16)          # (u0, v0, u1, v1), Blender's v up


TEXTURES = {"grass.png": tex_grass, "path.png": tex_path, "paving.png": tex_paving, "wood.png": tex_wood, "hedge.png": tex_hedge,
            "plaster.png": tex_plaster, "signs.png": tex_signs}


def stage_textures():
    from PIL import Image
    d = ROOT / TEXDIR
    d.mkdir(parents=True, exist_ok=True)
    for n, fn in TEXTURES.items():
        a = fn()
        Image.fromarray((srgb_encode(a) * 255 + 0.5).astype(np.uint8)).save(d / n, optimize=True)
        print("TEXTURE", n, a.shape, f"linear mean {a.mean():.3f} max {a.max():.3f}", (d / n).stat().st_size)


if bpy is None:
    if STAGE == "textures":
        stage_textures()
    else:
        print("without Blender only --stage textures runs")
    sys.exit(0)


# ================================================================ Blender from here on
SCENE = GB = BLEND = STILLS = None


def setup(sid):
    global SCENE, GB, BLEND, STILLS
    SCENE = sid
    GB = G.build(sid)
    BLEND = ROOT / f"blender/scenes/{sid}.blend"
    STILLS = ROOT / f"docs/renders/{sid}"


def work_dir(sid=None):
    d = Path(arg("--work", str(ROOT / "work"))) / (sid or SCENE)
    d.mkdir(parents=True, exist_ok=True)
    return d


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


def material(name, color=(0.5, 0.5, 0.5), rough=0.6, diff=None, tint=None, emit=None, tile=1.0):
    """A Principled material. `tint` multiplies the texture (a Mix set to Multiply: the glTF exporter writes it as baseColorFactor)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    if diff:
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "UVMap"
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image(TEXDIR + diff, True)
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
    m.use_backface_culling = True
    TILES[name] = tile
    MATS[name] = m
    return m


LAMP_EMIT = 3.0
# the colours: bright, plastic and pastel (docs/WORLD.md: the Overworld is plastic and bright), every channel held at or under 0.85 (linear)
FLAT = {
    "Steel": (0.52, 0.55, 0.58), "Plastic_Red": (0.80, 0.14, 0.11), "Plastic_Blue": (0.12, 0.34, 0.80), "Plastic_Yellow": (0.85, 0.70, 0.09),
    "Plastic_Green": (0.14, 0.62, 0.28), "Plastic_White": (0.82, 0.80, 0.76), "Bin_Green": (0.10, 0.42, 0.22), "Fake_Door": (0.42, 0.26, 0.16),
    "Window": (0.16, 0.26, 0.36), "Sign_Board": (0.80, 0.74, 0.52), "Fence_White": (0.84, 0.82, 0.78), "Paint_White": (0.84, 0.84, 0.80),
    "Paint_Yellow": (0.85, 0.72, 0.18), "Soil": (0.30, 0.20, 0.12), "Awning_White": (0.84, 0.82, 0.76),
    "Awning_A": (0.80, 0.22, 0.22), "Awning_B": (0.18, 0.42, 0.80), "Awning_C": (0.85, 0.62, 0.12), "Awning_D": (0.50, 0.28, 0.70),
    "Awning_E": (0.85, 0.42, 0.64), "Awning_F": (0.22, 0.64, 0.50),
}
GOODS = {"Goods_Dark": (0.10, 0.10, 0.12), "Goods_Orange": (0.85, 0.36, 0.06), "Goods_Red": (0.70, 0.08, 0.06), "Goods_Green": (0.22, 0.56, 0.12),
         "Goods_Yellow": (0.85, 0.72, 0.10), "Goods_Bread": (0.62, 0.36, 0.14), "Goods_Blue": (0.12, 0.30, 0.72), "Goods_Pink": (0.85, 0.50, 0.66),
         "Goods_Mint": (0.50, 0.80, 0.66), "Goods_White": (0.82, 0.82, 0.80), "Goods_Purple": (0.42, 0.22, 0.62), "Goods_Glass": (0.56, 0.72, 0.76),
         "Goods_Grey": (0.40, 0.42, 0.44), "Goods_Stem": (0.14, 0.50, 0.20)}
PLAY = {"Play_Steel": (0.52, 0.55, 0.58), "Play_Red": (0.80, 0.14, 0.11), "Play_Blue": (0.12, 0.34, 0.80), "Play_Yellow": (0.85, 0.70, 0.09),
        "Play_Green": (0.14, 0.62, 0.28), "Play_Black": (0.06, 0.06, 0.07), "Play_White": (0.82, 0.80, 0.76)}
TEXTURED = {   # name: (texture, tint, roughness, metres a repeat)
    "Grass": ("grass.png", (0.36, 0.74, 0.30), 0.95, 2.0), "Path": ("path.png", (0.86, 0.74, 0.54), 0.95, 2.0),
    "Paving": ("paving.png", (0.86, 0.82, 0.76), 0.85, 2.0), "Rubber": ("path.png", (0.72, 0.26, 0.22), 0.9, 1.0),
    "Sand": ("path.png", (0.98, 0.88, 0.60), 0.95, 1.0), "Hedge": ("hedge.png", (0.16, 0.50, 0.20), 0.95, 1.5),
    "Timber": ("wood.png", (0.78, 0.56, 0.32), 0.7, 1.0), "Shelf_Wood": ("wood.png", (0.72, 0.58, 0.40), 0.7, 1.0),
    "Counter_Wood": ("wood.png", (0.62, 0.42, 0.24), 0.6, 1.0), "Crate_Wood": ("wood.png", (0.80, 0.64, 0.40), 0.8, 0.8),
    "Facade": ("plaster.png", (0.92, 0.84, 0.74), 0.9, 2.0), "Signs": ("signs.png", None, 0.5, 1.0),
}
GB_MAT = {"grass": "Grass", "hedge": "Hedge", "path": "Path", "paving": "Paving", "rubber": "Rubber", "sand": "Sand", "timber": "Timber",
          "furniture": "Shelf_Wood", "counter": "Counter_Wood", "steel": "Steel", "plastic_red": "Plastic_Red", "plastic_blue": "Plastic_Blue",
          "plastic_yellow": "Plastic_Yellow", "plastic_green": "Plastic_Green", "plastic_white": "Plastic_White", "facade": "Facade",
          "fake_door": "Fake_Door", "window": "Window", "sign": "Sign_Board", "lamp": "Lamp_Emit", "awning_a": "Awning_A", "awning_b": "Awning_B",
          "awning_c": "Awning_C", "awning_d": "Awning_D", "awning_e": "Awning_E", "awning_f": "Awning_F"}
GB_PLAY = {"steel": "Play_Steel", "plastic_red": "Play_Red", "plastic_blue": "Play_Blue", "plastic_yellow": "Play_Yellow",
           "plastic_green": "Play_Green", "plastic_white": "Play_White"}


def make_materials():
    for n, (tx, tint, r, tile) in TEXTURED.items():
        material(n, diff=tx, tint=tint, rough=r, tile=tile)
    for n, c in FLAT.items():
        material(n, color=c, rough=0.35 if n.startswith(("Plastic", "Bin", "Awning")) else 0.6)
    for n, c in GOODS.items():
        material(n, color=c, rough=0.4)
    for n, c in PLAY.items():
        material(n, color=c, rough=0.35)
    material("Lamp_Emit", color=(0.85, 0.84, 0.76), rough=0.5, emit=((1.0, 0.95, 0.80), LAMP_EMIT))


# ---------------------------------------------------------------- geometry helpers (game coordinates in, world space)
def cube(bm, gmin, gmax):
    a, b = B(gmin), B(gmax)
    c = (a + b) / 2
    s = Vector((abs(a.x - b.x), abs(a.y - b.y), abs(a.z - b.z)))
    return bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((s.x, s.y, s.z, 1.0)))["verts"]


def bevel_box(bm, gmin, gmax, r=0.02, seg=2):
    vs = cube(bm, gmin, gmax)
    d = min(gmax[i] - gmin[i] for i in range(3))
    r = min(r, d * 0.3)
    if r > 0.004:
        es = list({e for v in vs for e in v.link_edges})
        bmesh.ops.bevel(bm, geom=es + vs, offset=r, segments=seg, affect="EDGES", profile=0.5, clamp_overlap=True)


def cyl(bm, p0, p1, r0, r1=None, seg=12, cap=True):
    a, b = B(p0), B(p1)
    d = b - a
    q = d.to_track_quat("Z", "Y")
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                          matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())


def ellipsoid(bm, p, rx, ry, rz, seg=10):
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(5, seg // 2 + 1), radius=1.0,
                              matrix=Matrix.Translation(B(p)) @ Matrix.Diagonal((rx, rz, ry, 1)))


def tube(bm, pts, r, seg=8):
    P = [B(p) for p in pts]
    rings, prev = [], None
    for i, p in enumerate(P):
        t = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        if prev is None:
            a = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
            nn = t.cross(a).normalized()
        else:
            nn = (prev - t * prev.dot(t))
            nn = nn.normalized() if nn.length > 1e-9 else prev
        b = t.cross(nn)
        prev = nn
        rings.append([bm.verts.new(p + (nn * math.cos(2 * math.pi * k / seg) + b * math.sin(2 * math.pi * k / seg)) * r) for k in range(seg)])
    for a_, b_ in zip(rings, rings[1:]):
        for k in range(seg):
            bm.faces.new((a_[k], a_[(k + 1) % seg], b_[(k + 1) % seg], b_[k]))


def quad(bm, x0, x1, z0, z1, y):
    vs = [bm.verts.new(B(p)) for p in ((x0, y, z0), (x0, y, z1), (x1, y, z1), (x1, y, z0))]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.z < 0:
        f.normal_flip()
    return f


def box_uv(bm, tile):
    """UV0: box projection in metres / tile from world positions."""
    uvl = bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y
            u, v = ((gz, gy) if ax == 0 else (gx, gy) if ax == 1 else (gx, gz))
            lp[uvl].uv = (u / tile, v / tile)


ART = PLAYC = LAYOUT_C = None


def finish(name, bm, mat, coll=None, smooth=False, keep_uv=False):
    for f in bm.faces:
        f.smooth = smooth
    if not bm.loops.layers.uv.get("UVMap"):
        bm.loops.layers.uv.new("UVMap")
    bm.normal_update()
    if not keep_uv:
        box_uv(bm, TILES.get(mat, 1.0))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(name, me)
    (coll or ART).objects.link(ob)
    if mat == "Lamp_Emit":
        ob.visible_shadow = False
    return ob


class Acc:
    """Faces by material for one named piece of art, finished as one object per material: <name> for the first, <name>_<material> after."""
    def __init__(s, name, coll=None):
        s.name, s.bms, s.coll, s.smooth = name, {}, coll, set()

    def bm(s, mat, smooth=False):
        if smooth:
            s.smooth.add(mat)
        return s.bms.setdefault(mat, bmesh.new())

    def done(s):
        out = []
        for i, (m, bm) in enumerate(s.bms.items()):
            if not bm.faces:
                bm.free()
                continue
            out.append(finish(s.name if i == 0 else f"{s.name}_{m}", bm, m, s.coll, smooth=m in s.smooth))
        return out


def thin_axis(mn, mx):
    """The long axis of a thin box (two sides at most 0.16 m and the third three times longer), else None."""
    d = [mx[i] - mn[i] for i in range(3)]
    o = sorted(range(3), key=lambda i: d[i])
    if d[o[1]] <= 0.165 and d[o[2]] >= 3 * d[o[1]]:
        return o[2]
    return None


def shape_box(bm, mn, mx, bevel=0.02):
    """A greybox box as art: a thin one becomes a round bar along its long axis, any other a box with softened edges."""
    ax = thin_axis(mn, mx)
    if ax is not None:
        c = [(mn[i] + mx[i]) / 2 for i in range(3)]
        r = min(mx[i] - mn[i] for i in range(3) if i != ax) / 2
        p0, p1 = list(c), list(c)
        p0[ax], p1[ax] = mn[ax], mx[ax]
        cyl(bm, p0, p1, r, seg=10)
        return True
    bevel_box(bm, mn, mx, bevel)
    return False


# ---------------------------------------------------------------- the art of each collider and decor box
def sign_face_uv(bm, text, normal_game):
    """Map the face of bm whose normal is normal_game (game axes) to the sign atlas row of `text`; the other faces to the row's border."""
    u0, v0, u1, v1 = sign_uv(text)
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    n = B(normal_game).normalized()
    up = Vector((0, 0, 1))
    right = up.cross(n)
    bm.normal_update()
    front = [f for f in bm.faces if f.normal.dot(n) > 0.9]
    pts = [lp.vert.co for f in front for lp in f.loops]
    if not pts:
        return
    us = [p.dot(right) for p in pts]
    zs = [p.z for p in pts]
    a0, a1, b0, b1 = min(us), max(us), min(zs), max(zs)
    for f in bm.faces:
        for lp in f.loops:
            if f in front:
                p = lp.vert.co
                lp[uvl].uv = (u0 + (u1 - u0) * (p.dot(right) - a0) / max(a1 - a0, 1e-6), v0 + (v1 - v0) * (p.z - b0) / max(b1 - b0, 1e-6))
            else:
                lp[uvl].uv = (u0 + 0.002, v0 + 0.01)


def sign_obj(name, mn, mx, text, normal):
    bm = bmesh.new()
    cube(bm, mn, mx)
    bm.loops.layers.uv.new("UVMap")
    sign_face_uv(bm, text, normal)
    bm.normal_update()
    n = B(normal).normalized()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.normal.dot(n) < -0.9], context="FACES")      # the back: against the board or unseen
    return finish(name, bm, "Signs", keep_uv=True)


def slab(name, b, mat):
    """The ground: its top, and its sides down to the slab's bottom (no bottom face)."""
    bm = bmesh.new()
    cube(bm, b["min"], b["max"])
    bm.normal_update()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.normal.z < -0.9], context="FACES")
    return finish(name, bm, mat)


def bench_art(name, b):
    mn, mx = b["min"], b["max"]
    acc = Acc(name)
    along_x = (mx[0] - mn[0]) >= (mx[2] - mn[2])
    bm = acc.bm("Timber")
    L0, L1 = (mn[0], mx[0]) if along_x else (mn[2], mx[2])
    W0, W1 = (mn[2], mx[2]) if along_x else (mn[0], mx[0])
    n = 4
    gap = 0.02
    w = (W1 - W0 - gap * (n - 1)) / n
    for k in range(n):
        a = W0 + k * (w + gap)
        lo = (L0, mx[1] - 0.05, a) if along_x else (a, mx[1] - 0.05, L0)
        hi = (L1, mx[1], a + w) if along_x else (a + w, mx[1], L1)
        bevel_box(bm, lo, hi, 0.01, 1)
    st = acc.bm("Steel")
    for t in (L0, L1 - 0.06):                                  # the legs at the ends, so the art fills the collider's box
        for s0, s1 in ((W0, W0 + 0.06), (W1 - 0.06, W1)):
            lo = (t, 0.0, s0) if along_x else (s0, 0.0, t)
            hi = (t + 0.06, mx[1] - 0.05, s1) if along_x else (s1, mx[1] - 0.05, t + 0.06)
            cube(st, lo, hi)
    acc.done()


def fence_art(name, b):
    mn, mx = b["min"], b["max"]
    bm = bmesh.new()
    z0, z1 = mn[2], mx[2]
    zc = (z0 + z1) / 2
    for y in (0.22, 0.58):                                       # two rails behind the pickets (away from the path)
        za, zb = (zc + 0.02, z1) if zc > 0 else (z0, zc - 0.02)
        cube(bm, (mn[0], y, za), (mx[0], y + 0.07, zb))
    x = mn[0] + 0.12
    while x + 0.07 <= mx[0] - 0.12:
        cube(bm, (x, 0.0, zc - 0.02), (x + 0.07, mx[1] - 0.06, zc + 0.02))
        x += 0.16
    # the run's ends: a post at each, the full height, so the art reaches the collider's ends
    for xa in (mn[0], mx[0] - 0.09):
        cube(bm, (xa, 0.0, z0), (xa + 0.09, mx[1], z1))
    finish(name, bm, "Fence_White")


def bin_art(name, b):
    mn, mx = b["min"], b["max"]
    c = ((mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2)
    r = min(mx[0] - mn[0], mx[2] - mn[2]) / 2
    acc = Acc(name)
    cyl(acc.bm("Bin_Green", True), (c[0], 0.0, c[1]), (c[0], mx[1] - 0.06, c[1]), r * 0.9, r, seg=16)
    cyl(acc.bm("Steel", True), (c[0], mx[1] - 0.06, c[1]), (c[0], mx[1], c[1]), r, r * 0.8, seg=16)
    acc.done()


def lamp_head(name, b):
    mn, mx = b["min"], b["max"]
    cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
    acc = Acc(name)
    bm = acc.bm("Lamp_Emit", True)
    ellipsoid(bm, (cx, mn[1] + 0.06, cz), 0.22, 0.17, 0.22, seg=14)
    cyl(acc.bm("Steel", True), (cx, mn[1] + 0.15, cz), (cx, mx[1] + 0.05, cz), 0.30, 0.06, seg=16)
    acc.done()


def crate_art(name, b):
    """Stacks of 0.8 m wooden crates, 0.6 m high, filling the collider's box: one crate across and one or two high."""
    mn, mx = b["min"], b["max"]
    acc = Acc(name)
    bm = acc.bm("Crate_Wood")
    nx = max(1, round((mx[0] - mn[0]) / 0.8))
    ny = max(1, round((mx[1] - mn[1]) / 0.6))
    w, h = (mx[0] - mn[0]) / nx, (mx[1] - mn[1]) / ny
    for i in range(nx):
        for j in range(ny):
            x0, y0 = mn[0] + i * w, mn[1] + j * h
            bevel_box(bm, (x0 + 0.03, y0, mn[2] + 0.03), (x0 + w - 0.03, y0 + h - 0.02, mx[2] - 0.03), 0.01, 1)
            for (a0, a1) in ((x0, x0 + 0.06), (x0 + w - 0.06, x0 + w)):          # corner battens
                for (c0, c1) in ((mn[2], mn[2] + 0.06), (mx[2] - 0.06, mx[2])):
                    cube(bm, (a0, y0, c0), (a1, y0 + h, c1))
            for yy in (y0 + 0.02, y0 + h - 0.1):                                   # bands round the crate
                cube(bm, (x0, yy, mn[2]), (x0 + w, yy + 0.06, mn[2] + 0.04))
                cube(bm, (x0, yy, mx[2] - 0.04), (x0 + w, yy + 0.06, mx[2]))
    # fruit in the top crates (decor: it sits inside the crate's box)
    if SCENE == "market":
        fr = Acc("decor_" + name + "_fruit")
        rng = np.random.default_rng(abs(hash(name)) % 1000)
        for i in range(nx):
            x0 = mn[0] + i * w
            col = ["Goods_Red", "Goods_Orange", "Goods_Green", "Goods_Yellow"][(i + len(name)) % 4]
            for k in range(9):
                fx = x0 + 0.16 + (k % 3) * (w - 0.32) / 2 + rng.uniform(-0.03, 0.03)
                fz = mn[2] + 0.16 + (k // 3) * ((mx[2] - mn[2]) - 0.32) / 2 + rng.uniform(-0.03, 0.03)
                ellipsoid(fr.bm(col, True), (fx, mx[1] - 0.06, fz), 0.09, 0.08, 0.09, seg=8)
        fr.done()
    acc.done()


def shelves_art(name, b, stock):
    """Open shelving inside the collider's box: two ends, a back panel and four boards; goods on the boards."""
    mn, mx = b["min"], b["max"]
    acc = Acc(name)
    bm = acc.bm("Shelf_Wood")
    back_n = mn[2] < -15                       # a north stall's shelves stand against its back at z -20 (their back at min z)
    zb0, zb1 = (mn[2], mn[2] + 0.04) if back_n else (mx[2] - 0.04, mx[2])
    cube(bm, (mn[0], 0.0, zb0), (mx[0], mx[1], zb1))
    for xa in (mn[0], mx[0] - 0.05):
        cube(bm, (xa, 0.0, mn[2]), (xa + 0.05, mx[1], mx[2]))
    levels = [0.08, 0.68, 1.28, mx[1] - 0.04]
    for y in levels:
        cube(bm, (mn[0], y - 0.04, mn[2]), (mx[0], y, mx[2]))
    acc.done()
    goods(name, mn[0] + 0.15, mx[0] - 0.15, mn[2] + 0.06, mx[2] - 0.06, levels[1:], stock, front_z=(mx[2] if back_n else mn[2]))


def counter_art(name, b):
    mn, mx = b["min"], b["max"]
    acc = Acc(name)
    bevel_box(acc.bm("Counter_Wood"), (mn[0] + 0.04, 0.0, mn[2] + 0.04), (mx[0] - 0.04, mx[1] - 0.05, mx[2] - 0.04), 0.015, 1)
    bevel_box(acc.bm("Timber"), (mn[0], mx[1] - 0.05, mn[2]), (mx[0], mx[1], mx[2]), 0.012, 1)
    acc.done()


def awning_art(name, b, mat):
    """Stripes across the awning (each 0.5 m, its colour and white), and a scalloped valance hanging at its front (decor)."""
    mn, mx = b["min"], b["max"]
    acc = Acc(name)
    x, k = mn[0], 0
    while x < mx[0] - 1e-6:
        x1 = min(mx[0], x + 0.5)
        cube(acc.bm(mat if k % 2 == 0 else "Awning_White"), (x, mn[1], mn[2]), (x1, mx[1], mx[2]))
        x, k = x1, k + 1
    acc.done()


def valance(name, x0, x1, z, mat, y=2.8):
    acc = Acc("decor_" + name)
    x, k = x0, 0
    while x < x1 - 1e-6:
        xb = min(x1, x + 0.5)
        bm = acc.bm(mat if k % 2 == 0 else "Awning_White")
        # a tab with a rounded bottom: a box and a flattened half-disc under it
        cube(bm, (x, y - 0.22, z - 0.01), (xb, y, z + 0.01))
        cyl(bm, ((x + xb) / 2, y - 0.22, z - 0.01), ((x + xb) / 2, y - 0.22, z + 0.01), (xb - x) / 2, seg=12)
        x, k = xb, k + 1
    for o in acc.done():
        pass


def goods(name, x0, x1, z0, z1, levels, stock, front_z):
    """Goods on the shelves and the counter, decor_ (they stand inside the shelves' and the counter's colliders)."""
    acc = Acc("decor_goods_" + name)
    rng = np.random.default_rng(len(name) * 7 + len(stock))
    zc = (z0 + z1) / 2
    for li, y in enumerate(levels):
        x = x0
        while x < x1 - 0.3:
            if stock == "weapons":                          # toy blasters on their sides, stocks and barrels
                bm = acc.bm(["Goods_Dark", "Goods_Orange", "Goods_Blue"][int(rng.integers(3))])
                bevel_box(bm, (x, y, zc - 0.12), (x + 0.45, y + 0.14, zc + 0.04), 0.02, 1)
                cyl(acc.bm("Goods_Grey", True), (x + 0.45, y + 0.09, zc - 0.04), (x + 0.68, y + 0.09, zc - 0.04), 0.025, seg=8)
                cube(acc.bm("Goods_Dark"), (x + 0.12, y, zc - 0.03), (x + 0.2, y + 0.14, zc + 0.0))
                x += 0.8
            elif stock == "gear":                           # backpacks and helmets
                if rng.random() < 0.55:
                    bevel_box(acc.bm(["Goods_Green", "Goods_Blue", "Goods_Red", "Goods_Yellow"][int(rng.integers(4))]),
                              (x, y, zc - 0.13), (x + 0.34, y + 0.44, zc + 0.13), 0.05, 2)
                    x += 0.46
                else:
                    bm = acc.bm(["Goods_Grey", "Goods_White", "Goods_Orange"][int(rng.integers(3))], True)
                    ellipsoid(bm, (x + 0.15, y, zc), 0.15, 0.17, 0.15, seg=12)
                    x += 0.38
            elif stock == "food":                           # jars, tins and loaves
                r = rng.random()
                if r < 0.4:
                    for k in range(3):
                        cyl(acc.bm(["Goods_Red", "Goods_Yellow", "Goods_Green"][k], True), (x + 0.08 + k * 0.17, y, zc),
                            (x + 0.08 + k * 0.17, y + 0.18, zc), 0.07, seg=10)
                    x += 0.6
                elif r < 0.7:
                    ellipsoid(acc.bm("Goods_Bread", True), (x + 0.18, y + 0.06, zc), 0.18, 0.08, 0.1, seg=10)
                    x += 0.44
                else:
                    cyl(acc.bm("Goods_Glass", True), (x + 0.09, y, zc), (x + 0.09, y + 0.24, zc), 0.08, seg=10)
                    cyl(acc.bm("Goods_Red", True), (x + 0.09, y + 0.24, zc), (x + 0.09, y + 0.27, zc), 0.08, seg=10)
                    x += 0.26
            elif stock == "keycards":                       # cards standing in racks, in their tier colours
                for k in range(6):
                    col = ["Goods_Blue", "Goods_Green", "Goods_Red", "Goods_Purple", "Goods_Yellow", "Goods_White"][(k + li) % 6]
                    cube(acc.bm(col), (x + k * 0.09, y, zc - 0.03), (x + k * 0.09 + 0.06, y + 0.09, zc + 0.03))
                cube(acc.bm("Goods_Dark"), (x - 0.02, y, zc - 0.06), (x + 0.55, y + 0.03, zc + 0.06))
                x += 0.75
            else:                                           # cosmetics: bottles and pots
                for k in range(4):
                    h = 0.12 + 0.08 * ((k + li) % 3)
                    col = ["Goods_Pink", "Goods_Mint", "Goods_Purple", "Goods_White"][(k + li) % 4]
                    cyl(acc.bm(col, True), (x + 0.05 + k * 0.12, y, zc), (x + 0.05 + k * 0.12, y + h, zc), 0.045, seg=10)
                    cyl(acc.bm("Goods_White", True), (x + 0.05 + k * 0.12, y + h, zc), (x + 0.05 + k * 0.12, y + h + 0.03, zc), 0.025, seg=8)
                x += 0.62
    acc.done()


def counter_goods(name, b, stock):
    mn, mx = b["min"], b["max"]
    y = mx[1]
    cx = (mn[0] + mx[0]) / 2
    zc = (mn[2] + mx[2]) / 2
    acc = Acc("decor_counter_" + name)
    if stock == "food":
        for k, col in enumerate(("Goods_Red", "Goods_Orange", "Goods_Green", "Goods_Yellow")):
            x0 = cx - 2.4 + k * 1.3
            cube(acc.bm("Crate_Wood"), (x0, y, zc - 0.22), (x0 + 0.9, y + 0.12, zc + 0.22))
            for i in range(5):
                for j in range(2):
                    ellipsoid(acc.bm(col, True), (x0 + 0.1 + i * 0.175, y + 0.17, zc - 0.1 + j * 0.2), 0.085, 0.08, 0.085, seg=8)
    elif stock == "weapons":
        for k in range(4):
            x0 = cx - 2.2 + k * 1.2
            cube(acc.bm("Goods_Grey"), (x0, y, zc - 0.04), (x0 + 0.7, y + 0.02, zc + 0.04))            # toy swords, flat on the counter
            cube(acc.bm("Goods_Dark"), (x0 - 0.2, y, zc - 0.1), (x0, y + 0.04, zc + 0.1))
    elif stock == "keycards":
        cube(acc.bm("Goods_White"), (cx - 0.6, y, zc - 0.15), (cx + 0.6, y + 0.02, zc + 0.15))
        for k in range(8):
            cube(acc.bm(["Goods_Blue", "Goods_Green", "Goods_Red", "Goods_Purple"][k % 4]), (cx - 0.55 + k * 0.14, y + 0.02, zc - 0.05),
                 (cx - 0.46 + k * 0.14, y + 0.025, zc + 0.05))
    elif stock == "cosmetics":
        cube(acc.bm("Goods_Glass"), (cx - 0.3, y, zc - 0.02), (cx + 0.3, y + 0.5, zc + 0.02))                # a mirror
        for k in range(6):
            cyl(acc.bm(["Goods_Pink", "Goods_Mint"][k % 2], True), (cx - 2.0 + k * 0.3, y, zc), (cx - 2.0 + k * 0.3, y + 0.16, zc), 0.05, seg=10)
    elif stock == "gear":
        for k in range(3):
            tube(acc.bm("Goods_Yellow", True), [(cx - 2.0 + k * 1.5 + 0.18 * math.cos(a / 8 * 2 * math.pi), y + 0.04,
                                                  zc + 0.18 * math.sin(a / 8 * 2 * math.pi)) for a in range(9)], 0.035)
    acc.done()


def facade_art(name, b):
    mn, mx = b["min"], b["max"]
    acc = Acc(name)
    bevel_box(acc.bm("Facade"), mn, mx, 0.03, 1)
    acc.done()


# ---------------------------------------------------------------- the playground's moving parts
def play_part(p):
    """One Play_ part: its greybox boxes, shaped (bars round, plates softened), the object at the pivot."""
    nm = p["name"]
    eq, part = p["props"]["equipment"], p["props"]["part"]
    piv = p["pivot"]
    bms = {}

    def bm_of(m):
        return bms.setdefault(m, bmesh.new())
    if eq == "merry_go_round":
        cx, y, cz = piv
        cyl(bm_of("Play_Yellow"), (cx, y, cz), (cx, y + 0.12, cz), 1.6, seg=32)
        cyl(bm_of("Play_Red"), (cx, y + 0.12, cz), (cx, y + 0.14, cz), 1.3, seg=32)
        for mn, mx, m in p["boxes"]:
            if m == "steel" and thin_axis(mn, mx) is not None:          # the centre post and the four handrail posts
                shape_box(bm_of("Play_Steel"), mn, mx)
        for a in range(4):                                                 # spokes from the centre post to each handrail post
            t = math.radians(45 + 90 * a)
            cyl(bm_of("Play_Steel"), (cx, y + 0.9, cz), (cx + 1.15 * math.cos(t), y + 0.9, cz + 1.15 * math.sin(t)), 0.03, seg=8)
        tube(bm_of("Play_Steel"), [(cx + 1.15 * math.cos(math.radians(a)), y + 0.9, cz + 1.15 * math.sin(math.radians(a))) for a in range(45, 406, 15)], 0.03)
    elif eq == "spring_riders":
        cx, y, cz = piv
        what = p["props"].get("what", "")
        col = {"horse": "Play_Red", "duck": "Play_Yellow", "bee": "Play_Blue"}.get(what, "Play_Red")
        coil = [(cx + 0.09 * math.cos(t), y + 0.02 + 0.33 * t / (6 * math.pi), cz + 0.09 * math.sin(t)) for t in np.linspace(0, 6 * math.pi, 49)]
        tube(bm_of("Play_Steel"), coil, 0.018, seg=6)
        ellipsoid(bm_of(col), (cx, y + 0.52, cz), 0.45, 0.17, 0.16, seg=14)
        ellipsoid(bm_of(col), (cx + 0.42, y + 0.84, cz), 0.14, 0.16, 0.12, seg=12)
        cyl(bm_of("Play_Black"), (cx - 0.02, y + 0.69, cz), (cx - 0.02, y + 0.71, cz), 0.13, seg=12)
        cyl(bm_of("Play_Steel"), (cx + 0.22, y + 0.87, cz - 0.25), (cx + 0.22, y + 0.87, cz + 0.25), 0.02, seg=8)
        cyl(bm_of("Play_Steel"), (cx + 0.22, y + 0.66, cz), (cx + 0.22, y + 0.87, cz), 0.02, seg=8)
        if what == "bee":
            for dx in (-0.2, 0.0, 0.2):
                cyl(bm_of("Play_Black"), (cx + dx - 0.04, y + 0.52, cz), (cx + dx + 0.04, y + 0.52, cz), 0.172, seg=14)
        cyl(bm_of("Play_Black"), (cx + 0.52, y + 0.86, cz - 0.07), (cx + 0.53, y + 0.86, cz - 0.07), 0.03, seg=8)
        cyl(bm_of("Play_Black"), (cx + 0.52, y + 0.86, cz + 0.07), (cx + 0.53, y + 0.86, cz + 0.07), 0.03, seg=8)
    else:
        for mn, mx, m in p["boxes"]:
            mm = GB_PLAY.get(m, "Play_Steel")
            if eq == "swing" and m == "plastic_red":
                mm = "Play_Black"                            # rubber seats
            shape_box(bm_of(mm), mn, mx, 0.03)
    me = bpy.data.meshes.new(nm)
    big = bmesh.new()
    mlist = []
    for m, bm in bms.items():
        if not bm.faces:
            continue
        mi = len(mlist)
        mlist.append(m)
        for f in bm.faces:
            f.material_index = mi
            f.smooth = eq in ("merry_go_round", "spring_riders") or m == "Play_Steel"
        tmp = bpy.data.meshes.new("tmp")
        bm.to_mesh(tmp)
        bm.free()
        big.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
    big.transform(Matrix.Translation(-B(piv)))
    big.loops.layers.uv.new("UVMap") if not big.loops.layers.uv.get("UVMap") else None
    big.to_mesh(me)
    big.free()
    for m in mlist:
        me.materials.append(MATS[m])
    ob = bpy.data.objects.new(nm, me)
    ob.location = B(piv)
    for k, v in p["props"].items():
        ob[k] = v
    ob["pivot"] = [round(v, 3) for v in piv]
    PLAYC.objects.link(ob)
    return ob


# ---------------------------------------------------------------- the dressing, from the greybox's boxes
STALL_STOCK = {f"Stall{n}": stock for n, stock, *_ in G.STALLS}


def build_boxes():
    """Every art box of the greybox becomes art, named as the greybox names it (decor_ for the passable ones)."""
    kiosk_signs = []
    for b in GB.boxes:
        if b.get("zone") or b.get("ctx") or not b.get("art", True):
            continue
        n, m = b["name"], b["mat"]
        mat = GB_MAT.get(m, "Plastic_White")
        mn, mx = b["min"], b["max"]
        if n.startswith("Ground_"):
            slab(n, b, mat)
        elif n.startswith("Hedge_"):
            bm = bmesh.new()
            bevel_box(bm, mn, mx, 0.12, 2)
            finish(n, bm, "Hedge")
        elif n.startswith("Bench_") or (n.startswith("Picnic_") and "_Bench" in n):
            bench_art(n, b)
        elif n.startswith("Picnic_") and "_Table" in n:
            bench_art(n, b)
        elif n.startswith("Fence_"):
            fence_art(n, b)
        elif n.startswith("Bin_"):
            bin_art(n, b)
        elif n.startswith("Crates_"):
            crate_art(n, b)
        elif n.startswith("decor_Lamp_") and n.endswith("_Head"):
            lamp_head(n, b)
        elif n.startswith("Stall") and n.endswith("_Shelves"):
            shelves_art(n, b, STALL_STOCK[n.split("_")[0]])
        elif n.startswith("Stall") and n.endswith("_Counter"):
            counter_art(n, b)
            counter_goods(n, b, STALL_STOCK[n.split("_")[0]])
        elif n.startswith("Stall") and n.endswith("_Awning"):
            awning_art(n, b, mat)
            front = mn[2] if mn[2] > 0 else mx[2]          # the awning's edge toward the square
            valance(n + "_valance", mn[0], mx[0], front, mat)
        elif n.startswith("decor_Stall") and n.endswith("_Sign"):
            st = STALL_STOCK[n.split("_")[1]]
            sign_obj(n, mn, mx, st.upper(), (0, 0, 1) if mn[2] < 0 else (0, 0, -1))
        elif n.startswith("decor_Kiosk_Sign"):
            sign_obj(n, mn, mx, "BUY-BACK", (0, 0, -1) if n.endswith("_N") else (0, 0, 1))
        elif n.startswith("decor_Facade_") and n.endswith("_Sign"):
            sign_obj(n, mn, mx, "MORE TO COME", (-1, 0, 0) if SCENE == "market" else (0, 0, 1))
        elif n.startswith("Facade_") and n.count("_") == 1:
            facade_art(n, b)
        elif n.startswith("Kiosk_Roof"):
            awning_art(n, b, "Awning_F")
        elif n.startswith("decor_") and (mx[1] - mn[1]) < 0.03:
            bm = bmesh.new()                                 # a pad, the path, the sand: a flat top just above the grass
            quad(bm, mn[0], mx[0], mn[2], mx[2], mx[1] + 0.012)
            finish(n, bm, mat)
        elif n.startswith("Step_") and mn[1] >= 0.5 - 1e-6 and mx[1] - mn[1] > 0.2:
            bm = bmesh.new()                                 # a step up in the air: a 19 cm tread under its top (the check's stand rule)
            bevel_box(bm, (mn[0], mn[1] + 0.05, mn[2]), (mx[0], mx[1] - 0.01, mx[2]), 0.02, 2)
            finish(n, bm, mat)
        elif n.startswith("Slide_Rail"):
            for k, (ya, yb) in enumerate(((mn[1], mn[1] + 0.17), (mn[1] + 0.21, mn[1] + 0.38), (mx[1] - 0.36, mx[1]))):
                bm = bmesh.new()                             # a guard rail of three bars, each its own piece
                c = (mn[2] + mx[2]) / 2
                if k < 2:
                    cyl(bm, (mn[0], (ya + yb) / 2, c), (mx[0], (ya + yb) / 2, c), 0.025, seg=10)
                    cube(bm, (mn[0], ya, mn[2]), (mn[0] + 0.05, yb, mx[2]))
                    cube(bm, (mx[0] - 0.05, ya, mn[2]), (mx[0], yb, mx[2]))
                else:
                    cyl(bm, (mn[0], yb - 0.03, c), (mx[0], yb - 0.03, c), 0.03, seg=10)
                    for xx in (mn[0], mx[0] - 0.05):
                        cube(bm, (xx, ya, mn[2]), (xx + 0.05, yb, mx[2]))
                finish(n if k == 0 else f"{n}_{k}", bm, "Steel", smooth=True)
        elif n.startswith("decor_Facade_") and n.endswith(("_Door", "_Window")):
            bm = bmesh.new()                                 # a fake door or window on a facade: no back face (it is inside the facade)
            cube(bm, mn, mx)
            bm.normal_update()
            back = B((1, 0, 0) if SCENE == "market" else (0, 0, -1))
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.normal.dot(back) > 0.9], context="FACES")
            finish(n, bm, mat)
        elif n.startswith("Step_slide_chute"):
            bm = bmesh.new()
            bevel_box(bm, mn, mx, 0.03, 2)
            finish(n, bm, "Plastic_Blue")
        else:
            bm = bmesh.new()
            shape_box(bm, mn, mx, 0.02)
            finish(n, bm, mat, smooth=thin_axis(mn, mx) is not None)
    for p in GB.parts:
        play_part(p)


def extras():
    """What the greybox does not have and can be walked through: the slide's side rails, hopscotch, a sign over each gap, toys, flowers."""
    if SCENE == "playground":
        cx, cz = G.PLOTS["slide"]
        acc = Acc("decor_slide_sides")
        seg = 4.0 / 7
        for zs in (cz - 0.37, cz + 0.33):
            pts = [(cx + 4.2 - i * seg, 0.12 + 0.2 * i, zs) for i in range(8)]
            tube(acc.bm("Plastic_Yellow", True), [(x, y, z + 0.02) for x, y, z in pts], 0.035)
        acc.done()
        acc = Acc("decor_hopscotch")
        bm = acc.bm("Paint_White")
        for k, (x, z) in enumerate(((0, 0), (0.6, 0), (1.2, -0.3), (1.2, 0.3), (1.8, 0), (2.4, -0.3), (2.4, 0.3), (3.0, 0))):
            x0, z0 = -1.5 + x, z
            for (a0, a1, b0, b1) in ((x0, x0 + 0.5, z0 - 0.28, z0 - 0.24), (x0, x0 + 0.5, z0 + 0.24, z0 + 0.28),
                                     (x0, x0 + 0.04, z0 - 0.28, z0 + 0.28), (x0 + 0.46, x0 + 0.5, z0 - 0.28, z0 + 0.28)):
                quad(bm, a0, a1, b0, b1, 0.026)
        for k in range(12):                                        # a painted snake of dots along the path
            a = k / 11
            quad(acc.bm("Paint_Yellow"), 10 + a * 8 - 0.15, 10 + a * 8 + 0.15, 1.1 * math.sin(a * 2 * math.pi) - 0.15,
                 1.1 * math.sin(a * 2 * math.pi) + 0.15, 0.026)
        acc.done()
        toys = Acc("decor_toys")
        ellipsoid(toys.bm("Plastic_Red", True), (-18.0, 0.12, -9.0), 0.12, 0.12, 0.12, seg=12)                # a ball left on the grass
        ellipsoid(toys.bm("Plastic_Blue", True), (25.0, 0.18, 9.5), 0.18, 0.18, 0.18, seg=12)
        cyl(toys.bm("Plastic_Yellow", True), (-11.0, 0.02, 18.6), (-11.0, 0.16, 18.6), 0.08, 0.1, seg=10)          # a bucket in the sandbox
        toys.done()
        for k, (x, z) in enumerate(((-24.0, -30.0), (0.0, -27.0), (24.0, -30.0), (-24.0, 30.0), (0.0, 29.0), (24.0, 30.0)), 1):
            flower_bed(k, x, z)
        arch("E", G.PX + 0.6, "PLAYGROUND")
        arch("W", -G.PX - 0.6, "PLAYGROUND")
        arch_x("S", G.PZ + 0.6, "SPORTS", "PLAYGROUND")
    else:
        arch("W", -G.MX - 0.6, "MARKET")
    flowers()


def arch(side, xc, text):
    """A sign over a hedge gap: two posts standing in the hedge either side of the gap, a beam and a board above head height."""
    for k, zc in enumerate((-3.1, 3.1), 1):
        bm = bmesh.new()
        cyl(bm, (xc, 0.0, zc), (xc, 2.95, zc), 0.08, seg=12)
        finish(f"Arch_{side}_post_{k}", bm, "Steel", smooth=True)
    bm = bmesh.new()
    cube(bm, (xc - 0.08, 2.75, -3.18), (xc + 0.08, 2.9, 3.18))
    finish(f"Arch_{side}_beam", bm, "Steel")
    sign_obj(f"Arch_{side}_sign_in", (xc - 0.04, 2.92, -2.6), (xc, 3.52, 2.6), text, (-1, 0, 0) if xc > 0 else (1, 0, 0))
    sign_obj(f"Arch_{side}_sign_out", (xc, 2.92, -2.6), (xc + 0.04, 3.52, 2.6), text, (1, 0, 0) if xc > 0 else (-1, 0, 0))


def arch_x(side, zc, text_in, text_out, x0=0.0):
    """arch() over a 6 m gap in a north or south hedge (the gap along x, centred on x0): text_in faces into the scene, text_out out of it."""
    for k, xc in enumerate((x0 - 3.1, x0 + 3.1), 1):
        bm = bmesh.new()
        cyl(bm, (xc, 0.0, zc), (xc, 2.95, zc), 0.08, seg=12)
        finish(f"Arch_{side}_post_{k}", bm, "Steel", smooth=True)
    bm = bmesh.new()
    cube(bm, (x0 - 3.18, 2.75, zc - 0.08), (x0 + 3.18, 2.9, zc + 0.08))
    finish(f"Arch_{side}_beam", bm, "Steel")
    sg = 1 if zc > 0 else -1                                   # the side the hedge is on: +z for the south hedge
    sign_obj(f"Arch_{side}_sign_in", (x0 - 2.6, 2.92, min(zc, zc - sg * 0.04)), (x0 + 2.6, 3.52, max(zc, zc - sg * 0.04)), text_in, (0, 0, -sg))
    sign_obj(f"Arch_{side}_sign_out", (x0 - 2.6, 2.92, min(zc, zc + sg * 0.04)), (x0 + 2.6, 3.52, max(zc, zc + sg * 0.04)), text_out, (0, 0, sg))


def flower_bed(k, x, z, r=1.6):
    """A round bed in the lawn: a soil disc, a rim of white stones and flowers (decor: you walk through it)."""
    rng = np.random.default_rng(100 + k)
    acc = Acc(f"decor_bed_{k}")
    cyl(acc.bm("Soil"), (x, 0.0, z), (x, 0.03, z), r, seg=28)
    for a in range(24):
        t = 2 * math.pi * a / 24
        ellipsoid(acc.bm("Plastic_White", True), (x + (r + 0.05) * math.cos(t), 0.04, z + (r + 0.05) * math.sin(t)), 0.11, 0.07, 0.09, seg=8)
    for i in range(40):
        rr, t = r * 0.9 * math.sqrt(rng.random()), 2 * math.pi * rng.random()
        fx, fz = x + rr * math.cos(t), z + rr * math.sin(t)
        h = rng.uniform(0.3, 0.55)
        cube(acc.bm("Goods_Stem"), (fx - 0.012, 0.03, fz - 0.012), (fx + 0.012, h, fz + 0.012))
        col = ["Goods_Pink", "Goods_Yellow", "Goods_White", "Goods_Purple", "Goods_Red"][(i + k) % 5]
        ellipsoid(acc.bm(col, True), (fx, h + 0.04, fz), 0.08, 0.05, 0.08, seg=8)
    acc.done()


def flowers():
    """Clumps of flowers along the hedges' inner faces, clear of the gaps, the spots and the pieces (decor: knee high, passable)."""
    rng = np.random.default_rng(17 if SCENE == "playground" else 19)
    X, Z = (G.PX, G.PZ) if SCENE == "playground" else (G.MX, G.MZ)
    acc = Acc("decor_flowers")
    stems = acc.bm("Goods_Stem")
    keep = [e["pos"] for e in GB.empties]
    cols = [b for b in GB.boxes if b["col"] and not b["name"].startswith(("Ground_", "Hedge_", "Edge_"))]
    n = 0
    for _ in range(600):
        side = int(rng.integers(4))
        t = rng.uniform(-1, 1)
        x, z = ((t * (X - 2), -Z + 0.5) if side == 0 else (t * (X - 2), Z - 0.5) if side == 1 else (-X + 0.5, t * (Z - 2)) if side == 2
                else (X - 0.5, t * (Z - 2)))
        if abs(z) < 4.5 and abs(x) > X - 2:
            continue
        if SCENE == "playground" and z > Z - 2 and abs(x) < 4.5:        # the south gap to the sports courts
            continue
        if any(math.hypot(x - p[0], z - p[2]) < 1.6 for p in keep):
            continue
        if any(c["min"][0] - 0.6 < x < c["max"][0] + 0.6 and c["min"][2] - 0.6 < z < c["max"][2] + 0.6 for c in cols):
            continue
        col = ["Goods_Pink", "Goods_Yellow", "Goods_White", "Goods_Purple", "Awning_E"][n % 5]
        for k in range(5):
            fx, fz = x + rng.uniform(-0.25, 0.25), z + rng.uniform(-0.25, 0.25)
            h = rng.uniform(0.25, 0.45)
            cube(stems, (fx - 0.01, 0.0, fz - 0.01), (fx + 0.01, h, fz + 0.01))
            ellipsoid(acc.bm(col, True), (fx, h + 0.03, fz), 0.06, 0.04, 0.06, seg=8)
        n += 1
        if n >= 70:
            break
    acc.done()


# ---------------------------------------------------------------- the layout objects (from the greybox model)
LAYOUT_PREFIX = ("COL_", "DoorLeaf_", "Link_", "Arrive_", "Spot_", "Zone_", "Marker_", "Play_")


def gb_names():
    n = {"COL_" + b["name"] for b in GB.boxes if b["col"]} | {b["name"] for b in GB.boxes if b.get("zone")}
    return n | {e["name"] for e in GB.empties} | {p["name"] for p in GB.parts}


def build_layout():
    for b in GB.boxes:
        nm = "COL_" + b["name"] if b["col"] else b["name"] if b.get("zone") else None
        if nm is None:
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


# ---------------------------------------------------------------- the sky and the sun (renders only; the bake is AO)
def setup_world():
    sc = bpy.context.scene
    w = bpy.data.worlds.new("Overworld")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    bg.inputs["Color"].default_value = (0.50, 0.68, 1.0, 1)
    bg.inputs["Strength"].default_value = 1.0
    w.light_settings.distance = 2.0


def add_sun():
    if "Sun" in bpy.data.objects:
        return
    d = bpy.data.lights.new("Sun", "SUN")
    d.energy, d.color, d.angle = 3.2, (1.0, 0.96, 0.88), math.radians(2.0)
    ob = bpy.data.objects.new("Sun", d)
    ob.rotation_euler = (math.radians(42), 0, math.radians(-35))
    bpy.context.scene.collection.objects.link(ob)


# ================================================================ build
def build_all():
    global ART, PLAYC, LAYOUT_C
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for d in (IMG_CACHE, MATS, TILES):
        d.clear()
    sc = bpy.context.scene
    ART, PLAYC, LAYOUT_C = (bpy.data.collections.new(n) for n in ("Art", "Play", "Layout"))
    for c in (ART, PLAYC, LAYOUT_C):
        sc.collection.children.link(c)
    make_materials()
    build_boxes()
    extras()
    build_layout()
    setup_world()
    add_sun()
    LAYOUT_C.hide_render = True
    tris = sum(len(p.vertices) - 2 for c in (ART, PLAYC) for o in c.objects for p in o.data.polygons)
    print(f"ART {SCENE}: {len(ART.objects)} art objects, {len(PLAYC.objects)} moving parts, about {tris} triangles")


def open_collections():
    global ART, PLAYC, LAYOUT_C
    ART, PLAYC, LAYOUT_C = (bpy.data.collections.get(n) for n in ("Art", "Play", "Layout"))
    MATS.clear()
    for m in bpy.data.materials:
        MATS[m.name] = m


def stage_layout():
    import export_scene
    export_scene.write(SCENE, ROOT / f"world/{SCENE}.json")


def stage_check():
    import check_layout
    world = json.loads((ROOT / f"world/{SCENE}.json").read_text())
    parts = check_layout.blender_parts("Art")
    consts = {"links": {l["door"]: {"arrive": l["arrive"], "at": [l["at"][0], l["at"][2]]} for l in world["links"]}}
    print(f"layout check: scene {SCENE}, {len(parts)} visible meshes, {len(world['colliders'])} colliders (the Play collection skipped: moving parts)")
    bad = check_layout.report(check_layout.check(parts, world, consts))
    print(f"CHECK_LAYOUT {SCENE} exit", 1 if bad else 0)
    return bad


# ---------------------------------------------------------------- bake: ambient occlusion
GROUND = ["Grass", "Path", "Paving", "Rubber", "Sand", "Soil", "Hedge"]
NOT_BAKED = ("Lamp_Emit", "Paint_White", "Paint_Yellow")           # the lamps, and the painted lines (narrower than a texel)
PAGES = [2048, 2048]
AO_DIST = [1.5, 0.8]
AO_INTENSITY = 1.0


def groups(exp):
    g0 = [m for m in GROUND if m in exp]
    g1 = [m for m in exp if m not in GROUND and m not in NOT_BAKED and not m.startswith(("Goods_", "Play_"))]
    return [g0, g1]


def cull_hidden(bm):
    """Drop the faces never seen: the undersides of boxes standing on the ground."""
    bm.normal_update()
    bad = [f for f in bm.faces if f.normal.z < -0.9 and f.calc_center_median().z < 0.005]
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
        tmp.transform(ob.matrix_world)
        cull_hidden(tmp)
        me = bpy.data.meshes.new("tmp")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    out = {}
    for mname, bm in by_mat.items():
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
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces = 6, 4, 2
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
    for o in objs:
        uvs = o.data.uv_layers
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.new(name="lightmap", do_init=False)
        uvs.active = uvs["lightmap"]
        uvs["UVMap"].active_render = True
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / page, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    a3 = sum(area3d(o) for o in objs)
    au = sum(uv_area(o, "lightmap") for o in objs)
    dens = page * math.sqrt(au / max(a3, 1e-9))
    print(f"  page {page}: {a3:.1f} m2, {dens:.1f} px/m")
    return dens


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
    path = str(work_dir() / "dn.exr")
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


def bake_ao(n, objs, S, dist):
    import time
    t0 = time.time()
    bpy.context.scene.world.light_settings.distance = dist
    img = bpy.data.images.new(f"AO_{n}", S, S, alpha=False, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    mats = [o.data.materials[0] for o in objs]
    for m in mats:
        nt = m.node_tree
        node = nt.nodes.new("ShaderNodeTexImage")
        node.name = "BAKE_TARGET"
        node.image = img
        nt.nodes.active = node
        node.select = True
    select_only(objs)
    for o in objs:
        o.data.uv_layers.active = o.data.uv_layers["lightmap"]
    bpy.ops.object.bake(type="AO", margin=MARGIN_PX, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
    for o in objs:
        o.data.uv_layers.active = o.data.uv_layers["UVMap"]
    for m in mats:
        nt = m.node_tree
        for nd in [nd for nd in nt.nodes if nd.name.startswith("BAKE_TARGET")]:
            nt.nodes.remove(nd)
    a = denoise_image(img, S)
    bpy.data.images.remove(img)
    ao = np.clip(a[..., :3].mean(axis=2), 0, 1)
    lit = ao[ao > 1e-4]
    pc = np.percentile(lit, [1, 10, 50, 90]) if lit.size else [1.0] * 4
    out = np.ones((S, S, 4), np.float32)
    out[..., 0] = out[..., 1] = out[..., 2] = ao                      # linear AO (the page loads it with NoColorSpace)
    png = bpy.data.images.new(f"AO_{n}_png", S, S, alpha=False)
    png.colorspace_settings.name = "Non-Color"
    png.pixels.foreach_set(out.ravel())
    png.filepath_raw = str(work_dir() / f"{SCENE}_{n}.png")
    png.file_format = "PNG"
    png.save()
    bpy.data.images.remove(png)
    for m in mats:
        m["aomap"] = f"world/lightmaps/{SCENE}_{n}.webp"
        m["aomap_intensity"] = AO_INTENSITY
    rep = {"size": S, "p1_p10_p50_p90": [round(float(v), 3) for v in pc], "samples": SAMPLES, "distance_m": dist,
           "device": bpy.context.scene.cycles.device, "seconds": round(time.time() - t0), "materials": [m.name for m in mats]}
    print(f"  AO map {n} baked", rep)
    return rep


def stage_bake():
    exp = make_export_objects()
    bpy.data.collections["Art"].hide_render = True
    bpy.data.collections["Art"].hide_viewport = True
    bpy.data.collections["Layout"].hide_render = True
    setup_world()
    setup_cycles(SAMPLES, bake=True)
    report = {}
    for n, mats in enumerate(groups(exp)):
        objs = [exp[m] for m in mats]
        print(f"AO map {n}: {mats}")
        dens = lightmap_uv(objs, PAGES[n])
        report[n] = bake_ao(n, objs, PAGES[n], AO_DIST[n])
        report[n]["px_per_m"] = round(dens, 1)
    (work_dir() / "aomaps.json").write_text(json.dumps(report, indent=1))
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Art"].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


# ---------------------------------------------------------------- privacy: the saved file and the GLB carry no paths, names or stamps
KEEP_PROPS = {"aomap", "aomap_intensity"}
SYS_KEEP = ("cycles", "eevee")


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private():
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
                    if kind == "objects" and st is idb and idb.name.startswith(LAYOUT_PREFIX):
                        continue
                    if st is not idb and k.startswith(SYS_KEEP):
                        continue
                    try:
                        del st[k]
                        dropped += 1
                    except Exception as e:
                        print("  could not drop custom property", idb.name, k, e)
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
    for scr in bpy.data.screens:
        for a in scr.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"_" * 1000
                    sp.params.directory = b"//"
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
                except Exception:
                    pass
    return dropped


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    scrub_private()
    bpy.ops.wm.save_mainfile(compress=True)


# ---------------------------------------------------------------- export
def stage_export():
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    bpy.data.collections["Art"].hide_viewport = True
    parts = sorted(bpy.data.collections["Play"].objects, key=lambda o: o.name)
    bpy.ops.object.select_all(action="DESELECT")
    for o in list(exp.objects) + parts:
        o.hide_set(False)
        o.hide_render = False
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = work_dir() / f"{SCENE}_raw.glb"
    scrub_private()
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False, export_animations=False)
    print("EXPORTED", raw, raw.stat().st_size)
    bpy.data.collections["Art"].hide_viewport = False
    exp.hide_viewport = exp.hide_render = True
    save_blend()


# ---------------------------------------------------------------- the review stills
def look_cam(name, loc, target, fov_v=60.0, ortho=None):
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
    e = {x["name"]: x for x in GB.empties}
    a = e["Arrive_lot"]["pos"]
    f = e["Arrive_lot"]["face"]
    arr = ((a[0], 1.55, a[2]), (a[0] + f[0] * 20, 1.0, a[2] + f[1] * 20), 62.0)
    if SCENE == "playground":
        return {"1_arrival": arr, "2_wide": ((44.0, 9.0, 30.0), (0.0, 0.0, -6.0), 58.0),
                "3_detail": ((31.0, 1.6, -15.2), (36.0, 0.5, -20.0), 58.0), "5_swing": ((-30.5, 1.6, -13.5), (-36.0, 1.2, -20.0), 55.0)}
    return {"1_arrival": arr, "2_wide": ((-26.0, 8.0, 18.0), (6.0, 0.0, -6.0), 60.0), "3_detail": ((-6.0, 1.6, -9.5), (-1.0, 1.2, -18.0), 55.0),
            "5_food": ((12.5, 1.6, -9.0), (16.0, 1.0, -18.0), 55.0)}


def stage_render():
    sc = bpy.context.scene
    STILLS.mkdir(parents=True, exist_ok=True)
    scrub_private()
    for c in ("Export", "Layout"):
        if c in bpy.data.collections:
            bpy.data.collections[c].hide_render = True
            bpy.data.collections[c].hide_viewport = True
    bpy.data.collections["Art"].hide_render = False
    setup_world()
    add_sun()
    setup_cycles(arg("--render-samples", 96, int))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = arg("--noise", 0.04, float)
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
    cams = {k: look_cam(k, p, t, f) for k, (p, t, f) in shots().items()}
    X, Z = (G.PX, G.PZ) if SCENE == "playground" else (G.MX, G.MZ)
    plan = look_cam("4_plan", (0.0, 120.0, 0.0), None, ortho=2 * X + 6)
    plan.rotation_euler = (0, 0, 0)
    todo = [(k, v, (1920, 1080)) for k, v in cams.items()] + [("4_plan", plan, (1600, int(1600 * (2 * Z + 6) / (2 * X + 6))))]
    for key, cam, (w, h) in todo:
        if which not in ("all", key):
            continue
        sc.camera = cam
        sc.view_settings.exposure = expo
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, arg("--scale", 100, int)
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        to_docs = key in ("1_arrival", "2_wide", "3_detail")
        path = STILLS / f"{key}.jpg" if to_docs else work_dir() / f"{key}.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 450_000 and q > 40 and to_docs:
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        strip_jpeg_comments(path)
        print("STILL", SCENE, key, path.name, path.stat().st_size, "q", q)


# ================================================================ main
if __name__ == "__main__":
    ST = set(STAGE.split(","))
    summary = []
    import traceback
    failed = []
    for sid in scene_list():
        try:
            setup(sid)
            print(f"=== {sid}: stages {sorted(ST)}")
            if ST & {"art"}:
                build_all()
                save_blend()
            else:
                bpy.ops.wm.open_mainfile(filepath=str(BLEND))
                open_collections()
            if ST & {"layout", "art"}:
                stage_layout()
            if ST & {"check", "art"}:
                summary.append((sid, "check", stage_check()))
            if ST & {"bake"}:
                stage_bake()
            if ST & {"export"}:
                stage_export()
            if ST & {"render"}:
                stage_render()
        except Exception:
            traceback.print_exc()
            failed.append(sid)
    for s in summary:
        print("SUMMARY", *s)
    print("OVERWORLD_PLAY ALL DONE", "failed:", failed or "none")
    sys.exit(1 if failed else 0)
