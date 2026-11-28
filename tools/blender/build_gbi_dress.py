"""Dresses and lights the Going back in chambers of floors L4 and L3 (docs/BLENDER_AREAS.md, section 6, step 2): `gbi_L4_1` (showroom floor),
`gbi_L4_2` (room sets), `gbi_L4_3` (stockroom), `gbi_L3_2` (white gallery), `gbi_L3_3` (colonnade) and `gbi_L3_4` (white maze).

    blender -b --factory-startup --python tools/blender/build_gbi_dress.py -- --scenes gbi_L4_1[,...] --stage art|all
    blender -b --factory-startup blender/scenes/<scene>.blend --python tools/blender/build_gbi_dress.py -- --scenes <scene> --stage bake|export|check|render
    python tools/blender/build_gbi_dress.py --pack <scene> [--work <dir>]     (no Blender: WebP lightmaps, the GLB's textures to WebP, caps.json applied)
    python tools/blender/build_gbi_dress.py --gain <scene>                     (no Blender: measures the packed GLB, writes docs/renders/<scene>/caps.json)

The hotel floors' method (tools/blender/build_hotel_floor2.py on its branch), made for the chambers. Stages: art (the greybox's layout objects,
the kit pieces as bake stand-ins, the shell as seen, the dressing, the lights; saves blender/scenes/<scene>.blend) -> bake (two light sets on
the same lightmap UVs: day, then night; the shell on one fixed 2048 page and the props on another; Cycles, OIDN, a highlight shoulder;
8-bit PNGs in the work folder) -> export (the GLB to the work folder, the layout through tools/blender/export_scene.py) -> check
(tools/blender/check_layout.py at the chamber's floor height) -> render (docs/renders/<scene>/1_arrival, 2_wide, 3_detail, 4_night and plan.jpg).
`all` runs them in that order.

The layout is the greybox's, unchanged (tools/blender/build_gbi_greybox.build(scene)): every COL_, DoorLeaf_, Marker_, Link_/Arrive_, Zone_ and
Spot_ comes from the same model, so export_scene.py writes the same world/<scene>.json as the greybox did. What is seen of the shell is
tools/blender/gbi_dress_skin.py's skin: the faces of the greybox's walls, floor, ceiling, partitions and columns that look into the air.

The connector kit's pieces are drawn by their own GLBs (world/kit/<piece>.glb), which the page places at the same `at` and `yaw`. Here each is
appended from blender/kit/<piece>.blend as a stand-in (collection `Kit`, never exported) so the bake and the stills see it. The chamber meets
them: the shell leaves out what each piece's GLB fills, and draws casings (M_GBI_kit) round the pieces whose GLB has no outside (the painted-sky
hall, the stair door's hallway) and over the safe house's dark outside.

Light: two sets on the same UVs, as the store floors and the hotel lobby: `lightmap` (day: the ceiling's fluorescent panels, `Lamp_Emit`) and
`lightmap_night` (the store shut: one panel in nine on the night circuit, `M_GBI_nightlight`, the emergency twin-spots, `Emergency_Emit`, and
the EXIT signs, M_X_exit, which are always on). Hazard_* parts are their own unbaked objects on their origins (the page moves them).

Materials (Secret Operations reskins these chambers, by name): the shell is the greybox's role materials, M_D_floor_<F>, M_D_wall_<F>,
M_D_ceil_<F>, filled from the store's own (blender/Look_Over_There.blend: M_D_floor_L4, M_U_wall_L4, M_D_ceil_L4; M_D_floor_L3, M_D_wall_L3,
M_D_ceil_L3), plus M_GBI_kit for the casings; the dressing keeps M_GBI_furn_<F>, M_D_trim, M_D_door, M_GBI_vent and M_GBI_hazard_<kind>
and adds a few store materials (M_X_*, M_U_*) and M_GBI_* of its own.
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import gbi_dress_skin as SK  # noqa: E402
GB = SK.GB

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
SAMPLES = arg("--samples", 512, int)
NIGHT_SAMPLES = arg("--night-samples", None, int) or SAMPLES
DEVICE = arg("--device", "auto")
MARGIN_PX = 8
SCENE = None
M = None              # the greybox model of SCENE
FLOOR = None

PAGES = {s: [2048, 2048] for s in SK.SCENES}     # fixed lightmap pages per scene: [shell, props]; day maps 0, 1 and night maps 2, 3
NIGHT_OFFSET = 2
WHITE_CAP = 12.0
SHOULDER = (80.0, 2.5)                           # light above the map's 80th percentile rolls off toward 2.5 x it
TARGET = {"day": {"L4": 0.50, "L3": 0.55, "L2": 0.45, "L1": 0.45, "B1": 0.55}, "night": {f: 0.15 for f in ("L4", "L3", "L2", "L1", "B1")}}   # the walls' displayed p50 the gain aims for
P99, P90 = 0.97, 0.88
WALLS = ("M_D_wall_",)

# the lights (Cycles watts) and the toggled materials' strengths
PANEL_W = {"L4": 95.0, "L3": 55.0, "L2": 40.0, "L1": 36.0, "B1": 50.0}
PANEL_EMIT, NIGHT_EMIT, EMERG_EMIT, EMERG_W, EXIT_W = 4.0, 4.0, 6.0, 22.0, 2.5
GRID = {"L4": 4.0, "L3": 4.5, "L2": 3.0, "L1": 3.0, "B1": 4.0}     # the small rooms of L2 and L1 need a tighter grid
NIGHT_EVERY = {"L4": 3, "L3": 3, "L2": 2, "L1": 2, "B1": 2}          # one panel in NIGHT_EVERY^2 stays on at night


def work():
    p = Path(arg("--work", str(Path(os.environ.get("TEMP", tempfile.gettempdir())) / "farway_gbi_dress")))
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


# ================================================================ pack, measure and gain (plain Python, no Blender)
def _glb_read(path):
    import struct
    b = Path(path).read_bytes()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    bn = struct.unpack("<I", b[20 + n:24 + n])[0]
    return j, b[28 + n:28 + n + bn]


def _glb_write(path, j, binc):
    import struct
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    binc = bytes(binc) + b"\0" * (-len(binc) % 4)
    Path(path).write_bytes(b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + 8 + len(binc)) + struct.pack("<I", len(js)) + b"JSON" + js
                           + struct.pack("<I", len(binc)) + b"BIN\x00" + binc)


def caps_of(sc):
    p = stills_dir(sc) / "caps.json"
    return json.loads(p.read_text()) if p.exists() else {}


def pack(sc):
    from PIL import Image
    import subprocess
    w = work()
    out = ROOT / "world/lightmaps"
    out.mkdir(parents=True, exist_ok=True)
    pngs = sorted(w.glob(f"{sc}_[0-9].png"))
    assert len(pngs) == 4, pngs
    for png in pngs:
        im = Image.open(png).convert("RGB")
        assert max(im.size) <= 2048
        dst = out / (png.stem + ".webp")
        im.save(dst, "WEBP", quality=90, method=6)
        print(f"{dst.relative_to(ROOT)}  {im.size[0]}x{im.size[1]}  {dst.stat().st_size / 1e3:.0f} KB")
    raw = w / f"{sc}_raw.glb"
    dst = glb_path(sc)
    subprocess.run([sys.executable, str(ROOT / "tools/webp_glb.py"), str(raw), str(dst), "90"], check=True)
    cp = caps_of(sc)
    if cp:
        j, binc = _glb_read(dst)
        n = 0
        for m in j["materials"]:
            ex = m.get("extras", {})
            for key, fkey in (("lightmap_intensity", "factor"), ("lightmap_night_intensity", "factor_night")):
                if key in ex and m["name"] in cp.get(fkey, {}):
                    ex[key] = round(ex[key] * cp[fkey][m["name"]], 4)
                    n += 1
        _glb_write(dst, j, binc)
        print(f"caps.json applied: {n} intensities")
    print(f"{dst.relative_to(ROOT)}  {dst.stat().st_size / 1e6:.2f} MB")


def measure(sc, key="lightmap"):
    """Displayed brightness per baked material, as the page shows it (lab_display.py's method): texel x intensity / pi x base colour."""
    import io
    from PIL import Image
    j, BIN = _glb_read(glb_path(sc))
    CT = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8}
    NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}

    def acc(i):
        a = j["accessors"][i]
        bv = j["bufferViews"][a["bufferView"]]
        dt = np.dtype(CT[a["componentType"]])
        nc = NC[a["type"]]
        st = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride", dt.itemsize * nc)
        raw = np.frombuffer(BIN, np.uint8, count=stride * (a["count"] - 1) + dt.itemsize * nc, offset=st)
        o = np.lib.stride_tricks.as_strided(raw, (a["count"], nc * dt.itemsize), (stride, 1)).copy().view(dt).reshape(a["count"], nc)
        return o.astype(np.float64)

    def s2l(x):
        return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
    imgs, lms = {}, {}

    def tex(t):
        tx = j["textures"][t]
        src = tx.get("extensions", {}).get("EXT_texture_webp", {}).get("source", tx.get("source"))
        if src not in imgs:
            im = j["images"][src]
            bv = j["bufferViews"][im["bufferView"]]
            imgs[src] = s2l(np.asarray(Image.open(io.BytesIO(BIN[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]])).convert("RGB"), np.float64) / 255)
        return imgs[src]

    def lmap(url):
        if url not in lms:
            lms[url] = s2l(np.asarray(Image.open(ROOT / url).convert("RGB"), np.float64) / 255)
        return lms[url]

    def sample(im, uv, wrap):
        h, w = im.shape[:2]
        u, v = (uv[:, 0] % 1.0, uv[:, 1] % 1.0) if wrap else (np.clip(uv[:, 0], 0, 1), np.clip(uv[:, 1], 0, 1))
        return im[np.clip((v * h).astype(int), 0, h - 1), np.clip((u * w).astype(int), 0, w - 1)]
    rng = np.random.default_rng(1)
    geo = {}
    for mesh in j["meshes"]:
        for p in mesh["primitives"]:
            at = p["attributes"]
            if "material" in p and "TEXCOORD_1" in at:
                geo.setdefault(p["material"], []).append((acc(at["POSITION"]), acc(at["TEXCOORD_0"]) if "TEXCOORD_0" in at else None,
                                                         acc(at["TEXCOORD_1"]), acc(p["indices"]).astype(int).reshape(-1, 3)))
    rows = {}
    for mi, parts in geo.items():
        m = j["materials"][mi]
        ex = m.get("extras", {})
        if key not in ex:
            continue
        pbr = m.get("pbrMetallicRoughness", {})
        fac = np.array(pbr.get("baseColorFactor", [1, 1, 1, 1])[:3])
        bt = pbr.get("baseColorTexture")
        base = tex(bt["index"]) if bt else None
        tt = (bt or {}).get("extensions", {}).get("KHR_texture_transform", {})
        L, k = lmap(ex[key]), ex[key + "_intensity"]
        vals, tot = [], 0.0
        for P, U0, U1, I in parts:
            a, b_, c = P[I[:, 0]], P[I[:, 1]], P[I[:, 2]]
            ar = 0.5 * np.linalg.norm(np.cross(b_ - a, c - a), axis=1)
            tot += ar.sum()
            if ar.sum() <= 0:
                continue
            N = max(2000, int(ar.sum() * 400))
            t = rng.choice(len(I), N, p=ar / ar.sum())
            r1, r2 = rng.random(N), rng.random(N)
            s = np.sqrt(r1)
            w0, w1, w2 = 1 - s, s * (1 - r2), s * r2
            tri = I[t]
            uv1 = U1[tri[:, 0]] * w0[:, None] + U1[tri[:, 1]] * w1[:, None] + U1[tri[:, 2]] * w2[:, None]
            col = fac
            if base is not None and U0 is not None:
                uv0 = U0[tri[:, 0]] * w0[:, None] + U0[tri[:, 1]] * w1[:, None] + U0[tri[:, 2]] * w2[:, None]
                if tt:
                    uv0 = uv0 * np.array(tt.get("scale", [1, 1])) + np.array(tt.get("offset", [0, 0]))
                col = fac * sample(base, uv0, True)
            vals.append(((sample(L, uv1, False) * k / math.pi) * col).max(axis=1))
        v = np.concatenate(vals)
        rows[m["name"]] = {"area": round(tot, 1), "map": Path(ex[key]).stem, "k": k, "p50": round(float(np.percentile(v, 50)), 3),
                           "p90": round(float(np.percentile(v, 90)), 3), "p99": round(float(np.percentile(v, 99)), 3)}
    return rows


def table(rows, title):
    out = [title, f"{'material':24s} {'m2':>8s} {'map':>12s} {'k':>8s} {'p50':>6s} {'p90':>6s} {'p99':>6s}"]
    for name, r in sorted(rows.items(), key=lambda kv: -kv[1]["area"]):
        out.append(f"{name:24s} {r['area']:8.1f} {r['map']:>12s} {r['k']:8.4f} {r['p50']:6.3f} {r['p90']:6.3f} {r['p99']:6.3f}")
    return "\n".join(out)


