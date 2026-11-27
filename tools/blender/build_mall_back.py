"""Dresses and lights three of the mall's back scenes, `construction`, `service_corridor` and `mirror_bathroom` (docs/BLENDER_AREAS.md, section 3,
step 2; docs/renders/construction/README.md), and places the connector kit's painted-sky hall in `sky_hall_01` to `sky_hall_04`. One script for
all of them: the three dressed scenes share the method, the materials, the textures and the part builders, and each gets two bakes on the same
lightmap UVs, as the mall atrium (`entrance`) has: the day set on `lightmap`, the emergency set (the mall locked at 20:00) on `lightmap_night`.

    blender -b --factory-startup --python tools/blender/build_mall_back.py -- --scenes construction,service_corridor,mirror_bathroom --stage all [--work <dir>]
    blender -b --factory-startup blender/scenes/<scene>.blend --python tools/blender/build_mall_back.py -- --scenes <scene> --stage bake|export|reexport|axes|check|render
    blender -b --factory-startup --python tools/blender/build_mall_back.py -- --scenes sky_hall_01,sky_hall_02,sky_hall_03,sky_hall_04 --stage kit
    python tools/blender/build_mall_back.py --pack <scene> [--work <dir>]       (no Blender: WebP lightmaps and textures -> world/)
    python tools/blender/build_mall_back.py --skin [scene ...]                    (no Blender: the seen shell, printed)

Stages: art (the layout objects from the greybox, the art, the lights; saves blender/scenes/<scene>.blend) -> bake (the seen shell and the merged
props on fixed lightmap PAGES, Cycles, OIDN, twice: day and night, 8-bit PNGs in the work folder) -> export (the GLB to the work folder; the layout
through tools/blender/export_scene.py, which must write the greybox's file unchanged) -> axes (the marker-cube check) -> check
(tools/blender/check_layout.py) -> render (docs/renders/<scene>/1_arrival, 2_wide, 3_detail.jpg and plan.jpg, the day set; a night arrival still
in the work folder for the owner's sheet). `all` runs them in that order; `--scenes` takes several, built one after the other in one Blender.

The layout is the greybox's, unchanged (tools/blender/build_mall_greybox.py): every COL_ box, DoorLeaf_, Link_/Arrive_, Marker_, Zone_ and Spot_ is
made from its model with the same names and numbers. The room's shell (walls, floors, ceilings, columns, the hoarding, the pit's floor) is skin():
the faces of those boxes that look into the air. Every other collider (the scaffold deck, its posts and rails, the site stair, the studs, the pallets,
the mixer, the pit's edge protection, the bins, the stalls, the vanity, the fire door) gets its own piece of art over its box. Everything else the
dressing adds is flush with a wall (4.5 cm at most), overhead (above 1.8 m), lower than 0.2 m, or a passable decor_ piece (cloth, tripods, the WCs),
so no collider is added.

The sky halls: the kit's sky_hall (blender/kit/sky_hall.blend) placed in each at (0, 0, 0), yaw 0, by tools/blender/kit_place.py; the suffix it adds
is taken off again, so the doors, links and markers keep the greybox's ids (entry, exit). Their art is the kit's: the page draws
world/kit/sky_hall.glb at (0, 0, 0), yaw 0 in each (no copy per scene); the .blend links the kit's Art collection for the layout check. The kit's
hall is lit by its own painted sky at every hour, so it has one light set.
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import build_mall_greybox as GB  # noqa: E402

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


SCENES = ("construction", "service_corridor", "mirror_bathroom")
SKY = tuple(f"sky_hall_{k:02d}" for k in range(1, 5))
FRONT = 0.004
PROUD = 0.045                   # the most a wall piece may stand out (the layout check allows 5 cm)

TITLE = {"construction": "The construction zone", "service_corridor": "The service corridor", "mirror_bathroom": "The mirror bathroom"}

# the shell: the colliders that are skinned (by name prefix); every other collider gets its own art
SHELL = {"construction": ("Site_", "Column", "Hoarding_", "Pit_Floor"),
         "service_corridor": ("Corridor_", "BinBay_", "Spur_", "FreightCar_"),
         "mirror_bathroom": ("Restroom_",)}
SPLITS = {"construction": (), "service_corridor": (1.2,), "mirror_bathroom": (2.1,)}


def R(region, x0, x1, y0, y1, z0, z1):
    return {"region": region, "min": [x0, y0, z0], "max": [x1, y1, z1]}


def air(sc):
    """The rooms' air (the first region a point is in names it): the shell's faces that look into one of these are seen."""
    if sc == "construction":
        return [R("pit", 7.5, 10.5, -1.2, 0.0, 2.0, 5.0), R("doorhole", -3.6, -2.4, 0.0, 2.16, 9.0, 9.2),
                R("doorhole", -5.55, -4.45, 3.0, 5.16, -9.2, -9.0), R("room", -12.0, 12.0, 0.0, 6.5, -9.0, 9.0)]
    if sc == "service_corridor":
        return [R("doorhole", a - 0.47, a + 0.47, 0.0, 2.16, 1.0, 1.2) for a in (-22.0, -8.0, 4.0, 12.0)] + \
               [R("doorhole", 18.4, 19.6, 0.0, 2.2, -12.2, -12.0), R("car", 17.9, 20.1, 0.0, 2.4, -14.6, -12.2),
                R("spur", 18.0, 20.0, 0.0, 3.0, -12.0, -1.0), R("bins", -17.0, -13.0, 0.0, 3.0, -2.4, -1.0),
                R("corridor", -26.0, 20.0, 0.0, 3.0, -1.0, 1.0)]
    return [R("doorhole", -4.07, -3.13, 0.0, 2.16, 4.0, 4.2), R("room", -5.0, 5.0, 0.0, 3.0, -4.0, 4.0)]


# ================================================================ the seen shell (pure Python)
def model(sc):
    return GB.build(sc)


def colliders(M):
    return [{"name": b["name"], "min": list(b["min"]), "max": list(b["max"])} for b in M.boxes if b["col"]]


def shell_cols(sc, M):
    return [c for c in colliders(M) if c["name"].startswith(SHELL[sc])]


def object_cols(sc, M):
    return [c for c in colliders(M) if not c["name"].startswith(SHELL[sc])]


def _inside(p, b, e=1e-4):
    return all(b["min"][i] + e < p[i] < b["max"][i] - e for i in range(3))


def _within(p, b, e=1e-7):
    return all(b["min"][i] - e <= p[i] <= b["max"][i] + e for i in range(3))


def _band_break(a, k, v, splits_y):
    return a != 1 and k == 1 and any(abs(v - y) < 1e-9 for y in splits_y)


def skin(cols, airs, splits_y=()):
    """Every collider face that looks into the air, as merged rectangles (floor 1's and the mazes' method):
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


def scene_skin(sc):
    M = model(sc)
    return skin(shell_cols(sc, M), air(sc), SPLITS[sc]), M


def quad_material(sc, q):
    up, down = q["axis"] == 1 and q["side"] > 0, q["axis"] == 1 and q["side"] < 0
    reg, coll = q["region"], q["coll"]
    if sc == "construction":
        if coll.startswith("Hoarding"):
            return "Hoarding_Ply"
        if coll.startswith("Column"):
            return "Column_Concrete"
        if reg == "pit":
            return "Pit_Concrete"
        if up:
            return "Slab_Concrete"
        if down and reg != "doorhole":
            return "Soffit_Concrete"
        return "Block_Bare"
    if sc == "service_corridor":
        if reg == "car":
            return "Car_Plate" if up else "Car_Ceiling" if down else "Car_Steel"
        if up:
            return "Floor_Epoxy"
        if down:
            return "Soffit_Paint" if reg != "doorhole" else "Jamb_Paint"
        if reg == "doorhole":
            return "Jamb_Paint"
        return "Block_Dado" if vrange(q)[0][0] < 1.2 - 1e-6 else "Block_Paint"
    if up:
        return "Tile_Floor_Bath"
    if down:
        return "Ceiling_Grid" if reg != "doorhole" else "Paint_Bath"
    return "Tile_Wall_Bath" if vrange(q)[0][0] < 2.1 - 1e-6 else "Paint_Bath"


def summary(sc):
    q, M = scene_skin(sc)
    by = {}
    for x in q:
        m = quad_material(sc, x)
        n, a = by.get(m, (0, 0.0))
        by[m] = (n + 1, a + area(x))
    print(f"SKIN {sc}: {len(q)} quads, {sum(area(x) for x in q):.1f} m2; {len(shell_cols(sc, M))} shell colliders, "
          f"{len(object_cols(sc, M))} object colliders: {sorted(c['name'] for c in object_cols(sc, M))}")
    for m, (n, a) in sorted(by.items()):
        print(f"  {m:18s} {n:4d} quads {a:7.1f} m2")


# ================================================================ paths
MARGIN_PX = 8
TEXDIR = ROOT / "blender/textures"
STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 1024, int)
NIGHT_SAMPLES = arg("--night-samples", None, int) or SAMPLES
DEVICE = arg("--device", "auto")
PAGES = [2048, 2048]
NIGHT_OFFSET = 2                 # the night set of map n is <scene>_<n + 2>
WHITE_CAP = 12.0
SHOULDER = (70.0, 2.5)
SCENE = None


def work():
    p = Path(arg("--work", str(Path(os.environ.get("TEMP", tempfile.gettempdir())) / "farway_mall_back")))
    if not p.is_absolute():
        p = ROOT / p
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
        for s in [a for a in args if a in SCENES] or SCENES:
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


# ---------------------------------------------------------------- generated images (own work: numpy, fixed seeds)
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


def gen_blocks(src, seed, span=1.6, bw=0.4, bh=0.2, joint=0.22, vary=0.08):
    """Blockwork: `bw` x `bh` m blocks in stretcher bond with mortar joints, `span` m square, drawn over a CC0 texture from the repo. Each block a
    little lighter or darker than the next."""
    s = load_pixels(src)
    Hh, W = s.shape[:2]
    rng = np.random.default_rng(seed)
    t = (np.arange(Hh) + 0.5) / Hh * span
    Y, X = np.meshgrid(t, t, indexing="ij")
    row = np.floor(Y / bh)
    xo = X + (row % 2) * bw / 2
    j = np.minimum(np.abs(np.mod(Y, bh)), np.abs(np.mod(Y, bh) - bh))
    j = np.minimum(j, np.minimum(np.abs(np.mod(xo, bw)), np.abs(np.mod(xo, bw) - bw)))
    bid = (np.floor(xo / bw) * 7 + row * 13) % 9
    tone = 1 + vary * (bid / 8 - 0.5)
    return np.clip(s * tone[..., None] * (1 - joint * smooth(0.008, 0.003, j))[..., None], 0, 1)


def gen_tile(seed=106, size=0.15, grout=(150, 146, 136), face=(226, 224, 214), span=0.9, speck=0.0):
    """Square tiles with grout lines, `span` m square (floor 1's bathroom tile, with optional specks for a porcelain floor)."""
    Hh = W = 1024
    rng = np.random.default_rng(seed)
    t = (np.arange(Hh) + 0.5) / Hh * span
    Y, X = np.meshgrid(t, t, indexing="ij")
    gx = np.minimum(np.mod(X, size), size - np.mod(X, size))
    gy = np.minimum(np.mod(Y, size), size - np.mod(Y, size))
    g = np.minimum(gx, gy)
    tid = (np.floor(X / size) * 7 + np.floor(Y / size) * 13) % 6
    img = np.broadcast_to(col(*face), (Hh, W, 3)) * (0.9 + 0.02 * tid[..., None]) / 0.95
    if speck:
        fine = vnoise(Hh, W, rng, 2, 220)
        img = img * (1 - speck * smooth(0.6, 0.75, fine))[..., None]
    img = lerp(img, col(*grout), smooth(0.003, 0.0012, g))
    n = vnoise(Hh, W, rng, 4, 4)
    img *= (0.94 + 0.08 * n)[..., None]
    return np.clip(img, 0, 1)


def gen_stripes(c1, c2, S=256, n=4, slant=1.0):
    """Diagonal bands of two colours (hazard paint, barrier tape), one repeat across the image."""
    t = (np.arange(S) + 0.5) / S
    Y, X = np.meshgrid(t, t, indexing="ij")
    v = np.mod((X + slant * Y) * n, 1.0)
    m = smooth(0.48, 0.52, v) - smooth(0.98, 1.0, v)
    return np.clip(lerp(np.broadcast_to(col(*c1), (S, S, 3)), col(*c2), m), 0, 1)


def gen_checker():
    """A steel checker plate: raised diagonal lozenges on a grey plate, 0.3 m square."""
    S = 512
    rng = np.random.default_rng(311)
    t = (np.arange(S) + 0.5) / S
    Y, X = np.meshgrid(t, t, indexing="ij")
    img = np.broadcast_to(col(132, 134, 136), (S, S, 3)).copy()
    for (ox, oy, ang) in ((0.0, 0.0, 0.785), (0.5, 0.5, -0.785)):
        P = 0.25
        lx, ly = np.mod(X + ox * P, P) - P / 2, np.mod(Y + oy * P, P) - P / 2
        u, v = lx * math.cos(ang) + ly * math.sin(ang), -lx * math.sin(ang) + ly * math.cos(ang)
        lz = smooth(1.0, 0.8, (u / 0.085) ** 2 + (v / 0.018) ** 2)
        img = lerp(img, col(178, 180, 182), lz)
    n = vnoise(S, S, rng, 4, 3)
    return np.clip(img * (0.86 + 0.2 * n)[..., None], 0, 1)


def gen_bag():
    """A 25 kg cement bag's paper: grey kraft, a printed red band and a darker logo panel (UV: the whole bag face)."""
    Hh, W = 256, 512
    rng = np.random.default_rng(312)
    y = (np.arange(Hh) + 0.5) / Hh
    x = (np.arange(W) + 0.5) / W
    Y, X = np.meshgrid(y, x, indexing="ij")
    img = np.broadcast_to(col(178, 172, 158), (Hh, W, 3)).copy()
    img = lerp(img, col(160, 40, 34), smooth(0.02, 0.0, np.abs(Y - 0.62) - 0.08))
    img = lerp(img, col(74, 76, 80), ((np.abs(X - 0.5) < 0.16) & (np.abs(Y - 0.35) < 0.12)).astype(float))
    n = vnoise(Hh, W, rng, 5, 3)
    return np.clip(img * (0.86 + 0.22 * n)[..., None], 0, 1)


def gen_decal(seed, rgb, size=512, a_in=0.3, a_rim=0.45, falloff=(0.78, 0.6)):
    """A soft stain or a drift of dust (RGBA): a ragged blob with a rim."""
    rng = np.random.default_rng(seed)
    t = (np.arange(size) + 0.5) / size * 2 - 1
    Y, X = np.meshgrid(t, t, indexing="ij")
    n = vnoise(size, size, rng, 5, 3)
    r = np.sqrt(X ** 2 + Y ** 2) + 0.45 * (n - 0.5)
    inside = smooth(falloff[0], falloff[1], r)
    rim = smooth(0.07, 0.0, np.abs(r - 0.66))
    rgbs = np.broadcast_to(col(*rgb), (size, size, 3)) * (0.85 + 0.3 * n)[..., None]
    a = np.clip(a_in * inside + a_rim * rim * smooth(0.85, 0.6, r), 0, 0.85)
    return np.concatenate([np.clip(rgbs, 0, 1), a[..., None]], axis=2)


