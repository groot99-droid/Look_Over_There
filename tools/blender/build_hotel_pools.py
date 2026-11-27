"""Dresses and lights the hotel's eleven sub-floor pools (docs/BLENDER_AREAS.md section 1: `sub_pool_01` to `sub_pool_11`), bakes each in soft,
even light and exports world/<scene>.glb and world/<scene>.json. One script for all eleven: a shared kit, varied per pool (the table LOOK below).

Re-runnable, from the repo root. `--scene` takes one id, a list (1,3,sub_pool_05) or `all`; with several, one Blender runs them one after another.

    python tools/blender/build_hotel_pools.py --stage textures            (the shared generated textures -> blender/textures/hotel_pools/, no Blender)
    python tools/blender/build_hotel_pools.py --stage plancheck           (the props' places against the layout, no Blender)
    blender -b --factory-startup --python tools/blender/build_hotel_pools.py -- --scene all --stage art      (art, layout objects; saves
                                                                          blender/scenes/<scene>.blend, writes world/<scene>.json, runs the check)
    blender -b --factory-startup --python tools/blender/build_hotel_pools.py -- --scene all --stage bake [--samples 512]
    blender -b --factory-startup --python tools/blender/build_hotel_pools.py -- --scene all --stage export
    blender -b --factory-startup --python tools/blender/build_hotel_pools.py -- --scene all --stage render [--render-samples 128]
    python tools/blender/build_hotel_pools.py --scene all --stage encode [--gain G]   (the raw bake -> lightmap PNGs again, no Blender)
    python tools/blender/pack_scene.py sub_pool_01 --work work/sub_pool_01            (WebP lightmaps and textures -> world/), per pool

The layout is the greybox's: tools/blender/build_hotel_greybox.py (`pool(k)`, imported here), so no coordinate of the layout is typed in: every
collider, door, link, marker, zone and spot comes from it, and export_scene.py writes the same world/<scene>.json as the greybox did.

The kit every pool shares: white square tile with grout (12.5 cm on the walls and in the basin, 25 cm on the deck), a raised tiled lip with a
bullnose round the basin, a waterline band and a dado band in the pool's accent colour, chrome ladders at the deep end and a chrome handrail down
the steps, recessed ceiling panels (Lamp_Emit), the deep end's two drains and the two shut grates (the underwater ways on), lane lines with their
T-ends, depth markers and the pool's number plate by the door. What varies per pool: the tile's tint (white, pale blue, mint, faded pink), the
ceiling (flat with panels, a barrel vault with cove lights, or a skylit light well), columns (the even pools' greybox columns, round or square),
wall niches or pilasters, loungers, a dead plant, a slide in one, a lost float toy. The textures are generated here (numpy, own work) and shared
by all eleven files; so are the kit's meshes (one builder each).

The water surface is its own material (`Pool_Water`): see-through (alpha blend), lightly tinted, never baked; it is hidden during the bake, so the
floors and walls under it are baked as seen through clear water. The odd pools' 12 cm of water over the whole floor is one surface at y 0.12.
Props you can walk through are decor_ (no collider; the layout file stays the greybox's).
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
except ImportError:                       # textures, plancheck and encode run in plain Python (numpy and Pillow)
    bpy = None

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import build_hotel_greybox as G          # noqa: E402  the layout model (pure Python)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


ALL = [f"sub_pool_{k:02d}" for k in range(1, 12)]


def scene_list():
    s = arg("--scene", "all")
    if s == "all":
        return ALL
    return [t if t.startswith("sub_pool_") else f"sub_pool_{int(t):02d}" for t in s.split(",")]


STAGE = arg("--stage", "art")
SAMPLES = arg("--samples", 512, int)
DEVICE = arg("--device", "auto")
TEXDIR = "blender/textures/hotel_pools/"
MARGIN_PX = 8
T = G.T
WATER_EVEN, WATER_ODD = -0.10, 0.12           # the greybox's water surface in the basin; the odd pools' water over the whole floor


# ================================================================ the look of each pool (the family)
TINT = {        # baseColorFactor on the shared white tile: walls; the basin a touch deeper; the deck a touch greyer
    "white": dict(wall=(0.97, 0.97, 0.95), pool=(0.80, 0.91, 0.96), deck=(0.93, 0.93, 0.91), accent=(0.10, 0.22, 0.55), trim=(0.86, 0.87, 0.86)),
    "blue": dict(wall=(0.82, 0.91, 0.98), pool=(0.66, 0.85, 0.97), deck=(0.86, 0.91, 0.94), accent=(0.05, 0.30, 0.45), trim=(0.72, 0.82, 0.90)),
    "mint": dict(wall=(0.82, 0.96, 0.88), pool=(0.68, 0.92, 0.86), deck=(0.87, 0.93, 0.89), accent=(0.08, 0.40, 0.32), trim=(0.70, 0.86, 0.78)),
    "pink": dict(wall=(0.98, 0.86, 0.85), pool=(0.92, 0.82, 0.83), deck=(0.94, 0.88, 0.87), accent=(0.48, 0.16, 0.20), trim=(0.88, 0.74, 0.74)),
}
TILE_NAME = {"white": "white", "blue": "pale blue", "mint": "mint", "pink": "faded pink"}

# props: ("lounger", x, z, yaw) head toward local -z (yaw 0 north, 90 west, -90 east, 180 south); ("plant", x, z); ("ring"|"duck"|"kick", x, z[, yaw])
# on the water; ("slide", z) on the west deck (pool 8). Every pool also gets the kit: two ladders at the deep end and the handrail down the steps.
LOOK = {
    1: dict(tile="white", ceiling="flat", cols=None, niches={}, pilasters="NEW",
            props=[("lounger", 8.75, -6.2, -90), ("lounger", 8.75, -4.8, -90), ("lounger", 8.75, -3.4, -90), ("ring", 1.6, -1.5)],
            detail=((7.6, 1.5, -0.6), (8.6, 0.4, -5.2))),
    2: dict(tile="blue", ceiling="vault", cols="round", niches={}, pilasters="",
            props=[("plant", 9.2, 9.2), ("lounger", 5.0, -0.42, 90), ("lounger", 5.0, 0.42, 90), ("kick", -4.6, -3.0, 25)],
            detail=((0.6, 1.6, 3.2), (-4.5, -0.6, -3.0))),
    3: dict(tile="mint", ceiling="skylit", cols=None, niches={"W": [-3.0, 1.0, 5.0]}, pilasters="",
            props=[("lounger", -1.6, 1.4, 90), ("lounger", -1.6, 2.6, 90), ("duck", 4.0, -2.5, 30), ("plant", -9.2, -9.2)],
            detail=((-5.0, 1.5, 6.5), (-9.6, 1.2, 1.0))),
    4: dict(tile="pink", ceiling="flat", cols="square", niches={}, pilasters="",
            props=[("lounger", -5.6, 6.0, 180), ("lounger", -4.4, 6.0, 180), ("lounger", 4.4, 6.0, 180), ("lounger", 5.6, 6.0, 180),
                   ("plant", 9.2, -9.2)],
            detail=((1.5, 1.5, 3.9), (5.0, 0.3, 6.4))),
    5: dict(tile="white", ceiling="vault", cols=None, niches={"W": [-5.0, 5.0], "E": [-5.0, 0.0, 5.0]}, pilasters="",
            props=[("ring", -0.8, -4.0), ("plant", 8.8, 8.8)],
            detail=((-1.5, 1.5, 7.6), (0.0, 0.3, 1.0))),
    6: dict(tile="blue", ceiling="skylit", cols="round", niches={}, pilasters="",
            props=[("lounger", -5.0, 5.0, 90), ("lounger", 5.0, 4.6, -90), ("lounger", 5.0, 5.4, -90), ("duck", -2.0, -5.0, -40),
                   ("plant", -9.2, 9.2)],
            detail=((-3.0, 1.5, 1.6), (2.0, 1.6, -5.0))),
    7: dict(tile="mint", ceiling="flat", cols=None, niches={"E": [-5.0, 5.0]}, pilasters="NWS",
            props=[("lounger", 8.75, -4.2, -90), ("lounger", 8.75, -2.8, -90), ("ring", -3.0, -2.0)],
            detail=((4.5, 1.5, 3.0), (9.4, 1.0, -4.0))),
    8: dict(tile="pink", ceiling="vault", cols="square", niches={}, pilasters="",
            props=[("slide", -7.6), ("duck", 3.0, -5.0, 120)],
            detail=((-1.0, 1.6, -3.0), (-5.0, 1.0, -7.6))),
    9: dict(tile="white", ceiling="skylit", cols=None, niches={"S": [-5.5, 5.5]}, pilasters="NEW",
            props=[("plant", 9.2, 9.2), ("lounger", 3.0, 3.0, 180), ("lounger", 4.2, 3.0, 180), ("kick", -3.0, -5.0, -15)],
            detail=((-2.0, 1.5, 2.0), (5.0, 2.6, -4.5))),
    10: dict(tile="mint", ceiling="flat", cols="round", niches={}, pilasters="",
             props=[("ring", 2.0, -3.0), ("plant", 9.2, -9.2), ("plant", -9.2, 9.2)],
             detail=((-4.0, 1.5, 8.0), (-7.5, 1.4, 2.5))),
    11: dict(tile="blue", ceiling="vault", cols=None, niches={"W": [-5.0, 1.0], "E": [-5.0, 1.0]}, pilasters="NS",
             props=[("lounger", -5.0, 7.4, 180), ("lounger", -3.8, 7.4, 180), ("duck", 3.0, -4.0, 200), ("ring", -2.0, -6.0)],
             detail=((-6.0, 1.5, -1.8), (-4.0, -0.8, -8.0))),
}
SKY_WELLS = {3: [(2.0, 7.0, -4.0, 1.0)], 6: [(-6.0, 6.0, -6.5, -3.5)], 9: [(-7.0, -3.0, -6.5, -2.5), (3.0, 7.0, -6.5, -2.5)]}   # (x0, x1, z0, z1)
VAULT_RISE = {3.2: 1.0, 4.0: 1.4}
WELL_H = 1.0
NICHE_W, NICHE_V, NICHE_D = 1.2, (0.5, 2.2), 0.15
PANEL = (1.2, 0.6)
PANEL_GRID = (-7.5, -2.5, 2.5, 7.5)


def pool_info(k):
    """The basin, its z profile, the water height and the columns, all from the greybox model."""
    S = G.build(f"sub_pool_{k:02d}")
    box = {b["name"]: b for b in S.boxes}
    bx0, bx1 = box["Deck_W"]["max"][0], box["Deck_E"]["min"][0]
    bz0, bz1 = box["Deck_N"]["max"][2], box["Deck_S"]["min"][2]
    segs = sorted(((b["min"][2], b["max"][2], b["max"][1], b["name"]) for b in S.boxes
                   if b["name"].startswith(("Step_", "Shallow_Floor", "Deep_Floor"))), key=lambda s: -s[1])
    z = bz1
    for s in segs:                                        # contiguous from the south (the way in) to the north (the deep end)
        assert abs(s[1] - z) < 1e-6, (k, s, z)
        z = s[0]
    assert abs(z - bz0) < 1e-6
    cols = [b for b in S.boxes if b["name"].startswith("Column")]
    h = box["Pool_Ceiling"]["min"][1]
    e = {x["name"]: x for x in S.empties}
    return dict(S=S, box=box, bx0=bx0, bx1=bx1, bz0=bz0, bz1=bz1, segs=segs, cols=cols, h=h, odd=bool(k % 2),
                water=WATER_ODD if k % 2 else WATER_EVEN, puzzle=e["Spot_puzzle_1"]["pos"], empties=e)


# ================================================================ the props' places (pure Python, checked by --stage plancheck)
LOUNGER = (0.66, 1.96)        # footprint (across, along)
PLANT_R = 0.32
LADDER_DZ = 2.2               # the deep-end ladders stand this far from the basin's north wall
LIP_W = 0.3


def ladder_places(I):
    z = I["bz0"] + LADDER_DZ
    return [("W", I["bx0"], z), ("E", I["bx1"], z)]


def footprints(k):
    """(name, x0, x1, z0, z1) of every prop that stands on the deck (the water toys float and are left out)."""
    I = pool_info(k)
    out = []
    for p in LOOK[k]["props"]:
        if p[0] == "lounger":
            _, x, z, yaw = p
            a, l = LOUNGER[0] / 2, LOUNGER[1] / 2
            hx, hz = (a, l) if abs(math.sin(math.radians(yaw))) < 0.5 else (l, a)
            out.append((f"lounger@{x},{z}", x - hx, x + hx, z - hz, z + hz))
        elif p[0] == "plant":
            out.append((f"plant@{p[1]},{p[2]}", p[1] - PLANT_R, p[1] + PLANT_R, p[2] - PLANT_R, p[2] + PLANT_R))
        elif p[0] == "slide":
            z = p[1]
            out.append(("slide_ladder", -7.0, -5.3, z - 0.45, z + 0.45))
    for side, x, z in ladder_places(I):
        d = -1 if side == "W" else 1
        out.append((f"ladder_{side}", min(x, x + d * 0.55), max(x, x + d * 0.55), z - 0.3, z + 0.3))
    return I, out


def plancheck(k):
    I, fps = footprints(k)
    bad = []
    bx0, bx1, bz0, bz1 = I["bx0"], I["bx1"], I["bz0"], I["bz1"]
    px, _, pz = I["puzzle"]
    for n, x0, x1, z0, z1 in fps:
        if x0 < -9.95 or x1 > 9.95 or z0 < -9.95 or z1 > 9.95:
            bad.append(f"{n} leaves the room")
        if not n.startswith("ladder") and x0 < bx1 + LIP_W + 0.3 and x1 > bx0 - LIP_W - 0.3 and z0 < bz1 + LIP_W + 0.3 and z1 > bz0 - LIP_W - 0.3:
            bad.append(f"{n} is on the basin or its lip")
        for c in I["cols"]:
            if x0 < c["max"][0] + 0.15 and x1 > c["min"][0] - 0.15 and z0 < c["max"][2] + 0.15 and z1 > c["min"][2] - 0.15:
                bad.append(f"{n} hits {c['name']}")
        cx, cz = min(max(px, x0), x1), min(max(pz, z0), z1)
        if math.hypot(cx - px, cz - pz) < 1.0:
            bad.append(f"{n} is within 1 m of the puzzle spot")
        if x0 < 1.6 and x1 > -1.6 and z1 > 7.6:
            bad.append(f"{n} is in the door's way or on the arrival")
    for i, a in enumerate(fps):
        for b in fps[i + 1:]:
            if a[1] < b[2] + 0.05 and a[2] > b[1] - 0.05 and a[3] < b[4] + 0.05 and a[4] > b[3] - 0.05:
                bad.append(f"{a[0]} overlaps {b[0]}")
    for p in LOOK[k]["props"]:                             # the toys float on the water, inside the basin
        if p[0] in ("ring", "duck", "kick") and not (bx0 + 0.6 < p[1] < bx1 - 0.6 and bz0 + 0.6 < p[2] < bz1 - 0.6):
            bad.append(f"{p[0]} at {p[1]}, {p[2]} is not on the water")
    for w in SKY_WELLS.get(k, []):
        for c in I["cols"]:
            if w[0] - 0.5 < c["max"][0] and w[1] + 0.5 > c["min"][0] and w[2] - 0.5 < c["max"][2] and w[3] + 0.5 > c["min"][2]:
                bad.append(f"sky well {w} over {c['name']}")
    print(f"PLANCHECK sub_pool_{k:02d}: {len(fps)} footprints, " + ("ok" if not bad else "; ".join(bad)))
    return not bad


# ================================================================ generated textures (numpy, own work, fixed seeds; shared by all eleven pools)
def srgb_encode(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def rs(a, h, w):
    ys, xs = np.linspace(0, a.shape[0] - 1, h), np.linspace(0, a.shape[1] - 1, w)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, a.shape[0] - 1), np.minimum(x0 + 1, a.shape[1] - 1)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    return a[y0][:, x0] * (1 - fy) * (1 - fx) + a[y0][:, x1] * (1 - fy) * fx + a[y1][:, x0] * fy * (1 - fx) + a[y1][:, x1] * fy * fx


def vnoise(h, w, rng, octaves=5, base=4, wrap=True):
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


def tile_pixels(S, n, grout_px, base, seed, speckle=0.0):
    """Square tiles, n a side per texture (the texture is 1 m), with grout lines and a small bevel; repeats without a seam. Linear RGB."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:S, 0:S]
    cell = S // n
    cx, cy = (xx + cell // 2) % cell, (yy + cell // 2) % cell        # grout on the texture's edges, so it meets itself when it repeats
    ix, iy = ((xx + cell // 2) // cell) % n, ((yy + cell // 2) // cell) % n
    tone = 1.0 + 0.022 * rng.standard_normal((n, n))
    warm = 0.006 * rng.standard_normal((n, n))
    edge = np.minimum(np.minimum(cx, cell - 1 - cx), np.minimum(cy, cell - 1 - cy)).astype(np.float64)
    g2 = grout_px / 2.0
    mott = vnoise(S, S, rng, 5, 4) - 0.5
    img = np.zeros((S, S, 3))
    t = tone[iy, ix] * (1 + 0.05 * mott)
    bev = np.clip((edge - g2) / 3.0, 0, 1)
    shade = (0.90 + 0.10 * bev) * t
    for c, w in enumerate((1.0 + warm[iy, ix], 1.0, 1.0 - warm[iy, ix])):
        img[..., c] = base * shade * w
    if speckle:
        sp = rng.random((S, S)) < speckle
        img[sp] *= 0.80
    gr = 0.40 + 0.05 * (vnoise(S, S, rng, 4, 8) - 0.5)
    m = edge < g2
    for c in range(3):
        img[..., c] = np.where(m, gr * (1.0, 0.99, 0.96)[c], img[..., c])
    return np.clip(img, 0, 0.82)


def plaster_pixels(S=512):
    rng = np.random.default_rng(77)
    n = 0.80 * (1 + 0.05 * (vnoise(S, S, rng, 6, 4) - 0.5) + 0.02 * (rng.random((S, S)) - 0.5))
    return np.clip(np.repeat(n[..., None], 3, axis=2) * np.array([1.0, 0.995, 0.985]), 0, 0.82)


GLYPHS = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"], "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"], "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"], "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"], "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"], "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"], "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"], "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    " ": ["00000"] * 7, ".": ["00000"] * 6 + ["00100"],
    "0": ["01110", "10011", "10101", "10101", "11001", "10001", "01110"], "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00110", "01000", "10000", "11111"], "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["10010", "10010", "10010", "11111", "00010", "00010", "00010"], "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["01110", "10000", "11110", "10001", "10001", "10001", "01110"], "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"], "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
}
SIGNS = [f"POOL {k}" for k in range(1, 12)] + ["1.2 M", "2.4 M", "NO DIVING", "DEEP END", "SHALLOW"]     # 16 slots, 2 columns x 8 rows


