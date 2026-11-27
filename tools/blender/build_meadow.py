"""Builds the dreamcore meadow (`meadow`) in Blender, bakes its ambient occlusion, renders its day and night backdrops and exports world/meadow.glb
(docs/BLENDER.md, "9. meadow").

Re-runnable, from the repo root (node tools/blender/dump_layout.mjs meadow first):

    python tools/blender/build_meadow.py --stage textures --src <folder>     (plain Python with numpy and Pillow: the three Poly Haven maps and the
                                                                               generated images -> blender/textures/meadow/)
    blender -b --python tools/blender/build_meadow.py -- --stage art          (build the art, save blender/scenes/meadow.blend)
    blender -b blender/scenes/meadow.blend --python tools/blender/build_meadow.py -- --stage bake [--samples 256]
    blender -b blender/scenes/meadow.blend --python tools/blender/build_meadow.py -- --stage export
    blender -b blender/scenes/meadow.blend --python tools/blender/build_meadow.py -- --stage axes
    blender -b blender/scenes/meadow.blend --python tools/blender/build_meadow.py -- --stage backdrop   (the two 4096 x 2048 panoramas)
    blender -b blender/scenes/meadow.blend --python tools/blender/build_meadow.py -- --stage render [--render-samples 128] [--only 1_arrival]
    blender -b --python tools/blender/build_meadow.py -- --stage all          (art, axes, bake, export, backdrop, render)
    python tools/blender/pack_scene.py meadow --work <work>                   (WebP AO maps and WebP textures -> world/)
    python tools/blender/build_meadow.py --stage pack-backdrops --work <work> (WebP backdrops -> world/backdrops/)

The meadow is the forest opening up, so it is built from the forest's own pieces (tools/blender/build_forest.py on claude/blender-forest): the same
three tree variants (A blossom, B spire, C parasol) made by the same code from the same seeds, the same bark and crown pictures, the same path sand, and
the page's look (FOREST_LOOK: a pink hemisphere light and haze). What is the meadow's own: a lighter, sunnier lawn with tall grass, the 420 flowers, a
straight path north to the house with a spur to the shed, and backdrops with more sky, open fields and groves, the forest dense to the south.

Only the ambient occlusion is baked (docs/BLENDER.md R1, AO-only scenes): every baked material carries `aomap` and `aomap_intensity` (no
`lightmap`), on the second UV set.

The 120 trees stand exactly at the layout's `trees` [x, z, trunk radius], because their trunks are the colliders; each variant is one mesh (bark and
crown) exported once with EXT_mesh_gpu_instancing. The 420 flowers stand exactly at the layout's `flowers` [x, z, colour]: five meshes, one per
colour, each a small clump of blooms, instanced, passable and not baked. The tall grass is instanced too (three clump variants), passable.

The owner's models, the shed (models/world/shed.glb) and the house (models/world/cottage.glb), are drawn by the page. They are imported here only as
stand-ins, placed the way index.html placeBuilding() places them, for the ground's AO bake (their contact shadow) and the stills; they are never
exported, never changed, never decimated, and never saved in the .blend (each stage that needs them imports them again from models/world/).

No coordinate of the layout is typed in here: the ground, the trees, the flowers, the arrival, the shed, the house and their doors come from
blender/layout/meadow.json. A game point (x, y, z) is Blender (x, -z, y).
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
    from mathutils import Matrix, Vector, noise, kdtree
except ImportError:                       # the textures stage runs in plain Python (numpy and Pillow)
    bpy = None

ROOT = Path(__file__).resolve().parents[2]
SCENE = "meadow"
LAYOUT = ROOT / f"blender/layout/{SCENE}.json"
TEX = ROOT / f"blender/textures/{SCENE}"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
STILLS = ROOT / f"docs/renders/{SCENE}"
AO_URL = "world/lightmaps/" + SCENE + "_{}.webp"      # the path the page reads from the material's `aomap` custom property
MARGIN_PX = 8

if "--" in sys.argv:
    args = sys.argv[sys.argv.index("--") + 1:]
else:
    args = sys.argv[1:] if bpy is None else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 256, int)
DEVICE = arg("--device", "auto")

L = json.loads(LAYOUT.read_text())
K = L["constants"]
TREES = L["trees"]                         # [x, z, trunk radius], game metres
FLOWERS = L["flowers"]                     # [x, z, colour index 0..4]
COLL = {}
for _c in L["world"]["colliders"]:
    COLL.setdefault(_c["s"], []).append(_c)
HX, HZ = K["half"]
PZ0, PZ1 = K["cz"] - HZ, K["cz"] + HZ       # the playable ground's z range (-84 .. 12)
EXT = (-62.0, 62.0, -104.0, 32.0)           # the art's ground (x0, x1, z0, z1): past the edge walls, for the ring of trees and the forest to the south
SHED, HOUSE = K["shed"], K["house"]
assert len(TREES) == K["trees"] == 120 and len(FLOWERS) == K["flowers"] == 420

# ---- the path: straight north on x = 0 from the forest (south, past the edge) to the house's door, with a spur west to the shed's door
PATH_W = 3.6                               # the ribbon's width in the meadow; its picture's ragged edge leaves about 2.9 m of sand (the flowers keep |x| >= 1.8)
PATH_W_FOREST = 7.0                        # the forest's path is 7 m wide: past the south edge the ribbon widens to meet it
PATH_Z0 = EXT[3]                           # from the art's south end ...
PATH_Z1 = HOUSE["door"]["at"][1] - 1.0     # ... to under the house's front (the page draws the house over its end)
SPUR_W = 2.4
SPUR_X0, SPUR_X1 = -1.0, SHED["at"][0] + SHED["half"][1] - 0.3       # from the path's edge to under the shed's front (its door faces the path, +x)
SPUR_Z = SHED["door"]["at"][1]


def path_w(z):
    """The main ribbon's width at z: 3.6 m in the meadow, widening to the forest's 7 m past the south edge, and to 5 m in front of the house's door."""
    t = min(1.0, max(0.0, (z - (PZ1 - 4.0)) / 14.0))
    w = PATH_W + (PATH_W_FOREST - PATH_W) * t * t * (3 - 2 * t)
    hz = HOUSE["door"]["at"][1]
    u = min(1.0, max(0.0, (hz + 5.0 - z) / 3.5))
    return w + 1.4 * u * u * (3 - 2 * u)


def on_path(x, z, pad=0.0):
    if PATH_Z1 - pad <= z <= PATH_Z0 and abs(x) < path_w(z) / 2 + pad:
        return True
    return SPUR_X1 - pad <= x <= SPUR_X0 + pad and abs(z - SPUR_Z) < SPUR_W / 2 + pad


