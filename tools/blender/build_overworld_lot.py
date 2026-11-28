"""Builds the Overworld's parking lot (`parking_lot`) in Blender: the lot of part 1 made an Overworld scene of its own, dressed in the Overworld's
look, its ambient occlusion baked, exported as world/parking_lot.glb and world/parking_lot.json (the owner, 2026-11-27: "The parking lot was
supposed to be part of the overworld and that house with balloons was supposed to go since it's been replaced").

Re-runnable, from the repo root:

    python tools/blender/build_overworld_lot.py --stage textures       (blender/textures/overworld_lot/, plain Python: numpy and Pillow)
    blender -b --factory-startup --python tools/blender/build_overworld_lot.py -- --stage art,bake,export,render [--samples 256] [--work <dir>]
        art:    the art and the layout objects; saves blender/scenes/parking_lot.blend, writes world/parking_lot.json, runs the layout check
        bake:   the ambient occlusion, two maps (the ground and the hedges; everything standing), into <work>/parking_lot_<n>.png
        export: <work>/parking_lot_raw.glb (the art merged by material)
        render: docs/renders/parking_lot/1_arrival.jpg, 2_wide.jpg, 3_detail.jpg, 4_plan.jpg
    python tools/blender/pack_scene.py parking_lot --work <work>/parking_lot     (WebP: world/parking_lot.glb and its AO maps)
    blender -b --factory-startup --python tools/blender/build_overworld_lot.py -- --stage compare --work <dir>
        the same views before (world/L4.glb with the store's old Exterior.glb, <work>/ctx/Exterior_before.glb) and after (world/L4.glb with
        world/parking_lot.glb and the two sets), into <work>/parking_lot/compare/; `--stage sheet` (plain Python) lays them out as an owner sheet

The layout is the greybox's: tools/blender/build_overworld_greybox.py (`parking_lot()`, imported here), so no coordinate of the layout is typed
in here: every collider, link, marker, spot and corridor comes from it, and export_scene.py writes the same world/parking_lot.json as
`build_overworld_greybox.py --preview`. Each collider's art is built inside its own box (a car fills its bay's box up to its bonnet, its cabin
standing on it; a post is a round post; a hedge is a rounded box), so the layout check's cover and stray rules hold; what can be walked through
is decor_ (the paint, the kerbs, the beds, the carts, the cones, the tyre planters, the flowers, the crowns and signs overhead).

The lot keeps part 1's frame: its floor is at y 9.6, where world/L4.glb's store stands at its north side. The store is not built here (its art
is L4.glb's, its colliders are copied into the layout from world/L4.json); the layout check leaves those colliders to L4.glb, and checks the
rest in the lot's own floor frame (y - 9.6), as it checks every other Overworld scene. In the bake, the store (world/L4.glb) and the two sets
that stand in the lot (world/table_and_chairs.glb, world/bus_station.glb, when <work>/ctx holds them) are there for the rays, never exported.

Light: open air, as every Overworld scene (docs/BLENDER.md R1, AO-only): the baked materials carry `aomap` (world/lightmaps/parking_lot_<n>.webp)
and `aomap_intensity` on the second UV set, and the page keeps them lit by its sun and sky. The lamp heads are `Lamp_Emit`. The far lawn
(Grass_Far, past 20 m from the lot) is not baked: it is open ground, its AO is 1. Every texture is generated here (numpy, own work), but for
the store's own four sign pictures (its logo, PARKING, STOP and the cart sign), which are copied out of the store's model as they were.

A game point (x, y, z) is Blender (x, -z, y).
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
except ImportError:                       # the textures and sheet stages run in plain Python (numpy and Pillow)
    bpy = None

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import build_overworld_greybox as G      # noqa: E402  the layout model (pure Python)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


SCENE = "parking_lot"
STAGE = arg("--stage", "art")
SAMPLES = arg("--samples", 256, int)
DEVICE = arg("--device", "auto")
TEXDIR = "blender/textures/overworld_lot/"
Y = G.LOT_Y                               # the lot's floor
MARGIN_PX = 8


# ================================================================ generated textures (plain Python)
def _rng(seed):
    return np.random.default_rng(seed)


def pnoise(h, w, scale, rng):
    """Periodic noise in 0..1: white noise low-passed in the Fourier domain (scale: the feature size in pixels)."""
    f = np.fft.fft2(rng.standard_normal((h, w)))
    fy, fx = np.fft.fftfreq(h)[:, None], np.fft.fftfreq(w)[None, :]
    a = np.real(np.fft.ifft2(f * np.exp(-((fx ** 2 + fy ** 2) * (scale ** 2)) * 2.0)))
    a -= a.min()
    return a / max(a.max(), 1e-9)


def fbm(h, w, scales, weights, rng):
    a = sum(wt * pnoise(h, w, s, rng) for s, wt in zip(scales, weights))
    a -= a.min()
    return a / max(a.max(), 1e-9)


def mix(c0, c1, t):
    c0, c1 = np.array(c0, float), np.array(c1, float)
    return c0[None, None, :] * (1 - t[..., None]) + c1[None, None, :] * t[..., None]


# sRGB colours (what the eye sees), 0..1: the asphalt, the grass and the hedges are the road's and the bus station's
# (tools/blender/overworld_textures.py), so the lot meets the road through its south hedge and the sets stand on the same ground
def tex_asphalt(n=1024):
    rng = _rng(31)
    t = fbm(n, n, (60, 6, 1.0), (0.3, 0.3, 0.4), rng)
    c = mix((0.25, 0.25, 0.29), (0.39, 0.38, 0.43), t)
    peb = pnoise(n, n, 0.8, rng) > 0.88
    c[peb] = c[peb] * 0.5 + np.array([0.60, 0.57, 0.62]) * 0.5
    return c


def tex_grass(n=1024):
    rng = _rng(32)
    t = fbm(n, n, (90, 30, 8), (0.5, 0.35, 0.15), rng)
    c = mix((0.40, 0.72, 0.36), (0.55, 0.84, 0.42), t)
    c *= (0.92 + 0.12 * pnoise(n, n, 1.2, rng))[..., None]
    flecks = pnoise(n, n, 2.0, rng) > 0.86
    c[flecks] = c[flecks] * 0.6 + np.array([0.80, 0.92, 0.55]) * 0.4
    return np.clip(c, 0, 0.86)


def tex_hedge(n=512):
    rng = _rng(33)
    t = fbm(n, n, (12, 4, 1.5), (0.4, 0.35, 0.25), rng)
    c = mix((0.12, 0.40, 0.18), (0.34, 0.66, 0.30), t)
    hi = pnoise(n, n, 1.0, rng) > 0.8
    c[hi] = c[hi] * 0.7 + np.array([0.55, 0.80, 0.45]) * 0.3
    return c


def tex_paving(n=512, slabs=4):
    """Pale lilac-grey slabs, 0.5 m each (the texture is 2 m), with grout lines, as the bus station's platform."""
    rng = _rng(34)
    c = mix((0.80, 0.78, 0.84), (0.88, 0.86, 0.90), fbm(n, n, (20, 3), (0.6, 0.4), rng))
    cell = n // slabs
    for i in range(slabs):
        for j in range(slabs):
            c[i * cell:(i + 1) * cell, j * cell:(j + 1) * cell] *= 0.96 + 0.06 * rng.random()
    g = np.zeros((n, n), bool)
    for k in range(slabs + 1):
        a = min(k * cell, n - 1)
        g[max(a - 2, 0):a + 3, :] = True
        g[:, max(a - 2, 0):a + 3] = True
    c[g] = c[g] * 0.78
    return np.clip(c, 0, 0.92)


SIGNS = ["MARKET  >", "<  PLAYGROUND", "PARKING LOT", "TO THE FOREST", "THE HILLS", "THE FOREST", "PLAYGROUND", "MARKET"]
SIGN_BG, SIGN_FG = (0.92, 0.86, 0.66), (0.30, 0.20, 0.14)          # the road's signposts' board and letters


