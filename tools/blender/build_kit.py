"""Builds the Farway connector kit (docs/BLENDER_AREAS.md, "The connector kit"): four pieces a scene links, each its own .blend with an art-only GLB,
its own lightmap and its own small layout (COL_, DoorLeaf_, Link_/Arrive_, Spot_, Zone_, Marker_).

    blender -b --factory-startup --python tools/blender/build_kit.py -- --piece all|elevator|stair_door|safe_house|sky_hall
            [--stage all|art|bake|export|render|layout] [--samples 384] [--render-samples 96] [--work work/kit] [--device auto|cpu]

| piece        | for                                                     | light (one baked set, `lightmap`) |
|--------------|---------------------------------------------------------|-----------------------------------|
| `elevator`   | the hotel's lift: the car (the Intern's look) and one landing (frame, two sliding leaves, call button) | night: the car's caged bulb; a dim corridor light at the landing |
| `stair_door` | a stair door with its landing and the lit hallway behind it (the store's, blender/kit/stair_door_source.json) | night: the landing's light panel and the hallway's lamps |
| `safe_house` | the hotel roof's safe house: shop counter, stash, save point, crafting bench, respawn pad, locker | soft: one large ceiling panel, a pendant and the lamps' glow |
| `sky_hall`   | the painted-sky hall with an EXIT door, between worlds  | sky-lit: the painted-sky laylight overhead |

The frame of every piece (game axes, metres, y up; Blender (x, y, z) is game (x, -z, y)): the origin is the middle of the piece's door opening, on the
floor, on the face of the wall that meets the host scene; the host is on +z and the piece lies toward -z (as the hotel's room layouts:
tools/blender/build_hotel_greybox.py). The stair door is the exception the store made: its landing is on +z, in front of the door, and its hallway on -z.
blender/kit/README.md says how a scene places each piece, and where each goes in the hotel's greybox.

Stages: art (geometry, materials, lights, the layout objects; saves blender/kit/<piece>.blend) -> bake (merge by node and material, one lightmap UV page,
a Cycles bake, OIDN; <work>/kit_<piece>_0.png) -> export (<work>/kit_<piece>_raw.glb; tools/blender/kit_pack.py makes the WebP files) -> layout
(world/kit/<piece>.json through tools/blender/export_scene.py, and <work>/kit_<piece>_boxes.json for tools/blender/check_layout.py --boxes) ->
render (three review stills, docs/renders/kit/<piece>/). The structure is the mall entrance's (tools/blender/build_entrance.py on its branch).
Textures: CC0 maps already in the repo (blender/textures/kit/, listed in blender/kit/README.md) and pictures drawn here (diamond plate, quilted
steel, the painted sky, the EXIT sign).
"""
import json
import math
import os
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
TEX = ROOT / "blender/textures/kit"
KITDIR = ROOT / "blender/kit"
MARGIN_PX = 6
PIECES = ["elevator", "stair_door", "safe_house", "sky_hall"]

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 384, int)
DEVICE = arg("--device", "auto")
WORK = Path(arg("--work", str(ROOT / "work/kit")))
if not WORK.is_absolute():
    WORK = ROOT / WORK
PIECE = None                     # the piece being built (set by run())


def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


def blend_path():
    return KITDIR / f"{PIECE}.blend"


def lm_url():
    return f"world/lightmaps/kit_{PIECE}_0.webp"


# ================================================================ materials
IMG_CACHE, MATS, TILES, EMITS = {}, {}, {}, {}


def image(fn, srgb=True):
    key = (fn, srgb)
    if key not in IMG_CACHE:
        im = bpy.data.images.load(str(TEX / fn))
        im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
        IMG_CACHE[key] = im
    return IMG_CACHE[key]


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, diff=None, img=None, tint=None, emit=None, tile=1.0):
    """A Principled material. `tint` multiplies the texture (a Mix node set to Multiply, which the glTF exporter writes as baseColorFactor).
    `emit` = (colour or None for the texture, strength in the bake and the stills): the base colour is black, so the page shows the emission
    alone; the GLB carries strength 1 (stage_export), so the page shows the emission colour as it is."""
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
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    tx = None
    if diff or img is not None:
        tx = nt.nodes.new("ShaderNodeTexImage")
        tx.image = img if img is not None else image(diff, True)
        nt.links.new(uv.outputs["UV"], tx.inputs["Vector"])
    if emit:
        bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
        if emit[0] is None and tx is not None:
            nt.links.new(tx.outputs["Color"], bsdf.inputs["Emission Color"])
        else:
            bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
        EMITS[name] = emit[1]
    elif tx is not None:
        if tint:
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs[0].default_value = 1.0
            nt.links.new(tx.outputs["Color"], mix.inputs[6])
            mix.inputs[7].default_value = (*tint, 1)
            nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
        else:
            nt.links.new(tx.outputs["Color"], bsdf.inputs["Base Color"])
    TILES[name] = tile
    MATS[name] = m
    return m


def set_emit_strength(scale):
    """scale None: the bake's strengths; otherwise every emissive material at `scale` (the export: 1)."""
    for name, s in EMITS.items():
        m = bpy.data.materials.get(name)
        if m:
            m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = s * SPEC[PIECE].get("light_scale", 1.0) if scale is None else scale


# ---------------------------------------------------------------- pictures drawn here (rows top to bottom, float RGB(A) 0..1)
def periodic_noise(h, w, rng, beta=2.2, lo=2.0):
    """Tileable fractal noise: white noise shaped in the frequency domain (power ~ 1 / f^beta), normalised to 0..1."""
    fy = np.fft.fftfreq(h)[:, None] * h
    fx = np.fft.rfftfreq(w)[None, :] * w
    f = np.sqrt(fx ** 2 + fy ** 2)
    f[0, 0] = 1
    amp = 1.0 / np.maximum(f, lo) ** (beta / 2)
    amp[0, 0] = 0
    ph = rng.standard_normal((h, w // 2 + 1)) + 1j * rng.standard_normal((h, w // 2 + 1))
    a = np.fft.irfft2(ph * amp, s=(h, w))
    a -= a.min()
    return a / a.max()


def mk_image(name, arr, srgb=True):
    """A packed image from a float array: written as a PNG first (a generated image forgets its pixels when the file is saved)."""
    h, w = arr.shape[:2]
    has_a = arr.shape[2] == 4
    im = bpy.data.images.new(name + "_gen", w, h, alpha=has_a)
    im.alpha_mode = "STRAIGHT"
    im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :arr.shape[2]] = arr
    im.pixels.foreach_set(np.flipud(rgba).ravel())
    gen = WORK / "gen"
    gen.mkdir(parents=True, exist_ok=True)
    path = gen / f"{name}.png"
    im.filepath_raw = str(path)
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)
    out = bpy.data.images.load(str(path))
    out.name = name
    out.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    out.alpha_mode = "STRAIGHT"
    out.pack()
    for ref in [out] + list(out.packed_files):
        attr = "filepath_raw" if ref is out else "filepath"
        setattr(ref, attr, "_" * 1000)
        setattr(ref, attr, f"//generated/{name}.png")
    return out


def diamond_plate_pixels(S=512, seed=181):
    """The Intern's cab floor (games/intern/src/walk/materials.js, diamond_plate): worn steel tread plate, lugs in alternating diagonals,
    rust bloom and grease between them."""
    rng = np.random.default_rng(seed)
    base = periodic_noise(S, S, rng, 2.4)
    a, b = np.array([0x36, 0x33, 0x2e]) / 255, np.array([0x5f, 0x5a, 0x52]) / 255
    img = a + (b - a) * (0.35 + 0.5 * base[..., None])
    rust = periodic_noise(S, S, rng, 3.0)
    img = img * (1 - 0.35 * np.clip((rust - 0.55) * 4, 0, 1)[..., None]) + np.array([0.30, 0.16, 0.07]) * 0.35 * np.clip((rust - 0.55) * 4, 0, 1)[..., None]
    n = 16
    cell = S / n
    yy, xx = np.mgrid[0:S, 0:S] + 0.5
    ci, cj = np.floor(xx / cell), np.floor(yy / cell)
    lx, ly = xx - (ci + 0.5) * cell, yy - (cj + 0.5) * cell
    sgn = np.where((ci + cj) % 2 == 0, 1.0, -1.0)
    u = (lx + sgn * ly) / math.sqrt(2)
    v = (lx - sgn * ly) / math.sqrt(2)
    lug = (u / (cell * 0.36)) ** 2 + (v / (cell * 0.11)) ** 2
    m = np.clip((1.0 - lug) * 3, 0, 1)
    shade = np.clip((1.15 - ((u / (cell * 0.36)) ** 2 + ((v - cell * 0.05) / (cell * 0.11)) ** 2)) * 2, 0, 1) - m
    img = img * (1 - 0.25 * np.clip(shade, 0, 1)[..., None])
    worn = 0.55 + 0.45 * periodic_noise(S, S, rng, 1.5)
    img = img * (1 - m[..., None]) + (np.array([0.62, 0.60, 0.56]) * worn[..., None]) * m[..., None]
    pits = rng.random((S, S)) < 0.004
    img[pits] *= 0.5
    return np.clip(img, 0, 1).astype(np.float32)


def quilted_steel_pixels(S=512, seed=191):
    """The Intern's cab walls (quilted_steel): brushed sheet steel embossed in a diamond quilt, seams pressed in and dark with grime."""
    rng = np.random.default_rng(seed)
    a, b = np.array([0x45, 0x44, 0x3f]) / 255, np.array([0x76, 0x74, 0x6c]) / 255
    yy, xx = np.mgrid[0:S, 0:S] + 0.5
    n = 6
    cell = S / n
    u, v = (xx + yy) / cell, (xx - yy) / cell
    fu, fv = u - np.floor(u), v - np.floor(v)
    d = np.minimum(np.minimum(fu, 1 - fu), np.minimum(fv, 1 - fv))
    pillow = np.clip(d * 4, 0, 1) ** 0.6
    brush = np.repeat(rng.random((S, 1)), S, axis=1) * 0.25 + periodic_noise(S, S, rng, 2.0) * 0.3
    t = 0.25 + 0.55 * pillow + 0.2 * brush
    img = a + (b - a) * t[..., None]
    seam = np.clip(1 - d * 30, 0, 1)
    img = img * (1 - 0.55 * seam[..., None])
    stud = ((fu - 0.5) ** 2 + (fv - 0.5) ** 2) < 0.002
    img[stud] = img[stud] * 0.6 + 0.25
    grime = periodic_noise(S, S, rng, 2.6)
    img = img * (1 - 0.3 * np.clip((grime - 0.5) * 3, 0, 1)[..., None])
    return np.clip(img, 0, 1).astype(np.float32)


def painted_sky_pixels(S=1024, seed=7, soft=1.0, flat=False, dim=1.0):
    """A painted sky: a blue that pales toward the bottom of the picture, and soft brushed clouds; tileable left to right and top to bottom
    (the bottom rows are the horizon haze, so a wall shows the pale band low and the deep blue high). `flat`: no gradient (the ceiling's)."""
    rng = np.random.default_rng(seed)
    y = np.linspace(0, 1, S)[:, None]
    top, low = np.array([0.36, 0.56, 0.82]), np.array([0.80, 0.86, 0.90])
    g = np.clip(y, 0, 1) ** 1.3 if not flat else np.full_like(y, 0.35)
    sky = top[None, None, :] * (1 - g[..., None]) + low[None, None, :] * g[..., None]
    sky = np.repeat(sky, S, axis=1)
    n = periodic_noise(S, S, rng, 4.2, lo=2.0)
    n2 = periodic_noise(S, S, rng, 3.0, lo=4.0)
    c = np.clip((n * 0.85 + n2 * 0.15 - 0.5) * 3.0 * soft, 0, 1)
    c = c * (0.6 + 0.4 * np.clip(1 - np.abs(y - 0.55) * 1.4, 0, 1))
    cloud = np.array([0.93, 0.92, 0.89]) * (0.86 + 0.14 * n2[..., None])
    under = np.array([0.70, 0.74, 0.82])
    shade = np.clip((n - np.roll(n, 6, axis=0)) * 10 + 0.5, 0, 1)[..., None]
    col = cloud * shade + under * (1 - shade)
    img = sky * (1 - c[..., None]) + col * c[..., None]
    stroke = (periodic_noise(S, S, rng, 1.2, lo=40.0) - 0.5) * 0.05
    return np.clip((img + stroke[..., None]) * dim, 0, 1).astype(np.float32)


GLYPH = {  # 5 x 7 block letters
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "X": ["#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"],
    "I": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "S": [".####", "#....", "#....", ".###.", "....#", "....#", "####."],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    "F": ["#####", "#....", "#....", "####.", "#....", "#....", "#...."],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "H": ["#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
    " ": ["....."] * 7,
}


def text_pixels(text, w, h, fg, bg, cell_frac=0.6):
    """Block letters centred on a plain ground (signs)."""
    img = np.ones((h, w, 3), np.float32) * np.array(bg, np.float32)
    n = len(text)
    ch = h * cell_frac / 7
    cw = min(ch, w * 0.86 / (n * 6))
    ch = cw
    x0 = (w - (n * 6 - 1) * cw) / 2
    y0 = (h - 7 * ch) / 2
    for k, c in enumerate(text):
        for r, row in enumerate(GLYPH[c]):
            for q, px in enumerate(row):
                if px == "#":
                    xa, ya = int(x0 + (k * 6 + q) * cw), int(y0 + r * ch)
                    img[ya:int(ya + ch + 0.999), xa:int(xa + cw + 0.999)] = fg
    return img


# ================================================================ geometry (world space, identity transforms)
FACES = {"-x": (0, 0), "+x": (0, 1), "-y": (1, 0), "+y": (1, 1), "-z": (2, 0), "+z": (2, 1)}   # game axis, side


def box(bm, mn, mx, skip=()):
    """An axis-aligned box from game corners, as six quads (minus the `skip` faces, named in game axes: "-y" is the bottom)."""
    x = (mn[0], mx[0])
    y = (mn[1], mx[1])
    z = (mn[2], mx[2])
    v = {}
    for i in (0, 1):
        for j in (0, 1):
            for k in (0, 1):
                v[i, j, k] = bm.verts.new(B((x[i], y[j], z[k])))
    quads = {"-x": [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)], "+x": [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)],
             "-y": [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)], "+y": [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)],
             "-z": [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)], "+z": [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]}
    for key, q in quads.items():
        if key in skip:
            continue
        f = bm.faces.new([v[t] for t in q])
        f.normal_update()
        ax, side = FACES[key]
        want = Vector((0, 0, 0))
        g = [0, 0, 0]
        g[ax] = 1 if side else -1
        want = B(g)
        if f.normal.dot(want) < 0:
            f.normal_flip()


