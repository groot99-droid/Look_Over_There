"""Dresses and lights the hotel's floor 2, green carpet (docs/BLENDER_AREAS.md, section 1, step 2): the two corridor scenes `floor_2_lower` and
`floor_2_upper`, the three key rooms off them (`dining`, `reception`, `key_room`) and the room layout `green_room` that loads behind their twenty
doors (docs/renders/floor_2_lower/README.md).

    blender -b --factory-startup --python tools/blender/build_hotel_floor2.py -- --scenes floor_2_lower,... --stage all
    blender -b --factory-startup blender/scenes/<scene>.blend --python tools/blender/build_hotel_floor2.py -- --scenes <scene> --stage bake|export|axes|check|render
    python tools/blender/build_hotel_floor2.py --pack <scene> [--work <dir>]           (no Blender: WebP lightmaps and textures -> world/)

Floor 1's method and code (tools/blender/build_hotel_floor1.py, on its branch), made for floor 2. Stages: art (the layout objects from the greybox,
the connector kit's pieces, the art, the lights; saves blender/scenes/<scene>.blend) -> bake (the seen faces and the merged props on fixed lightmap
PAGES, Cycles, OIDN, a highlight shoulder, 8-bit PNGs in the work folder) -> export (the GLB to the work folder; the layout through
tools/blender/export_scene.py) -> axes (the marker-cube check) -> check (tools/blender/check_layout.py) -> render (docs/renders/<scene>/1_arrival,
2_wide, 3_detail.jpg and plan.jpg). `all` runs them in that order.

The layout is the greybox's (tools/blender/build_hotel_greybox.py), which holds the connector kit's records as tools/blender/kit_place.py places
them (blender/kit/README.md; build_hotel_greybox.kit_floor2): on floor_2_lower the elevator at (-20, 0, 0), yaw 90 (its car and doors are the
kit's own GLB, drawn by the page), and the kit's stair door at every stair door, yaw -90, without its landing (the corridor is the landing) or its
hallway (the page draws the passage behind a link door). kit_place brings the kit's art: the elevator as a stand-in, the stair door's leaf. What is seen of the shell is tools/blender/hotel_floor2_skin.py's skin: only the faces that look into the air.

The door leaves are reused meshes: the twenty room doors and the doors to the key rooms are one panelled mesh (`Leaf_Room`), the closets another,
the stairwell's top door a third; each leaf is its own node with its origin at the hinge, so the page swings it by name, and the brass numbers
201 to 220 are small child nodes of their leaf. One leaf of each kind is baked (`BAKE_LEAF`); the others show the same lightmap, which fits
because every door has a sconce 2 m to either side.

Light: everything is baked at night. The corridors by their brass sconces (Lamp_Emit) and the exit signs (Emergency_Emit); the key rooms by their
own lamps; the green room with its lamps on and its door open onto a stand-in of the corridor, so it fits whichever door it sits behind.
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import hotel_floor2_skin as SK  # noqa: E402
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
KIND = None           # "corridor" | "keyroom" | "room"

# fixed lightmap pages per scene: [shell, props]
PAGES = {"floor_2_lower": [2048, 2048], "floor_2_upper": [2048, 2048], "dining": [2048, 2048], "reception": [2048, 2048], "key_room": [2048, 2048],
         "green_room": [1024, 1024]}
BAKE_LEAF = {"floor_2_lower": {"Leaf_Room": "DoorLeaf_room_203", "Leaf_Closet": "DoorLeaf_closet_4", "Leaf_Kit": "DoorLeaf_stairwell"},
             "floor_2_upper": {"Leaf_Room": "DoorLeaf_room_213", "Leaf_Closet": "DoorLeaf_closet_1", "Leaf_Kit": "DoorLeaf_stairs_down"},
             "dining": {"Leaf_Hall": "DoorLeaf_floor_2"}, "reception": {"Leaf_Hall": "DoorLeaf_floor_2"}, "key_room": {"Leaf_Hall": "DoorLeaf_floor_2"}}
WHITE_CAP = 12.0       # a map's white point: its 99.5th percentile texel, at most 12 x its 90th (the galleries' rule)
SHOULDER = {"default": (70.0, 2.5), "key_room": (35.0, 2.0), "dining": (65.0, 2.4)}   # light above the map's percentile k rolls off toward f x k

# the lights (Cycles watts) and the toggled materials' strengths
SCONCE_W, SHADE_EMIT, STAIR_W, EXIT_EMIT = 80.0, 3.0, 60.0, 5.0
LAMP_W, DOME_W, CHAND_W, PENDANT_W = 50.0, 90.0, 140.0, 420.0


def work():
    p = Path(arg("--work", str(Path(os.environ.get("TEMP", tempfile.gettempdir())) / "farway_hotel_floor2")))
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


def trellis(X, Y, P, oy=0.0):
    """A medallion trellis of period P: (d, r, th) = the diamond distance, the radius and the angle in each cell."""
    lx = np.mod(X, P) - P / 2
    ly = np.mod(Y - oy, P) - P / 2
    return np.abs(lx) + np.abs(ly), np.sqrt(lx ** 2 + ly ** 2), np.arctan2(ly, lx), lx, ly


def gen_green_carpet():
    """The corridor's wall-to-wall carpet: 8.8 m along (u) by its 2.2 m width (v). A deep green field with an old-gold medallion trellis and
    small claret hearts; a darker green border with two gold lines and a row of lozenges along each wall; faded and flattened down the middle
    where people walk; grime and a few old stains."""
    H, W = 512, 2048
    rng = np.random.default_rng(201)
    v = (np.arange(H) + 0.5) / H * 2.2
    u = (np.arange(W) + 0.5) / W * 8.8
    Y, X = np.meshgrid(v, u, indexing="ij")
    field, gold, claret, dark, sage = col(30, 62, 44), col(150, 128, 70), col(110, 44, 44), col(16, 36, 26), col(70, 104, 74)
    img = np.broadcast_to(field, (H, W, 3)).copy()
    d, r, th, lx, ly = trellis(X, Y, 0.55, 1.1)
    img = lerp(img, gold, smooth(0.014, 0.005, np.abs(d - 0.22)) * 0.9)
    petal = 0.075 * (0.7 + 0.3 * np.cos(4 * th))
    img = lerp(img, sage, smooth(petal + 0.01, petal, r))
    img = lerp(img, gold, smooth(0.012, 0.004, np.abs(r - petal)) * 0.8)
    img = lerp(img, claret, smooth(0.028, 0.02, r))
    cx = np.minimum(np.abs(np.abs(lx) - 0.275), 1) + np.minimum(np.abs(np.abs(ly) - 0.275), 1)
    img = lerp(img, claret, smooth(0.04, 0.028, cx) * 0.9)
    e = np.minimum(Y, 2.2 - Y)
    bord = e < 0.26
    img[bord] = dark
    for a0, a1 in ((0.05, 0.068), (0.215, 0.232)):
        m = (e >= a0) & (e < a1)
        img[m] = gold * 0.9
    lz = np.abs(np.mod(X, 0.24) - 0.12) / 0.12 + np.abs(e - 0.141) / 0.05
    img = np.where(((lz < 1.0) & bord)[..., None], lerp(dark, sage, 0.85) * np.ones(3), img)
    n = vnoise(H, W, rng, 6, 3)
    fine = vnoise(H, W, rng, 3, 64)
    wear = np.exp(-((Y - 1.1) / 0.45) ** 2) * (0.45 + 0.55 * n)
    img = lerp(img, col(84, 100, 80), 0.4 * wear)
    img *= (0.86 + 0.26 * fine)[..., None]
    img *= (0.9 + 0.2 * n)[..., None]
    for _ in range(8):
        sx, sy, rr = rng.random() * 8.8, 0.35 + rng.random() * 1.5, 0.05 + rng.random() * 0.14
        dd = np.sqrt(((X - sx + 4.4) % 8.8 - 4.4) ** 2 / 1.6 + (Y - sy) ** 2) / rr
        img *= (1 - 0.3 * smooth(1.0, 0.6, dd + 0.25 * (n - 0.5)))[..., None]
    return np.clip(img, 0, 1)


def gen_field():
    """The alcoves' and closets' carpet: the corridor's green with small gold flecks, 1 m square."""
    H = W = 512
    rng = np.random.default_rng(202)
    n = vnoise(H, W, rng, 5, 4)
    fine = vnoise(H, W, rng, 3, 96)
    img = np.broadcast_to(col(30, 60, 42), (H, W, 3)).copy()
    img = lerp(img, col(140, 120, 66), smooth(0.83, 0.9, fine) * 0.8)
    img *= (0.85 + 0.3 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_hall_carpet(seed, field_c=(32, 64, 46)):
    """The key rooms' carpet, 2 m square: a large rosette on each metre with fleurons between, old gold on deep green, faded in patches."""
    H = W = 1024
    rng = np.random.default_rng(seed)
    t = (np.arange(H) + 0.5) / H * 2.0
    Y, X = np.meshgrid(t, t, indexing="ij")
    img = np.broadcast_to(col(*field_c), (H, W, 3)).copy()
    d, r, th, lx, ly = trellis(X, Y, 1.0)
    ros = 0.3 * (0.75 + 0.25 * np.cos(8 * th))
    img = lerp(img, col(58, 92, 66), smooth(ros + 0.01, ros, r))
    img = lerp(img, col(150, 126, 70), smooth(0.012, 0.004, np.abs(r - ros)) * 0.85)
    img = lerp(img, col(150, 126, 70), smooth(0.01, 0.004, np.abs(r - 0.12)) * 0.85)
    img = lerp(img, col(112, 46, 44), smooth(0.06, 0.05, r))
    img = lerp(img, col(150, 126, 70), smooth(0.012, 0.005, np.abs(d - 0.48)) * 0.6)
    fx = np.minimum(np.abs(np.abs(lx) - 0.5), 1) + np.minimum(np.abs(np.abs(ly) - 0.5), 1)
    img = lerp(img, col(58, 92, 66), smooth(0.09, 0.075, fx))
    img = lerp(img, col(112, 46, 44), smooth(0.03, 0.022, fx))
    n = vnoise(H, W, rng, 6, 3)
    fine = vnoise(H, W, rng, 3, 128)
    img = lerp(img, col(80, 96, 78), 0.35 * smooth(0.55, 0.8, n))
    img *= (0.85 + 0.28 * fine)[..., None]
    img *= (0.9 + 0.2 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_room_carpet():
    """The green room's carpet, 2 m square: a small sage trellis on bottle green, flattened in a walked lane."""
    H = W = 1024
    rng = np.random.default_rng(203)
    t = (np.arange(H) + 0.5) / H * 2.0
    Y, X = np.meshgrid(t, t, indexing="ij")
    img = np.broadcast_to(col(36, 70, 50), (H, W, 3)).copy()
    d, r, th, lx, ly = trellis(X, Y, 0.25)
    img = lerp(img, col(76, 110, 80), smooth(0.008, 0.003, np.abs(d - 0.1)) * 0.8)
    img = lerp(img, col(140, 120, 70), smooth(0.016, 0.01, r) * 0.8)
    n = vnoise(H, W, rng, 6, 4)
    fine = vnoise(H, W, rng, 3, 128)
    img *= (0.84 + 0.3 * fine)[..., None]
    img *= (0.88 + 0.24 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_damask(seed, ground, motif, fade=0.25):
    """A tone-on-tone damask wallpaper, 1 m square: a lacy mirrored motif (thresholded mirrored noise inside a pointed oval) in 0.25 m by 0.5 m
    cells on a half drop, framed by an ogee lattice of fine lines; faded and foxed."""
    S = 1024
    rng = np.random.default_rng(seed)
    cw, ch = S // 4, S // 2
    nz = vnoise(ch, cw // 2, rng, 2, 22)
    u = (np.arange(cw) + 0.5) / cw - 0.5
    v = (np.arange(ch) + 0.5) / ch
    V, U = np.meshgrid(v, u, indexing="ij")
    hx = np.clip((np.abs(U) * cw).astype(int), 0, cw // 2 - 1)
    m = nz[np.arange(ch)[:, None], hx]
    half = 0.36 * np.sin(np.pi * np.clip((V - 0.08) / 0.84, 0, 1)) ** 0.7
    inside = smooth(0.012, -0.012, np.abs(U) - half)
    lace = smooth(0.5, 0.54, m) * inside
    rim = smooth(0.012, 0.004, np.abs(np.abs(U) - half)) * (V > 0.1) * (V < 0.9)
    stem = smooth(0.012, 0.005, np.abs(U)) * (V > 0.04) * (V < 0.96)
    ogee = smooth(0.008, 0.003, np.abs(np.abs(U) - (0.5 - 0.1 * np.abs(np.sin(np.pi * V)))))
    cell = np.clip(lace * 0.9 + rim + stem * 0.8 + ogee * 0.6, 0, 1)
    tile = np.zeros((S, S))
    for c in range(4):
        sh = (ch // 2) * (c % 2)
        tile[:, c * cw:(c + 1) * cw] = np.roll(np.vstack([cell, cell]), sh, axis=0)
    g, mo = col(*ground), col(*motif)
    img = lerp(np.broadcast_to(g, (S, S, 3)), mo, tile)
    n = vnoise(S, S, rng, 5, 3)
    fine = vnoise(S, S, rng, 2, 160)
    img = lerp(img, col(150, 146, 116), fade * smooth(0.45, 0.85, n))
    img *= (0.92 + 0.1 * fine)[..., None]
    return np.clip(img, 0, 1)


def gen_stripe_paper():
    """The green room's wallpaper, 1 m square: a regency stripe in cream and pale sage, a fine linen grain, faded."""
    S = 1024
    rng = np.random.default_rng(204)
    x = (np.arange(S) + 0.5) / S
    st = np.mod(x, 0.1)
    band = smooth(0.003, 0.0, np.abs(st - 0.025)) * 0 + ((st > 0.0) & (st < 0.05)).astype(float)
    line = smooth(0.0025, 0.001, np.abs(st - 0.075))
    img = np.broadcast_to(col(214, 206, 176), (S, S, 3)).copy()
    img = lerp(img, col(168, 184, 150), np.broadcast_to(band[None, :], (S, S)))
    img = lerp(img, col(120, 140, 106), np.broadcast_to(line[None, :], (S, S)) * 0.7)
    n = vnoise(S, S, rng, 5, 3)
    fine = vnoise(S, S, rng, 2, 160)
    img = lerp(img, col(196, 186, 150), 0.25 * smooth(0.45, 0.85, n))
    img *= (0.93 + 0.1 * fine)[..., None]
    return np.clip(img, 0, 1)


def gen_block():
    """Painted concrete block for the stairwell: 0.4 x 0.2 m blocks with mortar joints, 1.6 m square."""
    src = load_pixels("main_floor/wall_paint_diff.jpg")
    H, W = src.shape[:2]
    t = (np.arange(H) + 0.5) / H * 1.6
    Y, X = np.meshgrid(t, t, indexing="ij")
    row = np.floor(Y / 0.2)
    xo = X + (row % 2) * 0.2
    j = np.minimum(np.abs(np.mod(Y, 0.2) - 0.0), np.abs(np.mod(Y, 0.2) - 0.2))
    j = np.minimum(j, np.minimum(np.abs(np.mod(xo, 0.4)), np.abs(np.mod(xo, 0.4) - 0.4)))
    img = src * (1 - 0.22 * smooth(0.008, 0.003, j))[..., None]
    return np.clip(img, 0, 1)


def gen_stain(seed, size=512, dark=False):
    """A water stain (RGBA): a soft tide-marked blot, transparent around it."""
    rng = np.random.default_rng(seed)
    t = (np.arange(size) + 0.5) / size * 2 - 1
    Y, X = np.meshgrid(t, t, indexing="ij")
    n = vnoise(size, size, rng, 5, 3)
    r = np.sqrt(X ** 2 + Y ** 2) + 0.45 * (n - 0.5)
    inside = smooth(0.78, 0.6, r)
    rim = smooth(0.07, 0.0, np.abs(r - 0.66)) + 0.6 * smooth(0.05, 0.0, np.abs(r - 0.42))
    c = col(30, 26, 18) if dark else col(128, 98, 56)
    rgb = np.broadcast_to(c, (size, size, 3)) * (0.85 + 0.3 * n)[..., None]
    a = np.clip(0.26 * inside + 0.5 * rim * smooth(0.85, 0.6, r), 0, 0.8) * (0.5 if dark else 1.0)
    return np.concatenate([np.clip(rgb, 0, 1), a[..., None]], axis=2)


def gen_landscapes():
    """Four old landscape paintings in one 2 x 2 atlas (512 x 384 each), darkened under yellowed varnish: a valley with a river and trees, a
    lake under mountains at dusk, a coast with a ruined tower, a wood with a path into it."""
    H, W = 768, 1024
    img = np.zeros((H, W, 3))
    rng = np.random.default_rng(207)
    h, w = 384, 512
    y = (np.arange(h) + 0.5) / h
    x = (np.arange(w) + 0.5) / w
    Y, X = np.meshgrid(y, x, indexing="ij")              # Y = 0 is the bottom of the picture (numpy row 0 is the image's bottom in Blender)
    n = vnoise(h, w, rng, 5, 3)
    brush = vnoise(h, w, rng, 3, 48)
    # 1: a valley
    a = lerp(col(176, 186, 170), col(228, 206, 156), smooth(0.95, 0.55, Y))
    for k, (hy, c_) in enumerate(((0.62, col(120, 128, 120)), (0.5, col(96, 116, 74)), (0.36, col(78, 96, 52)))):
        ridge = hy + 0.05 * np.sin(X * (4 + k * 3) + k * 1.7) + 0.04 * (n - 0.5)
        a = lerp(a, c_, (Y < ridge).astype(float))
    riv = np.abs(X - 0.55 - 0.12 * np.sin(Y * 9)) < 0.03 * (1.2 - Y)
    a[(Y < 0.36) & riv] = col(170, 180, 170)
    for _ in range(14):
        cx, cy, s = rng.random(), 0.1 + rng.random() * 0.3, 0.03 + rng.random() * 0.04
        a = lerp(a, col(46, 62, 34), smooth(s, s * 0.7, np.sqrt((X - cx) ** 2 + ((Y - cy) * 0.7) ** 2) + 0.03 * brush))
    # 2: a lake at dusk
    b = lerp(col(110, 96, 120), col(232, 170, 110), smooth(1.0, 0.45, Y))
    mt = 0.45 + 0.25 * np.maximum(0, 1 - np.abs(X - 0.35) * 3.2) + 0.15 * np.maximum(0, 1 - np.abs(X - 0.75) * 4) + 0.03 * n
    b = lerp(b, col(72, 70, 90), ((Y < mt) & (Y > 0.4)).astype(float))
    b = lerp(b, lerp(col(150, 120, 110), col(60, 64, 80), smooth(0.4, 0.1, Y)), (Y <= 0.4).astype(float))
    b = lerp(b, col(240, 200, 140), smooth(0.05, 0.035, np.sqrt((X - 0.62) ** 2 + (Y - 0.62) ** 2)))
    # 3: a coast with a tower
    c = lerp(col(150, 164, 176), col(206, 204, 190), smooth(1.0, 0.5, Y))
    c = lerp(c, col(70, 100, 110), (Y < 0.42 + 0.01 * np.sin(X * 40)).astype(float))
    cliff = (X < 0.42 + 0.1 * Y + 0.05 * n) & (Y < 0.62 - 0.4 * X)
    c[cliff] = col(110, 100, 80)
    tower = (np.abs(X - 0.16) < 0.03) & (Y < 0.74) & (Y > 0.5)
    c[tower] = col(90, 84, 74)
    c = lerp(c, col(220, 226, 220), smooth(0.02, 0.0, np.abs(Y - 0.42 - 0.02 * np.sin(X * 25 + 2))) * (X > 0.4) * 0.6)
    # 4: a wood and a path
    d = lerp(col(70, 84, 52), col(170, 170, 120), smooth(0.2, 0.9, Y) * smooth(0.0, 0.25, 0.5 - np.abs(X - 0.5)))
    for k in range(9):
        tx = 0.06 + k * 0.11 + 0.03 * rng.random()
        d = lerp(d, col(48, 40, 30), (np.abs(X - tx) < 0.012 + 0.008 * (1 - Y)).astype(float) * (Y < 0.9))
    path = np.abs(X - 0.5 - 0.06 * np.sin(Y * 6)) < 0.18 * (1 - Y) * (Y < 0.55)
    d[path] = col(150, 130, 96)
    d = lerp(d, col(52, 70, 40), smooth(0.55, 0.8, n) * (Y > 0.6) * 0.7)
    for i, p in enumerate((a, b, c, d)):
        p = p * (0.86 + 0.18 * brush)[..., None] * (0.92 + 0.1 * n)[..., None]
        p = lerp(p, col(150, 120, 60), 0.18)
        r_, c_ = divmod(i, 2)
        img[r_ * h:(r_ + 1) * h, c_ * w:(c_ + 1) * w] = p
    return np.clip(img * 0.85, 0, 1)


def gen_card():
    """The fire-escape plan on the back of a room door: a cream card, a green border, the floor's plan in black, red arrows to the stairs."""
    H, W = 320, 256
    img = np.ones((H, W, 3)) * col(232, 226, 206)
    g = col(40, 80, 52)
    img[:10], img[-10:], img[:, :10], img[:, -10:] = g, g, g, g
    img[150:156, 30:226] = 0.1
    img[214:220, 30:226] = 0.1
    for xx in range(30, 230, 38):
        img[110:150, xx:xx + 4] = 0.15
        img[220:260, xx:xx + 4] = 0.15
    img[178:190, 40:210] = col(190, 40, 30)
    for k in range(10):
        img[184 - k:186 + k, 210 + k:212 + k] = col(190, 40, 30)
    img[40:70, 40:216] = col(40, 40, 40)
    return np.clip(img, 0, 1)


def gen_brushed():
    H = W = 256
    rng = np.random.default_rng(208)
    n = vnoise(H, W, rng, 3, 2)
    streak = vnoise(H, 8, rng, 3, 64)
    streak = np.repeat(streak, W // 8, axis=1)
    img = (0.7 + 0.12 * streak + 0.08 * n)[..., None] * np.ones(3)
    return np.clip(img, 0, 1)


def gen_leather():
    """Oxblood leather, 0.5 m square: a fine pebbled grain, worn paler on the high spots."""
    S = 512
    rng = np.random.default_rng(209)
    g = vnoise(S, S, rng, 3, 96)
    n = vnoise(S, S, rng, 5, 3)
    img = lerp(np.broadcast_to(col(92, 34, 28), (S, S, 3)), col(140, 74, 56), smooth(0.55, 0.85, n) * 0.5)
    img *= (0.8 + 0.35 * g)[..., None]
    return np.clip(img, 0, 1)


def gen_quilt():
    """The green room's bedspread, 1 m square: a cream ground quilted in diamonds, a sage border band, faded."""
    S = 1024
    rng = np.random.default_rng(210)
    t = (np.arange(S) + 0.5) / S
    Y, X = np.meshgrid(t, t, indexing="ij")
    img = np.broadcast_to(col(206, 198, 168), (S, S, 3)).copy()
    q = 0.125
    dd = np.minimum(np.abs(np.mod(X + Y, q) - q / 2), np.abs(np.mod(X - Y, q) - q / 2))
    img *= (1 - 0.18 * smooth(0.004, 0.001, np.abs(dd - q / 2)))[..., None]
    img = lerp(img, col(120, 150, 110), smooth(0.03, 0.02, np.abs(np.mod(Y, 0.5) - 0.25)) * 0.8)
    n = vnoise(S, S, rng, 4, 4)
    img *= (0.9 + 0.16 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_clock():
    """A clock face, 256 px: cream enamel, a black chapter ring with twelve bold and sixty fine ticks, blued hands stopped at 3:17."""
    S = 256
    t = (np.arange(S) + 0.5) / S * 2 - 1
    Y, X = np.meshgrid(t, t, indexing="ij")
    r, th = np.sqrt(X ** 2 + Y ** 2), np.arctan2(Y, X)
    img = np.ones((S, S, 3)) * col(232, 222, 196)
    img = lerp(img, col(30, 30, 30), smooth(0.012, 0.004, np.abs(r - 0.86)))
    for k in range(60):
        a = k * math.pi / 30
        big = k % 5 == 0
        dl = np.abs(-X * math.sin(a) + Y * math.cos(a))
        along = X * math.cos(a) + Y * math.sin(a)
        m = (dl < (0.025 if big else 0.008)) & (along > (0.66 if big else 0.76)) & (along < 0.84)
        img[m] = col(30, 30, 30)
    for ang, ln, wd in ((math.pi / 2 - 2 * math.pi * (3 + 17 / 60) / 12, 0.45, 0.03), (math.pi / 2 - 2 * math.pi * 17 / 60, 0.7, 0.018)):
        dl = np.abs(-X * math.sin(ang) + Y * math.cos(ang))
        along = X * math.cos(ang) + Y * math.sin(ang)
        img[(dl < wd) & (along > -0.08) & (along < ln)] = col(26, 34, 60)
    img[r < 0.04] = col(26, 34, 60)
    img[r > 0.98] = col(150, 120, 60)
    return np.clip(img, 0, 1)


def gen_ledger():
    """An open ledger, 512 x 256: two cream pages, ruled in blue with a red margin, rows of faded handwriting, a few names crossed out."""
    H, W = 256, 512
    rng = np.random.default_rng(211)
    img = np.ones((H, W, 3)) * col(226, 216, 186)
    for yy in range(18, H - 10, 11):
        img[yy:yy + 1, 8:W - 8] = col(150, 166, 196)
    for x0 in (40, 296):
        img[8:H - 8, x0:x0 + 1] = col(196, 90, 80)
    img[:, 254:258] = col(160, 146, 116)
    n = vnoise(H, W, rng, 2, 64)
    for yy in range(26, H - 14, 11):
        for x0, x1 in ((46, 120 + rng.integers(0, 110)), (302, 380 + rng.integers(0, 110))):
            seg = n[yy - 6:yy, x0:x1] > 0.52
            sub = img[yy - 6:yy, x0:x1]
            sub[seg] = col(52, 46, 60)
            if rng.random() < 0.08:
                img[yy - 3:yy - 2, x0:x1] = col(52, 46, 60)
    return np.clip(img, 0, 1)


# a 3 x 5 digit font (rows top to bottom), for numbered plates drawn into textures
DIGITS = {"0": "111101101101111", "1": "010110010010111", "2": "111001111100111", "3": "111001111001111", "4": "101101111001001",
          "5": "111100111001111", "6": "111100111101111", "7": "111001010010010", "8": "111101111101111", "9": "111101111001111"}


def gen_plates(numbers, cols_, fg, bg, cell=(64, 32), border=None):
    """An atlas of small number plates: plate k (in `numbers`) at column k % cols_, row k // cols_ from the top. Returns (image, rows)."""
    cw, chh = cell
    rows = (len(numbers) + cols_ - 1) // cols_
    img = np.ones((rows * chh, cols_ * cw, 3)) * col(*bg)
    for k, num in enumerate(numbers):
        r_, c_ = divmod(k, cols_)
        y0, x0 = r_ * chh, c_ * cw
        if border:
            img[y0:y0 + 2, x0:x0 + cw] = col(*border)
            img[y0 + chh - 2:y0 + chh, x0:x0 + cw] = col(*border)
            img[y0:y0 + chh, x0:x0 + 2] = col(*border)
            img[y0:y0 + chh, x0 + cw - 2:x0 + cw] = col(*border)
        s = str(num)
        px = max(1, min((cw - 8) // (4 * len(s)), (chh - 8) // 5))
        tw = (4 * len(s) - 1) * px
        sx, sy = x0 + (cw - tw) // 2, y0 + (chh - 5 * px) // 2
        for i, ch_ in enumerate(s):
            bits = DIGITS[ch_]
            for rr in range(5):
                for cc in range(3):
                    if bits[rr * 3 + cc] == "1":
                        yy = sy + rr * px
                        xx = sx + (i * 4 + cc) * px
                        img[yy:yy + px, xx:xx + px] = col(*fg)
    return img[::-1].copy(), rows               # numpy row 0 is the image's bottom in Blender: flip so plate 0 is at the top


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


WALLP, PLAST, WOOD, LINEN, MARBLE = "main_floor/wall_paint_diff.jpg", "laboratory/wall_paint_diff.jpg", "apartment/dark_wood_diff_1k.jpg", \
    "apartment/rough_linen_diff_512.jpg", "galleries/marble_01_diff_1k.jpg"
WARM = (1.0, 0.78, 0.52)
NUMBERS = {}          # plate atlases: name -> (numbers, cols, rows)


def make_materials():
    g = {k: mk_image(k, f()) for k, f in (("gen_brushed", gen_brushed), ("gen_landscapes", gen_landscapes),
                                          ("gen_stain_ceiling", lambda: gen_stain(221)), ("gen_stain_floor", lambda: gen_stain(222, 256, True)))}
    # shared by every scene
    material("Lamp_Emit", color=(1.0, 0.9, 0.74), rough=0.9, emit=(WARM, SHADE_EMIT))
    material("Lamp_Dead", color=srgb_lin("#a49c88"), rough=0.9)
    material("Brass", img=g["gen_brushed"], tint=srgb_lin("#b48c4c"), rough=0.35, metal=0.9, tile=0.3)
    material("Steel", img=g["gen_brushed"], tint=srgb_lin("#a6a8a6"), rough=0.35, metal=0.9, tile=0.4)
    material("Plastic_White", color=srgb_lin("#d6d2c6"), rough=0.5)
    material("Plastic_Black", color=srgb_lin("#1a1a1a"), rough=0.4)
    material("Trim_Wood", tex=WOOD, tint=(1.0, 0.9, 0.8), rough=0.45, tile=0.8)
    material("Trim_Cream", tex=WALLP, tint=srgb_lin("#ece2c6"), rough=0.6, tile=1.0)
    material("Wood_Dark", tex=WOOD, tint=(1.0, 0.88, 0.76), rough=0.45, tile=0.8)
    material("Picture", img=g["gen_landscapes"], rough=0.55)
    material("Frame_Gilt", img=g["gen_brushed"], tint=srgb_lin("#9c7a3c"), rough=0.4, metal=0.6, tile=0.2)
    material("Glass_Clear", color=(0.85, 0.92, 0.95), rough=0.05, alpha=0.16)
    material("Skirting", tex=WOOD, tint=(0.9, 0.76, 0.64), rough=0.5, tile=0.8)
    material("Door_Jamb", tex=WOOD, tint=(1.0, 0.9, 0.8), rough=0.45, tile=0.8)
    material("Threshold", img=g["gen_brushed"], tint=srgb_lin("#8c6c3c"), rough=0.4, metal=0.8, tile=0.3)
    material("Decal_Ceiling", img=g["gen_stain_ceiling"], rough=1.0, img_alpha=True)
    material("Decal_Floor", img=g["gen_stain_floor"], rough=1.0, img_alpha=True)
    material("Standin_Grey", color=(0.4, 0.38, 0.34), rough=0.9)
    material("Leaf_Room", tex=WOOD, tint=(1.0, 0.84, 0.7), rough=0.4, tile=0.9)
    material("Leaf_Hall", tex=WOOD, tint=(1.0, 0.84, 0.7), rough=0.4, tile=0.9)
    material("Leaf_Brass", img=g["gen_brushed"], tint=srgb_lin("#b8904e"), rough=0.3, metal=0.9, tile=0.2)
    material("SB_Carpet", color=srgb_lin("#1e3a2a"), rough=1.0)
    material("SB_Wall", color=srgb_lin("#5c7a5a"), rough=0.8)
    material("SB_Wainscot", color=srgb_lin("#d6caa6"), rough=0.8)
    material("SB_Ceiling", color=srgb_lin("#d0c6aa"), rough=0.9)
    if KIND == "corridor":
        g2 = {k: mk_image(k, f()) for k, f in (("gen_green_carpet", gen_green_carpet), ("gen_field", gen_field), ("gen_block", gen_block),
                                               ("gen_card", gen_card), ("gen_damask", lambda: gen_damask(205, (112, 146, 108), (134, 166, 126))))}
        material("Carpet_Green", img=g2["gen_green_carpet"], rough=1.0)
        material("Carpet_Field", img=g2["gen_field"], rough=1.0, tile=1.0)
        material("Wall_Green", img=g2["gen_damask"], rough=0.7, tile=0.6)
        material("Wainscot", tex=WALLP, tint=srgb_lin("#e6dcc0"), rough=0.6, tile=1.2)
        material("Ceiling_Plaster", tex=PLAST, tint=srgb_lin("#e4dcc6"), rough=0.95, tile=1.2)
        material("Closet_Paint", tex=WALLP, tint=srgb_lin("#c8c0a2"), rough=0.9, tile=1.5)
        material("Lift_Steel", img=g["gen_brushed"], tint=srgb_lin("#7c7e7a"), rough=0.4, metal=0.85, tile=0.4)
        material("Jamb_Steel", tex=WALLP, tint=srgb_lin("#6e7668"), rough=0.5, tile=1.0)
        material("Stair_Concrete", tex="factory_floor/concrete_floor_diff.jpg", tint=srgb_lin("#c8c4b8"), rough=0.8, tile=1.5)
        material("Stair_Paint", img=g2["gen_block"], tint=srgb_lin("#aebca4"), rough=0.8, tile=1.6)
        material("Stair_Ceiling", tex=WALLP, tint=srgb_lin("#c4c6b8"), rough=0.9, tile=1.5)
        material("Leaf_Card", img=g2["gen_card"], rough=0.6)
        material("Leaf_Fire", tex=WALLP, tint=srgb_lin("#7c8a76"), rough=0.5, tile=1.0)
        material("Leaf_Closet", tex=WALLP, tint=srgb_lin("#ddd2b2"), rough=0.6, tile=1.0)
        material("Leaf_Glass", color=srgb_lin("#2a3234"), rough=0.2)
        material("Red_Paint", color=srgb_lin("#9a2018"), rough=0.4)
        material("Emergency_Emit", color=(0.9, 0.1, 0.08), rough=0.4, emit=((1.0, 0.08, 0.05), EXIT_EMIT))
        material("Porcelain_Celadon", color=srgb_lin("#8fae96"), rough=0.2)
        material("Dried_Stems", color=srgb_lin("#7a6a48"), rough=0.9)
        material("Mirror", color=srgb_lin("#8c969a"), rough=0.08, metal=0.8)
    elif KIND == "keyroom":
        wall = {"dining": lambda: gen_damask(206, (176, 166, 120), (196, 186, 140), 0.2), "reception": lambda: gen_damask(207, (110, 142, 106), (132, 162, 124)),
                "key_room": lambda: gen_damask(208, (138, 156, 122), (152, 170, 134), 0.3)}[SCENE]
        g2 = {k: mk_image(k, f()) for k, f in (("gen_hall_carpet", lambda: gen_hall_carpet({"dining": 231, "reception": 232, "key_room": 233}[SCENE])),
                                               ("gen_wall_hall", wall))}
        material("Carpet_Hall", img=g2["gen_hall_carpet"], rough=1.0, tile=2.0)
        material("Wall_Hall", img=g2["gen_wall_hall"], rough=0.7, tile=0.7)
        if SCENE == "key_room":
            material("Wainscot", tex=WOOD, tint=(1.0, 0.8, 0.62), rough=0.5, tile=1.0)
        else:
            material("Wainscot", tex=WALLP, tint=srgb_lin("#e6dcc0"), rough=0.6, tile=1.2)
        material("Ceiling_Hall", tex=PLAST, tint=srgb_lin("#e6decb"), rough=0.95, tile=1.4)
        material("Window_Void", color=srgb_lin("#101214"), rough=0.6)
        material("Window_Frame", tex=WALLP, tint=srgb_lin("#ddd2b4"), rough=0.6, tile=1.0)
        material("Drape", tex=LINEN, tint=srgb_lin("#2e5a3c"), rough=0.95, tile=0.6)
        material("Drape_Sheer", tex=LINEN, tint=srgb_lin("#e6dcc6"), rough=0.95, tile=0.5)
        material("Cloth_White", tex=LINEN, tint=srgb_lin("#f0ebe0"), rough=0.95, tile=0.5)
        material("China", color=srgb_lin("#ebe6da"), rough=0.2)
        material("Silver", img=g["gen_brushed"], tint=srgb_lin("#c8c8c4"), rough=0.25, metal=0.95, tile=0.2)
        material("Upholstery", tex=LINEN, tint=srgb_lin("#3c6446"), rough=0.9, tile=0.4)
        material("Candle", color=srgb_lin("#efe6d0"), rough=0.6)
        material("Marble", tex=MARBLE, tint=srgb_lin("#e4e0d8"), rough=0.2, tile=1.2)
        g3 = {k: mk_image(k, f()) for k, f in (("gen_leather", gen_leather), ("gen_clock", gen_clock), ("gen_ledger", gen_ledger))}
        material("Leather", img=g3["gen_leather"], rough=0.5, tile=0.5)
        material("Clock_Face", img=g3["gen_clock"], rough=0.3)
        material("Ledger_Page", img=g3["gen_ledger"], rough=0.8)
        material("Book_Cover", color=srgb_lin("#5a2420"), rough=0.6)
        material("Glass_Green", color=srgb_lin("#1e6a3c"), rough=0.15)
        material("Iron", img=g["gen_brushed"], tint=srgb_lin("#3c3e3c"), rough=0.55, metal=0.7, tile=0.3)
        material("Safe_Paint", color=srgb_lin("#2c4a36"), rough=0.45, metal=0.2)
        material("Key_Tag", color=srgb_lin("#c8b48a"), rough=0.7)
        material("Key_Tag_Red", color=srgb_lin("#8a2a22"), rough=0.7)
        if SCENE == "reception":
            nums = [str(n) for n in range(101, 101 + 32 * 7)]
            NUMBERS["Plates"] = (nums, 32)
        else:
            nums = [str(n) for n in range(1, 1 + 32 * 4 + 20 * 4 + 64)]
            NUMBERS["Plates"] = (nums, 32)
        im, rows = gen_plates(NUMBERS["Plates"][0], NUMBERS["Plates"][1], (40, 30, 20), (196, 168, 104), border=(120, 90, 40))
        NUMBERS["Plates"] = (*NUMBERS["Plates"], rows)
        material("Number_Plates", img=mk_image("gen_plates", im), rough=0.35, metal=0.4)
    else:
        g2 = {k: mk_image(k, f()) for k, f in (("gen_room_carpet", gen_room_carpet), ("gen_stripe_paper", gen_stripe_paper), ("gen_quilt", gen_quilt))}
        material("Carpet_Room", img=g2["gen_room_carpet"], rough=1.0, tile=2.0)
        material("Wall_Room", img=g2["gen_stripe_paper"], rough=0.7, tile=1.0)
        material("Ceiling_Room", tex=PLAST, tint=srgb_lin("#e8e0cc"), rough=0.95, tile=1.2)
        material("Bedspread", img=g2["gen_quilt"], rough=0.95, tile=1.0)
        material("Linen_White", tex=LINEN, tint=srgb_lin("#f2e8dc"), rough=0.95, tile=0.6)
        material("Velvet_Green", tex=LINEN, tint=srgb_lin("#2c5a3c"), rough=0.85, tile=0.4)
        material("Drape", tex=LINEN, tint=srgb_lin("#2e5a3c"), rough=0.95, tile=0.6)
        material("Drape_Sheer", tex=LINEN, tint=srgb_lin("#e6dcc6"), rough=0.95, tile=0.5)
        material("Window_Void", color=srgb_lin("#101214"), rough=0.6)
        material("Window_Frame", tex=WALLP, tint=srgb_lin("#ddd2b4"), rough=0.6, tile=1.0)
        material("Door_Bath", tex=WALLP, tint=srgb_lin("#e0d4b2"), rough=0.6, tile=1.0)
        material("Paper", color=srgb_lin("#e6dcc4"), rough=0.8)
        material("Blotter", color=srgb_lin("#2a4a34"), rough=0.9)
        material("Book_Green", color=srgb_lin("#3a5a40"), rough=0.6)


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
    res = bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                                matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())
    return res


def tube(bm, p0, p1, r0, r1=None, seg=24):
    """An open tube (no caps)."""
    cyl(bm, p0, p1, r0, r1, seg, cap=False)


def sphere(bm, p, r, seg=12):
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(4, seg // 2), radius=r, matrix=Matrix.Translation(B(p)))


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


ART = PROPS = ARCH = SKIN = DOORS = LAYOUT = STANDIN = BAKE_STANDIN = LIGHTS = KIT = None


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


def corridor_wall(side):
    Z = GB.CORR_Z
    return {"N": Wall("z", -Z, 1), "S": Wall("z", Z, -1), "E": Wall("x", GB.CORR_X, -1), "W": Wall("x", -GB.CORR_X, 1)}[side]


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


def plate_quads(name, w, items, mat="Number_Plates", d=0.0):
    """Flat number plates on a wall face: items = [(k, a, y, width, height)]; plate k shows cell k of the Plates atlas (NUMBERS)."""
    nums, ncols, nrows = NUMBERS["Plates"]
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    R = w.right()
    flip = (R[0] if w.axis == "z" else R[2]) < 0
    for k, a, y, wd, ht in items:
        r_, c_ = divmod(k, ncols)
        u0, u1 = c_ / ncols, (c_ + 1) / ncols
        v1 = 1 - r_ / nrows
        v0 = 1 - (r_ + 1) / nrows
        corners = [(a - wd / 2, y - ht / 2), (a + wd / 2, y - ht / 2), (a + wd / 2, y + ht / 2), (a - wd / 2, y + ht / 2)]
        vs = [bm.verts.new(B(w.pt(aa, yy, d))) for aa, yy in corners]
        f = bm.faces.new(vs)
        f.normal_update()
        if f.normal.dot(B(w.normal())) < 0:
            f.normal_flip()
        for lp in f.loops:
            i = vs.index(lp.vert)
            t = 1.0 if i in (1, 2) else 0.0
            if flip:
                t = 1 - t
            lp[uvl].uv = (u0 + (u1 - u0) * t, v1 if i in (2, 3) else v0)
    return finish(name, bm, mat, PROPS, keep_uv=True)


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
    """Every COL_, Marker_, Link_/Arrive_ and Spot_ of the greybox model, with its names and numbers; the arch's art twins (grey boxes, for the
    layout check and the plan) in Art/Arch."""
    for b in M.boxes:
        if b.get("zone"):
            continue
        if b["col"]:
            col_box("COL_" + b["name"], b["min"], b["max"])
            if b["name"].startswith(SK.FURNITURE):
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


def gbox(ob):
    g = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return [min(p.x for p in g), min(p.z for p in g), min(-p.y for p in g)], [max(p.x for p in g), max(p.z for p in g), max(-p.y for p in g)]


def place_kit():
    """The connector kit's art (tools/blender/kit_place.py, blender/kit/README.md). Its layout records are the greybox model's already
    (build_hotel_greybox.kit_floor2, written by kit_layout as kit_place places them), so only art is taken here:
    - floor_2_lower: the elevator at (-20, 0, 0), yaw 90. The page draws the kit's own GLB there (its car moves, its leaves slide); here its art is
      a stand-in (collection `Kit`, never exported) for the bake and the stills. The appended layout objects are dropped (the model has them).
    - every corridor: the stair door's leaf (the store's 1.04 m door and its handle), read once in the kit's own frame and made into one mesh with
      its origin at the hinge (`Leaf_Kit`), which every stair door's node reuses."""
    if KIND != "corridor":
        return
    import kit_place
    if SK.is_lower(SK.model(SCENE)):
        made = kit_place.place("elevator", suffix="kit", at=(-GB.CORR_X, 0.0, 0.0), yaw_deg=90.0, art=True, collection=KIT)
        for n in made:
            ob = bpy.data.objects[n]
            if n.startswith(kit_place.PREFIXES):
                bpy.data.objects.remove(ob)
            elif ob.type == "MESH":
                ob.hide_render = False
    made = kit_place.place("stair_door", suffix="kitleaf", at=(0.0, 0.0, 0.0), yaw_deg=0.0, art=True, collection=KIT)
    kit = json.loads((ROOT / "world/kit/stair_door.json").read_text())
    rec = next(d for d in kit["doors"] if d["name"] == "DoorLeaf_stair")
    Mh = Matrix.Translation(B(rec["hinge"])) @ Matrix.Rotation(math.radians(rec["closed_yaw_deg"]), 4, "Z")
    bm = bmesh.new()
    mats = []
    for n in made:
        ob = bpy.data.objects[n]
        if ob.type == "MESH" and ob.get("node") == "Leaf_stair":
            tmp = bmesh.new()
            tmp.from_mesh(ob.data)
            tmp.transform(Mh.inverted() @ ob.matrix_world)
            m = ob.data.materials[0]
            if m not in mats:
                mats.append(m)
            for f in tmp.faces:
                f.material_index = mats.index(m)
            me = bpy.data.meshes.new("tmp")
            tmp.to_mesh(me)
            tmp.free()
            bm.from_mesh(me)
            bpy.data.meshes.remove(me)
        bpy.data.objects.remove(ob)
    me = bpy.data.meshes.new("Leaf_Kit")
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
        MATS[m.name] = m
    LEAF_MESH["Leaf_Kit"] = me
    print("KIT art:", len(KIT.objects), "stand-ins; Leaf_Kit", len(me.polygons), "faces,", [m.name for m in mats])


# ---------------------------------------------------------------- the skin (the shell as seen)
def build_skin():
    q, M = SK.scene_skin(SCENE)
    matf = SK.material_of(SCENE)
    by = {}
    for x in q:
        by.setdefault(matf(x), []).append(x)
    for mname, quads in sorted(by.items()):
        skin_mesh(mname, quads, SKIN)
    if KIND == "room":
        sq, _ = SK.scene_skin(SCENE, standin=True)
        by = {}
        for x in sq:
            by.setdefault(SK.room_material(x), []).append(x)
        for mname, quads in sorted(by.items()):
            skin_mesh("SB_" + mname, quads, BAKE_STANDIN, mname)
    return M


def skin_mesh(name, quads, coll, mname=None):
    mname = mname or name
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    tile = TILES.get(mname, 1.0)
    pieces = []
    for x in quads:                                      # long quads cut into pieces of 4 m at most: one 40 m island would shrink the whole atlas
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
            if mname == "Carpet_Green":
                u, v = gx / 8.8, (gz + GB.CORR_Z) / (2 * GB.CORR_Z)
            elif x["axis"] == 0:
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


def leaf_mesh(kind, width, height):
    """Local +X runs from the hinge along the leaf; z is up. The leaf's front (its -Y face) is the corridor side of a room door and the room side of
    a key room's door. Leaf_Room lies on the front side of its hinge (y -th..0, in the wall's opening at its room-side face); Leaf_Hall, Leaf_Closet
    and Leaf_Fire lie behind theirs (y 0..th)."""
    key = (kind, round(width, 3), round(height, 3))
    if key in LEAF_MESH:
        return LEAF_MESH[key]
    bm = bmesh.new()
    th = 0.05 if kind in ("Leaf_Room", "Leaf_Hall") else 0.045
    y0, y1 = (-th, 0.0) if kind == "Leaf_Room" else (0.0, th)
    w, h = width - 0.006, height - 0.008
    pieces = []

    def bx(x0, x1, ya, yb, z0, z1, mat):
        mm = bmesh.new()
        mm.loops.layers.uv.new("UVMap")
        bmesh.ops.create_cube(mm, size=1.0, matrix=Matrix.Translation(((x0 + x1) / 2, (ya + yb) / 2, (z0 + z1) / 2)) @ Matrix.Diagonal((x1 - x0, yb - ya, z1 - z0, 1)))
        pieces.append((mm, mat))

    def panels(rects, mat, both=True):
        """Raised panels in moulded frames, on the front (y0) face and, when `both`, the back (y1)."""
        for face, sg in ((y0, -1), (y1, 1)) if both else ((y0, -1),):
            for x0, x1, z0, z1 in rects:
                f0, f1 = sorted((face, face + sg * 0.008))
                q = 0.028
                bx(x0, x1, f0, f1, z0, z0 + q, mat)
                bx(x0, x1, f0, f1, z1 - q, z1, mat)
                bx(x0, x0 + q, f0, f1, z0 + q, z1 - q, mat)
                bx(x1 - q, x1, f0, f1, z0 + q, z1 - q, mat)
                r0, r1 = sorted((face, face + sg * 0.004))
                bx(x0 + 0.06, x1 - 0.06, r0, r1, z0 + 0.06, z1 - 0.06, mat)
    bx(0.003, w, y0, y1, 0.006, h, kind)
    if kind in ("Leaf_Room", "Leaf_Hall"):
        cx = w / 2
        rects = [(0.12, cx - 0.05, 0.24, 0.92), (cx + 0.05, w - 0.12, 0.24, 0.92), (0.12, cx - 0.05, 1.02, 1.5), (cx + 0.05, w - 0.12, 1.02, 1.5),
                 (0.12, cx - 0.05, 1.68, h - 0.13), (cx + 0.05, w - 0.12, 1.68, h - 0.13)]
        panels(rects, kind)
        bx(0.04, w - 0.04, y0 - 0.002, y0, 0.03, 0.2, "Leaf_Brass")                              # kick plate
        hx = w - 0.075
        for side, yy in ((-1, y0), (1, y1)):                                                  # lever roses and levers, both faces; the deadbolt above
            bx(hx - 0.025, hx + 0.025, *(sorted((yy, yy + side * 0.009))), 0.88, 1.06, "Leaf_Brass")
            bx(hx - 0.13, hx + 0.012, *(sorted((yy + side * 0.03, yy + side * 0.05))), 0.975, 0.995, "Leaf_Brass")
            bx(hx - 0.012, hx + 0.012, *(sorted((yy + side * 0.009, yy + side * 0.05))), 0.97, 1.0, "Leaf_Brass")
            bx(hx - 0.022, hx + 0.022, *(sorted((yy, yy + side * 0.012))), 1.13, 1.18, "Leaf_Brass")
        if kind == "Leaf_Room":
            bx(cx - 0.014, cx + 0.014, y0 - 0.006, y1 + 0.004, 1.43, 1.458, "Leaf_Brass")     # the peephole's barrel and rings
            bx(cx - 0.006, cx + 0.006, y0 - 0.0065, y0 - 0.006, 1.438, 1.45, "Leaf_Glass")
            bx(cx - 0.09, cx + 0.09, y1, y1 + 0.002, 1.2, 1.43, "Leaf_Card")                    # the fire-escape plan, room side
    elif kind == "Leaf_Closet":
        cx = w / 2
        panels([(0.1, w - 0.1, 0.2, 0.95), (0.1, w - 0.1, 1.05, h - 0.12)], kind, both=False)
        hx = w - 0.07
        bx(hx - 0.02, hx + 0.02, -0.055, -0.0, 0.93, 0.97, "Leaf_Brass")
    else:                                                                                    # the fire door: a steel leaf, a vision panel, a lever
        bx(w - 0.32, w - 0.16, -0.002, th + 0.002, 1.2, 1.85, "Leaf_Glass")
        hx = w - 0.08
        for yy, sd in ((0.0, -1), (th, 1)):
            bx(hx - 0.03, hx + 0.03, *sorted((yy, yy + sd * 0.01)), 0.92, 1.1, "Steel")
            bx(hx - 0.16, hx + 0.01, *sorted((yy + sd * 0.01, yy + sd * 0.05)), 1.0, 1.025, "Steel")
        bx(0.05, 0.5, -0.06, -0.0, h - 0.09, h - 0.05, "Steel")
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
    LEAF_MESH[key] = me
    return me


def box_uv_local(bm, tile):
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            u, v = (p.y, p.z) if ax == 0 else (p.x, p.z) if ax == 1 else (p.x, p.y)
            lp[uvl].uv = (u / tile, v / tile)


def leaf_kind(d):
    p = d["props"]
    if d["name"].startswith("DoorLeaf_stairs") or p.get("kind") == "stair door":
        return "Leaf_Fire"
    if "room" in p or (KIND == "corridor" and not p.get("kind")):
        return "Leaf_Room"
    if p.get("kind") == "closet":
        return "Leaf_Closet"
    if KIND == "keyroom":
        return "Leaf_Hall"
    return "Leaf_Fire"


def build_leaves(M):
    leaves = {}
    for d in M.doors:
        p = d["props"]
        name = d["name"]
        if p.get("kind") == "elevator":                    # the kit's elevator: its leaves are its own GLB's; the layout keeps the record
            ob = bpy.data.objects.new(name, None)
            ob.empty_display_type = "ARROWS"
            ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
            LAYOUT.objects.link(ob)
            for k, v in p.items():
                ob[k] = v
            continue
        kind = leaf_kind(d)
        mesh = LEAF_MESH["Leaf_Kit"] if p.get("kind") == "stair door" else leaf_mesh(kind, p["width"], p["height"])
        ob = bpy.data.objects.new(name, mesh)
        ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
        DOORS.objects.link(ob)
        leaves[name] = ob
        if "room" in p:
            door_number(ob, p["room"], p["width"])
        for k, v in p.items():
            ob[k] = v
    return leaves


def door_number(leaf, num, width):
    """The room's brass number on the corridor face, on the lock rail between the middle and top panels: a child node of the leaf."""
    bm = bmesh.new()
    me = text_mesh(num, 0.075, 0.0025, 1.05)
    tmp = bmesh.new()
    tmp.from_mesh(me)
    bpy.data.meshes.remove(me)
    M = Matrix(((1, 0, 0, (width - 0.006) / 2), (0, 0, -1, -0.05 - 0.0026), (0, 1, 0, 1.59), (0, 0, 0, 1)))   # text x -> +X, up -> +Z, toward the reader -> -Y
    bmesh.ops.transform(tmp, matrix=M, verts=tmp.verts)
    m2 = bpy.data.meshes.new("n")
    tmp.to_mesh(m2)
    tmp.free()
    bm.from_mesh(m2)
    bpy.data.meshes.remove(m2)
    bm.loops.layers.uv.new("UVMap")
    box_uv_local(bm, 0.1)
    me = bpy.data.meshes.new(f"DoorNum_{num}")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS["Leaf_Brass"])
    ob = bpy.data.objects.new(f"DoorNum_{num}", me)
    DOORS.objects.link(ob)
    ob.parent = leaf
    ob.matrix_parent_inverse = Matrix.Identity(4)
    return ob


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


# ---------------------------------------------------------------- shared dressing
def sconce(w, a, tag, dead=False, coll=None, y=None, power=None):
    """A brass wall sconce: an upright backplate, a swan-neck arm, a candle cup and a cream fabric shade (Lamp_Emit). Every part above 1.8 m."""
    y = y or SK.SCONCE_Y
    coll = coll or PROPS
    part(f"Sconce_{tag}_Plate", "Brass", lambda bm: (w.box(bm, a - 0.05, a + 0.05, y - 0.15, y + 0.02, 0.0, 0.012),
                                                       w.box(bm, a - 0.03, a + 0.03, y - 0.13, y - 0.07, 0.012, 0.02)), coll)
    part(f"Sconce_{tag}_Arm", "Brass", lambda bm: (cyl(bm, w.pt(a, y - 0.1, 0.018), w.pt(a, y - 0.1, 0.11), 0.008, seg=10),
                                                     cyl(bm, w.pt(a, y - 0.1, 0.11), w.pt(a, y - 0.07, 0.15), 0.008, seg=10)), coll)
    part(f"Sconce_{tag}_Cup", "Brass", lambda bm: cyl(bm, w.pt(a, y - 0.075, 0.15), w.pt(a, y - 0.05, 0.15), 0.03, 0.022, seg=14), coll)
    part(f"Sconce_{tag}_Shade", "Lamp_Dead" if dead else "Lamp_Emit",
         lambda bm: tube(bm, w.pt(a, y - 0.07, 0.15), w.pt(a, y + 0.075, 0.15), 0.095, 0.062, seg=28), coll, recalc=False)
    if not dead:
        light(f"L_sconce_{tag}", "POINT", w.pt(a, y - 0.005, 0.15), power or SCONCE_W, size=0.03)


def door_casing(w, a, half, top, tag, mat="Trim_Wood", width=0.09, proud=0.022, cap=True):
    part(f"Casing_{tag}_L", mat, lambda bm: w.box(bm, a - half - width, a - half, 0.0, top + width, 0.0, proud))
    part(f"Casing_{tag}_R", mat, lambda bm: w.box(bm, a + half, a + half + width, 0.0, top + width, 0.0, proud))
    part(f"Casing_{tag}_Head", mat, lambda bm: w.box(bm, a - half - width, a + half + width, top, top + width, 0.0, proud))
    if cap:                                              # a moulded cap over the head
        part(f"Casing_{tag}_Cap", mat, lambda bm: (w.box(bm, a - half - width - 0.03, a + half + width + 0.03, top + width, top + width + 0.035, 0.0, proud + 0.02),
                                                   w.box(bm, a - half - width - 0.015, a + half + width + 0.015, top + width + 0.035, top + width + 0.05, 0.0, proud + 0.01)))


def picture(w, a, y, wd, ht, tag, which, fw=0.05):
    """A framed landscape 3 cm off the wall: a gilt frame and one quarter of the landscape atlas."""
    part(f"Picture_{tag}_Frame", "Frame_Gilt", lambda bm: (w.box(bm, a - wd / 2, a + wd / 2, y - ht / 2, y - ht / 2 + fw, 0, 0.035),
                                                             w.box(bm, a - wd / 2, a + wd / 2, y + ht / 2 - fw, y + ht / 2, 0, 0.035),
                                                             w.box(bm, a - wd / 2, a - wd / 2 + fw, y - ht / 2, y + ht / 2, 0, 0.035),
                                                             w.box(bm, a + wd / 2 - fw, a + wd / 2, y - ht / 2, y + ht / 2, 0, 0.035)))
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    r, c = divmod(which % 4, 2)
    u0, v0 = c * 0.5, r * 0.5
    corners = [(a - wd / 2 + fw, y - ht / 2 + fw), (a + wd / 2 - fw, y - ht / 2 + fw), (a + wd / 2 - fw, y + ht / 2 - fw), (a - wd / 2 + fw, y + ht / 2 - fw)]
    R = w.right()
    vs = [bm.verts.new(B(w.pt(aa, yy, 0.012))) for aa, yy in corners]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.dot(B(w.normal())) < 0:
        f.normal_flip()
    for lp in f.loops:
        p = lp.vert.co
        g = (p.x, p.z, -p.y)
        along = g[0] if w.axis == "z" else g[2]
        t = (along - (a - wd / 2 + fw)) / (wd - 2 * fw)
        if (R[0] if w.axis == "z" else R[2]) < 0:
            t = 1 - t
        s = (g[1] - (y - ht / 2 + fw)) / (ht - 2 * fw)
        lp[uvl].uv = (u0 + 0.5 * t, v0 + 0.5 * s)
    finish(f"Picture_{tag}", bm, "Picture", PROPS, keep_uv=True)


def sign_plate(w, a, y, wd, ht, text, tag, plate="Brass", ink="Plastic_Black"):
    part(f"Sign_{tag}", plate, lambda bm: w.box(bm, a - wd / 2, a + wd / 2, y - ht / 2, y + ht / 2, 0.0, 0.01))
    part(f"Sign_{tag}_t", ink, lambda bm: wall_text(bm, w, text, a, y, 0.01, ht * 0.5, 0.002, 1.05))


def exit_sign(w, a, y0, tag):
    """A wall-mounted EXIT sign over a door: a white housing, a red-lit face (Emergency_Emit) with the letters standing out of it."""
    part(f"Exit_{tag}_Housing", "Plastic_White", lambda bm: w.box(bm, a - 0.18, a + 0.18, y0, y0 + 0.2, 0.0, 0.05))
    part(f"Exit_{tag}_Face", "Plastic_Black", lambda bm: w.box(bm, a - 0.165, a + 0.165, y0 + 0.015, y0 + 0.185, 0.05, 0.052))
    part(f"Exit_{tag}_Letters", "Emergency_Emit", lambda bm: wall_text(bm, w, "EXIT", a, y0 + 0.1, 0.052, 0.11, 0.004, 1.1))


def decal(name, mat, x, z, s, y, down=False, rot=0.0):
    """An alpha decal quad on the floor or the ceiling, its UVs the whole stain image."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    c, sn = math.cos(rot), math.sin(rot)
    pts, uvs = [], []
    for u, v in ((0, 0), (1, 0), (1, 1), (0, 1)):
        dx, dz = (u - 0.5) * s, (v - 0.5) * s
        pts.append((x + dx * c - dz * sn, y, z + dx * sn + dz * c))
        uvs.append((u, v))
    vs = [bm.verts.new(B(p)) for p in pts]
    f = bm.faces.new(vs)
    f.normal_update()
    if (f.normal.z < 0) != down:
        f.normal_flip()
    for lp in f.loops:
        lp[uvl].uv = uvs[vs.index(lp.vert)]
    finish(name, bm, mat, PROPS, keep_uv=True)


def recess_box(w, x0, x1, y0, y1, depth, mat, tag):
    """The lining of a recess in the wall: its two sides, head, sill and back, inside the wall's thickness."""
    part(f"Recess_{tag}", mat, lambda bm: (w.box(bm, x0, x0 + 0.01, y0, y1, -depth, 0.0), w.box(bm, x1 - 0.01, x1, y0, y1, -depth, 0.0),
                                           w.box(bm, x0, x1, y1 - 0.01, y1, -depth, 0.0), w.box(bm, x0, x1, max(y0, 0.0), max(y0, 0.0) + 0.01, -depth, 0.0),
                                           w.box(bm, x0, x1, y0, y1, -depth - 0.01, -depth)))


def extinguisher(w, x0, x1, y0, y1, depth):
    """A semi-recessed fire extinguisher cabinet: a red frame 2 cm proud, a glazed door, the extinguisher inside, a FIRE label over it."""
    recess_box(w, x0, x1, y0, y1, depth, "Plastic_White", "ext")
    a = (x0 + x1) / 2
    part("Ext_Frame", "Red_Paint", lambda bm: (w.box(bm, x0 - 0.025, x0 + 0.01, y0 - 0.025, y1 + 0.025, 0.0, 0.02),
                                               w.box(bm, x1 - 0.01, x1 + 0.025, y0 - 0.025, y1 + 0.025, 0.0, 0.02),
                                               w.box(bm, x0, x1, y1 - 0.01, y1 + 0.025, 0.0, 0.02), w.box(bm, x0, x1, y0 - 0.025, y0 + 0.01, 0.0, 0.02)))
    part("Ext_Glass", "Glass_Clear", lambda bm: w.box(bm, x0 + 0.01, x1 - 0.01, y0 + 0.01, y1 - 0.01, 0.012, 0.016))
    part("Ext_Body", "Red_Paint", lambda bm: cyl(bm, w.pt(a, y0 + 0.04, -depth + 0.075), w.pt(a, y0 + 0.5, -depth + 0.075), 0.065, seg=20))
    part("Ext_Head", "Plastic_Black", lambda bm: (cyl(bm, w.pt(a, y0 + 0.5, -depth + 0.075), w.pt(a, y0 + 0.58, -depth + 0.075), 0.022, seg=12),
                                                  w.box(bm, a - 0.07, a + 0.02, y0 + 0.56, y0 + 0.58, -depth + 0.06, -depth + 0.09)))
    part("Ext_Label", "Red_Paint", lambda bm: w.box(bm, x0 - 0.02, x1 + 0.02, y1 + 0.05, y1 + 0.14, 0.0, 0.006))
    part("Ext_Label_t", "Plastic_White", lambda bm: wall_text(bm, w, "FIRE", a, y1 + 0.095, 0.006, 0.055, 0.002, 1.1))


def wainscot_panels(w, runs, y0, y1, tag, mat="Trim_Cream", pw=0.9):
    """Moulded panel frames on a wainscot, between y0 and y1, along each run (a0, a1): one frame per `pw` metres or so."""
    def build(bm):
        q = 0.03
        for a0, a1 in runs:
            L = a1 - a0 - 0.16
            if L < 0.3:
                continue
            n = max(1, int(round(L / pw)))
            step = L / n
            for k in range(n):
                b0 = a0 + 0.08 + k * step + 0.04
                b1 = b0 + step - 0.08
                w.box(bm, b0, b1, y0, y0 + q, 0.0, 0.012)
                w.box(bm, b0, b1, y1 - q, y1, 0.0, 0.012)
                w.box(bm, b0, b0 + q, y0 + q, y1 - q, 0.0, 0.012)
                w.box(bm, b1 - q, b1, y0 + q, y1 - q, 0.0, 0.012)
    part(f"Panels_{tag}", mat, build)


def rails(w, runs, tag, dado, top, skirt_mat="Skirting", rail_mat="Trim_Cream", cornice=True):
    """Skirting, the dado rail and the cornice along a wall's runs."""
    for i, (a0, a1) in enumerate(runs):
        if a1 - a0 < 0.02:
            continue
        part(f"Skirting_{tag}_{i}", skirt_mat, lambda bm: (w.box(bm, a0, a1, 0.0, 0.16, 0.0, 0.016), w.box(bm, a0, a1, 0.16, 0.18, 0.0, 0.01)))
        part(f"Dado_{tag}_{i}", rail_mat, lambda bm: (w.box(bm, a0, a1, dado - 0.03, dado + 0.035, 0.0, 0.024), w.box(bm, a0, a1, dado - 0.045, dado - 0.03, 0.0, 0.012)))


def cornice(w, a0, a1, top, tag):
    part(f"Cornice_{tag}", "Trim_Cream", lambda bm: (w.box(bm, a0, a1, top - 0.1, top, 0.0, 0.03), w.box(bm, a0, a1, top - 0.04, top, 0.03, 0.07),
                                                     w.box(bm, a0, a1, top - 0.13, top - 0.1, 0.0, 0.012)))


def cut_runs(a0, a1, holes):
    runs, a = [], a0
    for h0, h1 in sorted(holes):
        if h0 > a:
            runs.append((a, h0))
        a = max(a, h1)
    if a < a1:
        runs.append((a, a1))
    return runs


# ---------------------------------------------------------------- the corridor's dressing
def wall_runs(side, M):
    """The corridor wall's runs between openings along `side` (N or S): [(a0, a1)], for the skirting, the dado rail and the panels."""
    holes = []
    for num, lay, s, a in SK.room_doors(M):
        if s == side:
            holes.append((a - GB.DOOR_W / 2 - 0.09, a + GB.DOOR_W / 2 + 0.09))
    for did, s, a in SK.scene_doors(M):
        if s == side:
            holes.append((a - GB.DOOR_W / 2 - 0.09, a + GB.DOOR_W / 2 + 0.09))
    for kind, s, a in SK.features(M):
        if s == side:
            hw = 0.4 + 0.07 if kind == "closet" else 0.6
            holes.append((a - hw, a + hw))
    for what, s, x0, x1, y0, y1, d in SK.recesses(SCENE):
        if s == side:
            holes.append((x0 - 0.04, x1 + 0.04))
    return cut_runs(-GB.CORR_X, GB.CORR_X, holes)


SCENE_LABEL = {"dining": "DINING ROOM", "reception": "RECEPTION", "key_room": "KEY ROOM"}


def build_corridor(M):
    X, Z, H = GB.CORR_X, GB.CORR_Z, GB.CORR_H
    lower = SK.is_lower(M)
    for side in ("N", "S"):
        w = corridor_wall(side)
        runs = wall_runs(side, M)
        rails(w, runs, side, SK.CHAIR, H)
        wainscot_panels(w, [r for r in runs if r[1] - r[0] > 0.6], 0.26, SK.CHAIR - 0.12, side)
        cornice(w, -X, X, H, side)
    for side in ("E", "W"):
        w = corridor_wall(side)
        gap = SK.SW / 2 + 0.09 if side == "E" else (0.6 + 0.02 if lower else 0.0)
        runs = [(-Z, -gap), (gap, Z)] if gap else [(-Z, Z)]
        rails(w, runs, side, SK.CHAIR, H)
        cornice(w, -Z, Z, H, side)
    # room doors and the key rooms' doors: casings (the leaves and their numbers are build_leaves'); a brass plaque over a key room's door
    for num, lay, side, a in SK.room_doors(M):
        door_casing(corridor_wall(side), a, GB.DOOR_W / 2, GB.DOOR_H, f"room_{num}")
    for did, side, a in SK.scene_doors(M):
        w = corridor_wall(side)
        door_casing(w, a, GB.DOOR_W / 2, GB.DOOR_H, did)
        sign_plate(w, a, 2.43, 0.62 if did != "key_room" else 0.5, 0.11, SCENE_LABEL[did], f"to_{did}")
    for kind, side, a in SK.features(M):
        w = corridor_wall(side)
        if kind == "closet":
            door_casing(w, a, 0.4, GB.DOOR_H, f"closet_{side}{int(a)}", width=0.07, cap=False)
            sign_plate(w, a, 2.32, 0.24, 0.07, "STAFF", f"closet_{side}{int(a)}")
            alcove_light(side, a, f"closet_{side}{int(a)}", dead=True)
            part(f"ClosetShelf_{side}{int(a)}", "Closet_Paint", lambda bm, side=side, a=a: closet_shelf(bm, side, a))
        elif SCENE == "floor_2_lower" and side == "S" and a == 12.0 or SCENE == "floor_2_upper" and side == "N" and a == 4.0:
            console_alcove(side, a)
        else:
            alcove_dress(side, a)
    # the east end: the kit's stair door (its leaf is the kit's), a casing, a STAIRS plaque, the EXIT sign
    we = corridor_wall("E")
    door_casing(we, 0.0, SK.SW / 2, GB.DOOR_H, "stairdoor")
    exit_sign(we, 0.0, 2.42, "corridor")
    wn = corridor_wall("N")
    sign_plate(wn, 19.42, 1.55, 0.44, 0.13, "STAIRS", "stairs")
    for side, x, dead in SK.sconces(SCENE, M):
        sconce(corridor_wall(side), x, f"{side}{int(x):+d}", dead)
    for i, (side, a) in enumerate(SK.pictures(SCENE, M)):
        picture(corridor_wall(side), a, 1.62, 0.86, 0.64, f"{side}{int(a):+d}", i + (0 if lower else 2))
    for x in (-15.0, -5.0, 5.0, 15.0):
        part(f"Smoke_{int(x):+d}", "Plastic_White", lambda bm, x=x: cyl(bm, (x, H - 0.035, 0.0), (x, H, 0.0), 0.065, seg=20))
    stains = [(-15.7, 0.3, 0.9), (-7.3, -0.4, 1.3), (2.2, 0.2, 0.8), (10.6, -0.1, 1.6), (18.4, 0.4, 1.0)] if lower else \
             [(-18.4, -0.3, 1.1), (-10.1, 0.4, 0.8), (-0.2, -0.2, 1.5), (8.7, 0.1, 1.0), (15.4, -0.4, 0.9)]
    for i, (x, z, s) in enumerate(stains):
        decal(f"decor_stain_ceiling_{i}", "Decal_Ceiling", x, z, s, H - 0.003, down=True, rot=i * 1.3)
    fl = [(-13.8, 0.25, 0.6), (-1.6, -0.3, 0.5), (7.9, 0.4, 0.6)] if lower else [(-15.9, 0.2, 0.6), (-4.6, -0.35, 0.7), (11.8, 0.3, 0.5)]
    for i, (x, z, s) in enumerate(fl):
        decal(f"decor_stain_floor_{i}", "Decal_Floor", x, z, s, 0.003, rot=i * 2.1)
    for what, side, x0, x1, y0, y1, d in SK.recesses(SCENE):
        extinguisher(corridor_wall(side), x0, x1, y0, y1, d)
    if lower:
        sign_plate(corridor_wall("S"), -17.3, 1.55, 0.7, 0.13, "201 - 210  >", "dir")
        stairwell_lower(M)
    else:
        sign_plate(corridor_wall("N"), 17.3, 1.55, 0.7, 0.13, "<  211 - 220", "dir")
        picture(corridor_wall("W"), 0.0, 1.62, 1.1, 0.8, "end", 1)
        landing_upper()


def closet_shelf(bm, side, a):
    sg = -1 if side == "N" else 1
    zb = sg * (GB.CORR_Z + GB.T + 1.0)
    z0, z1 = sorted((zb, zb - sg * 0.4))
    cube(bm, (a - 0.6, 1.9, z0), (a + 0.6, 1.92, z1))


def alcove_light(side, a, tag, dead=False):
    """A small ceiling fitting in an alcove or closet (2.4 m): an opal glass bowl on a brass rose."""
    sg = -1 if side == "N" else 1
    zc = sg * (GB.CORR_Z + GB.T + 0.5)
    part(f"AlcoveLight_{tag}", "Lamp_Dead" if dead else "Lamp_Emit", lambda bm: cyl(bm, (a, 2.32, zc), (a, 2.4, zc), 0.1, 0.14, seg=20))
    part(f"AlcoveRose_{tag}", "Brass", lambda bm: cyl(bm, (a, 2.39, zc), (a, 2.4, zc), 0.16, seg=20))
    if not dead:
        light(f"L_alcove_{tag}", "POINT", (a, 2.28, zc), SCONCE_W * 0.45, size=0.06)


def alcove_dress(side, a):
    """An open alcove: carpet, the green wall, a coat hook rail above head height, a dim fitting in its ceiling."""
    sg = -1 if side == "N" else 1
    back = Wall("z", sg * (GB.CORR_Z + GB.T + 1.0), -sg)
    part(f"AlcoveRail_{side}{int(a)}", "Trim_Wood", lambda bm: back.box(bm, a - 0.5, a + 0.5, 1.84, 1.93, 0.0, 0.02))
    for k in range(4):
        x = a - 0.36 + k * 0.24
        part(f"AlcoveHook_{side}{int(a)}_{k}", "Brass", lambda bm, x=x: back.box(bm, x - 0.012, x + 0.012, 1.82, 1.87, 0.02, 0.07))
    part(f"AlcoveSkirt_{side}{int(a)}", "Skirting", lambda bm: back.box(bm, a - 0.6, a + 0.6, 0.0, 0.16, 0.0, 0.016))
    part(f"AlcoveDado_{side}{int(a)}", "Trim_Cream", lambda bm: back.box(bm, a - 0.6, a + 0.6, SK.CHAIR - 0.03, SK.CHAIR + 0.035, 0.0, 0.024))
    alcove_light(side, a, f"alcove_{side}{int(a)}")


def console_alcove(side, a):
    """The alcove with the console table (its collider is the greybox's Console): a demilune table 20 cm deep, a celadon vase with dried
    stems on it, a gilt mirror over it, a dim fitting."""
    sg = -1 if side == "N" else 1
    zb = sg * (GB.CORR_Z + GB.T + 1.0)
    back = Wall("z", zb, -sg)
    part(f"Console_Top", "Wood_Dark", lambda bm: back.box(bm, a - 0.45, a + 0.45, 0.78, 0.82, 0.0, 0.2))
    part(f"Console_Apron", "Wood_Dark", lambda bm: back.box(bm, a - 0.42, a + 0.42, 0.68, 0.78, 0.0, 0.18))
    part(f"Console_Legs", "Wood_Dark", lambda bm: [cyl(bm, back.pt(x, 0.0, 0.15), back.pt(x, 0.68, 0.15), 0.018, 0.026, seg=10) for x in (a - 0.38, a + 0.38)]
         + [cyl(bm, back.pt(x, 0.0, 0.03), back.pt(x, 0.68, 0.03), 0.018, 0.026, seg=10) for x in (a - 0.38, a + 0.38)])
    part(f"Console_Stretcher", "Wood_Dark", lambda bm: back.box(bm, a - 0.38, a + 0.38, 0.14, 0.17, 0.08, 0.1))
    vx, vd = a + 0.12, 0.1
    part(f"Console_Vase", "Porcelain_Celadon", lambda bm: (cyl(bm, back.pt(vx, 0.82, vd), back.pt(vx, 0.9, vd), 0.04, 0.075, seg=18),
                                                             cyl(bm, back.pt(vx, 0.9, vd), back.pt(vx, 1.02, vd), 0.075, 0.05, seg=18),
                                                             cyl(bm, back.pt(vx, 1.02, vd), back.pt(vx, 1.1, vd), 0.03, 0.04, seg=14)))
    rng = np.random.default_rng(int(a * 10) + 7)
    stems = [(vx + (rng.random() - 0.5) * 0.22, 1.32 + rng.random() * 0.22, vd + (rng.random() - 0.5) * 0.12) for _ in range(7)]
    part(f"Console_Stems", "Dried_Stems", lambda bm: [cyl(bm, back.pt(vx, 1.05, vd), back.pt(sx, sy, max(0.03, sd)), 0.0035, seg=5) for sx, sy, sd in stems]
         + [sphere(bm, back.pt(sx, sy, max(0.03, sd)), 0.018, seg=6) for sx, sy, sd in stems])
    part(f"Console_Box", "Wood_Dark", lambda bm: back.box(bm, a - 0.3, a - 0.12, 0.82, 0.88, 0.04, 0.16))
    part(f"Mirror_console", "Mirror", lambda bm: back.box(bm, a - 0.34, a + 0.34, 1.32, 2.12, 0.0, 0.008))
    part(f"Mirror_console_frame", "Frame_Gilt", lambda bm: (back.box(bm, a - 0.4, a + 0.4, 1.26, 1.32, 0.0, 0.03), back.box(bm, a - 0.4, a + 0.4, 2.12, 2.2, 0.0, 0.03),
                                                              back.box(bm, a - 0.4, a - 0.34, 1.32, 2.12, 0.0, 0.03), back.box(bm, a + 0.34, a + 0.4, 1.32, 2.12, 0.0, 0.03)))
    part(f"AlcoveSkirt_{side}{int(a)}", "Skirting", lambda bm: back.box(bm, a - 0.6, a + 0.6, 0.0, 0.16, 0.0, 0.016))
    alcove_light(side, a, f"alcove_{side}{int(a)}")


def stairwell_lower(M):
    """The stairwell behind the east door: painted block, concrete flights with steel nosings, a steel handrail on each wall, two bulkhead lights,
    the EXIT sign over the door at the top (to floor_2_upper), the floor's signs."""
    steps = sorted((b for b in M.boxes if b["name"].startswith("Step_")), key=lambda b: b["min"][0])
    x0, x1 = steps[0]["min"][0], steps[-1]["max"][0]
    for i, s in enumerate(steps):
        part(f"Nosing_{i:02d}", "Steel", lambda bm, s=s: cube(bm, (s["min"][0], s["max"][1] - 0.012, -0.99), (s["min"][0] + 0.05, s["max"][1] + 0.003, 0.99)))
    for zs, tag in ((-1.0, "N"), (1.0, "S")):
        w = Wall("z", zs, -1 if zs > 0 else 1)
        slope = (steps[-1]["max"][1] - 0.0) / (x1 - x0)

        def rail(bm, w=w, slope=slope):
            xa, xb = x0 + 0.1, x1 - 0.1
            cyl(bm, w.pt(xa, 0.9 + (xa - x0) * slope, 0.031), w.pt(xb, 0.9 + (xb - x0) * slope, 0.031), 0.016, seg=10)
            for k in range(4):
                xc = x0 + 0.3 + (x1 - x0 - 0.6) * k / 3
                w.box(bm, xc - 0.02, xc + 0.02, 0.86 + (xc - x0) * slope, 0.9 + (xc - x0) * slope, 0.0, 0.03)
        part(f"Handrail_{tag}", "Steel", rail)
    wn = Wall("z", -1.0, 1)
    part("Bulkhead_low", "Lamp_Emit", lambda bm: wn.box(bm, 20.55, 20.85, 2.3, 2.45, 0.0, 0.08))
    part("Bulkhead_low_cage", "Plastic_Black", lambda bm: wn.box(bm, 20.53, 20.87, 2.28, 2.3, 0.0, 0.085))
    light("L_stair_low", "POINT", wn.pt(20.7, 2.37, 0.12), STAIR_W, size=0.06)
    part("Bulkhead_top", "Lamp_Emit", lambda bm: wn.box(bm, 25.65, 25.95, 5.35, 5.5, 0.0, 0.08))
    part("Bulkhead_top_cage", "Plastic_Black", lambda bm: wn.box(bm, 25.63, 25.97, 5.33, 5.35, 0.0, 0.085))
    light("L_stair_top", "POINT", wn.pt(25.8, 5.42, 0.12), STAIR_W, size=0.06)
    we = Wall("x", 26.6, -1)
    exit_sign(we, 0.0, 5.42, "stairs")
    hw = SK.SW / 2
    part("Casing_stairs_up_Head", "Jamb_Steel", lambda bm: we.box(bm, -hw - 0.06, hw + 0.06, 3.2 + GB.DOOR_H, 3.2 + GB.DOOR_H + 0.06, 0.0, 0.015))
    part("Casing_stairs_up_L", "Jamb_Steel", lambda bm: we.box(bm, -hw - 0.06, -hw, 3.2, 3.2 + GB.DOOR_H + 0.06, 0.0, 0.015))
    part("Casing_stairs_up_R", "Jamb_Steel", lambda bm: we.box(bm, hw, hw + 0.06, 3.2, 3.2 + GB.DOOR_H + 0.06, 0.0, 0.015))
    wb = Wall("x", GB.CORR_X + GB.T, 1)                                  # the stairwell side of the kit's stair door
    part("Casing_stairdoor_back", "Jamb_Steel", lambda bm: (wb.box(bm, -hw - 0.06, -hw, 0.0, GB.DOOR_H + 0.06, 0.0, 0.015),
                                                             wb.box(bm, hw, hw + 0.06, 0.0, GB.DOOR_H + 0.06, 0.0, 0.015),
                                                             wb.box(bm, -hw - 0.06, hw + 0.06, GB.DOOR_H, GB.DOOR_H + 0.06, 0.0, 0.015)))
    ws = Wall("z", 1.0, -1)
    sign_plate(ws, 20.7, 1.56, 0.5, 0.3, "2", "floor", "Plastic_White")
    sign_plate(ws, 25.9, 4.7, 0.6, 0.3, "2U", "floor_top", "Plastic_White")


def landing_upper():
    """The small landing behind the upper level's stair door: painted block, a bulkhead light, a FLOOR sign and the start of the handrail down."""
    we = Wall("x", 21.6, -1)
    part("Bulkhead_land", "Lamp_Emit", lambda bm: we.box(bm, -0.15, 0.15, 2.3, 2.45, 0.0, 0.08))
    part("Bulkhead_land_cage", "Plastic_Black", lambda bm: we.box(bm, -0.17, 0.17, 2.28, 2.3, 0.0, 0.085))
    light("L_landing", "POINT", we.pt(0.0, 2.37, 0.12), STAIR_W * 0.8, size=0.06)
    sign_plate(we, 0.0, 1.5, 0.6, 0.3, "2U", "floor", "Plastic_White")
    part("Handrail_land", "Steel", lambda bm: (cyl(bm, (20.45, 0.92, -0.969), (21.55, 0.92, -0.969), 0.016, seg=10),
                                               cube(bm, (20.6, 0.88, -1.0), (20.64, 0.92, -0.97)), cube(bm, (21.4, 0.88, -1.0), (21.44, 0.92, -0.97))))
    exit_sign(Wall("x", 20.2, 1), 0.0, 2.27, "landing")


def corridor_standins():
    """For the bake only: a room behind the baked room leaf (its back face then gets a room's light, not the void)."""
    lf = BAKE_LEAF[SCENE]["Leaf_Room"]
    num = lf.split("_")[-1]
    M = SK.model(SCENE)
    d = next(x for x in M.doors if x["name"] == lf)
    a = float(d["props"]["room_x"])
    sgn = -1 if d["props"]["room_z"] < 0 else 1
    lay = d["props"]["room_layout"]
    x0, x1, z0, z1 = SK.room_dims(lay)
    zz0, zz1 = sorted((sgn * (GB.CORR_Z + GB.T), sgn * (GB.CORR_Z + GB.T - z0 - 0.2)))
    xx0, xx1 = (a + x0, a + x1) if sgn < 0 else (a - x1, a - x0)

    def room(bm):
        for mn, mx in (((xx0, -0.3, zz0), (xx1, 0.0, zz1)), ((xx0, 2.8, zz0), (xx1, 3.0, zz1)), ((xx0 - 0.2, 0, zz0), (xx0, 2.8, zz1)),
                       ((xx1, 0, zz0), (xx1 + 0.2, 2.8, zz1)), (((xx0, 0, zz0 - 0.2) if sgn < 0 else (xx0, 0, zz1)), ((xx1, 2.8, zz0) if sgn < 0 else (xx1, 2.8, zz1 + 0.2)))):
            cube(bm, mn, mx)
    part(f"standin_room_{num}", "Standin_Grey", room, BAKE_STANDIN)
    light(f"L_standin_room_{num}", "POINT", ((xx0 + xx1) / 2, 2.3, (zz0 + zz1) / 2), LAMP_W, size=0.1, coll=BAKE_STANDIN)


# ---------------------------------------------------------------- the key rooms (14 m by 10 m, 3 m high, the door to floor 2 in the south wall)
KWALLS = {"N": Wall("z", -SK.KZ, 1), "S": Wall("z", SK.KZ, -1), "W": Wall("x", -SK.KX, 1), "E": Wall("x", SK.KX, -1)}


def mbox(M, prefix):
    return [b for b in M.boxes if b["name"].startswith(prefix)]


def keyroom_shell(M, skip):
    """Skirting, the dado rail, the wainscot's panel frames and the cornice round the room; the door's casing. `skip`: {side: [(a0, a1)]} spans
    where furniture stands against the wall (no panels there)."""
    H, D = SK.KH, SK.KEY_DADO
    trim = "Wood_Dark" if SCENE == "key_room" else "Trim_Cream"
    for side, w in KWALLS.items():
        L = SK.KX if side in "NS" else SK.KZ
        holes = [(-GB.DOOR_W / 2 - 0.09, GB.DOOR_W / 2 + 0.09)] if side == "S" else []
        win = [(zc - SK.DWIN[0] / 2 - 0.05, zc + SK.DWIN[0] / 2 + 0.05) for s, zc in SK.DINING_WINDOWS if s == side] if SCENE == "dining" else []
        rails(w, cut_runs(-L, L, holes + win), side, D, H, rail_mat=trim)
        free = cut_runs(-L, L, holes + win + skip.get(side, []))
        wainscot_panels(w, [r for r in free if r[1] - r[0] > 0.6], 0.28, D - 0.14, side, trim, pw=1.1)
        cornice(w, -L, L, H, side)
    ws = KWALLS["S"]
    door_casing(ws, 0.0, GB.DOOR_W / 2, GB.DOOR_H, "door", "Trim_Wood")
    part("Switch", "Brass", lambda bm: ws.box(bm, 0.72, 0.8, 1.15, 1.27, 0.0, 0.01))


def keyroom_standin():
    """For the bake only: the corridor outside the door (its carpet, walls, ceiling and two sconces), so the leaf's back, the jambs and the
    threshold get a corridor's light, not the void."""
    Zs = SK.KZ + GB.T
    def room(bm):
        for mn, mx in (((-4.0, -0.3, Zs), (4.0, 0.0, Zs + 2.2)), ((-4.0, 2.8, Zs), (4.0, 3.0, Zs + 2.2)), ((-4.0, 0, Zs + 2.2), (4.0, 2.8, Zs + 2.4)),
                       ((-4.2, 0, Zs), (-4.0, 2.8, Zs + 2.2)), ((4.0, 0, Zs), (4.2, 2.8, Zs + 2.2))):
            cube(bm, mn, mx)
    part("standin_corridor", "SB_Wall", room, BAKE_STANDIN)
    for xx in (-2.0, 2.0):
        light(f"L_sb_sconce_{xx:+.0f}", "POINT", (xx, SK.SCONCE_Y, Zs + 0.15), SCONCE_W, size=0.03, coll=BAKE_STANDIN)


def build_keyroom(M):
    if SCENE == "dining":
        dining(M)
    elif SCENE == "reception":
        reception(M)
    else:
        key_room(M)
    keyroom_standin()
    part("Smoke", "Plastic_White", lambda bm: cyl(bm, (5.5, SK.KH - 0.035, 3.5), (5.5, SK.KH, 3.5), 0.065, seg=20))
    rng = np.random.default_rng({"dining": 41, "reception": 42, "key_room": 43}[SCENE])
    for i in range(4):
        x, z, s = -6 + rng.random() * 12, -4 + rng.random() * 8, 0.7 + rng.random() * 0.9
        decal(f"decor_stain_ceiling_{i}", "Decal_Ceiling", x, z, s, SK.KH - 0.003, down=True, rot=i * 1.7)


def chandelier(x, z, tag, arms=6, r=0.42, dead=False):
    """A brass chandelier: a chain and stem from a ceiling rose, a bowl, `arms` curved arms ending in candle cups with small cream shades
    (Lamp_Emit), every part above 2.2 m."""
    H = SK.KH
    part(f"Chand_{tag}_Rose", "Trim_Cream", lambda bm: (cyl(bm, (x, H - 0.03, z), (x, H, z), 0.32, seg=28), cyl(bm, (x, H - 0.05, z), (x, H - 0.03, z), 0.18, seg=24)))
    y = 2.42

    def brass(bm):
        cyl(bm, (x, y + 0.1, z), (x, H - 0.05, z), 0.012, seg=10)
        cyl(bm, (x, y - 0.06, z), (x, y + 0.1, z), 0.05, 0.09, seg=18)
        sphere(bm, (x, y - 0.09, z), 0.035, seg=10)
        for k in range(arms):
            a = 2 * math.pi * k / arms
            cx, cz = x + r * math.cos(a), z + r * math.sin(a)
            mx, mz = x + r * 0.55 * math.cos(a), z + r * 0.55 * math.sin(a)
            cyl(bm, (x, y, z), (mx, y - 0.05, mz), 0.009, seg=8)
            cyl(bm, (mx, y - 0.05, mz), (cx, y + 0.02, cz), 0.009, seg=8)
            cyl(bm, (cx, y + 0.02, cz), (cx, y + 0.05, cz), 0.03, 0.035, seg=12)
    part(f"Chand_{tag}_Brass", "Brass", brass)
    part(f"Chand_{tag}_Candles", "Candle", lambda bm: [cyl(bm, (x + r * math.cos(2 * math.pi * k / arms), y + 0.05, z + r * math.sin(2 * math.pi * k / arms)),
                                                           (x + r * math.cos(2 * math.pi * k / arms), y + 0.14, z + r * math.sin(2 * math.pi * k / arms)), 0.011, seg=8)
                                                       for k in range(arms)])
    part(f"Chand_{tag}_Shades", "Lamp_Dead" if dead else "Lamp_Emit",
         lambda bm: [tube(bm, (x + r * math.cos(2 * math.pi * k / arms), y + 0.09, z + r * math.sin(2 * math.pi * k / arms)),
                          (x + r * math.cos(2 * math.pi * k / arms), y + 0.2, z + r * math.sin(2 * math.pi * k / arms)), 0.065, 0.04, seg=16) for k in range(arms)],
         recalc=False)
    if not dead:
        light(f"L_chand_{tag}", "POINT", (x, y + 0.12, z), CHAND_W, size=r * 0.8)


def window_tall(w, a0, a1, y0, y1, depth, tag):
    """A tall sash window set into the wall, its panes dark (it looks onto nothing), a painted frame, glazing bars, a sill; heavy drapes on a
    pole either side, tied back (decor_), a pelmet over them."""
    recess_box(w, a0, a1, y0, y1, depth, "Window_Frame", f"win_{tag}")
    part(f"Win_{tag}_Void", "Window_Void", lambda bm: w.box(bm, a0 + 0.01, a1 - 0.01, y0 + 0.01, y1 - 0.01, -depth + 0.01, -depth + 0.02))
    am = (a0 + a1) / 2
    ym = (y0 + y1) / 2 + 0.1

    def bars(bm):
        w.box(bm, a0, a1, ym - 0.03, ym + 0.03, -depth + 0.02, -depth + 0.07)
        w.box(bm, am - 0.02, am + 0.02, y0, y1, -depth + 0.02, -depth + 0.06)
        for yy in (y0 + (ym - y0) / 2, ym + (y1 - ym) / 2):
            w.box(bm, a0, a1, yy - 0.012, yy + 0.012, -depth + 0.02, -depth + 0.05)
        for aa in (a0 + (am - a0) / 2, am + (a1 - am) / 2):
            w.box(bm, aa - 0.012, aa + 0.012, y0, y1, -depth + 0.02, -depth + 0.05)
    part(f"Win_{tag}_Bars", "Window_Frame", bars)
    part(f"Win_{tag}_Sill", "Window_Frame", lambda bm: w.box(bm, a0 - 0.08, a1 + 0.08, y0 - 0.04, y0, 0.0, 0.06))
    part(f"Win_{tag}_Pelmet", "Drape", lambda bm: w.box(bm, a0 - 0.45, a1 + 0.45, y1 + 0.02, y1 + 0.24, 0.0, 0.2))
    for k, (c0, c1) in enumerate(((a0 - 0.42, a0 + 0.12), (a1 - 0.12, a1 + 0.42))):
        def cur(bm, c0=c0, c1=c1, k=k):
            n = 20
            rng = np.random.default_rng(int(abs(a0) * 10) + k + 3)
            ph = rng.random() * 6
            tie = 1.05
            top, bot = [], []
            for i in range(n + 1):
                t = i / n
                aa = c0 + (c1 - c0) * t
                dd = 0.1 + 0.05 * math.sin(t * math.pi * 7 + ph)
                top.append(w.pt(aa, y1 + 0.02, dd))
                pinch = (c0 + c1) / 2 + (aa - (c0 + c1) / 2) * 0.35 + (0.08 if k == 0 else -0.08)
                bot.append(w.pt(pinch, tie, dd * 0.7 + 0.05))
            vt = [bm.verts.new(B(p)) for p in top]
            vb = [bm.verts.new(B(p)) for p in bot]
            vf = [bm.verts.new(B(w.pt(c0 + (c1 - c0) * (i / n), 0.02, 0.1 + 0.05 * math.sin(i / n * math.pi * 7 + ph)))) for i in range(n + 1)]
            for i in range(n):
                bm.faces.new((vb[i], vb[i + 1], vt[i + 1], vt[i]))
                bm.faces.new((vf[i], vf[i + 1], vb[i + 1], vb[i]))
        part(f"decor_drape_{tag}_{k}", "Drape", cur, tile=0.6, recalc=False)


def round_table(tx, tz, tag, settings):
    """A round dining table laid for a meal: a white cloth to the floor, chargers, plates and folded napkins, the
    cutlery, two glasses a place, a candlestick and a small bowl of dried flowers in the middle."""
    R, Ht = 0.6, 0.76
    part(f"Table_{tag}_Cloth", "Cloth_White", lambda bm: (cyl(bm, (tx, Ht - 0.012, tz), (tx, Ht, tz), R, seg=40), tube(bm, (tx, 0.015, tz), (tx, Ht - 0.012, tz), R + 0.025, R, seg=40)))
    china, silver, glass = [], [], []
    for sx in settings:
        px, pz = tx + sx * 0.4, tz
        china.append(((px, Ht, pz), (px, Ht + 0.012, pz), 0.13))
        china.append(((px, Ht + 0.012, pz), (px, Ht + 0.022, pz), 0.11))
        for k, dz in enumerate((-0.17, -0.2, 0.17, 0.2)):
            silver.append(((px - 0.08, Ht + 0.002, pz + dz - 0.006), (px + 0.1, Ht + 0.006, pz + dz + 0.006)))
        gx, gz = tx + sx * 0.24, tz + 0.16
        glass.append((gx, gz))
        glass.append((gx + sx * 0.03, gz + 0.09))
    part(f"Table_{tag}_Chargers", "Frame_Gilt", lambda bm: [cyl(bm, (tx + sx * 0.4, Ht, tz), (tx + sx * 0.4, Ht + 0.006, tz), 0.16, seg=28) for sx in settings])
    part(f"Table_{tag}_China", "China", lambda bm: [cyl(bm, a, b, r, seg=28) for a, b, r in china])
    part(f"Table_{tag}_Napkins", "Cloth_White", lambda bm: [cube(bm, (tx + sx * 0.4 - 0.05, Ht + 0.022, tz - 0.07), (tx + sx * 0.4 + 0.05, Ht + 0.06, tz + 0.07)) for sx in settings])
    part(f"Table_{tag}_Cutlery", "Silver", lambda bm: [cube(bm, a, b) for a, b in silver])
    part(f"Table_{tag}_Glasses", "Glass_Clear", lambda bm: [(cyl(bm, (gx, Ht, gz), (gx, Ht + 0.006, gz), 0.035, seg=12), cyl(bm, (gx, Ht + 0.006, gz), (gx, Ht + 0.09, gz), 0.005, seg=6),
                                                             cyl(bm, (gx, Ht + 0.09, gz), (gx, Ht + 0.19, gz), 0.03, 0.04, seg=14)) for gx, gz in glass])
    part(f"Table_{tag}_Stick", "Silver", lambda bm: (cyl(bm, (tx, Ht, tz - 0.12), (tx, Ht + 0.02, tz - 0.12), 0.05, seg=14), cyl(bm, (tx, Ht + 0.02, tz - 0.12), (tx, Ht + 0.24, tz - 0.12), 0.012, 0.018, seg=10)))
    part(f"Table_{tag}_Candle", "Candle", lambda bm: cyl(bm, (tx, Ht + 0.24, tz - 0.12), (tx, Ht + 0.4, tz - 0.12), 0.012, seg=10))
    part(f"Table_{tag}_Bowl", "China", lambda bm: cyl(bm, (tx, Ht, tz + 0.1), (tx, Ht + 0.06, tz + 0.1), 0.04, 0.07, seg=16))
    part(f"Table_{tag}_Posy", "Dried", lambda bm: [sphere(bm, (tx + 0.04 * math.cos(k * 1.3), Ht + 0.08 + 0.02 * (k % 2), tz + 0.1 + 0.04 * math.sin(k * 1.3)), 0.025, seg=6) for k in range(6)])


def dining_chair(cx, cz, face, tag):
    """A dining chair on its 45 cm collider, facing the table (face +1: toward +x): turned legs, a green upholstered seat, a carved back rail."""
    s = 0.21
    bx_ = cx - face * 0.2                                 # the back's x
    part(f"Chair_{tag}_Frame", "Wood_Dark", lambda bm: (
        [cyl(bm, (cx + dx, 0.0, cz + dz), (cx + dx, 0.44, cz + dz), 0.018, 0.022, seg=8) for dx in (-s + 0.02, s - 0.02) for dz in (-s + 0.02, s - 0.02)],
        cube(bm, (cx - s, 0.4, cz - s), (cx + s, 0.44, cz + s)),
        [cube(bm, (bx_ - 0.018, 0.44, cz + dz - 0.018), (bx_ + 0.018, 0.92, cz + dz + 0.018)) for dz in (-s + 0.02, s - 0.02)],
        cube(bm, (bx_ - 0.02, 0.8, cz - s + 0.02), (bx_ + 0.02, 0.9, cz + s - 0.02)),
        cube(bm, (bx_ - 0.012, 0.56, cz - 0.05), (bx_ + 0.012, 0.8, cz + 0.05))))
    part(f"Chair_{tag}_Seat", "Upholstery", lambda bm: cube(bm, (cx - s + 0.01, 0.44, cz - s + 0.01), (cx + s - 0.01, 0.48, cz + s - 0.01)))


def dining(M):
    """The dining room set for a meal nobody came to: six round tables in white cloths, their chairs, the long sideboard with the silver on it,
    three chandeliers, tall windows with drapes over darkness, landscapes, wall sconces."""
    material("Dried", color=srgb_lin("#8a6a4a"), rough=0.9)
    tables = mbox(M, "Table")
    chairs = mbox(M, "Chair")
    for i, t in enumerate(tables):
        tx, tz = (t["min"][0] + t["max"][0]) / 2, (t["min"][2] + t["max"][2]) / 2
        round_table(tx, tz, i, (-1, 1))
    for i, c in enumerate(chairs):
        cx, cz = (c["min"][0] + c["max"][0]) / 2, (c["min"][2] + c["max"][2]) / 2
        near = min(tables, key=lambda t: abs((t["min"][0] + t["max"][0]) / 2 - cx) + abs((t["min"][2] + t["max"][2]) / 2 - cz))
        face = 1 if (near["min"][0] + near["max"][0]) / 2 > cx else -1
        dining_chair(cx, cz, face, i)
    sb = mbox(M, "Buffet")[0]
    sideboard(sb)
    for k, x in enumerate((-4.0, 0.0, 4.0)):
        chandelier(x, 0.0, k)
    w, y0, y1, d = SK.DWIN
    for side, zc in SK.DINING_WINDOWS:
        window_tall(KWALLS[side], zc - w / 2, zc + w / 2, y0, y1, d, f"{side}{int(zc):+d}")
    for side in ("W", "E"):
        sconce(KWALLS[side], 0.0, f"{side}0", y=2.1, power=SCONCE_W * 0.8)
    ws = KWALLS["S"]
    for x in (-3.2, 3.2):
        sconce(ws, x, f"S{int(x):+d}", y=2.1, power=SCONCE_W * 0.8)
    for x, k in ((-5.3, 2), (5.3, 3)):
        picture(ws, x, 1.75, 0.9, 0.7, f"S{int(x):+d}", k)
    picture(KWALLS["N"], 0.0, 2.15, 2.2, 1.1, "N0", 0, fw=0.08)
    keyroom_shell(M, {"N": [(-5.1, 5.1)]})


def sideboard(b):
    """The long sideboard against the north wall, on its collider: three cabinets with panelled doors and brass pulls under one top, a white
    runner, silver domes, a tureen, stacked plates, two candelabra."""
    x0, x1, z0, z1, h = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]
    front = Wall("z", z1, 1)
    part("Sideboard_Body", "Wood_Dark", lambda bm: (cube(bm, (x0 + 0.02, 0.1, z0), (x1 - 0.02, h - 0.04, z1 - 0.03)), cube(bm, (x0, h - 0.04, z0), (x1, h, z1))))
    part("Sideboard_Plinth", "Wood_Dark", lambda bm: cube(bm, (x0 + 0.05, 0.0, z0), (x1 - 0.05, 0.1, z1 - 0.06)))
    n = 9
    seg = (x1 - x0 - 0.04) / n

    def doors(bm):
        for k in range(n):
            a0 = x0 + 0.02 + k * seg + 0.02
            a1 = a0 + seg - 0.04
            front.box(bm, a0, a1, 0.14, h - 0.24, -0.03, -0.012)
            front.box(bm, a0 + 0.06, a1 - 0.06, 0.2, h - 0.3, -0.012, -0.004)
            front.box(bm, a0, a1, h - 0.21, h - 0.07, -0.03, -0.012)
    part("Sideboard_Doors", "Wood_Dark", doors)
    part("Sideboard_Pulls", "Brass", lambda bm: [front.box(bm, x0 + 0.02 + (k + 0.5) * seg - 0.04, x0 + 0.02 + (k + 0.5) * seg + 0.04, h - 0.15, h - 0.13, -0.012, 0.01) for k in range(n)]
         + [front.box(bm, x0 + 0.02 + (k + 1) * seg - 0.06, x0 + 0.02 + (k + 1) * seg - 0.045, 0.5, 0.6, -0.012, 0.004) for k in range(n)])
    part("Sideboard_Runner", "Cloth_White", lambda bm: cube(bm, (x0 + 0.3, h, z0 + 0.15), (x1 - 0.3, h + 0.004, z1 - 0.12)))
    zc = (z0 + z1) / 2

    def silver(bm):
        for x in (-3.4, -1.2, 1.2, 3.4):
            cyl(bm, (x, h + 0.004, zc), (x, h + 0.02, zc), 0.2, seg=24)
            cyl(bm, (x, h + 0.02, zc), (x, h + 0.14, zc), 0.17, 0.12, seg=24)
            cyl(bm, (x, h + 0.14, zc), (x, h + 0.2, zc), 0.12, 0.03, seg=24)
            sphere(bm, (x, h + 0.215, zc), 0.022, seg=8)
        cyl(bm, (0.0, h + 0.004, zc), (0.0, h + 0.05, zc), 0.08, 0.06, seg=18)
        cyl(bm, (0.0, h + 0.05, zc), (0.0, h + 0.22, zc), 0.16, 0.15, seg=24)
        cyl(bm, (0.0, h + 0.22, zc), (0.0, h + 0.26, zc), 0.15, 0.05, seg=24)
        for x in (-4.5, 4.5):
            cyl(bm, (x, h + 0.004, zc), (x, h + 0.03, zc), 0.07, seg=16)
            cyl(bm, (x, h + 0.03, zc), (x, h + 0.36, zc), 0.014, 0.02, seg=10)
            for dx in (-0.12, 0.0, 0.12):
                cyl(bm, (x, h + 0.3, zc), (x + dx, h + 0.36, zc), 0.007, seg=6)
                cyl(bm, (x + dx, h + 0.36, zc), (x + dx, h + 0.39, zc), 0.016, seg=10)
    part("Sideboard_Silver", "Silver", silver)
    part("Sideboard_Candles", "Candle", lambda bm: [cyl(bm, (x + dx, h + 0.39, zc), (x + dx, h + 0.52, zc), 0.011, seg=8) for x in (-4.5, 4.5) for dx in (-0.12, 0.0, 0.12)])
    part("Sideboard_Plates", "China", lambda bm: [cyl(bm, (x, h + 0.004 + k * 0.014, zc - 0.05), (x, h + 0.016 + k * 0.014, zc - 0.05), 0.13, seg=24) for x in (-2.3, 2.3) for k in range(8)])


def reception(M):
    """The second, older reception: the long counter with its brass bell, the guest book and a banker's lamp, the pigeonhole key rack behind it
    with a key or a letter in most of its holes, a clock over the rack that stopped at 3:17, leather club chairs either side of the room."""
    d = mbox(M, "Front_Desk")[0]
    counter(d)
    cub = mbox(M, "Key_Cubbies")[0]
    cubbies(cub)
    for i, s in enumerate(mbox(M, "Sofa")):
        chair_group(s, i)
    wn = KWALLS["N"]
    CY = 2.63
    part("Clock_Case", "Wood_Dark", lambda bm: cyl(bm, wn.pt(0.0, CY, 0.0), wn.pt(0.0, CY, 0.06), 0.22, seg=36))
    part("Clock_Bezel", "Brass", lambda bm: tube(bm, wn.pt(0.0, CY, 0.06), wn.pt(0.0, CY, 0.075), 0.2, seg=36))
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    ring = [bm.verts.new(B(wn.pt(0.19 * math.cos(2 * math.pi * k / 36), CY + 0.19 * math.sin(2 * math.pi * k / 36), 0.062))) for k in range(36)]
    f = bm.faces.new(ring)
    f.normal_update()
    if f.normal.dot(B(wn.normal())) < 0:
        f.normal_flip()
    for lp in f.loops:
        k = ring.index(lp.vert)
        lp[uvl].uv = (0.5 + 0.5 * math.cos(2 * math.pi * k / 36), 0.5 + 0.5 * math.sin(2 * math.pi * k / 36))
    finish("Clock_Face", bm, "Clock_Face", PROPS, keep_uv=True)
    for side in ("W", "E"):
        for z in (-2.0, 1.0):
            sconce(KWALLS[side], z, f"{side}{int(z):+d}", y=2.15, power=SCONCE_W * 0.75)
    ws = KWALLS["S"]
    for x in (-2.6, 2.6):
        sconce(ws, x, f"S{int(x):+d}", y=2.15, power=SCONCE_W * 0.75)
    picture(KWALLS["W"], 2.9, 1.85, 1.0, 0.75, "W", 0)
    picture(KWALLS["E"], 2.9, 1.85, 1.0, 0.75, "E", 3)
    picture(ws, -5.0, 1.8, 0.8, 0.6, "S-5", 1)
    picture(ws, 5.0, 1.8, 0.8, 0.6, "S+5", 2)
    chandelier(0.0, 1.8, "hall", arms=5, r=0.36)
    chandelier(0.0, -2.6, "desk", arms=5, r=0.36)
    for x in (-5.6, 5.6):
        sconce(wn, x, f"N{int(x):+d}", y=2.15, power=SCONCE_W * 0.75)
    keyroom_shell(M, {"N": [(-4.1, 4.1)]})


def counter(d):
    """The front desk on its collider: a panelled wooden front toward the door, a marble top, a lower shelf on the clerk's side; a brass bell,
    the open guest book with a pen and an inkwell, a banker's lamp with a green glass shade (lit), a brass RECEPTION plate on the front."""
    x0, x1, z0, z1, h = d["min"][0], d["max"][0], d["min"][2], d["max"][2], d["max"][1]
    front = Wall("z", z1, 1)
    part("Counter_Body", "Wood_Dark", lambda bm: (cube(bm, (x0 + 0.02, 0.0, z1 - 0.06), (x1 - 0.02, h - 0.04, z1)),
                                                   cube(bm, (x0 + 0.02, 0.0, z0), (x0 + 0.06, h - 0.04, z1)), cube(bm, (x1 - 0.06, 0.0, z0), (x1 - 0.02, h - 0.04, z1)),
                                                   cube(bm, (x0 + 0.06, 0.66, z0), (x1 - 0.06, 0.7, z1 - 0.06)), cube(bm, (x0 + 0.06, 0.0, z0 + 0.1), (x1 - 0.06, 0.08, z1 - 0.06))))
    n = 8
    seg = (x1 - x0 - 0.04) / n

    def panels(bm):
        for k in range(n):
            a0 = x0 + 0.02 + k * seg + 0.04
            a1 = a0 + seg - 0.08
            for yy0, yy1 in ((0.14, 0.62), (0.7, h - 0.12)):
                q = 0.03
                front.box(bm, a0, a1, yy0, yy0 + q, 0.0, 0.012)
                front.box(bm, a0, a1, yy1 - q, yy1, 0.0, 0.012)
                front.box(bm, a0, a0 + q, yy0, yy1, 0.0, 0.012)
                front.box(bm, a1 - q, a1, yy0, yy1, 0.0, 0.012)
                front.box(bm, a0 + 0.06, a1 - 0.06, yy0 + 0.06, yy1 - 0.06, 0.0, 0.006)
        front.box(bm, x0, x1, 0.0, 0.1, 0.0, 0.02)
    part("Counter_Panels", "Wood_Dark", panels)
    part("Counter_Top", "Marble", lambda bm: cube(bm, (x0 - 0.02, h - 0.04, z0 - 0.02), (x1 + 0.02, h, z1 + 0.03)))
    part("Sign_counter", "Brass", lambda bm: front.box(bm, -0.38, 0.38, 0.86, 0.98, 0.012, 0.022))
    part("Sign_counter_t", "Plastic_Black", lambda bm: wall_text(bm, front, "RECEPTION", 0.0, 0.92, 0.022, 0.06, 0.002, 1.1))
    zc = (z0 + z1) / 2
    part("Bell", "Brass", lambda bm: (cyl(bm, (1.3, h, zc + 0.08), (1.3, h + 0.012, zc + 0.08), 0.05, seg=18), cyl(bm, (1.3, h + 0.012, zc + 0.08), (1.3, h + 0.05, zc + 0.08), 0.045, 0.02, seg=18),
                                      cyl(bm, (1.3, h + 0.05, zc + 0.08), (1.3, h + 0.07, zc + 0.08), 0.005, seg=6), sphere(bm, (1.3, h + 0.075, zc + 0.08), 0.008, seg=6)))
    bx_, bz = -0.6, zc + 0.02
    part("GuestBook_Cover", "Book_Cover", lambda bm: cube(bm, (bx_ - 0.27, h, bz - 0.18), (bx_ + 0.27, h + 0.012, bz + 0.18)))
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    vs = [bm.verts.new(B(p)) for p in ((bx_ - 0.25, h + 0.022, bz + 0.165), (bx_ + 0.25, h + 0.022, bz + 0.165), (bx_ + 0.25, h + 0.022, bz - 0.165), (bx_ - 0.25, h + 0.022, bz - 0.165))]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.z < 0:
        f.normal_flip()
    for lp in f.loops:
        i = vs.index(lp.vert)
        lp[uvl].uv = ((0, 0), (1, 0), (1, 1), (0, 1))[i]
    finish("GuestBook_Pages", bm, "Ledger_Page", PROPS, keep_uv=True)
    part("GuestBook_Block", "Ledger_Page", lambda bm: cube(bm, (bx_ - 0.25, h + 0.012, bz - 0.165), (bx_ + 0.25, h + 0.021, bz + 0.165)), tile=0.3)
    part("Pen", "Plastic_Black", lambda bm: cyl(bm, (bx_ + 0.3, h + 0.006, bz - 0.1), (bx_ + 0.44, h + 0.006, bz + 0.02), 0.005, seg=8))
    part("Inkwell", "Glass_Green", lambda bm: cube(bm, (bx_ + 0.36, h, bz + 0.1), (bx_ + 0.42, h + 0.05, bz + 0.16)))
    lx, lz = -2.3, zc
    part("Banker_Base", "Brass", lambda bm: (cube(bm, (lx - 0.1, h, lz - 0.06), (lx + 0.1, h + 0.02, lz + 0.06)), cyl(bm, (lx, h + 0.02, lz), (lx, h + 0.32, lz), 0.01, seg=8),
                                              cyl(bm, (lx - 0.16, h + 0.32, lz), (lx + 0.16, h + 0.32, lz), 0.01, seg=8)))
    part("Banker_Shade", "Glass_Green", lambda bm: tube(bm, (lx - 0.18, h + 0.36, lz), (lx + 0.18, h + 0.36, lz), 0.07, 0.07, seg=20))
    part("Banker_Bulb", "Lamp_Emit", lambda bm: cyl(bm, (lx - 0.12, h + 0.335, lz), (lx + 0.12, h + 0.335, lz), 0.02, seg=10))
    light("L_banker", "POINT", (lx, h + 0.3, lz), LAMP_W * 0.9, size=0.04)
    part("Ledger_Stack", "Book_Cover", lambda bm: [cube(bm, (2.2, h + k * 0.04, zc - 0.12), (2.55, h + (k + 1) * 0.04 - 0.004, zc + 0.12)) for k in range(3)])


def cubbies(b):
    """The pigeonhole key rack on its collider: a cupboard below, seven rows of thirty-two holes above, each with a numbered brass plate, most
    holding a key on a fob or a folded note; a cornice over it."""
    x0, x1, z0, z1, h = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]
    front = Wall("z", z1, 1)
    part("Cubby_Base", "Wood_Dark", lambda bm: (cube(bm, (x0, 0.0, z0), (x1, 0.88, z1 - 0.01)), cube(bm, (x0 - 0.02, 0.88, z0), (x1 + 0.02, 0.92, z1 + 0.02))))
    part("Cubby_BaseDoors", "Wood_Dark", lambda bm: [front.box(bm, x0 + 0.05 + k * 1.0, x0 + 0.95 + k * 1.0, 0.1, 0.8, -0.01, 0.006) for k in range(8)])
    part("Cubby_BasePulls", "Brass", lambda bm: [front.box(bm, x0 + 0.47 + k * 1.0, x0 + 0.53 + k * 1.0, 0.6, 0.62, 0.006, 0.02) for k in range(8)])
    ncol, nrow = 32, 7
    cw, chh = (x1 - x0) / ncol, (2.3 - 0.92) / nrow

    def grid(bm):
        cube(bm, (x0, 0.92, z0), (x1, 2.3, z0 + 0.02))
        for k in range(ncol + 1):
            xx = x0 + k * cw
            cube(bm, (xx - 0.008, 0.92, z0), (xx + 0.008, 2.3, z1 - 0.01))
        for r in range(nrow + 1):
            yy = 0.92 + r * chh
            cube(bm, (x0, yy - 0.008, z0), (x1, yy + 0.008, z1 - 0.01))
    part("Cubby_Grid", "Wood_Dark", grid)
    part("Cubby_Cornice", "Wood_Dark", lambda bm: (cube(bm, (x0 - 0.03, 2.3, z0), (x1 + 0.03, 2.36, z1 + 0.03)), cube(bm, (x0 - 0.05, 2.36, z0), (x1 + 0.05, h, z1 + 0.05))))
    items, keys, notes = [], [], []
    rng = np.random.default_rng(51)
    for r in range(nrow):
        for k in range(ncol):
            idx = (nrow - 1 - r) * ncol + k
            xc = x0 + (k + 0.5) * cw
            yb = 0.92 + r * chh
            items.append((idx, xc, yb + 0.012, cw * 0.62, 0.022))
            u = rng.random()
            if u < 0.55:
                keys.append((xc + (rng.random() - 0.5) * 0.06, yb + 0.03, z0 + 0.12 + rng.random() * 0.1))
            elif u < 0.75:
                notes.append((xc, yb, z0 + 0.06 + rng.random() * 0.12))
    plate_quads("Cubby_Plates", Wall("z", z1 - 0.01, 1), items, d=0.004)
    part("Cubby_Keys", "Brass", lambda bm: [(cube(bm, (x - 0.008, y + 0.012, z - 0.004), (x + 0.008, y + 0.07, z + 0.004)), cube(bm, (x - 0.02, y + 0.07, z - 0.004), (x + 0.02, y + 0.1, z + 0.004)))
                                             for x, y, z in keys])
    part("Cubby_Fobs", "Key_Tag_Red", lambda bm: [cube(bm, (x - 0.022, y + 0.008, z + 0.01), (x + 0.022, y + 0.016, z + 0.07)) for x, y, z in keys])
    part("Cubby_Notes", "Ledger_Page", lambda bm: [cube(bm, (x - 0.07, y + 0.008, z), (x + 0.07, y + 0.012 + 0.03 * ((i * 7) % 3), z + 0.1)) for i, (x, y, z) in enumerate(notes)], tile=0.3)


def chair_group(b, i):
    """Two leather club chairs and a tall side cabinet with a lamp between them, on the greybox's sofa collider, facing the counter (north)."""
    x0, x1, z0, z1 = b["min"][0], b["max"][0], b["min"][2], b["max"][2]
    wch = (x1 - x0 - 0.3) / 2
    for k, (a0, a1) in enumerate(((x0, x0 + wch), (x1 - wch, x1))):
        def club(bm, a0=a0, a1=a1):
            cube(bm, (a0 + 0.02, 0.06, z0 + 0.02), (a1 - 0.02, 0.4, z1 - 0.02))
            cube(bm, (a0 + 0.14, 0.4, z0 + 0.06), (a1 - 0.14, 0.5, z1 - 0.2))
            cube(bm, (a0 + 0.12, 0.4, z1 - 0.24), (a1 - 0.12, 0.8, z1 - 0.02))
            for aa, ab in ((a0, a0 + 0.14), (a1 - 0.14, a1)):
                cube(bm, (aa, 0.06, z0 + 0.02), (ab, 0.64, z1 - 0.02))
                cyl(bm, (aa, 0.64, z0 + 0.02), (ab, 0.64, z0 + 0.02), 0.05, seg=10)
        part(f"Club_{i}_{k}", "Leather", club)
        part(f"Club_{i}_{k}_Feet", "Wood_Dark", lambda bm, a0=a0, a1=a1: [cube(bm, (x - 0.025, 0.0, z - 0.025), (x + 0.025, 0.06, z + 0.025))
                                                                        for x in (a0 + 0.06, a1 - 0.06) for z in (z0 + 0.06, z1 - 0.06)])
    tx, tz = (x0 + x1) / 2, (z0 + z1) / 2
    part(f"SideTable_{i}", "Wood_Dark", lambda bm: (cube(bm, (tx - 0.14, 0.04, z0 + 0.03), (tx + 0.14, 0.77, z1 - 0.03)), cube(bm, (tx - 0.15, 0.77, z0 + 0.02), (tx + 0.15, 0.8, z1 - 0.02)),
                                                     [cube(bm, (x - 0.02, 0.0, z - 0.02), (x + 0.02, 0.04, z + 0.02)) for x in (tx - 0.11, tx + 0.11) for z in (z0 + 0.06, z1 - 0.06)]))
    part(f"SideTable_{i}_Pull", "Brass", lambda bm: cube(bm, (tx - 0.03, 0.42, z0 + 0.01), (tx + 0.03, 0.44, z0 + 0.03)))
    part(f"SideLamp_{i}", "Brass", lambda bm: (cyl(bm, (tx, 0.8, tz), (tx, 0.82, tz), 0.06, seg=14), cyl(bm, (tx, 0.82, tz), (tx, 1.05, tz), 0.012, seg=8)))
    part(f"SideLamp_{i}_Shade", "Lamp_Emit", lambda bm: tube(bm, (tx, 1.0, tz), (tx, 1.17, tz), 0.13, 0.09, seg=24), recalc=False)
    light(f"L_sidelamp_{i}", "POINT", (tx, 1.08, tz), LAMP_W, size=0.04)


def key_room(M):
    """The room for keys: walls of numbered hooks with keys on them, a bank of key cabinets over card-index drawers, a locked cage round the
    safe, a heavy desk with the open ledger, and one lamp, a green enamel pendant over the desk."""
    t = mbox(M, "Table")[0]
    desk(t)
    hooks_board(Wall("z", -SK.KZ, 1), -4.0, 4.0, 1.0, 2.2, 0.1, "N", 0, 32)
    hooks_board(Wall("x", SK.KX, -1), 3.0, -2.0, 1.0, 2.2, 0.1, "E", 32 * 4, 20)
    cabinets(mbox(M, "Key_Cabinets")[0])
    cage(mbox(M, "Key_Cage")[0], mbox(M, "Safe")[0])
    ws = KWALLS["S"]
    sign_plate(ws, -3.0, 1.7, 0.9, 0.16, "KEYS SIGNED FOR", "rule")
    keyroom_shell(M, {"N": [(-4.1, 4.1)], "W": [(-3.1, 3.1)], "E": [(-5.0, 3.1)]})


def desk(t):
    """The heavy desk on its collider: a thick top with a leather writing panel, deep drawers on the clerk's side, turned legs; the open
    ledger, a pen tray, an inkwell, a ring of loose keys, a brass key box; the room's one lamp hangs over it."""
    x0, x1, z0, z1, h = t["min"][0], t["max"][0], t["min"][2], t["max"][2], t["max"][1]
    part("Desk_Top", "Wood_Dark", lambda bm: cube(bm, (x0, h - 0.06, z0), (x1, h, z1)))
    part("Desk_Leather", "Leather", lambda bm: cube(bm, (x0 + 0.25, h, z0 + 0.25), (x1 - 0.25, h + 0.003, z1 - 0.25)))
    part("Desk_Legs", "Wood_Dark", lambda bm: [cyl(bm, (x, 0.0, z), (x, h - 0.06, z), 0.045, 0.055, seg=12) for x in (x0 + 0.08, x1 - 0.08) for z in (z0 + 0.08, z1 - 0.08)])
    part("Desk_Apron", "Wood_Dark", lambda bm: (cube(bm, (x0 + 0.06, h - 0.22, z0 + 0.06), (x1 - 0.06, h - 0.06, z0 + 0.09)), cube(bm, (x0 + 0.06, h - 0.22, z1 - 0.09), (x1 - 0.06, h - 0.06, z1 - 0.06)),
                                                 cube(bm, (x0 + 0.06, h - 0.22, z0 + 0.09), (x0 + 0.09, h - 0.06, z1 - 0.09)), cube(bm, (x1 - 0.09, h - 0.22, z0 + 0.09), (x1 - 0.06, h - 0.06, z1 - 0.09))))
    part("Desk_Drawers", "Wood_Dark", lambda bm: [cube(bm, (x0 + 0.2 + k * 0.9, h - 0.2, z0 + 0.04), (x0 + 0.9 + k * 0.9, h - 0.08, z0 + 0.06)) for k in range(3)])
    part("Desk_Pulls", "Brass", lambda bm: [cube(bm, (x0 + 0.5 + k * 0.9, h - 0.15, z0 + 0.025), (x0 + 0.6 + k * 0.9, h - 0.13, z0 + 0.04)) for k in range(3)])
    bx_, bz = 0.0, 0.1
    part("Ledger_Cover", "Book_Cover", lambda bm: cube(bm, (bx_ - 0.36, h + 0.003, bz - 0.24), (bx_ + 0.36, h + 0.016, bz + 0.24)))
    part("Ledger_Block", "Ledger_Page", lambda bm: cube(bm, (bx_ - 0.34, h + 0.016, bz - 0.225), (bx_ + 0.34, h + 0.03, bz + 0.225)), tile=0.3)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    vs = [bm.verts.new(B(p)) for p in ((bx_ - 0.34, h + 0.031, bz + 0.225), (bx_ + 0.34, h + 0.031, bz + 0.225), (bx_ + 0.34, h + 0.031, bz - 0.225), (bx_ - 0.34, h + 0.031, bz - 0.225))]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.z < 0:
        f.normal_flip()
    for lp in f.loops:
        lp[uvl].uv = ((0, 0), (1, 0), (1, 1), (0, 1))[vs.index(lp.vert)]
    finish("Ledger_Pages", bm, "Ledger_Page", PROPS, keep_uv=True)
    part("Desk_Pen", "Plastic_Black", lambda bm: cyl(bm, (0.42, h + 0.008, -0.05), (0.56, h + 0.008, 0.1), 0.005, seg=8))
    part("Desk_Ink", "Glass_Green", lambda bm: cube(bm, (0.5, h, 0.2), (0.57, h + 0.06, 0.27)))
    part("Desk_KeyBox", "Brass", lambda bm: (cube(bm, (-1.0, h, -0.5), (-0.7, h + 0.08, -0.3)), cube(bm, (-1.0, h + 0.08, -0.5), (-0.7, h + 0.09, -0.29))))

    def ring(bm):
        cx, cz = 0.7, -0.45
        for k in range(16):
            a0, a1 = 2 * math.pi * k / 16, 2 * math.pi * (k + 1) / 16
            cyl(bm, (cx + 0.05 * math.cos(a0), h + 0.005, cz + 0.05 * math.sin(a0)), (cx + 0.05 * math.cos(a1), h + 0.005, cz + 0.05 * math.sin(a1)), 0.003, seg=5)
        for k in range(5):
            a = 0.6 + k * 0.5
            px, pz = cx + 0.05 * math.cos(a), cz + 0.05 * math.sin(a)
            cube(bm, (px - 0.006, h + 0.002, pz - 0.006), (px + 0.006 + 0.07 * math.cos(a), h + 0.006, pz + 0.006 + 0.07 * math.sin(a)))
    part("Desk_KeyRing", "Brass", ring)
    # the one lamp: a green enamel pendant on a cord, low over the desk
    py = 2.3
    part("Pendant_Cord", "Plastic_Black", lambda bm: cyl(bm, (0.0, py + 0.12, 0.0), (0.0, SK.KH, 0.0), 0.005, seg=6))
    part("Pendant_Rose", "Plastic_Black", lambda bm: cyl(bm, (0.0, SK.KH - 0.025, 0.0), (0.0, SK.KH, 0.0), 0.06, seg=16))
    part("Pendant_Shade", "Safe_Paint", lambda bm: (tube(bm, (0.0, py - 0.02, 0.0), (0.0, py + 0.08, 0.0), 0.32, 0.12, seg=32), cyl(bm, (0.0, py + 0.08, 0.0), (0.0, py + 0.12, 0.0), 0.12, 0.04, seg=24)),
         recalc=False)
    part("Pendant_Bulb", "Lamp_Emit", lambda bm: sphere(bm, (0.0, py - 0.02, 0.0), 0.05, seg=12))
    light("L_pendant", "POINT", (0.0, py - 0.05, 0.0), PENDANT_W, size=0.08)


def hooks_board(w, a0, a1, y0, y1, depth, tag, start, per_row):
    """A board of numbered hooks on a wall: four rows of `per_row` brass hooks, a numbered plate over each (Plates cell start + k), a key with
    a tag on most of them."""
    lo, hi = min(a0, a1), max(a0, a1)
    part(f"Hooks_{tag}_Board", "Wood_Dark", lambda bm: (w.box(bm, lo, hi, y0, y1, 0.0, 0.025), w.box(bm, lo - 0.03, hi + 0.03, y1 - 0.05, y1, 0.0, 0.05),
                                                         w.box(bm, lo - 0.03, hi + 0.03, y0, y0 + 0.04, 0.0, 0.04)))
    rows = [y0 + 0.2 + r * (y1 - y0 - 0.3) / 3.5 for r in range(4)]
    step = (hi - lo) / per_row
    rng = np.random.default_rng(61 + start)
    items, hooks, keys = [], [], []
    for r, yy in enumerate(reversed(rows)):
        for k in range(per_row):
            idx = start + r * per_row + k
            aa = lo + (k + 0.5) * step if (w.right()[0] if w.axis == "z" else w.right()[2]) > 0 else hi - (k + 0.5) * step
            items.append((idx, aa, yy + 0.07, step * 0.7, 0.04))
            hooks.append((aa, yy))
            if rng.random() < 0.68:
                keys.append((aa, yy, rng.random() < 0.3))
    plate_quads(f"Hooks_{tag}_Plates", w, items, d=0.026)
    part(f"Hooks_{tag}_Hooks", "Brass", lambda bm: [(cyl(bm, w.pt(aa, yy, 0.025), w.pt(aa, yy, 0.06), 0.004, seg=6), cyl(bm, w.pt(aa, yy, 0.06), w.pt(aa, yy + 0.015, 0.065), 0.004, seg=6))
                                                     for aa, yy in hooks])
    part(f"Hooks_{tag}_Keys", "Steel", lambda bm: [(w.box(bm, aa - 0.012, aa + 0.012, yy - 0.04, yy - 0.006, 0.045, 0.052), w.box(bm, aa - 0.004, aa + 0.004, yy - 0.1, yy - 0.04, 0.046, 0.051),
                                                    w.box(bm, aa, aa + 0.01, yy - 0.09, yy - 0.075, 0.046, 0.051)) for aa, yy, red in keys])
    part(f"Hooks_{tag}_Tags", "Key_Tag", lambda bm: [w.box(bm, aa - 0.016, aa + 0.016, yy - 0.16, yy - 0.1, 0.04, 0.044) for aa, yy, red in keys if not red])
    part(f"Hooks_{tag}_TagsRed", "Key_Tag_Red", lambda bm: [w.box(bm, aa - 0.016, aa + 0.016, yy - 0.16, yy - 0.1, 0.04, 0.044) for aa, yy, red in keys if red])


def cabinets(b):
    """Four tall key cabinets on the west wall, on their collider: card-index drawers below (brass label holders and cup pulls), two panelled
    doors above each with a numbered plate, a cornice over the bank."""
    x0, x1, z0, z1, h = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]
    front = Wall("x", x1, 1)
    part("Cab_Body", "Wood_Dark", lambda bm: (cube(bm, (x0, 0.0, z0), (x1 - 0.02, h - 0.08, z1)), cube(bm, (x0, h - 0.08, z0 - 0.03), (x1 + 0.03, h, z1 + 0.03))))
    n = 4
    cw = (z1 - z0) / n

    def fronts(bm):
        for c in range(n):
            a0 = z0 + c * cw
            for r in range(4):
                for k in range(6):
                    b0 = a0 + 0.03 + k * (cw - 0.06) / 6
                    b1 = b0 + (cw - 0.06) / 6 - 0.012
                    yy0 = 0.08 + r * 0.19
                    front.box(bm, b0, b1, yy0, yy0 + 0.17, -0.02, 0.0)
            for k in range(2):
                b0 = a0 + 0.04 + k * (cw - 0.08) / 2
                b1 = b0 + (cw - 0.08) / 2 - 0.02
                front.box(bm, b0, b1, 0.9, h - 0.12, -0.02, 0.0)
                front.box(bm, b0 + 0.08, b1 - 0.08, 0.98, h - 0.2, 0.0, 0.006)
    part("Cab_Fronts", "Wood_Dark", fronts)

    def brass(bm):
        for c in range(n):
            a0 = z0 + c * cw
            for r in range(4):
                for k in range(6):
                    bc = a0 + 0.03 + (k + 0.5) * (cw - 0.06) / 6 - 0.006
                    yy0 = 0.08 + r * 0.19
                    front.box(bm, bc - 0.035, bc + 0.035, yy0 + 0.11, yy0 + 0.145, 0.0, 0.004)
                    front.box(bm, bc - 0.02, bc + 0.02, yy0 + 0.05, yy0 + 0.07, 0.0, 0.018)
            for k in range(2):
                bc = a0 + 0.04 + (k + 0.5) * (cw - 0.08) / 2 - 0.01
                kx = bc + (0.28 if k == 0 else -0.28)
                front.box(bm, kx - 0.008, kx + 0.008, 1.42, 1.56, 0.006, 0.02)
    part("Cab_Brass", "Brass", brass)
    items = []
    for c in range(n):
        for k in range(2):
            bc = z0 + c * cw + 0.04 + (k + 0.5) * (cw - 0.08) / 2 - 0.01
            items.append((32 * 4 + 20 * 4 + c * 2 + k, bc, 1.92, 0.16, 0.06))
    plate_quads("Cab_Plates", Wall("x", x1 + 0.007, 1), items)


def cage(b, safe):
    """The locked cage in the north-east corner, round the safe, on its collider: steel posts, top and bottom rails, close vertical bars on its
    two open sides, a barred door with a hasp and a padlock; inside, the green safe with its dial, handle and maker's plate."""
    x0, x1, z0, z1, h = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]

    def frame(bm):
        for x, z in ((x0 + 0.03, z1 - 0.03), (x0 + 0.03, z0 + 0.03), (x1 - 0.03, z1 - 0.03)):
            cube(bm, (x - 0.025, 0.0, z - 0.025), (x + 0.025, h, z + 0.025))
        for y in (0.05, h - 0.05, 1.2):
            cube(bm, (x0 + 0.01, y - 0.02, z0 + 0.03), (x0 + 0.05, y + 0.02, z1 - 0.03))
            cube(bm, (x0 + 0.03, y - 0.02, z1 - 0.05), (x1 - 0.03, y + 0.02, z1 - 0.01))
        cube(bm, (x0, h - 0.03, z0), (x1, h, z1))
    part("Cage_Frame", "Iron", frame)

    def bars(bm):
        n = int((z1 - z0 - 0.1) / 0.1)
        for k in range(1, n):
            z = z0 + 0.05 + k * (z1 - z0 - 0.1) / n
            cyl(bm, (x0 + 0.03, 0.05, z), (x0 + 0.03, h - 0.05, z), 0.008, seg=6)
        n = int((x1 - x0 - 0.1) / 0.1)
        for k in range(1, n):
            x = x0 + 0.05 + k * (x1 - x0 - 0.1) / n
            if x0 + 0.5 < x < x0 + 1.3:                  # the door's bars are the door's
                continue
            cyl(bm, (x, 0.05, z1 - 0.03), (x, h - 0.05, z1 - 0.03), 0.008, seg=6)
    part("Cage_Bars", "Iron", bars)

    def door(bm):
        d0, d1, zz = x0 + 0.5, x0 + 1.3, z1 - 0.03
        for y in (0.08, 2.05, 1.05):
            cube(bm, (d0, y - 0.02, zz - 0.012), (d1, y + 0.02, zz + 0.012))
        for x in (d0, d1):
            cube(bm, (x - 0.015, 0.08, zz - 0.012), (x + 0.015, 2.05, zz + 0.012))
        for k in range(1, 8):
            x = d0 + k * (d1 - d0) / 8
            cyl(bm, (x, 0.08, zz), (x, 2.05, zz), 0.008, seg=6)
        cube(bm, (d1 - 0.02, 1.0, zz + 0.012), (d1 + 0.08, 1.1, zz + 0.02))
    part("Cage_Door", "Iron", door)
    part("Cage_Padlock", "Brass", lambda bm: (cube(bm, (x0 + 1.33, 0.93, z1 - 0.01), (x0 + 1.39, 1.0, z1 + 0.012)), tube(bm, (x0 + 1.345, 1.0, z1), (x0 + 1.375, 1.0, z1), 0.02, seg=10)))
    sx0, sx1, sz0, sz1, sh = safe["min"][0], safe["max"][0], safe["min"][2], safe["max"][2], safe["max"][1]
    part("Safe_Body", "Safe_Paint", lambda bm: (cube(bm, (sx0 + 0.02, 0.08, sz0 + 0.02), (sx1 - 0.02, sh, sz1 - 0.02)), cube(bm, (sx0, 0.0, sz0), (sx1, 0.08, sz1))))
    sf = Wall("z", sz1 - 0.02, 1)
    part("Safe_Door", "Safe_Paint", lambda bm: sf.box(bm, sx0 + 0.08, sx1 - 0.08, 0.16, sh - 0.08, 0.0, 0.025))
    part("Safe_Dial", "Silver", lambda bm: (cyl(bm, sf.pt(6.0, 0.8, 0.025), sf.pt(6.0, 0.8, 0.05), 0.07, seg=24), cyl(bm, sf.pt(6.0, 0.8, 0.05), sf.pt(6.0, 0.8, 0.07), 0.03, seg=12)))
    part("Safe_Handle", "Brass", lambda bm: (cyl(bm, sf.pt(6.3, 0.6, 0.025), sf.pt(6.3, 0.6, 0.08), 0.015, seg=10), sf.box(bm, 6.22, 6.38, 0.59, 0.61, 0.07, 0.085)))
    part("Safe_Plate", "Brass", lambda bm: sf.box(bm, 5.75, 6.25, 1.0, 1.06, 0.025, 0.028))


# ---------------------------------------------------------------- the green room
def room_build():
    lay = SCENE
    x0, x1, z0, z1 = SK.room_dims(lay)
    H = GB.ROOM_H
    Wn, Ws, We, Ww = Wall("z", z0, 1), Wall("z", z1, -1), Wall("x", x1, -1), Wall("x", x0, 1)
    door_casing(Ws, 0.0, GB.DOOR_W / 2, GB.DOOR_H, "door", "Wood_Dark")
    part("Switch", "Brass", lambda bm: Ws.box(bm, 0.66, 0.74, 1.15, 1.27, 0.0, 0.01))
    runs = [("S", Ws, [(x0, -0.56), (0.56, x1)]), ("E", We, [(z0, -4.0), (-3.2, -2.6), (-1.6, z1)]), ("N", Wn, [(-1.3, x1)]),
            ("W", Ww, [(-5.6, -4.6), (-3.4, -2.15), (-1.25, z1)])]
    for tag, w, rr in runs:
        for i, (a0, a1) in enumerate(rr):
            part(f"Skirting_{tag}_{i}", "Skirting", lambda bm, w=w, a0=a0, a1=a1: w.box(bm, a0, a1, 0.0, 0.14, 0.0, 0.014))
    for tag, w, a0, a1 in (("S", Ws, x0, x1), ("E", We, z0, z1), ("N", Wn, -1.3, x1), ("W", Ww, -5.6, z1)):
        cornice(w, a0, a1, H, tag)
    part("Ceiling_Rose", "Trim_Cream", lambda bm: cyl(bm, (0.0, H - 0.025, -3.6), (0.0, H, -3.6), 0.26, seg=28))
    part("Ceiling_Bowl", "Lamp_Emit", lambda bm: cyl(bm, (0.0, H - 0.16, -3.6), (0.0, H - 0.07, -3.6), 0.12, 0.2, seg=28))
    part("Ceiling_Bowl_Rod", "Brass", lambda bm: (cyl(bm, (0.0, H - 0.07, -3.6), (0.0, H - 0.025, -3.6), 0.01, seg=8), cyl(bm, (0.0, H - 0.18, -3.6), (0.0, H - 0.16, -3.6), 0.02, seg=8)))
    light("L_ceiling", "POINT", (0.0, H - 0.22, -3.6), DOME_W, size=0.12)
    part("Smoke", "Plastic_White", lambda bm: cyl(bm, (1.2, H - 0.035, -1.4), (1.2, H, -1.4), 0.065, seg=20))
    window(We, SK.GWIN)
    bed("Bed", -0.8, 0.8, z0, -5.2)
    nightstand(0.95, 1.45, z0, -6.72)
    armchair(1.4, 2.2, -4.0, -3.2)
    wardrobe(1.8, x1, -2.6, -1.6, 2.0)
    writing_desk(x0, -1.85, -4.6, -3.4, 0.78)
    bath_door(Ww, -1.7, 0.8)
    nook(x0, -1.4, z0, -5.7)
    picture(Wn, 0.0, 1.78, 0.9, 0.62, "bed", 0)
    picture(Ww, -4.0, 1.6, 0.66, 0.5, "desk", 2)
    picture(Ws, -1.6, 1.6, 0.6, 0.46, "door", 3)
    for zw, sg in ((0.0, 1), (2 * GB.CORR_Z, -1)):         # the corridor outside the open door (bake stand-ins: its sconces and the leaf, open into the room)
        w = Wall("z", zw, sg)
        for xx in (-2.0, 2.0):
            light(f"L_sb_sconce_{zw:.0f}_{xx:+.0f}", "POINT", w.pt(xx, SK.SCONCE_Y, 0.15), SCONCE_W, size=0.03, coll=BAKE_STANDIN)
            part(f"standin_shade_{zw:.0f}_{xx:+.0f}", "Lamp_Emit", lambda bm, w=w, xx=xx: tube(bm, w.pt(xx, SK.SCONCE_Y - 0.07, 0.15), w.pt(xx, SK.SCONCE_Y + 0.075, 0.15), 0.095, 0.062),
                 BAKE_STANDIN, recalc=False)
    bm = bmesh.new()
    cube(bm, (0, 0, 0), (0.93, 2.15, 0.05))
    me = bpy.data.meshes.new("standin_leaf")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS["Wood_Dark"])
    leaf = bpy.data.objects.new("standin_leaf", me)
    BAKE_STANDIN.objects.link(leaf)
    leaf.matrix_world = Matrix.Translation(B((-GB.DOOR_W / 2, 0.0, z1))) @ Matrix.Rotation(math.radians(95), 4, "Z")


def window(w, gw):
    """A recessed sash window in the east wall, its panes dark: it looks onto nothing. Green drapes on a pole either side (decor_), a sheer."""
    za, zb, y0, y1 = gw                                  # the east wall's `a` runs along z
    recess_box(w, za, zb, y0, y1, 0.12, "Window_Frame", "win")
    part("Win_Void", "Window_Void", lambda bm: w.box(bm, za + 0.01, zb - 0.01, y0 + 0.01, y1 - 0.01, -0.11, -0.1))
    zm, ym = (za + zb) / 2, (y0 + y1) / 2
    part("Win_Bars", "Window_Frame", lambda bm: (w.box(bm, zm - 0.02, zm + 0.02, y0, y1, -0.1, -0.06), w.box(bm, za, zb, ym - 0.025, ym + 0.025, -0.1, -0.06)))
    part("Win_Sill", "Window_Frame", lambda bm: w.box(bm, za - 0.06, zb + 0.06, y0 - 0.03, y0, 0.0, 0.05))
    part("decor_curtain_pole", "Brass", lambda bm: cyl(bm, w.pt(za - 0.35, 2.4, 0.09), w.pt(zb + 0.35, 2.4, 0.09), 0.014, seg=10))
    for k, (c0, c1) in enumerate(((za - 0.33, za + 0.12), (zb - 0.12, zb + 0.33))):
        def cur(bm, c0=c0, c1=c1, k=k):
            n = 18
            rng = np.random.default_rng(71 + k)
            ph = rng.random() * 6
            vt, vb = [], []
            for i in range(n + 1):
                t = i / n
                aa = c0 + (c1 - c0) * t
                dd = 0.075 + 0.04 * math.sin(t * math.pi * 7 + ph)
                vt.append(bm.verts.new(B(w.pt(aa, 2.38, dd))))
                vb.append(bm.verts.new(B(w.pt(aa, 0.03, dd + 0.01 * math.sin(t * 20)))))
            for i in range(n):
                bm.faces.new((vb[i], vb[i + 1], vt[i + 1], vt[i]))
        part(f"decor_curtain_{k}", "Drape", cur, tile=0.5, recalc=False)
    part("decor_curtain_sheer", "Drape_Sheer", lambda bm: w.box(bm, za - 0.02, zb + 0.02, 0.8, 2.36, 0.035, 0.037))


def bed(name, xa, xb, za, zb):
    """A double bed on its collider, its head against the north wall: a dark wood frame, the mattress under a cream quilted spread with a sage
    band, pillows, a buttoned green velvet headboard."""
    h_mat = 0.52
    part(f"{name}_Frame", "Wood_Dark", lambda bm: (cube(bm, (xa, 0.0, za + 0.07), (xb, 0.26, zb)), [cube(bm, (x - 0.03, 0.0, zb - 0.06), (x + 0.03, 0.62, zb)) for x in (xa + 0.03, xb - 0.03)],
                                                    cube(bm, (xa, 0.4, zb - 0.05), (xb, 0.55, zb))))
    part(f"{name}_Spread", "Bedspread", lambda bm: cube(bm, (xa + 0.01, 0.22, za + 0.42), (xb - 0.01, h_mat + 0.03, zb - 0.06)), tile=1.0)
    part(f"{name}_Sheet", "Linen_White", lambda bm: cube(bm, (xa + 0.03, 0.26, za + 0.08), (xb - 0.03, h_mat, za + 0.44)))
    for k, (px0, px1) in enumerate(((xa + 0.08, -0.03), (0.03, xb - 0.08))):
        part(f"{name}_Pillow_{k}", "Linen_White", lambda bm, px0=px0, px1=px1: cube(bm, (px0, h_mat, za + 0.1), (px1, h_mat + 0.14, za + 0.42)))
    part(f"{name}_Turn", "Linen_White", lambda bm: cube(bm, (xa + 0.01, h_mat + 0.03, za + 0.42), (xb - 0.01, h_mat + 0.07, za + 0.5)))
    part(f"{name}_Head", "Velvet_Green", lambda bm: (cube(bm, (xa - 0.03, 0.3, za), (xb + 0.03, 1.32, za + 0.07)), cyl(bm, (xa - 0.03, 1.32, za + 0.035), (xb + 0.03, 1.32, za + 0.035), 0.04, seg=12)))
    part(f"{name}_Buttons", "Brass", lambda bm: [sphere(bm, (xa + 0.15 + i * (xb - xa - 0.3) / 6, 0.75 + r * 0.22, za + 0.072), 0.009, seg=6) for i in range(7) for r in range(3)])


def nightstand(xa, xb, za, zb):
    h = 0.6
    part("Nightstand", "Wood_Dark", lambda bm: cube(bm, (xa + 0.01, 0.06, za + 0.01), (xb - 0.01, h, zb - 0.01)))
    part("Nightstand_Feet", "Wood_Dark", lambda bm: [cube(bm, (x - 0.02, 0.0, z - 0.02), (x + 0.02, 0.06, z + 0.02)) for x in (xa + 0.04, xb - 0.04) for z in (za + 0.04, zb - 0.04)])
    part("Nightstand_Pull", "Brass", lambda bm: cube(bm, ((xa + xb) / 2 - 0.04, 0.46, zb - 0.01), ((xa + xb) / 2 + 0.04, 0.48, zb + 0.005)))
    lx, lz = (xa + xb) / 2, (za + zb) / 2
    part("Lamp_Foot", "Brass", lambda bm: (cyl(bm, (lx, h, lz), (lx, h + 0.025, lz), 0.07, seg=20), cyl(bm, (lx, h + 0.025, lz), (lx, h + 0.3, lz), 0.045, 0.025, seg=18)))
    part("Lamp_Shade", "Lamp_Emit", lambda bm: tube(bm, (lx, h + 0.26, lz), (lx, h + 0.48, lz), 0.15, 0.11, seg=32), recalc=False)
    light("L_lamp", "POINT", (lx, h + 0.37, lz), LAMP_W, size=0.04)
    part("Book", "Book_Green", lambda bm: cube(bm, (xa + 0.04, h, zb - 0.16), (xa + 0.2, h + 0.03, zb - 0.04)))


def armchair(xa, xb, za, zb):
    """A green velvet wing chair on its collider, its back to the east wall, facing the room (west)."""
    def body(bm):
        cube(bm, (xa + 0.03, 0.08, za + 0.03), (xb - 0.03, 0.42, zb - 0.03))
        cube(bm, (xb - 0.2, 0.42, za + 0.03), (xb - 0.03, 1.05, zb - 0.03))
        for za_, zb_ in ((za + 0.0, za + 0.12), (zb - 0.12, zb)):
            cube(bm, (xa + 0.06, 0.08, za_), (xb - 0.03, 0.66, zb_))
            cube(bm, (xb - 0.32, 0.66, za_), (xb - 0.03, 1.0, zb_))
        cube(bm, (xa + 0.08, 0.42, za + 0.12), (xb - 0.2, 0.52, zb - 0.12))
    part("Armchair", "Velvet_Green", body)
    part("Armchair_Feet", "Wood_Dark", lambda bm: [cube(bm, (x - 0.025, 0.0, z - 0.025), (x + 0.025, 0.08, z + 0.025)) for x in (xa + 0.08, xb - 0.08) for z in (za + 0.06, zb - 0.06)])


def wardrobe(xa, xb, za, zb, h):
    """A dark wood wardrobe on its collider, facing west: two panelled doors with brass handles, a drawer below, a cornice, bun feet."""
    front = Wall("x", xa, -1)
    part("Wardrobe_Body", "Wood_Dark", lambda bm: (cube(bm, (xa + 0.02, 0.1, za + 0.01), (xb - 0.01, h - 0.08, zb - 0.01)), cube(bm, (xa - 0.02, h - 0.08, za - 0.02), (xb, h, zb + 0.02)),
                                                    cube(bm, (xa, 0.06, za), (xb - 0.01, 0.12, zb))))

    def doors(bm):
        zm = (za + zb) / 2
        for d0, d1 in ((za + 0.03, zm - 0.01), (zm + 0.01, zb - 0.03)):
            front.box(bm, d0, d1, 0.42, h - 0.12, -0.02, 0.0)
            front.box(bm, d0 + 0.07, d1 - 0.07, 0.5, h - 0.2, 0.0, 0.006)
        front.box(bm, za + 0.03, zb - 0.03, 0.14, 0.38, -0.02, 0.0)
    part("Wardrobe_Doors", "Wood_Dark", doors)
    zm = (za + zb) / 2
    part("Wardrobe_Handles", "Brass", lambda bm: (front.box(bm, zm - 0.06, zm - 0.04, 1.05, 1.2, 0.0, 0.02), front.box(bm, zm + 0.04, zm + 0.06, 1.05, 1.2, 0.0, 0.02),
                                                  front.box(bm, zm - 0.06, zm + 0.06, 0.25, 0.27, 0.0, 0.02)))
    part("Wardrobe_Feet", "Wood_Dark", lambda bm: [cyl(bm, (x, 0.0, z), (x, 0.06, z), 0.035, seg=10) for x in (xa + 0.06, xb - 0.06) for z in (za + 0.06, zb - 0.06)])
    part("Wardrobe_Case", "Book_Green", lambda bm: cube(bm, (xa + 0.1, h, za + 0.25), (xb - 0.12, h + 0.18, zb - 0.3)))


def writing_desk(xa, xb, za, zb, h):
    """The writing desk against the west wall, on its collider: a leather-topped desk with a drawer, a lamp (lit), a blotter, writing paper, a
    pen; its chair tucked in."""
    xt = xb - 0.03
    part("Desk_Top", "Wood_Dark", lambda bm: cube(bm, (xa, h - 0.035, za), (xt, h, zb)))
    part("Desk_Legs", "Wood_Dark", lambda bm: [cyl(bm, (x, 0.0, z), (x, h - 0.035, z), 0.018, 0.024, seg=10) for x in (xa + 0.05, xt - 0.03) for z in (za + 0.04, zb - 0.04)])
    part("Desk_Apron", "Wood_Dark", lambda bm: cube(bm, (xa + 0.03, h - 0.14, za + 0.03), (xt - 0.02, h - 0.035, zb - 0.03)))
    part("Desk_Pull", "Brass", lambda bm: cube(bm, (xt - 0.02, h - 0.1, (za + zb) / 2 - 0.04), (xt, h - 0.085, (za + zb) / 2 + 0.04)))
    part("Desk_Blotter", "Blotter", lambda bm: cube(bm, (xa + 0.12, h, za + 0.3), (xt - 0.08, h + 0.004, zb - 0.3)))
    part("Desk_Paper", "Paper", lambda bm: cube(bm, (xa + 0.2, h + 0.004, za + 0.45), (xa + 0.42, h + 0.007, za + 0.75)))
    part("Desk_Pen", "Plastic_Black", lambda bm: cyl(bm, (xa + 0.45, h + 0.008, za + 0.5), (xa + 0.47, h + 0.008, za + 0.65), 0.004, seg=6))
    lx, lz = xa + 0.16, zb - 0.16
    part("DeskLamp_Foot", "Brass", lambda bm: (cyl(bm, (lx, h, lz), (lx, h + 0.02, lz), 0.07, seg=18), cyl(bm, (lx, h + 0.02, lz), (lx, h + 0.36, lz), 0.01, seg=8)))
    part("DeskLamp_Shade", "Lamp_Emit", lambda bm: tube(bm, (lx, h + 0.28, lz), (lx, h + 0.44, lz), 0.12, 0.08, seg=28), recalc=False)
    light("L_desklamp", "POINT", (lx, h + 0.34, lz), LAMP_W * 0.8, size=0.03)
    cx0, cx1 = xb - 0.38, xb - 0.04
    cz0, cz1 = (za + zb) / 2 - 0.21, (za + zb) / 2 + 0.21
    part("DeskChair_Frame", "Wood_Dark", lambda bm: ([cyl(bm, (x, 0.0, z), (x, 0.44, z), 0.016, 0.02, seg=8) for x in (cx0 + 0.03, cx1 - 0.03) for z in (cz0 + 0.03, cz1 - 0.03)],
                                                      [cube(bm, (cx1 - 0.03, 0.44, z - 0.016), (cx1, 0.92, z + 0.016)) for z in (cz0 + 0.03, cz1 - 0.03)],
                                                      cube(bm, (cx1 - 0.035, 0.78, cz0 + 0.03), (cx1, 0.9, cz1 - 0.03))))
    part("DeskChair_Seat", "Velvet_Green", lambda bm: cube(bm, (cx0, 0.42, cz0), (cx1, 0.47, cz1)))


def bath_door(w, a, wd):
    """The bathroom door, shut: a cream panelled leaf 3 cm proud of the west wall in a dark wood casing, a brass knob."""
    part("Bath_Door", "Door_Bath", lambda bm: (w.box(bm, a - wd / 2, a + wd / 2, 0.0, 2.04, 0.0, 0.03),
                                               [w.box(bm, a - wd / 2 + 0.08, a + wd / 2 - 0.08, y0, y1, 0.03, 0.036) for y0, y1 in ((0.2, 0.92), (1.05, 1.92))]))
    door_casing(w, a, wd / 2 + 0.005, 2.045, "bath", "Wood_Dark", 0.07, 0.016, cap=False)
    part("Bath_Door_Knob", "Brass", lambda bm: (cyl(bm, w.pt(a - wd / 2 + 0.07, 0.95, 0.03), w.pt(a - wd / 2 + 0.07, 0.95, 0.06), 0.008, seg=8),
                                                sphere(bm, w.pt(a - wd / 2 + 0.07, 0.95, 0.068), 0.022, seg=10)))


def nook(xa, xb, za, zb):
    """The wardrobe nook (the hide spot): a hat shelf and a rail above head height, a few wooden hangers and an old coat on them (decor_)."""
    part("Nook_Shelf", "Wood_Dark", lambda bm: cube(bm, (xa, 1.92, za), (xb, 1.95, za + 0.4)))
    part("Nook_Rail", "Brass", lambda bm: cyl(bm, (xa, 1.86, za + 0.25), (xb, 1.86, za + 0.25), 0.012, seg=10))

    def hangers(bm):
        for k in range(4):
            x = xa + 0.2 + k * 0.2
            cube(bm, (x - 0.008, 1.62, za + 0.04), (x + 0.008, 1.66, za + 0.46))
            cyl(bm, (x, 1.66, za + 0.25), (x, 1.86, za + 0.25), 0.003, seg=5)
    part("decor_nook_hangers", "Wood_Dark", hangers)
    part("decor_nook_coat", "Velvet_Green", lambda bm: (cube(bm, (xa + 0.52, 0.95, za + 0.06), (xa + 0.66, 1.64, za + 0.44)), cube(bm, (xa + 0.5, 1.5, za + 0.02), (xa + 0.68, 1.66, za + 0.48))))


# ---------------------------------------------------------------- the file
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for d in (IMG, MATS, TILES, GEN, LEAF_MESH, NUMBERS):
        d.clear()


COLLS = ("Art", "Props", "Arch", "Skin", "Doors", "Layout", "Standins", "Bake_Standins", "Lights", "Kit")


def build_all():
    global ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, STANDIN, BAKE_STANDIN, LIGHTS, KIT
    reset()
    sc = bpy.context.scene
    ART = bpy.data.collections.new("Art")
    sc.collection.children.link(ART)
    PROPS, ARCH = bpy.data.collections.new("Props"), bpy.data.collections.new("Arch")
    ART.children.link(PROPS)
    ART.children.link(ARCH)
    SKIN, DOORS, LAYOUT, STANDIN, BAKE_STANDIN, LIGHTS, KIT = (bpy.data.collections.new(n) for n in ("Skin", "Doors", "Layout", "Standins", "Bake_Standins", "Lights", "Kit"))
    for c in (SKIN, DOORS, LAYOUT, STANDIN, BAKE_STANDIN, LIGHTS, KIT):
        sc.collection.children.link(c)
    make_materials()
    M = SK.model(SCENE)
    layout_from_model(M)
    place_kit()
    build_skin()
    if KIND == "corridor":
        build_leaves(M)
        build_corridor(M)
        corridor_standins()
    elif KIND == "keyroom":
        build_leaves(M)
        build_keyroom(M)
    else:
        room_build()
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
          f"{len(LIGHTS.objects)} lights, {len(KIT.objects)} kit stand-ins")


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
    stand = [c for c in ({"min": gbox(o)[0], "max": gbox(o)[1]} for o in bpy.data.objects if o.name.startswith("COL_") and o.type == "MESH") if cl._standing(c)]
    allc = [{"min": gbox(o)[0], "max": gbox(o)[1]} for o in bpy.data.objects if o.name.startswith("COL_") and o.type == "MESH"]
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
        if ob.type != "MESH" or ob.name.startswith("decor_"):
            continue
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
            nob = bpy.data.objects.new(f"{name}_p{k}", me)
            PROPS.objects.link(nob)
        done.append(f"{name} ({len(groups)})")
    print("SPLIT for the layout check:", done)


# ---------------------------------------------------------------- bake
SHELL_MATS = {"Carpet_Green", "Carpet_Field", "Ceiling_Plaster", "Closet_Paint", "Door_Jamb", "Jamb_Steel", "Lift_Steel", "Stair_Concrete", "Stair_Paint",
              "Stair_Ceiling", "Threshold", "Wainscot", "Wall_Green", "Carpet_Hall", "Wall_Hall", "Ceiling_Hall", "Carpet_Room", "Wall_Room", "Ceiling_Room"}
NO_LIGHTMAP = {"Lamp_Emit", "Emergency_Emit", "Glass_Clear"}
NO_CULL = ("Recess_", "Ext_", "Win_")


def arch_cols():
    return [c for c in SK.colliders(SK.model(SCENE), kit=False) if not c["name"].startswith(SK.FURNITURE)]


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


def lightmap_uv(objs, page=None, want=36.0):
    """One atlas for `objs`: smart-project islands at equal texel density, packed with MARGIN_PX on the fixed `page`. Returns (page, density)."""
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
            # a rotated rectangle lies on its side: its e2 side (ph pixels) runs along u, its e1 side (pw) along t, as layout() reserved it
            u, t = (b * ph, a * pw) if rot else (a * pw, b * ph)
            assert -1e-3 <= u <= (ph if rot else pw) + 1e-3 and -1e-3 <= t <= (pw if rot else ph) + 1e-3, (o.name, u, t, rot)
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
    """The leaves baked for their mesh (one per kind), and their brass numbers (each its own)."""
    reps = []
    for kind, name in BAKE_LEAF.get(SCENE, {}).items():
        reps.append(bpy.data.objects[name])
    reps += sorted((o for o in bpy.data.collections["Doors"].objects if o.name.startswith("DoorNum_")), key=lambda o: o.name)
    return reps


def bake_visibility():
    for c, hide in (("Art", True), ("Skin", True), ("Standins", True), ("Bake_Standins", False), ("Doors", False), ("Export", False), ("Kit", False)):
        bpy.data.collections[c].hide_render = hide
    bpy.data.collections["Art"].hide_viewport = True
    bpy.data.collections["Skin"].hide_viewport = True


def shoulder(rgb):
    knee_pc, roll = SHOULDER.get(SCENE, SHOULDER["default"])
    peak = rgb.max(axis=2)
    lit = peak[peak > 1e-5]
    if not len(lit):
        return rgb, 0.0
    k = float(np.percentile(lit, knee_pc))
    m = roll * k
    f = np.where(peak <= k, peak, k + (peak - k) / (1 + (peak - k) / (m - k)))
    return rgb * (f / np.maximum(peak, 1e-8))[..., None], k


def stage_bake(size_only=False):
    import time
    exp = make_export_objects()
    bake_visibility()
    setup_cycles(SAMPLES, bake=True)
    shell = [o for k, o in sorted(exp.items()) if o.data.materials[0].name in SHELL_MATS]
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
        np.save(work() / f"{SCENE}_{n}_raw.npy", rgb.astype(np.float16))
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
                     "shoulder": list(SHOULDER.get(SCENE, SHOULDER["default"])),
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
    global ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, STANDIN, BAKE_STANDIN, LIGHTS, KIT
    c = bpy.data.collections
    ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, STANDIN, BAKE_STANDIN, LIGHTS, KIT = (c.get(n) for n in ("Art", "Props", "Arch", "Skin", "Doors", "Layout", "Standins",
                                                                                              "Bake_Standins", "Lights", "Kit"))
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
    E = 1.6
    return {
        "floor_2_lower": {"1_arrival": ((-18.8, E, 0.0), (-8.8, E - 0.3, 0.0), 75), "2_wide": ((19.3, 2.35, 0.75), (-6.0, 0.6, -0.4), 70),
                          "3_detail": ((-1.2, 1.55, 0.6), (0.25, 1.45, -1.1), 62)},
        "floor_2_upper": {"1_arrival": ((18.8, E, 0.0), (8.8, E - 0.3, 0.0), 75), "2_wide": ((-19.3, 2.35, -0.75), (6.0, 0.6, 0.4), 70),
                          "3_detail": ((4.7, 1.5, 0.6), (3.9, 1.05, -2.0), 68)},
        "dining": {"1_arrival": ((0.0, E, 3.8), (0.0, E - 0.45, -4.0), 75), "2_wide": ((6.4, 2.45, 4.4), (-2.0, 0.6, -2.0), 75),
                   "3_detail": ((-2.5, 1.3, 2.7), (-4.0, 0.75, 1.5), 55)},
        "reception": {"1_arrival": ((0.0, E, 3.8), (0.0, E - 0.4, -4.5), 75), "2_wide": ((-6.3, 1.9, 4.5), (2.0, 1.0, -3.5), 72),
                      "3_detail": ((0.5, 1.5, 0.75), (-0.1, 1.05, -0.65), 55)},
        "key_room": {"1_arrival": ((0.0, E, 3.8), (0.0, E - 0.4, -4.5), 75), "2_wide": ((-6.3, 2.35, 4.4), (3.0, 0.8, -3.0), 75),
                     "3_detail": ((1.4, 1.5, -2.4), (-0.4, 1.45, -5.0), 60)},
        "green_room": {"1_arrival": ((0.0, E, -0.8), (0.0, E - 0.4, -6.8), 75), "2_wide": ((-1.9, 2.2, -0.6), (1.2, 0.5, -5.8), 75),
                       "3_detail": ((-0.5, 1.35, -2.9), (-2.3, 0.9, -4.1), 60)},
    }[SCENE]


def plan_box():
    cols = SK.colliders(SK.model(SCENE))
    x0, x1 = min(c["min"][0] for c in cols) - 0.4, max(c["max"][0] for c in cols) + 0.4
    z0, z1 = min(c["min"][2] for c in cols) - 0.4, max(c["max"][2] for c in cols) + 0.4
    return x0, x1, z0, z1


PLAN_HIDE = ("Ceiling", "Lift_Ceiling", "Stair_Ceiling", "Cornice_", "decor_stain_ceiling", "Smoke", "AlcoveLight", "AlcoveRose", "Bulkhead", "Chand_",
             "Pendant_", "standin", "SB_", "Win_", "Recess_win")


def stage_render():
    import re
    sc = bpy.context.scene
    d = stills_dir(SCENE)
    d.mkdir(parents=True, exist_ok=True)
    scrub_private()
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
    for c, hide in (("Art", False), ("Skin", False), ("Doors", False), ("Bake_Standins", False), ("Standins", True), ("Lights", False), ("Kit", False)):
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
        span = x1 - x0
        cam = look_cam("plan", ((x0 + x1) / 2, 30.0, (z0 + z1) / 2), None, ortho=span)
        cam.rotation_euler = (0, 0, 0)
        sc.camera = cam
        hidden = []
        top = 2.3 if KIND != "keyroom" else 2.5
        for o in list(bpy.data.collections["Skin"].objects) + list(bpy.data.collections["Props"].objects) + list(bpy.data.collections["Bake_Standins"].objects) \
                + list(bpy.data.collections["Kit"].objects) + list(bpy.data.collections["Doors"].objects):
            if o.type != "MESH":
                continue
            if o.name.startswith(PLAN_HIDE) or (min((o.matrix_world @ v.co).z for v in o.data.vertices) > top and not o.name.startswith("Step")):
                if not o.hide_render:
                    o.hide_render = True
                    hidden.append(o)
        arch = bpy.data.collections["Arch"]
        arch.hide_render = False
        floorish = re.compile(r".*(_Floor|_Ceiling)(_\d+)?$")
        for o in arch.objects:
            o.hide_render = bool(floorish.match(o.name)) or o.name.startswith(("Step_", "Landing_Top", "Car_"))
        world = sc.world
        bg = world.node_tree.nodes["Background"]
        old = bg.inputs["Strength"].default_value
        bg.inputs["Color"].default_value = (1, 1, 1, 1)
        bg.inputs["Strength"].default_value = 0.6
        W = 2400 if KIND == "corridor" else 1600
        H = max(200, int(round(W * (z1 - z0) / span)))
        sc.render.resolution_x, sc.render.resolution_y = W, H
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
        (work() / f"{SCENE}_plan.json").write_text(json.dumps({"x0": x0, "x1": x1, "z0": z0, "z1": z1, "w": W, "h": H}))
        print("PLAN", path, W, H)


# ---------------------------------------------------------------- main
def main():
    global SCENE, KIND
    scenes = arg("--scenes", "floor_2_lower").split(",")
    for sc in scenes:
        SCENE = sc
        KIND = "room" if sc in SK.ROOMS else "keyroom" if sc in SK.KEYROOMS else "corridor"
        print(f"==== {sc} ({KIND}) stage {STAGE}")
        if STAGE in ("art", "all", "size", "preview"):
            build_all()
            save_blend()
        else:
            load_scene_file()
        if STAGE == "size":
            stage_bake(size_only=True)
        if STAGE == "preview":
            import export_scene
            export_scene.write(SCENE, world_json(SCENE))
            stage_check()
        if STAGE in ("bake", "all"):
            stage_bake()
        if STAGE in ("export", "all", "reexport"):
            stage_export()
        if STAGE == "layout":                            # the layout file alone (no GLB), for the check before a bake
            import export_scene
            export_scene.write(SCENE, world_json(SCENE))
        if STAGE in ("axes", "all"):
            stage_axes()
        if STAGE in ("check", "all", "reexport", "layout"):
            stage_check()
        if STAGE in ("render", "all", "preview"):
            stage_render()
            save_blend()
        print(f"==== {sc} done")


main()
