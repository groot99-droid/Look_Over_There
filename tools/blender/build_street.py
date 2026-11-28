"""Builds Hallam Row (`street`) in Blender, bakes its ambient occlusion, renders its day and night backdrops and exports world/street.glb
(docs/BLENDER.md, "7. street").

Re-runnable, from the repo root (node tools/blender/dump_layout.mjs street and node tools/blender/street_extras.mjs first):

    python tools/blender/build_street.py --stage textures --src <folder>     (plain Python with numpy and Pillow: the CC0 maps and the generated
                                                                               images -> blender/textures/street/)
    blender -b --python tools/blender/build_street.py -- --stage art          (build the art, save blender/scenes/street.blend)
    blender -b blender/scenes/street.blend --python tools/blender/build_street.py -- --stage bake [--samples 256]
    blender -b blender/scenes/street.blend --python tools/blender/build_street.py -- --stage export
    blender -b blender/scenes/street.blend --python tools/blender/build_street.py -- --stage axes
    blender -b blender/scenes/street.blend --python tools/blender/build_street.py -- --stage backdrop   (the two 4096 x 2048 panoramas)
    blender -b blender/scenes/street.blend --python tools/blender/build_street.py -- --stage render [--render-samples 128] [--only 1_arrival]
    blender -b --python tools/blender/build_street.py -- --stage all          (art, bake, export, axes, backdrop, render)
    python tools/blender/pack_scene.py street --work <work>                   (WebP AO maps and WebP textures -> world/)
    python tools/blender/build_street.py --stage pack-backdrops --work <work> (WebP backdrops -> world/backdrops/)

The street has a day clock, so only the ambient occlusion is baked (docs/BLENDER.md R1, AO-only scenes): every baked material carries `aomap` and
`aomap_intensity` (no `lightmap`); the page keeps those materials lit, so its sun and sky still light them, and uses the bake on the second UV set as
their aoMap. The lamp heads use `Lamp_Emit` and the lit windows `Window_Lit`, both switched by the page's clock.

No coordinate of the layout is typed in here: the road, the sidewalks, the buildings (their sides, z ranges, depths, heights and colours), the doors,
the lamp posts, the bus shelter's bench and the edge walls come from blender/layout/street.json, and the window slots, the door's size, the PHARMACY
sign, the ghost window and the watchers' windows from blender/layout/street_extra.json. A game point (x, y, z) is Blender (x, -z, y).

What the page draws itself is left out (docs/BLENDER.md, contract 4): each door's sign, status lamp and roller shutter, the PHARMACY sign, the
pedestrians, the ghost window, the watchers, the trash bins and the bus. The wall above each door is plain. The signs, the lamps, the pedestrians,
the watchers and the ghost window are here as stand-ins for the review stills only (the `Standins` collection), never baked or exported.
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
SCENE = "street"
LAYOUT = ROOT / f"blender/layout/{SCENE}.json"
EXTRA = ROOT / f"blender/layout/{SCENE}_extra.json"
TEX = ROOT / f"blender/textures/{SCENE}"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
STILLS = ROOT / f"docs/renders/{SCENE}"
AO_URL = "world/lightmaps/" + SCENE + "_{}.webp"      # the path the page reads from the material's `aomap` custom property
MARGIN_PX = 8

if "--" in sys.argv:
    args = sys.argv[sys.argv.index("--") + 1:]
else:
    args = sys.argv[1:] if bpy is None else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 256, int)
DEVICE = arg("--device", "auto")

L = json.loads(LAYOUT.read_text())
X = json.loads(EXTRA.read_text())
K = L["constants"]
ROAD = K["ROAD"]
WORLD = K["WORLD"]
LAMP_ZS = K["LAMP_ZS"]
BUS = K["BUS_STREET"]
BUILDINGS = L["buildings"]
DOORS = {d["id"]: d for d in L["doors"]}
COLL = {}
for c in L["world"]["colliders"]:
    COLL.setdefault(c["s"], []).append(c)
FRONT = X["front"]                       # the buildings' street faces stand at x = +-FRONT
DOOR_W, DOOR_H = X["door"]["w"], X["door"]["h"]
SIGN = X["sign"]
GHOST = X["ghost_window"]
WATCH = {(w["building"], w["f"], w["k"]): w for w in X["watchers"]}

# ---------------------------------------------------------------- the art the layout does not name, placed relative to it
ROAD_Y, WALK_Y = -0.06, 0.06              # the road sits 6 cm under the collision floor (y 0), the sidewalks 6 cm over it: a 12 cm kerb
KERB_W = 0.15
PAR = 0.7                                 # parapet over each roof
PANE_W, PANE_H = 1.6, 1.3                 # the page's window pane (index.html cityProps)
WIN_DEPTH = 0.05                          # the upper windows' reveal; the glass sits 4 cm in
SHOP_Y = (0.45, 2.4)                      # shop windows: stall riser below, fascia above
SHOP_DEPTH = 0.15
DOOR_DEPTH = 0.25
DOOR_ZONE = 1.6                           # plain wall each side of a door's centre line out to here: the page's shutter (+-1.15) and lamp (+1.2) sit on it
SIGN_ZONE = 1.55                          # no awning or fascia within this of a door: the page's sign is 2.8 m wide at y 2.79 .. 3.31
FASCIA_Y = (2.45, 2.85)
PILASTER = 0.45
EDGE_BAY, EDGE_FLOOR = 3.4, 3.6           # the edge buildings' bays and floors (their textures are two bays by one floor)

# how each building looks: facade texture, its tile (m), tint mode, ground floor kind, glass variant, awning
LOOK = {
    "tower":   {"tex": "concrete.jpg", "tile": 3.0, "tint": "paint", "ground": "lobby", "glass": 1},
    "w41":     {"tex": "brick_red.jpg", "tile": 2.6, "tint": "brick", "ground": "shop", "glass": 0, "awning": "Awning_Red"},
    "wfill1":  {"tex": "plaster.jpg", "tile": 3.0, "tint": "paint", "ground": "pharmacy", "glass": 2},
    "w214":    {"tex": "render_patchy.jpg", "tile": 2.5, "tint": "paint", "ground": "shop", "glass": 0},
    "wfill2":  {"tex": "brick_red.jpg", "tile": 2.6, "tint": "brick", "ground": "house", "glass": 3},
    "w666":    {"tex": "brick_dark.jpg", "tile": 1.1, "tint": "brick", "ground": "shop", "glass": 3},
    "grocery": {"tex": "plaster.jpg", "tile": 3.0, "tint": "paint", "ground": "shop", "glass": 0, "awning": "Awning_Green"},
    "e108":    {"tex": "render_patchy.jpg", "tile": 2.5, "tint": "paint", "ground": "shop", "glass": 3},
    "mall":    {"tex": "concrete.jpg", "tile": 3.0, "tint": "paint", "ground": "lobby", "glass": 1},
    "e330":    {"tex": "brick_yellow.jpg", "tile": 1.5, "tint": "brick", "ground": "shop", "glass": 0, "awning": "Awning_Red"},
    "efill":   {"tex": "render_patchy.jpg", "tile": 2.5, "tint": "paint", "ground": "boarded", "glass": 3},
}
PAINT_K = 1.9                             # a painted facade's colour: the page's building colour (linear) times this, times a near-white texture


def lin_hex(h):
    c = [((h >> s) & 255) / 255 for s in (16, 8, 0)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


def facade_tint(b):
    c = np.array(lin_hex(b["color"]))
    if LOOK[b["id"]]["tint"] == "paint":
        return tuple(float(v) for v in np.clip(c * PAINT_K, 0, 1))
    t = (c / c.mean()) ** 0.35                                          # a brick keeps its own colour; the page's colour only leans it
    return tuple(float(v) for v in t / t.max())                         # (a glTF colour factor is at most 1)


def rng_for(*key):
    h = 2166136261
    for ch in "|".join(str(k) for k in key):
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return np.random.default_rng(h)


# ================================================================ the textures stage (plain Python: numpy and Pillow)
def tx_load(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB"), np.float32) / 255.0


def tx_save(arr, fn, q=88):
    from PIL import Image
    a = (np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8)
    im = Image.fromarray(a)
    p = TEX / fn
    if fn.endswith(".png"):
        im.save(p, optimize=True)
    else:
        im.save(p, "JPEG", quality=q, optimize=True)
    print("TEXTURE", fn, im.size, p.stat().st_size)


def to_lin(a):
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def to_srgb(a):
    a = np.clip(a, 0, 1)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(a, 1 / 2.4) - 0.055)


def blur(a, r, passes=3):
    n = 2 * r + 1
    for ax in (0, 1):
        for _ in range(passes):
            pad = [(0, 0)] * a.ndim
            pad[ax] = (r + 1, r)
            c = np.cumsum(np.pad(a, pad, mode="wrap"), axis=ax)
            Ln = c.shape[ax]
            a = (np.take(c, range(n, Ln), axis=ax) - np.take(c, range(0, Ln - n), axis=ax)) / n
    return a


def resize(a, w, h):
    from PIL import Image
    im = Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)).resize((w, h), Image.LANCZOS)
    return np.asarray(im, np.float32) / 255.0


def neutral(a, mean_lin, sat=0.0):
    """A texture made neutral (keeping `sat` of its colour) with its linear mean at `mean_lin`, so a colour factor tints it."""
    L_ = to_lin(a)
    g = L_.mean(axis=2, keepdims=True)
    L_ = g + (L_ - g) * sat
    return to_srgb(L_ * (mean_lin / L_.mean()))


GLYPHS = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"], "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"], "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"], "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"], "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"], "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"], "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"], "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"], "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "0": ["01110", "10011", "10101", "10101", "10101", "11001", "01110"], "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"], "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"], "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"], " ": ["00000"] * 7,
}


def draw_text(img, text, box, fg, fill=0.7):
    r0, r1, c0, c1 = box
    cols = len(text) * 6 - 1
    s = max(1, int(min((c1 - c0) * fill / cols, (r1 - r0) * fill / 7)))
    y = r0 + ((r1 - r0) - 7 * s) // 2
    x = c0 + ((c1 - c0) - cols * s) // 2
    for ch in text:
        for r, row in enumerate(GLYPHS[ch]):
            for c, v in enumerate(row):
                if v == "1":
                    img[y + r * s:y + (r + 1) * s, x + c * s:x + (c + 1) * s] = fg
        x += 6 * s


def window_art(img, r0, r1, c0, c1, rng, glass=(0.06, 0.07, 0.08), frame=(0.62, 0.60, 0.56), curtain=True):
    """One painted window: a light frame, a cross bar, dark glass with a faint sky reflection at the top, maybe a curtain."""
    img[r0:r1, c0:c1] = frame
    f = max(2, (c1 - c0) // 14)
    g0, g1, k0, k1 = r0 + f, r1 - f, c0 + f, c1 - f
    h = g1 - g0
    t = np.linspace(1, 0, h)[:, None, None]
    img[g0:g1, k0:k1] = np.array(glass) * rng.uniform(0.7, 1.3) + 0.10 * t ** 3
    if curtain and rng.random() < 0.45:
        col = np.array(rng.choice([(0.55, 0.48, 0.38), (0.42, 0.40, 0.45), (0.60, 0.58, 0.52), (0.35, 0.22, 0.18)]))
        w = int((k1 - k0) * rng.uniform(0.2, 0.45))
        img[g0:g1, k0:k0 + w] = col * rng.uniform(0.5, 0.8)
        if rng.random() < 0.5:
            img[g0:g1, k1 - w:k1] = col * rng.uniform(0.5, 0.8)
    img[(g0 + g1) // 2 - f // 2:(g0 + g1) // 2 + f // 2 + 1, k0:k1] = frame
    img[r1:r1 + f * 2, c0 - f:c1 + f] = np.array(frame) * 0.9           # the sill


def edge_tile(base, rng, kind):
    """An edge building's upper floor: two 3.4 m bays and one 3.6 m floor (1024 x 544 px), the wall `base` with a window in each bay."""
    W, H = 1024, 544
    img = resize(base, W, H)
    ppm = W / (2 * EDGE_BAY)
    for k in range(2):
        cx = (EDGE_BAY / 2 + k * EDGE_BAY) * ppm
        c0, c1 = int(cx - 0.7 * ppm), int(cx + 0.7 * ppm)
        r0, r1 = int(H - 2.45 * ppm), int(H - 0.9 * ppm)
        img[r0 - int(0.12 * ppm):r0, c0 - 6:c1 + 6] = np.array((0.55, 0.52, 0.48)) if kind != "render" else img[r0 - int(0.12 * ppm):r0, c0 - 6:c1 + 6] * 0.85
        window_art(img, r0, r1, c0, c1, rng)
    return img


def edge_ground_tile(base, rng):
    """The edge buildings' ground floor (two bays, 0 .. 3.6 m): a roller shutter in one bay, a door and a small window in the other, a sign band."""
    W, H = 1024, 544
    img = resize(base, W, H) * 0.85
    ppm = W / (2 * EDGE_BAY)
    # bay 0: a roller shutter 2.8 x 2.6 m
    c0, c1 = int(0.3 * ppm), int(3.1 * ppm)
    r0, r1 = int(H - 2.7 * ppm), H - 2
    yy = np.arange(r1 - r0)[:, None, None]
    img[r0:r1, c0:c1] = np.array((0.36, 0.37, 0.38)) * (0.9 + 0.1 * np.sin(yy * 2 * np.pi / (0.08 * ppm)))
    img[r0:r0 + 10, c0 - 8:c1 + 8] = (0.18, 0.18, 0.19)
    img[r1 - 40:r1, c0:c1] *= np.linspace(1, 0.6, 40)[:, None, None]
    # bay 1: a door and a window
    d0, d1 = int((EDGE_BAY + 0.4) * ppm), int((EDGE_BAY + 1.4) * ppm)
    img[int(H - 2.2 * ppm):H - 2, d0:d1] = (0.12, 0.16, 0.14)
    img[int(H - 2.2 * ppm):H - 2, d0:d0 + 6] = img[int(H - 2.2 * ppm):H - 2, d1 - 6:d1] = (0.5, 0.48, 0.45)
    window_art(img, int(H - 2.3 * ppm), int(H - 1.0 * ppm), int((EDGE_BAY + 1.8) * ppm), int((EDGE_BAY + 3.0) * ppm), rng, curtain=False)
    # a sign band
    img[int(H - 3.3 * ppm):int(H - 2.85 * ppm), int(0.2 * ppm):int((2 * EDGE_BAY - 0.2) * ppm)] = np.array(rng.choice([(0.12, 0.2, 0.16), (0.25, 0.1, 0.1), (0.1, 0.12, 0.22)]))
    n = blur(rng.random((H, W)).astype(np.float32), 3, 2)
    return img * (0.92 + 0.16 * n)[..., None]


