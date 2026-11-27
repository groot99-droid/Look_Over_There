"""Dresses, lights and bakes Right Door, Wrong Exit's Phase C rooms 16 to 34 (the teal wing and the institution, docs/renders/rdwe_greybox/ROOMS.md)
in Blender, round their greybox layouts (tools/blender/build_rdwe_greybox.py), with the kit in tools/blender/rdwe_rooms2_kit.py.

    blender -b --factory-startup --python tools/blender/build_rdwe_rooms2.py -- --scenes rdwe_void_room[,rdwe_lights_out,...] \\
        [--stage art,layout,check,bake,export,render] [--samples 256] [--render-samples 96]
    python tools/blender/rdwe_rooms2_pack.py <scene>         (grades the bake into world/lightmaps/<scene>_<n>.webp, writes world/<scene>.glb)

Each scene: blender/scenes/<scene>.blend, world/<scene>.json (export_scene.py), work/<scene>/ (the raw bake, the raw GLB, the owner's stills) and
docs/renders/<scene>/ (the three review stills). Several scenes run one after another in one Blender.

The look is Super Liminal's: rooms that are nearly ordinary, saturated and a little wrong, lit like a real interior. Every texture is either a CC0
file in blender/textures/rdwe_rooms2/ (Poly Haven and ambientCG) or generated here with numpy (fixed seeds, own work).
"""
import math
import sys
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import rdwe_rooms2_kit as KT            # noqa: E402
from rdwe_rooms2_kit import G          # noqa: E402  the greybox model
from rdwe_rooms2_kit import (K, B, box, cube, bx, cyl, sphere, quad, poly, torus, disc, part, finish, Painter, picture, light,  # noqa: E402
                             wall_box, on_wall, skirting, casings, cornice, rail, wall_band, gb_box, shell_art, vnoise, blur, text_lines,
                             text_mask, mat, set_uv_rect)

WARM, COOL, TUBE = (1.0, 0.80, 0.58), (0.72, 0.82, 1.0), (0.92, 0.96, 1.0)


# ================================================================ furniture helpers (each solid piece over its own collider)
def legs4(bm, x0, x1, z0, z1, y0, y1, r=0.022, inset=0.05, round_=True):
    for x in (x0 + inset, x1 - inset):
        for z in (z0 + inset, z1 - inset):
            if round_:
                cyl(bm, (x, y0, z), (x, y1, z), r, r, 8)
            else:
                box(bm, x - r, x + r, y0, y1, z - r, z + r)


def table(name, b, top, legm, t=0.04, r=0.022, inset=0.06, round_=False, apron=True):
    mn, mx = b["min"], b["max"]
    part(name, top, lambda bm: box(bm, mn[0], mx[0], mx[1] - t, mx[1], mn[2], mx[2]))

    def lg(bm):
        legs4(bm, mn[0], mx[0], mn[2], mx[2], 0.0, mx[1] - t, r, inset, round_)
        if apron:
            box(bm, mn[0] + inset, mx[0] - inset, mx[1] - t - 0.08, mx[1] - t, mn[2] + inset, mn[2] + inset + 0.02)
            box(bm, mn[0] + inset, mx[0] - inset, mx[1] - t - 0.08, mx[1] - t, mx[2] - inset - 0.02, mx[2] - inset)
    part(name + "_Legs", legm, lg)


def chair(name, b, seat, frame, back="N", seat_h=0.46, cushion=None):
    """A chair filling box b, its back on side `back` (the side it faces away from)."""
    mn, mx = b["min"], b["max"]
    x0, x1, z0, z1, h = mn[0], mx[0], mn[2], mx[2], mx[1]

    def fr(bm):
        legs4(bm, x0, x1, z0, z1, 0.0, seat_h - 0.04, 0.018, 0.04, False)
        t = 0.04
        if back == "N":
            box(bm, x0 + 0.02, x1 - 0.02, seat_h, h, z0, z0 + t)
        elif back == "S":
            box(bm, x0 + 0.02, x1 - 0.02, seat_h, h, z1 - t, z1)
        elif back == "W":
            box(bm, x0, x0 + t, seat_h, h, z0 + 0.02, z1 - 0.02)
        else:
            box(bm, x1 - t, x1, seat_h, h, z0 + 0.02, z1 - 0.02)
    part(name, frame, fr)
    part(name + "_Seat", seat, lambda bm: box(bm, x0, x1, seat_h - 0.05, seat_h + (0.04 if cushion else 0.0), z0, z1))


def armchair(name, b, fabric, legm, back="N", seat_h=0.42):
    mn, mx = b["min"], b["max"]
    x0, x1, z0, z1, h = mn[0], mx[0], mn[2], mx[2], mx[1]
    arm = 0.14

    def body(bm):
        box(bm, x0, x1, 0.12, seat_h, z0, z1)
        if back in "NS":
            zb = (z0, z0 + 0.2) if back == "N" else (z1 - 0.2, z1)
            box(bm, x0, x1, seat_h, h, *zb)
            box(bm, x0, x0 + arm, seat_h, seat_h + 0.22, z0, z1)
            box(bm, x1 - arm, x1, seat_h, seat_h + 0.22, z0, z1)
        else:
            xb = (x0, x0 + 0.2) if back == "W" else (x1 - 0.2, x1)
            box(bm, *xb, seat_h, h, z0, z1)
            box(bm, x0, x1, seat_h, seat_h + 0.22, z0, z0 + arm)
            box(bm, x0, x1, seat_h, seat_h + 0.22, z1 - arm, z1)
    part(name, fabric, body)
    part(name + "_Legs", legm, lambda bm: legs4(bm, x0, x1, z0, z1, 0.0, 0.12, 0.02, 0.06, True))


def sofa(name, b, fabric, legm, back="N", seat_h=0.44, arm=0.2):
    armchair(name, b, fabric, legm, back, seat_h)


def cabinet(name, b, body, front=None, doors=2, face="S", plinth=0.08, handle="Chrome"):
    mn, mx = b["min"], b["max"]
    part(name, body, lambda bm: (box(bm, mn[0], mx[0], plinth, mx[1], mn[2], mx[2]),
                                 box(bm, mn[0] + 0.02, mx[0] - 0.02, 0.0, plinth, mn[2] + 0.02, mx[2] - 0.02)))

    def fr(bm):
        if face in "NS":
            z = mx[2] + 0.004 if face == "S" else mn[2] - 0.004
            for k in range(doors):
                a0 = mn[0] + (mx[0] - mn[0]) * k / doors + 0.01
                a1 = mn[0] + (mx[0] - mn[0]) * (k + 1) / doors - 0.01
                box(bm, a0, a1, plinth + 0.02, mx[1] - 0.03, min(z, z - 0.004 if face == "S" else z + 0.004), max(z, z - 0.004 if face == "S" else z + 0.004))
        else:
            x = mx[0] + 0.004 if face == "E" else mn[0] - 0.004
            for k in range(doors):
                a0 = mn[2] + (mx[2] - mn[2]) * k / doors + 0.01
                a1 = mn[2] + (mx[2] - mn[2]) * (k + 1) / doors - 0.01
                box(bm, min(x, x - 0.004 if face == "E" else x + 0.004), max(x, x - 0.004 if face == "E" else x + 0.004), plinth + 0.02, mx[1] - 0.03, a0, a1)
    if front:
        part(name + "_Front", front, fr)


def plant(tag, cx, cz, y0, height, rng, pot_r=0.2, pot_mat="Pot_Clay", leaf_mat="Plant_Leaf", spread=0.45, solid=True):
    """A potted plant: the pot and the leaves, both solid over the plant's collider (the leaves kept inside its footprint), or both decor."""
    nm = tag if solid else "decor_" + tag
    part(nm, pot_mat, lambda bm: cyl(bm, (cx, y0, cz), (cx, y0 + pot_r * 1.6, cz), pot_r * 0.78, pot_r, 14))
    if solid and tag in K.BOX:
        b = K.BOX[tag]
        half = min(b["max"][0] - cx, cx - b["min"][0], b["max"][2] - cz, cz - b["min"][2])
        height = b["max"][1] - y0 - pot_r * 1.5
        spread = min(spread, half / max(height, 0.1))

    def leaves(bm):
        n = 14
        for i in range(n):
            a = 2 * math.pi * i / n + rng.uniform(-0.2, 0.2)
            ln = height * (1.0 if i == 0 else rng.uniform(0.55, 1.0))
            up = 1.0 if i == 0 else rng.uniform(0.5, 1.0)
            base = Vector((cx, y0 + pot_r * 1.5, cz))
            tip = base + Vector((math.cos(a) * spread * ln, up * ln, math.sin(a) * spread * ln))
            mid = (base + tip) / 2 + Vector((0, 0.08, 0))
            side = Vector((-math.sin(a), 0, math.cos(a))) * 0.07 * ln
            poly(bm, [tuple(base), tuple(mid + side), tuple(tip), tuple(mid - side)])
    part((tag if solid and tag in K.BOX else "decor_" + tag) + "_Leaves", leaf_mat, leaves)


def frame_picture(tag, side, a, y, w, h, img_mat, frame_mat="Frame_Gilt", uv=(0, 0, 1, 1), d=0.03, flip=False):
    """A framed picture on wall `side`, centred at a along it, its middle at height y (decor: it is flat on the wall)."""
    n = KT.SIDE_N[side]
    c = on_wall(side, a, y, d + 0.002)
    picture("decor_" + tag, img_mat, c, n, w, h, uv, flip=flip)
    part("decor_" + tag + "_Frame", frame_mat, lambda bm: (
        wall_box(bm, side, a - w / 2 - 0.05, a + w / 2 + 0.05, y + h / 2, y + h / 2 + 0.05, 0.0, d),
        wall_box(bm, side, a - w / 2 - 0.05, a + w / 2 + 0.05, y - h / 2 - 0.05, y - h / 2, 0.0, d),
        wall_box(bm, side, a - w / 2 - 0.05, a - w / 2, y - h / 2, y + h / 2, 0.0, d),
        wall_box(bm, side, a + w / 2, a + w / 2 + 0.05, y - h / 2, y + h / 2, 0.0, d)))


def troffer(bm_lit, bm_frame, x, z, w=0.6, l=1.2, along="x"):
    """A ceiling troffer: the diffuser (into bm_lit) and its frame (into bm_frame)."""
    hw, hl = (l / 2, w / 2) if along == "x" else (w / 2, l / 2)
    y = K.H
    box(bm_frame, x - hw - 0.03, x + hw + 0.03, y - 0.03, y, z - hl - 0.03, z + hl + 0.03)
    box(bm_lit, x - hw, x + hw, y - 0.034, y - 0.03, z - hl, z + hl)


def pendant(tag, x, z, drop, shade_r=0.22, shade_mat="Shade", cord_mat="Iron", bulb=True, watts=60, color=WARM, sets=None, kind="cone"):
    y1 = K.H
    yb = K.H - drop
    part("decor_" + tag + "_Cord", cord_mat, lambda bm: cyl(bm, (x, yb + 0.12, z), (x, y1, z), 0.006, 0.006, 6))
    if kind == "cone":
        part("decor_" + tag + "_Shade", shade_mat, lambda bm: cyl(bm, (x, yb - 0.05, z), (x, yb + 0.14, z), shade_r, 0.04, 20, cap=False))
    elif kind == "globe":
        part("decor_" + tag + "_Shade", shade_mat, lambda bm: sphere(bm, (x, yb, z), shade_r, 16))
    if bulb:
        part("decor_" + tag + "_Bulb", "Lamp_Emit", lambda bm: sphere(bm, (x, yb - 0.02, z), 0.045, 10))
    light("POINT", (x, yb - 0.08, z), watts, color, 0.06, sets)


def books_row(P, x0, x1, y0, z0, z1, rng, along="x", lean=0.0, hmax=0.3, keys=None):
    """A row of books standing on a shelf at y0, from x0 to x1 (along x) in a slot z0..z1 deep, into the Painter P."""
    keys = keys or ["book_red", "book_green", "book_blue", "book_tan", "book_black", "book_ochre", "book_cream", "book_plum"]
    a = x0
    while a < x1 - 0.03:
        t = rng.uniform(0.025, 0.06)
        hh = rng.uniform(0.6, 1.0) * hmax
        d = (z1 - z0) * rng.uniform(0.75, 0.95)
        b1 = min(a + t, x1)
        if along == "x":
            P.add(keys[rng.integers(len(keys))], box, a, b1, y0, y0 + hh, z0, z0 + d)
        else:
            P.add(keys[rng.integers(len(keys))], box, z0, z0 + d, y0, y0 + hh, a, b1)
        a = b1 + rng.uniform(0.0, 0.006)


def rug(tag, x0, x1, z0, z1, mname, y=0.0, t=0.012):
    part("decor_" + tag, mname, lambda bm: box(bm, x0, x1, y, y + t, z0, z1))


def strip_lines(bm, side, lo, hi, y0, y1, step, width, horiz=True, vert=True, d=0.004):
    """A grid of thin strips on wall `side` (for the green grid)."""
    if vert:
        a = lo
        while a <= hi + 1e-6:
            wall_box(bm, side, a - width / 2, a + width / 2, y0, y1, 0.0, d)
            a += step
    if horiz:
        y = y0
        while y <= y1 + 1e-6:
            wall_box(bm, side, lo, hi, y - width / 2, y + width / 2, 0.0, d)
            y += step


# ================================================================ generated pictures
def g_damask(bg, fg, S=512, seed=3, scale=2):
    def f():
        rng = np.random.default_rng(seed)
        yy, xx = (np.mgrid[0:S, 0:S] + 0.5) / S
        fx = np.abs(((xx * scale) % 1) - 0.5) * 2
        fy = (yy * scale) % 1
        r = np.sqrt((fx * 0.9) ** 2 + ((fy - 0.5) * 1.3) ** 2)
        th = np.arctan2(fy - 0.5, fx + 1e-3)
        leaf = np.clip(((0.30 + 0.10 * np.cos(3 * th) + 0.05 * np.cos(7 * th)) - r) / 0.02, 0, 1) * np.clip((r - 0.08) / 0.02, 0, 1)
        img = np.ones((S, S, 3), np.float32) * np.array(bg)
        img = img * (1 - leaf[..., None]) + np.array(fg) * leaf[..., None]
        return img * (0.9 + 0.14 * vnoise(S, S, rng, 5, 4)[..., None])
    return f


def g_stripes(c1, c2, n=8, S=256, seed=4):
    def f():
        rng = np.random.default_rng(seed)
        yy, xx = (np.mgrid[0:S, 0:S] + 0.5) / S
        st = ((xx * n) % 1) < 0.5
        img = np.where(st[..., None], np.array(c1), np.array(c2)).astype(np.float32)
        return img * (0.93 + 0.1 * vnoise(S, S, rng, 4, 4)[..., None])
    return f


