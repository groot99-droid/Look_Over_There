"""Dresses the Overworld's sports courts and racetrack (`sports` and `racetrack`, through the playground's south gap), bakes their ambient
occlusion and exports world/<scene>.glb and world/<scene>.json. The method and the look are the playground's: tools/blender/build_overworld_play.py
is imported for its palette, shapes, layout objects, bake, export and privacy scrub, and this script adds the courts' and the track's own art.

Re-runnable, from the repo root. `--scene` takes sports, racetrack or both (sports,racetrack).

    python tools/blender/build_overworld_sports.py --stage textures     (the generated textures -> blender/textures/overworld_sports/, no Blender)
    blender -b --factory-startup --python tools/blender/build_overworld_sports.py -- --scene sports --stage art,bake,export,render [--samples 256]
        art:    the art, the balls and the layout objects; saves blender/scenes/<scene>.blend, writes world/<scene>.json, runs the layout check
        bake:   the ambient occlusion, two maps a scene (the ground, and everything standing), into <work>/<scene>_<n>.png
        export: <work>/<scene>_raw.glb (the static art merged by material, and the balls as their own nodes)
        render: docs/renders/<scene>/1_arrival.jpg, 2_wide.jpg, 3_detail.jpg and <work>/4_plan.jpg, <work>/5_<view>.jpg
    python tools/blender/pack_scene.py <scene> --work work/<scene>      (WebP AO maps and textures -> world/)

The layout is the greybox's: tools/blender/build_overworld_greybox.py (`sports()`, `racetrack()`, imported here), so no coordinate of the layout
is typed in here. Each collider's art is built inside its own box (a fence run gets posts, rails and chain-link; a tyre chunk gets its stacks; a
grandstand tier is a concrete step), so the layout check's cover and stray rules hold; what is added on top and can be walked through is decor_
(the courts' surfaces and lines, the track and its curbs, the seats, the hoops overhead).

The balls (two basketballs and a tennis ball) are the greybox's Play_<equipment>_<part> objects, each its own node with its origin on its centre
and its custom properties (equipment, part, axis, motion, radius_m, what) as glTF extras, so the page can throw and roll them. They are not baked
and have materials of their own (Play_*), in the `Play` collection, which the layout check skips.

Only the ambient occlusion is baked (as the playground: `aomap` and `aomap_intensity` on the second UV set; the page keeps the materials lit by
its sun and sky). The chain-link, the tennis net and the hoops' nets are alpha-masked textures, double-sided and not baked (they are hidden from
the bake, so they cast no AO either). The lamp and floodlight heads are `Lamp_Emit`, switched by the page. Every texture is generated here or by
build_overworld_play.py (numpy, own work); no third-party asset is used.

A game point (x, y, z) is Blender (x, -z, y).
"""
import json
import math
import sys
import types
from pathlib import Path

import numpy as np

try:
    import bpy
    import bmesh
    from mathutils import Matrix, Vector
except ImportError:                       # the textures stage runs in plain Python (numpy and Pillow)
    bpy = None

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import build_overworld_greybox as G      # noqa: E402  the layout model (pure Python)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


ALL = ["sports", "racetrack"]
STAGE = arg("--stage", "art")
TEXDIR = "blender/textures/overworld_sports/"


def play_module():
    """build_overworld_play.py: imported in Blender; in plain Python only its numpy part (the texture helpers) is run."""
    if bpy is not None:
        import build_overworld_play
        return build_overworld_play
    src = (ROOT / "tools/blender/build_overworld_play.py").read_text(encoding="utf-8").split("\nif bpy is None:")[0]
    m = types.ModuleType("overworld_play_helpers")
    m.__file__ = str(ROOT / "tools/blender/build_overworld_play.py")
    saved = sys.argv
    sys.argv = [saved[0]]
    try:
        exec(compile(src, "build_overworld_play.py", "exec"), m.__dict__)
    finally:
        sys.argv = saved
    return m


P = play_module()


# ================================================================ generated textures (plain Python)
def tex_asphalt(S=512):
    """2 m of fine asphalt: grey with light and dark stones."""
    rng = np.random.default_rng(21)
    v = 0.70 + 0.10 * (P.vnoise(S, S, rng, 5, 8) - 0.5)
    st = rng.random((S, S))
    v = v + 0.22 * P.blur((st > 0.965).astype(float), 1, 1) * 2 - 0.20 * P.blur((st < 0.03).astype(float), 1, 1) * 2
    return P.grey(v + 0.05 * (rng.random((S, S)) - 0.5))


def tex_acrylic(S=512):
    """A court's acrylic coat: nearly flat, a faint grain."""
    rng = np.random.default_rng(23)
    return P.grey(0.86 + 0.05 * (P.vnoise(S, S, rng, 6, 8) - 0.5) + 0.03 * (rng.random((S, S)) - 0.5))


def tex_concrete(S=512):
    rng = np.random.default_rng(25)
    v = 0.82 + 0.08 * (P.vnoise(S, S, rng, 5, 4) - 0.5) + 0.02 * (rng.random((S, S)) - 0.5)
    return P.grey(v - 0.25 * P.blur((rng.random((S, S)) > 0.996).astype(float), 1, 1) * 3)


def tex_shutter(S=512):
    """A roller shutter: twelve ribs a metre (the texture is 1 m)."""
    rng = np.random.default_rng(27)
    y = (np.arange(S)[:, None] + 0.5) / S
    rib = 0.5 + 0.5 * np.cos(2 * math.pi * y * 12) + 0.0 * np.arange(S)[None, :]
    return P.grey(0.72 + 0.16 * (rib - 0.5) + 0.04 * (P.vnoise(S, S, rng, 4, 4) - 0.5))


def mesh_alpha(S, n, w, diamond):
    """A wire mesh that repeats: n cells across the texture, wires w (a fraction of a cell) wide; diamonds for chain-link, squares for a net."""
    u = (np.arange(S) + 0.5) / S
    X, Y = np.meshgrid(u, u)
    a, b = ((X + Y) * n, (X - Y) * n) if diamond else (X * n, Y * n)
    fa, fb = np.abs(a - np.round(a)), np.abs(b - np.round(b))
    return np.clip(np.maximum(1 - fa / w, 1 - fb / w) * 3, 0, 1)


def tex_chainlink(S=512):
    """1 m of galvanised chain-link: 10 cm diamonds, wires about 8 mm (drawn a little heavy so it reads at a distance)."""
    al = mesh_alpha(S, 10, 0.07, True)
    rgb = np.full((S, S, 3), 0.80)
    return np.dstack([rgb, al])


def tex_netting(S=256):
    """0.5 m of knotted net: 11 square cells, the cord about 3 mm."""
    al = mesh_alpha(S, 11, 0.08, False)
    rgb = np.full((S, S, 3), 0.85)
    return np.dstack([rgb, al])


TEXTURES = {"asphalt.png": tex_asphalt, "acrylic.png": tex_acrylic, "concrete.png": tex_concrete, "shutter.png": tex_shutter,
            "chainlink.png": tex_chainlink, "netting.png": tex_netting}


