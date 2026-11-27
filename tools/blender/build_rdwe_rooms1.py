"""Dresses and lights the first fifteen Phase C rooms of Right Door, Wrong Exit (docs/BLENDER_AREAS.md, section 7, step 2; one line each in
docs/renders/rdwe_greybox/ROOMS.md): the house (rdwe_long_table, rdwe_tiny_kitchen, rdwe_birthday_party, rdwe_attic, rdwe_kids_bedroom,
rdwe_giant_chair, rdwe_upside_room) and the halls (rdwe_door_hall, rdwe_stretching_hall, rdwe_bending_hall, rdwe_stair_loop, rdwe_tilted_hall,
rdwe_three_doors, rdwe_painted_door, rdwe_anamorphic_room), on their greybox layouts (tools/blender/build_rdwe_greybox.py) exactly.
docs/renders/rdwe_rooms1/README.md covers all fifteen.

    blender -b --factory-startup --python tools/blender/build_rdwe_rooms1.py -- --scenes rdwe_long_table[,...] --stage all [--samples 512]
    blender -b --factory-startup --python tools/blender/build_rdwe_rooms1.py -- --scenes <scene> --stage bake|export|check|render (from the .blend)
    python tools/blender/build_rdwe_rooms1.py --encode <scene> [--gain G]    (no Blender: the raw bake -> lightmap PNGs again)
    python tools/blender/pack_scene.py <scene> --work work/rdwe_rooms1     (no Blender: WebP lightmaps and textures -> world/)
    python tools/blender/build_rdwe_rooms1.py --caps <scene>               (no Blender: caps.json's factors into world/<scene>.glb)

The method is the hotel's (tools/blender/build_hotel_pools.py): stages art (the layout objects from the greybox model, the shell as seen, the
dressing, the lights; saves blender/scenes/<scene>.blend) -> bake (the shell, the props and the trick objects on fixed lightmap PAGES, Cycles,
OIDN; the light L written with a shoulder, texel = G L / (C + G L), lightmap_intensity = pi C) -> export (the GLB to the work folder; the layout
through tools/blender/export_scene.py) -> axes -> check (tools/blender/check_layout.py) -> render (docs/renders/<scene>/1_arrival, 2_wide,
3_detail.jpg and the plan to the work folder).

The layout is the greybox's: every COL_ box, DoorLeaf_ (with its `look`), Link_/Arrive_, Marker_, Zone_ and Spot_ comes from
build_rdwe_greybox.build(<scene>), so export_scene.py writes the same world/<scene>.json as `build_rdwe_greybox.py --preview`. The shell as seen
is made from the greybox's shell boxes (each face cut into pieces of 4 m at most, a piece kept when the air in front of it is inside the room and
in no other shell box); every box the greybox tags `f` (furniture) gets a dressed prop that covers it. Every door leaf is its own mesh, made from
its `look` (form, finish, handle), so no two doors look alike.

The trick objects (the long table's growing chairs, the upside room's hanging furniture, the painted door and the wall that hides the real one,
the anamorphic shards and the wall over the north door, the bending hall's cover over the lap door) are their own objects, named Trick_<what>
(solid) or decor_Trick_<what> (passable), with their own materials (<material>_T) on their own lightmap page; the room's own pages are baked
with them hidden, so no shadow of theirs is baked where they move. The shards glow (Shard_Glow, emissive, not baked).

Light: baked indoors on UV1 (`lightmap`). Not baked: Lamp_Emit (the page's lamps), Window_Lit (windows), Stars_Glow (the bedroom's glow stars),
Shard_Glow, Void (the black past every door), Glass_Clear. Textures: CC0 from Poly Haven, already in the repo (blender/textures/apartment,
galleries, laboratory), and patterns generated here (numpy, fixed seeds, own work).
"""
import json
import math
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import build_rdwe_greybox as GB  # noqa: E402

try:
    import bpy
    import bmesh
    from mathutils import Matrix, Vector
except ImportError:
    bpy = None
import numpy as np  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 512, int)
DEVICE = arg("--device", "auto")
MARGIN_PX = 8
TEXDIR = ROOT / "blender/textures"
SCENE = None
SCENES = ["rdwe_long_table", "rdwe_tiny_kitchen", "rdwe_birthday_party", "rdwe_attic", "rdwe_kids_bedroom", "rdwe_giant_chair", "rdwe_upside_room",
          "rdwe_door_hall", "rdwe_stretching_hall", "rdwe_bending_hall", "rdwe_stair_loop", "rdwe_tilted_hall", "rdwe_three_doors",
          "rdwe_painted_door", "rdwe_anamorphic_room"]
PAGES = {s: [2048, 2048, 1024] for s in SCENES}
for _s in ("rdwe_kids_bedroom", "rdwe_attic", "rdwe_three_doors", "rdwe_upside_room", "rdwe_painted_door"):
    PAGES[_s][0] = 1536
CURVE_C = 1.12               # texel = G L / (C + G L), intensity = pi C: the page shows albedo x G L, rolling off toward albedo x C near a lamp
GAIN_TARGET = 1.45           # G = GAIN_TARGET / the median light on the shell
NO_LIGHTMAP = {"Lamp_Emit", "Window_Lit", "Stars_Glow", "Shard_Glow", "Void", "Glass_Clear"}
NO_BAKE_VIS = {"Glass_Clear"}
FURN_EXTRA = {"rdwe_giant_chair": ("Step_cushions", "Fill_cushions")}     # greybox boxes dressed as props though not tagged `f`


def work():
    p = Path(arg("--work", str(ROOT / "work/rdwe_rooms1")))
    p.mkdir(parents=True, exist_ok=True)
    return p


def raw_dir():
    p = Path(arg("--raw-dir", str(work() / "raw")))
    p.mkdir(parents=True, exist_ok=True)
    return p


def world_json(sc):
    return ROOT / f"world/{sc}.json"


def glb_path(sc):
    return ROOT / f"world/{sc}.glb"


def blend_path(sc):
    return ROOT / f"blender/scenes/{sc}.blend"


def stills_dir(sc):
    return ROOT / f"docs/renders/{sc}"


def lm_url(sc, n):
    return f"world/lightmaps/{sc}_{n}.webp"


def srgb_encode(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def encode(rgb, gain):
    return srgb_encode(gain * rgb / (CURVE_C + gain * rgb))


# ================================================================ plain Python (no Blender): encode, caps
def stage_encode(sc):
    from PIL import Image
    rep_p = stills_dir(sc) / "bake.json"
    rep = json.loads(rep_p.read_text())
    gain = arg("--gain", None, float) or rep["0"]["gain"]
    for f in sorted(raw_dir().glob(f"{sc}_[0-9]_raw.npy")):
        n = f.name.split("_")[-2]
        rgb = np.load(f).astype(np.float32)
        Image.fromarray((np.flipud(encode(rgb, gain)) * 255 + 0.5).astype(np.uint8)).save(work() / f"{sc}_{n}.png")
        rep[n]["gain"] = round(gain, 4)
        print("ENCODED", f"{sc}_{n}.png", rgb.shape, "gain", gain)
    rep_p.write_text(json.dumps(rep, indent=1))


def apply_caps(sc):
    """caps.json's factors on each material's lightmap_intensity, written into the packed GLB's JSON chunk (the uncapped value is pi C)."""
    import struct
    p = glb_path(sc)
    b = p.read_bytes()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    rest = b[20 + n:]
    cj = json.loads((stills_dir(sc) / "caps.json").read_text())
    f = cj.get("factor", {})
    for m in j["materials"]:
        ex = m.get("extras", {})
        if "lightmap_intensity" in ex:
            ex["lightmap_intensity"] = round(math.pi * CURVE_C * f.get(m["name"], 1.0), 4)
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    out = b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + len(rest)) + struct.pack("<I", len(js)) + b"JSON" + js + rest
    p.write_bytes(out)
    print("CAPS written into", p.name, f)


if bpy is None:
    if "--encode" in args:
        for s in arg("--encode").split(","):
            stage_encode(s)
    elif "--caps" in args:
        apply_caps(arg("--caps"))
    else:
        print(__doc__)
    sys.exit(0)


# ================================================================ Blender from here on
def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