def g_checker(c1, c2, n=2, S=512, grout=None, seed=6):
    def f():
        rng = np.random.default_rng(seed)
        yy, xx = np.mgrid[0:S, 0:S]
        c = ((xx * n // S) + (yy * n // S)) % 2
        img = np.where(c[..., None] == 0, np.array(c1), np.array(c2)).astype(np.float32)
        if grout:
            g = ((xx % (S // n)) < 2) | ((yy % (S // n)) < 2)
            img[g] = grout
        return img * (0.9 + 0.14 * vnoise(S, S, rng, 5, 4)[..., None])
    return f


def g_tiles(c, grout, n=16, S=512, accent=None, seed=7, jitter=0.05):
    def f():
        rng = np.random.default_rng(seed)
        yy, xx = np.mgrid[0:S, 0:S]
        cell = S // n
        tid = (yy // cell) * n + (xx // cell)
        shade = rng.uniform(1 - jitter, 1 + jitter, n * n)[tid]
        img = np.ones((S, S, 3), np.float32) * np.array(c) * shade[..., None]
        if accent:
            acc = rng.random(n * n)[tid] < accent[1]
            img[acc] = np.array(accent[0]) * shade[acc][..., None]
        g = ((xx % cell) < max(1, cell // 12)) | ((yy % cell) < max(1, cell // 12))
        img[g] = grout
        return img * (0.94 + 0.08 * vnoise(S, S, rng, 4, 8)[..., None])
    return f


def g_carpet(base, fleck, S=512, seed=8, pattern=None):
    def f():
        rng = np.random.default_rng(seed)
        n = vnoise(S, S, rng, 6, 8)
        pile = vnoise(S, S, rng, 2, 128)
        img = np.ones((S, S, 3), np.float32) * np.array(base)
        fl = (rng.random((S, S)) < 0.04)
        img[fl] = np.array(fleck)
        img = blur(img, 1, 1)
        if pattern:
            img = pattern(img, rng)
        return img * (0.82 + 0.26 * n[..., None]) * (0.92 + 0.1 * pile[..., None])
    return f


def stars_pattern(col, density=0.0025, size=3):
    def p(img, rng):
        S = img.shape[0]
        for _ in range(int(S * S * density / 40)):
            y, x = rng.integers(size, S - size, 2)
            for k in range(-size, size + 1):
                img[y, x + k] = col
                img[y + k, x] = col
        return img
    return p


def g_night_sky(S=1024, seed=11, moon=False):
    def f():
        rng = np.random.default_rng(seed)
        yy, xx = (np.mgrid[0:S, 0:S // 2] + 0.5) / S
        img = np.zeros((S, S // 2, 3), np.float32)
        img[:] = np.array([0.012, 0.02, 0.07])
        img += (1 - yy[..., None]) * np.array([0.03, 0.05, 0.14])
        st = rng.random((S, S // 2))
        img[st > 0.9965] = (0.9, 0.9, 1.0)
        img[(st > 0.9935) & (st <= 0.9965)] = (0.45, 0.48, 0.6)
        img = img + 0.05 * blur(img, 2, 1)
        neb = vnoise(S, S // 2, rng, 5, 3)
        img += np.clip(neb - 0.55, 0, 1)[..., None] * np.array([0.10, 0.05, 0.18])
        return img
    return f


def g_moon(S=512, seed=12):
    def f():
        rng = np.random.default_rng(seed)
        yy, xx = (np.mgrid[0:S, 0:S] + 0.5) / S
        n = vnoise(S, S, rng, 6, 3)
        m = vnoise(S, S, rng, 3, 2)
        img = np.ones((S, S, 3), np.float32) * np.array([0.92, 0.91, 0.86])
        img *= (0.7 + 0.4 * n[..., None])
        img *= (1 - 0.35 * np.clip((m - 0.5) * 3, 0, 1))[..., None]
        for _ in range(40):
            cx, cy, r = rng.random(), rng.random(), rng.uniform(0.01, 0.05)
            d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
            img *= (1 - 0.25 * np.clip(1 - np.abs(d - r) / 0.006, 0, 1))[..., None]
        return img
    return f


def g_paintings(seed=21, n=8):
    """An atlas of n abstract paintings, 2 rows, own work: colour fields, rings, a horizon, a figure."""
    def f():
        rng = np.random.default_rng(seed)
        W, Hh = 1024, 512
        img = np.zeros((Hh, W, 3), np.float32)
        cw = W // (n // 2)
        pal = [(0.85, 0.30, 0.20), (0.15, 0.30, 0.55), (0.90, 0.75, 0.30), (0.20, 0.45, 0.30), (0.75, 0.40, 0.65), (0.10, 0.10, 0.12),
               (0.92, 0.88, 0.80), (0.30, 0.65, 0.70)]
        for k in range(n):
            r, c = k // (n // 2), k % (n // 2)
            y0, x0 = r * 256, c * cw
            yy, xx = (np.mgrid[0:256, 0:cw] + 0.5) / np.array([256, cw])[:, None, None]
            a, b2, c2 = [np.array(pal[(k * 3 + i) % len(pal)]) for i in range(3)]
            t = k % 4
            if t == 0:
                p = np.where((yy < 0.55)[..., None], a, b2) * 1.0
                p = np.where((np.abs(xx - 0.5) < 0.12)[..., None] & (yy > 0.3)[..., None] & (yy < 0.8)[..., None], c2, p)
            elif t == 1:
                d = np.sqrt((xx - 0.5) ** 2 + (yy - 0.5) ** 2)
                p = np.where((((d * 10) % 2) < 1)[..., None], a, b2)
            elif t == 2:
                p = a * (1 - yy[..., None]) + b2 * yy[..., None]
                p = np.where(((xx - 0.3) ** 2 + (yy - 0.35) ** 2 < 0.01)[..., None], c2, p)
            else:
                p = np.where(((xx * 3 + yy * 2) % 1 < 0.5)[..., None], a, c2)
            p = p * (0.85 + 0.25 * vnoise(256, cw, rng, 5, 4)[..., None])
            img[y0:y0 + 256, x0:x0 + cw] = p
        return img
    return f


def painting_uv(k, n=8):
    r, c = k // (n // 2), k % (n // 2)
    return (c / (n // 2), 1 - (r + 1) / 2, (c + 1) / (n // 2), 1 - r / 2)


class Atlas:
    """A 1024 x 1024 atlas of signs, faces and screens for one room, shelf-packed; uv(key) is its rectangle."""
    def __init__(s, entries, S=1024):
        s.S, s.rects, s.entries = S, {}, entries
        x = y = rowh = 0
        for key, w, h, fn in entries:
            if x + w > S:
                x, y, rowh = 0, y + rowh, 0
            s.rects[key] = (x, y, w, h)
            x += w
            rowh = max(rowh, h)
        assert y + rowh <= S, "atlas overflow"

    def pixels(s):
        img = np.zeros((s.S, s.S, 3), np.float32)
        for key, w, h, fn in s.entries:
            x, y, _, _ = s.rects[key]
            img[y:y + h, x:x + w] = fn(h, w)
        return img

    def uv(s, key):
        x, y, w, h = s.rects[key]
        S = s.S
        return (x / S, 1 - (y + h) / S, (x + w) / S, 1 - y / S)


def sign(lines, bg, fg, border=None, seed=1):
    def f(h, w):
        img = text_lines(lines if isinstance(lines, (list, tuple)) else [lines], h, w, bg, fg, rng=np.random.default_rng(seed))
        if border:
            b = max(2, h // 24)
            img[:b] = img[-b:] = img[:, :b] = img[:, -b:] = border
        return img
    return f


def clock_face(hour, minute=None, bg=(0.90, 0.87, 0.78), fg=(0.08, 0.07, 0.06), rim=(0.25, 0.16, 0.08), roman=True, hands=True):
    def f(h, w):
        yy, xx = (np.mgrid[0:h, 0:w] + 0.5 - np.array([h / 2, w / 2])[:, None, None]) / (np.array([h / 2, w / 2])[:, None, None])
        rr = np.sqrt(xx ** 2 + yy ** 2)
        img = np.zeros((h, w, 3), np.float32)
        img[:] = rim
        img[rr < 0.95] = bg
        ang = np.arctan2(xx, -yy)
        ticks = (rr > 0.78) & (rr < 0.9) & (np.abs(((ang / (2 * math.pi) * 12) % 1) - 0.5) > 0.46)
        img[ticks] = fg
        fine = (rr > 0.85) & (rr < 0.9) & (np.abs(((ang / (2 * math.pi) * 60) % 1) - 0.5) > 0.42)
        img[fine] = fg
        if hands:
            mm = (hour % 1) * 60 if minute is None else minute
            for a, ln, wd in ((((hour % 12) + mm / 60) / 12 * 2 * math.pi, 0.5, 0.05), (mm / 60 * 2 * math.pi, 0.75, 0.035)):
                ux, uy = math.sin(a), -math.cos(a)
                t = xx * ux + yy * uy
                dist = np.abs(xx * uy - yy * ux)
                img[(t > -0.08) & (t < ln) & (dist < wd)] = fg
        img[rr < 0.05] = rim
        return img
    return f


# ================================================================ room shells
def shell(fmat, wmat, cmat, skirt="Trim_Paint", casing="Trim_Paint", skip_casings=(), cornice_mat=None, dado=None):
    shell_art(fmat, wmat, cmat)
    if skirt:
        skirting(skirt)
    if casing:
        casings(casing, skip=skip_casings)
    if cornice_mat:
        cornice(cornice_mat)
    if dado:
        dm, dy, rm = dado
        wall_band(dm, 0.0, dy, name="decor_Wall_Dado")
        if rm:
            rail(rm, dy - 0.03, 0.05, 0.03, name="decor_Trim_Dado_Rail")


def ceiling_troffers(xs, zs, along="x", lit=None, w=0.6, l=1.2, watts=40.0, color=TUBE, sets=None, off_mat="Lamp_Off", tag="Troffer"):
    """A grid of troffers; lit(x, z) says which are on (the others are dark diffusers)."""
    bl, bo, bf = bmesh.new(), bmesh.new(), bmesh.new()
    for x in xs:
        for z in zs:
            on = lit(x, z) if lit else True
            troffer(bl if on else bo, bf, x, z, w, l, along)
            if on:
                light("AREA", (x, K.H - 0.05, z), watts, color, sets=sets, aim=(0, -1, 0), size=(l, w) if along == "x" else (w, l))
    for bm, m, nm in ((bl, "Lamp_Emit", f"decor_{tag}_Lit"), (bo, off_mat, f"decor_{tag}_Off"), (bf, "Trim_White", f"decor_{tag}_Frames")):
        if bm.faces:
            finish(nm, bm, m)
        else:
            bm.free()


# ================================================================ 16. rdwe_void_room
def dress_void_room():
    """Pitch black: charcoal felt walls, a black lacquer floor, one plain chair facing the lit door. The door's outline is the only light in the
    dark set; the lift set is the black lifting to charcoal (the teal room's door does it too), dim enough to stay a void."""
    shell("Void_Floor", "Void_Felt", "Void_Felt", skirt=None, casing=None)
    b = K.BOX["Lone_Chair"]
    chair("Lone_Chair", b, "Chair_Wood", "Chair_Wood", back="S", seat_h=0.46)
    table("Side_Table", K.BOX["Side_Table"], "Chair_Wood", "Chair_Wood", t=0.03, r=0.018, inset=0.04, apron=False)
    cs = K.BOX["Coat_Stand"]
    cx, cz = (cs["min"][0] + cs["max"][0]) / 2, (cs["min"][2] + cs["max"][2]) / 2

    def stand(bm):
        cyl(bm, (cx, 0.0, cz), (cx, 1.8, cz), 0.022, 0.018, 10)
        for k in range(3):
            a = 2 * math.pi * k / 3
            cyl(bm, (cx, 0.02, cz), (cx + 0.18 * math.cos(a), 0.0, cz + 0.18 * math.sin(a)), 0.015, 0.015, 6)
        for k in range(4):
            a = 2 * math.pi * k / 4 + 0.4
            cyl(bm, (cx, 1.62, cz), (cx + 0.16 * math.cos(a), 1.72, cz + 0.16 * math.sin(a)), 0.01, 0.012, 6)
    part("Coat_Stand", "Chair_Wood", stand)
    part("decor_Coat", "Coat_Wool", lambda bm: (cyl(bm, (cx + 0.06, 0.95, cz), (cx + 0.1, 1.62, cz), 0.13, 0.09, 12),))
    rug("Rug", *[K.BOX["decor_Rug"][k][i] for k, i in (("min", 0), ("max", 0), ("min", 2), ("max", 2))], "Rug_Grey")
    # the teal room's watch on the side table (its second hand runs backward: the page's)
    st = K.BOX["Side_Table"]
    wx, wz, wy = (st["min"][0] + st["max"][0]) / 2, (st["min"][2] + st["max"][2]) / 2, st["max"][1]
    part("decor_Watch_Case", "Chrome", lambda bm: cyl(bm, (wx, wy, wz), (wx, wy + 0.012, wz), 0.02, 0.02, 16))
    part("decor_Watch_Strap", "Rubber", lambda bm: box(bm, wx - 0.012, wx + 0.012, wy, wy + 0.006, wz - 0.11, wz + 0.11))
    part("decor_Glass_Water", "Glass_Door", lambda bm: cyl(bm, (wx + 0.11, wy, wz - 0.08), (wx + 0.12, wy + 0.12, wz - 0.08), 0.03, 0.034, 12))
    # the lit door's outline: light leaking round the leaf, on the wall round its hole
    h = next(h for h in K.HOLES if h["name"] == "DoorLeaf_lit")
    a, hw, ht = h["a"], h["w"] / 2, h["h"]
    part("decor_Door_Glow", "Edge_Glow", lambda bm: (wall_box(bm, "N", a - hw - 0.012, a - hw, 0.0, ht, 0.0, 0.004),
                                                      wall_box(bm, "N", a + hw, a + hw + 0.012, 0.0, ht, 0.0, 0.004),
                                                      wall_box(bm, "N", a - hw - 0.012, a + hw + 0.012, ht, ht + 0.012, 0.0, 0.004),
                                                      wall_box(bm, "N", a - hw, a + hw, 0.0, 0.006, 0.0, 0.03)))
    # dark: only the edge light, from behind the door (area lights in the gaps), and a faint fall on the floor in front of it
    for x, y, z, sz in ((a - hw + 0.01, ht / 2, K.Z0 + 0.02, (0.02, ht)), (a + hw - 0.01, ht / 2, K.Z0 + 0.02, (0.02, ht)), (a, ht, K.Z0 + 0.02, (2 * hw, 0.02)),
                        (a, 0.02, K.Z0 + 0.05, (2 * hw, 0.02))):
        light("AREA", (x, y, z), 6.0, (1.0, 0.97, 0.9), aim=(0, 0, 1), size=sz, sets=["dark", "lift"])
    light("POINT", (a, 0.15, K.Z0 + 0.4), 1.2, (1.0, 0.96, 0.9), 0.3, sets=["dark", "lift"])
    # lift: the black lifts to charcoal, a soft cool fill from nowhere
    light("AREA", (0.0, K.H - 0.05, 0.0), 260.0, (0.80, 0.86, 1.0), aim=(0, -1, 0), size=(8.0, 8.0), sets=["lift"])
    K.EMIT_SETS["Edge_Glow"] = {"dark": 6.0, "lift": 4.0, "export": 6.0}


VOID = dict(
    sets=["dark", "lift"],
    pages=(1024, 1024),
    grade={"target": 0.9, "shoulder": 1.15, "mode": "shared", "ref_set": "lift"},
    mats={"Void_Floor": dict(color=(0.03, 0.03, 0.035), rough=0.25, group="struct"),
          "Void_Felt": dict(diff="rough_linen_diff_512.jpg", tint=(0.2, 0.2, 0.22), rough=1.0, tile=0.8, group="struct"),
          "Chair_Wood": dict(diff="dark_wood_diff_1k.jpg", tint=(0.75, 0.7, 0.65), rough=0.5, tile=0.6),
          "Coat_Wool": dict(diff="rough_linen_diff_512.jpg", tint=(0.20, 0.17, 0.15), rough=1.0, tile=0.4),
          "Rug_Grey": dict(diff="rough_linen_diff_512.jpg", tint=(0.30, 0.29, 0.28), rough=1.0, tile=0.5),
          "Edge_Glow": dict(color=(1.0, 0.98, 0.92), emit=((1.0, 0.97, 0.9), 6.0), group=None)},
    dress=dress_void_room,
    shots={"1_arrival": ((0.0, 1.55, 3.6), (-2.2, 1.2, -5.0), 70.0),
           "2_wide": ((4.3, 2.2, 4.3), (-2.5, 0.8, -3.5), 75.0),
           "3_detail": ((0.9, 1.3, 2.9), (2.2, 0.55, 0.6), 55.0)},
    set_exposure={"dark": 1.5},
    shot_sets={"2_wide": "lift", "3_detail": "lift"},
    set_shots=("1_arrival", "2_wide", "3_detail"),
    plan_set="lift",
)


# ================================================================ 17. rdwe_lights_out
def dress_lights_out():
    """A dark sitting room in violet damask over a navy star carpet. Three switches on brass posts, each with its cord across the floor to its
    lamp: switch 1 the standard lamp by the steel door (the void), switch 2 the tube batten over the green mirror door (the way to the three
    doors), switch 3 a red bulb on a cord and a door of light on the bare north wall that leads nowhere. Each is its own bake."""
    shell("Carpet_Stars", "Paper_Violet", "Ceiling_Plaster", skirt="Trim_Dark", casing="Trim_Dark", dado=("Panel_Dark", 0.9, "Trim_Dark"))
    cornice("Trim_Dark")
    for k in (1, 2, 3):
        b = K.BOX[f"Switch_Post_{k}"]
        cx, cz = (b["min"][0] + b["max"][0]) / 2, (b["min"][2] + b["max"][2]) / 2
        part(f"Switch_Post_{k}", "Brass", lambda bm, cx=cx, cz=cz: (cyl(bm, (cx, 0.0, cz), (cx, 0.04, cz), 0.15, 0.15, 20),
                                                                   cyl(bm, (cx, 0.04, cz), (cx, 1.08, cz), 0.035, 0.03, 12),
                                                                   box(bm, cx - 0.08, cx + 0.08, 1.08, 1.2, cz - 0.08, cz + 0.08)))
        part(f"decor_Switch_Plate_{k}", "Bakelite", lambda bm, cx=cx, cz=cz, k=k: (
            box(bm, cx - 0.06, cx + 0.06, 1.2, 1.21, cz - 0.06, cz + 0.06),
            box(bm, cx - 0.012, cx + 0.012, 1.21, 1.27, cz - 0.03, cz + 0.03) if k == 1 else
            cyl(bm, (cx, 1.21, cz), (cx, 1.24, cz), 0.025, 0.025, 12) if k == 3 else
            (cyl(bm, (cx, 1.21, cz), (cx, 1.3, cz - 0.0), 0.004, 0.004, 6), sphere(bm, (cx, 1.3, cz), 0.015, 8))))
    # the cords, along the floor in two straight runs each
    runs = {1: [(-3.0, 2.0), (-3.0, -5.35), (-5.35, -5.35)], 2: [(0.0, -2.0), (3.0, -2.0), (3.0, 4.7)], 3: [(3.0, 2.0), (3.0, 0.4), (0.0, 0.4), (0.0, -5.5)]}

    def cords(bm):
        for pts in runs.values():
            for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
                cyl(bm, (x0, 0.008, z0), (x1, 0.008, z1), 0.008, 0.008, 6)
        cyl(bm, (3.0, 0.008, 4.7), (3.0, 3.1, 4.7), 0.006, 0.006, 6)                       # up the wall to the batten
        cyl(bm, (0.0, 0.008, -5.5), (0.0, 2.2, -5.5), 0.006, 0.006, 6)                     # up to the red bulb's ceiling rose
    part("decor_Cords", "Rubber", cords)
    # switch 1: the standard lamp
    fl = K.BOX["Floor_Lamp"]
    lx, lz = (fl["min"][0] + fl["max"][0]) / 2, (fl["min"][2] + fl["max"][2]) / 2
    part("Floor_Lamp", "Brass", lambda bm: (cyl(bm, (lx, 0.0, lz), (lx, 0.03, lz), 0.2, 0.2, 18), cyl(bm, (lx, 0.03, lz), (lx, 1.4, lz), 0.016, 0.016, 8)))
    part("Floor_Lamp_Shade", "Shade_Silk", lambda bm: cyl(bm, (lx, 1.38, lz), (lx, 1.72, lz), 0.25, 0.16, 20, cap=False))
    part("decor_Floor_Lamp_Bulb", "Lamp_S1", lambda bm: sphere(bm, (lx, 1.5, lz), 0.05, 10))
    light("POINT", (lx, 1.52, lz), 70.0, WARM, 0.12, sets=["s1"])
    # switch 2: the tube batten over the south door
    tb = K.BOX["decor_Tube_Batten"]
    part("decor_Tube_Body", "Trim_White", lambda bm: box(bm, tb["min"][0], tb["max"][0], tb["max"][1] - 0.05, tb["max"][1], tb["min"][2], tb["max"][2]))
    part("decor_Tube", "Lamp_S2", lambda bm: cyl(bm, (tb["min"][0] + 0.05, tb["max"][1] - 0.08, (tb["min"][2] + tb["max"][2]) / 2),
                                                 (tb["max"][0] - 0.05, tb["max"][1] - 0.08, (tb["min"][2] + tb["max"][2]) / 2), 0.016, 0.016, 10))
    light("AREA", ((tb["min"][0] + tb["max"][0]) / 2, tb["max"][1] - 0.1, (tb["min"][2] + tb["max"][2]) / 2), 55.0, TUBE, aim=(0, -1, 0),
          size=(2.0, 0.1), sets=["s2"])
    # switch 3: the red bulb on its cord, and the door of light on the bare north wall
    part("decor_Red_Bulb", "Lamp_S3", lambda bm: sphere(bm, (0.0, 2.12, -5.5), 0.06, 12))
    part("decor_Red_Rose", "Bakelite", lambda bm: cyl(bm, (0.0, 3.15, -5.5), (0.0, 3.2, -5.5), 0.06, 0.06, 12))
    part("decor_Red_Cord", "Rubber", lambda bm: cyl(bm, (0.0, 2.18, -5.5), (0.0, 3.15, -5.5), 0.005, 0.005, 6))
    light("POINT", (0.0, 2.1, -5.4), 24.0, (1.0, 0.12, 0.06), 0.05, sets=["s3"])
    ld = K.BOX["decor_Light_Door"]
    light("AREA", (0.0, 1.1, K.Z0 + 0.03), 90.0, (1.0, 0.92, 0.8), aim=(0, 0, -1), size=(1.1, 2.2), sets=["s3"], name="Light_Door")
    # the armchair in the corner, its table and a glass
    armchair("Armchair", K.BOX["Armchair"], "Velvet_Plum", "Wood_Dark", back="N")
    table("Side_Table", K.BOX["Side_Table"], "Wood_Dark", "Wood_Dark", t=0.03, inset=0.04, apron=False)
    stb = K.BOX["Side_Table"]
    part("decor_Glass", "Glass_Door", lambda bm: cyl(bm, (4.15, stb["max"][1], -5.45), (4.15, stb["max"][1] + 0.1, -5.45), 0.03, 0.035, 10))
    rug("Rug", -4.6, 4.6, -3.6, 4.0, "Rug_Plum")
    # a faint glow under the steel door, in every set (the void is not quite dark)
    K.EMIT_SETS.update({"Lamp_S1": {"s1": 6.0, "s2": 0.0, "s3": 0.0, "export": 6.0}, "Lamp_S2": {"s1": 0.0, "s2": 6.0, "s3": 0.0, "export": 6.0},
                        "Lamp_S3": {"s1": 0.0, "s2": 0.0, "s3": 6.0, "export": 6.0}})
    light("AREA", (0.0, K.H - 0.05, 0.0), 6.0, (0.6, 0.6, 1.0), aim=(0, -1, 0), size=(6, 6), name="Night_Fill")


LIGHTS_OUT = dict(
    sets=["s1", "s2", "s3"],
    pages=(2048,),
    grade={"target": 0.9, "shoulder": 1.15, "mode": "each", "set_gain": {"s3": 0.8}},
    mats={"Carpet_Stars": dict(gen="carpet", rough=1.0, tile=1.6, group="struct"),
          "Paper_Violet": dict(gen="paper", rough=0.9, tile=0.9, group="struct"),
          "Panel_Dark": dict(diff="dark_wood_diff_1k.jpg", tint=(0.6, 0.5, 0.55), rough=0.5, tile=1.2, group="struct"),
          "Ceiling_Plaster": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.78, 0.74, 0.86), rough=0.95, tile=2.5, group="struct"),
          "Trim_Dark": dict(diff="dark_wood_diff_1k.jpg", tint=(0.55, 0.45, 0.45), rough=0.45, tile=0.8, group="struct"),
          "Trim_White": dict(color=(0.85, 0.85, 0.83), rough=0.5),
          "Bakelite": dict(color=(0.06, 0.04, 0.03), rough=0.3),
          "Shade_Silk": dict(color=(0.92, 0.82, 0.62), rough=0.8, two_sided=True),
          "Velvet_Plum": dict(diff="rough_linen_diff_512.jpg", tint=(0.42, 0.14, 0.32), rough=1.0, tile=0.5),
          "Rug_Plum": dict(diff="rough_linen_diff_512.jpg", tint=(0.30, 0.12, 0.22), rough=1.0, tile=0.6),
          "Lamp_S1": dict(color=(1.0, 0.92, 0.78), emit=((1.0, 0.80, 0.55), 6.0), group=None),
          "Lamp_S2": dict(color=(0.95, 0.97, 1.0), emit=((0.92, 0.96, 1.0), 6.0), group=None),
          "Lamp_S3": dict(color=(1.0, 0.3, 0.2), emit=((1.0, 0.12, 0.06), 6.0), group=None)},
    gen={"carpet": g_carpet((0.05, 0.07, 0.24), (0.12, 0.16, 0.42), pattern=stars_pattern((0.75, 0.66, 0.30))),
         "paper": g_damask((0.36, 0.18, 0.55), (0.48, 0.28, 0.66))},
    dress=dress_lights_out,
    shots={"1_arrival": ((-4.3, 1.55, -3.0), (3.0, 1.0, 2.5), 72.0),
           "2_wide": ((5.4, 2.4, 5.4), (-3.0, 0.8, -3.0), 78.0),
           "3_detail": ((1.2, 1.5, 0.6), (0.0, 1.0, -5.9), 60.0)},
    set_shots=("1_arrival", "2_wide", "3_detail"),
)


def moving_part(name, mname, build, pivot, **kw):
    """An object the page moves or turns: built in place, its origin moved to `pivot` (a game point)."""
    ob = part(name, mname, build, **kw)
    if ob is None:
        return None
    ob.data.transform(Matrix.Translation(-B(pivot)))
    ob.location = B(pivot)
    K.MOVING.add(name)
    return ob


def wire_box(bm, x0, x1, y0, y1, z0, z1, r=0.008):
    """The twelve edges of a box, as thin rods."""
    xs, ys, zs = (x0, x1), (y0, y1), (z0, z1)
    for y in ys:
        for z in zs:
            cyl(bm, (x0, y, z), (x1, y, z), r, r, 4)
    for x in xs:
        for z in zs:
            cyl(bm, (x, y0, z), (x, y1, z), r, r, 4)
    for x in xs:
        for y in ys:
            cyl(bm, (x, y, z0), (x, y, z1), r, r, 4)


# ================================================================ 18. rdwe_green_grid
def dress_green_grid():
    """Behind the teal room's wallpaper: black voids between pine studs, and a glowing green wireframe drawing the rooms: lines on every wall,
    the floor and the ceiling, a sofa half built (leather to the middle, wireframe after), a door and a chair drawn in wire, the Ames room's
    checker floor half filled in. At the south end, the back of the teal room's paper. The grid is the light."""
    shell("Grid_Floor", "Grid_Wall", "Grid_Wall", skirt=None, casing=None)
    for k in range(1, 9):
        for sd in "WE":
            b = K.BOX[f"Stud_{sd}_{k}"]
            part(f"Stud_{sd}_{k}", "Stud_Pine", lambda bm, b=b: bx(bm, b))
    # noggins between the studs (overhead and at waist height: decor, inside the stud line)

    def noggins(bm):
        for sd, x0, x1 in (("W", -3.0, -2.72), ("E", 2.72, 3.0)):
            for k in range(7):
                za, zb = -13.0 + k * 3.6 + 0.15, -13.0 + (k + 1) * 3.6 - 0.15
                for y in (1.2, 2.6):
                    box(bm, x0 + 0.03, x1 - 0.03, y, y + 0.09, za, zb)
        for k in range(15):
            z = -14.0 + k * 2.0
            box(bm, -2.7, 2.7, 3.72, 3.86, z - 0.04, z + 0.04)
    part("decor_Noggins", "Stud_Pine", noggins)
    X0, X1, Z0, Z1, H = K.X0, K.X1, K.Z0, K.Z1, K.H

    def grid(bm):
        for side in "WE":
            strip_lines(bm, side, Z0, Z1, 0.0, H, 0.5, 0.012)
        for side in "NS":
            lo, hi = X0, X1
            a = lo
            while a <= hi + 1e-6:
                holes = KT.holes_on(side)
                spans = KT.free_spans(side, a - 0.006, a + 0.006, 0.0, H)
                for s0, s1 in spans:
                    wall_box(bm, side, s0, s1, 0.0, H, 0.0, 0.004) if False else None
                if not any(h0 - 0.01 < a < h1 + 0.01 for h0, h1, _, _ in holes):
                    wall_box(bm, side, a - 0.006, a + 0.006, 0.0, H, 0.0, 0.004)
                a += 0.5
            y = 0.0
            while y <= H + 1e-6:
                for s0, s1 in KT.free_spans(side, lo, hi, y - 0.006, y + 0.006):
                    wall_box(bm, side, s0, s1, y - 0.006, y + 0.006, 0.0, 0.004)
                y += 0.5
        x = X0
        while x <= X1 + 1e-6:
            box(bm, x - 0.006, x + 0.006, H - 0.004, H, Z0, Z1)
            box(bm, x - 0.008, x + 0.008, 0.0, 0.003, Z0, Z1)
            x += 1.0 if abs(x) > 1e-6 else 1.0
        z = Z0
        while z <= Z1 + 1e-6:
            box(bm, X0, X1, H - 0.004, H, z - 0.006, z + 0.006)
            box(bm, X0, X1, 0.0, 0.003, z - 0.008, z + 0.008)
            z += 1.0
    part("decor_Grid_Lines", "Grid_Emit", grid)
    # the half-built sofa: the teal room's orange leather, to the middle; then wire
    hs = K.BOX["Half_Sofa"]
    x0, x1, z0, z1 = hs["min"][0], hs["max"][0], hs["min"][2], hs["max"][2]
    part("Half_Sofa", "Leather_Orange", lambda bm: (box(bm, x0, x1, 0.1, 0.45, z0, z1), box(bm, x0, x1, 0.45, 0.78, z1 - 0.22, z1),
                                                     box(bm, x0, x0 + 0.24, 0.45, 0.68, z0, z1)))
    ws = K.BOX["decor_Wire_Sofa"]
    part("decor_Wire_Sofa", "Grid_Emit", lambda bm: (wire_box(bm, ws["min"][0], ws["max"][0], 0.1, 0.45, z0, z1),
                                                      wire_box(bm, ws["min"][0], ws["max"][0], 0.45, 0.78, z1 - 0.22, z1),
                                                      wire_box(bm, ws["max"][0] - 0.24, ws["max"][0], 0.45, 0.68, z0, z1)))
    wd = K.BOX["decor_Wire_Door"]
    part("decor_Wire_Door", "Grid_Emit", lambda bm: (wire_box(bm, wd["min"][0], wd["max"][0], 0.0, 2.2, wd["min"][2], wd["max"][2], 0.01),
                                                      wire_box(bm, wd["min"][0] + 0.12, wd["max"][0] - 0.12, 0.2, 1.0, wd["min"][2], wd["max"][2]),
                                                      wire_box(bm, wd["min"][0] + 0.12, wd["max"][0] - 0.12, 1.15, 2.05, wd["min"][2], wd["max"][2])))
    wc = K.BOX["decor_Wire_Chair"]
    a0, a1, c0, c1 = wc["min"][0], wc["max"][0], wc["min"][2], wc["max"][2]
    part("decor_Wire_Chair", "Grid_Emit", lambda bm: (wire_box(bm, a0, a1, 0.0, 0.45, c0, c1), wire_box(bm, a0, a1, 0.45, 0.9, c0, c0 + 0.05)))
    # the Ames room's checker, half filled in
    ck = K.BOX["decor_Wire_Checker"]
    rng = np.random.default_rng(5)

    def checker(bm, fill):
        n = 0
        xs = np.arange(ck["min"][0], ck["max"][0] - 1e-6, 0.4)
        for i, x in enumerate(xs):
            for j, z in enumerate(np.arange(ck["min"][2], ck["max"][2] - 1e-6, 0.4)):
                done = (z - ck["min"][2]) / (ck["max"][2] - ck["min"][2]) + rng.uniform(-0.2, 0.2) > 0.45
                if (i + j) % 2 == 0 and done == fill:
                    box(bm, x, x + 0.4, 0.004, 0.008, z, z + 0.4)
                    n += 1
    part("decor_Checker_Done", "Checker_Black", lambda bm: checker(bm, True))
    part("decor_Checker_White", "Checker_White", lambda bm: box(bm, ck["min"][0], ck["max"][0], 0.002, 0.0035, ck["min"][2], ck["min"][2] + 1.2))
    # timber: the sawhorse and the stack
    sh = K.BOX["Sawhorse"]

    def sawhorse(bm):
        sx0, sx1, sz0, sz1 = sh["min"][0], sh["max"][0], sh["min"][2], sh["max"][2]
        box(bm, sx0, sx1, 0.68, 0.75, (sz0 + sz1) / 2 - 0.05, (sz0 + sz1) / 2 + 0.05)
        for x in (sx0 + 0.08, sx1 - 0.08):
            for z in (sz0 + 0.03, sz1 - 0.03):
                cyl(bm, (x, 0.0, z), (x, 0.7, (sz0 + sz1) / 2), 0.025, 0.025, 4)
        box(bm, sx0 - 0.0, sx1, 0.75, 0.75, sz0, sz1) if False else None
    part("Sawhorse", "Stud_Pine", sawhorse)
    part("decor_Plank", "Plywood", lambda bm: box(bm, sh["min"][0] - 0.3, sh["max"][0] + 0.1, 0.75, 0.77, sh["min"][2] + 0.1, sh["max"][2] - 0.1))
    ts = K.BOX["Timber_Stack"]

    def stack(bm):
        for k in range(5):
            y = k * 0.1
            for j in range(4):
                xa = ts["min"][0] + j * 0.25 + (k % 2) * 0.02
                box(bm, xa, xa + 0.22, y, y + 0.09, ts["min"][2] + k * 0.03, ts["max"][2] - (4 - k) * 0.02)
    part("Timber_Stack", "Stud_Pine", stack)
    # cables on the floor, from the south end to a clamp lamp on a stud
    part("decor_Cables", "Rubber", lambda bm: [cyl(bm, (dx, 0.012, 14.4), (dx + 0.2, 0.012, -13.0), 0.012, 0.012, 6) for dx in (-2.5, -2.45, 2.3)])
    for k, (sd, z) in enumerate((("W", -9.4), ("E", 1.4), ("W", 8.6)), 1):
        x = -2.62 if sd == "W" else 2.62
        part(f"decor_Clamp_Lamp_{k}", "Iron", lambda bm, x=x, z=z: (box(bm, x - 0.05, x + 0.05, 2.2, 2.3, z - 0.05, z + 0.05),
                                                                    cyl(bm, (x, 2.28, z), (x + (0.3 if x < 0 else -0.3), 2.5, z), 0.012, 0.012, 6)))
        lx = x + (0.34 if x < 0 else -0.34)
        part(f"decor_Clamp_Shade_{k}", "Iron", lambda bm, lx=lx, z=z: cyl(bm, (lx, 2.38, z), (lx, 2.55, z), 0.12, 0.05, 14, cap=False))
        part(f"decor_Clamp_Bulb_{k}", "Lamp_Emit", lambda bm, lx=lx, z=z: sphere(bm, (lx, 2.42, z), 0.04, 8))
        light("POINT", (lx, 2.38, z), 28.0, WARM, 0.05)
    # the back of the teal room's paper, at the south end: brown paper, teal bleeding through, the corners peeling
    pb = K.BOX["decor_Paper_Back"]
    h = next(hh for hh in K.HOLES if hh["side"] == "S")
    for k, (a0, a1) in enumerate(((pb["min"][0], h["a"] - h["w"] / 2 - 0.08), (h["a"] + h["w"] / 2 + 0.08, pb["max"][0])), 1):
        picture(f"decor_Paper_Back_{k}", "Paper_Back", ((a0 + a1) / 2, 2.0, K.Z1 - 0.01), "-z", a1 - a0, 3.6)
    part("decor_Paper_Curl", "Paper_Back", lambda bm: [quad(bm, (x, 3.8, K.Z1 - 0.01), (x + 0.6, 3.8, K.Z1 - 0.01), (x + 0.5, 3.3, K.Z1 - 0.35),
                                                             (x + 0.05, 3.4, K.Z1 - 0.3)) for x in (-2.5, 1.7)], recalc=False)
    # the grid's own light along the ceiling (so the bake is steady), green
    for z in np.arange(-13.0, 14.0, 4.5):
        light("POINT", (0.0, K.H - 0.3, float(z)), 30.0, (0.25, 1.0, 0.4), 0.3)
    light("AREA", (0.0, 0.05, 0.0), 8.0, (0.25, 1.0, 0.4), aim=(0, 1, 0), size=(5.0, 28.0), name="Floor_Grid_Glow")


GREEN_GRID = dict(
    pages=(2048, 1024),
    grade={"target": 1.5, "shoulder": 1.15},
    mats={"Grid_Floor": dict(color=(0.035, 0.04, 0.035), rough=0.3, group="struct"),
          "Grid_Wall": dict(diff="concrete_floor_02_diff_1k.jpg", tint=(0.11, 0.12, 0.11), rough=0.9, tile=3.0, group="struct"),
          "Stud_Pine": dict(diff="plywood_diff_1k.jpg", tint=(1.0, 0.86, 0.62), rough=0.7, tile=1.0),
          "Leather_Orange": dict(color=(0.80, 0.30, 0.06), rough=0.45),
          "Checker_Black": dict(color=(0.05, 0.05, 0.05), rough=0.4),
          "Checker_White": dict(color=(0.80, 0.80, 0.78), rough=0.4),
          "Paper_Back": dict(gen="paperback", rough=1.0, two_sided=True)},
    gen={"paperback": lambda: (lambda rng: np.clip(np.ones((512, 256, 3), np.float32) * np.array([0.62, 0.52, 0.38])
                                                   * (0.85 + 0.25 * vnoise(512, 256, rng, 5, 4)[..., None])
                                                   + np.clip(vnoise(512, 256, rng, 4, 3) - 0.55, 0, 1)[..., None] * np.array([-0.5, 0.1, 0.05]), 0, 1))(
        np.random.default_rng(9))},
    dress=dress_green_grid,
    shots={"1_arrival": ((0.0, 1.55, 13.6), (0.0, 1.4, -14.0), 72.0),
           "2_wide": ((2.0, 2.6, -13.8), (-0.6, 0.9, 8.0), 70.0),
           "3_detail": ((0.4, 1.5, 9.3), (-1.6, 0.5, 6.8), 62.0)},
)


# ================================================================ 19. rdwe_ames_room
AMES_EYE = (0.0, KT.EYE, 4.2)          # the peephole (Spot_view_1), at eye height
AMES_ZV = -5.0                          # the square room it pretends to be: its back wall at z -5, as deep as the west corner


def ames_uv(bm, mname_tile=None):
    """UVs for the slanted back wall: each vertex shows what the square room's back wall (or its ceiling) shows along the ray from the peephole,
    so from Spot_view_1 the stepped wall reads as one flat wall with two square windows. The atlas: the back wall in its top half (14 m by
    4.5 m), the ceiling's plaster in the bottom half."""
    E = Vector(AMES_EYE)
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for lp in f.loops:
            p = lp.vert.co
            P = Vector((p.x, p.z, -p.y))
            t = (AMES_ZV - E.z) / (P.z - E.z) if abs(P.z - E.z) > 1e-6 else 1.0
            Hh = E + (P - E) * t
            if Hh.y <= K.H:
                lp[uvl].uv = ((Hh.x + 7.0) / 14.0, 0.5 + 0.5 * Hh.y / K.H)
            else:
                tc = (K.H - E.y) / (P.y - E.y)
                C = E + (P - E) * tc
                lp[uvl].uv = ((C.x + 7.0) / 14.0, 0.5 * (C.z - AMES_ZV) / (E.z - AMES_ZV + 1.0))


def grid_face(bm, p0, du, dv, nu, nv):
    """A quad from p0 spanned by du, dv (game vectors), cut into nu x nv quads (for the projected UVs)."""
    vs = [[bm.verts.new(B(tuple(Vector(p0) + Vector(du) * (i / nu) + Vector(dv) * (j / nv)))) for j in range(nv + 1)] for i in range(nu + 1)]
    for i in range(nu):
        for j in range(nv):
            bm.faces.new([vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1]])


def g_ames():
    S = 1024
    rng = np.random.default_rng(14)
    img = np.zeros((S, S, 3), np.float32)
    # top half: the square room's back wall, 14 m x 4.5 m (u = (x + 7) / 14, v = y / 4.5): magenta damask over a white dado, two square
    # windows of painted sky, a picture rail
    Hh, W = S // 2, S
    yy, xx = (np.mgrid[0:Hh, 0:W] + 0.5) / np.array([Hh, W])[:, None, None]
    y_m = (1 - yy) * 4.5
    x_m = xx * 14.0 - 7.0
    wall = g_damask((0.62, 0.05, 0.40), (0.78, 0.22, 0.55), S=256, seed=15)()
    tile = 0.9
    iy = ((y_m / tile) % 1 * 255).astype(int)
    ix = ((x_m / tile) % 1 * 255).astype(int)
    top = wall[iy, ix]
    dado = y_m < 1.0
    top[dado] = np.array([0.88, 0.86, 0.82])
    top[(np.abs(y_m - 1.0) < 0.04)] = np.array([0.95, 0.94, 0.9])
    top[(np.abs(y_m - 3.6) < 0.03)] = np.array([0.95, 0.94, 0.9])
    for cx in (-3.5, 3.5):
        inwin = (np.abs(x_m - cx) < 1.0) & (y_m > 1.5) & (y_m < 3.3)
        sky = np.array([0.55, 0.72, 0.95]) * (1 - 0.3 * (y_m - 1.5)[..., None] / 1.8) + np.array([0.2, 0.1, 0.0]) * ((y_m < 2.0)[..., None])
        top = np.where(inwin[..., None], sky, top)
        fr = ((np.abs(np.abs(x_m - cx) - 1.0) < 0.06) & (y_m > 1.44) & (y_m < 3.36)) | ((np.abs(y_m - 1.47) < 0.06) | (np.abs(y_m - 3.33) < 0.06)) & (np.abs(x_m - cx) < 1.06)
        fr |= (np.abs(x_m - cx) < 0.03) & (y_m > 1.5) & (y_m < 3.3) | (np.abs(y_m - 2.4) < 0.03) & (np.abs(x_m - cx) < 1.0)
        top[fr] = np.array([0.95, 0.94, 0.90])
    img[:Hh] = top * (0.94 + 0.08 * vnoise(Hh, W, rng, 4, 6)[..., None])
    # bottom half: the ceiling plaster
    img[Hh:] = np.array([0.86, 0.84, 0.80]) * (0.9 + 0.12 * vnoise(Hh, W, rng, 5, 4)[..., None])
    return img


def dress_ames_room():
    """A trapezoid room dressed as a square one: magenta damask over a white dado, a black and white checker floor, a plaster ceiling. Its back
    wall steps from 10 m deep in the west corner to 7 m in the east; the paper on it is projected from the peephole (Spot_view_1), so through the
    brass viewer it is one flat wall with two square windows. Two identical armchairs, one in each corner: from the viewer the east one is a
    giant's chair."""
    shell("Ames_Floor", "Ames_Paper", "Ames_Ceiling", skirt="Trim_White", casing="Trim_White")
    wall_band("Ames_Dado", 0.0, 1.0, name="decor_Wall_Dado", sides="SWE")
    rail("Trim_White", 0.97, 0.05, 0.025, sides="SWE", name="decor_Trim_Dado_Rail")
    rail("Trim_White", 3.57, 0.05, 0.02, sides="SWE", name="decor_Trim_Picture_Rail")
    prev = -5.0
    for i in range(7):
        n = f"Slant_{i + 1}"
        if n not in K.BOX:
            continue
        b = K.BOX[n]
        x0, x1, zi = b["min"][0], b["max"][0], b["max"][2]

        def build(bm, x0=x0, x1=x1, zi=zi, prev=prev):
            grid_face(bm, (x0, 0.0, zi), (x1 - x0, 0.0, 0.0), (0.0, K.H, 0.0), 10, 24)
            if x0 > -7.0 + 1e-6 and zi > prev + 1e-6:
                grid_face(bm, (x0, 0.0, prev), (0.0, 0.0, zi - prev), (0.0, K.H, 0.0), max(2, int((zi - prev) / 0.15)), 24)
            box(bm, x0, x1, 0.0, 0.002, -5.0, zi) if False else None
        ob = part(n, "Ames_Proj", build, keep_uv=True, recalc=False)
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        ames_uv(bm)
        bm.to_mesh(ob.data)
        bm.free()
        # its box must cover the collider for the layout check: a hidden back (never seen)
        part(n + "_Core", "Ames_Paper", lambda bm, b=b: cube(bm, (b["min"][0] + 0.02, 0.0, b["min"][2]), (b["max"][0] - 0.02, b["max"][1], b["max"][2] - 0.02)))
        prev = zi
    # the bit of the west corner's back wall (no slant box there): it is the square room's back wall, 0..2 m along
    part("decor_Back_West", "Ames_Proj", lambda bm: grid_face(bm, (-7.0, 0.0, -5.0 + 0.002), (2.0, 0.0, 0.0), (0.0, K.H, 0.0), 6, 24), keep_uv=True,
         recalc=False)
    ob = bpy.data.objects["decor_Back_West"]
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    ames_uv(bm)
    bm.to_mesh(ob.data)
    bm.free()
    # the viewer: a brass post, its eyepiece at 1.55 m, looking north
    vb = K.BOX["Viewer"]
    vx, vz = (vb["min"][0] + vb["max"][0]) / 2, (vb["min"][2] + vb["max"][2]) / 2
    part("Viewer", "Brass", lambda bm: (cyl(bm, (vx, 0.0, vz), (vx, 0.04, vz), 0.18, 0.18, 18), cyl(bm, (vx, 0.04, vz), (vx, 1.3, vz), 0.03, 0.03, 12)))
    part("decor_Viewer_Eyepiece", "Brass", lambda bm: (box(bm, vx - 0.09, vx + 0.09, 1.3, 1.62, vz - 0.12, vz + 0.12),
                                                       cyl(bm, (vx, 1.5, vz - 0.12), (vx, 1.5, vz - 0.22), 0.03, 0.035, 12),
                                                       cyl(bm, (vx, 1.5, vz + 0.12), (vx, 1.5, vz + 0.2), 0.035, 0.035, 12)))
    part("decor_Viewer_Lens", "Glass_Door", lambda bm: cyl(bm, (vx, 1.5, vz + 0.2), (vx, 1.5, vz + 0.205), 0.028, 0.028, 12))
    for n in ("Chair_Deep", "Chair_Shallow"):
        armchair(n, K.BOX[n], "Velvet_Green", "Wood_Dark", back="N")
    rug("Rug", -2.4, 2.4, -1.6, 2.2, "Rug_Red")
    for k, (x, z) in enumerate(((-3.8, -1.0), (0.0, 0.5), (3.6, -0.6)), 1):
        pendant(f"Pendant_{k}", x, z, 1.1, 0.2, "Shade_Glass", kind="globe", watts=70)
    frame_picture("Pic_S1", "S", 2.5, 2.2, 1.1, 0.8, "Paintings", uv=painting_uv(3))
    frame_picture("Pic_W1", "W", -2.5, 2.2, 0.9, 1.1, "Paintings", uv=painting_uv(1))
    frame_picture("Pic_E1", "E", 2.0, 2.2, 0.9, 1.1, "Paintings", uv=painting_uv(5))


AMES = dict(
    pages=(2048, 1024),
    grade={"target": 0.9, "shoulder": 1.15},
    mats={"Ames_Floor": dict(gen="checker", rough=0.35, tile=1.0, group="struct"),
          "Ames_Paper": dict(gen="ames", rough=0.9, tile=1.0, group="struct") if False else dict(gen="paper", rough=0.9, tile=0.9, group="struct"),
          "Ames_Proj": dict(gen="ames", rough=0.9, group="struct"),
          "Ames_Dado": dict(color=(0.88, 0.86, 0.82), rough=0.6, group="struct"),
          "Ames_Ceiling": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.88, 0.86, 0.82), rough=0.95, tile=2.5, group="struct"),
          "Trim_White": dict(color=(0.92, 0.91, 0.88), rough=0.45, group="struct"),
          "Velvet_Green": dict(diff="rough_linen_diff_512.jpg", tint=(0.10, 0.42, 0.24), rough=1.0, tile=0.5),
          "Rug_Red": dict(diff="rough_linen_diff_512.jpg", tint=(0.55, 0.10, 0.12), rough=1.0, tile=0.6),
          "Shade_Glass": dict(color=(0.95, 0.92, 0.85), rough=0.3, emit=((1.0, 0.9, 0.75), 2.0), group=None),
          "Paintings": dict(gen="paintings", rough=0.6),
          "Frame_Gilt": dict(color=(0.66, 0.50, 0.22), rough=0.35, metal=0.8)},
    gen={"checker": g_checker((0.88, 0.87, 0.84), (0.05, 0.05, 0.05), n=2, S=256), "ames": g_ames,
         "paper": g_damask((0.62, 0.05, 0.40), (0.78, 0.22, 0.55), S=256, seed=15, scale=1), "paintings": g_paintings(21)},
    dress=dress_ames_room,
    shots={"1_arrival": (AMES_EYE, (0.0, 1.55, -5.0), 62.0),
           "2_wide": ((-6.2, 2.4, 4.3), (3.0, 1.0, -3.0), 78.0),
           "3_detail": ((4.2, 1.4, 2.0), (6.5, 1.0, -1.6), 62.0)},
)


# ================================================================ 20. rdwe_shrink_hall
SHRINK = [(6.0, 12.0, 3.0, 3.6, 1.0), (0.0, 6.0, 2.4, 3.2, 0.8), (-6.0, 0.0, 1.8, 2.7, 0.6), (-12.0, -6.0, 1.0, 2.2, 0.37)]   # z0, z1, half width, ceiling, scale


def dress_shrink_hall():
    """A pink striped hall in four sections, each smaller than the last: the walls close in, the ceiling comes down, and everything scales with
    them (the stripes, the boards, the dado, the skirting, the pictures, the lamps, the console tables), so from the big end the 24 m look like 60."""
    shell_art("Floor_Boards", "Paper_Stripe", "Ceiling_Pink")
    rng = np.random.default_rng(20)
    for k, (z0, z1, hw, ch, sc) in enumerate(SHRINK, 1):
        # the floor of the section: boards at the section's scale, and the runner narrowing with it
        part(f"decor_Floor_{k}", "Floor_Boards", lambda bm, z0=z0, z1=z1, hw=hw: box(bm, -hw, hw, 0.0, 0.002, z0, z1), tile=1.4 * sc)
        part(f"decor_Runner_{k}", "Runner", lambda bm, z0=z0, z1=z1, hw=hw: box(bm, -0.62 * hw / 3, 0.62 * hw / 3, 0.002, 0.012, z0 + 0.2 * sc, z1 - 0.2 * sc),
             tile=0.8 * sc)
        for sd in "WE":
            x = -hw if sd == "W" else hw
            nn = f"Narrow_{sd}_{k - 1}" if k > 1 else None
            if nn:
                part(nn, "Paper_Stripe", lambda bm, b=K.BOX[nn]: bx(bm, b), tile=0.9 * sc)
            sg = 1 if sd == "W" else -1

            def trims(bm, x=x, sg=sg, z0=z0, z1=z1, sc=sc):
                box(bm, x, x + sg * 0.018 * sc, 0.0, 0.12 * sc, z0, z1)
                box(bm, x, x + sg * 0.025 * sc, 0.9 * sc, 0.95 * sc, z0, z1)
                box(bm, x, x + sg * 0.006, 0.0, 0.9 * sc, z0, z1)
            part(f"decor_Trim_{sd}_{k}", "Trim_White", trims)
            # pictures, scaled
            for j in range(2):
                z = z0 + (z1 - z0) * (0.3 + 0.4 * j)
                pw, ph = 0.8 * sc, 0.6 * sc
                c = (x + sg * 0.03, 1.55 * sc + 0.15, z)
                picture(f"decor_Pic_{sd}_{k}_{j}", "Paintings", c, "+x" if sd == "W" else "-x", pw, ph, painting_uv((k * 2 + j + (sd == "E")) % 8))
                part(f"decor_Pic_{sd}_{k}_{j}_Frame", "Frame_Gilt", lambda bm, x=x, sg=sg, z=z, pw=pw, ph=ph, sc=sc: (
                    box(bm, x, x + sg * 0.025, 1.55 * sc + 0.15 - ph / 2 - 0.04 * sc, 1.55 * sc + 0.15 + ph / 2 + 0.04 * sc, z - pw / 2 - 0.04 * sc, z - pw / 2),
                    box(bm, x, x + sg * 0.025, 1.55 * sc + 0.15 - ph / 2 - 0.04 * sc, 1.55 * sc + 0.15 + ph / 2 + 0.04 * sc, z + pw / 2, z + pw / 2 + 0.04 * sc),
                    box(bm, x, x + sg * 0.025, 1.55 * sc + 0.15 - ph / 2 - 0.04 * sc, 1.55 * sc + 0.15 - ph / 2, z - pw / 2, z + pw / 2),
                    box(bm, x, x + sg * 0.025, 1.55 * sc + 0.15 + ph / 2, 1.55 * sc + 0.15 + ph / 2 + 0.04 * sc, z - pw / 2, z + pw / 2)))
        # the section's lamps: smaller and closer together
        for j in range(2):
            z = z0 + (z1 - z0) * (0.25 + 0.5 * j)
            drop = 0.55 * sc
            yb = ch - drop
            part(f"decor_Lamp_{k}_{j}_Cord", "Iron", lambda bm, z=z, yb=yb, ch=ch: cyl(bm, (0.0, yb, z), (0.0, ch, z), 0.006, 0.006, 6))
            part(f"decor_Lamp_{k}_{j}_Shade", "Shade_Pink", lambda bm, z=z, yb=yb, sc=sc: cyl(bm, (0.0, yb - 0.14 * sc, z), (0.0, yb + 0.02, z), 0.26 * sc, 0.08 * sc, 18, cap=False))
            part(f"decor_Lamp_{k}_{j}_Bulb", "Lamp_Emit", lambda bm, z=z, yb=yb, sc=sc: sphere(bm, (0.0, yb - 0.06 * sc, z), 0.05 * sc, 10))
            light("POINT", (0.0, yb - 0.12 * sc, z), 55.0 * sc, WARM, 0.05)
        # the console table, scaled, with a lamp on it
        cb = K.BOX[f"Console_{k}"]
        table(f"Console_{k}", cb, "Wood_Dark", "Wood_Dark", t=0.035 * sc, r=0.02 * sc, inset=0.04 * sc)
        cx, cz, ct = (cb["min"][0] + cb["max"][0]) / 2, (cb["min"][2] + cb["max"][2]) / 2, cb["max"][1]
        part(f"decor_Console_Vase_{k}", "Vase_Blue", lambda bm, cx=cx, cz=cz, ct=ct, sc=sc: cyl(bm, (cx, ct, cz), (cx, ct + 0.3 * sc, cz), 0.06 * sc, 0.09 * sc, 12))
    # the ceiling steps (the greybox's decor soffits)
    for n in ("decor_Ceiling_Mid_2", "decor_Ceiling_Mid_3", "decor_Ceiling_Low"):
        gb_box(n, "Ceiling_Pink")
    KT.casings("Trim_White")


SHRINK_HALL = dict(
    pages=(2048, 1024),
    grade={"target": 0.9, "shoulder": 1.15},
    mats={"Floor_Boards": dict(diff="old_wood_floor_diff_1k.jpg", tint=(0.95, 0.82, 0.70), rough=0.5, tile=1.4, group="struct"),
          "Paper_Stripe": dict(gen="stripes", rough=0.9, tile=0.9, group="struct"),
          "Ceiling_Pink": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.95, 0.86, 0.86), rough=0.95, tile=2.0, group="struct"),
          "Trim_White": dict(color=(0.92, 0.91, 0.88), rough=0.45, group="struct"),
          "Runner": dict(gen="runner", rough=1.0, tile=0.8),
          "Shade_Pink": dict(color=(0.95, 0.55, 0.68), rough=0.6, two_sided=True),
          "Vase_Blue": dict(color=(0.15, 0.30, 0.65), rough=0.25),
          "Paintings": dict(gen="paintings", rough=0.6),
          "Frame_Gilt": dict(color=(0.66, 0.50, 0.22), rough=0.35, metal=0.8)},
    gen={"stripes": g_stripes((0.92, 0.50, 0.62), (0.98, 0.78, 0.82), n=6), "paintings": g_paintings(23),
         "runner": g_carpet((0.45, 0.06, 0.14), (0.75, 0.55, 0.25), seed=24, pattern=None)},
    dress=dress_shrink_hall,
    shots={"1_arrival": ((0.0, 1.55, 10.4), (0.0, 1.2, -12.0), 62.0),
           "2_wide": ((-2.6, 2.6, 11.6), (0.6, 0.8, -8.0), 72.0),
           "3_detail": ((0.0, 1.0, -8.0), (0.0, 0.8, -12.0), 66.0)},
)


# ================================================================ 21. rdwe_moon_window
def dress_moon_window():
    """A night study under a navy, star-painted ceiling: lilac walls, a big mullioned window on the north wall full of night sky and the moon,
    a window seat, a brass telescope on its tripod, a desk with a lamp, star charts, a bookcase, a globe, a round rug, and the white pedestal
    where the moon goes. The moon is its own object (the page picks it up and rescales it); it is not baked."""
    shell("Carpet_Stars", "Plaster_Lilac", "Ceiling_Navy", skirt="Trim_White", casing="Trim_White")
    rail("Trim_White", 0.9, 0.05, 0.025, name="decor_Trim_Dado_Rail")
    cornice("Trim_White")
    # the window: the night sky on the wall (emissive), a deep frame, mullions, the sill
    picture("decor_Window_Sky", "Window_Night", (0.0, 2.2, K.Z0 + 0.004), "+z", 6.0, 2.0)

    def frame(bm):
        for x in (-3.08, -1.0, 1.0, 3.08):
            hw = 0.08 if abs(x) > 3 else 0.04
            box(bm, x - hw, x + hw, 1.2, 3.2, K.Z0, K.Z0 + 0.12)
        for y in (1.2, 2.2, 3.2):
            hh = 0.08 if y != 2.2 else 0.035
            box(bm, -3.16, 3.16, y - hh, y + hh, K.Z0, K.Z0 + 0.12)
        box(bm, -3.3, 3.3, 1.1, 1.16, K.Z0, K.Z0 + 0.3)
    part("decor_Window_Frame", "Trim_White", frame)
    part("decor_Window_Glass", "Glass_Clear", lambda bm: box(bm, -3.0, 3.0, 1.2, 3.2, K.Z0 + 0.06, K.Z0 + 0.065))
    for k, (a0, a1) in enumerate(((-4.0, -3.1), (3.1, 4.0)), 1):
        part(f"decor_Curtain_{k}", "Curtain_Navy", lambda bm, a0=a0, a1=a1: [box(bm, a0 + (a1 - a0) * i / 6, a0 + (a1 - a0) * (i + 1) / 6, 0.3, 3.4,
                                                                               K.Z0 + 0.15 + 0.05 * (i % 2), K.Z0 + 0.2 + 0.05 * (i % 2)) for i in range(6)])
    part("decor_Curtain_Rail", "Brass", lambda bm: cyl(bm, (-4.2, 3.42, K.Z0 + 0.18), (4.2, 3.42, K.Z0 + 0.18), 0.02, 0.02, 10))
    ws = K.BOX["Window_Seat"]
    part("Window_Seat", "Trim_White", lambda bm: bx(bm, ws))
    part("Window_Seat_Cushion", "Velvet_Navy", lambda bm: box(bm, ws["min"][0] + 0.05, ws["max"][0] - 0.05, ws["max"][1], ws["max"][1] + 0.08, ws["min"][2] + 0.1, ws["max"][2]))
    P = Painter()
    for k, x in enumerate((-2.4, -1.6, 1.8)):
        P.add(["fabric_teal", "lemon", "magenta"][k], box, x, x + 0.5, ws["max"][1] + 0.08, ws["max"][1] + 0.45, ws["min"][2] + 0.1, ws["min"][2] + 0.25)
    P.done("decor_Seat_Cushions")
    # the moon (the page's): a sphere in the window, its origin at its centre
    mb = K.BOX["decor_Moon"]
    mc = ((mb["min"][0] + mb["max"][0]) / 2, (mb["min"][1] + mb["max"][1]) / 2, (mb["min"][2] + mb["max"][2]) / 2)
    moving_part("Moon", "Moon_Glow", lambda bm: sphere(bm, mc, 0.42, 32), mc, smooth=True)
    K.spec["moving"] = {"Moon": "the page picks it up: its scale is how far away you hold it; set on the pedestal it fills the room"}
    light("AREA", (0.0, 2.2, K.Z0 + 0.3), 110.0, (0.62, 0.72, 1.0), aim=(0, -0.2, 1), size=(5.6, 1.9), name="Moonlight")
    light("POINT", (mc[0], mc[1], mc[2] + 0.6), 12.0, (0.8, 0.85, 1.0), 0.4, name="Moon_Glow_Light")
    # the telescope on its tripod, pointed at the window
    tb = K.BOX["Telescope"]
    tx, tz = (tb["min"][0] + tb["max"][0]) / 2, (tb["min"][2] + tb["max"][2]) / 2

    def tripod(bm):
        for k in range(3):
            a = 2 * math.pi * k / 3 + 0.3
            cyl(bm, (tx + 0.3 * math.cos(a), 0.0, tz + 0.3 * math.sin(a)), (tx, 1.2, tz), 0.016, 0.012, 6)
        cyl(bm, (tx, 1.15, tz), (tx, 1.28, tz), 0.04, 0.04, 10)
    part("Telescope", "Wood_Dark", tripod)
    part("Telescope_Tube", "Brass", lambda bm: (cyl(bm, (tx + 0.08, 1.22, tz + 0.26), (tx - 0.1, 1.42, tz - 0.27), 0.06, 0.07, 16),
                                                cyl(bm, (tx + 0.09, 1.2, tz + 0.3), (tx + 0.07, 1.24, tz + 0.22), 0.025, 0.025, 10)))
    # the desk, its lamp, its chair; the star charts on the west wall
    table("Desk", K.BOX["Desk"], "Wood_Dark", "Wood_Dark", t=0.04, inset=0.05)
    db = K.BOX["Desk"]
    dy = db["max"][1]
    part("decor_Desk_Lamp", "Brass", lambda bm: (cyl(bm, (-4.75, dy, -2.2), (-4.75, dy + 0.02, -2.2), 0.08, 0.08, 14),
                                                 cyl(bm, (-4.75, dy + 0.02, -2.2), (-4.6, dy + 0.4, -2.1), 0.01, 0.01, 6)))
    part("decor_Desk_Lamp_Shade", "Shade_Green", lambda bm: cyl(bm, (-4.62, dy + 0.34, -2.08), (-4.56, dy + 0.44, -2.05), 0.1, 0.04, 14, cap=False))
    part("decor_Desk_Lamp_Bulb", "Lamp_Emit", lambda bm: sphere(bm, (-4.6, dy + 0.36, -2.08), 0.03, 8))
    light("POINT", (-4.6, dy + 0.3, -2.06), 30.0, WARM, 0.04, name="Desk_Lamp")
    P = Painter()
    P.add("paper", box, -4.9, -4.5, dy, dy + 0.004, -1.6, -1.0)
    P.add("book_blue", box, -4.95, -4.7, dy, dy + 0.06, -0.95, -0.7)
    P.add("book_red", box, -4.95, -4.72, dy + 0.06, dy + 0.1, -0.92, -0.72)
    P.done("decor_Desk_Things")
    chair("Desk_Chair", K.BOX["Desk_Chair"], "Wood_Dark", "Wood_Dark", back="E")
    for k, z in enumerate((-4.2, 3.8), 1):
        frame_picture(f"Chart_{k}", "W", z, 1.9, 1.0, 0.8, "Star_Chart", frame_mat="Trim_White")
    frame_picture("Chart_3", "E", 3.6, 1.9, 1.2, 0.9, "Star_Chart", frame_mat="Trim_White", flip=True)
    # the bookcase and its books
    bb = K.BOX["Bookcase"]
    part("Bookcase", "Wood_Dark", lambda bm: (box(bm, bb["min"][0], bb["max"][0], 0.0, 0.06, bb["min"][2], bb["max"][2]),
                                               box(bm, bb["min"][0], bb["max"][0], bb["max"][1] - 0.04, bb["max"][1], bb["min"][2], bb["max"][2]),
                                               box(bm, bb["min"][0], bb["min"][0] + 0.03, 0.0, bb["max"][1], bb["min"][2], bb["max"][2]),
                                               box(bm, bb["max"][0] - 0.03, bb["max"][0], 0.0, bb["max"][1], bb["min"][2], bb["max"][2]),
                                               box(bm, bb["min"][0], bb["max"][0], 0.0, bb["max"][1], bb["max"][2] - 0.02, bb["max"][2]),
                                               [box(bm, bb["min"][0], bb["max"][0], y, y + 0.025, bb["min"][2], bb["max"][2]) for y in (0.5, 0.95, 1.4, 1.8)]))
    P = Painter()
    rng = np.random.default_rng(31)
    for y in (0.06, 0.525, 0.975, 1.425, 1.825):
        books_row(P, bb["min"][0] + 0.04, bb["max"][0] - 0.04, y, bb["min"][2] + 0.02, bb["max"][2] - 0.03, rng, hmax=0.34)
    P.done("decor_Books")
    # the globe
    gb = K.BOX["Globe"]
    gx, gz = (gb["min"][0] + gb["max"][0]) / 2, (gb["min"][2] + gb["max"][2]) / 2
    part("Globe", "Wood_Dark", lambda bm: (cyl(bm, (gx, 0.0, gz), (gx, 0.05, gz), 0.25, 0.25, 16), cyl(bm, (gx, 0.05, gz), (gx, 0.72, gz), 0.03, 0.03, 8)))
    part("Globe_Ball", "Globe_Map", lambda bm: sphere(bm, (gx, 0.86, gz), 0.22, 18), smooth=True)
    part("decor_Globe_Ring", "Brass", lambda bm: torus(bm, (gx, 0.86, gz), "x", 0.25, 0.008, 24, 4))
    # the pedestal: a white column with a shallow bowl on top
    pb = K.BOX["Pedestal"]
    px, pz = (pb["min"][0] + pb["max"][0]) / 2, (pb["min"][2] + pb["max"][2]) / 2
    part("Pedestal", "Marble", lambda bm: (box(bm, pb["min"][0], pb["max"][0], 0.0, 0.12, pb["min"][2], pb["max"][2]),
                                           cyl(bm, (px, 0.12, pz), (px, 0.88, pz), 0.25, 0.22, 20),
                                           box(bm, pb["min"][0] + 0.04, pb["max"][0] - 0.04, 0.88, 0.94, pb["min"][2] + 0.04, pb["max"][2] - 0.04)))
    part("decor_Pedestal_Bowl", "Brass", lambda bm: cyl(bm, (px, 0.94, pz), (px, 1.0, pz), 0.14, 0.2, 20, cap=False))
    # the round rug and the ceiling's painted stars
    part("decor_Rug", "Rug_Round", lambda bm: disc(bm, (0.0, 0.006, -0.6), "y", 2.0, 40), recalc=False)
    for k, (x, z) in enumerate(((-2.0, -2.0), (2.0, 1.5)), 1):
        pendant(f"Pendant_{k}", x, z, 0.8, 0.18, "Shade_Paper", kind="globe", watts=20)


MOON_WINDOW = dict(
    pages=(2048, 1024),
    grade={"target": 1.7, "shoulder": 1.15, "caps": {"Trim_White": 0.88}},
    mats={"Carpet_Stars": dict(gen="carpet", rough=1.0, tile=1.6, group="struct"),
          "Plaster_Lilac": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.78, 0.68, 0.95), rough=0.95, tile=2.5, group="struct"),
          "Ceiling_Navy": dict(gen="ceiling", rough=0.95, tile=3.0, group="struct"),
          "Trim_White": dict(color=(0.90, 0.89, 0.86), rough=0.45, group="struct"),
          "Window_Night": dict(gen="sky", rough=1.0, emit_tex=1.6, group=None),
          "Moon_Glow": dict(gen="moon", rough=1.0, emit_tex=2.2, group=None),
          "Curtain_Navy": dict(diff="rough_linen_diff_512.jpg", tint=(0.10, 0.12, 0.35), rough=1.0, tile=0.6, two_sided=True),
          "Velvet_Navy": dict(diff="rough_linen_diff_512.jpg", tint=(0.12, 0.14, 0.40), rough=1.0, tile=0.5),
          "Shade_Green": dict(color=(0.05, 0.35, 0.18), rough=0.3, two_sided=True),
          "Shade_Paper": dict(color=(0.95, 0.92, 0.85), rough=0.6, emit=((1.0, 0.88, 0.7), 1.5), group=None),
          "Star_Chart": dict(gen="chart", rough=0.8),
          "Globe_Map": dict(gen="globe", rough=0.5),
          "Rug_Round": dict(diff="rough_linen_diff_512.jpg", tint=(0.55, 0.45, 0.72), rough=1.0, tile=0.7)},
    gen={"carpet": g_carpet((0.05, 0.07, 0.24), (0.12, 0.16, 0.42), seed=33, pattern=stars_pattern((0.75, 0.66, 0.30))),
         "ceiling": g_carpet((0.07, 0.09, 0.26), (0.10, 0.12, 0.32), seed=34, pattern=stars_pattern((0.9, 0.85, 0.6), 0.004, 2)),
         "sky": g_night_sky(), "moon": g_moon(),
         "chart": lambda: (lambda rng: np.clip(g_night_sky(512, 35)()[:, :, :] * 2.5 + 0.03, 0, 1))(None),
         "globe": lambda: (lambda rng: np.where((vnoise(256, 512, rng, 5, 3) > 0.52)[..., None], np.array([0.35, 0.45, 0.2]),
                                                np.array([0.15, 0.35, 0.6])).astype(np.float32))(np.random.default_rng(36))},
    dress=dress_moon_window,
    shots={"1_arrival": ((3.6, 1.55, 0.0), (-1.0, 1.9, -5.5), 72.0),
           "2_wide": ((4.3, 2.5, 5.3), (-2.0, 1.2, -4.0), 78.0),
           "3_detail": ((0.0, 1.5, -2.6), (0.0, 2.3, -6.0), 58.0)},
)


def bench(name, b, seat_mat, leg_mat, slats=True):
    mn, mx = b["min"], b["max"]
    along_x = (mx[0] - mn[0]) >= (mx[2] - mn[2])

    def seat(bm):
        if slats:
            n = 4
            for k in range(n):
                if along_x:
                    z0 = mn[2] + (mx[2] - mn[2]) * k / n + 0.008
                    box(bm, mn[0], mx[0], mx[1] - 0.04, mx[1], z0, z0 + (mx[2] - mn[2]) / n - 0.016)
                else:
                    x0 = mn[0] + (mx[0] - mn[0]) * k / n + 0.008
                    box(bm, x0, x0 + (mx[0] - mn[0]) / n - 0.016, mx[1] - 0.04, mx[1], mn[2], mx[2])
        else:
            box(bm, mn[0], mx[0], mx[1] - 0.05, mx[1], mn[2], mx[2])
    part(name, seat_mat, seat)

    def legs(bm):
        if along_x:
            for x in (mn[0] + 0.12, mx[0] - 0.12):
                box(bm, x - 0.025, x + 0.025, 0.0, mx[1] - 0.04, mn[2] + 0.03, mx[2] - 0.03)
        else:
            for z in (mn[2] + 0.12, mx[2] - 0.12):
                box(bm, mn[0] + 0.03, mx[0] - 0.03, 0.0, mx[1] - 0.04, z - 0.025, z + 0.025)
    part(name + "_Legs", leg_mat, legs)


def up_picture(name, mname, c, w, d, uv):
    """A flat picture lying face up (its top toward -z, north)."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    f = quad(bm, (c[0] - w / 2, c[1], c[2] + d / 2), (c[0] + w / 2, c[1], c[2] + d / 2), (c[0] + w / 2, c[1], c[2] - d / 2), (c[0] - w / 2, c[1], c[2] - d / 2))
    u0, v0, u1, v1 = uv
    for lp, (s, t) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = (u0 + (u1 - u0) * s, v0 + (v1 - v0) * t)
    f.normal_update()
    if f.normal.z < 0:
        f.normal_flip()
    return finish(name, bm, mname, keep_uv=True, recalc=False)


def mirror_copy(ob, name, coll=None):
    """A copy of `ob` reflected across x = 0 (the mirror room's glass line), faces turned back out."""
    me = ob.data.copy()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(ob.matrix_world)
    bm.transform(Matrix.Diagonal((-1, 1, 1, 1)))
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    c = bpy.data.objects.new(name, me)
    (coll or K.ART).objects.link(c)
    return c


# ================================================================ 22. rdwe_mirror_room
def dress_mirror_room():
    """A magenta sitting room doubled across a glass line at x = 0: the west half is the room, the east half its reflection, built as the west
    half reflected (so the clock runs the other way and the books and pictures read backwards). The glass is in two gilt-framed panes with a gap
    in the middle; the reflection's south door is the real way on. Everything east of the glass is the `Mirror_World` group: its own nodes."""
    shell("Floor_Parquet", "Paper_Magenta", "Ceiling_White", skirt="Trim_White", casing="Trim_White", dado=("Panel_White", 0.95, "Trim_White"))
    cornice("Trim_White")
    before = {o.name for o in K.ART.objects}
    # the west half
    sofa("Sofa_W", K.BOX["Sofa_W"], "Velvet_Magenta", "Wood_Dark", back="N")
    table("Coffee_Table_W", K.BOX["Coffee_Table_W"], "Marble", "Brass", t=0.03, r=0.015, inset=0.06)
    armchair("Armchair_W", K.BOX["Armchair_W"], "Velvet_Magenta", "Wood_Dark", back="W")
    table("Lamp_Table_W", K.BOX["Lamp_Table_W"], "Trim_White", "Trim_White", t=0.03, inset=0.03)
    lt = K.BOX["Lamp_Table_W"]
    lx, lz, ly = (lt["min"][0] + lt["max"][0]) / 2, (lt["min"][2] + lt["max"][2]) / 2, lt["max"][1]
    part("decor_Table_Lamp_W", "Brass", lambda bm: (cyl(bm, (lx, ly, lz), (lx, ly + 0.03, lz), 0.09, 0.09, 14), cyl(bm, (lx, ly + 0.03, lz), (lx, ly + 0.42, lz), 0.012, 0.012, 8)))
    part("decor_Table_Lamp_W_Shade", "Shade_Pink", lambda bm: cyl(bm, (lx, ly + 0.36, lz), (lx, ly + 0.6, lz), 0.2, 0.13, 18, cap=False))
    part("decor_Table_Lamp_W_Bulb", "Lamp_Emit", lambda bm: sphere(bm, (lx, ly + 0.45, lz), 0.04, 8))
    light("POINT", (lx, ly + 0.46, lz), 35.0, WARM, 0.05)
    light("POINT", (-lx, ly + 0.46, lz), 35.0, WARM, 0.05)
    cabinet("Sideboard_W", K.BOX["Sideboard_W"], "Wood_Dark", "Wood_Dark", doors=3, face="N")
    sb = K.BOX["Sideboard_W"]
    sy = sb["max"][1]
    P = Painter()
    rng = np.random.default_rng(41)
    books_row(P, -2.5, -1.9, sy, 4.62, 4.9, rng, hmax=0.26)
    P.add("ivory", box, -1.2, -0.95, sy, sy + 0.32, 4.62, 4.88)                       # the mantel clock's case
    P.add("pink", cyl, (-1.6, sy, 4.75), (-1.6, sy + 0.3, 4.75), 0.07, 0.1, 12)          # a vase
    P.done("decor_Sideboard_Things_W")
    picture("decor_Mantel_Clock_W", "Clock_Faces", (-1.075, sy + 0.2, 4.618), "-z", 0.18, 0.18, ATLAS_MIRROR.uv("clock"))
    rug("Rug_W", -7.4, -0.8, -3.4, 3.4, "Rug_Pink")
    for k, (a, pw, ph, pk) in enumerate(((-6.0, 1.2, 0.9, 0), (-2.4, 0.8, 1.0, 2)), 1):
        frame_picture(f"Pic_N{k}_W", "N", a, 2.1, pw, ph, "Paintings", uv=painting_uv(pk))
    frame_picture("Pic_S1_W", "S", -6.4, 2.1, 1.0, 0.7, "Paintings", uv=painting_uv(4))
    picture("decor_Sign_W", "Signs_Mirror", (-1.6, 2.6, K.Z0 + 0.03), "+z", 1.2, 0.3, ATLAS_MIRROR.uv("sign"))
    pendant("Chandelier_W", -4.0, 0.0, 0.9, 0.28, "Shade_Pink", kind="cone", watts=60)
    light("POINT", (4.0, K.H - 0.98, 0.0), 60.0, WARM, 0.06)
    west = [o for o in K.ART.objects if o.name not in before]
    # the reflection: every west piece, reflected; named as the east half's boxes where it has one
    for o in west:
        c = mirror_copy(o, o.name.replace("_W", "_E"))
        K.MIRROR.add(c.name)
    # the glass line: two panes in gilt frames, a gap in the middle
    for n in ("Glass_N", "Glass_S"):
        b = K.BOX[n]
        part(n, "Glass_Clear", lambda bm, b=b: box(bm, -0.006, 0.006, 0.05, K.H - 0.08, b["min"][2] + 0.04, b["max"][2] - 0.04))
        part(n + "_Frame", "Frame_Gilt", lambda bm, b=b: (box(bm, -0.05, 0.05, 0.0, 0.08, b["min"][2], b["max"][2]),
                                                          box(bm, -0.05, 0.05, 0.0, K.H, b["min"][2], b["min"][2] + 0.06),
                                                          box(bm, -0.05, 0.05, 0.0, K.H, b["max"][2] - 0.06, b["max"][2])))
    part("decor_Glass_Head", "Frame_Gilt", lambda bm: box(bm, -0.06, 0.06, K.H - 0.1, K.H, K.Z0, K.Z1))
    K.spec["separate"] = {"Mirror_World": "the reflection: the west half reflected across the glass (static, baked; the page may hide or swap it)"}


def mirror_post():
    """After the leaves: the west door's reflection on the east wall (a flat copy of the leaf and its casing, part of the reflection)."""
    lf = bpy.data.objects["DoorLeaf_moon"]
    c = mirror_copy(lf, "decor_Mirror_Door_Moon")
    c.data.materials.clear()
    for m in lf.data.materials:
        c.data.materials.append(m)
    K.MIRROR.add(c.name)
    h = next(hh for hh in K.HOLES if hh["name"] == "DoorLeaf_moon")
    a, hw, ht = h["a"], h["w"] / 2, h["h"]
    ob = part("decor_Mirror_Door_Casing", "Trim_White", lambda bm: (wall_box(bm, "E", a - hw - 0.075, a - hw, 0.0, ht + 0.075, 0.0, 0.022),
                                                                     wall_box(bm, "E", a + hw, a + hw + 0.075, 0.0, ht + 0.075, 0.0, 0.022),
                                                                     wall_box(bm, "E", a - hw, a + hw, ht, ht + 0.075, 0.0, 0.022)))
    K.MIRROR.add(ob.name)
    part("decor_Mirror_Door_Dark", "Void_Black", lambda bm: wall_box(bm, "E", a - hw, a + hw, 0.0, ht, 0.0, 0.002))


ATLAS_MIRROR = Atlas([("clock", 256, 256, clock_face(10.2, hands=True)), ("sign", 512, 128, sign("NOTHING IS WRONG", (0.95, 0.9, 0.92), (0.5, 0.05, 0.3)))])


MIRROR_ROOM = dict(
    pages=(2048, 2048),
    grade={"target": 0.9, "shoulder": 1.15},
    mats={"Floor_Parquet": dict(diff="herringbone_parquet_diff_1k.jpg", tint=(1.0, 0.92, 0.86), rough=0.4, tile=1.6, group="struct"),
          "Paper_Magenta": dict(gen="paper", rough=0.9, tile=0.9, group="struct"),
          "Panel_White": dict(color=(0.90, 0.88, 0.86), rough=0.5, group="struct"),
          "Ceiling_White": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.94, 0.92, 0.92), rough=0.95, tile=2.5, group="struct"),
          "Trim_White": dict(color=(0.93, 0.92, 0.90), rough=0.45, group="struct"),
          "Velvet_Magenta": dict(diff="rough_linen_diff_512.jpg", tint=(0.75, 0.08, 0.48), rough=1.0, tile=0.5),
          "Shade_Pink": dict(color=(0.98, 0.70, 0.80), rough=0.6, two_sided=True),
          "Rug_Pink": dict(diff="rough_linen_diff_512.jpg", tint=(0.85, 0.62, 0.70), rough=1.0, tile=0.6),
          "Paintings": dict(gen="paintings", rough=0.6),
          "Frame_Gilt": dict(color=(0.66, 0.50, 0.22), rough=0.35, metal=0.8),
          "Clock_Faces": dict(gen="atlas", rough=0.5),
          "Signs_Mirror": dict(gen="atlas", rough=0.6)},
    gen={"paper": g_damask((0.70, 0.08, 0.45), (0.85, 0.30, 0.62), seed=42), "paintings": g_paintings(43), "atlas": ATLAS_MIRROR.pixels},
    dress=dress_mirror_room,
    post=mirror_post,
    groups={"Mirror_World": "MIRROR"},
    shots={"1_arrival": ((-4.0, 1.55, 3.6), (1.0, 1.3, -3.0), 74.0),
           "2_wide": ((-7.4, 2.4, 4.4), (3.0, 1.0, -2.0), 80.0),
           "3_detail": ((-2.4, 1.55, 0.0), (6.0, 1.2, 0.0), 66.0)},
)


# ================================================================ 23. rdwe_dont_look
def dress_dont_look():
    """A white gallery on a marble floor: paintings under track lights, two benches, four plinths with busts, and the statue in front of the east
    door, a robed figure with her hands over her face. The statue is its own object (the page moves it when you look away), not baked; her
    collider is where she starts."""
    shell("Marble_Floor", "Plaster_White", "Ceiling_White", skirt="Trim_Grey", casing="Trim_Grey")
    rail("Trim_Grey", 3.2, 0.04, 0.02, name="decor_Trim_Picture_Rail")
    st = K.BOX["Statue"]
    sx, sz = (st["min"][0] + st["max"][0]) / 2, (st["min"][2] + st["max"][2]) / 2

    def statue(bm):
        box(bm, st["min"][0] + 0.02, st["max"][0] - 0.02, 0.0, 0.14, st["min"][2] + 0.02, st["max"][2] - 0.02)
        cyl(bm, (sx, 0.14, sz), (sx, 1.25, sz), 0.42, 0.24, 24)                    # the robe
        cyl(bm, (sx, 1.25, sz), (sx, 1.9, sz), 0.24, 0.2, 20)                     # the body
        sphere(bm, (sx, 1.96, sz), 0.2, 16, 0.6)                                     # shoulders
        cyl(bm, (sx, 2.0, sz), (sx, 2.13, sz), 0.07, 0.07, 12)                    # neck
        sphere(bm, (sx, 2.25, sz + 0.0), 0.12, 16, 1.15)                             # the head
        for sg in (-1, 1):                                                           # arms up, hands over the face (she faces west)
            cyl(bm, (sx, 1.94, sz + sg * 0.2), (sx - 0.22, 2.1, sz + sg * 0.12), 0.055, 0.05, 10)
            cyl(bm, (sx - 0.22, 2.1, sz + sg * 0.12), (sx - 0.13, 2.26, sz + sg * 0.04), 0.05, 0.045, 10)
            sphere(bm, (sx - 0.13, 2.26, sz + sg * 0.045), 0.055, 10, 0.8, sx=0.6)
            for k in range(5):                                                       # the wings, folded behind
                y0 = 2.08 - k * 0.24
                quad(bm, (sx + 0.15, y0, sz + sg * 0.15), (sx + 0.42, y0 + 0.25, sz + sg * (0.3 + 0.03 * k)),
                     (sx + 0.44, y0 - 0.05, sz + sg * (0.32 + 0.03 * k)), (sx + 0.2, y0 - 0.25, sz + sg * 0.17))
        for k in range(10):                                                          # the robe's folds
            a = 2 * math.pi * k / 10
            cyl(bm, (sx + 0.38 * math.cos(a), 0.14, sz + 0.38 * math.sin(a)), (sx + 0.22 * math.cos(a), 1.25, sz + 0.22 * math.sin(a)), 0.05, 0.03, 6)
    moving_part("Statue", "Statue_Stone", statue, (sx, 0.0, sz), smooth=True, sharp_deg=50)
    K.spec["moving"] = {"Statue": "moves toward the east door's spot only while no one is looking at it; its collider starts here"}
    # the plinths and their busts
    for k in range(1, 5):
        b = K.BOX[f"Plinth_{k}"]
        cx, cz, top = (b["min"][0] + b["max"][0]) / 2, (b["min"][2] + b["max"][2]) / 2, b["max"][1]
        part(f"Plinth_{k}", "Plinth_White", lambda bm, b=b: (box(bm, b["min"][0], b["max"][0], 0.0, 0.08, b["min"][2], b["max"][2]),
                                                             box(bm, b["min"][0] + 0.04, b["max"][0] - 0.04, 0.08, b["max"][1] - 0.05, b["min"][2] + 0.04, b["max"][2] - 0.04),
                                                             box(bm, b["min"][0], b["max"][0], b["max"][1] - 0.05, b["max"][1], b["min"][2], b["max"][2])))
        part(f"decor_Bust_{k}", "Marble", lambda bm, cx=cx, cz=cz, top=top: (cyl(bm, (cx, top, cz), (cx, top + 0.06, cz), 0.12, 0.12, 14),
                                                                              sphere(bm, (cx, top + 0.2, cz), 0.2, 14, 0.5),
                                                                              cyl(bm, (cx, top + 0.26, cz), (cx, top + 0.36, cz), 0.06, 0.06, 10),
                                                                              sphere(bm, (cx, top + 0.46, cz), 0.11, 14, 1.2)), smooth=True)
    for n in ("Bench_N", "Bench_S"):
        bench(n, K.BOX[n], "Wood_Oak", "Steel", slats=False)
    # paintings, each under its own spot
    pics = [("N", -4.5, 2.0, 1.6, 1.1, 0), ("N", 0.0, 2.1, 2.2, 1.4, 1), ("N", 4.4, 2.0, 1.2, 1.5, 2), ("S", -4.5, 2.0, 1.4, 1.0, 3),
            ("S", 0.0, 2.1, 2.0, 1.3, 4), ("S", 4.4, 2.0, 1.3, 1.3, 5), ("W", -3.2, 2.0, 1.0, 1.3, 6), ("W", 3.2, 2.0, 1.0, 1.3, 7)]
    for k, (sd, a, y, pw, ph, pk) in enumerate(pics, 1):
        frame_picture(f"Pic_{k}", sd, a, y, pw, ph, "Paintings", uv=painting_uv(pk))
        tgt = on_wall(sd, a, y, 0.0)
        src = on_wall(sd, a, K.H - 0.12, 1.4)
        aim = tuple(tgt[i] - src[i] for i in range(3))
        light("SPOT", src, 90.0, (1.0, 0.93, 0.82), 0.05, aim=aim, cone=38.0)
    # the track: two rails along the room with their spot cans
    part("decor_Track", "Iron", lambda bm: [box(bm, -6.5, 6.5, K.H - 0.04, K.H, z - 0.02, z + 0.02) for z in (-3.6, 3.6)])
    part("decor_Track_Cans", "Iron", lambda bm: [cyl(bm, (x, K.H - 0.04, z), (x, K.H - 0.2, z + (0.06 if z < 0 else -0.06)), 0.05, 0.06, 12)
                                                 for x in (-4.5, 0.0, 4.4) for z in (-3.6, 3.6)])
    part("decor_Track_Lenses", "Lamp_Emit", lambda bm: [disc(bm, (x, K.H - 0.205, z + (0.06 if z < 0 else -0.06)), "y", 0.05, 12, -1) for x in (-4.5, 0.0, 4.4)
                                                        for z in (-3.6, 3.6)], recalc=False)
    light("SPOT", (2.2, K.H - 0.1, 0.0), 220.0, (1.0, 0.95, 0.88), 0.08, aim=(1.3, -2.6, 0.0), cone=45.0, name="Statue_Spot")
    light("AREA", (0.0, K.H - 0.05, 0.0), 90.0, (1.0, 0.97, 0.92), aim=(0, -1, 0), size=(10.0, 6.0), name="Fill")
    # stanchions and a rope round the statue's plinth line? (no: she must be free to move) - a placard on the floor instead
    picture("decor_Placard", "Signs_Gallery", (2.2, 1.0, 0.0), "-x", 0.3, 0.2, ATLAS_GALLERY.uv("placard"))
    part("decor_Placard_Stand", "Iron", lambda bm: (cyl(bm, (2.22, 0.0, 0.0), (2.22, 0.9, 0.0), 0.012, 0.012, 6), box(bm, 2.205, 2.23, 0.88, 1.1, -0.16, 0.16)))


ATLAS_GALLERY = Atlas([("placard", 384, 256, sign(["THE WATCHER", "MARBLE, DATE UNKNOWN", "PLEASE DO NOT", "LOOK AWAY"], (0.92, 0.9, 0.85),
                                                  (0.12, 0.1, 0.08)))])

DONT_LOOK = dict(
    pages=(2048, 1024),
    grade={"target": 0.95, "shoulder": 1.15},
    mats={"Marble_Floor": dict(diff="Marble012_color_1k.jpg", tint=(0.92, 0.9, 0.88), rough=0.2, tile=2.0, group="struct"),
          "Plaster_White": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.9, 0.89, 0.86), rough=0.95, tile=2.5, group="struct"),
          "Ceiling_White": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.92, 0.91, 0.9), rough=0.95, tile=2.5, group="struct"),
          "Trim_Grey": dict(color=(0.55, 0.55, 0.54), rough=0.5, group="struct"),
          "Statue_Stone": dict(diff="marble_01_diff_1k.jpg", tint=(0.88, 0.86, 0.82), rough=0.5, tile=0.8, group=None),
          "Plinth_White": dict(color=(0.88, 0.87, 0.85), rough=0.6),
          "Paintings": dict(gen="paintings", rough=0.6),
          "Frame_Gilt": dict(color=(0.66, 0.50, 0.22), rough=0.35, metal=0.8),
          "Signs_Gallery": dict(gen="atlas", rough=0.6)},
    gen={"paintings": g_paintings(51), "atlas": ATLAS_GALLERY.pixels},
    dress=dress_dont_look,
    shots={"1_arrival": ((-5.6, 1.55, 0.0), (4.0, 1.4, 0.0), 66.0),
           "2_wide": ((-6.4, 2.6, 4.4), (4.0, 1.0, -2.0), 78.0),
           "3_detail": ((1.0, 1.55, 1.6), (3.5, 1.7, 0.0), 58.0)},
)


# ================================================================ 24. rdwe_waiting_room
def dress_waiting_room():
    """An institution's waiting room: mint walls over a darker mint dado, grey vinyl tiles, a tiled ceiling with troffers. Three rows of blue
    bucket seats on beams face the door under the red NOW SERVING display; a ticket machine with its paper tongue, a water cooler, a plant, a
    table of old magazines, a closed hatch with a bell, a notice board and a clock that has stopped."""
    shell("Vinyl_Grey", "Plaster_Mint", "Ceiling_Tiles", skirt="Trim_Mint", casing="Trim_Mint", dado=("Paint_Mint_Dark", 1.1, "Trim_Mint"))
    for k in range(1, 4):
        b = K.BOX[f"Seats_{k}"]
        x0, x1, z0, z1 = b["min"][0], b["max"][0], b["min"][2], b["max"][2]
        n = 6

        def seats(bm, x0=x0, x1=x1, z0=z0, z1=z1):
            for i in range(n):
                a0 = x0 + (x1 - x0) * i / n + 0.04
                a1 = x0 + (x1 - x0) * (i + 1) / n - 0.04
                box(bm, a0, a1, 0.40, 0.45, z0, z1)
                box(bm, a0, a1, 0.45, 0.86, z1 - 0.06, z1 - 0.02)
        part(f"Seats_{k}", "Plastic_Blue", seats)

        def beam(bm, x0=x0, x1=x1, z0=z0, z1=z1):
            box(bm, x0, x1, 0.33, 0.40, (z0 + z1) / 2 - 0.04, (z0 + z1) / 2 + 0.04)
            for x in (x0 + 0.3, (x0 + x1) / 2, x1 - 0.3):
                box(bm, x - 0.03, x + 0.03, 0.0, 0.33, (z0 + z1) / 2 - 0.03, (z0 + z1) / 2 + 0.03)
                box(bm, x - 0.04, x + 0.04, 0.0, 0.02, z0 + 0.02, z1 - 0.02)
        part(f"Seats_{k}_Frame", "Chrome", beam)
    tm = K.BOX["Ticket_Machine"]
    part("Ticket_Machine", "Paint_Red", lambda bm: (box(bm, tm["min"][0] + 0.15, tm["max"][0] - 0.15, 0.0, 1.0, tm["min"][2] + 0.15, tm["max"][2] - 0.15),
                                                    box(bm, tm["min"][0], tm["max"][0], 1.0, 1.4, tm["min"][2], tm["max"][2]),
                                                    box(bm, tm["min"][0] + 0.1, tm["max"][0] - 0.1, 0.0, 0.05, tm["min"][2] + 0.1, tm["max"][2] - 0.1)))
    picture("decor_Ticket_Screen", "Screen_Ticket", (tm["min"][0] - 0.005, 1.25, 3.8), "-x", 0.4, 0.14, ATLAS_WAIT.uv("ticket_screen"))
    P = Painter()
    P.add("white", box, tm["min"][0] - 0.004, tm["min"][0] + 0.002, 0.95, 1.05, 3.72, 3.84)     # the ticket's tongue
    P.add("black", box, tm["min"][0] - 0.003, tm["min"][0], 1.06, 1.08, 3.66, 3.9)              # the slot
    P.done("decor_Ticket_Tongue")
    nd = K.BOX["decor_Number_Display"]
    picture("decor_Number_Display", "Screen_Number", ((nd["min"][0] + nd["max"][0]) / 2, (nd["min"][1] + nd["max"][1]) / 2, K.Z0 + 0.085), "+z",
            nd["max"][0] - nd["min"][0], nd["max"][1] - nd["min"][1], ATLAS_WAIT.uv("number"))
    part("decor_Number_Box", "Iron", lambda bm: box(bm, nd["min"][0] - 0.05, nd["max"][0] + 0.05, nd["min"][1] - 0.05, nd["max"][1] + 0.05, K.Z0, K.Z0 + 0.08))
    light("AREA", (3.0, 2.45, K.Z0 + 0.2), 6.0, (1.0, 0.2, 0.1), aim=(0, -0.3, 1), size=(2.0, 0.5), name="Display_Glow")
    wc = K.BOX["Water_Cooler"]
    wx, wz = (wc["min"][0] + wc["max"][0]) / 2, (wc["min"][2] + wc["max"][2]) / 2
    part("Water_Cooler", "Plastic_White", lambda bm: box(bm, wc["min"][0], wc["max"][0], 0.0, 1.0, wc["min"][2], wc["max"][2]))
    part("Water_Cooler_Bottle", "Glass_Blue", lambda bm: cyl(bm, (wx, 1.0, wz), (wx, 1.3, wz), 0.13, 0.13, 16), smooth=True)
    pl = K.BOX["Plant"]
    plant("Plant", (pl["min"][0] + pl["max"][0]) / 2, (pl["min"][2] + pl["max"][2]) / 2, 0.0, 1.2, np.random.default_rng(52), 0.25)
    mt = K.BOX["Magazine_Table"]
    table("Magazine_Table", mt, "Wood_Oak", "Chrome", t=0.03, r=0.015, inset=0.05, apron=False)
    P = Painter()
    rng = np.random.default_rng(53)
    for i in range(7):
        x, z = rng.uniform(3.35, 4.1), rng.uniform(-0.3, 0.1)
        P.add(["red", "blue", "yellow", "paper", "pink", "green", "orange"][i], box, x, x + 0.21, 0.42 + i * 0.006, 0.425 + i * 0.006, z, z + 0.28)
    P.done("decor_Magazines")
    cb = K.BOX["Counter"]
    part("Counter", "Wood_Oak", lambda bm: bx(bm, cb))
    part("decor_Hatch", "Frosted", lambda bm: wall_box(bm, "S", -1.6, 1.6, 1.15, 2.2, 0.0, 0.01))
    part("decor_Hatch_Frame", "Trim_Mint", lambda bm: (wall_box(bm, "S", -1.7, 1.7, 1.08, 1.15, 0.0, 0.04), wall_box(bm, "S", -1.7, 1.7, 2.2, 2.27, 0.0, 0.04),
                                                       wall_box(bm, "S", -1.7, -1.6, 1.15, 2.2, 0.0, 0.04), wall_box(bm, "S", 1.6, 1.7, 1.15, 2.2, 0.0, 0.04),
                                                       wall_box(bm, "S", -0.02, 0.02, 1.15, 2.2, 0.0, 0.03)))
    part("decor_Bell", "Chrome", lambda bm: (cyl(bm, (0.6, cb["max"][1], 4.7), (0.6, cb["max"][1] + 0.01, 4.7), 0.05, 0.05, 12),
                                             sphere(bm, (0.6, cb["max"][1] + 0.02, 4.7), 0.045, 12, 0.7)))
    picture("decor_Hatch_Sign", "Signs_Wait", (0.0, 2.45, K.Z1 - 0.012), "-z", 1.6, 0.2, ATLAS_WAIT.uv("hatch"))
    cs = K.BOX["Coat_Stand"]
    cx, cz = (cs["min"][0] + cs["max"][0]) / 2, (cs["min"][2] + cs["max"][2]) / 2
    part("Coat_Stand", "Chrome", lambda bm: (cyl(bm, (cx, 0.0, cz), (cx, 1.8, cz), 0.02, 0.02, 10),
                                             [cyl(bm, (cx, 0.02, cz), (cx + 0.18 * math.cos(a), 0.0, cz + 0.18 * math.sin(a)), 0.012, 0.012, 6)
                                              for a in (0.3, 2.4, 4.5)]))
    part("decor_Umbrella", "Iron", lambda bm: cyl(bm, (cx + 0.08, 0.05, cz + 0.05), (cx + 0.1, 0.95, cz + 0.02), 0.04, 0.015, 8))
    picture("decor_Notices", "Signs_Wait", on_wall("W", -3.0, 1.75, 0.01), "+x", 1.4, 0.9, ATLAS_WAIT.uv("notices"))
    part("decor_Notice_Frame", "Wood_Oak", lambda bm: wall_box(bm, "W", -3.75, -2.25, 1.27, 2.23, 0.0, 0.008))
    picture("decor_Clock", "Signs_Wait", on_wall("E", 1.0, 2.35, 0.02), "-x", 0.42, 0.42, ATLAS_WAIT.uv("clock"))
    part("decor_Clock_Rim", "Iron", lambda bm: cyl(bm, on_wall("E", 1.0, 2.35, 0.0), on_wall("E", 1.0, 2.35, 0.018), 0.23, 0.23, 24))
    picture("decor_Poster", "Signs_Wait", on_wall("E", -2.6, 1.6, 0.004), "-x", 0.7, 1.0, ATLAS_WAIT.uv("poster"))
    ceiling_troffers([-4.5, 0.0, 4.5], [-2.5, 2.5], along="x", watts=55.0, color=TUBE, lit=lambda x, z: not (x > 4 and z < 0))


ATLAS_WAIT = Atlas([("number", 512, 128, sign(["NOW SERVING  07"], (0.05, 0.02, 0.02), (1.0, 0.12, 0.05))),
                    ("ticket_screen", 256, 128, sign(["TAKE A", "NUMBER"], (0.05, 0.08, 0.1), (0.4, 0.9, 1.0))),
                    ("hatch", 512, 64, sign("PLEASE WAIT TO BE CALLED", (0.88, 0.9, 0.86), (0.1, 0.25, 0.2))),
                    ("notices", 384, 256, lambda h, w: text_lines(["NOTICE", "", "YOUR NUMBER WILL", "BE CALLED", "", "DO NOT LEAVE", "THE WAITING ROOM"],
                                                                 h, w, (0.86, 0.84, 0.76), (0.12, 0.12, 0.14), rng=np.random.default_rng(3))),
                    ("clock", 256, 256, clock_face(3.95, hands=True, bg=(0.95, 0.95, 0.93))),
                    ("poster", 256, 384, lambda h, w: text_lines(["", "WAITING", "IS", "PART OF", "THE", "PROCESS", ""], h, w, (0.35, 0.65, 0.55),
                                                                 (0.95, 0.95, 0.9), rng=np.random.default_rng(4)))])

WAITING_ROOM = dict(
    pages=(2048, 1024),
    grade={"target": 0.95, "shoulder": 1.15},
    mats={"Vinyl_Grey": dict(gen="vinyl", rough=0.5, tile=2.4, group="struct"),
          "Plaster_Mint": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.62, 0.88, 0.76), rough=0.95, tile=2.5, group="struct"),
          "Paint_Mint_Dark": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.30, 0.58, 0.48), rough=0.6, tile=2.5, group="struct"),
          "Ceiling_Tiles": dict(gen="ceiltile", rough=0.9, tile=1.2, group="struct"),
          "Trim_Mint": dict(color=(0.22, 0.42, 0.36), rough=0.5, group="struct"),
          "Trim_White": dict(color=(0.92, 0.92, 0.9), rough=0.5),
          "Plastic_Blue": dict(color=(0.08, 0.30, 0.62), rough=0.4),
          "Plastic_White": dict(color=(0.88, 0.88, 0.86), rough=0.4),
          "Paint_Red": dict(color=(0.72, 0.06, 0.05), rough=0.4),
          "Glass_Blue": dict(color=(0.45, 0.65, 0.85), rough=0.1),
          "Pot_Clay": dict(color=(0.55, 0.28, 0.16), rough=0.8),
          "Plant_Leaf": dict(color=(0.10, 0.30, 0.10), rough=0.6, two_sided=True),
          "Frosted": dict(color=(0.80, 0.84, 0.84), rough=0.3),
          "Screen_Number": dict(gen="atlas", rough=0.5, emit_tex=3.0, group=None),
          "Screen_Ticket": dict(gen="atlas", rough=0.5, emit_tex=2.0, group=None),
          "Signs_Wait": dict(gen="atlas", rough=0.6)},
    gen={"vinyl": g_tiles((0.55, 0.56, 0.56), (0.40, 0.40, 0.40), n=4, S=512, accent=((0.42, 0.44, 0.45), 0.3), seed=54),
         "ceiltile": g_tiles((0.86, 0.86, 0.84), (0.62, 0.62, 0.6), n=2, S=256, seed=55, jitter=0.02),
         "atlas": ATLAS_WAIT.pixels},
    dress=dress_waiting_room,
    shots={"1_arrival": ((-5.6, 1.55, 0.0), (3.0, 1.4, -4.2), 74.0),
           "2_wide": ((6.4, 2.3, 4.4), (-3.0, 0.8, -3.0), 78.0),
           "3_detail": ((1.6, 1.4, -1.6), (3.0, 2.0, -5.0), 60.0)},
)


