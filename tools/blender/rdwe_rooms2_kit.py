"""The shared dressing kit for Right Door, Wrong Exit's teal wing and institution rooms (Phase C rooms 16 to 34), used by
tools/blender/build_rdwe_rooms2.py. It is the hotel lobby's method (tools/blender/build_lobby.py on claude/blender-hotel-lobby) made generic:

- the layout is the greybox model's (tools/blender/build_rdwe_greybox.py, imported: no coordinate is typed in twice). Every COL_ box, door leaf,
  Link_/Arrive_ and Spot_ is written into the .blend under the greybox's names, so tools/blender/export_scene.py writes the same world/<scene>.json
  as `build_rdwe_greybox.py --preview`;
- the art is built round it: one Art object per collider (so tools/blender/check_layout.py can see each piece over its box), merged by material
  into the Export collection for the bake and the GLB, faces nobody can see culled;
- door leaves are built from their `look` (form, finish, handle), so no two are alike;
- light sets: each room names its sets (one, two or three). A set is a bake of every baked material: `lightmap` for the first set,
  `lightmap_<set>` for the others, each with its `_intensity`. Objects the page moves are their own nodes and are not baked;
- the bake keeps the raw irradiance (work/<scene>/raw_<n>.npy); tools/blender/rdwe_rooms2_pack.py grades it to the lightmap WebPs and writes
  the intensities into the GLB, in plain Python, so the brightness can be tuned without Blender.

Game coordinates throughout (metres, y up, north = -z); Blender (x, y, z) = game (x, -z, y).
"""
import json
import math
import os
import sys
import time
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/blender"))
import build_rdwe_greybox as G          # noqa: E402  the layout model (pure Python)

TEX = ROOT / "blender/textures/rdwe_rooms2"
MARGIN_PX = 6
LAMP_EMIT = 6.0
EYE = 1.55
SEEN_UP = 2.0           # an up-facing face higher than this is never seen from 1.55 m
SEEN_DOWN = 1.4         # nor a down-facing face lower than this


def B(p):
    return Vector((p[0], -p[2], p[1]))


class Ctx:
    pass


K = Ctx()


def reset(sid, spec):
    """Start a scene: an empty file, the greybox model, the collections."""
    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    K.sid, K.spec = sid, spec
    K.GB = G.build(sid)
    K.BOX = {b["name"]: b for b in K.GB.boxes}
    fl = K.BOX["Room_Floor"]
    K.X0, K.X1 = fl["min"][0] + G.T, fl["max"][0] - G.T
    K.Z0, K.Z1 = fl["min"][2] + G.T, fl["max"][2] - G.T
    K.H = K.BOX["Room_Ceiling"]["min"][1]
    K.MATS, K.TILES, K.GROUP, K.IMG, K.GEN = {}, {}, {}, {}, {}
    K.LIGHTS = []
    K.EMIT_SETS = {}          # material -> {set: strength} (default: its own strength in every set)
    K.MOVING = set()          # object names the page moves: their own nodes, not baked
    K.SEPARATE = set()        # object names kept as their own nodes, baked
    K.MIRROR = set()          # object names merged into the group spec["groups"] names (the mirror room's reflection), baked
    K.MATDEF = dict(MATLIB)
    K.MATDEF.update(spec.get("mats", {}))
    K.SETS = spec.get("sets", ["main"])
    sc = bpy.context.scene
    K.ART, K.DOORS, K.LAYOUT, K.STAND = (bpy.data.collections.new(n) for n in ("Art", "Doors", "Layout", "Standins"))
    for c in (K.ART, K.DOORS, K.LAYOUT, K.STAND):
        sc.collection.children.link(c)
    K.HOLES = door_holes()
    K.SOLIDS = [b for b in K.GB.boxes if (b["col"] and not b["name"].startswith("Beyond_")) or ("ceiling" in b["tags"] and b.get("art"))]


def work():
    d = ROOT / "work" / K.sid
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- materials
# name: dict(color, rough, metal, diff (a CC0 file in blender/textures/rdwe_rooms2), gen (a generated picture), tint, emit (colour, strength),
# alpha, tile (metres a repeat), two_sided, group: "struct" (the shell's page), "props" (the props' page) or None (not baked: lamps, screens,
# glass, the black past a door)
MATLIB = {
    "Void_Black": dict(color=(0.0, 0.0, 0.0), rough=1.0, group=None),
    "Lamp_Emit": dict(color=(1.0, 0.92, 0.78), rough=0.5, emit=((1.0, 0.80, 0.55), LAMP_EMIT), group=None),
    "Lamp_Off": dict(color=(0.80, 0.80, 0.76), rough=0.4, group="props"),
    "Brass": dict(color=(0.62, 0.46, 0.20), rough=0.35, metal=0.9),
    "Chrome": dict(color=(0.75, 0.76, 0.78), rough=0.2, metal=1.0),
    "Steel": dict(color=(0.55, 0.56, 0.58), rough=0.45, metal=0.8, diff="Metal048A_color_512.jpg", tint=(0.9, 0.9, 0.92), tile=1.0),
    "Iron": dict(color=(0.08, 0.08, 0.085), rough=0.6, metal=0.6),
    "Glass_Door": dict(color=(0.55, 0.64, 0.66), rough=0.05, group="props"),
    "Glass_Clear": dict(color=(0.80, 0.88, 0.88), rough=0.05, alpha=0.18, group=None),
    "Mirror": dict(color=(0.70, 0.74, 0.78), rough=0.08, metal=0.6),
    "Rubber": dict(color=(0.05, 0.05, 0.05), rough=0.9),
    "Paint_Palette": dict(gen="palette", rough=0.7, tile=1.0),
    "Plaster_White": dict(diff="plastered_wall_04_diff_1k.jpg", tint=(0.92, 0.91, 0.88), rough=0.95, tile=2.5, group="struct"),
    "Wood_Dark": dict(diff="dark_wood_diff_1k.jpg", tint=(0.95, 0.9, 0.85), rough=0.5, tile=1.2),
    "Wood_Oak": dict(diff="old_wood_floor_diff_1k.jpg", tint=(1.0, 0.92, 0.80), rough=0.5, tile=1.4),
    "Plywood": dict(diff="plywood_diff_1k.jpg", rough=0.7, tile=1.2),
    "Linen": dict(diff="rough_linen_diff_512.jpg", tint=(0.85, 0.82, 0.76), rough=1.0, tile=0.6),
    "Marble": dict(diff="marble_01_diff_1k.jpg", tint=(0.95, 0.93, 0.90), rough=0.25, tile=1.4),
}
for _fin, _c in {"oak": None, "birch": None, "teal paint": (0.05, 0.42, 0.40), "mint paint": (0.50, 0.85, 0.68), "pink laminate": (0.95, 0.45, 0.62),
                 "brushed steel": None, "cream gloss": (0.86, 0.80, 0.64), "cherry red": (0.62, 0.05, 0.06), "bottle green": (0.04, 0.24, 0.10),
                 "lilac": (0.66, 0.54, 0.86), "black lacquer": (0.035, 0.035, 0.04), "orange vinyl": (0.95, 0.40, 0.08), "sky blue": (0.40, 0.66, 0.92),
                 "mustard": (0.82, 0.62, 0.10), "plum": (0.36, 0.10, 0.26)}.items():
    _n = "Door_" + _fin.title().replace(" ", "_")
    if _fin == "oak":
        MATLIB[_n] = dict(diff="old_wood_floor_diff_1k.jpg", tint=(1.0, 0.86, 0.66), rough=0.45, tile=1.0)
    elif _fin == "birch":
        MATLIB[_n] = dict(diff="plywood_diff_1k.jpg", tint=(1.0, 0.96, 0.88), rough=0.45, tile=1.0)
    elif _fin == "brushed steel":
        MATLIB[_n] = dict(diff="Metal048A_color_512.jpg", tint=(0.86, 0.87, 0.9), rough=0.35, metal=0.7, tile=0.8)
    else:
        MATLIB[_n] = dict(color=_c, rough=0.25 if "gloss" in _fin or "lacquer" in _fin else 0.5)


def finish_mat(fin):
    return "Door_" + fin.title().replace(" ", "_")


def image(fn, srgb=True):
    key = (fn, srgb)
    if key not in K.IMG:
        im = bpy.data.images.load(str(TEX / fn))
        im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
        K.IMG[key] = im
    return K.IMG[key]