def stage_textures():
    from PIL import Image
    d = ROOT / TEXDIR
    d.mkdir(parents=True, exist_ok=True)
    for n, fn in TEXTURES.items():
        a = fn()
        rgb = (P.srgb_encode(a[..., :3]) * 255 + 0.5).astype(np.uint8)
        if a.shape[2] == 4:
            im = Image.fromarray(np.dstack([rgb, (np.clip(a[..., 3], 0, 1) * 255 + 0.5).astype(np.uint8)]), "RGBA")
        else:
            im = Image.fromarray(rgb)
        im.save(d / n, optimize=True)
        print("TEXTURE", n, a.shape, f"linear mean {a[..., :3].mean():.3f} max {a[..., :3].max():.3f}", (d / n).stat().st_size)


if bpy is None:
    if STAGE == "textures":
        stage_textures()
    else:
        print("without Blender only --stage textures runs")
    sys.exit(0)


# ================================================================ Blender from here on
B, cube, bevel_box, cyl, ellipsoid, tube, quad, finish, Acc = P.B, P.cube, P.bevel_box, P.cyl, P.ellipsoid, P.tube, P.quad, P.finish, P.Acc


def scene_list():
    s = arg("--scene", "sports")
    return ALL if s == "all" else s.split(",")


# ---------------------------------------------------------------- materials (the playground's palette, and these)
SP_TEXTURED = {   # name: (texture, tint, roughness, metres a repeat)
    "Asphalt": ("asphalt.png", (0.30, 0.30, 0.31), 0.9, 2.0), "Concrete": ("concrete.png", (0.74, 0.73, 0.70), 0.85, 2.0),
    "Court_Green": ("acrylic.png", (0.20, 0.44, 0.26), 0.6, 2.0), "Court_Blue": ("acrylic.png", (0.13, 0.30, 0.60), 0.6, 2.0),
    "Court_Orange": ("acrylic.png", (0.74, 0.36, 0.17), 0.6, 2.0), "Shutter": ("shutter.png", (0.66, 0.68, 0.70), 0.5, 1.0),
}
SP_ALPHA = {"Chainlink": ("chainlink.png", (0.62, 0.64, 0.66), 1.0), "Net_Tennis": ("netting.png", (0.07, 0.07, 0.08), 0.5),
            "Net_Hoop": ("netting.png", (0.84, 0.84, 0.82), 0.3)}
SP_FLAT = {"Rail_Green": (0.10, 0.34, 0.20), "Hoop_Orange": (0.85, 0.32, 0.06), "Tyre_Black": (0.05, 0.05, 0.055), "Tyre_Red": (0.72, 0.10, 0.08),
           "Tyre_White": (0.80, 0.80, 0.78), "Curb_Red": (0.74, 0.10, 0.08), "Curb_White": (0.82, 0.82, 0.80), "Net_Band": (0.82, 0.82, 0.80),
           "Paint_Black": (0.04, 0.04, 0.045), "Lamp_Red_Off": (0.30, 0.03, 0.03), "Pad_Blue": (0.10, 0.24, 0.55)}
SP_PLAY = {"Play_Orange": (0.78, 0.30, 0.07), "Play_Tennis": (0.70, 0.80, 0.12)}
GBM = {"court_green": "Court_Green", "court_blue": "Court_Blue", "court_orange": "Court_Orange", "chainlink": "Chainlink", "net": "Net_Tennis",
       "rail_green": "Rail_Green", "concrete": "Concrete", "tyre": "Tyre_Black", "curb_red": "Curb_Red", "curb_white": "Curb_White",
       "asphalt": "Asphalt", "roof": "Steel"}
ALPHA = tuple(SP_ALPHA)


def tex_material(name, tex, tint, rough, tile):
    old = P.TEXDIR
    P.TEXDIR = TEXDIR
    try:
        return P.material(name, diff=tex, tint=tint, rough=rough, tile=tile)
    finally:
        P.TEXDIR = old


def alpha_material(name, tex, tint, tile):
    """An alpha-masked, double-sided material: the texture's alpha through a Round node (the glTF exporter writes alphaMode MASK, cutoff 0.5)."""
    m = tex_material(name, tex, tint, 0.6, tile)
    nt = m.node_tree
    img = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    rnd = nt.nodes.new("ShaderNodeMath")
    rnd.operation = "ROUND"
    nt.links.new(img.outputs["Alpha"], rnd.inputs[0])
    nt.links.new(rnd.outputs[0], bsdf.inputs["Alpha"])
    m.use_backface_culling = False
    for attr, val in (("blend_method", "CLIP"), ("surface_render_method", "DITHERED")):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    return m


def make_materials():
    P.make_materials()
    for n, (tx, tint, r, tile) in SP_TEXTURED.items():
        tex_material(n, tx, tint, r, tile)
    for n, (tx, tint, tile) in SP_ALPHA.items():
        alpha_material(n, tx, tint, tile)
    for n, c in SP_FLAT.items():
        P.material(n, color=c, rough=0.45 if n.startswith(("Tyre", "Curb")) else 0.6)
    for n, c in SP_PLAY.items():
        P.material(n, color=c, rough=0.5)


# ---------------------------------------------------------------- shapes
def up_faces(bm):
    for f in bm.faces:
        f.normal_update()
        if f.normal.z < 0:
            f.normal_flip()


def poly(bm, pts, y):
    """A flat face over game points (x, z) at height y, facing up."""
    vs = [bm.verts.new(B((x, y, z))) for x, z in pts]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.z < 0:
        f.normal_flip()
    return f


def arc_band(bm, cx, cz, r0, r1, a0, a1, y, n=None):
    """An annulus segment (r0 to r1, angles a0 to a1 in degrees, game x-z plane) at height y, facing up."""
    n = n or max(3, int(abs(a1 - a0) / 6))
    for i in range(n):
        t0, t1 = math.radians(a0 + (a1 - a0) * i / n), math.radians(a0 + (a1 - a0) * (i + 1) / n)
        poly(bm, [(cx + r0 * math.cos(t0), cz + r0 * math.sin(t0)), (cx + r1 * math.cos(t0), cz + r1 * math.sin(t0)),
                  (cx + r1 * math.cos(t1), cz + r1 * math.sin(t1)), (cx + r0 * math.cos(t1), cz + r0 * math.sin(t1))], y)


def disc(bm, cx, cz, r, y, n=32):
    poly(bm, [(cx + r * math.cos(2 * math.pi * k / n), cz + r * math.sin(2 * math.pi * k / n)) for k in range(n)], y)


def hexa(bm, corners):
    """A six-faced solid from eight game points: bottom (x0z0, x1z0, x1z1, x0z1) then top in the same order."""
    vs = [bm.verts.new(B(p)) for p in corners]
    fs = [bm.faces.new([vs[i] for i in f]) for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))]
    bmesh.ops.recalc_face_normals(bm, faces=fs)


def rot_box(bm, c, size, yaw, tilt=0.0):
    """A box of size (along, across, up) centred at game point c, turned yaw (radians, Blender z) and tilted (radians, about its across axis)."""
    m = Matrix.Translation(B(c)) @ Matrix.Rotation(yaw, 4, "Z") @ Matrix.Rotation(tilt, 4, "Y") @ Matrix.Diagonal((*size, 1.0))
    bmesh.ops.create_cube(bm, size=1.0, matrix=m)