def gen_brushed():
    Hh = W = 256
    rng = np.random.default_rng(108)
    n = vnoise(Hh, W, rng, 3, 2)
    streak = np.repeat(vnoise(Hh, 8, rng, 3, 64), W // 8, axis=1)
    return np.clip((0.7 + 0.12 * streak + 0.08 * n)[..., None] * np.ones(3), 0, 1)


def gen_crack():
    """A hairline crack (RGBA), a branching dark line on transparent, for the tile under the portal mirror."""
    Hh, W = 256, 128
    rng = np.random.default_rng(313)
    img = np.zeros((Hh, W, 4))
    img[..., :3] = col(40, 38, 36)
    y = np.arange(Hh)
    x = W / 2 + np.cumsum(rng.normal(0, 1.1, Hh))
    for yy, xx in zip(y, x):
        xi = int(round(xx))
        for dx in (-1, 0, 1):
            if 0 <= xi + dx < W:
                img[yy, xi + dx, 3] = max(img[yy, xi + dx, 3], 0.85 if dx == 0 else 0.35)
    bx = x[90] + np.cumsum(rng.normal(0.6, 0.9, 70))
    for k, xx in enumerate(bx):
        yy, xi = 90 + k, int(round(xx))
        if 0 <= xi < W and yy < Hh:
            img[yy, xi, 3] = max(img[yy, xi, 3], 0.6)
    return img


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
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.name = "Principled BSDF"
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


CONC2, CONC, PLY, LINEN = "kit/concrete_floor_02_diff_1k.jpg", "factory_floor/concrete_floor_diff.jpg", "kit/plywood_diff_1k.jpg", "kit/rough_linen_diff_512.jpg"
WALLP, PLAST, CEILT, GRIME = "main_floor/wall_paint_diff.jpg", "laboratory/wall_paint_diff.jpg", "laboratory/ceiling_tile_diff.jpg", "factory_floor/paint_grime_diff.jpg"
WOOD, DWOOD, SHUTTER = "factory_floor/wood_diff.jpg", "apartment/dark_wood_diff_1k.jpg", "kit/painted_metal_shutter_diff_1k.jpg"

LAMP_EMIT = 3.0               # Lamp_Emit's exported strength: the working lights (on by day, off while the mall is locked)
EMERG_EMIT = 5.0              # Emergency_Emit's exported strength: the emergency fittings (on only while the mall is locked)
NO_LIGHTMAP = {"Lamp_Emit", "Emergency_Emit", "Sign_Exit", "Reader_Glow", "Glass_Clear"}


def make_materials():
    g = {k: mk_image(k, f()) for k, f in (
        ("gen_block_bare", lambda: gen_blocks(CONC2, 401, joint=0.22, vary=0.1)),
        ("gen_block_paint", lambda: gen_blocks(WALLP, 402, joint=0.18, vary=0.03)),
        ("gen_tile_white", lambda: gen_tile(403, 0.15, (168, 166, 160), (234, 234, 228), 0.9)),
        ("gen_tile_floor", lambda: gen_tile(404, 0.3, (88, 88, 86), (150, 150, 146), 1.2, speck=0.25)),
        ("gen_hazard", lambda: gen_stripes((222, 172, 24), (26, 24, 22), n=4)),
        ("gen_tape", lambda: gen_stripes((214, 40, 34), (236, 234, 228), n=6, slant=0.3)),
        ("gen_checker", gen_checker), ("gen_bag", gen_bag), ("gen_brushed", gen_brushed), ("gen_crack", gen_crack),
        ("gen_dust", lambda: gen_decal(405, (170, 164, 150), a_in=0.32, a_rim=0.2, falloff=(0.95, 0.4))),
        ("gen_stain", lambda: gen_decal(406, (52, 46, 40), a_in=0.22, a_rim=0.4)),
        ("gen_cement", lambda: gen_decal(407, (196, 194, 188), a_in=0.6, a_rim=0.3, falloff=(0.7, 0.45))))}
    # ---- the shell (each names a lightmap; no prop uses one)
    material("Slab_Concrete", tex=CONC2, tint=srgb_lin("#d2cfc8"), rough=0.9, tile=3.0)
    material("Soffit_Concrete", tex=CONC2, tint=srgb_lin("#c8c6c0"), rough=0.95, tile=3.5)
    material("Pit_Concrete", tex=CONC, tint=srgb_lin("#b8b4ac"), rough=0.95, tile=2.0)
    material("Column_Concrete", tex=CONC2, tint=srgb_lin("#d8d4cc"), rough=0.9, tile=1.5)
    material("Block_Bare", img=g["gen_block_bare"], tint=srgb_lin("#e6e8e6"), rough=0.95, tile=1.6)
    material("Hoarding_Ply", tex=PLY, tint=srgb_lin("#f2e4cc"), rough=0.85, tile=1.2)
    material("Floor_Epoxy", tex=CONC, tint=srgb_lin("#a8aca8"), rough=0.5, tile=2.5)
    material("Soffit_Paint", tex=PLAST, tint=srgb_lin("#d8d8d2"), rough=0.9, tile=2.0)
    material("Block_Dado", img=g["gen_block_paint"], tint=srgb_lin("#7c8a80"), rough=0.6, tile=1.6)
    material("Block_Paint", img=g["gen_block_paint"], tint=srgb_lin("#e2dcc8"), rough=0.75, tile=1.6)
    material("Jamb_Paint", tex=WALLP, tint=srgb_lin("#5a6a64"), rough=0.5, tile=1.0)
    material("Car_Steel", img=g["gen_brushed"], tint=srgb_lin("#b8bcbe"), rough=0.4, metal=0.6, tile=0.6)
    material("Car_Plate", img=g["gen_checker"], rough=0.45, metal=0.5, tile=0.3)
    material("Car_Ceiling", tex=PLAST, tint=srgb_lin("#c8c8c4"), rough=0.8, tile=1.0)
    material("Tile_Floor_Bath", img=g["gen_tile_floor"], rough=0.4, tile=1.2)
    material("Tile_Wall_Bath", img=g["gen_tile_white"], rough=0.25, tile=0.9)
    material("Paint_Bath", tex=PLAST, tint=srgb_lin("#e2e0d6"), rough=0.85, tile=2.0)
    material("Ceiling_Grid", tex=CEILT, tint=srgb_lin("#ecece6"), rough=0.9, tile=0.6)
    # ---- the props
    material("Scaffold_Tube", img=g["gen_brushed"], tint=srgb_lin("#9a9ea0"), rough=0.45, metal=0.7, tile=0.5)
    material("Coupler", tex=GRIME, tint=srgb_lin("#55585a"), rough=0.5, metal=0.6, tile=0.3)
    material("Scaffold_Board", tex=PLY, tint=srgb_lin("#d6b888"), rough=0.85, tile=1.0)
    material("Board_End", color=srgb_lin("#8a8e90"), rough=0.4, metal=0.7)
    material("Timber_Stud", tex=WOOD, tint=srgb_lin("#f4dcb4"), rough=0.8, tile=0.8)
    material("Ply_Pallet", tex=WOOD, tint=srgb_lin("#d8b890"), rough=0.85, tile=0.8)
    material("Plasterboard", tex=PLAST, tint=srgb_lin("#ddd6cc"), rough=0.9, tile=1.2)
    material("Tile_Glazed", img=g["gen_tile_white"], tint=srgb_lin("#f0f2f0"), rough=0.2, tile=0.9)
    material("Adhesive", tex=CONC, tint=srgb_lin("#a8a8a2"), rough=0.95, tile=0.6)
    material("Cement_Bag", img=g["gen_bag"], rough=0.9, tile=1.0)
    material("Skip_Paint", tex=GRIME, tint=srgb_lin("#d4a420"), rough=0.6, metal=0.3, tile=1.2)
    material("Mixer_Paint", tex=GRIME, tint=srgb_lin("#d06a24"), rough=0.5, metal=0.3, tile=0.8)
    material("Lift_Paint", tex=GRIME, tint=srgb_lin("#3a5a8a"), rough=0.5, metal=0.3, tile=0.8)
    material("Rail_Yellow", tex=GRIME, tint=srgb_lin("#e0b828"), rough=0.5, metal=0.2, tile=0.6)
    material("Rubble", tex=CONC2, tint=srgb_lin("#a8a49c"), rough=0.95, tile=0.5)
    material("Rubber_Black", color=srgb_lin("#1c1c1c"), rough=0.7)
    material("Hazard_Paint", img=g["gen_hazard"], rough=0.6, tile=0.4)
    material("Barrier_Tape", img=g["gen_tape"], rough=0.5, tile=0.5)
    material("Sheet_Cloth", tex=LINEN, tint=srgb_lin("#e8e2d4"), rough=1.0, tile=0.8)
    material("Cable_Black", color=srgb_lin("#202020"), rough=0.5)
    material("Cable_Orange", color=srgb_lin("#d0661c"), rough=0.5)
    material("Plastic_White", color=srgb_lin("#d6d2c6"), rough=0.5)
    material("Plastic_Black", color=srgb_lin("#1a1a1a"), rough=0.4)
    material("Plastic_Yellow", color=srgb_lin("#d8b020"), rough=0.5)
    material("Sign_White", color=srgb_lin("#e8e6de"), rough=0.6)
    material("Sign_Red", color=srgb_lin("#b22a22"), rough=0.6)
    material("Sign_Blue", color=srgb_lin("#20488a"), rough=0.6)
    material("Sign_Green", color=srgb_lin("#1e7a3a"), rough=0.6)
    material("Sign_Ink", color=srgb_lin("#22221f"), rough=0.6)
    material("Chalk_Blue", color=srgb_lin("#3c6cc0"), rough=1.0)
    material("Spray_Red", color=srgb_lin("#c02a20"), rough=1.0)
    material("Steel_Galv", img=g["gen_brushed"], tint=srgb_lin("#a8acae"), rough=0.4, metal=0.7, tile=0.4)
    material("Steel_Dark", tex=GRIME, tint=srgb_lin("#46494c"), rough=0.5, metal=0.6, tile=0.4)
    material("Frame_Steel", tex=WALLP, tint=srgb_lin("#55625c"), rough=0.45, metal=0.3, tile=1.0)
    material("Leaf_White", tex=PLAST, tint=srgb_lin("#eeece4"), rough=0.45, tile=1.0)
    material("Leaf_Ply", tex=PLY, tint=srgb_lin("#e8d4b0"), rough=0.85, tile=1.2)
    material("Leaf_Steel", tex=SHUTTER, tint=srgb_lin("#8c9a92"), rough=0.45, metal=0.3, tile=1.2)
    material("Leaf_Fire", tex=SHUTTER, tint=srgb_lin("#b8483a"), rough=0.45, metal=0.3, tile=1.2)
    material("Leaf_Laminate", tex=DWOOD, tint=srgb_lin("#e4c8a8"), rough=0.4, tile=1.0)
    material("Gate_Steel", tex=GRIME, tint=srgb_lin("#6c7072"), rough=0.45, metal=0.6, tile=0.5)
    material("Glass_Dark", color=srgb_lin("#262c30"), rough=0.15)
    material("Brass", img=g["gen_brushed"], tint=srgb_lin("#b48c4c"), rough=0.35, metal=0.9, tile=0.3)
    material("Chrome", img=g["gen_brushed"], tint=srgb_lin("#c8cacc"), rough=0.2, metal=0.9, tile=0.3)
    material("Pipe_Green", tex=WALLP, tint=srgb_lin("#3e6a4a"), rough=0.4, tile=1.0)
    material("Pipe_Red", tex=WALLP, tint=srgb_lin("#a02c24"), rough=0.4, tile=1.0)
    material("Pipe_Lagged", tex=LINEN, tint=srgb_lin("#c8c4b8"), rough=0.9, tile=0.6)
    material("Bin_Green", tex=GRIME, tint=srgb_lin("#3a6a3c"), rough=0.6, tile=0.8)
    material("Bin_Grey", tex=GRIME, tint=srgb_lin("#5c6064"), rough=0.6, tile=0.8)
    material("Bag_Black", color=srgb_lin("#161616"), rough=0.35)
    material("Laminate_Stall", tex=PLAST, tint=srgb_lin("#8e9ea6"), rough=0.35, tile=1.2)
    material("Counter_Solid", tex=CONC2, tint=srgb_lin("#e4e2dc"), rough=0.3, tile=1.5)
    material("Ceramic_White", color=srgb_lin("#ecece8"), rough=0.15)
    material("Mirror_Glass", tex=PLAST, tint=srgb_lin("#6c7276"), rough=0.35, tile=3.0)   # flat, dark silver: the page swaps it
    material("Frame_Chrome", img=g["gen_brushed"], tint=srgb_lin("#c4c6c8"), rough=0.25, metal=0.85, tile=0.3)
    material("Frame_Bronze", img=g["gen_brushed"], tint=srgb_lin("#6a5236"), rough=0.5, metal=0.75, tile=0.3)   # Mirror_4's, the tell
    material("Cardboard", tex=PLY, tint=srgb_lin("#b08a5c"), rough=0.9, tile=0.6)
    material("Beam_Concrete", tex=CONC2, tint=srgb_lin("#d0ccc4"), rough=0.9, tile=1.5)
    material("Tile_Skirt", img=g["gen_tile_white"], tint=srgb_lin("#6a6c6e"), rough=0.3, tile=0.9)
    material("Cork", tex=WOOD, tint=srgb_lin("#b08050"), rough=0.95, tile=0.4)
    material("Paper", color=srgb_lin("#e8e4d8"), rough=0.9)
    material("Decal_Dust", img=g["gen_dust"], rough=1.0, img_alpha=True)
    material("Decal_Stain", img=g["gen_stain"], rough=1.0, img_alpha=True)
    material("Decal_Cement", img=g["gen_cement"], rough=1.0, img_alpha=True)
    material("Decal_Crack", img=g["gen_crack"], rough=1.0, img_alpha=True)
    material("Lamp_Emit", color=(0.92, 0.9, 0.84), rough=0.6, emit=((1.0, 0.94, 0.84), LAMP_EMIT))
    material("Lamp_Dead", color=srgb_lin("#a49c88"), rough=0.6)
    material("Emergency_Emit", color=(0.92, 0.95, 1.0), rough=0.3, emit=((0.86, 0.93, 1.0), EMERG_EMIT))
    material("Sign_Exit", color=(0.0, 0.0, 0.0), rough=0.4, emit=((0.08, 0.85, 0.3), 2.5))        # the EXIT signs: maintained, always lit
    material("Reader_Glow", color=(0.0, 0.0, 0.0), rough=0.4, emit=((1.0, 0.08, 0.04), 4.0))     # the keycard reader's red light, always lit
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


def hexa(bm, pts):
    """A solid from 8 game points (bottom four then top four, each counter-clockwise seen from above): a skip, a sloped stringer."""
    vs = [bm.verts.new(B(p)) for p in pts]
    for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        bm.faces.new([vs[i] for i in f])


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


ART = PROPS = ARCH = SKIN = DOORS = LAYOUT = STANDIN = LIGHTS = None


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
    cu.resolution_u = 2
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
    Rr, U, N = Vector(B(right)), Vector(B(up)), Vector(B(normal))
    O = B(origin)
    M = Matrix(((Rr.x, U.x, N.x, O.x), (Rr.y, U.y, N.y, O.y), (Rr.z, U.z, N.z, O.z), (0, 0, 0, 1)))
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


def wall_decal(name, mat, w, a0, a1, y0, y1, d=0.002):
    a0, a1 = (a0, a1) if w.ra() > 0 else (a1, a0)
    return flat_quad(name, mat, [w.pt(a0, y0, d), w.pt(a1, y0, d), w.pt(a1, y1, d), w.pt(a0, y1, d)], [(0, 0), (1, 0), (1, 1), (0, 1)], normal=w.normal())


def light(name, kind, pos, power, color=(1.0, 0.93, 0.82), size=0.05, aim=None, sets="day", shape="DISK", size_y=None, spot=None):
    d = bpy.data.lights.new(name, kind)
    d.energy = power
    d.color = color
    if kind == "AREA":
        d.shape = shape
        d.size = size
        if size_y is not None:
            d.size_y = size_y
    else:
        d.shadow_soft_size = size
    if kind == "SPOT" and spot:
        d.spot_size, d.spot_blend = math.radians(spot), 0.5
    ob = bpy.data.objects.new(uname(name), d)
    ob.location = B(pos)
    if aim is not None:
        ob.rotation_euler = (B(aim) - B(pos)).to_track_quat("-Z", "Y").to_euler()
    bpy.data.collections["Lights_Day" if sets == "day" else "Lights_Night"].objects.link(ob)
    return ob


def multi_part(name, pieces, coll=None):
    """One object with several materials: pieces = [(material, build)]; each face keeps its piece's material and its box UVs at that material's tile."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    mats = []
    for mat, build in pieces:
        tmp = bmesh.new()
        build(tmp)
        bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces)
        tmp.loops.layers.uv.new("UVMap")
        box_uv(tmp, TILES.get(mat, 1.0))
        if mat not in mats:
            mats.append(mat)
        for f in tmp.faces:
            f.material_index = mats.index(mat)
            f.smooth = False
        me = bpy.data.meshes.new("tmp")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    me = bpy.data.meshes.new(uname(name))
    bm.to_mesh(me)
    bm.free()
    for mat in mats:
        me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(me.name, me)
    (coll or PROPS).objects.link(ob)
    return ob


def slab_x(bm, yz, x0, x1):
    """A prism along x from x0 to x1 over a quad in the (y, z) plane (four (y, z) points in order): a sloped stringer, a skip's side."""
    hexa_pts = [(x0, y, z) for y, z in yz] + [(x1, y, z) for y, z in yz]
    vs = [bm.verts.new(B(p)) for p in hexa_pts]
    for f in ((0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)):
        bm.faces.new([vs[i] for i in f])


def oriented(bm, c, size, yaw_b, pitch=0.0):
    """A box of `size` (along its facing, across, up) at game point c, its facing turned yaw_b about Blender Z and pitched down by `pitch`."""
    m = Matrix.Translation(B(c)) @ Matrix.Rotation(yaw_b, 4, "Z") @ Matrix.Rotation(pitch, 4, "Y") @ Matrix.Diagonal((*size, 1.0))
    bmesh.ops.create_cube(bm, size=1.0, matrix=m)


def facing_yaw(frm, to):
    """Blender yaw (about Z) and downward pitch of the direction from game point frm to game point to."""
    d = B(to) - B(frm)
    return math.atan2(d.y, d.x), math.atan2(-d.z, math.hypot(d.x, d.y))


def polyline(bm, pts, r, seg=6):
    for p0, p1 in zip(pts, pts[1:]):
        cyl(bm, p0, p1, r, seg=seg, cap=False)


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
    """Every COL_ box, Zone_ box and empty (Marker_, Link_/Arrive_, Spot_) of the greybox, by its names. The shell's colliders also get a plain
    stand-in in `Arch` (for the plan and the layout check's cover rule; the skin shows them); the other colliders are covered by their own art."""
    shell = {c["name"] for c in shell_cols(SCENE, M)}
    for b in M.boxes:
        if b.get("zone"):
            col_box(b["name"], b["min"], b["max"])
            continue
        if b["col"]:
            col_box("COL_" + b["name"], b["min"], b["max"])
            if b["name"] in shell:
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
    for x in quads:                                      # long quads cut into pieces of 4 m at most (one 46 m island would shrink the atlas)
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


# ---------------------------------------------------------------- the door leaves: one mesh per kind and size, shared by every leaf of it
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


def leaf_style(name):
    d = name[len("DoorLeaf_"):]
    if SCENE == "construction":
        return "ply" if d == "wing_books" else "sky"
    if SCENE == "service_corridor":
        return "gate" if d.startswith("network") else "steel"
    return "stall" if d.startswith("stall") else "restroom"


def leaf_mesh(style, width, height):
    """A leaf in its own frame: local +X runs from the hinge along the leaf, local Y is its thickness (centred on the hinge line), z is up; the
    greybox's leaves are placed the same way. Furniture is on both faces unless said."""
    key = (style, round(width, 3), round(height, 3))
    if key in LEAF_MESH:
        return LEAF_MESH[key]
    pieces = []

    def bx(x0, x1, ya, yb, z0, z1, mat):
        mm = bmesh.new()
        mm.loops.layers.uv.new("UVMap")
        bmesh.ops.create_cube(mm, size=1.0, matrix=Matrix.Translation(((x0 + x1) / 2, (ya + yb) / 2, (z0 + z1) / 2)) @ Matrix.Diagonal((x1 - x0, yb - ya, z1 - z0, 1)))
        pieces.append((mm, mat))

    def both(x0, x1, t0, t1, z0, z1, mat):
        bx(x0, x1, t0, t1, z0, z1, mat)
        bx(x0, x1, -t1, -t0, z0, z1, mat)
    w, h = width - 0.006, height - 0.008
    if style == "sky":                                    # the kit hall's white panel door, a brass lever both sides
        th = 0.02
        bx(0.003, w, -th, th, 0.006, h, "Leaf_White")
        for z0, z1 in ((0.2, 0.95), (1.15, h - 0.18)):
            for x0, x1 in ((0.11, w / 2 - 0.05), (w / 2 + 0.05, w - 0.11)):
                both(x0, x1, th, th + 0.006, z0, z1, "Leaf_White")
        both(w - 0.11, w - 0.06, th, th + 0.01, 0.95, 1.1, "Brass")
        both(w - 0.2, w - 0.06, th + 0.01, th + 0.05, 1.0, 1.03, "Brass")
    elif style == "ply":                                  # the hoarding's site door: 18 mm ply on a ledged and braced timber frame, a hasp
        th = 0.009
        bx(0.003, w, -th, th, 0.006, h, "Leaf_Ply")
        for z0 in (0.12, h / 2 - 0.05, h - 0.22):
            bx(0.04, w - 0.04, th, th + 0.045, z0, z0 + 0.1, "Timber_Stud")
        for k in range(8):                                # the brace, in steps up the diagonal
            t0, t1 = k / 8, (k + 1) / 8
            bx(0.06 + t0 * (w - 0.22), 0.16 + t1 * (w - 0.22), th, th + 0.04, 0.22 + t0 * (h / 2 - 0.3), 0.22 + t1 * (h / 2 - 0.3), "Timber_Stud")
        both(w - 0.16, w - 0.05, th, th + 0.012, 1.0, 1.05, "Steel_Dark")
        bx(w - 0.1, w - 0.06, -th - 0.06, -th - 0.012, 0.92, 1.0, "Brass")      # the padlock, on the zone's side
        bx(w - 0.2, w - 0.04, -th - 0.004, -th, 0.12, 0.42, "Sign_White")      # KEEP SHUT plate
    elif style in ("steel", "restroom"):                  # a painted steel staff door / a laminate restroom door: push plate, kick plate, vision panel
        th = 0.022
        leaf = "Leaf_Steel" if style == "steel" else "Leaf_Laminate"
        plate = "Steel_Galv" if style == "steel" else "Chrome"
        if style == "steel":
            bx(0.003, w, -th, th, 0.006, 1.28, leaf)
            bx(0.003, w, -th, th, 1.88, h, leaf)
            bx(0.003, w / 2 - 0.08, -th, th, 1.28, 1.88, leaf)
            bx(w / 2 + 0.08, w, -th, th, 1.28, 1.88, leaf)
            bx(w / 2 - 0.08, w / 2 + 0.08, -0.006, 0.006, 1.28, 1.88, "Glass_Dark")
            both(w / 2 - 0.1, w / 2 + 0.1, th, th + 0.006, 1.26, 1.9, "Steel_Dark")
        else:
            bx(0.003, w, -th, th, 0.006, h, leaf)
        both(0.04, w - 0.04, th, th + 0.002, 0.02, 0.26, plate)
        both(w - 0.16, w - 0.06, th, th + 0.003, 1.05, 1.4, plate)
        bx(w - 0.13, w - 0.09, th + 0.003, th + 0.06, 0.95, 1.25, plate)       # the pull handle, one side
    elif style == "gate":                                 # a freight lift's landing gate: a steel frame and vertical bars
        th = 0.02
        for x0, x1, z0, z1 in ((0.003, 0.05, 0.006, h), (w - 0.05, w, 0.006, h), (0.003, w, 0.006, 0.08), (0.003, w, h - 0.06, h),
                               (0.003, w, 1.05, 1.11)):
            bx(x0, x1, -th, th, z0, z1, "Gate_Steel")
        n = max(2, int((w - 0.1) / 0.075))
        for k in range(1, n):
            x = 0.05 + (w - 0.1) * k / n
            bx(x - 0.008, x + 0.008, -0.008, 0.008, 0.08, h - 0.06, "Gate_Steel")
        bx(w - 0.12, w - 0.05, th, th + 0.05, 1.0, 1.16, "Plastic_Yellow")
    elif style == "stall":                                # a cubicle door: laminate on a 15 cm gap, an indicator bolt and a coat hook
        th = 0.015
        z0 = 0.15
        bx(0.003, w, -th, th, z0, z0 + h, "Laminate_Stall")
        bx(w - 0.12, w - 0.04, th, th + 0.012, 1.0, 1.06, "Chrome")
        bx(w - 0.11, w - 0.05, th + 0.012, th + 0.014, 1.012, 1.048, "Sign_Green")
        bx(w - 0.12, w - 0.04, -th - 0.012, -th, 1.0, 1.06, "Chrome")
        bx(w / 2 - 0.02, w / 2 + 0.02, -th - 0.06, -th, 1.75, 1.79, "Chrome")
    me = bpy.data.meshes.new(f"Leaf_{style}_{int(width * 100)}")
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


def build_leaves(M):
    for d in M.doors:
        p = d["props"]
        ob = bpy.data.objects.new(d["name"], leaf_mesh(leaf_style(d["name"]), p["width"], p["height"]))
        ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
        DOORS.objects.link(ob)
        for k, v in p.items():
            ob[k] = v


def casing(w, a, width, height, y0, mat, tag, fw=0.07, d=0.03):
    hw = width / 2
    part(f"Casing_{tag}_L", mat, lambda bm: w.box(bm, a - hw - fw, a - hw, y0, y0 + height + fw, 0.0, d))
    part(f"Casing_{tag}_R", mat, lambda bm: w.box(bm, a + hw, a + hw + fw, y0, y0 + height + fw, 0.0, d))
    part(f"Casing_{tag}_Head", mat, lambda bm: w.box(bm, a - hw - fw, a + hw + fw, y0 + height, y0 + height + fw, 0.0, d))


# ---------------------------------------------------------------- shared fittings
def emergency_twin(w, a, y, tag, power=150.0):
    """A maintained twin-spot emergency unit (the atrium's kind): a white box, two heads whose lenses are Emergency_Emit; night set."""
    part(f"Emerg_{tag}_Body", "Plastic_White", lambda bm: w.box(bm, a - 0.16, a + 0.16, y - 0.07, y + 0.07, 0.0, 0.09))
    heads = []
    for s in (-1, 1):
        p0 = w.pt(a + s * 0.1, y - 0.07, 0.07)
        dd = (Vector(w.pt(a + s * 0.45, y - 0.9, 0.9)) - Vector(p0)).normalized()
        heads.append((p0, tuple(dd)))
    part(f"Emerg_{tag}_Heads", "Plastic_White", lambda bm: [cyl(bm, p, tuple(Vector(p) + Vector(dd) * 0.07), 0.045, 0.05, seg=12) for p, dd in heads])
    part(f"Emerg_{tag}_Lens", "Emergency_Emit", lambda bm: [cyl(bm, tuple(Vector(p) + Vector(dd) * 0.07), tuple(Vector(p) + Vector(dd) * 0.076), 0.044, seg=12)
                                                           for p, dd in heads])
    for i, (p, dd) in enumerate(heads):
        q = tuple(Vector(p) + Vector(dd) * 0.09)
        light(f"L_emerg_{tag}_{i}", "SPOT", q, power, color=(0.86, 0.93, 1.0), size=0.03, aim=tuple(Vector(q) + Vector(dd)), sets="night", spot=75)


def bulkhead(w, a, y, tag, power=14.0):
    """An emergency bulkhead: a white base and an opal Emergency_Emit lens; night set."""
    part(f"Bulkhead_{tag}_Base", "Plastic_White", lambda bm: w.box(bm, a - 0.17, a + 0.17, y - 0.07, y + 0.07, 0.0, 0.05))
    part(f"Bulkhead_{tag}_Lens", "Emergency_Emit", lambda bm: w.box(bm, a - 0.14, a + 0.14, y - 0.05, y + 0.05, 0.05, 0.075))
    light(f"L_bulk_{tag}", "POINT", w.pt(a, y, 0.16), power, color=(0.9, 0.95, 1.0), size=0.08, sets="night")


def exit_sign(w, a, y0, tag, text="EXIT", wide=0.36):
    """A maintained EXIT sign: a white housing, a green face that is always lit (Sign_Exit, not one of the page's switched names), white letters."""
    part(f"Exit_{tag}_Housing", "Plastic_White", lambda bm: w.box(bm, a - wide / 2, a + wide / 2, y0, y0 + 0.2, 0.0, 0.04))
    part(f"Exit_{tag}_Face", "Sign_Exit", lambda bm: w.box(bm, a - wide / 2 + 0.015, a + wide / 2 - 0.015, y0 + 0.015, y0 + 0.185, 0.04, 0.042))
    part(f"Exit_{tag}_Letters", "Sign_White", lambda bm: wall_text(bm, w, text, a, y0 + 0.1, 0.042, 0.085, 0.003, 1.05))


def batten(x, z, y, tag, along="x", length=1.5, dead=False, power=34.0):
    """A twin fluorescent batten on the soffit: a white body and two tubes (Lamp_Emit); day set."""
    hl = length / 2
    lx, lz = (hl, 0.045) if along == "x" else (0.045, hl)
    part(f"Batten_{tag}_Body", "Plastic_White", lambda bm: cube(bm, (x - lx - 0.03, y - 0.05, z - lz - 0.03 * (along == "z")), (x + lx + 0.03, y, z + lz + 0.03 * (along == "z"))))
    def tubes(bm):
        for s in (-1, 1):
            if along == "x":
                cyl(bm, (x - hl, y - 0.07, z + s * 0.022), (x + hl, y - 0.07, z + s * 0.022), 0.013, seg=8)
            else:
                cyl(bm, (x + s * 0.022, y - 0.07, z - hl), (x + s * 0.022, y - 0.07, z + hl), 0.013, seg=8)
    part(f"Batten_{tag}_Tubes", "Lamp_Dead" if dead else "Lamp_Emit", tubes)
    if not dead:
        light(f"L_batten_{tag}", "AREA", (x, y - 0.09, z), power, color=(0.92, 0.96, 1.0), size=length - 0.1 if along == "x" else 0.1,
              size_y=0.1 if along == "x" else length - 0.1, shape="RECTANGLE", aim=(x, 0.0, z))


def text_board(w, a, y, wide, high, lines, board="Sign_White", ink="Sign_Ink", tag="sign", d=0.012, head=None):
    """A sign board flush on a wall: `lines` = [(text, size)], top to bottom; `head`: (text, colour) a coloured header strip."""
    part(f"Board_{tag}", board, lambda bm: w.box(bm, a - wide / 2, a + wide / 2, y - high / 2, y + high / 2, 0.0, d))
    top = y + high / 2
    if head:
        part(f"Board_{tag}_Head", head[1], lambda bm: w.box(bm, a - wide / 2, a + wide / 2, top - 0.1, top, d, d + 0.002))
        part(f"Board_{tag}_HeadText", "Sign_White", lambda bm: wall_text(bm, w, head[0], a, top - 0.05, d + 0.002, 0.065, 0.002))
        top -= 0.1
    yy = top - 0.03
    for text, size in lines:
        yy -= size * 0.75
        part(f"Board_{tag}_Text", ink, lambda bm, t=text, s=size, q=yy: wall_text(bm, w, t, a, q, d, s, 0.002))
        yy -= size * 0.5


def cloth(bm, corners, nu=8, nv=8, amp=0.03, waves=(3.0, 2.0), th=0.008, seed=0):
    """A dust sheet: a grid between four game corners (in order), rippled along its normal, with a thin back so both sides take light."""
    c0, c1, c2, c3 = [Vector(c) for c in corners]
    n = (c1 - c0).cross(c3 - c0).normalized()
    rng = np.random.default_rng(seed)
    ph = rng.random(2) * 6.28
    grid = {}
    for side, off in ((0, 0.0), (1, th)):
        for i in range(nu + 1):
            for j in range(nv + 1):
                u, v = i / nu, j / nv
                p = c0 * (1 - u) * (1 - v) + c1 * u * (1 - v) + c2 * u * v + c3 * (1 - u) * v
                p = p + n * (amp * math.sin(u * waves[0] * 6.28 + ph[0]) * math.sin(v * waves[1] * 3.14 + ph[1]) + off)
                grid[(side, i, j)] = bm.verts.new(B(tuple(p)))
        for i in range(nu):
            for j in range(nv):
                q = [grid[(side, i, j)], grid[(side, i + 1, j)], grid[(side, i + 1, j + 1)], grid[(side, i, j + 1)]]
                bm.faces.new(q if side == 0 else q[::-1])


DETAIL = {}           # the detail still: {"cam": game point, "at": game point}


# ================================================================ construction: a scaffolded unit mid-fit-out
TUBE = 0.024                     # scaffold tube radius (48.3 mm)


def tripod(x, y0, z, aim, tag, power=520.0):
    """A site work lamp: a tripod, a mast to 1.9 m, a T-bar and two LED floods (Lamp_Emit lenses) turned toward `aim`; day set. Passable (decor_):
    the layout has no collider for it."""
    yaw, pitch = facing_yaw((x, y0 + 1.9, z), aim)
    across = (-math.sin(yaw), -math.cos(yaw))                     # game (x, z) across the facing
    feet = [(x + 0.45 * math.cos(t), y0, z + 0.45 * math.sin(t)) for t in (yaw + 0.5, yaw + 2.6, yaw + 4.7)]
    part(f"decor_Tripod_{tag}_Frame", "Steel_Dark", lambda bm: ([cyl(bm, f, (x, y0 + 0.95, z), 0.014, seg=6) for f in feet],
                                                               cyl(bm, (x, y0 + 0.6, z), (x, y0 + 1.92, z), 0.02, seg=8),
                                                               cyl(bm, (x + across[0] * 0.32, y0 + 1.92, z + across[1] * 0.32),
                                                                   (x - across[0] * 0.32, y0 + 1.92, z - across[1] * 0.32), 0.016, seg=6)))
    heads = [(x + s * across[0] * 0.26, y0 + 1.98, z + s * across[1] * 0.26) for s in (-1, 1)]
    part(f"decor_Tripod_{tag}_Heads", "Plastic_Yellow", lambda bm: [oriented(bm, h, (0.09, 0.26, 0.2), yaw, pitch) for h in heads])
    fwd = Vector((math.cos(yaw) * math.cos(pitch), math.sin(yaw) * math.cos(pitch), -math.sin(pitch)))     # Blender
    gf = (fwd.x, fwd.z, -fwd.y)
    lens = [tuple(h[i] + gf[i] * 0.047 for i in range(3)) for h in heads]
    part(f"decor_Tripod_{tag}_Lens", "Lamp_Emit", lambda bm: [oriented(bm, c, (0.006, 0.22, 0.16), yaw, pitch) for c in lens])
    for i, c in enumerate(lens):
        q = tuple(c[k] + gf[k] * 0.03 for k in range(3))
        light(f"L_tripod_{tag}_{i}", "SPOT", q, power, color=(1.0, 0.97, 0.92), size=0.12, aim=tuple(q[k] + gf[k] for k in range(3)), spot=110)


def festoon(pts, tag, every=1.5, sag=0.22, power=30.0):
    """Temporary site lighting: a cable strung between hooks (game points), sagging, a caged bulb (Lamp_Emit) every `every` m; day set."""
    path = []
    for p0, p1 in zip(pts, pts[1:]):
        n = max(2, int(math.dist(p0, p1) / 0.5))
        for k in range(n):
            t = k / n
            path.append((p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t - sag * math.sin(math.pi * t), p0[2] + (p1[2] - p0[2]) * t))
    path.append(pts[-1])
    part(f"Festoon_{tag}_Cable", "Cable_Black", lambda bm: polyline(bm, path, 0.006, seg=5))
    total = sum(math.dist(a, b) for a, b in zip(path, path[1:]))
    bulbs, acc, nxt = [], 0.0, every / 2
    for a, b in zip(path, path[1:]):
        L = math.dist(a, b)
        while acc + L >= nxt:
            t = (nxt - acc) / L
            bulbs.append(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))
            nxt += every
        acc += L
    part(f"Festoon_{tag}_Holders", "Plastic_Black", lambda bm: [cyl(bm, (p[0], p[1] - 0.01, p[2]), (p[0], p[1] - 0.07, p[2]), 0.016, seg=8) for p in bulbs])
    part(f"Festoon_{tag}_Cages", "Plastic_Yellow", lambda bm: [cyl(bm, (p[0], p[1] - 0.07, p[2]), (p[0], p[1] - 0.075, p[2]), 0.045, seg=10) for p in bulbs])
    part(f"Festoon_{tag}_Bulbs", "Lamp_Emit", lambda bm: [sphere(bm, (p[0], p[1] - 0.115, p[2]), 0.038, seg=10) for p in bulbs])
    for i, p in enumerate(bulbs):
        light(f"L_festoon_{tag}_{i}", "POINT", (p[0], p[1] - 0.12, p[2]), power, color=(1.0, 0.84, 0.64), size=0.04)
    return total