def mat(name):
    """The material `name`, made on first use from its definition (MATLIB, or the room's own `mats`)."""
    if name in K.MATS:
        return K.MATS[name]
    d = K.MATDEF[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.name = "Principled BSDF"
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*d.get("color", (0.6, 0.6, 0.6)), 1)
    bsdf.inputs["Roughness"].default_value = d.get("rough", 0.7)
    bsdf.inputs["Metallic"].default_value = d.get("metal", 0.0)
    img = None
    if d.get("diff"):
        img = image(d["diff"])
    elif d.get("gen"):
        img = gen_image(d["gen"])
    if img is not None:
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "UVMap"
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = img
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        src = n.outputs["Color"]
        if d.get("tint"):
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs[0].default_value = 1.0
            nt.links.new(n.outputs["Color"], mix.inputs[6])
            mix.inputs[7].default_value = (*d["tint"], 1)
            src = mix.outputs[2]
        nt.links.new(src, bsdf.inputs["Base Color"])
        if d.get("emit_tex"):
            nt.links.new(src, bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = d["emit_tex"]
    if d.get("emit"):
        bsdf.inputs["Emission Color"].default_value = (*d["emit"][0], 1)
        bsdf.inputs["Emission Strength"].default_value = d["emit"][1]
    if d.get("alpha") is not None:
        bsdf.inputs["Alpha"].default_value = d["alpha"]
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    m.use_backface_culling = not d.get("two_sided", False)
    K.TILES[name] = d.get("tile", 1.0)
    K.GROUP[name] = d.get("group", "props") if not (d.get("emit") or d.get("emit_tex")) else None
    if "group" in d:
        K.GROUP[name] = d["group"]
    K.MATS[name] = m
    return m


# ---------------------------------------------------------------- generated pictures (numpy, own work, fixed seeds)
GLYPHS = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"], "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"], "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"], "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"], "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"], "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"], "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"], "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"], "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"], "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"], "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"], "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"], "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"], "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    " ": ["00000"] * 7, "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"], ".": ["00000"] * 6 + ["00100"],
    "&": ["01100", "10010", "10100", "01000", "10101", "10010", "01101"], ">": ["01000", "00100", "00010", "00001", "00010", "00100", "01000"],
    ":": ["00000", "00100", "00000", "00000", "00000", "00100", "00000"], "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    "0": ["01110", "10011", "10101", "10101", "11001", "10001", "01110"], "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00110", "01000", "10000", "11111"], "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["10010", "10010", "10010", "11111", "00010", "00010", "00010"], "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["01110", "10000", "11110", "10001", "10001", "10001", "01110"], "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"], "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
}
GLYPHS.update({",": ["00000"] * 5 + ["00100", "01000"], "'": ["00100", "00100", "01000", "00000", "00000", "00000", "00000"],
               "?": ["01110", "10001", "00001", "00110", "00100", "00000", "00100"], "!": ["00100"] * 5 + ["00000", "00100"],
               "#": ["01010", "11111", "01010", "01010", "11111", "01010", "00000"], "<": ["00010", "00100", "01000", "10000", "01000", "00100", "00010"],
               "(": ["00010", "00100", "01000", "01000", "01000", "00100", "00010"], ")": ["01000", "00100", "00010", "00010", "00010", "00100", "01000"]})


def blur(a, r, passes=3):
    n = 2 * r + 1
    for ax in (0, 1):
        for _ in range(passes):
            pad = [(0, 0)] * a.ndim
            pad[ax] = (r + 1, r)
            c = np.cumsum(np.pad(a, pad, mode="edge"), axis=ax)
            Ln = c.shape[ax]
            a = (np.take(c, range(n, Ln), axis=ax) - np.take(c, range(0, Ln - n), axis=ax)) / n
    return a


def rs(a, h, w):
    ys, xs = np.linspace(0, a.shape[0] - 1, h), np.linspace(0, a.shape[1] - 1, w)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, a.shape[0] - 1), np.minimum(x0 + 1, a.shape[1] - 1)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    return a[y0][:, x0] * (1 - fy) * (1 - fx) + a[y0][:, x1] * (1 - fy) * fx + a[y1][:, x0] * fy * (1 - fx) + a[y1][:, x1] * fy * fx


def vnoise(h, w, rng, octaves=5, base=4, wrap=True):
    out, amp, tot = np.zeros((h, w)), 1.0, 0.0
    for k in range(octaves):
        n = base * 2 ** k
        g = rng.random((n + 1, n + 1))
        if wrap:
            g[-1, :] = g[0, :]
            g[:, -1] = g[:, 0]
        out += amp * rs(g, h, w)
        tot += amp
        amp *= 0.5
    return out / tot


def text_mask(text, h, w, fill=0.62, maxw=0.9):
    adv = 6
    text = text.upper()
    units = max(1, len(text) * adv - 1)
    s = max(1, int(min(w * maxw / units, h * fill / 7)))
    m = np.zeros((h, w), np.float32)
    x = (w - units * s) // 2
    y0 = (h - 7 * s) // 2
    for ch in text:
        g = GLYPHS.get(ch, GLYPHS[" "])
        for r, row in enumerate(g):
            for c, v in enumerate(row):
                if v == "1":
                    m[y0 + r * s:y0 + (r + 1) * s, x + c * s:x + (c + 1) * s] = 1
        x += adv * s
    k = max(1, s // 4)
    return np.clip((blur(m, k, 2) - 0.5) * 4 + 0.5, 0, 1)


def text_lines(lines, h, w, bg, fg, line_h=None, left=False, rng=None):
    img = np.zeros((h, w, 3), np.float32)
    img[:] = bg
    lh = line_h or h // max(1, len(lines))
    for i, t in enumerate(lines):
        if not t:
            continue
        m = text_mask(t, lh, w, fill=0.6, maxw=0.94 if not left else min(0.94, len(t) / 40))
        if left:
            nz = np.nonzero(m.max(axis=0) > 0.1)[0]
            if len(nz):
                m = np.roll(m, 16 - nz[0], axis=1)
        y = i * lh
        img[y:y + lh] = img[y:y + lh] * (1 - m[..., None]) + np.array(fg) * m[..., None]
    if rng is not None:
        img *= 0.9 + 0.14 * vnoise(h, w, rng, 4, 6)[..., None]
    return img


PAL = {
    "book_red": (0.45, 0.08, 0.07), "book_green": (0.10, 0.25, 0.14), "book_blue": (0.10, 0.15, 0.33), "book_tan": (0.66, 0.55, 0.38),
    "book_black": (0.07, 0.07, 0.07), "book_ochre": (0.62, 0.42, 0.10), "book_cream": (0.86, 0.82, 0.70), "book_plum": (0.30, 0.10, 0.22),
    "paper": (0.88, 0.86, 0.80), "white": (0.86, 0.86, 0.84), "black": (0.03, 0.03, 0.035), "grey": (0.35, 0.35, 0.36),
    "red": (0.70, 0.06, 0.05), "orange": (0.90, 0.38, 0.06), "yellow": (0.88, 0.72, 0.12), "green": (0.12, 0.45, 0.16),
    "teal": (0.04, 0.40, 0.38), "blue": (0.10, 0.25, 0.62), "pink": (0.92, 0.42, 0.60), "violet": (0.40, 0.16, 0.70),
    "leaf": (0.10, 0.28, 0.08), "soil": (0.10, 0.07, 0.05), "pot": (0.55, 0.28, 0.16), "wood": (0.40, 0.25, 0.13),
    "cream": (0.86, 0.80, 0.64), "brass": (0.66, 0.50, 0.22), "steel": (0.58, 0.60, 0.62), "plastic_blue": (0.20, 0.45, 0.70),
    "towel": (0.92, 0.90, 0.84), "towel_blue": (0.40, 0.62, 0.80), "skin": (0.80, 0.62, 0.50), "gold": (0.78, 0.58, 0.20),
    "mint": (0.50, 0.85, 0.68), "peach": (0.95, 0.62, 0.48), "magenta": (0.80, 0.08, 0.55), "lilac": (0.66, 0.54, 0.86),
    "navy": (0.05, 0.07, 0.25), "maroon": (0.35, 0.05, 0.08), "olive": (0.35, 0.36, 0.12), "beige": (0.72, 0.64, 0.50),
    "chair_grey": (0.22, 0.23, 0.25), "screen_off": (0.025, 0.03, 0.035), "fabric_red": (0.55, 0.10, 0.10), "fabric_teal": (0.10, 0.45, 0.48),
    "wax": (0.60, 0.12, 0.10), "candle": (0.92, 0.88, 0.76), "string": (0.75, 0.05, 0.05), "felt_green": (0.08, 0.30, 0.14),
    "rust": (0.45, 0.20, 0.08), "concrete": (0.55, 0.54, 0.52), "denim": (0.22, 0.30, 0.48), "lemon": (0.95, 0.88, 0.30),
    "acid": (0.65, 0.95, 0.10), "sky": (0.45, 0.68, 0.92), "chrome": (0.80, 0.81, 0.83), "ivory": (0.92, 0.89, 0.80),
}
PAL_KEYS = list(PAL)


def pal_uv(key):
    i = PAL_KEYS.index(key)
    return ((i % 8 + 0.5) / 8, 1 - (i // 8 + 0.5) / 8)


def palette_pixels():
    img = np.zeros((128, 128, 3), np.float32)
    for i, k in enumerate(PAL_KEYS):
        r, c = i // 8, i % 8
        img[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16] = PAL[k]
    return img


GEN_FUNCS = {"palette": palette_pixels}


def gen_image(key):
    """A packed image from a generated picture (GEN_FUNCS[key] or the room's `gen`), written as a PNG first."""
    if key in K.GEN:
        return K.GEN[key]
    fn = K.spec.get("gen", {}).get(key) or GEN_FUNCS[key]
    arr = fn()
    h, w = arr.shape[:2]
    im = bpy.data.images.new(key + "_tmp", w, h, alpha=False)
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :3] = np.clip(arr[..., :3], 0, 1)
    im.pixels.foreach_set(np.flipud(rgba).ravel())
    g = work() / "gen"
    g.mkdir(parents=True, exist_ok=True)
    path = g / f"{K.sid}_{key}.png"
    im.filepath_raw = str(path)
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)
    out = bpy.data.images.load(str(path))
    out.name = f"{K.sid}_{key}"
    out.pack()
    for ref in [out] + list(out.packed_files):
        attr = "filepath_raw" if ref is out else "filepath"
        setattr(ref, attr, "_" * 1000)
        setattr(ref, attr, f"//generated/{K.sid}_{key}.png")
    K.GEN[key] = out
    return out


# ---------------------------------------------------------------- geometry (world space, game coordinates in, identity transforms)
def cube(bm, gmin, gmax):
    a, b = B(gmin), B(gmax)
    c = (a + b) / 2
    s = Vector((abs(a.x - b.x), abs(a.y - b.y), abs(a.z - b.z)))
    s = Vector((max(s.x, 1e-4), max(s.y, 1e-4), max(s.z, 1e-4)))
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((s.x, s.y, s.z, 1.0)))


def box(bm, x0, x1, y0, y1, z0, z1):
    cube(bm, (min(x0, x1), min(y0, y1), min(z0, z1)), (max(x0, x1), max(y0, y1), max(z0, z1)))


def bx(bm, b, shrink=0.0):
    """A greybox box (dict with min, max), optionally inset."""
    mn, mx = b["min"], b["max"]
    cube(bm, [mn[0] + shrink, mn[1], mn[2] + shrink], [mx[0] - shrink, mx[1], mx[2] - shrink])