def srgb_lin(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


# ---------------------------------------------------------------- generated images (own work: numpy, fixed seeds)
def vnoise(h, w, rng, octaves=5, base=4):
    out = np.zeros((h, w))
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        ny = base * 2 ** o
        nx = max(1, int(round(ny * w / h)))
        g = rng.random((ny, nx))
        ys, xs = np.arange(h) * ny / h, np.arange(w) * nx / w
        y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
        fy, fx = ys - y0, xs - x0
        fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
        y1, x1 = (y0 + 1) % ny, (x0 + 1) % nx
        a, b, c, d = g[y0][:, x0], g[y0][:, x1], g[y1][:, x0], g[y1][:, x1]
        v = (a * (1 - fx) + b * fx) * (1 - fy)[:, None] + (c * (1 - fx) + d * fx) * fy[:, None]
        out += v * amp
        tot += amp
        amp *= 0.55
    return out / tot


def C(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


def lerp(a, b, t):
    t = np.asarray(t)[..., None] if np.ndim(t) else t
    return a * (1 - t) + b * t


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def grid(n):
    Y, X = np.mgrid[0:n, 0:n] / n
    return X, Y


def gen_shag(seed, a, b, c, n=512):
    """A deep shag pile: fine fibre noise over a slow swirl, three greens."""
    rng = np.random.default_rng(seed)
    fib = rng.random((n, n))
    fib = (fib + np.roll(fib, 1, 0) + np.roll(fib, 1, 1) + np.roll(fib, (1, 1), (0, 1))) / 4
    slow = vnoise(n, n, rng, 4, 3)
    t = np.clip(0.5 + (fib - 0.5) * 1.6 + (slow - 0.5) * 0.8, 0, 1)
    return np.clip(lerp(lerp(C(a), C(b), smooth(0.0, 0.6, t)), C(c), smooth(0.6, 1.0, t)), 0, 1)


def gen_swirl(seed, ground, ink1, ink2, n=512):
    """The dining room's paper: cream, with soft paisley swirls in pink and mint that seem to turn as you look (psychedelic, slightly wrong)."""
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    w = vnoise(n, n, rng, 4, 2)
    r = np.hypot(np.mod(X * 3, 1) - 0.5, np.mod(Y * 3, 1) - 0.5)
    th = np.arctan2(np.mod(Y * 3, 1) - 0.5, np.mod(X * 3, 1) - 0.5)
    sw = 0.5 + 0.5 * np.sin(th * 3 + r * 26 + w * 6)
    band = smooth(0.82, 0.95, sw) * smooth(0.48, 0.3, r)
    band2 = smooth(0.85, 0.97, 0.5 + 0.5 * np.sin((X + Y) * 2 * math.pi * 6 + w * 5))
    base = lerp(C(ground), C(ground) * 0.93, vnoise(n, n, rng, 5, 8))
    out = lerp(base, C(ink1), band * 0.55)
    return np.clip(lerp(out, C(ink2), band2 * 0.35 * (1 - band)), 0, 1)


def gen_plaid(seed, n=512):
    """The hallway's printed plaid, grey-beige, with violet and lime threads gone a little too bright."""
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    base = lerp(C("#c9c1ae"), C("#bcb39e"), vnoise(n, n, rng, 4, 6))
    out = base.copy()
    for period, width, col, k in ((0.5, 0.06, "#8f8676", 0.45), (0.25, 0.012, "#7a3fb8", 0.55), (0.5, 0.01, "#9ee03a", 0.45)):
        dx = np.abs(np.mod(X + period / 2, period) - period / 2) < width
        dy = np.abs(np.mod(Y + period / 2, period) - period / 2) < width
        m = (dx | dy).astype(float) * (1 + ((dx & dy).astype(float)))
        out = lerp(out, C(col), np.clip(m * k, 0, 0.9))
    return np.clip(out, 0, 1)


def gen_diamond_carpet(seed, n=512):
    """The hallway's worn tan carpet with a lattice of dark diamonds."""
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    base = lerp(C("#a98552"), C("#8e6c3e"), vnoise(n, n, rng, 5, 6))
    base = lerp(base, C("#c49a5e"), smooth(0.7, 1.0, rng.random((n, n))) * 0.3)
    d = np.abs(np.mod(X * 4, 1) - 0.5) + np.abs(np.mod(Y * 4, 1) - 0.5)
    line = smooth(0.06, 0.0, np.abs(d - 0.45))
    dot = smooth(0.08, 0.02, d)
    return np.clip(lerp(lerp(base, C("#4a2e1a"), line * 0.8), C("#b03a8a"), dot * 0.8), 0, 1)


def gen_pixels(seed, n=256, cells=16):
    """Mossy pixel-block stone: square cells of greys and greens."""
    rng = np.random.default_rng(seed)
    pal = [C(h) for h in ("#5e6a52", "#4c5a40", "#6f7c5c", "#3f6a2c", "#5aa03a", "#7c8a6a", "#2f4a24", "#8cd04a")]
    cell = rng.integers(0, len(pal), (cells, cells))
    cell = np.where(rng.random((cells, cells)) < 0.25, 4 + rng.integers(0, 4, (cells, cells)), cell)
    img = np.array([[pal[cell[i * cells // n, j * cells // n]] for j in range(n)] for i in range(n)])
    gx = (np.arange(n) % (n // cells) == 0)
    img[gx, :] *= 0.6
    img[:, gx] *= 0.6
    return np.clip(img, 0, 1)


def gen_fleck(seed, dark, n=512):
    """The teal rooms' coarse brown flecked carpet."""
    rng = np.random.default_rng(seed)
    a, b = (C("#5a3f28"), C("#2c1d12")) if dark else (C("#6b4b30"), C("#3a2718"))
    base = lerp(a, b, vnoise(n, n, rng, 5, 8) * 0.8)
    out = base.copy()
    for h, p in (("#cdb48c", 0.06), ("#17110b", 0.08), ("#e8743a", 0.03), ("#3dd6c8", 0.015)):
        m = rng.random((n, n)) < p
        out[m] = C(h)
    return np.clip(out, 0, 1)


def gen_tiles(seed, cols, a, b, grout, gw, n=512):
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    ci, cj = np.floor(X * cols).astype(int), np.floor(Y * cols).astype(int)
    pick = rng.random((cols, cols))
    t = lerp(C(a), C(b), pick[cj, ci])
    t = lerp(t, t * 0.94, vnoise(n, n, rng, 4, 8) * 0.6)
    fx, fy = np.mod(X * cols, 1), np.mod(Y * cols, 1)
    g = (np.minimum(fx, 1 - fx) < gw * cols / 2) | (np.minimum(fy, 1 - fy) < gw * cols / 2)
    t[g] = C(grout)
    return np.clip(t, 0, 1)


def gen_sky(seed, w=2048, h=512):
    """The flooded corridor's painted sky: a saturated blue, fat cumulus, a green hill line, a strip of yellow flowers; tiles along u."""
    rng = np.random.default_rng(seed)
    Y, X = np.mgrid[0:h, 0:w]
    y, x = Y / h, X / w
    sky = lerp(C("#2a6dff"), C("#8fd0ff"), smooth(0.0, 0.75, y))
    cl = vnoise(h, w, rng, 5, 3)
    cloud = smooth(0.55, 0.7, cl * (1 - smooth(0.25, 0.75, y)) + 0.25 * (1 - y))
    sky = lerp(sky, C("#fff6f0"), cloud)
    sky = lerp(sky, C("#ffb0e0"), smooth(0.75, 0.9, cl) * cloud * 0.4)
    hill = 0.78 + 0.06 * np.sin(x * 2 * math.pi * 2 + 1.3) + 0.03 * np.sin(x * 2 * math.pi * 5)
    g = y > hill
    grass = lerp(C("#3fbf3a"), C("#1f7a2a"), smooth(0.0, 1.0, (y - hill) * 6))
    sky[g] = grass[g]
    fl = (y > 0.93) & (rng.random((h, w)) < 0.05)
    sky[fl] = C("#ffe23a")
    return np.clip(sky, 0, 1)


def gen_photos(seed, n=1024, k=4):
    """The photo wall: a 4 x 4 atlas of family snapshots, blurred figures on saturated grounds, every face missing."""
    rng = np.random.default_rng(seed)
    img = np.zeros((n, n, 3))
    s = n // k
    grounds = ["#e7a35a", "#6ab0d8", "#c46aa8", "#8cc46a", "#d8c46a", "#6a8cd8", "#d86a6a", "#6ad8b8"]
    for i in range(k):
        for j in range(k):
            Y, X = np.mgrid[0:s, 0:s] / s
            g = lerp(C(rng.choice(grounds)), C(rng.choice(grounds)), smooth(0.2, 1.0, Y))
            for f in range(rng.integers(1, 4)):
                cx, w = 0.2 + 0.6 * rng.random(), 0.12 + 0.08 * rng.random()
                body = (np.abs(X - cx) < w * (0.6 + Y)) & (Y > 0.45)
                head = np.hypot(X - cx, Y - 0.33) < w * 0.75
                col = C(rng.choice(["#3a2a24", "#5a4434", "#2a3a5a", "#6a2a3a"]))
                g[body] = col
                g[head] = C("#f0dcc4")
            g = lerp(g, C("#f4ead8"), 0.15)
            img[i * s:(i + 1) * s, j * s:(j + 1) * s] = g
    return np.clip(img, 0, 1)


def gen_grid(n=256):
    """The glowing green grid under the peeled wallpaper."""
    X, Y = grid(n)
    f = 8
    d = np.minimum(np.minimum(np.mod(X * f, 1), 1 - np.mod(X * f, 1)), np.minimum(np.mod(Y * f, 1), 1 - np.mod(Y * f, 1)))
    v = smooth(0.08, 0.0, d)
    out = np.zeros((n, n, 3))
    out[..., 1] = 0.08 + 0.92 * v
    out[..., 0] = 0.05 * v
    out[..., 2] = 0.2 * v
    return out


def gen_quilt(seed, a, b, n=512, cells=4):
    """Padded vinyl: square pads with dark seams and a soft highlight (the trampoline park's walls and frames)."""
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    fx, fy = np.mod(X * cells, 1), np.mod(Y * cells, 1)
    edge = np.minimum(np.minimum(fx, 1 - fx), np.minimum(fy, 1 - fy))
    pad = smooth(0.0, 0.18, edge)
    base = lerp(C(b), C(a), pad)
    return np.clip(lerp(base, base * 0.9, vnoise(n, n, rng, 4, 8) * 0.5), 0, 1)


def gen_weave(seed, n=256):
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    w = 0.5 + 0.5 * np.sin(X * 2 * math.pi * 32) * np.sin(Y * 2 * math.pi * 32)
    base = lerp(C("#141416"), C("#2a2a30"), w * 0.7 + vnoise(n, n, rng, 3, 8) * 0.3)
    return np.clip(base, 0, 1)


def gen_speckle(seed, a, b, n=512):
    """Glossy speckled vinyl tile in big pastel squares (the grocery)."""
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    ck = ((np.floor(X * 4) + np.floor(Y * 4)) % 2).astype(float)
    base = lerp(C(a), C(b), ck)
    sp = rng.random((n, n))
    base[sp < 0.03] *= 0.7
    base[(sp > 0.97)] = base[(sp > 0.97)] * 0.5 + 0.5 * C("#ff4fa0")
    fx, fy = np.mod(X * 4, 1), np.mod(Y * 4, 1)
    g = (np.minimum(fx, 1 - fx) < 0.004) | (np.minimum(fy, 1 - fy) < 0.004)
    base[g] *= 0.85
    return np.clip(base, 0, 1)


def gen_rings(seed, n=512):
    """The dining room's round rug: concentric rings in pink, orange, teal and cream, a little off-centre and wobbling."""
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    r = np.hypot(X - 0.5, Y - 0.5) * 2 + 0.03 * (vnoise(n, n, rng, 3, 3) - 0.5)
    pal = np.array([C(h) for h in ("#ff5aa8", "#ff9a3a", "#2ad0c0", "#fff0d0", "#8a4ad8")])
    k = np.floor(r * 9).astype(int) % len(pal)
    out = pal[k]
    edge = np.abs(np.mod(r * 9, 1) - 0.5) > 0.46
    out[edge] *= 0.8
    return np.clip(out, 0, 1)


def gen_brushed(n=256):
    rng = np.random.default_rng(5)
    v = rng.random((n, 1)) * 0.5 + rng.random((n, n)) * 0.1
    return np.repeat(np.clip(0.75 + 0.25 * (v - 0.3), 0, 1)[..., None], 3, axis=2)


def gen_concrete(seed, n=512):
    rng = np.random.default_rng(seed)
    v = vnoise(n, n, rng, 6, 4)
    base = lerp(C("#8e8a82"), C("#6e6a64"), v)
    base[rng.random((n, n)) < 0.01] *= 0.8
    return np.clip(base, 0, 1)


GEN = {}


def mk_image(name, arr):
    h, w = arr.shape[:2]
    im = bpy.data.images.new(name, w, h, alpha=False)
    im.colorspace_settings.name = "sRGB"
    px = np.ones((h, w, 4), np.float32)
    px[..., :3] = arr[::-1, :, :3]                      # numpy's row 0 is the top; Blender's is the bottom
    im.pixels.foreach_set(px.ravel())
    im.filepath_raw = f"//generated/{name}.png"
    im.file_format = "PNG"
    im.pack()
    GEN[name] = im
    return im


# ---------------------------------------------------------------- materials
IMG, MATS, TILES = {}, {}, {}


def image(rel):
    if rel not in IMG:
        im = bpy.data.images.load(str(TEXDIR / rel))
        im.colorspace_settings.name = "sRGB"
        IMG[rel] = im
    return IMG[rel]


def set_blend(m):
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(m, attr, val)
        except (AttributeError, TypeError):
            pass


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, tex=None, img=None, tint=None, emit=None, alpha=None, tile=1.0):
    """A Principled material; `tint` multiplies the texture (a Mix node set to Multiply: the glTF exporter writes it as baseColorFactor)."""
    if name in MATS:
        return MATS[name]
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
    if tex or img:
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "UVMap"
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = img or image(tex)
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
        set_blend(m)
    TILES[name] = tile
    MATS[name] = m
    return m



# ---------------------------------------------------------------- more generated images (own work: numpy, fixed seeds)
def gen_stripes(seed, cols, widths, n=512, noise=0.06):
    """Vertical stripes (wallpaper): cols cycle with the given widths (fractions of the tile)."""
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    edges = np.cumsum([0.0] + list(widths))
    edges = edges / edges[-1]
    out = np.zeros((n, n, 3))
    for i in range(len(widths)):
        m = (X >= edges[i]) & (X < edges[i + 1])
        out[m] = C(cols[i % len(cols)])
    return np.clip(lerp(out, out * (1 - noise), vnoise(n, n, rng, 4, 8)), 0, 1)


def gen_checker(seed, a, b, cells=4, n=512, grout="#888888", gw=0.004):
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    ck = ((np.floor(X * cells) + np.floor(Y * cells)) % 2).astype(float)
    base = lerp(C(a), C(b), ck)
    base = lerp(base, base * 0.92, vnoise(n, n, rng, 4, 8) * 0.5)
    fx, fy = np.mod(X * cells, 1), np.mod(Y * cells, 1)
    g = (np.minimum(fx, 1 - fx) < gw * cells) | (np.minimum(fy, 1 - fy) < gw * cells)
    base[g] = C(grout)
    return np.clip(base, 0, 1)


def gen_books(seed, n=512, rows=4):
    """A shelf of book spines: rows of upright spines in saturated colours with a gold band or two (u along the shelf, v up)."""
    rng = np.random.default_rng(seed)
    pal = [C(h) for h in ("#b8283a", "#2a5ab8", "#2a8a4a", "#e0b030", "#7a3ab0", "#e86a2a", "#1a1a2a", "#f0e6cc", "#3ab0b0", "#c8507a")]
    img = np.zeros((n, n, 3))
    rh = n // rows
    for r in range(rows):
        x = 0
        while x < n:
            w = int(rng.integers(10, 30))
            col = pal[int(rng.integers(0, len(pal)))]
            top = int(rh * rng.uniform(0.0, 0.22))
            sl = img[r * rh + top:(r + 1) * rh, x:x + w]
            sl[:] = col * rng.uniform(0.75, 1.0)
            for bnd in (0.2, 0.75):
                y0 = int((rh - top) * bnd)
                sl[y0:y0 + 3] = C("#d8b048")
            sl[:, :1] *= 0.5
            x += w
        img[r * rh:r * rh + 3] = C("#3a2414")
    return np.clip(img[::-1], 0, 1)


def gen_cardboard(seed, n=256):
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    base = lerp(C("#b08858"), C("#9a7448"), vnoise(n, n, rng, 4, 6))
    flute = 0.5 + 0.5 * np.sin(Y * 2 * math.pi * 40)
    return np.clip(lerp(base, base * 0.93, flute * 0.3), 0, 1)


def gen_clouds(seed, n=512):
    """The bedroom's wallpaper: soft white clouds on sky blue, a few yellow stars."""
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    base = lerp(C("#78c8f0"), C("#5ab0e8"), Y)
    cl = vnoise(n, n, rng, 5, 3)
    out = lerp(base, C("#f4f8ff"), smooth(0.55, 0.68, cl))
    for _ in range(24):
        cx, cy, r = rng.random(), rng.random(), 0.012
        d = np.hypot(np.mod(X - cx + 0.5, 1) - 0.5, np.mod(Y - cy + 0.5, 1) - 0.5)
        out[d < r] = C("#ffe060")
    return np.clip(out, 0, 1)


def gen_posters(seed, n=1024, k=2):
    """Four posters (2 x 2 atlas): a rocket, a planet, a dinosaur's silhouette, a smiling sun, flat 90s colours."""
    rng = np.random.default_rng(seed)
    img = np.zeros((n, n, 3))
    s = n // k
    Y, X = np.mgrid[0:s, 0:s] / s
    grounds = [("#1a2a6a", "#ff7a30"), ("#2a1a4a", "#f0d040"), ("#2a8a5a", "#f4e6c0"), ("#40b0f0", "#ffe040")]
    for i in range(k):
        for j in range(k):
            g0, g1 = grounds[i * k + j]
            t = lerp(C(g0), C(g0) * 0.7, Y)
            idx = i * k + j
            if idx == 0:
                m = (np.abs(X - 0.5) < 0.09 * (1 - np.clip((0.3 - Y) / 0.15, 0, 1))) & (Y > 0.15) & (Y < 0.7)
                t[m] = C("#f0f0f0")
                t[(np.abs(X - 0.5) < 0.05) & (Y > 0.7) & (Y < 0.85)] = C(g1)
            elif idx == 1:
                d = np.hypot(X - 0.5, Y - 0.5)
                t[d < 0.25] = C(g1)
                t[(np.abs(d - 0.36) < 0.02) & (np.abs(Y - 0.5) < 0.12)] = C("#ff5ab0")
            elif idx == 2:
                m = ((np.hypot(X - 0.45, (Y - 0.55) * 1.6) < 0.22) | ((np.abs(X - 0.75) < 0.05) & (Y > 0.25) & (Y < 0.55))
                     | (np.hypot(X - 0.78, Y - 0.22) < 0.08))
                t[m] = C("#1a3a2a")
            else:
                d = np.hypot(X - 0.5, Y - 0.5)
                t[d < 0.22] = C(g1)
                t[(d > 0.26) & (d < 0.36) & (np.mod(np.arctan2(Y - 0.5, X - 0.5) * 6 / math.pi, 1) < 0.4)] = C(g1)
            t[:6], t[-6:], t[:, :6], t[:, -6:] = C("#f4f0e8"), C("#f4f0e8"), C("#f4f0e8"), C("#f4f0e8")
            img[i * s:(i + 1) * s, j * s:(j + 1) * s] = t
    return np.clip(img, 0, 1)


def gen_painted_door(n=512):
    """The painted door's picture, as seen from the mark: a cream six-panel door in a dark frame, a brass knob, the shadow of its recess;
    u across the door (0..1), v up it (row 0 is the bottom). Painted flat; the build stretches it over the floor and the end wall."""
    Yi, Xi = np.mgrid[0:2 * n, 0:n]
    Y, X = Yi / (2 * n), Xi / n
    img = np.zeros((2 * n, n, 3))
    img[:] = C("#3a2a20")
    leaf = (X > 0.08) & (X < 0.92) & (Y < 0.95)
    img[leaf] = C("#e4d6b8")
    for x0, x1 in ((0.16, 0.46), (0.54, 0.84)):
        for y0, y1 in ((0.06, 0.32), (0.38, 0.6), (0.66, 0.88)):
            p = (X > x0) & (X < x1) & (Y > y0) & (Y < y1)
            img[p] = C("#cdbd9a")
            img[p & ((X < x0 + 0.02) | (Y > y1 - 0.012))] = C("#8a7a5a")
            img[p & ((X > x1 - 0.02) | (Y < y0 + 0.012))] = C("#f4ead4")
    img[np.hypot(X - 0.82, (Y - 0.45) * 2.0) < 0.035] = C("#c89a38")
    sh = (X > 0.08) & (X < 0.13) & leaf
    img[sh] = img[sh] * 0.7
    img[(Y < 0.012)] = C("#2a1e16")
    return np.clip(img, 0, 1)


# ---------------------------------------------------------------- textures (Poly Haven, CC0, already in the repo) and materials
WOOD = "apartment/dark_wood_diff_1k.jpg"
FLOORWOOD = "apartment/old_wood_floor_diff_1k.jpg"
BEIGE = "apartment/beige_wall_001_diff_1k.jpg"
LINEN = "apartment/rough_linen_diff_512.jpg"
PARQUET = "galleries/herringbone_parquet_diff_1k.jpg"
MARBLE = "galleries/marble_01_diff_1k.jpg"
PLASTER = "galleries/plastered_wall_04_diff_1k.jpg"
VINYL = "laboratory/floor_vinyl_diff.jpg"
PAINT = "laboratory/wall_paint_diff.jpg"
ACOUSTIC = "laboratory/ceiling_tile_diff.jpg"
WARM, COOL = (1.0, 0.8, 0.58), (0.86, 0.92, 1.0)
GENS = {   # generated images, made when a material first needs them
    "gen_brushed": lambda: gen_brushed(),
    "gen_shag": lambda: gen_shag(11, "#1f5a18", "#3f9a2a", "#9ae05a"),
    "gen_shag_rose": lambda: gen_shag(13, "#8a2a4a", "#c84a7a", "#f08ab0"),
    "gen_swirl": lambda: gen_swirl(21, "#f4e2bc", "#ff8ac8", "#7af0c0"),
    "gen_swirl_sun": lambda: gen_swirl(22, "#f8d870", "#ff7a3a", "#ffffff"),
    "gen_photos": lambda: gen_photos(31),
    "gen_plaid": lambda: gen_plaid(61),
    "gen_diamond": lambda: gen_diamond_carpet(62),
    "gen_tile_mint": lambda: gen_tiles(141, 8, "#a8f0c8", "#98e4bc", "#e8f4ec", 0.02),
    "gen_checker": lambda: gen_checker(142, "#f2eee4", "#2a2a30", 4),
    "gen_checker_bw": lambda: gen_checker(143, "#e8e4dc", "#c8c0b0", 2, grout="#a8a090"),
    "gen_stripes_pink": lambda: gen_stripes(151, ["#ff9ac4", "#ffd2e4", "#ff9ac4", "#fff2f6"], [3, 1, 3, 0.5]),
    "gen_stripes_peach": lambda: gen_stripes(152, ["#f8b48c", "#f4d2b0"], [1, 1]),
    "gen_weave_lilac": lambda: gen_weave(153),
    "gen_quilt_orange": lambda: gen_quilt(201, "#ff9a3a", "#c85a10"),
    "gen_books": lambda: gen_books(161),
    "gen_cardboard": lambda: gen_cardboard(162),
    "gen_clouds": lambda: gen_clouds(163),
    "gen_posters": lambda: gen_posters(164),
    "gen_concrete": lambda: gen_concrete(204),
    "gen_painted_door": lambda: gen_painted_door(),
}


def gimg(key):
    return GEN[key] if key in GEN else mk_image(key, GENS[key]())


SPEC = {   # name: material() keywords; `gen` names a generated image, `hex` a colour (sRGB) for color or tint
    # emissive, never baked
    "Lamp_Emit": dict(color=(1.0, 0.93, 0.8), rough=0.9, emit=(WARM, 5.0)),
    "Window_Lit": dict(gen="gen_clouds", rough=0.9, emit=((1.0, 0.97, 0.92), 1.4), emit_tex=True),
    "Stars_Glow": dict(color=(0.7, 1.0, 0.4), rough=0.9, emit=((0.65, 1.0, 0.35), 2.5)),
    "Shard_Glow": dict(color=(0.75, 1.0, 0.1), rough=0.4, emit=((0.72, 1.0, 0.08), 2.2)),
    "Void": dict(color=(0.0, 0.0, 0.0), rough=1.0),
    "Glass_Clear": dict(color=(0.8, 0.9, 0.95), rough=0.05, alpha=0.18),
    # metals and small parts
    "Brass": dict(gen="gen_brushed", hex="#d4a548", rough=0.3, metal=0.9, tile=0.3),
    "Chrome": dict(gen="gen_brushed", hex="#e0e4ea", rough=0.15, metal=1.0, tile=0.3),
    "Iron": dict(gen="gen_brushed", hex="#3a3c40", rough=0.5, metal=0.7, tile=0.3),
    "Glass_Knob": dict(hex="#bfe6ff", rough=0.05),
    "Leaf_Glass": dict(hex="#20303a", rough=0.1, metal=0.2),
    "Mirror": dict(hex="#a8b8c8", rough=0.08, metal=0.6),
    "Rubber_Black": dict(hex="#1a1a1c", rough=0.7),
    "Plastic_White": dict(hex="#dcd8ce", rough=0.5),
    "Plastic_Black": dict(hex="#222226", rough=0.45),
    "Frame_Wood": dict(tex=WOOD, hex="#a86a3a", rough=0.5, tile=0.6),
    "Frame_Back": dict(hex="#e8e4da", rough=0.9),
    "Frame_Gilt": dict(gen="gen_brushed", hex="#c8a040", rough=0.35, metal=0.8, tile=0.2),
    "Photo": dict(gen="gen_photos", rough=0.5),
    "Poster": dict(gen="gen_posters", rough=0.6),
    "Paper": dict(hex="#ece6d6", rough=0.9),
    "China": dict(hex="#f0ece4", rough=0.15),
    "China_Rim": dict(hex="#3a8ad8", rough=0.2),
    "Candle": dict(hex="#f4ecd8", rough=0.6),
    # wood, cloth, paint for props
    "Maple": dict(tex=WOOD, hex="#ffb060", rough=0.4, tile=0.9),
    "Maple_Dark": dict(tex=WOOD, hex="#c87838", rough=0.45, tile=0.9),
    "Walnut": dict(tex=WOOD, hex="#9a6438", rough=0.45, tile=0.9),
    "Pine": dict(tex=FLOORWOOD, hex="#f0c890", rough=0.6, tile=1.2),
    "Velvet_Red": dict(tex=LINEN, hex="#c01850", rough=0.9, tile=0.6),
    "Velvet_Orange": dict(tex=LINEN, hex="#ff7a20", rough=0.9, tile=1.4),
    "Velvet_Green": dict(tex=LINEN, hex="#2a9a5a", rough=0.9, tile=0.8),
    "Linen_White": dict(tex=LINEN, hex="#f4eee2", rough=0.95, tile=0.5),
    "Linen_Pink": dict(tex=LINEN, hex="#ff9ac8", rough=0.95, tile=0.6),
    "Linen_Cyan": dict(tex=LINEN, hex="#6ad8f0", rough=0.95, tile=0.6),
    "Linen_Yellow": dict(tex=LINEN, hex="#ffd850", rough=0.95, tile=0.6),
    "Linen_Red": dict(tex=LINEN, hex="#c82838", rough=0.95, tile=0.6),
    "Paint_White": dict(tex=PAINT, hex="#f4f0e6", rough=0.5, tile=1.0),
    "Paint_Mint": dict(tex=PAINT, hex="#8cf0c4", rough=0.45, tile=1.0),
    "Paint_Red": dict(tex=PAINT, hex="#e8303a", rough=0.4, tile=1.0),
    "Paint_Yellow": dict(tex=PAINT, hex="#ffd030", rough=0.45, tile=1.0),
    "Paint_Cream": dict(tex=PAINT, hex="#f4e6c4", rough=0.5, tile=1.0),
    "Paint_Black": dict(hex="#141418", rough=0.3),
    "Paint_Pink": dict(tex=PAINT, hex="#ff6ab4", rough=0.4, tile=1.0),
    "Paint_Cyan": dict(tex=PAINT, hex="#30d8f0", rough=0.4, tile=1.0),
    "Paint_Violet": dict(tex=PAINT, hex="#9a5ae8", rough=0.45, tile=1.0),
    "Paint_Lime": dict(tex=PAINT, hex="#b8f040", rough=0.45, tile=1.0),
    "Enamel_Cream": dict(tex=PAINT, hex="#f0e4cc", rough=0.25, tile=1.0),
    "Marble_Top": dict(tex=MARBLE, hex="#f4f0ea", rough=0.2, tile=1.0),
    "Marble_Prop": dict(tex=MARBLE, hex="#f0ece6", rough=0.25, tile=1.2),
    "Steel": dict(gen="gen_brushed", hex="#c0c4c8", rough=0.35, metal=0.8, tile=0.4),
    "Cardboard": dict(gen="gen_cardboard", rough=0.85, tile=0.6),
    "Tape": dict(hex="#c8a870", rough=0.5),
    "Books": dict(gen="gen_books", rough=0.6, tile=1.0),
    "Pages": dict(hex="#f0e8d0", rough=0.8),
    "Cover_Red": dict(tex=LINEN, hex="#c02838", rough=0.6, tile=0.8),
    "Cover_Blue": dict(tex=LINEN, hex="#2a5ac8", rough=0.6, tile=0.8),
    "Cover_Green": dict(tex=LINEN, hex="#2a9a4a", rough=0.6, tile=0.8),
    "Cover_Yellow": dict(tex=LINEN, hex="#e8b830", rough=0.6, tile=0.8),
    "Cover_Violet": dict(tex=LINEN, hex="#8a3ac0", rough=0.6, tile=0.8),
    "Leaf_Plant": dict(hex="#3aae3a", rough=0.6),
    "Pot_Clay": dict(hex="#c86a40", rough=0.85),
    "Soil": dict(hex="#2a1f14", rough=1.0),
    "Gift_Pink": dict(hex="#ff5ab0", rough=0.35),
    "Gift_Cyan": dict(hex="#30d0f0", rough=0.35),
    "Gift_Lime": dict(hex="#a8f040", rough=0.35),
    "Gift_Violet": dict(hex="#9a50f0", rough=0.35),
    "Ribbon_Gold": dict(gen="gen_brushed", hex="#f0c040", rough=0.3, metal=0.6, tile=0.2),
    "Balloon_Pink": dict(hex="#ff4aa0", rough=0.2),
    "Balloon_Cyan": dict(hex="#20c8f0", rough=0.2),
    "Balloon_Lime": dict(hex="#a0f030", rough=0.2),
    "Balloon_Violet": dict(hex="#9a40f0", rough=0.2),
    "Icing": dict(hex="#fff4f0", rough=0.5),
    "Icing_Pink": dict(hex="#ff8ac0", rough=0.5),
    "Banner": dict(hex="#ffd040", rough=0.7),
    "Piano_Black": dict(hex="#121216", rough=0.15),
    "Keys_White": dict(hex="#f0ece4", rough=0.3),
    "Horse_White": dict(hex="#f0e8dc", rough=0.4),
    "Rug_Lilac": dict(tex=LINEN, hex="#c8a0ff", rough=0.95, tile=0.6),
    "Rug_Pink": dict(gen="gen_shag_rose", rough=1.0, tile=1.2),
    "Rug_Red": dict(tex=LINEN, hex="#a01830", rough=0.95, tile=0.6),
    "Radiator": dict(tex=PAINT, hex="#ece8de", rough=0.35, tile=1.0),
    "Velvet_Orange_Tuft": dict(tex=LINEN, hex="#d85a10", rough=0.9, tile=1.4),
    "Mug_White": dict(hex="#f0ece6", rough=0.2),
    "Rail_Black": dict(hex="#1c1c20", rough=0.4, metal=0.3),
    "Tread_Wood": dict(tex=WOOD, hex="#d89060", rough=0.45, tile=0.8),
    "Nosing": dict(gen="gen_brushed", hex="#a0a4a8", rough=0.4, metal=0.7, tile=0.3),
    "Crate_Wood": dict(tex=FLOORWOOD, hex="#d8a870", rough=0.7, tile=0.8),
    "Painted_Door": dict(gen="gen_painted_door", rough=0.6),
    "Floor_Paint_Yellow": dict(hex="#ffd030", rough=0.5),
    "Floor_Paint_Red": dict(hex="#e8303a", rough=0.5),
    "Floor_Paint_Cyan": dict(hex="#30c8e8", rough=0.5),
    "Note_Card": dict(hex="#f4f0e4", rough=0.8),
    "Trim_Cream": dict(tex=PAINT, hex="#fff2dc", rough=0.5, tile=1.0),
    "Trim_White": dict(tex=PAINT, hex="#f4f2ec", rough=0.45, tile=1.0),
    "Trim_Dark": dict(tex=WOOD, hex="#7a4a2a", rough=0.5, tile=0.9),
    "Trim_Mint": dict(tex=PAINT, hex="#e8fff2", rough=0.45, tile=1.0),
    "Trim_Lilac": dict(tex=PAINT, hex="#e8d8ff", rough=0.45, tile=1.0),
    "Trim_Peach": dict(tex=PAINT, hex="#fff0e0", rough=0.45, tile=1.0),
    "Trim_Teal": dict(tex=PAINT, hex="#f4fff8", rough=0.45, tile=1.0),
    "Trim_Navy": dict(tex=PAINT, hex="#c8d0ff", rough=0.45, tile=1.0),
    "Trim_Yellow": dict(tex=PAINT, hex="#fff8e0", rough=0.45, tile=1.0),
    "Tiles_Small": dict(gen="gen_checker", rough=0.25, tile=0.5),
    # shells: walls, floors, ceilings (only ever on the shell page)
    "Wall_Cream": dict(gen="gen_swirl", rough=0.8, tile=1.6),
    "Floor_Shag": dict(gen="gen_shag", rough=1.0, tile=1.1),
    "Floor_Shag_Rose": dict(gen="gen_shag_rose", rough=1.0, tile=1.1),
    "Ceil_Plaster": dict(tex=PLASTER, hex="#fff2e6", rough=0.95, tile=2.6),
    "Ceil_White": dict(tex=PLASTER, hex="#f8f6f0", rough=0.95, tile=2.4),
    "Ceil_Acoustic": dict(tex=ACOUSTIC, hex="#fff8ee", rough=0.9, tile=1.2),
    "Wall_Mint_Tile": dict(gen="gen_tile_mint", rough=0.25, tile=1.2),
    "Floor_Checker": dict(gen="gen_checker", rough=0.25, tile=1.0),
    "Wall_Pink_Stripe": dict(gen="gen_stripes_pink", rough=0.8, tile=1.2),
    "Floor_Parquet": dict(tex=PARQUET, hex="#ffd0a0", rough=0.5, tile=2.0),
    "Wall_Boards": dict(tex=FLOORWOOD, hex="#e0b888", rough=0.75, tile=1.6),
    "Floor_Boards": dict(tex=FLOORWOOD, hex="#d8a878", rough=0.75, tile=1.6),
    "Ceil_Boards": dict(tex=FLOORWOOD, hex="#c89868", rough=0.8, tile=1.6),
    "Wall_Clouds": dict(gen="gen_clouds", rough=0.8, tile=2.0),
    "Floor_Carpet_Lilac": dict(tex=LINEN, hex="#d8b8ff", rough=1.0, tile=0.5),
    "Ceil_Night": dict(tex=PLASTER, hex="#3a4a90", rough=0.95, tile=2.4),
    "Wall_Peach_Paper": dict(tex=BEIGE, hex="#ffc8a0", rough=0.85, tile=2.0),
    "Wall_Sun_Damask": dict(gen="gen_swirl_sun", rough=0.8, tile=1.4),
    "Floor_Ceiling_Plaster": dict(tex=PLASTER, hex="#f6f4ee", rough=0.95, tile=2.4),
    "Ceil_Floorboards": dict(tex=FLOORWOOD, hex="#d8a878", rough=0.75, tile=1.6),
    "Wall_Plaid": dict(gen="gen_plaid", rough=0.8, tile=1.4),
    "Floor_Diamond": dict(gen="gen_diamond", rough=1.0, tile=1.6),
    "Wall_White": dict(tex=PAINT, hex="#f2f0ea", rough=0.6, tile=2.0),
    "Floor_White": dict(tex=VINYL, hex="#f0eee8", rough=0.3, tile=2.0),
    "Wall_Fin": dict(tex=PAINT, hex="#f8f6f2", rough=0.3, tile=1.0),
    "Wall_Lilac": dict(tex=PLASTER, hex="#c8a8f0", rough=0.85, tile=2.2),
    "Wall_Violet": dict(tex=PLASTER, hex="#9a6ae0", rough=0.85, tile=2.2),
    "Wall_Mint": dict(tex=PLASTER, hex="#9ae8c4", rough=0.85, tile=2.2),
    "Floor_Concrete": dict(gen="gen_concrete", rough=0.9, tile=3.0),
    "Stair_Tread": dict(tex=WOOD, hex="#d89060", rough=0.45, tile=0.8),
    "Stair_Mint": dict(tex=PLASTER, hex="#7ad8b0", rough=0.85, tile=2.2),
    "Wall_Peach_Stripe": dict(gen="gen_stripes_peach", rough=0.8, tile=1.2),
    "Floor_Tan": dict(gen="gen_diamond", rough=1.0, tile=1.6),
    "Floor_Marble": dict(tex=MARBLE, hex="#f4f2ee", rough=0.2, tile=2.2),
    "Wall_Gallery": dict(tex=PAINT, hex="#f4f2ec", rough=0.6, tile=2.0),
    "Wall_Teal_Cream": dict(tex=PLASTER, hex="#e8f0d8", rough=0.85, tile=2.2),
    "Floor_Checker_Pale": dict(gen="gen_checker_bw", rough=0.3, tile=2.4),
    "Wall_Indigo": dict(tex=PLASTER, hex="#6a74c8", rough=0.85, tile=2.2),
    "Floor_Indigo": dict(gen="gen_checker", hex="#8890d0", rough=0.4, tile=1.6),
    "Ceil_Indigo": dict(tex=PLASTER, hex="#4a5094", rough=0.95, tile=2.4),
}
TRICK_SUFFIX = "_T"


def M(name):
    """The material `name` (made from SPEC on first use); `<name>_T` is its copy for the trick objects (their own lightmap page)."""
    if name in MATS:
        return name
    if name.endswith(TRICK_SUFFIX) and name[:-2] in SPEC:
        base = MATS[M(name[:-2])]
        m = base.copy()
        m.name = name
        MATS[name] = m
        TILES[name] = TILES.get(name[:-2], 1.0)
        return name
    sp = dict(SPEC[name])
    g = sp.pop("gen", None)
    hx = sp.pop("hex", None)
    emit_tex = sp.pop("emit_tex", False)
    if g:
        sp["img"] = gimg(g)
    if hx:
        if g or "tex" in sp:
            sp["tint"] = srgb_lin(hx)
        else:
            sp["color"] = srgb_lin(hx)
    material(name, **sp)
    if emit_tex:
        nt = MATS[name].node_tree
        tn = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
        bs = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        nt.links.new(tn.outputs["Color"], bs.inputs["Emission Color"])
    return name


def T(name):
    return M(name + TRICK_SUFFIX)


# every door finish (build_rdwe_greybox.FINISHES) as its own leaf material: saturated, a step too far
FINISH = {"oak": ("tex", "#d8a060"), "teal paint": ("paint", "#18b8b0"), "mint paint": ("paint", "#7cf0b8"), "pink laminate": ("gloss", "#ff6ab4"),
          "brushed steel": ("steel", "#b8bcc2"), "cream gloss": ("gloss", "#f4e8c8"), "cherry red": ("gloss", "#d81c2a"),
          "bottle green": ("paint", "#0e6a34"), "lilac": ("paint", "#b48cf0"), "black lacquer": ("gloss", "#141418"), "birch": ("tex", "#f0d8a8"),
          "orange vinyl": ("gloss", "#ff7a18"), "sky blue": ("paint", "#5ab4ff"), "mustard": ("paint", "#e0b020"), "plum": ("paint", "#7a2a6a")}


def leaf_mat(finish):
    name = "Leaf_" + "".join(w.capitalize() for w in finish.replace("(", "").replace(")", "").split())
    if name in MATS:
        return name
    kind, h = FINISH.get(finish, ("paint", "#888888"))
    col = srgb_lin(h)
    if kind == "tex":
        return material(name, tex=WOOD, tint=tuple(min(1.0, c * 1.6) for c in col), rough=0.45, tile=0.9).name
    if kind == "steel":
        return material(name, img=gimg("gen_brushed"), tint=col, rough=0.35, metal=0.85, tile=0.5).name
    return material(name, tex=PAINT, tint=col, rough=0.3 if kind == "gloss" else 0.6, tile=1.0).name


def common_materials():
    for n in ("Lamp_Emit", "Void", "Glass_Clear", "Brass", "Chrome", "Iron", "Glass_Knob", "Leaf_Glass", "Mirror", "Rubber_Black", "Plastic_White"):
        M(n)
    material("Leaf_Painted", tex=PAINT, tint=srgb_lin("#e4d6b8"), rough=0.5, tile=1.0)
    material("Standin_Grey", color=(0.4, 0.38, 0.34), rough=0.9)


# the shell, per room: greybox colour -> this room's material (the ceiling, by tag)
SHELL = {
    "rdwe_long_table": {"cream": "Wall_Cream", "shag": "Floor_Shag", "ceiling": "Ceil_Plaster"},
    "rdwe_tiny_kitchen": {"mint": "Wall_Mint_Tile", "tile": "Floor_Checker", "ceiling": "Ceil_White"},
    "rdwe_birthday_party": {"pink": "Wall_Pink_Stripe", "peach": "Floor_Parquet", "ceiling": "Ceil_Plaster"},
    "rdwe_attic": {"wood": "Wall_Boards", "ceiling": "Ceil_Boards"},
    "rdwe_kids_bedroom": {"cyan": "Wall_Clouds", "lilac": "Floor_Carpet_Lilac", "ceiling": "Ceil_Night"},
    "rdwe_giant_chair": {"cream": "Wall_Peach_Paper", "shag": "Floor_Shag_Rose", "ceiling": "Ceil_Plaster"},
    "rdwe_upside_room": {"sun": "Wall_Sun_Damask", "ceiling": "Floor_Ceiling_Plaster", "shag": "Ceil_Floorboards"},
    "rdwe_door_hall": {"plaid": "Wall_Plaid", "carpet_tan": "Floor_Diamond", "ceiling": "Ceil_Plaster"},
    "rdwe_stretching_hall": {"white": "Wall_White", "ceiling": "Ceil_White"},
    "rdwe_bending_hall": {"lilac": "Wall_Lilac", "violet": "Wall_Violet", "carpet_tan": "Floor_Tan", "ceiling": "Ceil_Plaster"},
    "rdwe_stair_loop": {"mint": "Wall_Mint", "concrete": "Floor_Concrete", "stair": "Stair_Tread", "ceiling": "Ceil_White"},
    "rdwe_tilted_hall": {"peach": "Wall_Peach_Stripe", "wallpaper": "Wall_Peach_Stripe", "carpet_tan": "Floor_Tan", "ceiling": "Ceil_Plaster"},
    "rdwe_three_doors": {"white": "Wall_Gallery", "ceiling": "Ceil_White"},
    "rdwe_painted_door": {"teal_cream": "Wall_Teal_Cream", "white": "Floor_Checker_Pale", "ceiling": "Ceil_White"},
    "rdwe_anamorphic_room": {"navy": "Wall_Indigo", "ceiling": "Ceil_Indigo"},
}
FLOOR_MAT = {"rdwe_stretching_hall": "Floor_White", "rdwe_three_doors": "Floor_Marble", "rdwe_anamorphic_room": "Floor_Indigo",
             "rdwe_attic": "Floor_Boards", "rdwe_upside_room": "Floor_Ceiling_Plaster"}
CEIL_MAT = {s: SHELL[s]["ceiling"] for s in SHELL}
CEIL_MAT["rdwe_upside_room"] = "Ceil_Floorboards"


def shell_material(b, ax, side, centre):
    """The material of one shell piece: by the box's greybox colour; ceilings by tag, floors (the top of a floor slab) by the room."""
    s, n = SCENE, b["name"]
    if b["mat"] == "void" or n.startswith("Beyond_"):
        return M("Void")
    if "ceiling" in b["tags"] or n.endswith("_Ceiling"):
        return M(CEIL_MAT[s])
    if n.endswith("_Floor") and s in FLOOR_MAT:
        return M(FLOOR_MAT[s])
    if s == "rdwe_upside_room" and n.endswith("_Floor"):
        return M("Floor_Ceiling_Plaster")
    if n.startswith(("Step_", "Landing")) and s == "rdwe_stair_loop":
        return M("Stair_Tread" if (ax == 1 and side > 0) else "Stair_Mint")
    if n.startswith(("Step_tilt", "Fill_tilt")):
        return M("Floor_Tan" if (ax == 1 and side > 0) else "Wall_Peach_Stripe")
    if n.startswith("Fill_up"):
        return M("Stair_Mint")
    if n == "Core":
        return M("Wall_Violet")
    if s == "rdwe_stretching_hall" and n.startswith("Fin_"):
        return M("Wall_Fin")
    m = SHELL[s].get(b["mat"])
    if m is None:
        m = SHELL[s].get("ceiling") if b["mat"] == "ceiling" else next(iter(SHELL[s].values()))
    return M(m)


# ---------------------------------------------------------------- geometry helpers (world space; Blender = game (x, -z, y))
def cube(bm, gmin, gmax):
    a, b = B(gmin), B(gmax)
    c = (a + b) / 2
    s = Vector((abs(a.x - b.x), abs(a.y - b.y), abs(a.z - b.z)))
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((max(s.x, 1e-5), max(s.y, 1e-5), max(s.z, 1e-5), 1.0)))


def cyl(bm, p0, p1, r0, r1=None, seg=16, cap=True):
    a, b = B(p0), B(p1)
    d = b - a
    q = d.to_track_quat("Z", "Y")
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                          matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())


def sphere(bm, p, r, seg=12, sy=1.0):
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(4, seg // 2), radius=r, matrix=Matrix.Translation(B(p)) @ Matrix.Diagonal((1, 1, sy, 1)))


def torus(bm, p, R, r, axis=(0, 1, 0), seg=16, rseg=6):
    """A ring of radius R, tube r, round the game axis `axis`, centred on p."""
    tmp = bmesh.new()
    vs = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        for j in range(rseg):
            b = 2 * math.pi * j / rseg
            vs.append(tmp.verts.new(((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b))))
    for i in range(seg):
        for j in range(rseg):
            a0, a1 = i * rseg + j, i * rseg + (j + 1) % rseg
            b0, b1 = ((i + 1) % seg) * rseg + j, ((i + 1) % seg) * rseg + (j + 1) % rseg
            tmp.faces.new((vs[a0], vs[b0], vs[b1], vs[a1]))
    q = B(axis).to_track_quat("Z", "Y")
    bmesh.ops.transform(tmp, matrix=Matrix.Translation(B(p)) @ q.to_matrix().to_4x4(), verts=tmp.verts)
    me = bpy.data.meshes.new("t")
    tmp.to_mesh(me)
    tmp.free()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)


def prism(bm, pts2, a0, a1, axis="x"):
    """A prism: the polygon pts2 [(u, y)] (u = game z for axis 'x', game x for axis 'z') extruded along `axis` from a0 to a1."""
    def P(u, y, a):
        return B((a, y, u)) if axis == "x" else B((u, y, a))
    v0 = [bm.verts.new(P(u, y, a0)) for u, y in pts2]
    v1 = [bm.verts.new(P(u, y, a1)) for u, y in pts2]
    n = len(pts2)
    bm.faces.new(v0[::-1])
    bm.faces.new(v1)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((v0[i], v0[j], v1[j], v1[i]))


def box_uv(bm, tile):
    uvl = bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y
            u, v = (gz, gy) if ax == 0 else (gx, gy) if ax == 1 else (gx, gz)
            lp[uvl].uv = (u / tile, v / tile)


ART = PROPS = ARCH = SKIN = DOORS = LAYOUT = LIGHTS = ALTL = None


def finish(name, bm, mat, coll, tile=None, keep_uv=False, recalc=True, smooth=False):
    if recalc and not keep_uv:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        f.smooth = smooth
    if not bm.loops.layers.uv.get("UVMap"):
        bm.loops.layers.uv.new("UVMap")
    if not keep_uv:
        box_uv(bm, tile or TILES.get(mat, 1.0))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def part(name, mat, build, coll=None, tile=None, smooth=False, recalc=True):
    bm = bmesh.new()
    build(bm)
    return finish(name, bm, mat, coll or PROPS, tile, recalc=recalc, smooth=smooth)


def boxes(name, mat, rects, coll=None, tile=None):
    """One object of axis boxes: rects = [(min, max)] in game coordinates."""
    def b(bm):
        for mn, mx in rects:
            cube(bm, mn, mx)
    return part(name, mat, b, coll, tile)


def text_mesh(body, size, extrude):
    cu = bpy.data.curves.new("txt", "FONT")
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    cu.resolution_u = 3
    ob = bpy.data.objects.new("txt", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return me


def add_text(bm, body, size, depth, origin, right, up, normal):
    me = text_mesh(body, size, depth / 2)
    R, U, N = B(right), B(up), B(normal)
    O = B(origin)
    M = Matrix(((R.x, U.x, N.x, O.x), (R.y, U.y, N.y, O.y), (R.z, U.z, N.z, O.z), (0, 0, 0, 1)))
    tmp = bmesh.new()
    tmp.from_mesh(me)
    bmesh.ops.translate(tmp, verts=tmp.verts, vec=Vector((0, 0, depth / 2)))
    bmesh.ops.transform(tmp, matrix=M, verts=tmp.verts)
    m2 = bpy.data.meshes.new("t2")
    tmp.to_mesh(m2)
    tmp.free()
    bm.from_mesh(m2)
    bpy.data.meshes.remove(m2)
    bpy.data.meshes.remove(me)


# ---------------------------------------------------------------- the model, its boxes and its doors
_MODEL = {}


def model():
    if SCENE not in _MODEL:
        _MODEL[SCENE] = GB.build(SCENE)
    return _MODEL[SCENE]


def gbx(name):
    return next(b for b in model().boxes if b["name"] == name)


def is_furniture(b):
    return "f" in b.get("tags", ()) or b["name"].startswith(FURN_EXTRA.get(SCENE, ("~none~",)))


def shell_boxes():
    return [b for b in model().boxes if b.get("col") and b.get("art", True) and not b.get("zone") and not is_furniture(b)]


def door_geom(d):
    """A door's opening: (hinge (x, y, z), run (x, z) along the leaf, inward (x, z) into the room, width, height)."""
    p = d["props"]
    th = math.radians(p["closed_yaw_deg"])
    run = (math.cos(th), -math.sin(th))
    sw = math.radians(p["closed_yaw_deg"] + (90 if p["swing_deg"] > 0 else -90))
    inward = (round(math.cos(sw), 6), round(-math.sin(sw), 6))
    return d["hinge"], run, inward, p["width"], p["height"]


# ---------------------------------------------------------------- layout objects (exported to the JSON, never to the GLB)
def col_box(name, mn, mx, coll=None):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    cube(bm, mn, mx)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    (coll or LAYOUT).objects.link(ob)
    ob.hide_render = True
    ob.display_type = "WIRE"
    return ob


def layout_from_model(M):
    for b in M.boxes:
        if b.get("zone"):
            col_box(b["name"], b["min"], b["max"])
            continue
        if b["col"]:
            col_box("COL_" + b["name"], b["min"], b["max"])
            if is_furniture(b):
                continue
            bm = bmesh.new()
            cube(bm, b["min"], b["max"])
            finish(b["name"], bm, "Standin_Grey", ARCH, tile=1.0)
    for e in M.empties:
        ob = bpy.data.objects.new(e["name"], None)
        ob.location = B(e["pos"])
        if e["face"]:
            ob.rotation_euler = (0, 0, math.atan2(e["face"][0], e["face"][1]))
        for k, v in e["props"].items():
            ob[k] = v
        ob.empty_display_size = 0.3
        LAYOUT.objects.link(ob)
    for ob in ARCH.objects:
        ob.hide_render = True


# ---------------------------------------------------------------- the shell as seen
# the air of each room (game min, max): a shell face is drawn only where the air in front of it is in here (or in a door's opening) and in no
# other shell box. The dining room's stairwell, the hallway's well and the door openings are air too.
def room_air():
    """The room's air: inside its shell, from the floor (y 0) to the underside of its ceiling."""
    c = next(b for b in model().boxes if b["name"] in ("Room_Ceiling", "Stairs_Ceiling"))
    return [((c["min"][0] + GB.T, 0.0, c["min"][2] + GB.T), (c["max"][0] - GB.T, c["min"][1], c["max"][2] - GB.T))]


def air_boxes():
    out = [{"min": list(a), "max": list(b)} for a, b in room_air()]
    for d in model().doors:
        (hx, hy, hz), run, inw, w, h = door_geom(d)
        p0 = (hx - run[0] * 0.03 - inw[0] * 0.6, hz - run[1] * 0.03 - inw[1] * 0.6)
        p1 = (hx + run[0] * (w + 0.03) + inw[0] * 0.6, hz + run[1] * (w + 0.03) + inw[1] * 0.6)
        out.append({"min": [min(p0[0], p1[0]), hy, min(p0[1], p1[1])], "max": [max(p0[0], p1[0]), hy + h + 0.03, max(p0[1], p1[1])]})
    return out


def _inside(p, b, e=1e-4):
    return all(b["min"][i] + e < p[i] < b["max"][i] - e for i in range(3))


def build_skin():
    shells = shell_boxes()
    inner = [b for b in shells if not b["name"].startswith("Beyond_")]
    lo = [min(b["min"][i] for b in inner) for i in range(3)]
    hi = [max(b["max"][i] for b in inner) for i in range(3)]
    ctr = [(lo[i] + hi[i]) / 2 for i in range(3)]
    air = air_boxes()
    by = {}
    for b in shells:
        beyond = b["name"].startswith("Beyond_")
        if beyond:
            thin = min(range(3), key=lambda i: b["max"][i] - b["min"][i])
        for ax in range(3):
            for side in (-1, 1):
                if beyond and not (ax == thin and side == (1 if ctr[ax] > (b["min"][ax] + b["max"][ax]) / 2 else -1)):
                    continue
                o = [a for a in range(3) if a != ax]
                c0, c1 = o
                plane = b["max"][ax] if side > 0 else b["min"][ax]
                n0 = max(1, math.ceil((b["max"][c0] - b["min"][c0]) / 4.0))
                n1 = max(1, math.ceil((b["max"][c1] - b["min"][c1]) / 4.0))
                for i in range(n0):
                    for j in range(n1):
                        u0 = b["min"][c0] + (b["max"][c0] - b["min"][c0]) * i / n0
                        u1 = b["min"][c0] + (b["max"][c0] - b["min"][c0]) * (i + 1) / n0
                        v0 = b["min"][c1] + (b["max"][c1] - b["min"][c1]) * j / n1
                        v1 = b["min"][c1] + (b["max"][c1] - b["min"][c1]) * (j + 1) / n1
                        if u1 - u0 < 1e-4 or v1 - v0 < 1e-4:
                            continue
                        keep = beyond
                        if not beyond:
                            for fu, fv in ((0.5, 0.5), (0.1, 0.1), (0.9, 0.1), (0.1, 0.9), (0.9, 0.9)):
                                f = [0.0, 0.0, 0.0]
                                f[ax] = plane + side * 0.01
                                f[c0] = u0 + (u1 - u0) * fu
                                f[c1] = v0 + (v1 - v0) * fv
                                if any(_inside(f, a, 0.0) for a in air) and not any(_inside(f, c) for c in shells if c is not b):
                                    keep = True
                                    break
                        if not keep:
                            continue
                        cen = [0.0, 0.0, 0.0]
                        cen[ax], cen[c0], cen[c1] = plane, (u0 + u1) / 2, (v0 + v1) / 2
                        mname = shell_material(b, ax, side, cen)
                        by.setdefault(mname, []).append((ax, side, plane, c0, u0, u1, c1, v0, v1))
    for mname, quads in sorted(by.items()):
        skin_mesh(mname, quads)
    print("SKIN", {k: len(v) for k, v in sorted(by.items())})


def skin_mesh(mname, quads):
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    tile = TILES.get(mname, 1.0)
    for ax, side, plane, c0, u0, u1, c1, v0, v1 in quads:
        pts = []
        for uu, vv in ((u0, v0), (u1, v0), (u1, v1), (u0, v1)):
            p = [0.0, 0.0, 0.0]
            p[ax], p[c0], p[c1] = plane, uu, vv
            pts.append(p)
        f = bm.faces.new([bm.verts.new(B(p)) for p in pts])
        f.normal_update()
        want = [0, 0, 0]
        want[ax] = side
        if f.normal.dot(B(want)) < 0:
            f.normal_flip()
        for lp in f.loops:
            gx, gy, gz = lp.vert.co.x, lp.vert.co.z, -lp.vert.co.y
            u, v = (gz, gy) if ax == 0 else (gx, gz) if ax == 1 else (gx, gy)
            lp[uvl].uv = (u / tile, v / tile)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    me = bpy.data.meshes.new(mname)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mname])
    ob = bpy.data.objects.new(mname, me)
    SKIN.objects.link(ob)
    return ob


# ---------------------------------------------------------------- door leaves: one mesh per door, made from its look
STORY = {   # the explicit looks of rooms 1-15 -> (form, finish material, handle, extras); the rest are "<form> <finish> door, <handle>"
    "a door painted on the end wall": ("six-panel", "Leaf_Painted", "brass knob", ()),
}


def parse_look(look):
    for k, v in STORY.items():
        if look.startswith(k):
            return v
    # "<form> <finish> door, <handle>"
    head, handle = look.split(", ", 1)
    head = head[:-len(" door")]
    form = next(f for f in sorted(GB.FORMS, key=len, reverse=True) if head.startswith(f))
    fin = head[len(form) + 1:]
    return form, leaf_mat(fin), handle, ()


def leaf_mesh(name, look, width, height):
    """Local +X runs from the hinge along the leaf, z is up, the leaf is 5 cm thick on y -0.025..0.025 (the room side is -Y, as built: the
    page swings it round its origin). The form, the finish and the handle come from the door's `look`."""
    form, fmat, handle, extras = parse_look(look)
    pieces = {}
    th = 0.025
    w, h = width - 0.006, height - 0.008

    def bx(x0, x1, y0, y1, z0, z1, mat):
        bm = pieces.setdefault(mat, bmesh.new())
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)) @ Matrix.Diagonal(
            (max(x1 - x0, 1e-4), max(y1 - y0, 1e-4), max(z1 - z0, 1e-4), 1)))

    def cylx(p, r, depth, mat, axis="y", seg=16):
        bm = pieces.setdefault(mat, bmesh.new())
        rot = Matrix.Rotation(math.pi / 2, 4, "X") if axis == "y" else Matrix.Identity(4)
        bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=depth, matrix=Matrix.Translation(p) @ rot)

    def sph(p, r, mat):
        bm = pieces.setdefault(mat, bmesh.new())
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=6, radius=r, matrix=Matrix.Translation(p))

    def ring(p, R, r, mat, axis="y"):
        bm = pieces.setdefault(mat, bmesh.new())
        tmp = bmesh.new()
        seg, rs = 16, 6
        vs = []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            for j in range(rs):
                b = 2 * math.pi * j / rs
                vs.append(tmp.verts.new(((R + r * math.cos(b)) * math.cos(a), r * math.sin(b), (R + r * math.cos(b)) * math.sin(a))))
        for i in range(seg):
            for j in range(rs):
                tmp.faces.new((vs[i * rs + j], vs[((i + 1) % seg) * rs + j], vs[((i + 1) % seg) * rs + (j + 1) % rs], vs[i * rs + (j + 1) % rs]))
        if axis == "x":
            bmesh.ops.rotate(tmp, verts=tmp.verts, matrix=Matrix.Rotation(math.pi / 2, 3, "Z"))
        bmesh.ops.translate(tmp, verts=tmp.verts, vec=Vector(p))
        me = bpy.data.meshes.new("r")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)

    def panels(rects, mat, depth=0.006, both=True):
        for yy, sg in ((-th, -1), (th, 1)) if both else ((-th, -1),):
            for x0, x1, z0, z1 in rects:
                a, b = sorted((yy, yy + sg * depth))
                q = 0.035
                bx(x0, x1, a, b, z0, z0 + q, mat)
                bx(x0, x1, a, b, z1 - q, z1, mat)
                bx(x0, x0 + q, a, b, z0 + q, z1 - q, mat)
                bx(x1 - q, x1, a, b, z0 + q, z1 - q, mat)
                a2, b2 = sorted((yy, yy + sg * depth * 0.6))
                bx(x0 + 0.07, x1 - 0.07, a2, b2, z0 + 0.07, z1 - 0.07, mat)

    if form is None:
        return None
    if form == "slab":                                   # the square doorway: a slab of black flush with the wall, nothing else
        bx(0.0, width, -0.004, 0.02, 0.0, height, "Void")
    elif form == "round-topped":
        r = w / 2
        n = 12
        bm = pieces.setdefault(fmat, bmesh.new())
        prof = [(0.003, 0.006), (w, 0.006)] + [(w / 2 + r * math.cos(math.pi * i / n), h - r + r * math.sin(math.pi * i / n)) for i in range(n + 1)]
        v0 = [bm.verts.new((x, -th, z)) for x, z in prof]
        v1 = [bm.verts.new((x, th, z)) for x, z in prof]
        bm.faces.new(v0[::-1])
        bm.faces.new(v1)
        for i in range(len(prof)):
            j = (i + 1) % len(prof)
            bm.faces.new((v0[i], v0[j], v1[j], v1[i]))
        panels([(0.12, w - 0.12, 0.2, h * 0.55)], fmat, 0.005)
    elif form == "frame":                                # an empty picture frame, door-sized: a deep gilt frame, its canvas the leaf
        bx(0.003, w, -0.01, th, 0.006, h, fmat)
        for x0, x1, z0, z1 in ((0.003, 0.1, 0.006, h), (w - 0.1, w, 0.006, h), (0.003, w, 0.006, 0.1), (0.003, w, h - 0.1, h)):
            bx(x0, x1, -0.07, th, z0, z1, "Frame_Wood")
        for x0, x1, z0, z1 in ((0.09, 0.12, 0.09, h - 0.09), (w - 0.12, w - 0.09, 0.09, h - 0.09), (0.09, w - 0.09, 0.09, 0.12), (0.09, w - 0.09, h - 0.12, h - 0.09)):
            bx(x0, x1, -0.05, -0.0, z0, z1, "Frame_Back")
    elif form == "sliding_pair":                         # two glass leaves in aluminium frames, meeting in the middle, chained
        for k in range(2):
            x0, x1 = (0.003, w / 2 - 0.005) if k == 0 else (w / 2 + 0.005, w)
            bx(x0, x1, -0.02, 0.02, 0.006, 0.12, "Alu")
            bx(x0, x1, -0.02, 0.02, h - 0.08, h, "Alu")
            bx(x0, x0 + 0.06, -0.02, 0.02, 0.12, h - 0.08, "Alu")
            bx(x1 - 0.06, x1, -0.02, 0.02, 0.12, h - 0.08, "Alu")
            bx(x0 + 0.06, x1 - 0.06, -0.006, 0.006, 0.12, h - 0.08, "Leaf_Glass")
            bx(x1 - 0.2 if k == 0 else x0 + 0.05, x1 - 0.05 if k == 0 else x0 + 0.2, -0.05, -0.02, 0.95, 1.05, "Alu")
    elif form == "flaps":                                # rubber strip curtain over a black steel frame
        bx(0.003, w, -0.03, 0.03, h - 0.12, h, "Iron")
        n = 7
        for i in range(n):
            x0 = 0.01 + i * (w - 0.02) / n
            bx(x0 + 0.004, x0 + (w - 0.02) / n - 0.004, -0.006 + (i % 2) * 0.012, 0.0 + (i % 2) * 0.012, 0.03, h - 0.12, fmat)
    else:
        bx(0.003, w, -th, th, 0.006, h, fmat)
        if form == "panelled":
            cx = w / 2
            panels([(0.1, cx - 0.04, 0.2, h * 0.45), (cx + 0.04, w - 0.1, 0.2, h * 0.45), (0.1, cx - 0.04, h * 0.5, h - 0.12),
                    (cx + 0.04, w - 0.1, h * 0.5, h - 0.12)], fmat)
        elif form == "six-panel":
            cx = w / 2
            rows = [(0.18, h * 0.36), (h * 0.4, h * 0.6), (h * 0.64, h - 0.12)]
            panels([(x0, x1, z0, z1) for z0, z1 in rows for x0, x1 in ((0.1, cx - 0.04), (cx + 0.04, w - 0.1))], fmat)
        elif form == "louvred":
            q = 0.07
            for x0, x1, z0, z1 in ((0.003, q, 0.006, h), (w - q, w, 0.006, h), (0.003, w, 0.006, 0.2), (0.003, w, h - 0.12, h), (0.003, w, h * 0.5 - 0.04, h * 0.5 + 0.04)):
                bx(x0, x1, -th - 0.006, th + 0.006, z0, z1, fmat)
            z = 0.24
            while z < h - 0.16:
                if abs(z - h * 0.5) > 0.06:
                    bx(q, w - q, -th - 0.004, -th + 0.004, z, z + 0.03, "Leaf_Glass")
                z += 0.065
        elif form == "half-glazed":
            panels([(0.1, w - 0.1, 0.2, h * 0.45)], fmat)
            bx(0.12, w - 0.12, -th - 0.002, th + 0.002, h * 0.52, h - 0.14, "Leaf_Glass")
            for x in (w / 3, 2 * w / 3):
                bx(x - 0.012, x + 0.012, -th - 0.008, th + 0.008, h * 0.52, h - 0.14, fmat)
        elif form == "ledged and braced":
            for i in range(1, 6):
                x = i * w / 6
                bx(x - 0.004, x + 0.004, -th - 0.002, -th + 0.002, 0.006, h, "Leaf_Glass")
            for z in (0.25, h / 2, h - 0.3):
                bx(0.05, w - 0.05, -th - 0.025, -th, z - 0.07, z + 0.07, fmat)
            bm = pieces.setdefault(fmat, bmesh.new())
            for za, zb in ((0.32, h / 2 - 0.08), (h / 2 + 0.08, h - 0.37)):
                L = math.hypot(w - 0.2, zb - za)
                bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, -th - 0.0125, (za + zb) / 2)) @ Matrix.Rotation(
                    math.atan2(zb - za, w - 0.2), 4, "Y").inverted() @ Matrix.Diagonal((L, 0.025, 0.1, 1)))
        elif form == "studded":
            for i in range(4):
                for j in range(7):
                    sph((0.15 + i * (w - 0.3) / 3, -th, 0.25 + j * (h - 0.5) / 6), 0.018, "Brass" if "brass" not in handle else "Chrome")
            panels([(0.08, w - 0.08, 0.1, h - 0.1)], fmat, 0.004, both=False)
        elif form == "quilted":
            for i in range(4):
                for j in range(7):
                    sph((0.13 + i * (w - 0.26) / 3, -th - 0.004, 0.22 + j * (h - 0.42) / 6), 0.02, fmat)
            for i in range(3):
                for j in range(6):
                    bx(0.13 + (i + 0.5) * (w - 0.26) / 3 - 0.09, 0.13 + (i + 0.5) * (w - 0.26) / 3 + 0.09, -th - 0.03, -th, 0.22 + (j + 0.5) * (h - 0.42) / 6 - 0.13,
                       0.22 + (j + 0.5) * (h - 0.42) / 6 + 0.13, fmat)
        elif form == "mirror-faced":
            bx(0.07, w - 0.07, -th - 0.004, -th, 0.12, h - 0.12, "Mirror")
            bx(0.07, w - 0.07, th, th + 0.004, 0.12, h - 0.12, "Mirror")
        elif form == "porthole":
            cylx((w / 2, 0.0, h * 0.68), 0.2, 2 * th + 0.01, "Leaf_Glass", seg=24)
            ring((w / 2, -th, h * 0.68), 0.21, 0.025, "Chrome")
            ring((w / 2, th, h * 0.68), 0.21, 0.025, "Chrome")
        elif form == "stable (split)":
            bx(0.003, w, -th - 0.01, th + 0.01, h * 0.48, h * 0.5, fmat)
            panels([(0.1, w - 0.1, 0.2, h * 0.44), (0.1, w - 0.1, h * 0.54, h - 0.12)], fmat)
        elif form == "flush":
            for x0, x1, z0, z1 in ((0.003, w, 0.006, 0.02), (0.003, w, h - 0.014, h)):
                bx(x0, x1, -th - 0.003, th + 0.003, z0, z1, fmat)
    # handles
    hx = w - 0.08
    hz = 0.98 if height > 1.2 else height * 0.45
    for yy, sg in ((-th, -1), (th, 1)):
        if handle == "brass knob" or handle == "glass knob":
            m = "Brass" if handle == "brass knob" else "Glass_Knob"
            cylx((hx, yy + sg * 0.004, hz), 0.032, 0.008, "Brass")
            cylx((hx, yy + sg * 0.03, hz), 0.009, 0.05, "Brass")
            sph((hx, yy + sg * 0.065, hz), 0.03, m)
        elif handle == "chrome lever":
            bx(hx - 0.022, hx + 0.022, *sorted((yy, yy + sg * 0.01)), hz - 0.09, hz + 0.09, "Chrome")
            bx(hx - 0.012, hx + 0.012, *sorted((yy, yy + sg * 0.055)), hz - 0.012, hz + 0.012, "Chrome")
            bx(hx - 0.14, hx + 0.012, *sorted((yy + sg * 0.045, yy + sg * 0.065)), hz - 0.012, hz + 0.012, "Chrome")
        elif handle == "push plate":
            bx(hx - 0.05, hx + 0.05, *sorted((yy, yy + sg * 0.004)), hz + 0.1, hz + 0.4, "Brass")
        elif handle == "ring pull":
            cylx((hx, yy + sg * 0.004, hz), 0.035, 0.008, "Iron")
            ring((hx, yy + sg * 0.02, hz - 0.06), 0.06, 0.008, "Iron", axis="x")
        elif handle == "push bar":
            bx(0.12, w - 0.06, *sorted((yy + sg * 0.05, yy + sg * 0.08)), hz - 0.03, hz + 0.03, "Chrome")
            for x in (0.14, w - 0.1):
                bx(x - 0.03, x + 0.03, *sorted((yy, yy + sg * 0.06)), hz - 0.06, hz + 0.06, "Chrome")
        elif handle == "laurel":
            ring((hx - 0.04, yy + sg * 0.03, hz + 0.05), 0.1, 0.012, "Laurel", axis="x")
            for i in range(10):
                a = 2 * math.pi * i / 10
                sph((hx - 0.04 + 0.1 * math.cos(a), yy + sg * 0.035, hz + 0.05 + 0.1 * math.sin(a)), 0.022, "Laurel")
    for ex in extras:
        if ex == "knocker":
            ring((w / 2, -th - 0.02, h * 0.66), 0.07, 0.012, "Brass", axis="x")
            cylx((w / 2, -th - 0.005, h * 0.72), 0.03, 0.012, "Brass")
        elif ex == "studs_edge":
            for z in np.linspace(0.08, h - 0.08, 18):
                for x in (0.05, w - 0.05):
                    sph((x, -th, float(z)), 0.012, "Brass")
        elif ex == "iron":
            for z in (0.35, h - 0.35):
                bx(0.02, w * 0.75, -th - 0.03, -th - 0.02, z - 0.03, z + 0.03, "Iron")
        elif ex == "grid_peel":
            for x0, x1, z0, z1 in ((0.15, 0.6, 1.2, 1.7), (0.4, 0.75, 0.4, 0.75)):
                bx(x0, x1, -th - 0.002, -th, z0, z1, "Grid_Emit")
                bx(x1 - 0.06, x1, -th - 0.05, -th - 0.002, z0, z1, "Paper_Back")
        elif ex == "meander":
            for zc in (0.12, h - 0.12):
                for i in range(int((w - 0.1) / 0.08)):
                    x = 0.05 + i * 0.08
                    bx(x, x + 0.06, -th - 0.008, -th, zc - 0.03, zc - 0.018, "Brass")
                    bx(x + 0.048, x + 0.06, -th - 0.008, -th, zc - 0.03, zc + 0.03, "Brass")
                    bx(x + 0.012, x + 0.06, -th - 0.008, -th, zc + 0.018, zc + 0.03, "Brass")
        elif ex == "vent_slots":
            for i in range(5):
                bx(0.15, w - 0.15, -th - 0.03, -th - 0.028, 1.6 + i * 0.07, 1.63 + i * 0.07, "Rubber_Black")
        elif ex == "chain":
            for i in range(9):
                ring((w / 2, -0.06, 1.0 + (i - 4) * 0.055), 0.025, 0.006, "Chrome", axis="x" if i % 2 else "y")
            bx(w / 2 - 0.04, w / 2 + 0.04, -0.09, -0.05, 0.7, 0.78, "Brass")
        elif ex == "staff_only":
            bm = pieces.setdefault("Plastic_White", bmesh.new())
            bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, -0.035, 1.75)) @ Matrix.Diagonal((0.5, 0.004, 0.14, 1)))
            tm = text_mesh("STAFF ONLY", 0.075, 0.002)
            tb = bmesh.new()
            tb.from_mesh(tm)
            bpy.data.meshes.remove(tm)
            bmesh.ops.transform(tb, matrix=Matrix(((1, 0, 0, w / 2), (0, 0, -1, -0.0395), (0, 1, 0, 1.75), (0, 0, 0, 1))), verts=tb.verts)
            m2 = bpy.data.meshes.new("s")
            tb.to_mesh(m2)
            tb.free()
            pieces.setdefault("Rubber_Black", bmesh.new()).from_mesh(m2)
            bpy.data.meshes.remove(m2)
    me = bpy.data.meshes.new(name)
    out = bmesh.new()
    out.loops.layers.uv.new("UVMap")
    mats = []
    for mat, pm in pieces.items():
        mats.append(mat)
        for f in pm.faces:
            f.material_index = len(mats) - 1
        bmesh.ops.recalc_face_normals(pm, faces=pm.faces)
        pm.loops.layers.uv.new("UVMap")
        t = TILES.get(mat, 1.0)
        uvl = pm.loops.layers.uv["UVMap"]
        for f in pm.faces:
            ax = max(range(3), key=lambda i: abs(f.normal[i]))
            for lp in f.loops:
                p = lp.vert.co
                u, v = (p.y, p.z) if ax == 0 else (p.x, p.z) if ax == 1 else (p.x, p.y)
                if mat == "Leaf_Canvas":
                    u, v = p.x / w, p.z / h
                    t = 1.0
                lp[uvl].uv = (u / t, v / t)
        m2 = bpy.data.meshes.new("p")
        pm.to_mesh(m2)
        pm.free()
        out.from_mesh(m2)
        bpy.data.meshes.remove(m2)
    out.to_mesh(me)
    out.free()
    for mat in mats:
        me.materials.append(MATS[mat])
    return me


