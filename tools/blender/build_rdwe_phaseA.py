"""Dresses and lights the seven Phase A rooms of Right Door, Wrong Exit (docs/BLENDER_AREAS.md, section 7, step 2): rdwe_dining, rdwe_hallway,
rdwe_teal, rdwe_teal2, rdwe_flooded, rdwe_trampoline and rdwe_grocery, the rooms that exist in games/rdwe/scenes/*.js, remade larger and
psychedelic around the greybox (tools/blender/build_rdwe_greybox.py) exactly (docs/renders/rdwe_dining/README.md covers all seven).

    blender -b --factory-startup --python tools/blender/build_rdwe_phaseA.py -- --scenes rdwe_dining[,...] --stage all [--samples 768]
    blender -b --factory-startup blender/scenes/<scene>.blend --python tools/blender/build_rdwe_phaseA.py -- --scenes <scene> --stage bake|export|axes|check|render
    python tools/blender/build_rdwe_phaseA.py --pack <scene> [--work <dir>]        (no Blender: WebP lightmaps and textures -> world/)
    python tools/blender/build_rdwe_phaseA.py --caps <scene>                        (no Blender: writes caps into world/<scene>.glb as export would)

The hotel floors' method (tools/blender/build_hotel_floor2.py): stages art (the layout objects from the greybox model, the shell as seen, the
dressing, the lights; saves blender/scenes/<scene>.blend) -> bake (the shell and the props on fixed lightmap PAGES, Cycles, OIDN, a highlight
shoulder; 8-bit PNGs in the work folder) -> export (the GLB to the work folder; the layout through tools/blender/export_scene.py) -> axes ->
check (tools/blender/check_layout.py) -> render (docs/renders/<scene>/1_arrival, 2_wide, 3_detail.jpg and plan.jpg). `all` runs them in order.

The layout is the greybox's, unchanged: every COL_ box, DoorLeaf_ (with its `look`), Link_/Arrive_, Marker_, Zone_ and Spot_ comes from
build_rdwe_greybox.build(<scene>), so export_scene.py writes the same world/<scene>.json. The shell as seen is made from the greybox's shell boxes:
each face cut into pieces of 4 m at most, a piece kept when the air in front of it is inside the room and in no other shell box. The furniture
boxes (the table, the sofas, the shelving...) get dressed props that cover them; the shell boxes keep grey twins in Art/Arch (hidden; for the
layout check and the plan). Every door leaf is its own mesh, made from its `look` (form, finish, handle), so no two doors look alike.

Light: baked indoors on UV1 (`lightmap`); the dining room also has an alt set, its green lamp off (`lightmap_night`, the page's lamp-off beat).
Unbaked materials: Lamp_Emit (the page's lamps), Emergency_Emit (EXIT signs, the red door, the red glow), Window_Lit (the teal room's fake
window), Grid_Emit and Amber_Emit (the glowing grid, the hallway's amber bars), Void (the black past every door), Water (the flooded floor's
skin, transparent), Glass_Clear.
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import build_rdwe_greybox as GB  # noqa: E402

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
SAMPLES = arg("--samples", 768, int)
DEVICE = arg("--device", "auto")
MARGIN_PX = 8
TEXDIR = ROOT / "blender/textures"
SCENE = None
SCENES = ["rdwe_dining", "rdwe_hallway", "rdwe_teal", "rdwe_teal2", "rdwe_flooded", "rdwe_trampoline", "rdwe_grocery", "rdwe_repeating_room",
          "rdwe_finale"]
PAGES = {s: [2048, 2048] for s in SCENES}
PAGES["rdwe_teal"] = PAGES["rdwe_teal2"] = [1536, 1536]
PAGES["rdwe_trampoline"] = PAGES["rdwe_grocery"] = [2048, 2048, 2048]
PAGES["rdwe_repeating_room"] = [1536, 1536]
PAGES["rdwe_finale"] = [2048, 2048, 2048]
PAGE2 = {"rdwe_trampoline": {"Truss_Steel"}, "rdwe_grocery": {"Gondola", "Gondola_Back", "Kick"},
         "rdwe_finale": {"Rack_Body", "Gondola", "Cubicle_Panel", "Cubicle_Frame"}}   # a third page: the big repeated props
ALT = {"rdwe_dining": "the green lamp off"}            # scenes with a second light set (lightmap_night: maps n + 2)
WHITE_CAP = 12.0
SHOULDER = {"default": (75.0, 2.5)}
FURNITURE = {"rdwe_repeating_room": ("Armchair", "Side_Table"),
             "rdwe_finale": ("Cubicle_", "Desk_", "House_", "Rack_", "Aisle_Shelf_", "Hall_Fountain"),
             "rdwe_dining": ("Table", "Chair_", "Sideboard", "China_Tower"), "rdwe_hallway": (), "rdwe_teal": ("Sofa_", "Plant"),
             "rdwe_teal2": ("Sofa", "Plant_Tall"), "rdwe_flooded": ("Rail_", "Heap_"), "rdwe_trampoline": ("Column_", "AngledWall_"),
             "rdwe_grocery": ("Shelf_", "Post_", "Cart", "Stanchion_")}
NO_LIGHTMAP = {"Lamp_Emit", "Lamp_Emit_Green", "Emergency_Emit_Green", "Screen_Emit", "Server_Emit", "Emergency_Emit", "Window_Lit", "Grid_Emit", "Amber_Emit", "Glow_Emit", "Void", "Water", "Glass_Clear"}
NO_BAKE_VIS = {"Water", "Glass_Clear"}                   # hidden while baking (they would shade the floor under them)


def work():
    p = Path(arg("--work", str(Path(os.environ.get("TEMP", tempfile.gettempdir())) / "farway_rdwe_phaseA")))
    p.mkdir(parents=True, exist_ok=True)
    return p


def world_json(sc):
    return ROOT / f"world/{sc}.json"


def glb_path(sc):
    return ROOT / f"world/{sc}.glb"


def blend_path(sc):
    return ROOT / f"blender/scenes/{sc}.blend"


def stills_dir(sc):
    return ROOT / f"docs/renders/{sc}"


def lm_url(sc, n):
    return f"world/lightmaps/{sc}_{n}.webp"


# ================================================================ plain Python (no Blender): pack, caps
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
        dst = out / (png.stem + ".webp")
        im.save(dst, "WEBP", quality=90, method=6)
        print(f"{dst.relative_to(ROOT)}  {im.size[0]}x{im.size[1]}  {dst.stat().st_size / 1e3:.0f} KB")
    raw = w / f"{sc}_raw.glb"
    dst = glb_path(sc)
    subprocess.run([sys.executable, str(ROOT / "tools/webp_glb.py"), str(raw), str(dst), "90"], check=True)
    print(f"{dst.relative_to(ROOT)}  {dst.stat().st_size / 1e6:.2f} MB")


def apply_caps(sc):
    """caps.json's factors on each material's lightmap_intensity (and lightmap_night_intensity), written into the packed GLB's JSON chunk: the
    same numbers stage_export writes from the .blend with the same caps.json (the raw GLB carries the uncapped intensities; `base` keeps them)."""
    import struct
    p = glb_path(sc)
    b = p.read_bytes()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    rest = b[20 + n:]
    cj = json.loads((stills_dir(sc) / "caps.json").read_text())
    f, fn = cj.get("factor", {}), cj.get("factor_night", cj.get("factor", {}))
    for m in j["materials"]:
        ex = m.get("extras", {})
        if "lightmap" not in ex:
            continue
        assert "base" in ex, f"{m['name']}: no uncapped intensities (re-pack the raw GLB before capping again)"
        base = ex.pop("base")
        for k, ff in (("lightmap_intensity", f), ("lightmap_night_intensity", fn)):
            if k in base:
                ex[k] = round(base[k] * ff.get(m["name"], 1.0), 4)
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    out = b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + len(rest)) + struct.pack("<I", len(js)) + b"JSON" + js + rest
    p.write_bytes(out)
    print("CAPS written into", p.name, {k: v for k, v in f.items() if v != cj.get("gain")})


if bpy is None:
    if "--pack" in args:
        pack(arg("--pack"))
    elif "--caps" in args:
        apply_caps(arg("--caps"))
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


def C(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


def lerp(a, b, t):
    t = np.asarray(t)[..., None] if np.ndim(t) else t
    return a * (1 - t) + b * t


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def grid(n):
    Y, X = np.mgrid[0:n, 0:n] / n
    return X, Y


def gen_shag(seed, a, b, c, n=512):
    """A deep shag pile: fine fibre noise over a slow swirl, three greens."""
    rng = np.random.default_rng(seed)
    fib = rng.random((n, n))
    fib = (fib + np.roll(fib, 1, 0) + np.roll(fib, 1, 1) + np.roll(fib, (1, 1), (0, 1))) / 4
    slow = vnoise(n, n, rng, 4, 3)
    t = np.clip(0.5 + (fib - 0.5) * 1.6 + (slow - 0.5) * 0.8, 0, 1)
    return np.clip(lerp(lerp(C(a), C(b), smooth(0.0, 0.6, t)), C(c), smooth(0.6, 1.0, t)), 0, 1)


def gen_swirl(seed, ground, ink1, ink2, n=512):
    """The dining room's paper: cream, with soft paisley swirls in pink and mint that seem to turn as you look (psychedelic, slightly wrong)."""
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    w = vnoise(n, n, rng, 4, 2)
    r = np.hypot(np.mod(X * 3, 1) - 0.5, np.mod(Y * 3, 1) - 0.5)
    th = np.arctan2(np.mod(Y * 3, 1) - 0.5, np.mod(X * 3, 1) - 0.5)
    sw = 0.5 + 0.5 * np.sin(th * 3 + r * 26 + w * 6)
    band = smooth(0.82, 0.95, sw) * smooth(0.48, 0.3, r)
    band2 = smooth(0.85, 0.97, 0.5 + 0.5 * np.sin((X + Y) * 2 * math.pi * 6 + w * 5))
    base = lerp(C(ground), C(ground) * 0.93, vnoise(n, n, rng, 5, 8))
    out = lerp(base, C(ink1), band * 0.55)
    return np.clip(lerp(out, C(ink2), band2 * 0.35 * (1 - band)), 0, 1)


def gen_plaid(seed, n=512):
    """The hallway's printed plaid, grey-beige, with violet and lime threads gone a little too bright."""
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    base = lerp(C("#c9c1ae"), C("#bcb39e"), vnoise(n, n, rng, 4, 6))
    out = base.copy()
    for period, width, col, k in ((0.5, 0.06, "#8f8676", 0.45), (0.25, 0.012, "#7a3fb8", 0.55), (0.5, 0.01, "#9ee03a", 0.45)):
        dx = np.abs(np.mod(X + period / 2, period) - period / 2) < width
        dy = np.abs(np.mod(Y + period / 2, period) - period / 2) < width
        m = (dx | dy).astype(float) * (1 + ((dx & dy).astype(float)))
        out = lerp(out, C(col), np.clip(m * k, 0, 0.9))
    return np.clip(out, 0, 1)


def gen_diamond_carpet(seed, n=512):
    """The hallway's worn tan carpet with a lattice of dark diamonds."""
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    base = lerp(C("#a98552"), C("#8e6c3e"), vnoise(n, n, rng, 5, 6))
    base = lerp(base, C("#c49a5e"), smooth(0.7, 1.0, rng.random((n, n))) * 0.3)
    d = np.abs(np.mod(X * 4, 1) - 0.5) + np.abs(np.mod(Y * 4, 1) - 0.5)
    line = smooth(0.06, 0.0, np.abs(d - 0.45))
    dot = smooth(0.08, 0.02, d)
    return np.clip(lerp(lerp(base, C("#4a2e1a"), line * 0.8), C("#b03a8a"), dot * 0.8), 0, 1)


