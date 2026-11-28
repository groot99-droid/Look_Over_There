"""Dresses and lights the hotel's seven anomaly maze rooms, `maze_01` to `maze_07` (docs/BLENDER_AREAS.md, section 1, step 2;
docs/renders/maze_01/README.md). One script for all seven: they share the method, the materials, the textures and the meshes, and each gets its
own wrongness and its own night bake.

    blender -b --factory-startup --python tools/blender/build_hotel_mazes.py -- --scenes maze_01,...,maze_07 --stage all [--work <dir>]
    blender -b --factory-startup blender/scenes/<scene>.blend --python tools/blender/build_hotel_mazes.py -- --scenes <scene> --stage bake|export|reexport|axes|check|render
    python tools/blender/build_hotel_mazes.py --pack <scene> [--work <dir>]       (no Blender: WebP lightmaps and textures -> world/)
    python tools/blender/build_hotel_mazes.py --skin [scene ...]                    (no Blender: the seen shell and the dressing slots, printed)

Stages: art (the layout objects from the greybox, the art, the lights; saves blender/scenes/<scene>.blend) -> bake (the seen faces and the merged
props on fixed lightmap PAGES, Cycles, OIDN, 8-bit PNGs in the work folder) -> export (the GLB to the work folder; the layout through
tools/blender/export_scene.py, which must write the greybox's file unchanged) -> axes (the marker-cube check) -> check (tools/blender/check_layout.py)
-> render (docs/renders/<scene>/1_arrival, 2_wide, 3_detail.jpg and plan.jpg). `all` runs them in that order; `--scenes` takes several, built one
after the other in one Blender (the file is reset between them). `preview` is art then render at low samples, no bake.

The layout is the greybox's, unchanged (tools/blender/build_hotel_greybox.py, maze(k)): every COL_ box, DoorLeaf_, Link_/Arrive_, Marker_ and Spot_
is made from its model with the same names and numbers, so the walls, the one-way doors and the puzzle spot stay exactly where they are; the
puzzle's moving parts are the page's. What is seen of the shell is skin(): only the faces of those boxes that look into the air. Everything the
dressing adds is flush with a wall (5 cm at most), overhead (above 1.8 m), lower than 0.2 m, or a passable decor_ piece, so no collider is needed.

The seven wrongnesses, all in the hotel's own materials (floor 1's carpet, wallcovering, wood and tile; the repo's CC0 textures):
  1 too-small doors  the motel corridor's finish, a door in every bay, each a little too small, every one numbered 101; sconces over them
  2 the dry pool      white tile floor to ceiling, a blue band where the water line would be, depth marks, grab rails, drains; no water
  3 the wallpaper     green carpet and a damask paper whose pattern repeats far too often; the same print hung in every bay
  4 the laundry       identical built-in washers, three across and two high in every bay, every one No. 7; tube lights, one dead
  5 the ballroom      parquet, wainscot, mirrors and chandeliers, and no furniture at all: only pale marks where the tables stood
  6 the guest room    one room's four walls (bed, window, door 214, TV) repeated in the same order round every turn of the maze
  7 the stairwell     painted block, handrails, fire doors to the same floor, EXIT signs that disagree, and stairs hung upside down from
                      the ceiling that climb into the wall
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import build_hotel_greybox as GB  # noqa: E402

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


SCENES = tuple(f"maze_{k:02d}" for k in range(1, 8))
A, H = 8.0, 3.0                 # the maze's half size and height (greybox maze())
FRONT = 0.004
PROUD = 0.045                   # the most a wall piece may stand out (the layout check allows 5 cm)

# ================================================================ the themes
THEME = {
    1: {"title": "The corridor of small doors", "floor": "Carpet_Field", "ceiling": "Ceiling_Popcorn", "jamb": "Door_Jamb",
        "bands": [(0.9, "Wall_Lower"), (9.0, "Wall_Upper")], "mood": "warm amber sconces, a motel corridor at 3 a.m."},
    2: {"title": "The dry pool", "floor": "Tile_Floor_Pool", "ceiling": "Tile_Ceiling", "jamb": "Tile_Wall",
        "bands": [(1.1, "Tile_Wall"), (1.25, "Tile_Band"), (9.0, "Tile_Wall")], "mood": "cold, even, cyan-white panel light"},
    3: {"title": "The wallpaper that repeats", "floor": "Carpet_Green", "ceiling": "Ceiling_Plaster", "jamb": "Door_Jamb",
        "bands": [(0.9, "Dado_Paint"), (9.0, "Paper_Repeat")], "mood": "sickly yellow-green ceiling domes"},
    4: {"title": "The laundry of identical machines", "floor": "Vinyl_Floor", "ceiling": "Ceiling_Tile", "jamb": "Jamb_Steel",
        "bands": [(1.2, "Block_Lower"), (9.0, "Paint_Upper")], "mood": "cold blue-white tubes, some dead"},
    5: {"title": "The ballroom with no furniture", "floor": "Parquet", "ceiling": "Ceiling_Plaster", "jamb": "Door_Jamb",
        "bands": [(1.0, "Wainscot"), (9.0, "Plaster_Cream")], "mood": "dim gold chandeliers"},
    6: {"title": "The guest room in a loop", "floor": "Carpet_Room", "ceiling": "Ceiling_Popcorn", "jamb": "Door_Jamb",
        "bands": [(9.0, "Wall_Room")], "mood": "rose bedside lamps, the ceiling dark"},
    7: {"title": "The stairs that end in a wall", "floor": "Stair_Concrete", "ceiling": "Stair_Ceiling", "jamb": "Jamb_Steel",
        "bands": [(1.2, "Block_Lower"), (9.0, "Block_Upper")], "mood": "red emergency bulkheads, green EXIT signs"},
}


def kof(sc):
    return int(sc.split("_")[1])


def grid(sc):
    k = kof(sc)
    n = 8 if k % 2 else 7
    return n, 2 * A / n


# ================================================================ the seen shell (pure Python)
def model(sc):
    return GB.build(sc)


def colliders(M):
    return [{"name": b["name"], "min": list(b["min"]), "max": list(b["max"])} for b in M.boxes if b["col"]]


def doors_z(M):
    """{door: (x of the wall's inner face, z of the opening's middle)} for entry and way_on."""
    out = {}
    for d in M.doors:
        out[d["name"][len("DoorLeaf_"):]] = (d["hinge"][0], d["hinge"][2] + GB.DOOR_W / 2)
    return out


def air(M):
    dz = doors_z(M)
    T = GB.T
    out = [{"region": "maze", "min": [-A, 0.0, -A], "max": [A, H, A]}]
    xe, ze = dz["entry"]
    xo, zo = dz["way_on"]
    out.append({"region": "doorhole", "min": [-A - T, 0.0, ze - GB.DOOR_W / 2], "max": [-A, GB.DOOR_H, ze + GB.DOOR_W / 2]})
    out.append({"region": "doorhole", "min": [A, 0.0, zo - GB.DOOR_W / 2], "max": [A + T, GB.DOOR_H, zo + GB.DOOR_W / 2]})
    return out


def _inside(p, b, e=1e-4):
    return all(b["min"][i] + e < p[i] < b["max"][i] - e for i in range(3))


def _within(p, b, e=1e-7):
    return all(b["min"][i] - e <= p[i] <= b["max"][i] + e for i in range(3))


def _band_break(a, k, v, splits_y):
    return a != 1 and k == 1 and any(abs(v - y) < 1e-9 for y in splits_y)


def skin(cols, airs, splits_y=()):
    """Every collider face that looks into the air, as merged rectangles (floor 1's skin, tools/blender/build_hotel_floor1.py's method):
    [{coll, axis, side, p, bi, ci, b: (u0, u1), c: (v0, v1), region}]."""
    everything = cols + list(airs)
    out = []
    for C in sorted(cols, key=lambda c: c["name"]):
        for a in range(3):
            bi, ci = [i for i in range(3) if i != a]
            for side in (-1, 1):
                p = C["max"][a] if side > 0 else C["min"][a]
                cuts = {bi: {C["min"][bi], C["max"][bi]}, ci: {C["min"][ci], C["max"][ci]}}
                for o in everything:
                    if o is C or not (o["min"][a] - 0.01 <= p <= o["max"][a] + 0.01):
                        continue
                    for k in (bi, ci):
                        for v in (o["min"][k], o["max"][k]):
                            if C["min"][k] < v < C["max"][k]:
                                cuts[k].add(v)
                if a != 1:
                    for y in splits_y:
                        if C["min"][1] < y < C["max"][1]:
                            cuts[1].add(y)
                ub, uc = sorted(cuts[bi]), sorted(cuts[ci])
                cells = {}
                for i in range(len(ub) - 1):
                    for j in range(len(uc) - 1):
                        if ub[i + 1] - ub[i] < 1e-6 or uc[j + 1] - uc[j] < 1e-6:
                            continue
                        c = [0.0, 0.0, 0.0]
                        c[a], c[bi], c[ci] = p, (ub[i] + ub[i + 1]) / 2, (uc[j] + uc[j + 1]) / 2
                        f = list(c)
                        f[a] += side * FRONT
                        reg = next((X["region"] for X in airs if _within(f, X)), None)
                        if reg is None or any(_inside(f, o) for o in cols if o is not C):
                            continue
                        dup = False
                        for o in cols:
                            if o is C or o["name"] > C["name"]:
                                continue
                            q = o["max"][a] if side > 0 else o["min"][a]
                            if abs(q - p) < 1e-6 and o["min"][bi] - 1e-6 <= c[bi] <= o["max"][bi] + 1e-6 and o["min"][ci] - 1e-6 <= c[ci] <= o["max"][ci] + 1e-6:
                                dup = True
                                break
                        if not dup:
                            cells[(i, j)] = reg
                used = set()
                for (i, j) in sorted(cells, key=lambda t: (t[1], t[0])):
                    if (i, j) in used:
                        continue
                    reg = cells[(i, j)]
                    i1 = i
                    while (i1 + 1, j) in cells and (i1 + 1, j) not in used and cells[(i1 + 1, j)] == reg and not _band_break(a, bi, ub[i1 + 1], splits_y):
                        i1 += 1
                    j1 = j
                    while all((k, j1 + 1) in cells and (k, j1 + 1) not in used and cells[(k, j1 + 1)] == reg for k in range(i, i1 + 1)) \
                            and not _band_break(a, ci, uc[j1 + 1], splits_y):
                        j1 += 1
                    for k in range(i, i1 + 1):
                        for m in range(j, j1 + 1):
                            used.add((k, m))
                    out.append({"coll": C["name"], "axis": a, "side": side, "p": p, "bi": bi, "ci": ci,
                                "b": (ub[i], ub[i1 + 1]), "c": (uc[j], uc[j1 + 1]), "region": reg})
    return out


def quad_points(q):
    a, bi, ci, p = q["axis"], q["bi"], q["ci"], q["p"]
    (b0, b1), (c0, c1) = q["b"], q["c"]
    pts = []
    for bb, cc in ((b0, c0), (b1, c0), (b1, c1), (b0, c1)):
        v = [0.0, 0.0, 0.0]
        v[a], v[bi], v[ci] = p, bb, cc
        pts.append(v)
    return pts


def area(q):
    return (q["b"][1] - q["b"][0]) * (q["c"][1] - q["c"][0])


def vrange(q):
    """A vertical quad's (y0, y1) and (run0, run1) along its wall."""
    return (q["b"], q["c"]) if q["axis"] == 0 else (q["c"], q["b"])


def splits(sc):
    return tuple(y for y, _ in THEME[kof(sc)]["bands"] if y < H)


def scene_skin(sc):
    M = model(sc)
    return skin(colliders(M), air(M), splits(sc)), M


def quad_material(sc, q):
    th = THEME[kof(sc)]
    if q["region"] == "doorhole":
        return "Threshold" if (q["axis"] == 1 and q["side"] > 0) else th["jamb"]
    if q["axis"] == 1:
        return th["floor"] if q["side"] > 0 else th["ceiling"]
    y0 = vrange(q)[0][0]
    for top, m in th["bands"]:
        if y0 < top - 1e-6:
            return m
    return th["bands"][-1][1]