# ================================================================ 25. rdwe_wrong_clock
CLOCK_HOURS = [1.9, 6.6, 9.2, 11.75, 4.1, 2.45, 7.3, 10.05, 5.5, 12.9, 3.33, 8.8, 0.6, 6.15]


def dress_wrong_clock():
    """A room of grandfather clocks round oxblood damask and dark panelling, every one at its own hour. Their hands and pendulums are their own
    objects (the page turns and swings them; not baked). Clock 2, the tall one on the east wall, runs backward: its face is the teal room's
    wristwatch face, and the watch itself lies under a glass dome on the table in the middle."""
    shell("Floor_Parquet", "Paper_Oxblood", "Ceiling_Dark", skirt="Trim_Dark", casing="Trim_Dark", dado=("Panel_Dark", 1.2, "Trim_Dark"))
    cornice("Trim_Dark")
    for k, hour in enumerate(CLOCK_HOURS, 1):
        b = K.BOX[f"Clock_{k}"]
        face = next(t for t in b["tags"] if t.startswith("face:"))[5:]
        x0, x1, z0, z1, h = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]
        # the clock's own frame: u along its front, n into the room
        if face == "E":
            n, front = (-1, 0, 0), x0
        elif face == "W":
            n, front = (1, 0, 0), x1
        elif face == "N":
            n, front = (0, 0, 1), z1
        else:
            n, front = (0, 0, -1), z0
        along_x = face in "NS"
        lo, hi = (x0, x1) if along_x else (z0, z1)
        mid = (lo + hi) / 2
        wdt = hi - lo
        dep = (z1 - z0) if along_x else (x1 - x0)
        big = wdt > 0.8

        def P3(a, y, d):
            """a along the front, y up, d in from the front face (into the case)"""
            if face == "E":
                return (front + d, y, a)
            if face == "W":
                return (front - d, y, a)
            if face == "N":
                return (a, y, front - d)
            return (a, y, front + d)

        def bxa(bm, a0, a1, y0, y1, d0, d1):
            p, q = P3(a0, y0, d0), P3(a1, y1, d1)
            cube(bm, [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)])

        hood_y0 = h - (0.75 if not big else 1.1)
        fr = 0.2 if not big else 0.32

        def case(bm):
            bxa(bm, lo, hi, 0.0, 0.45, 0.0, dep)                                     # the base
            bxa(bm, lo + 0.06, hi - 0.06, 0.45, hood_y0, 0.04, dep)                  # the trunk
            bxa(bm, lo - 0.02, hi + 0.02, hood_y0, h - 0.12, 0.0, dep)               # the hood
            bxa(bm, lo + 0.03, hi - 0.03, h - 0.12, h, 0.02, dep)                    # the crest
            bxa(bm, lo - 0.03, hi + 0.03, 0.42, 0.47, -0.01, dep)                    # mouldings
            bxa(bm, lo - 0.04, hi + 0.04, hood_y0 - 0.03, hood_y0, -0.01, dep)
        part(f"Clock_{k}", "Clock_Wood", case)
        fy = hood_y0 + (h - 0.12 - hood_y0) / 2
        fc = P3(mid, fy, -0.004)
        nrm = {"E": "-x", "W": "+x", "N": "+z", "S": "-z"}[face]
        picture(f"decor_Clock_{k}_Face", "Clock_Faces", fc, nrm, 2 * fr, 2 * fr, ATLAS_CLOCKS.uv("watch" if k == 2 else f"face{k % 4}"))
        part(f"decor_Clock_{k}_Bezel", "Brass", lambda bm, fc=fc: torus(bm, fc, "x" if face in "EW" else "z", fr + 0.01, 0.012, 28, 6))
        # the trunk's window and the pendulum behind it
        part(f"decor_Clock_{k}_Window", "Glass_Door", lambda bm: bxa(bm, mid - wdt * 0.22, mid + wdt * 0.22, 0.7, hood_y0 - 0.15, 0.035, 0.04))
        piv = P3(mid, hood_y0 - 0.05, 0.12)
        moving_part(f"Clock_{k}_Pendulum", "Brass_Move", lambda bm, piv=piv: (cyl(bm, piv, (piv[0], 0.95, piv[2]), 0.008, 0.008, 6),
                                                                           sphere(bm, (piv[0], 0.95, piv[2]), 0.09 if not big else 0.14, 16, 1.0,
                                                                                  sx=1.0 if face in "NS" else 0.25, sz=0.25 if face in "NS" else 1.0)), piv)
        # the hands, pivoting at the face's centre
        hc = P3(mid, fy, -0.012)
        hr = ((hour % 12) / 12) * 2 * math.pi
        mr = (hour % 1) * 2 * math.pi
        for hn, ang, ln, wd, off in (("Hour", hr, fr * 0.55, 0.022, 0.0), ("Minute", mr, fr * 0.82, 0.014, 0.006)):
            if k == 2:
                ang = -ang

            def hand(bm, ang=ang, ln=ln, wd=wd, off=off, hc=hc):
                ux, uy = math.sin(ang), math.cos(ang)
                tip = (ln * ux, ln * uy)
                tail = (-0.18 * ln * ux, -0.18 * ln * uy)
                pr = (-uy * wd / 2, ux * wd / 2)
                pts2 = [(tail[0] + pr[0], tail[1] + pr[1]), (tip[0], tip[1]), (tail[0] - pr[0], tail[1] - pr[1])]
                pts = []
                for (ua, ya) in pts2:
                    if face == "E":
                        pts.append((hc[0] - off, hc[1] + ya, hc[2] - ua))
                    elif face == "W":
                        pts.append((hc[0] + off, hc[1] + ya, hc[2] + ua))
                    elif face == "N":
                        pts.append((hc[0] + ua, hc[1] + ya, hc[2] + off))
                    else:
                        pts.append((hc[0] - ua, hc[1] + ya, hc[2] - off))
                f = poly(bm, pts)
                f.normal_update()
                want = B(n)
                if f.normal.dot(want) < 0:
                    f.normal_flip()
            moving_part(f"Clock_{k}_{hn}", "Hand_Black", hand, hc, recalc=False)
        light("POINT", P3(mid, h + 0.05, -0.35), 10.0, WARM, 0.1)
    K.spec["moving"] = {**{f"Clock_{k}_Pendulum": "swings about its top (the page)" for k in range(1, 15)},
                        **{f"Clock_{k}_Hour": "turns about the face's centre: the hour hand" for k in range(1, 15)},
                        **{f"Clock_{k}_Minute": "turns about the face's centre: the minute hand" for k in range(1, 15)},
                        "Clock_2_Hour": "runs BACKWARD: the clock to stop (the teal room's watch face)", "Clock_2_Minute": "runs BACKWARD with it",
                        "Watch_Hand": "the wristwatch's second hand, backward"}
    # the watch under its dome
    wt = K.BOX["Watch_Table"]
    table("Watch_Table", wt, "Clock_Wood", "Clock_Wood", t=0.04, inset=0.08, round_=True)
    ty = wt["max"][1]
    part("decor_Dome", "Glass_Clear", lambda bm: (cyl(bm, (0.0, ty + 0.02, 0.0), (0.0, ty + 0.3, 0.0), 0.2, 0.2, 24, cap=False),
                                                  sphere(bm, (0.0, ty + 0.3, 0.0), 0.2, 24, 0.5)))
    part("decor_Dome_Base", "Clock_Wood", lambda bm: cyl(bm, (0.0, ty, 0.0), (0.0, ty + 0.025, 0.0), 0.23, 0.23, 24))
    part("decor_Watch_Strap", "Leather_Brown", lambda bm: box(bm, -0.014, 0.014, ty + 0.025, ty + 0.03, -0.12, 0.12))
    part("decor_Watch_Case", "Chrome", lambda bm: cyl(bm, (0.0, ty + 0.025, 0.0), (0.0, ty + 0.038, 0.0), 0.024, 0.024, 20))
    up_picture("decor_Watch_Face", "Clock_Faces", (0.0, ty + 0.0385, 0.0), 0.044, 0.044, ATLAS_CLOCKS.uv("watch"))
    moving_part("Watch_Hand", "Hand_Black", lambda bm: box(bm, -0.001, 0.001, ty + 0.04, ty + 0.041, -0.002, 0.019), (0.0, ty + 0.04, 0.0))
    for k, (x, z) in enumerate(((-2.5, -2.5), (2.5, 2.5)), 1):
        pendant(f"Chandelier_{k}", x, z, 1.4, 0.3, "Shade_Amber", kind="cone", watts=80)
    rug("Rug", -2.4, 2.4, -2.4, 2.4, "Rug_Red")