def gain(sc):
    """caps.json: per light set, one gain that brings the walls to TARGET (p50), lowered per material so none passes p99 0.97 or p90 0.88.
    Measured on the packed GLB (an existing caps.json, already applied by --pack, is divided out first)."""
    floor = sc.split("_")[1]
    old = caps_of(sc)
    out = {"target_p99": P99, "target_p90": P90}
    for st, key, fkey in (("day", "lightmap", "factor"), ("night", "lightmap_night", "factor_night")):
        rows = measure(sc, key)
        for n, r in rows.items():                       # a GLB packed with caps.json: read it as it was before them
            f0 = old.get(fkey, {}).get(n, 1.0)
            for k in ("p50", "p90", "p99"):
                r[k] = r[k] / f0
        walls = [r for n, r in rows.items() if n.startswith(WALLS)]
        wall = sum(r["p50"] * r["area"] for r in walls) / max(1e-6, sum(r["area"] for r in walls))
        g = TARGET[st][floor] / max(wall, 1e-6)
        fac = {}
        for n, r in rows.items():
            f = g
            if r["p99"] * f > P99:
                f = P99 / max(r["p99"], 1e-6)
            if r["p90"] * f > P90:
                f = min(f, P90 / max(r["p90"], 1e-6))
            fac[n] = round(f, 4)
        out[st] = {"gain": round(g, 4), "wall_p50_before": round(wall, 4), "target_wall_p50": TARGET[st][floor]}
        out[fkey] = fac
        print(f"{st}: walls p50 {wall:.3f} -> gain {g:.3f}; capped: " + ", ".join(f"{n} {f / g:.2f}" for n, f in fac.items() if f < g - 1e-4))
    stills_dir(sc).mkdir(parents=True, exist_ok=True)
    (stills_dir(sc) / "caps.json").write_text(json.dumps(out, indent=1))
    print("wrote", stills_dir(sc) / "caps.json")


if bpy is None:
    if "--pack" in args:
        pack(arg("--pack"))
    elif "--gain" in args:
        gain(arg("--gain"))
    elif "--measure" in args:
        sc = arg("--measure")
        print(table(measure(sc, "lightmap"), f"{sc}: day (lightmap)"))
        print()
        print(table(measure(sc, "lightmap_night"), f"{sc}: night (lightmap_night)"))
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
def vnoise(h, w, rng, octaves=4, base=4):
    out = np.zeros((h, w))
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        n = base * 2 ** o
        g = rng.random((n + 1, n + 1))
        g[-1, :], g[:, -1] = g[0, :], g[:, 0]
        ys, xs = np.linspace(0, n, h, endpoint=False), np.linspace(0, n, w, endpoint=False)
        y0, x0 = ys.astype(int), xs.astype(int)
        fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
        fy, fx = fy * fy * (3 - 2 * fy), fx * fx * (3 - 2 * fx)
        a = g[y0][:, x0] * (1 - fx) + g[y0][:, x0 + 1] * fx
        b = g[y0 + 1][:, x0] * (1 - fx) + g[y0 + 1][:, x0 + 1] * fx
        out += amp * (a * (1 - fy) + b * fy)
        tot += amp
        amp *= 0.5
    return out / tot


def gen_tape():
    """Yellow and black hazard tape, 45 degree stripes."""
    S = 128
    y, x = np.mgrid[0:S, 0:S]
    band = ((x + y) // 32) % 2
    img = np.where(band[..., None] == 0, np.array([232, 186, 24]), np.array([28, 26, 22]))
    return img.astype(np.uint8)


def gen_lava():
    rng = np.random.default_rng(401)
    n = vnoise(256, 256, rng, 5, 4)
    t = np.clip((n - 0.3) * 2.2, 0, 1)[..., None]
    hot, crust = np.array([255, 150, 30]), np.array([120, 18, 6])
    return (crust * (1 - t) + hot * t).astype(np.uint8)


def gen_shutter():
    S = 256
    y = np.arange(S)
    rib = 0.5 + 0.5 * np.cos(y / S * 2 * math.pi * 16)
    v = (150 + 40 * rib)[:, None] * np.ones((1, S))
    rng = np.random.default_rng(402)
    v = v * (0.92 + 0.08 * vnoise(S, S, rng, 4, 4))
    return np.clip(np.repeat(v[..., None], 3, 2) * np.array([1.0, 1.0, 0.96]), 0, 255).astype(np.uint8)


def gen_card():
    rng = np.random.default_rng(403)
    n = vnoise(256, 256, rng, 5, 6)
    base = np.array([176, 136, 90])
    img = base * (0.86 + 0.2 * n)[..., None]
    img[118:138, :] = img[118:138, :] * 0.78 + np.array([200, 190, 160]) * 0.22      # a strip of tape
    return np.clip(img, 0, 255).astype(np.uint8)


def gen_brushed():
    rng = np.random.default_rng(404)
    n = rng.random((256, 1)) * np.ones((1, 256))
    n = 0.85 + 0.15 * (0.6 * n + 0.4 * vnoise(256, 256, rng, 3, 8))
    return np.repeat((n * 205)[..., None], 3, 2).astype(np.uint8)


def gen_canvas():
    rng = np.random.default_rng(405)
    n = vnoise(256, 256, rng, 5, 16)
    v = 236 + 10 * n
    return np.repeat(v[..., None], 3, 2).clip(0, 255).astype(np.uint8)


GEN = {}


def mk_image(name, arr):
    h, w = arr.shape[:2]
    im = bpy.data.images.new(name, w, h, alpha=False)
    px = np.ones((h, w, 4), np.float32)
    px[..., :3] = arr[::-1].astype(np.float32) / 255
    im.pixels.foreach_set(px.ravel())
    im.filepath_raw = f"//generated/{name}.png"
    im.file_format = "PNG"
    im.pack()
    GEN[name] = im
    return im


# ---------------------------------------------------------------- materials
MATS, TILES = {}, {}


def set_blend(m):
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(m, attr, val)
        except (AttributeError, TypeError):
            pass


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, img=None, tint=None, emit=None, alpha=None, tile=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = 0.0
    if img:
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "UVMap"
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = img
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


STORE = ROOT / "blender/Look_Over_There.blend"


def store_material(src, name=None):
    """The store's own material, appended by name from blender/Look_Over_There.blend; its normal map is dropped (the page draws baked
    materials unlit and never reads it) and its metalness set to 0 (a baked material carries its light in the lightmap)."""
    with bpy.data.libraries.load(str(STORE), link=False) as (s, d):
        d.materials = [src]
    m = d.materials[0]
    m.name = name or src
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type == "NORMAL_MAP":
            for l in list(n.inputs["Color"].links):
                nt.nodes.remove(l.from_node)
            nt.nodes.remove(n)
    for n in nt.nodes:
        if n.type == "BSDF_PRINCIPLED":
            n.inputs["Metallic"].default_value = 0.0
    MATS[m.name] = m
    TILES[m.name] = 1.0                         # the store's UVs are in metres; its Mapping node sets the repeat
    return m


def store_model(src):
    """A store furniture model (Poly Haven, CC0), appended by name; returns (mesh in its model frame, Blender units, rotation applied)."""
    with bpy.data.libraries.load(str(STORE), link=False) as (s, d):
        d.objects = [src]
    ob = d.objects[0]
    me = ob.data.copy()
    me.transform(ob.matrix_world.to_3x3().to_4x4())
    glass = [i for i, m in enumerate(me.materials) if m and "glass" in m.name.lower()]
    if glass:                                    # a picture's glass: the page would draw it opaque over the artwork
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in glass], context="FACES")
        bm.to_mesh(me)
        bm.free()
    for sl in ob.material_slots:
        if sl.material:
            MATS[sl.material.name] = sl.material
            TILES[sl.material.name] = 1.0
            strip_material(sl.material)
    uvs = me.uv_layers
    if len(uvs):
        keep = uvs.active or uvs[0]
        keep.name = "UVMap"
        for u in list(uvs):
            if u.name != "UVMap":
                uvs.remove(u)
    bpy.data.objects.remove(ob)
    return me


def strip_material(m):
    """Only the base colour reaches the page (baked materials are drawn unlit): drop the image nodes that feed anything else (normal,
    roughness, metalness, displacement), and set metalness to 0."""
    nt = m.node_tree
    for n in nt.nodes:                           # nothing drives metalness, roughness or normals (a metallic surface bakes black)
        if n.type == "BSDF_PRINCIPLED":
            for k in ("Metallic", "Roughness", "Normal"):
                for l in list(n.inputs[k].links):
                    nt.links.remove(l)
    for n in list(nt.nodes):
        if n.type in ("NORMAL_MAP", "BUMP", "DISPLACEMENT"):
            nt.nodes.remove(n)
    for _ in range(4):                           # then every node that no longer feeds anything
        for n in list(nt.nodes):
            if n.type not in ("OUTPUT_MATERIAL", "BSDF_PRINCIPLED") and not any(o.links for o in n.outputs):
                nt.nodes.remove(n)
    for n in list(nt.nodes):
        if n.type == "TEX_IMAGE":
            to = [l.to_socket.name for o in n.outputs for l in o.links]
            if not to or any(t in ("Roughness", "Metallic", "Normal", "Specular IOR Level", "Height") for t in to):
                nt.nodes.remove(n)
    for n in nt.nodes:
        if n.type == "BSDF_PRINCIPLED":
            n.inputs["Metallic"].default_value = 0.0


WARM = (1.0, 0.95, 0.86)


def make_materials():
    F = FLOOR
    g = {k: mk_image(k, f()) for k, f in (("gen_tape", gen_tape), ("gen_lava", gen_lava), ("gen_card", gen_card), ("gen_brushed", gen_brushed),
                                          ("gen_shutter", gen_shutter), ("gen_canvas", gen_canvas))}
    # the shell: the greybox's role names, filled with the store's own materials
    store_material(f"M_D_floor_{F}")
    store_material(f"M_D_ceil_{F}")
    store_material("M_U_wall_L4" if F == "L4" else f"M_D_wall_{F}", f"M_D_wall_{F}")
    store_material("M_U_wall_L4" if F == "L4" else f"M_D_wall_{F}", "M_GBI_kit")
    if F == "B1":
        store_material("M_Water")                                               # the store's pool water (alpha blend, unbaked)        # the casings round the kit pieces: the floor's wall
    # the store's own small materials
    for n in ("M_X_white", "M_X_dark", "M_X_steel", "M_X_exit", "M_Fixture_Housing", "M_U_bluepaint", "M_U_blue", "M_U_yellow", "M_U_arrow",
              "M_X_orange", "M_U_rug_blue", "M_U_rug_grey", "M_U_rug_red"):
        store_material(n)
    MATS["M_X_exit"].node_tree.nodes  # (its emission stays: always on, as in the store)
    # the toggled panels and lamps
    material("Lamp_Emit", color=(1.0, 0.97, 0.86), rough=0.3, emit=(WARM, PANEL_EMIT))
    material("M_GBI_nightlight", color=(1.0, 0.97, 0.86), rough=0.3, emit=(WARM, NIGHT_EMIT))
    material("Emergency_Emit", color=(1.0, 0.95, 0.88), rough=0.3, emit=((1.0, 0.93, 0.82), EMERG_EMIT))
    # roles the greybox named, now dressed
    material(f"M_GBI_furn_{F}", color=srgb_lin({"L4": "#f26b0f", "L3": "#ebeae4", "L2": "#8a6a48", "L1": "#6e6a62", "B1": "#d8e4ea"}[F]),
             rough=0.6)                                                         # L4 the store's orange, L3 white plinths, L2 desk wood, L1 grey, B1 tile
    material("M_D_trim", color=srgb_lin("#c9cac6"), rough=0.6)
    material("M_D_door", color=srgb_lin("#a88b66"), rough=0.6)
    material("M_GBI_vent", img=g["gen_brushed"], tint=srgb_lin("#c4c8cc"), rough=0.4, tile=0.5)
    material("M_GBI_tape", img=g["gen_tape"], rough=0.6, tile=0.4)
    material("M_GBI_card", img=g["gen_card"], rough=0.9, tile=0.6)
    material("M_GBI_wood", color=srgb_lin("#a07a4c"), rough=0.8)
    material("M_GBI_textile", color=srgb_lin("#d9d4c8"), rough=0.95)
    material("M_GBI_textile_dark", color=srgb_lin("#46505a"), rough=0.95)
    material("M_GBI_shutter", img=g["gen_shutter"], rough=0.5, tile=1.0)
    material("M_GBI_canvas", img=g["gen_canvas"], rough=0.9, tile=1.0)
    material("M_GBI_frame", color=srgb_lin("#2a2a28"), rough=0.5)
    for i, hx in enumerate(("#8d9a82", "#b9a48a", "#a8634e", "#4e5f78", "#c9a24a"), 1):     # the room sets' painted back walls
        material(f"M_GBI_accent_{i}", color=srgb_lin(hx), rough=0.8)
    # the hazards: unbaked (the page moves them); lava glows
    material("M_GBI_hazard_lava", img=g["gen_lava"], emit=((1.0, 0.35, 0.05), 2.0), rough=0.6, tile=1.0)
    material("M_GBI_hazard_blade", img=g["gen_brushed"], tint=srgb_lin("#b8bcc0"), rough=0.3, tile=0.3)
    material("M_GBI_hazard_crush", color=srgb_lin({"L4": "#e07020", "L3": "#d8d6cf", "L2": "#b8ac8c", "L1": "#c9b98a", "B1": "#dfe8ec"}[F]), rough=0.7)
    material("M_GBI_hazard_tide", color=srgb_lin("#3d8fa8"), rough=0.1, alpha=0.6)
    material("M_GBI_hazard_gas", color=srgb_lin("#8fc23a"), rough=0.9, alpha=0.35)
    material("M_GBI_fabric", color=srgb_lin("#5f6b78"), rough=0.95)            # cubicle panels
    material("Standin_Grey", color=(0.4, 0.4, 0.4), rough=0.9)


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


