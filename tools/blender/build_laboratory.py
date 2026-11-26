"""Builds the Farway laboratory in Blender, lights and bakes it, and exports world/laboratory.glb (docs/BLENDER.md, "3. laboratory").

Re-runnable, from the repo root:

    blender -b --python tools/blender/build_laboratory.py                       (every stage, in one run)
    blender -b --python tools/blender/build_laboratory.py -- --stage art        (build the art, save blender/scenes/laboratory.blend)
    blender -b blender/scenes/laboratory.blend --python tools/blender/build_laboratory.py -- --stage bake [--samples 256] [--device cpu]
    blender -b blender/scenes/laboratory.blend --python tools/blender/build_laboratory.py -- --stage export
    blender -b blender/scenes/laboratory.blend --python tools/blender/build_laboratory.py -- --stage axes     (the marker-cube axes check)
    blender -b blender/scenes/laboratory.blend --python tools/blender/build_laboratory.py -- --stage render [--samples 128] [--only 1_arrival]
    blender -b --python tools/blender/build_laboratory.py -- --stage textures --src <folder of the Poly Haven downloads>   (re-derive the three textures)

Stages: art (geometry, materials, lights, stand-ins) -> bake (merge by material, lightmap UV, Cycles bake, OIDN denoise, 8-bit PNGs in the work
folder) -> export (GLB; tools/blender/pack_scene.py then makes world/laboratory.glb with WebP textures and world/lightmaps/laboratory_<n>.webp)
-> axes -> render (the three review stills and a plan view).

No coordinate of the layout is typed in here: the room, its colliders, the five stations, the way out and the sealed B2 door come from
blender/layout/laboratory.json (node tools/blender/dump_layout.mjs laboratory). A game point (x, y, z) is Blender (x, -z, y). Only the art the
layout does not name (a tap, a balance, a strip light) is placed here, relative to those boxes. The page keeps drawing the station signs and the
B2 sign (docs/BLENDER.md, contract 4): the art leaves their spots clear, and the art stage checks that (SIGNS below).
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

SCENE = "laboratory"
ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / f"blender/layout/{SCENE}.json"
TEX = ROOT / f"blender/textures/{SCENE}"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"    # the path the page reads from the material's `lightmap` custom property
MARGIN_PX = 8

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 256, int)
DEVICE = arg("--device", "auto")
ENGINE = arg("--engine", "CYCLES")

L = json.loads(LAYOUT.read_text()) if LAYOUT.exists() else None
if L is None and STAGE != "textures":
    raise SystemExit(f"no {LAYOUT.relative_to(ROOT)}: run `node tools/blender/dump_layout.mjs {SCENE}` first")
K = L["constants"] if L else {}
COLLIDERS = {c["s"]: c for c in L["world"]["colliders"]} if L else {}
if L is not None and not all(k in K for k in ("half", "h")):
    raise SystemExit(f"{LAYOUT.relative_to(ROOT)} lacks constants.half or constants.h: re-run `node tools/blender/dump_layout.mjs {SCENE}`")
HX, HZ = K["half"] if L else (0, 0)
H = K["h"] if L else 0
WALL_T = 0.2

# The signs the page draws (index.html labProps, docs/BLENDER.md "3. laboratory"): each station's sign hangs over the station at 2.3 m
# (1.6 x 0.34 m, turned to face the room's middle), the B2 sign over the sealed door at 2.8 m (2.2 x 0.4 m, 10 cm off the wall).
# The art keeps out of these boxes (game coordinates); the art stage prints a PASS/FAIL line per box.
SIGN_Y, SIGN_W, SIGN_H = 2.3, 1.6, 0.34
B2_SIGN_Y, B2_SIGN_W, B2_SIGN_H = 2.8, 2.2, 0.4


def sign_boxes():
    out = []
    for s in K["stations"]:
        r = SIGN_W / 2 + 0.05
        out.append((f"sign {s['label']}", (s["x"] - r, SIGN_Y - SIGN_H / 2 - 0.05, s["z"] - r), (s["x"] + r, SIGN_Y + SIGN_H / 2 + 0.05, s["z"] + r)))
    b = K["b2"]
    out.append(("sign B2", (b["x"] - B2_SIGN_W / 2 - 0.05, B2_SIGN_Y - B2_SIGN_H / 2 - 0.05, b["z"] + 0.02), (b["x"] + B2_SIGN_W / 2 + 0.05, B2_SIGN_Y + B2_SIGN_H / 2 + 0.05, b["z"] + 0.25)))
    return out


def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


# ---------------------------------------------------------------- materials
IMG_CACHE = {}
MATS = {}
TILES = {}


def image(fn, srgb=True):
    key = (fn, srgb)
    if key not in IMG_CACHE:
        im = bpy.data.images.load(str(TEX / fn))
        im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
        IMG_CACHE[key] = im
    return IMG_CACHE[key]


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, diff=None, rough_img=None, normal=None, emit=None, img=None, emit_img=None, alpha=None, tile=None):
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

    def tex(im):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = im
        nt.links.new(uv.outputs["UV"], n.inputs["Vector"])
        return n

    if diff:
        nt.links.new(tex(image(diff)).outputs["Color"], bsdf.inputs["Base Color"])
    if img is not None:                                        # a generated (packed) base-colour image
        n = tex(img)
        nt.links.new(n.outputs["Color"], bsdf.inputs["Base Color"])
    if rough_img:
        nt.links.new(tex(image(rough_img, False)).outputs["Color"], bsdf.inputs["Roughness"])
    if normal:
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(tex(image(normal, False)).outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    if emit_img is not None:
        bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
        nt.links.new(tex(emit_img).outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emit_img.get("strength", 1.0)
    if alpha is not None:
        bsdf.inputs["Alpha"].default_value = alpha
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    TILES[name] = tile or 1.0
    MATS[name] = m
    return m


def make_materials(gen):
    material("Floor_Vinyl", diff="floor_vinyl_diff.jpg", rough_img="floor_vinyl_rough.jpg", normal="floor_vinyl_nor_gl.jpg", tile=1.5)
    material("Wall_Paint", diff="wall_paint_diff.jpg", rough=0.85, tile=1.5)
    material("Ceiling_Tile", diff="ceiling_tile_diff.jpg", rough=0.95, tile=0.6)
    material("Trim_Vinyl", color=(0.20, 0.25, 0.25), rough=0.5)
    material("Wall_Stripe", color=(0.05, 0.36, 0.38), rough=0.5)
    material("Trunking_PVC", color=(0.78, 0.79, 0.78), rough=0.4)
    material("Decal_Print", img=gen["atlas"], rough=0.6)
    material("Floor_Hazard", img=gen["hazard"], rough=0.6, tile=0.25)
    material("Steel_Brushed", img=gen["steel"], rough=0.3, metal=0.9, tile=0.6)
    material("Steel_Painted", color=(0.74, 0.76, 0.76), rough=0.45)
    material("Plastic_White", color=(0.80, 0.81, 0.80), rough=0.35)
    material("Plastic_Dark", color=(0.03, 0.035, 0.04), rough=0.4)
    material("Plastic_Accent", color=(0.05, 0.36, 0.38), rough=0.4)
    material("Plastic_Yellow", color=(0.85, 0.62, 0.03), rough=0.4)
    material("Glassware", color=(0.62, 0.70, 0.72), rough=0.15)
    material("Paper", color=(0.80, 0.80, 0.76), rough=0.9)
    material("Binder_Blue", color=(0.05, 0.12, 0.32), rough=0.5)
    material("Cardboard", color=(0.42, 0.30, 0.17), rough=0.9)
    material("Rubber_Black", color=(0.03, 0.03, 0.03), rough=0.8)
    material("Fixture_Alu", color=(0.62, 0.63, 0.64), rough=0.35, metal=0.6)
    material("Door_Paint", color=(0.66, 0.68, 0.67), rough=0.45)
    material("Door_Steel_Dark", color=(0.10, 0.11, 0.12), rough=0.45, metal=0.5)
    material("Glass_Dark", color=(0.015, 0.02, 0.025), rough=0.08)
    material("Label_Print", img=gen["atlas"], rough=0.6)
    material("Paint_Red", color=(0.55, 0.03, 0.02), rough=0.35)
    # not baked: lamps and lights that glow, and the clear glass (the page shows them as exported)
    material("Lamp_Emit", color=(0.95, 0.97, 1.0), rough=0.4, emit=((0.92, 0.96, 1.0), 8.0))
    material("Exit_Sign_Emit", emit_img=gen["exit"], rough=0.4)
    material("Display_Emit", color=(0.02, 0.04, 0.06), rough=0.2, emit=((0.30, 0.75, 1.0), 2.5))
    material("Indicator_Red", color=(0.3, 0.0, 0.0), rough=0.3, emit=((1.0, 0.05, 0.03), 6.0))
    material("B2_Slit_Glow", color=(0.02, 0.0, 0.0), rough=0.1, emit=((0.60, 0.02, 0.04), 0.6))
    material("Glass_Clear", color=(0.85, 0.92, 0.95), rough=0.05, alpha=0.15)


# ---------------------------------------------------------------- geometry helpers (all built in world space, identity object transforms)
def cube(bm, gmin, gmax):
    a, b = B(gmin), B(gmax)
    c = (a + b) / 2
    s = Vector((abs(a.x - b.x), abs(a.y - b.y), abs(a.z - b.z)))
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((s.x, s.y, s.z, 1.0)))


def soft_cube(bm, gmin, gmax, r=0.02, seg=2):
    n0 = len(bm.verts)
    cube(bm, gmin, gmax)
    bm.verts.ensure_lookup_table()
    geo = [bm.verts[i] for i in range(n0, len(bm.verts))]
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
    return bm.faces.new(vs)


def box_uv(bm, tile):
    """UV0: box projection in metres / tile, from world positions, so a texture runs on across the pieces of a wall."""
    uvl = bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y             # back to game axes
            if ax == 0:
                u, v = gz, gy
            elif ax == 1:
                u, v = gx, gy
            else:
                u, v = gx, gz
            lp[uvl].uv = (u / tile, v / tile)


ART = STANDIN = None


def finish(name, bm, mat, coll, smooth=False, tile=None, sharp_deg=35, keep_uv=False, recalc=True):
    for e in bm.edges:
        if smooth and len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) < math.radians(sharp_deg)
        else:
            e.smooth = not (len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(1))
    for f in bm.faces:
        f.smooth = smooth
    if recalc and not keep_uv:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if not bm.loops.layers.uv.get("UVMap"):
        bm.loops.layers.uv.new("UVMap")
    if not keep_uv:
        box_uv(bm, tile or TILES[mat])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(name, me)
    (coll or ART).objects.link(ob)
    return ob


def part(name, mat, build, smooth=False, tile=None, coll=None):
    bm = bmesh.new()
    build(bm)
    return finish(name, bm, mat, coll or ART, smooth, tile)


def panel(name, mat, centre, normal, up, w, h, uv=(0, 0, 1, 1), coll=None):
    """A flat quad facing `normal` (a game vector), `up` its picture's up (a game vector), w x h metres, its UV0 the rect uv=(u0, v0, u1, v1)."""
    n, u = Vector(normal).normalized(), Vector(up).normalized()
    r = (-n).cross(u)                                     # a viewer looking at the face (along -n) has this on their right
    c = Vector(centre)
    pts = [c - r * w / 2 - u * h / 2, c + r * w / 2 - u * h / 2, c + r * w / 2 + u * h / 2, c - r * w / 2 + u * h / 2]
    bm = bmesh.new()
    f = quad(bm, *[tuple(p) for p in pts])
    uvl = bm.loops.layers.uv.new("UVMap")
    u0, v0, u1, v1 = uv
    for lp, t in zip(f.loops, ((u0, v0), (u1, v0), (u1, v1), (u0, v1))):
        lp[uvl].uv = t
    return finish(name, bm, mat, coll or ART, keep_uv=True)