def text_mask(text, h, w, fill=0.56, maxw=0.86):
    adv = 6
    units = len(text) * adv - 1
    s = max(1, int(min(w * maxw / units, h * fill / 7)))
    m = np.zeros((h, w), np.float64)
    x = (w - units * s) // 2
    y0 = (h - 7 * s) // 2
    for ch in text:
        g = GLYPHS[ch]
        for r, row in enumerate(g):
            for c, v in enumerate(row):
                if v == "1":
                    m[y0 + r * s:y0 + (r + 1) * s, x + c * s:x + (c + 1) * s] = 1
        x += adv * s
    return np.clip((blur(m, max(1, s // 5), 2) - 0.5) * 4 + 0.5, 0, 1)


def signs_pixels():
    """The shared sign atlas: each slot 512 x 128, off-white glazed tile with navy letters and a navy border (one atlas for all eleven pools)."""
    rng = np.random.default_rng(11)
    img = np.zeros((1024, 1024, 3))
    for i, t in enumerate(SIGNS):
        r, c = i // 2, i % 2
        slot = np.zeros((128, 512, 3))
        slot[:] = (0.78, 0.78, 0.76)
        m = text_mask(t, 128, 512)
        navy = np.array((0.03, 0.06, 0.16))
        slot = slot * (1 - m[..., None]) + navy * m[..., None]
        slot[:7] = slot[-7:] = slot[:, :7] = slot[:, -7:] = navy
        slot *= (0.97 + 0.05 * vnoise(128, 512, rng, 3, 4, wrap=False))[..., None]
        img[r * 128:(r + 1) * 128, c * 512:(c + 1) * 512] = slot
    return np.clip(img, 0, 0.82)


def sign_uv(text):
    i = SIGNS.index(text)
    r, c = i // 2, i % 2
    return (c * 0.5, 1 - (r + 1) / 8, (c + 1) * 0.5, 1 - r / 8)          # (u0, v0, u1, v1), Blender's v up


def stage_textures():
    from PIL import Image
    d = ROOT / TEXDIR
    d.mkdir(parents=True, exist_ok=True)
    out = {"tile_wall.png": tile_pixels(1024, 8, 5, 0.80, 1), "tile_deck.png": tile_pixels(1024, 4, 7, 0.76, 2, speckle=0.004),
           "plaster.png": plaster_pixels(), "signs.png": signs_pixels()}
    for n, a in out.items():
        Image.fromarray((srgb_encode(a) * 255 + 0.5).astype(np.uint8)).save(d / n, optimize=True)
        print("TEXTURE", n, a.shape, f"linear max {a.max():.3f}", (d / n).stat().st_size)


# ================================================================ brightness: how the page shows the maps
# The page draws a baked material unlit, with no tone mapping: texture x base colour x texel x intensity / pi. The bake's light L (Cycles' diffuse
# pass without colour) is written with a shoulder: texel = G L / (C + G L), and intensity = pi C, so the page shows texture x G L where the light is
# ordinary and rolls off toward texture x C near a lamp, never clipping. C keeps the white tile under 0.98; G is set per pool from its own bake
# (GAIN_TARGET over the median light on the shell), so every pool reads equally bright. --stage encode --gain re-writes the maps without a bake.
CURVE_C = 1.18
GAIN_TARGET = 1.5
CAP = {"Plastic_White": 0.85, "Toy_White": 0.85, "Toy_Yellow": 0.9, "Signs": 0.9, "Chrome": 0.9}


def encode(rgb, gain):
    return srgb_encode(gain * rgb / (CURVE_C + gain * rgb))


def work_dir(sid):
    d = Path(arg("--work", str(ROOT / "work"))) / sid
    d.mkdir(parents=True, exist_ok=True)
    return d


def raw_dir(sid):
    d = Path(arg("--raw-dir", str(ROOT / "work"))) / sid
    d.mkdir(parents=True, exist_ok=True)
    return d


def stage_encode(sid):
    from PIL import Image
    rep_p = work_dir(sid) / "lightmaps.json"
    rep = json.loads(rep_p.read_text())
    gain = arg("--gain", None, float) or rep["0"]["gain"]
    for f in sorted(raw_dir(sid).glob(f"{sid}_[0-9]_raw.npy")):
        n = f.name.split("_")[-2]
        rgb = np.load(f).astype(np.float32)
        Image.fromarray((np.flipud(encode(rgb, gain)) * 255 + 0.5).astype(np.uint8)).save(work_dir(sid) / f"{sid}_{n}.png")
        rep[n]["gain"] = gain
        print("ENCODED", f"{sid}_{n}.png", rgb.shape, "gain", gain)
    rep_p.write_text(json.dumps(rep, indent=1))


if bpy is None:
    if STAGE == "textures":
        stage_textures()
    elif STAGE == "plancheck":
        ok = all([plancheck(int(s[-2:])) for s in scene_list()])
        print("PLANCHECK", "PASS" if ok else "FAIL")
        sys.exit(0 if ok else 1)
    elif STAGE == "encode":
        for s in scene_list():
            stage_encode(s)
    else:
        print("without Blender only --stage textures, plancheck or encode run")
    sys.exit(0)


# ================================================================ Blender from here on
SCENE = K = I = L = GB = BOX = None
BLEND = STILLS = None


def setup(sid):
    global SCENE, K, I, L, GB, BOX, BLEND, STILLS
    SCENE, K = sid, int(sid[-2:])
    I = pool_info(K)
    L = LOOK[K]
    GB = I["S"]
    BOX = I["box"]
    BLEND = ROOT / f"blender/scenes/{sid}.blend"
    STILLS = ROOT / f"docs/renders/{sid}"


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


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, diff=None, tint=None, emit=None, alpha=None, tile=None, two_sided=False):
    """A Principled material. `tint` multiplies the diffuse texture (a Mix node set to Multiply, written by the glTF exporter as baseColorFactor)."""
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
    if diff:
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "UVMap"
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
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    if alpha is not None:
        bsdf.inputs["Alpha"].default_value = alpha
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    m.use_backface_culling = not two_sided
    TILES[name] = tile or 1.0
    MATS[name] = m
    return m


LAMP_EMIT = 6.0           # Lamp_Emit's exported strength (on, as in the bake; the page switches it)
SKY_EMIT = 3.0
EMITS = ("Lamp_Emit", "Sky_Glow")
NOT_BAKED = ("Lamp_Emit", "Sky_Glow", "Pool_Water")


def make_materials():
    t = TINT[L["tile"]]
    TW, TD, PL = TEXDIR + "tile_wall.png", TEXDIR + "tile_deck.png", TEXDIR + "plaster.png"
    material("Tile_Wall", diff=TW, tint=t["wall"], rough=0.22, tile=1.0)
    material("Tile_Pool", diff=TW, tint=t["pool"], rough=0.18, tile=1.0)
    material("Tile_Deck", diff=TD, tint=t["deck"], rough=0.5, tile=1.0)
    material("Tile_Accent", diff=TW, tint=t["accent"], rough=0.2, tile=1.0)
    material("Tile_Trim", diff=TW, tint=t["trim"], rough=0.25, tile=1.0)
    material("Tile_Lip", diff=TD, tint=(0.96, 0.95, 0.91), rough=0.35, tile=1.0)
    material("Tile_Lane", diff=TW, tint=(0.05, 0.08, 0.20), rough=0.2, tile=1.0)
    material("Ceiling_Paint", diff=PL, tint=(0.95, 0.95, 0.94), rough=0.9, tile=2.0)
    material("Door_Paint", diff=PL, tint=(0.86, 0.88, 0.87), rough=0.45, tile=1.0)
    material("Signs", diff=TEXDIR + "signs.png", rough=0.3, tile=1.0)
    material("Chrome", color=(0.70, 0.72, 0.74), rough=0.12)                # metal 0: the page shows base colour x light
    material("Glass_Dark", color=(0.05, 0.07, 0.08), rough=0.08)
    material("Grate_Iron", color=(0.05, 0.05, 0.05), rough=0.6)
    material("Plastic_White", color=(0.80, 0.80, 0.77), rough=0.45)
    material("Pot_Clay", color=(0.45, 0.22, 0.13), rough=0.9)
    material("Plant_Dry", color=(0.26, 0.19, 0.10), rough=0.9)
    material("Toy_Red", color=(0.72, 0.07, 0.05), rough=0.35)
    material("Toy_White", color=(0.80, 0.80, 0.78), rough=0.35)
    material("Toy_Yellow", color=(0.82, 0.60, 0.04), rough=0.35)
    material("Toy_Blue", color=(0.06, 0.22, 0.62), rough=0.5)
    material("Slide_Blue", color=(0.08, 0.32, 0.68), rough=0.25)
    material("Lamp_Emit", color=(1.0, 0.98, 0.95), rough=0.5, emit=((1.0, 0.97, 0.92), LAMP_EMIT))
    material("Sky_Glow", color=(0.92, 0.96, 1.0), rough=0.6, emit=((0.86, 0.93, 1.0), SKY_EMIT))
    material("Pool_Water", color=(0.50, 0.80, 0.86), rough=0.04, alpha=0.32, two_sided=True)


# ---------------------------------------------------------------- geometry helpers (game coordinates in, world space, identity transforms)
def gface(bm, pts, want):
    f = bm.faces.new([bm.verts.new(B(p)) for p in pts])
    f.normal_update()
    if f.normal.dot(B(want)) < 0:
        f.normal_flip()
    return f


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


def ellipsoid(bm, p, rx, ry, rz, seg=14):
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(6, seg // 2 + 1), radius=1.0,
                              matrix=Matrix.Translation(B(p)) @ Matrix.Diagonal((rx, rz, ry, 1)))


def rounded(pts, rad=0.12, n=5):
    """A polyline with its inner corners rounded (quadratic, rad metres back along each leg)."""
    P = [Vector(p) for p in pts]
    out = [P[0]]
    for i in range(1, len(P) - 1):
        a, b, c = P[i - 1], P[i], P[i + 1]
        r = min(rad, (b - a).length / 2, (c - b).length / 2)
        p0 = b + (a - b).normalized() * r
        p2 = b + (c - b).normalized() * r
        for k in range(n + 1):
            t = k / n
            out.append((1 - t) ** 2 * p0 + 2 * (1 - t) * t * b + t ** 2 * p2)
    out.append(P[-1])
    return [tuple(v) for v in out]


def tube(bm, pts, r, seg=10, cap=True):
    """A round tube along game points (parallel-transported rings)."""
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
    if cap:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])


def box_uv(bm, tile):
    """UV0: box projection in metres / tile from world positions, so a texture runs on across pieces (the tiles line up on the metre grid)."""
    uvl = bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y
            u, v = ((gz, gy) if ax == 0 else (gx, gy) if ax == 1 else (gx, gz))
            lp[uvl].uv = (u / tile, v / tile)


ART = DOORS_C = LAYOUT_C = None


def finish(name, bm, mat, coll=None, smooth=False, keep_uv=False, recalc=False, sharp_deg=35):
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
        box_uv(bm, TILES[mat])
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


class Acc:
    """Faces by material, finished as one object per material, named <prefix>_<material>."""
    def __init__(s, prefix):
        s.prefix, s.bms = prefix, {}

    def bm(s, mat):
        return s.bms.setdefault(mat, bmesh.new())

    def face(s, mat, pts, want):
        return gface(s.bm(mat), pts, want)

    def extent(s, mat, *pts):
        """Tiny hidden quads at the corners of the collider this art stands for: the layout check reads one box per object and wants the
        collider's whole box covered. They sit inside the walls or under the slab and are dropped at export (cull_hidden)."""
        for p in pts:
            s.face(mat, [p, (p[0] + 0.01, p[1], p[2]), (p[0] + 0.01, p[1], p[2] + 0.01), (p[0], p[1], p[2] + 0.01)], (0, 1, 0))

    def done(s, coll=None):
        return [finish(f"{s.prefix}_{m}", bm, m, coll) for m, bm in s.bms.items() if bm.faces]


def transform(bm, at, yaw_deg):
    bmesh.ops.transform(bm, matrix=Matrix.Translation(B(at)) @ Matrix.Rotation(math.radians(yaw_deg), 4, "Z"), verts=bm.verts)


# ---------------------------------------------------------------- the walls (inner faces), niches, pilasters, door casing
A = 10.0
WALLS = {   # name: (inward normal, to3(u, v, d): u along the wall, v up, d out from the wall into the room)
    "N": ((0, 0, 1), lambda u, v, d=0.0: (u, v, -A + d)),
    "S": ((0, 0, -1), lambda u, v, d=0.0: (u, v, A - d)),
    "W": ((1, 0, 0), lambda u, v, d=0.0: (-A + d, v, u)),
    "E": ((-1, 0, 0), lambda u, v, d=0.0: (A - d, v, u)),
}
WALL_BANDS = [(0.0, 0.15, "Tile_Accent"), (0.15, 1.2, "Tile_Wall"), (1.2, 1.3, "Tile_Accent"), (1.3, 99.0, "Tile_Wall")]
COL_BANDS = [(0.0, 1.2, "Tile_Wall"), (1.2, 1.3, "Tile_Accent"), (1.3, 99.0, "Tile_Wall")]
DOOR_X = G.DOOR_W / 2


def band_of(bands, v):
    return next(m for a, b, m in bands if a <= v < b)


def grid(acc, wall, u0, u1, v0, v1, holes=(), bands=WALL_BANDS, d=0.0):
    """The wall's face over [u0, u1] x [v0, v1] at offset d, cut at the bands and around the holes (u0, u1, v0, v1)."""
    n, to3 = WALLS[wall]
    us = sorted({u0, u1, *[min(max(x, u0), u1) for h in holes for x in h[:2]]})
    vs = sorted({v0, v1, *[min(max(y, v0), v1) for h in holes for y in h[2:]], *[y for a, b, _ in bands for y in (a, b) if v0 < y < v1]})
    for ua, ub in zip(us, us[1:]):
        for va, vb in zip(vs, vs[1:]):
            if ub - ua < 1e-6 or vb - va < 1e-6:
                continue
            um, vm = (ua + ub) / 2, (va + vb) / 2
            if any(h[0] < um < h[1] and h[2] < vm < h[3] for h in holes):
                continue
            acc.face(band_of(bands, vm), [to3(ua, va, d), to3(ub, va, d), to3(ub, vb, d), to3(ua, vb, d)], n)


def niche(acc, wall, c):
    """A recess 15 cm into the wall: an accent mosaic back, tiled sides and head, a cream sill."""
    n, to3 = WALLS[wall]
    u0, u1 = c - NICHE_W / 2, c + NICHE_W / 2
    v0, v1 = NICHE_V
    dd = -NICHE_D
    acc.face("Tile_Accent", [to3(u0, v0, dd), to3(u1, v0, dd), to3(u1, v1, dd), to3(u0, v1, dd)], n)
    du = tuple(a - b for a, b in zip(to3(1, 0), to3(0, 0)))
    acc.face("Tile_Wall", [to3(u0, v0, dd), to3(u0, v0, 0), to3(u0, v1, 0), to3(u0, v1, dd)], du)
    acc.face("Tile_Wall", [to3(u1, v0, dd), to3(u1, v0, 0), to3(u1, v1, 0), to3(u1, v1, dd)], tuple(-x for x in du))
    acc.face("Tile_Wall", [to3(u0, v1, dd), to3(u1, v1, dd), to3(u1, v1, 0), to3(u0, v1, 0)], (0, -1, 0))
    acc.face("Tile_Lip", [to3(u0, v0, dd), to3(u1, v0, dd), to3(u1, v0, 0.02), to3(u0, v0, 0.02)], (0, 1, 0))
    acc.face("Tile_Lip", [to3(u0, v0, 0.02), to3(u1, v0, 0.02), to3(u1, v0 - 0.04, 0.02), to3(u0, v0 - 0.04, 0.02)], n)


def pilaster(name, wall, c, top):
    n, to3 = WALLS[wall]
    du = tuple(a - b for a, b in zip(to3(1, 0), to3(0, 0)))
    w, dp = 0.18, 0.04

    def build(bm):
        u0, u1 = c - w, c + w
        gface(bm, [to3(u0, 0, dp), to3(u1, 0, dp), to3(u1, top, dp), to3(u0, top, dp)], n)
        gface(bm, [to3(u0, 0, 0), to3(u0, 0, dp), to3(u0, top, dp), to3(u0, top, 0)], tuple(-x for x in du))
        gface(bm, [to3(u1, 0, 0), to3(u1, 0, dp), to3(u1, top, dp), to3(u1, top, 0)], du)
    part(name, "Tile_Trim", build)


def wall_niches(wall):
    return [(c - NICHE_W / 2, c + NICHE_W / 2, NICHE_V[0], NICHE_V[1]) for c in L["niches"].get(wall, [])]


def build_walls():
    h = I["h"]
    ext = {"N": [(-A - T, 0.0, -A - T), (A + T - 0.01, h, -A - 0.01)], "W": [(-A - T, 0.0, -A), (-A - T, h, A - 0.01)],
           "E": [(A + T - 0.01, 0.0, -A), (A + T - 0.01, h, A - 0.01)]}
    for wall in ("N", "E", "W"):
        acc = Acc(f"Wall_{wall}")
        grid(acc, wall, -A, A, 0.0, h, holes=wall_niches(wall))
        for c in L["niches"].get(wall, []):
            niche(acc, wall, c)
        acc.extent("Tile_Wall", *ext[wall])
        acc.done()
    # the south wall, round the door: the parts left and right of it (with the opening's reveals) and the part over it are separate objects,
    # so each stands on its own collider (the layout check reads one box per object)
    holes = wall_niches("S")
    for nm, (u0, u1, v0, v1) in (("SL", (-A, -DOOR_X, 0.0, h)), ("SR", (DOOR_X, A, 0.0, h)), ("ST", (-DOOR_X, DOOR_X, G.DOOR_H, h))):
        acc = Acc(f"Wall_{nm}")
        grid(acc, "S", u0, u1, v0, v1, holes=[x for x in holes if u0 < (x[0] + x[1]) / 2 < u1])
        for c in L["niches"].get("S", []):
            if u0 < c < u1:
                niche(acc, "S", c)
        if nm == "SL":
            acc.face("Tile_Wall", [(-DOOR_X, 0, A), (-DOOR_X, 0, A + T), (-DOOR_X, G.DOOR_H, A + T), (-DOOR_X, G.DOOR_H, A)], (1, 0, 0))
            acc.extent("Tile_Wall", (-A - T, 0.0, A), (-DOOR_X - 0.01, h, A + T - 0.01))
        elif nm == "SR":
            acc.face("Tile_Wall", [(DOOR_X, 0, A), (DOOR_X, 0, A + T), (DOOR_X, G.DOOR_H, A + T), (DOOR_X, G.DOOR_H, A)], (-1, 0, 0))
            acc.extent("Tile_Wall", (A + T - 0.01, h, A + T - 0.01))
        else:
            acc.face("Tile_Wall", [(-DOOR_X, G.DOOR_H, A), (DOOR_X, G.DOOR_H, A), (DOOR_X, G.DOOR_H, A + T), (-DOOR_X, G.DOOR_H, A + T)], (0, -1, 0))
            acc.extent("Tile_Wall", (DOOR_X - 0.01, h, A + T - 0.01))
        acc.done()
    part("Threshold", "Tile_Deck", lambda bm: gface(bm, [(-DOOR_X, 0, A), (DOOR_X, 0, A), (DOOR_X, 0, A + T), (-DOOR_X, 0, A + T)], (0, 1, 0)))
    # the door's casing on the room side: painted steel, 7 cm wide, 2 cm proud; three objects (jambs and head)
    cw, cd = 0.07, 0.02
    for nm, (x0, x1, y0, y1) in (("L", (-DOOR_X - cw, -DOOR_X, 0.0, G.DOOR_H + cw)), ("R", (DOOR_X, DOOR_X + cw, 0.0, G.DOOR_H + cw)),
                                 ("T", (-DOOR_X, DOOR_X, G.DOOR_H, G.DOOR_H + cw))):
        part(f"Casing_{nm}", "Door_Paint", lambda bm, x0=x0, x1=x1, y0=y0, y1=y1: box(bm, x0, x1, y0, y1, A - cd, A))
    for wall in L["pilasters"]:
        for i, c in enumerate((-5.0, 0.0, 5.0) if wall != "S" else (-5.0, 5.0)):
            pilaster(f"Pilaster_{wall}_{i}", wall, c, h)
    # the pool's number by the door, and the deep end's sign on the north wall
    sign_plate("Sign_Pool", f"POOL {K}", "S", -1.6, 1.62, 0.56, 0.14)
    sign_plate("Sign_Deep", "DEEP END", "N", (I["bx0"] + I["bx1"]) / 2, 1.75, 0.64, 0.16)


def sign_plate(name, text, wall, u, v, w, hh):
    n, to3 = WALLS[wall]
    u0, v0, u1, v1 = sign_uv(text)
    s = 1 if wall in ("N", "E") else -1                        # the picture reads left to right seen from the room
    if wall in ("W",):
        s = -1

    def build(bm):
        uvl = bm.loops.layers.uv.new("UVMap")
        d = 0.012
        pts = [to3(u - s * w / 2, v - hh / 2, d), to3(u + s * w / 2, v - hh / 2, d), to3(u + s * w / 2, v + hh / 2, d), to3(u - s * w / 2, v + hh / 2, d)]
        f = bm.faces.new([bm.verts.new(B(p)) for p in pts])
        for lp, (a, b) in zip(f.loops, ((u0, v0), (u1, v0), (u1, v1), (u0, v1))):
            lp[uvl].uv = (a, b)
        f.normal_update()
        if f.normal.dot(B(n)) < 0:
            f.normal_flip()
    part(name, "Signs", build, keep_uv=True)


def deck_marker(name, text, x, z, along_x, w=0.6, hh=0.15, flip=False):
    """A sign tile flush on the deck (2 mm up), reading from the side named by flip."""
    u0, v0, u1, v1 = sign_uv(text)

    def build(bm):
        uvl = bm.loops.layers.uv.new("UVMap")
        if along_x:
            pts = [(x - w / 2, 0.002, z + hh / 2), (x + w / 2, 0.002, z + hh / 2), (x + w / 2, 0.002, z - hh / 2), (x - w / 2, 0.002, z - hh / 2)]
        else:
            pts = [(x - hh / 2, 0.002, z - w / 2), (x - hh / 2, 0.002, z + w / 2), (x + hh / 2, 0.002, z + w / 2), (x + hh / 2, 0.002, z - w / 2)]
        if flip:
            pts = pts[2:] + pts[:2]
        f = bm.faces.new([bm.verts.new(B(p)) for p in pts])
        for lp, (a, b) in zip(f.loops, ((u0, v0), (u1, v0), (u1, v1), (u0, v1))):
            lp[uvl].uv = (a, b)
        f.normal_update()
        if f.normal.dot(B((0, 1, 0))) < 0:
            f.normal_flip()
    part(name, "Signs", build, keep_uv=True)


# ---------------------------------------------------------------- the deck, the lip and the basin
def build_deck_and_basin():
    bx0, bx1, bz0, bz1 = I["bx0"], I["bx1"], I["bz0"], I["bz1"]
    ox0, ox1, oz0, oz1 = bx0 - LIP_W, bx1 + LIP_W, bz0 - LIP_W, bz1 + LIP_W
    deck = Acc("Deck")
    for (x0, x1, z0, z1) in ((-A, A, -A, oz0), (-A, A, oz1, A), (-A, ox0, oz0, oz1), (ox1, A, oz0, oz1)):
        if x1 - x0 > 1e-6 and z1 - z0 > 1e-6:
            deck.face("Tile_Deck", [(x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1)], (0, 1, 0))
    deck.extent("Tile_Deck", (-A - T, -G.POOL_DEEP - G.SLAB, -A - T), (A + T - 0.01, 0.0, A + T - 0.01))   # the deck boxes reach the slab
    deck.done()
    # the lip: a raised (2 cm) tiled coping, 30 cm wide, with a bullnose over the basin's edge; swept round the basin, mitred at the corners
    prof = [(LIP_W, 0.0), (LIP_W, 0.02), (0.02, 0.02)] + [(-0.02 * math.cos(a), -0.02 + 0.04 * math.sin(a)) for a in np.linspace(math.pi / 2, -math.pi / 2, 8)[1:]]
    corners = [(bx0, bz0, -1, -1), (bx1, bz0, 1, -1), (bx1, bz1, 1, 1), (bx0, bz1, -1, 1)]

    def lip(bm):
        rings = [[bm.verts.new(B((cx + sx * d, y, cz + sz * d))) for d, y in prof] for cx, cz, sx, sz in corners]
        top = None
        for i in range(4):
            a, b = rings[i], rings[(i + 1) % 4]
            for j in range(len(prof) - 1):
                f = bm.faces.new((a[j], b[j], b[j + 1], a[j + 1]))
                if i == 0 and j == 1:
                    top = f
        top.normal_update()
        if top.normal.z < 0:                                    # the flat top must look up; the sweep's winding is the same everywhere
            for f in bm.faces:
                f.normal_flip()
    part("Lip", "Tile_Lip", lip)
    # the basin: floors and step tops, risers, the north wall, the two side walls; a waterline band under the lip
    basin = Acc("Basin")
    bands = [(-9.0, -0.28, "Tile_Pool"), (-0.28, 0.01, "Tile_Accent")]
    segs = I["segs"]

    def vface(pts, want):
        """A vertical quad cut at the waterline band."""
        ys = sorted({p[1] for p in pts})
        y0, y1 = ys[0], ys[-1]
        cuts = sorted({y0, y1, *[y for a, b, _ in bands for y in (a, b) if y0 < y < y1]})
        (xa, _, za), (xb, _, zb) = pts[0], pts[1]
        for ya, yb in zip(cuts, cuts[1:]):
            basin.face(band_of(bands, (ya + yb) / 2), [(xa, ya, za), (xb, ya, zb), (xb, yb, zb), (xa, yb, za)], want)
    prev_top = 0.0
    for z0, z1, top, nm in segs:                                   # from the south (z1 = bz1) north
        basin.face("Tile_Pool", [(bx0, top, z0), (bx1, top, z0), (bx1, top, z1), (bx0, top, z1)], (0, 1, 0))
        if top < prev_top - 1e-6:
            vface([(bx0, top, z1), (bx1, top, z1), (bx1, prev_top, z1), (bx0, prev_top, z1)], (0, 0, -1))
        vface([(bx0, top, z0), (bx0, top, z1), (bx0, 0.0, z1), (bx0, 0.0, z0)], (1, 0, 0))
        vface([(bx1, top, z0), (bx1, top, z1), (bx1, 0.0, z1), (bx1, 0.0, z0)], (-1, 0, 0))
        if nm.startswith("Step_"):                                  # a dark nosing stripe on each step's front edge
            basin.face("Tile_Lane", [(bx0, top + 0.002, z0), (bx1, top + 0.002, z0), (bx1, top + 0.002, z0 + 0.06), (bx0, top + 0.002, z0 + 0.06)], (0, 1, 0))
        prev_top = top
    deep = segs[-1][2]
    vface([(bx0, deep, bz0), (bx1, deep, bz0), (bx1, 0.0, bz0), (bx0, 0.0, bz0)], (0, 0, 1))
    # lane lines on the deep and shallow floors (25 cm, 2.5 m apart, T-ends 1.2 m short of the wall) and the targets on the north wall
    cx = (bx0 + bx1) / 2
    half = (bx1 - bx0) / 2 - 1.8
    xs = [cx + o for o in np.arange(-10 + 1.25, 10, 2.5) if abs(o) <= half + 1e-6]
    for z0, z1, top, nm in segs:
        if not nm.startswith(("Deep_Floor", "Shallow_Floor")):
            continue
        y = top + 0.002
        za = z0 + (1.2 if nm.startswith("Deep") else 0.3)
        zb = z1 - 0.3
        for x in xs:
            basin.face("Tile_Lane", [(x - 0.125, y, za), (x + 0.125, y, za), (x + 0.125, y, zb), (x - 0.125, y, zb)], (0, 1, 0))
            if nm.startswith("Deep"):
                basin.face("Tile_Lane", [(x - 0.5, y, za - 0.25), (x + 0.5, y, za - 0.25), (x + 0.5, y, za), (x - 0.5, y, za)], (0, 1, 0))
    for x in xs:
        zw = bz0 + 0.002
        basin.face("Tile_Lane", [(x - 0.125, deep + 0.3, zw), (x + 0.125, deep + 0.3, zw), (x + 0.125, -0.6, zw), (x - 0.125, -0.6, zw)], (0, 0, 1))
        basin.face("Tile_Lane", [(x - 0.4, -0.85, zw), (x + 0.4, -0.85, zw), (x + 0.4, -0.6, zw), (x - 0.4, -0.6, zw)], (0, 0, 1))
    basin.done()
    # the deep end's two drains, the two shut grates (the underwater ways on; the greybox's decor_Grate_ boxes)
    dz = (bz0 + segs[-1][1]) / 2
    for i, x in enumerate((cx - 1.2, cx + 1.2)):
        drain(f"Drain_{i}", x, deep, dz, 0.45)
    for b in GB.boxes:
        if b["name"].startswith("decor_Grate_"):
            grate(b["name"], b["min"], b["max"])
    # depth markers on the deck beside the lip, and NO DIVING at the shallow end
    zs_mid = next((s[0] + s[1]) / 2 for s in segs if s[3] == "Shallow_Floor")
    zd_mid = bz0 + 1.0                                             # north of the ladders
    for side, x in (("W", bx0 - LIP_W - 0.2), ("E", bx1 + LIP_W + 0.2)):
        deck_marker(f"Mark_{side}_shallow", "1.2 M", x, zs_mid, False, flip=(side == "E"))
        deck_marker(f"Mark_{side}_deep", "2.4 M", x, zd_mid, False, flip=(side == "E"))
    deck_marker("Mark_nodiving", "NO DIVING", cx + 1.4, bz1 + LIP_W + 0.2, True)


def drain(name, x, y, z, s):
    def frame(bm):
        w = 0.04
        for (x0, x1, z0, z1) in ((x - s / 2, x + s / 2, z - s / 2, z - s / 2 + w), (x - s / 2, x + s / 2, z + s / 2 - w, z + s / 2),
                                 (x - s / 2, x - s / 2 + w, z - s / 2 + w, z + s / 2 - w), (x + s / 2 - w, x + s / 2, z - s / 2 + w, z + s / 2 - w)):
            box(bm, x0, x1, y, y + 0.012, z0, z1)
    part(f"{name}_Frame", "Chrome", frame)

    def bars(bm):
        for k in range(6):
            xx = x - s / 2 + 0.06 + k * (s - 0.12) / 5
            box(bm, xx - 0.012, xx + 0.012, y, y + 0.008, z - s / 2 + 0.04, z + s / 2 - 0.04)
        gface(bm, [(x - s / 2 + 0.04, y + 0.001, z - s / 2 + 0.04), (x + s / 2 - 0.04, y + 0.001, z - s / 2 + 0.04),
                   (x + s / 2 - 0.04, y + 0.001, z + s / 2 - 0.04), (x - s / 2 + 0.04, y + 0.001, z + s / 2 - 0.04)], (0, 1, 0))
    part(f"{name}_Bars", "Grate_Iron", bars)


def grate(name, mn, mx):
    """The shut way on: a heavy grate over a dark mouth, as big as the greybox's decor box (1 m, 3 cm)."""
    y = mn[1]

    def build(bm):
        x0, x1, z0, z1 = mn[0], mx[0], mn[2], mx[2]
        w = 0.06
        for (a0, a1, c0, c1) in ((x0, x1, z0, z0 + w), (x0, x1, z1 - w, z1), (x0, x0 + w, z0 + w, z1 - w), (x1 - w, x1, z0 + w, z1 - w)):
            box(bm, a0, a1, y, y + 0.03, c0, c1)
        for k in range(1, 8):
            xx = x0 + k * (x1 - x0) / 8
            box(bm, xx - 0.018, xx + 0.018, y, y + 0.028, z0 + w, z1 - w)
        gface(bm, [(x0 + w, y + 0.001, z0 + w), (x1 - w, y + 0.001, z0 + w), (x1 - w, y + 0.001, z1 - w), (x0 + w, y + 0.001, z1 - w)], (0, 1, 0))
    part(name, "Grate_Iron", build)


# ---------------------------------------------------------------- columns
def build_columns():
    h = I["h"]
    for i, c in enumerate(I["cols"]):
        x0, x1, z0, z1 = c["min"][0], c["max"][0], c["min"][2], c["max"][2]
        x, z = (x0 + x1) / 2, (z0 + z1) / 2
        nm = c["name"]
        part(f"{nm}_Plinth", "Tile_Trim", lambda bm: box(bm, x0 - 0.03, x1 + 0.03, 0.0, 0.12, z0 - 0.03, z1 + 0.03))
        part(f"{nm}_Capital", "Tile_Trim", lambda bm: box(bm, x0 - 0.05, x1 + 0.05, h - 0.25, h, z0 - 0.05, z1 + 0.05))
        if L["cols"] == "square":
            acc = Acc(nm)
            for n, pts in (((0, 0, 1), lambda y0, y1: [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),
                           ((0, 0, -1), lambda y0, y1: [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)]),
                           ((1, 0, 0), lambda y0, y1: [(x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0)]),
                           ((-1, 0, 0), lambda y0, y1: [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)])):
                for a, b, m in COL_BANDS:
                    ya, yb = max(a, 0.12), min(b, h - 0.25)
                    if yb > ya:
                        acc.face(m, pts(ya, yb), n)
            acc.done()
        else:                                                       # round: 24 sides, the tiles wrapped round it
            r, seg = (x1 - x0) / 2, 24
            for a, b, m in COL_BANDS:
                ya, yb = max(a, 0.12), min(b, h - 0.25)
                if yb <= ya:
                    continue
                bm = bmesh.new()
                uvl = bm.loops.layers.uv.new("UVMap")
                ring = lambda y: [bm.verts.new(B((x + r * math.cos(2 * math.pi * k / seg), y, z + r * math.sin(2 * math.pi * k / seg)))) for k in range(seg + 1)]
                lo, hi = ring(ya), ring(yb)
                for k in range(seg):
                    f = bm.faces.new((lo[k], lo[k + 1], hi[k + 1], hi[k]))
                    f.normal_update()
                    mid = 2 * math.pi * (k + 0.5) / seg
                    if f.normal.dot(B((math.cos(mid), 0, math.sin(mid)))) < 0:
                        f.normal_flip()
                    for i_, lp in enumerate(f.loops):
                        co = lp.vert.co
                        kk = (lo + hi).index(lp.vert) % (seg + 1)
                        lp[uvl].uv = (1.5 * kk / seg, co.z)       # twelve 12.5 cm tiles round the column (1.57 m), no seam
                finish(f"{nm}_{m}_{int(a * 10)}", bm, m, smooth=True, keep_uv=True, sharp_deg=30)