ATLAS_CLOCKS = Atlas([(f"face{i}", 256, 256, clock_face(0, hands=False, bg=bg, rim=rim)) for i, (bg, rim) in
                      enumerate((((0.90, 0.86, 0.74), (0.3, 0.2, 0.1)), ((0.93, 0.92, 0.88), (0.6, 0.45, 0.2)), ((0.82, 0.76, 0.62), (0.15, 0.1, 0.06)),
                                 ((0.95, 0.94, 0.9), (0.2, 0.2, 0.22))))]
                     + [("watch", 256, 256, clock_face(0, hands=False, bg=(0.05, 0.38, 0.36), fg=(0.95, 0.92, 0.8), rim=(0.75, 0.76, 0.78)))])

WRONG_CLOCK = dict(
    pages=(2048, 2048),
    grade={"target": 0.9, "shoulder": 1.15},
    mats={"Floor_Parquet": dict(diff="herringbone_parquet_diff_1k.jpg", tint=(0.85, 0.72, 0.6), rough=0.4, tile=1.6, group="struct"),
          "Paper_Oxblood": dict(gen="paper", rough=0.9, tile=0.9, group="struct"),
          "Panel_Dark": dict(diff="dark_wood_diff_1k.jpg", tint=(0.7, 0.6, 0.55), rough=0.5, tile=1.2, group="struct"),
          "Ceiling_Dark": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.72, 0.62, 0.58), rough=0.95, tile=2.5, group="struct"),
          "Trim_Dark": dict(diff="dark_wood_diff_1k.jpg", tint=(0.6, 0.5, 0.45), rough=0.45, tile=0.8, group="struct"),
          "Clock_Wood": dict(diff="dark_wood_diff_1k.jpg", tint=(1.0, 0.8, 0.65), rough=0.35, tile=0.9),
          "Clock_Faces": dict(gen="atlas", rough=0.5),
          "Brass_Move": dict(color=(0.66, 0.50, 0.22), rough=0.3, metal=0.9, group=None),
          "Hand_Black": dict(color=(0.03, 0.03, 0.03), rough=0.4, group=None, two_sided=True),
          "Leather_Brown": dict(color=(0.30, 0.16, 0.08), rough=0.6),
          "Shade_Amber": dict(color=(0.95, 0.6, 0.25), rough=0.4, two_sided=True),
          "Rug_Red": dict(diff="rough_linen_diff_512.jpg", tint=(0.45, 0.08, 0.10), rough=1.0, tile=0.6)},
    gen={"paper": g_damask((0.36, 0.03, 0.05), (0.50, 0.10, 0.10), seed=61), "atlas": ATLAS_CLOCKS.pixels},
    dress=dress_wrong_clock,
    shots={"1_arrival": ((-4.0, 1.55, 0.0), (5.0, 1.8, -1.0), 72.0),
           "2_wide": ((-5.3, 2.8, 5.3), (4.0, 1.2, -3.0), 80.0),
           "3_detail": ((3.4, 1.7, -0.6), (5.0, 2.6, -1.5), 56.0)},
)