def scaffold_deck():
    """The tube-and-clip scaffold along the north wall: standards front (on the greybox's Deck_Post boxes) and back (against the wall), ledgers,
    transoms, braces, couplers, a timber board deck at 3 m (the Deck box), guard rails and toe boards (Deck_Rail, Deck_Rail_2, Deck_Rail_3)."""
    FZ, BZ, LY, TY = -5.25, -8.976, 2.889, 2.937
    front, back = (-9.75, -5.5, -1.05), (-9.75, -6.0, -1.05)
    for i, x in enumerate(front):
        part(f"Scaffold_Standard_F{i}", "Scaffold_Tube", lambda bm, x=x: (cyl(bm, (x, 0.043, FZ), (x, 4.05, FZ), TUBE, seg=10),
                                                                           cube(bm, (x - 0.07, 0.035, FZ - 0.07), (x + 0.07, 0.043, FZ + 0.07))))
        part(f"Scaffold_Sole_F{i}", "Scaffold_Board", lambda bm, x=x: cube(bm, (x - 0.09, 0.0, FZ - 0.09), (x + 0.09, 0.035, FZ + 0.09)))
    for i, x in enumerate(back):
        part(f"Scaffold_Standard_B{i}", "Scaffold_Tube", lambda bm, x=x: cyl(bm, (x, 0.035, BZ), (x, 3.4, BZ), TUBE, seg=10))
        part(f"Scaffold_Sole_B{i}", "Scaffold_Board", lambda bm, x=x: cube(bm, (x - 0.09, 0.0, -9.0), (x + 0.09, 0.035, BZ + 0.024)))
    # overhead: ledgers along x, transoms across, knee braces from 1.9 m (every part above head height)
    xs = [-11.0 + 0.0 + k * (9.95 / 8) for k in range(9)]

    def overhead(bm):
        for z in (FZ, BZ):
            cyl(bm, (-11.05, LY, z), (-1.0, LY, z), TUBE, seg=8)
        for x in xs:
            cyl(bm, (x, TY, -9.0), (x, TY, -5.2), TUBE, seg=8)
        for x0, x1 in ((-9.75, -8.85), (-5.5, -4.6), (-5.5, -6.4), (-1.05, -1.95)):
            cyl(bm, (x0, 1.95, FZ), (x1, LY - 0.03, FZ), TUBE * 0.95, seg=8)
        for x in back:
            cyl(bm, (x, LY, FZ), (x, LY, BZ), TUBE, seg=8)
    part("Scaffold_Overhead", "Scaffold_Tube", overhead)

    def couplers(bm):
        for x in front:
            for y in (LY, 3.5, 3.976):
                cube(bm, (x - 0.04, y - 0.035, FZ - 0.04), (x + 0.04, y + 0.035, FZ + 0.04))
        for x in back:
            cube(bm, (x - 0.04, LY - 0.035, BZ - 0.024), (x + 0.04, LY + 0.035, BZ + 0.024))
        for x in xs:
            for z in (FZ, BZ):
                cube(bm, (x - 0.035, TY - 0.03, z - 0.035), (x + 0.035, TY + 0.03, z + 0.035))
    part("Scaffold_Couplers", "Coupler", couplers)
    # the back row's facade braces, flat against the wall (their plan is the wall's)
    for i, (x0, x1) in enumerate(((-9.75, -6.0), (-6.0, -1.05))):
        part(f"Scaffold_Brace_{i}", "Scaffold_Tube", lambda bm, x0=x0, x1=x1: cyl(bm, (x0, 0.15, BZ), (x1, LY - 0.05, BZ), TUBE * 0.95, seg=8))
    # the deck: scaffold boards along x, 225 mm wide, staggered joints, galvanised end bands
    def boards(bm):
        for k in range(16):
            z0 = -9.0 + k * 0.2375
            off = (k % 3) * 1.3
            cuts = [-11.0] + [c for c in np.arange(-11.0 + off + 2.6, -1.0, 3.9)] + [-1.0]
            for a, b in zip(cuts, cuts[1:]):
                if b - a > 0.05:
                    cube(bm, (a + 0.004, 2.962, z0), (b - 0.004, 3.0, z0 + 0.225))
    part("Deck_Boards", "Scaffold_Board", boards, tile=1.0)

    def bands(bm):
        for k in range(16):
            z0 = -9.0 + k * 0.2375
            off = (k % 3) * 1.3
            cuts = [-11.0] + [c for c in np.arange(-11.0 + off + 2.6, -1.0, 3.9)] + [-1.0]
            for a, b in zip(cuts, cuts[1:]):
                for e in (a + 0.03, b - 0.06):
                    cube(bm, (e, 3.0, z0 + 0.01), (e + 0.03, 3.002, z0 + 0.215))
    part("Deck_Board_Bands", "Board_End", bands)
    # guard rails and toe boards: the front (Deck_Rail) and the east end (Deck_Rail_2)
    multi_part("Scaffold_GuardRail_F", [("Scaffold_Tube", lambda bm: (cyl(bm, (-9.8, 3.976, FZ), (-1.05, 3.976, FZ), TUBE, seg=8),
                                                                      cyl(bm, (-9.8, 3.5, FZ), (-1.05, 3.5, FZ), TUBE, seg=8))),
                                        ("Scaffold_Board", lambda bm: cube(bm, (-9.8, 3.0, -5.292), (-1.08, 3.15, -5.254)))])
    multi_part("Scaffold_GuardRail_E", [("Scaffold_Tube", lambda bm: (cyl(bm, (-1.05, 3.976, -9.0), (-1.05, 3.976, FZ), TUBE, seg=8),
                                                                      cyl(bm, (-1.05, 3.5, -9.0), (-1.05, 3.5, FZ), TUBE, seg=8))),
                                        ("Scaffold_Board", lambda bm: cube(bm, (-1.096, 3.0, -9.0), (-1.058, 3.15, -5.3)))])
    # the west end (Deck_Rail_3, over the 1 m gap to the wall): the same two rails and toe board, on a post clipped to the end transom at the
    # stair's head; everything inside the box x -11 to -10.9
    WX, PZ = -10.95, -5.235
    multi_part("Scaffold_GuardRail_W", [("Scaffold_Tube", lambda bm: (cyl(bm, (WX, 3.976, -9.0), (WX, 3.976, -5.2), TUBE, seg=8),
                                                                      cyl(bm, (WX, 3.5, -9.0), (WX, 3.5, -5.2), TUBE, seg=8),
                                                                      cyl(bm, (WX, TY - 0.03, PZ), (WX, 4.05, PZ), TUBE, seg=10))),
                                        ("Scaffold_Board", lambda bm: cube(bm, (-10.942, 3.0, -9.0), (-10.904, 3.15, -5.26))),
                                        ("Coupler", lambda bm: [cube(bm, (WX - 0.04, y - 0.035, PZ - 0.035), (WX + 0.04, y + 0.035, PZ + 0.035))
                                                                for y in (TY, 3.5, 3.976)])])