ART = PROPS = ARCH = SKIN = DOORS = LAYOUT = HAZ = LIGHTS = KIT = None
COLLS = ("Art", "Props", "Arch", "Skin", "Doors", "Layout", "Hazards", "Lights", "Kit")


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


def boxes(bm, items):
    for mn, mx in items:
        cube(bm, mn, mx)


def joined(name, parts, coll=None):
    """One object of several materials: parts = [(material, [(min, max), ...])]. Its box is the union, as check_layout reads it."""
    objs = [part(f"{name}__{i}", mat, lambda bm, it=items: boxes(bm, it), coll) for i, (mat, items) in enumerate(parts) if items]
    return join(name, objs)


def join(name, objs):
    """Merges objects into one (world space, materials remapped), in the first one's collection."""
    objs = [o for o in objs if o is not None]
    coll = objs[0].users_collection[0]
    mats, bm = [], bmesh.new()
    for o in objs:
        tmp = bmesh.new()
        tmp.from_mesh(o.data)
        tmp.transform(o.matrix_world)
        remap = []
        for m in o.data.materials:
            if m not in mats:
                mats.append(m)
            remap.append(mats.index(m))
        for f in tmp.faces:
            f.material_index = remap[f.material_index] if remap else 0
        me = bpy.data.meshes.new("tmp")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        old = o.data
        bpy.data.objects.remove(o)
        if old.users == 0:
            bpy.data.meshes.remove(old)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def quad(bm, pts, normal):
    f = bm.faces.new([bm.verts.new(B(p)) for p in pts])
    f.normal_update()
    if f.normal.dot(B(normal)) < 0:
        f.normal_flip()
    return f


def decal(name, mat, x0, x1, z0, z1, y, rot=0, uvfit=False):
    """A flat floor decal (a quad 4 mm up); uvfit maps the image once over it, turned `rot` quarter turns."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    pts = [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)]
    f = quad(bm, pts, (0, 1, 0))
    for lp in f.loops:
        gx, gz = lp.vert.co.x, -lp.vert.co.y
        if uvfit:
            a, c = (gx - x0) / (x1 - x0), (gz - z0) / (z1 - z0)
            # the store's arrow points along the image's +u: turn it to the heading (0 north (-z), 1 east (+x), 2 south (+z), 3 west (-x))
            u, v = {0: (1 - c, 1 - a), 1: (a, 1 - c), 2: (c, a), 3: (1 - a, c)}[rot % 4]
            lp[uvl].uv = (u, v)
        else:
            t = TILES.get(mat, 1.0)
            lp[uvl].uv = (gx / t, gz / t)
    return finish(name, bm, mat, PROPS, keep_uv=True)


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
    R, U, N = Vector(B(right)), Vector(B(up)), Vector(B(normal))
    O = B(origin)
    Mx = Matrix(((R.x, U.x, N.x, O.x), (R.y, U.y, N.y, O.y), (R.z, U.z, N.z, O.z), (0, 0, 0, 1)))
    tmp = bmesh.new()
    tmp.from_mesh(me)
    bmesh.ops.translate(tmp, verts=tmp.verts, vec=Vector((0, 0, depth / 2)))
    bmesh.ops.transform(tmp, matrix=Mx, verts=tmp.verts)
    m2 = bpy.data.meshes.new("t2")
    tmp.to_mesh(m2)
    tmp.free()
    bm.from_mesh(m2)
    bpy.data.meshes.remove(m2)
    bpy.data.meshes.remove(me)


MODELS = {}


def model_mesh(src):
    if src not in MODELS:
        MODELS[src] = store_model(src)
    return MODELS[src]


def place_model(name, src, gmin, gmax, yaw=0.0, mode="stretch", coll=None):
    """A store model fitted into the game box [gmin, gmax], turned `yaw` (three.js rotation.y; the model's front, Blender -Y, faces game
    (sin yaw, cos yaw)). mode 'stretch' fills the box; 'uniform' keeps proportions, stands on the box's floor, centred."""
    me = model_mesh(src).copy()
    me.name = name
    me.transform(Matrix.Rotation(math.radians(yaw), 4, "Z"))
    vs = [v.co for v in me.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    a, b = B(gmin), B(gmax)
    tlo = Vector((min(a.x, b.x), min(a.y, b.y), min(a.z, b.z)))
    thi = Vector((max(a.x, b.x), max(a.y, b.y), max(a.z, b.z)))
    s = Vector([(thi[i] - tlo[i]) / max(hi[i] - lo[i], 1e-6) for i in range(3)])
    if mode == "uniform":
        k = min(s)
        s = Vector((k, k, k))
        size = (hi - lo) * k
        off = Vector(((tlo.x + thi.x) / 2 - size.x / 2, (tlo.y + thi.y) / 2 - size.y / 2, tlo.z))
    else:
        off = tlo
    me.transform(Matrix.Translation(off) @ Matrix.Diagonal((*s, 1.0)) @ Matrix.Translation(-lo))
    ob = bpy.data.objects.new(name, me)
    (coll or PROPS).objects.link(ob)
    return ob


# ---------------------------------------------------------------- layout objects (exported to the JSON, never to the GLB)
def col_box(name, mn, mx, coll):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    cube(bm, mn, mx)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob.hide_render = True
    ob.display_type = "WIRE"
    return ob


def layout_from_model():
    """Every COL_, Zone_, Marker_, Link_/Arrive_ and Spot_ of the greybox model, with its names, numbers and properties; the shell's and the
    kit's colliders get a grey twin in Art/Arch (never rendered or exported) for the layout check, as on the hotel floors."""
    for b in M.boxes:
        if b.get("zone"):
            col_box(b["name"], b["min"], b["max"], LAYOUT)
            continue
        if b["col"]:
            col_box("COL_" + b["name"], b["min"], b["max"], LAYOUT)
            if not SK.is_furniture(b):
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


def gbox(ob):
    g = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return [min(p.x for p in g), min(p.z for p in g), min(-p.y for p in g)], [max(p.x for p in g), max(p.z for p in g), max(-p.y for p in g)]


# ---------------------------------------------------------------- the connector kit's pieces: bake and still stand-ins (never exported)
KIT_PREFIX = ("COL_", "DoorLeaf_", "Link_", "Arrive_", "Spot_", "Zone_", "Marker_")


def place_kit():
    for k in M.kits:
        path = ROOT / f"blender/kit/{k['piece']}.blend"
        with bpy.data.libraries.load(str(path), link=False) as (src, dst):
            dst.collections = [c for c in src.collections if c == "Art"]
        Mk = Matrix.Translation(B(k["at"])) @ Matrix.Rotation(math.radians(k["yaw"]), 4, "Z")
        n = 0
        for coll in dst.collections:
            obs = list(coll.all_objects)
            for ob in obs:
                if ob.name.split(".")[0].startswith(KIT_PREFIX):
                    bpy.data.objects.remove(ob)
            obs = [o for o in coll.all_objects]
            roots = [o for o in obs if o.parent is None or o.parent not in obs]
            for ob in roots:
                ob.matrix_basis = Mk @ ob.matrix_basis
            for ob in obs:
                ob.name = f"kit_{k['sfx']}_{ob.name}"
                KIT.objects.link(ob)
                n += 1
            bpy.data.collections.remove(coll)
        print(f"KIT {k['piece']} at {k['at']} yaw {k['yaw']}: {n} stand-in objects")


# ---------------------------------------------------------------- the skin (the shell as seen)
def build_skin():
    q = SK.skin(M)
    by = {}
    for x in q:
        by.setdefault(SK.material(x, FLOOR), []).append(x)
    for mname, quads in sorted(by.items()):
        skin_mesh(mname, quads)


def skin_mesh(mname, quads):
    name = f"Skin_{mname}"
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    pieces = []
    for x in quads:                                      # long quads cut into pieces of 4 m at most: one 50 m island would shrink the atlas
        nb = max(1, math.ceil((x["b"][1] - x["b"][0]) / 4.0))
        nc = max(1, math.ceil((x["c"][1] - x["c"][0]) / 4.0))
        for i in range(nb):
            for j in range(nc):
                y = dict(x)
                y["b"] = (x["b"][0] + (x["b"][1] - x["b"][0]) * i / nb, x["b"][0] + (x["b"][1] - x["b"][0]) * (i + 1) / nb)
                y["c"] = (x["c"][0] + (x["c"][1] - x["c"][0]) * j / nc, x["c"][0] + (x["c"][1] - x["c"][0]) * (j + 1) / nc)
                pieces.append(y)
    for x in pieces:
        pts = SK.quad_points(x)
        want = [0, 0, 0]
        want[x["axis"]] = x["side"]
        f = quad(bm, pts, want)
        for lp in f.loops:
            gx, gy, gz = lp.vert.co.x, lp.vert.co.z, -lp.vert.co.y
            u, v = (gz, gy) if x["axis"] == 0 else (gx, gz) if x["axis"] == 1 else (gx, gy)
            lp[uvl].uv = (u, v)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mname])
    ob = bpy.data.objects.new(name, me)
    SKIN.objects.link(ob)
    return ob


# ---------------------------------------------------------------- door leaves (a node per door, origin at the hinge) and the hazards
def leaf_mesh(name, width, height, kind):
    """Local +X runs from the hinge along the leaf; z is up; the leaf is 45 mm thick, centred on the hinge line."""
    bm = bmesh.new()
    t = 0.0225
    if kind == "vent":
        cube(bm, (0.0, 0.0, -0.015), (width, height, 0.015))
        for i in range(1, 8):                             # louvres
            z = height * i / 8
            cube(bm, (0.04, z - 0.012, -0.03), (width - 0.04, z + 0.012, 0.03))
        mat = "M_GBI_vent"
    else:
        cube(bm, (0.0, 0.0, -t), (width, height, t))
        cube(bm, (0.06, 0.02, -t - 0.004), (width - 0.06, 0.12, t + 0.004))        # kick plates
        mat = "M_D_door"
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for lp in f.loops:
            p = lp.vert.co
            lp[uvl].uv = (p.x + p.y, p.z)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mat])
    if kind != "vent":                                    # the handle (steel), both sides
        bm = bmesh.new()
        hx = width - 0.09
        for s in (-1, 1):
            cube(bm, (hx - 0.012, 1.0 - 0.012, s * t), (hx + 0.012, 1.0 + 0.012, s * (t + 0.06)))
            cube(bm, (hx - 0.13, 1.0 - 0.012, s * (t + 0.048)), (hx + 0.012, 1.0 + 0.012, s * (t + 0.072)))
        uvl = bm.loops.layers.uv.new("UVMap")
        for f in bm.faces:
            for lp in f.loops:
                lp[uvl].uv = (lp.vert.co.x, lp.vert.co.z)
        me2 = bpy.data.meshes.new(name + "_h")
        bm.to_mesh(me2)
        bm.free()
        me2.materials.append(MATS["M_X_steel"])
        b2 = bmesh.new()
        b2.from_mesh(me)
        off = len(me.materials)
        me.materials.append(MATS["M_X_steel"])
        tmp = bmesh.new()
        tmp.from_mesh(me2)
        for f in tmp.faces:
            f.material_index = off
        tmp.to_mesh(me2)
        tmp.free()
        b2.from_mesh(me2)
        b2.to_mesh(me)
        b2.free()
        bpy.data.meshes.remove(me2)
    return me


def build_doors():
    """The chamber's own doors (interior chamber doors, the plain doors in the outer wall, the vent grilles) as leaves with their own mesh each
    (each is baked where it stands). The kit's doors are drawn by the kit's GLB: their DoorLeaf_ records are empties here."""
    for d in M.doors:
        p = d["props"]
        if d.get("kit"):
            ob = bpy.data.objects.new(d["name"], None)
            ob.empty_display_size = 0.3
            ob.empty_display_type = "ARROWS"
            LAYOUT.objects.link(ob)
        else:
            kind = "vent" if p.get("kind") == "vent" else "door"
            me = leaf_mesh(d["name"], p["width"], p["height"], kind)
            # leaf_mesh used cube(), which maps game (x, y, z) to Blender (x, -z, y): local game x along the leaf, y up -> Blender x, z
            ob = bpy.data.objects.new(d["name"], me)
            DOORS.objects.link(ob)
        ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
        for k, v in p.items():
            ob[k] = v


