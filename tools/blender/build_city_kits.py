"""Builds the City's extras (docs/BLENDER_AREAS.md section 5): three kits for Hallam Row, which is code-first, so these are pieces, not layouts.

    street_segment   a 40 m length of Hallam Row with two building slots (one each side), so the street can grow as addons unlock (street_of_jobs)
    bus_stop         the stop's shelter, bench and sign as one set
    depot_yard       the trash truck's yard behind 41 Hallam Row, and the truck (its own nodes; the wheels and the tailgate turn)

Re-runnable, from the repo root. `--piece` takes one id, a comma list, or all.

    python tools/blender/build_city_kits.py --stage textures           (plain Python with numpy and Pillow: the generated textures -> blender/textures/city_kits/)
    blender -b --factory-startup --python tools/blender/build_city_kits.py -- --piece bus_stop --stage art,bake,export,render [--samples 256]
        art:    the art and the layout objects; saves blender/kit/<piece>.blend, writes world/kit/<piece>.json (tools/blender/export_scene.py), runs the layout check
        bake:   the ambient occlusion into <work>/kit_<piece>_<n>.png
        export: <work>/kit_<piece>_raw.glb (the static art merged by material; the moving things as their own nodes)
        render: docs/renders/kit/<piece>/1_*.jpg, 2_*.jpg, 3_*.jpg and <work>/4_plan.jpg; re-exports the layout to <work>/kit_<piece>_reexport.json
    python tools/blender/city_kits_pack.py [piece ...]                (WebP AO maps -> world/lightmaps/kit_<piece>_<n>.webp, WebP textures -> world/kit/<piece>.glb)

Every kit is built in its own frame (game axes: metres, y up; a game point (x, y, z) is Blender (x, -z, y)); its origin and how it lands in the street
are in docs/renders/kit/<piece>/README.md. Placing a kit: `at` (where its origin goes) and `yaw` (its turn about y, as three.js's rotation.y): a kit point
(x, z) lands at (at.x + x cos yaw + z sin yaw, at.z - x sin yaw + z cos yaw), as for the connector kit.

These scenes have a day clock, so only the ambient occlusion is baked (docs/BLENDER.md R1, AO-only scenes, as the street, the meadow, the forest and the
playground): every baked material carries `aomap` and `aomap_intensity` (no `lightmap`), on the second UV set; the page keeps them lit by its sun and sky.
`Lamp_Emit` and `Window_Lit` are the page's switched materials, as on the street. What moves (the truck, its wheels and tailgate, the yard's gate leaves)
is not baked and has materials of its own.

The street's look is the street's own: its textures (blender/textures/street/ on claude/blender-street) are copied to blender/textures/city_kits/ unchanged,
and its facade rules (the door's plain wall and piers for the page's sign, lamp and shutter, the window slots, the shop glass, the fascias and awnings)
are the ones tools/blender/build_street.py uses.
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
except ImportError:                       # the textures stage runs in plain Python (numpy and Pillow)
    bpy = None

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


PIECES = ["street_segment", "bus_stop", "depot_yard"]
STAGE = arg("--stage", "art")
SAMPLES = arg("--samples", 256, int)
DEVICE = arg("--device", "auto")
TEX = ROOT / "blender/textures/city_kits"
KITDIR = ROOT / "blender/kit"
MARGIN_PX = 8


def piece_list():
    s = arg("--piece", "bus_stop")
    return PIECES if s == "all" else s.split(",")


def rng_for(*key):
    h = 2166136261
    for ch in "|".join(str(k) for k in key):
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return np.random.default_rng(h)


def lin_hex(h):
    c = [((h >> s) & 255) / 255 for s in (16, 8, 0)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c)


# ================================================================ the generated textures (plain Python: numpy and Pillow)
def to_lin(a):
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def to_srgb(a):
    a = np.clip(a, 0, 1)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(a, 1 / 2.4) - 0.055)


def blur(a, r, passes=3):
    n = 2 * r + 1
    for ax in (0, 1):
        for _ in range(passes):
            pad = [(0, 0)] * a.ndim
            pad[ax] = (r + 1, r)
            c = np.cumsum(np.pad(a, pad, mode="wrap"), axis=ax)
            Ln = c.shape[ax]
            a = (np.take(c, range(n, Ln), axis=ax) - np.take(c, range(0, Ln - n), axis=ax)) / n
    return a


# the street's 5 x 7 pixel font (tools/blender/build_street.py), with the letters these signs add
GLYPHS = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"], "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"], "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"], "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"], "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"], "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"], "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"], "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"], "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"], "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"], "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"], "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "0": ["01110", "10011", "10101", "10101", "10101", "11001", "01110"], "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"], "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"], "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"], "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"], "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"], ".": ["00000"] * 6 + ["00100"],
    ":": ["00000", "00100", "00000", "00000", "00000", "00100", "00000"], " ": ["00000"] * 7,
}


def draw_text(img, text, box, fg, fill=0.7):
    r0, r1, c0, c1 = box
    cols = len(text) * 6 - 1
    s = max(1, int(min((c1 - c0) * fill / cols, (r1 - r0) * fill / 7)))
    y = r0 + ((r1 - r0) - 7 * s) // 2
    x = c0 + ((c1 - c0) - cols * s) // 2
    for ch in text:
        for r, row in enumerate(GLYPHS[ch]):
            for c, v in enumerate(row):
                if v == "1":
                    img[y + r * s:y + (r + 1) * s, x + c * s:x + (c + 1) * s] = fg
        x += 6 * s


# the sign atlas (1024 x 1024, sRGB): each sign is a pixel rectangle (r0, r1, c0, c1); the geometry maps its face onto it (sign_uv)
SIGN_RECT = {
    "flag": (0, 320, 0, 256),             # the bus stop's flag, 0.48 x 0.6 m
    "timetable": (0, 427, 256, 512),      # the timetable in its case, 0.3 x 0.5 m
    "chevrons": (0, 448, 512, 1024),      # the truck's rear: red and yellow chevrons
    "fascia": (448, 528, 0, 1024),        # the shelter's roof fascia, HALLAM ROW, 2.5 x 0.2 m
    "depot": (528, 733, 0, 1024),         # the depot's name board on the gate fence, 4.0 x 0.8 m
    "noparking": (733, 887, 0, 512),      # NO PARKING / VEHICLES TURNING, 2.0 x 0.6 m
    "office": (733, 840, 512, 1024),      # DEPOT OFFICE, 1.2 x 0.25 m
    "truck": (887, 1024, 0, 1024),        # the truck's side: HALLAM ROW SANITATION, on the body's green
}
TRUCK_GREEN = (0.075, 0.26, 0.12)         # linear: the truck body's colour (the decal's ground is the same)


def signs_atlas():
    S = 1024
    img = np.zeros((S, S, 3), np.float32) + 0.5
    cream, dark = tuple(to_srgb(np.array(lin_hex(0xe8e0c0)))), tuple(to_srgb(np.array(lin_hex(0x1a1a1e))))
    white, red = (0.86, 0.86, 0.84), (0.72, 0.10, 0.09)

    def rect(k):
        return SIGN_RECT[k]
    # the flag: a white plate, a plain dark green disc with BUS in it (a generic stop, no operator's mark), STOP and the street's name under it
    r0, r1, c0, c1 = rect("flag")
    img[r0:r1, c0:c1] = white
    cy, cx, R = r0 + 110, (c0 + c1) // 2, 88
    yy, xx = np.mgrid[r0:r1, c0:c1]
    disc = np.hypot(yy - cy, xx - cx) < R
    img[r0:r1, c0:c1][disc] = to_srgb(np.array((0.03, 0.12, 0.06)))
    draw_text(img, "BUS", (cy - 30, cy + 30, cx - R + 14, cx + R - 14), white, 0.85)
    draw_text(img, "STOP", (r0 + 210, r0 + 262, c0 + 16, c1 - 16), dark, 0.85)
    draw_text(img, "HALLAM ROW", (r0 + 266, r0 + 306, c0 + 12, c1 - 12), (0.25, 0.25, 0.27), 0.9)
    img[r0:r0 + 6, c0:c1] = img[r1 - 6:r1, c0:c1] = img[r0:r1, c0:c0 + 6] = img[r0:r1, c1 - 6:c1] = (0.35, 0.35, 0.36)
    # the timetable: a white sheet, a dark header, rows of grey bars (times), a frame
    r0, r1, c0, c1 = rect("timetable")
    img[r0:r1, c0:c1] = (0.80, 0.80, 0.77)
    img[r0 + 10:r0 + 60, c0 + 10:c1 - 10] = (0.10, 0.18, 0.42)
    draw_text(img, "TIMES", (r0 + 10, r0 + 60, c0 + 10, c1 - 10), white, 0.7)
    rng = np.random.default_rng(41)
    for k in range(14):
        y = r0 + 78 + k * 24
        img[y:y + 9, c0 + 18:c0 + 60] = (0.30, 0.30, 0.32)
        for j in range(4):
            if rng.random() < 0.85:
                img[y:y + 9, c0 + 76 + j * 42:c0 + 106 + j * 42] = (0.42, 0.42, 0.44)
    img[r0:r0 + 8, c0:c1] = img[r1 - 8:r1, c0:c1] = img[r0:r1, c0:c0 + 8] = img[r0:r1, c1 - 8:c1] = (0.20, 0.20, 0.21)
    # the chevrons (the truck's rear): red and yellow stripes at 45 degrees, meeting in a point at the middle
    r0, r1, c0, c1 = rect("chevrons")
    yy, xx = np.mgrid[r0:r1, c0:c1]
    t = ((np.abs(xx - (c0 + c1) / 2) + (yy - r0)) // 48) % 2
    img[r0:r1, c0:c1] = np.where(t[..., None] == 0, np.array((0.78, 0.08, 0.06)), np.array((0.90, 0.72, 0.08)))
    # the shelter's fascia: HALLAM ROW, cream on dark (the page's sign colours)
    r0, r1, c0, c1 = rect("fascia")
    img[r0:r1, c0:c1] = dark
    draw_text(img, "HALLAM ROW", (r0, r1, c0, c1), cream, 0.62)
    # the depot's name board: two lines, white on dark green, a thin white border
    r0, r1, c0, c1 = rect("depot")
    img[r0:r1, c0:c1] = to_srgb(np.array((0.03, 0.12, 0.06)))
    img[r0 + 8:r0 + 12, c0 + 8:c1 - 8] = img[r1 - 12:r1 - 8, c0 + 8:c1 - 8] = white
    img[r0 + 8:r1 - 8, c0 + 8:c0 + 12] = img[r0 + 8:r1 - 8, c1 - 12:c1 - 8] = white
    draw_text(img, "41 HALLAM ROW", (r0 + 16, r0 + 110, c0 + 20, c1 - 20), white, 0.75)
    draw_text(img, "SANITATION DEPOT", (r0 + 100, r1 - 16, c0 + 20, c1 - 20), (0.80, 0.82, 0.70), 0.78)
    # NO PARKING / VEHICLES TURNING: red on white
    r0, r1, c0, c1 = rect("noparking")
    img[r0:r1, c0:c1] = white
    draw_text(img, "NO PARKING", (r0 + 6, r0 + 80, c0 + 10, c1 - 10), red, 0.8)
    draw_text(img, "VEHICLES TURNING", (r0 + 78, r1 - 8, c0 + 10, c1 - 10), dark, 0.85)
    # DEPOT OFFICE: dark on pale yellow
    r0, r1, c0, c1 = rect("office")
    img[r0:r1, c0:c1] = (0.80, 0.72, 0.30)
    draw_text(img, "DEPOT OFFICE", (r0, r1, c0 + 10, c1 - 10), dark, 0.78)
    # the truck's side: white on the body's green
    r0, r1, c0, c1 = rect("truck")
    img[r0:r1, c0:c1] = to_srgb(np.array(TRUCK_GREEN))
    img[r0 + 10:r0 + 16, c0:c1] = img[r1 - 16:r1 - 10, c0:c1] = (0.78, 0.78, 0.74)
    draw_text(img, "HALLAM ROW SANITATION", (r0 + 16, r1 - 16, c0 + 10, c1 - 10), (0.80, 0.80, 0.76), 0.86)
    return np.clip(img, 0, 1)


def ad_poster():
    """The shelter's side panel: a job advert (512 x 1024), dark navy, faded at the edges: NOW HIRING / ASK AT 41 HALLAM ROW, and a green bin."""
    W, H = 512, 1024
    img = np.zeros((H, W, 3), np.float32) + to_srgb(np.array((0.025, 0.035, 0.07)))
    white, yellow = (0.84, 0.84, 0.80), (0.86, 0.72, 0.20)
    draw_text(img, "NOW", (60, 200, 30, W - 30), yellow, 0.9)
    draw_text(img, "HIRING", (200, 330, 30, W - 30), white, 0.9)
    # a green wheelie bin: body, lid, two wheels
    g = to_srgb(np.array((0.10, 0.34, 0.14)))
    img[430:690, 170:340] = g
    img[408:436, 158:352] = g * 0.8
    for cx in (190, 320):
        yy, xx = np.mgrid[680:740, cx - 30:cx + 30]
        m = np.hypot(yy - 710, xx - cx) < 26
        img[680:740, cx - 30:cx + 30][m] = (0.06, 0.06, 0.06)
    draw_text(img, "ASK AT", (780, 860, 40, W - 40), white, 0.8)
    draw_text(img, "41 HALLAM ROW", (860, 940, 20, W - 20), yellow, 0.9)
    yy, xx = np.mgrid[0:H, 0:W]
    v = 1 - 0.35 * (np.hypot((xx - W / 2) / W, (yy - H / 2) / H) * 1.6) ** 2
    rng = np.random.default_rng(7)
    n = blur(rng.random((H, W)).astype(np.float32), 3, 2)
    return np.clip(img * v[..., None] * (0.92 + 0.16 * n[..., None]), 0, 1)