def cyl(bm, p0, p1, r0, r1=None, seg=16, cap=True):
    a, b = B(p0), B(p1)
    d = b - a
    if d.length < 1e-6:
        return
    q = d.to_track_quat("Z", "Y")
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                          matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())


def sphere(bm, p, r, seg=12, squash=1.0, sx=1.0, sz=1.0):
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(4, seg // 2 + 1), radius=r,
                              matrix=Matrix.Translation(B(p)) @ Matrix.Diagonal((sx, sz, squash, 1)))


def quad(bm, p0, p1, p2, p3):
    return bm.faces.new([bm.verts.new(B(p)) for p in (p0, p1, p2, p3)])


def tri(bm, p0, p1, p2):
    return bm.faces.new([bm.verts.new(B(p)) for p in (p0, p1, p2)])


def poly(bm, pts):
    return bm.faces.new([bm.verts.new(B(p)) for p in pts])


def torus(bm, c, axis, R, r, seg=24, rseg=8):
    """A ring of radius R, tube r, round the game axis `axis` ('x', 'y' or 'z') through c."""
    bm2 = bmesh.new()
    rings = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        ring = []
        for j in range(rseg):
            b = 2 * math.pi * j / rseg
            u = (R + r * math.cos(b)) * math.cos(a)
            v = (R + r * math.cos(b)) * math.sin(a)
            w = r * math.sin(b)
            if axis == "y":
                p = (c[0] + u, c[1] + w, c[2] + v)
            elif axis == "x":
                p = (c[0] + w, c[1] + u, c[2] + v)
            else:
                p = (c[0] + u, c[1] + v, c[2] + w)
            ring.append(bm2.verts.new(B(p)))
        rings.append(ring)
    for i in range(seg):
        for j in range(rseg):
            a, b = rings[i], rings[(i + 1) % seg]
            bm2.faces.new([a[j], b[j], b[(j + 1) % rseg], a[(j + 1) % rseg]])
    merge(bm, bm2)


def merge(bm, other):
    me = bpy.data.meshes.new("tmp")
    other.to_mesh(me)
    other.free()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)


def disc(bm, c, axis, r, seg=24, sign=1):
    """A flat disc facing +axis (sign 1) or -axis."""
    pts = []
    for i in range(seg):
        a = 2 * math.pi * i / seg * sign
        u, v = r * math.cos(a), r * math.sin(a)
        if axis == "z":
            pts.append((c[0] + u, c[1] + v, c[2]))
        elif axis == "x":
            pts.append((c[0], c[1] + v, c[2] + u))
        else:
            pts.append((c[0] + u, c[1], c[2] + v))
    f = poly(bm, pts)
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


def finish(name, bm, mname, coll=None, smooth=False, tile=None, keep_uv=False, recalc=True, sharp_deg=40):
    mat(mname)
    for e in bm.edges:
        if smooth and len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) < math.radians(sharp_deg)
        else:
            e.smooth = False
    for f in bm.faces:
        f.smooth = smooth
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if not bm.loops.layers.uv.get("UVMap"):
        bm.loops.layers.uv.new("UVMap")
    if not keep_uv:
        bm.normal_update()
        box_uv(bm, tile or K.TILES[mname])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(K.MATS[mname])
    ob = bpy.data.objects.new(name, me)
    (coll or K.ART).objects.link(ob)
    return ob


def part(name, mname, build, **kw):
    bm = bmesh.new()
    build(bm)
    if not bm.faces:
        bm.free()
        return None
    return finish(name, bm, mname, **kw)


class Painter:
    """One palette mesh from many pieces, each painted one swatch."""
    def __init__(s, mname="Paint_Palette"):
        s.bm = bmesh.new()
        s.uvl = s.bm.loops.layers.uv.new("UVMap")
        s.mname = mname

    def add(s, key, fn, *a, **kw):
        old = set(s.bm.faces)
        fn(s.bm, *a, **kw)
        uv = pal_uv(key)
        for f in s.bm.faces:
            if f not in old:
                for lp in f.loops:
                    lp[s.uvl].uv = uv

    def done(s, name, coll=None, smooth=False):
        if not s.bm.faces:
            s.bm.free()
            return None
        return finish(name, s.bm, s.mname, coll, smooth=smooth, keep_uv=True)


def set_uv_rect(bm, faces, rect, axes):
    """Planar UV over a game-space rectangle: axes = (iu, iv) game axis indices, rect = (u0, v0, u1, v1) in metres -> 0..1."""
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    u0, v0, u1, v1 = rect
    for f in faces:
        for lp in f.loops:
            p = lp.vert.co
            g = (p.x, p.z, -p.y)
            lp[uvl].uv = ((g[axes[0]] - u0) / (u1 - u0), (g[axes[1]] - v0) / (v1 - v0))


RIGHT = {"+x": (0, 0, -1), "-x": (0, 0, 1), "+z": (1, 0, 0), "-z": (-1, 0, 0)}
NORMAL = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}
SIDE_N = {"N": "+z", "S": "-z", "W": "+x", "E": "-x"}          # a wall by its inward normal


def picture(name, mname, centre, normal, w, h, uv=(0, 0, 1, 1), coll=None, bm=None, flip=False):
    """A flat quad facing `normal`, w wide, h tall, showing the UV rectangle uv upright (flip mirrors it, for the reflection)."""
    r = Vector(RIGHT[normal])
    up = Vector((0, 1, 0))
    c = Vector(centre)
    pts = [c - r * w / 2 - up * h / 2, c + r * w / 2 - up * h / 2, c + r * w / 2 + up * h / 2, c - r * w / 2 + up * h / 2]
    own = bm is None
    bm = bm or bmesh.new()
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    f = quad(bm, *[tuple(p) for p in pts])
    u0, v0, u1, v1 = uv
    st = ((1, 0), (0, 0), (0, 1), (1, 1)) if flip else ((0, 0), (1, 0), (1, 1), (0, 1))
    for lp, (s, t) in zip(f.loops, st):
        lp[uvl].uv = (u0 + (u1 - u0) * s, v0 + (v1 - v0) * t)
    if own:
        return finish(name, bm, mname, coll, keep_uv=True, recalc=False)
    return f


def wall_face(side):
    return {"N": K.Z0, "S": K.Z1, "W": K.X0, "E": K.X1}[side]


def on_wall(side, a, y, d):
    """A game point on wall `side`: a along it, height y, d metres into the room."""
    f = wall_face(side)
    if side == "N":
        return (a, y, f + d)
    if side == "S":
        return (a, y, f - d)
    if side == "W":
        return (f + d, y, a)
    return (f - d, y, a)


def wall_box(bm, side, a0, a1, y0, y1, d0, d1):
    p, q = on_wall(side, a0, y0, d0), on_wall(side, a1, y1, d1)
    cube(bm, [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)])


# ---------------------------------------------------------------- the door holes, from the leaves
def door_holes():
    out = []
    for d in K.GB.doors:
        p = d["props"]
        w, h = p["width"], p["height"]
        hx, hy, hz = d["hinge"]
        yaw = round(p["closed_yaw_deg"])
        side, a = {0: ("N", hx + w / 2), 180: ("S", hx - w / 2), 90: ("W", hz - w / 2), -90: ("E", hz + w / 2)}[yaw]
        out.append({"name": d["name"], "side": side, "a": a, "w": w + 0.04, "h": h + 0.04, "y": hy, "look": p.get("look", ""), "door": d})
    return out


def holes_on(side):
    return [(h["a"] - h["w"] / 2, h["a"] + h["w"] / 2, h["y"], h["y"] + h["h"]) for h in K.HOLES if h["side"] == side]


def free_spans(side, lo, hi, y0, y1, extra=()):
    """The parts of [lo, hi] along wall `side` not cut by a door hole (or the `extra` spans) between heights y0 and y1."""
    cuts = [(a0, a1) for a0, a1, ya, yb in holes_on(side) if ya < y1 and yb > y0] + list(extra)
    spans, x = [], lo
    for a0, a1 in sorted(cuts):
        if a0 > x:
            spans.append((x, min(a0, hi)))
        x = max(x, a1)
    if x < hi:
        spans.append((x, hi))
    return [(a, b) for a, b in spans if b - a > 0.02]


def wall_range(side):
    return (K.X0, K.X1) if side in "NS" else (K.Z0, K.Z1)


def skirting(mname, h=0.12, d=0.018, sides="NSWE", ranges=None, name="decor_Trim_Skirting"):
    def build(bm):
        for side in sides:
            lo, hi = (ranges or {}).get(side, wall_range(side))
            for a0, a1 in free_spans(side, lo, hi, 0.0, h):
                wall_box(bm, side, a0, a1, 0.0, h, 0.0, d)
    return part(name, mname, build)


def wall_band(mname, y0, y1, d=0.008, sides="NSWE", name="decor_Wall_Band", ranges=None, tile=None):
    def build(bm):
        for side in sides:
            lo, hi = (ranges or {}).get(side, wall_range(side))
            for a0, a1 in free_spans(side, lo, hi, y0, y1):
                ya, yb = y0, y1
                hs = [hh for hh in holes_on(side) if hh[0] < a1 and hh[1] > a0]
                if hs:
                    continue
                wall_box(bm, side, a0, a1, ya, yb, 0.0, d)
            # the band over each door (above the hole) and beside it
            for a0, a1, ya, yb in holes_on(side):
                if yb < y1:
                    wall_box(bm, side, max(a0, lo), min(a1, hi), max(y0, yb), y1, 0.0, d)
    return part(name, mname, build, tile=tile)


def rail(mname, y, h=0.05, d=0.025, sides="NSWE", name="decor_Trim_Rail"):
    def build(bm):
        for side in sides:
            lo, hi = wall_range(side)
            for a0, a1 in free_spans(side, lo, hi, y, y + h):
                wall_box(bm, side, a0, a1, y, y + h, 0.0, d)
    return part(name, mname, build)