def build_leaves(M):
    for d in M.doors:
        p = d["props"]
        me = leaf_mesh(d["name"], p["look"], p["width"], p["height"])
        if me is None:                                       # the arch: no leaf; the layout keeps its record as an empty
            ob = bpy.data.objects.new(d["name"], None)
            ob.empty_display_type = "ARROWS"
            ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
            LAYOUT.objects.link(ob)
        else:
            ob = bpy.data.objects.new(d["name"], me)
            ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
            DOORS.objects.link(ob)
        for k, v in p.items():
            ob[k] = v


def casings(mat, skip=(), width=0.1, proud=0.025):
    """An architrave round every door opening, on the room side (the story's frameless doors skipped)."""
    for d in model().doors:
        did = d["name"][len("DoorLeaf_"):]
        if did in skip:
            continue
        (hx, hy, hz), run, inw, w, h = door_geom(d)
        W, Ht = w + 0.04, h + 0.04
        a0 = (hx - run[0] * 0.02, hz - run[1] * 0.02)
        rects = []
        for t0, t1, y0, y1 in ((-width, 0.0, hy, hy + Ht + width), (W, W + width, hy, hy + Ht + width), (-width, W + width, hy + Ht, hy + Ht + width)):
            pa = (a0[0] + run[0] * t0, a0[1] + run[1] * t0)
            pb = (a0[0] + run[0] * t1, a0[1] + run[1] * t1)
            pc = (pa[0] + inw[0] * proud, pa[1] + inw[1] * proud)
            xs, zs = sorted((pa[0], pb[0], pc[0])), sorted((pa[1], pb[1], pc[1]))
            rects.append(((xs[0], y0, zs[0]), (xs[-1], y1, zs[-1])))
        boxes(f"decor_Casing_{did}", mat, rects)