def rect_holes(bm, x0, x1, z0, z1, holes, y):
    """A flat rectangle at height y with rectangular holes cut out (a grid on every edge, the cells inside a hole left out): what lies under
    a court or a path is never seen, so it takes no texels of the bake and does not count in the brightness table."""
    xs = sorted({x0, x1, *[min(max(v, x0), x1) for h in holes for v in h[:2]]})
    zs = sorted({z0, z1, *[min(max(v, z0), z1) for h in holes for v in h[2:]]})
    for i in range(len(xs) - 1):
        for j in range(len(zs) - 1):
            cx, cz = (xs[i] + xs[i + 1]) / 2, (zs[j] + zs[j + 1]) / 2
            if xs[i + 1] - xs[i] < 1e-6 or zs[j + 1] - zs[j] < 1e-6 or any(h[0] < cx < h[1] and h[2] < cz < h[3] for h in holes):
                continue
            quad(bm, xs[i], xs[i + 1], zs[j], zs[j + 1], y)


def rect_of(n):
    b = next(b for b in P.GB.boxes if b["name"] == n)
    return (b["min"][0], b["max"][0], b["min"][2], b["max"][2])


HOLES = {"decor_Tennis_Surround": ["decor_Tennis_Court"], "decor_Basket_Surround": ["decor_Basket_Court"],
         "decor_Basket_Court": ["decor_Basket_Key_N", "decor_Basket_Key_S"]}


def ground_art(n, b, mat):
    """The ground slab: its sides as the playground's, its top with holes under the courts' surrounds and the path (sports)."""
    if P.SCENE != "sports":
        return P.slab(n, b, mat)
    mn, mx = b["min"], b["max"]
    bm = bmesh.new()
    cube(bm, mn, mx)
    bm.normal_update()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if abs(f.normal.z) > 0.9], context="FACES")
    rect_holes(bm, mn[0], mx[0], mn[2], mx[2], [rect_of(h) for h in ("decor_Tennis_Surround", "decor_Basket_Surround", "decor_Path")], mx[1])
    return finish(n, bm, mat)


SURF_Y = {"decor_Path": 0.022, "decor_Tennis_Surround": 0.022, "decor_Basket_Surround": 0.022, "decor_Tennis_Court": 0.026,
          "decor_Basket_Court": 0.026, "decor_Basket_Key_N": 0.028, "decor_Basket_Key_S": 0.028, "decor_Pit_Lane": 0.016}
LINE_Y = 0.031


# ---------------------------------------------------------------- the courts
def chainlink_run(name, b):
    """A run of the tennis fence inside its collider: steel posts at the ends and every 3 m or less, top and bottom rails, chain-link between.
    The piece over the gate (it starts above head height) has rails and chain-link only."""
    mn, mx = b["min"], b["max"]
    ax = 0 if mx[0] - mn[0] >= mx[2] - mn[2] else 2
    c = (mn[2 - ax] + mx[2 - ax]) / 2
    a0, a1, y0, y1 = mn[ax], mx[ax], mn[1], mx[1]

    def pt(a, y):
        return (a, y, c) if ax == 0 else (c, y, a)
    acc = Acc(name)
    st = acc.bm("Steel", True)
    if y0 < 0.1:
        n = max(1, math.ceil((a1 - a0 - 0.08) / 3.0))
        for k in range(n + 1):
            a = a0 + 0.04 + (a1 - a0 - 0.08) * k / n
            cyl(st, pt(a, y0), pt(a, y1), 0.04, seg=10)
    for y in ((y0 + 0.05, y1 - 0.03) if y0 >= 0.1 else (0.12, y1 - 0.03, 1.8)):
        cyl(st, pt(a0, y), pt(a1, y), 0.025, seg=8)
    bm = acc.bm("Chainlink")
    ya, yb = (y0 + 0.05, y1 - 0.03) if y0 >= 0.1 else (0.04, y1 - 0.03)
    vs = [bm.verts.new(B(p)) for p in (pt(a0, ya), pt(a1, ya), pt(a1, yb), pt(a0, yb))]
    bm.faces.new(vs)
    acc.done()


def railing_run(name, b):
    """A run of the basketball court's low fence: green steel posts, top and bottom rails and pickets 12 cm apart."""
    mn, mx = b["min"], b["max"]
    ax = 0 if mx[0] - mn[0] >= mx[2] - mn[2] else 2
    c0, c1 = mn[2 - ax], mx[2 - ax]
    c = (c0 + c1) / 2
    a0, a1, h = mn[ax], mx[ax], mx[1]

    def box(a, b_, y, yy, w=None):
        lo, hi = (c - w / 2, c + w / 2) if w else (c0, c1)
        if ax == 0:
            cube(bm, (a, y, lo), (b_, yy, hi))
        else:
            cube(bm, (lo, y, a), (hi, yy, b_))
    bm = bmesh.new()
    n = max(1, math.ceil((a1 - a0 - 0.06) / 2.5))
    for k in range(n + 1):
        a = a0 + (a1 - a0 - 0.06) * k / n
        box(a, a + 0.06, 0.0, h)
    box(a0, a1, h - 0.05, h, 0.05)
    box(a0, a1, 0.1, 0.14, 0.04)
    a = a0 + 0.12
    while a + 0.02 < a1 - 0.08:
        box(a, a + 0.02, 0.14, h - 0.05, 0.02)
        a += 0.12
    finish(name, bm, "Rail_Green")


def net_art(name, b):
    """The tennis net between its posts: netting sagging from 1.07 m at the posts to 0.914 m in the middle, a white headband and centre strap."""
    mn, mx = b["min"], b["max"]
    x0, x1 = mn[0], mx[0]
    xc, hx = (x0 + x1) / 2, (x1 - x0) / 2
    top = lambda x: 0.914 + (1.07 - 0.914) * ((x - xc) / hx) ** 2
    n = 16
    xs = [x0 + (x1 - x0) * i / n for i in range(n + 1)]
    acc = Acc(name)
    bm = acc.bm("Net_Tennis")
    lo = [bm.verts.new(B((x, 0.04, 0.0))) for x in xs]
    hi = [bm.verts.new(B((x, top(x) - 0.05, 0.0))) for x in xs]
    for i in range(n):
        bm.faces.new((lo[i], lo[i + 1], hi[i + 1], hi[i]))
    band = acc.bm("Net_Band")
    for i in range(n):
        xa, xb = xs[i], xs[i + 1]
        hexa(band, [(xa, top(xa) - 0.06, -0.012), (xb, top(xb) - 0.06, -0.012), (xb, top(xb) - 0.06, 0.012), (xa, top(xa) - 0.06, 0.012),
                    (xa, top(xa), -0.012), (xb, top(xb), -0.012), (xb, top(xb), 0.012), (xa, top(xa), 0.012)])
    cube(band, (xc - 0.025, 0.04, -0.012), (xc + 0.025, 0.914 - 0.05, 0.012))
    cube(band, (x0, 0.02, -0.01), (x1, 0.05, 0.01))                   # the bottom cord
    acc.done()