def cyl(bm, p0, p1, r0, r1=None, seg=12, cap=True):
    a, b = B(p0), B(p1)
    d = b - a
    q = d.to_track_quat("Z", "Y")
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                          matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())


def sphere(bm, p, r, seg=10):
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=r, matrix=Matrix.Translation(B(p)))


def quad(bm, pts, facing):
    """A single face through four game points, turned to face the game direction `facing`."""
    f = bm.faces.new([bm.verts.new(B(p)) for p in pts])
    f.normal_update()
    if f.normal.dot(B(facing)) < 0:
        f.normal_flip()
    return f


def box_uv(bm, tile, origin=(0.0, 0.0, 0.0)):
    """UV0: box projection in metres / tile, from world positions, so a texture runs on across the pieces of a wall."""
    uvl = bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        nx, ny, nz = n.x, n.z, -n.y
        ax = max(range(3), key=lambda i: abs((nx, ny, nz)[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x - origin[0], p.z - origin[1], -p.y - origin[2]
            if ax == 0:
                u, v = (-gz if nx > 0 else gz), gy
            elif ax == 1:
                u, v = gx, gz
            else:
                u, v = (gx if nz > 0 else -gx), gy
            lp[uvl].uv = (u / tile, v / tile)


ART = LAYOUT = CONTEXT = None
NODES = {}                     # node name -> pivot (game) and rotation (deg about y), for the GLB's hierarchy


def part(name, mat, build, node, smooth=False, tile=None, coll=None, uv_origin=(0, 0, 0), uv_fn=None):
    """One Art mesh, built in world space by `build(bm)`, of one material, belonging to the GLB node `node`."""
    bm = bmesh.new()
    build(bm)
    for f in bm.faces:
        f.smooth = smooth
    if not bm.loops.layers.uv.get("UVMap"):
        bm.loops.layers.uv.new("UVMap")
    if uv_fn:
        uv_fn(bm)
    else:
        box_uv(bm, tile or TILES.get(mat, 1.0), uv_origin)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(name, me)
    (coll or ART).objects.link(ob)
    if mat in EMITS:
        ob.visible_shadow = False
    ob["node"] = node
    if node not in NODES:
        NODES[node] = ((0.0, 0.0, 0.0), 0.0)
    return ob


def node(name, pivot=(0.0, 0.0, 0.0), yaw=0.0):
    NODES[name] = (tuple(pivot), yaw)


def boxes(name, mat, node_name, bxs, skip=(), **kw):
    def build(bm):
        for bx in bxs:
            box(bm, bx[0], bx[1], bx[2] if len(bx) > 2 else skip)
    return part(name, mat, build, node_name, **kw)


# ---------------------------------------------------------------- the layout objects (docs/BLENDER_AREAS.md, "The exporter and its names")
def col(name, mn, mx):
    """A COL_ box: the page's collider. Kept hidden, never exported to the GLB."""
    bm = bmesh.new()
    box(bm, mn, mx)
    me = bpy.data.meshes.new("COL_" + name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("COL_" + name, me)
    LAYOUT.objects.link(ob)
    ob.display_type = "WIRE"
    ob.hide_render = True
    return ob


def empty(name, pos, face=None, props=None, kind="PLAIN_AXES"):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_type = kind
    ob.empty_display_size = 0.25
    ob.location = B(pos)
    if face is not None:
        ob.rotation_euler = (0, 0, math.atan2(face[0], face[1]))       # the empty's -Y axis is game (fx, fz)
    for k, v in (props or {}).items():
        ob[k] = v
    LAYOUT.objects.link(ob)
    return ob


def door(name, hinge, width, height, closed_yaw, swing, props=None):
    """DoorLeaf_<name>: an empty at the hinge carrying what export_scene.py writes (the leaf's art is the GLB node Leaf_<name>, or the sliding
    leaves an elevator names in `leaves`)."""
    p = {"width": round(width, 3), "height": round(height, 3), "closed_yaw_deg": float(closed_yaw), "swing_deg": float(swing), "state": "closed"}
    p.update(props or {})
    ob = empty("DoorLeaf_" + name, hinge, props=p, kind="ARROWS")
    ob.rotation_euler = (0, 0, math.radians(closed_yaw))
    return ob


def link(did, at, arrive, face):
    empty("Link_" + did, at, kind="SPHERE")
    empty("Arrive_" + did, arrive, face=face, kind="SINGLE_ARROW")


def spot(kind, n, pos, face=(0, 1), props=None):
    empty(f"Spot_{kind}_{n}", pos, face=face, props=props, kind="CONE")


def zone(kind, name, mn, mx):
    bm = bmesh.new()
    box(bm, mn, mx)
    me = bpy.data.meshes.new(f"Zone_{kind}_{name}")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(f"Zone_{kind}_{name}", me)
    LAYOUT.objects.link(ob)
    ob.display_type = "WIRE"
    ob.hide_render = True


def marker(name, pos, kind="Entrance"):
    empty("Marker_" + name, pos, props={"kind": kind})


# ---------------------------------------------------------------- lights
def light(name, kind, pos, energy, color, size=0.1, direction=(0, -1, 0), size_y=None, coll=None):
    d = bpy.data.lights.new(name, kind)
    d.energy, d.color = energy * SPEC[PIECE].get("light_scale", 1.0), color
    if kind == "AREA":
        d.shape = "RECTANGLE"
        d.size = size
        d.size_y = size_y if size_y is not None else size
    else:
        d.shadow_soft_size = size
    ob = bpy.data.objects.new(name, d)
    ob.location = B(pos)
    ob.rotation_euler = B(direction).to_track_quat("-Z", "Y").to_euler()
    (coll or bpy.data.collections["Lights"]).objects.link(ob)
    return ob


def setup_world(color=(0.02, 0.02, 0.025), strength=1.0):
    sc = bpy.context.scene
    w = bpy.data.worlds.new("Kit_World")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (*color, 1)
    bg.inputs["Strength"].default_value = strength


# ================================================================ piece 1: the elevator (the Intern's cab, games/intern/data/rooms.json S7_C)
# The greybox's shaft (tools/blender/build_hotel_greybox.py, atrium()): inside 2.2 m by 2.2 m, its front wall 0.2 m thick with a 1.2 m by 2.2 m
# opening at every stop; the car 2.1 m by 2.1 m and 2.4 m high. On the corridor floors the lift door is the same 1.2 m by 2.2 m opening.
CAR_W, CAR_D, CAR_H = 2.1, 2.1, 2.4
CAR_Z0, CAR_Z1 = -0.25, -0.25 - CAR_D          # the car's front and back faces (kit frame)
OPEN_W, OPEN_H = 1.2, 2.2
WALL_T = 0.2


def mats_elevator():
    g = {"diamond": mk_image("Diamond_Plate", diamond_plate_pixels()), "quilt": mk_image("Quilted_Steel", quilted_steel_pixels())}
    material("Car_Floor_Diamond", img=g["diamond"], rough=0.5, metal=0.0, tile=0.9)
    material("Car_Wall_Quilted", img=g["quilt"], rough=0.45, tile=0.7)
    material("Car_Rust", diff="painted_metal_shutter_diff_1k.jpg", tint=(0.42, 0.27, 0.17), rough=0.8, tile=1.2)       # ceiling, kick plate, frame of the cab
    material("Car_Dark", diff="painted_metal_shutter_diff_1k.jpg", tint=(0.16, 0.16, 0.15), rough=0.6, tile=1.0)       # panel plate, indicator housing, gate uprights
    material("Brass", color=(0.48, 0.36, 0.17), rough=0.35, metal=0.0)            # bezels, handrail, gate links, call plate (lightmapped, so no metal)
    material("Button_Grey", color=(0.30, 0.30, 0.29), rough=0.5)
    material("Landing_Leaf", diff="painted_metal_shutter_diff_1k.jpg", tint=(0.34, 0.36, 0.33), rough=0.55, tile=1.6)  # the landing's sliding leaves
    material("Landing_Frame", diff="painted_metal_shutter_diff_1k.jpg", tint=(0.22, 0.21, 0.19), rough=0.5, tile=1.2)
    material("Steel_Sill", diff="concrete_floor_02_diff_1k.jpg", tint=(0.45, 0.45, 0.46), rough=0.4, tile=0.5)
    material("Landing_Stone", diff="concrete_floor_02_diff_1k.jpg", tint=(0.62, 0.58, 0.52), rough=0.6, tile=1.2)
    material("Kit_Bulb_Emit", rough=0.3, emit=((0.95, 0.80, 0.58), 10.0))
    material("Kit_Button_Glow", rough=0.3, emit=((0.25, 0.95, 0.45), 6.0))
    material("Kit_Indicator_Glow", rough=0.3, emit=((0.95, 0.55, 0.16), 6.0))
    material("Kit_Call_Glow", rough=0.3, emit=((0.95, 0.70, 0.30), 5.0))
    material("Ctx_Wall", diff="beige_wall_001_diff_1k.jpg", tint=(0.62, 0.58, 0.50), rough=0.9, tile=2.0)
    material("Ctx_Carpet", diff="rough_linen_diff_512.jpg", tint=(0.36, 0.16, 0.13), rough=1.0, tile=1.0)
    material("Ctx_Shaft", diff="concrete_floor_02_diff_1k.jpg", tint=(0.30, 0.29, 0.27), rough=0.95, tile=2.0)
    material("Ctx_Ceiling", diff="beige_wall_001_diff_1k.jpg", tint=(0.80, 0.78, 0.72), rough=0.95, tile=2.0)
    material("Ctx_Lamp", rough=0.4, emit=((0.95, 0.85, 0.70), 8.0))


def build_elevator():
    x0, x1 = -CAR_W / 2, CAR_W / 2
    zf, zb = CAR_Z0, CAR_Z1
    wt = 0.05                              # the cab's wall thickness
    ow = OPEN_W / 2
    # --- the car (GLB node elevator_car: the page moves it up and down the shaft; its colliders move with it)
    node("elevator_car")
    boxes("Car_Floor", "Car_Floor_Diamond", "elevator_car", [((x0, -0.12, zb), (x1, 0.0, zf), ("-y",))])
    boxes("Car_Walls", "Car_Wall_Quilted", "elevator_car", [
        ((x0, 0.3, zb), (x0 + wt, CAR_H, zf), ("-x",)),                     # west
        ((x1 - wt, 0.3, zb), (x1, CAR_H, zf), ("+x",)),                     # east
        ((x0 + wt, 0.3, zb), (x1 - wt, CAR_H, zb + wt), ("-z",)),           # back
        ((x0 + wt, 0.3, zf - wt), (-ow, OPEN_H, zf), ("+z",)),              # front, either side of the opening
        ((ow, 0.3, zf - wt), (x1 - wt, OPEN_H, zf), ("+z",)),
    ])
    boxes("Car_Kick", "Car_Rust", "elevator_car", [
        ((x0, 0.0, zb), (x0 + wt + 0.012, 0.3, zf), ("-x", "-y")), ((x1 - wt - 0.012, 0.0, zb), (x1, 0.3, zf), ("+x", "-y")),
        ((x0 + wt + 0.012, 0.0, zb), (x1 - wt - 0.012, 0.3, zb + wt + 0.012), ("-z", "-y")),
        ((x0 + wt + 0.012, 0.0, zf - wt - 0.012), (-ow, 0.3, zf), ("+z", "-y")), ((ow, 0.0, zf - wt - 0.012), (x1 - wt - 0.012, 0.3, zf), ("+z", "-y")),
        ((x0 + wt, OPEN_H, zf - wt), (x1 - wt, CAR_H, zf), ("+z",)),       # the head over the car's opening
        ((x0, CAR_H, zb), (x1, CAR_H + 0.08, zf), ("+y",)),                # the cab's ceiling
        ((-ow - 0.04, 0.0, zf - wt - 0.02), (-ow + 0.005, OPEN_H, zf), ("+z",)), ((ow - 0.005, 0.0, zf - wt - 0.02), (ow + 0.04, OPEN_H, zf), ("+z",)),   # the car's jambs
    ])
    # handrail along the back and the sides, on brackets
    def rail(bm):
        y = 0.92
        d = 0.06
        for p0, p1 in (((x0 + wt + d, y, zb + wt + d), (x1 - wt - d, y, zb + wt + d)), ((x0 + wt + d, y, zb + wt + d), (x0 + wt + d, y, zf - 0.35)),
                       ((x1 - wt - d, y, zb + wt + d), (x1 - wt - d, y, zf - 0.35))):
            cyl(bm, p0, p1, 0.018, seg=10)
        for p in ((x0 + wt, y, zb + 0.45), (x0 + wt, y, zf - 0.45), (x1 - wt, y, zb + 0.45), (x1 - wt, y, zf - 0.45), (-0.6, y, zb + wt), (0.6, y, zb + wt)):
            q = list(p)
            if abs(q[0]) > 0.9:
                box(bm, (min(q[0], q[0] + (d if q[0] < 0 else -d)), y - 0.012, q[2] - 0.012), (max(q[0], q[0] + (d if q[0] < 0 else -d)), y + 0.012, q[2] + 0.012))
            else:
                box(bm, (q[0] - 0.012, y - 0.012, q[2]), (q[0] + 0.012, y + 0.012, q[2] + d))
    part("decor_Car_Handrail", "Brass", rail, "elevator_car", smooth=True)
    # the control panel (props.js cabpanel): 66 buttons in a 6 x 11 grid on a dark plate in a brass bezel, button 41 lit; on the east wall by the door
    PX = x1 - wt                            # the east wall's inner face
    pz, py0 = zf - 0.42, 0.7                # the plate's centre along the wall, its bottom
    W_, H_ = 0.42, 1.2

    def onwall(a, y, d):                    # a: along the wall (toward the back is +a), y up, d out of the wall into the car
        return (PX - d, y, pz - a)
    def wbox(bm, a0, a1, y0, y1, d0, d1):
        p, q = onwall(a0, y0, d0), onwall(a1, y1, d1)
        box(bm, [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)], ("+x",))
    part("decor_Car_Panel_Plate", "Car_Dark", lambda bm: wbox(bm, -W_ / 2, W_ / 2, py0, py0 + H_, 0, 0.03), "elevator_car")
    part("decor_Car_Panel_Bezel", "Brass", lambda bm: [wbox(bm, *r) for r in (
        (-W_ / 2 - 0.015, W_ / 2 + 0.015, py0 - 0.025, py0, 0, 0.04), (-W_ / 2 - 0.015, W_ / 2 + 0.015, py0 + H_, py0 + H_ + 0.025, 0, 0.04),
        (-W_ / 2 - 0.025, -W_ / 2, py0, py0 + H_, 0, 0.04), (W_ / 2, W_ / 2 + 0.025, py0, py0 + H_, 0, 0.04),
        (-0.12, 0.12, py0 + H_ - 0.12, py0 + H_ - 0.07, 0.03, 0.036))], "elevator_car")
    LIT = 41
    def buttons(bm, lit):
        for i in range(66):
            if (i == LIT) != lit:
                continue
            c, r = i % 6, i // 6
            a = -0.15 + c * 0.06
            y = py0 + 0.1 + r * 0.095
            s = 0.021 if lit else 0.018
            wbox(bm, a - s, a + s, y - s, y + s, 0.03, 0.03 + (0.022 if lit else 0.016))
    part("decor_Car_Buttons", "Button_Grey", lambda bm: buttons(bm, False), "elevator_car")
    part("decor_Car_Button_Lit", "Kit_Button_Glow", lambda bm: buttons(bm, True), "elevator_car")
    # the floor indicator over the door, inside (props.js floorind): three seven-segment cells in a dark housing, reading "--"
    iy, iz = 2.24, zf - wt
    def ind_housing(bm):
        box(bm, (-0.26, iy, iz - 0.05), (0.26, iy + 0.12, iz), ("+z",))
    part("decor_Car_Indicator", "Car_Dark", ind_housing, "elevator_car")
    def segs(bm, lit):
        dw, dh, st = 0.05, 0.08, 0.011
        for k in range(3):
            cx = (k - 1) * 0.1
            cy = iy + 0.06
            for L, (sx, sy, hz) in {"a": (0, dh / 2, 1), "d": (0, -dh / 2, 1), "g": (0, 0, 1), "b": (dw / 2, dh / 4, 0), "c": (dw / 2, -dh / 4, 0),
                                    "e": (-dw / 2, -dh / 4, 0), "f": (-dw / 2, dh / 4, 0)}.items():
                on = L == "g" and k > 0
                if on != lit:
                    continue
                if hz:
                    box(bm, (cx + sx - (dw - st) / 2, cy + sy - st / 2, iz - 0.056), (cx + sx + (dw - st) / 2, cy + sy + st / 2, iz - 0.05), ("+z",))
                else:
                    box(bm, (cx + sx - st / 2, cy + sy - (dh / 2 - st) / 2, iz - 0.056), (cx + sx + st / 2, cy + sy + (dh / 2 - st) / 2, iz - 0.05), ("+z",))
    part("decor_Car_Segments", "Button_Grey", lambda bm: segs(bm, False), "elevator_car")
    part("decor_Car_Segments_Lit", "Kit_Indicator_Glow", lambda bm: segs(bm, True), "elevator_car")
    # the caged bulb (props.js cabbulb): ceiling plate, stem, socket, six ribs and three rings, the bare bulb
    cy_ = CAR_H
    bz = (zf + zb) / 2
    def cage(bm):
        box(bm, (-0.1, cy_ - 0.025, bz - 0.1), (0.1, cy_, bz + 0.1), ("+y",))
        cyl(bm, (0, cy_ - 0.025, bz), (0, cy_ - 0.18, bz), 0.016, seg=8)
        cyl(bm, (0, cy_ - 0.18, bz), (0, cy_ - 0.23, bz), 0.034, 0.03, seg=10)
        R, top = 0.075, cy_ - 0.2
        for i in range(6):
            a = i / 6 * 2 * math.pi
            cyl(bm, (math.cos(a) * R * 0.7, top, bz + math.sin(a) * R * 0.7), (math.cos(a) * R, top - 0.08, bz + math.sin(a) * R), 0.005, seg=4)
            cyl(bm, (math.cos(a) * R, top - 0.08, bz + math.sin(a) * R), (math.cos(a) * R * 0.8, top - 0.16, bz + math.sin(a) * R * 0.8), 0.005, seg=4)
        for y, r in ((top, R * 0.7), (top - 0.08, R), (top - 0.16, R * 0.8)):
            for i in range(6):
                a, b = i / 6 * 2 * math.pi, (i + 1) / 6 * 2 * math.pi
                cyl(bm, (math.cos(a) * r, y, bz + math.sin(a) * r), (math.cos(b) * r, y, bz + math.sin(b) * r), 0.005, seg=4)
    part("decor_Car_BulbCage", "Car_Rust", cage, "elevator_car")
    part("decor_Car_Bulb", "Kit_Bulb_Emit", lambda bm: sphere(bm, (0, cy_ - 0.28, bz), 0.042), "elevator_car", smooth=True)
    # the scissor gate (props.js scissorgate), folded against the west jamb inside the car's opening: visual only
    def gate(bm, links):
        w, h, bars = OPEN_W, 2.1, 7
        span = w * 0.12
        gx0 = -ow
        gz = zf - wt - 0.04
        bay = span / (bars - 1)
        if not links:
            for i in range(bars):
                box(bm, (gx0 + i * bay - 0.012, 0.02, gz - 0.012), (gx0 + i * bay + 0.012, h - 0.02, gz + 0.012))
            box(bm, (-ow - 0.04, h, gz - 0.03), (ow + 0.04, h + 0.05, gz + 0.03))
        else:
            th = (h - 0.18) / 2
            for i in range(bars - 1):
                for k in range(2):
                    xa, xb = gx0 + i * bay, gx0 + (i + 1) * bay
                    ya, yb = 0.12 + k * th, 0.12 + (k + 1) * th
                    cyl(bm, (xa, ya, gz - 0.02), (xb, yb, gz - 0.02), 0.006, seg=4)
                    cyl(bm, (xb, ya, gz - 0.03), (xa, yb, gz - 0.03), 0.006, seg=4)
    part("decor_Car_Gate", "Car_Dark", lambda bm: gate(bm, False), "elevator_car")
    part("decor_Car_GateLinks", "Brass", lambda bm: gate(bm, True), "elevator_car")
    # a framed inspection certificate on the back wall
    part("decor_Car_Certificate", "Brass", lambda bm: box(bm, (-0.75, 1.45, zb + wt), (-0.45, 1.85, zb + wt + 0.012), ("-z",)), "elevator_car")
    # the car's colliders
    col("Car_Floor", (x0, -0.12, zb), (x1, 0.0, zf))
    col("Car_Wall_W", (x0, 0.0, zb), (x0 + wt, CAR_H, zf))
    col("Car_Wall_E", (x1 - wt, 0.0, zb), (x1, CAR_H, zf))
    col("Car_Wall_Back", (x0 + wt, 0.0, zb), (x1 - wt, CAR_H, zb + wt))
    col("Car_Front_W", (x0 + wt, 0.0, zf - wt), (-ow, CAR_H, zf))
    col("Car_Front_E", (ow, 0.0, zf - wt), (x1 - wt, CAR_H, zf))
    col("Car_Head", (-ow, OPEN_H, zf - wt), (ow, CAR_H, zf))
    col("Car_Ceiling", (x0, CAR_H, zb), (x1, CAR_H + 0.08, zf))
    # --- one landing (GLB node elevator_landing; one copy per stop): the frame, the two sliding leaves, the sill, the call button, the indicator
    node("elevator_landing")
    fw = 0.08
    boxes("Landing_Frame", "Landing_Frame", "elevator_landing", [
        ((-ow - fw, 0.0, -0.02), (-ow, OPEN_H + fw, 0.06), ("-z",)), ((ow, 0.0, -0.02), (ow + fw, OPEN_H + fw, 0.06), ("-z",)),
        ((-ow, OPEN_H, -0.02), (ow, OPEN_H + fw, 0.06), ("-z",)),
    ])
    boxes("decor_Landing_Lining", "Landing_Frame", "elevator_landing", [                          # inside the host wall's opening: never walked into
        ((-ow, OPEN_H - 0.01, -WALL_T), (ow, OPEN_H, -0.02), ()),                                 # the head's soffit across the wall's thickness
        ((-ow, 0.0, -WALL_T), (-ow + 0.01, OPEN_H, -0.02), ("-x",)), ((ow - 0.01, 0.0, -WALL_T), (ow, OPEN_H, -0.02), ("+x",)),   # the jamb linings
    ])
    part("Landing_Sill", "Steel_Sill", lambda bm: box(bm, (-ow - fw, -0.01, -WALL_T), (ow + fw, 0.008, 0.07), ("-y",)), "elevator_landing")
    # the landing's stone in front of the doors (1.8 m by 1.2 m, 6 mm proud of the host's floor): what you stand on to call the car
    part("Landing_Plate", "Landing_Stone", lambda bm: box(bm, (-0.9, -0.01, 0.07), (0.9, 0.006, 1.27), ("-y",)), "elevator_landing")
    col("Landing_Floor", (-0.9, -0.05, 0.07), (0.9, 0.006, 1.27))
    # the leaves (landingdoors): two panels with four ribs each, closed, set 7 cm into the opening; the page slides them apart (0.6 m each way)
    for s, nm in ((-1, "LiftLeaf_L"), (1, "LiftLeaf_R")):
        node(nm, pivot=(s * ow / 2, 0.0, -0.09))
        a0, a1 = (-ow, -0.002) if s < 0 else (0.002, ow)
        boxes(f"{nm}_Panel", "Landing_Leaf", nm, [((a0, 0.01, -0.12), (a1, OPEN_H - 0.005, -0.07))])
        boxes(f"{nm}_Ribs", "Landing_Frame", nm, [((a0 + 0.03, 0.3 + i * (OPEN_H - 0.6) / 3, -0.07), (a1 - 0.03, 0.33 + i * (OPEN_H - 0.6) / 3, -0.06), ("-z",))
                                                   for i in range(4)])
    # the call button: a brass plate by the east jamb with one round button, its ring lit
    cx_, cy0 = ow + fw + 0.2, 1.0
    part("decor_Call_Plate", "Brass", lambda bm: box(bm, (cx_ - 0.05, cy0, 0.0), (cx_ + 0.05, cy0 + 0.18, 0.012), ("-z",)), "elevator_landing")
    part("decor_Call_Button", "Kit_Call_Glow", lambda bm: cyl(bm, (cx_, cy0 + 0.09, 0.012), (cx_, cy0 + 0.09, 0.024), 0.022, seg=16), "elevator_landing", smooth=True)
    # the landing's floor indicator over the frame (the same three cells, reading "--")
    def l_ind(bm):
        box(bm, (-0.26, OPEN_H + 0.14, 0.0), (0.26, OPEN_H + 0.3, 0.05), ("-z",))
    part("decor_Landing_Indicator", "Car_Dark", l_ind, "elevator_landing")
    def l_segs(bm, lit):
        dw, dh, st = 0.05, 0.08, 0.011
        for k in range(3):
            cx = (k - 1) * 0.1
            cy = OPEN_H + 0.22
            for L, (sx, sy, hz) in {"a": (0, dh / 2, 1), "d": (0, -dh / 2, 1), "g": (0, 0, 1), "b": (dw / 2, dh / 4, 0), "c": (dw / 2, -dh / 4, 0),
                                    "e": (-dw / 2, -dh / 4, 0), "f": (-dw / 2, dh / 4, 0)}.items():
                on = L == "g" and k > 0
                if on != lit:
                    continue
                if hz:
                    box(bm, (cx + sx - (dw - st) / 2, cy + sy - st / 2, 0.05), (cx + sx + (dw - st) / 2, cy + sy + st / 2, 0.056), ("-z",))
                else:
                    box(bm, (cx + sx - st / 2, cy + sy - (dh / 2 - st) / 2, 0.05), (cx + sx + st / 2, cy + sy + (dh / 2 - st) / 2, 0.056), ("-z",))
    part("decor_Landing_Segments", "Button_Grey", lambda bm: l_segs(bm, False), "elevator_landing")
    part("decor_Landing_Segments_Lit", "Kit_Indicator_Glow", lambda bm: l_segs(bm, True), "elevator_landing")
    col("Landing_Jamb_W", (-ow - fw, 0.0, -0.02), (-ow, OPEN_H + fw, 0.06))
    col("Landing_Jamb_E", (ow, 0.0, -0.02), (ow + fw, OPEN_H + fw, 0.06))
    col("Landing_Head", (-ow, OPEN_H, -0.02), (ow, OPEN_H + fw, 0.06))
    # the layout: the lift door (one record, as the greybox's; the page slides LiftLeaf_L and LiftLeaf_R), the link, where you arrive
    door("lift", (ow, 0.0, 0.0), OPEN_W, OPEN_H, 180.0, 95.0,
         props={"kind": "elevator", "leaves": "LiftLeaf_L,LiftLeaf_R", "slide_m": round(ow, 3), "car": "elevator_car"})
    link("lift", (0.0, 0.0, 0.6), (0.0, 0.0, 1.0), (0, 1))
    spot("call", 1, (cx_, 0.0, 0.45), face=(0, -1), props={"what": "the call button"})
    spot("panel", 1, (PX - 0.45, 0.0, pz), face=(1, 0), props={"what": "the car's floor buttons (inside the car)"})
    marker("Landing", (0.0, 0.0, 1.0), "Entrance")
    # --- context (stills and bake only; not in the GLB, not in the layout): the shaft round the car, the shaft's front wall, a corridor in front
    def ctx(name, mat, bxs):
        boxes("ctx_" + name, mat, "ctx", bxs, coll=CONTEXT)
    ctx("ShaftFront", "Ctx_Wall", [((-1.6, 0.0, -WALL_T), (-ow, 3.0, 0.0)), ((ow, 0.0, -WALL_T), (1.6, 3.0, 0.0)), ((-ow, OPEN_H, -WALL_T), (ow, 3.0, 0.0))])
    ctx("Shaft", "Ctx_Shaft", [((-1.3, -1.0, -2.6), (-1.1, 3.5, -WALL_T)), ((1.1, -1.0, -2.6), (1.3, 3.5, -WALL_T)), ((-1.1, -1.0, -2.6), (1.1, 3.5, -2.4)),
                               ((-1.1, -1.0, -2.4), (1.1, -0.9, -WALL_T))])
    ctx("Corridor_Floor", "Ctx_Carpet", [((-1.6, -0.2, 0.0), (1.6, 0.0, 3.2))])
    ctx("Corridor_Walls", "Ctx_Wall", [((-1.8, 0.0, 0.0), (-1.6, 3.0, 3.2)), ((1.6, 0.0, 0.0), (1.8, 3.0, 3.2))])
    ctx("Corridor_Ceiling", "Ctx_Ceiling", [((-1.8, 3.0, -0.2), (1.8, 3.2, 3.2))])
    ctx("Corridor_Lamp", "Ctx_Lamp", [((-0.3, 2.98, 1.6), (0.3, 3.0, 2.2))])
    # lights (night): the bulb in the cage, the lit button's glow, the indicator; a dim ceiling panel in the corridor
    light("Car_Bulb", "POINT", (0, cy_ - 0.28, bz), 120.0, (1.0, 0.81, 0.60), size=0.04)
    light("Car_Button", "POINT", (PX - 0.06, py0 + 0.1 + 6 * 0.095, pz - (-0.15 + 5 * 0.06)), 0.25, (0.2, 1.0, 0.47), size=0.01)
    light("Car_Indicator", "POINT", (0, iy + 0.06, iz - 0.12), 0.25, (1.0, 0.6, 0.23), size=0.02)
    light("Corridor_Lamp", "AREA", (0, 2.96, 1.9), 55.0, (1.0, 0.86, 0.68), size=0.6, direction=(0, -1, 0))
    light("Call_Glow", "POINT", (cx_, cy0 + 0.09, 0.06), 0.15, (1.0, 0.72, 0.35), size=0.01)
    setup_world((0.01, 0.01, 0.012), 1.0)


def cams_elevator():
    return {"1_car_from_landing": ((0.0, 1.55, 2.4), (0.0, 1.25, -1.3), 62.0, {"hide": ["LiftLeaf_L", "LiftLeaf_R"]}),
            "2_car_inside": ((-0.75, 1.55, -1.95), (0.85, 1.1, -0.55), 72.0, {}),
            "3_landing_closed": ((1.1, 1.5, 2.7), (-0.1, 1.2, 0.0), 56.0, {})}


# ================================================================ piece 2: the stair door with its lit hallway (the store's, read-only)
def stair_src():
    return json.loads((KITDIR / "stair_door_source.json").read_text())["stairs"][STAIR_KEY]


STAIR_KEY = "L1_L2"                     # the store's L1 -> L2 stair door: its parts were built whole (backrooms_L1_stairdoors.py carved nothing there)


def stair_frame(s):
    """Store Blender (x, y, z) -> kit game coordinates: the door's centre on the landing face of its head wall is the origin, and the store's
    landing (game -z of the door there) turns to kit +z (a half turn about y, so nothing is mirrored)."""
    hw = [b for b in s["parts"][f"Stair_{STAIR_KEY}_lower_wallHi"]["boxes"] if b["max"][2] - b["min"][2] < 0.6]   # the door head
    head = hw[0]
    cx = (head["min"][0] + head["max"][0]) / 2
    face_y = max(b["max"][1] for b in s["parts"][f"Stair_{STAIR_KEY}_lower_wallHi"]["boxes"] if b["max"][1] - b["min"][1] < 0.25 and b["min"][1] < -10)
    fy = s["leaf"]["hinge"][2]                                                     # the store floor's height (Blender z)

    def to_kit(p):
        gx, gy, gz = p[0], p[2], -p[1]                                             # store Blender -> store game
        return (-(gx - cx), gy - fy, -(gz - (-face_y)))
    return to_kit, cx, face_y, fy


HALL_L, HALL_W, HALL_H, HALL_T, DW, DH = 10.0, 2.4, 2.7, 0.2, 1.1, 2.16        # index.html buildPassage (PASSAGE_LEN, _W, _H) and its door


def mats_stair():
    material("Stair_Wall", diff="beige_wall_001_diff_1k.jpg", tint=(0.86, 0.78, 0.52), rough=0.85, tile=1.2)     # the store's L2 look: a yellowed wallpaper
    material("Stair_Floor", diff="rough_linen_diff_512.jpg", tint=(0.46, 0.40, 0.30), rough=0.95, tile=0.8)        # its worn carpet
    material("Stair_Ceiling", diff="beige_wall_001_diff_1k.jpg", tint=(0.90, 0.89, 0.84), rough=0.9, tile=1.2)
    material("Fixture_Housing", color=(0.62, 0.62, 0.60), rough=0.6)                                                  # M_Fixture_Housing
    material("Stair_Door", diff="dark_wood_diff_1k.jpg", tint=(0.80, 0.62, 0.44), rough=0.7, tile=1.4)               # M_Door (0.42, 0.30, 0.18)
    material("Hall_Wall", diff="beige_wall_001_diff_1k.jpg", tint=(0.85, 0.76, 0.42), rough=0.95, tile=1.6)          # PASSAGE_TINT, L1: 0xd9c36a
    material("Hall_Floor", diff="concrete_floor_02_diff_1k.jpg", tint=(0.30, 0.28, 0.25), rough=1.0, tile=1.5)       # 0x2c2a26
    material("Hall_Ceiling", diff="beige_wall_001_diff_1k.jpg", tint=(0.91, 0.90, 0.86), rough=1.0, tile=1.6)        # 0xe9e6dc
    material("Door_Handle", color=(0.50, 0.40, 0.22), rough=0.35)
    material("Kit_Tube_Emit", rough=0.3, emit=((0.95, 0.93, 0.83), 2.0))                                              # M_Fluorescent (1.0, 0.97, 0.86)
    material("Ctx_Step", diff="rough_linen_diff_512.jpg", tint=(0.42, 0.37, 0.28), rough=0.95, tile=0.8)


def build_stair_door():
    s = stair_src()
    to_kit, cx, face_y, fy = stair_frame(s)
    LAND = 1.6                                                                     # the store's landing reaches 1.6 m in front of the door (its top step)
    kept, cut = [], []

    def kbox(b):
        p, q = to_kit(b["min"]), to_kit(b["max"])
        return [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)]
    node("stair_door_landing")
    parts = s["parts"]
    for nm, p in sorted(parts.items()):
        pk = p["part"]
        if pk == "wallLo":                                                         # the stair shaft below the landing: the host's stairs, not the door's
            continue
        mat = {"landing": "Stair_Floor", "wallHi": "Stair_Wall", "ceil": "Stair_Ceiling", "housing": "Fixture_Housing", "tube": "Kit_Tube_Emit"}[pk]
        bxs = []
        for b in p["boxes"]:
            mn, mx = kbox(b)
            if mx[2] > LAND + 1e-3 and mn[2] < LAND:
                cut.append((nm, round(mx[2] - mn[2], 3)))
                mx[2] = LAND                                                       # a side wall or the ceiling that runs on over the stairs: cut at the top step
            elif mn[2] >= LAND - 1e-3:
                continue                                                           # the shaft's far wall, past the stairs
            else:
                kept.append(nm)
            bxs.append((tuple(round(v, 4) for v in mn), tuple(round(v, 4) for v in mx)))
        if bxs:
            boxes(f"Stair_{pk}", mat, "stair_door_landing", bxs, tile=None)
            if pk in ("landing", "wallHi", "ceil"):
                for i, (mn, mx) in enumerate(bxs):
                    col(f"Stair_{pk}_{i}", mn, mx)
    # the leaf (DoorLeaf_Stair_L1_L2_up), its 1.04 m by 2.12 m by 5 cm box unchanged, hinged on its own node
    lb = s["leaf"]["boxes"][0]
    mn, mx = kbox(lb)
    hinge = to_kit(s["leaf"]["hinge"])
    node("Leaf_stair", pivot=hinge, yaw=180.0)
    boxes("Leaf_Stair", "Stair_Door", "Leaf_stair", [(tuple(mn), tuple(mx))])
    hx = mx[0] - 0.08 if hinge[0] < 0 else mn[0] + 0.08                            # a handle on both faces, at the free edge
    part("decor_Leaf_Handle", "Door_Handle", lambda bm: [cyl(bm, (hx, 1.0, mn[2] - 0.06), (hx, 1.0, mx[2] + 0.06), 0.012, seg=10),
                                                          box(bm, (hx - 0.11, 0.985, mx[2] + 0.05), (hx + 0.0, 1.015, mx[2] + 0.07)),
                                                          box(bm, (hx - 0.11, 0.985, mn[2] - 0.07), (hx + 0.0, 1.015, mn[2] - 0.05))], "Leaf_stair", smooth=True)
    # the lit hallway behind the door, as the page draws it (index.html buildPassage): 10 m by 2.4 m, 2.7 m high, a lamp every 3 m, a shut door at the far end
    node("stair_door_hallway")
    hw_, z0, z1 = HALL_W / 2, -HALL_T, -HALL_T - HALL_L
    boxes("Hall_Floor", "Hall_Floor", "stair_door_hallway", [((-hw_, -0.3, z1), (hw_, 0.0, z0), ("-y",))])
    boxes("Hall_Ceiling", "Hall_Ceiling", "stair_door_hallway", [((-hw_, HALL_H, z1), (hw_, HALL_H + 0.2, z0), ("+y",))])
    boxes("Hall_Walls", "Hall_Wall", "stair_door_hallway", [
        ((-hw_ - HALL_T, -0.3, z1 - HALL_T), (-hw_, HALL_H + 0.2, z0), ("-x",)), ((hw_, -0.3, z1 - HALL_T), (hw_ + HALL_T, HALL_H + 0.2, z0), ("+x",)),
        ((-hw_, 0.0, z1 - HALL_T), (-DW / 2, HALL_H, z1), ("-z",)), ((DW / 2, 0.0, z1 - HALL_T), (hw_, HALL_H, z1), ("-z",)),
        ((-DW / 2, DH, z1 - HALL_T), (DW / 2, HALL_H, z1), ("-z",)),
    ])                                                                             # the near end is the store's head wall itself (2.7 m wide)
    lamps = [z for z in np.arange(-1.5 + z0, z1, -3.0)]
    part("Hall_Lamps", "Kit_Tube_Emit", lambda bm: [box(bm, (-0.4, HALL_H - 0.06, z - 0.2), (0.4, HALL_H, z + 0.2), ("+y",)) for z in lamps], "stair_door_hallway")
    lw = DW - 0.06
    node("Leaf_hall_far", pivot=(-DW / 2 + 0.03, 0.0, z1 - HALL_T / 2), yaw=0.0)
    boxes("Leaf_Hall_Far", "Stair_Door", "Leaf_hall_far", [((-DW / 2 + 0.03, 0.0, z1 - HALL_T / 2 - 0.025), (-DW / 2 + 0.03 + lw, 2.12, z1 - HALL_T / 2 + 0.025))])
    col("Hall_Floor", (-hw_, -0.3, z1), (hw_, 0.0, z0))
    col("Hall_Ceiling", (-hw_, HALL_H, z1), (hw_, HALL_H + 0.2, z0))
    col("Hall_Wall_W", (-hw_ - HALL_T, -0.3, z1 - HALL_T), (-hw_, HALL_H + 0.2, z0))
    col("Hall_Wall_E", (hw_, -0.3, z1 - HALL_T), (hw_ + HALL_T, HALL_H + 0.2, z0))
    col("Hall_End_W", (-hw_, 0.0, z1 - HALL_T), (-DW / 2, HALL_H, z1))
    col("Hall_End_E", (DW / 2, 0.0, z1 - HALL_T), (hw_, HALL_H, z1))
    col("Hall_End_Head", (-DW / 2, DH, z1 - HALL_T), (DW / 2, HALL_H, z1))
    # the layout: the stair door (the store's record, turned into the kit frame), the hallway's far door, their links
    leaf = [d for d in json.loads((KITDIR / "stair_door_source.json").read_text())["bk_doors_stair"] if d["name"] == f"DoorLeaf_Stair_{STAIR_KEY}_up"][0]
    door("stair", hinge, leaf["width"], leaf["height"], 180.0, leaf["swing_deg"], props={"kind": "stair door", "from": f"store {leaf['name']}"})
    link("stair", (0.0, 0.0, 0.6), (0.0, 0.0, 0.95), (0, 1))
    door("hall_far", (-DW / 2 + 0.03, 0.0, z1 - HALL_T / 2), lw, 2.12, 0.0, 90.0, props={"kind": "hallway door"})
    link("hall_far", (0.0, 0.0, z1 + 0.6), (0.0, 0.0, z1 + 1.0), (0, 1))
    marker("Landing", (0.0, 0.0, 0.95), "Entrance")
    STAIR_NOTE.update({"kept_whole": sorted(set(kept)), "cut_at_top_step": cut, "leaf": leaf["name"], "door_centre_store_x": round(cx, 4),
                       "head_wall_face_store_y": face_y, "floor_store_z": fy})
    # context: the store's stairs going down from the top step (the store's flight: 3.2 m over 4.62 m), and dark beyond
    n, rise, run = 12, 3.2 / 12, 4.62 / 12
    boxes("ctx_Steps", "Ctx_Step", "ctx", [((-1.15, -(i + 1) * rise, LAND + i * run), (1.15, -i * rise, LAND + (i + 1) * run)) for i in range(n)], coll=CONTEXT)
    boxes("ctx_ShaftWalls", "Stair_Wall", "ctx", [((-1.35, -3.4, LAND), (-1.15, HALL_H, LAND + 4.8)), ((1.15, -3.4, LAND), (1.35, HALL_H, LAND + 4.8)),
                                                 ((-1.35, HALL_H, LAND), (1.35, HALL_H + 0.2, LAND + 4.8))], coll=CONTEXT)
    # lights (night): the landing's panel; the hallway's lamps
    hz = (to_kit(parts[f"Stair_{STAIR_KEY}_lower_tube"]["boxes"][0]["min"])[2] + to_kit(parts[f"Stair_{STAIR_KEY}_lower_tube"]["boxes"][0]["max"])[2]) / 2
    light("Landing_Panel", "AREA", (0.0, HALL_H - 0.1, hz), 70.0, (1.0, 0.96, 0.84), size=0.56, size_y=1.16)
    for i, z in enumerate(lamps):
        light(f"Hall_Lamp_{i}", "AREA", (0.0, HALL_H - 0.07, z), 45.0, (1.0, 0.95, 0.80), size=0.8, size_y=0.4)
    setup_world((0.01, 0.01, 0.012), 1.0)


STAIR_NOTE = {}


def cams_stair():
    return {"1_landing": ((0.3, 1.55, 2.9), (0.0, 1.2, -1.0), 64.0, {"hide": ["Leaf_stair"]}),
            "2_door_shut": ((-0.7, 1.55, 1.45), (0.25, 1.1, -0.2), 64.0, {}),
            "3_hallway": ((0.5, 1.55, -0.6), (-0.2, 1.2, -10.4), 60.0, {"hide": ["Leaf_stair"]})}


# ================================================================ piece 3: the safe house (the roof's, tools/blender/build_hotel_greybox.py roof())
# The greybox's room is x -11 to -5, z -11 to -6 on the roof, 2.8 m high, its 1.0 m opening in the south wall at x -8. The kit frame is the roof's
# moved by (+8, 0, +5.8): the opening's middle on the outer face of the south wall.
SH_DX, SH_DZ = 8.0, 5.8
SH_X0, SH_X1, SH_Z0, SH_Z1, SH_H = -3.0, 3.0, -5.2, -0.2, 2.8


def R(x, z):
    """A roof point (greybox) -> the kit frame."""
    return (x + SH_DX, z + SH_DZ)


def mats_safe():
    material("SH_Floor", diff="old_wood_floor_diff_1k.jpg", tint=(0.92, 0.86, 0.78), rough=0.6, tile=2.0)
    material("SH_Wall", diff="plastered_wall_04_diff_1k.jpg", tint=(0.62, 0.70, 0.60), rough=0.9, tile=2.2)       # the greybox's "safe" sage
    material("SH_Ceiling", diff="plastered_wall_04_diff_1k.jpg", tint=(0.92, 0.90, 0.84), rough=0.95, tile=2.4)
    material("SH_Trim", diff="dark_wood_diff_1k.jpg", tint=(0.86, 0.76, 0.66), rough=0.6, tile=0.9)               # skirting, dado, casings, counter top
    material("SH_Wood", diff="dark_wood_diff_1k.jpg", tint=(1.0, 0.92, 0.82), rough=0.65, tile=1.0)               # counter, desk, bench top, shelves
    material("SH_Ply", diff="plywood_diff_1k.jpg", tint=(0.95, 0.90, 0.80), rough=0.8, tile=0.9)                  # the stash crates, the pegboard
    material("SH_Steel", diff="painted_metal_shutter_diff_1k.jpg", tint=(0.42, 0.50, 0.52), rough=0.5, tile=1.0)  # the locker, the vice, the till
    material("SH_Iron", color=(0.10, 0.10, 0.10), rough=0.55)                                                        # straps, legs, the lamp's arm
    material("SH_Goods", diff="rough_linen_diff_512.jpg", tint=(0.72, 0.48, 0.34), rough=0.9, tile=0.5)          # tins, jars, packets on the shelf
    material("SH_Paper", color=(0.82, 0.79, 0.70), rough=0.9)                                                        # the ledger's pages, labels
    material("SH_Cloth", diff="rough_linen_diff_512.jpg", tint=(0.55, 0.20, 0.17), rough=1.0, tile=1.0)          # the runner under the desk, the ledger's cover
    material("SH_Pad", diff="concrete_floor_02_diff_1k.jpg", tint=(0.48, 0.52, 0.52), rough=0.6, tile=1.2)       # the respawn pad's stone
    material("Kit_Lamp_Emit", rough=0.3, emit=((0.95, 0.84, 0.66), 18.0))
    material("Kit_Save_Glow", rough=0.3, emit=((0.35, 0.85, 0.50), 1.5))
    material("Kit_Respawn_Glow", rough=0.3, emit=((0.45, 0.90, 0.85), 5.0))
    material("SH_Outside", diff="plastered_wall_04_diff_1k.jpg", tint=(0.58, 0.60, 0.56), rough=0.9, tile=2.2)
    material("Ctx_Roof", diff="concrete_floor_02_diff_1k.jpg", tint=(0.36, 0.36, 0.36), rough=0.95, tile=3.0)


def build_safe_house():
    x0, x1, z0, z1, H, T = SH_X0, SH_X1, SH_Z0, SH_Z1, SH_H, 0.2
    dh = 2.16
    node("safe_house")
    N = "safe_house"
    boxes("SH_Floor", "SH_Floor", N, [((x0 - T, -0.3, z0 - T), (x1 + T, 0.0, z1 + T), ("-y", "-x", "+x", "-z", "+z"))])
    boxes("SH_Ceiling", "SH_Ceiling", N, [((x0 - T, H, z0 - T), (x1 + T, H + 0.2, z1 + T), ("+y", "-x", "+x", "-z", "+z"))])
    walls = [((x0 - T, 0.0, z0 - T), (x1 + T, H, z0)), ((x0 - T, 0.0, z0), (x0, H, z1)), ((x1, 0.0, z0), (x1 + T, H, z1)),
             ((x0 - T, 0.0, z1), (-0.5, H, z1 + T)), ((0.5, 0.0, z1), (x1 + T, H, z1 + T)), ((-0.5, dh, z1), (0.5, H, z1 + T))]
    outer = ["-z", "-x", "+x", "+z", "+z", "+z"]
    boxes("SH_Walls", "SH_Wall", N, [(mn, mx, (o,)) for (mn, mx), o in zip(walls, outer)])
    # the outside (seen from the roof): its own material, so the roof's bake can light it and the room's table stays the room's
    X0, X1, Z0, Z1, Y1 = x0 - T, x1 + T, z0 - T, z1 + T, H + 0.2
    def skin(bm):
        quad(bm, [(X0, 0, Z0), (X1, 0, Z0), (X1, Y1, Z0), (X0, Y1, Z0)], (0, 0, -1))
        quad(bm, [(X0, 0, Z0), (X0, 0, Z1), (X0, Y1, Z1), (X0, Y1, Z0)], (-1, 0, 0))
        quad(bm, [(X1, 0, Z0), (X1, 0, Z1), (X1, Y1, Z1), (X1, Y1, Z0)], (1, 0, 0))
        quad(bm, [(X0, Y1, Z0), (X1, Y1, Z0), (X1, Y1, Z1), (X0, Y1, Z1)], (0, 1, 0))
        for a, b, ya, yb in ((X0, -0.5, 0, Y1), (0.5, X1, 0, Y1), (-0.5, 0.5, dh, Y1)):
            quad(bm, [(a, ya, Z1), (b, ya, Z1), (b, yb, Z1), (a, yb, Z1)], (0, 0, 1))
    part("SH_Exterior", "SH_Outside", skin, N)
    boxes("decor_SH_Lantern", "SH_Iron", N, [((0.8, 2.05, Z1), (0.96, 2.35, Z1 + 0.14))])
    part("decor_SH_Lantern_Glass", "Kit_Lamp_Emit", lambda bm: box(bm, (0.82, 2.09, Z1 + 0.02), (0.94, 2.3, Z1 + 0.13), ("-z",)), N)
    names = ["Wall_N", "Wall_W", "Wall_E", "Wall_S_W", "Wall_S_E", "Wall_S_Head"]
    for nm, (mn, mx) in zip(names, walls):
        col("SH_" + nm, mn, mx)
    col("SH_Floor", (x0 - T, -0.05, z0 - T), (x1 + T, 0.0, z1 + T))            # the slabs' visible faces (their edges are the exterior skin)
    col("SH_Ceiling", (x0 - T, H, z0 - T), (x1 + T, H + 0.05, z1 + T))
    # skirting and a dado rail round the room (not across the opening), door casings inside and out
    sk, dd = [], []
    for (a, b, c, axis, d) in ((x0, x1, z0, "x", +1), (x0, -0.5, z1, "x", -1), (0.5, x1, z1, "x", -1), (z0, z1, x0, "z", +1), (z0, z1, x1, "z", -1)):
        if axis == "x":
            lo, hi = (c, c + 0.02) if d > 0 else (c - 0.02, c)
            sk.append(((a, 0.0, lo), (b, 0.12, hi)))
            dd.append(((a, 0.92, min(lo, hi) if d > 0 else lo - 0.005), (b, 0.96, hi + 0.005 if d > 0 else hi)))
        else:
            lo, hi = (c, c + 0.02) if d > 0 else (c - 0.02, c)
            sk.append(((lo, 0.0, a), (hi, 0.12, b)))
            dd.append(((lo - (0 if d > 0 else 0.005), 0.92, a), (hi + (0.005 if d > 0 else 0), 0.96, b)))
    boxes("SH_Skirting", "SH_Trim", N, sk)
    boxes("decor_SH_Dado", "SH_Trim", N, dd)
    cas = []
    for zz, zt in ((z1 - 0.025, z1), (z1 + T, z1 + T + 0.025)):
        cas += [((-0.6, 0.0, zz), (-0.5, dh + 0.1, zt)), ((0.5, 0.0, zz), (0.6, dh + 0.1, zt)), ((-0.6, dh, zz), (0.6, dh + 0.1, zt))]
    boxes("SH_Casing", "SH_Trim", N, cas)
    boxes("SH_Reveal", "SH_Trim", N, [((-0.5, 0.0, z1), (-0.49, dh, z1 + T)), ((0.49, 0.0, z1), (0.5, dh, z1 + T)), ((-0.5, dh - 0.01, z1), (0.5, dh, z1 + T))])
    # 1. the shop counter (greybox SH_Counter, x -10.8 to -9.0, z -10.8 to -10.2, 1.0 m): a wooden counter, a till, a bell; shelves of goods behind
    (cx0, cz0), (cx1, cz1) = R(-10.8, -10.8), R(-9.0, -10.2)
    boxes("SH_Counter", "SH_Wood", N, [((cx0, 0.0, cz0), (cx1, 0.94, cz1 - 0.03)), ((cx0 + 0.04, 0.0, cz1 - 0.03), (cx1 - 0.04, 0.1, cz1 - 0.01))])
    boxes("SH_CounterTop", "SH_Trim", N, [((cx0 - 0.02, 0.94, cz0), (cx1 + 0.02, 1.0, cz1 + 0.02))])
    col("SH_Counter", (cx0 - 0.02, 0.0, cz0), (cx1 + 0.02, 1.0, cz1 + 0.02))
    tx = cx0 + 0.45
    boxes("decor_SH_Till", "SH_Steel", N, [((tx - 0.18, 1.0, cz0 + 0.12), (tx + 0.18, 1.12, cz0 + 0.42)), ((tx - 0.16, 1.12, cz0 + 0.14), (tx + 0.16, 1.26, cz0 + 0.24))])
    part("decor_SH_Bell", "Door_Handle" if "Door_Handle" in MATS else "SH_Steel", lambda bm: cyl(bm, (cx1 - 0.3, 1.0, cz1 - 0.2), (cx1 - 0.3, 1.07, cz1 - 0.2), 0.045, 0.02, seg=12), N, smooth=True)
    shelf = []
    for y in (1.45, 1.85, 2.25):
        shelf.append(((cx0, y, z0), (cx1, y + 0.03, z0 + 0.26)))
    shelf += [((cx0, 1.3, z0), (cx0 + 0.03, 2.4, z0 + 0.26)), ((cx1 - 0.03, 1.3, z0), (cx1, 2.4, z0 + 0.26))]
    boxes("decor_SH_Shelves", "SH_Wood", N, shelf)
    rng = np.random.default_rng(11)
    goods = []
    for y in (1.45, 1.85, 2.25):
        x = cx0 + 0.06
        while x < cx1 - 0.15:
            w = 0.07 + rng.random() * 0.1
            h = 0.1 + rng.random() * 0.18
            goods.append(((x, y + 0.03, z0 + 0.04), (x + w, y + 0.03 + h, z0 + 0.04 + 0.08 + rng.random() * 0.1)))
            x += w + 0.02 + rng.random() * 0.05
    boxes("decor_SH_Goods", "SH_Goods", N, goods)
    # 2. the stash (greybox SH_Stash, x -6.0 to -5.2, z -10.8 to -10.0, 1.0 m): two plywood crates under a strapped trunk
    (sx0, sz0), (sx1, sz1) = R(-6.0, -10.8), R(-5.2, -10.0)
    boxes("SH_Stash_Crates", "SH_Ply", N, [((sx0, 0.0, sz0), (sx1, 0.45, sz1)), ((sx0 + 0.02, 0.45, sz0 + 0.02), (sx1 - 0.02, 0.92, sz1 - 0.02))])
    boxes("SH_Stash_Straps", "SH_Iron", N, [((sx0 + 0.15, 0.45, sz0 + 0.01), (sx0 + 0.2, 0.93, sz1 - 0.01)), ((sx1 - 0.2, 0.45, sz0 + 0.01), (sx1 - 0.15, 0.93, sz1 - 0.01)),
                                            ((sx0 - 0.005, 0.2, sz0 - 0.005), (sx1 + 0.005, 0.24, sz1 + 0.005)),
                                            ((sx0 + 0.32, 0.78, sz1 - 0.02), (sx0 + 0.48, 0.86, sz1 - 0.005))])
    boxes("SH_Stash_Lid", "SH_Wood", N, [((sx0 + 0.01, 0.92, sz0 + 0.01), (sx1 - 0.01, 1.0, sz1 - 0.01))])
    col("SH_Stash", (sx0 - 0.005, 0.0, sz0 - 0.005), (sx1 + 0.005, 1.0, sz1 + 0.005))
    # 3. the save point (new; the greybox has its spot only, at x -7.0, z -10.4 facing north): a writing desk on the north wall, an open guest
    #    ledger, a lamp with a green glass shade
    (vx, vz) = R(-7.0, -10.4)
    dz1 = vz - 0.3
    boxes("SH_Desk", "SH_Wood", N, [((vx - 0.35, 0.74, z0), (vx + 0.35, 0.78, dz1)), ((vx - 0.35, 0.0, z0), (vx - 0.31, 0.74, dz1)),
                                    ((vx + 0.31, 0.0, z0), (vx + 0.35, 0.74, dz1)), ((vx - 0.31, 0.6, z0), (vx + 0.31, 0.74, dz1)),
                                    ((vx - 0.31, 0.0, z0), (vx + 0.31, 0.6, dz1 - 0.02))])          # a bureau: a drawer under the top, a cupboard below
    boxes("decor_SH_Desk_Knobs", "SH_Iron", N, [((vx - 0.02, 0.64, dz1), (vx + 0.02, 0.68, dz1 + 0.02)), ((vx + 0.2, 0.3, dz1 - 0.02), (vx + 0.23, 0.36, dz1))])
    col("SH_Save_Desk", (vx - 0.35, 0.0, z0), (vx + 0.35, 0.78, dz1))
    boxes("decor_SH_Ledger", "SH_Cloth", N, [((vx - 0.2, 0.78, dz1 - 0.24), (vx + 0.12, 0.795, dz1 - 0.03))])
    boxes("decor_SH_Pages", "SH_Paper", N, [((vx - 0.19, 0.795, dz1 - 0.235), (vx - 0.04, 0.81, dz1 - 0.035)), ((vx - 0.035, 0.795, dz1 - 0.235), (vx + 0.11, 0.81, dz1 - 0.035))])
    lx, lz = vx + 0.22, z0 + 0.1
    part("decor_SH_Lamp_Stand", "SH_Iron", lambda bm: [cyl(bm, (lx, 0.78, lz), (lx, 0.8, lz), 0.06, seg=12), cyl(bm, (lx, 0.8, lz), (lx, 1.08, lz), 0.008, seg=6)], N, smooth=True)
    part("decor_SH_Lamp_Shade", "Kit_Save_Glow", lambda bm: cyl(bm, (lx, 1.08, lz + 0.02), (lx, 1.08, lz - 0.02), 0.03, seg=12) if False else
         box(bm, (lx - 0.12, 1.06, lz - 0.05), (lx + 0.12, 1.12, lz + 0.05)), N)
    # 4. the crafting bench (greybox SH_Bench, x -5.8 to -5.2, z -8.6 to -7.0, 0.9 m): a heavy bench, a vice, tools on a pegboard above it
    (bx0, bz0), (bx1, bz1) = R(-5.8, -8.6), R(-5.2, -7.0)
    boxes("SH_Bench_Top", "SH_Wood", N, [((bx0, 0.84, bz0), (bx1, 0.9, bz1))])
    boxes("SH_Bench_Frame", "SH_Iron", N, [((bx0 + 0.03, 0.0, bz0 + 0.03), (bx0 + 0.08, 0.84, bz0 + 0.08)), ((bx1 - 0.08, 0.0, bz0 + 0.03), (bx1 - 0.03, 0.84, bz0 + 0.08)),
                                           ((bx0 + 0.03, 0.0, bz1 - 0.08), (bx0 + 0.08, 0.84, bz1 - 0.03)), ((bx1 - 0.08, 0.0, bz1 - 0.08), (bx1 - 0.03, 0.84, bz1 - 0.03)),
                                           ((bx0 + 0.03, 0.18, bz0 + 0.03), (bx1 - 0.03, 0.22, bz1 - 0.03))])
    # under the top: a drawer cabinet at each end and boxes of parts on the shelf, so the bench reads (and collides) as one solid block
    boxes("SH_Bench_Cabinets", "SH_Ply", N, [((bx0 + 0.04, 0.0, bz0 + 0.04), (bx1 - 0.04, 0.84, bz0 + 0.62)), ((bx0 + 0.04, 0.0, bz1 - 0.62), (bx1 - 0.04, 0.84, bz1 - 0.04)),
                                             ((bx0 + 0.05, 0.0, bz0 + 0.62), (bx1 - 0.04, 0.84, bz1 - 0.62))])
    boxes("decor_SH_Bench_Pulls", "SH_Iron", N, [((bx0 + 0.02, y, bz0 + 0.25), (bx0 + 0.04, y + 0.02, bz0 + 0.41)) for y in (0.25, 0.5, 0.72)] +
          [((bx0 + 0.02, y, bz1 - 0.41), (bx0 + 0.04, y + 0.02, bz1 - 0.25)) for y in (0.25, 0.5, 0.72)])
    col("SH_Bench", (bx0, 0.0, bz0), (bx1, 0.9, bz1))
    boxes("decor_SH_Vice", "SH_Steel", N, [((bx0 + 0.02, 0.9, bz1 - 0.3), (bx0 + 0.2, 1.02, bz1 - 0.12)), ((bx0 - 0.04, 0.93, bz1 - 0.24), (bx0 + 0.02, 1.0, bz1 - 0.18))])
    boxes("decor_SH_Pegboard", "SH_Ply", N, [((x1 - 0.015, 1.05, bz0 + 0.1), (x1, 2.0, bz1 - 0.1))])
    tools = []
    for i, zz in enumerate(np.linspace(bz0 + 0.25, bz1 - 0.25, 6)):
        ln = 0.2 + 0.12 * ((i * 7) % 3)
        tools.append(((x1 - 0.04, 1.7 - ln, zz - 0.015), (x1 - 0.015, 1.7, zz + 0.015)))
        tools.append(((x1 - 0.05, 1.7, zz - 0.04 - 0.02 * (i % 2)), (x1 - 0.015, 1.76, zz + 0.04)))
    boxes("decor_SH_Tools", "SH_Iron", N, tools)
    boxes("decor_SH_Parts", "SH_Goods", N, [((bx0 + 0.12, 0.9, bz0 + 0.2), (bx0 + 0.32, 0.98, bz0 + 0.5)), ((bx0 + 0.3, 0.9, bz0 + 0.62), (bx0 + 0.45, 0.94, bz0 + 0.74))])
    # 5. the locker (greybox SH_Locker, x -10.8 to -10.3, z -7.4 to -6.6, 2.0 m): a steel locker, vents, a handle, a number plate
    (kx0, kz0), (kx1, kz1) = R(-10.8, -7.4), R(-10.3, -6.6)
    boxes("SH_Locker", "SH_Steel", N, [((kx0, 0.0, kz0), (kx1, 2.0, kz1))])
    col("SH_Locker", (kx0, 0.0, kz0), (kx1 + 0.02, 2.0, kz1))
    lk = [((kx1, 0.08, kz0 + 0.03), (kx1 + 0.006, 1.97, (kz0 + kz1) / 2 - 0.01)), ((kx1, 0.08, (kz0 + kz1) / 2 + 0.01), (kx1 + 0.006, 1.97, kz1 - 0.03))]
    boxes("decor_SH_Locker_Doors", "SH_Steel", N, lk)
    vents = []
    for half in (kz0 + 0.03, (kz0 + kz1) / 2 + 0.01):
        for i in range(5):
            y = 1.7 + i * 0.04
            vents.append(((kx1 + 0.006, y, half + 0.07), (kx1 + 0.012, y + 0.015, half + 0.3)))
        vents.append(((kx1 + 0.006, 1.0, half + 0.3), (kx1 + 0.02, 1.16, half + 0.33)))
    boxes("decor_SH_Locker_Vents", "SH_Iron", N, vents)
    # 6. the respawn pad (greybox decor_Respawn_Pad, x -8.6 to -7.4, z -9.2 to -8.0): a round stone pad, its ring glowing
    (px, pz) = R(-8.0, -8.6)
    part("decor_SH_Pad", "SH_Pad", lambda bm: cyl(bm, (px, 0.0, pz), (px, 0.03, pz), 0.6, seg=32), N, smooth=False)
    def ring(bm):
        n = 32
        for k in range(n):
            a, b = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
            for r0, r1 in ((0.47, 0.52),):
                quad(bm, [(px + r0 * math.cos(a), 0.032, pz + r0 * math.sin(a)), (px + r1 * math.cos(a), 0.032, pz + r1 * math.sin(a)),
                          (px + r1 * math.cos(b), 0.032, pz + r1 * math.sin(b)), (px + r0 * math.cos(b), 0.032, pz + r0 * math.sin(b))], (0, 1, 0))
    part("decor_SH_Pad_Ring", "Kit_Respawn_Glow", ring, N)
    # the light: a pendant in the middle, a small shade over the bench
    part("decor_SH_Pendant", "SH_Iron", lambda bm: [cyl(bm, (0, H, -2.7), (0, H - 0.5, -2.7), 0.006, seg=6), cyl(bm, (0, H - 0.5, -2.7), (0, H - 0.68, -2.7), 0.05, 0.22, seg=20, cap=False)], N, smooth=True)
    part("decor_SH_Pendant_Bulb", "Kit_Lamp_Emit", lambda bm: sphere(bm, (0, H - 0.66, -2.7), 0.05), N, smooth=True)
    # the layout: the spots exactly where the greybox has them, the safe zone, the way in (an opening, as the greybox: no leaf)
    for kind, (gx, gz), face in (("shop", (-9.9, -9.5), (0, -1)), ("stash", (-5.6, -9.4), (0, -1)), ("save", (-7.0, -10.4), (0, -1)),
                                 ("craft", (-6.3, -7.8), (1, 0)), ("respawn", (-8.0, -8.6), (0, 1)), ("locker", (-9.8, -7.0), (-1, 0))):
        kx, kz = R(gx, gz)
        spot(kind, 1, (round(kx, 3), 0.0, round(kz, 3)), face=face)
    zone("safe", "safe_house", (x0, 0.0, z0), (x1, H, z1))
    marker("Door", (0.0, 0.0, -0.8), "Entrance")
    # context: the roof outside (the stills only)
    boxes("ctx_Roof", "Ctx_Roof", "ctx", [((-5.0, -0.3, z1 + T), (5.0, 0.0, 4.0))], coll=CONTEXT)
    # lights (soft): one large dim ceiling panel for the even fill, the pendant, the desk lamp's and the pad's glow, a little night outside
    light("Ceiling_Fill", "AREA", (0.0, H - 0.02, -2.7), 190.0, (1.0, 0.90, 0.78), size=3.6, size_y=3.0)
    light("Pendant", "POINT", (0, H - 0.66, -2.7), 45.0, (1.0, 0.82, 0.62), size=0.08)
    light("Desk_Lamp", "POINT", (lx, 1.0, lz), 3.0, (0.5, 1.0, 0.6), size=0.05)
    light("Lantern", "POINT", (0.88, 2.2, Z1 + 0.08), 12.0, (1.0, 0.82, 0.6), size=0.04)
    light("Pad_Glow", "AREA", (px, 0.06, pz), 6.0, (0.5, 1.0, 0.95), size=1.0, direction=(0, 1, 0))
    setup_world((0.02, 0.025, 0.05), 1.0)


def cams_safe():
    return {"1_doorway": ((0.0, 1.55, 2.6), (0.0, 1.1, -4.0), 66.0, {}),
            "2_wide": ((2.6, 1.6, -0.55), (-1.6, 0.9, -4.2), 76.0, {}),
            "3_shop_and_save": ((0.6, 1.5, -2.2), (-1.2, 1.1, -5.2), 64.0, {})}


# ================================================================ piece 4: the painted-sky hall with an EXIT door
SKY_L, SKY_W, SKY_H = 10.0, 2.4, 3.0


def mats_sky():
    g = {"sky": mk_image("Painted_Sky", painted_sky_pixels(dim=0.88)), "ceil": mk_image("Painted_Sky_Ceiling", painted_sky_pixels(seed=8, flat=True)),
         "exit": mk_image("Exit_Sign", text_pixels("EXIT", 256, 96, (0.88, 1.0, 0.9), (0.04, 0.42, 0.16)))}
    material("Sky_Mural", img=g["sky"], rough=0.9, tile=4.0)                       # the walls above the dado: the painted sky
    material("Kit_Sky_Emit", img=g["ceil"], rough=0.9, emit=(None, 2.9), tile=4.0)   # the laylight overhead: a sky lit from behind (the hall's light)
    material("Sky_Panel", diff="plastered_wall_04_diff_1k.jpg", tint=(0.97, 0.97, 0.95), rough=0.7, tile=1.6)     # the white wainscot
    material("Sky_Trim", diff="plastered_wall_04_diff_1k.jpg", tint=(0.93, 0.93, 0.90), rough=0.5, tile=1.2)      # dado rail, skirting, cornice, casings
    material("Sky_Floor", diff="herringbone_parquet_diff_1k.jpg", tint=(0.92, 0.88, 0.84), rough=0.5, tile=2.0)
    material("Sky_Door", diff="plastered_wall_04_diff_1k.jpg", tint=(0.90, 0.90, 0.88), rough=0.45, tile=1.4)
    material("Door_Handle", color=(0.50, 0.40, 0.22), rough=0.35)
    material("Kit_Exit_Emit", img=g["exit"], rough=0.3, emit=(None, 4.0), tile=1.0)
    material("Ctx_Dark", color=(0.05, 0.05, 0.05), rough=1.0)


def build_sky_hall():
    hw, L, H, T = SKY_W / 2, SKY_L, SKY_H, 0.2
    z0, z1 = -T, -T - L                                  # the hall's inside runs from the entry wall's inner face to the exit wall's
    N = "sky_hall"
    node(N)
    DADO, CORN = 1.0, H - 0.12
    boxes("Sky_Floor", "Sky_Floor", N, [((-hw, -0.3, z1), (hw, 0.0, z0), ("-y",))])
    # the walls; their outer faces are left out (the host's wall stands there, or nothing is seen: the hall is entered through its doors)
    walls = [((-hw - T, 0.0, z1 - T), (-hw, H, z0 + T), ("-x",)), ((hw, 0.0, z1 - T), (hw + T, H, z0 + T), ("+x",))]
    ends = []
    for (za, zb), out in (((z0, 0.0), "+z"), ((z1 - T, z1), "-z")):
        ends += [((-hw, 0.0, za), (-DW / 2, H, zb), (out,)), ((DW / 2, 0.0, za), (hw, H, zb), (out,)), ((-DW / 2, DH, za), (DW / 2, H, zb), (out,))]
    def mural_uv(bm):
        box_uv(bm, 4.0)
        uvl = bm.loops.layers.uv["UVMap"]
        for f in bm.faces:                               # the sky's pale horizon low on the wall: v from the dado (the picture's bottom row) up
            for lp in f.loops:
                gy = lp.vert.co.z
                u, _ = lp[uvl].uv
                lp[uvl].uv = (u, (gy - DADO) / (H - DADO) * 0.98 + 0.01)
    sky_parts = [((mn[0], max(mn[1], DADO), mn[2]), mx, sk) for mn, mx, sk in walls + ends if mx[1] > DADO]
    part("Sky_Walls", "Sky_Mural", lambda bm: [box(bm, a, b, sk + (("-y",) if a[1] == DADO else ())) for a, b, sk in sky_parts], N, uv_fn=mural_uv)
    low = [((mn[0], mn[1], mn[2]), (mx[0], min(mx[1], DADO), mx[2]), sk + ("+y", "-y")) for mn, mx, sk in walls + ends if mn[1] < DADO]
    boxes("Sky_Wainscot", "Sky_Panel", N, low)
    walls = [w[:2] for w in walls]
    ends = [e[:2] for e in ends]
    for i, (mn, mx) in enumerate(walls):
        col(f"Sky_Wall_{'W' if i == 0 else 'E'}", mn, mx)
    for i, (mn, mx) in enumerate(ends):
        col(f"Sky_End_{i}", mn, mx)
    col("Sky_Floor", (-hw, -0.3, z1), (hw, 0.0, z0))
    col("Sky_Ceiling", (-hw - T, H, z1 - T), (hw + T, H + 0.25, z0 + T))
    # the ceiling: a white frame of coffers round the laylight, which shows the painted sky lit from behind
    cof = [((-hw, H - 0.02, z1), (-hw + 0.25, H, z0)), ((hw - 0.25, H - 0.02, z1), (hw, H, z0)), ((-hw, H - 0.02, z1), (hw, H, z1 + 0.25)), ((-hw, H - 0.02, z0 - 0.25), (hw, H, z0))]
    ribs = [z for z in np.linspace(z1 + 0.25, z0 - 0.25, 6)[1:-1]]
    cof += [((-hw + 0.25, H - 0.08, z - 0.06), (hw - 0.25, H - 0.02, z + 0.06)) for z in ribs]
    cof += [((-0.03, H - 0.08, z1 + 0.25), (0.03, H - 0.02, z0 - 0.25))]
    boxes("Sky_Coffers", "Sky_Trim", N, cof)
    boxes("Sky_CeilingSlab", "Sky_Trim", N, [((-hw - T, H, z1 - T), (hw + T, H + 0.25, z0 + T), ("+y",))])
    part("Sky_Laylight", "Kit_Sky_Emit", lambda bm: quad(bm, [(-hw + 0.25, H - 0.01, z1 + 0.25), (hw - 0.25, H - 0.01, z1 + 0.25), (hw - 0.25, H - 0.01, z0 - 0.25),
                                                          (-hw + 0.25, H - 0.01, z0 - 0.25)], (0, -1, 0)), N,
         uv_fn=lambda bm: box_uv(bm, 4.0))
    # trim: skirting, dado rail, cornice along both long walls and the ends; casings at both doors
    trim = []
    for x, s in ((-hw, 1), (hw, -1)):
        a, b = (x, x + 0.02 * s) if s > 0 else (x + 0.02 * s, x)
        trim += [((min(a, b), 0.0, z1), (max(a, b), 0.14, z0)), ((min(a, b) - (0.01 if s < 0 else 0), DADO - 0.03, z1), (max(a, b) + (0.01 if s > 0 else 0), DADO + 0.03, z0)),
                 ((min(a, b) - (0.04 if s < 0 else 0), CORN, z1), (max(a, b) + (0.04 if s > 0 else 0), H - 0.02, z0))]
    for zf, s in ((z0, -1), (z1, 1)):
        za, zb = (zf, zf + 0.02) if s > 0 else (zf - 0.02, zf)
        for xa, xb in ((-hw, -DW / 2 - 0.1), (DW / 2 + 0.1, hw)):
            trim += [((xa, 0.0, za), (xb, 0.14, zb)), ((xa, DADO - 0.03, min(za, zb) - (0.01 if s < 0 else 0)), (xb, DADO + 0.03, max(za, zb) + (0.01 if s > 0 else 0)))]
        trim += [((-hw, CORN, min(za, zb) - (0.04 if s < 0 else 0)), (hw, H - 0.02, max(za, zb) + (0.04 if s > 0 else 0)))]
        trim += [((-DW / 2 - 0.1, 0.0, za), (-DW / 2, DH + 0.1, zb)), ((DW / 2, 0.0, za), (DW / 2 + 0.1, DH + 0.1, zb)), ((-DW / 2 - 0.1, DH, za), (DW / 2 + 0.1, DH + 0.1, zb))]
    boxes("Sky_Trim", "Sky_Trim", N, trim)
    # the outside faces of the two doors (the host's side): casings
    boxes("Sky_Casing_Out", "Sky_Trim", N, [((-DW / 2 - 0.1, 0.0, 0.0), (-DW / 2, DH + 0.1, 0.025)), ((DW / 2, 0.0, 0.0), (DW / 2 + 0.1, DH + 0.1, 0.025)),
                                             ((-DW / 2 - 0.1, DH, 0.0), (DW / 2 + 0.1, DH + 0.1, 0.025)),
                                             ((-DW / 2 - 0.1, 0.0, z1 - T - 0.025), (-DW / 2, DH + 0.1, z1 - T)), ((DW / 2, 0.0, z1 - T - 0.025), (DW / 2 + 0.1, DH + 0.1, z1 - T)),
                                             ((-DW / 2 - 0.1, DH, z1 - T - 0.025), (DW / 2 + 0.1, DH + 0.1, z1 - T))])
    # the doors: the entry (hinged on the west jamb) and the EXIT door (hinged on the east jamb), white panel doors with brass levers
    lw = DW - 0.06
    for nm, zc, hx, yaw in (("entry", z0 + T / 2, -DW / 2 + 0.03, 0.0), ("exit", z1 - T / 2, DW / 2 - 0.03, 180.0)):
        node(f"Leaf_{nm}", pivot=(hx, 0.0, zc), yaw=yaw)
        xa, xb = (hx, hx + lw) if yaw == 0 else (hx - lw, hx)
        boxes(f"Leaf_{nm}_Slab", "Sky_Door", f"Leaf_{nm}", [((xa, 0.0, zc - 0.025), (xb, 2.12, zc + 0.025))])
        pnl = []
        for (ya, yb) in ((0.2, 0.95), (1.1, 1.95)):
            for zz in (zc - 0.033, zc + 0.025):
                pnl.append(((xa + 0.12, ya, zz), (xb - 0.12, yb, zz + 0.008)))
        boxes(f"decor_Leaf_{nm}_Panels", "Sky_Trim", f"Leaf_{nm}", pnl)
        fx = xb - 0.08 if yaw == 0 else xa + 0.08
        part(f"decor_Leaf_{nm}_Lever", "Door_Handle", lambda bm, fx=fx, zc=zc, yaw=yaw: [
            cyl(bm, (fx, 1.0, zc - 0.07), (fx, 1.0, zc + 0.07), 0.012, seg=10),
            box(bm, (fx - (0.12 if yaw == 0 else -0.0), 0.988, zc + 0.055), (fx + (0.0 if yaw == 0 else 0.12), 1.012, zc + 0.07)),
            box(bm, (fx - (0.12 if yaw == 0 else -0.0), 0.988, zc - 0.07), (fx + (0.0 if yaw == 0 else 0.12), 1.012, zc - 0.055))], f"Leaf_{nm}", smooth=True)
    # the EXIT sign over the far door, on the hall side: a green box, the word lit
    ey = DH + 0.22
    boxes("Sky_ExitBox", "Sky_Trim", N, [((-0.34, ey, z1), (0.34, ey + 0.26, z1 + 0.08))])
    def exit_face(bm):
        quad(bm, [(-0.3, ey + 0.02, z1 + 0.081), (0.3, ey + 0.02, z1 + 0.081), (0.3, ey + 0.24, z1 + 0.081), (-0.3, ey + 0.24, z1 + 0.081)], (0, 0, 1))
    def exit_uv(bm):
        uvl = bm.loops.layers.uv["UVMap"]
        for f in bm.faces:
            for lp in f.loops:
                p = lp.vert.co
                lp[uvl].uv = ((p.x + 0.3) / 0.6, (p.z - ey - 0.02) / 0.22)
    part("decor_Sky_ExitFace", "Kit_Exit_Emit", exit_face, N, uv_fn=exit_uv)
    # the layout: two doors, two links (where you press F to leave by each, and where you stand after coming in by it)
    door("entry", (-DW / 2 + 0.03, 0.0, z0 + T / 2), lw, 2.12, 0.0, 90.0, props={"kind": "hall door"})
    door("exit", (DW / 2 - 0.03, 0.0, z1 - T / 2), lw, 2.12, 180.0, 90.0, props={"kind": "EXIT door"})
    link("entry", (0.0, 0.0, z0 - 0.5), (0.0, 0.0, z0 - 0.9), (0, -1))
    link("exit", (0.0, 0.0, z1 + 0.5), (0.0, 0.0, z1 + 0.9), (0, 1))
    marker("Entry", (0.0, 0.0, z0 - 0.9), "Entrance")
    marker("Exit", (0.0, 0.0, z1 + 0.9), "Exit")
    # context: dark rooms outside both doors (the stills only)
    boxes("ctx_Outside", "Ctx_Dark", "ctx", [((-1.5, -0.3, 0.0), (1.5, 0.0, 2.0)), ((-1.5, -0.3, z1 - T - 2.0), (1.5, 0.0, z1 - T))], coll=CONTEXT)
    # lights (sky-lit): the laylight itself is the source (an emissive sky); a soft sky-blue area under it evens the long walls
    light("Laylight", "AREA", (0.0, H - 0.04, (z0 + z1) / 2), 126.0, (0.86, 0.92, 1.0), size=SKY_W - 0.5, size_y=L - 0.5)
    light("Exit_Glow", "AREA", (0.0, ey + 0.13, z1 + 0.12), 1.5, (0.3, 1.0, 0.45), size=0.6, size_y=0.22, direction=(0, 0, 1))
    setup_world((0.02, 0.02, 0.025), 1.0)


def cams_sky():
    return {"1_entry": ((0.35, 1.55, -0.6), (-0.15, 1.45, -10.4), 62.0, {}),
            "2_wall": ((-0.9, 1.5, -2.6), (1.2, 1.9, -6.5), 74.0, {}),
            "3_exit": ((0.4, 1.5, -7.0), (0.0, 1.6, -10.4), 58.0, {})}


SPEC = {
    "elevator": {"mats": mats_elevator, "build": build_elevator, "cams": cams_elevator, "page": 1024, "light": "night", "light_scale": 1.8},
    "stair_door": {"mats": mats_stair, "build": build_stair_door, "cams": cams_stair, "page": 1024, "light": "night", "light_scale": 1.25},
    "safe_house": {"mats": mats_safe, "build": build_safe_house, "cams": cams_safe, "page": 1024, "light": "soft", "keep_outside": True, "light_scale": 3.0},
    "sky_hall": {"mats": mats_sky, "build": build_sky_hall, "cams": cams_sky, "page": 1024, "light": "sky-lit", "light_scale": 1.3},
}


# ================================================================ stages
def clear_file():
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.lights, bpy.data.cameras, bpy.data.worlds):
        for d in list(coll):
            coll.remove(d)
    IMG_CACHE.clear()
    MATS.clear()
    TILES.clear()
    EMITS.clear()
    NODES.clear()


def build_all():
    global ART, LAYOUT, CONTEXT
    clear_file()
    sc = bpy.context.scene
    sc.name = f"kit_{PIECE}"
    ART = bpy.data.collections.new("Art")
    LAYOUT = bpy.data.collections.new("Layout")
    CONTEXT = bpy.data.collections.new("Context")
    lights = bpy.data.collections.new("Lights")
    for c in (ART, LAYOUT, CONTEXT, lights):
        sc.collection.children.link(c)
    SPEC[PIECE]["mats"]()
    SPEC[PIECE]["build"]()
    sc["kit_nodes"] = json.dumps(NODES)
    sc.unit_settings.system = "METRIC"


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
            devs = [d for d in prefs.devices if d.type != "CPU"]
            if devs:
                for d in prefs.devices:
                    d.use = d.type != "CPU"
                gpu = True
                break
    cy.device = "GPU" if gpu else "CPU"
    print("CYCLES device:", cy.device)
    return gpu


def make_export_objects():
    """Merge the Art meshes by (GLB node, material) into the Export collection; each node is an empty at its pivot (its yaw about y), the
    meshes its children, so the page can move a car, slide a leaf or swing a door by its node."""
    nodes = {k: (tuple(v[0]), v[1]) for k, v in json.loads(bpy.context.scene["kit_nodes"]).items()}
    if "Export" in bpy.data.collections:
        for o in list(bpy.data.collections["Export"].objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(bpy.data.collections["Export"])
    exp = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(exp)
    groups = {}
    for ob in bpy.data.collections["Art"].objects:
        key = (ob["node"], ob.data.materials[0].name)
        groups.setdefault(key, []).append(ob)
    empties = {}
    for nname, (piv, yaw) in nodes.items():
        if nname == "ctx" or not any(k[0] == nname for k in groups):
            continue
        e = bpy.data.objects.new(nname, None)
        e.location = B(piv)
        e.rotation_euler = (0, 0, math.radians(yaw))
        exp.objects.link(e)
        empties[nname] = e
    bpy.context.view_layer.update()
    out = []
    culled = [0, 0]
    # faces never seen are dropped before the merge: pressed against another surface (something within 2 cm in front of every sample point),
    # or, unless the piece is seen from outside (the safe house on the roof), turned to the void (nothing in front of any sample point: a
    # wall's outer skin, the car's roof). The rays see the Art and the Context only.
    LAYOUT.hide_viewport = True
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    keep_out = SPEC[PIECE].get("keep_outside", False)
    culled_mesh = {}
    for ob in bpy.data.collections["Art"].objects:
        tmp_bm = bmesh.new()
        tmp_bm.from_mesh(ob.data)
        mname = ob.data.materials[0].name
        if mname not in EMITS and not str(ob["node"]).startswith(DOOR_NODES):
            bad = []
            for f in tmp_bm.faces:
                c, n = f.calc_center_median(), f.normal
                pts = [c] + [c.lerp(v.co, 0.8) for v in f.verts]
                res = []
                for p in pts:
                    hit, loc, *_ = bpy.context.scene.ray_cast(dg, p + n * 0.001, n, distance=60.0)
                    res.append("near" if hit and (loc - p).length < 0.02 else ("void" if not hit else "seen"))
                if all(r == "near" for r in res) or (not keep_out and all(r == "void" for r in res)):
                    bad.append(f)
            culled[0] += len(bad)
            culled[1] += len(tmp_bm.faces)
            bmesh.ops.delete(tmp_bm, geom=bad, context="FACES")
        me = bpy.data.meshes.new("culled_" + ob.name)
        tmp_bm.to_mesh(me)
        tmp_bm.free()
        culled_mesh[ob.name] = me
    LAYOUT.hide_viewport = False
    print(f"  culled {culled[0]} of {culled[1]} faces never seen")
    for (nname, mname), obs in sorted(groups.items()):
        bm = bmesh.new()
        for ob in obs:
            tmp = culled_mesh[ob.name]
            tmp_bm = bmesh.new()
            tmp_bm.from_mesh(tmp)
            tmp_bm.to_mesh(tmp)
            tmp_bm.free()
            bm.from_mesh(tmp)
            bpy.data.meshes.remove(tmp)
        me = bpy.data.meshes.new(f"{nname}_{mname}")
        bm.to_mesh(me)
        bm.free()
        if not me.polygons:
            bpy.data.meshes.remove(me)
            continue
        me.materials.append(bpy.data.materials[mname])
        o = bpy.data.objects.new(f"{nname}_{mname}", me)
        exp.objects.link(o)
        if mname in EMITS:
            o.visible_shadow = False                      # a bulb or a lamp's lens round its light must not block it
        par = empties[nname]
        o.parent = par
        o.matrix_parent_inverse = par.matrix_world.inverted()
        out.append(o)
    return exp, out


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
    print(f"  page {page}: {a3:.1f} m2, {dens:.1f} px/m")
    for o in objs:
        o.data.uv_layers["UVMap"].active_render = True
    return dens


def srgb_encode(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def denoise_image(img, S):
    """OIDN through the compositor's Denoise node."""
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
    path = str(WORK / "dn.exr")
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=sc.name)
    r = bpy.data.images.load(path)
    a = np.empty(S * S * 4, np.float32)
    r.pixels.foreach_get(a)
    bpy.data.images.remove(r)
    cd = cam.data
    bpy.data.objects.remove(cam)
    bpy.data.cameras.remove(cd)
    bpy.data.scenes.remove(sc)
    bpy.data.node_groups.remove(ng)
    return a.reshape(S, S, 4)


def stage_bake():
    import time
    WORK.mkdir(parents=True, exist_ok=True)
    exp, objs = make_export_objects()
    for c in ("Art",):
        bpy.data.collections[c].hide_render = True
        bpy.data.collections[c].hide_viewport = True
    setup_cycles(SAMPLES, bake=True)
    set_emit_strength(None)
    S = SPEC[PIECE]["page"]
    bake_objs = [o for o in objs if o.data.materials[0].name not in EMITS]
    dens = lightmap_uv(bake_objs, S)
    t0 = time.time()
    img = bpy.data.images.new(f"LM_{PIECE}", S, S, alpha=False, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    for o in bake_objs:
        nt = o.data.materials[0].node_tree
        nd = nt.nodes.new("ShaderNodeTexImage")
        nd.name = "BAKE_TARGET"
        nd.image = img
        nt.nodes.active = nd
        nd.select = True
        o.data.uv_layers.active = o.data.uv_layers["lightmap"]
    select_only(bake_objs)
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
    for o in bake_objs:
        nt = o.data.materials[0].node_tree
        for nd in [n for n in nt.nodes if n.name.startswith("BAKE_TARGET")]:
            nt.nodes.remove(nd)
        o.data.uv_layers.active = o.data.uv_layers["UVMap"]
    rgb = denoise_image(img, S)[..., :3].copy()
    bpy.data.images.remove(img)
    peak = rgb.max(axis=2)
    sel = peak > 1e-5
    pc = np.percentile(peak[sel], [50, 90, 99, 99.5, 100]) if sel.any() else [1.0] * 5
    scale = float(pc[3])
    out = np.ones((S, S, 4), np.float32)
    out[..., :3] = srgb_encode(rgb / scale)
    png = bpy.data.images.new(f"LM_{PIECE}_png", S, S, alpha=False)
    png.colorspace_settings.name = "Non-Color"
    png.pixels.foreach_set(out.ravel())
    png.filepath_raw = str(WORK / f"kit_{PIECE}_0.png")
    png.file_format = "PNG"
    png.save()
    bpy.data.images.remove(png)
    for o in bake_objs:
        m = o.data.materials[0]
        m["lightmap"] = lm_url()
        m["lightmap_intensity"] = round(math.pi * scale, 4)
    report = {"piece": PIECE, "set": SPEC[PIECE]["light"], "size": S, "px_per_m": round(dens, 1), "scale": round(scale, 4),
              "p50_p90_p99_p995_max": [round(float(v), 3) for v in pc], "samples": SAMPLES, "device": bpy.context.scene.cycles.device,
              "seconds": round(time.time() - t0), "materials": sorted({o.data.materials[0].name for o in bake_objs}),
              "emissive_not_baked": sorted({o.data.materials[0].name for o in objs if o.data.materials[0].name in EMITS})}
    (WORK / f"kit_{PIECE}_lightmap.json").write_text(json.dumps(report, indent=1))
    print("BAKED", report)
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Art"].hide_viewport = False
    exp.hide_render = exp.hide_viewport = True
    save_blend()


# ---------------------------------------------------------------- privacy (the .blend, the GLB and the stills are public)
KEEP_MAT = {"lightmap", "lightmap_intensity"}
KEEP_OBJ = {"node", "width", "height", "closed_yaw_deg", "swing_deg", "state", "kind", "leaves", "slide_m", "car", "what", "where", "from"}
KEEP_SCENE = {"kit_nodes"}
SYS_KEEP = ("cycles", "eevee")


def scrub_ui_paths():
    for sc in bpy.data.screens:
        for a in sc.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"_" * 1000
                    sp.params.directory = b"//"


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private():
    kinds = ("scenes", "worlds", "objects", "meshes", "materials", "collections", "cameras", "lights", "images", "node_groups", "screens",
             "window_managers", "workspaces")
    keep = {"materials": KEEP_MAT, "objects": KEEP_OBJ, "scenes": KEEP_SCENE}
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
                    if st is idb and k in keep.get(kind, ()):
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
    base = KITDIR
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
    KITDIR.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path()))
    scrub_private()
    bpy.ops.wm.save_mainfile()


def stage_export():
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    for c in ("Art", "Layout", "Context"):
        bpy.data.collections[c].hide_viewport = True
    set_emit_strength(1.0)
    bpy.ops.object.select_all(action="DESELECT")
    for o in exp.objects:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = WORK / f"kit_{PIECE}_raw.glb"
    scrub_private()
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False, export_animations=False)
    print("EXPORTED", raw, raw.stat().st_size)
    set_emit_strength(None)
    for c in ("Art", "Layout", "Context"):
        bpy.data.collections[c].hide_viewport = False
    exp.hide_viewport = exp.hide_render = True