def site_stair():
    """The site stair up to the deck: twelve galvanised treads, each its step's box at most 0.2 m deep (so the layout check reads it as a step, not
    a wall), yellow nosings, passable stringers (decor_), and the handrail on the Stair_Rail box."""
    for i in range(12):
        zf, zb, top = -1.6 - 0.3 * i, -1.9 - 0.3 * i, 0.25 * (i + 1)

        def tread(bm, zf=zf, zb=zb, top=top):
            cube(bm, (-11.0, top - 0.035, zb), (-9.8, top, zf))
            cube(bm, (-10.99, top - 0.199, zf - 0.006), (-9.81, top - 0.035, zf))
            cube(bm, (-11.0, top - 0.199, zb), (-10.99, top, zf))
            cube(bm, (-9.81, top - 0.199, zb), (-9.8, top, zf))
        part(f"Stair_Tread_{i:02d}", "Steel_Galv", tread)
        part(f"Stair_Nosing_{i:02d}", "Hazard_Paint", lambda bm, zf=zf, top=top: cube(bm, (-10.98, top, zf - 0.05), (-9.82, top + 0.003, zf - 0.003)), tile=0.4)
    for x0, x1 in ((-11.06, -11.0), (-9.8, -9.74)):
        part("decor_Stair_Stringer", "Steel_Galv", lambda bm, x0=x0, x1=x1: slab_x(bm, [(0.0, -1.35), (2.75, -5.2), (3.0, -5.2), (0.3, -1.6)], x0, x1))
    X = -9.775

    def rail(bm):
        for z, top in ((-1.65, 1.29), (-3.4, 2.75), (-5.15, 4.05)):
            cyl(bm, (X, 0.0, z), (X, top, z), TUBE, seg=8)
        cyl(bm, (X, 1.25, -1.65), (X, 3.976, -5.15), TUBE, seg=8)
        cyl(bm, (X, 0.75, -1.65), (X, 3.5, -5.15), TUBE, seg=8)
    part("Stair_Handrail", "Scaffold_Tube", rail)


def stud_wall():
    """The half-built partition: the greybox's six studs and two plates as C16 timber, the one plasterboard sheet, noggins."""
    xs = [-11.0 + k * 1.2 for k in range(6)]
    for i, x in enumerate(xs):
        part(f"Stud_{i}", "Timber_Stud", lambda bm, x=x: cube(bm, (x + 0.0015, 0.05, 5.0025), (x + 0.0485, 2.95, 5.0975)))
    part("Stud_Plate_Bottom", "Timber_Stud", lambda bm: cube(bm, (-11.0, 0.0, 5.0025), (-4.95, 0.05, 5.0975)))
    part("Stud_Plate_Top", "Timber_Stud", lambda bm: cube(bm, (-11.0, 2.95, 5.0025), (-4.95, 3.0, 5.0975)))
    part("Stud_Noggins", "Timber_Stud", lambda bm: [cube(bm, (x + 0.05, 1.45, 5.005), (x + 1.2, 1.495, 5.095)) for x in xs[:-1]])
    part("Plasterboard_Sheet", "Plasterboard", lambda bm: cube(bm, (-11.0, 0.05, 5.1), (-8.6, 2.95, 5.1125)))
    part("Plasterboard_Screws", "Steel_Dark", lambda bm: [cube(bm, (x - 0.004, y - 0.004, 5.1125), (x + 0.004, y + 0.004, 5.114))
                                                          for x in (-10.975, -9.775, -8.625) for y in np.arange(0.3, 2.9, 0.3)])


def pallet_build(x0, x1, z0, z1):
    """A timber pallet, 144 mm high: three bearers, nine blocks, top boards (a builder for part / multi_part)."""
    def build(bm):
        for zz in (z0, (z0 + z1) / 2 - 0.05, z1 - 0.1):
            cube(bm, (x0, 0.0, zz), (x1, 0.022, zz + 0.1))
        for xx in (x0, (x0 + x1) / 2 - 0.06, x1 - 0.12):
            for zz in (z0, (z0 + z1) / 2 - 0.05, z1 - 0.1):
                cube(bm, (xx, 0.022, zz), (xx + 0.12, 0.122, zz + 0.1))
        n = 7
        for k in range(n):
            a = z0 + (z1 - z0 - 0.1) * k / (n - 1)
            cube(bm, (x0, 0.122, a), (x1, 0.144, a + 0.1))
    return build


def cement_pallet():
    """The pallet under the deck (the greybox's Pallet), stacked with 25 kg cement bags to 0.9 m."""
    x0, x1, z0, z1 = -8.0, -6.8, -8.6, -7.4
    part("Pallet_cement", "Ply_Pallet", pallet_build(x0, x1, z0, z1))
    rng = np.random.default_rng(501)

    def bags(bm):
        y = 0.144
        for layer in range(5):
            h = 0.148
            if layer % 2 == 0:
                cells = [(x0 + 0.6 * i, x0 + 0.6 * (i + 1), z0 + 0.4 * j, z0 + 0.4 * (j + 1)) for i in range(2) for j in range(3)]
            else:
                cells = [(x0 + 0.4 * i, x0 + 0.4 * (i + 1), z0 + 0.6 * j, z0 + 0.6 * (j + 1)) for i in range(3) for j in range(2)]
            if layer == 4:
                cells = cells[:4]
            for a0, a1, b0, b1 in cells:
                j = rng.uniform(0.0, 0.012, 4)
                cube(bm, (a0 + 0.008 + j[0], y, b0 + 0.008 + j[1]), (a1 - 0.008 - j[2], y + h - 0.004 - 0.01 * rng.random(), b1 - 0.008 - j[3]))
            y += h
    part("Cement_Bags", "Cement_Bag", bags, tile=0.6)


def skip():
    """A mini skip on the greybox's Pallet_2 box: yellow steel, sloped ends, lifting lugs, rubble to near the brim."""
    x0, x1, z0, z1 = 9.0, 11.4, -8.6, -6.8
    t = 0.04
    bx0, bx1 = 9.4, 11.0

    def shell(bm):
        cube(bm, (bx0, 0.1, z0 + 0.06), (bx1, 0.14, z1 - 0.06))
        slab_x(bm, [(0.1, z0 + 0.06), (1.2, z0), (1.2, z0 + t), (0.1, z0 + 0.06 + t)], bx0, bx1)
        slab_x(bm, [(0.1, z1 - 0.06 - t), (1.2, z1 - t), (1.2, z1), (0.1, z1 - 0.06)], bx0, bx1)
        for xa, xb, xc, xd in ((bx0, x0, x0 + t, bx0 + t), (bx1 - t, x1 - t, x1, bx1)):
            pts = [(xa, 0.1, z0 + 0.06), (xa, 0.1, z1 - 0.06), (xd, 0.1, z1 - 0.06), (xd, 0.1, z0 + 0.06),
                   (xb, 1.2, z0), (xb, 1.2, z1), (xc, 1.2, z1), (xc, 1.2, z0)]
            vs = [bm.verts.new(B(p)) for p in pts]
            for f in ((0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)):
                bm.faces.new([vs[i] for i in f])
        cube(bm, (x0, 1.16, z0), (x1, 1.2, z0 + 0.06))
        cube(bm, (x0, 1.16, z1 - 0.06), (x1, 1.2, z1))
    rng = np.random.default_rng(502)

    def rubble(bm):
        cube(bm, (bx0 + 0.04, 0.14, z0 + 0.1), (bx1 - 0.04, 0.9, z1 - 0.1))
        for k in range(46):
            cx, cz = rng.uniform(9.25, 11.15), rng.uniform(z0 + 0.15, z1 - 0.15)
            s = rng.uniform(0.08, 0.26)
            oriented(bm, (cx, 0.92 + rng.uniform(0.0, 0.2), cz), (s, s * rng.uniform(0.4, 1.0), s * rng.uniform(0.3, 0.8)), rng.uniform(0, 6.28), rng.uniform(-0.6, 0.6))
    multi_part("Skip", [("Skip_Paint", shell),
                        ("Steel_Dark", lambda bm: ([cube(bm, (bx0 + 0.05, 0.0, z), (bx1 - 0.05, 0.1, z + 0.12)) for z in (z0 + 0.3, z1 - 0.42)],
                                                   [cyl(bm, (x, 1.0, z0 + 0.25), (x, 1.0, z1 - 0.25), 0.03, seg=8) for x in (9.12, 11.28)])),
                        ("Rubble", rubble),
                        ("Plasterboard", lambda bm: oriented(bm, (10.3, 1.05, -7.5), (1.1, 0.012, 0.7), 0.4, 0.5))])


def mixer():
    """A site cement mixer on the greybox's Cement_Mixer box: a stand on two wheels, an orange drum tipped toward the room, a motor box (one
    object, so its box is the mixer's)."""
    cz = 7.2
    multi_part("Mixer", [
        ("Steel_Dark", lambda bm: (cyl(bm, (4.2, 0.2, 6.7), (4.2, 0.2, 7.7), 0.02, seg=8),
                                   cyl(bm, (4.2, 0.2, 6.75), (4.5, 0.75, cz), 0.025, seg=8),
                                   cyl(bm, (4.2, 0.2, 7.65), (4.5, 0.75, cz), 0.025, seg=8),
                                   cyl(bm, (4.92, 0.0, cz), (4.5, 0.75, cz), 0.025, seg=8),
                                   cube(bm, (4.55, 0.4, 7.05), (4.85, 0.62, 7.35)),
                                   cyl(bm, (4.3, 1.32, cz), (4.27, 1.38, cz), 0.2, 0.19, seg=18, cap=True))),
        ("Rubber_Black", lambda bm: [cyl(bm, (4.2, 0.2, z), (4.2, 0.2, z + 0.08 * sg), 0.2, seg=16) for z, sg in ((6.62, 1), (7.78, -1))]),
        ("Mixer_Paint", lambda bm: (cyl(bm, (4.62, 0.72, cz), (4.42, 1.08, cz), 0.3, 0.33, seg=18),
                                    cyl(bm, (4.42, 1.08, cz), (4.3, 1.32, cz), 0.33, 0.2, seg=18, cap=False),
                                    cyl(bm, (4.62, 0.72, cz), (4.7, 0.6, cz), 0.3, 0.12, seg=18),
                                    cube(bm, (4.62, 0.62, 6.68), (4.98, 0.92, 6.98))))])


def scissor_lift():
    """A small scissor lift, stowed, on the greybox's Scissor_Lift box (one object, so its box is the lift's)."""
    def arms(bm):
        for z in (-1.86, -0.94):
            for (a, ya), (b, yb) in (((2.25, 0.48), (4.15, 0.95)), ((2.25, 0.95), (4.15, 0.48))):
                cyl(bm, (a, ya, z), (b, yb, z), 0.03, seg=6)
        cyl(bm, (3.2, 0.715, -1.9), (3.2, 0.715, -0.9), 0.022, seg=8)

    def rails(bm):
        for x in (2.08, 3.2, 4.32):
            for z in (-1.92, -0.88):
                cube(bm, (x - 0.02, 1.03, z - 0.02), (x + 0.02, 2.0, z + 0.02))
        for y in (1.5, 1.97):
            for z in (-1.92, -0.88):
                cube(bm, (2.06, y - 0.02, z - 0.02), (4.34, y + 0.02, z + 0.02))
            for x in (2.08, 4.32):
                cube(bm, (x - 0.02, y - 0.02, -1.92), (x + 0.02, y + 0.02, -0.88))
    multi_part("Scissor_Lift", [
        ("Lift_Paint", lambda bm: (cube(bm, (2.05, 0.12, -1.93), (4.35, 0.45, -0.87)), cube(bm, (2.05, 0.95, -1.95), (4.35, 1.03, -0.85)))),
        ("Rubber_Black", lambda bm: [cyl(bm, (x, 0.12, z), (x, 0.12, z + 0.1 * sg), 0.12, seg=14) for x in (2.32, 4.08) for z, sg in ((-1.98, 1), (-0.82, -1))]),
        ("Steel_Dark", arms), ("Rail_Yellow", rails),
        ("Plastic_Black", lambda bm: cube(bm, (3.8, 1.75, -0.9), (4.1, 1.95, -0.82)))])


