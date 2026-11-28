"""Dresses and lights the hotel's floor 1, the motel (docs/BLENDER_AREAS.md, section 1, step 2): the two corridor scenes `floor_1_lower` and
`floor_1_upper`, and the two room layouts that load behind their doors, `motel_a` and `motel_b` (docs/renders/floor_1_lower/README.md).

    blender -b --factory-startup --python tools/blender/build_hotel_floor1.py -- --scenes floor_1_lower,floor_1_upper,motel_a,motel_b --stage all
    blender -b --factory-startup blender/scenes/<scene>.blend --python tools/blender/build_hotel_floor1.py -- --scenes <scene> --stage bake|export|axes|check|render
    python tools/blender/build_hotel_floor1.py --pack <scene> [--work <dir>]           (no Blender: WebP lightmaps and textures -> world/)

Stages: art (the layout objects from the greybox, the art, the lights; saves blender/scenes/<scene>.blend) -> bake (the seen faces and the merged
props on fixed lightmap PAGES, Cycles, OIDN, 8-bit PNGs in the work folder) -> export (the GLB to the work folder; the layout through
tools/blender/export_scene.py, which must write the greybox's file unchanged) -> axes (the marker-cube check) -> check (tools/blender/check_layout.py)
-> render (docs/renders/<scene>/1_arrival, 2_wide, 3_detail.jpg and plan.jpg). `all` runs them in that order; `--scenes` takes several, built one
after the other in one Blender (the file is reset between them).

The layout is the greybox's, unchanged (tools/blender/build_hotel_greybox.py): every COL_ box, DoorLeaf_, Link_/Arrive_, Marker_ and Spot_ is made
from its model with the same names and numbers. What is seen of the shell is tools/blender/hotel_floor1_skin.py's skin: only the faces of those boxes
that look into the air. The art around it is this file's: the motel's carpet runner, two-tone vinyl walls and chair rail, wood-look doors with brass
numbers and peepholes, drum-shade sconces (Lamp_Emit), a built-in ice machine, a fire extinguisher cabinet, a water-stained popcorn ceiling, the EXIT
signs (Emergency_Emit) at the stairwell, and in the rooms a bed, nightstand and lamp, a TV on a dresser, a bathroom door and curtains over a window
that faces nothing.

The door leaves are reused meshes: the twenty room doors of both levels are one mesh (`Leaf_Room`), the closets another, the fire doors a third; each
leaf is its own node with its origin at the hinge, so the page swings it by name. The brass numbers are small child nodes of their leaf. One leaf of
each kind is baked (`BAKE_LEAF`); the others show the same lightmap, which fits because every door has a sconce 2 m to either side.

The connector kit (blender/kit/README.md) is in the greybox's model (build_hotel_greybox._f1, kit_layout): on the lower level the kit's elevator at
(-20, 0, 0), yaw 90 (its car and landing colliders, its door record `lift`, its two spots), and the kit's stair door at every stair door, yaw -90
(only its door record: 1.1 m openings, a 1.04 m by 2.12 m leaf). The layout objects are made from the model as before. place_kit() then places
the pieces with tools/blender/kit_place.py, checks that every layout object it brings lands where the model has it, and keeps the elevator's art
and lamps as bake and still stand-ins (Bake_Standins, never in this GLB: the page draws world/kit/elevator.glb). The stair leaves are this
scene's own (`Leaf_Fire`, at the kit's size and hinge). DoorLeaf_lift stays an empty (the layout keeps its entry).

Light: the corridors are baked at night (sconces and exit signs on); the rooms are baked with their lamps on and the door open onto a stand-in of the
corridor (the same sconces 2 m either side), so a room fits whichever door it sits behind, on either side, on either level.
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import hotel_floor1_skin as SK  # noqa: E402
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
KIND = None           # "corridor" | "room"

# fixed lightmap pages per scene: [shell, props] (found by --stage size: the smallest page giving >= 36 px/m, then kept)
PAGES = {"floor_1_lower": [2048, 2048], "floor_1_upper": [2048, 2048], "motel_a": [1024, 1024], "motel_b": [1024, 1024]}
BAKE_LEAF = {"floor_1_lower": {"Leaf_Room": "DoorLeaf_room_103", "Leaf_Closet": "DoorLeaf_closet_4", "Leaf_Fire": "DoorLeaf_stairwell"},
             "floor_1_upper": {"Leaf_Room": "DoorLeaf_room_113", "Leaf_Closet": "DoorLeaf_closet_4", "Leaf_Fire": "DoorLeaf_stairs_down"}}
WHITE_CAP = 12.0       # a map's white point: its 99.5th percentile texel, at most 12 x its 90th (the galleries' rule)
SHOULDER = (70.0, 2.5)  # the bake's highlight shoulder: light above the map's 70th percentile k rolls off toward 2.5k (sconce scallops, lamp pools)

# the lights (Cycles watts) and the toggled materials' strengths; tuned on the first bake against the brief's brightness limits
SCONCE_W, SHADE_EMIT, STAIR_W, EXIT_EMIT = 60.0, 3.0, 60.0, 5.0
LAMP_W, DOME_W, BATH_W = 50.0, 110.0, 35.0


def work():
    p = Path(arg("--work", str(Path(os.environ.get("TEMP", tempfile.gettempdir())) / "farway_hotel_floor1")))
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


def gen_runner():
    """The corridor's carpet: 8.8 m along (u) by its 2.2 m width (v). A navy border with gold lines along both walls; a maroon field with a gold
    diamond lattice and teal centres; worn paler and flatter down the middle where people walk; grime and a few old stains."""
    H, W = 512, 2048
    rng = np.random.default_rng(101)
    v = (np.arange(H) + 0.5) / H * 2.2
    u = (np.arange(W) + 0.5) / W * 8.8
    Y, X = np.meshgrid(v, u, indexing="ij")
    field, gold, teal, navy = col(96, 30, 38), col(150, 112, 56), col(38, 82, 86), col(34, 40, 62)
    img = np.broadcast_to(field, (H, W, 3)).copy()
    P = 0.55
    lx = np.mod(X, P) - P / 2
    ly = np.mod(Y - 1.1, P) - P / 2
    d = np.abs(lx) + np.abs(ly)
    img = lerp(img, gold, smooth(0.016, 0.006, np.abs(d - 0.2)))
    img = lerp(img, teal, smooth(0.085, 0.07, d))
    img = lerp(img, gold, smooth(0.03, 0.02, d))
    cx = np.minimum(np.abs(np.abs(lx) - P / 2), 1) + np.minimum(np.abs(np.abs(ly) - P / 2), 1)
    img = lerp(img, teal, smooth(0.05, 0.035, cx))
    e = np.minimum(Y, 2.2 - Y)
    bord = e < 0.24
    img[bord] = navy
    for a0, a1 in ((0.065, 0.085), (0.195, 0.212)):
        m = (e >= a0) & (e < a1)
        img[m] = gold * 0.92
    n = vnoise(H, W, rng, 6, 3)
    fine = vnoise(H, W, rng, 3, 64)
    wear = np.exp(-((Y - 1.1) / 0.42) ** 2) * (0.45 + 0.55 * n)
    img = lerp(img, col(122, 92, 84), 0.42 * wear)
    img *= (0.86 + 0.26 * fine)[..., None]
    img *= (0.9 + 0.2 * n)[..., None]
    for _ in range(9):
        sx, sy, r = rng.random() * 8.8, 0.35 + rng.random() * 1.5, 0.05 + rng.random() * 0.14
        dd = np.sqrt(((X - sx + 4.4) % 8.8 - 4.4) ** 2 / 1.6 + (Y - sy) ** 2) / r
        img *= (1 - 0.32 * smooth(1.0, 0.6, dd + 0.25 * (n - 0.5)))[..., None]
    return np.clip(img, 0, 1)


def gen_field():
    """The alcoves' and closets' carpet: the runner's maroon with small gold flecks, 1 m square."""
    H = W = 512
    rng = np.random.default_rng(102)
    n = vnoise(H, W, rng, 5, 4)
    fine = vnoise(H, W, rng, 3, 96)
    img = np.broadcast_to(col(90, 30, 36), (H, W, 3)).copy()
    img = lerp(img, col(140, 104, 54), smooth(0.83, 0.9, fine) * 0.8)
    img *= (0.85 + 0.3 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_room_carpet():
    """The rooms' carpet: a brown and rust 1970s loop pattern on a tan ground, 2 m square, flattened in a walked lane."""
    H = W = 1024
    rng = np.random.default_rng(103)
    t = (np.arange(H) + 0.5) / H * 2.0
    Y, X = np.meshgrid(t, t, indexing="ij")
    img = np.broadcast_to(col(112, 80, 52), (H, W, 3)).copy()
    P = 0.25
    lx, ly = np.mod(X, P) - P / 2, np.mod(Y, P) - P / 2
    r = np.sqrt(lx ** 2 + ly ** 2)
    img = lerp(img, col(136, 66, 38), smooth(0.012, 0.004, np.abs(r - 0.07)))
    sq = np.maximum(np.abs(lx), np.abs(ly))
    img = lerp(img, col(150, 116, 56), smooth(0.008, 0.003, np.abs(sq - 0.118)) * 0.8)
    n = vnoise(H, W, rng, 6, 4)
    fine = vnoise(H, W, rng, 3, 128)
    img *= (0.84 + 0.3 * fine)[..., None]
    img *= (0.88 + 0.24 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_bedspread():
    """A quilted floral bedspread: teal ground, dusky rose flowers with mustard hearts, green leaves, diamond quilting, 1 m square."""
    H = W = 1024
    rng = np.random.default_rng(104)
    t = (np.arange(H) + 0.5) / H
    Y, X = np.meshgrid(t, t, indexing="ij")
    img = np.broadcast_to(col(50, 88, 96), (H, W, 3)).copy()
    for _ in range(26):
        cx, cy, s = rng.random(), rng.random(), 0.035 + rng.random() * 0.03
        dx = (X - cx + 0.5) % 1 - 0.5
        dy = (Y - cy + 0.5) % 1 - 0.5
        ang = np.arctan2(dy, dx)
        rr = np.sqrt(dx ** 2 + dy ** 2)
        leaf = smooth(s * 2.4, s * 1.9, rr) * smooth(0.55, 0.85, np.cos(2 * (ang - rng.random() * 3)))
        img = lerp(img, col(74, 112, 70), leaf * 0.9)
        petal = s * (0.75 + 0.35 * np.cos(5 * ang + rng.random() * 6))
        img = lerp(img, col(168, 92, 110), smooth(petal, petal * 0.85, rr))
        img = lerp(img, col(196, 150, 70), smooth(s * 0.3, s * 0.2, rr))
    q = 0.125
    dd = np.minimum(np.abs(np.mod(X + Y, q) - q / 2), np.abs(np.mod(X - Y, q) - q / 2))
    img *= (1 - 0.22 * smooth(0.004, 0.001, np.abs(dd - q / 2)))[..., None]
    n = vnoise(H, W, rng, 4, 4)
    img *= (0.9 + 0.18 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_wallcover():
    """Vinyl wallcovering, 1 m square: the repo's neutral painted plaster with faint vertical stripes and a fine linen grain."""
    src = load_pixels("main_floor/wall_paint_diff.jpg")
    H, W = src.shape[:2]
    rng = np.random.default_rng(105)
    x = (np.arange(W) + 0.5) / W
    stripe = 1 - 0.035 * (np.mod(x, 0.06) < 0.03) - 0.06 * smooth(0.004, 0.0015, np.abs(np.mod(x, 0.3) - 0.15))
    grain = vnoise(H, W, rng, 2, 160)
    img = src * stripe[None, :, None] * (0.95 + 0.1 * grain)[..., None]
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


def gen_tile():
    """White 15 cm bathroom tiles with grey grout, 0.9 m square."""
    H = W = 1024
    rng = np.random.default_rng(106)
    t = (np.arange(H) + 0.5) / H * 0.9
    Y, X = np.meshgrid(t, t, indexing="ij")
    gx = np.minimum(np.mod(X, 0.15), 0.15 - np.mod(X, 0.15))
    gy = np.minimum(np.mod(Y, 0.15), 0.15 - np.mod(Y, 0.15))
    g = np.minimum(gx, gy)
    tid = (np.floor(X / 0.15) * 7 + np.floor(Y / 0.15) * 13) % 6
    base = 0.9 + 0.02 * tid[..., None]
    img = np.broadcast_to(col(226, 224, 214), (H, W, 3)) * base / 0.95
    img = lerp(img, col(150, 146, 136), smooth(0.003, 0.0012, g))
    n = vnoise(H, W, rng, 4, 4)
    img *= (0.94 + 0.08 * n)[..., None]
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
    c = col(40, 24, 18) if dark else col(128, 92, 52)
    rgb = np.broadcast_to(c, (size, size, 3)) * (0.85 + 0.3 * n)[..., None]
    a = np.clip(0.28 * inside + 0.55 * rim * smooth(0.85, 0.6, r), 0, 0.85) * (0.5 if dark else 1.0)
    return np.concatenate([np.clip(rgb, 0, 1), a[..., None]], axis=2)


def gen_prints():
    """Four generic motel prints in one 2 x 2 atlas (512 x 384 each): a seascape, hills at dusk, a vase of flowers, soft abstract bands."""
    H, W = 768, 1024
    img = np.zeros((H, W, 3))
    rng = np.random.default_rng(107)
    h, w = 384, 512
    y = (np.arange(h) + 0.5) / h
    x = (np.arange(w) + 0.5) / w
    Y, X = np.meshgrid(y, x, indexing="ij")
    n = vnoise(h, w, rng, 5, 3)
    sea = lerp(lerp(col(64, 92, 120), col(196, 178, 150), smooth(0.45, 1.0, Y)), col(40, 70, 96), smooth(0.47, 0.44, Y))
    sea = lerp(sea, col(236, 214, 170), smooth(0.07, 0.05, np.sqrt((X - 0.68) ** 2 + (Y - 0.6) ** 2)))
    hills = lerp(col(150, 96, 90), col(226, 170, 120), smooth(0.4, 1.0, Y))
    for k, hy in enumerate((0.52, 0.42, 0.3)):
        ridge = hy + 0.06 * np.sin(X * (5 + k * 2) + k) + 0.03 * n
        hills = lerp(hills, col(70 - k * 10, 66 - k * 8, 80 - k * 6), (Y < ridge).astype(float))
    flow = lerp(col(206, 196, 170), col(170, 160, 136), Y)
    vase = (np.abs(X - 0.5) < 0.09 + 0.04 * np.sin(Y * 9)) & (Y < 0.42)
    flow[vase] = col(70, 96, 110)
    for _ in range(9):
        cx, cy = 0.5 + (rng.random() - 0.5) * 0.4, 0.55 + rng.random() * 0.3
        flow = lerp(flow, col(176 + rng.integers(0, 50), 80, 90), smooth(0.05, 0.035, np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)))
    band = lerp(col(90, 110, 120), col(200, 150, 110), 0.5 + 0.5 * np.sin(Y * 7 + X * 2 + 3 * n))
    for i, p in enumerate((sea, hills, flow, band)):
        p = p * (0.9 + 0.12 * n)[..., None]
        r, c = divmod(i, 2)
        img[r * h:(r + 1) * h, c * w:(c + 1) * w] = p
    return np.clip(img * 0.92, 0, 1)


def gen_card():
    """The fire-escape plan on the back of a room door: a white card, a red border, the floor's plan in black, red arrows to the stairs."""
    H, W = 320, 256
    img = np.ones((H, W, 3)) * col(232, 228, 216)
    img[:10], img[-10:], img[:, :10], img[:, -10:] = col(170, 30, 30), col(170, 30, 30), col(170, 30, 30), col(170, 30, 30)
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


def gen_grille():
    H = W = 128
    y = (np.arange(H) + 0.5) / H
    s = smooth(0.12, 0.06, np.abs(np.mod(y * 10, 1) - 0.5))
    img = np.ones((H, W, 3)) * col(200, 198, 190)
    img = lerp(img, col(30, 30, 30), np.broadcast_to(s[:, None], (H, W)))
    img[:6], img[-6:], img[:, :6], img[:, -6:] = col(210, 208, 200), col(210, 208, 200), col(210, 208, 200), col(210, 208, 200)
    return img


def gen_brushed():
    H = W = 256
    rng = np.random.default_rng(108)
    n = vnoise(H, W, rng, 3, 2)
    streak = vnoise(H, 8, rng, 3, 64)
    streak = np.repeat(streak, W // 8, axis=1)
    img = (0.7 + 0.12 * streak + 0.08 * n)[..., None] * np.ones(3)
    return np.clip(img, 0, 1)


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


WALLP, PLAST, WOOD, LINEN, FTILE = "main_floor/wall_paint_diff.jpg", "laboratory/wall_paint_diff.jpg", "apartment/dark_wood_diff_1k.jpg", \
    "apartment/rough_linen_diff_512.jpg", "main_floor/floor_tiles_diff.jpg"
WARM = (1.0, 0.78, 0.52)


def make_materials():
    g = {k: mk_image(k, f()) for k, f in (("gen_wallcover", gen_wallcover), ("gen_brushed", gen_brushed), ("gen_prints", gen_prints),
                                          ("gen_grille", gen_grille), ("gen_stain_ceiling", lambda: gen_stain(201)),
                                          ("gen_stain_floor", lambda: gen_stain(202, 256, True)))}
    # shared by every scene
    material("Ceiling_Popcorn" if KIND == "corridor" else "Ceiling_Room", tex=PLAST, tint=srgb_lin("#e6dcc4"), rough=0.95, tile=1.2)
    material("Lamp_Emit", color=(1.0, 0.9, 0.74), rough=0.9, emit=(WARM, SHADE_EMIT))
    material("Brass", img=g["gen_brushed"], tint=srgb_lin("#b48c4c"), rough=0.35, metal=0.9, tile=0.3)
    material("Steel", img=g["gen_brushed"], tint=srgb_lin("#a6a8a6"), rough=0.35, metal=0.9, tile=0.4)
    material("Plastic_White", color=srgb_lin("#d6d2c6"), rough=0.5)
    material("Plastic_Black", color=srgb_lin("#1a1a1a"), rough=0.4)
    material("Grille", img=g["gen_grille"], rough=0.6, tile=0.3)
    material("Trim_Wood", tex=WOOD, tint=(1.0, 0.86, 0.74), rough=0.5, tile=0.8)
    material("Picture", img=g["gen_prints"], rough=0.6)
    material("Frame_Gilt", img=g["gen_brushed"], tint=srgb_lin("#9c7a3c"), rough=0.4, metal=0.6, tile=0.2)
    material("Glass_Clear", color=(0.85, 0.92, 0.95), rough=0.05, alpha=0.16)
    if KIND == "corridor":
        g2 = {k: mk_image(k, f()) for k, f in (("gen_runner", gen_runner), ("gen_field", gen_field), ("gen_block", gen_block), ("gen_card", gen_card))}
        material("Carpet_Runner", img=g2["gen_runner"], rough=1.0)
        material("Carpet_Field", img=g2["gen_field"], rough=1.0, tile=1.0)
        material("Wall_Upper", img=g["gen_wallcover"], tint=srgb_lin("#e4d4b2"), rough=0.7, tile=1.0)
        material("Wall_Lower", img=g["gen_wallcover"], tint=srgb_lin("#c2aa80"), rough=0.6, tile=1.0)
        material("Closet_Paint", tex=WALLP, tint=srgb_lin("#bdb6a0"), rough=0.9, tile=1.5)
        material("Door_Jamb", tex=WOOD, tint=(1.0, 0.86, 0.74), rough=0.5, tile=0.8)
        material("Threshold", img=g["gen_brushed"], tint=srgb_lin("#8c6c3c"), rough=0.4, metal=0.8, tile=0.3)
        material("Lift_Shaft", tex=WALLP, tint=srgb_lin("#4a4c4c"), rough=0.6, tile=1.0)
        material("Lift_Ceiling", tex=WALLP, tint=srgb_lin("#3c3e3e"), rough=0.6, tile=1.0)
        material("Lift_Steel", img=g["gen_brushed"], tint=srgb_lin("#9a9c9a"), rough=0.35, metal=0.9, tile=0.4)
        material("Jamb_Steel", tex=WALLP, tint=srgb_lin("#6e7668"), rough=0.5, tile=1.0)
        material("Stair_Concrete", tex="factory_floor/concrete_floor_diff.jpg", tint=srgb_lin("#c8c4b8"), rough=0.8, tile=1.5)
        material("Stair_Paint", img=g2["gen_block"], tint=srgb_lin("#b4bca6"), rough=0.8, tile=1.6)
        material("Stair_Ceiling", tex=WALLP, tint=srgb_lin("#c4c6b8"), rough=0.9, tile=1.5)
        material("Skirting", color=srgb_lin("#3a2c24"), rough=0.5)
        material("Lamp_Dead", color=srgb_lin("#a49c88"), rough=0.9)
        material("Leaf_Room", tex=WOOD, tint=(1.0, 0.9, 0.8), rough=0.45, tile=0.9)
        material("Leaf_Brass", img=g["gen_brushed"], tint=srgb_lin("#b8904e"), rough=0.3, metal=0.9, tile=0.2)
        material("Leaf_Card", img=g2["gen_card"], rough=0.6)
        material("Leaf_Fire", tex=WALLP, tint=srgb_lin("#8c8e7c"), rough=0.5, tile=1.0)
        material("Leaf_Closet", tex=WALLP, tint=srgb_lin("#cfc8b2"), rough=0.7, tile=1.0)
        material("Leaf_Glass", color=srgb_lin("#2a3234"), rough=0.2)
        material("Ice_Steel", img=g["gen_brushed"], tint=srgb_lin("#b6b8b4"), rough=0.3, metal=0.9, tile=0.5)
        material("Red_Paint", color=srgb_lin("#9a2018"), rough=0.4)
        material("Emergency_Emit", color=(0.9, 0.1, 0.08), rough=0.4, emit=((1.0, 0.08, 0.05), EXIT_EMIT))
        material("Decal_Ceiling", img=g["gen_stain_ceiling"], rough=1.0, img_alpha=True)
        material("Decal_Floor", img=g["gen_stain_floor"], rough=1.0, img_alpha=True)
        material("Standin_Grey", color=(0.4, 0.38, 0.34), rough=0.9)
    else:
        g2 = {k: mk_image(k, f()) for k, f in (("gen_room_carpet", gen_room_carpet), ("gen_bedspread", gen_bedspread), ("gen_tile", gen_tile))}
        material("Carpet_Room", img=g2["gen_room_carpet"], rough=1.0, tile=2.0)
        material("Wall_Room", tex=WALLP, tint=srgb_lin("#dccaa6"), rough=0.85, tile=1.5)
        material("Tile_Floor", tex=FTILE, tint=srgb_lin("#d8d4c8"), rough=0.4, tile=1.2)
        material("Tile_Wall", img=g2["gen_tile"], rough=0.3, tile=0.9)
        material("Wood_Laminate", tex=WOOD, tint=(1.0, 0.92, 0.84), rough=0.45, tile=0.8)
        material("Bedspread", img=g2["gen_bedspread"], rough=0.95, tile=1.0)
        material("Linen_White", tex=LINEN, tint=srgb_lin("#f2e8dc"), rough=0.95, tile=0.6)
        material("Curtain", tex=LINEN, tint=srgb_lin("#a07848"), rough=0.95, tile=0.5)
        material("Lamp_Base", color=srgb_lin("#8a7656"), rough=0.4)
        material("TV_Plastic", color=srgb_lin("#1c1c1c"), rough=0.45)
        material("TV_Screen", color=srgb_lin("#1e2624"), rough=0.15)
        material("Mirror", color=srgb_lin("#9aa4a8"), rough=0.08, metal=0.8)
        material("Window_Frame", img=g["gen_brushed"], tint=srgb_lin("#a4a49e"), rough=0.4, metal=0.7, tile=0.4)
        material("Window_Void", color=srgb_lin("#151719"), rough=0.6)
        material("Porcelain", color=srgb_lin("#e6e4dc"), rough=0.2)
        material("Door_Bath", tex=WOOD, tint=(1.0, 0.9, 0.8), rough=0.45, tile=0.9)
        material("SB_Carpet", color=srgb_lin("#4a1c20"), rough=1.0)
        material("SB_Wall", color=srgb_lin("#a8946c"), rough=0.8)
        material("SB_Ceiling", color=srgb_lin("#c8bea6"), rough=0.9)
        material("Standin_Grey", color=(0.4, 0.38, 0.34), rough=0.9)


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
    """An open tube (no caps), double-walled 3 mm so both sides render solid."""
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


# ---------------------------------------------------------------- the skin (the shell as seen)
def build_skin():
    q, M = SK.scene_skin(SCENE)
    matf = SK.corridor_material if KIND == "corridor" else SK.room_material
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
            if mname == "Carpet_Runner":
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
    """kind Leaf_Room: the leaf lies on the corridor side of its hinge (local -Y is the corridor); Leaf_Closet and Leaf_Fire lie behind theirs
    (local +Y), their corridor face flush with the wall (local y = 0). Local +X runs from the hinge along the leaf; z is up."""
    if kind in LEAF_MESH:
        return LEAF_MESH[kind]
    bm = bmesh.new()
    th = 0.045
    y0, y1 = (-th, 0.0) if kind == "Leaf_Room" else (0.0, th)
    front = y0 if kind == "Leaf_Room" else y1 * 0          # the corridor face's local y
    fs = -1                                                  # the corridor face's normal: -Y for every kind
    w, h = width - 0.006, height - 0.008

    def bx(x0, x1, ya, yb, z0, z1, mat):
        mm = bmesh.new()
        mm.loops.layers.uv.new("UVMap")
        bmesh.ops.create_cube(mm, size=1.0, matrix=Matrix.Translation(((x0 + x1) / 2, (ya + yb) / 2, (z0 + z1) / 2)) @ Matrix.Diagonal((x1 - x0, yb - ya, z1 - z0, 1)))
        return mm, mat

    pieces = []
    pieces.append(bx(0.003, w, y0, y1, 0.006, h, kind))
    yf = y0 if kind == "Leaf_Room" else 0.0
    yb = 0.0 if kind == "Leaf_Room" else th
    if kind == "Leaf_Room":
        pieces.append(bx(0.035, w - 0.035, yf - 0.002, yf, 0.03, 0.22, "Leaf_Brass"))          # kick plate
        hx = w - 0.075
        for side, yy in ((-1, yf), (1, yb)):                                                  # knob roses and knobs, both faces; deadbolt above
            pieces.append(bx(hx - 0.032, hx + 0.032, *(sorted((yy, yy + side * 0.008))), 0.92, 0.98, "Leaf_Brass"))
            pieces.append(bx(hx - 0.022, hx + 0.022, *(sorted((yy + side * 0.008, yy + side * 0.06))), 0.93, 0.97, "Leaf_Brass"))
            pieces.append(bx(hx - 0.024, hx + 0.024, *(sorted((yy, yy + side * 0.012))), 1.12, 1.17, "Leaf_Brass"))
        pc = w / 2
        pieces.append(bx(pc - 0.014, pc + 0.014, yf - 0.006, yb + 0.004, 1.5, 1.528, "Leaf_Brass"))        # the peephole's barrel and rings
        pieces.append(bx(pc - 0.006, pc + 0.006, yf - 0.0065, yf - 0.006, 1.508, 1.52, "Leaf_Glass"))
        pieces.append(bx(pc - 0.09, pc + 0.09, yb, yb + 0.002, 1.32, 1.55, "Leaf_Card"))                    # the fire-escape plan, room side
    elif kind == "Leaf_Closet":
        for zz0, zz1 in ((0.12, 0.98), (1.12, h - 0.1)):                                    # two louvred panels
            pieces.append(bx(0.08, w - 0.08, -0.004, 0.0, zz0 - 0.02, zz0, "Leaf_Closet"))
            pieces.append(bx(0.08, w - 0.08, -0.004, 0.0, zz1, zz1 + 0.02, "Leaf_Closet"))
            n = int((zz1 - zz0) / 0.05)
            for k in range(n):
                z = zz0 + (k + 0.5) * (zz1 - zz0) / n
                pieces.append(bx(0.1, w - 0.1, -0.012, -0.002, z - 0.008, z + 0.008, "Leaf_Closet"))
        hx = w - 0.07
        pieces.append(bx(hx - 0.02, hx + 0.02, -0.055, -0.0, 0.93, 0.97, "Leaf_Brass"))
    else:                                                                                    # the fire door: a steel leaf, a vision panel, a lever
        pieces.append(bx(w - 0.32, w - 0.16, -0.002, th + 0.002, 1.2, 1.85, "Leaf_Glass"))
        hx = w - 0.08
        for yy, sd in ((0.0, -1), (th, 1)):
            pieces.append(bx(hx - 0.03, hx + 0.03, *sorted((yy, yy + sd * 0.01)), 0.92, 1.1, "Steel"))
            pieces.append(bx(hx - 0.16, hx + 0.01, *sorted((yy + sd * 0.01, yy + sd * 0.05)), 1.0, 1.025, "Steel"))
        pieces.append(bx(0.05, 0.5, -0.06, -0.0, h - 0.09, h - 0.05, "Steel"))               # the closer arm along the head (corridor side)
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


def box_uv_local(bm, tile):
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            u, v = (p.y, p.z) if ax == 0 else (p.x, p.z) if ax == 1 else (p.x, p.y)
            lp[uvl].uv = (u / tile, v / tile)


def build_leaves(M):
    leaves = {}
    for d in M.doors:
        p = d["props"]
        name = d["name"]
        if p.get("kind") == "elevator":                    # the kit's elevator doors go here: the layout keeps the entry, the GLB has no leaf
            ob = bpy.data.objects.new(name, None)
            ob.empty_display_type = "ARROWS"
            ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
            LAYOUT.objects.link(ob)
        else:
            kind = "Leaf_Room" if "room" in p else "Leaf_Closet" if p.get("kind") == "closet" else "Leaf_Fire"
            ob = bpy.data.objects.new(name, leaf_mesh(kind, p["width"], p["height"]))
            ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
            DOORS.objects.link(ob)
            leaves[name] = ob
            if "room" in p:
                door_number(ob, p["room"], p["width"])
        for k, v in p.items():
            ob[k] = v
    return leaves


def door_number(leaf, num, width):
    """The room's brass number on the corridor face, 1.66 m up: a child node of the leaf, so it swings with it."""
    bm = bmesh.new()
    me = text_mesh(num, 0.085, 0.0025, 1.05)
    tmp = bmesh.new()
    tmp.from_mesh(me)
    bpy.data.meshes.remove(me)
    M = Matrix(((1, 0, 0, (width - 0.006) / 2), (0, 0, -1, -0.045 - 0.0026), (0, 1, 0, 1.68), (0, 0, 0, 1)))   # text x -> +X, up -> +Z, toward the reader -> -Y
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


# ---------------------------------------------------------------- the corridor's dressing
def sconce(w, a, tag, dead=False, coll=None):
    y = SK.SCONCE_Y
    coll = coll or PROPS
    part(f"Sconce_{tag}_Plate", "Brass", lambda bm: w.box(bm, a - 0.05, a + 0.05, y - 0.11, y + 0.07, 0.0, 0.014), coll)
    part(f"Sconce_{tag}_Arm", "Brass", lambda bm: cyl(bm, w.pt(a, y - 0.04, 0.012), w.pt(a, y - 0.04, 0.14), 0.009, seg=10), coll)
    part(f"Sconce_{tag}_Cup", "Brass", lambda bm: cyl(bm, w.pt(a, y - 0.06, 0.15), w.pt(a, y - 0.03, 0.15), 0.03, 0.02, seg=14), coll)
    part(f"Sconce_{tag}_Shade", "Lamp_Dead" if dead else "Lamp_Emit",
         lambda bm: tube(bm, w.pt(a, y - 0.085, 0.15), w.pt(a, y + 0.085, 0.15), 0.1, 0.078, seg=28), coll, recalc=False)
    if not dead:
        light(f"L_sconce_{tag}", "POINT", w.pt(a, y - 0.005, 0.15), SCONCE_W, size=0.03)


def door_casing(w, a, half, top, tag, mat="Trim_Wood", width=0.07, proud=0.018):
    part(f"Casing_{tag}_L", mat, lambda bm: w.box(bm, a - half - width, a - half, 0.0, top + width, 0.0, proud))
    part(f"Casing_{tag}_R", mat, lambda bm: w.box(bm, a + half, a + half + width, 0.0, top + width, 0.0, proud))
    part(f"Casing_{tag}_Head", mat, lambda bm: w.box(bm, a - half - width, a + half + width, top, top + width, 0.0, proud))


def wall_runs(side, M):
    """The corridor wall's runs between openings along `side` (N or S): [(a0, a1)], for the skirting and the chair rail."""
    holes = []
    for num, lay, s, a in SK.room_doors(M):
        if s == side:
            holes.append((a - GB.DOOR_W / 2 - 0.07, a + GB.DOOR_W / 2 + 0.07))
    for kind, s, a in SK.features(M):
        if s == side:
            hw = 0.4 + 0.07 if kind == "closet" else 0.6
            holes.append((a - hw, a + hw))
    for what, s, x0, x1, y0, y1, d in SK.recesses(SCENE):
        if s == side and what == "ice":
            holes.append((x0 - 0.04, x1 + 0.04))
    holes.sort()
    runs, a = [], -GB.CORR_X
    for h0, h1 in holes:
        if h0 > a:
            runs.append((a, h0))
        a = max(a, h1)
    if a < GB.CORR_X:
        runs.append((a, GB.CORR_X))
    return runs


def build_corridor(M):
    X, Z, H = GB.CORR_X, GB.CORR_Z, GB.CORR_H
    lower = SCENE.endswith("lower")
    # skirting and chair rail along both long walls; skirting round the alcoves and the ends
    for side in ("N", "S"):
        w = corridor_wall(side)
        for i, (a0, a1) in enumerate(wall_runs(side, M)):
            part(f"Skirting_{side}_{i}", "Skirting", lambda bm: w.box(bm, a0, a1, 0.0, 0.1, 0.0, 0.012))
            part(f"ChairRail_{side}_{i}", "Trim_Wood", lambda bm: w.box(bm, a0, a1, SK.CHAIR - 0.03, SK.CHAIR + 0.035, 0.0, 0.022))
    for side in ("E", "W"):
        w = corridor_wall(side)
        gap = SK.STAIR_W / 2 + 0.07 if side == "E" else 0.6 + 0.08
        if side == "W" and not lower:
            gap = 0.0
        for i, (a0, a1) in enumerate([(-Z, -gap), (gap, Z)] if gap else [(-Z, Z)]):
            part(f"Skirting_{side}_{i}", "Skirting", lambda bm: w.box(bm, a0, a1, 0.0, 0.1, 0.0, 0.012))
            part(f"ChairRail_{side}_{i}", "Trim_Wood", lambda bm: w.box(bm, a0, a1, SK.CHAIR - 0.03, SK.CHAIR + 0.035, 0.0, 0.022))
    # room doors: casings (the leaves and their numbers are build_leaves')
    for num, lay, side, a in SK.room_doors(M):
        door_casing(corridor_wall(side), a, GB.DOOR_W / 2, GB.DOOR_H, f"room_{num}")
    for kind, side, a in SK.features(M):
        w = corridor_wall(side)
        if kind == "closet":
            door_casing(w, a, 0.4, GB.DOOR_H, f"closet_{side}{int(a)}")
            part(f"Plaque_closet_{side}{int(a)}", "Plastic_White", lambda bm: w.box(bm, a - 0.12, a + 0.12, 2.24, 2.32, 0.0, 0.008))
            part(f"Plaque_closet_{side}{int(a)}_t", "Plastic_Black",
                 lambda bm: wall_text(bm, w, "STAFF", a, 2.28, 0.008, 0.05, 0.002, 1.1))
            alcove_light(side, a, f"closet_{side}{int(a)}", dead=True)
        else:
            alcove_dress(side, a)
    # the east end: the stair door's casing, a STAIRS plaque, the EXIT sign
    we = corridor_wall("E")
    door_casing(we, 0.0, SK.STAIR_W / 2, GB.DOOR_H, "stairdoor", "Jamb_Steel", 0.06, 0.015)
    exit_sign(we, 0.0, 2.27, "corridor")
    wn = corridor_wall("N")
    part("Plaque_stairs", "Plastic_White", lambda bm: wn.box(bm, 19.28, 19.72, 1.45, 1.6, 0.0, 0.008))
    part("Plaque_stairs_t", "Plastic_Black", lambda bm: wall_text(bm, wn, "STAIRS", 19.5, 1.525, 0.008, 0.07, 0.002, 1.05))
    # the sconces
    for side, x, dead in SK.sconces(SCENE, M):
        sconce(corridor_wall(side), x, f"{side}{int(x):+d}", dead)
    # pictures opposite the alcoves and closets
    rng = np.random.default_rng(11 if lower else 12)
    for i, (kind, side, a) in enumerate(SK.features(M)):
        other = "S" if side == "N" else "N"
        picture(corridor_wall(other), a, 1.5, 0.62, 0.47, f"{other}{int(a):+d}", i % 4)
    # the ceiling: smoke detectors, return grilles, water stains; the carpet's stains
    for x in (-15.0, -5.0, 5.0, 15.0):
        part(f"Smoke_{int(x):+d}", "Plastic_White", lambda bm: cyl(bm, (x, H - 0.035, 0.0), (x, H, 0.0), 0.065, seg=20))
    for x in (-10.0, 10.0):
        part(f"Grille_{int(x):+d}", "Grille", lambda bm: cube(bm, (x - 0.2, H - 0.008, -0.2), (x + 0.2, H, 0.2)), tile=0.4)
        fix_uv_square(f"Grille_{int(x):+d}")
    stains = [(-16.7, 0.3, 0.9), (-6.3, -0.4, 1.4), (3.2, 0.2, 0.7), (11.6, -0.1, 1.8), (17.9, 0.5, 1.1)] if lower else \
             [(-17.4, -0.3, 1.2), (-9.1, 0.4, 0.8), (-1.2, -0.2, 1.6), (7.7, 0.1, 1.0), (14.4, -0.5, 0.9), (19.2, 0.2, 1.3)]
    for i, (x, z, s) in enumerate(stains):
        decal(f"decor_stain_ceiling_{i}", "Decal_Ceiling", x, z, s, H - 0.003, down=True, rot=i * 1.3)
    fl = [(-12.8, 0.25, 0.7), (-2.6, -0.3, 0.5), (6.9, 0.4, 0.6), (13.3, -0.1, 0.9)] if lower else [(-14.9, 0.2, 0.6), (-5.6, -0.35, 0.8), (9.8, 0.3, 0.5)]
    for i, (x, z, s) in enumerate(fl):
        decal(f"decor_stain_floor_{i}", "Decal_Floor", x, z, s, 0.003, rot=i * 2.1)
    for what, side, x0, x1, y0, y1, d in SK.recesses(SCENE):
        if what == "ice":
            ice_machine(corridor_wall(side), x0, x1, y1, d)
            sgn = -1 if side == "N" else 1
            decal("decor_stain_floor_ice", "Decal_Floor", (x0 + x1) / 2, sgn * (Z - 0.32), 0.75, 0.0035, rot=0.4)
        else:
            extinguisher(corridor_wall(side), x0, x1, y0, y1, d)
    # direction sign
    if lower:
        ws = corridor_wall("S")
        sign_plate(ws, -17.35, 1.5, 0.72, 0.16, "101 - 110  >", "dir")
        stairwell_lower(M)
    else:
        sign_plate(corridor_wall("N"), 17.35, 1.5, 0.72, 0.16, "<  111 - 120", "dir")
        picture(corridor_wall("W"), 0.0, 1.5, 0.9, 0.66, "end", 1)
        landing_upper()


def fix_uv_square(name):
    """Give a flat fitting its whole texture once (the grille)."""
    me = bpy.data.objects[name].data
    uv = me.uv_layers["UVMap"].data
    xs = [v.co for v in me.vertices]
    for p in me.polygons:
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            n = p.normal
            ax = max(range(3), key=lambda i: abs(n[i]))
            k = [i for i in range(3) if i != ax]
            lo = [min(c[i] for c in xs) for i in k]
            hi = [max(c[i] for c in xs) for i in k]
            uv[li].uv = tuple((co[k[j]] - lo[j]) / max(hi[j] - lo[j], 1e-6) for j in range(2))


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


def picture(w, a, y, wd, ht, tag, which):
    """A framed print 3 cm off the wall: a gilt frame and one quarter of the print atlas."""
    part(f"Picture_{tag}_Frame", "Frame_Gilt", lambda bm: (w.box(bm, a - wd / 2, a + wd / 2, y - ht / 2, y - ht / 2 + 0.035, 0, 0.03),
                                                             w.box(bm, a - wd / 2, a + wd / 2, y + ht / 2 - 0.035, y + ht / 2, 0, 0.03),
                                                             w.box(bm, a - wd / 2, a - wd / 2 + 0.035, y - ht / 2, y + ht / 2, 0, 0.03),
                                                             w.box(bm, a + wd / 2 - 0.035, a + wd / 2, y - ht / 2, y + ht / 2, 0, 0.03)))
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    r, c = divmod(which, 2)
    u0, v0 = c * 0.5, r * 0.5                           # numpy row 0 is the image's bottom row in Blender
    corners = [(a - wd / 2 + 0.035, y - ht / 2 + 0.035, 0.0), (a + wd / 2 - 0.035, y - ht / 2 + 0.035, 1.0),
               (a + wd / 2 - 0.035, y + ht / 2 - 0.035, 2.0), (a - wd / 2 + 0.035, y + ht / 2 - 0.035, 3.0)]
    R = w.right()
    vs = []
    for aa, yy, k in corners:
        vs.append(bm.verts.new(B(w.pt(aa, yy, 0.012))))
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.dot(B(w.normal())) < 0:
        f.normal_flip()
    for lp in f.loops:
        p = lp.vert.co
        g = (p.x, p.z, -p.y)
        along = g[0] if w.axis == "z" else g[2]
        t = (along - (a - wd / 2 + 0.035)) / (wd - 0.07)
        if (R[0] if w.axis == "z" else R[2]) < 0:
            t = 1 - t
        s = (g[1] - (y - ht / 2 + 0.035)) / (ht - 0.07)
        lp[uvl].uv = (u0 + 0.5 * t, v0 + 0.5 * s)
    finish(f"Picture_{tag}", bm, "Picture", PROPS, keep_uv=True)


def sign_plate(w, a, y, wd, ht, text, tag):
    part(f"Sign_{tag}", "Plastic_White", lambda bm: w.box(bm, a - wd / 2, a + wd / 2, y - ht / 2, y + ht / 2, 0.0, 0.01))
    part(f"Sign_{tag}_t", "Plastic_Black", lambda bm: wall_text(bm, w, text, a, y, 0.01, ht * 0.5, 0.002, 1.05))


def exit_sign(w, a, y0, tag):
    """A wall-mounted EXIT sign over a door: a white housing, a red-lit face (Emergency_Emit) with the letters standing out of it."""
    part(f"Exit_{tag}_Housing", "Plastic_White", lambda bm: w.box(bm, a - 0.18, a + 0.18, y0, y0 + 0.2, 0.0, 0.05))
    part(f"Exit_{tag}_Face", "Plastic_Black", lambda bm: w.box(bm, a - 0.165, a + 0.165, y0 + 0.015, y0 + 0.185, 0.05, 0.052))
    part(f"Exit_{tag}_Letters", "Emergency_Emit", lambda bm: wall_text(bm, w, "EXIT", a, y0 + 0.1, 0.052, 0.11, 0.004, 1.1))


def alcove_light(side, a, tag, dead=False):
    """A small ceiling fitting in an alcove or closet (2.4 m): an opal glass box."""
    sg = -1 if side == "N" else 1
    zc = sg * (GB.CORR_Z + GB.T + 0.5)
    part(f"AlcoveLight_{tag}", "Lamp_Dead" if dead else "Lamp_Emit", lambda bm: cube(bm, (a - 0.15, 2.34, zc - 0.1), (a + 0.15, 2.4, zc + 0.1)))
    if not dead:
        light(f"L_alcove_{tag}", "POINT", (a, 2.3, zc), SCONCE_W * 0.4, size=0.05)


def alcove_dress(side, a):
    """An open alcove: carpet, the wallcovering, a coat hook rail above head height, a dim fitting in its ceiling."""
    sg = -1 if side == "N" else 1
    back = Wall("z", sg * (GB.CORR_Z + GB.T + 1.0), -sg)
    part(f"AlcoveRail_{side}{int(a)}", "Trim_Wood", lambda bm: back.box(bm, a - 0.5, a + 0.5, 1.84, 1.93, 0.0, 0.02))
    for k in range(4):
        x = a - 0.36 + k * 0.24
        part(f"AlcoveHook_{side}{int(a)}_{k}", "Brass", lambda bm: back.box(bm, x - 0.012, x + 0.012, 1.82, 1.87, 0.02, 0.07))
    part(f"AlcoveSkirt_{side}{int(a)}", "Skirting", lambda bm: back.box(bm, a - 0.6, a + 0.6, 0.0, 0.1, 0.0, 0.012))
    alcove_light(side, a, f"alcove_{side}{int(a)}")


def recess_box(w, x0, x1, y0, y1, depth, mat, tag):
    """The lining of a recess in the wall: its two sides, head, sill and back, inside the wall's thickness."""
    part(f"Recess_{tag}", mat, lambda bm: (w.box(bm, x0, x0 + 0.01, y0, y1, -depth, 0.0), w.box(bm, x1 - 0.01, x1, y0, y1, -depth, 0.0),
                                           w.box(bm, x0, x1, y1 - 0.01, y1, -depth, 0.0), w.box(bm, x0, x1, max(y0, 0.0), max(y0, 0.0) + 0.01, -depth, 0.0),
                                           w.box(bm, x0, x1, y0, y1, -depth - 0.01, -depth)))


def ice_machine(w, x0, x1, top, depth):
    """A built-in ice machine set into the wall (its front 0 to 4 cm proud): a steel cabinet, a black panel with ICE in white, a dispensing bay
    with a drip grille, a lift-up bin door with a pull."""
    recess_box(w, x0, x1, 0.0, top, depth, "Ice_Steel", "ice")
    a = (x0 + x1) / 2
    part("Ice_Frame", "Ice_Steel", lambda bm: (w.box(bm, x0, x0 + 0.04, 0.0, top, -0.01, 0.03), w.box(bm, x1 - 0.04, x1, 0.0, top, -0.01, 0.03),
                                               w.box(bm, x0, x1, top - 0.05, top, -0.01, 0.03), w.box(bm, x0, x1, 0.0, 0.1, -0.01, 0.025)))
    part("Ice_BinDoor", "Ice_Steel", lambda bm: w.box(bm, x0 + 0.05, x1 - 0.05, 0.12, 0.78, -0.02, 0.01))
    part("Ice_Pull", "Steel", lambda bm: w.box(bm, a - 0.2, a + 0.2, 0.7, 0.73, 0.01, 0.038))
    part("Ice_Bay", "Plastic_Black", lambda bm: w.box(bm, x0 + 0.08, x1 - 0.08, 0.86, 1.2, -0.12, -0.1))
    part("Ice_BayLining", "Ice_Steel", lambda bm: (w.box(bm, x0 + 0.06, x0 + 0.08, 0.84, 1.22, -0.12, 0.0), w.box(bm, x1 - 0.08, x1 - 0.06, 0.84, 1.22, -0.12, 0.0),
                                                   w.box(bm, x0 + 0.06, x1 - 0.06, 1.2, 1.22, -0.12, 0.0)))
    part("Ice_Drip", "Grille", lambda bm: w.box(bm, x0 + 0.08, x1 - 0.08, 0.84, 0.86, -0.12, 0.02), tile=0.1)
    part("Ice_Nozzle", "Plastic_Black", lambda bm: w.box(bm, a - 0.05, a + 0.05, 1.12, 1.2, -0.1, -0.05))
    part("Ice_Panel", "Plastic_Black", lambda bm: w.box(bm, x0 + 0.06, x1 - 0.06, 1.28, top - 0.07, -0.01, 0.012))
    part("Ice_Letters", "Plastic_White", lambda bm: wall_text(bm, w, "ICE", a, 1.42, 0.012, 0.13, 0.004, 1.15))


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
    part("Ext_Hose", "Plastic_Black", lambda bm: cyl(bm, w.pt(a + 0.05, y0 + 0.54, -depth + 0.09), w.pt(a + 0.08, y0 + 0.2, -depth + 0.11), 0.008, seg=8))
    part("Ext_Label", "Red_Paint", lambda bm: w.box(bm, x0 - 0.02, x1 + 0.02, y1 + 0.05, y1 + 0.14, 0.0, 0.006))
    part("Ext_Label_t", "Plastic_White", lambda bm: wall_text(bm, w, "FIRE", a, y1 + 0.095, 0.006, 0.055, 0.002, 1.1))


# the connector kit (blender/kit/README.md), as build_hotel_greybox._f1 puts it in the model: (piece, suffix, at, yaw, art, {kit door: scene door})
KIT = {
    "floor_1_lower": [("elevator", "F1", (-20.0, 0.0, 0.0), 90.0, True, {"lift": "lift"}),
                      ("stair_door", "F1", (20.0, 0.0, 0.0), -90.0, False, {"stair": "stairwell"}),
                      ("stair_door", "F1_top", (26.6, 3.2, 0.0), -90.0, False, {"stair": "stairs_up"})],
    "floor_1_upper": [("stair_door", "F1U", (20.0, 0.0, 0.0), -90.0, False, {"stair": "stairs_down"})],
}
KIT_PREFIX = ("COL_", "DoorLeaf_", "Link_", "Arrive_", "Spot_", "Zone_", "Marker_")
KIT_LIGHTS_DROP = ("Corridor_Lamp",)    # the elevator kit's stand-in corridor light: this scene has its own corridor
KIT_MOVED = {"Spot_call_1_F1"}          # the kit spot the greybox moves 8 cm off the north wall (build_hotel_greybox._f1)


def place_kit(M):
    """Each kit piece through tools/blender/kit_place.py: every layout object it brings that the model has (a kit door renamed to the scene's
    door id) must land where the model put it (the model's own objects are already in Layout, from layout_from_model and build_leaves); then
    the kit's copies are removed, and its art (when used) stays in Bake_Standins with its lamps in Lights: in the bake and the stills, never in
    this scene's GLB."""
    import kit_place
    want = {"COL_" + b["name"]: b for b in M.boxes if b["col"]}
    want.update({e["name"]: e for e in M.empties})
    want.update({d["name"]: d for d in M.doors})
    checked, dropped = 0, []
    for piece, suffix, at, yaw, art, doors in KIT.get(SCENE, []):
        made = kit_place.place(piece, suffix=suffix, at=at, yaw_deg=yaw, art=art, collection=BAKE_STANDIN)
        ren = {f"DoorLeaf_{k}_{suffix}": f"DoorLeaf_{v}" for k, v in doors.items()}
        for nm in made:
            ob = bpy.data.objects[nm]
            if nm.startswith(KIT_PREFIX):
                base = nm.split(".")[0]                  # the model's own object has the name already, so Blender numbered the kit's
                key = ren.get(base, base)
                ref = want.get(key)
                if ref is None:
                    dropped.append(nm)                     # the kit's own links, markers, landing and hallway: the model leaves them out
                elif key not in KIT_MOVED:
                    if "hinge" in ref:
                        assert (ob.matrix_world.translation - B(ref["hinge"])).length < 1e-4, (nm, tuple(ob.matrix_world.translation), ref["hinge"])
                        assert abs(float(ob["closed_yaw_deg"]) - ref["props"]["closed_yaw_deg"]) < 0.05, (nm, ob["closed_yaw_deg"])
                    elif "pos" in ref:
                        assert (ob.matrix_world.translation - B(ref["pos"])).length < 1e-4, (nm, ref["pos"])
                    else:
                        g = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
                        mn = (min(p.x for p in g), min(p.z for p in g), min(-p.y for p in g))
                        mx = (max(p.x for p in g), max(p.z for p in g), max(-p.y for p in g))
                        assert all(abs(mn[i] - ref["min"][i]) < 1e-3 and abs(mx[i] - ref["max"][i]) < 1e-3 for i in range(3)), (nm, mn, mx, ref)
                    checked += 1
                bpy.data.objects.remove(ob)
            elif ob.type != "MESH":
                bpy.data.objects.remove(ob)
        if art:
            kit_lights(piece, at, yaw)
    print(f"KIT {SCENE}: {checked} layout objects from kit_place.py land on the model's; left out {len(dropped)}; stand-ins {len(BAKE_STANDIN.objects)}")


def kit_lights(piece, at, yaw):
    """The kit piece's own lamps (its Lights collection: the car's bulb, the call button's and indicators' glow), moved and turned as kit_place
    moves its art, into this scene's Lights."""
    path = ROOT / f"blender/kit/{piece}.blend"
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.collections = [c for c in src.collections if c == "Lights"]
    m = Matrix.Translation(Vector((at[0], -at[2], at[1]))) @ Matrix.Rotation(math.radians(yaw), 4, "Z")
    for coll in dst.collections:
        for ob in list(coll.objects):
            if ob.name.startswith(KIT_LIGHTS_DROP):
                bpy.data.objects.remove(ob)
                continue
            ob.name = f"Kit_{piece}_{ob.name}"
            ob.matrix_world = m @ ob.matrix_basis.copy()          # appended, in no scene yet: its matrix_world is not evaluated
            LIGHTS.objects.link(ob)
        bpy.data.collections.remove(coll)


def stairwell_lower(M):
    """The stairwell behind the east door: painted block, concrete flights with steel nosings, a steel handrail on each wall, two bulkhead lights,
    the EXIT sign over the door at the top (to floor_1_upper), a FLOOR 1 sign."""
    steps = sorted((b for b in M.boxes if b["name"].startswith("Step_")), key=lambda b: b["min"][0])
    x0, x1 = steps[0]["min"][0], steps[-1]["max"][0]
    rise = steps[-1]["max"][1] / len(steps)
    for i, s in enumerate(steps):
        part(f"Nosing_{i:02d}", "Steel", lambda bm: cube(bm, (s["min"][0], s["max"][1] - 0.012, -0.99), (s["min"][0] + 0.05, s["max"][1] + 0.003, 0.99)))
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
    hw = SK.STAIR_W / 2                                                            # the kit's 1.1 m opening
    part("Casing_stairs_up_Head", "Jamb_Steel", lambda bm: we.box(bm, -hw - 0.06, hw + 0.06, 3.2 + GB.DOOR_H, 3.2 + GB.DOOR_H + 0.06, 0.0, 0.015))
    part("Casing_stairs_up_L", "Jamb_Steel", lambda bm: we.box(bm, -hw - 0.06, -hw, 3.2, 3.2 + GB.DOOR_H + 0.06, 0.0, 0.015))
    part("Casing_stairs_up_R", "Jamb_Steel", lambda bm: we.box(bm, hw, hw + 0.06, 3.2, 3.2 + GB.DOOR_H + 0.06, 0.0, 0.015))
    ws = Wall("z", 1.0, -1)
    part("Sign_floor", "Plastic_White", lambda bm: ws.box(bm, 20.45, 20.95, 1.4, 1.7, 0.0, 0.008))
    part("Sign_floor_t", "Plastic_Black", lambda bm: wall_text(bm, ws, "1", 20.7, 1.56, 0.008, 0.2, 0.003))
    part("Sign_floor_top", "Plastic_White", lambda bm: ws.box(bm, 25.6, 26.2, 4.55, 4.85, 0.0, 0.008))
    part("Sign_floor_top_t", "Plastic_Black", lambda bm: wall_text(bm, ws, "1U", 25.9, 4.7, 0.008, 0.18, 0.003))


def landing_upper():
    """The small landing behind the upper level's stair door: painted block, a bulkhead light, a FLOOR 1 sign and the start of the handrail down."""
    we = Wall("x", 21.6, -1)
    part("Bulkhead_land", "Lamp_Emit", lambda bm: we.box(bm, -0.15, 0.15, 2.3, 2.45, 0.0, 0.08))
    part("Bulkhead_land_cage", "Plastic_Black", lambda bm: we.box(bm, -0.17, 0.17, 2.28, 2.3, 0.0, 0.085))
    light("L_landing", "POINT", we.pt(0.0, 2.37, 0.12), STAIR_W * 0.8, size=0.06)
    part("Sign_floor", "Plastic_White", lambda bm: we.box(bm, -0.3, 0.3, 1.35, 1.65, 0.0, 0.008))
    part("Sign_floor_t", "Plastic_Black", lambda bm: wall_text(bm, we, "1U", 0.0, 1.5, 0.008, 0.18, 0.003))
    wn = Wall("z", -1.0, 1)
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


# ---------------------------------------------------------------- the rooms
def room_build():
    lay = SCENE
    x0, x1, z0, z1 = SK.room_dims(lay)
    H = GB.ROOM_H
    Wn, Wsth, We, Ww = Wall("z", z0, 1), Wall("z", z1, -1), Wall("x", x1, -1), Wall("x", x0, 1)
    # the door from inside: casing, light switch; the leaf's own casing and number are the corridor's
    door_casing(Wsth, 0.0, GB.DOOR_W / 2, GB.DOOR_H, "door", "Wood_Laminate")
    part("Switch", "Plastic_White", lambda bm: Wsth.box(bm, -0.68, -0.6, 1.15, 1.27, 0.0, 0.01) if lay == "motel_b" else Wsth.box(bm, 0.6, 0.68, 1.15, 1.27, 0.0, 0.01))
    # skirting round the bedroom (not across the door)
    runs = {"motel_a": [(Wsth, -1.2, -0.54), (Wsth, 0.54, 2.8), (We, z0, z1), (Wn, 0.7, 2.8), (Ww, -4.2, z1)],
            "motel_b": [(Wsth, -1.2, -0.54), (Wsth, 0.54, 2.5), (We, z0, z1), (Wn, x0, x1), (Ww, z0, -3.01), (Ww, -2.09, -1.5)]}[lay]
    for i, (w, a0, a1) in enumerate(runs):
        part(f"Skirting_{i}", "Wood_Laminate", lambda bm: w.box(bm, a0, a1, 0.0, 0.09, 0.0, 0.012))
    # ceiling light and smoke detector
    if lay == "motel_a":
        cx, cz = 1.0, -2.6
    else:
        cx, cz = 0.0, -3.0
    part("Dome", "Lamp_Emit", lambda bm: cyl(bm, (cx, H - 0.09, cz), (cx, H, cz), 0.16, 0.19, seg=28))
    part("Dome_Rim", "Brass", lambda bm: cyl(bm, (cx, H - 0.012, cz), (cx, H, cz), 0.2, seg=28))
    light("L_dome", "POINT", (cx, H - 0.14, cz), DOME_W, size=0.12)
    part("Smoke", "Plastic_White", lambda bm: cyl(bm, (cx + 0.9, H - 0.035, cz + 1.2), (cx + 0.9, H, cz + 1.2), 0.065, seg=20))
    # the window that faces nothing, its curtains
    wx0, wx1 = SK.window_x(lay)
    window(Wn, wx0, wx1)
    if lay == "motel_a":
        bed("Bed", 0.8, 2.8, -4.0, -2.4, head="+x")
        nightstand(2.3, 2.8, -4.6, -4.1, lamp_at=(2.55, -4.35))
        dresser(-1.2, -0.7, -3.6, -1.6, 0.8, face="+x", tv=True)
        picture(We, -3.2, 1.6, 0.8, 0.52, "bed", 0)
        bathroom_a()
        part("Heater", "Grille", lambda bm: Wn.box(bm, 1.3, 2.3, 0.15, 0.55, 0.0, 0.03), tile=0.4)
    else:
        bed("Bed_1", -2.4, -1.4, -5.0, -3.0, head="-z")
        bed("Bed_2", 1.4, 2.4, -5.0, -3.0, head="-z")
        nightstand(-0.25, 0.25, -5.0, -4.5, lamp_at=(0.0, -4.75))
        dresser(1.5, 2.5, -1.6, -1.1, 0.9, face="-z", tv=True)
        picture(We, -4.0, 1.55, 0.7, 0.5, "bed", 2)
        closet_b()
        bath_door_flush(Ww, -2.55, 0.8)
        part("Heater", "Grille", lambda bm: Wn.box(bm, -0.55, 0.55, 0.15, 0.55, 0.0, 0.03), tile=0.4)
    # the corridor outside the open door (bake stand-ins: its sconces and the leaf, open into the room)
    for zw, sg in ((0.0, 1), (2 * GB.CORR_Z, -1)):
        w = Wall("z", zw, sg)
        for xx in (-2.0, 2.0):
            light(f"L_sb_sconce_{zw:.0f}_{xx:+.0f}", "POINT", w.pt(xx, SK.SCONCE_Y, 0.15), SCONCE_W, size=0.03, coll=BAKE_STANDIN)
            part(f"standin_shade_{zw:.0f}_{xx:+.0f}", "Lamp_Emit", lambda bm: tube(bm, w.pt(xx, SK.SCONCE_Y - 0.085, 0.15), w.pt(xx, SK.SCONCE_Y + 0.085, 0.15), 0.1, 0.078),
                 BAKE_STANDIN, recalc=False)
    bm = bmesh.new()
    cube(bm, (0, 0, 0), (0.93, 2.15, 0.045))
    me = bpy.data.meshes.new("standin_leaf")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS["Door_Bath"])
    leaf = bpy.data.objects.new("standin_leaf", me)
    BAKE_STANDIN.objects.link(leaf)
    leaf.matrix_world = Matrix.Translation(B((-GB.DOOR_W / 2, 0.0, z1))) @ Matrix.Rotation(math.radians(95), 4, "Z")


def window(w, a0, a1):
    """A recessed aluminium window 12 cm deep, its glass dark: it looks onto nothing. Curtains on a rail over it, drawn nearly shut (decor_)."""
    y0, y1 = SK.WIN_Y0, SK.WIN_Y1
    recess_box(w, a0, a1, y0, y1, 0.12, "Window_Frame", "win")
    part("Win_Void", "Window_Void", lambda bm: w.box(bm, a0 + 0.01, a1 - 0.01, y0 + 0.01, y1 - 0.01, -0.11, -0.1))
    am = (a0 + a1) / 2
    part("Win_Mullion", "Window_Frame", lambda bm: (w.box(bm, am - 0.02, am + 0.02, y0, y1, -0.1, -0.06), w.box(bm, a0, a1, y0 + 0.42, y0 + 0.46, -0.1, -0.06)))
    part("Win_Sill", "Wood_Laminate", lambda bm: w.box(bm, a0 - 0.06, a1 + 0.06, y0 - 0.03, y0, 0.0, 0.045))
    part("decor_curtain_rail", "Window_Frame", lambda bm: cyl(bm, w.pt(a0 - 0.3, 2.3, 0.09), w.pt(a1 + 0.3, 2.3, 0.09), 0.014, seg=10))
    gap = 0.16
    for k, (c0, c1) in enumerate(((a0 - 0.28, am - gap / 2), (am + gap / 2, a1 + 0.28))):
        def cur(bm, c0=c0, c1=c1, k=k):
            n = 26
            rng = np.random.default_rng(31 + k)
            ph = rng.random() * 6
            pts_top, pts_bot = [], []
            for i in range(n + 1):
                t = i / n
                aa = c0 + (c1 - c0) * t
                dd = 0.075 + 0.045 * math.sin(t * math.pi * 9 + ph)
                pts_top.append(w.pt(aa, 2.27, dd))
                pts_bot.append(w.pt(aa, 0.62, dd + 0.01 * math.sin(t * 20)))
            vt = [bm.verts.new(B(p)) for p in pts_top]
            vb = [bm.verts.new(B(p)) for p in pts_bot]
            for i in range(n):
                bm.faces.new((vb[i], vb[i + 1], vt[i + 1], vt[i]))
        part(f"decor_curtain_{k}", "Curtain", cur, tile=0.5, recalc=False)
    part("decor_curtain_sheer", "Linen_White", lambda bm: w.box(bm, a0 - 0.05, a1 + 0.05, 0.75, 2.24, 0.035, 0.037))


def bed(name, xa, xb, za, zb, head):
    """A motel bed on its collider's footprint: a laminate plinth, a mattress, a quilted floral spread hanging over three sides, pillows, a headboard."""
    h_plinth, h_mat = 0.24, 0.5
    e = 0.02
    part(f"{name}_Plinth", "Wood_Laminate", lambda bm: cube(bm, (xa + 0.03, 0.0, za + 0.03), (xb - 0.03, 0.17, zb - 0.03)))   # the spread is the mattress's cover
    if head == "+x":
        sx = (xa - 0.015, xb - 0.32)
        sz = (za - 0.015, zb + 0.015)
    else:
        sx = (xa - 0.015, xb + 0.015)
        sz = (za + 0.32, zb + 0.015)
    part(f"{name}_Spread", "Bedspread", lambda bm: cube(bm, (sx[0], 0.16, sz[0]), (sx[1], h_mat + 0.035, sz[1])), tile=1.0)
    if head == "+x":                                     # the sheet's end at the head, where the spread is turned down
        part(f"{name}_Sheet", "Linen_White", lambda bm: cube(bm, (sx[1], 0.17, za + e), (xb - e, h_mat, zb - e)))
    else:
        part(f"{name}_Sheet", "Linen_White", lambda bm: cube(bm, (xa + e, 0.17, za + e), (xb - e, h_mat, sz[0])))
    if head == "+x":
        for k, (pz0, pz1) in enumerate(((za + 0.1, (za + zb) / 2 - 0.04), ((za + zb) / 2 + 0.04, zb - 0.1))):
            part(f"{name}_Pillow_{k}", "Linen_White", lambda bm: cube(bm, (xb - 0.42, h_mat, pz0), (xb - 0.06, h_mat + 0.13, pz1)), smooth=False)
        part(f"{name}_Head", "Wood_Laminate", lambda bm: cube(bm, (xb - 0.035, 0.3, za - 0.04), (xb, 1.15, zb + 0.04)))
        part(f"{name}_Turn", "Linen_White", lambda bm: cube(bm, (xb - 0.32, h_mat, za), (xb - 0.3, h_mat + 0.04, zb)))
    else:
        part(f"{name}_Pillow", "Linen_White", lambda bm: cube(bm, (xa + 0.1, h_mat, za + 0.05), (xb - 0.1, h_mat + 0.13, za + 0.4)))
        part(f"{name}_Head", "Wood_Laminate", lambda bm: cube(bm, (xa - 0.02, 0.28, za), (xb + 0.02, 1.05, za + 0.035)))
        part(f"{name}_Turn", "Linen_White", lambda bm: cube(bm, (xa, h_mat, za + 0.3), (xb, h_mat + 0.04, za + 0.32)))


def nightstand(xa, xb, za, zb, lamp_at):
    h = 0.6
    part("Nightstand", "Wood_Laminate", lambda bm: cube(bm, (xa + 0.01, 0.06, za + 0.01), (xb - 0.01, h, zb - 0.01)))
    part("Nightstand_Plinth", "Plastic_Black", lambda bm: cube(bm, (xa + 0.04, 0.0, za + 0.04), (xb - 0.04, 0.06, zb - 0.04)))
    lx, lz = lamp_at
    part("Lamp_Foot", "Lamp_Base", lambda bm: (cyl(bm, (lx, h, lz), (lx, h + 0.03, lz), 0.075, seg=20), cyl(bm, (lx, h + 0.03, lz), (lx, h + 0.3, lz), 0.05, 0.03, seg=18)))
    part("Lamp_Stem", "Brass", lambda bm: cyl(bm, (lx, h + 0.3, lz), (lx, h + 0.42, lz), 0.008, seg=8))
    part("Lamp_Shade", "Lamp_Emit", lambda bm: tube(bm, (lx, h + 0.28, lz), (lx, h + 0.52, lz), 0.17, 0.13, seg=32), recalc=False)
    light("L_lamp", "POINT", (lx, h + 0.4, lz), LAMP_W, size=0.04)
    part("Clock", "Plastic_Black", lambda bm: cube(bm, (xa + 0.04, h, za + 0.04), (xa + 0.18, h + 0.07, za + 0.12)))


def dresser(xa, xb, za, zb, h, face, tv):
    """A laminate dresser with three drawers (fronts and pulls on the face toward the room), a CRT television on top facing the bed."""
    part("Dresser", "Wood_Laminate", lambda bm: cube(bm, (xa + 0.01, 0.05, za + 0.01), (xb - 0.01, h, zb - 0.01)))
    part("Dresser_Plinth", "Plastic_Black", lambda bm: cube(bm, (xa + 0.03, 0.0, za + 0.03), (xb - 0.03, 0.05, zb - 0.03)))
    if face == "+x":
        w = Wall("x", xb - 0.01, 1)
        a0, a1 = za + 0.04, zb - 0.04
    else:
        w = Wall("z", za + 0.01, -1)
        a0, a1 = xa + 0.04, xb - 0.04
    for k in range(3):
        y0 = 0.09 + k * (h - 0.12) / 3
        y1 = y0 + (h - 0.12) / 3 - 0.02
        part(f"Drawer_{k}", "Wood_Laminate", lambda bm: w.box(bm, a0, a1, y0, y1, 0.0, 0.012))
        am = (a0 + a1) / 2
        part(f"Drawer_{k}_Pull", "Brass", lambda bm: w.box(bm, am - 0.08, am + 0.08, (y0 + y1) / 2 - 0.008, (y0 + y1) / 2 + 0.008, 0.012, 0.03))
    if tv:
        if face == "+x":
            tx0, tx1, tz0, tz1 = xa + 0.04, xb - 0.06, (za + zb) / 2 - 0.3, (za + zb) / 2 + 0.3
        else:
            tx0, tx1, tz0, tz1 = (xa + xb) / 2 - 0.28, (xa + xb) / 2 + 0.28, za + 0.05, zb - 0.06
        part("TV", "TV_Plastic", lambda bm: (cube(bm, (tx0, h + 0.04, tz0), (tx1, h + 0.46, tz1)), cube(bm, (tx0 + 0.05, h, tz0 + 0.05), (tx1 - 0.05, h + 0.04, tz1 - 0.05))))
        if face == "+x":
            part("TV_Screen", "TV_Screen", lambda bm: cube(bm, (tx1, h + 0.1, tz0 + 0.05), (tx1 + 0.006, h + 0.42, tz1 - 0.1)))
            part("TV_Knob", "Plastic_White", lambda bm: cube(bm, (tx1, h + 0.12, tz1 - 0.08), (tx1 + 0.012, h + 0.15, tz1 - 0.05)))
        else:
            part("TV_Screen", "TV_Screen", lambda bm: cube(bm, (tx0 + 0.05, h + 0.1, tz0 - 0.006), (tx1 - 0.1, h + 0.42, tz0)))
            part("TV_Knob", "Plastic_White", lambda bm: cube(bm, (tx1 - 0.08, h + 0.12, tz0 - 0.012), (tx1 - 0.05, h + 0.15, tz0)))


def bathroom_a():
    """motel_a's bathroom behind its partition: tiled, a light, a wall-hung basin under a mirror, a towel bar, the door standing ajar into it."""
    Ww = Wall("x", -1.2, 1)
    part("Basin", "Porcelain", lambda bm: cube(bm, (-1.2, 0.76, -5.35), (-0.78, 0.88, -4.85)))
    part("Basin_Trap", "Steel", lambda bm: cube(bm, (-1.2, 0.36, -5.13), (-1.16, 0.76, -5.07)))
    part("Basin_Tap", "Steel", lambda bm: cube(bm, (-1.2, 0.88, -5.12), (-1.1, 0.95, -5.08)))
    part("Mirror_bath", "Mirror", lambda bm: Ww.box(bm, -5.4, -4.8, 1.15, 1.85, 0.0, 0.008))
    part("Mirror_bath_frame", "Steel", lambda bm: (Ww.box(bm, -5.42, -5.4, 1.13, 1.87, 0.0, 0.012), Ww.box(bm, -4.8, -4.78, 1.13, 1.87, 0.0, 0.012)))
    Wb = Wall("x", 0.6, -1)
    part("TowelBar", "Steel", lambda bm: (Wb.box(bm, -5.6, -4.9, 1.1, 1.12, 0.03, 0.045), Wb.box(bm, -5.6, -5.58, 1.08, 1.14, 0.0, 0.045),
                                          Wb.box(bm, -4.92, -4.9, 1.08, 1.14, 0.0, 0.045)))
    part("BathLight", "Lamp_Emit", lambda bm: cyl(bm, (-0.3, 2.74, -5.25), (-0.3, 2.8, -5.25), 0.12, seg=20))
    light("L_bath", "POINT", (-0.3, 2.62, -5.25), BATH_W, size=0.08)
    part("BathLintel", "Wall_Room", lambda bm: cube(bm, (-0.65, 2.1, -4.3), (0.05, 2.8, -4.2)))
    door_casing(Wall("z", -4.2, 1), -0.3, 0.35, 2.1, "bath", "Wood_Laminate", 0.06, 0.015)

    def leaf(bm):
        cube(bm, (0.0, 0.0, -0.035), (0.7, 2.08, 0.0))
    ob = part("decor_bath_door", "Door_Bath", leaf)
    me = ob.data
    M = Matrix.Translation(B((0.05, 0.0, -4.265))) @ Matrix.Rotation(math.radians(112), 4, "Z")
    me.transform(M)
    me.update()
    rebox_uv(ob)
    part("decor_bath_knob", "Brass", lambda bm: cube(bm, (0.05 - 0.62 * math.cos(math.radians(68)) - 0.02, 0.93, -4.265 - 0.62 * math.sin(math.radians(68)) - 0.05),
                                                     (0.05 - 0.62 * math.cos(math.radians(68)) + 0.02, 0.97, -4.265 - 0.62 * math.sin(math.radians(68)) + 0.05)))


def rebox_uv(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    box_uv(bm, TILES.get(ob.data.materials[0].name, 1.0))
    bm.to_mesh(ob.data)
    bm.free()


def closet_b():
    """motel_b's closet by the door: a shelf and a rail above head height, four wire hangers, nothing on them."""
    part("Closet_Shelf", "Wood_Laminate", lambda bm: cube(bm, (-2.5, 1.96, -1.4), (-1.3, 1.98, -0.85)))
    part("Closet_Rod", "Steel", lambda bm: cyl(bm, (-2.5, 1.88, -0.95), (-1.3, 1.88, -0.95), 0.012, seg=10))
    for k in range(4):
        x = -2.3 + k * 0.17

        def hanger(bm, x=x):
            cyl(bm, (x, 1.83, -1.17), (x, 1.83, -0.73), 0.003, seg=6)
            cyl(bm, (x, 1.83, -1.17), (x, 1.875, -0.95), 0.003, seg=6)
            cyl(bm, (x, 1.83, -0.73), (x, 1.875, -0.95), 0.003, seg=6)
            cyl(bm, (x, 1.875, -0.95), (x, 1.905, -0.95), 0.003, seg=6)
        part(f"Closet_Hanger_{k}", "Steel", hanger)


def bath_door_flush(w, a, wd):
    """motel_b's bathroom door, shut: a leaf 3 cm proud of the west wall in a laminate casing, a lever 4.6 cm proud at most."""
    part("Bath_Door", "Door_Bath", lambda bm: w.box(bm, a - wd / 2, a + wd / 2, 0.0, 2.04, 0.0, 0.03))
    door_casing(w, a, wd / 2 + 0.005, 2.045, "bath", "Wood_Laminate", 0.06, 0.015)
    part("Bath_Door_Lever", "Brass", lambda bm: (w.box(bm, a + wd / 2 - 0.1, a + wd / 2 - 0.06, 0.9, 1.0, 0.03, 0.036),
                                                 w.box(bm, a + wd / 2 - 0.22, a + wd / 2 - 0.06, 0.94, 0.96, 0.036, 0.046)))


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
    if KIND == "corridor":
        build_leaves(M)
        build_corridor(M)
        place_kit(M)
        corridor_standins()
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
    stand = [c for c in (bx(o) for o in bpy.data.objects if o.name.startswith("COL_") and o.type == "MESH") if cl._standing(c)]
    marks = [(o.matrix_world.translation.x, -o.matrix_world.translation.y) for o in bpy.data.objects if o.name.startswith("Marker_")]

    def fails(p):
        if not cl._stands(p):
            return False
        if any(cl._in_plan(p, x, z, cl.CLEAR_R) for x, z in marks):
            return True
        for x in cl._samples(p["min"][0], p["max"][0], cl.STEP / 2):
            for z in cl._samples(p["min"][2], p["max"][2], cl.STEP / 2):
                if not any(cl._in_plan(c, x, z, cl.TOL) for c in stand):
                    return True
        return False
    done = []
    for ob in list(PROPS.objects):
        if ob.type != "MESH" or ob.name.startswith("decor_") or not fails(bx(ob)):
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
SHELL_MATS = {"Carpet_Runner", "Carpet_Field", "Ceiling_Popcorn", "Closet_Paint", "Door_Jamb", "Jamb_Steel", "Lift_Shaft", "Lift_Ceiling", "Lift_Steel",
              "Stair_Concrete", "Stair_Paint", "Stair_Ceiling", "Threshold", "Wall_Lower", "Wall_Upper",
              "Carpet_Room", "Ceiling_Room", "Tile_Floor", "Tile_Wall", "Wall_Room"}
NO_LIGHTMAP = {"Lamp_Emit", "Emergency_Emit", "Glass_Clear"}
NO_CULL = ("Recess_", "Ice_", "Ext_", "Win_")


def arch_cols():
    return [c for c in SK.colliders(SK.model(SCENE)) if not c["name"].startswith(SK.FURNITURE + SK.KIT)]


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
    """One atlas for `objs`: smart-project islands at equal texel density, packed with MARGIN_PX on the fixed `page` (or, with None, the smallest
    page giving >= `want` px/m). Returns (page, density)."""
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
            # a rotated rectangle lies on its side: its e2 side (ph pixels) runs along u, its e1 side (pw) along t, as layout() reserved it
            # (the old code wrote b * pw, a * ph here, so a tall face ran past its row into the next one; found by the floor 2 job)
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
    if KIND == "corridor":
        for kind, name in BAKE_LEAF[SCENE].items():
            reps.append(bpy.data.objects[name])
        reps += sorted((o for o in bpy.data.collections["Doors"].objects if o.name.startswith("DoorNum_")), key=lambda o: o.name)
    return reps


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
    p = Path(arg("--caps")) / f"{SCENE}.json" if arg("--caps") else stills_dir(SCENE) / "caps.json"     # --caps <dir>: the same files, elsewhere
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
    for o in bpy.data.collections["Arch"].objects:         # the plan render hides some of them for its picture; the check needs every one
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
    if SCENE == "floor_1_lower":
        return {"1_arrival": ((-18.8, E, 0.0), (-8.8, E - 0.3, 0.0), 75), "2_wide": ((19.3, 2.35, 0.75), (-6.0, 0.6, -0.4), 70),
                "3_detail": ((-1.2, 1.55, 0.6), (0.25, 1.45, -1.1), 62)}
    if SCENE == "floor_1_upper":
        return {"1_arrival": ((18.8, E, 0.0), (8.8, E - 0.3, 0.0), 75), "2_wide": ((-19.3, 2.35, -0.75), (6.0, 0.6, 0.4), 70),
                "3_detail": ((12.6, 1.5, 0.5), (11.9, 1.0, -1.9), 70)}
    if SCENE == "motel_a":
        return {"1_arrival": ((0.0, E, -0.8), (0.6, E - 0.35, -5.8), 75), "2_wide": ((2.55, 2.3, -0.5), (0.2, 0.5, -4.6), 75),
                "3_detail": ((1.2, 1.35, -4.55), (2.6, 0.75, -4.3), 60)}
    return {"1_arrival": ((0.0, E, -0.8), (0.0, E - 0.4, -5.8), 75), "2_wide": ((2.25, 2.3, -0.5), (-1.0, 0.5, -4.8), 75),
            "3_detail": ((1.05, 1.3, -2.7), (-0.1, 0.85, -5.0), 62)}


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
        span = x1 - x0
        cam = look_cam("plan", ((x0 + x1) / 2, 30.0, (z0 + z1) / 2), None, ortho=span)
        cam.rotation_euler = (0, 0, 0)
        sc.camera = cam
        hidden = []
        for o in list(bpy.data.collections["Skin"].objects) + list(bpy.data.collections["Props"].objects) + list(bpy.data.collections["Bake_Standins"].objects):
            if o.name.startswith(("Ceiling", "Lift_Ceiling", "Stair_Ceiling", "decor_stain_ceiling", "Smoke", "Grille", "Dome", "BathLight", "AlcoveLight",
                                  "Bulkhead", "standin_room", "SB_")) or (o.type == "MESH" and min((o.matrix_world @ v.co).z for v in o.data.vertices) > 2.3
                                                                         and not o.name.startswith("Step")):
                if not o.hide_render:
                    o.hide_render = True
                    hidden.append(o)
        arch = bpy.data.collections["Arch"]
        arch.hide_render = False
        for o in arch.objects:
            o.hide_render = o.name.startswith(("Corridor_Ceiling", "Corridor_Floor", "Alcove_Floor", "Alcove_Ceiling", "Room_Ceiling", "Room_Floor",
                                               "Stairwell_Ceiling", "Stairwell_Floor", "Car_Ceiling", "Car_Floor", "Landing_Floor_", "Step_", "Landing_Top",
                                               "StairLanding_Ceiling", "StairLanding_Floor", "Bed", "Nightstand", "Dresser"))
        world = sc.world
        bg = world.node_tree.nodes["Background"]
        old = bg.inputs["Strength"].default_value
        bg.inputs["Color"].default_value = (1, 1, 1, 1)
        bg.inputs["Strength"].default_value = 0.6
        W = 2400 if KIND == "corridor" else 1400
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
    scenes = arg("--scenes", "floor_1_lower").split(",")
    for sc in scenes:
        SCENE = sc
        KIND = "room" if sc in SK.ROOMS else "corridor"
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
        if STAGE in ("check", "all", "reexport"):
            stage_check()
        if STAGE in ("render", "all"):
            stage_render()
            save_blend()
        print(f"==== {sc} done")


main()