def shop_atlas(rng):
    """Shop glass, 2 x 2 cells (each 512 px for a panel about 3 x 2 m): 0 a dim shop interior with shelves, 1 a lobby (a lit floor, a counter, a plant),
    2 whitewashed glass (a closed shop), 3 closed blinds. Each has a faint sky reflection at the top."""
    S = 512
    img = np.zeros((2 * S, 2 * S, 3), np.float32)

    def cell(i):
        r, c = divmod(i, 2)
        return img[r * S:(r + 1) * S, c * S:(c + 1) * S]
    a = cell(0)
    a[:] = (0.07, 0.065, 0.06)
    a[int(S * 0.72):] = (0.12, 0.11, 0.10)
    for s in (0.25, 0.42, 0.59):
        y = int(S * s)
        a[y:y + 6] = (0.30, 0.28, 0.26)
        for c in range(20, S - 40, 26):
            if rng.random() < 0.55:
                h = int(rng.uniform(25, 55))
                a[y - h:y, c:c + 20] = np.array(rng.choice([(0.5, 0.45, 0.35), (0.2, 0.3, 0.5), (0.55, 0.2, 0.15), (0.6, 0.55, 0.2), (0.3, 0.45, 0.3)])) * rng.uniform(0.3, 0.6)
    a[int(S * 0.62):int(S * 0.75), int(S * 0.6):int(S * 0.95)] = (0.2, 0.17, 0.14)
    b = cell(1)
    b[:] = (0.16, 0.15, 0.14)
    b[int(S * 0.65):] = (0.30, 0.29, 0.27)
    b[int(S * 0.55):int(S * 0.72), int(S * 0.15):int(S * 0.55)] = (0.08, 0.07, 0.07)
    b[int(S * 0.08):int(S * 0.12), :] = (0.55, 0.54, 0.50)
    b[int(S * 0.45):int(S * 0.7), int(S * 0.75):int(S * 0.85)] = (0.08, 0.16, 0.08)
    c_ = cell(2)
    n = blur(rng.random((S, S)).astype(np.float32), 9, 3)
    sm = blur(rng.random((S, S)).astype(np.float32), 2, 1)
    c_[:] = np.array((0.78, 0.77, 0.72))[None, None, :] * (0.8 + 0.4 * n[..., None]) * (0.9 + 0.2 * sm[..., None])
    for k in range(14):
        y = int(rng.uniform(0, S))
        c_[y:y + 18] *= 0.9
    d = cell(3)
    yy = np.arange(S)[:, None, None]
    d[:] = np.array((0.42, 0.40, 0.36)) * (0.75 + 0.25 * (np.sin(yy * 2 * np.pi / 14) > -0.6))
    for i in range(4):
        cc = cell(i)
        t = np.linspace(1, 0, S)[:, None, None]
        cc += 0.08 * t ** 2
    return np.clip(img, 0, 1)


def lit_atlas(rng):
    """The lit windows at night (an emissive map), 2 x 2 cells of 256 px: warm curtains, a bare warm room, amber blinds, a cool television glow."""
    S = 256
    img = np.zeros((2 * S, 2 * S, 3), np.float32)
    yy, xx = np.mgrid[0:S, 0:S] / S
    glow = np.exp(-((xx - 0.5) ** 2 / 0.18 + (yy - 0.35) ** 2 / 0.25))[..., None]
    cells = []
    a = np.array((1.0, 0.72, 0.38)) * (0.45 + 0.55 * glow)
    cur = (np.abs(xx - 0.5) > 0.3)[..., None]
    a = np.where(cur, np.array((0.85, 0.45, 0.22)) * (0.4 + 0.3 * glow), a)
    cells.append(a)
    b = np.array((1.0, 0.86, 0.62)) * (0.35 + 0.65 * glow)
    b[int(S * 0.7):] *= 0.6
    cells.append(b)
    c = np.array((1.0, 0.62, 0.28)) * (0.5 + 0.5 * glow) * (0.55 + 0.45 * (np.sin(yy * S * 2 * np.pi / 10) > -0.4))[..., None]
    cells.append(c)
    d = np.array((0.45, 0.6, 1.0)) * (0.25 + 0.6 * glow)
    cells.append(d)
    for i, cc in enumerate(cells):
        r, col = divmod(i, 2)
        img[r * S:(r + 1) * S, col * S:(col + 1) * S] = cc
    return np.clip(img, 0, 1)


def drain_pixels():
    W, H = 256, 128
    img = np.zeros((H, W, 3), np.float32) + 0.10
    img[8:H - 8, 8:W - 8] = 0.05
    for c in range(16, W - 16, 16):
        img[14:H - 14, c:c + 8] = 0.015
    img[:6] = img[-6:] = img[:, :6] = img[:, -6:] = 0.16
    return img


def gate_pixels(rng):
    """Corrugated steel (a roller gate or a hoarding), 512 px a 3.4 m repeat: vertical ribs, blue-grey paint, rust runs."""
    S = 512
    xx = np.arange(S)[None, :, None]
    img = np.zeros((S, S, 3), np.float32) + np.array((0.30, 0.34, 0.38))
    img *= 0.8 + 0.25 * (0.5 + 0.5 * np.sin(xx * 2 * np.pi / 18))
    rust = blur(rng.random((S, S)).astype(np.float32), 6, 3)
    runs = blur((rng.random((1, S)) < 0.04).astype(np.float32) * np.ones((S, 1)), 2, 1) * np.linspace(0.2, 1, S)[:, None]
    m = np.clip((rust - 0.52) * 6 + runs * 3, 0, 1)[..., None]
    return np.clip(img * (1 - m) + np.array((0.32, 0.17, 0.08)) * m, 0, 1)


def bd_atlas(rng, night):
    """The distant city's facades for the backdrops: 2 x 2 cells (each 512 px for 4 bays by 4 floors, 12 x 12 m): concrete flats, brick, a glass office,
    pale render. By day the walls and dark windows; by night black walls and the lit windows (about a third, warm, some cool)."""
    S = 512
    img = np.zeros((2 * S, 2 * S, 3), np.float32)
    walls = [(0.42, 0.42, 0.42), (0.40, 0.22, 0.16), (0.30, 0.36, 0.42), (0.62, 0.58, 0.50)]
    for i in range(4):
        r, c = divmod(i, 2)
        cel = img[r * S:(r + 1) * S, c * S:(c + 1) * S]
        if not night:
            n = blur(rng.random((S, S)).astype(np.float32), 4, 2)
            cel[:] = np.array(walls[i]) * (0.85 + 0.3 * n[..., None])
        win_w, win_h = (0.62, 0.55) if i != 2 else (0.92, 0.7)
        for fy in range(4):
            for bx in range(4):
                c0, c1 = int((bx + (1 - win_w) / 2) * S / 4), int((bx + (1 + win_w) / 2) * S / 4)
                r0, r1 = int((fy + (1 - win_h) / 2) * S / 4), int((fy + (1 + win_h) / 2) * S / 4)
                if night:
                    if rng.random() < 0.33:
                        col = np.array((1.0, 0.75, 0.42)) if rng.random() < 0.8 else np.array((0.6, 0.75, 1.0))
                        cel[r0:r1, c0:c1] = col * rng.uniform(0.35, 1.0)
                else:
                    cel[r0:r1, c0:c1] = np.array((0.10, 0.12, 0.15)) * rng.uniform(0.6, 1.4) + (0.15 if i == 2 else 0.0)
    return np.clip(img, 0, 1)


def signs_pixels():
    """Stand-ins for the page's signs (index.html signTexture: #e8e0c0 on #1a1a1e), one row each: the doors' labels, then PHARMACY. Stills only."""
    rows = [d["label"] for d in L["doors"]] + [SIGN["text"]]
    img = np.zeros((96 * len(rows), 512, 3), np.float32)
    img[:] = to_srgb(np.array(lin_hex(0x1a1a1e)))
    for i, t in enumerate(rows):
        draw_text(img, t, (i * 96, (i + 1) * 96, 0, 512), tuple(to_srgb(np.array(lin_hex(0xe8e0c0)))), 0.8)
    return img


def stage_textures():
    """From the CC0 maps (--src: the five Poly Haven 1k diffuse JPEGs; the four others are already in the repo) make the build's textures, and draw the
    generated ones (numpy, fixed seeds). JPEG quality 88; the sign stand-ins as PNG."""
    src = Path(arg("--src", "."))
    TEX.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(1966)
    asph = tx_load(src / "asphalt_02_diff_1k.jpg")
    tx_save(to_srgb(to_lin(asph) * 1.05), "road_asphalt.jpg")
    pav = tx_load(src / "square_concrete_pavers_diff_1k.jpg")
    tx_save(neutral(pav, 0.20, 0.25), "sidewalk_slab.jpg")
    red = tx_load(src / "red_bricks_04_diff_1k.jpg")
    tx_save(to_srgb(to_lin(red) * 1.5), "brick_red.jpg")
    dark = tx_load(src / "dark_brick_wall_diff_1k.jpg")
    tx_save(to_srgb(to_lin(dark) * 1.15), "brick_dark.jpg")
    yel = tx_load(ROOT / "blender/textures/factory_floor/brick_diff.jpg")
    tx_save(yel, "brick_yellow.jpg")
    rough = tx_load(src / "rough_plaster_brick_diff_1k.jpg")
    tx_save(neutral(rough, 0.42, 0.35), "render_patchy.jpg")
    pl = tx_load(ROOT / "blender/textures/galleries/plastered_wall_04_diff_1k.jpg")
    tx_save(neutral(pl, 0.50, 0.0), "plaster.jpg")
    con = tx_load(ROOT / "blender/textures/factory_floor/concrete_floor_diff.jpg")
    tx_save(neutral(con, 0.40, 0.1), "concrete.jpg")
    wood = tx_load(ROOT / "blender/textures/apartment/dark_wood_diff_1k.jpg")
    tx_save(to_srgb(to_lin(neutral(wood, 0.20, 0.35)) * np.array((1.05, 0.98, 0.88))), "wood.jpg")       # weathered plywood boards
    tx_save(edge_tile(red, rng, "brick"), "edge_upper_a.jpg")
    tx_save(edge_tile(dark, rng, "brick"), "edge_upper_b.jpg")
    tx_save(edge_tile(neutral(rough, 0.30, 0.4), rng, "render"), "edge_upper_c.jpg")
    tx_save(edge_ground_tile(dark, rng), "edge_ground.jpg")
    tx_save(shop_atlas(rng), "shop_atlas.jpg")
    tx_save(lit_atlas(rng), "window_lit.jpg")
    tx_save(drain_pixels(), "drain.jpg")
    tx_save(gate_pixels(rng), "gate.jpg")
    tx_save(bd_atlas(np.random.default_rng(7), False), "bd_day.jpg")
    tx_save(bd_atlas(np.random.default_rng(7), True), "bd_night.jpg")
    tx_save(signs_pixels(), "signs_standin.png")


def stage_pack_backdrops():
    """The backdrop PNGs from the work folder -> world/backdrops/street_day.webp and street_night.webp (4096 x 2048, WebP q85)."""
    from PIL import Image
    work = Path(arg("--work", "."))
    out = ROOT / "world/backdrops"
    out.mkdir(parents=True, exist_ok=True)
    for k in ("day", "night"):
        im = Image.open(work / f"backdrop_{k}.png").convert("RGB")
        assert im.size == (4096, 2048), im.size
        dst = out / f"{SCENE}_{k}.webp"
        im.save(dst, "WEBP", quality=85, method=6)
        print(f"{dst.relative_to(ROOT)}  {im.size}  {dst.stat().st_size / 1e3:.0f} KB")


if bpy is None:
    if STAGE == "textures":
        stage_textures()
    elif STAGE == "pack-backdrops":
        stage_pack_backdrops()
    else:
        print("without Blender only --stage textures and --stage pack-backdrops run")
    sys.exit(0)


# ================================================================ Blender from here on
def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


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


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, diff=None, tint=None, emit=None, emit_img=None, alpha=None, tile=1.0):
    """A Principled material. `tint` multiplies the diffuse texture by a constant colour (a Mix node set to Multiply), which the glTF exporter writes as
    baseColorFactor. `emit` is (colour, strength); with `emit_img` the picture is the emission colour."""
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
    if diff:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image(diff, True)
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
    if emit_img:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image(emit_img, True)
        n.name = "EMIT_IMG"
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        nt.links.new(n.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    elif emit:
        bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    if alpha is not None:
        bsdf.inputs["Alpha"].default_value = alpha
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    TILES[name] = tile
    MATS[name] = m
    return m


LAMP_EMIT = ((1.0, 0.80, 0.52), 6.0)          # the lamp heads' lenses (sodium-warm), exported strength: the page switches it on from dusk
WINDOW_EMIT = 2.2                             # the lit windows' emissive strength (times their picture): the page switches it on at night


def make_materials():
    for b in BUILDINGS:
        lk = LOOK[b["id"]]
        material(f"Facade_{b['id']}", diff=lk["tex"], tint=facade_tint(b), rough=0.9, tile=lk["tile"])
    material("Road_Asphalt", diff="road_asphalt.jpg", rough=0.9, tile=4.0)
    material("Road_Line", color=(0.62, 0.62, 0.58), rough=0.6)
    material("Road_Yellow", color=(0.62, 0.42, 0.06), rough=0.6)
    material("Sidewalk_Slab", diff="sidewalk_slab.jpg", rough=0.85, tile=2.6)
    material("Kerb_Stone", diff="concrete.jpg", tint=(0.62, 0.62, 0.60), rough=0.8, tile=1.5)
    material("Backlot_Ground", diff="concrete.jpg", tint=(0.42, 0.42, 0.41), rough=0.95, tile=5.0)
    material("Drain_Iron", diff="drain.jpg", rough=0.6, metal=0.3)
    material("Roof_Felt", diff="concrete.jpg", tint=(0.17, 0.17, 0.18), rough=0.95, tile=3.0)
    material("Trim_Stone", diff="concrete.jpg", tint=(0.95, 0.92, 0.84), rough=0.85, tile=2.0)
    material("Fascia_Paint", color=(0.035, 0.06, 0.05), rough=0.45)
    material("Frame_Dark", color=(0.03, 0.033, 0.036), rough=0.4, metal=0.4)
    material("Shop_Glass", diff="shop_atlas.jpg", rough=0.08)
    material("Window_Dark", color=(0.03, 0.035, 0.045), rough=0.08)
    material("Window_Lit", color=(0.03, 0.032, 0.035), rough=0.1, emit=((1, 1, 1), WINDOW_EMIT), emit_img="window_lit.jpg")
    material("Door_Leaf", color=(0.055, 0.09, 0.075), rough=0.45)
    material("Boarding", diff="wood.jpg", rough=0.9, tile=2.4)
    material("Metal_Dark", color=(0.03, 0.032, 0.035), rough=0.45, metal=0.6)
    material("Lamp_Emit", color=(0.62, 0.60, 0.55), rough=0.3, emit=LAMP_EMIT)
    material("Shelter_Glass", color=(0.55, 0.62, 0.65), rough=0.05, alpha=0.18)
    material("Awning_Red", color=(0.30, 0.035, 0.03), rough=0.85)
    material("Awning_Green", color=(0.03, 0.15, 0.075), rough=0.85)
    material("Edge_Ground", diff="edge_ground.jpg", rough=0.9)
    material("Edge_Upper_A", diff="edge_upper_a.jpg", rough=0.9)
    material("Edge_Upper_B", diff="edge_upper_b.jpg", rough=0.9)
    material("Edge_Upper_C", diff="edge_upper_c.jpg", rough=0.9)
    material("Viaduct_Brick", diff="brick_dark.jpg", tint=(0.95, 0.9, 0.88), rough=0.9, tile=1.1)
    material("Edge_Gate", diff="gate.jpg", rough=0.6, metal=0.3, tile=3.4)
    # stand-ins (the review stills only, never baked or exported)
    material("Standin_Sign", color=(0, 0, 0), emit=((1, 1, 1), 1.0), emit_img="signs_standin.png")
    material("Standin_Lamp", color=(0, 0, 0), emit=((0.25, 0.88, 0.38), 6.0))
    material("Standin_Coat", color=lin_hex(0x4a4a58), rough=0.8)
    material("Standin_Skin", color=lin_hex(0xc8b8a8), rough=0.7)
    material("Standin_Dark", color=lin_hex(0x202024), rough=0.7)
    material("Standin_Shade", color=lin_hex(0x0a0a0c), rough=0.9)
    material("Standin_Ghost", color=(0.02, 0.02, 0.02), emit=((1.0, 0.85, 0.56), 3.0))


# ---------------------------------------------------------------- geometry (all built in world space, identity object transforms)
def quad(bm, pts, n, uv=None):
    """A face through game points `pts`, turned to face the game direction `n`; `uv` optional per-corner UVs."""
    vs = [bm.verts.new(B(p)) for p in pts]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.dot(B(n)) < 0:
        f.normal_flip()
    if uv:
        lay = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
        by_vert = dict(zip(vs, uv))
        for lp in f.loops:
            lp[lay].uv = by_vert[lp.vert]
    return f


def box(bm, mn, mx, skip=()):
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    F = {"-x": ([(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)], (-1, 0, 0)),
         "+x": ([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], (1, 0, 0)),
         "-y": ([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], (0, -1, 0)),
         "+y": ([(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)], (0, 1, 0)),
         "-z": ([(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)], (0, 0, -1)),
         "+z": ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], (0, 0, 1))}
    for k, (pts, n) in F.items():
        if k not in skip:
            quad(bm, pts, n)