def hazard_mesh(h):
    """Each hazard's moving part, built to its greybox box (relative to its origin): lava a glowing strip, a blade a toothed disc on a carriage,
    a crushing wall a slab (a rack end with a striped edge on L4, a plaster slab on L3)."""
    mn, mx = h["box"]
    kind = h["kind"]
    bm = bmesh.new()
    if kind == "lava":
        cube(bm, mn, mx)
    elif kind == "blade":
        along_x = (mx[0] - mn[0]) > (mx[2] - mn[2])
        r = 0.55
        c = (0.0, 0.62, 0.0)
        th = 0.012
        segs = 48
        verts_f, verts_b = [], []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            rr = r + (0.05 if i % 2 == 0 else 0.0)
            u, v = rr * math.cos(a), rr * math.sin(a)
            for sgn, lst in ((1, verts_f), (-1, verts_b)):
                p = (c[0] + u, c[1] + v, sgn * th) if along_x else (sgn * th, c[1] + v, c[2] + u)
                lst.append(bm.verts.new(B(p)))
        bm.faces.new(verts_f)
        bm.faces.new(list(reversed(verts_b)))
        for i in range(segs):
            j = (i + 1) % segs
            bm.faces.new([verts_f[i], verts_f[j], verts_b[j], verts_b[i]])
        hub = (0.04, 0.12, 0.12)
        cube(bm, (-hub[0], c[1] - hub[1], -hub[2]), (hub[0], c[1] + hub[1], hub[2]))
        cube(bm, (-0.05, 0.0, -0.05), (0.05, c[1], 0.05))                          # the arm up from the slot
    else:
        cube(bm, mn, mx)
    org = h["origin"]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            u, v = (p.y, p.z) if ax == 0 else (p.x, p.y) if ax == 2 else (p.x, p.z)
            lp[uvl].uv = (u, v)
    me = bpy.data.meshes.new(h["name"])
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[f"M_GBI_hazard_{kind}"])
    ob = bpy.data.objects.new(h["name"], me)
    ob.location = B(org)
    for k, v in h["props"].items():
        ob[k] = v
    ob["travel_a"] = [round(v, 3) for v in h["a"]]
    ob["travel_b"] = [round(v, 3) for v in h["b"]]
    ob["zone"] = h["zone"]
    HAZ.objects.link(ob)
    return ob


def build_hazards():
    for h in M.hazards:
        hazard_mesh(h)


# ---------------------------------------------------------------- lights
def light(name, kind, pos, power, color=WARM, size=0.05, size_y=None, aim=None, spot=None):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = power
    ld.color = color
    if kind == "AREA":
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = size, size_y or size
    else:
        ld.shadow_soft_size = size
    if spot:
        ld.spot_size = math.radians(spot)
        ld.spot_blend = 0.6
    ob = bpy.data.objects.new(name, ld)
    ob.location = B(pos)
    if aim is not None:
        ob.rotation_euler = (B(aim) - B(pos)).to_track_quat("-Z", "Y").to_euler()
    LIGHTS.objects.link(ob)
    return ob


def blocked_above(x, z, hw, hd):
    """True where a ceiling panel at (x, z) would sit over a wall that reaches the ceiling, a kit piece, or a casing."""
    Y, H = M.Y, M.H
    for b in SK.colliders(M):
        if b["name"] in ("Floor", "Ceiling") or (b["max"][1] < Y + H - 0.3 and not SK.is_kit(b)):
            continue
        g = 0.3 if FLOOR in ("L4", "L3") else 0.15
        if b["min"][0] - g < x + hw and b["max"][0] + g > x - hw and b["min"][2] - g < z + hd and b["max"][2] + g > z - hd:
            return True
    for h in SK.hulls(M):
        if h["min"][0] - 0.3 < x + hw and h["max"][0] + 0.3 > x - hw and h["min"][2] - 0.3 < z + hd and h["max"][2] + 0.3 > z - hd:
            return True
    return False


def ceiling_panels():
    """The store's flush fluorescent panels, 1.2 m by 0.6 m, on a grid (L4 every 4 m, L3 every 4.5 m), each with an area light under it.
    One in nine is on the night circuit (M_GBI_nightlight): it stays on when the store shuts."""
    Y, H, g = M.Y, M.H, GRID[FLOOR]
    top = Y + H
    xs = [x for x in np.arange(-24.0, 24.01, g)]
    zs = [z for z in np.arange(-20.0, 25.01, g)]
    hous, day, night = [], [], []
    n = 0
    for i, x in enumerate(xs):
        for j, z in enumerate(zs):
            if blocked_above(x, z, 0.62, 0.32):
                continue
            hous.append(((x - 0.64, top - 0.05, z - 0.34), (x + 0.64, top, z + 0.34)))
            k = NIGHT_EVERY[FLOOR]
            nightc = (i % k == 1 and j % k == 1)
            (night if nightc else day).append((x, z))
            n += 1
            light(f"{'LB' if nightc else 'LD'}_panel_{i}_{j}", "AREA", (x, top - 0.07, z), PANEL_W[FLOOR], size=1.2, size_y=0.6,
                  aim=(x, top - 2.0, z))

    def faces(lst):
        def f(bm):
            for x, z in lst:
                quad(bm, [(x - 0.6, top - 0.052, z - 0.3), (x + 0.6, top - 0.052, z - 0.3), (x + 0.6, top - 0.052, z + 0.3), (x - 0.6, top - 0.052, z + 0.3)], (0, -1, 0))
        return f
    part("Panel_Housings", "M_Fixture_Housing", lambda bm: boxes(bm, hous))
    if day:
        part("Panel_Day", "Lamp_Emit", faces(day), recalc=False)
    if night:
        part("Panel_Night", "M_GBI_nightlight", faces(night), recalc=False)
    print(f"PANELS {n} ({len(night)} on the night circuit)")


def wall_frame(side):
    """An outer wall's frame: the point at run `a`, height y, `d` in front of the face; its inward normal and the viewer's right."""
    if side == "N":
        return (lambda a, y, d: (a, y, GB.Z0 + d)), (0, 0, 1), (1, 0, 0)
    if side == "S":
        return (lambda a, y, d: (a, y, GB.Z1 - d)), (0, 0, -1), (-1, 0, 0)
    if side == "W":
        return (lambda a, y, d: (GB.X0 + d, y, a)), (1, 0, 0), (0, 0, -1)
    return (lambda a, y, d: (GB.X1 - d, y, a)), (-1, 0, 0), (0, 0, 1)


def free_at(p, r=0.25):
    """The point is in the room's air: not in a collider, a kit hull or a casing (an outer-wall fitting must not stand in front of anything)."""
    for b in SK.colliders(M):
        if b["name"] in ("Floor", "Ceiling") or b["name"].startswith("Wall_"):
            continue
        if all(b["min"][i] - r < p[i] < b["max"][i] + r for i in (0, 2)) and b["min"][1] - 0.2 < p[1] < b["max"][1] + 0.2:
            return False
    for h in SK.hulls(M) + SK.casings(M):
        if all(h["min"][i] - r < p[i] < h["max"][i] + r for i in (0, 2)) and h["min"][1] - 0.2 < p[1] < h["max"][1] + 0.5:
            return False
    return True


def door_spots():
    """Where each way through stands, with the wall it is in: [(centre (x, y, z), inward normal, right, kind)], for the EXIT signs."""
    out = []
    for d in M.doors:
        p = d["props"]
        th = math.radians(p["closed_yaw_deg"])
        rx, rz = math.cos(th), -math.sin(th)
        if d.get("kit"):
            k = next(k for k in M.kits if k["sfx"] == d["kit"])
            a = math.radians(k["yaw"])
            nrm = (math.sin(a), 0, math.cos(a))
            ax, ay, az = k["at"]
            if d["name"].startswith("DoorLeaf_lift"):
                out.append(((ax + nrm[0] * 0.06, ay + 2.62, az + nrm[2] * 0.06), nrm, "lift"))
            elif d["name"].startswith("DoorLeaf_entry"):
                out.append(((ax + nrm[0] * 0.0, ay + 2.45, az + nrm[2] * 0.0), nrm, "hall"))
            elif d["name"].startswith("DoorLeaf_stair"):
                out.append(((ax + nrm[0] * 1.45, ay + 2.5, az + nrm[2] * 1.45), nrm, "stair"))
        elif p.get("kind") in ("door", "hall door"):
            cx, cz = d["hinge"][0] + rx * p["width"] / 2, d["hinge"][2] + rz * p["width"] / 2
            nrm = (0, 0, 1) if abs(cz - GB.Z0) < 1e-6 else (0, 0, -1) if abs(cz - GB.Z1) < 1e-6 else (1, 0, 0) if abs(cx - GB.X0) < 1e-6 else (-1, 0, 0)
            out.append(((cx, M.Y + 2.45, cz), nrm, "door"))
    return out


def oriented_box(c, right, nrm, w, h, d0, d1):
    """An axis-aligned box centred on c along `right` (w wide) and up (h high), from d0 to d1 along `nrm`."""
    pts = []
    for su in (-0.5, 0.5):
        for sv in (-0.5, 0.5):
            for dd in (d0, d1):
                pts.append((c[0] + right[0] * su * w + nrm[0] * dd, c[1] + sv * h, c[2] + right[2] * su * w + nrm[2] * dd))
    return tuple(min(p[i] for p in pts) for i in range(3)), tuple(max(p[i] for p in pts) for i in range(3))


def exit_signs():
    """A lit EXIT sign over every way through (the store's M_X_exit and its sign_exit picture, always on), and an emergency twin-spot beside each
    sign on a wall (Emergency_Emit). Under the stair door's landing ceiling the sign hangs, lit both sides."""
    cases, faces = [], []
    for i, (c, nrm, kind) in enumerate(door_spots()):
        right = (nrm[2], 0, -nrm[0])
        hang = kind == "stair"
        w, h = 0.36, 0.18
        if hang:
            cases.append(oriented_box(c, right, nrm, w, h, -0.025, 0.025))
            cases.append(oriented_box((c[0], c[1] + h / 2 + 0.05, c[2]), right, nrm, 0.02, 0.1, -0.01, 0.01))
            faces.append((c, right, nrm, w, h, 0.027))
            faces.append((c, (-right[0], 0, -right[2]), (-nrm[0], 0, -nrm[2]), w, h, 0.027))
        else:
            cases.append(oriented_box(c, right, nrm, w, h, 0.0, 0.05))
            faces.append((c, right, nrm, w, h, 0.052))
            emergency_unit((c[0] + right[0] * 0.75, c[1] + 0.05, c[2] + right[2] * 0.75), nrm, right)
        light(f"LB_exit_{i}", "POINT", (c[0] + nrm[0] * 0.3, c[1] - 0.05, c[2] + nrm[2] * 0.3), EXIT_W, color=(0.3, 1.0, 0.45), size=0.1)
    if not cases:
        return
    part("Exit_Cases", "M_X_white", lambda bm: boxes(bm, cases))
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    for c, right, nrm, w, h, d in faces:
        corners = [(0, 0), (1, 0), (1, 1), (0, 1)]
        pts = [(c[0] + right[0] * (u - 0.5) * w + nrm[0] * d, c[1] + (v - 0.5) * h, c[2] + right[2] * (u - 0.5) * w + nrm[2] * d) for u, v in corners]
        f = bm.faces.new([bm.verts.new(B(p)) for p in pts])
        f.normal_update()
        if f.normal.dot(B(nrm)) < 0:
            f.normal_flip()
        for lp in f.loops:
            p = lp.vert.co
            g = (p.x, p.z, -p.y)
            u = ((g[0] - c[0]) * right[0] + (g[2] - c[2]) * right[2]) / w + 0.5
            v = (g[1] - c[1]) / h + 0.5
            lp[uvl].uv = (u, v)
    finish("Exit_Signs", bm, "M_X_exit", PROPS, keep_uv=True)


EMERG = {"cases": [], "heads": []}


def emergency_unit(p, nrm, right):
    """A wall-mounted twin-spot emergency light: a white box and two lamp heads (Emergency_Emit), each a spot aimed down and out (night only)."""
    x, y, z = p
    w, h, d = 0.34, 0.12, 0.08
    lo = (x - abs(right[0]) * w / 2, y - h / 2, z - abs(right[2]) * w / 2)
    hi = (x + abs(right[0]) * w / 2, y + h / 2, z + abs(right[2]) * w / 2)
    lo = (lo[0] + min(0, nrm[0]) * d, lo[1], lo[2] + min(0, nrm[2]) * d)
    hi = (hi[0] + max(0, nrm[0]) * d, hi[1], hi[2] + max(0, nrm[2]) * d)
    EMERG["cases"].append((lo, hi))
    for s in (-1, 1):
        hx, hz = x + right[0] * s * 0.11 + nrm[0] * (d + 0.03), z + right[2] * s * 0.11 + nrm[2] * (d + 0.03)
        EMERG["heads"].append(((hx, y - 0.1, hz), 0.035))
        n = len(EMERG["heads"])
        light(f"LN_emerg_{n}", "SPOT", (hx, y - 0.12, hz), EMERG_W, color=(1.0, 0.94, 0.84), size=0.03, spot=95,
              aim=(hx + nrm[0] * 2.5 + right[0] * s * 1.5, y - 2.2, hz + nrm[2] * 2.5 + right[2] * s * 1.5))