# ---------------------------------------------------------------- the ceiling: flat with panels, a barrel vault with coves, or skylit wells
LIGHTS = []        # (kind, game pos, watts, colour, size (x, z), aim "down"/"up"/(dir))
WARM_WHITE = (1.0, 0.97, 0.92)
DAYLIGHT = (0.86, 0.93, 1.0)


def panel_spots(avoid=()):
    out = []
    for x in PANEL_GRID:
        for z in PANEL_GRID:
            if any(w[0] - 0.8 < x < w[1] + 0.8 and w[2] - 0.6 < z < w[3] + 0.6 for w in avoid):
                continue
            out.append((x, z))
    return out


def recessed_panels(acc, spots, y, depth=0.08):
    """Holes for the panels in the ceiling face are cut by the caller; here the recess sides, the lit lens and a chrome bezel."""
    pw, pd = PANEL
    for i, (x, z) in enumerate(spots):
        x0, x1, z0, z1 = x - pw / 2, x + pw / 2, z - pd / 2, z + pd / 2
        for (a, b, n) in (((x0, z0), (x1, z0), (0, 0, 1)), ((x1, z1), (x0, z1), (0, 0, -1)), ((x0, z1), (x0, z0), (1, 0, 0)), ((x1, z0), (x1, z1), (-1, 0, 0))):
            acc.face("Ceiling_Paint", [(a[0], y, a[1]), (b[0], y, b[1]), (b[0], y + depth, b[1]), (a[0], y + depth, a[1])], n)
        part(f"Panel_{i:02d}", "Lamp_Emit", lambda bm, x0=x0, x1=x1, z0=z0, z1=z1: gface(bm, [(x0 + 0.02, y + depth - 0.01, z0 + 0.02), (x1 - 0.02, y + depth - 0.01, z0 + 0.02),
                                                                                       (x1 - 0.02, y + depth - 0.01, z1 - 0.02), (x0 + 0.02, y + depth - 0.01, z1 - 0.02)], (0, -1, 0)))

        def bezel(bm, x0=x0, x1=x1, z0=z0, z1=z1):
            w, yy = 0.03, y - 0.003
            for (a0, a1, c0, c1) in ((x0 - w, x1 + w, z0 - w, z0), (x0 - w, x1 + w, z1, z1 + w), (x0 - w, x0, z0, z1), (x1, x1 + w, z0, z1)):
                gface(bm, [(a0, yy, c0), (a1, yy, c0), (a1, yy, c1), (a0, yy, c1)], (0, -1, 0))
        part(f"Panel_{i:02d}_Bezel", "Chrome", bezel)
        LIGHTS.append(("AREA", (x, y + depth - 0.02, z), 95.0, WARM_WHITE, (pw - 0.04, pd - 0.04), "down"))