def gen_pixels(seed, n=256, cells=16):
    """Mossy pixel-block stone: square cells of greys and greens."""
    rng = np.random.default_rng(seed)
    pal = [C(h) for h in ("#5e6a52", "#4c5a40", "#6f7c5c", "#3f6a2c", "#5aa03a", "#7c8a6a", "#2f4a24", "#8cd04a")]
    cell = rng.integers(0, len(pal), (cells, cells))
    cell = np.where(rng.random((cells, cells)) < 0.25, 4 + rng.integers(0, 4, (cells, cells)), cell)
    img = np.array([[pal[cell[i * cells // n, j * cells // n]] for j in range(n)] for i in range(n)])
    gx = (np.arange(n) % (n // cells) == 0)
    img[gx, :] *= 0.6
    img[:, gx] *= 0.6
    return np.clip(img, 0, 1)


def gen_fleck(seed, dark, n=512):
    """The teal rooms' coarse brown flecked carpet."""
    rng = np.random.default_rng(seed)
    a, b = (C("#5a3f28"), C("#2c1d12")) if dark else (C("#6b4b30"), C("#3a2718"))
    base = lerp(a, b, vnoise(n, n, rng, 5, 8) * 0.8)
    out = base.copy()
    for h, p in (("#cdb48c", 0.06), ("#17110b", 0.08), ("#e8743a", 0.03), ("#3dd6c8", 0.015)):
        m = rng.random((n, n)) < p
        out[m] = C(h)
    return np.clip(out, 0, 1)


def gen_tiles(seed, cols, a, b, grout, gw, n=512):
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    ci, cj = np.floor(X * cols).astype(int), np.floor(Y * cols).astype(int)
    pick = rng.random((cols, cols))
    t = lerp(C(a), C(b), pick[cj, ci])
    t = lerp(t, t * 0.94, vnoise(n, n, rng, 4, 8) * 0.6)
    fx, fy = np.mod(X * cols, 1), np.mod(Y * cols, 1)
    g = (np.minimum(fx, 1 - fx) < gw * cols / 2) | (np.minimum(fy, 1 - fy) < gw * cols / 2)
    t[g] = C(grout)
    return np.clip(t, 0, 1)


def gen_sky(seed, w=2048, h=512):
    """The flooded corridor's painted sky: a saturated blue, fat cumulus, a green hill line, a strip of yellow flowers; tiles along u."""
    rng = np.random.default_rng(seed)
    Y, X = np.mgrid[0:h, 0:w]
    y, x = Y / h, X / w
    sky = lerp(C("#2a6dff"), C("#8fd0ff"), smooth(0.0, 0.75, y))
    cl = vnoise(h, w, rng, 5, 3)
    cloud = smooth(0.55, 0.7, cl * (1 - smooth(0.25, 0.75, y)) + 0.25 * (1 - y))
    sky = lerp(sky, C("#fff6f0"), cloud)
    sky = lerp(sky, C("#ffb0e0"), smooth(0.75, 0.9, cl) * cloud * 0.4)
    hill = 0.78 + 0.06 * np.sin(x * 2 * math.pi * 2 + 1.3) + 0.03 * np.sin(x * 2 * math.pi * 5)
    g = y > hill
    grass = lerp(C("#3fbf3a"), C("#1f7a2a"), smooth(0.0, 1.0, (y - hill) * 6))
    sky[g] = grass[g]
    fl = (y > 0.93) & (rng.random((h, w)) < 0.05)
    sky[fl] = C("#ffe23a")
    return np.clip(sky, 0, 1)


def gen_photos(seed, n=1024, k=4):
    """The photo wall: a 4 x 4 atlas of family snapshots, blurred figures on saturated grounds, every face missing."""
    rng = np.random.default_rng(seed)
    img = np.zeros((n, n, 3))
    s = n // k
    grounds = ["#e7a35a", "#6ab0d8", "#c46aa8", "#8cc46a", "#d8c46a", "#6a8cd8", "#d86a6a", "#6ad8b8"]
    for i in range(k):
        for j in range(k):
            Y, X = np.mgrid[0:s, 0:s] / s
            g = lerp(C(rng.choice(grounds)), C(rng.choice(grounds)), smooth(0.2, 1.0, Y))
            for f in range(rng.integers(1, 4)):
                cx, w = 0.2 + 0.6 * rng.random(), 0.12 + 0.08 * rng.random()
                body = (np.abs(X - cx) < w * (0.6 + Y)) & (Y > 0.45)
                head = np.hypot(X - cx, Y - 0.33) < w * 0.75
                col = C(rng.choice(["#3a2a24", "#5a4434", "#2a3a5a", "#6a2a3a"]))
                g[body] = col
                g[head] = C("#f0dcc4")
            g = lerp(g, C("#f4ead8"), 0.15)
            img[i * s:(i + 1) * s, j * s:(j + 1) * s] = g
    return np.clip(img, 0, 1)


def gen_grid(n=256):
    """The glowing green grid under the peeled wallpaper."""
    X, Y = grid(n)
    f = 8
    d = np.minimum(np.minimum(np.mod(X * f, 1), 1 - np.mod(X * f, 1)), np.minimum(np.mod(Y * f, 1), 1 - np.mod(Y * f, 1)))
    v = smooth(0.08, 0.0, d)
    out = np.zeros((n, n, 3))
    out[..., 1] = 0.08 + 0.92 * v
    out[..., 0] = 0.05 * v
    out[..., 2] = 0.2 * v
    return out


def gen_quilt(seed, a, b, n=512, cells=4):
    """Padded vinyl: square pads with dark seams and a soft highlight (the trampoline park's walls and frames)."""
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    fx, fy = np.mod(X * cells, 1), np.mod(Y * cells, 1)
    edge = np.minimum(np.minimum(fx, 1 - fx), np.minimum(fy, 1 - fy))
    pad = smooth(0.0, 0.18, edge)
    base = lerp(C(b), C(a), pad)
    return np.clip(lerp(base, base * 0.9, vnoise(n, n, rng, 4, 8) * 0.5), 0, 1)


def gen_weave(seed, n=256):
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    w = 0.5 + 0.5 * np.sin(X * 2 * math.pi * 32) * np.sin(Y * 2 * math.pi * 32)
    base = lerp(C("#141416"), C("#2a2a30"), w * 0.7 + vnoise(n, n, rng, 3, 8) * 0.3)
    return np.clip(base, 0, 1)


def gen_speckle(seed, a, b, n=512):
    """Glossy speckled vinyl tile in big pastel squares (the grocery)."""
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    ck = ((np.floor(X * 4) + np.floor(Y * 4)) % 2).astype(float)
    base = lerp(C(a), C(b), ck)
    sp = rng.random((n, n))
    base[sp < 0.03] *= 0.7
    base[(sp > 0.97)] = base[(sp > 0.97)] * 0.5 + 0.5 * C("#ff4fa0")
    fx, fy = np.mod(X * 4, 1), np.mod(Y * 4, 1)
    g = (np.minimum(fx, 1 - fx) < 0.004) | (np.minimum(fy, 1 - fy) < 0.004)
    base[g] *= 0.85
    return np.clip(base, 0, 1)


def gen_rings(seed, n=512):
    """The dining room's round rug: concentric rings in pink, orange, teal and cream, a little off-centre and wobbling."""
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    r = np.hypot(X - 0.5, Y - 0.5) * 2 + 0.03 * (vnoise(n, n, rng, 3, 3) - 0.5)
    pal = np.array([C(h) for h in ("#ff5aa8", "#ff9a3a", "#2ad0c0", "#fff0d0", "#8a4ad8")])
    k = np.floor(r * 9).astype(int) % len(pal)
    out = pal[k]
    edge = np.abs(np.mod(r * 9, 1) - 0.5) > 0.46
    out[edge] *= 0.8
    return np.clip(out, 0, 1)


def gen_door_paper(seed, n=512):
    """The repeating room's paper: lilac, and on it a lattice of little pink doors, each a hair different (the room that repeats)."""
    rng = np.random.default_rng(seed)
    X, Y = grid(n)
    base = lerp(C("#b89af0"), C("#a688e4"), vnoise(n, n, rng, 4, 6))
    k = 6
    fx, fy = np.mod(X * k, 1), np.mod(Y * k, 1)
    ci, cj = np.floor(X * k).astype(int), np.floor(Y * k).astype(int)
    jit = rng.random((k, k)) * 0.06
    door = (np.abs(fx - 0.5) < 0.14 + jit[cj, ci] * 0.3) & (fy > 0.2) & (fy < 0.8)
    knob = np.hypot(fx - 0.6, fy - 0.5) < 0.025
    out = base.copy()
    out[door] = C("#ff8ac8")
    out[door & knob] = C("#ffe23a")
    return np.clip(out, 0, 1)


def gen_room_picture(seed, n=512):
    """A picture of this room, with a picture of this room in it: lilac frames inside frames, a pink door at the heart."""
    X, Y = grid(n)
    out = np.zeros((n, n, 3)) + C("#b89af0")
    for i in range(7):
        m = 0.06 * i
        band = (np.minimum(np.minimum(X - m, 1 - m - X), np.minimum(Y - m, 1 - m - Y)))
        ring = (band > 0) & (band < 0.025)
        out[ring] = C("#c8a040") if i % 2 else C("#7a5ad0")
    door = (np.abs(X - 0.5) < 0.05) & (np.abs(Y - 0.52) < 0.09)
    out[door] = C("#ff5aa8")
    return np.clip(out, 0, 1)


def gen_brushed(n=256):
    rng = np.random.default_rng(5)
    v = rng.random((n, 1)) * 0.5 + rng.random((n, n)) * 0.1
    return np.repeat(np.clip(0.75 + 0.25 * (v - 0.3), 0, 1)[..., None], 3, axis=2)


def gen_concrete(seed, n=512):
    rng = np.random.default_rng(seed)
    v = vnoise(n, n, rng, 6, 4)
    base = lerp(C("#8e8a82"), C("#6e6a64"), v)
    base[rng.random((n, n)) < 0.01] *= 0.8
    return np.clip(base, 0, 1)


GEN = {}


def mk_image(name, arr):
    h, w = arr.shape[:2]
    im = bpy.data.images.new(name, w, h, alpha=False)
    im.colorspace_settings.name = "sRGB"
    px = np.ones((h, w, 4), np.float32)
    px[..., :3] = arr[::-1, :, :3]                      # numpy's row 0 is the top; Blender's is the bottom
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


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, tex=None, img=None, tint=None, emit=None, alpha=None, tile=1.0):
    """A Principled material; `tint` multiplies the texture (a Mix node set to Multiply: the glTF exporter writes it as baseColorFactor)."""
    if name in MATS:
        return MATS[name]
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
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    if alpha is not None:
        bsdf.inputs["Alpha"].default_value = alpha
        set_blend(m)
    TILES[name] = tile
    MATS[name] = m
    return m


PLASTER, WOOD, LINEN, MARBLE, CONCRETE = "rdwe/plastered_wall_04_diff_1k.jpg", "rdwe/dark_wood_diff_1k.jpg", "rdwe/rough_linen_diff_512.jpg", \
    "rdwe/marble_01_diff_1k.jpg", "rdwe/concrete_floor_02_diff_1k.jpg"
VINYL, ACOUSTIC, PAINT, PLYWOOD = "rdwe/floor_vinyl_diff.jpg", "rdwe/ceiling_tile_diff.jpg", "rdwe/wall_paint_diff.jpg", "rdwe/plywood_diff_1k.jpg"
WARM, COOL = (1.0, 0.8, 0.58), (0.86, 0.92, 1.0)

# every door finish (build_rdwe_greybox.FINISHES) as its own leaf material: saturated, the room's colours pushed a step too far
FINISH = {"oak": ("tex", "#d8a060"), "teal paint": ("paint", "#18b8b0"), "mint paint": ("paint", "#7cf0b8"), "pink laminate": ("gloss", "#ff6ab4"),
          "brushed steel": ("steel", "#b8bcc2"), "cream gloss": ("gloss", "#f4e8c8"), "cherry red": ("gloss", "#d81c2a"),
          "bottle green": ("paint", "#0e6a34"), "lilac": ("paint", "#b48cf0"), "black lacquer": ("gloss", "#141418"), "birch": ("tex", "#f0d8a8"),
          "orange vinyl": ("gloss", "#ff7a18"), "sky blue": ("paint", "#5ab4ff"), "mustard": ("paint", "#e0b020"), "plum": ("paint", "#7a2a6a")}


def leaf_mat(finish):
    name = "Leaf_" + "".join(w.capitalize() for w in finish.replace("(", "").replace(")", "").split())
    kind, h = FINISH.get(finish, ("paint", "#888888"))
    col = srgb_lin(h)
    if kind == "tex":
        return material(name, tex=WOOD, tint=tuple(min(1.0, c * 1.6) for c in col), rough=0.45, tile=0.9).name
    if kind == "steel":
        return material(name, img=GEN["gen_brushed"], tint=col, rough=0.35, metal=0.85, tile=0.5).name
    return material(name, tex=PAINT, tint=col, rough=0.3 if kind == "gloss" else 0.6, tile=1.0).name


def common_materials():
    g = {k: mk_image(k, f()) for k, f in (("gen_brushed", gen_brushed),)}
    material("Lamp_Emit", color=(1.0, 0.93, 0.8), rough=0.9, emit=(WARM, 4.0))
    material("Emergency_Emit", color=(1.0, 0.1, 0.08), rough=0.5, emit=((1.0, 0.06, 0.04), 6.0))
    material("Void", color=(0.0, 0.0, 0.0), rough=1.0)
    material("Glass_Clear", color=(0.8, 0.9, 0.95), rough=0.05, alpha=0.18)
    material("Brass", img=g["gen_brushed"], tint=srgb_lin("#d4a548"), rough=0.3, metal=0.9, tile=0.3)
    material("Chrome", img=g["gen_brushed"], tint=srgb_lin("#e0e4ea"), rough=0.15, metal=1.0, tile=0.3)
    material("Iron", img=g["gen_brushed"], tint=srgb_lin("#3a3c40"), rough=0.5, metal=0.7, tile=0.3)
    material("Glass_Knob", color=srgb_lin("#bfe6ff"), rough=0.05)
    material("Leaf_Glass", color=srgb_lin("#20303a"), rough=0.1, metal=0.2)
    material("Mirror", color=srgb_lin("#c8d2dc"), rough=0.04, metal=1.0)
    material("Rubber_Black", color=srgb_lin("#1a1a1c"), rough=0.7)
    material("Plastic_White", color=srgb_lin("#e8e4da"), rough=0.5)
    material("Standin_Grey", color=(0.4, 0.38, 0.34), rough=0.9)
    for f in GB.FINISHES:
        leaf_mat(f)


def room_materials():
    s = SCENE
    if s == "rdwe_dining":
        g = {k: mk_image(k, f()) for k, f in (("gen_shag", lambda: gen_shag(11, "#1f5a18", "#3f9a2a", "#9ae05a")),
                                               ("gen_shag_stair", lambda: gen_shag(12, "#0e3010", "#1e5a1c", "#4a9a3a")),
                                               ("gen_swirl", lambda: gen_swirl(21, "#f4e2bc", "#ff8ac8", "#7af0c0")),
                                               ("gen_photos", lambda: gen_photos(31)), ("gen_rings", lambda: gen_rings(32)))}
        material("Rug_Rings", img=g["gen_rings"], rough=1.0)
        material("Wall_Cream", img=g["gen_swirl"], rough=0.8, tile=1.6)
        material("Shag_Green", img=g["gen_shag"], rough=1.0, tile=1.1)
        material("Ceiling_Dining", tex=PLASTER, tint=srgb_lin("#fff2e6"), rough=0.95, tile=2.6)
        material("Stair_Carpet", img=g["gen_shag_stair"], rough=1.0, tile=0.8)
        material("Stair_Wall", tex=PLASTER, tint=srgb_lin("#8a9a78"), rough=0.95, tile=2.0)
        material("Maple", tex=WOOD, tint=srgb_lin("#ffb060"), rough=0.4, tile=0.9)
        material("Maple_Dark", tex=WOOD, tint=srgb_lin("#c87838"), rough=0.45, tile=0.9)
        material("Trim_Cream", tex=PAINT, tint=srgb_lin("#fff4dc"), rough=0.5, tile=1.0)
        material("China", color=srgb_lin("#f6f2ea"), rough=0.15)
        material("China_Rim", color=srgb_lin("#3a8ad8"), rough=0.2)
        material("Ceramic_Green", color=srgb_lin("#2a8a50"), rough=0.2)
        material("Sheer", tex=LINEN, tint=srgb_lin("#fff6ea"), rough=0.95, tile=0.7)
        material("Linen", tex=LINEN, tint=srgb_lin("#f4e6cc"), rough=0.95, tile=0.5)
        material("Photo", img=g["gen_photos"], rough=0.5)
        material("Frame_Dark", color=srgb_lin("#3a2414"), rough=0.4)
        material("Frame_Gilt", img=GEN["gen_brushed"], tint=srgb_lin("#c8a040"), rough=0.35, metal=0.8, tile=0.2)
        material("Flower_Pink", color=srgb_lin("#ff4aa8"), rough=0.6)
        material("Leaf_Green", color=srgb_lin("#2aa040"), rough=0.6)
        material("Glow_Emit", color=(1.0, 0.95, 0.85), rough=0.9, emit=((1.0, 0.9, 0.75), 3.0))
        material("Lamp_Emit_Green", color=(1.0, 0.93, 0.78), rough=0.9, emit=(WARM, 4.0))
    elif s == "rdwe_hallway":
        g = {k: mk_image(k, f()) for k, f in (("gen_plaid", lambda: gen_plaid(61)), ("gen_diamond", lambda: gen_diamond_carpet(62)),
                                               ("gen_moss", lambda: gen_pixels(63)))}
        material("Wall_Plaid", img=g["gen_plaid"], rough=0.8, tile=1.4)
        material("Wall_Amber", tex=PLASTER, tint=srgb_lin("#ffb850"), rough=0.9, tile=2.0)
        material("Carpet_Tan", img=g["gen_diamond"], rough=1.0, tile=1.6)
        material("Ceiling_Hall", tex=PLASTER, tint=srgb_lin("#f4eee2"), rough=0.95, tile=2.6)
        material("Moss_Stone", img=g["gen_moss"], rough=0.95, tile=1.6)
        material("Moss_Block", img=g["gen_moss"], tint=srgb_lin("#c8ffb0"), rough=0.95, tile=0.8)
        material("Trim_Hall", tex=PAINT, tint=srgb_lin("#6a6258"), rough=0.6, tile=1.0)
        material("Fixture", color=srgb_lin("#ecebe4"), rough=0.5)
        material("Amber_Emit", color=(1.0, 0.7, 0.35), rough=0.6, emit=((1.0, 0.62, 0.25), 5.0))
    elif s in ("rdwe_teal", "rdwe_teal2"):
        d = s == "rdwe_teal2"
        g = {k: mk_image(k, f()) for k, f in (("gen_fleck", lambda: gen_fleck(112 if d else 111, d)),)}
        material("Wall_Teal", tex=PLASTER, tint=srgb_lin("#12a8ac" if d else "#22d0cc"), rough=0.85, tile=2.4)
        material("Carpet_Fleck", img=g["gen_fleck"], rough=1.0, tile=0.9)
        material("Ceiling_Teal", tex=PLASTER, tint=srgb_lin("#f4ead4"), rough=0.95, tile=2.6)
        material("Trim_Teal", tex=PAINT, tint=srgb_lin("#fff2dc"), rough=0.5, tile=1.0)
        material("Leather", tex=LINEN, tint=srgb_lin("#c8662a" if d else "#ff8a24"), rough=0.4, tile=0.7)
        material("Leather_Seam", color=srgb_lin("#7a3a12" if d else "#b8501a"), rough=0.5)
        material("Sofa_Foot", color=srgb_lin("#151210"), rough=0.5)
        material("Terracotta", color=srgb_lin("#d87040"), rough=0.85)
        material("Stone_Planter", tex=CONCRETE, tint=srgb_lin("#b8b0a0"), rough=0.9, tile=1.0)
        material("Soil", color=srgb_lin("#2a1f14"), rough=1.0)
        material("Plant_Leaf", color=srgb_lin("#3fae3a" if d else "#4ccf40"), rough=0.6)
        material("Dome", color=srgb_lin("#fff6ea"), rough=0.5)
        if d:
            material("Grid_Emit", img=mk_image("gen_grid", gen_grid()), color=(0, 0, 0), rough=0.9, emit=((0.25, 1.0, 0.4), 2.5))
            gg = MATS["Grid_Emit"].node_tree
            tn = next(n for n in gg.nodes if n.type == "TEX_IMAGE")
            bs = next(n for n in gg.nodes if n.type == "BSDF_PRINCIPLED")
            gg.links.new(tn.outputs["Color"], bs.inputs["Emission Color"])
            material("Paper_Back", color=srgb_lin("#efe4cc"), rough=0.95)
            material("Paper_Teal", tex=PLASTER, tint=srgb_lin("#12a8ac"), rough=0.85, tile=2.4)
        else:
            material("Window_Lit", img=mk_image("gen_sky_small", gen_sky(171, 512, 256)), rough=0.9, emit=((1.0, 0.95, 0.85), 1.6))
            wl = MATS["Window_Lit"].node_tree
            tn = next(n for n in wl.nodes if n.type == "TEX_IMAGE")
            bs = next(n for n in wl.nodes if n.type == "BSDF_PRINCIPLED")
            wl.links.new(tn.outputs["Color"], bs.inputs["Emission Color"])
            material("Sill", tex=PAINT, tint=srgb_lin("#fff2dc"), rough=0.5, tile=1.0)
    elif s == "rdwe_flooded":
        g = {k: mk_image(k, f()) for k, f in (("gen_tile_wall", lambda: gen_tiles(141, 8, "#f8f8f4", "#eeeee6", "#c8c8c0", 0.018)),
                                               ("gen_tile_floor", lambda: gen_tiles(142, 3, "#f0e8d4", "#e6dcc4", "#c8bea8", 0.012)),
                                               ("gen_sky", lambda: gen_sky(143)))}
        material("Tile_Wall", img=g["gen_tile_wall"], rough=0.25, tile=1.2)
        material("Tile_Floor", img=g["gen_tile_floor"], rough=0.2, tile=1.2)
        material("Ceiling_White", tex=PLASTER, tint=srgb_lin("#f8f6f0"), rough=0.95, tile=2.4)
        material("Sky_Paint", img=g["gen_sky"], rough=0.8, tile=1.0)
        material("Rail_Steel", img=GEN["gen_brushed"], tint=srgb_lin("#d0d4da"), rough=0.25, metal=1.0, tile=0.3)
        material("Frame_Wood", tex=WOOD, tint=srgb_lin("#ffb070"), rough=0.5, tile=0.6)
        material("Frame_Back", color=srgb_lin("#f3f1ea"), rough=0.9)
        material("Cardboard", tex=PLYWOOD, tint=srgb_lin("#e8b880"), rough=0.45, tile=0.8)
        material("Cardboard_Light", tex=PLYWOOD, tint=srgb_lin("#ffd8a0"), rough=0.5, tile=0.8)
        material("Wet_Paper", color=srgb_lin("#dcd6c6"), rough=0.35)
        material("Photo_Wet", img=mk_image("gen_photos", gen_photos(144, 512, 2)), rough=0.3)
        material("Grate_Steel", color=srgb_lin("#4a4d52"), rough=0.45, metal=0.9)
        material("Tactile", color=srgb_lin("#ffd820"), rough=0.6)
        material("Panel_Rim", color=srgb_lin("#dcdcd6"), rough=0.5)
        material("Drip_Blue", color=srgb_lin("#2e6cff"), rough=0.15)
        material("Water", color=srgb_lin("#bfe4f0"), rough=0.02, alpha=0.28)
    elif s == "rdwe_trampoline":
        g = {k: mk_image(k, f()) for k, f in (("gen_pad", lambda: gen_quilt(201, "#ff9a3a", "#c85a10")),
                                               ("gen_pad_pale", lambda: gen_quilt(202, "#f4e6a0", "#c8b870")),
                                               ("gen_weave", lambda: gen_weave(203)), ("gen_concrete", lambda: gen_concrete(204)))}
        material("Pad_Wall", img=g["gen_pad"], rough=0.6, tile=1.6)
        material("Concrete_Apron", img=g["gen_concrete"], rough=0.9, tile=3.0)
        material("Truss_Deck", color=srgb_lin("#1e1a16"), rough=0.9)
        material("Pad_Orange", img=g["gen_pad"], rough=0.6, tile=1.0)
        material("Pad_Pale", img=g["gen_pad_pale"], rough=0.6, tile=1.0)
        material("Bed_Weave", img=g["gen_weave"], rough=0.75, tile=0.5)
        material("Edge_Yellow", color=srgb_lin("#ffe23a"), rough=0.6)
        material("Truss_Steel", color=srgb_lin("#2e2a26"), rough=0.6, metal=0.5)
        material("Column_Band", color=srgb_lin("#ffe88c"), rough=0.6)
        material("Wall_Mesh", img=g["gen_weave"], tint=srgb_lin("#3a3a48"), rough=0.75, tile=0.5)
        material("Vent_Grille", color=srgb_lin("#3a3a3e"), rough=0.5, metal=0.6)
    elif s == "rdwe_grocery":
        g = {k: mk_image(k, f()) for k, f in (("gen_vinyl", lambda: gen_speckle(221, "#f0e4d0", "#c8f0e4")),)}
        material("Vinyl_Floor", img=g["gen_vinyl"], rough=0.25, tile=2.4)
        material("Store_Wall", tex=PAINT, tint=srgb_lin("#f0e2c8"), rough=0.85, tile=2.0)
        material("Acoustic", tex=ACOUSTIC, tint=srgb_lin("#fff4e4"), rough=0.9, tile=1.2)
        material("Gondola", img=GEN["gen_brushed"], tint=srgb_lin("#c8c8c2"), rough=0.45, metal=0.4, tile=0.6)
        material("Gondola_Back", tex=PAINT, tint=srgb_lin("#a8a8a2"), rough=0.6, tile=1.0)
        material("Kick", color=srgb_lin("#55544f"), rough=0.7)
        material("Endcap_Pink", tex=PAINT, tint=srgb_lin("#ff5ab0"), rough=0.45, tile=1.0)
        material("Endcap_Lime", tex=PAINT, tint=srgb_lin("#9ef03a"), rough=0.45, tile=1.0)
        material("Endcap_Cyan", tex=PAINT, tint=srgb_lin("#30d8f0"), rough=0.45, tile=1.0)
        material("Post_Cream", tex=PAINT, tint=srgb_lin("#fff0d8"), rough=0.8, tile=1.0)
        material("Cart_Red", color=srgb_lin("#e8202a"), rough=0.4)
        material("Wheel", color=srgb_lin("#151515"), rough=0.8)
        material("Tin", img=GEN["gen_brushed"], tint=srgb_lin("#d0d0ca"), rough=0.3, metal=0.75, tile=0.2)
        material("Tin_Band", color=srgb_lin("#e8dcc0"), rough=0.8)
        material("Tin_Red", color=srgb_lin("#e8202a"), rough=0.4)
        material("Card_Flat", tex=PLYWOOD, tint=srgb_lin("#b08a5a"), rough=0.9, tile=0.8)
        material("Tape_Yellow", color=srgb_lin("#ffd820"), rough=0.6)
        material("Strip_Housing", color=srgb_lin("#d5d2c8"), rough=0.5)
        material("Alu", img=GEN["gen_brushed"], tint=srgb_lin("#c0c4c8"), rough=0.35, metal=0.8, tile=0.4)
    if s == "rdwe_repeating_room":
        g = {k: mk_image(k, f()) for k, f in (("gen_doors", lambda: gen_door_paper(301)), ("gen_peach", lambda: gen_shag(302, "#e88a6a", "#ffb08a", "#ffd8b8")))}
        material("Wall_Doors", img=g["gen_doors"], rough=0.8, tile=1.2)
        material("Leaf_Lilac", img=g["gen_doors"], rough=0.8, tile=1.2)
        material("Baffle_Paper", img=g["gen_doors"], rough=0.8, tile=1.2)
        material("Carpet_Peach", img=g["gen_peach"], rough=1.0, tile=1.0)
        material("Ceiling_Repeat", tex=PLASTER, tint=srgb_lin("#fff0f4"), rough=0.95, tile=2.4)
        material("Trim_Repeat", tex=PAINT, tint=srgb_lin("#fff6ff"), rough=0.5, tile=1.0)
        material("Leaf_White", tex=PAINT, tint=srgb_lin("#ffffff"), rough=0.35, tile=1.0)
        material("Velvet_Pink", tex=LINEN, tint=srgb_lin("#ff5aa8"), rough=0.9, tile=0.5)
        material("Wood_Table", tex=WOOD, tint=srgb_lin("#ffb878"), rough=0.4, tile=0.8)
        material("Shade_Paper", color=srgb_lin("#fff0e0"), rough=0.9)
        material("Picture_Room", img=mk_image("gen_room_pic", gen_room_picture(303)), rough=0.5)
        material("Frame_Gilt", img=GEN["gen_brushed"], tint=srgb_lin("#c8a040"), rough=0.35, metal=0.8, tile=0.2)
    if s == "rdwe_finale":
        g = {k: mk_image(k, f()) for k, f in (("gen_vinyl_f", lambda: gen_speckle(401, "#dcd6e8", "#c8e8f0")),)}
        material("Wall_Navy", tex=PAINT, tint=srgb_lin("#2a3a9a"), rough=0.7, tile=2.0)
        material("Vinyl_Finale", img=g["gen_vinyl_f"], rough=0.25, tile=2.4)
        material("Acoustic_Finale", tex=ACOUSTIC, tint=srgb_lin("#f4f0ff"), rough=0.9, tile=1.2)
        material("Stripe_Pink", tex=PAINT, tint=srgb_lin("#ff3aa0"), rough=0.5, tile=1.0)
        material("Kick_Finale", color=srgb_lin("#1a1e40"), rough=0.6)
        material("Strip_Housing", color=srgb_lin("#d5d2c8"), rough=0.5)
        material("Cubicle_Panel", tex=LINEN, tint=srgb_lin("#7a8ab8"), rough=0.95, tile=0.6)
        material("Cubicle_Frame", img=GEN["gen_brushed"], tint=srgb_lin("#c0c4c8"), rough=0.35, metal=0.8, tile=0.4)
        material("Desk_Top", tex=WOOD, tint=srgb_lin("#ffcf98"), rough=0.4, tile=0.8)
        material("Monitor", color=srgb_lin("#1c1c20"), rough=0.4)
        material("Screen_Emit", color=(0.2, 0.9, 1.0), rough=0.4, emit=((0.25, 0.85, 1.0), 3.0))
        material("Quilt_Pink", tex=LINEN, tint=srgb_lin("#ff7ab8"), rough=0.95, tile=0.6)
        material("Linen", tex=LINEN, tint=srgb_lin("#f4e6cc"), rough=0.95, tile=0.5)
        material("Wood_House", tex=WOOD, tint=srgb_lin("#e09060"), rough=0.45, tile=0.8)
        material("Maple", tex=WOOD, tint=srgb_lin("#ffb060"), rough=0.4, tile=0.9)
        material("Leather", tex=LINEN, tint=srgb_lin("#ff8a24"), rough=0.4, tile=0.7)
        material("Rack_Body", img=GEN["gen_brushed"], tint=srgb_lin("#3a3e48"), rough=0.4, metal=0.6, tile=0.5)
        material("Rack_Grille", color=srgb_lin("#101216"), rough=0.6)
        material("Server_Emit", color=(0.1, 1.0, 0.3), rough=0.5, emit=((0.15, 1.0, 0.35), 4.0))
        material("Gondola", img=GEN["gen_brushed"], tint=srgb_lin("#c8c8c2"), rough=0.45, metal=0.4, tile=0.6)
        material("Basin", tex=CONCRETE, tint=srgb_lin("#8af0ff"), rough=0.4, tile=1.0)
        material("Water", color=srgb_lin("#bfe4f0"), rough=0.02, alpha=0.4)
        material("Cam_White", color=srgb_lin("#e8e8e4"), rough=0.4)
        material("Cam_Black", color=srgb_lin("#121214"), rough=0.3)
        material("Vent_Grille", color=srgb_lin("#3a3a3e"), rough=0.5, metal=0.6)
        material("Alu", img=GEN["gen_brushed"], tint=srgb_lin("#c0c4c8"), rough=0.35, metal=0.8, tile=0.4)
        material("Leaf_Blue", tex=PAINT, tint=srgb_lin("#2a7aff"), rough=0.4, tile=1.0)
        material("Emergency_Emit_Green", color=(0.1, 1.0, 0.3), rough=0.5, emit=((0.1, 1.0, 0.25), 6.0))
        material("Rug_Finale", tex=LINEN, tint=srgb_lin("#30d8c0"), rough=1.0, tile=0.6)
        material("Till", color=srgb_lin("#e8e4da"), rough=0.5)
    if s in ("rdwe_trampoline",):
        material("Marble_Door", tex=MARBLE, tint=srgb_lin("#f4f0ea"), rough=0.2, tile=1.0)
    if s == "rdwe_teal":
        material("Leaf_Stone", tex=CONCRETE, tint=srgb_lin("#8a948a"), rough=0.9, tile=1.0)
    if s == "rdwe_hallway":
        material("Leaf_Baize", tex=LINEN, tint=srgb_lin("#1e8a3a"), rough=0.95, tile=0.5)
    if s == "rdwe_dining":
        material("Leaf_White", tex=PAINT, tint=srgb_lin("#ffffff"), rough=0.35, tile=1.0)
        material("Leaf_Cream", img=GEN["gen_swirl"], rough=0.8, tile=1.6)
        material("Leaf_Black", color=srgb_lin("#0c0c0e"), rough=0.5)
    if s == "rdwe_flooded":
        material("Leaf_Canvas", img=mk_image("gen_sky_canvas", gen_sky(145, 512, 512)), rough=0.8, tile=1.0)
    if s == "rdwe_grocery":
        material("Bronze", img=GEN["gen_brushed"], tint=srgb_lin("#b07838"), rough=0.35, metal=0.9, tile=0.3)
        material("Laurel", img=GEN["gen_brushed"], tint=srgb_lin("#d8b040"), rough=0.3, metal=0.9, tile=0.2)
        material("Flap_Rubber", color=srgb_lin("#121214"), rough=0.55)
        material("Steel_Door", img=GEN["gen_brushed"], tint=srgb_lin("#9a9c98"), rough=0.45, metal=0.4, tile=0.6)


# shell box material (greybox name) -> this room's material
SHELL = {"rdwe_dining": {"cream": "Wall_Cream", "shag": "Shag_Green", "ceiling": "Ceiling_Dining", "stair_green": "Stair_Wall", "void": "Void"},
         "rdwe_hallway": {"plaid": "Wall_Plaid", "carpet_tan": "Carpet_Tan", "ceiling": "Ceiling_Hall", "moss": "Moss_Stone", "void": "Void"},
         "rdwe_teal": {"teal": "Wall_Teal", "fleck": "Carpet_Fleck", "teal_cream": "Ceiling_Teal", "void": "Void"},
         "rdwe_teal2": {"teal": "Wall_Teal", "fleck": "Carpet_Fleck", "teal_cream": "Ceiling_Teal", "void": "Void"},
         "rdwe_flooded": {"tile": "Tile_Wall", "white": "Ceiling_White", "void": "Void"},
         "rdwe_trampoline": {"pad": "Pad_Wall", "concrete": "Concrete_Apron", "truss": "Truss_Deck", "void": "Void"},
         "rdwe_grocery": {"wall": "Store_Wall", "vinyl": "Vinyl_Floor", "ceiling": "Acoustic", "void": "Void"},
         "rdwe_repeating_room": {"lilac": "Wall_Doors", "peach": "Carpet_Peach", "ceiling": "Ceiling_Repeat", "void": "Void"},
         "rdwe_finale": {"navy": "Wall_Navy", "vinyl": "Vinyl_Finale", "ceiling": "Acoustic_Finale", "void": "Void"}}


def shell_material(b, ax, side, centre):
    """The material of one shell piece: by the box's greybox colour, with the faces that differ (the dining stairs' treads and risers, the
    hallway's amber vestibule, the flooded floor) picked by where they are."""
    s, n = SCENE, b["name"]
    if "ceiling" in b["tags"] or n.endswith("_Ceiling") or n == "Well_Ceiling":
        return {"rdwe_dining": "Ceiling_Dining", "rdwe_hallway": "Ceiling_Hall", "rdwe_teal": "Ceiling_Teal", "rdwe_teal2": "Ceiling_Teal",
                "rdwe_flooded": "Ceiling_White", "rdwe_trampoline": "Truss_Deck", "rdwe_grocery": "Acoustic",
                "rdwe_repeating_room": "Ceiling_Repeat", "rdwe_finale": "Acoustic_Finale"}[s]
    if s == "rdwe_dining" and (n.startswith("Step_") or (n == "Landing" and ax == 1 and side > 0)):
        return "Stair_Carpet"
    if s == "rdwe_hallway" and b["mat"] == "plaid" and centre[0] > 40.0:
        return "Wall_Amber"
    if s == "rdwe_flooded" and n == "Flooded_Floor":
        return "Tile_Floor"
    return SHELL[s][b["mat"]]


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
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                          matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())


def sphere(bm, p, r, seg=12, sy=1.0):
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(4, seg // 2), radius=r, matrix=Matrix.Translation(B(p)) @ Matrix.Diagonal((1, 1, sy, 1)))


def torus(bm, p, R, r, axis=(0, 1, 0), seg=16, rseg=6):
    """A ring of radius R, tube r, round the game axis `axis`, centred on p."""
    tmp = bmesh.new()
    vs = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        for j in range(rseg):
            b = 2 * math.pi * j / rseg
            vs.append(tmp.verts.new(((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b))))
    for i in range(seg):
        for j in range(rseg):
            a0, a1 = i * rseg + j, i * rseg + (j + 1) % rseg
            b0, b1 = ((i + 1) % seg) * rseg + j, ((i + 1) % seg) * rseg + (j + 1) % rseg
            tmp.faces.new((vs[a0], vs[b0], vs[b1], vs[a1]))
    q = B(axis).to_track_quat("Z", "Y")
    bmesh.ops.transform(tmp, matrix=Matrix.Translation(B(p)) @ q.to_matrix().to_4x4(), verts=tmp.verts)
    me = bpy.data.meshes.new("t")
    tmp.to_mesh(me)
    tmp.free()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)


def prism(bm, pts2, a0, a1, axis="x"):
    """A prism: the polygon pts2 [(u, y)] (u = game z for axis 'x', game x for axis 'z') extruded along `axis` from a0 to a1."""
    def P(u, y, a):
        return B((a, y, u)) if axis == "x" else B((u, y, a))
    v0 = [bm.verts.new(P(u, y, a0)) for u, y in pts2]
    v1 = [bm.verts.new(P(u, y, a1)) for u, y in pts2]
    n = len(pts2)
    bm.faces.new(v0[::-1])
    bm.faces.new(v1)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((v0[i], v0[j], v1[j], v1[i]))


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


ART = PROPS = ARCH = SKIN = DOORS = LAYOUT = LIGHTS = ALTL = None


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


def boxes(name, mat, rects, coll=None, tile=None):
    """One object of axis boxes: rects = [(min, max)] in game coordinates."""
    def b(bm):
        for mn, mx in rects:
            cube(bm, mn, mx)
    return part(name, mat, b, coll, tile)


def text_mesh(body, size, extrude):
    cu = bpy.data.curves.new("txt", "FONT")
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    cu.resolution_u = 3
    ob = bpy.data.objects.new("txt", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return me


def add_text(bm, body, size, depth, origin, right, up, normal):
    me = text_mesh(body, size, depth / 2)
    R, U, N = B(right), B(up), B(normal)
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


# ---------------------------------------------------------------- the model, its boxes and its doors
_MODEL = {}


def model():
    if SCENE not in _MODEL:
        _MODEL[SCENE] = GB.build(SCENE)
    return _MODEL[SCENE]


def gbx(name):
    return next(b for b in model().boxes if b["name"] == name)


def is_furniture(b):
    return b["name"].startswith(FURNITURE[SCENE]) if FURNITURE[SCENE] else False


def shell_boxes():
    return [b for b in model().boxes if b.get("col") and b.get("art", True) and not b.get("zone") and not is_furniture(b)]


def door_geom(d):
    """A door's opening: (hinge (x, y, z), run (x, z) along the leaf, inward (x, z) into the room, width, height)."""
    p = d["props"]
    th = math.radians(p["closed_yaw_deg"])
    run = (math.cos(th), -math.sin(th))
    sw = math.radians(p["closed_yaw_deg"] + (90 if p["swing_deg"] > 0 else -90))
    inward = (round(math.cos(sw), 6), round(-math.sin(sw), 6))
    return d["hinge"], run, inward, p["width"], p["height"]


# ---------------------------------------------------------------- layout objects (exported to the JSON, never to the GLB)
def col_box(name, mn, mx, coll=None):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    cube(bm, mn, mx)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    (coll or LAYOUT).objects.link(ob)
    ob.hide_render = True
    ob.display_type = "WIRE"
    return ob


def layout_from_model(M):
    for b in M.boxes:
        if b.get("zone"):
            col_box(b["name"], b["min"], b["max"])
            continue
        if b["col"]:
            col_box("COL_" + b["name"], b["min"], b["max"])
            if is_furniture(b):
                continue
            bm = bmesh.new()
            cube(bm, b["min"], b["max"])
            finish(b["name"], bm, "Standin_Grey", ARCH, tile=1.0)
    for e in M.empties + M.cams:
        ob = bpy.data.objects.new(e["name"], None)
        ob.location = B(e["pos"])
        if e["face"]:
            ob.rotation_euler = (0, 0, math.atan2(e["face"][0], e["face"][1]))
        for k, v in e["props"].items():
            ob[k] = v
        ob.empty_display_size = 0.3
        LAYOUT.objects.link(ob)
    for ob in ARCH.objects:
        ob.hide_render = True


# ---------------------------------------------------------------- the shell as seen
# the air of each room (game min, max): a shell face is drawn only where the air in front of it is in here (or in a door's opening) and in no
# other shell box. The dining room's stairwell, the hallway's well and the door openings are air too.
AIR = {"rdwe_repeating_room": [((-6.0, 0.0, -6.0), (6.0, 3.2, 6.0)), ((5.9, 0.0, -3.8), (8.2, 2.6, -2.2))],
       "rdwe_finale": [((-24.0, 0.0, -22.0), (24.0, 4.5, 22.0))],
       "rdwe_dining": [((-8.0, 0.0, -10.0), (8.0, 4.2, 10.0)), ((-1.3, 0.0, -10.0 - 12 * 0.36 - 1.6), (0.3, 5.6, -10.0))],
       "rdwe_hallway": [((-4.0, 0.0, -1.6), (45.0, 4.6, 1.6)), ((40.0, -0.8, -0.8), (45.0, 1.2, 0.8))],
       "rdwe_teal": [((-7.0, 0.0, -9.0), (7.0, 4.0, 9.0))],
       "rdwe_teal2": [((-4.0, 0.0, -11.0), (4.0, 5.5, 11.0))],
       "rdwe_flooded": [((0.0, 0.0, -2.5), (50.0, 4.0, 2.5))],
       "rdwe_trampoline": [((-15.0, 0.0, -25.0), (15.0, 9.0, 25.0))],
       "rdwe_grocery": [((-25.0, 0.0, -25.0), (25.0, 5.0, 25.0))]}


def air_boxes():
    out = [{"min": list(a), "max": list(b)} for a, b in AIR[SCENE]]
    for d in model().doors:
        (hx, hy, hz), run, inw, w, h = door_geom(d)
        p0 = (hx - run[0] * 0.03 - inw[0] * 0.6, hz - run[1] * 0.03 - inw[1] * 0.6)
        p1 = (hx + run[0] * (w + 0.03) + inw[0] * 0.6, hz + run[1] * (w + 0.03) + inw[1] * 0.6)
        out.append({"min": [min(p0[0], p1[0]), hy, min(p0[1], p1[1])], "max": [max(p0[0], p1[0]), hy + h + 0.03, max(p0[1], p1[1])]})
    return out


def _inside(p, b, e=1e-4):
    return all(b["min"][i] + e < p[i] < b["max"][i] - e for i in range(3))


def build_skin():
    shells = shell_boxes()
    inner = [b for b in shells if not b["name"].startswith("Beyond_")]
    lo = [min(b["min"][i] for b in inner) for i in range(3)]
    hi = [max(b["max"][i] for b in inner) for i in range(3)]
    ctr = [(lo[i] + hi[i]) / 2 for i in range(3)]
    air = air_boxes()
    by = {}
    for b in shells:
        beyond = b["name"].startswith("Beyond_")
        if beyond:
            thin = min(range(3), key=lambda i: b["max"][i] - b["min"][i])
        for ax in range(3):
            for side in (-1, 1):
                if beyond and not (ax == thin and side == (1 if ctr[ax] > (b["min"][ax] + b["max"][ax]) / 2 else -1)):
                    continue
                o = [a for a in range(3) if a != ax]
                c0, c1 = o
                plane = b["max"][ax] if side > 0 else b["min"][ax]
                n0 = max(1, math.ceil((b["max"][c0] - b["min"][c0]) / 4.0))
                n1 = max(1, math.ceil((b["max"][c1] - b["min"][c1]) / 4.0))
                for i in range(n0):
                    for j in range(n1):
                        u0 = b["min"][c0] + (b["max"][c0] - b["min"][c0]) * i / n0
                        u1 = b["min"][c0] + (b["max"][c0] - b["min"][c0]) * (i + 1) / n0
                        v0 = b["min"][c1] + (b["max"][c1] - b["min"][c1]) * j / n1
                        v1 = b["min"][c1] + (b["max"][c1] - b["min"][c1]) * (j + 1) / n1
                        if u1 - u0 < 1e-4 or v1 - v0 < 1e-4:
                            continue
                        keep = beyond
                        if not beyond:
                            for fu, fv in ((0.5, 0.5), (0.1, 0.1), (0.9, 0.1), (0.1, 0.9), (0.9, 0.9)):
                                f = [0.0, 0.0, 0.0]
                                f[ax] = plane + side * 0.01
                                f[c0] = u0 + (u1 - u0) * fu
                                f[c1] = v0 + (v1 - v0) * fv
                                if any(_inside(f, a, 0.0) for a in air) and not any(_inside(f, c) for c in shells if c is not b):
                                    keep = True
                                    break
                        if not keep:
                            continue
                        cen = [0.0, 0.0, 0.0]
                        cen[ax], cen[c0], cen[c1] = plane, (u0 + u1) / 2, (v0 + v1) / 2
                        mname = shell_material(b, ax, side, cen)
                        by.setdefault(mname, []).append((ax, side, plane, c0, u0, u1, c1, v0, v1))
    for mname, quads in sorted(by.items()):
        skin_mesh(mname, quads)
    print("SKIN", {k: len(v) for k, v in sorted(by.items())})


def skin_mesh(mname, quads):
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    tile = TILES.get(mname, 1.0)
    for ax, side, plane, c0, u0, u1, c1, v0, v1 in quads:
        pts = []
        for uu, vv in ((u0, v0), (u1, v0), (u1, v1), (u0, v1)):
            p = [0.0, 0.0, 0.0]
            p[ax], p[c0], p[c1] = plane, uu, vv
            pts.append(p)
        f = bm.faces.new([bm.verts.new(B(p)) for p in pts])
        f.normal_update()
        want = [0, 0, 0]
        want[ax] = side
        if f.normal.dot(B(want)) < 0:
            f.normal_flip()
        for lp in f.loops:
            gx, gy, gz = lp.vert.co.x, lp.vert.co.z, -lp.vert.co.y
            u, v = (gz, gy) if ax == 0 else (gx, gz) if ax == 1 else (gx, gy)
            lp[uvl].uv = (u / tile, v / tile)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    me = bpy.data.meshes.new(mname)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mname])
    ob = bpy.data.objects.new(mname, me)
    SKIN.objects.link(ob)
    return ob


# ---------------------------------------------------------------- door leaves: one mesh per door, made from its look
STORY = {   # the story doors' own words -> (form, finish material, handle, extras)
    "the front door": ("six-panel", "Leaf_White", "brass knob", ("knocker",)),
    "a door that was not there before": ("flush", "Leaf_Cream", "no handle", ()),
    "the dark door at the top": ("flush", "Leaf_Black", "no handle", ()),
    "the landing door: green baize": ("flush", "Leaf_Baize", "push plate", ("studs_edge",)),
    "a low door at the foot of the well": ("ledged and braced", "Leaf_Stone", "ring pull", ("iron",)),
    "the square doorway": ("slab", "Void", "no handle", ()),
    "the tall arch": (None, None, None, ()),
    "a door under peeled wallpaper": ("flush", "Paper_Teal", "no handle", ("grid_peel",)),
    "the back of the arch": ("round-topped", "Leaf_TealPaint", "no handle", ()),
    "an empty picture frame": ("frame", "Leaf_Canvas", "no handle", ()),
    "the red door": ("panelled", "Emergency_Emit", "chrome lever", ()),
    "a tall marble door": ("panelled", "Marble_Door", "brass knob", ("meander",)),
    "a padded vent door": ("quilted", "Pad_Orange", "no handle", ("vent_slots",)),
    "the entrance: a pair of glass": ("sliding_pair", "Alu", "no handle", ("chain",)),
    "the fire exit": ("flush", "Steel_Door", "push bar", ()),
    "a bronze door": ("six-panel", "Bronze", "laurel", ()),
    "a stockroom door": ("flaps", "Flap_Rubber", "no handle", ("staff_only",)),
    "the north door: plain white flush": ("flush", "Leaf_White", "chrome lever", ("number:12",)),
    "the south door: the north door again": ("flush", "Leaf_White", "chrome lever", ("number:13",)),
    "the door from one angle": ("flush", "Leaf_Lilac", "no handle", ()),
    "the grocery's glass doors, from the other side": ("sliding_pair", "Alu", "no handle", ()),
    "a pair of tall blue doors": ("double", "Leaf_Blue", "push bar", ()),
}


def parse_look(look):
    for k, v in STORY.items():
        if look.startswith(k):
            return v
    # "<form> <finish> door, <handle>"
    head, handle = look.split(", ", 1)
    head = head[:-len(" door")]
    form = next(f for f in sorted(GB.FORMS, key=len, reverse=True) if head.startswith(f))
    fin = head[len(form) + 1:]
    return form, leaf_mat(fin), handle, ()


def leaf_mesh(name, look, width, height):
    """Local +X runs from the hinge along the leaf, z is up, the leaf is 5 cm thick on y -0.025..0.025 (the room side is -Y, as built: the
    page swings it round its origin). The form, the finish and the handle come from the door's `look`."""
    form, fmat, handle, extras = parse_look(look)
    pieces = {}
    th = 0.025
    w, h = width - 0.006, height - 0.008

    def bx(x0, x1, y0, y1, z0, z1, mat):
        bm = pieces.setdefault(mat, bmesh.new())
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)) @ Matrix.Diagonal(
            (max(x1 - x0, 1e-4), max(y1 - y0, 1e-4), max(z1 - z0, 1e-4), 1)))

    def cylx(p, r, depth, mat, axis="y", seg=16):
        bm = pieces.setdefault(mat, bmesh.new())
        rot = Matrix.Rotation(math.pi / 2, 4, "X") if axis == "y" else Matrix.Identity(4)
        bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r, depth=depth, matrix=Matrix.Translation(p) @ rot)

    def sph(p, r, mat):
        bm = pieces.setdefault(mat, bmesh.new())
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=6, radius=r, matrix=Matrix.Translation(p))

    def ring(p, R, r, mat, axis="y"):
        bm = pieces.setdefault(mat, bmesh.new())
        tmp = bmesh.new()
        seg, rs = 16, 6
        vs = []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            for j in range(rs):
                b = 2 * math.pi * j / rs
                vs.append(tmp.verts.new(((R + r * math.cos(b)) * math.cos(a), r * math.sin(b), (R + r * math.cos(b)) * math.sin(a))))
        for i in range(seg):
            for j in range(rs):
                tmp.faces.new((vs[i * rs + j], vs[((i + 1) % seg) * rs + j], vs[((i + 1) % seg) * rs + (j + 1) % rs], vs[i * rs + (j + 1) % rs]))
        if axis == "x":
            bmesh.ops.rotate(tmp, verts=tmp.verts, matrix=Matrix.Rotation(math.pi / 2, 3, "Z"))
        bmesh.ops.translate(tmp, verts=tmp.verts, vec=Vector(p))
        me = bpy.data.meshes.new("r")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)

    def panels(rects, mat, depth=0.006, both=True):
        for yy, sg in ((-th, -1), (th, 1)) if both else ((-th, -1),):
            for x0, x1, z0, z1 in rects:
                a, b = sorted((yy, yy + sg * depth))
                q = 0.035
                bx(x0, x1, a, b, z0, z0 + q, mat)
                bx(x0, x1, a, b, z1 - q, z1, mat)
                bx(x0, x0 + q, a, b, z0 + q, z1 - q, mat)
                bx(x1 - q, x1, a, b, z0 + q, z1 - q, mat)
                a2, b2 = sorted((yy, yy + sg * depth * 0.6))
                bx(x0 + 0.07, x1 - 0.07, a2, b2, z0 + 0.07, z1 - 0.07, mat)

    if form is None:
        return None
    if form == "slab":                                   # the square doorway: a slab of black flush with the wall, nothing else
        bx(0.0, width, -0.004, 0.02, 0.0, height, "Void")
    elif form == "round-topped":
        r = w / 2
        n = 12
        bm = pieces.setdefault(fmat, bmesh.new())
        prof = [(0.003, 0.006), (w, 0.006)] + [(w / 2 + r * math.cos(math.pi * i / n), h - r + r * math.sin(math.pi * i / n)) for i in range(n + 1)]
        v0 = [bm.verts.new((x, -th, z)) for x, z in prof]
        v1 = [bm.verts.new((x, th, z)) for x, z in prof]
        bm.faces.new(v0[::-1])
        bm.faces.new(v1)
        for i in range(len(prof)):
            j = (i + 1) % len(prof)
            bm.faces.new((v0[i], v0[j], v1[j], v1[i]))
        panels([(0.12, w - 0.12, 0.2, h * 0.55)], fmat, 0.005)
    elif form == "frame":                                # an empty picture frame, door-sized: a deep gilt frame, its canvas the leaf
        bx(0.003, w, -0.01, th, 0.006, h, fmat)
        for x0, x1, z0, z1 in ((0.003, 0.1, 0.006, h), (w - 0.1, w, 0.006, h), (0.003, w, 0.006, 0.1), (0.003, w, h - 0.1, h)):
            bx(x0, x1, -0.07, th, z0, z1, "Frame_Wood")
        for x0, x1, z0, z1 in ((0.09, 0.12, 0.09, h - 0.09), (w - 0.12, w - 0.09, 0.09, h - 0.09), (0.09, w - 0.09, 0.09, 0.12), (0.09, w - 0.09, h - 0.12, h - 0.09)):
            bx(x0, x1, -0.05, -0.0, z0, z1, "Frame_Back")
    elif form == "sliding_pair":                         # two glass leaves in aluminium frames, meeting in the middle, chained
        for k in range(2):
            x0, x1 = (0.003, w / 2 - 0.005) if k == 0 else (w / 2 + 0.005, w)
            bx(x0, x1, -0.02, 0.02, 0.006, 0.12, "Alu")
            bx(x0, x1, -0.02, 0.02, h - 0.08, h, "Alu")
            bx(x0, x0 + 0.06, -0.02, 0.02, 0.12, h - 0.08, "Alu")
            bx(x1 - 0.06, x1, -0.02, 0.02, 0.12, h - 0.08, "Alu")
            bx(x0 + 0.06, x1 - 0.06, -0.006, 0.006, 0.12, h - 0.08, "Leaf_Glass")
            bx(x1 - 0.2 if k == 0 else x0 + 0.05, x1 - 0.05 if k == 0 else x0 + 0.2, -0.05, -0.02, 0.95, 1.05, "Alu")
    elif form == "flaps":                                # rubber strip curtain over a black steel frame
        bx(0.003, w, -0.03, 0.03, h - 0.12, h, "Iron")
        n = 7
        for i in range(n):
            x0 = 0.01 + i * (w - 0.02) / n
            bx(x0 + 0.004, x0 + (w - 0.02) / n - 0.004, -0.006 + (i % 2) * 0.012, 0.0 + (i % 2) * 0.012, 0.03, h - 0.12, fmat)
    else:
        bx(0.003, w, -th, th, 0.006, h, fmat)
        if form == "panelled":
            cx = w / 2
            panels([(0.1, cx - 0.04, 0.2, h * 0.45), (cx + 0.04, w - 0.1, 0.2, h * 0.45), (0.1, cx - 0.04, h * 0.5, h - 0.12),
                    (cx + 0.04, w - 0.1, h * 0.5, h - 0.12)], fmat)
        elif form == "six-panel":
            cx = w / 2
            rows = [(0.18, h * 0.36), (h * 0.4, h * 0.6), (h * 0.64, h - 0.12)]
            panels([(x0, x1, z0, z1) for z0, z1 in rows for x0, x1 in ((0.1, cx - 0.04), (cx + 0.04, w - 0.1))], fmat)
        elif form == "louvred":
            q = 0.07
            for x0, x1, z0, z1 in ((0.003, q, 0.006, h), (w - q, w, 0.006, h), (0.003, w, 0.006, 0.2), (0.003, w, h - 0.12, h), (0.003, w, h * 0.5 - 0.04, h * 0.5 + 0.04)):
                bx(x0, x1, -th - 0.006, th + 0.006, z0, z1, fmat)
            z = 0.24
            while z < h - 0.16:
                if abs(z - h * 0.5) > 0.06:
                    bx(q, w - q, -th - 0.004, -th + 0.004, z, z + 0.03, "Leaf_Glass")
                z += 0.065
        elif form == "half-glazed":
            panels([(0.1, w - 0.1, 0.2, h * 0.45)], fmat)
            bx(0.12, w - 0.12, -th - 0.002, th + 0.002, h * 0.52, h - 0.14, "Leaf_Glass")
            for x in (w / 3, 2 * w / 3):
                bx(x - 0.012, x + 0.012, -th - 0.008, th + 0.008, h * 0.52, h - 0.14, fmat)
        elif form == "ledged and braced":
            for i in range(1, 6):
                x = i * w / 6
                bx(x - 0.004, x + 0.004, -th - 0.002, -th + 0.002, 0.006, h, "Leaf_Glass")
            for z in (0.25, h / 2, h - 0.3):
                bx(0.05, w - 0.05, -th - 0.025, -th, z - 0.07, z + 0.07, fmat)
            bm = pieces.setdefault(fmat, bmesh.new())
            for za, zb in ((0.32, h / 2 - 0.08), (h / 2 + 0.08, h - 0.37)):
                L = math.hypot(w - 0.2, zb - za)
                bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, -th - 0.0125, (za + zb) / 2)) @ Matrix.Rotation(
                    math.atan2(zb - za, w - 0.2), 4, "Y").inverted() @ Matrix.Diagonal((L, 0.025, 0.1, 1)))
        elif form == "studded":
            for i in range(4):
                for j in range(7):
                    sph((0.15 + i * (w - 0.3) / 3, -th, 0.25 + j * (h - 0.5) / 6), 0.018, "Brass" if "brass" not in handle else "Chrome")
            panels([(0.08, w - 0.08, 0.1, h - 0.1)], fmat, 0.004, both=False)
        elif form == "quilted":
            for i in range(4):
                for j in range(7):
                    sph((0.13 + i * (w - 0.26) / 3, -th - 0.004, 0.22 + j * (h - 0.42) / 6), 0.02, fmat)
            for i in range(3):
                for j in range(6):
                    bx(0.13 + (i + 0.5) * (w - 0.26) / 3 - 0.09, 0.13 + (i + 0.5) * (w - 0.26) / 3 + 0.09, -th - 0.03, -th, 0.22 + (j + 0.5) * (h - 0.42) / 6 - 0.13,
                       0.22 + (j + 0.5) * (h - 0.42) / 6 + 0.13, fmat)
        elif form == "mirror-faced":
            bx(0.07, w - 0.07, -th - 0.004, -th, 0.12, h - 0.12, "Mirror")
            bx(0.07, w - 0.07, th, th + 0.004, 0.12, h - 0.12, "Mirror")
        elif form == "porthole":
            cylx((w / 2, 0.0, h * 0.68), 0.2, 2 * th + 0.01, "Leaf_Glass", seg=24)
            ring((w / 2, -th, h * 0.68), 0.21, 0.025, "Chrome")
            ring((w / 2, th, h * 0.68), 0.21, 0.025, "Chrome")
        elif form == "stable (split)":
            bx(0.003, w, -th - 0.01, th + 0.01, h * 0.48, h * 0.5, fmat)
            panels([(0.1, w - 0.1, 0.2, h * 0.44), (0.1, w - 0.1, h * 0.54, h - 0.12)], fmat)
        elif form == "flush":
            for x0, x1, z0, z1 in ((0.003, w, 0.006, 0.02), (0.003, w, h - 0.014, h)):
                bx(x0, x1, -th - 0.003, th + 0.003, z0, z1, fmat)
        elif form == "double":                           # a pair: two panelled halves meeting in the middle
            bx(w / 2 - 0.006, w / 2 + 0.006, -th - 0.003, th + 0.003, 0.006, h, "Rubber_Black")
            for x0, x1 in ((0.003, w / 2 - 0.006), (w / 2 + 0.006, w)):
                panels([(x0 + 0.1, x1 - 0.1, 0.25, h * 0.48), (x0 + 0.1, x1 - 0.1, h * 0.55, h - 0.15)], fmat)
    # handles
    hx = w - 0.08
    hz = 0.98 if height > 1.2 else height * 0.45
    for yy, sg in ((-th, -1), (th, 1)):
        if handle == "brass knob" or handle == "glass knob":
            m = "Brass" if handle == "brass knob" else "Glass_Knob"
            cylx((hx, yy + sg * 0.004, hz), 0.032, 0.008, "Brass")
            cylx((hx, yy + sg * 0.03, hz), 0.009, 0.05, "Brass")
            sph((hx, yy + sg * 0.065, hz), 0.03, m)
        elif handle == "chrome lever":
            bx(hx - 0.022, hx + 0.022, *sorted((yy, yy + sg * 0.01)), hz - 0.09, hz + 0.09, "Chrome")
            bx(hx - 0.012, hx + 0.012, *sorted((yy, yy + sg * 0.055)), hz - 0.012, hz + 0.012, "Chrome")
            bx(hx - 0.14, hx + 0.012, *sorted((yy + sg * 0.045, yy + sg * 0.065)), hz - 0.012, hz + 0.012, "Chrome")
        elif handle == "push plate":
            bx(hx - 0.05, hx + 0.05, *sorted((yy, yy + sg * 0.004)), hz + 0.1, hz + 0.4, "Brass")
        elif handle == "ring pull":
            cylx((hx, yy + sg * 0.004, hz), 0.035, 0.008, "Iron")
            ring((hx, yy + sg * 0.02, hz - 0.06), 0.06, 0.008, "Iron", axis="x")
        elif handle == "push bar":
            bx(0.12, w - 0.06, *sorted((yy + sg * 0.05, yy + sg * 0.08)), hz - 0.03, hz + 0.03, "Chrome")
            for x in (0.14, w - 0.1):
                bx(x - 0.03, x + 0.03, *sorted((yy, yy + sg * 0.06)), hz - 0.06, hz + 0.06, "Chrome")
        elif handle == "laurel":
            ring((hx - 0.04, yy + sg * 0.03, hz + 0.05), 0.1, 0.012, "Laurel", axis="x")
            for i in range(10):
                a = 2 * math.pi * i / 10
                sph((hx - 0.04 + 0.1 * math.cos(a), yy + sg * 0.035, hz + 0.05 + 0.1 * math.sin(a)), 0.022, "Laurel")
    for ex in extras:
        if ex == "knocker":
            ring((w / 2, -th - 0.02, h * 0.66), 0.07, 0.012, "Brass", axis="x")
            cylx((w / 2, -th - 0.005, h * 0.72), 0.03, 0.012, "Brass")
        elif ex == "studs_edge":
            for z in np.linspace(0.08, h - 0.08, 18):
                for x in (0.05, w - 0.05):
                    sph((x, -th, float(z)), 0.012, "Brass")
        elif ex == "iron":
            for z in (0.35, h - 0.35):
                bx(0.02, w * 0.75, -th - 0.03, -th - 0.02, z - 0.03, z + 0.03, "Iron")
        elif ex == "grid_peel":
            for x0, x1, z0, z1 in ((0.15, 0.6, 1.2, 1.7), (0.4, 0.75, 0.4, 0.75)):
                bx(x0, x1, -th - 0.002, -th, z0, z1, "Grid_Emit")
                bx(x1 - 0.06, x1, -th - 0.05, -th - 0.002, z0, z1, "Paper_Back")
        elif ex == "meander":
            for zc in (0.12, h - 0.12):
                for i in range(int((w - 0.1) / 0.08)):
                    x = 0.05 + i * 0.08
                    bx(x, x + 0.06, -th - 0.008, -th, zc - 0.03, zc - 0.018, "Brass")
                    bx(x + 0.048, x + 0.06, -th - 0.008, -th, zc - 0.03, zc + 0.03, "Brass")
                    bx(x + 0.012, x + 0.06, -th - 0.008, -th, zc + 0.018, zc + 0.03, "Brass")
        elif ex.startswith("number:"):
            num = ex.split(":")[1]
            for yy, sg in ((-th, -1), (th, 1)):
                bx(w / 2 - 0.09, w / 2 + 0.09, *sorted((yy, yy + sg * 0.004)), 1.52, 1.66, "Brass")
                tm = text_mesh(num, 0.09, 0.002)
                tb = bmesh.new()
                tb.from_mesh(tm)
                bpy.data.meshes.remove(tm)
                rot = Matrix(((1, 0, 0, w / 2), (0, 0, -1, yy + sg * 0.006), (0, 1, 0, 1.59), (0, 0, 0, 1))) if sg < 0 else \
                    Matrix(((-1, 0, 0, w / 2), (0, 0, 1, yy + sg * 0.006), (0, 1, 0, 1.59), (0, 0, 0, 1)))
                bmesh.ops.transform(tb, matrix=rot, verts=tb.verts)
                m2 = bpy.data.meshes.new("n")
                tb.to_mesh(m2)
                tb.free()
                pieces.setdefault("Rubber_Black", bmesh.new()).from_mesh(m2)
                bpy.data.meshes.remove(m2)
        elif ex == "vent_slots":
            for i in range(5):
                bx(0.15, w - 0.15, -th - 0.03, -th - 0.028, 1.6 + i * 0.07, 1.63 + i * 0.07, "Rubber_Black")
        elif ex == "chain":
            for i in range(9):
                ring((w / 2, -0.06, 1.0 + (i - 4) * 0.055), 0.025, 0.006, "Chrome", axis="x" if i % 2 else "y")
            bx(w / 2 - 0.04, w / 2 + 0.04, -0.09, -0.05, 0.7, 0.78, "Brass")
        elif ex == "staff_only":
            bm = pieces.setdefault("Plastic_White", bmesh.new())
            bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, -0.035, 1.75)) @ Matrix.Diagonal((0.5, 0.004, 0.14, 1)))
            tm = text_mesh("STAFF ONLY", 0.075, 0.002)
            tb = bmesh.new()
            tb.from_mesh(tm)
            bpy.data.meshes.remove(tm)
            bmesh.ops.transform(tb, matrix=Matrix(((1, 0, 0, w / 2), (0, 0, -1, -0.0395), (0, 1, 0, 1.75), (0, 0, 0, 1))), verts=tb.verts)
            m2 = bpy.data.meshes.new("s")
            tb.to_mesh(m2)
            tb.free()
            pieces.setdefault("Rubber_Black", bmesh.new()).from_mesh(m2)
            bpy.data.meshes.remove(m2)
    me = bpy.data.meshes.new(name)
    out = bmesh.new()
    out.loops.layers.uv.new("UVMap")
    mats = []
    for mat, pm in pieces.items():
        mats.append(mat)
        for f in pm.faces:
            f.material_index = len(mats) - 1
        bmesh.ops.recalc_face_normals(pm, faces=pm.faces)
        pm.loops.layers.uv.new("UVMap")
        t = TILES.get(mat, 1.0)
        uvl = pm.loops.layers.uv["UVMap"]
        for f in pm.faces:
            ax = max(range(3), key=lambda i: abs(f.normal[i]))
            for lp in f.loops:
                p = lp.vert.co
                u, v = (p.y, p.z) if ax == 0 else (p.x, p.z) if ax == 1 else (p.x, p.y)
                if mat == "Leaf_Canvas":
                    u, v = p.x / w, p.z / h
                    t = 1.0
                lp[uvl].uv = (u / t, v / t)
        m2 = bpy.data.meshes.new("p")
        pm.to_mesh(m2)
        pm.free()
        out.from_mesh(m2)
        bpy.data.meshes.remove(m2)
    out.to_mesh(me)
    out.free()
    for mat in mats:
        me.materials.append(MATS[mat])
    return me