def disc(name, mat, centre, normal, up, r, uv_rect, seg=32, coll=None):
    """A flat round face (a clock's dial) with its UVs mapped into uv_rect of an atlas."""
    n, u = Vector(normal).normalized(), Vector(up).normalized()
    rt = (-n).cross(u)
    c = Vector(centre)
    bm = bmesh.new()
    pts = [c + rt * r * math.cos(2 * math.pi * i / seg) + u * r * math.sin(2 * math.pi * i / seg) for i in range(seg)]
    f = bm.faces.new([bm.verts.new(B(tuple(p))) for p in pts])
    uvl = bm.loops.layers.uv.new("UVMap")
    u0, v0, u1, v1 = uv_rect
    for i, lp in enumerate(f.loops):
        a = 2 * math.pi * i / seg
        lp[uvl].uv = (u0 + (u1 - u0) * (0.5 + 0.5 * math.cos(a)), v0 + (v1 - v0) * (0.5 + 0.5 * math.sin(a)))
    return finish(name, bm, mat, coll or ART, keep_uv=True)


# ---------------------------------------------------------------- stations: a local frame per station, "front" toward the room's middle
class Station:
    def __init__(self, s):
        self.s, self.id, self.x, self.z, self.hw = s, s["id"], s["x"], s["z"], s["half"]
        c = COLLIDERS["Station_" + s["id"]]
        self.top = c["max"][1]                                            # 0.95 for a bench, 1.9 for the freezer (the collision file)
        if abs(s["x"]) > abs(s["z"]):
            self.f = (-math.copysign(1, s["x"]), 0.0)
        else:
            self.f = (0.0, -math.copysign(1, s["z"]))
        self.l = (-self.f[1], self.f[0])

    def P(self, u, y, v):
        """station-local (u toward the front, y up, v sideways) -> game (x, y, z)"""
        return (self.x + u * self.f[0] + v * self.l[0], y, self.z + u * self.f[1] + v * self.l[1])

    def box(self, bm, a, b):
        p, q = self.P(*a), self.P(*b)
        cube(bm, tuple(min(p[i], q[i]) for i in range(3)), tuple(max(p[i], q[i]) for i in range(3)))

    def sbox(self, bm, a, b, r=0.02, seg=2):
        p, q = self.P(*a), self.P(*b)
        soft_cube(bm, tuple(min(p[i], q[i]) for i in range(3)), tuple(max(p[i], q[i]) for i in range(3)), r, seg)

    def cyl(self, bm, a, b, r0, r1=None, seg=16, cap=True):
        cyl(bm, self.P(*a), self.P(*b), r0, r1, seg, cap)

    def front(self):
        return (self.f[0], 0.0, self.f[1])

    def name(self, what):
        return f"St_{self.id}_{what}"


def steel_bench(st, top="Steel_Brushed", shelf=True):
    """A free-standing steel bench filling the station's 1.2 m square to its 0.95 m top: worktop, frame, legs, an undershelf."""
    w, T = st.hw, st.top
    part(st.name("Top"), top, lambda bm: (st.box(bm, (-w, T - 0.04, -w), (w, T, w)), st.box(bm, (-w, T, -w), (-w + 0.025, T + 0.08, w))))

    def frame(bm):
        for uu in (-w + 0.02, w - 0.06):
            for vv in (-w + 0.02, w - 0.06):
                st.box(bm, (uu, 0.03, vv), (uu + 0.04, T - 0.04, vv + 0.04))            # legs
                st.cyl(bm, (uu + 0.02, 0, vv + 0.02), (uu + 0.02, 0.03, vv + 0.02), 0.022, 0.018, 10)   # levelling feet
        st.box(bm, (-w + 0.02, T - 0.12, -w + 0.02), (w - 0.02, T - 0.04, -w + 0.05))  # aprons
        st.box(bm, (-w + 0.02, T - 0.12, w - 0.05), (w - 0.02, T - 0.04, w - 0.02))
        st.box(bm, (-w + 0.02, T - 0.12, -w + 0.05), (-w + 0.05, T - 0.04, w - 0.05))
        st.box(bm, (w - 0.05, T - 0.12, -w + 0.05), (w - 0.02, T - 0.04, w - 0.05))
        if shelf:
            st.box(bm, (-w + 0.04, 0.15, -w + 0.04), (w - 0.04, 0.175, w - 0.04))
    part(st.name("Frame"), "Steel_Brushed", frame)


def build_sink(st):
    w, T = st.hw, st.top
    # a closed cabinet under a stainless top with a basin; the tap at the back
    def cab(bm):
        st.box(bm, (-w + 0.01, 0.09, -w + 0.01), (w - 0.03, T - 0.04, w - 0.01))
        st.box(bm, (-w + 0.04, 0, -w + 0.04), (w - 0.10, 0.09, w - 0.04))            # the plinth, set back (a toe kick)
    part(st.name("Cabinet"), "Steel_Painted", cab)

    def doors(bm):
        for v0, v1 in ((-w + 0.02, -0.005), (0.005, w - 0.02)):
            st.box(bm, (w - 0.03, 0.10, v0), (w - 0.01, T - 0.07, v1))
    part(st.name("Doors"), "Steel_Painted", doors)
    part(st.name("Pulls"), "Plastic_Dark", lambda bm: [st.box(bm, (w - 0.01, T - 0.22, vv - 0.01), (w + 0.015, T - 0.10, vv + 0.01)) for vv in (-0.06, 0.06)])
    bu0, bu1, bv0, bv1, by = -0.30, 0.30, -0.36, 0.36, T - 0.26                     # the basin

    def top(bm):
        st.box(bm, (-w, T - 0.04, -w), (w, T, bv0))
        st.box(bm, (-w, T - 0.04, bv1), (w, T, w))
        st.box(bm, (-w, T - 0.04, bv0), (bu0, T, bv1))
        st.box(bm, (bu1, T - 0.04, bv0), (w, T, bv1))
        st.box(bm, (-w, T, -w), (-w + 0.025, T + 0.10, w))                              # the upstand at the back
    part(st.name("Top"), "Steel_Brushed", top)

    # the basin's inside: a floor and four walls, every face turned toward the basin's middle (an open box: no normal recalculation)
    a, b = st.P(bu0, by, bv0), st.P(bu1, by, bv1)
    x0, x1, z0, z1 = min(a[0], b[0]), max(a[0], b[0]), min(a[2], b[2]), max(a[2], b[2])
    y0, y1 = by, T - 0.04
    bm = bmesh.new()
    for q in (((x0, y0, z0), (x0, y0, z1), (x1, y0, z1), (x1, y0, z0)), ((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)),
              ((x0, y0, z1), (x0, y1, z1), (x1, y1, z1), (x1, y0, z1)), ((x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)),
              ((x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0))):
        quad(bm, *q)
    mid = B(((x0 + x1) / 2, (y0 + y1) / 2 + 0.05, (z0 + z1) / 2))
    for f in bm.faces:
        f.normal_update()
        if f.normal.dot(mid - f.calc_center_median()) < 0:
            f.normal_flip()
    finish(st.name("Basin"), bm, "Steel_Brushed", ART, recalc=False)
    part(st.name("Drain"), "Plastic_Dark", lambda bm: st.cyl(bm, (0, by, 0), (0, by + 0.004, 0), 0.04, 0.04, 16))

    def tap(bm):
        u0 = -w + 0.09
        st.cyl(bm, (u0, T, 0), (u0, T + 0.02, 0), 0.04, 0.035, 16)                    # the rose
        st.cyl(bm, (u0, T + 0.02, 0), (u0, T + 0.36, 0), 0.016, 0.016, 12)
        n = 7
        for i in range(n):                                                             # the goose neck: an arc forward and down
            a0, a1 = math.pi * i / n, math.pi * (i + 1) / n
            r = 0.13
            p0 = (u0 + r - r * math.cos(a0), T + 0.36 + r * math.sin(a0), 0)
            p1 = (u0 + r - r * math.cos(a1), T + 0.36 + r * math.sin(a1), 0)
            st.cyl(bm, p0, p1, 0.016, 0.016, 12)
        st.cyl(bm, (u0 + 2 * 0.13, T + 0.36, 0), (u0 + 2 * 0.13, T + 0.31, 0), 0.016, 0.012, 12)
        for vv in (-0.12, 0.12):                                                       # wrist-action levers
            st.cyl(bm, (u0, T, vv), (u0, T + 0.07, vv), 0.022, 0.018, 12)
            st.box(bm, (u0 - 0.01, T + 0.07, vv - 0.01), (u0 + 0.14, T + 0.085, vv + 0.01))
    part(st.name("Tap"), "Steel_Brushed", tap, smooth=True)
    # beside the basin: a wash bottle and two beakers, a flask
    part(st.name("WashBottle"), "Plastic_White", lambda bm: (st.cyl(bm, (0.42, T, 0.47), (0.42, T + 0.16, 0.47), 0.04, 0.04, 16), st.cyl(bm, (0.42, T + 0.16, 0.47), (0.42, T + 0.21, 0.47), 0.04, 0.01, 12)), smooth=True)

    def glass(bm):
        st.cyl(bm, (0.15, T, 0.46), (0.15, T + 0.12, 0.46), 0.045, 0.045, 18)
        st.cyl(bm, (0.25, T, 0.50), (0.25, T + 0.09, 0.50), 0.035, 0.035, 18)
        st.cyl(bm, (-0.05, T, 0.47), (-0.05, T + 0.10, 0.47), 0.07, 0.022, 18)       # an Erlenmeyer flask
        st.cyl(bm, (-0.05, T + 0.10, 0.47), (-0.05, T + 0.16, 0.47), 0.02, 0.02, 12)
    part(st.name("Glassware"), "Glassware", glass, smooth=True)


def build_scale(st):
    T = st.top
    steel_bench(st)

    def balance(bm):
        st.sbox(bm, (-0.38, T, -0.17), (0.02, T + 0.08, 0.17), 0.012)                  # the base
        st.sbox(bm, (-0.38, T + 0.08, -0.17), (-0.28, T + 0.40, 0.17), 0.012)          # the column at the back
    part(st.name("Balance"), "Plastic_White", balance)
    part(st.name("BalancePan"), "Steel_Brushed", lambda bm: st.cyl(bm, (-0.13, T + 0.085, 0), (-0.13, T + 0.095, 0), 0.05, 0.05, 20))
    part(st.name("BalanceShield"), "Glass_Clear", lambda bm: st.box(bm, (-0.28, T + 0.08, -0.16), (0.0, T + 0.36, 0.16)))
    part(st.name("BalanceDisplay"), "Display_Emit", lambda bm: st.box(bm, (0.02, T + 0.02, -0.08), (0.025, T + 0.06, 0.08)))

    def rack(bm):
        st.box(bm, (-0.25, T, 0.28), (0.05, T + 0.07, 0.50))
    part(st.name("TubeRack"), "Plastic_Accent", rack)

    def tubes(bm):
        for i in range(4):
            for j in range(3):
                st.cyl(bm, (-0.21 + i * 0.07, T + 0.03, 0.32 + j * 0.07), (-0.21 + i * 0.07, T + 0.16, 0.32 + j * 0.07), 0.012, 0.012, 10)
    part(st.name("Tubes"), "Glassware", tubes)
    part(st.name("Notebook"), "Paper", lambda bm: st.box(bm, (0.15, T, -0.50), (0.45, T + 0.015, -0.28)))
    part(st.name("WeighBoats"), "Plastic_White", lambda bm: st.box(bm, (0.20, T, 0.25), (0.30, T + 0.04, 0.35)))
    part(st.name("Boxes"), "Cardboard", lambda bm: (st.box(bm, (-0.45, 0.175, -0.5), (0.0, 0.45, -0.05)), st.box(bm, (0.05, 0.175, -0.45), (0.45, 0.36, 0.0))))