def ceiling_face(acc, y, holes):
    """The flat ceiling at height y, facing down, cut round holes (x0, x1, z0, z1)."""
    xs = sorted({-A, A, *[v for h in holes for v in h[:2]]})
    zs = sorted({-A, A, *[v for h in holes for v in h[2:]]})
    for xa, xb in zip(xs, xs[1:]):
        for za, zb in zip(zs, zs[1:]):
            xm, zm = (xa + xb) / 2, (za + zb) / 2
            if any(h[0] < xm < h[1] and h[2] < zm < h[3] for h in holes):
                continue
            acc.face("Ceiling_Paint", [(xa, y, za), (xb, y, za), (xb, y, zb), (xa, y, zb)], (0, -1, 0))


def build_ceiling():
    h = I["h"]
    kind = L["ceiling"]
    if kind in ("flat", "skylit"):
        wells = SKY_WELLS.get(K, []) if kind == "skylit" else []
        spots = panel_spots(wells)
        pw, pd = PANEL
        acc = Acc("Ceiling")
        ceiling_face(acc, h, [(x - pw / 2, x + pw / 2, z - pd / 2, z + pd / 2) for x, z in spots] + [tuple(w) for w in wells])
        acc.extent("Ceiling_Paint", (-A - T, h, -A - T), (A + T - 0.01, h + 0.2, A + T - 0.01))
        recessed_panels(acc, spots, h)
        for i, (x0, x1, z0, z1) in enumerate(wells):              # the light well: plaster sides up 1 m, a frosted pane, a chrome frame
            for (a, b, n) in (((x0, z0), (x1, z0), (0, 0, 1)), ((x1, z1), (x0, z1), (0, 0, -1)), ((x0, z1), (x0, z0), (1, 0, 0)), ((x1, z0), (x1, z1), (-1, 0, 0))):
                acc.face("Ceiling_Paint", [(a[0], h, a[1]), (b[0], h, b[1]), (b[0], h + WELL_H, b[1]), (a[0], h + WELL_H, a[1])], n)
            part(f"Sky_{i}", "Sky_Glow", lambda bm, x0=x0, x1=x1, z0=z0, z1=z1: gface(bm, [(x0, h + WELL_H, z0), (x1, h + WELL_H, z0), (x1, h + WELL_H, z1), (x0, h + WELL_H, z1)], (0, -1, 0)))

            def mullions(bm, x0=x0, x1=x1, z0=z0, z1=z1):
                yy = h + WELL_H - 0.06
                for xx in np.linspace(x0, x1, int(round((x1 - x0) / 1.25)) + 1):
                    box(bm, max(x0, xx - 0.03), min(x1, xx + 0.03), yy, yy + 0.05, z0, z1)
                for zz in np.linspace(z0, z1, int(round((z1 - z0) / 1.25)) + 1):
                    box(bm, x0, x1, yy, yy + 0.05, max(z0, zz - 0.03), min(z1, zz + 0.03))
            part(f"Sky_{i}_Frame", "Chrome", mullions)
            LIGHTS.append(("AREA", ((x0 + x1) / 2, h + WELL_H - 0.08, (z0 + z1) / 2), 22.0 * (x1 - x0) * (z1 - z0), DAYLIGHT, (x1 - x0 - 0.1, z1 - z0 - 0.1), "down"))
        acc.done()
        return
    # the barrel vault: a half ellipse across x (vertical where it meets the long walls), along z; ribs over the column rows; cove lights
    rise = VAULT_RISE[h]
    n = 32
    xs = [-A * math.cos(math.pi * i / n) for i in range(n + 1)]
    yv = [h + rise * math.sin(math.pi * i / n) for i in range(n + 1)]
    acc = Acc("Vault")
    for i in range(n):
        xm = (xs[i] + xs[i + 1]) / 2
        acc.face("Ceiling_Paint", [(xs[i], yv[i], -A), (xs[i + 1], yv[i + 1], -A), (xs[i + 1], yv[i + 1], A), (xs[i], yv[i], A)], (-xm / A, -1.0, 0))
    acc.extent("Ceiling_Paint", (-A - T, h, -A - T), (A + T - 0.01, h + 0.2, A + T - 0.01))
    acc.done()
    for wall, nm in (("N", "Lunette_N"), ("S", "Lunette_S")):    # the end walls go up into the vault
        n_, to3 = WALLS[wall]
        lun = Acc(nm)
        for i in range(n):
            lun.face("Tile_Wall", [to3(xs[i], h), to3(xs[i + 1], h), to3(xs[i + 1], yv[i + 1]), to3(xs[i], yv[i])], n_)
        lun.done()

    def ribs(bm):
        for zc in (-7.5, -2.5, 2.5, 7.5):
            z0, z1 = zc - 0.15, zc + 0.15
            inner = [(xs[i] * (1 - 0.012), yv[i] - 0.12 * math.sin(math.pi * i / n)) for i in range(n + 1)]
            for i in range(n):
                xm = (xs[i] + xs[i + 1]) / 2
                gface(bm, [(inner[i][0], inner[i][1], z0), (inner[i + 1][0], inner[i + 1][1], z0), (inner[i + 1][0], inner[i + 1][1], z1), (inner[i][0], inner[i][1], z1)], (-xm, -1.0, 0))
                for zz, s in ((z0, -1), (z1, 1)):
                    gface(bm, [(xs[i], yv[i], zz), (xs[i + 1], yv[i + 1], zz), (inner[i + 1][0], inner[i + 1][1], zz), (inner[i][0], inner[i][1], zz)], (0, 0, s))
    part("Vault_Ribs", "Tile_Trim", ribs)
    for side, s in (("W", -1), ("E", 1)):                         # a tiled trough along each long wall, a lit strip in it lighting the vault
        xw = s * A
        xi = s * (A - 0.3)

        def trough(bm, xw=xw, xi=xi, s=s):
            y0, y1 = h - 0.42, h - 0.22
            gface(bm, [(xi, y0, -A), (xi, y0, A), (xi, y1, A), (xi, y1, -A)], (-s, 0, 0))
            gface(bm, [(xw, y0, -A), (xi, y0, -A), (xi, y0, A), (xw, y0, A)], (0, -1, 0))
            gface(bm, [(xi, y1, -A), (xi + s * 0.04, y1, -A), (xi + s * 0.04, y1, A), (xi, y1, A)], (0, 1, 0))
            gface(bm, [(xi + s * 0.04, y0 + 0.02, -A), (xi + s * 0.04, y0 + 0.02, A), (xi + s * 0.04, y1, A), (xi + s * 0.04, y1, -A)], (s, 0, 0))
            gface(bm, [(xi + s * 0.04, y0 + 0.02, -A), (xw, y0 + 0.02, -A), (xw, y0 + 0.02, A), (xi + s * 0.04, y0 + 0.02, A)], (0, 1, 0))
        part(f"Cove_{side}", "Tile_Trim", trough)
        part(f"Cove_{side}_Strip", "Lamp_Emit", lambda bm, xw=xw, xi=xi, s=s: gface(bm, [(xi + s * 0.08, h - 0.39, -A + 0.1), (xw - s * 0.04, h - 0.39, -A + 0.1),
                                                                                         (xw - s * 0.04, h - 0.39, A - 0.1), (xi + s * 0.08, h - 0.39, A - 0.1)], (0, 1, 0)))
        for zc in (-7.5, -2.5, 2.5, 7.5):
            LIGHTS.append(("AREA", ((xw + xi) / 2 + s * 0.02, h - 0.36, zc), 260.0, WARM_WHITE, (0.16, 4.6), (-s * 0.35, 1.0, 0.0)))
    # three lenses along the crown
    pw, pd = PANEL
    yc = h + rise
    for i, z in enumerate((-5.0, 0.0, 5.0)):
        part(f"Panel_{i:02d}", "Lamp_Emit", lambda bm, z=z: gface(bm, [(-pd / 2, yc - 0.012, z - pw / 2), (pd / 2, yc - 0.012, z - pw / 2),
                                                                         (pd / 2, yc - 0.012, z + pw / 2), (-pd / 2, yc - 0.012, z + pw / 2)], (0, -1, 0)))

        def bezel(bm, z=z):
            w, yy = 0.03, yc - 0.014
            x0, x1, z0, z1 = -pd / 2, pd / 2, z - pw / 2, z + pw / 2
            for (a0, a1, c0, c1) in ((x0 - w, x1 + w, z0 - w, z0), (x0 - w, x1 + w, z1, z1 + w), (x0 - w, x0, z0, z1), (x1, x1 + w, z0, z1)):
                gface(bm, [(a0, yy, c0), (a1, yy, c0), (a1, yy, c1), (a0, yy, c1)], (0, -1, 0))
        part(f"Panel_{i:02d}_Bezel", "Chrome", bezel)
        LIGHTS.append(("AREA", (0.0, yc - 0.03, z), 120.0, WARM_WHITE, (pd - 0.04, pw - 0.04), "down"))