def cornice(mname, h=0.12, d=0.10, name="decor_Trim_Cornice"):
    def build(bm):
        for side in "NSWE":
            lo, hi = wall_range(side)
            wall_box(bm, side, lo, hi, K.H - h, K.H, 0.0, d * 0.4)
            wall_box(bm, side, lo, hi, K.H - h * 0.45, K.H, 0.0, d)
    return part(name, mname, build)


def casings(mname, w=0.075, d=0.022, skip=(), name="decor_Trim_Casings"):
    def build(bm):
        for hh in K.HOLES:
            if any(s in hh["name"] for s in skip):
                continue
            side, a, hw, ht, y = hh["side"], hh["a"], hh["w"] / 2, hh["h"], hh["y"]
            wall_box(bm, side, a - hw - w, a - hw, y, y + ht + w, 0.0, d)
            wall_box(bm, side, a + hw, a + hw + w, y, y + ht + w, 0.0, d)
            wall_box(bm, side, a - hw, a + hw, y + ht, y + ht + w, 0.0, d)
    return part(name, mname, build)


# ---------------------------------------------------------------- art from the greybox boxes
def gb_box(name, mname, shrink=0.0, tile=None):
    b = K.BOX[name]
    return part(name, mname, lambda bm: bx(bm, b, shrink), tile=tile)


def shell_art(fmat, wmat, cmat, skip=(), wall_from=None):
    """The floor, the walls and the ceiling as the greybox built them (one Art object per box), and the black past every door."""
    for b in K.GB.boxes:
        n = b["name"]
        if not b.get("art") or b.get("zone") or any(n.startswith(s) for s in skip):
            continue
        if n == "Room_Floor":
            gb_box(n, fmat)
        elif n == "Room_Ceiling":
            gb_box(n, cmat)
        elif n.startswith("Room_Wall_"):
            gb_box(n, wmat)
        elif n.startswith("Beyond_"):
            gb_box(n, "Void_Black")


# ---------------------------------------------------------------- door leaves, from their look
def parse_look(look):
    for form in sorted(G.FORMS, key=len, reverse=True):
        if look.startswith(form + " "):
            rest = look[len(form) + 1:]
            for fin in sorted(G.FINISHES, key=len, reverse=True):
                if rest.startswith(fin + " door, "):
                    return form, fin, rest[len(fin) + 7:]
    return None


class Leaf:
    """A door leaf in its own frame (local x along the leaf from the hinge, y across: -y faces into the room, z up), one bmesh per material."""
    def __init__(s, w, h, t=0.045):
        s.w, s.h, s.t = w, h, t
        s.parts = {}

    def bm(s, mname):
        if mname not in s.parts:
            s.parts[mname] = bmesh.new()
        return s.parts[mname]

    def box(s, mname, x0, x1, y0, y1, z0, z1):
        bmesh.ops.create_cube(s.bm(mname), size=1.0, matrix=Matrix.Translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
                              @ Matrix.Diagonal((max(1e-4, x1 - x0), max(1e-4, y1 - y0), max(1e-4, z1 - z0), 1)))

    def both(s, mname, x0, x1, z0, z1, d, inset=0.0):
        """A raised piece on both faces: d proud of the slab."""
        t = s.t / 2
        s.box(mname, x0, x1, -t - d, -t + inset, z0, z1)
        s.box(mname, x0, x1, t - inset, t + d, z0, z1)

    def cyl_y(s, mname, x, z, r, y0, y1, seg=16):
        bmesh.ops.create_cone(s.bm(mname), cap_ends=True, segments=seg, radius1=r, radius2=r, depth=abs(y1 - y0),
                              matrix=Matrix.Translation((x, (y0 + y1) / 2, z)) @ Matrix.Rotation(math.pi / 2, 4, "X"))

    def sphere(s, mname, x, y, z, r, seg=10, sq=1.0):
        bmesh.ops.create_uvsphere(s.bm(mname), u_segments=seg, v_segments=max(4, seg // 2), radius=r,
                                  matrix=Matrix.Translation((x, y, z)) @ Matrix.Diagonal((1, sq, 1, 1)))

    def ring_y(s, mname, x, z, R, r, ysgn, seg=20):
        bm2 = bmesh.new()
        rings = []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            ring = []
            for j in range(6):
                b = 2 * math.pi * j / 6
                ring.append(bm2.verts.new((x + (R + r * math.cos(b)) * math.cos(a), ysgn * (s.t / 2 + r + 0.01) + r * math.sin(b),
                                           z + (R + r * math.cos(b)) * math.sin(a))))
            rings.append(ring)
        for i in range(seg):
            for j in range(6):
                a, b = rings[i], rings[(i + 1) % seg]
                bm2.faces.new([a[j], b[j], b[(j + 1) % 6], a[(j + 1) % 6]])
        me = bpy.data.meshes.new("tmp")
        bm2.to_mesh(me)
        bm2.free()
        s.bm(mname).from_mesh(me)
        bpy.data.meshes.remove(me)

    def prism(s, mname, pts, y0, y1):
        """A prism from a convex outline [(x, z)] in the leaf's plane, from y0 to y1."""
        bm = s.bm(mname)
        a = [bm.verts.new((x, y0, z)) for x, z in pts]
        b = [bm.verts.new((x, y1, z)) for x, z in pts]
        bm.faces.new(a)
        bm.faces.new(b[::-1])
        n = len(pts)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new([a[i], a[j], b[j], b[i]])

    def disc_y(s, mname, x, z, r, y, seg=28):
        bm = s.bm(mname)
        vs = [bm.verts.new((x + r * math.cos(2 * math.pi * i / seg), y, z + r * math.sin(2 * math.pi * i / seg))) for i in range(seg)]
        bm.faces.new(vs)

    def make(s, name, coll):
        names = sorted(s.parts)
        bm = bmesh.new()
        uvl = bm.loops.layers.uv.new("UVMap")
        for i, mname in enumerate(names):
            mat(mname)
            p = s.parts[mname]
            p.normal_update()
            if not p.loops.layers.uv.get("UVMap"):
                p.loops.layers.uv.new("UVMap")
            ul = p.loops.layers.uv["UVMap"]
            tile = K.TILES[mname]
            for f in p.faces:
                f.material_index = i
                n = f.normal
                ax = max(range(3), key=lambda k: abs(n[k]))
                for lp in f.loops:
                    c = lp.vert.co
                    u, v = ((c.y, c.z) if ax == 0 else (c.x, c.z) if ax == 1 else (c.x, c.y))
                    lp[ul].uv = (u / tile, v / tile)
            merge(bm, p)
        for f in bm.faces:
            f.smooth = False
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for mname in names:
            me.materials.append(K.MATS[mname])
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)
        return ob


HANDLE_MAT = {"brass knob": "Brass", "chrome lever": "Chrome", "push plate": "Steel", "ring pull": "Iron", "glass knob": "Glass_Door"}