def faces(sc):
    """The maze's wall faces as a walker sees them between junctions, from the skin: [(axis 'x'|'z', plane, sign, run0, run1)], each the band
    that holds eye height, merged along its run (the wall finish's band cuts are vertical only)."""
    q, M = scene_skin(sc)
    out = set()
    for x in q:
        if x["axis"] == 1 or x["region"] != "maze":
            continue
        (y0, y1), (r0, r1) = vrange(x)
        if not (y0 <= 1.5 <= y1):
            continue
        out.add(("x" if x["axis"] == 0 else "z", round(x["p"], 4), x["side"], round(r0, 4), round(r1, 4)))
    # merge touching runs on the same plane
    merged = []
    for key in sorted({(a, p, s) for a, p, s, _, _ in out}):
        runs = sorted((r0, r1) for a, p, s, r0, r1 in out if (a, p, s) == key)
        cur = list(runs[0])
        for r0, r1 in runs[1:]:
            if r0 <= cur[1] + 1e-6:
                cur[1] = max(cur[1], r1)
            else:
                merged.append((*key, *cur))
                cur = [r0, r1]
        merged.append((*key, *cur))
    return merged


def bays(sc):
    """Dressing slots: one per cell edge along every wall face, centred on its cell, (pitch / 2 - 0.16) either side: [(face index, a, half)]."""
    n, p = grid(sc)
    hw = p / 2 - 0.16
    centres = [-A + (i + 0.5) * p for i in range(n)]
    out = []
    for fi, (ax, pl, s, r0, r1) in enumerate(faces(sc)):
        for cc in centres:
            if cc - hw >= r0 - 1e-6 and cc + hw <= r1 + 1e-6:
                out.append((fi, round(cc, 4), round(hw, 4)))
    return out


def cells(sc):
    """Every cell's middle (x, z), except the middle room's four cells in the odd mazes (that room gets one fitting at its middle)."""
    n, p = grid(sc)
    out = []
    c = n // 2 - 1
    for i in range(n):
        for j in range(n):
            if kof(sc) % 2 == 1 and i in (c, c + 1) and j in (c, c + 1):
                continue
            out.append((round(-A + (i + 0.5) * p, 4), round(-A + (j + 0.5) * p, 4)))
    return out


def summary(sc):
    q, M = scene_skin(sc)
    by = {}
    for x in q:
        m = quad_material(sc, x)
        n, a = by.get(m, (0, 0.0))
        by[m] = (n + 1, a + area(x))
    print(f"SKIN {sc} ({THEME[kof(sc)]['title']}): {len(q)} quads, {sum(area(x) for x in q):.1f} m2; {len(faces(sc))} wall faces, "
          f"{len(bays(sc))} bays, {len(cells(sc))} cells")
    for m, (n, a) in sorted(by.items()):
        print(f"  {m:18s} {n:4d} quads {a:7.1f} m2")


# ================================================================ paths
MARGIN_PX = 8
TEXDIR = ROOT / "blender/textures"
STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 1024, int)
DEVICE = arg("--device", "auto")
PAGES = {sc: [2048, 2048] for sc in SCENES}
WHITE_CAP = 12.0
SHOULDER = (70.0, 2.5)
SCENE = None
K = None


def work():
    p = Path(arg("--work", str(Path(os.environ.get("TEMP", tempfile.gettempdir())) / "farway_hotel_mazes")))
    p.mkdir(parents=True, exist_ok=True)
    return p


def world_json(sc):
    return ROOT / "world" / f"{sc}.json"


def glb_path(sc):
    return ROOT / "world" / f"{sc}.glb"


def blend_path(sc):
    return ROOT / f"blender/scenes/{sc}.blend"


def stills_dir(sc):
    return ROOT / f"docs/renders/{sc}"


def lm_url(sc, n):
    return f"world/lightmaps/{sc}_{n}.webp"


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
    elif "--skin" in args:
        for s in [a for a in args if a.startswith("maze_")] or SCENES:
            summary(s)
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


# ---------------------------------------------------------------- generated images (own work: numpy, fixed seeds; floor 1's where shared)
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