DOOR_NODES = ("Leaf_", "LiftLeaf_")         # the leaves the page swings or slides: doors, not walls (no collider; the door record blocks)


def component_parts(collection):
    """check_layout.blender_parts, one entry per connected piece of each mesh rather than per mesh: a kit mesh holds many separate boxes (a
    wall's runs, a room's walls), and the whole mesh's box would cover the floor between them. Door leaves are left out."""
    out = []
    for ob in bpy.data.collections[collection].all_objects:
        if ob.type != "MESH" or ob.hide_render or str(ob.get("node", "")).startswith(DOOR_NODES):
            continue
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        seen = set()
        k = 0
        for v in bm.verts:
            if v.index in seen:
                continue
            stack, isl = [v], []
            seen.add(v.index)
            while stack:
                a = stack.pop()
                isl.append(a)
                for e in a.link_edges:
                    b = e.other_vert(a)
                    if b.index not in seen:
                        seen.add(b.index)
                        stack.append(b)
            g = [(p.x, p.z, -p.y) for p in (ob.matrix_world @ a.co for a in isl)]
            k += 1
            out.append({"name": f"{ob.name}#{k}", "min": [round(min(q[i] for q in g), 4) for i in range(3)],
                        "max": [round(max(q[i] for q in g), 4) for i in range(3)]})
        bm.free()
    return out