def leaf_standard(L, form, fin, handle, flip_handle=False):
    w, h, t = L.w, L.h, L.t
    fm = finish_mat(fin)
    trim = fm
    L.box(fm, 0, w, -t / 2, t / 2, 0, h)
    st = 0.12                                                   # stiles and rails
    if form == "panelled":
        for (x0, x1) in ((st, w / 2 - 0.04), (w / 2 + 0.04, w - st)):
            for (z0, z1) in ((0.22, h * 0.45), (h * 0.5, h - st)):
                L.both(trim, x0, x1, z0, z1, 0.012)
                L.both(trim, x0 + 0.03, x1 - 0.03, z0 + 0.03, z1 - 0.03, 0.022)
    elif form == "six-panel":
        for (x0, x1) in ((st, w / 2 - 0.035), (w / 2 + 0.035, w - st)):
            for (z0, z1) in ((0.2, h * 0.36), (h * 0.40, h * 0.74), (h * 0.78, h - st)):
                L.both(trim, x0, x1, z0, z1, 0.015)
                L.both(trim, x0 + 0.025, x1 - 0.025, z0 + 0.025, z1 - 0.025, 0.026)
    elif form == "flush":
        L.both("Wood_Dark" if fin not in ("oak", "birch") else "Iron", 0, w, 0, 0.012, 0.004)
        L.both(fm, 0.01, w - 0.01, h * 0.08, h * 0.08 + 0.006, 0.003)
    elif form == "louvred":
        L.both(trim, 0, st, 0, h, 0.012)
        L.both(trim, w - st, w, 0, h, 0.012)
        L.both(trim, 0, w, h - st, h, 0.012)
        L.both(trim, 0, w, 0, 0.2, 0.012)
        L.both(trim, 0, w, h * 0.48, h * 0.52, 0.012)
        z = 0.24
        while z < h - st - 0.04:
            if not (h * 0.46 < z < h * 0.54):
                L.both(trim, st, w - st, z, z + 0.035, 0.01)
            z += 0.07
    elif form == "half-glazed":
        L.box("Glass_Door", st, w - st, -t / 2 - 0.002, t / 2 + 0.002, h * 0.52, h - st)
        for k in (1, 2):
            L.both(trim, st + (w - 2 * st) * k / 3 - 0.015, st + (w - 2 * st) * k / 3 + 0.015, h * 0.52, h - st, 0.01)
        L.both(trim, st, w - st, h * 0.52 + (h * 0.48 - st) / 2 - 0.015, h * 0.52 + (h * 0.48 - st) / 2 + 0.015, 0.01)
        L.both(trim, st, w - st, 0.2, h * 0.47, 0.018)
    elif form == "ledged and braced":
        n = max(4, int(w / 0.12))
        for k in range(n):
            L.both("Iron" if fin == "black lacquer" else fm, k * w / n + 0.004, (k + 1) * w / n - 0.004, 0.0, h, 0.006)
        for z in (0.25, h / 2, h - 0.25):
            L.box(fm, 0.04, w - 0.04, -t / 2 - 0.035, -t / 2, z - 0.08, z + 0.08)
        for (za, zb) in ((0.25, h / 2), (h / 2, h - 0.25)):
            ln = math.hypot(w - 0.2, zb - za)
            ang = math.atan2(zb - za, w - 0.2)
            m = Matrix.Translation((w / 2, -t / 2 - 0.02, (za + zb) / 2)) @ Matrix.Rotation(-ang, 4, "Y") @ Matrix.Diagonal((ln, 0.03, 0.1, 1))
            bmesh.ops.create_cube(L.bm(fm), size=1.0, matrix=m)
        for z in (0.25, h - 0.25):
            L.box("Iron", 0.0, w * 0.45, -t / 2 - 0.045, -t / 2 - 0.035, z - 0.03, z + 0.03)
    elif form == "round-topped":
        cx, r = w / 2, w / 2 - st
        zc = h - st - r
        arch = [(cx + r * math.cos(math.pi * i / 16), zc + r * math.sin(math.pi * i / 16)) for i in range(17)] + [(cx - r, 0.25), (cx + r, 0.25)]
        inner = [(cx + (r - 0.04) * math.cos(math.pi * i / 16), zc + (r - 0.04) * math.sin(math.pi * i / 16)) for i in range(17)] +             [(cx - r + 0.04, 0.29), (cx + r - 0.04, 0.29)]
        for sg in (-1, 1):
            L.prism(trim, arch, sg * t / 2, sg * (t / 2 + 0.014))
            L.prism("Brass" if fin in ("sky blue", "cream gloss") else "Wood_Dark", inner, sg * (t / 2 + 0.014), sg * (t / 2 + 0.02))
    elif form == "studded":
        nx, nz = 4, 8
        for i in range(nx):
            for j in range(nz):
                x = st * 0.6 + (w - st * 1.2) * (i + 0.5) / nx
                z = 0.2 + (h - 0.4) * (j + 0.5) / nz
                for sg in (-1, 1):
                    L.sphere("Iron", x, sg * t / 2, z, 0.018, 8, 0.6)
        for z in (0.3, h - 0.3):
            L.box("Iron", 0.0, w * 0.7, -t / 2 - 0.006, -t / 2, z - 0.035, z + 0.035)
    elif form == "quilted":
        nx, nz = 3, 6
        cw, ch = (w - 0.12) / nx, (h - 0.2) / nz
        for i in range(nx):
            for j in range(nz):
                x = 0.06 + cw * (i + 0.5)
                z = 0.1 + ch * (j + 0.5)
                rr = min(cw, ch) * 0.58
                for sg in (-1, 1):
                    bmesh.ops.create_uvsphere(L.bm(fm), u_segments=10, v_segments=6, radius=1.0, matrix=Matrix.Translation((x, sg * t / 2, z))
                                              @ Matrix.Diagonal((cw * 0.56, 0.035, ch * 0.56, 1)))
                    if i < nx - 1 and j < nz - 1:
                        L.sphere("Brass", x + cw / 2, sg * (t / 2 + 0.02), z + ch / 2, 0.012, 6)
    elif form == "mirror-faced":
        for sg in (-1, 1):
            y0, y1 = (-t / 2 - 0.006, -t / 2) if sg < 0 else (t / 2, t / 2 + 0.006)
            L.box("Mirror", 0.08, w - 0.08, y0, y1, 0.08, h - 0.08)
        L.both(trim, 0, 0.08, 0, h, 0.014)
        L.both(trim, w - 0.08, w, 0, h, 0.014)
        L.both(trim, 0, w, 0, 0.08, 0.014)
        L.both(trim, 0, w, h - 0.08, h, 0.014)
    elif form == "porthole":
        zc, r = h * 0.68, min(0.18, w * 0.22)
        for sg in (-1, 1):
            L.disc_y("Glass_Door", w / 2, zc, r, sg * (t / 2 + 0.002))
            L.ring_y("Brass" if fin not in ("brushed steel",) else "Chrome", w / 2, zc, r + 0.02, 0.022, sg)
        L.both(trim, 0.1, w - 0.1, 0.12, 0.34, 0.01)
    elif form == "stable (split)":
        L.both("Iron", 0, w, h * 0.52 - 0.005, h * 0.52 + 0.005, 0.003)
        L.box(trim, -0.0, w, -t / 2 - 0.10, -t / 2, h * 0.52 - 0.05, h * 0.52 - 0.01)
        for (z0, z1) in ((0.15, h * 0.48), (h * 0.56, h - 0.12)):
            L.both(trim, 0.1, w - 0.1, z0, z1, 0.012)
        for z in (0.3, h * 0.45, h * 0.6, h - 0.3):
            L.box("Iron", 0.0, 0.25, -t / 2 - 0.006, -t / 2, z - 0.02, z + 0.02)
    # the handle, both sides, on the far edge from the hinge
    hx = w - 0.075 if not flip_handle else 0.075
    hz = 1.0
    hm = HANDLE_MAT.get(handle)
    for sg in (-1, 1):
        y = sg * t / 2
        if handle in ("brass knob", "glass knob"):
            L.cyl_y(hm, hx, hz, 0.028, y, y + sg * 0.012)
            L.cyl_y(hm, hx, hz, 0.008, y, y + sg * 0.05, 8)
            L.sphere(hm, hx, y + sg * 0.062, hz, 0.03, 12, 0.85)
        elif handle == "chrome lever":
            L.box(hm, hx - 0.02, hx + 0.02, min(y, y + sg * 0.01), max(y, y + sg * 0.01), hz - 0.07, hz + 0.05)
            L.cyl_y(hm, hx, hz, 0.01, y, y + sg * 0.055, 8)
            d = 1 if not flip_handle else -1
            L.box(hm, min(hx, hx - d * 0.13), max(hx, hx - d * 0.13), min(y + sg * 0.045, y + sg * 0.062), max(y + sg * 0.045, y + sg * 0.062), hz - 0.009, hz + 0.009)
        elif handle == "push plate":
            L.box(hm, hx - 0.05, hx + 0.03, min(y, y + sg * 0.004), max(y, y + sg * 0.004), hz - 0.02, hz + 0.28)
        elif handle == "ring pull":
            L.cyl_y(hm, hx, hz + 0.04, 0.03, y, y + sg * 0.012)
            L.ring_y(hm, hx, hz - 0.02, 0.045, 0.008, sg)


def leaf_special(L, look, name):
    """The leaves whose look is a story's own words."""
    w, h, t = L.w, L.h, L.t
    if "lit door" in look:                                       # the void's door: white, its edges glowing (the glow is round the hole)
        L.box("Door_Lit_White", 0, w, -t / 2, t / 2, 0, h)
        L.both("Door_Lit_White", 0.1, w - 0.1, 0.12, h - 0.12, 0.006)
        L.cyl_y("Chrome", w - 0.08, 1.0, 0.025, -t / 2, -t / 2 - 0.05)
        L.cyl_y("Chrome", w - 0.08, 1.0, 0.025, t / 2, t / 2 + 0.05)
    elif "seam in the grid" in look:
        L.box("Grid_Black", 0, w, -t / 2, t / 2, 0, h)
        for k in range(1, 5):
            L.both("Grid_Emit", 0, w, h * k / 5 - 0.006, h * k / 5 + 0.006, 0.003)
        for k in range(1, 3):
            L.both("Grid_Emit", w * k / 3 - 0.006, w * k / 3 + 0.006, 0, h, 0.003)
        for z in np.linspace(0.05, h - 0.05, 9):
            L.both("Grid_Emit", w - 0.03 - 0.03 * math.sin(z * 9), w, z - 0.04, z + 0.04, 0.004)
    elif "reflection" in look:                                   # the mirror image of the round-topped cream door you came in by
        leaf_standard(L, "round-topped", "cream gloss", "glass knob", flip_handle=True)
        L.both("Mirror", 0.0, w, h - 0.06, h, 0.003)
    elif "locker door" in look:
        fm = "Locker_Blue"
        L.box(fm, 0, w, -t / 2, t / 2, 0, h)
        for z0 in (h - 0.42, 0.12):
            for k in range(6):
                z = z0 + k * 0.05
                L.box("Iron", 0.15, w - 0.15, -t / 2 - 0.004, -t / 2, z, z + 0.022)
        L.both(fm, 0.04, w - 0.04, 0.5, h - 0.5, 0.008)
        L.box("Chrome", w - 0.12, w - 0.07, -t / 2 - 0.04, -t / 2, 0.9, 1.2)
        L.box("Sign_Locker13", w / 2 - 0.12, w / 2 + 0.12, -t / 2 - 0.012, -t / 2 - 0.008, h - 0.62, h - 0.48)
    elif "washing machine" in look:                              # a round door: a chrome ring, the glass bowl, the handle
        cx, cz, r = w / 2, h / 2, min(w, h) / 2 - 0.02
        L.ring_y("Chrome", cx, cz, r - 0.06, 0.06, -1, 32)
        L.ring_y("Chrome", cx, cz, r - 0.06, 0.06, 1, 32)
        bm = L.bm("Washer_Enamel")
        for sg in (-1, 1):
            vs = [bm.verts.new((cx + (r - 0.04) * math.cos(2 * math.pi * i / 32), sg * 0.05, cz + (r - 0.04) * math.sin(2 * math.pi * i / 32)))
                  for i in range(32)]
            vi = [bm.verts.new((cx + (r - 0.2) * math.cos(2 * math.pi * i / 32), sg * 0.05, cz + (r - 0.2) * math.sin(2 * math.pi * i / 32)))
                  for i in range(32)]
            for i in range(32):
                j = (i + 1) % 32
                bm.faces.new([vs[i], vs[j], vi[j], vi[i]] if sg < 0 else [vi[i], vi[j], vs[j], vs[i]])
        L.disc_y("Glass_Door", cx, cz, r - 0.19, -0.03)
        L.disc_y("Glass_Door", cx, cz, r - 0.19, 0.03)
        L.box("Chrome", w - 0.12, w - 0.02, -0.11, -0.05, cz - 0.15, cz + 0.15)
    elif "vending machine" in look:
        t2 = 0.1
        L.box("Vend_Body", 0, w, -t2 / 2, t2 / 2, 0, h)
        L.box("Vend_Glow", 0.06, w - 0.3, -t2 / 2 - 0.004, -t2 / 2, 0.5, h - 0.08)
        L.box("Vend_Panel", w - 0.26, w - 0.05, -t2 / 2 - 0.006, -t2 / 2, 0.7, h - 0.3)
        L.box("Iron", 0.06, w - 0.3, -t2 / 2 - 0.02, -t2 / 2, 0.12, 0.42)
    elif "marked EXIT" in look:
        L.box("Door_Exit_Grey", 0, w, -t / 2, t / 2, 0, h)
        L.box("Chrome", 0.1, w - 0.1, -t / 2 - 0.07, -t / 2 - 0.05, 0.98, 1.02)
        for x in (0.12, w - 0.12):
            L.box("Chrome", x - 0.02, x + 0.02, -t / 2 - 0.07, -t / 2, 0.95, 1.05)
        L.box("Sign_Exit", w / 2 - 0.16, w / 2 + 0.16, -t / 2 - 0.004, -t / 2, 1.5, 1.62)
    else:
        L.box("Door_Cream_Gloss", 0, w, -t / 2, t / 2, 0, h)