def gen_field():
    """Floor 1's alcove carpet: maroon with small gold flecks, 1 m square."""
    Hh = W = 512
    rng = np.random.default_rng(102)
    n = vnoise(Hh, W, rng, 5, 4)
    fine = vnoise(Hh, W, rng, 3, 96)
    img = np.broadcast_to(col(90, 30, 36), (Hh, W, 3)).copy()
    img = lerp(img, col(140, 104, 54), smooth(0.83, 0.9, fine) * 0.8)
    img *= (0.85 + 0.3 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_green():
    """Floor 2's green: a dark bottle-green loop pile with a faint gold trellis, 1 m square."""
    Hh = W = 512
    rng = np.random.default_rng(301)
    t = (np.arange(Hh) + 0.5) / Hh
    Y, X = np.meshgrid(t, t, indexing="ij")
    img = np.broadcast_to(col(34, 70, 44), (Hh, W, 3)).copy()
    P = 0.25
    lx, ly = np.mod(X, P) - P / 2, np.mod(Y, P) - P / 2
    d = np.abs(lx) + np.abs(ly)
    img = lerp(img, col(110, 98, 52), smooth(0.01, 0.004, np.abs(d - 0.1)) * 0.7)
    n = vnoise(Hh, W, rng, 5, 4)
    fine = vnoise(Hh, W, rng, 3, 96)
    img *= (0.84 + 0.3 * fine)[..., None]
    img *= (0.88 + 0.24 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_room_carpet():
    """Floor 1's room carpet: brown and rust 1970s loops on tan, 2 m square."""
    Hh = W = 1024
    rng = np.random.default_rng(103)
    t = (np.arange(Hh) + 0.5) / Hh * 2.0
    Y, X = np.meshgrid(t, t, indexing="ij")
    img = np.broadcast_to(col(112, 80, 52), (Hh, W, 3)).copy()
    P = 0.25
    lx, ly = np.mod(X, P) - P / 2, np.mod(Y, P) - P / 2
    r = np.sqrt(lx ** 2 + ly ** 2)
    img = lerp(img, col(136, 66, 38), smooth(0.012, 0.004, np.abs(r - 0.07)))
    sq = np.maximum(np.abs(lx), np.abs(ly))
    img = lerp(img, col(150, 116, 56), smooth(0.008, 0.003, np.abs(sq - 0.118)) * 0.8)
    n = vnoise(Hh, W, rng, 6, 4)
    fine = vnoise(Hh, W, rng, 3, 128)
    img *= (0.84 + 0.3 * fine)[..., None]
    img *= (0.88 + 0.24 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_wallcover():
    """Floor 1's vinyl wallcovering: the repo's painted plaster with faint vertical stripes, 1 m square."""
    src = load_pixels("main_floor/wall_paint_diff.jpg")
    Hh, W = src.shape[:2]
    rng = np.random.default_rng(105)
    x = (np.arange(W) + 0.5) / W
    stripe = 1 - 0.035 * (np.mod(x, 0.06) < 0.03) - 0.06 * smooth(0.004, 0.0015, np.abs(np.mod(x, 0.3) - 0.15))
    grain = vnoise(Hh, W, rng, 2, 160)
    return np.clip(src * stripe[None, :, None] * (0.95 + 0.1 * grain)[..., None], 0, 1)


def gen_block():
    """Floor 1's stairwell block: 0.4 x 0.2 m blocks with mortar joints, 1.6 m square."""
    src = load_pixels("main_floor/wall_paint_diff.jpg")
    Hh, W = src.shape[:2]
    t = (np.arange(Hh) + 0.5) / Hh * 1.6
    Y, X = np.meshgrid(t, t, indexing="ij")
    row = np.floor(Y / 0.2)
    xo = X + (row % 2) * 0.2
    j = np.minimum(np.abs(np.mod(Y, 0.2)), np.abs(np.mod(Y, 0.2) - 0.2))
    j = np.minimum(j, np.minimum(np.abs(np.mod(xo, 0.4)), np.abs(np.mod(xo, 0.4) - 0.4)))
    return np.clip(src * (1 - 0.22 * smooth(0.008, 0.003, j))[..., None], 0, 1)


def gen_tile(seed=106, size=0.15, grout=(150, 146, 136), face=(226, 224, 214), span=0.9):
    """Floor 1's bathroom tiles: square tiles with grout, `span` m square."""
    Hh = W = 1024
    rng = np.random.default_rng(seed)
    t = (np.arange(Hh) + 0.5) / Hh * span
    Y, X = np.meshgrid(t, t, indexing="ij")
    gx = np.minimum(np.mod(X, size), size - np.mod(X, size))
    gy = np.minimum(np.mod(Y, size), size - np.mod(Y, size))
    g = np.minimum(gx, gy)
    tid = (np.floor(X / size) * 7 + np.floor(Y / size) * 13) % 6
    img = np.broadcast_to(col(*face), (Hh, W, 3)) * (0.9 + 0.02 * tid[..., None]) / 0.95
    img = lerp(img, col(*grout), smooth(0.003, 0.0012, g))
    n = vnoise(Hh, W, rng, 4, 4)
    img *= (0.94 + 0.08 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_damask():
    """The wallpaper that repeats too often: a mustard damask on olive whose motif repeats every 12 cm (a hotel paper's is about 50 cm). One image
    holds one repeat; the material tiles it 8.3 times a metre."""
    S = 256
    rng = np.random.default_rng(303)
    t = (np.arange(S) + 0.5) / S
    Y, X = np.meshgrid(t, t, indexing="ij")
    img = np.broadcast_to(col(92, 98, 58), (S, S, 3)).copy()
    for cx, cy in ((0.5, 0.5), (0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)):
        dx, dy = (X - cx) * 1.0, (Y - cy) * 0.8
        ang = np.arctan2(dy, dx)
        r = np.sqrt(dx ** 2 + dy ** 2)
        petal = 0.2 * (0.6 + 0.4 * np.cos(4 * ang)) * (0.8 + 0.2 * np.cos(8 * ang))
        img = lerp(img, col(176, 148, 70), smooth(petal, petal * 0.86, r))
        img = lerp(img, col(92, 98, 58), smooth(0.05, 0.035, np.abs(r - petal * 0.55)) * smooth(petal, petal * 0.8, r))
        img = lerp(img, col(190, 160, 80), smooth(0.03, 0.02, r))
    stem = smooth(0.012, 0.004, np.abs(X - 0.5 - 0.04 * np.sin(Y * 12.566)))
    img = lerp(img, col(150, 128, 62), stem * (np.abs(Y - 0.5) > 0.22))
    n = vnoise(S, S, rng, 3, 4)
    return np.clip(img * (0.92 + 0.1 * n)[..., None], 0, 1)


def gen_stain(seed, size=512, dark=False):
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


def gen_ghost():
    """Where a round banquet table stood: a paler, less worn disc on the parquet, soft edged (RGBA)."""
    S = 256
    rng = np.random.default_rng(305)
    t = (np.arange(S) + 0.5) / S * 2 - 1
    Y, X = np.meshgrid(t, t, indexing="ij")
    n = vnoise(S, S, rng, 4, 3)
    r = np.sqrt(X ** 2 + Y ** 2)
    a = smooth(0.95, 0.8, r + 0.04 * (n - 0.5)) * 0.13
    a = a + smooth(0.04, 0.0, np.abs(r - 0.86)) * 0.07
    rgb = np.broadcast_to(col(236, 206, 160), (S, S, 3))
    return np.concatenate([rgb, np.clip(a, 0, 1)[..., None]], axis=2)


def gen_prints():
    """Floor 1's four motel prints in one 2 x 2 atlas: a seascape, hills at dusk, a vase of flowers, soft bands."""
    Hh, W = 768, 1024
    img = np.zeros((Hh, W, 3))
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


def gen_grille():
    Hh = W = 128
    y = (np.arange(Hh) + 0.5) / Hh
    s = smooth(0.12, 0.06, np.abs(np.mod(y * 10, 1) - 0.5))
    img = np.ones((Hh, W, 3)) * col(200, 198, 190)
    img = lerp(img, col(30, 30, 30), np.broadcast_to(s[:, None], (Hh, W)))
    img[:6], img[-6:], img[:, :6], img[:, -6:] = col(210, 208, 200), col(210, 208, 200), col(210, 208, 200), col(210, 208, 200)
    return img


def gen_brushed():
    Hh = W = 256
    rng = np.random.default_rng(108)
    n = vnoise(Hh, W, rng, 3, 2)
    streak = np.repeat(vnoise(Hh, 8, rng, 3, 64), W // 8, axis=1)
    return np.clip((0.7 + 0.12 * streak + 0.08 * n)[..., None] * np.ones(3), 0, 1)


def gen_porthole():
    """A washer's door glass seen from outside: dark smoked glass, a pale crescent of reflection, and the same red sock pressed to it."""
    S = 256
    t = (np.arange(S) + 0.5) / S * 2 - 1
    Y, X = np.meshgrid(t, t, indexing="ij")
    r = np.sqrt(X ** 2 + Y ** 2)
    img = lerp(np.broadcast_to(col(40, 46, 50), (S, S, 3)), col(18, 20, 22), smooth(0.2, 1.0, r))
    img = lerp(img, col(140, 150, 156), smooth(0.08, 0.0, np.abs(r - 0.78)) * (X < -0.1) * 0.6)
    sock = np.exp(-(((X - 0.18) * np.cos(0.6) + (Y + 0.3) * np.sin(0.6)) / 0.32) ** 2 - (((Y + 0.3) * np.cos(0.6) - (X - 0.18) * np.sin(0.6)) / 0.11) ** 2)
    img = lerp(img, col(150, 30, 28), smooth(0.4, 0.6, sock))
    return np.clip(img, 0, 1)


GEN = {}


def mk_image(name, arr):
    h, w = arr.shape[:2]
    im = bpy.data.images.new(name, w, h, alpha=arr.shape[2] == 4)
    im.colorspace_settings.name = "sRGB"
    px = np.ones((h, w, 4), np.float32)
    px[..., :arr.shape[2]] = arr
    im.pixels.foreach_set(px.ravel())
    im.filepath_raw = f"//generated/{name}.png"
    im.file_format = "PNG"
    im.pack()
    GEN[name] = im
    return im


# ---------------------------------------------------------------- materials (the same set in all seven files; each GLB carries those it uses)
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
PARQ, PLASTER4, VINYL, CEILT, CONC = "galleries/herringbone_parquet_diff_1k.jpg", "galleries/plastered_wall_04_diff_1k.jpg", \
    "laboratory/floor_vinyl_diff.jpg", "laboratory/ceiling_tile_diff.jpg", "factory_floor/concrete_floor_diff.jpg"

# each maze's light: (colour, Cycles watts of its main fitting, the lamp shades' emissive colour and strength)
MOOD = {1: ((1.0, 0.72, 0.42), 55.0), 2: ((0.78, 0.93, 1.0), 70.0), 3: ((0.92, 0.95, 0.52), 45.0), 4: ((0.82, 0.9, 1.0), 60.0),
        5: ((1.0, 0.74, 0.4), 70.0), 6: ((1.0, 0.62, 0.55), 32.0), 7: ((1.0, 0.22, 0.12), 45.0)}


def make_materials():
    g = {k: mk_image(k, f()) for k, f in (
        ("gen_wallcover", gen_wallcover), ("gen_brushed", gen_brushed), ("gen_prints", gen_prints), ("gen_grille", gen_grille),
        ("gen_field", gen_field), ("gen_green", gen_green), ("gen_room_carpet", gen_room_carpet), ("gen_block", gen_block),
        ("gen_tile", gen_tile), ("gen_tile_pool", lambda: gen_tile(307, 0.1, (120, 140, 150), (232, 236, 236), 1.0)),
        ("gen_damask", gen_damask), ("gen_stain_ceiling", lambda: gen_stain(201)), ("gen_stain_floor", lambda: gen_stain(202, 256, True)),
        ("gen_ghost", gen_ghost), ("gen_porthole", gen_porthole))}
    lc, _ = MOOD[K]
    # the shell
    material("Carpet_Field", img=g["gen_field"], rough=1.0, tile=1.0)
    material("Carpet_Green", img=g["gen_green"], rough=1.0, tile=1.0)
    material("Carpet_Room", img=g["gen_room_carpet"], rough=1.0, tile=2.0)
    material("Ceiling_Popcorn", tex=PLAST, tint=srgb_lin("#e6dcc4"), rough=0.95, tile=1.2)
    material("Ceiling_Plaster", tex=PLASTER4, tint=srgb_lin("#ece4d0"), rough=0.9, tile=2.0)
    material("Ceiling_Tile", tex=CEILT, tint=srgb_lin("#e8e8e2"), rough=0.9, tile=0.6)
    material("Wall_Upper", img=g["gen_wallcover"], tint=srgb_lin("#e4d4b2"), rough=0.7, tile=1.0)
    material("Wall_Lower", img=g["gen_wallcover"], tint=srgb_lin("#c2aa80"), rough=0.6, tile=1.0)
    material("Wall_Room", tex=WALLP, tint=srgb_lin("#dccaa6"), rough=0.85, tile=1.5)
    material("Tile_Floor_Pool", img=g["gen_tile_pool"], rough=0.35, tile=1.0)
    material("Tile_Wall", img=g["gen_tile"], rough=0.3, tile=0.9)
    material("Tile_Ceiling", img=g["gen_tile"], tint=srgb_lin("#eef0ee"), rough=0.4, tile=0.9)
    material("Tile_Band", img=g["gen_tile_pool"], tint=srgb_lin("#3c78a8"), rough=0.3, tile=1.0)
    material("Paper_Repeat", img=g["gen_damask"], rough=0.8, tile=0.12)
    material("Dado_Paint", tex=WALLP, tint=srgb_lin("#6c7a52"), rough=0.6, tile=1.5)
    material("Vinyl_Floor", tex=VINYL, tint=srgb_lin("#c6cac6"), rough=0.5, tile=1.2)
    material("Block_Lower", img=g["gen_block"], tint=srgb_lin("#8c9a8c"), rough=0.7, tile=1.6)
    material("Block_Upper", img=g["gen_block"], tint=srgb_lin("#d8d2bc"), rough=0.8, tile=1.6)
    material("Paint_Upper", tex=WALLP, tint=srgb_lin("#dcdcd2"), rough=0.85, tile=1.5)
    material("Parquet", tex=PARQ, tint=srgb_lin("#e8d8c0"), rough=0.5, tile=1.6)
    material("Wainscot", tex=WOOD, tint=srgb_lin("#c8a888"), rough=0.5, tile=0.9)
    material("Plaster_Cream", tex=PLASTER4, tint=srgb_lin("#e8d6b0"), rough=0.85, tile=2.0)
    material("Stair_Concrete", tex=CONC, tint=srgb_lin("#c8c4b8"), rough=0.8, tile=1.5)
    material("Stair_Ceiling", tex=WALLP, tint=srgb_lin("#c4c6b8"), rough=0.9, tile=1.5)
    material("Door_Jamb", tex=WOOD, tint=(1.0, 0.86, 0.74), rough=0.5, tile=0.8)
    material("Jamb_Steel", tex=WALLP, tint=srgb_lin("#6e7668"), rough=0.5, tile=1.0)
    material("Wainscot_Trim", tex=WOOD, tint=srgb_lin("#c8a888"), rough=0.5, tile=0.9)        # the props' copies of shell finishes: a material
    material("Step_Concrete", tex=CONC, tint=srgb_lin("#c8c4b8"), rough=0.8, tile=1.5)       # names one lightmap, so shell and props never share one
    material("Skirt_Steel", tex=WALLP, tint=srgb_lin("#6e7668"), rough=0.5, tile=1.0)
    material("Threshold", img=g["gen_brushed"], tint=srgb_lin("#8c6c3c"), rough=0.4, metal=0.8, tile=0.3)
    # the props
    material("Lamp_Emit", color=tuple(0.35 + 0.65 * c for c in lc), rough=0.9, emit=(lc, 3.0))
    material("Lamp_Dead", color=srgb_lin("#a49c88"), rough=0.9)
    material("Emergency_Emit", color=(0.1, 0.8, 0.3), rough=0.4, emit=((0.1, 1.0, 0.25), 5.0))
    material("Brass", img=g["gen_brushed"], tint=srgb_lin("#b48c4c"), rough=0.35, metal=0.9, tile=0.3)
    material("Gilt", img=g["gen_brushed"], tint=srgb_lin("#a8843c"), rough=0.35, metal=0.8, tile=0.2)
    material("Steel", img=g["gen_brushed"], tint=srgb_lin("#a6a8a6"), rough=0.35, metal=0.9, tile=0.4)
    material("Plastic_White", color=srgb_lin("#d6d2c6"), rough=0.5)
    material("Plastic_Black", color=srgb_lin("#1a1a1a"), rough=0.4)
    material("Grille", img=g["gen_grille"], rough=0.6, tile=0.3)
    material("Trim_Wood", tex=WOOD, tint=(1.0, 0.86, 0.74), rough=0.5, tile=0.8)
    material("Skirting", color=srgb_lin("#3a2c24"), rough=0.5)
    material("Trim_White", tex=PLASTER4, tint=srgb_lin("#efe8d8"), rough=0.6, tile=1.0)
    material("Picture", img=g["gen_prints"], rough=0.6)
    material("Leaf_Room", tex=WOOD, tint=(1.0, 0.9, 0.8), rough=0.45, tile=0.9)
    material("Leaf_Fire", tex=WALLP, tint=srgb_lin("#8c8e7c"), rough=0.5, tile=1.0)
    material("Leaf_Glass", color=srgb_lin("#2a3234"), rough=0.2)
    material("Red_Paint", color=srgb_lin("#9a2018"), rough=0.4)
    material("Enamel", color=srgb_lin("#e4e4de"), rough=0.3)
    material("Porthole", img=g["gen_porthole"], rough=0.1)
    material("Mirror", tex=PLASTER4, tint=srgb_lin("#9aa6ac"), rough=0.08, metal=0.7, tile=3.0)
    material("Upholstery", tex=LINEN, tint=srgb_lin("#7a4a52"), rough=0.95, tile=0.5)
    material("Curtain", tex=LINEN, tint=srgb_lin("#a07848"), rough=0.95, tile=0.5)
    material("Window_Frame", img=g["gen_brushed"], tint=srgb_lin("#a4a49e"), rough=0.4, metal=0.7, tile=0.4)
    material("Window_Void", color=srgb_lin("#151719"), rough=0.6)
    material("TV_Plastic", color=srgb_lin("#1c1c1c"), rough=0.45)
    material("Tile_Black", color=srgb_lin("#202428"), rough=0.3)
    material("Decal_Ceiling", img=g["gen_stain_ceiling"], rough=1.0, img_alpha=True)
    material("Decal_Floor", img=g["gen_stain_floor"], rough=1.0, img_alpha=True)
    material("Decal_Ghost", img=g["gen_ghost"], rough=1.0, img_alpha=True)
    material("Glass_Clear", color=(0.85, 0.92, 0.95), rough=0.05, alpha=0.16)
    material("Standin_Grey", color=(0.4, 0.38, 0.34), rough=0.9)


# ---------------------------------------------------------------- geometry helpers (Blender = game (x, -z, y))
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


def sphere(bm, p, r, seg=10):
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


def finish(name, bm, mat, coll, tile=None, keep_uv=False, recalc=True):
    if recalc and not keep_uv:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        f.smooth = False
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


NAMES = set()


def uname(n):
    base, k = n, 1
    while n in NAMES:
        k += 1
        n = f"{base}_{k}"
    NAMES.add(n)
    return n


def part(name, mat, build, coll=None, tile=None, recalc=True):
    bm = bmesh.new()
    build(bm)
    return finish(uname(name), bm, mat, coll or PROPS, tile, recalc=recalc)


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
        return (n[2], 0, -n[0])

    def ra(s):
        """+1 if `a` grows to the viewer's right, facing the wall."""
        r = s.right()
        return 1 if (r[0] if s.axis == "z" else r[2]) > 0 else -1


def text_mesh(body, size, extrude, spacing=1.0):
    cu = bpy.data.curves.new("txt", "FONT")
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    cu.space_character = spacing
    cu.resolution_u = 3
    ob = bpy.data.objects.new("txt", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return me


TEXT_CACHE = {}


def add_text(bm, body, size, depth, origin, right, up, normal, spacing=1.0):
    key = (body, size, depth, spacing)
    if key not in TEXT_CACHE:
        TEXT_CACHE[key] = text_mesh(body, size, depth / 2, spacing)
    me = TEXT_CACHE[key]
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


def wall_text(bm, w, body, a, y, d, size, depth=0.004, spacing=1.0):
    add_text(bm, body, size, depth, w.pt(a, y, d), w.right(), (0, 1, 0), w.normal(), spacing)


def flat_quad(name, mat, corners, uvs, coll=None, normal=None):
    """One textured quad (game corners), its UVs given."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    vs = [bm.verts.new(B(p)) for p in corners]
    f = bm.faces.new(vs)
    f.normal_update()
    if normal is not None and f.normal.dot(B(normal)) < 0:
        f.normal_flip()
    for lp in f.loops:
        lp[uvl].uv = uvs[vs.index(lp.vert)]
    return finish(uname(name), bm, mat, coll or PROPS, keep_uv=True)


def decal(name, mat, x, z, s, y, down=False, rot=0.0, sz=None):
    c, sn = math.cos(rot), math.sin(rot)
    sz = sz or s
    pts = []
    for u, v in ((0, 0), (1, 0), (1, 1), (0, 1)):
        dx, dz = (u - 0.5) * s, (v - 0.5) * sz
        pts.append((x + dx * c - dz * sn, y, z + dx * sn + dz * c))
    return flat_quad(name, mat, pts, [(0, 0), (1, 0), (1, 1), (0, 1)], normal=(0, -1 if down else 1, 0))


def wall_picture(w, a, y, wd, ht, which, tag, frame="Gilt"):
    """A framed print 3 cm off the wall: a frame and one quarter of floor 1's print atlas."""
    fw = 0.035
    part(f"Picture_{tag}_Frame", frame, lambda bm: (w.box(bm, a - wd / 2, a + wd / 2, y - ht / 2, y - ht / 2 + fw, 0, 0.03),
                                                    w.box(bm, a - wd / 2, a + wd / 2, y + ht / 2 - fw, y + ht / 2, 0, 0.03),
                                                    w.box(bm, a - wd / 2, a - wd / 2 + fw, y - ht / 2, y + ht / 2, 0, 0.03),
                                                    w.box(bm, a + wd / 2 - fw, a + wd / 2, y - ht / 2, y + ht / 2, 0, 0.03)))
    r, c = divmod(which, 2)
    u0, v0 = c * 0.5, r * 0.5
    a0, a1 = a - wd / 2 + fw, a + wd / 2 - fw
    if w.ra() < 0:
        a0, a1 = a1, a0
    corners = [w.pt(a0, y - ht / 2 + fw, 0.012), w.pt(a1, y - ht / 2 + fw, 0.012), w.pt(a1, y + ht / 2 - fw, 0.012), w.pt(a0, y + ht / 2 - fw, 0.012)]
    flat_quad(f"Picture_{tag}", "Picture", corners, [(u0, v0), (u0 + 0.5, v0), (u0 + 0.5, v0 + 0.5), (u0, v0 + 0.5)], normal=w.normal())


def light(name, kind, pos, power, color=None, size=0.05, aim=None, coll=None, shape="DISK", size_y=None):
    d = bpy.data.lights.new(name, kind)
    d.energy = power
    d.color = color or MOOD[K][0]
    if kind == "AREA":
        d.shape = shape
        d.size = size
        if size_y is not None:
            d.size_y = size_y
    else:
        d.shadow_soft_size = size
    ob = bpy.data.objects.new(uname(name), d)
    ob.location = B(pos)
    if aim is not None:
        ob.rotation_euler = (B(aim) - B(pos)).to_track_quat("-Z", "Y").to_euler()
    (coll or LIGHTS).objects.link(ob)
    return ob


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


# ---------------------------------------------------------------- the skin
def build_skin():
    q, M = scene_skin(SCENE)
    by = {}
    for x in q:
        by.setdefault(quad_material(SCENE, x), []).append(x)
    for mname, quads in sorted(by.items()):
        skin_mesh("Skin_" + mname, quads, SKIN, mname)
    return M


def skin_mesh(name, quads, coll, mname):
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    tile = TILES.get(mname, 1.0)
    pieces = []
    for x in quads:                                      # long quads cut into pieces of 4 m at most (one 16 m island would shrink the atlas)
        nb = max(1, math.ceil((x["b"][1] - x["b"][0]) / 4.0))
        nc = max(1, math.ceil((x["c"][1] - x["c"][0]) / 4.0))
        for i in range(nb):
            for j in range(nc):
                y = dict(x)
                y["b"] = (x["b"][0] + (x["b"][1] - x["b"][0]) * i / nb, x["b"][0] + (x["b"][1] - x["b"][0]) * (i + 1) / nb)
                y["c"] = (x["c"][0] + (x["c"][1] - x["c"][0]) * j / nc, x["c"][0] + (x["c"][1] - x["c"][0]) * (j + 1) / nc)
                pieces.append(y)
    for x in pieces:
        f = bm.faces.new([bm.verts.new(B(p)) for p in quad_points(x)])
        f.normal_update()
        want = [0, 0, 0]
        want[x["axis"]] = x["side"]
        if f.normal.dot(B(want)) < 0:
            f.normal_flip()
        for lp in f.loops:
            gx, gy, gz = lp.vert.co.x, lp.vert.co.z, -lp.vert.co.y
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


# ---------------------------------------------------------------- the two one-way doors: one leaf mesh (reused in all seven files)
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


def leaf_mesh(width, height):
    """`Leaf_Maze`: a wood-look hotel door, 4.5 cm thick, centred on its hinge line. Local +X runs from the hinge along the leaf, z is up. Its
    knob and brass plate are on the local -Y face only: for `entry` that is the atrium's side (it does not open from the maze), for `way_on` the
    maze's side (it opens when the puzzle is solved). The greybox's leaves are centred the same way."""
    if "Leaf_Maze" in LEAF_MESH:
        return LEAF_MESH["Leaf_Maze"]
    th = 0.0225
    w, h = width - 0.006, height - 0.008
    pieces = []

    def bx(x0, x1, ya, yb, z0, z1, mat):
        mm = bmesh.new()
        mm.loops.layers.uv.new("UVMap")
        bmesh.ops.create_cube(mm, size=1.0, matrix=Matrix.Translation(((x0 + x1) / 2, (ya + yb) / 2, (z0 + z1) / 2)) @ Matrix.Diagonal((x1 - x0, yb - ya, z1 - z0, 1)))
        pieces.append((mm, mat))
    bx(0.003, w, -th, th, 0.006, h, "Leaf_Room")
    for zz0, zz1 in ((0.25, 0.95), (1.15, h - 0.2)):                  # raised panels both faces
        for yy, sd in ((-th, -1), (th, 1)):
            bx(0.12, w - 0.12, *sorted((yy, yy + sd * 0.006)), zz0, zz1, "Leaf_Room")
    hx = w - 0.075
    bx(hx - 0.032, hx + 0.032, -th - 0.008, -th, 0.92, 0.98, "Brass")
    bx(hx - 0.022, hx + 0.022, -th - 0.06, -th - 0.008, 0.93, 0.97, "Brass")
    bx(0.035, w - 0.035, -th - 0.002, -th, 0.03, 0.2, "Brass")
    me = bpy.data.meshes.new("Leaf_Maze")
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
    LEAF_MESH["Leaf_Maze"] = me
    return me


def build_leaves(M):
    for d in M.doors:
        p = d["props"]
        ob = bpy.data.objects.new(d["name"], leaf_mesh(p["width"], p["height"]))
        ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
        DOORS.objects.link(ob)
        for k, v in p.items():
            ob[k] = v
    dz = doors_z(M)
    for door, (x, z) in dz.items():
        w = Wall("x", x, 1 if x < 0 else -1)
        jm = THEME[K]["jamb"]
        cm = "Steel" if jm == "Jamb_Steel" else "Trim_White" if K == 2 else "Trim_Wood"
        hw = GB.DOOR_W / 2
        part(f"Casing_{door}_L", cm, lambda bm, w=w, z=z: w.box(bm, z - hw - 0.07, z - hw, 0.0, GB.DOOR_H + 0.07, 0.0, 0.018))
        part(f"Casing_{door}_R", cm, lambda bm, w=w, z=z: w.box(bm, z + hw, z + hw + 0.07, 0.0, GB.DOOR_H + 0.07, 0.0, 0.018))
        part(f"Casing_{door}_Head", cm, lambda bm, w=w, z=z: w.box(bm, z - hw - 0.07, z + hw + 0.07, GB.DOOR_H, GB.DOOR_H + 0.07, 0.0, 0.018))
        if door == "way_on":                               # a small plaque over the way on, the maze's number: where you are, and no more
            part("Plaque_way_on", "Brass", lambda bm, w=w, z=z: w.box(bm, z - 0.16, z + 0.16, 2.3, 2.42, 0.0, 0.006))
            part("Plaque_way_on_t", "Plastic_Black", lambda bm, w=w, z=z: wall_text(bm, w, f"{K:02d}", z, 2.36, 0.006, 0.07, 0.002, 1.1))


# ---------------------------------------------------------------- the dressing, shared pieces
def face_walls():
    return [(Wall(ax, pl, s), r0, r1) for ax, pl, s, r0, r1 in faces(SCENE)]


def bay_list():
    fw = face_walls()
    return [(fw[fi][0], a, hw, fi) for fi, a, hw in bays(SCENE)]


def rail_runs(w, r0, r1, gaps, y0, y1, d, mat, tag):
    """A strip along a face from r0 to r1 (skirting, chair rail, picture rail, handrail), broken at gaps [(a0, a1)]."""
    a = r0
    k = 0
    for g0, g1 in sorted(gaps) + [(r1, r1)]:
        if g0 > a + 0.02:
            k += 1
            part(f"{tag}_{k}", mat, lambda bm, a0=a, a1=min(g0, r1): w.box(bm, a0, a1, y0, y1, 0.0, d))
        a = max(a, g1)


def sconce(w, a, y, tag, dead=False, shade="Lamp_Emit", power=None):
    """Floor 1's drum-shade sconce (every part above 1.8 m)."""
    part(f"Sconce_{tag}_Plate", "Brass", lambda bm: w.box(bm, a - 0.05, a + 0.05, y - 0.11, y + 0.07, 0.0, 0.014))
    part(f"Sconce_{tag}_Arm", "Brass", lambda bm: cyl(bm, w.pt(a, y - 0.04, 0.012), w.pt(a, y - 0.04, 0.14), 0.009, seg=8))
    part(f"Sconce_{tag}_Shade", "Lamp_Dead" if dead else shade,
         lambda bm: cyl(bm, w.pt(a, y - 0.085, 0.15), w.pt(a, y + 0.085, 0.15), 0.1, 0.078, seg=20, cap=False), recalc=False)
    if not dead:
        light(f"L_sconce_{tag}", "POINT", w.pt(a, y - 0.005, 0.15), power or MOOD[K][1], size=0.03)


def ceiling_dome(x, z, tag, power=None, r=0.17, dead=False):
    part(f"Dome_{tag}", "Lamp_Dead" if dead else "Lamp_Emit", lambda bm: cyl(bm, (x, H - 0.08, z), (x, H, z), r - 0.03, r, seg=20))
    part(f"Dome_{tag}_Rim", "Brass", lambda bm: cyl(bm, (x, H - 0.012, z), (x, H, z), r + 0.015, seg=20))
    if not dead:
        light(f"L_dome_{tag}", "POINT", (x, H - 0.14, z), power or MOOD[K][1], size=0.1)


def smoke(x, z, tag):
    part(f"Smoke_{tag}", "Plastic_White", lambda bm: cyl(bm, (x, H - 0.035, z), (x, H, z), 0.065, seg=16))


def exit_sign(w, a, y0, tag, arrow=""):
    part(f"Exit_{tag}_Housing", "Plastic_White", lambda bm: w.box(bm, a - 0.18, a + 0.18, y0, y0 + 0.2, 0.0, 0.04))
    part(f"Exit_{tag}_Face", "Plastic_Black", lambda bm: w.box(bm, a - 0.165, a + 0.165, y0 + 0.015, y0 + 0.185, 0.04, 0.042))
    part(f"Exit_{tag}_Letters", "Emergency_Emit", lambda bm: wall_text(bm, w, ("EXIT " + arrow).strip(), a, y0 + 0.1, 0.042, 0.09, 0.004, 1.05))


def stains(n, seed, floor=True, ceiling=True):
    rng = np.random.default_rng(seed)
    cl = cells(SCENE)
    for i in range(n):
        x, z = cl[int(rng.integers(len(cl)))]
        x += (rng.random() - 0.5) * 0.6
        z += (rng.random() - 0.5) * 0.6
        if ceiling:
            decal(f"decor_stain_ceiling_{i}", "Decal_Ceiling", x, z, 0.7 + rng.random() * 0.9, H - 0.003, down=True, rot=rng.random() * 6)
        if floor and i % 2 == 0:
            decal(f"decor_stain_floor_{i}", "Decal_Floor", x + 0.3, z - 0.2, 0.5 + rng.random() * 0.5, 0.003, rot=rng.random() * 6)


DETAIL = {}           # the theme's hero piece: {"w": Wall, "a": a, "y": y}, for the detail still


def hero(w, a, y=1.3):
    if "w" not in DETAIL:
        DETAIL.update(w=w, a=a, y=y)


def near_entry(bl):
    """Bays ordered by distance from the entry's arrival point (so the hero is one the player sees first)."""
    M = model(SCENE)
    ax, az = next(e["pos"] for e in M.empties if e["name"] == "Arrive_entry")[::2]

    def dist(b):
        w, a = b[0], b[1]
        p = w.pt(a, 0, 1.4)
        return math.hypot(p[0] - ax, p[2] - az)
    return sorted(bl, key=dist)


# ---------------------------------------------------------------- 1: the corridor of small doors
def dress_1():
    bl = bay_list()
    gaps = {}
    DW, DH = 0.70, 1.78                                 # a hotel door is 0.94 by 2.16
    for i, (w, a, hw, fi) in enumerate(bl):
        tag = f"{fi}_{i}"
        gaps.setdefault(fi, []).append((a - DW / 2 - 0.06, a + DW / 2 + 0.06))
        part(f"SmallDoor_{tag}_Casing", "Trim_Wood", lambda bm, w=w, a=a: (w.box(bm, a - DW / 2 - 0.06, a - DW / 2, 0, DH + 0.06, 0, 0.018),
                                                                           w.box(bm, a + DW / 2, a + DW / 2 + 0.06, 0, DH + 0.06, 0, 0.018),
                                                                           w.box(bm, a - DW / 2 - 0.06, a + DW / 2 + 0.06, DH, DH + 0.06, 0, 0.018)))
        part(f"SmallDoor_{tag}_Leaf", "Leaf_Room", lambda bm, w=w, a=a: (w.box(bm, a - DW / 2, a + DW / 2, 0.0, DH, 0.0, 0.012),
                                                                         w.box(bm, a - DW / 2 + 0.09, a + DW / 2 - 0.09, 0.2, 0.78, 0.012, 0.017),
                                                                         w.box(bm, a - DW / 2 + 0.09, a + DW / 2 - 0.09, 0.95, DH - 0.15, 0.012, 0.017)))
        kx = a + w.ra() * (DW / 2 - 0.07)
        part(f"SmallDoor_{tag}_Knob", "Brass", lambda bm, w=w, kx=kx: (w.box(bm, kx - 0.025, kx + 0.025, 0.78, 0.83, 0.012, 0.02),
                                                                        w.box(bm, kx - 0.016, kx + 0.016, 0.79, 0.82, 0.02, 0.06)))
        part(f"SmallDoor_{tag}_Kick", "Brass", lambda bm, w=w, a=a: w.box(bm, a - DW / 2 + 0.03, a + DW / 2 - 0.03, 0.03, 0.18, 0.012, 0.014))
        part(f"SmallDoor_{tag}_Num", "Brass", lambda bm, w=w, a=a: wall_text(bm, w, "101", a, 1.4, 0.017, 0.07, 0.003, 1.05))
        part(f"SmallDoor_{tag}_Peep", "Brass", lambda bm, w=w, a=a: cyl(bm, w.pt(a, 1.22, 0.017), w.pt(a, 1.22, 0.027), 0.011, seg=10))
        if i % 2 == 0:
            sconce(w, a, 2.22, tag, dead=(i % 10 == 4))
        hero(w, a, 1.0)
    for fi, (w, r0, r1) in enumerate(face_walls()):
        rail_runs(w, r0, r1, gaps.get(fi, []), 0.0, 0.1, 0.012, "Skirting", f"Skirting_{fi}")
        rail_runs(w, r0, r1, gaps.get(fi, []), 0.87, 0.935, 0.022, "Trim_Wood", f"ChairRail_{fi}")
    for i, (x, z) in enumerate(cells(SCENE)):
        if i % 5 == 2:
            smoke(x, z, str(i))
    stains(9, 401)


# ---------------------------------------------------------------- 2: the dry pool
def dress_2():
    bl = bay_list()
    marks = ["1.2 M", "2.4 M", "1.2 M", "NO DIVING", "2.4 M", "1.2 M"]
    for i, (w, a, hw, fi) in enumerate(bl):
        tag = f"{fi}_{i}"
        if i % 3 == 0:
            t = marks[(i // 3) % len(marks)]
            part(f"Depth_{tag}", "Tile_Black", lambda bm, w=w, a=a, t=t: wall_text(bm, w, t, a, 1.75, 0.0, 0.16 if len(t) < 6 else 0.12, 0.004, 1.1))
            hero(w, a, 1.5)
        elif i % 3 == 1:                                    # a black lane target, as on a pool's end wall
            part(f"Target_{tag}", "Tile_Black", lambda bm, w=w, a=a: (w.box(bm, a - 0.05, a + 0.05, 0.3, 1.0, 0.0, 0.004),
                                                                      w.box(bm, a - 0.3, a + 0.3, 1.0, 1.1, 0.0, 0.004)))
    for fi, (w, r0, r1) in enumerate(face_walls()):
        if r1 - r0 < 0.8:
            continue
        part(f"GrabRail_{fi}", "Steel", lambda bm, w=w, r0=r0, r1=r1: (
            cyl(bm, w.pt(r0 + 0.15, 0.95, 0.055), w.pt(r1 - 0.15, 0.95, 0.055), 0.019, seg=10),
            *[w.box(bm, c - 0.015, c + 0.015, 0.93, 0.97, 0.0, 0.055) for c in np.linspace(r0 + 0.2, r1 - 0.2, max(2, int((r1 - r0) / 1.2) + 1))]))
    for i, (x, z) in enumerate(cells(SCENE)):
        part(f"Panel_{i}", "Lamp_Emit", lambda bm, x=x, z=z: cube(bm, (x - 0.3, H - 0.02, z - 0.3), (x + 0.3, H, z + 0.3)))
        part(f"Panel_{i}_Rim", "Steel", lambda bm, x=x, z=z: (cube(bm, (x - 0.33, H - 0.025, z - 0.33), (x + 0.33, H - 0.019, z - 0.3)),
                                                               cube(bm, (x - 0.33, H - 0.025, z + 0.3), (x + 0.33, H - 0.019, z + 0.33)),
                                                               cube(bm, (x - 0.33, H - 0.025, z - 0.3), (x - 0.3, H - 0.019, z + 0.3)),
                                                               cube(bm, (x + 0.3, H - 0.025, z - 0.3), (x + 0.33, H - 0.019, z + 0.3))))
        la = light(f"L_panel_{i}", "AREA", (x, H - 0.03, z), MOOD[K][1], size=0.6, aim=(x, 0.0, z), shape="SQUARE")
        if i % 3 == 0:
            part(f"Drain_{i}", "Grille", lambda bm, x=x, z=z: cube(bm, (x - 0.09, 0.0, z - 0.09), (x + 0.09, 0.004, z + 0.09)), tile=0.18)
    stains(5, 402, ceiling=False)


# ---------------------------------------------------------------- 3: the wallpaper that repeats
def dress_3():
    bl = bay_list()
    for i, (w, a, hw, fi) in enumerate(bl):
        tag = f"{fi}_{i}"
        wall_picture(w, a, 1.6, 0.46, 0.36, 1, tag)        # the same print, the same size, at the same height, in every bay
        part(f"Switch_{tag}", "Plastic_White", lambda bm, w=w, a=a: w.box(bm, a + hw - 0.12, a + hw - 0.04, 1.15, 1.27, 0.0, 0.01))
        hero(w, a, 1.35)
    for fi, (w, r0, r1) in enumerate(face_walls()):
        rail_runs(w, r0, r1, [], 0.0, 0.11, 0.014, "Trim_White", f"Skirting_{fi}")
        rail_runs(w, r0, r1, [], 0.88, 0.94, 0.02, "Trim_White", f"DadoRail_{fi}")
        rail_runs(w, r0, r1, [], H - 0.08, H, 0.03, "Trim_White", f"Cornice_{fi}")
    for i, (x, z) in enumerate(cells(SCENE)):
        ceiling_dome(x, z, str(i), dead=(i % 13 == 6))
    if kof(SCENE) % 2:
        ceiling_dome(0.0, 0.0, "room", r=0.24)
    stains(6, 403, floor=False)


# ---------------------------------------------------------------- 4: the laundry of identical machines
def washer(w, a, y0, tag):
    """One built-in front-loader's face, 4.4 cm proud at most: enamel front, control strip, a dial, a coin slot, the porthole ring and glass, a
    handle, the number 7. Every machine in the maze is this one."""
    W2 = 0.3
    part(f"Washer_{tag}_Front", "Enamel", lambda bm: w.box(bm, a - W2, a + W2, y0, y0 + 0.8, 0.0, 0.03))
    part(f"Washer_{tag}_Strip", "Plastic_Black", lambda bm: w.box(bm, a - W2 + 0.03, a + W2 - 0.03, y0 + 0.68, y0 + 0.77, 0.03, 0.034))
    part(f"Washer_{tag}_Dial", "Steel", lambda bm: cyl(bm, w.pt(a + 0.17, y0 + 0.725, 0.034), w.pt(a + 0.17, y0 + 0.725, 0.044), 0.03, seg=8))
    part(f"Washer_{tag}_Coin", "Steel", lambda bm: w.box(bm, a - 0.2, a - 0.1, y0 + 0.7, y0 + 0.75, 0.034, 0.04))
    part(f"Washer_{tag}_Num", "Plastic_White", lambda bm: wall_text(bm, w, "7", a, y0 + 0.725, 0.034, 0.05, 0.002))
    yc = y0 + 0.34
    part(f"Washer_{tag}_Ring", "Steel", lambda bm: cyl(bm, w.pt(a, yc, 0.03), w.pt(a, yc, 0.044), 0.2, 0.19, seg=12, cap=False), recalc=False)
    part(f"Washer_{tag}_Handle", "Steel", lambda bm: w.box(bm, a + w.ra() * 0.21 - 0.02, a + w.ra() * 0.21 + 0.02, yc - 0.06, yc + 0.06, 0.03, 0.044))
    r = 0.19
    seg = 12
    pts, uvs = [], []
    for k in range(seg):
        t = 2 * math.pi * k / seg
        pts.append(w.pt(a + w.ra() * r * math.cos(t), yc + r * math.sin(t), 0.04))
        uvs.append((0.5 + 0.5 * math.cos(t), 0.5 + 0.5 * math.sin(t)))
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    vs = [bm.verts.new(B(p)) for p in pts]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.dot(B(w.normal())) < 0:
        f.normal_flip()
    for lp in f.loops:
        lp[uvl].uv = uvs[vs.index(lp.vert)]
    finish(uname(f"Washer_{tag}_Glass"), bm, "Porthole", PROPS, keep_uv=True)


def dress_4():
    bl = bay_list()
    for i, (w, a, hw, fi) in enumerate(bl):
        tag = f"{fi}_{i}"
        for c in (-0.64, 0.0, 0.64):
            for r, y0 in enumerate((0.12, 0.95)):
                washer(w, a + c, y0, f"{tag}_{int(c * 10):+d}{r}")
        part(f"Plinth_{tag}", "Plastic_Black", lambda bm, w=w, a=a: w.box(bm, a - 0.95, a + 0.95, 0.0, 0.11, 0.0, 0.03))
        hero(w, a, 1.0)
    for fi, (w, r0, r1) in enumerate(face_walls()):
        rail_runs(w, r0, r1, [], 1.85, 1.9, 0.02, "Steel", f"Duct_{fi}")
    for i, (x, z) in enumerate(cells(SCENE)):
        dead = i % 11 == 5
        part(f"Tube_{i}", "Lamp_Dead" if dead else "Lamp_Emit", lambda bm, x=x, z=z: cube(bm, (x - 0.6, H - 0.03, z - 0.08), (x + 0.6, H, z + 0.08)))
        part(f"Tube_{i}_Body", "Steel", lambda bm, x=x, z=z: (cube(bm, (x - 0.63, H - 0.035, z - 0.13), (x + 0.63, H - 0.03, z - 0.08)),
                                                               cube(bm, (x - 0.63, H - 0.035, z + 0.08), (x + 0.63, H - 0.03, z + 0.13))))
        if not dead:
            light(f"L_tube_{i}", "AREA", (x, H - 0.04, z), MOOD[K][1], size=1.2, size_y=0.16, aim=(x, 0.0, z), shape="RECTANGLE")
        if i % 4 == 1:
            part(f"Drain_{i}", "Grille", lambda bm, x=x, z=z: cube(bm, (x - 0.1, 0.0, z - 0.1), (x + 0.1, 0.004, z + 0.1)), tile=0.2)
    stains(8, 404)


# ---------------------------------------------------------------- 5: the ballroom with no furniture
def chandelier(x, z, tag, r=0.36, arms=6, power=None):
    """Hung from the ceiling, every part above 2.0 m: a rose, a chain, a gilt body, a ring of arms with candle bulbs (Lamp_Emit)."""
    yb = 2.32
    part(f"Chand_{tag}_Rose", "Gilt", lambda bm: cyl(bm, (x, H - 0.03, z), (x, H, z), 0.14, 0.18, seg=16))
    part(f"Chand_{tag}_Chain", "Gilt", lambda bm: cyl(bm, (x, yb + 0.25, z), (x, H - 0.03, z), 0.012, seg=6))
    part(f"Chand_{tag}_Body", "Gilt", lambda bm: (cyl(bm, (x, yb - 0.12, z), (x, yb + 0.05, z), 0.03, 0.08, seg=12),
                                                  cyl(bm, (x, yb + 0.05, z), (x, yb + 0.25, z), 0.08, 0.02, seg=12),
                                                  sphere(bm, (x, yb - 0.16, z), 0.04, 10)))

    def arms_(bm):
        for k in range(arms):
            t = 2 * math.pi * k / arms
            ex, ez = x + r * math.cos(t), z + r * math.sin(t)
            cyl(bm, (x, yb, z), (ex, yb + 0.05, ez), 0.01, seg=6)
            cyl(bm, (ex, yb + 0.03, ez), (ex, yb + 0.06, ez), 0.035, 0.045, seg=10)
    part(f"Chand_{tag}_Arms", "Gilt", arms_)

    def bulbs(bm):
        for k in range(arms):
            t = 2 * math.pi * k / arms
            ex, ez = x + r * math.cos(t), z + r * math.sin(t)
            cyl(bm, (ex, yb + 0.06, ez), (ex, yb + 0.15, ez), 0.012, seg=8)
            sphere(bm, (ex, yb + 0.18, ez), 0.024, 8)
    part(f"Chand_{tag}_Bulbs", "Lamp_Emit", bulbs)
    light(f"L_chand_{tag}", "POINT", (x, yb + 0.12, z), power or MOOD[K][1], size=r * 0.7)


def dress_5():
    bl = bay_list()
    rng = np.random.default_rng(405)
    for i, (w, a, hw, fi) in enumerate(bl):
        tag = f"{fi}_{i}"
        for pa in (a - hw / 2, a + hw / 2):                 # two wainscot panels a bay, mouldings 1.5 cm proud
            part(f"Panel_{tag}_{pa:+.2f}", "Wainscot_Trim", lambda bm, w=w, pa=pa, hw=hw: (
                w.box(bm, pa - hw / 2 + 0.06, pa + hw / 2 - 0.06, 0.2, 0.23, 0.0, 0.015), w.box(bm, pa - hw / 2 + 0.06, pa + hw / 2 - 0.06, 0.77, 0.8, 0.0, 0.015),
                w.box(bm, pa - hw / 2 + 0.06, pa - hw / 2 + 0.09, 0.23, 0.77, 0.0, 0.015), w.box(bm, pa + hw / 2 - 0.09, pa + hw / 2 - 0.06, 0.23, 0.77, 0.0, 0.015)))
        if i % 2 == 0:                                      # a tall mirror in a gilt frame
            part(f"Mirror_{tag}", "Mirror", lambda bm, w=w, a=a: w.box(bm, a - 0.45, a + 0.45, 1.12, 2.5, 0.0, 0.01))
            part(f"Mirror_{tag}_Frame", "Gilt", lambda bm, w=w, a=a: (w.box(bm, a - 0.5, a + 0.5, 1.07, 1.12, 0.0, 0.035), w.box(bm, a - 0.5, a + 0.5, 2.5, 2.58, 0.0, 0.035),
                                                                      w.box(bm, a - 0.5, a - 0.45, 1.12, 2.5, 0.0, 0.035), w.box(bm, a + 0.45, a + 0.5, 1.12, 2.5, 0.0, 0.035)))
            hero(w, a, 1.6)
        else:                                               # a two-candle sconce, all above 1.8 m
            def sc_(bm, w=w, a=a):
                w.box(bm, a - 0.06, a + 0.06, 1.86, 2.12, 0.0, 0.015)
                for s in (-1, 1):
                    cyl(bm, w.pt(a, 1.95, 0.015), w.pt(a + s * 0.16, 1.98, 0.13), 0.01, seg=6)
                    cyl(bm, w.pt(a + s * 0.16, 1.97, 0.13), w.pt(a + s * 0.16, 2.0, 0.13), 0.04, 0.05, seg=10)
            part(f"Candle_{tag}", "Gilt", sc_)
            part(f"Candle_{tag}_Bulbs", "Lamp_Emit", lambda bm, w=w, a=a: [cyl(bm, w.pt(a + s * 0.16, 2.0, 0.13), w.pt(a + s * 0.16, 2.1, 0.13), 0.012, seg=8) for s in (-1, 1)])
            light(f"L_candle_{tag}", "POINT", w.pt(a, 2.08, 0.15), MOOD[K][1] * 0.25, size=0.08)
    for fi, (w, r0, r1) in enumerate(face_walls()):
        rail_runs(w, r0, r1, [], 0.0, 0.13, 0.016, "Wainscot_Trim", f"Skirting_{fi}")
        rail_runs(w, r0, r1, [], 0.96, 1.03, 0.025, "Gilt", f"DadoRail_{fi}")
        rail_runs(w, r0, r1, [], 2.68, 2.72, 0.02, "Gilt", f"PictureRail_{fi}")
        rail_runs(w, r0, r1, [], H - 0.1, H, 0.04, "Trim_White", f"Cornice_{fi}")
    n, p = grid(SCENE)
    for i, (x, z) in enumerate(cells(SCENE)):
        ii, jj = round((x + A) / p - 0.5), round((z + A) / p - 0.5)
        if (ii + jj) % 2 == 0:
            chandelier(x, z, str(i))
        elif rng.random() < 0.55:                          # a pale disc where a round table stood, and the four chairs' feet
            decal(f"decor_ghost_{i}", "Decal_Ghost", x + (rng.random() - 0.5) * 0.3, z + (rng.random() - 0.5) * 0.3, 1.45, 0.002, rot=rng.random())
    chandelier(0.0, 0.0, "room", r=0.62, arms=10, power=MOOD[K][1] * 2.2)
    for k in range(6):                                     # the dance floor's middle: the pale marks of a ring of chairs, and nothing else
        t = 2 * math.pi * k / 6
        decal(f"decor_chair_{k}", "Decal_Ghost", 1.35 * math.cos(t), 1.35 * math.sin(t), 0.5, 0.002, rot=t)


# ---------------------------------------------------------------- 6: the guest room in a loop
def dress_6():
    bl = bay_list()
    for i, (w, a, hw, fi) in enumerate(bl):
        tag = f"{fi}_{i}"
        kind = i % 4                                       # bed, window, door, TV: round and round, the same room
        if kind == 0:
            part(f"Headboard_{tag}", "Upholstery", lambda bm, w=w, a=a: w.box(bm, a - 0.72, a + 0.72, 0.5, 1.32, 0.0, 0.045))
            part(f"Headboard_{tag}_Trim", "Wood_Laminate" if "Wood_Laminate" in MATS else "Trim_Wood",
                 lambda bm, w=w, a=a: w.box(bm, a - 0.76, a + 0.76, 1.32, 1.37, 0.0, 0.045))
            for s in (-1, 1):
                la = a + s * 0.8
                part(f"BedLamp_{tag}_{s:+d}_Arm", "Brass", lambda bm, w=w, la=la: (w.box(bm, la - 0.04, la + 0.04, 1.08, 1.2, 0.0, 0.012),
                                                                                    cyl(bm, w.pt(la, 1.14, 0.012), w.pt(la, 1.14, 0.15), 0.008, seg=6)))
                part(f"BedLamp_{tag}_{s:+d}_Shade", "Lamp_Emit", lambda bm, w=w, la=la: cyl(bm, w.pt(la, 1.08, 0.15), w.pt(la, 1.24, 0.15), 0.085, 0.065, seg=18, cap=False),
                     recalc=False)
                light(f"L_bedlamp_{tag}_{s:+d}", "POINT", w.pt(la, 1.16, 0.15), MOOD[K][1], size=0.05)
            wall_picture(w, a, 1.85, 0.62, 0.42, 0, tag)
            hero(w, a, 1.2)
        elif kind == 1:                                    # the window that looks onto nothing, drawn nearly shut
            part(f"Window_{tag}_Frame", "Window_Frame", lambda bm, w=w, a=a: (w.box(bm, a - 0.66, a + 0.66, 0.9, 0.95, 0.0, 0.04), w.box(bm, a - 0.66, a + 0.66, 2.05, 2.1, 0.0, 0.04),
                                                                              w.box(bm, a - 0.66, a - 0.61, 0.95, 2.05, 0.0, 0.04), w.box(bm, a + 0.61, a + 0.66, 0.95, 2.05, 0.0, 0.04),
                                                                              w.box(bm, a - 0.02, a + 0.02, 0.95, 2.05, 0.0, 0.03)))
            part(f"Window_{tag}_Void", "Window_Void", lambda bm, w=w, a=a: w.box(bm, a - 0.61, a + 0.61, 0.95, 2.05, 0.0, 0.006))
            part(f"decor_curtain_{tag}_rail", "Window_Frame", lambda bm, w=w, a=a: w.box(bm, a - 0.9, a + 0.9, 2.26, 2.3, 0.0, 0.04))
            for s in (-1, 1):
                def cur(bm, w=w, a=a, s=s):
                    c0, c1 = (a - 0.88, a - 0.08) if s < 0 else (a + 0.08, a + 0.88)
                    n = 16
                    top, bot = [], []
                    for k in range(n + 1):
                        t = k / n
                        aa = c0 + (c1 - c0) * t
                        dd = 0.025 + 0.018 * math.sin(t * math.pi * 7 + s)
                        top.append(bm.verts.new(B(w.pt(aa, 2.25, dd))))
                        bot.append(bm.verts.new(B(w.pt(aa, 0.62, dd))))
                    nw = B(w.normal())
                    for k in range(n):
                        f = bm.faces.new((bot[k], bot[k + 1], top[k + 1], top[k]))
                        f.normal_update()
                        if f.normal.dot(nw) < 0:              # the curtain faces the room, so its bake sees the room's light
                            f.normal_flip()
                part(f"decor_curtain_{tag}_{s:+d}", "Curtain", cur, tile=0.5, recalc=False)
            part(f"Heater_{tag}", "Grille", lambda bm, w=w, a=a: w.box(bm, a - 0.5, a + 0.5, 0.12, 0.5, 0.0, 0.03), tile=0.4)
        elif kind == 2:                                    # the room's own door: 214, every time
            part(f"RoomDoor_{tag}_Casing", "Trim_Wood", lambda bm, w=w, a=a: (w.box(bm, a - 0.54, a - 0.47, 0, 2.23, 0, 0.018), w.box(bm, a + 0.47, a + 0.54, 0, 2.23, 0, 0.018),
                                                                              w.box(bm, a - 0.54, a + 0.54, 2.16, 2.23, 0, 0.018)))
            part(f"RoomDoor_{tag}_Leaf", "Leaf_Room", lambda bm, w=w, a=a: w.box(bm, a - 0.47, a + 0.47, 0, 2.16, 0, 0.012))
            kx = a + w.ra() * 0.4
            part(f"RoomDoor_{tag}_Knob", "Brass", lambda bm, w=w, kx=kx: (w.box(bm, kx - 0.03, kx + 0.03, 0.92, 0.98, 0.012, 0.02),
                                                                           w.box(bm, kx - 0.02, kx + 0.02, 0.93, 0.97, 0.02, 0.06)))
            part(f"RoomDoor_{tag}_Chain", "Brass", lambda bm, w=w, kx=kx: w.box(bm, kx - 0.1, kx - 0.02, 1.4, 1.42, 0.012, 0.02))
            part(f"RoomDoor_{tag}_Card", "Plastic_White", lambda bm, w=w, a=a: w.box(bm, a - 0.12, a + 0.12, 1.35, 1.6, 0.012, 0.014))
            part(f"RoomDoor_{tag}_Card_t", "Red_Paint", lambda bm, w=w, a=a: wall_text(bm, w, "214", a, 1.5, 0.014, 0.07, 0.002))
            part(f"DND_{tag}", "Red_Paint", lambda bm, w=w, kx=kx: w.box(bm, kx - 0.045, kx + 0.045, 0.7, 0.9, 0.012, 0.016))
        else:                                              # the TV wall
            part(f"TV_{tag}", "TV_Plastic", lambda bm, w=w, a=a: w.box(bm, a - 0.48, a + 0.48, 1.0, 1.56, 0.0, 0.04))
            part(f"TV_{tag}_Screen", "Window_Void", lambda bm, w=w, a=a: w.box(bm, a - 0.45, a + 0.45, 1.03, 1.53, 0.04, 0.042))
            wall_picture(w, a, 2.05, 0.5, 0.36, 0, tag)
            part(f"Sign_{tag}", "Plastic_White", lambda bm, w=w, a=a: w.box(bm, a - 0.62, a - 0.52, 1.2, 1.3, 0.0, 0.006))
    for fi, (w, r0, r1) in enumerate(face_walls()):
        rail_runs(w, r0, r1, [], 0.0, 0.09, 0.012, "Trim_Wood", f"Skirting_{fi}")
    for i, (x, z) in enumerate(cells(SCENE)):
        if i % 3 == 0:
            ceiling_dome(x, z, str(i), power=MOOD[K][1] * 0.5, dead=(i % 2 == 1))
        elif i % 3 == 1:
            smoke(x, z, str(i))
    stains(6, 406)


# ---------------------------------------------------------------- 7: the stairs that end in a wall
def flight_down(w, a, tag):
    """Stairs hung upside down from the ceiling, climbing (downward) into the wall: six concrete steps 1 m wide, the deepest against the wall,
    its underside 1.98 m up; steel nosings and an upside-down handrail. Every part is above 1.8 m."""
    rise, tread, n = 0.17, 0.2, 6
    for k in range(n):
        d0, d1 = k * tread, (k + 1) * tread
        y = H - (n - k) * rise
        part(f"Flight_{tag}_Step{k}", "Step_Concrete", lambda bm, d0=d0, d1=d1, y=y: w.box(bm, a - 0.5, a + 0.5, y, H, d0, d1))
        part(f"Flight_{tag}_Nose{k}", "Steel", lambda bm, d1=d1, y=y: w.box(bm, a - 0.5, a + 0.5, y - 0.003, y + 0.012, d1 - 0.04, d1 + 0.003))
    part(f"Flight_{tag}_Rail", "Steel", lambda bm: (cyl(bm, w.pt(a + 0.47, H - n * rise - 0.1 + 0.04, 0.05), w.pt(a + 0.47, H - 0.1, n * tread), 0.018, seg=8),
                                                    cyl(bm, w.pt(a + 0.47, H - 0.1, n * tread), w.pt(a + 0.47, H, n * tread), 0.012, seg=6)))
    hero(w, a, 2.3)


def dress_7():
    bl = bay_list()
    arrows = ["<", ">", ">", "<", "^"]
    for i, (w, a, hw, fi) in enumerate(bl):
        tag = f"{fi}_{i}"
        kind = i % 5
        if kind in (0, 3):                                 # a fire door to the stairs, flush in its frame: STAIRS L4, every one of them
            part(f"FireDoor_{tag}_Frame", "Steel", lambda bm, w=w, a=a: (w.box(bm, a - 0.53, a - 0.47, 0, 2.16, 0, 0.02), w.box(bm, a + 0.47, a + 0.53, 0, 2.16, 0, 0.02),
                                                                         w.box(bm, a - 0.53, a + 0.53, 2.1, 2.16, 0, 0.02)))
            part(f"FireDoor_{tag}_Leaf", "Leaf_Fire", lambda bm, w=w, a=a: w.box(bm, a - 0.47, a + 0.47, 0, 2.1, 0, 0.01))
            part(f"FireDoor_{tag}_Glass", "Leaf_Glass", lambda bm, w=w, a=a: w.box(bm, a + w.ra() * 0.15 - 0.08, a + w.ra() * 0.15 + 0.08, 1.2, 1.8, 0.01, 0.012))
            part(f"FireDoor_{tag}_Bar", "Steel", lambda bm, w=w, a=a: w.box(bm, a - 0.4, a + 0.4, 0.98, 1.04, 0.01, 0.045))
            part(f"FireDoor_{tag}_Sign", "Plastic_White", lambda bm, w=w, a=a: w.box(bm, a - 0.22, a + 0.22, 1.55, 1.7, 0.01, 0.014))
            part(f"FireDoor_{tag}_Sign_t", "Plastic_Black", lambda bm, w=w, a=a: wall_text(bm, w, "STAIRS  L4", a, 1.625, 0.014, 0.05, 0.002, 1.05))
            part(f"Bulkhead_{tag}", "Lamp_Emit", lambda bm, w=w, a=a: w.box(bm, a - 0.15, a + 0.15, 2.3, 2.45, 0.0, 0.08))
            part(f"Bulkhead_{tag}_Cage", "Plastic_Black", lambda bm, w=w, a=a: w.box(bm, a - 0.17, a + 0.17, 2.28, 2.3, 0.0, 0.085))
            light(f"L_bulkhead_{tag}", "POINT", w.pt(a, 2.37, 0.12), MOOD[K][1], size=0.06)
        elif kind == 1:
            flight_down(w, a, tag)
        elif kind == 2:                                    # EXIT, and an arrow that disagrees with the last one
            exit_sign(w, a, 2.25, tag, arrows[(i // 5) % len(arrows)])
            light(f"L_exit_{tag}", "POINT", w.pt(a, 2.3, 0.12), 6.0, color=(0.15, 1.0, 0.3), size=0.1)
            part(f"Level_{tag}", "Plastic_Black", lambda bm, w=w, a=a: wall_text(bm, w, "4", a, 1.45, 0.0, 0.5, 0.003))
        else:
            part(f"Level_{tag}", "Red_Paint", lambda bm, w=w, a=a: wall_text(bm, w, "L4", a, 1.45, 0.0, 0.32, 0.003))
    for fi, (w, r0, r1) in enumerate(face_walls()):
        if r1 - r0 < 0.8:
            continue
        part(f"Handrail_{fi}", "Steel", lambda bm, w=w, r0=r0, r1=r1: (
            cyl(bm, w.pt(r0 + 0.1, 0.92, 0.05), w.pt(r1 - 0.1, 0.92, 0.05), 0.018, seg=8),
            *[w.box(bm, c - 0.015, c + 0.015, 0.86, 0.92, 0.0, 0.05) for c in np.linspace(r0 + 0.2, r1 - 0.2, max(2, int((r1 - r0) / 1.4) + 1))]))
        rail_runs(w, r0, r1, [], 0.0, 0.1, 0.008, "Skirt_Steel", f"Skirting_{fi}")
    stains(7, 407)


DRESS = {1: dress_1, 2: dress_2, 3: dress_3, 4: dress_4, 5: dress_5, 6: dress_6, 7: dress_7}


# ---------------------------------------------------------------- build
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for d in (IMG, MATS, TILES, GEN, LEAF_MESH, DETAIL, TEXT_CACHE):
        d.clear()
    NAMES.clear()


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
    M = model(SCENE)
    layout_from_model(M)
    build_skin()
    build_leaves(M)
    DRESS[K]()
    if K != 7:                                             # an EXIT sign over the way on (the maze_07 one is among its own)
        exit_sign(Wall("x", A, -1), doors_z(M)["way_on"][1], 2.5, "way_on")
    else:
        exit_sign(Wall("x", A, -1), doors_z(M)["way_on"][1], 2.5, "way_on", ">")
    for t in list(TEXT_CACHE.values()):
        bpy.data.meshes.remove(t)
    TEXT_CACHE.clear()
    sc["detail"] = json.dumps({"axis": DETAIL["w"].axis, "p": DETAIL["w"].p, "s": DETAIL["w"].s, "a": DETAIL["a"], "y": DETAIL["y"]}) if DETAIL else ""
    w = sc.world or bpy.data.worlds.new("Night")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.01, 0.012, 0.02, 1)
    bg.inputs["Strength"].default_value = 0.0
    ensure_marker()
    for ob in LAYOUT.objects:
        ob.hide_render = True
    print(f"ART {SCENE} ({THEME[K]['title']}): {len(PROPS.objects)} props, {len(ARCH.objects)} arch boxes, {len(SKIN.objects)} skin meshes, "
          f"{len(DOORS.objects)} door nodes, {len(LIGHTS.objects)} lights")


def arrival():
    M = model(SCENE)
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


# ---------------------------------------------------------------- bake (floor 1's method)
NO_LIGHTMAP = {"Lamp_Emit", "Emergency_Emit", "Glass_Clear"}


def shell_mats():
    q, _ = scene_skin(SCENE)
    return {quad_material(SCENE, x) for x in q}


def arch_cols():
    return colliders(model(SCENE))


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
            cull_flush(tmp, cols)
            me = bpy.data.meshes.new("tmp")
            tmp.to_mesh(me)
            tmp.free()
            bm = by_mat.setdefault(mname, bmesh.new())
            bm.from_mesh(me)
            bpy.data.meshes.remove(me)
    for mname, bm in by_mat.items():
        name = "Props_" + mname
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        if not len(me.polygons):
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
    MARGIN_PX round it, shelf-packed at the highest density that fits the fixed page S."""
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


PROPS_MARGIN = 4      # px round each prop island (the props are thousands of small pieces: 8 px each would eat the page)
MIN_DENSITY = 32.0    # px/m: below this on one page, the props are split over two pages (by material)


def prop_islands(objs):
    """The props' lightmap islands, by connected piece (world space): a thin piece lying flat against something (a door leaf, a casing, a
    washer's front, a letter) is ONE island, projected along its thin axis: its front faces get the island, its sides become lines (no texels)
    and its back faces a point. Anything else gets up to six islands, its faces grouped by the axis they face. Returns
    [(obj, [(face index, [loop indices])], axis, sign_or_None, (u0, v0), (w, h), collapse set)]."""
    out = []
    for o in objs:
        mw = o.matrix_world
        me = o.data
        co = [mw @ v.co for v in me.vertices]
        g = [(c.x, c.z, -c.y) for c in co]                        # game coordinates
        vf = {}
        for p in me.polygons:
            for vi in p.vertices:
                vf.setdefault(vi, []).append(p.index)
        seen = set()
        for p0 in me.polygons:
            if p0.index in seen:
                continue
            comp, stack = [], [p0.index]
            seen.add(p0.index)
            while stack:
                f = stack.pop()
                comp.append(f)
                for vi in me.polygons[f].vertices:
                    for f2 in vf[vi]:
                        if f2 not in seen:
                            seen.add(f2)
                            stack.append(f2)
            info = []
            for f in comp:
                p = me.polygons[f]
                n = (mw.to_3x3() @ p.normal)
                n = (n.x, n.z, -n.y)
                ax = max(range(3), key=lambda i: abs(n[i]))
                info.append((f, ax, 1 if n[ax] > 0 else -1, p.area, n))
            pts = [g[vi] for f in comp for vi in me.polygons[f].vertices]
            ext = [max(q[i] for q in pts) - min(q[i] for q in pts) for i in range(3)]
            tot = sum(x[3] for x in info) or 1e-9
            by = {}
            for f, ax, sg, ar, n in info:
                by[(ax, sg)] = by.get((ax, sg), 0.0) + ar
            cen = {}
            for f, ax, sg, ar, n in info:
                c = me.polygons[f].center
                c = mw @ c
                cen.setdefault((ax, sg), []).append(((c.x, c.z, -c.y), ar))

            def facing_in(key):
                ax, sg = key
                pts_ = cen[key]
                tot_ = sum(a for _, a in pts_) or 1e-9
                c = [sum(p[i] * a for p, a in pts_) / tot_ for i in range(3)]
                c[ax] += sg * 0.03
                return any(all(o_["min"][i] < c[i] < o_["max"][i] for i in range(3)) for o_ in COLS)
            (bax, bsg), barea = max(by.items(), key=lambda kv: kv[1] * (0.3 if facing_in(kv[0]) else 1.0))
            groups = []
            if ext[bax] <= 0.08 and barea >= 0.4 * tot:
                fr = [f for f, ax, sg, ar, n in info if not (n[bax] * bsg < -0.5)]
                back = {f for f, ax, sg, ar, n in info if n[bax] * bsg < -0.5}
                groups.append((bax, fr, back))
            else:
                for (ax, sg) in sorted(by):
                    groups.append((ax, [f for f, a2, s2, ar, n in info if (a2, s2) == (ax, sg)], set()))
            for ax, faces_, back in groups:
                ui, vi_ = [i for i in range(3) if i != ax]
                q = [g[v] for f in faces_ for v in me.polygons[f].vertices]
                if not q:
                    continue
                u0, u1 = min(x[ui] for x in q), max(x[ui] for x in q)
                v0, v1 = min(x[vi_] for x in q), max(x[vi_] for x in q)
                out.append((o, faces_ + sorted(back), (ui, vi_), (u0, v0), (max(u1 - u0, 1e-3), max(v1 - v0, 1e-3)), back))
    return out


COLS = []


def islands_uv(objs, S, margin=PROPS_MARGIN):
    """Shelf-pack prop_islands() on the fixed page S at the highest density that fits; write the `lightmap` UV layer. Returns (S, density)."""
    isl = prop_islands(objs)

    def layout(D):
        boxes = []
        for i, (o, fs, axes, uv0, (w, h), back) in enumerate(isl):
            pw, ph = max(1, math.ceil(w * D)), max(1, math.ceil(h * D))
            rot = ph > pw
            if rot:
                pw, ph = ph, pw
            boxes.append((ph + 2 * margin, pw + 2 * margin, i, rot))
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
            place[i] = (x + margin, y + margin, rot)
            x += bw
            rowh = max(rowh, bh)
        return place
    lo, hi, best = 1.0, 400.0, None
    for _ in range(36):
        mid = (lo + hi) / 2
        pl = layout(mid)
        if pl:
            lo, best = mid, (mid, pl)
        else:
            hi = mid
    D, place = best
    for o in objs:
        uvs = o.data.uv_layers
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.new(name="lightmap", do_init=False)
        uvs["UVMap"].active_render = True
    for i, (o, fs, (ui, vi_), (u0, v0), (w, h), back) in enumerate(isl):
        x0, y0, rot = place[i]
        me = o.data
        mw = o.matrix_world
        uv = me.uv_layers["lightmap"].data
        for f in fs:
            p = me.polygons[f]
            for li in p.loop_indices:
                if f in back:
                    uv[li].uv = (x0 / S, y0 / S)
                    continue
                c = mw @ me.vertices[me.loops[li].vertex_index].co
                gq = (c.x, c.z, -c.y)
                a, b = (gq[ui] - u0) * D, (gq[vi_] - v0) * D
                if rot:
                    a, b = b, a
                uv[li].uv = ((x0 + a) / S, (y0 + b) / S)
    a3 = sum(world_area(o) for o in objs)
    print(f"  island pack: {len(isl)} islands, {a3:.1f} m2 at {D:.1f} px/m on {S}")
    return S, D


def prop_pages(objs):
    """The props on one page, or split over two (by material, balanced by area) when one page would give under MIN_DENSITY."""
    S = PAGES[SCENE][1]
    isl = prop_islands(objs)
    need = sum((w * MIN_DENSITY + 2 * PROPS_MARGIN) * (h * MIN_DENSITY + 2 * PROPS_MARGIN) for _, _, _, _, (w, h), _ in isl) * 1.15
    if need <= S * S:
        return [objs]
    groups = []                                          # objects that share a material must share a page (the material names its map)
    for o in objs:
        ms = {sl.material.name for sl in o.material_slots}
        hit = [g for g in groups if g[0] & ms]
        g = (set(ms), [o])
        for h in hit:
            g[0].update(h[0])
            g[1].extend(h[1])
            groups.remove(h)
        groups.append(g)
    a, b, sa, sb = [], [], 0.0, 0.0
    for ms, os_ in sorted(groups, key=lambda g: -sum(world_area(o) for o in g[1])):
        ar = sum(world_area(o) for o in os_)
        if sa <= sb:
            a += os_
            sa += ar
        else:
            b += os_
            sb += ar
    return [a, b]


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
    """One door leaf is baked for the shared leaf mesh (the entry: both doors' surrounds are alike)."""
    return [bpy.data.objects["DoorLeaf_entry"]]


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


def stage_bake():
    import time
    exp = make_export_objects()
    COLS[:] = arch_cols()
    bake_visibility()
    setup_cycles(SAMPLES, bake=True)
    sm = shell_mats()
    shell = [o for k, o in sorted(exp.items()) if k.startswith("Skin_")]
    props = [o for k, o in sorted(exp.items()) if not k.startswith("Skin_") and o.data.materials[0].name not in NO_LIGHTMAP] + leaf_reps()
    assert {o.data.materials[0].name for o in shell} <= sm
    clash = sm & {s.material.name for o in props for s in o.material_slots}
    assert not clash, f"shell materials used by props: {clash}"
    report = {}
    for n, objs in enumerate([shell] + prop_pages(props)):
        t0 = time.time()
        print(f"lightmap {n}: {[o.name for o in objs]}")
        S, dens = rect_uv(objs, PAGES[SCENE][0]) if n == 0 else islands_uv(objs, PAGES[SCENE][1])
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
        bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX if n == 0 else PROPS_MARGIN, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
        rgb = denoise_image(img, S)[..., :3]
        rgb_s, knee = shoulder(rgb)
        peak = rgb_s.max(axis=2)
        assert (peak > 1e-5).any(), f"lightmap {n} came out black"
        pc = np.percentile(peak[peak > 1e-5], [50, 90, 99, 99.5, 100])
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
                    if kind == "scenes" and st is idb and k == "detail":
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
    M = model(SCENE)
    (pos, look, pitch) = M.still
    p0 = (pos[0] + 0.1, E, pos[2])
    ln = math.hypot(*look)
    t0 = (p0[0] + look[0] / ln * 6, E - 0.35, p0[2] + look[1] / ln * 6)
    out = {"1_arrival": (p0, t0, 75), "2_wide": ((-7.0, 13.5, 10.0), (0.4, -1.0, 0.6), 46)}
    d = json.loads(bpy.context.scene.get("detail") or "{}")
    if d:
        w = Wall(d["axis"], d["p"], d["s"])
        cam = w.pt(d["a"] - 0.3, 1.55 if d["y"] < 2 else 1.3, 1.6)
        out["3_detail"] = (cam, w.pt(d["a"] + 0.05, d["y"], 0.0), 62)
    return out


def plan_box():
    return -A - 0.6, A + 0.6, -A - 0.6, A + 0.6


def high(o):
    return o.type == "MESH" and min((o.matrix_world @ v.co).z for v in o.data.vertices) > 2.3


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
    ceil_mats = {THEME[K]["ceiling"]}
    lid = [o for o in bpy.data.collections["Skin"].objects if o.data.materials[0].name in ceil_mats]
    for key, (loc, tgt, fov) in shots().items():
        if which not in ("all", key):
            continue
        hidden = []
        if key == "2_wide":                                # a cutaway: the ceiling and everything hung from it left out
            for o in lid + [o for o in bpy.data.collections["Props"].objects if high(o)]:
                if not o.hide_render:
                    o.hide_render = True
                    hidden.append(o)
        sc.view_settings.exposure = arg("--exposure", 0.0, float) + (1.3 if key == "2_wide" else 0.0)
        sc.camera = look_cam(key, loc, tgt, fov)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 1080, arg("--pct", 100, int)
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
        for o in hidden:
            o.hide_render = False
        print("STILL", key, path.stat().st_size, "q", q)
    if which in ("all", "plan"):
        x0, x1, z0, z1 = plan_box()
        span = x1 - x0
        cam = look_cam("plan", ((x0 + x1) / 2, 30.0, (z0 + z1) / 2), None, ortho=span)
        cam.rotation_euler = (0, 0, 0)
        sc.camera = cam
        hidden = []
        for o in lid + [o for o in list(bpy.data.collections["Props"].objects) if high(o) or o.name.startswith("decor_stain_ceiling")]:
            if not o.hide_render:
                o.hide_render = True
                hidden.append(o)
        for o in bpy.data.collections["Lights"].objects:     # the plan is lit flat from above, not by the maze's own lamps
            o.hide_render = True
        arch = bpy.data.collections["Arch"]
        arch.hide_render = False
        for o in arch.objects:
            o.hide_render = o.name.startswith(("Maze_Ceiling", "Maze_Floor"))
        world = sc.world
        bg = world.node_tree.nodes["Background"]
        old = bg.inputs["Strength"].default_value
        bg.inputs["Color"].default_value = (1, 1, 1, 1)
        bg.inputs["Strength"].default_value = 0.9
        W = 1600
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, W, 100
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 88
        path = d / "plan.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        strip_jpeg_comments(path)
        bg.inputs["Strength"].default_value = old
        bg.inputs["Color"].default_value = (0.01, 0.012, 0.02, 1)
        for o in hidden:
            o.hide_render = False
        for o in bpy.data.collections["Lights"].objects:
            o.hide_render = False
        for o in arch.objects:
            o.hide_render = False
        arch.hide_render = True
        print("PLAN", path, W)


# ---------------------------------------------------------------- main
def main():
    global SCENE, K
    for sc in arg("--scenes", "maze_01").split(","):
        SCENE, K = sc, kof(sc)
        print(f"==== {sc} ({THEME[K]['title']}) stage {STAGE}")
        if STAGE in ("art", "all", "preview"):
            build_all()
            save_blend()
        else:
            load_scene_file()
        if STAGE in ("bake", "all"):
            stage_bake()
        if STAGE in ("export", "all", "reexport"):
            stage_export()
        if STAGE in ("axes", "all"):
            stage_axes()
        if STAGE in ("check", "all", "reexport", "art", "preview"):
            stage_check()
        if STAGE in ("render", "all", "preview"):
            stage_render()
            save_blend()
        print(f"==== {sc} done")


main()