def skirting(mat, runs, y, h=0.14, d=0.02, cuts_extra=(), name="decor_Skirting"):
    """Skirting boards: runs = [(axis, plane, inward sign, a0, a1)], cut round the door holes (and cuts_extra: (axis, plane, a0, a1))."""
    holes = []
    for dd in model().doors:
        (hx, hy, hz), run, inw, w, _ = door_geom(dd)
        holes.append((hx, hz, run, w))
    rects = []
    for axis, plane, sg, a0, a1 in runs:
        cuts = []
        for hx, hz, run, w in holes:
            if axis == "x" and abs(hz - plane) < 0.05:
                xa, xb = sorted((hx, hx + run[0] * w))
                cuts.append((xa - 0.12, xb + 0.12))
            if axis == "z" and abs(hx - plane) < 0.05:
                za, zb = sorted((hz, hz + run[1] * w))
                cuts.append((za - 0.12, zb + 0.12))
        cuts += [(c0, c1) for ax2, pl2, c0, c1 in cuts_extra if ax2 == axis and abs(pl2 - plane) < 0.05]
        segs, a = [], a0
        for c0, c1 in sorted(cuts):
            if c0 > a:
                segs.append((a, min(c0, a1)))
            a = max(a, c1)
        if a < a1:
            segs.append((a, a1))
        for s0, s1 in segs:
            if s1 - s0 < 0.05:
                continue
            q0, q1 = sorted((plane, plane + sg * d))
            rects.append(((s0, y, q0), (s1, y + h, q1)) if axis == "x" else ((q0, y, s0), (q1, y + h, s1)))
    return boxes(name, mat, rects) if rects else None


def room_runs(x0, x1, z0, z1):
    return [("x", z0, 1, x0, x1), ("x", z1, -1, x0, x1), ("z", x0, 1, z0, z1), ("z", x1, -1, z0, z1)]


# ---------------------------------------------------------------- lights
def light(name, kind, pos, power, color=WARM, size=0.1, aim=None, spot=None, coll=None, size_y=None):
    d = bpy.data.lights.new(name, kind)
    d.energy, d.color = power, color
    if kind == "AREA":
        d.shape = "RECTANGLE" if size_y else "DISK"
        d.size = size
        if size_y:
            d.size_y = size_y
    elif kind != "SUN":
        d.shadow_soft_size = size
    if spot:
        d.spot_size, d.spot_blend = math.radians(spot), 0.6
    ob = bpy.data.objects.new(name, d)
    ob.location = B(pos)
    if aim is not None:
        ob.rotation_euler = (B(aim) - B(pos)).to_track_quat("-Z", "Y").to_euler()
    (coll or LIGHTS).objects.link(ob)
    return ob


def down_light(name, pos, power, color=WARM, size=0.5, size_y=None, coll=None):
    return light(name, "AREA", pos, power, color, size, aim=(pos[0], pos[1] - 1, pos[2]), coll=coll, size_y=size_y)



# ================================================================ the prop kit (game coordinates; each prop one object, a material per part)
class Prop:
    def __init__(s, name, coll=None):
        s.name, s.coll, s.bms = name, coll, {}

    def bm(s, mat):
        return s.bms.setdefault(M(mat), bmesh.new())

    def box(s, mat, mn, mx):
        if all(mx[i] - mn[i] > 1e-5 for i in range(3)):
            cube(s.bm(mat), mn, mx)

    def cyl(s, mat, p0, p1, r0, r1=None, seg=16, cap=True):
        cyl(s.bm(mat), p0, p1, r0, r1, seg, cap)

    def sph(s, mat, p, r, seg=12, sy=1.0):
        sphere(s.bm(mat), p, r, seg, sy)

    def flip(s, H):
        """Mirror the prop upside down about the plane y = H (game), for the upside room."""
        for pm in s.bms.values():
            bmesh.ops.transform(pm, matrix=Matrix(((1, 0, 0, 0), (0, 1, 0, 0), (0, 0, -1, 2 * H), (0, 0, 0, 1))), verts=pm.verts)

    def done(s, coll=None):
        out = bmesh.new()
        out.loops.layers.uv.new("UVMap")
        mats = []
        for mat, pm in s.bms.items():
            bmesh.ops.recalc_face_normals(pm, faces=pm.faces)
            uvl = pm.loops.layers.uv.new("UVMap")
            t = TILES.get(mat, 1.0)
            for f in pm.faces:
                f.material_index = len(mats)
                ax = max(range(3), key=lambda i: abs(f.normal[i]))
                for lp in f.loops:
                    p = lp.vert.co
                    gx, gy, gz = p.x, p.z, -p.y
                    u, v = (gz, gy) if ax == 0 else (gx, gy) if ax == 1 else (gx, gz)
                    lp[uvl].uv = (u / t, v / t)
            mats.append(mat)
            me = bpy.data.meshes.new("tmp")
            pm.to_mesh(me)
            pm.free()
            out.from_mesh(me)
            bpy.data.meshes.remove(me)
        me = bpy.data.meshes.new(s.name)
        out.to_mesh(me)
        out.free()
        for m in mats:
            me.materials.append(MATS[m])
        ob = bpy.data.objects.new(s.name, me)
        (coll or s.coll or PROPS).objects.link(ob)
        return ob


def bb(b):
    return b["min"][0], b["max"][0], b["min"][1], b["max"][1], b["min"][2], b["max"][2]


def legs(P, mat, x0, x1, z0, z1, y0, y1, w=0.06, inset=0.03):
    for x in (x0 + inset, x1 - inset - w):
        for z in (z0 + inset, z1 - inset - w):
            P.box(mat, (x, y0, z), (x + w, y1, z + w))


def k_table(P, b, top, leg, cloth=None, th=0.05):
    x0, x1, y0, y1, z0, z1 = bb(b)
    P.box(top, (x0, y1 - th, z0), (x1, y1, z1))
    P.box(leg, (x0 + 0.06, y1 - th - 0.09, z0 + 0.06), (x1 - 0.06, y1 - th, z1 - 0.06))
    legs(P, leg, x0, x1, z0, z1, y0, y1 - th, w=min(0.08, (x1 - x0) / 8), inset=0.04)
    if cloth:
        P.box(cloth, (x0 + 0.005, y1 - 0.32, z0 + 0.005), (x1 - 0.005, y1 + 0.006, z1 - 0.005))


def k_chair(P, b, face, frame, seat, back_h=None, seat_h=None):
    """A chair filling its box, facing `face` ((1, 0) = the seat's front toward +x): legs, a cushion, a back on the far side."""
    x0, x1, y0, y1, z0, z1 = bb(b)
    s = min(x1 - x0, z1 - z0) / 0.5
    sh = seat_h or min(0.47 * s, (y1 - y0) * 0.5)
    lw = 0.045 * s
    legs(P, frame, x0, x1, z0, z1, y0, sh - 0.06 * s, w=lw, inset=0.01 * s)
    P.box(frame, (x0, sh - 0.07 * s, z0), (x1, sh - 0.04 * s, z1))
    P.box(seat, (x0 + 0.01 * s, sh - 0.04 * s, z0 + 0.01 * s), (x1 - 0.01 * s, sh + 0.03 * s, z1 - 0.01 * s))
    top = back_h or y1
    t = 0.05 * s
    fx, fz = face
    if fx > 0:
        ra = (x0, x0 + t, z0, z1)
    elif fx < 0:
        ra = (x1 - t, x1, z0, z1)
    elif fz > 0:
        ra = (x0, x1, z0, z0 + t)
    else:
        ra = (x0, x1, z1 - t, z1)
    a0, a1, c0, c1 = ra
    if fx:
        for c in (c0, c1 - lw):
            P.box(frame, (a0, sh, c), (a1, top, c + lw))
        P.box(seat, (a0 + (t * 0.2 if fx > 0 else -t * 0.2), sh + 0.12 * s, c0 + lw), (a1 + (t * 0.3 if fx > 0 else -t * 0.3), top - 0.04 * s, c1 - lw))
        P.box(frame, (a0, top - 0.05 * s, c0), (a1, top, c1))
    else:
        for a in (a0, a1 - lw):
            P.box(frame, (a, sh, c0), (a + lw, top, c1))
        P.box(seat, (a0 + lw, sh + 0.12 * s, c0 + (t * 0.2 if fz > 0 else -t * 0.2)), (a1 - lw, top - 0.04 * s, c1 + (t * 0.3 if fz > 0 else -t * 0.3)))
        P.box(frame, (a0, top - 0.05 * s, c0), (a1, top, c1))


def k_counter(P, b, face, body, top, handle="Chrome", kick="Rubber_Black", top_th=0.04, doors=0.6):
    x0, x1, y0, y1, z0, z1 = bb(b)
    fx, fz = face
    ki = 0.06
    kb = (x0 + (ki if fx > 0 else 0), x1 - (ki if fx < 0 else 0), z0 + (ki if fz > 0 else 0), z1 - (ki if fz < 0 else 0))
    P.box(kick, (kb[0], y0, kb[2]), (kb[1], y0 + 0.1, kb[3]))
    P.box(body, (x0, y0 + 0.1, z0), (x1, y1 - top_th, z1))
    if top:
        P.box(top, (x0, y1 - top_th, z0), (x1, y1, z1))
    run = (x1 - x0) if fz else (z1 - z0)
    n = max(1, int(round(run / doors)))
    for i in range(1, n):
        a = (x0 if fz else z0) + run * i / n
        if fz:
            zz = z1 if fz > 0 else z0
            P.box("Rubber_Black", (a - 0.004, y0 + 0.12, min(zz, zz + 0.004 * fz)), (a + 0.004, y1 - top_th - 0.03, max(zz, zz + 0.004 * fz)))
        else:
            xx = x1 if fx > 0 else x0
            P.box("Rubber_Black", (min(xx, xx + 0.004 * fx), y0 + 0.12, a - 0.004), (max(xx, xx + 0.004 * fx), y1 - top_th - 0.03, a + 0.004))
    for i in range(n):
        a = (x0 if fz else z0) + run * (i + 0.5) / n + run / n * 0.32
        hy = y1 - top_th - 0.12
        if fz:
            zz = z1 if fz > 0 else z0
            P.box(handle, (a - 0.008, hy - 0.08, min(zz, zz + 0.02 * fz)), (a + 0.008, hy, max(zz, zz + 0.02 * fz)))
        else:
            xx = x1 if fx > 0 else x0
            P.box(handle, (min(xx, xx + 0.02 * fx), hy - 0.08, a - 0.008), (max(xx, xx + 0.02 * fx), hy, a + 0.008))


def k_fridge(P, b, face, body="Enamel_Cream"):
    x0, x1, y0, y1, z0, z1 = bb(b)
    P.box(body, (x0, y0 + 0.04, z0), (x1, y1, z1))
    P.box("Rubber_Black", (x0 + 0.02, y0, z0 + 0.02), (x1 - 0.02, y0 + 0.04, z1 - 0.02))
    fx, fz = face
    sy = y0 + (y1 - y0) * 0.62
    if fz:
        zz = z1 if fz > 0 else z0
        P.box("Rubber_Black", (x0, sy - 0.006, min(zz, zz + 0.005 * fz)), (x1, sy + 0.006, max(zz, zz + 0.005 * fz)))
        for ya, yb in ((sy + 0.08, sy + 0.38), (sy - 0.38, sy - 0.08)):
            P.box("Chrome", (x1 - 0.1, ya, min(zz, zz + 0.04 * fz)), (x1 - 0.07, yb, max(zz, zz + 0.04 * fz)))
    else:
        xx = x1 if fx > 0 else x0
        P.box("Rubber_Black", (min(xx, xx + 0.005 * fx), sy - 0.006, z0), (max(xx, xx + 0.005 * fx), sy + 0.006, z1))
        for ya, yb in ((sy + 0.08, sy + 0.38), (sy - 0.38, sy - 0.08)):
            P.box("Chrome", (min(xx, xx + 0.04 * fx), ya, z1 - 0.1), (max(xx, xx + 0.04 * fx), yb, z1 - 0.07))


def k_sideboard(P, b, face, body, top="Marble_Top", handle="Brass"):
    x0, x1, y0, y1, z0, z1 = bb(b)
    lh = 0.14 * (y1 - y0) / 0.9
    legs(P, body, x0, x1, z0, z1, y0, y0 + lh, w=0.05, inset=0.03)
    P.box(body, (x0, y0 + lh, z0), (x1, y1 - 0.03, z1))
    P.box(top, (x0, y1 - 0.03, z0), (x1, y1, z1))
    fx, fz = face
    run = (x1 - x0) if fz else (z1 - z0)
    n = max(2, int(round(run / 0.7)))
    for i in range(n):
        a = (x0 if fz else z0) + run * (i + 0.5) / n
        for hy in (y0 + lh + (y1 - y0 - lh) * 0.3, y0 + lh + (y1 - y0 - lh) * 0.72):
            if fz:
                zz = z1 if fz > 0 else z0
                P.box(handle, (a - 0.05, hy - 0.008, min(zz, zz + 0.02 * fz)), (a + 0.05, hy + 0.008, max(zz, zz + 0.02 * fz)))
            else:
                xx = x1 if fx > 0 else x0
                P.box(handle, (min(xx, xx + 0.02 * fx), hy - 0.008, a - 0.05), (max(xx, xx + 0.02 * fx), hy + 0.008, a + 0.05))


def k_bench(P, b, wood="Walnut", seat=None):
    x0, x1, y0, y1, z0, z1 = bb(b)
    long_x = (x1 - x0) >= (z1 - z0)
    P.box(seat or wood, (x0, y1 - 0.06, z0), (x1, y1, z1))
    for k in (0, 1):
        if long_x:
            xa = x0 + 0.08 if k == 0 else x1 - 0.14
            P.box(wood, (xa, y0, z0 + 0.04), (xa + 0.06, y1 - 0.06, z1 - 0.04))
        else:
            za = z0 + 0.08 if k == 0 else z1 - 0.14
            P.box(wood, (x0 + 0.04, y0, za), (x1 - 0.04, y1 - 0.06, za + 0.06))
    if long_x:
        P.box(wood, (x0 + 0.1, y0 + 0.12, (z0 + z1) / 2 - 0.02), (x1 - 0.1, y0 + 0.18, (z0 + z1) / 2 + 0.02))
    else:
        P.box(wood, ((x0 + x1) / 2 - 0.02, y0 + 0.12, z0 + 0.1), ((x0 + x1) / 2 + 0.02, y0 + 0.18, z1 - 0.1))


def k_plant(P, b, seed=1):
    x0, x1, y0, y1, z0, z1 = bb(b)
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    r = min(x1 - x0, z1 - z0) / 2
    ph = min(0.42, (y1 - y0) * 0.32)
    P.cyl("Pot_Clay", (cx, y0, cz), (cx, y0 + ph, cz), r * 0.72, r, seg=24)
    P.cyl("Soil", (cx, y0 + ph - 0.03, cz), (cx, y0 + ph - 0.01, cz), r * 0.86, seg=20)
    rnd = random.Random(seed)
    for i in range(9):
        a = rnd.uniform(0, 2 * math.pi)
        d = rnd.uniform(0.0, r * 0.45)
        y = y0 + ph + (y1 - y0 - ph) * rnd.uniform(0.35, 0.8)
        rr = r * rnd.uniform(0.32, 0.5)
        P.sph("Leaf_Plant", (cx + d * math.cos(a), min(y, y1 - rr), cz + d * math.sin(a)), rr, seg=8, sy=0.8)
    P.cyl("Leaf_Plant", (cx, y0 + ph, cz), (cx, y0 + ph + (y1 - y0 - ph) * 0.5, cz), 0.015, seg=6)
    P.sph("Leaf_Plant", (cx, y1 - r * 0.35, cz), r * 0.35, seg=8, sy=1.0)


def k_books_row(P, x0, x1, y0, h, z0, z1, along_x=True, mat="Books"):
    P.box(mat, (x0, y0, z0), (x1, y0 + h, z1))


def k_bookshelf(P, b, face, frame="Paint_White", shelves=5, books="Books"):
    x0, x1, y0, y1, z0, z1 = bb(b)
    fx, fz = face
    t = 0.025
    if fx:
        P.box(frame, (x0, y0, z0), (x1, y1, z0 + t))
        P.box(frame, (x0, y0, z1 - t), (x1, y1, z1))
        bx0, bx1 = (x0, x0 + 0.015) if fx > 0 else (x1 - 0.015, x1)
        P.box(frame, (bx0, y0, z0), (bx1, y1, z1))
    else:
        P.box(frame, (x0, y0, z0), (x0 + t, y1, z1))
        P.box(frame, (x1 - t, y0, z0), (x1, y1, z1))
        bz0, bz1 = (z0, z0 + 0.015) if fz > 0 else (z1 - 0.015, z1)
        P.box(frame, (x0, y0, bz0), (x1, y1, bz1))
    for i in range(shelves + 1):
        y = y0 + (y1 - y0 - t) * i / shelves
        P.box(frame, (x0, y, z0), (x1, y + t, z1))
        if i < shelves:
            hh = (y1 - y0) / shelves * 0.78
            if fx:
                P.box(books, (x0 + 0.03, y + t, z0 + t + 0.01), (x1 - 0.05, y + t + hh, z1 - t - 0.01))
            else:
                P.box(books, (x0 + t + 0.01, y + t, z0 + 0.03), (x1 - t - 0.01, y + t + hh, z1 - 0.05))


def k_chest(P, b, body, lid, band="Brass"):
    x0, x1, y0, y1, z0, z1 = bb(b)
    P.box(body, (x0, y0, z0), (x1, y1 - 0.12, z1))
    P.box(lid, (x0, y1 - 0.12, z0), (x1, y1, z1))
    for k in (0.25, 0.75):
        x = x0 + (x1 - x0) * k
        P.box(band, (x - 0.02, y0 + 0.02, z0 - 0.0), (x + 0.02, y1 + 0.004, z0 + 0.012))
        P.box(band, (x - 0.02, y0 + 0.02, z1 - 0.012), (x + 0.02, y1 + 0.004, z1))


def k_boxes(P, b, seed=1, photos=True):
    """A stack of cardboard boxes in its box: two or three, a little askew in size, the top one open on photographs."""
    x0, x1, y0, y1, z0, z1 = bb(b)
    rnd = random.Random(seed)
    H = y1 - y0
    n = 1 if H < 0.6 else 2 if H < 1.0 else 3
    y = y0
    for i in range(n):
        h = H / n
        ix, iz = rnd.uniform(0.0, 0.08) * (i > 0), rnd.uniform(0.0, 0.08) * (i > 0)
        bx0, bx1, bz0, bz1 = x0 + ix, x1 - ix * 0.5, z0 + iz * 0.5, z1 - iz
        P.box("Cardboard", (bx0, y, bz0), (bx1, y + h - 0.004, bz1))
        P.box("Tape", ((bx0 + bx1) / 2 - 0.03, y + h - 0.004, bz0), ((bx0 + bx1) / 2 + 0.03, y + h, bz1))
        y += h
    if photos:
        for k in range(4):
            px, pz = rnd.uniform(x0 + 0.1, x1 - 0.25), rnd.uniform(z0 + 0.1, z1 - 0.2)
            P.box("Photo", (px, y1, pz), (px + 0.15, y1 + 0.004 + k * 0.002, pz + 0.1))


def k_radiator(P, b, mat="Radiator"):
    x0, x1, y0, y1, z0, z1 = bb(b)
    along_x = (x1 - x0) > (z1 - z0)
    run = (x1 - x0) if along_x else (z1 - z0)
    n = int(run / 0.08)
    for i in range(n):
        a = (x0 if along_x else z0) + i * run / n
        if along_x:
            P.box(mat, (a + 0.01, y0 + 0.1, z0), (a + run / n - 0.01, y1, z1))
        else:
            P.box(mat, (x0, y0 + 0.1, a + 0.01), (x1, y1, a + run / n - 0.01))
    if along_x:
        for y in (y0 + 0.12, y1 - 0.05):
            P.box(mat, (x0, y, z0 + 0.02), (x1, y + 0.04, z1 - 0.02))
        legs(P, mat, x0, x1, z0, z1, y0, y0 + 0.1, w=0.03, inset=0.05)
    else:
        for y in (y0 + 0.12, y1 - 0.05):
            P.box(mat, (x0 + 0.02, y, z0), (x1 - 0.02, y + 0.04, z1))
        legs(P, mat, x0, x1, z0, z1, y0, y0 + 0.1, w=0.03, inset=0.05)


def k_crate(P, b, wood="Crate_Wood"):
    x0, x1, y0, y1, z0, z1 = bb(b)
    P.box(wood, (x0 + 0.03, y0 + 0.03, z0 + 0.03), (x1 - 0.03, y1 - 0.03, z1 - 0.03))
    w = 0.07
    for xa, xb in ((x0, x0 + w), (x1 - w, x1)):
        for za, zb in ((z0, z0 + w), (z1 - w, z1)):
            P.box("Walnut", (xa, y0, za), (xb, y1, zb))
    for y in (y0, y1 - w):
        P.box("Walnut", (x0, y, z0), (x1, y + w, z0 + w))
        P.box("Walnut", (x0, y, z1 - w), (x1, y + w, z1))
        P.box("Walnut", (x0, y, z0), (x0 + w, y + w, z1))
        P.box("Walnut", (x1 - w, y, z0), (x1, y + w, z1))


def k_pillar(P, b, mat="Marble_Prop", cap="Trim_White"):
    x0, x1, y0, y1, z0, z1 = bb(b)
    P.box(cap, (x0, y0, z0), (x1, y0 + 0.18, z1))
    P.box(mat, (x0 + 0.05, y0 + 0.18, z0 + 0.05), (x1 - 0.05, y1 - 0.2, z1 - 0.05))
    P.box(cap, (x0, y1 - 0.2, z0), (x1, y1, z1))


def k_plinth(P, b, mat="Marble_Prop", cap="Trim_White"):
    x0, x1, y0, y1, z0, z1 = bb(b)
    P.box(cap, (x0, y0, z0), (x1, y0 + 0.08, z1))
    P.box(mat, (x0 + 0.04, y0 + 0.08, z0 + 0.04), (x1 - 0.04, y1 - 0.06, z1 - 0.04))
    P.box(cap, (x0, y1 - 0.06, z0), (x1, y1, z1))


def k_upholstered(P, b, mat, tuft=None, piping=None, buttons=0, top_buttons=True):
    """A padded block: the box, rounded a little with a lip at its top edge, and buttons on its top (or its biggest vertical face)."""
    x0, x1, y0, y1, z0, z1 = bb(b)
    e = min(0.06 * max(1.0, (y1 - y0) / 2.0), 0.25)
    P.box(mat, (x0 + e, y0, z0 + e), (x1 - e, y1, z1 - e))
    P.box(mat, (x0, y0, z0 + e), (x1, y1 - e, z1 - e))
    P.box(mat, (x0 + e, y0, z0), (x1 - e, y1 - e, z1))
    for cx, cz in ((x0 + e, z0 + e), (x1 - e, z0 + e), (x0 + e, z1 - e), (x1 - e, z1 - e)):
        P.cyl(mat, (cx, y0, cz), (cx, y1 - e, cz), e, seg=10)
    if piping:
        P.box(piping, (x0 + e * 0.6, y1 - e * 0.55, z0 + e * 0.6), (x1 - e * 0.6, y1 - e * 0.45, z1 - e * 0.6))
    if buttons and tuft:
        nx = max(1, int((x1 - x0) / (0.45 * max(1.0, (y1 - y0) / 2.0))))
        nz = max(1, int((z1 - z0) / (0.45 * max(1.0, (y1 - y0) / 2.0))))
        r = min(0.025 * max(1.0, (y1 - y0) / 1.5), 0.12)
        for i in range(nx):
            for j in range(nz):
                P.sph(tuft, (x0 + (i + 0.5) * (x1 - x0) / nx, y1, z0 + (j + 0.5) * (z1 - z0) / nz), r, seg=8, sy=0.5)


# ---------------------------------------------------------------- room-wide pieces
def furn():
    return [b for b in model().boxes if b.get("col") and is_furniture(b)]


CLAIMED = set()


def gdecor(name):
    b = next(b for b in model().boxes if b["name"] == "decor_" + name)
    CLAIMED.add(b["name"])
    return b


def decor_rest(mapping):
    """Every greybox decor box not dressed by name gets a plain box in a material by its greybox colour."""
    for b in model().boxes:
        if b["col"] or b.get("zone") or not b["name"].startswith("decor_") or b["name"] in CLAIMED:
            continue
        P = Prop(b["name"])
        P.box(mapping.get(b["mat"], "Plastic_White"), b["min"], b["max"])
        P.done()


def dims():
    rf = gbx("Room_Floor") if any(b["name"] == "Room_Floor" for b in model().boxes) else None
    if rf:
        return rf["min"][0] + GB.T, rf["max"][0] - GB.T, rf["min"][2] + GB.T, rf["max"][2] - GB.T
    raise KeyError("no Room_Floor")


def cornice(mat, x0, x1, z0, z1, H, h=0.12, d=0.06, name="decor_Cornice"):
    boxes(name, M(mat), [((x0, H - h, z0), (x1, H, z0 + d)), ((x0, H - h, z1 - d), (x1, H, z1)), ((x0, H - h, z0), (x0 + d, H, z1)),
                         ((x1 - d, H - h, z0), (x1, H, z1))])


def dado(mat, x0, x1, z0, z1, y, h=0.05, d=0.02):
    skirting(M(mat), room_runs(x0, x1, z0, z1), y, h=h, d=d, name="decor_Dado")


def standard_room(trim, x0=None, x1=None, z0=None, z1=None, H=None, dado_y=None, skip=()):
    if x0 is None:
        x0, x1, z0, z1 = dims()
    casings(M(trim), skip=skip)
    if dado_y:
        dado(trim, x0, x1, z0, z1, dado_y)
    skirting(M(trim), room_runs(x0, x1, z0, z1), 0.0, h=0.14)
    if H:
        cornice(trim, x0, x1, z0, z1, H)


def frame_on_wall(P, side, a, y0, y1, w, plane, mat_pic="Photo", frame="Frame_Gilt", d=0.04):
    """A framed picture on a wall: side N/S/W/E names the wall (its inner face at `plane`), centred on `a` along it."""
    t = 0.05
    if side in "NS":
        sg = 1 if side == "N" else -1
        za, zb = sorted((plane, plane + sg * d))
        P.box(frame, (a - w / 2, y0, za), (a + w / 2, y1, zb))
        zc = plane + sg * (d + 0.002)
        za2, zb2 = sorted((plane + sg * d * 0.5, zc))
        P.box(mat_pic, (a - w / 2 + t, y0 + t, za2), (a + w / 2 - t, y1 - t, zb2))
    else:
        sg = 1 if side == "W" else -1
        xa, xb = sorted((plane, plane + sg * d))
        P.box(frame, (xa, y0, a - w / 2), (xb, y1, a + w / 2))
        xc = plane + sg * (d + 0.002)
        xa2, xb2 = sorted((plane + sg * d * 0.5, xc))
        P.box(mat_pic, (xa2, y0 + t, a - w / 2 + t), (xb2, y1 - t, a + w / 2 - t))