def yard_concrete():
    """The depot's yard: the street's concrete (hangar_concrete_floor, CC0) with oil stains and tyre wear, tiling (1024 px, a 4 m repeat)."""
    from PIL import Image
    a = np.asarray(Image.open(TEX / "concrete.jpg").convert("RGB"), np.float32) / 255.0
    L = to_lin(a)
    rng = np.random.default_rng(4141)
    S = L.shape[0]
    stain = blur(rng.random((S, S)).astype(np.float32), 110, 3)
    stain = (stain - stain.mean()) / (stain.std() + 1e-6)
    blots = np.clip((stain - 1.1) * 0.8, 0, 1)                  # a few broad, soft oil stains a repeat
    fine = blur(rng.random((S, S)).astype(np.float32), 4, 2)
    k = 1 - 0.30 * blots * (0.8 + 0.4 * fine)
    xx = np.arange(S)[None, :]
    tracks = 1 - 0.10 * np.exp(-((xx % (S // 2) - S * 0.18) ** 2) / (2 * (S * 0.03) ** 2))     # two worn bands a repeat
    return to_srgb(L * k[..., None] * tracks[..., None] * 0.95)


def stage_textures():
    from PIL import Image
    TEX.mkdir(parents=True, exist_ok=True)
    for fn, arr in (("signs_city.png", signs_atlas()), ("ad_poster.png", ad_poster()), ("yard_concrete.jpg", yard_concrete())):
        im = Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8))
        p = TEX / fn
        if fn.endswith(".png"):
            im.save(p, optimize=True)
        else:
            im.save(p, "JPEG", quality=88, optimize=True)
        print("TEXTURE", fn, im.size, p.stat().st_size)


if bpy is None:
    if STAGE == "textures":
        stage_textures()
    else:
        print("without Blender only --stage textures runs")
    sys.exit(0)


# ================================================================ Blender from here on
PIECE = BLEND = STILLS = None


def setup(pid):
    global PIECE, BLEND, STILLS
    PIECE = pid
    BLEND = KITDIR / f"{pid}.blend"
    STILLS = ROOT / f"docs/renders/kit/{pid}"


def scene_id():
    return f"kit_{PIECE}"


def work_dir():
    d = Path(arg("--work", str(ROOT / "work/city_kits"))) / PIECE
    d.mkdir(parents=True, exist_ok=True)
    return d


def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


# ---------------------------------------------------------------- materials
IMG_CACHE, MATS, TILES = {}, {}, {}


def image(fn, srgb=True):
    key = (fn, srgb)
    if key not in IMG_CACHE:
        im = bpy.data.images.load(str(TEX / fn))
        im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
        IMG_CACHE[key] = im
    return IMG_CACHE[key]


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, diff=None, tint=None, emit=None, emit_img=None, alpha=None, tile=1.0):
    """A Principled material. `tint` multiplies the diffuse texture by a constant colour (a Mix set to Multiply; the glTF exporter writes it as
    baseColorFactor). `emit` is (colour, strength); with `emit_img` the picture is the emission colour."""
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
    if emit_img:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image(emit_img, True)
        n.name = "EMIT_IMG"
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        nt.links.new(n.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    elif emit:
        bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    if alpha is not None:
        bsdf.inputs["Alpha"].default_value = alpha
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    TILES[name] = tile
    MATS[name] = m
    return m


LAMP_EMIT = ((1.0, 0.80, 0.52), 6.0)          # the street's lamp lenses (sodium-warm); the page switches them on from dusk
WINDOW_EMIT = 2.2                             # the street's lit windows (times their picture); the page switches them on at night


def street_materials():
    """The street's materials, by the street's names and values (tools/blender/build_street.py make_materials)."""
    material("Road_Asphalt", diff="road_asphalt.jpg", rough=0.9, tile=4.0)
    material("Road_Line", color=(0.62, 0.62, 0.58), rough=0.6)
    material("Road_Yellow", color=(0.62, 0.42, 0.06), rough=0.6)
    material("Sidewalk_Slab", diff="sidewalk_slab.jpg", rough=0.85, tile=2.6)
    material("Kerb_Stone", diff="concrete.jpg", tint=(0.62, 0.62, 0.60), rough=0.8, tile=1.5)
    material("Backlot_Ground", diff="concrete.jpg", tint=(0.42, 0.42, 0.41), rough=0.95, tile=5.0)
    material("Drain_Iron", diff="drain.jpg", rough=0.6, metal=0.3)
    material("Roof_Felt", diff="concrete.jpg", tint=(0.17, 0.17, 0.18), rough=0.95, tile=3.0)
    material("Trim_Stone", diff="concrete.jpg", tint=(0.95, 0.92, 0.84), rough=0.85, tile=2.0)
    material("Fascia_Paint", color=(0.035, 0.06, 0.05), rough=0.45)
    material("Frame_Dark", color=(0.03, 0.033, 0.036), rough=0.4, metal=0.4)
    material("Shop_Glass", diff="shop_atlas.jpg", rough=0.08)
    material("Window_Dark", color=(0.03, 0.035, 0.045), rough=0.08)
    material("Window_Lit", color=(0.03, 0.032, 0.035), rough=0.1, emit=((1, 1, 1), WINDOW_EMIT), emit_img="window_lit.jpg")
    material("Door_Leaf", color=(0.055, 0.09, 0.075), rough=0.45)
    material("Boarding", diff="wood.jpg", rough=0.9, tile=2.4)
    material("Metal_Dark", color=(0.03, 0.032, 0.035), rough=0.45, metal=0.6)
    material("Lamp_Emit", color=(0.62, 0.60, 0.55), rough=0.3, emit=LAMP_EMIT)
    material("Awning_Red", color=(0.30, 0.035, 0.03), rough=0.85)
    material("Awning_Green", color=(0.03, 0.15, 0.075), rough=0.85)


# ---------------------------------------------------------------- geometry (built in world space; game coordinates in)
def quad(bm, pts, n, uv=None):
    """A face through game points `pts`, turned to face the game direction `n`; `uv` optional per-corner UVs."""
    vs = [bm.verts.new(B(p)) for p in pts]
    f = bm.faces.new(vs)
    f.normal_update()
    if f.normal.dot(B(n)) < 0:
        f.normal_flip()
    if uv:
        lay = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
        by_vert = dict(zip(vs, uv))
        for lp in f.loops:
            lp[lay].uv = by_vert[lp.vert]
        f.tag = True
    return f


def box(bm, mn, mx, skip=()):
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    F = {"-x": ([(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)], (-1, 0, 0)),
         "+x": ([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], (1, 0, 0)),
         "-y": ([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], (0, -1, 0)),
         "+y": ([(x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)], (0, 1, 0)),
         "-z": ([(x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)], (0, 0, -1)),
         "+z": ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], (0, 0, 1))}
    for k, (pts, n) in F.items():
        if k not in skip:
            quad(bm, pts, n)


def bevel_box(bm, mn, mx, r=0.02, seg=2):
    a, b = B(mn), B(mx)
    c = (a + b) / 2
    s = Vector((abs(a.x - b.x), abs(a.y - b.y), abs(a.z - b.z)))
    vs = bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((s.x, s.y, s.z, 1.0)))["verts"]
    d = min(mx[i] - mn[i] for i in range(3))
    r = min(r, d * 0.3)
    if r > 0.004:
        es = list({e for v in vs for e in v.link_edges})
        bmesh.ops.bevel(bm, geom=es + vs, offset=r, segments=seg, affect="EDGES", profile=0.5, clamp_overlap=True)


def cyl(bm, p0, p1, r0, r1=None, seg=8, cap=True):
    a, b = B(p0), B(p1)
    d = b - a
    q = d.to_track_quat("Z", "Y")
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                          matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())


def prism(bm, pts2, y0, y1, axis="x"):
    """A prism: the polygon `pts2` (in (z, y) if axis is x, the section seen from +x) swept along x from y0 to y1 (here y0, y1 are the x range)."""
    a0, a1 = y0, y1
    ring0 = [bm.verts.new(B((a0, p[1], p[0]))) for p in pts2]
    ring1 = [bm.verts.new(B((a1, p[1], p[0]))) for p in pts2]
    n = len(pts2)
    fs = [bm.faces.new(ring0[::-1]), bm.faces.new(ring1)]
    for i in range(n):
        j = (i + 1) % n
        fs.append(bm.faces.new((ring0[i], ring0[j], ring1[j], ring1[i])))
    bmesh.ops.recalc_face_normals(bm, faces=fs)


def box_uv(bm, tile):
    """UV0 for faces without their own: box projection in metres / tile, from world positions (game axes)."""
    lay = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        if f.tag:
            continue
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y
            u, v = ((gz, gy) if ax == 0 else (gx, gy) if ax == 1 else (gx, gz))
            lp[lay].uv = (u / tile, v / tile)


ART = None


def finish(name, bm, mat, coll=None, smooth=False):
    if not bm.faces:
        bm.free()
        return None
    bm.normal_update()
    for f in bm.faces:
        f.smooth = smooth
    if not bm.loops.layers.uv.get("UVMap"):
        bm.loops.layers.uv.new("UVMap")
    box_uv(bm, TILES.get(mat, 1.0))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(name, me)
    (coll or ART).objects.link(ob)
    if mat in ("Lamp_Emit", "Shelter_Glass"):
        ob.visible_shadow = False
    return ob


class Parts:
    """Per-object bmeshes: name -> (material, bmesh, smooth). done() makes one object each."""
    def __init__(self, coll=None):
        self.d, self.coll = {}, coll

    def bm(self, name, mat, smooth=False):
        if name not in self.d:
            self.d[name] = (mat, bmesh.new(), smooth)
        return self.d[name][1]

    def done(self):
        out = []
        for name, (mat, bm, sm) in self.d.items():
            o = finish(name, bm, mat, self.coll, smooth=sm)
            if o:
                out.append(o)
        self.d = {}
        return out


def joined(name, parts, coll, origin=(0, 0, 0), parent=None):
    """One object with several materials from Parts-made objects: joined, its origin moved to the game point `origin` (world), parented to `parent`."""
    objs = [o for o in parts if o]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    o = B(origin)
    ob.data.transform(Matrix.Translation(-o))
    ob.location = o
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    coll.objects.link(ob)
    if parent is not None:                                       # the parent is an unrotated empty: the child's location is its offset from it
        ob.parent = parent
        ob.matrix_parent_inverse = Matrix.Identity(4)
        ob.location = o - parent.location
    return ob


def empty(name, pos, face=None, props=None, coll=None, kind="PLAIN_AXES", size=0.3):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_type = kind
    ob.empty_display_size = size
    ob.location = B(pos)
    if face:                                # the empty's -Y axis is the game direction face = (fx, fz)
        ob.rotation_euler = (0, 0, math.atan2(face[0], face[1]))
    for k, v in (props or {}).items():
        ob[k] = v
    (coll or LAYOUT).objects.link(ob)
    return ob


LAYOUT = None


def collider(name, mn, mx, prefix="COL_"):
    me = bpy.data.meshes.new(prefix + name)
    bm = bmesh.new()
    box(bm, mn, mx)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(prefix + name, me)
    ob.display_type = "WIRE"
    ob.hide_render = True
    LAYOUT.objects.link(ob)
    return ob


def sign_uv(key, flip=False):
    """Per-corner UVs (lower left, lower right, upper right, upper left) of a sign's rectangle in signs_city.png."""
    r0, r1, c0, c1 = SIGN_RECT[key]
    u0, u1, v0, v1 = c0 / 1024, c1 / 1024, 1 - r1 / 1024, 1 - r0 / 1024
    uv = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    return [uv[1], uv[0], uv[3], uv[2]] if flip else uv


def atlas_uv(cell, n=2, inset=0.0):
    r, c = divmod(cell, n)
    u0, u1 = c / n + inset, (c + 1) / n - inset
    v1, v0 = 1 - r / n - inset, 1 - (r + 1) / n + inset
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def flip_u(uv):
    return [uv[1], uv[0], uv[3], uv[2]]


# ================================================================ the street segment
# The frame: the origin is the road's centre line at the segment's south end, on the collision floor (y 0); the segment runs 40 m north, to z -40,
# as Hallam Row runs (north is -z). The road is x -5 to 5, the sidewalks 3 m each side, the building fronts at x +-8: the street's own numbers
# (shared/city.js ROAD, WALK, FRONT). Placed at (0, 0, z) with yaw 0, it continues the street north of z.
SEG_L = 40.0
ROAD_X, FRONT = 5.0, 8.0
ROAD_Y, WALK_Y = -0.06, 0.06              # the street's: the road 6 cm under the collision floor, the sidewalks 6 cm over it (a 12 cm kerb)
KERB_W = 0.15
YARD_X = 30.0                             # the yards behind the buildings run out to x +-30 (the street's own run on to its edge rows at +-60)
SEG_LAMP_ZS = [0.0, -20.0]                # every 20 m as on the street (the lamp at z -40 is the next segment's z 0)
PAR = 0.7
PANE_W, PANE_H = 1.6, 1.3
WIN_DEPTH = 0.05
SHOP_Y = (0.45, 2.4)
SHOP_DEPTH = 0.15
DOOR_W, DOOR_H = 1.8, 2.5                 # the street's door (shared/city.js DOOR_W, DOOR_H)
DOOR_DEPTH = 0.25
DOOR_ZONE = 1.6                           # plain wall each side of a door's centre line: the page's shutter (+-1.15) and lamp (+1.2) sit on it
SIGN_ZONE = 1.55                          # no awning or fascia within this of a door: the page's sign is 2.8 m wide at y 2.79 .. 3.31
FASCIA_Y = (2.45, 2.85)
PILASTER = 0.45
EDGE_BAY = 3.4
PAINT_K = 1.9
# the two slots (a job's building with a door; its own nodes, slot_W and slot_E) and two fillers (no door), on plots like the street's
SEG_BUILDINGS = [
    {"id": "slot_W", "side": "w", "z0": -24.0, "z1": -38.0, "depth": 16.0, "h": 10.0, "color": 0x7e6a5e, "door_z": -31.0,
     "tex": "brick_red.jpg", "tile": 2.6, "tint": "brick", "ground": "shop", "glass": 0, "awning": "Awning_Red"},
    {"id": "fill_W", "side": "w", "z0": -2.0, "z1": -20.0, "depth": 14.0, "h": 11.0, "color": 0x8a96a2, "door_z": None,
     "tex": "render_patchy.jpg", "tile": 2.5, "tint": "paint", "ground": "house", "glass": 3},
    {"id": "slot_E", "side": "e", "z0": -2.0, "z1": -16.0, "depth": 16.0, "h": 9.0, "color": 0x8a9a8c, "door_z": -9.0,
     "tex": "render_patchy.jpg", "tile": 2.5, "tint": "paint", "ground": "shop", "glass": 0, "awning": "Awning_Green"},
    {"id": "fill_E", "side": "e", "z0": -20.0, "z1": -38.0, "depth": 14.0, "h": 8.0, "color": 0x8a8a6a, "door_z": None,
     "tex": "brick_yellow.jpg", "tile": 1.5, "tint": "brick", "ground": "boarded", "glass": 3},
]
SEG_BINS = [(-5.4, -12.0), (5.4, -30.0)]  # where the trash route's bins stand on this length (the kerb, x +-5.4, as shared/trash.js BINS)