def pit_protection():
    """Edge protection round the open lift pit on the greybox's four Pit_Barrier boxes: yellow posts and rails, a striped toe board, red and white
    barrier tape on the outside, DANGER signs. The pit stays open (Zone_hazard_lift_pit)."""
    sides = {"N": ("z", 1.675, 7.2, 10.8, -1), "S": ("z", 5.325, 7.2, 10.8, 1), "W": ("x", 7.175, 1.7, 5.3, -1), "E": ("x", 10.825, 1.7, 5.3, 1)}
    for tag, (ax, c, r0, r1, out) in sides.items():
        def P(a, y, d):
            return (a, y, c + d) if ax == "z" else (c + d, y, a)

        def bxx(bm, a0, a1, y0, y1, d0, d1):
            p, q = P(a0, y0, d0), P(a1, y1, d1)
            cube(bm, [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)])
        posts = [r0 + 0.02, (r0 + r1) / 2, r1 - 0.02]

        def frame(bm):
            for a in posts:
                bxx(bm, a - 0.02, a + 0.02, 0.0, 1.0, -0.02, 0.02)
            for y in (0.48, 0.96):
                bxx(bm, r0, r1, y, y + 0.035, -0.015, 0.015)
        part(f"PitGuard_{tag}_Frame", "Rail_Yellow", frame)
        part(f"PitGuard_{tag}_Toe", "Hazard_Paint", lambda bm: bxx(bm, r0, r1, 0.0, 0.15, -0.01, 0.01), tile=0.4)
        part(f"PitGuard_{tag}_Tape", "Barrier_Tape", lambda bm: (bxx(bm, r0, r1, 0.72, 0.77, out * 0.022, out * 0.024),
                                                                bxx(bm, r0, r1, 0.3, 0.35, out * 0.022, out * 0.024)), tile=0.5)
    for tag, wz, sgn, a in (("N", 1.65, -1, 8.4), ("S", 5.35, 1, 9.6)):
        w = Wall("z", wz - sgn * 0.002, sgn)
        text_board(w, a, 0.62, 0.46, 0.32, [("OPEN LIFT PIT", 0.05), ("KEEP OUT", 0.06)], tag=f"pit_{tag}", d=0.006, head=("DANGER", "Sign_Red"))
    # the slab's edge painted round the pit, the pit's floor
    for (x0, x1, z0, z1) in ((7.4, 10.6, 1.9, 2.0), (7.4, 10.6, 5.0, 5.1), (7.4, 7.5, 2.0, 5.0), (10.5, 10.6, 2.0, 5.0)):
        L = max(x1 - x0, z1 - z0)
        flat_quad("Pit_Edge_Paint", "Hazard_Paint", [(x0, 0.002, z0), (x1, 0.002, z0), (x1, 0.002, z1), (x0, 0.002, z1)],
                  [(0, 0), ((x1 - x0) / 0.4, 0), ((x1 - x0) / 0.4, (z1 - z0) / 0.4), (0, (z1 - z0) / 0.4)], normal=(0, 1, 0))
    decal("decor_pit_puddle", "Decal_Stain", 9.3, 3.8, 1.6, -1.197, rot=0.5)
    rng = np.random.default_rng(503)
    part("Pit_Debris", "Rubble", lambda bm: [oriented(bm, (rng.uniform(7.8, 10.2), -1.16, rng.uniform(2.3, 4.7)), (0.12, 0.08, 0.06), rng.uniform(0, 6.28))
                                             for _ in range(9)])
    part("decor_Pit_Rebar", "Steel_Dark", lambda bm: [cyl(bm, (x, -1.2, z), (x + 0.02, -0.25, z + 0.01), 0.008, seg=6)
                                                      for x in (7.6, 7.75, 10.25, 10.4) for z in (2.1, 4.9)])


def half_tiles():
    """Walls half tiled for a fit-out that stopped: white 150 mm tiles on the east wall and the north wall's east end, row by row to a ragged top,
    combed adhesive past them, a stack of tile boxes."""
    wE, wN = Wall("x", 12.0, -1), Wall("x", 12.0, -1)
    wN = Wall("z", -9.0, 1)
    rows_e = [16, 16, 16, 15, 14, 14, 12, 10, 9, 7, 5, 3]
    part("Tiles_East", "Tile_Glazed", lambda bm: [wE.box(bm, -9.0 + 0.6 * k, -9.0 + 0.6 * (k + 1), 0.0, 0.15 * n, 0.0, 0.009) for k, n in enumerate(rows_e)])
    part("Adhesive_East", "Adhesive", lambda bm: (wE.box(bm, -1.8, -0.7, 0.0, 0.75, 0.0, 0.004), wE.box(bm, -2.4, -1.8, 0.45, 1.3, 0.0, 0.004),
                                                  wE.box(bm, -4.2, -3.0, 1.8, 2.2, 0.0, 0.004)))
    rows_n = [14, 14, 13, 12, 11, 9, 6, 4, 2]
    part("Tiles_North", "Tile_Glazed", lambda bm: [wN.box(bm, 12.0 - 0.6 * (k + 1), 12.0 - 0.6 * k, 0.0, 0.15 * n, 0.0, 0.009) for k, n in enumerate(rows_n)])
    part("Adhesive_North", "Adhesive", lambda bm: (wN.box(bm, 5.4, 6.6, 0.0, 0.6, 0.0, 0.004), wN.box(bm, 6.6, 7.2, 0.6, 1.05, 0.0, 0.004)))
    part("decor_Tile_Boxes", "Cardboard", lambda bm: [cube(bm, (10.7 + 0.02 * k, 0.0 + 0.14 * k, -1.2 + 0.03 * (k % 2)), (11.5 + 0.02 * k, 0.14 * (k + 1), -0.6 + 0.03 * (k % 2)))
                                                       for k in range(4)])
    rng = np.random.default_rng(504)
    part("Loose_Tiles", "Tile_Glazed", lambda bm: [oriented(bm, (rng.uniform(10.6, 11.7), 0.006, rng.uniform(-2.6, -1.4)), (0.15, 0.15, 0.008), rng.uniform(0, 6.28))
                                                   for _ in range(5)])


def site_cables():
    """Cable runs clipped along the walls at 2.6 m, a 110 V distribution box on the west wall, cables over the floor to the work lamps."""
    wW, wN = Wall("x", -12.0, 1), Wall("z", -9.0, 1)
    part("Cables_West", "Cable_Black", lambda bm: (cyl(bm, wW.pt(-8.9, 2.6, 0.015), wW.pt(8.9, 2.6, 0.015), 0.009, seg=6),
                                                   cyl(bm, wW.pt(1.5, 2.6, 0.015), wW.pt(1.5, 1.55, 0.015), 0.009, seg=6)))
    part("Cables_West_2", "Cable_Orange", lambda bm: (cyl(bm, wW.pt(-8.9, 2.64, 0.034), wW.pt(8.9, 2.64, 0.034), 0.011, seg=6),
                                                      cyl(bm, wW.pt(1.7, 2.64, 0.034), wW.pt(1.7, 1.55, 0.034), 0.011, seg=6),
                                                      cyl(bm, wW.pt(1.6, 0.9, 0.03), wW.pt(1.6, 0.0, 0.03), 0.011, seg=6)))
    part("Cables_North", "Cable_Black", lambda bm: cyl(bm, wN.pt(-11.9, 4.6, 0.015), wN.pt(11.9, 4.6, 0.015), 0.009, seg=6))
    part("Cable_Clips", "Plastic_Black", lambda bm: ([wW.box(bm, a - 0.012, a + 0.012, 2.57, 2.68, 0.0, 0.045) for a in np.arange(-8.7, 8.8, 0.6)],
                                                      [wN.box(bm, a - 0.012, a + 0.012, 4.57, 4.63, 0.0, 0.028) for a in np.arange(-11.6, 11.8, 0.6)]))
    part("Distribution_Box", "Plastic_Yellow", lambda bm: wW.box(bm, 1.35, 1.85, 0.9, 1.55, 0.0, 0.044))
    part("Distribution_Sockets", "Sign_Blue", lambda bm: [wW.box(bm, a - 0.04, a + 0.04, 1.0, 1.08, 0.044, 0.045) for a in (1.47, 1.6, 1.73)])
    for tag, pts in (("a", [(-11.97, 0.012, 1.6), (-10.0, 0.012, 1.9), (-5.0, 0.012, 1.0), (-1.4, 0.012, 2.2), (-1.0, 0.012, 3.2)]),
                     ("b", [(-11.97, 0.012, 1.62), (-6.0, 0.012, 0.6), (0.6, 0.012, 0.5), (4.8, 0.012, 0.4), (5.3, 0.012, 0.15)])):
        part(f"Floor_Cable_{tag}", "Cable_Orange", lambda bm, pts=pts: polyline(bm, pts, 0.012, seg=6))


def dust_and_marks(seed, xs, zs, n_dust=10, n_stain=6, floor_y=0.002):
    rng = np.random.default_rng(seed)
    for i in range(n_dust):
        decal(f"decor_dust_{i}", "Decal_Dust", rng.uniform(*xs), rng.uniform(*zs), rng.uniform(1.2, 2.6), floor_y, rot=rng.uniform(0, 6.28),
              sz=rng.uniform(0.8, 1.8))
    for i in range(n_stain):
        decal(f"decor_stain_{i}", "Decal_Stain", rng.uniform(*xs), rng.uniform(*zs), rng.uniform(0.4, 1.0), floor_y + 0.001, rot=rng.uniform(0, 6.28))


def dress_construction():
    wN, wS, wE, wW = Wall("z", -9.0, 1), Wall("z", 8.9, -1), Wall("x", 12.0, -1), Wall("x", -12.0, 1)
    wS_up = Wall("z", 9.0, -1)
    scaffold_deck()
    site_stair()
    stud_wall()
    cement_pallet()
    skip()
    multi_part("Plasterboard_Pallet", [("Ply_Pallet", pallet_build(1.0, 3.0, 6.42, 7.98)),
                                       ("Plasterboard", lambda bm: cube(bm, (1.02, 0.144, 6.45), (2.98, 0.96, 7.95))),
                                       ("Plastic_Black", lambda bm: [cube(bm, (x, 0.143, 6.445), (x + 0.03, 0.962, 7.955)) for x in (1.4, 2.55)])])
    part("decor_DustSheet_Stack", "Sheet_Cloth", lambda bm: cloth(bm, [(0.98, 0.97, 6.56), (2.2, 0.98, 6.56), (2.2, 0.98, 7.84), (0.98, 0.97, 7.84)], 6, 6, 0.01, seed=1), recalc=False)
    part("decor_DustSheet_Stack_Side", "Sheet_Cloth", lambda bm: cloth(bm, [(0.97, 0.3, 6.56), (0.97, 0.3, 7.84), (0.97, 0.97, 7.84), (0.97, 0.97, 6.56)], 6, 4, 0.015, seed=2), recalc=False)
    mixer()
    scissor_lift()
    pit_protection()
    half_tiles()
    site_cables()
    # the hoarding's door: a timber lining and a KEEP SHUT stencil; the sky hall's raw doorway up on the deck: a timber lining and a steel lintel
    casing(wS, -3.0, 1.3, 2.16, 0.0, "Timber_Stud", "site", fw=0.05, d=0.035)
    part("Site_Door_Stencil", "Sign_Ink", lambda bm: wall_text(bm, wS, "KEEP SHUT", -1.75, 1.5, 0.0, 0.12, 0.002))
    casing(wN, -5.0, 1.1, 2.16, 3.0, "Timber_Stud", "sky", fw=0.06, d=0.04)
    part("Sky_Lintel", "Steel_Dark", lambda bm: wN.box(bm, -5.9, -4.1, 5.22, 5.42, 0.0, 0.03))
    text_board(wN, -3.4, 4.3, 0.5, 0.34, [("NO ACCESS", 0.06), ("BEYOND THIS POINT", 0.035)], tag="sky", d=0.008, head=("DANGER", "Sign_Red"))
    # signs on the hoarding
    text_board(wS, -8.2, 1.75, 1.1, 0.86, [("HARD HATS", 0.085), ("HI-VIS VESTS", 0.085), ("SAFETY BOOTS", 0.085), ("MUST BE WORN", 0.07)],
               board="Sign_Blue", ink="Sign_White", tag="ppe", d=0.01)
    part("Hoarding_Paint_1", "Sign_Ink", lambda bm: wall_text(bm, wS, "UNIT 14   FIT-OUT", 5.0, 2.35, 0.0, 0.22, 0.002, 1.05))
    part("Hoarding_Paint_2", "Sign_Red", lambda bm: wall_text(bm, wS, "NO UNAUTHORISED ACCESS", 5.0, 1.95, 0.0, 0.11, 0.002, 1.05))
    exit_sign(wS, -3.0, 2.3, "site")
    # overhead: the beams, a cable tray hung from the soffit, the festoon lighting
    for x in (-6.0, 0.0, 6.0):
        part("decor_Beam", "Beam_Concrete", lambda bm, x=x: cube(bm, (x - 0.15, 6.0, -9.0), (x + 0.15, 6.5, 9.0)), tile=1.5)
    part("Cable_Tray", "Steel_Galv", lambda bm: (cube(bm, (-11.9, 5.6, -0.15), (11.9, 5.62, 0.15)), cube(bm, (-11.9, 5.62, -0.15), (11.9, 5.7, -0.14)),
                                                 cube(bm, (-11.9, 5.62, 0.14), (11.9, 5.7, 0.15)),
                                                 [cyl(bm, (x, 5.62, z), (x, 6.0, z), 0.005, seg=4) for x in np.arange(-11.0, 11.5, 2.0) for z in (-0.16, 0.16)]))
    part("Cable_Tray_Cables", "Cable_Black", lambda bm: [cyl(bm, (-11.9, 5.64, z), (11.9, 5.64, z), 0.012, seg=6) for z in (-0.08, -0.02, 0.05)])
    for tag, z in (("a", -3.0), ("b", 3.0)):
        for k, (x0, x1) in enumerate(((-11.95, -6.25), (-5.75, -0.25), (0.25, 5.75), (6.25, 11.95))):
            festoon([(x0, 3.75, z), (x1, 3.75, z)], f"{tag}{k}")
    festoon([(-11.0, 4.6, -8.95), (-6.0, 4.6, -8.95), (-1.0, 4.6, -8.95)], "deck", every=1.6, sag=0.12)
    tripod(-1.0, 0.0, 3.6, (-8.0, 2.2, -6.5), "1")
    tripod(5.4, 0.0, 0.3, (11.5, 1.0, -4.5), "2")
    tripod(-7.4, 3.0, -7.4, (-3.0, 0.0, 2.0), "3", power=420.0)
    # the emergency set
    emergency_twin(wW, 2.0, 2.7, "W")
    emergency_twin(wE, 4.0, 2.8, "E")
    emergency_twin(wN, 6.0, 3.0, "N")
    emergency_twin(wS_up, 6.0, 3.6, "S")
    emergency_twin(wN, -8.2, 5.0, "deck")
    # dust sheets, loose bags, a wheelbarrow, a ladder, the floor's marks
    part("decor_DustSheet_Deck", "Sheet_Cloth", lambda bm: cloth(bm, [(-5.4, 0.45, -5.205), (-1.2, 0.45, -5.205), (-1.2, 3.96, -5.205), (-5.4, 3.96, -5.205)],
                                                                 12, 10, 0.03, waves=(5.0, 1.0), seed=3), recalc=False)
    part("DustSheet_Floor", "Sheet_Cloth", lambda bm: cloth(bm, [(6.2, 0.004, 4.0), (8.8, 0.004, 4.3), (8.6, 0.004, 6.9), (6.0, 0.004, 6.5)], 8, 8, 0.006, seed=4), recalc=False)
    part("decor_Loose_Bags", "Cement_Bag", lambda bm: [oriented(bm, c, (0.6, 0.4, 0.14), yw) for c, yw in (((3.3, 0.07, 5.9), 0.3), ((3.7, 0.07, 5.3), 1.2), ((3.5, 0.21, 5.65), 0.8))],
         tile=0.6)
    decal("decor_cement_spill", "Decal_Cement", 4.0, 5.6, 0.9, 0.003, rot=0.6)
    part("decor_Wheelbarrow", "Bin_Green", lambda bm: (cube(bm, (5.5, 0.35, 5.6), (6.3, 0.62, 6.25)), cyl(bm, (6.45, 0.18, 5.85), (6.45, 0.18, 6.0), 0.18, seg=12)))
    part("decor_Wheelbarrow_Handles", "Steel_Dark", lambda bm: [cyl(bm, (6.45, 0.18, z), (5.05, 0.6, z), 0.015, seg=6) for z in (5.65, 6.2)])
    part("decor_Ladder", "Steel_Galv", lambda bm: ([cyl(bm, (11.35, 0.0, a), (11.98, 3.3, a), 0.02, seg=6) for a in (0.6, 1.05)],
                                                   [cyl(bm, (11.35 + 0.063 * k, 0.33 * k, 0.6), (11.35 + 0.063 * k, 0.33 * k, 1.05), 0.014, seg=6) for k in range(1, 10)]))
    for x0, z0, x1, z1 in ((1.0, -1.0, 11.0, -1.0), (1.0, -1.0, 1.0, -8.6), (-4.6, 3.4, 4.6, 3.4)):
        if x0 == x1:
            flat_quad("Chalk_Line", "Chalk_Blue", [(x0 - 0.006, 0.002, z0), (x0 + 0.006, 0.002, z0), (x1 + 0.006, 0.002, z1), (x1 - 0.006, 0.002, z1)], [(0, 0)] * 4, normal=(0, 1, 0))
        else:
            flat_quad("Chalk_Line", "Chalk_Blue", [(x0, 0.002, z0 - 0.006), (x1, 0.002, z0 - 0.006), (x1, 0.002, z1 + 0.006), (x0, 0.002, z1 + 0.006)], [(0, 0)] * 4, normal=(0, 1, 0))
    for x, z in ((1.0, -1.0), (6.0, -1.0), (11.0, -1.0), (1.0, -4.8), (-4.6, 3.4), (4.6, 3.4)):
        for s in (-1, 1):
            flat_quad("Spray_Mark", "Spray_Red", [(x - 0.12, 0.0025, z - 0.12 * s - 0.01), (x + 0.12, 0.0025, z + 0.12 * s - 0.01),
                                                  (x + 0.12, 0.0025, z + 0.12 * s + 0.01), (x - 0.12, 0.0025, z - 0.12 * s + 0.01)], [(0, 0)] * 4, normal=(0, 1, 0))
    dust_and_marks(505, (-11.0, 11.0), (-8.5, 8.5), 12, 7)
    DETAIL.update(cam=(6.6, 1.55, 7.4), at=(9.2, -0.3, 3.4))