def sconce(P, side, a, y, plane):
    sg = {"N": 1, "S": -1, "W": 1, "E": -1}[side]
    if side in "NS":
        za, zb = sorted((plane, plane + sg * 0.05))
        P.box("Brass", (a - 0.07, y - 0.12, za), (a + 0.07, y + 0.05, zb))
        P.cyl("Lamp_Emit", (a, y, plane + sg * 0.14), (a, y + 0.22, plane + sg * 0.14), 0.09, 0.12, seg=14)
    else:
        xa, xb = sorted((plane, plane + sg * 0.05))
        P.box("Brass", (xa, y - 0.12, a - 0.07), (xb, y + 0.05, a + 0.07))
        P.cyl("Lamp_Emit", (plane + sg * 0.14, y, a), (plane + sg * 0.14, y + 0.22, a), 0.09, 0.12, seg=14)


def wall_light(name, side, a, y, plane, power=25.0, color=WARM):
    off = {"N": (0, 0.35), "S": (0, -0.35), "W": (0.35, 0), "E": (-0.35, 0)}[side]
    if side in "NS":
        return light(name, "POINT", (a, y + 0.1, plane + off[1]), power, color, size=0.12)
    return light(name, "POINT", (plane + off[0], y + 0.1, a), power, color, size=0.12)


def ceiling_panels(name, x0, x1, z0, z1, H, nx, nz, pw=0.6, pd=0.6, power=60.0, color=WARM, emit=True):
    P = Prop(name)
    for i in range(nx):
        for j in range(nz):
            cx, cz = x0 + (i + 0.5) * (x1 - x0) / nx, z0 + (j + 0.5) * (z1 - z0) / nz
            if emit:
                P.box("Lamp_Emit", (cx - pw / 2, H - 0.02, cz - pd / 2), (cx + pw / 2, H, cz + pd / 2))
                P.box("Chrome", (cx - pw / 2 - 0.03, H - 0.012, cz - pd / 2 - 0.03), (cx + pw / 2 + 0.03, H - 0.002, cz + pd / 2 + 0.03))
            down_light(f"{name}_{i}_{j}", (cx, H - 0.05, cz), power, color, size=pw, size_y=pd)
    if emit:
        P.done()


def pendant(name, x, z, y_lo, H, power=40.0, shade="Lamp_Emit", r=0.25, color=WARM):
    P = Prop(name)
    P.cyl("Rubber_Black", (x, y_lo + 0.25, z), (x, H, z), 0.006, seg=6)
    P.cyl(shade, (x, y_lo, z), (x, y_lo + 0.25, z), r, r * 0.35, seg=20)
    P.done()
    light(name + "_L", "POINT", (x, y_lo - 0.05, z), power, color, size=0.12)

def uv_quads(name, mat, quads, coll=None):
    """One object of quads with their own UVs: quads = [(4 game points, 4 (u, v))], counter-clockwise seen from the front."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    for pts, uvs in quads:
        f = bm.faces.new([bm.verts.new(B(p)) for p in pts])
        for lp, (u, v) in zip(f.loops, uvs):
            lp[uvl].uv = (u, v)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[M(mat)])
    ob = bpy.data.objects.new(name, me)
    (coll or PROPS).objects.link(ob)
    return ob


def wall_quad(side, plane, a0, a1, y0, y1, off=0.004):
    """The 4 corners (counter-clockwise from the room) of a rectangle on a wall's inner face; side N/S/W/E, `plane` the face."""
    if side == "N":
        z = plane + off
        return [(a0, y0, z), (a1, y0, z), (a1, y1, z), (a0, y1, z)]
    if side == "S":
        z = plane - off
        return [(a1, y0, z), (a0, y0, z), (a0, y1, z), (a1, y1, z)]
    if side == "W":
        x = plane + off
        return [(x, y0, a1), (x, y0, a0), (x, y1, a0), (x, y1, a1)]
    x = plane - off
    return [(x, y0, a0), (x, y0, a1), (x, y1, a1), (x, y1, a0)]


def cell_uv(i, j, k=4):
    u0, v0 = j / k, i / k
    return [(u0, v0), (u0 + 1 / k, v0), (u0 + 1 / k, v0 + 1 / k), (u0, v0 + 1 / k)]


def pictures(name, items, frame="Frame_Gilt", atlas="Photo", k=4, seed=3, cell=None):
    """Framed pictures on the walls: items = [(side, plane, a, y0, y1, w)]; each frame a box, each picture a quad from the atlas."""
    rnd = random.Random(seed)
    P = Prop("decor_" + name + "_Frames")
    quads = []
    for side, plane, a, y0, y1, w in items:
        sg = {"N": 1, "S": -1, "W": 1, "E": -1}[side]
        d = 0.035
        if side in "NS":
            za, zb = sorted((plane, plane + sg * d))
            P.box(frame, (a - w / 2, y0, za), (a + w / 2, y1, zb))
        else:
            xa, xb = sorted((plane, plane + sg * d))
            P.box(frame, (xa, y0, a - w / 2), (xb, y1, a + w / 2))
        quads.append((wall_quad(side, plane, a - w / 2 + 0.06, a + w / 2 - 0.06, y0 + 0.06, y1 - 0.06, off=d + 0.003),
                      cell_uv(*(cell or (rnd.randrange(k), rnd.randrange(k))), k)))
    P.done()
    uv_quads("decor_" + name + "_Pictures", atlas, quads)


def text_on(P, mat, body, size, depth, origin, right, up):
    nrm = (right[1] * up[2] - right[2] * up[1], right[2] * up[0] - right[0] * up[2], right[0] * up[1] - right[1] * up[0])
    add_text(P.bm(mat), body, size, depth, origin, right, up, nrm)


def dress_furn(rules, trick=()):
    """Every furniture box gets the first rule whose prefix it starts with: (prefix, builder(P, b)); names in `trick` become Trick_<name>."""
    for b in furn():
        fn = next((f for pre, f in rules if b["name"].startswith(pre)), None)
        nm = ("Trick_" + b["name"]) if b["name"].startswith(tuple(trick)) else b["name"]
        P = Prop(nm)
        if fn is None:
            print("  no builder for", b["name"], "- a plain block")
            P.box("Plastic_White", b["min"], b["max"])
        else:
            fn(P, b)
        P.done()


SPEC["Ceil_Prop"] = dict(tex=PLASTER, hex="#fff2e6", rough=0.95, tile=2.6)


# ================================================================ the rooms
def dress_long_table():
    X, Z, H = 4.0, 17.0, 3.2
    standard_room("Trim_Cream", -X, X, -Z, Z, H, dado_y=0.95)

    def chair(P, b):
        k_chair(P, b, (1, 0) if b["name"].startswith("Chair_W") else (-1, 0), T("Maple_Dark"), T("Velvet_Red"))

    def far(P, b):
        if b["name"].endswith("Back"):
            x0, x1, y0, y1, z0, z1 = bb(b)
            k_upholstered(P, {"min": [x0 + 0.08, y0 + 1.25, z0], "max": [x1 - 0.08, y1 - 0.08, z1]}, "Velvet_Red", "Brass", buttons=1)
            for x in (x0, x1 - 0.1):
                P.box("Maple_Dark", (x, y0, z0), (x + 0.1, y1, z1))
            P.box("Maple_Dark", (x0, y1 - 0.1, z0), (x1, y1, z1))
            P.box("Maple_Dark", (x0, y0, z0), (x1, y0 + 1.25, z1))
        else:
            x0, x1, y0, y1, z0, z1 = bb(b)
            legs(P, "Maple_Dark", x0, x1, z0, z1, y0, y1 - 0.35, w=0.16, inset=0.02)
            P.box("Maple_Dark", (x0, y1 - 0.38, z0), (x1, y1 - 0.25, z1))
            k_upholstered(P, {"min": [x0 + 0.03, y1 - 0.25, z0 + 0.03], "max": [x1 - 0.03, y1, z1 - 0.03]}, "Velvet_Red", "Brass", buttons=1)

    dress_furn([("Table_", lambda P, b: k_table(P, b, "Maple", "Maple_Dark")), ("Chair_", chair), ("Far_Chair", far),
                ("Sideboard_W", lambda P, b: k_sideboard(P, b, (1, 0), "Walnut")), ("Sideboard_E", lambda P, b: k_sideboard(P, b, (-1, 0), "Walnut"))],
               trick=("Chair_",))
    gdecor("Runner")
    boxes("decor_Runner", M("Linen_White"), [((-0.35, 0.8, -13.9), (0.35, 0.806, 13.9))])
    # the place settings: a plate, a glass and a candle at every chair, growing with it
    P = Prop("decor_Settings")
    for k in range(7):
        z = -12.0 + k * 4.0
        s = (0.55 + 0.75 * (6 - k) / 6) / 0.55
        hw = [1.2, 1.2, 1.1, 1.0, 1.0, 0.9, 0.9][k]
        for sg in (-1, 1):
            x = sg * (hw - 0.2 * s)
            P.cyl("China", (x, 0.8, z), (x, 0.812, z), 0.13 * s, seg=24)
            P.cyl("China_Rim", (x, 0.812, z), (x, 0.815, z), 0.1 * s, seg=24)
            P.cyl("Glass_Clear", (x - sg * 0.02, 0.8, z - 0.22 * s), (x - sg * 0.02, 0.8 + 0.13 * s, z - 0.22 * s), 0.035 * s, seg=12)
        if k == 6:
            continue
        P.cyl("Brass", (0, 0.806, z + 2.0), (0, 0.84, z + 2.0), 0.07 * s, seg=12)
        P.cyl("Brass", (0, 0.84, z + 2.0), (0, 0.84 + 0.22 * s, z + 2.0), 0.02 * s, seg=8)
        P.cyl("Candle", (0, 0.84 + 0.22 * s, z + 2.0), (0, 1.0 + 0.3 * s, z + 2.0), 0.022 * s, seg=8)
    P.done()
    for k in range(5):
        z = -11.0 + k * 5.5
        gdecor(f"Chandelier_{k + 1}")
        P = Prop(f"decor_Chandelier_{k + 1}")
        P.cyl("Brass", (0, 2.95, z), (0, H, z), 0.012, seg=6)
        P.cyl("Brass", (0, 2.55, z), (0, 2.95, z), 0.04, 0.02, seg=12)
        P.cyl("Brass", (0, 2.52, z), (0, 2.58, z), 0.42, 0.42, seg=24)
        for a in range(8):
            t = a * math.pi / 4
            cx, cz = 0.4 * math.cos(t), z + 0.4 * math.sin(t)
            P.cyl("Brass", (cx, 2.58, cz), (cx, 2.64, cz), 0.03, seg=8)
            P.cyl("Lamp_Emit", (cx, 2.64, cz), (cx, 2.76, cz), 0.018, seg=6)
        P.done()
        light(f"Chandelier_L{k}", "POINT", (0, 2.7, z), 70.0, WARM, size=0.35)
    pictures("Portraits", [("W", -X, z, 1.35, 2.35, 0.8) for z in (-14.0, -6.0, 2.0, 14.5)] + [("E", X, z, 1.35, 2.35, 0.8) for z in (-14.0, -6.0, 2.0)]
             + [("S", Z, x, 1.5, 2.5, 0.9) for x in (-2.6, 2.6)], seed=11)
    for k in range(6):
        down_light(f"Fill_{k}", (0, H - 0.05, -14.5 + k * 5.8), 55.0, WARM, size=1.2, size_y=3.0)
    decor_rest({})


def dress_tiny_kitchen():
    X, Z, H = 5.0, 4.0, 3.0
    standard_room("Trim_Mint", -X, X, -Z, Z, H)

    def counter(face):
        return lambda P, b: k_counter(P, b, face, "Paint_Mint", "Marble_Top")
    dress_furn([("Counter_N", counter((0, 1))), ("Counter_Small", counter((0, 1))), ("Counter_S", counter((0, -1))),
                ("Sink_Small", counter((0, -1))), ("Fridge", lambda P, b: k_fridge(P, b, (0, 1))),
                ("Table", lambda P, b: k_table(P, b, "Walnut", "Walnut", cloth="Linen_Red")),
                ("Chair_1", lambda P, b: k_chair(P, b, (1, 0), "Chrome", "Paint_Red")), ("Chair_2", lambda P, b: k_chair(P, b, (0, -1), "Chrome", "Paint_Red")),
                ("Chair_Small_1", lambda P, b: k_chair(P, b, (1, 0), "Chrome", "Paint_Red")),
                ("Chair_Small_2", lambda P, b: k_chair(P, b, (-1, 0), "Chrome", "Paint_Red"))])
    gdecor("Ceiling_Drop")
    P = Prop("decor_Ceiling_Drop")
    P.box("Ceil_Prop", (-X, 2.0, -Z), (-1.0, 2.04, Z))
    P.box("Trim_Mint", (-1.06, 2.0, -Z), (-1.0, H, Z))
    P.done()
    for nm, face in (("Cabinets_N", (0, 1)), ("Cabinets_Small", (0, 1))):
        b = gdecor(nm)
        P = Prop("decor_" + nm)
        k_counter(P, b, face, "Paint_Mint", None, kick="Paint_Mint", top_th=0.0, doors=0.5 if nm.endswith("N") else 0.25)
        P.done()
    # the stove and the sinks, the same at both sizes
    P = Prop("decor_Appliances")
    for s, (sx, sz, top) in ((1.0, (0.4, -3.7, 0.92)), (0.5, (-2.6, -3.82, 0.48))):
        P.box("Plastic_Black", (sx - 0.35 * s, top, sz - 0.25 * s), (sx + 0.35 * s, top + 0.012, sz + 0.25 * s))
        for dx, dz in ((-0.17, -0.1), (0.17, -0.1), (-0.17, 0.12), (0.17, 0.12)):
            P.cyl("Iron", (sx + dx * s, top + 0.012, sz + dz * s), (sx + dx * s, top + 0.02, sz + dz * s), 0.08 * s, seg=16)
        P.cyl("Chrome", (sx + 0.9 * s, top, sz), (sx + 0.9 * s, top + 0.24 * s, sz), 0.1 * s, 0.08 * s, seg=16)
    for s, (sx, sz, top) in ((1.0, (2.6, 3.7, 0.92)), (0.5, (-3.0, 3.8, 0.48))):
        P.box("Chrome", (sx - 0.35 * s, top, sz - 0.2 * s), (sx + 0.35 * s, top + 0.01, sz + 0.2 * s))
        P.cyl("Chrome", (sx, top, sz + 0.22 * s), (sx, top + 0.3 * s, sz + 0.22 * s), 0.015 * s, seg=8)
        for i in range(4):
            P.cyl("China", (sx + 0.55 * s, top + i * 0.012 * s, sz), (sx + 0.55 * s, top + (i + 1) * 0.012 * s, sz), 0.12 * s, seg=20)
    P.done()
    for nm, (x0, x1, y0, y1) in (("Window_S", (1.6, 3.6, 1.25, 2.35)), ("Window_Small", (-3.6, -2.4, 0.7, 1.3))):
        gdecor(nm)
        uv_quads("decor_" + nm, "Window_Lit", [(wall_quad("S", Z, x0, x1, y0, y1), [(0, 0), (1, 0), (1, 1), (0, 1)])])
        P = Prop("decor_" + nm + "_Frame")
        t = 0.05 if nm == "Window_S" else 0.025
        for a0, a1, b0, b1 in ((x0 - t, x1 + t, y0 - t, y0), (x0 - t, x1 + t, y1, y1 + t), (x0 - t, x0, y0, y1), (x1, x1 + t, y0, y1), ((x0 + x1) / 2 - t / 2, (x0 + x1) / 2 + t / 2, y0, y1)):
            P.box("Trim_Mint", (a0, b0, Z - 0.04), (a1, b1, Z))
        P.done()
    gdecor("Pendant")
    pendant("decor_Pendant", 1.7, 0.1, 2.15, H, power=45.0)
    boxes("decor_Tiles_Small", M("Tiles_Small"), [((-X, 0.0, -Z), (-1.0, 0.003, Z))])
    ceiling_panels("decor_Panels", 0.0, 4.6, -3.0, 3.0, H, 2, 2, power=40.0)
    ceiling_panels("decor_Panels_Small", -4.4, -1.6, -2.6, 2.6, 2.0, 1, 2, pw=0.3, pd=0.3, power=14.0)
    light("Window_S_L", "AREA", (2.6, 1.8, Z - 0.1), 40.0, COOL, size=2.0, aim=(2.6, 1.6, 0.0), size_y=1.1)
    decor_rest({})


def dress_birthday_party():
    X, Z, H = 7.0, 5.0, 3.2
    standard_room("Trim_Peach", -X, X, -Z, Z, H, dado_y=1.0)

    def chair(P, b):
        n = b["name"]
        face = (0, 1) if "_N_" in n else (0, -1) if "_S_" in n else (1, 0) if n.endswith("_W") else (-1, 0)
        k_chair(P, b, face, "Chrome", "Paint_White")

    def gifts(P, b):
        x0, x1, y0, y1, z0, z1 = bb(b)
        rnd = random.Random(5)
        cols = ["Gift_Pink", "Gift_Cyan", "Gift_Lime", "Gift_Violet"]
        P.box(cols[0], (x0, y0, z0), (x1, y0 + 0.35, z1))
        for i in range(6):
            w, d, h = rnd.uniform(0.3, 0.7), rnd.uniform(0.3, 0.7), rnd.uniform(0.15, 0.4)
            gx, gz = rnd.uniform(x0, x1 - w), rnd.uniform(z0, z1 - d)
            yb = y0 + 0.35 if i < 4 else y0 + 0.35 + 0.0
            P.box(cols[(i + 1) % 4], (gx, yb, gz), (gx + w, min(yb + h, y1), gz + d))
            P.box("Ribbon_Gold", (gx + w / 2 - 0.02, yb, gz - 0.002), (gx + w / 2 + 0.02, min(yb + h, y1) + 0.004, gz + d + 0.002))
        P.box("Ribbon_Gold", ((x0 + x1) / 2 - 0.03, y0, z0 - 0.002), ((x0 + x1) / 2 + 0.03, y0 + 0.355, z1 + 0.002))
        P.box(cols[2], (x1 - 0.5, y0 + 0.35, z1 - 0.5), (x1 - 0.05, y1, z1 - 0.05))

    def piano(P, b):
        x0, x1, y0, y1, z0, z1 = bb(b)
        P.box("Piano_Black", (x0 + 0.25, y0, z0), (x1, y1, z1))
        P.box("Piano_Black", (x0, y0 + 0.65, z0), (x0 + 0.25, y0 + 0.72, z1))
        P.box("Keys_White", (x0 + 0.02, y0 + 0.72, z0 + 0.05), (x0 + 0.25, y0 + 0.74, z1 - 0.05))
        n = int((z1 - z0 - 0.1) / 0.06)
        for i in range(n):
            if i % 7 in (0, 1, 3, 4, 5):
                z = z0 + 0.05 + i * 0.06 + 0.045
                P.box("Piano_Black", (x0 + 0.1, y0 + 0.74, z - 0.012), (x0 + 0.25, y0 + 0.755, z + 0.012))
        P.box("Piano_Black", (x0, y0 + 0.72, z0), (x0 + 0.25, y0 + 0.8, z0 + 0.05))
        P.box("Piano_Black", (x0, y0 + 0.72, z1 - 0.05), (x0 + 0.25, y0 + 0.8, z1))
        legs(P, "Piano_Black", x0, x0 + 0.25, z0, z1, y0, y0 + 0.65, w=0.05, inset=0.01)
    dress_furn([("Party_Table", lambda P, b: k_table(P, b, "Paint_White", "Paint_White", cloth="Linen_Pink")), ("Chair_", chair),
                ("Gift_Pile", gifts), ("Punch_Table", lambda P, b: k_table(P, b, "Paint_White", "Paint_White", cloth="Linen_White")),
                ("Piano", piano)])
    gdecor("Cake")
    P = Prop("decor_Cake")
    P.cyl("China", (0, 0.76, 0), (0, 0.8, 0), 0.4, seg=32)
    P.cyl("Icing", (0, 0.8, 0), (0, 1.0, 0), 0.32, seg=32)
    P.cyl("Icing_Pink", (0, 0.88, 0), (0, 0.92, 0), 0.325, seg=32)
    P.cyl("Icing", (0, 1.0, 0), (0, 1.14, 0), 0.22, seg=32)
    for i in range(9):
        a = i * 2 * math.pi / 9
        cx, cz = 0.15 * math.cos(a), 0.15 * math.sin(a)
        P.cyl("Candle", (cx, 1.14, cz), (cx, 1.24, cz), 0.008, seg=6)
    P.done()
    # the places: a plate, a hat, a name card at each chair
    P = Prop("decor_Places")
    for x, z, rot in [(x, -0.55, 1) for x in (-2.25, -0.75, 0.75, 2.25)] + [(x, 0.55, -1) for x in (-2.25, -0.75, 0.75, 2.25)] + [(-2.7, 0, 0), (2.7, 0, 0)]:
        P.cyl("China", (x, 0.766, z), (x, 0.776, z), 0.12, seg=20)
        P.cyl(["Gift_Pink", "Gift_Cyan", "Gift_Lime", "Gift_Violet"][int(abs(x * 2 + z * 3)) % 4], (x + 0.12, 0.766, z + 0.1 * rot), (x + 0.12, 0.98, z + 0.1 * rot), 0.07, 0.003, seg=12)
        P.box("Note_Card", (x - 0.08, 0.766, z - 0.17 * (rot or 1) - 0.01), (x + 0.08, 0.83, z - 0.17 * (rot or 1) + 0.01))
    P.done()
    P = Prop("decor_Balloons")
    cols = ["Balloon_Pink", "Balloon_Cyan", "Balloon_Lime", "Balloon_Violet"]
    for k in range(14):
        b = gdecor(f"Balloon_{k + 1}")
        cx, cz = (b["min"][0] + b["max"][0]) / 2, (b["min"][2] + b["max"][2]) / 2
        P.sph(cols[k % 4], (cx, 2.88, cz), 0.21, seg=14, sy=1.2)
        P.box("Paper", (cx - 0.003, 1.9 + (k % 3) * 0.2, cz - 0.003), (cx + 0.003, 2.63, cz + 0.003))
    P.done()
    gdecor("Banner")
    P = Prop("decor_Banner")
    for i in range(15):
        x = -4.2 + i * 0.6
        P.box(cols[i % 4].replace("Balloon", "Gift"), (x - 0.18, 2.55 - 0.08 * math.sin(i / 14 * math.pi), -Z + 0.01), (x + 0.18, 2.85 - 0.08 * math.sin(i / 14 * math.pi), -Z + 0.02))
    text_on(P, "Paint_Violet", "HAPPY BIRTHDAY", 0.32, 0.02, (0.0, 2.2, -Z + 0.015), (1, 0, 0), (0, 1, 0))
    P.done()
    P = Prop("decor_Punch")
    P.cyl("Glass_Clear", (-3.5, 0.806, 4.67), (-3.5, 1.0, 4.67), 0.12, 0.2, seg=20)
    for i in range(5):
        P.cyl("Plastic_White", (-4.6 + i * 0.18, 0.806, 4.6), (-4.6 + i * 0.18, 0.9, 4.6), 0.035, 0.04, seg=10)
    P.done()
    # fairy lights round the room under the cornice, and the streamers
    P = Prop("decor_Fairy_Lights")
    for side, plane, a0, a1 in (("N", -Z, -X, X), ("S", Z, -X, X), ("W", -X, -Z, Z), ("E", X, -Z, Z)):
        n = int((a1 - a0) / 0.35)
        for i in range(n):
            a = a0 + (i + 0.5) * (a1 - a0) / n
            y = H - 0.3 - 0.08 * math.sin((i % 6) / 5 * math.pi)
            p = (a, y, plane + (0.06 if side == "N" else -0.06)) if side in "NS" else (plane + (0.06 if side == "W" else -0.06), y, a)
            P.sph("Lamp_Emit", p, 0.025, seg=6)
    P.done()
    pendant("decor_Pendant", 0.0, 0.0, 2.3, H, power=60.0, r=0.35)
    for k, (x, z) in enumerate(((-4.5, -2.5), (4.5, -2.5), (-4.5, 2.5), (4.5, 2.5))):
        down_light(f"Fill_{k}", (x, H - 0.05, z), 45.0, WARM, size=1.5)
    for k, x in enumerate((-5.0, 0.0, 5.0)):
        light(f"Fairy_{k}", "AREA", (x, H - 0.35, -Z + 0.3), 20.0, (1.0, 0.75, 0.55), size=3.0, aim=(x, 0.0, 0.0), size_y=0.3)
    decor_rest({})


def dress_attic():
    X, Z, H = 6.0, 4.0, 2.6
    casings(M("Trim_Dark"))
    # the roof: plank slopes over the eaves up to the ceiling's flat, rafters every 1.2 m, a ridge purlin
    P = Prop("decor_Roof")
    for sg in (-1, 1):
        prism(P.bm("Pine"), [(sg * 3.2, 1.1), (sg * 3.2, 1.06), (sg * 2.4, 2.56), (sg * 2.4, 2.6)], -X, X, axis="x")
        for i in range(11):
            x = -X + 0.5 + i * 1.1
            prism(P.bm("Walnut"), [(sg * 3.24, 1.08), (sg * 3.24, 0.96), (sg * 2.36, 2.6), (sg * 2.24, 2.6)], x - 0.05, x + 0.05, axis="x")
    for z in (-1.2, 1.2):
        P.box("Walnut", (-X, H - 0.16, z - 0.07), (X, H, z + 0.07))
    P.done()
    standard_trim = M("Trim_Dark")
    skirting(standard_trim, room_runs(-X, X, -Z, Z), 0.0, h=0.12)
    dress_furn([("Photo_Boxes_", lambda P, b: k_boxes(P, b, seed=int(b["name"][-1]))), ("Trunk", lambda P, b: k_chest(P, b, "Walnut", "Walnut")),
                ("Dress_Form", dress_form), ("Rocking_Horse", rocking_horse), ("Mirror", mirror_leaning)])
    gdecor("Hatch")
    P = Prop("decor_Hatch")
    for a0, a1, b0, b1 in ((-0.7, 0.7, -0.7, -0.6), (-0.7, 0.7, 0.6, 0.7), (-0.7, -0.6, -0.6, 0.6), (0.6, 0.7, -0.6, 0.6)):
        P.box("Walnut", (a0, 0.0, b0), (a1, 0.03, b1))
    P.box("Void", (-0.6, 0.0, -0.6), (0.6, 0.004, 0.6))
    P.box("Pine", (-0.6, 0.02, -0.72), (0.6, 0.06, -0.7))
    P.done()
    gdecor("Bulb")
    P = Prop("decor_Bulb")
    P.cyl("Rubber_Black", (0, 2.1, 0), (0, H, 0), 0.005, seg=6)
    P.cyl("Brass", (0, 2.04, 0), (0, 2.1, 0), 0.018, seg=8)
    P.sph("Lamp_Emit", (0, 2.0, 0), 0.04, seg=10)
    P.done()
    light("Bulb_L", "POINT", (0.0, 1.95, 0.0), 45.0, (1.0, 0.72, 0.45), size=0.06)
    gdecor("Gable_Window")
    uv_quads("decor_Gable_Window", "Window_Lit", [(wall_quad("E", X, -0.9, 0.9, 1.2, 2.3), [(0, 0), (1, 0), (1, 1), (0, 1)])])
    P = Prop("decor_Gable_Frame")
    for a0, a1, b0, b1 in ((-0.96, 0.96, 1.14, 1.2), (-0.96, 0.96, 2.3, 2.36), (-0.96, -0.9, 1.2, 2.3), (0.9, 0.96, 1.2, 2.3), (-0.03, 0.03, 1.2, 2.3), (-0.9, 0.9, 1.72, 1.78)):
        P.box("Walnut", (X - 0.05, b0, a0), (X, b1, a1))
    P.done()
    light("Gable_L", "AREA", (X - 0.15, 1.75, 0.0), 30.0, COOL, size=1.6, aim=(0.0, 0.6, 0.0), size_y=1.0)
    P = Prop("decor_Spilled_Photos")
    rnd = random.Random(9)
    quads = []
    for i in range(22):
        cx, cz = rnd.uniform(-5.5, -2.8), rnd.uniform(-1.6, 1.4)
        if abs(cx + 4.0) < 0.35 and abs(cz + 0.6) < 0.35:
            continue
        a = rnd.uniform(0, math.pi)
        dx, dz = 0.09 * math.cos(a), 0.09 * math.sin(a)
        ex, ez = -0.065 * math.sin(a), 0.065 * math.cos(a)
        y = 0.002 + i * 0.0004
        quads.append(([(cx - dx - ex, y, cz - dz - ez), (cx - dx + ex, y, cz - dz + ez), (cx + dx + ex, y, cz + dz + ez), (cx + dx - ex, y, cz + dz - ez)],
                      cell_uv(rnd.randrange(4), rnd.randrange(4))))
    P.done()
    uv_quads("decor_Photos_Floor", "Photo", quads)
    for k, x in enumerate((-3.6, 3.6)):
        down_light(f"Fill_{k}", (x, H - 0.05, 0.0), 22.0, (1.0, 0.8, 0.6), size=1.6)
    decor_rest({})