def build_leaves(M):
    for d in M.doors:
        p = d["props"]
        me = leaf_mesh(d["name"], p["look"], p["width"], p["height"])
        if me is None:                                       # the arch: no leaf; the layout keeps its record as an empty
            ob = bpy.data.objects.new(d["name"], None)
            ob.empty_display_type = "ARROWS"
            ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
            LAYOUT.objects.link(ob)
        else:
            ob = bpy.data.objects.new(d["name"], me)
            ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
            DOORS.objects.link(ob)
        for k, v in p.items():
            ob[k] = v


def casings(mat, skip=(), width=0.1, proud=0.025):
    """An architrave round every door opening, on the room side (the story's frameless doors skipped)."""
    for d in model().doors:
        did = d["name"][len("DoorLeaf_"):]
        if did in skip:
            continue
        (hx, hy, hz), run, inw, w, h = door_geom(d)
        W, Ht = w + 0.04, h + 0.04
        a0 = (hx - run[0] * 0.02, hz - run[1] * 0.02)
        rects = []
        for t0, t1, y0, y1 in ((-width, 0.0, hy, hy + Ht + width), (W, W + width, hy, hy + Ht + width), (-width, W + width, hy + Ht, hy + Ht + width)):
            pa = (a0[0] + run[0] * t0, a0[1] + run[1] * t0)
            pb = (a0[0] + run[0] * t1, a0[1] + run[1] * t1)
            pc = (pa[0] + inw[0] * proud, pa[1] + inw[1] * proud)
            xs, zs = sorted((pa[0], pb[0], pc[0])), sorted((pa[1], pb[1], pc[1]))
            rects.append(((xs[0], y0, zs[0]), (xs[-1], y1, zs[-1])))
        boxes(f"decor_Casing_{did}", mat, rects)