# ================================================================ service_corridor: the hidden network's back corridor
def runs(r0, r1, gaps):
    """The pieces of [r0, r1] outside the gaps [(a0, a1)]."""
    out, a = [], r0
    for g0, g1 in sorted(gaps):
        if g0 > a + 0.02:
            out.append((a, min(g0, r1)))
        a = max(a, g1)
    if r1 > a + 0.02:
        out.append((a, r1))
    return out


def euro_bin(x0, x1, z0, z1, top, mat, tag):
    """An 1100 litre wheelie bin on the greybox's Bin box: a tapered body, a black lid, four castors, side handles (one object: its box is the bin's)."""
    def body(bm):
        pts = [(x0 + 0.06, 0.16, z0 + 0.06), (x1 - 0.06, 0.16, z0 + 0.06), (x1 - 0.06, 0.16, z1 - 0.04), (x0 + 0.06, 0.16, z1 - 0.04),
               (x0 + 0.01, top - 0.1, z0 + 0.01), (x1 - 0.01, top - 0.1, z0 + 0.01), (x1 - 0.01, top - 0.1, z1 - 0.01), (x0 + 0.01, top - 0.1, z1 - 0.01)]
        vs = [bm.verts.new(B(p)) for p in pts]
        for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            bm.faces.new([vs[i] for i in f])
    multi_part(f"Bin_{tag}", [
        (mat, body),
        ("Plastic_Black", lambda bm: (cube(bm, (x0, top - 0.1, z0), (x1, top - 0.02, z1)), cube(bm, (x0 + 0.05, top - 0.02, z0 + 0.05), (x1 - 0.05, top, z1 - 0.05)))),
        ("Rubber_Black", lambda bm: [cyl(bm, (x, 0.08, z - 0.03), (x, 0.08, z + 0.03), 0.08, seg=10) for x in (x0 + 0.15, x1 - 0.15) for z in (z0 + 0.15, z1 - 0.15)]),
        ("Steel_Galv", lambda bm: [cube(bm, (x - 0.01, 0.9, z0 + 0.25), (x + 0.01, 0.94, z1 - 0.25)) for x in (x0 + 0.005, x1 - 0.005)])])


def held_fire_door(x, tag):
    """A fire door set across the corridor, held open: a steel frame (its jambs flush on the walls, its head overhead) and two leaves held back
    flat against the walls on magnetic holders."""
    wN, wS = Wall("z", -1.0, 1), Wall("z", 1.0, -1)
    part(f"FireFrame_{tag}_Head", "Frame_Steel", lambda bm: cube(bm, (x - 0.05, 2.16, -1.0), (x + 0.05, 2.3, 1.0)))
    for w in (wN, wS):
        part(f"FireFrame_{tag}_Jamb", "Frame_Steel", lambda bm, w=w: w.box(bm, x - 0.05, x + 0.05, 0.0, 2.16, 0.0, 0.04))
        multi_part(f"FireLeaf_{tag}", [
            ("Leaf_Steel", lambda bm, w=w: (w.box(bm, x + 0.06, x + 1.04, 0.02, 1.25, 0.002, 0.042), w.box(bm, x + 0.06, x + 1.04, 1.85, 2.12, 0.002, 0.042),
                                            w.box(bm, x + 0.06, x + 0.45, 1.25, 1.85, 0.002, 0.042), w.box(bm, x + 0.65, x + 1.04, 1.25, 1.85, 0.002, 0.042))),
            ("Glass_Dark", lambda bm, w=w: w.box(bm, x + 0.45, x + 0.65, 1.25, 1.85, 0.015, 0.03)),
            ("Steel_Galv", lambda bm, w=w: (w.box(bm, x + 0.08, x + 1.02, 0.04, 0.26, 0.042, 0.044), w.box(bm, x + 0.9, x + 1.0, 1.05, 1.35, 0.042, 0.044)))])
        part(f"FireHolder_{tag}", "Steel_Dark", lambda bm, w=w: w.box(bm, x + 1.05, x + 1.12, 1.9, 1.98, 0.0, 0.044))
        part(f"FireSign_{tag}", "Sign_Blue", lambda bm, w=w: cyl(bm, w.pt(x + 0.55, 1.6, 0.042), w.pt(x + 0.55, 1.6, 0.0445), 0.07, seg=16))


def dress_service():
    wS, wN, wW, wE = Wall("z", 1.0, -1), Wall("z", -1.0, 1), Wall("x", -26.0, 1), Wall("x", 20.0, -1)
    wSpW, wSpN, wCar = Wall("x", 18.0, 1), Wall("z", -12.0, 1), Wall("z", -14.6, 1)
    wBin = Wall("z", -2.4, 1)
    doors = [(-22.0, "CINEMA"), (-8.0, "BOOKS"), (4.0, "ENTERTAINMENT"), (12.0, "FOOD COURT")]
    gaps_s = [(a - 0.55, a + 0.55) for a, _ in doors]
    for i, (a, name) in enumerate(doors):
        casing(wS, a, 0.94, 2.16, 0.0, "Frame_Steel", f"staff_{i}", fw=0.06, d=0.03)
        part(f"Stencil_{i}", "Sign_Ink", lambda bm, a=a, name=name: wall_text(bm, wS, name, a, 2.45, 0.0, 0.13, 0.002, 1.05))
        part(f"Stencil_{i}_No", "Sign_Ink", lambda bm, a=a, i=i: wall_text(bm, wS, f"S{i + 1}", a + 0.75, 1.55, 0.0, 0.09, 0.002))
        part(f"CallPoint_{i}", "Sign_Red", lambda bm, a=a: wS.box(bm, a + 0.68, a + 0.78, 1.32, 1.42, 0.0, 0.03))
    # bumper rails, broken at the doors and the openings
    for r0, r1 in runs(-26.0, 20.0, gaps_s):
        part("Bumper_S", "Rubber_Black", lambda bm, r0=r0, r1=r1: wS.box(bm, r0, r1, 0.3, 0.45, 0.0, 0.04))
    for r0, r1 in runs(-26.0, 18.0, [(-17.0, -13.0)]):
        part("Bumper_N", "Rubber_Black", lambda bm, r0=r0, r1=r1: wN.box(bm, r0, r1, 0.3, 0.45, 0.0, 0.04))
    for x, z in ((18.0, -1.0), (-17.0, -1.0), (-13.0, -1.0)):
        part("Corner_Guard", "Steel_Galv", lambda bm, x=x, z=z: cube(bm, (x - 0.035, 0.0, z - 0.035), (x + 0.035, 1.2, z)))
    # the fire exit at the far (west) end, on the greybox's Fire_Door box
    multi_part("Fire_Exit_Doors", [
        ("Leaf_Fire", lambda bm: (wW.box(bm, -0.6, -0.004, 0.0, 2.1, 0.0, 0.055), wW.box(bm, 0.004, 0.6, 0.0, 2.1, 0.0, 0.055))),
        ("Chrome", lambda bm: [wW.box(bm, a0, a1, 0.98, 1.04, 0.06, 0.088) for a0, a1 in ((-0.55, -0.06), (0.06, 0.55))] +
                              [wW.box(bm, a, a + 0.03, 0.96, 1.06, 0.055, 0.088) for a in (-0.57, -0.09, 0.06, 0.54)]),
        ("Steel_Galv", lambda bm: [wW.box(bm, a0, a1, 0.03, 0.25, 0.055, 0.057) for a0, a1 in ((-0.57, -0.03), (0.03, 0.57))])])
    casing(wW, 0.0, 1.2, 2.1, 0.0, "Frame_Steel", "fire", fw=0.06, d=0.03)
    exit_sign(wW, 0.0, 2.25, "fire", "FIRE EXIT", wide=0.6)
    part("Fire_Exit_Sign_Keep", "Sign_Blue", lambda bm: cyl(bm, wW.pt(0.32, 1.6, 0.055), wW.pt(0.32, 1.6, 0.058), 0.08, seg=16))
    part("decor_Extinguisher_1", "Sign_Red", lambda bm: (cyl(bm, wN.pt(-24.8, 0.3, 0.1), wN.pt(-24.8, 0.86, 0.1), 0.08, seg=12),
                                                         cyl(bm, wN.pt(-24.8, 0.86, 0.1), wN.pt(-24.8, 0.94, 0.1), 0.03, seg=8)))
    part("decor_Extinguisher_2", "Sign_Red", lambda bm: (cyl(bm, wSpW.pt(-3.0, 0.3, 0.1), wSpW.pt(-3.0, 0.86, 0.1), 0.08, seg=12),
                                                         cyl(bm, wSpW.pt(-3.0, 0.86, 0.1), wSpW.pt(-3.0, 0.94, 0.1), 0.03, seg=8)))
    held_fire_door(-11.5, "w")
    held_fire_door(15.5, "e")
    # overhead: the pipes (the greybox's two runs), their hangers, sprinklers, the cable tray, the battens
    part("Pipe_Main", "Pipe_Green", lambda bm: cyl(bm, (-26.0, 2.675, -0.825), (20.0, 2.675, -0.825), 0.075, seg=14), tile=1.0)
    part("Pipe_Sprinkler", "Pipe_Red", lambda bm: (cyl(bm, (-26.0, 2.5, -0.55), (20.0, 2.5, -0.55), 0.05, seg=12),
                                                    [cyl(bm, (x, 2.5, -0.55), (x, 2.5, -0.1), 0.014, seg=6) for x in np.arange(-24.0, 19.0, 3.0)],
                                                    [cyl(bm, (x, 2.5, -0.1), (x, 2.93, -0.1), 0.014, seg=6) for x in np.arange(-24.0, 19.0, 3.0)]))
    part("Sprinkler_Heads", "Chrome", lambda bm: [cyl(bm, (x, 2.93, -0.1), (x, 2.97, -0.1), 0.02, 0.03, seg=8) for x in np.arange(-24.0, 19.0, 3.0)])
    part("Pipe_Hangers", "Steel_Galv", lambda bm: ([cube(bm, (x - 0.02, 2.58, -0.95), (x + 0.02, 3.0, -0.92)) for x in np.arange(-25.0, 20.0, 2.0)],
                                                   [cube(bm, (x - 0.02, 2.58, -0.95), (x + 0.02, 2.6, -0.45)) for x in np.arange(-25.0, 20.0, 2.0)],
                                                   [cube(bm, (x - 0.02, 2.425, -0.62), (x + 0.02, 2.445, -0.48)) for x in np.arange(-25.0, 20.0, 2.0)]))

    def tray(bm, x0, x1, z0, z1, y):
        cube(bm, (x0, y, z0), (x1, y + 0.06, z0 + 0.012))
        cube(bm, (x0, y, z1 - 0.012), (x1, y + 0.06, z1))
        for x in np.arange(x0 + 0.15, x1, 0.3):
            cube(bm, (x - 0.012, y, z0), (x + 0.012, y + 0.012, z1))
        for x in np.arange(x0 + 0.75, x1, 1.5):
            for z in (z0 + 0.006, z1 - 0.006):
                cyl(bm, (x, y + 0.06, z), (x, 3.0, z), 0.005, seg=4)

    def tray_z(bm, x0, x1, z0, z1, y):
        cube(bm, (x0, y, z0), (x0 + 0.012, y + 0.06, z1))
        cube(bm, (x1 - 0.012, y, z0), (x1, y + 0.06, z1))
        for z in np.arange(z0 + 0.15, z1, 0.3):
            cube(bm, (x0, y, z - 0.012), (x1, y + 0.012, z + 0.012))
    part("Cable_Tray", "Steel_Galv", lambda bm: (tray(bm, -26.0, 20.0, 0.5, 0.8, 2.6), tray_z(bm, 18.1, 18.3, -12.0, -1.0, 2.6)))
    part("Tray_Cables", "Cable_Black", lambda bm: ([cyl(bm, (-26.0, 2.625, z), (20.0, 2.625, z), 0.012, seg=6) for z in (0.56, 0.62, 0.7)],
                                                    cyl(bm, (18.2, 2.625, -12.0), (18.2, 2.625, -1.0), 0.012, seg=6)))
    part("Tray_Cables_2", "Cable_Orange", lambda bm: cyl(bm, (-26.0, 2.63, 0.75), (20.0, 2.63, 0.75), 0.014, seg=6))
    for k, x in enumerate(np.arange(-24.0, 17.0, 4.0)):
        batten(float(x), 0.0, 3.0, f"c{k}", dead=(k == 6))
    batten(19.0, -4.0, 3.0, "s1", along="z")
    batten(19.0, -8.5, 3.0, "s2", along="z")
    batten(-15.0, -1.7, 3.0, "bins")
    # the emergency set: bulkheads under the pipes, the spur's, the hanging EXIT signs
    for i, x in enumerate((-22.0, -10.0, 2.0, 14.0)):
        bulkhead(wN, x, 2.22, f"n{i}")
    bulkhead(wE, -6.5, 2.4, "spur")
    for i, x in enumerate((-14.0, 7.0)):
        part(f"Exit_Hang_{i}_Rods", "Steel_Galv", lambda bm, x=x: [cyl(bm, (x, 2.5, z), (x, 3.0, z), 0.004, seg=4) for z in (-0.15, 0.15)])
        part(f"Exit_Hang_{i}_Box", "Plastic_White", lambda bm, x=x: cube(bm, (x - 0.02, 2.28, -0.2), (x + 0.02, 2.5, 0.2)))
        part(f"Exit_Hang_{i}_Face", "Sign_Exit", lambda bm, x=x: cube(bm, (x - 0.022, 2.295, -0.185), (x + 0.022, 2.485, 0.185)))
        for s in (-1, 1):
            part(f"Exit_Hang_{i}_Text", "Sign_White", lambda bm, x=x, s=s: add_text(bm, "EXIT", 0.08, 0.002, (x + s * 0.022, 2.39, 0.0),
                                                                                   (0, 0, -s), (0, 1, 0), (s, 0, 0)))
    # the bins and their bay
    euro_bin(-16.8, -15.4, -2.4, -1.5, 1.3, "Bin_Green", "1")
    euro_bin(-15.2, -13.8, -2.4, -1.5, 1.3, "Bin_Grey", "2")
    text_board(wBin, -16.1, 1.7, 0.6, 0.22, [("CARDBOARD ONLY", 0.055)], board="Sign_Green", ink="Sign_White", tag="bin1", d=0.008)
    text_board(wBin, -14.5, 1.7, 0.6, 0.22, [("GENERAL WASTE", 0.055)], tag="bin2", d=0.008)
    rng = np.random.default_rng(601)
    part("decor_Bin_Bags", "Bag_Black", lambda bm: [sphere(bm, (x, 0.2, z), 0.22 + 0.04 * rng.random(), seg=10) for x, z in ((-13.5, -1.35), (-13.3, -1.75), (-13.65, -2.1))])
    # the freight lift spur: the landing's steel portal, its indicator, the keycard reader, the signs, the car
    casing(wSpN, 19.0, 1.2, 2.2, 0.0, "Steel_Galv", "gate", fw=0.1, d=0.04)
    part("Lift_Indicator", "Plastic_Black", lambda bm: wSpN.box(bm, 18.7, 19.3, 2.42, 2.62, 0.0, 0.03))
    part("Lift_Indicator_Text", "Sign_White", lambda bm: wall_text(bm, wSpN, "FREIGHT", 19.0, 2.52, 0.03, 0.07, 0.002, 1.1))
    flat_quad("Gate_Sill", "Hazard_Paint", [(18.4, 0.002, -12.0), (19.6, 0.002, -12.0), (19.6, 0.002, -11.85), (18.4, 0.002, -11.85)],
              [(0, 0), (3, 0), (3, 0.4), (0, 0.4)], normal=(0, 1, 0))
    flat_quad("Gate_Sill_2", "Hazard_Paint", [(18.4, 0.002, -12.2), (19.6, 0.002, -12.2), (19.6, 0.002, -12.0), (18.4, 0.002, -12.0)],
              [(0, 0), (3, 0), (3, 0.5), (0, 0.5)], normal=(0, 1, 0))
    za = -11.15
    multi_part("Keycard_Reader", [
        ("Plastic_Black", lambda bm: wSpW.box(bm, za - 0.05, za + 0.05, 1.12, 1.3, 0.0, 0.03)),
        ("Glass_Dark", lambda bm: wSpW.box(bm, za - 0.035, za + 0.035, 1.14, 1.22, 0.03, 0.033)),
        ("Steel_Galv", lambda bm: wSpW.box(bm, za - 0.04, za + 0.04, 1.245, 1.26, 0.03, 0.034))])
    part("Keycard_Reader_LED", "Reader_Glow", lambda bm: wSpW.box(bm, za - 0.012, za + 0.012, 1.272, 1.288, 0.03, 0.036))
    part("Keycard_Conduit", "Steel_Galv", lambda bm: cyl(bm, wSpW.pt(za, 1.3, 0.012), wSpW.pt(za, 2.6, 0.012), 0.01, seg=6))
    text_board(wSpW, za, 1.43, 0.24, 0.1, [("SWIPE KEYCARD", 0.03)], tag="swipe", d=0.004)
    text_board(wSpW, -10.1, 1.65, 0.62, 0.52, [("AUTHORISED STAFF", 0.05), ("KEYCARD ONLY", 0.05), ("MAX LOAD 2000 KG", 0.04)],
               tag="freight", d=0.008, head=("FREIGHT LIFT", "Sign_Red"))
    part("Car_Handrail", "Chrome", lambda bm: (cyl(bm, wCar.pt(18.15, 0.95, 0.035), wCar.pt(19.85, 0.95, 0.035), 0.016, seg=10),
                                               [wCar.box(bm, a - 0.012, a + 0.012, 0.93, 0.97, 0.0, 0.035) for a in (18.25, 19.75)]))
    part("Car_Light", "Lamp_Emit", lambda bm: cube(bm, (18.7, 2.38, -13.7), (19.3, 2.4, -13.1)))
    light("L_car", "AREA", (19.0, 2.36, -13.4), 30.0, color=(0.92, 0.96, 1.0), size=0.55, shape="SQUARE", aim=(19.0, 0.0, -13.4))
    part("Car_Buttons", "Steel_Galv", lambda bm: Wall("x", 20.1, -1).box(bm, -12.7, -12.5, 1.0, 1.4, 0.0, 0.02))
    part("decor_Sack_Truck", "Steel_Dark", lambda bm: (cyl(bm, (19.75, 0.0, -2.6), (19.88, 1.3, -2.6), 0.015, seg=6), cyl(bm, (19.75, 0.0, -2.2), (19.88, 1.3, -2.2), 0.015, seg=6),
                                                       cube(bm, (19.55, 0.0, -2.65), (19.78, 0.02, -2.15)),
                                                       cyl(bm, (19.8, 0.1, -2.7), (19.8, 0.1, -2.62), 0.1, seg=10), cyl(bm, (19.8, 0.1, -2.18), (19.8, 0.1, -2.1), 0.1, seg=10)))
    # the notice board, the floor's walkway lines and marks
    multi_part("Notice_Board", [("Cork", lambda bm: wN.box(bm, 5.2, 6.4, 1.2, 1.8, 0.0, 0.02)),
                                ("Paper", lambda bm: [wN.box(bm, a, a + 0.21, y, y + 0.297, 0.02, 0.021) for a, y in ((5.3, 1.42), (5.58, 1.46), (5.86, 1.3), (6.1, 1.44))])])
    for z in (-0.82, 0.82):
        flat_quad("Walkway_Line", "Plastic_Yellow", [(-26.0, 0.002, z - 0.025), (20.0, 0.002, z - 0.025), (20.0, 0.002, z + 0.025), (-26.0, 0.002, z + 0.025)],
                  [(0, 0)] * 4, normal=(0, 1, 0))
    dust_and_marks(602, (-25.0, 19.0), (-0.8, 0.8), 8, 10)
    DETAIL.update(cam=(19.45, 1.55, -9.7), at=(18.0, 1.15, -11.3))


