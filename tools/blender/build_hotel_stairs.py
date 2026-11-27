"""Dresses and lights the hotel's last pieces (docs/BLENDER_AREAS.md, section 1, step 2): the connector scenes `escalators` and `other_stairs`
between the atrium's four galleries, and the two room layouts `clue_room` and `empty_room` that load behind floor 3's doors
(docs/renders/escalators/README.md covers all four).

    blender -b --factory-startup --python tools/blender/build_hotel_stairs.py -- --scenes escalators,other_stairs,clue_room,empty_room --stage all
    blender -b --factory-startup blender/scenes/<scene>.blend --python tools/blender/build_hotel_stairs.py -- --scenes <scene> --stage bake|export|axes|check|render
    python tools/blender/build_hotel_stairs.py --pack <scene> [--work <dir>]           (no Blender: WebP lightmaps and textures -> world/)

Stages, as tools/blender/build_hotel_floor1.py's (floor 1, the motel): art (the layout objects from the greybox, the art, the lights; saves
blender/scenes/<scene>.blend) -> bake (the seen shell and the merged props on fixed lightmap PAGES, Cycles, OIDN, 8-bit PNGs in the work folder)
-> export (the GLB to the work folder; the layout through tools/blender/export_scene.py, which must write the greybox's file unchanged) -> axes
(the marker-cube check) -> check (tools/blender/check_layout.py) -> render (docs/renders/<scene>/1_arrival, 2_wide, 3_detail.jpg and plan.jpg).

The layout is the greybox's (tools/blender/build_hotel_greybox.py): every COL_ box, DoorLeaf_, Link_/Arrive_, Marker_ and Spot_ is made from its
model with the same names and numbers. The greybox gained, with this dressing, the escalators' balustrades, newels, landing guards and the ground
run's closed truss, and the solid base of the stairwell's ground flight, each with its collider (esc_solids() there); no step, link, door or spot
moved. What is seen of the shell is tools/blender/hotel_stairs_skin.py's skin.

- escalators: three stopped escalators. One step mesh (`Esc_Step`: a grooved steel tread with yellow edges, a cleated riser), 48 linked copies;
  black handrails, ivory balustrade panels with round lamps (Lamp_Emit), steel skirts, champagne cladding; steel floor plates at the ends; the
  landings carry the carpet of the gallery they open onto (floor 1 red, floor 2 green, floor 3 tan), the ground the sub floor's white tile.
- other_stairs: a switchback service stair, painted concrete with yellow nosings, a steel handrail each side of every flight; at every landing a
  stencilled level number, an EXIT sign over the door (Emergency_Emit) and a caged lamp (Lamp_Emit); a caged lamp on each half landing too.
- clue_room: a floor 3 hotel room holding a clue: a pinboard of notes, maps and clippings joined by red string, a desk with a green-shaded lamp,
  papers everywhere. No people or figure images anywhere.
- empty_room: stripped. A bare concrete floor with old adhesive, a stain where the bed stood, paler patches where it and the pictures were, one bare
  bulb on its cord, the curtains open on a black window, the greybox's single chair.

Light: the two connector halls are baked at night (one set); the rooms are baked once with their lamps on and the door open onto a stand-in of
floor 3's corridor, so a room fits whichever door it sits behind.
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import hotel_stairs_skin as SK  # noqa: E402
GB = SK.GB

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
SAMPLES = arg("--samples", 1024, int)
DEVICE = arg("--device", "auto")
MARGIN_PX = 8
TEXDIR = ROOT / "blender/textures"
SCENE = None          # set per scene in main()
KIND = None           # "hall" | "room"

PAGES = {"escalators": [2048, 2048], "other_stairs": [2048, 1024], "clue_room": [1024, 1024], "empty_room": [1024, 1024]}
BAKE_LEAF = {"escalators": {"Leaf_Esc": "DoorLeaf_atrium_L0"}, "other_stairs": {"Leaf_Stair": "DoorLeaf_atrium_L0"}}
WHITE_CAP = 12.0       # a map's white point: its 99.5th percentile texel, at most 12 x its 90th
SHOULDER = (70.0, 2.5)  # the bake's highlight shoulder: light above the map's 70th percentile k rolls off toward 2.5k

# lights (Cycles watts) and the toggled materials' strengths
BAL_W, SCONCE_W, BULK_W, CAGE_W, EXIT_EMIT, SHADE_EMIT = 3.0, 110.0, 30.0, 50.0, 4.0, 3.0
DESK_W, DOME_W, BULB_W, CORR_SCONCE_W = 32.0, 34.0, 70.0, 45.0
WARM = (1.0, 0.78, 0.52)
COOL = (0.86, 0.9, 1.0)
E = 1.6                # eye height for the stills


def work():
    p = Path(arg("--work", str(Path(os.environ.get("TEMP", tempfile.gettempdir())) / "farway_hotel_stairs")))
    p.mkdir(parents=True, exist_ok=True)
    return p


def world_json(sc):
    return ROOT / ("world/rooms" if sc in SK.ROOMS else "world") / f"{sc}.json"


def glb_path(sc):
    return ROOT / ("world/rooms" if sc in SK.ROOMS else "world") / f"{sc}.glb"


def blend_path(sc):
    return ROOT / f"blender/scenes/{sc}.blend"


def stills_dir(sc):
    return ROOT / f"docs/renders/{sc}"


def lm_url(sc, n):
    return f"world/lightmaps/{sc}_{n}.webp"


# ================================================================ pack (plain Python, no Blender)
def pack(sc):
    from PIL import Image
    import subprocess
    w = work()
    out = ROOT / "world/lightmaps"
    out.mkdir(parents=True, exist_ok=True)
    pngs = sorted(w.glob(f"{sc}_[0-9].png"))
    assert pngs and len(pngs) <= 4, pngs
    for png in pngs:
        im = Image.open(png).convert("RGB")
        assert max(im.size) <= 2048
        dst = out / (png.stem + ".webp")
        im.save(dst, "WEBP", quality=90, method=6)
        print(f"{dst.relative_to(ROOT)}  {im.size[0]}x{im.size[1]}  {dst.stat().st_size / 1e3:.0f} KB")
    raw = w / f"{sc}_raw.glb"
    dst = glb_path(sc)
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / "tools/webp_glb.py"), str(raw), str(dst), "90"], check=True)
    print(f"{dst.relative_to(ROOT)}  {dst.stat().st_size / 1e6:.2f} MB")


if bpy is None:
    if "--pack" in args:
        pack(arg("--pack"))
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
    """Value noise that tiles in both directions, 0..1."""
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


def col(*rgb):
    return np.array(rgb, float) / 255.0


def lerp(a, b, t):
    t = np.asarray(t)[..., None] if np.ndim(t) else t
    return a * (1 - t) + b * t


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def load_pixels(rel):
    im = bpy.data.images.load(str(TEXDIR / rel))
    w, h = im.size
    a = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(a)
    bpy.data.images.remove(im)
    return a.reshape(h, w, 4)[..., :3].astype(float)


def grid(H, W, sy, sx):
    """Pixel-centre coordinates (metres): rows 0..sy (row 0 is the image's BOTTOM in Blender), columns 0..sx."""
    y = (np.arange(H) + 0.5) / H * sy
    x = (np.arange(W) + 0.5) / W * sx
    return np.meshgrid(y, x, indexing="ij")


def gen_tile(size=1.2, cell=0.15, base=(226, 224, 214), grout=(150, 146, 136), seed=106, band=None):
    """Glazed 15 cm tiles with grey grout, `size` m square; `band`: (row, rgb) a coloured row (the dado's top)."""
    H = W = 1024
    rng = np.random.default_rng(seed)
    Y, X = grid(H, W, size, size)
    gx = np.minimum(np.mod(X, cell), cell - np.mod(X, cell))
    gy = np.minimum(np.mod(Y, cell), cell - np.mod(Y, cell))
    g = np.minimum(gx, gy)
    tid = (np.floor(X / cell) * 7 + np.floor(Y / cell) * 13) % 6
    img = np.broadcast_to(col(*base), (H, W, 3)) * (0.9 + 0.02 * tid[..., None]) / 0.95
    if band:
        row, rgb = band
        m = np.floor(Y / cell) == row
        img = np.where(m[..., None], col(*rgb) * (0.92 + 0.03 * tid[..., None]), img)
    img = lerp(img, col(*grout), smooth(0.003, 0.0012, g))
    n = vnoise(H, W, rng, 4, 4)
    img *= (0.94 + 0.08 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_brushed(seed=108):
    H = W = 256
    rng = np.random.default_rng(seed)
    n = vnoise(H, W, rng, 3, 2)
    streak = vnoise(H, 8, rng, 3, 64)
    streak = np.repeat(streak, W // 8, axis=1)
    return np.clip((0.7 + 0.12 * streak + 0.08 * n)[..., None] * np.ones(3), 0, 1)


def gen_tread():
    """An escalator step's tread, 1.2 m across (u) by 0.3 m along (v, v = 0 at the nosing): aluminium cleats along the travel every 6 mm, yellow
    demarcation 4 cm wide along both sides and the nosing, scuffed."""
    H, W = 256, 1024
    rng = np.random.default_rng(301)
    Y, X = grid(H, W, 0.3, 1.2)
    cleat = 0.5 + 0.5 * np.cos(2 * np.pi * X / 0.006)
    img = lerp(col(42, 42, 44), col(168, 168, 164), smooth(0.25, 0.65, cleat))
    yel = (X < 0.04) | (X > 1.16) | (Y < 0.04)
    img = np.where(yel[..., None], lerp(col(70, 58, 18), col(214, 170, 40), smooth(0.25, 0.65, cleat)), img)
    n = vnoise(H, W, rng, 5, 3)
    img *= (0.82 + 0.3 * n)[..., None]
    wear = np.exp(-((X - 0.6) / 0.28) ** 2) * (0.5 + 0.5 * n)
    img = lerp(img, col(120, 118, 112), 0.25 * wear)
    return np.clip(img, 0, 1)


def gen_riser():
    """The riser: 1.2 m across by 0.25 m, vertical cleats every 6 mm, darker."""
    H, W = 128, 1024
    rng = np.random.default_rng(302)
    Y, X = grid(H, W, 0.25, 1.2)
    cleat = 0.5 + 0.5 * np.cos(2 * np.pi * X / 0.006)
    img = lerp(col(28, 28, 30), col(120, 120, 118), smooth(0.3, 0.7, cleat))
    n = vnoise(H, W, rng, 4, 3)
    img *= (0.85 + 0.25 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_plate():
    """The landing plates at an escalator's ends: brushed aluminium with raised diagonal ribs."""
    H = W = 512
    rng = np.random.default_rng(303)
    Y, X = grid(H, W, 0.5, 0.5)
    rib = np.minimum(np.abs(np.mod(X + Y, 0.05) - 0.025), np.abs(np.mod(X - Y, 0.05) - 0.025))
    img = np.ones((H, W, 3)) * col(150, 150, 146)
    img = lerp(img, col(196, 196, 190), smooth(0.006, 0.002, rib))
    n = vnoise(H, W, rng, 4, 3)
    img *= (0.85 + 0.25 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_carpet(kind):
    """The landings' carpets, 1 m square, as the gallery each opens onto: the motel's red hex lattice, floor 2's green with gold fleurons,
    floor 3's tan with a fine cream grid."""
    H = W = 512
    rng = np.random.default_rng({"motel": 311, "green": 312, "apart": 313, "clue": 314}[kind])
    Y, X = grid(H, W, 1.0, 1.0)
    n = vnoise(H, W, rng, 6, 3)
    fine = vnoise(H, W, rng, 3, 64)
    if kind == "motel":
        img = np.broadcast_to(col(104, 30, 34), (H, W, 3)).copy()
        P = 0.25
        u, v = np.mod(X, P) - P / 2, np.mod(Y + (np.floor(X / P) % 2) * P / 2, P) - P / 2
        d = np.maximum(np.abs(u) * 1.15 + np.abs(v) * 0.58, np.abs(v) * 1.15)
        img = lerp(img, col(160, 118, 58), smooth(0.012, 0.004, np.abs(d - 0.1)))
        img = lerp(img, col(52, 22, 30), smooth(0.04, 0.03, d))
    elif kind == "green":
        img = np.broadcast_to(col(36, 74, 44), (H, W, 3)).copy()
        P = 0.33
        u, v = np.mod(X, P) - P / 2, np.mod(Y, P) - P / 2
        r = np.sqrt(u ** 2 + v ** 2)
        a = np.arctan2(v, u)
        petal = 0.055 * (0.6 + 0.4 * np.cos(4 * a))
        img = lerp(img, col(150, 122, 60), smooth(petal, petal - 0.01, r))
        img = lerp(img, col(26, 52, 32), smooth(0.012, 0.005, np.abs(r - 0.11)) * 0.7)
    elif kind == "apart":
        img = np.broadcast_to(col(150, 122, 88), (H, W, 3)).copy()
        P = 0.2
        g = np.minimum(np.abs(np.mod(X, P) - P / 2), np.abs(np.mod(Y, P) - P / 2))
        img = lerp(img, col(196, 176, 140), smooth(0.006, 0.002, P / 2 - g) * 0.6)
    else:
        img = np.broadcast_to(col(118, 92, 66), (H, W, 3)).copy()
        P = 0.18
        u, v = np.mod(X, P) - P / 2, np.mod(Y, P) - P / 2
        d = np.abs(u) + np.abs(v)
        img = lerp(img, col(84, 62, 46), smooth(0.012, 0.004, np.abs(d - 0.06)))
        img = lerp(img, col(150, 120, 80), smooth(0.02, 0.012, d) * 0.6)
    img *= (0.84 + 0.3 * fine)[..., None]
    img *= (0.88 + 0.24 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_block(tint_src="main_floor/wall_paint_diff.jpg"):
    """Painted concrete block: 0.4 x 0.2 m blocks with mortar joints, 1.6 m square (as floor 1's stairwell)."""
    src = load_pixels(tint_src)
    H, W = src.shape[:2]
    Y, X = grid(H, W, 1.6, 1.6)
    row = np.floor(Y / 0.2)
    xo = X + (row % 2) * 0.2
    j = np.minimum(np.abs(np.mod(Y, 0.2)), np.abs(np.mod(Y, 0.2) - 0.2))
    j = np.minimum(j, np.minimum(np.abs(np.mod(xo, 0.4)), np.abs(np.mod(xo, 0.4) - 0.4)))
    return np.clip(src * (1 - 0.22 * smooth(0.008, 0.003, j))[..., None], 0, 1)


def gen_stain(seed, size=512, dark=False, rgb=None, alpha=1.0):
    """A stain (RGBA): a soft tide-marked blot, transparent around it."""
    rng = np.random.default_rng(seed)
    t = (np.arange(size) + 0.5) / size * 2 - 1
    Y, X = np.meshgrid(t, t, indexing="ij")
    n = vnoise(size, size, rng, 5, 3)
    r = np.sqrt(X ** 2 + Y ** 2) + 0.45 * (n - 0.5)
    inside = smooth(0.78, 0.6, r)
    rim = smooth(0.07, 0.0, np.abs(r - 0.66)) + 0.6 * smooth(0.05, 0.0, np.abs(r - 0.42))
    c = col(*rgb) if rgb else (col(40, 24, 18) if dark else col(128, 92, 52))
    out = np.broadcast_to(c, (size, size, 3)) * (0.85 + 0.3 * n)[..., None]
    a = np.clip(0.28 * inside + 0.55 * rim * smooth(0.85, 0.6, r), 0, 0.85) * (0.5 if dark else 1.0) * alpha
    return np.concatenate([np.clip(out, 0, 1), a[..., None]], axis=2)


def gen_bedstain():
    """Where the bed stood (RGBA, 1.6 x 2.0 m): a dark rectangle of old grime with soft edges and a tide line, a paler band round it where the
    bedspread hung, and four darker dents for the legs."""
    H, W = 640, 512
    rng = np.random.default_rng(321)
    Y, X = grid(H, W, 2.2, 1.8)
    n = vnoise(H, W, rng, 5, 3)
    dx = np.abs(X - 0.9) - 0.8
    dy = np.abs(Y - 1.1) - 1.0
    d = np.maximum(dx, dy) + 0.05 * (n - 0.5)
    inside = smooth(0.02, -0.08, d)
    rim = smooth(0.03, 0.0, np.abs(d + 0.02))
    rgb = np.broadcast_to(col(46, 36, 28), (H, W, 3)) * (0.8 + 0.4 * n)[..., None]
    a = np.clip(0.5 * inside * (0.7 + 0.5 * n) + 0.4 * rim, 0, 0.85)
    for lx, ly in ((0.13, 0.13), (1.67, 0.13), (0.13, 2.07), (1.67, 2.07)):
        a = np.maximum(a, 0.9 * smooth(0.035, 0.02, np.sqrt((X - lx) ** 2 + (Y - ly) ** 2)))
    return np.concatenate([np.clip(rgb, 0, 1), a[..., None]], axis=2)


def gen_ghost(seed, w=256, h=256, rgb=(236, 228, 210), alpha=0.5):
    """A paler patch on a wall (RGBA) where something hung for years: a soft-edged rectangle, a faint dirt line at its top edge."""
    rng = np.random.default_rng(seed)
    Y, X = grid(h, w, 1.0, 1.0)
    n = vnoise(h, w, rng, 4, 3)
    d = np.maximum(np.abs(X - 0.5), np.abs(Y - 0.5)) * 2
    a = smooth(1.0, 0.86, d + 0.04 * (n - 0.5)) * alpha
    out = np.broadcast_to(col(*rgb), (h, w, 3)) * (0.95 + 0.08 * n)[..., None]
    line = smooth(0.06, 0.0, np.abs(Y - 0.97)) * smooth(0.5, 0.45, np.abs(X - 0.5))
    out = lerp(out, col(90, 80, 66), line * 0.8)
    a = np.maximum(a, line * 0.6 * alpha)
    return np.concatenate([np.clip(out, 0, 1), a[..., None]], axis=2)


def gen_wallpaper(kind):
    """Hotel wallpaper, 1 m square. clue: faded sage and cream stripes with a fine damask line. stripped: the same paper, torn away in patches
    to grey plaster, glue streaks where it came off, a few curled edges darker."""
    H = W = 1024
    rng = np.random.default_rng(331 if kind == "clue" else 332)
    size = 1.0 if kind == "clue" else 2.0
    Y, X = grid(H, W, size, size)
    src = load_pixels("main_floor/wall_paint_diff.jpg")
    sh, sw = src.shape[:2]
    plaster = src[(np.arange(H) * sh // H)][:, (np.arange(W) * sw // W)] * col(196, 194, 186) / max(float(src.mean()), 1e-3) * 0.8
    stripe = np.mod(X, 0.25) < 0.125
    paper = np.where(stripe[..., None], col(196, 190, 160), col(214, 206, 180))
    fl = np.abs(np.mod(X + 0.0625, 0.125) - 0.0625)
    paper = lerp(paper, col(170, 162, 128), smooth(0.004, 0.0015, fl) * 0.7)
    n = vnoise(H, W, rng, 5, 3)
    paper = paper * (0.9 + 0.16 * n)[..., None]
    if kind == "clue":
        return np.clip(paper, 0, 1)
    m = vnoise(H, W, rng, 5, 2)
    m = m + 0.12 * (vnoise(H, W, rng, 3, 16) - 0.5)
    torn = smooth(0.48, 0.5, m)
    edge = smooth(0.012, 0.0, np.abs(m - 0.49))
    glue = (0.5 + 0.5 * np.sin(X * 90 + 6 * n)) * smooth(0.4, 0.6, vnoise(H, W, rng, 3, 4))
    bare = plaster * (1 - 0.12 * glue)[..., None]
    img = lerp(paper, bare, torn)
    img = lerp(img, col(120, 106, 80), edge * 0.6)
    return np.clip(img, 0, 1)


def gen_subfloor():
    """The empty room's bare floor, 2 m square: grey concrete screed (the repo's CC0 concrete), the carpet's adhesive left in combed arcs, a few
    tack-strip nail holes."""
    src = load_pixels("factory_floor/concrete_floor_diff.jpg")
    H, W = src.shape[:2]
    rng = np.random.default_rng(341)
    Y, X = grid(H, W, 2.0, 2.0)
    n = vnoise(H, W, rng, 5, 3)
    base = src * col(200, 196, 188) / max(float(src.mean()), 1e-3) * 0.55
    arcs = 0.5 + 0.5 * np.sin(np.sqrt((X - 0.7) ** 2 + (Y + 0.4) ** 2) * 160 + 4 * n)
    patch = smooth(0.45, 0.6, vnoise(H, W, rng, 4, 2))
    img = lerp(base, col(84, 74, 52), 0.35 * patch * smooth(0.3, 0.8, arcs))
    img *= (0.9 + 0.16 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_cork():
    """The pinboard's cork, 3 m by 1.2 m."""
    H, W = 512, 1280
    rng = np.random.default_rng(351)
    n = vnoise(H, W, rng, 5, 6)
    g = rng.random((H, W))
    img = lerp(col(150, 104, 62), col(196, 150, 96), n)
    img = lerp(img, col(96, 62, 34), (g > 0.86) * 0.6)
    img = lerp(img, col(210, 170, 116), (g < 0.05) * 0.5)
    return np.clip(img, 0, 1)


NOTE_CELLS = 4, 4        # the notes atlas: 4 x 4 cells of 256 x 320 px


def gen_notes():
    """Sixteen papers in one atlas (cells 256 x 320, row 0 at the BOTTOM): lined pages and index cards in scrawled ink, yellow and pink sticky
    notes, a hand-drawn plan of a hotel corridor with one door ringed, a street map with a circled block, newspaper clippings (headline bars and
    columns of grey type), a photograph of an empty corridor, a photograph of a door, a room key tag, a torn calendar page with days crossed out.
    No people and no figures: every picture is of a place or a thing."""
    ch, cw = 320, 256
    R, C = NOTE_CELLS
    img = np.zeros((R * ch, C * cw, 3))
    rng = np.random.default_rng(361)
    ink, red = col(30, 34, 60), col(160, 28, 28)

    def scrawl(a, x0, x1, y0, y1, rows, color=ink, w=1.6, gap=0.0):
        hh, ww = a.shape[:2]
        for r in range(rows):
            yy = y0 + (y1 - y0) * (r + 0.5) / rows
            xs = np.arange(int(x0 * ww), int((x1 - rng.random() * 0.25) * ww))
            if len(xs) < 4:
                continue
            ph = rng.random() * 6
            ys = yy * hh + 3.2 * np.sin(xs * 0.35 + ph) + 1.6 * np.sin(xs * 1.7 + ph * 2)
            for x, y in zip(xs, ys):
                if gap and np.sin(x * 0.09 + ph) > 0.85:
                    continue
                y = int(y)
                a[max(0, y - int(w / 2)):y + int(w / 2) + 1, x] = color

    def paper(base):
        n = vnoise(ch, cw, rng, 3, 2)
        return np.broadcast_to(col(*base), (ch, cw, 3)) * (0.93 + 0.1 * n)[..., None]
    cells = []
    for k in range(R * C):
        kind = k % 8
        if kind == 0:                                     # lined page
            a = paper((232, 228, 214))
            for yy in range(30, ch - 10, 18):
                a[yy:yy + 1] = col(150, 170, 200)
            a[:, 34:36] = col(200, 120, 120)
            scrawl(a, 0.16, 0.94, 0.08, 0.86, 13, gap=1)
        elif kind == 1:                                   # sticky note
            a = paper((236, 214, 96) if k < 8 else (236, 160, 176))
            scrawl(a, 0.1, 0.9, 0.15, 0.75, 5, w=2.4)
            a[int(ch * 0.83):int(ch * 0.86), int(cw * 0.15):int(cw * 0.7)] = red
        elif kind == 2:                                   # hand-drawn corridor plan, one door ringed
            a = paper((236, 232, 220))
            a[140:144, 20:236] = ink
            a[190:194, 20:236] = ink
            for xx in range(34, 236, 40):
                a[100:140, xx:xx + 3] = ink
                a[194:234, xx:xx + 3] = ink
            Y, X = np.mgrid[0:ch, 0:cw]
            ring = np.abs(np.sqrt((X - 154) ** 2 + (Y - 120) ** 2) - 26) < 2.2
            a[ring] = red
            scrawl(a, 0.1, 0.9, 0.82, 0.95, 1, color=red, w=2.2)
            scrawl(a, 0.1, 0.6, 0.04, 0.16, 2)
        elif kind == 3:                                   # newspaper clipping
            a = paper((214, 208, 190))
            a[ch - 60:ch - 30, 16:240] = col(40, 40, 40)
            for c0 in (16, 92, 168):
                for yy in range(20, ch - 74, 7):
                    if rng.random() > 0.08:
                        a[yy:yy + 3, c0:c0 + 70] = col(120, 118, 110)
        elif kind == 4:                                   # street map, a block circled
            a = paper((226, 224, 204))
            for xx in range(0, cw, 46):
                a[:, xx:xx + 6] = col(250, 248, 240)
            for yy in range(10, ch, 52):
                a[yy:yy + 6] = col(250, 248, 240)
            a[:, 120:130] = col(220, 190, 120)
            a[60:200, 150:200] = col(170, 200, 150)
            Y, X = np.mgrid[0:ch, 0:cw]
            a[np.abs(np.sqrt((X - 86) ** 2 + ((Y - 200) * 1.2) ** 2) - 34) < 2.6] = red
        elif kind == 5:                                   # photograph: an empty corridor in perspective
            a = np.ones((ch, cw, 3)) * col(240, 238, 230)
            Y, X = np.mgrid[0:ch, 0:cw].astype(float)
            ph = (Y > 20) & (Y < ch - 50) & (X > 14) & (X < cw - 14)
            u, v = (X - cw / 2) / (cw / 2 - 14), (Y - (20 + ch - 50) / 2) / ((ch - 70) / 2)
            depth = np.maximum(np.abs(u), np.abs(v))
            tone = lerp(col(70, 52, 40), col(196, 160, 110), smooth(0.15, 1.0, depth))
            tone = lerp(tone, col(30, 24, 20), (depth < 0.16).astype(float))
            for t in (0.3, 0.45, 0.62, 0.8):
                tone = lerp(tone, col(60, 40, 30), (np.abs(np.abs(u) - t) < 0.02) * (np.abs(v) < t * 0.8) * 0.8)
            a[ph] = tone[ph] * (0.9 + 0.1 * rng.random((ph.sum(), 1)))
            scrawl(a, 0.15, 0.7, 0.04, 0.12, 1, w=2)
        elif kind == 6:                                   # photograph: a numbered door
            a = np.ones((ch, cw, 3)) * col(238, 236, 228)
            a[20:ch - 50, 14:cw - 14] = col(150, 128, 96)
            a[40:ch - 50, 70:cw - 70] = col(54, 74, 58)
            a[ch - 140:ch - 120, 112:144] = col(196, 160, 80)
            a[150:160, 160:172] = col(196, 160, 80)
            scrawl(a, 0.2, 0.8, 0.04, 0.12, 1, color=red, w=2)
        else:                                             # calendar page, days crossed out
            a = paper((240, 238, 232))
            a[ch - 50:ch - 14, 12:244] = col(150, 40, 40)
            for r in range(5):
                for c in range(7):
                    x0, y0 = 14 + c * 33, 20 + r * 46
                    a[y0:y0 + 1, x0:x0 + 31] = col(160, 160, 160)
                    a[y0:y0 + 44, x0:x0 + 1] = col(160, 160, 160)
                    if r * 7 + c < 19 + (k % 5):
                        for t in range(30):
                            a[y0 + 6 + t, x0 + 1 + t] = red
                            a[y0 + 36 - t, x0 + 1 + t] = red
        cells.append(a)
    for k, a in enumerate(cells):
        r, c = divmod(k, C)
        img[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw] = a
    return np.clip(img, 0, 1)


def gen_blind():
    """A closed Venetian blind, 1 m square: 2.5 cm cream slats, a shadow line under each."""
    H = W = 256
    Y, X = grid(H, W, 1.0, 1.0)
    t = np.mod(Y, 0.025) / 0.025
    img = lerp(col(214, 206, 186), col(150, 142, 124), smooth(0.7, 0.95, t))
    return np.clip(img, 0, 1)


def gen_grille():
    H = W = 128
    y = (np.arange(H) + 0.5) / H
    s = smooth(0.12, 0.06, np.abs(np.mod(y * 10, 1) - 0.5))
    img = np.ones((H, W, 3)) * col(200, 198, 190)
    img = lerp(img, col(30, 30, 30), np.broadcast_to(s[:, None], (H, W)))
    img[:6], img[-6:], img[:, :6], img[:, -6:] = col(210, 208, 200), col(210, 208, 200), col(210, 208, 200), col(210, 208, 200)
    return img


def gen_norm(rel, mean=0.55):
    """A repo photo texture lifted to a mean of `mean` (as stored, sRGB): the concrete and the dark wood are too dark to tint up otherwise."""
    src = load_pixels(rel)
    return np.clip(src * (mean / max(float(src.mean()), 1e-3)), 0, 1)


GEN = {}


def mk_image(name, arr):
    h, w = arr.shape[:2]
    alpha = arr.shape[2] == 4
    im = bpy.data.images.new(name, w, h, alpha=alpha)
    im.colorspace_settings.name = "sRGB"
    px = np.ones((h, w, 4), np.float32)
    px[..., :arr.shape[2]] = arr
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


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, tex=None, img=None, tint=None, emit=None, alpha=None, tile=1.0, img_alpha=False):
    """A Principled material. `tint` multiplies the texture (a Mix node set to Multiply: the glTF exporter writes it as baseColorFactor)."""
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
        if img_alpha:
            nt.links.new(n.outputs["Alpha"], bsdf.inputs["Alpha"])
            set_blend(m)
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    if alpha is not None:
        bsdf.inputs["Alpha"].default_value = alpha
        set_blend(m)
    TILES[name] = tile
    MATS[name] = m
    return m


WALLP, PLAST, WOOD, LINEN, CONC = "main_floor/wall_paint_diff.jpg", "laboratory/wall_paint_diff.jpg", "apartment/dark_wood_diff_1k.jpg", \
    "apartment/rough_linen_diff_512.jpg", "factory_floor/concrete_floor_diff.jpg"


def make_materials():
    g = {k: mk_image(k, f()) for k, f in (("gen_brushed", gen_brushed), ("gen_grille", gen_grille), ("gen_concrete", lambda: gen_norm(CONC, 0.6)),
                                          ("gen_wood", lambda: gen_norm(WOOD, 0.5)))}
    # shared
    material("Lamp_Emit", color=(1.0, 0.9, 0.74), rough=0.9, emit=(WARM, SHADE_EMIT))
    material("Lamp_Dead", color=srgb_lin("#a49c88"), rough=0.9)
    material("Steel", img=g["gen_brushed"], tint=srgb_lin("#a6a8a6"), rough=0.35, metal=0.9, tile=0.4)
    material("Brass", img=g["gen_brushed"], tint=srgb_lin("#b48c4c"), rough=0.35, metal=0.9, tile=0.3)
    material("Plastic_White", color=srgb_lin("#d6d2c6"), rough=0.5)
    material("Plastic_Black", color=srgb_lin("#1a1a1a"), rough=0.4)
    material("Grille", img=g["gen_grille"], rough=0.6, tile=0.3)
    material("Standin_Grey", color=(0.4, 0.38, 0.34), rough=0.9)
    if KIND == "hall":
        material("Door_Jamb", tex=WALLP, tint=srgb_lin("#6e726c"), rough=0.5, tile=1.0)
        material("Emergency_Emit", color=(0.1, 0.8, 0.3), rough=0.4, emit=((0.15, 1.0, 0.35), EXIT_EMIT))
        material("Sign_Green", color=srgb_lin("#0e3a1e"), rough=0.4)
        material("Iron_Black", color=srgb_lin("#1c1c1c"), rough=0.5, metal=0.6)
        material("Glass_Clear", color=(0.85, 0.92, 0.95), rough=0.05, alpha=0.16)
    if SCENE == "escalators":
        e = {k: mk_image(k, f()) for k, f in (("gen_tread", gen_tread), ("gen_riser", gen_riser), ("gen_plate", gen_plate),
                                              ("gen_floor_tile", lambda: gen_tile(1.2)),
                                              ("gen_wall_tile", lambda: gen_tile(1.2, band=(7, (64, 112, 86)), seed=107)),
                                              ("gen_carpet_motel", lambda: gen_carpet("motel")), ("gen_carpet_green", lambda: gen_carpet("green")),
                                              ("gen_carpet_apart", lambda: gen_carpet("apart")), ("gen_stain_floor", lambda: gen_stain(371, 256, True)))}
        material("Floor_Tile", img=e["gen_floor_tile"], rough=0.3, tile=1.2)
        material("Wall_Tile", img=e["gen_wall_tile"], rough=0.25, tile=1.2)
        material("Wall_Hall", tex=WALLP, tint=srgb_lin("#cfc4ae"), rough=0.85, tile=1.6)
        material("Ceiling_Hall", tex=PLAST, tint=srgb_lin("#b8b2a4"), rough=0.95, tile=1.6)
        material("Soffit_Plaster", tex=PLAST, tint=srgb_lin("#d8d0bc"), rough=0.95, tile=1.2)
        material("Fascia_Paint", tex=WALLP, tint=srgb_lin("#3c3a36"), rough=0.6, tile=1.0)
        material("Carpet_Motel", img=e["gen_carpet_motel"], rough=1.0, tile=1.0)
        material("Carpet_Green", img=e["gen_carpet_green"], rough=1.0, tile=1.0)
        material("Carpet_Apart", img=e["gen_carpet_apart"], rough=1.0, tile=1.0)
        material("Esc_Tread", img=e["gen_tread"], rough=0.4, metal=0.6)
        material("Esc_Riser", img=e["gen_riser"], rough=0.45, metal=0.6)
        material("Esc_Frame", color=srgb_lin("#202022"), rough=0.6)
        material("Esc_Plate", img=e["gen_plate"], rough=0.35, metal=0.8, tile=0.5)
        material("Esc_Skirt", img=g["gen_brushed"], tint=srgb_lin("#b4b6b2"), rough=0.3, metal=0.9, tile=0.5)
        material("Esc_Panel", tex=WALLP, tint=srgb_lin("#e2d8bc"), rough=0.45, tile=1.0)
        material("Esc_Clad", img=g["gen_brushed"], tint=srgb_lin("#a6a296"), rough=0.35, metal=0.85, tile=0.6)
        material("Esc_Handrail", color=srgb_lin("#121212"), rough=0.55)
        material("Comb_Yellow", color=srgb_lin("#c89a28"), rough=0.5)
        material("Red_Paint", color=srgb_lin("#9a2018"), rough=0.4)
        material("Leaf_Esc", tex=WALLP, tint=srgb_lin("#8a8c88"), rough=0.5, tile=1.0)
        material("Leaf_Glass", color=srgb_lin("#2a3234"), rough=0.2)
        material("Trim_Steel", img=g["gen_brushed"], tint=srgb_lin("#8c8e8a"), rough=0.35, metal=0.9, tile=0.4)
        material("Decal_Floor", img=e["gen_stain_floor"], rough=1.0, img_alpha=True)
    elif SCENE == "other_stairs":
        s = {k: mk_image(k, f()) for k, f in (("gen_block", gen_block), ("gen_stain_floor", lambda: gen_stain(381, 256, True)))}
        material("Stair_Paint", img=s["gen_block"], tint=srgb_lin("#d4d2c4"), rough=0.8, tile=1.6)
        material("Stair_Dado", img=s["gen_block"], tint=srgb_lin("#7e8c7a"), rough=0.7, tile=1.6)
        material("Stair_Edge", img=g["gen_concrete"], tint=srgb_lin("#b8b4a8"), rough=0.8, tile=1.5)
        material("Stair_Floor", img=g["gen_concrete"], tint=srgb_lin("#a6a69c"), rough=0.75, tile=1.5)
        material("Stair_Ceiling", img=g["gen_concrete"], tint=srgb_lin("#c8c6bc"), rough=0.9, tile=1.5)
        material("Stair_Step", img=g["gen_concrete"], tint=srgb_lin("#9c9c94"), rough=0.7, tile=1.5)
        material("Nosing_Yellow", color=srgb_lin("#c89a28"), rough=0.6)
        material("Rail_Steel", img=g["gen_brushed"], tint=srgb_lin("#6c7470"), rough=0.4, metal=0.85, tile=0.4)
        material("Stencil_Paint", color=srgb_lin("#1e2a24"), rough=0.6)
        material("Red_Paint", color=srgb_lin("#9a2018"), rough=0.4)
        material("Leaf_Stair", tex=WALLP, tint=srgb_lin("#7c8676"), rough=0.5, tile=1.0)
        material("Leaf_Glass", color=srgb_lin("#2a3234"), rough=0.2)
        material("Decal_Floor", img=s["gen_stain_floor"], rough=1.0, img_alpha=True)
    else:
        r = {k: mk_image(k, f()) for k, f in (("gen_notes", gen_notes), ("gen_blind", gen_blind))}
        material("Ceiling_Room", tex=PLAST, tint=srgb_lin("#e0d8c4"), rough=0.95, tile=1.2)
        material("Wood_Laminate", img=g["gen_wood"], tint=(0.55, 0.45, 0.38), rough=0.45, tile=0.8)
        material("Wood_Dark", img=g["gen_wood"], tint=(0.34, 0.25, 0.2), rough=0.45, tile=0.8)
        material("Paper", img=r["gen_notes"], rough=0.9)
        material("Window_Frame", img=g["gen_brushed"], tint=srgb_lin("#a4a49e"), rough=0.4, metal=0.7, tile=0.4)
        material("Window_Void", color=srgb_lin("#08090a"), rough=0.6)
        material("Curtain", tex=LINEN, tint=srgb_lin("#8a6a48"), rough=0.95, tile=0.5)
        material("SB_Carpet", color=srgb_lin("#6a3a2c"), rough=1.0)
        material("SB_Wall", color=srgb_lin("#a8a68c"), rough=0.8)
        material("SB_Ceiling", color=srgb_lin("#c8bea6"), rough=0.9)
        material("Door_Wood", img=g["gen_wood"], tint=srgb_lin("#46604a"), rough=0.45, tile=0.9)
        if SCENE == "clue_room":
            c = {k: mk_image(k, f()) for k, f in (("gen_carpet_clue", lambda: gen_carpet("clue")), ("gen_wall_clue", lambda: gen_wallpaper("clue")),
                                                  ("gen_cork", gen_cork))}
            material("Carpet_Clue", img=c["gen_carpet_clue"], rough=1.0, tile=1.0)
            material("Wall_Clue", img=c["gen_wall_clue"], rough=0.8, tile=1.0)
            material("Cork", img=c["gen_cork"], rough=0.95)
            material("String_Red", color=srgb_lin("#a01c1c"), rough=0.8)
            material("Pin_Heads", color=srgb_lin("#c43a2a"), rough=0.3)
            material("Blind", img=r["gen_blind"], rough=0.6, tile=1.0)
            material("Lamp_Green", color=srgb_lin("#1f5a36"), rough=0.2, metal=0.1)
            material("Mug", color=srgb_lin("#d8d2c4"), rough=0.3)
            material("Folder_Buff", color=srgb_lin("#b89a64"), rough=0.8)
        else:
            e = {k: mk_image(k, f()) for k, f in (("gen_subfloor", gen_subfloor), ("gen_wall_stripped", lambda: gen_wallpaper("stripped")),
                                                  ("gen_bedstain", gen_bedstain), ("gen_ghost", lambda: gen_ghost(391)))}
            material("Floor_Bare", img=e["gen_subfloor"], rough=0.85, tile=2.0)
            material("Wall_Stripped", img=e["gen_wall_stripped"], rough=0.85, tile=2.0)
            material("Decal_Bed", img=e["gen_bedstain"], rough=1.0, img_alpha=True)
            material("Decal_Ghost", img=e["gen_ghost"], rough=1.0, img_alpha=True)
            material("Bulb_Glass", color=(1.0, 0.92, 0.8), rough=0.1, emit=(WARM, 8.0))
            material("Cord", color=srgb_lin("#141414"), rough=0.6)
            material("Tack_Strip", img=g["gen_wood"], tint=(0.5, 0.42, 0.34), rough=0.8, tile=0.5)


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
    return bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                                 matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())


def tube(bm, p0, p1, r0, r1=None, seg=24):
    cyl(bm, p0, p1, r0, r1, seg, cap=False)


def sphere(bm, p, r, seg=12):
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(4, seg // 2), radius=r, matrix=Matrix.Translation(B(p)))


def prism(bm, ring_a, ring_b):
    """A closed solid between two matching rings of game points (each a convex polygon, in order): caps and side quads."""
    va = [bm.verts.new(B(p)) for p in ring_a]
    vb = [bm.verts.new(B(p)) for p in ring_b]
    n = len(va)
    bm.faces.new(va)
    bm.faces.new(list(reversed(vb)))
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((va[i], va[j], vb[j], vb[i]))


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


ART = PROPS = ARCH = SKIN = DOORS = LAYOUT = STANDIN = BAKE_STANDIN = LIGHTS = None


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


class Wall:
    """A wall face: the plane `axis` = p ('x' or 'z'), its inward normal sign s; `a` runs along it, `d` is the distance in front of it."""
    def __init__(s, axis, p, sign):
        s.axis, s.p, s.s = axis, p, sign

    def pt(s, a, y, d):
        return (a, y, s.p + s.s * d) if s.axis == "z" else (s.p + s.s * d, y, a)

    def box(s, bm, a0, a1, y0, y1, d0, d1):
        p0, p1 = s.pt(a0, y0, d0), s.pt(a1, y1, d1)
        cube(bm, [min(p0[i], p1[i]) for i in range(3)], [max(p0[i], p1[i]) for i in range(3)])

    def normal(s):
        return (0, 0, s.s) if s.axis == "z" else (s.s, 0, 0)

    def right(s):
        n = s.normal()
        return (n[2], 0, -n[0])          # the viewer's right, facing the wall


def text_mesh(body, size, extrude, spacing=1.0):
    """Blender's built-in text font as a mesh, centred on the origin, in text space (x right, y up, z toward the reader)."""
    cu = bpy.data.curves.new("txt", "FONT")
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    cu.space_character = spacing
    cu.resolution_u = 4
    ob = bpy.data.objects.new("txt", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return me


def add_text(bm, body, size, depth, origin, right, up, normal, spacing=1.0):
    """Text standing on a surface: `origin` its centre (game), `right`/`up`/`normal` game directions; `depth` its relief."""
    me = text_mesh(body, size, depth / 2, spacing)
    R, U, N = Vector(B(right)), Vector(B(up)), Vector(B(normal))
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


def wall_text(bm, w, body, a, y, d, size, depth=0.004, spacing=1.0):
    add_text(bm, body, size, depth, w.pt(a, y, d), w.right(), (0, 1, 0), w.normal(), spacing)


def quad(name, mat, corners, uvs, coll=None, normal=None):
    """One textured quad: four game points and their UVs; `normal` (game) the side it faces."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    vs = [bm.verts.new(B(p)) for p in corners]
    f = bm.faces.new(vs)
    f.normal_update()
    if normal is not None and f.normal.dot(B(normal)) < 0:
        f.normal_flip()
    for lp in f.loops:
        lp[uvl].uv = uvs[vs.index(lp.vert)]
    return finish(name, bm, mat, coll or PROPS, keep_uv=True)


# ---------------------------------------------------------------- layout objects (exported to the JSON, never to the GLB)
def col_box(name, mn, mx):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    cube(bm, mn, mx)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    LAYOUT.objects.link(ob)
    ob.hide_render = True
    ob.display_type = "WIRE"
    return ob


def layout_from_model(M):
    """Every COL_, Marker_, Link_/Arrive_ and Spot_ of the greybox model, with its names and numbers; each collider's grey twin in Art/Arch (for
    the layout check and the plan; never exported)."""
    for b in M.boxes:
        if b.get("zone"):
            continue
        if b["col"]:
            col_box("COL_" + b["name"], b["min"], b["max"])
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


# ---------------------------------------------------------------- the skin (the shell as seen)
def build_skin():
    q, M = SK.scene_skin(SCENE)
    by = {}
    for x in q:
        by.setdefault(SK.material(SCENE, x), []).append(x)
    for mname, quads in sorted(by.items()):
        skin_mesh(mname, quads, SKIN)
    if KIND == "room":
        sq, _ = SK.scene_skin(SCENE, standin=True)
        by = {}
        for x in sq:
            by.setdefault(SK.room_material(SCENE, x), []).append(x)
        for mname, quads in sorted(by.items()):
            skin_mesh("SB_" + mname if not mname.startswith("SB_") else mname, quads, BAKE_STANDIN, mname)
    return M


def skin_mesh(name, quads, coll, mname=None):
    mname = mname or name
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    tile = TILES.get(mname, 1.0)
    pieces = []
    for x in quads:                                      # long quads cut into pieces of 4 m at most
        nb = max(1, math.ceil((x["b"][1] - x["b"][0]) / 4.0))
        nc = max(1, math.ceil((x["c"][1] - x["c"][0]) / 4.0))
        for i in range(nb):
            for j in range(nc):
                y = dict(x)
                y["b"] = (x["b"][0] + (x["b"][1] - x["b"][0]) * i / nb, x["b"][0] + (x["b"][1] - x["b"][0]) * (i + 1) / nb)
                y["c"] = (x["c"][0] + (x["c"][1] - x["c"][0]) * j / nc, x["c"][0] + (x["c"][1] - x["c"][0]) * (j + 1) / nc)
                pieces.append(y)
    for x in pieces:
        pts = SK.quad_points(x)
        f = bm.faces.new([bm.verts.new(B(p)) for p in pts])
        f.normal_update()
        want = [0, 0, 0]
        want[x["axis"]] = x["side"]
        if f.normal.dot(B(want)) < 0:
            f.normal_flip()
        for lp, p in zip(f.loops, [(v.co.x, v.co.z, -v.co.y) for v in f.verts]):
            gx, gy, gz = p
            if x["axis"] == 0:
                u, v = gz / tile, gy / tile
            elif x["axis"] == 1:
                u, v = gx / tile, gz / tile
            else:
                u, v = gx / tile, gy / tile
            lp[uvl].uv = (u, v)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mname])
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


# ---------------------------------------------------------------- door leaves: one mesh per kind, a node per door (origin at the hinge)
LEAF_MESH = {}


def box_uv_local(bm, tile):
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            u, v = (p.y, p.z) if ax == 0 else (p.x, p.z) if ax == 1 else (p.x, p.y)
            lp[uvl].uv = (u / tile, v / tile)


def leaf_mesh(kind, width, height):
    """A steel door to the atrium: the leaf lies in the wall's thickness behind its hinge (local +Y is the atrium's side), its face to this scene
    (local -Y) flush with the wall's inner face. Local +X runs from the hinge along the leaf; z is up. A wired-glass vision panel, a lever on the
    atrium side, a push bar and the closer's arm on this side, a kick plate."""
    if kind in LEAF_MESH:
        return LEAF_MESH[kind]
    th = 0.045
    w, h = width - 0.006, height - 0.008
    pieces = []

    def bx(x0, x1, ya, yb, z0, z1, mat):
        mm = bmesh.new()
        mm.loops.layers.uv.new("UVMap")
        bmesh.ops.create_cube(mm, size=1.0, matrix=Matrix.Translation(((x0 + x1) / 2, (ya + yb) / 2, (z0 + z1) / 2)) @ Matrix.Diagonal((x1 - x0, yb - ya, z1 - z0, 1)))
        pieces.append((mm, mat))
    bx(0.003, w, 0.0, th, 0.006, h, kind)
    bx(w - 0.34, w - 0.14, -0.002, th + 0.002, 1.25, 1.85, "Leaf_Glass")
    hx = w - 0.08
    bx(hx - 0.03, hx + 0.03, th, th + 0.01, 0.92, 1.1, "Steel" if kind == "Leaf_Esc" else "Rail_Steel")
    bx(hx - 0.16, hx + 0.01, th + 0.01, th + 0.05, 1.0, 1.025, "Steel" if kind == "Leaf_Esc" else "Rail_Steel")
    for x0, x1 in ((0.08, 0.12), (w - 0.12, w - 0.08)):                                       # the push bar's brackets and the bar
        bx(x0, x1, -0.07, 0.0, 0.98, 1.06, "Steel" if kind == "Leaf_Esc" else "Rail_Steel")
    bx(0.08, w - 0.08, -0.075, -0.05, 1.0, 1.04, "Steel" if kind == "Leaf_Esc" else "Rail_Steel")
    bx(0.05, 0.5, -0.06, 0.0, h - 0.09, h - 0.05, "Steel" if kind == "Leaf_Esc" else "Rail_Steel")
    bx(0.03, w - 0.03, -0.002, 0.0, 0.03, 0.25, "Steel" if kind == "Leaf_Esc" else "Rail_Steel")
    me = bpy.data.meshes.new(kind)
    mats = []
    out = bmesh.new()
    out.loops.layers.uv.new("UVMap")
    for mm, mat in pieces:
        if mat not in mats:
            mats.append(mat)
        for f in mm.faces:
            f.material_index = mats.index(mat)
        box_uv_local(mm, TILES.get(mat, 1.0))
        m2 = bpy.data.meshes.new("p")
        mm.to_mesh(m2)
        mm.free()
        out.from_mesh(m2)
        bpy.data.meshes.remove(m2)
    out.to_mesh(me)
    out.free()
    for mat in mats:
        me.materials.append(MATS[mat])
    LEAF_MESH[kind] = me
    return me


def build_leaves(M):
    kind = "Leaf_Esc" if SCENE == "escalators" else "Leaf_Stair"
    for d in M.doors:
        p = d["props"]
        ob = bpy.data.objects.new(d["name"], leaf_mesh(kind, p["width"], p["height"]))
        ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
        DOORS.objects.link(ob)
        for k, v in p.items():
            ob[k] = v


# ---------------------------------------------------------------- lights
def light(name, kind, pos, power, color=WARM, size=0.05, aim=None, spot=None, coll=None):
    d = bpy.data.lights.new(name, kind)
    d.energy, d.color = power, color
    if kind == "AREA":
        d.shape = "DISK"
        d.size = size
    else:
        d.shadow_soft_size = size
    if spot:
        d.spot_size, d.spot_blend = math.radians(spot), 0.6
    ob = bpy.data.objects.new(name, d)
    ob.location = B(pos)
    if aim is not None:
        ob.rotation_euler = (B(aim) - B(pos)).to_track_quat("-Z", "Y").to_euler()
    (coll or LIGHTS).objects.link(ob)
    return ob


# ---------------------------------------------------------------- shared fittings
def door_casing(w, a, half, top, tag, mat, width=0.06, proud=0.015, y0=0.0):
    part(f"Casing_{tag}_L", mat, lambda bm: w.box(bm, a - half - width, a - half, y0, y0 + top + width, 0.0, proud))
    part(f"Casing_{tag}_R", mat, lambda bm: w.box(bm, a + half, a + half + width, y0, y0 + top + width, 0.0, proud))
    part(f"Casing_{tag}_Head", mat, lambda bm: w.box(bm, a - half - width, a + half + width, y0 + top, y0 + top + width, 0.0, proud))


def exit_sign(w, a, y0, tag):
    """A wall-mounted EXIT sign: a white housing, a green face with the letters lit (Emergency_Emit), standing out of it."""
    part(f"Exit_{tag}_Housing", "Plastic_White", lambda bm: w.box(bm, a - 0.18, a + 0.18, y0, y0 + 0.2, 0.0, 0.05))
    part(f"Exit_{tag}_Face", "Sign_Green", lambda bm: w.box(bm, a - 0.165, a + 0.165, y0 + 0.015, y0 + 0.185, 0.05, 0.052))
    part(f"Exit_{tag}_Letters", "Emergency_Emit", lambda bm: wall_text(bm, w, "EXIT", a, y0 + 0.1, 0.052, 0.11, 0.004, 1.1))


def caged_lamp(w, a, y, tag, power=None, dead=False):
    """A bulkhead on a wall: a round steel back plate, an opal glass dome (Lamp_Emit), a wire cage over it (four hoops and a ring)."""
    part(f"Cage_{tag}_Base", "Rail_Steel" if SCENE == "other_stairs" else "Trim_Steel",
         lambda bm: cyl(bm, w.pt(a, y, 0.0), w.pt(a, y, 0.03), 0.11, seg=20))
    part(f"Cage_{tag}_Glass", "Lamp_Dead" if dead else "Lamp_Emit", lambda bm: cyl(bm, w.pt(a, y, 0.03), w.pt(a, y, 0.12), 0.075, 0.055, seg=20))

    def cage(bm):
        n, R, U = w.normal(), w.right(), (0, 1, 0)
        c0 = w.pt(a, y, 0.03)
        tube(bm, w.pt(a, y, 0.128), w.pt(a, y, 0.136), 0.05, seg=16)
        for k in range(4):
            ang = k * math.pi / 4
            dv = [R[i] * math.cos(ang) + U[i] * math.sin(ang) for i in range(3)]
            for sgn in (1, -1):
                pb = [c0[i] + sgn * dv[i] * 0.1 for i in range(3)]
                pm = [c0[i] + sgn * dv[i] * 0.09 + n[i] * 0.075 for i in range(3)]
                pt = [c0[i] + sgn * dv[i] * 0.05 + n[i] * 0.132 for i in range(3)]
                cyl(bm, pb, pm, 0.0035, seg=6)
                cyl(bm, pm, pt, 0.0035, seg=6)
    part(f"Cage_{tag}_Wire", "Iron_Black", cage)
    if not dead:
        light(f"L_cage_{tag}", "POINT", w.pt(a, y - 0.02, 0.2), power or CAGE_W, size=0.04)


def decal(name, mat, x, z, sx, sz, y, down=False, rot=0.0, uv=(0, 0, 1, 1)):
    """An alpha decal quad on the floor or the ceiling, `sx` by `sz`, turned `rot` about y."""
    c, sn = math.cos(rot), math.sin(rot)
    pts, uvs = [], []
    u0, v0, u1, v1 = uv
    for u, v in ((0, 0), (1, 0), (1, 1), (0, 1)):
        dx, dz = (u - 0.5) * sx, (v - 0.5) * sz
        pts.append((x + dx * c - dz * sn, y, z + dx * sn + dz * c))
        uvs.append((u0 + (u1 - u0) * u, v0 + (v1 - v0) * v))
    return quad(name, mat, pts, uvs, normal=(0, -1 if down else 1, 0))


def wall_decal(name, mat, w, a, y, wd, ht, d=0.002, uv=(0, 0, 1, 1), rot=0.0, coll=None):
    """An alpha decal (or a paper) flat on a wall: centred at (a, y), `wd` by `ht`, `d` in front of it, turned `rot` (radians) in its plane."""
    R = w.right()
    sign = 1 if (R[0] if w.axis == "z" else R[2]) > 0 else -1
    c, s = math.cos(rot), math.sin(rot)
    u0, v0, u1, v1 = uv
    pts, uvs = [], []
    for u, v in ((0, 0), (1, 0), (1, 1), (0, 1)):
        du, dv = (u - 0.5) * wd, (v - 0.5) * ht
        aa = a + sign * (du * c - dv * s)
        yy = y + du * s + dv * c
        pts.append(w.pt(aa, yy, d))
        uvs.append((u0 + (u1 - u0) * u, v0 + (v1 - v0) * v))
    return quad(name, mat, pts, uvs, coll, normal=w.normal())


# ================================================================ the escalators
def esc_line(fl, s):
    """An escalator run's deck line (game y) at distance s along its travel: flat at the first step's tread before it, along the nosings, flat at
    the top landing after the last step."""
    y0 = fl[5]
    return y0 + GB.ESC_RISE + (GB.ESC_RISE / GB.ESC_TREAD) * min(max(s, 0.0), GB.ESC_TREAD * (GB.ESC_N - 1))


def esc_z(fl, s):
    return fl[3] + fl[4] * s


def esc_band(bm, fl, x0, x1, lo, hi, s0, s1):
    """A solid band of a balustrade across x [x0, x1], along s [s0, s1], between y = lo(s) and hi(s) (piecewise linear: cut at the line's knees)."""
    knots = sorted({s0, s1, *[k for k in (0.0, GB.ESC_TREAD * (GB.ESC_N - 1)) if s0 < k < s1]})
    for a, b in zip(knots, knots[1:]):
        za, zb = esc_z(fl, a), esc_z(fl, b)
        ring_a = [(x0, lo(a), za), (x0, hi(a), za), (x0, hi(b), zb), (x0, lo(b), zb)]
        ring_b = [(x1, lo(a), za), (x1, hi(a), za), (x1, hi(b), zb), (x1, lo(b), zb)]
        prism(bm, ring_a, ring_b)


def step_mesh():
    """THE escalator step, one mesh for all 48: in its own frame (Blender local: x across the lane, -y along the travel, z up), its front (the
    riser) at the origin's plane, 1.2 m wide, 0.3 m deep, 0.25 m high. A grooved tread with the yellow edges (its UVs span the tread texture
    once), a cleated riser, the dark frame under the tread."""
    if "Esc_Step" in bpy.data.meshes:
        return bpy.data.meshes["Esc_Step"]
    W, D, Hh = 1.2, GB.ESC_TREAD, GB.ESC_RISE
    pieces = []

    def bx(x0, x1, s0, s1, z0, z1, mat, uvmode=None):
        mm = bmesh.new()
        uvl = mm.loops.layers.uv.new("UVMap")
        bmesh.ops.create_cube(mm, size=1.0, matrix=Matrix.Translation(((x0 + x1) / 2, -(s0 + s1) / 2, (z0 + z1) / 2)) @ Matrix.Diagonal((x1 - x0, s1 - s0, z1 - z0, 1)))
        for f in mm.faces:
            n = f.normal
            ax = max(range(3), key=lambda i: abs(n[i]))
            for lp in f.loops:
                p = lp.vert.co
                if uvmode == "tread" and ax == 2:
                    lp[uvl].uv = ((p.x + W / 2) / W, (-p.y) / D)
                elif uvmode == "riser" and ax == 1:
                    lp[uvl].uv = ((p.x + W / 2) / W, p.z / Hh)
                else:
                    u, v = (p.y, p.z) if ax == 0 else (p.x, p.z) if ax == 1 else (p.x, p.y)
                    lp[uvl].uv = (u / 0.3, v / 0.3)
        pieces.append((mm, mat))
    bx(-W / 2, W / 2, 0.0, D, Hh - 0.03, Hh, "Esc_Tread", "tread")
    bx(-W / 2, W / 2, 0.0, 0.012, 0.0, Hh - 0.03, "Esc_Riser", "riser")
    me = bpy.data.meshes.new("Esc_Step")
    mats, out = [], bmesh.new()
    out.loops.layers.uv.new("UVMap")
    for mm, mat in pieces:
        if mat not in mats:
            mats.append(mat)
        for f in mm.faces:
            f.material_index = mats.index(mat)
        m2 = bpy.data.meshes.new("p")
        mm.to_mesh(m2)
        mm.free()
        out.from_mesh(m2)
        bpy.data.meshes.remove(m2)
    out.to_mesh(me)
    out.free()
    for mat in mats:
        me.materials.append(MATS[mat])
    return me


DEAD_BAL = {("esc_0_4", "E", 3), ("esc_4_8", "W", 1), ("esc_4_8", "W", 2), ("esc_8_12", "E", 4)}


def build_escalators(M):
    me = step_mesh()
    for fl in GB.ESC_RUNS:
        name, l0, l1, z0, d, y0 = fl
        xc = (l0 + l1) / 2
        for i in range(GB.ESC_N):
            ob = bpy.data.objects.new(f"Esc_Step_{name}_{i:02d}", me)                     # a linked copy of the one step mesh
            zf = z0 + d * GB.ESC_TREAD * i
            ob.matrix_world = Matrix.Translation(B((xc, y0 + GB.ESC_RISE * i, zf))) @ Matrix.Rotation(0.0 if d > 0 else math.pi, 4, "Z")
            PROPS.objects.link(ob)
        L = lambda s, fl=fl: esc_line(fl, s)
        S_END = GB.ESC_TREAD * GB.ESC_N
        N0, N1 = -GB.ESC_NEWEL, S_END + GB.ESC_NEWEL
        ground = y0 == 0.0
        for side, inner, sg in (("W", l0, -1), ("E", l1, 1)):
            outer = inner + sg * GB.ESC_BAL
            xs = lambda a, b, inner=inner, sg=sg: tuple(sorted((inner + sg * a, inner + sg * b)))
            top = lambda s: L(s) + GB.ESC_BAL_H
            y_top = y0 + GB.ESC_RISE * GB.ESC_N

            def three(bm, xa, xb, lo_run, hi, lo_bot=None, lo_top=None):
                """The band over the bottom newel, the run, the top newel: each end stands on its own floor."""
                esc_band(bm, fl, xa, xb, lo_bot or lo_run, hi, N0, 0.0)
                esc_band(bm, fl, xa, xb, lo_run, hi, 0.0, S_END)
                esc_band(bm, fl, xa, xb, lo_top or lo_run, hi, S_END, N1)
            floor_b, floor_t = (lambda s: y0), (lambda s: y_top)
            # the inner skirt beside the steps, brushed steel
            xa, xb = xs(0.0, 0.015)
            part(f"Esc_{name}_{side}_Skirt", "Esc_Skirt", lambda bm: three(bm, xa, xb, lambda s: L(s) - 0.38, lambda s: L(s) + 0.1, floor_b, floor_t))
            # the ivory balustrade panel above it ("the side panels"), and the handrail, black, on top
            xa, xb = xs(0.015, 0.105)
            part(f"Esc_{name}_{side}_Panel", "Esc_Panel", lambda bm: three(bm, xa, xb, lambda s: L(s) + 0.1, lambda s: top(s) - 0.06))
            xa, xb = xs(0.01, 0.11)
            part(f"Esc_{name}_{side}_Handrail", "Esc_Handrail", lambda bm: three(bm, xa, xb, lambda s: top(s) - 0.06, top))
            # the outer cladding, champagne, down to the floor (the ground run) or the truss's underside (the upper runs)
            xa, xb = xs(0.105, GB.ESC_BAL)
            run_lo = floor_b if ground else (lambda s: L(s) - GB.ESC_TRUSS)
            part(f"Esc_{name}_{side}_Clad", "Esc_Clad", lambda bm: three(bm, xa, xb, run_lo, lambda s: top(s) - 0.06, floor_b, floor_t))
            # the newel ends: the balustrade's end faces, capped with the handrail turning down (a black block)
            for tag, s_end, ds in (("bottom", N0, 1), ("top", N1, -1)):
                part(f"Esc_{name}_{side}_{tag}_Cap", "Esc_Handrail", lambda bm, s_end=s_end, ds=ds: esc_band(
                    bm, fl, *xs(0.01, 0.11), lambda s: L(s) + 0.3, top, min(s_end, s_end + ds * 0.06), max(s_end, s_end + ds * 0.06)))
            # the side lamps: round lenses on the panel's inner face every 0.9 m, lighting the steps (a few dead)
            for k, s in enumerate([0.45 + 0.9 * j for j in range(6)]):
                dead = (name, side, k) in DEAD_BAL
                yy = L(s) + 0.3
                xf = inner + sg * 0.015
                part(f"Esc_{name}_{side}_Lamp_{k}", "Lamp_Dead" if dead else "Lamp_Emit",
                     lambda bm, yy=yy, s=s, xf=xf: cyl(bm, (xf, yy, esc_z(fl, s)), (xf - sg * 0.008, yy, esc_z(fl, s)), 0.03, seg=16))
                part(f"Esc_{name}_{side}_LampRim_{k}", "Esc_Skirt",
                     lambda bm, yy=yy, s=s, xf=xf: tube(bm, (xf, yy, esc_z(fl, s)), (xf - sg * 0.01, yy, esc_z(fl, s)), 0.036, seg=16))
                if not dead:
                    light(f"L_bal_{name}_{side}_{k}", "POINT", (xf - sg * 0.07, yy, esc_z(fl, s)), BAL_W, size=0.03)
        # under an upper run: the truss's underside and its two ends, clad
        if not ground:
            part(f"Esc_{name}_Truss", "Esc_Clad", lambda bm: (esc_band(bm, fl, l0, l1, lambda s: L(s) - GB.ESC_TRUSS, lambda s: L(s) - GB.ESC_TRUSS + 0.02, 0.0, S_END),
                                                              esc_band(bm, fl, l0, l1, lambda s: L(s) - GB.ESC_TRUSS, lambda s: L(s) - GB.ESC_RISE, 0.0, 0.01),
                                                              esc_band(bm, fl, l0, l1, lambda s: L(s) - GB.ESC_TRUSS, lambda s: L(s) - GB.ESC_RISE, S_END - 0.01, S_END)))
        else:                                  # the ground run's closed end under its top step, facing the space under landing 4
            part(f"Esc_{name}_End", "Esc_Clad", lambda bm: esc_band(bm, fl, l0, l1, lambda s: y0, lambda s: L(s) - GB.ESC_RISE, S_END - 0.01, S_END))
        # the floor plates and yellow comb plates at both ends, and the stop button on the west bottom newel
        for tag, sa, sb, yy, ca, cb in (("bottom", N0, 0.0, y0, -0.05, 0.0), ("top", S_END, N1, y0 + GB.ESC_RISE * GB.ESC_N, S_END, S_END + 0.05)):
            za, zb = sorted((esc_z(fl, sa), esc_z(fl, sb)))
            part(f"Esc_{name}_Plate_{tag}", "Esc_Plate", lambda bm, za=za, zb=zb, yy=yy: cube(bm, (l0, yy, za), (l1, yy + 0.008, zb)))
            qa, qb = sorted((esc_z(fl, ca), esc_z(fl, cb)))
            part(f"Esc_{name}_Comb_{tag}", "Comb_Yellow", lambda bm, qa=qa, qb=qb, yy=yy: cube(bm, (l0, yy + 0.008, qa), (l1, yy + 0.02, qb)))
        zs = esc_z(fl, N0 + 0.22)
        part(f"Esc_{name}_StopPlate", "Plastic_Black", lambda bm: cube(bm, (l0 - 0.015, y0 + 0.88, zs - 0.05), (l0 - 0.012, y0 + 1.0, zs + 0.05)))
        part(f"Esc_{name}_Stop", "Red_Paint", lambda bm: cyl(bm, (l0 - 0.012, y0 + 0.94, zs), (l0 - 0.002, y0 + 0.94, zs), 0.022, seg=14))
    # the landings' guards: black iron balusters, a brass handrail (the atrium's balustrade), a bottom rail
    for b in M.boxes:
        if not b["name"].startswith("Guard_"):
            continue
        x0, x1 = b["min"][0], b["max"][0]
        y, yt = b["min"][1], b["max"][1]
        za, zb = b["min"][2], b["max"][2]
        part(f"{b['name']}_Rail", "Brass", lambda bm: cube(bm, (x0, yt - 0.05, za), (x1, yt, zb)))
        part(f"{b['name']}_Bottom", "Iron_Black", lambda bm: cube(bm, (x0, y + 0.06, za + 0.01), (x1, y + 0.1, zb - 0.01)))

        def bal(bm, x0=x0, x1=x1, y=y, yt=yt, za=za, zb=zb):
            n = max(2, int(round((x1 - x0) / 0.12)) + 1)
            for k in range(n):
                x = x0 + 0.02 + (x1 - x0 - 0.04) * k / (n - 1)
                cube(bm, (x - 0.009, y + 0.1, za + 0.015), (x + 0.009, yt - 0.05, zb - 0.015))
            cube(bm, (x0, y, za), (x0 + 0.04, yt - 0.05, zb))
            cube(bm, (x1 - 0.04, y, za), (x1, yt - 0.05, zb))
        part(f"{b['name']}_Balusters", "Iron_Black", bal)
    # the landings' edges: a steel nosing on each slab's edge, the FLOOR name on its fascia, toward the hall
    for nm, y, ze, sgz, label in (("Landing_4", 4.0, -2.4, 1, "FLOOR 1"), ("Landing_8", 8.0, 2.4, -1, "FLOOR 2"), ("Landing_12", 12.0, -2.4, 1, "FLOOR 3")):
        w = Wall("z", ze, sgz)
        part(f"{nm}_Nosing", "Trim_Steel", lambda bm, w=w, y=y: w.box(bm, -3.0, 3.0, y - 0.03, y + 0.004, 0.0, 0.012))
        lx = {4.0: 1.6, 8.0: -1.9, 12.0: -1.0}[y]
        part(f"{nm}_Label", "Brass", lambda bm, w=w, y=y, label=label, lx=lx: wall_text(bm, w, label, lx, y - 0.16, 0.0, 0.12, 0.006, 1.15))
    hall_walls_escalators(M)


def hall_walls_escalators(M):
    """The hall's walls: a steel band at every landing level, the doors' casings, signs, exit signs, the bulkheads over the doors, the wall
    uplights, a stain or two, a level sign beside every door."""
    X, Z = 3.0, 4.4
    walls = {"W": Wall("x", -X, 1), "E": Wall("x", X, -1), "N": Wall("z", -Z, 1), "S": Wall("z", Z, -1)}
    names = {0.0: "SUB FLOOR", 4.0: "FLOOR 1", 8.0: "FLOOR 2", 12.0: "FLOOR 3"}
    for y in (4.0, 8.0, 12.0):
        for k, w in walls.items():
            ext = Z if k in ("W", "E") else X
            part(f"Band_{k}_{int(y)}", "Trim_Steel", lambda bm, w=w, ext=ext, y=y: w.box(bm, -ext, ext, y - 0.34, y - 0.3, 0.0, 0.01))
    for k, w in (("W", walls["W"]), ("E", walls["E"]), ("N", walls["N"]), ("S", walls["S"])):
        ext = Z if k in ("W", "E") else X
        part(f"Skirting_{k}", "Plastic_Black", lambda bm, w=w, ext=ext: w.box(bm, -ext, ext, 0.0, 0.08, 0.0, 0.01))
    for name, y, side in SK.doors(M):
        w = walls[side]
        door_casing(w, 0.0, GB.DOOR_W / 2, GB.DOOR_H, name, "Trim_Steel", y0=y)
        exit_sign(w, 0.0, y + 2.27, name)
        # the level's name on a plate beside the door, and an ESCALATORS UP/DOWN plate
        part(f"Plate_{name}", "Fascia_Paint", lambda bm, w=w, y=y: w.box(bm, 0.75, 1.75, y + 1.42, y + 1.72, 0.0, 0.012))
        part(f"Plate_{name}_t", "Brass", lambda bm, w=w, y=y: wall_text(bm, w, names[y], 1.25, y + 1.57, 0.012, 0.13, 0.003, 1.1))
        # a caged bulkhead over the door's sign on either side
        caged_lamp(w, -0.95, y + 2.5, f"door_{name}", power=BULK_W, dead=(y == 12.0))
    # wall uplights: a half-drum on each side wall at every level, throwing light up the tall walls
    for y in (0.0, 4.0, 8.0, 12.0):
        for k in ("W", "E"):
            w = walls[k]
            for z in ((3.4,) if y in (0.0, 8.0) else (-3.4,)) + ((-3.4,) if y == 0.0 else ()):
                dead = (y, k, z) == (8.0, "E", 3.4)
                a = z
                part(f"Uplight_{k}_{int(y)}_{z:+.0f}", "Trim_Steel", lambda bm, w=w, a=a, y=y: w.box(bm, a - 0.16, a + 0.16, y + 2.0, y + 2.14, 0.0, 0.1))
                part(f"Uplight_{k}_{int(y)}_{z:+.0f}_Glow", "Lamp_Dead" if dead else "Lamp_Emit", lambda bm, w=w, a=a, y=y: w.box(bm, a - 0.15, a + 0.15, y + 2.14, y + 2.15, 0.01, 0.095))
                if not dead:
                    light(f"L_up_{k}_{int(y)}_{z:+.0f}", "POINT", w.pt(a, y + 2.3, 0.22), SCONCE_W * 0.7, size=0.08)
    # the ceiling: one hanging opal globe on a rod, high in the dark; one dead
    for x, z, dead in ((0.0, -1.2, False), (0.0, 2.0, True)):
        part(f"Pendant_{z:+.0f}_Rod", "Iron_Black", lambda bm, x=x, z=z: cyl(bm, (x, 14.2, z), (x, SK.HALL_H, z), 0.012, seg=8))
        part(f"Pendant_{z:+.0f}_Globe", "Lamp_Dead" if dead else "Lamp_Emit", lambda bm, x=x, z=z: sphere(bm, (x, 14.0, z), 0.22, seg=20))
        if not dead:
            light(f"L_pendant_{z:+.0f}", "POINT", (x, 14.0, z), 90.0, size=0.18)
    # a stain on the ground tile near the bottom of the first run, and a dark patch under landing 4
    decal("decor_stain_floor_0", "Decal_Floor", -0.6, 2.0, 0.9, 0.9, 0.003, rot=0.7)
    decal("decor_stain_floor_1", "Decal_Floor", 1.4, -3.5, 1.3, 1.3, 0.003, rot=2.1)


# ================================================================ the other staircase
def flight_steps(M, fl):
    return sorted((b for b in M.boxes if b["name"].startswith(f"Step_{fl}_")), key=lambda b: b["name"])


def build_other_stairs(M):
    X0, X1, Z0, Z1 = -2.6, 2.6, -3.0, 3.0
    WAIST = 0.19
    for k in range(3):
        for half in ("a", "b"):
            fl = f"st_{k}_{half}"
            steps = flight_steps(M, fl)
            d = -1 if half == "a" else 1
            lx0, lx1 = steps[0]["min"][0], steps[0]["max"][0]
            if fl == "st_0_a":                         # the ground flight is solid to the floor: one piece a step (its collider and its fill's)
                for i, s in enumerate(steps):
                    part(f"Flight_{fl}_{i:02d}", "Stair_Step", lambda bm, s=s: cube(bm, (lx0, 0.0, s["min"][2]), (lx1, s["max"][1], s["max"][2])), tile=1.5)
            else:                                     # a concrete flight: the steps' sawtooth on a sloped soffit WAIST below the inner corners
                def flight(bm, steps=steps, d=d):
                    for i, s in enumerate(steps):
                        zf = s["max"][2] if d < 0 else s["min"][2]        # the riser's plane (the step's front)
                        zr = s["min"][2] if d < 0 else s["max"][2]
                        yb, yt = s["min"][1], s["max"][1]
                        ring = [(zf, yb - WAIST), (zf, yt), (zr, yt), (zr, yt - WAIST)]
                        prism(bm, [(lx0, y, z) for z, y in ring], [(lx1, y, z) for z, y in ring])
                part(f"Flight_{fl}", "Stair_Step", flight, tile=1.5)
            # the yellow nosings (5 cm, on every step's front) and the handrails on both sides of the flight
            part(f"Nosing_{fl}", "Nosing_Yellow", lambda bm, steps=steps, d=d: [cube(bm, (lx0 + 0.03, s["max"][1], (s["max"][2] - 0.05) if d < 0 else s["min"][2]),
                                                                                     (lx1 - 0.03, s["max"][1] + 0.003, s["max"][2] if d < 0 else s["min"][2] + 0.05)) for s in steps])
            zs = [s["max"][2] if d < 0 else s["min"][2] for s in steps]
            ys = [s["max"][1] for s in steps]
            za, zb = zs[0] + d * 0.03, zs[-1] + d * 0.25
            ya, yb = ys[0] + 0.9, ys[-1] + 0.9 + 0.25 * (0.25 / 0.3) * 0
            slope = (ys[-1] - ys[0]) / (zs[-1] - zs[0])
            for side, xw, sg in (("wall", lx0 if half == "a" else lx1, 1 if half == "a" else -1), ("spine", lx1 if half == "a" else lx0, -1 if half == "a" else 1)):
                xr = xw + sg * 0.065

                def rail(bm, xw=xw, xr=xr, sg=sg):
                    pa = (xr, ys[0] + 0.9 + (za - zs[0]) * slope, za)
                    pb = (xr, ys[0] + 0.9 + (zb - zs[0]) * slope, zb)
                    cyl(bm, pa, pb, 0.021, seg=12)
                    for t in (0.12, 0.5, 0.88):
                        zz = za + (zb - za) * t
                        yy = ys[0] + 0.9 + (zz - zs[0]) * slope
                        cube(bm, (min(xw, xw + sg * 0.065), yy - 0.06, zz - 0.012), (max(xw, xw + sg * 0.065), yy - 0.02, zz + 0.012))
                        cyl(bm, (xw, yy - 0.04, zz), (xw + sg * 0.008, yy - 0.04, zz), 0.035, seg=12)
                part(f"Handrail_{fl}_{side}", "Rail_Steel", rail)
    # walls: the doors' casings, the exit signs, the level numbers, the caged lamps on the landings and half landings
    ws = Wall("z", Z1, -1)
    big = {0.0: "S", 4.0: "1", 8.0: "2", 12.0: "3"}
    small = {0.0: "SUB FLOOR", 4.0: "FLOOR 1", 8.0: "FLOOR 2", 12.0: "FLOOR 3"}
    for name, y, side in SK.doors(M):
        door_casing(ws, 0.0, GB.DOOR_W / 2, GB.DOOR_H, name, "Rail_Steel", y0=y)
        exit_sign(ws, 0.0, y + 2.27, name)
        part(f"Level_{name}", "Stencil_Paint", lambda bm, y=y: wall_text(bm, ws, big[y], 1.55, y + 1.45, 0.0, 0.85, 0.002, 1.0))
        part(f"Level_{name}_t", "Stencil_Paint", lambda bm, y=y: wall_text(bm, ws, small[y], 1.55, y + 0.85, 0.0, 0.14, 0.002, 1.12))
        part(f"Level_{name}_bar", "Stencil_Paint", lambda bm, y=y: ws.box(bm, 0.95, 2.15, y + 0.98, y + 1.0, 0.0, 0.002))
        caged_lamp(Wall("x", X1, -1), 2.2, y + 2.45, f"land_{int(y)}", dead=(y == 8.0))
        part(f"decor_hose_{int(y)}", "Red_Paint", lambda bm, y=y: (cyl(bm, (-2.35, y + 1.0, 2.9), (-2.35, y + 1.0, 3.0), 0.05, seg=14),
                                                             cyl(bm, (-2.35, y + 1.0, 2.9), (-2.35, y + 1.25, 2.9), 0.035, seg=12)))
    wn = Wall("z", Z0, 1)
    for k in range(3):
        y = 4.0 * k + 2.0
        caged_lamp(wn, 0.0, y + 2.35, f"half_{k}", dead=(k == 2))
        part(f"Half_{k}_t", "Stencil_Paint", lambda bm, y=y, k=k: wall_text(bm, wn, f"{k}  >  {k + 1}" if k else "S  >  1", 0.0, y + 1.5, 0.0, 0.16, 0.002, 1.1))
    # the fire main: a red standpipe in the south-west corner through every level (decor_: it is in the corner, out of the walker's reach)
    part("decor_standpipe", "Red_Paint", lambda bm: cyl(bm, (-2.5, 0.0, 2.9), (-2.5, SK.HALL_H, 2.9), 0.05, seg=14))
    for y in GB.LEVELS:
        part(f"decor_standpipe_valve_{int(y)}", "Brass", lambda bm, y=y: cyl(bm, (-2.5, y + 1.0, 2.9), (-2.35, y + 1.0, 2.9), 0.03, seg=10))
    # stains under the stairs and on a half landing
    decal("decor_stain_floor_0", "Decal_Floor", 1.4, -2.1, 1.1, 1.1, 0.003, rot=0.4)
    decal("decor_stain_floor_1", "Decal_Floor", -1.6, -2.0, 0.8, 0.8, 2.003, rot=1.7)


# ================================================================ the rooms
def room_common(lay):
    x0, x1, z0, z1 = SK.room_dims(lay)
    H = GB.ROOM_H
    Wn, Wsth, We, Ww = Wall("z", z0, 1), Wall("z", z1, -1), Wall("x", x1, -1), Wall("x", x0, 1)
    door_casing(Wsth, 0.0, GB.DOOR_W / 2, GB.DOOR_H, "door", "Wood_Laminate", width=0.07, proud=0.018)
    part("Switch", "Plastic_White", lambda bm: Wsth.box(bm, 0.6, 0.68, 1.15, 1.27, 0.0, 0.01))
    part("Smoke", "Plastic_White", lambda bm: cyl(bm, (x1 - 1.0, H - 0.035, z1 - 1.2), (x1 - 1.0, H, z1 - 1.2), 0.065, seg=20))
    part("Vent", "Grille", lambda bm: Wn.box(bm, x1 - 0.8, x1 - 0.4, H - 0.32, H - 0.12, 0.0, 0.01), tile=0.4)
    # the corridor outside the open door (bake stand-ins: floor 3's sconces 2 m either side of the door, on both walls, and the leaf open)
    for zw, sg in ((0.0, 1), (2 * GB.CORR_Z, -1)):
        w = Wall("z", zw, sg)
        for xx in (-2.0, 2.0):
            light(f"L_sb_sconce_{zw:.0f}_{xx:+.0f}", "POINT", w.pt(xx, 1.85, 0.15), CORR_SCONCE_W, size=0.03, coll=BAKE_STANDIN)
            part(f"standin_shade_{zw:.0f}_{xx:+.0f}", "Lamp_Emit", lambda bm, w=w, xx=xx: tube(bm, w.pt(xx, 1.85 - 0.085, 0.15), w.pt(xx, 1.85 + 0.085, 0.15), 0.1, 0.078),
                 BAKE_STANDIN, recalc=False)
    bm = bmesh.new()
    cube(bm, (0, 0, 0), (0.93, 2.15, 0.045))
    me = bpy.data.meshes.new("standin_leaf")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS["Door_Wood"])
    leaf = bpy.data.objects.new("standin_leaf", me)
    BAKE_STANDIN.objects.link(leaf)
    leaf.matrix_world = Matrix.Translation(B((-GB.DOOR_W / 2, 0.0, z1))) @ Matrix.Rotation(math.radians(95), 4, "Z")
    return x0, x1, z0, z1, H, Wn, Wsth, We, Ww


def skirting(runs, mat="Wood_Laminate"):
    for i, (w, a0, a1) in enumerate(runs):
        part(f"Skirting_{i}", mat, lambda bm, w=w, a0=a0, a1=a1: w.box(bm, a0, a1, 0.0, 0.09, 0.0, 0.012))


def window(w, a0, a1, lay):
    """A recessed window 12 cm deep, its glass black: it looks onto nothing."""
    y0, y1 = SK.WIN_Y0, SK.WIN_Y1

    def rec(bm):
        w.box(bm, a0, a0 + 0.01, y0, y1, -0.12, 0.0)
        w.box(bm, a1 - 0.01, a1, y0, y1, -0.12, 0.0)
        w.box(bm, a0, a1, y1 - 0.01, y1, -0.12, 0.0)
        w.box(bm, a0, a1, y0, y0 + 0.01, -0.12, 0.0)
    part("Win_Recess", "Window_Frame", rec)
    part("Win_Void", "Window_Void", lambda bm: w.box(bm, a0 + 0.01, a1 - 0.01, y0 + 0.01, y1 - 0.01, -0.12, -0.11))
    am = (a0 + a1) / 2
    part("Win_Mullion", "Window_Frame", lambda bm: (w.box(bm, am - 0.02, am + 0.02, y0, y1, -0.11, -0.07), w.box(bm, a0, a1, y0 + 0.42, y0 + 0.46, -0.11, -0.07)))
    part("Win_Sill", "Wood_Laminate", lambda bm: w.box(bm, a0 - 0.06, a1 + 0.06, y0 - 0.03, y0, 0.0, 0.045))


def curtains(w, a0, a1, open_):
    """Curtains on a rail over the window: drawn open (bunched at the sides) or nearly shut. decor_: they hang in front of the wall."""
    part("decor_curtain_rail", "Window_Frame", lambda bm: cyl(bm, w.pt(a0 - 0.45, 2.3, 0.09), w.pt(a1 + 0.45, 2.3, 0.09), 0.014, seg=10))
    am = (a0 + a1) / 2
    spans = ((a0 - 0.42, a0 - 0.02), (a1 + 0.02, a1 + 0.42)) if open_ else ((a0 - 0.28, am - 0.08), (am + 0.08, a1 + 0.28))
    for k, (c0, c1) in enumerate(spans):
        def cur(bm, c0=c0, c1=c1, k=k):
            n = 22
            rng = np.random.default_rng(41 + k)
            ph = rng.random() * 6
            freq = 13 if open_ else 9
            vt = [bm.verts.new(B(w.pt(c0 + (c1 - c0) * i / n, 2.27, 0.075 + 0.05 * math.sin(i / n * math.pi * freq + ph)))) for i in range(n + 1)]
            vb = [bm.verts.new(B(w.pt(c0 + (c1 - c0) * i / n, 0.5, 0.085 + 0.055 * math.sin(i / n * math.pi * freq + ph) + 0.01 * math.sin(i)))) for i in range(n + 1)]
            for i in range(n):
                bm.faces.new((vb[i], vb[i + 1], vt[i + 1], vt[i]))
        part(f"decor_curtain_{k}", "Curtain", cur, tile=0.5, recalc=False)


def paper_uv(k):
    r, c = divmod(k % 16, NOTE_CELLS[1])
    return (c / NOTE_CELLS[1], r / NOTE_CELLS[0], (c + 1) / NOTE_CELLS[1], (r + 1) / NOTE_CELLS[0])


def build_clue_room(M):
    lay = "clue_room"
    x0, x1, z0, z1, H, Wn, Wsth, We, Ww = room_common(lay)
    skirting([(Wsth, x0, -0.54), (Wsth, 0.54, x1), (We, z0, z1), (Wn, x0, x1), (Ww, z0, -4.0), (Ww, -2.4, z1)])
    # the ceiling dome, on (a dim fill), and the vent; the window over the desk with its blind down
    cx, cz = 0.0, -3.3
    part("Dome", "Lamp_Emit", lambda bm: cyl(bm, (cx, H - 0.09, cz), (cx, H, cz), 0.16, 0.19, seg=28))
    part("Dome_Rim", "Brass", lambda bm: cyl(bm, (cx, H - 0.012, cz), (cx, H, cz), 0.2, seg=28))
    light("L_dome", "POINT", (cx, H - 0.14, cz), DOME_W, size=0.12)
    side, a0, a1 = SK.window(lay)
    window(Ww, a0, a1, lay)
    part("decor_blind", "Blind", lambda bm: Ww.box(bm, a0 + 0.02, a1 - 0.02, SK.WIN_Y0 + 0.02, SK.WIN_Y1 - 0.04, -0.06, -0.055), tile=1.0)
    part("decor_blind_head", "Plastic_White", lambda bm: Ww.box(bm, a0 + 0.01, a1 - 0.01, SK.WIN_Y1 - 0.05, SK.WIN_Y1 - 0.01, -0.07, -0.04))
    # the desk against the west wall (its collider's box): a top, two pedestals of drawers, a chair pushed under it
    dx0, dx1, dz0, dz1 = -2.5, -1.3, -4.0, -2.4
    part("Desk_Top", "Wood_Dark", lambda bm: cube(bm, (dx0 + 0.01, 0.72, dz0 + 0.01), (dx1 - 0.01, 0.75, dz1 - 0.01)))
    for zz0, zz1 in ((dz0 + 0.02, dz0 + 0.42), (dz1 - 0.42, dz1 - 0.02)):
        part(f"Desk_Ped_{zz0:+.1f}", "Wood_Dark", lambda bm, zz0=zz0, zz1=zz1: cube(bm, (dx0 + 0.03, 0.0, zz0), (dx1 - 0.03, 0.72, zz1)))
        fw = Wall("x", dx1 - 0.03, 1)
        for k in range(3):
            y0 = 0.08 + k * 0.21
            part(f"Desk_Drawer_{zz0:+.1f}_{k}", "Wood_Dark", lambda bm, fw=fw, y0=y0, zz0=zz0, zz1=zz1: fw.box(bm, zz0 + 0.02, zz1 - 0.02, y0, y0 + 0.19, 0.0, 0.012))
            part(f"Desk_Pull_{zz0:+.1f}_{k}", "Brass", lambda bm, fw=fw, y0=y0, zz0=zz0, zz1=zz1: fw.box(bm, (zz0 + zz1) / 2 - 0.05, (zz0 + zz1) / 2 + 0.05, y0 + 0.09, y0 + 0.105, 0.012, 0.028))
    chair(-1.75, -3.2, face=(-1, 0), name="Desk_Chair", tucked=True)
    # the desk lamp: a green banker's shade on a brass stem (Lamp_Emit inside), lit
    lx, lz = -2.2, -3.65
    part("DeskLamp_Base", "Brass", lambda bm: cube(bm, (lx - 0.1, 0.75, lz - 0.07), (lx + 0.1, 0.77, lz + 0.07)))
    part("DeskLamp_Stem", "Brass", lambda bm: cyl(bm, (lx - 0.06, 0.77, lz), (lx - 0.06, 1.08, lz), 0.01, seg=8))
    part("DeskLamp_Shade", "Lamp_Green", lambda bm: cyl(bm, (lx + 0.06, 1.05, lz - 0.2), (lx + 0.06, 1.05, lz + 0.2), 0.09, 0.09, seg=20))
    part("DeskLamp_Glow", "Lamp_Emit", lambda bm: cube(bm, (lx - 0.02, 0.985, lz - 0.17), (lx + 0.14, 0.99, lz + 0.17)))
    light("L_desk", "POINT", (lx + 0.06, 0.95, lz), DESK_W, size=0.05)
    # the desk's papers: a spread of notes, an open folder, a mug, a pen
    rng = np.random.default_rng(71)
    for k in range(7):
        px, pz = dx0 + 0.3 + rng.random() * 0.55, dz0 + 0.25 + rng.random() * 1.1
        rot = (rng.random() - 0.5) * 1.2
        decal(f"Desk_Paper_{k}", "Paper", px, pz, 0.21, 0.27, 0.751 + 0.001 * k, rot=rot, uv=paper_uv(k * 3 + 1))
    part("Desk_Folder", "Folder_Buff", lambda bm: cube(bm, (-1.95, 0.75, -3.05), (-1.55, 0.765, -2.7)))
    part("Desk_Mug", "Mug", lambda bm: cyl(bm, (-1.5, 0.75, -2.62), (-1.5, 0.85, -2.62), 0.04, seg=14))
    part("Desk_Pen", "Plastic_Black", lambda bm: cyl(bm, (-1.8, 0.755, -3.3), (-1.66, 0.755, -3.22), 0.005, seg=6))
    # the table in the middle: a hotel plan spread, stacks of paper, a box file, a magnifier
    tx0, tx1, tz0, tz1 = -0.6, 0.6, -3.8, -2.8
    part("Table_Top", "Wood_Laminate", lambda bm: cube(bm, (tx0, 0.72, tz0), (tx1, 0.75, tz1)))
    for lx2, lz2 in ((tx0 + 0.05, tz0 + 0.05), (tx1 - 0.05, tz0 + 0.05), (tx0 + 0.05, tz1 - 0.05), (tx1 - 0.05, tz1 - 0.05)):
        part(f"Table_Leg_{lx2:+.1f}_{lz2:+.1f}", "Wood_Laminate", lambda bm, a=lx2, b=lz2: cube(bm, (a - 0.025, 0.0, b - 0.025), (a + 0.025, 0.72, b + 0.025)))
    decal("Table_Plan", "Paper", -0.12, -3.3, 0.62, 0.78, 0.751, rot=0.12, uv=paper_uv(2))
    for k, (px, pz) in enumerate(((0.35, -3.55), (0.38, -3.0), (-0.4, -2.98))):
        h = 0.03 + 0.03 * k
        part(f"Table_Stack_{k}", "Plastic_White", lambda bm, px=px, pz=pz, h=h: cube(bm, (px - 0.105, 0.75, pz - 0.135), (px + 0.105, 0.75 + h, pz + 0.135)))
        decal(f"Table_StackTop_{k}", "Paper", px, pz, 0.21, 0.27, 0.751 + h, rot=0.05 * k, uv=paper_uv(8 + k))
    part("Table_Lens", "Brass", lambda bm: tube(bm, (0.05, 0.752, -3.05), (0.05, 0.762, -3.05), 0.045, seg=18))
    part("Table_LensHandle", "Plastic_Black", lambda bm: cyl(bm, (0.09, 0.757, -3.0), (0.19, 0.757, -2.9), 0.008, seg=8))
    # the pinboard on the north wall (its collider): a cork board in a wood frame, papers pinned on it, red string between the pins
    px0, px1, py0, py1 = -1.5, 1.5, 1.0, 2.2
    part("Pinboard_Frame", "Wood_Dark", lambda bm: (Wn.box(bm, px0, px1, py0, py0 + 0.04, 0.0, 0.05), Wn.box(bm, px0, px1, py1 - 0.04, py1, 0.0, 0.05),
                                                    Wn.box(bm, px0, px0 + 0.04, py0, py1, 0.0, 0.05), Wn.box(bm, px1 - 0.04, px1, py0, py1, 0.0, 0.05)))
    part("Pinboard_Back", "Wood_Dark", lambda bm: Wn.box(bm, px0 + 0.04, px1 - 0.04, py0 + 0.04, py1 - 0.04, 0.0, 0.02))
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    vs = [bm.verts.new(B(Wn.pt(a, y, 0.03))) for a, y in ((px0 + 0.04, py0 + 0.04), (px1 - 0.04, py0 + 0.04), (px1 - 0.04, py1 - 0.04), (px0 + 0.04, py1 - 0.04))]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.dot(B(Wn.normal())) < 0:
        f.normal_flip()
    for lp in f.loops:
        g = (lp.vert.co.x, lp.vert.co.z)
        lp[uvl].uv = ((g[0] - px0) / (px1 - px0), (g[1] - py0) / (py1 - py0))
    finish("Pinboard_Cork", bm, "Cork", PROPS, keep_uv=True)
    rng = np.random.default_rng(72)
    pins = []
    spots = [(-1.18, 1.86), (-0.62, 1.95), (-0.05, 1.88), (0.52, 1.97), (1.12, 1.84), (-1.05, 1.38), (-0.4, 1.32), (0.2, 1.45), (0.78, 1.35), (1.2, 1.28),
             (-0.75, 1.62), (0.55, 1.62)]
    for k, (a, y) in enumerate(spots):
        wd, ht = (0.21, 0.27) if k % 3 else (0.26, 0.2)
        rot = (rng.random() - 0.5) * 0.25
        wall_decal(f"decor_pin_paper_{k}", "Paper", Wn, a, y, wd, ht, d=0.031 + 0.0005 * k, uv=paper_uv(k), rot=rot)
        pins.append((a, y + ht / 2 - 0.03))
    part("decor_pin_heads", "Pin_Heads", lambda bm: [sphere(bm, Wn.pt(a, y, 0.04), 0.009, seg=8) for a, y in pins])
    links = [(0, 2), (2, 7), (7, 11), (11, 4), (1, 10), (10, 5), (10, 6), (6, 7), (3, 11), (8, 11), (9, 4), (2, 10)]

    def strings(bm):
        for i, j in links:
            (a, y), (b, yb) = pins[i], pins[j]
            cyl(bm, Wn.pt(a, y, 0.044), Wn.pt(b, yb, 0.044), 0.0025, seg=6)
    part("decor_strings", "String_Red", strings)
    # notes taped on the east wall at the other two clue spots, a line of string between them; papers on the floor
    for k, (a, y) in enumerate(((-1.35, 1.55), (-1.05, 1.42), (-1.2, 1.18), (-4.6, 1.6), (-4.3, 1.4), (-4.55, 1.2))):
        wall_decal(f"decor_east_paper_{k}", "Paper", We, a, y, 0.18, 0.23, d=0.003 + 0.0005 * k, uv=paper_uv(k + 4), rot=(k - 2.5) * 0.08)
    part("decor_east_string", "String_Red", lambda bm: cyl(bm, We.pt(-1.2, 1.55, 0.006), We.pt(-4.45, 1.5, 0.006), 0.0025, seg=6))
    for k, (px, pz, rot) in enumerate(((-0.9, -4.9, 0.6), (-0.3, -5.1, -0.3), (0.8, -4.6, 1.2), (-1.0, -2.0, 0.2), (1.4, -2.3, -0.8), (0.3, -1.5, 0.5))):
        decal(f"decor_floor_paper_{k}", "Paper", px, pz, 0.21, 0.27, 0.004 + 0.0005 * k, rot=rot, uv=paper_uv(k + 9))


def chair(cx, cz, face, name, tucked=False):
    """A plain wooden chair 0.45 m square on its footprint: four legs, a seat, a back on the side away from `face`."""
    hx = 0.22
    fx, fz = face
    part(f"{name}_Seat", "Wood_Laminate", lambda bm: cube(bm, (cx - hx, 0.43, cz - hx), (cx + hx, 0.46, cz + hx)))
    legs = [(cx - hx + 0.03, cz - hx + 0.03), (cx + hx - 0.03, cz - hx + 0.03), (cx - hx + 0.03, cz + hx - 0.03), (cx + hx - 0.03, cz + hx - 0.03)]
    part(f"{name}_Legs", "Wood_Laminate", lambda bm: [cube(bm, (a - 0.018, 0.0, b - 0.018), (a + 0.018, 0.43, b + 0.018)) for a, b in legs])
    bx, bz = cx - fx * (hx - 0.02), cz - fz * (hx - 0.02)
    if fx:
        part(f"{name}_Back", "Wood_Laminate", lambda bm: (cube(bm, (bx - 0.015, 0.46, cz - hx + 0.02), (bx + 0.015, 0.9, cz - hx + 0.05)),
                                                          cube(bm, (bx - 0.015, 0.46, cz + hx - 0.05), (bx + 0.015, 0.9, cz + hx - 0.02)),
                                                          cube(bm, (bx - 0.012, 0.7, cz - hx + 0.02), (bx + 0.012, 0.88, cz + hx - 0.02))))
    else:
        part(f"{name}_Back", "Wood_Laminate", lambda bm: (cube(bm, (cx - hx + 0.02, 0.46, bz - 0.015), (cx - hx + 0.05, 0.9, bz + 0.015)),
                                                          cube(bm, (cx + hx - 0.05, 0.46, bz - 0.015), (cx + hx - 0.02, 0.9, bz + 0.015)),
                                                          cube(bm, (cx - hx + 0.02, 0.7, bz - 0.012), (cx + hx - 0.02, 0.88, bz + 0.012))))


def build_empty_room(M):
    lay = "empty_room"
    x0, x1, z0, z1, H, Wn, Wsth, We, Ww = room_common(lay)
    # the skirting is gone along the north wall where the bed stood, and the carpet's tack strips are left round the edges
    skirting([(Wsth, x0, -0.54), (Wsth, 0.54, x1), (We, z0, z1), (Wn, x0, -1.2), (Wn, 0.8, x1), (Ww, z0, -6.4), (Ww, -4.8, z1)])
    for k, (w, a0, a1) in enumerate(((Wn, x0, x1), (We, z0, z1), (Ww, z0, z1), (Wsth, x0, -0.6), (Wsth, 0.6, x1))):
        part(f"decor_tack_{k}", "Tack_Strip", lambda bm, w=w, a0=a0, a1=a1: w.box(bm, a0 + 0.02, a1 - 0.02, 0.0, 0.008, 0.02, 0.045))
    # the window on the west wall, the curtains open on black
    side, a0, a1 = SK.window(lay)
    window(Ww, a0, a1, lay)
    curtains(Ww, a0, a1, open_=True)
    # the single bare bulb on its cord from a ceiling rose in the middle
    cx, cz = 0.0, -4.2
    part("Rose", "Plastic_White", lambda bm: cyl(bm, (cx, H - 0.03, cz), (cx, H, cz), 0.06, seg=18))
    part("Cord", "Cord", lambda bm: cyl(bm, (cx, 2.24, cz), (cx, H - 0.03, cz), 0.004, seg=6))
    part("Bulb_Holder", "Plastic_Black", lambda bm: cyl(bm, (cx, 2.16, cz), (cx, 2.24, cz), 0.018, seg=12))
    part("Bulb", "Lamp_Emit", lambda bm: sphere(bm, (cx, 2.12, cz), 0.032, seg=16))
    light("L_bulb", "POINT", (cx, 2.07, cz), BULB_W, size=0.02)
    # where the bed stood: the stain on the floor, the paler ghost of the headboard on the wall, the pictures' ghosts
    decal("decor_bed_stain", "Decal_Bed", -0.2, -7.12, 1.8, 2.1, 0.003, rot=0.0)
    wall_decal("decor_ghost_head", "Decal_Ghost", Wn, -0.2, 0.75, 1.8, 0.9, d=0.002)
    wall_decal("decor_ghost_pic_0", "Decal_Ghost", We, -5.0, 1.6, 0.85, 0.6, d=0.002)
    wall_decal("decor_ghost_pic_1", "Decal_Ghost", Wsth, -1.8, 1.55, 0.6, 0.8, d=0.002)
    decal("decor_ghost_dresser", "Decal_Ghost", 2.5, -2.4, 0.5, 1.2, 0.0035)
    # the chair the greybox left in the room, facing where the bed was
    chair(2.05, -5.75, face=(-1, 0), name="Chair")
    # a dead outlet plate and the light switch's cover off: small things that make it a real room
    part("Outlet", "Plastic_White", lambda bm: We.box(bm, -3.05, -2.97, 0.3, 0.42, 0.0, 0.008))


# ---------------------------------------------------------------- the file
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for d in (IMG, MATS, TILES, GEN, LEAF_MESH):
        d.clear()


def build_all():
    global ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, STANDIN, BAKE_STANDIN, LIGHTS
    reset()
    sc = bpy.context.scene
    ART = bpy.data.collections.new("Art")
    sc.collection.children.link(ART)
    PROPS, ARCH = bpy.data.collections.new("Props"), bpy.data.collections.new("Arch")
    ART.children.link(PROPS)
    ART.children.link(ARCH)
    SKIN, DOORS, LAYOUT, STANDIN, BAKE_STANDIN, LIGHTS = (bpy.data.collections.new(n) for n in ("Skin", "Doors", "Layout", "Standins", "Bake_Standins", "Lights"))
    for c in (SKIN, DOORS, LAYOUT, STANDIN, BAKE_STANDIN, LIGHTS):
        sc.collection.children.link(c)
    make_materials()
    M = SK.model(SCENE)
    layout_from_model(M)
    build_skin()
    if SCENE == "escalators":
        build_leaves(M)
        build_escalators(M)
    elif SCENE == "other_stairs":
        build_leaves(M)
        build_other_stairs(M)
    elif SCENE == "clue_room":
        build_clue_room(M)
    else:
        build_empty_room(M)
    w = sc.world or bpy.data.worlds.new("Night")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.01, 0.012, 0.02, 1)
    bg.inputs["Strength"].default_value = 0.0
    ensure_marker()
    for ob in LAYOUT.objects:
        ob.hide_render = True
    split_for_check()
    print(f"ART {SCENE}: {len(PROPS.objects)} props, {len(ARCH.objects)} arch boxes, {len(SKIN.objects)} skin meshes, {len(DOORS.objects)} door nodes, "
          f"{len(LIGHTS.objects)} lights")


def arrival():
    M = SK.model(SCENE)
    mk = next(e for e in M.empties if e["name"].startswith("Marker_"))
    return list(mk["pos"])


def ensure_marker():
    ob = bpy.data.objects.get("standin_arrival_marker")
    if ob is None:
        me = bpy.data.meshes.new("standin_arrival_marker")
        bm = bmesh.new()
        a = arrival()
        cube(bm, (a[0] - 0.1, a[1], a[2] - 0.1), (a[0] + 0.1, a[1] + 0.2, a[2] + 0.1))
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("standin_arrival_marker", me)
        bpy.data.collections["Standins"].objects.link(ob)
    ob.hide_render = True
    return ob


def split_for_check():
    """check_layout.py works one box per object: an Art piece made of separate parts whose box would fail its STRAY or CLEAR rule is cut into its
    loose parts (`<name>`, `<name>_p1`, ...). Only Art is cut; Export is merged by material from Art, so the GLB is the same either way."""
    import check_layout as cl

    def bx(ob):
        g = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        return {"min": [min(p.x for p in g), min(p.z for p in g), min(-p.y for p in g)], "max": [max(p.x for p in g), max(p.z for p in g), max(-p.y for p in g)]}
    cols = [bx(o) for o in bpy.data.objects if o.name.startswith("COL_") and o.type == "MESH"]
    stand = [c for c in cols if cl._standing(c)]
    marks = [(o.matrix_world.translation.x, -o.matrix_world.translation.y) for o in bpy.data.objects if o.name.startswith("Marker_")]

    def fails(p):
        if not cl._stands(p):
            return False
        if any(cl._in_plan(p, x, z, cl.CLEAR_R) for x, z in marks):
            return True
        for x in cl._samples(p["min"][0], p["max"][0], cl.STEP / 2):
            for z in cl._samples(p["min"][2], p["max"][2], cl.STEP / 2):
                if not any(cl._in_plan(c, x, z, cl.TOL) for c in stand) and not any(
                        cl._in_plan(c, x, z, cl.TOL) and c["min"][1] - cl.TOL <= p["min"][1] < c["max"][1] - cl.TOL for c in cols):
                    return True
        return False
    done = []
    for ob in list(PROPS.objects):
        if ob.type != "MESH" or ob.name.startswith("decor_") or ob.data.users > 1 or not fails(bx(ob)):
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
            nob = bpy.data.objects.new(f"{name}_p{k}", me)
            nob.matrix_world = ob.matrix_world.copy()
            PROPS.objects.link(nob)
        done.append(f"{name} ({len(groups)})")
    print("SPLIT for the layout check:", done)


# ---------------------------------------------------------------- bake
NO_LIGHTMAP = {"Lamp_Emit", "Emergency_Emit", "Glass_Clear", "Bulb_Glass"}
NO_CULL = ("Win_", "Pinboard_", "decor_pin", "decor_strings", "decor_east", "Exit_", "Level_", "Plate_", "Half_")


def shell_mats():
    return {o.data.materials[0].name for o in bpy.data.collections["Skin"].objects}


def arch_cols():
    return [c for c in SK.colliders(SK.model(SCENE)) if not c["name"].startswith(SK.PROP_COLLIDERS)]


def cull_flush(bm, cols):
    """Drop the faces pressed against the shell (their front 3 mm is inside a wall, the floor or the ceiling): never seen."""
    bad = []
    for f in bm.faces:
        c, n = f.calc_center_median(), f.normal
        g = (c.x + n.x * 0.003, c.z + n.z * 0.003, -(c.y + n.y * 0.003))
        if any(all(o["min"][i] + 1e-4 < g[i] < o["max"][i] - 1e-4 for i in range(3)) for o in cols):
            bad.append(f)
    bmesh.ops.delete(bm, geom=bad, context="FACES")


def make_export_objects():
    """Export: the skin meshes as they are (one per material), and the props merged by material (faces against the shell dropped)."""
    if "Export" in bpy.data.collections:
        for o in list(bpy.data.collections["Export"].objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(bpy.data.collections["Export"])
    exp = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(exp)
    cols = arch_cols()
    out = {}
    for ob in bpy.data.collections["Skin"].objects:
        me = ob.data.copy()
        me.name = ob.name
        o2 = bpy.data.objects.new(ob.name, me)
        exp.objects.link(o2)
        out[ob.name] = o2
    by_mat = {}
    for ob in bpy.data.collections["Props"].objects:
        for idx, slot in enumerate(ob.material_slots):
            mname = slot.material.name
            tmp = bmesh.new()
            tmp.from_mesh(ob.data)
            tmp.transform(ob.matrix_world)
            bmesh.ops.delete(tmp, geom=[f for f in tmp.faces if f.material_index != idx], context="FACES")
            if not tmp.faces:
                tmp.free()
                continue
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


def lightmap_uv(objs, page=None, want=36.0):
    """One atlas for `objs`: smart-project islands at equal texel density, packed with MARGIN_PX on the fixed `page`. Returns (page, density)."""
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
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.average_islands_scale()
    chosen = (page, 0.0)
    for S in ((page,) if page else (512, 768, 1024, 1280, 1536, 1792, 2048)):
        if bpy.context.mode != "EDIT_MESH":
            bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / S, shape_method="CONCAVE")
        bpy.ops.object.mode_set(mode="OBJECT")
        a3 = sum(world_area(o) for o in objs)
        au = sum(uv_area(o, "lightmap") for o in objs)
        dens = S * math.sqrt(au / a3)
        print(f"  page {S}: {a3:.1f} m2, {dens:.1f} px/m")
        chosen = (S, dens)
        if dens >= want:
            break
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    return chosen


def rect_uv(objs, S):
    """The shell's lightmap UVs, packed by hand: every face of the skin is an axis-aligned rectangle (4 m at most), so each becomes its own
    pixel-aligned island with MARGIN_PX round it, shelf-packed at the highest density that fits the fixed page S. Deterministic."""
    m = MARGIN_PX
    rects = []
    for o in objs:
        uvs = o.data.uv_layers
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
        boxes = []
        for i, (o, p, v0, e1, e2, w, h) in enumerate(rects):
            pw, ph = max(1, math.ceil(w * D)), max(1, math.ceil(h * D))
            rot = ph > pw
            if rot:
                pw, ph = ph, pw
            boxes.append((ph + 2 * m, pw + 2 * m, i, rot))
        boxes.sort(key=lambda b: (-b[0], -b[1]))
        x = y = rowh = 0
        place = {}
        for bh, bw, i, rot in boxes:
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
    lo, hi = 2.0, 400.0
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
            if rot:
                u, t = b * pw, a * ph
            else:
                u, t = a * pw, b * ph
            uv[li].uv = ((x0 + u) / S, (y0 + t) / S)
    print(f"  rect pack: {len(rects)} faces at {D:.1f} px/m on {S}")
    return S, D


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


def leaf_reps():
    return [bpy.data.objects[name] for kind, name in BAKE_LEAF.get(SCENE, {}).items()]


def bake_visibility():
    for c, hide in (("Art", True), ("Skin", True), ("Standins", True), ("Bake_Standins", False), ("Doors", False), ("Export", False)):
        bpy.data.collections[c].hide_render = hide
    bpy.data.collections["Art"].hide_viewport = True
    bpy.data.collections["Skin"].hide_viewport = True


def shoulder(rgb):
    peak = rgb.max(axis=2)
    lit = peak[peak > 1e-5]
    if not len(lit):
        return rgb, 0.0
    k = float(np.percentile(lit, SHOULDER[0]))
    m = SHOULDER[1] * k
    f = np.where(peak <= k, peak, k + (peak - k) / (1 + (peak - k) / (m - k)))
    return rgb * (f / np.maximum(peak, 1e-8))[..., None], k


def stage_bake(size_only=False):
    import time
    exp = make_export_objects()
    bake_visibility()
    setup_cycles(SAMPLES, bake=True)
    sm = shell_mats()
    shell = [o for k, o in sorted(exp.items()) if k in sm]
    props = [o for k, o in sorted(exp.items()) if o not in shell and o.data.materials[0].name not in NO_LIGHTMAP] + leaf_reps()
    report = {}
    for n, objs in enumerate((shell, props)):
        t0 = time.time()
        print(f"lightmap {n}: {[o.name for o in objs]}")
        S, dens = rect_uv(objs, PAGES[SCENE][n]) if n == 0 else lightmap_uv(objs, None if size_only else PAGES[SCENE][n])
        if size_only:
            print(f"SIZE {SCENE} map {n}: page {S}, {dens:.1f} px/m")
            continue
        img = bpy.data.images.new(f"LM_{n}", S, S, alpha=False, float_buffer=True)
        img.colorspace_settings.name = "Non-Color"
        mats = sorted({s.material for o in objs for s in o.material_slots}, key=lambda m: m.name)
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
        rgb = denoise_image(img, S)[..., :3]
        rgb_s, knee = shoulder(rgb)
        peak = rgb_s.max(axis=2)
        pc = np.percentile(peak[peak > 1e-5], [50, 90, 99, 99.5, 100]) if (peak > 1e-5).any() else [1.0] * 5
        scale = float(min(pc[3], WHITE_CAP * pc[1]))
        out = np.ones((S, S, 4), np.float32)
        out[..., :3] = srgb_encode(rgb_s / scale)
        png = bpy.data.images.new(f"LM_{n}_png", S, S, alpha=False)
        png.colorspace_settings.name = "Non-Color"
        png.pixels.foreach_set(out.ravel())
        png.filepath_raw = str(work() / f"{SCENE}_{n}.png")
        png.file_format = "PNG"
        png.save()
        for m in mats:
            m["lightmap"] = lm_url(SCENE, n)
            m["lightmap_intensity"] = round(math.pi * scale, 4)
            for nd in [nd for nd in m.node_tree.nodes if nd.name.startswith("BAKE_TARGET")]:
                m.node_tree.nodes.remove(nd)
        raw = rgb.max(axis=2)
        report[n] = {"size": S, "px_per_m": round(dens, 1), "scale": round(scale, 4), "knee": round(knee, 4),
                     "raw_p50_p90_p99_p995_max": [round(float(v), 3) for v in np.percentile(raw[raw > 1e-5], [50, 90, 99, 99.5, 100])],
                     "p50_p90_p99_p995_max": [round(float(v), 3) for v in pc], "samples": SAMPLES, "device": bpy.context.scene.cycles.device,
                     "seconds": round(time.time() - t0), "materials": [m.name for m in mats]}
        print("  baked", report[n])
        bpy.data.images.remove(img)
        bpy.data.images.remove(png)
    if size_only:
        return
    (work() / f"{SCENE}_lightmaps.json").write_text(json.dumps(report, indent=1))
    stills_dir(SCENE).mkdir(parents=True, exist_ok=True)
    (stills_dir(SCENE) / "bake.json").write_text(json.dumps(report, indent=1))
    for c in ("Art", "Skin"):
        bpy.data.collections[c].hide_render = False
        bpy.data.collections[c].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


# ---------------------------------------------------------------- privacy
KEEP_PROPS = {"lightmap", "lightmap_intensity"}
LAYOUT_PREFIX = ("DoorLeaf_", "Marker_", "Spot_")


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private():
    kinds = ("scenes", "worlds", "objects", "meshes", "materials", "collections", "cameras", "lights", "images", "node_groups", "screens",
             "window_managers", "workspaces", "curves", "fonts")
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
    for scr in bpy.data.screens:
        for a in scr.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"_" * 1000
                    sp.params.directory = b"//"


def save_blend():
    p = blend_path(SCENE)
    p.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(p))
    scrub_private()
    bpy.ops.wm.save_mainfile()


def load_scene_file():
    bpy.ops.wm.open_mainfile(filepath=str(blend_path(SCENE)))
    global ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, STANDIN, BAKE_STANDIN, LIGHTS
    c = bpy.data.collections
    ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, STANDIN, BAKE_STANDIN, LIGHTS = (c.get(n) for n in ("Art", "Props", "Arch", "Skin", "Doors", "Layout", "Standins",
                                                                                         "Bake_Standins", "Lights"))
    for m in bpy.data.materials:
        MATS[m.name] = m


# ---------------------------------------------------------------- export
def caps():
    """Per-material factors on lightmap_intensity (docs/renders/<scene>/caps.json, from the display check of the uncapped GLB): the scene's one gain
    (its big shell surfaces up to p99 0.9), lowered for any material that would pass p99 0.97 or p90 0.88."""
    p = Path(arg("--caps")) / f"{SCENE}.json" if arg("--caps") else stills_dir(SCENE) / "caps.json"
    return json.loads(p.read_text()).get("factor", {}) if p.exists() else {}


def stage_export():
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    for c in ("Art", "Skin"):
        bpy.data.collections[c].hide_viewport = True
    leaves = list(bpy.data.collections["Doors"].objects)
    stash = {o.name: {k: o[k] for k in o.keys()} for o in leaves}
    for o in leaves:
        for k in list(o.keys()):
            del o[k]
    cp = caps()
    base = {}
    for m in bpy.data.materials:
        if "lightmap_intensity" in m:
            base[m.name] = m["lightmap_intensity"]
            if m.name in cp:
                m["lightmap_intensity"] = round(m["lightmap_intensity"] * cp[m.name], 4)
    bpy.ops.object.select_all(action="DESELECT")
    for o in list(exp.objects) + leaves:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = work() / f"{SCENE}_raw.glb"
    scrub_private()
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_animations=False)
    for o in leaves:
        for k, v in stash[o.name].items():
            o[k] = v
    for m in bpy.data.materials:
        if m.name in base:
            m["lightmap_intensity"] = base[m.name]
    print("EXPORTED", raw, raw.stat().st_size, "caps", cp)
    for c in ("Art", "Skin"):
        bpy.data.collections[c].hide_viewport = False
    exp.hide_viewport = exp.hide_render = True
    import export_scene
    export_scene.write(SCENE, world_json(SCENE))
    save_blend()


def stage_axes():
    import struct
    ob = ensure_marker()
    bpy.ops.object.select_all(action="DESELECT")
    ob.hide_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    path = work() / f"axes_{SCENE}.glb"
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_yup=True, export_apply=True, export_materials="NONE")
    b = path.read_bytes()
    j = json.loads(b[20:20 + struct.unpack("<I", b[12:16])[0]])
    acc = j["accessors"][j["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    off = j["nodes"][0].get("translation", [0, 0, 0])
    centre = [(acc["min"][i] + acc["max"][i]) / 2 + off[i] for i in range(3)]
    a = arrival()
    want = [a[0], a[1] + 0.1, a[2]]
    print(f"AXES glTF centre {tuple(round(v, 3) for v in centre)}, game point {tuple(want)}")
    assert all(abs(centre[i] - want[i]) < 1e-4 for i in range(3))
    print("AXES PASS: game (x, y, z) = Blender (x, -z, y) = glTF (x, y, z)")


def stage_check():
    import check_layout
    for o in bpy.data.collections["Arch"].objects:
        o.hide_render = False
    code = check_layout.main(["--scene", SCENE, "--collection", "Art"])
    print("CHECK_LAYOUT exit", code)


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
    cam.clip_start, cam.clip_end = 0.03, 200
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


def shots():
    if SCENE == "escalators":
        return {"1_arrival": ((0.0, E, 3.2), (-0.5, 2.4, -4.0), 75), "2_wide": ((2.6, 1.5, 4.1), (-1.4, 6.4, -1.8), 80),
                "3_detail": ((-2.1, 1.45, 4.15), (-2.2, 1.0, 1.3), 62)}
    if SCENE == "other_stairs":
        return {"1_arrival": ((0.0, E, 2.0), (-1.3, 1.6, -1.2), 75), "2_wide": ((2.25, 4.0 + 1.75, 2.75), (1.2, 2.3, -2.5), 80),
                "3_detail": ((0.2, 4.0 + 1.5, 2.2), (1.55, 4.0 + 1.35, 3.0), 62)}
    if SCENE == "clue_room":
        return {"1_arrival": ((0.0, E, -0.8), (0.0, E - 0.2, -6.2), 75), "2_wide": ((2.2, 2.35, -0.5), (-1.0, 0.7, -4.5), 75),
                "3_detail": ((-0.2, 1.55, -4.6), (0.0, 1.55, -6.2), 62)}
    return {"1_arrival": ((0.0, E, -0.8), (0.0, E - 0.35, -8.2), 75), "2_wide": ((2.7, 2.35, -0.5), (-1.2, 0.5, -6.2), 75),
            "3_detail": ((1.0, 1.4, -5.0), (-2.9, 1.3, -5.6), 62)}


def plan_box():
    cols = SK.colliders(SK.model(SCENE))
    x0, x1 = min(c["min"][0] for c in cols) - 0.4, max(c["max"][0] for c in cols) + 0.4
    z0, z1 = min(c["min"][2] for c in cols) - 0.4, max(c["max"][2] for c in cols) + 0.4
    return x0, x1, z0, z1


def stage_render():
    sc = bpy.context.scene
    d = stills_dir(SCENE)
    d.mkdir(parents=True, exist_ok=True)
    scrub_private()
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
    for c, hide in (("Art", False), ("Skin", False), ("Doors", False), ("Bake_Standins", False), ("Standins", True), ("Lights", False)):
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
    sc.view_settings.exposure = arg("--exposure", 0.0, float)
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    which = arg("--only", "all")
    for key, (loc, tgt, fov) in shots().items():
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
        span = max(x1 - x0, (z1 - z0) * 0.75)
        cam = look_cam("plan", ((x0 + x1) / 2, 40.0, (z0 + z1) / 2), None, ortho=max(x1 - x0, z1 - z0))
        cam.rotation_euler = (0, 0, 0)
        sc.camera = cam
        hidden = []
        cut = 2.3 if KIND == "room" else SK.HALL_H - 0.5
        for o in list(bpy.data.collections["Skin"].objects) + list(bpy.data.collections["Props"].objects) + list(bpy.data.collections["Bake_Standins"].objects) \
                + list(bpy.data.collections["Doors"].objects):
            if o.type != "MESH":
                continue
            if o.name.startswith(("Ceiling", "Stair_Ceiling", "Soffit", "Smoke", "Dome", "Rose", "Cord", "Bulb", "Pendant", "standin", "SB_")) or \
                    min((o.matrix_world @ v.co).z for v in o.data.vertices) > cut:
                if not o.hide_render:
                    o.hide_render = True
                    hidden.append(o)
        arch = bpy.data.collections["Arch"]
        arch.hide_render = False
        for o in arch.objects:
            o.hide_render = o.name.endswith(("_Ceiling",)) or o.name.startswith(("Room_Floor", "Escalators_Floor", "Stairs_Floor", "Desk", "Table", "Chair",
                                                                                 "Pinboard", "Step_", "Balustrade_", "Fill_", "Newel_", "Guard_", "Landing_",
                                                                                 "Half_Landing_")) or min((o.matrix_world @ v.co).z for v in o.data.vertices) > cut
        world = sc.world
        bg = world.node_tree.nodes["Background"]
        old = bg.inputs["Strength"].default_value
        bg.inputs["Color"].default_value = (1, 1, 1, 1)
        bg.inputs["Strength"].default_value = 0.6
        W = 1400
        H = max(200, int(round(W * (z1 - z0) / (x1 - x0)))) if (x1 - x0) >= (z1 - z0) else W
        Wd = W if (x1 - x0) >= (z1 - z0) else max(200, int(round(W * (x1 - x0) / (z1 - z0))))
        sc.render.resolution_x, sc.render.resolution_y = Wd, H
        sc.render.image_settings.file_format = "JPEG"
        path = d / "plan.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        strip_jpeg_comments(path)
        bg.inputs["Strength"].default_value = old
        bg.inputs["Color"].default_value = (0.01, 0.012, 0.02, 1)
        for o in hidden:
            o.hide_render = False
        for o in arch.objects:
            o.hide_render = False
        arch.hide_render = True
        (work() / f"{SCENE}_plan.json").write_text(json.dumps({"x0": x0, "x1": x1, "z0": z0, "z1": z1, "w": Wd, "h": H}))
        print("PLAN", path, Wd, H)


# ---------------------------------------------------------------- main
def main():
    global SCENE, KIND
    scenes = arg("--scenes", "escalators").split(",")
    for sc in scenes:
        SCENE = sc
        KIND = "room" if sc in SK.ROOMS else "hall"
        print(f"==== {sc} ({KIND}) stage {STAGE}")
        if STAGE in ("art", "all", "size"):
            build_all()
            save_blend()
        else:
            load_scene_file()
        if STAGE == "size":
            stage_bake(size_only=True)
        if STAGE in ("bake", "all"):
            stage_bake()
        if STAGE in ("export", "all", "reexport"):
            stage_export()
        if STAGE in ("axes", "all"):
            stage_axes()
        if STAGE in ("check", "all", "reexport", "art"):
            stage_check()
        if STAGE in ("render", "all"):
            stage_render()
            save_blend()
        print(f"==== {sc} done")


main()