def build_centrifuge(st):
    T = st.top
    steel_bench(st)
    part(st.name("Body"), "Plastic_White", lambda bm: st.sbox(bm, (-0.40, T, -0.28), (0.22, T + 0.33, 0.28), 0.05, 3), smooth=True)
    part(st.name("Lid"), "Plastic_Dark", lambda bm: st.cyl(bm, (-0.12, T + 0.33, 0), (-0.12, T + 0.35, 0), 0.22, 0.20, 32), smooth=True)
    part(st.name("Panel"), "Plastic_Dark", lambda bm: st.box(bm, (0.12, T + 0.20, -0.20), (0.225, T + 0.30, 0.20)))
    part(st.name("Display"), "Display_Emit", lambda bm: st.box(bm, (0.225, T + 0.24, -0.10), (0.23, T + 0.28, 0.06)))
    part(st.name("Rack"), "Plastic_Accent", lambda bm: st.box(bm, (0.15, T, 0.32), (0.45, T + 0.06, 0.52)))
    part(st.name("Tubes"), "Glassware", lambda bm: [st.cyl(bm, (0.19 + i * 0.08, T + 0.02, 0.37 + j * 0.10), (0.19 + i * 0.08, T + 0.14, 0.37 + j * 0.10), 0.014, 0.014, 10) for i in range(4) for j in range(2)])
    part(st.name("Gloves"), "Cardboard", lambda bm: st.box(bm, (0.28, T, -0.52), (0.40, T + 0.09, -0.28)))
    part(st.name("Bin"), "Plastic_Yellow", lambda bm: st.cyl(bm, (0.15, 0.175, 0.25), (0.15, 0.62, 0.25), 0.2, 0.22, 24), smooth=True)
    part(st.name("BinLid"), "Plastic_Yellow", lambda bm: st.cyl(bm, (0.15, 0.62, 0.25), (0.15, 0.66, 0.25), 0.225, 0.2, 24), smooth=True)


def build_freezer(st):
    """An upright ultra-low freezer filling the station's box to 1.9 m, its door toward the room."""
    w, T = st.hw, st.top
    part(st.name("Body"), "Plastic_White", lambda bm: st.sbox(bm, (-w, 0.10, -w), (w - 0.04, T, w), 0.03, 2))
    part(st.name("Base"), "Plastic_Dark", lambda bm: st.box(bm, (-w + 0.03, 0.0, -w + 0.03), (w - 0.06, 0.10, w - 0.03)))
    part(st.name("Door"), "Plastic_White", lambda bm: st.sbox(bm, (w - 0.05, 0.32, -w + 0.03), (w - 0.005, 1.56, w - 0.03), 0.015, 2))
    part(st.name("Grille"), "Plastic_Dark", lambda bm: [st.box(bm, (w - 0.045, 0.13 + i * 0.03, -w + 0.06), (w - 0.035, 0.145 + i * 0.03, w - 0.06)) for i in range(6)])

    def handle(bm):
        st.box(bm, (w - 0.005, 0.80, w - 0.12), (w + 0.04, 0.84, w - 0.08))
        st.box(bm, (w - 0.005, 1.20, w - 0.12), (w + 0.04, 1.24, w - 0.08))
        st.box(bm, (w + 0.02, 0.80, w - 0.12), (w + 0.045, 1.24, w - 0.08))
    part(st.name("Handle"), "Steel_Brushed", handle)
    part(st.name("Panel"), "Plastic_Dark", lambda bm: st.box(bm, (w - 0.045, 1.62, -0.35), (w - 0.035, 1.82, 0.35)))
    part(st.name("Display"), "Display_Emit", lambda bm: st.box(bm, (w - 0.035, 1.67, -0.25), (w - 0.03, 1.77, 0.05)))
    part(st.name("Alarm"), "Indicator_Red", lambda bm: st.cyl(bm, (w - 0.035, 1.72, 0.17), (w - 0.025, 1.72, 0.17), 0.015, 0.015, 12))
    # the cryo warning on the door
    c = st.P(w - 0.004, 1.30, 0.0)
    panel(st.name("Sticker"), "Label_Print", c, st.front(), (0, 1, 0), 0.22, 0.20, uv=ATLAS["cryo"])


def build_log(st):
    w, T = st.hw, st.top
    steel_bench(st)
    part(st.name("Pedestal"), "Steel_Painted", lambda bm: st.box(bm, (-w + 0.08, 0.175, -w + 0.08), (w - 0.06, T - 0.13, -w + 0.50)))
    part(st.name("DrawerPulls"), "Plastic_Dark", lambda bm: [st.box(bm, (w - 0.06, y, -w + 0.24), (w - 0.04, y + 0.02, -w + 0.34)) for y in (0.32, 0.52, 0.70)])
    # the log book, open: a blue cover and two ruled pages, turned toward the reader at the front
    part(st.name("BookCover"), "Binder_Blue", lambda bm: st.box(bm, (-0.05, T, -0.22), (0.30, T + 0.012, 0.26)))
    up = (-st.f[0], 0.0, -st.f[1])                                                     # the page's top is away from the reader
    pg = (0, 1, 0)
    for i, (v0, key) in enumerate(((0.02, "page_l"), (-0.215, "page_r"))):            # the reader's left is +v (their right hand is -v)
        c = st.P(0.125, T + 0.016, v0 + 0.1175)
        panel(st.name(f"Page{i}"), "Label_Print", c, pg, up, 0.235, 0.33, uv=ATLAS[key])
    part(st.name("Pen"), "Plastic_Dark", lambda bm: st.cyl(bm, (0.08, T + 0.025, -0.30), (0.22, T + 0.025, -0.26), 0.005, 0.005, 8))

    def monitor(bm):
        st.box(bm, (-0.42, T, 0.18), (-0.30, T + 0.012, 0.42))                       # foot
        st.box(bm, (-0.40, T, 0.28), (-0.37, T + 0.30, 0.32))                         # neck
        st.box(bm, (-0.37, T + 0.16, 0.05), (-0.34, T + 0.50, 0.55))                  # the panel
    part(st.name("Monitor"), "Plastic_Dark", monitor)
    part(st.name("Keyboard"), "Plastic_Dark", lambda bm: st.box(bm, (0.05, T, 0.30), (0.20, T + 0.02, 0.56)))

    def binders(bm):
        for i in range(5):
            st.box(bm, (-0.55, T, -0.55 + i * 0.07), (-0.27, T + 0.31, -0.49 + i * 0.07))
    part(st.name("Binders"), "Binder_Blue", binders)
    part(st.name("Paper"), "Paper", lambda bm: st.box(bm, (0.0, 0.175, 0.05), (0.32, 0.29, 0.48)))


def build_stool(st, name):
    T = st.top

    def stool(bm):
        u, v = st.hw + 0.38, 0.0
        for a in range(4):
            ang = math.pi / 4 + a * math.pi / 2
            du, dv = 0.19 * math.cos(ang), 0.19 * math.sin(ang)
            st.cyl(bm, (u + du, 0, v + dv), (u + du * 0.4, 0.60, v + dv * 0.4), 0.012, 0.012, 8)
        st.cyl(bm, (u, 0.25, v), (u, 0.26, v), 0.15, 0.15, 20, cap=False)
    part(f"decor_stool_{name}", "Steel_Brushed", stool)
    part(f"decor_stool_{name}_seat", "Rubber_Black", lambda bm: st.cyl(bm, (st.hw + 0.38, 0.60, 0), (st.hw + 0.38, 0.66, 0), 0.17, 0.17, 24), smooth=True)


# ---------------------------------------------------------------- the shell, doors and the dressing on walls and ceiling
def build_shell():
    """The room's six slabs, straight from the collision file's boxes (Floor_*, Ceiling_*, Wall_*), so art and colliders agree."""
    for s, c in COLLIDERS.items():
        mn, mx = c["min"], c["max"]
        if s.startswith("Floor"):
            part(s, "Floor_Vinyl", lambda bm: cube(bm, mn, mx))
        elif s.startswith("Ceiling"):
            part(s, "Ceiling_Tile", lambda bm: cube(bm, mn, mx))
        elif s.startswith("Wall_"):
            part(s, "Wall_Paint", lambda bm: cube(bm, mn, mx))


def wall_runs(y0, y1, depth, gaps):
    """Boxes along the four walls' inner faces from y0 to y1, `depth` proud, skipping each gap (wall, a, b): wall "N"/"S" gaps are x ranges."""
    out = []
    for wall in "NSWE":
        if wall in "NS":
            zf = -HZ if wall == "N" else HZ
            spans = [(-HX, HX)]
            for gw, a, b in gaps:
                if gw == wall:
                    spans = [p for s0, s1 in spans for p in ((s0, min(s1, a)), (max(s0, b), s1)) if p[1] - p[0] > 0.01]
            for a, b in spans:
                z0, z1 = (zf, zf + depth) if wall == "N" else (zf - depth, zf)
                out.append((wall, (a, y0, z0), (b, y1, z1)))
        else:
            xf = -HX if wall == "W" else HX
            x0, x1 = (xf, xf + depth) if wall == "W" else (xf - depth, xf)
            out.append((wall, (x0, y0, -HZ + depth), (x1, y1, HZ - depth)))    # the west and east runs stop where the north and south runs begin
    return out


def wall_parts(name, mat, runs, extra=None):
    """One object per wall (so each wall's trim has its own box, and a cut-away view can hide one wall's)."""
    for wall in "NSWE":
        rr = [(a, b) for w, a, b in runs if w == wall]
        if rr:
            part(f"{name}_{wall}", mat, lambda bm: [cube(bm, a, b) for a, b in rr] + ([extra(bm, rr)] if extra else []))