def cyl(bm, p0, p1, r0, r1=None, seg=8, cap=True):
    a, b = B(p0), B(p1)
    d = b - a
    q = d.to_track_quat("Z", "Y")
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                          matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())


def box_uv(bm, tile):
    """UV0 for faces without their own: box projection in metres / tile, from world positions (game axes)."""
    lay = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        if f.tag:
            continue
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y
            if ax == 0:
                u, v = gz, gy
            elif ax == 1:
                u, v = gx, gy
            else:
                u, v = gx, gz
            lp[lay].uv = (u / tile, v / tile)


ART = STANDIN = None


def finish(name, bm, mat, coll=None, smooth=False, keep_uv=False):
    if not bm.faces:
        bm.free()
        return None
    for f in bm.faces:
        f.smooth = smooth
        f.tag = keep_uv
    if not keep_uv:
        box_uv(bm, TILES[mat])
    elif not bm.loops.layers.uv.get("UVMap"):
        box_uv(bm, TILES[mat])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(name, me)
    (coll or ART).objects.link(ob)
    return ob


class Parts:
    """Per-object bmeshes, by object name -> (material, bmesh, keep_uv)."""
    def __init__(self):
        self.d = {}

    def bm(self, name, mat, keep_uv=False):
        if name not in self.d:
            self.d[name] = (mat, bmesh.new(), keep_uv)
        return self.d[name][1]

    def done(self, coll=None):
        for name, (mat, bm, keep_uv) in self.d.items():
            finish(name, bm, mat, coll, keep_uv=keep_uv)
        self.d = {}


def cells(As, Ys, holes):
    """The cells of a grid on (a, y) not inside any hole (a0, a1, y0, y1)."""
    out = []
    for i in range(len(As) - 1):
        for j in range(len(Ys) - 1):
            ca, cy = (As[i] + As[i + 1]) / 2, (Ys[j] + Ys[j + 1]) / 2
            if any(h[0] < ca < h[1] and h[2] < cy < h[3] for h in holes):
                continue
            out.append((As[i], As[i + 1], Ys[j], Ys[j + 1]))
    return out


def grid(a0, a1, y0, y1, holes):
    As = sorted({a0, a1} | {v for h in holes for v in h[:2] if a0 < v < a1})
    Ys = sorted({y0, y1} | {v for h in holes for v in h[2:] if y0 < v < y1})
    return cells(As, Ys, holes)


# ---------------------------------------------------------------- a building
class Front:
    """A facade plane x = F whose outward normal is (s, 0, 0); `a` runs along game z, `d` is the depth into the building."""
    def __init__(self, F, s):
        self.F, self.s = F, s

    def p(self, a, y, d=0.0):
        return (self.F - self.s * d, y, a)

    def face(self, bm, a0, a1, y0, y1, d=0.0, n_out=True, uv=None):
        return quad(bm, [self.p(a0, y0, d), self.p(a1, y0, d), self.p(a1, y1, d), self.p(a0, y1, d)], (self.s if n_out else -self.s, 0, 0), uv)

    def reveal(self, bm, h, d):
        a0, a1, y0, y1 = h
        P = self.p
        quad(bm, [P(a0, y0), P(a1, y0), P(a1, y0, d), P(a0, y0, d)], (0, 1, 0))
        quad(bm, [P(a0, y1), P(a1, y1), P(a1, y1, d), P(a0, y1, d)], (0, -1, 0))
        quad(bm, [P(a0, y0), P(a0, y1), P(a0, y1, d), P(a0, y0, d)], (0, 0, 1))
        quad(bm, [P(a1, y0), P(a1, y1), P(a1, y1, d), P(a1, y0, d)], (0, 0, -1))

    def slab(self, bm, a0, a1, y0, y1, d0, d1, skip=()):
        """A box on the facade from depth d0 to d1 (negative: out in front of it)."""
        xa, xb = self.F - self.s * d0, self.F - self.s * d1
        box(bm, (min(xa, xb), y0, a0), (max(xa, xb), y1, a1), skip)

    def out_key(self):
        return "+x" if self.s > 0 else "-x"

    def in_key(self):
        return "-x" if self.s > 0 else "+x"


def atlas_uv(cell, n=2, inset=0.0):
    r, c = divmod(cell, n)
    u0, u1 = c / n + inset, (c + 1) / n - inset
    v1, v0 = 1 - r / n - inset, 1 - (r + 1) / n + inset
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def flip_u(uv):
    return [uv[1], uv[0], uv[3], uv[2]]


def shop_spans(b, a0, a1, dz):
    """The ground floor's runs along the front, cut round the door: [(a0, a1)]."""
    runs = [(a0 + PILASTER, a1 - PILASTER)]
    if dz is not None:
        out = []
        for r0, r1 in runs:
            if r0 < dz - DOOR_ZONE:
                out.append((r0, min(r1, dz - DOOR_ZONE)))
            if r1 > dz + DOOR_ZONE:
                out.append((max(r0, dz + DOOR_ZONE), r1))
        runs = out
    return [(r0, r1) for r0, r1 in runs if r1 - r0 > 1.2]


def panels(r0, r1, maxw=3.0, pier=0.3):
    n = max(1, math.ceil((r1 - r0 + pier) / (maxw + pier)))
    w = (r1 - r0 - (n - 1) * pier) / n
    return [(r0 + i * (w + pier), r0 + i * (w + pier) + w) for i in range(n)]


def sign_clash(slot):
    """True for a window pane the PHARMACY sign (3.4 x 0.64 m at SIGN) would overlap, with 25 cm round it."""
    if slot is None or SIGN["side"] != ("w" if slot["dir"] > 0 else "e"):
        return False
    return abs(slot["z"] - SIGN["z"]) < (PANE_W + 3.4) / 2 + 0.25 and abs(slot["y"] - SIGN["y"]) < (PANE_H + 0.64) / 2 + 0.25