def tex_signs():
    """Eight 1024 x 128 rows: the boards over the joins, the signpost and the stile. The letters are drawn with the system's sans-serif bold
    (pixels only; no font file is shipped)."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (1024, 1024), tuple(int(v * 255) for v in SIGN_BG))
    d = ImageDraw.Draw(im)
    font = None
    for f in ("C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(f, 84)
            break
        except OSError:
            continue
    font = font or ImageFont.load_default(size=84)
    fg = tuple(int(v * 255) for v in SIGN_FG)
    for i, t in enumerate(SIGNS):
        y0 = i * 128
        d.rectangle((6, y0 + 6, 1017, y0 + 121), outline=fg, width=6)
        w = d.textlength(t, font=font)
        d.text(((1024 - w) / 2, y0 + 20), t, font=font, fill=fg)
    return im


def sign_uv(text):
    i = SIGNS.index(text)
    return (0.0, 1 - (i + 1) / 8, 1.0, 1 - i / 8)            # (u0, v0, u1, v1), Blender's v up


# the store's own sign pictures (world/Exterior.glb before the split: logo_lot, sign_stop, sign_parking, sign_cart), on one 1024 x 512 atlas
STORE_SIGNS = {"logo": (0, 0, 512, 512), "stop": (512, 0, 768, 256), "parking": (768, 0, 1024, 128), "cart": (768, 128, 1024, 256)}


def store_uv(name):
    x0, y0, x1, y1 = STORE_SIGNS[name]
    return (x0 / 1024, 1 - y1 / 512, x1 / 1024, 1 - y0 / 512)


def tex_store_signs(src):
    """The atlas from the four pictures in `src` (a folder of PNGs copied out of the old Exterior.glb), each over white (the posts' signs)
    or the pylon's blue (the logo), so nothing needs alpha."""
    from PIL import Image
    at = Image.new("RGB", (1024, 512), (255, 255, 255))
    for name, fn, bg in (("logo", "logo_lot.png", (14, 54, 160)), ("stop", "sign_stop.png", (255, 255, 255)),
                         ("parking", "sign_parking.png", (32, 32, 32)), ("cart", "sign_cart.png", (32, 32, 32))):
        x0, y0, x1, y1 = STORE_SIGNS[name]
        im = Image.open(Path(src) / fn).convert("RGBA").resize((x1 - x0, y1 - y0), Image.LANCZOS)
        base = Image.new("RGBA", im.size, bg + (255,))
        at.paste(Image.alpha_composite(base, im).convert("RGB"), (x0, y0))
    return at.point(lambda v: int(v * 0.92 + 0.5))           # the whites held under 1 on the page, as every Overworld colour


def stage_textures():
    from PIL import Image
    d = ROOT / TEXDIR
    d.mkdir(parents=True, exist_ok=True)
    for name, fn in (("asphalt", tex_asphalt), ("grass", tex_grass), ("hedge", tex_hedge), ("paving", tex_paving)):
        a = fn()
        Image.fromarray(np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8), "RGB").save(d / f"{name}.jpg", "JPEG", quality=88, optimize=True)
    tex_signs().save(d / "signs.png", optimize=True)
    src = arg("--store-signs")
    if src:                                                    # once, from the pictures copied out of the old Exterior.glb
        tex_store_signs(src).save(d / "store_signs.png", optimize=True)
    for f in sorted(d.iterdir()):
        print("TEXTURE", f.relative_to(ROOT), f.stat().st_size)


# ================================================================ the owner sheet (plain Python)
def stage_sheet():
    from PIL import Image, ImageDraw, ImageFont
    cmp_dir = Path(arg("--work", str(ROOT / "work"))) / SCENE / "compare"
    out = Path(arg("--out", str(cmp_dir / "owner_parking_lot.png")))
    font = None
    for f in ("C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            font, small = ImageFont.truetype(f, 34), ImageFont.truetype(f.replace("bd", "") if "arialbd" in f else f, 24)
            break
        except OSError:
            continue
    W, H = 960, 540
    rows = [("bus", ("after", "l4"), ("THE OVERWORLD", "L4 (THE ORIGINAL)"),
             "From the bus station (-46, 9.75, 47), toward Hallam Row: the city's towers on the horizon, south past the back hedge"),
            ("doors", ("after", "l4"), ("THE OVERWORLD", "L4 (THE ORIGINAL)"),
             "From the store's doors (0, 9.6, 29.5), out over the lot to the skyline (gbi_L4_4 sees the same through the glass)"),
            ("arrival", ("before", "after"), ("BEFORE", "AFTER"), "From the table, where the walk out of the store arrives (-8, 9.6, 43.6)"),
            ("west", ("before", "after"), ("BEFORE", "AFTER"), "West across the lot, toward where the Right Door, Wrong Exit house stood (x -120)")]
    sheet = Image.new("RGB", (2 * W + 60, 120 + len(rows) * (H + 70) + H + 200), (246, 244, 240))
    d = ImageDraw.Draw(sheet)
    d.text((20, 20), "parking_lot: the Overworld's lot; the house gone; the city's towers on the horizon from the bus stop", font=font,
           fill=(30, 30, 34))
    d.text((20, 66), "Overworld: L4.glb + parking_lot.glb + city_skyline.glb + the two sets, clear-day sky.  L4: the same with the split "
           "Exterior.glb, at its own dusk.  Before: L4.glb + the old Exterior.glb.", font=small, fill=(60, 60, 66))
    y = 120
    for key, sides, labels, cap in rows:
        d.text((20, y), cap, font=small, fill=(30, 30, 34))
        for k, (side, lab) in enumerate(zip(sides, labels)):
            p = cmp_dir / f"{side}_{key}.jpg"
            if p.exists():
                sheet.paste(Image.open(p).convert("RGB").resize((W, H), Image.LANCZOS), (20 + k * (W + 20), y + 34))
            d.text((30 + k * (W + 20), y + 42), lab, font=font, fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0))
        y += H + 70
    d.text((20, y), "The Overworld from high over the store's back, out to the skyline (left), and the plan of the lot (right: the store, "
           "the two sets, the arches east and west, the road's gap and the stile)", font=small, fill=(30, 30, 34))
    for k, nm in enumerate(("after_overview.jpg", "after_plan.jpg")):
        p = cmp_dir / nm
        if p.exists():
            im = Image.open(p).convert("RGB")
            im.thumbnail((W, H + 120), Image.LANCZOS)
            sheet.paste(im, (20 + k * (W + 20), y + 34))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, optimize=True)
    print("SHEET", out, sheet.size, out.stat().st_size)


if bpy is None:
    if STAGE == "textures":
        stage_textures()
    elif STAGE == "sheet":
        stage_sheet()
    else:
        print("without Blender only --stage textures or --stage sheet runs")
    sys.exit(0)


# ================================================================ Blender from here on
GB = G.build(SCENE)
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
STILLS = ROOT / f"docs/renders/{SCENE}"
STORE_COLS = {b["name"] for b in GB.boxes if "store" in b["tags"]}


def work_dir(sub=None):
    d = Path(arg("--work", str(ROOT / "work"))) / SCENE
    if sub:
        d = d / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


def ctx_dir():
    return Path(arg("--work", str(ROOT / "work"))) / "ctx"


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


def material(name, color=(0.5, 0.5, 0.5), rough=0.6, diff=None, emit=None, tile=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    if diff:
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "UVMap"
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image(TEXDIR + diff, True)
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    m.use_backface_culling = True
    TILES[name] = tile
    MATS[name] = m
    return m


LAMP_EMIT = 3.0
TEXTURED = {   # name: (texture, roughness, metres a repeat)
    "Asphalt": ("asphalt.jpg", 0.9, 4.0), "Paving": ("paving.jpg", 0.85, 2.0), "Grass": ("grass.jpg", 0.95, 4.0),
    "Grass_Far": ("grass.jpg", 0.95, 4.0), "Hedge": ("hedge.jpg", 0.9, 2.0), "Signs": ("signs.png", 0.5, 1.0), "Store_Signs": ("store_signs.png", 0.5, 1.0),
}
# flat colours, linear, every channel held at or under 0.85 (the Overworld is plastic and pastel, docs/WORLD.md)
FLAT = {
    "Steel": (0.52, 0.55, 0.60), "Paint_White": (0.84, 0.84, 0.80), "Paint_Yellow": (0.85, 0.70, 0.30), "Kerb": (0.66, 0.64, 0.70),
    "Timber": (0.50, 0.32, 0.18), "Bark": (0.40, 0.27, 0.20), "Soil": (0.26, 0.17, 0.11), "Shrub": (0.26, 0.56, 0.30),
    "Leaf_Pink": (0.85, 0.48, 0.64), "Leaf_Mint": (0.46, 0.80, 0.60), "Leaf_Lilac": (0.64, 0.54, 0.85),
    "Pylon_Blue": (0.04, 0.13, 0.52), "Plastic_Coral": (0.85, 0.42, 0.40), "Plastic_White": (0.82, 0.80, 0.76), "Bin_Green": (0.16, 0.48, 0.30),
    "Cart_Blue": (0.24, 0.42, 0.80), "Cart_Wire": (0.56, 0.58, 0.62), "Tyre": (0.04, 0.04, 0.045), "Car_Glass": (0.12, 0.16, 0.24), "Car_Light": (0.85, 0.82, 0.70),
    "Car_Cover": (0.62, 0.56, 0.74),
    "Flower_Pink": (0.85, 0.46, 0.66), "Flower_Yellow": (0.85, 0.74, 0.30), "Flower_White": (0.84, 0.84, 0.82), "Flower_Lilac": (0.60, 0.48, 0.85),
    "Flower_Stem": (0.20, 0.50, 0.22),
}
# part 1's car colours, made pastel: (its colour name) -> material
CAR = {"black": ("Car_Plum", (0.42, 0.30, 0.50)), "green": ("Car_Mint", (0.40, 0.76, 0.58)), "navy": ("Car_Periwinkle", (0.38, 0.46, 0.80)),
       "red": ("Car_Coral", (0.85, 0.40, 0.42)), "silver": ("Car_Silver", (0.64, 0.66, 0.72)), "teal": ("Car_Teal", (0.28, 0.66, 0.68)),
       "van": ("Car_Cream", (0.82, 0.78, 0.68)), "white": ("Car_Pink", (0.85, 0.58, 0.68)), "yellow": ("Car_Yellow", (0.85, 0.74, 0.36)),
       "covered": ("Car_Cover", (0.62, 0.56, 0.74))}


def make_materials():
    for n, (tx, r, tile) in TEXTURED.items():
        material(n, diff=tx, rough=r, tile=tile)
    for n, c in FLAT.items():
        material(n, color=c, rough=0.15 if n == "Car_Glass" else 0.4 if n.startswith(("Plastic", "Bin", "Cart", "Pylon")) else 0.6)
    for n, c in CAR.values():
        if n not in MATS:
            material(n, color=c, rough=0.35)
    material("Lamp_Emit", color=(0.85, 0.84, 0.76), rough=0.5, emit=((1.0, 0.95, 0.80), LAMP_EMIT))


# ---------------------------------------------------------------- geometry helpers (game coordinates in, world space)
def cube(bm, gmin, gmax):
    a, b = B(gmin), B(gmax)
    c = (a + b) / 2
    s = Vector((abs(a.x - b.x), abs(a.y - b.y), abs(a.z - b.z)))
    return bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((s.x, s.y, s.z, 1.0)))["verts"]