def build_trim():
    ex, b2 = K["door"]["at"][0], K["b2"]["x"]
    door_gaps = [("S", ex - EXIT_W / 2 - 0.08, ex + EXIT_W / 2 + 0.08), ("N", b2 - B2_W / 2 - 0.08, b2 + B2_W / 2 + 0.08)]
    wall_parts("Trim_Skirting", "Trim_Vinyl", wall_runs(0.0, 0.10, 0.015, door_gaps))
    wall_parts("Trim_Stripe", "Wall_Stripe", wall_runs(1.36, 1.44, 0.002, door_gaps))
    tr_gaps = door_gaps + [("N", b2 + B2_W / 2, b2 + B2_W / 2 + 0.5), ("S", ex + EXIT_W / 2, ex + EXIT_W / 2 + 1.6), ("S", ex - EXIT_W / 2 - 1.6, ex - EXIT_W / 2)]
    runs = wall_runs(0.95, 1.07, 0.04, tr_gaps)
    wall_parts("Trim_Trunking", "Trunking_PVC", runs)

    def sockets(bm, rr):                                   # double sockets on the trunking's face, about every 1.8 m
        for (x0, _, z0), (x1, _, z1) in rr:
            along_x = (x1 - x0) > (z1 - z0)
            n = int((x1 - x0 if along_x else z1 - z0) // 1.8)
            for i in range(n):
                t = (i + 0.5) / n
                if along_x:                                # a north or south run: its face is the side toward the room
                    x, face = x0 + (x1 - x0) * t, (z1 if z0 < 0 else z0)
                    s = 1 if z0 < 0 else -1
                    cube(bm, (x - 0.08, 0.975, min(face, face + s * 0.008)), (x + 0.08, 1.045, max(face, face + s * 0.008)))
                else:
                    z, face = z0 + (z1 - z0) * t, (x1 if x0 < 0 else x0)
                    s = 1 if x0 < 0 else -1
                    cube(bm, (min(face, face + s * 0.008), 0.975, z - 0.08), (max(face, face + s * 0.008), 1.045, z + 0.08))
    for wall in "NSWE":
        rr = [(a, b) for w, a, b in runs if w == wall]
        part(f"Trim_Sockets_{wall}", "Plastic_White", lambda bm: sockets(bm, rr))


EXIT_W, EXIT_H = 2.2, 2.4          # the way out: a pair of doors in the south wall at the door spot's x (the blockout's opening is 2.4 x 2.5 m with its frame)
B2_W, B2_H = 1.9, 2.4              # the sealed door: a pair of steel leaves in the north wall at b2.x (the blockout's slab is 2.0 x 2.5 m)


def build_exit():
    x = K["door"]["at"][0]
    z = HZ
    a, b = x - EXIT_W / 2, x + EXIT_W / 2

    def frame(bm):
        cube(bm, (a - 0.08, 0, z - 0.045), (a, EXIT_H + 0.08, z))
        cube(bm, (b, 0, z - 0.045), (b + 0.08, EXIT_H + 0.08, z))
        cube(bm, (a - 0.08, EXIT_H, z - 0.045), (b + 0.08, EXIT_H + 0.08, z))
    part("Exit_Frame", "Steel_Painted", frame)
    part("Exit_Leaves", "Door_Paint", lambda bm: (cube(bm, (a, 0.005, z - 0.035), (x - 0.004, EXIT_H, z - 0.002)), cube(bm, (x + 0.004, 0.005, z - 0.035), (b, EXIT_H, z - 0.002))))

    def plates(bm):
        for c in ((a + x) / 2, (x + b) / 2):
            cube(bm, (c - 0.45, 0.02, z - 0.039), (c + 0.45, 0.28, z - 0.035))                 # kick plates
            cube(bm, ((c + x) / 2 - 0.06, 1.0, z - 0.040), ((c + x) / 2 + 0.06, 1.35, z - 0.035))   # push plates by the meeting stiles
    part("Exit_Plates", "Steel_Brushed", plates)

    def vision(bm):
        for c in ((a + x) / 2, (x + b) / 2):
            cube(bm, (c - 0.13, 1.25, z - 0.037), (c + 0.13, 1.95, z - 0.033))
    part("Exit_Vision", "Glass_Dark", vision)
    # the exit sign over the doors: a lit box (above head height)
    sy = EXIT_H + 0.32
    part("Exit_SignBox", "Plastic_White", lambda bm: cube(bm, (x - 0.24, sy - 0.11, z - 0.06), (x + 0.24, sy + 0.11, z)))
    panel("Exit_SignFace", "Exit_Sign_Emit", (x, sy, z - 0.061), (0, 0, -1), (0, 1, 0), 0.44, 0.18)


def build_b2():
    """The sealed door toward Secret Operations: a pair of heavy steel leaves that do not open, a card reader, hazard markings."""
    x, z = K["b2"]["x"], -HZ
    a, b = x - B2_W / 2, x + B2_W / 2

    def frame(bm):
        cube(bm, (a - 0.10, 0, z), (a, B2_H + 0.10, z + 0.045))
        cube(bm, (b, 0, z), (b + 0.10, B2_H + 0.10, z + 0.045))
        cube(bm, (a - 0.10, B2_H, z), (b + 0.10, B2_H + 0.10, z + 0.045))
    part("B2_Frame", "Door_Steel_Dark", frame)

    def leaves(bm):
        cube(bm, (a, 0.005, z), (x - 0.004, B2_H, z + 0.032))
        cube(bm, (x + 0.004, 0.005, z), (b, B2_H, z + 0.032))
        for c in ((a + x) / 2, (x + b) / 2):                                               # raised panels
            for y0, y1 in ((0.40, 1.15), (1.25, 2.25)):
                cube(bm, (c - 0.36, y0, z + 0.032), (c + 0.36, y1, z + 0.038))
    part("B2_Leaves", "Door_Steel_Dark", leaves)
    part("B2_KickBand", "Floor_Hazard", lambda bm: (cube(bm, (a + 0.02, 0.05, z + 0.032), (x - 0.02, 0.32, z + 0.036)), cube(bm, (x + 0.02, 0.05, z + 0.032), (b - 0.02, 0.32, z + 0.036))), tile=0.25)

    def slit_frames(bm):
        for c in ((a + x) / 2 + 0.22, (x + b) / 2 - 0.22):
            cube(bm, (c - 0.08, 1.55, z + 0.038), (c + 0.08, 2.15, z + 0.044))
    part("B2_SlitFrames", "Plastic_Dark", slit_frames)
    for i, c in enumerate(((a + x) / 2 + 0.22, (x + b) / 2 - 0.22)):
        panel(f"B2_Slit{i}", "B2_Slit_Glow", (c, 1.85, z + 0.0445), (0, 0, 1), (0, 1, 0), 0.10, 0.54)
    part("B2_Pulls", "Steel_Brushed", lambda bm: [cube(bm, (c - 0.015, 0.95, z + 0.032), (c + 0.015, 1.25, z + 0.046)) for c in (x - 0.09, x + 0.09)])
    # the warnings on the leaves: no entry (left), a warning triangle (right), on the upper raised panels
    panel("B2_SignNoEntry", "Decal_Print", ((a + x) / 2 - 0.15, 1.50, z + 0.0395), (0, 0, 1), (0, 1, 0), 0.24, 0.24, uv=ATLAS["noentry"])
    panel("B2_SignWarn", "Decal_Print", ((x + b) / 2 + 0.15, 1.50, z + 0.0395), (0, 0, 1), (0, 1, 0), 0.24, 0.24, uv=ATLAS["warn"])
    # the card reader on the wall beside the door, its conduit up to the services at the ceiling
    rx = b + 0.30
    part("B2_Reader", "Plastic_Dark", lambda bm: cube(bm, (rx - 0.05, 1.10, z), (rx + 0.05, 1.28, z + 0.03)))
    part("B2_ReaderLED", "Indicator_Red", lambda bm: cube(bm, (rx - 0.012, 1.245, z + 0.03), (rx + 0.012, 1.26, z + 0.034)))
    part("B2_Conduit", "Fixture_Alu", lambda bm: cyl(bm, (rx, 1.28, z + 0.018), (rx, PIPE_Y + 0.05, z + 0.018), 0.012, 0.012, 8))
    # hazard tape on the floor in front of it: keep clear
    def tape(bm):
        t, y = 0.06, 0.0015
        x0, x1, z1 = a - 0.25, b + 0.25, z + 1.1
        cube(bm, (x0, 0, z1 - t), (x1, y, z1))
        cube(bm, (x0, 0, z + 0.02), (x0 + t, y, z1 - t))
        cube(bm, (x1 - t, 0, z + 0.02), (x1, y, z1 - t))
    part("decor_b2_tape", "Floor_Hazard", tape)


PIPE_Y = 3.55


def build_services():
    """Above head height: the strip lights hung on wires, a run of pipes along the north wall, ceiling diffusers, wall cupboards."""
    rows = LIGHT_ROWS

    seg = 2 * LIGHT_X / LIGHT_MODULES                  # each row is a line of 1.5 m modules (and so are its lightmap islands)

    def housings(bm):
        for z in rows:
            for k in range(LIGHT_MODULES):
                x0 = -LIGHT_X + k * seg
                cube(bm, (x0 + 0.003, LIGHT_Y, z - 0.06), (x0 + seg - 0.003, LIGHT_Y + 0.07, z + 0.06))
            for xx in np.arange(-LIGHT_X + 0.3, LIGHT_X, 2.9):
                cyl(bm, (xx, LIGHT_Y + 0.07, z), (xx, H, z), 0.0025, 0.0025, 4, cap=False)
                cyl(bm, (xx, H - 0.006, z), (xx, H, z), 0.025, 0.025, 10)
    part("Light_Housings", "Fixture_Alu", housings)
    part("Light_Diffusers", "Lamp_Emit", lambda bm: [cube(bm, (-LIGHT_X + k * seg + 0.01, LIGHT_Y - 0.006, z - 0.05), (-LIGHT_X + (k + 1) * seg - 0.01, LIGHT_Y, z + 0.05))
                                                     for z in rows for k in range(LIGHT_MODULES)])

    def pipes(bm):                                    # two pipes in 3 m lengths with a coupling at each joint, on brackets
        z = -HZ
        xs = np.linspace(-HX, HX, 7)
        for x0, x1 in zip(xs[:-1], xs[1:]):
            cyl(bm, (x0, PIPE_Y, z + 0.12), (x1, PIPE_Y, z + 0.12), 0.05, 0.05, 16, cap=False)
            cyl(bm, (x0, PIPE_Y + 0.17, z + 0.10), (x1, PIPE_Y + 0.17, z + 0.10), 0.035, 0.035, 12, cap=False)
        for xx in xs[1:-1]:
            cyl(bm, (xx - 0.04, PIPE_Y, z + 0.12), (xx + 0.04, PIPE_Y, z + 0.12), 0.058, 0.058, 16)
            cyl(bm, (xx - 0.03, PIPE_Y + 0.17, z + 0.10), (xx + 0.03, PIPE_Y + 0.17, z + 0.10), 0.042, 0.042, 12)
        for xx in np.arange(-HX + 0.5, HX, 2.0):
            cube(bm, (xx - 0.02, PIPE_Y - 0.07, z), (xx + 0.02, PIPE_Y + 0.23, z + 0.20))
    part("Services_Pipes", "Fixture_Alu", pipes, smooth=True)
    part("Services_Lagging", "Plastic_White", lambda bm: [cyl(bm, (x0, PIPE_Y, -HZ + 0.12), (x1, PIPE_Y, -HZ + 0.12), 0.062, 0.062, 16) for x0, x1 in ((-HX + 0.6, -HX + 3.2), (2.0, 6.2))], smooth=True)

    def vents(bm):
        for vx, vz in VENTS:
            cube(bm, (vx - 0.29, H - 0.012, vz - 0.29), (vx + 0.29, H, vz + 0.29))
    part("Ceiling_Vents", "Fixture_Alu", vents)
    part("Ceiling_VentSlots", "Plastic_Dark", lambda bm: [cube(bm, (vx - 0.2, H - 0.014, vz - 0.2 + i * 0.1), (vx + 0.2, H - 0.012, vz - 0.17 + i * 0.1)) for vx, vz in VENTS for i in range(4)])
    # wall cupboards, 1.9 to 2.6 m (above head height, clear of the signs): behind the west and east stations, and along the north wall
    # either side of the sealed door, clear of its card reader
    cab_y0, cab_y1, d = 1.90, 2.60, 0.35
    runs = []
    for st in STATIONS:
        if st.f[1] == 0:                                     # a station by the west or the east wall
            runs.append(("W" if st.x < 0 else "E", max(st.z - 1.6, -HZ + 0.1), min(st.z + 1.6, HZ - 0.1)))
    b2x = K["b2"]["x"]
    runs += [("N", -HX + 0.6, b2x - B2_W / 2 - 1.0), ("N", b2x + B2_W / 2 + 1.0, HX - 0.6)]

    def cupboards(bm, run):
        w, s0, s1 = run
        wbox(bm, w, (s0, cab_y0, 0.0), (s1, cab_y1, d))

    def cup_lines(bm, run):                                  # doors of about 0.8 m: the gaps between them, and a pull at each door's free edge
        w, s0, s1 = run
        n = max(2, round((s1 - s0) / 0.8))
        ds = (s1 - s0) / n
        for i in range(1, n):
            wbox(bm, w, (s0 + ds * i - 0.004, cab_y0 + 0.01, d), (s0 + ds * i + 0.004, cab_y1 - 0.01, d + 0.004))
        for i in range(n):
            ss = s0 + ds * (i + (0.85 if i % 2 == 0 else 0.15))
            wbox(bm, w, (ss - 0.06, cab_y0 + 0.05, d), (ss + 0.06, cab_y0 + 0.07, d + 0.02))
    for i, run in enumerate(runs):                           # one object a run, so each has its own box in the checks
        part(f"Cupboard_{run[0]}{i}", "Steel_Painted", lambda bm: cupboards(bm, run))
        part(f"Cupboard_{run[0]}{i}_Lines", "Plastic_Dark", lambda bm: cup_lines(bm, run))


def wpt(wall, s, y, t):
    """a point on a wall: `s` along it (z on the west and east walls, x on the north and south), `t` out from its face into the room"""
    return {"W": (-HX + t, y, s), "E": (HX - t, y, s), "N": (s, y, -HZ + t), "S": (s, y, HZ - t)}[wall]


def wbox(bm, wall, a, b):
    p, q = wpt(wall, *a), wpt(wall, *b)
    cube(bm, tuple(min(p[i], q[i]) for i in range(3)), tuple(max(p[i], q[i]) for i in range(3)))


def build_dressing():
    """Flat things on the walls (within 5 cm of them), and the two passable props: a fire extinguisher and a first-aid box (decor_)."""
    e = 0.004
    # a notice board on the east wall, by the way out
    nz0, nz1, ny0, ny1 = HZ - 3.6, HZ - 2.0, 1.15, 1.95
    part("Notice_Frame", "Fixture_Alu", lambda bm: cube(bm, (HX - 0.02, ny0, nz0), (HX, ny1, nz1)))
    panel("Notice_Board", "Decal_Print", (HX - 0.02 - e, (ny0 + ny1) / 2, (nz0 + nz1) / 2), (-1, 0, 0), (0, 1, 0), nz1 - nz0 - 0.04, ny1 - ny0 - 0.04, uv=ATLAS["notice"])
    # the clock on the south wall over the coats, above head height
    ex = K["door"]["at"][0]
    cx, cy = ex - EXIT_W / 2 - 2.4, 2.55
    part("Clock_Rim", "Plastic_White", lambda bm: cyl(bm, (cx, cy, HZ), (cx, cy, HZ - 0.04), 0.18, 0.18, 32), smooth=True)
    disc("Clock_Face", "Decal_Print", (cx, cy, HZ - 0.041), (0, 0, -1), (0, 1, 0), 0.16, ATLAS["clock"])
    # a whiteboard on the west wall between the two cupboard runs
    wz0, wz1 = -1.2, 0.2
    part("Whiteboard_Frame", "Fixture_Alu", lambda bm: (cube(bm, (-HX, 1.13, wz0), (-HX + 0.025, 1.87, wz1)), cube(bm, (-HX, 1.10, wz0 + 0.1), (-HX + 0.05, 1.13, wz1 - 0.1))))
    part("Whiteboard_Face", "Plastic_White", lambda bm: cube(bm, (-HX + 0.025, 1.15, wz0 + 0.02), (-HX + 0.027, 1.85, wz1 - 0.02)))
    # lab coats on a rail by the way out (decor_: cloth, passable)
    part("Coat_Rail", "Fixture_Alu", lambda bm: cube(bm, (cx - 0.75, 1.74, HZ - 0.03), (cx + 0.75, 1.78, HZ)))

    def coats(bm):
        for k, dx in enumerate((-0.48, -0.02, 0.44)):
            x = cx + dx
            soft_cube(bm, (x - 0.21, 0.88, HZ - 0.16), (x + 0.21, 1.66, HZ - 0.04), 0.04, 2)            # the body, hanging
            soft_cube(bm, (x - 0.17, 1.62, HZ - 0.13), (x + 0.17, 1.74, HZ - 0.05), 0.03, 2)            # the shoulders
            cube(bm, (x - 0.012, 1.70, HZ - 0.05), (x + 0.012, 1.76, HZ - 0.02))                        # the loop on its hook
    part("decor_coats", "Paper", coats, smooth=True)
    # signs by the sink: eye protection
    sink = next(s for s in STATIONS if s.id == "sink")
    panel("Sign_Goggles", "Decal_Print", (-HX + e, 1.62, sink.z), (1, 0, 0), (0, 1, 0), 0.26, 0.26, uv=ATLAS["goggles"])
    # the fire point by the way out: an extinguisher and a first-aid box (decor_: passable, as in the pilot)
    fx = ex + EXIT_W / 2 + 0.75
    part("decor_extinguisher", "Paint_Red", lambda bm: (cyl(bm, (fx, 0.12, HZ - 0.12), (fx, 0.62, HZ - 0.12), 0.08, 0.08, 20), sphere(bm, (fx, 0.62, HZ - 0.12), 0.08, 16)), smooth=True)
    part("decor_extinguisher_head", "Plastic_Dark", lambda bm: (cyl(bm, (fx, 0.68, HZ - 0.12), (fx, 0.76, HZ - 0.12), 0.022, 0.022, 10), cube(bm, (fx - 0.01, 0.40, HZ - 0.02), (fx + 0.01, 0.72, HZ))))
    panel("Sign_FirePoint", "Decal_Print", (fx, 1.0, HZ - e), (0, 0, -1), (0, 1, 0), 0.22, 0.22, uv=ATLAS["fire"])
    ax = ex - EXIT_W / 2 - 0.9
    part("decor_firstaid", "Plastic_White", lambda bm: cube(bm, (ax - 0.18, 1.25, HZ - 0.12), (ax + 0.18, 1.55, HZ)))
    panel("decor_firstaid_sign", "Decal_Print", (ax, 1.40, HZ - 0.121), (0, 0, -1), (0, 1, 0), 0.2, 0.2, uv=ATLAS["aid"])
    # a floor drain by the sink
    part("Floor_Drain", "Steel_Brushed", lambda bm: cube(bm, (sink.x + 1.0, 0.0, sink.z - 0.12), (sink.x + 1.24, 0.002, sink.z + 0.12)))


# ---------------------------------------------------------------- generated images (own work, numpy, fixed seeds)
def rs(a, h, w):
    ys, xs = np.linspace(0, a.shape[0] - 1, h), np.linspace(0, a.shape[1] - 1, w)
    y0, x0 = np.floor(ys).astype(int), np.floor(xs).astype(int)
    y1, x1 = np.minimum(y0 + 1, a.shape[0] - 1), np.minimum(x0 + 1, a.shape[1] - 1)
    fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
    if a.ndim == 3:
        fy, fx = fy[..., None], fx[..., None]
    return (a[y0][:, x0] * (1 - fy) * (1 - fx) + a[y0][:, x1] * (1 - fy) * fx + a[y1][:, x0] * fy * (1 - fx) + a[y1][:, x1] * fy * fx)


def vnoise(h, w, rng, octaves=5, base=4):
    out, amp, tot = np.zeros((h, w)), 1.0, 0.0
    for k in range(octaves):
        n = base * 2 ** k + 1
        out += amp * rs(rng.random((n, n)), h, w)
        tot += amp
        amp *= 0.5
    return out / tot


def blur(a, r, passes=3, axes=(0, 1)):
    n = 2 * r + 1
    for ax in axes:
        for _ in range(passes):
            pad = [(0, 0)] * a.ndim
            pad[ax] = (r + 1, r)
            c = np.cumsum(np.pad(a, pad, mode="wrap"), axis=ax)
            Ln = c.shape[ax]
            a = (np.take(c, range(n, Ln), axis=ax) - np.take(c, range(0, Ln - n), axis=ax)) / n
    return a


def steel_pixels():
    """Brushed stainless: fine streaks along one axis, a little mottling (tiles seamlessly)."""
    S = 512
    rng = np.random.default_rng(21)
    streak = blur(rng.random((S, S)), 40, 2, axes=(1,))
    streak = (streak - streak.mean()) / (streak.std() + 1e-6)
    mot = vnoise(S, S, rng, 4, 3)
    v = 0.66 + 0.035 * streak + 0.05 * (mot - 0.5)
    return np.clip(np.stack([v * 0.98, v, v * 1.02], -1), 0, 1).astype(np.float32)


def hazard_pixels():
    S = 256
    yy, xx = np.mgrid[0:S, 0:S]
    band = ((xx + yy) // (S // 4)) % 2 == 0
    img = np.zeros((S, S, 3), np.float32)
    img[band] = (0.93, 0.70, 0.05)
    img[~band] = (0.05, 0.05, 0.05)
    rng = np.random.default_rng(4)
    return np.clip(img * (0.9 + 0.12 * vnoise(S, S, rng, 4, 4))[..., None], 0, 1).astype(np.float32)


def _poly(img, pts, col, x0, y0):
    """fill a convex polygon (pixel coordinates inside a cell at x0, y0)"""
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    inside = np.ones((h, w), bool)
    n = len(pts)
    for i in range(n):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
        ax, ay, bx, by = ax + x0, ay + y0, bx + x0, by + y0
        inside &= (bx - ax) * (yy - ay) - (by - ay) * (xx - ax) >= 0
    img[inside] = col


def _circle(img, cx, cy, r, col, ring=None):
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot(xx - cx, yy - cy)
    m = d <= r if ring is None else (d <= r) & (d >= r - ring)
    img[m] = col


def _rect(img, x0, y0, x1, y1, col):
    img[int(y0):int(y1), int(x0):int(x1)] = col


ATLAS_PX = 1024
ATLAS_CELLS = {             # name: (column px, row px, width px, height px) in the atlas image, rows from the top
    "warn": (0, 0, 256, 256), "cryo": (256, 0, 256, 256), "goggles": (512, 0, 256, 256), "aid": (768, 0, 256, 256),
    "noentry": (0, 256, 256, 256), "clock": (256, 256, 256, 256), "fire": (512, 256, 256, 256),
    "page_l": (768, 256, 128, 180), "page_r": (896, 256, 128, 180),          # the log book's pages, 0.235 x 0.33 m
    "notice": (0, 512, 1024, 500),                                          # the notice board, 1.56 x 0.76 m
}
ATLAS = {}


def _uv(cell, inset=4):
    c, r, w, h = cell
    return ((c + inset) / ATLAS_PX, 1 - (r + h - inset) / ATLAS_PX, (c + w - inset) / ATLAS_PX, 1 - (r + inset) / ATLAS_PX)


def atlas_pixels():
    """One image for every printed thing: safety signs as pictograms (no words: the page draws the text signs), a clock face, two ruled pages of
    the log book, a cork notice board with papers. Pictograms after the usual safety-sign shapes, drawn here from simple shapes."""
    S = ATLAS_PX
    rng = np.random.default_rng(9)
    img = np.ones((S, S, 3), np.float32) * 0.92
    white, black, yellow, blue, green, red = (0.93, 0.93, 0.91), (0.04, 0.04, 0.04), (0.95, 0.72, 0.05), (0.05, 0.25, 0.60), (0.02, 0.45, 0.22), (0.72, 0.05, 0.05)

    def cell(name):
        c, r, w, h = ATLAS_CELLS[name]
        return c, r, w, h
    # warning: a yellow triangle with a black border and an exclamation mark
    for name in ("warn", "cryo"):
        c, r, w, h = cell(name)
        _rect(img, c, r, c + w, r + h, white)
        _poly(img, [(128, 22), (238, 222), (18, 222)], black, c, r)
        _poly(img, [(128, 52), (210, 206), (46, 206)], yellow, c, r)
        if name == "warn":
            _poly(img, [(120, 95), (136, 95), (132, 165), (124, 165)], black, c, r)
            _circle(img, c + 128, r + 184, 9, black)
        else:                                                   # a snowflake: three crossed bars
            for a in (0, 60, 120):
                t = math.radians(a)
                dx, dy = math.cos(t), math.sin(t)
                pts = [(128 + dx * 50 - dy * 5, 150 + dy * 50 + dx * 5), (128 - dx * 50 - dy * 5, 150 - dy * 50 + dx * 5),
                       (128 - dx * 50 + dy * 5, 150 - dy * 50 - dx * 5), (128 + dx * 50 + dy * 5, 150 + dy * 50 - dx * 5)]
                _poly(img, pts[::-1], black, c, r)
    # mandatory: a blue disc with white goggles
    c, r, w, h = cell("goggles")
    _rect(img, c, r, c + w, r + h, white)
    _circle(img, c + 128, r + 128, 112, blue)
    _rect(img, c + 58, r + 112, c + 198, r + 150, white)
    _circle(img, c + 92, r + 131, 30, white)
    _circle(img, c + 164, r + 131, 30, white)
    _circle(img, c + 92, r + 131, 18, blue)
    _circle(img, c + 164, r + 131, 18, blue)
    # first aid: a white cross on green
    c, r, w, h = cell("aid")
    _rect(img, c, r, c + w, r + h, green)
    _rect(img, c + 100, r + 40, c + 156, r + 216, white)
    _rect(img, c + 40, r + 100, c + 216, r + 156, white)
    # fire point: a white extinguisher on red
    c, r, w, h = cell("fire")
    _rect(img, c, r, c + w, r + h, red)
    _rect(img, c + 98, r + 70, c + 158, r + 226, white)
    _circle(img, c + 128, r + 72, 30, white)
    _rect(img, c + 112, r + 30, c + 144, r + 50, white)
    _rect(img, c + 144, r + 34, c + 196, r + 44, white)
    # no entry: a red disc with a white bar
    c, r, w, h = cell("noentry")
    _rect(img, c, r, c + w, r + h, white)
    _circle(img, c + 128, r + 128, 112, red)
    _rect(img, c + 48, r + 110, c + 208, r + 146, white)
    # the clock: a white dial, ticks, two hands at ten past ten
    c, r, w, h = cell("clock")
    _rect(img, c, r, c + w, r + h, white)
    _circle(img, c + 128, r + 128, 126, (0.97, 0.97, 0.96))
    for i in range(60):
        t = 2 * math.pi * i / 60
        r0, r1, hw = (100, 122, 3.5) if i % 5 == 0 else (114, 122, 1.2)
        dx, dy = math.sin(t), -math.cos(t)
        pts = [(128 + dx * r0 - dy * hw, 128 + dy * r0 + dx * hw), (128 + dx * r1 - dy * hw, 128 + dy * r1 + dx * hw),
               (128 + dx * r1 + dy * hw, 128 + dy * r1 - dx * hw), (128 + dx * r0 + dy * hw, 128 + dy * r0 - dx * hw)]
        _poly(img, pts[::-1], black, c, r)
    for ang, ln, hw in ((math.radians(305), 62, 5), (math.radians(60), 92, 3.5)):
        dx, dy = math.sin(ang), -math.cos(ang)
        pts = [(128 - dy * hw, 128 + dx * hw), (128 + dx * ln - dy * hw, 128 + dy * ln + dx * hw), (128 + dx * ln + dy * hw, 128 + dy * ln - dx * hw), (128 + dy * hw, 128 - dx * hw)]
        _poly(img, pts[::-1], black, c, r)
    _circle(img, c + 128, r + 128, 7, red)
    # the log book's pages: ruled, a margin, rows of handwriting as grey strokes
    for name in ("page_l", "page_r"):
        c, r, w, h = cell(name)
        _rect(img, c, r, c + w, r + h, (0.94, 0.93, 0.88))
        for y in range(r + 30, r + h - 10, 14):
            _rect(img, c + 8, y, c + w - 8, y + 1, (0.55, 0.68, 0.85))
        _rect(img, c + 34, r + 8, c + 36, r + h - 8, (0.85, 0.45, 0.45))
        filled = 13 if name == "page_l" else 6
        for k, y in enumerate(range(r + 30, r + h - 10, 14)):
            if k >= filled:
                break
            x = c + 40
            while x < c + w - 20:
                ln = int(rng.integers(8, 34))
                _rect(img, x, y - 7, min(x + ln, c + w - 14), y - 4, (0.18, 0.20, 0.32))
                x += ln + int(rng.integers(4, 9))
    # the notice board: cork, with papers and a rota grid pinned to it
    c, r, w, h = cell("notice")
    cork = vnoise(h, w, rng, 6, 16)
    speck = (rng.random((h, w)) < 0.08) * 0.12
    img[r:r + h, c:c + w] = np.stack([0.52 + 0.18 * cork - speck, 0.36 + 0.13 * cork - speck, 0.20 + 0.08 * cork - speck], -1)
    _rect(img, c, r, c + w, r + 10, (0.55, 0.56, 0.57))
    _rect(img, c, r + h - 10, c + w, r + h, (0.55, 0.56, 0.57))
    papers = [(40, 40, 230, 330), (300, 60, 520, 360), (580, 30, 800, 300), (850, 70, 990, 260), (600, 330, 980, 480), (60, 370, 330, 480)]
    for i, (x0, y0, x1, y1) in enumerate(papers):
        tint = (0.95, 0.95, 0.93) if i != 3 else (0.95, 0.88, 0.45)
        _rect(img, c + x0 + 4, r + y0 + 5, c + x1 + 4, r + y1 + 5, (0.25, 0.18, 0.10))
        _rect(img, c + x0, r + y0, c + x1, r + y1, tint)
        _rect(img, c + x0 + 14, r + y0 + 14, c + x0 + (x1 - x0) * 0.7, r + y0 + 26, (0.15, 0.15, 0.18))
        if i == 1:                                             # a rota: a grid
            for gx in range(x0 + 14, x1 - 10, 34):
                _rect(img, c + gx, r + y0 + 40, c + gx + 1, r + y1 - 14, (0.3, 0.3, 0.35))
            for gy in range(y0 + 40, y1 - 10, 22):
                _rect(img, c + x0 + 14, r + gy, c + x1 - 14, r + gy + 1, (0.3, 0.3, 0.35))
        else:
            for y in range(y0 + 40, y1 - 14, 13):
                ln = int((x1 - x0 - 28) * rng.uniform(0.5, 1.0))
                _rect(img, c + x0 + 14, r + y, c + x0 + 14 + ln, r + y + 4, (0.35, 0.35, 0.38))
        _circle(img, c + (x0 + x1) // 2, r + y0 + 8, 7, (0.80, 0.10, 0.10))
    return np.clip(img, 0, 1).astype(np.float32)


def exit_pixels():
    """The exit sign: a green panel with a white door and an arrow (a pictogram, no words)."""
    Wd, Hd = 256, 104
    img = np.zeros((Hd, Wd, 3), np.float32)
    img[:] = (0.02, 0.55, 0.20)
    _rect(img, 6, 6, Wd - 6, Hd - 6, (0.04, 0.62, 0.25))
    _rect(img, 150, 18, 212, 88, (0.95, 0.97, 0.95))            # the door
    _rect(img, 158, 26, 204, 88, (0.02, 0.55, 0.20))
    _rect(img, 60, 46, 130, 58, (0.95, 0.97, 0.95))             # the arrow toward it
    _poly(img, [(130, 30), (150, 52), (130, 74)], (0.95, 0.97, 0.95), 0, 0)
    return img


def mk_image(name, arr, srgb=True):
    """A packed image from a float array (rows top to bottom): written as a PNG first, because a generated image forgets its pixels when the file is saved."""
    h, w = arr.shape[:2]
    im = bpy.data.images.new(name + "_gen", w, h, alpha=False)
    im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :arr.shape[2]] = arr
    im.pixels.foreach_set(np.flipud(rgba).ravel())
    gen = stage_work() / "gen"
    gen.mkdir(parents=True, exist_ok=True)
    path = gen / f"{name}.png"
    im.filepath_raw = str(path)
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)
    return packed_image(name, path.read_bytes(), "sRGB" if srgb else "Non-Color")


def packed_image(name, data, colorspace, fname=None):
    """A new image packed from PNG bytes under a neutral relative name. Built fresh, so neither the image's path nor its packed
    file's path ever holds the work folder (a renamed path would leave the old one in the bytes after the new one's end)."""
    out = bpy.data.images.new(name, 1, 1, alpha=False)
    out.filepath_raw = f"//gen/{bpy.path.clean_name(fname or name)}.png"
    out.source = "FILE"
    out.pack(data=data, data_len=len(data))
    out.colorspace_settings.name = colorspace
    return out


def make_generated():
    for k, cellv in ATLAS_CELLS.items():
        ATLAS[k] = _uv(cellv)
    gen = {"atlas": mk_image("Print_Atlas", atlas_pixels()), "steel": mk_image("Steel_Brushed_Img", steel_pixels()), "hazard": mk_image("Hazard_Img", hazard_pixels())}
    ex = mk_image("Exit_Sign_Img", exit_pixels())
    ex["strength"] = 3.0
    gen["exit"] = ex
    return gen


# ---------------------------------------------------------------- the textures derived from the Poly Haven downloads (stage "textures")
def load_px(path):
    im = bpy.data.images.load(str(path))
    w, h = im.size
    a = np.empty(w * h * im.channels, np.float32)
    im.pixels.foreach_get(a)
    a = np.flipud(a.reshape(h, w, im.channels))[..., :3]
    bpy.data.images.remove(im)
    return a


def save_jpg(arr, path, q=88):
    h, w = arr.shape[:2]
    im = bpy.data.images.new(path.stem, w, h, alpha=False)
    rgba = np.ones((h, w, 4), np.float32)
    rgba[..., :3] = np.clip(arr, 0, 1)
    im.pixels.foreach_set(np.flipud(rgba).ravel())
    im.filepath_raw = str(path)
    im.file_format = "JPEG"
    im.save(filepath=str(path), quality=q)
    bpy.data.images.remove(im)
    print("TEXTURE", path.relative_to(ROOT), path.stat().st_size)


def stage_textures():
    """floor_vinyl_*: tiled_floor_001 (its terracotta made a pale clinical grey; its seams darker), wall_paint_diff: white_plaster_02 lifted to
    an off-white, ceiling_tile_diff: one 0.6 m ceiling tile cut from polystyrene with the grid's T-bar drawn round it. All Poly Haven, CC0."""
    src = Path(arg("--src"))
    TEX.mkdir(parents=True, exist_ok=True)
    lum = lambda a: a @ np.array([0.299, 0.587, 0.114], np.float32)
    f = lum(load_px(src / "tiled_floor_001_diffuse_1k.jpg"))
    n = (f - f.mean()) / f.std()
    base = np.array([0.76, 0.78, 0.77], np.float32)
    save_jpg(base[None, None, :] - 0.04 * n[..., None], TEX / "floor_vinyl_diff.jpg")
    save_jpg(load_px(src / "tiled_floor_001_nor_gl_1k.jpg"), TEX / "floor_vinyl_nor_gl.jpg")
    save_jpg(load_px(src / "tiled_floor_001_rough_1k.jpg") * 0.8, TEX / "floor_vinyl_rough.jpg")
    p = lum(load_px(src / "white_plaster_02_diff_1k.jpg"))
    save_jpg(np.array([0.90, 0.905, 0.89], np.float32)[None, None, :] + 0.5 * (p - p.mean())[..., None], TEX / "wall_paint_diff.jpg")
    c = lum(load_px(src / "polystyrene_diff_1k.jpg"))
    crop = c[100:100 + 410, 300:300 + 410]
    crop = rs(crop, 512, 512)
    t = np.array([0.93, 0.935, 0.93], np.float32)[None, None, :] + 0.7 * (crop - crop.mean())[..., None]
    bar, grid = 10, np.array([0.80, 0.81, 0.83], np.float32)
    t[:bar], t[-bar:], t[:, :bar], t[:, -bar:] = grid, grid, grid, grid
    t[bar:bar + 2, bar:-bar] *= 0.78
    t[bar:-bar, bar:bar + 2] *= 0.78
    save_jpg(t, TEX / "ceiling_tile_diff.jpg")


# ---------------------------------------------------------------- lights, world, marker
LIGHT_ROWS = (-3.0, 0.0, 3.0)      # strip-light rows (game z), along x
LIGHT_X = 7.5                      # each row runs x -7.5 .. 7.5
LIGHT_Y = 3.40                     # the diffuser's underside, hung 0.6 m under the 4 m ceiling
LIGHT_MODULES = 10                 # 1.5 m modules a row
VENTS = ((-4.5, -4.5), (4.5, -4.5), (-4.5, 1.5), (4.5, 1.5))     # ceiling diffusers, on the 0.6 m tile grid's centres
# How bright: the page draws a baked material unlit (three's MeshBasicMaterial: texture x lightmap x lightmap_intensity / pi, no tone mapping),
# so a surface over 1.0 clips to white. At the first bake's 210 W down and 45 W up the floor's and the ceiling's 90th percentile showed at 1.03 and
# 1.13 (13 % and 15 % of them flat white). Down x0.6 and up x0.5 (the ceiling was the hottest) keep the main surfaces' 90th percentile under 1.0
# (docs/renders/laboratory/README.md, "How bright"). The bake stage sets the lights to these, so a relight needs no art stage.
DOWN_W = arg("--down", 126.0, float)   # watts per row, down
UP_W = arg("--up", 22.5, float)        # watts per row, up toward the ceiling (a direct/indirect fitting)


def add_lights():
    lights = bpy.data.collections.new("Lights")
    bpy.context.scene.collection.children.link(lights)
    for i, z in enumerate(LIGHT_ROWS):
        for kind, y, w, rot in (("Down", LIGHT_Y - 0.007, DOWN_W, (0, 0, 0)), ("Up", LIGHT_Y + 0.075, UP_W, (math.pi, 0, 0))):
            d = bpy.data.lights.new(f"Strip{i}_{kind}", "AREA")
            d.shape = "RECTANGLE"
            d.size, d.size_y = 2 * LIGHT_X - 0.05, 0.09
            d.energy, d.color = w, (0.96, 0.98, 1.0)
            ob = bpy.data.objects.new(f"Strip{i}_{kind}", d)
            ob.location = B((0, y, z))
            ob.rotation_euler = rot
            lights.objects.link(ob)


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("Dark")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
    bg.inputs["Strength"].default_value = 0.0


def ensure_marker():
    """A 20 cm marker cube at the arrival point (docs/BLENDER.md, contract 3), kept in Standins and never exported or rendered."""
    st = bpy.data.collections["Standins"]
    ob = bpy.data.objects.get("standin_arrival_marker")
    if ob is None:
        me = bpy.data.meshes.new("standin_arrival_marker")
        bm = bmesh.new()
        a = K["arrive"]
        cube(bm, (a[0] - 0.1, a[1], a[2] - 0.1), (a[0] + 0.1, a[1] + 0.2, a[2] + 0.1))
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("standin_arrival_marker", me)
        st.objects.link(ob)
    ob.hide_render = True
    return ob


def standin_signs():
    """Hidden stand-ins where the page hangs its signs (never exported, never rendered), so the .blend shows the spots to keep clear."""
    sm = MATS["Plastic_Dark"]
    for s in K["stations"]:
        ang = math.atan2(-s["x"], -s["z"])
        n = (math.sin(ang), 0, math.cos(ang))
        ob = panel(f"standin_sign_{s['id']}", "Plastic_Dark", (s["x"], SIGN_Y, s["z"]), n, (0, 1, 0), SIGN_W, SIGN_H, coll=STANDIN)
        ob.hide_render = True
    b = K["b2"]
    ob = panel("standin_sign_b2", "Plastic_Dark", (b["x"], B2_SIGN_Y, b["z"] + 0.1), (0, 0, 1), (0, 1, 0), B2_SIGN_W, B2_SIGN_H, coll=STANDIN)
    ob.hide_render = True


def check_signs():
    """Every Art object's box against the page's sign boxes: none may reach into one."""
    bad = 0
    parts = []
    for ob in bpy.data.collections["Art"].all_objects:
        pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        g = [(p.x, p.z, -p.y) for p in pts]
        parts.append((ob.name, [min(q[i] for q in g) for i in range(3)], [max(q[i] for q in g) for i in range(3)]))
    for label, mn, mx in sign_boxes():
        hit = [n for n, a, b in parts if all(a[i] < mx[i] and b[i] > mn[i] for i in range(3)) and n not in COLLIDERS]     # the room's slabs bound it, of course
        print(f"SIGNS {'PASS' if not hit else 'FAIL'} {label}: y {mn[1]:.2f}..{mx[1]:.2f} " + ("clear" if not hit else "reached by " + ", ".join(hit)))
        bad += bool(hit)
    return bad


STATIONS = []


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
    gen = make_generated()
    make_materials(gen)
    STATIONS[:] = [Station(s) for s in K["stations"]]
    build_shell()
    build_trim()
    build_exit()
    build_b2()
    builders = {"sink": build_sink, "scale": build_scale, "centrifuge": build_centrifuge, "freezer": build_freezer, "log": build_log}
    for st in STATIONS:
        builders[st.id](st)
    for st in STATIONS:
        if st.id in ("scale", "log"):
            build_stool(st, st.id)
    build_services()
    build_dressing()
    add_lights()
    setup_world()
    ensure_marker()
    standin_signs()
    bpy.context.view_layer.update()
    bad = check_signs()
    assert not bad, "art reaches into a sign's spot"


# ---------------------------------------------------------------- bake
SHELL_MATS = ["Floor_Vinyl", "Wall_Paint", "Ceiling_Tile", "Trim_Vinyl", "Wall_Stripe", "Trunking_PVC", "Decal_Print", "Floor_Hazard"]
CONTENT_MATS = ["Steel_Brushed", "Steel_Painted", "Plastic_White", "Plastic_Dark", "Plastic_Accent", "Plastic_Yellow", "Glassware", "Paper", "Binder_Blue",
                "Cardboard", "Rubber_Black", "Fixture_Alu", "Door_Paint", "Door_Steel_Dark", "Glass_Dark", "Label_Print", "Paint_Red"]
GROUPS = [SHELL_MATS, CONTENT_MATS]
SHELL_PREFIX = ("Wall_N", "Wall_S", "Wall_W", "Wall_E", "Floor_", "Ceiling_Lab")
NO_BAKE = ["Lamp_Emit", "Exit_Sign_Emit", "Display_Emit", "Indicator_Red", "B2_Slit_Glow", "Glass_Clear"]


def trim_outside(bm):
    """Drop the faces of a shell slab that look away from the room: never seen, and they would cost lightmap texels."""
    centre = Vector((0, 0, H / 2))
    bad = [f for f in bm.faces if f.normal.dot(f.calc_center_median() - centre) > 1e-4]
    bmesh.ops.delete(bm, geom=bad, context="FACES")


def stage_work():
    d = Path(arg("--work", str(Path(os.environ.get("TEMP", "/tmp")) / f"farway_{SCENE}")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def no_stamps(sc):
    """Turn off every metadata stamp, so no rendered file carries the .blend's absolute path (public repo)."""
    for p in sc.render.bl_rna.properties:
        if p.identifier.startswith("use_stamp") and not p.is_readonly:
            setattr(sc.render, p.identifier, False)
    sc.render.stamp_note_text = ""


def strip_jpeg_meta(path):
    """Drop every COM and APP1..APP15 segment from a JPEG (Blender writes its render stats there), keeping the pixels byte for byte."""
    b = Path(path).read_bytes()
    assert b[:2] == b"\xff\xd8", path
    out, i = bytearray(b[:2]), 2
    while i < len(b):
        assert b[i] == 0xFF, (path, i)
        m = b[i + 1]
        if m == 0xDA:                                     # start of scan: the rest is image data
            out += b[i:]
            break
        n = int.from_bytes(b[i + 2:i + 4], "big")
        if not (m == 0xFE or 0xE1 <= m <= 0xEF):
            out += b[i:i + 2 + n]
        i += 2 + n
    Path(path).write_bytes(bytes(out))


def setup_cycles(samples, bake=False):
    sc = bpy.context.scene
    no_stamps(sc)
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = samples
    cy.use_adaptive_sampling = not bake
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces, cy.transmission_bounces, cy.transparent_max_bounces = 8, 6, 3, 6, 8
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
    print("CYCLES device:", cy.device, [d.name for d in prefs.devices if d.use] if gpu else "CPU")
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
        if ob.name in COLLIDERS and ob.name.startswith(SHELL_PREFIX):
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
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    print(f"  unwrapping {len(bpy.context.objects_in_mode)} objects")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
    bpy.ops.uv.average_islands_scale()
    a3 = sum(area3d(o) for o in objs)
    sizes = (512, 640, 768, 896, 1024, 1280, 1536, 1792, 2048)

    def pack(S):
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / S, shape_method="CONCAVE")
        bpy.ops.object.mode_set(mode="OBJECT")
        dens = S * math.sqrt(sum(uv_area(o, "lightmap") for o in objs) / a3)
        print(f"  page {S}: {a3:.1f} m2, {dens:.1f} px/m")
        return dens
    # The margin is a fraction of the page, so the density does not scale linearly with the page: start from a guess, walk up until a page
    # reaches 30 px/m, then down while a smaller one still does; the smallest page that reaches it is packed last.
    d1024 = pack(1024)
    i = next((k for k, S in enumerate(sizes) if d1024 * S / 1024 >= 30), len(sizes) - 1)
    tried = {1024: d1024}
    while sizes[i] not in tried:
        tried[sizes[i]] = pack(sizes[i])
        if tried[sizes[i]] >= 30 or i == len(sizes) - 1:
            break
        i += 1
    while i > 0 and tried.get(sizes[i], 0) >= 30 and sizes[i - 1] not in tried:
        tried[sizes[i - 1]] = pack(sizes[i - 1])
        if tried[sizes[i - 1]] < 30:
            break
        i -= 1
    ok = [S for S in sizes if tried.get(S, 0) >= 30]
    S = ok[0] if ok else sizes[-1]
    dens = pack(S) if S != list(tried)[-1] else tried[S]
    if dens < 1e-6:
        raise RuntimeError("the lightmap pack came out empty")
    for o in objs:                                   # UV0 stays the render UV: the lightmap is the second set (TEXCOORD_1)
        o.data.uv_layers["UVMap"].active_render = True
    return S, dens


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
    no_stamps(sc)
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
    import time
    t0 = time.time()
    stage_work()
    for ob in bpy.data.collections["Lights"].objects:   # the strip lights at this file's strengths (DOWN_W, UP_W), whatever the .blend was saved with
        if ob.type == "LIGHT" and ob.name.startswith("Strip"):
            ob.data.energy = DOWN_W if ob.name.endswith("_Down") else UP_W
            print(f"  light {ob.name}: {ob.data.energy} W")
    keep_uv = "--keep-uv" in args                     # a relight: bake the saved Export objects on their own lightmap UVs and pages (the GLB's geometry stays as it is)
    exp = {o.data.materials[0].name: o for o in bpy.data.collections["Export"].objects} if keep_uv else make_export_objects()
    if keep_uv:                                       # a saved bake leaves Export hidden: it must be visible and selectable to bake
        bpy.data.collections["Export"].hide_viewport = bpy.data.collections["Export"].hide_render = False
        for o in exp.values():
            o.hide_set(False)
            o.hide_render = False
    bpy.data.collections["Art"].hide_render = True
    bpy.data.collections["Art"].hide_viewport = True
    setup_cycles(SAMPLES, bake=True)
    report = {}
    hidden = [exp[m] for m in ("Lamp_Emit", "Glass_Clear") if m in exp]
    for o in hidden:
        o.hide_render = True                         # the strip lights' diffusers (the area lights stand for their light) and the clear glass; the small glowing parts stay
    pages = []
    for n, mats in enumerate(GROUPS):                # every group unwrapped first, then the bakes
        objs = [exp[m] for m in mats if m in exp]
        print(f"lightmap {n}: {[o.name for o in objs]}")
        if keep_uv:
            old = bpy.data.images.load(str(ROOT / LM_URL.format(n)))   # the shipped map gives the page size
            S = old.size[0]
            bpy.data.images.remove(old)
            pages.append((S, S * math.sqrt(sum(uv_area(o, "lightmap") for o in objs) / sum(area3d(o) for o in objs))))
        else:
            pages.append(lightmap_uv(objs))
    for n, mats in enumerate(GROUPS):
        objs = [exp[m] for m in mats if m in exp]
        S, dens = pages[n]
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
        select_only(objs)
        for o in objs:
            o.data.uv_layers.active = o.data.uv_layers["lightmap"]
        tb = time.time()
        bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
        print(f"  bake {n}: {S}x{S} at {SAMPLES} samples took {time.time() - tb:.0f} s")
        a = denoise_image(img, S)
        rgb = a[..., :3]
        peak = rgb.max(axis=2)
        pc = np.percentile(peak[peak > 1e-5], [50, 90, 99, 99.5, 100]) if (peak > 1e-5).any() else [1.0] * 5
        scale = float(pc[3])                         # the 99.5th percentile of the lit texels maps to white; the few hotter ones clip
        print('  texel percentiles p50 p90 p99 p99.5 max:', [round(float(v), 3) for v in pc])
        out = np.ones((S, S, 4), np.float32)
        out[..., :3] = srgb_encode(rgb / scale)
        png = bpy.data.images.new(f"LM_{n}_png", S, S, alpha=False)
        png.colorspace_settings.name = "Non-Color"
        png.pixels.foreach_set(out.ravel())
        png.filepath_raw = str(stage_work() / f"{SCENE}_{n}.png")
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
        report[n] = {"size": S, "px_per_m": round(dens, 1), "scale": round(scale, 4), "p50_p90_p99_p995_max": [round(float(v), 3) for v in pc], "samples": SAMPLES,
                     "mean": round(float(rgb.mean()), 4), "materials": mats}
        print("  baked", report[n])
        bpy.data.images.remove(img)
        bpy.data.images.remove(png)
    for o in hidden:
        o.hide_render = False
    report["seconds"] = round(time.time() - t0)
    report["device"] = bpy.context.scene.cycles.device
    (stage_work() / "lightmaps.json").write_text(json.dumps(report, indent=1))
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Art"].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


def drop_addon_state():
    """The user's own add-ons keep state on the scene and the window manager (some of it local paths); the glTF exporter writes the
    scene's into the GLB's scene extras. Only Cycles' settings are kept."""
    for idb in list(bpy.data.scenes) + list(bpy.data.window_managers):
        g = idb.bl_system_properties_get()
        for k in [k for k in (g.keys() if g else []) if not k.startswith("cycles")]:
            del g[k]


def scrub_paths():
    """The .blend is committed to a public repo: no path into the work folder (the system temp folder by default) may stay in it.
    A packed image keeps its pixels in the file, so its source path is replaced by a neutral relative name; an unpacked image
    must live inside the repo. A packed image whose path (or its packed file's path) points outside the repo is rebuilt from its
    bytes by packed_image(). Every scene's render output path is cleared, the file browsers' folders too (the user's home), and
    the state the user's own add-ons keep on the scene and the window manager (their paths) is dropped; only Cycles' is kept."""
    root = str(ROOT.resolve()).lower()
    inside = lambda p: os.path.abspath(bpy.path.abspath(p)).lower().startswith(root)
    for im in list(bpy.data.images):
        if im.source != "FILE" or not im.filepath_raw:
            continue
        if im.packed_file is not None:
            if not inside(im.filepath_raw) or any(not inside(pf.filepath) for pf in im.packed_files):
                name, keep = im.name, dict(im.items())
                new = packed_image(name + "_clean", bytes(im.packed_file.data), im.colorspace_settings.name, fname=name)
                for k, v in keep.items():
                    new[k] = v
                im.user_remap(new)
                bpy.data.images.remove(im)
                new.name = name
        elif not inside(im.filepath_raw):
            raise SystemExit(f"image {im.name} is neither packed nor inside the repo")
        else:
            wipe(im, "filepath_raw", im.filepath_raw)   # the repo textures were loaded by absolute path, made relative on save
    for sc in bpy.data.scenes:
        wipe(sc.render, "filepath", "")
    drop_addon_state()
    for scr in bpy.data.screens:
        for a in scr.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and sp.params:
                    wipe(sp.params, "directory", b"", b"_")


def wipe(owner, attr, value, run="_"):
    """A path field is a fixed buffer: a shorter new value leaves the old one's tail after its end, and that tail is saved. So the
    whole buffer is filled with a neutral run first (the setter cuts it to the buffer's size), then the value is set."""
    setattr(owner, attr, run * 4096)
    setattr(owner, attr, value)


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    bpy.ops.file.make_paths_relative()
    scrub_paths()
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
    raw = stage_work() / f"{SCENE}_raw.glb"
    drop_addon_state()
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False, export_animations=False)
    print("EXPORTED", raw, raw.stat().st_size)
    bpy.data.collections["Art"].hide_viewport = False
    exp.hide_viewport = exp.hide_render = True


def stage_axes():
    """The axes check: export the marker alone through the glTF exporter and read back where it landed. A game point (x, y, z) must come out as (x, y, z)."""
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
    print(f"AXES blender centre {tuple(round(v, 3) for v in bl)} (x, -z, y of the game point {tuple(want)})")
    print(f"AXES glTF centre {tuple(round(v, 3) for v in centre)}, game point {tuple(want)}")
    assert all(abs(centre[i] - want[i]) < 1e-4 for i in range(3)), "the exporter's axes disagree with (x, -z, y)"
    assert abs(bl.x - want[0]) < 1e-4 and abs(bl.y + want[2]) < 1e-4 and abs(bl.z - want[1]) < 1e-4
    print("AXES PASS: game (x, y, z) = Blender (x, -z, y) = glTF (x, y, z)")


# ---------------------------------------------------------------- the review stills
def look_cam(name, loc, target, fov_v=75.0, ortho=None):
    cam = bpy.data.cameras.get(name) or bpy.data.cameras.new(name)
    cam.sensor_fit = "VERTICAL"
    if ortho:
        cam.type = "ORTHO"
        cam.ortho_scale = ortho
        cam.sensor_fit = "HORIZONTAL"
    else:
        cam.lens_unit = "FOV"
        cam.angle_y = math.radians(fov_v)
    cam.clip_start, cam.clip_end = 0.05, 100
    ob = bpy.data.objects.get(name) or bpy.data.objects.new(name, cam)
    if ob.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(ob)
    ob.location = B(loc)
    ob.rotation_euler = (B(target) - B(loc)).to_track_quat("-Z", "Y").to_euler() if target is not None else (0, 0, 0)
    return ob


def stage_render():
    sc = bpy.context.scene
    STILLS.mkdir(parents=True, exist_ok=True)
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
        bpy.data.collections["Export"].hide_viewport = True
    setup_cycles(arg("--samples", 128, int))
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.adaptive_threshold = 0.02
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = arg("--exposure", 0.0, float)
    which = arg("--only", "all")
    if ENGINE.upper().startswith("EEVEE"):
        ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
        sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in ids else "BLENDER_EEVEE_NEXT"
    arrive, face = K["arrive"], K["face"]
    b2 = K["b2"]
    fz = next(s for s in K["stations"] if s["id"] == "freezer")
    shots = {
        "1_arrival": look_cam("arrival", (arrive[0], 1.6, arrive[2]), (arrive[0] + face[0] * 3, 1.6, arrive[2] + face[1] * 3), 75.0),
        "2_wide": look_cam("wide", (0.0, 5.4, HZ + 4.6), (0.0, 0.5, -1.6), 64.0),
        "3_detail": look_cam("detail", (b2["x"] + 1.9, 1.45, b2["z"] + 3.0), (b2["x"] + 0.1, 1.25, b2["z"]), 60.0),
    }
    plan = look_cam("plan", (0, H + 6, 0), None, ortho=2 * HX + 0.8)
    arts = bpy.data.collections["Art"].objects
    cut_plan = [o for o in arts if o.name.startswith(("Ceiling_", "Light_", "Services_"))]
    cut_wide = [o for o in arts if o.name.startswith(("Wall_S", "Ceiling_Lab", "Exit_", "decor_extinguisher", "decor_firstaid", "decor_coats", "Coat_Rail", "Clock_", "Sign_FirePoint", "Ceiling_Vent"))
                or (o.name.startswith("Trim_") and o.name.endswith("_S"))]
    todo = [(k, v, (1920, 1080)) for k, v in shots.items()] + [("4_plan", plan, (1600, int(1600 * (2 * HZ + 0.8) / (2 * HX + 0.8))))]
    for key, cam, (w, h) in todo:
        if which not in ("all", key):
            continue
        sc.camera = cam
        for o in arts:
            o.visible_camera = True
        for o in {"4_plan": cut_plan, "2_wide": cut_wide}.get(key, []):
            o.visible_camera = False                      # a cut-away view: these stay for the light and the shadows, the camera just does not see them
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, arg("--scale", 100, int)
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        path = STILLS / f"{key}.jpg" if key != "4_plan" else stage_work() / "plan.jpg"
        sc.render.filepath = str(path)
        import time
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 400_000 and q > 40 and key != "4_plan":
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        strip_jpeg_meta(path)                             # no stamp, no render stats: nothing but the picture in a public file
        print("STILL", key, path.stat().st_size, "q", q, f"{time.time() - t0:.0f} s")
    for o in arts:
        o.visible_camera = True


if __name__ == "__main__":
    if STAGE == "textures":
        stage_textures()
        raise SystemExit(0)
    if STAGE in ("art", "all"):
        build_all()
        save_blend()
    else:
        STATIONS[:] = [Station(s) for s in K["stations"]]
    if STAGE in ("bake", "all"):
        stage_bake()
    if STAGE in ("export", "all"):
        stage_export()
    if STAGE in ("axes", "all"):
        stage_axes()
        save_blend()
    if STAGE in ("render", "all"):
        stage_render()
