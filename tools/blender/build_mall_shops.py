"""Dresses and lights four mall scenes you can enter (docs/BLENDER_AREAS.md section 3, step 2): `bookstore`, `bookstore_desk`, `cinema_lobby`
and `food_court`. Each gets a day set (`lightmap`) and an emergency set (`lightmap_night`), switched as part 1's `entrance` switches them:
`Lamp_Emit` is on by day and off while the mall is locked (20:00 to 06:00), `Emergency_Emit` is on only while it is locked.

    blender -b --factory-startup --python tools/blender/build_mall_shops.py -- --scenes bookstore --stage art
    blender -b --factory-startup blender/scenes/<scene>.blend --python tools/blender/build_mall_shops.py -- --scenes <scene> --stage layout,check,bake,export,axes,render
    python tools/blender/build_mall_shops.py --pack <scene> [--work <dir>]    (no Blender: WebP lightmaps and textures -> world/)
    python tools/blender/build_mall_shops.py --compare                       (no Blender: world/<scene>.json against the greybox model)
    python tools/blender/build_mall_shops.py --gen <dir>                     (no Blender: the generated pictures as PNGs, to look at)

Stages: art (the layout objects from the greybox, the art, the lights; saves blender/scenes/<scene>.blend) -> layout (world/<scene>.json through
tools/blender/export_scene.py: it must equal the greybox model's file) -> check (tools/blender/check_layout.py's rules on the Art collection, plus
the links' points and every Spot_mannequin kept clear) -> bake (merged by material, lightmap UVs on fixed PAGES, Cycles, two bakes per map: the day
set and the emergency set, OIDN) -> export (the art-only GLB to the work folder) -> axes (the marker-cube check) -> render (the three review stills
in docs/renders/<scene>/; the night still and the plan go to the work folder). `all` runs every stage in that order.

The layout is the greybox's (tools/blender/build_mall_greybox.py, imported; no coordinate is copied by hand): every COL_ box, DoorLeaf_, Link_/Arrive_,
Marker_ and Spot_ comes from its model with the same names and numbers. The dressing asked for new solid furniture (the bookstore's reading chairs
and children's corner, the stock room's rack, the cinema's drinks fridge and the cupboard under its balcony stair, the food court's bins); those
colliders were added to the greybox model itself, so the model, the .blend and world/<scene>.json stay one. Art stands on or within 5 cm of a
collider, or is named decor_ (passable), or hangs overhead; the Spot_mannequin places stay clear (the page draws the mannequins).

The look follows `entrance`: the same mall, old, abandoned and mid-refit; its textures are reused (terrazzo, painted shutters, plywood, beige
plaster, concrete, dark wood, linen) and its emergency heads, EXIT signs and dust sheets are drawn the same way. Everything with words on it is
generated here from a 5 x 7 pixel font: book spines carry no real titles, the film posters are made-up films with no people, the food stalls'
names are invented.
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import build_mall_greybox as G  # noqa: E402  the layout model (pure Python)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


ALL = ("bookstore", "bookstore_desk", "cinema_lobby", "food_court")
STAGE = arg("--stage", "all")
SCENES = [s for s in arg("--scenes", ",".join(ALL)).split(",") if s]
SAMPLES = arg("--samples", 1024, int)
NIGHT_SAMPLES = arg("--night-samples", 2048, int)
DEVICE = arg("--device", "auto")
TEX = ROOT / "blender/textures/mall_shops"
MARGIN_PX = 8
SC = None             # the scene being built (set per scene in main())


def work(sc=None):
    base = Path(arg("--work", str(ROOT / "work/mall_shops")))
    p = base / (sc or SC)
    p.mkdir(parents=True, exist_ok=True)
    return p


def blend_path(sc):
    return ROOT / f"blender/scenes/{sc}.blend"


def stills_dir(sc):
    return ROOT / f"docs/renders/{sc}"


def lm_url(sc, n):
    return f"world/lightmaps/{sc}_{n}.webp"


# ================================================================ generated pictures (numpy only, own work, fixed seeds)
def blur(a, r, passes=3, wrap=False):
    n = 2 * r + 1
    for ax in (0, 1):
        for _ in range(passes):
            pad = [(0, 0)] * a.ndim
            pad[ax] = (r + 1, r)
            c = np.cumsum(np.pad(a, pad, mode="wrap" if wrap else "edge"), axis=ax)
            Ln = c.shape[ax]
            a = (np.take(c, range(n, Ln), axis=ax) - np.take(c, range(0, Ln - n), axis=ax)) / n
    return a


def rs(a, h, w):
    ys, xs = np.linspace(0, a.shape[0] - 1, h), np.linspace(0, a.shape[1] - 1, w)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, a.shape[0] - 1), np.minimum(x0 + 1, a.shape[1] - 1)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    return a[y0][:, x0] * (1 - fy) * (1 - fx) + a[y0][:, x1] * (1 - fy) * fx + a[y1][:, x0] * fy * (1 - fx) + a[y1][:, x1] * fy * fx


def vnoise(h, w, rng, octaves=5, base=4, wrap=False):
    out, amp, tot = np.zeros((h, w)), 1.0, 0.0
    for k in range(octaves):
        n = base * 2 ** k
        g = rng.random((n + 1, n + 1))
        if wrap:
            g[-1, :] = g[0, :]
            g[:, -1] = g[:, 0]
        out += amp * rs(g, h, w)
        tot += amp
        amp *= 0.5
    return out / tot


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
    "&": ["01100", "10010", "10100", "01000", "10101", "10010", "01101"], ">": ["01000", "00100", "00010", "00001", "00010", "00100", "01000"],
    "<": ["00010", "00100", "01000", "10000", "01000", "00100", "00010"], ":": ["00000", "00100", "00000", "00000", "00000", "00100", "00000"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"], "'": ["00100", "00100", "01000", "00000", "00000", "00000", "00000"],
    "!": ["00100", "00100", "00100", "00100", "00100", "00000", "00100"], ",": ["00000", "00000", "00000", "00000", "00110", "00100", "01000"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"], "#": ["01010", "11111", "01010", "01010", "01010", "11111", "01010"],
    "0": ["01110", "10011", "10101", "10101", "11001", "10001", "01110"], "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00110", "01000", "10000", "11111"], "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["10010", "10010", "10010", "11111", "00010", "00010", "00010"], "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["01110", "10000", "11110", "10001", "10001", "10001", "01110"], "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"], "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
}


def text_mask(text, h, w, fill=0.62, maxw=0.9, painted=False, rng=None, align="center"):
    """A line of capitals in the 5 x 7 pixel font, h x w; strokes rounded by a blur and re-threshold (brush-like and ragged when `painted`)."""
    adv = 6
    units = max(1, len(text) * adv - 1)
    s = max(1, int(min(w * maxw / units, h * fill / 7)))
    m = np.zeros((h, w), np.float32)
    x = (w - units * s) // 2 if align == "center" else int(w * (1 - maxw) / 2)
    y0 = (h - 7 * s) // 2
    for ch in text:
        g = GLYPHS.get(ch, GLYPHS[" "])
        jy = int(rng.integers(-max(1, s // 6), max(1, s // 6) + 1)) if painted and rng is not None else 0
        for r, row in enumerate(g):
            for c, v in enumerate(row):
                if v == "1":
                    m[max(0, y0 + jy + r * s):max(0, y0 + jy + (r + 1) * s), x + c * s:x + (c + 1) * s] = 1
        x += adv * s
    k = max(1, s // 4)
    m = np.clip((blur(m, k, 2) - 0.5) * 4 + 0.5, 0, 1)
    if painted and rng is not None:
        m = np.clip((m - 0.5) * 3 + (vnoise(h, w, rng, 4, 16) - 0.5) * 0.9 + 0.5, 0, 1)
    return m


def lines_mask(lines, h, w, fill=0.66, maxw=0.9, painted=False, rng=None, weights=None):
    """Several lines stacked in h x w (each band its share of h by `weights`)."""
    weights = weights or [1.0] * len(lines)
    tot = sum(weights)
    m = np.zeros((h, w), np.float32)
    y = 0
    for ln, wt in zip(lines, weights):
        bh = int(round(h * wt / tot))
        if ln and bh > 3:
            m[y:y + bh] = np.maximum(m[y:y + bh], text_mask(ln, bh, w, fill, maxw, painted, rng))
        y += bh
    return m


def put(img, mask, colour):
    img[...] = img * (1 - mask[..., None]) + np.array(colour, np.float32) * mask[..., None]


def carpet_shop_pixels():
    """Worn blue-grey commercial carpet tiles, 0.5 m each (2 x 2 in the picture, which repeats every 1 m): loop pile, the tiles laid quarter-turned."""
    S = 512
    rng = np.random.default_rng(11)
    yy, xx = np.mgrid[0:S, 0:S]
    n = vnoise(S, S, rng, 6, 4, wrap=True)
    fine = blur(rng.random((S, S)), 1, 1, wrap=True)
    t = ((xx // 256) + (yy // 256)) % 2
    rib = np.where(t == 0, np.sin(2 * np.pi * xx / S * 96), np.sin(2 * np.pi * yy / S * 96)) * 0.5 + 0.5
    v = (0.86 + 0.26 * n) * (0.93 + 0.07 * rib) * (0.86 + 0.28 * fine)
    img = np.ones((S, S, 3), np.float32) * np.array([0.44, 0.49, 0.57]) * v[..., None]
    seam = ((xx % 256) < 2) | ((yy % 256) < 2)
    img[seam] *= 0.78
    fleck = rng.random((S, S)) > 0.985
    img[fleck] = img[fleck] * 0.5 + np.array([0.55, 0.52, 0.45]) * 0.5
    return np.clip(img, 0, 1)


def carpet_cinema_pixels():
    """A multiplex carpet: deep purple pile scattered with bright confetti (rings, squiggles, diamonds, stars) in teal, gold, magenta and orange.
    It repeats without a seam every 1.6 m (shapes are drawn wrapped round the picture's edges)."""
    S = 1024
    rng = np.random.default_rng(23)
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    n = vnoise(S, S, rng, 6, 4, wrap=True)
    img = np.ones((S, S, 3), np.float32) * np.array([0.38, 0.20, 0.46]) * (0.82 + 0.3 * n)[..., None]
    cols = [(0.12, 0.62, 0.60), (0.90, 0.72, 0.18), (0.78, 0.18, 0.52), (0.92, 0.44, 0.12), (0.40, 0.58, 0.92)]

    def tor(cx, cy):
        dx = np.abs(xx - cx)
        dy = np.abs(yy - cy)
        return np.minimum(dx, S - dx), np.minimum(dy, S - dy)
    for i in range(150):
        cx, cy = rng.random() * S, rng.random() * S
        c = cols[i % len(cols)]
        kind = i % 4
        dx, dy = tor(cx, cy)
        if kind == 0:                                     # ring
            r = rng.uniform(10, 22)
            m = np.abs(np.hypot(dx, dy) - r) < 3.2
        elif kind == 1:                                   # diamond
            r = rng.uniform(7, 14)
            m = (dx + dy) < r
        elif kind == 2:                                   # star (a plus and a cross)
            r = rng.uniform(8, 16)
            m = ((dx < 2.5) & (dy < r)) | ((dy < 2.5) & (dx < r)) | ((np.abs(dx - dy) < 2.0) & (dx < r * 0.6))
        else:                                             # squiggle: discs stamped along a short sine
            m = np.zeros((S, S), bool)
            ang = rng.uniform(0, np.pi)
            for t in np.linspace(-1, 1, 14):
                px = cx + np.cos(ang) * t * 34 - np.sin(ang) * np.sin(t * 5) * 7
                py = cy + np.sin(ang) * t * 34 + np.cos(ang) * np.sin(t * 5) * 7
                ddx, ddy = tor(px % S, py % S)
                m |= (ddx * ddx + ddy * ddy) < 9.0
        img[m] = np.array(c) * (0.85 + 0.2 * n[m])[..., None]
    fine = blur(rng.random((S, S)).astype(np.float32), 1, 1, wrap=True)
    img *= (0.88 + 0.24 * fine)[..., None]
    return np.clip(img, 0, 1)


def wall_tile_pixels():
    """Cream glazed wall tiles, 15 cm, 8 x 8 to the picture (it repeats every 1.2 m), grey grout, a little grime toward the bottom of each."""
    S = 512
    rng = np.random.default_rng(31)
    yy, xx = np.mgrid[0:S, 0:S]
    t = S // 8
    tid = (yy // t) * 8 + (xx // t)
    tint = rng.uniform(0.94, 1.04, 64)[tid]
    n = vnoise(S, S, rng, 5, 8, wrap=True)
    img = np.ones((S, S, 3), np.float32) * np.array([0.86, 0.84, 0.77]) * (tint * (0.94 + 0.08 * n))[..., None]
    g = ((xx % t) < 3) | ((yy % t) < 3)
    img[g] = np.array([0.52, 0.50, 0.46]) * (0.9 + 0.2 * n[g])[..., None]
    return np.clip(img, 0, 1)


# ---- book spines: one atlas, 8 rows of 128 px (0.32 m at 400 px/m), each a run of spines; the build takes its books from this list
SPINE_PX_M = 400.0
SPINE_ROW = 128
BOOK_COLS = [(0.42, 0.09, 0.08), (0.11, 0.22, 0.14), (0.10, 0.15, 0.32), (0.62, 0.52, 0.36), (0.08, 0.08, 0.08), (0.58, 0.40, 0.11),
             (0.80, 0.76, 0.64), (0.30, 0.10, 0.21), (0.18, 0.32, 0.38), (0.55, 0.20, 0.12), (0.70, 0.62, 0.30), (0.35, 0.34, 0.30),
             (0.86, 0.84, 0.80), (0.20, 0.12, 0.08), (0.45, 0.48, 0.20), (0.62, 0.30, 0.38)]
PAGES_RECT = (984, 7 * 128, 1024, 8 * 128)        # x0, y0, x1, y1 (image px): the page-block swatch, for the books' tops


def spines_pixels():
    """Returns (picture, spines): each spine (row, x0, x1, height m) is one book. A faded cloth or paper colour, gilt or black bands, and its
    'title' as a column of short dashes that read as lettering from a distance but spell nothing."""
    W = 1024
    rng = np.random.default_rng(5)
    img = np.ones((W, W, 3), np.float32) * 0.06
    spines = []
    for r in range(8):
        x = 0
        xmax = PAGES_RECT[0] - 4 if r == 7 else W
        while x < xmax - 28:
            w = int(rng.integers(9, 27))
            h_m = float(rng.uniform(0.19, 0.31))
            hp = int(h_m * SPINE_PX_M)
            yb = (r + 1) * SPINE_ROW
            y0 = yb - hp
            c = np.array(BOOK_COLS[int(rng.integers(len(BOOK_COLS)))]) * rng.uniform(0.75, 1.15)
            col = np.ones((hp, w, 3), np.float32) * c
            ink = np.array((0.85, 0.72, 0.35)) if rng.random() < 0.5 else (np.array((0.05, 0.05, 0.05)) if c.mean() > 0.4 else np.array((0.88, 0.86, 0.80)))
            for fr in sorted(rng.uniform(0.04, 0.96, int(rng.integers(1, 4)))):
                yy = int(hp * (1 - fr))
                col[max(0, yy - 2):yy + 2] = ink * 0.9 + c * 0.1
            if rng.random() < 0.85:                       # the illegible 'title': dashes down the middle third
                yy = int(hp * rng.uniform(0.18, 0.3))
                ye = int(hp * rng.uniform(0.55, 0.72))
                xm = w // 2
                while yy < ye:
                    L = int(rng.integers(2, 6))
                    col[yy:yy + L, max(1, xm - max(1, w // 5)):xm + max(1, w // 5)] = ink
                    yy += L + int(rng.integers(1, 3))
            if rng.random() < 0.6:                        # the publisher's mark near the foot
                yy = int(hp * 0.88)
                col[yy:yy + 4, w // 2 - 2:w // 2 + 2] = ink
            nz = vnoise(hp, w, rng, 3, 2)
            col *= (0.82 + 0.3 * nz)[..., None] * np.linspace(1.08, 0.92, hp)[:, None, None]   # sun-faded toward the top
            col[:, :1] *= 0.6
            col[:, -1:] *= 0.55
            img[y0:yb, x:x + w] = col
            spines.append((r, x, x + w, h_m))
            x += w
    x0, y0, x1, y1 = PAGES_RECT
    pg = np.ones((y1 - y0, x1 - x0, 3), np.float32) * np.array((0.80, 0.76, 0.66))
    pg[::3] *= 0.9
    img[y0:y1, x0:x1] = pg
    return np.clip(img, 0, 1), spines


def palette_pixels(pal):
    S = 512
    keys = list(pal)
    img = np.zeros((S, S, 3), np.float32)
    for i, k in enumerate(keys):
        r, c = divmod(i, 8)
        img[r * 64:(r + 1) * 64, c * 64:(c + 1) * 64] = pal[k]
    return img


def exit_pixels():
    h, w = 96, 256
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (0.02, 0.45, 0.16)
    m = text_mask("EXIT", h, w, fill=0.66, maxw=0.8)
    put(img, m, (0.95, 1.0, 0.95))
    img[:4] = img[-4:] = img[:, :4] = img[:, -4:] = (0.01, 0.2, 0.07)
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def whitewash_pixels():
    """Glass whitewashed from the inside for the refit (entrance's), streaky brush arcs."""
    S = 512
    rng = np.random.default_rng(29)
    yy, xx = np.mgrid[0:S, 0:S] / S
    streak = 0.5 + 0.5 * np.sin((xx * 3.0 + yy * 1.4 + 0.15 * np.sin(yy * 17)) * 2 * math.pi * 6)
    n = vnoise(S, S, rng, 6, 6)
    cover = np.clip(0.72 + 0.22 * streak * n + (n - 0.5) * 0.4, 0, 1)
    img = np.array([0.55, 0.60, 0.60]) * (1 - cover[..., None]) + np.array([0.90, 0.89, 0.84]) * cover[..., None]
    return np.clip(img, 0, 1).astype(np.float32)


def paper_pixels():
    """Brown paper taped over a shop window from the inside: sheets with creases and strips of tape."""
    S = 512
    rng = np.random.default_rng(41)
    yy, xx = np.mgrid[0:S, 0:S]
    n = vnoise(S, S, rng, 6, 4)
    img = np.ones((S, S, 3), np.float32) * np.array((0.56, 0.42, 0.27)) * (0.86 + 0.26 * n)[..., None]
    for k in range(9):
        ang = rng.uniform(0, np.pi)
        d = (xx - rng.uniform(0, S)) * np.cos(ang) + (yy - rng.uniform(0, S)) * np.sin(ang)
        img[np.abs(d) < 1.2] *= 0.86
    seam = (xx % 256 < 3) | (yy % 256 < 3)
    img[seam] *= 0.8
    for cx in (0, 256):
        for cy in (0, 256):
            img[max(0, cy - 10):cy + 10, cx:cx + 90] = img[max(0, cy - 10):cy + 10, cx:cx + 90] * 0.3 + np.array((0.80, 0.76, 0.58)) * 0.7
    return np.clip(img, 0, 1)


def skyglass_pixels():
    """Dirty wired glass (entrance's skylight)."""
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
    """A soft patch of dust and grit (RGBA), dense in the middle and thinning out: dropped under counters, along the shelves, in corners."""
    S = 256
    rng = np.random.default_rng(43)
    yy, xx = np.mgrid[0:S, 0:S] / (S - 1) * 2 - 1
    n = vnoise(S, S, rng, 6, 4)
    r = np.hypot(xx, yy)
    a = np.clip(0.42 * (1 - np.clip(r, 0, 1)) ** 1.5 + (n - 0.5) * 0.35, 0, 0.42)
    rgba = np.zeros((S, S, 4), np.float32)
    rgba[..., :3] = np.array([0.50, 0.46, 0.40]) * (0.85 + 0.3 * n[..., None])
    rgba[..., 3] = a
    return rgba


def sign_paint(sp, rng):
    """One item of a scene's sign atlas (h x w x 3): kinds sign (a board with lines of text), menu (a dark board, a heading and priced lines),
    notice (a cork board with pinned notes), panel (a flat colour, a stripe or a pattern) and label (a printed card)."""
    w, h = sp["w"], sp["h"]
    kind = sp.get("kind", "sign")
    bg, fg = np.array(sp.get("bg", (0.9, 0.9, 0.88))), np.array(sp.get("fg", (0.1, 0.1, 0.1)))
    img = np.ones((h, w, 3), np.float32) * bg
    if kind == "sign":
        m = lines_mask(sp["lines"], h, w, fill=sp.get("fill", 0.66), maxw=sp.get("maxw", 0.86), painted=sp.get("painted", False), rng=rng,
                       weights=sp.get("weights"))
        put(img, m, fg)
    elif kind == "menu":
        head = sp["lines"][0]
        hh = int(h * 0.24)
        put(img[:hh], text_mask(head, hh, w, 0.6, 0.8), sp.get("accent", (0.95, 0.75, 0.2)))
        img[hh:hh + 2, int(w * 0.06):int(w * 0.94)] = sp.get("accent", (0.95, 0.75, 0.2))
        items = sp["lines"][1:]
        rh = (h - hh - 6) // max(1, len(items))
        for i, it in enumerate(items):
            name, _, price = it.rpartition(" ")
            y = hh + 4 + i * rh
            band = img[y:y + rh]
            put(band[:, :int(w * 0.72)], text_mask(name, rh, int(w * 0.72), 0.5, 0.86, align="left"), fg)
            put(band[:, int(w * 0.72):], text_mask(price, rh, w - int(w * 0.72), 0.5, 0.7), sp.get("accent", (0.95, 0.75, 0.2)))
    elif kind == "notice":
        n = vnoise(h, w, rng, 6, 6)
        img = np.ones((h, w, 3), np.float32) * np.array((0.62, 0.45, 0.28)) * (0.8 + 0.35 * n)[..., None]
        speck = rng.random((h, w)) > 0.93
        img[speck] *= 0.75
        b = max(6, w // 40)
        img[:b] = img[-b:] = img[:, :b] = img[:, -b:] = (0.42, 0.30, 0.18)
        hh = int(h * 0.16)
        put(img[b:b + hh], text_mask(sp["lines"][0], hh, w, 0.6, 0.6), (0.92, 0.90, 0.85))
        notes = [(0.95, 0.93, 0.86), (0.98, 0.92, 0.55), (0.70, 0.85, 0.95), (0.95, 0.75, 0.80), (0.85, 0.95, 0.75)]
        for k in range(int(sp.get("notes", 14))):
            nw, nh = int(rng.uniform(0.12, 0.24) * w), int(rng.uniform(0.14, 0.28) * h)
            x0, y0 = int(rng.uniform(b, w - b - nw)), int(rng.uniform(b + hh, h - b - nh))
            c = np.array(notes[k % len(notes)]) * rng.uniform(0.85, 1.0)
            img[y0 + 3:y0 + nh + 3, x0 + 3:x0 + nw + 3] *= 0.7
            img[y0:y0 + nh, x0:x0 + nw] = c
            for yy in range(y0 + nh // 6, y0 + nh - 4, max(4, nh // 8)):         # handwriting: wobbly grey lines, nothing legible
                L = int(nw * rng.uniform(0.45, 0.85))
                img[yy:yy + 2, x0 + 4:x0 + 4 + L] = (0.25, 0.25, 0.35)
            px, py = x0 + nw // 2, y0 + 4
            img[py - 3:py + 3, px - 3:px + 3] = (0.8, 0.1, 0.1) if k % 2 else (0.1, 0.3, 0.8)
    elif kind == "panel":
        n = vnoise(h, w, rng, 4, 4)
        img *= (0.88 + 0.2 * n)[..., None]
        pat = sp.get("pattern")
        if pat == "stripes":
            yy, xx = np.mgrid[0:h, 0:w]
            s = ((xx + yy) // max(4, h // 6)) % 2 == 0
            img[s] = img[s] * 0.6 + np.array(fg) * 0.4
        elif pat == "stars":
            yy, xx = np.mgrid[0:h, 0:w]
            for k in range(int(w * h / 1800)):
                cx, cy, r = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(3, 7)
                m = (np.abs(xx - cx) + np.abs(yy - cy)) < r
                img[m] = fg
        elif pat == "band":
            img[int(h * 0.42):int(h * 0.58)] = fg
    elif kind == "label":
        m = lines_mask(sp["lines"], h, w, fill=0.5, maxw=0.8)
        put(img, m, fg)
        img[:2] = img[-2:] = img[:, :2] = img[:, -2:] = fg
    if sp.get("border") is not None:
        bw = max(2, min(w, h) // 14)
        img[:bw] = img[-bw:] = img[:, :bw] = img[:, -bw:] = sp["border"]
    if sp.get("aged", True):
        n = vnoise(h, w, rng, 4, 3)
        img *= (0.86 + 0.22 * n)[..., None]
    return np.clip(img, 0, 1)


def sign_atlas(items, W=1024, seed=7):
    """Shelf-pack every item into one picture W wide (2048 when 1024 would need more than 1024 rows). Returns (picture, {key: (u0, v0, u1, v1)})."""
    rng = np.random.default_rng(seed)
    order = sorted(items.items(), key=lambda kv: (-kv[1]["h"], -kv[1]["w"]))

    def shelf(W):
        x = y = rowh = 0
        place = {}
        for key, sp in order:
            assert sp["w"] <= W, key
            if x + sp["w"] > W:
                x, y, rowh = 0, y + rowh, 0
            place[key] = (x, y)
            x += sp["w"]
            rowh = max(rowh, sp["h"])
        return place, y + rowh
    place, used = shelf(W)
    if used > W:
        W = 2048
        place, used = shelf(W)
    Ht = 256
    while Ht < used:
        Ht *= 2
    img = np.ones((Ht, W, 3), np.float32) * 0.5
    uv = {}
    for key, sp in order:
        px, py = place[key]
        img[py:py + sp["h"], px:px + sp["w"]] = sign_paint(sp, rng)
        uv[key] = ((px + 0.5) / W, 1 - (py + sp["h"] - 0.5) / Ht, (px + sp["w"] - 0.5) / W, 1 - (py + 0.5) / Ht)
    return img, uv


# ---- made-up film posters (cinema): no real films, no people; abstract shapes, a title, illegible credits
POSTERS = [("MOTH", "SEASON", "moth", (0.30, 0.16, 0.36), (0.92, 0.58, 0.30)), ("COMET", "MOTEL", "motel", (0.05, 0.10, 0.26), (0.98, 0.80, 0.30)),
           ("LOW TIDE", "AT FARWAY", "sea", (0.10, 0.40, 0.45), (0.98, 0.62, 0.36)), ("THE ORCHARD", "ENGINE", "orchard", (0.12, 0.26, 0.12), (0.92, 0.80, 0.40)),
           ("NINE MILES", "OF FOG", "fog", (0.46, 0.48, 0.50), (0.95, 0.95, 0.92)), ("THE PALE", "ESCALATOR", "steps", (0.70, 0.45, 0.55), (0.20, 0.10, 0.22)),
           ("SILVER", "STATIC", "static", (0.62, 0.64, 0.68), (0.10, 0.10, 0.14)), ("DOOR", "NUMBER FOUR", "door", (0.50, 0.08, 0.08), (0.98, 0.90, 0.70))]


def poster_pixels(top, bottom, motif, c1, c2, rng):
    w, h = 256, 384
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = yy / h
    img = (np.array(c1) * (1 - t[..., None]) + np.array(c1) * 0.45 * t[..., None]).astype(np.float32)
    cx, cy = w / 2, h * 0.5
    if motif == "moth":
        for sg in (-1, 1):
            m = ((xx - cx - sg * 46) / 52) ** 2 + ((yy - cy + 10) / 70) ** 2 < 1
            img[m] = np.array(c2) * 0.9
            m2 = ((xx - cx - sg * 46) / 22) ** 2 + ((yy - cy + 4) / 22) ** 2 < 1
            img[m2] = np.array(c1) * 0.6
        img[(np.abs(xx - cx) < 6) & (np.abs(yy - cy) < 64)] = np.array(c1) * 0.3
        img[((xx - cx) ** 2 + (yy - h * 0.22) ** 2) < 26 ** 2] = (0.95, 0.93, 0.80)
    elif motif == "motel":
        img[int(h * 0.48):int(h * 0.72), 40:216] = np.array(c1) * 2.2
        for wx in range(54, 206, 26):
            img[int(h * 0.55):int(h * 0.62), wx:wx + 14] = c2
        img[int(h * 0.30):int(h * 0.46), 150:158] = np.array(c2) * 0.8
        img[int(h * 0.26):int(h * 0.34), 120:190] = c2
        for k in range(40):
            px, py = 20 + k * 3.5, 40 + k * 1.6
            img[((xx - px) ** 2 + (yy - py) ** 2) < max(1, 9 - k * 0.2) ** 2] = (0.98, 0.95, 0.85)
    elif motif == "sea":
        img[yy > h * 0.52] = np.array(c1) * 0.6
        for k in range(10):
            yl = h * 0.55 + k * 13
            img[np.abs(yy - yl - 3 * np.sin(xx / 12 + k)) < 1.4] = np.array(c2) * 0.7
        img[((xx - cx) ** 2 + (yy - h * 0.5) ** 2 < 44 ** 2) & (yy < h * 0.52)] = c2
    elif motif == "orchard":
        img[yy > h * 0.6] = np.array(c1) * 0.55
        for row in range(3):
            for k in range(6):
                tx, ty = 26 + k * 42 + row * 12, h * 0.42 + row * 34
                img[(np.abs(xx - tx) < 2) & (yy > ty) & (yy < ty + 30)] = (0.25, 0.15, 0.08)
                img[((xx - tx) ** 2 + (yy - ty) ** 2) < (16 - row * 3) ** 2] = np.array(c2) * (0.7 + row * 0.1)
    elif motif == "fog":
        for k in range(6):
            yl = h * 0.35 + k * 30
            band = np.exp(-((yy - yl - 6 * np.sin(xx / 30 + k)) / 9) ** 2)
            img += band[..., None] * 0.22 * np.array(c2)
    elif motif == "steps":
        for k in range(9):
            x0, y0 = 30 + k * 22, h * 0.80 - k * 22
            img[int(y0):int(y0 + 22), int(x0):] = np.array(c2) * (0.4 + 0.05 * k)
        img[(np.abs((xx - 30) - (h * 0.80 - yy) * 1.0) < 3) & (yy > h * 0.2) & (yy < h * 0.82)] = (0.95, 0.92, 0.90)
    elif motif == "static":
        sx, sy = slice(48, 208), slice(int(h * 0.3), int(h * 0.62))
        img[sy, sx] = rng.random((sy.stop - sy.start, 160, 1)) * 0.9 + 0.05
        img[int(h * 0.28):int(h * 0.3), 44:212] = c2
        img[int(h * 0.62):int(h * 0.64), 44:212] = c2
    elif motif == "door":
        img[int(h * 0.30):int(h * 0.78), 84:172] = np.array(c1) * 0.4
        img[int(h * 0.33):int(h * 0.76), 92:164] = np.array(c2)
        img[int(h * 0.55):int(h * 0.57), 150:158] = np.array(c1) * 0.3
        tri = (yy > h * 0.78) & (np.abs(xx - cx) < (yy - h * 0.78) * 1.6 + 40)
        img[tri] = img[tri] * 0.4 + np.array(c2) * 0.6 * 0.5
    put(img[8:78], lines_mask([top, bottom], 70, w, 0.72, 0.9), c2 if motif not in ("steps", "static") else (0.12, 0.08, 0.12))
    for k in range(4):                                         # the credits block: tiny bars that read as small print
        y0 = h - 44 + k * 8
        for x0 in range(24, 232, 26):
            L = int(rng.integers(8, 22))
            img[y0:y0 + 3, x0:x0 + L] = img[y0:y0 + 3, x0:x0 + L] * 0.3 + 0.55
    n = vnoise(h, w, rng, 4, 3)
    img *= (0.85 + 0.25 * n)[..., None]
    img[:4] = img[-4:] = img[:, :4] = img[:, -4:] = 0.05
    return np.clip(img, 0, 1)


def posters_pixels():
    rng = np.random.default_rng(13)
    img = np.zeros((768, 1024, 3), np.float32)
    for i, (a, b, motif, c1, c2) in enumerate(POSTERS):
        r, c = divmod(i, 4)
        img[r * 384:(r + 1) * 384, c * 256:(c + 1) * 256] = poster_pixels(a, b, motif, c1, c2, rng)
    return img


def poster_uv(i):
    r, c = divmod(i, 4)
    return (c * 256 + 0.5) / 1024, 1 - ((r + 1) * 384 - 0.5) / 768, ((c + 1) * 256 - 0.5) / 1024, 1 - (r * 384 + 0.5) / 768


# ---- the door leaves: one atlas, four columns of 256 x 1024 (a leaf's face, hinge side left): wood (INFORMATION), wood (STOCK ROOM),
# whitewashed glass in a steel frame, a steel staff door; the right-most 16 px of each column is the edge colour
DOOR_COLS = {"wood_info": 0, "wood_stock": 1, "glass": 2, "steel": 3}


def doors_pixels():
    W, H = 1024, 1024
    rng = np.random.default_rng(17)
    img = np.zeros((H, W, 3), np.float32)
    for kind, c in DOOR_COLS.items():
        x0 = c * 256
        col = np.zeros((H, 256, 3), np.float32)
        n = vnoise(H, 256, rng, 5, 3)
        if kind.startswith("wood"):
            grain = 0.5 + 0.5 * np.sin(np.mgrid[0:H, 0:256][1] / 3.0 + vnoise(H, 256, rng, 3, 2) * 10)
            col[:] = np.array((0.48, 0.32, 0.18)) * (0.82 + 0.14 * grain + 0.12 * n)[..., None]
            for b0, b1 in ((0.05, 0.45), (0.52, 0.94)):              # two fielded panels: their edges shaded and lit
                ya, yb, xa, xb = int(H * (1 - b1)), int(H * (1 - b0)), 24, 216
                col[ya:ya + 4, xa:xb] *= 0.7
                col[yb - 4:yb, xa:xb] *= 1.15
                col[ya:yb, xa:xa + 4] *= 0.75
                col[ya:yb, xb - 4:xb] *= 1.1
            label = "INFORMATION" if kind == "wood_info" else "STOCK ROOM"
            pl = np.ones((60, 200, 3), np.float32) * (0.86, 0.80, 0.55)
            put(pl, text_mask(label, 60, 200, 0.5, 0.86), (0.12, 0.10, 0.08))
            col[int(H * 0.36):int(H * 0.36) + 60, 20:220] = pl
            col[int(H * 0.52):int(H * 0.52) + 16, 200:228] = (0.70, 0.56, 0.25)          # the handle's plate (painted; the knob is geometry)
        elif kind == "glass":
            col[:] = np.array((0.55, 0.56, 0.58)) * (0.9 + 0.15 * n)[..., None]
            ww = whitewash_pixels()
            for k in range(3):
                col[120:H - 80, 28:224, k] = rs(ww[..., k], H - 200, 196)
            col[int(H * 0.52):int(H * 0.55), 30:222] = (0.70, 0.72, 0.74)                    # the push bar's back plate
            pl = np.ones((44, 180, 3), np.float32) * (0.95, 0.95, 0.92)
            put(pl, text_mask("PUSH", 44, 180, 0.5, 0.5), (0.2, 0.2, 0.2))
            col[int(H * 0.44):int(H * 0.44) + 44, 38:218] = pl
        else:
            col[:] = np.array((0.42, 0.45, 0.46)) * (0.86 + 0.2 * n)[..., None]
            col[H - 140:H - 40] = np.array((0.68, 0.68, 0.66)) * (0.9 + 0.1 * n[H - 140:H - 40])[..., None]   # the kick plate
            pl = np.ones((70, 200, 3), np.float32) * (0.90, 0.12, 0.10)
            put(pl, lines_mask(["STAFF", "ONLY"], 70, 200, 0.7, 0.6), (0.98, 0.98, 0.95))
            col[int(H * 0.30):int(H * 0.30) + 70, 28:228] = pl
        col[:, 240:] = col[:, 120:121] * 0.8
        img[:, x0:x0 + 256] = col
    return np.clip(img, 0, 1)


def door_uv(kind):
    c = DOOR_COLS[kind]
    return (c * 256 + 1) / 1024, 0.002, (c * 256 + 238) / 1024, 0.998


def door_edge_uv(kind):
    c = DOOR_COLS[kind]
    return ((c * 256 + 248) / 1024, 0.5)


# ================================================================ the scenes' words: signs, menus, notices (one atlas per scene)
CATEGORIES = ["FICTION", "MYSTERY", "HISTORY", "TRAVEL", "COOKERY", "POETRY", "SCIENCE", "ART & DESIGN"]
STALLS = [("LANTERN NOODLES", "NOODLES & RICE", (0.70, 0.12, 0.10), ["NOODLE BOX 5.20", "RICE BOWL 4.80", "SPRING ROLLS 2.60", "GREEN TEA 1.40"]),
          ("ORBIT PIZZA", "BY THE SLICE", (0.12, 0.40, 0.18), ["CHEESE SLICE 2.90", "PEPPER SLICE 3.20", "GARLIC KNOTS 2.10", "COLA 1.50"]),
          ("HARBOUR BURGERS", "GRILL", (0.10, 0.20, 0.44), ["HARBOUR BURGER 5.90", "DOUBLE 7.40", "FRIES 2.20", "SHAKE 3.10"]),
          ("COMET TACOS", "FRESH DAILY", (0.86, 0.46, 0.10), ["THREE TACOS 5.50", "BURRITO 6.20", "NACHOS 3.80", "LIME SODA 1.60"]),
          ("KNOTS", "SOFT PRETZELS", (0.52, 0.30, 0.12), ["SALT KNOT 2.40", "CINNAMON 2.70", "DIP 0.80", "LEMONADE 1.90"]),
          ("BLUE KIWI", "JUICE & SMOOTHIES", (0.12, 0.50, 0.55), ["BERRY BLEND 3.60", "MANGO 3.60", "GREEN 3.90", "ORANGE 2.80"]),
          ("HENHOUSE", "ROAST CHICKEN", (0.80, 0.60, 0.12), ["QUARTER 4.90", "HALF 7.80", "WINGS 4.10", "SLAW 1.80"]),
          ("TIDE SUSHI", "ROLLS & BOXES", (0.92, 0.88, 0.80), ["SALMON ROLL 5.40", "VEG BOX 4.60", "MISO 1.90", "EDAMAME 2.30"]),
          ("GYRO GARDEN", "WRAPS & PLATES", (0.40, 0.48, 0.14), ["GYRO WRAP 5.70", "PLATE 7.90", "PITTA 1.20", "AYRAN 1.70"]),
          ("POLAR SCOOP", "ICE CREAM", (0.62, 0.78, 0.92), ["ONE SCOOP 2.20", "TWO SCOOPS 3.60", "SUNDAE 4.40", "CONE 0.50"])]
FILMS = ["MOTH SEASON", "COMET MOTEL", "LOW TIDE AT FARWAY", "THE ORCHARD ENGINE"]


def sign_items(sc):
    white, ink, red = (0.93, 0.92, 0.88), (0.10, 0.10, 0.10), (0.62, 0.10, 0.08)
    it = {}
    if sc in ("bookstore", "bookstore_desk"):
        it["info"] = dict(lines=["INFORMATION >"], w=512, h=96, bg=(0.10, 0.22, 0.30), fg=white, border=(0.82, 0.70, 0.35))
    if sc == "bookstore":
        for k, c in enumerate(CATEGORIES):
            it[f"cat{k}"] = dict(lines=[c], w=384, h=80, bg=(0.12, 0.26, 0.20), fg=(0.95, 0.88, 0.62), border=(0.70, 0.58, 0.30))
        for k, c in enumerate(["NEW IN", "PAPERBACKS", "CLASSICS", "BIOGRAPHY", "REFERENCE", "LOCAL INTEREST"]):
            it[f"wall{k}"] = dict(lines=[c], w=512, h=72, bg=(0.86, 0.82, 0.70), fg=(0.20, 0.14, 0.10))
        it["kids"] = dict(lines=["CHILDREN'S BOOKS", "STORY CORNER"], w=640, h=160, bg=(0.95, 0.80, 0.20), fg=(0.20, 0.28, 0.62),
                          border=(0.85, 0.25, 0.20), weights=[1.3, 1.0])
        it["sale"] = dict(lines=["SALE", "ALL STOCK MUST GO"], w=320, h=192, bg=(0.96, 0.94, 0.88), fg=red, border=red, weights=[1.6, 1.0])
        it["closing"] = dict(lines=["CLOSING DOWN"], w=512, h=96, bg=(0.95, 0.85, 0.20), fg=red, painted=True)
    if sc == "bookstore_desk":
        it["orders"] = dict(lines=["ORDERS & COLLECTIONS"], w=640, h=80, bg=(0.10, 0.22, 0.30), fg=white)
        it["wait"] = dict(lines=["PLEASE WAIT", "HERE"], w=256, h=128, bg=white, fg=(0.10, 0.22, 0.30), border=(0.10, 0.22, 0.30))
        it["notice"] = dict(kind="notice", lines=["STAFF NOTICES"], w=512, h=352, notes=16)
        it["rota"] = dict(kind="label", lines=["ROTA", "WEEK 46"], w=192, h=256, bg=(0.97, 0.97, 0.95), fg=(0.15, 0.15, 0.18))
        it["slip"] = dict(kind="label", lines=["ORDER", "NO."], w=96, h=128, bg=(0.98, 0.94, 0.70), fg=(0.45, 0.20, 0.10))
        it["screen"] = dict(kind="panel", w=128, h=96, bg=(0.06, 0.10, 0.08), aged=True)
        it["keys"] = dict(kind="panel", w=128, h=48, bg=(0.78, 0.76, 0.70), fg=(0.45, 0.44, 0.40), pattern="stripes")
    if sc == "cinema_lobby":
        for k in range(1, 5):
            it[f"screen{k}"] = dict(lines=[f"SCREEN {k}"], w=320, h=96, bg=(0.06, 0.06, 0.08), fg=(0.98, 0.82, 0.35), border=(0.45, 0.36, 0.18))
        it["proj"] = dict(lines=["PROJECTION", "STAFF ONLY"], w=320, h=128, bg=(0.06, 0.06, 0.08), fg=(0.95, 0.30, 0.25), border=(0.45, 0.36, 0.18))
        it["staff"] = dict(lines=["STAFF"], w=192, h=64, bg=(0.06, 0.06, 0.08), fg=(0.95, 0.90, 0.80))
        it["boxoffice"] = dict(lines=["BOX OFFICE"], w=640, h=96, bg=(0.50, 0.06, 0.08), fg=(0.98, 0.84, 0.40), border=(0.70, 0.55, 0.25))
        it["closed"] = dict(kind="label", lines=["CLOSED"], w=192, h=96, bg=(0.97, 0.96, 0.92), fg=(0.60, 0.08, 0.08))
        it["concess"] = dict(lines=["CONCESSIONS"], w=1024, h=96, bg=(0.06, 0.06, 0.08), fg=(0.98, 0.82, 0.35))
        it["nowshow"] = dict(lines=["NOW SHOWING:  " + "  -  ".join(FILMS[:3])], w=1024, h=64, bg=(0.92, 0.90, 0.84), fg=(0.10, 0.10, 0.12),
                             maxw=0.96, fill=0.6)
        it["menu_pop"] = dict(kind="menu", lines=["POPCORN", "SMALL 3.50", "MEDIUM 4.90", "LARGE 5.90", "SHARE TUB 7.50"], w=384, h=256,
                              bg=(0.06, 0.06, 0.10), fg=(0.94, 0.94, 0.90), accent=(0.98, 0.78, 0.25))
        it["menu_drink"] = dict(kind="menu", lines=["DRINKS", "FIZZ SMALL 2.40", "FIZZ LARGE 3.40", "STILL WATER 1.90", "SLUSH 3.20"], w=384, h=256,
                                bg=(0.06, 0.06, 0.10), fg=(0.94, 0.94, 0.90), accent=(0.35, 0.80, 0.95))
        it["menu_snack"] = dict(kind="menu", lines=["SNACKS", "NACHOS 4.20", "HOT DOG 3.90", "PICK & MIX 2.80", "COMBO DEAL 9.90"], w=384, h=256,
                                bg=(0.06, 0.06, 0.10), fg=(0.94, 0.94, 0.90), accent=(0.95, 0.40, 0.55))
        it["popcorn"] = dict(lines=["POPCORN"], w=320, h=80, bg=(0.80, 0.08, 0.08), fg=(0.99, 0.88, 0.30))
        it["cold"] = dict(lines=["COLD DRINKS"], w=384, h=80, bg=(0.10, 0.30, 0.62), fg=white)
        it["counter"] = dict(kind="panel", w=512, h=96, bg=(0.36, 0.06, 0.10), fg=(0.95, 0.74, 0.28), pattern="stars")
        it["fizz"] = dict(kind="panel", w=128, h=128, bg=(0.10, 0.28, 0.60), fg=(0.95, 0.30, 0.25), pattern="band")
    if sc == "food_court":
        for k, (name, sub, c, menu) in enumerate(STALLS):
            fg = (0.98, 0.97, 0.92) if sum(c) < 1.8 else (0.12, 0.16, 0.30)
            it[f"stall{k}"] = dict(lines=[name, sub], w=512, h=112, bg=c, fg=fg, weights=[1.5, 0.9], border=tuple(v * 0.6 for v in c))
            it[f"menu{k}"] = dict(kind="menu", lines=["MENU"] + menu, w=320, h=176, bg=(0.08, 0.08, 0.10), fg=(0.92, 0.92, 0.88), accent=c if sum(c) > 0.6 else (0.9, 0.8, 0.3))
            it[f"front{k}"] = dict(kind="panel", w=192, h=64, bg=c, fg=tuple(min(1, v * 1.4 + 0.15) for v in c), pattern="band")
        it["thanks"] = dict(lines=["THANK YOU"], w=256, h=64, bg=(0.20, 0.22, 0.24), fg=white)
        it["trays"] = dict(lines=["TRAYS HERE"], w=320, h=64, bg=(0.20, 0.22, 0.24), fg=white)
        it["court"] = dict(lines=["FOOD COURT"], w=640, h=112, bg=(0.10, 0.18, 0.30), fg=(0.98, 0.84, 0.40), border=(0.70, 0.55, 0.25))
        it["wet"] = dict(lines=["CAUTION", "WET FLOOR"], w=192, h=192, bg=(0.96, 0.80, 0.10), fg=(0.10, 0.10, 0.10))
    return it


# ================================================================ pack and compare (plain Python, no Blender)
def pack(sc):
    from PIL import Image
    import subprocess
    w = work(sc)
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
    dst = ROOT / f"world/{sc}.glb"
    subprocess.run([sys.executable, str(ROOT / "tools/webp_glb.py"), str(raw), str(dst), "90"], check=True)
    print(f"{dst.relative_to(ROOT)}  {dst.stat().st_size / 1e6:.2f} MB")


def compare(ids):
    """world/<scene>.json (what export_scene.py wrote from the .blend) against the greybox model's own file (build_mall_greybox.doc_of)."""
    bad = 0
    for sid in ids:
        a = json.loads((ROOT / f"world/{sid}.json").read_text())
        b = G.doc_of(G.build(sid))
        same = a == b
        bad += not same
        print(f"COMPARE {sid}: {'SAME as the greybox model' if same else 'DIFFERENT'} ({len(a['colliders'])} colliders, {len(a['doors'])} doors, "
              f"{len(a['links'])} links, {len(a['spots'])} spots, {len(a['markers'])} markers)")
        if not same:
            for k in a:
                if a[k] != b.get(k):
                    print("   differs:", k)
    return bad


def write_gen(d):
    from PIL import Image
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    pics = {"carpet_shop": carpet_shop_pixels(), "carpet_cinema": carpet_cinema_pixels(), "wall_tile": wall_tile_pixels(), "spines": spines_pixels()[0],
            "posters": posters_pixels(), "doors": doors_pixels(), "paper": paper_pixels(), "exit": exit_pixels()}
    for sc in ALL:
        pics[f"signs_{sc}"] = sign_atlas(sign_items(sc))[0]
    for k, a in pics.items():
        Image.fromarray((np.clip(a[..., :3], 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)).save(d / f"{k}.png")
        print("wrote", d / f"{k}.png", a.shape)


try:
    import bpy
    import bmesh
    from mathutils import Matrix, Vector
except ImportError:
    bpy = None

if bpy is None:
    if "--pack" in args:
        pack(arg("--pack"))
    elif "--compare" in args:
        sys.exit(1 if compare(SCENES) else 0)
    elif "--gen" in args:
        write_gen(arg("--gen"))
    else:
        print(__doc__)
    sys.exit(0)


# ================================================================ Blender from here on
def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


IMG_CACHE, MATS, TILES, GEN = {}, {}, {}, {}
LAMP_EMIT = 8.0          # Lamp_Emit's exported strength: on by day, off while the mall is locked (as entrance)
EMERG_EMIT = 6.0         # Emergency_Emit's exported strength: on only while the mall is locked (as entrance)
EXIT_EMIT = 3.0          # Sign_Exit: always on, in both sets' light


def image(fn, srgb=True):
    key = (fn, srgb)
    if key not in IMG_CACHE:
        im = bpy.data.images.load(str(TEX / fn))
        im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
        IMG_CACHE[key] = im
    return IMG_CACHE[key]


def mk_image(name, arr, srgb=True):
    """A packed image from a float array (rows top to bottom), written as a PNG first (a generated image forgets its pixels when the file is saved)."""
    h, w = arr.shape[:2]
    has_a = arr.shape[2] == 4
    im = bpy.data.images.new(name + "_gen", w, h, alpha=has_a)
    im.alpha_mode = "STRAIGHT"
    im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :arr.shape[2]] = arr
    im.pixels.foreach_set(np.flipud(rgba).ravel())
    gen = work() / "gen"
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


SPINES = []
SIGN_UV = {}
PAL = {
    "white": (0.85, 0.84, 0.80), "cream": (0.86, 0.82, 0.70), "paper": (0.90, 0.88, 0.82), "kraft": (0.56, 0.42, 0.26), "card": (0.62, 0.50, 0.34),
    "black": (0.04, 0.04, 0.04), "charcoal": (0.12, 0.12, 0.13), "grey": (0.40, 0.40, 0.40), "red": (0.62, 0.08, 0.07), "blue": (0.12, 0.25, 0.62),
    "yellow": (0.90, 0.72, 0.12), "green": (0.14, 0.48, 0.20), "orange": (0.88, 0.40, 0.08), "pink": (0.86, 0.44, 0.56), "teal": (0.10, 0.48, 0.48),
    "purple": (0.36, 0.18, 0.52), "popcorn": (0.98, 0.86, 0.48), "kernel": (0.85, 0.62, 0.20), "cola": (0.25, 0.08, 0.04), "lime": (0.50, 0.75, 0.20),
    "tray": (0.52, 0.24, 0.10), "tray2": (0.72, 0.42, 0.14), "beige": (0.72, 0.66, 0.54), "screen": (0.05, 0.08, 0.07), "chrome": (0.62, 0.63, 0.64),
    "rope": (0.55, 0.06, 0.08), "belt": (0.10, 0.12, 0.30), "rubber": (0.06, 0.06, 0.06), "felt": (0.18, 0.22, 0.30), "rug_a": (0.80, 0.30, 0.20),
    "rug_b": (0.20, 0.45, 0.70), "rug_c": (0.92, 0.80, 0.30), "bean_a": (0.85, 0.30, 0.25), "bean_b": (0.25, 0.55, 0.45), "crayon_b": (0.18, 0.36, 0.80),
    "brass": (0.60, 0.46, 0.20), "glass_dk": (0.08, 0.10, 0.11), "candy_a": (0.88, 0.20, 0.30), "candy_b": (0.30, 0.70, 0.90), "candy_c": (0.95, 0.85, 0.20),
    "bottle_a": (0.70, 0.10, 0.08), "bottle_b": (0.10, 0.45, 0.20), "bottle_c": (0.20, 0.35, 0.75), "bottle_d": (0.95, 0.65, 0.10), "napkin": (0.92, 0.92, 0.90),
    "lamp_shade": (0.82, 0.76, 0.60), "leaf": (0.20, 0.30, 0.14), "steel_dk": (0.22, 0.23, 0.24), "foam": (0.80, 0.78, 0.70), "tape": (0.76, 0.66, 0.42),
    "slip_y": (0.96, 0.90, 0.55), "slip_p": (0.95, 0.72, 0.78), "ink": (0.12, 0.16, 0.40), "seat_a": (0.85, 0.42, 0.12), "seat_b": (0.18, 0.40, 0.62),
    "seat_c": (0.70, 0.12, 0.12), "seat_d": (0.24, 0.50, 0.30),
}
PAL_KEYS = list(PAL)
assert len(PAL_KEYS) <= 64


def pal_uv(key):
    i = PAL_KEYS.index(key)
    return ((i % 8 + 0.5) / 8, 1 - (i // 8 + 0.5) / 8)


def gen(key):
    if key not in GEN:
        global SPINES
        if key == "spines":
            arr, SPINES = spines_pixels()
            GEN[key] = mk_image("Book_Spines", arr)
        elif key == "signs":
            arr, uv = sign_atlas(sign_items(SC))
            SIGN_UV.clear()
            SIGN_UV.update(uv)
            GEN[key] = mk_image(f"Signs_{SC}", arr)
        else:
            fn = {"carpet_shop": carpet_shop_pixels, "carpet_cinema": carpet_cinema_pixels, "wall_tile": wall_tile_pixels, "posters": posters_pixels,
                  "doors": doors_pixels, "paper": paper_pixels, "exit": exit_pixels, "whitewash": whitewash_pixels, "skyglass": skyglass_pixels,
                  "dust": dust_pixels, "palette": lambda: palette_pixels(PAL)}[key]
            GEN[key] = mk_image({"palette": "Palette"}.get(key, key.title().replace("_", "")), fn())
    return GEN[key]


# every material any of the four scenes uses: (kwargs for material()); made when first used
MATDEF = {
    "Carpet_Shop": dict(gen="carpet_shop", rough=1.0, tile=1.0),
    "Carpet_Cinema": dict(gen="carpet_cinema", rough=1.0, tile=1.6),
    "Floor_Terrazzo": dict(diff="terrazzo_tiles_diff_1k.jpg", tint=(0.92, 0.88, 0.84), rough=0.4, tile=2.0),
    "Floor_Border": dict(diff="terrazzo_tiles_diff_1k.jpg", tint=(0.46, 0.42, 0.40), rough=0.4, tile=2.0),
    "Floor_Concrete": dict(diff="concrete_floor_02_diff_1k.jpg", tint=(0.92, 0.90, 0.86), rough=0.9, tile=3.0),
    "Floor_Vinyl": dict(diff="concrete_floor_02_diff_1k.jpg", tint=(0.42, 0.40, 0.38), rough=0.6, tile=2.0),
    "Wall_Paint": dict(diff="beige_wall_001_diff_1k.jpg", tint=(0.92, 0.88, 0.80), rough=0.9, tile=2.4),
    "Wall_Lower": dict(diff="beige_wall_001_diff_1k.jpg", tint=(0.66, 0.60, 0.52), rough=0.9, tile=2.4),
    "Wall_Fabric": dict(diff="rough_linen_diff_512.jpg", tint=(0.82, 0.32, 0.34), rough=1.0, tile=0.9),
    "Wall_Tile": dict(gen="wall_tile", rough=0.25, tile=1.2),
    "Ceiling_Tile": dict(diff="ceiling_tile_diff.jpg", tint=(0.96, 0.95, 0.92), rough=0.95, tile=0.6),
    "Ceiling_Paint": dict(diff="beige_wall_001_diff_1k.jpg", tint=(0.94, 0.93, 0.90), rough=0.95, tile=3.0),
    "Ceiling_Dark": dict(diff="beige_wall_001_diff_1k.jpg", tint=(0.52, 0.48, 0.50), rough=0.95, tile=3.0),
    "Trim_Paint": dict(color=(0.62, 0.60, 0.55), rough=0.55),
    "Trim_Dark": dict(color=(0.16, 0.10, 0.10), rough=0.5),
    "Wood_Shelf": dict(diff="plywood_diff_1k.jpg", tint=(0.80, 0.52, 0.34), rough=0.6, tile=0.9),
    "Shelf_Back": dict(diff="plywood_diff_1k.jpg", tint=(0.58, 0.40, 0.28), rough=0.7, tile=1.2),
    "Wood_Light": dict(diff="plywood_diff_1k.jpg", tint=(0.92, 0.86, 0.76), rough=0.7, tile=1.0),
    "Wood_Desk": dict(diff="dark_wood_diff_1k.jpg", tint=(0.80, 0.66, 0.52), rough=0.5, tile=1.2),
    "Laminate": dict(color=(0.72, 0.70, 0.64), rough=0.4),
    "Shutter_Metal": dict(diff="painted_metal_shutter_diff_1k.jpg", tint=(0.80, 0.80, 0.80), rough=0.5, metal=0.2, tile=2.0),
    "Metal_Steel": dict(color=(0.48, 0.49, 0.50), rough=0.4, metal=0.85),
    "Metal_Dark": dict(color=(0.06, 0.06, 0.065), rough=0.45, metal=0.7),
    "Brass": dict(color=(0.62, 0.47, 0.22), rough=0.35, metal=0.9),
    "Plastic_White": dict(color=(0.70, 0.70, 0.67), rough=0.5),
    "Cloth_Sheet": dict(diff="rough_linen_diff_512.jpg", tint=(0.95, 0.93, 0.88), rough=1.0, tile=0.8),
    "Fabric_Chair": dict(diff="rough_linen_diff_512.jpg", tint=(0.30, 0.42, 0.30), rough=1.0, tile=0.5),
    "Fabric_Padded": dict(diff="rough_linen_diff_512.jpg", tint=(0.50, 0.10, 0.12), rough=0.8, tile=0.4),
    "Paint_Palette": dict(gen="palette", rough=0.6, tile=1.0),
    "Sign_Paint": dict(gen="signs", rough=0.6, tile=1.0),
    "Book_Spines": dict(gen="spines", rough=0.75, tile=1.0),
    "Book_Loose": dict(gen="spines", rough=0.75, tile=1.0),
    "Doors": dict(gen="doors", rough=0.5, tile=1.0),
    "Glass_Paper": dict(gen="paper", rough=0.8, tile=1.0),
    "Glass_Whitewash": dict(gen="whitewash", rough=0.3, tile=3.0),
    "Poster_Print": dict(gen="posters", rough=0.4, tile=1.0),
    "Skylight_Glass": dict(gen="skyglass", rough=0.2, tile=1.5),
    "Decal_Dust": dict(gen="dust", alpha="texture", rough=1.0, tile=1.0),
    "Lens_Dead": dict(color=(0.55, 0.55, 0.53), rough=0.4),
    "Lamp_Emit": dict(color=(1.0, 0.94, 0.84), rough=0.4, emit=((1.0, 0.92, 0.78), LAMP_EMIT)),
    "Emergency_Emit": dict(color=(0.9, 0.95, 1.0), rough=0.3, emit=((0.85, 0.93, 1.0), EMERG_EMIT)),
    "Sign_Exit": dict(gen="exit", rough=0.4, emit_img=EXIT_EMIT),
    "Glass_Clear": dict(color=(0.75, 0.85, 0.85), rough=0.05, alpha=0.18),
}
NO_LIGHTMAP = {"Lamp_Emit", "Emergency_Emit", "Sign_Exit", "Glass_Clear"}
SHELL = {"Carpet_Shop", "Carpet_Cinema", "Floor_Terrazzo", "Floor_Border", "Floor_Concrete", "Floor_Vinyl", "Wall_Paint", "Wall_Lower", "Wall_Fabric",
         "Wall_Tile", "Ceiling_Tile", "Ceiling_Paint", "Ceiling_Dark", "Trim_Paint", "Trim_Dark", "Decal_Dust"}
TWO_SIDED = ("Cloth_Sheet",)


def material(name):
    if name in MATS:
        return MATS[name]
    d = dict(MATDEF[name])
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*d.get("color", (0.5, 0.5, 0.5)), 1)
    bsdf.inputs["Roughness"].default_value = d.get("rough", 0.8)
    bsdf.inputs["Metallic"].default_value = d.get("metal", 0.0)
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    img = gen(d["gen"]) if "gen" in d else (image(d["diff"]) if "diff" in d else None)
    if img is not None:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = img
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        if "emit_img" in d:
            bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
            nt.links.new(n.outputs["Color"], bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = d["emit_img"]
        elif "tint" in d:
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs[0].default_value = 1.0
            nt.links.new(n.outputs["Color"], mix.inputs[6])
            mix.inputs[7].default_value = (*d["tint"], 1)
            nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        else:
            nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
        if d.get("alpha") == "texture":
            nt.links.new(n.outputs["Alpha"], bsdf.inputs["Alpha"])
    if "emit" in d:
        bsdf.inputs["Emission Color"].default_value = (*d["emit"][0], 1)
        bsdf.inputs["Emission Strength"].default_value = d["emit"][1]
    if d.get("alpha") is not None:
        if d["alpha"] != "texture":
            bsdf.inputs["Alpha"].default_value = d["alpha"]
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    m.use_backface_culling = name not in TWO_SIDED
    TILES[name] = d.get("tile", 1.0)
    MATS[name] = m
    return m


# ---------------------------------------------------------------- geometry helpers (world space, identity transforms)
def cube(bm, gmin, gmax):
    a, b = B(gmin), B(gmax)
    c = (a + b) / 2
    s = Vector((abs(a.x - b.x), abs(a.y - b.y), abs(a.z - b.z)))
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((max(s.x, 1e-4), max(s.y, 1e-4), max(s.z, 1e-4), 1.0)))


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


def disc_down(bm, p, r, seg=16):
    vs = [bm.verts.new(B((p[0] + r * math.cos(2 * math.pi * k / seg), p[1], p[2] - r * math.sin(2 * math.pi * k / seg)))) for k in range(seg)]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.z > 0:
        f.normal_flip()
    return f


def box_uv(bm, tile):
    uvl = bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y
            u, v = ((gz, gy) if ax == 0 else (gx, gy) if ax == 1 else (gx, gz))
            lp[uvl].uv = (u / tile, v / tile)


ART = STANDIN = DOORS_C = LAYOUT_C = None


def finish(name, bm, mat, coll=None, smooth=False, tile=None, sharp_deg=35, keep_uv=False, recalc=True):
    material(mat)
    for e in bm.edges:
        if smooth and len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) < math.radians(sharp_deg)
        else:
            e.smooth = not (len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(1))
    for f in bm.faces:
        f.smooth = smooth
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if not bm.loops.layers.uv.get("UVMap"):
        bm.loops.layers.uv.new("UVMap")
    if not keep_uv:
        bm.normal_update()
        box_uv(bm, tile or TILES[mat])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(name, me)
    (coll or ART).objects.link(ob)
    return ob


def part(name, mat, build, **kw):
    bm = bmesh.new()
    build(bm)
    if not bm.faces:
        bm.free()
        return None
    return finish(name, bm, mat, **kw)


class Painter:
    """One palette mesh from many pieces, each piece one swatch (all its UVs at the swatch's centre)."""
    def __init__(s):
        s.bm = bmesh.new()
        s.uvl = s.bm.loops.layers.uv.new("UVMap")

    def add(s, key, fn, *a, **kw):
        old = set(s.bm.faces)
        fn(s.bm, *a, **kw)
        uv = pal_uv(key)
        for f in s.bm.faces:
            if f not in old:
                for lp in f.loops:
                    lp[s.uvl].uv = uv

    def done(s, name, coll=None, smooth=False, recalc=True):
        if not s.bm.faces:
            s.bm.free()
            return None
        return finish(name, s.bm, "Paint_Palette", coll, smooth=smooth, keep_uv=True, recalc=recalc)


def paint(name, pieces, smooth=False):
    """pieces: [(swatch, fn, args...)]"""
    p = Painter()
    for key, fn, *a in pieces:
        p.add(key, fn, *a)
    return p.done(name, smooth=smooth)


RIGHT = {"+x": (0, 0, -1), "-x": (0, 0, 1), "+z": (1, 0, 0), "-z": (-1, 0, 0)}
NORMAL = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}
SIDE_N = {"N": "+z", "S": "-z", "W": "+x", "E": "-x"}
X0 = X1 = Z0 = Z1 = H = 0.0


def wall_face(nm):
    return {"+z": Z0, "-z": Z1, "+x": X0, "-x": X1}[nm]


def on_wall(nm, a, y, d, face=None):
    """A game point on the wall whose inward normal is nm: a along it, height y, d metres into the room (from `face`, the room's wall by default)."""
    f = wall_face(nm) if face is None else face
    off = f + (1 if nm[0] == "+" else -1) * d
    return (off, y, a) if nm[1] == "x" else (a, y, off)


def wall_box(bm, nm, a0, a1, y0, y1, d0, d1, face=None):
    p, q = on_wall(nm, a0, y0, d0, face), on_wall(nm, a1, y1, d1, face)
    cube(bm, [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)])


def panel(name, mat, centre, nm, w, h, uv=(0, 0, 1, 1), bm=None, coll=None):
    """A flat quad facing nm (+x, -x, +z, -z), w wide, h tall, UV rect uv, the picture upright."""
    r, up, c = Vector(RIGHT[nm]), Vector((0, 1, 0)), Vector(centre)
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


def sign(name, key, centre, nm, w, h, depth=0.02, frame=None):
    """A sign board from the scene's atlas: a thin box (its edges a flat colour) and its face, `depth` proud of the plane it stands on."""
    nv = Vector(NORMAL[nm])
    c = Vector(centre) + nv * depth
    panel(name, "Sign_Paint", tuple(c + nv * 0.001), nm, w, h, SIGN_UV[key])
    if depth > 0.004:
        r = Vector(RIGHT[nm])
        a = Vector(centre) - r * w / 2 - Vector((0, h / 2, 0))
        b = Vector(centre) + r * w / 2 + Vector((0, h / 2, 0)) + nv * depth
        part(name + "_board", frame or "Metal_Dark", lambda bm: cube(bm, [min(a[i], b[i]) for i in range(3)], [max(a[i], b[i]) for i in range(3)]))


def orient_out(bm, centre):
    """Wind every face of an open sheet so it faces away from `centre` (game)."""
    bm.normal_update()
    cb = B(centre)
    for f in bm.faces:
        if f.normal.dot(f.calc_center_median() - cb) < 0:
            f.normal_flip()


def drape(bm, x0, x1, z0, z1, h, rng, y_hem=0.0, fold=0.022, n=10, top_sag=0.02):
    """A dust sheet thrown over a box: a sagging top and four hanging sides that fold (welded at the corners), hem at y_hem."""
    def disp(s, y):
        return fold * (0.6 * math.sin(s * 9.0 + y * 2.0) + 0.4 * math.sin(s * 23.0 + 1.3)) * min(1.0, (h - y) / 0.25)
    per = [(x0, z0), (x1, z0), (x1, z1), (x0, z1), (x0, z0)]
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    ring_s, pts = [], []
    s = 0.0
    for i in range(4):
        (ax, az), (bx, bz) = per[i], per[i + 1]
        L = math.hypot(bx - ax, bz - az)
        k = max(2, int(L / 0.12))
        for j in range(k):
            t = j / k
            pts.append((ax + (bx - ax) * t, az + (bz - az) * t))
            ring_s.append(s + L * t)
        s += L
    ys = [h - (h - y_hem) * (j / n) for j in range(n + 1)]
    grid = []
    for y in ys:
        row = []
        for (px, pz), sv in zip(pts, ring_s):
            dx, dz = px - cx, pz - cz
            ln = math.hypot(dx, dz) or 1.0
            d = disp(sv, y) + (0.012 if y < y_hem + 0.15 else 0.0)
            ox = 1.0 if abs(px - x0) < 1e-6 or abs(px - x1) < 1e-6 else 0.0
            oz = 1.0 if abs(pz - z0) < 1e-6 or abs(pz - z1) < 1e-6 else 0.0
            sx = math.copysign(ox, dx) if ox else 0.0
            sz = math.copysign(oz, dz) if oz else 0.0
            row.append(bm.verts.new(B((px + sx * d, y, pz + sz * d))))
        grid.append(row)
    for a, b in zip(grid, grid[1:]):
        m = len(a)
        for i in range(m):
            bm.faces.new((a[i], a[(i + 1) % m], b[(i + 1) % m], b[i]))
    nx, nz = max(2, int((x1 - x0) / 0.15)), max(2, int((z1 - z0) / 0.15))
    env = lambda i, j: math.sin(math.pi * i / nx) * math.sin(math.pi * j / nz)
    top = [[bm.verts.new(B((x0 + (x1 - x0) * i / nx, h + (top_sag * 0.5 * math.sin(i * 1.7 + j * 2.3) - top_sag) * env(i, j),
                            z0 + (z1 - z0) * j / nz))) for j in range(nz + 1)] for i in range(nx + 1)]
    for i in range(nx):
        for j in range(nz):
            bm.faces.new((top[i][j], top[i + 1][j], top[i + 1][j + 1], top[i][j + 1]))
    orient_out(bm, (cx, y_hem - 1.0, cz))
    bm.normal_update()
    for f in bm.faces:
        c = f.calc_center_median()
        if f.normal.z < -0.3 and c.z > h - 0.05:            # top faces: they must look up
            f.normal_flip()


def hole_free_spans(a0, a1, holes):
    """[a0, a1] minus the (h0, h1) intervals."""
    out, a = [], a0
    for h0, h1 in sorted(holes):
        if h1 <= a or h0 >= a1:
            continue
        if h0 > a:
            out.append((a, h0))
        a = max(a, h1)
    if a < a1:
        out.append((a, a1))
    return out


# ---------------------------------------------------------------- lights
LIGHTS = []         # dicts: set (day/night/always), kind, pos, power, color, size, aim, cone, shape, size_y
WARM, COOL, EMERG_C = (1.0, 0.86, 0.70), (0.92, 0.96, 1.0), (0.86, 0.93, 1.0)


def light(st, kind, pos, power, color=WARM, size=0.05, aim=None, cone=120.0, size_y=None):
    LIGHTS.append(dict(set=st, kind=kind, pos=tuple(pos), power=power, color=color, size=size, aim=aim, cone=cone, size_y=size_y))


TROFFER_W, CAN_W, SOFFIT_W, PENDANT_W, SCONCE_W, POSTER_W, FRIDGE_W = 70.0, 240.0, 70.0, 220.0, 30.0, 8.0, 18.0
EMERG_W, EXIT_W = 450.0, 2.0
SUN_W, SUN_DIR, SKY_STRENGTH = 7.0, (0.42, -0.78, -0.46), 4.0


def troffer(x, z, y, on, along_x=True, w=0.6, L=1.2):
    hx, hz = (L / 2, w / 2) if along_x else (w / 2, L / 2)
    part(f"Troffer_frame_{x:.1f}_{z:.1f}", "Plastic_White", lambda bm: [box(bm, x - hx - 0.02, x + hx + 0.02, y - 0.02, y, z - hz - 0.02, z - hz + 0.02),
                                                                      box(bm, x - hx - 0.02, x + hx + 0.02, y - 0.02, y, z + hz - 0.02, z + hz + 0.02),
                                                                      box(bm, x - hx - 0.02, x - hx + 0.02, y - 0.02, y, z - hz, z + hz),
                                                                      box(bm, x + hx - 0.02, x + hx + 0.02, y - 0.02, y, z - hz, z + hz)])
    part(f"Troffer_lens_{x:.1f}_{z:.1f}", "Lamp_Emit" if on else "Lens_Dead", lambda bm: box(bm, x - hx + 0.02, x + hx - 0.02, y - 0.012, y - 0.004, z - hz + 0.02, z + hz - 0.02))
    if on:
        light("day", "AREA", (x, y - 0.03, z), TROFFER_W, COOL, size=2 * hx - 0.06, size_y=2 * hz - 0.06, aim=(0, -1, 0))


def emergency_head(name, nm, a, y, face=None):
    """A twin-spot emergency fitting on a wall: a white box, two lamp heads aimed down and to either side (Emergency_Emit lenses), two spot lights."""
    nv, rv = Vector(NORMAL[nm]), Vector(RIGHT[nm])
    c = Vector(on_wall(nm, a, y, 0.0, face))
    part(f"{name}_body", "Plastic_White", lambda bm: wall_box(bm, nm, a - 0.16, a + 0.16, y - 0.07, y + 0.07, 0.0, 0.09, face))
    bm = bmesh.new()
    for sg in (-1, 1):
        p = c + nv * 0.13 + rv * sg * 0.11 - Vector((0, 0.02, 0))
        d = (nv * 0.6 + rv * sg * 0.45 - Vector((0, 0.75, 0))).normalized()
        cyl(bm, tuple(p - d * 0.03), tuple(p + d * 0.035), 0.04, 0.045, 12)
        light("night", "SPOT", tuple(p + d * 0.07), EMERG_W, EMERG_C, size=0.03, aim=tuple(d), cone=80.0)
    finish(f"{name}_heads", bm, "Emergency_Emit", smooth=True)
    part(f"{name}_brk", "Plastic_White", lambda bm: wall_box(bm, nm, a - 0.03, a + 0.03, y - 0.04, y + 0.04, 0.09, 0.12, face))


def ceiling_head(name, x, z, y):
    """A round emergency bulkhead on the ceiling (Emergency_Emit lens), one spot light straight down."""
    part(f"{name}_ring", "Plastic_White", lambda bm: cyl(bm, (x, y, z), (x, y - 0.05, z), 0.14, 0.13, 20), smooth=True)
    part(f"{name}_lens", "Emergency_Emit", lambda bm: cyl(bm, (x, y - 0.05, z), (x, y - 0.065, z), 0.11, 0.10, 20), smooth=True)
    light("night", "SPOT", (x, y - 0.09, z), EMERG_W * 0.8, EMERG_C, size=0.05, aim=(0, -1, 0), cone=110.0)


def exit_sign(name, nm, a, y, face=None, proud=0.0):
    """An EXIT box sign on a wall, its face glowing (Sign_Exit, always on)."""
    part(f"{name}_box", "Plastic_White", lambda bm: wall_box(bm, nm, a - 0.2, a + 0.2, y - 0.08, y + 0.08, proud, proud + 0.05, face))
    nv = Vector(NORMAL[nm])
    c = Vector(on_wall(nm, a, y, proud + 0.0505, face))
    panel(f"{name}_face", "Sign_Exit", tuple(c), nm, 0.36, 0.135, (0, 0, 1, 1))
    light("always", "AREA", tuple(c + nv * 0.05), EXIT_W, (0.3, 1.0, 0.45), size=0.36, size_y=0.13, aim=tuple(nv))


def downlight(x, z, y, on, power=None, cone=100.0, r=0.09):
    part(f"Can_trim_{x:.1f}_{z:.1f}_{y:.1f}", "Plastic_White", lambda bm: cyl(bm, (x, y, z), (x, y - 0.015, z), r + 0.03, r + 0.03, 16), smooth=True)
    part(f"Can_lens_{x:.1f}_{z:.1f}_{y:.1f}", "Lamp_Emit" if on else "Lens_Dead", lambda bm: cyl(bm, (x, y - 0.015, z), (x, y - 0.02, z), r, r, 16), smooth=True)
    if on:
        light("day", "SPOT", (x, y - 0.04, z), power or CAN_W, WARM, size=0.05, aim=(0, -1, 0), cone=cone)


def dust(name, x, z, sx, sz, y=0.003):
    """A dust decal on the floor (passable)."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    f = quad(bm, (x - sx, y, z + sz), (x + sx, y, z + sz), (x + sx, y, z - sz), (x - sx, y, z - sz))
    for lp, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = uv
    finish(f"decor_dust_{name}", bm, "Decal_Dust", keep_uv=True, recalc=False)


# ---------------------------------------------------------------- the layout objects (from the greybox model) and the shell
GB = BOX = None
P = ""
HIDDEN = []            # (x0, x1, y0, y1, z0, z1): volumes no one sees into; faces inside them are dropped before the bake
SEEN_UP, SEEN_DOWN = 2.2, 0.8


def build_layout():
    """COL_ boxes (hidden) and the empties (Link_, Arrive_, Marker_, Spot_), named and placed exactly as the greybox model has them."""
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


def build_floor(regions, default):
    """The floor collider as cells of material: regions [(mat, x0, x1, z0, z1)] (the first that holds a cell's middle wins), `default` elsewhere."""
    f = BOX[f"{P}_Floor"]
    xs = sorted({f["min"][0], f["max"][0], *[v for r in regions for v in r[1:3]]})
    zs = sorted({f["min"][2], f["max"][2], *[v for r in regions for v in r[3:5]]})
    xs = [v for v in xs if f["min"][0] <= v <= f["max"][0]]
    zs = [v for v in zs if f["min"][2] <= v <= f["max"][2]]
    cells = {}
    for xa, xb in zip(xs, xs[1:]):
        for za, zb in zip(zs, zs[1:]):
            xm, zm = (xa + xb) / 2, (za + zb) / 2
            m = next((r[0] for r in regions if r[1] <= xm <= r[2] and r[3] <= zm <= r[4]), default)
            cells.setdefault(m, []).append((xa, xb, za, zb))
    for m, cs in cells.items():
        part(f"Floor_{m}", m, lambda bm, cs=cs: [box(bm, xa, xb, f["min"][1], 0.0, za, zb) for xa, xb, za, zb in cs])


DADO = None


def build_walls(lower="Wall_Lower", upper="Wall_Paint", dado=1.0, skirting="Trim_Paint", cuts=()):
    """Each wall collider piece gets its art twin, cut at the dado (one material below, one above); a skirting board 10 cm high along the foot of
    each piece that stands on the floor."""
    global DADO
    DADO = dado
    for n, b in sorted(BOX.items()):
        if not n.startswith(f"{P}_Wall_"):
            continue
        side = n.split("_")[2]
        axis = "x" if side in "NS" else "z"
        ia, ic = (0, 2) if axis == "x" else (2, 0)
        lo, hi, c0, c1 = b["min"][ia], b["max"][ia], b["min"][ic], b["max"][ic]
        y0, y1 = b["min"][1], b["max"][1]
        tag = n[len(P) + 6:]
        segs = sorted({lo, hi, *[c for c in cuts if lo < c < hi]})          # cut where shelving starts and stops, so the hidden part can be dropped
        for si, (la, lb) in enumerate(zip(segs, segs[1:])):
            for band, ya, yb, mat in (("lo", y0, min(y1, dado or 0.0), lower), ("hi", max(y0, dado or 0.0), y1, upper)):
                if yb - ya < 1e-4:
                    continue
                part(f"Wall_{tag}_{si}_{band}", mat, lambda bm, ya=ya, yb=yb, la=la, lb=lb: box(bm, *((la, lb, ya, yb, c0, c1) if axis == "x" else (c0, c1, ya, yb, la, lb))))
        if y0 < 1e-6 and skirting:
            nm = SIDE_N[side]
            a0, a1 = max(lo, X0 if axis == "x" else Z0), min(hi, X1 if axis == "x" else Z1)
            if a1 - a0 > 0.05:
                part(f"Skirt_{tag}", skirting, lambda bm, a0=a0, a1=a1, nm=nm: wall_box(bm, nm, a0, a1, 0.0, 0.1, 0.0, 0.015))


def build_ceiling(mat, holes=()):
    c = BOX[f"{P}_Ceiling"]
    mn, mx = c["min"], c["max"]

    def bld(bm):
        cx = sorted({mn[0], mx[0], *[h[i] for h in holes for i in (0, 1)]})
        cz = sorted({mn[2], mx[2], *[h[i] for h in holes for i in (2, 3)]})
        for xa, xb in zip(cx, cx[1:]):
            for za, zb in zip(cz, cz[1:]):
                xm, zm = (xa + xb) / 2, (za + zb) / 2
                if any(h[0] < xm < h[1] and h[2] < zm < h[3] for h in holes):
                    continue
                box(bm, xa, xb, mn[1], mx[1], za, zb)
    part("Ceiling_main", mat, bld)


def door_frames(trim="Trim_Paint", lining=None):
    """Casings round every door opening on the room side of its wall (both sides on a wall inside the room), the reveal linings in the wall's
    thickness, from the greybox's leaves: hinge, run (the closed leaf's direction) and size."""
    lining = lining or trim
    for d in GB.doors:
        h, w, ht = d["hinge"], d["props"]["width"], d["props"]["height"]
        th = d["yaw"]
        r = Vector((math.cos(th), 0, -math.sin(th)))                         # game: along the closed leaf from the hinge
        hv = Vector(h)
        faces = []
        if abs(h[2] - Z1) < 1e-3:
            faces = [(Vector((0, 0, -1)), 0.0)]
        elif abs(h[2] - Z0) < 1e-3:
            faces = [(Vector((0, 0, 1)), 0.0)]
        elif abs(h[0] - X0) < 1e-3:
            faces = [(Vector((1, 0, 0)), 0.0)]
        elif abs(h[0] - X1) < 1e-3:
            faces = [(Vector((-1, 0, 0)), 0.0)]
        else:                                                                # a wall inside the room: find it, frame both faces
            wb = next(b for n, b in BOX.items() if b["col"] and "Wall" in n and b["min"][0] - 1e-3 <= h[0] <= b["max"][0] + 1e-3
                      and b["min"][2] - 1e-3 <= h[2] <= b["max"][2] + 1e-3 and b["min"][1] < 0.1)
            if wb["max"][0] - wb["min"][0] < wb["max"][2] - wb["min"][2]:
                t = wb["max"][0] - wb["min"][0]
                nrm = Vector((1, 0, 0)) if abs(h[0] - wb["max"][0]) < 1e-3 else Vector((-1, 0, 0))
            else:
                t = wb["max"][2] - wb["min"][2]
                nrm = Vector((0, 0, 1)) if abs(h[2] - wb["max"][2]) < 1e-3 else Vector((0, 0, -1))
            faces = [(nrm, 0.0), (-nrm, t)]
        single = not (d["name"].endswith("_A") or d["name"].endswith("_B"))
        tag = d["name"][9:]

        def bx(name, mat, p, q):                                            # each piece its own object: a jamb stands over its wall piece
            part(name, mat, lambda bm: cube(bm, [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)]))
        up = lambda y: Vector((0, y, 0))
        cw, dp = 0.085, 0.022
        for k, (nrm, shift) in enumerate(faces):
            base = hv + nrm * shift
            bx(f"Door_casing_{tag}_{k}_j0", trim, base - r * cw, base + nrm * dp + up(ht + cw))
            bx(f"Door_casing_{tag}_{k}_head", trim, base - r * cw + up(ht), base + r * (w + (cw if single else 0.0)) + nrm * dp + up(ht + cw))
            if single:
                bx(f"Door_casing_{tag}_{k}_j1", trim, base + r * w, base + r * (w + cw) + nrm * dp + up(ht + cw))
        T = G.T
        nrm = faces[0][0]
        bx(f"Door_lining_{tag}_j0", lining, hv, hv + r * 0.02 - nrm * T + up(ht))
        bx(f"Door_lining_{tag}_head", lining, hv + up(ht - 0.02), hv + r * w - nrm * T + up(ht))
        if single:
            bx(f"Door_lining_{tag}_j1", lining, hv + r * (w - 0.02), hv + r * w - nrm * T + up(ht))


def leaf_mesh(w, h, kind, knob="lever"):
    """A leaf in its own frame: local x from the hinge along the leaf (0..w), y across (-0.025..0.025), z up (0..h). Both faces show the door
    picture `kind`; the edges take its edge colour. knob: lever (a brass lever both sides) or bar (a push bar)."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    t = 0.025
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, 0, h / 2)) @ Matrix.Diagonal((w, 2 * t, h, 1)))
    u0, v0, u1, v1 = door_uv(kind)
    edge = door_edge_uv(kind)
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
    for sg in (-1, 1):
        if knob == "bar":
            bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.016, radius2=0.016, depth=w * 0.72,
                                  matrix=Matrix.Translation((w * 0.5, sg * (t + 0.05), 1.0)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
            for xx in (w * 0.16, w * 0.84):
                bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.012, radius2=0.012, depth=0.05,
                                      matrix=Matrix.Translation((xx, sg * (t + 0.025), 1.0)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
        else:
            kx = w - 0.07
            bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.011, radius2=0.011, depth=0.05,
                                  matrix=Matrix.Translation((kx, sg * (t + 0.025), 1.02)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
            bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.011, radius2=0.011, depth=0.13,
                                  matrix=Matrix.Translation((kx - 0.065, sg * (t + 0.05), 1.02)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
    knob_uv = pal_uv("chrome") if knob == "bar" else pal_uv("brass")
    for f in bm.faces:
        if f not in old:
            for lp in f.loops:
                lp[uvl].uv = (knob_uv[0] * 0.0 + edge[0], edge[1])
    return bm


def build_leaves(kinds):
    """Every greybox door as its own leaf object (Doors collection), origin at the hinge, with the greybox door's properties, so export_scene.py
    writes the same `doors` and the page swings each by name. kinds: {door name prefix: (picture, knob)}."""
    for d in GB.doors:
        p = d["props"]
        key = next((k for k in kinds if d["name"].startswith(k)), None)
        pic, knob = kinds.get(key, ("wood_info", "lever"))
        bm = leaf_mesh(p["width"], p["height"], pic, knob)
        me = bpy.data.meshes.new(d["name"])
        bm.to_mesh(me)
        bm.free()
        me.materials.append(material("Doors"))
        ob = bpy.data.objects.new(d["name"], me)
        ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
        for k, v in p.items():
            ob[k] = v
        DOORS_C.objects.link(ob)


# ---------------------------------------------------------------- shelving and books (the bookstore, the desk's special orders)
ROWS = []         # (collider name, origin game Vector, u (along), w, y0, h, normal Vector, depth) of every shelf row that gets books


def shelf_unit(cname, nm, a0, a1, face, depth, top, levels, bay=0.92, back=True, double=None, plinth=0.1, books=True):
    """A run of shelving whose front is the plane `face` (along nm's axis), from a0 to a1 along it, `depth` deep toward the wall, `top` high, with
    board tops at `levels`. double: the far face of a double-sided run (its front plane), for a freestanding bookcase. Registers its rows in ROWS."""
    nv = Vector(NORMAL[nm])
    r = Vector(RIGHT[nm])
    alongx = nm[1] == "z"
    nb = max(1, int(round((a1 - a0) / bay)))
    bw = (a1 - a0) / nb
    sides = [(nm, face)] + ([(("-" if nm[0] == "+" else "+") + nm[1], double)] if double is not None else [])

    def P3(a, y, d, f=face, n=nm):            # a along, y, d metres back from the front plane f (toward the wall / the run's middle)
        return on_wall(n, a, y, -d, f)

    def carcass(bm):
        for i in range(nb + 1):                                  # uprights at the bay lines, full depth
            a = a0 + i * bw
            p, q = P3(a - 0.015, 0.0, 0.0), P3(a + 0.015, top, depth if double is None else (abs(double - face)))
            cube(bm, [min(p[k], q[k]) for k in range(3)], [max(p[k], q[k]) for k in range(3)])
        for (n, f) in sides:                                     # the plinth's kick and the cornice, on each face
            p, q = on_wall(n, a0, 0.0, 0.0, f), on_wall(n, a1, plinth, -0.03, f)
            cube(bm, [min(p[k], q[k]) for k in range(3)], [max(p[k], q[k]) for k in range(3)])
            p, q = on_wall(n, a0 - 0.02, top - 0.09, 0.02, f), on_wall(n, a1 + 0.02, top, -0.06, f)
            cube(bm, [min(p[k], q[k]) for k in range(3)], [max(p[k], q[k]) for k in range(3)])
        full = depth if double is None else abs(double - face)
        for y in levels:                                          # the boards, one long box per level
            p, q = P3(a0, y - 0.025, 0.005), P3(a1, y, full - 0.005)
            cube(bm, [min(p[k], q[k]) for k in range(3)], [max(p[k], q[k]) for k in range(3)])
    part(f"{cname}_wood", "Wood_Shelf", carcass)
    if back:
        full = depth if double is None else abs(double - face)
        dmid = depth - 0.012 if double is None else full / 2 - 0.006
        part(f"{cname}_back", "Shelf_Back", lambda bm: wall_box(bm, nm, a0, a1, plinth, top - 0.09, -dmid, -(dmid + 0.012), face))
    if not books:
        return
    full = depth if double is None else abs(double - face)
    for (n, f) in sides:
        for i in range(nb):
            for y0, y1 in zip(levels, levels[1:] + [top - 0.09]):
                h = y1 - 0.025 - y0 if y1 != top - 0.09 else y1 - y0
                if h < 0.2:
                    continue
                ru = Vector(RIGHT[n])
                a = a0 + i * bw + 0.016
                pos = (ru.x if alongx else ru.z) > 0                    # does the row's right hand run up the bay's coordinate?
                o = Vector(on_wall(n, a if pos else a0 + (i + 1) * bw - 0.016, y0, 0.0, f))
                ROWS.append((cname, o, ru, bw - 0.032, y0, h, Vector(NORMAL[n]), (full if double is None else full / 2) - 0.03))


def pack_rows(S):
    """Each shelf row is one rectangle of the books' lightmap (its front plane, w x h): shelf-pack them all at the highest density that fits S."""
    m = MARGIN_PX

    def layout(D):
        boxes = sorted(((math.ceil(r[5] * D) + 2 * m, math.ceil(r[3] * D) + 2 * m, i) for i, r in enumerate(ROWS)), key=lambda b: (-b[0], -b[1]))
        x = y = rowh = 0
        place = {}
        for bh, bw, i in boxes:
            if x + bw > S:
                x, y, rowh = 0, y + rowh, 0
            if y + bh > S or bw > S:
                return None
            place[i] = (x + m, y + m)
            x += bw
            rowh = max(rowh, bh)
        return place
    lo, hi, best = 4.0, 600.0, None
    for _ in range(40):
        mid = (lo + hi) / 2
        pl = layout(mid)
        if pl:
            lo, best = mid, (mid, pl)
        else:
            hi = mid
    return best


BOOKS_PAGE = 2048


def build_books(rng, fill_lo=0.25, fill_hi=1.0, empty=0.12):
    """Every row filled from the spine atlas: books flush at the front, their heights the spines' own; some rows thin or empty, a book leaning
    at the end of a short row. Each book is its front, top and two sides; their lightmap UVs project onto the row's rectangle (packed by
    pack_rows), so a row is one island (the tops and sides fall on its lines: they take its light)."""
    if not ROWS:
        return 0
    D, place = pack_rows(BOOKS_PAGE)
    S = BOOKS_PAGE
    by_col = {}
    pages = ((PAGES_RECT[0] + 4) / 1024, 1 - (PAGES_RECT[3] - 4) / 1024)
    nbooks = 0
    for i, (cname, o, u, w, y0, h, nrm, depth) in enumerate(ROWS):
        bm = by_col.get(cname)
        if bm is None:
            bm = by_col[cname] = bmesh.new()
            bm.loops.layers.uv.new("UVMap")
            bm.loops.layers.uv.new("lightmap")
        uvl, lml = bm.loops.layers.uv["UVMap"], bm.loops.layers.uv["lightmap"]
        px, py = place[i]
        fill = 0.0 if rng.random() < empty else rng.uniform(fill_lo, fill_hi) if rng.random() < 0.4 else rng.uniform(0.8, 1.0)
        start = int(rng.integers(len(SPINES)))
        x = 0.0
        k = 0
        lean = None

        def lm(v):
            g = Vector((v.x, v.z, -v.y))
            a = (g - o).dot(u)
            b = g.y - y0
            return ((px + max(0.0, min(w, a)) * D) / S, (py + max(0.0, min(h, b)) * D) / S)
        row = []
        while True:
            r, sx0, sx1, hm = SPINES[(start + k) % len(SPINES)]
            k += 1
            bwid = (sx1 - sx0) / SPINE_PX_M
            if hm > h - 0.01:
                hm = h - 0.012
            if x + bwid > w * fill:
                if 0.0 < fill < 0.9 and x + 0.3 < w and rng.random() < 0.5:
                    lean = (x, bwid, hm, r, sx0, sx1)
                break
            gap = 0.0 if rng.random() < 0.9 else rng.uniform(0.002, 0.01)
            row.append((x + gap, bwid, hm, gap, min(depth, rng.uniform(0.15, 0.23)), r, sx0, sx1))
            x += bwid + gap
        fb = -nrm * 0.012                                          # 12 mm back from the shelf's front
        for j, (bx0, bwid, hm, gap, bd, r, sx0, sx1) in enumerate(row):
            p0 = o + u * bx0 + fb
            p1 = p0 + u * bwid
            up = Vector((0, hm, 0))
            vb0 = 1 - (r + 1) * SPINE_ROW / 1024
            vt0 = vb0 + hm * SPINE_PX_M / 1024
            ua, ub = (sx0 + 0.5) / 1024, (sx1 - 0.5) / 1024
            faces = [((p0, p1, p1 + up, p0 + up), ((ua, vb0), (ub, vb0), (ub, vt0), (ua, vt0)))]           # the spine
            if y0 + hm < SEEN_UP + 0.05:                                                              # the top, where it can be seen
                faces.append(((p0 + up, p1 + up, p1 + up - nrm * bd, p0 + up - nrm * bd), [pages] * 4))
            prev = row[j - 1] if j else None
            nxt = row[j + 1] if j + 1 < len(row) else None
            if prev is None or gap > 0 or prev[2] < hm - 0.015:                                       # a side only where it shows
                faces.append(((p0 - nrm * bd, p0, p0 + up, p0 - nrm * bd + up), [(ua + 0.5 / 1024, vb0)] * 2 + [(ua + 0.5 / 1024, vt0)] * 2))
            if nxt is None or nxt[3] > 0 or nxt[2] < hm - 0.015:
                faces.append(((p1, p1 - nrm * bd, p1 - nrm * bd + up, p1 + up), [(ub - 0.5 / 1024, vb0)] * 2 + [(ub - 0.5 / 1024, vt0)] * 2))
            for vs, uvs in faces:
                f = bm.faces.new([bm.verts.new(B(tuple(q))) for q in vs])
                for lp, uvv in zip(f.loops, uvs):
                    lp[uvl].uv = uvv
                    lp[lml].uv = lm(lp.vert.co)
            nbooks += 1
        if lean:                                                   # one book leaning on the last standing one, its foot slid out toward the empty end
            lx, bwid, hm, r, sx0, sx1 = lean
            ang = math.radians(rng.uniform(12, 24))
            bd = 0.18
            base = o - nrm * 0.012 + Vector((0, 0.0005, 0))
            vb0 = 1 - (r + 1) * SPINE_ROW / 1024
            vt0 = vb0 + hm * SPINE_PX_M / 1024
            ua, ub = (sx0 + 0.5) / 1024, (sx1 - 0.5) / 1024
            wdir = u * math.cos(ang) + Vector((0, math.sin(ang), 0))          # along the book's width, tipped
            vdir = -u * math.sin(ang) + Vector((0, math.cos(ang), 0))         # up the book's spine, tipped back onto its neighbour
            bl = base + u * (lx + hm * math.sin(ang))
            br, tl = bl + wdir * bwid, bl + vdir * hm
            tr = br + vdir * hm
            vs = [bm.verts.new(B(tuple(c))) for c in (bl, br, tr, tl)]
            vsb = [bm.verts.new(B(tuple(c - nrm * bd))) for c in (bl, br, tr, tl)]
            for vv, uvs in (((vs[0], vs[1], vs[2], vs[3]), ((ua, vb0), (ub, vb0), (ub, vt0), (ua, vt0))),
                            ((vs[3], vs[2], vsb[2], vsb[3]), [pages] * 4),
                            ((vs[1], vsb[1], vsb[2], vs[2]), [(ub, vb0)] * 2 + [(ub, vt0)] * 2)):
                f = bm.faces.new(vv)
                for lp, uvv in zip(f.loops, uvs):
                    lp[uvl].uv = uvv
                    lp[lml].uv = lm(lp.vert.co)
            nbooks += 1
    for cname, bm in by_col.items():
        bm.normal_update()
        finish(f"{cname}_books", bm, "Book_Spines", keep_uv=True, recalc=False)
    print(f"BOOKS {nbooks} books on {len(ROWS)} rows; lightmap {D:.1f} px/m on {S}")
    return D


def book_pile(bm_uv_painter_bm, x, z, y, n, rng, along_x=True, size=(0.16, 0.24)):
    """A pile of n books lying flat (Book_Loose): returns nothing; adds to the given bmesh (which must have a UVMap layer)."""
    bm = bm_uv_painter_bm
    uvl = bm.loops.layers.uv["UVMap"]
    for i in range(n):
        r, sx0, sx1, hm = SPINES[int(rng.integers(len(SPINES)))]
        t = (sx1 - sx0) / SPINE_PX_M
        w, d = rng.uniform(*size), rng.uniform(size[0] * 0.75, size[0])
        off = rng.uniform(-0.015, 0.015, 2)
        ang = rng.uniform(-0.15, 0.15)
        old = set(bm.faces)
        cx, cz = x + off[0], z + off[1]
        ca, sa = math.cos(ang), math.sin(ang)
        hw, hd = (w / 2, d / 2) if along_x else (d / 2, w / 2)
        pts = [(cx + ca * px - sa * pz, cz + sa * px + ca * pz) for px, pz in ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd))]
        vb = [bm.verts.new(B((px, y, pz))) for px, pz in pts]
        vt = [bm.verts.new(B((px, y + t, pz))) for px, pz in pts]
        bm.faces.new((vt[0], vt[3], vt[2], vt[1]))                     # wound to face out (the corners run +x then +z)
        for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
            bm.faces.new((vb[b], vb[a], vt[a], vt[b]))
        vb0 = 1 - (r + 1) * SPINE_ROW / 1024
        for f in bm.faces:
            if f in old:
                continue
            for lp in f.loops:
                lp[uvl].uv = ((sx0 + sx1) / 2048, vb0 + 0.03)
        y += t
    return y


def loose_books(name, piles, rng, split=False):
    """piles: [(x, z, y, n, along_x)]: Book_Loose piles, one object (or one per pile with `split`, so each pile's box is its own)."""
    groups_ = [[p] for p in piles] if split else [piles]
    for k, grp in enumerate(groups_):
        bm = bmesh.new()
        bm.loops.layers.uv.new("UVMap")
        for x, z, y, n, ax in grp:
            book_pile(bm, x, z, y, n, rng, ax)
        if bm.faces:
            bm.normal_update()
            finish(f"{name}_{k}" if split else name, bm, "Book_Loose", keep_uv=True, recalc=False)
        else:
            bm.free()


def ladder(name, nm, a, face, height=3.05, width=0.44):
    """A library ladder hooked on its rail, stowed upright against the shelf (its stiles within 4 cm of the shelf's front)."""
    def bld(bm):
        for sg in (-1, 1):
            wall_box(bm, nm, a + sg * width / 2 - 0.02, a + sg * width / 2 + 0.02, 0.02, height, 0.005, 0.04, face)
        y = 0.28
        while y < height - 0.15:
            wall_box(bm, nm, a - width / 2 + 0.02, a + width / 2 - 0.02, y, y + 0.03, 0.012, 0.035, face)
            y += 0.3
    part(name, "Wood_Desk", bld)
    paint(f"{name}_hw", [("brass", lambda bm: [wall_box(bm, nm, a + sg * width / 2 - 0.025, a + sg * width / 2 + 0.025, height - 0.05, height + 0.03, 0.0, 0.045, face)
                                               for sg in (-1, 1)]),
                         ("rubber", lambda bm: [wall_box(bm, nm, a + sg * width / 2 - 0.025, a + sg * width / 2 + 0.025, 0.0, 0.03, 0.0, 0.045, face) for sg in (-1, 1)])])


def armchair(name, x0, x1, z0, z1, h, face, rng):
    """An armchair filling its collider box: a base, seat cushion, a back on the side away from `face` (game dir it looks), two arms."""
    fx, fz = face
    def bld(bm):
        box(bm, x0 + 0.02, x1 - 0.02, 0.06, 0.38, z0 + 0.02, z1 - 0.02)
        if abs(fx) > 0.5:
            bx0, bx1 = (x0, x0 + 0.2) if fx > 0 else (x1 - 0.2, x1)
            box(bm, bx0, bx1, 0.3, h, z0 + 0.02, z1 - 0.02)
            for za, zb in ((z0, z0 + 0.15), (z1 - 0.15, z1)):
                box(bm, x0 + 0.02, x1 - 0.02, 0.3, 0.64, za, zb)
            sx0, sx1 = (bx1, x1 - 0.04) if fx > 0 else (x0 + 0.04, bx0)
            box(bm, sx0, sx1, 0.38, 0.5, z0 + 0.16, z1 - 0.16)
        else:
            bz0, bz1 = (z0, z0 + 0.2) if fz > 0 else (z1 - 0.2, z1)
            box(bm, x0 + 0.02, x1 - 0.02, 0.3, h, bz0, bz1)
            for xa, xb in ((x0, x0 + 0.15), (x1 - 0.15, x1)):
                box(bm, xa, xb, 0.3, 0.64, z0 + 0.02, z1 - 0.02)
            sz0, sz1 = (bz1, z1 - 0.04) if fz > 0 else (z0 + 0.04, bz0)
            box(bm, x0 + 0.16, x1 - 0.16, 0.38, 0.5, sz0, sz1)
    part(name, "Fabric_Chair", bld, smooth=False)
    paint(f"{name}_feet", [("charcoal", lambda bm: [box(bm, x - 0.025, x + 0.025, 0.0, 0.07, z - 0.025, z + 0.025)
                                                    for x in (x0 + 0.06, x1 - 0.06) for z in (z0 + 0.06, z1 - 0.06)])])


# ================================================================ the four scenes
def bookstore():
    rng = np.random.default_rng(101)
    build_floor([], "Carpet_Shop")
    build_walls(lower="Wall_Paint", upper="Wall_Paint", dado=3.3, cuts=(4.2, 6.0))
    HIDDEN.extend([(-10.01, 10.01, 0.0, 3.3, -8.01, -7.995), (-10.01, -9.995, 0.0, 3.3, -8.0, 6.0), (9.995, 10.01, 0.0, 3.3, -8.0, 4.2)])   # the wall behind the shelving
    build_ceiling("Ceiling_Tile")
    door_frames("Trim_Paint")
    build_leaves({"DoorLeaf_wing_books": ("glass", "bar"), "DoorLeaf_bookstore_desk": ("wood_info", "lever")})
    TOP = 3.3
    lv_wall = [0.1, 0.48, 0.86, 1.24, 1.62, 2.0, 2.38, 2.76]
    lv_run = [0.1, 0.46, 0.82, 1.18, 1.54]
    sN, sW, sE = BOX["Shelf_N"], BOX["Shelf_W"], BOX["Shelf_E"]
    shelf_unit("Shelf_N", "+z", -9.6, 9.6, sN["max"][2], 0.4, TOP, lv_wall)
    shelf_unit("Shelf_W", "+x", sW["min"][2], sW["max"][2], sW["max"][0], 0.4, TOP, lv_wall)
    shelf_unit("Shelf_E", "-x", sE["min"][2], sE["max"][2], sE["min"][0], 0.4, TOP, lv_wall)
    # the corners of the wall shelving (behind the side runs' ends) and the side runs' end panels
    part("Shelf_corner_W", "Wood_Shelf", lambda bm: box(bm, -10.0, -9.6, 0.0, TOP, -8.0, -7.6))
    part("Shelf_corner_E", "Wood_Shelf", lambda bm: box(bm, 9.6, 10.0, 0.0, TOP, -8.0, -7.6))
    part("Shelf_W_end", "Wood_Shelf", lambda bm: box(bm, -10.0, -9.6, 0.0, TOP, sW["max"][2] - 0.03, sW["max"][2]))
    part("Shelf_E_end", "Wood_Shelf", lambda bm: box(bm, 9.6, 10.0, 0.0, TOP, sE["max"][2] - 0.03, sE["max"][2]))
    runs = sorted([b for n, b in BOX.items() if n.startswith("Bookcase_Run")], key=lambda b: b["min"][0])
    for k, b in enumerate(runs):
        n = next(nn for nn, bb in BOX.items() if bb is b)
        x0, x1, z0, z1 = b["min"][0], b["max"][0], b["min"][2], b["max"][2]
        shelf_unit(n, "+x", z0, z1, x1, (x1 - x0) / 2, 2.0, lv_run, bay=0.925, double=x0)
        part(f"{n}_ends", "Wood_Shelf", lambda bm: [box(bm, x0, x1, 0.0, 2.0, z0, z0 + 0.03), box(bm, x0, x1, 0.0, 2.0, z1 - 0.03, z1)])
        sign(f"{n}_cat_S", f"cat{2 * k}", ((x0 + x1) / 2, 1.72, z1), "+z", 0.7, 0.15, depth=0.012)
        sign(f"{n}_cat_N", f"cat{2 * k + 1}", ((x0 + x1) / 2, 1.72, z0), "-z", 0.7, 0.15, depth=0.012)
        for sg, nm in ((1, "+x"), (-1, "-x")):                # the header board over the run, both faces (overhead)
            sign(f"{n}_head_{nm}", f"cat{(2 * k + (sg > 0)) % 8}", (x1 if sg > 0 else x0, 2.17, (z0 + z1) / 2), nm, 1.6, 0.34, depth=0.0)
        part(f"decor_{n}_header", "Wood_Shelf", lambda bm: box(bm, x0 + 0.002, x1 - 0.002, 2.0, 2.34, (z0 + z1) / 2 - 0.82, (z0 + z1) / 2 + 0.82))
    for i, a in enumerate((-7.0, -1.6, 3.6, 8.2)):                       # boards standing on the cornices
        sign(f"Wall_sign_N{i}", f"wall{i}", (a, 3.43, sN["max"][2]), "+z", 1.5, 0.21, depth=0.01)
    sign("Wall_sign_W", "wall4", (sW["max"][0], 3.43, -3.5), "+x", 1.5, 0.21, depth=0.01)
    sign("Wall_sign_E", "wall5", (sE["min"][0], 3.43, -2.0), "-x", 1.5, 0.21, depth=0.01)
    # the brass rail the ladders hang from, and three ladders stowed upright
    part("Ladder_rail_N", "Brass", lambda bm: cyl(bm, (-9.5, 3.02, sN["max"][2] + 0.03), (9.5, 3.02, sN["max"][2] + 0.03), 0.015, 0.015, 8), smooth=True)
    part("Ladder_rail_W", "Brass", lambda bm: cyl(bm, (sW["max"][0] + 0.03, 3.02, -7.5), (sW["max"][0] + 0.03, 3.02, 5.9), 0.015, 0.015, 8), smooth=True)
    ladder("Ladder_1", "+z", -3.05, sN["max"][2])
    ladder("Ladder_2", "+z", 5.55, sN["max"][2])
    ladder("Ladder_3", "+x", -2.6, sW["max"][0])
    # the sale table (sheet pulled half off) and three display tables under dust sheets
    tables = sorted([(n, b) for n, b in BOX.items() if n.startswith("Sheeted_Display_Table")])
    for n, b in tables:
        x0, x1, z0, z1, hh = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]
        sale = n.endswith("_4")
        part(f"{n}_table", "Wood_Desk", lambda bm: [box(bm, x0, x1, hh - 0.04, hh, z0, z1)] + [box(bm, x - 0.03, x + 0.03, 0.0, hh - 0.04, z - 0.03, z + 0.03)
                                                                                         for x in (x0 + 0.05, x1 - 0.05) for z in (z0 + 0.05, z1 - 0.05)])
        if sale:
            xm = (x0 + x1) / 2
            part(f"{n}_sheet", "Cloth_Sheet", lambda bm: drape(bm, x0 - 0.005, xm, z0 - 0.005, z1 + 0.005, hh + 0.09, rng, y_hem=hh, fold=0.03, n=4, top_sag=0.05),
                 recalc=False)                                     # pulled back and bunched on one half
            loose_books(f"{n}_books", [(xm + 0.15, z0 + 0.3, hh, 4, True), (xm + 0.42, z0 + 0.35, hh, 3, False), (xm + 0.2, z0 + 0.75, hh, 5, True),
                                       (xm + 0.45, z0 + 1.05, hh, 2, False), (xm + 0.12, z1 - 0.2, hh, 3, True), (x0 + 0.25, z0 + 0.5, hh + 0.06, 2, True)], rng)
            panel(f"{n}_card", "Sign_Paint", (xm + 0.3, hh + 0.25, z1 - 0.02), "+z", 0.3, 0.18, SIGN_UV["sale"])
            paint(f"{n}_card_stand", [("card", lambda bm: box(bm, xm + 0.14, xm + 0.46, hh, hh + 0.34, z1 - 0.045, z1 - 0.025))])
        else:
            part(f"{n}_sheet", "Cloth_Sheet", lambda bm: drape(bm, x0 - 0.005, x1 + 0.005, z0 - 0.005, z1 + 0.005, hh + 0.012, rng, y_hem=0.04), recalc=False)
    # the window displays: carpeted plinths, book pyramids, the glass papered over from the inside
    for n, b in sorted((n, b) for n, b in BOX.items() if n.startswith("Window_Plinth")):
        x0, x1, z0, z1, hh = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]
        paint(n, [("felt", lambda bm: box(bm, x0, x1, 0.0, hh, z0, z1))])
        xm = -5.5 if x1 < 0 else 5.5
        piles = [(x, z0 + 0.45, hh, int(rng.integers(3, 8)), True) for x in np.arange(x0 + 0.5, x1 - 0.3, 0.55) if abs(x - xm) > 0.7]
        loose_books(f"{n}_books", piles, rng, split=True)
    for xa, xb in ((-9.6, -1.0), (1.0, 9.6)):
        panel(f"Window_paper_{xa:.0f}", "Glass_Paper", ((xa + xb) / 2, 1.5, 7.992), "-z", xb - xa, 2.2, (0, 0, (xb - xa) / 1.0, 2.2))
        part(f"Window_frame_{xa:.0f}", "Metal_Dark", lambda bm, xa=xa, xb=xb: [wall_box(bm, "-z", xa, xb, 0.38, 0.42, 0.0, 0.03), wall_box(bm, "-z", xa, xb, 2.58, 2.64, 0.0, 0.03)]
             + [wall_box(bm, "-z", x - 0.03, x + 0.03, 0.4, 2.6, 0.0, 0.03) for x in np.linspace(xa, xb, 5)])
    sign("Window_closing", "closing", (-5.5, 2.35, 7.98), "-z", 1.3, 0.24, depth=0.0)
    # the children's corner: picture-book bins, a low table and stools, a rug, beanbags, bunting, its sign
    kb = BOX["Kids_Bins"]
    x0, x1, z0, z1, hh = kb["min"][0], kb["max"][0], kb["min"][2], kb["max"][2], kb["max"][1]
    bins = []
    for i, zc in enumerate(np.linspace(z0 + 0.4, z1 - 0.4, 3)):
        c = ("red", "blue", "yellow")[i]
        bins += [(c, box, x0, x1, 0.0, hh * 0.45, zc - 0.38, zc + 0.38), (c, box, x0, x0 + 0.06, hh * 0.45, hh, zc - 0.38, zc + 0.38),
                 (c, box, x0, x1, hh * 0.45, hh * 0.55, zc - 0.40, zc - 0.36), (c, box, x0, x1, hh * 0.45, hh * 0.55, zc + 0.36, zc + 0.40)]
        for j in range(5):                                               # picture books standing face out, leaning back
            bins.append(((("rug_a", "rug_b", "rug_c", "green", "pink")[(i + j) % 5]), box, x0 + 0.08 + j * 0.07, x0 + 0.1 + j * 0.07,
                         hh * 0.45, hh * 0.45 + 0.26, zc - 0.17, zc + 0.17))
    paint("Kids_Bins", bins)
    kt = BOX["Kids_Table"]
    cx, cz = (kt["min"][0] + kt["max"][0]) / 2, (kt["min"][2] + kt["max"][2]) / 2
    paint("Kids_Table", [("yellow", cyl, (cx, 0.48, cz), (cx, 0.52, cz), 0.42, 0.42, 24), ("white", cyl, (cx, 0.0, cz), (cx, 0.48, cz), 0.05, 0.05, 10)]
          + [(c, cyl, (cx + dx, 0.0, cz + dz), (cx + dx, 0.3, cz + dz), 0.16, 0.15, 16) for c, (dx, dz) in
             zip(("red", "blue", "green", "orange"), ((-0.74, 0.0), (0.74, 0.0), (0.0, -0.64), (0.0, 0.64)))], smooth=False)
    paint("decor_kids_rug", [("rug_b", cyl, (cx, 0.0, cz), (cx, 0.008, cz), 1.15, 1.15, 32), ("rug_c", cyl, (cx, 0.008, cz), (cx, 0.012, cz), 0.8, 0.8, 32),
                             ("rug_a", cyl, (cx, 0.012, cz), (cx, 0.015, cz), 0.45, 0.45, 32)])
    paint("decor_beanbags", [("bean_a", sphere, (-6.0, 0.22, 6.35), 0.38, 12, 0.6), ("bean_b", sphere, (-5.35, 0.22, 5.4), 0.36, 12, 0.6)], smooth=True)
    loose_books("decor_kids_books", [(cx + 0.1, cz - 0.1, 0.52, 2, True), (cx - 0.2, cz + 0.15, 0.52, 1, False), (-8.9, 4.75, 0.0, 2, False)], rng)

    def bunting(bm):
        pass
    bt = Painter()
    for (xa, za), (xb, zb) in (((-9.6, 4.6), (-5.2, 6.9)), ((-9.6, 6.9), (-5.2, 4.6))):
        n = 12
        for i in range(n):
            t0, t1 = i / n, (i + 0.7) / n
            sag = lambda t: 3.1 - 0.35 * math.sin(math.pi * t)
            pa = (xa + (xb - xa) * t0, sag(t0), za + (zb - za) * t0)
            pb = (xa + (xb - xa) * t1, sag(t1), za + (zb - za) * t1)
            pc = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2 - 0.18, (pa[2] + pb[2]) / 2)

            def tri(bm, pa=pa, pb=pb, pc=pc):
                f = bm.faces.new([bm.verts.new(B(p)) for p in (pa, pb, pc)])
                f2 = bm.faces.new([bm.verts.new(B(p)) for p in (pa, pc, pb)])
            bt.add(("rug_a", "rug_b", "rug_c", "green", "pink")[i % 5], tri)
    bt.done("decor_bunting", recalc=False)
    sign("Kids_sign", "kids", (sW["max"][0] + 0.002, 3.0, 5.2), "+x", 1.4, 0.35, depth=0.0)
    # the reading chairs, their side table with a lamp (off) and an open book
    armchair("Reading_Chair", *[BOX["Reading_Chair"][k][i] for k, i in (("min", 0), ("max", 0), ("min", 2), ("max", 2))], 0.95, (1, 0), rng)
    armchair("Reading_Chair_2", *[BOX["Reading_Chair_2"][k][i] for k, i in (("min", 0), ("max", 0), ("min", 2), ("max", 2))], 0.95, (-1, 0), rng)
    rt = BOX["Reading_Table"]
    tx, tz = (rt["min"][0] + rt["max"][0]) / 2, (rt["min"][2] + rt["max"][2]) / 2
    part("Reading_Table", "Wood_Desk", lambda bm: [cyl(bm, (tx, 0.52, tz), (tx, 0.55, tz), 0.29, 0.29, 20), cyl(bm, (tx, 0.0, tz), (tx, 0.52, tz), 0.03, 0.03, 8),
                                                   box(bm, rt["min"][0], rt["max"][0], 0.0, 0.03, tz - 0.03, tz + 0.03), box(bm, tx - 0.03, tx + 0.03, 0.0, 0.03, rt["min"][2], rt["max"][2])], smooth=True)
    paint("Reading_lamp", [("brass", cyl, (tx + 0.08, 0.55, tz), (tx + 0.08, 0.92, tz), 0.012, 0.012, 8), ("brass", cyl, (tx + 0.08, 0.55, tz), (tx + 0.08, 0.57, tz), 0.07, 0.07, 12),
                           ("lamp_shade", cyl, (tx + 0.08, 0.85, tz), (tx + 0.08, 1.04, tz), 0.15, 0.09, 16)], smooth=True)
    loose_books("Reading_books", [(tx - 0.12, tz, 0.55, 2, False), (5.12, 5.62, 0.5, 1, True)], rng)
    # odds and ends on the floor (passable): fallen books, a carton of returns, a kick-step stool
    loose_books("decor_fallen", [(-6.2, -4.6, 0.0, 1, False), (-5.2, 0.9, 0.0, 2, True), (8.1, -2.3, 0.0, 1, True), (-0.6, -6.6, 0.0, 3, True), (2.6, 3.1, 0.0, 1, False)], rng,
                split=True)
    paint("decor_carton", [("kraft", box, -8.9, -8.4, 0.0, 0.32, -6.95, -6.5), ("tape", box, -8.9, -8.4, 0.32, 0.325, -6.75, -6.7)])
    loose_books("decor_carton_books", [(-8.65, -6.72, 0.325, 3, True)], rng)
    paint("decor_kickstep", [("charcoal", cyl, (6.2, 0.0, -1.0), (6.2, 0.38, -1.0), 0.2, 0.15, 16), ("rubber", cyl, (6.2, 0.38, -1.0), (6.2, 0.4, -1.0), 0.15, 0.15, 16)], smooth=True)
    for i, (x, z, sx, sz) in enumerate(((0.0, -6.6, 2.0, 0.6), (-5.7, -2.0, 0.6, 2.2), (5.7, -2.0, 0.6, 2.0), (8.6, -4.0, 0.6, 2.5), (-2.6, 3.0, 2.0, 0.8),
                                         (6.0, 6.6, 2.0, 0.4), (-8.6, -1.0, 0.6, 2.4))):
        dust(f"{i}", x, z, sx, sz)
    # the information sign over the desk's door; EXIT signs; the ceiling's lights and emergency heads
    sign("Info_sign", "info", (X1, 2.38, 5.0), "-x", 1.0, 0.19, depth=0.015)
    exit_sign("Exit_S", "-z", 0.0, 2.62)
    exit_sign("Exit_E", "-x", 5.0, 2.62 + 0.0, proud=0.0)
    dead = {(0, 1), (3, 2), (1, 3), (4, 0)}
    for i, x in enumerate((-7.2, -3.6, 0.0, 3.6, 7.2)):
        for j, z in enumerate((-6.4, -3.0, 0.4, 3.8, 6.6)):
            troffer(x, z, H, (i, j) not in dead, along_x=False)
    for k, (x, z) in enumerate(((-5.7, -4.6), (5.7, -4.6), (0.0, -1.6), (-5.0, 5.2), (5.0, 5.0), (0.0, 6.4), (-8.6, -1.0), (8.6, -1.0), (0.0, -6.6))):
        ceiling_head(f"Emerg_{k}", x, z, H)


def bookstore_desk():
    rng = np.random.default_rng(202)
    build_floor([("Floor_Vinyl", 3.2, X1 + G.T, Z0 - G.T, -1.6)], "Carpet_Shop")
    build_walls(lower="Wall_Lower", upper="Wall_Paint", dado=1.0)
    build_ceiling("Ceiling_Tile")
    # the stock room's own walls (inside the room): their art twins
    for n in ("Office_Wall_W", "Office_Wall_S_1", "Office_Wall_S_2", "Office_Wall_S_3"):
        b = BOX[n]
        part(n, "Wall_Paint", lambda bm, b=b: cube(bm, b["min"], b["max"]))
    door_frames("Trim_Paint")
    build_leaves({"DoorLeaf_bookstore": ("wood_info", "lever"), "DoorLeaf_office": ("wood_stock", "lever")})
    # the desk: an L of wood panels, a laminate top with a lip, the knee space open on the staff side
    cd, cr = BOX["Cash_Desk"], BOX["Cash_Desk_Return"]
    part("Cash_Desk", "Wood_Desk", lambda bm: [box(bm, cd["min"][0], cd["max"][0], 0.0, 1.0, cd["max"][2] - 0.04, cd["max"][2]),
                                               box(bm, cd["min"][0], cd["min"][0] + 0.04, 0.0, 1.0, cd["min"][2], cd["max"][2]),
                                               box(bm, -0.9, -0.86, 0.0, 1.0, cd["min"][2], cd["max"][2] - 0.04),
                                               box(bm, cd["min"][0], cd["max"][0], 0.0, 0.08, cd["min"][2] + 0.05, cd["max"][2] - 0.04)])
    part("Cash_Desk_top", "Laminate", lambda bm: box(bm, cd["min"][0] - 0.02, cd["max"][0], 1.0, 1.05, cd["min"][2], cd["max"][2] + 0.03))
    part("Cash_Desk_Return", "Wood_Desk", lambda bm: [box(bm, cr["min"][0], cr["min"][0] + 0.04, 0.0, 1.0, cr["min"][2], cr["max"][2]),
                                                      box(bm, cr["max"][0] - 0.04, cr["max"][0], 0.0, 1.0, cr["min"][2], cr["max"][2]),
                                                      box(bm, cr["min"][0], cr["max"][0], 0.0, 1.0, cr["max"][2] - 0.04, cr["max"][2])])
    part("Cash_Desk_Return_top", "Laminate", lambda bm: box(bm, cr["min"][0] - 0.02, cr["max"][0] + 0.02, 1.0, 1.05, cr["min"][2], cr["max"][2] + 0.02))
    # on the desk: the old terminal (a beige CRT and keyboard), the till, order slips on a spike and in a tray, a phone, a bell, pens
    tx, tz = -1.6, -0.9                                             # it faces the staff side (-z)
    paint("Desk_terminal", [("beige", box, tx - 0.2, tx + 0.2, 1.05, 1.42, tz - 0.16, tz + 0.18), ("beige", box, tx - 0.14, tx + 0.14, 1.1, 1.36, tz + 0.18, tz + 0.3),
                            ("charcoal", box, tx - 0.15, tx + 0.15, 1.1, 1.38, tz - 0.165, tz - 0.16), ("beige", box, tx - 0.1, tx + 0.1, 1.05, 1.07, tz - 0.1, tz + 0.1),
                            ("beige", box, tx - 0.24, tx + 0.24, 1.05, 1.085, tz - 0.34, tz - 0.2), ("grey", box, tx - 0.22, tx + 0.22, 1.085, 1.09, tz - 0.33, tz - 0.21)])
    panel("Desk_terminal_screen", "Sign_Paint", (tx, 1.245, tz - 0.168), "-z", 0.27, 0.21, SIGN_UV["screen"])
    paint("decor_Till", [("charcoal", box, -0.4, 0.4, 1.05, 1.15, -1.1, -0.7), ("grey", box, -0.3, 0.3, 1.15, 1.25, -1.05, -0.85), ("cream", box, -0.25, 0.25, 1.25, 1.33, -1.0, -0.94),
                         ("black", box, -0.12, 0.12, 1.15, 1.32, -0.78, -0.74)])
    sp = Painter()
    sp.add("chrome", cyl, (1.0, 1.05, -0.9), (1.0, 1.22, -0.9), 0.003, 0.003, 6)
    sp.add("charcoal", cyl, (1.0, 1.05, -0.9), (1.0, 1.065, -0.9), 0.04, 0.04, 12)
    for i in range(9):                                              # the slips on the spike, each a thin card a little turned
        y = 1.07 + i * 0.012
        dx, dz = rng.uniform(-0.012, 0.012, 2)
        sp.add(("slip_y", "slip_p", "paper")[i % 3], box, 1.0 - 0.05 + dx, 1.0 + 0.05 + dx, y, y + 0.002, -0.9 - 0.07 + dz, -0.9 + 0.07 + dz)
    sp.add("charcoal", box, 1.4, 1.75, 1.05, 1.1, -1.12, -0.82)
    for i in range(6):
        sp.add(("slip_y", "paper", "slip_p")[i % 3], box, 1.42 + rng.uniform(-0.01, 0.01), 1.72, 1.1 + i * 0.004, 1.104 + i * 0.004, -1.1, -0.86)
    sp.add("ink", cyl, (2.0, 1.05, -1.0), (2.0, 1.16, -1.0), 0.035, 0.035, 10)
    for i in range(4):
        sp.add(("ink", "red", "black", "blue")[i], cyl, (2.0 + 0.01 * i - 0.015, 1.1, -1.0 + 0.008 * i), (2.0 + 0.02 * i - 0.02, 1.25, -1.0 + 0.01 * i), 0.004, 0.004, 6)
    sp.add("beige", box, 2.55, 2.85, 1.05, 1.11, -1.05, -0.75)
    sp.add("beige", box, 2.57, 2.83, 1.11, 1.15, -1.02, -0.92)
    sp.add("chrome", cyl, (0.6, 1.05, -0.75), (0.6, 1.1, -0.75), 0.04, 0.02, 12)
    sp.done("Desk_items", smooth=False)
    sp = Painter()
    for i in range(7):
        sp.add(("slip_y", "slip_p", "paper")[i % 3], box, 2.5 + rng.uniform(-0.02, 0.02), 2.9, 1.05 + i * 0.003, 1.053 + i * 0.003, 0.2 + i * 0.03, 0.42 + i * 0.03)
    sp.add("chrome", box, 2.48, 2.92, 1.05, 1.12, 0.95, 1.4)
    sp.done("Return_items")
    loose_books("Return_books", [(2.7, 1.2, 1.12, 3, False), (2.68, 0.7, 1.05, 4, False)], rng)
    sign("Orders_sign", "orders", (0.0, 2.35, -0.9), "+z", 2.2, 0.28, depth=0.02, frame="Metal_Dark")
    paint("decor_Orders_hangers", [("chrome", cyl, (x, 2.49, -0.89), (x, H, -0.89), 0.004, 0.004, 6) for x in (-0.9, 0.9)])
    # the back counter: cupboard doors, pigeonholes of order slips, the special-orders shelves over it (wrapped books with slips in them)
    bc = BOX["Back_Counter"]
    part("Back_Counter", "Wood_Desk", lambda bm: [box(bm, bc["min"][0], bc["max"][0], 0.0, 0.86, bc["max"][2] - 0.03, bc["max"][2])]
         + [box(bm, x - 0.006, x + 0.006, 0.08, 0.82, bc["max"][2], bc["max"][2] + 0.008) for x in np.arange(bc["min"][0] + 0.6, bc["max"][0], 0.6)]
         + [box(bm, bc["min"][0], bc["max"][0], 0.0, 0.86, bc["min"][2], bc["max"][2] - 0.03), box(bm, bc["max"][0] - 0.03, bc["max"][0], 0.0, 0.86, bc["min"][2], bc["max"][2])])
    part("Back_Counter_top", "Laminate", lambda bm: box(bm, bc["min"][0], bc["max"][0] + 0.02, 0.86, 0.9, bc["min"][2], bc["max"][2] + 0.02))
    paint("Back_Counter_knobs", [("chrome", box, x - 0.02, x + 0.02, 0.7, 0.74, bc["max"][2] + 0.008, bc["max"][2] + 0.03) for x in np.arange(bc["min"][0] + 0.45, bc["max"][0], 0.6)])
    ph = Painter()
    for i in range(6):
        for j in range(3):
            x0 = -5.4 + i * 0.22
            ph.add("cream", box, x0, x0 + 0.21, 0.92 + j * 0.15, 0.925 + j * 0.15, -3.98, -3.62)
            if rng.random() < 0.7:
                ph.add(("slip_y", "paper", "slip_p")[(i + j) % 3], box, x0 + 0.02, x0 + 0.19, 0.926 + j * 0.15, 0.926 + j * 0.15 + rng.uniform(0.01, 0.05), -3.95, -3.66)
    ph.add("cream", box, -5.42, -4.06, 0.9, 1.38, -4.0, -3.98)
    for i in range(7):
        ph.add("cream", box, -5.42 + i * 0.22, -5.40 + i * 0.22, 0.9, 1.38, -3.98, -3.62)
    ph.done("Back_pigeonholes")
    shelves = Painter()
    for y in (1.4, 1.8, 2.2, 2.6):
        shelves.add("cream", box, bc["min"][0], bc["max"][0], y - 0.025, y, -4.0, -3.78)
    for x in np.linspace(bc["min"][0], bc["max"][0], 6):
        shelves.add("cream", box, x - 0.012, x + 0.012, 1.375, 2.6, -4.0, -3.78)
    shelves.done("Special_Orders_shelf")
    piles = []
    sl = Painter()
    for y in (1.4, 1.8, 2.2):
        x = bc["min"][0] + 0.1
        while x < bc["max"][0] - 0.3:
            kind = rng.random()
            if kind < 0.45:
                piles.append((x + 0.1, -3.89, y, int(rng.integers(2, 6)), False))
                if rng.random() < 0.7:
                    sl.add(("slip_y", "slip_p")[int(rng.integers(2))], box, x + 0.02, x + 0.08, y + 0.05, y + 0.22, -3.79, -3.785)
                x += 0.32
            elif kind < 0.8:
                sl.add("kraft", box, x, x + 0.26, y, y + rng.uniform(0.06, 0.14), -3.97, -3.8)
                sl.add(("slip_y", "slip_p", "paper")[int(rng.integers(3))], box, x + 0.05, x + 0.18, y + 0.02, y + 0.12, -3.795, -3.792)
                x += 0.32
            else:
                x += 0.25
    sl.done("Special_Orders_parcels")
    loose_books("Special_Orders_books", piles, rng)
    # the staff noticeboard and the rota on the stock room's west wall
    nb_x = BOX["Office_Wall_W"]["min"][0]
    sign("Noticeboard", "notice", (nb_x, 1.62, -2.7), "-x", 1.3, 0.9, depth=0.025, frame="Wood_Desk")
    panel("Notice_rota", "Sign_Paint", (nb_x - 0.004, 1.42, -1.85 - 0.12 * 0), "-x", 0.21, 0.28, SIGN_UV["rota"])
    # the queue posts and their rope (passable), the PLEASE WAIT HERE stand
    q = Painter()
    for x in (-4.5, -3.3, -2.1):
        q.add("chrome", cyl, (x, 0.0, 1.65), (x, 0.95, 1.65), 0.025, 0.025, 10)
        q.add("chrome", cyl, (x, 0.0, 1.65), (x, 0.03, 1.65), 0.16, 0.16, 16)
        q.add("chrome", sphere, (x, 0.97, 1.65), 0.04, 10)
    for xa, xb in ((-4.5, -3.3), (-3.3, -2.1)):
        for i in range(8):
            t0, t1 = i / 8, (i + 1) / 8
            ya = 0.88 - 0.14 * math.sin(math.pi * t0)
            yb = 0.88 - 0.14 * math.sin(math.pi * t1)
            q.add("rope", cyl, (xa + (xb - xa) * t0, ya, 1.65), (xa + (xb - xa) * t1, yb, 1.65), 0.012, 0.012, 6)
    q.done("decor_Queue", smooth=True)
    paint("decor_wait_stand", [("chrome", cyl, (-5.0, 0.0, 1.0), (-5.0, 1.2, 1.0), 0.015, 0.015, 8), ("chrome", cyl, (-5.0, 0.0, 1.0), (-5.0, 0.02, 1.0), 0.15, 0.15, 14)], smooth=True)
    panel("decor_wait_sign", "Sign_Paint", (-5.0, 1.32, 1.02), "+z", 0.3, 0.15, SIGN_UV["wait"])
    # the returns trolley under a half-pulled sheet
    rt = BOX["Sheeted_Returns_Trolley"]
    x0, x1, z0, z1, hh = rt["min"][0], rt["max"][0], rt["min"][2], rt["max"][2], rt["max"][1]
    part("Returns_Trolley", "Metal_Steel", lambda bm: [box(bm, x0, x1, 0.12, 0.15, z0, z1), box(bm, x0, x1, 0.55, 0.58, z0, z1)]
         + [box(bm, x - 0.012, x + 0.012, 0.08, hh - 0.05, z - 0.012, z + 0.012) for x in (x0 + 0.02, x1 - 0.02) for z in (z0 + 0.02, z1 - 0.02)])
    paint("Returns_Trolley_wheels", [("rubber", cyl, (x, 0.0, z), (x, 0.08, z), 0.035, 0.035, 10) for x in (x0 + 0.05, x1 - 0.05) for z in (z0 + 0.06, z1 - 0.06)])
    loose_books("Returns_books", [(x0 + 0.2, z0 + 0.25, 0.58, 4, False), (x0 + 0.55, z0 + 0.3, 0.58, 3, False), (x0 + 0.3, z0 + 0.7, 0.15, 5, False)], rng)
    part("Returns_sheet", "Cloth_Sheet", lambda bm: drape(bm, x0 - 0.005, x1 + 0.005, (z0 + z1) / 2 - 0.05, z1 + 0.005, hh, rng, y_hem=0.35, n=6), recalc=False)
    # the stock room: the packing table with cartons, the filing cabinet, the steel rack of cartons and book piles, a carton or two on the floor
    od, fc, sr = BOX["Office_Desk"], BOX["Filing_Cabinet"], BOX["Stock_Rack"]
    part("Office_Desk", "Wood_Light", lambda bm: [box(bm, od["min"][0], od["max"][0], od["max"][1] - 0.03, od["max"][1], od["min"][2], od["max"][2])]
         + [box(bm, x - 0.025, x + 0.025, 0.0, od["max"][1] - 0.03, z - 0.025, z + 0.025) for x in (od["min"][0] + 0.04, od["max"][0] - 0.04)
            for z in (od["min"][2] + 0.04, od["max"][2] - 0.04)])
    yt = od["max"][1]
    paint("Office_cartons", [("kraft", box, 4.5, 4.95, yt, yt + 0.3, -3.75, -3.35), ("card", box, 5.0, 5.55, yt, yt + 0.22, -3.72, -3.3), ("kraft", box, 4.6, 4.9, yt + 0.3, yt + 0.48, -3.7, -3.42),
                             ("tape", box, 4.5, 4.95, yt + 0.3, yt + 0.305, -3.57, -3.53), ("charcoal", box, 5.2, 5.4, yt, yt + 0.08, -3.2, -3.06)])
    paint("Filing_Cabinet", [("steel_dk", box, fc["min"][0], fc["max"][0], 0.0, fc["max"][1], fc["min"][2], fc["max"][2])]
          + [("chrome", box, fc["min"][0] + 0.18, fc["max"][0] - 0.18, y, y + 0.03, fc["max"][2], fc["max"][2] + 0.02) for y in (0.25, 0.57, 0.89, 1.17)])
    part("Stock_Rack", "Metal_Steel", lambda bm: [box(bm, sr["min"][0], sr["max"][0], y - 0.02, y, sr["min"][2], sr["max"][2]) for y in (0.12, 0.62, 1.12, 1.62, 2.12)]
         + [box(bm, x - 0.015, x + 0.015, 0.0, sr["max"][1], z - 0.015, z + 0.015) for x in (sr["min"][0] + 0.015, sr["max"][0] - 0.015) for z in (sr["min"][2] + 0.015, sr["max"][2] - 0.015)])
    rk = Painter()
    for y in (0.12, 0.62, 1.12, 1.62, 2.12):
        z = sr["min"][2] + 0.05
        while z < sr["max"][2] - 0.25:
            dz = rng.uniform(0.25, 0.4)
            if rng.random() < 0.8:
                rk.add(("kraft", "card")[int(rng.integers(2))], box, sr["min"][0] + 0.02, sr["max"][0] - 0.02, y, y + rng.uniform(0.18, min(0.42, 0.46 if y < 2 else 0.25)), z, min(sr["max"][2] - 0.03, z + dz))
            z += dz + 0.03
    rk.done("Stock_Rack_cartons")
    paint("decor_floor_cartons", [("kraft", box, 3.4, 3.9, 0.0, 0.35, -2.5, -2.0), ("card", box, 3.45, 3.85, 0.35, 0.55, -2.45, -2.1), ("tape", box, 3.4, 3.9, 0.35, 0.352, -2.27, -2.23)])
    for i, (x, z, sx, sz) in enumerate(((-2.0, -2.4, 2.4, 0.6), (4.6, -2.6, 0.9, 0.8), (-4.0, 3.0, 1.6, 0.6), (5.2, 2.5, 0.8, 1.2))):
        dust(f"{i}", x, z, sx, sz)
    exit_sign("Exit_W", "+x", 2.0, 2.5)
    for k, (x, z) in enumerate(((-3.6, 2.2), (0.0, 2.2), (-3.6, -2.2), (0.0, -2.3), (2.0, 1.2))):
        troffer(x, z, H, k != 2, along_x=True)
    part("Stock_batten", "Plastic_White", lambda bm: box(bm, 4.0, 5.4, H - 0.08, H, -2.86, -2.74))
    part("Stock_batten_tube", "Lamp_Emit", lambda bm: cyl(bm, (4.05, H - 0.1, -2.8), (5.35, H - 0.1, -2.8), 0.016, 0.016, 10), smooth=True)
    light("day", "AREA", (4.7, H - 0.13, -2.8), 50.0, COOL, size=1.2, size_y=0.08, aim=(0, -1, 0))
    emergency_head("Emerg_N", "+z", -1.6, 2.7)
    emergency_head("Emerg_S", "-z", 1.0, 2.7)
    ceiling_head("Emerg_stock", 4.6, -2.2, H)


def cinema_lobby():
    rng = np.random.default_rng(303)
    global SEEN_UP
    SEEN_UP = 4.7
    build_floor([("Floor_Vinyl", -7.0, 7.0, Z0, -6.8)], "Carpet_Cinema")
    build_walls(lower="Wall_Fabric", upper="Wall_Paint", dado=2.7, skirting="Trim_Dark")
    build_ceiling("Ceiling_Dark")
    door_frames("Brass", lining="Trim_Dark")
    build_leaves({"DoorLeaf_wing_cinema": ("glass", "bar")})
    # the balcony: its slab, carpet, the brass-edged fascia with CONCESSIONS on it, a solid balustrade with NOW SHOWING, the soffit's downlights
    bs = BOX["Balcony_Slab"]
    part("Balcony_slab", "Ceiling_Paint", lambda bm: box(bm, bs["min"][0], bs["max"][0], bs["min"][1], bs["max"][1] - 0.02, bs["min"][2], bs["max"][2]))
    part("Balcony_carpet", "Carpet_Cinema", lambda bm: box(bm, bs["min"][0], bs["max"][0], bs["max"][1] - 0.02, bs["max"][1], bs["min"][2], bs["max"][2] - 0.1))
    part("Balcony_fascia_brass", "Brass", lambda bm: [box(bm, bs["min"][0], bs["max"][0], 2.68, 2.72, bs["max"][2] - 0.01, bs["max"][2] + 0.02),
                                                      box(bm, bs["min"][0], bs["max"][0], 2.97, 3.0, bs["max"][2] - 0.01, bs["max"][2] + 0.02)])
    sign("Concessions_sign", "concess", (0.0, 2.845, bs["max"][2]), "+z", 3.6, 0.24, depth=0.0)
    for nr in ("Balcony_Rail", "Balcony_Rail_2"):
        b = BOX[nr]
        part(f"{nr}_panel", "Wall_Fabric", lambda bm, b=b: box(bm, b["min"][0], b["max"][0], b["min"][1], b["max"][1] - 0.08, b["min"][2] + 0.01, b["max"][2] - 0.01))
        part(f"{nr}_cap", "Brass", lambda bm, b=b: [cyl(bm, (b["min"][0], b["max"][1] - 0.04, (b["min"][2] + b["max"][2]) / 2), (b["max"][0], b["max"][1] - 0.04, (b["min"][2] + b["max"][2]) / 2), 0.045, 0.045, 12),
                                                    box(bm, b["min"][0], b["max"][0], b["min"][1], b["min"][1] + 0.05, b["min"][2], b["max"][2])], smooth=True)
    sign("Nowshowing", "nowshow", (-1.5, 3.5, BOX["Balcony_Rail"]["max"][2]), "+z", 15.0, 0.36, depth=0.0)
    for x in (-10.5, -6.0, -2.0, 2.0, 6.0):
        downlight(x, -6.45, 2.7, x != -2.0, power=SOFFIT_W, cone=110, r=0.07)
    # the stair: carpet treads with brass nosings over painted risers (each piece under 0.2 m), its dwarf wall, the closed underside (passable art)
    steps = sorted((n, b) for n, b in BOX.items() if n.startswith("Step_balcony_"))
    for n, b in steps:
        x0, x1, y0, y1, z0, z1 = b["min"][0], b["max"][0], b["min"][1], b["max"][1], b["min"][2], b["max"][2]
        part(f"Stair_{n}_tread", "Carpet_Cinema", lambda bm, b=b: box(bm, x0, x1, y1 - 0.045, y1, z0, z1))
        part(f"Stair_{n}_nose", "Brass", lambda bm, b=b: box(bm, x0, x1, y1 - 0.05, y1 + 0.004, z1 - 0.03, z1 + 0.004))
        part(f"Stair_{n}_body", "Trim_Dark", lambda bm, b=b: box(bm, x0 + 0.005, x1 - 0.005, y0 + 0.01, y1 - 0.045, z0, z1))     # under 0.2 m tall
    sw = BOX["Stair_Wall"]
    part("Stair_Wall", "Wall_Fabric", lambda bm: box(bm, sw["min"][0], sw["max"][0], 0.0, sw["max"][1] - 0.05, sw["min"][2], sw["max"][2]))
    part("Stair_Wall_cap", "Brass", lambda bm: box(bm, sw["min"][0] - 0.01, sw["max"][0] + 0.01, sw["max"][1] - 0.05, sw["max"][1], sw["min"][2], sw["max"][2]))
    xs0, xs1 = steps[0][1]["min"][0], steps[0][1]["max"][0]
    zs0, zs1 = steps[0][1]["max"][2], steps[-1][1]["min"][2]

    def underside(bm):                                              # the stair's side closed over its dwarf wall, up to each step's foot (faces the lobby, -x)
        for n, b in steps:
            yb, zf, zb = b["min"][1] + 0.01, b["max"][2], b["min"][2]
            if yb > 0.99:
                bm.faces.new([bm.verts.new(B(p)) for p in ((9.5, 0.98, zf), (9.5, yb, zf), (9.5, yb, zb), (9.5, 0.98, zb))])
    part("decor_stair_side", "Trim_Dark", underside, recalc=False)
    part("decor_stair_rail", "Brass", lambda bm: [cyl(bm, (11.95, 0.95, zs0), (11.95, 3.9, zs1), 0.025, 0.025, 10)]
         + [cyl(bm, (11.995, 0.95 + (2.95 * t), zs0 + (zs1 - zs0) * t), (11.95, 0.95 + 2.95 * t, zs0 + (zs1 - zs0) * t), 0.01, 0.01, 6) for t in (0.1, 0.5, 0.9)], smooth=True)
    uc = BOX["Understair_Cupboard"]
    part("Understair_Cupboard", "Wall_Fabric", lambda bm: box(bm, uc["min"][0], uc["max"][0], 0.0, uc["max"][1], uc["min"][2], uc["max"][2]))
    paint("Understair_door", [("charcoal", box, uc["min"][0] - 0.03, uc["min"][0], 0.0, 2.1, -7.0, -6.1), ("brass", box, uc["min"][0] - 0.042, uc["min"][0] - 0.03, 1.0, 1.04, -6.25, -6.15)])
    sign("Understair_sign", "staff", (uc["min"][0] - 0.03, 2.25, -6.55), "-x", 0.42, 0.14, depth=0.0)
    # the screen doors: padded double doors with portholes and push plates, chained shut, a lit-box sign over each; 1 and 2 below, 3 and 4 on the
    # balcony; the fifth door on the balcony is the projection room's
    def screen_door(cn, key, padded=True):
        b = BOX[cn]
        x0, x1, y0, y1, z0, z1 = b["min"][0], b["max"][0], b["min"][1], b["max"][1], b["min"][2], b["max"][2]
        alongx = (x1 - x0) > (z1 - z0)
        if alongx:
            nm, face, a0, a1 = "+z", z0, x0, x1
        else:
            nm, face, a0, a1 = ("+x", x0, z0, z1) if abs(x0 - X0) < 1e-3 else ("-x", x1, z0, z1)
        am = (a0 + a1) / 2
        part(f"{cn}_leaves", "Fabric_Padded" if padded else "Metal_Steel",
             lambda bm: [wall_box(bm, nm, a0 + 0.04, am - 0.008, y0, y1 - 0.06, 0.0, 0.055), wall_box(bm, nm, am + 0.008, a1 - 0.04, y0, y1 - 0.06, 0.0, 0.055)])
        part(f"{cn}_frame", "Brass" if padded else "Metal_Dark", lambda bm: [wall_box(bm, nm, a0, a0 + 0.04, y0, y1, 0.0, 0.06), wall_box(bm, nm, a1 - 0.04, a1, y0, y1, 0.0, 0.06),
                                                                           wall_box(bm, nm, a0, a1, y1 - 0.06, y1, 0.0, 0.06)])
        hw = Painter()
        for sg in (-1, 1):
            ac = am + sg * 0.38
            if padded:
                p = Vector(on_wall(nm, ac, y0 + 1.55, 0.056, face))
                hw.add("glass_dk", cyl, tuple(p - Vector(NORMAL[nm]) * 0.002), tuple(p + Vector(NORMAL[nm]) * 0.004), 0.12, 0.12, 16)
                hw.add("brass", cyl, tuple(p - Vector(NORMAL[nm]) * 0.003), tuple(p + Vector(NORMAL[nm]) * 0.002), 0.14, 0.14, 16)
            hw.add("brass" if padded else "chrome", wall_box, nm, am + sg * 0.05 - 0.035, am + sg * 0.05 + 0.035, y0 + 0.9, y0 + 1.25, 0.055, 0.065, face)
        hw.add("chrome", wall_box, nm, am - 0.12, am + 0.12, y0 + 1.04, y0 + 1.06, 0.065, 0.085, face)       # the chain across the plates, and its padlock
        hw.add("brass", wall_box, nm, am - 0.025, am + 0.025, y0 + 0.95, y0 + 1.03, 0.07, 0.095, face)
        hw.done(f"{cn}_hw", smooth=False)
        sign(f"{cn}_sign", key, on_wall(nm, am, y1 + 0.2, 0.0, face), nm, 0.78, 0.24, depth=0.05)
    for cn, key in (("Screen_1_Door", "screen1"), ("Screen_2_Door", "screen2"), ("Screen_3_Door", "screen3"), ("Screen_4_Door", "screen4")):
        screen_door(cn, key)
    screen_door("Screen_5_Door", "proj", padded=False)
    # the concession stand: a long counter (starred panels, a steel top), glass candy cases, the popcorn machine, a drinks fountain, tills, cups
    cc, bk = BOX["Concession_Counter"], BOX["Back_Counter"]
    x0, x1, z0, z1, hh = cc["min"][0], cc["max"][0], cc["min"][2], cc["max"][2], cc["max"][1]
    part("Concession_body", "Trim_Dark", lambda bm: [box(bm, x0, x1, 0.0, hh - 0.05, z0, z1 - 0.03), box(bm, x0, x1, 0.0, 0.12, z1 - 0.03, z1)])
    for i, xa in enumerate(np.arange(x0, x1 - 0.01, 1.75)):
        panel(f"Concession_panel_{i}", "Sign_Paint", (xa + 0.875, 0.6, z1 - 0.0), "+z", 1.69, 0.9, SIGN_UV["counter"])
    part("Concession_top", "Metal_Steel", lambda bm: box(bm, x0 - 0.02, x1 + 0.02, hh - 0.05, hh, z0, z1 + 0.04))
    pc = Painter()
    for k, xc in enumerate((-5.8, -3.6)):                          # the candy cases' contents (the glass is Glass_Clear)
        for i in range(10):
            pc.add(("candy_a", "candy_b", "candy_c", "pink", "orange")[(i + k) % 5], box, xc - 0.8 + i * 0.16, xc - 0.66 + i * 0.16, hh + 0.02, hh + 0.2,
                   z0 + 0.12 + (i % 2) * 0.22, z0 + 0.3 + (i % 2) * 0.22)
        pc.add("chrome", box, xc - 0.92, xc + 0.92, hh, hh + 0.02, z0 + 0.05, z1 - 0.05)
    pc.done("Concession_candy")
    part("Concession_candy_glass", "Glass_Clear", lambda bm: [box(bm, xc - 0.92, xc + 0.92, hh + 0.02, hh + 0.42, z0 + 0.05, z1 - 0.05) for xc in (-5.8, -3.6)])
    px, pz = 4.9, (z0 + z1) / 2                                    # the popcorn machine: a red cart top, a glass cabinet, the kettle, a mound of corn
    pm = Painter()
    pm.add("red", box, px - 0.45, px + 0.45, hh, hh + 0.12, pz - 0.34, pz + 0.34)
    for sx in (-1, 1):
        for sz in (-1, 1):
            pm.add("red", box, px + sx * 0.45 - 0.03, px + sx * 0.45 + 0.03, hh + 0.12, hh + 0.92, pz + sz * 0.34 - 0.03, pz + sz * 0.34 + 0.03)
    pm.add("red", box, px - 0.5, px + 0.5, hh + 0.92, hh + 1.02, pz - 0.38, pz + 0.38)
    pm.add("yellow", box, px - 0.36, px + 0.36, hh + 1.02, hh + 1.07, pz - 0.26, pz + 0.26)
    pm.add("popcorn", sphere, (px, hh + 0.12, pz), 0.29, 14, 0.6)
    pm.add("chrome", cyl, (px, hh + 0.92, pz), (px, hh + 0.72, pz), 0.012, 0.012, 6)
    pm.add("chrome", cyl, (px, hh + 0.72, pz), (px, hh + 0.56, pz), 0.17, 0.14, 16)
    pm.add("kernel", sphere, (px, hh + 0.6, pz), 0.12, 10, 0.5)
    pm.done("Popcorn_machine", smooth=False)
    part("Popcorn_glass", "Glass_Clear", lambda bm: box(bm, px - 0.43, px + 0.43, hh + 0.12, hh + 0.92, pz - 0.32, pz + 0.32))
    panel("Popcorn_sign", "Sign_Paint", (px, hh + 0.97, pz + 0.385), "+z", 0.8, 0.09, SIGN_UV["popcorn"])
    fx = -1.2                                                       # the drinks fountain and its cups
    dp = Painter()
    dp.add("steel_dk", box, fx - 0.5, fx + 0.5, hh, hh + 0.65, z0 + 0.04, z0 + 0.4)
    dp.add("chrome", box, fx - 0.48, fx + 0.48, hh, hh + 0.04, z0 + 0.4, z1 - 0.05)
    for i in range(4):
        dp.add("chrome", cyl, (fx - 0.36 + i * 0.24, hh + 0.42, z0 + 0.42), (fx - 0.36 + i * 0.24, hh + 0.34, z0 + 0.42), 0.02, 0.016, 8)
    for i in range(6):
        dp.add(("white", "red", "white", "blue", "white", "red")[i], cyl, (1.0 + i * 0.13, hh, z0 + 0.2), (1.0 + i * 0.13, hh + 0.35 + 0.02 * (i % 3), z0 + 0.2), 0.045, 0.055, 12)
    for xr in (-3.0 + 0.6 * 0, 2.6):                                 # two tills
        dp.add("charcoal", box, xr - 0.22, xr + 0.22, hh, hh + 0.1, z0 + 0.25, z0 + 0.6)
        dp.add("grey", box, xr - 0.16, xr + 0.16, hh + 0.1, hh + 0.34, z0 + 0.3, z0 + 0.36)
    dp.add("napkin", box, -6.95 + 0.25, -6.95 + 0.45, hh, hh + 0.14, z1 - 0.3, z1 - 0.15)
    dp.done("Concession_items", smooth=False)
    for i in range(4):
        panel(f"Fountain_logo_{i}", "Sign_Paint", (fx - 0.36 + i * 0.24, hh + 0.55, z0 + 0.402), "+z", 0.18, 0.18, SIGN_UV["fizz"])
    part("Back_Counter", "Trim_Dark", lambda bm: box(bm, bk["min"][0], bk["max"][0], 0.0, bk["max"][1] - 0.04, bk["min"][2], bk["max"][2]))
    part("Back_Counter_top", "Metal_Steel", lambda bm: box(bm, bk["min"][0], bk["max"][0], bk["max"][1] - 0.04, bk["max"][1], bk["min"][2], bk["max"][2] + 0.02))
    paint("Back_Counter_items", [("chrome", box, -5.5, -4.9, bk["max"][1], bk["max"][1] + 0.25, -7.98, -7.62), ("glass_dk", box, -5.48, -4.92, bk["max"][1] + 0.06, bk["max"][1] + 0.22, -7.62, -7.61),
                                 ("chrome", box, 3.0, 3.7, bk["max"][1], bk["max"][1] + 0.16, -7.95, -7.65), ("kernel", box, 3.05, 3.65, bk["max"][1] + 0.16, bk["max"][1] + 0.19, -7.9, -7.7),
                                 ("kraft", box, 0.5, 1.0, bk["max"][1], bk["max"][1] + 0.3, -7.98, -7.65), ("card", box, 1.05, 1.4, bk["max"][1], bk["max"][1] + 0.22, -7.97, -7.7),
                                 ("white", cyl, (-1.8, bk["max"][1], -7.8), (-1.8, bk["max"][1] + 0.5, -7.8), 0.05, 0.06, 12)])
    for i, (key, xm) in enumerate((("menu_pop", -4.2), ("menu_drink", 0.0), ("menu_snack", 4.2))):
        sign(f"Menu_{key}", key, (xm, 2.2, Z0), "+z", 1.2, 0.8, depth=0.03, frame="Metal_Dark")
        light("day", "AREA", (xm, 2.62, Z0 + 0.35), 12.0, WARM, size=1.2, size_y=0.1, aim=(0, -0.5, -0.86))
    part("Menu_lamps", "Lamp_Emit", lambda bm: [box(bm, xm - 0.6, xm + 0.6, 2.63, 2.66, Z0 + 0.05, Z0 + 0.12) for xm in (-4.2, 0.0, 4.2)])
    # the drinks fridge: a red cabinet, COLD DRINKS, its glass door onto shelves of bottles and cans, the light inside
    df = BOX["Drinks_Fridge"]
    x0, x1, z0, z1, hh = df["min"][0], df["max"][0], df["min"][2], df["max"][2], df["max"][1]
    part("Drinks_Fridge", "Plastic_White", lambda bm: [box(bm, x0, x1, 0.0, hh, z0, z1 - 0.06), box(bm, x0, x0 + 0.05, 0.0, hh, z1 - 0.06, z1), box(bm, x1 - 0.05, x1, 0.0, hh, z1 - 0.06, z1),
                                                     box(bm, x0, x1, 0.0, 0.12, z1 - 0.06, z1), box(bm, x0, x1, hh - 0.26, hh, z1 - 0.06, z1)])
    panel("Fridge_header", "Sign_Paint", ((x0 + x1) / 2, hh - 0.13, z1 + 0.001), "+z", 0.9, 0.19, SIGN_UV["cold"])
    fr = Painter()
    for y in (0.3, 0.72, 1.14, 1.56):
        fr.add("chrome", box, x0 + 0.05, x1 - 0.05, y - 0.015, y, z0 + 0.05, z1 - 0.08)
        for i in range(8):
            xb = x0 + 0.1 + i * 0.105
            c = ("bottle_a", "bottle_b", "bottle_c", "bottle_d")[(i + int(y * 10)) % 4]
            if rng.random() < 0.8:
                fr.add(c, cyl, (xb, y, z1 - 0.2), (xb, y + (0.3 if y < 1.5 else 0.14), z1 - 0.2), 0.032, 0.03, 8)
    fr.done("Fridge_stock", smooth=False)
    part("Fridge_glass", "Glass_Clear", lambda bm: box(bm, x0 + 0.05, x1 - 0.05, 0.12, hh - 0.26, z1 - 0.03, z1 - 0.02))
    part("Fridge_lamp", "Lamp_Emit", lambda bm: box(bm, x0 + 0.08, x1 - 0.08, hh - 0.3, hh - 0.28, z1 - 0.12, z1 - 0.07))
    light("day", "AREA", ((x0 + x1) / 2, hh - 0.32, z1 - 0.15), FRIDGE_W, COOL, size=0.8, size_y=0.1, aim=(0, -1, 0))
    # the box office: a panelled booth, three ticket windows with their blinds down and a CLOSED card, speaker grilles, its sign
    bo = BOX["Box_Office"]
    x0, x1, z0, z1, hh = bo["min"][0], bo["max"][0], bo["min"][2], bo["max"][2], bo["max"][1]
    HIDDEN.append((x0 + 0.06, x1 - 0.06, 0.02, hh - 0.06, z0 + 0.06, z1 - 0.06))
    part("Box_Office_lower", "Wall_Fabric", lambda bm: [box(bm, x0, x1, 0.0, 1.0, z0, z1), box(bm, x0, x1 - 0.06, 1.0, hh, z0, z1)])
    part("Box_Office_frame", "Brass", lambda bm: [box(bm, x1 - 0.06, x1, 1.0, hh, z, z + 0.06) for z in np.linspace(z0, z1 - 0.06, 4)]
         + [box(bm, x1 - 0.07, x1, 0.98, 1.04, z0, z1), box(bm, x1 - 0.06, x1, hh - 0.3, hh - 0.26, z0, z1)])
    part("Box_Office_roof", "Trim_Dark", lambda bm: box(bm, x0 - 0.03, x1 + 0.03, hh - 0.04, hh, z0 - 0.03, z1 + 0.03))
    part("Box_Office_glass", "Glass_Clear", lambda bm: box(bm, x1 - 0.04, x1 - 0.03, 1.04, hh - 0.3, z0 + 0.06, z1 - 0.06))
    bl = Painter()
    for k, z in enumerate(np.linspace(z0, z1 - 0.06, 4)[:-1]):
        zc = z + (z1 - z0 - 0.06) / 6 + 0.03
        bl.add("beige", box, x1 - 0.06, x1 - 0.055, 1.04 + (0.0 if k != 1 else 0.6), hh - 0.3, z + 0.06, z + (z1 - z0 - 0.06) / 3)
        bl.add("charcoal", cyl, (x1 - 0.06, 1.75, zc), (x1 - 0.045, 1.75, zc), 0.07, 0.07, 14)
        bl.add("chrome", box, x1 - 0.06, x1 + 0.04, 1.04, 1.06, zc - 0.2, zc + 0.2)
    bl.done("Box_Office_blinds")
    panel("Box_Office_closed", "Sign_Paint", (x1 - 0.048, 1.35, z0 + 0.5), "+x", 0.3, 0.15, SIGN_UV["closed"])
    sign("Box_Office_sign_E", "boxoffice", (x1, hh - 0.14, (z0 + z1) / 2), "+x", 2.6, 0.22, depth=0.0)
    sign("Box_Office_sign_N", "boxoffice", ((x0 + x1) / 2, hh - 0.14, z0), "-z", 2.6, 0.22, depth=0.0)
    q = Painter()                                                   # the queue's belt barriers (passable)
    for z in (3.95, 5.0, 6.05, 7.1):
        q.add("chrome", cyl, (-5.15, 0.0, z), (-5.15, 0.95, z), 0.03, 0.03, 10)
        q.add("chrome", cyl, (-5.15, 0.0, z), (-5.15, 0.03, z), 0.17, 0.17, 16)
    for za, zb in ((3.95, 5.0), (5.0, 6.05), (6.05, 7.1)):
        q.add("belt", box, -5.16, -5.14, 0.86, 0.91, za, zb)
    q.done("decor_queue", smooth=True)
    # the standee under its sheet; the poster cases (each lit from inside by day); the balcony's sconces
    st = BOX["Sheeted_Cardboard_Standee"]
    x0, x1, z0, z1, hh = st["min"][0], st["max"][0], st["min"][2], st["max"][2], st["max"][1]
    part("Standee_sheet", "Cloth_Sheet", lambda bm: drape(bm, x0, x1, z0, z1, hh, rng, y_hem=0.0, fold=0.02, n=12), recalc=False)
    cases = [("+x", 1.2, 1.7, 0), ("+x", 6.2, 1.7, 1), ("-x", 0.0, 1.7, 2), ("-x", 6.0, 1.7, 3), ("-z", -6.5, 1.7, 4), ("-z", -3.4, 1.7, 5),
             ("-z", 3.4, 1.7, 6), ("-z", 6.5, 1.7, 7)]
    for nm, a, y, i in cases:
        part(f"Poster_case_{i}", "Metal_Dark", lambda bm, nm=nm, a=a, y=y: [wall_box(bm, nm, a - 0.55, a + 0.55, y - 0.78, y - 0.72, 0.0, 0.045), wall_box(bm, nm, a - 0.55, a + 0.55, y + 0.72, y + 0.78, 0.0, 0.045),
                                                                         wall_box(bm, nm, a - 0.55, a - 0.49, y - 0.72, y + 0.72, 0.0, 0.045), wall_box(bm, nm, a + 0.49, a + 0.55, y - 0.72, y + 0.72, 0.0, 0.045),
                                                                         wall_box(bm, nm, a - 0.49, a + 0.49, y - 0.72, y + 0.72, 0.0, 0.01)])
        panel(f"Poster_{i}", "Poster_Print", on_wall(nm, a, y, 0.012), nm, 0.96, 1.42, poster_uv(i))
        part(f"Poster_lamp_{i}", "Lamp_Emit", lambda bm, nm=nm, a=a, y=y: wall_box(bm, nm, a - 0.45, a + 0.45, y + 0.68, y + 0.71, 0.02, 0.04))
        nv = Vector(NORMAL[nm])
        light("day", "AREA", tuple(Vector(on_wall(nm, a, y + 0.66, 0.05)) - Vector((0, 0.01, 0))), POSTER_W, WARM, size=0.85, size_y=0.04, aim=tuple((nv * 0.3 - Vector((0, 1, 0))).normalized()))
    for x in (-10.4, -5.0, 1.0, 6.2):
        c = on_wall("+z", x, 4.55, 0.0)
        part(f"Sconce_{x:.0f}", "Lamp_Emit", lambda bm, x=x: wall_box(bm, "+z", x - 0.14, x + 0.14, 4.4, 4.75, 0.0, 0.09))
        part(f"Sconce_{x:.0f}_cap", "Brass", lambda bm, x=x: [wall_box(bm, "+z", x - 0.15, x + 0.15, 4.75, 4.79, 0.0, 0.1), wall_box(bm, "+z", x - 0.15, x + 0.15, 4.36, 4.4, 0.0, 0.1)])
        light("day", "POINT", (x, 4.58, Z0 + 0.2), SCONCE_W, WARM, size=0.08)
    for i, (x, z, sx, sz) in enumerate(((0.0, 5.0, 2.5, 1.5), (-4.4, 5.0, 0.6, 1.8), (6.0, -4.2, 2.0, 0.8), (-9.0, 1.0, 1.5, 3.0), (0.0, -7.2, 3.0, 0.3))):
        dust(f"{i}", x, z, sx, sz)
    # the ceiling's cans (two dead), the emergency heads and EXIT signs
    for i, x in enumerate((-9.0, -4.5, 0.0, 4.5, 9.0)):
        for j, z in enumerate((-2.6, 1.6, 5.6)):
            downlight(x, z, H, (i, j) not in {(1, 1), (4, 2)})
    for j, x in enumerate((-9.0, -4.5, 0.0, 4.5)):
        downlight(x, -6.5, H, j != 2, power=CAN_W * 0.6)
    exit_sign("Exit_S", "-z", 0.0, 3.0)
    exit_sign("Exit_stair", "-x", -4.2, 4.6)
    emergency_head("Emerg_S_W", "-z", -5.0, 3.2)
    emergency_head("Emerg_S_E", "-z", 5.0, 3.2)
    emergency_head("Emerg_W", "+x", 3.5, 3.2)
    emergency_head("Emerg_E", "-x", 6.5, 3.2)
    emergency_head("Emerg_bal_W", "+z", -9.0, 5.7)
    emergency_head("Emerg_bal_E", "+z", 1.0, 5.7)
    ceiling_head("Emerg_soffit", -8.5, -6.5, 2.7)
    ceiling_head("Emerg_soffit_2", 8.0, -6.2, 2.7)


def food_court():
    rng = np.random.default_rng(404)
    band = [("Floor_Border", -15.0, 12.1, -9.5, -7.55), ("Floor_Border", 10.1, 12.1, -9.5, 8.1)]
    build_floor(band + [("Floor_Concrete", -13.9, 9.9, -12.2, -9.6), ("Floor_Concrete", 12.2, 15.2, -7.9, 7.9)], "Floor_Terrazzo")
    build_walls(lower="Wall_Tile", upper="Wall_Paint", dado=1.2)
    SKY = (-9.5, 6.5, -4.0, 4.0)
    build_ceiling("Ceiling_Paint", holes=[SKY])
    door_frames("Metal_Steel", lining="Metal_Steel")
    build_leaves({"DoorLeaf_wing_entertainment": ("glass", "bar"), "DoorLeaf_entrance": ("glass", "bar"), "DoorLeaf_service_corridor": ("steel", "lever")})
    HIDDEN.append((-13.9, 9.9, -0.01, 6.01, -12.0 - 0.01, -9.6 + 0.001))
    HIDDEN.append((12.2 - 0.001, 15.01, -0.01, 6.01, -7.9, 7.9))
    # the skylight: a lantern over the ceiling's opening, its glazed upstand and pitched roof of wired glass (the panes' lightmap is filled flat)
    sx0, sx1, sz0, sz1 = SKY
    UP, RIDGE = 0.8, 1.4
    y0 = H + 0.2

    def frames(bm):
        for x in np.linspace(sx0, sx1, 9):
            box(bm, x - 0.04, x + 0.04, y0, y0 + UP, sz0 - 0.04, sz0 + 0.04)
            box(bm, x - 0.04, x + 0.04, y0, y0 + UP, sz1 - 0.04, sz1 + 0.04)
        for z in np.linspace(sz0, sz1, 5):
            box(bm, sx0 - 0.04, sx0 + 0.04, y0, y0 + UP, z - 0.04, z + 0.04)
            box(bm, sx1 - 0.04, sx1 + 0.04, y0, y0 + UP, z - 0.04, z + 0.04)
        box(bm, sx0, sx1, y0 + UP - 0.06, y0 + UP, sz0 - 0.05, sz0 + 0.05)
        box(bm, sx0, sx1, y0 + UP - 0.06, y0 + UP, sz1 - 0.05, sz1 + 0.05)
        box(bm, sx0, sx1, y0 + UP + RIDGE - 0.05, y0 + UP + RIDGE + 0.03, -0.05, 0.05)
        for x in np.linspace(sx0, sx1, 9):
            for zz in (sz0, sz1):
                cyl(bm, (x, y0 + UP, zz), (x, y0 + UP + RIDGE, 0.0), 0.035, 0.035, 6)
        box(bm, sx0 - 0.2, sx1 + 0.2, H, y0, sz0 - 0.2, sz0)
        box(bm, sx0 - 0.2, sx1 + 0.2, H, y0, sz1, sz1 + 0.2)
        box(bm, sx0 - 0.2, sx0, H, y0, sz0, sz1)
        box(bm, sx1, sx1 + 0.2, H, y0, sz0, sz1)
    part("Skylight_frame", "Metal_Steel", frames)

    def panes(bm):
        for z in (sz0, sz1):
            quad(bm, (sx0, y0, z), (sx1, y0, z), (sx1, y0 + UP, z), (sx0, y0 + UP, z))
        for x in (sx0, sx1):
            quad(bm, (x, y0, sz0), (x, y0, sz1), (x, y0 + UP, sz1), (x, y0 + UP, sz0))
        for zz in (sz0, sz1):
            quad(bm, (sx0, y0 + UP, zz), (sx1, y0 + UP, zz), (sx1, y0 + UP + RIDGE, 0.0), (sx0, y0 + UP + RIDGE, 0.0))
        for x in (sx0, sx1):
            bm.faces.new([bm.verts.new(B(p)) for p in ((x, y0 + UP, sz0), (x, y0 + UP, sz1), (x, y0 + UP + RIDGE, 0.0))])
        cx, cz = (sx0 + sx1) / 2, 0.0
        bm.normal_update()
        cb = B((cx, y0 + 0.4, cz))
        for f in bm.faces:
            if f.normal.dot(f.calc_center_median() - cb) > 0:
                f.normal_flip()
    part("Skylight_panes", "Skylight_Glass", panes, recalc=False)
    # the stalls: partitions clad in steel, counters in each stall's colour, shutters down, the menu boards and the name signs, a bulkhead over all
    north = sorted([(b["min"][0], n) for n, b in BOX.items() if n.startswith("Stall_Counter") and b["max"][2] < -9.0])
    east = sorted([(b["min"][2], n) for n, b in BOX.items() if n.startswith("Stall_Counter") and b["min"][0] > 11.0])
    stalls = [(n, "+z") for _, n in north] + [(n, "-x") for _, n in east]
    for n, b in BOX.items():
        if n.startswith("Stall_Partition"):
            part(f"{n}", "Wall_Paint", lambda bm, b=b: cube(bm, b["min"], b["max"]))
            if b["max"][2] < -9.0:
                part(f"{n}_clad", "Metal_Steel", lambda bm, b=b: box(bm, b["min"][0] - 0.01, b["max"][0] + 0.01, 0.0, b["max"][1], b["max"][2] - 0.03, b["max"][2] + 0.01))
            else:
                part(f"{n}_clad", "Metal_Steel", lambda bm, b=b: box(bm, b["min"][0] - 0.01, b["min"][0] + 0.03, 0.0, b["max"][1], b["min"][2] - 0.01, b["max"][2] + 0.01))
    for k, (cn, nm) in enumerate(stalls):
        cb = BOX[cn]
        sn = cn.replace("Counter", "Shutter")
        sb = BOX[sn]
        x0, x1, z0, z1, hh = cb["min"][0], cb["max"][0], cb["min"][2], cb["max"][2], cb["max"][1]
        if nm == "+z":
            face, a0, a1 = z1, x0, x1
        else:
            face, a0, a1 = x0, z0, z1
        am = (a0 + a1) / 2
        part(f"{cn}", "Trim_Dark", lambda bm: cube(bm, cb["min"], [cb["max"][0], hh - 0.05, cb["max"][2]]))
        panel(f"{cn}_front", "Sign_Paint", on_wall(nm, am, 0.55, 0.002, face), nm, a1 - a0, 0.9, SIGN_UV[f"front{k}"])
        part(f"{cn}_top", "Metal_Steel", lambda bm: wall_box(bm, nm, a0, a1, hh - 0.05, hh, 0.03, -0.1, face))     # the lip in front of the shutter
        part(f"{cn}_kick", "Metal_Dark", lambda bm: wall_box(bm, nm, a0, a1, 0.0, 0.1, 0.0, 0.012, face))
        sy0, sy1 = sb["min"][1], sb["max"][1]
        sface = sb["max"][2] if nm == "+z" else sb["min"][0]

        def shutter(bm, a0=a0, a1=a1, sy0=sy0, sy1=sy1, sface=sface, nm=nm):
            rows = int((sy1 - 0.12 - sy0) / 0.025)
            vs = []
            for i in range(rows + 1):
                y = sy0 + (sy1 - 0.12 - sy0) * i / rows
                d = -0.056 + 0.012 * 0.5 * (1 - math.cos(2 * math.pi * (y - sy0) / 0.075))
                vs.append((bm.verts.new(B(on_wall(nm, a0 + 0.03, y, d, sface))), bm.verts.new(B(on_wall(nm, a1 - 0.03, y, d, sface)))))
            for (p0, p1), (q0, q1) in zip(vs, vs[1:]):
                bm.faces.new((p0, p1, q1, q0))
            bm.normal_update()
            nv = B(NORMAL[nm]) - B((0, 0, 0))
            for f in bm.faces:
                if f.normal.dot(nv) < 0:
                    f.normal_flip()
        part(f"{sn}", "Shutter_Metal", shutter, recalc=False)
        part(f"{sn}_box", "Metal_Steel", lambda bm: [wall_box(bm, nm, a0, a1, sy1 - 0.14, sy1 + 0.06, -0.1, 0.0, sface),
                                                     wall_box(bm, nm, a0, a0 + 0.04, sy0, sy1, -0.1, 0.0, sface), wall_box(bm, nm, a1 - 0.04, a1, sy0, sy1, -0.1, 0.0, sface),
                                                     wall_box(bm, nm, a0 + 0.04, a1 - 0.04, sy0, sy0 + 0.04, -0.07, -0.02, sface)])
        part(f"{sn}_lock", "Brass", lambda bm: wall_box(bm, nm, am - 0.04, am + 0.04, sy0 + 0.04, sy0 + 0.1, -0.03, -0.015, sface))
        hface = sface
        sign(f"Stall_menu_{k}", f"menu{k}", on_wall(nm, am, 3.62, 0.0, hface), nm, (a1 - a0) * 0.62, 0.56, depth=0.02)
        sign(f"Stall_name_{k}", f"stall{k}", on_wall(nm, am, 4.32, 0.0, hface), nm, (a1 - a0) - 0.3, 0.6, depth=0.06, frame="Metal_Dark")
    part("Stall_bulkhead_N", "Wall_Paint", lambda bm: box(bm, -14.1, 10.1, 3.26, H, -9.62, -9.5))
    part("Stall_bulkhead_E", "Wall_Paint", lambda bm: box(bm, 12.1, 12.22, 3.26, H, -8.1, 8.1))
    part("Stall_bulkhead_trim", "Metal_Steel", lambda bm: [box(bm, -14.1, 10.1, 3.22, 3.26, -9.64, -9.5), box(bm, 12.08, 12.22, 3.22, 3.26, -8.1, 8.1),
                                                          box(bm, -14.1, 10.1, 4.68, 4.72, -9.64, -9.5), box(bm, 12.08, 12.22, 4.68, 4.72, -8.1, 8.1)])
    # the twenty tables, each with its fixed seats on steel arms (backless swivel seats, two a side; one in the middle where a mannequin sits)
    manns = [e["pos"] for e in GB.empties if e["name"].startswith("Spot_mannequin") and e["pos"][1] > 0.3]
    seat_cols = ("seat_a", "seat_b", "seat_c", "seat_d")
    tables = sorted((n, b) for n, b in BOX.items() if n.startswith("Table"))
    benches = [(n, b) for n, b in BOX.items() if n.startswith("Bench")]
    for ti, (n, b) in enumerate(tables):
        x0, x1, z0, z1 = b["min"][0], b["max"][0], b["min"][2], b["max"][2]
        cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
        part(f"{n}_top", "Laminate", lambda bm: box(bm, x0, x1, 0.72, 0.75, z0, z1))
        part(f"{n}_frame", "Metal_Steel", lambda bm: [cyl(bm, (cx, 0.0, cz), (cx, 0.72, cz), 0.04, 0.04, 10), box(bm, x0 + 0.03, x1 - 0.03, 0.0, 0.04, cz - 0.03, cz + 0.03),
                                                     box(bm, cx - 0.03, cx + 0.03, 0.0, 0.04, z0 + 0.03, z1 - 0.03), box(bm, cx - 0.35, cx + 0.35, 0.69, 0.72, cz - 0.02, cz + 0.02)], smooth=False)
        for bn, bb in benches:
            if not (bb["min"][0] < cx < bb["max"][0] and abs((bb["min"][2] + bb["max"][2]) / 2 - cz) < 1.2):
                continue
            bz = (bb["min"][2] + bb["max"][2]) / 2
            sgn = 1 if bz > cz else -1
            mid = any(abs(m[0] - cx) < 0.2 and abs(m[2] - bz) < 0.2 for m in manns)
            xs = [cx] if mid else [cx - 0.33, cx + 0.33]
            col = seat_cols[(ti + (sgn > 0)) % 4]

            def seats(bm, xs=xs, bz=bz, sgn=sgn, bb=bb):
                for x in xs:
                    cyl(bm, (x, 0.04, bz), (x, 0.4, bz), 0.025, 0.025, 8)
                for zz in (bz - 0.16, bz + 0.16):                    # the footrest frame round the seats' feet
                    box(bm, bb["min"][0] + 0.02, bb["max"][0] - 0.02, 0.1, 0.13, zz - 0.012, zz + 0.012)
                for xx in (bb["min"][0] + 0.03, bb["max"][0] - 0.03):
                    box(bm, xx - 0.012, xx + 0.012, 0.1, 0.13, bz - 0.16, bz + 0.16)

            def arms(bm, xs=xs, bz=bz, sgn=sgn):                     # the steel arms from the table's foot (low: under 0.2 m)
                for x in xs:
                    cyl(bm, (x, 0.12, cz + sgn * 0.5), (x, 0.12, bz), 0.02, 0.02, 6)
                    cyl(bm, (x, 0.04, cz + sgn * 0.5), (x, 0.13, cz + sgn * 0.5), 0.022, 0.022, 6)
                box(bm, cx - 0.02, cx + 0.02, 0.1, 0.13, cz + sgn * 0.46, bz)
            part(f"{bn}_frame", "Metal_Steel", seats, smooth=True)
            part(f"{bn}_arms", "Metal_Steel", arms, smooth=True)
            paint(f"{bn}_seats", [(col, cyl, (x, 0.4, bz), (x, 0.45, bz), 0.19, 0.19, 18) for x in xs], smooth=True)
    for n, b in tables[::3]:                                        # left on the tables: a tray, a cup, a napkin (each table its own)
        cx, cz = (b["min"][0] + b["max"][0]) / 2, (b["min"][2] + b["max"][2]) / 2
        paint(f"decor_litter_{n}", [("tray", box, cx - 0.22, cx + 0.12, 0.75, 0.765, cz - 0.16, cz + 0.12),
                                    ("white", cyl, (cx + 0.25, 0.75, cz + 0.2), (cx + 0.25, 0.87, cz + 0.2), 0.04, 0.045, 10),
                                    ("napkin", box, cx - 0.1, cx + 0.05, 0.765, 0.768, cz - 0.05, cz + 0.06)])
    # the bins (THANK YOU flaps), the tray return and its rack of trays, the kiddie ride under its sheet
    for n, b in sorted(BOX.items()):
        if not n.startswith("Bin"):
            continue
        x0, x1, z0, z1, hh = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]
        part(f"{n}", "Wood_Light", lambda bm: [box(bm, x0, x1, 0.0, hh - 0.05, z0, z1)])
        part(f"{n}_top", "Metal_Steel", lambda bm: box(bm, x0 - 0.01, x1 + 0.01, hh - 0.05, hh, z0 - 0.01, z1 + 0.01))
        fz = 1 if (z0 + z1) / 2 < 0 else -1
        nm = "+z" if fz > 0 else "-z"
        zf = z1 if fz > 0 else z0
        paint(f"{n}_flap", [("steel_dk", box, x0 + 0.08, x1 - 0.08, 0.62, 0.92, min(zf, zf + fz * 0.01), max(zf, zf + fz * 0.01))])
        panel(f"{n}_thanks", "Sign_Paint", ((x0 + x1) / 2, 0.98, zf + fz * 0.003), nm, 0.4, 0.1, SIGN_UV["thanks"])
    trb = BOX["Tray_Return"]
    x0, x1, z0, z1, hh = trb["min"][0], trb["max"][0], trb["min"][2], trb["max"][2], trb["max"][1]
    part("Tray_Return", "Metal_Steel", lambda bm: [box(bm, x0, x1, 0.0, 0.9, z0, z1), box(bm, x0, x0 + 0.04, 0.9, hh, z0, z1), box(bm, x1 - 0.04, x1, 0.9, hh, z0, z1),
                                                   box(bm, x0, x1, hh - 0.04, hh, z0, z1), box(bm, x0, x1, 0.9, hh, z1 - 0.03, z1)])
    trk = Painter()
    trk.add("glass_dk", box, x0 + 0.15, x1 - 0.15, 0.25, 0.8, z0 - 0.004, z0)
    for i in range(8):
        y = 0.92 + i * 0.055
        for xa in (x0 + 0.06, (x0 + x1) / 2 + 0.02):
            if rng.random() < 0.75:
                trk.add(("tray", "tray2")[i % 2], box, xa, xa + 0.9, y, y + 0.018, z0 + 0.05 + rng.uniform(0, 0.08), z1 - 0.06)
        trk.add("chrome", box, x0 + 0.04, x1 - 0.04, y - 0.006, y, z1 - 0.06, z1 - 0.03)
    trk.done("Tray_rack")
    sign("Tray_sign", "trays", ((x0 + x1) / 2, hh + 0.2, z0 + 0.4), "-z", 0.9, 0.18, depth=0.02)
    paint("decor_Tray_sign_post", [("chrome", cyl, ((x0 + x1) / 2, hh, z0 + 0.42), ((x0 + x1) / 2, hh + 0.12, z0 + 0.42), 0.01, 0.01, 6)])
    kt = BOX["Sheeted_Kiddie_Train"]
    x0, x1, z0, z1, hh = kt["min"][0], kt["max"][0], kt["min"][2], kt["max"][2], kt["max"][1]
    part("Kiddie_sheet", "Cloth_Sheet", lambda bm: drape(bm, x0, x1, z0, z1, hh, rng, y_hem=0.05, fold=0.03, n=12, top_sag=0.03), recalc=False)
    paint("Kiddie_wheels", [("red", cyl, (x, 0.0, z), (x, 0.06, z), 0.12, 0.12, 14) for x in (x0 + 0.3, x1 - 0.3) for z in (z0 + 0.03, z1 - 0.03)])
    # odds and ends: a wet-floor board, a mop bucket (passable), dust in the corners and under the counters
    paint("decor_wet_floor", [("yellow", box, 2.5, 2.85, 0.0, 0.62, -6.2, -6.18), ("yellow", box, 2.52, 2.83, 0.0, 0.04, -6.3, -6.06)])
    panel("decor_wet_sign", "Sign_Paint", (2.675, 0.36, -6.18 + 0.001), "+z", 0.26, 0.26, SIGN_UV["wet"])
    paint("decor_bucket", [("yellow", cyl, (-14.2, 0.0, -11.3), (-14.2, 0.32, -11.3), 0.17, 0.2, 14), ("charcoal", cyl, (-14.2, 0.0, -11.3), (-14.0, 1.2, -11.6), 0.012, 0.012, 6)], smooth=True)
    for i, (x, z, sx, sz) in enumerate(((-2.0, -8.5, 8.0, 0.9), (11.0, 0.0, 0.8, 7.0), (0.0, 10.6, 3.0, 1.2), (-14.0, 0.0, 0.8, 4.0), (-1.5, 0.0, 5.0, 3.0),
                                         (-12.5, 9.0, 1.6, 2.2), (12.8, -10.0, 1.8, 1.6))):
        dust(f"{i}", x, z, sx, sz)
    sign("Court_sign", "court", (0.0, 3.4, Z1), "-z", 3.2, 0.56, depth=0.03)
    # the pendants (two dead), the emergency heads, the EXIT signs
    for k, (x, z) in enumerate(((-12.5, -5.0), (-12.5, 5.0), (-5.75, -6.2), (-5.75, 6.2), (2.0, -6.2), (2.0, 6.2), (9.5, -5.0), (9.5, 5.0), (-12.5, 0.0), (9.5, 0.0))):
        on = k not in (3, 8)
        yb = 4.2
        part(f"Pendant_{k}_rod", "Metal_Dark", lambda bm, x=x, z=z: cyl(bm, (x, yb + 0.25, z), (x, H, z), 0.008, 0.008, 6))
        part(f"Pendant_{k}_shade", "Metal_Dark", lambda bm, x=x, z=z: cyl(bm, (x, yb, z), (x, yb + 0.25, z), 0.32, 0.22, 20, cap=False), smooth=True)
        part(f"Pendant_{k}_lens", "Lamp_Emit" if on else "Lens_Dead", lambda bm, x=x, z=z: disc_down(bm, (x, yb + 0.01, z), 0.3, 20), recalc=False)
        if on:
            light("day", "SPOT", (x, yb - 0.02, z), PENDANT_W, WARM, size=0.15, aim=(0, -1, 0), cone=120.0)
    exit_sign("Exit_S", "-z", 0.0, 2.95)
    exit_sign("Exit_W", "+x", 0.0, 2.95)
    exit_sign("Exit_kitchen", "+z", 12.5, 2.45)
    emergency_head("Emerg_S_W", "-z", -7.0, 3.2)
    emergency_head("Emerg_S_E", "-z", 7.0, 3.2)
    emergency_head("Emerg_W_N", "+x", -6.0, 3.2)
    emergency_head("Emerg_W_S", "+x", 6.0, 3.2)
    emergency_head("Emerg_bulk_N", "+z", -2.0, 5.2, face=-9.5)
    emergency_head("Emerg_bulk_E", "-x", 0.0, 5.2, face=12.1)
    emergency_head("Emerg_NE", "+z", 13.8, 3.0)


BUILD = {"bookstore": bookstore, "bookstore_desk": bookstore_desk, "cinema_lobby": cinema_lobby, "food_court": food_court}
PREFIX = {"bookstore": "Shop", "bookstore_desk": "Desk", "cinema_lobby": "Lobby", "food_court": "Court"}
# per scene: which lights the day shows, the stills, the fixed pages, how the maps split, pane handling
CFG = {
    "bookstore": dict(split="books", pages=[2048, 2048], sky=False, shots={
        "1_arrival": None, "2_wide": ((8.9, 1.75, 6.8), (-6.0, 1.3, -5.5), 80.0), "3_detail": ((-3.6, 1.45, 3.2), (-8.0, 0.8, 6.4), 66.0)},
        extra={"4_runs": ((5.7, 1.55, 1.2), (5.7, 1.3, -6.5), 70.0)}),
    "bookstore_desk": dict(split="shell", pages=[2048, 2048], sky=False, shots={
        "1_arrival": None, "2_wide": ((5.5, 1.7, 3.6), (-3.5, 1.1, -3.0), 82.0), "3_detail": ((-0.5, 1.55, -2.3), (-1.7, 1.15, -0.8), 62.0)},
        extra={"4_stock": ((4.6, 1.55, -0.6), (4.8, 1.2, -3.8), 78.0)}),
    "cinema_lobby": dict(split="shell", pages=[2048, 2048], sky=False, shots={
        "1_arrival": None, "2_wide": ((8.8, 4.55, -5.8), (-6.0, 1.0, 4.0), 80.0), "3_detail": ((3.0, 1.6, -3.3), (6.2, 1.25, -7.4), 64.0)},
        extra={"4_boxoffice": ((-2.0, 1.6, 2.0), (-8.0, 1.4, 5.5), 70.0)}),
    "food_court": dict(split="shell", pages=[2048, 2048], sky=True, shots={
        "1_arrival": None, "2_wide": ((-14.2, 1.8, 8.4), (6.0, 1.5, -8.0), 80.0), "3_detail": ((-4.0, 1.55, -4.6), (-6.5, 2.6, -9.8), 66.0)},
        extra={"4_stalls_e": ((5.0, 1.6, -1.0), (12.5, 2.4, 3.0), 72.0)}),
}


def setup_scene(sc):
    global SC, GB, BOX, P, X0, X1, Z0, Z1, H, SEEN_UP
    SC = sc
    GB = G.build(sc)
    BOX = {b["name"]: b for b in GB.boxes}
    P = PREFIX[sc]
    f = BOX[f"{P}_Floor"]
    X0, X1, Z0, Z1 = f["min"][0] + G.T, f["max"][0] - G.T, f["min"][2] + G.T, f["max"][2] - G.T
    H = BOX[f"{P}_Ceiling"]["min"][1]
    SEEN_UP = 2.2
    HIDDEN.clear()
    ROWS.clear()
    LIGHTS.clear()


def arrival():
    """The main door's arrival point and the way it faces (the spawn)."""
    sp = next(e for e in GB.empties if e["name"] == "Marker_Spawn")["pos"]
    a = min((e for e in GB.empties if e["name"].startswith("Arrive_")), key=lambda e: math.dist(e["pos"], sp))
    return a["pos"], a["face"]


# ---------------------------------------------------------------- lights, world, light sets
def add_lights():
    cols = {}
    for name in ("Lights_Day", "Lights_Night", "Lights_Always"):
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        cols[name] = c
    for i, L in enumerate(LIGHTS):
        d = bpy.data.lights.new(f"{L['set']}_{i:03d}", L["kind"])
        d.energy, d.color = L["power"], L["color"]
        if L["kind"] == "AREA":
            d.shape = "RECTANGLE"
            d.size, d.size_y = L["size"], L["size_y"] or L["size"]
        elif L["kind"] != "SUN":
            d.shadow_soft_size = L["size"]
        if L["kind"] == "SPOT":
            d.spot_size, d.spot_blend = math.radians(L["cone"]), 0.55
        ob = bpy.data.objects.new(d.name, d)
        ob.location = B(L["pos"])
        if L["aim"] is not None:
            ob.rotation_euler = B(L["aim"]).to_track_quat("-Z", "Y").to_euler()
        cols[{"day": "Lights_Day", "night": "Lights_Night", "always": "Lights_Always"}[L["set"]]].objects.link(ob)
    if CFG[SC]["sky"]:
        d = bpy.data.lights.new("Sun", "SUN")
        d.energy, d.color = SUN_W, (1.0, 0.95, 0.86)
        d.angle = math.radians(1.5)
        ob = bpy.data.objects.new("Sun", d)
        ob.location = B((0, 20, 0))
        ob.rotation_euler = B(SUN_DIR).to_track_quat("-Z", "Y").to_euler()
        cols["Lights_Day"].objects.link(ob)


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("Sky")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.58, 0.66, 0.80, 1)
    bg.inputs["Strength"].default_value = 0.0


def set_emit(mname, strength):
    m = bpy.data.materials.get(mname)
    if m:
        m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = strength


PANE_MAT = "Skylight_Glass"
PANE_DAY, PANE_NIGHT = 0.95, 0.03          # the panes' lightmap texels: a fraction of the encoded range (the bright sky by day, a dull glow at night)
PANE_SHOW = {"day": 0.92, "night": 0.05}
PANE_GLOW = 5.0


def apply_light_set(name):
    """day: the shop's own lamps (and the sun and the sky through the food court's skylight), Lamp_Emit on, Emergency_Emit off; night: the
    emergency heads alone, Lamp_Emit off (the mall locked); export: both toggled materials at the strength the page switches on."""
    day = name == "day"
    for c, on in (("Lights_Day", day), ("Lights_Night", name == "night"), ("Lights_Always", True)):
        if c in bpy.data.collections:
            bpy.data.collections[c].hide_render = not on
    w = bpy.context.scene.world
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = SKY_STRENGTH if (day and CFG[SC]["sky"]) else 0.0
    set_emit("Lamp_Emit", LAMP_EMIT if name in ("day", "export") else 0.0)
    set_emit("Emergency_Emit", EMERG_EMIT if name in ("night", "export") else 0.0)
    m = bpy.data.materials.get(PANE_MAT)
    if m:
        bsdf = m.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Emission Color"].default_value = (0.92, 0.95, 1.0, 1)
        bsdf.inputs["Emission Strength"].default_value = {"day": PANE_GLOW, "night": PANE_GLOW * 0.01}.get(name, 0.0)


def ensure_marker():
    st = bpy.data.collections["Standins"]
    ob = bpy.data.objects.get("standin_arrival_marker")
    if ob is None:
        me = bpy.data.meshes.new("standin_arrival_marker")
        bm = bmesh.new()
        a = arrival()[0]
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
    path = work() / "axes_marker.glb"
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_yup=True, export_apply=True, export_materials="NONE")
    b = path.read_bytes()
    j = json.loads(b[20:20 + struct.unpack("<I", b[12:16])[0]])
    acc = j["accessors"][j["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    off = j["nodes"][0].get("translation", [0, 0, 0])
    centre = [(acc["min"][i] + acc["max"][i]) / 2 + off[i] for i in range(3)]
    a = arrival()[0]
    want = [a[0], a[1] + 0.1, a[2]]
    print(f"AXES glTF centre {tuple(round(v, 3) for v in centre)}, game point {tuple(want)}")
    assert all(abs(centre[i] - want[i]) < 1e-4 for i in range(3)), "the exporter's axes disagree with (x, -z, y)"
    print("AXES PASS: game (x, y, z) = Blender (x, -z, y) = glTF (x, y, z)")


def reset():
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
    GEN.clear()


def build_all():
    global ART, STANDIN, DOORS_C, LAYOUT_C
    reset()
    sc = bpy.context.scene
    ART, STANDIN, DOORS_C, LAYOUT_C = (bpy.data.collections.new(n) for n in ("Art", "Standins", "Doors", "Layout"))
    for c in (ART, STANDIN, DOORS_C, LAYOUT_C):
        sc.collection.children.link(c)
    gen("signs")
    gen("spines")
    BUILD[SC]()
    if ROWS:
        build_books(np.random.default_rng(7))
    build_layout()
    add_lights()
    setup_world()
    apply_light_set("day")
    ensure_marker()
    LAYOUT_C.hide_render = True
    tris = sum(len(p.vertices) - 2 for o in ART.objects for p in o.data.polygons)
    print(f"ART {SC}: {len(ART.objects)} objects, about {tris} triangles before culling; {len(LIGHTS)} lights; materials {sorted(MATS)}")


# ---------------------------------------------------------------- layout file and the checks
def stage_layout():
    import export_scene
    export_scene.write(SC, ROOT / f"world/{SC}.json")
    a = json.loads((ROOT / f"world/{SC}.json").read_text())
    b = G.doc_of(GB)
    print(f"LAYOUT {SC}: export_scene.py's file is {'THE SAME AS' if a == b else 'DIFFERENT FROM'} the greybox model's")


def stage_check():
    import check_layout as CL
    world = json.loads((ROOT / f"world/{SC}.json").read_text())
    parts = CL.blender_parts("Art")
    consts = {"links": {l["door"]: {"arrive": l["arrive"], "at": [l["at"][0], l["at"][2]]} for l in world["links"]}}
    print(f"layout check: scene {SC}, {len(parts)} visible meshes, {len(world['colliders'])} colliders")
    res = CL.check(parts, world, consts)
    # the mannequins' places: nothing solid or passable stands within 25 cm of one, from just above where it stands to 1.8 m over it
    for s in world["spots"]:
        if s["kind"] != "mannequin":
            continue
        x, y, z = s["position"]
        hit = [p["name"] for p in parts if p["max"][1] > y + 0.06 and p["min"][1] < y + 1.8
               and p["min"][0] - 0.25 < x < p["max"][0] + 0.25 and p["min"][2] - 0.25 < z < p["max"][2] + 0.25]
        res.append((not hit, "SPOT", f"{s['name']} ({x:.2f}, {y:.2f}, {z:.2f}): " + ("clear within 0.25 m" if not hit else "art in the way: " + ", ".join(hit))))
    bad = CL.report(res)
    print("CHECK_LAYOUT", SC, "exit", 1 if bad else 0)
    (work() / "check_layout.txt").write_text("\n".join(f"{'PASS' if ok else 'FAIL'}  {r:6s} {t}" for ok, r, t in res) + "\n")


# ---------------------------------------------------------------- bake
UV_SCALE = {"Ceiling_Tile": 0.5, "Ceiling_Paint": 0.4, "Ceiling_Dark": 0.5, "Shelf_Back": 0.4, "Wood_Shelf": 0.8, PANE_MAT: 0.15, "Decal_Dust": 0.5, "Paint_Palette": 0.8}
PRE_LM = ("Book_Spines",)


def cull(bm, mname, oname):
    """Drop faces never seen: on the room's outer planes facing out, flat against the floor or the ceiling facing into them, inside a HIDDEN
    volume, and (props) faces looking up from high or down from low."""
    e = 2e-3
    bad = []
    for f in bm.faces:
        c, n = f.calc_center_median(), f.normal
        gx, gy, gz = c.x, c.z, -c.y
        nx, ny, nz = n.x, n.z, -n.y
        out = (nx < -0.9 and gx <= X0 + e) or (nx > 0.9 and gx >= X1 - e) or (nz < -0.9 and gz <= Z0 + e) or (nz > 0.9 and gz >= Z1 - e) \
            or (ny < -0.9 and gy <= e) or (ny > 0.9 and gy >= H - e)
        if oname.startswith("Floor_"):
            out = not (ny > 0.9 and abs(gy) < e)
        elif oname.startswith("Ceiling_"):
            out = not ((ny < -0.9 and abs(gy - H) < e) or (abs(ny) < 0.1 and X0 + e < gx < X1 - e and Z0 + e < gz < Z1 - e))
        elif oname.startswith("Wall_"):
            out = out or (DADO is not None and abs(ny) > 0.9 and abs(gy - DADO) < e)
        elif mname not in TWO_SIDED and mname != PANE_MAT and not oname.startswith("Skylight_"):
            out = out or (ny > 0.5 and gy > SEEN_UP) or (ny < -0.5 and gy < SEEN_DOWN)
        if not out and any(h[0] < gx < h[1] and h[2] < gy < h[3] and h[4] < gz < h[5] for h in HIDDEN):
            out = True
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
    for ob in sorted(art.objects, key=lambda o: o.name):
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
        if not bm.faces:
            bm.free()
            continue
        if mname not in PRE_LM:
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        me = bpy.data.meshes.new(mname)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(bpy.data.materials[mname])
        ob = bpy.data.objects.new(mname, me)
        exp.objects.link(ob)
        out[mname] = ob
    return out


def groups(exp):
    """The two maps: books (bookstore: map 0 everything else, map 1 the books) or shell (map 0 the shell, map 1 the rest)."""
    lm = [m for m in sorted(exp) if m not in NO_LIGHTMAP]
    if CFG[SC]["split"] == "books":
        return [[m for m in lm if m not in PRE_LM], [m for m in lm if m in PRE_LM]]
    return [[m for m in lm if m in SHELL], [m for m in lm if m not in SHELL]]


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
    """One atlas for `objs`: smart-project islands at equal texel density (some materials scaled down), packed with MARGIN_PX on a `page` square.
    The books keep the lightmap UVs build_books gave them."""
    pre = [o for o in objs if o.name in PRE_LM]
    rest = [o for o in objs if o not in pre]
    if rest:
        for o in rest:
            uvs = o.data.uv_layers
            if "lightmap" in uvs:
                uvs.remove(uvs["lightmap"])
            uvs.new(name="lightmap", do_init=False)
            uvs.active = uvs["lightmap"]
        select_only(rest)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
        bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.average_islands_scale()
        bpy.ops.object.mode_set(mode="OBJECT")
        for o in rest:
            if o.name in UV_SCALE:
                d = o.data.uv_layers["lightmap"].data
                us = np.array([x.uv for x in d]) * UV_SCALE[o.name]
                d.foreach_set("uv", us.ravel())
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / page, shape_method="CONCAVE")
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        o.data.uv_layers.active = o.data.uv_layers["lightmap"]
        o.data.uv_layers["UVMap"].active_render = True
    plain = [o for o in objs if o.name not in UV_SCALE]
    a3 = sum(area3d(o) for o in plain) or 1.0
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
    path = str(work() / "dn.exr")
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


# ---------------------------------------------------------------- brightness: how the page shows the maps
# The page draws a baked material unlit, with no tone mapping: texture x base colour x texel x intensity / pi. A texel holds the bake's light L
# (Cycles' diffuse irradiance) through a shoulder: texel = G L / (C + G L), and intensity = pi C, so the page shows texture x G L where the light
# is ordinary and rolls off toward texture x C under a lamp or in the sun's patch, never clipping. G is each set's exposure, found from the
# shell map's median light (TARGET) unless --gain-day / --gain-night give it; CAP lowers one bright material.
C_SHOULDER = 1.12
TARGET = {"bookstore": 2.4, "bookstore_desk": 1.8, "cinema_lobby": 5.6, "food_court": 3.0}     # the floor's median G L by day (it gets the
NIGHT_SHARE = 0.45                                                                                  # lamps' direct light; the walls about a fifth)
CAP = {}


FLOOR = {"bookstore": "Carpet_Shop", "bookstore_desk": "Carpet_Shop", "cinema_lobby": "Carpet_Cinema", "food_court": "Floor_Terrazzo"}


def gain_of(light_set, rgb, mask):
    """mask: the floor's texels in the shell map: the gain puts the floor's median light at TARGET."""
    g = arg(f"--gain-{light_set}", None, float)
    if g:
        return g, "given"
    peak = rgb.max(axis=2)
    sel = (peak > 1e-6) & mask
    med = float(np.percentile(peak[sel], 50)) if sel.any() else 1.0
    t = TARGET[SC] * (1.0 if light_set == "day" else NIGHT_SHARE)
    return t / max(med, 1e-6), f"auto (the floor's median light {med:.4f} to {t:.2f})"


def stage_bake():
    import time
    work()
    exp = make_export_objects()
    leaves = sorted(bpy.data.collections["Doors"].objects, key=lambda o: o.name)
    bpy.data.collections["Art"].hide_render = True
    bpy.data.collections["Art"].hide_viewport = True
    setup_cycles(SAMPLES, bake=True)
    hide = [m for m in ("Glass_Clear", PANE_MAT) if m in exp]
    for m in hide:
        exp[m].hide_render = True
    gr = groups(exp)
    leaf_map = 0 if CFG[SC]["split"] == "books" else 1
    report, gains = {}, {}
    for n, mats in enumerate(gr):
        objs = [exp[m] for m in mats] + (leaves if n == leaf_map else [])
        print(f"lightmap {n}: {[o.name for o in objs]}")
        S, dens, small = lightmap_uv(objs, CFG[SC]["pages"][n])
        if PRE_LM[0] in [o.name for o in objs]:
            dens = round(BOOKS_D or 0.0, 1)
        mask = uv_mask(exp[PANE_MAT], S) if PANE_MAT in exp and exp[PANE_MAT] in objs else np.zeros((S, S), bool)
        for light_set, idx, samples in (("day", n, SAMPLES), ("night", n + 2, NIGHT_SAMPLES)):
            t0 = time.time()
            rgb = bake_set(n, objs, S, light_set, samples)
            peak = rgb.max(axis=2)
            sel = (peak > 1e-6) & ~mask
            pc = np.percentile(peak[sel], [50, 90, 99, 99.5, 100]) if sel.any() else [1.0] * 5
            if light_set not in gains:
                fl = FLOOR[SC]
                assert n == 0 and fl in exp and exp[fl] in objs, "the gain is set from the floor, in the first map"
                gains[light_set] = gain_of(light_set, rgb, uv_mask(exp[fl], S, grow=0))
            Gn, how = gains[light_set]
            print(f"  {light_set} texel percentiles p50 p90 p99 p99.5 max:", [round(float(v), 4) for v in pc], f"gain {Gn:.3f} ({how})")
            tex = Gn * rgb / (C_SHOULDER + Gn * rgb)
            if mask.any():
                tex[mask] = PANE_DAY if light_set == "day" else PANE_NIGHT
            out = np.ones((S, S, 4), np.float32)
            out[..., :3] = srgb_encode(tex)
            png = bpy.data.images.new(f"LM_{idx}_png", S, S, alpha=False)
            png.colorspace_settings.name = "Non-Color"
            png.pixels.foreach_set(out.ravel())
            png.filepath_raw = str(work() / f"{SC}_{idx}.png")
            png.file_format = "PNG"
            png.save()
            bpy.data.images.remove(png)
            report[idx] = {"map": n, "set": light_set, "size": S, "gain": round(Gn, 4), "gain_how": how, "C": C_SHOULDER, "px_per_m": round(dens, 1),
                           "px_per_m_scaled": small, "p50_p90_p99_p995_max": [round(float(v), 4) for v in pc], "samples": samples,
                           "device": bpy.context.scene.cycles.device, "seconds": round(time.time() - t0), "materials": mats + ([o.name for o in leaves] if n == leaf_map else [])}
            print("  baked", report[idx])
    (work() / "lightmaps.json").write_text(json.dumps(report, indent=1))
    for m in hide:
        exp[m].hide_render = False
    apply_light_set("day")
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Art"].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


BOOKS_D = None


def set_intensities():
    rep = json.loads((work() / "lightmaps.json").read_text())
    for idx, r in rep.items():
        idx = int(idx)
        st = r["set"]
        key, kkey = ("lightmap", "lightmap_intensity") if st == "day" else ("lightmap_night", "lightmap_night_intensity")
        for nm in r["materials"]:
            ob = bpy.data.objects.get(nm)
            mats = [bpy.data.materials.get(nm)] if bpy.data.materials.get(nm) else [s.material for s in ob.material_slots] if ob else []
            for m in mats:
                if m is None:
                    continue
                m[key] = lm_url(SC, idx)
                if m.name == PANE_MAT:
                    pane = PANE_DAY if st == "day" else PANE_NIGHT
                    m[kkey] = round(math.pi * PANE_SHOW[st] / pane, 4)
                else:
                    m[kkey] = round(math.pi * r["C"] * CAP.get((SC, st, m.name), 1.0), 4)


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
    base = blend_path(SC).parent
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
    p = blend_path(SC)
    p.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(p))
    scrub_private()
    bpy.ops.wm.save_mainfile()


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
    raw = work() / f"{SC}_raw.glb"
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
    cam = bpy.data.cameras.new(name)
    cam.sensor_fit = "VERTICAL"
    if ortho:
        cam.type = "ORTHO"
        cam.ortho_scale = ortho
        cam.sensor_fit = "AUTO"
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
    stills_dir(SC).mkdir(parents=True, exist_ok=True)
    scrub_private()
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
        bpy.data.collections["Export"].hide_viewport = True
    bpy.data.collections["Layout"].hide_render = True
    sets = arg("--set", "day,night").split(",")
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
    for o in bpy.data.collections["Art"].objects:
        if o.data.materials and o.data.materials[0].name in ("Glass_Clear", PANE_MAT):
            for attr in ("visible_shadow", "visible_diffuse", "visible_glossy", "visible_transmission", "visible_volume_scatter"):
                setattr(o, attr, False)
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    a, f = arrival()
    cfg = CFG[SC]
    cams = {"1_arrival": look_cam("arrival", (a[0], 1.6, a[2]), (a[0] + f[0] * 3, 1.5, a[2] + f[1] * 3), 75.0)}
    for k, v in list(cfg["shots"].items()) + list(cfg.get("extra", {}).items()):
        if v:
            cams[k] = look_cam(k, v[0], v[1], v[2])
    span = max(X1 - X0, Z1 - Z0) * 1.04
    plan = look_cam("plan", ((X0 + X1) / 2, H + 10, (Z0 + Z1) / 2), None, ortho=span)
    plan.rotation_euler = (0, 0, 0)
    arts = list(bpy.data.collections["Art"].objects) + list(bpy.data.collections["Doors"].objects)
    cut = [o for o in arts if o.type == "MESH" and min((o.matrix_world @ Vector(c)).z for c in o.bound_box) > 2.45]
    which = arg("--only", "all")
    expo = arg("--exposure", 0.0, float)
    for light_set in sets:
        apply_light_set(light_set)
        for key, cam in list(cams.items()) + [("5_plan", plan)]:
            review = key in ("1_arrival", "2_wide", "3_detail")
            if which not in ("all", key):
                continue
            if light_set != "day" and key not in ("1_arrival", "2_wide"):
                continue
            sc.camera = cam
            sc.view_settings.exposure = expo + (0.6 if key == "5_plan" else 0.0)
            for o in arts:
                o.visible_camera = True
            if key == "5_plan":
                for o in cut:
                    o.visible_camera = False
                w, h = (1600, int(1600 * (Z1 - Z0) / (X1 - X0))) if X1 - X0 >= Z1 - Z0 else (int(1600 * (X1 - X0) / (Z1 - Z0)), 1600)
            else:
                w, h = 1920, 1080
            sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, arg("--scale", 100, int)
            sc.render.image_settings.file_format = "JPEG"
            sc.render.image_settings.quality = 90
            to_docs = review and light_set == "day"
            path = stills_dir(SC) / f"{key}.jpg" if to_docs else work() / f"{key}{'' if light_set == 'day' else '_' + light_set}.jpg"
            sc.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            q = 90
            while path.stat().st_size > 400_000 and q > 40 and to_docs:
                q -= 5
                sc.render.image_settings.quality = q
                bpy.data.images["Render Result"].save_render(str(path), scene=sc)
            strip_jpeg_comments(path)
            print("STILL", SC, light_set, key, path.name, path.stat().st_size, "q", q)
    for o in arts:
        o.visible_camera = True
    apply_light_set("day")


def load_scene_file(sc):
    p = blend_path(sc)
    if bpy.data.filepath and Path(bpy.data.filepath).resolve() == p.resolve():
        return
    bpy.ops.wm.open_mainfile(filepath=str(p))


def rebuild_state():
    """After opening a saved scene: the module's per-scene state that the later stages read (the room's bounds, hidden volumes, the books' density)."""
    global ART, STANDIN, DOORS_C, LAYOUT_C, BOOKS_D, DADO, SEEN_UP
    ART, STANDIN = bpy.data.collections.get("Art"), bpy.data.collections.get("Standins")
    DOORS_C, LAYOUT_C = bpy.data.collections.get("Doors"), bpy.data.collections.get("Layout")
    st = json.loads((work() / "state.json").read_text()) if (work() / "state.json").exists() else {}
    HIDDEN[:] = [tuple(h) for h in st.get("hidden", [])]
    BOOKS_D = st.get("books_d")
    DADO = st.get("dado")
    SEEN_UP = st.get("seen_up", 2.2)


def save_state(books_d):
    (work() / "state.json").write_text(json.dumps({"hidden": HIDDEN, "books_d": books_d, "dado": DADO, "seen_up": SEEN_UP}))


def main():
    global BOOKS_D
    ST = set(STAGE.split(","))
    if "all" in ST:
        ST = {"art", "layout", "check", "bake", "export", "axes", "render"}
    for sc in SCENES:
        setup_scene(sc)
        if "art" in ST:
            build_all()
            BOOKS_D = None
            if ROWS:
                BOOKS_D = pack_rows(BOOKS_PAGE)[0]
            save_state(BOOKS_D)
            save_blend()
        else:
            load_scene_file(sc)
            setup_scene(sc)
            rebuild_state()
        if "layout" in ST:
            stage_layout()
        if "check" in ST:
            stage_check()
        if "bake" in ST:
            stage_bake()
        if "export" in ST:
            stage_export()
        if "axes" in ST:
            stage_axes()
        if "render" in ST:
            stage_render()
        print("DONE", sc, sorted(ST))


if __name__ == "__main__":
    main()