# ================================================================ 26. rdwe_crossroads
def dress_crossroads():
    """Four institutional corridors meeting under a painted skylight: terrazzo, acid green gloss over green tile, a white ceiling with
    troffers down each arm, the same benches and the same WAY OUT sign at the end of every arm, an indoor street lamp in the middle and four
    planters. Only the doors differ."""
    shell_art("Terrazzo", "Paint_Acid", "Ceiling_White")
    for nm in ("NW", "NE", "SW", "SE"):
        gb_box(f"Block_{nm}", "Paint_Acid")
    ranges = {"W": (-4.0, 4.0), "E": (-4.0, 4.0), "N": (-4.0, 4.0), "S": (-4.0, 4.0)}
    skirting("Trim_Green", ranges=ranges)
    casings("Trim_Green")

    def bands(bm, y0, y1, d):
        for nm, x0, x1, z0, z1 in (("NW", -16.0, -4.0, -16.0, -4.0), ("NE", 4.0, 16.0, -16.0, -4.0), ("SW", -16.0, -4.0, 4.0, 16.0), ("SE", 4.0, 16.0, 4.0, 16.0)):
            fx = x1 if x0 < 0 else x0                       # its face toward the north-south arm
            fz = z1 if z0 < 0 else z0                       # and toward the east-west arm
            sx = 1 if x0 < 0 else -1
            sz = 1 if z0 < 0 else -1
            box(bm, fx, fx + sx * d, y0, y1, z0, z1)
            box(bm, x0, x1, y0, y1, fz, fz + sz * d)
        for side in "NSWE":
            for a0, a1 in KT.free_spans(side, -4.0, 4.0, y0, y1):
                wall_box(bm, side, a0, a1, y0, y1, 0.0, d)
    part("decor_Wall_Tile_Band", "Tile_Green", lambda bm: bands(bm, 0.0, 1.3, 0.006))
    part("decor_Tile_Rail", "Trim_Green", lambda bm: bands(bm, 1.3, 1.36, 0.022))
    part("decor_Block_Skirting", "Trim_Green", lambda bm: bands(bm, 0.0, 0.1, 0.016))
    # the skylight: a well with a painted sky, its frame
    part("decor_Skylight_Sky", "Sky_Painted", lambda bm: box(bm, -3.0, 3.0, K.H - 0.002, K.H, -3.0, 3.0))
    part("decor_Skylight_Frame", "Trim_White", lambda bm: (box(bm, -3.15, 3.15, K.H - 0.12, K.H, -3.15, -3.0), box(bm, -3.15, 3.15, K.H - 0.12, K.H, 3.0, 3.15),
                                                           box(bm, -3.15, -3.0, K.H - 0.12, K.H, -3.0, 3.0), box(bm, 3.0, 3.15, K.H - 0.12, K.H, -3.0, 3.0),
                                                           box(bm, -0.04, 0.04, K.H - 0.08, K.H, -3.0, 3.0), box(bm, -3.0, 3.0, K.H - 0.08, K.H, -0.04, 0.04)))
    light("AREA", (0.0, K.H - 0.1, 0.0), 320.0, (0.85, 0.92, 1.0), aim=(0, -1, 0), size=(5.8, 5.8), name="Skylight")
    # the lamp post
    part("Lamp_Post", "Iron", lambda bm: (cyl(bm, (0.0, 0.0, 0.0), (0.0, 0.25, 0.0), 0.15, 0.1, 16), cyl(bm, (0.0, 0.25, 0.0), (0.0, 2.6, 0.0), 0.05, 0.04, 12)))
    part("decor_Lamp_Post_Head", "Iron", lambda bm: (cyl(bm, (0.0, 2.6, 0.0), (0.0, 2.66, 0.0), 0.1, 0.1, 12), cyl(bm, (0.0, 3.05, 0.0), (0.0, 3.12, 0.0), 0.12, 0.04, 12)))
    part("decor_Lamp_Post_Globe", "Lamp_Emit", lambda bm: sphere(bm, (0.0, 2.85, 0.0), 0.2, 16), smooth=True)
    light("POINT", (0.0, 2.85, 0.0), 120.0, WARM, 0.18, name="Street_Lamp")
    for nm in ("NW", "NE", "SW", "SE"):
        b = K.BOX[f"Planter_{nm}"]
        cx, cz = (b["min"][0] + b["max"][0]) / 2, (b["min"][2] + b["max"][2]) / 2
        part(f"Planter_{nm}", "Concrete_Planter", lambda bm, b=b: bx(bm, b))
        plant(f"Planter_{nm}_Plant", cx, cz, 0.85, 1.0, np.random.default_rng(70 + len(nm)), 0.2, solid=False)
    for nm in ("NW", "NE", "SW", "SE"):
        bench(f"Bench_{nm}", K.BOX[f"Bench_{nm}"], "Wood_Oak", "Iron")
    # the same sign over every door, and the same arrows
    for h in K.HOLES:
        side, a = h["side"], h["a"]
        c = on_wall(side, a, h["h"] + 0.45, 0.03)
        picture(f"decor_Sign_{side}", "Signs_Cross", c, KT.SIDE_N[side], 1.4, 0.35, ATLAS_CROSS.uv("wayout"))
        light("AREA", on_wall(side, a, h["h"] + 0.45, 0.25), 3.0, (0.3, 1.0, 0.4), aim=tuple(-v for v in KT.NORMAL[KT.SIDE_N[side]]) if False else KT.NORMAL[KT.SIDE_N[side]],
              size=(1.2, 0.3)) if False else None
    for nm, (x0, x1, z0, z1) in (("NW", (-16.0, -4.0, -16.0, -4.0)), ("NE", (4.0, 16.0, -16.0, -4.0)), ("SW", (-16.0, -4.0, 4.0, 16.0)), ("SE", (4.0, 16.0, 4.0, 16.0))):
        fx = x1 if x0 < 0 else x0
        fz = z1 if z0 < 0 else z0
        sx = 1 if x0 < 0 else -1
        sz = 1 if z0 < 0 else -1
        picture(f"decor_Arrow_{nm}_A", "Signs_Cross", (fx + sx * 0.008, 1.9, (z0 + z1) / 2), "+x" if sx > 0 else "-x", 0.9, 0.3, ATLAS_CROSS.uv("arrow"))
        picture(f"decor_Arrow_{nm}_B", "Signs_Cross", ((x0 + x1) / 2, 1.9, fz + sz * 0.008), "+z" if sz > 0 else "-z", 0.9, 0.3, ATLAS_CROSS.uv("arrow"))
    # troffers down every arm and round the skylight
    bl, bf = bmesh.new(), bmesh.new()
    pts = [(x, 0.0, "x") for x in (-14.0, -11.0, -8.0, -5.5, 5.5, 8.0, 11.0, 14.0)] + [(0.0, z, "z") for z in (-14.0, -11.0, -8.0, -5.5, 5.5, 8.0, 11.0, 14.0)]
    for x, z, al in pts:
        troffer(bl, bf, x, z, 0.6, 1.2, "z" if al == "x" else "x")
        light("AREA", (x, K.H - 0.05, z), 60.0, TUBE, aim=(0, -1, 0), size=(0.6, 1.2) if al == "x" else (1.2, 0.6))
    finish("decor_Troffers_Lit", bl, "Lamp_Emit")
    finish("decor_Troffers_Frames", bf, "Trim_White")


ATLAS_CROSS = Atlas([("wayout", 512, 128, sign("WAY OUT", (0.05, 0.35, 0.12), (0.95, 0.95, 0.9), border=(0.9, 0.9, 0.85))),
                     ("arrow", 384, 128, sign("THIS WAY >", (0.95, 0.95, 0.9), (0.05, 0.3, 0.12)))])

CROSSROADS = dict(
    pages=(2048, 1024),
    grade={"target": 0.95, "shoulder": 1.15},
    mats={"Terrazzo": dict(diff="terrazzo_tiles_diff_1k.jpg", tint=(0.95, 0.95, 0.92), rough=0.3, tile=2.0, group="struct"),
          "Paint_Acid": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.62, 0.90, 0.20), rough=0.35, tile=2.5, group="struct"),
          "Tile_Green": dict(gen="tile", rough=0.25, tile=0.6, group="struct"),
          "Ceiling_White": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.92, 0.92, 0.9), rough=0.95, tile=2.5, group="struct"),
          "Trim_Green": dict(color=(0.08, 0.30, 0.12), rough=0.4, group="struct"),
          "Trim_White": dict(color=(0.92, 0.92, 0.9), rough=0.5),
          "Sky_Painted": dict(gen="sky", rough=1.0, emit_tex=1.4, group=None),
          "Concrete_Planter": dict(diff="concrete_floor_02_diff_1k.jpg", tint=(0.75, 0.75, 0.72), rough=0.8, tile=1.0),
          "Pot_Clay": dict(color=(0.45, 0.45, 0.42), rough=0.8),
          "Plant_Leaf": dict(color=(0.12, 0.34, 0.10), rough=0.6, two_sided=True),
          "Signs_Cross": dict(gen="atlas", rough=0.5)},
    gen={"tile": g_tiles((0.12, 0.42, 0.20), (0.75, 0.78, 0.72), n=4, S=256, seed=71, jitter=0.06),
         "sky": lambda: (lambda rng: np.clip((np.array([0.42, 0.62, 0.92]) * (1 - 0.25 * np.mgrid[0:512, 0:512][0][..., None] / 512)
                                              + np.clip(vnoise(512, 512, rng, 5, 3) - 0.5, 0, 1)[..., None] * 1.6), 0, 1).astype(np.float32))(np.random.default_rng(72)),
         "atlas": ATLAS_CROSS.pixels},
    dress=dress_crossroads,
    shots={"1_arrival": ((-14.0, 1.55, 0.0), (14.0, 1.4, 0.0), 62.0),
           "2_wide": ((3.6, 2.4, 3.6), (-14.0, 1.0, -0.8), 80.0),
           "3_detail": ((0.0, 1.55, 5.0), (0.0, 1.8, -16.0), 62.0)},
)


# ================================================================ 27. rdwe_changing_rooms
def dress_changing_rooms():
    """Wet changing rooms for a pool that is not there: white tiles to the ceiling, a small aqua mosaic floor that shines with water, blue
    lockers, slatted benches with damp towels, three showers (one still running), basins and a mirror, a TO POOL sign that points at a tiled
    wall, and locker 13, big enough to walk into."""
    shell("Mosaic", "Tile_White", "Ceiling_White", skirt=None, casing="Trim_Steel")
    for n in ("Lockers", "Lockers_E1", "Lockers_E2"):
        b = K.BOX[n]
        mn, mx = b["min"], b["max"]
        face = "N" if n == "Lockers" else "W"
        part(n, "Locker_Blue", lambda bm, mn=mn, mx=mx: (box(bm, mn[0], mx[0], 0.1, mx[1], mn[2], mx[2]),
                                                         box(bm, mn[0] + 0.02, mx[0] - 0.02, 0.0, 0.1, mn[2] + 0.02, mx[2] - 0.02)))

        def doors(bm, mn=mn, mx=mx, face=face):
            if face == "N":
                k = int(round((mx[0] - mn[0]) / 0.4))
                for i in range(k):
                    a0 = mn[0] + i * 0.4 + 0.012
                    for (y0, y1) in ((0.12, 0.98), (1.02, 1.96)):
                        box(bm, a0, a0 + 0.376, y0, y1, mn[2] - 0.006, mn[2])
                        for v in range(4):
                            box(bm, a0 + 0.1, a0 + 0.276, y1 - 0.12 - v * 0.03, y1 - 0.11 - v * 0.03, mn[2] - 0.009, mn[2] - 0.006)
            else:
                k = int(round((mx[2] - mn[2]) / 0.4))
                step = (mx[2] - mn[2]) / k
                for i in range(k):
                    a0 = mn[2] + i * step + 0.012
                    for (y0, y1) in ((0.12, 0.98), (1.02, 1.96)):
                        box(bm, mn[0] - 0.006, mn[0], y0, y1, a0, a0 + step - 0.024)
                        for v in range(4):
                            box(bm, mn[0] - 0.009, mn[0] - 0.006, y1 - 0.12 - v * 0.03, y1 - 0.11 - v * 0.03, a0 + 0.1, a0 + step - 0.124)
        part(n + "_Doors", "Locker_Door", doors)
    for n in ("Bench", "Bench_2"):
        bench(n, K.BOX[n], "Wood_Oak", "Steel")
    for k in range(1, 4):
        b = K.BOX[f"Shower_Wall_{k}"]
        part(f"Shower_Wall_{k}", "Tile_White", lambda bm, b=b: bx(bm, b), tile=0.6)
    for k, z in enumerate((-3.25, -1.75), 1):
        part(f"decor_Shower_{k}", "Chrome", lambda bm, z=z: (cyl(bm, (K.X0, 2.05, z), (K.X0 + 0.25, 2.1, z), 0.015, 0.015, 8),
                                                            cyl(bm, (K.X0 + 0.25, 2.1, z), (K.X0 + 0.28, 2.02, z), 0.06, 0.04, 14),
                                                            cyl(bm, (K.X0, 1.05, z - 0.12), (K.X0 + 0.07, 1.05, z - 0.12), 0.03, 0.03, 10),
                                                            cyl(bm, (K.X0, 1.05, z + 0.12), (K.X0 + 0.07, 1.05, z + 0.12), 0.03, 0.03, 10)))
        part(f"decor_Shower_Drain_{k}", "Chrome", lambda bm, z=z: cyl(bm, (K.X0 + 0.6, 0.0, z), (K.X0 + 0.6, 0.003, z), 0.06, 0.06, 12))
    part("decor_Shower_Water", "Water_Fall", lambda bm: [cyl(bm, (K.X0 + 0.28 + 0.01 * i, 2.0, -1.75 + 0.012 * (i - 2)),
                                                             (K.X0 + 0.32 + 0.03 * i, 0.0, -1.75 + 0.03 * (i - 2)), 0.004, 0.004, 4) for i in range(5)])
    sk = K.BOX["Sinks"]
    part("Sinks", "Tile_White", lambda bm: bx(bm, sk), tile=0.6)
    part("decor_Basins", "Porcelain", lambda bm: [cyl(bm, (6.65, 0.86, z), (6.65, 0.92, z), 0.2, 0.22, 18) for z in (-4.2, -3.6, -3.0)])
    part("decor_Taps", "Chrome", lambda bm: [cyl(bm, (6.95, 0.86, z), (6.88, 1.05, z), 0.012, 0.012, 6) for z in (-4.2, -3.6, -3.0)])
    part("decor_Mirror", "Mirror", lambda bm: wall_box(bm, "E", -4.5, -2.7, 1.2, 2.1, 0.0, 0.01))
    tb = K.BOX["Towel_Bin"]
    part("Towel_Bin", "Plastic_Grey", lambda bm: cyl(bm, ((tb["min"][0] + tb["max"][0]) / 2, 0.0, (tb["min"][2] + tb["max"][2]) / 2),
                                                     ((tb["min"][0] + tb["max"][0]) / 2, 0.8, (tb["min"][2] + tb["max"][2]) / 2), 0.25, 0.28, 18, cap=False))
    # towels: damp, on the benches, on hooks, in the bin
    P = Painter()
    rng = np.random.default_rng(80)
    for x in (-2.4, -0.6, 1.8):
        P.add("towel" if x < 1 else "towel_blue", box, x, x + 0.5, 0.45, 0.48, -0.18, 0.18)
        P.add("towel" if x < 1 else "towel_blue", box, x + 0.02, x + 0.48, 0.18, 0.45, 0.17, 0.2)
    for i in range(8):
        a = -6.5 + i * 0.6
        P.add("chrome", box, a, a + 0.04, 2.1, 2.14, K.Z0 + 0.0, K.Z0 + 0.06)
        if rng.random() < 0.6:
            P.add(["towel", "towel_blue", "towel"][i % 3], box, a - 0.12, a + 0.16, 1.45, 2.1, K.Z0 + 0.04, K.Z0 + 0.08)
    P.add("towel_blue", sphere, ((tb["min"][0] + tb["max"][0]) / 2, 0.78, (tb["min"][2] + tb["max"][2]) / 2), 0.24, 10, 0.4)
    P.done("decor_Towels")
    # the puddles (the greybox's water zone): flat, glossy
    part("decor_Puddles", "Water_Puddle", lambda bm: [disc(bm, (x, 0.003, z), "y", r, 18) for x, z, r in
                                                      ((-5.4, -4.2, 0.6), (-4.6, -2.5, 0.45), (-1.0, -3.6, 0.8), (2.6, -4.3, 0.5), (4.8, -2.8, 0.65))], recalc=False)
    picture("decor_Sign_Pool", "Signs_Changing", on_wall("N", 1.0, 2.35, 0.004), "+z", 1.4, 0.35, ATLAS_CHANGE.uv("pool"))
    picture("decor_Sign_Run", "Signs_Changing", on_wall("W", 2.5, 2.2, 0.004), "+x", 1.0, 0.3, ATLAS_CHANGE.uv("run"))
    ceiling_troffers([-4.0, 0.0, 4.0], [-2.5, 2.0], along="x", watts=50.0, color=TUBE, lit=lambda x, z: not (x < -3 and z > 0))
    light("POINT", (-6.0, 2.4, -1.75), 12.0, TUBE, 0.1, name="Shower_Light")


ATLAS_CHANGE = Atlas([("pool", 512, 128, sign("< TO POOL", (0.1, 0.45, 0.62), (0.95, 0.97, 0.98), border=(0.9, 0.9, 0.9))),
                      ("run", 512, 128, sign("NO RUNNING", (0.95, 0.95, 0.93), (0.75, 0.08, 0.06), border=(0.75, 0.08, 0.06)))])

CHANGING_ROOMS = dict(
    pages=(2048, 1024),
    grade={"target": 0.95, "shoulder": 1.15},
    mats={"Mosaic": dict(gen="mosaic", rough=0.15, tile=0.8, group="struct"),
          "Tile_White": dict(gen="tile", rough=0.2, tile=0.6, group="struct"),
          "Ceiling_White": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.92, 0.94, 0.94), rough=0.95, tile=2.5, group="struct"),
          "Trim_Steel": dict(color=(0.62, 0.64, 0.66), rough=0.35, metal=0.6, group="struct"),
          "Trim_White": dict(color=(0.92, 0.92, 0.9), rough=0.5),
          "Locker_Blue": dict(color=(0.18, 0.36, 0.60), rough=0.4, metal=0.3),
          "Locker_Door": dict(color=(0.22, 0.42, 0.68), rough=0.35, metal=0.3),
          "Porcelain": dict(color=(0.94, 0.94, 0.93), rough=0.15),
          "Plastic_Grey": dict(color=(0.45, 0.47, 0.5), rough=0.5, two_sided=True),
          "Water_Fall": dict(color=(0.8, 0.9, 1.0), rough=0.05, alpha=0.4, group=None),
          "Water_Puddle": dict(color=(0.30, 0.42, 0.48), rough=0.02),
          "Signs_Changing": dict(gen="atlas", rough=0.5)},
    gen={"mosaic": g_tiles((0.80, 0.90, 0.92), (0.55, 0.62, 0.64), n=16, S=512, accent=((0.25, 0.62, 0.70), 0.12), seed=81),
         "tile": g_tiles((0.90, 0.91, 0.90), (0.66, 0.68, 0.68), n=4, S=256, seed=82, jitter=0.03),
         "atlas": ATLAS_CHANGE.pixels},
    dress=dress_changing_rooms,
    shots={"1_arrival": ((-4.0, 1.55, -3.4), (2.0, 1.2, 4.0), 74.0),
           "2_wide": ((6.3, 2.3, -4.4), (-4.0, 0.8, 3.0), 80.0),
           "3_detail": ((-3.0, 1.5, 0.8), (-6.9, 1.2, -2.2), 66.0)},
)


