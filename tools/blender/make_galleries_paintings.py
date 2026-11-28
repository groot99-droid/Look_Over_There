"""The pictures in the museum hall's frames (scene `galleries`): one atlas of pictures of the game's other scenes, cropped to each frame's opening.

    python tools/blender/make_galleries_paintings.py --views <folder of the store and exterior views>

Sources: the review stills of the built scenes (docs/renders/<scene>/*.jpg for apartment, laboratory, factory_floor, main_floor and galleries_wing; not
the hall itself) and the views of the store floors and the exterior that tools/blender/render_galleries_views.py renders (<scene>_<k>.jpg). Every frame
of tools/blender/galleries_frames.py gets one; no picture repeats within a hang (a bay of a long wall, the north wall, the door wall), and the large works
get the best views (HERO, in order). Writes blender/textures/galleries/paintings_atlas.jpg and paintings_atlas.json (per frame: the picture and its UV
rectangle, Blender's v up), which build_galleries.py reads.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import galleries_frames as gf  # noqa: E402

STILL_SCENES = ["apartment", "laboratory", "factory_floor", "main_floor", "galleries_wing"]
ATLAS = 2048
PAD = 10                         # px of edge colour round each picture (mip and bilinear bleed; the canvas reaches 1.2 cm, about 4 px, past it)
OUT = ROOT / "blender/textures/galleries"
# the best pictures first: the large works take them in this order (ids: <scene>/<still> or the view's file stem); every other picture follows
HERO = ["L4_08", "L1_02", "factory_floor/2_wide", "B1_01", "main_floor/2_wide", "L2_05", "laboratory/2_wide", "Exterior_07", "galleries_wing/2_wide",
        "apartment/2_wide", "L3_00", "L4_04", "L1_07", "B1_03", "L2_00", "L4_09", "factory_floor/1_arrival", "main_floor/1_arrival", "laboratory/1_arrival",
        "galleries_wing/1_arrival", "apartment/1_arrival", "Exterior_05"]
args = sys.argv[1:]


def arg(name, default=None):
    return args[args.index(name) + 1] if name in args else default


def sources(views):
    pics = {}
    for s in STILL_SCENES:
        for p in sorted((ROOT / "docs/renders" / s).glob("*.jpg")):
            pics[f"{s}/{p.stem}"] = p
    for p in sorted(Path(views).glob("*.jpg")):
        pics[p.stem] = p
    return pics


def levelled(im):
    """A picture on a wall at night reads only if it is not too dark: lift it so its 98th percentile luminance sits at 0.92 (at most x 1.8)."""
    a = np.asarray(im.convert("RGB"), np.float32) / 255
    lum = a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    k = min(1.8, max(1.0, 0.92 / max(float(np.percentile(lum, 98)), 1e-3)))
    return Image.fromarray((np.clip(a * k, 0, 1) * 255 + 0.5).astype(np.uint8))


def crop(im, aspect, slot):
    """The part of `im` with the given aspect (w / h); `slot` 0, 1, 2 takes the middle, left or right (top, bottom) of what is cut away."""
    w, h = im.size
    pos = [0.5, 0.25, 0.75][slot % 3]
    if w / h > aspect:
        cw = round(h * aspect)
        x0 = round((w - cw) * pos)
        return im.crop((x0, 0, x0 + cw, h))
    ch = round(w / aspect)
    y0 = round((h - ch) * [0.5, 0.35, 0.65][slot % 3])
    return im.crop((0, y0, w, y0 + ch))


def assign(frames, ids):
    """Per frame a picture id: the large works (by area) take the HERO order first; within a hang no repeat, and the two walls of a bay do not share one;
    among the allowed ones the least used goes first."""
    hero = [i for i in HERO if i in ids] + [i for i in ids if i not in HERO]
    used = {i: 0 for i in ids}
    groups = {}
    for k, f in enumerate(frames):
        groups.setdefault(f[7], []).append(k)
    order = sorted(range(len(frames)), key=lambda k: -(gf.opening(frames[k])[0] * gf.opening(frames[k])[1]))
    pick = {}
    for k in order:
        g = frames[k][7]
        twin = ("-x" if g.startswith("+x") else "+x") + g[2:] if g[:2] in ("+x", "-x") else None
        taken = {pick[j] for j in groups[g] if j in pick} | ({pick[j] for j in groups.get(twin, []) if j in pick} if twin else set())
        cand = [i for i in hero if i not in taken]
        best = min(cand, key=lambda i: (used[i], hero.index(i)))
        pick[k] = best
        used[best] += 1
    return pick, used


def main():
    pics = sources(arg("--views"))
    k = json.loads((ROOT / "blender/layout/galleries.json").read_text())["constants"]
    frames = gf.frames(k)
    pick, used = assign(frames, list(pics))
    sizes = [gf.opening(f) for f in frames]
    slot = {}
    for k_, f in enumerate(frames):                     # the n-th use of a picture takes the n-th crop
        slot[k_] = sum(1 for j in range(k_) if pick[j] == pick[k_])
    # the largest density (px per m) at which a shelf packing of every picture fits the atlas
    order = sorted(range(len(frames)), key=lambda i: -sizes[i][1])

    def pack(D):
        x = y = row = 0
        pos = {}
        for i in order:
            w, h = round(sizes[i][0] * D) + 2 * PAD, round(sizes[i][1] * D) + 2 * PAD
            if x + w > ATLAS:
                x, y, row = 0, y + row, 0
            if y + h > ATLAS:
                return None
            pos[i] = (x, y, w, h)
            x += w
            row = max(row, h)
        return pos
    D = 600
    while not pack(D):
        D -= 5
    pos = pack(D)
    atlas = Image.new("RGB", (ATLAS, ATLAS), (40, 36, 32))
    cache = {}
    out = []
    for i, f in enumerate(frames):
        pid = pick[i]
        if pid not in cache:
            cache[pid] = levelled(Image.open(pics[pid]))
        x, y, w, h = pos[i]
        im = crop(cache[pid], sizes[i][0] / sizes[i][1], slot[i]).resize((w - 2 * PAD, h - 2 * PAD), Image.LANCZOS)
        big = Image.new("RGB", (w, h))
        a = np.asarray(im)
        big.paste(Image.fromarray(np.pad(a, ((PAD, PAD), (PAD, PAD), (0, 0)), mode="edge")), (0, 0))
        atlas.paste(big, (x, y))
        u0, u1 = (x + PAD) / ATLAS, (x + w - PAD) / ATLAS
        v1, v0 = 1 - (y + PAD) / ATLAS, 1 - (y + h - PAD) / ATLAS
        out.append({"frame": i, "group": f[7], "picture": pid, "crop": slot[i], "opening_m": [round(sizes[i][0], 3), round(sizes[i][1], 3)],
                    "uv": [round(u0, 6), round(v0, 6), round(u1, 6), round(v1, 6)]})
    OUT.mkdir(parents=True, exist_ok=True)
    atlas.save(OUT / "paintings_atlas.jpg", quality=90, optimize=True)
    (OUT / "paintings_atlas.json").write_text(json.dumps({"size": ATLAS, "px_per_m": D, "frames": out}, indent=1) + "\n")
    print(f"ATLAS {len(frames)} pictures at {D} px/m, {len(set(pick.values()))} different of {len(pics)} sources;",
          "uses:", sorted(used.items(), key=lambda t: -t[1])[:6])


main()