def net_post(name, b):
    mn, mx = b["min"], b["max"]
    c = ((mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2)
    acc = Acc(name)
    cyl(acc.bm("Rail_Green", True), (c[0], 0.0, c[1]), (c[0], mx[1], c[1]), 0.05, seg=12)
    acc.done()


def umpire_chair(name, b):
    """The umpire's tall chair: a green steel frame with braces and a ladder, a timber platform and seat, a back and arms (inside its collider)."""
    mn, mx = b["min"], b["max"]
    x0, x1, z0, z1 = mn[0], mx[0], mn[2], mx[2]
    acc = Acc(name)
    st = acc.bm("Rail_Green", True)
    r = 0.025
    legs = [(x0 + 0.05, z0 + 0.05), (x1 - 0.05, z0 + 0.05), (x1 - 0.05, z1 - 0.05), (x0 + 0.05, z1 - 0.05)]
    for x, z in legs:
        cyl(st, (x, 0.0, z), (x, 1.75, z), r, seg=8)
    for y in (0.5, 1.1, 1.7):
        for i in range(4):
            (xa, za), (xb, zb) = legs[i], legs[(i + 1) % 4]
            cyl(st, (xa, y, za), (xb, y, zb), 0.018, seg=6)
    for y in (0.3, 0.8, 1.4):                                          # the ladder's rungs, on the side away from the court
        cyl(st, (x1 - 0.05, y, z0 + 0.05), (x1 - 0.05, y, z1 - 0.05), 0.016, seg=6)
    for z in (z0 + 0.08, z1 - 0.08):                                   # the arms and the back's posts
        cyl(st, (x1 - 0.1, 1.85, z), (x1 - 0.1, 2.55, z), 0.02, seg=6)
        cyl(st, (x0 + 0.15, 2.15, z), (x1 - 0.1, 2.15, z), 0.02, seg=6)
        cyl(st, (x0 + 0.15, 1.8, z), (x0 + 0.15, 2.15, z), 0.02, seg=6)
    wd = acc.bm("Timber")
    P.bevel_box(wd, (x0 + 0.04, 1.75, z0 + 0.04), (x1 - 0.04, 1.8, z1 - 0.04), 0.01, 1)
    P.bevel_box(wd, (x0 + 0.2, 1.8, z0 + 0.15), (x1 - 0.15, 1.86, z1 - 0.15), 0.01, 1)
    P.bevel_box(wd, (x1 - 0.14, 2.0, z0 + 0.12), (x1 - 0.08, 2.6, z1 - 0.12), 0.01, 1)
    P.bevel_box(wd, (x0, 1.25, z0 + 0.15), (x0 + 0.25, 1.29, z1 - 0.15), 0.01, 1)   # the footrest, on the court's side
    acc.done()


def pole_art(name, b):
    """A hoop's pole: a padded blue foot to 1.9 m, a steel pole above (the arm and the board are decor overhead)."""
    mn, mx = b["min"], b["max"]
    c = ((mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2)
    acc = Acc(name)
    P.bevel_box(acc.bm("Pad_Blue"), (mn[0], 0.0, mn[2]), (mx[0], 1.9, mx[2]), 0.04, 2)
    cyl(acc.bm("Steel", True), (c[0], 1.9, c[1]), (c[0], mx[1], c[1]), 0.1, seg=14)
    acc.done()


def hoop_art(name, b):
    mn, mx = b["min"], b["max"]
    kind = name.split("_")[3]
    sg = 1 if mn[2] > 0 else -1
    bx = (mn[0] + mx[0]) / 2
    acc = Acc(name)
    if kind == "Arm":
        st = acc.bm("Steel", True)
        zp, zf = sg * G.BAS_POLE_Z, sg * (G.BAS_BOARD_Z + 0.05)
        cyl(st, (bx, 3.35, zp), (bx, 3.35, zf), 0.05, seg=10)
        cyl(st, (bx, 2.85, zp - sg * 0.1), (bx, 3.35, (zp + zf) / 2), 0.035, seg=8)
        cyl(st, (bx - 0.35, 3.35, zf), (bx + 0.35, 3.35, zf), 0.035, seg=8)
    elif kind == "Board":
        P.bevel_box(acc.bm("Plastic_White"), mn, mx, 0.015, 1)
        front = mn[2] if sg > 0 else mx[2]                              # the face toward the court
        zz = (front - sg * 0.006, front - sg * 0.001)
        pr = acc.bm("Plastic_Red")
        za, zb = min(zz), max(zz)
        for (xa, xb, ya, yb) in ((bx - 0.295, bx + 0.295, 3.05, 3.1), (bx - 0.295, bx + 0.295, 3.45, 3.5),
                                  (bx - 0.295, bx - 0.245, 3.05, 3.5), (bx + 0.245, bx + 0.295, 3.05, 3.5),
                                  (mn[0], mx[0], mx[1] - 0.05, mx[1]), (mn[0], mx[0], mn[1], mn[1] + 0.05),
                                  (mn[0], mn[0] + 0.05, mn[1], mx[1]), (mx[0] - 0.05, mx[0], mn[1], mx[1])):
            cube(pr, (xa, ya, za), (xb, yb, zb))
    elif kind == "Ring":
        zh = (mn[2] + mx[2]) / 2
        ho = acc.bm("Hoop_Orange", True)
        tube(ho, [(bx + 0.225 * math.cos(2 * math.pi * k / 24), 3.05, zh + 0.225 * math.sin(2 * math.pi * k / 24)) for k in range(25)], 0.01, seg=6)
        cube(ho, (bx - 0.08, 3.0, min(zh + sg * 0.225, sg * G.BAS_BOARD_Z)), (bx + 0.08, 3.06, max(zh + sg * 0.225, sg * G.BAS_BOARD_Z)))
    elif kind == "Net":
        zh = (mn[2] + mx[2]) / 2
        bm = acc.bm("Net_Hoop")
        n = 16
        top = [bm.verts.new(B((bx + 0.222 * math.cos(2 * math.pi * k / n), 3.04, zh + 0.222 * math.sin(2 * math.pi * k / n)))) for k in range(n)]
        bot = [bm.verts.new(B((bx + 0.14 * math.cos(2 * math.pi * k / n), 2.64, zh + 0.14 * math.sin(2 * math.pi * k / n)))) for k in range(n)]
        for k in range(n):
            bm.faces.new((top[k], top[(k + 1) % n], bot[(k + 1) % n], bot[k]))
    acc.done()


def mast_art(name, b):
    mn, mx = b["min"], b["max"]
    c = ((mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2)
    r = (mx[0] - mn[0]) / 2
    acc = Acc(name)
    cyl(acc.bm("Steel", True), (c[0], 0.0, c[1]), (c[0], mx[1], c[1]), r, r * 0.55, seg=12)
    acc.done()


def flood_head(name, b):
    """A floodlight mast's head: a cross-bar and two lamps tilted down toward the court (Lamp_Emit lenses)."""
    mn, mx = b["min"], b["max"]
    x, z = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
    k = int(name.split("_")[2])
    tx, tz = (G.TEN_X, 0.0) if k <= 4 else (G.BAS_X, 0.0)
    d = B((tx, 0.0, tz)) - B((x, 0.0, z))
    yaw = math.atan2(d.y, d.x)
    acc = Acc(name)
    st = acc.bm("Steel")
    y = mn[1] + 0.3
    rot_box(st, (x, y - 0.2, z), (0.08, 1.3, 0.08), yaw)
    across = Vector((-math.sin(yaw), math.cos(yaw), 0.0))
    for s in (-0.38, 0.38):
        p = B((x, y, z)) + across * s
        g = (p.x, p.z, -p.y)
        rot_box(st, g, (0.18, 0.55, 0.42), yaw, math.radians(35))
        fwd = Vector((math.cos(yaw) * math.cos(math.radians(35)), math.sin(yaw) * math.cos(math.radians(35)), -math.sin(math.radians(35))))
        q = p + fwd * 0.095
        rot_box(acc.bm("Lamp_Emit"), (q.x, q.z, -q.y), (0.02, 0.48, 0.35), yaw, math.radians(35))
    acc.done()


def court_lines():
    """The tennis and basketball lines (Paint_White, not baked: narrower than a texel)."""
    acc = Acc("decor_court_lines")
    bm = acc.bm("Paint_White")
    y = LINE_Y
    cx, hl, hw, sw = G.TEN_X, G.TEN_L / 2, G.TEN_W / 2, G.TEN_SW / 2
    for sg in (-1, 1):
        quad(bm, cx - hw, cx + hw, min(sg * hl, sg * (hl - 0.1)), max(sg * hl, sg * (hl - 0.1)), y)              # baselines
        quad(bm, cx - sw, cx + sw, min(sg * 6.4, sg * 6.35), max(sg * 6.4, sg * 6.35), y)                          # service lines
        quad(bm, cx - 0.025, cx + 0.025, min(sg * (hl - 0.1), sg * (hl - 0.2)), max(sg * (hl - 0.1), sg * (hl - 0.2)), y)   # centre marks
        for xs in (hw, sw):                                                                                         # doubles and singles sidelines
            quad(bm, min(cx + sg * xs, cx + sg * (xs - 0.05)), max(cx + sg * xs, cx + sg * (xs - 0.05)), -hl, hl, y)
    quad(bm, cx - 0.025, cx + 0.025, -6.35, 6.35, y)                                                               # the centre service line
    bx, L, W = G.BAS_X, G.BAS_L / 2, G.BAS_W / 2
    w = 0.05
    for sg in (-1, 1):
        quad(bm, bx - W, bx + W, min(sg * L, sg * (L - w)), max(sg * L, sg * (L - w)), y)                           # baselines
        quad(bm, min(bx + sg * W, bx + sg * (W - w)), max(bx + sg * W, bx + sg * (W - w)), -L, L, y)               # sidelines
        kz = sg * (L - 5.8)
        for xs in (-2.45, 2.45 - w):                                                                               # the key
            quad(bm, bx + xs, bx + xs + w, min(sg * L, kz), max(sg * L, kz), y)
        quad(bm, bx - 2.45, bx + 2.45, min(kz, kz + sg * w), max(kz, kz + sg * w), y)
        arc_band(bm, bx, kz, 1.75, 1.8, 0, 360, y, 48)                                                               # the free-throw circle
        hz = sg * G.BAS_HOOP_Z                                                                                      # the three-point line
        dz = math.sqrt(6.75 ** 2 - 6.6 ** 2)
        a = math.degrees(math.atan2(dz, 6.6))
        lo, hi = (a, 180 - a) if sg < 0 else (180 + a, 360 - a)
        arc_band(bm, bx, hz, 6.70, 6.75, lo, hi, y, 60)
        for xs in (-6.6, 6.6 - w):
            quad(bm, bx + xs, bx + xs + w, min(sg * L, hz - sg * dz), max(sg * L, hz - sg * dz), y)
        arc_band(bm, bx, hz, 1.25, 1.30, 0 if sg < 0 else 180, 180 if sg < 0 else 360, y, 24)                        # the restricted area
    quad(bm, bx - W, bx + W, -w / 2, w / 2, y)                                                                     # the centre line and circle
    arc_band(bm, bx, 0.0, 1.75, 1.8, 0, 360, y, 48)
    acc.done()


# ---------------------------------------------------------------- the racetrack
TYRES = {}


def tyre_stack(bm, x, z):
    """Three tyres stacked (0.78 m): a grooved round wall, the top tyre's tread and its hole down to a floor."""
    H = [0.0, 0.13, 0.26, 0.39, 0.52, 0.65, 0.78]
    R = [0.27, 0.30, 0.265, 0.30, 0.265, 0.30, 0.27]
    n = 8
    ring = lambda r, y: [bm.verts.new(B((x + r * math.cos(2 * math.pi * (k + 0.5) / n), y, z + r * math.sin(2 * math.pi * (k + 0.5) / n))))
                         for k in range(n)]
    rings = [ring(r, h) for r, h in zip(R, H)]
    hole_t, hole_b = ring(0.14, 0.78), ring(0.14, 0.64)
    fs = []
    for a, b_ in zip(rings, rings[1:]):
        for k in range(n):
            fs.append(bm.faces.new((a[k], a[(k + 1) % n], b_[(k + 1) % n], b_[k])))
    for k in range(n):
        fs.append(bm.faces.new((rings[-1][k], rings[-1][(k + 1) % n], hole_t[(k + 1) % n], hole_t[k])))
        fs.append(bm.faces.new((hole_t[k], hole_t[(k + 1) % n], hole_b[(k + 1) % n], hole_b[k])))
    fs.append(bm.faces.new(hole_b[::-1]))
    bmesh.ops.recalc_face_normals(bm, faces=fs)


def tyre_art(name):
    """One chunk's stacks, one colour a chunk (one object, so its box is the collider's): red, black, white, black along the bend."""
    k = int(name.split("_")[-1]) - 1
    m = ("Tyre_Red", "Tyre_Black", "Tyre_White", "Tyre_Black")[k % 4]
    bm = bmesh.new()
    for x, z, row, col in TYRES[name]:
        tyre_stack(bm, x, z)
    finish(name, bm, m, smooth=True)


def track_art():
    """The asphalt loop (decor: you walk and drive on it), finer than the greybox's, with a white line along each edge."""
    pts = G.track_centre(36)
    hw = G.RT_W / 2
    bm = bmesh.new()
    v, f = G.ribbon(pts, -hw, hw, 0.012)
    vs = [bm.verts.new(B(p)) for p in v]
    for fc in f:
        bm.faces.new([vs[i] for i in fc])
    up_faces(bm)
    finish("decor_Track", bm, "Asphalt")
    acc = Acc("decor_track_lines")
    pw = acc.bm("Paint_White")
    for d0, d1 in ((-hw + 0.25, -hw + 0.37), (hw - 0.37, hw - 0.25)):
        v, f = G.ribbon(pts, d0, d1, 0.02)
        vs = [pw.verts.new(B(p)) for p in v]
        for fc in f:
            pw.faces.new([vs[i] for i in fc])
    up_faces(pw)
    # the start/finish line: two rows of 0.5 m checks across the track; the grid: ten painted slots behind it, staggered
    x, zc = G.RT_START_X, -(G.RT_CZ + G.RT_R)
    pb = acc.bm("Paint_Black")
    for i in range(2):
        for j in range(16):
            quad(pw if (i + j) % 2 == 0 else pb, x - 0.5 + 0.5 * i, x + 0.5 * i, zc - hw + 0.5 * j, zc - hw + 0.5 * (j + 1), 0.022)
    up_faces(pb)
    for k in range(10):
        gx, gz = x - 4.0 - 4.5 * k, zc + (1.8 if k % 2 else -1.8)
        quad(pw, gx - 0.1, gx, gz - 0.8, gz + 0.8, 0.022)
        for s in (-0.8, 0.7):
            quad(pw, gx - 1.3, gx, gz + s, gz + s + 0.1, 0.022)
    up_faces(pw)
    # the pit lane: its edge line on the track side and a yellow box in front of each garage
    zi = -(G.RT_CZ + G.RT_R - hw)
    quad(pw, -36.0, 36.0, zi + 0.95, zi + 1.07, 0.024)
    py = acc.bm("Paint_Yellow")
    for xc in (-20.0, -12.0, -4.0, 4.0, 12.0, 20.0):
        for (a0, a1, b0, b1) in ((xc - 2.0, xc + 2.0, zi + 3.4, zi + 3.48), (xc - 2.0, xc + 2.0, zi + 6.52, zi + 6.6),
                                 (xc - 2.0, xc - 1.92, zi + 3.4, zi + 6.6), (xc + 1.92, xc + 2.0, zi + 3.4, zi + 6.6)):
            quad(py, a0, a1, b0, b1, 0.024)
    up_faces(py)
    acc.done()


def curbs_art():
    """Red and white curbs on the inside and outside of each bend: a low ridge (5 cm) that rises from the track's edge."""
    for col in ("curb_red", "curb_white"):
        bm = bmesh.new()
        for inner in (True, False):
            for key, (cx, cz), r0, r1, a0, a1, c in G.curb_segments(inner):
                if c != col:
                    continue
                edge, far = (r1, r0) if inner else (r0, r1)                  # the side on the track, the side on the grass
                rs = [edge, edge + (far - edge) * 0.35, far]
                ys = [0.014, 0.05, 0.03]
                n = 3
                for i in range(n):
                    t0, t1 = math.radians(a0 + (a1 - a0) * i / n), math.radians(a0 + (a1 - a0) * (i + 1) / n)
                    for j in range(2):
                        pts = [(rs[j], ys[j], t0), (rs[j + 1], ys[j + 1], t0), (rs[j + 1], ys[j + 1], t1), (rs[j], ys[j], t1)]
                        vs = [bm.verts.new(B((cx + r * math.cos(t), y, cz + r * math.sin(t)))) for r, y, t in pts]
                        bm.faces.new(vs)
        up_faces(bm)
        finish(f"decor_Curbs_{col.split('_')[1].capitalize()}", bm, GBM[col])


def pit_entries():
    for m in P.GB.meshes:
        if m["name"].startswith("decor_Pit_"):
            bm = bmesh.new()
            vs = [bm.verts.new(B((p[0], 0.016, p[2]))) for p in m["verts"]]
            for fc in m["faces"]:
                bm.faces.new([vs[i] for i in fc])
            up_faces(bm)
            finish(m["name"], bm, "Asphalt")


def seats_art(name, b):
    """A row of plastic seats at the back of a tier, facing the track (decor: on the tier's step)."""
    mn, mx = b["min"], b["max"]
    y0, z0 = mn[1], mn[2]
    acc = Acc(name)
    i = int(name.split("_")[-1])
    x = mn[0] + 0.25
    k = 0
    while x + 0.22 <= mx[0]:
        m = "Plastic_White" if i == 4 else "Plastic_Blue"
        bm = acc.bm(m)
        cube(bm, (x - 0.04, y0, z0 + 0.2), (x + 0.04, y0 + 0.36, z0 + 0.3))
        cube(bm, (x - 0.21, y0 + 0.36, z0 + 0.06), (x + 0.21, y0 + 0.41, z0 + 0.45))
        cube(bm, (x - 0.21, y0 + 0.41, z0 + 0.03), (x + 0.21, y0 + 0.8, z0 + 0.07))
        x += 0.5
        k += 1
    acc.done()


def roof_art(name, b):
    mn, mx = b["min"], b["max"]
    acc = Acc(name)
    P.bevel_box(acc.bm("Steel"), mn, mx, 0.02, 1)
    acc.done()
    st = Acc("decor_stand_trusses")                                       # cantilevers under the roof, every 4 m, braced from the back wall
    bm = st.bm("Steel", True)
    x = mn[0] + 0.6
    zb, zf = mn[2] + 0.4, mx[2] - 0.4
    while x <= mx[0] - 0.5:
        cyl(bm, (x, mn[1] - 0.12, zb), (x, mn[1] - 0.12, zf), 0.06, seg=8)
        cyl(bm, (x, 3.1, zb + 0.05), (x, mn[1] - 0.15, zb + (zf - zb) * 0.55), 0.05, seg=8)
        x += 4.0
    st.done()


def pit_wall_art(name, b):
    mn, mx = b["min"], b["max"]
    acc = Acc(name)
    P.bevel_box(acc.bm("Concrete"), mn, mx, 0.02, 1)
    x = mn[0]
    k = 0
    while x < mx[0] - 0.01:                                                # red and white panels on the track's face
        cube(acc.bm("Curb_Red" if k % 2 == 0 else "Curb_White"), (x, 0.1, mn[2] - 0.006), (min(x + 2.0, mx[0]), 0.9, mn[2]))
        x += 2.0
        k += 1
    acc.done()


def garages_art(name, b):
    mn, mx = b["min"], b["max"]
    acc = Acc(name)
    P.bevel_box(acc.bm("Concrete"), mn, mx, 0.03, 1)
    cube(acc.bm("Curb_Red"), (mn[0], mx[1] - 0.35, mn[2] - 0.006), (mx[0], mx[1] - 0.1, mn[2]))          # a red band along the front
    acc.done()
    rf = Acc("decor_garage_roof")
    P.bevel_box(rf.bm("Steel"), (mn[0] - 0.3, mx[1], mn[2] - 1.2), (mx[0] + 0.3, mx[1] + 0.12, mx[2] + 0.2), 0.02, 1)
    rf.done()


def shutter_art(name, b):
    mn, mx = b["min"], b["max"]
    acc = Acc(name)
    bm = acc.bm("Shutter")
    cube(bm, mn, mx)
    bm.normal_update()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.normal.y < -0.9], context="FACES")                # the back is in the wall
    cube(acc.bm("Steel"), (mn[0], mx[1], mn[2] - 0.04), (mx[0], mx[1] + 0.25, mx[2]))                     # the shutter's box over it
    acc.done()


def gantry_beam(name, b):
    """A box truss over the track: four chords and diagonals."""
    mn, mx = b["min"], b["max"]
    acc = Acc(name)
    bm = acc.bm("Steel", True)
    xs, ys = (mn[0] + 0.04, mx[0] - 0.04), (mn[1] + 0.04, mx[1] - 0.04)
    for x in xs:
        for y in ys:
            cyl(bm, (x, y, mn[2]), (x, y, mx[2]), 0.04, seg=8)
    n = max(2, int((mx[2] - mn[2]) / 0.8))
    for i in range(n):
        za, zb = mn[2] + (mx[2] - mn[2]) * i / n, mn[2] + (mx[2] - mn[2]) * (i + 1) / n
        for x in xs:
            cyl(bm, (x, ys[0], za), (x, ys[1], zb) if i % 2 == 0 else (x, ys[1], za), 0.025, seg=6)
            cyl(bm, (x, ys[1], zb if i % 2 == 0 else za), (x, ys[0], zb), 0.025, seg=6)
    acc.done()


def gantry_lights(name, b):
    """The start lights, off: a black housing with five red lenses facing the grid (west)."""
    mn, mx = b["min"], b["max"]
    acc = Acc(name)
    P.bevel_box(acc.bm("Tyre_Black"), mn, mx, 0.02, 1)
    for k in range(5):
        z = mn[2] + (mx[2] - mn[2]) * (k + 0.5) / 5
        cyl(acc.bm("Lamp_Red_Off", True), (mn[0] - 0.015, (mn[1] + mx[1]) / 2, z), (mn[0], (mn[1] + mx[1]) / 2, z), 0.15, seg=14)
    cube(acc.bm("Steel"), ((mn[0] + mx[0]) / 2 - 0.03, mx[1], (mn[2] + mx[2]) / 2 - 0.03), ((mn[0] + mx[0]) / 2 + 0.03, 5.6, (mn[2] + mx[2]) / 2 + 0.03))
    acc.done()


# ---------------------------------------------------------------- the balls (moving parts)
def ball_part(p):
    nm = p["name"]
    eq = p["props"]["equipment"]
    piv = p["pivot"]
    r = p["props"]["radius_m"]
    bms = {}

    def bm_of(m):
        return bms.setdefault(m, bmesh.new())
    if eq == "basketball":
        ellipsoid(bm_of("Play_Orange"), piv, r, r, r, seg=20)
        x, y, z = piv
        rr = r * 1.004
        for ring in ([(x + rr * math.cos(t), y, z + rr * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 33)],
                     [(x + rr * math.cos(t), y + rr * math.sin(t), z) for t in np.linspace(0, 2 * math.pi, 33)],
                     [(x, y + rr * math.sin(t), z + rr * math.cos(t)) for t in np.linspace(0, 2 * math.pi, 33)]):
            tube(bm_of("Play_Black"), ring, 0.004, seg=4)
    else:
        ellipsoid(bm_of("Play_Tennis"), piv, r, r, r, seg=14)
    me = bpy.data.meshes.new(nm)
    big = bmesh.new()
    mlist = []
    for m, bm in bms.items():
        mi = len(mlist)
        mlist.append(m)
        for f in bm.faces:
            f.material_index = mi
            f.smooth = True
        tmp = bpy.data.meshes.new("tmp")
        bm.to_mesh(tmp)
        bm.free()
        big.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
    big.transform(Matrix.Translation(-B(piv)))
    if not big.loops.layers.uv.get("UVMap"):
        big.loops.layers.uv.new("UVMap")
    big.to_mesh(me)
    big.free()
    for m in mlist:
        me.materials.append(P.MATS[m])
    ob = bpy.data.objects.new(nm, me)
    ob.location = B(piv)
    for k, v in p["props"].items():
        ob[k] = v
    ob["pivot"] = [round(v, 3) for v in piv]
    P.PLAYC.objects.link(ob)
    return ob


# ---------------------------------------------------------------- the dressing, from the greybox's boxes
def build_boxes():
    for b in P.GB.boxes:
        if b.get("zone") or b.get("ctx") or not b.get("art", True):
            continue
        n, m = b["name"], b["mat"]
        mat = GBM.get(m) or P.GB_MAT.get(m, "Plastic_White")
        mn, mx = b["min"], b["max"]
        if n.startswith("Ground_"):
            ground_art(n, b, mat)
        elif n.startswith("Hedge_"):
            bm = bmesh.new()
            bevel_box(bm, mn, mx, 0.12, 2)
            finish(n, bm, "Hedge")
        elif n.startswith("Bench_"):
            P.bench_art(n, b)
        elif n.startswith("Bin_"):
            P.bin_art(n, b)
        elif n.startswith("decor_Lamp_") and n.endswith("_Head"):
            P.lamp_head(n, b)
        elif n.startswith("Flood_"):
            mast_art(n, b)
        elif n.startswith("decor_Flood_"):
            flood_head(n, b)
        elif n.startswith("Tennis_Fence_"):
            chainlink_run(n, b)
        elif n.startswith("Basket_Fence_"):
            railing_run(n, b)
        elif n.startswith("Tennis_Net_Post_"):
            net_post(n, b)
        elif n == "Tennis_Net":
            net_art(n, b)
        elif n == "Umpire_Chair":
            umpire_chair(n, b)
        elif n.startswith("Hoop_") and n.endswith("_Pole"):
            pole_art(n, b)
        elif n.startswith("decor_Hoop_"):
            hoop_art(n, b)
        elif n == "decor_Basket_Circle":
            bm = bmesh.new()
            disc(bm, (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2, (mx[0] - mn[0]) / 2, 0.028, 48)
            finish(n, bm, mat)
        elif n.startswith("Tyres_"):
            tyre_art(n)
        elif n.startswith("Step_stand_") or n.startswith(("Stand_Back", "Stand_Side", "Stand_Wall")):
            bm = bmesh.new()
            bevel_box(bm, mn, mx, 0.02, 1)
            finish(n, bm, "Concrete")
        elif n.startswith("decor_Stand_Seats_"):
            seats_art(n, b)
        elif n == "Stand_Roof":
            roof_art(n, b)
        elif n == "Pit_Wall":
            pit_wall_art(n, b)
        elif n == "Pit_Garages":
            garages_art(n, b)
        elif n.startswith("decor_Pit_Shutter_"):
            shutter_art(n, b)
        elif n == "decor_Pit_Sign":
            P.sign_obj(n, mn, mx, "PITS", (0, 0, -1))
        elif n.startswith("Gantry_Pillar_"):
            bm = bmesh.new()
            bevel_box(bm, mn, mx, 0.03, 1)
            finish(n, bm, "Steel")
        elif n == "decor_Gantry_Beam":
            gantry_beam(n, b)
        elif n == "decor_Gantry_Sign":
            P.sign_obj(n, mn, mx, "FINISH", (-1, 0, 0))
        elif n == "decor_Gantry_Lights":
            gantry_lights(n, b)
        elif n.startswith("decor_") and (mx[1] - mn[1]) < 0.03:
            bm = bmesh.new()
            rect_holes(bm, mn[0], mx[0], mn[2], mx[2], [rect_of(h) for h in HOLES.get(n, [])], SURF_Y.get(n, mx[1] + 0.012))
            finish(n, bm, mat)
        else:
            bm = bmesh.new()
            P.shape_box(bm, mn, mx, 0.02)
            finish(n, bm, mat, smooth=P.thin_axis(mn, mx) is not None)
    for p in P.GB.parts:
        ball_part(p)


def extras():
    """What the greybox does not have: the arches over the gaps, the lines, the track and its curbs, a few signs."""
    if P.SCENE == "sports":
        P.arch_x("N", -G.SPZ - 0.6, "PLAYGROUND", "SPORTS")
        P.arch_x("S", G.SPZ + 0.6, "RACETRACK", "SPORTS")
        court_lines()
        fx1 = G.TEN_X + G.TEN_FX
        P.sign_obj("decor_Tennis_Sign", (fx1 + 0.045, 2.45, G.TEN_GATE[0] - 0.5), (fx1 + 0.075, 2.95, G.TEN_GATE[1] + 0.5), "TENNIS", (1, 0, 0))
        P.sign_obj("decor_Tennis_Sign_In", (fx1 - 0.075, 2.45, G.TEN_GATE[0] - 0.5), (fx1 - 0.045, 2.95, G.TEN_GATE[1] + 0.5), "TENNIS", (-1, 0, 0))
        x0 = G.BAS_FENCE[0]
        P.sign_obj("decor_Basket_Sign", (x0 - 0.075, 0.3, G.BAS_GATE[0] - 2.6), (x0 - 0.045, 0.85, G.BAS_GATE[0] - 0.4), "BASKETBALL", (-1, 0, 0))
        P.sign_obj("decor_Basket_Sign_In", (x0 + 0.045, 0.3, G.BAS_GATE[0] - 2.6), (x0 + 0.075, 0.85, G.BAS_GATE[0] - 0.4), "BASKETBALL", (1, 0, 0))
    else:
        P.arch_x("N", -G.RT_Z - 0.6, "SPORTS", "RACETRACK", x0=-38.0)
        for m in P.GB.meshes:
            assert m["name"] in ("decor_Track", "decor_Curbs_Red", "decor_Curbs_White", "decor_Pit_Entry", "decor_Pit_Exit"), m["name"]
        track_art()
        curbs_art()
        pit_entries()
        x = G.RT_START_X
        P.sign_obj("decor_Gantry_Sign_E", (x + 0.2, 5.65, -36.0), (x + 0.26, 6.35, -30.0), "FINISH", (1, 0, 0))
        P.sign_obj("decor_Stand_Sign", (-22.0, 4.0, -46.85), (-10.0, 4.55, -46.8), "RACETRACK", (0, 0, -1))


# ================================================================ build
def build_all():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for d in (P.IMG_CACHE, P.MATS, P.TILES):
        d.clear()
    sc = bpy.context.scene
    P.ART, P.PLAYC, P.LAYOUT_C = (bpy.data.collections.new(n) for n in ("Art", "Play", "Layout"))
    for c in (P.ART, P.PLAYC, P.LAYOUT_C):
        sc.collection.children.link(c)
    TYRES.clear()
    TYRES.update(dict(G.tyre_chunks()))
    make_materials()
    build_boxes()
    extras()
    P.build_layout()
    P.setup_world()
    P.add_sun()
    P.LAYOUT_C.hide_render = True
    tris = sum(len(p.vertices) - 2 for c in (P.ART, P.PLAYC) for o in c.objects for p in o.data.polygons)
    print(f"ART {P.SCENE}: {len(P.ART.objects)} art objects, {len(P.PLAYC.objects)} balls, about {tris} triangles")


# ---------------------------------------------------------------- bake: ambient occlusion (the playground's, with the courts' and the track's materials)
GROUND = ["Grass", "Path", "Court_Green", "Court_Blue", "Court_Orange", "Asphalt", "Curb_Red", "Curb_White", "Hedge"]
NOT_BAKED = ("Lamp_Emit", "Paint_White", "Paint_Yellow", "Paint_Black", "Lamp_Red_Off") + ALPHA


# the racetrack's tyres (536 stacks) and grandstand seats (440) are thousands of small UV islands: baked, they took the standing map down to under
# 3 px a metre; left out (black rubber and plastic seats, lit by the page), the walls, the roof, the gantry and the garages get the map
NOT_BAKED_SCENE = {"racetrack": ("Tyre_Black", "Tyre_Red", "Tyre_White", "Plastic_Blue", "Plastic_White")}


def bake_setup():
    P.GROUND, P.NOT_BAKED = GROUND, NOT_BAKED + NOT_BAKED_SCENE.get(P.SCENE, ())
    P.PAGES, P.AO_DIST = [2048, 2048], [1.5, 0.8]
    orig = P.make_export_objects

    def make_export_objects():
        out = orig()
        for m in ALPHA:                                   # the chain-link and the nets cast no AO (they are mostly holes)
            if m in out:
                out[m].hide_render = True
        return out
    if not getattr(P.make_export_objects, "_sports", False):
        make_export_objects._sports = True
        P.make_export_objects = make_export_objects


# ---------------------------------------------------------------- the review stills
def shots():
    e = {x["name"]: x for x in P.GB.empties}
    if P.SCENE == "sports":
        a, f = e["Arrive_playground"]["pos"], e["Arrive_playground"]["face"]
        arr = ((a[0], 1.55, a[2]), (a[0] + f[0] * 20, 1.0, a[2] + f[1] * 20), 62.0)
        return {"1_arrival": arr, "2_wide": ((29.0, 11.0, -23.0), (-2.0, 0.0, 2.0), 60.0),
                "3_detail": ((18.5, 1.6, -3.5), (14.0, 2.6, -12.4), 58.0), "5_tennis": ((-6.3, 1.65, 13.5), (-13.0, 0.9, 0.0), 58.0)}
    a, f = e["Arrive_sports"]["pos"], e["Arrive_sports"]["face"]
    arr = ((a[0], 1.55, a[2]), (a[0] + f[0] * 20, 1.0, a[2] + f[1] * 20), 62.0)
    return {"1_arrival": arr, "2_wide": ((72.0, 16.0, 48.0), (0.0, 0.0, -8.0), 58.0),
            "3_detail": ((-20.0, 1.6, -32.0), (8.0, 3.0, -35.5), 60.0), "5_bend": ((38.0, 1.6, -31.0), (62.0, 0.4, -19.0), 60.0)}


def stage_render():
    sc = bpy.context.scene
    P.STILLS.mkdir(parents=True, exist_ok=True)
    P.scrub_private()
    for c in ("Export", "Layout"):
        if c in bpy.data.collections:
            bpy.data.collections[c].hide_render = True
            bpy.data.collections[c].hide_viewport = True
    bpy.data.collections["Art"].hide_render = False
    P.setup_world()
    P.add_sun()
    P.setup_cycles(arg("--render-samples", 96, int))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = arg("--noise", 0.04, float)
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    which = arg("--only", "all")
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    cams = {k: P.look_cam(k, p, t, f) for k, (p, t, f) in shots().items()}
    X, Z = (G.SPX, G.SPZ) if P.SCENE == "sports" else (G.RT_X, G.RT_Z)
    plan = P.look_cam("4_plan", (0.0, 120.0, 0.0), None, ortho=2 * X + 6)
    plan.rotation_euler = (0, 0, 0)
    todo = [(k, v, (1920, 1080)) for k, v in cams.items()] + [("4_plan", plan, (1600, int(1600 * (2 * Z + 6) / (2 * X + 6))))]
    for key, cam, (w, h) in todo:
        if which not in ("all", key):
            continue
        sc.camera = cam
        sc.view_settings.exposure = arg("--exposure", 0.0, float)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, arg("--scale", 100, int)
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        to_docs = key in ("1_arrival", "2_wide", "3_detail")
        path = P.STILLS / f"{key}.jpg" if to_docs else P.work_dir() / f"{key}.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 450_000 and q > 40 and to_docs:
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        P.strip_jpeg_comments(path)
        print("STILL", P.SCENE, key, path.name, path.stat().st_size, "q", q)


# ================================================================ main
if __name__ == "__main__":
    ST = set(STAGE.split(","))
    summary = []
    import traceback
    failed = []
    for sid in scene_list():
        try:
            P.setup(sid)
            bake_setup()
            print(f"=== {sid}: stages {sorted(ST)}")
            if ST & {"art"}:
                build_all()
                P.save_blend()
            else:
                bpy.ops.wm.open_mainfile(filepath=str(P.BLEND))
                P.open_collections()
            if ST & {"layout", "art"}:
                P.stage_layout()
            if ST & {"check", "art"}:
                summary.append((sid, "check", P.stage_check()))
            if ST & {"bake"}:
                P.stage_bake()
            if ST & {"export"}:
                P.stage_export()
            if ST & {"render"}:
                stage_render()
        except Exception:
            traceback.print_exc()
            failed.append(sid)
    for s in summary:
        print("SUMMARY", *s)
    print("OVERWORLD_SPORTS ALL DONE", "failed:", failed or "none")
    sys.exit(1 if failed else 0)
