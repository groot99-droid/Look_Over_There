"""Dresses and lights the 13 unique Secret Operations scenes (docs/BLENDER_AREAS.md, section 8, step 2) around the greybox's layout
(tools/blender/build_secretops_greybox.py), bakes a normal set and an alarm set, and exports world/<scene>.glb with world/<scene>.json.

    blender -b --factory-startup --python tools/blender/build_secretops_dress.py -- --scenes <id,id,...> --stage all [--samples 512] [--work <dir>]
    blender -b --factory-startup blender/scenes/<scene>.blend --python tools/blender/build_secretops_dress.py -- --scenes <scene> --stage bake|export|check|render
    python tools/blender/build_secretops_dress.py --skin <scene>       (no Blender) the seen faces of the shell, per material
    python tools/blender/build_secretops_dress.py --pack <scene> [--work <dir>]
                                                                       (no Blender) lightmaps -> WebP, the GLB's textures -> WebP, caps applied

Stages: art (the greybox's layout objects, rebuilt exactly; the shell as only the faces that look into the air; the dressing; the lights) ->
bake (two fixed lightmap PAGES per set, Cycles + OIDN, a highlight shoulder; `lightmap` the normal set, `lightmap_night` the alarm set) ->
export (the art-only GLB to the work folder; the layout through tools/blender/export_scene.py, the same file the greybox wrote) -> check
(tools/blender/check_layout.py) -> render (docs/renders/<scene>/1_arrival, 2_wide, 3_detail, 4_alarm.jpg and plan.jpg). `all` runs them in order.

The look is the laboratory's (world/laboratory.glb): a clean, cold government facility, white and grey under flat strip light, with a coloured
stripe at hand height. Each kind of space keeps the greybox's material family: labs white with a teal stripe, corridors pale with a blue (A) or
amber (B) stripe, checkpoints blue-grey with a red one, service spaces painted block over concrete, the Registrar's hall and its control room
green with the pink stripe. Slightly wrong: nobody sits at any desk, the planters hold plastic plants, the clocks have stopped, the hall hums.

What the page changes stays its own object, named as the greybox named it: Rack_<n> (one shared mesh), FloorPanel_<x>_<z> and
CeilingPanel_<x>_<z> (each its own mesh and lightmap island), every SecCam_<nn>_rig (one shared mesh, origin at its swivel, -Y the way it
looks), the DoorLeaf_* (one mesh per kind, origin at the hinge) and Chair_control. See bake_passes() for how the arena's removable parts are
baked so that a missing rack or panel leaves no shadow behind.

Light: `Lamp_Emit` (every ceiling fitting), `Emergency_Emit` (the red alarm beacons and wall lamps) and the screens (`Screen_Emit`,
`Screen_Window`) are their own emissive materials. The normal set bakes the lamps on and the beacons off; the alarm set the beacons on and the
lamps off; the screens and the green exit signs (`Sign_Emit`) are on in both.

Coordinates are GAME coordinates (metres, y up, north = -z), as in the greybox; Blender (x, y, z) is game (x, -z, y).
"""
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import build_secretops_greybox as GB  # noqa: E402

try:
    import bpy
    import bmesh
    from mathutils import Matrix, Vector
except ImportError:
    bpy = None
import numpy as np  # noqa: E402
import functools  # noqa: E402
print = functools.partial(print, flush=True)  # noqa: A001 (the box log shows progress as it goes)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 512, int)
DEVICE = arg("--device", "auto")
MARGIN_PX = 8
TEXDIR = ROOT / "blender/textures"
SCENE = None
S = None              # the greybox model of SCENE

# fixed lightmap pages per scene: [shell, props]; the same two pages carry the normal set (maps 0, 1) and the alarm set (maps 2, 3)
PAGES = {"registrar_hall": [2048, 2048], "control_room": [1536, 1536], "checkpoint_1": [2048, 1536], "checkpoint_2": [2048, 1536],
         "checkpoint_3": [2048, 1536], "corridors_a": [2048, 2048], "corridors_b": [2048, 1536], "labs_a": [2048, 2048], "labs_b": [2048, 2048],
         "breaker_room": [1536, 1536], "service_entry": [2048, 2048], "b2_entry": [2048, 1536], "hidden_entry": [1024, 1024]}
SETS = ("normal", "alarm")
CURVE_C = 1.2          # texel = G L / (C + G L), intensity = pi C: the page shows albedo x G L, rolling off toward albedo x C (never clips)
TARGET = {"normal": 0.34, "alarm": 0.26}     # G is set so the median wall texel shows this much light (x the wall's albedo)
LM_SCALE = {"Beam_Steel": 0.55}   # texel density on page 1 relative to the rest (far, dark surfaces get less)
FILL_SIDE = 0.4        # a floor or ceiling panel's edges show this fraction of the median panel light (see bake_passes)


def work():
    p = Path(arg("--work", str(Path(os.environ.get("TEMP", tempfile.gettempdir())) / "farway_secretops")))
    if not p.is_absolute():
        p = ROOT / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def blend_path(sc):
    return ROOT / f"blender/scenes/{sc}.blend"


def stills_dir(sc):
    return ROOT / f"docs/renders/{sc}"


def lm_url(sc, n):
    return f"world/lightmaps/{sc}_{n}.webp"


# ================================================================ the shell, pure Python: which faces of the greybox's boxes can be seen
SHELL = ("Floor_", "Wall_", "Ceiling_", "Lintel_", "Sill_", "Pool_", "Pit_", "Step_")
SEPARATE = ("Rack_", "FloorPanel_", "CeilingPanel_", "Chair_control")
FRONT = 0.004
FLOOR_MAT = {"concrete": "Floor_Concrete", "service": "Floor_Concrete", "steel": "Floor_Steel", "tile": "Floor_Tile", "lab_floor": "Floor_Lab",
             "lab": "Floor_Lab", "corridor_floor": "Floor_Corridor", "corridor": "Floor_Corridor", "checkpoint_floor": "Floor_Checkpoint",
             "checkpoint": "Floor_Checkpoint", "server_floor": "Floor_Server", "server_green": "Floor_Server", "cell": "Floor_Cell", "pit": "Pit_Concrete"}
WALL_MAT = {"service": "Wall_Service", "concrete": "Wall_Service", "steel": "Wall_Steel", "tile": "Wall_Tile", "lab": "Wall_Lab", "corridor": "Wall_Corridor",
            "checkpoint": "Wall_Checkpoint", "server_green": "Wall_Green", "cell": "Wall_Cell", "pit": "Pit_Concrete"}
CEIL_MAT = {"service": "Ceiling_Concrete", "concrete": "Ceiling_Concrete", "steel": "Wall_Steel", "cell": "Ceiling_Concrete", "server_green": "Ceiling_Server"}
STRIPE = {"lab": "Stripe_Teal", "corridor": ("Stripe_Blue", "Stripe_Amber"), "checkpoint": "Stripe_Red", "server_green": "Stripe_Pink"}


def is_shell(name):
    return name.startswith(SHELL)


def cols_of(M):
    return [b for b in M.boxes if b["col"]]


def air_boxes(M):
    """[(min, max, ('space', k) | ('open', o) | ('pit', mat))]: the open volumes a walker or the camera is in."""
    A = []
    for k, s in enumerate(M.spaces):
        A.append(((s["x0"], 0.0 if s["floor"] else -10.0, s["z0"]), (s["x1"], s["h"], s["z1"]), ("space", k)))
    for o in M.openings:
        A.append(((o["x0"], o["sill"], o["z0"]), (o["x1"], o["top"], o["z1"]), ("open", None)))
    for r in M.pits:
        A.append(((r[0], -10.0, r[2]), (r[1], 0.0, r[3]), ("pit", "tile" if M.id == "service_entry" else "pit")))
    return A


def _in(p, mn, mx, e=1e-7):
    return all(mn[i] - e <= p[i] <= mx[i] + e for i in range(3))


def _strict(p, mn, mx, e=1e-6):
    return all(mn[i] + e < p[i] < mx[i] - e for i in range(3))


def skin(M, max_len=6.0):
    """Every face of a shell collider that looks into the air, as rectangles: [{box, axis, side, c, u: (a, b), v: (a, b), mat, kind, space}].
    axis: the normal's axis (0 x, 1 y, 2 z), side its sign; u, v the other two axes in order. A face is cut wherever another box or the edge of
    the air meets it, and kept where the point FRONT in front of it is in the air and inside no collider."""
    cols = cols_of(M)
    air = air_boxes(M)
    out = []
    for B in cols:
        if not is_shell(B["name"]):
            continue
        for a in range(3):
            ua, va = [i for i in range(3) if i != a]
            for side in (-1, 1):
                c = B["max"][a] if side > 0 else B["min"][a]
                fc = c + side * FRONT
                lo, hi = (B["min"][ua], B["min"][va]), (B["max"][ua], B["max"][va])
                bu, bv = {lo[0], hi[0]}, {lo[1], hi[1]}
                near, nair = [], []
                for X, is_air in [((x["min"], x["max"]), False) for x in cols if x is not B] + [((x[0], x[1]), True) for x in air]:
                    mn, mx = X
                    if mn[a] - 1e-6 <= fc <= mx[a] + 1e-6 and mn[ua] < hi[0] and mx[ua] > lo[0] and mn[va] < hi[1] and mx[va] > lo[1]:
                        (nair if is_air else near).append(X)
                        for v in (mn[ua], mx[ua]):
                            if lo[0] < v < hi[0]:
                                bu.add(v)
                        for v in (mn[va], mx[va]):
                            if lo[1] < v < hi[1]:
                                bv.add(v)
                bu, bv = sorted(bu), sorted(bv)
                cells = {}
                for i in range(len(bu) - 1):
                    for j in range(len(bv) - 1):
                        p = [0.0, 0.0, 0.0]
                        p[a], p[ua], p[va] = fc, (bu[i] + bu[i + 1]) / 2, (bv[j] + bv[j + 1]) / 2
                        if any(_strict(p, X[0], X[1]) for X in near):
                            continue
                        where = next((x[2] for x in air if _in(p, x[0], x[1])), None)
                        if where is None:
                            continue
                        cells[(i, j)] = face_key(M, B, a, side, where)
                for i0, i1, j0, j1, key in GB.grid_rects(cells):
                    u0, u1, v0, v1 = bu[i0], bu[i1], bv[j0], bv[j1]
                    nu, nv = max(1, math.ceil((u1 - u0) / max_len - 1e-9)), max(1, math.ceil((v1 - v0) / max_len - 1e-9))
                    for m in range(nu):
                        for n in range(nv):
                            out.append({"box": B["name"], "axis": a, "side": side, "c": c,
                                        "u": (u0 + (u1 - u0) * m / nu, u0 + (u1 - u0) * (m + 1) / nu),
                                        "v": (v0 + (v1 - v0) * n / nv, v0 + (v1 - v0) * (n + 1) / nv), "mat": key[0], "kind": key[1], "space": key[2]})
    return out


def face_key(M, B, a, side, where):
    """(material, kind, space index or -1) of a seen face."""
    k = where[1] if where[0] == "space" else -1
    s = M.spaces[k] if k >= 0 else None
    if B["name"].startswith(("Step_", "Pool_", "Pit_")) or where[0] == "pit":
        m = where[1] if where[0] == "pit" and not B["name"].startswith(("Step_", "Pool_", "Pit_")) else B["mat"]
        if a == 1 and side > 0:
            return (FLOOR_MAT.get(m, "Floor_Concrete"), "floor", k)
        return (WALL_MAT.get(m, FLOOR_MAT.get(m, "Wall_Service")), "wall", k)
    if a == 1 and side > 0:
        return (FLOOR_MAT[s["fmat"]] if s else FLOOR_MAT.get(B["mat"], "Floor_Concrete"), "floor", k)
    if a == 1 and side < 0:
        if B["name"].startswith("Ceiling_") and s:
            return (CEIL_MAT.get(s["wmat"], "Ceiling_Tile"), "ceiling", k)
        return (WALL_MAT.get(B["mat"], "Wall_Service"), "soffit", k)
    wm = s["wmat"] if s else B["mat"]
    return (WALL_MAT.get(wm, FLOOR_MAT.get(wm, "Wall_Service")), "wall", k)


def edge_doors(M):
    """[(door name, axis of its wall's normal, wall plane c, along centre, inward sign)] for every door leaf (edge links and openings)."""
    out = []
    for d in M.doors:
        th = d["yaw"]
        run = (math.cos(th), -math.sin(th))           # game (x, z) of the leaf's local +x
        w = d["props"]["width"]
        cx, cz = d["hinge"][0] + run[0] * w / 2, d["hinge"][2] + run[1] * w / 2
        if abs(run[0]) > 0.5:                          # the leaf runs along x: its wall's normal is z
            out.append((d["name"], 2, d["hinge"][2], cx))
        else:
            out.append((d["name"], 0, d["hinge"][0], cz))
    return out


# ================================================================ Blender: helpers
def G(x, y, z):
    return Vector((x, -z, y))


def Bv(p):
    return Vector((p[0], -p[2], p[1]))


def srgb_lin(c):
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


def C3(*rgb):
    return np.array(rgb, float) / 255.0