SPECIAL_MATS = {
    "Door_Lit_White": dict(color=(0.86, 0.86, 0.84), rough=0.5),
    "Grid_Black": dict(color=(0.02, 0.025, 0.02), rough=0.4),
    "Grid_Emit": dict(color=(0.15, 1.0, 0.3), emit=((0.15, 1.0, 0.3), 3.0), group=None),
    "Locker_Blue": dict(color=(0.20, 0.38, 0.62), rough=0.4, metal=0.3),
    "Washer_Enamel": dict(color=(0.86, 0.87, 0.86), rough=0.3),
    "Vend_Body": dict(color=(0.10, 0.10, 0.11), rough=0.4),
    "Vend_Panel": dict(color=(0.55, 0.56, 0.58), rough=0.4, metal=0.5),
    "Door_Exit_Grey": dict(color=(0.42, 0.43, 0.44), rough=0.6),
    "Sign_Locker13": dict(color=(0.86, 0.84, 0.76), rough=0.5),
    "Sign_Exit": dict(color=(0.10, 0.55, 0.22), emit=((0.15, 0.9, 0.3), 2.0), group=None),
}
MATLIB.update(SPECIAL_MATS)


def build_leaves():
    for d in K.GB.doors:
        p = d["props"]
        w, h = p["width"], p["height"]
        look = p.get("look", "")
        L = Leaf(w, h)
        pl = parse_look(look)
        if pl:
            leaf_standard(L, *pl)
        else:
            leaf_special(L, look, d["name"])
        ob = L.make(d["name"], K.DOORS)
        ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(math.radians(p["closed_yaw_deg"]), 4, "Z")
        for k, v in p.items():
            ob[k] = v


# ---------------------------------------------------------------- lights
def light(kind, pos, watts, color=(1.0, 0.85, 0.65), radius=0.08, sets=None, aim=None, cone=120.0, size=None, name=None):
    """A Cycles light, on in `sets` (None: every set). aim: a game direction (spot, area)."""
    K.LIGHTS.append(dict(kind=kind, pos=pos, watts=watts, color=color, radius=radius, sets=sets, aim=aim, cone=cone, size=size, name=name))


def add_lights():
    cols = {}
    for s in ["all"] + K.SETS:
        c = bpy.data.collections.new("Lights_" + s)
        bpy.context.scene.collection.children.link(c)
        cols[s] = c
    for i, L in enumerate(K.LIGHTS):
        d = bpy.data.lights.new(L["name"] or f"Lamp_{i:02d}", L["kind"])
        d.energy, d.color = L["watts"], L["color"]
        if L["kind"] == "AREA":
            sz = L["size"] or (0.5, 0.5)
            d.shape, d.size, d.size_y = "RECTANGLE", sz[0], sz[1]
        elif L["kind"] != "SUN":
            d.shadow_soft_size = L["radius"]
        if L["kind"] == "SPOT":
            d.spot_size, d.spot_blend = math.radians(L["cone"]), 0.5
        ob = bpy.data.objects.new(d.name, d)
        ob.visible_camera = False
        ob.location = B(L["pos"])
        if L["aim"]:
            ob.rotation_euler = B(L["aim"]).to_track_quat("-Z", "Y").to_euler()
        for s in (L["sets"] or ["all"]):
            cols[s].objects.link(ob)


def setup_world():
    sc = bpy.context.scene
    w = bpy.data.worlds.new("Room")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background") or w.node_tree.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
    bg.inputs["Strength"].default_value = 0.0


def set_emit(mname, strength):
    m = bpy.data.materials.get(mname)
    if m:
        m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = strength


def apply_light_set(name):
    """`name` one of K.SETS, or "export" (as the first set)."""
    st = K.SETS[0] if name == "export" else name
    for s in K.SETS:
        c = bpy.data.collections.get("Lights_" + s)
        if c:
            c.hide_render = s != st
    for mname, per in K.EMIT_SETS.items():
        if mname in K.MATS:
            set_emit(mname, per.get(st, per.get("default", 0.0)))


# ---------------------------------------------------------------- layout objects
def build_layout():
    for b in K.GB.boxes:
        if b.get("zone"):
            n = b["name"]
        elif b["col"]:
            n = "COL_" + b["name"]
        else:
            continue
        me = bpy.data.meshes.new(n)
        bm = bmesh.new()
        cube(bm, b["min"], b["max"])
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(n, me)
        ob.display_type = "WIRE"
        ob.hide_render = True
        K.LAYOUT.objects.link(ob)
    for e in K.GB.empties + K.GB.cams:
        ob = bpy.data.objects.new(e["name"], None)
        ob.location = B(e["pos"])
        if e["face"]:
            ob.rotation_euler = (0, 0, math.atan2(e["face"][0], e["face"][1]))
        for k, v in e["props"].items():
            ob[k] = v
        ob.empty_display_size = 0.3
        K.LAYOUT.objects.link(ob)


def stage_layout():
    import export_scene
    export_scene.write(K.sid, ROOT / f"world/{K.sid}.json")


def stage_check():
    """tools/blender/check_layout.py's rules on the Art collection, with the links' arrivals and F spots as the points to keep clear."""
    import check_layout
    world = json.loads((ROOT / f"world/{K.sid}.json").read_text())
    consts = {"links": {l["door"]: {"arrive": l["arrive"], "at": [l["at"][0], l["at"][2]]} for l in world["links"]},
              "spots": {s["name"]: {"at": [s["position"][0], s["position"][2]]} for s in world["spots"]}}
    parts = check_layout.blender_parts("Art")
    print(f"layout check: scene {K.sid}, {len(parts)} visible meshes, {len(world['colliders'])} colliders")
    res = check_layout.check(parts, world, consts)
    bad = check_layout.report(res)
    print("CHECK_LAYOUT", K.sid, "exit", 1 if bad else 0)
    lines = [f"layout check: scene {K.sid}, {len(parts)} visible meshes, {len(world['colliders'])} colliders"]
    lines += [f"{'PASS' if ok else 'FAIL'}  {rule:6s} {text}" for ok, rule, text in res]
    lines.append(f"{'PASS' if not bad else 'FAIL'}: {len(res) - bad} of {len(res)} checks passed" + (f", {bad} failed" if bad else ""))
    (work() / "check_layout.txt").write_text("\n".join(lines) + "\n")
    return bad


# ---------------------------------------------------------------- export objects: merged by material, faces nobody sees dropped
def hidden_inside(bm, oname):
    """Cut a big plain mesh (a wall, a floor, a block) on a 1 m grid, and drop the cells that lie against another collider's box (a wall
    behind the narrowing walls, the floor under a cabinet, a hidden core): their light is never seen."""
    if len(bm.faces) > 64 or oname.startswith(("Beyond_", "decor_")):
        return
    bm.verts.ensure_lookup_table()
    lo = [min(v.co[i] for v in bm.verts) for i in range(3)]
    hi = [max(v.co[i] for v in bm.verts) for i in range(3)]
    if max(hi[i] - lo[i] for i in range(3)) < 1.5:
        return
    for ax in range(3):
        c = math.floor(lo[ax]) + 1.0
        while c < hi[ax] - 1e-3:
            no = [0.0, 0.0, 0.0]
            no[ax] = 1.0
            co = [0.0, 0.0, 0.0]
            co[ax] = c
            bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces), plane_co=co, plane_no=no)
            c += 1.0
    bm.normal_update()
    mid = [(lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2, -(lo[1] + hi[1]) / 2]
    boxes = [b for b in K.SOLIDS if not all(b["min"][i] - 1e-3 <= mid[i] <= b["max"][i] + 1e-3 for i in range(3))]   # not the box it dresses
    bad = []
    for f in bm.faces:
        c, n = f.calc_center_median(), f.normal
        p = (c.x + n.x * 0.01, c.z + n.z * 0.01, -(c.y + n.y * 0.01))
        for b in boxes:
            if b["name"] == oname:
                continue
            if all(b["min"][i] + 1e-3 < p[i] < b["max"][i] - 1e-3 for i in range(3)):
                bad.append(f)
                break
    bmesh.ops.delete(bm, geom=bad, context="FACES")


def cull(bm, mname, oname):
    hidden_inside(bm, oname)
    e = 2e-3
    two = K.MATDEF.get(mname, {}).get("two_sided")
    bad = []
    for f in bm.faces:
        c, n = f.calc_center_median(), f.normal
        gx, gy, gz = c.x, c.z, -c.y
        nx, ny, nz = n.x, n.z, -n.y
        out = (nx < -0.9 and gx <= K.X0 + e) or (nx > 0.9 and gx >= K.X1 - e) or (nz < -0.9 and gz <= K.Z0 + e) or (nz > 0.9 and gz >= K.Z1 - e) \
            or (ny < -0.9 and gy <= e) or (ny > 0.9 and gy >= K.H - e)
        if oname == "Room_Floor":
            out = not (ny > 0.9 and abs(gy) < e)
        elif oname == "Room_Ceiling":
            out = not (ny < -0.9 and abs(gy - K.H) < e)
        elif oname.startswith("Beyond_"):
            out = False
        elif not two and not oname.startswith("Room_Wall"):
            out = out or (ny > 0.5 and gy > SEEN_UP and gy < K.H - 0.05) or (ny < -0.5 and gy < SEEN_DOWN and gy > e)
        if out:
            bad.append(f)
    bmesh.ops.delete(bm, geom=bad, context="FACES")


def make_export_objects():
    exp = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(exp)
    by_mat = {}
    sep = []
    gname = next(iter(K.spec.get("groups", {})), None)
    for ob in K.ART.objects:
        if ob.name in K.MOVING or ob.name in K.SEPARATE:
            sep.append(ob)
            continue
        mats = [m for m in ob.data.materials]
        if len(mats) != 1:
            sep.append(ob)
            continue
        mname = mats[0].name
        key = mname if not (gname and ob.name in K.MIRROR) else f"{gname}_{mname}"
        bm = by_mat.setdefault(key, bmesh.new())
        tmp = bmesh.new()
        tmp.from_mesh(ob.data)
        tmp.transform(ob.matrix_world)
        tmp.normal_update()
        cull(tmp, mname, ob.name)
        merge(bm, tmp)
    out = {}
    for key, bm in by_mat.items():
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-4, edges=bm.edges)          # zero-area faces crash the UV packer
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_area() < 1e-7], context="FACES")
        if not bm.faces:
            bm.free()
            continue
        mname = key[len(gname) + 1:] if gname and key.startswith(gname + "_") else key
        me = bpy.data.meshes.new(key)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(bpy.data.materials[mname])
        ob = bpy.data.objects.new(key, me)
        exp.objects.link(ob)
        out[key] = ob
    for ob in sep:                                             # the page's own nodes: a copy, same name, same origin
        c = ob.copy()
        c.data = ob.data.copy()
        c.name = ob.name + "_x"
        for coll in list(c.users_collection):
            coll.objects.unlink(c)
        exp.objects.link(c)
        out[c.name] = c
    return exp, out