def side_slots(length, h, margin=1.4):
    """Windows on a side or back face: (a, y) centres, every 3.4 m, one row a floor (3.6 m) from the first floor up."""
    out = []
    n = int((length - 2 * margin) // EDGE_BAY) + 1
    if n < 1:
        return out
    start = (length - (n - 1) * EDGE_BAY) / 2
    for f in range(1, 99):
        y = f * 3.6
        if y + 0.8 > h - 0.5:
            break
        for k in range(n):
            out.append((start + k * EDGE_BAY, y))
    return out


def build_building(b, P):
    bid = b["id"]
    lk = LOOK[bid]
    s = 1 if b["side"] == "w" else -1
    F = -FRONT if b["side"] == "w" else FRONT
    depth, h = b["depth"], b["h"]
    a0, a1 = min(b["z0"], b["z1"]), max(b["z0"], b["z1"])
    back = F - s * depth
    top = h + PAR
    fr = Front(F, s)
    door = DOORS.get(bid)
    dz = door["z"] if door else None
    rng = rng_for("bld", bid)
    mass = P.bm(f"Bld_{bid}", f"Facade_{bid}")
    hi = P.bm(f"TrimHi_{bid}", "Trim_Stone")
    frame = P.bm(f"Frame_{bid}", "Frame_Dark")
    glass = P.bm(f"Glass_{bid}", "Shop_Glass", keep_uv=True)
    lit = P.bm(f"WinLit_{bid}", "Window_Lit", keep_uv=True)
    dark = P.bm(f"WinDark_{bid}", "Window_Dark")

    holes = []            # (a0, a1, y0, y1, depth, kind)
    # the ground floor
    kind = lk["ground"]
    if dz is not None:                         # the door's threshold is level with the sidewalk
        holes.append((dz - DOOR_W / 2, dz + DOOR_W / 2, WALK_Y, DOOR_H, DOOR_DEPTH, "door"))
    runs = shop_spans(b, a0, a1, dz)
    if kind in ("shop", "lobby", "pharmacy", "boarded"):
        for r0, r1 in runs:
            for p0, p1 in panels(r0, r1, 3.2 if kind != "lobby" else 2.4):
                holes.append((p0, p1, SHOP_Y[0] if kind != "lobby" else 0.15, SHOP_Y[1], SHOP_DEPTH if kind != "boarded" else 0.06, kind))
    elif kind == "house":
        for r0, r1 in runs:
            for p0, p1 in panels(r0, r1, 1.3, 1.9):
                c = (p0 + p1) / 2
                holes.append((c - 0.6, c + 0.6, 0.9, 2.2, WIN_DEPTH, "housewin"))
    # the page's window slots (upper floors)
    for sl in X["windows"][bid]:
        if sign_clash(sl):
            continue
        # (the last slot of a long front can run past the building's end in the page's blockout: the pane stops 15 cm short of the corner)
        holes.append((max(a0 + 0.15, sl["z"] - PANE_W / 2), min(a1 - 0.15, sl["z"] + PANE_W / 2), sl["y"] - PANE_H / 2, sl["y"] + PANE_H / 2, WIN_DEPTH,
                      ("slot", sl["f"], sl["k"])))
    # the front face, cut round every hole, up to the parapet's top
    for c0, c1, y0, y1 in grid(a0, a1, 0.0, top, [h_[:4] for h_ in holes]):
        fr.face(mass, c0, c1, y0, y1)
    for hh in holes:
        a_0, a_1, y0, y1, d, k = hh
        fr.reveal(mass, hh[:4], d)
        if k == "door":
            build_door(fr, P, bid, hh)
        elif isinstance(k, tuple):
            f_, k_ = k[1], k[2]
            uvc = atlas_uv(int(rng.integers(4)))
            pane = (a_0, a_1, y0, y1)
            if (bid, f_, k_) in WATCH:
                wb = P.bm(f"WinWatch_{bid}", "Window_Lit", keep_uv=True)      # exported as Window_Watcher_<building>
                fr.face(wb, *pane, d=0.04, uv=uvc)
            elif rng.random() < 0.5:
                fr.face(lit, *pane, d=0.04, uv=uvc)
            else:
                fr.face(dark, *pane, d=0.04)
            # a stone sill and a lintel (both over head height, so outside the layout check's standing rule)
            fr.slab(hi, a_0 - 0.1, a_1 + 0.1, y0 - 0.07, y0, 0.0, -0.06, skip=(fr.in_key(),))
            fr.slab(hi, a_0 - 0.08, a_1 + 0.08, y1, y1 + 0.16, 0.0, -0.015, skip=(fr.in_key(),))
        elif k == "housewin":
            fr.face(dark, a_0, a_1, y0, y1, d=0.04)
            fr.slab(P.bm(f"TrimLo_{bid}", "Trim_Stone"), a_0 - 0.08, a_1 + 0.08, y0 - 0.06, y0, 0.0, -0.04, skip=(fr.in_key(),))
        elif k == "boarded":
            bd = P.bm(f"Board_{bid}", "Boarding")
            fr.face(bd, a_0, a_1, y0, y1, d=0.05)
        else:                                   # a shop or lobby panel: a frame ring and the glass
            gd = SHOP_DEPTH - 0.03
            cell = lk["glass"]
            fr.face(glass, a_0 + 0.05, a_1 - 0.05, y0 + 0.05, y1 - 0.05, d=gd, uv=atlas_uv(cell, inset=0.01))
            for (u0, u1, v0, v1) in ((a_0, a_0 + 0.06, y0, y1), (a_1 - 0.06, a_1, y0, y1), (a_0, a_1, y0, y0 + 0.07), (a_0, a_1, y1 - 0.06, y1)):
                fr.slab(frame, u0, u1, v0, v1, gd - 0.03, gd + 0.02, skip=(fr.in_key(),))
            if y1 - y0 > 1.8:                   # a transom bar
                fr.slab(frame, a_0, a_1, y1 - 0.45, y1 - 0.4, gd - 0.03, gd + 0.01, skip=(fr.in_key(),))
    # the fascia over the shop runs (never over the door: the page's sign hangs there), and the awnings
    if kind in ("shop", "pharmacy", "boarded", "lobby"):
        fa = P.bm(f"Fascia_{bid}", "Fascia_Paint")
        for r0, r1 in runs:
            r0_, r1_ = r0 - 0.1, r1 + 0.1
            if dz is not None:
                if r0_ < dz:
                    r1_ = min(r1_, dz - SIGN_ZONE)
                else:
                    r0_ = max(r0_, dz + SIGN_ZONE)
            if r1_ - r0_ > 0.5:
                fr.slab(fa, r0_, r1_, FASCIA_Y[0], FASCIA_Y[1], 0.0, -0.04, skip=(fr.in_key(),))
                if lk.get("awning"):
                    build_awning(fr, P, bid, r0_ + 0.1, r1_ - 0.1, lk["awning"])
    # back and sides: flush windows, a back door
    bk = Front(back, -s)
    for c0, c1, y0, y1 in grid(a0, a1, 0.0, top, []):
        bk.face(mass, c0, c1, y0, y1)
    r2 = rng_for("back", bid)
    for (a, y) in side_slots(a1 - a0, h):
        pane = (a0 + a - 0.6, a0 + a + 0.6, y - 0.65, y + 0.65)
        if r2.random() < 0.3:
            bk.face(lit, *pane, d=-0.012, uv=flip_u(atlas_uv(int(r2.integers(4)))))
        else:
            bk.face(dark, *pane, d=-0.012)
    bd = P.bm(f"BackDoor_{bid}", "Door_Leaf")
    bk.face(bd, (a0 + a1) / 2 - 0.5, (a0 + a1) / 2 + 0.5, 0.0, 2.1, d=-0.012)
    for zc, nz in ((a0, -1), (a1, 1)):           # the two sides (faces at z = a0 and a1)
        xs = sorted((back, F))
        quad(mass, [(xs[0], 0, zc), (xs[1], 0, zc), (xs[1], top, zc), (xs[0], top, zc)], (0, 0, nz))
        for (a, y) in side_slots(depth, h, 1.6):
            x0_ = F - s * (a - 0.6)
            x1_ = F - s * (a + 0.6)
            pts = [(x0_, y - 0.65, zc + nz * 0.012), (x1_, y - 0.65, zc + nz * 0.012), (x1_, y + 0.65, zc + nz * 0.012), (x0_, y + 0.65, zc + nz * 0.012)]
            if r2.random() < 0.3:
                quad(lit, pts, (0, 0, nz), atlas_uv(int(r2.integers(4))))
            else:
                quad(dark, pts, (0, 0, nz))
    # the roof inside the parapet, the parapet's inner faces and its coping
    t = 0.25
    roof = P.bm(f"Roof_{bid}", "Roof_Felt")
    xi0, xi1 = sorted((F - s * t, back + s * t))
    quad(roof, [(xi0, h, a0 + t), (xi1, h, a0 + t), (xi1, h, a1 - t), (xi0, h, a1 - t)], (0, 1, 0))
    quad(mass, [(xi0, h, a0 + t), (xi1, h, a0 + t), (xi1, top, a0 + t), (xi0, top, a0 + t)], (0, 0, 1))
    quad(mass, [(xi0, h, a1 - t), (xi1, h, a1 - t), (xi1, top, a1 - t), (xi0, top, a1 - t)], (0, 0, -1))
    quad(mass, [(xi0, h, a0 + t), (xi0, h, a1 - t), (xi0, top, a1 - t), (xi0, top, a0 + t)], (1, 0, 0))
    quad(mass, [(xi1, h, a0 + t), (xi1, h, a1 - t), (xi1, top, a1 - t), (xi1, top, a0 + t)], (-1, 0, 0))
    xo0, xo1 = sorted((F, back))
    for (q0, q1, r0, r1) in ((xo0, xo1, a0, a0 + t), (xo0, xo1, a1 - t, a1), (xo0, xi0, a0 + t, a1 - t), (xi1, xo1, a0 + t, a1 - t)):
        quad(mass, [(q0, top, r0), (q1, top, r0), (q1, top, r1), (q0, top, r1)], (0, 1, 0))
    # a cornice along the street front, under the parapet's top
    fr.slab(hi, a0, a1, top - 0.45, top - 0.1, 0.0, -0.2, skip=(fr.in_key(),))
    fr.slab(hi, a0, a1, top - 0.02, top + 0.06, 0.03, -0.06, skip=())
    # plant on the roof: the tower's lift room and water tank, a box on the bigger roofs
    if bid == "tower":
        cx, cz = (F + back) / 2, (a0 + a1) / 2
        box(mass, (cx - 3.5, h, cz - 2.5), (cx + 3.5, h + 3.2, cz + 2.5), skip=("-y",))
        box(roof, (cx - 3.6, h + 3.2, cz - 2.6), (cx + 3.6, h + 3.35, cz + 2.6), skip=("-y",))
        cyl(P.bm(f"RoofPlant_{bid}", "Metal_Dark"), (cx + 5.5, h, cz + 4), (cx + 5.5, h + 2.6, cz + 4), 1.3, seg=12)
    elif depth * (a1 - a0) > 250:
        cx, cz = (F + back) / 2 - s * 2, (a0 + a1) / 2 + 2
        box(P.bm(f"RoofPlant_{bid}", "Metal_Dark"), (cx - 1.5, h, cz - 1.0), (cx + 1.5, h + 1.6, cz + 1.0), skip=("-y",))


def build_door(fr, P, bid, hh):
    """A pair of leaves at the back of the door's recess: a dark frame, a painted lower panel and glass above; the page's shutter comes down in front."""
    a0, a1, y0, y1, d, _ = hh
    frame = P.bm(f"Frame_{bid}", "Frame_Dark")
    leaf = P.bm(f"Door_{bid}", "Door_Leaf")
    glass = P.bm(f"Glass_{bid}", "Shop_Glass", keep_uv=True)
    dd = d - 0.03
    for (u0, u1, v0, v1) in ((a0, a0 + 0.07, y0, y1), (a1 - 0.07, a1, y0, y1), (a0, a1, y1 - 0.08, y1)):
        fr.slab(frame, u0, u1, v0, v1, dd - 0.02, dd + 0.03, skip=(fr.in_key(),))
    mid = (a0 + a1) / 2
    for l0, l1 in ((a0 + 0.07, mid - 0.005), (mid + 0.005, a1 - 0.07)):
        fr.slab(leaf, l0, l1, 0.0, 0.95, dd, dd + 0.02, skip=(fr.in_key(), "-y"))
        fr.face(glass, l0 + 0.08, l1 - 0.08, 1.0, y1 - 0.2, d=dd + 0.01, uv=atlas_uv(3, inset=0.05))
        for (u0, u1, v0, v1) in ((l0, l0 + 0.08, 0.95, y1 - 0.08), (l1 - 0.08, l1, 0.95, y1 - 0.08), (l0, l1, y1 - 0.2, y1 - 0.08), (l0, l1, 0.95, 1.0)):
            fr.slab(leaf, u0, u1, v0, v1, dd - 0.005, dd + 0.02, skip=(fr.in_key(),))
        hx = l1 - 0.12 if l0 < mid else l0 + 0.06
        fr.slab(frame, hx, hx + 0.06, 0.9, 1.25, dd - 0.06, dd - 0.005, skip=(fr.in_key(),))      # a push bar


def build_awning(fr, P, bid, r0, r1, mat):
    """A canvas awning over a shop run: from the fascia's foot out 1.2 m, falling 0.45 m, with a 0.22 m valance (its lowest edge 2.0 m up)."""
    aw = P.bm(f"Awning_{bid}", mat)
    y_top, out, drop, val = FASCIA_Y[0] + 0.02, 1.2, 0.45, 0.2          # its lowest edge 1.82 m up: over head height
    P_ = fr.p
    quad(aw, [P_(r0, y_top, 0.0), P_(r1, y_top, 0.0), P_(r1, y_top - drop, -out), P_(r0, y_top - drop, -out)], (fr.s, 1, 0))
    quad(aw, [P_(r0, y_top - drop, -out), P_(r1, y_top - drop, -out), P_(r1, y_top - drop - val, -out), P_(r0, y_top - drop - val, -out)], (fr.s, 0, 0))
    for a, n in ((r0, -1), (r1, 1)):                                    # the cheeks
        quad(aw, [P_(a, y_top, 0.0), P_(a, y_top - drop, -out), P_(a, y_top - drop - val, -out), P_(a, y_top - 0.12, 0.0)], (0, 0, n))


# ---------------------------------------------------------------- the ground
def building_boxes():
    out = []
    for b in BUILDINGS:
        c = COLL[f"Building_{b['id']}"][0]
        out.append((c["min"][0], c["max"][0], c["min"][2], c["max"][2]))
    return out


def build_ground(P):
    z0, z1 = WORLD["z0"], WORLD["z1"]
    xw = WORLD["x"]
    rx0, rx1 = ROAD["x0"], ROAD["x1"]
    # the road, cut into 30 m lengths
    road = P.bm("Road", "Road_Asphalt")
    zs = list(np.arange(z0, z1, 30.0)) + [z1]
    for i in range(len(zs) - 1):
        quad(road, [(rx0, ROAD_Y, zs[i]), (rx1, ROAD_Y, zs[i]), (rx1, ROAD_Y, zs[i + 1]), (rx0, ROAD_Y, zs[i + 1])], (0, 1, 0))
    # the kerbs and the sidewalks, both sides, the whole length
    kerb = P.bm("Kerb", "Kerb_Stone")
    walk = P.bm("Sidewalk", "Sidewalk_Slab")
    for sgn in (-1, 1):
        xk = rx1 if sgn > 0 else rx0
        xa, xb = sorted((xk, xk + sgn * KERB_W))
        for i in range(len(zs) - 1):                       # in 30 m lengths, so no AO island is longer than that
            quad(kerb, [(xk, ROAD_Y, zs[i]), (xk, WALK_Y, zs[i]), (xk, WALK_Y, zs[i + 1]), (xk, ROAD_Y, zs[i + 1])], (-sgn, 0, 0))
            quad(kerb, [(xa, WALK_Y, zs[i]), (xb, WALK_Y, zs[i]), (xb, WALK_Y, zs[i + 1]), (xa, WALK_Y, zs[i + 1])], (0, 1, 0))
        xa, xb = sorted((xk + sgn * KERB_W, sgn * FRONT))
        for i in range(len(zs) - 1):
            quad(walk, [(xa, WALK_Y, zs[i]), (xb, WALK_Y, zs[i]), (xb, WALK_Y, zs[i + 1]), (xa, WALK_Y, zs[i + 1])], (0, 1, 0))
    # where no building stands on the sidewalk's back edge, its edge steps down to the yards (y 0)
    bb = building_boxes()
    for sgn in (-1, 1):
        xe = sgn * FRONT
        fronts = sorted((b[2], b[3]) for b in bb if (b[0] if sgn > 0 else b[1]) == xe)
        z = z0
        gaps = []
        for f0, f1 in fronts:
            if f0 > z:
                gaps.append((z, f0))
            z = max(z, f1)
        if z < z1:
            gaps.append((z, z1))
        for g0, g1 in gaps:
            quad(walk, [(xe, 0.0, g0), (xe, WALK_Y, g0), (xe, WALK_Y, g1), (xe, 0.0, g1)], (sgn, 0, 0))
    # the yards behind and between the buildings, at y 0, with a skirt down to y -1 at the world's edge (the collision floor is a metre thick)
    yard = P.bm("Yard", "Backlot_Ground")
    for sgn in (-1, 1):
        xs = sorted({sgn * FRONT, sgn * xw} | {v for b in bb for v in (b[0], b[1]) if (v * sgn) >= FRONT})
        zz = sorted({z0, z1} | {v for b in bb for v in (b[2], b[3])})
        xs2, zs2 = [], []
        for i in range(len(xs) - 1):
            n = max(1, int(math.ceil((xs[i + 1] - xs[i]) / 26.0)))
            xs2 += list(np.linspace(xs[i], xs[i + 1], n + 1)[:-1])
        xs2.append(xs[-1])
        for i in range(len(zz) - 1):
            n = max(1, int(math.ceil((zz[i + 1] - zz[i]) / 26.0)))
            zs2 += list(np.linspace(zz[i], zz[i + 1], n + 1)[:-1])
        zs2.append(zz[-1])
        for i in range(len(xs2) - 1):
            for j in range(len(zs2) - 1):
                cx, cz = (xs2[i] + xs2[i + 1]) / 2, (zs2[j] + zs2[j + 1]) / 2
                if any(b[0] < cx < b[1] and b[2] < cz < b[3] for b in bb):
                    continue
                quad(yard, [(xs2[i], 0, zs2[j]), (xs2[i + 1], 0, zs2[j]), (xs2[i + 1], 0, zs2[j + 1]), (xs2[i], 0, zs2[j + 1])], (0, 1, 0))
    xs_ = list(np.linspace(-xw, xw, 5))                                  # the skirt, in lengths of 30 m or less (AO islands)
    for zc, n in ((z0, (0, 0, -1)), (z1, (0, 0, 1))):
        for a, b_ in zip(xs_[:-1], xs_[1:]):
            quad(yard, [(a, -1.0, zc), (b_, -1.0, zc), (b_, ROAD_Y, zc), (a, ROAD_Y, zc)], n)
    for sgn in (-1, 1):
        for a, b_ in zip(zs[:-1], zs[1:]):
            quad(yard, [(sgn * xw, -1.0, a), (sgn * xw, -1.0, b_), (sgn * xw, 0.0, b_), (sgn * xw, 0.0, a)], (sgn, 0, 0))
    # road paint: the centre dashes (as the blockout's: every 8 m), double yellow lines along both kerbs, the bus stop's box, parking bays in the yards
    line = P.bm("RoadLine", "Road_Line")
    yel = P.bm("RoadYellow", "Road_Yellow")
    yp = ROAD_Y + 0.008
    z = ROAD["z1"] - 4
    while z > ROAD["z0"]:
        quad(line, [(-0.07, yp, z - 1.8), (0.07, yp, z - 1.8), (0.07, yp, z + 1.8), (-0.07, yp, z + 1.8)], (0, 1, 0))
        z -= 8
    bz0, bz1 = BUS["arrive"][2] - 9.0, BUS["arrive"][2] + 7.0          # the bus stop's clearway on the east side, round the arrival point
    for sgn in (-1, 1):
        for off in (0.25, 0.42):
            xa = sgn * (rx1 - off) - 0.045
            spans = [(z0, z1)] if sgn < 0 else [(z0, bz0), (bz1, z1)]
            for p0, p1 in spans:
                cut = sorted({p0, p1} | {v for v in zs if p0 < v < p1})
                for q0, q1 in zip(cut[:-1], cut[1:]):
                    quad(yel, [(xa, yp, q0), (xa + 0.09, yp, q0), (xa + 0.09, yp, q1), (xa, yp, q1)], (0, 1, 0))
    bx0, bx1 = rx1 - 2.6, rx1 - 0.25
    for (u0, u1, v0, v1) in ((bx0, bx1, bz0, bz0 + 0.15), (bx0, bx1, bz1 - 0.15, bz1), (bx0, bx0 + 0.15, bz0, bz1)):
        quad(yel, [(u0, yp, v0), (u1, yp, v0), (u1, yp, v1), (u0, yp, v1)], (0, 1, 0))
    for sgn in (-1, 1):                                                 # parking bays along the edge walls: a line every 2.6 m, 5 m long
        x_in = sgn * (xw - 5.5)
        z = z0 + 4.0
        while z < z1 - 4.0:
            xa, xb = sorted((x_in, sgn * (xw - 0.6)))
            quad(line, [(xa, 0.006, z - 0.05), (xb, 0.006, z - 0.05), (xb, 0.006, z + 0.05), (xa, 0.006, z + 0.05)], (0, 1, 0))
            z += 2.6
    # drains along the kerbs and a few manhole covers
    dr = P.bm("Drains", "Drain_Iron", keep_uv=True)
    duv = [(0, 0), (1, 0), (1, 1), (0, 1)]
    for z in np.arange(ROAD["z1"] - 6, ROAD["z0"], -12.0):
        for sgn in (-1, 1):
            xa, xb = sorted((sgn * (rx1 - 0.02), sgn * (rx1 - 0.38)))
            quad(dr, [(xa, ROAD_Y + 0.006, z - 0.3), (xb, ROAD_Y + 0.006, z - 0.3), (xb, ROAD_Y + 0.006, z + 0.3), (xa, ROAD_Y + 0.006, z + 0.3)], (0, 1, 0), duv)
    rm = rng_for("manholes")
    for z in np.arange(ROAD["z1"] - 15, ROAD["z0"], -23.0):
        x = float(rm.uniform(-3.0, 3.0))
        if abs(x) < 0.5:
            x += 1.0
        quad(dr, [(x - 0.35, ROAD_Y + 0.006, z - 0.35), (x + 0.35, ROAD_Y + 0.006, z - 0.35), (x + 0.35, ROAD_Y + 0.006, z + 0.35), (x - 0.35, ROAD_Y + 0.006, z + 0.35)],
             (0, 1, 0), [(0.1, 0.0), (0.9, 0.0), (0.9, 1.0), (0.1, 1.0)])


# ---------------------------------------------------------------- the lamp posts and the bus shelter
def build_lamps(P):
    for z in LAMP_ZS:
        for sgn in (-1, 1):
            c = next(cc for cc in COLL["Lamp_Street"] if abs((cc["min"][2] + cc["max"][2]) / 2 - z) < 1e-6 and (cc["min"][0] > 0) == (sgn > 0))
            x = (c["min"][0] + c["max"][0]) / 2
            hw = (c["max"][0] - c["min"][0]) / 2
            tag = f"{'E' if sgn > 0 else 'W'}{abs(int(z)):03d}"
            post = P.bm(f"LampPost_{tag}", "Metal_Dark")
            box(post, (x - hw, 0.0, z - hw), (x + hw, 0.55, z + hw), skip=("-y",))           # the base, the collider's size
            cyl(post, (x, 0.55, z), (x, 4.75, z), 0.065, 0.05, seg=8)
            head = P.bm(f"LampHead_{tag}", "Metal_Dark")
            ex = x - sgn * 1.25                                                                 # the arm reaches out over the road
            cyl(head, (x, 4.70, z), (ex, 4.78, z), 0.035, seg=6)
            box(head, (min(ex, ex - sgn * 0.55) - 0.0, 4.68, z - 0.16), (max(ex, ex - sgn * 0.55), 4.82, z + 0.16))
            lens = P.bm(f"LampLens_{tag}", "Lamp_Emit")
            l0, l1 = sorted((ex - sgn * 0.05, ex - sgn * 0.5))
            quad(lens, [(l0, 4.675, z - 0.12), (l1, 4.675, z - 0.12), (l1, 4.675, z + 0.12), (l0, 4.675, z + 0.12)], (0, -1, 0))


def build_shelter(P):
    """The bus shelter round the bench's collider: its back glass along the bench's north edge (where the blockout's glass is), the posts at the
    bench's ends, a side panel at the east end, all inside the collider's floor plan; the roof cantilevers out over the bench (over head height)."""
    c = COLL["Bench_BusStop"][0]
    x0, x1, z0, z1 = c["min"][0], c["max"][0], c["min"][2], c["max"][2]
    fr = P.bm("Shelter_Frame", "Metal_Dark")
    gl = P.bm("Shelter_Glass", "Shelter_Glass")
    for x in (x0 + 0.04, x1 - 0.04):
        box(fr, (x - 0.04, 0.0, z0), (x + 0.04, 2.32, z0 + 0.08), skip=("-y",))
    box(fr, (x0, 2.24, z0), (x1, 2.32, z0 + 0.08))
    box(fr, (x0, 0.08, z0), (x1, 0.14, z0 + 0.08))
    quad(gl, [(x0 + 0.08, 0.14, z0 + 0.04), (x1 - 0.08, 0.14, z0 + 0.04), (x1 - 0.08, 2.24, z0 + 0.04), (x0 + 0.08, 2.24, z0 + 0.04)], (0, 0, 1))
    quad(gl, [(x0 + 0.08, 0.14, z0 + 0.04), (x1 - 0.08, 0.14, z0 + 0.04), (x1 - 0.08, 2.24, z0 + 0.04), (x0 + 0.08, 2.24, z0 + 0.04)], (0, 0, -1))
    xe = x1 - 0.04                                                      # the side panel at the east end
    box(fr, (xe - 0.04, 0.0, z1 - 0.08), (xe + 0.04, 2.32, z1), skip=("-y",))
    quad(gl, [(xe, 0.14, z0 + 0.08), (xe, 0.14, z1 - 0.08), (xe, 2.24, z1 - 0.08), (xe, 2.24, z0 + 0.08)], (1, 0, 0))
    quad(gl, [(xe, 0.14, z0 + 0.08), (xe, 0.14, z1 - 0.08), (xe, 2.24, z1 - 0.08), (xe, 2.24, z0 + 0.08)], (-1, 0, 0))
    # the bench: a perforated steel seat on two legs, facing south (the blockout's way)
    box(fr, (x0 + 0.2, 0.42, z0 + 0.12), (x1 - 0.2, 0.47, z1 - 0.12))
    box(fr, (x0 + 0.2, 0.47, z0 + 0.10), (x1 - 0.2, 0.88, z0 + 0.16))
    for x in (x0 + 0.3, x1 - 0.35):
        box(fr, (x, 0.0, z0 + 0.2), (x + 0.05, 0.42, z1 - 0.2), skip=("-y",))
    roof = P.bm("ShelterRoof", "Metal_Dark")
    box(roof, (x0 - 0.3, 2.32, z0 - 0.15), (x1 + 0.3, 2.42, z1 + 0.75))
    tt = P.bm("ShelterSign", "Fascia_Paint")
    box(tt, (x0 + 0.35, 2.42, z1 + 0.6), (x1 - 0.35, 2.68, z1 + 0.68))


# ---------------------------------------------------------------- the world's edge: rows of buildings at the edge walls, a railway viaduct at the north end
def edge_segments(side):
    """Segments of the edge row on one side: (s0, s1, height, style). W and E run along z, S along x."""
    w = COLL[{"W": "Wall_W", "E": "Wall_E", "S": "Wall_S"}[side]][0]
    if side in ("W", "E"):
        s_lo, s_hi = w["min"][2], w["max"][2]
    else:
        s_lo, s_hi = w["min"][0], w["max"][0]
    rng = rng_for("edge", side)
    out, s = [], s_lo
    while s < s_hi - 1e-6:
        n = int(rng.integers(4, 9))
        s1 = min(s_hi, s + n * EDGE_BAY)
        if s_hi - s1 < 2 * EDGE_BAY:
            s1 = s_hi
        hfl = int(rng.integers(3, 7)) if side != "S" else int(rng.integers(3, 5))
        out.append((s, s1, EDGE_FLOOR * (hfl + 1) + 0.6, "ABC"[int(rng.integers(3))]))
        s = s1
    return out, w


def build_edges(P):
    for side in ("W", "E", "S"):
        segs, w = edge_segments(side)
        if side == "W":
            plane, nrm = w["max"][0], (1, 0, 0)
        elif side == "E":
            plane, nrm = w["min"][0], (-1, 0, 0)
        else:
            plane, nrm = w["min"][2], (0, 0, -1)
        thick = 1.0
        rng = rng_for("edgewin", side)

        def pt(sv, y, d=0.0):                       # a point on the row's face: `sv` along it, `d` metres back into the wall (or out, negative)
            if side in ("W", "E"):
                return (plane - nrm[0] * d, y, sv)
            return (sv, y, plane - nrm[2] * d)
        for i, (s0, s1, H, st) in enumerate(segs):
            g = P.bm(f"EdgeG_{side}{i:02d}", "Edge_Ground", keep_uv=True)
            u = P.bm(f"EdgeU_{side}{i:02d}", f"Edge_Upper_{st}", keep_uv=True)
            top = P.bm(f"EdgeTop_{side}{i:02d}", "Roof_Felt")
            L_ = s1 - s0
            road_gate = side == "S" and s0 < ROAD["x1"] and s1 > ROAD["x0"]
            nb = int(math.ceil(L_ / EDGE_BAY - 1e-6))
            # the row is a metre deep (its collider): a 1 cm sliver of its back face, full height, makes the piece's box the wall's
            quad(g, [pt(s0, 0.0, thick), pt(s0 + 0.01, 0.0, thick), pt(s0 + 0.01, H, thick), pt(s0, H, thick)], tuple(-v for v in nrm), [(0, 0), (0.001, 0), (0.001, 0.001), (0, 0.001)])
            for k in range(nb):
                b0, b1 = s0 + k * EDGE_BAY, min(s1, s0 + (k + 1) * EDGE_BAY)
                uv0, uv1 = (k % 2) * 0.5, (k % 2) * 0.5 + 0.5 * (b1 - b0) / EDGE_BAY
                uvg = [(uv0, 0), (uv1, 0), (uv1, 1), (uv0, 1)]
                quad(g, [pt(b0, 0.0), pt(b1, 0.0), pt(b1, EDGE_FLOOR), pt(b0, EDGE_FLOOR)], nrm, uvg)
                nf = int(round((H - 0.6 - EDGE_FLOOR) / EDGE_FLOOR))
                for f in range(nf):
                    y0, y1 = EDGE_FLOOR * (f + 1), EDGE_FLOOR * (f + 2)
                    quad(u, [pt(b0, y0), pt(b1, y0), pt(b1, y1), pt(b0, y1)], nrm, [(a, v) for (a, v) in ((uvg[0][0], 0), (uvg[1][0], 0), (uvg[2][0], 1), (uvg[3][0], 1))])
                    if b1 - b0 > EDGE_BAY - 0.01 and rng.random() < 0.28:            # a lit window over the painted one (the texture's window: 1.4 x 1.55 m)
                        c = (b0 + b1) / 2
                        quad(P.bm(f"EdgeLit_{side}", "Window_Lit", keep_uv=True),
                             [pt(c - 0.62, y0 + 0.98, -0.012), pt(c + 0.62, y0 + 0.98, -0.012), pt(c + 0.62, y0 + 2.38, -0.012), pt(c - 0.62, y0 + 2.38, -0.012)],
                             nrm, atlas_uv(int(rng.integers(4))))
                # the parapet band over the last floor
                yt = EDGE_FLOOR * (nf + 1)
                quad(u, [pt(b0, yt), pt(b1, yt), pt(b1, H), pt(b0, H)], nrm, [(uvg[0][0], 0.0), (uvg[1][0], 0.0), (uvg[1][0], 0.12), (uvg[0][0], 0.12)])
                if road_gate is False and rng.random() < 0.12:                      # a gate onto a yard behind
                    quad(P.bm(f"EdgeGate_{side}", "Edge_Gate"), [pt(b0 + 0.2, 0.0, -0.015), pt(b1 - 0.2, 0.0, -0.015), pt(b1 - 0.2, 3.0, -0.015), pt(b0 + 0.2, 3.0, -0.015)], nrm)
            if road_gate:                                                            # the road ends at a depot's gate
                quad(P.bm("EdgeGate_S", "Edge_Gate"), [pt(ROAD["x0"] + 0.5, 0.0, -0.015), pt(ROAD["x1"] - 0.5, 0.0, -0.015), pt(ROAD["x1"] - 0.5, 4.6, -0.015), pt(ROAD["x0"] + 0.5, 4.6, -0.015)], nrm)
            quad(top, [pt(s0, H, 0.0), pt(s1, H, 0.0), pt(s1, H, thick), pt(s0, H, thick)], (0, 1, 0))
            # where the neighbour is lower, the step's end face
            for j, sv, ns in ((i - 1, s0, -1), (i + 1, s1, 1)):
                hn = segs[j][2] if 0 <= j < len(segs) else 0.0
                if hn < H:
                    ndir = (0, 0, ns) if side in ("W", "E") else (ns, 0, 0)
                    quad(u, [pt(sv, hn, 0.0), pt(sv, hn, thick), pt(sv, H, thick), pt(sv, H, 0.0)], ndir, [(0, 0), (0.15, 0), (0.15, 0.3), (0, 0.3)])
            # a coping along the top, out over the face (above head height)
            cp = P.bm(f"EdgeCope_{side}", "Trim_Stone")
            a, b_ = pt(s0, H - 0.25, -0.18), pt(s1, H + 0.05, 0.0)
            box(cp, tuple(min(a[k], b_[k]) for k in range(3)), tuple(max(a[k], b_[k]) for k in range(3)), skip=())


def build_viaduct(P):
    """The north end: a brick railway viaduct on the edge wall Wall_N, blind arches every 10 m, the middle one over the road closed by a steel gate."""
    w = COLL["Wall_N"][0]
    zf = w["max"][2]                     # its face (z -150), looking +z
    x0, x1 = w["min"][0], w["max"][0]
    H = 14.4
    span, spring = 7.6, 5.0
    rad = span / 2
    gate = P.bm("ViaductGate", "Edge_Gate")
    trim = P.bm("ViaductTrim", "Trim_Stone")
    centres = [c for c in np.arange(-50.0, 50.01, 10.0)]
    edges = [x0] + [v for c in centres for v in (c - rad, c + rad)] + [x1]
    seg = 10
    for j, c in enumerate(centres):
        # one piece a bay (its pier to the west, the arch; the last also the east end's pier), so no AO island is longer than a bay
        vb = P.bm(f"Viaduct_{j:02d}", "Viaduct_Brick")
        piers = [(edges[2 * j], edges[2 * j + 1])] + ([(edges[-2], edges[-1])] if j == len(centres) - 1 else [])
        for a, b_ in piers:
            quad(vb, [(a, 0, zf), (b_, 0, zf), (b_, H, zf), (a, H, zf)], (0, 0, 1))
        # a 1 cm sliver of the viaduct's back face (it is a metre deep, as its collider), full height, so the piece's box spans the wall's depth
        quad(vb, [(edges[2 * j], 0, w["min"][2]), (edges[2 * j] + 0.01, 0, w["min"][2]), (edges[2 * j] + 0.01, H, w["min"][2]), (edges[2 * j], H, w["min"][2])], (0, 0, -1))
        d = 0.95 if abs(c) < 1e-6 else 0.45
        arch = [(c + rad * math.cos(math.pi * (1 - t / seg)), spring + rad * math.sin(math.pi * (1 - t / seg))) for t in range(seg + 1)]
        for (xa, ya), (xb, yb) in zip(arch[:-1], arch[1:]):                    # the spandrel over the arch, a strip per arch segment, and the arch's soffit
            quad(vb, [(xa, ya, zf), (xb, yb, zf), (xb, H, zf), (xa, H, zf)], (0, 0, 1))
            quad(vb, [(xa, ya, zf), (xb, yb, zf), (xb, yb, zf - d), (xa, ya, zf - d)], (c - (xa + xb) / 2, spring - (ya + yb) / 2, 0))
        for xs_, n in ((c - rad, 1), (c + rad, -1)):                           # the jambs
            quad(vb, [(xs_, 0, zf), (xs_, spring, zf), (xs_, spring, zf - d), (xs_, 0, zf - d)], (n, 0, 0))
        poly = [(c - rad, 0.0), (c + rad, 0.0), (c + rad, spring)] + [p for p in reversed(arch[1:-1])] + [(c - rad, spring)]
        target = gate if abs(c) < 1e-6 else vb
        vs = [target.verts.new(B((px, py, zf - d))) for px, py in poly]
        f = target.faces.new(vs)
        f.normal_update()
        if f.normal.dot(B((0, 0, 1))) < 0:
            f.normal_flip()
        # a keystone (over head height: trim)
        box(trim, (c - 0.25, spring + rad - 0.05, zf), (c + 0.25, spring + rad + 0.55, zf + 0.05), skip=("-z",))
    # string course, coping and the deck's top, in 10 m lengths
    cuts = [x0] + [c + 5.0 for c in centres[:-1]] + [x1]
    top = P.bm("ViaductTop", "Roof_Felt")
    for a, b_ in zip(cuts[:-1], cuts[1:]):
        box(trim, (a, 12.6, zf), (b_, 12.95, zf + 0.18), skip=("-z",))
        box(trim, (a, H, zf - 1.0), (b_, H + 0.12, zf + 0.12))
        quad(top, [(a, H + 0.12, zf - 1.0), (b_, H + 0.12, zf - 1.0), (b_, H + 0.12, zf + 0.12), (a, H + 0.12, zf + 0.12)], (0, 1, 0))
    # overhead line masts and a railing on top (over head height)
    m = P.bm("ViaductMasts", "Metal_Dark")
    for x in np.arange(x0 + 8, x1 - 4, 20.0):
        box(m, (x - 0.12, H + 0.12, zf - 0.6), (x + 0.12, H + 6.5, zf - 0.36), skip=("-y",))
        box(m, (x - 0.06, H + 5.6, zf - 0.6), (x + 0.06, H + 5.75, zf + 1.8))
    box(m, (x0, H + 1.05, zf - 0.04), (x1, H + 1.12, zf + 0.04))
    for x in np.arange(x0 + 1, x1, 2.0):
        box(m, (x - 0.025, H + 0.12, zf - 0.025), (x + 0.025, H + 1.05, zf + 0.025), skip=("-y",))


def build_wires(P):
    """Phone and power lines strung across the street between the upper floors (over head height)."""
    w = P.bm("Wires", "Metal_Dark")
    rng = rng_for("wires")
    for z in (-12.0, -37.0, -63.0, -91.0, -125.0):
        y0, y1 = float(rng.uniform(6.2, 7.0)), float(rng.uniform(6.2, 7.0))
        dz = float(rng.uniform(-3, 3))
        pts = []
        for t in np.linspace(0, 1, 9):
            x = -FRONT + 2 * FRONT * t
            pts.append((x, y0 + (y1 - y0) * t - 0.9 * math.sin(math.pi * t), z + dz * t))
        for a, b_ in zip(pts[:-1], pts[1:]):
            cyl(w, a, b_, 0.012, seg=4, cap=False)


# ---------------------------------------------------------------- the page's things, as stand-ins (index.html cityProps, anomalyProps): stills only
def build_standins():
    rows = len(L["doors"]) + 1
    for i, d in enumerate(L["doors"]):
        s = 1 if d["side"] == "w" else -1
        x = d["x"] + s * 0.06
        bm = bmesh.new()
        y = DOOR_H + 0.55
        r0 = i / rows
        uv = [(0, 1 - (i + 1) / rows), (1, 1 - (i + 1) / rows), (1, 1 - r0), (0, 1 - r0)]
        pts = [(x, y - 0.26, d["z"] + s * 1.4), (x, y - 0.26, d["z"] - s * 1.4), (x, y + 0.26, d["z"] - s * 1.4), (x, y + 0.26, d["z"] + s * 1.4)]
        quad(bm, pts, (s, 0, 0), uv)
        finish(f"standin_sign_{d['id']}", bm, "Standin_Sign", STANDIN, keep_uv=True)
        bm = bmesh.new()
        lx = d["x"] + s * 0.07
        box(bm, (lx - 0.03, 1.4, d["z"] + 1.1), (lx + 0.03, 1.6, d["z"] + 1.3))
        finish(f"standin_lamp_{d['id']}", bm, "Standin_Lamp", STANDIN)
    s = 1 if SIGN["side"] == "w" else -1
    x = (-FRONT if SIGN["side"] == "w" else FRONT) + s * 0.06
    bm = bmesh.new()
    uv =[(0, 0), (1, 0), (1, 1 / rows), (0, 1 / rows)]
    pts = [(x, SIGN["y"] - 0.32, SIGN["z"] + s * 1.7), (x, SIGN["y"] - 0.32, SIGN["z"] - s * 1.7), (x, SIGN["y"] + 0.32, SIGN["z"] - s * 1.7), (x, SIGN["y"] + 0.32, SIGN["z"] + s * 1.7)]
    quad(bm, pts, (s, 0, 0), uv)
    finish("standin_sign_pharmacy", bm, "Standin_Sign", STANDIN, keep_uv=True)
    for j, (px, pz) in enumerate(X["pedestrians"]):                          # anomalyProps' plain figures, all facing up the street (-z)
        for mat, parts in (("Standin_Coat", [(0.46, 0.8, 0.28, 0, 1.0, 0), (0.12, 0.62, 0.12, -0.3, 1.02, 0), (0.12, 0.62, 0.12, 0.3, 1.02, 0)]),
                           ("Standin_Dark", [(0.16, 0.6, 0.16, -0.12, 0.3, 0), (0.16, 0.6, 0.16, 0.12, 0.3, 0), (0.05, 0.04, 0.02, -0.06, 1.64, -0.135), (0.05, 0.04, 0.02, 0.06, 1.64, -0.135)]),
                           ("Standin_Skin", [(0.26, 0.3, 0.26, 0, 1.6, 0)])):
            bm = bmesh.new()
            for (w_, h_, d_, ox, oy, oz) in parts:
                box(bm, (px + ox - w_ / 2, oy - h_ / 2, pz + oz - d_ / 2), (px + ox + w_ / 2, oy + h_ / 2, pz + oz + d_ / 2))
            finish(f"standin_ped_{j}_{mat[8:].lower()}", bm, mat, STANDIN)
    for w in X["watchers"]:                                                    # the watchers (night stills): a dark figure in each window
        p = w["at"]
        bm = bmesh.new()
        y = p["y"] - 0.65
        box(bm, (p["x"] - 0.14, y, p["z"] - 0.275), (p["x"] + 0.14, y + 0.6, p["z"] + 0.275))
        box(bm, (p["x"] - 0.13, y + 0.67, p["z"] - 0.13), (p["x"] + 0.13, y + 0.97, p["z"] + 0.13))
        finish(f"standin_night_watcher_{w['building']}", bm, "Standin_Shade", STANDIN)
    gx, gy, gz = GHOST["at"]
    bm = bmesh.new()
    quad(bm, [(gx - GHOST["w"] / 2, gy - GHOST["h"] / 2, gz), (gx + GHOST["w"] / 2, gy - GHOST["h"] / 2, gz), (gx + GHOST["w"] / 2, gy + GHOST["h"] / 2, gz), (gx - GHOST["w"] / 2, gy + GHOST["h"] / 2, gz)], (0, 0, 1))
    finish("standin_night_ghost_window", bm, "Standin_Ghost", STANDIN)


def ensure_marker():
    st = bpy.data.collections["Standins"]
    ob = bpy.data.objects.get("standin_arrival_marker")
    if ob is None:
        bm = bmesh.new()
        a = BUS["arrive"]
        box(bm, (a[0] - 0.1, a[1], a[2] - 0.1), (a[0] + 0.1, a[1] + 0.2, a[2] + 0.1))
        ob = finish("standin_arrival_marker", bm, "Standin_Dark", st)
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
    a = BUS["arrive"]
    want = [a[0], a[1] + 0.1, a[2]]
    bl = sum((v.co for v in ob.data.vertices), Vector()) / len(ob.data.vertices)
    print(f"AXES blender centre {tuple(round(v, 3) for v in bl)}, glTF centre {tuple(round(v, 3) for v in centre)}, game point {tuple(want)}")
    assert all(abs(centre[i] - want[i]) < 1e-4 for i in range(3)), "the exporter's axes disagree with (x, -z, y)"
    assert abs(bl.x - want[0]) < 1e-4 and abs(bl.y + want[2]) < 1e-4 and abs(bl.z - want[1]) < 1e-4
    print("AXES PASS: game (x, y, z) = Blender (x, -z, y) = glTF (x, y, z)")


# ---------------------------------------------------------------- lights and worlds (the bake needs none: AO is geometry only)
SUN_DAY = 4.0
WORLD_DAY = 0.9


def add_lights():
    lights = bpy.data.collections.new("Lights")
    bpy.context.scene.collection.children.link(lights)
    d = bpy.data.lights.new("Sun", "SUN")
    d.energy, d.color, d.angle = SUN_DAY, (1.0, 0.93, 0.82), math.radians(0.8)
    ob = bpy.data.objects.new("Sun", d)
    ob.rotation_euler = B((-0.55, -0.62, 0.55)).to_track_quat("-Z", "Y").to_euler()        # from the south-west, 38 degrees up: it lights the east side
    lights.objects.link(ob)
    d = bpy.data.lights.new("Moon", "SUN")
    d.energy, d.color, d.angle = 0.04, (0.6, 0.7, 1.0), math.radians(1.0)
    ob = bpy.data.objects.new("Moon", d)
    ob.rotation_euler = B((0.4, -0.8, 0.45)).to_track_quat("-Z", "Y").to_euler()
    lights.objects.link(ob)
    for z in LAMP_ZS:                                                       # a spot under each lamp head (the night stills only; the page lights its own)
        for sgn in (-1, 1):
            c = next(cc for cc in COLL["Lamp_Street"] if abs((cc["min"][2] + cc["max"][2]) / 2 - z) < 1e-6 and (cc["min"][0] > 0) == (sgn > 0))
            x = (c["min"][0] + c["max"][0]) / 2 - sgn * 1.5
            d = bpy.data.lights.new(f"LampSpot_{sgn}_{z}", "SPOT")
            d.energy, d.color, d.spot_size, d.spot_blend, d.shadow_soft_size = 1400.0, (1.0, 0.72, 0.42), math.radians(130), 0.6, 0.15
            ob = bpy.data.objects.new(d.name, d)
            ob.location = B((x, 4.6, z))
            lights.objects.link(ob)


def set_time(night):
    lights = bpy.data.collections["Lights"]
    for o in lights.objects:
        if o.name == "Sun":
            o.hide_render = night
        elif o.name == "Moon" or o.name.startswith("LampSpot_"):
            o.hide_render = not night
    for name, on in (("Lamp_Emit", night), ("Window_Lit", night)):
        m = bpy.data.materials.get(name)
        if m:
            bs = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
            bs.inputs["Emission Strength"].default_value = (LAMP_EMIT[1] if name == "Lamp_Emit" else WINDOW_EMIT) if on else 0.0
    for o in bpy.data.collections["Standins"].objects:
        if "_night_" in o.name:
            o.hide_render = not night


def setup_world(night=False, backdrop=None):
    """The sky that lights the stills, and for camera rays the backdrop picture (its middle column north, Blender +Y, its right east, +X)."""
    sc = bpy.context.scene
    w = bpy.data.worlds.get("Street") or bpy.data.worlds.new("Street")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    sky = nt.nodes.new("ShaderNodeBackground")
    sky.inputs["Color"].default_value = (0.04, 0.05, 0.09, 1) if night else (0.50, 0.62, 0.85, 1)
    sky.inputs["Strength"].default_value = 0.35 if night else WORLD_DAY
    if backdrop and Path(backdrop).exists():
        tc = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Rotation"].default_value = (0, 0, -math.pi / 2)      # turns Blender +Y (north) to where an equirect picture's middle looks (+X)
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(str(backdrop), check_existing=True)
        cam = nt.nodes.new("ShaderNodeBackground")
        cam.inputs["Strength"].default_value = 1.0
        lp = nt.nodes.new("ShaderNodeLightPath")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
        nt.links.new(env.outputs["Color"], cam.inputs["Color"])
        nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
        nt.links.new(sky.outputs[0], mix.inputs[1])
        nt.links.new(cam.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
    else:
        nt.links.new(sky.outputs[0], out.inputs["Surface"])
    w.light_settings.distance = AO_DIST


AO_DIST = 7.0           # metres: the AO bake's reach (World > Ambient Occlusion > Distance, which Cycles' AO bake reads)


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
    sc.unit_settings.system = "METRIC"
    make_materials()
    P = Parts()
    build_ground(P)
    for b in BUILDINGS:
        build_building(b, P)
    build_lamps(P)
    build_shelter(P)
    build_edges(P)
    build_viaduct(P)
    build_wires(P)
    P.done()
    build_standins()
    add_lights()
    setup_world()
    ensure_marker()
    set_time(False)
    n = len(ART.objects)
    tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in ART.objects)
    print(f"ART {n} objects, {tris} triangles")


# ---------------------------------------------------------------- bake (AO only)
GROUPS = [["Road_Asphalt", "Road_Line", "Road_Yellow", "Sidewalk_Slab", "Kerb_Stone", "Backlot_Ground", "Drain_Iron"],                     # 0: the ground
          [f"Facade_{b['id']}" for b in BUILDINGS] + ["Roof_Felt"],                                          # 1: the buildings
          ["Edge_Ground", "Edge_Upper_A", "Edge_Upper_B", "Edge_Upper_C", "Viaduct_Brick", "Edge_Gate"],                                    # 2: the edge rows, the viaduct
          ["Door_Leaf", "Boarding", "Awning_Red", "Awning_Green"]]                                                                       # 3: the small things
PAGES = [2048, 2048, 2048, 512]
if arg("--pages"):
    PAGES = [None] * 4 if arg("--pages") == "auto" else [int(v) for v in arg("--pages").split(",")]
NO_AO = ("Window_Lit", "Lamp_Emit", "Shelter_Glass", "Window_Dark", "Shop_Glass", "Frame_Dark", "Metal_Dark", "Trim_Stone", "Fascia_Paint")
# (emissive, glass, near black, or the thousand small sills, lintels and copings, whose islands would crowd the buildings' page)
NO_WELD = ("Road", "Kerb", "Sidewalk", "Yard", "RoadLine", "RoadYellow", "Drains")         # big flat quads, each its own AO island (welded they make 180 m strips)
KEEP_SEPARATE = {"WinWatch_": "Window_Watcher_"}     # exported as their own meshes, so the page can find the watchers' panes by name


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
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces, cy.transmission_bounces, cy.transparent_max_bounces = 8, 4, 3, 6, 16
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
    by_key = {}
    for ob in art.objects:
        assert len(ob.data.materials) == 1, ob.name
        mname = ob.data.materials[0].name
        sep = next((p for p in KEEP_SEPARATE if ob.name.startswith(p)), None)
        key = KEEP_SEPARATE[sep] + ob.name[len(sep):] if sep else mname
        bm = by_key.setdefault(key, (mname, bmesh.new()))[1]
        tmp = bmesh.new()
        tmp.from_mesh(ob.data)
        if not ob.name.startswith(NO_WELD):           # weld within a piece only: welding across pieces would join long AO islands
            bmesh.ops.remove_doubles(tmp, verts=tmp.verts, dist=1e-5)
        me = bpy.data.meshes.new("tmp")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    out = {}
    for key, (mname, bm) in by_key.items():
        me = bpy.data.meshes.new(key)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(bpy.data.materials[mname])
        ob = bpy.data.objects.new(key, me)
        exp.objects.link(ob)
        out[key] = ob
    return out


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


def lightmap_uv(objs, page=None, want=12.0):
    """UV1 ("lightmap"): one shared atlas for `objs`, smart-project islands at equal texel density, packed with MARGIN_PX, on `page` px (or the
    smallest page that gives `want` px/m)."""
    for o in objs:
        uvs = o.data.uv_layers
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.new(name="lightmap")
        uvs.active = uvs["lightmap"]
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    chosen = None
    for S in ((page,) if page else (512, 768, 1024, 1536, 2048)):
        bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / S, shape_method="CONCAVE")
        bpy.ops.object.mode_set(mode="OBJECT")
        a3 = sum(area3d(o) for o in objs)
        au = sum(uv_area(o, "lightmap") for o in objs)
        dens = S * math.sqrt(au / a3)
        print(f"  page {S}: {a3:.1f} m2, {dens:.1f} px/m")
        chosen = (S, dens)
        if dens >= want:
            break
        bpy.ops.object.mode_set(mode="EDIT")
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        o.data.uv_layers.active = o.data.uv_layers["UVMap"]
        o.data.uv_layers["UVMap"].active_render = True
    return chosen


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
    os.remove(path)
    return a.reshape(S, S, 4)