def bevel_box(bm, gmin, gmax, r=0.02, seg=2):
    vs = cube(bm, gmin, gmax)
    d = min(gmax[i] - gmin[i] for i in range(3))
    r = min(r, d * 0.3)
    if r > 0.004:
        es = list({e for v in vs for e in v.link_edges})
        bmesh.ops.bevel(bm, geom=es + vs, offset=r, segments=seg, affect="EDGES", profile=0.5, clamp_overlap=True)


def cyl(bm, p0, p1, r0, r1=None, seg=12, cap=True):
    a, b = B(p0), B(p1)
    d = b - a
    q = d.to_track_quat("Z", "Y")
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                          matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())


def ellipsoid(bm, p, rx, ry, rz, seg=10):
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(5, seg // 2 + 1), radius=1.0,
                              matrix=Matrix.Translation(B(p)) @ Matrix.Diagonal((rx, rz, ry, 1)))


def ring(bm, c, r_major, r_minor, seg=16):
    """A torus lying flat (a tyre on its side): a tube round a circle."""
    pts = [(c[0] + r_major * math.cos(2 * math.pi * k / seg), c[1], c[2] + r_major * math.sin(2 * math.pi * k / seg)) for k in range(seg + 1)]
    tube(bm, pts, r_minor, 8)


def quad(bm, x0, x1, z0, z1, y):
    vs = [bm.verts.new(B(p)) for p in ((x0, y, z0), (x0, y, z1), (x1, y, z1), (x1, y, z0))]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.z < 0:
        f.normal_flip()
    return f


def box_uv(bm, tile):
    uvl = bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y
            u, v = ((gz, gy) if ax == 0 else (gx, gy) if ax == 1 else (gx, gz))
            lp[uvl].uv = (u / tile, v / tile)


ART = LAYOUT_C = None


def finish(name, bm, mat, coll=None, smooth=False, keep_uv=False):
    for f in bm.faces:
        f.smooth = smooth
    if not bm.loops.layers.uv.get("UVMap"):
        bm.loops.layers.uv.new("UVMap")
    bm.normal_update()
    if not keep_uv:
        box_uv(bm, TILES.get(mat, 1.0))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(name, me)
    (coll or ART).objects.link(ob)
    if mat == "Lamp_Emit":
        ob.visible_shadow = False
    return ob


class Acc:
    """Faces by material for one named piece of art, finished as one object per material: <name> for the first, <name>_<material> after."""
    def __init__(s, name, coll=None):
        s.name, s.bms, s.coll, s.smooth = name, {}, coll, set()

    def bm(s, mat, smooth=False):
        if smooth:
            s.smooth.add(mat)
        return s.bms.setdefault(mat, bmesh.new())

    def done(s):
        out = []
        for i, (m, bm) in enumerate(s.bms.items()):
            if not bm.faces:
                bm.free()
                continue
            out.append(finish(s.name if i == 0 else f"{s.name}_{m}", bm, m, s.coll, smooth=m in s.smooth))
        return out


def face_uv(bm, uvrect, normal_game):
    """Map the faces of bm whose normal is normal_game onto the atlas rect (u0, v0, u1, v1), as read from in front of them."""
    u0, v0, u1, v1 = uvrect
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    n = B(normal_game).normalized()
    right = Vector((0, 0, 1)).cross(n)
    bm.normal_update()
    front = [f for f in bm.faces if f.normal.dot(n) > 0.9]
    pts = [lp.vert.co for f in front for lp in f.loops]
    if not pts:
        return
    us, zs = [p.dot(right) for p in pts], [p.z for p in pts]
    a0, a1, b0, b1 = min(us), max(us), min(zs), max(zs)
    for f in front:
        for lp in f.loops:
            p = lp.vert.co
            lp[uvl].uv = (u0 + (u1 - u0) * (p.dot(right) - a0) / max(a1 - a0, 1e-6), v0 + (v1 - v0) * (p.z - b0) / max(b1 - b0, 1e-6))


def board(name, mn, mx, uvrect, normals, mat="Signs"):
    """A thin board whose faces toward `normals` carry the atlas rect; its other faces take the rect's corner (the board's own colour)."""
    bm = bmesh.new()
    cube(bm, mn, mx)
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for lp in f.loops:
            lp[uvl].uv = (uvrect[0] + 0.002, uvrect[1] + 0.002)
    for nrm in normals:
        face_uv(bm, uvrect, nrm)
    return finish(name, bm, mat, keep_uv=True)


def disc_sign(name, c, r, normal, uvrect, sides=40, rot=0.0):
    """A round (or, with sides 8, octagonal) sign facing `normal` (a game (x, z) axis), its face mapped onto the atlas rect as read from in front."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    u0, v0, u1, v1 = uvrect
    nx, nz = normal
    # the reader's right: facing a sign whose face looks +z (south) you look north, and your right is +x; likewise for the others
    rx, rz = (1.0, 0.0) if nz > 0 else (-1.0, 0.0) if nz < 0 else (0.0, -float(nx))
    vs, uvs = [], {}
    for k in range(sides):
        a = rot + 2 * math.pi * k / sides
        du, dv = math.cos(a), math.sin(a)
        v = bm.verts.new(B((c[0] + r * du * rx, c[1] + r * dv, c[2] + r * du * rz)))
        vs.append(v)
        uvs[v] = (u0 + (u1 - u0) * (0.5 + 0.5 * du), v0 + (v1 - v0) * (0.5 + 0.5 * dv))
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.dot(B((nx, 0, nz))) < 0:
        f.normal_flip()
    for lp in f.loops:
        lp[uvl].uv = uvs[lp.vert]
    return finish(name, bm, "Store_Signs", keep_uv=True)


# ---------------------------------------------------------------- the art of each layout box
def box_of(name):
    return next(b for b in GB.boxes if b["name"] == name)


def slab(name, b, mat, drop=0.0):
    """Ground: its top (lowered by `drop`), and its sides down to the box's bottom (no bottom face)."""
    bm = bmesh.new()
    mx = list(b["max"])
    mx[1] -= drop
    cube(bm, b["min"], mx)
    bm.normal_update()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.normal.z < -0.9], context="FACES")
    return finish(name, bm, mat)


def hedge_art(name, b):
    bm = bmesh.new()
    bevel_box(bm, b["min"], b["max"], 0.14, 2)
    return finish(name, bm, "Hedge")