def dress_form(P, b):
    x0, x1, y0, y1, z0, z1 = bb(b)
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    for a in range(3):
        t = a * 2 * math.pi / 3
        P.cyl("Walnut", (cx, y0 + 0.3, cz), (cx + 0.22 * math.cos(t), y0, cz + 0.22 * math.sin(t)), 0.015, seg=6)
    P.cyl("Iron", (cx, y0 + 0.3, cz), (cx, y0 + 1.0, cz), 0.015, seg=8)
    P.sph("Linen_White", (cx, y0 + 1.3, cz), 0.22, seg=14, sy=1.5)
    P.cyl("Walnut", (cx, y1 - 0.06, cz), (cx, y1, cz), 0.04, seg=10)


def rocking_horse(P, b):
    x0, x1, y0, y1, z0, z1 = bb(b)
    cz = (z0 + z1) / 2
    for z in (z0 + 0.08, z1 - 0.08):
        for i in range(8):
            xa, xb = x0 + i * (x1 - x0) / 8, x0 + (i + 1) * (x1 - x0) / 8
            ya = y0 + 0.12 * (((xa + xb) / 2 - (x0 + x1) / 2) / ((x1 - x0) / 2)) ** 2
            P.box("Paint_Red", (xa, ya, z - 0.03), (xb, ya + 0.05, z + 0.03))
    for x in (x0 + 0.25, x1 - 0.25):
        for z in (z0 + 0.1, z1 - 0.1):
            P.box("Horse_White", (x - 0.03, y0 + 0.05, z - 0.03), (x + 0.03, y0 + 0.55, z + 0.03))
    P.box("Horse_White", (x0 + 0.2, y0 + 0.5, cz - 0.15), (x1 - 0.2, y0 + 0.75, cz + 0.15))
    P.box("Paint_Red", (x0 + 0.38, y0 + 0.75, cz - 0.16), (x0 + 0.62, y0 + 0.79, cz + 0.16))
    P.box("Horse_White", (x1 - 0.3, y0 + 0.7, cz - 0.08), (x1 - 0.12, y1, cz + 0.08))
    P.box("Horse_White", (x1 - 0.12, y1 - 0.18, cz - 0.07), (x1, y1 - 0.04, cz + 0.07))
    P.box("Walnut", (x1 - 0.32, y1 - 0.25, cz - 0.02), (x1 - 0.22, y1 + 0.0, cz + 0.02))


def mirror_leaning(P, b):
    x0, x1, y0, y1, z0, z1 = bb(b)
    P.box("Frame_Gilt", (x0, y0, z0), (x0 + 0.08, y1, z1))
    P.box("Mirror", (x0 - 0.004, y0 + 0.08, z0 + 0.08), (x0 + 0.004, y1 - 0.08, z1 - 0.08))
    P.box("Walnut", (x0 + 0.08, y0, z0 + 0.1), (x1, y0 + 0.06, z0 + 0.16))
    P.box("Walnut", (x0 + 0.08, y0, z1 - 0.16), (x1, y0 + 0.06, z1 - 0.1))


def dress_kids_bedroom():
    X, Z, H = 4.0, 4.0, 2.8
    standard_room("Trim_White", -X, X, -Z, Z, H)

    def bed(P, b):
        x0, x1, y0, y1, z0, z1 = bb(b)
        legs(P, "Paint_White", x0, x1, z0, z1, y0, y0 + 0.2, w=0.06, inset=0.02)
        P.box("Paint_White", (x0, y0 + 0.2, z0), (x1, y0 + 0.32, z1))
        P.box("Linen_White", (x0 + 0.04, y0 + 0.32, z0 + 0.15), (x1 - 0.04, y0 + 0.5, z1 - 0.04))
        P.box("Linen_Cyan", (x0 + 0.02, y0 + 0.36, z0 + 0.75), (x1 - 0.02, y1, z1 - 0.02))
        P.box("Linen_Yellow", (x0 + 0.02, y1 - 0.1, z0 + 0.75), (x1 - 0.02, y1 + 0.004, z0 + 1.05))
        P.box("Linen_White", (x0 + 0.25, y0 + 0.5, z0 + 0.22), (x1 - 0.25, y0 + 0.64, z0 + 0.62))
        P.box("Paint_White", (x0, y0, z0), (x1, y0 + 1.1, z0 + 0.12))
        P.box("Paint_Cyan", (x0 + 0.1, y0 + 0.55, z0 + 0.12), (x1 - 0.1, y0 + 0.95, z0 + 0.13))
        P.box("Paint_White", (x0, y0, z1 - 0.08), (x1, y0 + 0.65, z1))
    dress_furn([("Bed", bed), ("Toy_Chest", lambda P, b: k_chest(P, b, "Paint_Yellow", "Paint_Red", band="Paint_Cyan")),
                ("Desk_Chair", lambda P, b: k_chair(P, b, (0, -1), "Paint_Red", "Paint_Red")),
                ("Desk", lambda P, b: k_table(P, b, "Paint_White", "Paint_White")), ("Bookshelf", lambda P, b: k_bookshelf(P, b, (1, 0))),
                ("Nightstand", lambda P, b: k_sideboard(P, b, (0, 1), "Paint_White", top="Paint_White"))])
    gdecor("Ceiling_Hatch")
    boxes("decor_Ceiling_Hatch", M("Paint_White"), [((-0.65, H - 0.03, -0.65), (0.65, H - 0.005, -0.58)), ((-0.65, H - 0.03, 0.58), (0.65, H - 0.005, 0.65)),
                                                   ((-0.65, H - 0.03, -0.58), (-0.58, H - 0.005, 0.58)), ((0.58, H - 0.03, -0.58), (0.65, H - 0.005, 0.58)),
                                                   ((-0.58, H - 0.012, -0.58), (0.58, H - 0.004, 0.58)), ((0.3, 2.2, 0.3), (0.31, H - 0.012, 0.31))])
    gdecor("Glow_Stars")
    rnd = random.Random(17)
    P = Prop("decor_Glow_Stars")
    for i in range(60):
        x, z = rnd.uniform(-3.7, 3.7), rnd.uniform(-3.7, 3.7)
        if abs(x) < 0.7 and abs(z) < 0.7:
            continue
        r = rnd.uniform(0.04, 0.09)
        P.box("Stars_Glow", (x - r, H - 0.006, z - r * 0.25), (x + r, H - 0.002, z + r * 0.25))
        P.box("Stars_Glow", (x - r * 0.25, H - 0.006, z - r), (x + r * 0.25, H - 0.002, z + r))
    P.done()
    gdecor("Rug")
    boxes("decor_Rug", M("Rug_Pink"), [((-1.4, 0.0, -0.4), (1.6, 0.012, 2.2))])
    gdecor("Notes")
    P = Prop("decor_Notes")
    for i in range(7):
        x, z = -3.35 + i * 0.2, -0.92 + (i % 3) * 0.12
        P.box("Note_Card", (x, 0.001 + i * 0.0005, z), (x + 0.15, 0.003 + i * 0.0005, z + 0.1))
        for t in range(4):
            P.box("Plastic_Black", (x + 0.02 + t * 0.025, 0.0035 + i * 0.0005, z + 0.02), (x + 0.026 + t * 0.025, 0.0045 + i * 0.0005, z + 0.08))
    P.done()
    uv_quads("decor_Posters", "Poster", [(wall_quad("E", X, 0.6, 1.5, 1.2, 2.4), cell_uv(0, 0, 2)), (wall_quad("E", X, 1.9, 2.8, 1.2, 2.4), cell_uv(0, 1, 2)),
                                         (wall_quad("S", Z, -2.6, -1.6, 1.1, 2.3), cell_uv(1, 0, 2)), (wall_quad("W", -X, -3.0, -2.0, 1.2, 2.2), cell_uv(1, 1, 2))])
    P = Prop("decor_Toys")
    rnd = random.Random(23)
    for i in range(9):
        x, z = rnd.uniform(-1.2, 1.8), rnd.uniform(1.2, 3.4)
        s = rnd.uniform(0.07, 0.12)
        P.box(["Paint_Red", "Paint_Yellow", "Paint_Cyan", "Paint_Lime"][i % 4], (x, 0.012, z), (x + s, 0.012 + s, z + s))
    P.cyl("Paint_White", (2.6, 0.75, -3.75), (2.6, 0.78, -3.75), 0.08, seg=12)
    P.cyl("Paint_Red", (2.6, 0.78, -3.75), (2.6, 1.1, -3.75), 0.05, 0.005, seg=12)
    P.cyl("Lamp_Emit", (-1.45, 0.55, -3.75), (-1.45, 0.75, -3.75), 0.09, 0.06, seg=14)
    P.done()
    light("Bedside_L", "POINT", (-1.45, 0.85, -3.6), 12.0, WARM, size=0.08)
    light("Desk_L", "POINT", (2.6, 1.15, -3.5), 10.0, (1.0, 0.75, 0.6), size=0.05)
    pendant("decor_Pendant", 1.8, 1.4, 2.25, H, power=40.0, r=0.22)
    down_light("Fill_0", (-1.8, H - 0.05, 1.8), 25.0, (0.85, 0.88, 1.0), size=1.4)
    light("Window_Moon", "AREA", (0.0, 1.6, Z - 0.15), 12.0, COOL, size=2.0, aim=(0.0, 1.0, 0.0), size_y=1.0)
    decor_rest({})


def dress_giant_chair():
    X, Z, H = 8.0, 7.0, 8.0
    casings(M("Trim_Cream"))
    skirting(M("Trim_Cream"), room_runs(-X, X, -Z, Z), 0.0, h=0.62, d=0.08)
    cornice("Trim_Cream", -X, X, -Z, Z, H, h=0.5, d=0.25)

    def chairpart(P, b):
        n = b["name"]
        x0, x1, y0, y1, z0, z1 = bb(b)
        if n == "Chair_Back":
            k_upholstered(P, b, "Velvet_Orange", piping="Velvet_Orange_Tuft")
            for i in range(5):
                for j in range(4):
                    P.sph("Velvet_Orange_Tuft", (x0 + 1.0 + i * (x1 - x0 - 2.0) / 4, y0 + 3.6 + j * 0.85, z1), 0.08, seg=8, sy=0.6)
        elif n.startswith("Chair_Arm"):
            k_upholstered(P, {"min": [x0, y0, z0], "max": [x1, y1 - 0.45, z1]}, "Velvet_Orange")
            P.cyl("Velvet_Orange", ((x0 + x1) / 2, y1 - 0.8, z0), ((x0 + x1) / 2, y1 - 0.8, z1), (x1 - x0) / 2, seg=20)
            P.cyl("Velvet_Orange_Tuft", ((x0 + x1) / 2, y1 - 0.8, z1 - 0.01), ((x0 + x1) / 2, y1 - 0.8, z1 + 0.0), (x1 - x0) / 2 * 0.7, seg=20)
        else:
            P.box("Walnut", (x0, y0, z0), (x1, y0 + 0.8, z1))
            k_upholstered(P, {"min": [x0, y0 + 0.8, z0], "max": [x1, y1, z1]}, "Velvet_Orange", piping="Velvet_Orange_Tuft")

    covers = ["Cover_Red", "Cover_Blue", "Cover_Green", "Cover_Yellow", "Cover_Violet"]

    def book(P, x0, x1, y0, y1, z0, z1, k):
        c = covers[k % len(covers)]
        P.box(c, (x0, y0, z0), (x1, y0 + 0.025, z1))
        P.box(c, (x0, y1 - 0.025, z0), (x1, y1, z1))
        P.box(c, (x0, y0, z0), (x0 + 0.03, y1, z1))
        P.box("Pages", (x0 + 0.03, y0 + 0.025, z0 + 0.012), (x1 - 0.012, y1 - 0.025, z1 - 0.012))
        P.box("Ribbon_Gold", (x0 - 0.002, y0 + 0.08, z0 + 0.0), (x0 + 0.002, y1 - 0.08, z1))

    def steps(P, b):
        x0, x1, y0, y1, z0, z1 = bb(b)
        i = int(b["name"][-2:])
        n = max(1, round((y1 - y0) / 0.25))
        for j in range(n):
            book(P, x0, x1, y0 + j * (y1 - y0) / n, y0 + (j + 1) * (y1 - y0) / n, z0, z1, i + j * 2)

    def ledge(P, b):
        x0, x1, y0, y1, z0, z1 = bb(b)
        P.box("Walnut", (x0 + 0.15, y0 + 0.4, z0 + 0.15), (x1 - 0.15, y1 - 0.5, z1 - 0.15))
        legs(P, "Walnut", x0, x1, z0, z1, y0, y1 - 0.5, w=0.28, inset=0.0)
        k_upholstered(P, {"min": [x0, y1 - 0.5, z0], "max": [x1, y1, z1]}, "Velvet_Green", "Brass", buttons=1)

    def lamp(P, b):
        x0, x1, y0, y1, z0, z1 = bb(b)
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        if b["name"] == "Lamp_Base":
            P.cyl("Brass", (cx, y0, cz), (cx, y1, cz), (x1 - x0) / 2, (x1 - x0) / 2 * 0.8, seg=32)
        else:
            P.cyl("Brass", (cx, y0, cz), (cx, y1, cz), (x1 - x0) / 2 * 0.6, seg=16)
            for y in (y0 + 1.0, y0 + 3.0):
                P.cyl("Brass", (cx, y, cz), (cx, y + 0.12, cz), (x1 - x0) / 2, seg=16)

    def remote(P, b):
        x0, x1, y0, y1, z0, z1 = bb(b)
        P.box("Plastic_Black", (x0, y0, z0), (x1, y1, z1))
        for i in range(4):
            for j in range(3):
                P.cyl("Paint_Red" if (i, j) == (0, 1) else "Plastic_White", (x0 + 0.4 + i * 0.5, y1, z0 + 0.2 + j * 0.2), (x0 + 0.4 + i * 0.5, y1 + 0.03, z0 + 0.2 + j * 0.2), 0.07, seg=12)

    def mug(P, b):
        x0, x1, y0, y1, z0, z1 = bb(b)
        P.cyl("China", ((x0 + x1) / 2, y0, (z0 + z1) / 2), ((x0 + x1) / 2, y0 + 0.05, (z0 + z1) / 2), (z1 - z0) / 2, seg=40)
        r = (x1 - x0) / 2 - 0.15
        cx, cz = x0 + r, (z0 + z1) / 2
        P.cyl("Mug_White", (cx, y0, cz), (cx, y1, cz), r, seg=32)
        P.cyl("Walnut", (cx, y1 - 0.15, cz), (cx, y1 - 0.14, cz), r - 0.05, seg=32)
        P.box("Mug_White", (cx + r - 0.05, y0 + 0.35, cz - 0.08), (x1, y0 + 0.5, cz + 0.08))
        P.box("Mug_White", (cx + r - 0.05, y1 - 0.5, cz - 0.08), (x1, y1 - 0.35, cz + 0.08))
        P.box("Mug_White", (x1 - 0.12, y0 + 0.35, cz - 0.08), (x1, y1 - 0.35, cz + 0.08))
    dress_furn([("Chair_", chairpart), ("Step_cushions", steps), ("Fill_cushions", steps), ("Ledge", ledge), ("Lamp_", lamp),
                ("Remote", remote), ("Mug", mug)])
    gdecor("Lamp_Shade")
    P = Prop("decor_Lamp_Shade")
    P.cyl("Lamp_Emit", (6.4, 5.4, -6.0), (6.4, 7.0, -6.0), 1.15, 0.85, seg=40)
    P.done()
    light("Lamp_L", "POINT", (6.4, 5.6, -6.0), 700.0, WARM, size=0.5)
    gdecor("Window_W")
    uv_quads("decor_Window_W", "Window_Lit", [(wall_quad("W", -X, -2.0, 3.0, 2.0, 6.2), [(0, 0), (1, 0), (1, 1), (0, 1)])])
    P = Prop("decor_Window_Frame")
    for a0, a1, b0, b1 in ((-2.15, 3.15, 1.85, 2.0), (-2.15, 3.15, 6.2, 6.35), (-2.15, -2.0, 2.0, 6.2), (3.0, 3.15, 2.0, 6.2), (0.44, 0.56, 2.0, 6.2), (-2.0, 3.0, 4.05, 4.15)):
        P.box("Trim_Cream", (-X, b0, a0), (-X + 0.1, b1, a1))
    P.box("Linen_Pink", (-X, 1.0, -3.2), (-X + 0.25, H - 0.6, -2.3))
    P.box("Linen_Pink", (-X, 1.0, 3.3), (-X + 0.25, H - 0.6, 4.2))
    P.done()
    light("Window_L", "AREA", (-X + 0.3, 4.1, 0.5), 260.0, COOL, size=5.0, aim=(0.0, 1.0, 0.5), size_y=4.2)
    gdecor("Rug")
    boxes("decor_Rug", M("Rug_Lilac"), [((-6.0, 0.0, 0.8), (6.0, 0.015, 6.4))])
    pictures("Giant_Frame", [("E", X, 2.0, 2.2, 5.4, 4.4)], seed=5)
    P = Prop("decor_Socket")
    P.box("Plastic_White", (-1.4, 0.75, Z - 0.03), (-0.6, 1.35, Z))
    for dx in (-0.16, 0.16):
        P.box("Plastic_Black", (-1.0 + dx - 0.03, 1.0, Z - 0.035), (-1.0 + dx + 0.03, 1.12, Z - 0.03))
    P.cyl("Brass", (4.2, 0.0, 5.2), (4.2, 0.06, 5.2), 0.5, seg=40)
    P.done()
    for k, (x, z) in enumerate(((-4.0, 3.5), (3.0, 3.5), (-4.0, -2.0), (3.5, -2.5))):
        down_light(f"Fill_{k}", (x, H - 0.05, z), 180.0, WARM, size=2.5)
    decor_rest({})


def dress_upside_room():
    X, Z, H = 5.0, 5.0, 3.4
    casings(M("Trim_Yellow"))
    skirting(M("Trim_Yellow"), room_runs(-X, X, -Z, Z), H - 0.16, h=0.16)
    cornice("Trim_Yellow", -X, X, -Z, Z, 0.14, h=0.14, d=0.08, name="decor_Cornice_Floor")

    def chandelier(P, b):
        x0, x1, y0, y1, z0, z1 = bb(b)
        P.cyl("Brass", (0, y0, 0), (0, 0.05, 0), 0.14, seg=20)
        P.cyl("Brass", (0, 0.05, 0), (0, 1.1, 0), 0.025, seg=10)
        P.sph("Glass_Knob", (0, 0.6, 0), 0.06, seg=10)
        P.cyl("Brass", (0, 1.08, 0), (0, 1.14, 0), 0.26, seg=24)
        for a in range(6):
            t = a * math.pi / 3
            cx, cz = 0.27 * math.cos(t), 0.27 * math.sin(t)
            P.cyl("Brass", (cx, 1.14, cz), (cx, 1.26, cz), 0.025, seg=8)
            P.cyl("Lamp_Emit", (cx, 1.26, cz), (cx, 1.42, cz), 0.014, seg=6)
            P.sph("Glass_Knob", (cx * 0.7, 0.95, cz * 0.7), 0.022, seg=6)
        P.cyl("Brass", (0, 1.14, 0), (0, y1, 0), 0.02, 0.005, seg=8)
    dress_furn([("Chandelier_Up", chandelier)])
    light("Chandelier_L", "POINT", (0.0, 1.45, 0.0), 160.0, WARM, size=0.3)
    gdecor("Floor_Rose")
    P = Prop("decor_Floor_Rose")
    for r, h in ((0.8, 0.012), (0.6, 0.025), (0.35, 0.04)):
        P.cyl("Trim_White", (0, 0.0, 0), (0, h, 0), r, seg=40)
    P.box("Plastic_White", (2.9, 0.0, 2.9), (3.1, 0.03, 3.1))
    P.box("Trim_White", (-3.5, 0.0, -1.0), (-3.0, 0.02, 1.0))
    P.done()
    # the furniture, built the right way up and then hung from the ceiling (Trick_: the page may turn it)
    for nm in ("Ceiling_Table", "Ceiling_Sofa", "Ceiling_Lamp", "Ceiling_Shelf", "Ceiling_Rug") + tuple(f"Ceiling_Chair_{k}" for k in range(1, 5)):
        gdecor(nm)
    P = Prop("decor_Trick_Upside_Table")
    k_table(P, {"min": [-1.2, 0.0, -0.8], "max": [1.2, 0.76, 0.8]}, T("Walnut"), T("Walnut"), cloth=T("Linen_White"))
    P.cyl(T("China"), (0, 0.766, 0), (0, 0.78, 0), 0.25, seg=24)
    P.flip(H / 2)
    P.done()
    for k, (x, z, face) in enumerate(((-1.6, 0.0, (1, 0)), (1.6, 0.0, (-1, 0)), (0.0, -1.2, (0, 1)), (0.0, 1.2, (0, -1))), 1):
        P = Prop(f"decor_Trick_Upside_Chair_{k}")
        k_chair(P, {"min": [x - 0.25, 0.0, z - 0.25], "max": [x + 0.25, 0.95, z + 0.25]}, face, T("Walnut"), T("Velvet_Red"))
        P.flip(H / 2)
        P.done()
    P = Prop("decor_Trick_Upside_Sofa")
    sx0, sx1, sz0, sz1 = -2.0, 2.0, -5.0, -4.1
    P.box(T("Walnut"), (sx0, 0.0, sz0), (sx1, 0.12, sz1))
    k_upholstered(P, {"min": [sx0, 0.12, sz0 + 0.2], "max": [sx1, 0.45, sz1]}, T("Velvet_Orange"))
    k_upholstered(P, {"min": [sx0, 0.12, sz0], "max": [sx1, 0.85, sz0 + 0.22]}, T("Velvet_Orange"))
    for x in (sx0, sx1 - 0.2):
        k_upholstered(P, {"min": [x, 0.12, sz0], "max": [x + 0.2, 0.62, sz1]}, T("Velvet_Orange"))
    P.flip(H / 2)
    P.done()
    P = Prop("decor_Trick_Upside_Lamp")
    P.cyl(T("Brass"), (3.5, 0.0, -3.5), (3.5, 0.03, -3.5), 0.18, seg=16)
    P.cyl(T("Brass"), (3.5, 0.03, -3.5), (3.5, 1.2, -3.5), 0.015, seg=8)
    P.cyl("Lamp_Emit", (3.5, 1.15, -3.5), (3.5, 1.45, -3.5), 0.2, 0.14, seg=16)
    P.flip(H / 2)
    P.done()
    light("Upside_Lamp_L", "POINT", (3.5, H - 1.3, -3.5), 25.0, WARM, size=0.1)
    P = Prop("decor_Trick_Upside_Shelf")
    k_bookshelf(P, {"min": [-5.0, 0.0, 2.0], "max": [-4.6, 1.4, 4.0]}, (1, 0), frame=T("Walnut"), shelves=4, books=T("Books"))
    P.flip(H / 2)
    P.done()
    P = Prop("decor_Trick_Upside_Rug")
    P.box(T("Rug_Pink"), (-2.4, H - 0.012, -1.8), (2.4, H - 0.001, 1.8))
    P.done()
    pictures("Upside", [("N", -Z, 3.4, 1.0, 1.9, 0.8), ("S", Z, -2.6, 1.1, 1.8, 0.6), ("E", X, 2.8, 1.0, 1.8, 0.7)], seed=29)
    # the light comes from below: panels in the floor (the ceiling's lights, upside down), shining up
    P = Prop("decor_Floor_Lights")
    for k, (x, z) in enumerate(((-3.0, -3.0), (3.0, -3.0), (-3.0, 3.0), (3.0, 3.0))):
        P.box("Lamp_Emit", (x - 0.25, 0.0, z - 0.25), (x + 0.25, 0.006, z + 0.25))
        P.box("Chrome", (x - 0.28, 0.0, z - 0.28), (x + 0.28, 0.004, z + 0.28))
        light(f"Floor_L{k}", "AREA", (x, 0.08, z), 45.0, WARM, size=0.5, aim=(x, 2.0, z))
    P.done()
    decor_rest({})


def dress_door_hall():
    X, Z, H = 3.0, 22.0, 3.4
    standard_room("Trim_Dark", -X, X, -Z, Z, H, dado_y=1.0)
    dress_furn([("Bench", lambda P, b: k_bench(P, b, "Walnut", seat="Velvet_Red")), ("Console_W", lambda P, b: k_sideboard(P, b, (1, 0), "Walnut")),
                ("Console_E", lambda P, b: k_sideboard(P, b, (-1, 0), "Walnut")), ("Plant_", lambda P, b: k_plant(P, b, seed=len(b["name"])))])
    gdecor("Runner")
    P = Prop("decor_Runner")
    P.box("Rug_Red", (-1.0, 0.0, -21.6), (1.0, 0.01, 21.6))
    P.box("Brass", (-1.0, 0.0, -21.6), (-0.96, 0.014, 21.6))
    P.box("Brass", (0.96, 0.0, -21.6), (1.0, 0.014, 21.6))
    P.done()
    P = Prop("decor_Console_Lamps")
    for x, z in ((-2.78, -11.5), (-2.78, 5.5), (2.78, 1.0), (2.78, 11.1)):
        P.cyl("Brass", (x, 0.85, z), (x, 0.88, z), 0.1, seg=14)
        P.cyl("Brass", (x, 0.88, z), (x, 1.25, z), 0.015, seg=8)
        P.cyl("Lamp_Emit", (x, 1.2, z), (x, 1.45, z), 0.17, 0.11, seg=16)
        light(f"Console_L_{x}_{z}", "POINT", (x + (0.15 if x < 0 else -0.15), 1.35, z), 18.0, WARM, size=0.08)
    P.done()
    # the number plates: 1 to 12 over the side doors in the order you meet them, the way back unnumbered
    P = Prop("decor_Numbers")
    side_doors = sorted([d for d in model().doors if d["name"] != "DoorLeaf_hallway"], key=lambda d: (-door_geom(d)[0][2]))
    for k, d in enumerate(side_doors, 1):
        (hx, hy, hz), run, inw, w, h = door_geom(d)
        cx, cz = hx + run[0] * w / 2, hz + run[1] * w / 2
        y = h + 0.3
        if inw[0] > 0:
            P.box("Brass", (cx, y - 0.1, cz - 0.14), (cx + 0.012, y + 0.1, cz + 0.14))
            text_on(P, "Paint_Black", str(k), 0.14, 0.004, (cx + 0.016, y - 0.02, cz), (0, 0, -1), (0, 1, 0))
        else:
            P.box("Brass", (cx - 0.012, y - 0.1, cz - 0.14), (cx, y + 0.1, cz + 0.14))
            text_on(P, "Paint_Black", str(k), 0.14, 0.004, (cx - 0.016, y - 0.02, cz), (0, 0, 1), (0, 1, 0))
    P.done()
    for k in range(11):
        pendant(f"decor_Pendant_{k}", 0.0, -20.0 + k * 4.0, 2.6, H, power=30.0, r=0.2)
    decor_rest({})