def gen_tile():
    """White glazed ceramic tiles, 0.15 m, grey grout: 512 px = 1.2 m."""
    H = W = 512
    rng = np.random.default_rng(11)
    y, x = np.mgrid[0:H, 0:W]
    cell = W / 8
    gx, gy = np.mod(x, cell), np.mod(y, cell)
    grout = (np.minimum(gx, cell - gx) < 2.2) | (np.minimum(gy, cell - gy) < 2.2)
    per = rng.normal(0, 0.018, (8, 8))[(y // cell).astype(int) % 8, (x // cell).astype(int) % 8]
    n = vnoise(H, W, rng, 4, 8) - 0.5
    base = C3(232, 236, 236)[None, None] * (1 + per + n * 0.04)[..., None]
    return np.clip(np.where(grout[..., None], C3(168, 172, 170)[None, None], base), 0, 1)


def gen_server_floor():
    """Raised-floor tiles, 0.6 m, dark green-grey, every other one perforated: 512 px = 1.2 m."""
    H = W = 512
    rng = np.random.default_rng(12)
    y, x = np.mgrid[0:H, 0:W]
    cell = W / 2
    gx, gy = np.mod(x, cell), np.mod(y, cell)
    edge = np.minimum(np.minimum(gx, cell - gx), np.minimum(gy, cell - gy))
    tid = ((x // cell).astype(int) + (y // cell).astype(int)) % 2
    holes = (np.hypot(np.mod(gx, 16) - 8, np.mod(gy, 16) - 8) < 3.0) & (edge > 14) & (tid == 1)
    n = vnoise(H, W, rng, 4, 6) - 0.5
    base = C3(112, 138, 122)[None, None] * (1 + n * 0.12)[..., None]
    out = np.where((edge < 2.5)[..., None], C3(30, 38, 34)[None, None], base)
    out = np.where(((edge >= 2.5) & (edge < 5))[..., None], base * 1.18, out)
    return np.clip(np.where(holes[..., None], C3(22, 28, 25)[None, None], out), 0, 1)


def gen_panel(variant):
    """An arena floor panel, 2 m square (512 px): four by four 0.5 m perforated tiles, a steel rim; two greens (the checker)."""
    H = W = 512
    rng = np.random.default_rng(13 + variant)
    y, x = np.mgrid[0:H, 0:W]
    cell = W / 4
    gx, gy = np.mod(x, cell), np.mod(y, cell)
    edge = np.minimum(np.minimum(gx, cell - gx), np.minimum(gy, cell - gy))
    rim = np.minimum(np.minimum(x, W - 1 - x), np.minimum(y, H - 1 - y))
    holes = (np.hypot(np.mod(gx, 12) - 6, np.mod(gy, 12) - 6) < 2.2) & (edge > 10)
    n = vnoise(H, W, rng, 4, 6) - 0.5
    tone = C3(64, 112, 82) if variant == 0 else C3(48, 88, 64)
    base = tone[None, None] * (1 + n * 0.1)[..., None]
    out = np.where((edge < 2)[..., None], C3(26, 34, 30)[None, None], base)
    out = np.where(holes[..., None], out * 0.45, out)
    out = np.where((rim < 7)[..., None], C3(120, 128, 124)[None, None] * (1 + n[..., None] * 0.1), out)
    return np.clip(out, 0, 1)


def gen_ceiling_panel():
    """The arena's ceiling: 4 m panels (512 px) of dark acoustic tiles, 1 m, with a grey grid."""
    H = W = 512
    rng = np.random.default_rng(14)
    y, x = np.mgrid[0:H, 0:W]
    cell = W / 4
    gx, gy = np.mod(x, cell), np.mod(y, cell)
    edge = np.minimum(np.minimum(gx, cell - gx), np.minimum(gy, cell - gy))
    n = vnoise(H, W, rng, 5, 8) - 0.5
    base = C3(62, 72, 66)[None, None] * (1 + n * 0.18)[..., None]
    return np.clip(np.where((edge < 2.5)[..., None], C3(120, 126, 122)[None, None], base), 0, 1)


def gen_tread():
    """Diamond tread plate, 0.6 m (256 px)."""
    H = W = 256
    rng = np.random.default_rng(15)
    y, x = np.mgrid[0:H, 0:W].astype(float)
    p = 32.0
    a = np.mod(x + y * 0.5, p) - p / 2
    b = np.mod(y, p / 2) - p / 4
    lug = (np.abs(a) < 9) & (np.abs(b) < 2.2)
    a2 = np.mod(x - y * 0.5 + p / 2, p) - p / 2
    b2 = np.mod(y + p / 4, p / 2) - p / 4
    lug |= (np.abs(a2) < 9) & (np.abs(b2) < 2.2)
    n = vnoise(H, W, rng, 5, 4)
    base = C3(132, 136, 140)[None, None] * (0.85 + 0.3 * n)[..., None]
    return np.clip(np.where(lug[..., None], base * 1.25, base), 0, 1)


def gen_brushed():
    H = W = 256
    rng = np.random.default_rng(16)
    streak = rng.normal(0, 1, (1, W)).repeat(H, 0)
    streak = (streak + np.roll(streak, 1, 1) + np.roll(streak, 2, 1)) / 3
    n = vnoise(H, W, rng, 4, 4)
    v = 0.62 + 0.04 * streak + 0.06 * (n - 0.5)
    return np.clip(np.stack([v * 0.98, v, v * 1.02], -1), 0, 1)


def gen_hazard():
    """Yellow and black diagonal stripes: 256 x 64 px = 0.8 m x 0.2 m."""
    H, W = 64, 256
    y, x = np.mgrid[0:H, 0:W]
    s = np.mod(x + y, 64) < 32
    return np.where(s[..., None], C3(222, 178, 20)[None, None], C3(22, 22, 20)[None, None])


def gen_rack():
    """A server rack's atlas: left half its front (1.2 m x 2.4 m: a dark steel door with a perforated window over 1U servers and their LEDs),
    right half its sides and top (plain dark steel with a vent strip)."""
    H, W = 512, 512
    rng = np.random.default_rng(17)
    y, x = np.mgrid[0:H, 0:W]
    out = np.zeros((H, W, 3)) + C3(58, 64, 64)
    n = vnoise(H, W, rng, 4, 8)
    out *= (0.85 + 0.3 * n)[..., None]
    fx, fy = x / (W / 2), 1 - y / H                       # the front: u 0..1 over its width, v 0..1 bottom to top
    front = x < W / 2
    win = front & (fx > 0.08) & (fx < 0.92) & (fy > 0.06) & (fy < 0.94)
    unit = np.floor(fy * 42).astype(int)
    slot = np.mod(fy * 42, 1.0)
    srv = win & (slot > 0.12)
    out[srv] = C3(78, 86, 86)
    out[win & (slot <= 0.12)] = C3(10, 12, 12)
    perf = srv & (np.hypot(np.mod(x, 6) - 3, np.mod(y, 6) - 3) < 1.2) & (fx < 0.62)
    out[perf] = C3(14, 16, 16)
    rng2 = np.random.default_rng(18)
    on = rng2.random(64) < 0.7
    led_x = 0.70 + 0.05 * np.arange(4)
    for i, lx in enumerate(led_x):
        dot = srv & (np.abs(fx - lx) < 0.012) & (np.abs(slot - 0.55) < 0.22)
        colr = [C3(60, 255, 120), C3(60, 255, 120), C3(255, 176, 40), C3(80, 160, 255)][i]
        lit = on[(unit + i * 7) % 64]
        out[dot & lit] = colr
        out[dot & ~lit] = C3(30, 50, 36)
    out[front & ((fx < 0.03) | (fx > 0.97))] = C3(16, 18, 18)
    side = ~front
    vent = side & (np.abs(np.mod((x - W / 2) / (W / 2), 1.0) - 0.5) < 0.35) & (np.mod(y, 10) < 3) & (y < H * 0.2)
    out[vent] = C3(10, 12, 12)
    return np.clip(out, 0, 1)


def gen_cam():
    """The camera's atlas, 64 px: white body (0..0.5), dark grey bracket (0.5..1, top), the black lens and the red light (bottom right)."""
    out = np.zeros((64, 64, 3))
    out[:, :32] = C3(226, 228, 226)
    out[:32, 32:] = C3(60, 62, 64)
    out[32:, 32:48] = C3(8, 9, 10)
    out[32:, 48:] = C3(255, 40, 30)
    return out


CAM_UV = {"body": (0.25, 0.5), "bracket": (0.75, 0.75), "lens": (0.625, 0.25), "led": (0.875, 0.25)}


def gen_screens():
    """The screens' atlas, 1024 x 512, four by two cells: green text, two camera feeds, a waveform, the base's map, a grid of feeds, a column
    of names being filed, and the Registrar's eye."""
    H, W = 512, 1024
    rng = np.random.default_rng(19)
    out = np.zeros((H, W, 3)) + C3(4, 10, 8)
    cw, ch = W // 4, H // 2
    y, x = np.mgrid[0:ch, 0:cw]

    def put(ci, cj, img):
        out[cj * ch:(cj + 1) * ch, ci * cw:(ci + 1) * cw] = img

    def text_lines(seed, colr, dense=0.6):
        r = np.random.default_rng(seed)
        im = np.zeros((ch, cw, 3)) + C3(4, 12, 8)
        for row in range(4, ch - 8, 10):
            ln = int(r.integers(20, cw - 20))
            x0 = 10
            while x0 < ln:
                wl = int(r.integers(6, 30))
                if r.random() < dense:
                    im[row:row + 5, x0:min(x0 + wl, cw - 6)] = colr
                x0 += wl + 5
        return im

    def feed(seed):
        r = np.random.default_rng(seed)
        im = np.zeros((ch, cw, 3))
        g = 0.15 + 0.5 * (1 - np.abs(x - cw / 2) / (cw / 2)) * (y / ch)
        im += (g * 0.6)[..., None] * C3(200, 215, 210)[None, None]
        vx = cw / 2 + r.normal(0, 10)
        corridor = (np.abs(x - vx) < (y / ch) * cw * 0.45 + 8) & (y > ch * 0.25)
        im[corridor] *= 1.6
        im += r.normal(0, 0.03, im.shape)
        im[4:12, 6:60] = C3(240, 240, 240)
        im[6:10, cw - 20:cw - 10] = C3(255, 40, 30)
        return np.clip(im, 0, 1)

    put(0, 0, text_lines(1, C3(80, 255, 140)))
    put(1, 0, feed(2))
    wave = np.zeros((ch, cw, 3)) + C3(4, 10, 14)
    for k, colr in enumerate((C3(80, 200, 255), C3(255, 120, 200))):
        yy = ch / 2 + (ch / 4) * np.sin(x[0] / (12 + 9 * k) + k) * np.sin(x[0] / 47.0)
        for i in range(cw):
            wave[int(yy[i]) - 1:int(yy[i]) + 2, i] = colr
    wave[(np.mod(x, 32) == 0) | (np.mod(y, 32) == 0)] = C3(20, 40, 40)
    put(2, 0, wave)
    mp = np.zeros((ch, cw, 3)) + C3(6, 14, 20)
    rr = np.random.default_rng(4)
    for _ in range(14):
        a, b = int(rr.integers(10, cw - 60)), int(rr.integers(10, ch - 40))
        w, h = int(rr.integers(20, 60)), int(rr.integers(14, 40))
        mp[b:b + h, a:a + w] = C3(30, 90, 110)
        mp[b + 2:b + h - 2, a + 2:a + w - 2] = C3(10, 30, 40)
    mp[int(ch * 0.6):int(ch * 0.6) + 6, int(cw * 0.7):int(cw * 0.7) + 6] = C3(255, 60, 60)
    put(3, 0, mp)
    grid = np.zeros((ch, cw, 3))
    for i in range(3):
        for j in range(3):
            f = feed(10 + i * 3 + j)
            sub = f[::3, ::3][:ch // 3 - 2, :cw // 3 - 2]
            grid[j * (ch // 3) + 1:j * (ch // 3) + 1 + sub.shape[0], i * (cw // 3) + 1:i * (cw // 3) + 1 + sub.shape[1]] = sub
    put(0, 1, grid)
    put(1, 1, text_lines(6, C3(230, 230, 220), 0.8) * np.where((np.mod(y, 20) < 10)[..., None], 1.0, 0.7))
    put(2, 1, feed(7))
    eye = np.zeros((ch, cw, 3)) + C3(2, 6, 4)
    r = np.hypot((x - cw / 2) / 1.6, y - ch / 2)
    eye[(r < 70) & (r > 62)] = C3(255, 92, 158)
    eye[r < 22] = C3(255, 92, 158)
    eye[r < 9] = C3(10, 10, 10)
    eye[(np.abs(y - ch / 2) < 2) & (r < 110)] = C3(80, 255, 140)
    put(3, 1, eye)
    return np.clip(out, 0, 1)


def gen_window():
    """The control room seen through its window from the arena: a dark teal room, rows of lit monitors, one chair."""
    H, W = 256, 1024
    y, x = np.mgrid[0:H, 0:W]
    out = np.zeros((H, W, 3)) + C3(6, 22, 20) * (0.6 + 0.6 * (y / H))[..., None]
    for row in range(2):
        for i in range(12):
            x0, y0 = 60 + i * 76, 40 + row * 60
            out[y0:y0 + 44, x0:x0 + 64] = C3(60, 170, 140) if (i + row) % 3 else C3(200, 90, 150)
    out[160:240, 480:540] = C3(8, 10, 10)
    out[150:175, 470:550] = C3(8, 10, 10)
    return np.clip(out, 0, 1)


def gen_paper():
    """A notice board's sheets and a clock face: 256 px."""
    H = W = 256
    out = np.zeros((H, W, 3)) + C3(120, 92, 60)
    rng = np.random.default_rng(20)
    for k in range(5):
        x0, y0 = int(rng.integers(8, 150)), int(rng.integers(8, 140))
        w, h = int(rng.integers(60, 100)), int(rng.integers(80, 110))
        out[y0:y0 + h, x0:x0 + w] = C3(236, 236, 228)
        for r in range(y0 + 10, y0 + h - 6, 7):
            out[r:r + 2, x0 + 6:x0 + int(w * rng.uniform(0.5, 0.9))] = C3(60, 60, 70)
        out[y0 + 2:y0 + 6, x0 + w // 2 - 2:x0 + w // 2 + 2] = C3(200, 30, 30)
    return np.clip(out, 0, 1)


def gen_clock():
    H = W = 128
    y, x = np.mgrid[0:H, 0:W]
    r = np.hypot(x - 64, y - 64)
    out = np.zeros((H, W, 3)) + C3(30, 30, 30)
    out[r < 60] = C3(240, 240, 236)
    a = np.arctan2(y - 64, x - 64)
    for k in range(12):
        t = k * math.pi / 6
        m = (np.abs(((a - t + math.pi) % (2 * math.pi)) - math.pi) < 0.05) & (r > 48) & (r < 57)
        out[m] = C3(20, 20, 20)
    # stopped at 3:33 (the hands)
    for ang, ln, wd in ((math.radians(-90 + 3.55 * 30), 30, 3.2), (math.radians(-90 + 33 * 6), 46, 2.0)):
        px, py = x - 64, y - 64
        t = px * math.cos(ang) + py * math.sin(ang)
        d = np.abs(-px * math.sin(ang) + py * math.cos(ang))
        out[(t > 0) & (t < ln) & (d < wd)] = C3(15, 15, 15)
    return out


GEN = {}


def mk_image(name, arr):
    h, w = arr.shape[:2]
    im = bpy.data.images.new(name, w, h, alpha=False)
    im.colorspace_settings.name = "sRGB"
    px = np.ones((h, w, 4), np.float32)
    px[..., :3] = arr[::-1]                               # numpy rows top-down -> Blender bottom-up
    im.pixels.foreach_set(px.ravel())
    im.filepath_raw = f"//generated/{name}.png"
    im.file_format = "PNG"
    im.pack()
    GEN[name] = im
    return im


# ---------------------------------------------------------------- materials
IMG, MATS, TILES = {}, {}, {}
NO_LIGHTMAP = {"Lamp_Emit", "Emergency_Emit", "Screen_Emit", "Screen_Window", "Sign_Emit", "Glass_Clear", "Water"}
VINYL, PAINT, CTILE, CONC, PLY = ("laboratory/floor_vinyl_diff.jpg", "laboratory/wall_paint_diff.jpg", "laboratory/ceiling_tile_diff.jpg",
                                  "kit/concrete_floor_02_diff_1k.jpg", "kit/plywood_diff_1k.jpg")


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


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, tex=None, img=None, tint=None, emit=None, emit_img=False, alpha=None, tile=1.0):
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
    n = None
    if tex or img:
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "UVMap"
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = img or image(tex)
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        if emit_img:
            bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
            nt.links.new(n.outputs["Color"], bsdf.inputs["Emission Color"])
        elif tint:
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
        if not emit_img:
            bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    if alpha is not None:
        bsdf.inputs["Alpha"].default_value = alpha
        set_blend(m)
    TILES[name] = tile
    MATS[name] = m
    m["emit_on"] = emit[1] if emit else 0.0
    return m


def make_materials():
    g = {k: mk_image(k, f()) for k, f in (("gen_tile", gen_tile), ("gen_server_floor", gen_server_floor), ("gen_panel_a", lambda: gen_panel(0)),
                                          ("gen_panel_b", lambda: gen_panel(1)), ("gen_ceiling_panel", gen_ceiling_panel), ("gen_tread", gen_tread),
                                          ("gen_brushed", gen_brushed), ("gen_hazard", gen_hazard), ("gen_rack", gen_rack), ("gen_cam", gen_cam),
                                          ("gen_screens", gen_screens), ("gen_window", gen_window), ("gen_paper", gen_paper), ("gen_clock", gen_clock))}
    L = srgb_lin
    # the shell (lightmap page 0)
    material("Floor_Lab", tex=VINYL, tint=(0.97, 0.98, 0.99), rough=0.55, tile=2.4)
    material("Floor_Corridor", tex=VINYL, tint=L((0.80, 0.83, 0.82)), rough=0.5, tile=2.4)
    material("Floor_Checkpoint", tex=VINYL, tint=L((0.62, 0.67, 0.74)), rough=0.5, tile=2.4)
    material("Floor_Concrete", tex=CONC, tint=(0.95, 0.95, 0.95), rough=0.85, tile=3.0)
    material("Floor_Cell", tex=CONC, tint=(0.78, 0.76, 0.72), rough=0.9, tile=2.0)
    material("Floor_Tile", img=g["gen_tile"], rough=0.25, tile=1.2)
    material("Floor_Server", img=g["gen_server_floor"], rough=0.5, tile=1.2)
    material("Floor_Steel", img=g["gen_tread"], rough=0.4, metal=0.6, tile=0.6)
    material("Wall_Lab", tex=PAINT, tint=(0.97, 0.98, 0.98), tile=3.0)
    material("Wall_Corridor", tex=PAINT, tint=L((0.93, 0.92, 0.88)), tile=3.0)
    material("Wall_Checkpoint", tex=PAINT, tint=L((0.80, 0.85, 0.90)), tile=3.0)
    material("Wall_Service", tex=PAINT, tint=L((0.72, 0.76, 0.78)), tile=3.0)
    material("Wall_Green", tex=PAINT, tint=L((0.42, 0.66, 0.50)), tile=3.0)
    material("Wall_Cell", tex=CONC, tint=(0.80, 0.78, 0.74), rough=0.9, tile=2.0)
    material("Wall_Tile", img=g["gen_tile"], rough=0.25, tile=1.2)
    material("Wall_Steel", img=g["gen_brushed"], rough=0.35, metal=0.7, tile=1.0)
    material("Pit_Concrete", tex=CONC, tint=(0.42, 0.44, 0.43), rough=0.95, tile=3.0)
    material("Ceiling_Tile", tex=CTILE, tint=(0.96, 0.96, 0.96), tile=0.6)
    material("Ceiling_Concrete", tex=CONC, tint=(0.88, 0.88, 0.88), rough=0.9, tile=3.0)
    material("Ceiling_Server", img=g["gen_ceiling_panel"], tile=4.0)
    # the dressing (lightmap page 1)
    for nm, c in (("Skirting", (0.20, 0.21, 0.22)), ("Stripe_Teal", (0.05, 0.52, 0.54)), ("Stripe_Blue", (0.12, 0.28, 0.62)),
                  ("Stripe_Amber", (0.86, 0.52, 0.10)), ("Stripe_Red", (0.70, 0.10, 0.08)), ("Stripe_Pink", (0.97, 0.36, 0.62)),
                  ("Door_Frame", (0.52, 0.55, 0.58)), ("Door_Steel", (0.68, 0.70, 0.72)), ("Door_Keycard", (0.62, 0.66, 0.70)),
                  ("Paint_Grey", (0.48, 0.50, 0.52)), ("Paint_Yellow", (0.86, 0.66, 0.06)), ("Paint_Orange", (0.86, 0.36, 0.06)),
                  ("Paint_Dark", (0.12, 0.13, 0.14)), ("Plastic_White", (0.86, 0.87, 0.87)), ("Plastic_Black", (0.035, 0.035, 0.04)),
                  ("Plastic_Grey", (0.52, 0.54, 0.55)), ("Laminate", (0.72, 0.72, 0.70)), ("Bench_Top", (0.09, 0.10, 0.10)),
                  ("Cardboard", (0.58, 0.44, 0.28)), ("Locker_Paint", (0.40, 0.50, 0.47)), ("Liquid", (0.12, 0.42, 0.28)),
                  ("Specimen", (0.05, 0.06, 0.05)), ("Fabric", (0.13, 0.14, 0.16)), ("Mattress", (0.58, 0.60, 0.62)), ("Rubber", (0.03, 0.03, 0.03)),
                  ("Plant", (0.12, 0.36, 0.16)), ("Soil", (0.08, 0.06, 0.05)), ("Sign_Plate", (0.90, 0.90, 0.88)), ("Lamp_Housing", (0.80, 0.81, 0.82)),
                  ("Cable", (0.04, 0.04, 0.045)), ("Trafo_Paint", (0.36, 0.40, 0.38)), ("Breaker_Paint", (0.56, 0.58, 0.60)),
                  ("Cell_Dark", (0.03, 0.03, 0.035))):
        material(nm, color=L(c) if nm not in () else c, rough=0.6)
    material("Steel", img=g["gen_brushed"], rough=0.35, metal=0.7, tile=0.8)
    material("Steel_Dark", color=L((0.30, 0.31, 0.32)), rough=0.45, metal=0.6)
    material("Beam_Steel", color=L((0.30, 0.32, 0.31)), rough=0.5, metal=0.5)
    material("Hazard", img=g["gen_hazard"], tile=0.8)
    material("Wood_Crate", tex=PLY, tint=(0.95, 0.9, 0.85), tile=1.2)
    material("Concrete_Prop", tex=CONC, tint=(1.0, 1.0, 0.98), rough=0.7, tile=4.0)
    material("Pillar_Paint", tex=PAINT, tint=L((0.90, 0.90, 0.88)), tile=3.0)
    material("Server_Body", img=g["gen_rack"], rough=0.5)
    material("Cam_Body", img=g["gen_cam"], rough=0.4)
    material("Panel_A", img=g["gen_panel_a"], rough=0.5, tile=2.0)
    material("Panel_B", img=g["gen_panel_b"], rough=0.5, tile=2.0)
    material("Ceiling_Panel", img=g["gen_ceiling_panel"], tile=4.0)
    material("Notice", img=g["gen_paper"], tile=1.0)
    material("Clock_Face", img=g["gen_clock"], tile=1.0)
    # emissive and clear (no lightmap)
    material("Lamp_Emit", color=(0.0, 0.0, 0.0), emit=((1.0, 1.0, 1.0), 6.0))
    material("Emergency_Emit", color=(0.0, 0.0, 0.0), emit=((1.0, 0.06, 0.04), 8.0))
    material("Sign_Emit", color=(0.0, 0.0, 0.0), emit=(L((0.10, 0.85, 0.35)), 3.0))
    material("Screen_Emit", img=g["gen_screens"], emit=((1, 1, 1), 2.2), emit_img=True)
    material("Screen_Window", img=g["gen_window"], emit=((1, 1, 1), 1.6), emit_img=True)
    material("Glass_Clear", color=(0.80, 0.90, 0.92), rough=0.05, alpha=0.16)
    material("Water", color=L((0.20, 0.52, 0.58)), rough=0.05, alpha=0.62)


# ---------------------------------------------------------------- a mesh builder in game coordinates (several materials, one object)
class Model:
    def __init__(s, name):
        s.name, s.bm, s.mats, s.region = name, bmesh.new(), [], {}

    def _tag(s, verts, mat, region=None):
        if mat not in s.mats:
            s.mats.append(mat)
        mi = s.mats.index(mat)
        for f in {f for v in verts for f in v.link_faces}:
            f.material_index = mi
            if region:
                s.region[f] = region

    def box(s, mat, mn, mx, region=None, seg=6.0):
        mn, mx = [min(mn[i], mx[i]) for i in range(3)], [max(mn[i], mx[i]) for i in range(3)]
        for ax in (0, 2):                                  # a box longer than `seg` is made of pieces (long islands pack badly)
            if mx[ax] - mn[ax] > seg + 1e-6:
                n = math.ceil((mx[ax] - mn[ax]) / seg)
                vs = []
                for i in range(n):
                    a0, a1 = list(mn), list(mx)
                    a0[ax] = mn[ax] + (mx[ax] - mn[ax]) * i / n
                    a1[ax] = mn[ax] + (mx[ax] - mn[ax]) * (i + 1) / n
                    vs += s.box(mat, a0, a1, region, seg)
                return vs
        a, b = Bv(mn), Bv(mx)
        c = (a + b) / 2
        sz = Vector((max(abs(a.x - b.x), 1e-4), max(abs(a.y - b.y), 1e-4), max(abs(a.z - b.z), 1e-4)))
        r = bmesh.ops.create_cube(s.bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((sz.x, sz.y, sz.z, 1.0)))
        s._tag(r["verts"], mat, region)
        return list(r["verts"])

    def cyl(s, mat, p0, p1, r0, r1=None, seg=12, cap=True, region=None):
        a, b = Bv(p0), Bv(p1)
        d = b - a
        q = d.to_track_quat("Z", "Y")
        r = bmesh.ops.create_cone(s.bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                                  matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())
        s._tag(r["verts"], mat, region)
        return r["verts"]

    def sphere(s, mat, p, r, seg=10, scale=(1, 1, 1), region=None):
        res = bmesh.ops.create_uvsphere(s.bm, u_segments=seg, v_segments=max(4, seg // 2), radius=r,
                                        matrix=Matrix.Translation(Bv(p)) @ Matrix.Diagonal((scale[0], scale[2], scale[1], 1)))
        s._tag(res["verts"], mat, region)
        return res["verts"]

    def quad(s, mat, pts, region=None):
        vs = [s.bm.verts.new(Bv(p)) for p in pts]
        f = s.bm.faces.new(vs)
        s._tag(vs, mat, region)
        return f

    def prism(s, mat, prof, axis, a0, a1, region=None):
        """A profile [(p, q)] (CCW) extruded along `axis` ('x' or 'z') from a0 to a1: for axis x the profile is (z, y), for z it is (x, y)."""
        def P(t, p, q):
            return (t, q, p) if axis == "x" else (p, q, t)
        v0 = [s.bm.verts.new(Bv(P(a0, p, q))) for p, q in prof]
        v1 = [s.bm.verts.new(Bv(P(a1, p, q))) for p, q in prof]
        n = len(prof)
        faces = [s.bm.faces.new(v0[::-1]), s.bm.faces.new(v1)]
        for i in range(n):
            faces.append(s.bm.faces.new((v0[i], v0[(i + 1) % n], v1[(i + 1) % n], v1[i])))
        bmesh.ops.recalc_face_normals(s.bm, faces=faces)
        s._tag(v0 + v1, mat, region)

    def text(s, mat, body, size, depth, origin, right, up, normal):
        cu = bpy.data.curves.new("txt", "FONT")
        cu.body = body
        cu.size = size
        cu.extrude = depth / 2
        cu.align_x, cu.align_y = "CENTER", "CENTER"
        cu.resolution_u = 3
        ob = bpy.data.objects.new("txt", cu)
        bpy.context.scene.collection.objects.link(ob)
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(cu)
        R, U, N = Bv(right), Bv(up), Bv(normal)
        O = Bv(origin)
        M = Matrix(((R.x, U.x, N.x, O.x), (R.y, U.y, N.y, O.y), (R.z, U.z, N.z, O.z), (0, 0, 0, 1)))
        n0 = len(s.bm.verts)
        tmp = bmesh.new()
        tmp.from_mesh(me)
        bmesh.ops.translate(tmp, verts=tmp.verts, vec=Vector((0, 0, depth / 2)))
        bmesh.ops.transform(tmp, matrix=M, verts=tmp.verts)
        m2 = bpy.data.meshes.new("t2")
        tmp.to_mesh(m2)
        tmp.free()
        s.bm.from_mesh(m2)
        bpy.data.meshes.remove(m2)
        bpy.data.meshes.remove(me)
        s.bm.verts.ensure_lookup_table()
        s._tag(s.bm.verts[n0:], mat)

    def rotate(s, verts, angle, axis_game, pivot):
        ax = Bv(axis_game)
        bmesh.ops.rotate(s.bm, verts=list(verts), cent=Bv(pivot), matrix=Matrix.Rotation(angle, 3, ax))

    def done(s, coll, uv=None):
        bm = s.bm
        if not s.mats:
            bm.free()
            return None
        bm.normal_update()                                 # faces made with faces.new() have no normal until now
        layers = list(bm.loops.layers.uv)                 # a text mesh brings a UV layer of its own: keep one layer only
        uvl = layers[0] if layers else bm.loops.layers.uv.new("UVMap")
        for extra in layers[1:]:
            bm.loops.layers.uv.remove(extra)
        for f in bm.faces:
            mat = s.mats[f.material_index]
            if f in s.region and mat == "Cam_Body":
                c = CAM_UV[s.region[f]]
                for lp in f.loops:
                    lp[uvl].uv = c
                continue
            if uv:
                if uv(f, uvl):
                    continue
            tile = TILES.get(mat, 1.0)
            n = f.normal
            ax = max(range(3), key=lambda i: abs(n[i]))
            for lp in f.loops:
                p = lp.vert.co
                gx, gy, gz = p.x, p.z, -p.y
                u, v = (gz, gy) if ax == 0 else (gx, gy) if ax == 1 else (gx, gz)
                lp[uvl].uv = (u / tile, v / tile)
        me = bpy.data.meshes.new(s.name)
        bm.to_mesh(me)
        bm.free()
        for m in s.mats:
            me.materials.append(MATS[m])
        ob = bpy.data.objects.new(s.name, me)
        coll.objects.link(ob)
        return ob


# ================================================================ the scene: layout objects (as the greybox makes them) and the art
COLL = {}
NAMES = ("Art", "Arch", "Props", "Separate", "Shell", "Doors", "Layout", "Lights_Normal", "Lights_Alarm")


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for d in (IMG, MATS, TILES, GEN, COLL, LEAF):
        d.clear()


def collections():
    sc = bpy.context.scene
    for n in NAMES:
        c = bpy.data.collections.new(n)
        COLL[n] = c
        (COLL["Art"] if n in ("Arch", "Props", "Separate") else sc.collection).children.link(c)


def unit_box(name, b, coll):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    mn, mx = b["min"], b["max"]
    a, c = Bv(mn), Bv(mx)
    ctr = (a + c) / 2
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(ctr) @ Matrix.Diagonal((abs(c.x - a.x), abs(c.y - a.y), abs(c.z - a.z), 1)))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def build_layout():
    """The greybox's layout objects, exactly as build_secretops_greybox._blender_main makes them: COL_ boxes, zones, empties (links, arrivals,
    spots), the SecCam_<nn> empties with their properties. The door leaves are made in build_doors (same names, hinges and properties)."""
    lay = COLL["Layout"]
    for b in S.boxes:
        if b.get("zone"):
            ob = unit_box(b["name"], b, lay)
            ob.display_type = "WIRE"
            ob.hide_render = True
        elif b["col"]:
            ob = unit_box("COL_" + b["name"], b, lay)
            ob.display_type = "WIRE"
            ob.hide_render = True
    for e in S.empties + S.cams:
        ob = bpy.data.objects.new(e["name"], None)
        ob.location = Bv(e["pos"])
        if e["face"]:
            ob.rotation_euler = (0, 0, math.atan2(e["face"][0], e["face"][1]))
        for k, v in e["props"].items():
            ob[k] = v
        ob.empty_display_size = 0.3
        lay.objects.link(ob)


def build_arch():
    """One box per shell collider, for the layout check only (never rendered or exported)."""
    for b in cols_of(S):
        if is_shell(b["name"]):
            ob = unit_box(b["name"], b, COLL["Arch"])
            ob.hide_render = True


def build_shell(quads):
    """The seen faces, one object per material (`Shell_<mat>`), every face a rectangle with its normal into the air."""
    by = {}
    for q in quads:
        by.setdefault(q["mat"], []).append(q)
    for mat, qs in sorted(by.items()):
        M = Model("Shell_" + mat)
        for q in qs:
            a, side = q["axis"], q["side"]
            ua, va = [i for i in range(3) if i != a]
            pts = []
            for (uu, vv) in ((q["u"][0], q["v"][0]), (q["u"][1], q["v"][0]), (q["u"][1], q["v"][1]), (q["u"][0], q["v"][1])):
                p = [0.0, 0.0, 0.0]
                p[a], p[ua], p[va] = q["c"], uu, vv
                pts.append(p)
            e1 = np.subtract(pts[1], pts[0])
            e2 = np.subtract(pts[3], pts[0])
            n = np.cross(e1, e2)
            if n[a] * side < 0:
                pts = pts[::-1]
            M.quad(mat, pts)
        M.done(COLL["Shell"])


# ---------------------------------------------------------------- the dressing: wall trims, doors, windows
def wall_faces(quads, kind="wall"):
    return [q for q in quads if q["kind"] == kind and q["axis"] != 1]


def trim_runs(q, y0, y1):
    """The parts of a wall face's u-span at heights y0..y1 (the face must cover them)."""
    a = q["axis"]
    ua, va = [i for i in range(3) if i != a]
    if va != 1 or q["v"][0] > y0 + 1e-6 or q["v"][1] < y1 - 1e-6:
        return None
    return q["u"]


def doors_on(q, doors):
    a = q["axis"]
    return [(d[3]) for d in doors if d[1] == a and abs(d[2] - q["c"]) < 0.06]


def cut(u0, u1, holes, half):
    runs = [(u0, u1)]
    for h in holes:
        nr = []
        for a, b in runs:
            if h + half <= a or h - half >= b:
                nr.append((a, b))
            else:
                if h - half > a:
                    nr.append((a, h - half))
                if h + half < b:
                    nr.append((h + half, b))
        runs = nr
    return [(a, b) for a, b in runs if b - a > 0.05]


def wall_box(M, q, mat, u0, u1, y0, y1, d0, d1):
    a, side = q["axis"], q["side"]
    c = q["c"]
    p0, p1 = [0.0] * 3, [0.0] * 3
    ua = 2 if a == 0 else 0
    p0[a], p1[a] = c + side * d0, c + side * d1
    p0[ua], p1[ua] = u0, u1
    p0[1], p1[1] = y0, y1
    M.box(mat, p0, p1)


def stripe_mat(space):
    wm = space["wmat"]
    s = STRIPE.get(wm)
    if isinstance(s, tuple):
        return s[0] if SCENE == "corridors_a" else s[1]
    return s


def build_trims(quads):
    """A dark cove skirting along every wall, and the coloured stripe at hand height where the space has one (the arena has the greybox's pink
    stripe already, 1.2 to 1.5 m)."""
    doors = edge_doors(S)
    sk = Model("decor_skirting")
    st = {}
    for q in wall_faces(quads):
        if q["space"] < 0:
            continue
        sp = S.spaces[q["space"]]
        holes = doors_on(q, doors)
        r = trim_runs(q, 0.0, 0.12)
        if r and sp["wmat"] not in ("tile", "steel"):
            for u0, u1 in cut(r[0], r[1], holes, 0.6):
                wall_box(sk, q, "Skirting", u0, u1, 0.0, 0.12, 0.0, 0.012)
        m = stripe_mat(sp)
        if m and sp["wmat"] != "server_green":
            r = trim_runs(q, 1.05, 1.17)
            if r:
                for u0, u1 in cut(r[0], r[1], holes, 0.6):
                    wall_box(st.setdefault(m, Model("decor_stripe_" + m)), q, m, u0, u1, 1.05, 1.17, 0.0, 0.006)
    sk.done(COLL["Props"])
    for M in st.values():
        M.done(COLL["Props"])


LEAF = {}


def leaf_mesh(kind, w, h):
    """A steel door leaf in its own frame (origin at the hinge, local +x along it, game y up): a kick plate, a narrow vision panel, a lever
    handle; the keycard door is heavier, with a red band and a reader's light."""
    key = (kind, round(w, 3), round(h, 3))
    if key in LEAF:
        return LEAF[key]
    M = Model(f"Leaf_{kind}")
    t = 0.025
    body = "Door_Keycard" if kind == "keycard" else "Door_Steel"
    M.box(body, (0.0, 0.0, -t), (w, h, t))
    for sgn in (-1, 1):
        M.box("Steel", (0.06, 0.02, sgn * t), (w - 0.06, 0.28, sgn * (t + 0.003)))
        M.box("Plastic_Black", (w - 0.28, 1.25, sgn * t), (w - 0.18, 1.85, sgn * (t + 0.002)))
        M.box("Steel", (0.10, 1.0, sgn * (t + 0.01)), (0.24, 1.03, sgn * (t + 0.05)))
        M.box("Steel", (0.07, 0.96, sgn * t), (0.11, 1.07, sgn * (t + 0.05)))
        if kind == "keycard":
            M.box("Stripe_Red", (0.0, 1.35, sgn * t), (w, 1.45, sgn * (t + 0.002)))
    me_ob = M.done(COLL["Doors"])
    me = me_ob.data
    bpy.data.objects.remove(me_ob)
    LEAF[key] = me
    return me


def frame_for(d, quads):
    """A painted steel frame round a door: two jambs and a head, proud of the wall on the sides that are seen."""
    M = Model(f"decor_frame_{d['name'][9:]}")
    th = d["yaw"]
    w, h = d["props"]["width"], d["props"]["height"]
    run = (math.cos(th), -math.sin(th))
    hx, hz = d["hinge"][0], d["hinge"][2]
    nrm = (-run[1], run[0])
    fw, pr = 0.07, 0.03
    sides = []
    for sg in (-1, 1):
        p = (hx + run[0] * w / 2 + nrm[0] * sg * 0.15, 0.5, hz + run[1] * w / 2 + nrm[1] * sg * 0.15)
        if any(_in(p, x[0], x[1]) for x in air_boxes(S)):
            sides.append(sg)
    for sg in sides:
        for a0, a1, y0, y1 in ((-fw, 0.0, 0.0, h + fw), (w, w + fw, 0.0, h + fw), (-fw, w + fw, h, h + fw)):
            pts = []
            for (aa, dd) in ((a0, 0.0), (a1, sg * pr)):
                pts.append((hx + run[0] * aa + nrm[0] * dd, hz + run[1] * aa + nrm[1] * dd))
            M.box("Door_Frame", (min(pts[0][0], pts[1][0]), y0, min(pts[0][1], pts[1][1])), (max(pts[0][0], pts[1][0]), y1, max(pts[0][1], pts[1][1])))
    return M.done(COLL["Props"])


def build_doors(quads):
    for d in S.doors:
        kind = "keycard" if d["props"].get("keycard_tier") else "plain"
        ob = bpy.data.objects.new(d["name"], leaf_mesh(kind, d["props"]["width"], d["props"]["height"]))
        ob.matrix_world = Matrix.Translation(Bv(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
        for k, v in d["props"].items():
            ob[k] = v
        COLL["Doors"].objects.link(ob)
        frame_for(d, quads)


def door_centre(d):
    th = d["yaw"]
    run = (math.cos(th), -math.sin(th))
    w = d["props"]["width"]
    return d["hinge"][0] + run[0] * w / 2, d["hinge"][2] + run[1] * w / 2, run


# ---------------------------------------------------------------- props: one model per collider, filling its box
def front_side(b):
    """The side (axis, sign) of a box that faces the room: the long side whose outside is open air."""
    mn, mx = b["min"], b["max"]
    w, d = mx[0] - mn[0], mx[2] - mn[2]
    cands = [(2, -1), (2, 1)] if w >= d else [(0, -1), (0, 1)]
    cands += [(0, -1), (0, 1)] if w >= d else [(2, -1), (2, 1)]
    air = air_boxes(S)
    cols = cols_of(S)
    best = None
    for a, sg in cands:
        p = [(mn[i] + mx[i]) / 2 for i in range(3)]
        p[1] = 0.5
        p[a] = (mx[a] if sg > 0 else mn[a]) + sg * 0.3
        free = any(_in(p, x[0], x[1]) for x in air) and not any(_strict(p, c["min"], c["max"]) for c in cols if c is not b)
        if free:
            best = (a, sg)
            break
    return best or cands[0]


def bx(M, mat, b, x0, x1, y0, y1, z0, z1, region=None):
    """A box in the collider's own frame: fractions of its size for x and z, metres for y."""
    mn, mx = b["min"], b["max"]
    W, D = mx[0] - mn[0], mx[2] - mn[2]
    M.box(mat, (mn[0] + x0 * W, mn[1] + y0, mn[2] + z0 * D), (mn[0] + x1 * W, mn[1] + y1, mn[2] + z1 * D), region)


def prop_bench(b, M):
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    if h < 0.6:                                         # a changing-room or poolside bench: steel legs, a slatted seat
        for fx in (0.04, 0.92):
            bx(M, "Steel", b, fx, fx + 0.04, 0, h - 0.05, 0.1, 0.9)
        n = 5
        for i in range(n):
            bx(M, "Laminate", b, 0, 1, h - 0.05, h, i / n + 0.01, (i + 1) / n - 0.01)
        bx(M, "Steel", b, 0, 1, 0.0, 0.03, 0.45, 0.55)
        return
    a, sg = front_side(b)
    bx(M, "Bench_Top", b, 0, 1, h - 0.04, h, 0, 1)
    bx(M, "Plastic_White", b, 0.02, 0.98, 0.1, h - 0.04, 0.03, 0.97)
    bx(M, "Paint_Dark", b, 0.04, 0.96, 0.0, 0.1, 0.08, 0.92)
    L = (mx[0] - mn[0]) if a == 2 else (mx[2] - mn[2])
    nd = max(2, int(L / 0.6))
    for i in range(nd):
        t0, t1 = 0.02 + 0.96 * i / nd, 0.02 + 0.96 * (i + 1) / nd
        for sgn in (-1, 1):
            if a == 2:
                z = mn[2] + 0.03 * (mx[2] - mn[2]) if sgn < 0 else mx[2] - 0.03 * (mx[2] - mn[2])
                xm = mn[0] + (t0 + t1) / 2 * (mx[0] - mn[0])
                M.box("Steel", (xm - 0.08, h - 0.16, z - 0.015), (xm + 0.08, h - 0.14, z + 0.015))
                M.box("Plastic_Grey", (mn[0] + t0 * (mx[0] - mn[0]) + 0.005, 0.12, z - 0.003), (mn[0] + t1 * (mx[0] - mn[0]) - 0.005, h - 0.06, z + 0.003))
            else:
                x = mn[0] + 0.03 * (mx[0] - mn[0]) if sgn < 0 else mx[0] - 0.03 * (mx[0] - mn[0])
                zm = mn[2] + (t0 + t1) / 2 * (mx[2] - mn[2])
                M.box("Steel", (x - 0.015, h - 0.16, zm - 0.08), (x + 0.015, h - 0.14, zm + 0.08))
                M.box("Plastic_Grey", (x - 0.003, 0.12, mn[2] + t0 * (mx[2] - mn[2]) + 0.005), (x + 0.003, h - 0.06, mn[2] + t1 * (mx[2] - mn[2]) - 0.005))
    # on top: a microscope case, a rack of tubes, two bottles, a sink in one in three benches
    rng = np.random.default_rng(abs(hash(b["name"])) % 2 ** 31)
    cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
    along = (1, 0) if a == 2 else (0, 1)
    Lh = L / 2
    for k, kind in enumerate(rng.permutation(["case", "tubes", "bottles", "none"])[:3]):
        off = -Lh * 0.6 + k * Lh * 0.6
        px, pz = cx + along[0] * off, cz + along[1] * off
        if kind == "case":
            M.box("Plastic_White", (px - 0.18, h, pz - 0.15), (px + 0.18, h + 0.22, pz + 0.15))
            M.box("Plastic_Black", (px - 0.16, h + 0.08, pz - 0.151), (px + 0.0, h + 0.18, pz - 0.149))
        elif kind == "tubes":
            M.box("Plastic_Grey", (px - 0.15, h, pz - 0.05), (px + 0.15, h + 0.08, pz + 0.05))
            for i in range(6):
                M.cyl("Liquid" if i % 2 else "Plastic_White", (px - 0.12 + i * 0.048, h + 0.02, pz), (px - 0.12 + i * 0.048, h + 0.16, pz), 0.012, seg=6)
        elif kind == "bottles":
            M.cyl("Plastic_White", (px - 0.08, h, pz), (px - 0.08, h + 0.24, pz), 0.05, seg=10)
            M.cyl("Specimen", (px + 0.07, h, pz), (px + 0.07, h + 0.2, pz), 0.045, seg=10)


def prop_crate(b, M):
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    split = [0.0, h] if h <= 1.0 else [0.0, round(h * 0.55, 3), h]
    for i in range(len(split) - 1):
        y0, y1 = split[i], split[i + 1]
        ins = 0.0 if i == 0 else 0.04
        bx(M, "Wood_Crate", b, ins, 1 - ins, y0, y1 - 0.005, ins, 1 - ins)
        for (fx0, fx1, fz0, fz1) in ((ins, 1 - ins, ins - 0.003, ins + 0.06), (ins, 1 - ins, 1 - ins - 0.06, 1 - ins + 0.003)):
            bx(M, "Paint_Grey", b, fx0, fx1, y0, y0 + 0.07, max(0, fz0), min(1, fz1))
            bx(M, "Paint_Grey", b, fx0, fx1, y1 - 0.075, y1 - 0.005, max(0, fz0), min(1, fz1))
    bx(M, "Sign_Plate", b, 0.35, 0.65, h * 0.5, h * 0.5 + 0.18, -0.004, 0.0)


def prop_pallet(b, M):
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    for fz in (0.0, 0.45, 0.9):
        bx(M, "Wood_Crate", b, 0, 1, 0, 0.1, fz, fz + 0.1)
    bx(M, "Wood_Crate", b, 0, 1, 0.1, 0.14, 0, 1)
    for i in range(2):
        for j in range(2):
            for k in range(2):
                y0 = 0.14 + k * (h - 0.14) / 2
                bx(M, "Cardboard", b, 0.02 + i * 0.49, 0.49 + i * 0.49, y0, y0 + (h - 0.14) / 2 - 0.01, 0.02 + j * 0.49, 0.49 + j * 0.49)
    bx(M, "Plastic_White", b, 0.0, 1.0, h - 0.02, h, 0.0, 1.0)


def prop_forklift(b, M):
    mn, mx = b["min"], b["max"]
    W = mx[0] - mn[0]
    bx(M, "Paint_Yellow", b, 0.0, 0.62, 0.18, 1.15, 0.05, 0.95)
    bx(M, "Paint_Dark", b, 0.0, 0.2, 0.18, 1.25, 0.05, 0.95)
    for fz in (0.05, 0.9):
        bx(M, "Steel_Dark", b, 0.2, 0.25, 1.15, 2.0, fz, fz + 0.05)
        bx(M, "Steel_Dark", b, 0.55, 0.6, 1.15, 2.0, fz, fz + 0.05)
    bx(M, "Steel_Dark", b, 0.2, 0.6, 1.95, 2.0, 0.05, 0.95)
    bx(M, "Fabric", b, 0.3, 0.45, 1.15, 1.35, 0.3, 0.7)
    for fz in (0.1, 0.83):
        bx(M, "Steel_Dark", b, 0.66, 0.72, 0.05, 2.0, fz, fz + 0.07)
    bx(M, "Steel_Dark", b, 0.66, 0.72, 1.85, 1.95, 0.1, 0.9)
    for fz in (0.2, 0.7):
        bx(M, "Steel_Dark", b, 0.72, 1.0, 0.04, 0.09, fz, fz + 0.1)
    for fx in (0.12, 0.5):
        for fz in (0.0, 0.88):
            cxw = mn[0] + fx * W
            M.cyl("Rubber", (cxw, 0.2, mn[2] + fz * (mx[2] - mn[2])), (cxw, 0.2, mn[2] + (fz + 0.12) * (mx[2] - mn[2])), 0.2, seg=14)
            M.box("Rubber", (cxw - 0.2, 0.0, mn[2] + fz * (mx[2] - mn[2])), (cxw + 0.2, 0.02, mn[2] + (fz + 0.12) * (mx[2] - mn[2])))


def prop_pillar(b, M):
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    bx(M, "Pillar_Paint", b, 0, 1, 0, h, 0, 1)
    g = 0.06 / max(mx[0] - mn[0], 0.1)
    for fx in (0, 1):
        for fz in (0, 1):
            x = mn[0] if fx == 0 else mx[0]
            z = mn[2] if fz == 0 else mx[2]
            sx, sz = (1 if fx == 0 else -1), (1 if fz == 0 else -1)
            M.box("Steel", (x - sx * 0.004, 0.12, z - sz * 0.004), (x + sx * 0.07, 1.4, z + sz * 0.004 * 0 + sz * 0.012))
            M.box("Steel", (x - sx * 0.004, 0.12, z - sz * 0.004), (x + sx * 0.012, 1.4, z + sz * 0.07))
    bx(M, "Hazard", b, 0, 1, 0.0, 0.12, 0, 1)
    del g


def prop_shelf(b, M):
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    a, sg = front_side(b)
    L = (mx[0] - mn[0]) if a == 2 else (mx[2] - mn[2])
    bays = max(1, round(L / 1.25))
    rng = np.random.default_rng(abs(hash(b["name"])) % 2 ** 31)
    for i in range(bays + 1):
        f = i / bays
        f0, f1 = max(0, f - 0.008), min(1, f + 0.008)
        for d0, d1 in ((0, 0.06), (0.94, 1)):
            if a == 2:
                bx(M, "Paint_Grey", b, f0, f1, 0, h, d0, d1)
            else:
                bx(M, "Paint_Grey", b, d0, d1, 0, h, f0, f1)
    levels = [0.1, h * 0.36, h * 0.66, h - 0.03]
    for y in levels:
        if a == 2:
            bx(M, "Steel", b, 0, 1, y, y + 0.03, 0, 1)
        else:
            bx(M, "Steel", b, 0, 1, y, y + 0.03, 0, 1)
    for li, y in enumerate(levels[:-1]):
        gap = (levels[li + 1] - y) - 0.06
        for i in range(bays):
            for k in range(int(rng.integers(1, 4))):
                f0 = (i + 0.08 + k * 0.3) / bays
                f1 = f0 + 0.25 / bays
                hh = min(gap, float(rng.uniform(0.2, 0.42)))
                if a == 2:
                    bx(M, "Cardboard", b, f0, f1, y + 0.03, y + 0.03 + hh, 0.1, 0.9)
                else:
                    bx(M, "Cardboard", b, 0.1, 0.9, y + 0.03, y + 0.03 + hh, f0, f1)


def prop_desk(b, M):
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    a, sg = front_side(b)
    bx(M, "Laminate", b, 0, 1, h - 0.035, h, 0, 1)
    for f in (0.0, 0.97):
        if a == 2:
            bx(M, "Paint_Grey", b, f, f + 0.03, 0, h - 0.035, 0.03, 0.97)
        else:
            bx(M, "Paint_Grey", b, 0.03, 0.97, 0, h - 0.035, f, f + 0.03)
    back = 1 if sg < 0 else 0                                  # the modesty panel on the side away from the room
    if a == 2:
        bx(M, "Paint_Grey", b, 0.03, 0.97, 0.15, h - 0.035, 0.9 if back else 0.0, 1.0 if back else 0.1)
    else:
        bx(M, "Paint_Grey", b, 0.9 if back else 0.0, 1.0 if back else 0.1, 0.15, h - 0.035, 0.03, 0.97)
    # monitors facing the room, a keyboard, a phone; nobody sits here
    cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
    L = (mx[0] - mn[0]) if a == 2 else (mx[2] - mn[2])
    nmon = 1 if L < 2 else 2
    for i in range(nmon):
        off = 0 if nmon == 1 else (-0.45 + 0.9 * i)
        if a == 2:
            z = mx[2] - 0.15 if sg < 0 else mn[2] + 0.15
            zf = z + (-0.03 if sg < 0 else 0.03)
            M.box("Plastic_Black", (cx + off - 0.03, h, z - 0.03), (cx + off + 0.03, h + 0.12, z + 0.03))
            M.box("Plastic_Black", (cx + off - 0.28, h + 0.12, min(z, zf)), (cx + off + 0.28, h + 0.45, max(z, zf)))
            M.quad("Screen_Emit", [(cx + off - 0.26, h + 0.14, zf + sg * 0.001), (cx + off + 0.26, h + 0.14, zf + sg * 0.001),
                                   (cx + off + 0.26, h + 0.43, zf + sg * 0.001), (cx + off - 0.26, h + 0.43, zf + sg * 0.001)][::(1 if sg > 0 else -1)],
                   region=("scr", i))
            kz = (mn[2] + mx[2]) / 2 + sg * 0.12
            M.box("Plastic_Black", (cx + off - 0.22, h, kz - 0.07), (cx + off + 0.22, h + 0.02, kz + 0.07))
        else:
            x = mx[0] - 0.15 if sg < 0 else mn[0] + 0.15
            xf = x + (-0.03 if sg < 0 else 0.03)
            M.box("Plastic_Black", (x - 0.03, h, cz + off - 0.03), (x + 0.03, h + 0.12, cz + off + 0.03))
            M.box("Plastic_Black", (min(x, xf), h + 0.12, cz + off - 0.28), (max(x, xf), h + 0.45, cz + off + 0.28))
            M.quad("Screen_Emit", [(xf + sg * 0.001, h + 0.14, cz + off + 0.26), (xf + sg * 0.001, h + 0.14, cz + off - 0.26),
                                   (xf + sg * 0.001, h + 0.43, cz + off - 0.26), (xf + sg * 0.001, h + 0.43, cz + off + 0.26)][::(1 if sg > 0 else -1)],
                   region=("scr", i))
            kx = (mn[0] + mx[0]) / 2 + sg * 0.12
            M.box("Plastic_Black", (kx - 0.07, h, cz + off - 0.22), (kx + 0.07, h + 0.02, cz + off + 0.22))


def prop_lockers(b, M):
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    a, sg = front_side(b)
    bx(M, "Locker_Paint", b, 0, 1, 0.1, h, 0, 1)
    bx(M, "Paint_Dark", b, 0.02, 0.98, 0, 0.1, 0.02, 0.98)
    L = (mx[0] - mn[0]) if a == 2 else (mx[2] - mn[2])
    n = max(1, int(L / 0.32))
    for i in range(n):
        f0, f1 = i / n + 0.004, (i + 1) / n - 0.004
        for y0, y1 in ((0.14, h * 0.52), (h * 0.53, h - 0.04)):
            if a == 2:
                z = mx[2] if sg > 0 else mn[2]
                M.box("Locker_Paint", (mn[0] + f0 * L, y0, z), (mn[0] + f1 * L, y1, z + sg * 0.006))
                for k in range(4):
                    M.box("Paint_Dark", (mn[0] + (f0 + 0.2 * (f1 - f0)) * L, y1 - 0.08 - k * 0.025, z + sg * 0.006),
                          (mn[0] + (f1 - 0.2 * (f1 - f0)) * L, y1 - 0.07 - k * 0.025, z + sg * 0.008))
                M.box("Steel", (mn[0] + (f1 - 0.18 * (f1 - f0)) * L, (y0 + y1) / 2 - 0.05, z + sg * 0.006), (mn[0] + (f1 - 0.1 * (f1 - f0)) * L, (y0 + y1) / 2 + 0.05, z + sg * 0.02))
            else:
                x = mx[0] if sg > 0 else mn[0]
                M.box("Locker_Paint", (x, y0, mn[2] + f0 * L), (x + sg * 0.006, y1, mn[2] + f1 * L))
                for k in range(4):
                    M.box("Paint_Dark", (x + sg * 0.006, y1 - 0.08 - k * 0.025, mn[2] + (f0 + 0.2 * (f1 - f0)) * L),
                          (x + sg * 0.008, y1 - 0.07 - k * 0.025, mn[2] + (f1 - 0.2 * (f1 - f0)) * L))
                M.box("Steel", (x + sg * 0.006, (y0 + y1) / 2 - 0.05, mn[2] + (f1 - 0.18 * (f1 - f0)) * L), (x + sg * 0.02, (y0 + y1) / 2 + 0.05, mn[2] + (f1 - 0.1 * (f1 - f0)) * L))


def prop_barrier(b, M):
    """A concrete safety barrier: the Jersey profile along its long axis, a yellow and black band near the top."""
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    along = "x" if mx[0] - mn[0] >= mx[2] - mn[2] else "z"
    p0, p1 = (mn[2], mx[2]) if along == "x" else (mn[0], mx[0])
    a0, a1 = (mn[0], mx[0]) if along == "x" else (mn[2], mx[2])
    w = p1 - p0
    c = (p0 + p1) / 2
    prof = [(p0, 0.0), (p1, 0.0), (p1, 0.08), (c + w * 0.3, 0.32), (c + w * 0.18, h), (c - w * 0.18, h), (c - w * 0.3, 0.32), (p0, 0.08)]
    M.prism("Concrete_Prop", prof, along, a0, a1)
    yb0, yb1 = h * 0.7, h * 0.86
    def at(y):
        t = (y - 0.32) / (h - 0.32)
        return w * (0.3 + (0.18 - 0.3) * t)
    for y0, y1 in ((yb0, yb1),):
        hw0, hw1 = at(y0), at(y1)
        for sg in (-1, 1):
            prof2 = [(c + sg * hw0, y0), (c + sg * (hw0 + 0.004), y0), (c + sg * (hw1 + 0.004), y1), (c + sg * hw1, y1)]
            if sg < 0:
                prof2 = prof2[::-1]
            M.prism("Hazard", prof2, along, a0 + 0.02, a1 - 0.02)


def prop_planter(b, M):
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    bx(M, "Concrete_Prop", b, 0, 1, 0, h, 0, 0.06)
    bx(M, "Concrete_Prop", b, 0, 1, 0, h, 0.94, 1)
    bx(M, "Concrete_Prop", b, 0, 0.06, 0, h, 0.06, 0.94)
    bx(M, "Concrete_Prop", b, 0.94, 1, 0, h, 0.06, 0.94)
    bx(M, "Soil", b, 0.06, 0.94, 0, h - 0.08, 0.06, 0.94)
    cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
    rng = np.random.default_rng(7)
    for k in range(7):                                    # plastic shrubs: too green, too regular
        ang = k * 2 * math.pi / 7
        r = 0.45 if k else 0.0
        px, pz = cx + r * math.cos(ang), cz + r * math.sin(ang)
        M.cyl("Plant", (px, h - 0.08, pz), (px, h + 0.25 + 0.1 * (k % 2), pz), 0.02, seg=6)
        M.sphere("Plant", (px, h + 0.4 + 0.1 * (k % 2), pz), 0.2, seg=8, scale=(1, 1.3, 1))
    del rng


def prop_hood(b, M):
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    a, sg = front_side(b)
    bx(M, "Plastic_White", b, 0, 1, 0, 0.9, 0, 1)
    bx(M, "Bench_Top", b, 0, 1, 0.9, 0.94, 0, 1)
    bx(M, "Plastic_White", b, 0, 1, 1.85, h, 0, 1)
    if a == 0:
        back = (0.0, 0.08) if sg > 0 else (0.92, 1.0)
        bx(M, "Plastic_White", b, back[0], back[1], 0.94, 1.85, 0, 1)
        for fz in ((0, 0.05), (0.95, 1)):
            bx(M, "Plastic_White", b, 0, 1, 0.94, 1.85, fz[0], fz[1])
        x = mx[0] if sg > 0 else mn[0]
        M.box("Glass_Clear", (x - sg * 0.04, 1.2, mn[2] + 0.05), (x - sg * 0.03, 1.85, mx[2] - 0.05))
        M.box("Steel", (x - sg * 0.05, 1.18, mn[2] + 0.05), (x, 1.22, mx[2] - 0.05))
        M.box("Plastic_Black", (x, 1.88, mn[2] + 0.2), (x + sg * 0.004, 2.05, mn[2] + 0.6))
    else:
        back = (0.0, 0.08) if sg > 0 else (0.92, 1.0)
        bx(M, "Plastic_White", b, 0, 1, 0.94, 1.85, back[0], back[1])
        for fx in ((0, 0.05), (0.95, 1)):
            bx(M, "Plastic_White", b, fx[0], fx[1], 0.94, 1.85, 0, 1)
        z = mx[2] if sg > 0 else mn[2]
        M.box("Glass_Clear", (mn[0] + 0.05, 1.2, z - sg * 0.04), (mx[0] - 0.05, 1.85, z - sg * 0.03))
        M.box("Steel", (mn[0] + 0.05, 1.18, z - sg * 0.05), (mx[0] - 0.05, 1.22, z))
    cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
    ctop = next((sp["h"] for sp in S.spaces if sp["x0"] <= cx <= sp["x1"] and sp["z0"] <= cz <= sp["z1"]), 3.0)
    M.cyl("Steel", (cx, h, cz), (cx, ctop, cz), 0.12, seg=12)


def prop_tank(b, M):
    """A specimen tank: a steel plinth and cap, a glass cylinder, murky green liquid and something dark inside."""
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
    r = min(mx[0] - mn[0], mx[2] - mn[2]) / 2
    bx(M, "Steel_Dark", b, 0, 1, 0, 0.3, 0, 1)
    bx(M, "Steel_Dark", b, 0, 1, h - 0.22, h, 0, 1)
    M.cyl("Glass_Clear", (cx, 0.3, cz), (cx, h - 0.22, cz), r * 0.96, seg=20, cap=False)
    M.cyl("Liquid", (cx, 0.3, cz), (cx, h * 0.82, cz), r * 0.9, seg=20)
    M.cyl("Steel", (cx, h - 0.22, cz), (cx, h - 0.05, cz), r * 0.25, seg=10)
    for k in range(4):
        ang = k * math.pi / 2 + math.pi / 4
        M.box("Steel", (cx + r * 0.95 * math.cos(ang) - 0.015, 0.3, cz + r * 0.95 * math.sin(ang) - 0.015),
              (cx + r * 0.95 * math.cos(ang) + 0.015, h - 0.22, cz + r * 0.95 * math.sin(ang) + 0.015))


def prop_breaker(b, M):
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    a, sg = front_side(b)
    circuit = b["props"].get("circuit", "")
    bx(M, "Breaker_Paint", b, 0, 1, 0.0, h, 0, 1)
    L = (mx[0] - mn[0]) if a == 2 else (mx[2] - mn[2])
    nd = 2 if L > 1.4 else 1
    fp = mx[a] if sg > 0 else mn[a]
    for i in range(nd):
        f0, f1 = i / nd + 0.03, (i + 1) / nd - 0.03
        lo = (mn[0] if a == 2 else mn[2])

        def face_box(mat, u0, u1, y0, y1, d0, d1):
            if a == 2:
                M.box(mat, (lo + u0 * L, y0, fp + sg * d0), (lo + u1 * L, y1, fp + sg * d1))
            else:
                M.box(mat, (fp + sg * d0, y0, lo + u0 * L), (fp + sg * d1, y1, lo + u1 * L))
        face_box("Breaker_Paint", f0, f1, 0.1, h - 0.1, 0.0, 0.008)
        face_box("Paint_Dark", f0 + 0.04, f0 + 0.06, 0.9, 1.3, 0.008, 0.02)
        face_box("Sign_Plate", f0 + 0.15, f1 - 0.15, h - 0.42, h - 0.2, 0.008, 0.012)
        face_box("Paint_Yellow", (f0 + f1) / 2 - 0.08, (f0 + f1) / 2 + 0.08, 1.45, 1.6, 0.008, 0.011)
        for k in range(6):
            face_box("Plastic_Black", f0 + 0.15 + k * (f1 - f0 - 0.3) / 6, f0 + 0.15 + (k + 0.6) * (f1 - f0 - 0.3) / 6, 1.0, 1.12, 0.008, 0.04)
    um = (mn[0] + mx[0]) / 2 if a == 2 else (mn[2] + mx[2]) / 2
    yl = 1.05
    if a == 2:
        M.box("Paint_Orange", (um - 0.06, yl - 0.25, fp), (um + 0.06, yl + 0.25, fp + sg * 0.025))
        M.box("Paint_Orange", (um - 0.03, yl + 0.2, fp + sg * 0.025), (um + 0.03, yl + 0.3, fp + sg * 0.045))
        nrm, right = (0, 0, sg), (sg, 0, 0)
    else:
        M.box("Paint_Orange", (fp, yl - 0.25, um - 0.06), (fp + sg * 0.025, yl + 0.25, um + 0.06))
        M.box("Paint_Orange", (fp + sg * 0.025, yl + 0.2, um - 0.03), (fp + sg * 0.045, yl + 0.3, um + 0.03))
        nrm, right = (sg, 0, 0), (0, 0, -sg)
    if circuit:
        o = [0, h - 0.31, 0]
        o[a] = fp + sg * 0.012
        o[2 if a == 0 else 0] = um
        M.text("Plastic_Black", circuit, 0.16, 0.004, o, right, (0, 1, 0), nrm)


def prop_trafo(b, M):
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    bx(M, "Trafo_Paint", b, 0.12, 0.88, 0, h - 0.25, 0.12, 0.88)
    bx(M, "Paint_Dark", b, 0.1, 0.9, 0, 0.1, 0.1, 0.9)
    W, D = mx[0] - mn[0], mx[2] - mn[2]
    n = int(W / 0.12)
    for i in range(n):
        f = (i + 0.5) / n
        bx(M, "Trafo_Paint", b, f - 0.01, f + 0.01, 0.15, h - 0.35, 0.0, 0.12)
        bx(M, "Trafo_Paint", b, f - 0.01, f + 0.01, 0.15, h - 0.35, 0.88, 1.0)
    for i in range(3):
        px = mn[0] + W * (0.3 + 0.2 * i)
        pz = (mn[2] + mx[2]) / 2
        M.cyl("Plastic_White", (px, h - 0.25, pz), (px, h - 0.02, pz), 0.07, 0.04, seg=10)
    bx(M, "Paint_Yellow", b, 0.4, 0.6, 1.0, 1.2, 0.115, 0.12)


def prop_rack_like(b, M):
    """A server cabinet filling its box (the corridor's server closet, the control room): the rack atlas on its front and back."""
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    M.box("Server_Body", (mn[0], 0.04, mn[2]), (mx[0], h, mx[2]))
    M.box("Paint_Dark", (mn[0] + 0.02, 0.0, mn[2] + 0.02), (mx[0] - 0.02, 0.04, mx[2] - 0.02))


def rack_uv(lo, hi, front_axis):
    """UVs on the rack atlas: faces looking along front_axis show the front (left half), the rest the sides (right half)."""
    def f(face, uvl):
        n = face.normal
        g = (n.x, n.z, -n.y)
        ax = max(range(3), key=lambda i: abs(g[i]))
        for lp in face.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y
            if ax == front_axis:
                t = ((gx - lo[0]) / (hi[0] - lo[0])) if front_axis == 2 else ((gz - lo[2]) / (hi[2] - lo[2]))
                lp[uvl].uv = (0.5 * min(max(t, 0), 1), min(max((gy - lo[1]) / (hi[1] - lo[1]), 0), 1))
            else:
                u = (gz - lo[2]) / (hi[2] - lo[2]) if ax == 0 else (gx - lo[0]) / (hi[0] - lo[0])
                lp[uvl].uv = (0.5 + 0.5 * min(max(u, 0), 1), min(max((gy - lo[1]) / (hi[1] - lo[1]), 0), 1))
        return True
    return f


def prop_cubicle(b, M):
    """A glass test cubicle: a steel frame, glass on four sides (a door on the side facing the room), a white floor and a bolted chair."""
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    p = 0.06
    bx(M, "Plastic_White", b, 0, 1, 0.0, 0.1, 0, 1)
    for fx in (0, 1):
        for fz in (0, 1):
            x = mn[0] if fx == 0 else mx[0] - p
            z = mn[2] if fz == 0 else mx[2] - p
            M.box("Steel", (x, 0.1, z), (x + p, h, z + p))
    for y0, y1 in ((h - 0.12, h), (0.1, 0.16)):
        M.box("Steel", (mn[0], y0, mn[2]), (mx[0], y1, mn[2] + p))
        M.box("Steel", (mn[0], y0, mx[2] - p), (mx[0], y1, mx[2]))
        M.box("Steel", (mn[0], y0, mn[2] + p), (mn[0] + p, y1, mx[2] - p))
        M.box("Steel", (mx[0] - p, y0, mn[2] + p), (mx[0], y1, mx[2] - p))
    M.box("Plastic_White", (mn[0], h - 0.04, mn[2]), (mx[0], h, mx[2]))
    c = 0.03
    M.box("Glass_Clear", (mn[0] + p, 0.16, mn[2] + c - 0.005), (mx[0] - p, h - 0.12, mn[2] + c + 0.005))
    M.box("Glass_Clear", (mn[0] + p, 0.16, mx[2] - c - 0.005), (mx[0] - p, h - 0.12, mx[2] - c + 0.005))
    M.box("Glass_Clear", (mn[0] + c - 0.005, 0.16, mn[2] + p), (mn[0] + c + 0.005, h - 0.12, mx[2] - p))
    M.box("Glass_Clear", (mx[0] - c - 0.005, 0.16, mn[2] + p), (mx[0] - c + 0.005, h - 0.12, mx[2] - p))
    cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
    M.box("Steel", (cx - 0.25, 0.1, cz - 0.25), (cx + 0.25, 0.48, cz + 0.25))
    M.box("Steel", (cx - 0.25, 0.48, cz + 0.2), (cx + 0.25, 1.1, cz + 0.25))
    for sx in (-1, 1):
        M.box("Plastic_Black", (cx + sx * 0.25, 0.55, cz - 0.15), (cx + sx * 0.27, 0.62, cz + 0.05))
    M.box("Specimen", (cx - 0.2, h - 0.04 - 0.002, cz - 0.4), (cx + 0.2, h - 0.04, cz - 0.38))


def prop_bunk(b, M):
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    bx(M, "Steel", b, 0, 1, h - 0.18, h - 0.12, 0, 1)
    bx(M, "Mattress", b, 0.02, 0.98, h - 0.12, h, 0.05, 0.95)
    for fx in (0.01, 0.95):
        bx(M, "Steel", b, fx, fx + 0.04, 0, h - 0.18, 0.05, 0.12)
        bx(M, "Steel", b, fx, fx + 0.04, 0, h - 0.18, 0.88, 0.95)


def prop_console(b, M):
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    bx(M, "Paint_Dark", b, 0.0, 1.0, 0.0, h - 0.25, 0.0, 1.0)
    bx(M, "Plastic_Black", b, 0.0, 1.0, h - 0.25, h - 0.2, 0.0, 1.0)
    for i in range(6):                                  # the sloping panel with six small screens
        f0, f1 = i / 6 + 0.01, (i + 1) / 6 - 0.01
        x0, x1 = mn[0] + f0 * (mx[0] - mn[0]), mn[0] + f1 * (mx[0] - mn[0])
        z0 = mn[2] + 0.05
        M.box("Paint_Dark", (x0, h - 0.2, z0), (x1, h, z0 + 0.25))
        M.quad("Screen_Emit", [(x0 + 0.05, h - 0.17, z0 + 0.25 + 0.001), (x1 - 0.05, h - 0.17, z0 + 0.25 + 0.001),
                               (x1 - 0.05, h - 0.03, z0 + 0.25 + 0.001), (x0 + 0.05, h - 0.03, z0 + 0.25 + 0.001)], region=("scr", i + 2))
        M.box("Plastic_Black", (x0 + 0.1, h - 0.2, z0 + 0.4), (x1 - 0.1, h - 0.18, z0 + 0.6))


def prop_monitors(b, M):
    """The wall of monitors: a black frame and twelve screens, four by three, facing the chair."""
    mn, mx = b["min"], b["max"]
    h = mx[1] - mn[1]
    bx(M, "Plastic_Black", b, 0, 1, 0.0, h, 0.0, 0.6)
    bx(M, "Paint_Dark", b, 0, 1, 0.0, 0.5, 0.6, 1.0)
    zf = mn[2] + 0.6 * (mx[2] - mn[2]) + 0.001
    k = 0
    for row in range(3):
        for col in range(4):
            x0 = mn[0] + 0.08 + col * (mx[0] - mn[0] - 0.16) / 4
            x1 = x0 + (mx[0] - mn[0] - 0.16) / 4 - 0.06
            y0 = 0.62 + row * (h - 0.7) / 3
            y1 = y0 + (h - 0.7) / 3 - 0.06
            M.quad("Screen_Emit", [(x0, y0, zf), (x1, y0, zf), (x1, y1, zf), (x0, y1, zf)], region=("scr", k))
            k += 1
    M.box("Plastic_Black", (mn[0], 0.5, zf - 0.001), (mx[0], 0.62, mx[2]))


def prop_glass(b, M):
    """A window in a wall: a steel frame the wall's depth and one clear pane."""
    mn, mx = b["min"], b["max"]
    f = 0.05
    if mx[2] - mn[2] < mx[0] - mn[0]:
        M.box("Door_Frame", (mn[0], mn[1], mn[2]), (mx[0], mn[1] + f, mx[2]))
        M.box("Door_Frame", (mn[0], mx[1] - f, mn[2]), (mx[0], mx[1], mx[2]))
        M.box("Door_Frame", (mn[0], mn[1] + f, mn[2]), (mn[0] + f, mx[1] - f, mx[2]))
        M.box("Door_Frame", (mx[0] - f, mn[1] + f, mn[2]), (mx[0], mx[1] - f, mx[2]))
        cz = (mn[2] + mx[2]) / 2
        M.box("Glass_Clear", (mn[0] + f, mn[1] + f, cz - 0.004), (mx[0] - f, mx[1] - f, cz + 0.004))
    else:
        M.box("Door_Frame", (mn[0], mn[1], mn[2]), (mx[0], mn[1] + f, mx[2]))
        M.box("Door_Frame", (mn[0], mx[1] - f, mn[2]), (mx[0], mx[1], mx[2]))
        M.box("Door_Frame", (mn[0], mn[1] + f, mn[2]), (mx[0], mx[1] - f, mn[2] + f))
        M.box("Door_Frame", (mn[0], mn[1] + f, mx[2] - f), (mx[0], mx[1] - f, mx[2]))
        cx = (mn[0] + mx[0]) / 2
        M.box("Glass_Clear", (cx - 0.004, mn[1] + f, mn[2] + f), (cx + 0.004, mx[1] - f, mx[2] - f))


PROPS_BY = {"Bench": prop_bench, "Crate": prop_crate, "Pallet": prop_pallet, "Forklift": prop_forklift, "Pillar": prop_pillar, "Shelf": prop_shelf,
            "Desk": prop_desk, "Lockers": prop_lockers, "Barrier": prop_barrier, "Planter": prop_planter, "Hood": prop_hood, "Tank": prop_tank,
            "Breaker": prop_breaker, "Trafo": prop_trafo, "Cabinet": prop_rack_like, "Cubicle": prop_cubicle, "Bunk": prop_bunk,
            "Console": prop_console, "Monitors": prop_monitors, "Glass": prop_glass}


def screen_uv(M):
    """Each screen quad shows one cell of the screens' atlas (4 x 2), picked by its index."""
    cells = {}
    for f, r in M.region.items():
        if isinstance(r, tuple) and r[0] == "scr":
            cells[f] = (r[1] * 5 + len(SCENE)) % 8
        elif isinstance(r, tuple) and r[0] == "cell":
            cells[f] = r[1]

    def fn(face, uvl):
        if face not in cells:
            return False
        k = cells[face]
        ci, cj = k % 4, k // 4
        lps = list(face.loops)
        corners = [(0, 0), (1, 0), (1, 1), (0, 1)]
        for lp, (u, v) in zip(lps, corners):
            lp[uvl].uv = ((ci + 0.02 + 0.96 * u) / 4, 1 - (cj + 0.02 + 0.96 * (1 - v)) / 2)
        return True
    return fn


def build_props():
    for b in cols_of(S):
        n = b["name"]
        if is_shell(n) or n.startswith(SEPARATE):
            continue
        kind = re.match(r"[A-Za-z]+", n).group(0)
        fn = PROPS_BY.get(kind)
        assert fn, ("no model for", n)
        M = Model(n)
        fn(b, M)
        uv = None
        if kind == "Cabinet":
            uv = rack_uv(b["min"], b["max"], 2 if (b["max"][0] - b["min"][0]) >= (b["max"][2] - b["min"][2]) else 0)
        elif M.region:
            uv = screen_uv(M)
        M.done(COLL["Props"], uv)


# ---------------------------------------------------------------- the arena's own objects
def build_separate():
    sep = COLL["Separate"]
    racks = [b for b in S.boxes if b["name"].startswith("Rack_")]
    if racks:
        r0 = racks[0]
        w, d, h = (r0["max"][0] - r0["min"][0]), (r0["max"][2] - r0["min"][2]), r0["max"][1] - r0["min"][1]
        M = Model("Rack_mesh")
        M.box("Server_Body", (-w / 2, 0.06, -d / 2), (w / 2, h, d / 2))
        M.box("Server_Body", (-w / 2 + 0.03, 0.0, -d / 2 + 0.03), (w / 2 - 0.03, 0.06, d / 2 - 0.03))
        ob = M.done(sep, rack_uv((-w / 2, 0.0, -d / 2), (w / 2, h, d / 2), 2))
        me = ob.data
        bpy.data.objects.remove(ob)
        for b in racks:
            o = bpy.data.objects.new(b["name"], me)
            o.location = Bv(((b["min"][0] + b["max"][0]) / 2, b["min"][1], (b["min"][2] + b["max"][2]) / 2))
            for k, v in b["props"].items():
                o[k] = v
            sep.objects.link(o)
    for b in S.boxes:
        n = b["name"]
        if n.startswith("FloorPanel_"):
            M = Model(n)
            mn, mx = b["min"], b["max"]
            mat = "Panel_A" if b["mat"] == "panel_a" else "Panel_B"
            M.quad(mat, [(mn[0], mx[1], mx[2]), (mx[0], mx[1], mx[2]), (mx[0], mx[1], mn[2]), (mn[0], mx[1], mn[2])])
            side_faces(M, mat, mn, mx, top=False)
            o = M.done(sep, panel_uv(mn, mx))
            for k, v in b["props"].items():
                o[k] = v
            o["fill_sides"] = 1
        elif n.startswith("CeilingPanel_"):
            M = Model(n)
            mn, mx = b["min"], b["max"]
            M.quad("Ceiling_Panel", [(mn[0], mn[1], mn[2]), (mx[0], mn[1], mn[2]), (mx[0], mn[1], mx[2]), (mn[0], mn[1], mx[2])])
            side_faces(M, "Ceiling_Panel", mn, mx, top=True)
            o = M.done(sep, panel_uv(mn, mx))
            for k, v in b["props"].items():
                o[k] = v
            o["fill_sides"] = 1
        elif n == "Chair_control":
            M = Model(n)
            mn, mx = b["min"], b["max"]
            cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
            for k in range(5):
                ang = k * 2 * math.pi / 5
                M.box("Plastic_Black", (cx + 0.36 * math.cos(ang) - 0.025, 0.0, cz + 0.36 * math.sin(ang) - 0.025),
                      (cx + 0.36 * math.cos(ang) + 0.025, 0.06, cz + 0.36 * math.sin(ang) + 0.025))
                M.box("Plastic_Black", (cx + 0.18 * math.cos(ang) - 0.03, 0.05, cz + 0.18 * math.sin(ang) - 0.03),
                      (cx + 0.18 * math.cos(ang) + 0.03, 0.09, cz + 0.18 * math.sin(ang) + 0.03))
            M.box("Plastic_Black", (mn[0], 0.0, mn[2]), (mn[0] + 0.02, 0.02, mn[2] + 0.02))
            M.box("Plastic_Black", (mx[0] - 0.02, 0.0, mx[2] - 0.02), (mx[0], 0.02, mx[2]))
            M.cyl("Steel", (cx, 0.06, cz), (cx, 0.45, cz), 0.03, seg=10)
            M.box("Fabric", (cx - 0.26, 0.45, cz - 0.25), (cx + 0.26, 0.55, cz + 0.25))
            M.box("Fabric", (cx - 0.24, 0.6, cz + 0.27), (cx + 0.24, mx[1], cz + 0.35))
            M.box("Steel", (cx - 0.03, 0.5, cz + 0.22), (cx + 0.03, 0.62, cz + 0.32))
            for sx in (-1, 1):
                M.box("Plastic_Black", (cx + sx * 0.27, 0.62, cz - 0.15), (cx + sx * 0.3, 0.66, cz + 0.12))
                M.box("Plastic_Black", (cx + sx * 0.28 - 0.01, 0.55, cz + 0.0), (cx + sx * 0.28 + 0.01, 0.62, cz + 0.02))
            o = M.done(sep)
            for k, v in b["props"].items():
                o[k] = v


def side_faces(M, mat, mn, mx, top):
    """A panel's four edges (and, for a ceiling panel, nothing on top): seen only once a neighbour has gone."""
    y0, y1 = mn[1], mx[1]
    M.quad(mat, [(mn[0], y0, mn[2]), (mx[0], y0, mn[2]), (mx[0], y1, mn[2]), (mn[0], y1, mn[2])][::-1], region="side")
    M.quad(mat, [(mn[0], y0, mx[2]), (mx[0], y0, mx[2]), (mx[0], y1, mx[2]), (mn[0], y1, mx[2])], region="side")
    M.quad(mat, [(mn[0], y0, mn[2]), (mn[0], y0, mx[2]), (mn[0], y1, mx[2]), (mn[0], y1, mn[2])], region="side")
    M.quad(mat, [(mx[0], y0, mn[2]), (mx[0], y0, mx[2]), (mx[0], y1, mx[2]), (mx[0], y1, mn[2])][::-1], region="side")


def panel_uv(mn, mx):
    """The panel's texture spans its top exactly (2 m floor panels, 4 m ceiling panels); the edges take a strip of it."""
    def f(face, uvl):
        for lp in face.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y
            u = (gx - mn[0]) / (mx[0] - mn[0])
            v = (gz - mn[2]) / (mx[2] - mn[2])
            if abs(face.normal.z) < 0.5:
                v = 0.02 + 0.02 * (gy - mn[1]) / (mx[1] - mn[1])
                if abs(face.normal.x) > 0.5:
                    u = (gz - mn[2]) / (mx[2] - mn[2])
            lp[uvl].uv = (u, v)
        return True
    return f


def build_cams():
    """Each camera: a fixed mount (a pole from the ceiling, or a wall bracket) and its rig SecCam_<nn>_rig, one shared mesh, origin at the
    swivel, its -Y the way it looks, tilted down 18 degrees as the camera's tilt base is."""
    if not S.cams:
        return
    M = Model("Cam_rig_mesh")
    tilt = math.radians(-18.0)
    v = M.box("Cam_Body", (-0.012, -0.06, -0.012), (0.012, 0.0, 0.012), region="bracket")
    hv = list(M.box("Cam_Body", (-0.075, -0.17, 0.02), (0.075, -0.05, 0.34), region="body"))
    hv += list(M.box("Cam_Body", (-0.09, -0.04, 0.0), (0.09, -0.03, 0.38), region="body"))
    hv += list(M.cyl("Cam_Body", (0, -0.11, 0.34), (0, -0.11, 0.352), 0.05, seg=12, region="lens"))
    hv += list(M.box("Cam_Body", (0.045, -0.065, 0.341), (0.065, -0.05, 0.346), region="led"))
    M.rotate(hv, -tilt, (1, 0, 0), (0, -0.06, 0))
    del v
    ob = M.done(COLL["Separate"])
    me = ob.data
    bpy.data.objects.remove(ob)
    mounts = Model("decor_cam_mounts")
    for c in S.cams:
        p = c["pos"]
        ctop = ceiling_at(p[0], p[2])
        mounts.cyl("Steel_Dark", (p[0], p[1], p[2]), (p[0], ctop, p[2]), 0.02, seg=8)
        mounts.cyl("Steel_Dark", (p[0], ctop - 0.02, p[2]), (p[0], ctop, p[2]), 0.06, seg=10)
        o = bpy.data.objects.new(c["name"] + "_rig", me)
        o.location = Bv(p)
        o.rotation_euler = (0, 0, math.atan2(c["face"][0], c["face"][1]))
        o["camera"] = c["name"]
        COLL["Separate"].objects.link(o)
    mounts.done(COLL["Props"])


def ceiling_at(x, z):
    hs = [s["h"] for s in S.spaces if s["x0"] - 0.35 <= x <= s["x1"] + 0.35 and s["z0"] - 0.35 <= z <= s["z1"] + 0.35]
    return max(hs) if hs else 3.0


# ---------------------------------------------------------------- the greybox's decor boxes, dressed
def build_decor():
    D = Model("decor_details")
    arches = []
    for b in S.boxes:
        n = b["name"]
        if b["col"] or not b.get("art", True) or b.get("zone") or n.endswith("_rig"):
            continue
        mn, mx = b["min"], b["max"]
        if n.startswith("decor_stripe"):
            D.box("Stripe_Pink", mn, mx)
        elif n.startswith("decor_scanner_arch"):
            D.box("Plastic_Grey", mn, (mx[0], mx[1] - 0.05, mx[2]))
            D.box("Plastic_Black", (mn[0], mx[1] - 0.05, mn[2]), mx)
            arches.append(b)
        elif n.startswith("decor_cell_bar"):
            cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
            D.cyl("Steel", (cx, mn[1], cz), (cx, mx[1], cz), 0.022, seg=8)
        elif n.startswith("decor_control_room_window"):
            D.quad("Screen_Window", [(mn[0], mn[1], mx[2]), (mn[0], mn[1], mn[2]), (mn[0], mx[1], mn[2]), (mn[0], mx[1], mx[2])])
            D.box("Door_Frame", (mn[0] - 0.02, mn[1] - 0.08, mn[2] - 0.08), (mx[0], mn[1], mx[2] + 0.08))
            D.box("Door_Frame", (mn[0] - 0.02, mx[1], mn[2] - 0.08), (mx[0], mx[1] + 0.08, mx[2] + 0.08))
            D.box("Door_Frame", (mn[0] - 0.02, mn[1], mn[2] - 0.08), (mx[0], mx[1], mn[2]))
            D.box("Door_Frame", (mn[0] - 0.02, mn[1], mx[2]), (mx[0], mx[1], mx[2] + 0.08))
        elif n.startswith(("decor_control_room_sign", "decor_vault_sign")):
            D.box("Sign_Plate", mn, mx)
            txt = "CONTROL" if "control" in n else "VAULT  3"
            x = mn[0] - 0.003
            D.text("Plastic_Black", txt, (mx[1] - mn[1]) * 0.55, 0.004, (x, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2), (0, 0, 1), (0, 1, 0), (-1, 0, 0))
        elif n.startswith("decor_cable_tray"):
            D.box("Steel", mn, (mx[0], mn[1] + 0.01, mx[2]))
            D.box("Steel", mn, (mx[0], mx[1], mn[2] + 0.01))
            D.box("Steel", (mn[0], mn[1], mx[2] - 0.01), mx)
            for k in range(6):
                z0 = mn[2] + 0.04 + k * (mx[2] - mn[2] - 0.08) / 6
                D.box("Cable", (mn[0], mn[1] + 0.01, z0), (mx[0], mn[1] + 0.04, z0 + 0.05))
        elif n.startswith("decor_lift_panel"):
            D.box("Steel", mn, mx)
            for k in range(4):
                y = mn[1] + 0.1 + k * 0.09
                D.cyl("Emergency_Emit" if k == 0 else "Plastic_White", (mn[0] - 0.002, y, (mn[2] + mx[2]) / 2), (mn[0] - 0.012, y, (mn[2] + mx[2]) / 2), 0.025, seg=10)
        else:
            D.box("Paint_Grey", mn, mx)
    for i in range(0, len(arches) - 1, 2):                   # the scanner arches: a header across each pair of posts
        a, b = arches[i], arches[i + 1]
        mn = [min(a["min"][k], b["min"][k]) for k in range(3)]
        mx = [max(a["max"][k], b["max"][k]) for k in range(3)]
        D.box("Plastic_Black", (mn[0], mx[1] - 0.12, mn[2]), (mx[0], mx[1], mx[2]))
        cxm, czm = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
        D.box("Emergency_Emit", (cxm - 0.05, mx[1] - 0.14, czm - 0.05), (cxm + 0.05, mx[1] - 0.12, czm + 0.05))
    D.done(COLL["Props"])


# ---------------------------------------------------------------- signs, readers, clocks, extinguishers
SIGN_TEXT = {"service_entry": "SERVICE", "hidden_entry": "", "b2_entry": "B2", "checkpoint_1": "CHECKPOINT 1", "checkpoint_2": "CHECKPOINT 2",
             "checkpoint_3": "CHECKPOINT 3", "corridors_a": "SECTION A", "corridors_b": "SECTION B", "labs_a": "LABS A", "labs_b": "LABS B",
             "breaker_room": "PLANT", "registrar_hall": "REGISTRY", "control_room": "CONTROL", "laboratory": "LAB  B2", "repeating_room": "",
             "freight_lift": "", "pool_dive": ""}


def link_doors():
    """[(door, link id, goes_to scene key)] of the doors that are links (their leaf carries goes_to)."""
    out = []
    for d in S.doors:
        if "link_door" in d["props"]:
            did = d["props"]["link_door"]
            tgt = S.links[did][0].split()[0] if did in S.links else ""
            key = did if did in SIGN_TEXT else re.sub(r"_(west|east)$", "", did)
            out.append((d, did, key, tgt))
    return out


def build_signs(quads):
    """Above every link door: its destination on a white plate, a green exit sign over the doors that lead back out, a red beacon (alarm);
    a keycard reader by every reader spot; hazard tape on the floor before every keycard door."""
    P = Model("decor_signs")
    for d, did, key, tgt in link_doors():
        cx, cz, run = door_centre(d)
        nrm = (-run[1], run[0])
        into = (d["props"].get("swing_deg", 90) > 0)
        # the inward normal: the side of the wall the room is on
        inward = None
        for sg in (-1, 1):
            p = (cx + nrm[0] * sg * 0.3, 1.0, cz + nrm[1] * sg * 0.3)
            if any(_in(p, x[0], x[1]) for x in air_boxes(S)):
                inward = (nrm[0] * sg, nrm[1] * sg)
                break
        if inward is None:
            continue
        top = ceiling_at(cx + inward[0] * 0.3, cz + inward[1] * 0.3)
        right = (inward[1], 0, -inward[0])                  # the reader's right, facing the wall
        normal = (inward[0], 0, inward[1])
        txt = SIGN_TEXT.get(key, key.replace("_", " ").upper())
        y = d["props"]["height"] + 0.32
        if txt and y + 0.12 < top - 0.05:
            w = 0.16 * len(txt) * 0.62 + 0.3
            c0 = (cx + inward[0] * 0.006, y, cz + inward[1] * 0.006)
            P.box("Sign_Plate", (c0[0] - abs(right[0]) * w / 2 - inward[0] * 0.006, y - 0.11, c0[2] - abs(right[2]) * w / 2 - inward[1] * 0.006),
                  (c0[0] + abs(right[0]) * w / 2, y + 0.11, c0[2] + abs(right[2]) * w / 2))
            P.text("Plastic_Black", txt, 0.15, 0.004, (cx + inward[0] * 0.007, y, cz + inward[1] * 0.007), right, (0, 1, 0), normal)
            tier = d["props"].get("keycard_tier")
            if tier:
                yy = y - 0.2
                P.box("Stripe_Red", (cx - abs(right[0]) * 0.35 - inward[0] * 0.0, yy - 0.06, cz - abs(right[2]) * 0.35),
                      (cx + abs(right[0]) * 0.35 + inward[0] * 0.006, yy + 0.06, cz + abs(right[2]) * 0.35 + inward[1] * 0.006))
                P.text("Plastic_White", f"TIER {tier}", 0.09, 0.003, (cx + inward[0] * 0.007, yy, cz + inward[1] * 0.007), right, (0, 1, 0), normal)
        # the alarm beacon over the door
        by = min(top - 0.12, d["props"]["height"] + 0.62)
        bxp = cx + right[0] * 0.75
        bzp = cz + right[2] * 0.75
        P.box("Plastic_Black", (bxp - 0.07 if inward[0] == 0 else bxp, by - 0.07, bzp - 0.07 if inward[1] == 0 else bzp),
              (bxp + 0.07 if inward[0] == 0 else bxp + inward[0] * 0.05, by - 0.05, bzp + 0.07 if inward[1] == 0 else bzp + inward[1] * 0.05))
        P.cyl("Emergency_Emit", (bxp + inward[0] * 0.03, by - 0.05, bzp + inward[1] * 0.03), (bxp + inward[0] * 0.03, by + 0.06, bzp + inward[1] * 0.03), 0.045, seg=10)
        ALARM.append(((bxp + inward[0] * 0.12, by, bzp + inward[1] * 0.12), 45.0))
        # the exit sign on doors that lead back toward an entry
        if not S.links.get(did, ("", True))[1] or did in ("laboratory", "repeating_room"):
            ex = cx - right[0] * 0.75
            ez = cz - right[2] * 0.75
            ey = by - 0.02
            P.box("Sign_Emit", (ex - abs(right[0]) * 0.17, ey - 0.07, ez - abs(right[2]) * 0.17),
                  (ex + abs(right[0]) * 0.17 + inward[0] * 0.025, ey + 0.07, ez + abs(right[2]) * 0.17 + inward[1] * 0.025))
        if d["props"].get("keycard_tier"):
            P.box("Hazard", (cx + inward[0] * 0.05 - abs(right[0]) * 0.7, 0.0, cz + inward[1] * 0.05 - abs(right[2]) * 0.7),
                  (cx + inward[0] * 0.15 + abs(right[0]) * 0.7, 0.002, cz + inward[1] * 0.15 + abs(right[2]) * 0.7))
    for e in S.empties:
        if e["name"].startswith("Spot_reader"):
            fx, fz = e["face"]
            wx, wz = e["pos"][0] + fx * 0.45, e["pos"][2] + fz * 0.45
            P.box("Plastic_Black", (wx - 0.06 * abs(fz) - (fx * 0.03 if fx else 0), 1.1, wz - 0.06 * abs(fx) - (fz * 0.03 if fz else 0)),
                  (wx + 0.06 * abs(fz), 1.3, wz + 0.06 * abs(fx)))
            P.box("Emergency_Emit", (wx - 0.02 * abs(fz) - fx * 0.032, 1.26, wz - 0.02 * abs(fx) - fz * 0.032), (wx + 0.02 * abs(fz) - fx * 0.03, 1.28, wz + 0.02 * abs(fx) - fz * 0.03))
            P.box("Sign_Emit", (wx - 0.02 * abs(fz) - fx * 0.032, 1.12, wz - 0.02 * abs(fx) - fz * 0.032), (wx + 0.02 * abs(fz) - fx * 0.03, 1.14, wz + 0.02 * abs(fx) - fz * 0.03))
    P.done(COLL["Props"])


def build_walldress(quads):
    """A few things on the walls of each space: a stopped clock, a notice board, a fire extinguisher, a room plate. All within 5 cm of the wall
    (decor_: they never stand in the way)."""
    P = Model("decor_walls")
    rng = np.random.default_rng(len(SCENE) * 31 + 7)
    used = set()
    doors = edge_doors(S)
    for q in sorted(wall_faces(quads), key=lambda q: -(q["u"][1] - q["u"][0])):
        if q["space"] < 0 or q["space"] in used or q["u"][1] - q["u"][0] < 3.0 or q["v"][0] > 0.01 or q["v"][1] < 2.3:
            continue
        sp = S.spaces[q["space"]]
        if sp["wmat"] in ("tile", "steel", "server_green", "cell"):
            continue
        holes = doors_on(q, doors)
        mid = (q["u"][0] + q["u"][1]) / 2
        if any(abs(h - mid) < 1.5 for h in holes):
            continue
        used.add(q["space"])
        a, side, c = q["axis"], q["side"], q["c"]
        normal = (side, 0, 0) if a == 0 else (0, 0, side)
        right = (0, 0, -side) if a == 0 else (side, 0, 0)

        def at(u, y, d):
            return (c + side * d, y, u) if a == 0 else (u, y, c + side * d)

        k = int(rng.integers(0, 3))
        if k == 0 or sp["kind"] == "corridor":
            p0, p1 = at(mid - 0.6, 1.2, 0.0), at(mid + 0.6, 2.0, 0.015)
            P.box("Notice", [min(p0[i], p1[i]) for i in range(3)], [max(p0[i], p1[i]) for i in range(3)])
        else:
            p0, p1 = at(mid - 0.2, 2.15, 0.0), at(mid + 0.2, 2.55, 0.04)
            P.box("Clock_Face", [min(p0[i], p1[i]) for i in range(3)], [max(p0[i], p1[i]) for i in range(3)])
        e = mid + (1.2 if rng.random() < 0.5 else -1.2)
        if q["u"][0] + 0.3 < e < q["u"][1] - 0.3 and not any(abs(h - e) < 0.8 for h in holes):
            p0, p1 = at(e - 0.12, 0.4, 0.0), at(e + 0.12, 1.0, 0.04)
            P.box("Stripe_Red", [min(p0[i], p1[i]) for i in range(3)], [max(p0[i], p1[i]) for i in range(3)])
            p0, p1 = at(e - 0.07, 1.0, 0.0), at(e + 0.07, 1.1, 0.04)
            P.box("Plastic_Black", [min(p0[i], p1[i]) for i in range(3)], [max(p0[i], p1[i]) for i in range(3)])
    P.done(COLL["Props"], fit_uv(P, ("Notice", "Clock_Face")))


def fit_uv(M, mats):
    """The whole texture once across each vertical face of these materials (a notice board, a clock face)."""
    idx = {M.mats.index(m) for m in mats if m in M.mats}

    def fn(face, uvl):
        if face.material_index not in idx or abs(face.normal.z) > 0.5:
            return False
        n = face.normal
        horiz = Vector((-n.y, n.x, 0)).normalized()
        pts = [lp.vert.co for lp in face.loops]
        us = [p.dot(horiz) for p in pts]
        vs = [p.z for p in pts]
        for lp in face.loops:
            p = lp.vert.co
            lp[uvl].uv = ((p.dot(horiz) - min(us)) / max(max(us) - min(us), 1e-6), (p.z - min(vs)) / max(max(vs) - min(vs), 1e-6))
        return True
    return fn


# ---------------------------------------------------------------- light fittings and the lights
LIGHTS = []        # (kind, pos, size, power, colour) for the normal set
ALARM = []         # (pos, power) red point lamps for the alarm set
TINT = {"breaker_room": (1.0, 0.64, 0.34), "registrar_hall": (0.80, 1.0, 0.86), "control_room": (0.80, 0.96, 1.0), "hidden_entry": (1.0, 0.86, 0.66),
        "service_entry": (0.92, 0.97, 1.0)}


def build_fittings():
    """Ceiling fittings in every space with a ceiling: recessed troffers (0.6 x 1.2 m) on a grid in rooms, continuous strips along corridors,
    caged battens in service spaces; the arena's strips hang from steel beams under its ceiling panels. Each is a Lamp_Emit diffuser in a
    white housing, with an area light under it for the bake; and red emergency lamps on the walls for the alarm set."""
    F = Model("decor_fittings")
    for s in S.spaces:
        x0, x1, z0, z1, h = s["x0"], s["x1"], s["z0"], s["z1"], s["h"]
        w, d = x1 - x0, z1 - z0
        if not s["ceiling"] or SCENE == "registrar_hall":
            continue
        service = s["wmat"] in ("service", "cell") or s["fmat"] == "concrete"
        if min(w, d) < 3.2 or s["kind"] == "corridor":
            along = "x" if w >= d else "z"
            L = max(w, d)
            n = max(1, int(round(L / 3.0)))
            for i in range(n):
                t = (i + 0.5) / n
                cx = x0 + w * t if along == "x" else (x0 + x1) / 2
                cz = (z0 + z1) / 2 if along == "x" else z0 + d * t
                fitting(F, cx, cz, h, (1.5, 0.16) if along == "x" else (0.16, 1.5), "batten" if service else "strip")
        else:
            nx, nz = max(1, int(round(w / 3.2))), max(1, int(round(d / 3.2)))
            for i in range(nx):
                for j in range(nz):
                    cx, cz = x0 + w * (i + 0.5) / nx, z0 + d * (j + 0.5) / nz
                    if blocked_above(cx, cz, h):
                        continue
                    fitting(F, cx, cz, h, (0.6, 1.2) if not service else (1.5, 0.16), "batten" if service else "troffer")
    if SCENE == "registrar_hall":
        arena_beams(F)
    # red emergency lamps on the walls of every space, about every 7 m
    for s in S.spaces:
        if SCENE == "registrar_hall" and s["name"] == "field":
            continue
        per = 2 * ((s["x1"] - s["x0"]) + (s["z1"] - s["z0"]))
        n = max(1, int(per / 14))
        y = min(s["h"] - 0.3, 2.6)
        pts = []
        for i in range(n):
            t = (i + 0.5) / n
            if (s["x1"] - s["x0"]) >= (s["z1"] - s["z0"]):
                pts.append(((s["x0"] + (s["x1"] - s["x0"]) * t), s["z0"] + 0.06, (0, 1)) if i % 2 == 0 else ((s["x0"] + (s["x1"] - s["x0"]) * t), s["z1"] - 0.06, (0, -1)))
            else:
                pts.append((s["x0"] + 0.06, s["z0"] + (s["z1"] - s["z0"]) * t, (1, 0)) if i % 2 == 0 else (s["x1"] - 0.06, s["z0"] + (s["z1"] - s["z0"]) * t, (-1, 0)))
        for px, pz, f in pts:
            wx, wz = px - f[0] * 0.06, pz - f[1] * 0.06
            if not wall_behind(wx - f[0] * 0.05, y, wz - f[1] * 0.05):
                continue
            F.box("Plastic_Black", (wx - 0.12 * abs(f[1]), y - 0.05, wz - 0.12 * abs(f[0])), (wx + 0.12 * abs(f[1]) + f[0] * 0.06, y + 0.05, wz + 0.12 * abs(f[0]) + f[1] * 0.06))
            F.box("Emergency_Emit", (wx - 0.1 * abs(f[1]) + f[0] * 0.06, y - 0.035, wz - 0.1 * abs(f[0]) + f[1] * 0.06),
                  (wx + 0.1 * abs(f[1]) + f[0] * 0.065, y + 0.035, wz + 0.1 * abs(f[0]) + f[1] * 0.065))
            ALARM.append(((wx + f[0] * 0.2, y, wz + f[1] * 0.2), 22.0))
    F.done(COLL["Props"])


def wall_behind(x, y, z):
    return any(_strict((x, y, z), c["min"], c["max"], 0.0) for c in cols_of(S) if c["name"].startswith(("Wall_", "Pit_")))


def blocked_above(x, z, h):
    return any(c["min"][0] - 0.3 < x < c["max"][0] + 0.3 and c["min"][2] - 0.3 < z < c["max"][2] + 0.3 and c["max"][1] > h - 0.6
               for c in cols_of(S) if not is_shell(c["name"]))


def fitting(F, cx, cz, h, size, kind):
    sx, sz = size
    tint = TINT.get(SCENE, (0.94, 0.98, 1.0))
    if kind == "troffer":
        F.box("Lamp_Housing", (cx - sx / 2 - 0.03, h - 0.012, cz - sz / 2 - 0.03), (cx + sx / 2 + 0.03, h, cz + sz / 2 + 0.03))
        F.box("Lamp_Emit", (cx - sx / 2, h - 0.016, cz - sz / 2), (cx + sx / 2, h - 0.012, cz + sz / 2))
        LIGHTS.append((cx, h - 0.03, cz, sx, sz, 70.0, tint))
    elif kind == "strip":
        F.box("Lamp_Housing", (cx - sx / 2 - 0.02, h - 0.06, cz - sz / 2 - 0.02), (cx + sx / 2 + 0.02, h, cz + sz / 2 + 0.02))
        F.box("Lamp_Emit", (cx - sx / 2, h - 0.065, cz - sz / 2), (cx + sx / 2, h - 0.06, cz + sz / 2))
        LIGHTS.append((cx, h - 0.08, cz, sx, sz, 55.0, tint))
    else:
        yb = h - 0.25 if h > 3.5 else h - 0.1
        if h > 3.5:
            for e in (-1, 1):
                ex, ez = (cx + e * sx * 0.4, cz) if sx > sz else (cx, cz + e * sz * 0.4)
                F.cyl("Steel_Dark", (ex, yb, ez), (ex, h, ez), 0.006, seg=4)
        F.box("Steel_Dark", (cx - sx / 2, yb, cz - sz / 2), (cx + sx / 2, yb + 0.07, cz + sz / 2))
        F.box("Lamp_Emit", (cx - sx / 2 + 0.03, yb - 0.035, cz - sz / 2 + 0.03), (cx + sx / 2 - 0.03, yb, cz + sz / 2 - 0.03))
        LIGHTS.append((cx, yb - 0.06, cz, sx, sz, 70.0, tint))


def arena_beams(F):
    """The arena: steel beams along x under the ceiling-panel seams (z = -6, -2, 2, 6) and round its edge, strip lights hung under them, and
    the landings' ceilings with their own strips. The beams stay when the page opens a ceiling panel on the sky."""
    H = GB.ARENA_H
    x0, x1 = -24.0, 23.0
    for z in (-10.0 + 0.15, -6.0, -2.0, 2.0, 6.0, 10.0 - 0.15):
        F.box("Beam_Steel", (x0, H - 0.45, z - 0.12), (x1, H, z + 0.12))
    for x in (-20.0, -12.0, -4.0, 4.0, 12.0, 20.0):
        F.box("Beam_Steel", (x - 0.1, H - 0.35, -10.0), (x + 0.1, H, 10.0))
    tint = TINT["registrar_hall"]
    for z in (-6.0, -2.0, 2.0, 6.0):
        for x in np.arange(-18.0, 18.1, 4.0):
            yb = 5.4
            for e in (-1, 1):
                F.cyl("Steel_Dark", (x + e * 1.0, yb, z), (x + e * 1.0, H - 0.45, z), 0.008, seg=4)
            F.box("Lamp_Housing", (x - 1.2, yb, z - 0.1), (x + 1.2, yb + 0.08, z + 0.1))
            F.box("Lamp_Emit", (x - 1.15, yb - 0.01, z - 0.07), (x + 1.15, yb, z + 0.07))
            LIGHTS.append((x, yb - 0.03, z, 2.3, 0.14, 260.0, tint))
            LIGHTS.append((x, yb + 0.1, z, 2.3, 0.14, -70.0, tint))      # the fitting's up-light onto the ceiling (negative: aimed up)
    for xa, xb in ((-24.0, -20.0), (20.0, 23.0)):
        for z in np.arange(-8.0, 8.1, 4.0):
            cx = (xa + xb) / 2
            F.box("Lamp_Housing", (cx - 0.1, H - 0.08, z - 1.2), (cx + 0.1, H, z + 1.2))
            F.box("Lamp_Emit", (cx - 0.07, H - 0.09, z - 1.15), (cx + 0.07, H - 0.08, z + 1.15))
            LIGHTS.append((cx, H - 0.12, z, 0.14, 2.3, 200.0, tint))
    # cable trays over the four rack rows, hung from the beams (they stay when racks are shot)
    for z in (-6.5, -2.5, 2.5, 6.5):
        F.box("Steel", (-19.0, 3.3, z - 0.2), (19.0, 3.32, z + 0.2))
        F.box("Steel", (-19.0, 3.32, z - 0.2), (19.0, 3.42, z - 0.19))
        F.box("Steel", (-19.0, 3.32, z + 0.19), (19.0, 3.42, z + 0.2))
        for k in range(5):
            F.box("Cable", (-19.0, 3.32, z - 0.17 + k * 0.07), (19.0, 3.37, z - 0.12 + k * 0.07))
        for x in np.arange(-18.0, 18.1, 4.0):
            F.cyl("Steel_Dark", (x, 3.42, z), (x, H - 0.45, z), 0.01, seg=4)
    # the Registrar's eye on four wall screens (it sees through the cameras)
    E = Model("decor_eye_screens")
    for x in (-10.0, 10.0):
        for z, f in ((-10.0, 1), (10.0, -1)):
            E.box("Plastic_Black", (x - 1.7, 3.3, z if f > 0 else z - 0.06), (x + 1.7, 5.3, z + 0.06 if f > 0 else z))
            zz = z + f * 0.061
            pts = [(x - 1.6, 3.4, zz), (x + 1.6, 3.4, zz), (x + 1.6, 5.2, zz), (x - 1.6, 5.2, zz)]
            E.quad("Screen_Emit", pts if f > 0 else pts[::-1], region=("cell", 7))
    E.done(COLL["Props"], screen_uv(E))
    # the pit: a dim green line of lamps round its floor (what you see if a panel goes)
    for z in (-9.9, 9.9):
        F.box("Lamp_Emit", (-19.8, -7.9, z - 0.04 * np.sign(z)), (19.8, -7.85, z))
    # big wall lamps over the pink stripe, red for the alarm
    for x in np.arange(-20.0, 20.1, 5.0):
        for z, f in ((-10.0, 1), (10.0, -1)):
            F.box("Plastic_Black", (x - 0.2, 4.4, z if f > 0 else z - 0.08), (x + 0.2, 4.6, z + 0.08 if f > 0 else z))
            F.box("Emergency_Emit", (x - 0.16, 4.43, z + f * 0.08), (x + 0.16, 4.57, z + f * 0.085))
            ALARM.append(((x, 4.5, z + f * 0.3), 90.0))


def make_lights():
    for i, (x, y, z, sx, sz, p, tint) in enumerate(LIGHTS):
        ld = bpy.data.lights.new(f"L{i:03d}", "AREA")
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = sx, sz
        ld.energy = abs(p)
        ld.color = tint
        ob = bpy.data.objects.new(f"L{i:03d}", ld)
        ob.location = Bv((x, y, z))
        if p < 0:
            ob.rotation_euler = (math.pi, 0, 0)
        COLL["Lights_Normal"].objects.link(ob)
    for i, (p, w) in enumerate(ALARM):
        ld = bpy.data.lights.new(f"E{i:03d}", "POINT")
        ld.energy = w
        ld.shadow_soft_size = 0.08
        ld.color = (1.0, 0.07, 0.04)
        ob = bpy.data.objects.new(f"E{i:03d}", ld)
        ob.location = Bv(p)
        COLL["Lights_Alarm"].objects.link(ob)


def apply_set(name):
    """normal: the lamps on, the beacons off; alarm: the beacons on, the lamps off. The screens and exit signs stay on."""
    alarm = name == "alarm"
    COLL["Lights_Normal"].hide_render = alarm
    COLL["Lights_Alarm"].hide_render = not alarm
    for mname, on in (("Lamp_Emit", not alarm), ("Emergency_Emit", alarm)):
        m = bpy.data.materials.get(mname)
        if m:
            m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = m["emit_on"] if on else 0.0


def export_strengths():
    for mname in ("Lamp_Emit", "Emergency_Emit"):
        m = bpy.data.materials.get(mname)
        if m:
            m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = m["emit_on"]


# ---------------------------------------------------------------- the whole scene
def build_all():
    global LIGHTS, ALARM
    LIGHTS, ALARM = [], []
    reset()
    collections()
    make_materials()
    build_layout()
    build_arch()
    quads = skin(S)
    build_shell(quads)
    build_trims(quads)
    build_doors(quads)
    build_props()
    build_separate()
    build_cams()
    build_decor()
    build_signs(quads)
    build_walldress(quads)
    build_fittings()
    make_lights()
    w = bpy.data.worlds.new("Dark")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
    bg.inputs["Strength"].default_value = 0.0
    apply_set("normal")
    print(f"ART {SCENE}: {len(quads)} shell faces, {len(COLL['Props'].objects)} props, {len(COLL['Separate'].objects)} separate objects, "
          f"{len(COLL['Doors'].objects)} doors, {len(LIGHTS)} lights, {len(ALARM)} alarm lamps")


# ================================================================ bake
def select_only(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def base_uv(o):
    uvs = o.data.uv_layers
    if "UVMap" not in uvs:
        first = next((u for u in uvs if u.name != "lightmap"), None)
        if first is None:
            first = uvs.new(name="UVMap")
        first.name = "UVMap"
    return uvs


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


def rect_uv(objs, S_, weight=None, is_fill=None):
    """The shell page's lightmap UVs, packed by hand: every face is an axis-aligned rectangle, each its own pixel-aligned island with MARGIN_PX
    round it, shelf-packed at the highest density that fits the fixed page. weight(o): a face's density relative to the rest (the arena's far
    ceiling panels get less); is_fill(o, p): a face left out of the packing and pointed at one shared square whose light is set after the
    bake (a panel's edges). Returns (page, px/m, [(x, y, w, h, vertical, object name)], fill square (x, y, size) or None)."""
    m = MARGIN_PX
    rects, fills = [], []
    for o in objs:
        uvs = base_uv(o)
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.new(name="lightmap", do_init=False)
        uvs["UVMap"].active_render = True
        mw = o.matrix_world
        wt = weight(o) if weight else 1.0
        for p in o.data.polygons:
            if is_fill and is_fill(o, p):
                fills.append((o, p))
                continue
            vs = [mw @ o.data.vertices[i].co for i in p.vertices]
            assert len(vs) == 4, (o.name, len(vs))
            e1, e2 = vs[1] - vs[0], vs[3] - vs[0]
            rects.append((o, p, vs[0], e1, e2, e1.length, e2.length, abs(p.normal.z) < 0.5, wt))
    FS = 6

    def layout(D):
        boxes = []
        for i, r in enumerate(rects):
            w, h = r[5] * r[8], r[6] * r[8]
            pw, ph = max(1, math.ceil(w * D)), max(1, math.ceil(h * D))
            rot = ph > pw
            if rot:
                pw, ph = ph, pw
            boxes.append((ph + 2 * m, pw + 2 * m, i, rot))
        if fills:
            boxes.append((FS + 2 * m, FS + 2 * m, -1, False))
        boxes.sort(key=lambda b: (-b[0], -b[1]))
        x = y = rowh = 0
        place = {}
        for bh, bw, i, rot in boxes:
            if bw > S_:
                return None
            if x + bw > S_:
                x, y, rowh = 0, y + rowh, 0
            if y + bh > S_:
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
    pix = []
    for i, (o, p, v0, e1, e2, w, h, vert, wt) in enumerate(rects):
        x0, y0, rot = place[i]
        pw, ph = max(1, math.ceil(w * wt * D)), max(1, math.ceil(h * wt * D))
        uv = o.data.uv_layers["lightmap"].data
        for li in p.loop_indices:
            v = o.matrix_world @ o.data.vertices[o.data.loops[li].vertex_index].co
            a, b = (v - v0).dot(e1) / (w * w), (v - v0).dot(e2) / (h * h)
            u, t = (b * ph, a * pw) if rot else (a * pw, b * ph)
            uv[li].uv = ((x0 + u) / S_, (y0 + t) / S_)
        pix.append((x0, y0, ph if rot else pw, pw if rot else ph, vert, o.name))
    fsq = None
    if fills:
        fx, fy, _ = place[-1]
        fsq = (fx, fy, FS)
        corners = [(fx + 1, fy + 1), (fx + FS - 1, fy + 1), (fx + FS - 1, fy + FS - 1), (fx + 1, fy + FS - 1)]
        for o, p in fills:
            uv = o.data.uv_layers["lightmap"].data
            for k, li in enumerate(p.loop_indices):
                c = corners[k % 4]
                uv[li].uv = (c[0] / S_, c[1] / S_)
    print(f"  rect pack: {len(rects)} faces at {D:.1f} px/m on {S_}, {len(fills)} faces on the fill square")
    return S_, D, pix, fsq


def lightmap_uv(objs, page):
    """One atlas for `objs`: smart-project islands at equal texel density, packed with MARGIN_PX on the fixed page. A panel's edges are shrunk
    to a sliver first (their light is filled after the bake). Returns (page, px/m)."""
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
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        f = LM_SCALE.get(o.data.materials[0].name if o.data.materials else "", 1.0)
        if f != 1.0:
            uv = o.data.uv_layers["lightmap"].data
            for d in uv:
                d.uv = d.uv * f
    for o in objs:
        if o.get("fill_sides"):
            uv = o.data.uv_layers["lightmap"].data
            for p in o.data.polygons:
                if abs(p.normal.z) < 0.5:
                    pts = [uv[i].uv.copy() for i in p.loop_indices]
                    c = sum(pts, Vector((0, 0))) / len(pts)
                    for i in p.loop_indices:
                        uv[i].uv = c + (uv[i].uv - c) * 0.08
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=5 / page, shape_method="AABB")
    bpy.ops.object.mode_set(mode="OBJECT")
    a3 = sum(world_area(o) for o in objs)
    au = sum(uv_area(o, "lightmap") for o in objs)
    dens = page * math.sqrt(au / a3)
    print(f"  page {page}: {a3:.1f} m2, {dens:.1f} px/m")
    return page, dens


def poly_mask(S_, polys):
    """A boolean S x S mask of the UV polygons (convex), each grown by 2 px."""
    mask = np.zeros((S_, S_), bool)
    for pts in polys:
        P = np.array(pts) * S_
        x0, y0 = np.floor(P.min(0)).astype(int) - 2
        x1, y1 = np.ceil(P.max(0)).astype(int) + 2
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, S_), min(y1, S_)
        if x1 <= x0 or y1 <= y0:
            continue
        mask[y0:y1, x0:x1] = True
    return mask


def srgb_encode(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def denoise_image(img, S_):
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
    sc.render.resolution_x = sc.render.resolution_y = S_
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
    a = np.empty(S_ * S_ * 4, np.float32)
    r.pixels.foreach_get(a)
    bpy.data.images.remove(r)
    os.remove(path)
    bpy.data.objects.remove(cam)
    bpy.data.scenes.remove(sc)
    bpy.data.node_groups.remove(ng)
    return a.reshape(S_, S_, 4)


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


def make_export_objects():
    """Export: the shell objects as they are (one per material), the props merged by material (faces resting on the floor dropped), and
    the separate objects (racks, panels, rigs, the chair) as themselves."""
    if "Export" in bpy.data.collections:
        for o in list(bpy.data.collections["Export"].objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(bpy.data.collections["Export"])
    exp = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(exp)
    out = {}
    for ob in COLL["Shell"].objects:
        me = ob.data.copy()
        me.name = ob.name[len("Shell_"):]
        o2 = bpy.data.objects.new(ob.name[len("Shell_"):], me)
        exp.objects.link(o2)
        out[o2.name] = o2
    shellc = [c for c in cols_of(S) if is_shell(c["name"])]
    by_mat = {}
    for ob in COLL["Props"].objects:
        for idx, slot in enumerate(ob.material_slots):
            mname = slot.material.name
            tmp = bmesh.new()
            tmp.from_mesh(ob.data)
            tmp.transform(ob.matrix_world)
            bad = [f for f in tmp.faces if f.material_index != idx or (f.normal.z < -0.99 and abs(f.calc_center_median().z) < 0.003)
                   or pressed(f, shellc)]
            bmesh.ops.delete(tmp, geom=bad, context="FACES")
            for f in tmp.faces:
                f.material_index = 0
            me = bpy.data.meshes.new("tmp")
            tmp.to_mesh(me)
            tmp.free()
            bm = by_mat.setdefault(mname, bmesh.new())
            bm.from_mesh(me)
            bpy.data.meshes.remove(me)
    for mname, bm in sorted(by_mat.items()):
        name = mname if mname not in out else mname + "_props"
        assert mname not in out, ("a material on both pages", mname)
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


def pressed(f, cols):
    """A face whose front 3 mm is inside a wall, floor or ceiling box: never seen (the back of a stripe, a sign, a frame)."""
    c, n = f.calc_center_median(), f.normal
    g = (c.x + n.x * 0.003, c.z + n.z * 0.003, -(c.y + n.y * 0.003))
    return any(_strict(g, o["min"], o["max"], 1e-4) for o in cols)


def reps():
    """The separate objects that carry their own lightmap islands: every panel and the chair; one rack, one camera rig and one leaf of each
    kind (the others share their mesh, and so their islands)."""
    seen, out = set(), []
    for o in sorted(list(COLL["Separate"].objects) + list(COLL["Doors"].objects), key=lambda o: o.name):
        if o.type != "MESH" or o.data.name in seen:
            continue
        seen.add(o.data.name)
        out.append(o)
    return out


def bake_image(objs, S_, samples, prefill=None, margin=MARGIN_PX):
    bpy.context.scene.cycles.samples = samples
    img = bpy.data.images.new("LM_bake", S_, S_, alpha=False, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    if prefill is not None:
        px = np.full((S_, S_, 4), prefill, np.float32)
        px[..., 3] = 1
        img.pixels.foreach_set(px.ravel())
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
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=margin, margin_type="EXTEND", use_clear=prefill is None,
                        target="IMAGE_TEXTURES")
    for m in mats:
        for nd in [nd for nd in m.node_tree.nodes if nd.name.startswith("BAKE_TARGET")]:
            m.node_tree.nodes.remove(nd)
    a = np.empty(S_ * S_ * 4, np.float32)
    img.pixels.foreach_get(a)
    raw = a.reshape(S_, S_, 4)[..., :3].copy()
    return img, raw


def make_proxy(name, objs):
    """One mesh joining `objs` in world space with their UVs (lightmap included) and materials: Cycles bakes it as a single object (baking
    hundreds of separate objects re-syncs the scene for each)."""
    mats = []
    bm = bmesh.new()
    for o in objs:
        n0 = len(bm.faces)
        nv = len(bm.verts)
        bm.from_mesh(o.data)
        bm.faces.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        bmesh.ops.transform(bm, matrix=o.matrix_world, verts=list(bm.verts[nv:]))
        for f in bm.faces[n0:]:
            m = o.material_slots[f.material_index].material
            if m not in mats:
                mats.append(m)
            f.material_index = mats.index(m)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    bpy.data.collections["Export"].objects.link(ob)
    me.uv_layers.active = me.uv_layers["lightmap"]
    return ob


def stage_bake():
    """Two fixed pages per set. How the arena's removable parts are baked: the shell (walls, landings, the pit) with every rack and floor
    panel hidden, so the pit is lit as it is once panels have gone and no rack throws a shadow that would stay after it is shot; the floor
    panels, ceiling panels and props (pass A) with every rack hidden, so no panel holds a rack's shadow; the one rack mesh (pass B) on its own,
    its neighbours hidden and the panels under it, so all 48 racks share light that does not depend on which others still stand. A panel's
    edges are filled with a fixed fraction of the panels' median light, so a gap shows its neighbours' edges as dim steel, not baked black."""
    import time
    exp = make_export_objects()
    for c in ("Art", "Shell"):
        COLL[c].hide_render = True
    bpy.data.collections["Export"].hide_render = False
    COLL["Art"].hide_render = False
    COLL["Props"].hide_render = True
    for o in COLL["Arch"].objects:
        o.hide_render = True
    COLL["Separate"].hide_render = False
    setup_cycles(SAMPLES, bake=True)
    shell = [o for k, o in sorted(exp.items()) if o.data.materials[0].name in SHELL_MATS()]
    props = [o for k, o in sorted(exp.items()) if o not in shell and o.data.materials[0].name not in NO_LIGHTMAP]
    seps = [o for o in reps() if not all(s.material.name in NO_LIGHTMAP for s in o.material_slots)]
    rack_rep = next((o for o in seps if o.name.startswith("Rack_")), None)
    racks = [o for o in COLL["Separate"].objects if o.name.startswith("Rack_")]
    floor = [o for o in seps if o.name.startswith("FloorPanel_")]
    ceil = [o for o in seps if o.name.startswith("CeilingPanel_")]
    rest = props + [o for o in seps if o is not rack_rep and o not in floor and o not in ceil]
    page0 = shell + ceil + floor
    page1 = rest + ([rack_rep] if rack_rep else [])
    report = {"scene": SCENE, "samples": SAMPLES}
    t0 = time.time()
    S0, D0, pix, fsq = rect_uv(page0, PAGES[SCENE][0], weight=lambda o: 0.45 if o.name.startswith("CeilingPanel_") else 1.0,
                               is_fill=lambda o, p: bool(o.get("fill_sides")) and abs(p.normal.z) < 0.5)
    S1, D1 = lightmap_uv(page1, PAGES[SCENE][1])
    print(f"  uv done in {time.time() - t0:.0f} s", flush=True)
    wall = np.zeros((S0, S0), bool)
    ptop = np.zeros((S0, S0), bool)
    for x0, y0, w, h, vert, nm in pix:
        if vert and not nm.startswith(("FloorPanel_", "CeilingPanel_")):
            wall[y0:y0 + h, x0:x0 + w] = True
        if nm.startswith("FloorPanel_"):
            ptop[y0:y0 + h, x0:x0 + w] = True
    P0 = make_proxy("BakeProxy_shell", shell + ceil)
    P1 = make_proxy("BakeProxy_props", rest)
    PF = make_proxy("BakeProxy_floor", floor) if floor else None
    proxied = shell + ceil + rest + floor
    for o in proxied:
        o.hide_render = True
    raw = {}
    for st in SETS:
        apply_set(st)
        for o in racks + ([PF] if PF else []):
            o.hide_render = True
        img, r0 = bake_image([P0], S0, SAMPLES)
        s0 = denoise_image(img, S0)[..., :3]
        bpy.data.images.remove(img)
        if PF:
            PF.hide_render = False
            img, rF = bake_image([PF], S0, SAMPLES, prefill=-1.0, margin=3)
            m = rF[..., 0] >= 0
            px = np.ones((S0, S0, 4), np.float32)
            px[..., :3] = np.maximum(rF, 0)
            img.pixels.foreach_set(px.ravel())
            f = denoise_image(img, S0)[..., :3]
            bpy.data.images.remove(img)
            s0[m] = f[m]
        raw[(st, 0)] = s0
        img, rA = bake_image([P1], S1, SAMPLES)
        a = denoise_image(img, S1)[..., :3]
        bpy.data.images.remove(img)
        if rack_rep is not None:
            rack_rep.hide_render = False
            img, rB = bake_image([rack_rep], S1, SAMPLES, prefill=-1.0, margin=3)
            m = rB[..., 0] >= 0
            px = np.ones((S1, S1, 4), np.float32)
            px[..., :3] = np.maximum(rB, 0)
            img.pixels.foreach_set(px.ravel())
            b = denoise_image(img, S1)[..., :3]
            bpy.data.images.remove(img)
            a[m] = b[m]
        for o in racks:
            o.hide_render = False
        raw[(st, 1)] = a
        print(f"  baked {st} in {time.time() - t0:.0f} s", flush=True)
    for o in proxied:
        o.hide_render = False
    for P in (P0, P1, PF):
        if P:
            me = P.data
            bpy.data.objects.remove(P)
            bpy.data.meshes.remove(me)
    apply_set("normal")
    for st in SETS:
        L0 = raw[(st, 0)].max(axis=2)
        Lw = L0[wall & (L0 > 1e-6)]
        med = float(np.median(Lw)) if len(Lw) else float(np.median(L0[L0 > 1e-6]))
        y = TARGET[st]
        Gs = y / (1 - y / CURVE_C) / max(med, 1e-6)
        for n in (0, 1):
            rgb = np.maximum(raw[(st, n)], 0)
            tex = Gs * rgb / (CURVE_C + Gs * rgb)
            if n == 0 and fsq is not None:
                pk = tex.max(axis=2)
                top = pk[ptop & (pk > 1e-4)]
                fv = FILL_SIDE * float(np.median(top)) if len(top) else 0.1
                fx, fy, fs = fsq
                tex[fy - 2:fy + fs + 2, fx - 2:fx + fs + 2] = fv
            idx = n + (2 if st == "alarm" else 0)
            S_ = tex.shape[0]
            out = np.ones((S_, S_, 4), np.float32)
            out[..., :3] = srgb_encode(tex)
            png = bpy.data.images.new(f"LM_{idx}_png", S_, S_, alpha=False)
            png.colorspace_settings.name = "Non-Color"
            png.pixels.foreach_set(out.ravel())
            png.filepath_raw = str(work() / f"{SCENE}_{idx}.png")
            png.file_format = "PNG"
            png.save()
            bpy.data.images.remove(png)
            pk = rgb.max(axis=2)
            report[f"map_{idx}"] = {"set": st, "page": n, "size": S_, "px_per_m": round(D0 if n == 0 else D1, 1), "gain": round(Gs, 5), "C": CURVE_C,
                                    "wall_median_L": round(med, 5), "raw_p50_p90_p99": [round(float(v), 4) for v in np.percentile(pk[pk > 1e-6], [50, 90, 99])]}
        print(f"  {st}: G {Gs:.4f} (wall median {med:.4f})", flush=True)
    objs_by_page = {0: page0, 1: page1}
    for n, objs in objs_by_page.items():
        mats = {s.material for o in objs for s in o.material_slots if s.material.name not in NO_LIGHTMAP}
        for m in mats:
            m["lightmap"] = lm_url(SCENE, n)
            m["lightmap_intensity"] = round(math.pi * CURVE_C, 4)
            m["lightmap_night"] = lm_url(SCENE, n + 2)
            m["lightmap_night_intensity"] = round(math.pi * CURVE_C, 4)
        report[f"page_{n}_materials"] = sorted(m.name for m in mats)
    report["seconds"] = round(time.time() - t0)
    report["device"] = bpy.context.scene.cycles.device
    (work() / f"{SCENE}_bake.json").write_text(json.dumps(report, indent=1))
    stills_dir(SCENE).mkdir(parents=True, exist_ok=True)
    (stills_dir(SCENE) / "bake.json").write_text(json.dumps(report, indent=1))
    COLL["Shell"].hide_render = False
    COLL["Props"].hide_render = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


def SHELL_MATS():
    return {s.material.name for o in COLL["Shell"].objects for s in o.material_slots}


# ================================================================ privacy, saving, export
KEEP_PROPS = {"lightmap", "lightmap_intensity", "lightmap_night", "lightmap_night_intensity", "emit_on"}
LAYOUT_PREFIX = ("DoorLeaf_", "Spot_", "SecCam_", "Link_", "Arrive_", "Rack_", "FloorPanel_", "CeilingPanel_", "Chair_control")


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
                    if kind == "objects" and st is idb and (idb.name.startswith(LAYOUT_PREFIX) or k == "fill_sides"):
                        continue
                    if st is not idb and k.startswith(("cycles", "eevee")):
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
    print("SCRUB dropped", dropped)


def save_blend():
    p = blend_path(SCENE)
    p.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    try:
        bpy.context.preferences.filepaths.use_file_compression = True
    except Exception:
        pass
    bpy.ops.wm.save_as_mainfile(filepath=str(p), compress=True)
    scrub_private()
    bpy.ops.wm.save_mainfile(compress=True)


def load_scene_file():
    bpy.ops.wm.open_mainfile(filepath=str(blend_path(SCENE)))
    for n in NAMES:
        COLL[n] = bpy.data.collections.get(n)
    for m in bpy.data.materials:
        MATS[m.name] = m


def stage_export():
    export_strengths()
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    leaves = list(COLL["Doors"].objects)
    stash = {o.name: {k: o[k] for k in o.keys()} for o in leaves}
    for o in leaves:
        for k in list(o.keys()):
            del o[k]
    seps = [o for o in COLL["Separate"].objects]
    fills = {o.name: o.get("fill_sides") for o in seps}
    for o in seps:
        if "fill_sides" in o:
            del o["fill_sides"]
    emits = {m.name: m["emit_on"] for m in bpy.data.materials if "emit_on" in m}
    for m in bpy.data.materials:
        if "emit_on" in m:
            del m["emit_on"]
    bpy.ops.object.select_all(action="DESELECT")
    COLL["Separate"].hide_viewport = False
    COLL["Art"].hide_viewport = False
    for o in list(exp.objects) + leaves + seps:
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
    for o in seps:
        if fills.get(o.name):
            o["fill_sides"] = fills[o.name]
    for k, v in emits.items():
        bpy.data.materials[k]["emit_on"] = v
    print("EXPORTED", raw, raw.stat().st_size)
    exp.hide_viewport = exp.hide_render = True
    import export_scene
    export_scene.write(SCENE, ROOT / f"world/{SCENE}.json")
    save_blend()


def stage_check():
    import check_layout
    import contextlib
    import io
    for o in COLL["Arch"].objects:
        o.hide_render = False
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = check_layout.main(["--scene", SCENE, "--collection", "Art"])
    txt = buf.getvalue()
    (work() / f"{SCENE}_check_layout.txt").write_text(txt)
    print(txt[-3000:])
    print("CHECK_LAYOUT exit", code)
    for o in COLL["Arch"].objects:
        o.hide_render = True


# ================================================================ review stills
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
    ob.location = Bv(loc)
    if target is not None:
        ob.rotation_euler = (Bv(target) - Bv(loc)).to_track_quat("-Z", "Y").to_euler()
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


SHOTS = {   # 2_wide and 3_detail: (eye, target, fov); 1_arrival is the greybox's still (the first arrival going deeper)
    "registrar_hall": {"2_wide": ((-23.2, 4.2, 9.0), (8.0, 0.5, -6.0), 70), "3_detail": ((-9.0, 1.6, 0.6), (-13.0, 1.2, -2.5), 62)},
    "control_room": {"2_wide": ((-4.2, 2.4, 4.7), (2.5, 0.9, -4.0), 75), "3_detail": ((2.6, 1.55, 3.9), (-0.8, 1.2, -4.6), 66)},
    "checkpoint_1": {"2_wide": ((-11.4, 2.6, 9.4), (4.0, 0.6, -2.0), 72), "3_detail": ((-2.0, 1.55, -7.0), (0.0, 1.4, -12.0), 62)},
    "checkpoint_2": {"2_wide": ((-5.2, 2.6, 7.4), (8.0, 0.6, -6.0), 72), "3_detail": ((12.0, 1.55, 1.2), (16.0, 1.3, -0.3), 62)},
    "checkpoint_3": {"2_wide": ((-1.2, 2.6, 7.4), (12.0, 0.6, -5.0), 72), "3_detail": ((10.4, 1.55, 1.6), (14.0, 1.6, 0.0), 62)},
    "corridors_a": {"2_wide": ((-19.4, 2.3, 13.6), (19.0, 1.0, 13.0), 70), "3_detail": ((-5.4, 1.55, 3.9), (0.0, 1.0, 0.0), 70)},
    "corridors_b": {"2_wide": ((-21.4, 2.3, -9.6), (20.0, 1.0, -9.0), 70), "3_detail": ((-4.4, 1.55, 3.0), (2.0, 1.0, -1.0), 70)},
    "labs_a": {"2_wide": ((15.4, 2.6, 7.2), (2.0, 0.6, -6.0), 75), "3_detail": ((-12.0, 1.55, -1.5), (-15.6, 1.4, -4.5), 62)},
    "labs_b": {"2_wide": ((17.4, 2.7, 5.4), (-6.0, 0.6, -6.0), 75), "3_detail": ((-14.0, 1.55, -12.0), (-16.5, 1.2, -16.5), 62)},
    "breaker_room": {"2_wide": ((8.4, 2.6, 5.4), (-5.0, 0.8, -4.0), 75), "3_detail": ((-1.6, 1.55, -3.4), (-6.0, 1.1, -5.8), 62)},
    "service_entry": {"2_wide": ((9.4, 3.3, 5.4), (-6.0, 0.6, -4.0), 75), "3_detail": ((-11.0, 1.55, 2.8), (-17.0, -0.8, -1.5), 62)},
    "b2_entry": {"2_wide": ((5.4, 2.4, -3.8), (-4.0, 0.6, -12.0), 75), "3_detail": ((19.0, 1.55, -7.8), (25.0, 1.0, -8.8), 62)},
    "hidden_entry": {"2_wide": ((15.4, 2.2, 15.4), (8.0, 0.6, 10.6), 75), "3_detail": ((2.0, 1.55, 2.2), (-1.0, 1.0, -2.8), 62)},
}


def shots():
    pos, face, pitch = S.still
    e = (pos[0], pos[1] + GB.EYE, pos[2])
    t = (e[0] + face[0] * 10, e[1] + math.tan(math.radians(pitch)) * 10, e[2] + face[1] * 10)
    out = {"1_arrival": (e, t, 75)}
    out.update(SHOTS[SCENE])
    out["4_alarm"] = out["2_wide"]
    return out


def stage_render():
    sc = bpy.context.scene
    d = stills_dir(SCENE)
    d.mkdir(parents=True, exist_ok=True)
    scrub_private()
    export_strengths()
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
    for c in ("Art", "Shell", "Props", "Separate", "Doors"):
        COLL[c].hide_render = False
    for o in COLL["Arch"].objects:
        o.hide_render = True
    setup_cycles(arg("--render-samples", 96, int))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.03
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    sc.view_settings.exposure = arg("--exposure", 0.2, float)
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    which = arg("--only", "all")
    for key, (loc, tgt, fov) in shots().items():
        if which not in ("all", key):
            continue
        apply_set("alarm" if key == "4_alarm" else "normal")
        sc.view_settings.exposure = arg("--exposure", 0.2, float) + (0.8 if key == "4_alarm" else 0.0)
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
    apply_set("normal")
    sc.view_settings.exposure = arg("--exposure", 0.2, float)
    if which in ("all", "plan"):
        cols = cols_of(S)
        x0, x1 = min(c["min"][0] for c in cols) - 0.4, max(c["max"][0] for c in cols) + 0.4
        z0, z1 = min(c["min"][2] for c in cols) - 0.4, max(c["max"][2] for c in cols) + 0.4
        span = x1 - x0
        cam = look_cam("plan", ((x0 + x1) / 2, 40.0, (z0 + z1) / 2), None, ortho=span)
        cam.rotation_euler = (0, 0, 0)
        sc.camera = cam
        hidden = []
        for c in ("Shell", "Props", "Separate", "Doors"):
            for o in COLL[c].objects:
                if o.type != "MESH":
                    continue
                zs = [(o.matrix_world @ v.co).z for v in o.data.vertices]
                if (o.name.startswith(("Shell_Ceiling", "CeilingPanel_", "decor_fittings")) or (zs and min(zs) > 2.3)) and not o.hide_render:
                    o.hide_render = True
                    hidden.append(o)
        lamps = COLL["Lights_Normal"].hide_render
        COLL["Lights_Normal"].hide_render = True
        bg = sc.world.node_tree.nodes["Background"]
        bg.inputs["Color"].default_value = (1, 1, 1, 1)
        bg.inputs["Strength"].default_value = 0.7
        W = 2400
        H = max(200, int(round(W * (z1 - z0) / span)))
        sc.render.resolution_x, sc.render.resolution_y = W, H
        sc.cycles.samples = 48
        sc.view_settings.view_transform = "Standard"
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 88
        path = d / "plan.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        strip_jpeg_comments(path)
        bg.inputs["Strength"].default_value = 0.0
        bg.inputs["Color"].default_value = (0, 0, 0, 1)
        COLL["Lights_Normal"].hide_render = lamps
        for o in hidden:
            o.hide_render = False
        (work() / f"{SCENE}_plan.json").write_text(json.dumps({"x0": x0, "x1": x1, "z0": z0, "z1": z1, "w": W, "h": H}))
        print("PLAN", path, W, H)


# ================================================================ pack (plain Python, no Blender)
def pack(sc):
    from PIL import Image
    import subprocess
    import struct
    w = work()
    out = ROOT / "world/lightmaps"
    out.mkdir(parents=True, exist_ok=True)
    for i in range(4):
        png = w / f"{sc}_{i}.png"
        im = Image.open(png).convert("RGB")
        dst = out / f"{sc}_{i}.webp"
        im.save(dst, "WEBP", quality=90, method=6)
        print(f"{dst.relative_to(ROOT)}  {im.size[0]}x{im.size[1]}  {dst.stat().st_size / 1e3:.0f} KB")
    raw = w / f"{sc}_raw.glb"
    caps_p = stills_dir(sc) / "caps.json"
    caps = json.loads(caps_p.read_text()) if caps_p.exists() else {}
    b = raw.read_bytes()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    for m in j.get("materials", []):
        ex = m.get("extras", {})
        for key, kk in (("normal", "lightmap_intensity"), ("alarm", "lightmap_night_intensity")):
            f = caps.get(key, {}).get("gain", 1.0) * caps.get(key, {}).get("factor", {}).get(m["name"], 1.0)
            if kk in ex and f != 1.0:
                ex[kk] = round(ex[kk] * f, 4)
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    rest = b[20 + n:]
    total = 12 + 8 + len(js) + len(rest)
    nb = b[:8] + struct.pack("<I", total) + struct.pack("<I", len(js)) + b"JSON" + js + rest
    tmp = w / f"{sc}_capped.glb"
    tmp.write_bytes(nb)
    dst = ROOT / f"world/{sc}.glb"
    subprocess.run([sys.executable, str(ROOT / "tools/webp_glb.py"), str(tmp), str(dst), "90"], check=True)
    print(f"{dst.relative_to(ROOT)}  {dst.stat().st_size / 1e6:.2f} MB")


# ================================================================ main
def main():
    global SCENE, S
    failed = []
    for sc in arg("--scenes", "registrar_hall").split(","):
        try:
            run_scene(sc)
        except Exception:
            import traceback
            traceback.print_exc()
            failed.append(sc)
            print(f"==== {sc} FAILED")
    print("==== ALL DONE", "failed:", failed or "none")


def run_scene(sc):
    global SCENE, S
    if True:
        SCENE = sc
        S = GB.build(sc)
        print(f"==== {sc} stage {STAGE}")
        if STAGE in ("art", "all"):
            build_all()
            save_blend()
        else:
            load_scene_file()
        if STAGE in ("bake", "all"):
            stage_bake()
        if STAGE in ("export", "all"):
            stage_export()
        if STAGE in ("check", "all", "export"):
            stage_check()
        if STAGE in ("render", "all"):
            stage_render()
            save_blend()
        print(f"==== {sc} done")


if __name__ == "__main__":
    if bpy is not None:
        main()
    elif "--skin" in sys.argv:
        sc = arg("--skin")
        q = skin(GB.build(sc))
        by = {}
        for f in q:
            by.setdefault(f["mat"], [0, 0.0])
            by[f["mat"]][0] += 1
            by[f["mat"]][1] += (f["u"][1] - f["u"][0]) * (f["v"][1] - f["v"][0])
        for k, (n, a) in sorted(by.items()):
            print(f"{k:18s} {n:5d} faces {a:8.1f} m2")
        print(len(q), "faces")
    elif "--pack" in sys.argv:
        pack(arg("--pack"))
    else:
        print(__doc__)
