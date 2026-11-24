"""Builds the Farway apartment in Blender, lights and bakes it, and exports world/apartment.glb (docs/BLENDER.md, "1. apartment (the pilot)").

Re-runnable, from the repo root:

    blender -b --python tools/blender/build_apartment.py                       (every stage, in one run)
    blender -b --python tools/blender/build_apartment.py -- --stage art        (build the art, save blender/scenes/apartment.blend)
    blender -b blender/scenes/apartment.blend --python tools/blender/build_apartment.py -- --stage bake [--samples 512] [--device gpu]
    blender -b blender/scenes/apartment.blend --python tools/blender/build_apartment.py -- --stage export
    blender -b blender/scenes/apartment.blend --python tools/blender/build_apartment.py -- --stage axes     (the marker-cube axes check)
    blender -b blender/scenes/apartment.blend --python tools/blender/build_apartment.py -- --stage render [--engine CYCLES|EEVEE]

Stages: art (geometry, materials, lights, stand-ins) -> bake (merge by material, lightmap UV, Cycles bake, OIDN denoise, 8-bit PNGs in
blender/scenes/lightmaps/) -> export (GLB; the WebP step is tools/webp_glb.py and the lightmap PNGs become world/lightmaps/*.webp, see the README)
-> render (the three review stills).

No coordinate is typed in here for the layout: the room, the colliders, the bed, desk, fridge, computer, window and door come from
blender/layout/apartment.json (node tools/blender/dump_layout.mjs apartment). A game point (x, y, z) is Blender (x, -z, y).
Only the art that the layout does not name (a lamp, a mug, a poster) is placed here, relative to those boxes.
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
LAYOUT = ROOT / "blender/layout/apartment.json"
TEX = ROOT / "blender/textures/apartment"
BLEND = ROOT / "blender/scenes/apartment.blend"
LM_DIR = ROOT / "blender/scenes/lightmaps"          # the bake's 8-bit PNGs (the WebPs in world/lightmaps/ are made from these)
GLB_RAW = ROOT / "blender/scenes/apartment_raw.glb"  # the exporter's output, before the WebP step
STILLS = ROOT / "docs/renders/apartment"
LM_URL = "world/lightmaps/apartment_{}.webp"        # the path the page reads from the material's `lightmap` custom property
TARGET_PX_M = 32.0                                   # texel density indoors (docs/BLENDER.md R1)
MARGIN_PX = 8

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 512, int)
DEVICE = arg("--device", "auto")
ENGINE = arg("--engine", "CYCLES")

L = json.loads(LAYOUT.read_text())
K = L["constants"]
COLLIDERS = {c["s"]: c for c in L["world"]["colliders"]}
HX, HZ = K["half"]
H = K["h"]


def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


# ---------------------------------------------------------------- materials
IMG_CACHE = {}


def image(fn, srgb=True):
    key = (fn, srgb)
    if key not in IMG_CACHE:
        im = bpy.data.images.load(str(TEX / fn))
        im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
        IMG_CACHE[key] = im
    return IMG_CACHE[key]


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, diff=None, rough_img=None, normal=None, emit=None, emit_img=None, alpha=None, tile=None):
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

    def tex(fn, srgb, sock):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = image(fn, srgb)
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        return n

    if diff:
        n = tex(diff, True, None)
        nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
    if rough_img:
        n = tex(rough_img, False, None)
        nt.links.new(n.outputs["Color"], bsdf.inputs["Roughness"])
    if normal:
        n = tex(normal, False, None)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    if emit_img is not None:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = emit_img
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        nt.links.new(n.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emit_img.get("strength", 1.0)
    if alpha is not None:
        bsdf.inputs["Alpha"].default_value = alpha
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    TILES[name] = tile or 1.0
    return m


MATS = {}
TILES = {}


def make_materials():
    M = MATS
    M["Floor_Wood"] = material("Floor_Wood", diff="old_wood_floor_diff_1k.jpg", rough_img="old_wood_floor_rough_1k.jpg", normal="old_wood_floor_nor_gl_1k.jpg", tile=1.2)
    M["Wall_Plaster"] = material("Wall_Plaster", diff="beige_wall_001_diff_1k.jpg", rough=0.92, tile=2.0)
    M["Ceiling_Paint"] = material("Ceiling_Paint", color=(0.62, 0.60, 0.54), rough=0.95)
    M["Trim_Paint"] = material("Trim_Paint", color=(0.55, 0.53, 0.47), rough=0.55)
    M["Door_Wood"] = material("Door_Wood", diff="dark_wood_diff_1k.jpg", rough=0.6, tile=0.9)
    M["Desk_Wood"] = material("Desk_Wood", diff="dark_wood_diff_1k.jpg", rough=0.55, tile=0.9)
    M["Bed_Linen"] = material("Bed_Linen", diff="rough_linen_diff_512.jpg", rough=0.95, tile=0.8)
    M["Pillow_Cotton"] = material("Pillow_Cotton", color=(0.72, 0.70, 0.65), rough=0.95)
    M["Bed_Throw"] = material("Bed_Throw", color=(0.30, 0.10, 0.07), rough=0.97)
    M["Rug_Wool"] = material("Rug_Wool", color=(0.16, 0.19, 0.17), rough=1.0)
    M["Fridge_Enamel"] = material("Fridge_Enamel", color=(0.62, 0.62, 0.55), rough=0.3, metal=0.0)
    M["Metal_Dark"] = material("Metal_Dark", color=(0.035, 0.035, 0.04), rough=0.4, metal=0.8)
    M["Metal_Brass"] = material("Metal_Brass", color=(0.55, 0.38, 0.12), rough=0.4, metal=0.9)
    M["Plastic_Black"] = material("Plastic_Black", color=(0.02, 0.02, 0.025), rough=0.35)
    M["Ceramic_White"] = material("Ceramic_White", color=(0.65, 0.65, 0.6), rough=0.2)
    M["Paper"] = material("Paper", color=(0.7, 0.68, 0.6), rough=0.9)
    M["Radiator_Paint"] = material("Radiator_Paint", color=(0.5, 0.5, 0.46), rough=0.5)
    M["Lamp_Shade"] = material("Lamp_Shade", color=(0.08, 0.2, 0.18), rough=0.5, metal=0.2)
    M["Shade_Paper"] = material("Shade_Paper", color=(0.52, 0.46, 0.34), rough=0.8)
    M["Lamp_Emit"] = material("Lamp_Emit", color=(1, 0.8, 0.55), rough=0.5, emit=((1.0, 0.72, 0.4), 12.0))
    M["Screen_Standin"] = material("Screen_Standin", color=(0.02, 0.04, 0.06), rough=0.2, emit=((0.1, 0.2, 0.32), 0.2))
    M["Window_Glass"] = material("Window_Glass", color=(0.8, 0.9, 1.0), rough=0.05, alpha=0.12)


# ---------------------------------------------------------------- geometry helpers (all built in world space, identity object transforms)
def new_bm():
    return bmesh.new()


def cube(bm, gmin, gmax):
    a, b = B(gmin), B(gmax)
    c = (a + b) / 2
    s = Vector((abs(a.x - b.x), abs(a.y - b.y), abs(a.z - b.z)))
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((s.x, s.y, s.z, 1.0)))


def soft_cube(bm, gmin, gmax, r=0.04, seg=3):
    n0 = len(bm.verts)
    cube(bm, gmin, gmax)
    geo = [v for v in bm.verts if v.index >= n0]
    edges = list({e for v in geo for e in v.link_edges})
    bmesh.ops.bevel(bm, geom=geo + edges, offset=r, offset_type="OFFSET", segments=seg, profile=0.5, affect="EDGES")


def cyl(bm, p0, p1, r0, r1=None, seg=16, cap=True):
    a, b = B(p0), B(p1)
    d = b - a
    q = d.to_track_quat("Z", "Y")
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                          matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())


def sphere(bm, p, r, seg=12):
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2 + 1, radius=r, matrix=Matrix.Translation(B(p)))


def quad(bm, p0, p1, p2, p3):
    vs = [bm.verts.new(B(p)) for p in (p0, p1, p2, p3)]
    bm.faces.new(vs)


def box_uv(bm, tile):
    """UV0: box projection in metres / tile, from world positions, so a texture runs on across the pieces of a wall."""
    uvl = bm.loops.layers.uv.verify() if not bm.loops.layers.uv.get("UVMap") else bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y            # back to game axes
            if ax == 0:
                u, v = gz, gy
            elif ax == 1:
                u, v = gx, gy
            else:
                u, v = gx, gz
            lp[uvl].uv = (u / tile, v / tile)


def finish(name, bm, mat, coll, smooth=False, tile=None, sharp_deg=35):
    for e in bm.edges:
        if smooth and len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) < math.radians(sharp_deg)
        else:
            e.smooth = not (len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(1))
    for f in bm.faces:
        f.smooth = smooth
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if not bm.loops.layers.uv.get("UVMap"):
        bm.loops.layers.uv.new("UVMap")
    box_uv(bm, tile or TILES[mat])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


ART = STANDIN = None


def part(name, mat, build, smooth=False, tile=None, coll=None):
    bm = new_bm()
    build(bm)
    return finish(name, bm, mat, coll or ART, smooth, tile)


# ---------------------------------------------------------------- the art
def build_shell():
    """The room's six slabs, straight from the collision file's boxes (Floor_*, Ceiling_*, Wall_*), so art and colliders agree."""
    w = K["window"]
    wy0, wy1 = w["y"]
    wz0, wz1 = w["z"]
    for s, c in COLLIDERS.items():
        mn, mx = c["min"], c["max"]
        if s.startswith("Floor"):
            part(s, "Floor_Wood", lambda bm: cube(bm, mn, mx))
        elif s.startswith("Ceiling"):
            part(s, "Ceiling_Paint", lambda bm: cube(bm, mn, mx))
        elif s == "Wall_E":
            def e(bm):
                cube(bm, (mn[0], mn[1], mn[2]), (mx[0], wy0, mx[2]))             # below the window
                cube(bm, (mn[0], wy1, mn[2]), (mx[0], mx[1], mx[2]))             # above it
                cube(bm, (mn[0], wy0, mn[2]), (mx[0], wy1, wz0))                 # beside it, north
                cube(bm, (mn[0], wy0, wz1), (mx[0], wy1, mx[2]))                 # beside it, south
            part(s, "Wall_Plaster", e)
        elif s.startswith("Wall_"):
            part(s, "Wall_Plaster", lambda bm: cube(bm, mn, mx))


def build_trim():
    dx = K["door"]["at"][0]
    t, h = 0.02, 0.12

    def skirt(bm):
        cube(bm, (-HX, 0, -HZ), (HX, h, -HZ + t))                                   # north
        cube(bm, (-HX, 0, HZ - t), (dx - 0.5, h, HZ))                                # south, either side of the door
        cube(bm, (dx + 0.5, 0, HZ - t), (HX, h, HZ))
        cube(bm, (-HX, 0, -HZ), (-HX + t, h, HZ))                                    # west
        cube(bm, (HX - t, 0, -HZ), (HX, h, HZ))                                      # east
    part("Trim_Skirting", "Trim_Paint", skirt)

    # the door: a leaf and a frame inset 5 cm from the south wall's inner face; it does not open (the page's door prompt is code)
    def frame(bm):
        w, d = 0.45, 0.045
        cube(bm, (dx - w - 0.07, 0, HZ - d), (dx - w, 2.17, HZ))
        cube(bm, (dx + w, 0, HZ - d), (dx + w + 0.07, 2.17, HZ))
        cube(bm, (dx - w - 0.07, 2.1, HZ - d), (dx + w + 0.07, 2.17, HZ))
    part("Trim_DoorFrame", "Trim_Paint", frame)
    part("Door_Leaf", "Door_Wood", lambda bm: cube(bm, (dx - 0.45, 0, HZ - 0.04), (dx + 0.45, 2.1, HZ - 0.005)))

    def handle(bm):
        cube(bm, (dx + 0.28, 0.97, HZ - 0.045), (dx + 0.36, 1.0, HZ - 0.03))
        cube(bm, (dx + 0.28, 0.93, HZ - 0.04), (dx + 0.31, 1.04, HZ - 0.03))
        cube(bm, (dx + 0.28, 1.12, HZ - 0.04), (dx + 0.33, 1.17, HZ - 0.03))        # deadbolt rose
    part("Door_Handle", "Metal_Brass", handle)

    # the window: a frame lining the reveal, a mullion, a sill board, the glass (a code-toggled pane: Window_Glass) and the street behind
    w = K["window"]
    wy0, wy1 = w["y"]
    wz0, wz1 = w["z"]
    zc = (wz0 + wz1) / 2

    def wframe(bm):
        x0, x1, f = HX + 0.03, HX + 0.12, 0.06
        cube(bm, (x0, wy1 - f, wz0), (x1, wy1, wz1))
        cube(bm, (x0, wy0, wz0), (x1, wy0 + f, wz1))
        cube(bm, (x0, wy0, wz0), (x1, wy1, wz0 + f))
        cube(bm, (x0, wy0, wz1 - f), (x1, wy1, wz1))
        cube(bm, (x0 + 0.01, wy0, zc - 0.025), (x0 + 0.05, wy1, zc + 0.025))
    part("Trim_WindowFrame", "Trim_Paint", wframe)
    part("Trim_Sill", "Trim_Paint", lambda bm: cube(bm, (HX - 0.09, wy0 - 0.03, wz0 - 0.06), (HX + 0.03, wy0 + 0.01, wz1 + 0.06)))   # the sill board, 9 cm proud: low, so passable by the rule
    part("Window_Pane", "Window_Glass", lambda bm: quad(bm, (HX + 0.075, wy0 + 0.06, wz0 + 0.06), (HX + 0.075, wy0 + 0.06, wz1 - 0.06), (HX + 0.075, wy1 - 0.06, wz1 - 0.06), (HX + 0.075, wy1 - 0.06, wz0 + 0.06)), tile=1.0)


def build_bed():
    b = K["bed"]
    x0, y0, z0 = b["min"]
    x1, y1, z1 = b["max"]
    wood = "Desk_Wood"

    def frame(bm):
        cube(bm, (x0, 0.12, z0), (x1, 0.30, z1))                                     # the base
        for x in (x0, x1 - 0.08):
            for z in (z0, z1 - 0.08):
                cube(bm, (x, 0, z), (x + 0.08, 0.12, z + 0.08))                       # four feet
        cube(bm, (x0, 0.30, z0), (x1, 1.05, z0 + 0.06))                               # the headboard
        cube(bm, (x0, 0.30, z1 - 0.05), (x1, 0.42, z1))                               # the foot rail
    part("Bed_Frame", wood, frame)
    part("Bed_Mattress", "Bed_Linen", lambda bm: soft_cube(bm, (x0 + 0.03, 0.30, z0 + 0.06), (x1 - 0.03, 0.50, z1 - 0.04), 0.035), smooth=True)
    part("Bed_Blanket", "Bed_Throw", lambda bm: soft_cube(bm, (x0 + 0.02, 0.495, z0 + 0.80), (x1 - 0.02, 0.555, z1 - 0.02), 0.025), smooth=True)

    def pillows(bm):
        soft_cube(bm, (x0 + 0.20, 0.50, z0 + 0.10), (x0 + 0.85, 0.60, z0 + 0.62), 0.04)
        soft_cube(bm, (x0 + 1.05, 0.50, z0 + 0.10), (x0 + 1.75, 0.595, z0 + 0.62), 0.04)
    part("Bed_Pillows", "Pillow_Cotton", pillows, smooth=True)


def build_desk():
    d = K["desk"]
    x0, y0, z0 = d["min"]
    x1, y1, z1 = d["max"]
    cx = K["computer"]["at"][0]

    def desk(bm):
        cube(bm, (x0, y1 - 0.04, z0), (x1, y1, z1))                                  # the top
        for x in (x0 + 0.02, x1 - 0.07):
            for z in (z0 + 0.03, z1 - 0.08):
                cube(bm, (x, 0, z), (x + 0.05, y1 - 0.04, z + 0.05))
        cube(bm, (x0 + 0.07, 0.28, z0 + 0.01), (x1 - 0.07, y1 - 0.04, z0 + 0.03))     # the modesty panel
        cube(bm, (x0 + 0.02, 0.05, z0 + 0.03), (x0 + 0.46, y1 - 0.04, z1 - 0.03))     # the drawer unit
    part("Desk_Body", "Desk_Wood", desk)

    def drawers(bm):
        for i in range(3):
            ya = 0.1 + i * 0.21
            cube(bm, (x0 + 0.05, ya, z1 - 0.045), (x0 + 0.43, ya + 0.18, z1 - 0.025))
    part("Desk_Drawers", "Door_Wood", drawers)
    part("Desk_Pulls", "Metal_Brass", lambda bm: [cube(bm, (x0 + 0.20, 0.17 + i * 0.21, z1 - 0.075), (x0 + 0.28, 0.20 + i * 0.21, z1 - 0.045)) for i in range(3)])

    # the computer's art: a monitor shell, stand and keyboard. The screen is code (the UI opens on F): only a hidden stand-in sits where it goes.
    sy0, sy1, sz = y1 + 0.10, y1 + 0.52, z0 + 0.22
    def monitor(bm):
        cube(bm, (cx - 0.33, sy0 - 0.03, sz - 0.06), (cx + 0.33, sy1 + 0.03, sz - 0.01))                                       # back shell
        for a, b_ in (((cx - 0.33, sy0 - 0.03, sz - 0.01), (cx + 0.33, sy0 + 0.0, sz + 0.02)), ((cx - 0.33, sy1, sz - 0.01), (cx + 0.33, sy1 + 0.03, sz + 0.02)),
                      ((cx - 0.33, sy0, sz - 0.01), (cx - 0.30, sy1, sz + 0.02)), ((cx + 0.30, sy0, sz - 0.01), (cx + 0.33, sy1, sz + 0.02))):
            cube(bm, a, b_)                                                                                                    # the bezel
        cube(bm, (cx - 0.04, y1, sz - 0.1), (cx + 0.04, sy0, sz - 0.04))                                                       # neck
        cube(bm, (cx - 0.17, y1, sz - 0.2), (cx + 0.17, y1 + 0.012, sz + 0.02))                                                # foot
    part("Computer_Shell", "Plastic_Black", monitor)
    def keys(bm):
        cube(bm, (cx - 0.26, y1, z0 + 0.58), (cx + 0.24, y1 + 0.022, z0 + 0.78))                                               # keyboard
        cube(bm, (cx + 0.34, y1, z0 + 0.62), (cx + 0.40, y1 + 0.03, z0 + 0.74))                                                # mouse
    part("Desk_Keyboard", "Plastic_Black", keys)

    def standin(bm):
        quad(bm, (cx - 0.30, sy0, sz + 0.0205), (cx + 0.30, sy0, sz + 0.0205), (cx + 0.30, sy1, sz + 0.0205), (cx - 0.30, sy1, sz + 0.0205))
    part("standin_screen", "Screen_Standin", standin, coll=STANDIN, tile=1.0)

    # things on the desk
    part("Desk_Mug", "Ceramic_White", lambda bm: cyl(bm, (x1 - 0.30, y1, z0 + 0.45), (x1 - 0.30, y1 + 0.10, z0 + 0.45), 0.043, 0.04, 20), smooth=True)
    def books(bm):
        cube(bm, (x1 - 0.32, y1, z0 + 0.08), (x1 - 0.07, y1 + 0.045, z0 + 0.38))
        cube(bm, (x1 - 0.31, y1 + 0.045, z0 + 0.09), (x1 - 0.09, y1 + 0.08, z0 + 0.36))
    part("Desk_Books", "Pillow_Cotton", books)
    part("Desk_Papers", "Paper", lambda bm: cube(bm, (cx + 0.45, y1, z0 + 0.55), (cx + 0.70, y1 + 0.012, z0 + 0.85)))

    # the desk lamp: a heavy base, two arms, a shade; the bulb is the light (Lamp_Emit) and the spot light of the bake sits on it
    bx, bz = x0 + 0.62, z0 + 0.35
    top = (bx + 0.10, y1 + 0.46, bz + 0.15)
    p1 = (bx - 0.02, y1 + 0.27, bz + 0.05)
    def lamp(bm):
        cyl(bm, (bx, y1, bz), (bx, y1 + 0.03, bz), 0.085, 0.075, 24)
        cyl(bm, (bx, y1 + 0.03, bz), p1, 0.011, 0.011, 8)
        cyl(bm, p1, top, 0.009, 0.009, 8)
        sphere(bm, p1, 0.02, 8)
    part("Desk_Lamp_Arm", "Metal_Dark", lamp, smooth=True)
    sh0 = top
    sh1 = (top[0] + 0.07, top[1] - 0.10, top[2] + 0.07)
    part("Desk_Lamp_Shade", "Lamp_Shade", lambda bm: cyl(bm, sh0, sh1, 0.03, 0.095, 24, cap=False), smooth=True)
    bulb = ((sh0[0] + sh1[0]) / 2 + 0.01, (sh0[1] + sh1[1]) / 2 - 0.02, (sh0[2] + sh1[2]) / 2 + 0.01)
    part("Desk_Lamp_Bulb", "Lamp_Emit", lambda bm: sphere(bm, bulb, 0.026, 12), smooth=True)
    return {"lamp_bulb": bulb, "lamp_dir": (sh1[0] - sh0[0], sh1[1] - sh0[1], sh1[2] - sh0[2])}


def build_chair():
    cx = K["computer"]["at"][0]
    z = K["desk"]["max"][2]

    def chair(bm):
        n0 = len(bm.verts)
        x0, x1, z0, z1 = cx - 0.24, cx + 0.24, z + 0.05, z + 0.50
        soft_cube(bm, (x0, 0.44, z0), (x1, 0.49, z1), 0.012, 2)
        soft_cube(bm, (x0, 0.50, z1 - 0.04), (x1, 0.92, z1), 0.02, 2)                 # the back
        for xx in (x0 + 0.03, x1 - 0.05):
            for zz in (z0 + 0.03, z1 - 0.05):
                cube(bm, (xx, 0, zz), (xx + 0.025, 0.44, zz + 0.025))
        geo = [v for v in bm.verts]
        bmesh.ops.rotate(bm, cent=B((cx, 0, z + 0.3)), matrix=Matrix.Rotation(math.radians(-14), 3, "Z"), verts=geo)
    part("decor_chair", "Door_Wood", chair, tile=0.9)


def build_fridge():
    f = K["fridge"]
    x0, y0, z0 = f["min"]
    x1, y1, z1 = f["max"]

    def body(bm):
        cube(bm, (x0, 0.04, z0), (x1 - 0.02, y1, z1))                                  # the cabinet
        cube(bm, (x0 + 0.04, 0, z0 + 0.04), (x1 - 0.06, 0.04, z1 - 0.04))               # the plinth
        cube(bm, (x1 - 0.02, 1.22, z0 + 0.01), (x1, y1 - 0.02, z1 - 0.01))              # freezer door
        cube(bm, (x1 - 0.02, 0.06, z0 + 0.01), (x1, 1.19, z1 - 0.01))                   # fridge door
    part("Fridge_Body", "Fridge_Enamel", body)
    part("Fridge_Handles", "Metal_Dark", lambda bm: [cube(bm, (x1, a, z0 + 0.08), (x1 + 0.025, b, z0 + 0.12)) for a, b in ((1.30, 1.52), (0.95, 1.12))])


def build_window_street():
    w = K["window"]
    # a radiator under the window, and a radiator pipe: passable props (decor_), the collision file has no box for them
    part("decor_radiator", "Radiator_Paint", lambda bm: [cube(bm, (HX - 0.10 + 0.0, 0.18, w["z"][0] + 0.1 + i * 0.09), (HX - 0.01, 0.78, w["z"][0] + 0.15 + i * 0.09)) for i in range(11)])
    part("decor_radiator_pipe", "Radiator_Paint", lambda bm: cyl(bm, (HX - 0.05, 0.0, w["z"][0] + 0.06), (HX - 0.05, 0.25, w["z"][0] + 0.06), 0.012, 0.012, 8))


def build_wall_dressing(lamp):
    """The worn parts: a damp stain by the window, a poster over the bed, a rug, a ceiling lamp, switch and socket."""
    dx = K["door"]["at"][0]
    # a rug (passable)
    part("decor_rug", "Rug_Wool", lambda bm: cube(bm, (-0.7, 0.0, -0.1), (1.0, 0.012, 1.5)), tile=1.0)
    # the ceiling lamp: a flat paper shade; the light is Lamp_Emit inside
    part("Ceiling_Lamp_Rose", "Trim_Paint", lambda bm: cyl(bm, (0, H - 0.03, 0), (0, H, 0), 0.09, 0.09, 24), smooth=True)
    part("Ceiling_Lamp_Cord", "Plastic_Black", lambda bm: cyl(bm, (0, H - 0.25, 0), (0, H - 0.03, 0), 0.006, 0.006, 6))
    part("Ceiling_Lamp_Shade", "Shade_Paper", lambda bm: cyl(bm, (0, H - 0.42, 0), (0, H - 0.25, 0), 0.22, 0.04, 28, cap=False), smooth=True)
    part("Ceiling_Lamp_Bulb", "Lamp_Emit", lambda bm: sphere(bm, (0, H - 0.34, 0), 0.045, 14), smooth=True)
    # a switch by the door and a socket by the desk (flat plates, 1.5 cm proud of the wall)
    part("Plate_Switch", "Trim_Paint", lambda bm: cube(bm, (dx - 0.72, 1.18, HZ - 0.015), (dx - 0.64, 1.28, HZ)))
    part("Plate_Socket", "Trim_Paint", lambda bm: cube(bm, (-HX, 0.3, 0.2), (-HX + 0.015, 0.38, 0.3)))




# ---------------------------------------------------------------- generated images: the street behind the window, a poster, a damp stain (own work, numpy, fixed seeds)
def rs(a, h, w):
    ys, xs = np.linspace(0, a.shape[0] - 1, h), np.linspace(0, a.shape[1] - 1, w)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, a.shape[0] - 1), np.minimum(x0 + 1, a.shape[1] - 1)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    return (a[y0][:, x0] * (1 - fy) * (1 - fx) + a[y0][:, x1] * (1 - fy) * fx + a[y1][:, x0] * fy * (1 - fx) + a[y1][:, x1] * fy * fx)


def vnoise(h, w, rng, octaves=5, base=4):
    out, amp, tot = np.zeros((h, w)), 1.0, 0.0
    for k in range(octaves):
        n = base * 2 ** k + 1
        out += amp * rs(rng.random((n, n)), h, w)
        tot += amp
        amp *= 0.5
    return out / tot


def blur(a, r, passes=3):
    n = 2 * r + 1
    for ax in (0, 1):
        for _ in range(passes):
            pad = [(0, 0)] * a.ndim
            pad[ax] = (r + 1, r)
            c = np.cumsum(np.pad(a, pad, mode="edge"), axis=ax)
            L = c.shape[ax]
            a = (np.take(c, range(n, L), axis=ax) - np.take(c, range(0, L - n), axis=ax)) / n
    return a


def street_pixels():
    """The street across from the window, at dusk: a run of brick and render facades with a mix of lit and dark windows, on a plane 40 x 16 m."""
    W, Hh = 2048, 1024
    ppu, ppv = W / BACKDROP[0], Hh / BACKDROP[1]
    y_top = BACKDROP[2] + BACKDROP[1] / 2
    rng = np.random.default_rng(11)
    yy = y_top - (np.arange(Hh) + 0.5) / ppv
    t = np.clip((yy - 6.0) / 6.0, 0, 1)[:, None, None]
    img = np.zeros((Hh, W, 3), np.float32)
    img[:] = np.array([0.70, 0.40, 0.30]) * (1 - t) + np.array([0.07, 0.09, 0.22]) * t
    pal = [(0.33, 0.16, 0.12), (0.36, 0.30, 0.25), (0.26, 0.27, 0.31), (0.30, 0.20, 0.15), (0.38, 0.33, 0.22)]
    z0w = -BACKDROP[0] / 2
    z = z0w
    mask = np.zeros((Hh, W), bool)
    while z < -z0w:
        w = rng.uniform(4.0, 9.0)
        roof = rng.uniform(7.0, 10.8)
        if rng.random() < 0.12:
            z += rng.uniform(0.8, 1.8)                              # a gap between buildings
            continue
        a, b = int((z - z0w) * ppu), min(W, int((z + w - z0w) * ppu))
        rows = yy < roof
        col = np.array(pal[rng.integers(len(pal))]) * rng.uniform(0.7, 1.0) * 0.6
        img[rows, a:b] = col
        mask[rows, a:b] = True
        for wz in np.arange(z + 1.0, z + w - 1.5, 2.5):
            for wy in np.arange(-5.0, roof - 1.6, 3.0):
                r0, r1 = int((y_top - (wy + 1.7)) * ppv), int((y_top - wy) * ppv)
                c0, c1 = int((wz - z0w) * ppu), int((wz + 1.2 - z0w) * ppu)
                if r0 < 0 or c1 > W or r1 > Hh:
                    continue
                p = rng.random()
                if p < 0.30:
                    c = np.array([1.0, 0.72, 0.38]) * rng.uniform(0.55, 1.0)
                elif p < 0.38:
                    c = np.array([0.45, 0.65, 1.0]) * rng.uniform(0.4, 0.8)
                else:
                    c = np.array([0.05, 0.065, 0.10])
                img[r0:r1, c0:c1] = c
                m = c0 + (c1 - c0) // 2
                img[r0:r1, m - 1:m + 1] *= 0.35                     # the glazing bar
        z += w
    n = vnoise(Hh, W, rng, 6, 8)
    img[mask] *= (0.75 + 0.5 * n[mask])[:, None]
    img = blur(img, 2)
    glow = np.exp(-np.clip(yy + 4, 0, 16) / 5.0)[:, None, None] * np.array([0.30, 0.16, 0.08])      # the street's sodium glow, rising from below
    return np.clip(img + glow * 0.5, 0, 1).astype(np.float32)


def poster_pixels():
    h, w = 384, 256
    rng = np.random.default_rng(5)
    y = np.linspace(0, 1, h)[:, None]
    img = np.zeros((h, w, 3), np.float32)
    img[:] = np.array([0.55, 0.22, 0.28]) * (1 - y[..., None]) + np.array([0.95, 0.62, 0.32]) * y[..., None]
    yy, xx = np.mgrid[0:h, 0:w]
    img[((xx - 128) ** 2 + (yy - 190) ** 2) < 46 ** 2] = (0.98, 0.9, 0.62)                          # a low sun
    x = 0
    while x < w:                                                                                    # a skyline
        bw, bh = int(rng.integers(18, 40)), int(rng.integers(70, 190))
        img[h - bh:, x:x + bw] = (0.10, 0.07, 0.13)
        x += bw
    border = 12
    img[:border] = img[-border:] = img[:, :border] = img[:, -border:] = (0.80, 0.77, 0.68)
    return np.clip(blur(img, 1, 1) + (rng.random((h, w, 1)) - 0.5) * 0.03, 0, 1).astype(np.float32)


def stain_pixels():
    S = 512
    rng = np.random.default_rng(3)
    yy, xx = (np.mgrid[0:S, 0:S] - S / 2) / (S / 2)
    r = np.sqrt(xx ** 2 + (yy * 1.25) ** 2) + (vnoise(S, S, rng, 5, 4) - 0.5) * 0.9
    a = np.clip(1.0 - r, 0, 1) ** 0.8
    edge = np.clip(1 - np.abs(r - 0.62) * 9, 0, 1) * 0.5                                            # the tide line
    alpha = np.clip(a * 0.30 + edge * 0.12, 0, 0.32)
    rgb = np.zeros((S, S, 4), np.float32)
    rgb[..., :3] = np.array([0.34, 0.27, 0.15])
    rgb[..., 3] = alpha
    return rgb


def mk_image(name, arr, srgb=True):
    """A packed image from a float array (rows top to bottom): written as a PNG first, because a generated image forgets its pixels when the file is saved."""
    h, w = arr.shape[:2]
    has_a = arr.shape[2] == 4
    im = bpy.data.images.new(name + "_gen", w, h, alpha=has_a)
    im.alpha_mode = "STRAIGHT"
    im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"           # before the pixels: changing it regenerates the image
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :arr.shape[2]] = arr
    im.pixels.foreach_set(np.flipud(rgba).ravel())
    gen = Path(os.environ.get("TEMP", "/tmp")) / "farway_apartment_gen"
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
    return out


def make_generated():
    street = mk_image("Street_Dusk", street_pixels())
    street["strength"] = 2.2
    poster = mk_image("Poster_Dusk", poster_pixels())
    stain = mk_image("Wall_Stain", stain_pixels())
    return street, poster, stain


def textured(name, im, emit=False, alpha=False, rough=0.9, tile=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out, bsdf, tx, uv = (nt.nodes.new(t) for t in ("ShaderNodeOutputMaterial", "ShaderNodeBsdfPrincipled", "ShaderNodeTexImage", "ShaderNodeUVMap"))
    uv.uv_map = "UVMap"
    tx.image = im
    nt.links.new(uv.outputs["UV"], tx.inputs["Vector"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Roughness"].default_value = rough
    if emit:
        bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
        nt.links.new(tx.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = im.get("strength", 1.0)
    else:
        nt.links.new(tx.outputs["Color"], bsdf.inputs["Base Color"])
    if alpha:
        nt.links.new(tx.outputs["Alpha"], bsdf.inputs["Alpha"])
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    TILES[name] = tile
    return m


# ---------------------------------------------------------------- panels flat on a wall, the street, the lights
RIGHT = {"+x": (0, 0, -1), "-x": (0, 0, 1), "+z": (1, 0, 0), "-z": (-1, 0, 0)}   # a viewer looking at a surface whose normal is +x, -x, ...: the game direction of their right hand


def panel(name, mat, centre, normal, w, h, flip_u=False, coll=None):
    """A flat quad facing `normal` (a game axis such as "+x": the wall's inward normal), w wide, h tall, UV 0..1 with the picture upright."""
    r = Vector(RIGHT[normal])
    up = Vector((0, 1, 0))
    c = Vector(centre)
    pts = [c - r * w / 2 - up * h / 2, c + r * w / 2 - up * h / 2, c + r * w / 2 + up * h / 2, c - r * w / 2 + up * h / 2]
    bm = new_bm()
    quad(bm, *[tuple(p) for p in pts])
    bm.faces.ensure_lookup_table()
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp, uv in zip(bm.faces[0].loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = (1 - uv[0] if flip_u else uv[0], uv[1])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(name, me)
    (coll or ART).objects.link(ob)
    return ob


def build_dressing_decals():
    e = 0.003
    panel("Decal_Stain_W", "Decal_Grime", (-HX + e, 2.15, 1.35), "+x", 1.7, 1.15)
    panel("Decal_Stain_N", "Decal_Grime", (1.9, 2.15, -HZ + e), "+z", 1.6, 1.0, flip_u=True)
    # the poster over the bed, framed
    pxc, pyc, pw, ph = (K["bed"]["min"][0] + K["bed"]["max"][0]) / 2 - 0.2, 1.55, 0.55, 0.78
    panel("Poster", "Poster_Print", (pxc, pyc, -HZ + 0.025), "+z", pw, ph)

    def fr(bm):
        t, d = 0.03, 0.025
        cube(bm, (pxc - pw / 2 - t, pyc - ph / 2 - t, -HZ), (pxc + pw / 2 + t, pyc - ph / 2, -HZ + d))
        cube(bm, (pxc - pw / 2 - t, pyc + ph / 2, -HZ), (pxc + pw / 2 + t, pyc + ph / 2 + t, -HZ + d))
        cube(bm, (pxc - pw / 2 - t, pyc - ph / 2, -HZ), (pxc - pw / 2, pyc + ph / 2, -HZ + d))
        cube(bm, (pxc + pw / 2, pyc - ph / 2, -HZ), (pxc + pw / 2 + t, pyc + ph / 2, -HZ + d))
    part("Poster_Frame", "Desk_Wood", fr)


BACKDROP = (40.0, 16.0, 4.0)        # width (z), height (y), centre height: a plane 12 m past the east wall; the window shows ~ +-15 m of it from a step away


def build_street(bx=12.0):
    """The backdrop plane the window looks onto: far enough that the parallax is gentle, large enough to fill the window from anywhere in the room."""
    panel("decor_backdrop", "Backdrop_Street", (bx, BACKDROP[2], 0.0), "-x", BACKDROP[0], BACKDROP[1])


CEIL_W, DESK_W = 220.0, 45.0


def add_lights(lamp):
    lights = bpy.data.collections.new("Lights")
    bpy.context.scene.collection.children.link(lights)

    def light(name, kind, pos, energy, color, size):
        d = bpy.data.lights.new(name, kind)
        d.energy, d.color = energy, color
        d.shadow_soft_size = size
        ob = bpy.data.objects.new(name, d)
        ob.location = B(pos)
        lights.objects.link(ob)
        return ob, d
    light("Ceiling_Light", "POINT", (0, H - 0.35, 0), CEIL_W, (1.0, 0.80, 0.60), 0.07)
    ob, d = light("Desk_Light", "SPOT", lamp["lamp_bulb"], DESK_W, (1.0, 0.66, 0.38), 0.025)
    d.spot_size, d.spot_blend = math.radians(100), 0.55
    ob.rotation_euler = B(lamp["lamp_dir"]).to_track_quat("-Z", "Y").to_euler()


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("Night")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.01, 0.012, 0.02, 1)
    bg.inputs["Strength"].default_value = 1.0


def ensure_marker():
    """A 20 cm marker cube at the arrival point (docs/BLENDER.md, contract 3), kept in Standins and never exported or rendered."""
    st = bpy.data.collections["Standins"]
    ob = bpy.data.objects.get("standin_arrival_marker")
    if ob is None:
        me = bpy.data.meshes.new("standin_arrival_marker")
        bm = new_bm()
        a = K["arrive"]
        cube(bm, (a[0] - 0.1, a[1], a[2] - 0.1), (a[0] + 0.1, a[1] + 0.2, a[2] + 0.1))
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("standin_arrival_marker", me)
        st.objects.link(ob)
    ob.hide_render = True
    return ob


def stage_axes():
    """The axes check: export the marker alone through the glTF exporter and read back where it landed. A game point (x, y, z) must come out as (x, y, z)."""
    import struct
    ob = ensure_marker()
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    path = stage_work() / "axes_marker.glb"
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_yup=True, export_apply=True, export_materials="NONE")
    b = path.read_bytes()
    j = json.loads(b[20:20 + struct.unpack("<I", b[12:16])[0]])
    acc = j["accessors"][j["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    node = j["nodes"][0]
    off = node.get("translation", [0, 0, 0])
    lo = [acc["min"][i] + off[i] for i in range(3)]
    hi = [acc["max"][i] + off[i] for i in range(3)]
    centre = [(lo[i] + hi[i]) / 2 for i in range(3)]
    a = K["arrive"]
    want = [a[0], a[1] + 0.1, a[2]]
    bl = sum((v.co for v in ob.data.vertices), Vector()) / len(ob.data.vertices)          # the marker's centre in Blender coordinates (the object sits at the origin)
    print(f"AXES blender centre {tuple(round(v, 3) for v in bl)} (x, -z, y of the game point {tuple(want)})")
    print(f"AXES glTF centre {tuple(round(v, 3) for v in centre)}, game point {tuple(want)}")
    assert all(abs(centre[i] - want[i]) < 1e-4 for i in range(3)), "the exporter's axes disagree with (x, -z, y)"
    assert abs(bl.x - want[0]) < 1e-4 and abs(bl.y + want[2]) < 1e-4 and abs(bl.z - want[1]) < 1e-4
    print("AXES PASS: game (x, y, z) = Blender (x, -z, y) = glTF (x, y, z)")


def build_all():
    global ART, STANDIN
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.lights, bpy.data.cameras):
        for d in list(coll):
            coll.remove(d)
    IMG_CACHE.clear()
    MATS.clear()
    TILES.clear()
    ART = bpy.data.collections.new("Art")
    STANDIN = bpy.data.collections.new("Standins")
    sc = bpy.context.scene
    sc.collection.children.link(ART)
    sc.collection.children.link(STANDIN)
    street, poster, stain = make_generated()
    make_materials()
    MATS["Backdrop_Street"] = textured("Backdrop_Street", street, emit=True, tile=1.0)
    MATS["Poster_Print"] = textured("Poster_Print", poster, rough=0.6)
    MATS["Decal_Grime"] = textured("Decal_Grime", stain, alpha=True)
    build_shell()
    build_trim()
    build_bed()
    lamp = build_desk()
    build_chair()
    build_fridge()
    build_window_street()
    build_wall_dressing(lamp)
    build_dressing_decals()
    build_street()
    add_lights(lamp)
    setup_world()
    ensure_marker()
    return lamp


# ---------------------------------------------------------------- bake
SHELL_MATS = ["Floor_Wood", "Wall_Plaster", "Ceiling_Paint", "Trim_Paint", "Decal_Grime", "Poster_Print", "Radiator_Paint"]
CONTENT_MATS = ["Desk_Wood", "Door_Wood", "Bed_Linen", "Pillow_Cotton", "Bed_Throw", "Rug_Wool", "Fridge_Enamel", "Metal_Dark", "Metal_Brass", "Plastic_Black", "Ceramic_White", "Paper", "Lamp_Shade", "Shade_Paper"]
GROUPS = [SHELL_MATS, CONTENT_MATS]
SHELL_PREFIX = ("Wall_", "Floor_", "Ceiling_")


def trim_outside(bm):
    """Drop the faces of a shell slab that look away from the room (the outer skin of the walls, the floor's underside, the ceiling's top): never seen, and they would cost lightmap texels."""
    centre = Vector((0, 0, H / 2))
    bad = [f for f in bm.faces if f.normal.dot(f.calc_center_median() - centre) > 1e-4]
    bmesh.ops.delete(bm, geom=bad, context="FACES")


def stage_work():
    d = Path(arg("--work", str(Path(os.environ.get("TEMP", "/tmp")) / "farway_apartment")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup_cycles(samples, bake=False):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = samples
    cy.use_adaptive_sampling = False
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces, cy.transmission_bounces, cy.transparent_max_bounces = 10, 8, 4, 8, 16
    cy.use_denoising = not bake
    prefs = bpy.context.preferences.addons["cycles"].preferences
    gpu = False
    if DEVICE != "cpu":
        for t in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
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
    print("CYCLES device:", cy.device, [d.name for d in prefs.devices if d.use])
    return gpu


def make_export_objects():
    art = bpy.data.collections["Art"]
    if "Export" in bpy.data.collections:
        for o in list(bpy.data.collections["Export"].objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(bpy.data.collections["Export"])
    exp = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(exp)
    by_mat = {}
    for ob in art.objects:
        assert len(ob.data.materials) == 1, ob.name
        mname = ob.data.materials[0].name
        bm = by_mat.setdefault(mname, bmesh.new())
        tmp = bmesh.new()
        tmp.from_mesh(ob.data)
        if ob.name in COLLIDERS and ob.name.startswith(SHELL_PREFIX):          # the slabs that came from the collision file
            trim_outside(tmp)
        me = bpy.data.meshes.new("tmp")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    out = {}
    for mname, bm in by_mat.items():
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        me = bpy.data.meshes.new(mname)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(bpy.data.materials[mname])
        ob = bpy.data.objects.new(mname, me)
        exp.objects.link(ob)
        out[mname] = ob
    return out


def select_only(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
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


def lightmap_uv(objs):
    """One shared atlas for `objs`: smart-project islands, equal texel density, packed with MARGIN_PX; the smallest square page that gives >= 30 px/m."""
    for o in objs:
        uvs = o.data.uv_layers
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.new(name="lightmap")
        uvs.active = uvs["lightmap"]
        uvs["lightmap"].active_render = True
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    chosen = None
    for S in (512, 640, 768, 896, 1024, 1536, 2048):
        bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / S, shape_method="CONCAVE")
        bpy.ops.object.mode_set(mode="OBJECT")
        a3 = sum(area3d(o) for o in objs)
        au = sum(uv_area(o, "lightmap") for o in objs)
        dens = S * math.sqrt(au / a3)
        print(f"  page {S}: {a3:.1f} m2, {dens:.1f} px/m")
        chosen = (S, dens)
        if dens >= 30:
            break
        bpy.ops.object.mode_set(mode="EDIT")
    return chosen


def srgb_encode(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


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
    return a.reshape(S, S, 4)


def stage_bake():
    stage_work()
    exp = make_export_objects()
    bpy.data.collections["Art"].hide_render = True
    bpy.data.collections["Art"].hide_viewport = True
    setup_cycles(SAMPLES, bake=True)
    report = {}
    for n, mats in enumerate(GROUPS):
        objs = [exp[m] for m in mats if m in exp]
        print(f"lightmap {n}: {[o.name for o in objs]}")
        S, dens = lightmap_uv(objs)
        img = bpy.data.images.new(f"LM_{n}", S, S, alpha=False, float_buffer=True)
        img.colorspace_settings.name = "Non-Color"
        for o in objs:
            for slot in o.material_slots:
                nt = slot.material.node_tree
                node = nt.nodes.new("ShaderNodeTexImage")
                node.name = "BAKE_TARGET"
                node.image = img
                nt.nodes.active = node
                node.select = True
        glass = exp.get("Window_Glass")
        if glass:
            glass.hide_render = True
        select_only(objs)
        for o in objs:
            o.data.uv_layers.active = o.data.uv_layers["lightmap"]
        bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
        if glass:
            glass.hide_render = False
        a = denoise_image(img, S)
        rgb = a[..., :3]
        peak = rgb.max(axis=2)
        pc = np.percentile(peak[peak > 1e-5], [50, 90, 99, 99.5, 100]) if (peak > 1e-5).any() else [1.0] * 5
        scale = float(pc[3])                                 # the 99.5th percentile of the lit texels maps to white; the few hotter ones (right under a lamp) clip
        print('  texel percentiles p50 p90 p99 p99.5 max:', [round(float(v), 3) for v in pc])
        out = np.ones((S, S, 4), np.float32)
        out[..., :3] = srgb_encode(rgb / scale)
        png = bpy.data.images.new(f"LM_{n}_png", S, S, alpha=False)
        png.colorspace_settings.name = "Non-Color"
        png.pixels.foreach_set(out.ravel())
        png.filepath_raw = str(stage_work() / f"apartment_{n}.png")
        png.file_format = "PNG"
        png.save()
        for o in objs:
            for slot in o.material_slots:
                m = slot.material
                m["lightmap"] = LM_URL.format(n)
                m["lightmap_intensity"] = round(math.pi * scale, 4)
                nt = m.node_tree
                for nd in [nd for nd in nt.nodes if nd.name.startswith("BAKE_TARGET")]:
                    nt.nodes.remove(nd)
        report[n] = {"size": S, "px_per_m": round(dens, 1), "scale": round(scale, 4), "p50_p90_p99_p995_max": [round(float(v), 3) for v in pc], "samples": SAMPLES, "mean": round(float(rgb.mean()), 4), "materials": mats}
        print("  baked", report[n])
        bpy.data.images.remove(img)
        bpy.data.images.remove(png)
    (stage_work() / "lightmaps.json").write_text(json.dumps(report, indent=1))
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Art"].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0                # no apartment.blend1 backups next to it
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile()


# ---------------------------------------------------------------- export
def stage_export():
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    bpy.data.collections["Art"].hide_viewport = True
    bpy.ops.object.select_all(action="DESELECT")
    for o in exp.objects:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = stage_work() / "apartment_raw.glb"
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False, export_animations=False)
    print("EXPORTED", raw, raw.stat().st_size)
    bpy.data.collections["Art"].hide_viewport = False
    exp.hide_viewport = exp.hide_render = True


# ---------------------------------------------------------------- the review stills
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
    cam.clip_start, cam.clip_end = 0.05, 100
    ob = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = B(loc)
    if target is not None:
        ob.rotation_euler = (B(target) - B(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


def stage_render():
    sc = bpy.context.scene
    STILLS.mkdir(parents=True, exist_ok=True)
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
        bpy.data.collections["Export"].hide_viewport = True
    setup_cycles(arg("--samples", 256, int))
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.exposure = arg("--exposure", 0.0, float)
    which = arg("--only", "all")
    if ENGINE.upper().startswith("EEVEE"):
        ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
        sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in ids else "BLENDER_EEVEE_NEXT"
    arrive, face = K["arrive"], K["face"]
    shots = {
        "1_arrival": look_cam("arrival", (arrive[0], 1.6, arrive[2]), (arrive[0] + face[0] * 3, 1.6, arrive[2] + face[1] * 3), 75.0),
        "2_wide": look_cam("wide", (0.2, 3.4, HZ + 3.1), (0.0, 0.5, -0.2), 58.0),
        "3_detail": look_cam("detail", (0.35, 1.5, -0.55), (1.55, 0.98, -2.1), 62.0),
    }
    plan = look_cam("plan", (0, H + 5, 0), None, ortho=7.4)
    arts = bpy.data.collections["Art"].objects
    cut_plan = [o for o in arts if o.name.startswith(("Ceiling_Apartment", "Ceiling_Lamp", "decor_backdrop"))]
    cut_wide = [o for o in arts if o.name in ("Wall_S", "Ceiling_Apartment", "Trim_DoorFrame", "Door_Leaf", "Door_Handle", "Plate_Switch", "decor_backdrop")]
    todo = [(k, v, (1920, 1080)) for k, v in shots.items()] + [("4_plan", plan, (1600, 1260))]
    for key, cam, (w, h) in todo:
        if which not in ("all", key):
            continue
        sc.camera = cam
        for o in arts:
            o.visible_camera = True
        for o in {"4_plan": cut_plan, "2_wide": cut_wide}.get(key, []):
            o.visible_camera = False                      # a cut-away view: these stay in the room for the light and the shadows, the camera just does not see them
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, arg("--scale", 100, int)
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        path = STILLS / f"{key}.jpg" if key != "4_plan" else stage_work() / "plan.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 400_000 and q > 40 and key != "4_plan":
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        print("STILL", key, path.stat().st_size, "q", q)


if __name__ == "__main__":
    if STAGE in ("art", "all"):
        build_all()
        save_blend()
    if STAGE in ("bake", "all"):
        stage_bake()
    if STAGE in ("export", "all"):
        stage_export()
    if STAGE in ("axes", "all"):
        stage_axes()
        save_blend()
    if STAGE in ("render", "all"):
        stage_render()