# ================================================================ mirror_bathroom: a tiled public restroom, six mirrors, one a portal
def basin(x, z, y0, tag):
    """A round vessel basin on the counter: an open bowl (outer wall, rim, inner wall, a bowl floor) and a chrome waste."""
    def bowl(bm):
        cyl(bm, (x, y0, z), (x, y0 + 0.13, z), 0.15, 0.2, seg=20, cap=False)
        cyl(bm, (x, y0 + 0.13, z), (x, y0 + 0.135, z), 0.2, 0.19, seg=20, cap=False)
        cyl(bm, (x, y0 + 0.02, z), (x, y0 + 0.135, z), 0.13, 0.19, seg=20, cap=False)
        cyl(bm, (x, y0 + 0.018, z), (x, y0 + 0.02, z), 0.13, seg=20, cap=True)
    part(f"Basin_{tag}", "Ceramic_White", bowl, recalc=False)
    part(f"Basin_{tag}_Waste", "Chrome", lambda bm: cyl(bm, (x, y0 + 0.02, z), (x, y0 + 0.023, z), 0.025, seg=10))
    part(f"Tap_{tag}", "Chrome", lambda bm: (cyl(bm, (x, y0, -3.94), (x, y0 + 0.28, -3.94), 0.018, seg=10),
                                            cyl(bm, (x, y0 + 0.27, -3.94), (x, y0 + 0.27, -3.8), 0.012, seg=8),
                                            cube(bm, (x - 0.008, y0 + 0.28, -3.96), (x + 0.008, y0 + 0.3, -3.88))))


def dress_bathroom():
    wN, wS, wW, wE = Wall("z", -4.0, 1), Wall("z", 4.0, -1), Wall("x", -5.0, 1), Wall("x", 5.0, -1)
    door_gap = [(-4.15, -3.05)]
    for w, r0, r1, gaps in ((wN, -5.0, 5.0, []), (wS, -5.0, 5.0, door_gap), (wW, -4.0, 4.0, []), (wE, -4.0, 4.0, [])):
        for a0, a1 in runs(r0, r1, gaps):
            part("Tile_Trim", "Chrome", lambda bm, w=w, a0=a0, a1=a1: w.box(bm, a0, a1, 2.095, 2.115, 0.0, 0.008))
            part("Tile_Skirt", "Tile_Skirt", lambda bm, w=w, a0=a0, a1=a1: w.box(bm, a0, a1, 0.0, 0.1, 0.0, 0.008), tile=0.9)
    casing(wS, -3.6, 0.94, 2.16, 0.0, "Chrome", "door", fw=0.05, d=0.025)
    exit_sign(wS, -3.6, 2.35, "door")
    # the vanity: a laminate carcass, a solid-surface top and apron, six vessel basins and their taps, soap between the mirrors
    multi_part("Vanity", [("Laminate_Stall", lambda bm: (cube(bm, (-4.6, 0.08, -4.0), (4.6, 0.6, -3.46)), cube(bm, (-4.58, 0.6, -4.0), (4.58, 0.81, -3.44)))),
                          ("Plastic_Black", lambda bm: cube(bm, (-4.58, 0.0, -4.0), (4.58, 0.08, -3.5))),
                          ("Counter_Solid", lambda bm: (cube(bm, (-4.6, 0.81, -4.0), (4.6, 0.85, -3.4)), cube(bm, (-4.6, 0.62, -3.44), (4.6, 0.81, -3.4))))])
    for k, x in enumerate(GB.MIRROR_X, 1):
        basin(x, -3.72, 0.85, str(k))
    for k in range(5):
        x = (GB.MIRROR_X[k] + GB.MIRROR_X[k + 1]) / 2
        part(f"Soap_{k}", "Chrome", lambda bm, x=x: (wN.box(bm, x - 0.045, x + 0.045, 1.05, 1.27, 0.0, 0.045), wN.box(bm, x - 0.012, x + 0.012, 1.03, 1.05, 0.03, 0.045)))
    # the six mirrors: a chrome frame each and the glass as its own node (Mirror_<n> in the GLB, with the greybox's properties); Mirror_4 is the
    # portal and its frame is the tell: a darker, older bronze, a little heavier, its glass set deeper, a hairline crack in the tile under it
    M = model(SCENE)
    for k, x in enumerate(GB.MIRROR_X, 1):
        tell = k == GB.PORTAL_MIRROR
        fw, fd, gd = (0.045, 0.04, 0.012) if tell else (0.03, 0.03, 0.022)
        x0, x1, y0, y1 = x - 0.65, x + 0.65, 1.0, 2.2
        part(f"Mirror_Frame_{k}", "Frame_Bronze" if tell else "Frame_Chrome",
             lambda bm, x0=x0, x1=x1, fw=fw, fd=fd: (wN.box(bm, x0, x1, y0, y0 + fw, 0.0, fd), wN.box(bm, x0, x1, y1 - fw, y1, 0.0, fd),
                                                     wN.box(bm, x0, x0 + fw, y0, y1, 0.0, fd), wN.box(bm, x1 - fw, x1, y0, y1, 0.0, fd)))
        part(f"Mirror_Back_{k}", "Steel_Dark", lambda bm, x0=x0, x1=x1, fw=fw, gd=gd: wN.box(bm, x0 + fw, x1 - fw, y0 + fw, y1 - fw, 0.0, gd - 0.002))
        g = flat_quad(f"Glass_Mirror_{k}", "Mirror_Glass", [(x0 + fw, y0 + fw, -4.0 + gd), (x1 - fw, y0 + fw, -4.0 + gd), (x1 - fw, y1 - fw, -4.0 + gd), (x0 + fw, y1 - fw, -4.0 + gd)],
                      [(0, 0), (1, 0), (1, 1), (0, 1)], normal=(0, 0, 1))
        if tell:
            wall_decal("Crack_Mirror_4", "Decal_Crack", wN, x0 + 0.18, x0 + 0.36, 0.855, 1.0, d=0.001)
            DETAIL.update(cam=(x - 0.45, 1.5, -2.2), at=(x + 0.05, 1.45, -4.0))
    # the stalls: laminate partitions and pilasters on chrome legs, a headrail, wall-hung WCs (passable), flush plates, roll holders
    for i, (b, c) in enumerate(sorted((b["name"], b) for b in M.boxes if b["col"] and b["name"].startswith(("Stall_Partition", "Stall_Front")))):
        mn, mx = c["min"], c["max"]
        thin_x = mx[0] - mn[0] < mx[2] - mn[2]
        if thin_x:
            xm = (mn[0] + mx[0]) / 2
            panel = lambda bm, xm=xm, mn=mn, mx=mx: cube(bm, (xm - 0.015, 0.15, mn[2]), (xm + 0.015, 2.07, mx[2] - 0.004))
            legs = lambda bm, xm=xm, mn=mn: cyl(bm, (xm, 0.0, mn[2] + 0.06), (xm, 0.15, mn[2] + 0.06), 0.016, seg=8)
        else:
            zm = (mn[2] + mx[2]) / 2
            panel = lambda bm, zm=zm, mn=mn, mx=mx: cube(bm, (mn[0] + 0.002, 0.15, zm - 0.015), (mx[0] - 0.002, 2.07, zm + 0.015))
            legs = lambda bm, zm=zm, mn=mn, mx=mx: cyl(bm, ((mn[0] + mx[0]) / 2, 0.0, zm), ((mn[0] + mx[0]) / 2, 0.15, zm), 0.016, seg=8)
        multi_part(f"Stall_{b}", [("Laminate_Stall", panel), ("Chrome", legs)])
    part("Stall_Headrail", "Chrome", lambda bm: cube(bm, (-2.2, 2.07, 2.405), (5.0, 2.1, 2.445)))
    for k in range(4):
        a = -2.2 + 1.8 * k
        c = a + 0.9
        part(f"decor_WC_{k}", "Ceramic_White", lambda bm, c=c: (cyl(bm, (c, 0.26, 3.5), (c, 0.4, 3.5), 0.15, 0.18, seg=16), cube(bm, (c - 0.17, 0.26, 3.5), (c + 0.17, 0.4, 3.99))))
        part(f"decor_WC_{k}_Seat", "Plastic_White", lambda bm, c=c: (cyl(bm, (c, 0.4, 3.52), (c, 0.425, 3.52), 0.185, seg=16), cube(bm, (c - 0.18, 0.4, 3.52), (c + 0.18, 0.425, 3.92)),
                                                                   cube(bm, (c - 0.19, 0.425, 3.94), (c + 0.19, 0.85, 3.97))))
        part(f"Flush_Plate_{k}", "Chrome", lambda bm, c=c: wS.box(bm, c - 0.12, c + 0.12, 1.0, 1.16, 0.0, 0.012))
        part(f"Roll_Holder_{k}", "Chrome", lambda bm, a=a: cube(bm, (a + 0.04, 0.72, 3.2), (a + 0.14, 0.8, 3.36)))
        decal(f"decor_wc_stain_{k}", "Decal_Stain", c, 3.7, 0.5, 0.002, rot=k * 1.3)
    # the hand dryer, a bin and a wet floor sign (passable), the ceiling's panels and vent, the emergency set
    part("decor_Hand_Dryer", "Plastic_White", lambda bm: wW.box(bm, -1.0, -0.6, 1.1, 1.45, 0.0, 0.2))
    part("decor_Hand_Dryer_Nozzle", "Chrome", lambda bm: wW.box(bm, -0.88, -0.72, 1.08, 1.1, 0.06, 0.16))
    part("decor_Bin", "Chrome", lambda bm: cyl(bm, (-4.72, 0.0, 0.1), (-4.72, 0.6, 0.1), 0.17, seg=16))
    part("decor_Wet_Floor", "Plastic_Yellow", lambda bm: (oriented(bm, (-4.3, 0.33, -2.75), (0.02, 0.3, 0.66), 0.0, 0.26),
                                                         oriented(bm, (-4.12, 0.33, -2.75), (0.02, 0.3, 0.66), 0.0, -0.26)))
    for i, (x, z) in enumerate(((-2.7, -2.1), (0.3, -2.1), (3.3, -2.1), (-2.7, 0.9), (0.9, 3.3), (2.7, 3.3))):
        part(f"Panel_{i}", "Lamp_Emit", lambda bm, x=x, z=z: cube(bm, (x - 0.29, 2.99, z - 0.29), (x + 0.29, 3.0, z + 0.29)))
        part(f"Panel_{i}_Rim", "Plastic_White", lambda bm, x=x, z=z: (cube(bm, (x - 0.3, 2.985, z - 0.3), (x + 0.3, 2.99, z - 0.28)),
                                                                     cube(bm, (x - 0.3, 2.985, z + 0.28), (x + 0.3, 2.99, z + 0.3)),
                                                                     cube(bm, (x - 0.3, 2.985, z - 0.28), (x - 0.28, 2.99, z + 0.28)),
                                                                     cube(bm, (x + 0.28, 2.985, z - 0.28), (x + 0.3, 2.99, z + 0.28))))
        light(f"L_panel_{i}", "AREA", (x, 2.97, z), 42.0, color=(0.95, 0.97, 1.0), size=0.55, shape="SQUARE", aim=(x, 0.0, z))
    part("Vent", "Steel_Galv", lambda bm: cube(bm, (1.8, 2.985, -0.3), (2.4, 3.0, 0.3)))
    part("Smoke_Detector", "Plastic_White", lambda bm: cyl(bm, (-0.6, 2.965, 0.6), (-0.6, 3.0, 0.6), 0.06, seg=14))
    for i, (x, z) in enumerate(((-2.1, 1.6), (1.5, -1.2))):
        part(f"EmergDown_{i}_Rim", "Plastic_White", lambda bm, x=x, z=z: cyl(bm, (x, 2.985, z), (x, 3.0, z), 0.08, seg=16))
        part(f"EmergDown_{i}_Lens", "Emergency_Emit", lambda bm, x=x, z=z: cyl(bm, (x, 2.978, z), (x, 2.985, z), 0.05, seg=16))
        light(f"L_emergdown_{i}", "SPOT", (x, 2.96, z), 30.0, color=(0.9, 0.95, 1.0), size=0.03, aim=(x, 0.0, z), sets="night", spot=110)
    part("Floor_Drain", "Steel_Dark", lambda bm: cube(bm, (-0.1, 0.0, 0.4), (0.1, 0.003, 0.6)))
    dust_and_marks(701, (-4.6, 4.6), (-3.3, 2.2), 4, 5)


DRESS = {"construction": dress_construction, "service_corridor": dress_service, "mirror_bathroom": dress_bathroom}


# ---------------------------------------------------------------- build
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for d in (IMG, MATS, TILES, GEN, LEAF_MESH, DETAIL, TEXT_CACHE):
        d.clear()
    NAMES.clear()


def set_emit(mname, strength):
    m = bpy.data.materials.get(mname)
    if m:
        m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = strength


def apply_light_set(name):
    """day: the working lights (Lamp_Emit and its lamps); night: the emergency set alone (Emergency_Emit and its lamps), the mall locked at 20:00;
    export: both materials at the strength the page switches on. The EXIT signs and the reader's light are always lit."""
    bpy.data.collections["Lights_Day"].hide_render = name != "day"
    bpy.data.collections["Lights_Night"].hide_render = name != "night"
    set_emit("Lamp_Emit", LAMP_EMIT if name in ("day", "export") else 0.0)
    set_emit("Emergency_Emit", EMERG_EMIT if name in ("night", "export") else 0.0)


def build_all():
    global ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, STANDIN, LIGHTS
    reset()
    sc = bpy.context.scene
    ART = bpy.data.collections.new("Art")
    sc.collection.children.link(ART)
    PROPS, ARCH = bpy.data.collections.new("Props"), bpy.data.collections.new("Arch")
    ART.children.link(PROPS)
    ART.children.link(ARCH)
    SKIN, DOORS, LAYOUT, STANDIN, LIGHTS = (bpy.data.collections.new(n) for n in ("Skin", "Doors", "Layout", "Standins", "Lights"))
    for c in (SKIN, DOORS, LAYOUT, STANDIN, LIGHTS):
        sc.collection.children.link(c)
    for n in ("Lights_Day", "Lights_Night"):
        LIGHTS.children.link(bpy.data.collections.new(n))
    make_materials()
    M = model(SCENE)
    layout_from_model(M)
    build_skin()
    build_leaves(M)
    DRESS[SCENE]()
    for t in list(TEXT_CACHE.values()):
        bpy.data.meshes.remove(t)
    TEXT_CACHE.clear()
    sc["detail"] = json.dumps(DETAIL)
    w = sc.world or bpy.data.worlds.new("Dark")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.01, 0.012, 0.02, 1)
    bg.inputs["Strength"].default_value = 0.0
    ensure_marker()
    apply_light_set("day")
    ARCH.hide_render = True
    for ob in LAYOUT.objects:
        ob.hide_render = True
    tris = sum(len(p.vertices) - 2 for c in (PROPS, SKIN) for o in c.objects for p in o.data.polygons)
    print(f"ART {SCENE}: {len(PROPS.objects)} props, {len(ARCH.objects)} shell stand-ins, {len(SKIN.objects)} skin meshes, {len(DOORS.objects)} door "
          f"leaves, {len(bpy.data.collections['Lights_Day'].objects)} day lights, {len(bpy.data.collections['Lights_Night'].objects)} night lights, "
          f"about {tris} triangles before culling")


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


# ---------------------------------------------------------------- bake (the mazes' method, twice: day and night on the same UVs)
def shell_mats():
    q, _ = scene_skin(SCENE)
    return {quad_material(SCENE, x) for x in q}