def stage_bake():
    import time
    stage_work()
    exp = make_export_objects()
    for cn in ("Art", "Standins"):
        bpy.data.collections[cn].hide_render = True
        bpy.data.collections[cn].hide_viewport = True
    setup_world()
    setup_cycles(SAMPLES, bake=True)
    report = {}
    for n, mats in enumerate(GROUPS):
        t0 = time.time()
        objs = [exp[m] for m in mats if m in exp]
        print(f"AO map {n}: {[o.name for o in objs]}")
        S, dens = lightmap_uv(objs, PAGES[n])
        img = bpy.data.images.new(f"AO_{n}", S, S, alpha=False, float_buffer=True)
        img.colorspace_settings.name = "Non-Color"
        for o in objs:
            nt = o.data.materials[0].node_tree
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
        a = denoise_image(img, S)
        ao = np.clip(a[..., :3].mean(axis=2), 0, 1)
        lit = ao[ao > 1e-4]
        pc = np.percentile(lit, [1, 10, 50, 90]) if lit.size else [1.0] * 4
        print("  AO percentiles p1 p10 p50 p90:", [round(float(v), 3) for v in pc])
        out = np.ones((S, S, 4), np.float32)
        out[..., 0] = out[..., 1] = out[..., 2] = ao                     # linear AO (the page loads it with NoColorSpace)
        png = bpy.data.images.new(f"AO_{n}_png", S, S, alpha=False)
        png.colorspace_settings.name = "Non-Color"
        png.pixels.foreach_set(out.ravel())
        png.filepath_raw = str(stage_work() / f"{SCENE}_{n}.png")
        png.file_format = "PNG"
        png.save()
        for o in objs:
            m = o.data.materials[0]
            m["aomap"] = AO_URL.format(n)
            m["aomap_intensity"] = 1.0
            nt = m.node_tree
            for nd in [nd for nd in nt.nodes if nd.name.startswith("BAKE_TARGET")]:
                nt.nodes.remove(nd)
        report[n] = {"size": S, "px_per_m": round(dens, 1), "p1_p10_p50_p90": [round(float(v), 3) for v in pc], "samples": SAMPLES, "distance_m": AO_DIST,
                     "device": bpy.context.scene.cycles.device, "seconds": round(time.time() - t0), "materials": [o.data.materials[0].name for o in objs]}
        print("  baked", report[n])
        bpy.data.images.remove(img)
        bpy.data.images.remove(png)
    (stage_work() / "aomaps.json").write_text(json.dumps(report, indent=1))
    for cn in ("Art", "Standins"):
        bpy.data.collections[cn].hide_render = False
        bpy.data.collections[cn].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