def emergency_walls():
    """Emergency twin-spots along the outer walls, every 13 m or so, where the wall is free."""
    Y = M.Y
    y = Y + min(M.H - 0.45, 2.75)
    for side, span in (("N", (GB.X0, GB.X1)), ("S", (GB.X0, GB.X1)), ("W", (GB.Z0, GB.Z1)), ("E", (GB.Z0, GB.Z1))):
        P, nrm, right = wall_frame(side)
        n = int((span[1] - span[0]) // 13.0)
        for k in range(n):
            a0 = span[0] + (span[1] - span[0]) * (k + 0.5) / n
            for da in (0.0, 1.5, -1.5, 3.0, -3.0):
                a = a0 + da
                if free_at(P(a, y, 0.3), 0.5) and free_at(P(a, Y + 1.0, 0.3), 0.3):
                    emergency_unit(P(a, y, 0.0), nrm, right)
                    break


def finish_emergency():
    if EMERG["cases"]:
        part("Emergency_Cases", "M_X_white", lambda bm: boxes(bm, EMERG["cases"]))

        def heads(bm):
            for (c, r) in EMERG["heads"]:
                bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=r, matrix=Matrix.Translation(B(c)))
        part("Emergency_Heads", "Emergency_Emit", heads)


# ---------------------------------------------------------------- shared dressing
def furniture(prefix):
    return [b for b in SK.colliders(M) if b["name"].startswith(prefix)]


def vents():
    """The vent ducts (built shut): a galvanised casing over the greybox box, a flange at each end."""
    for b in furniture("Vent_"):
        mn, mx = b["min"], b["max"]
        it = [(mn, mx)]
        part(b["name"], "M_GBI_vent", lambda bm, it=it: boxes(bm, it), tile=0.5)


def greybox_decor():
    """The greybox's own decor boxes (walk-through art): the blades' floor slots and the stockroom's dock door."""
    for b in M.boxes:
        if b["col"] or b.get("zone") or not b.get("art"):
            continue
        n = b["name"]
        mn, mx = list(b["min"]), list(b["max"])
        if "Blade_Slot" in n:
            joined(n, [("M_X_dark", [(mn, mx)]), ("M_GBI_tape", [((mn[0] - 0.12, mn[1], mn[2] - 0.12), (mn[0] - 0.02, mx[1] - 0.001, mx[2] + 0.12)),
                                                                   ((mx[0] + 0.02, mn[1], mn[2] - 0.12), (mx[0] + 0.12, mx[1] - 0.001, mx[2] + 0.12))]
                                                     if (mx[2] - mn[2]) > (mx[0] - mn[0]) else
                                                     [((mn[0] - 0.12, mn[1], mn[2] - 0.12), (mx[0] + 0.12, mx[1] - 0.001, mn[2] - 0.02)),
                                                      ((mn[0] - 0.12, mn[1], mx[2] + 0.02), (mx[0] + 0.12, mx[1] - 0.001, mx[2] + 0.12))])])
        elif "Water" in n:                                                  # a pool's surface: the store's water, unbaked
            joined(n, [("M_Water", [(mn, mx)])])
        elif "Dock_Door" in n:
            joined(n, [("M_GBI_shutter", [(mn, (mx[0], mx[1] - 0.3, mx[2]))]), ("M_X_dark", [((mn[0], mx[1] - 0.3, mn[2]), (mx[0], mx[1], mx[2] + 0.12))]),
                       ("M_U_yellow", [((mn[0] - 0.15, mn[1], mn[2]), (mn[0], mx[1], mx[2] + 0.06)), ((mx[0], mn[1], mn[2]), (mx[0] + 0.15, mx[1], mx[2] + 0.06))])])
        else:
            joined(n, [("M_D_trim", [(mn, mx)])])


def arrows(path):
    """The store's painted floor arrows (M_U_arrow), along the way through: [(x, z, heading)], heading 0 = north (-z), 1 = east, 2 = south, 3 = west."""
    Y = M.Y + 0.004
    objs = []
    for i, (x, z, hd) in enumerate(path):
        objs.append(decal(f"Arrow_{i}", "M_U_arrow", x - 0.6, x + 0.6, z - 0.6, z + 0.6, Y, rot=hd, uvfit=True))
    if objs:
        join("Floor_Arrows", objs)


# ---------------------------------------------------------------- L4: the showroom floor's furniture
def gondola(b):
    """A double-sided store gondola over the greybox box (long along x): a plinth, a pegboard spine, four shelves a side, orange end panels and
    a header; nearly empty (a few cartons)."""
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    zc = (z0 + z1) / 2
    h = y1 - y0
    steel, orange, card = [], [], []
    steel.append(((x0 + 0.05, y0, z0 + 0.02), (x1 - 0.05, y0 + 0.12, z1 - 0.02)))                 # plinth
    steel.append(((x0 + 0.05, y0 + 0.12, zc - 0.03), (x1 - 0.05, y0 + h - 0.08, zc + 0.03)))       # spine
    for yy in (0.55, 1.0, 1.45):
        for s in (-1, 1):
            za, zb = sorted((zc + s * 0.03, zc + s * 0.48))
            steel.append(((x0 + 0.06, y0 + yy, za), (x1 - 0.06, y0 + yy + 0.025, zb)))
    nx = max(1, int(round((x1 - x0) / 1.25)))
    for k in range(nx + 1):
        x = x0 + 0.05 + (x1 - x0 - 0.1) * k / nx
        orange.append(((x - 0.025, y0 + 0.12, zc - 0.05), (x + 0.025, y0 + h - 0.08, zc + 0.05)))   # uprights
    for xe in (x0, x1 - 0.05):
        orange.append(((xe, y0, z0), (xe + 0.05, y1, z1)))                                          # end panels
    orange.append(((x0 + 0.05, y1 - 0.08, zc - 0.12), (x1 - 0.05, y1, zc + 0.12)))                  # header
    rng = np.random.default_rng(int(abs(x0 * 13 + z0 * 7)) + 11)
    for yy in (0.12, 0.575, 1.025):
        for s in (-1, 1):
            for _ in range(int(rng.integers(0, 3))):
                cx = x0 + 0.4 + rng.random() * (x1 - x0 - 0.8)
                w, d, hh = 0.3 + rng.random() * 0.2, 0.3, 0.22 + rng.random() * 0.16
                za, zb = sorted((zc + s * 0.06, zc + s * (0.06 + d)))
                card.append(((cx - w / 2, y0 + yy + 0.025, za), (cx + w / 2, y0 + yy + 0.025 + hh, zb)))
    joined(b["name"], [("M_X_white", steel), ("M_GBI_furn_L4", orange), ("M_GBI_card", card)])


def island(b):
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    joined(b["name"], [("M_D_trim", [((x0, y1 - 0.03, z0), (x1, y1, z1))]),
                       ("M_X_dark", [((x0 + 0.04, y0, z0 + 0.04), (x1 - 0.04, y1 - 0.03, z1 - 0.04))]),
                       ("M_U_yellow", [((x0, y1 - 0.03, z0 - 0.0), (x1, y1 - 0.005, z0 + 0.05)), ((x0, y1 - 0.03, z1 - 0.05), (x1, y1 - 0.005, z1))])])


def checkout(b):
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    joined(b["name"], [("M_U_bluepaint", [((x0, y0, z0), (x1, y1 - 0.04, z1))]),
                       ("M_X_white", [((x0 - 0.0, y1 - 0.04, z0), (x1, y1, z1))]),
                       ("M_X_dark", [((x0 + 0.4, y1, z0 + 0.3), (x0 + 0.9, y1 + 0.12, z0 + 0.7)), ((x0 + 1.2, y1, z0 + 0.4), (x1 - 0.8, y1 + 0.01, z1 - 0.4)),
                                     ((x1 - 0.7, y1, z0 + 0.5), (x1 - 0.4, y1 + 0.35, z0 + 0.52))])])


def display_table(b, cartons=3):
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    legs = [((x - 0.03, y0, z - 0.03), (x + 0.03, y1 - 0.04, z + 0.03)) for x in (x0 + 0.08, x1 - 0.08) for z in (z0 + 0.08, z1 - 0.08)]
    rng = np.random.default_rng(int(abs(x0 * 31 + z0)) + 5)
    card = []
    for _ in range(cartons):
        cx, cz = x0 + 0.5 + rng.random() * (x1 - x0 - 1.0), z0 + 0.4 + rng.random() * (z1 - z0 - 0.8)
        card.append(((cx - 0.22, y1, cz - 0.18), (cx + 0.22, y1 + 0.3, cz + 0.18)))
    joined(b["name"], [("M_X_white", [((x0, y1 - 0.04, z0), (x1, y1, z1))]), ("M_X_steel", legs), ("M_GBI_card", card)])


def sofa_set(b, rug):
    """A mock room's sofa (the store's Poly Haven sofa_02, against the outer wall, facing the aisle) and a round coffee table, filling the
    greybox box; a rug under them."""
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    s = place_model(b["name"] + "_sofa", "Set_sofa_02", (x0, y0, z0), (x0 + 0.9, y1, z1), yaw=90.0, mode="stretch")
    t = place_model(b["name"] + "_table", "Set_coffee_table_round_01", (x1 - 0.95, y0, (z0 + z1) / 2 - 0.5), (x1, y0 + 0.45, (z0 + z1) / 2 + 0.5), mode="stretch")
    join(b["name"], [s, t])
    decal(b["name"] + "_rug", rug, x0 - 0.3, x1 + 0.6, z0 - 0.3, z1 + 0.3, y0 + 0.006)


def bed_set(b, cover):
    """A mock room's bed, its headboard to the outer wall (east): a base, a mattress, a duvet and two pillows, filling the greybox box."""
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    joined(b["name"], [("M_GBI_wood", [((x0 + 0.6, y0, z0), (x1, y0 + 0.3, z1)), ((x1 - 0.08, y0, z0), (x1, y0 + 1.15, z1))]),
                       ("M_GBI_textile", [((x0 + 0.62, y0 + 0.3, z0 + 0.02), (x1 - 0.1, y1 - 0.06, z1 - 0.02)),
                                          ((x1 - 0.55, y1 - 0.06, z0 + 0.15), (x1 - 0.12, y1 + 0.08, (z0 + z1) / 2 - 0.05)),
                                          ((x1 - 0.55, y1 - 0.06, (z0 + z1) / 2 + 0.05), (x1 - 0.12, y1 + 0.08, z1 - 0.15))]),
                       (cover, [((x0 + 0.6, y1 - 0.07, z0), (x1 - 0.6, y1, z1))]),
                       ("M_GBI_wood", [((x0, y0, z0 + 0.2), (x0 + 0.55, y0 + 0.45, z1 - 0.2))])])


def rack(b):
    """Pallet racking over the greybox box (long along x): blue uprights in pairs every 2.7 m, orange beams at three levels, chipboard decks and
    a few pallets of cartons left on them."""
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    blue, orange, deck, wood, card = [], [], [], [], []
    nb = max(1, int(round((x1 - x0) / 2.7)))
    for k in range(nb + 1):
        x = x0 + 0.05 + (x1 - x0 - 0.1) * k / nb
        for z in (z0 + 0.05, z1 - 0.05):
            blue.append(((x - 0.05, y0, z - 0.05), (x + 0.05, y1, z + 0.05)))
        blue.append(((x - 0.02, y0 + 0.3, z0 + 0.08), (x + 0.02, y0 + 0.34, z1 - 0.08)))
        blue.append(((x - 0.02, y0 + 2.2, z0 + 0.08), (x + 0.02, y0 + 2.24, z1 - 0.08)))
    rng = np.random.default_rng(int(abs(x0 * 7 + z0 * 3)) + 21)
    for yy in (1.35, 2.7, y1 - y0 - 0.12):
        for z in (z0, z1 - 0.1):
            orange.append(((x0, y0 + yy, z), (x1, y0 + yy + 0.12, z + 0.1)))
        if yy < 3.5:
            deck.append(((x0 + 0.05, y0 + yy + 0.12, z0 + 0.1), (x1 - 0.05, y0 + yy + 0.14, z1 - 0.1)))
    for lvl in (0.0, 1.49, 2.84):
        for k in range(nb):
            if rng.random() < 0.38:
                cx = x0 + (x1 - x0) * (k + 0.5) / nb + (rng.random() - 0.5) * 0.4
                base = y0 + lvl + (0.0 if lvl == 0 else 0.0)
                wood.append(((cx - 0.6, base, z0 + 0.2), (cx + 0.6, base + 0.14, z1 - 0.2)))
                hh = 0.5 + rng.random() * 0.6 if lvl < 2.8 else 0.4 + rng.random() * 0.4
                card.append(((cx - 0.55, base + 0.14, z0 + 0.24), (cx + 0.55, base + 0.14 + hh, z1 - 0.24)))
    joined(b["name"], [("M_U_bluepaint", blue), ("M_GBI_furn_L4", orange), ("M_D_trim", deck), ("M_GBI_wood", wood), ("M_GBI_card", card)])