def lin_hex(h):
    c = np.array([(h >> 16) & 255, (h >> 8) & 255, h & 255], float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


# ---- the look (index.html FOREST_LOOK, which the meadow shares): a hemisphere light (#fff0f8 over #f0c8dc, 1.55) and a linear fog #f4d8ec from 22 to
# 105 m, with no tone mapping. A material of albedo a shows about a x 1.55. The trees' colours are the forest's, so the two scenes read as one place.
SKY_HEX = 0xf4d8ec
FOG = (22.0, 105.0)
HEMI_SKY, HEMI_GROUND, HEMI_K = 0xfff0f8, 0xf0c8dc, 1.55
ALB = 1 / 1.5
CROWN_CELLS = [0xf7b8d2, 0xf9c8dc, 0xd4c4f4, 0xffcfd6,       # A, blossom: pink, light pink, lilac, rose          (the forest's, unchanged)
               0xbfe8d4, 0xa8d8f0, 0xc8d0f4, 0xd4f0dc,       # B, spire: mint, sky, periwinkle, pale mint
               0xffd8b0, 0xfff4c0, 0xffe2cc, 0xf8ccbe]       # C, parasol: peach, butter, apricot cream, salmon
VARIANTS = "ABC"
VARIANT_CELLS = {"A": [0, 1, 2, 3], "B": [4, 5, 6, 7], "C": [8, 9, 10, 11]}
VARIANT_P = (0.45, 0.2, 0.35)                                # the meadow's edge: more blossom and parasol, fewer spires than the forest (0.4, 0.3, 0.3)
BARK_HEX = {"A": 0xf0dcdc, "B": 0xe4dcec, "C": 0xf4e4d0}
FLOWER_HEX = [0xff8fbf, 0xfff07a, 0xb8a0ff, 0xffffff, 0x8fe0ff]   # index.html FLOWER_COLORS: the layout's colour index 0..4
GROUND_LIN = np.array((0.40, 0.56, 0.36))                    # the meadow's lawn: the forest's mint (0.34, 0.50, 0.37) in the open, lighter and sunnier
PATH_LIN = np.array((0.56, 0.45, 0.41))                      # the forest's peach sand
CELL = 256                                                    # the crown atlas: 4 x 4 cells of 256 px
INSET = 4
PERIOD = (CELL - 2 * INSET) // 2


def rng_for(*key):
    h = 2166136261
    for ch in "|".join(str(k) for k in key):
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return np.random.default_rng(h)


# ================================================================ the textures stage (plain Python: numpy and Pillow)
def tx_load(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB"), np.float32) / 255.0


def tx_save(arr, fn, q=88):
    from PIL import Image
    a = (np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8)
    im = Image.fromarray(a)
    p = TEX / fn
    if fn.endswith(".png"):
        im.save(p, optimize=True)
    else:
        im.save(p, "JPEG", quality=q, optimize=True)
    print("TEXTURE", fn, im.size, p.stat().st_size)


def to_lin(a):
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def to_srgb(a):
    a = np.clip(a, 0, 1)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(a, 1 / 2.4) - 0.055)


def fft_blur(a, sigma):
    """A periodic gaussian blur (the textures tile)."""
    H, W = a.shape[:2]
    g = np.exp(-2 * (np.pi * sigma) ** 2 * (np.fft.fftfreq(H)[:, None] ** 2 + np.fft.fftfreq(W)[None, :] ** 2))
    if a.ndim == 2:
        return np.real(np.fft.ifft2(np.fft.fft2(a) * g))
    return np.stack([np.real(np.fft.ifft2(np.fft.fft2(a[..., c]) * g)) for c in range(a.shape[2])], -1)


def pnoise(shape, sigma, rng):
    n = fft_blur(rng.standard_normal(shape), sigma)
    return (n - n.mean()) / (n.std() + 1e-9)


def detail(img, sigma):
    """A photo's luminance detail as a ratio around 1 (its colour and large-scale shading dropped)."""
    lum = to_lin(img) @ np.array([0.2126, 0.7152, 0.0722])
    return lum / (fft_blur(lum, sigma) + 1e-4)


def cap_p90(lin, cap=0.76):
    """Scale a linear picture down so the p90 of its brightest channel is at most `cap` (the page lights it at about 1.55)."""
    p = float(np.percentile(lin[..., :3].max(axis=-1), 90))
    return lin * (cap / p) if p > cap else lin


def tex_grass(src):
    """The meadow's lawn: the photo's grass detail on a lighter, sunnier mint than the forest's, with a little warm patchiness (sun-dried and clover)
    and only a few pink petals (the forest's drifts thinned to a scatter)."""
    g = tx_load(src / "leafy_grass_diff_1k.jpg")
    rng = np.random.default_rng(32)
    d = np.clip(detail(g, 48), 0.3, 2.2)
    lin = to_lin(g)
    leaf = np.clip((lin[..., 0] - lin[..., 1]) * 9.0, 0, 1) ** 1.6
    drift = np.clip((pnoise(leaf.shape, 70, rng) - 0.9) * 1.2, 0, 1) * np.clip(0.6 + 0.6 * pnoise(leaf.shape, 14, rng), 0, 1)
    leaf = fft_blur(leaf, 0.8) * drift * 0.6
    low = 1 + 0.06 * pnoise(d.shape, 90, rng)
    warm = np.clip(0.5 + 0.5 * pnoise(d.shape, 55, rng), 0, 1)[..., None]
    base = GROUND_LIN * (1 - 0.25 * warm) + np.array((0.47, 0.55, 0.32)) * 0.25 * warm
    out = base * (1 + 0.55 * (d - 1))[..., None] * low[..., None]
    petal = np.array((0.62, 0.40, 0.52)) * (0.9 + 0.2 * d)[..., None]
    out = out * (1 - 0.7 * leaf[..., None]) + petal * 0.7 * leaf[..., None]
    tx_save(to_srgb(cap_p90(out, 0.64)), "grass.jpg")


def tex_bark(src):
    """The forest's bark, unchanged."""
    b = tx_load(src / "bark_platanus_diff_1k.jpg")
    d = np.clip(detail(b, 60), 0.35, 1.9)
    out = 0.80 * (1 + 0.65 * (d - 1))[..., None] * np.array((1.0, 0.98, 0.97))
    tx_save(to_srgb(np.clip(out, 0, 1)), "bark.jpg")


def tex_path(src):
    """The path ribbon's picture (the forest's sand): u along the path (PATH_W a repeat), v across it (v = 0.5 its middle line). Sand, lighter where it
    is trodden, a grassy fringe, and a ragged edge in the alpha (the material cuts it at 0.5)."""
    s = tx_load(src / "forrest_sand_01_diff_1k.jpg")
    rng = np.random.default_rng(9)
    d = np.clip(detail(s, 48), 0.3, 2.2)
    d = np.tile(d, (2, 2)).reshape(1024, 2, 1024, 2).mean(axis=(1, 3))   # two repeats across 3.6 m, still periodic
    N = 1024
    v = (np.arange(N) + 0.5) / N
    v = v[::-1][:, None]
    edge = {}
    for side in (0, 1):
        e = 0.40 + 0.035 * pnoise((1, N), 40, rng)[0] + 0.012 * pnoise((1, N), 5, rng)[0]
        edge[side] = e[None, :]
    half = np.where(v < 0.5, edge[0], edge[1])
    off = np.abs(v - 0.5)
    fine = pnoise((N, N), 1.6, rng)
    alpha = np.clip((half - off) / 0.016 + 0.5 + 0.35 * fine, 0, 1)
    t = np.clip(off / half, 0, 1)
    trod = 1.06 - 0.16 * t ** 2
    col = PATH_LIN * (1 + 0.5 * (d - 1))[..., None] * trod[..., None]
    moss = np.clip((t - 0.78) / 0.22, 0, 1)[..., None] * (0.5 + 0.5 * (pnoise((N, N), 6, rng) > 0)[..., None])
    col = col * (1 - 0.45 * moss) + GROUND_LIN * (1 + 0.4 * (d - 1))[..., None] * 0.45 * moss
    col = cap_p90(col, 0.62)
    rgba = np.concatenate([to_srgb(col), alpha[..., None]], -1)
    tx_save(rgba, "path.png")


def tex_crowns():
    """The forest's crown atlas, unchanged: 4 x 4 cells of 256 px, each a pastel (CROWN_COLORS / 1.5) with soft dappling."""
    A = np.zeros((4 * CELL, 4 * CELL, 3))
    for c, hx in enumerate(CROWN_CELLS):
        rng = np.random.default_rng(100 + c)
        base = lin_hex(hx) * ALB
        shp = (CELL, PERIOD)
        low = pnoise(shp, 14, rng)
        mid = pnoise(shp, 4, rng)
        spk = pnoise(shp, 1.1, rng)
        val = 1 + 0.07 * low + 0.05 * mid
        tile = base * val[..., None]
        light = np.clip((spk - 1.4) * 2.0, 0, 1)[..., None]
        tile = tile * (1 - light) + np.minimum(base * 1.22 + 0.04, 0.78) * light
        dark = np.clip((-spk - 1.7) * 2.0, 0, 1)[..., None]
        tile = tile * (1 - 0.22 * dark)
        grad = np.linspace(0.92, 1.07, CELL)[:, None, None]
        tile = np.concatenate([tile, tile], axis=1) * grad
        tile = np.pad(tile, ((0, 0), (INSET, INSET), (0, 0)), mode="wrap")
        r0, c0 = (c // 4) * CELL, (c % 4) * CELL
        A[r0:r0 + CELL, c0:c0 + CELL] = tile
    tx_save(to_srgb(np.minimum(A, 0.8))[::-1], "crowns.jpg", q=90)


def tex_decor():
    """The small things' atlas, 8 cells of 64 x 64: the five petal colours (FLOWER_COLORS / 1.5, a little lighter at the tip), the forest's blade green
    (dark base to light tip), the flowers' butter centres, and a second blade, sage to straw (the tall grass's seed heads)."""
    A = np.zeros((64, 512, 3))
    rng = np.random.default_rng(6)
    t = np.linspace(0, 1, 64)[:, None, None]                                # UV order: row 0 is v = 0
    for i, hx in enumerate(FLOWER_HEX):
        A[:, i * 64:(i + 1) * 64] = lin_hex(hx) * ALB * (0.9 + 0.12 * t) * (1 + 0.05 * pnoise((64, 64), 3, rng))[..., None]
    A[:, 320:384] = np.array((0.17, 0.32, 0.21)) * (1 - t) + np.array((0.44, 0.64, 0.46)) * t
    A[:, 384:448] = lin_hex(0xfff0a0) * ALB
    A[:, 448:512] = np.array((0.22, 0.34, 0.22)) * (1 - t) + np.array((0.62, 0.60, 0.40)) * t
    tx_save(to_srgb(np.minimum(A, 0.8))[::-1], "decor.png")


def stage_textures():
    src = Path(arg("--src", "."))
    TEX.mkdir(parents=True, exist_ok=True)
    tex_grass(src)
    tex_bark(src)
    tex_path(src)
    tex_crowns()
    tex_decor()


def stage_pack_backdrops():
    """The backdrop PNGs from the work folder -> world/backdrops/meadow_day.webp and meadow_night.webp (4096 x 2048, WebP q85)."""
    from PIL import Image
    work = Path(arg("--work", "."))
    out = ROOT / "world/backdrops"
    out.mkdir(parents=True, exist_ok=True)
    for k in ("day", "night"):
        im = Image.open(work / f"backdrop_{k}.png").convert("RGB")
        assert im.size == (4096, 2048), im.size
        dst = out / f"{SCENE}_{k}.webp"
        im.save(dst, "WEBP", quality=85, method=6)
        print(f"{dst.relative_to(ROOT)}  {im.size}  {dst.stat().st_size / 1e3:.0f} KB")


if bpy is None:
    if STAGE == "textures":
        stage_textures()
    elif STAGE == "pack-backdrops":
        stage_pack_backdrops()
    else:
        print("without Blender only --stage textures and --stage pack-backdrops run")
    sys.exit(0)


# ================================================================ Blender from here on
def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


IMG_CACHE = {}
MATS = {}


def image(fn, srgb=True):
    key = (fn, srgb)
    if key not in IMG_CACHE:
        im = bpy.data.images.load(str(TEX / fn))
        im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
        IMG_CACHE[key] = im
    return IMG_CACHE[key]


def material(name, color=(0.5, 0.5, 0.5), rough=0.9, diff=None, tint=None, emit=None, alpha_clip=False, double=False):
    """A Principled material. `tint` multiplies the diffuse texture by a constant colour (a Mix node set to Multiply), which the glTF exporter writes as
    baseColorFactor. `alpha_clip` takes the texture's alpha through Math > Round (glTF alphaMode MASK, cutoff 0.5)."""
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
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    if diff:
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
        if alpha_clip:
            rnd = nt.nodes.new("ShaderNodeMath")
            rnd.operation = "ROUND"
            rnd.name = "ALPHA_ROUND"
            nt.links.new(n.outputs["Alpha"], rnd.inputs[0])
            nt.links.new(rnd.outputs[0], bsdf.inputs["Alpha"])
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    m.use_backface_culling = not double
    MATS[name] = m
    return m


def make_materials():
    material("Ground_Grass", diff="grass.jpg", rough=0.95)
    material("Path_Sand", diff="path.png", rough=0.95, alpha_clip=True)
    for v in VARIANTS:
        t = lin_hex(BARK_HEX[v]) * ALB / 0.80                           # bark.jpg's mean is about 0.8
        material(f"Bark_{v}", diff="bark.jpg", tint=tuple(float(c) for c in t), rough=0.85)
        material(f"Crown_{v}", diff="crowns.jpg", rough=0.8)
    material("Decor_Bloom", diff="decor.png", rough=0.7, double=True)
    # stand-ins (the stills and the layout check only, never baked or exported)
    material("Standin_Post", color=tuple(lin_hex(0xe8d8c8)), rough=0.8)
    material("Standin_Footprint", color=tuple(lin_hex(0xd8c4b0)), rough=0.8)


# ---------------------------------------------------------------- geometry (the trees: build_forest.py's, unchanged)
def ring_tube(bm, pts, radii, seg, mat, tile_v=1.5, wobble=None):
    """A tube through Blender points `pts` with `radii`, `seg` sides, quads only (no caps), smooth, with a bark UV (u round it, v along it / tile_v)."""
    lay = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    rings, vs_along = [], [0.0]
    for j in range(1, len(pts)):
        vs_along.append(vs_along[-1] + (pts[j] - pts[j - 1]).length)
    for j, (p, r) in enumerate(zip(pts, radii)):
        d = (pts[min(j + 1, len(pts) - 1)] - pts[max(j - 1, 0)]).normalized()
        q = d.to_track_quat("Z", "Y")
        ring = []
        for k in range(seg):
            a = 2 * math.pi * k / seg
            rr = r * (wobble(j, k) if wobble else 1.0)
            ring.append(bm.verts.new(p + q @ Vector((math.cos(a) * rr, math.sin(a) * rr, 0))))
        rings.append(ring)
    for j in range(len(rings) - 1):
        for k in range(seg):
            k1 = (k + 1) % seg
            f = bm.faces.new((rings[j][k], rings[j][k1], rings[j + 1][k1], rings[j + 1][k]))
            f.material_index = mat
            f.smooth = True
            u0, u1 = k / seg, (k + 1) / seg
            for lp, uvv in zip(f.loops, ((u0, vs_along[j] / tile_v), (u1, vs_along[j] / tile_v), (u1, vs_along[j + 1] / tile_v), (u0, vs_along[j + 1] / tile_v))):
                lp[lay].uv = uvv
    return rings


R0 = 0.31                                 # every variant's trunk base radius in its mesh: an instance's x/y scale is the layout's radius / R0
FLARE = 1.08                              # the root flare (to y 0.4) at most: r x 1.08 stays within the collider + 5 cm
CROWN_MIN = 2.6                           # nothing of a crown below this in the mesh: with heights scaled 0.9 .. 1.12, every crown starts above 2.34 m
H_SCALE = (0.9, 1.12)


def trunk(bm, top, seed):
    rings = [(-0.2, FLARE), (0.0, FLARE), (0.16, 1.04), (0.4, 1.0), (1.0, 0.965), (1.8, 0.93), (2.6, 0.88), (3.6, 0.80), (4.6, 0.70)]
    rings = [r for r in rings if r[0] < top - 0.6] + [(top, 0.55)]
    pts = [Vector((0, 0, y)) for y, _ in rings]
    radii = [R0 * f for _, f in rings]

    def wob(j, k):                                                        # bark bumps, inward only (the trunk never leaves its collider)
        return 1.0 - 0.035 * abs(noise.noise(Vector((k * 0.9, j * 0.7, seed))))
    ring_tube(bm, pts, radii, 12, 0, tile_v=1.5, wobble=wob)


def branch(bm, p0, p1, r0, r1):
    pts = [p0, p0.lerp(p1, 0.5) + Vector((0, 0, 0.12)), p1]
    ring_tube(bm, pts, [r0, (r0 + r1) / 2, r1], 6, 0, tile_v=1.5)


def crown_uv(bm, faces, centre, cell, lay):
    cu, cv = (cell % 4) * CELL, (cell // 4) * CELL
    S = 4 * CELL
    for f in faces:
        us, vs = [], []
        for lp in f.loops:
            d = (lp.vert.co - centre)
            n = d.normalized() if d.length > 1e-9 else Vector((0, 0, 1))
            us.append(math.atan2(n.y, n.x) / (2 * math.pi) + 0.5)
            vs.append(0.5 + 0.5 * max(-1.0, min(1.0, n.z)))
        if max(us) - min(us) > 0.5:
            us = [u + 1.0 if u < 0.5 else u for u in us]
        for lp, u, v in zip(f.loops, us, vs):
            lp[lay].uv = ((cu + INSET + u * PERIOD) / S, (cv + INSET + v * (CELL - 2 * INSET)) / S)


def puff(bm, c, r, sub, sq, seed, lump, cell):
    lay = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    ret = bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=1.0, matrix=Matrix.Identity(4))
    vs = ret["verts"]
    off = Vector((seed * 7.13, seed * 3.71, seed * 5.27))
    for v in vs:
        d = v.co.normalized()
        k = 1 + lump * noise.noise(d * 1.7 + off) + 0.45 * lump * noise.noise(d * 4.1 + off * 1.7)
        zf = sq if d.z >= 0 else sq * 0.75
        v.co = Vector((c.x + d.x * r * k, c.y + d.y * r * k, c.z + d.z * r * k * zf))
    faces = list({f for v in vs for f in v.link_faces})
    for f in faces:
        f.material_index = 1
        f.smooth = True
    crown_uv(bm, faces, c, cell, lay)


def polar(rad, az_deg, z):
    a = math.radians(az_deg)
    return Vector((rad * math.cos(a), rad * math.sin(a), z))


def build_variant(v):
    """(trunk bmesh, crown bmesh) of variant v, in its own space: z up, the trunk's base at the origin (build_forest.py's, same seeds)."""
    rng = rng_for("variant", v)
    cells = VARIANT_CELLS[v]
    pick = lambda: int(cells[rng.integers(len(cells))])
    tb, cb = bmesh.new(), bmesh.new()
    if v == "A":
        top = 6.3
        trunk(tb, top, 1.0)
        for i, (h, az) in enumerate(((3.0, 10), (3.6, 150), (4.2, 260), (4.8, 80), (5.3, 210))):
            p0 = Vector((0, 0, h))
            branch(cb, p0, polar(1.55, az, h + 1.35), 0.11, 0.045)
        puff(cb, Vector((0, 0, 7.45)), 1.75, 4, 0.86, 11, 0.16, pick())
        for k in range(5):
            puff(cb, polar(1.7, 72 * k + 18, 6.05 + 0.3 * math.sin(k * 2.1)), 1.35, 4, 0.80, 20 + k, 0.17, pick())
        for k in range(3):
            puff(cb, polar(1.8, 120 * k + 55, 4.75), 1.05, 3, 0.80, 40 + k, 0.17, pick())
    elif v == "B":
        top = 8.3
        trunk(tb, top, 2.0)
        tiers = ((3.75, 1.75, 0.55), (5.1, 1.45, 0.58), (6.35, 1.15, 0.62), (7.45, 0.85, 0.70), (8.4, 0.55, 0.85))
        for t, (z, r, sq) in enumerate(tiers):
            puff(cb, Vector((0, 0, z)), r, 4 if r > 1.0 else 3, sq, 60 + t, 0.13, pick())
            if t < 4:
                for k in range(3):
                    puff(cb, polar(r * 0.62, 120 * k + 40 * t, z - 0.05), r * 0.46, 3, 0.75, 70 + 3 * t + k, 0.16, pick())
        for i, az in enumerate((30, 150, 270)):
            branch(cb, Vector((0, 0, 3.05)), polar(1.0, az, 3.55), 0.09, 0.04)
    else:
        top = 5.0
        trunk(tb, top, 3.0)
        for i, az in enumerate((20, 140, 260)):
            branch(cb, Vector((0, 0, 3.35)), polar(1.55, az, 5.25), 0.12, 0.05)
        puff(cb, Vector((0, 0, 6.0)), 1.7, 4, 0.56, 90, 0.14, pick())
        for k in range(6):
            puff(cb, polar(1.85, 60 * k + 15, 5.6 + 0.12 * math.cos(k * 1.7)), 1.05, 4, 0.62, 91 + k, 0.16, pick())
        for k in range(3):
            puff(cb, polar(0.85, 120 * k + 75, 6.6), 0.9, 3, 0.75, 99 + k, 0.15, pick())
    zmin = min(vv.co.z for vv in cb.verts)
    assert zmin >= CROWN_MIN, (v, zmin)
    return tb, cb


def bm_to_mesh(bm, name, mats):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    for m in mats:
        me.materials.append(m)
    return me


# ---------------------------------------------------------------- the ground and the path
def ground_h(x, z):
    """The ground's height: flat on and beside the path and round the shed and the house, a gentle roll (a few cm) in the field, a little more past
    the edge walls."""
    d = abs(x) if z >= PATH_Z1 - 2 else math.hypot(x, z - PATH_Z1)
    d = min(d, math.hypot(max(0.0, abs(z - SPUR_Z) - SPUR_W / 2), max(0.0, x - SPUR_X0, SPUR_X1 - x)) + 2.0)
    for b in (SHED, HOUSE):
        d = min(d, max(0.0, math.hypot(x - b["at"][0], z - b["at"][1]) - 6.0))
    inside = -HX <= x <= HX and PZ0 <= z <= PZ1
    amp = (0.04 if inside else 0.12) * min(1.0, max(0.0, (d - 4.0) / 3.0))
    return amp * noise.noise(Vector((x * 0.13, z * 0.13, 0.7)))


def build_ground():
    """The ground: a 2 m grid over EXT with a skirt down to y -1 round its edge (the collider Ground_Meadow is a metre deep), UV0 planar / 3 m."""
    bm = bmesh.new()
    lay = bm.loops.layers.uv.new("UVMap")
    x0, x1, z0, z1 = EXT
    xs = np.arange(x0, x1 + 1e-6, 2.0)
    zs = np.arange(z0, z1 + 1e-6, 2.0)
    V = [[bm.verts.new(B((float(x), ground_h(float(x), float(z)), float(z)))) for x in xs] for z in zs]
    T = 3.0
    for j in range(len(zs) - 1):
        for i in range(len(xs) - 1):
            f = bm.faces.new((V[j][i], V[j][i + 1], V[j + 1][i + 1], V[j + 1][i]))
            f.normal_update()
            if f.normal.z < 0:
                f.normal_flip()
            for lp in f.loops:
                lp[lay].uv = (lp.vert.co.x / T, lp.vert.co.y / T)
    edge = [V[0][i] for i in range(len(xs))] + [V[j][-1] for j in range(1, len(zs))] + [V[-1][i] for i in range(len(xs) - 2, -1, -1)] + \
           [V[j][0] for j in range(len(zs) - 2, 0, -1)]
    low = [bm.verts.new((v.co.x, v.co.y, -1.0)) for v in edge]
    cx, cy = (x0 + x1) / 2, -(z0 + z1) / 2
    for k in range(len(edge)):
        k1 = (k + 1) % len(edge)
        f = bm.faces.new((edge[k], edge[k1], low[k1], low[k]))
        f.normal_update()
        mid = f.calc_center_median()
        if f.normal.dot(Vector((mid.x - cx, mid.y - cy, 0))) < 0:
            f.normal_flip()
        for lp in f.loops:
            lp[lay].uv = ((lp.vert.co.x + lp.vert.co.y) / T, lp.vert.co.z / T)
    for f in bm.faces:
        f.smooth = True
    return bm_to_mesh(bm, "Ground", [MATS["Ground_Grass"]])


def ribbon(bm, lay, pts, widths, y):
    """A ribbon along game points `pts` [(x, z)], `widths` across, at height y; u along it (one repeat per PATH_W), v across it (0 .. 1)."""
    rows, s = [], 0.0
    for i, (x, z) in enumerate(pts):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tx, tz = b[0] - a[0], b[1] - a[1]
        n = math.hypot(tx, tz)
        nx, nz = -tz / n, tx / n
        if i:
            s += math.hypot(x - pts[i - 1][0], z - pts[i - 1][1])
        w = widths[i]
        left = bm.verts.new(B((x - nx * w / 2, y, z - nz * w / 2)))
        right = bm.verts.new(B((x + nx * w / 2, y, z + nz * w / 2)))
        rows.append((left, right, s / PATH_W))
    for i in range(len(rows) - 1):
        (l0, r0, u0), (l1, r1, u1) = rows[i], rows[i + 1]
        f = bm.faces.new((l0, r0, r1, l1))
        uvs = {l0: (u0, 0.0), r0: (u0, 1.0), r1: (u1, 1.0), l1: (u1, 0.0)}
        f.normal_update()
        if f.normal.z < 0:
            f.normal_flip()
        for lp in f.loops:
            lp[lay].uv = uvs[lp.vert]


def build_path():
    """The path: a ribbon at y 0.025 straight north on x = 0 from the art's south end (where it meets the forest's 7 m path) to under the house's
    front, and a spur west at the shed's door, a centimetre higher so the two do not fight."""
    bm = bmesh.new()
    lay = bm.loops.layers.uv.new("UVMap")
    zs = np.arange(PATH_Z0, PATH_Z1 - 1e-6, -1.0)
    zs = np.append(zs, PATH_Z1) if zs[-1] > PATH_Z1 + 1e-6 else zs
    ribbon(bm, lay, [(0.0, float(z)) for z in zs], [path_w(float(z)) for z in zs], 0.025)
    xs = np.arange(SPUR_X0, SPUR_X1 - 1e-6, -1.0)
    xs = np.append(xs, SPUR_X1)
    ribbon(bm, lay, [(float(x), SPUR_Z) for x in xs], [SPUR_W] * len(xs), 0.03)
    return bm_to_mesh(bm, "Path", [MATS["Path_Sand"]])


# ---- the small things (instanced, passable, not baked)
def cell_uv(cell, fu=0.5, fv=0.5):
    return ((cell * 64 + 6 + fu * 52) / 512, (6 + fv * 52) / 64)


def blade(bm, lay, base, a, h, lean, w, cell, segs=3):
    """One grass blade: a tapering strip from `base` bending out along azimuth a, `segs` segments, v from the atlas cell's dark base to its light tip."""
    out = Vector((math.cos(a), math.sin(a), 0))
    side = Vector((-math.sin(a), math.cos(a), 0))
    prev = None
    for s in range(segs + 1):
        t = s / segs
        c = base + out * (lean * h * t * t) + Vector((0, 0, h * t * (1 - 0.18 * lean * t)))
        if s == segs:
            tip = bm.verts.new(c)
            f = bm.faces.new((prev[0], prev[1], tip))
            f.smooth = True
            for lp in f.loops:
                lp[lay].uv = cell_uv(cell, 0.5, 0.02 + 0.96 * (prev[2] if lp.vert in prev[:2] else 1.0))
            return tip
        ww = w * (1 - 0.8 * t)
        pair = (bm.verts.new(c - side * ww), bm.verts.new(c + side * ww), t)
        if prev:
            f = bm.faces.new((prev[0], prev[1], pair[1], pair[0]))
            f.smooth = True
            for lp in f.loops:
                lp[lay].uv = cell_uv(cell, 0.5, 0.02 + 0.96 * (prev[2] if lp.vert in prev[:2] else t))
        prev = pair


GRASS_KINDS = {                     # name: (blades, height range, lean range, width range, seed stalks, clump radius)
    "Grass_Tall": (24, (0.40, 0.80), (0.18, 0.45), (0.018, 0.028), 0, 0.30),
    "Grass_Mid": (22, (0.22, 0.46), (0.25, 0.55), (0.020, 0.030), 0, 0.34),
    "Grass_Seed": (14, (0.30, 0.55), (0.2, 0.45), (0.016, 0.024), 5, 0.24),
}


def grass_mesh(kind):
    """A clump of tall meadow grass: blades in the forest's blade green, and (Grass_Seed) a few taller stalks in sage to straw with a seed head."""
    n, hr, lr, wr, stalks, rad = GRASS_KINDS[kind]
    bm = bmesh.new()
    lay = bm.loops.layers.uv.new("UVMap")
    rng = rng_for("grass", kind)
    for k in range(n):
        a = 2 * math.pi * k / n + rng.uniform(-0.3, 0.3)
        rr = rad * math.sqrt(rng.uniform(0.02, 1.0))
        base = Vector((math.cos(a) * rr, math.sin(a) * rr, -0.02))
        blade(bm, lay, base, a + rng.uniform(-0.4, 0.4), rng.uniform(*hr), rng.uniform(*lr), rng.uniform(*wr), 5 if rng.random() < 0.8 else 7)
    for k in range(stalks):
        a = rng.uniform(0, 2 * math.pi)
        base = Vector((math.cos(a) * 0.03, math.sin(a) * 0.03, -0.02))
        tipv = blade(bm, lay, base, a, rng.uniform(0.7, 0.95), rng.uniform(0.05, 0.15), 0.008, 7, segs=3)
        # a seed head: a slim spindle at the stalk's top
        ret = bmesh.ops.create_uvsphere(bm, u_segments=5, v_segments=3, radius=1.0, matrix=Matrix.Identity(4))
        for v in ret["verts"]:
            v.co = tipv.co + Vector((v.co.x * 0.018, v.co.y * 0.018, v.co.z * 0.07 - 0.04))
        for f in {f for v in ret["verts"] for f in v.link_faces}:
            f.smooth = True
            for lp in f.loops:
                lp[lay].uv = cell_uv(7, 0.5, 0.92)
    return bm_to_mesh(bm, kind, [MATS["Decor_Bloom"]])


def flower_mesh(c):
    """One of the layout's flowers: a clump of six blooms of colour c (the page's FLOWER_COLORS[c]), each a stem, a leaf and a six-petal head
    with a butter centre, 0.34 to 0.60 m tall with heads 16 to 24 cm across, so they stand over the mid grass. Centred on the flower's spot."""
    bm = bmesh.new()
    lay = bm.loops.layers.uv.new("UVMap")
    rng = rng_for("flower", c)
    for k in range(6):
        a = 2 * math.pi * k / 6 + rng.uniform(-0.5, 0.5)
        rr = 0.0 if k == 0 else rng.uniform(0.1, 0.28)
        base = Vector((math.cos(a) * rr, math.sin(a) * rr, -0.02))
        h = rng.uniform(0.34, 0.60)
        top = base + Vector((rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05), h))
        # the stem: a thin three-sided tube
        rings = ring_tube(bm, [base, base.lerp(top, 0.5) + Vector((0.01, 0, 0)), top], [0.007, 0.006, 0.005], 3, 0)
        for f in {f for r in rings for v in r for f in v.link_faces}:
            for lp in f.loops:
                lp[lay].uv = cell_uv(5, 0.5, 0.2 + 0.6 * min(1.0, max(0.0, (lp.vert.co.z - base.z) / h)))
        # a leaf
        blade(bm, lay, base + Vector((0, 0, 0.02)), a + 1.3, h * 0.45, 0.7, 0.022, 5, segs=2)
        # the head: six petals round a butter centre, tilted a little
        tilt = Vector((rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25), 1)).normalized()
        q = tilt.to_track_quat("Z", "Y")
        pr = rng.uniform(0.08, 0.12)
        ctr = bm.verts.new(top + q @ Vector((0, 0, 0.012)))
        rim = []
        for p in range(12):
            ang = 2 * math.pi * p / 12
            rad = pr if p % 2 == 0 else pr * 0.42
            rim.append(bm.verts.new(top + q @ Vector((math.cos(ang) * rad, math.sin(ang) * rad, 0.006 * (p % 2)))))
        for p in range(12):
            f = bm.faces.new((ctr, rim[p], rim[(p + 1) % 12]))
            f.smooth = True
            for lp in f.loops:
                lp[lay].uv = cell_uv(6) if lp.vert is ctr else cell_uv(c, 0.5, 0.85 if p % 2 == 0 and lp.vert is rim[p] else 0.4)
        # its back, so the head reads from below and behind too
        back = bm.verts.new(top - q @ Vector((0, 0, 0.01)))
        for p in range(12):
            f = bm.faces.new((back, rim[(p + 1) % 12], rim[p]))
            f.smooth = True
            for lp in f.loops:
                lp[lay].uv = cell_uv(5, 0.5, 0.6) if lp.vert is back else cell_uv(c, 0.5, 0.4)
    return bm_to_mesh(bm, f"Flower_{c}", [MATS["Decor_Bloom"]])