# ---------------------------------------------------------------- privacy
def scrub_ui_paths():
    for sc in bpy.data.screens:
        for a in sc.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"_" * 1000
                    sp.params.directory = b"//"


KEEP_PROPS = {"aomap", "aomap_intensity"}      # the only custom properties this scene carries (on materials, for the page)
SYS_KEEP = ("cycles", "eevee")


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private():
    """The .blend, the GLB (export_extras) and the stills are public: drop every custom property but the materials' AO extras, make image paths
    relative, blank the render output path and every stamp, and the file browser's remembered folder (the galleries build's scrub)."""
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
    scrub_ui_paths()


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    for im in [im for im in bpy.data.images if im.name.startswith("backdrop_")]:     # the rendered panoramas are not kept in the .blend
        bpy.data.images.remove(im)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    scrub_private()
    bpy.ops.wm.save_mainfile()


# ---------------------------------------------------------------- export
def stage_export():
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    for cn in ("Art", "Standins", "Backdrop"):
        if cn in bpy.data.collections:
            bpy.data.collections[cn].hide_viewport = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in exp.objects:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = stage_work() / f"{SCENE}_raw.glb"
    for name, k in (("Lamp_Emit", LAMP_EMIT[1]), ("Window_Lit", WINDOW_EMIT)):    # the page's "on" strength is the exported one
        bs = next(n for n in bpy.data.materials[name].node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        bs.inputs["Emission Strength"].default_value = k
    scrub_private()
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False, export_animations=False)
    print("EXPORTED", raw, raw.stat().st_size)
    albedo_report()
    for cn in ("Art", "Standins"):
        bpy.data.collections[cn].hide_viewport = False
    exp.hide_viewport = exp.hide_render = True