def skirting(mat, runs, y, h=0.14, d=0.02, cuts_extra=()):
    """Skirting boards: runs = [(axis, plane, inward sign, a0, a1)], cut round the door holes (and cuts_extra: (axis, plane, a0, a1))."""
    holes = []
    for dd in model().doors:
        (hx, hy, hz), run, inw, w, _ = door_geom(dd)
        holes.append((hx, hz, run, w))
    rects = []
    for axis, plane, sg, a0, a1 in runs:
        cuts = []
        for hx, hz, run, w in holes:
            if axis == "x" and abs(hz - plane) < 0.05:
                xa, xb = sorted((hx, hx + run[0] * w))
                cuts.append((xa - 0.12, xb + 0.12))
            if axis == "z" and abs(hx - plane) < 0.05:
                za, zb = sorted((hz, hz + run[1] * w))
                cuts.append((za - 0.12, zb + 0.12))
        cuts += [(c0, c1) for ax2, pl2, c0, c1 in cuts_extra if ax2 == axis and abs(pl2 - plane) < 0.05]
        segs, a = [], a0
        for c0, c1 in sorted(cuts):
            if c0 > a:
                segs.append((a, min(c0, a1)))
            a = max(a, c1)
        if a < a1:
            segs.append((a, a1))
        for s0, s1 in segs:
            if s1 - s0 < 0.05:
                continue
            q0, q1 = sorted((plane, plane + sg * d))
            rects.append(((s0, y, q0), (s1, y + h, q1)) if axis == "x" else ((q0, y, s0), (q1, y + h, s1)))
    boxes("decor_Skirting", mat, rects)


def room_runs(x0, x1, z0, z1):
    return [("x", z0, 1, x0, x1), ("x", z1, -1, x0, x1), ("z", x0, 1, z0, z1), ("z", x1, -1, z0, z1)]


# ---------------------------------------------------------------- lights
def light(name, kind, pos, power, color=WARM, size=0.1, aim=None, spot=None, coll=None, size_y=None):
    d = bpy.data.lights.new(name, kind)
    d.energy, d.color = power, color
    if kind == "AREA":
        d.shape = "RECTANGLE" if size_y else "DISK"
        d.size = size
        if size_y:
            d.size_y = size_y
    elif kind != "SUN":
        d.shadow_soft_size = size
    if spot:
        d.spot_size, d.spot_blend = math.radians(spot), 0.6
    ob = bpy.data.objects.new(name, d)
    ob.location = B(pos)
    if aim is not None:
        ob.rotation_euler = (B(aim) - B(pos)).to_track_quat("-Z", "Y").to_euler()
    (coll or LIGHTS).objects.link(ob)
    return ob


def down_light(name, pos, power, color=WARM, size=0.5, size_y=None, coll=None):
    return light(name, "AREA", pos, power, color, size, aim=(pos[0], pos[1] - 1, pos[2]), coll=coll, size_y=size_y)