# ---------------------------------------------------------------- placements (fixed seeds; written to the work folder for the GLB check)
def tree_placements():
    """Each layout tree: its variant, yaw and height scale."""
    rng = np.random.default_rng(K["seed"])
    out = []
    for i, (x, z, r) in enumerate(TREES):
        v = VARIANTS[int(rng.choice(3, p=VARIANT_P))]
        out.append({"i": i, "v": v, "x": x, "z": z, "r": r, "yaw": float(rng.uniform(0, 2 * math.pi)), "hs": float(rng.uniform(*H_SCALE))})
    return out


def ring_placements():
    """Trees past the edge walls, out of reach: to the south the forest (dense, the forest's spacing and mix, open where the path goes in), round the
    other three sides a looser band of the meadow's trees, thinning outward."""
    rng = np.random.default_rng(78)
    pts = []
    tries = 0
    while tries < 50000:
        tries += 1
        x, z = rng.uniform(EXT[0] + 1.5, EXT[1] - 1.5), rng.uniform(EXT[2] + 1.5, EXT[3] - 1.5)
        if -HX - 1.6 < x < HX + 1.6 and PZ0 - 1.6 < z < PZ1 + 1.6:
            continue
        south = z > PZ1
        if south and abs(x) < 4.6 + (z - PZ1) * 0.08:
            continue
        gap = 2.9 if south else 3.6
        if not south:
            out = max(-HX - x, x - HX, PZ0 - z)                          # metres past the edge wall
            if rng.random() < out / 26.0:
                continue
        if any((x - a) ** 2 + (z - b) ** 2 < gap ** 2 for a, b, *_ in pts):
            continue
        p = (0.4, 0.3, 0.3) if south else VARIANT_P
        pts.append((x, z, float(rng.uniform(0.25, 0.42)), VARIANTS[int(rng.choice(3, p=p))], float(rng.uniform(0, 2 * math.pi)), float(rng.uniform(*H_SCALE))))
    return [{"x": round(x, 3), "z": round(z, 3), "r": r, "v": v, "yaw": yaw, "hs": hs} for x, z, r, v, yaw, hs in pts]