def cull_flush(bm, cols):
    """Drop the faces pressed against the shell (their front 3 mm is inside a wall, the floor or the ceiling): never seen."""
    bad = []
    for f in bm.faces:
        c, n = f.calc_center_median(), f.normal
        g = (c.x + n.x * 0.003, c.z + n.z * 0.003, -(c.y + n.y * 0.003))
        if any(all(o["min"][i] + 1e-4 < g[i] < o["max"][i] - 1e-4 for i in range(3)) for o in cols):
            bad.append(f)
    bmesh.ops.delete(bm, geom=bad, context="FACES")


def mirror_props():
    return {b["name"]: dict(b.get("props", {})) for b in model(SCENE).boxes if b["name"].startswith("Mirror_")}


def make_export_objects():
    if "Export" in bpy.data.collections:
        for o in list(bpy.data.collections["Export"].objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(bpy.data.collections["Export"])
    exp = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(exp)
    cols = shell_cols(SCENE, model(SCENE))
    out = {}
    for ob in bpy.data.collections["Skin"].objects:
        me = ob.data.copy()
        me.name = "X_" + ob.name
        o2 = bpy.data.objects.new("X_" + ob.name, me)
        exp.objects.link(o2)
        out[ob.name] = o2
    mp = mirror_props()
    by_mat = {}
    for ob in bpy.data.collections["Props"].objects:
        if ob.name.startswith("Glass_Mirror_"):                    # each mirror stays its own node, its origin at the glass's middle
            k = ob.name[len("Glass_Mirror_"):]
            me = ob.data.copy()
            vs = [v.co.copy() for v in me.vertices]
            c = sum(vs, Vector()) / len(vs)
            for v in me.vertices:
                v.co -= c
            me.name = f"Mirror_{k}"
            o2 = bpy.data.objects.new(f"Mirror_{k}", me)
            o2.location = c
            for key, val in mp.get(f"Mirror_{k}", {}).items():
                o2[key] = val
            exp.objects.link(o2)
            out[o2.name] = o2
            continue
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


def world_area(ob):
    return sum(p.area for p in ob.data.polygons) * abs(ob.matrix_world.to_3x3().determinant()) ** (2 / 3)


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
COLS = []


def prop_islands(objs):
    """The props' lightmap islands, by connected piece (world space): a thin piece lying flat against something is ONE island, projected along its
    thin axis (its sides become lines, its back a point); anything else gets up to six islands, its faces grouped by the axis they face. Returns
    [(obj, faces, (u axis, v axis), (u0, v0), (w, h), collapse set)]."""
    out = []
    for o in objs:
        mw = o.matrix_world
        me = o.data
        co = [mw @ v.co for v in me.vertices]
        g = [(c.x, c.z, -c.y) for c in co]
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
                c = mw @ me.polygons[f].center
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
            against = (bax, -bsg) not in cen or facing_in((bax, -bsg))      # a free-standing panel or a door leaf keeps both faces
            if ext[bax] <= 0.08 and barea >= 0.4 * tot and against:
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
    lo, hi, best = 0.5, 400.0, None
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
    os.remove(path)
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
    """One door leaf per leaf mesh is baked (the mesh's lightmap UVs, so every leaf of that kind shares the texels)."""
    reps = {}
    for o in sorted(bpy.data.collections["Doors"].objects, key=lambda o: o.name):
        reps.setdefault(o.data.name, o)
    return list(reps.values())


def bake_visibility():
    for c, hide in (("Art", True), ("Skin", True), ("Standins", True), ("Doors", False), ("Export", False)):
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


def bake_one(objs, S, n, samples):
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
    bpy.context.scene.cycles.samples = samples
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX if n == 0 else PROPS_MARGIN, margin_type="EXTEND",
                        use_clear=True, target="IMAGE_TEXTURES")
    rgb = denoise_image(img, S)[..., :3].copy()
    for m in mats:
        for nd in [nd for nd in m.node_tree.nodes if nd.name.startswith("BAKE_TARGET")]:
            m.node_tree.nodes.remove(nd)
    bpy.data.images.remove(img)
    return rgb, mats


def stage_bake():
    import time
    exp = make_export_objects()
    COLS[:] = shell_cols(SCENE, model(SCENE))
    bake_visibility()
    setup_cycles(SAMPLES, bake=True)
    sm = shell_mats()
    shell = [o for k, o in sorted(exp.items()) if k.startswith("Skin_")]
    props = [o for k, o in sorted(exp.items()) if not k.startswith("Skin_") and o.data.materials[0].name not in NO_LIGHTMAP] + leaf_reps()
    assert {o.data.materials[0].name for o in shell} <= sm
    clash = sm & {s.material.name for o in props for s in o.material_slots}
    assert not clash, f"shell materials used by props: {clash}"
    report = {}
    for n, objs in enumerate([shell, props]):
        print(f"lightmap {n}: {len(objs)} objects")
        S, dens = rect_uv(objs, PAGES[0]) if n == 0 else islands_uv(objs, PAGES[1])
        for st, idx, samples in (("day", n, SAMPLES), ("night", n + NIGHT_OFFSET, NIGHT_SAMPLES)):
            t0 = time.time()
            apply_light_set(st)
            rgb, mats = bake_one(objs, S, n, samples)
            rgb_s, knee = shoulder(rgb)
            peak = rgb_s.max(axis=2)
            assert (peak > 1e-5).any(), f"lightmap {idx} came out black"
            pc = np.percentile(peak[peak > 1e-5], [50, 90, 99, 99.5, 100])
            scale = float(min(pc[3], WHITE_CAP * pc[1]))
            out = np.ones((S, S, 4), np.float32)
            out[..., :3] = srgb_encode(rgb_s / scale)
            png = bpy.data.images.new(f"LM_{idx}_png", S, S, alpha=False)
            png.colorspace_settings.name = "Non-Color"
            png.pixels.foreach_set(out.ravel())
            png.filepath_raw = str(work() / f"{SCENE}_{idx}.png")
            png.file_format = "PNG"
            png.save()
            bpy.data.images.remove(png)
            key, kkey = ("lightmap", "lightmap_intensity") if st == "day" else ("lightmap_night", "lightmap_night_intensity")
            for m in mats:
                m[key] = lm_url(SCENE, idx)
                m[kkey] = round(math.pi * scale, 4)
            raw = rgb.max(axis=2)
            report[idx] = {"map": n, "set": st, "size": S, "px_per_m": round(dens, 1), "scale": round(scale, 5), "knee": round(knee, 5),
                           "raw_p50_p90_p99_p995_max": [round(float(v), 4) for v in np.percentile(raw[raw > 1e-5], [50, 90, 99, 99.5, 100])],
                           "p50_p90_p99_p995_max": [round(float(v), 4) for v in pc], "samples": samples, "device": bpy.context.scene.cycles.device,
                           "seconds": round(time.time() - t0), "materials": [m.name for m in mats]}
            print("  baked", {k: v for k, v in report[idx].items() if k != "materials"})
    (work() / f"{SCENE}_lightmaps.json").write_text(json.dumps(report, indent=1))
    stills_dir(SCENE).mkdir(parents=True, exist_ok=True)
    (stills_dir(SCENE) / "bake.json").write_text(json.dumps(report, indent=1))
    apply_light_set("day")
    for c in ("Art", "Skin"):
        bpy.data.collections[c].hide_render = False
        bpy.data.collections[c].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


# ---------------------------------------------------------------- privacy
KEEP_PROPS = {"lightmap", "lightmap_intensity", "lightmap_night", "lightmap_night_intensity"}
LAYOUT_PREFIX = ("DoorLeaf_", "Marker_", "Spot_", "Mirror_")


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private():
    kinds = ("scenes", "worlds", "objects", "meshes", "materials", "collections", "cameras", "lights", "images", "node_groups", "screens",
             "window_managers", "workspaces", "curves", "fonts", "libraries")
    dropped = 0
    for kind in kinds:
        for idb in getattr(bpy.data, kind):
            if getattr(idb, "library", None) is not None:
                continue
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
    for lib in bpy.data.libraries:
        p = Path(bpy.path.abspath(lib.filepath))
        try:
            rel = "//" + os.path.relpath(p, base).replace("\\", "/")
        except ValueError:
            rel = "//" + p.name
        set_path(lib, "filepath", rel)
    for im in bpy.data.images:
        if im.library is not None or im.packed_file or im.source != "FILE" or not im.filepath:
            continue
        p = Path(bpy.path.abspath(im.filepath))
        try:
            rel = "//" + os.path.relpath(p, base).replace("\\", "/")
        except ValueError:
            rel = "//" + p.name
        set_path(im, "filepath", rel)
    for im in bpy.data.images:
        if im.library is None and im.packed_file and im.filepath and not im.filepath.startswith("//generated/"):
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
    global ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, STANDIN, LIGHTS
    c = bpy.data.collections
    ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, STANDIN, LIGHTS = (c.get(n) for n in ("Art", "Props", "Arch", "Skin", "Doors", "Layout", "Standins", "Lights"))
    for m in bpy.data.materials:
        MATS[m.name] = m


# ---------------------------------------------------------------- export
def caps():
    """docs/renders/<scene>/caps.json: {"day": {"factor": {material: f}}, "night": {"factor": {...}}}, multiplied into each set's intensity."""
    p = Path(arg("--caps")) / f"{SCENE}.json" if arg("--caps") else stills_dir(SCENE) / "caps.json"
    if not p.exists():
        return {"day": {}, "night": {}}
    d = json.loads(p.read_text())
    return {st: d.get(st, {}).get("factor", {}) for st in ("day", "night")}


def stage_export():
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    for c in ("Art", "Skin"):
        bpy.data.collections[c].hide_viewport = True
    apply_light_set("export")
    leaves = list(bpy.data.collections["Doors"].objects)
    stash = {o.name: {k: o[k] for k in o.keys()} for o in leaves}
    for o in leaves:
        for k in list(o.keys()):
            del o[k]
    cp = caps()
    base = {}
    for m in bpy.data.materials:
        for st, kk in (("day", "lightmap_intensity"), ("night", "lightmap_night_intensity")):
            if kk in m:
                base[(m.name, kk)] = m[kk]
                if m.name in cp[st]:
                    m[kk] = round(m[kk] * cp[st][m.name], 4)
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
    for (mn, kk), v in base.items():
        bpy.data.materials[mn][kk] = v
    apply_light_set("day")
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
    code = check_layout.main(["--scene", SCENE, "--collection", "Art"])
    print("CHECK_LAYOUT exit", code)


# ---------------------------------------------------------------- review stills
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


WIDE = {"construction": ((11.3, 5.6, 8.5), (-4.0, 1.0, -4.0), 72, False),
        "service_corridor": ((15.0, 6.0, 3.0), (19.0, 0.0, -7.0), 66, True),
        "mirror_bathroom": ((0.0, 7.4, 6.6), (0.0, 0.0, -0.4), 58, True)}
PLAN = {"construction": ((-12.6, 12.6, -9.6, 9.6), 3.3), "service_corridor": ((-26.6, 20.6, -15.2, 1.6), 2.3),
        "mirror_bathroom": ((-5.6, 5.6, -4.6, 4.6), 2.3)}
STILL_EXPOSURE = {"construction": 1.6, "service_corridor": 0.0, "mirror_bathroom": 0.0}
CEILINGS = {"Soffit_Concrete", "Soffit_Paint", "Car_Ceiling", "Ceiling_Grid"}


def shots():
    E = 1.6
    M = model(SCENE)
    (pos, look, pitch) = M.still
    p0 = (pos[0] + 0.05, pos[1] + E, pos[2])
    ln = math.hypot(*look)
    t0 = (p0[0] + look[0] / ln * 6, p0[1] + 6 * math.tan(math.radians(pitch)) - 0.2, p0[2] + look[1] / ln * 6)
    out = {"1_arrival": (p0, t0, 75, False), "2_wide": WIDE[SCENE]}
    d = json.loads(bpy.context.scene.get("detail") or "{}")
    if d:
        out["3_detail"] = (tuple(d["cam"]), tuple(d["at"]), 62, False)
    return out


def high(o, top):
    return o.type == "MESH" and min((o.matrix_world @ v.co).z for v in o.data.vertices) > top


def render_still(path, loc, tgt, fov, cut, exposure=0.0):
    sc = bpy.context.scene
    hidden = []
    if cut:                                               # a cutaway: the ceiling and everything hung from it left out
        lid = [o for o in bpy.data.collections["Skin"].objects if o.data.materials[0].name in CEILINGS]
        for o in lid + [o for o in bpy.data.collections["Props"].objects if high(o, 2.3)]:
            if not o.hide_render:
                o.hide_render = True
                hidden.append(o)
    sc.view_settings.exposure = arg("--exposure", 0.0, float) + exposure
    sc.camera = look_cam(path.stem, loc, tgt, fov)
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 1080, arg("--pct", 100, int)
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 90
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
    print("STILL", path.name, path.stat().st_size, "q", q)


def stage_render():
    sc = bpy.context.scene
    d = stills_dir(SCENE)
    d.mkdir(parents=True, exist_ok=True)
    scrub_private()
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
    for c, hide in (("Art", False), ("Skin", False), ("Doors", False), ("Standins", True), ("Lights", False), ("Arch", True)):
        bpy.data.collections[c].hide_render = hide
    setup_cycles(arg("--render-samples", 128, int))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.03
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    which = arg("--only", "all")
    apply_light_set("day")
    sh = shots()
    for key, (loc, tgt, fov, cut) in sh.items():
        if which in ("all", key):
            render_still(d / f"{key}.jpg", loc, tgt, fov, cut, STILL_EXPOSURE[SCENE] + (1.0 if cut else 0.0))
    if which in ("all", "night"):
        apply_light_set("night")
        loc, tgt, fov, cut = sh["1_arrival"]
        render_still(work() / f"{SCENE}_night_arrival.jpg", loc, tgt, fov, cut, arg("--night-exposure", 1.5, float))
        apply_light_set("day")
    if which in ("all", "plan"):
        (x0, x1, z0, z1), top = PLAN[SCENE]
        span = max(x1 - x0, z1 - z0)
        cam = look_cam("plan", ((x0 + x1) / 2, 30.0, (z0 + z1) / 2), None, ortho=span)
        cam.rotation_euler = (0, 0, 0)
        sc.camera = cam
        hidden = []
        lid = [o for o in bpy.data.collections["Skin"].objects if o.data.materials[0].name in CEILINGS]
        for o in lid + [o for o in bpy.data.collections["Props"].objects if high(o, top) or o.name.startswith("decor_Beam")]:
            if not o.hide_render:
                o.hide_render = True
                hidden.append(o)
        bpy.data.collections["Lights"].hide_render = True
        world = sc.world
        bg = world.node_tree.nodes["Background"]
        old = bg.inputs["Strength"].default_value
        bg.inputs["Color"].default_value = (1, 1, 1, 1)
        bg.inputs["Strength"].default_value = 0.9
        W = 1600
        asp = (x1 - x0) / (z1 - z0)
        sc.render.resolution_x, sc.render.resolution_y = (W, int(W / asp)) if asp >= 1 else (int(W * asp), W)
        sc.render.resolution_percentage = 100
        sc.view_settings.exposure = 0.0
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
        bpy.data.collections["Lights"].hide_render = False
        print("PLAN", path, sc.render.resolution_x, sc.render.resolution_y)


# ---------------------------------------------------------------- the sky halls: the kit's piece, placed
def build_sky():
    """sky_hall_<nn>: the kit's sky_hall at (0, 0, 0), yaw 0 by kit_place.py (the layout appended; the suffix it adds taken off again, so the
    greybox's door ids stay), the greybox's own extra empties (a mannequin spot in 02 and 04), the kit's Art collection LINKED (not copied: the
    page draws world/kit/sky_hall.glb here). Writes world/<scene>.json and runs the layout check on the kit's art."""
    import kit_place
    import export_scene
    import check_layout
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    lay = bpy.data.collections.new("Layout")
    sc.collection.children.link(lay)
    made = kit_place.place("sky_hall", suffix="KIT", at=(0.0, 0.0, 0.0), yaw_deg=0.0, art=False, collection=lay)
    for n in made:
        ob = bpy.data.objects[n]
        assert n.endswith("_KIT"), n
        ob.name = n[:-4]
        assert ob.name == n[:-4], f"{n}: the name {n[:-4]} is taken"
        ob.hide_render = True
        if ob.type == "MESH":
            ob.display_type = "WIRE"
    M = model(SCENE)
    for d in M.doors:                                     # kit_place writes a turned door's yaw in [-180, 180): 180 comes back as -180; keep the greybox's
        ob = bpy.data.objects.get(d["name"])
        want = float(d["props"]["closed_yaw_deg"])
        if ob is not None and abs((float(ob["closed_yaw_deg"]) - want + 180.0) % 360.0 - 180.0) < 0.05:
            ob["closed_yaw_deg"] = want
    have = {o.name for o in lay.objects}
    added = []
    for e in M.empties:
        if e["name"] in have:
            continue
        ob = bpy.data.objects.new(e["name"], None)
        ob.location = B(e["pos"])
        if e["face"]:
            ob.rotation_euler = (0, 0, math.atan2(e["face"][0], e["face"][1]))
        for k, v in e["props"].items():
            ob[k] = v
        ob.empty_display_size = 0.3
        lay.objects.link(ob)
        added.append(e["name"])
    p = blend_path(SCENE)
    p.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(p))
    with bpy.data.libraries.load(str(ROOT / "blender/kit/sky_hall.blend"), link=True, relative=True) as (src, dst):
        dst.collections = [c for c in src.collections if c == "Art"]
    art = dst.collections[0]
    sc.collection.children.link(art)
    print(f"KIT {SCENE}: {len(made)} layout objects from the kit, {added} added from the greybox, the kit's Art linked ({len(art.all_objects)} objects)")
    export_scene.write(SCENE, world_json(SCENE))
    code = check_layout.main(["--scene", SCENE, "--collection", art.name])
    print("CHECK_LAYOUT exit", code)
    scrub_private()
    bpy.ops.wm.save_mainfile()


# ---------------------------------------------------------------- main
def main():
    global SCENE
    for sc in arg("--scenes", "construction").split(","):
        SCENE = sc
        print(f"==== {sc} stage {STAGE}")
        if sc in SKY:
            build_sky()
            print(f"==== {sc} done")
            continue
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