def facade_tint(b):
    c = np.array(lin_hex(b["color"]))
    if b["tint"] == "paint":
        return tuple(float(v) for v in np.clip(c * PAINT_K, 0, 1))
    t = (c / c.mean()) ** 0.35
    return tuple(float(v) for v in t / t.max())


def seg_box(b):
    x = -FRONT if b["side"] == "w" else FRONT
    x0, x1 = (x - b["depth"], x) if b["side"] == "w" else (x, x + b["depth"])
    return (x0, 0.0, min(b["z0"], b["z1"])), (x1, b["h"], max(b["z0"], b["z1"]))


def window_slots(b):
    """The page's window panes on a street face (shared/city.js windowSlots): floor f from 1, a slot every 3.4 m, none beside the door on floor 1."""
    out, zl, zh = [], min(b["z0"], b["z1"]), max(b["z0"], b["z1"])
    f = 1
    while f * 3.6 < b["h"] - 1:
        k, z = 0, zl + 1.5
        while z < zh - 1.2:
            if not (b["door_z"] is not None and f == 1 and abs(z + 0.8 - b["door_z"]) < 2.4):
                out.append({"f": f, "k": k, "y": f * 3.6, "z": z + 0.8})
            z += 3.4
            k += 1
        f += 1
    return out


def cells(As, Ys, holes):
    out = []
    for i in range(len(As) - 1):
        for j in range(len(Ys) - 1):
            ca, cy = (As[i] + As[i + 1]) / 2, (Ys[j] + Ys[j + 1]) / 2
            if any(h[0] < ca < h[1] and h[2] < cy < h[3] for h in holes):
                continue
            out.append((As[i], As[i + 1], Ys[j], Ys[j + 1]))
    return out


def grid(a0, a1, y0, y1, holes):
    As = sorted({a0, a1} | {v for h in holes for v in h[:2] if a0 < v < a1})
    Ys = sorted({y0, y1} | {v for h in holes for v in h[2:] if y0 < v < y1})
    return cells(As, Ys, holes)


class Front:
    """A facade plane x = F whose outward normal is (s, 0, 0); `a` runs along game z, `d` is the depth into the building."""
    def __init__(self, F, s):
        self.F, self.s = F, s

    def p(self, a, y, d=0.0):
        return (self.F - self.s * d, y, a)

    def face(self, bm, a0, a1, y0, y1, d=0.0, n_out=True, uv=None):
        return quad(bm, [self.p(a0, y0, d), self.p(a1, y0, d), self.p(a1, y1, d), self.p(a0, y1, d)], (self.s if n_out else -self.s, 0, 0), uv)

    def reveal(self, bm, h, d):
        a0, a1, y0, y1 = h
        P = self.p
        quad(bm, [P(a0, y0), P(a1, y0), P(a1, y0, d), P(a0, y0, d)], (0, 1, 0))
        quad(bm, [P(a0, y1), P(a1, y1), P(a1, y1, d), P(a0, y1, d)], (0, -1, 0))
        quad(bm, [P(a0, y0), P(a0, y1), P(a0, y1, d), P(a0, y0, d)], (0, 0, 1))
        quad(bm, [P(a1, y0), P(a1, y1), P(a1, y1, d), P(a1, y0, d)], (0, 0, -1))

    def slab(self, bm, a0, a1, y0, y1, d0, d1, skip=()):
        xa, xb = self.F - self.s * d0, self.F - self.s * d1
        box(bm, (min(xa, xb), y0, a0), (max(xa, xb), y1, a1), skip)

    def in_key(self):
        return "-x" if self.s > 0 else "+x"


def shop_spans(a0, a1, dz):
    runs = [(a0 + PILASTER, a1 - PILASTER)]
    if dz is not None:
        out = []
        for r0, r1 in runs:
            if r0 < dz - DOOR_ZONE:
                out.append((r0, min(r1, dz - DOOR_ZONE)))
            if r1 > dz + DOOR_ZONE:
                out.append((max(r0, dz + DOOR_ZONE), r1))
        runs = out
    return [(r0, r1) for r0, r1 in runs if r1 - r0 > 1.2]


def panels(r0, r1, maxw=3.0, pier=0.3):
    n = max(1, math.ceil((r1 - r0 + pier) / (maxw + pier)))
    w = (r1 - r0 - (n - 1) * pier) / n
    return [(r0 + i * (w + pier), r0 + i * (w + pier) + w) for i in range(n)]