def post_art(name, b, mat="Steel"):
    mn, mx = b["min"], b["max"]
    c = ((mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2)
    r = min(mx[0] - mn[0], mx[2] - mn[2]) / 2
    bm = bmesh.new()
    cyl(bm, (c[0], mn[1], c[1]), (c[0], mx[1], c[1]), r, seg=10)
    return finish(name, bm, mat, smooth=True)


def bench_art(name, b):
    mn, mx = b["min"], b["max"]
    acc = Acc(name)
    bm = acc.bm("Timber")
    L0, L1, W0, W1 = mn[0], mx[0], mn[2], mx[2]
    n, gap = 4, 0.02
    w = (W1 - W0 - gap * (n - 1)) / n
    for k in range(n):
        a = W0 + k * (w + gap)
        bevel_box(bm, (L0, mx[1] - 0.05, a), (L1, mx[1], a + w), 0.01, 1)
    st = acc.bm("Steel")
    for t in (L0, L1 - 0.06):
        for s0, s1 in ((W0, W0 + 0.06), (W1 - 0.06, W1)):
            cube(st, (t, mn[1], s0), (t + 0.06, mx[1] - 0.05, s1))
    acc.done()


def bin_art(name, b):
    mn, mx = b["min"], b["max"]
    c = ((mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2)
    r = min(mx[0] - mn[0], mx[2] - mn[2]) / 2
    acc = Acc(name)
    cyl(acc.bm("Bin_Green", True), (c[0], mn[1], c[1]), (c[0], mx[1] - 0.06, c[1]), r * 0.9, r, seg=16)
    cyl(acc.bm("Steel", True), (c[0], mx[1] - 0.06, c[1]), (c[0], mx[1], c[1]), r, r * 0.8, seg=16)
    acc.done()


def rack_art(name, b):
    """A cycle rack: four steel hoops along the box, joined at the foot."""
    mn, mx = b["min"], b["max"]
    bm = bmesh.new()
    zc = (mn[2] + mx[2]) / 2
    n = 4
    w = (mx[0] - mn[0]) / n
    for k in range(n):
        x0, x1 = mn[0] + k * w + 0.08, mn[0] + (k + 1) * w - 0.08
        r = (x1 - x0) / 2
        pts = [(x0, mn[1], zc), (x0, mx[1] - r, zc)] + [((x0 + x1) / 2 - r * math.cos(t), mx[1] - r + r * math.sin(t) - 0.03, zc)
                                                         for t in np.linspace(0.15, math.pi - 0.15, 7)] + [(x1, mx[1] - r, zc), (x1, mn[1], zc)]
        tube(bm, pts, 0.03, 8)
    cube(bm, (mn[0], mn[1], mn[2]), (mx[0], mn[1] + 0.04, mx[2]))
    cube(bm, (mn[0], mn[1], mn[2]), (mn[0] + 0.05, mx[1], mx[2]))
    cube(bm, (mx[0] - 0.05, mn[1], mn[2]), (mx[0], mx[1], mx[2]))
    return finish(name, bm, "Steel", smooth=True)


def tube(bm, pts, r, seg=8):
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
        bb = t.cross(nn)
        prev = nn
        rings.append([bm.verts.new(p + (nn * math.cos(2 * math.pi * k / seg) + bb * math.sin(2 * math.pi * k / seg)) * r) for k in range(seg)])
    for a_, b_ in zip(rings, rings[1:]):
        for k in range(seg):
            bm.faces.new((a_[k], a_[(k + 1) % seg], b_[(k + 1) % seg], b_[k]))


def corral_art(name, b):
    """A cart corral's side: a post at each end and two rails, one object filling the collider's box."""
    mn, mx = b["min"], b["max"]
    bm = bmesh.new()
    along_x = (mx[0] - mn[0]) >= (mx[2] - mn[2])
    for end in (0, 1):
        if along_x:
            x0 = mn[0] if end == 0 else mx[0] - 0.08
            cube(bm, (x0, mn[1], mn[2]), (x0 + 0.08, mx[1], mx[2]))
        else:
            z0 = mn[2] if end == 0 else mx[2] - 0.08
            cube(bm, (mn[0], mn[1], z0), (mx[0], mx[1], z0 + 0.08))
    for y in (0.35, mx[1] - mn[1] - 0.06):
        cube(bm, (mn[0], mn[1] + y, mn[2]), (mx[0], mn[1] + y + 0.06, mx[2]))
    return finish(name, bm, "Steel")


def car_art(name, b):
    """A rounded plastic car filling its collider's box up to the bonnet (the box's top), its cabin standing on it (solid: it is over the box),
    wheels, windows and lamps. The box runs along z; `yaw` says which end is the front."""
    mn, mx = b["min"], b["max"]
    col = next(t for t in b["tags"] if t.startswith("car:"))[4:]
    yaw = int(next(t for t in b["tags"] if t.startswith("yaw:"))[4:])
    mat = CAR[col][0]
    x0, x1, z0, z1, y0, yb = mn[0], mx[0], mn[2], mx[2], mn[1], mx[1]
    acc = Acc(name)
    if col == "covered":
        bm = acc.bm(mat, True)
        bevel_box(bm, (x0, y0 + 0.05, z0), (x1, yb - 0.25, z1), 0.25, 3)
        bevel_box(bm, (x0 + 0.18, yb - 0.45, z0 + 0.9), (x1 - 0.18, yb, z1 - 0.8), 0.22, 3)
        for zz in (z0 + 0.5, z1 - 0.5):
            cube(acc.bm("Tyre"), (x0 + 0.02, y0, zz - 0.25), (x1 - 0.02, y0 + 0.08, zz + 0.25))
        acc.done()
        return
    front = 1 if yaw < 0 else -1                        # the bonnet's end: +z or -z
    van = col == "van"
    body = acc.bm(mat, True)
    bevel_box(body, (x0 + 0.02, y0 + 0.24, z0), (x1 - 0.02, yb, z1), 0.16, 3)
    if van:
        ca, cb = (z0 + 0.25, z1 - 1.0) if front > 0 else (z0 + 1.0, z1 - 0.25)
        top = yb + 1.05
    else:
        ca, cb = (z0 + 1.15, z1 - 1.45) if front > 0 else (z0 + 1.45, z1 - 1.15)
        top = yb + 0.62
    bevel_box(body, (x0 + 0.12, yb - 0.02, ca), (x1 - 0.12, top, cb), 0.14, 3)
    gl = acc.bm("Car_Glass")
    for xs in (x0 + 0.105, x1 - 0.125):                 # side windows
        cube(gl, (xs, yb + 0.12, ca + 0.18), (xs + 0.02, top - 0.1, cb - 0.18))
    for zz, sgn in ((ca, -1), (cb, 1)):                 # the windscreen and the rear window
        cube(gl, (x0 + 0.25, yb + 0.1, zz + sgn * 0.01 - 0.01), (x1 - 0.25, top - 0.12, zz + sgn * 0.01 + 0.01))
    ty = acc.bm("Tyre", True)
    for zz in (z0 + 0.36, z1 - 0.36):                    # at the corners: toy wheels (they also fill the box's foot, for the cover rule)
        for xa, xb in ((x0, x0 + 0.26), (x1 - 0.26, x1)):
            cyl(ty, (xa, y0 + 0.33, zz), (xb, y0 + 0.33, zz), 0.33, seg=14)
    lt = acc.bm("Car_Light")
    zf = z1 if front > 0 else z0
    for xs in (x0 + 0.25, x1 - 0.55):
        cube(lt, (xs, yb - 0.25, zf - 0.03 if front > 0 else zf), (xs + 0.3, yb - 0.1, zf if front > 0 else zf + 0.03))
    acc.done()


def tree_art(name, b, crown_box=None, seed=0):
    """A pastel tree: a tapered trunk filling its collider and a crown of plastic blobs overhead (decor_)."""
    mn, mx = b["min"], b["max"]
    cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
    r = min(mx[0] - mn[0], mx[2] - mn[2]) / 2
    bm = bmesh.new()
    cyl(bm, (cx, mn[1], cz), (cx, mx[1], cz), r, r * 0.7, seg=10)
    finish(name, bm, "Bark", smooth=True)
    rng = np.random.default_rng(seed)
    mat = ["Leaf_Pink", "Leaf_Mint", "Leaf_Lilac"][seed % 3]
    acc = Acc(f"decor_{name}_Crown")
    y0 = mx[1] - 0.2
    for k in range(5):
        a = 2 * math.pi * k / 5 + rng.uniform(-0.3, 0.3)
        rr = 0.9 if k else 0.0
        ellipsoid(acc.bm(mat, True), (cx + rr * math.cos(a), y0 + 1.1 + rng.uniform(-0.2, 0.4), cz + rr * math.sin(a)),
                  1.25 + rng.uniform(-0.2, 0.2), 1.0, 1.25 + rng.uniform(-0.2, 0.2), seg=12)
    ellipsoid(acc.bm(mat, True), (cx, y0 + 2.0, cz), 1.1, 0.9, 1.1, seg=12)
    acc.done()


def lamp_post(name, x, z, y0, h=4.5):
    """A lamp in a hedge: its pole (solid: it stands in the hedge's box) and its head (decor_, overhead)."""
    bm = bmesh.new()
    cyl(bm, (x, y0, z), (x, y0 + h, z), 0.07, 0.05, seg=10)
    finish(name, bm, "Steel", smooth=True)
    acc = Acc(f"decor_{name}_Head")
    ellipsoid(acc.bm("Lamp_Emit", True), (x, Y + h + 0.06, z), 0.22, 0.17, 0.22, seg=14)
    cyl(acc.bm("Steel", True), (x, Y + h + 0.15, z), (x, Y + h + 0.3, z), 0.30, 0.06, seg=16)
    acc.done()


# ---------------------------------------------------------------- the dressing, from the model's boxes
def build_boxes():
    for b in GB.boxes:
        if b.get("zone") or b.get("ctx") or not b.get("art", True):
            continue
        n, mn, mx = b["name"], b["min"], b["max"]
        if n.startswith("Ground_"):
            far = "far" in b["tags"]
            mat = {"asphalt": "Asphalt", "paving": "Paving", "grass": "Grass_Far" if far else "Grass"}[b["mat"]]
            slab(n, b, mat, drop=0.03 if b["mat"] == "grass" else 0.0)
        elif n.startswith("Hedge_"):
            hedge_art(n, b)
        elif n.startswith("Car_"):
            car_art(n, b)
        elif n.startswith("Tree_") and not n.endswith("_Crown"):
            tree_art(n, b, seed=int(n.split("_")[1]))
        elif n.startswith(("Post_", "Arch_")) and "_beam" not in n:
            post_art(n, b)
        elif n == "Signpost_road":
            post_art(n, b, "Timber")
        elif n.startswith("Bench_"):
            bench_art(n, b)
        elif n.startswith("Bin_"):
            bin_art(n, b)
        elif n == "Rack":
            rack_art(n, b)
        elif n.startswith("Corral_"):
            corral_art(n, b)
        elif n == "Pylon_base":
            bm = bmesh.new()
            bevel_box(bm, mn, mx, 0.05, 2)
            finish(n, bm, "Pylon_Blue")
        elif n == "Pylon_pole":
            bm = bmesh.new()
            bevel_box(bm, mn, mx, 0.04, 2)
            finish(n, bm, "Pylon_Blue")
        elif n.startswith("decor_"):
            continue                                          # the decor boxes are drawn in extras() (signs, beds, lines, crowns, beams)
        else:
            raise ValueError(f"no art for {n}")


def paint():
    """The lines, decor_: the bays' lines from the model, the crossing to the doors, the store's yellow no-parking lines, the road's head."""
    acc = Acc("decor_Paint")
    w = acc.bm("Paint_White")
    for b in GB.boxes:
        if b["name"].startswith("decor_Line_"):
            quad(w, b["min"][0], b["max"][0], b["min"][2], b["max"][2], Y + 0.004)
    cx0, cx1, cz0, cz1 = G.LOT_CROSSWALK
    x = cx0
    while x < cx1 - 0.2:
        quad(w, x, x + 0.45, cz0, cz1, Y + 0.004)                # the crossing's stripes run toward the doors
        x += 0.9
    yel = acc.bm("Paint_Yellow")
    for z in (40.0, 41.1):
        quad(yel, -12.2, 12.2, z - 0.06, z + 0.06, Y + 0.004)
    rx0, rx1 = G.LOT_ROAD_GAP
    rc = (rx0 + rx1) / 2
    z = G.LOT["asphalt"][3] + 0.6
    while z < G.LOT["asphalt"][3] + 7.6:
        quad(yel, rc - 0.06, rc + 0.06, z, z + 1.2, Y + 0.004)    # the road's centre line starts in the gap
        z += 2.4
    for xe in (rx0 + 0.35, rx1 - 0.35):
        quad(w, xe - 0.06, xe + 0.06, G.LOT["asphalt"][3], G.LOT["asphalt"][3] + 8.0, Y + 0.004)
    acc.done()


def kerbs():
    """Low kerbs (decor_, 6 cm, walked over): along the asphalt's north edge before the store, round each planter hedge and each bed."""
    acc = Acc("decor_Kerbs")
    k = acc.bm("Kerb")
    x0, x1, z0, z1 = G.LOT["asphalt"]
    cube(k, (x0, Y, z0 - 0.05), (x1, Y + 0.06, z0 + 0.15))
    for a, b in G.LOT_ROW_HEDGES:
        bevel_box(k, (a - 0.3, Y, 54.2), (b + 0.3, Y + 0.12, 56.8), 0.03, 1)
    soil = acc.bm("Soil")
    for a, b in G.LOT_ROW_HEDGES:
        quad(soil, a - 0.2, b + 0.2, 54.3, 56.7, Y + 0.121)
    for bx0, bx1, bz0, bz1 in G.LOT_BEDS:
        for (a0, a1, c0, c1) in ((bx0 - 0.15, bx1 + 0.15, bz0 - 0.15, bz0), (bx0 - 0.15, bx1 + 0.15, bz1, bz1 + 0.15),
                                 (bx0 - 0.15, bx0, bz0, bz1), (bx1, bx1 + 0.15, bz0, bz1)):
            cube(k, (a0, Y, c0), (a1, Y + 0.08, c1))
    acc.done()


def row_trees_and_lamps():
    """Part 1's planter row: a pastel tree where each of its trees stood, a lamp where each of its lamps stood (inside the hedges)."""
    k = 0
    for x in (-56.0, -48.0, -30.0, -22.0, -4.0, 4.0, 22.0, 30.0, 48.0, 56.0):
        k += 1
        tree_art(f"Tree_row_{k:02d}", {"min": [x - 0.14, Y + 0.1, 55.36], "max": [x + 0.14, Y + 2.5, 55.64]}, seed=k + 20)
    for k, x in enumerate((-52.0, -26.0, 0.0, 26.0, 52.0), 1):
        lamp_post(f"Lamp_row_{k}", x, 55.5, Y + 0.1)


def signs():
    """The signs: the store's own (its logo on the pylon, PARKING, STOP, the cart sign), the arches' boards, the signpost and the stile."""
    lx, lz = -42.0, 91.5
    for nz, z in ((1, lz + 0.17), (-1, lz - 0.17)):                        # the pylon's logo both ways, on a disc over the pole
        disc_sign(f"decor_Pylon_logo_{'S' if nz > 0 else 'N'}", (lx, Y + 10.5, z), 2.5, (0, nz), store_uv("logo"))
    bm = bmesh.new()
    cyl(bm, (lx, Y + 10.5, lz - 0.15), (lx, Y + 10.5, lz + 0.15), 2.56, seg=40)
    finish("decor_Pylon_disc", bm, "Pylon_Blue", smooth=False)
    for b in GB.boxes:
        n = b["name"]
        if not n.startswith("Post_"):
            continue
        cx, cz, top = (b["min"][0] + b["max"][0]) / 2, (b["min"][2] + b["max"][2]) / 2, b["max"][1]
        if n.startswith("Post_park"):
            board(f"decor_{n}_Sign", (cx - 0.5, top - 0.5, cz + 0.04), (cx + 0.5, top, cz + 0.07), store_uv("parking"), [(0, 0, 1), (0, 0, -1)])
        elif n.startswith("Post_stop"):
            for nz in (1, -1):
                disc_sign(f"decor_{n}_Sign_{'S' if nz > 0 else 'N'}", (cx, top - 0.4, cz + nz * 0.06), 0.38, (0, nz), store_uv("stop"), sides=8,
                          rot=math.pi / 8)
        elif n == "Post_cart":
            board(f"decor_{n}_Sign", (cx - 0.6, top - 0.6, cz + 0.04), (cx + 0.6, top, cz + 0.07), store_uv("cart"), [(0, 0, 1), (0, 0, -1)])
    for side, xc, tin, tout in (("E", G.LOT["asphalt"][1] + 0.6, "MARKET", "PARKING LOT"),
                                ("W", G.LOT["asphalt"][0] - 0.6, "PLAYGROUND", "PARKING LOT")):
        za, zb = G.LOT_ARCH_Z
        beam = box_of(f"decor_Arch_{side}_beam")
        bm = bmesh.new()
        cube(bm, beam["min"], beam["max"])
        finish(f"decor_Arch_{side}_beam", bm, "Steel")
        sg = 1 if xc > 0 else -1                                   # the arch's outer side: +x in the east
        board(f"decor_Arch_{side}_sign_in", (xc - 0.04 if sg > 0 else xc, Y + 2.92, za + 0.5), (xc if sg > 0 else xc + 0.04, Y + 3.52, zb - 0.5),
              sign_uv(tin), [(-sg, 0, 0)])
        board(f"decor_Arch_{side}_sign_out", (xc if sg > 0 else xc - 0.04, Y + 2.92, za + 0.5), (xc + 0.04 if sg > 0 else xc, Y + 3.52, zb - 0.5),
              sign_uv(tout), [(sg, 0, 0)])
    b = box_of("decor_Signpost_road_Board")
    board("decor_Signpost_road_Board", b["min"], b["max"], sign_uv("TO THE FOREST"), [(0, 0, -1)])
    b = box_of("decor_Stile_Board")
    board("decor_Stile_Board", b["min"], b["max"], sign_uv("THE HILLS"), [(0, 0, -1)])


def stile():
    """The hills' stile: a post each side standing in the hedge's ends, a step and a rail across the gap (the step and the rail decor_)."""
    sx0, sx1 = G.LOT_STILE_GAP
    hz0, hz1, _ = G.LOT_HEDGE_S
    for k, x in enumerate((sx0 - 0.12, sx1 + 0.12), 1):
        bm = bmesh.new()
        cube(bm, (x - 0.07, Y, hz0 + 0.5), (x + 0.07, Y + 2.3, hz0 + 0.64))
        finish(f"Stile_post_{k}", bm, "Timber")
    acc = Acc("decor_Stile")
    s = box_of("decor_Stile_Step")
    bevel_box(acc.bm("Timber"), s["min"], s["max"], 0.02, 1)
    cube(acc.bm("Timber"), (sx0 - 0.05, Y + 1.05, hz0 + 0.52), (sx1 + 0.05, Y + 1.13, hz0 + 0.62))
    for x in (sx0 + 0.2, sx1 - 0.2):                               # the board for the stile's sign, on two thin legs
        cube(acc.bm("Timber"), (x - 0.03, Y, hz0 - 0.06), (x + 0.03, Y + 1.72, hz0 - 0.01))
    acc.done()
    b = box_of("decor_Signpost_road_Board")
    acc = Acc("decor_Signpost_road_arm")
    cube(acc.bm("Timber"), (b["min"][0] + 0.1, b["min"][1] - 0.1, b["min"][2] + 0.02), (b["max"][0] - 0.1, b["min"][1], b["max"][2] + 0.1))
    acc.done()


def joins():
    """A short paved way out under each arch, onto the lawn (decor_: the joins are walk links; the page loads the next scene)."""
    acc = Acc("decor_Ways")
    za, zb = G.LOT_ARCH_Z
    x0, x1 = G.LOT["asphalt"][:2]
    quad(acc.bm("Paving"), x1, x1 + 7.0, za + 0.1, zb - 0.1, Y - 0.02)
    quad(acc.bm("Paving"), x0 - 7.0, x0, za + 0.1, zb - 0.1, Y - 0.02)
    acc.done()


CARTS_LOOSE = [(32.1, 38.89, -67.3), (-20.32, 85.65, 15.1), (2.76, 65.57, 39.1), (29.91, 46.79, -14.8), (11.33, 60.8, 55.1), (-18.16, 88.56, 141.0),
               (-33.18, 43.53, 6.6), (-45.38, 37.58, -89.2), (2.08, 50.45, -51.8), (-16.51, 81.73, -15.2), (-25.8, 51.28, 168.6),
               (-25.75, 77.12, -50.1), (-18.74, 87.77, 89.7), (-31.57, 79.82, 40.9)]
CARTS_CORRAL = [(-34.0 + 0.28 * k, 33.2, 90.0) for k in range(7)]
CARTS_DOORS = [(-4.5 + 0.28 * k, 25.05, 0.0) for k in range(6)]
TYRES = [(-2.37, 92.33), (-0.1, 93.5), (3.0, 89.5), (36.1, 92.8), (36.4, 90.9)]
CONES = [(20.04, 96.15), (-4.8, 58.3), (17.5, 35.1), (-48.2, 30.9), (-49.0, 95.2)]


def cart(acc, x, z, yaw_deg):
    """A shopping cart (decor_: carts are pushed about, they never block): a wire basket, a handle, four castors."""
    a = math.radians(yaw_deg)
    ca, sa = math.cos(a), math.sin(a)

    def P(u, h, v):                                                # cart-local (u along, h up, v across) -> game
        return (x + u * ca + v * sa, Y + h, z - u * sa + v * ca)
    bl = acc.bm("Cart_Blue")
    st = acc.bm("Cart_Wire")
    corners = [(-0.38, -0.27), (0.36, -0.27), (0.36, 0.27), (-0.38, 0.27)]
    for h in (0.42, 0.98):
        pts = [P(u, h, v) for u, v in corners] + [P(*(corners[0][0], h, corners[0][1]))]
        tube(st, pts, 0.012, 5)
    for u, v in corners:
        tube(st, [P(u, 0.42, v), P(u, 0.98, v)], 0.012, 5)
    for u in (-0.2, 0.0, 0.2):
        tube(st, [P(u, 0.42, -0.27), P(u, 0.98, -0.27)], 0.008, 4)
        tube(st, [P(u, 0.42, 0.27), P(u, 0.98, 0.27)], 0.008, 4)
    tube(bl, [P(-0.46, 1.0, -0.26), P(-0.46, 1.0, 0.26)], 0.02, 8)  # the handle, blue plastic
    tube(st, [P(-0.38, 0.98, -0.25), P(-0.46, 1.0, -0.26)], 0.012, 5)
    tube(st, [P(-0.38, 0.98, 0.25), P(-0.46, 1.0, 0.26)], 0.012, 5)
    for u, v in corners:
        tube(st, [P(u * 0.9, 0.42, v * 0.9), P(u * 0.9, 0.08, v * 0.9)], 0.012, 5)
        cyl(acc.bm("Cart_Wire"), P(u * 0.9 - 0.04, 0.05, v * 0.9), P(u * 0.9 + 0.04, 0.05, v * 0.9), 0.05, seg=8)


def small_things():
    """Decor_: the carts, part 1's old tyres made flower planters, its traffic cones, flowers along the hedges and in the beds, shrubs."""
    solid = [b for b in GB.boxes if b["col"] and b["max"][1] > Y + 0.2 and not b["name"].startswith(("Ground_", "Edge_")) and "store" not in b["tags"]]

    def free(x, z, pad=0.6):                                       # part 1 left some of these inside a car or a hedge: those are not put back
        return not any(c["min"][0] - pad < x < c["max"][0] + pad and c["min"][2] - pad < z < c["max"][2] + pad for c in solid)
    acc = Acc("decor_Carts")
    for x, z, yaw in [c for c in CARTS_LOOSE if free(c[0], c[1])] + CARTS_CORRAL + CARTS_DOORS:
        cart(acc, x, z, yaw)
    acc.done()
    rng = np.random.default_rng(41)
    acc = Acc("decor_Tyre_planters")
    for k, (x, z) in enumerate([t for t in TYRES if free(*t)]):
        col = ["Leaf_Pink", "Leaf_Mint", "Leaf_Lilac"][k % 3]
        ring(acc.bm(col, True), (x, Y + 0.12, z), 0.30, 0.11, seg=18)
        cyl(acc.bm("Soil"), (x, Y + 0.02, z), (x, Y + 0.2, z), 0.22, seg=12)
        for i in range(7):
            a = 2 * math.pi * i / 7
            fx, fz = x + 0.12 * math.cos(a), z + 0.12 * math.sin(a)
            h = rng.uniform(0.38, 0.55)
            cube(acc.bm("Flower_Stem"), (fx - 0.01, Y + 0.2, fz - 0.01), (fx + 0.01, Y + h, fz + 0.01))
            ellipsoid(acc.bm(["Flower_Pink", "Flower_Yellow", "Flower_White"][(i + k) % 3], True), (fx, Y + h + 0.03, fz), 0.06, 0.04, 0.06, seg=8)
    acc.done()
    acc = Acc("decor_Cones")
    for x, z in [c for c in CONES if free(*c)]:
        cyl(acc.bm("Plastic_Coral", True), (x, Y + 0.04, z), (x, Y + 0.70, z), 0.17, 0.025, seg=14)
        cyl(acc.bm("Plastic_White", True), (x, Y + 0.38, z), (x, Y + 0.48, z), 0.105, 0.085, seg=14)
        cube(acc.bm("Plastic_Coral"), (x - 0.21, Y, z - 0.21), (x + 0.21, Y + 0.04, z + 0.21))
    acc.done()
    # flowers along the hedges (the lot's side of the back hedge, both sides of the planter row) and in the beds; shrubs in the beds
    keep = [e["pos"] for e in GB.empties]
    cols = [b for b in GB.boxes if b["col"] and not b["name"].startswith(("Ground_", "Hedge_", "Edge_")) and "store" not in b["tags"]]
    acc = Acc("decor_Flowers")
    stems = acc.bm("Flower_Stem")
    spots = []
    for _ in range(400):
        r = rng.random()
        if r < 0.4:
            x, z = rng.uniform(-62.0, 62.0), G.LOT_HEDGE_S[0] - 0.35
            if G.LOT_ROAD_GAP[0] - 0.5 < x < G.LOT_ROAD_GAP[1] + 0.5 or G.LOT_STILE_GAP[0] - 0.5 < x < G.LOT_STILE_GAP[1] + 0.5:
                continue
        elif r < 0.6:
            bx0, bx1, bz0, bz1 = G.LOT_BEDS[int(rng.integers(2))]
            x, z = rng.uniform(bx0 + 0.5, bx1 - 0.5), rng.uniform(bz0 + 0.5, bz1 - 0.5)
        else:
            a, b = G.LOT_ROW_HEDGES[int(rng.integers(5))]
            x, z = rng.uniform(a, b), (54.35 if rng.random() < 0.5 else 56.65)
        if any(math.hypot(x - p[0], z - p[2]) < 1.6 for p in keep):
            continue
        if any(c["min"][0] - 0.5 < x < c["max"][0] + 0.5 and c["min"][2] - 0.5 < z < c["max"][2] + 0.5 for c in cols):
            continue
        spots.append((x, z))
        if len(spots) >= 90:
            break
    for n, (x, z) in enumerate(spots):
        col = ["Flower_Pink", "Flower_Yellow", "Flower_White", "Flower_Lilac"][n % 4]
        y0 = Y + (0.12 if 54.0 < z < 57.0 else 0.0)
        for k in range(5):
            fx, fz = x + rng.uniform(-0.22, 0.22), z + rng.uniform(-0.12, 0.12)
            h = rng.uniform(0.22, 0.42)
            cube(stems, (fx - 0.01, y0, fz - 0.01), (fx + 0.01, y0 + h, fz + 0.01))
            ellipsoid(acc.bm(col, True), (fx, y0 + h + 0.03, fz), 0.06, 0.04, 0.06, seg=8)
    acc.done()
    acc = Acc("decor_Shrubs")
    trees = [(b["min"][0] + 0.2, b["min"][2] + 0.2) for b in GB.boxes if b["name"].startswith("Tree_") and not b["name"].endswith("_Crown")]
    n = 0
    for _ in range(200):
        bx0, bx1, bz0, bz1 = G.LOT_BEDS[n % 2]
        x, z = rng.uniform(bx0 + 1.0, bx1 - 1.0), rng.uniform(bz0 + 1.0, bz1 - 1.0)
        if any(math.hypot(x - tx, z - tz) < 2.4 for tx, tz in trees):
            continue
        r = rng.uniform(0.5, 0.8)
        ellipsoid(acc.bm("Shrub", True), (x, Y + r * 0.7, z), r, r * 0.8, r, seg=10)
        ellipsoid(acc.bm(["Flower_Pink", "Flower_Lilac", "Flower_White"][n % 3], True), (x + 0.2, Y + r * 1.25, z - 0.1), 0.12, 0.08, 0.12, seg=8)
        n += 1
        if n >= 22:
            break
    acc.done()


def extras():
    paint()
    kerbs()
    row_trees_and_lamps()
    signs()
    stile()
    joins()
    small_things()


# ---------------------------------------------------------------- the layout objects (from the model)
LAYOUT_PREFIX = ("COL_", "DoorLeaf_", "Link_", "Arrive_", "Spot_", "Zone_", "Marker_", "Play_")


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
    want = {"COL_" + b["name"] for b in GB.boxes if b["col"]} | {e["name"] for e in GB.empties}
    missing = want - {o.name for o in bpy.data.objects}
    assert not missing, f"layout objects missing: {sorted(missing)}"


# ---------------------------------------------------------------- the sky, the sun, the context
def setup_world(sky=True):
    """The renders' sky: the Overworld's clear-day backdrop (<work>/ctx/overworld_clear_day.webp, its middle column north) when it is there,
    else a plain blue; the bake's world is always the plain one (the AO bake does not see it)."""
    sc = bpy.context.scene
    w = bpy.data.worlds.new("Overworld")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    bg.inputs["Color"].default_value = (0.50, 0.68, 1.0, 1)
    bg.inputs["Strength"].default_value = 1.0
    pic = ctx_dir() / "overworld_clear_day.webp"
    if sky and pic.exists():
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(str(pic))
        tc = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Rotation"].default_value = (0, 0, math.radians(-90))    # the picture's middle column to Blender +Y (game north)
        nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
        nt.links.new(env.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = 0.9
    w.light_settings.distance = 2.0


def add_sun():
    if "Sun" in bpy.data.objects:
        return
    d = bpy.data.lights.new("Sun", "SUN")
    d.energy, d.color, d.angle = 3.2, (1.0, 0.96, 0.88), math.radians(2.0)
    ob = bpy.data.objects.new("Sun", d)
    ob.rotation_euler = (math.radians(38), 0, math.radians(-35))            # the clear-day sky's sun: south-west, 52 degrees up
    bpy.context.scene.collection.objects.link(ob)


def import_glb(path, coll_name, offset=(0.0, 0.0, 0.0)):
    """Import a GLB into its own collection (rays and renders only; never exported). `offset` is a game-frame translation of its roots."""
    path = Path(path)
    if not path.exists():
        print("CONTEXT missing", path.name)
        return None
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.data.objects if o not in before]
    coll = bpy.data.collections.get(coll_name) or bpy.data.collections.new(coll_name)
    if coll.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(coll)
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
        if o.parent is None:
            o.location = o.location + B(offset)
    print("CONTEXT", path.name, len(new), "objects")
    return coll


def add_context():
    """The store (world/L4.glb) and the two sets at their places in the lot (the greybox's ATTACH), for the bake's rays and the stills."""
    import_glb(ROOT / "world/L4.glb", "Context")
    for sid, (_sc, (x, y, z), _yaw) in G.ATTACH.items():
        p = ctx_dir() / f"{sid}.glb"
        import_glb(p, "Context", (x, y, z))


def drop_collection(name):
    c = bpy.data.collections.get(name)
    if c:
        for o in list(c.objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(c)


# ================================================================ build
def build_all():
    global ART, LAYOUT_C
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for d in (IMG_CACHE, MATS, TILES):
        d.clear()
    sc = bpy.context.scene
    ART, LAYOUT_C = (bpy.data.collections.new(n) for n in ("Art", "Layout"))
    for c in (ART, LAYOUT_C):
        sc.collection.children.link(c)
    make_materials()
    build_boxes()
    extras()
    build_layout()
    setup_world()
    add_sun()
    LAYOUT_C.hide_render = True
    tris = sum(len(p.vertices) - 2 for o in ART.objects for p in o.data.polygons)
    print(f"ART {SCENE}: {len(ART.objects)} art objects, about {tris} triangles")


def open_collections():
    global ART, LAYOUT_C
    ART, LAYOUT_C = (bpy.data.collections.get(n) for n in ("Art", "Layout"))
    MATS.clear()
    for m in bpy.data.materials:
        MATS[m.name] = m


def stage_layout():
    import export_scene
    export_scene.write(SCENE, ROOT / f"world/{SCENE}.json")
    want = json.loads(json.dumps(G.doc_of(GB)))
    have = json.loads((ROOT / f"world/{SCENE}.json").read_text())
    print("GATE export: world/parking_lot.json from the .blend", "EQUALS" if have == want else "DIFFERS FROM", "the greybox model's (--preview)")
    return have == want


def stage_check():
    """The layout check (check_layout.py) in the lot's floor frame (y - 9.6), as for every Overworld scene. The store's colliders are left to
    world/L4.glb, whose art they are; the rest must be covered by this scene's art."""
    import check_layout
    world = json.loads((ROOT / f"world/{SCENE}.json").read_text())
    parts = check_layout.blender_parts("Art")

    def sh(p):
        return [p[0], p[1] - Y, p[2]]
    parts = [{"name": p["name"], "min": sh(p["min"]), "max": sh(p["max"])} for p in parts]
    store = [c for c in world["colliders"] if c["s"] in STORE_COLS]
    rest = {**world, "colliders": [{"s": c["s"], "min": sh(c["min"]), "max": sh(c["max"])} for c in world["colliders"] if c["s"] not in STORE_COLS],
            "markers": [{**m, "position": sh(m["position"])} for m in world["markers"]]}
    consts = {"links": {l["door"]: {"arrive": sh(l["arrive"]), "at": [l["at"][0], l["at"][2]]} for l in world["links"]}}
    print(f"layout check: scene {SCENE}, {len(parts)} visible meshes, {len(rest['colliders'])} colliders of the lot's own (the floor frame, y - {Y})")
    print(f"PASS  STORE  {len(store)} colliders of the store (world/L4.json's, and the doors' block): their art is world/L4.glb's")
    bad = check_layout.report(check_layout.check(parts, rest, consts))
    print(f"CHECK_LAYOUT {SCENE} exit", 1 if bad else 0)
    return bad


# ---------------------------------------------------------------- bake: ambient occlusion
GROUND = ["Asphalt", "Paving", "Grass", "Hedge"]
# not baked: the lamps, the paint (narrower than a texel), the far lawn (open ground), the cars' glass and lamps, the flowers, and the carts
# (hundreds of thin wires: as islands they would take the standing map's texels from everything else; the page's sun and sky light them)
NOT_BAKED = ("Lamp_Emit", "Paint_White", "Paint_Yellow", "Grass_Far", "Car_Glass", "Car_Light", "Flower_Pink", "Flower_Yellow", "Flower_White",
             "Flower_Lilac", "Flower_Stem", "Cart_Blue", "Cart_Wire")
PAGES = [2048, 2048]
AO_DIST = [1.5, 0.8]
AO_INTENSITY = 1.0


def groups(exp):
    g0 = [m for m in GROUND if m in exp]
    g1 = [m for m in exp if m not in GROUND and m not in NOT_BAKED]
    return [g0, g1]


def cull_hidden(bm):
    """Drop the faces never seen: the undersides of things standing on the lot's floor, and the ground's sides below it."""
    bm.normal_update()
    bad = [f for f in bm.faces if f.normal.z < -0.9 and f.calc_center_median().z < Y + 0.005]
    bad += [f for f in bm.faces if abs(f.normal.z) < 0.1 and max(v.co.z for v in f.verts) < Y - 0.02]
    bmesh.ops.delete(bm, geom=list(set(bad)), context="FACES")


def make_export_objects():
    art = bpy.data.collections["Art"]
    drop_collection("Export")
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
        cull_hidden(tmp)
        me = bpy.data.meshes.new("tmp")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    out = {}
    for mname, bm in by_mat.items():
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
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces = 6, 4, 2
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
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / page, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    a3 = sum(area3d(o) for o in objs)
    au = sum(uv_area(o, "lightmap") for o in objs)
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
    path = str(work_dir() / "dn.exr")
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


def bake_ao(n, objs, S, dist):
    import time
    t0 = time.time()
    bpy.context.scene.world.light_settings.distance = dist
    img = bpy.data.images.new(f"AO_{n}", S, S, alpha=False, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    mats = [o.data.materials[0] for o in objs]
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
    for m in mats:
        nt = m.node_tree
        for nd in [nd for nd in nt.nodes if nd.name.startswith("BAKE_TARGET")]:
            nt.nodes.remove(nd)
    a = denoise_image(img, S)
    bpy.data.images.remove(img)
    ao = np.clip(a[..., :3].mean(axis=2), 0, 1)
    lit = ao[ao > 1e-4]
    pc = np.percentile(lit, [1, 10, 50, 90]) if lit.size else [1.0] * 4
    out = np.ones((S, S, 4), np.float32)
    out[..., 0] = out[..., 1] = out[..., 2] = ao
    png = bpy.data.images.new(f"AO_{n}_png", S, S, alpha=False)
    png.colorspace_settings.name = "Non-Color"
    png.pixels.foreach_set(out.ravel())
    png.filepath_raw = str(work_dir() / f"{SCENE}_{n}.png")
    png.file_format = "PNG"
    png.save()
    bpy.data.images.remove(png)
    for m in mats:
        m["aomap"] = f"world/lightmaps/{SCENE}_{n}.webp"
        m["aomap_intensity"] = AO_INTENSITY
    rep = {"size": S, "p1_p10_p50_p90": [round(float(v), 3) for v in pc], "samples": SAMPLES, "distance_m": dist,
           "device": bpy.context.scene.cycles.device, "seconds": round(time.time() - t0), "materials": [m.name for m in mats]}
    print(f"  AO map {n} baked", rep)
    return rep


def stage_bake():
    exp = make_export_objects()
    for c in ("Art", "Layout"):
        bpy.data.collections[c].hide_render = True
        bpy.data.collections[c].hide_viewport = True
    add_context()                                     # the store and the sets: in the rays, never baked or exported
    setup_world(sky=False)
    setup_cycles(SAMPLES, bake=True)
    report = {}
    for n, mats in enumerate(groups(exp)):
        objs = [exp[m] for m in mats]
        print(f"AO map {n}: {mats}")
        dens = lightmap_uv(objs, PAGES[n])
        report[n] = bake_ao(n, objs, PAGES[n], AO_DIST[n])
        report[n]["px_per_m"] = round(dens, 1)
    (work_dir() / "aomaps.json").write_text(json.dumps(report, indent=1))
    drop_collection("Context")
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Art"].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


# ---------------------------------------------------------------- privacy: the saved file and the GLB carry no paths, names or stamps
KEEP_PROPS = {"aomap", "aomap_intensity"}
SYS_KEEP = ("cycles", "eevee")


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private():
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
                    if kind == "objects" and st is idb and idb.name.startswith(LAYOUT_PREFIX):
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
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    bpy.data.collections["Art"].hide_viewport = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in exp.objects:
        o.hide_set(False)
        o.hide_render = False
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = work_dir() / f"{SCENE}_raw.glb"
    scrub_private()
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False, export_animations=False)
    print("EXPORTED", raw, raw.stat().st_size)
    bpy.data.collections["Art"].hide_viewport = False
    exp.hide_viewport = exp.hide_render = True
    save_blend()


# ---------------------------------------------------------------- the review stills
def look_cam(name, loc, target, fov_v=60.0, ortho=None):
    cam = bpy.data.cameras.new(name)
    cam.sensor_fit = "VERTICAL"
    if ortho:
        cam.type = "ORTHO"
        cam.ortho_scale = ortho
        cam.sensor_fit = "HORIZONTAL"
    else:
        cam.lens_unit = "FOV"
        cam.angle_y = math.radians(fov_v)
    cam.clip_start, cam.clip_end = 0.05, 1200
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


E = 1.55
VIEWS = {   # the same views for the stills and the before/after pairs: (camera, target, vertical fov)
    "arrival": ((-8.0, Y + E, 43.6), (-8.0, Y + 1.25, 23.6), 62.0),
    "west": ((-48.0, Y + E, 66.0), (-120.0, Y + 6.0, 61.0), 62.0),
    "south": ((0.0, Y + E, 30.5), (0.0, Y + 0.9, 98.0), 62.0),
    "wide": ((78.0, Y + 42.0, 132.0), (-6.0, Y, 44.0), 55.0),
    "detail": ((-21.5, Y + 1.6, 85.0), (-30.0, Y + 1.0, 97.5), 58.0),
    "bus": ((-46.0, Y + 0.15 + E, 47.4), (-88.0, Y + 8.0, 343.0), 55.0),          # on the bus station's platform, toward the skyline
    "doors": ((0.0, Y + E, 29.5), (-62.0, Y + 9.0, 360.0), 62.0),
    "overview": ((60.0, Y + 70.0, -70.0), (-55.0, Y, 250.0), 55.0),             # high over the store's back, out to the skyline
}
PLAN = ((0.0, Y + 150.0, 39.0), 150.0)                 # over the lot's middle, 150 m across


def render_settings(samples):
    sc = bpy.context.scene
    setup_cycles(samples)
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = arg("--noise", 0.04, float)
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    sc.view_settings.exposure = arg("--exposure", 0.0, float)


def shoot(key, cam, path, w=1920, h=1080, limit=450_000):
    sc = bpy.context.scene
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, arg("--scale", 100, int)
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 90
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    q = 90
    while path.stat().st_size > limit and q > 40:
        q -= 5
        sc.render.image_settings.quality = q
        bpy.data.images["Render Result"].save_render(str(path), scene=sc)
    strip_jpeg_comments(path)
    print("STILL", key, path.name, path.stat().st_size, "q", q)


def plan_cam(name):
    (x, y, z), span = PLAN
    cam = look_cam(name, (x, y, z), None, ortho=span)
    cam.rotation_euler = (0, 0, 0)
    return cam


def stage_render():
    STILLS.mkdir(parents=True, exist_ok=True)
    scrub_private()
    for c in ("Export", "Layout"):
        if c in bpy.data.collections:
            bpy.data.collections[c].hide_render = True
            bpy.data.collections[c].hide_viewport = True
    bpy.data.collections["Art"].hide_render = False
    add_context()
    import_glb(ROOT / "world/city_skyline.glb", "Context")
    setup_world()
    add_sun()
    render_settings(arg("--render-samples", 96, int))
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    which = arg("--only", "all")
    shots = {"1_arrival": "arrival", "2_wide": "wide", "3_detail": "detail"}
    for key, v in shots.items():
        if which in ("all", key):
            p, t, f = VIEWS[v]
            shoot(key, look_cam(key, p, t, f), STILLS / f"{key}.jpg")
    if which in ("all", "4_plan"):
        shoot("4_plan", plan_cam("4_plan"), STILLS / "4_plan.jpg", 1600, int(1600 * (PLAN[1] * 0.92) / PLAN[1]), 600_000)
    drop_collection("Context")


# ---------------------------------------------------------------- before and after, as the page draws them
def stage_compare():
    """The same views before and after, from the GLBs the page loads: before, world/L4.glb and the store's old Exterior.glb (<work>/ctx/
    Exterior_before.glb, the file as it was before tools/split_exterior.py) with its sky box lit as index.html lights it in the lot (x 3.5);
    after, world/L4.glb, world/parking_lot.glb and the two sets, under the Overworld's clear-day sky; and the Original's L4 after (world/L4.glb,
    world/parking_lot.glb and the split world/Exterior.glb: the Intern's street and its city, the sky box at its own dusk), which also shows
    the split file loads."""
    out = work_dir("compare")
    which = arg("--only", "all")
    for side in ("before", "after", "l4"):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        import_glb(ROOT / "world/L4.glb", "Context")
        if side == "before":
            import_glb(ctx_dir() / "Exterior_before.glb", "Context")
            for m in bpy.data.materials:
                if m.name.startswith("M_U_sky") and m.node_tree:
                    for nd in m.node_tree.nodes:
                        if nd.type == "BSDF_PRINCIPLED":
                            nd.inputs["Emission Strength"].default_value = nd.inputs["Emission Strength"].default_value * 3.5
                        elif nd.type == "EMISSION":
                            nd.inputs["Strength"].default_value = nd.inputs["Strength"].default_value * 3.5
            setup_world(sky=False)
        elif side == "l4":
            import_glb(ROOT / "world/parking_lot.glb", "Context")
            import_glb(ROOT / "world/city_skyline.glb", "Context")
            import_glb(ROOT / "world/Exterior.glb", "Context")
            setup_world(sky=False)
        else:
            import_glb(ROOT / "world/parking_lot.glb", "Context")
            import_glb(ROOT / "world/city_skyline.glb", "Context")
            for sid, (_sc, (x, y, z), _yaw) in G.ATTACH.items():
                import_glb(ctx_dir() / f"{sid}.glb", "Context", (x, y, z))
            setup_world()
        add_sun()
        render_settings(arg("--render-samples", 64, int))
        for key in ("arrival", "west", "south", "wide", "bus", "doors", "overview"):
            if which in ("all", key) and (side != "l4" or key in ("west", "wide", "bus", "doors")) and                     (side == "after" or key not in ("bus", "doors", "overview")) or (side == "l4" and key in ("bus", "doors")):
                p, t, f = VIEWS[key]
                shoot(f"{side}_{key}", look_cam(key, p, t, f), out / f"{side}_{key}.jpg", 1600, 900, 400_000)
        if side == "after" and which in ("all", "plan"):
            shoot("after_plan", plan_cam("plan"), out / "after_plan.jpg", 1400, int(1400 * 0.92), 500_000)


# ================================================================ main
if __name__ == "__main__":
    ST = set(STAGE.split(","))
    import traceback
    failed = []
    try:
        if ST & {"compare"}:
            stage_compare()
        else:
            if ST & {"art"}:
                build_all()
                save_blend()
            else:
                bpy.ops.wm.open_mainfile(filepath=str(BLEND))
                open_collections()
            if ST & {"layout", "art"}:
                if not stage_layout():
                    failed.append("export")
            if ST & {"check", "art"}:
                if stage_check():
                    failed.append("check")
            if ST & {"bake"}:
                stage_bake()
            if ST & {"export"}:
                stage_export()
            if ST & {"render"}:
                stage_render()
    except Exception:
        traceback.print_exc()
        failed.append("exception")
    print("OVERWORLD_LOT ALL DONE", "failed:", failed or "none")
    sys.exit(1 if failed else 0)