def dress_stretching_hall():
    X, Z, H = 2.0, 23.0, 3.0
    casings(M("Trim_White"))
    P = Prop("decor_Fin_Strips")
    for k in range(19):
        z = -21.6 + k * 2.4
        for sg in (-1, 1):
            x = sg * 1.65
            P.box("Lamp_Emit", (min(x, x - sg * 0.006), 0.15, z - 0.02), (max(x, x - sg * 0.006), H - 0.15, z + 0.02))
    P.box("Lamp_Emit", (-0.04, H - 0.006, -22.6), (0.04, H, 22.6))
    P.done()
    gdecor("Floor_Line")
    P = Prop("decor_Floor_Line")
    P.box("Lamp_Emit", (-0.03, 0.0, -22.6), (0.03, 0.004, 22.6))
    for k in range(7):
        z = -18.0 + k * 6.0
        for sg in (-1, 1):
            P.box("Floor_Paint_Cyan", (sg * 0.25 - 0.18, 0.0, z - 0.04), (sg * 0.25 + 0.18, 0.003, z + 0.04))
    P.done()
    for k in range(12):
        z = -22.0 + k * 4.0 + 0.0
        down_light(f"Strip_{k}", (0.0, H - 0.05, z), 32.0, (0.95, 0.97, 1.0), size=0.3, size_y=3.2)
    decor_rest({})


def dress_bending_hall():
    X, Z, H = 10.0, 10.0, 3.0
    standard_room("Trim_Lilac", -X, X, -Z, Z, H, dado_y=0.9)
    skirting(M("Trim_Lilac"), [("x", -6.0, -1, -6.0, 6.0), ("x", 6.0, 1, -6.0, 6.0), ("z", -6.0, -1, -6.0, 6.0), ("z", 6.0, 1, -6.0, 6.0)], 0.0, h=0.14,
             name="decor_Skirting_Core")
    skirting(M("Trim_Lilac"), [("x", -6.0, -1, -6.0, 6.0), ("x", 6.0, 1, -6.0, 6.0), ("z", -6.0, -1, -6.0, 6.0), ("z", 6.0, 1, -6.0, 6.0)], 0.9, h=0.05,
             name="decor_Dado_Core")
    dress_furn([("Radiator_", lambda P, b: k_radiator(P, b)), ("Plant_", lambda P, b: k_plant(P, b, seed=len(b["name"]) * 3))])
    for nm in ("Runner_S", "Runner_N", "Runner_W", "Runner_E"):
        b = gdecor(nm)
        boxes("decor_" + nm, M("Rug_Red"), [(b["min"], b["max"])])
    # the same picture on every wall of the lap, so no stretch is told from another
    items = []
    for side, plane in (("N", -X), ("S", X), ("W", -X), ("E", X)):
        items.append((side, plane, -1.5 if side != "N" else 1.0, 1.3, 2.1, 0.9))
    for side, plane in (("S", -6.0), ("N", 6.0), ("E", -6.0), ("W", 6.0)):
        items.append((side, plane, 0.0, 1.3, 2.1, 0.9))
    pictures("Lap", items, seed=1, cell=(2, 1))
    P = Prop("decor_Sconces")
    for side, plane in (("N", -X), ("S", X), ("W", -X), ("E", X)):
        for a in (-6.0, 4.0):
            sconce(P, side, a, 2.1, plane)
            wall_light(f"Sconce_{side}_{a}", side, a, 2.1, plane, power=22.0)
    P.done()
    # the cover over the lap door (the page lifts it on the third lap), and the plaque that counts
    d = next(d for d in model().doors if d["name"] == "DoorLeaf_lap")
    (hx, hy, hz), run, inw, w, h = door_geom(d)
    xa, xb = sorted((hx - 0.15, hx + run[0] * w + 0.15))
    P = Prop("decor_Trick_Lap_Cover")
    P.box(T("Wall_Lilac"), (xa, 0.0, -Z + 0.035), (xb, h + 0.18, -Z + 0.045))
    P.box(T("Trim_Lilac"), (xa, 0.0, -Z + 0.045), (xb, 0.14, -Z + 0.065))
    P.box(T("Trim_Lilac"), (xa, 0.88, -Z + 0.045), (xb, 0.93, -Z + 0.065))
    P.done()
    P = Prop("decor_Trick_Lap_Plaque")
    P.box(T("Brass"), (X - 0.012, 1.45, -0.3), (X, 1.75, 0.3))
    text_on(P, T("Paint_Black"), "LAP 1", 0.11, 0.004, (X - 0.016, 1.56, 0.0), (0, 0, 1), (0, 1, 0))
    P.done()
    for k, (x, z) in enumerate(((-8, -8), (0, -8), (8, -8), (8, 0), (8, 8), (0, 8), (-8, 8), (-8, 0))):
        down_light(f"Fill_{k}", (x, H - 0.05, z), 40.0, WARM, size=1.6)
    decor_rest({})


def dress_stair_loop():
    X, Z, H = 4.0, 7.0, 6.4
    casings(M("Trim_Mint"))
    skirting(M("Trim_Mint"), room_runs(-X, X, -Z, Z), 0.0, h=0.14)
    skirting(M("Trim_Mint"), [("x", -Z, 1, -1.2, X), ("z", X, -1, -Z, -0.8)], 3.0, h=0.12, name="decor_Skirting_Landing")
    P = Prop("decor_Nosings")
    for i in range(12):
        z0 = 4.0 - (i + 1) * 0.4
        y = 0.25 * (i + 1)
        P.box("Nosing", (-3.6, y - 0.03, z0 + 0.36), (-1.2, y + 0.003, z0 + 0.4))
    P.box("Nosing", (-1.2, 2.97, -0.84), (X, 3.003, -0.8))
    P.done()

    def rail(P, b):
        x0, x1, y0, y1, z0, z1 = bb(b)
        P.box("Rail_Black", (x0, y1 - 0.05, z0), (x1, y1, z1))
        n = int((x1 - x0) / 0.12)
        for i in range(n + 1):
            x = x0 + i * (x1 - x0 - 0.02) / n
            P.box("Rail_Black", (x, y0, z0 + 0.02), (x + 0.02, y1 - 0.05, z1 - 0.02))
        P.box("Rail_Black", (x0, y0 + 0.08, z0 + 0.01), (x1, y0 + 0.12, z1 - 0.01))
    dress_furn([("Landing_Rail", rail), ("Plant", lambda P, b: k_plant(P, b, seed=4)),
                ("Cupboard", lambda P, b: k_counter(P, b, (0, 1), "Paint_White", "Paint_White", handle="Brass"))])
    gdecor("Handrail")
    P = Prop("decor_Handrail")
    P.cyl("Rail_Black", (-1.25, 0.95, 4.2), (-1.25, 3.95, -0.8), 0.025, seg=10)
    for i in range(12):
        z = 4.0 - i * 0.4 - 0.2
        y = 0.25 * (i + 1)
        P.cyl("Rail_Black", (-1.25, y, z), (-1.25, 0.95 + 3.0 * (4.2 - z) / 5.0, z), 0.012, seg=6)
    P.cyl("Rail_Black", (-3.97, 0.95, 4.0), (-3.97, 3.95, -0.8), 0.02, seg=8)
    P.done()
    gdecor("Window_E")
    uv_quads("decor_Window_E", "Window_Lit", [(wall_quad("E", X, -6.4, -4.6, 3.6, 5.6), [(0, 0), (1, 0), (1, 1), (0, 1)])])
    P = Prop("decor_Window_Frame")
    for a0, a1, b0, b1 in ((-6.46, -4.54, 3.54, 3.6), (-6.46, -4.54, 5.6, 5.66), (-6.46, -6.4, 3.6, 5.6), (-4.6, -4.54, 3.6, 5.6), (-5.53, -5.47, 3.6, 5.6)):
        P.box("Trim_Mint", (X - 0.05, b0, a0), (X, b1, a1))
    P.done()
    light("Window_L", "AREA", (X - 0.2, 4.6, -5.5), 60.0, COOL, size=1.8, aim=(0.0, 3.0, -4.0), size_y=2.0)
    gdecor("Pendant")
    pendant("decor_Pendant", 1.0, 3.0, 4.6, H, power=80.0, r=0.3)
    P = Prop("decor_Count")
    text_on(P, "Paint_Black", "12", 0.5, 0.004, (1.0, 3.003, -3.0), (1, 0, 0), (0, 0, -1))
    P.done()
    for k, (x, y, z) in enumerate(((1.5, H - 0.05, 4.5), (0.0, H - 0.05, -4.0), (-2.4, 2.7 - 0.05, -3.0))):
        if y > 3:
            down_light(f"Fill_{k}", (x, y, z), 70.0, WARM, size=1.6)
    light("Under_L", "AREA", (1.4, 2.64, -3.6), 30.0, WARM, size=1.2, aim=(1.4, 0.0, -3.6))
    decor_rest({})


def dress_tilted_hall():
    X, Z, H = 3.0, 15.0, 4.0
    T6 = 26.0 / 6
    casings(M("Trim_Peach"))
    skirting(M("Trim_Peach"), [("x", Z, -1, -X, X), ("z", -X, 1, 11.0, Z), ("z", X, -1, 11.0, Z)], 0.0, h=0.14, name="decor_Skirting_Start")
    items = []
    P = Prop("decor_Terrace_Trim")
    for k in range(6):
        z0, z1 = 11.0 - (k + 1) * T6, 11.0 - k * T6
        y = 0.25 * (k + 1)
        w = 0.25 * (k + 1)
        s = 1.0 - 0.09 * k
        for sg in (-1, 1):
            xw = sg * (X - w)
            xa, xb = sorted((xw, xw - sg * 0.02))
            P.box("Trim_Peach", (xa, y, z0), (xb, y + 0.14 * s, z1))
            P.box("Trim_Peach", (xa, y + 0.95 * s, z0), (xb, y + 0.95 * s + 0.05 * s, z1))
            items.append(("W" if sg < 0 else "E", xw, (z0 + z1) / 2, y + 1.25 * s, y + 1.25 * s + 0.8 * s, 0.9 * s))
        b = gdecor(f"Ceiling_Step_{k + 1}")
        P.box("Ceil_Prop", (b["min"][0], b["min"][1], z0), (b["max"][0], b["min"][1] + 0.03, z1))
        for sg in (-1, 1):
            P.box("Trim_Peach", (sg * (X - w) - (0.06 if sg > 0 else 0.0), b["min"][1] - 0.06, z0), (sg * (X - w) + (0.06 if sg < 0 else 0.0), b["min"][1], z1))
        pendant(f"decor_Pendant_{k}", 0.0, (z0 + z1) / 2, b["min"][1] - 0.3 * s, b["min"][1], power=40.0 * s, r=0.25 * s)
        down_light(f"Fill_{k}", (0.0, b["min"][1] - 0.04, (z0 + z1) / 2 + 1.2), 30.0 * s, WARM, size=1.0 * s, size_y=2.0)
    P.done()
    pictures("Shrinking", items, seed=7)
    pendant("decor_Pendant_Start", 0.0, 13.0, 3.1, H, power=50.0, r=0.3)
    decor_rest({})


def dress_three_doors():
    X, Z, H = 6.0, 5.0, 3.4
    standard_room("Trim_White", -X, X, -Z, Z, H)
    dress_furn([("Plinth", lambda P, b: k_plinth(P, b)), ("Bench_", lambda P, b: k_bench(P, b, "Walnut", seat="Velvet_Green")),
                ("Plant_", lambda P, b: k_plant(P, b, seed=len(b["name"]) * 5))])
    P = Prop("decor_Note")
    P.box("Note_Card", (-0.16, 1.0, 0.85), (0.16, 1.003, 1.15))
    text_on(P, "Plastic_Black", "ONE OF THESE", 0.035, 0.001, (0.0, 1.004, 0.97), (1, 0, 0), (0, 0, -1))
    text_on(P, "Plastic_Black", "IS RIGHT", 0.035, 0.001, (0.0, 1.004, 1.04), (1, 0, 0), (0, 0, -1))
    P.done()
    cols = [("Paint_Red", "Floor_Paint_Red", (1.0, 0.35, 0.3)), ("Paint_Yellow", "Floor_Paint_Yellow", (1.0, 0.85, 0.4)), ("Paint_Cyan", "Floor_Paint_Cyan", (0.4, 0.9, 1.0))]
    P = Prop("decor_Signs")
    for k, x in enumerate((-4.0, 0.0, 4.0), 1):
        gdecor(f"Sign_{k}")
        gdecor(f"Line_{k}")
        pm, fm, lc = cols[k - 1]
        P.box(pm, (x - 0.6, 2.62, -Z), (x + 0.6, 2.98, -Z + 0.03))
        text_on(P, "Paint_White", ["LEFT", "MIDDLE", "RIGHT"][k - 1], 0.16, 0.004, (x, 2.74, -Z + 0.034), (1, 0, 0), (0, 1, 0))
        P.box(fm, (x * 0.5 - 0.08, 0.0, -4.2), (x * 0.5 + 0.08, 0.003, 0.2))
        P.box(fm, (x - 0.08, 0.0, -4.4), (x + 0.08, 0.003, -4.2))
        P.box("Lamp_Emit", (x - 0.4, 3.04, -Z + 0.02), (x + 0.4, 3.09, -Z + 0.1))
        light(f"Door_L{k}", "AREA", (x, 3.0, -Z + 0.35), 40.0, lc, size=0.8, aim=(x, 1.0, -Z), size_y=0.2)
    P.done()
    P = Prop("decor_Coffers")
    for i in range(1, 6):
        x = -X + i * 2.0
        P.box("Trim_White", (x - 0.06, H - 0.16, -Z), (x + 0.06, H, Z))
    for j in range(1, 5):
        z = -Z + j * 2.0
        P.box("Trim_White", (-X, H - 0.16, z - 0.06), (X, H, z + 0.06))
    P.done()
    for i in range(3):
        for j in range(2):
            down_light(f"Coffer_{i}_{j}", (-4.0 + i * 4.0, H - 0.18, -2.0 + j * 4.0), 45.0, (1.0, 0.95, 0.88), size=1.4)
    decor_rest({})


PAINT_EYE = (0.0, GB.EYE, 6.0)               # Spot_view_1 at eye height: the one place the painted door is a door
PAINT_ZV, PAINT_WALL = -9.0, -11.952


def painted_door_quads(nu=10, nv=48):
    """The painted door as seen from the mark: a 1.3 m by 2.45 m door (frame included) standing 3 m in front of the end wall, cut into
    cells, each cell carried along its line of sight onto the end wall (its top) or the floor (its foot). [(4 points, 4 uvs)]."""
    ex, ey, ez = PAINT_EYE
    tw = (PAINT_WALL - ez) / (PAINT_ZV - ez)
    y_th = ey - (ey - 0.003) / tw

    def proj(x, y, on_wall):
        if on_wall:
            return (ex + tw * (x - ex), max(ey + tw * (y - ey), 0.003), PAINT_WALL)
        tf = (0.003 - ey) / (y - ey) if y < ey - 1e-6 else tw
        tf = min(tf, tw)
        return (ex + tf * (x - ex), 0.003, ez + tf * (PAINT_ZV - ez))
    out = []
    W2, Ht = 0.65, 2.45
    for i in range(nu):
        for j in range(nv):
            u0, u1, v0, v1 = i / nu, (i + 1) / nu, j / nv, (j + 1) / nv
            xa, xb, ya, yb = -W2 + 2 * W2 * u0, -W2 + 2 * W2 * u1, Ht * v0, Ht * v1
            wall = (ya + yb) / 2 > y_th
            pts = [proj(xa, ya, wall), proj(xb, ya, wall), proj(xb, yb, wall), proj(xa, yb, wall)]
            out.append((pts, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]))
    return out


def dress_painted_door():
    X, Z, H = 3.0, 12.0, 3.4
    standard_room("Trim_Teal", -X, X, -Z, Z, H, skip=("painted",))
    dress_furn([("Pillar", lambda P, b: k_pillar(P, b)), ("Bench", lambda P, b: k_bench(P, b, "Walnut", seat="Velvet_Green"))])
    gdecor("Mark")
    P = Prop("decor_Mark")
    P.cyl("Floor_Paint_Yellow", (0, 0.0, 6.0), (0, 0.003, 6.0), 0.32, seg=40)
    P.cyl("Paint_White", (0, 0.0, 6.0), (0, 0.004, 6.0), 0.26, seg=40)
    for sg in (-1, 1):
        P.box("Floor_Paint_Yellow", (sg * 0.09 - 0.05, 0.004, 5.86), (sg * 0.09 + 0.05, 0.006, 6.12))
    P.done()
    gdecor("Painted_Door")
    d = next(d for d in model().doors if d["name"] == "DoorLeaf_painted")
    (hx, hy, hz), run, inw, w, h = door_geom(d)
    xa, xb = sorted((hx, hx + run[0] * w))
    P = Prop("decor_Trick_Painted_Wall")
    P.box(T("Wall_Teal_Cream"), (xa - 0.04, 0.0, -Z + 0.03), (xb + 0.04, h + 0.06, -Z + 0.04))
    P.done()
    uv_quads("decor_Trick_Painted_Door", T("Painted_Door"), painted_door_quads())
    pictures("Gallery", [("W", -X, z, 1.2, 2.2, 0.9) for z in (-6.0, 0.0, 7.0)] + [("E", X, z, 1.2, 2.2, 0.9) for z in (-7.0, 2.5, 8.0)], seed=19)
    for k in range(4):
        down_light(f"Fill_{k}", (0.0, H - 0.05, 8.5 - k * 5.5), 55.0, (1.0, 0.95, 0.88), size=1.4, size_y=2.4)
    light("End_Spot", "SPOT", (0.0, H - 0.1, -6.0), 220.0, (1.0, 0.92, 0.8), size=0.2, aim=(0.0, 1.0, -12.0), spot=55)
    decor_rest({})


def dress_anamorphic_room():
    X, Z, H = 7.0, 7.0, 4.0
    standard_room("Trim_Navy", -X, X, -Z, Z, H, skip=("word",))

    def tripod(P, b):
        x0, x1, y0, y1, z0, z1 = bb(b)
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        for a in range(3):
            t = a * 2 * math.pi / 3 + 0.4
            P.cyl("Iron", (cx, y1 - 0.3, cz), (cx + 0.22 * math.cos(t), y0, cz + 0.22 * math.sin(t)), 0.012, seg=6)
        P.box("Plastic_Black", (cx - 0.12, y1 - 0.3, cz - 0.08), (cx + 0.12, y1 - 0.12, cz + 0.08))
        P.box("Plastic_Black", (cx - 0.04, y1 - 0.12, cz - 0.04), (cx + 0.04, y1, cz + 0.04))
        P.cyl("Iron", (cx, y0, cz), (cx, y0 + 0.01, cz), (x1 - x0) / 2, seg=24)
        P.cyl("Chrome", (cx + 0.02, y1 - 0.21, cz - 0.08), (cx + 0.1, y1 - 0.21, cz - 0.2), 0.045, seg=14)
    dress_furn([("Crate_", lambda P, b: k_crate(P, b)), ("Tripod", tripod)])
    for k, (q0, q1, th) in enumerate(GB.anamorphic_shards(), 1):
        gdecor(f"Shard_{k}")
        P = Prop(f"decor_Trick_Shard_{k}")
        P.cyl("Shard_Glow", q0, q1, th, seg=4)
        P.done()
    gdecor("Footprints")
    P = Prop("decor_Footprints")
    for sg in (-1, 1):
        cx, cz = -4.0 + sg * 0.1, 4.0
        P.box("Floor_Paint_Yellow", (cx - 0.05, 0.0, cz - 0.13), (cx + 0.05, 0.003, cz + 0.13))
    P.cyl("Floor_Paint_Yellow", (-4.0, 0.0, 4.0), (-4.0, 0.002, 4.0), 0.4, seg=40)
    P.done()
    d = next(d for d in model().doors if d["name"] == "DoorLeaf_word")
    (hx, hy, hz), run, inw, w, h = door_geom(d)
    xa, xb = sorted((hx, hx + run[0] * w))
    P = Prop("decor_Trick_Word_Cover")
    P.box(T("Wall_Indigo"), (xa - 0.04, 0.0, -Z + 0.03), (xb + 0.04, h + 0.06, -Z + 0.04))
    P.done()
    for k, (x, z) in enumerate(((-3.5, -3.5), (3.5, -3.5), (-3.5, 3.5), (3.5, 3.5))):
        down_light(f"Fill_{k}", (x, H - 0.05, z), 60.0, (0.9, 0.9, 1.0), size=1.6)
    light("Spot_N", "SPOT", (-2.0, H - 0.1, 2.0), 260.0, (1.0, 0.9, 0.75), size=0.2, aim=(3.0, 1.0, -7.0), spot=50)
    decor_rest({})


DRESS = {"rdwe_long_table": dress_long_table, "rdwe_tiny_kitchen": dress_tiny_kitchen, "rdwe_birthday_party": dress_birthday_party,
         "rdwe_attic": dress_attic, "rdwe_kids_bedroom": dress_kids_bedroom, "rdwe_giant_chair": dress_giant_chair,
         "rdwe_upside_room": dress_upside_room, "rdwe_door_hall": dress_door_hall, "rdwe_stretching_hall": dress_stretching_hall,
         "rdwe_bending_hall": dress_bending_hall, "rdwe_stair_loop": dress_stair_loop, "rdwe_tilted_hall": dress_tilted_hall,
         "rdwe_three_doors": dress_three_doors, "rdwe_painted_door": dress_painted_door, "rdwe_anamorphic_room": dress_anamorphic_room}

E = 1.55
SHOTS = {   # (camera, target, vertical fov): 1 the arrival, 2 the whole room, 3 the trick or a detail
    "rdwe_long_table": {"1_arrival": ((0.0, E, 15.6), (0.0, 1.0, -14.0), 62), "2_wide": ((3.3, 2.9, 16.4), (-1.0, 0.6, -6.0), 70),
                        "3_detail": ((2.6, 1.6, -9.5), (0.0, 1.1, -16.0), 66)},
    "rdwe_tiny_kitchen": {"1_arrival": ((3.6, E, 0.0), (-3.0, 0.9, 0.0), 72), "2_wide": ((4.4, 2.7, 3.4), (-2.0, 0.6, -1.5), 78),
                          "3_detail": ((-0.4, 1.25, 0.9), (-3.4, 0.4, -2.0), 70)},
    "rdwe_birthday_party": {"1_arrival": ((-5.3, E, 0.0), (2.0, 1.0, 0.0), 72), "2_wide": ((6.3, 2.8, 4.3), (-2.0, 0.6, -1.5), 76),
                            "3_detail": ((-0.9, 1.45, 1.8), (0.0, 0.95, 0.0), 60)},
    "rdwe_attic": {"1_arrival": ((-3.0, E, 2.4), (-1.0, 1.1, -3.0), 75), "2_wide": ((5.2, 1.9, 2.6), (-4.0, 0.8, -1.0), 78),
                   "3_detail": ((-2.8, 1.3, 0.6), (-4.6, 0.5, -2.4), 66)},
    "rdwe_kids_bedroom": {"1_arrival": ((2.4, E, -2.0), (-2.6, 0.8, -1.4), 75), "2_wide": ((3.5, 2.4, 3.5), (-1.8, 0.6, -2.0), 80),
                          "3_detail": ((-1.4, 0.9, 0.6), (-2.6, 0.2, -0.8), 66)},
    "rdwe_giant_chair": {"1_arrival": ((-5.0, E, 5.4), (-2.0, 3.6, -6.0), 78), "2_wide": ((7.4, 7.2, 6.4), (-2.0, 1.5, -4.0), 78),
                         "3_detail": ((4.6, E, 3.0), (3.0, 2.8, -5.0), 70)},
    "rdwe_upside_room": {"1_arrival": ((-3.3, E, 0.4), (1.0, 2.4, -0.6), 78), "2_wide": ((4.4, 2.0, 4.4), (-2.0, 1.6, -2.4), 80),
                         "3_detail": ((0.4, 0.9, 2.6), (0.0, 2.4, 0.0), 72)},
    "rdwe_door_hall": {"1_arrival": ((0.0, E, 20.4), (0.0, 1.4, -10.0), 62), "2_wide": ((-2.2, 2.9, -20.6), (1.2, 0.8, 8.0), 66),
                       "3_detail": ((0.8, E, -2.6), (-2.8, 1.2, -9.0), 66)},
    "rdwe_stretching_hall": {"1_arrival": ((0.0, E, 21.4), (0.0, 1.5, -10.0), 58), "2_wide": ((0.9, 2.6, -21.6), (-0.3, 1.0, 10.0), 62),
                             "3_detail": ((-1.1, 1.0, 1.4), (1.6, 1.6, -3.5), 66)},
    "rdwe_bending_hall": {"1_arrival": ((-8.0, E, 8.4), (-8.0, 1.3, -6.0), 70), "2_wide": ((-9.2, 2.6, -9.2), (8.0, 0.8, -6.0), 68),
                          "3_detail": ((7.2, E, -6.0), (8.0, 1.2, -10.0), 66)},
    "rdwe_stair_loop": {"1_arrival": ((2.0, E, 5.4), (-2.0, 2.4, -3.0), 78), "2_wide": ((3.4, 3.0 + 2.2, -6.4), (-2.4, 1.0, 4.0), 80),
                        "3_detail": ((-2.4, E + 0.2, 5.6), (-2.4, 2.6, 0.0), 70)},
    "rdwe_tilted_hall": {"1_arrival": ((0.0, E, 13.6), (0.0, 2.0, -15.0), 62), "2_wide": ((-1.0, 1.5 + E, -13.4), (0.6, 1.0, 14.0), 62),
                         "3_detail": ((0.6, 0.25 + E, 8.0), (-2.6, 1.5, 2.0), 64)},
    "rdwe_three_doors": {"1_arrival": ((0.0, E, 3.6), (0.0, 1.4, -5.0), 72), "2_wide": ((5.4, 2.8, 4.4), (-2.0, 0.8, -3.0), 76),
                         "3_detail": ((0.5, 1.5, 1.9), (0.0, 1.0, 1.0), 56)},
    "rdwe_painted_door": {"1_arrival": ((0.0, E, 6.0), (0.0, 1.3, -12.0), 56), "2_wide": ((2.3, 2.6, -3.0), (-0.6, 0.5, -12.0), 70),
                          "3_detail": ((-2.2, 1.2, -5.0), (0.6, 0.4, -11.0), 70)},
    "rdwe_anamorphic_room": {"1_arrival": ((-4.0, E, 4.0), (3.0, 1.15, -7.0), 62), "2_wide": ((6.2, 3.3, 6.2), (-1.0, 0.8, -2.0), 76),
                             "3_detail": ((-5.4, E, 0.2), (3.0, 1.2, -7.0), 66)},
}


# ================================================================ build
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for d in (IMG, MATS, TILES, GEN):
        d.clear()


def build_all():
    global ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, LIGHTS, ALTL
    reset()
    sc = bpy.context.scene
    ART = bpy.data.collections.new("Art")
    sc.collection.children.link(ART)
    PROPS, ARCH = bpy.data.collections.new("Props"), bpy.data.collections.new("Arch")
    ART.children.link(PROPS)
    ART.children.link(ARCH)
    SKIN, DOORS, LAYOUT, LIGHTS, ALTL = (bpy.data.collections.new(n) for n in ("Skin", "Doors", "Layout", "Lights", "Lights_Alt"))
    for c in (SKIN, DOORS, LAYOUT, LIGHTS, ALTL):
        sc.collection.children.link(c)
    CLAIMED.clear()
    common_materials()
    mdl = model()
    layout_from_model(mdl)
    build_skin()
    build_leaves(mdl)
    DRESS[SCENE]()
    w = sc.world or bpy.data.worlds.new("Room")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.01, 0.012, 0.02, 1)
    bg.inputs["Strength"].default_value = 0.0
    for ob in LAYOUT.objects:
        ob.hide_render = True
    used = {s.material.name for o in PROPS.objects for s in o.material_slots} | {s.material.name for o in DOORS.objects for s in o.material_slots}
    shell = {s.material.name for o in SKIN.objects for s in o.material_slots}
    clash = (used & shell) - NO_LIGHTMAP
    assert not clash, f"materials on both the shell page and the props page: {clash}"
    split_for_check()
    print(f"ART {SCENE}: {len(PROPS.objects)} props, {len(ARCH.objects)} arch boxes, {len(SKIN.objects)} skin meshes, {len(DOORS.objects)} leaves, "
          f"{len(LIGHTS.objects) + len(ALTL.objects)} lights")