# ---------------------------------------------------------------- the kit's props
def ladder(name, side, xw, z):
    """A chrome pool ladder on a side wall of the basin: two rails over the lip, three treads in the water."""
    s = 1 if side == "W" else -1                                    # +1: the basin is toward +x of the wall

    def build(bm):
        for dz in (-0.25, 0.25):
            pts = [(xw - s * 0.48, 0.0, z + dz), (xw - s * 0.48, 0.62, z + dz), (xw - s * 0.30, 0.86, z + dz), (xw + s * 0.02, 0.86, z + dz),
                   (xw + s * 0.17, 0.62, z + dz), (xw + s * 0.17, -1.25, z + dz), (xw + s * 0.02, -1.38, z + dz)]
            tube(bm, rounded(pts, 0.14, 6), 0.022, 10)
        for y in (-0.32, -0.66, -1.0):
            box(bm, xw + s * 0.03, xw + s * 0.17, y - 0.015, y + 0.015, z - 0.25, z + 0.25)
            cyl(bm, (xw, y, z - 0.18), (xw + s * 0.04, y, z - 0.18), 0.02, seg=8)
            cyl(bm, (xw, y, z + 0.18), (xw + s * 0.04, y, z + 0.18), 0.02, seg=8)
        for dz in (-0.25, 0.25):                                    # the deck flanges
            cyl(bm, (xw - s * 0.48, 0.0, z + dz), (xw - s * 0.48, 0.015, z + dz), 0.05, seg=12)
    part(f"decor_{name}", "Chrome", build, smooth=True)