def pallets(b):
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    wood, card = [], []
    nx, nz = max(1, int((x1 - x0) // 1.2)), max(1, int((z1 - z0) // 1.0))
    for i in range(nx):
        for k in range(nz):
            a0, a1 = x0 + (x1 - x0) * i / nx, x0 + (x1 - x0) * (i + 1) / nx
            c0, c1 = z0 + (z1 - z0) * k / nz, z0 + (z1 - z0) * (k + 1) / nz
            wood.append(((a0 + 0.02, y0, c0 + 0.02), (a1 - 0.02, y0 + 0.14, c1 - 0.02)))
            card.append(((a0 + 0.05, y0 + 0.14, c0 + 0.05), (a1 - 0.05, y1, c1 - 0.05)))
    joined(b["name"], [("M_GBI_wood", wood), ("M_GBI_card", card)])


def hanging_sign(name, x, z, along_x, text, y):
    """A blue aisle board hung from the ceiling on two wires, white numbers on both faces (decor: overhead)."""
    w, h, t = 1.6, 0.5, 0.03
    top = M.Y + M.H
    if along_x:
        board = ((x - w / 2, y, z - t / 2), (x + w / 2, y + h, z + t / 2))
        wires = [((x + s * 0.6 - 0.004, y + h, z - 0.004), (x + s * 0.6 + 0.004, top, z + 0.004)) for s in (-1, 1)]
    else:
        board = ((x - t / 2, y, z - w / 2), (x + t / 2, y + h, z + w / 2))
        wires = [((x - 0.004, y + h, z + s * 0.6 - 0.004), (x + 0.004, top, z + s * 0.6 + 0.004)) for s in (-1, 1)]
    a = part(f"decor_{name}_board", "M_U_blue", lambda bm: cube(bm, *board))
    wv = part(f"decor_{name}_wires", "M_X_steel", lambda bm: boxes(bm, wires))

    def txt(bm):
        for s in (-1, 1):
            nrm = (0, 0, s) if along_x else (s, 0, 0)
            right = (s, 0, 0) if along_x else (0, 0, -s)
            add_text(bm, text, 0.32, 0.004, (x + nrm[0] * (t / 2), y + h / 2, z + nrm[2] * (t / 2)), right, (0, 1, 0), nrm)
    tx = part(f"decor_{name}_text", "M_X_white", txt, recalc=False)
    join(f"decor_{name}", [a, wv, tx])


def wall_band(side, a0, a1, y0, y1, mat="M_U_blue", stripe=True):
    """The store's blue band with its yellow stripe, high on a wall (flat panels 2 cm proud)."""
    P, nrm, right = wall_frame(side)

    def bx(a, b, ya, yb, d0, d1):
        p0, p1 = P(a, ya, d0), P(b, yb, d1)
        return tuple(min(p0[i], p1[i]) for i in range(3)), tuple(max(p0[i], p1[i]) for i in range(3))
    parts_ = [(mat, [bx(a0, a1, y0, y1, 0.0, 0.02)])]
    if stripe:
        parts_.append(("M_U_yellow", [bx(a0, a1, y0 - 0.14, y0 - 0.04, 0.0, 0.02)]))
    joined(f"Band_{side}_{int(a0)}", parts_)


def picture(name, side, a, y, w=0.6, h=0.84):
    """A framed print on an outer wall face: a dark frame and a pale print, 3 cm proud (inside the layout check's 5 cm)."""
    P, nrm, right = wall_frame(side)
    c = P(a, y, 0.0)
    frame = oriented_box(c, right, nrm, w, h, 0.0, 0.03)
    art = oriented_box(c, right, nrm, w - 0.1, h - 0.1, 0.0, 0.034)
    f = part(name + "_frame", "M_GBI_frame", lambda bm: cube(bm, *frame))
    p_ = part(name + "_print", "M_GBI_canvas", lambda bm: cube(bm, *art))
    return join(name, [f, p_])


# ---------------------------------------------------------------- the chambers
def dress_L4_1():
    for b in furniture("Gondola_"):
        gondola(b)
    for b in furniture("Island_"):
        island(b)
    for b in furniture("Cash_Desk"):
        checkout(b)
    for b in furniture("Display_"):
        display_table(b, 4)
    vents()
    Y = M.Y + 0.004
    for z in (-7.0, 5.0):                                        # the lava band's edges: hazard tape across the floor
        decal(f"Tape_{_t(z)}", "M_GBI_tape", GB.X0, GB.X1, z - 0.06, z + 0.06, Y)
    for i, (z, n) in enumerate(((16.5, "1"), (11.5, "2"))):
        for x in (-13.0, 13.0):
            hanging_sign(f"Aisle_{n}_{_t(x)}", x, z, True, n, M.Y + 3.2)
    hanging_sign("Bays", 0.0, -8.6, True, "A", M.Y + 3.45)
    wall_band("S", GB.X0 + 0.2, GB.X1 - 0.2, M.Y + 3.4, M.Y + 4.0)
    wall_band("N", GB.X0 + 0.2, -6.3, M.Y + 3.4, M.Y + 4.0)
    wall_band("N", -5.9, 5.9, M.Y + 3.4, M.Y + 4.0)
    wall_band("N", 6.3, GB.X1 - 0.2, M.Y + 3.4, M.Y + 4.0)
    arrows([(0.0, 21.0, 0), (0.0, 16.5, 0), (0.0, 11.5, 0), (0.0, 7.0, 0), (0.0, -11.0, 0), (-4.5, -15.5, 3), (-8.5, -15.5, 3), (-12.0, -16.0, 0)])


def dress_L4_2():
    rugs = ["M_U_rug_grey", "M_U_rug_blue", "M_U_rug_red", "M_U_rug_grey", "M_U_rug_blue"]
    covers = ["M_GBI_textile_dark", "M_U_rug_red", "M_GBI_textile_dark", "M_U_rug_blue"]
    for i, b in enumerate(sorted(furniture("Sofa_W_"), key=lambda b: b["name"])):
        sofa_set(b, rugs[i % len(rugs)])
    for i, b in enumerate(sorted(furniture("Bed_E_"), key=lambda b: b["name"])):
        bed_set(b, covers[i % len(covers)])
        z = (b["min"][2] + b["max"][2]) / 2
        picture(f"Pic_E_{i}", "E", z, M.Y + 1.75)
    for i, zc in enumerate((23.5, 16.5, 9.5, 2.5, -4.5)):
        picture(f"Pic_W_{i}", "W", zc - 0.6, M.Y + 1.6)
    # each mock room's back wall (the outer wall between two set walls) painted its own colour: a flat panel 2 cm proud, up to the set walls' 3 m
    edges = sorted({round((b["min"][2] + b["max"][2]) / 2, 3) for b in SK.colliders(M) if b["name"].startswith("Set_W_")})
    bays = list(zip(edges[:-1], edges[1:])) + [(edges[-1], GB.Z1)]
    for i, (za, zb) in enumerate(bays):
        for side, k in (("W", i), ("E", i + 2)):
            if side == "E" and zb > 20.5:
                continue
            P, nrm, right = wall_frame(side)
            p0, p1 = P(za + 0.12, M.Y + 0.1, 0.0), P(zb - 0.12, M.Y + 3.0, 0.02)
            mn, mx = tuple(min(p0[j], p1[j]) for j in range(3)), tuple(max(p0[j], p1[j]) for j in range(3))
            part(f"Accent_{side}_{i}", f"M_GBI_accent_{k % 5 + 1}", lambda bm, mn=mn, mx=mx: cube(bm, mn, mx))
    greybox_decor()
    wall_band("S", GB.X0 + 0.2, 10.6, M.Y + 3.4, M.Y + 4.0)
    wall_band("S", 13.4, GB.X1 - 0.2, M.Y + 3.4, M.Y + 4.0)
    for i, zc in enumerate((16.5, 2.5)):
        hanging_sign(f"Sets_W_{i}", -16.0, zc, False, "B" if i == 0 else "C", M.Y + 3.4)
        hanging_sign(f"Sets_E_{i}", 16.0, zc, False, "D" if i == 0 else "E", M.Y + 3.4)
    arrows([(12.0, 21.0, 0), (10.0, 15.0, 0), (10.0, 9.0, 0), (10.0, 3.0, 0), (10.0, -3.0, 0), (10.0, -8.5, 0)])


def dress_L4_3():
    for b in furniture("Rack_"):
        rack(b)
    for b in furniture("Pallets_"):
        pallets(b)
    greybox_decor()
    Y = M.Y + 0.004
    lines = []
    for zc in (18.0, 12.0, 6.0, 0.0, -6.0):
        for s in (-1, 1):
            z = zc + s * 0.75
            lines.append((-22.2, -1.8, z, z + 0.08) if s > 0 else (-22.2, -1.8, z - 0.08, z))
            lines.append((1.8, 22.2, z, z + 0.08) if s > 0 else (1.8, 22.2, z - 0.08, z))
    objs = [decal(f"Line_{i}", "M_U_yellow", a, b, c, d, Y) for i, (a, b, c, d) in enumerate(lines)]
    join("Floor_Lines", objs)
    for x in (-0.7, 0.7):                                        # the cross aisle's crush zone, taped
        decal(f"Tape_cross_{_t(x)}", "M_GBI_tape", x - 0.05, x + 0.05, 0.6, 5.4, Y + 0.001)
    arrows([(-14.0, 21.5, 1), (-7.0, 21.5, 1), (0.0, 15.0, 0), (0.0, 9.0, 0), (0.0, 3.0, 0), (0.0, -3.0, 0), (6.0, -9.0, 1), (13.0, -9.0, 1), (20.0, -9.2, 0)])


def dress_L3_2():
    for b in furniture("Plinth_"):
        (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
        joined(b["name"], [("M_GBI_furn_L3", [((x0, y0 + 0.04, z0), (x1, y1, z1))]), ("M_X_dark", [((x0 + 0.02, y0, z0 + 0.02), (x1 - 0.02, y0 + 0.04, z1 - 0.02))])])
    greybox_decor()
    canvases()


def canvases():
    """Blank canvases on the gallery's free-standing walls: stretched white cloth on a thin frame, 4 cm proud (inside the layout check's 5 cm)."""
    objs = []
    for b in SK.colliders(M):
        if not b["name"].startswith("Plaster_"):
            continue
        (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
        along_x = (x1 - x0) > (z1 - z0)
        L = (x1 - x0) if along_x else (z1 - z0)
        if L < 3.0:
            continue
        n = max(1, int(L // 4.0))
        for k in range(n):
            a = (x0 if along_x else z0) + L * (k + 0.5) / n
            w, h = (1.2, 0.9) if k % 2 == 0 else (0.8, 1.1)
            yc = M.Y + 1.55
            for s in (-1, 1):
                if along_x:
                    zf = z1 if s > 0 else z0
                    mn, mx = (a - w / 2, yc - h / 2, min(zf, zf + s * 0.04)), (a + w / 2, yc + h / 2, max(zf, zf + s * 0.04))
                else:
                    xf = x1 if s > 0 else x0
                    mn, mx = (min(xf, xf + s * 0.04), yc - h / 2, a - w / 2), (max(xf, xf + s * 0.04), yc + h / 2, a + w / 2)
                objs.append(part(f"Canvas_{len(objs)}", "M_GBI_canvas", lambda bm, mn=mn, mx=mx: cube(bm, mn, mx)))
    # each canvas stays its own object: check_layout reads one box per object, and a joined set would span the gallery


def dress_L3_3():
    """The colonnade's columns get a plinth and a capital, 4 cm proud (inside the layout check's 5 cm)."""
    for b in SK.colliders(M):
        if not b["name"].startswith("Column_"):
            continue
        (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
        trims = [((x0 - 0.04, y0, z0 - 0.04), (x1 + 0.04, y0 + 0.18, z1 + 0.04)), ((x0 - 0.04, y1 - 0.22, z0 - 0.04), (x1 + 0.04, y1, z1 + 0.04)),
                 ((x0 - 0.02, y1 - 0.3, z0 - 0.02), (x1 + 0.02, y1 - 0.22, z1 + 0.02))]
        part(f"Trim_{b['name']}", "M_D_trim", lambda bm, t=trims: boxes(bm, t))          # one object per column (the layout check reads its box)
    Y = M.Y + 0.004
    for z in (1.1, 4.9):
        for xc in (-6.0, 6.0):
            decal(f"Tape_{_t(xc)}_{_t(z)}", "M_GBI_tape", xc - 1.2, xc + 1.2, z + (0.0 if z < 3 else -0.1), z + (0.1 if z < 3 else 0.0), Y)


def dress_L3_4():
    Y = M.Y + 0.004
    decal("Tape_lava_w", "M_GBI_tape", -10.0, -9.88, -7.9, -0.1, Y)




# ---------------------------------------------------------------- L2, L1, B1: offices, cartons, pools
def desk(b, top="M_GBI_furn"):
    """An office desk over the greybox box: a top, two pedestal ends and a modesty panel; a monitor or a few papers on some."""
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    along_x = (x1 - x0) >= (z1 - z0)
    ends = [((x0, y0, z0), (x0 + 0.05, y1 - 0.03, z1)), ((x1 - 0.05, y0, z0), (x1, y1 - 0.03, z1))] if along_x else         [((x0, y0, z0), (x1, y1 - 0.03, z0 + 0.05)), ((x0, y0, z1 - 0.05), (x1, y1 - 0.03, z1))]
    panel = [((x0 + 0.05, y0 + 0.25, (z0 + z1) / 2 - 0.01), (x1 - 0.05, y1 - 0.03, (z0 + z1) / 2 + 0.01))] if along_x else         [(((x0 + x1) / 2 - 0.01, y0 + 0.25, z0 + 0.05), ((x0 + x1) / 2 + 0.01, y1 - 0.03, z1 - 0.05))]
    rng = np.random.default_rng(int(abs(x0 * 17 + z0 * 5)) + 31)
    dark = []
    if rng.random() < 0.6:
        cx, cz = (x0 + x1) / 2 + (rng.random() - 0.5) * 0.6, (z0 + z1) / 2
        dark.append(((cx - 0.25, y1, cz - 0.06), (cx + 0.25, y1 + 0.38, cz + 0.06)) if along_x else ((cx - 0.06, y1, cz - 0.25), (cx + 0.06, y1 + 0.38, cz + 0.25)))
    joined(b["name"], [(f"M_GBI_furn_{FLOOR}", [((x0, y1 - 0.03, z0), (x1, y1, z1))]), ("M_X_steel", ends + panel), ("M_X_dark", dark)])


def cartons(b):
    """A stack of cartons left where the greybox has a box: three or four cartons, taped."""
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    xm = (x0 + x1) / 2
    items = [((x0, y0, z0), (xm - 0.02, y0 + (y1 - y0) * 0.55, z1)), ((xm + 0.02, y0, z0), (x1, y0 + (y1 - y0) * 0.5, z1)),
             ((x0 + 0.1, y0 + (y1 - y0) * 0.55, z0 + 0.05), (xm + 0.2, y1, z1 - 0.1))]
    joined(b["name"], [("M_GBI_card", items)])


def cubicle(b):
    """A cubicle panel (the greybox's 1.4 m partition): grey fabric between aluminium caps."""
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    joined(b["name"], [("M_GBI_fabric", [((x0, y0 + 0.08, z0), (x1, y1 - 0.03, z1))]),
                       ("M_X_steel", [((x0, y1 - 0.03, z0), (x1, y1, z1)), ((x0, y0, z0), (x1, y0 + 0.08, z1))])])


def dress_L2_2():
    for b in furniture("Boxes_"):
        cartons(b)
    vents()
    greybox_decor()


def dress_L2_3():
    for b in furniture("Core_Table"):
        desk(b)
    greybox_decor()


def dress_L2_4():
    for b in furniture("Desk_"):
        desk(b)
    greybox_decor()


def dress_L1_2():
    for b in SK.colliders(M):
        if b["name"].startswith(("Pod_Back", "Pod_Side")):
            cubicle(b)
        elif b["name"].startswith("Pod_Desk"):
            (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
            joined(b["name"], [(f"M_GBI_furn_{FLOOR}", [((x0, y1 - 0.03, z0), (x1, y1, z1))]),
                               ("M_X_steel", [((x0 + 0.02, y0, z0 + 0.02), (x0 + 0.06, y1 - 0.03, z1 - 0.02)), ((x1 - 0.06, y0, z0 + 0.02), (x1 - 0.02, y1 - 0.03, z1 - 0.02))])])
    greybox_decor()


def dress_L1_3():
    for b in furniture("Desk_"):
        desk(b)
    vents()
    greybox_decor()


def dress_L1_4():
    for b in furniture("Desk_") + furniture("Conf_Table"):
        desk(b)
    greybox_decor()


def dress_B1():
    greybox_decor()
    vents()


def _t(v):
    return GB._tag(v)


DRESS = {"gbi_L4_1": dress_L4_1, "gbi_L4_2": dress_L4_2, "gbi_L4_3": dress_L4_3, "gbi_L3_2": dress_L3_2, "gbi_L3_3": dress_L3_3, "gbi_L3_4": dress_L3_4,
         "gbi_L2_2": dress_L2_2, "gbi_L2_3": dress_L2_3, "gbi_L2_4": dress_L2_4, "gbi_L1_2": dress_L1_2, "gbi_L1_3": dress_L1_3, "gbi_L1_4": dress_L1_4,
         "gbi_B1_2": dress_B1, "gbi_B1_3": dress_B1, "gbi_B1_4": dress_B1}


# ---------------------------------------------------------------- the file
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for d in (MATS, TILES, GEN, MODELS):
        d.clear()
    EMERG["cases"].clear()
    EMERG["heads"].clear()


def build_all():
    global ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, HAZ, LIGHTS, KIT
    reset()
    sc = bpy.context.scene
    ART = bpy.data.collections.new("Art")
    sc.collection.children.link(ART)
    PROPS, ARCH = bpy.data.collections.new("Props"), bpy.data.collections.new("Arch")
    ART.children.link(PROPS)
    ART.children.link(ARCH)
    SKIN, DOORS, LAYOUT, HAZ, LIGHTS, KIT = (bpy.data.collections.new(n) for n in ("Skin", "Doors", "Layout", "Hazards", "Lights", "Kit"))
    for c in (SKIN, DOORS, LAYOUT, HAZ, LIGHTS, KIT):
        sc.collection.children.link(c)
    make_materials()
    layout_from_model()
    place_kit()
    relink_textures()
    build_skin()
    build_doors()
    build_hazards()
    ceiling_panels()
    exit_signs()
    emergency_walls()
    finish_emergency()
    DRESS[SCENE]()
    w = bpy.data.worlds.new("Dark")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
    bg.inputs["Strength"].default_value = 0.0
    for ob in LAYOUT.objects:
        ob.hide_render = True
    for ob in ARCH.objects:
        ob.hide_render = True
    print(f"ART {SCENE}: {len(PROPS.objects)} props, {len(ARCH.objects)} arch twins, {len(SKIN.objects)} skin meshes, {len(DOORS.objects)} leaves, "
          f"{len(HAZ.objects)} hazards, {len(LIGHTS.objects)} lights, {len(KIT.objects)} kit stand-ins")


# ---------------------------------------------------------------- bake
NO_LIGHTMAP = {"Lamp_Emit", "Emergency_Emit", "M_GBI_nightlight", "M_X_exit", "M_Water"}


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
    """Export: the skin meshes as they are (one per material), and the props merged by material (faces against the shell dropped)."""
    if "Export" in bpy.data.collections:
        for o in list(bpy.data.collections["Export"].objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(bpy.data.collections["Export"])
    exp = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(exp)
    cols = SK.shell_boxes(M)
    out = {}
    for ob in bpy.data.collections["Skin"].objects:
        me = ob.data.copy()
        nm = ob.data.materials[0].name
        me.name = nm
        o2 = bpy.data.objects.new(nm, me)
        exp.objects.link(o2)
        out[nm] = o2
    by_mat = {}
    for ob in bpy.data.collections["Props"].objects:
        if ob.type != "MESH":
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
        assert not mname.startswith(SK.SHELL_MATS), f"{mname} is a shell material and cannot be on the props page"
        me = bpy.data.meshes.new(mname)
        bm.to_mesh(me)
        bm.free()
        if not me.polygons:
            bpy.data.meshes.remove(me)
            continue
        me.materials.append(bpy.data.materials[mname])
        ob = bpy.data.objects.new(mname, me)
        exp.objects.link(ob)
        out[mname] = ob
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
    if "UVMap" not in uvs:
        first = next((u for u in uvs if u.name != "lightmap"), None)
        if first is None:
            first = uvs.new(name="UVMap")
        first.name = "UVMap"
    for u in list(uvs):
        if u.name not in ("UVMap", "lightmap"):
            uvs.remove(u)
    return uvs


def lightmap_uv(objs, page):
    """One atlas for `objs`: smart-project islands at equal texel density, packed with MARGIN_PX on the fixed `page`. Returns (page, density)."""
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
    """The shell's lightmap UVs, packed by hand: every face of the skin is an axis-aligned rectangle (4 m at most), so each becomes its own
    pixel-aligned island with MARGIN_PX round it, shelf-packed at the highest density that fits the fixed page S. Deterministic."""
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
        bx = []
        for i, (o, p, v0, e1, e2, w, h) in enumerate(rects):
            pw, ph = max(1, math.ceil(w * D)), max(1, math.ceil(h * D))
            rot = ph > pw
            if rot:
                pw, ph = ph, pw
            bx.append((ph + 2 * m, pw + 2 * m, i, rot))
        bx.sort(key=lambda b: (-b[0], -b[1]))
        x = y = rowh = 0
        place = {}
        for bh, bw, i, rot in bx:
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
            u, t = (b * ph, a * pw) if rot else (a * pw, b * ph)
            assert -1e-3 <= u <= (ph if rot else pw) + 1e-3 and -1e-3 <= t <= (pw if rot else ph) + 1e-3, (o.name, u, t, rot)
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


def light_set(name):
    """day: the panels (Lamp_Emit), the night circuit and the EXIT signs; night: the night circuit, the emergency spots (Emergency_Emit) and the
    EXIT signs."""
    day = name == "day"
    for ob in bpy.data.collections["Lights"].objects:
        on = ob.name.startswith("LB_") or (ob.name.startswith("LD_") and day) or (ob.name.startswith("LN_") and not day)
        ob.hide_render = not on
    for mname, strength in (("Lamp_Emit", PANEL_EMIT if day else 0.0), ("Emergency_Emit", 0.0 if day else EMERG_EMIT)):
        m = bpy.data.materials.get(mname)
        if m:
            for n in m.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED":
                    n.inputs["Emission Strength"].default_value = strength


def bake_visibility():
    for c, hide in (("Art", True), ("Skin", True), ("Doors", False), ("Export", False), ("Kit", False), ("Hazards", True), ("Lights", False)):
        bpy.data.collections[c].hide_render = hide
    bpy.data.collections["Art"].hide_viewport = True
    bpy.data.collections["Skin"].hide_viewport = True


def shoulder(rgb):
    knee_pc, roll = SHOULDER
    peak = rgb.max(axis=2)
    lit = peak[peak > 1e-5]
    if not len(lit):
        return rgb, 0.0
    k = float(np.percentile(lit, knee_pc))
    m = roll * k
    f = np.where(peak <= k, peak, k + (peak - k) / (1 + (peak - k) / (m - k)))
    return rgb * (f / np.maximum(peak, 1e-8))[..., None], k


def stage_bake():
    import time
    exp = make_export_objects()
    bake_visibility()
    shell = [o for k, o in sorted(exp.items()) if o.data.materials[0].name.startswith(SK.SHELL_MATS)]
    props = [o for k, o in sorted(exp.items()) if o not in shell and o.data.materials[0].name not in NO_LIGHTMAP]
    props += sorted((o for o in bpy.data.collections["Doors"].objects if o.type == "MESH"), key=lambda o: o.name)
    pages = []
    for n, objs in enumerate((shell, props)):
        print(f"lightmap {n}: {[o.name for o in objs]}")
        pages.append(rect_uv(objs, PAGES[SCENE][n]) if n == 0 else lightmap_uv(objs, PAGES[SCENE][n]))
    report = {}
    for st, off, samples in (("day", 0, SAMPLES), ("night", NIGHT_OFFSET, NIGHT_SAMPLES)):
        light_set(st)
        setup_cycles(samples, bake=True)
        for n, objs in enumerate((shell, props)):
            t0 = time.time()
            S, dens = pages[n]
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
            bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
            rgb = denoise_image(img, S)[..., :3]
            rgb_s, knee = shoulder(rgb)
            peak = rgb_s.max(axis=2)
            pc = np.percentile(peak[peak > 1e-5], [50, 90, 99, 99.5, 100]) if (peak > 1e-5).any() else [1.0] * 5
            scale = float(min(pc[3], WHITE_CAP * pc[1]))
            out = np.ones((S, S, 4), np.float32)
            out[..., :3] = srgb_encode(rgb_s / scale)
            png = bpy.data.images.new(f"LM_{n}_png", S, S, alpha=False)
            png.colorspace_settings.name = "Non-Color"
            png.pixels.foreach_set(out.ravel())
            idx = n + off
            png.filepath_raw = str(work() / f"{SCENE}_{idx}.png")
            png.file_format = "PNG"
            png.save()
            key = "lightmap" if st == "day" else "lightmap_night"
            for m in mats:
                m[key] = lm_url(SCENE, idx)
                m[key + "_intensity"] = round(math.pi * scale, 4)
                for nd in [nd for nd in m.node_tree.nodes if nd.name.startswith("BAKE_TARGET")]:
                    m.node_tree.nodes.remove(nd)
            raw = rgb.max(axis=2)
            report[f"{st}_{n}"] = {"map": idx, "size": S, "px_per_m": round(dens, 1), "scale": round(scale, 4), "knee": round(knee, 4),
                                   "raw_p50_p90_p99_max": [round(float(v), 4) for v in np.percentile(raw[raw > 1e-5], [50, 90, 99, 100])] if (raw > 1e-5).any() else [],
                                   "samples": samples, "device": bpy.context.scene.cycles.device, "seconds": round(time.time() - t0),
                                   "materials": [m.name for m in mats]}
            print("  baked", st, n, {k: v for k, v in report[f"{st}_{n}"].items() if k != "materials"})
            bpy.data.images.remove(img)
            bpy.data.images.remove(png)
    light_set("day")
    stills_dir(SCENE).mkdir(parents=True, exist_ok=True)
    (stills_dir(SCENE) / "bake.json").write_text(json.dumps(report, indent=1))
    for c in ("Art", "Skin"):
        bpy.data.collections[c].hide_render = False
        bpy.data.collections[c].hide_viewport = False
    for ob in ARCH_objects():
        ob.hide_render = True
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


def ARCH_objects():
    return list(bpy.data.collections["Arch"].objects)


# ---------------------------------------------------------------- privacy
KEEP_PROPS = {"lightmap", "lightmap_intensity", "lightmap_night", "lightmap_night_intensity"}
LAYOUT_PREFIX = ("DoorLeaf_", "Marker_", "Spot_", "Hazard_")


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
    for im in bpy.data.images:
        if im.packed_file:
            # a packed image also keeps the path it was packed from (ImagePackedFile.filepath, read only): the store's textures carry the
            # store author's machine path. Re-pack them from their own bytes under a neutral relative name.
            if any(pf.filepath and not pf.filepath.startswith("//") for pf in im.packed_files):
                data = bytes(im.packed_file.data)
                ext = Path(im.packed_files[0].filepath.replace("\\", "/")).suffix or ".png"
                im.unpack(method="REMOVE")
                set_path(im, "filepath", "//packed/" + bpy.path.clean_name(im.name) + ext)
                im.pack(data=data, data_len=len(data))
            elif im.filepath and not im.filepath.startswith(("//generated/", "//packed/")):
                set_path(im, "filepath", "//packed/" + bpy.path.clean_name(im.name) + ".png")
        elif im.source == "FILE" and im.filepath:
            ab = Path(bpy.path.abspath(im.filepath))
            hit = find_texture(ab.name) or ab
            try:
                rel = "//" + os.path.relpath(hit, blend_path(SCENE).parent).replace("\\", "/")
            except ValueError:
                rel = "//" + ab.name
            set_path(im, "filepath", rel)
    for lib in list(bpy.data.libraries):
        try:
            bpy.data.libraries.remove(lib)
        except Exception:
            pass
    for scr in bpy.data.screens:
        for a in scr.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"_" * 1000
                    sp.params.directory = b"//"


def find_texture(name):
    """A texture of the repo's (the kit's stand-ins read theirs from blender/textures/kit/), by file name."""
    hits = sorted((ROOT / "blender/textures").rglob(name))
    return hits[0] if hits else None


def relink_textures():
    for im in bpy.data.images:
        if im.packed_file or im.source != "FILE" or not im.filepath:
            continue
        if not Path(bpy.path.abspath(im.filepath)).exists():
            hit = find_texture(Path(bpy.path.abspath(im.filepath)).name)
            if hit:
                im.filepath = str(hit)
                im.reload()


def save_blend():
    p = blend_path(SCENE)
    p.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    scrub_private()
    bpy.ops.wm.save_as_mainfile(filepath=str(p), compress=True)
    scrub_private()
    bpy.ops.wm.save_mainfile(compress=True)


def load_scene_file():
    bpy.ops.wm.open_mainfile(filepath=str(blend_path(SCENE)))
    relink_textures()
    global ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, HAZ, LIGHTS, KIT
    c = bpy.data.collections
    ART, PROPS, ARCH, SKIN, DOORS, LAYOUT, HAZ, LIGHTS, KIT = (c.get(n) for n in COLLS)
    for m in bpy.data.materials:
        MATS[m.name] = m


# ---------------------------------------------------------------- export
def stage_export():
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    for c in ("Art", "Skin"):
        bpy.data.collections[c].hide_viewport = True
    leaves = [o for o in bpy.data.collections["Doors"].objects if o.type == "MESH"]
    hz = list(bpy.data.collections["Hazards"].objects)
    stash = {o.name: {k: o[k] for k in o.keys()} for o in leaves}
    for o in leaves:
        for k in list(o.keys()):
            del o[k]
    bpy.ops.object.select_all(action="DESELECT")
    for o in list(exp.objects) + leaves + hz:
        o.hide_set(False)
        o.hide_render = False
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = work() / f"{SCENE}_raw.glb"
    scrub_private()
    for mname, strength in (("Lamp_Emit", PANEL_EMIT), ("Emergency_Emit", EMERG_EMIT)):   # exported on: the page switches them off and on
        m = bpy.data.materials.get(mname)
        if m:
            for n in m.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED":
                    n.inputs["Emission Strength"].default_value = strength
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_animations=False)
    for o in leaves:
        for k, v in stash[o.name].items():
            o[k] = v
    light_set("day")
    print("EXPORTED", raw, raw.stat().st_size)
    for c in ("Art", "Skin"):
        bpy.data.collections[c].hide_viewport = False
    exp.hide_viewport = exp.hide_render = True
    import export_scene
    export_scene.write(SCENE, world_json(SCENE))
    save_blend()


def stage_check():
    """check_layout.py on the Art collection, heights read from the chamber's floor: the props, and the shell's and the kit's colliders' grey
    twins (Art/Arch, never rendered or exported), as on the hotel floors."""
    import check_layout
    arch = ARCH_objects()
    for o in arch:
        o.hide_render = False
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = check_layout.main(["--scene", SCENE, "--collection", "Art", "--floor", str(M.Y)])
    for o in arch:
        o.hide_render = True
    print(buf.getvalue())
    (work() / f"{SCENE}_check_layout.txt").write_text(buf.getvalue() + f"CHECK_LAYOUT exit {code}" + chr(10))
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


DETAIL = {"gbi_L4_1": ((3.0, 1.6, 16.5), (16.0, 1.0, 16.2), 62), "gbi_L4_2": ((-11.5, 1.6, 12.2), (-23.0, 0.6, 9.0), 62),
          "gbi_L4_3": ((-0.6, 1.6, 9.0), (-18.0, 1.6, 9.2), 62), "gbi_L3_2": ((-0.5, 1.55, 9.0), (-4.0, 0.9, 14.0), 62),
          "gbi_L3_3": ((-23.0, 1.55, 15.0), (12.0, 1.3, 13.0), 62), "gbi_L3_4": ((-24.5, 1.55, 19.5), (10.0, 1.3, 19.8), 62),
          "gbi_L2_2": ((2.0, 1.6, 14.0), (-4.35, 1.1, 8.0), 62), "gbi_L2_3": ((-18.0, 1.55, 19.0), (18.0, 1.3, 19.0), 62),
          "gbi_L2_4": ((-11.0, 1.55, 24.0), (-11.0, 1.3, -10.0), 62), "gbi_L1_2": ((-2.0, 1.6, 10.5), (-9.0, 0.8, 0.0), 62),
          "gbi_L1_3": ((0.0, 1.55, 24.0), (0.0, 1.3, -18.0), 62), "gbi_L1_4": ((-14.0, 1.55, 16.0), (-14.0, 1.3, -12.0), 62),
          "gbi_B1_2": ((-14.0, 1.6, 20.0), (8.0, 0.3, -2.0), 62), "gbi_B1_3": ((-24.0, 1.55, 6.0), (20.0, 1.3, 6.0), 62),
          "gbi_B1_4": ((-18.0, 1.6, 16.0), (0.0, 0.3, 3.0), 62)}


def shots():
    Y = M.Y
    (pos, face, pitch) = M.still
    ln = math.hypot(*face) or 1.0
    f = (face[0] / ln, face[1] / ln)
    eye = (pos[0], Y + GB.EYE, pos[2])
    tgt = (pos[0] + f[0] * 10, Y + GB.EYE + math.tan(math.radians(pitch)) * 10, pos[2] + f[1] * 10)
    south = pos[2] > 0
    wide = ((GB.X1 - 1.2, Y + M.H - 0.35, GB.Z1 - 1.2), (-6.0, Y + 0.3, -4.0)) if south else ((GB.X0 + 1.2, Y + M.H - 0.35, GB.Z0 + 1.2), (6.0, Y + 0.3, 4.0))
    dl, dt, dfov = DETAIL[SCENE]
    return {"1_arrival": (eye, tgt, 75, "day"), "2_wide": (wide[0], wide[1], 80, "day"),
            "3_detail": ((dl[0], Y + dl[1], dl[2]), (dt[0], Y + dt[1], dt[2]), dfov, "day"), "4_night": (eye, tgt, 75, "night")}


def stage_render():
    sc = bpy.context.scene
    d = stills_dir(SCENE)
    d.mkdir(parents=True, exist_ok=True)
    scrub_private()
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
    for c, hide in (("Art", False), ("Skin", False), ("Doors", False), ("Lights", False), ("Kit", False), ("Hazards", False)):
        bpy.data.collections[c].hide_render = hide
    for ob in ARCH_objects():
        ob.hide_render = True
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
    for key, (loc, tgt, fov, st) in shots().items():
        if which not in ("all", key):
            continue
        light_set(st)
        sc.view_settings.exposure = arg("--exposure", 0.0, float) + (arg("--night-ev", 1.5, float) if st == "night" else 0.0)
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
    light_set("day")
    sc.view_settings.exposure = arg("--exposure", 0.0, float)
    if which in ("all", "plan"):
        x0, x1, z0, z1 = GB.FOOT[0] - 0.4, GB.FOOT[1] + 0.4, GB.FOOT[2] - 0.4, GB.FOOT[3] + 0.4
        span = x1 - x0
        cam = look_cam("plan", ((x0 + x1) / 2, M.Y + 30.0, (z0 + z1) / 2), None, ortho=span)
        cam.rotation_euler = (0, 0, 0)
        sc.camera = cam
        hidden = []
        top = M.Y + min(M.H - 0.3, 3.4)
        for o in list(bpy.data.collections["Skin"].objects) + list(bpy.data.collections["Props"].objects) + list(bpy.data.collections["Kit"].all_objects):
            if o.type != "MESH" or o.hide_render:
                continue
            zs = [(o.matrix_world @ v.co).z for v in o.data.vertices]
            if o.name.startswith(("M_D_ceil_", "Panel_", "decor_")) or (zs and min(zs) > top):
                o.hide_render = True
                hidden.append(o)
        kit_roofs = []
        for o in bpy.data.collections["Kit"].all_objects:
            if o.type == "MESH" and not o.hide_render and any(s in o.name for s in ("Ceiling", "Sky_Emit", "Tube_Emit")):
                o.hide_render = True
                kit_roofs.append(o)
        W = 1600
        H = int(round(W * (z1 - z0) / span))
        sc.render.resolution_x, sc.render.resolution_y = W, H
        sc.render.image_settings.file_format = "JPEG"
        path = d / "plan.jpg"
        sc.render.filepath = str(path)
        sc.view_settings.exposure = arg("--exposure", 0.0, float) + 0.5
        bpy.ops.render.render(write_still=True)
        strip_jpeg_comments(path)
        for o in hidden + kit_roofs:
            o.hide_render = False
        sc.view_settings.exposure = arg("--exposure", 0.0, float)
        print("PLAN", path, W, H)


# ---------------------------------------------------------------- main
def main():
    global SCENE, M, FLOOR
    scenes = arg("--scenes", "gbi_L4_1").split(",")
    for sc in scenes:
        SCENE = sc
        M = SK.model(sc)
        FLOOR = M.floor
        print(f"==== {sc} ({FLOOR}) stage {STAGE}")
        if STAGE in ("art", "all"):
            build_all()
            save_blend()
        else:
            load_scene_file()
        if STAGE in ("art", "layout"):
            import export_scene
            export_scene.write(SCENE, world_json(SCENE))
        if STAGE in ("bake", "all"):
            stage_bake()
        if STAGE in ("export", "all", "bake_export"):
            stage_export()
        if STAGE in ("check", "all", "art", "layout"):
            stage_check()
        if STAGE == "resave":                             # load, scrub and save again (no other change)
            save_blend()
        if STAGE in ("render", "all"):
            stage_render()
            save_blend()
        print(f"==== {sc} done")


main()
