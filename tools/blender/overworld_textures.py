"""The Overworld's dressing textures, made here from noise and drawing (no downloads, no third-party pixels): plain Python with numpy and Pillow.

    python tools/blender/overworld_textures.py            writes blender/textures/overworld/<name>.jpg

Every tiling texture is periodic (its noise is built in the Fourier domain), so it repeats without a seam. The colours are the Overworld's
plastic dreamcore palette (docs/WORLD.md: "plastic, like a simulation, and eerily beautiful"): clean, a little too saturated, soft. Albedos stay
under about 0.75 (linear) so a lit surface does not clip. tools/blender/dress_overworld.py loads them by path.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "blender/textures/overworld"
RNG = np.random.default_rng(7)


def pnoise(h, w, scale, rng=RNG):
    """Periodic noise in 0..1: white noise low-passed in the Fourier domain (scale: the feature size in pixels)."""
    f = np.fft.fft2(rng.standard_normal((h, w)))
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    k = np.exp(-((fx ** 2 + fy ** 2) * (scale ** 2)) * 2.0)
    a = np.real(np.fft.ifft2(f * k))
    a -= a.min()
    return a / max(a.max(), 1e-9)


def fbm(h, w, scales, weights):
    a = sum(wt * pnoise(h, w, s) for s, wt in zip(scales, weights))
    a -= a.min()
    return a / max(a.max(), 1e-9)


def mix(c0, c1, t):
    c0, c1 = np.array(c0, float), np.array(c1, float)
    return c0[None, None, :] * (1 - t[..., None]) + c1[None, None, :] * t[..., None]


def save(name, rgb_srgb):
    OUT.mkdir(parents=True, exist_ok=True)
    im = Image.fromarray(np.clip(rgb_srgb * 255 + 0.5, 0, 255).astype(np.uint8), "RGB")
    p = OUT / f"{name}.jpg"
    im.save(p, "JPEG", quality=88, optimize=True)        # Pillow writes no comment or EXIF unless asked
    print(f"{p.relative_to(ROOT)}  {im.size[0]}x{im.size[1]}  {p.stat().st_size / 1e3:.0f} KB")


def font(px):
    for f in ("C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            continue
    return ImageFont.load_default(size=px)


# sRGB colours (what the eye sees), 0..1
def grass(n=1024):
    t = fbm(n, n, (90, 30, 8), (0.5, 0.35, 0.15))
    c = mix((0.40, 0.72, 0.36), (0.55, 0.84, 0.42), t)
    blades = pnoise(n, n, 1.2)
    c *= (0.92 + 0.12 * blades)[..., None]
    flecks = pnoise(n, n, 2.0) > 0.86
    c[flecks] = c[flecks] * 0.6 + np.array([0.80, 0.92, 0.55]) * 0.4
    return np.clip(c, 0, 0.86)


def hedge(n=512):
    t = fbm(n, n, (24, 8, 2.5), (0.3, 0.4, 0.3))
    c = mix((0.22, 0.48, 0.28), (0.44, 0.72, 0.42), t ** 1.3)
    hi = pnoise(n, n, 3.0) > 0.8
    c[hi] = c[hi] * 0.5 + np.array([0.55, 0.80, 0.45]) * 0.5
    return c


def bark(n=512):
    y = np.linspace(0, 1, n, endpoint=False)
    streak = fbm(n, n, (2, 6), (0.6, 0.4))
    streak = np.roll(streak, 0, 0)
    t = 0.5 * streak + 0.5 * fbm(n, n, (40, 12), (0.6, 0.4))
    t = np.clip(t, 0, 1)
    c = mix((0.46, 0.33, 0.29), (0.70, 0.54, 0.47), t)        # a warm, slightly lilac brown
    # vertical fissures: stretch the noise along v by sampling a narrow-wide field
    f = pnoise(n, n // 8, 1.5)
    f = np.repeat(f, 8, axis=1)[:, :n]
    c *= (0.85 + 0.2 * f)[..., None]
    _ = y
    return np.clip(c, 0, 0.8)


def planks(n=1024, base=((0.66, 0.48, 0.32), (0.80, 0.62, 0.42)), boards=8):
    """Boards along u (each n/boards tall), grain along u, dark seams; the boards' ends staggered."""
    v = np.arange(n)[:, None] / n
    grain = fbm(n, n, (1.5, 4.0), (0.5, 0.5))
    grain = np.repeat(pnoise(n, n // 16, 1.2), 16, axis=1)[:, :n] * 0.6 + grain * 0.4
    tone = np.zeros((n, n))
    rows = (v[:, 0] * boards).astype(int)
    rng = np.random.default_rng(3)
    shade = rng.uniform(-0.12, 0.12, boards)
    tone += shade[rows][:, None]
    c = mix(base[0], base[1], np.clip(grain + tone, 0, 1))
    seam = ((v * boards) % 1.0 < 0.02) | ((v * boards) % 1.0 > 0.985)
    c[np.broadcast_to(seam, (n, n))] *= 0.55
    for r in range(boards):                            # one butt joint per board, staggered
        x = int(((r * 0.37) % 1.0) * n)
        y0, y1 = int(r * n / boards), int((r + 1) * n / boards)
        c[y0:y1, max(0, x - 2):x + 2] *= 0.6
    return np.clip(c, 0, 0.8)


def siding(n=512):
    """Painted vertical boards, pastel mint, a little worn."""
    c = planks(n, base=((0.60, 0.80, 0.74), (0.70, 0.88, 0.80)), boards=6)
    return np.transpose(c, (1, 0, 2)).copy()


def shingles(n=512, rows=8):
    v = np.arange(n)[:, None] / n
    u = np.arange(n)[None, :] / n
    r = (v * rows).astype(int)
    off = (r % 2) * 0.5 / 4
    cell = ((u + off) * 4) % 1.0
    t = fbm(n, n, (6, 2), (0.6, 0.4))
    c = mix((0.78, 0.40, 0.42), (0.90, 0.56, 0.54), t)
    edge = ((v * rows) % 1.0 > 0.88) | (cell < 0.03)
    c[np.broadcast_to(edge, (n, n))] *= 0.62
    return np.clip(c, 0, 0.8)


def asphalt(n=1024):
    t = fbm(n, n, (60, 6, 1.0), (0.3, 0.3, 0.4))
    c = mix((0.24, 0.24, 0.27), (0.38, 0.38, 0.41), t)
    peb = pnoise(n, n, 0.8) > 0.88
    c[peb] = c[peb] * 0.5 + np.array([0.58, 0.56, 0.58]) * 0.5
    return c


def concrete(n=512):
    t = fbm(n, n, (30, 4), (0.6, 0.4))
    return mix((0.70, 0.68, 0.66), (0.82, 0.80, 0.77), t)


def plaster(n=512, a=(0.86, 0.74, 0.70), b=(0.94, 0.84, 0.78)):
    t = fbm(n, n, (40, 10, 2), (0.5, 0.3, 0.2))
    return mix(a, b, t)


def foliage(n=512, a=(0.86, 0.52, 0.72), b=(0.98, 0.74, 0.86)):
    t = fbm(n, n, (10, 3), (0.6, 0.4))
    return mix(a, b, t ** 0.8)


def sign_board(text_lines, n=(1024, 410), bg=(0.92, 0.86, 0.66), fg=(0.30, 0.20, 0.14), arrow=None):
    w, h = n
    base = planks(w, base=((bg[0] * 0.92, bg[1] * 0.92, bg[2] * 0.92), bg), boards=4)[:h, :w]
    im = Image.fromarray((np.clip(base, 0, 1) * 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    f = font(int(h * 0.42 / max(1, len(text_lines)) * 1.6))
    room = w - h * 0.8 - 70 if arrow else w - 60                      # the text fits beside the arrow
    while max(d.textlength(t, font=f) for t in text_lines) > room and f.size > 12:
        f = font(f.size - 4)
    y = h * 0.5 - len(text_lines) * f.size * 0.6
    for line in text_lines:
        tw = d.textlength(line, font=f)
        x0, x1 = (h * 0.8 if arrow == "left" else 30), (w - h * 0.8 if arrow == "right" else w - 30)
        x = (x0 + x1 - tw) / 2
        d.text((x, y), line, fill=tuple(int(v * 255) for v in fg), font=f)
        y += f.size * 1.15
    if arrow:
        cx = w - h * 0.45 if arrow == "right" else h * 0.45
        s = 1 if arrow == "right" else -1
        d.polygon([(cx + s * h * 0.25, h / 2), (cx - s * h * 0.1, h * 0.25), (cx - s * h * 0.1, h * 0.75)], fill=tuple(int(v * 255) for v in fg))
    d.rectangle([4, 4, w - 5, h - 5], outline=tuple(int(v * 200) for v in fg), width=6)
    return np.asarray(im, float) / 255


def more_to_come(n=(1024, 160)):
    w, h = n
    im = Image.new("RGB", (w, h), (238, 214, 120))
    d = ImageDraw.Draw(im)
    f = font(int(h * 0.62))
    t = "MORE TO COME"
    tw = d.textlength(t, font=f)
    d.text(((w - tw) / 2, h * 0.14), t, fill=(150, 60, 90), font=f)
    d.rectangle([3, 3, w - 4, h - 4], outline=(150, 60, 90), width=8)
    return np.asarray(im, float) / 255


def fake_door(n=(256, 512)):
    w, h = n
    base = planks(512, base=((0.48, 0.30, 0.34), (0.58, 0.38, 0.40)), boards=5)
    base = np.transpose(base, (1, 0, 2))[:h, :w].copy()
    im = Image.fromarray((base * 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for (x0, y0, x1, y1) in ((30, 40, w - 30, h * 0.45), (30, h * 0.52, w - 30, h - 40)):
        d.rectangle([x0, y0, x1, y1], outline=(90, 50, 60), width=8)
    d.ellipse([w - 60, h * 0.5 - 14, w - 32, h * 0.5 + 14], fill=(220, 190, 90))
    return np.asarray(im, float) / 255


def window_lit(n=(256, 256)):
    """A warm window, four panes; it is also the emission (Window_Lit: on at night)."""
    w, h = n
    yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
    glow = 1.0 - 0.35 * ((xx - 0.5) ** 2 + (yy - 0.55) ** 2) * 4
    c = mix((0.85, 0.62, 0.38), (1.0, 0.86, 0.60), np.clip(glow, 0, 1))
    frame = (xx < 0.07) | (xx > 0.93) | (yy < 0.07) | (yy > 0.93) | (abs(xx - 0.5) < 0.03) | (abs(yy - 0.5) < 0.03)
    c[frame] = (0.92, 0.92, 0.88)
    return c


def puzzle_board(n=(1024, 560)):
    """The tree house's puzzle: a carved board of nine symbols in three rows (the page decides what they mean)."""
    w, h = n
    base = planks(1024, base=((0.55, 0.38, 0.26), (0.68, 0.50, 0.34)), boards=6)[:h, :w]
    im = Image.fromarray((base * 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    ink = (60, 36, 26)
    w = h * 1.0                                                     # the symbols on a square grid, centred
    ox = (n[0] - w) / 2
    cols, rows = 3, 3
    for r in range(rows):
        for c in range(cols):
            cx, cy = ox + (c + 0.5) * w / cols, (r + 0.5) * h / rows * 0.9 + h * 0.05
            s = w / cols * 0.3
            k = r * cols + c
            if k == 0:
                d.ellipse([cx - s, cy - s, cx + s, cy + s], outline=ink, width=10)
            elif k == 1:
                d.polygon([(cx, cy - s), (cx + s, cy + s), (cx - s, cy + s)], outline=ink, width=10)
            elif k == 2:
                d.rectangle([cx - s, cy - s, cx + s, cy + s], outline=ink, width=10)
            elif k == 3:
                d.line([(cx - s, cy), (cx + s, cy)], fill=ink, width=10)
                d.line([(cx, cy - s), (cx, cy + s)], fill=ink, width=10)
            elif k == 4:
                pts = [(cx + s * np.cos(a), cy + s * np.sin(a)) for a in np.linspace(-np.pi / 2, 1.5 * np.pi, 6)[:-1]]
                d.polygon(pts, outline=ink, width=10)
            elif k == 5:
                d.arc([cx - s, cy - s, cx + s, cy + s], 200, 520, fill=ink, width=10)
            elif k == 6:
                for i in range(3):
                    d.line([(cx - s, cy - s + i * s), (cx + s, cy - s + i * s)], fill=ink, width=8)
            elif k == 7:
                d.ellipse([cx - s * 0.3, cy - s * 0.3, cx + s * 0.3, cy + s * 0.3], fill=ink)
                d.ellipse([cx - s, cy - s, cx + s, cy + s], outline=ink, width=6)
            else:
                d.line([(cx - s, cy - s), (cx + s, cy + s)], fill=ink, width=10)
                d.line([(cx + s, cy - s), (cx - s, cy + s)], fill=ink, width=10)
    d.rectangle([8, 8, n[0] - 9, h - 9], outline=ink, width=12)
    return np.asarray(im, float) / 255


def door_wood(n=512):
    return np.transpose(planks(n, base=((0.56, 0.36, 0.30), (0.68, 0.46, 0.36)), boards=5), (1, 0, 2)).copy()


def hopscotch(n=(512, 1024)):
    w, h = n
    im = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(im)
    f = font(int(w * 0.22))
    cells = [(1, 0.5, 0), (2, 0.5, 1), (3, 0.5, 2), (4, 0.25, 3), (5, 0.75, 3), (6, 0.5, 4), (7, 0.25, 5), (8, 0.75, 5)]
    ch = h / 6
    paint = (240, 240, 232)
    for k, cx, r in cells:
        cw = w / 2 if cx != 0.5 else w / 2
        x0 = cx * w - cw / 2
        y0 = h - (r + 1) * ch
        d.rectangle([x0 + 6, y0 + 6, x0 + cw - 6, y0 + ch - 6], outline=paint, width=14)
        t = str(k)
        tw = d.textlength(t, font=f)
        d.text((x0 + cw / 2 - tw / 2, y0 + ch * 0.18), t, fill=paint, font=f)
    return np.asarray(im, float) / 255


ALL = {
    "grass": grass, "hedge": hedge, "bark": bark, "deck": planks, "siding": siding, "shingles": shingles, "asphalt": asphalt,
    "concrete": concrete, "plaster": plaster,
    "plaster_blue": lambda: plaster(a=(0.66, 0.78, 0.90), b=(0.76, 0.86, 0.95)),
    "plaster_yellow": lambda: plaster(a=(0.92, 0.84, 0.58), b=(0.97, 0.90, 0.68)),
    "leaf_pink": foliage, "leaf_mint": lambda: foliage(a=(0.46, 0.80, 0.62), b=(0.66, 0.92, 0.76)),
    "leaf_lilac": lambda: foliage(a=(0.68, 0.58, 0.88), b=(0.82, 0.74, 0.96)),
    "sign_forest": lambda: sign_board(["TO THE FOREST"], arrow="right"),
    "sign_lot": lambda: sign_board(["BACK TO THE LOT"], arrow="left"),
    "sign_back": lambda: sign_board(["THE WAY BACK"], arrow="left"),
    "more_to_come": more_to_come, "fake_door": fake_door, "window_lit": window_lit, "puzzle_board": puzzle_board, "door_wood": door_wood,
    "hopscotch": hopscotch,
}

if __name__ == "__main__":
    names = sys.argv[1:] or list(ALL)
    for nm in names:
        save(nm, ALL[nm]())