def ring_face(bm, c, side, rx0, rx1, ry0, ry1, r, d, seg=40):
    """On wall `side`: the rectangle [rx0, rx1] x [ry0, ry1] (along the wall, up) minus a circle of radius r round c = (a, y), d proud of the
    wall: its front face, its outer edges and the circle's tunnel back to the wall."""
    a0, y0 = c
    outer, inner = [], []
    for i in range(seg):
        th = 2 * math.pi * i / seg
        ca, sa = math.cos(th), math.sin(th)
        ts = []
        if ca > 1e-9:
            ts.append((rx1 - a0) / ca)
        if ca < -1e-9:
            ts.append((rx0 - a0) / ca)
        if sa > 1e-9:
            ts.append((ry1 - y0) / sa)
        if sa < -1e-9:
            ts.append((ry0 - y0) / sa)
        t = min(ts)
        outer.append(on_wall(side, a0 + t * ca, y0 + t * sa, d))
        inner.append(on_wall(side, a0 + r * ca, y0 + r * sa, d))
    for i in range(seg):
        j = (i + 1) % seg
        quad(bm, outer[i], outer[j], inner[j], inner[i])
        ib, jb = list(inner[i]), list(inner[j])
        ia, ja = on_wall(side, a0 + r * math.cos(2 * math.pi * i / seg), y0 + r * math.sin(2 * math.pi * i / seg), -0.2), \
            on_wall(side, a0 + r * math.cos(2 * math.pi * j / seg), y0 + r * math.sin(2 * math.pi * j / seg), -0.2)
        quad(bm, tuple(ib), tuple(jb), ja, ia)
    wall_box(bm, side, rx0, rx1, ry1 - 0.001, ry1, 0.0, d)
    wall_box(bm, side, rx0, rx0 + 0.001, ry0, ry1, 0.0, d)
    wall_box(bm, side, rx1 - 0.001, rx1, ry0, ry1, 0.0, d)


def porthole(bm_ring, bm_glass, c, normal_side, r, d):
    """A front-loader's round door on a machine front: a chrome ring and a dark glass disc."""
    a, y = c
    p = on_wall(normal_side, a, y, d) if isinstance(normal_side, str) else None
    return p


def machine_door(P_ring, P_glass, centre, n, r):
    """A washer's door at `centre` facing game direction n (a unit axis vector): chrome ring into P_ring, dark glass into P_glass (bmeshes)."""
    ax = "x" if abs(n[0]) > 0.5 else "z"
    torus(P_ring, centre, ax, r, r * 0.16, 28, 6)
    disc(P_glass, tuple(centre[i] + n[i] * 0.01 for i in range(3)), ax, r * 0.88, 28, 1 if (n[0] + n[2]) > 0 else -1)


# ================================================================ 28. rdwe_laundromat
def dress_laundromat():
    """A late laundromat in cyan and white: a checker floor, white tile to 1.3 m, a row of front-loaders, a bank of dryers, orange chairs on a
    beam, a folding table with folded washing, a wire cart, the change and soap machines, the notices; and on the north wall a washer the size
    of a car, MAXI-WASH, whose round glass door is the way on. Its drum, behind the glass, is its own object (the page turns it); not baked."""
    shell("Vinyl_Checker", "Paint_Cyan", "Ceiling_Tiles", skirt="Trim_Steel", casing="Trim_Steel", skip_casings=("drum",),
          dado=("Tile_White", 1.3, "Trim_Steel"))
    rl, gl = bmesh.new(), bmesh.new()
    for k in range(1, 7):
        b = K.BOX[f"Washer_{k}"]
        x0, x1, z0, z1, h = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]
        part(f"Washer_{k}", "Washer_Enamel", lambda bm, b=b: (box(bm, b["min"][0], b["max"][0], 0.04, b["max"][1], b["min"][2], b["max"][2]),
                                                              box(bm, b["min"][0] + 0.03, b["max"][0] - 0.03, 0.0, 0.04, b["min"][2] + 0.03, b["max"][2] - 0.03)))
        part(f"decor_Washer_{k}_Panel", "Panel_Grey", lambda bm, x0=x0, x1=x1, z1=z1, h=h: box(bm, x0 + 0.02, x1 - 0.02, h - 0.16, h - 0.02, z1, z1 + 0.012))
        machine_door(rl, gl, ((x0 + x1) / 2, 0.52, z1 + 0.012), (0, 0, 1), 0.27)
    # the dryers: four wide, two high, on the south wall
    db = K.BOX["Dryers"]
    part("Dryers", "Washer_Enamel", lambda bm: bx(bm, db))
    for i in range(4):
        for j in range(2):
            x = db["min"][0] + (db["max"][0] - db["min"][0]) * (i + 0.5) / 4
            y = 0.5 + j * 1.0
            machine_door(rl, gl, (x, y, db["min"][2] - 0.012), (0, 0, -1), 0.3)
    part("decor_Dryer_Seams", "Panel_Grey", lambda bm: [box(bm, db["min"][0], db["max"][0], 0.99, 1.01, db["min"][2] - 0.008, db["min"][2])] +
         [box(bm, db["min"][0] + (db["max"][0] - db["min"][0]) * i / 4 - 0.01, db["min"][0] + (db["max"][0] - db["min"][0]) * i / 4 + 0.01, 0.0, 2.0,
              db["min"][2] - 0.008, db["min"][2]) for i in range(1, 4)])
    # the giant: MAXI-WASH, the north wall's facade round the drum door
    h = next(hh for hh in K.HOLES if hh["name"] == "DoorLeaf_drum")
    dc = (h["a"], h["y"] + (h["h"] - 0.04) / 2)
    R = 0.70
    gw = K.BOX["decor_Giant_Washer"]
    part("decor_Giant_Facade", "Washer_Enamel", lambda bm: ring_face(bm, dc, "N", gw["min"][0], gw["max"][0], 0.0, 3.0, R, 0.08))
    part("decor_Giant_Top", "Panel_Grey", lambda bm: (wall_box(bm, "N", gw["min"][0] + 0.1, gw["max"][0] - 0.1, 2.15, 2.85, 0.08, 0.1),))
    part("decor_Giant_Dial", "Chrome", lambda bm: cyl(bm, on_wall("N", gw["max"][0] - 0.7, 2.5, 0.1), on_wall("N", gw["max"][0] - 0.7, 2.5, 0.2), 0.22, 0.2, 24))
    part("decor_Giant_Drawer", "Panel_Grey", lambda bm: wall_box(bm, "N", gw["min"][0] + 0.25, gw["min"][0] + 1.2, 2.25, 2.75, 0.1, 0.16))
    picture("decor_Giant_Label", "Signs_Laundry", on_wall("N", (gw["min"][0] + gw["max"][0]) / 2 - 0.2, 2.5, 0.102), "+z", 1.2, 0.3, ATLAS_LAUNDRY.uv("maxi"))
    for sg in (-1, 1):
        part(f"decor_Giant_Foot_{sg}", "Rubber", lambda bm, sg=sg: wall_box(bm, "N", dc[0] + sg * 1.4 - 0.2, dc[0] + sg * 1.4 + 0.2, 0.0, 0.05, 0.0, 0.12))
    # the drum behind the glass: steel, perforated, three paddles; the page turns it about its axis
    pivot = on_wall("N", dc[0], dc[1], -0.05)

    def drum(bm):
        cyl(bm, on_wall("N", dc[0], dc[1], -0.02), on_wall("N", dc[0], dc[1], -0.34), R - 0.03, R - 0.03, 32, cap=False)
        disc(bm, on_wall("N", dc[0], dc[1], -0.34), "z", R - 0.03, 32, 1)
        for k in range(3):
            a = 2 * math.pi * k / 3
            ux, uy = math.cos(a), math.sin(a)
            p0 = on_wall("N", dc[0] + ux * (R - 0.2), dc[1] + uy * (R - 0.2), -0.04)
            p1 = on_wall("N", dc[0] + ux * (R - 0.04), dc[1] + uy * (R - 0.04), -0.32)
            cube(bm, [min(p0[i], p1[i]) - (0.03 if i != 2 else 0) for i in range(3)], [max(p0[i], p1[i]) + (0.03 if i != 2 else 0) for i in range(3)])
    moving_part("Drum", "Drum_Steel", drum, pivot)
    moving_part("decor_Drum_Clothes", "Clothes_Move", lambda bm: sphere(bm, on_wall("N", dc[0] + 0.1, dc[1] - 0.4, -0.2), 0.32, 14, 0.5), pivot, smooth=True)
    K.spec["moving"] = {"Drum": "turns about its axis (the round door's centre); a turn each time you look away",
                        "decor_Drum_Clothes": "the washing in the drum: turns with it"}
    finish("decor_Door_Rings", rl, "Chrome")
    finish("decor_Door_Glass", gl, "Glass_Dark", recalc=False)
    # the folding table and the washing on it; the chairs; the cart
    table("Folding_Table", K.BOX["Folding_Table"], "Laminate_White", "Chrome", t=0.035, inset=0.06)
    P = Painter()
    rng = np.random.default_rng(90)
    ft = K.BOX["Folding_Table"]
    for i in range(6):
        x = -1.8 + i * 0.6 + rng.uniform(-0.05, 0.05)
        hh = 0.03 + 0.03 * (i % 3)
        P.add(["towel", "denim", "pink", "white", "towel_blue", "yellow"][i], box, x, x + 0.4, ft["max"][1], ft["max"][1] + hh, 0.8, 1.2)
    P.add("plastic_blue", box, 1.3, 1.85, ft["max"][1], ft["max"][1] + 0.28, 1.15, 1.5)
    P.done("decor_Washing")
    ch = K.BOX["Chairs"]
    part("Chairs", "Plastic_Orange", lambda bm: [(box(bm, ch["min"][0] + i * 0.75 + 0.04, ch["min"][0] + (i + 1) * 0.75 - 0.04, 0.40, 0.45, ch["min"][2], ch["max"][2]),
                                                  box(bm, ch["min"][0] + i * 0.75 + 0.04, ch["min"][0] + (i + 1) * 0.75 - 0.04, 0.45, 0.85, ch["max"][2] - 0.05, ch["max"][2]))
                                                 for i in range(4)])
    part("Chairs_Frame", "Chrome", lambda bm: (box(bm, ch["min"][0], ch["max"][0], 0.34, 0.4, ch["min"][2] + 0.2, ch["min"][2] + 0.28),
                                               [box(bm, x - 0.025, x + 0.025, 0.0, 0.34, ch["min"][2] + 0.2, ch["min"][2] + 0.28) for x in (ch["min"][0] + 0.2, ch["max"][0] - 0.2)]))
    lc = K.BOX["Laundry_Cart"]
    part("Laundry_Cart", "Chrome", lambda bm: (wire_box(bm, lc["min"][0], lc["max"][0], 0.45, 0.9, lc["min"][2], lc["max"][2], 0.01),
                                               [cyl(bm, (x, 0.08, z), (x, 0.45, z), 0.012, 0.012, 6) for x in (lc["min"][0] + 0.03, lc["max"][0] - 0.03)
                                                for z in (lc["min"][2] + 0.03, lc["max"][2] - 0.03)],
                                               [sphere(bm, (x, 0.05, z), 0.05, 8) for x in (lc["min"][0] + 0.03, lc["max"][0] - 0.03) for z in (lc["min"][2] + 0.03, lc["max"][2] - 0.03)]))
    part("decor_Cart_Washing", "Clothes", lambda bm: sphere(bm, ((lc["min"][0] + lc["max"][0]) / 2, 0.75, (lc["min"][2] + lc["max"][2]) / 2), 0.3, 12, 0.6), smooth=True)
    for n, m, key in (("Change_Machine", "Steel", "change"), ("Soap_Machine", "Paint_Red", "soap")):
        b = K.BOX[n]
        part(n, m, lambda bm, b=b: bx(bm, b))
        picture(f"decor_{n}_Face", "Signs_Laundry", ((b["max"][0] + 0.004), 1.0, (b["min"][2] + b["max"][2]) / 2), "+x", 0.6, 0.7, ATLAS_LAUNDRY.uv(key))
    picture("decor_Prices", "Signs_Laundry", on_wall("S", 0.8, 2.1, 0.004), "-z", 1.6, 0.5, ATLAS_LAUNDRY.uv("prices"))
    picture("decor_Notice", "Signs_Laundry", on_wall("E", -1.0, 1.7, 0.004), "-x", 0.9, 0.6, ATLAS_LAUNDRY.uv("notice"))
    picture("decor_Open", "Signs_Laundry", on_wall("W", -2.6, 2.3, 0.004), "+x", 0.9, 0.3, ATLAS_LAUNDRY.uv("open"))
    ceiling_troffers([-6.0, -2.0, 2.0, 6.0], [-1.6, 1.8], along="x", watts=55.0, color=TUBE)


ATLAS_LAUNDRY = Atlas([("maxi", 512, 128, sign("MAXI-WASH  80 KG", (0.85, 0.86, 0.85), (0.1, 0.25, 0.55))),
                       ("prices", 512, 160, sign(["WASH  4.00", "DRY   2.00"], (0.95, 0.95, 0.9), (0.1, 0.1, 0.12), border=(0.1, 0.4, 0.6))),
                       ("notice", 384, 256, lambda h, w: text_lines(["NOT RESPONSIBLE", "FOR LOST ITEMS", "", "DO NOT LEAVE", "WASHING", "UNATTENDED"], h, w,
                                                                    (0.92, 0.9, 0.78), (0.15, 0.12, 0.1), rng=np.random.default_rng(5))),
                       ("open", 384, 128, sign("OPEN 24 HOURS", (0.1, 0.1, 0.12), (1.0, 0.4, 0.6))),
                       ("change", 256, 256, sign(["CHANGE", "", "COINS"], (0.35, 0.36, 0.38), (0.9, 0.85, 0.3))),
                       ("soap", 256, 256, sign(["SOAP", "SOFTENER", "BLEACH"], (0.72, 0.06, 0.05), (0.98, 0.95, 0.9)))])

LAUNDROMAT = dict(
    pages=(2048, 1024),
    grade={"target": 0.95, "shoulder": 1.15},
    mats={"Vinyl_Checker": dict(gen="checker", rough=0.4, tile=0.6, group="struct"),
          "Paint_Cyan": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.30, 0.78, 0.86), rough=0.6, tile=2.5, group="struct"),
          "Tile_White": dict(gen="tile", rough=0.25, tile=0.6, group="struct"),
          "Ceiling_Tiles": dict(gen="ceiltile", rough=0.9, tile=1.2, group="struct"),
          "Trim_Steel": dict(color=(0.62, 0.64, 0.66), rough=0.35, metal=0.6, group="struct"),
          "Trim_White": dict(color=(0.92, 0.92, 0.9), rough=0.5),
          "Washer_Enamel": dict(color=(0.88, 0.89, 0.88), rough=0.3),
          "Panel_Grey": dict(color=(0.45, 0.47, 0.5), rough=0.4),
          "Glass_Dark": dict(color=(0.10, 0.13, 0.15), rough=0.05),
          "Drum_Steel": dict(gen="perf", rough=0.3, metal=0.7, tile=0.15, group=None),
          "Clothes_Move": dict(color=(0.55, 0.30, 0.55), rough=1.0, group=None),
          "Clothes": dict(color=(0.30, 0.42, 0.62), rough=1.0),
          "Laminate_White": dict(color=(0.90, 0.90, 0.88), rough=0.35),
          "Plastic_Orange": dict(color=(0.92, 0.42, 0.08), rough=0.4),
          "Paint_Red": dict(color=(0.72, 0.06, 0.05), rough=0.4),
          "Signs_Laundry": dict(gen="atlas", rough=0.5)},
    gen={"checker": g_checker((0.88, 0.88, 0.86), (0.12, 0.45, 0.50), n=2, S=256, seed=91),
         "tile": g_tiles((0.90, 0.91, 0.90), (0.66, 0.68, 0.68), n=4, S=256, seed=92, jitter=0.03),
         "ceiltile": g_tiles((0.86, 0.86, 0.84), (0.62, 0.62, 0.6), n=2, S=256, seed=93, jitter=0.02),
         "perf": lambda: (lambda yy, xx: np.where((((yy % 32) - 16) ** 2 + ((xx % 32) - 16) ** 2 < 36)[..., None], np.array([0.08, 0.08, 0.09]),
                                                  np.array([0.72, 0.74, 0.76])).astype(np.float32))(*np.mgrid[0:256, 0:256]),
         "atlas": ATLAS_LAUNDRY.pixels},
    dress=dress_laundromat,
    shots={"1_arrival": ((-6.6, 1.55, 0.0), (5.0, 1.1, -3.6), 74.0),
           "2_wide": ((7.4, 2.4, 3.4), (-4.0, 0.8, -2.0), 80.0),
           "3_detail": ((4.0, 1.4, -0.2), (4.0, 1.2, -4.0), 66.0)},
)


# ================================================================ 29. rdwe_motel_room
def dress_motel_room():
    """A roadside motel room, 1974: wood panelling behind the bed, peach walls, an orange shag carpet, a popcorn ceiling. The bed under a
    seascape, two nightstands with lamps and a phone, a dresser with the TV (its screen is the page's: this room from the corner, a second late),
    an armchair, a table by the curtained window with the VACANCY sign's red through it, a luggage rack with a case."""
    shell("Carpet_Shag", "Plaster_Peach", "Ceiling_Popcorn", skirt="Trim_Wood", casing="Trim_Wood")
    wall_band("Panel_Wood", 0.0, K.H, name="decor_Wall_Panelling", sides="W", d=0.012)
    bb = K.BOX["Bed"]
    part("Bed", "Wood_Dark", lambda bm: box(bm, bb["min"][0] + 0.08, bb["max"][0], 0.0, 0.3, bb["min"][2], bb["max"][2]))
    part("Bed_Mattress", "Bedspread", lambda bm: (box(bm, bb["min"][0] + 0.08, bb["max"][0] + 0.02, 0.3, 0.55, bb["min"][2] - 0.02, bb["max"][2] + 0.02),
                                                  box(bm, bb["max"][0] - 0.02, bb["max"][0] + 0.03, 0.08, 0.55, bb["min"][2] - 0.02, bb["max"][2] + 0.02)))
    P = Painter()
    for z0 in (0.1, 0.85):
        P.add("cream", sphere, (bb["min"][0] + 0.35, 0.62, z0 + 0.33), 0.32, 12, 0.3, sx=0.6)
    P.done("decor_Pillows")
    part("Bed_Headboard", "Wood_Dark", lambda bm: box(bm, bb["min"][0], bb["min"][0] + 0.06, 0.0, 1.15, bb["min"][2] - 0.1, bb["max"][2] + 0.1))
    frame_picture("Seascape", "W", 0.8, 1.75, 1.2, 0.6, "Paintings", uv=painting_uv(2), frame_mat="Frame_Gilt")
    for n in ("Nightstand_N", "Nightstand_S"):
        b = K.BOX[n]
        cabinet(n, b, "Wood_Dark", "Wood_Dark", doors=1, face="E", plinth=0.05)
        cx, cz, ty = (b["min"][0] + b["max"][0]) / 2, (b["min"][2] + b["max"][2]) / 2, b["max"][1]
        part(f"decor_{n}_Lamp", "Ceramic_Orange", lambda bm, cx=cx, cz=cz, ty=ty: cyl(bm, (cx, ty, cz), (cx, ty + 0.3, cz), 0.07, 0.1, 14))
        part(f"decor_{n}_Shade", "Shade_Linen", lambda bm, cx=cx, cz=cz, ty=ty: cyl(bm, (cx, ty + 0.28, cz), (cx, ty + 0.52, cz), 0.19, 0.14, 18, cap=False))
        part(f"decor_{n}_Bulb", "Lamp_Emit", lambda bm, cx=cx, cz=cz, ty=ty: sphere(bm, (cx, ty + 0.36, cz), 0.04, 8))
        light("POINT", (cx, ty + 0.38, cz), 30.0, WARM, 0.06)
    nb = K.BOX["Nightstand_N"]
    P = Painter()
    P.add("beige", box, nb["min"][0] + 0.04, nb["min"][0] + 0.24, nb["max"][1], nb["max"][1] + 0.08, nb["min"][2] + 0.05, nb["min"][2] + 0.2)
    P.add("maroon", box, nb["min"][0] + 0.05, nb["min"][0] + 0.2, nb["max"][1], nb["max"][1] + 0.03, nb["max"][2] - 0.2, nb["max"][2] - 0.04)
    P.done("decor_Phone_Bible")
    tv = K.BOX["TV_Stand"]
    cabinet("TV_Stand", tv, "Wood_Dark", "Wood_Dark", doors=3, face="W", plinth=0.06)
    ty = tv["max"][1]
    tz = (tv["min"][2] + tv["max"][2]) / 2
    part("decor_TV", "Plastic_Brown", lambda bm: (box(bm, 2.5, 2.95, ty, ty + 0.5, tz - 0.32, tz + 0.32), box(bm, 2.6, 2.9, ty + 0.5, ty + 0.53, tz - 0.05, tz + 0.05)))
    picture("decor_TV_Screen", "Screen_TV", (2.496, ty + 0.27, tz - 0.04), "-x", 0.48, 0.36, (0, 0, 1, 1))
    part("decor_TV_Knobs", "Chrome", lambda bm: [cyl(bm, (2.5, ty + 0.36 - k * 0.1, tz + 0.25), (2.48, ty + 0.36 - k * 0.1, tz + 0.25), 0.02, 0.02, 10) for k in range(2)])
    light("AREA", (2.42, ty + 0.27, tz - 0.04), 3.0, (0.55, 0.7, 1.0), aim=(-1, 0, 0), size=(0.36, 0.48), name="TV_Glow")
    armchair("Armchair", K.BOX["Armchair"], "Velvet_Mustard", "Wood_Dark", back="S")
    table("Table", K.BOX["Table"], "Laminate_Wood", "Chrome", t=0.03, r=0.015, inset=0.06)
    chair("Chair", K.BOX["Chair"], "Velvet_Mustard", "Chrome", back="W")
    lr = K.BOX["Luggage_Rack"]
    part("Luggage_Rack", "Chrome", lambda bm: ([cyl(bm, (x, 0.0, z), (x, 0.45, z), 0.012, 0.012, 6) for x in (lr["min"][0] + 0.03, lr["max"][0] - 0.03)
                                                for z in (lr["min"][2] + 0.03, lr["max"][2] - 0.03)],
                                               [box(bm, lr["min"][0], lr["max"][0], 0.44, 0.46, z - 0.02, z + 0.02) for z in (lr["min"][2] + 0.1, lr["max"][2] - 0.1)]))
    part("decor_Suitcase", "Leather_Brown", lambda bm: box(bm, lr["min"][0] + 0.1, lr["max"][0] - 0.1, 0.46, 0.68, lr["min"][2] + 0.02, lr["max"][2] - 0.02))
    # the window on the south wall: curtains drawn, the red of the sign in the gap
    part("decor_Window_Glow", "Neon_Red", lambda bm: wall_box(bm, "S", 1.85, 2.05, 0.9, 2.2, 0.0, 0.004))
    for k, (a0, a1) in enumerate(((0.2, 1.9), (2.0, 2.9)), 1):
        part(f"decor_Curtain_{k}", "Curtain_Orange", lambda bm, a0=a0, a1=a1: [wall_box(bm, "S", a0 + (a1 - a0) * i / 6, a0 + (a1 - a0) * (i + 1) / 6, 0.7, 2.45,
                                                                                    0.04 + 0.04 * (i % 2), 0.08 + 0.04 * (i % 2)) for i in range(6)])
    part("decor_Curtain_Rail", "Chrome", lambda bm: cyl(bm, on_wall("S", 0.1, 2.48, 0.08), on_wall("S", 2.95, 2.48, 0.08), 0.012, 0.012, 8))
    light("AREA", on_wall("S", 1.95, 1.5, 0.05), 14.0, (1.0, 0.12, 0.08), aim=(0, 0, -1), size=(0.2, 1.3), name="Vacancy_Glow")
    part("decor_AC", "Plastic_Beige", lambda bm: wall_box(bm, "E", 3.0, 4.0, 1.95, 2.35, 0.0, 0.25))
    part("decor_Smoke_Detector", "Plastic_Beige", lambda bm: cyl(bm, (2.75, K.H, -4.75), (2.75, K.H - 0.04, -4.75), 0.07, 0.07, 14))
    part("decor_Ceiling_Dome", "Shade_Glass", lambda bm: sphere(bm, (0.0, K.H - 0.02, 0.0), 0.22, 16, 0.35))
    light("POINT", (0.0, K.H - 0.12, 0.0), 45.0, WARM, 0.1, name="Ceiling_Light")
    rug("Bath_Mat", 1.1, 1.9, -4.9, -4.5, "Towel_White")


MOTEL_ROOM = dict(
    pages=(2048, 1024),
    grade={"target": 0.9, "shoulder": 1.15},
    mats={"Carpet_Shag": dict(gen="shag", rough=1.0, tile=1.2, group="struct"),
          "Plaster_Peach": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.98, 0.72, 0.56), rough=0.9, tile=2.5, group="struct"),
          "Panel_Wood": dict(diff="dark_wood_diff_1k.jpg", tint=(1.0, 0.78, 0.55), rough=0.5, tile=1.2, group="struct"),
          "Ceiling_Popcorn": dict(diff="concrete_floor_02_diff_1k.jpg", tint=(1.05, 1.0, 0.92), rough=1.0, tile=0.8, group="struct"),
          "Trim_Wood": dict(diff="dark_wood_diff_1k.jpg", tint=(0.8, 0.6, 0.45), rough=0.5, tile=0.8, group="struct"),
          "Bedspread": dict(gen="floral", rough=1.0, tile=1.0),
          "Ceramic_Orange": dict(color=(0.85, 0.40, 0.10), rough=0.2),
          "Shade_Linen": dict(diff="rough_linen_diff_512.jpg", tint=(0.95, 0.86, 0.65), rough=1.0, two_sided=True, tile=0.4),
          "Plastic_Brown": dict(color=(0.22, 0.14, 0.08), rough=0.4),
          "Screen_TV": dict(gen="tv", rough=0.2, emit_tex=1.4, group=None),
          "Velvet_Mustard": dict(diff="rough_linen_diff_512.jpg", tint=(0.80, 0.58, 0.12), rough=1.0, tile=0.5),
          "Laminate_Wood": dict(diff="dark_wood_diff_1k.jpg", tint=(1.0, 0.85, 0.65), rough=0.3, tile=0.8),
          "Leather_Brown": dict(color=(0.30, 0.16, 0.08), rough=0.6),
          "Neon_Red": dict(color=(1.0, 0.2, 0.15), emit=((1.0, 0.1, 0.06), 4.0), group=None),
          "Curtain_Orange": dict(diff="rough_linen_diff_512.jpg", tint=(0.85, 0.38, 0.10), rough=1.0, tile=0.5, two_sided=True),
          "Plastic_Beige": dict(color=(0.80, 0.76, 0.66), rough=0.5),
          "Shade_Glass": dict(color=(0.95, 0.92, 0.85), rough=0.3, emit=((1.0, 0.9, 0.75), 2.0), group=None),
          "Towel_White": dict(diff="rough_linen_diff_512.jpg", tint=(0.95, 0.94, 0.9), rough=1.0, tile=0.3),
          "Paintings": dict(gen="paintings", rough=0.6),
          "Frame_Gilt": dict(color=(0.66, 0.50, 0.22), rough=0.35, metal=0.8)},
    gen={"shag": g_carpet((0.55, 0.25, 0.06), (0.72, 0.40, 0.10), seed=101),
         "floral": lambda: (lambda rng, yy, xx: np.clip(np.where(((np.sin(xx * 0.1) * np.cos(yy * 0.1) + 0.3 * np.sin((xx + yy) * 0.05)) > 0.45)[..., None],
                                                                np.array([0.85, 0.55, 0.15]), np.array([0.42, 0.22, 0.10]))
                                                        * (0.85 + 0.25 * vnoise(256, 256, rng, 4, 4)[..., None]), 0, 1).astype(np.float32))(
             np.random.default_rng(102), *np.mgrid[0:256, 0:256]),
         "tv": lambda: (lambda rng, yy, xx: np.clip((np.array([0.30, 0.40, 0.52]) * (0.6 + 0.4 * vnoise(192, 256, rng, 3, 3)[..., None])
                                                     * (0.85 + 0.15 * ((yy % 4) < 2)[..., None])
                                                     + ((np.abs(xx - 150) < 18) & (yy > 60) & (yy < 150))[..., None] * np.array([0.12, 0.1, 0.08])), 0, 1).astype(np.float32))(
             np.random.default_rng(103), *np.mgrid[0:192, 0:256]),
         "paintings": g_paintings(104)},
    dress=dress_motel_room,
    shots={"1_arrival": ((-1.0, 1.55, -2.0), (2.6, 1.0, 1.4), 76.0),
           "2_wide": ((2.6, 2.3, -4.6), (-2.0, 0.6, 2.6), 82.0),
           "3_detail": ((-0.4, 1.3, 1.0), (2.7, 1.1, 1.0), 58.0)},
)