def handrail():
    """A chrome rail down the middle of the steps, from the deck to the shallow floor."""
    bx0, bx1, bz1 = I["bx0"], I["bx1"], I["bz1"]
    sh = next(s for s in I["segs"] if s[3] == "Shallow_Floor")
    x = (bx0 + bx1) / 2

    def build(bm):
        pts = [(x, 0.0, bz1 + 0.55), (x, 0.92, bz1 + 0.55), (x, 0.92, bz1 + 0.05), (x, -0.30, sh[1] - 0.05), (x, -0.30, sh[1] - 0.55), (x, -1.2, sh[1] - 0.55)]
        tube(bm, rounded(pts, 0.16, 6), 0.024, 10)
        cyl(bm, (x, 0.0, bz1 + 0.55), (x, 0.015, bz1 + 0.55), 0.055, seg=12)
        cyl(bm, (x, -1.2, sh[1] - 0.55), (x, -1.185, sh[1] - 0.55), 0.055, seg=12)
    part("decor_Handrail", "Chrome", build, smooth=True)


def lounger(name, x, z, yaw):
    """A white plastic lounger, its back raised at the head (local -z), built at the origin then turned and placed."""
    w, ln = 0.62, 1.9
    hx = w / 2

    def build(bm):
        y = 0.30
        zf, zh = ln / 2, -ln / 2 + 0.62                             # the flat bed from the foot to the hinge
        for (a, b) in ((-hx, -hx + 0.05), (hx - 0.05, hx)):         # the side rails
            box(bm, a, b, y - 0.06, y, zh, zf)
        n = 10
        for k in range(n):
            z0 = zh + k * (zf - zh) / n + 0.012
            z1 = zh + (k + 1) * (zf - zh) / n - 0.012
            box(bm, -hx + 0.04, hx - 0.04, y - 0.025, y, z0, z1)
        ang = math.radians(42)                                       # the back, raised toward the head
        tmp = bmesh.new()
        for k in range(6):
            a0, a1 = k * 0.62 / 6 + 0.01, (k + 1) * 0.62 / 6 - 0.01
            box(tmp, -hx + 0.04, hx - 0.04, -0.025, 0.0, -a1, -a0)
        for (a, b) in ((-hx, -hx + 0.05), (hx - 0.05, hx)):
            box(tmp, a, b, -0.06, 0.0, -0.62, 0.0)
        bmesh.ops.transform(tmp, matrix=Matrix.Translation(B((0, y, zh))) @ Matrix.Rotation(ang, 4, "X"), verts=tmp.verts)
        me = bpy.data.meshes.new("tmp")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        for (lx, lz) in ((-hx + 0.05, zf - 0.08), (hx - 0.05, zf - 0.08), (-hx + 0.05, zh + 0.05), (hx - 0.05, zh + 0.05)):
            box(bm, lx - 0.03, lx + 0.03, 0.0, y - 0.05, lz - 0.03, lz + 0.03)
        for lx in (-hx - 0.01, hx + 0.01):                           # the wheels at the head
            cyl(bm, (lx - 0.02, 0.07, zh - 0.06), (lx + 0.02, 0.07, zh - 0.06), 0.07, seg=12)
        transform(bm, (x, 0.0, z), yaw)
    part(f"decor_{name}", "Plastic_White", build)


def plant(name, x, z, seed):
    """A dead plant: a terracotta pot, dry soil, bare stalks bent over, a few brown leaves hanging."""
    rng = np.random.default_rng(seed)
    part(f"decor_{name}_Pot", "Pot_Clay", lambda bm: (cyl(bm, (x, 0.0, z), (x, 0.46, z), 0.19, 0.25, seg=18),
                                                      cyl(bm, (x, 0.42, z), (x, 0.50, z), 0.265, 0.27, seg=18)), smooth=True, sharp_deg=50)

    def stalks(bm):
        gface(bm, [(x + 0.24 * math.cos(a), 0.44, z + 0.24 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 14)[:-1]], (0, 1, 0))
        for k in range(7):
            a = rng.uniform(0, 2 * math.pi)
            r0 = rng.uniform(0.0, 0.12)
            p0 = (x + r0 * math.cos(a), 0.44, z + r0 * math.sin(a))
            hgt = rng.uniform(0.5, 1.1)
            lean = rng.uniform(0.15, 0.45)
            droop = rng.uniform(0.1, 0.35)
            pts = [p0, (p0[0] + 0.3 * lean * math.cos(a), p0[1] + hgt * 0.6, p0[2] + 0.3 * lean * math.sin(a)),
                   (p0[0] + lean * math.cos(a), p0[1] + hgt, p0[2] + lean * math.sin(a)),
                   (p0[0] + (lean + droop) * math.cos(a), p0[1] + hgt - droop * 1.2, p0[2] + (lean + droop) * math.sin(a))]
            tube(bm, rounded(pts, 0.2, 4), 0.008, 5)
            for j in range(3):                                      # a few curled dead leaves hanging off it
                t = rng.uniform(0.4, 0.95)
                i0 = int(t * (len(pts) - 1))
                q = Vector(pts[min(i0, len(pts) - 2)]).lerp(Vector(pts[min(i0 + 1, len(pts) - 1)]), t * (len(pts) - 1) - i0)
                b = rng.uniform(0, 2 * math.pi)
                l, wd = rng.uniform(0.09, 0.16), rng.uniform(0.025, 0.045)
                tip = (q.x + 0.3 * l * math.cos(b), q.y - l, q.z + 0.3 * l * math.sin(b))
                sx, sz = -math.sin(b) * wd, math.cos(b) * wd
                gface(bm, [tuple(q), (q.x + sx + 0.5 * (tip[0] - q.x), q.y - l / 2, q.z + sz + 0.5 * (tip[2] - q.z)), tip,
                               (q.x - sx + 0.5 * (tip[0] - q.x), q.y - l / 2, q.z - sz + 0.5 * (tip[2] - q.z))], (math.cos(b), 0.2, math.sin(b)))
    part(f"decor_{name}_Stalks", "Plant_Dry", stalks)