def stage_layout():
    """world/kit/<piece>.json through export_scene.py, the layout check against the Art collection (tools/blender/check_layout.py), and the
    art's boxes for re-running that check without Blender (check_layout.py --boxes)."""
    import export_scene
    import check_layout
    out = ROOT / f"world/kit/{PIECE}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    d = export_scene.write(f"kit_{PIECE}", out)
    parts = component_parts("Art")
    (WORK / f"kit_{PIECE}_boxes.json").write_text(json.dumps(parts))
    print(f"LAYOUT_CHECK kit/{PIECE}")
    bad = check_layout.report(check_layout.check(parts, d, {}))
    if STAIR_NOTE:
        (WORK / "stair_door_cut.json").write_text(json.dumps(STAIR_NOTE, indent=1))
    return bad


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


def look_cam(name, loc, target, fov_v):
    cam = bpy.data.cameras.new(name)
    cam.sensor_fit = "VERTICAL"
    cam.lens_unit = "FOV"
    cam.angle_y = math.radians(fov_v)
    cam.clip_start, cam.clip_end = 0.03, 100
    ob = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = B(loc)
    ob.rotation_euler = (B(target) - B(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


def stage_render():
    sc = bpy.context.scene
    stills = ROOT / f"docs/renders/kit/{PIECE}"
    stills.mkdir(parents=True, exist_ok=True)
    scrub_private()
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
    set_emit_strength(None)
    setup_cycles(arg("--render-samples", 96, int))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.03
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = arg("--view", "Standard")       # the page draws with no tone mapping: the stills preview its brightness
    sc.view_settings.exposure = 0.0
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    art = list(bpy.data.collections["Art"].objects)
    for key, (loc, tgt, fov, opt) in SPEC[PIECE]["cams"]().items():
        cam = look_cam(key, loc, tgt, fov)
        sc.camera = cam
        hide = [o for o in art if o.get("node") in opt.get("hide", [])]
        for o in hide:
            o.hide_render = True
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1600, 900, 100
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 88
        path = stills / f"{key}.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        strip_jpeg_comments(path)
        for o in hide:
            o.hide_render = False
        print("STILL", key, path.stat().st_size)
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)


def open_blend():
    bpy.ops.wm.open_mainfile(filepath=str(blend_path()))
    global ART, LAYOUT, CONTEXT
    ART, LAYOUT, CONTEXT = (bpy.data.collections[c] for c in ("Art", "Layout", "Context"))
    # the build's tables (emissive strengths) come from the materials' names: rebuild EMITS from the file
    EMITS.clear()
    for m in bpy.data.materials:
        if m.name.startswith("Kit_") or m.name in ("Ctx_Lamp",):
            EMITS[m.name] = m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value


def run(piece):
    global PIECE
    PIECE = piece
    print(f"==== KIT {piece} stage {STAGE}")
    if STAGE in ("art", "all"):
        STAIR_NOTE.clear()
        build_all()
        save_blend()
    else:
        open_blend()
    bad = 0
    if STAGE in ("layout", "all", "art"):
        bad = stage_layout()
    if STAGE in ("bake", "all"):
        stage_bake()
    if STAGE in ("export", "all"):
        if "Export" not in bpy.data.collections:
            raise SystemExit("bake first: no Export collection")
        stage_export()
    if STAGE in ("render", "all"):
        stage_render()
    if STAGE != "render":
        save_blend()
    return bad


if __name__ == "__main__":
    which = arg("--piece", "all")
    todo = PIECES if which == "all" else which.split(",")
    WORK.mkdir(parents=True, exist_ok=True)
    fails = {p: run(p) for p in todo}
    print("KIT DONE", fails)