def albedo_report():
    """The displayed albedo of every exported material (its texture times its colour factor, linear): p90 of the brightest channel. The page lights
    these materials with its own sun and sky, so keep them under about 0.8 or a sunlit street clips."""
    rep = {}
    for m in sorted({o.data.materials[0] for o in bpy.data.collections["Export"].objects}, key=lambda m: m.name):
        nt = m.node_tree
        bs = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        base = np.array(bs.inputs["Base Color"].default_value[:3])
        tex = next((n for n in nt.nodes if n.type == "TEX_IMAGE" and n.name != "EMIT_IMG"), None)
        mix = next((n for n in nt.nodes if n.type == "MIX"), None)
        if tex is not None:
            im = tex.image
            w, h = im.size
            a = np.empty(w * h * 4, np.float32)
            im.pixels.foreach_get(a)
            px = a.reshape(-1, 4)[:, :3]
            if im.colorspace_settings.name == "sRGB":
                px = to_lin(px)                               # a byte image's pixels come as stored (sRGB / 255)
            f =np.array(mix.inputs[7].default_value[:3]) if mix else np.ones(3)
            vals = (px * f).max(axis=1)
        else:
            vals = np.array([base.max()])
        rep[m.name] = round(float(np.percentile(vals, 90)), 3)
    worst = max(rep.values())
    print("ALBEDO p90 (brightest channel, linear):", json.dumps(rep))
    print(f"ALBEDO worst p90 {worst:.3f} ({'PASS' if worst <= 0.8 else 'FAIL'}: at most about 0.8)")
    (stage_work() / "albedo.json").write_text(json.dumps(rep, indent=1))


# ---------------------------------------------------------------- the backdrops (R3): the city past both ends, 4096 x 2048 equirect, day and night
BD_CENTRE = ((WORLD["z0"] + WORLD["z1"]) / 2)          # the panoramas are taken from the middle of the street's world, at eye height