# ---------------------------------------------------------------- cycles, the lightmap UVs, the bake
def setup_cycles(samples, bake=False):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = samples
    cy.use_adaptive_sampling = False
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces, cy.transmission_bounces, cy.transparent_max_bounces = 8, 5, 3, 6, 12
    cy.use_denoising = not bake
    prefs = bpy.context.preferences.addons["cycles"].preferences
    gpu = False
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
    sc.view_settings.view_transform = "Standard"
    return cy.device


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


def lightmap_uv(objs, page, scale):
    for o in objs:
        uvs = o.data.uv_layers
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.new(name="lightmap", do_init=False)
        uvs.active = uvs["lightmap"]
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        base = o.name[:-2] if o.name.endswith("_x") and o.name[:-2] in K.SEPARATE else o.name
        f = scale.get(base) or scale.get(o.data.materials[0].name if o.data.materials else "", None)
        if f:
            d = o.data.uv_layers["lightmap"].data
            us = np.array([x.uv for x in d]) * f
            d.foreach_set("uv", us.ravel())
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / page, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    a3 = sum(area3d(o) for o in objs)
    au = sum(uv_area(o, "lightmap") for o in objs)
    dens = page * math.sqrt(au / max(a3, 1e-9))
    print(f"  page {page}: {a3:.1f} m2, about {dens:.1f} px/m")
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
    path = str(work() / "dn.exr")
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


def bake_set(objs, S, light_set, samples, tag):
    apply_light_set(light_set)
    bpy.context.scene.cycles.samples = samples
    img = bpy.data.images.new(f"LM_{tag}_{light_set}", S, S, alpha=False, float_buffer=True)
    img.colorspace_settings.name = "Non-Color"
    for o in objs:
        for slot in o.material_slots:
            nt = slot.material.node_tree
            node = nt.nodes.new("ShaderNodeTexImage")
            node.name = "BAKE_TARGET"
            node.image = img
            nt.nodes.active = node
            node.select = True
    select_only(objs)
    for o in objs:
        o.data.uv_layers.active = o.data.uv_layers["lightmap"]
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX, margin_type="EXTEND", use_clear=True,
                        target="IMAGE_TEXTURES")
    for o in objs:
        for slot in o.material_slots:
            nt = slot.material.node_tree
            for nd in [nd for nd in nt.nodes if nd.name.startswith("BAKE_TARGET")]:
                nt.nodes.remove(nd)
    a = denoise_image(img, S)
    bpy.data.images.remove(img)
    return a[..., :3].copy()


def bake_plan():
    """The maps: [(index, group(s), light set, extras key)]. One set: the shell's page and the props' page. Two: the same pair per set. Three or
    more: one page of everything per set (at most four maps a scene)."""
    sets = K.SETS
    keyof = {s: ("lightmap" if i == 0 else f"lightmap_{s}") for i, s in enumerate(sets)}
    if len(sets) <= 2:
        plan = []
        for si, s in enumerate(sets):
            plan += [(2 * si, ("struct",), s, keyof[s]), (2 * si + 1, ("props",), s, keyof[s])]
        pages = {("struct",): K.spec.get("pages", (2048, 2048))[0], ("props",): K.spec.get("pages", (2048, 2048))[1]}
    else:
        plan = [(si, ("struct", "props"), s, keyof[s]) for si, s in enumerate(sets)]
        pages = {("struct", "props"): K.spec.get("pages", (2048,))[0]}
    return plan, pages, keyof


def stage_bake(samples):
    exp, out = make_export_objects()
    K.ART.hide_render = K.ART.hide_viewport = True
    leaves = sorted(K.DOORS.objects, key=lambda o: o.name)
    setup_cycles(samples, bake=True)
    for nm, o in out.items():                                  # what the page moves is not in the bake (its light and shadow would stay behind)
        base = nm[:-2] if nm.endswith("_x") else None
        if base in K.MOVING or nm in K.spec.get("hide_in_bake", ()):
            o.hide_render = True
    plan, pages, keyof = bake_plan()
    groups_done = {}
    report = {}
    for idx, groups, light_set, key in plan:
        objs = [o for nm, o in out.items() if not (nm.endswith("_x") and nm[:-2] in K.MOVING) and o.data.materials
                and all(K.GROUP.get(s.material.name) in groups for s in o.material_slots)]
        if "props" in groups:
            objs += leaves
        if groups not in groups_done:
            print(f"lightmap page {groups}: {[o.name for o in objs]}")
            groups_done[groups] = lightmap_uv(objs, pages[groups], K.spec.get("uv_scale", {}))
        S = pages[groups]
        t0 = time.time()
        rgb = bake_set(objs, S, light_set, samples, idx)
        np.save(work() / f"raw_{idx}.npy", rgb.astype(np.float16))
        mats = sorted({s.material.name for o in objs for s in o.material_slots if K.GROUP.get(s.material.name) is not None})
        report[idx] = {"set": light_set, "key": key, "groups": list(groups), "size": S, "px_per_m": round(groups_done[groups], 1), "samples": samples,
                       "seconds": round(time.time() - t0), "materials": mats, "objects": [o.name for o in objs]}
        print("  baked", idx, light_set, groups, report[idx]["seconds"], "s")
    (work() / "bake.json").write_text(json.dumps({"scene": K.sid, "sets": K.SETS, "keys": keyof, "maps": report, "grade": K.spec.get("grade", {}),
                                                  "moving": sorted(K.MOVING), "separate": sorted(K.SEPARATE)}, indent=1))
    for o in out.values():
        o.hide_render = False
    apply_light_set(K.SETS[0])
    K.ART.hide_render = K.ART.hide_viewport = False
    exp.hide_render = exp.hide_viewport = True


# ---------------------------------------------------------------- privacy, saving, the GLB
KEEP_PROPS_PREFIX = ("lightmap",)
LAYOUT_PREFIX = ("DoorLeaf_", "Spot_", "Marker_", "Link_", "Arrive_", "SecCam_")


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private(blend_dir):
    kinds = ("scenes", "worlds", "objects", "meshes", "materials", "collections", "cameras", "lights", "images", "node_groups", "screens",
             "window_managers", "workspaces")
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
                    if kind == "materials" and st is idb and k.startswith(KEEP_PROPS_PREFIX):
                        continue
                    if kind == "objects" and st is idb and idb.name.startswith(LAYOUT_PREFIX):
                        continue
                    if kind == "objects" and st is idb and k in ("page", "unbaked", "pivot"):
                        continue
                    if st is not idb and k.startswith(("cycles", "eevee")):
                        continue
                    try:
                        del st[k]
                    except Exception:
                        pass
    for sc in bpy.data.scenes:
        set_path(sc.render, "filepath", "//")
        for p in sc.render.bl_rna.properties:
            if p.identifier.startswith("use_stamp") and not p.is_readonly:
                setattr(sc.render, p.identifier, False)
    for im in bpy.data.images:
        for pf in im.packed_files:
            if pf.filepath and not pf.filepath.startswith("//"):
                set_path(pf, "filepath", "//generated/" + Path(pf.filepath).name)
        if im.packed_file or im.source != "FILE" or not im.filepath:
            continue
        p = Path(bpy.path.abspath(im.filepath))
        try:
            rel = "//" + os.path.relpath(p, blend_dir).replace("\\", "/")
        except ValueError:
            rel = "//" + p.name
        set_path(im, "filepath", rel)
    for scr in bpy.data.screens:
        for a in scr.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"//"
    wm = bpy.context.window_manager
    for op in ("import_scene.gltf", "export_scene.gltf", "wm.save_as_mainfile", "wm.save_mainfile", "wm.open_mainfile", "image.save_as"):
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