# ================================================================ 30. rdwe_office_night
def dress_office_night():
    """An open-plan office after hours: carpet tiles, grey walls, a tiled ceiling where only the middle rows are still lit, six banks of desks
    behind blue-grey partitions, every chair pushed in but one, every monitor dark but one (its screen is the notebook's first entry), filing
    cabinets, a printer, a water cooler, plants, exit signs, and the city at night in the south windows."""
    shell("Carpet_Tiles", "Paint_Office", "Ceiling_Tiles", skirt="Trim_Dark", casing="Trim_Dark")
    rng = np.random.default_rng(110)
    mons, scr, kb, P = bmesh.new(), bmesh.new(), bmesh.new(), Painter()
    for i in range(3):
        for j in range(2):
            pb = K.BOX[f"Partition_{i}_{j}"]
            part(f"Partition_{i}_{j}", "Fabric_Partition", lambda bm, pb=pb: (bx(bm, pb),))
            part(f"Partition_{i}_{j}_Cap", "Trim_Dark", lambda bm, pb=pb: box(bm, pb["min"][0], pb["max"][0], 1.38, 1.42, pb["min"][2] - 0.01, pb["max"][2] + 0.01))
            for side in "NS":
                for q in range(2):
                    dn = f"Desk_{i}_{j}_{side}{q}"
                    db = K.BOX[dn]
                    table(dn, db, "Desk_Top", "Steel", t=0.03, r=0.02, inset=0.04, apron=False, round_=False)
                    x0, x1, z0, z1, ty = db["min"][0], db["max"][0], db["min"][2], db["max"][2], db["max"][1]
                    back = z0 if side == "S" else z1                       # the partition side
                    fz = 1 if side == "S" else -1                          # toward the sitter
                    mx = (x0 + x1) / 2 + rng.uniform(-0.2, 0.2)
                    lit = (i, j, side, q) == (1, 0, "S", 1)
                    zc = back + fz * 0.18
                    box(mons, mx - 0.28, mx + 0.28, ty + 0.12, ty + 0.46, zc - 0.015, zc + 0.015)
                    box(mons, mx - 0.03, mx + 0.03, ty, ty + 0.14, zc - 0.01, zc + 0.01)
                    box(mons, mx - 0.12, mx + 0.12, ty, ty + 0.01, zc - 0.08, zc + 0.08)
                    if not lit:
                        box(scr, mx - 0.26, mx + 0.26, ty + 0.14, ty + 0.44, zc + fz * 0.016 - 0.001, zc + fz * 0.016 + 0.001)
                    else:
                        picture("decor_Monitor_Lit", "Screen_Monitor", (mx, ty + 0.29, zc + fz * 0.017), "+z" if fz > 0 else "-z", 0.52, 0.3, (0, 0, 1, 1))
                        light("AREA", (mx, ty + 0.29, zc + fz * 0.05), 4.0, (0.75, 0.85, 1.0), aim=(0, 0, fz), size=(0.5, 0.3), name="Monitor_Glow")
                    box(kb, mx - 0.22, mx + 0.22, ty, ty + 0.02, zc + fz * 0.25 - 0.07, zc + fz * 0.25 + 0.07)
                    if rng.random() < 0.5:
                        cx = x0 + rng.uniform(0.15, 0.4)
                        P.add(["white", "red", "blue", "yellow"][int(rng.integers(4))], cyl, (cx, ty, zc + fz * 0.3), (cx, ty + 0.1, zc + fz * 0.3), 0.04, 0.04, 10)
                    if rng.random() < 0.6:
                        px = x1 - rng.uniform(0.3, 0.6)
                        P.add("paper", box, px, px + 0.21, ty, ty + 0.02 + 0.03 * rng.random(), zc + fz * 0.2 - 0.15, zc + fz * 0.2 + 0.15)
                    part(f"decor_{dn}_Pedestal", "Steel", lambda bm, x1=x1, z0=z0, z1=z1, ty=ty: box(bm, x1 - 0.45, x1 - 0.05, 0.02, ty - 0.04, z0 + 0.05, z1 - 0.1))
                    cn = "Chair_Out" if lit else f"Chair_{i}_{j}_{side}{q}"
                    cb = K.BOX[cn]
                    cx0, cx1, cz0, cz1 = cb["min"][0], cb["max"][0], cb["min"][2], cb["max"][2]
                    if lit:
                        sz0, sz1 = cz0, cz1
                        back_z = cz1
                    else:
                        sz0, sz1 = (cz0 - 0.3, cz1) if side == "S" else (cz0, cz1 + 0.3)
                        back_z = cz1 if side == "S" else cz0
                    ccx = (cx0 + cx1) / 2

                    def office_chair(bm, ccx=ccx, sz0=sz0, sz1=sz1, back_z=back_z):
                        zc2 = (sz0 + sz1) / 2
                        for k in range(5):
                            a = 2 * math.pi * k / 5
                            cyl(bm, (ccx, 0.08, zc2), (ccx + 0.28 * math.cos(a), 0.04, zc2 + 0.28 * math.sin(a)), 0.02, 0.02, 6)
                        cyl(bm, (ccx, 0.08, zc2), (ccx, 0.42, zc2), 0.03, 0.03, 8)
                        box(bm, ccx - 0.25, ccx + 0.25, 0.42, 0.5, sz0 + 0.04, sz1 - 0.04)
                        bz0, bz1 = (back_z - 0.06, back_z) if back_z >= zc2 else (back_z, back_z + 0.06)
                        box(bm, ccx - 0.23, ccx + 0.23, 0.55, 0.95, bz0, bz1)
                        box(bm, ccx - 0.02, ccx + 0.02, 0.48, 0.6, bz0, bz1)
                    part(cn, "Chair_Black", office_chair)
    finish("decor_Monitors", mons, "Plastic_Black")
    finish("decor_Screens_Off", scr, "Screen_Off")
    finish("decor_Keyboards", kb, "Plastic_Grey")
    P.done("decor_Desk_Things")
    for n in ("Filing_1", "Filing_2"):
        b = K.BOX[n]
        part(n, "Cabinet_Grey", lambda bm, b=b: bx(bm, b))
        part(f"decor_{n}_Drawers", "Trim_Dark", lambda bm, b=b: [box(bm, b["min"][0] - 0.006, b["min"][0], 0.06 + k * 0.31, 0.34 + k * 0.31, b["min"][2] + 0.03, b["max"][2] - 0.03)
                                                                for k in range(4)])
    pr = K.BOX["Printer"]
    part("Printer", "Cabinet_Grey", lambda bm: (box(bm, pr["min"][0], pr["max"][0], 0.0, 0.8, pr["min"][2], pr["max"][2]),
                                                box(bm, pr["min"][0] + 0.1, pr["max"][0] - 0.1, 0.8, 1.1, pr["min"][2] + 0.1, pr["max"][2] - 0.1)))
    wc = K.BOX["Water_Cooler"]
    part("Water_Cooler", "Plastic_White", lambda bm: box(bm, wc["min"][0], wc["max"][0], 0.0, 1.0, wc["min"][2], wc["max"][2]))
    part("Water_Cooler_Bottle", "Glass_Blue", lambda bm: cyl(bm, ((wc["min"][0] + wc["max"][0]) / 2, 1.0, (wc["min"][2] + wc["max"][2]) / 2),
                                                            ((wc["min"][0] + wc["max"][0]) / 2, 1.3, (wc["min"][2] + wc["max"][2]) / 2), 0.13, 0.13, 16), smooth=True)
    for n in ("Plant_1", "Plant_2"):
        b = K.BOX[n]
        plant(n, (b["min"][0] + b["max"][0]) / 2, (b["min"][2] + b["max"][2]) / 2, 0.0, 1.3, np.random.default_rng(111 + len(n)), 0.25)
    # the south windows: the city at night, mullions, half-lowered blinds
    picture("decor_City", "Window_City", (0.0, 1.75, K.Z1 - 0.004), "-z", 23.6, 2.1, (0, 0, 1, 1))

    def mullions(bm):
        for x in np.arange(-12.0, 12.01, 2.0):
            wall_box(bm, "S", x - 0.04, x + 0.04, 0.7, 2.8, 0.0, 0.08)
        wall_box(bm, "S", K.X0, K.X1, 0.66, 0.72, 0.0, 0.12)
        wall_box(bm, "S", K.X0, K.X1, 2.78, 2.84, 0.0, 0.08)
    part("decor_Mullions", "Trim_Dark", mullions)
    part("decor_Blinds", "Blind_Slats", lambda bm: [wall_box(bm, "S", x + 0.05, x + 1.95, 2.0 + (0.5 if (int(x) // 2) % 3 == 0 else 0.0) - k * 0.03,
                                                             2.012 + (0.5 if (int(x) // 2) % 3 == 0 else 0.0) - k * 0.03, 0.1, 0.13) for x in np.arange(-12.0, 11.99, 2.0)
                                                    for k in range(int((2.78 - 2.0 - (0.5 if (int(x) // 2) % 3 == 0 else 0.0)) / 0.03))])
    light("AREA", (0.0, 1.8, K.Z1 - 0.3), 160.0, (0.55, 0.62, 0.9), aim=(0, -0.1, -1), size=(23.0, 2.0), name="City_Glow")
    for h in K.HOLES:
        c = on_wall(h["side"], h["a"], h["h"] + 0.3, 0.02)
        picture(f"decor_Exit_{h['side']}", "Exit_Sign", c, KT.SIDE_N[h["side"]], 0.4, 0.15, ATLAS_OFFICE.uv("exit"))
    ceiling_troffers([-9.0, -6.0, -3.0, 0.0, 3.0, 6.0, 9.0], [-7.5, -2.5, 2.5, 7.5], along="z", watts=50.0, color=TUBE,
                     lit=lambda x, z: (-2.6 < z < 2.6) or (x in (0.0, 3.0) and z < 0))


ATLAS_OFFICE = Atlas([("exit", 256, 96, sign("EXIT", (0.05, 0.55, 0.2), (0.95, 1.0, 0.95)))])


def g_monitor():
    lines = ["DAY 1", "", "THEY SAID TO WAIT", "IN THE DINING ROOM.", "", "I DID. NOBODY CAME.", "THE STAIRS GO UP TO", "A DOOR THAT WAS NOT", "THERE BEFORE.", "",
             "I AM WRITING DOWN", "EVERY DOOR."]
    img = text_lines(lines, 384, 640, (0.06, 0.08, 0.12), (0.75, 0.88, 1.0), left=True, rng=np.random.default_rng(112))
    img[:28] = (0.2, 0.3, 0.5)
    return img


OFFICE_NIGHT = dict(
    pages=(2048, 2048),
    grade={"target": 0.9, "shoulder": 1.15},
    mats={"Carpet_Tiles": dict(gen="carpet", rough=1.0, tile=2.0, group="struct"),
          "Paint_Office": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.72, 0.74, 0.72), rough=0.8, tile=2.5, group="struct"),
          "Ceiling_Tiles": dict(gen="ceiltile", rough=0.9, tile=1.2, group="struct"),
          "Trim_Dark": dict(color=(0.20, 0.21, 0.23), rough=0.5, group="struct"),
          "Trim_White": dict(color=(0.92, 0.92, 0.9), rough=0.5),
          "Fabric_Partition": dict(diff="rough_linen_diff_512.jpg", tint=(0.38, 0.45, 0.58), rough=1.0, tile=0.6),
          "Desk_Top": dict(diff="dark_wood_diff_1k.jpg", tint=(1.0, 0.9, 0.78), rough=0.4, tile=1.0),
          "Chair_Black": dict(color=(0.06, 0.06, 0.07), rough=0.6),
          "Plastic_Black": dict(color=(0.04, 0.04, 0.045), rough=0.4),
          "Plastic_Grey": dict(color=(0.55, 0.56, 0.58), rough=0.5),
          "Plastic_White": dict(color=(0.88, 0.88, 0.86), rough=0.4),
          "Screen_Off": dict(color=(0.02, 0.025, 0.03), rough=0.1),
          "Screen_Monitor": dict(gen="monitor", rough=0.2, emit_tex=1.6, group=None),
          "Cabinet_Grey": dict(color=(0.48, 0.50, 0.52), rough=0.5, metal=0.3),
          "Glass_Blue": dict(color=(0.45, 0.65, 0.85), rough=0.1),
          "Pot_Clay": dict(color=(0.25, 0.25, 0.27), rough=0.6),
          "Plant_Leaf": dict(color=(0.10, 0.30, 0.10), rough=0.6, two_sided=True),
          "Window_City": dict(gen="city", rough=1.0, emit_tex=1.2, group=None),
          "Blind_Slats": dict(color=(0.80, 0.80, 0.78), rough=0.6, two_sided=True),
          "Exit_Sign": dict(gen="atlas", rough=0.5, emit_tex=3.0, group=None)},
    gen={"carpet": lambda: g_tiles((0.24, 0.27, 0.32), (0.18, 0.2, 0.24), n=4, S=256, accent=((0.28, 0.30, 0.36), 0.4), seed=113, jitter=0.08)(),
         "ceiltile": g_tiles((0.86, 0.86, 0.84), (0.62, 0.62, 0.6), n=2, S=256, seed=114, jitter=0.02),
         "monitor": g_monitor,
         "city": lambda: (lambda rng: (lambda img: img)(np.clip(
             np.array([0.02, 0.03, 0.07]) + np.where((rng.random((64, 512)) < 0.3)[..., None], np.array([0.9, 0.75, 0.45]), 0.0)[np.repeat(np.arange(64), 4)][:, np.repeat(np.arange(512), 2)][:256, :1024]
             * np.where((np.mgrid[0:256, 0:1024][0] > 90 + 60 * np.sin(np.mgrid[0:256, 0:1024][1] / 40.0) ** 2)[..., None], 1.0, 0.0), 0, 1).astype(np.float32)))(np.random.default_rng(115)),
         "atlas": ATLAS_OFFICE.pixels},
    dress=dress_office_night,
    shots={"1_arrival": ((-10.4, 1.55, -6.0), (2.0, 1.0, -4.0), 74.0),
           "2_wide": ((11.0, 2.4, -9.0), (-6.0, 0.6, 6.0), 82.0),
           "3_detail": ((1.1, 1.45, -3.6), (0.0, 1.0, -5.7), 58.0)},
)


# ================================================================ 31. rdwe_elevator_lobby
def dress_elevator_lobby():
    """A marble lift lobby with steel walls and a coffered ceiling: four lift doors, no two alike in their surrounds (brass sunburst, walnut,
    steel with a red lamp, teal tile), each under a floor dial with no numbers whose needle the page can move, a call pillar with one blank
    button, benches, planters, ash bins and a directory board with every name gone."""
    shell("Marble_Floor", "Steel_Wall", "Ceiling_White", skirt="Trim_Dark", casing=None)
    casings("Trim_Dark", skip=("lift",))
    wall_band("Marble_Wall", 1.2, K.H, name="decor_Wall_Marble_Band", d=0.008)
    rail("Brass", 1.17, 0.04, 0.02, name="decor_Trim_Band_Rail")
    styles = {"DoorLeaf_lift_1": "Brass", "DoorLeaf_lift_2": "Wood_Dark", "DoorLeaf_lift_3": "Chrome", "DoorLeaf_lift_4": "Tile_Teal"}
    for k, h in enumerate([hh for hh in K.HOLES if "lift" in hh["name"]], 1):
        a, hw, ht = h["a"], h["w"] / 2, h["h"]
        m = styles[h["door"]["name"]]
        wdt = {1: 0.18, 2: 0.14, 3: 0.06, 4: 0.22}[k]
        part(f"decor_Wall_Lift_Surround_{k}", m, lambda bm, a=a, hw=hw, ht=ht, wdt=wdt: (wall_box(bm, "N", a - hw - wdt, a - hw, 0.0, ht + wdt, 0.0, 0.05),
                                                                                  wall_box(bm, "N", a + hw, a + hw + wdt, 0.0, ht + wdt, 0.0, 0.05),
                                                                                  wall_box(bm, "N", a - hw, a + hw, ht, ht + wdt, 0.0, 0.05)))
        if k == 1:                                            # the sunburst over lift 1
            part("decor_Sunburst", "Brass", lambda bm, a=a, ht=ht: [poly(bm, [on_wall("N", a, ht + 0.2, 0.052),
                                                                               on_wall("N", a + 0.55 * math.cos(t - 0.06), ht + 0.2 + 0.55 * math.sin(t - 0.06), 0.052),
                                                                               on_wall("N", a + 0.55 * math.cos(t + 0.06), ht + 0.2 + 0.55 * math.sin(t + 0.06), 0.052)])
                                                                     for t in np.linspace(0.25, math.pi - 0.25, 9)], recalc=False)
        if k == 3:
            part("decor_Lift3_Lamp", "Lamp_Red", lambda bm, a=a, ht=ht: cyl(bm, on_wall("N", a + 0.25, ht + 0.12, 0.0), on_wall("N", a + 0.25, ht + 0.12, 0.05), 0.03, 0.03, 12))
        # the dial: a half-round face with no numbers, its needle the page's
        dy = ht + wdt + 0.42
        picture(f"decor_Dial_{k}", "Dials", on_wall("N", a, dy, 0.006), "+z", 0.6, 0.3, ATLAS_LIFT.uv("dial"))
        part(f"decor_Dial_{k}_Rim", "Brass", lambda bm, a=a, dy=dy: wall_box(bm, "N", a - 0.33, a + 0.33, dy - 0.18, dy + 0.18, 0.0, 0.005))
        piv = on_wall("N", a, dy - 0.13, 0.012)
        ang = [0.4, 1.3, 2.2, 2.9][k - 1]
        moving_part(f"Dial_{k}_Needle", "Hand_Black", lambda bm, piv=piv, ang=ang: poly(bm, [(piv[0] - 0.008 * math.sin(ang), piv[1] - 0.008 * math.cos(ang) * 0 + 0.0, piv[2]),
                                                                                            (piv[0] + 0.24 * math.cos(ang), piv[1] + 0.24 * math.sin(ang), piv[2]),
                                                                                            (piv[0] + 0.008 * math.sin(ang), piv[1] + 0.008, piv[2])]), piv, recalc=False)
        light("SPOT", on_wall("N", a, K.H - 0.1, 0.9), 70.0, WARM, 0.05, aim=(0, -1.0, -0.45), cone=60.0)
    K.spec["moving"] = {f"Dial_{k}_Needle": "the lift's floor needle, turning about its pivot (the page)" for k in range(1, 5)}
    cp = K.BOX["Call_Pillar"]
    cx, cz = (cp["min"][0] + cp["max"][0]) / 2, (cp["min"][2] + cp["max"][2]) / 2
    part("Call_Pillar", "Steel", lambda bm: (box(bm, cp["min"][0], cp["max"][0], 0.0, 0.08, cp["min"][2], cp["max"][2]),
                                             box(bm, cx - 0.15, cx + 0.15, 0.08, 1.3, cz - 0.15, cz + 0.15)))
    part("decor_Call_Plate", "Brass", lambda bm: box(bm, cx - 0.1, cx + 0.1, 1.0, 1.2, cz - 0.157, cz - 0.15))
    part("decor_Call_Button", "Button_Glow", lambda bm: cyl(bm, (cx, 1.1, cz - 0.157), (cx, 1.1, cz - 0.175), 0.035, 0.035, 16))
    light("POINT", (cx, 1.1, cz - 0.25), 1.5, (1.0, 0.7, 0.3), 0.03, name="Button_Light")
    for n in ("Bench_W", "Bench_E"):
        bench(n, K.BOX[n], "Wood_Dark", "Steel", slats=False)
    for n in ("Planter_W", "Planter_E"):
        b = K.BOX[n]
        part(n, "Marble_Wall", lambda bm, b=b: bx(bm, b))
        plant(n + "_Plant", (b["min"][0] + b["max"][0]) / 2, (b["min"][2] + b["max"][2]) / 2, 0.95, 1.1, np.random.default_rng(120 + len(n)), 0.22, solid=False)
    for k in range(1, 4):
        b = K.BOX[f"Bin_{k}"]
        bxc, bzc = (b["min"][0] + b["max"][0]) / 2, (b["min"][2] + b["max"][2]) / 2
        part(f"Bin_{k}", "Steel", lambda bm, bxc=bxc, bzc=bzc: cyl(bm, (bxc, 0.0, bzc), (bxc, 0.7, bzc), 0.19, 0.19, 18))
        part(f"decor_Bin_{k}_Sand", "Sand", lambda bm, bxc=bxc, bzc=bzc: disc(bm, (bxc, 0.69, bzc), "y", 0.17, 18), recalc=False)
    picture("decor_Directory", "Dials", on_wall("S", -4.2, 1.7, 0.01), "-z", 1.2, 1.4, ATLAS_LIFT.uv("directory"))
    part("decor_Directory_Frame", "Brass", lambda bm: wall_box(bm, "S", -4.85, -3.55, 0.95, 2.45, 0.0, 0.008))
    # the coffered ceiling: beams in a grid, a downlight in each coffer

    def beams(bm):
        for x in np.arange(-9.0, 9.01, 3.0):
            box(bm, x - 0.12, x + 0.12, K.H - 0.3, K.H, K.Z0, K.Z1)
        for z in (-5.0, 0.0, 5.0):
            box(bm, K.X0, K.X1, K.H - 0.3, K.H, z - 0.12, z + 0.12)
    part("decor_Ceiling_Beams", "Ceiling_White", beams)
    dl = []
    for x in np.arange(-7.5, 7.51, 3.0):
        for z in (-2.5, 2.5):
            dl.append((float(x), z))
            light("SPOT", (float(x), K.H - 0.02, z), 60.0, WARM, 0.05, aim=(0, -1, 0), cone=100.0)
    part("decor_Downlights", "Lamp_Emit", lambda bm: [disc(bm, (x, K.H - 0.004, z), "y", 0.08, 16, -1) for x, z in dl], recalc=False)
    rug("Runner", -1.0, 1.0, 1.4, 4.9, "Rug_Red")


ATLAS_LIFT = Atlas([("dial", 512, 256, lambda h, w: (lambda yy, xx: np.where(((((yy - h) ** 2 + (xx - w / 2) ** 2) < (w * 0.48) ** 2) & (yy < h))[..., None],
                                                                            np.where(((((yy - h) ** 2 + (xx - w / 2) ** 2) > (w * 0.42) ** 2)
                                                                                      & ((np.arctan2(h - yy, xx - w / 2) * 14 / math.pi) % 1 < 0.18))[..., None],
                                                                                     np.array([0.1, 0.08, 0.05]), np.array([0.92, 0.88, 0.76])),
                                                                            np.array([0.55, 0.42, 0.18])).astype(np.float32))(*np.mgrid[0:h, 0:w])),
                    ("directory", 384, 448, lambda h, w: (lambda img: img)(text_lines(["DIRECTORY", "", "", "", "", "", "", "", "", ""], h, w, (0.08, 0.08, 0.09),
                                                                                      (0.85, 0.8, 0.6), rng=np.random.default_rng(121))))])

ELEVATOR_LOBBY = dict(
    pages=(2048, 1024),
    grade={"target": 0.95, "shoulder": 1.15},
    mats={"Marble_Floor": dict(diff="Marble012_color_1k.jpg", tint=(0.92, 0.9, 0.86), rough=0.2, tile=2.0, group="struct"),
          "Steel_Wall": dict(diff="Metal048A_color_512.jpg", tint=(0.82, 0.83, 0.85), rough=0.4, metal=0.5, tile=1.2, group="struct"),
          "Marble_Wall": dict(diff="marble_01_diff_1k.jpg", tint=(0.9, 0.86, 0.8), rough=0.3, tile=1.6, group="struct"),
          "Ceiling_White": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.92, 0.91, 0.88), rough=0.95, tile=2.5, group="struct"),
          "Trim_Dark": dict(color=(0.12, 0.12, 0.13), rough=0.4, group="struct"),
          "Tile_Teal": dict(gen="tile", rough=0.25, tile=0.4),
          "Dials": dict(gen="atlas", rough=0.5),
          "Hand_Black": dict(color=(0.03, 0.03, 0.03), rough=0.4, group=None, two_sided=True),
          "Lamp_Red": dict(color=(1.0, 0.2, 0.1), emit=((1.0, 0.1, 0.05), 4.0), group=None),
          "Button_Glow": dict(color=(1.0, 0.8, 0.5), emit=((1.0, 0.65, 0.25), 3.0), group=None),
          "Sand": dict(color=(0.75, 0.68, 0.52), rough=1.0),
          "Pot_Clay": dict(color=(0.30, 0.30, 0.30), rough=0.6),
          "Plant_Leaf": dict(color=(0.10, 0.30, 0.10), rough=0.6, two_sided=True),
          "Rug_Red": dict(diff="rough_linen_diff_512.jpg", tint=(0.50, 0.08, 0.10), rough=1.0, tile=0.6)},
    gen={"tile": g_tiles((0.05, 0.42, 0.40), (0.85, 0.85, 0.8), n=4, S=256, seed=122, jitter=0.06), "atlas": ATLAS_LIFT.pixels},
    dress=dress_elevator_lobby,
    shots={"1_arrival": ((0.0, 1.55, 3.4), (0.0, 1.6, -5.0), 76.0),
           "2_wide": ((8.0, 2.4, 4.4), (-5.0, 1.2, -4.0), 80.0),
           "3_detail": ((-0.6, 1.5, 2.0), (0.0, 1.1, 0.8), 56.0)},
)


# ================================================================ 32. rdwe_map_room
def dress_map_room():
    """The notebook made real: a big table under green lamps with a model of every room you have found, each a little coloured block, joined
    by red string where a door joins them (G.PAIRS: connections, not space); the rooms not found are blank white blocks. Shelves of binders,
    a desk with the notebook, a plan chest, pinboards of photographs and string."""
    shell("Floor_Oak", "Paper_Map", "Ceiling_Wood", skirt="Trim_Dark", casing="Trim_Dark", dado=("Panel_Dark", 1.0, "Trim_Dark"))
    mt = K.BOX["Map_Table"]
    table("Map_Table", mt, "Felt_Green", "Wood_Dark", t=0.06, r=0.06, inset=0.12, round_=True)
    ty = mt["max"][1]
    ids = list(G.SCENES)
    n = len(ids)
    rng = np.random.default_rng(130)
    pos = {}
    for i, sid in enumerate(ids):                                   # a graph drawing, not a plan: a spiral, jittered
        r = 0.4 + 2.2 * math.sqrt(i / n)
        a = i * 2.39996
        pos[sid] = (r * math.cos(a) + rng.uniform(-0.08, 0.08), r * math.sin(a) + rng.uniform(-0.08, 0.08))
    blank = set(ids[-12:]) - {K.sid}
    P = Painter()
    cols = {"spine": "teal", "house": "peach", "halls": "lilac", "teal": "mint", "inst": "yellow"}
    for sid in ids:
        x, z = pos[sid]
        s = 0.12 + 0.08 * rng.random()
        hgt = 0.06 + 0.06 * rng.random()
        cl = getattr(G.build(sid), "cluster", "") if False else None
        key = "white" if sid in blank else ["teal", "peach", "lilac", "mint", "yellow", "pink", "sky", "acid"][G._h(sid) % 8]
        P.add(key, box, x - s / 2, x + s / 2, ty, ty + hgt, z - s / 2, z + s / 2)
        P.add("red" if sid not in blank else "grey", sphere, (x, ty + hgt + 0.012, z), 0.012, 6)
    for (a, _), (b, _), kind, _ in G.PAIRS:
        if a in pos and b in pos and a not in blank and b not in blank:
            (x0, z0), (x1, z1) = pos[a], pos[b]
            P.add("string", cyl, (x0, ty + 0.13, z0), (x1, ty + 0.13, z1), 0.003, 0.003, 4)
    P.done("decor_Model")
    for k, x in enumerate((-1.5, 1.5), 1):
        pendant(f"Lamp_{k}", x, 0.0, 1.5, 0.3, "Shade_Green", kind="cone", watts=90)
    sw = K.BOX["Shelves_W"]
    part("Shelves_W", "Wood_Dark", lambda bm: (box(bm, sw["min"][0], sw["max"][0], 0.0, 0.06, sw["min"][2], sw["max"][2]),
                                               box(bm, sw["min"][0], sw["min"][0] + 0.02, 0.0, sw["max"][1], sw["min"][2], sw["max"][2]),
                                               [box(bm, sw["min"][0], sw["max"][0], y, y + 0.025, sw["min"][2], sw["max"][2]) for y in (0.45, 0.9, 1.35, 1.8, 2.375)],
                                               [box(bm, sw["min"][0], sw["max"][0], 0.0, sw["max"][1], z - 0.015, z + 0.015) for z in (-4.0, -2.0, 0.0, 2.0, 3.985)]))
    P = Painter()
    rng = np.random.default_rng(131)
    for y in (0.06, 0.475, 0.925, 1.375, 1.825):
        for z0 in (-3.98, -1.98, 0.02, 2.02):
            books_row(P, z0 + 0.02, z0 + 1.95, y, sw["min"][0] + 0.03, sw["max"][0] - 0.02, rng, along="z", hmax=0.34,
                      keys=["book_black", "book_blue", "book_red", "book_green", "paper", "book_tan"])
    P.done("decor_Binders")
    table("Desk_E", K.BOX["Desk_E"], "Wood_Dark", "Wood_Dark", t=0.04, inset=0.05)
    de = K.BOX["Desk_E"]
    P = Painter()
    P.add("book_black", box, 5.5, 5.8, de["max"][1], de["max"][1] + 0.025, -1.4, -1.0)
    P.add("paper", box, 5.45, 5.85, de["max"][1] + 0.025, de["max"][1] + 0.027, -1.42, -0.98)
    P.add("brass", cyl, (5.8, de["max"][1], -0.4), (5.8, de["max"][1] + 0.35, -0.4), 0.01, 0.01, 6)
    P.done("decor_Notebook")
    part("decor_Desk_Lamp_Shade", "Shade_Green", lambda bm: cyl(bm, (5.8, de["max"][1] + 0.32, -0.55), (5.8, de["max"][1] + 0.4, -0.5), 0.12, 0.05, 14, cap=False))
    light("POINT", (5.8, de["max"][1] + 0.3, -0.55), 25.0, WARM, 0.04, name="Desk_Lamp")
    chair("Chair_E", K.BOX["Chair_E"], "Wood_Dark", "Wood_Dark", back="W")
    cabinet("Plan_Chest", K.BOX["Plan_Chest"], "Wood_Dark", "Trim_Dark", doors=1, face="N", plinth=0.06)
    pc = K.BOX["Plan_Chest"]
    part("decor_Plan_Drawers", "Brass", lambda bm: [box(bm, (pc["min"][0] + pc["max"][0]) / 2 - 0.12, (pc["min"][0] + pc["max"][0]) / 2 + 0.12, y, y + 0.02,
                                                        pc["min"][2] - 0.02, pc["min"][2]) for y in (0.2, 0.4, 0.6, 0.8)])
    for k, (sd, a) in enumerate((("E", 2.8), ("E", -4.0), ("N", -3.5), ("S", -3.5)), 1):
        picture(f"decor_Pinboard_{k}", "Pinboard", on_wall(sd, a, 1.75, 0.012), KT.SIDE_N[sd], 1.6, 1.0, (0, 0, 1, 1))
        part(f"decor_Pinboard_{k}_Frame", "Wood_Dark", lambda bm, sd=sd, a=a: wall_box(bm, sd, a - 0.85, a + 0.85, 1.2, 2.3, 0.0, 0.01))
    light("AREA", (0.0, K.H - 0.05, 0.0), 120.0, WARM, aim=(0, -1, 0), size=(8.0, 8.0), name="Fill")


def g_pinboard():
    rng = np.random.default_rng(132)
    img = np.ones((256, 384, 3), np.float32) * np.array([0.62, 0.45, 0.28]) * (0.85 + 0.25 * vnoise(256, 384, rng, 5, 6)[..., None])
    pts = []
    for k in range(9):
        x, y = int(rng.integers(20, 320)), int(rng.integers(15, 190))
        img[y:y + 50, x:x + 44] = np.array([0.9, 0.88, 0.8]) if k % 3 else np.array([0.35, 0.4, 0.45])
        img[y + 6:y + 40, x + 5:x + 39] *= 0.85
        pts.append((x + 22, y + 4))
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        for t in np.linspace(0, 1, 200):
            img[int(y0 + (y1 - y0) * t), int(x0 + (x1 - x0) * t)] = (0.8, 0.05, 0.05)
    return img


MAP_ROOM = dict(
    pages=(2048, 1024),
    grade={"target": 0.9, "shoulder": 1.15},
    mats={"Floor_Oak": dict(diff="old_wood_floor_diff_1k.jpg", tint=(0.95, 0.85, 0.72), rough=0.5, tile=1.4, group="struct"),
          "Paper_Map": dict(gen="mappaper", rough=0.9, tile=1.2, group="struct"),
          "Panel_Dark": dict(diff="dark_wood_diff_1k.jpg", tint=(0.75, 0.65, 0.55), rough=0.5, tile=1.2, group="struct"),
          "Ceiling_Wood": dict(diff="dark_wood_diff_1k.jpg", tint=(0.8, 0.7, 0.6), rough=0.6, tile=1.6, group="struct"),
          "Trim_Dark": dict(diff="dark_wood_diff_1k.jpg", tint=(0.6, 0.5, 0.45), rough=0.45, tile=0.8, group="struct"),
          "Felt_Green": dict(diff="rough_linen_diff_512.jpg", tint=(0.12, 0.40, 0.20), rough=1.0, tile=0.6),
          "Shade_Green": dict(color=(0.05, 0.35, 0.18), rough=0.3, two_sided=True),
          "Pinboard": dict(gen="pinboard", rough=0.9)},
    gen={"mappaper": lambda: (lambda rng: np.clip(np.ones((512, 512, 3), np.float32) * np.array([0.84, 0.78, 0.58]) * (0.88 + 0.18 * vnoise(512, 512, rng, 6, 3)[..., None])
                                                  - (np.abs(vnoise(512, 512, rng, 4, 2) - 0.5) < 0.01)[..., None] * 0.25, 0, 1).astype(np.float32))(np.random.default_rng(133)),
         "pinboard": g_pinboard},
    dress=dress_map_room,
    shots={"1_arrival": ((0.0, 1.55, 3.6), (0.0, 0.8, -1.0), 72.0),
           "2_wide": ((5.0, 2.5, 5.0), (-3.0, 0.6, -3.0), 80.0),
           "3_detail": ((-1.6, 1.6, 2.6), (0.4, 0.9, -0.4), 56.0)},
)


# ================================================================ 33. rdwe_vending_room
VENDS = {"Machine_1": ("red", "snacks"), "Machine_2": ("cyan", "drinks"), "Machine_3": ("acid", "odd"), "Machine_4": ("sun", "coffee"), "Machine_5": ("cyan", "cold")}


def dress_vending_room():
    """A small navy room of glowing vending machines (snacks, drinks, coffee, a cold cabinet, one of strange things), a bench and a bin, one
    tube still lit, and a door marked EXIT under a green sign that never opens. The machine in the middle of the north wall is a door."""
    shell("Vinyl_Dark", "Paint_Navy", "Ceiling_Tiles", skirt="Trim_Steel", casing="Trim_Steel", skip_casings=("machine",))
    for n, (col, kind) in VENDS.items():
        b = K.BOX[n]
        mn, mx = b["min"], b["max"]
        if n in ("Machine_4", "Machine_5"):
            face, nrm = "-x", (-1, 0, 0)
        else:
            face, nrm = "+z", (0, 0, 1)
        part(n, f"Vend_{col.title()}", lambda bm, b=b: bx(bm, b))
        if face == "+z":
            c = ((mn[0] + mx[0]) / 2 - 0.1, 1.15, mx[2] + 0.004)
            w, h = (mx[0] - mn[0]) - 0.32, 1.25
            part(f"decor_{n}_Panel", "Vend_Panel", lambda bm, mn=mn, mx=mx: box(bm, mx[0] - 0.22, mx[0] - 0.04, 0.6, 1.7, mx[2], mx[2] + 0.01))
            part(f"decor_{n}_Tray", "Iron", lambda bm, mn=mn, mx=mx: box(bm, mn[0] + 0.08, mx[0] - 0.26, 0.15, 0.4, mx[2], mx[2] + 0.02))
        else:
            c = (mn[0] - 0.004, 1.12, (mn[2] + mx[2]) / 2 + 0.1)
            w, h = (mx[2] - mn[2]) - 0.32, 1.2
            part(f"decor_{n}_Panel", "Vend_Panel", lambda bm, mn=mn, mx=mx: box(bm, mn[0] - 0.01, mn[0], 0.6, 1.6, mn[2] + 0.04, mn[2] + 0.22))
            part(f"decor_{n}_Tray", "Iron", lambda bm, mn=mn, mx=mx: box(bm, mn[0] - 0.02, mn[0], 0.15, 0.4, mn[2] + 0.26, mx[2] - 0.08))
        picture(f"decor_{n}_Front", "Vend_Glow", c, face, w, h, ATLAS_VEND.uv(kind))
        lp = (c[0] + nrm[0] * 0.3, 1.1, c[2] + nrm[2] * 0.3)
        light("AREA", lp, 14.0, (0.85, 0.9, 1.0), aim=nrm, size=(w, h), name=f"{n}_Glow")
    # the machine that is a door: its glow, and a frame flush round it in the wall
    h = next(hh for hh in K.HOLES if hh["name"] == "DoorLeaf_machine")
    a, hw, ht = h["a"], h["w"] / 2, h["h"]
    part("decor_Machine_Door_Frame", "Vend_Body", lambda bm: (wall_box(bm, "N", a - hw - 0.08, a - hw, 0.0, ht + 0.08, 0.0, 0.06),
                                                              wall_box(bm, "N", a + hw, a + hw + 0.08, 0.0, ht + 0.08, 0.0, 0.06),
                                                              wall_box(bm, "N", a - hw, a + hw, ht, ht + 0.08, 0.0, 0.06)))
    light("AREA", on_wall("N", a - 0.1, 1.2, 0.35), 14.0, (0.85, 0.9, 1.0), aim=(0, 0, 1), size=(0.7, 1.3), name="Door_Machine_Glow")
    es = K.BOX["decor_Exit_Sign"]
    picture("decor_Exit_Sign", "Exit_Sign", (K.X0 + 0.08, (es["min"][1] + es["max"][1]) / 2, 0.0), "+x", 0.8, 0.25, ATLAS_VEND.uv("exit"))
    part("decor_Exit_Box", "Iron", lambda bm: box(bm, K.X0, K.X0 + 0.078, es["min"][1] - 0.02, es["max"][1] + 0.02, -0.42, 0.42))
    light("AREA", (K.X0 + 0.2, 2.2, 0.0), 6.0, (0.3, 1.0, 0.4), aim=(1, -0.5, 0), size=(0.8, 0.25), name="Exit_Glow")
    bench("Bench", K.BOX["Bench"], "Plastic_Blue", "Chrome", slats=False)
    b = K.BOX["Bin"]
    part("Bin", "Steel", lambda bm: cyl(bm, ((b["min"][0] + b["max"][0]) / 2, 0.0, (b["min"][2] + b["max"][2]) / 2), ((b["min"][0] + b["max"][0]) / 2, 0.75,
                                                                                                                  (b["min"][2] + b["max"][2]) / 2), 0.24, 0.24, 18))
    ceiling_troffers([-2.0, 2.0], [-1.5, 1.5], along="x", watts=40.0, color=TUBE, lit=lambda x, z: x > 0 and z > 0)
    P = Painter()
    rng = np.random.default_rng(140)
    for i in range(6):
        x, z = rng.uniform(-3.0, 2.5), rng.uniform(-2.5, 3.0)
        P.add(["red", "yellow", "white", "blue", "orange", "green"][i], box, x, x + 0.08, 0.0, 0.004, z, z + 0.14)
    P.done("decor_Wrappers")


def g_vend():
    """The machine fronts: rows of products behind glass, per machine kind; and the EXIT sign."""
    return ATLAS_VEND.pixels()


def vend_front(kind, seed):
    def f(h, w):
        rng = np.random.default_rng(seed)
        img = np.ones((h, w, 3), np.float32) * np.array([0.78, 0.82, 0.86])
        rows = 6 if kind != "cold" else 4
        cols = 5 if kind not in ("drinks", "cold") else 4
        for r in range(rows):
            y0 = int(h * r / rows)
            img[y0:y0 + 4] = (0.35, 0.36, 0.38)
            for c in range(cols):
                x0 = int(w * c / cols) + 6
                pw, ph = int(w / cols) - 12, int(h / rows) - 18
                col = np.array([rng.uniform(0.1, 1.0), rng.uniform(0.1, 0.9), rng.uniform(0.1, 0.8)])
                if kind == "drinks" or kind == "cold":
                    img[y0 + 10:y0 + 10 + ph, x0 + pw // 4:x0 + 3 * pw // 4] = col
                elif kind == "odd":
                    yy, xx = np.mgrid[0:ph, 0:pw]
                    m = ((yy - ph / 2) ** 2 + (xx - pw / 2) ** 2) < (min(pw, ph) / 2.5) ** 2
                    img[y0 + 10:y0 + 10 + ph, x0:x0 + pw][m] = col
                else:
                    img[y0 + 14:y0 + 10 + ph, x0:x0 + pw] = col
                img[y0 + int(h / rows) - 10:y0 + int(h / rows) - 4, x0 + pw // 2 - 8:x0 + pw // 2 + 8] = (0.95, 0.95, 0.95)
        return img
    return f


ATLAS_VEND = Atlas([("snacks", 256, 384, vend_front("snacks", 141)), ("drinks", 256, 384, vend_front("drinks", 142)), ("odd", 256, 384, vend_front("odd", 143)),
                    ("coffee", 256, 384, lambda h, w: text_lines(["", "COFFEE", "", "BLACK", "WHITE", "SUGAR", "", ""], h, w, (0.25, 0.14, 0.08), (0.98, 0.9, 0.7))),
                    ("cold", 256, 384, vend_front("cold", 144)),
                    ("exit", 512, 160, sign("EXIT", (0.05, 0.55, 0.2), (0.95, 1.0, 0.95)))])

VENDING_ROOM = dict(
    pages=(2048, 1024),
    grade={"target": 0.9, "shoulder": 1.15},
    mats={"Vinyl_Dark": dict(gen="vinyl", rough=0.45, tile=1.2, group="struct"),
          "Paint_Navy": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.20, 0.25, 0.55), rough=0.7, tile=2.5, group="struct"),
          "Ceiling_Tiles": dict(gen="ceiltile", rough=0.9, tile=1.2, group="struct"),
          "Trim_Steel": dict(color=(0.62, 0.64, 0.66), rough=0.35, metal=0.6, group="struct"),
          "Trim_White": dict(color=(0.92, 0.92, 0.9), rough=0.5),
          "Vend_Red": dict(color=(0.70, 0.06, 0.06), rough=0.35), "Vend_Cyan": dict(color=(0.05, 0.55, 0.65), rough=0.35),
          "Vend_Acid": dict(color=(0.55, 0.85, 0.08), rough=0.35), "Vend_Sun": dict(color=(0.85, 0.62, 0.08), rough=0.35),
          "Vend_Glow": dict(gen="atlas", rough=0.1, emit_tex=1.4, group=None),
          "Exit_Sign": dict(gen="atlas", rough=0.5, emit_tex=3.0, group=None),
          "Plastic_Blue": dict(color=(0.08, 0.30, 0.62), rough=0.4)},
    gen={"vinyl": g_tiles((0.30, 0.31, 0.33), (0.20, 0.20, 0.22), n=4, S=256, seed=145, jitter=0.06),
         "ceiltile": g_tiles((0.86, 0.86, 0.84), (0.62, 0.62, 0.6), n=2, S=256, seed=146, jitter=0.02), "atlas": g_vend},
    dress=dress_vending_room,
    shots={"1_arrival": ((0.0, 1.55, 2.6), (0.4, 1.2, -4.0), 78.0),
           "2_wide": ((3.0, 2.3, 3.4), (-3.0, 1.0, -3.0), 84.0),
           "3_detail": ((-1.6, 1.5, 1.4), (-4.0, 1.6, 0.0), 64.0)},
)


# ================================================================ 34. rdwe_melting_library
def sag_y(z, j):
    """How far a shelf at level j has slumped at z (metres, down): most in the middle of the run, more higher up."""
    return (0.06 + 0.07 * j) * (1 - (z / 4.0) ** 2)


def lean_x(y, k):
    """The rows lean into the aisle as they rise (k = 1 the west row, 2 the east)."""
    return (1 if k == 1 else -1) * 0.5 * (y / 4.6) ** 1.5


def dress_melting_library():
    """Two rows of tall bookcases that lean into the aisle and slump like wax, their shelves sagging, their books sliding and dripping in
    strands; oxblood walls lined with ordinary straight shelves (only the middle melts), a reading table with green lamps, a globe, a melting
    chandelier, and a stone arch round the north door. The shelves are baked where they are (the page does not animate them)."""
    shell("Floor_Parquet", "Paper_Oxblood", "Ceiling_Dark", skirt="Trim_Dark", casing="Trim_Dark", skip_casings=("arch",))
    rng = np.random.default_rng(150)
    for k, x in ((1, -4.0), (2, 4.0)):
        for j in range(3):
            b = K.BOX[f"Shelf_{k}_{j + 1}"]
            y0, y1 = b["min"][1], b["max"][1]

            def case(bm, k=k, x=x, j=j, b=b, y0=y0, y1=y1):
                zs = np.linspace(-4.0, 4.0, 33)
                for yb in np.arange(y0, y1 - 0.05, 0.45 if j == 0 else 0.46):     # the boards: a strip along z, slumped and leaning
                    for z0, z1 in zip(zs, zs[1:]):
                        ya, yb2 = yb - sag_y(z0, j + yb / 2), yb - sag_y(z1, j + yb / 2)
                        xa, xb = x + lean_x(ya, k), x + lean_x(yb2, k)
                        xa0, xa1 = max(b["min"][0], xa - 0.38), min(b["max"][0], xa + 0.38)
                        xb0, xb1 = max(b["min"][0], xb - 0.38), min(b["max"][0], xb + 0.38)
                        quad(bm, (xa0, ya + 0.03, z0), (xa1, ya + 0.03, z0), (xb1, yb2 + 0.03, z1), (xb0, yb2 + 0.03, z1))
                        quad(bm, (xa0, ya, z0), (xb0, yb2, z1), (xb1, yb2, z1), (xa1, ya, z0))
                        quad(bm, (xa1, ya, z0), (xb1, yb2, z1), (xb1, yb2 + 0.03, z1), (xa1, ya + 0.03, z0))
                        quad(bm, (xa0, ya, z0), (xa0, ya + 0.03, z0), (xb0, yb2 + 0.03, z1), (xb0, yb2, z1))
                for zu in (-4.0, -2.0, 0.0, 2.0, 4.0):                          # the uprights, bent the same way
                    ys = np.linspace(y0, y1, 8)
                    for ya, yb2 in zip(ys, ys[1:]):
                        xa, xb = x + lean_x(ya, k), x + lean_x(yb2, k)
                        xa0, xa1 = max(b["min"][0], xa - 0.38), min(b["max"][0], xa + 0.38)
                        xb0, xb1 = max(b["min"][0], xb - 0.38), min(b["max"][0], xb + 0.38)
                        za0, za1 = zu - 0.025 - (0.03 * math.sin(ya * 3) if abs(zu) < 3 else 0), zu + 0.025
                        quad(bm, (xa0, ya, za1), (xa1, ya, za1), (xb1, yb2, za1), (xb0, yb2, za1))
                        quad(bm, (xa1, ya, za0), (xa0, ya, za0), (xb0, yb2, za0), (xb1, yb2, za0))
                        quad(bm, (xa1, ya, za1), (xa1, ya, za0), (xb1, yb2, za0), (xb1, yb2, za1))
                        quad(bm, (xa0, ya, za0), (xa0, ya, za1), (xb0, yb2, za1), (xb0, yb2, za0))
                back = b["min"][0] if k == 1 else b["max"][0]                    # the back panel, on the outside of the row
                box(bm, back - 0.01, back + 0.01, y0, y1, -4.0, 4.0) if j == 0 else None
            part(f"Shelf_{k}_{j + 1}", "Shelf_Wood", case, recalc=False, smooth=True, sharp_deg=60)
        # the books on every board: following the slump, tilted, some sliding off the edge
        P = Painter()
        for j in range(3):
            b = K.BOX[f"Shelf_{k}_{j + 1}"]
            for yb in np.arange(b["min"][1], b["max"][1] - 0.05, 0.45 if j == 0 else 0.46):
                z = -3.95
                while z < 3.9:
                    t = rng.uniform(0.03, 0.06)
                    hh = rng.uniform(0.2, 0.32)
                    ya = yb + 0.03 - sag_y(z, j + yb / 2)
                    xc = x + lean_x(ya, k)
                    tilt = (sag_y(z + 0.1, j + yb / 2) - sag_y(z - 0.1, j + yb / 2)) * 3
                    key = ["book_red", "book_green", "book_blue", "book_tan", "book_black", "book_ochre", "book_cream", "book_plum"][int(rng.integers(8))]
                    slide = rng.random() < 0.06
                    if slide:
                        P.add(key, quad, (xc + 0.35 * (1 if k == 1 else -1), ya, z), (xc + 0.6 * (1 if k == 1 else -1), ya - 0.25, z),
                              (xc + 0.6 * (1 if k == 1 else -1), ya - 0.25, z + t), (xc + 0.35 * (1 if k == 1 else -1), ya, z + t))
                    else:
                        bmp = (xc - 0.3, xc + 0.3)
                        P.add(key, lambda bm, xa=bmp[0], xb=bmp[1], ya=ya, z=z, t=t, hh=hh, tilt=tilt: poly(bm, [(xa, ya, z), (xa, ya, z + t), (xa, ya + hh, z + t + tilt * hh),
                                                                                                                (xa, ya + hh, z + tilt * hh)])
                              if False else box(bm, xa, xb, ya, ya + hh, z, z + t))
                    z += t + rng.uniform(0.0, 0.01)
        P.done(f"decor_Books_{k}")
        # wax drips from the boards' slumped middles
        part(f"decor_Drips_{k}", "Wax", lambda bm, k=k, x=x: [cyl(bm, (x + lean_x(y, k) + rng.uniform(-0.3, 0.3), y - sag_y(z, 1), z),
                                                                (x + lean_x(y, k) + rng.uniform(-0.3, 0.3), y - sag_y(z, 1) - rng.uniform(0.15, 0.6), z + rng.uniform(-0.05, 0.05)),
                                                                0.025, 0.006, 8) for y in (1.8, 2.7, 3.6) for z in rng.uniform(-2.5, 2.5, 6)], smooth=True)
    # the wall shelves: straight, ordinary
    for n in ("Wall_Shelves_W", "Wall_Shelves_E"):
        b = K.BOX[n]
        part(n, "Shelf_Wood", lambda bm, b=b: (box(bm, b["min"][0], b["max"][0], 0.0, 0.06, b["min"][2], b["max"][2]),
                                               box(bm, b["min"][0], b["max"][0], b["max"][1] - 0.05, b["max"][1], b["min"][2], b["max"][2]),
                                               [box(bm, b["min"][0], b["max"][0], y, y + 0.025, b["min"][2], b["max"][2]) for y in (0.45, 0.9, 1.35, 1.8, 2.25, 2.7)],
                                               [box(bm, b["min"][0], b["max"][0], 0.0, b["max"][1], z - 0.015, z + 0.015) for z in np.linspace(b["min"][2], b["max"][2], 6)]))
        P = Painter()
        for y in (0.06, 0.475, 0.925, 1.375, 1.825, 2.275, 2.725):
            books_row(P, b["min"][2] + 0.02, b["max"][2] - 0.02, y, b["min"][0] + 0.02, b["max"][0] - 0.02, rng, along="z", hmax=0.34)
        P.done(f"decor_{n}_Books")
    table("Reading_Table", K.BOX["Reading_Table"], "Shelf_Wood", "Shelf_Wood", t=0.05, inset=0.08)
    rt = K.BOX["Reading_Table"]
    for k, x in enumerate((-0.7, 0.7), 1):
        part(f"decor_Banker_{k}", "Brass", lambda bm, x=x: (cyl(bm, (x, rt["max"][1], -5.4), (x, rt["max"][1] + 0.02, -5.4), 0.08, 0.08, 14),
                                                          cyl(bm, (x, rt["max"][1] + 0.02, -5.4), (x, rt["max"][1] + 0.32, -5.4), 0.01, 0.01, 6)))
        part(f"decor_Banker_{k}_Shade", "Shade_Green", lambda bm, x=x: cyl(bm, (x - 0.18, rt["max"][1] + 0.34, -5.4), (x + 0.18, rt["max"][1] + 0.34, -5.4), 0.06, 0.06, 14, cap=False))
        light("POINT", (x, rt["max"][1] + 0.3, -5.4), 25.0, WARM, 0.04)
    P = Painter()
    P.add("paper", box, -0.3, 0.3, rt["max"][1], rt["max"][1] + 0.02, -5.55, -5.2)
    P.add("book_red", box, -0.32, 0.32, rt["max"][1] - 0.002, rt["max"][1] + 0.012, -5.57, -5.18)
    P.done("decor_Open_Book")
    gb = K.BOX["Globe"]
    gx, gz = (gb["min"][0] + gb["max"][0]) / 2, (gb["min"][2] + gb["max"][2]) / 2
    part("Globe", "Shelf_Wood", lambda bm: (cyl(bm, (gx, 0.0, gz), (gx, 0.05, gz), 0.25, 0.25, 16), cyl(bm, (gx, 0.05, gz), (gx, 0.72, gz), 0.03, 0.03, 8)))
    part("Globe_Ball", "Globe_Map", lambda bm: sphere(bm, (gx, 0.88, gz), 0.22, 18, 0.8), smooth=True)
    rr = K.BOX["decor_Rug"]
    rug("Rug", rr["min"][0], rr["max"][0], rr["min"][2], rr["max"][2], "Rug_Red")
    # the chandelier, melting: a brass ring with candles that run
    part("decor_Chandelier", "Brass", lambda bm: (torus(bm, (0.0, 3.4, 0.0), "y", 0.6, 0.025, 28, 6), cyl(bm, (0.0, 3.4, 0.0), (0.0, K.H, 0.0), 0.012, 0.012, 6)))
    part("decor_Candles", "Wax", lambda bm: [cyl(bm, (0.6 * math.cos(a), 3.2 - 0.25 * (k % 3), 0.6 * math.sin(a)), (0.6 * math.cos(a), 3.42, 0.6 * math.sin(a)), 0.025, 0.03, 8)
                                             for k, a in enumerate(np.linspace(0, 2 * math.pi, 8, endpoint=False))], smooth=True)
    part("decor_Flames", "Lamp_Emit", lambda bm: [sphere(bm, (0.6 * math.cos(a), 3.46, 0.6 * math.sin(a)), 0.02, 8, 1.8) for a in np.linspace(0, 2 * math.pi, 8, endpoint=False)])
    light("POINT", (0.0, 3.3, 0.0), 160.0, (1.0, 0.72, 0.42), 0.6, name="Chandelier")
    for sd in "WE":
        for a in (-3.0, 3.0):
            c = on_wall(sd, a, 3.6, 0.5)
            light("POINT", c, 30.0, WARM, 0.1)
            part(f"decor_Sconce_{sd}{int(a)}", "Lamp_Emit", lambda bm, c=c: sphere(bm, c, 0.05, 8))
            part(f"decor_Sconce_{sd}{int(a)}_Arm", "Brass", lambda bm, c=c, sd=sd, a=a: cyl(bm, on_wall(sd, a, 3.5, 0.0), c, 0.012, 0.012, 6))
    # the stone arch round the north door
    h = next(hh for hh in K.HOLES if hh["name"] == "DoorLeaf_arch")
    a, hw, ht = h["a"], h["w"] / 2, h["h"]

    def arch(bm):
        wall_box(bm, "N", a - hw - 0.3, a - hw, 0.0, ht, 0.0, 0.12)
        wall_box(bm, "N", a + hw, a + hw + 0.3, 0.0, ht, 0.0, 0.12)
        R0, R1 = hw, hw + 0.3
        seg = 14
        for i in range(seg):
            t0, t1 = math.pi * i / seg, math.pi * (i + 1) / seg
            pts = [on_wall("N", a + R1 * math.cos(t0), ht + R1 * math.sin(t0), 0.12), on_wall("N", a + R1 * math.cos(t1), ht + R1 * math.sin(t1), 0.12),
                   on_wall("N", a + R0 * math.cos(t1), ht + R0 * math.sin(t1), 0.12), on_wall("N", a + R0 * math.cos(t0), ht + R0 * math.sin(t0), 0.12)]
            poly(bm, pts)
            quad(bm, on_wall("N", a + R0 * math.cos(t0), ht + R0 * math.sin(t0), 0.12), on_wall("N", a + R0 * math.cos(t1), ht + R0 * math.sin(t1), 0.12),
                 on_wall("N", a + R0 * math.cos(t1), ht + R0 * math.sin(t1), 0.0), on_wall("N", a + R0 * math.cos(t0), ht + R0 * math.sin(t0), 0.0))
        wall_box(bm, "N", a - hw, a + hw, ht, ht + hw, 0.0, 0.002)
    part("decor_Arch", "Stone", arch, recalc=False)
    part("decor_Arch_Fill", "Void_Black", lambda bm: wall_box(bm, "N", a - hw, a + hw, ht, ht + hw - 0.02, 0.0, 0.004))


MELTING_LIBRARY = dict(
    pages=(2048, 2048),
    grade={"target": 0.9, "shoulder": 1.15},
    mats={"Floor_Parquet": dict(diff="herringbone_parquet_diff_1k.jpg", tint=(0.85, 0.72, 0.6), rough=0.4, tile=1.6, group="struct"),
          "Paper_Oxblood": dict(gen="paper", rough=0.9, tile=0.9, group="struct"),
          "Ceiling_Dark": dict(diff="dark_wood_diff_1k.jpg", tint=(0.7, 0.6, 0.55), rough=0.6, tile=1.6, group="struct"),
          "Trim_Dark": dict(diff="dark_wood_diff_1k.jpg", tint=(0.6, 0.5, 0.45), rough=0.45, tile=0.8, group="struct"),
          "Shelf_Wood": dict(diff="dark_wood_diff_1k.jpg", tint=(1.0, 0.82, 0.66), rough=0.45, tile=1.0, two_sided=True),
          "Wax": dict(color=(0.60, 0.12, 0.10), rough=0.25),
          "Shade_Green": dict(color=(0.05, 0.35, 0.18), rough=0.3, two_sided=True),
          "Globe_Map": dict(color=(0.20, 0.38, 0.55), rough=0.5),
          "Rug_Red": dict(diff="rough_linen_diff_512.jpg", tint=(0.42, 0.08, 0.08), rough=1.0, tile=0.6),
          "Stone": dict(diff="concrete_floor_02_diff_1k.jpg", tint=(0.92, 0.88, 0.80), rough=0.8, tile=1.0)},
    gen={"paper": g_damask((0.32, 0.03, 0.05), (0.45, 0.08, 0.08), seed=151)},
    dress=dress_melting_library,
    shots={"1_arrival": ((-3.0, 1.55, 5.6), (1.0, 2.0, -6.0), 74.0),
           "2_wide": ((6.0, 2.6, 6.2), (-1.0, 1.6, -4.0), 80.0),
           "3_detail": ((0.0, 1.5, 2.8), (0.0, 2.6, -2.0), 70.0)},
)


ROOMS = {"rdwe_void_room": VOID, "rdwe_lights_out": LIGHTS_OUT, "rdwe_green_grid": GREEN_GRID, "rdwe_ames_room": AMES,
         "rdwe_shrink_hall": SHRINK_HALL, "rdwe_moon_window": MOON_WINDOW, "rdwe_mirror_room": MIRROR_ROOM, "rdwe_dont_look": DONT_LOOK,
         "rdwe_waiting_room": WAITING_ROOM, "rdwe_wrong_clock": WRONG_CLOCK, "rdwe_crossroads": CROSSROADS, "rdwe_changing_rooms": CHANGING_ROOMS,
         "rdwe_laundromat": LAUNDROMAT, "rdwe_motel_room": MOTEL_ROOM, "rdwe_office_night": OFFICE_NIGHT, "rdwe_elevator_lobby": ELEVATOR_LOBBY,
         "rdwe_map_room": MAP_ROOM, "rdwe_vending_room": VENDING_ROOM, "rdwe_melting_library": MELTING_LIBRARY}


# ================================================================ the run
def build_scene(sid, stages, samples, rsamples):
    spec = ROOMS[sid]
    t0 = time.time()
    KT.reset(sid, spec)
    spec["dress"]()
    KT.fill_missing()
    KT.build_leaves()
    if spec.get("post"):
        spec["post"]()
    KT.build_layout()
    KT.add_lights()
    KT.setup_world()
    KT.apply_light_set(K.SETS[0])
    K.LAYOUT.hide_render = True
    KT.summary()
    KT.save_blend()
    print(f"STAGE art {sid} {time.time() - t0:.0f}s")
    if "layout" in stages:
        KT.stage_layout()
    if "check" in stages:
        KT.stage_check()
    if "bake" in stages:
        t1 = time.time()
        KT.stage_bake(samples)
        KT.save_blend()
        print(f"STAGE bake {sid} {time.time() - t1:.0f}s")
        if "export" in stages:
            KT.stage_export()
            KT.save_blend()
    if "render" in stages:
        t1 = time.time()
        KT.stage_render(rsamples, only=None)
        print(f"STAGE render {sid} {time.time() - t1:.0f}s")
    KT.save_blend()
    print(f"SCENE DONE {sid} {time.time() - t0:.0f}s")


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

    def arg(n, d=None, cast=str):
        return cast(a[a.index(n) + 1]) if n in a else d
    ids = arg("--scenes", "").split(",")
    stages = set(arg("--stage", "art,layout,check,bake,export,render").split(","))
    print("BLENDER", bpy.app.version_string)
    for sid in ids:
        try:
            build_scene(sid, stages, arg("--samples", 256, int), arg("--render-samples", 96, int))
        except Exception:
            import traceback
            traceback.print_exc()
            print("SCENE FAILED", sid)
    print("ALL DONE")