def gbox(ob):
    g = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return [min(p.x for p in g), min(p.z for p in g), min(-p.y for p in g)], [max(p.x for p in g), max(p.z for p in g), max(-p.y for p in g)]


def split_for_check():
    """check_layout.py works one box per object: a prop made of separate parts whose box would fail its STRAY or CLEAR rule is cut into its loose
    parts (`<name>`, `<name>_p1`, ...). Only Art is cut; Export is merged by material from Art, so the GLB is the same either way."""
    import check_layout as cl
    allc = [{"min": gbox(o)[0], "max": gbox(o)[1]} for o in bpy.data.objects if o.name.startswith("COL_") and o.type == "MESH"]
    stand = [c for c in allc if cl._standing(c)]
    marks = [(o.matrix_world.translation.x, -o.matrix_world.translation.y) for o in bpy.data.objects if o.name.startswith("Marker_")]

    def fails(p):
        if not cl._stands(p):
            return False
        if any(cl._in_plan(p, x, z, cl.CLEAR_R) for x, z in marks):
            return True
        for x in cl._samples(p["min"][0], p["max"][0], cl.STEP / 2):
            for z in cl._samples(p["min"][2], p["max"][2], cl.STEP / 2):
                if not any(cl._in_plan(c, x, z, cl.TOL) for c in stand) and not any(cl._in_plan(c, x, z, cl.TOL) and c["min"][1] - cl.TOL <= p["min"][1] < c["max"][1] - cl.TOL
                                                                                    for c in allc):
                    return True
        return False
    done = []
    for ob in list(PROPS.objects):
        if ob.type != "MESH" or ob.name.startswith("decor_") or is_furniture({"name": ob.name}):
            continue                                       # furniture stands on its own collider: never cut (its parts would not cover it)
        mn, mx = gbox(ob)
        if not fails({"min": mn, "max": mx}):
            continue
        src = bmesh.new()
        src.from_mesh(ob.data)
        src.faces.index_update()
        seen, groups = set(), []
        for f in src.faces:
            if f.index in seen:
                continue
            comp, stack = set(), [f]
            seen.add(f.index)
            while stack:
                u = stack.pop()
                comp.add(u.index)
                for v in u.verts:
                    for w2 in v.link_faces:
                        if w2.index not in seen:
                            seen.add(w2.index)
                            stack.append(w2)
            groups.append(comp)
        src.free()
        if len(groups) < 2:
            continue
        name = ob.name
        mats = list(ob.data.materials)
        for k in range(len(groups) - 1, -1, -1):
            bm = bmesh.new()
            bm.from_mesh(ob.data)
            bm.faces.index_update()
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in groups[k]], context="FACES")
            if k == 0:
                bm.to_mesh(ob.data)
                bm.free()
                continue
            me = bpy.data.meshes.new(f"{name}_p{k}")
            for m in mats:
                me.materials.append(m)
            bm.to_mesh(me)
            bm.free()
            PROPS.objects.link(bpy.data.objects.new(f"{name}_p{k}", me))
        done.append(f"{name} ({len(groups)})")
    print("SPLIT for the layout check:", done)


# ---------------------------------------------------------------- bake
NO_CULL = ("decor_Photos", "decor_Pictures", "decor_Window", "decor_Gable_Window", "decor_Posters", "decor_Tiles_Small")
TRICK_PREFIX = ("Trick_", "decor_Trick_")


def cull_flush(bm, cols):
    bad = []
    for f in bm.faces:
        c, n = f.calc_center_median(), f.normal
        g = (c.x + n.x * 0.003, c.z + n.z * 0.003, -(c.y + n.y * 0.003))
        if any(all(o["min"][i] + 1e-4 < g[i] < o["max"][i] - 1e-4 for i in range(3)) for o in cols):
            bad.append(f)
    bmesh.ops.delete(bm, geom=bad, context="FACES")


def make_export_objects():
    if "Export" in bpy.data.collections:
        for o in list(bpy.data.collections["Export"].objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(bpy.data.collections["Export"])
    exp = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(exp)
    cols = [{"min": b["min"], "max": b["max"]} for b in shell_boxes()]
    out = {}
    for ob in bpy.data.collections["Skin"].objects:
        me = ob.data.copy()
        me.name = ob.name
        o2 = bpy.data.objects.new(ob.name, me)
        exp.objects.link(o2)
        out[ob.name] = o2
    by_mat = {}
    for ob in bpy.data.collections["Props"].objects:
        if ob.name.startswith(TRICK_PREFIX):                 # a trick object stays whole, under its own name
            me = ob.data.copy()
            me.transform(ob.matrix_world)
            o2 = bpy.data.objects.new(ob.name + "_x", me)
            exp.objects.link(o2)
            out[ob.name + "_x"] = o2
            continue
        for idx, slot in enumerate(ob.material_slots):
            mname = slot.material.name
            tmp = bmesh.new()
            tmp.from_mesh(ob.data)
            tmp.transform(ob.matrix_world)
            bmesh.ops.delete(tmp, geom=[f for f in tmp.faces if f.material_index != idx], context="FACES")
            for f in tmp.faces:
                f.material_index = 0
            if not ob.name.startswith(NO_CULL):
                cull_flush(tmp, cols)
            me = bpy.data.meshes.new("tmp")
            tmp.to_mesh(me)
            tmp.free()
            bm = by_mat.setdefault(mname, bmesh.new())
            bm.from_mesh(me)
            bpy.data.meshes.remove(me)
    for mname, bm in by_mat.items():
        name = mname if mname not in out else mname + "_props"
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        if not me.polygons:
            bpy.data.meshes.remove(me)
            continue
        me.materials.append(bpy.data.materials[mname])
        ob = bpy.data.objects.new(name, me)
        exp.objects.link(ob)
        out[name] = ob
    return out


def select_only(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def uv_area(ob, layer):
    uv = ob.data.uv_layers[layer].data
    tot = 0.0
    for p in ob.data.polygons:
        pts = [uv[i].uv for i in p.loop_indices]
        n = len(pts)
        tot += abs(sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))) / 2
    return tot


def world_area(ob):
    return sum(p.area for p in ob.data.polygons) * abs(ob.matrix_world.to_3x3().determinant()) ** (2 / 3)


def base_uv(o):
    uvs = o.data.uv_layers
    if "UVMap" not in uvs:
        first = next((u for u in uvs if u.name != "lightmap"), None)
        if first is None:
            first = uvs.new(name="UVMap")
        first.name = "UVMap"
    return uvs


def lightmap_uv(objs, page):
    for o in objs:
        uvs = base_uv(o)
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.new(name="lightmap", do_init=False)
        uvs.active = uvs["lightmap"]
        uvs["UVMap"].active_render = True
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / page, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    a3 = sum(world_area(o) for o in objs)
    au = sum(uv_area(o, "lightmap") for o in objs)
    dens = page * math.sqrt(au / a3)
    print(f"  page {page}: {a3:.1f} m2, {dens:.1f} px/m")
    return page, dens


def rect_uv(objs, S):
    """The shell's lightmap UVs packed by hand: every skin face is an axis-aligned rectangle (4 m at most), each its own pixel-aligned island with
    MARGIN_PX round it, shelf-packed at the highest density that fits the fixed page S. Deterministic."""
    m = MARGIN_PX
    rects = []
    for o in objs:
        uvs = base_uv(o)
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.new(name="lightmap", do_init=False)
        uvs["UVMap"].active_render = True
        mw = o.matrix_world
        for p in o.data.polygons:
            vs = [mw @ o.data.vertices[i].co for i in p.vertices]
            assert len(vs) == 4, (o.name, len(vs))
            e1, e2 = vs[1] - vs[0], vs[3] - vs[0]
            rects.append((o, p, vs[0], e1, e2, e1.length, e2.length))

    def layout(D):
        bxs = []
        for i, (o, p, v0, e1, e2, w, h) in enumerate(rects):
            pw, ph = max(1, math.ceil(w * D)), max(1, math.ceil(h * D))
            rot = ph > pw
            if rot:
                pw, ph = ph, pw
            bxs.append((ph + 2 * m, pw + 2 * m, i, rot))
        bxs.sort(key=lambda b: (-b[0], -b[1]))
        x = y = rowh = 0
        place = {}
        for bh, bw, i, rot in bxs:
            if bw > S:
                return None
            if x + bw > S:
                x, y, rowh = 0, y + rowh, 0
            if y + bh > S:
                return None
            place[i] = (x + m, y + m, rot)
            x += bw
            rowh = max(rowh, bh)
        return place
    lo, hi = 1.0, 400.0
    best = None
    for _ in range(40):
        mid = (lo + hi) / 2
        pl = layout(mid)
        if pl:
            lo, best = mid, (mid, pl)
        else:
            hi = mid
    D, place = best
    for i, (o, p, v0, e1, e2, w, h) in enumerate(rects):
        x0, y0, rot = place[i]
        pw, ph = max(1, math.ceil(w * D)), max(1, math.ceil(h * D))
        uv = o.data.uv_layers["lightmap"].data
        for li in p.loop_indices:
            v = o.matrix_world @ o.data.vertices[o.data.loops[li].vertex_index].co
            a, b = (v - v0).dot(e1) / (w * w), (v - v0).dot(e2) / (h * h)
            u, t = (b * ph, a * pw) if rot else (a * pw, b * ph)
            uv[li].uv = ((x0 + u) / S, (y0 + t) / S)
    print(f"  rect pack: {len(rects)} faces at {D:.1f} px/m on {S}")
    return S, D


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
    path = str(work() / f"dn_{SCENE}.exr")
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=sc.name)
    r = bpy.data.images.load(path)
    a = np.empty(S * S * 4, np.float32)
    r.pixels.foreach_get(a)
    bpy.data.images.remove(r)
    bpy.data.objects.remove(cam)
    bpy.data.scenes.remove(sc)
    bpy.data.node_groups.remove(ng)
    return a.reshape(S, S, 4)


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


def bake_visibility():
    for c, hide in (("Art", True), ("Skin", True), ("Doors", False), ("Export", False)):
        bpy.data.collections[c].hide_render = hide
    bpy.data.collections["Art"].hide_viewport = True
    bpy.data.collections["Skin"].hide_viewport = True
    for o in bpy.data.collections["Export"].objects:
        o.hide_render = o.data.materials[0].name in NO_BAKE_VIS


def bake_page(objs, S):
    mats = sorted({s.material for o in objs for s in o.material_slots}, key=lambda m: m.name)
    img = bpy.data.images.new("LM_bake", S, S, alpha=False, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    for m in mats:
        node = m.node_tree.nodes.new("ShaderNodeTexImage")
        node.name = "BAKE_TARGET"
        node.image = img
        m.node_tree.nodes.active = node
        node.select = True
    select_only(objs)
    for o in objs:
        o.data.uv_layers.active = o.data.uv_layers["lightmap"]
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
    for m in mats:
        for nd in [nd for nd in m.node_tree.nodes if nd.name.startswith("BAKE_TARGET")]:
            m.node_tree.nodes.remove(nd)
    rgb = denoise_image(img, S)[..., :3].copy()
    bpy.data.images.remove(img)
    return rgb, [m for m in mats if m.name not in NO_LIGHTMAP]


def write_png(rgb, gain, path):
    S = rgb.shape[0]
    out = np.ones((S, S, 4), np.float32)
    out[..., :3] = encode(rgb, gain)
    png = bpy.data.images.new("LM_png", S, S, alpha=False)
    png.colorspace_settings.name = "Non-Color"
    png.pixels.foreach_set(out.ravel())
    png.filepath_raw = str(path)
    png.file_format = "PNG"
    png.save()
    bpy.data.images.remove(png)


def stage_encode_blender():
    """The maps again at another gain (--gain), from the raw bake kept on the box, without baking."""
    rep_p = work() / f"{SCENE}_bake.json"
    rep = json.loads(rep_p.read_text())
    gain = arg("--gain", None, float) or rep["0"]["gain"]
    for n in sorted(rep):
        write_png(np.load(raw_dir() / f"{SCENE}_{n}_raw.npy").astype(np.float32), gain, work() / f"{SCENE}_{n}.png")
        rep[n]["gain"] = round(gain, 4)
    rep_p.write_text(json.dumps(rep, indent=1))
    print("ENCODED", SCENE, "gain", gain)


def stage_bake():
    """Three pages: 0 the shell (hand-packed rectangles), 1 the props and the door leaves, 2 the trick objects. Pages 0 and 1 are baked with the
    trick objects hidden (no shadow of theirs where they move); page 2 with everything. G comes from the shell's median light."""
    import time
    exp = make_export_objects()
    bake_visibility()
    setup_cycles(SAMPLES, bake=True)
    skin = {o.name for o in bpy.data.collections["Skin"].objects}
    tricks = [o for o in exp.values() if o.name.startswith(TRICK_PREFIX)]

    def lit(o):
        return any(sl.material.name not in NO_LIGHTMAP for sl in o.material_slots)
    shell = [o for k, o in sorted(exp.items()) if o.name.split(".")[0] in skin and o not in tricks and lit(o)]
    leaves = [o for o in bpy.data.collections["Doors"].objects if o.type == "MESH" and lit(o)]
    props = [o for k, o in sorted(exp.items()) if o not in shell and o not in tricks and lit(o)] + leaves
    groups = [shell, props] + ([[o for o in tricks if lit(o)]] if any(lit(o) for o in tricks) else [])
    report, gain = {}, None
    for n, objs in enumerate(groups):
        for o in tricks:
            o.hide_render = n < 2
        print(f"lightmap {n}: {len(objs)} objects")
        t0 = time.time()
        S, dens = rect_uv(objs, PAGES[SCENE][n]) if n == 0 else lightmap_uv(objs, PAGES[SCENE][n])
        rgb, mats = bake_page(objs, S)
        peak = rgb.max(axis=2)
        sel = peak > 1e-5
        pc = np.percentile(peak[sel], [50, 90, 99, 99.5, 100]) if sel.any() else [1.0] * 5
        if gain is None:
            gain = GAIN_TARGET / max(float(pc[0]), 1e-6)
        np.save(raw_dir() / f"{SCENE}_{n}_raw.npy", rgb.astype(np.float16))
        write_png(rgb, gain, work() / f"{SCENE}_{n}.png")
        for m in mats:
            m["lightmap"] = lm_url(SCENE, n)
            m["lightmap_intensity"] = round(math.pi * CURVE_C, 4)
        report[str(n)] = {"map": n, "size": S, "gain": round(gain, 4), "C": CURVE_C, "px_per_m": round(dens, 1),
                          "p50_p90_p99_p995_max": [round(float(v), 4) for v in pc], "samples": SAMPLES, "device": bpy.context.scene.cycles.device,
                          "seconds": round(time.time() - t0), "materials": [m.name for m in mats]}
        print("  baked", {k: v for k, v in report[str(n)].items() if k != "materials"})
    for o in tricks:
        o.hide_render = False
    stills_dir(SCENE).mkdir(parents=True, exist_ok=True)
    (stills_dir(SCENE) / "bake.json").write_text(json.dumps(report, indent=1))
    (work() / f"{SCENE}_bake.json").write_text(json.dumps(report, indent=1))
    for c in ("Art", "Skin"):
        bpy.data.collections[c].hide_render = False
        bpy.data.collections[c].hide_viewport = False
    bpy.data.collections["Arch"].hide_render = True
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


# ---------------------------------------------------------------- privacy
KEEP_PROPS = {"lightmap", "lightmap_intensity", "lightmap_night", "lightmap_night_intensity"}
LAYOUT_PREFIX = ("DoorLeaf_", "Marker_", "Spot_")


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private():
    kinds = ("scenes", "worlds", "objects", "meshes", "materials", "collections", "cameras", "lights", "images", "node_groups", "screens",
             "window_managers", "workspaces", "curves", "fonts", "libraries")
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
                    if st is not idb and k.startswith(("cycles", "eevee")):
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
    base = blend_path(SCENE).parent
    for im in bpy.data.images:
        if im.packed_file or im.source != "FILE" or not im.filepath:
            continue
        p = Path(bpy.path.abspath(im.filepath))
        try:
            rel = "//" + os.path.relpath(p, base).replace("\\", "/")
        except ValueError:
            rel = "//" + p.name
        set_path(im, "filepath", rel)
    for im in bpy.data.images:
        if im.packed_file and im.filepath and not im.filepath.startswith("//generated/"):
            set_path(im, "filepath", "//packed/" + bpy.path.clean_name(im.name) + ".png")
    for lib in list(bpy.data.libraries):
        try:
            bpy.data.libraries.remove(lib)
        except Exception:
            pass


def save_blend():
    p = blend_path(SCENE)
    p.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(p))
    scrub_private()
    bpy.ops.wm.save_mainfile()


def load_scene_file():
    bpy.ops.wm.open_mainfile(filepath=str(blend_path(SCENE)))
    global ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, LIGHTS, ALTL
    c = bpy.data.collections
    ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, LIGHTS, ALTL = (c.get(n) for n in ("Art", "Props", "Arch", "Skin", "Doors", "Layout", "Lights", "Lights_Alt"))
    for m in bpy.data.materials:
        MATS[m.name] = m


# ---------------------------------------------------------------- export
def caps():
    p = stills_dir(SCENE) / "caps.json"
    return json.loads(p.read_text()) if p.exists() else {}


def stage_export():
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    for c in ("Art", "Skin"):
        bpy.data.collections[c].hide_viewport = True
    leaves = [o for o in bpy.data.collections["Doors"].objects if o.type == "MESH"]
    stash = {o.name: {k: o[k] for k in o.keys()} for o in leaves}
    for o in leaves:
        for k in list(o.keys()):
            del o[k]
    cj = caps()
    f, fn = cj.get("factor", {}), cj.get("factor_night", cj.get("factor", {}))
    base = {}
    for m in bpy.data.materials:
        for key, ff in (("lightmap_intensity", f), ("lightmap_night_intensity", fn)):
            if key in m:
                base.setdefault(m.name, {})[key] = m[key]
                m[key] = round(m[key] * ff.get(m.name, 1.0), 4)
        if m.name in base:
            m["base"] = dict(base[m.name])                  # the uncapped intensities, for --caps (tools re-run caps without Blender)
    bpy.ops.object.select_all(action="DESELECT")
    for o in list(exp.objects) + leaves:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = work() / f"{SCENE}_raw.glb"
    renamed = []
    for o in list(exp.objects):
        want = o.name[:-2] if o.name.endswith("_x") else o.name.split(".")[0]
        if want != o.name:
            other = bpy.data.objects.get(want)
            if other is not None:
                other.name = want + "__src"
                renamed.append((other, want))
            o.name = want
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_animations=False)
    for o in list(exp.objects):
        o.name = o.name + ("_x" if o.name.startswith(TRICK_PREFIX) else ".exp")
    for other, want in renamed:
        other.name = want
    for o in leaves:
        for k, v in stash[o.name].items():
            o[k] = v
    for m in bpy.data.materials:
        if m.name in base:
            for key, v in base[m.name].items():
                m[key] = v
            del m["base"]
    print("EXPORTED", raw, raw.stat().st_size, "caps", f)
    for c in ("Art", "Skin"):
        bpy.data.collections[c].hide_viewport = False
    exp.hide_viewport = exp.hide_render = True
    import export_scene
    export_scene.write(SCENE, world_json(SCENE))
    save_blend()


def stage_axes():
    import struct
    M = model()
    mk = next((e for e in M.empties if e["name"].startswith(("Marker_", "Arrive_"))))
    a = list(mk["pos"])
    me = bpy.data.meshes.new("axes_marker")
    bm = bmesh.new()
    cube(bm, (a[0] - 0.1, a[1], a[2] - 0.1), (a[0] + 0.1, a[1] + 0.2, a[2] + 0.1))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("axes_marker", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    path = work() / f"axes_{SCENE}.glb"
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_yup=True, export_apply=True, export_materials="NONE")
    b = path.read_bytes()
    j = json.loads(b[20:20 + struct.unpack("<I", b[12:16])[0]])
    acc = j["accessors"][j["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    off = j["nodes"][0].get("translation", [0, 0, 0])
    centre = [(acc["min"][i] + acc["max"][i]) / 2 + off[i] for i in range(3)]
    want = [a[0], a[1] + 0.1, a[2]]
    print(f"AXES glTF centre {tuple(round(v, 3) for v in centre)}, game point {tuple(want)} ({mk['name']})")
    assert all(abs(centre[i] - want[i]) < 1e-4 for i in range(3))
    print("AXES PASS: game (x, y, z) = Blender (x, -z, y) = glTF (x, y, z)")
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)


def stage_check():
    """tools/blender/check_layout.py's three rules on Art (the shell's grey twins shown): every arrival and F spot of the room's links is checked
    for clearance (an RDWE room has no markers; its links are its arrival points)."""
    import check_layout
    for o in bpy.data.collections["Arch"].objects:
        o.hide_render = False
    world = json.loads(world_json(SCENE).read_text())
    # the rule is on the plan only, so a point up on a ledge, a landing or a terrace would read as inside the block it stands on: those are
    # checked in three dimensions by build_rdwe_greybox.py --check (clear by 0.28 m, with a floor under them) and left out here
    consts = {"links": {l["door"]: {"arrive": l["arrive"], "at": [l["at"][0], l["at"][2]]} for l in world.get("links", []) if l["at"][1] < 0.3}}
    print("CLEAR leaves out the raised points:", [l["door"] for l in world.get("links", []) if l["at"][1] >= 0.3])
    parts = check_layout.blender_parts("Art")
    print(f"layout check: scene {SCENE}, {len(parts)} visible meshes, {len(world['colliders'])} colliders")
    bad = check_layout.report(check_layout.check(parts, world, consts))
    for o in bpy.data.collections["Arch"].objects:
        o.hide_render = True
    print(f"CHECK_LAYOUT {SCENE} exit", 1 if bad else 0)
    return bad


# ---------------------------------------------------------------- review stills
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
    cam.clip_start, cam.clip_end = 0.03, 300
    ob = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = B(loc)
    if target is not None:
        ob.rotation_euler = (B(target) - B(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


def strip_jpeg_comments(path):
    """Blender writes render metadata as JPEG comment segments even with every stamp off; drop them, and any APP1 (EXIF) segment."""
    b = path.read_bytes()
    out, i = bytearray(b[:2]), 2
    while i < len(b) and b[i] == 0xFF and b[i + 1] != 0xDA:
        n = int.from_bytes(b[i + 2:i + 4], "big")
        if b[i + 1] not in (0xFE, 0xE1):
            out += b[i:i + 2 + n]
        i += 2 + n
    out += b[i:]
    path.write_bytes(bytes(out))


EXPOSURE = {}


def plan_box():
    cols = [b for b in shell_boxes() if not b["name"].startswith("Beyond_")]
    x0, x1 = min(c["min"][0] for c in cols) - 0.4, max(c["max"][0] for c in cols) + 0.4
    z0, z1 = min(c["min"][2] for c in cols) - 0.4, max(c["max"][2] for c in cols) + 0.4
    return x0, x1, z0, z1


def stage_render():
    import re
    sc = bpy.context.scene
    d = stills_dir(SCENE)
    d.mkdir(parents=True, exist_ok=True)
    scrub_private()
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
    for c, hide in (("Art", False), ("Skin", False), ("Doors", False), ("Lights", False), ("Lights_Alt", False)):
        bpy.data.collections[c].hide_render = hide
    bpy.data.collections["Arch"].hide_render = True
    setup_cycles(arg("--render-samples", 128, int))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.03
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    bj = work() / f"{SCENE}_bake.json"
    g = json.loads(bj.read_text())["0"]["gain"] if bj.exists() else 1.0
    sc.view_settings.exposure = arg("--exposure", round(math.log2(g) - 0.4 + EXPOSURE.get(SCENE, 0.0), 2), float)
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    which = arg("--only", "all")
    for key, (loc, tgt, fov) in SHOTS[SCENE].items():
        if which not in ("all", key):
            continue
        sc.camera = look_cam(key, loc, tgt, fov)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 1080, 100
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        path = d / f"{key}.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 400_000 and q > 40:
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        strip_jpeg_comments(path)
        print("STILL", key, path.stat().st_size, "q", q)
    if which in ("all", "plan"):
        x0, x1, z0, z1 = plan_box()
        span = max(x1 - x0, z1 - z0)
        cam = look_cam("plan", ((x0 + x1) / 2, 40.0, (z0 + z1) / 2), None, ortho=span)
        cam.rotation_euler = (0, 0, 0)
        if (z1 - z0) > (x1 - x0):
            cam.data.sensor_fit = "VERTICAL"
        sc.camera = cam
        hidden = []
        ceil = set(CEIL_MAT.values())
        for o in list(bpy.data.collections["Skin"].objects) + list(bpy.data.collections["Props"].objects) + list(bpy.data.collections["Doors"].objects):
            if o.type != "MESH":
                continue
            lowest = min((o.matrix_world @ v.co).z for v in o.data.vertices) if o.data.vertices else 0
            if o.name in ceil or (lowest > 2.6 and not o.name.startswith(("Step", "Fill", "Landing", "Ledge", "Chair_", "decor_Trick_Painted"))):
                if not o.hide_render:
                    o.hide_render = True
                    hidden.append(o)
        arch = bpy.data.collections["Arch"]
        arch.hide_render = False
        floorish = re.compile(r".*(_Floor|_Ceiling|Landing|Under.*)(_\d+)?$")
        for o in arch.objects:
            o.hide_render = bool(floorish.match(o.name)) or o.name.startswith(("Step_", "Beyond_", "Well_Ceiling"))
        world = sc.world
        bg = world.node_tree.nodes["Background"]
        old = bg.inputs["Strength"].default_value
        bg.inputs["Color"].default_value = (1, 1, 1, 1)
        bg.inputs["Strength"].default_value = 0.8
        W = 1800
        if (z1 - z0) > (x1 - x0):
            Hh, W = 1800, max(300, int(round(1800 * (x1 - x0) / (z1 - z0))))
        else:
            Hh = max(300, int(round(W * (z1 - z0) / (x1 - x0))))
        sc.render.resolution_x, sc.render.resolution_y = W, Hh
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 88
        path = work() / f"{SCENE}_plan.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        strip_jpeg_comments(path)
        bg.inputs["Strength"].default_value = old
        bg.inputs["Color"].default_value = (0.01, 0.012, 0.02, 1)
        for o in hidden:
            o.hide_render = False
        for o in arch.objects:
            o.hide_render = True
        arch.hide_render = True
        print("PLAN", path, W, Hh)


# ---------------------------------------------------------------- main
def main():
    global SCENE
    import traceback
    failed = []
    for sc in arg("--scenes", ",".join(SCENES)).split(","):
        SCENE = sc
        print(f"==== {sc} stage {STAGE}")
        try:
            if STAGE == "encode":
                stage_encode_blender()
                continue
            if STAGE in ("art", "all", "preview"):
                build_all()
                save_blend()
            else:
                load_scene_file()
            if STAGE in ("art", "preview"):
                import export_scene
                export_scene.write(SCENE, world_json(SCENE))
                stage_check()
            if STAGE == "preview":
                stage_render()
            if STAGE in ("bake", "all"):
                stage_bake()
            if STAGE in ("export", "all", "reexport"):
                stage_export()
            if STAGE in ("axes", "all"):
                stage_axes()
            if STAGE in ("check", "all", "reexport"):
                stage_check()
            if STAGE in ("render", "all"):
                stage_render()
                save_blend()
        except Exception:
            traceback.print_exc()
            failed.append(sc)
        print(f"==== {sc} done")
    print("ROOMS1 ALL DONE, failed:", failed or "none")
    sys.stdout.flush()
    sys.exit(1 if failed else 0)


main()