def blend_path():
    return ROOT / f"blender/scenes/{K.sid}.blend"


def save_blend():
    p = blend_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    scrub_private(p.parent)
    bpy.ops.wm.save_as_mainfile(filepath=str(p), compress=True)
    scrub_private(p.parent)
    bpy.ops.wm.save_mainfile(compress=True)


def stage_export():
    """The GLB: the Export collection and the leaves, as art only. Each baked material names its maps (`lightmap`, `lightmap_<set>`) with a
    placeholder intensity; tools/blender/rdwe_rooms2_pack.py writes the graded intensities. The page's own nodes carry `page` (what it does with
    them) and `unbaked` (true: drawn with the page's own light)."""
    bake = json.loads((work() / "bake.json").read_text())
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    K.ART.hide_viewport = True
    leaves = sorted(K.DOORS.objects, key=lambda o: o.name)
    url = "world/lightmaps/" + K.sid + "_{}.webp"
    for idx, r in bake["maps"].items():
        for mn in r["materials"]:
            m = bpy.data.materials[mn]
            m[r["key"]] = url.format(idx)
            m[r["key"] + "_intensity"] = 1.0
    for o in exp.objects:
        base = o.name[:-2] if o.name.endswith("_x") else o.name
        if base in K.MOVING:
            o["unbaked"] = True
            o["page"] = K.spec.get("moving", {}).get(base, "moves")
        elif base in K.SEPARATE:
            o["page"] = K.spec.get("separate", {}).get(base, "its own node")
        for g in K.spec.get("groups", {}):
            if o.name.startswith(g + "_"):
                o["page"] = K.spec.get("separate", {}).get(g, "a group of its own nodes")
    stash = {o.name: {k: o[k] for k in o.keys()} for o in leaves}
    for o in leaves:
        for k in list(o.keys()):
            del o[k]
    apply_light_set("export")
    for mname, per in K.EMIT_SETS.items():                    # the page switches these: exported at their 'on' strength
        if mname in K.MATS:
            set_emit(mname, per.get("export", max(per.values())))
    names = {}
    for o in exp.objects:
        if o.name.endswith("_x"):
            names[o.name] = o.name[:-2]
    bpy.ops.object.select_all(action="DESELECT")
    for o in list(exp.objects) + leaves:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = work() / f"{K.sid}_raw.glb"
    scrub_private(blend_path().parent)
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False, export_animations=False)
    for o in leaves:
        for k, v in stash[o.name].items():
            o[k] = v
    (work() / "node_names.json").write_text(json.dumps(names))
    print("EXPORTED", raw, raw.stat().st_size)
    apply_light_set(K.SETS[0])
    K.ART.hide_viewport = False
    exp.hide_viewport = exp.hide_render = True


# ---------------------------------------------------------------- stills
def look_cam(name, loc, target, fov_v=70.0, ortho=None):
    cam = bpy.data.cameras.new(name)
    cam.sensor_fit = "VERTICAL"
    if ortho:
        cam.type = "ORTHO"
        cam.ortho_scale = ortho
        cam.sensor_fit = "AUTO"
    else:
        cam.lens_unit = "FOV"
        cam.angle_y = math.radians(fov_v)
    cam.clip_start, cam.clip_end = 0.05, 200
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


def arrive_of(door):
    e = next(e for e in K.GB.empties if e["name"] == "Arrive_" + door)
    return e["pos"], e["face"]


def stage_render(samples=96, only=None):
    sc = bpy.context.scene
    stills = ROOT / f"docs/renders/{K.sid}"
    stills.mkdir(parents=True, exist_ok=True)
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
    K.LAYOUT.hide_render = True
    setup_cycles(samples)
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
    shots = {}
    for key, (loc, tgt, fov) in K.spec["shots"].items():
        shots[key] = look_cam(key, loc, tgt, fov)
    span = max(K.X1 - K.X0, K.Z1 - K.Z0)
    plan = look_cam("plan", ((K.X0 + K.X1) / 2, K.H + 20, (K.Z0 + K.Z1) / 2), None, ortho=span * 1.04)
    plan.rotation_euler = (0, 0, 0)
    arts = list(K.ART.objects) + list(K.DOORS.objects)
    cut = [o for o in arts if o.name == "Room_Ceiling" or o.name.startswith(tuple(K.spec.get("plan_cut", ())) + ("Ceiling",))
           or (o.type == "MESH" and min((o.matrix_world @ Vector(c)).z for c in o.bound_box) > 2.3)]
    expo = K.spec.get("exposure", 0.0)
    sets = K.SETS
    todo = []
    first = K.spec.get("shot_sets", {})                         # the set a review still is shown in (the first set by default)
    for s in sets:
        for key in shots:
            if s != sets[0] and key not in K.spec.get("set_shots", ("1_arrival", "2_wide")):
                continue
            todo.append((key, s))
    todo.append(("5_plan", K.spec.get("plan_set", sets[0])))
    for key, s in todo:
        if only and key not in only:
            continue
        apply_light_set(s)
        sc.camera = shots.get(key, plan)
        for o in arts:
            o.visible_camera = not (key == "5_plan" and o in cut)
        w, h = (1920, 1080) if key != "5_plan" else (1400, int(1400 * (K.Z1 - K.Z0 + 0.4) / (K.X1 - K.X0 + 0.4)) if K.X1 - K.X0 > K.Z1 - K.Z0 else 1400)
        if key == "5_plan" and K.Z1 - K.Z0 >= K.X1 - K.X0:
            w, h = int(1400 * (K.X1 - K.X0 + 0.4) / (K.Z1 - K.Z0 + 0.4)), 1400
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = max(64, w), max(64, h), 100
        sc.view_settings.exposure = expo + K.spec.get("set_exposure", {}).get(s, 0.0) + (0.8 if key == "5_plan" else 0.0)
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        to_docs = key in ("1_arrival", "2_wide", "3_detail") and s == first.get(key, sets[0])
        path = stills / f"{key}.jpg" if to_docs else work() / f"{key}{'' if key == '5_plan' or s == first.get(key, sets[0]) else '_' + s}.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        q = 90
        while to_docs and path.stat().st_size > 400_000 and q > 40:
            q -= 6
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        strip_jpeg_comments(path)
        print("STILL", key, s, path.name, path.stat().st_size)
    for o in arts:
        o.visible_camera = True
    apply_light_set(sets[0])


def fill_missing():
    """A plain box (in its greybox colour) for any collider the room's dressing did not build, so no collider is ever left without art."""
    have = {o.name for o in K.ART.objects}
    n = 0
    for b in K.GB.boxes:
        if not b["col"] or not b.get("art"):
            continue
        if b["name"] in have or any(h.startswith(b["name"] + "_") for h in have):
            continue
        mn = "GB_" + b["mat"]
        K.MATDEF.setdefault(mn, dict(color=G.MATS.get(b["mat"], (0.5, 0.5, 0.5)), rough=0.7))
        gb_box(b["name"], mn)
        n += 1
        print("  FILL", b["name"], b["mat"])
    print(f"FILL {n} collider(s) given a plain box")
    return n


def ensure_cover(tol=0.04):
    """The layout check wants every collider's box covered by the world box of some solid piece (to 5 cm). Where a collider's own pieces
    (named after it) fall short in plan (a round stand on a square box), its first piece gets a 2 mm floor plate of its own material
    over the box's footprint, so its box spans the collider."""
    from mathutils import Vector
    n = 0
    for b in K.GB.boxes:
        if not b["col"] or not b.get("art") or b["name"].startswith(("Room_", "Beyond_")):
            continue
        obs = [o for o in K.ART.objects if (o.name == b["name"] or o.name.startswith(b["name"] + "_")) and o.type == "MESH" and o.data.polygons]
        if not obs:
            continue

        def gbox(o):
            pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
            g = [(p.x, p.z, -p.y) for p in pts]
            return [min(q[i] for q in g) for i in range(3)], [max(q[i] for q in g) for i in range(3)]
        bbs = [gbox(o) for o in obs]
        lo = [min(bb[0][i] for bb in bbs) for i in range(3)]
        hi = [max(bb[1][i] for bb in bbs) for i in range(3)]
        single = any(all(bb[0][i] <= b["min"][i] + tol and bb[1][i] >= b["max"][i] - tol for i in range(3)) for bb in bbs)
        if single:
            continue
        inside = [o for o in obs if all(gbox(o)[0][i] >= b["min"][i] - tol and gbox(o)[1][i] <= b["max"][i] + tol for i in (0, 2))]
        if not inside:
            continue
        main = max(inside, key=lambda o: (gbox(o)[1][1] - gbox(o)[0][1]))
        bm = bmesh.new()
        bm.from_mesh(main.data)
        y0 = b["min"][1]
        mn, mx = b["min"], b["max"]
        cube(bm, (mn[0] + 0.01, y0, mn[2] + 0.01), (mx[0] - 0.01, y0 + 0.002, mx[2] - 0.01))
        ytop = gbox(main)[1][1]
        if ytop < mx[1] - tol:                                     # and a hair-thin rod up to the box's top, on the piece's axis
            c = ((mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2)
            cube(bm, (c[0] - 0.004, ytop - 0.01, c[1] - 0.004), (c[0] + 0.004, mx[1] - 0.005, c[1] + 0.004))
        uvl = bm.loops.layers.uv.get("UVMap")
        bm.to_mesh(main.data)
        bm.free()
        n += 1
        print("  COVER plate", b["name"], "on", main.name)
    print(f"COVER {n} collider(s) given a floor plate")


def summary():
    tris = sum(len(p.vertices) - 2 for o in list(K.ART.objects) + list(K.DOORS.objects) if o.type == "MESH" for p in o.data.polygons)
    print(f"ART {K.sid}: {len(K.ART.objects)} objects, {len(K.DOORS.objects)} leaves, about {tris} triangles; {len(K.LIGHTS)} lights; "
          f"{len(K.MATS)} materials; moving {sorted(K.MOVING)}; separate {sorted(K.SEPARATE)}")