def bd_material(name, night):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(TEX / ("bd_night.jpg" if night else "bd_day.jpg")), check_existing=True)
    nt.links.new(uv.outputs["UV"], tex.inputs["Vector"])
    cd = nt.nodes.new("ShaderNodeCameraData")
    haze = nt.nodes.new("ShaderNodeEmission")
    haze.inputs["Color"].default_value = (0.11, 0.07, 0.05, 1) if night else (0.66, 0.73, 0.84, 1)
    haze.inputs["Strength"].default_value = 1.0
    # fac = 1 - exp(-d / L)
    dv = nt.nodes.new("ShaderNodeMath")
    dv.operation = "DIVIDE"
    dv.inputs[1].default_value = -1100.0 if night else -900.0
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = "EXPONENT"
    sub = nt.nodes.new("ShaderNodeMath")
    sub.operation = "SUBTRACT"
    sub.inputs[0].default_value = 1.0
    nt.links.new(cd.outputs["View Distance"], dv.inputs[0])
    nt.links.new(dv.outputs[0], ex.inputs[0])
    nt.links.new(ex.outputs[0], sub.inputs[1])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(sub.outputs[0], mix.inputs[0])
    if night:
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Strength"].default_value = 3.0
        nt.links.new(tex.outputs["Color"], em.inputs["Color"])
        dif = nt.nodes.new("ShaderNodeBsdfDiffuse")
        dif.inputs["Color"].default_value = (0.012, 0.012, 0.014, 1)
        add = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(em.outputs[0], add.inputs[0])
        nt.links.new(dif.outputs[0], add.inputs[1])
        nt.links.new(add.outputs[0], mix.inputs[1])
    else:
        bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bs.inputs["Roughness"].default_value = 0.8
        nt.links.new(tex.outputs["Color"], bs.inputs["Base Color"])
        nt.links.new(bs.outputs[0], mix.inputs[1])
    nt.links.new(haze.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return m


def build_backdrop_city():
    """The city round Hallam Row, outside its world: blocks of flats, offices and warehouses on a ground plane, taller towards a centre to the north,
    a church spire, chimneys, two tower cranes. Rendered into the panoramas only; never exported."""
    if "Backdrop" in bpy.data.collections:
        for o in list(bpy.data.collections["Backdrop"].objects):
            bpy.data.objects.remove(o)
        coll = bpy.data.collections["Backdrop"]
    else:
        coll = bpy.data.collections.new("Backdrop")
        bpy.context.scene.collection.children.link(coll)
    rng = np.random.default_rng(404)
    cz = BD_CENTRE
    xw, z0, z1 = WORLD["x"], WORLD["z0"], WORLD["z1"]
    bms = {k: bmesh.new() for k in range(4)}
    placed = []

    def free(x, zc, r):
        if -xw - 18 - r < x < xw + 18 + r and z0 - 18 - r < zc < z1 + 18 + r:
            return False
        return all((x - px) ** 2 + (zc - pz) ** 2 > (r + pr) ** 2 for px, pz, pr in placed)
    for _ in range(2600):
        ang = rng.uniform(0, 2 * math.pi)
        dist = 85 + rng.gamma(1.5, 220)
        if dist > 2200:
            continue
        x, zc = math.sin(ang) * dist, cz - math.cos(ang) * dist
        north = -math.cos(ang)                                   # 1 looking north (to the centre), -1 south
        w, d = rng.uniform(14, 34), rng.uniform(14, 34)
        r = math.hypot(w, d) / 2
        if not free(x, zc, r):
            continue
        placed.append((x, zc, r))
        # tall enough to rise over the edge rows (14 to 26 m, 60 m out to the sides): about 20 to 30 degrees up near the sides, less far off
        hbase = min(150.0, 30 + 0.10 * dist)
        h = rng.uniform(0.6, 1.5) * hbase * (1.4 if north > 0.6 and dist > 300 else 1.0)
        if rng.random() < 0.10:
            h *= rng.uniform(1.6, 2.6)                          # the odd tower
        h = min(h, 320.0)
        k = int(rng.integers(4)) if h < 60 else (2 if rng.random() < 0.6 else 0)
        bm = bms[k]
        rot = Matrix.Rotation(float(rng.choice([0.0, 0.0, rng.uniform(-0.4, 0.4)])), 4, "Z")
        tmp = bmesh.new()
        box(tmp, (x - w / 2, 0, zc - d / 2), (x + w / 2, h, zc + d / 2), skip=("-y",))
        bmesh.ops.transform(tmp, matrix=Matrix.Translation(B((x, 0, zc))) @ rot @ Matrix.Translation(-B((x, 0, zc))), verts=tmp.verts)
        lay = tmp.loops.layers.uv.new("UVMap")
        for f in tmp.faces:                                                  # UV in cells of 12 m; the material maps it into the kind's cell, repeating
            nrm = f.normal
            for lp in f.loops:
                p = lp.vert.co
                if abs(nrm.z) > 0.5:
                    lp[lay].uv = (0.02, 0.02)                                # a roof: a patch of wall colour
                else:
                    t = p.x if abs(nrm.x) < abs(nrm.y) else p.y
                    lp[lay].uv = (t / 12.0, p.z / 12.0)
        me = bpy.data.meshes.new("tmp")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    # landmarks
    lm = bmesh.new()
    sx, sz = -260.0, cz + 120.0                                                  # a church to the west: a tower and a spire
    box(lm, (sx - 5, 0, sz - 5), (sx + 5, 38, sz + 5), skip=("-y",))
    cyl(lm, (sx, 38, sz), (sx, 70, sz), 5.5, 0.05, seg=8)
    for (cx_, cz_, hh) in ((340.0, cz - 60, 62.0), (380.0, cz - 30, 55.0), (-420.0, cz - 380, 80.0)):     # chimneys
        cyl(lm, (cx_, 0, cz_), (cx_, hh, cz_), 3.2, 2.2, seg=12)
    for (cx_, cz_) in ((120.0, z0 - 260), (-160.0, z0 - 320)):                  # tower cranes to the north
        box(lm, (cx_ - 1.2, 0, cz_ - 1.2), (cx_ + 1.2, 78, cz_ + 1.2), skip=("-y",))
        box(lm, (cx_ - 18, 78, cz_ - 0.8), (cx_ + 46, 80, cz_ + 0.8))
        box(lm, (cx_ - 1.5, 80, cz_ - 1.5), (cx_ + 1.5, 86, cz_ + 1.5))
    ground = bmesh.new()
    G = 6000
    quad(ground, [(-G, -0.05, cz - G), (G, -0.05, cz - G), (G, -0.05, cz + G), (-G, -0.05, cz + G)], (0, 1, 0))
    objs = []
    for k, bm in bms.items():
        me =bpy.data.meshes.new(f"bd_blocks_{k}")
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(f"bd_blocks_{k}", me)
        coll.objects.link(ob)
        objs.append((ob, k))
    me = bpy.data.meshes.new("bd_landmarks")
    lm.to_mesh(me)
    lm.free()
    ob = bpy.data.objects.new("bd_landmarks", me)
    coll.objects.link(ob)
    objs.append((ob, -1))
    me = bpy.data.meshes.new("bd_ground")
    ground.to_mesh(me)
    ground.free()
    ob = bpy.data.objects.new("bd_ground", me)
    coll.objects.link(ob)
    objs.append((ob, -2))
    return coll, objs


def bd_cell_material(k, night):
    """A backdrop block material showing cell k of the 2 x 2 atlas (a Mapping node scales and offsets UV into the cell, repeating)."""
    name = f"bd_{'night' if night else 'day'}_{k}"
    m = bd_material(name, night)
    nt = m.node_tree
    tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
    uv = next(n for n in nt.nodes if n.type == "UVMAP")
    # fract(uv) * 0.5 + cell offset
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(uv.outputs["UV"], sep.inputs[0])
    for i, axis in enumerate(("X", "Y")):
        fr_ = nt.nodes.new("ShaderNodeMath")
        fr_.operation = "FRACT"
        mu = nt.nodes.new("ShaderNodeMath")
        mu.operation = "MULTIPLY_ADD"
        mu.inputs[1].default_value = 0.5
        mu.inputs[2].default_value = (k % 2) * 0.5 if i == 0 else (1 - (k // 2 + 1) * 0.5)
        nt.links.new(sep.outputs[i], fr_.inputs[0])
        nt.links.new(fr_.outputs[0], mu.inputs[0])
        nt.links.new(mu.outputs[0], comb.inputs[i])
    nt.links.new(comb.outputs[0], tex.inputs["Vector"])
    tex.interpolation = "Closest" if night else "Linear"
    return m


def plain_bd_material(name, col, night, emit=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if emit:
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = (*emit[0], 1)
        e.inputs["Strength"].default_value = emit[1]
        nt.links.new(e.outputs[0], out.inputs["Surface"])
        return m
    cd = nt.nodes.new("ShaderNodeCameraData")
    dv = nt.nodes.new("ShaderNodeMath")
    dv.operation = "DIVIDE"
    dv.inputs[1].default_value = -1100.0 if night else -900.0
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = "EXPONENT"
    sub = nt.nodes.new("ShaderNodeMath")
    sub.operation = "SUBTRACT"
    sub.inputs[0].default_value = 1.0
    nt.links.new(cd.outputs["View Distance"], dv.inputs[0])
    nt.links.new(dv.outputs[0], ex.inputs[0])
    nt.links.new(ex.outputs[0], sub.inputs[1])
    bs = nt.nodes.new("ShaderNodeBsdfDiffuse")
    bs.inputs["Color"].default_value = (*col, 1)
    haze = nt.nodes.new("ShaderNodeEmission")
    haze.inputs["Color"].default_value = (0.11, 0.07, 0.05, 1) if night else (0.66, 0.73, 0.84, 1)
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(sub.outputs[0], mix.inputs[0])
    nt.links.new(bs.outputs[0], mix.inputs[1])
    nt.links.new(haze.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return m


def sky_world(night):
    """A gradient sky for the panoramas: hazy pale at the horizon to blue overhead by day; by night a dark navy with a sodium glow low down."""
    w = bpy.data.worlds.get("BackdropSky") or bpy.data.worlds.new("BackdropSky")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    cr = ramp.color_ramp
    if night:
        stops = [(0.0, (0.10, 0.06, 0.035)), (0.06, (0.075, 0.05, 0.04)), (0.22, (0.022, 0.025, 0.045)), (1.0, (0.004, 0.006, 0.016))]
    else:
        stops = [(0.0, (0.68, 0.74, 0.84)), (0.08, (0.62, 0.70, 0.84)), (0.35, (0.36, 0.50, 0.76)), (1.0, (0.20, 0.33, 0.62))]
    cr.elements[0].position, cr.elements[0].color = stops[0][0], (*stops[0][1], 1)
    cr.elements[1].position, cr.elements[1].color = stops[-1][0], (*stops[-1][1], 1)
    for p, c in stops[1:-1]:
        e = cr.elements.new(p)
        e.color = (*c, 1)
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    bpy.context.scene.world = w
    return w


def pano_camera():
    cam = bpy.data.cameras.get("pano") or bpy.data.cameras.new("pano")
    cam.type = "PANO"
    for owner in (cam, getattr(cam, "cycles", None)):
        if owner is not None and hasattr(owner, "panorama_type"):
            owner.panorama_type = "EQUIRECTANGULAR"
    cam.clip_start, cam.clip_end = 0.1, 20000
    ob = bpy.data.objects.get("pano") or bpy.data.objects.new("pano", cam)
    if ob.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(ob)
    ob.location = B((0.0, 1.6, BD_CENTRE))
    ob.rotation_euler = (math.pi / 2, 0, 0)                    # looking north (+Y), its right is east (+X)
    return ob


def orientation_test(coll_hide):
    """Before the panoramas: three glowing markers far out (red east, green north, blue south) on a black sky, rendered small; the picture's middle
    column must be green, three quarters across red, the edges blue (docs/BLENDER.md R3: the middle faces north, the right east)."""
    sc = bpy.context.scene
    tmp = bpy.data.collections.new("OrientTest")
    sc.collection.children.link(tmp)
    for name, p, col in (("east", (400, 1.6, BD_CENTRE), (1, 0, 0)), ("north", (0, 1.6, BD_CENTRE - 400), (0, 1, 0)), ("south", (0, 1.6, BD_CENTRE + 400), (0, 0, 1))):
        bm = bmesh.new()
        box(bm, (p[0] - 40, p[1] - 40, p[2] - 40), (p[0] + 40, p[1] + 40, p[2] + 40))
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(plain_bd_material(f"orient_{name}", (0, 0, 0), False, emit=(col, 5.0)))
        ob = bpy.data.objects.new(f"orient_{name}", me)
        tmp.objects.link(ob)
    w = bpy.data.worlds.new("black")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
    sc.world = w
    for c in coll_hide:
        c.hide_render = True
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 256, 128, 100
    keep_samples = sc.cycles.samples
    sc.cycles.samples = 4
    sc.render.image_settings.file_format = "PNG"
    path = stage_work() / "orient_test.png"
    sc.render.filepath = str(path)
    sc.view_settings.view_transform = "Standard"
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(str(path))
    a = np.empty(256 * 128 * 4, np.float32)
    im.pixels.foreach_get(a)
    a = a.reshape(128, 256, 4)[64]                               # the horizon row
    def centre(ch):                                              # the middle of the marker's run of bright pixels (the seam wraps for south)
        on = np.nonzero(a[:, ch] > 0.5 * a[:, ch].max())[0]
        if on.size and on.max() - on.min() > 128:
            on = np.where(on < 128, on + 256, on)
        return int(round(on.mean())) % 256
    col_of = {c: centre(i) for i, c in enumerate(("red", "green", "blue"))}
    print("ORIENT columns of the markers on the horizon row:", col_of)
    assert abs(col_of["green"] - 128) <= 4, "north is not in the middle"
    assert abs(col_of["red"] - 192) <= 4, "east is not three quarters across (the right)"
    assert min(col_of["blue"], 255 - col_of["blue"]) <= 4, "south is not at the edges"
    print("ORIENT PASS: middle north (-z), right east (+x)")
    bpy.data.images.remove(im)
    for o in list(tmp.objects):
        bpy.data.objects.remove(o)
    bpy.data.collections.remove(tmp)
    bpy.data.worlds.remove(w)
    sc.cycles.samples = keep_samples
    for c in coll_hide:
        c.hide_render = False


def stage_backdrop():
    sc = bpy.context.scene
    coll, objs = build_backdrop_city()
    others = [c for c in bpy.data.collections if c.name in ("Art", "Standins", "Export", "Lights")]
    setup_cycles(arg("--bd-samples", 96, int))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    cam = pano_camera()
    sc.camera = cam
    coll.hide_render = True
    orientation_test(others)
    coll.hide_render = False
    for c in others:
        c.hide_render = True
    sun = bpy.data.lights.get("bd_sun") or bpy.data.lights.new("bd_sun", "SUN")
    sun.energy, sun.color, sun.angle = 3.2, (1.0, 0.94, 0.85), math.radians(1)
    so = bpy.data.objects.get("bd_sun") or bpy.data.objects.new("bd_sun", sun)
    if so.name not in coll.objects:
        coll.objects.link(so)
    so.rotation_euler = B((-0.55, -0.62, 0.55)).to_track_quat("-Z", "Y").to_euler()
    for night in (False, True):
        for ob, k in objs:
            ob.data.materials.clear()
            if k >= 0:
                ob.data.materials.append(bd_cell_material(k, night))
            elif k == -1:
                ob.data.materials.append(plain_bd_material(f"bd_landmark_{night}", (0.30, 0.29, 0.28) if not night else (0.01, 0.01, 0.012), night))
            else:
                ob.data.materials.append(plain_bd_material(f"bd_ground_{night}", (0.16, 0.16, 0.15) if not night else (0.02, 0.018, 0.016), night))
        so.hide_render = night
        sky_world(night)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 4096, 2048, 100
        sc.view_settings.view_transform = "AgX"
        try:
            sc.view_settings.look = "AgX - Base Contrast"
        except TypeError:
            pass
        sc.view_settings.exposure = 0.0
        sc.render.image_settings.file_format = "PNG"
        sc.render.image_settings.color_depth = "8"
        path = stage_work() / f"backdrop_{'night' if night else 'day'}.png"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print("BACKDROP", path, path.stat().st_size)
    coll.hide_render = True
    coll.hide_viewport = True
    for c in others:
        c.hide_render = c.name in ("Export",)
    setup_world()
    save_blend()


# ---------------------------------------------------------------- the review stills
def look_cam(name, loc, target, fov_v=75.0, ortho=None):
    cam = bpy.data.cameras.new(name)
    cam.sensor_fit = "VERTICAL"
    if ortho:
        cam.type = "ORTHO"
        cam.ortho_scale = ortho
        cam.sensor_fit = "AUTO"
    else:
        cam.lens_unit = "FOV"
        cam.angle_y = math.radians(fov_v)
    cam.clip_start, cam.clip_end = 0.05, 3000
    ob = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = B(loc)
    if target is not None:
        ob.rotation_euler = (B(target) - B(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


def strip_jpeg_meta(path):
    """Drop the JPEG's comment (FE) and APP1 (E1: EXIF/XMP) segments: Blender writes its render metadata there even with every stamp off."""
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
    for cn in ("Export", "Backdrop"):
        if cn in bpy.data.collections:
            bpy.data.collections[cn].hide_render = True
            bpy.data.collections[cn].hide_viewport = True
    setup_cycles(arg("--render-samples", 128, int))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = arg("--noise", 0.03, float)
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    which = arg("--only", "all")
    for o in [o for o in bpy.data.objects if o.type == "CAMERA" and o.name != "pano"]:
        bpy.data.objects.remove(o)
    a = BUS["arrive"]
    face = BUS["face"]
    d108 = DOORS["e108"]
    shots = {
        "1_arrival": (look_cam("arrival", (a[0], 1.6, a[2]), (a[0] + face[0] * 10, 1.6, a[2] + face[1] * 10), 75.0), False, 0.0, (1920, 1080)),
        "2_wide": (look_cam("wide", (-17.0, 26.0, 26.0), (2.0, 0.0, -62.0), 62.0), False, 0.0, (1920, 1080)),
        "3_detail": (look_cam("detail", (d108["x"] - 4.2, 1.7, d108["z"] + 3.6), (d108["x"], 1.9, d108["z"] - 0.6), 55.0), False, 0.0, (1920, 1080)),
        "4_day": (look_cam("day", (-2.2, 1.6, -78.0), (0.4, 4.0, -150.0), 70.0), False, 0.0, (1920, 1080)),
        "5_night": (look_cam("night", (-2.2, 1.6, -78.0), (0.4, 4.0, -150.0), 70.0), True, 2.2, (1920, 1080)),
        "6_plan": (look_cam("plan", (0.0, 120.0, (WORLD["z0"] + WORLD["z1"]) / 2), (0.0, 0.0, (WORLD["z0"] + WORLD["z1"]) / 2 - 0.001), ortho=2 * (WORLD["z1"] - WORLD["z0"]) / 2 + 8), False, 0.0, (1400, 2000)),
    }
    plan_cam = shots["6_plan"][0]
    plan_cam.rotation_euler = (0, 0, 0)
    work = stage_work()
    for key, (cam, night, expo, (w, h)) in shots.items():
        if which not in ("all", key):
            continue
        set_time(night)
        bd = work / f"backdrop_{'night' if night else 'day'}.png"
        setup_world(night, bd if key != "6_plan" else None)
        sc.camera = cam
        sc.view_settings.exposure = expo
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, arg("--scale", 100, int)
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        path = STILLS / f"{key}.jpg" if key != "6_plan" else work / "plan.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 400_000 and q > 40 and key != "6_plan":
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        strip_jpeg_meta(path)
        print("STILL", key, path.stat().st_size, "q", q)
    set_time(False)
    setup_world()


if __name__ == "__main__":
    ST = set(STAGE.split(",")) | ({"art", "bake", "export", "axes", "backdrop", "render"} if STAGE == "all" else set())    # e.g. --stage export,axes
    if "art" in ST:
        build_all()
        save_blend()
    else:
        ART = bpy.data.collections.get("Art")
        STANDIN = bpy.data.collections.get("Standins")
    if "bake" in ST:
        stage_bake()
    if "export" in ST:
        stage_export()
    if "axes" in ST:
        stage_axes()
        save_blend()
    if "backdrop" in ST:
        stage_backdrop()
    if "render" in ST:
        stage_render()