# ================================================================ the rooms
def dress_dining():
    M = model()
    X, Z, H = 8.0, 10.0, 4.2
    casings("Trim_Cream", skip=("loop",))
    skirting("Trim_Cream", room_runs(-X, X, -Z, Z), 0.0, h=0.18, cuts_extra=(("x", -Z, -1.35, 0.35),))
    boxes("decor_Cornice", "Trim_Cream", [((-X, H - 0.16, -Z), (X, H, -Z + 0.06)), ((-X, H - 0.16, Z - 0.06), (X, H, Z)),
                                          ((-X, H - 0.16, -Z), (-X + 0.06, H, Z)), ((X - 0.06, H - 0.16, -Z), (X, H, Z))])
    # the giant round table: a 4.4 m maple top on a turned pedestal and four splayed feet; laid for four guests who never came
    t = gbx("Table")

    def table(bm):
        cyl(bm, (0, 1.17, 0), (0, 1.25, 0), 2.2, seg=64)
        cyl(bm, (0, 1.06, 0), (0, 1.17, 0), 2.0, 2.06, seg=48)
        cyl(bm, (0, 0.12, 0), (0, 1.06, 0), 0.38, 0.3, seg=24)
        cyl(bm, (0, 0.45, 0), (0, 0.7, 0), 0.5, 0.5, seg=24)
        cube(bm, (-2.2, 0.0, -0.06), (2.2, 0.12, 0.06))                 # the cross of splayed feet, out to the top's edge
        cube(bm, (-0.06, 0.0, -2.2), (0.06, 0.12, 2.2))
        for ex, ez in ((2.1, 0.0), (-2.1, 0.0), (0.0, 2.1), (0.0, -2.1)):
            cube(bm, (ex - 0.1, 0.0, ez - 0.1), (ex + 0.1, 0.16, ez + 0.1))
    ob = part("Table", "Maple", table, smooth=False)
    assert abs(t["max"][1] - 1.25) < 1e-6
    # four arrow-back chairs to match (each over its seat and back colliders)
    for nm in ("N", "S", "W", "E"):
        s, bk = gbx(f"Chair_{nm}"), gbx(f"Chair_{nm}_Back")
        cx, cz = (s["min"][0] + s["max"][0]) / 2, (s["min"][2] + s["max"][2]) / 2
        bx0, bx1, bz0, bz1 = bk["min"][0], bk["max"][0], bk["min"][2], bk["max"][2]

        def chair(bm, s=s, bk=bk):
            x0, x1, z0, z1 = s["min"][0], s["max"][0], s["min"][2], s["max"][2]
            cube(bm, (x0, 0.66, z0), (x1, 0.75, z1))
            for lx, lz in ((x0 + 0.08, z0 + 0.08), (x1 - 0.08, z0 + 0.08), (x0 + 0.08, z1 - 0.08), (x1 - 0.08, z1 - 0.08)):
                cyl(bm, (lx, 0.0, lz), (lx, 0.66, lz), 0.05, 0.04, seg=10)
            for lx0, lz0, lx1, lz1 in ((x0 + 0.08, z0 + 0.08, x1 - 0.08, z0 + 0.08), (x0 + 0.08, z1 - 0.08, x1 - 0.08, z1 - 0.08)):
                cyl(bm, (lx0, 0.25, lz0), (lx1, 0.25, lz1), 0.025, seg=8)
            b0, b1, c0, c1 = bk["min"][0], bk["max"][0], bk["min"][2], bk["max"][2]
            along_x = (b1 - b0) > (c1 - c0)
            mx_, mz_ = (b0 + b1) / 2, (c0 + c1) / 2
            for k in (0, 1):
                if along_x:
                    px = b0 + 0.06 if k == 0 else b1 - 0.06
                    cyl(bm, (px, 0.66, mz_), (px, 2.4, mz_), 0.055, 0.045, seg=10)
                else:
                    pz = c0 + 0.06 if k == 0 else c1 - 0.06
                    cyl(bm, (mx_, 0.66, pz), (mx_, 2.4, pz), 0.055, 0.045, seg=10)
            if along_x:
                cube(bm, (b0, 2.18, mz_ - 0.05), (b1, 2.4, mz_ + 0.05))
                cube(bm, (b0 + 0.05, 0.95, mz_ - 0.035), (b1 - 0.05, 1.03, mz_ + 0.035))
                for i in range(5):
                    xx = b0 + 0.22 + i * (b1 - b0 - 0.44) / 4
                    cyl(bm, (xx, 1.03, mz_), (xx, 2.18, mz_), 0.022, seg=8)
                    sphere(bm, (xx, 1.7, mz_), 0.045, seg=8, sy=1.8)
            else:
                cube(bm, (mx_ - 0.05, 2.18, c0), (mx_ + 0.05, 2.4, c1))
                cube(bm, (mx_ - 0.035, 0.95, c0 + 0.05), (mx_ + 0.035, 1.03, c1 - 0.05))
                for i in range(5):
                    zz = c0 + 0.22 + i * (c1 - c0 - 0.44) / 4
                    cyl(bm, (mx_, 1.03, zz), (mx_, 2.18, zz), 0.022, seg=8)
                    sphere(bm, (mx_, 1.7, zz), 0.045, seg=8, sy=1.8)
        part(f"Chair_{nm}", "Maple_Dark", chair)
        # a cushion on each seat
        boxes(f"decor_Cushion_{nm}", "Linen", [((cx - 0.48, 0.75, cz - 0.48), (cx + 0.48, 0.82, cz + 0.48))])
    # the table, laid: four places (plate, cup and saucer the size of a hat), a white cloth runner, a vase of too-pink flowers
    def china(bm):
        for a in range(4):
            ang = a * math.pi / 2
            px, pz = math.sin(ang) * 1.45, math.cos(ang) * 1.45
            cyl(bm, (px, 1.25, pz), (px, 1.272, pz), 0.42, 0.46, seg=32)
            cyl(bm, (px * 0.72 + 0.3, 1.25, pz * 0.72 + 0.3), (px * 0.72 + 0.3, 1.262, pz * 0.72 + 0.3), 0.2, seg=24)
            cyl(bm, (px * 0.72 + 0.3, 1.262, pz * 0.72 + 0.3), (px * 0.72 + 0.3, 1.46, pz * 0.72 + 0.3), 0.1, 0.16, seg=24)
        cyl(bm, (0, 1.25, 0), (0, 1.75, 0), 0.16, 0.22, seg=24)
    part("decor_China_Table", "China", china)
    boxes("decor_Runner", "Linen", [((-1.9, 1.25, -0.3), (1.9, 1.258, 0.3))])

    def rug(bm):
        cyl(bm, (0, 0.0, 0), (0, 0.012, 0), 3.6, seg=64)
        uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
        for f in bm.faces:
            for lp in f.loops:
                lp[uvl].uv = (lp.vert.co.x / 7.2 + 0.5, lp.vert.co.y / 7.2 + 0.5)
    bm = bmesh.new()
    rug(bm)
    finish("decor_Rug", bm, "Rug_Rings", PROPS, keep_uv=True)

    def flowers(bm):
        rng = np.random.default_rng(3)
        for i in range(9):
            a, r = rng.random() * 6.28, 0.05 + 0.15 * rng.random()
            sphere(bm, (math.cos(a) * r, 1.95 + 0.25 * rng.random(), math.sin(a) * r), 0.09 + 0.05 * rng.random(), seg=10)
    part("decor_Flowers", "Flower_Pink", flowers)
    part("decor_Stems", "Leaf_Green", lambda bm: [cyl(bm, (0, 1.7, 0), (math.cos(a) * 0.15, 2.0, math.sin(a) * 0.15), 0.012, seg=6) for a in np.linspace(0, 6, 7)])
    # the sideboard and its green ceramic lamp (west wall)
    sb = gbx("Sideboard")
    x0, x1, z0, z1 = sb["min"][0], sb["max"][0], sb["min"][2], sb["max"][2]

    def sideboard(bm):
        cube(bm, (x0, 0.12, z0), (x1, 1.22, z1))
        cube(bm, (x0, 1.22, z0 - 0.0), (x1, 1.3, z1))
        for lz in (z0 + 0.1, z1 - 0.1):
            cube(bm, (x1 - 0.12, 0.0, lz - 0.05), (x1 - 0.02, 0.12, lz + 0.05))
            cube(bm, (x0 + 0.02, 0.0, lz - 0.05), (x0 + 0.12, 0.12, lz + 0.05))
    part("Sideboard", "Maple", sideboard)

    def fronts(bm):
        n = 4
        for i in range(n):
            za, zb = z0 + 0.08 + i * (z1 - z0 - 0.16) / n, z0 + 0.08 + (i + 1) * (z1 - z0 - 0.16) / n
            cube(bm, (x1, 0.9, za + 0.02), (x1 + 0.02, 1.16, zb - 0.02))
            cube(bm, (x1, 0.2, za + 0.02), (x1 + 0.02, 0.84, zb - 0.02))
    part("decor_Sideboard_Fronts", "Maple_Dark", fronts)
    part("decor_Sideboard_Knobs", "Brass", lambda bm: [sphere(bm, (x1 + 0.04, zz, z0 + 0.08 + (i + 0.5) * (z1 - z0 - 0.16) / 4), 0.025, seg=8)
                                                       for i in range(4) for zz in (1.03, 0.55)])
    lx, lz = (x0 + x1) / 2, -1.0
    part("decor_Lamp_Base", "Ceramic_Green", lambda bm: (sphere(bm, (lx, 1.52, lz), 0.2, seg=20, sy=1.1), cyl(bm, (lx, 1.3, lz), (lx, 1.36, lz), 0.14, seg=16),
                                                         cyl(bm, (lx, 1.7, lz), (lx, 1.78, lz), 0.03, seg=8)))
    part("decor_Lamp_Shade", "Lamp_Emit_Green", lambda bm: cyl(bm, (lx, 1.76, lz), (lx, 2.08, lz), 0.3, 0.18, seg=24, cap=False))
    # a short stack of plates on the sideboard
    part("decor_Plates_Sideboard", "China", lambda bm: [cyl(bm, (lx, 1.3 + i * 0.022, 0.6 + (i % 3) * 0.006), (lx, 1.318 + i * 0.022, 0.6 + (i % 3) * 0.006),
                                                            0.2, seg=24) for i in range(9)])
    # the photo wall: six frames on the north wall, west of the stairs (the photo spots face them)
    uvp = []
    for k in range(6):
        b = gbx(f"decor_Photo_{k + 1}")
        fx0, fx1, fy0, fy1 = b["min"][0], b["max"][0], b["min"][1], b["max"][1]
        pad = 0.06
        boxes(f"decor_PhotoFrame_{k + 1}", "Frame_Gilt" if k % 2 else "Frame_Dark",
              [((fx0 - pad, fy0 - pad, -Z), (fx1 + pad, fy0, -Z + 0.05)), ((fx0 - pad, fy1, -Z), (fx1 + pad, fy1 + pad, -Z + 0.05)),
               ((fx0 - pad, fy0, -Z), (fx0, fy1, -Z + 0.05)), ((fx1, fy0, -Z), (fx1 + pad, fy1, -Z + 0.05))])
        uvp.append((k, fx0, fx1, fy0, fy1))
    photo_quads("decor_Photos", "Photo", [(k, x0_, x1_, y0_, y1_, -Z + 0.02) for k, x0_, x1_, y0_, y1_ in uvp], cells=4)
    # the good china: four crooked towers against the east wall, between the curtains and the front wall
    for k in range(4):
        b = gbx(f"China_Tower_{k + 1}")
        cx, cz = (b["min"][0] + b["max"][0]) / 2, (b["min"][2] + b["max"][2]) / 2
        top = b["max"][1]
        rng = np.random.default_rng(40 + k)

        def tower(bm, cx=cx, cz=cz, top=top, rng=rng):
            y, i = 0.0, 0
            lean = rng.random() * 6.28
            while y < top - 1e-3:
                hgt = min(0.22, top - y)
                off = 0.035 * math.sin(i * 0.7 + lean) * (y / top)
                ox, oz = cx + off * math.cos(lean), cz + off * math.sin(lean)
                r = 0.36 - 0.03 * (i % 3)
                cyl(bm, (ox, y, oz), (ox, y + hgt, oz), r - 0.04, r, seg=28)
                y += hgt
                i += 1
            cube(bm, (cx - 0.4, 0.0, cz - 0.4), (cx + 0.4, 0.002, cz + 0.4))
        part(f"China_Tower_{k + 1}", "China", tower)

        def rims(bm, cx=cx, cz=cz, top=top):
            y = 0.2
            while y < top - 0.05:
                cyl(bm, (cx, y, cz), (cx, y + 0.012, cz), 0.365, seg=28)
                y += 0.22
        part(f"decor_China_Rims_{k + 1}", "China_Rim", rims)
    # folded tablecloths on the floor by the towers
    boxes("decor_Tablecloths", "Linen", [((X - 1.0, 0.0, 3.3), (X - 0.3, 0.22, 4.1)), ((X - 1.0, 0.0, 8.7), (X - 0.4, 0.14, 9.5))])
    # sheer curtains on the east wall, on a rod (over a window that is not there)
    c = gbx("decor_Curtains")

    def curtains(bm):
        z0, z1 = c["min"][2], c["max"][2]
        n = 22
        vs = []
        for i in range(n + 1):
            z = z0 + (z1 - z0) * i / n
            x = X - 0.08 - 0.06 * (i % 2)
            vs.append((x, z))
        for i in range(n):
            (xa, za), (xb, zb) = vs[i], vs[i + 1]
            f = bm.faces.new([bm.verts.new(B(p)) for p in ((xa, 0.1, za), (xb, 0.1, zb), (xb, H - 0.3, zb), (xa, H - 0.3, za))])
    part("decor_Curtains", "Sheer", curtains, recalc=False)
    part("decor_Curtain_Rod", "Brass", lambda bm: cyl(bm, (X - 0.12, H - 0.25, c["min"][2] - 0.3), (X - 0.12, H - 0.25, c["max"][2] + 0.3), 0.02, seg=10))
    # the stairwell: stringers, a handrail on two brackets, the hair of light round the dark door, a light switch by the opening
    SX0, SX1 = -1.3, 0.3
    zt = -Z - 12 * 0.36
    def stringers(bm):
        for x in (SX0, SX1 - 0.05):
            for i in range(12):
                za, zb = -Z - i * 0.36, -Z - (i + 1) * 0.36
                cube(bm, (x, 0.25 * i, zb), (x + 0.05, 0.25 * (i + 1) + 0.12, za))
    part("decor_Stringers", "Maple_Dark", stringers)
    part("decor_Handrail", "Brass", lambda bm: (cyl(bm, (SX1 - 0.07, 0.95, -Z + 0.2), (SX1 - 0.07, 3.95, zt), 0.025, seg=10),
                                                cyl(bm, (SX1, 1.6, -Z - 1.0), (SX1 - 0.07, 1.6, -Z - 1.0), 0.012, seg=6),
                                                cyl(bm, (SX1, 3.4, -Z - 3.4), (SX1 - 0.07, 3.4, -Z - 3.4), 0.012, seg=6)))
    dd = next(d for d in M.doors if d["name"] == "DoorLeaf_stairs")
    (hx, hy, hz), run, inw, w, h = door_geom(dd)
    g = 0.012
    boxes("decor_Door_Glow", "Glow_Emit", [((hx - 0.02, hy, hz - 0.005), (hx - 0.02 + g, hy + h + 0.02, hz + 0.003)),
                                          ((hx + w + 0.02 - g, hy, hz - 0.005), (hx + w + 0.02, hy + h + 0.02, hz + 0.003)),
                                          ((hx - 0.02, hy + h + 0.02 - g, hz - 0.005), (hx + w + 0.02, hy + h + 0.02, hz + 0.003))])
    boxes("decor_Switch", "Trim_Cream", [((SX1 + 0.35, 1.3, -Z), (SX1 + 0.45, 1.42, -Z + 0.015))])
    # the ceiling: two big dome lights, a ceiling rose like a flower that has opened a little too far
    for k, (dx, dz) in enumerate(((0.0, 0.0), (0.0, 6.5))):
        part(f"decor_Dome_{k}", "Lamp_Emit", lambda bm, dx=dx, dz=dz: sphere(bm, (dx, H - 0.02, dz), 0.55, seg=24, sy=0.35))

        def rose(bm, dx=dx, dz=dz):
            for i in range(12):
                a = i * math.pi / 6
                sphere(bm, (dx + math.cos(a) * 0.95, H - 0.03, dz + math.sin(a) * 0.95), 0.32, seg=12, sy=0.12)
        part(f"decor_Rose_{k}", "Trim_Cream", rose)
    # lights: the domes, the green lamp (its own collection: the alt set turns it off), a faint glow at the top of the stairs
    for k, (dx, dz) in enumerate(((0.0, 0.0), (0.0, 6.5))):
        down_light(f"Dome_{k}", (dx, H - 0.3, dz), 900.0, WARM, size=1.2)
    for k, (dx, dz) in enumerate(((-5.0, -6.0), (5.0, -6.0), (-5.0, 6.0), (5.0, 6.0))):
        down_light(f"Fill_{k}", (dx, H - 0.1, dz), 260.0, (1.0, 0.86, 0.72), size=2.0)
    light("Lamp_Green", "POINT", (lx, 1.92, lz), 160.0, (1.0, 0.82, 0.55), size=0.15, coll=ALTL)
    light("Stair_Glow", "POINT", (-0.5, 4.8, zt - 0.6), 60.0, (1.0, 0.9, 0.75), size=0.1)
    light("Stair_Mid", "AREA", (-0.5, 4.9, -Z - 1.6), 90.0, (1.0, 0.86, 0.7), size=0.5, aim=(-0.5, 1.0, -Z - 1.6))