def keep_points():
    """The spots the small things keep off (game x, z, radius): the arrival, the house's return spot, the two doors."""
    a, rh = K["arrive"], K["returnHouse"]["arrive"]
    return [(a[0], a[2], 1.2), (rh[0], rh[2], 1.2), (*SHED["door"]["at"], 1.4), (*HOUSE["door"]["at"], 1.6)]


def in_building(x, z, pad):
    return any(abs(x - b["at"][0]) < b["half"][0] + pad and abs(z - b["at"][1]) < b["half"][1] + pad for b in (SHED, HOUSE))


def decor_placements(trees, ring):
    """The tall grass: clumps over the whole ground, thicker toward the trees and in drifts, thinner by the path (kept off its sand), off the trunks,
    the buildings, the doors and the arrival."""
    rng = np.random.default_rng(2027)
    kd = kdtree.KDTree(len(trees) + len(ring))
    allt = [(t["x"], t["z"], t["r"]) for t in trees] + [(t["x"], t["z"], t["r"]) for t in ring]
    for k, (x, z, r) in enumerate(allt):
        kd.insert((x, z, 0), k)
    kd.balance()
    keep = keep_points()

    def ok(x, z, keep_r=0.12):
        if not (EXT[0] + 1 < x < EXT[1] - 1 and EXT[2] + 1 < z < EXT[3] - 1):
            return False
        if on_path(x, z, 0.35) or in_building(x, z, 0.4):
            return False
        if any(math.hypot(x - px, z - pz) < pr for px, pz, pr in keep):
            return False
        (px, pz, _), k, d = kd.find((x, z, 0))
        return d > allt[k][2] + keep_r

    out = {k: [] for k in GRASS_KINDS}
    want = {"Grass_Tall": 3000, "Grass_Mid": 4000, "Grass_Seed": 1000}
    for kind, n in want.items():
        tries = 0
        while len(out[kind]) < n and tries < 200000:
            tries += 1
            x, z = rng.uniform(EXT[0], EXT[1]), rng.uniform(EXT[2], EXT[3])
            dens = 0.55 + 0.45 * noise.noise(Vector((x * 0.06, z * 0.06, 5.1 + len(kind))))
            near_path = min(abs(x), 99.0) if z > PATH_Z1 else 99.0
            if near_path < 5.0:
                dens *= 0.35 + 0.65 * near_path / 5.0
            if kind == "Grass_Tall" and abs(x) < 3.2 and z > PATH_Z1:
                continue                                                     # the tall clumps keep a little back from the path
            if rng.random() > dens:
                continue
            if ok(x, z):
                out[kind].append((x, z, float(rng.uniform(0, 2 * math.pi)), float(rng.uniform(0.8, 1.3))))
    return out


def flower_placements():
    """The layout's 420 flowers, each on its spot, with a turn and a size of its own."""
    rng = np.random.default_rng(K["flowerSeed"])
    return [{"i": i, "x": x, "z": z, "c": int(c), "yaw": float(rng.uniform(0, 2 * math.pi)), "s": float(rng.uniform(0.85, 1.2))} for i, (x, z, c) in enumerate(FLOWERS)]


# ---------------------------------------------------------------- collections and objects
ART = EXPORT = STANDIN = PAGE = None


def place(name, me, coll, x, z, yaw, sxy, sz, y=0.0, parent=None):
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if parent is not None:
        ob.parent = parent
    ob.location = B((x, y, z))
    ob.rotation_euler = (0.0, 0.0, yaw)
    ob.scale = (sxy, sxy, sz)
    return ob


def build_pagedrawn():
    """The page's buildings for the layout check: the colliders `Shed` and `House` stand where the page draws the owner's models, so `PageDrawn`
    (read by the check with the art, never baked, rendered or exported) holds each footprint as the collider's box. The models themselves are
    imported as stand-ins by the stages that bake and render (owner_models())."""
    for name in ("Shed", "House"):
        c = COLL[name][0]
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        mn, mx = B(c["min"]), B(c["max"])
        lo = Vector((min(mn.x, mx.x), min(mn.y, mx.y), min(mn.z, mx.z)))
        hi = Vector((max(mn.x, mx.x), max(mn.y, mx.y), max(mn.z, mx.z)))
        for v in bm.verts:
            v.co = lo + Vector(((v.co.x + 0.5) * (hi.x - lo.x), (v.co.y + 0.5) * (hi.y - lo.y), (v.co.z + 0.5) * (hi.z - lo.z)))
        me = bm_to_mesh(bm, f"pagedrawn_{name.lower()}_footprint", [MATS["Standin_Footprint"]])
        PAGE.objects.link(bpy.data.objects.new(f"pagedrawn_{name.lower()}_footprint", me))