def torus_parts(cx, y, cz, R=0.36, r=0.10, nu=32, nv=12, stripes=8):
    bms = {"Toy_Red": bmesh.new(), "Toy_White": bmesh.new()}
    for k in range(nu):
        m = "Toy_Red" if (k * stripes // nu) % 2 == 0 else "Toy_White"
        bm = bms[m]
        for j in range(nv):
            def P(kk, jj):
                u, v = 2 * math.pi * kk / nu, 2 * math.pi * jj / nv
                return (cx + (R + r * math.cos(v)) * math.cos(u), y + r * math.sin(v), cz + (R + r * math.cos(v)) * math.sin(u))
            pts = [P(k, j), P(k + 1, j), P(k + 1, j + 1), P(k, j + 1)]
            u, v = 2 * math.pi * (k + 0.5) / nu, 2 * math.pi * (j + 0.5) / nv
            gface(bm, pts, (math.cos(v) * math.cos(u), math.sin(v), math.cos(v) * math.sin(u)))
    return bms


def float_ring(name, x, z):
    for m, bm in torus_parts(x, I["water"] + 0.03, z).items():
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        finish(f"decor_{name}_{m}", bm, m, smooth=True, sharp_deg=60)


def duck(name, x, z, yaw):
    y = I["water"]

    def body(bm):
        ellipsoid(bm, (0, 0.10, 0), 0.20, 0.13, 0.28)
        ellipsoid(bm, (0, 0.30, -0.17), 0.12, 0.12, 0.12)
        ellipsoid(bm, (0, 0.20, 0.25), 0.07, 0.06, 0.07)
        transform(bm, (x, y, z), yaw)
    part(f"decor_{name}_Body", "Toy_Yellow", body, smooth=True, sharp_deg=70)

    def beak(bm):
        ellipsoid(bm, (0, 0.28, -0.30), 0.06, 0.03, 0.07, seg=10)
        transform(bm, (x, y, z), yaw)
    part(f"decor_{name}_Beak", "Toy_Red", beak, smooth=True, sharp_deg=70)


def kickboard(name, x, z, yaw):
    def build(bm):
        box(bm, -0.22, 0.22, -0.01, 0.025, -0.15, 0.15)
        cyl(bm, (0, -0.01, -0.15), (0, 0.025, -0.15), 0.22, seg=20)
        transform(bm, (x, I["water"], z), yaw)
    part(f"decor_{name}", "Toy_Blue", build)


def slide(z):
    """A fibreglass water slide on the west deck (pool 8): a chrome ladder up to a small platform, a curving chute down into the deep water."""
    bx0 = I["bx0"]
    yp = 1.55
    xl0, xl1 = -7.0, -6.0                                          # the ladder's foot and top
    xp0, xp1 = -6.0, -5.4                                           # the platform

    # the chute's path (game coordinates): a cubic from the platform's edge, swinging out and back, to just over the water past the lip
    P0, P1, P2, P3 = Vector((xp1, yp, z)), Vector((-4.4, yp - 0.1, z + 0.6)), Vector((-3.6, 0.45, z - 0.5)), Vector((bx0 + 0.55, 0.12, z + 0.1))
    N = 28
    path = []
    for i in range(N + 1):
        t = i / N
        p = (1 - t) ** 3 * P0 + 3 * (1 - t) ** 2 * t * P1 + 3 * (1 - t) * t ** 2 * P2 + t ** 3 * P3
        d = -3 * (1 - t) ** 2 * P0 + 3 * ((1 - t) ** 2 - 2 * (1 - t) * t) * P1 + 3 * (2 * (1 - t) * t - t ** 2) * P2 + 3 * t ** 2 * P3
        d.normalize()
        side = d.cross(Vector((0, 1, 0))).normalized()
        path.append((t, p, d, side, side.cross(d).normalized()))

    def chute(bm):
        prof = [(0.34 * math.cos(a), 0.34 + 0.30 * math.sin(a)) for a in np.linspace(math.pi, 2 * math.pi, 11)]      # the channel, bottom at the path
        outer = [(0.37 * math.cos(a), 0.34 + 0.33 * math.sin(a)) for a in np.linspace(math.pi, 2 * math.pi, 11)]     # 3 cm of fibreglass
        rings_i, rings_o = [], []
        for t, p, d, side, up in path:
            base = p - up * 0.04
            rings_i.append([bm.verts.new(B(tuple(base + side * a + up * b))) for a, b in prof])
            rings_o.append([bm.verts.new(B(tuple(base + side * a + up * b))) for a, b in outer])
        for R in (rings_i, rings_o):
            for a_, b_ in zip(R, R[1:]):
                for k in range(len(prof) - 1):
                    bm.faces.new((a_[k], a_[k + 1], b_[k + 1], b_[k]))
        for i in range(N):                                         # the rims along both edges
            for k in (0, len(prof) - 1):
                bm.faces.new((rings_i[i][k], rings_i[i + 1][k], rings_o[i + 1][k], rings_o[i][k]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)          # a closed band in section (channel, rims, underside): outward everywhere
    part("decor_Slide_Chute", "Slide_Blue", chute, smooth=True, sharp_deg=50)

    legs = [q for q in path if 0.3 < q[0] < 0.85 and q[1].x < bx0 - 0.45]
    legs = [legs[0], legs[-1]] if len(legs) > 1 else legs

    def frame(bm):
        for dz in (-0.33, 0.33):
            tube(bm, [(xl0, 0.0, z + dz), (xl1, yp, z + dz), (xl1 + 0.05, yp + 0.9, z + dz)], 0.025, 10)
            tube(bm, [(xp1, 0.0, z + dz), (xp1, yp, z + dz)], 0.03, 10)
            tube(bm, [(xp0, 0.0, z + dz), (xp0, yp, z + dz)], 0.03, 10)
            tube(bm, rounded([(xp0, yp + 0.9, z + dz), (xp1 - 0.05, yp + 0.9, z + dz), (xp1 + 0.25, yp + 0.35, z + dz)], 0.15, 5), 0.022, 10)
        for k in range(1, 7):
            t = k / 7
            box(bm, xl0 + (xl1 - xl0) * t - 0.07, xl0 + (xl1 - xl0) * t + 0.07, yp * t - 0.02, yp * t + 0.0, z - 0.32, z + 0.32)
        box(bm, xp0, xp1, yp - 0.05, yp, z - 0.36, z + 0.36)
        for t, p, d, side, up in legs:                              # two pairs of legs under the chute, on the deck
            for sg in (-1, 1):
                q = p - up * 0.03 + side * (sg * 0.2)
                tube(bm, [(q.x, 0.0, q.z), (q.x, q.y, q.z)], 0.03, 10)
    part("decor_Slide_Frame", "Chrome", frame, smooth=True)


def build_props():
    for side, x, z in ladder_places(I):
        ladder(f"Ladder_{side}", side, x, z)
    handrail()
    for i, p in enumerate(L["props"]):
        kind = p[0]
        if kind == "lounger":
            lounger(f"Lounger_{i}", p[1], p[2], p[3])
        elif kind == "plant":
            plant(f"Plant_{i}", p[1], p[2], 100 * K + i)
        elif kind == "ring":
            float_ring(f"Ring_{i}", p[1], p[2])
        elif kind == "duck":
            duck(f"Duck_{i}", p[1], p[2], p[3])
        elif kind == "kick":
            kickboard(f"Kick_{i}", p[1], p[2], p[3])
        elif kind == "slide":
            slide(p[1])


def build_water():
    """The water: one surface, see-through and lightly tinted, never baked. Even pools: the basin at y -0.1; odd pools: the whole floor at 0.12."""
    y = I["water"]
    if I["odd"]:
        x0, x1, z0, z1 = -A, A, -A, A
    else:
        x0, x1, z0, z1 = I["bx0"], I["bx1"], I["bz0"], I["bz1"]
    part("Water", "Pool_Water", lambda bm: gface(bm, [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)], (0, 1, 0)))


# ---------------------------------------------------------------- the door leaf (the page swings it), and the layout objects
def build_leaf():
    d = next(x for x in GB.doors if x["name"] == "DoorLeaf_atrium")
    w, hh = d["props"]["width"], d["props"]["height"]
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    t = 0.025

    def add(fn, mi):
        old = set(bm.faces)
        fn()
        for f in bm.faces:
            if f not in old:
                f.material_index = mi
    add(lambda: bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, 0, hh / 2)) @ Matrix.Diagonal((w, 2 * t, hh, 1))), 0)
    for sg in (-1, 1):                                              # both faces: porthole ring and glass, push plate, kick plate
        add(lambda: bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=0.17, radius2=0.17, depth=0.012,
                                          matrix=Matrix.Translation((w / 2, sg * (t + 0.006), 1.52)) @ Matrix.Rotation(math.pi / 2, 4, "X")), 1)
        add(lambda: bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=0.135, radius2=0.135, depth=0.004,
                                          matrix=Matrix.Translation((w / 2, sg * (t + 0.0135), 1.52)) @ Matrix.Rotation(math.pi / 2, 4, "X")), 2)
        add(lambda: bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w - 0.14, sg * (t + 0.003), 1.05)) @ Matrix.Diagonal((0.1, 0.006, 0.3, 1))), 1)
        add(lambda: bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, sg * (t + 0.002), 0.13)) @ Matrix.Diagonal((w - 0.04, 0.004, 0.24, 1))), 1)
    for f in bm.faces:
        f.smooth = False
    bm.normal_update()
    for f in bm.faces:                                              # UV0 in metres (the leaf's own frame)
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            lp[uvl].uv = ((p.y, p.z) if ax == 0 else (p.x, p.z) if ax == 1 else (p.x, p.y))
    me = bpy.data.meshes.new(d["name"])
    bm.to_mesh(me)
    bm.free()
    for m in ("Door_Paint", "Chrome", "Glass_Dark"):
        me.materials.append(MATS[m])
    ob = bpy.data.objects.new(d["name"], me)
    ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
    for k, v in d["props"].items():
        ob[k] = v
    DOORS_C.objects.link(ob)


LAYOUT_PREFIX = ("COL_", "DoorLeaf_", "Link_", "Arrive_", "Spot_", "Zone_", "Marker_")


def gb_names():
    n = {"COL_" + b["name"] for b in GB.boxes if b["col"]} | {b["name"] for b in GB.boxes if b.get("zone")}
    return n | {e["name"] for e in GB.empties} | {d["name"] for d in GB.doors}


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


# ---------------------------------------------------------------- lights and the world
def add_lights():
    c = bpy.data.collections.new("Lights")
    bpy.context.scene.collection.children.link(c)
    for i, (kind, pos, w, col, size, aim) in enumerate(LIGHTS):
        d = bpy.data.lights.new(f"Lamp_{i:02d}", kind)
        d.energy, d.color = w, col
        d.shape = "RECTANGLE"
        d.size, d.size_y = size[0], size[1]
        ob = bpy.data.objects.new(f"Lamp_{i:02d}", d)
        ob.location = B(pos)
        if aim == "up":
            ob.rotation_euler = (math.pi, 0, 0)
        elif aim != "down":                                         # tracked: local Y stays on Blender Y (game -z), so size_y runs along z
            ob.rotation_euler = B(aim).normalized().to_track_quat("-Z", "Y").to_euler()
        c.objects.link(ob)
        try:
            ob.visible_camera = False
        except AttributeError:
            pass


def setup_world():
    sc = bpy.context.scene
    w = bpy.data.worlds.new("Underground")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    bg.inputs["Color"].default_value = (0.004, 0.005, 0.006, 1)
    bg.inputs["Strength"].default_value = 1.0