def side_slots(length, h, margin=1.4):
    out = []
    n = int((length - 2 * margin) // EDGE_BAY) + 1
    if n < 1:
        return out
    start = (length - (n - 1) * EDGE_BAY) / 2
    for f in range(1, 99):
        y = f * 3.6
        if y + 0.8 > h - 0.5:
            break
        for k in range(n):
            out.append((start + k * EDGE_BAY, y))
    return out


def build_building(b, P):
    """One building as the street builds it (tools/blender/build_street.py build_building): the front cut round the door, the shop panels and the
    window slots, the door at the back of its recess, the fascia and awning (never over the door), flush windows on the back and sides, the parapet,
    the roof and a cornice."""
    bid = b["id"]
    s = 1 if b["side"] == "w" else -1
    F = -FRONT if b["side"] == "w" else FRONT
    depth, h = b["depth"], b["h"]
    a0, a1 = min(b["z0"], b["z1"]), max(b["z0"], b["z1"])
    back = F - s * depth
    top = h + PAR
    fr = Front(F, s)
    dz = b["door_z"]
    rng = rng_for("bld", bid)
    mass = P.bm(f"Bld_{bid}", f"Facade_{bid}")
    hi = P.bm(f"TrimHi_{bid}", "Trim_Stone")
    frame = P.bm(f"Frame_{bid}", "Frame_Dark")
    glass = P.bm(f"Glass_{bid}", "Shop_Glass")
    lit = P.bm(f"WinLit_{bid}", "Window_Lit")
    dark = P.bm(f"WinDark_{bid}", "Window_Dark")
    holes = []
    kind = b["ground"]
    if dz is not None:
        holes.append((dz - DOOR_W / 2, dz + DOOR_W / 2, WALK_Y, DOOR_H, DOOR_DEPTH, "door"))
    runs = shop_spans(a0, a1, dz)
    if kind in ("shop", "boarded"):
        for r0, r1 in runs:
            for p0, p1 in panels(r0, r1, 3.2):
                holes.append((p0, p1, SHOP_Y[0], SHOP_Y[1], SHOP_DEPTH if kind != "boarded" else 0.06, kind))
    elif kind == "house":
        for r0, r1 in runs:
            for p0, p1 in panels(r0, r1, 1.3, 1.9):
                c = (p0 + p1) / 2
                holes.append((c - 0.6, c + 0.6, 0.9, 2.2, WIN_DEPTH, "housewin"))
    for sl in window_slots(b):
        holes.append((max(a0 + 0.15, sl["z"] - PANE_W / 2), min(a1 - 0.15, sl["z"] + PANE_W / 2), sl["y"] - PANE_H / 2, sl["y"] + PANE_H / 2, WIN_DEPTH,
                      ("slot", sl["f"], sl["k"])))
    for c0, c1, y0, y1 in grid(a0, a1, 0.0, top, [h_[:4] for h_ in holes]):
        fr.face(mass, c0, c1, y0, y1)
    for hh in holes:
        a_0, a_1, y0, y1, d, k = hh
        fr.reveal(mass, hh[:4], d)
        if k == "door":
            build_door(fr, P, bid, hh)
        elif isinstance(k, tuple):
            pane = (a_0, a_1, y0, y1)
            if rng.random() < 0.5:
                fr.face(lit, *pane, d=0.04, uv=atlas_uv(int(rng.integers(4))))
            else:
                fr.face(dark, *pane, d=0.04)
            fr.slab(hi, a_0 - 0.1, a_1 + 0.1, y0 - 0.07, y0, 0.0, -0.06, skip=(fr.in_key(),))
            fr.slab(hi, a_0 - 0.08, a_1 + 0.08, y1, y1 + 0.16, 0.0, -0.015, skip=(fr.in_key(),))
        elif k == "housewin":
            fr.face(dark, a_0, a_1, y0, y1, d=0.04)
            fr.slab(P.bm(f"TrimLo_{bid}", "Trim_Stone"), a_0 - 0.08, a_1 + 0.08, y0 - 0.06, y0, 0.0, -0.04, skip=(fr.in_key(),))
        elif k == "boarded":
            fr.face(P.bm(f"Board_{bid}", "Boarding"), a_0, a_1, y0, y1, d=0.05)
        else:
            gd = SHOP_DEPTH - 0.03
            fr.face(glass, a_0 + 0.05, a_1 - 0.05, y0 + 0.05, y1 - 0.05, d=gd, uv=atlas_uv(b["glass"], inset=0.01))
            for (u0, u1, v0, v1) in ((a_0, a_0 + 0.06, y0, y1), (a_1 - 0.06, a_1, y0, y1), (a_0, a_1, y0, y0 + 0.07), (a_0, a_1, y1 - 0.06, y1)):
                fr.slab(frame, u0, u1, v0, v1, gd - 0.03, gd + 0.02, skip=(fr.in_key(),))
            if y1 - y0 > 1.8:
                fr.slab(frame, a_0, a_1, y1 - 0.45, y1 - 0.4, gd - 0.03, gd + 0.01, skip=(fr.in_key(),))
    if kind in ("shop", "boarded"):
        fa = P.bm(f"Fascia_{bid}", "Fascia_Paint")
        for r0, r1 in runs:
            r0_, r1_ = r0 - 0.1, r1 + 0.1
            if dz is not None:
                if r0_ < dz:
                    r1_ = min(r1_, dz - SIGN_ZONE)
                else:
                    r0_ = max(r0_, dz + SIGN_ZONE)
            if r1_ - r0_ > 0.5:
                fr.slab(fa, r0_, r1_, FASCIA_Y[0], FASCIA_Y[1], 0.0, -0.04, skip=(fr.in_key(),))
                if b.get("awning"):
                    build_awning(fr, P, bid, r0_ + 0.1, r1_ - 0.1, b["awning"])
    bk = Front(back, -s)
    for c0, c1, y0, y1 in grid(a0, a1, 0.0, top, []):
        bk.face(mass, c0, c1, y0, y1)
    r2 = rng_for("back", bid)
    for (a, y) in side_slots(a1 - a0, h):
        pane = (a0 + a - 0.6, a0 + a + 0.6, y - 0.65, y + 0.65)
        if r2.random() < 0.3:
            bk.face(lit, *pane, d=-0.012, uv=flip_u(atlas_uv(int(r2.integers(4)))))
        else:
            bk.face(dark, *pane, d=-0.012)
    bk.face(P.bm(f"BackDoor_{bid}", "Door_Leaf"), (a0 + a1) / 2 - 0.5, (a0 + a1) / 2 + 0.5, 0.0, 2.1, d=-0.012)
    for zc, nz in ((a0, -1), (a1, 1)):
        xs = sorted((back, F))
        quad(mass, [(xs[0], 0, zc), (xs[1], 0, zc), (xs[1], top, zc), (xs[0], top, zc)], (0, 0, nz))
        for (a, y) in side_slots(depth, h, 1.6):
            x0_, x1_ = F - s * (a - 0.6), F - s * (a + 0.6)
            pts = [(x0_, y - 0.65, zc + nz * 0.012), (x1_, y - 0.65, zc + nz * 0.012), (x1_, y + 0.65, zc + nz * 0.012), (x0_, y + 0.65, zc + nz * 0.012)]
            if r2.random() < 0.3:
                quad(lit, pts, (0, 0, nz), atlas_uv(int(r2.integers(4))))
            else:
                quad(dark, pts, (0, 0, nz))
    t = 0.25
    roof = P.bm(f"Roof_{bid}", "Roof_Felt")
    xi0, xi1 = sorted((F - s * t, back + s * t))
    quad(roof, [(xi0, h, a0 + t), (xi1, h, a0 + t), (xi1, h, a1 - t), (xi0, h, a1 - t)], (0, 1, 0))
    quad(mass, [(xi0, h, a0 + t), (xi1, h, a0 + t), (xi1, top, a0 + t), (xi0, top, a0 + t)], (0, 0, 1))
    quad(mass, [(xi0, h, a1 - t), (xi1, h, a1 - t), (xi1, top, a1 - t), (xi0, top, a1 - t)], (0, 0, -1))
    quad(mass, [(xi0, h, a0 + t), (xi0, h, a1 - t), (xi0, top, a1 - t), (xi0, top, a0 + t)], (1, 0, 0))
    quad(mass, [(xi1, h, a0 + t), (xi1, h, a1 - t), (xi1, top, a1 - t), (xi1, top, a0 + t)], (-1, 0, 0))
    xo0, xo1 = sorted((F, back))
    for (q0, q1, r0, r1) in ((xo0, xo1, a0, a0 + t), (xo0, xo1, a1 - t, a1), (xo0, xi0, a0 + t, a1 - t), (xi1, xo1, a0 + t, a1 - t)):
        quad(mass, [(q0, top, r0), (q1, top, r0), (q1, top, r1), (q0, top, r1)], (0, 1, 0))
    fr.slab(hi, a0, a1, top - 0.45, top - 0.1, 0.0, -0.2, skip=(fr.in_key(),))
    fr.slab(hi, a0, a1, top - 0.02, top + 0.06, 0.03, -0.06, skip=())
    if depth * (a1 - a0) > 200:
        cx, cz = (F + back) / 2 - s * 2, (a0 + a1) / 2 + 2
        box(P.bm(f"RoofPlant_{bid}", "Metal_Dark"), (cx - 1.5, h, cz - 1.0), (cx + 1.5, h + 1.6, cz + 1.0), skip=("-y",))


def build_door(fr, P, bid, hh):
    a0, a1, y0, y1, d, _ = hh
    frame = P.bm(f"Frame_{bid}", "Frame_Dark")
    leaf = P.bm(f"Door_{bid}", "Door_Leaf")
    glass = P.bm(f"Glass_{bid}", "Shop_Glass")
    dd = d - 0.03
    for (u0, u1, v0, v1) in ((a0, a0 + 0.07, y0, y1), (a1 - 0.07, a1, y0, y1), (a0, a1, y1 - 0.08, y1)):
        fr.slab(frame, u0, u1, v0, v1, dd - 0.02, dd + 0.03, skip=(fr.in_key(),))
    mid = (a0 + a1) / 2
    for l0, l1 in ((a0 + 0.07, mid - 0.005), (mid + 0.005, a1 - 0.07)):
        fr.slab(leaf, l0, l1, 0.0, 0.95, dd, dd + 0.02, skip=(fr.in_key(), "-y"))
        fr.face(glass, l0 + 0.08, l1 - 0.08, 1.0, y1 - 0.2, d=dd + 0.01, uv=atlas_uv(3, inset=0.05))
        for (u0, u1, v0, v1) in ((l0, l0 + 0.08, 0.95, y1 - 0.08), (l1 - 0.08, l1, 0.95, y1 - 0.08), (l0, l1, y1 - 0.2, y1 - 0.08), (l0, l1, 0.95, 1.0)):
            fr.slab(leaf, u0, u1, v0, v1, dd - 0.005, dd + 0.02, skip=(fr.in_key(),))
        hx = l1 - 0.12 if l0 < mid else l0 + 0.06
        fr.slab(frame, hx, hx + 0.06, 0.9, 1.25, dd - 0.06, dd - 0.005, skip=(fr.in_key(),))


def build_awning(fr, P, bid, r0, r1, mat):
    aw = P.bm(f"Awning_{bid}", mat)
    y_top, out, drop, val = FASCIA_Y[0] + 0.02, 1.2, 0.45, 0.2
    P_ = fr.p
    quad(aw, [P_(r0, y_top, 0.0), P_(r1, y_top, 0.0), P_(r1, y_top - drop, -out), P_(r0, y_top - drop, -out)], (fr.s, 1, 0))
    quad(aw, [P_(r0, y_top - drop, -out), P_(r1, y_top - drop, -out), P_(r1, y_top - drop - val, -out), P_(r0, y_top - drop - val, -out)], (fr.s, 0, 0))
    for a, n in ((r0, -1), (r1, 1)):
        quad(aw, [P_(a, y_top, 0.0), P_(a, y_top - drop, -out), P_(a, y_top - drop - val, -out), P_(a, y_top - 0.12, 0.0)], (0, 0, n))


def build_segment_ground(P):
    z0, z1 = -SEG_L, 0.0
    zs = [0.0, -20.0, -40.0]                                   # 20 m lengths: no AO island longer than that
    road = P.bm("Road", "Road_Asphalt")
    for a, b_ in zip(zs[:-1], zs[1:]):
        quad(road, [(-ROAD_X, ROAD_Y, a), (ROAD_X, ROAD_Y, a), (ROAD_X, ROAD_Y, b_), (-ROAD_X, ROAD_Y, b_)], (0, 1, 0))
    kerb, walk = P.bm("Kerb", "Kerb_Stone"), P.bm("Sidewalk", "Sidewalk_Slab")
    for sgn in (-1, 1):
        xk = sgn * ROAD_X
        xa, xb = sorted((xk, xk + sgn * KERB_W))
        for a, b_ in zip(zs[:-1], zs[1:]):
            quad(kerb, [(xk, ROAD_Y, a), (xk, WALK_Y, a), (xk, WALK_Y, b_), (xk, ROAD_Y, b_)], (-sgn, 0, 0))
            quad(kerb, [(xa, WALK_Y, a), (xb, WALK_Y, a), (xb, WALK_Y, b_), (xa, WALK_Y, b_)], (0, 1, 0))
        xa, xb = sorted((xk + sgn * KERB_W, sgn * FRONT))
        for a, b_ in zip(zs[:-1], zs[1:]):
            quad(walk, [(xa, WALK_Y, a), (xb, WALK_Y, a), (xb, WALK_Y, b_), (xa, WALK_Y, b_)], (0, 1, 0))
    boxes = [seg_box(b) for b in SEG_BUILDINGS]
    for sgn in (-1, 1):                                        # the sidewalk's back edge steps down to the yards where no building stands on it
        xe = sgn * FRONT
        fronts = sorted((mn[2], mx[2]) for mn, mx in boxes if (mn[0] if sgn > 0 else mx[0]) == xe)
        z, gaps = z0, []
        for f0, f1 in fronts:
            if f0 > z:
                gaps.append((z, f0))
            z = max(z, f1)
        if z < z1:
            gaps.append((z, z1))
        for g0, g1 in gaps:
            quad(walk, [(xe, 0.0, g0), (xe, WALK_Y, g0), (xe, WALK_Y, g1), (xe, 0.0, g1)], (sgn, 0, 0))
    yard = P.bm("Yard", "Backlot_Ground")
    for sgn in (-1, 1):
        xs = sorted({sgn * FRONT, sgn * YARD_X} | {v for mn, mx in boxes for v in (mn[0], mx[0]) if v * sgn >= FRONT})
        zz = sorted({z0, z1} | {v for mn, mx in boxes for v in (mn[2], mx[2])})
        for i in range(len(xs) - 1):
            for j in range(len(zz) - 1):
                cx, cz = (xs[i] + xs[i + 1]) / 2, (zz[j] + zz[j + 1]) / 2
                if any(mn[0] < cx < mx[0] and mn[2] < cz < mx[2] for mn, mx in boxes):
                    continue
                quad(yard, [(xs[i], 0, zz[j]), (xs[i + 1], 0, zz[j]), (xs[i + 1], 0, zz[j + 1]), (xs[i], 0, zz[j + 1])], (0, 1, 0))
        for a, b_ in zip(zs[:-1], zs[1:]):                     # a skirt down to y -1 at the yards' outer edge (the collision floor is a metre thick)
            quad(yard, [(sgn * YARD_X, -1.0, a), (sgn * YARD_X, -1.0, b_), (sgn * YARD_X, 0.0, b_), (sgn * YARD_X, 0.0, a)], (sgn, 0, 0))
    line, yel = P.bm("RoadLine", "Road_Line"), P.bm("RoadYellow", "Road_Yellow")
    yp = ROAD_Y + 0.008
    for z in (-4.0, -12.0, -20.0, -28.0, -36.0):               # the centre dashes every 8 m (5 a segment, so they run on across segments)
        quad(line, [(-0.07, yp, z - 1.8), (0.07, yp, z - 1.8), (0.07, yp, z + 1.8), (-0.07, yp, z + 1.8)], (0, 1, 0))
    for sgn in (-1, 1):                                        # double yellow lines along both kerbs, as on the street
        for off in (0.25, 0.42):
            xa = sgn * (ROAD_X - off) - 0.045
            for a, b_ in zip(zs[:-1], zs[1:]):
                quad(yel, [(xa, yp, a), (xa + 0.09, yp, a), (xa + 0.09, yp, b_), (xa, yp, b_)], (0, 1, 0))
    dr = P.bm("Drains", "Drain_Iron")
    duv = [(0, 0), (1, 0), (1, 1), (0, 1)]
    for z in (-6.0, -18.0, -30.0):
        for sgn in (-1, 1):
            xa, xb = sorted((sgn * (ROAD_X - 0.02), sgn * (ROAD_X - 0.38)))
            quad(dr, [(xa, ROAD_Y + 0.006, z - 0.3), (xb, ROAD_Y + 0.006, z - 0.3), (xb, ROAD_Y + 0.006, z + 0.3), (xa, ROAD_Y + 0.006, z + 0.3)], (0, 1, 0), duv)
    x = 1.7
    quad(dr, [(x - 0.35, ROAD_Y + 0.006, -24.35), (x + 0.35, ROAD_Y + 0.006, -24.35), (x + 0.35, ROAD_Y + 0.006, -23.65), (x - 0.35, ROAD_Y + 0.006, -23.65)],
         (0, 1, 0), [(0.1, 0.0), (0.9, 0.0), (0.9, 1.0), (0.1, 1.0)])


def build_lamps(P):
    """The street's lamp posts (tools/blender/build_street.py build_lamps): a base the collider's size, a tapered pole, an arm over the road, a head
    with its lens (`Lamp_Emit`)."""
    for z in SEG_LAMP_ZS:
        for sgn in (-1, 1):
            x, hw = sgn * 5.5, 0.1
            tag = f"{'E' if sgn > 0 else 'W'}{abs(int(z)):03d}"
            post = P.bm(f"LampPost_{tag}", "Metal_Dark")
            box(post, (x - hw, 0.0, z - hw), (x + hw, 0.55, z + hw), skip=("-y",))
            cyl(post, (x, 0.55, z), (x, 4.75, z), 0.065, 0.05, seg=8)
            head = P.bm(f"LampHead_{tag}", "Metal_Dark")
            ex = x - sgn * 1.25
            cyl(head, (x, 4.70, z), (ex, 4.78, z), 0.035, seg=6)
            box(head, (min(ex, ex - sgn * 0.55), 4.68, z - 0.16), (max(ex, ex - sgn * 0.55), 4.82, z + 0.16))
            lens = P.bm(f"LampLens_{tag}", "Lamp_Emit")
            l0, l1 = sorted((ex - sgn * 0.05, ex - sgn * 0.5))
            quad(lens, [(l0, 4.675, z - 0.12), (l1, 4.675, z - 0.12), (l1, 4.675, z + 0.12), (l0, 4.675, z + 0.12)], (0, -1, 0))


SLOT_COLL = {}


def build_street_segment():
    street_materials()
    for b in SEG_BUILDINGS:
        material(f"Facade_{b['id']}", diff=b["tex"], tint=facade_tint(b), rough=0.9, tile=b["tile"])
    P = Parts(ART)
    build_segment_ground(P)
    build_lamps(P)
    for b in SEG_BUILDINGS:
        if b["id"].startswith("fill"):
            build_building(b, P)
    P.done()
    for b in SEG_BUILDINGS:                                    # each slot's building in its own collection (exported as its own node, slot_W / slot_E)
        if not b["id"].startswith("slot"):
            continue
        c = bpy.data.collections.new("Slot_" + b["id"])
        ART.children.link(c)
        SLOT_COLL[b["id"]] = c
        Ps = Parts(c)
        build_building(b, Ps)
        Ps.done()
    # the layout
    collider("Ground_Segment", (-YARD_X, -1.0, -SEG_L), (YARD_X, 0.0, 0.0), prefix="COL_")
    for b in SEG_BUILDINGS:
        mn, mx = seg_box(b)
        collider("Building_" + b["id"], mn, mx)
    for z in SEG_LAMP_ZS:
        for sgn in (-1, 1):
            collider("Lamp_Street", (sgn * 5.5 - 0.1, 0.0, z - 0.1), (sgn * 5.5 + 0.1, 4.2, z + 0.1))
    # the lamp colliders share one name in the layout (as on the street); Blender renames the copies .001.., which export_scene skips, so name them apart
    for i, o in enumerate(sorted([o for o in LAYOUT.objects if o.name.startswith("COL_Lamp_Street")], key=lambda o: o.name)):
        o.name = f"COL_Lamp_Street_{i + 1}"
    for b in SEG_BUILDINGS:
        if b["door_z"] is None:
            continue
        sgn = -1 if b["side"] == "w" else 1
        face = (-sgn * 1.0, 0.0)
        empty(f"Link_{b['id']}", (sgn * (FRONT - 0.6), 0.0, b["door_z"]))
        empty(f"Arrive_{b['id']}", (sgn * (FRONT - 1.1), 0.0, b["door_z"]), face=face, kind="SINGLE_ARROW")
    for i, (x, z) in enumerate(SEG_BINS):
        empty(f"Spot_bin_{i + 1}", (x, 0.0, z), face=(-1.0 if x > 0 else 1.0, 0.0), props={"what": "the trash route's bin at the kerb"})


# ================================================================ the bus stop
# The frame: the origin is the middle of the bench, on the ground. The shelter's back is to -z (north on the street), its open side to +z, the road
# to -x (as the street's stop at shared/city.js BUS_STREET.shelter (7, 5), where it lands with at (7, 0, 5) and yaw 0: the bench's collider is then
# exactly world/street.json's Bench_BusStop, and the link is BUS_STREET's own at and arrive).
BS_W = 1.22                               # the shelter's half width (x)
BS_BACK = (-0.38, -0.28)                  # the back panel's collider (z)
BS_SIDE_Z = (-0.30, 0.82)                 # the east side panel's collider (z)
BS_ROOF = (2.32, 2.46)
BS_POLE = (-1.55, 0.35)                   # the flag pole, by the kerb on the street


def build_bus_stop():
    material("Steel_Grey", color=(0.36, 0.37, 0.38), rough=0.4, metal=0.6)
    material("Bench_Steel", color=(0.05, 0.11, 0.08), rough=0.45, metal=0.5)
    material("Shelter_Glass", color=(0.55, 0.62, 0.65), rough=0.05, alpha=0.18)
    material("Signs", diff="signs_city.png", rough=0.5)
    material("Poster", diff="ad_poster.png", rough=0.3)
    material("Roof_Panel", color=(0.30, 0.31, 0.32), rough=0.5, metal=0.5)
    P = Parts(ART)
    zb = (BS_BACK[0] + BS_BACK[1]) / 2                           # the back glass's plane, z -0.33
    fr = P.bm("Shelter_Back", "Steel_Grey")
    gl = P.bm("decor_Shelter_Glass_Back", "Shelter_Glass")
    for x in (-BS_W + 0.06, 0.0, BS_W - 0.06):                   # two posts and a mullion
        w = 0.04 if x else 0.025
        box(fr, (x - w, 0.0, zb - 0.04), (x + w, 2.36 if x else 2.24, zb + 0.04), skip=("-y",))
    for y0, y1 in ((0.06, 0.12), (2.20, 2.26)):
        box(fr, (-BS_W + 0.02, y0, zb - 0.03), (BS_W - 0.02, y1, zb + 0.03))
    for x0, x1 in ((-BS_W + 0.10, -0.025), (0.025, BS_W - 0.10)):
        for n in (1, -1):
            quad(gl, [(x0, 0.12, zb), (x1, 0.12, zb), (x1, 2.20, zb), (x0, 2.20, zb)], (0, 0, n))
    # the east side panel: a post at the front, the advert in a slim frame (both faces)
    sd = P.bm("Shelter_Side", "Steel_Grey")
    xs = BS_W - 0.06
    box(sd, (xs - 0.04, 0.0, BS_SIDE_Z[1] - 0.08), (xs + 0.04, 2.36, BS_SIDE_Z[1]), skip=("-y",))
    box(sd, (xs - 0.05, 0.22, zb + 0.04), (xs + 0.05, 0.28, BS_SIDE_Z[1] - 0.08))
    box(sd, (xs - 0.05, 2.10, zb + 0.04), (xs + 0.05, 2.16, BS_SIDE_Z[1] - 0.08))
    po = P.bm("Shelter_Poster", "Poster")
    for n in (1, -1):
        xp = xs + n * 0.051
        uv = [(0, 0), (1, 0), (1, 1), (0, 1)] if n > 0 else [(1, 0), (0, 0), (0, 1), (1, 1)]
        quad(po, [(xp, 0.28, BS_SIDE_Z[1] - 0.08), (xp, 0.28, zb + 0.04), (xp, 2.10, zb + 0.04), (xp, 2.10, BS_SIDE_Z[1] - 0.08)], (n, 0, 0),
             uv if n > 0 else [(1, 0), (0, 0), (0, 1), (1, 1)])
    box(P.bm("Shelter_Side_Back", "Steel_Grey"), (xs - 0.05, 0.28, zb + 0.04), (xs + 0.05, 2.10, zb + 0.07))
    # the roof: two arms from the back posts out over the bench, a panel, a fascia with HALLAM ROW on its front (over head height)
    rf = P.bm("decor_Shelter_Roof", "Roof_Panel")
    for x in (-BS_W + 0.06, BS_W - 0.06):
        box(rf, (x - 0.035, BS_ROOF[0], zb - 0.06), (x + 0.035, BS_ROOF[0] + 0.08, 1.24))
    box(rf, (-BS_W - 0.03, BS_ROOF[0] + 0.08, zb - 0.09), (BS_W + 0.03, BS_ROOF[0] + 0.13, 1.30))
    box(rf, (-BS_W - 0.03, BS_ROOF[0] - 0.04, 1.26), (BS_W + 0.03, BS_ROOF[1] + 0.04, 1.32), skip=("+z", "-z"))
    fa = P.bm("decor_Shelter_Fascia", "Signs")
    quad(fa, [(-BS_W - 0.03, BS_ROOF[0] - 0.04, 1.32), (BS_W + 0.03, BS_ROOF[0] - 0.04, 1.32), (BS_W + 0.03, BS_ROOF[1] + 0.04, 1.32),
              (-BS_W - 0.03, BS_ROOF[1] + 0.04, 1.32)], (0, 0, 1), sign_uv("fascia"))
    quad(fa, [(BS_W + 0.03, BS_ROOF[0] - 0.04, 1.26), (-BS_W - 0.03, BS_ROOF[0] - 0.04, 1.26), (-BS_W - 0.03, BS_ROOF[1] + 0.04, 1.26),
              (BS_W + 0.03, BS_ROOF[1] + 0.04, 1.26)], (0, 0, -1), sign_uv("fascia"))
    # the bench, inside the street's Bench_BusStop box (1.4 x 0.6 m, 0.9 m high): a slatted steel seat and back on two cantilever legs
    bn = P.bm("Bench", "Bench_Steel")
    for k in range(5):
        z0 = -0.22 + k * 0.096
        box(bn, (-0.66, 0.42, z0), (0.66, 0.46, z0 + 0.08))
    for k in range(3):
        y0 = 0.52 + k * 0.12
        box(bn, (-0.66, y0, -0.29), (0.66, y0 + 0.09, -0.25))
    for x in (-0.52, 0.52):
        box(bn, (x - 0.03, 0.0, -0.28), (x + 0.03, 0.42, -0.20), skip=("-y",))
        box(bn, (x - 0.03, 0.38, -0.28), (x + 0.03, 0.42, 0.26))
        box(bn, (x - 0.03, 0.42, -0.30), (x + 0.03, 0.88, -0.245))
        box(bn, (x - 0.08, 0.0, -0.30), (x + 0.08, 0.03, -0.18), skip=("-y",))
    # the flag pole: a round pole, a cap, the timetable case at chest height (on the pole's +z side), the flag over head height
    px, pz = BS_POLE
    pl = P.bm("Sign_Pole", "Steel_Grey")
    cyl(pl, (px, 0.0, pz), (px, 2.95, pz), 0.045, seg=12)
    cyl(pl, (px, 2.95, pz), (px, 2.99, pz), 0.055, 0.03, seg=12)
    box(pl, (px - 0.15, 1.25, pz + 0.045), (px + 0.15, 1.75, pz + 0.075))
    tt = P.bm("decor_Sign_Timetable", "Signs")
    quad(tt, [(px - 0.135, 1.27, pz + 0.076), (px + 0.135, 1.27, pz + 0.076), (px + 0.135, 1.73, pz + 0.076), (px - 0.135, 1.73, pz + 0.076)], (0, 0, 1),
         sign_uv("timetable"))
    fl = P.bm("decor_Sign_Flag", "Signs")
    f0, f1, y0, y1 = px - 0.53, px - 0.05, 2.30, 2.90             # the flag stands out over the kerb, away from the shelter's roof
    quad(fl, [(f0, y0, pz + 0.011), (f1, y0, pz + 0.011), (f1, y1, pz + 0.011), (f0, y1, pz + 0.011)], (0, 0, 1), sign_uv("flag"))
    quad(fl, [(f1, y0, pz - 0.011), (f0, y0, pz - 0.011), (f0, y1, pz - 0.011), (f1, y1, pz - 0.011)], (0, 0, -1), sign_uv("flag"))
    fe = P.bm("decor_Sign_Flag_Edge", "Steel_Grey")
    box(fe, (f0 - 0.01, y0 - 0.01, pz - 0.01), (f1 + 0.01, y0, pz + 0.01))
    box(fe, (f0 - 0.01, y1, pz - 0.01), (f1 + 0.01, y1 + 0.01, pz + 0.01))
    box(fe, (f0 - 0.01, y0, pz - 0.01), (f0, y1, pz + 0.01))
    for y in (y0 + 0.08, y1 - 0.08):
        box(fe, (f1, y - 0.02, pz - 0.02), (px - 0.04, y + 0.02, pz + 0.02))
    P.done()
    # the layout
    collider("Edge_Ground_host", (-4.0, -1.0, -2.0), (2.5, 0.0, 2.0), prefix="")   # the host's ground (invisible here; the street or the lot is the floor)
    bpy.data.objects["Edge_Ground_host"].name = "COL_Edge_Ground_host"
    collider("Bench", (-0.7, 0.0, -0.3), (0.7, 0.9, 0.3))
    collider("Shelter_Back", (-BS_W, 0.0, BS_BACK[0]), (BS_W, BS_ROOF[0], BS_BACK[1]))
    collider("Shelter_Side", (BS_W - 0.14, 0.0, BS_SIDE_Z[0]), (BS_W, BS_ROOF[0], BS_SIDE_Z[1]))
    collider("Sign_Pole", (px - 0.17, 0.0, pz - 0.06), (px + 0.17, 2.95, pz + 0.10))
    empty("Link_bus_stop", (-0.8, 0.0, -1.0))                  # the street's BUS_STREET: at (6.2, 4.0), arrive (3.6, 0, 4.0) facing north
    empty("Arrive_bus_stop", (-3.4, 0.0, -1.0), face=(0.0, -1.0), kind="SINGLE_ARROW")


# ================================================================ the depot yard and the truck
# The frame: the origin is the middle of the yard's gate, on the ground, on the fence's line; the lane to the street is on +z, the yard toward -z
# (24 m by 24 m: x -12 to 12, z 0 to -24). On the street it stands behind 41 Hallam Row with at (-26, 0, -50) and yaw 90: the gate faces east down
# the 4 m gap between 41 and the filler north of it (z -48 to -52) to the road, and the yard covers x -26 to -50, z -38 to -62.
DY_X, DY_Z = 12.0, 24.0
DY_WALL_T, DY_WALL_H = 0.36, 2.6
DY_GATE = 3.0                             # the gate opening's half width; the two leaves are 2.98 m each
DY_PIER = 0.45
DY_FENCE_H = 2.4
TRUCK_AT = (3.5, 0.0, -13.0)              # the truck's pivot (its footprint's middle, on the ground); it faces +z, the gate
TRUCK_L, TRUCK_W = 9.0, 2.5
TRUCK_COLS = {"Truck_parked": ((-1.45, 0.4, -4.1), (1.45, 3.45, 4.66)), "Truck_parked_rear": ((-1.24, 0.45, -4.74), (1.24, 3.45, -4.05))}   # truck coordinates
OFFICE = (-11.0, -5.0, -23.0, -20.4)      # x0, x1, z0, z1 (0.64 m clear of the walls behind and beside it)
BINS_ROWS = [(-3.6, -10.4), (-11.6, -16.4)]


def depot_materials():
    material("Yard_Concrete", diff="yard_concrete.jpg", tint=(0.72, 0.72, 0.70), rough=0.9, tile=6.0)
    material("Wall_Brick", diff="brick_red.jpg", tint=(1.0, 0.92, 0.88), rough=0.9, tile=2.6)
    material("Trim_Concrete", diff="concrete.jpg", tint=(0.80, 0.79, 0.76), rough=0.85, tile=2.0)
    material("Fence_Steel", color=(0.04, 0.09, 0.06), rough=0.5, metal=0.5)
    material("Office_Panel", diff="gate.jpg", tint=(1.6, 1.62, 1.55), rough=0.6, tile=2.0)
    material("Office_Trim", color=(0.30, 0.31, 0.30), rough=0.6)
    material("Door_Leaf", color=(0.055, 0.09, 0.075), rough=0.45)
    material("Window_Dark", color=(0.03, 0.035, 0.045), rough=0.08)
    material("Window_Lit", color=(0.03, 0.032, 0.035), rough=0.1, emit=((1, 1, 1), WINDOW_EMIT), emit_img="window_lit.jpg")
    material("Bin_Green", color=(0.06, 0.22, 0.09), rough=0.45)
    material("Rubber_Black", color=(0.03, 0.03, 0.03), rough=0.8)
    material("Skip_Yellow", color=(0.62, 0.44, 0.04), rough=0.55, metal=0.3)
    material("Metal_Dark", color=(0.03, 0.032, 0.035), rough=0.45, metal=0.6)
    material("Steel_Grey", color=(0.36, 0.37, 0.38), rough=0.4, metal=0.6)
    material("Lamp_Emit", color=(0.62, 0.60, 0.55), rough=0.3, emit=LAMP_EMIT)
    material("Signs", diff="signs_city.png", rough=0.5)
    material("Paint_Yellow", color=(0.62, 0.44, 0.06), rough=0.6)
    material("Drain_Iron", diff="drain.jpg", rough=0.6, metal=0.3)
    # what moves (not baked): the gate's leaves and the truck
    material("Leaf_Steel", color=(0.04, 0.09, 0.06), rough=0.5, metal=0.5)
    for n, c, r, m in (("Truck_White", (0.62, 0.63, 0.60), 0.4, 0.0), ("Truck_Green", TRUCK_GREEN, 0.45, 0.0), ("Truck_Dark", (0.025, 0.026, 0.028), 0.6, 0.2),
                       ("Truck_Glass", (0.02, 0.025, 0.03), 0.05, 0.0), ("Truck_Light", (0.70, 0.68, 0.58), 0.2, 0.0), ("Truck_Red", (0.45, 0.03, 0.02), 0.3, 0.0),
                       ("Truck_Amber", (0.70, 0.36, 0.02), 0.3, 0.0), ("Truck_Steel", (0.40, 0.41, 0.42), 0.4, 0.7), ("Truck_Tyre", (0.025, 0.025, 0.025), 0.85, 0.0),
                       ("Truck_Hub", (0.42, 0.43, 0.44), 0.35, 0.7)):
        material(n, color=c, rough=r, metal=m)
    material("Truck_Signs", diff="signs_city.png", rough=0.45)


def bin_centres(za, zb, pitch=0.70):
    """The bins' centres (z) in a row from za down to zb, centred in it."""
    n = int((za - zb) // pitch)
    off = ((za - zb) - n * pitch) / 2
    return [za - off - pitch / 2 - i * pitch for i in range(n)]


def palisade(bm, x0, x1, z, h, pitch=0.16, pale=0.065):
    """A steel palisade along x at z: two rails, D-section pales with a three-point top (a prism each)."""
    for y in (0.45, h - 0.35):
        box(bm, (x0, y, z - 0.035), (x1, y + 0.05, z + 0.035) if True else None)
    n = int((x1 - x0) / pitch)
    off = ((x1 - x0) - (n - 1) * pitch) / 2
    for i in range(n):
        x = x0 + off + i * pitch
        a, b = x - pale / 2, x + pale / 2
        prism_pts = [(z - 0.012, 0.3), (z + 0.012, 0.3), (z + 0.012, h - 0.08), (z, h), (z - 0.012, h - 0.08)]
        prism(bm, prism_pts, a, b)


def build_truck(coll):
    """The trash truck: a rear-loading refuse truck, 9 m by 2.5 m. Nodes: trash_truck (the pivot, on the ground under the footprint's middle; it
    faces +z), trash_truck_body, Truck_wheel_FL/FR/RL/RR (each on its axle, spinning about x; the front pair also steer about y) and
    Truck_tailgate (hinged at its top, about x). Built in truck coordinates (origin at the pivot), then moved to TRUCK_AT."""
    ox, oy, oz = TRUCK_AT
    T = lambda p: (p[0] + ox, p[1] + oy, p[2] + oz)            # noqa: E731  truck coordinates -> kit
    root = bpy.data.objects.new("trash_truck", None)
    root.empty_display_type = "ARROWS"
    root.location = B(TRUCK_AT)
    for k, v in {"what": "the trash truck (rear loader)", "length_m": TRUCK_L, "width_m": TRUCK_W, "faces": "+z", "parked": "kit (3.5, 0, -13)"}.items():
        root[k] = v
    coll.objects.link(root)
    P = Parts(coll)
    W2 = 1.22
    # the cab: low entry, white over a green band, a big windscreen, side windows, a black bumper, a grille, lights, mirrors, a beacon
    cab_z0, cab_z1 = 1.95, 4.45
    bevel_box(P.bm("t_cab", "Truck_White"), T((-W2, 1.15, cab_z0)), T((W2, 3.05, cab_z1)), r=0.08)
    band = P.bm("t_cab_band", "Truck_Green")                    # the green band under the windows, cut round the front wheels' arches
    fa0, fa1 = 2.7 - 0.62, 2.7 + 0.62
    bevel_box(band, T((-W2 - 0.005, 0.55, fa1)), T((W2 + 0.005, 1.15, cab_z1 + 0.005)), r=0.04)
    box(band, T((-W2 - 0.005, 0.55, cab_z0 + 0.02)), T((W2 + 0.005, 1.15, fa0)))
    box(band, T((-0.80, 0.55, fa0)), T((0.80, 1.15, fa1)))
    for sx in (-1, 1):
        box(band, T((min(sx * 0.80, sx * (W2 + 0.005)), 1.10, fa0)), T((max(sx * 0.80, sx * (W2 + 0.005)), 1.15, fa1)))
    g = P.bm("t_glass", "Truck_Glass")
    quad(g, [T((-1.08, 1.78, cab_z1 + 0.012)), T((1.08, 1.78, cab_z1 + 0.012)), T((1.04, 2.86, cab_z1 + 0.012)), T((-1.04, 2.86, cab_z1 + 0.012))], (0, 0, 1))
    for sx in (-1, 1):
        xg = sx * (W2 + 0.012)
        quad(g, [T((xg, 1.72, 3.0)), T((xg, 1.72, 4.25)), T((xg, 2.80, 4.25)), T((xg, 2.80, 3.0))], (sx, 0, 0))
        quad(g, [T((xg, 1.72, 2.1)), T((xg, 1.72, 2.85)), T((xg, 2.80, 2.85)), T((xg, 2.80, 2.1))], (sx, 0, 0))
    d = P.bm("t_dark", "Truck_Dark")
    box(d, T((-1.2, 0.42, cab_z1 - 0.05)), T((1.2, 0.86, cab_z1 + 0.16)))                     # the bumper
    box(d, T((-0.78, 0.95, cab_z1)), T((0.78, 1.58, cab_z1 + 0.02)))                          # the grille
    for y in (1.05, 1.2, 1.35, 1.5):
        box(P.bm("t_grille_bars", "Truck_Steel"), T((-0.74, y, cab_z1 + 0.02)), T((0.74, y + 0.03, cab_z1 + 0.035)))
    li = P.bm("t_lights", "Truck_Light")
    for sx in (-1, 1):
        box(li, T((sx * 0.86 - 0.16, 1.0, cab_z1 + 0.005)), T((sx * 0.86 + 0.16, 1.22, cab_z1 + 0.03)))
        cyl(d, T((sx * W2, 2.45, 4.25)), T((sx * 1.40, 2.45, 4.25)), 0.02, seg=6)              # the mirror arms
        box(d, T((sx * 1.40 - 0.03, 2.2, 4.15)), T((sx * 1.40 + 0.03, 2.62, 4.35)))           # the mirrors
        box(d, T((sx * (W2 - 0.25) - 0.25, 0.42, 3.55)), T((sx * (W2 - 0.25) + 0.25, 0.48, 3.95)))   # a step under each door
    cyl(P.bm("t_beacon", "Truck_Amber"), T((0, 3.05, 3.3)), T((0, 3.2, 3.3)), 0.09, seg=12)
    # the chassis, the lockers between the axles, the mudguards, the fuel tank
    for sx in (-1, 1):
        box(d, T((sx * 0.5 - 0.1, 0.62, -4.1)), T((sx * 0.5 + 0.1, 0.92, 4.2)))
    box(d, T((-0.75, 0.55, -0.7)), T((0.75, 0.95, 1.85)))
    for sx in (-1, 1):                                           # the mudguards over the rear duals
        box(d, T((min(sx * 0.58, sx * 1.26), 1.10, -2.25)), T((max(sx * 0.58, sx * 1.26), 1.16, -0.95)))
    cyl(P.bm("t_tank", "Truck_Steel"), T((-1.0, 0.75, 0.0)), T((-1.0, 0.75, 1.3)), 0.22, seg=12)
    # the body: green, its top edges rounded, the street's name on both sides, a ladder at the back
    bevel_box(P.bm("t_body", "Truck_Green"), T((-W2, 0.95, -3.45)), T((W2, 3.45, 1.88)), r=0.14, seg=3)
    sg = P.bm("t_signs", "Truck_Signs")
    for sx in (-1, 1):                                           # read left to right from outside: toward -z on the +x side, toward +z on the -x side
        xg = sx * (W2 + 0.006)
        za, zb = (1.3, -2.9) if sx > 0 else (-2.9, 1.3)
        quad(sg, [T((xg, 2.05, za)), T((xg, 2.05, zb)), T((xg, 2.7, zb)), T((xg, 2.7, za))], (sx, 0, 0), sign_uv("truck"))
    body = [o for o in P.done()]
    tb = joined("trash_truck_body", body, coll, origin=TRUCK_AT, parent=root)
    # the wheels: tyre and hub, each its own node on its axle (spinning about x)
    R, axles = 0.52, {"F": (2.7, 0.34, 1.05), "R": (-1.6, 0.64, 0.92)}
    for key, (az, tw, xc) in axles.items():
        for sx, side in ((-1, "L"), (1, "R")):
            Pw = Parts(coll)
            c = (sx * xc, R, az)
            tyre = Pw.bm("w_tyre", "Truck_Tyre", smooth=True)
            if key == "R":                                       # the rear duals: two tyres with a gap
                for off in (-0.17, 0.17):
                    cyl(tyre, T((c[0] + off - 0.14, R, az)), T((c[0] + off + 0.14, R, az)), R, seg=20)
            else:
                cyl(tyre, T((c[0] - tw / 2, R, az)), T((c[0] + tw / 2, R, az)), R, seg=20)
            hub = Pw.bm("w_hub", "Truck_Hub")
            xo = c[0] + sx * (tw / 2 + 0.005)
            cyl(hub, T((xo - sx * 0.01, R, az)), T((xo, R, az)), R * 0.62, seg=16)
            cyl(hub, T((xo, R, az)), T((xo + sx * 0.06, R, az)), R * 0.2, seg=10)
            w = joined(f"Truck_wheel_{key}{side}", Pw.done(), coll, origin=T(c), parent=root)
            for k, v in {"axis": "x", "motion": "roll", "radius_m": R, "steer": key == "F"}.items():
                w[k] = v
    # the tailgate: the hopper at the back, hinged at its top edge (y 3.45, z -3.45 in truck coordinates); the chevrons on its back, the bin lift
    Pt = Parts(coll)
    hz0, hz1, top = -4.5, -3.45, 3.45
    sec = [(hz1, 0.75), (hz1, top), (hz1 - 0.55, top), (hz0, 2.2), (hz0, 0.75)]        # the hopper's section (z, y), truck coordinates
    prism(Pt.bm("g_shell", "Truck_Green"), [(z + oz, y + oy) for z, y in sec], ox - W2, ox + W2)
    cv = Pt.bm("g_chev", "Truck_Signs")
    zc = hz0 - 0.008
    quad(cv, [T((-W2 + 0.05, 0.85, zc)), T((W2 - 0.05, 0.85, zc)), T((W2 - 0.05, 2.1, zc)), T((-W2 + 0.05, 2.1, zc))], (0, 0, -1), sign_uv("chevrons"))
    lift = Pt.bm("g_lift", "Truck_Steel")
    for sx in (-1, 1):
        box(lift, T((sx * 0.75 - 0.05, 0.45, hz0 - 0.18)), T((sx * 0.75 + 0.05, 1.45, hz0 - 0.02)))
        box(Pt.bm("g_tail", "Truck_Red"), T((sx * 1.05 - 0.1, 0.9, hz0 - 0.03)), T((sx * 1.05 + 0.1, 1.25, hz0)))
    box(lift, T((-0.85, 1.3, hz0 - 0.2)), T((0.85, 1.4, hz0 - 0.02)))
    box(lift, T((-0.85, 0.45, hz0 - 0.2)), T((0.85, 0.55, hz0 - 0.02)))
    tg = joined("Truck_tailgate", Pt.done(), coll, origin=T((0.0, top, hz1)), parent=root)
    for k, v in {"axis": "x", "motion": "tilt", "range_deg": 70.0, "pivot": "top rear edge of the body"}.items():
        tg[k] = v
    return root


def build_gate_leaf(name, hinge_x, ext, coll):
    """One palisade gate leaf (own node `Leaf_<name>`, origin at its hinge): a tube frame, pales, a drop bolt."""
    Pl = Parts(coll)
    bm = Pl.bm("l", "Leaf_Steel")
    x0, x1 = sorted((hinge_x, hinge_x + ext))
    for y in (0.06, 1.05, DY_FENCE_H - 0.3):
        box(bm, (x0, y, -0.03), (x1, y + 0.06, 0.03))
    for x in (x0, x1 - 0.06):
        box(bm, (x, 0.06, -0.03), (x + 0.06, DY_FENCE_H - 0.24, 0.03))
    palisade(bm, x0 + 0.08, x1 - 0.08, 0.0, DY_FENCE_H, pitch=0.16)
    leaf = joined(f"Leaf_{name}", Pl.done(), coll, origin=(hinge_x, 0.0, 0.0))
    return leaf


def build_depot_yard():
    depot_materials()
    P = Parts(ART)
    X, Z = DY_X, DY_Z
    # the yard's floor: concrete in 12 m squares, a skirt down to y -1 at its edges
    gr = P.bm("Yard_Floor", "Yard_Concrete")
    for x0 in (-X, 0.0):
        for z0 in (0.0, -12.0):
            quad(gr, [(x0, 0, z0), (x0 + X, 0, z0), (x0 + X, 0, z0 - 12), (x0, 0, z0 - 12)], (0, 1, 0))
    for (a, b_, c, n) in (((-X, -Z), (X, -Z), "z", (0, 0, -1)), ((-X, 0.0), (X, 0.0), "z", (0, 0, 1)), ((-X, -Z), (-X, 0.0), "x", (-1, 0, 0)), ((X, -Z), (X, 0.0), "x", (1, 0, 0))):
        quad(gr, [(a[0], -1.0, a[1]), (b_[0], -1.0, b_[1]), (b_[0], 0.0, b_[1]), (a[0], 0.0, a[1])], n)
    # the walls: dark brick on three sides, a darker plinth, a concrete coping; three strands of barbed wire on brackets over them (decor_)
    T_, H_ = DY_WALL_T, DY_WALL_H
    runs = {"back": ((-X, 0, -Z), (X, H_, -Z + T_)), "W": ((-X, 0, -Z + T_), (-X + T_, H_, 0.0)), "E": ((X - T_, 0, -Z + T_), (X, H_, 0.0))}
    for k, (mn, mx) in runs.items():                            # faces never seen are left out (they would bake black): the tops under the coping,
        box(P.bm(f"Wall_{k}", "Wall_Brick"), mn, mx, skip=("-y", "+y") + (("+z",) if k != "back" else ()))   # the side walls' ends in the piers
        cp = P.bm(f"Coping_{k}", "Trim_Concrete")
        box(cp, (mn[0] - 0.03, H_, mn[2] - 0.03), (mx[0] + 0.03, H_ + 0.08, mx[2] + 0.03), skip=("-y",))
    wire = P.bm("decor_Barbed", "Metal_Dark")
    for (p0, p1) in (((-X + 0.1, -Z + 0.18), (X - 0.1, -Z + 0.18)), ((-X + 0.18, -Z + 0.1), (-X + 0.18, -0.3)), ((X - 0.18, -Z + 0.1), (X - 0.18, -0.3))):
        ln = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        n = max(2, int(ln / 3.0) + 1)
        for i in range(n):
            t = i / (n - 1)
            bx, bz = p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t
            box(wire, (bx - 0.015, H_ + 0.08, bz - 0.015), (bx + 0.015, H_ + 0.55, bz + 0.015))
        for y in (H_ + 0.22, H_ + 0.36, H_ + 0.5):
            cyl(wire, (p0[0], y, p0[1]), (p1[0], y, p1[1]), 0.006, seg=4, cap=False)
    # the front: brick piers at the corners and at the gate, a palisade on a concrete plinth either side of the gate, the depot's name board
    piers = {"corner_W": (-X, -X + T_), "gate_W": (-DY_GATE - DY_PIER, -DY_GATE), "gate_E": (DY_GATE, DY_GATE + DY_PIER), "corner_E": (X - T_, X)}
    for k, (x0, x1) in piers.items():
        zc0, zc1 = (-DY_PIER / 2, DY_PIER / 2) if k.startswith("gate") else (-T_ - 0.03, 0.03)
        if k.startswith("corner"):                              # 3 cm proud of the wall's end, so no face lies in the wall's
            x0, x1 = x0 - 0.03, x1 + 0.03
        box(P.bm(f"Pier_{k}", "Wall_Brick"), (x0, 0.0, zc0), (x1, 2.8, zc1), skip=("-y", "+y") + (("-z",) if k.startswith("corner") else ()))
        box(P.bm(f"PierCap_{k}", "Trim_Concrete"), (x0 - 0.04, 2.8, zc0 - 0.04), (x1 + 0.04, 2.9, zc1 + 0.04))
    fences = {"W": (-X + T_, -DY_GATE - DY_PIER), "E": (DY_GATE + DY_PIER, X - T_)}
    for k, (x0, x1) in fences.items():
        box(P.bm(f"Plinth_{k}", "Trim_Concrete"), (x0, 0.0, -0.075), (x1, 0.3, 0.075), skip=("-y",))
        palisade(P.bm(f"Fence_{k}", "Fence_Steel"), x0, x1, 0.0, DY_FENCE_H)
    sg = P.bm("Sign_Depot", "Signs")
    quad(sg, [(-9.0, 1.0, 0.085), (-5.0, 1.0, 0.085), (-5.0, 1.8, 0.085), (-9.0, 1.8, 0.085)], (0, 0, 1), sign_uv("depot"))
    box(P.bm("Sign_Depot_Back", "Metal_Dark"), (-9.04, 0.96, 0.04), (-4.96, 1.84, 0.08))
    quad(P.bm("Sign_NoParking", "Signs"), [(5.0, 1.0, 0.085), (7.0, 1.0, 0.085), (7.0, 1.6, 0.085), (5.0, 1.6, 0.085)], (0, 0, 1), sign_uv("noparking"))
    box(P.bm("Sign_NoParking_Back", "Metal_Dark"), (4.96, 0.96, 0.04), (7.04, 1.64, 0.08))
    # the site office: a steel cabin on blocks, a door with two steps, two windows (one lit at night), its sign
    x0, x1, z0, z1 = OFFICE
    ob = P.bm("Office", "Office_Panel")
    box(ob, (x0, 0.28, z0), (x1, 2.85, z1), skip=("-y", "+y"))   # the underside (on blocks, 28 cm up) and the top (under the roof trim) are never seen
    otr = P.bm("Office_Trim", "Office_Trim")
    for bx in (x0 + 0.2, (x0 + x1) / 2, x1 - 0.5):
        for bz in (z0 + 0.15, z1 - 0.45):
            box(otr, (bx, 0.0, bz), (bx + 0.3, 0.28, bz + 0.3), skip=("-y",))
    box(otr, (x0 - 0.04, 2.85, z0 - 0.04), (x1 + 0.04, 2.92, z1 + 0.04))
    dx = -9.6
    box(P.bm("Office_Door", "Door_Leaf"), (dx - 0.45, 0.30, z1), (dx + 0.45, 2.3, z1 + 0.02))
    box(otr, (dx - 0.5, 2.3, z1), (dx + 0.5, 2.36, z1 + 0.04))
    stp = P.bm("Office_Steps", "Steel_Grey")
    box(stp, (dx - 0.55, 0.0, z1), (dx + 0.55, 0.13, z1 + 0.7), skip=("-y",))
    box(stp, (dx - 0.55, 0.13, z1), (dx + 0.55, 0.25, z1 + 0.35), skip=("-y",))
    for i, wx in enumerate((-7.9, -6.4)):
        mat = "Window_Lit" if i == 0 else "Window_Dark"
        quad(P.bm(f"Office_Win_{i}", mat), [(wx - 0.55, 1.2, z1 + 0.012), (wx + 0.55, 1.2, z1 + 0.012), (wx + 0.55, 2.1, z1 + 0.012), (wx - 0.55, 2.1, z1 + 0.012)],
             (0, 0, 1), atlas_uv(1) if i == 0 else None)
        box(otr, (wx - 0.6, 1.14, z1), (wx + 0.6, 1.2, z1 + 0.06))
    quad(P.bm("Office_Sign", "Signs"), [(dx - 0.6, 2.42, z1 + 0.012), (dx + 0.6, 2.42, z1 + 0.012), (dx + 0.6, 2.67, z1 + 0.012), (dx - 0.6, 2.67, z1 + 0.012)],
         (0, 0, 1), sign_uv("office"))
    # the bins: two rows of green wheelie bins against the east wall, their wheels to the wall
    for r, (za, zb) in enumerate(BINS_ROWS):
        bb, rb = P.bm(f"Bins_{r + 1}", "Bin_Green"), P.bm(f"Bins_{r + 1}_wheels", "Rubber_Black")
        xw = X - T_
        for zc in bin_centres(za, zb):
            bevel_box(bb, (xw - 0.76, 0.06, zc - 0.29), (xw - 0.04, 1.0, zc + 0.29), r=0.025)
            box(bb, (xw - 0.80, 1.0, zc - 0.30), (xw - 0.02, 1.06, zc + 0.30))
            box(bb, (xw - 0.86, 0.92, zc - 0.2), (xw - 0.78, 0.98, zc + 0.2))           # the handle
            for s_ in (-1, 1):
                cyl(rb, (xw - 0.12, 0.1, zc + s_ * 0.24), (xw - 0.12, 0.1, zc + s_ * 0.30), 0.1, seg=10)
    # the skip: yellow steel, its ends sloping, two lugs each side
    sk = P.bm("Skip", "Skip_Yellow")
    prism(sk, [(-14.1, 0.0), (-11.9, 0.0), (-11.9, 0.05), (-11.6, 1.55), (-14.4, 1.55), (-14.1, 0.05)], -10.3, -6.7)
    for x in (-10.3, -6.7):
        for z in (-13.9, -12.1):
            cyl(P.bm("Skip_Lugs", "Metal_Dark"), (x, 1.2, z), (x + (0.12 if x > -8 else -0.12), 1.2, z), 0.05, seg=6)
    # tyres: two stacks of four
    for k, (tx, tz) in enumerate(((-10.75, -5.6), (-10.75, -6.6))):
        for j in range(4):
            cyl(P.bm("Tyres", "Rubber_Black", smooth=True), (tx, 0.22 * j, tz), (tx, 0.22 * j + 0.21, tz), 0.42, seg=16)
    # the floodlight masts: a pole, two heads aimed into the yard (Lamp_Emit lenses)
    for k, (mx_, mz, aim) in enumerate(((-X + T_ + 0.22, -13.0, 1), (X - T_ - 0.22, -21.0, -1))):
        mp = P.bm(f"Mast_{k + 1}", "Steel_Grey")
        box(mp, (mx_ - 0.15, 0.0, mz - 0.15), (mx_ + 0.15, 0.4, mz + 0.15), skip=("-y",))
        cyl(mp, (mx_, 0.4, mz), (mx_, 6.2, mz), 0.08, 0.06, seg=10)
        hd = P.bm(f"decor_MastHead_{k + 1}", "Metal_Dark")
        ln = P.bm(f"decor_MastLens_{k + 1}", "Lamp_Emit")
        for dz in (-0.3, 0.3):
            box(hd, (mx_ + aim * 0.05 - 0.2, 6.0, mz + dz - 0.22), (mx_ + aim * 0.05 + 0.2, 6.25, mz + dz + 0.22))
            quad(ln, [(mx_ + aim * 0.05 - 0.17, 5.995, mz + dz - 0.19), (mx_ + aim * 0.05 + 0.17, 5.995, mz + dz - 0.19),
                      (mx_ + aim * 0.05 + 0.17, 5.995, mz + dz + 0.19), (mx_ + aim * 0.05 - 0.17, 5.995, mz + dz + 0.19)], (0, -1, 0))
    # the floor's paint: the truck's bay, a walkway to the office, a wash-down drain
    pt = P.bm("decor_Paint", "Paint_Yellow")
    tx, tz = TRUCK_AT[0], TRUCK_AT[2]
    hx, hz = 1.75, 5.25
    yp = 0.004
    for (u0, u1, v0, v1) in ((tx - hx, tx - hx + 0.1, tz - hz, tz + hz), (tx + hx - 0.1, tx + hx, tz - hz, tz + hz), (tx - hx, tx + hx, tz - hz, tz - hz + 0.1)):
        quad(pt, [(u0, yp, v0), (u1, yp, v0), (u1, yp, v1), (u0, yp, v1)], (0, 1, 0))
    for (u0, u1) in ((-10.4, -10.3), (-8.9, -8.8)):
        quad(pt, [(u0, yp, -20.0), (u1, yp, -20.0), (u1, yp, -1.0), (u0, yp, -1.0)], (0, 1, 0))
    dr = P.bm("decor_Drain", "Drain_Iron")
    quad(dr, [(tx - 0.3, yp, -4.6), (tx + 0.3, yp, -4.6), (tx + 0.3, yp, -3.4), (tx - 0.3, yp, -3.4)], (0, 1, 0), [(0, 0), (1, 0), (1, 1), (0, 1)])
    P.done()
    # what moves: the truck (collection Truck, checked with the art; its collider is COL_Truck_parked) and the two gate leaves (collection Leaves)
    build_truck(TRUCK)
    leafW = build_gate_leaf("depot_gate_W", -DY_GATE, DY_GATE - 0.02, LEAVES)
    leafE = build_gate_leaf("depot_gate_E", DY_GATE, -(DY_GATE - 0.02), LEAVES)
    # the layout
    collider("Ground_Yard", (-X, -1.0, -Z), (X, 0.0, 0.0))
    for k, (mn, mx) in runs.items():
        collider(f"Wall_{k}", mn, mx)
    for k, (x0, x1) in piers.items():
        zc0, zc1 = (-DY_PIER / 2, DY_PIER / 2) if k.startswith("gate") else (-T_ - 0.03, 0.03)
        if k.startswith("corner"):
            x0, x1 = x0 - 0.03, x1 + 0.03
        collider(f"Pier_{k}", (x0, 0.0, zc0), (x1, 2.8, zc1))
    for k, (x0, x1) in fences.items():
        collider(f"Fence_{k}", (x0, 0.0, -0.08), (x1, DY_FENCE_H, 0.09))
    x0, x1, z0, z1 = OFFICE
    collider("Office", (x0 - 0.04, 0.0, z0 - 0.04), (x1 + 0.04, 2.92, z1 + 0.06))     # the cabin with its roof trim, sills and door head
    collider("Office_Steps", (-9.6 - 0.55, 0.0, z1), (-9.6 + 0.55, 0.25, z1 + 0.7))
    for r, (za, zb) in enumerate(BINS_ROWS):
        cs = bin_centres(za, zb)
        collider(f"Bins_{r + 1}", (X - T_ - 0.86, 0.0, min(cs) - 0.30), (X - T_, 1.06, max(cs) + 0.30))
    collider("Skip", (-10.32, 0.0, -14.4), (-6.68, 1.55, -11.6))
    collider("Tyres", (-11.2, 0.0, -7.05), (-10.3, 0.87, -5.15))
    for k, (mx_, mz) in enumerate(((-X + T_ + 0.22, -13.0), (X - T_ - 0.22, -21.0))):
        collider(f"Mast_{k + 1}", (mx_ - 0.15, 0.0, mz - 0.15), (mx_ + 0.15, 6.2, mz + 0.15))
    for nm, (mn, mx) in TRUCK_COLS.items():                    # the parked truck: the body and cab, and the hopper behind it (the page moves or drops them)
        collider(nm, tuple(mn[i] + TRUCK_AT[i] for i in range(3)), tuple(mx[i] + TRUCK_AT[i] for i in range(3)))
    for nm, hx, yaw, sw in (("depot_gate_W", -DY_GATE, 0.0, 90.0), ("depot_gate_E", DY_GATE, 180.0, -90.0)):
        empty(f"DoorLeaf_{nm}", (hx, 0.0, 0.0), props={"width": DY_GATE - 0.02, "height": DY_FENCE_H, "closed_yaw_deg": yaw, "swing_deg": sw,
                                                        "state": "closed", "kind": "vehicle gate", "leaf": f"Leaf_{nm}"}, kind="ARROWS")
    empty("Marker_Gate", (0.0, 0.0, 1.0), props={"kind": "Entrance"})
    empty("Spot_clock_1", (-9.6, 0.0, OFFICE[3] + 1.3), face=(0.0, -1.0), props={"what": "clock in and out (the office door)"})
    empty("Spot_bins_1", (X - T_ - 1.5, 0.0, -10.0), face=(1.0, 0.0), props={"what": "the bin store"})


# ================================================================ build, layout, check
TRUCK = LEAVES = STANDINS = BAKEC = None
LAYOUT_PREFIX = ("COL_", "DoorLeaf_", "Link_", "Arrive_", "Spot_", "Zone_", "Marker_")
KEEP_OBJ_PROPS = LAYOUT_PREFIX + ("trash_truck", "Truck_", "Leaf_", "slot_")


def setup_world():
    sc = bpy.context.scene
    w = bpy.data.worlds.get("City") or bpy.data.worlds.new("City")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    bg.inputs["Color"].default_value = (0.50, 0.62, 0.85, 1)       # the street's day sky (tools/blender/build_street.py setup_world)
    bg.inputs["Strength"].default_value = 0.9
    w.light_settings.distance = 2.0


def add_sun():
    if "Sun" in bpy.data.objects:
        return
    d = bpy.data.lights.new("Sun", "SUN")
    d.energy, d.color, d.angle = 4.0, (1.0, 0.93, 0.82), math.radians(0.8)       # the street's sun, from the south-west, 38 degrees up
    ob = bpy.data.objects.new("Sun", d)
    ob.rotation_euler = B((-0.55, -0.62, 0.55)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(ob)


def build_standins():
    """For the stills only (never baked or exported): the street round the bus stop; two more street segments north and south of the segment."""
    if PIECE == "bus_stop":
        street_materials()
        P = Parts(STANDINS)
        ox, oz = -7.0, -5.0                                     # the kit at (7, 0, 5) on the street: street (x, z) is kit (x - 7, z - 5)
        z0, z1 = -14.0, 9.0
        quad(P.bm("sd_road", "Road_Asphalt"), [(-12.0 + 0, ROAD_Y, z0), (ox + ROAD_X, ROAD_Y, z0), (ox + ROAD_X, ROAD_Y, z1), (-12.0, ROAD_Y, z1)], (0, 1, 0))
        kb = P.bm("sd_kerb", "Kerb_Stone")
        quad(kb, [(ox + ROAD_X, ROAD_Y, z0), (ox + ROAD_X, WALK_Y, z0), (ox + ROAD_X, WALK_Y, z1), (ox + ROAD_X, ROAD_Y, z1)], (-1, 0, 0))
        quad(kb, [(ox + ROAD_X, WALK_Y, z0), (ox + ROAD_X + KERB_W, WALK_Y, z0), (ox + ROAD_X + KERB_W, WALK_Y, z1), (ox + ROAD_X, WALK_Y, z1)], (0, 1, 0))
        quad(P.bm("sd_walk", "Sidewalk_Slab"), [(ox + ROAD_X + KERB_W, WALK_Y, z0), (ox + FRONT, WALK_Y, z0), (ox + FRONT, WALK_Y, z1),
                                                (ox + ROAD_X + KERB_W, WALK_Y, z1)], (0, 1, 0))
        quad(P.bm("sd_yard", "Backlot_Ground"), [(ox + FRONT, 0.0, z0), (6.0, 0.0, z0), (6.0, 0.0, z1), (ox + FRONT, 0.0, z1)], (0, 1, 0))
        P.done()
    elif PIECE == "street_segment":
        for k, dz in (("north", -SEG_L), ("south", SEG_L)):
            inst = bpy.data.objects.new(f"standin_segment_{k}", None)
            inst.instance_type = "COLLECTION"
            inst.instance_collection = ART
            inst.location = B((0.0, 0.0, dz))
            STANDINS.objects.link(inst)
    elif PIECE == "depot_yard":
        material("Backlot_Ground", diff="concrete.jpg", tint=(0.42, 0.42, 0.41), rough=0.95, tile=5.0)
        P = Parts(STANDINS)
        quad(P.bm("sd_lane", "Backlot_Ground"), [(-16.0, -0.002, 0.0), (16.0, -0.002, 0.0), (16.0, -0.002, 26.0), (-16.0, -0.002, 26.0)], (0, 1, 0))
        P.done()


def build_all():
    global ART, LAYOUT, TRUCK, LEAVES, STANDINS, BAKEC
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for d in (IMG_CACHE, MATS, TILES, SLOT_COLL):
        d.clear()
    sc = bpy.context.scene
    ART, LAYOUT, TRUCK, LEAVES, STANDINS = (bpy.data.collections.new(n) for n in ("Art", "Layout", "Truck", "Leaves", "Standins"))
    for c in (ART, LAYOUT, TRUCK, LEAVES, STANDINS):
        sc.collection.children.link(c)
    {"street_segment": build_street_segment, "bus_stop": build_bus_stop, "depot_yard": build_depot_yard}[PIECE]()
    build_standins()
    setup_world()
    add_sun()
    LAYOUT.hide_render = True
    bpy.context.view_layer.update()
    tris = sum(len(p.vertices) - 2 for c in (ART, TRUCK, LEAVES) for o in c.all_objects if o.type == "MESH" for p in o.data.polygons)
    print(f"ART {PIECE}: {len(ART.all_objects)} art objects, {len(TRUCK.objects)} truck objects, {len(LEAVES.objects)} leaves, about {tris} triangles")


def open_collections():
    global ART, LAYOUT, TRUCK, LEAVES, STANDINS
    ART, LAYOUT, TRUCK, LEAVES, STANDINS = (bpy.data.collections.get(n) for n in ("Art", "Layout", "Truck", "Leaves", "Standins"))
    MATS.clear()
    for m in bpy.data.materials:
        MATS[m.name] = m


def stage_layout(path=None):
    import export_scene
    path = path or ROOT / f"world/kit/{PIECE}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return export_scene.write(scene_id(), path)


def stage_check():
    import check_layout
    world = json.loads((ROOT / f"world/kit/{PIECE}.json").read_text())
    bpy.context.view_layer.update()
    parts = check_layout.blender_parts("Art") + (check_layout.blender_parts("Truck") if TRUCK and TRUCK.objects else [])
    consts = {"links": {l["door"]: {"arrive": l["arrive"], "at": [l["at"][0], l["at"][2]]} for l in world["links"]}}
    print(f"layout check: scene {scene_id()}, {len(parts)} visible meshes, {len(world['colliders'])} colliders"
          + (" (the gate leaves skipped: the page's doors collide them)" if LEAVES and LEAVES.objects else ""))
    bad = check_layout.report(check_layout.check(parts, world, consts))
    print(f"CHECK_LAYOUT {scene_id()} exit", 1 if bad else 0)
    return bad


# ---------------------------------------------------------------- bake: ambient occlusion
GROUND = ["Road_Asphalt", "Kerb_Stone", "Sidewalk_Slab", "Backlot_Ground", "Drain_Iron", "Yard_Concrete"]
SMALL = ["Door_Leaf", "Boarding", "Awning_Red", "Awning_Green", "Trim_Stone"]
NOT_BAKED = ("Window_Lit", "Lamp_Emit", "Shelter_Glass", "Window_Dark", "Shop_Glass", "Frame_Dark", "Metal_Dark", "Fascia_Paint", "Road_Line", "Road_Yellow",
             "Paint_Yellow")
PLAN = {     # per piece: the AO maps: (page size, AO distance m, which materials)
    "street_segment": [(2048, 3.0, "ground"), (2048, 3.0, "buildings"), (1024, 1.0, "small")],
    "bus_stop": [(1024, 1.0, "all")],
    "depot_yard": [(1024, 2.0, "ground"), (2048, 1.2, "standing")],
}
AO_INTENSITY = 1.0


def groups(exp):
    mats = sorted({o.data.materials[0].name for o in exp})
    baked = [m for m in mats if m not in NOT_BAKED]
    out = []
    for S, dist, kind in PLAN[PIECE]:
        if kind == "ground":
            sel = [m for m in baked if m in GROUND]
        elif kind == "buildings":
            sel = [m for m in baked if m not in GROUND and m not in SMALL]
        elif kind == "small":
            sel = [m for m in baked if m in SMALL]
        elif kind == "standing":
            sel = [m for m in baked if m not in GROUND]
        else:
            sel = baked
        out.append((S, dist, sel))
    return out


def cull_hidden(bm):
    """Drop the faces never seen: the undersides of boxes standing on the ground."""
    bm.normal_update()
    bad = [f for f in bm.faces if f.normal.z < -0.9 and f.calc_center_median().z < 0.005]
    bmesh.ops.delete(bm, geom=bad, context="FACES")


def make_export_objects():
    """The art merged by material, per node group: the main art by material name, a slot's building as `slot_<side>_<material>` under its own empty."""
    if "Export" in bpy.data.collections:
        for o in list(bpy.data.collections["Export"].objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(bpy.data.collections["Export"])
    exp = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(exp)
    by_key = {}
    bpy.context.view_layer.update()
    arts = [o for o in bpy.data.objects if o.type == "MESH" and any(c.name == "Art" or c.name.startswith("Slot_") for c in o.users_collection)]
    print(f"EXPORT objects: {len(arts)} art meshes")
    for ob in arts:
        assert len(ob.data.materials) == 1, ob.name
        grp = next((c.name[len("Slot_"):] for c in ob.users_collection if c.name.startswith("Slot_")), "")
        mname = ob.data.materials[0].name
        bm = by_key.setdefault((grp, mname), bmesh.new())
        tmp = bmesh.new()
        tmp.from_mesh(ob.data)
        tmp.transform(ob.matrix_world)
        cull_hidden(tmp)
        me = bpy.data.meshes.new("tmp")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    roots = {}
    out = []
    for (grp, mname), bm in sorted(by_key.items()):
        nm = f"{grp}_{mname}" if grp else mname
        me = bpy.data.meshes.new(nm)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(bpy.data.materials[mname])
        ob = bpy.data.objects.new(nm, me)
        exp.objects.link(ob)
        if grp:
            if grp not in roots:
                r = bpy.data.objects.new(grp, None)
                b = next(b for b in SEG_BUILDINGS if b["id"] == grp)
                mn, mx = seg_box(b)
                for k, v in {"slot": grp, "side": b["side"], "front_x": -FRONT if b["side"] == "w" else FRONT, "z0": mn[2], "z1": mx[2], "depth_m": b["depth"],
                             "height_m": b["h"], "door_z": b["door_z"], "door_w": DOOR_W, "door_h": DOOR_H}.items():
                    r[k] = v
                exp.objects.link(r)
                roots[grp] = r
            ob.parent = roots[grp]
        out.append(ob)
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
    mats = sorted({o.data.materials[0] for o in objs}, key=lambda m: m.name)
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
    png.filepath_raw = str(work_dir() / f"kit_{PIECE}_{n}.png")
    png.file_format = "PNG"
    png.save()
    bpy.data.images.remove(png)
    for m in mats:
        m["aomap"] = f"world/lightmaps/kit_{PIECE}_{n}.webp"
        m["aomap_intensity"] = AO_INTENSITY
    rep = {"size": S, "p1_p10_p50_p90": [round(float(v), 3) for v in pc], "samples": SAMPLES, "distance_m": dist,
           "device": bpy.context.scene.cycles.device, "seconds": round(time.time() - t0), "materials": [m.name for m in mats]}
    print(f"  AO map {n} baked", rep)
    return rep


def bake_occluder():
    """The bus stop stands on its host's ground: a plain ground plane for the bake only (never exported), so the shelter's feet are occluded."""
    if PIECE != "bus_stop":
        return None
    me = bpy.data.meshes.new("bake_ground")
    bm = bmesh.new()
    quad(bm, [(-8, 0.0, -6), (8, 0.0, -6), (8, 0.0, 6), (-8, 0.0, 6)], (0, 1, 0))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(bpy.data.materials.get("Steel_Grey"))
    ob = bpy.data.objects.new("bake_ground", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def stage_bake():
    exp = make_export_objects()
    for c in ("Art", "Layout", "Truck", "Leaves", "Standins"):
        cc = bpy.data.collections.get(c)
        if cc:
            cc.hide_render = True
            cc.hide_viewport = True
    occ = bake_occluder()
    setup_world()
    setup_cycles(SAMPLES, bake=True)
    report = {}
    meshes = [o for o in exp if o.type == "MESH"]
    for n, (S, dist, mats) in enumerate(groups(meshes)):
        objs = [o for o in meshes if o.data.materials[0].name in mats]
        if not objs:
            continue
        print(f"AO map {n}: {mats}")
        dens = lightmap_uv(objs, S)
        report[n] = bake_ao(n, objs, S, dist)
        report[n]["px_per_m"] = round(dens, 1)
    if occ:
        bpy.data.objects.remove(occ)
    (work_dir() / "bake.json").write_text(json.dumps(report, indent=1))
    for c in ("Art", "Truck", "Leaves", "Standins"):
        cc = bpy.data.collections.get(c)
        if cc:
            cc.hide_render = c == "Standins" and False
            cc.hide_viewport = False
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
                    if kind == "objects" and st is idb and idb.name.startswith(KEEP_OBJ_PROPS):
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
    ART.hide_viewport = True
    if STANDINS:
        STANDINS.hide_viewport = True
    movers = []
    for c in (TRUCK, LEAVES):
        if c:
            c.hide_viewport = False
            movers += list(c.objects)
    bpy.ops.object.select_all(action="DESELECT")
    for o in list(exp.objects) + movers:
        o.hide_set(False)
        o.hide_render = False
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(o for o in exp.objects if o.type == "MESH")
    raw = work_dir() / f"kit_{PIECE}_raw.glb"
    scrub_private()
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False, export_animations=False)
    print("EXPORTED", raw.name, raw.stat().st_size)
    ART.hide_viewport = False
    if STANDINS:
        STANDINS.hide_viewport = False
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
    cam.clip_start, cam.clip_end = 0.05, 600
    ob = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = B(loc)
    ob.rotation_euler = (B(target) - B(loc)).to_track_quat("-Z", "Y").to_euler() if target is not None else (0, 0, 0)
    return ob


def strip_jpeg_meta(path):
    """Drop the JPEG's comment (FE) and APP1 (E1) segments: Blender writes its render metadata there even with every stamp off."""
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
    """(eye, target, vertical fov, gates open) per still; the plan is added in stage_render."""
    if PIECE == "street_segment":
        return {"1_street": ((2.8, 1.55, -1.0), (-0.8, 2.6, -40.0), 62.0, False),
                "2_wide": ((26.0, 20.0, 10.0), (0.0, 0.0, -21.0), 58.0, False),
                "3_slot": ((-3.2, 1.7, -26.6), (-8.0, 2.2, -31.6), 58.0, False),
                "5_slot_E": ((3.4, 1.7, -4.4), (8.0, 2.2, -9.6), 58.0, False)}
    if PIECE == "bus_stop":
        return {"1_front": ((-0.4, 1.55, 4.6), (0.0, 1.2, -0.2), 55.0, False),
                "2_side": ((-5.2, 1.65, 2.4), (-0.3, 1.3, -0.1), 55.0, False),
                "3_sign": ((-0.5, 1.6, 2.5), (-1.75, 2.05, 0.35), 52.0, False)}
    return {"1_gate": ((0.0, 1.6, 9.0), (0.5, 1.3, -14.0), 60.0, True),
            "2_wide": ((16.0, 15.0, 9.0), (0.0, 0.0, -12.0), 58.0, True),
            "3_truck": ((-1.6, 1.7, -21.5), (3.4, 1.6, -15.5), 58.0, True),
            "5_cab": ((0.2, 1.6, -4.2), (3.5, 1.8, -9.0), 58.0, True)}


def set_gates(open_):
    for nm, sgn in (("Leaf_depot_gate_W", 1), ("Leaf_depot_gate_E", -1)):     # open: both swung 80 degrees into the yard (game -z, Blender +y)
        o = bpy.data.objects.get(nm)
        if o:
            o.rotation_euler = (0, 0, math.radians(80.0 * sgn) if open_ else 0.0)


def stage_render():
    sc = bpy.context.scene
    STILLS.mkdir(parents=True, exist_ok=True)
    scrub_private()
    for c in ("Export", "Layout"):
        if c in bpy.data.collections:
            bpy.data.collections[c].hide_render = True
            bpy.data.collections[c].hide_viewport = True
    for c in ("Art", "Truck", "Leaves", "Standins"):
        if c in bpy.data.collections:
            bpy.data.collections[c].hide_render = False
            bpy.data.collections[c].hide_viewport = False
    setup_world()
    add_sun()
    setup_cycles(arg("--render-samples", 128, int))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = arg("--noise", 0.03, float)
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    which = arg("--only", "all")
    for name in ("Lamp_Emit", "Window_Lit"):                     # the stills are by day: the page's clock has the lamps and lit windows off (not saved)
        m = bpy.data.materials.get(name)
        if m:
            next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Emission Strength"].default_value = 0.0
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    todo = []
    for k, (p, t, f, gates) in shots().items():
        todo.append((k, look_cam(k, p, t, f), (1920, 1080), gates))
    ext = {"street_segment": ((-YARD_X, YARD_X), (-SEG_L - 2, 2.0)), "bus_stop": ((-4.0, 2.5), (-2.0, 2.0)), "depot_yard": ((-13.0, 13.0), (-25.0, 2.0))}[PIECE]
    (xa, xb), (za, zb) = ext
    w_, h_ = xb - xa + 1.0, zb - za + 1.0
    plan = look_cam("4_plan", ((xa + xb) / 2, 80.0, (za + zb) / 2), None, ortho=max(w_, h_))
    plan.data.sensor_fit = "AUTO"                                # the scale spans the render's longer side
    plan.rotation_euler = (0, 0, 0)                              # looking straight down, north (-z) up
    pw, ph = (1600, int(1600 * h_ / w_)) if w_ >= h_ else (int(1600 * w_ / h_), 1600)
    todo.append(("4_plan", plan, (pw, ph), False))
    for key, cam, (w, h), gates in todo:
        if which not in ("all", key):
            continue
        set_gates(gates)
        sc.camera = cam
        sc.view_settings.exposure = 0.0
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, arg("--scale", 100, int)
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        to_docs = key[:2] in ("1_", "2_", "3_")
        path = STILLS / f"{key}.jpg" if to_docs else work_dir() / f"{key}.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 420_000 and q > 40 and to_docs:
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        strip_jpeg_meta(path)
        print("STILL", PIECE, key, path.name, path.stat().st_size, "q", q)
    set_gates(False)
    stage_layout(work_dir() / f"kit_{PIECE}_reexport.json")       # the gate: the saved .blend still writes the same layout


# ================================================================ main
if __name__ == "__main__":
    ST = set(STAGE.split(","))
    import traceback
    failed, summary = [], []
    for pid in piece_list():
        try:
            setup(pid)
            print(f"=== {pid}: stages {sorted(ST)}")
            if "art" in ST:
                build_all()
                save_blend()
            else:
                bpy.ops.wm.open_mainfile(filepath=str(BLEND))
                open_collections()
            if ST & {"layout", "art"}:
                stage_layout()
            if ST & {"check", "art"}:
                summary.append((pid, "check", stage_check()))
            if "bake" in ST:
                stage_bake()
            if "export" in ST:
                stage_export()
            if "render" in ST:
                stage_render()
        except Exception:
            traceback.print_exc()
            failed.append(pid)
    for s in summary:
        print("SUMMARY", *s)
    print("CITY_KITS ALL DONE", "failed:", failed or "none")
    sys.exit(1 if failed else 0)