def build_all():
    global ART, EXPORT, STANDIN, PAGE
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.lights, bpy.data.cameras):
        for d in list(coll):
            coll.remove(d)
    IMG_CACHE.clear()
    MATS.clear()
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    check = bpy.data.collections.new("LayoutCheck")         # what the layout check reads: the art and the page's building footprints
    ART = bpy.data.collections.new("Art")
    PAGE = bpy.data.collections.new("PageDrawn")
    EXPORT = bpy.data.collections.new("Export")
    STANDIN = bpy.data.collections.new("Standins")
    sc.collection.children.link(check)
    check.children.link(ART)
    check.children.link(PAGE)
    sc.collection.children.link(EXPORT)
    sc.collection.children.link(STANDIN)
    make_materials()

    ground = build_ground()
    path = build_path()
    ART.objects.link(bpy.data.objects.new("Ground_art", ground))
    ART.objects.link(bpy.data.objects.new("Path_art", path))
    EXPORT.objects.link(bpy.data.objects.new("Ground", ground))
    EXPORT.objects.link(bpy.data.objects.new("Path", path))

    meshes = {}
    for v in VARIANTS:
        tb, cb = build_variant(v)
        both = bmesh.new()
        tmp = bm_to_mesh(tb, "tmp_t", [])
        both.from_mesh(tmp)
        tmp2 = bm_to_mesh(cb, "tmp_c", [])
        both.from_mesh(tmp2)
        mats = [MATS[f"Bark_{v}"], MATS[f"Crown_{v}"]]
        meshes[v] = {"trunk": bm_to_mesh(tb, f"Tree{v}_trunk", mats), "crown": bm_to_mesh(cb, f"Tree{v}_crown", mats), "tree": bm_to_mesh(both, f"Tree{v}", mats)}
        for d in (tmp, tmp2):
            bpy.data.meshes.remove(d)
        tb.free()
        cb.free()
        both.free()
        me = meshes[v]["tree"]
        print(f"VARIANT {v}: {sum(len(p.vertices) - 2 for p in me.polygons)} triangles, {len(me.vertices)} vertices")

    trees = tree_placements()
    ring = ring_placements()
    holders = {}
    for v in VARIANTS:
        e = bpy.data.objects.new(f"Trees_{v}", None)
        EXPORT.objects.link(e)
        holders[v] = e
    for t in trees:
        s = t["r"] / R0
        # the trunk is round (a 12-gon), so in Art it is not turned: the layout check reads each object's box, and a turned box would grow by up to 41 %
        place(f"Tree_{t['v']}_{t['i']:03d}_trunk", meshes[t["v"]]["trunk"], ART, t["x"], t["z"], 0.0, s, t["hs"])
        place(f"Tree_{t['v']}_{t['i']:03d}_crown", meshes[t["v"]]["crown"], ART, t["x"], t["z"], t["yaw"], s, t["hs"])
        place(f"Tree{t['v']}.{t['i']:03d}", meshes[t["v"]]["tree"], EXPORT, t["x"], t["z"], t["yaw"], s, t["hs"], parent=holders[t["v"]])
    for j, t in enumerate(ring):
        s = t["r"] / R0
        place(f"decor_ring_{t['v']}_{j:03d}", meshes[t["v"]]["tree"], ART, t["x"], t["z"], t["yaw"], s, t["hs"])
        place(f"Tree{t['v']}.r{j:03d}", meshes[t["v"]]["tree"], EXPORT, t["x"], t["z"], t["yaw"], s, t["hs"], parent=holders[t["v"]])

    fls = flower_placements()
    for c in range(5):
        me = flower_mesh(c)
        e = bpy.data.objects.new(f"Flowers_{c}", None)
        EXPORT.objects.link(e)
        for f in (f for f in fls if f["c"] == c):
            place(f"Flower{c}.{f['i']:03d}", me, EXPORT, f["x"], f["z"], f["yaw"], f["s"], f["s"], parent=e)
    dec = decor_placements(trees, ring)
    for kind in GRASS_KINDS:
        me = grass_mesh(kind)
        print(f"DECOR {kind}: {sum(len(p.vertices) - 2 for p in me.polygons)} triangles x {len(dec[kind])}")
        e = bpy.data.objects.new(kind, None)
        EXPORT.objects.link(e)
        for k, (x, z, yaw, s) in enumerate(dec[kind]):
            place(f"{kind}.{k:04d}", me, EXPORT, x, z, yaw, s, s * (0.9 + 0.2 * ((k * 7919) % 101) / 100), parent=e)
    build_pagedrawn()
    setup_world()
    rep = {"trees": trees, "ring": ring, "flowers": fls, "decor": {k: len(v) for k, v in dec.items()}, "R0": R0}
    (stage_work() / "instances.json").write_text(json.dumps(rep))
    print(f"ART {len(ART.objects)} objects; trees {len(trees)} ({', '.join(f'{v} {sum(t['v'] == v for t in trees)}' for v in VARIANTS)}), ring {len(ring)}, "
          f"flowers {len(fls)} ({', '.join(str(sum(f['c'] == c for f in fls)) for c in range(5))}), grass {rep['decor']}")


# ---------------------------------------------------------------- the owner's models, as stand-ins (never exported, never saved in the .blend)
OWNER = (("shed", "shed.glb", SHED), ("house", "cottage.glb", HOUSE))


def owner_models():
    """Import models/world/shed.glb and cottage.glb into `Standins` and place them as index.html placeBuilding() does: scaled evenly to `height`,
    the box's bottom on the floor and its middle over `at`, turned by `yaw` about the vertical (a three.js turn about y is the same angle about
    Blender's z). Their geometry and materials are not touched. Returns the game-space boxes, for the README."""
    st = bpy.data.collections.get("Standins")
    rep = {}
    for key, fn, b in OWNER:
        if any(o.name.startswith(f"standin_{key}") for o in bpy.data.objects):
            continue
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(ROOT / "models/world" / fn))
        new = [o for o in bpy.data.objects if o not in before]
        for o in new:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            st.objects.link(o)
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ Vector(c) for o in new if o.type == "MESH" for c in o.bound_box]
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        k = b["height"] / (hi.z - lo.z)
        M = Matrix.Translation(B((b["at"][0], 0.0, b["at"][1]))) @ Matrix.Rotation(b["yaw"], 4, "Z") @ Matrix.Scale(k, 4) @ \
            Matrix.Translation(Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z)))
        for o in new:
            if o.parent is None:
                o.matrix_world = M @ o.matrix_world
            o.name = f"standin_{key}_{o.name}"
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ Vector(c) for o in new if o.type == "MESH" for c in o.bound_box]
        g = [(p.x, p.z, -p.y) for p in pts]
        box = {"min": [round(min(q[i] for q in g), 3) for i in range(3)], "max": [round(max(q[i] for q in g), 3) for i in range(3)]}
        c = COLL[key.capitalize()][0]
        rep[key] = {"file": f"models/world/{fn}", "scale": round(k, 4), "box": box, "collider": {"min": c["min"], "max": c["max"]},
                    "triangles": sum(len(p.vertices) - 2 for o in new if o.type == "MESH" for p in o.data.polygons)}
        print(f"OWNER {key}: {fn} scale {k:.4f}, box {box}, collider {c['min']} .. {c['max']}")
    if rep:
        (stage_work() / "owner_models.json").write_text(json.dumps(rep, indent=1))
    return rep


def drop_owner_models():
    gone = [o for o in bpy.data.objects if o.name.startswith(("standin_shed", "standin_house"))]
    for o in gone:
        bpy.data.objects.remove(o)
    if gone:
        try:
            bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
        except Exception as e:
            print("  orphans_purge:", e)


def ensure_marker():
    ob = bpy.data.objects.get("standin_arrival_marker")
    if ob is None:
        bm = bmesh.new()
        a = K["arrive"]
        bmesh.ops.create_cube(bm, size=0.2)
        for v in bm.verts:
            v.co = B((a[0], a[1] + 0.1, a[2])) + v.co
        me = bm_to_mesh(bm, "standin_arrival_marker", [MATS.get("Standin_Post") or bpy.data.materials["Standin_Post"]])
        ob = bpy.data.objects.new("standin_arrival_marker", me)
        bpy.data.collections["Standins"].objects.link(ob)
    ob.hide_render = True
    return ob