# ================================================================ build
def build_all():
    global ART, DOORS_C, LAYOUT_C
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for d in (IMG_CACHE, MATS, TILES):
        d.clear()
    LIGHTS.clear()
    sc = bpy.context.scene
    ART, DOORS_C, LAYOUT_C = (bpy.data.collections.new(n) for n in ("Art", "Doors", "Layout"))
    for c in (ART, DOORS_C, LAYOUT_C):
        sc.collection.children.link(c)
    make_materials()
    build_walls()
    build_deck_and_basin()
    build_columns()
    build_ceiling()
    build_props()
    build_water()
    build_leaf()
    build_layout()
    add_lights()
    setup_world()
    LAYOUT_C.hide_render = True
    tris = sum(len(p.vertices) - 2 for o in ART.objects for p in o.data.polygons)
    print(f"ART {SCENE}: {len(ART.objects)} objects, about {tris} triangles; {len(LIGHTS)} lights")


def open_collections():
    global ART, DOORS_C, LAYOUT_C
    ART, DOORS_C, LAYOUT_C = (bpy.data.collections.get(n) for n in ("Art", "Doors", "Layout"))
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
    print(f"layout check: scene {SCENE}, {len(parts)} visible meshes, {len(world['colliders'])} colliders")
    bad = check_layout.report(check_layout.check(parts, world, {}))
    print(f"CHECK_LAYOUT {SCENE} exit", 1 if bad else 0)
    return bad


# ---------------------------------------------------------------- bake
GROUPS = [["Tile_Wall", "Tile_Pool", "Tile_Deck", "Tile_Accent", "Tile_Trim", "Tile_Lip", "Tile_Lane", "Ceiling_Paint"],
          ["Chrome", "Door_Paint", "Glass_Dark", "Signs", "Grate_Iron", "Plastic_White", "Pot_Clay", "Plant_Dry", "Toy_Red", "Toy_White",
           "Toy_Yellow", "Toy_Blue", "Slide_Blue"]]
PAGES = [2048, 1024]
LEAVES_PAGE = 1
UV_SCALE = {"Ceiling_Paint": 0.6, "Tile_Lane": 0.6, "Grate_Iron": 0.6, "Glass_Dark": 0.5}


def cull_hidden(bm, mname):
    """Drop the faces never seen: the extent quads inside the walls (|x| or |z| past 10.17 m: the niches' backs at 10.15 stay) and under the
    slab, and any upward-facing ceiling face above the ceiling's plane."""
    bm.normal_update()
    h = I["h"]
    bad = []
    for f in bm.faces:
        c = f.calc_center_median()
        gx, gy, gz = c.x, c.z, -c.y
        if abs(gx) > A + 0.17 or abs(gz) > A + 0.17 or gy < -G.POOL_DEEP - G.SLAB + 0.01 or (mname == "Ceiling_Paint" and f.normal.z > 0.9 and gy > h + 0.1):
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
    for ob in art.objects:
        assert len(ob.data.materials) == 1, ob.name
        mname = ob.data.materials[0].name
        bm = by_mat.setdefault(mname, bmesh.new())
        tmp = bmesh.new()
        tmp.from_mesh(ob.data)
        tmp.transform(ob.matrix_world)
        cull_hidden(tmp, mname)
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


def setup_cycles(samples, bake=False):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = samples
    cy.use_adaptive_sampling = False
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces, cy.transmission_bounces, cy.transparent_max_bounces = 12, 8, 4, 8, 16
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
    M = ob.matrix_world
    return sum(p.area for p in ob.data.polygons) * abs(M.to_3x3().determinant()) ** (2 / 3)


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
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        if o.name in UV_SCALE:
            d = o.data.uv_layers["lightmap"].data
            us = np.array([x.uv for x in d]) * UV_SCALE[o.name]
            d.foreach_set("uv", us.ravel())
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / page, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    plain = [o for o in objs if o.name not in UV_SCALE]
    a3 = sum(area3d(o) for o in plain)
    au = sum(uv_area(o, "lightmap") for o in plain)
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
    path = str(work_dir(SCENE) / "dn.exr")
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


def bake_page(n, objs, S, samples):
    bpy.context.scene.cycles.samples = samples
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
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
    for o in objs:
        for slot in o.material_slots:
            nt = slot.material.node_tree
            for nd in [nd for nd in nt.nodes if nd.name.startswith("BAKE_TARGET")]:
                nt.nodes.remove(nd)
    a = denoise_image(img, S)
    bpy.data.images.remove(img)
    return a[..., :3].copy()


def set_emit(mname, strength):
    m = bpy.data.materials.get(mname)
    if m:
        next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Emission Strength"].default_value = strength


def stage_bake():
    import time
    exp = make_export_objects()
    leaves = sorted(bpy.data.collections["Doors"].objects, key=lambda o: o.name)
    bpy.data.collections["Art"].hide_render = True
    bpy.data.collections["Art"].hide_viewport = True
    bpy.data.collections["Layout"].hide_render = True
    if "Pool_Water" in exp:
        exp["Pool_Water"].hide_render = True                       # baked as seen through clear water
    setup_cycles(SAMPLES, bake=True)
    set_emit("Lamp_Emit", LAMP_EMIT)
    set_emit("Sky_Glow", SKY_EMIT)
    report, gain = {}, None
    for n, mats in enumerate(GROUPS):
        objs = [exp[m] for m in mats if m in exp] + (leaves if n == LEAVES_PAGE else [])
        print(f"lightmap {n}: {[o.name for o in objs]}")
        dens = lightmap_uv(objs, PAGES[n])
        t0 = time.time()
        rgb = bake_page(n, objs, PAGES[n], SAMPLES)
        peak = rgb.max(axis=2)
        sel = peak > 1e-5
        pc = np.percentile(peak[sel], [50, 90, 99, 99.5, 100]) if sel.any() else [1.0] * 5
        if gain is None:                                           # the pool's gain, from its shell's median light
            gain = GAIN_TARGET / max(float(pc[0]), 1e-6)
        np.save(raw_dir(SCENE) / f"{SCENE}_{n}_raw.npy", rgb.astype(np.float16))
        out = np.ones((PAGES[n], PAGES[n], 4), np.float32)
        out[..., :3] = encode(rgb, gain)
        png = bpy.data.images.new(f"LM_{n}_png", PAGES[n], PAGES[n], alpha=False)
        png.colorspace_settings.name = "Non-Color"
        png.pixels.foreach_set(out.ravel())
        png.filepath_raw = str(work_dir(SCENE) / f"{SCENE}_{n}.png")
        png.file_format = "PNG"
        png.save()
        bpy.data.images.remove(png)
        report[n] = {"map": n, "size": PAGES[n], "gain": round(gain, 4), "C": CURVE_C, "px_per_m": round(dens, 1),
                     "p50_p90_p99_p995_max": [round(float(v), 4) for v in pc], "samples": SAMPLES, "device": bpy.context.scene.cycles.device,
                     "seconds": round(time.time() - t0), "materials": [m for m in mats if m in exp] + ([o.name for o in leaves] if n == LEAVES_PAGE else [])}
        print("  baked", report[n])
    (work_dir(SCENE) / "lightmaps.json").write_text(json.dumps(report, indent=1))
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Art"].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


def set_intensities():
    rep = json.loads((work_dir(SCENE) / "lightmaps.json").read_text())
    for idx, r in rep.items():
        for nm in r["materials"]:
            ob = bpy.data.objects.get(nm)
            mats = [bpy.data.materials.get(nm)] if bpy.data.materials.get(nm) else [s.material for s in ob.material_slots] if ob else []
            for m in mats:
                if m is None:
                    continue
                m["lightmap"] = f"world/lightmaps/{SCENE}_{idx}.webp"
                m["lightmap_intensity"] = round(math.pi * CURVE_C * CAP.get(m.name, 1.0), 4)


# ---------------------------------------------------------------- privacy: the saved file and the GLB carry no paths, names or stamps
KEEP_PROPS = {"lightmap", "lightmap_intensity"}
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
    set_intensities()
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    bpy.data.collections["Art"].hide_viewport = True
    leaves = sorted(bpy.data.collections["Doors"].objects, key=lambda o: o.name)
    stash = {o.name: {k: o[k] for k in o.keys()} for o in leaves}        # the leaf's layout properties are in world/<scene>.json, not in the GLB
    for o in leaves:
        for k in list(o.keys()):
            del o[k]
    set_emit("Lamp_Emit", LAMP_EMIT)
    set_emit("Sky_Glow", SKY_EMIT)
    bpy.ops.object.select_all(action="DESELECT")
    for o in list(exp.objects) + leaves:
        o.hide_set(False)
        o.hide_render = False
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = work_dir(SCENE) / f"{SCENE}_raw.glb"
    scrub_private()
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False, export_animations=False)
    for o in leaves:
        for k, v in stash[o.name].items():
            o[k] = v
    print("EXPORTED", raw, raw.stat().st_size)
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


def shots():
    a = I["empties"]["Arrive_atrium"]["pos"]
    h = I["h"]
    cx, cz = (I["bx0"] + I["bx1"]) / 2, (I["bz0"] + I["bz1"]) / 2
    sx = -1 if cx > 0.5 else 1
    wide = ((sx * 9.3, h - 0.55, 9.3), (cx - sx * 2.0, -0.8, cz - 2.0), 74.0)
    dp, dt = L["detail"]
    return {"1_arrival": ((a[0], 1.55, a[2]), (a[0], 0.75, a[2] - 8.0), 72.0), "2_wide": wide, "3_detail": (dp, dt, 62.0)}


CEIL_PREFIX = ("Ceiling_", "Vault", "Lunette_", "Cove_", "Panel_", "Sky_")


def stage_render():
    sc = bpy.context.scene
    STILLS.mkdir(parents=True, exist_ok=True)
    scrub_private()
    for c in ("Export", "Layout"):
        if c in bpy.data.collections:
            bpy.data.collections[c].hide_render = True
            bpy.data.collections[c].hide_viewport = True
    bpy.data.collections["Art"].hide_render = False
    set_emit("Lamp_Emit", LAMP_EMIT)
    set_emit("Sky_Glow", SKY_EMIT)
    setup_cycles(arg("--render-samples", 128, int))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = arg("--noise", 0.03, float)
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    rep_p = work_dir(SCENE) / "lightmaps.json"
    gain = json.loads(rep_p.read_text())["0"]["gain"] if rep_p.exists() else 1.0
    expo = arg("--exposure", 0.0, float) + math.log2(max(gain, 1e-3)) - 0.6
    which = arg("--only", "all")
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    cams = {k: look_cam(k, p, t, f) for k, (p, t, f) in shots().items()}
    plan = look_cam("plan", (0.0, 30.0, 0.0), None, ortho=21.0)
    plan.rotation_euler = (0, 0, 0)
    arts = list(bpy.data.collections["Art"].objects) + list(bpy.data.collections["Doors"].objects)
    ceil = [o for o in arts if o.name.startswith(CEIL_PREFIX)]
    todo = [(k, v, (1920, 1080)) for k, v in cams.items()] + [("4_plan", plan, (1400, 1400))]
    for key, cam, (w, h) in todo:
        if which not in ("all", key):
            continue
        sc.camera = cam
        sc.view_settings.exposure = expo + (0.4 if key == "4_plan" else 0.0)
        for o in arts:
            o.visible_camera = True
        if key == "4_plan":
            for o in ceil:
                o.visible_camera = False
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, arg("--scale", 100, int)
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        to_docs = key != "4_plan" and not arg("--work-stills")
        path = STILLS / f"{key}.jpg" if to_docs else work_dir(SCENE) / f"{key}.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 400_000 and q > 40 and to_docs:
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        strip_jpeg_comments(path)
        print("STILL", SCENE, key, path.name, path.stat().st_size, "q", q, "exposure", round(sc.view_settings.exposure, 2))
    for o in arts:
        o.visible_camera = True


# ================================================================ main
if __name__ == "__main__":
    ST = set(STAGE.split(","))
    summary = []
    import traceback
    failed = []
    for sid in scene_list():
        try:
            setup(sid)
            print(f"=== {sid}: {L['tile']} tile, {L['ceiling']} ceiling, columns {L['cols']}, stages {sorted(ST)}")
            if ST & {"art"}:
                build_all()
                save_blend()
            else:
                bpy.ops.wm.open_mainfile(filepath=str(BLEND))
                open_collections()
                LIGHTS.clear()
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
    print("POOLS ALL DONE", "failed:", failed or "none")
    sys.exit(1 if failed else 0)