def photo_quads(name, mat, items, cells=4, axis="z", inward=1):
    """Flat pictures on a wall: items = [(k, a0, a1, y0, y1, plane)]; picture k shows cell k of a cells x cells atlas."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    for k, a0, a1, y0, y1, pl in items:
        r_, c_ = divmod(k, cells)
        u0, u1 = c_ / cells, (c_ + 1) / cells
        v1, v0 = 1 - r_ / cells, 1 - (r_ + 1) / cells
        if axis == "z":
            pts = [(a0, y0, pl), (a1, y0, pl), (a1, y1, pl), (a0, y1, pl)]
            nrm = (0, 0, inward)
        else:
            pts = [(pl, y0, a0), (pl, y0, a1), (pl, y1, a1), (pl, y1, a0)]
            nrm = (inward, 0, 0)
        vs = [bm.verts.new(B(p)) for p in pts]
        f = bm.faces.new(vs)
        f.normal_update()
        if f.normal.dot(B(nrm)) < 0:
            f.normal_flip()
        for lp in f.loops:
            i = vs.index(lp.vert)
            lp[uvl].uv = (u0 if i in (0, 3) else u1, v0 if i in (0, 1) else v1)
    return finish(name, bm, mat, PROPS, keep_uv=True)


def dress_hallway():
    W2, H = 1.6, 4.6
    yC = 1.2
    casings("Trim_Hall")
    skirting("Trim_Hall", [("x", -W2, 1, 2.4, 40.0), ("x", W2, -1, 2.4, 40.0)], yC, h=0.16)
    skirting("Trim_Hall", [("x", -W2, 1, -4.0, 0.0), ("x", W2, -1, -4.0, 0.0), ("z", -4.0, 1, -W2, W2)], 0.0, h=0.16)
    boxes("decor_Cornice", "Trim_Hall", [((-4.0, H - 0.1, -W2), (40.0, H, -W2 + 0.04)), ((-4.0, H - 0.1, W2 - 0.04), (40.0, H, W2))])
    # nine twin-tube fluorescents, surface mounted (their tubes are Lamp_Emit: the page flickers them one at a time)
    for k in range(9):
        x = 4.0 + k * 4.0
        boxes(f"decor_Tube_Housing_{k + 1}", "Fixture", [((x - 0.68, H - 0.1, -0.2), (x + 0.68, H, 0.2))])
        part(f"decor_Tube_{k + 1}", "Lamp_Emit", lambda bm, x=x: [cyl(bm, (x - 0.62, H - 0.13, zz), (x + 0.62, H - 0.13, zz), 0.022, seg=10) for zz in (-0.09, 0.09)])
        down_light(f"Tube_{k + 1}", (x, H - 0.18, 0.0), 130.0, COOL, size=1.3, size_y=0.3)
    # the amber vestibule over the well: its ceiling stacked with light bars
    for k in range(7):
        x = 40.2 + k * 0.7
        part(f"decor_Amber_Bar_{k}", "Amber_Emit", lambda bm, x=x: cube(bm, (x, H - 0.22, -1.2), (x + 0.4, H - 0.05, 1.2)))
    down_light("Amber", (42.5, H - 0.3, 0.0), 500.0, (1.0, 0.6, 0.25), size=2.0, size_y=2.0)
    light("Well_Glow", "POINT", (43.5, -0.3, 0.0), 120.0, (0.5, 1.0, 0.4), size=0.4)
    light("Landing", "AREA", (-2.0, H - 0.2, 0.0), 160.0, WARM, size=1.0, aim=(-2.0, 0.0, 0.0))
    # a runner of light switches and a fire-plan frame, and a strip of brass stair nosings up the flight
    part("decor_Nosings", "Brass", lambda bm: [cube(bm, (0.4 * i - 0.03, 0.2 * (i + 1) - 0.01, -W2 + 0.05), (0.4 * i + 0.02, 0.2 * (i + 1) + 0.005, W2 - 0.05))
                                               for i in range(6)])
    # moss creeping up the well's walls: blocks proud of the stone
    rng = np.random.default_rng(66)

    def moss(bm):
        for i in range(40):
            x = 40.0 + rng.random() * 5.0
            z = (W2 - 0.05) * (1 if rng.random() < 0.5 else -1)
            y = -0.8 + rng.random() * 2.6
            s = 0.1 + rng.random() * 0.15
            cube(bm, (x, y, z - (0.03 if z > 0 else 0)), (x + s, y + s, z + (0.03 if z < 0 else 0)))
    part("decor_Moss_Blocks", "Moss_Block", moss)


def dress_teal():
    M = model()
    X, Z, H = 7.0, 9.0, 4.0
    casings("Trim_Teal", skip=("void",))
    skirting("Trim_Teal", room_runs(-X, X, -Z, Z), 0.0, h=0.12)
    # the orange angular sofa: a chamfered shell (an elongated octagon in side view), three seat cushions, a low back, black feet
    def shell(bm):
        z0 = -Z
        prof = [(z0, 0.05), (z0, 2.2), (z0 + 0.25, 2.3), (z0 + 0.6, 2.3), (z0 + 0.6, 1.05), (z0 + 2.0, 1.05), (z0 + 2.2, 0.9), (z0 + 2.2, 0.3), (z0 + 2.0, 0.05)]
        prism(bm, prof, -5.6, -5.0, "x")
        prism(bm, prof, -0.6, 0.0, "x")
        prism(bm, [(z0, 0.05), (z0, 2.2), (z0 + 0.25, 2.3), (z0 + 0.6, 2.3), (z0 + 0.6, 0.05)], -5.0, -0.6, "x")
        prism(bm, [(z0 + 0.6, 0.05), (z0 + 0.6, 0.62), (z0 + 2.0, 0.62), (z0 + 2.2, 0.5), (z0 + 2.2, 0.3), (z0 + 2.0, 0.05)], -5.0, -0.6, "x")
        cube(bm, (-5.6, 1.05, -Z + 0.6), (-5.0, 1.6, -Z + 2.0))
        cube(bm, (-0.6, 1.05, -Z + 0.6), (0.0, 1.6, -Z + 2.0))
    part("Sofa_Shell", "Leather", shell)
    for i in range(3):
        xa = -5.0 + i * 4.4 / 3
        part(f"decor_Sofa_Cushion_{i}", "Leather", lambda bm, xa=xa: cube(bm, (xa + 0.02, 0.62, -Z + 0.62), (xa + 4.4 / 3 - 0.02, 1.05, -Z + 2.18)))
        part(f"decor_Sofa_Back_{i}", "Leather", lambda bm, xa=xa: cube(bm, (xa + 0.02, 1.05, -Z + 0.6), (xa + 4.4 / 3 - 0.02, 2.0, -Z + 1.0)))
    part("decor_Sofa_Seams", "Leather_Seam", lambda bm: [cube(bm, (-5.0 + i * 4.4 / 3 - 0.02, 0.62, -Z + 2.18), (-5.0 + i * 4.4 / 3 + 0.02, 1.05, -Z + 2.2))
                                                          for i in range(1, 3)])
    part("decor_Sofa_Feet", "Sofa_Foot", lambda bm: [cube(bm, (fx - 0.06, 0.0, fz - 0.06), (fx + 0.06, 0.12, fz + 0.06))
                                                     for fx in (-5.45, -0.15) for fz in (-Z + 0.2, -Z + 2.0)])
    # the blocky little plant: a stone planter and pixel leaves (cubes), in the corner right of the doorway
    p = gbx("Plant")
    px0, px1, pz0, pz1 = p["min"][0], p["max"][0], p["min"][2], p["max"][2]
    part("Plant_Pot", "Stone_Planter", lambda bm: cube(bm, (px0, 0.0, pz0), (px1, 0.6, pz1)))
    rng = np.random.default_rng(77)

    def leaves(bm):
        cube(bm, (px0, 0.6, pz0), (px0 + 0.3, 0.9, pz0 + 0.3))
        cube(bm, (px1 - 0.3, 1.5, pz1 - 0.3), (px1, 1.8, pz1))
        for i in range(20):
            s = 0.18 + 0.12 * rng.random()
            x = px0 + rng.random() * (px1 - px0 - s)
            z = pz0 + rng.random() * (pz1 - pz0 - s)
            y = 0.6 + rng.random() * (1.8 - 0.6 - s)
            cube(bm, (x, y, z), (x + s, y + s, z + s))
    part("Plant_Leaves", "Plant_Leaf", leaves)
    part("decor_Soil", "Soil", lambda bm: cube(bm, (px0 + 0.06, 0.6, pz0 + 0.06), (px1 - 0.06, 0.61, pz1 - 0.06)))
    # the fake window on the west wall: a recess frame, the painted sun that never moves (Window_Lit), a cream sill
    fw = gbx("decor_Fake_Window")
    y0, y1, z0, z1 = fw["min"][1], fw["max"][1], fw["min"][2], fw["max"][2]
    photo_quads("decor_Window_Sky", "Window_Lit", [(0, z0, z1, y0, y1, -X + 0.01)], cells=1, axis="x", inward=1)
    boxes("decor_Window_Frame", "Sill", [((-X, y0 - 0.1, z0 - 0.1), (-X + 0.08, y0, z1 + 0.1)), ((-X, y1, z0 - 0.1), (-X + 0.08, y1 + 0.1, z1 + 0.1)),
                                         ((-X, y0, z0 - 0.1), (-X + 0.08, y1, z0)), ((-X, y0, z1), (-X + 0.08, y1, z1 + 0.1)),
                                         ((-X, y0 - 0.1, z0 - 0.15), (-X + 0.22, y0 - 0.04, z1 + 0.15)), ((-X, y0, -0.025), (-X + 0.05, y1, 0.025)),
                                         ((-X, (y0 + y1) / 2 - 0.025, z0), (-X + 0.05, (y0 + y1) / 2 + 0.025, z1))])
    # flush dome light
    part("decor_Dome", "Lamp_Emit", lambda bm: sphere(bm, (0.0, H - 0.01, 0.0), 0.45, seg=24, sy=0.25))
    part("decor_Dome_Rim", "Dome", lambda bm: cyl(bm, (0.0, H - 0.03, 0.0), (0.0, H, 0.0), 0.5, seg=24))
    down_light("Dome", (0.0, H - 0.2, 0.0), 700.0, WARM, size=1.0)
    for k, (dx, dz) in enumerate(((-4.0, -5.0), (4.0, -5.0), (-4.0, 5.0), (4.0, 5.0))):
        down_light(f"Fill_{k}", (dx, H - 0.1, dz), 160.0, (1.0, 0.9, 0.78), size=2.5)
    light("Window_Sun", "AREA", (-X + 0.3, 2.4, 0.0), 260.0, (1.0, 0.86, 0.6), size=1.6, size_y=3.2, aim=(0.0, 0.0, 1.5))


def dress_teal2():
    X, Z, H = 4.0, 11.0, 5.5
    casings("Trim_Teal", skip=("arch",))
    skirting("Trim_Teal", room_runs(-X, X, -Z, Z), 0.0, h=0.12)
    # the rounded cognac sofa along the west wall
    s, sb = gbx("Sofa"), gbx("Sofa_Back")

    def sofa(bm):
        z0, z1 = s["min"][2], s["max"][2]
        cube(bm, (-X, 0.05, z0), (-X + 1.0, 0.5, z1))
        cyl(bm, (-X, 0.62, z0 + 0.23), (-X + 1.0, 0.62, z0 + 0.23), 0.23, seg=20)
        cyl(bm, (-X, 0.62, z1 - 0.23), (-X + 1.0, 0.62, z1 - 0.23), 0.23, seg=20)
        cube(bm, (-X, 0.5, z0 + 0.23), (-X + 1.0, 0.72, z1 - 0.23))
        cube(bm, (-X, 0.85, z0), (-X + 0.35, 1.3, z1))
        cyl(bm, (-X + 0.175, 1.3, z0), (-X + 0.175, 1.3, z1), 0.2, seg=16)
    part("Sofa_Body", "Leather", sofa, smooth=True)
    part("decor_Sofa_Cushions", "Leather", lambda bm: [cyl(bm, (-X + 0.6, 0.92, zz - 0.62), (-X + 0.6, 0.92, zz + 0.62), 0.12, seg=14) for zz in (-1.4, 0.0, 1.4)], smooth=True)
    part("decor_Sofa_Feet", "Sofa_Foot", lambda bm: [cyl(bm, (fx, 0.0, fz), (fx, 0.12, fz), 0.05, seg=10) for fx in (-X + 0.15, -X + 0.85) for fz in (s["min"][2] + 0.2, s["max"][2] - 0.2)])
    # the tall spiky plant: a terracotta pot and long tilted leaves
    p = gbx("Plant_Tall")
    cx, cz = (p["min"][0] + p["max"][0]) / 2, (p["min"][2] + p["max"][2]) / 2
    part("Plant_Pot", "Terracotta", lambda bm: cyl(bm, (cx, 0.0, cz), (cx, 0.7, cz), 0.3, 0.4, seg=20))
    rng = np.random.default_rng(88)

    def spikes(bm):
        cube(bm, (p["min"][0], 0.0, p["min"][2]), (p["min"][0] + 0.02, 0.02, p["min"][2] + 0.02))
        for i in range(14):
            a = rng.random() * 6.28
            r = 0.1 + 0.25 * rng.random()
            top = (cx + math.cos(a) * r, 1.6 + 1.6 * rng.random(), cz + math.sin(a) * r)
            top = (min(max(top[0], p["min"][0] + 0.02), p["max"][0] - 0.02), min(top[1], 3.19), min(max(top[2], p["min"][2] + 0.02), p["max"][2] - 0.02))
            v0 = bm.verts.new(B((cx - 0.04, 0.68, cz)))
            v1 = bm.verts.new(B((cx + 0.04, 0.68, cz)))
            v2 = bm.verts.new(B(top))
            bm.faces.new((v0, v1, v2))
        cube(bm, (p["max"][0] - 0.02, 3.18, p["max"][2] - 0.02), (p["max"][0], 3.2, p["max"][2]))
    part("Plant_Spikes", "Plant_Leaf", spikes, recalc=False)
    part("decor_Soil", "Soil", lambda bm: cyl(bm, (cx, 0.66, cz), (cx, 0.68, cz), 0.37, seg=20))
    # the arch: no leaf; its round top fills the opening's upper corners, a cream trim round it, the black corridor beyond
    d = next(dd for dd in model().doors if dd["name"] == "DoorLeaf_arch")
    (hx, hy, hz), run, inw, w, h = door_geom(d)
    W = w + 0.04
    r = W / 2
    xc = hx - 0.02 + W / 2
    top = h + 0.04

    def arch_fill(bm):
        for sgn in (-1, 1):
            pts = [(xc + sgn * r * math.cos(math.pi / 2 * i / 10), top - r + r * math.sin(math.pi / 2 * i / 10)) for i in range(11)] + [(xc + sgn * r, top)]
            v0 = [bm.verts.new(B((xx, yy, -Z - 0.2))) for xx, yy in pts]
            v1 = [bm.verts.new(B((xx, yy, -Z + 0.0))) for xx, yy in pts]
            bm.faces.new(v0)
            bm.faces.new(v1[::-1])
            for i in range(len(pts)):
                j = (i + 1) % len(pts)
                bm.faces.new((v0[i], v0[j], v1[j], v1[i]))
    part("decor_Arch_Fill", "Paper_Teal", arch_fill)

    def arch_trim(bm):
        n = 16
        for i in range(n):
            a0, a1 = math.pi * i / n, math.pi * (i + 1) / n
            p0 = (xc + (r + 0.06) * math.cos(a0), top - r + (r + 0.06) * math.sin(a0))
            p1 = (xc + (r + 0.06) * math.cos(a1), top - r + (r + 0.06) * math.sin(a1))
            cube(bm, (min(p0[0], p1[0]) - 0.04, min(p0[1], p1[1]) - 0.04, -Z), (max(p0[0], p1[0]) + 0.04, max(p0[1], p1[1]) + 0.04, -Z + 0.03))
        for xx in (xc - r - 0.1, xc + r + 0.02):
            cube(bm, (xx, 0.0, -Z), (xx + 0.08, top - r, -Z + 0.03))
    part("decor_Arch_Trim", "Trim_Teal", arch_trim)
    # peeled wallpaper on the east wall: the glowing grid under it (Grid_Emit), curled paper along two torn edges
    for k in range(3):
        b = gbx(f"decor_Peel_{k + 1}")
        y0, y1, z0, z1 = b["min"][1], b["max"][1], b["min"][2], b["max"][2]
        photo_quads(f"decor_Grid_{k + 1}", "Grid_Emit", [(0, z0, z1, y0, y1, X - 0.005)], cells=1, axis="x", inward=-1)

        def curl(bm, y0=y0, y1=y1, z0=z0, z1=z1, k=k):
            for i in range(6):
                a0, a1 = math.pi * i / 6, math.pi * (i + 1) / 6
                rr = 0.06
                cube(bm, (X - 0.01 - rr * math.sin(a1), y0, z1 + rr * (1 - math.cos(a0)) - 0.01), (X - 0.004 - rr * math.sin(a0) * 0.9, y1 + 0.05, z1 + rr * (1 - math.cos(a1))))
            cube(bm, (X - 0.03, y1, z0 - 0.02), (X - 0.004, y1 + 0.08, z1 + 0.02))
        part(f"decor_Peel_Curl_{k + 1}", "Paper_Back", curl)
        light(f"Grid_{k + 1}", "AREA", (X - 0.3, (y0 + y1) / 2, (z0 + z1) / 2), 18.0, (0.3, 1.0, 0.4), size=1.0, aim=(0.0, (y0 + y1) / 2, (z0 + z1) / 2))
    part("decor_Dome", "Lamp_Emit", lambda bm: sphere(bm, (0.0, H - 0.01, 0.0), 0.4, seg=24, sy=0.25))
    part("decor_Dome_Rim", "Dome", lambda bm: cyl(bm, (0.0, H - 0.03, 0.0), (0.0, H, 0.0), 0.45, seg=24))
    down_light("Dome", (0.0, H - 0.2, 0.0), 600.0, (1.0, 0.82, 0.62), size=1.0)
    for k, dz in enumerate((-7.5, -2.5, 2.5, 7.5)):
        down_light(f"Fill_{k}", (0.0, H - 0.1, dz), 150.0, (1.0, 0.86, 0.72), size=2.5)
    light("Arch_Dark", "POINT", (xc, 1.6, -Z + 0.6), 6.0, (0.4, 0.7, 0.7), size=0.3)


def dress_flooded():
    X0, X1, Z, H = 0.0, 50.0, 2.5, 4.0
    casings("Frame_Wood", skip=("frame", "arch", "red_door"))
    # the painted sky along the north wall, above a dado cap
    s = gbx("decor_Painted_Sky")
    y0, y1, a0, a1 = s["min"][1], s["max"][1], s["min"][0], s["max"][0]
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    nseg = 6
    for i in range(nseg):
        xa, xb = a0 + (a1 - a0) * i / nseg, a0 + (a1 - a0) * (i + 1) / nseg
        vs = [bm.verts.new(B(p)) for p in ((xa, y0, -Z + 0.012), (xb, y0, -Z + 0.012), (xb, y1, -Z + 0.012), (xa, y1, -Z + 0.012))]
        f = bm.faces.new(vs)
        f.normal_update()
        if f.normal.dot(B((0, 0, 1))) < 0:
            f.normal_flip()
        for lp in f.loops:
            p = lp.vert.co
            lp[uvl].uv = ((p.x - a0) / 11.25, (p.z - y0) / (y1 - y0))
    finish("decor_Painted_Sky", bm, "Sky_Paint", PROPS, keep_uv=True)
    boxes("decor_Dado", "Rail_Steel", [((X0 + 1.0, y0 - 0.04, -Z), (a1, y0, -Z + 0.03))])
    # handrails each side, on brackets (over the rail colliders)
    for nm in ("Rail_N", "Rail_S_1", "Rail_S_2"):
        r = gbx(nm)
        zc = (r["min"][2] + r["max"][2]) / 2
        wall_z = -Z if zc < 0 else Z

        def rail(bm, r=r, zc=zc, wall_z=wall_z):
            cube(bm, (r["min"][0], 0.9, r["min"][2]), (r["max"][0], 0.98, r["max"][2]))
            x = r["min"][0] + 0.3
            while x < r["max"][0]:
                cube(bm, (x - 0.015, 0.84, min(zc, wall_z)), (x + 0.015, 0.9, max(zc, wall_z)))
                x += 2.4
        part(nm, "Rail_Steel", rail)
    # empty wooden frames down the south wall, shrinking a little toward the far end
    frames = sorted((b for b in model().boxes if b["name"].startswith("decor_Frame_")), key=lambda b: b["min"][0])
    for k, b in enumerate(frames):
        cx = (b["min"][0] + b["max"][0]) / 2
        sc = 1.25 - 0.4 * k / max(1, len(frames) - 1)
        w2, h2, yc = 0.4 * sc, 0.5 * sc, 2.1
        q = 0.07 * sc
        boxes(f"decor_Frame_{k + 1}", "Frame_Wood", [((cx - w2, yc - h2, Z - 0.06), (cx + w2, yc - h2 + q, Z)), ((cx - w2, yc + h2 - q, Z - 0.06), (cx + w2, yc + h2, Z)),
                                                    ((cx - w2, yc - h2 + q, Z - 0.06), (cx - w2 + q, yc + h2 - q, Z)), ((cx + w2 - q, yc - h2 + q, Z - 0.06), (cx + w2, yc + h2 - q, Z))])
        boxes(f"decor_Frame_Back_{k + 1}", "Frame_Back", [((cx - w2 + q, yc - h2 + q, Z - 0.012), (cx + w2 - q, yc + h2 - q, Z))])
    # the ceiling: square recessed light panels (Lamp_Emit) down the centre, little vents between them
    for k in range(8):
        x = 3.0 + k * 6.4
        boxes(f"decor_Panel_Rim_{k}", "Panel_Rim", [((x - 0.7, H - 0.04, -0.7), (x + 0.7, H, -0.6)), ((x - 0.7, H - 0.04, 0.6), (x + 0.7, H, 0.7)),
                                                   ((x - 0.7, H - 0.04, -0.6), (x - 0.6, H, 0.6)), ((x + 0.6, H - 0.04, -0.6), (x + 0.7, H, 0.6))])
        part(f"decor_Panel_{k}", "Lamp_Emit", lambda bm, x=x: cube(bm, (x - 0.6, H - 0.02, -0.6), (x + 0.6, H - 0.005, 0.6)))
        down_light(f"Panel_{k}", (x, H - 0.1, 0.0), 300.0, COOL, size=1.2, size_y=1.2)
        if k < 7:
            boxes(f"decor_Vent_{k}", "Grate_Steel", [((x + 3.0, H - 0.015, -0.25), (x + 3.4, H, 0.25))])
    # the heaps: sodden cardboard boxes stacked in each heap's box, wet paper slumped over them; three photographs on the first
    for k in range(3):
        b = gbx(f"Heap_{k + 1}")
        rng = np.random.default_rng(140 + k)
        x0, x1, z0, z1, top = b["min"][0], b["max"][0], b["min"][2], b["max"][2], b["max"][1]

        def heap(bm, x0=x0, x1=x1, z0=z0, z1=z1, top=top, rng=rng):
            cube(bm, (x0, 0.0, z0), (x1, 0.12, z1))
            y = 0.12
            layer = 0
            while y < top - 0.05:
                hh = min(0.32 + 0.1 * rng.random(), top - y)
                xa = x0 + 0.1 * layer
                while xa < x1 - 0.2 - 0.1 * layer:
                    wd = min(0.4 + 0.3 * rng.random(), x1 - 0.1 * layer - xa)
                    cube(bm, (xa + 0.01, y, z0 + 0.02 * layer), (xa + wd - 0.01, y + hh, z1 - 0.1 * layer - 0.05 * rng.random()))
                    xa += wd
                y += hh
                layer += 1
            cube(bm, (x0 + 0.5, top - 0.02, z0 + 0.2), (x0 + 0.52, top, z0 + 0.22))
        part(f"Heap_{k + 1}", "Cardboard" if k % 2 == 0 else "Cardboard_Light", heap)
        part(f"decor_Paper_{k + 1}", "Wet_Paper", lambda bm, x0=x0, x1=x1, z1=z1: [cube(bm, (x0 + 0.2 + i * 0.5, 0.0, z1 + 0.05 + 0.1 * (i % 2)),
                                                                                       (x0 + 0.6 + i * 0.5, 0.01, z1 + 0.4 + 0.1 * (i % 2))) for i in range(4)])
    b = gbx("Heap_1")
    boxes("decor_Heap_Photos", "Photo_Wet", [((b["min"][0] + 0.4 + i * 0.42, b["max"][1], b["max"][2] - 0.5), (b["min"][0] + 0.72 + i * 0.42, b["max"][1] + 0.004, b["max"][2] - 0.25))
                                             for i in range(3)])
    # the yellow tactile strip under the water, the grate (soft), the drips: perfect blue blocks melting into puddles
    boxes("decor_Tactile", "Tactile", [((X0 + 0.5, 0.0, 1.0), (X1 - 6.0, 0.004, 1.3))])
    g = gbx("decor_Grate")

    def grate(bm):
        gx0, gx1, gz0, gz1 = g["min"][0], g["max"][0], g["min"][2], g["max"][2]
        cube(bm, (gx0, 0.0, gz0), (gx1, 0.03, gz0 + 0.05))
        cube(bm, (gx0, 0.0, gz1 - 0.05), (gx1, 0.03, gz1))
        for i in range(9):
            x = gx0 + 0.05 + i * (gx1 - gx0 - 0.1) / 8
            cube(bm, (x - 0.012, 0.0, gz0), (x + 0.012, 0.03, gz1))
    part("decor_Grate", "Grate_Steel", grate)
    boxes("decor_Grate_Dark", "Void", [((g["min"][0] + 0.02, -0.06, g["min"][2] + 0.05), (g["max"][0] - 0.02, -0.002, g["max"][2] - 0.05))])
    rng = np.random.default_rng(149)
    boxes("decor_Drips", "Drip_Blue", [((x, 0.0, z), (x + s, s, z + s)) for x, z, s in
                                      ((6.0 + 38 * rng.random(), -1.5 + 3 * rng.random(), 0.06 + 0.06 * rng.random()) for _ in range(9))])
    # the water: one sheet over the whole floor, its own unbaked material (transparent; the page may ripple it)
    part("decor_Water", "Water", lambda bm: cube(bm, (X0, 0.05, -Z), (X1, 0.052, Z)))
    # the red door's lit frame
    d = next(dd for dd in model().doors if dd["name"] == "DoorLeaf_red_door")
    (hx, hy, hz), run, inw, w, h = door_geom(d)
    za, zb = sorted((hz, hz + run[1] * w))
    boxes("decor_Red_Frame", "Emergency_Emit", [((X1 - 0.03, 0.0, za - 0.1), (X1, h + 0.1, za - 0.02)), ((X1 - 0.03, 0.0, zb + 0.02), (X1, h + 0.1, zb + 0.1)),
                                               ((X1 - 0.03, h + 0.02, za - 0.1), (X1, h + 0.1, zb + 0.1))])
    light("Red_Door", "AREA", (X1 - 0.4, 1.2, 0.0), 120.0, (1.0, 0.1, 0.06), size=1.0, size_y=2.0, aim=(0.0, 1.2, 0.0))
    # the frame door: a door-sized gilt picture frame round its leaf
    d = next(dd for dd in model().doors if dd["name"] == "DoorLeaf_frame")
    (hx, hy, hz), run, inw, w, h = door_geom(d)
    xa, xb = sorted((hx, hx + run[0] * w))
    boxes("decor_Frame_Door", "Frame_Wood", [((xa - 0.16, 0.0, Z - 0.08), (xa - 0.02, h + 0.16, Z)), ((xb + 0.02, 0.0, Z - 0.08), (xb + 0.16, h + 0.16, Z)),
                                            ((xa - 0.16, h + 0.02, Z - 0.08), (xb + 0.16, h + 0.16, Z))])


def dress_trampoline():
    X, Z, H = 15.0, 25.0, 9.0
    casings("Pad_Orange")
    # the beds: black weave in yellow edges, in orange padded frames (pale every other row)
    bed, edge, frame, pale = [], [], [], []
    for i in range(6):
        for j in range(9):
            x0, z0 = -11.0 + i * 3.8, -21.0 + j * 4.2
            bed.append(((x0, 0.0, z0), (x0 + 3.0, 0.02, z0 + 3.4)))
            for r in (((x0, 0.0, z0), (x0 + 3.0, 0.03, z0 + 0.08)), ((x0, 0.0, z0 + 3.32), (x0 + 3.0, 0.03, z0 + 3.4)),
                      ((x0, 0.0, z0), (x0 + 0.08, 0.03, z0 + 3.4)), ((x0 + 2.92, 0.0, z0), (x0 + 3.0, 0.03, z0 + 3.4))):
                edge.append(r)
            tgt = pale if j % 2 else frame
            for r in (((x0 - 0.2, 0.0, z0 - 0.2), (x0 + 3.2, 0.06, z0)), ((x0 - 0.2, 0.0, z0 + 3.4), (x0 + 3.2, 0.06, z0 + 3.6)),
                      ((x0 - 0.2, 0.0, z0), (x0, 0.06, z0 + 3.4)), ((x0 + 3.0, 0.0, z0), (x0 + 3.2, 0.06, z0 + 3.4))):
                tgt.append(r)
    boxes("decor_Beds", "Bed_Weave", bed)
    boxes("decor_Bed_Edges", "Edge_Yellow", edge)
    boxes("decor_Bed_Frames", "Pad_Orange", frame)
    boxes("decor_Bed_Frames_Pale", "Pad_Pale", pale)
    # padded columns with yellow bands
    for k in range(4):
        c = gbx(f"Column_{k + 1}")
        part(f"Column_{k + 1}", "Pad_Orange", lambda bm, c=c: cube(bm, c["min"], c["max"]))
        part(f"decor_Column_Bands_{k + 1}", "Column_Band", lambda bm, c=c: [cube(bm, (c["min"][0] - 0.02, y, c["min"][2] - 0.02), (c["max"][0] + 0.02, y + 0.15, c["max"][2] + 0.02))
                                                                            for y in (1.0, 2.2)])
    # the angled trampoline walls at both edges: a sloped bed of mesh in a padded frame
    for nm in ("AngledWall_W", "AngledWall_E"):
        a = gbx(nm)
        west = nm.endswith("W")
        wx0, wx1, wz0, wz1 = a["min"][0], a["max"][0], a["min"][2], a["max"][2]
        inner, outer = (wx1, wx0) if west else (wx0, wx1)
        prof = [(outer, 0.0), (inner, 0.0), (outer, 2.4)]

        def wedge(bm, prof=prof, wz0=wz0, wz1=wz1):
            prism(bm, prof, wz0, wz1, "z")
        part(nm, "Wall_Mesh", wedge)
        part(f"decor_{nm}_Pad", "Pad_Orange", lambda bm, wz0=wz0, wz1=wz1, wx0=wx0, wx1=wx1: [cube(bm, (wx0, 0.0, wz0), (wx1, 2.45, wz0 + 0.15)),
                                                                                              cube(bm, (wx0, 0.0, wz1 - 0.15), (wx1, 2.45, wz1))])
    # the truss ceiling: beams across every 4.7 m, purlins along, LED panels between (Lamp_Emit)
    beams = []
    z = -Z + 2.0
    while z < Z:
        beams.append(((-X, H - 0.9, z - 0.08), (X, H - 0.75, z + 0.08)))
        beams.append(((-X, H - 0.15, z - 0.08), (X, H, z + 0.08)))
        for xx in np.arange(-X + 1.0, X, 2.0):
            beams.append(((xx - 0.04, H - 0.75, z - 0.04), (xx + 0.04, H - 0.15, z + 0.04)))
        z += 4.7
    for xx in (-10.0, -5.0, 0.0, 5.0, 10.0):
        beams.append(((xx - 0.06, H - 0.3, -Z), (xx + 0.06, H - 0.15, Z)))
    boxes("decor_Truss", "Truss_Steel", beams)
    leds = []
    for i, xx in enumerate((-12.5, -7.5, -2.5, 2.5, 7.5, 12.5)):
        for j, zz in enumerate(np.arange(-Z + 4.35, Z, 4.7)):
            leds.append(((xx - 0.6, H - 0.95, zz - 0.6), (xx + 0.6, H - 0.92, zz + 0.6)))
            if (i + j) % 2 == 0:
                down_light(f"LED_{i}_{j}", (xx, H - 1.0, float(zz)), 900.0, (1.0, 0.9, 0.76), size=1.2, size_y=1.2)
    boxes("decor_LEDs", "Lamp_Emit", leds)
    # the vent you fall out of (a grille in the ceiling over the apron), and the red glow far north (the anomaly)
    v = gbx("decor_Vent")
    boxes("decor_Vent_Grille", "Vent_Grille", [((v["min"][0] + i * 0.2, H - 0.12, v["min"][2]), (v["min"][0] + i * 0.2 + 0.05, H - 0.02, v["max"][2])) for i in range(11)])
    boxes("decor_Vent_Dark", "Void", [((v["min"][0], H - 0.01, v["min"][2]), (v["max"][0], H, v["max"][2]))])
    rg = gbx("decor_Red_Glow")
    part("decor_Red_Glow", "Emergency_Emit", lambda bm: sphere(bm, ((rg["min"][0] + rg["max"][0]) / 2, (rg["min"][1] + rg["max"][1]) / 2, (rg["min"][2] + rg["max"][2]) / 2),
                                                             0.5, seg=20))
    light("Red_Glow", "POINT", (0.0, 1.6, -23.3), 300.0, (1.0, 0.08, 0.05), size=0.5)
    # the scuff mark on one pad near the apron (the page wraps you back over it)
    boxes("decor_Scuff", "Truss_Steel", [((1.7, 0.061, 18.8), (2.4, 0.062, 19.1))])


def dress_grocery():
    X, Z, H = 25.0, 25.0, 5.0
    casings("Post_Cream", skip=("entrance",))
    skirting("Kick", room_runs(-X, X, -Z, Z), 0.0, h=0.12)
    # the gondola shelving: one run per shelf box (kick, back panel, five shelves each side, end panels), merged by material at export
    gond, back, kick, caps_ = [], [], [], {"Endcap_Pink": [], "Endcap_Lime": [], "Endcap_Cyan": []}
    accents = list(caps_)
    for b in model().boxes:
        if not b["name"].startswith("Shelf_"):
            continue
        x0, y0, z0 = b["min"]
        x1, y1, z1 = b["max"]
        along_x = (x1 - x0) > (z1 - z0)
        if along_x:
            zc = (z0 + z1) / 2
            back.append(((x0, 0.12, zc - 0.03), (x1, y1, zc + 0.03)))
            kick.append(((x0, 0.0, z0 + 0.04), (x1, 0.12, z1 - 0.04)))
            for y in (0.12, 0.5, 0.85, 1.2, 1.55):
                gond.append(((x0 + 0.02, y, z0), (x1 - 0.02, y + 0.03, z1)))
            for xe in (x0, x1 - 0.03):
                gond.append(((xe, 0.0, z0), (xe + 0.03, y1, z1)))
        else:
            xc = (x0 + x1) / 2
            back.append(((xc - 0.03, 0.12, z0), (xc + 0.03, y1, z1)))
            kick.append(((x0 + 0.04, 0.0, z0), (x1 - 0.04, 0.12, z1)))
            for y in (0.12, 0.5, 0.85, 1.2, 1.55):
                gond.append(((x0, y, z0 + 0.02), (x1, y + 0.03, z1 - 0.02)))
            for ze in (z0, z1 - 0.03):
                gond.append(((x0, 0.0, ze), (x1, y1, ze + 0.03)))
    # each run is its own object (the layout check covers one collider per run); the export merges them by material
    k = 0
    for b in model().boxes:
        if not b["name"].startswith("Shelf_"):
            continue
        mn, mx = b["min"], b["max"]
        sel = lambda rs: [r for r in rs if all(mn[i] - 1e-6 <= r[0][i] and r[1][i] <= mx[i] + 1e-6 for i in range(3))]
        part(b["name"], "Gondola", lambda bm, rs=sel(gond): [cube(bm, a, c) for a, c in rs])
        part(f"decor_{b['name']}_Back", "Gondola_Back", lambda bm, rs=sel(back): [cube(bm, a, c) for a, c in rs])
        part(f"decor_{b['name']}_Kick", "Kick", lambda bm, rs=sel(kick): [cube(bm, a, c) for a, c in rs])
        k += 1
    # the posts: cream end caps with a band of the aisle's accent colour (the psychedelic touch: each aisle a sweet)
    for i, b in enumerate(b for b in model().boxes if b["name"].startswith("Post_")):
        mn, mx = b["min"], b["max"]
        part(b["name"], "Post_Cream", lambda bm, mn=mn, mx=mx: cube(bm, mn, mx))
        acc = accents[i % 3]
        part(f"decor_{b['name']}_Band", acc, lambda bm, mn=mn, mx=mx: cube(bm, (mn[0] - 0.01, 1.55, mn[2] - 0.01), (mx[0] + 0.01, 1.75, mx[2] + 0.01)))
    # fluorescent strips in rows along z, one every 5 m, over the aisles
    strips, housing = [], []
    for c in range(10):
        x = -X + (c + 0.5) * 5.0
        for zz in np.arange(-Z + 1.0, Z - 1.0, 4.0):
            housing.append(((x - 0.12, H - 0.08, zz), (x + 0.12, H, zz + 3.0)))
            strips.append(((x - 0.08, H - 0.1, zz + 0.05), (x + 0.08, H - 0.08, zz + 2.95)))
        for zz in np.arange(-Z + 2.5, Z, 10.0):
            down_light(f"Strip_{c}_{int(zz)}", (x, H - 0.15, float(zz) + 2.5), 520.0, (1.0, 0.94, 0.84), size=0.4, size_y=8.0)
    boxes("decor_Strip_Housing", "Strip_Housing", housing)
    boxes("decor_Strips", "Lamp_Emit", strips)
    # the red cart, roped off between four chrome stanchions with sagging caution tape
    cb = gbx("Cart")

    def cart(bm):
        x0, x1, z0, z1 = cb["min"][0], cb["max"][0], cb["min"][2], cb["max"][2]
        for y in (0.45, 1.0):
            for (a, b_) in (((x0, z0), (x1, z0)), ((x1, z0), (x1, z1)), ((x1, z1), (x0, z1)), ((x0, z1), (x0, z0))):
                cyl(bm, (a[0], y, a[1]), (b_[0], y, b_[1]), 0.015, seg=6)
        for xx in np.linspace(x0, x1, 5):
            cyl(bm, (xx, 0.45, z0), (xx, 1.0, z0), 0.008, seg=5)
            cyl(bm, (xx, 0.45, z1), (xx, 1.0, z1), 0.008, seg=5)
        for zz in np.linspace(z0, z1, 7):
            cyl(bm, (x0, 0.45, zz), (x0, 1.0, zz), 0.008, seg=5)
            cyl(bm, (x1, 0.45, zz), (x1, 1.0, zz), 0.008, seg=5)
            cyl(bm, (x0, 0.45, zz), (x1, 0.45, zz), 0.008, seg=5)
        for xx in (x0 + 0.05, x1 - 0.05):
            for zz in (z0 + 0.1, z1 - 0.1):
                cyl(bm, (xx, 0.0, zz), (xx, 0.45, zz), 0.018, seg=6)
        cyl(bm, (x0, 1.05, z1 - 0.02), (x1, 1.05, z1 - 0.02), 0.02, seg=8)
    part("Cart", "Cart_Red", cart)
    part("decor_Cart_Wheels", "Wheel", lambda bm: [cyl(bm, (xx - 0.02, 0.06, zz), (xx + 0.02, 0.06, zz), 0.06, seg=12)
                                                    for xx in (cb["min"][0] + 0.05, cb["max"][0] - 0.05) for zz in (cb["min"][2] + 0.1, cb["max"][2] - 0.1)])
    tops = []
    for k in range(4):
        st = gbx(f"Stanchion_{k + 1}")
        cx, cz = (st["min"][0] + st["max"][0]) / 2, (st["min"][2] + st["max"][2]) / 2
        part(f"Stanchion_{k + 1}", "Chrome", lambda bm, cx=cx, cz=cz, st=st: (cyl(bm, (cx, 0.0, cz), (cx, 0.03, cz), 0.1, seg=16),
                                                                               cyl(bm, (cx, 0.03, cz), (cx, 1.0, cz), 0.025, seg=10)))
        tops.append((cx, cz))

    def tape(bm):
        order = [0, 1, 3, 2, 0]
        for i in range(4):
            (ax_, az), (bx_, bz) = tops[order[i]], tops[order[i + 1]]
            n = 8
            for j in range(n):
                t0, t1 = j / n, (j + 1) / n
                s0, s1 = 0.18 * math.sin(math.pi * t0), 0.18 * math.sin(math.pi * t1)
                p0 = (ax_ + (bx_ - ax_) * t0, 0.95 - s0, az + (bz - az) * t0)
                p1 = (ax_ + (bx_ - ax_) * t1, 0.95 - s1, az + (bz - az) * t1)
                vs = [bm.verts.new(B(p)) for p in (p0, p1, (p1[0], p1[1] - 0.05, p1[2]), (p0[0], p0[1] - 0.05, p0[2]))]
                bm.faces.new(vs)
    part("decor_Caution_Tape", "Tape_Yellow", tape, recalc=False)
    # what is left: pyramids of tins in the three dead ends (one red tin each), flats of cardboard beside them
    for sp in (e for e in model().empties if e["name"].startswith("Spot_tin_")):
        x, _, z = sp["pos"]
        tins, red = [], []
        n = 0
        for row in range(4):
            for i in range(4 - row):
                for j in range(4 - row):
                    p = (x - 0.36 + (i + row * 0.5) * 0.24, row * 0.17, z + 1.0 + (j + row * 0.5) * 0.24)
                    (red if n == 7 else tins).append(p)
                    n += 1
        part(f"decor_Tins_{sp['name']}", "Tin", lambda bm, tins=tins: [cyl(bm, p, (p[0], p[1] + 0.165, p[2]), 0.1, seg=12) for p in tins])
        part(f"decor_Tin_Bands_{sp['name']}", "Tin_Band", lambda bm, tins=tins: [cyl(bm, (p[0], p[1] + 0.04, p[2]), (p[0], p[1] + 0.125, p[2]), 0.102, seg=12) for p in tins])
        part(f"decor_Tin_Red_{sp['name']}", "Tin_Red", lambda bm, red=red: [cyl(bm, p, (p[0], p[1] + 0.165, p[2]), 0.102, seg=12) for p in red])
        boxes(f"decor_Flats_{sp['name']}", "Card_Flat", [((x + 0.7, 0.0, z + 0.9), (x + 1.4, 0.06, z + 1.7))])
    # the lit EXIT over the fire door
    es = gbx("decor_Exit_Sign")
    boxes("decor_Exit_Box", "Strip_Housing", [((es["min"][0] - 0.05, es["min"][1] - 0.05, -Z), (es["max"][0] + 0.05, es["max"][1] + 0.05, -Z + 0.1))])
    part("decor_Exit_Text", "Emergency_Emit", lambda bm: add_text(bm, "EXIT", 0.3, 0.01, ((es["min"][0] + es["max"][0]) / 2, (es["min"][1] + es["max"][1]) / 2, -Z + 0.1),
                                                                   (1, 0, 0), (0, 1, 0), (0, 0, 1)))
    light("Exit_Glow", "POINT", ((es["min"][0] + es["max"][0]) / 2, 2.4, -Z + 0.5), 20.0, (1.0, 0.1, 0.06), size=0.2)


def dress_repeating_room():
    X, Z, H = 6.0, 6.0, 3.2
    casings("Trim_Repeat", skip=("secret_ops",))
    skirting("Trim_Repeat", room_runs(-X, X, -Z, Z), 0.0, h=0.14, cuts_extra=(("z", X, -3.85, -2.15),))
    boxes("decor_Cornice", "Trim_Repeat", [((-X, H - 0.12, -Z), (X, H, -Z + 0.05)), ((-X, H - 0.12, Z - 0.05), (X, H, Z)),
                                           ((-X, H - 0.12, -Z), (-X + 0.05, H, Z)), ((X - 0.05, H - 0.12, -Z), (X, H, Z))])
    # the pink velvet armchair, over its box
    a = gbx("Armchair")
    x0, x1, z0, z1 = a["min"][0], a["max"][0], a["min"][2], a["max"][2]

    def chair(bm):
        cube(bm, (x0, 0.06, z0), (x1, 0.45, z1))
        cube(bm, (x0, 0.45, z0), (x0 + 0.25, 0.9, z1))                  # the back against the west
        cube(bm, (x0 + 0.25, 0.45, z0), (x1, 0.68, z0 + 0.2))
        cube(bm, (x0 + 0.25, 0.45, z1 - 0.2), (x1, 0.68, z1))
        for fx in (x0 + 0.08, x1 - 0.08):
            for fz in (z0 + 0.08, z1 - 0.08):
                cyl(bm, (fx, 0.0, fz), (fx, 0.06, fz), 0.04, seg=8)
    part("Armchair", "Velvet_Pink", chair)
    boxes("decor_Armchair_Cushion", "Velvet_Pink", [((x0 + 0.27, 0.45, z0 + 0.22), (x1 - 0.02, 0.56, z1 - 0.22))])
    # the side table, a lamp on it (Lamp_Emit) and a clock whose hands the page may move
    t = gbx("Side_Table")
    tx, tz = (t["min"][0] + t["max"][0]) / 2, (t["min"][2] + t["max"][2]) / 2

    def table(bm):
        cyl(bm, (tx, 0.66, tz), (tx, 0.7, tz), 0.4, seg=32)
        cyl(bm, (tx, 0.03, tz), (tx, 0.66, tz), 0.05, seg=12)
        cube(bm, (t["min"][0], 0.0, t["min"][2]), (t["max"][0], 0.03, t["max"][2]))
    part("Side_Table", "Wood_Table", table)
    part("decor_Lamp_Base", "Trim_Repeat", lambda bm: cyl(bm, (tx, 0.7, tz), (tx, 1.05, tz), 0.06, 0.04, seg=12))
    part("decor_Lamp_Shade", "Lamp_Emit", lambda bm: cyl(bm, (tx, 1.0, tz), (tx, 1.25, tz), 0.2, 0.13, seg=20, cap=False))
    # a picture of this room, in which there is a picture of this room (on the west wall)
    photo_quads("decor_Picture", "Picture_Room", [(0, -1.0, 1.0, 1.2, 2.2, -X + 0.02)], cells=1, axis="x", inward=1)
    boxes("decor_Picture_Frame", "Frame_Gilt", [((-X, 1.12, -1.08), (-X + 0.05, 1.2, 1.08)), ((-X, 2.2, -1.08), (-X + 0.05, 2.28, 1.08)),
                                               ((-X, 1.2, -1.08), (-X + 0.05, 2.2, -1.0)), ((-X, 1.2, 1.0), (-X + 0.05, 2.2, 1.08))])
    # the baffle hides the recess: same paper, a cream cap; the recess and its door are the wall's lilac (the door seen from one angle)
    b = gbx("Baffle")
    boxes("decor_Baffle_Cap", "Trim_Repeat", [((b["min"][0] - 0.01, 0.0, b["min"][2] - 0.01), (b["max"][0] + 0.01, 0.12, b["max"][2] + 0.01))])
    # one pendant in the middle of the ceiling, and soft fills
    part("decor_Pendant", "Lamp_Emit", lambda bm: sphere(bm, (0.0, H - 0.55, 0.0), 0.28, seg=20))
    part("decor_Pendant_Cord", "Trim_Repeat", lambda bm: cyl(bm, (0.0, H - 0.3, 0.0), (0.0, H, 0.0), 0.008, seg=6))
    light("Pendant", "POINT", (0.0, H - 0.55, 0.0), 260.0, WARM, size=0.25)
    light("Table_Lamp", "POINT", (tx, 1.12, tz), 60.0, WARM, size=0.12)
    for k, (dx, dz) in enumerate(((-3.0, -3.0), (3.0, -3.0), (-3.0, 3.0), (3.0, 3.0))):
        down_light(f"Fill_{k}", (dx, H - 0.05, dz), 90.0, (1.0, 0.88, 0.85), size=2.0)
    light("Recess", "POINT", (7.2, 2.2, -3.0), 12.0, (1.0, 0.86, 0.9), size=0.2)


def sec_cam(name, pos, face):
    """A security camera on its wall: a white body on a black arm, the lens looking along `face` (game x, z), tilted down."""
    x, y, z = pos
    fx, fz = face
    ln = math.hypot(fx, fz) or 1.0
    fx, fz = fx / ln, fz / ln

    def body(bm):
        cyl(bm, (x - fx * 0.12, y + 0.02, z - fz * 0.12), (x + fx * 0.2, y - 0.04, z + fz * 0.2), 0.07, seg=12)
    def arm(bm):
        cyl(bm, (x - fx * 0.15, y + 0.12, z - fz * 0.15), (x - fx * 0.12, y + 0.02, z - fz * 0.12), 0.02, seg=6)
        cyl(bm, (x + fx * 0.2, y - 0.04, z + fz * 0.2), (x + fx * 0.23, y - 0.045, z + fz * 0.23), 0.05, seg=12)
    part(f"decor_{name}_Body", "Cam_White", body)
    part(f"decor_{name}_Lens", "Cam_Black", arm)


def dress_finale():
    X, Z, H = 24.0, 22.0, 4.5
    M = model()
    casings("Kick_Finale")
    skirting("Kick_Finale", room_runs(-X, X, -Z, Z), 0.0, h=0.14)
    # a neon pink stripe round the hall and the wings at 1.2 m (the game's palette turning on you)
    rects = []
    for x0, x1, zz, sg in ((-X, X, -Z, 1), (-X, X, Z, -1)):
        rects.append(((x0, 1.15, min(zz, zz + sg * 0.012)), (x1, 1.3, max(zz, zz + sg * 0.012))))
    for xx, sg in ((-X, 1), (X, -1)):
        rects.append(((min(xx, xx + sg * 0.012), 1.15, -Z), (max(xx, xx + sg * 0.012), 1.3, Z)))
    boxes("decor_Stripe", "Stripe_Pink", rects)
    # offices: cubicle partitions (fabric on aluminium), desks, a monitor on each (Screen_Emit)
    for b in M.boxes:
        n = b["name"]
        if n.startswith("Cubicle_"):
            mn, mx = b["min"], b["max"]
            part(n, "Cubicle_Panel", lambda bm, mn=mn, mx=mx: cube(bm, (mn[0], 0.05, mn[2]), (mx[0], mx[1] - 0.04, mx[2])))
            part(f"decor_{n}_Frame", "Cubicle_Frame", lambda bm, mn=mn, mx=mx: (cube(bm, (mn[0] - 0.005, mx[1] - 0.04, mn[2] - 0.005), (mx[0] + 0.005, mx[1], mx[2] + 0.005)),
                                                                             cube(bm, (mn[0] - 0.005, 0.0, mn[2] - 0.005), (mx[0] + 0.005, 0.05, mx[2] + 0.005))))
        elif n.startswith("Desk_"):
            mn, mx = b["min"], b["max"]

            def desk(bm, mn=mn, mx=mx):
                cube(bm, (mn[0], 0.71, mn[2]), (mx[0], 0.75, mx[2]))
                for lx in (mn[0] + 0.03, mx[0] - 0.06):
                    cube(bm, (lx, 0.0, mn[2] + 0.03), (lx + 0.03, 0.71, mx[2] - 0.03))
            part(n, "Desk_Top", desk)
            cx, cz = (mn[0] + mx[0]) / 2, mn[2] + 0.2
            boxes(f"decor_{n}_Monitor", "Monitor", [((cx - 0.3, 0.75, cz - 0.03), (cx + 0.3, 1.15, cz + 0.02)), ((cx - 0.04, 0.75, cz - 0.02), (cx + 0.04, 0.8, cz + 0.1))])
            boxes(f"decor_{n}_Screen", "Screen_Emit", [((cx - 0.27, 0.78, cz + 0.02), (cx + 0.27, 1.12, cz + 0.024))])
    # the house: a bed with a pink quilt, a wardrobe, a table with a laptop (the house's computer), an orange sofa, a round rug
    b = gbx("House_Bed")
    bx0, bx1, bz0, bz1 = b["min"][0], b["max"][0], b["min"][2], b["max"][2]
    part("House_Bed", "Wood_House", lambda bm: (cube(bm, (bx0, 0.0, bz0), (bx1, 0.35, bz1)), cube(bm, (bx0, 0.35, bz0), (bx0 + 0.08, 0.6, bz1))))
    boxes("decor_Bed_Quilt", "Quilt_Pink", [((bx0 + 0.08, 0.35, bz0 + 0.02), (bx1 - 0.02, 0.55, bz1 - 0.02))])
    boxes("decor_Bed_Pillow", "Linen", [((bx0 + 0.12, 0.55, bz0 + 0.2), (bx0 + 0.6, 0.6, bz1 - 0.2))])
    w = gbx("House_Wardrobe")
    part("House_Wardrobe", "Wood_House", lambda bm: cube(bm, w["min"], w["max"]))
    boxes("decor_Wardrobe_Doors", "Maple", [((w["max"][0], 0.1, w["min"][2] + 0.05), (w["max"][0] + 0.02, 2.1, (w["min"][2] + w["max"][2]) / 2 - 0.01)),
                                           ((w["max"][0], 0.1, (w["min"][2] + w["max"][2]) / 2 + 0.01), (w["max"][0] + 0.02, 2.1, w["max"][2] - 0.05))])
    t = gbx("House_Table")

    def htable(bm):
        cube(bm, (t["min"][0], 0.75, t["min"][2]), (t["max"][0], 0.8, t["max"][2]))
        for lx in (t["min"][0] + 0.05, t["max"][0] - 0.1):
            for lz in (t["min"][2] + 0.05, t["max"][2] - 0.1):
                cube(bm, (lx, 0.0, lz), (lx + 0.05, 0.75, lz + 0.05))
    part("House_Table", "Maple", htable)
    boxes("decor_Laptop", "Monitor", [((-12.8, 0.8, 11.3), (-12.2, 0.82, 11.7)), ((-12.8, 0.82, 11.28), (-12.2, 1.12, 11.3))])
    boxes("decor_Laptop_Screen", "Screen_Emit", [((-12.76, 0.84, 11.302), (-12.24, 1.1, 11.306))])
    so = gbx("House_Sofa")
    part("House_Sofa", "Leather", lambda bm: (cube(bm, (so["min"][0], 0.05, so["min"][2]), (so["max"][0], 0.45, so["max"][2])),
                                             cube(bm, (so["min"][0], 0.45, so["max"][2] - 0.3), (so["max"][0], 0.9, so["max"][2])),
                                             cube(bm, (so["min"][0], 0.0, so["min"][2]), (so["min"][0] + 0.02, 0.05, so["min"][2] + 0.02))))
    part("decor_House_Rug", "Rug_Finale", lambda bm: cyl(bm, (-15.0, 0.0, 9.0), (-15.0, 0.01, 9.0), 2.6, seg=40))
    # servers: rack rows (grilles, blinking lights: Server_Emit), the console on the last rack's south face
    for k in range(4):
        r = gbx(f"Rack_{k + 1}")
        part(f"Rack_{k + 1}", "Rack_Body", lambda bm, r=r: cube(bm, r["min"], r["max"]))
        grills, leds = [], []
        for i in range(10):
            xa = r["min"][0] + 0.1 + i * 1.19
            for zz, sg in ((r["min"][2], -1), (r["max"][2], 1)):
                q0, q1 = sorted((zz, zz + sg * 0.01))
                grills.append(((xa, 0.15, q0), (xa + 1.0, 2.05, q1)))
                for j in range(6):
                    leds.append(((xa + 0.1 + 0.12 * (j % 3), 1.7 - 0.25 * j, min(q0, q1) - 0.004 * (sg < 0)), (xa + 0.16 + 0.12 * (j % 3), 1.73 - 0.25 * j, max(q0, q1) + 0.004 * (sg > 0))))
        boxes(f"decor_Rack_Grilles_{k + 1}", "Rack_Grille", grills)
        boxes(f"decor_Rack_Leds_{k + 1}", "Server_Emit", leds)
    r4 = gbx("Rack_4")
    boxes("decor_Console", "Monitor", [((14.5, 1.0, r4["max"][2]), (15.5, 1.6, r4["max"][2] + 0.08))])
    boxes("decor_Console_Screen", "Screen_Emit", [((14.55, 1.05, r4["max"][2] + 0.08), (15.45, 1.55, r4["max"][2] + 0.085))])
    # aisles: gondola runs over the shelf boxes, a till on the last one
    for k in range(4):
        s_ = gbx(f"Aisle_Shelf_{k + 1}")
        x0, x1, z0, z1, top = s_["min"][0], s_["max"][0], s_["min"][2], s_["max"][2], s_["max"][1]

        def gond(bm, x0=x0, x1=x1, z0=z0, z1=z1, top=top):
            zc = (z0 + z1) / 2
            cube(bm, (x0, 0.0, z0 + 0.04), (x1, 0.12, z1 - 0.04))
            cube(bm, (x0, 0.12, zc - 0.03), (x1, top, zc + 0.03))
            for y in (0.12, 0.5, 0.85, 1.2, 1.55):
                cube(bm, (x0 + 0.02, y, z0), (x1 - 0.02, y + 0.03, z1))
            for xe in (x0, x1 - 0.03):
                cube(bm, (xe, 0.0, z0), (xe + 0.03, top, z1))
        part(f"Aisle_Shelf_{k + 1}", "Gondola", gond)
    s4 = gbx("Aisle_Shelf_4")
    boxes("decor_Till", "Till", [((14.6, s4["max"][1], s4["max"][2] - 0.5), (15.4, s4["max"][1] + 0.25, s4["max"][2] - 0.1))])
    boxes("decor_Till_Screen", "Screen_Emit", [((14.7, s4["max"][1] + 0.25, s4["max"][2] - 0.35), (15.3, s4["max"][1] + 0.45, s4["max"][2] - 0.33))])
    # the hall's fountain: a cyan basin, a sheet of water (Water, unbaked), a spout
    f = gbx("Hall_Fountain")
    fx0, fx1, fz0, fz1 = f["min"][0], f["max"][0], f["min"][2], f["max"][2]

    def basin(bm):
        cube(bm, (fx0, 0.0, fz0), (fx1, 0.9, fz0 + 0.15))
        cube(bm, (fx0, 0.0, fz1 - 0.15), (fx1, 0.9, fz1))
        cube(bm, (fx0, 0.0, fz0 + 0.15), (fx0 + 0.15, 0.9, fz1 - 0.15))
        cube(bm, (fx1 - 0.15, 0.0, fz0 + 0.15), (fx1, 0.9, fz1 - 0.15))
        cube(bm, (fx0 + 0.15, 0.0, fz0 + 0.15), (fx1 - 0.15, 0.5, fz1 - 0.15))
        cyl(bm, ((fx0 + fx1) / 2, 0.5, (fz0 + fz1) / 2), ((fx0 + fx1) / 2, 1.6, (fz0 + fz1) / 2), 0.12, 0.06, seg=16)
    part("Hall_Fountain", "Basin", basin)
    part("decor_Fountain_Water", "Water", lambda bm: cube(bm, (fx0 + 0.15, 0.75, fz0 + 0.15), (fx1 - 0.15, 0.76, fz1 - 0.15)))
    # the ten security cameras (art; the layout's SecCam_ empties are where they look from), the agents' vents
    for c in M.cams:
        sec_cam(c["name"].replace("SecCam_", "Cam_"), c["pos"], c["face"])
    for b in M.boxes:
        if b["name"].startswith("decor_Vent_"):
            mn, mx = b["min"], b["max"]
            thin = min(range(3), key=lambda i: mx[i] - mn[i])
            bars = []
            for i in range(8):
                if thin == 0:
                    zz = mn[2] + (i + 0.5) * (mx[2] - mn[2]) / 8
                    bars.append(((mn[0], mn[1], zz - 0.02), (mx[0], mx[1], zz + 0.02)))
                else:
                    xx = mn[0] + (i + 0.5) * (mx[0] - mn[0]) / 8
                    bars.append(((xx - 0.02, mn[1], mn[2]), (xx + 0.02, mx[1], mx[2])))
            boxes(b["name"] + "_Grille", "Vent_Grille", bars)
            boxes(b["name"] + "_Dark", "Void", [(mn, mx)])
    # the green EXIT over the win doors
    d = next(dd for dd in M.doors if dd["name"] == "DoorLeaf_win")
    (hx, hy, hz), run, inw, w_, h_ = door_geom(d)
    xc = hx + run[0] * w_ / 2
    boxes("decor_Exit_Box", "Strip_Housing", [((xc - 0.45, h_ + 0.25, -Z), (xc + 0.45, h_ + 0.6, -Z + 0.1))])
    part("decor_Exit_Text", "Emergency_Emit_Green", lambda bm: add_text(bm, "EXIT", 0.25, 0.01, (xc, h_ + 0.425, -Z + 0.1), (1, 0, 0), (0, 1, 0), (0, 0, 1)))
    # lights: strips over the hall and the wings, the house warmer, the server room dimmer and blue
    strips, housing = [], []
    for xx in (-21.0, -15.0, -9.0, -3.0, 3.0, 9.0, 15.0, 21.0):
        for z0 in np.arange(-Z + 1.0, Z - 1.0, 4.0):
            housing.append(((xx - 0.12, H - 0.08, z0), (xx + 0.12, H, z0 + 3.0)))
            strips.append(((xx - 0.08, H - 0.1, z0 + 0.05), (xx + 0.08, H - 0.08, z0 + 2.95)))
        for zc in (-15.0, -5.0, 5.0, 15.0):
            col = (0.75, 0.85, 1.0) if (xx > 6 and zc < 0) else (1.0, 0.86, 0.7) if (xx < -6 and zc > 0) else (1.0, 0.94, 0.86)
            pw = 300.0 if (xx > 6 and zc < 0) else 520.0
            down_light(f"Strip_{int(xx)}_{int(zc)}", (xx, H - 0.15, zc), pw, col, size=0.4, size_y=8.0)
    boxes("decor_Strip_Housing", "Strip_Housing", housing)
    boxes("decor_Strips", "Lamp_Emit", strips)
    light("Exit_Glow", "POINT", (xc, h_ + 0.4, -Z + 0.5), 25.0, (0.1, 1.0, 0.3), size=0.2)
    light("Fountain_Glow", "POINT", (0.0, 1.8, -5.5), 40.0, (0.4, 0.9, 1.0), size=0.3)


DRESS = {"rdwe_dining": dress_dining, "rdwe_hallway": dress_hallway, "rdwe_teal": dress_teal, "rdwe_teal2": dress_teal2, "rdwe_flooded": dress_flooded,
         "rdwe_trampoline": dress_trampoline, "rdwe_grocery": dress_grocery,
         "rdwe_repeating_room": dress_repeating_room, "rdwe_finale": dress_finale}


# ================================================================ build
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for d in (IMG, MATS, TILES, GEN):
        d.clear()


def build_all():
    global ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, LIGHTS, ALTL
    reset()
    sc = bpy.context.scene
    ART = bpy.data.collections.new("Art")
    sc.collection.children.link(ART)
    PROPS, ARCH = bpy.data.collections.new("Props"), bpy.data.collections.new("Arch")
    ART.children.link(PROPS)
    ART.children.link(ARCH)
    SKIN, DOORS, LAYOUT, LIGHTS, ALTL = (bpy.data.collections.new(n) for n in ("Skin", "Doors", "Layout", "Lights", "Lights_Alt"))
    for c in (SKIN, DOORS, LAYOUT, LIGHTS, ALTL):
        sc.collection.children.link(c)
    common_materials()
    room_materials()
    M = model()
    layout_from_model(M)
    build_skin()
    build_leaves(M)
    DRESS[SCENE]()
    w = sc.world or bpy.data.worlds.new("Room")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.01, 0.012, 0.02, 1)
    bg.inputs["Strength"].default_value = 0.0
    for ob in LAYOUT.objects:
        ob.hide_render = True
    used = {s.material.name for o in PROPS.objects for s in o.material_slots} | {s.material.name for o in DOORS.objects for s in o.material_slots}
    shell = {s.material.name for o in SKIN.objects for s in o.material_slots}
    clash = (used & shell) - NO_LIGHTMAP
    assert not clash, f"materials on both the shell page and the props page: {clash}"
    split_for_check()
    print(f"ART {SCENE}: {len(PROPS.objects)} props, {len(ARCH.objects)} arch boxes, {len(SKIN.objects)} skin meshes, {len(DOORS.objects)} leaves, "
          f"{len(LIGHTS.objects) + len(ALTL.objects)} lights")


def gbox(ob):
    g = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return [min(p.x for p in g), min(p.z for p in g), min(-p.y for p in g)], [max(p.x for p in g), max(p.z for p in g), max(-p.y for p in g)]


def split_for_check():
    """check_layout.py works one box per object: a prop made of separate parts whose box would fail its STRAY or CLEAR rule is cut into its loose
    parts (`<name>`, `<name>_p1`, ...). Only Art is cut; Export is merged by material from Art, so the GLB is the same either way."""
    import check_layout as cl
    allc = [{"min": gbox(o)[0], "max": gbox(o)[1]} for o in bpy.data.objects if o.name.startswith("COL_") and o.type == "MESH"]
    stand = [c for c in allc if cl._standing(c)]
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
        if ob.type != "MESH" or ob.name.startswith("decor_") or is_furniture({"name": ob.name}):
            continue                                       # furniture stands on its own collider: never cut (its parts would not cover it)
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
            PROPS.objects.link(bpy.data.objects.new(f"{name}_p{k}", me))
        done.append(f"{name} ({len(groups)})")
    print("SPLIT for the layout check:", done)


# ---------------------------------------------------------------- bake
NO_CULL = ("decor_Water", "decor_Painted_Sky", "decor_Window_Sky", "decor_Grid_", "decor_Photos", "decor_Curtains")


def cull_flush(bm, cols):
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
    cols = [{"min": b["min"], "max": b["max"]} for b in shell_boxes()]
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
    for extra in [u.name for u in uvs][1:]:               # one texture UV only (a text mesh joined into a leaf brings its own): UV1 must be the lightmap
        if extra != "lightmap":
            uvs.remove(uvs[extra])
    if "UVMap" not in uvs:
        first = next((u for u in uvs if u.name != "lightmap"), None)
        if first is None:
            first = uvs.new(name="UVMap")
        first.name = "UVMap"
    return uvs


def lightmap_uv(objs, page):
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
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / page, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    a3 = sum(world_area(o) for o in objs)
    au = sum(uv_area(o, "lightmap") for o in objs)
    dens = page * math.sqrt(au / a3)
    print(f"  page {page}: {a3:.1f} m2, {dens:.1f} px/m")
    return page, dens


def rect_uv(objs, S):
    """The shell's lightmap UVs packed by hand: every skin face is an axis-aligned rectangle (4 m at most), each its own pixel-aligned island with
    MARGIN_PX round it, shelf-packed at the highest density that fits the fixed page S. Deterministic."""
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
        bxs = []
        for i, (o, p, v0, e1, e2, w, h) in enumerate(rects):
            pw, ph = max(1, math.ceil(w * D)), max(1, math.ceil(h * D))
            rot = ph > pw
            if rot:
                pw, ph = ph, pw
            bxs.append((ph + 2 * m, pw + 2 * m, i, rot))
        bxs.sort(key=lambda b: (-b[0], -b[1]))
        x = y = rowh = 0
        place = {}
        for bh, bw, i, rot in bxs:
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
    lo, hi = 1.0, 400.0
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
            u, t = (b * ph, a * pw) if rot else (a * pw, b * ph)
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


def bake_visibility():
    for c, hide in (("Art", True), ("Skin", True), ("Doors", False), ("Export", False)):
        bpy.data.collections[c].hide_render = hide
    bpy.data.collections["Art"].hide_viewport = True
    bpy.data.collections["Skin"].hide_viewport = True
    for o in bpy.data.collections["Export"].objects:
        o.hide_render = o.data.materials[0].name in NO_BAKE_VIS


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


def set_light_set(name):
    """day (the first set) or alt: the dining room's green lamp off (its light, and its shade's emission)."""
    alt = name == "alt"
    for o in bpy.data.collections["Lights_Alt"].objects:
        o.hide_render = alt
    if SCENE == "rdwe_dining":
        m = bpy.data.materials.get("Lamp_Emit_Green")
        if m:
            bs = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
            bs.inputs["Emission Strength"].default_value = 0.0 if alt else 4.0


def stage_bake():
    import time
    exp = make_export_objects()
    bake_visibility()
    setup_cycles(SAMPLES, bake=True)
    skin_mats = {s.material.name for o in bpy.data.collections["Skin"].objects for s in o.material_slots}
    shell = [o for k, o in sorted(exp.items()) if o.data.materials[0].name in skin_mats and o.data.materials[0].name not in NO_LIGHTMAP]
    leaves = [o for o in bpy.data.collections["Doors"].objects if o.type == "MESH" and any(s.material.name not in NO_LIGHTMAP for s in o.material_slots)]
    props = [o for k, o in sorted(exp.items()) if o not in shell and o.data.materials[0].name not in NO_LIGHTMAP] + leaves
    big = [o for o in props if o.type == "MESH" and o not in leaves and o.data.materials[0].name in PAGE2.get(SCENE, set())]
    props = [o for o in props if o not in big]
    groups = (shell, props) + ((big,) if big else ())
    report = {}
    sets = ["day"] + (["alt"] if SCENE in ALT else [])
    metal = {}                                            # bake metals as if matte: the page multiplies the light by their colour, and a
    for m in bpy.data.materials:                          # metal's diffuse pass is black
        bs = next((nd for nd in m.node_tree.nodes if nd.type == "BSDF_PRINCIPLED"), None) if m.node_tree else None
        if bs and bs.inputs["Metallic"].default_value > 0:
            metal[m.name] = bs.inputs["Metallic"].default_value
            bs.inputs["Metallic"].default_value = 0.0
    for n, objs in enumerate(groups):
        print(f"lightmap {n}: {[o.name for o in objs]}")
        S, dens = rect_uv(objs, PAGES[SCENE][n]) if n == 0 else lightmap_uv(objs, PAGES[SCENE][n])
        mats = sorted({s.material for o in objs for s in o.material_slots}, key=lambda m: m.name)
        for ls in sets:
            t0 = time.time()
            set_light_set(ls)
            idx = n if ls == "day" else n + len(groups)
            img = bpy.data.images.new(f"LM_{idx}", S, S, alpha=False, float_buffer=True)
            img.colorspace_settings.name = "Non-Color"
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
            if ls == "alt":                                   # the alt set shares the day's white point, so the lamp going off reads as a dimming
                scale = report[n]["scale"]
            out = np.ones((S, S, 4), np.float32)
            out[..., :3] = srgb_encode(rgb_s / scale)
            png = bpy.data.images.new(f"LM_{idx}_png", S, S, alpha=False)
            png.colorspace_settings.name = "Non-Color"
            png.pixels.foreach_set(out.ravel())
            png.filepath_raw = str(work() / f"{SCENE}_{idx}.png")
            png.file_format = "PNG"
            png.save()
            key = "lightmap" if ls == "day" else "lightmap_night"
            for m in mats:
                if m.name in NO_LIGHTMAP:
                    continue
                m[key] = lm_url(SCENE, idx)
                m[key + "_intensity"] = round(math.pi * scale, 4)
            for m in mats:
                for nd in [nd for nd in m.node_tree.nodes if nd.name.startswith("BAKE_TARGET")]:
                    m.node_tree.nodes.remove(nd)
            raw = rgb.max(axis=2)
            report[idx] = {"set": ls, "size": S, "px_per_m": round(dens, 1), "scale": round(scale, 4), "knee": round(knee, 4),
                           "raw_p50_p90_p99_p995_max": [round(float(v), 3) for v in np.percentile(raw[raw > 1e-5], [50, 90, 99, 99.5, 100])],
                           "p50_p90_p99_p995_max": [round(float(v), 3) for v in pc], "samples": SAMPLES, "device": bpy.context.scene.cycles.device,
                           "seconds": round(time.time() - t0), "materials": [m.name for m in mats if m.name not in NO_LIGHTMAP]}
            print("  baked", idx, {k: v for k, v in report[idx].items() if k != "materials"})
            bpy.data.images.remove(img)
            bpy.data.images.remove(png)
    set_light_set("day")
    for name, v in metal.items():
        next(nd for nd in bpy.data.materials[name].node_tree.nodes if nd.type == "BSDF_PRINCIPLED").inputs["Metallic"].default_value = v
    stills_dir(SCENE).mkdir(parents=True, exist_ok=True)
    (stills_dir(SCENE) / "bake.json").write_text(json.dumps(report, indent=1))
    for c in ("Art", "Skin"):
        bpy.data.collections[c].hide_render = False
        bpy.data.collections[c].hide_viewport = False
    bpy.data.collections["Arch"].hide_render = True
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


# ---------------------------------------------------------------- privacy
KEEP_PROPS = {"lightmap", "lightmap_intensity", "lightmap_night", "lightmap_night_intensity"}
LAYOUT_PREFIX = ("DoorLeaf_", "Marker_", "Spot_", "SecCam_")


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


def save_blend():
    p = blend_path(SCENE)
    p.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(p))
    scrub_private()
    bpy.ops.wm.save_mainfile()


def load_scene_file():
    bpy.ops.wm.open_mainfile(filepath=str(blend_path(SCENE)))
    global ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, LIGHTS, ALTL
    c = bpy.data.collections
    ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, LIGHTS, ALTL = (c.get(n) for n in ("Art", "Props", "Arch", "Skin", "Doors", "Layout", "Lights", "Lights_Alt"))
    for m in bpy.data.materials:
        MATS[m.name] = m
    for c in model().cams:                                # SecCam_ properties (an older save scrubbed them): the layout's, from the model
        ob = bpy.data.objects.get(c["name"])
        if ob is not None:
            for k, v in c["props"].items():
                ob[k] = v


# ---------------------------------------------------------------- export
def caps():
    p = stills_dir(SCENE) / "caps.json"
    return json.loads(p.read_text()) if p.exists() else {}


def stage_export():
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    for c in ("Art", "Skin"):
        bpy.data.collections[c].hide_viewport = True
    leaves = [o for o in bpy.data.collections["Doors"].objects if o.type == "MESH"]
    stash = {o.name: {k: o[k] for k in o.keys()} for o in leaves}
    for o in leaves:
        for k in list(o.keys()):
            del o[k]
    cj = caps()
    f, fn = cj.get("factor", {}), cj.get("factor_night", cj.get("factor", {}))
    base = {}
    for m in bpy.data.materials:
        for key, ff in (("lightmap_intensity", f), ("lightmap_night_intensity", fn)):
            if key in m:
                base.setdefault(m.name, {})[key] = m[key]
                m[key] = round(m[key] * ff.get(m.name, 1.0), 4)
        if m.name in base:
            m["base"] = dict(base[m.name])                  # the uncapped intensities, for --caps (tools re-run caps without Blender)
    bpy.ops.object.select_all(action="DESELECT")
    for o in list(exp.objects) + leaves:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = work() / f"{SCENE}_raw.glb"
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_animations=False)
    for o in leaves:
        for k, v in stash[o.name].items():
            o[k] = v
    for m in bpy.data.materials:
        if m.name in base:
            for key, v in base[m.name].items():
                m[key] = v
            del m["base"]
    print("EXPORTED", raw, raw.stat().st_size, "caps", f)
    for c in ("Art", "Skin"):
        bpy.data.collections[c].hide_viewport = False
    exp.hide_viewport = exp.hide_render = True
    import export_scene
    export_scene.write(SCENE, world_json(SCENE))
    save_blend()


def stage_axes():
    import struct
    M = model()
    mk = next((e for e in M.empties if e["name"].startswith(("Marker_", "Arrive_"))))
    a = list(mk["pos"])
    me = bpy.data.meshes.new("axes_marker")
    bm = bmesh.new()
    cube(bm, (a[0] - 0.1, a[1], a[2] - 0.1), (a[0] + 0.1, a[1] + 0.2, a[2] + 0.1))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("axes_marker", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    path = work() / f"axes_{SCENE}.glb"
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_yup=True, export_apply=True, export_materials="NONE")
    b = path.read_bytes()
    j = json.loads(b[20:20 + struct.unpack("<I", b[12:16])[0]])
    acc = j["accessors"][j["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    off = j["nodes"][0].get("translation", [0, 0, 0])
    centre = [(acc["min"][i] + acc["max"][i]) / 2 + off[i] for i in range(3)]
    want = [a[0], a[1] + 0.1, a[2]]
    print(f"AXES glTF centre {tuple(round(v, 3) for v in centre)}, game point {tuple(want)} ({mk['name']})")
    assert all(abs(centre[i] - want[i]) < 1e-4 for i in range(3))
    print("AXES PASS: game (x, y, z) = Blender (x, -z, y) = glTF (x, y, z)")
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)


def stage_check():
    import check_layout
    for o in bpy.data.collections["Arch"].objects:
        o.hide_render = False
    code = check_layout.main(["--scene", SCENE, "--collection", "Art", "--links"])
    for o in bpy.data.collections["Arch"].objects:
        o.hide_render = True
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
    cam.clip_start, cam.clip_end = 0.03, 300
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


E = 1.55
SHOTS = {
    "rdwe_repeating_room": {"1_arrival": ((-3.5, E, 4.5), (6.9, 1.2, -3.0), 70), "2_wide": ((-5.4, 2.6, 5.4), (2.0, 0.6, -3.0), 78),
                            "3_detail": ((-1.2, 1.5, 2.2), (-5.0, 1.2, 0.6), 65)},
    "rdwe_finale": {"1_arrival": ((0.0, E, 19.6), (0.0, 1.3, -10.0), 75), "2_wide": ((-22.5, 4.0, 20.5), (2.0, 0.5, -4.0), 78),
                    "3_detail": ((8.2, 1.6, -0.8), (15.0, 1.25, -3.8), 65)},
    "rdwe_dining": {"1_arrival": ((0.0, E, 9.0), (0.0, 1.3, -6.0), 75), "2_wide": ((7.0, 3.2, 9.2), (-3.0, 0.8, -4.0), 78),
                    "3_detail": ((-4.4, 1.7, -6.4), (-5.0, 1.6, -10.0), 62)},
    "rdwe_hallway": {"1_arrival": ((-2.6, E, 0.0), (20.0, 2.2, 0.0), 70), "2_wide": ((38.0, 1.2 + E, 0.9), (4.0, 1.6, -0.3), 65),
                     "3_detail": ((19.0, 1.2 + E, 1.0), (21.0, 1.9, -1.6), 62)},
    "rdwe_teal": {"1_arrival": ((-3.0, E, 7.0), (0.6, 1.2, -9.0), 75), "2_wide": ((6.0, 3.0, 8.0), (-3.0, 0.8, -6.0), 78),
                  "3_detail": ((-0.5, 1.4, -3.5), (-2.8, 0.9, -8.0), 62)},
    "rdwe_teal2": {"1_arrival": ((-2.4, 1.0, 1.0), (1.4, 2.0, -11.0), 72), "2_wide": ((2.6, 3.6, 10.0), (-1.0, 1.4, -8.0), 70),
                   "3_detail": ((1.0, 1.6, -4.0), (4.0, 1.9, -6.0), 60)},
    "rdwe_flooded": {"1_arrival": ((2.0, E, 0.0), (40.0, 1.5, 0.0), 65), "2_wide": ((48.0, 2.2, -1.5), (4.0, 1.2, 0.8), 70),
                     "3_detail": ((8.0, 1.4, 0.8), (6.0, 0.9, -2.0), 62)},
    "rdwe_trampoline": {"1_arrival": ((0.0, E, 22.0), (0.0, 1.5, -20.0), 75), "2_wide": ((13.0, 7.0, 23.0), (-6.0, 0.0, -10.0), 75),
                        "3_detail": ((-10.0, 1.6, -3.0), (-13.1, 1.2, -6.0), 62)},
    "rdwe_grocery": {"1_arrival": ((-2.5, E, 21.6), (-2.5, 1.4, 10.0), 75), "2_wide": ((-22.0, 4.4, 22.0), (2.0, 0.5, -2.0), 75),
                     "3_detail": ((1.4, 1.6, 3.6), (0.0, 0.8, 0.0), 62)},
}
EXPOSURE = {}


def plan_box():
    cols = [b for b in shell_boxes() if not b["name"].startswith("Beyond_")]
    x0, x1 = min(c["min"][0] for c in cols) - 0.4, max(c["max"][0] for c in cols) + 0.4
    z0, z1 = min(c["min"][2] for c in cols) - 0.4, max(c["max"][2] for c in cols) + 0.4
    return x0, x1, z0, z1


def stage_render():
    import re
    sc = bpy.context.scene
    d = stills_dir(SCENE)
    d.mkdir(parents=True, exist_ok=True)
    scrub_private()
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
    for c, hide in (("Art", False), ("Skin", False), ("Doors", False), ("Lights", False), ("Lights_Alt", False)):
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
    sc.view_settings.exposure = arg("--exposure", EXPOSURE.get(SCENE, 0.0), float)
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    which = arg("--only", "all")
    for key, (loc, tgt, fov) in SHOTS[SCENE].items():
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
        span = max(x1 - x0, z1 - z0)
        cam = look_cam("plan", ((x0 + x1) / 2, 40.0, (z0 + z1) / 2), None, ortho=span)
        cam.rotation_euler = (0, 0, 0)
        if (z1 - z0) > (x1 - x0):
            cam.data.sensor_fit = "VERTICAL"
        sc.camera = cam
        hidden = []
        ceil = {"Ceiling_Dining", "Ceiling_Hall", "Ceiling_Teal", "Ceiling_White", "Truss_Deck", "Acoustic", "Ceiling_Repeat", "Acoustic_Finale"}
        for o in list(bpy.data.collections["Skin"].objects) + list(bpy.data.collections["Props"].objects) + list(bpy.data.collections["Doors"].objects):
            if o.type != "MESH":
                continue
            lowest = min((o.matrix_world @ v.co).z for v in o.data.vertices) if o.data.vertices else 0
            if o.name in ceil or (lowest > 2.6 and not o.name.startswith(("Step", "decor_Stringers", "Table"))) or o.name == "decor_Water":
                if not o.hide_render:
                    o.hide_render = True
                    hidden.append(o)
        arch = bpy.data.collections["Arch"]
        arch.hide_render = False
        floorish = re.compile(r".*(_Floor|_Ceiling|Landing|Under.*)(_\d+)?$")
        for o in arch.objects:
            o.hide_render = bool(floorish.match(o.name)) or o.name.startswith(("Step_", "Beyond_", "Well_Ceiling"))
        world = sc.world
        bg = world.node_tree.nodes["Background"]
        old = bg.inputs["Strength"].default_value
        bg.inputs["Color"].default_value = (1, 1, 1, 1)
        bg.inputs["Strength"].default_value = 0.8
        W = 1800
        if (z1 - z0) > (x1 - x0):
            Hh, W = 1800, max(300, int(round(1800 * (x1 - x0) / (z1 - z0))))
        else:
            Hh = max(300, int(round(W * (z1 - z0) / (x1 - x0))))
        sc.render.resolution_x, sc.render.resolution_y = W, Hh
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
        for o in arch.objects:
            o.hide_render = True
        arch.hide_render = True
        print("PLAN", path, W, Hh)


# ---------------------------------------------------------------- main
def main():
    global SCENE
    for sc in arg("--scenes", "rdwe_dining").split(","):
        SCENE = sc
        print(f"==== {sc} stage {STAGE}")
        if STAGE in ("art", "all", "preview"):
            build_all()
            save_blend()
        else:
            load_scene_file()
        if STAGE == "preview":
            import export_scene
            export_scene.write(SCENE, world_json(SCENE))
            stage_check()
            stage_render()
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