def stage_axes():
    import struct
    ob = ensure_marker()
    bpy.ops.object.select_all(action="DESELECT")
    ob.hide_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    path = stage_work() / "axes_marker.glb"
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_yup=True, export_apply=True, export_materials="NONE")
    b = path.read_bytes()
    j = json.loads(b[20:20 + struct.unpack("<I", b[12:16])[0]])
    acc = j["accessors"][j["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    off = j["nodes"][0].get("translation", [0, 0, 0])
    centre = [(acc["min"][i] + acc["max"][i]) / 2 + off[i] for i in range(3)]
    a = K["arrive"]
    want = [a[0], a[1] + 0.1, a[2]]
    bl = sum((v.co for v in ob.data.vertices), Vector()) / len(ob.data.vertices)
    print(f"AXES blender centre {tuple(round(v, 3) for v in bl)}, glTF centre {tuple(round(v, 3) for v in centre)}, game point {tuple(want)}")
    assert all(abs(centre[i] - want[i]) < 1e-4 for i in range(3)), "the exporter's axes disagree with (x, -z, y)"
    assert abs(bl.x - want[0]) < 1e-4 and abs(bl.y + want[2]) < 1e-4 and abs(bl.z - want[1]) < 1e-4
    print("AXES PASS: game (x, y, z) = Blender (x, -z, y) = glTF (x, y, z)")


# ---------------------------------------------------------------- the world: the page's hemisphere light for every ray, the backdrop for camera rays
def hemi_nodes(nt, night=False):
    """A Background node lit like the page's HemisphereLight: #fff0f8 above, #f0c8dc below, 1.55 (by night a dim lilac, for the night still)."""
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = -0.4, 0.4
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = (*lin_hex(HEMI_GROUND), 1)
    mix.inputs[7].default_value = (*lin_hex(HEMI_SKY), 1)
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 0.26 if night else HEMI_K
    if night:
        mix.inputs[6].default_value = (0.50, 0.40, 0.60, 1)
        mix.inputs[7].default_value = (0.58, 0.62, 0.98, 1)
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    nt.links.new(mr.outputs[0], mix.inputs[0])
    nt.links.new(mix.outputs[2], bg.inputs["Color"])
    return bg


AO_DIST = 5.0


def setup_world(night=False, backdrop=None, cam_col=None):
    """The page's hemisphere light for every ray; camera rays see the backdrop picture, or the flat colour `cam_col` (the wide still from above)."""
    sc = bpy.context.scene
    w = bpy.data.worlds.get("Meadow") or bpy.data.worlds.new("Meadow")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    hemi = hemi_nodes(nt, night)
    if backdrop and Path(backdrop).exists():
        tc = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Rotation"].default_value = (0, 0, -math.pi / 2)      # turns Blender +Y (north) to where an equirect picture's middle looks (+X)
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(str(backdrop), check_existing=True)
        cam = nt.nodes.new("ShaderNodeBackground")
        cam.inputs["Strength"].default_value = 1.0
        lp = nt.nodes.new("ShaderNodeLightPath")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
        nt.links.new(env.outputs["Color"], cam.inputs["Color"])
        nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
        nt.links.new(hemi.outputs[0], mix.inputs[1])
        nt.links.new(cam.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
    elif cam_col is not None:
        cam = nt.nodes.new("ShaderNodeBackground")
        cam.inputs["Color"].default_value = (*cam_col, 1)
        lp = nt.nodes.new("ShaderNodeLightPath")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
        nt.links.new(hemi.outputs[0], mix.inputs[1])
        nt.links.new(cam.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
    else:
        nt.links.new(hemi.outputs[0], out.inputs["Surface"])
    w.light_settings.distance = AO_DIST
    return w


# ---------------------------------------------------------------- bake (AO only)
TREE_PAGE = 1024
GROUND_PAGE = 2048
TREE_AO_DIST = 2.5
GROUND_AO_DIST = 5.0
AO_INTENSITY = {"ground": 1.0, "tree": 0.9}


def stage_work():
    d = Path(arg("--work", str(Path(os.environ.get("TEMP", "/tmp")) / f"farway_{SCENE}")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup_cycles(samples, bake=False):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = samples
    cy.use_adaptive_sampling = False
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces, cy.transmission_bounces, cy.transparent_max_bounces = 8, 4, 2, 4, 16
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
            devs = [d for d in prefs.devices if d.type != "CPU"]
            if devs:
                for d in prefs.devices:
                    d.use = d.type != "CPU"
                gpu = True
                break
    cy.device = "GPU" if gpu else "CPU"
    print("CYCLES device:", cy.device, [d.name for d in prefs.devices if d.use] if gpu else "CPU")
    return gpu


def select_only(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False)
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
    """UV1 ("lightmap"): smart-project islands at equal texel density, packed with MARGIN_PX on a `page` px square."""
    for o in objs:
        uvs = o.data.uv_layers
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.new(name="lightmap")
        uvs.active = uvs["lightmap"]
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / page, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    a3 = sum(area3d(o) for o in objs)
    au = sum(uv_area(o, "lightmap") for o in objs)
    dens = page * math.sqrt(au / a3)
    print(f"  page {page}: {a3:.1f} m2, {dens:.1f} px/m (mesh units)")
    for o in objs:
        o.data.uv_layers.active = o.data.uv_layers["UVMap"]
        o.data.uv_layers["UVMap"].active_render = True
    return page, dens


def denoise_image(img, S):
    """OIDN through the compositor's Denoise node: the image goes in as a float image and comes back as a float array."""
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
    path = str(stage_work() / "dn.exr")
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=sc.name)
    r = bpy.data.images.load(path)
    a = np.empty(S * S * 4, np.float32)
    r.pixels.foreach_get(a)
    bpy.data.images.remove(r)
    bpy.data.scenes.remove(sc)
    bpy.data.node_groups.remove(ng)
    bpy.data.objects.remove(cam)
    os.remove(path)
    return a.reshape(S, S, 4)


def bake_ao(objs, S, dist, n, mats, intensity):
    import time
    t0 = time.time()
    bpy.context.scene.world.light_settings.distance = dist
    img = bpy.data.images.new(f"AO_{n}", S, S, alpha=False, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    for m in mats:
        nt = m.node_tree
        node = nt.nodes.new("ShaderNodeTexImage")
        node.name = "BAKE_TARGET"
        node.image = img
        nt.nodes.active = node
        node.select = True
    select_only(objs)
    for o in objs:
        o.data.uv_layers.active = o.data.uv_layers["lightmap"]
    bpy.ops.object.bake(type="AO", margin=MARGIN_PX, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
    for o in objs:
        o.data.uv_layers.active = o.data.uv_layers["UVMap"]
    a = denoise_image(img, S)
    ao = np.clip(a[..., :3].mean(axis=2), 0, 1)
    lit = ao[ao > 1e-4]
    pc = np.percentile(lit, [1, 10, 50, 90]) if lit.size else [1.0] * 4
    out = np.ones((S, S, 4), np.float32)
    out[..., 0] = out[..., 1] = out[..., 2] = ao                     # linear AO (the page loads it with NoColorSpace)
    png = bpy.data.images.new(f"AO_{n}_png", S, S, alpha=False)
    png.colorspace_settings.name = "Non-Color"
    png.pixels.foreach_set(out.ravel())
    png.filepath_raw = str(stage_work() / f"{SCENE}_{n}.png")
    png.file_format = "PNG"
    png.save()
    for m in mats:
        m["aomap"] = AO_URL.format(n)
        m["aomap_intensity"] = intensity
        nt = m.node_tree
        for nd in [nd for nd in nt.nodes if nd.name.startswith("BAKE_TARGET")]:
            nt.nodes.remove(nd)
    bpy.data.images.remove(img)
    bpy.data.images.remove(png)
    rep = {"size": S, "p1_p10_p50_p90": [round(float(v), 3) for v in pc], "samples": SAMPLES, "distance_m": dist,
           "device": bpy.context.scene.cycles.device, "seconds": round(time.time() - t0), "materials": [m.name for m in mats]}
    print(f"  AO map {n} baked", rep)
    return rep


def stage_bake():
    stage_work()
    sc = bpy.context.scene
    bpy.data.collections["LayoutCheck"].hide_render = True
    st = bpy.data.collections["Standins"]
    exp = bpy.data.collections["Export"]
    setup_world()
    setup_cycles(SAMPLES, bake=True)
    report = {}
    # 1 .. 3: each variant alone over a ground plane (its own trunk's contact), at the origin
    st.hide_render = True
    tmp = bpy.data.collections.new("BakeTmp")
    sc.collection.children.link(tmp)
    exp.hide_render = True
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=12.0)
    plane = bpy.data.objects.new("bake_plane", bm_to_mesh(bm, "bake_plane", [MATS_get("Ground_Grass")]))
    tmp.objects.link(plane)
    for n, v in enumerate(VARIANTS, start=1):
        me = bpy.data.meshes[f"Tree{v}"]
        ob = bpy.data.objects.new(f"bake_{v}", me)
        tmp.objects.link(ob)
        print(f"AO map {n}: variant {v}")
        S, dens = lightmap_uv([ob], TREE_PAGE)
        report[n] = bake_ao([ob], S, TREE_AO_DIST, n, [MATS_get(f"Bark_{v}"), MATS_get(f"Crown_{v}")], AO_INTENSITY["tree"])
        report[n]["px_per_m"] = round(dens, 1)
        report[n]["variant"] = v
        bpy.data.objects.remove(ob)
    bpy.data.objects.remove(plane)
    bpy.data.meshes.remove(bpy.data.meshes["bake_plane"])
    bpy.data.collections.remove(tmp)
    # 0: the ground, with every tree in place and the owner's shed and house standing where the page draws them (their contact shadow); the path,
    # the flowers and the grass hidden
    exp.hide_render = False
    st.hide_render = False
    owner_models()
    for o in st.objects:
        if not o.name.startswith(("standin_shed", "standin_house")):
            o.hide_render = True
    hidden = [o for o in exp.all_objects if o.name == "Path" or o.name.startswith(("Flower", "Grass_"))]
    for o in hidden:
        o.hide_render = True
    ground = bpy.data.objects["Ground"]
    print("AO map 0: the ground")
    S, dens = lightmap_uv([ground], GROUND_PAGE)
    report[0] = bake_ao([ground], S, GROUND_AO_DIST, 0, [MATS_get("Ground_Grass")], AO_INTENSITY["ground"])
    report[0]["px_per_m"] = round(dens, 1)
    for o in hidden:
        o.hide_render = False
    (stage_work() / "aomaps.json").write_text(json.dumps(report, indent=1))
    bpy.data.collections["LayoutCheck"].hide_render = False
    save_blend()


def MATS_get(name):
    return MATS.get(name) or bpy.data.materials[name]


# ---------------------------------------------------------------- privacy
def scrub_ui_paths():
    for sc in bpy.data.screens:
        for a in sc.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"_" * 1000
                    sp.params.directory = b"//"


KEEP_PROPS = {"aomap", "aomap_intensity"}      # the only custom properties this scene carries (on materials, for the page)
SYS_KEEP = ("cycles", "eevee")


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private():
    """The .blend, the GLB (export_extras) and the stills are public: drop every custom property but the materials' AO extras, make image paths
    relative, blank the render output path and every stamp, and the file browser's remembered folder."""
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
    scrub_ui_paths()


def save_blend():
    """Save blender/scenes/meadow.blend without the owner's models (imported again by each stage that needs them) or the rendered panoramas."""
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    drop_owner_models()
    for im in [im for im in bpy.data.images if im.name.startswith("backdrop_")]:
        bpy.data.images.remove(im)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    scrub_private()
    bpy.ops.wm.save_mainfile()


# ---------------------------------------------------------------- export
def stage_export():
    import struct
    drop_owner_models()
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    bpy.ops.object.select_all(action="DESELECT")
    for o in exp.all_objects:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects["Ground"]
    raw = stage_work() / f"{SCENE}_raw.glb"
    scrub_private()
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=False,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False, export_animations=False,
                              export_gpu_instances=True)
    print("EXPORTED", raw, raw.stat().st_size)
    b = raw.read_bytes()
    j = json.loads(b[20:20 + struct.unpack("<I", b[12:16])[0]])
    inst = {n["name"]: j["accessors"][n["extensions"]["EXT_mesh_gpu_instancing"]["attributes"]["TRANSLATION"]]["count"]
            for n in j["nodes"] if "EXT_mesh_gpu_instancing" in n.get("extensions", {})}
    print("INSTANCED nodes:", inst, "nodes", len(j["nodes"]), "meshes", len(j["meshes"]), "extensions", j.get("extensionsUsed"))
    rep = json.loads((stage_work() / "instances.json").read_text())
    for v in VARIANTS:
        want = sum(t["v"] == v for t in rep["trees"]) + sum(t["v"] == v for t in rep["ring"])
        assert inst.get(f"Trees_{v}") == want, (v, inst.get(f"Trees_{v}"), want)
    for c in range(5):
        assert inst.get(f"Flowers_{c}") == sum(f["c"] == c for f in rep["flowers"]), (c, inst.get(f"Flowers_{c}"))
    assert "EXT_mesh_gpu_instancing" in j.get("extensionsUsed", [])
    assert not any("standin" in (m.get("name") or "") or "shed" in (m.get("name") or "").lower() for m in j["meshes"]), "an owner's model was exported"
    albedo_report()


def albedo_report():
    """The displayed albedo of every exported material (its texture times its colour factor, linear): p90 of the brightest channel, over the opaque
    texels. The page lights these with its hemisphere light (1.55), so they stay at or under about 0.8."""
    rep = {}
    mats = sorted({m for o in bpy.data.collections["Export"].all_objects if o.type == "MESH" for m in o.data.materials}, key=lambda m: m.name)
    for m in mats:
        nt = m.node_tree
        bs = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        base = np.array(bs.inputs["Base Color"].default_value[:3])
        tex = next((n for n in nt.nodes if n.type == "TEX_IMAGE"), None)
        mix = next((n for n in nt.nodes if n.type == "MIX"), None)
        if tex is not None:
            im = tex.image
            w, h = im.size
            a = np.empty(w * h * 4, np.float32)
            im.pixels.foreach_get(a)
            a = a.reshape(-1, 4)
            px = a[:, :3]
            if m.name == "Path_Sand":
                px = px[a[:, 3] >= 0.5]
            if im.colorspace_settings.name == "sRGB":
                px = to_lin(px)
            f = np.array(mix.inputs[7].default_value[:3]) if mix else np.ones(3)
            vals = (px * f).max(axis=1)
        else:
            vals = np.array([base.max()])
        rep[m.name] = round(float(np.percentile(vals, 90)), 3)
    worst = max(rep.values())
    print("ALBEDO p90 (brightest channel, linear):", json.dumps(rep))
    print(f"ALBEDO worst p90 {worst:.3f} ({'PASS' if worst <= 0.8 else 'FAIL'}: at most about 0.8)")
    (stage_work() / "albedo.json").write_text(json.dumps(rep, indent=1))


# ---------------------------------------------------------------- the backdrops (R3): more meadow and groves past the edges, the forest south, the sky
BD_CENTRE = K["cz"]                                   # the panoramas are taken from the middle of the meadow, at eye height
BD_HAZE = {False: (*lin_hex(SKY_HEX),), True: (0.26, 0.22, 0.40)}
BD_HAZE_L = 120.0                                     # the meadow's haze is softer than the forest's (70 m): the fields read further
MOON_DIR = (0.16, 0.34, -1.0)                         # game direction to the moon: north, a little east, 18 degrees up, over the house from the path


def haze_mix(m, night, L, near=15.0, k=1.0):
    """Wrap a material's surface: camera rays see it mixed toward the haze colour by its distance from the camera, 1 - exp(-(d - near) / L), times k."""
    nt = m.node_tree
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    src = out.inputs["Surface"].links[0].from_socket
    cd = nt.nodes.new("ShaderNodeCameraData")
    a = nt.nodes.new("ShaderNodeMath")
    a.operation = "SUBTRACT"
    a.inputs[1].default_value = near
    b = nt.nodes.new("ShaderNodeMath")
    b.operation = "DIVIDE"
    b.inputs[1].default_value = -L
    b.use_clamp = False
    c = nt.nodes.new("ShaderNodeMath")
    c.operation = "EXPONENT"
    d = nt.nodes.new("ShaderNodeMath")
    d.operation = "SUBTRACT"
    d.inputs[0].default_value = 1.0
    d.use_clamp = True
    e = nt.nodes.new("ShaderNodeMath")
    e.operation = "MULTIPLY"
    e.inputs[1].default_value = k
    mx = nt.nodes.new("ShaderNodeMath")
    mx.operation = "MAXIMUM"
    mx.inputs[1].default_value = 0.0
    lp = nt.nodes.new("ShaderNodeLightPath")
    f = nt.nodes.new("ShaderNodeMath")
    f.operation = "MULTIPLY"
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*BD_HAZE[night], 1)
    em.inputs["Strength"].default_value = 1.0
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(cd.outputs["View Distance"], a.inputs[0])
    nt.links.new(a.outputs[0], mx.inputs[0])
    nt.links.new(mx.outputs[0], b.inputs[0])
    nt.links.new(b.outputs[0], c.inputs[0])
    nt.links.new(c.outputs[0], d.inputs[1])
    nt.links.new(d.outputs[0], e.inputs[0])
    nt.links.new(e.outputs[0], f.inputs[0])
    nt.links.new(lp.outputs["Is Camera Ray"], f.inputs[1])
    nt.links.new(f.outputs[0], mix.inputs[0])
    nt.links.new(src, mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return m


def flat_material(name, col, rough=0.9, emit=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bs.inputs["Base Color"].default_value = (*col, 1)
    bs.inputs["Roughness"].default_value = rough
    if emit:
        bs.inputs["Emission Color"].default_value = (*emit[0], 1)
        bs.inputs["Emission Strength"].default_value = emit[1]
    nt.links.new(bs.outputs[0], out.inputs["Surface"])
    return m


def build_backdrop(night):
    """Past the playable meadow, as far as the haze lets one see: a wide lawn; the forest dense to the south (the way back), with the path going in;
    round the other sides open fields with groves of the same trees and a few lone ones, thinning outward; low pastel hills far out on every side
    but the south."""
    old = bpy.data.collections.get("Backdrop")
    if old:
        for o in list(old.objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(old)
    coll = bpy.data.collections.new("Backdrop")
    bpy.context.scene.collection.children.link(coll)
    sfx = "night" if night else "day"
    bdm = {}
    for name in ["Ground_Grass", "Path_Sand"] + [f"Bark_{v}" for v in VARIANTS] + [f"Crown_{v}" for v in VARIANTS]:
        m = MATS_get(name).copy()
        m.name = f"bd_{name}_{sfx}"
        for k in list(m.keys()):
            del m[k]
        bdm[name] = haze_mix(m, night, BD_HAZE_L)
    hill = haze_mix(flat_material(f"bd_hill_{sfx}", (0.46, 0.44, 0.62)), night, 1.0, near=0.0, k=0.62)
    hill2 = haze_mix(flat_material(f"bd_hill2_{sfx}", (0.42, 0.52, 0.46)), night, 1.0, near=0.0, k=0.5)
    # the ground: a 1.6 km square, flat
    bm = bmesh.new()
    lay = bm.loops.layers.uv.new("UVMap")
    R = 800.0
    vs = [bm.verts.new(B((x, -0.03, z))) for x, z in ((-R, BD_CENTRE + R), (R, BD_CENTRE + R), (R, BD_CENTRE - R), (-R, BD_CENTRE - R))]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.z < 0:
        f.normal_flip()
    for lp in f.loops:
        lp[lay].uv = (lp.vert.co.x / 3.0, lp.vert.co.y / 3.0)
    coll.objects.link(bpy.data.objects.new("bd_ground", bm_to_mesh(bm, "bd_ground", [bdm["Ground_Grass"]])))
    # the path into the forest, south
    bm = bmesh.new()
    lay = bm.loops.layers.uv.new("UVMap")
    z0, z1 = EXT[3] - 2, 400.0
    vs = [bm.verts.new(B(p)) for p in ((-3.5, 0.01, z0), (3.5, 0.01, z0), (3.5, 0.01, z1), (-3.5, 0.01, z1))]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.z < 0:
        f.normal_flip()
    for lp, uv in zip(f.loops, ((0, 0.1), (0, 0.9), ((z1 - z0) / 7, 0.9), ((z1 - z0) / 7, 0.1))):
        lp[lay].uv = uv
    coll.objects.link(bpy.data.objects.new("bd_road", bm_to_mesh(bm, "bd_road", [bdm["Path_Sand"]])))
    rng = np.random.default_rng(5151 + int(night))
    meshes = {v: bpy.data.meshes[f"Tree{v}"] for v in VARIANTS}
    n = 0

    def tree(x, z, v, s):
        nonlocal n
        ob = bpy.data.objects.new(f"bd_tree_{n}", meshes[v])
        coll.objects.link(ob)
        ob.location = B((x, 0.0, z))
        ob.rotation_euler = (0, 0, rng.uniform(0, 2 * math.pi))
        ob.scale = (s, s, s * rng.uniform(0.9, 1.15))
        for i, mn in enumerate((f"Bark_{v}", f"Crown_{v}")):
            ob.material_slots[i].link = "OBJECT"
            ob.material_slots[i].material = bdm[mn]
        n += 1

    def off_art(x, z):
        return not (EXT[0] - 1 < x < EXT[1] + 1 and EXT[2] - 1 < z < EXT[3] + 1)
    # the forest, south: the forest's jittered grid, out to 300 m, open along the path
    for step, rmin, rmax in ((5.0, 0, 130), (7.5, 130, 300)):
        for gx in np.arange(-rmax, rmax, step):
            for gz in np.arange(EXT[3] - 4, BD_CENTRE + rmax, step):
                x, z = gx + rng.uniform(-0.45, 0.45) * step, gz + rng.uniform(-0.45, 0.45) * step
                d = math.hypot(x, z - BD_CENTRE)
                if not (rmin <= d < rmax) or not off_art(x, z) or z < EXT[3] - 6:
                    continue
                if abs(x) < 5.5 + (z - EXT[3]) * 0.04:
                    continue
                edge = (z - EXT[3]) / 40.0 + 0.25                         # the forest's edge is ragged where it meets the meadow
                if rng.random() > min(1.0, edge + 0.15 * noise.noise(Vector((x * 0.03, z * 0.03, 1.0))) + 0.5):
                    continue
                v = VARIANTS[int(rng.choice(3, p=(0.4, 0.3, 0.3)))]
                tree(x, z, v, rng.uniform(0.8, 1.35) * (1 + 0.25 * min(1.0, d / 250)))
    # the open country round the other three sides: groves (noise-gathered) and lone trees, thinning outward, to 340 m
    for step, rmin, rmax in ((6.0, 0, 160), (9.0, 160, 340)):
        for gx in np.arange(-rmax, rmax, step):
            for gz in np.arange(-rmax, rmax, step):
                x, z = gx + rng.uniform(-0.45, 0.45) * step, BD_CENTRE + gz + rng.uniform(-0.45, 0.45) * step
                d = math.hypot(x, z - BD_CENTRE)
                if not (rmin <= d < rmax) or not off_art(x, z) or z > EXT[3] - 6:
                    continue
                grove = noise.noise(Vector((x * 0.018, z * 0.018, 4.0)))
                p = 0.9 if grove > 0.22 else (0.04 if grove > -0.1 else 0.0)
                if rng.random() > p * (1.0 - 0.35 * min(1.0, d / 340)):
                    continue
                v = VARIANTS[int(rng.choice(3, p=VARIANT_P))]
                tree(x, z, v, rng.uniform(0.85, 1.35) * (1 + 0.3 * min(1.0, d / 300)))
    # hills far out, lavender and sage, west to north to east (behind the house); the forest hides the south
    for k in range(18):
        a = math.radians(rng.uniform(-115, 115))
        d = rng.uniform(380, 780)
        x, z = math.sin(a) * d, BD_CENTRE - math.cos(a) * d
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=1.0)
        w, h = rng.uniform(150, 280), rng.uniform(26, 70)
        for vv in bm.verts:
            vv.co = Vector((x + vv.co.x * w, -z + vv.co.y * w * 0.7, vv.co.z * h - h * 0.15))
        ob = bpy.data.objects.new(f"bd_hill_{k}", bm_to_mesh(bm, f"bd_hill_{k}", [hill if k % 3 else hill2]))
        coll.objects.link(ob)
    print(f"BACKDROP {sfx}: {n} trees, 18 hills")
    return coll


def sky_world(night):
    """The painted sky, for camera rays: the page's haze colour (#f4d8ec) at the horizon, rising to lavender by day with soft clouds and the sun's glow
    where the page's own sun sprite stands (index.html dreamSky); by night a violet sky with stars and a full moon over the house (MOON_DIR) with a
    wide halo, over a pink afterglow at the horizon. Every other ray sees the page's hemisphere light."""
    w = bpy.data.worlds.get("BackdropSky") or bpy.data.worlds.new("BackdropSky")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    cr = ramp.color_ramp
    if night:
        stops = [(0.0, lin_hex(SKY_HEX)), (0.03, lin_hex(0xd6b0dc)), (0.09, lin_hex(0x8470b0)), (0.3, lin_hex(0x363070)), (1.0, lin_hex(0x141634))]
    else:
        stops = [(0.0, lin_hex(SKY_HEX)), (0.08, lin_hex(0xf0d4ec)), (0.3, lin_hex(0xdcd0f2)), (1.0, lin_hex(0xbcc8f4))]
    cr.elements[0].position, cr.elements[0].color = stops[0][0], (*stops[0][1], 1)
    cr.elements[1].position, cr.elements[1].color = stops[-1][0], (*stops[-1][1], 1)
    for p, c in stops[1:-1]:
        e = cr.elements.new(p)
        e.color = (*c, 1)
    col = ramp.outputs["Color"]
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 2.8 if not night else 320.0
    nz.inputs["Detail"].default_value = 6.0 if not night else 0.0
    stretch = nt.nodes.new("ShaderNodeMapping")
    stretch.inputs["Scale"].default_value = (1.0, 1.0, 3.4) if not night else (1.0, 1.0, 1.0)
    nt.links.new(tc.outputs["Generated"], stretch.inputs["Vector"])
    nt.links.new(stretch.outputs["Vector"], nz.inputs["Vector"])
    cm = nt.nodes.new("ShaderNodeMapRange")
    if night:
        cm.inputs["From Min"].default_value, cm.inputs["From Max"].default_value = 0.79, 0.83
    else:
        cm.inputs["From Min"].default_value, cm.inputs["From Max"].default_value = 0.50, 0.72
    nt.links.new(nz.outputs["Fac"], cm.inputs["Value"])
    above = nt.nodes.new("ShaderNodeMapRange")
    above.inputs["From Min"].default_value, above.inputs["From Max"].default_value = (0.04, 0.25) if not night else (0.06, 0.2)
    nt.links.new(sep.outputs["Z"], above.inputs["Value"])
    amt = nt.nodes.new("ShaderNodeMath")
    amt.operation = "MULTIPLY"
    nt.links.new(cm.outputs[0], amt.inputs[0])
    nt.links.new(above.outputs[0], amt.inputs[1])
    amt2 = nt.nodes.new("ShaderNodeMath")
    amt2.operation = "MULTIPLY"
    amt2.inputs[1].default_value = 0.75 if not night else 1.0
    nt.links.new(amt.outputs[0], amt2.inputs[0])
    mixc = nt.nodes.new("ShaderNodeMix")
    mixc.data_type = "RGBA"
    nt.links.new(amt2.outputs[0], mixc.inputs[0])
    nt.links.new(col, mixc.inputs[6])
    mixc.inputs[7].default_value = (1.0, 0.96, 0.98, 1) if not night else (1.0, 0.97, 0.92, 1)
    col = mixc.outputs[2]
    if night:
        sd = Vector(MOON_DIR)
        sd = B((sd.x, sd.y, sd.z))
    else:
        sd = B((-60.0, 70.0 - 1.6, -160.0 - BD_CENTRE))                  # index.html dreamSky: the sun sprite at (-60, y + 70, -160)
    sd.normalize()
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    dot.inputs[1].default_value = sd
    nt.links.new(tc.outputs["Generated"], dot.inputs[0])
    glow = None
    parts = ((900.0, 2.5), (40.0, 0.35)) if not night else ((2500.0, 0.9), (60.0, 0.22), (8.0, 0.05))
    for pw_, k_ in parts:
        pw = nt.nodes.new("ShaderNodeMath")
        pw.operation = "POWER"
        pw.inputs[1].default_value = pw_
        mx = nt.nodes.new("ShaderNodeMath")
        mx.operation = "MAXIMUM"
        mx.inputs[1].default_value = 0.0
        nt.links.new(dot.outputs["Value"], mx.inputs[0])
        nt.links.new(mx.outputs[0], pw.inputs[0])
        sc_ = nt.nodes.new("ShaderNodeMath")
        sc_.operation = "MULTIPLY"
        sc_.inputs[1].default_value = k_
        nt.links.new(pw.outputs[0], sc_.inputs[0])
        if glow is None:
            glow = sc_
        else:
            ad = nt.nodes.new("ShaderNodeMath")
            ad.operation = "ADD"
            nt.links.new(glow.outputs[0], ad.inputs[0])
            nt.links.new(sc_.outputs[0], ad.inputs[1])
            glow = ad
    if night:                                                           # the moon's disc: about 1.6 degrees across, soft-edged
        disc = nt.nodes.new("ShaderNodeMapRange")
        disc.inputs["From Min"].default_value, disc.inputs["From Max"].default_value = 0.99988, 0.99993
        disc.inputs["To Min"].default_value, disc.inputs["To Max"].default_value = 0.0, 3.0
        nt.links.new(dot.outputs["Value"], disc.inputs["Value"])
        ad = nt.nodes.new("ShaderNodeMath")
        ad.operation = "ADD"
        nt.links.new(glow.outputs[0], ad.inputs[0])
        nt.links.new(disc.outputs[0], ad.inputs[1])
        glow = ad
    gcol = nt.nodes.new("ShaderNodeMix")
    gcol.data_type = "RGBA"
    gcol.blend_type = "ADD"
    gcol.clamp_result = False
    nt.links.new(glow.outputs[0], gcol.inputs[0])
    nt.links.new(col, gcol.inputs[6])
    gcol.inputs[7].default_value = (1.0, 0.97, 0.82, 1) if not night else (0.94, 0.94, 1.0, 1)
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(gcol.outputs[2], bg.inputs["Color"])
    hemi = hemi_nodes(nt, night)
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(hemi.outputs[0], mix.inputs[1])
    nt.links.new(bg.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    bpy.context.scene.world = w
    return w


def pano_camera():
    cam = bpy.data.cameras.get("pano") or bpy.data.cameras.new("pano")
    cam.type = "PANO"
    for owner in (cam, getattr(cam, "cycles", None)):
        if owner is not None and hasattr(owner, "panorama_type"):
            owner.panorama_type = "EQUIRECTANGULAR"
    cam.clip_start, cam.clip_end = 0.1, 20000
    ob = bpy.data.objects.get("pano") or bpy.data.objects.new("pano", cam)
    if ob.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(ob)
    ob.location = B((0.0, 1.6, BD_CENTRE))
    ob.rotation_euler = (math.pi / 2, 0, 0)                    # looking north (+Y), its right is east (+X)
    return ob


def orientation_test(coll_hide):
    """Before the panoramas: three glowing markers far out (red east, green north, blue south) on a black sky, rendered small; the picture's middle
    column must be green, three quarters across red, the edges blue (docs/BLENDER.md R3: the middle faces north, the right east)."""
    sc = bpy.context.scene
    tmp = bpy.data.collections.new("OrientTest")
    sc.collection.children.link(tmp)
    for name, p, col in (("east", (400, 1.6, BD_CENTRE), (1, 0, 0)), ("north", (0, 1.6, BD_CENTRE - 400), (0, 1, 0)), ("south", (0, 1.6, BD_CENTRE + 400), (0, 0, 1))):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=80.0)
        for v in bm.verts:
            v.co += B(p)
        ob = bpy.data.objects.new(f"orient_{name}", bm_to_mesh(bm, name, [flat_material(f"orient_{name}", (0, 0, 0), emit=(col, 5.0))]))
        tmp.objects.link(ob)
    w = bpy.data.worlds.new("black")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
    sc.world = w
    for c in coll_hide:
        c.hide_render = True
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 256, 128, 100
    keep_samples = sc.cycles.samples
    sc.cycles.samples = 4
    sc.render.image_settings.file_format = "PNG"
    path = stage_work() / "orient_test.png"
    sc.render.filepath = str(path)
    sc.view_settings.view_transform = "Standard"
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(str(path))
    a = np.empty(256 * 128 * 4, np.float32)
    im.pixels.foreach_get(a)
    a = a.reshape(128, 256, 4)[64]

    def centre(ch):
        on = np.nonzero(a[:, ch] > 0.5 * a[:, ch].max())[0]
        if on.size and on.max() - on.min() > 128:
            on = np.where(on < 128, on + 256, on)
        return int(round(on.mean())) % 256
    col_of = {c: centre(i) for i, c in enumerate(("red", "green", "blue"))}
    print("ORIENT columns of the markers on the horizon row:", col_of)
    assert abs(col_of["green"] - 128) <= 4, "north is not in the middle"
    assert abs(col_of["red"] - 192) <= 4, "east is not three quarters across (the right)"
    assert min(col_of["blue"], 255 - col_of["blue"]) <= 4, "south is not at the edges"
    print("ORIENT PASS: middle north (-z), right east (+x)")
    bpy.data.images.remove(im)
    for o in list(tmp.objects):
        bpy.data.objects.remove(o)
    bpy.data.collections.remove(tmp)
    bpy.data.worlds.remove(w)
    sc.cycles.samples = keep_samples
    for c in coll_hide:
        c.hide_render = False


def stage_backdrop():
    sc = bpy.context.scene
    drop_owner_models()
    others = [c for c in bpy.data.collections if c.name in ("LayoutCheck", "Standins", "Export")]
    setup_cycles(arg("--bd-samples", 96, int))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    cam = pano_camera()
    sc.camera = cam
    orientation_test(others)
    for c in others:
        c.hide_render = True
    for night in (False, True):
        coll = build_backdrop(night)
        sky_world(night)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 4096, 2048, arg("--scale", 100, int)
        sc.view_settings.view_transform = "Standard"
        sc.view_settings.look = "None"
        sc.view_settings.exposure = 0.0
        sc.render.image_settings.file_format = "PNG"
        sc.render.image_settings.color_depth = "8"
        path = stage_work() / f"backdrop_{'night' if night else 'day'}.png"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print("BACKDROP", path, path.stat().st_size)
        coll.hide_render = True
    for c in others:
        c.hide_render = False


# ---------------------------------------------------------------- the review stills
def look_cam(name, loc, target, fov_v=75.0):
    cam = bpy.data.cameras.new(name)
    cam.sensor_fit = "VERTICAL"
    cam.lens_unit = "FOV"
    cam.angle_y = math.radians(fov_v)
    cam.clip_start, cam.clip_end = 0.05, 3000
    ob = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = B(loc)
    ob.rotation_euler = (B(target) - B(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


def strip_jpeg_meta(path):
    """Drop the JPEG's comment (FE) and APP1 (E1: EXIF/XMP) segments: Blender writes its render metadata there even with every stamp off."""
    b = path.read_bytes()
    out, i = bytearray(b[:2]), 2
    while i < len(b) and b[i] == 0xFF and b[i + 1] != 0xDA:
        n = int.from_bytes(b[i + 2:i + 4], "big")
        if b[i + 1] not in (0xFE, 0xE1):
            out += b[i:i + 2 + n]
        i += 2 + n
    out += b[i:]
    path.write_bytes(bytes(out))


FOG_NIGHT = (0.24, 0.21, 0.36)


def add_page_fog(night):
    """The page's fog for the stills: three.js Fog is linear in view depth, #f4d8ec from 22 to 105 m. Every material the stills show mixes toward it
    for camera rays; a cut-out material only where it is solid. Not saved."""
    col = FOG_NIGHT if night else tuple(lin_hex(SKY_HEX))
    mats = {m for o in bpy.data.objects if o.type == "MESH" and not o.hide_render for m in o.data.materials if m} | \
           {s.material for o in bpy.data.objects if o.type == "MESH" for s in o.material_slots if s.link == "OBJECT" and s.material}
    for m in mats:
        if m.name.startswith("bd_") or not m.use_nodes:
            continue
        nt = m.node_tree
        if "FOG_MIX" in nt.nodes:
            nt.nodes["FOG_EMIT"].inputs["Color"].default_value = (*col, 1)
            continue
        out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None) or next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
        if out is None or not out.inputs["Surface"].links:
            continue
        src = out.inputs["Surface"].links[0].from_socket
        cd = nt.nodes.new("ShaderNodeCameraData")
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = FOG
        mr.clamp = True
        lp = nt.nodes.new("ShaderNodeLightPath")
        f = nt.nodes.new("ShaderNodeMath")
        f.operation = "MULTIPLY"
        nt.links.new(cd.outputs["View Z Depth"], mr.inputs["Value"])
        nt.links.new(mr.outputs[0], f.inputs[0])
        nt.links.new(lp.outputs["Is Camera Ray"], f.inputs[1])
        fac = f.outputs[0]
        if "ALPHA_ROUND" in nt.nodes:
            g = nt.nodes.new("ShaderNodeMath")
            g.operation = "MULTIPLY"
            nt.links.new(fac, g.inputs[0])
            nt.links.new(nt.nodes["ALPHA_ROUND"].outputs[0], g.inputs[1])
            fac = g.outputs[0]
        em = nt.nodes.new("ShaderNodeEmission")
        em.name = "FOG_EMIT"
        em.inputs["Color"].default_value = (*col, 1)
        mix = nt.nodes.new("ShaderNodeMixShader")
        mix.name = "FOG_MIX"
        nt.links.new(fac, mix.inputs[0])
        nt.links.new(src, mix.inputs[1])
        nt.links.new(em.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])


def night_lights():
    """The night still's light: the moon (a sun lamp from MOON_DIR, pale blue) and the page's porch light (index.html meadowProps: a PointLight
    #ffd8a0 at the house's door, 2.6 m up and 0.6 m out). Stills only."""
    st = bpy.data.collections["Standins"]
    out = []
    ld = bpy.data.lights.new("standin_moon", "SUN")
    ld.energy = 0.55
    ld.color = (0.78, 0.82, 1.0)
    ld.angle = math.radians(1.2)
    moon = bpy.data.objects.new("standin_moon", ld)
    st.objects.link(moon)
    moon.rotation_euler = (-B(MOON_DIR)).to_track_quat("-Z", "Y").to_euler()
    out.append(moon)
    lp = bpy.data.lights.new("standin_porch_light", "POINT")
    lp.energy = 140.0
    lp.color = tuple(lin_hex(0xffd8a0))
    lp.shadow_soft_size = 0.12
    porch = bpy.data.objects.new("standin_porch_light", lp)
    st.objects.link(porch)
    d = HOUSE["door"]["at"]
    porch.location = B((d[0], 2.6, d[1] + 0.6))
    out.append(porch)
    return out


def stage_render():
    sc = bpy.context.scene
    STILLS.mkdir(parents=True, exist_ok=True)
    owner_models()
    scrub_private()
    bpy.data.collections["Art"].hide_render = True                # the stills show what ships (Export) and the page's stand-ins
    bpy.data.collections["PageDrawn"].hide_render = True
    for cn in ("Backdrop",):
        if cn in bpy.data.collections:
            bpy.data.collections[cn].hide_render = True
    setup_cycles(arg("--render-samples", 128, int))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = arg("--noise", 0.03, float)
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.use_denoising = "--no-denoise" not in args
    sc.view_settings.view_transform = "Standard"                     # the page has no tone mapping
    sc.view_settings.look = "None"
    which = arg("--only", "all")
    bpy.data.objects["Path"].visible_shadow = False                  # the page casts no shadows
    for o in [o for o in bpy.data.objects if o.type == "CAMERA" and o.name != "pano"]:
        bpy.data.objects.remove(o)
    for o in [o for o in bpy.data.objects if o.type == "LIGHT"]:
        bpy.data.objects.remove(o)
    lights = night_lights()
    a, face = K["arrive"], K["face"]
    fls = json.loads((stage_work() / "instances.json").read_text())["flowers"]
    f = min((f for f in fls if f["x"] > 2.0), key=lambda f: math.hypot(f["x"] - 3.0, f["z"] + 16.0))     # the flower nearest the path's east side, mid-meadow
    hx, hz = HOUSE["at"]
    shots = {
        "1_arrival": (look_cam("arrival", (a[0], 1.6, a[2]), (a[0] + face[0] * 10, 1.6, a[2] + face[1] * 10), 75.0), False),
        "2_wide": (look_cam("wide", (40.0, 34.0, 30.0), (-3.0, 0.0, -40.0), 58.0), False),
        "3_detail": (look_cam("detail", (f["x"] - 2.2, 0.85, f["z"] + 1.4), (f["x"], 0.35, f["z"]), 48.0), False),
        "4_day": (look_cam("day", (5.0, 1.7, -12.0), (-5.0, 2.4, -52.0), 66.0), False),
        "5_night": (look_cam("night", (1.6, 1.6, -42.0), (hx - 0.4, 4.6, hz), 66.0), True),
    }
    work = stage_work()
    for key, (cam, night) in shots.items():
        if which not in ("all", key):
            continue
        for lo in lights:
            lo.hide_render = not night and lo.name == "standin_moon"
        bd = work / f"backdrop_{'night' if night else 'day'}.png"
        setup_world(night, bd if key != "2_wide" else None, cam_col=tuple(lin_hex(SKY_HEX)))
        add_page_fog(night)
        sc.camera = cam
        sc.view_settings.exposure = 0.9 if night else 0.0
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 1080, arg("--scale", 100, int)
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        path = STILLS / f"{key}.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 400_000 and q > 40:
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        strip_jpeg_meta(path)
        print("STILL", key, path.stat().st_size, "q", q)


if __name__ == "__main__":
    ST = set(STAGE.split(",")) | ({"art", "axes", "bake", "export", "backdrop", "render"} if STAGE == "all" else set())
    if "art" in ST:
        build_all()
        save_blend()
    else:
        ART = bpy.data.collections.get("Art")
        EXPORT = bpy.data.collections.get("Export")
        STANDIN = bpy.data.collections.get("Standins")
        PAGE = bpy.data.collections.get("PageDrawn")
    if "axes" in ST:
        stage_axes()
        save_blend()
    if "bake" in ST:
        stage_bake()
    if "export" in ST:
        stage_export()
    if "backdrop" in ST:
        stage_backdrop()
    if "render" in ST:
        stage_render()
