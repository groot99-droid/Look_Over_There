"""Builds the museum's side galleries, scene `galleries_wing`: the NATURAL-HISTORY HALL behind the main hall's west wall and the HISTORY GALLERY
behind its east wall, each reached through a themed door in the middle bay of the hall's long walls (docs/renders/galleries_wing/README.md).

Blender is this scene's layout source (docs/BLENDER_AREAS.md, part 2): its colliders are COL_* boxes, its doors DoorLeaf_* leaves (origin at the
hinge), its links Link_*/Arrive_* empties, its arrival points Marker_* empties and its places for the page's live figures Spot_* empties, all
written to world/galleries_wing.json by tools/blender/export_scene.py. The art goes to world/galleries_wing.glb with its own four lightmaps.

    blender -b --factory-startup --python tools/blender/build_galleries_wing.py -- --stage all [--samples 512] [--render-samples 128] [--work <dir>]
    blender -b --factory-startup blender/scenes/galleries_wing.blend --python tools/blender/build_galleries_wing.py -- --stage size|bake|export|axes|render
    python tools/blender/pack_scene.py galleries_wing [--work <dir>]

Stages: art (geometry, materials, models, lights, layout empties; saves blender/scenes/galleries_wing.blend) -> bake (merge by material, lightmap
UV on the fixed PAGES, Cycles bake, OIDN, 8-bit PNGs in the work folder) -> export (the GLB to the work folder, world/galleries_wing.json through
export_scene.py) -> axes (the marker-cube check) -> render (docs/renders/galleries_wing/1_arrival, 2_wide, 3_detail.jpg; the plan to the work
folder). `size` only lays out the lightmap UVs and prints the smallest page per map that gives 30 px/m (how PAGES was found); it bakes nothing.

The rooms are placed from the main hall's numbers (blender/layout/galleries.json, written by `node tools/blender/dump_layout.mjs galleries`): they
stand behind the hall's long walls, on its middle bay (z = -10), 0.2 m outside the hall's 0.2 m walls, so the three rooms share one ground plan.
Nothing in this file touches the hall's files.

The live exhibits are NOT here. The T. rex skeleton and the soldier figures come alive at night and the page draws and animates them; this scene
only gives them their places (Spot_trex on the stone platform, Spot_warrior_<nn> on the era plinths, Spot_specimen_<n> on the empty specimen
plinths). The T. rex's grey stand-in (its real size, 12 m by 3.7 m) is in the bake, so the platform keeps its contact shadow; the soldiers'
stand-ins are shown in the review stills only. No stand-in is ever exported.

What came from the owner's Chronicle Museum (Earth_Worldbuild/_Museum: web/js/procroom.js, doors.js, matlib.js, build_layout.py): the moulding
profiles (skirting, dado, picture rail, cornice), mitred in the corners; wall paints and trim colour; the salon hang with bevelled frames by era;
picture lights; sconces either side of each door; laylights and chandeliers; column pedestals; themed doors (Doric pediment, round arch with
keystone) with a plaque; its CC0 textures (ambientCG Marble012, PaintedPlaster017, Metal048A) and its CC0 models (Poly Haven chandeliers, bench,
vases, mirror, bust, bull and horse heads; Smithsonian Open Access scans) in blender/models/galleries/. The models keep their full geometry.
"""
import json
import math
import os
import re
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector, Quaternion

ROOT = Path(__file__).resolve().parents[2]
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


SCENE = "galleries_wing"
LAYOUT = ROOT / "blender/layout/galleries.json"           # the main hall's numbers (read only)
TEX = ROOT / "blender/textures/galleries"
MODELS = ROOT / "blender/models/galleries"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
STILLS = Path(arg("--stills", str(ROOT / f"docs/renders/{SCENE}")))
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"
MARGIN_PX = 8
STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 512, int)
DEVICE = arg("--device", "auto")

L = json.loads(LAYOUT.read_text())
K = L["constants"]
HCOL = {c["s"]: c for c in L["world"]["colliders"]}
HX = K["half"][0]                              # the hall's half width (inner face of its long walls)
WALL_T = HCOL["Wall_W"]["max"][0] - HCOL["Wall_W"]["min"][0]     # 0.2 m
ROWS = sorted({z for _, z in K["homes"]})
STEP = ROWS[1] - ROWS[0]
SIDE_Z = ROWS[1] - STEP / 2                    # the middle bay of the hall's long walls: z = -10
SIDE_W = 1.8                                    # a side door's opening (two 0.9 m leaves); the hall's build cuts the same openings
DORIC_H, ARCH_H = 2.6, 3.0                      # the Doric door's leaves; the arched door's crown (its leaves stop at the springing line, 2.1 m)
WX = HX + 2 * WALL_T                            # the galleries' walls stand against the outside of the hall's: their inner face is at |x| = 6.4

# the rooms (game axes): interior x0..x1, z0..z1, height h; `door` is the wall (inward normal) that backs onto the hall
NH = dict(name="NatHist", x0=-WX - 18.0, x1=-WX, z0=SIDE_Z - 6.0, z1=SIDE_Z + 6.0, h=6.5, door="-x", paint="#8c9a78")
HG = dict(name="History", x0=WX, x1=WX + 14.0, z0=SIDE_Z - 6.0, z1=SIDE_Z + 6.0, h=5.0, door="+x", paint="#6f83a0")
ROOMS = [NH, HG]
DADO = 0.95


def srgb_lin(hexs):
    c = [int(hexs[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def B(p):
    """game (x, y, z) -> Blender (x, -z, y); also for directions"""
    return Vector((p[0], -p[2], p[1]))


# ---------------------------------------------------------------- materials
IMG_CACHE, MATS, TILES = {}, {}, {}


def image(fn):
    if fn not in IMG_CACHE:
        im = bpy.data.images.load(str(TEX / fn))
        im.colorspace_settings.name = "sRGB"
        IMG_CACHE[fn] = im
    return IMG_CACHE[fn]


def set_blend(m):
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(m, attr, val)
        except (AttributeError, TypeError):
            pass


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, diff=None, tint=None, emit=None, alpha=None, tile=None, img=None):
    """A Principled material. `tint` multiplies the diffuse texture (a Mix node set to Multiply, which the glTF exporter writes as baseColorFactor)."""
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
    if diff or img:
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "UVMap"
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = img or image(diff)
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
    TILES[name] = tile or 1.0
    MATS[name] = m
    return m


PARQ, MARB, PLAS, METL, WOOD = "herringbone_parquet_diff_1k.jpg", "Marble012_color_1k.jpg", "PaintedPlaster017_color_1k.jpg", "Metal048A_color_512.jpg", "dark_wood_diff_1k.jpg"


def make_materials():
    material("Floor_Parquet", diff=PARQ, tint=(0.95, 0.85, 0.74), rough=0.6, tile=3.4)
    material("Floor_Stone", diff=MARB, tint=srgb_lin("#d9d0c2"), rough=0.45, tile=2.0)
    material("Floor_Border", diff=MARB, tint=srgb_lin("#5a504a"), rough=0.35, tile=2.0)
    for R in ROOMS:
        material(f"Wall_Paint_{R['name']}", diff=PLAS, tint=srgb_lin(R["paint"]), rough=0.95, tile=3.0)
    material("Ceiling_Paint", diff=PLAS, tint=srgb_lin("#f4efe4"), rough=0.95, tile=3.0)
    material("Trim_Paint", diff=PLAS, tint=srgb_lin("#efe6d6"), rough=0.7, tile=1.0)
    material("Wainscot_Wood", diff=WOOD, tint=(0.95, 0.88, 0.84), rough=0.5, tile=0.9)
    material("Door_Wood", diff=WOOD, tint=(1.0, 0.92, 0.86), rough=0.5, tile=0.9)
    material("Frame_Wood", diff=WOOD, tint=(0.55, 0.47, 0.42), rough=0.45, tile=0.6)
    material("Marble_White", diff=MARB, tint=srgb_lin("#f1ece2"), rough=0.4, tile=2.0)
    material("Marble_Dark", diff=MARB, tint=srgb_lin("#4a403b"), rough=0.4, tile=2.0)
    material("Stone", diff=PLAS, tint=srgb_lin("#c2b49a"), rough=0.9, tile=1.5)
    material("Frame_Gold", diff=METL, tint=srgb_lin("#f0c56a"), rough=0.32, metal=0.9, tile=0.5)
    material("Metal_Brass", diff=METL, tint=srgb_lin("#d3a35d"), rough=0.38, metal=0.9, tile=0.5)
    material("Metal_Dark", color=(0.03, 0.03, 0.035), rough=0.4, metal=0.8)
    material("Lamp_Emit", color=(1.0, 0.85, 0.62), rough=0.4, emit=((1.0, 0.80, 0.55), 14.0))
    material("Laylight_Glass", color=(1.0, 0.96, 0.88), rough=0.9, emit=((1.0, 0.93, 0.80), 2.5))
    material("Vitrine_Glass", color=(0.92, 0.96, 0.98), rough=0.05, alpha=0.12)
    material("Standin_Grey", color=(0.45, 0.45, 0.45), rough=0.8)


# ---------------------------------------------------------------- geometry helpers (world space, identity object transforms)
def cube(bm, gmin, gmax):
    a, b = B(gmin), B(gmax)
    c = (a + b) / 2
    s = Vector((abs(a.x - b.x), abs(a.y - b.y), abs(a.z - b.z)))
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((s.x, s.y, s.z, 1.0)))


def cyl(bm, p0, p1, r0, r1=None, seg=16, cap=True):
    a, b = B(p0), B(p1)
    d = b - a
    q = d.to_track_quat("Z", "Y")
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                          matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())


def sphere(bm, p, r, seg=12):
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2 + 1, radius=r, matrix=Matrix.Translation(B(p)))


def gface(bm, pts, want):
    """A face through game points, turned so its normal points along the game direction `want`."""
    f = bm.faces.new([bm.verts.new(B(p)) for p in pts])
    f.normal_update()
    if f.normal.dot(B(want)) < 0:
        f.normal_flip()
    return f


def box_uv(bm, tile):
    """UV0: box projection in metres / tile, from world positions."""
    uvl = bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y
            u, v = (gz, gy) if ax == 0 else (gx, gy) if ax == 1 else (gx, gz)
            lp[uvl].uv = (u / tile, v / tile)


def finish(name, bm, mat, coll, smooth=False, tile=None, keep_uv=False, recalc=True):
    for e in bm.edges:
        if smooth and len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) < math.radians(35)
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
    coll.objects.link(ob)
    return ob


ART = STANDIN = BAKE_STANDIN = LAYOUT_C = DOORS_C = None


def part(name, mat, build, smooth=False, tile=None, coll=None, recalc=True):
    bm = bmesh.new()
    build(bm)
    return finish(name, bm, mat, coll or ART, smooth, tile, recalc=recalc)


# walls are named by their inward normal: "+x" is a room's west wall (face x0); `a` runs along it (+z on x-walls, +x on z-walls)
NVEC = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}
ADIR = {"+x": (0, 0, 1), "-x": (0, 0, 1), "+z": (1, 0, 0), "-z": (1, 0, 0)}
WNAME = {"+x": "W", "-x": "E", "+z": "N", "-z": "S"}
RIGHT = {"+x": (0, 0, -1), "-x": (0, 0, 1), "+z": (1, 0, 0), "-z": (-1, 0, 0)}


def span(R, n):
    return (R["z0"], R["z1"]) if n[1] == "x" else (R["x0"], R["x1"])


def on_wall(R, n, a, y, d):
    if n == "+x":
        return (R["x0"] + d, y, a)
    if n == "-x":
        return (R["x1"] - d, y, a)
    if n == "+z":
        return (a, y, R["z0"] + d)
    return (a, y, R["z1"] - d)


def wall_box(bm, R, n, a0, a1, y0, y1, d0, d1):
    p, q = on_wall(R, n, a0, y0, d0), on_wall(R, n, a1, y1, d1)
    cube(bm, [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)])


def vadd(*terms):
    out = [0.0, 0.0, 0.0]
    for k, v in terms:
        for i in range(3):
            out[i] += k * v[i]
    return tuple(out)


def sweep(bm, R, n, a0, a1, prof, mitre=(True, True)):
    """A moulding: profile [(u out from the wall, v height)] swept along the wall from a0 to a1; inside corners mitred, other ends capped."""
    N, A = NVEC[n], ADIR[n]

    def P(end, u, v):
        a = (a0 + (u if mitre[0] else 0.0)) if end == 0 else (a1 - (u if mitre[1] else 0.0))
        return on_wall(R, n, a, v, u)
    for (u0, v0), (u1, v1) in zip(prof, prof[1:]):
        gface(bm, [P(0, u0, v0), P(1, u0, v0), P(1, u1, v1), P(0, u1, v1)], vadd((v1 - v0, N), (-(u1 - u0), (0, 1, 0))))
    for end, m, s in ((0, mitre[0], -1), (1, mitre[1], 1)):
        if not m:
            gface(bm, [P(end, u, v) for u, v in prof], tuple(s * x for x in A))


def ring_profile(bm, R, n, a0, a1, y0, y1, prof):
    """A rectangular moulding on a wall (a frame, a wainscot panel): prof [(inset, depth)] from the outer back edge to the inner back edge."""
    N, A = NVEC[n], ADIR[n]
    rects = [[on_wall(R, n, a, y, d) for a, y in ((a0 + s, y0 + s), (a1 - s, y0 + s), (a1 - s, y1 - s), (a0 + s, y1 - s))] for s, d in prof]
    outs = [(0, -1, 0), A, (0, 1, 0), tuple(-x for x in A)]
    for k in range(len(prof) - 1):
        ds, dd = prof[k + 1][0] - prof[k][0], prof[k + 1][1] - prof[k][1]
        if abs(ds) < 1e-9 and abs(dd) < 1e-9:
            continue
        for i in range(4):
            j = (i + 1) % 4
            gface(bm, [rects[k][i], rects[k][j], rects[k + 1][j], rects[k + 1][i]], vadd((ds, N), (dd, outs[i])))


def profiles(h):
    """Chronicle Museum moulding profiles (procroom.js PROFILES) for a room h high; below head height nothing is more than 4.5 cm proud."""
    rail = h - 0.9
    return dict(
        skirting=[(0, 0), (0.035, 0), (0.035, 0.2), (0.025, 0.215), (0.032, 0.245), (0.02, 0.27), (0, 0.28)],
        dado=[(0, DADO - 0.07), (0.032, DADO - 0.07), (0.044, DADO - 0.05), (0.032, DADO), (0, DADO + 0.01)],
        rail=[(0, rail - 0.07), (0.035, rail - 0.07), (0.048, rail - 0.04), (0.03, rail), (0, rail)],
        cornice=[(0, h - 0.5), (0.03, h - 0.5), (0.03, h - 0.42), (0.08, h - 0.37), (0.08, h - 0.3), (0.15, h - 0.24), (0.17, h - 0.16),
                 (0.3, h - 0.07), (0.36, h), (0, h)], rail_y=rail)


FRAME_PROF = {"gilt-ornate": [(0, 0), (0, .028), (.18, .042), (.42, .034), (.62, .045), (.85, .03), (1, .018), (1, 0)],
              "gilt-simple": [(0, 0), (0, .026), (.35, .040), (.75, .030), (1, .016), (1, 0)],
              "dark-wood": [(0, 0), (0, .030), (.5, .035), (1, .022), (1, 0)]}
FRAME_MAT = {"gilt-ornate": "Frame_Gold", "gilt-simple": "Frame_Gold", "dark-wood": "Frame_Wood"}
PANEL_PROF = [(0, 0), (0, 0.012), (0.03, 0.018), (0.055, 0.012), (0.055, 0)]

DOORS, FRAMES, LIGHTS, OBSTACLES = [], [], [], []    # OBSTACLES: wall spans (room, normal, a0, a1) where the wainscot panels stop (vitrines)


def runs(R, n, gaps):
    lo, hi = span(R, n)
    cuts = sorted(g for g in gaps if g[1] > lo and g[0] < hi)
    out, a, m = [], lo, True
    for g0, g1 in cuts:
        out.append((a, g0, m, False))
        a, m = g1, False
    out.append((a, hi, m, True))
    return [r for r in out if r[1] - r[0] > 0.05]


def gaps_of(R, n, below=None):
    return [g for (r, nn, a, g, kind, top) in DOORS if r is R and nn == n and (below is None or top > below)]


# ---------------------------------------------------------------- layout objects (the Layout collection: exported to the JSON, never to the GLB)
def col_box(name, mn, mx):
    """A COL_ collider box (game min, max)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    cube(bm, mn, mx)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    LAYOUT_C.objects.link(ob)
    ob.hide_render = True
    ob.display_type = "WIRE"
    return {"min": list(mn), "max": list(mx)}


def empty(name, pos, face=None, props=None):
    """An empty at game `pos`; `face` (game x, z) turns it so its -Y axis points that way (export_scene.py reads it back)."""
    ob = bpy.data.objects.new(name, None)
    ob.location = B(pos)
    if face:
        ob.rotation_euler = (0, 0, math.atan2(face[0], face[1]))
    for k, v in (props or {}).items():
        ob[k] = v
    ob.empty_display_size = 0.3
    LAYOUT_C.objects.link(ob)
    return ob


# ---------------------------------------------------------------- the shell
def build_shell(R):
    """Floor, walls (paint above a wainscot), ceiling with laylight openings, and the COL_ boxes they stand for."""
    nm, t = R["name"], WALL_T
    x0, x1, z0, z1, h = R["x0"], R["x1"], R["z0"], R["z1"], R["h"]
    floor = col_box(f"COL_{nm}_Floor", (x0 - t, -t, z0 - t), (x1 + t, 0.0, z1 + t))
    ceil = col_box(f"COL_{nm}_Ceiling", (x0 - t, h, z0 - t), (x1 + t, h + t, z1 + t))
    walls = {"+z": col_box(f"COL_{nm}_Wall_N", (x0 - t, 0.0, z0 - t), (x1 + t, h, z0)),
             "-z": col_box(f"COL_{nm}_Wall_S", (x0 - t, 0.0, z1), (x1 + t, h, z1 + t))}
    for n, xa, xb, wn in (("+x", x0 - t, x0, "W"), ("-x", x1, x1 + t, "E")):
        if R["door"] != n:
            walls[n] = col_box(f"COL_{nm}_Wall_{wn}", (xa, 0.0, z0), (xb, h, z1))
            continue
        # the wall that backs onto the hall: the door's opening (SIDE_W wide, up to the leaves' top) is cut out of it, as the hall's build cuts
        # the hall's side of it; the closed leaves (the page's door boxes) shut it until the page opens them
        a0, a1, top = R["opening"]
        walls[n] = col_box(f"COL_{nm}_Wall_{wn}", (xa, 0.0, z0), (xb, h, a0))
        walls[n + "b"] = col_box(f"COL_{nm}_Wall_{wn}_Door_S", (xa, 0.0, a1), (xb, h, z1))
        walls[n + "c"] = col_box(f"COL_{nm}_Wall_{wn}_Door_Head", (xa, top, a0), (xb, h, a1))
        mat = "Marble_White" if R is NH else "Stone"

        def reveal(bm, n=n, a0=a0, a1=a1, top=top):
            e = 0.03
            wall_box(bm, R, n, a0, a0 + e, 0.0, top, -t, 0.0)
            wall_box(bm, R, n, a1 - e, a1, 0.0, top, -t, 0.0)
            wall_box(bm, R, n, a0, a1, top - e, top, -t, 0.0)
        part(f"Door_{nm}_Reveal", mat, reveal)
    mn, mx = floor["min"], floor["max"]
    b = 0.5
    field = "Floor_Stone" if R is NH else "Floor_Parquet"
    part(f"Floor_{nm}_Field", field, lambda bm: cube(bm, (x0 + b, mn[1], z0 + b), (x1 - b, mx[1], z1 - b)))

    def border(bm):
        cube(bm, (mn[0], mn[1], mn[2]), (mx[0], mx[1], z0 + b))
        cube(bm, (mn[0], mn[1], z1 - b), (mx[0], mx[1], mx[2]))
        cube(bm, (mn[0], mn[1], z0 + b), (x0 + b, mx[1], z1 - b))
        cube(bm, (x1 - b, mn[1], z0 + b), (mx[0], mx[1], z1 - b))
    part(f"Floor_{nm}_Border", "Floor_Border", border)
    for key, c in walls.items():
        a, q = c["min"], c["max"]
        wn = WNAME[key[:2]] + key[2:]
        part(f"Wall_{nm}_{wn}", f"Wall_Paint_{nm}", lambda bm: cube(bm, (a[0], max(DADO, a[1]), a[2]), (q[0], q[1], q[2])))
        if a[1] < DADO:
            part(f"Wall_{nm}_{wn}_Lower", "Wainscot_Wood", lambda bm: cube(bm, (a[0], a[1], a[2]), (q[0], DADO, q[2])))
    holes = R["lay"]                                  # [(xc, zc, hx, hz)]
    xs = sorted({x0 - t, x1 + t} | {v for xc, zc, hx, hz in holes for v in (xc - hx, xc + hx)})
    zs = sorted({z0 - t, z1 + t} | {v for xc, zc, hx, hz in holes for v in (zc - hz, zc + hz)})

    def ceiling(bm):
        for i in range(len(xs) - 1):
            for j in range(len(zs) - 1):
                cx, cz = (xs[i] + xs[i + 1]) / 2, (zs[j] + zs[j + 1]) / 2
                if any(abs(cx - xc) < hx and abs(cz - zc) < hz for xc, zc, hx, hz in holes):
                    continue
                cube(bm, (xs[i], h, zs[j]), (xs[i + 1], h + t, zs[j + 1]))
    part(f"Ceiling_{nm}", "Ceiling_Paint", ceiling)
    build_laylights(R)


def build_laylights(R):
    """Chronicle's laylight: a glazed panel in the ceiling lit from above: a painted lining and frame, glazing bars, an emissive diffuser
    (Laylight_Glass, no lightmap) and an area light just under it for the bake and the stills."""
    nm, h, t = R["name"], R["h"], WALL_T
    y0, y1 = h, h + t
    holes = R["lay"]
    th = 0.03

    def lining(bm):
        for xc, zc, hx, hz in holes:
            cube(bm, (xc - hx, y0, zc - hz), (xc + hx, y1, zc - hz + th))
            cube(bm, (xc - hx, y0, zc + hz - th), (xc + hx, y1, zc + hz))
            cube(bm, (xc - hx, y0, zc - hz), (xc - hx + th, y1, zc + hz))
            cube(bm, (xc + hx - th, y0, zc - hz), (xc + hx, y1, zc + hz))
            cube(bm, (xc - hx - 0.12, y0 - 0.05, zc - hz - 0.12), (xc + hx + 0.12, y0, zc - hz))
            cube(bm, (xc - hx - 0.12, y0 - 0.05, zc + hz), (xc + hx + 0.12, y0, zc + hz + 0.12))
            cube(bm, (xc - hx - 0.12, y0 - 0.05, zc - hz), (xc - hx, y0, zc + hz))
            cube(bm, (xc + hx, y0 - 0.05, zc - hz), (xc + hx + 0.12, y0, zc + hz))
            nx, nz = max(2, round(hx * 2 / 0.8)), max(2, round(hz * 2 / 0.8))
            for k in range(1, nx):
                x = xc - hx + 2 * hx * k / nx
                cube(bm, (x - 0.02, y1 - 0.1, zc - hz), (x + 0.02, y1 - 0.03, zc + hz))
            for k in range(1, nz):
                z = zc - hz + 2 * hz * k / nz
                cube(bm, (xc - hx, y1 - 0.1, z - 0.02), (xc + hx, y1 - 0.03, z + 0.02))
    part(f"Laylight_{nm}_Frame", "Trim_Paint", lining)

    def panes(bm):
        for xc, zc, hx, hz in holes:
            gface(bm, [(xc - hx, y1 - 0.03, zc - hz), (xc + hx, y1 - 0.03, zc - hz), (xc + hx, y1 - 0.03, zc + hz), (xc - hx, y1 - 0.03, zc + hz)], (0, -1, 0))
    part(f"Laylight_{nm}_Pane", "Laylight_Glass", panes, tile=1.0, recalc=False)
    for xc, zc, hx, hz in holes:
        LIGHTS.append(dict(name=f"Laylight_{nm}_{len(LIGHTS)}", kind="AREA", pos=(xc, y0 - 0.02, zc), aim=(xc, 0, zc), power=R["lay_w"] * (hx * hz),
                           color=(1.0, 0.95, 0.86), size=(2 * hx - 0.1, 2 * hz - 0.1)))


def build_mouldings(R):
    nm = R["name"]
    P = profiles(R["h"])

    def walls(bm, prof, below):
        for n in NVEC:
            for a0, a1, m0, m1 in runs(R, n, gaps_of(R, n, below)):
                sweep(bm, R, n, a0, a1, prof, (m0, m1))
    part(f"Trim_{nm}_Skirting", "Marble_Dark", lambda bm: walls(bm, P["skirting"], 0.0), recalc=False)
    part(f"Trim_{nm}_Dado", "Wainscot_Wood", lambda bm: walls(bm, P["dado"], 0.0), recalc=False)
    part(f"Trim_{nm}_PictureRail", "Trim_Paint", lambda bm: walls(bm, P["rail"], P["rail_y"] - 0.08), recalc=False)
    part(f"Cornice_{nm}", "Trim_Paint", lambda bm: walls(bm, P["cornice"], R["h"] - 0.5), recalc=False)

    def panels(bm):
        for n in NVEC:
            stops = gaps_of(R, n, 0.0) + [(a0, a1) for (r, nn, a0, a1) in OBSTACLES if r is R and nn == n]
            for a0, a1, _, _ in runs(R, n, stops):
                ln = a1 - a0 - 0.3
                if ln < 0.5:
                    continue
                k = max(1, round(ln / 1.4))
                w = (ln - 0.2 * (k - 1)) / k
                for i in range(k):
                    s = a0 + 0.15 + i * (w + 0.2)
                    ring_profile(bm, R, n, s, s + w, 0.36, DADO - 0.16, PANEL_PROF)
    part(f"Trim_{nm}_Panels", "Wainscot_Wood", panels, recalc=False)


def build_frames(R):
    """Empty frames in the Chronicle salon manner (the paintings were taken down), bevelled by era, on brass wires from the picture rail; a
    picture light over every frame 1.4 m or wider."""
    nm = R["name"]
    rail = profiles(R["h"])["rail_y"]
    mine = [f for f in FRAMES if f[0] is R]
    for i, (_, n, a, yc, w, h, style) in enumerate(mine):
        t = {"gilt-ornate": 0.11, "gilt-simple": 0.075, "dark-wood": 0.065}[style]
        part(f"Frame_{nm}_{i}", FRAME_MAT[style], lambda bm: ring_profile(bm, R, n, a - w / 2, a + w / 2, yc - h / 2, yc + h / 2,
                                                                          [(s * t, d) for s, d in FRAME_PROF[style]]), recalc=False)

    def wires(bm):
        for _, n, a, yc, w, h, style in mine:
            top = yc + h / 2
            for k in (-1, 1):
                cyl(bm, on_wall(R, n, a + k * w * 0.32, rail - 0.07, 0.02), on_wall(R, n, a + k * w * 0.18, top, 0.02), 0.002, 0.002, 4, cap=False)
                cyl(bm, on_wall(R, n, a + k * w * 0.32, rail - 0.085, 0.018), on_wall(R, n, a + k * w * 0.32, rail - 0.05, 0.018), 0.008, 0.008, 6)
    part(f"Frame_{nm}_Wires", "Metal_Brass", wires)
    lit = [f for f in mine if f[4] >= 1.4]

    def picture_lights(bm):
        for _, n, a, yc, w, h, style in lit:
            top = yc + h / 2 + 0.14
            lw = min(1.2, w * 0.6)
            wall_box(bm, R, n, a - 0.04, a + 0.04, top - 0.03, top + 0.06, 0.0, 0.02)
            cyl(bm, on_wall(R, n, a, top + 0.015, 0.01), on_wall(R, n, a, top + 0.08, 0.24), 0.009, 0.009, 8)
            cyl(bm, on_wall(R, n, a - lw / 2, top + 0.08, 0.26), on_wall(R, n, a + lw / 2, top + 0.08, 0.26), 0.03, 0.03, 16)
    part(f"Picture_Lights_{nm}", "Metal_Brass", picture_lights, smooth=True)

    def tubes(bm):
        for _, n, a, yc, w, h, style in lit:
            top = yc + h / 2 + 0.14
            lw = min(1.2, w * 0.6)
            cyl(bm, on_wall(R, n, a - lw / 2 + 0.02, top + 0.055, 0.245), on_wall(R, n, a + lw / 2 - 0.02, top + 0.055, 0.245), 0.012, 0.012, 8)
    part(f"Picture_Light_Tubes_{nm}", "Lamp_Emit", tubes, smooth=True)
    for _, n, a, yc, w, h, style in lit:
        top = yc + h / 2 + 0.14
        LIGHTS.append(dict(name=f"Picture_Light_{nm}_{len(LIGHTS)}", kind="SPOT", pos=on_wall(R, n, a, top + 0.03, 0.26),
                           aim=on_wall(R, n, a, yc - h * 0.3, 0.0), power=120.0 if w < 3 else 220.0, color=(1.0, 0.82, 0.6), size=0.15, cone=120, blend=0.8))


def salon(R, n, a, y=2.05, big="gilt-ornate", small="dark-wood", top="gilt-simple"):
    """A Chronicle salon cluster centred at `a`: a large frame, two narrower ones either side, two small ones above."""
    FRAMES.append((R, n, a, y, 1.7, 1.3, big))
    for k in (-1, 1):
        FRAMES.append((R, n, a + k * 1.55, y - 0.1, 0.7, 0.9, small))
        FRAMES.append((R, n, a + k * 0.5, y + 1.25, 0.75, 0.55, top))


# ---------------------------------------------------------------- doors, plaques, sconces
GLYPHS = {"E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"], "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
          "I": ["111", "010", "010", "010", "010", "010", "111"], "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
          "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"], "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
          "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"], "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
          "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"], "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
          "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"], "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
          "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"], "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
          "G": ["01111", "10000", "10000", "10011", "10001", "10001", "01111"], "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
          "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"], "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
          "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"], "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
          "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"], " ": ["000"] * 7}


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


def text_pixels(text, w, h, bg, fg, border=None):
    """Own pixel font, gold on dark, centred; the scale is the largest that fits."""
    cols = sum(len(GLYPHS[ch][0]) + 1 for ch in text) - 1
    s = max(1, min((w - 24) // cols, (h - 16) // 7))
    img = np.zeros((h, w, 3), np.float32)
    img[:] = bg
    x = (w - cols * s) // 2
    y0 = (h - 7 * s) // 2
    for ch in text:
        g = GLYPHS[ch]
        for r, row in enumerate(g):
            for c, v in enumerate(row):
                if v == "1":
                    img[y0 + r * s:y0 + (r + 1) * s, x + c * s:x + (c + 1) * s] = fg
        x += (len(g[0]) + 1) * s
    if border:
        b = border
        img[b:2 * b, b:-b] = img[-2 * b:-b, b:-b] = fg
        img[b:-b, b:2 * b] = img[b:-b, -2 * b:-b] = fg
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def plaque_mat(mname, text, w=512, h=144):
    if mname not in MATS:
        textured(mname, mk_image(mname, text_pixels(text, w, h, (0.10, 0.07, 0.05), (0.92, 0.80, 0.52), border=max(3, h // 24))))
    return mname


def plaque(R, n, a, y, text, mname):
    plaque_mat(mname, text)
    nm = R["name"]
    part(f"Plaque_{nm}_{WNAME[n]}_Back", "Metal_Brass", lambda bm: wall_box(bm, R, n, a - 0.6, a + 0.6, y - 0.2, y + 0.2, 0.0, 0.035))
    panel(f"Plaque_{nm}_{WNAME[n]}", mname, on_wall(R, n, a, y, 0.0355), n, 1.1, 1.1 * 144 / 512)


def door_leaf(R, n, a0, a1, top, hinge_end, name):
    """One leaf, its own object in the Doors collection with its origin at the hinge (the page swings it by name): 3.5 cm proud of the wall with two
    raised fields; custom properties for export_scene.py (closed_yaw_deg: the leaf's local +X runs from the hinge along it; swing_deg opens it into the room)."""
    bm = bmesh.new()
    wall_box(bm, R, n, a0, a1, 0.0, top, 0.0, 0.035)
    for yy0, yy1 in ((0.18, top * 0.38), (top * 0.45, top - 0.18)):
        wall_box(bm, R, n, a0 + 0.12, a1 - 0.12, yy0, yy1, 0.035, 0.045)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    meet = a1 - 0.06 if hinge_end == 0 else a0 + 0.035                          # a wooden pull by the meeting edge: part of the leaf, so it swings with it
    wall_box(bm, R, n, meet, meet + 0.025, 0.95, 1.3, 0.045, 0.058)
    bm.loops.layers.uv.new("UVMap")
    box_uv(bm, TILES["Door_Wood"])
    hinge = on_wall(R, n, a0 if hinge_end == 0 else a1, 0.0, 0.0)
    runs_dir = Vector(ADIR[n]) * (1 if hinge_end == 0 else -1)                  # game direction from the hinge along the leaf
    th = math.atan2(-runs_dir.z, runs_dir.x)                                     # three: local +X -> (cos th, -sin th)
    into = Vector(NVEC[n])
    open_dir = math.atan2(-into.z, into.x)
    swing = 95.0 if math.sin(open_dir - th) > 0 else -95.0                       # turning by +95 from th must head into the room
    M = Matrix.Translation(B(hinge)) @ Matrix.Rotation(th, 4, "Z")
    bmesh.ops.transform(bm, matrix=M.inverted(), verts=bm.verts)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MATS["Door_Wood"])
    ob = bpy.data.objects.new(name, me)
    ob.matrix_world = M
    DOORS_C.objects.link(ob)
    ob["width"] = round(a1 - a0, 3)
    ob["height"] = round(top, 3)
    ob["closed_yaw_deg"] = round(math.degrees(th), 1)
    ob["swing_deg"] = swing
    ob["state"] = "closed"
    return ob


def sconces(R, n, a, half, y=2.35):
    nm = R["name"]

    def brass(bm):
        for k in (-1, 1):
            aa = a + k * (half + 0.35)
            cyl(bm, on_wall(R, n, aa, y - 0.1, 0.0), on_wall(R, n, aa, y - 0.1, 0.02), 0.08, 0.08, 16)
            cyl(bm, on_wall(R, n, aa, y - 0.1, 0.02), on_wall(R, n, aa, y - 0.1, 0.24), 0.015, 0.015, 8)
            cyl(bm, on_wall(R, n, aa, y - 0.12, 0.26), on_wall(R, n, aa, y, 0.26), 0.035, 0.06, 14)
    part(f"Sconces_{nm}_{WNAME[n]}", "Metal_Brass", brass, smooth=True)

    def bulbs(bm):
        for k in (-1, 1):
            sphere(bm, on_wall(R, n, a + k * (half + 0.35), y + 0.05, 0.26), 0.05, 12)
    part(f"Sconce_Bulbs_{nm}_{WNAME[n]}", "Lamp_Emit", bulbs, smooth=True)
    for k in (-1, 1):
        LIGHTS.append(dict(name=f"Sconce_{nm}_{len(LIGHTS)}", kind="POINT", pos=on_wall(R, n, a + k * (half + 0.35), y + 0.05, 0.26), power=60.0,
                           color=(1.0, 0.78, 0.52), size=0.05))


def tri(bm, R, n, a, y, w, hh, d0, d1):
    pts = [(a - w / 2, y), (a + w / 2, y), (a, y + hh)]
    f = [bm.verts.new(B(on_wall(R, n, p[0], p[1], d1))) for p in pts]
    b = [bm.verts.new(B(on_wall(R, n, p[0], p[1], d0))) for p in pts]
    bm.faces.new(f)
    bm.faces.new(b[::-1])
    for i in range(3):
        j = (i + 1) % 3
        bm.faces.new((b[i], b[j], f[j], f[i]))


def door_pair(R, n, a, top, tag):
    """Two leaves meeting at `a`, hinged at the opening's sides."""
    w = SIDE_W
    door_leaf(R, n, a - w / 2, a - 0.004, top, 0, f"DoorLeaf_{tag}_A")
    door_leaf(R, n, a + 0.004, a + w / 2, top, 1, f"DoorLeaf_{tag}_B")


def door_doric(R, n, a, text, mname, tag, w=SIDE_W, h=DORIC_H):
    """Chronicle's doric-pediment door: marble casing, flat pilasters (4.5 cm), entablature, pediment with a gilt tympanum, the plaque on the
    frieze, two closed leaves."""
    nm = R["name"]
    cw = 0.22
    px = w / 2 + cw + 0.3
    ent0, ent1 = h + cw, h + cw + 0.42
    pedW = w + 2 * cw + 1.4

    def casing(bm):
        wall_box(bm, R, n, a - w / 2 - cw, a - w / 2, 0.0, h + cw, 0.0, 0.045)
        wall_box(bm, R, n, a + w / 2, a + w / 2 + cw, 0.0, h + cw, 0.0, 0.045)
        wall_box(bm, R, n, a - w / 2 - cw, a + w / 2 + cw, h, h + cw, 0.0, 0.045)
        for k in (-1, 1):
            wall_box(bm, R, n, a + k * px - 0.18, a + k * px + 0.18, 0.0, ent0, 0.0, 0.04)
            wall_box(bm, R, n, a + k * px - 0.22, a + k * px + 0.22, 0.0, 0.3, 0.0, 0.045)
            wall_box(bm, R, n, a + k * px - 0.24, a + k * px + 0.24, ent0 - 0.16, ent0, 0.0, 0.1)
        wall_box(bm, R, n, a - pedW / 2, a + pedW / 2, ent0, ent1, 0.0, 0.12)
        wall_box(bm, R, n, a - pedW / 2 - 0.06, a + pedW / 2 + 0.06, ent1, ent1 + 0.06, 0.0, 0.15)
        tri(bm, R, n, a, ent1 + 0.06, pedW + 0.1, (pedW + 0.1) * 0.2, 0.0, 0.14)
    part(f"Door_{nm}_Surround", "Marble_White", casing)
    part(f"Door_{nm}_Tympanum", "Frame_Gold", lambda bm: tri(bm, R, n, a, ent1 + 0.12, pedW - 0.5, (pedW - 0.5) * 0.2 - 0.06, 0.14, 0.16))
    R["opening"] = (a - w / 2, a + w / 2, h)
    door_pair(R, n, a, h, tag)
    plaque(R, n, a, (ent0 + ent1) / 2, text, mname)
    DOORS.append((R, n, a, (a - px - 0.25, a + px + 0.25), "doric", ent1))
    sconces(R, n, a, px + 0.22)
    return h


def door_arch(R, n, a, text, mname, tag, w=SIDE_W, h=ARCH_H):
    """Chronicle's round-arch-keystone door: stone jambs to the springing line (2.1 m), a stone arch ring, an outer marble order and a keystone;
    the leaves stop at the springing line under a wooden tympanum."""
    nm = R["name"]
    cw = 0.22
    r = w / 2
    spr = h - r

    def arcring(bm, r0, r1, d0, d1, seg=20):
        c = on_wall(R, n, a, spr, 0.0)
        N, A = NVEC[n], ADIR[n]

        def P(rr, t, d):
            return vadd((1, c), (rr * math.cos(t), A), (rr * math.sin(t), (0, 1, 0)), (d, N))
        for i in range(seg):
            t0, t1 = math.pi * i / seg, math.pi * (i + 1) / seg
            tm = (t0 + t1) / 2
            gface(bm, [P(r0, t0, d1), P(r1, t0, d1), P(r1, t1, d1), P(r0, t1, d1)], N)
            gface(bm, [P(r1, t0, d0), P(r1, t1, d0), P(r1, t1, d1), P(r1, t0, d1)], vadd((math.cos(tm), A), (math.sin(tm), (0, 1, 0))))
            gface(bm, [P(r0, t0, d0), P(r0, t1, d0), P(r0, t1, d1), P(r0, t0, d1)], vadd((-math.cos(tm), A), (-math.sin(tm), (0, 1, 0))))

    def stone(bm):
        wall_box(bm, R, n, a - r - cw, a - r, 0.0, spr, 0.0, 0.045)
        wall_box(bm, R, n, a + r, a + r + cw, 0.0, spr, 0.0, 0.045)
        wall_box(bm, R, n, a - r - cw - 0.04, a - r + 0.02, spr - 0.12, spr, 0.0, 0.07)
        wall_box(bm, R, n, a + r - 0.02, a + r + cw + 0.04, spr - 0.12, spr, 0.0, 0.07)
        arcring(bm, r, r + cw, 0.0, 0.06)
    part(f"Door_{nm}_Surround", "Stone", stone, recalc=False)

    def outer(bm):
        arcring(bm, r + cw, r + cw + 0.14, 0.0, 0.035)
        wall_box(bm, R, n, a - 0.17, a + 0.17, h + cw - 0.32, h + cw + 0.18, 0.0, 0.11)
    part(f"Door_{nm}_Order", "Marble_White", outer, recalc=False)

    def tympanum(bm):
        c = on_wall(R, n, a, spr, 0.03)
        N, A = NVEC[n], ADIR[n]
        seg = 16
        for i in range(seg):
            t0, t1 = math.pi * i / seg, math.pi * (i + 1) / seg
            gface(bm, [c, vadd((1, c), (r * math.cos(t0), A), (r * math.sin(t0), (0, 1, 0))), vadd((1, c), (r * math.cos(t1), A), (r * math.sin(t1), (0, 1, 0)))], N)
    part(f"Door_{nm}_Tympanum", "Door_Wood", tympanum, recalc=False)
    R["opening"] = (a - w / 2, a + w / 2, spr)
    door_pair(R, n, a, spr, tag)
    plaque(R, n, a, h + cw + 0.18 + 0.28, text, mname)
    DOORS.append((R, n, a, (a - r - cw - 0.2, a + r + cw + 0.2), "arch", h + cw + 0.6))
    sconces(R, n, a, r + cw + 0.14)
    return spr


# ---------------------------------------------------------------- pedestals and the Chronicle Museum's models
def column_pedestal(bm, x, z, r=0.36, h=1.1):
    """Chronicle's column pedestal (procroom.js): square plinth, tapered shaft, echinus, square abacus."""
    cube(bm, (x - r * 1.1, 0.0, z - r * 1.1), (x + r * 1.1, 0.25, z + r * 1.1))
    sh = h - 0.25 - 0.22
    cyl(bm, (x, 0.25, z), (x, 0.25 + sh * 0.5, z), r * 0.72, r * 0.70, 24)
    cyl(bm, (x, 0.25 + sh * 0.5, z), (x, 0.25 + sh, z), r * 0.70, r * 0.63, 24)
    cyl(bm, (x, 0.25 + sh, z), (x, 0.25 + sh + 0.14, z), r * 0.63, r * 0.95, 24)
    cube(bm, (x - r, h - 0.08, z - r), (x + r, h, z + r))


MCAT = None
C_G2B = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
PROPKEYS = {}


def catalogue():
    global MCAT
    if MCAT is None:
        MCAT = {}
        for f in ("models.json", "models_wing.json"):
            MCAT.update(json.loads((MODELS / f).read_text())["models"])
    return MCAT


MODEL_TRIS = {}


def import_model(mid, name, pos, base_y=0.0, face=(0, 1), target_h=None, mat_map=None):
    """A Chronicle Museum CC0 model: imported, set upright (the Smithsonian Voyager rotation the GLB does not carry), scaled to its real height,
    turned so its front (glTF +Z) faces the game direction `face`, stood at game (x, z) `pos` on base_y, its materials reduced to the base
    colour (texture x lightmap on the page). Its geometry is kept whole: nothing is decimated."""
    rec = catalogue()[mid]
    f = MODELS / mid / rec["file"]
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(f))
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    q = rec.get("voyager_rotation")
    Rm = (C_G2B @ Quaternion((q[3], q[0], q[1], q[2])).to_matrix() @ C_G2B.transposed()).to_4x4() if q else Matrix()
    bm = bmesh.new()
    mats = []
    for o in meshes:
        for s in o.material_slots:
            if s.material not in mats:
                mats.append(s.material)
        tmp = bmesh.new()
        tmp.from_mesh(o.data)
        bmesh.ops.transform(tmp, matrix=o.matrix_world, verts=tmp.verts)
        for fc in tmp.faces:
            fc.material_index = mats.index(o.material_slots[fc.material_index].material) if o.material_slots else 0
        me = bpy.data.meshes.new("tmp")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    bmesh.ops.transform(bm, matrix=Rm, verts=bm.verts)
    xs = [v.co for v in bm.verts]
    mn = Vector([min(p[i] for p in xs) for i in range(3)])
    mx = Vector([max(p[i] for p in xs) for i in range(3)])
    s = (target_h or rec["target_h"]) / (mx.z - mn.z)
    M = Matrix.Translation(B((pos[0], base_y, pos[1]))) @ Matrix.Rotation(math.atan2(face[0], face[1]), 4, "Z") @ Matrix.Scale(s, 4) \
        @ Matrix.Translation(-Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z)))
    bmesh.ops.transform(bm, matrix=M, verts=bm.verts)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ART.objects.link(ob)
    for o in new:
        bpy.data.objects.remove(o)
    MODEL_TRIS[name] = (mid, sum(len(p.vertices) - 2 for p in me.polygons))
    for p in me.polygons:
        p.use_smooth = True
    me.materials.clear()
    for m in mats:
        me.materials.append(prop_material(mid, m, mat_map))
    return ob


def prop_material(mid, src, mat_map=None):
    base = re.sub(r"\.\d{3}$", "", src.name)
    if mat_map and base in mat_map:
        return MATS[mat_map[base]]
    key = (mid, base)
    if key in PROPKEYS:
        return PROPKEYS[key]
    nt = src.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    img, color, rough, metal = None, (0.8, 0.8, 0.8), 0.6, 0.0
    if bsdf:
        color = tuple(bsdf.inputs["Base Color"].default_value)[:3]
        rough = min(1.0, max(0.25, bsdf.inputs["Roughness"].default_value))
        metal = bsdf.inputs["Metallic"].default_value

        def find_img(sock, depth=0):
            for lk in sock.links:
                nd = lk.from_node
                if nd.type == "TEX_IMAGE":
                    return nd.image
                if depth < 3:
                    for i in nd.inputs:
                        r = find_img(i, depth + 1)
                        if r:
                            return r
            return None
        img = find_img(bsdf.inputs["Base Color"])
    if img is not None and max(img.size) > 1024:
        img.scale(1024, 1024)                    # the GLB's texture goes out at 1k, as the Poly Haven ones; the scaled pixels stay packed in the .blend
        img.pack()
    n = len([k for k in PROPKEYS if k[0] == mid])
    short = mid.split("-", 1)[1].replace("-", "_")
    m = material(f"Prop_{short}" + (f"_{n}" if n else ""), color=color if img is None else (1, 1, 1), rough=rough, metal=metal, img=img)
    PROPKEYS[key] = m
    return m


def chandelier(R, mid, x, z, height, power):
    nm = R["name"]
    top = R["h"] - 0.35
    bulb = {"ph-chandelier-02": "Chandelier_02_bulb", "ph-chandelier-01": "lamps_classic_chandelier_1"}[mid]
    import_model(mid, f"Chandelier_{nm}_{len(LIGHTS)}", (x, z), base_y=top - height, target_h=height, mat_map={bulb: "Lamp_Emit"})

    def chain(bm):
        cyl(bm, (x, top - 0.02, z), (x, R["h"], z), 0.012, 0.012, 8)
        cyl(bm, (x, R["h"] - 0.04, z), (x, R["h"], z), 0.09, 0.09, 16)
    part(f"Chandelier_{nm}_{len(LIGHTS)}_Chain", "Metal_Brass", chain)
    LIGHTS.append(dict(name=f"Chandelier_{nm}_{len(LIGHTS)}", kind="POINT", pos=(x, top - height * 0.62, z), power=power, color=(1.0, 0.80, 0.56), size=0.25))


def pedestal_piece(R, mid, x, z, face, i, target_h=None):
    nm, r = R["name"], 0.36
    part(f"Pedestal_{nm}_{i}", "Marble_White", lambda bm: column_pedestal(bm, x, z, r))
    col_box(f"COL_{nm}_Pedestal_{i}", (x - r * 1.1, 0.0, z - r * 1.1), (x + r * 1.1, 1.1, z + r * 1.1))
    import_model(mid, f"Piece_{nm}_{i}", (x, z), base_y=1.1, face=face, target_h=target_h)


def bench(R, x, z, face, i):
    b = import_model("ph-bench", f"Bench_{R['name']}_{i}", (x, z), face=face)
    c = [b.matrix_world @ Vector(v) for v in b.bound_box]
    col_box(f"COL_{R['name']}_Bench_{i}", (min(p.x for p in c), 0.0, min(-p.y for p in c)), (max(p.x for p in c), max(p.z for p in c), max(-p.y for p in c)))


# ---------------------------------------------------------------- generated images (own work, numpy)
def stage_work():
    d = Path(arg("--work", str(Path(os.environ.get("TEMP", "/tmp")) / f"farway_{SCENE}")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def mk_image(name, arr):
    """A packed image from a float array (rows top to bottom), written as a PNG first (a generated image forgets its pixels on save)."""
    h, w = arr.shape[:2]
    im = bpy.data.images.new(name + "_gen", w, h, alpha=arr.shape[2] == 4)
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
    out = bpy.data.images.load(str(path))
    out.name = name
    out.colorspace_settings.name = "sRGB"
    out.pack()
    for ref in [out] + list(out.packed_files):
        attr = "filepath_raw" if ref is out else "filepath"
        setattr(ref, attr, "_" * 1000)
        setattr(ref, attr, f"//generated/{name}.png")
    return out


def textured(name, im, rough=0.9, tile=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out, bsdf, tx, uv = (nt.nodes.new(t) for t in ("ShaderNodeOutputMaterial", "ShaderNodeBsdfPrincipled", "ShaderNodeTexImage", "ShaderNodeUVMap"))
    uv.uv_map = "UVMap"
    tx.image = im
    nt.links.new(uv.outputs["UV"], tx.inputs["Vector"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    nt.links.new(tx.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    TILES[name] = tile
    MATS[name] = m
    return m


def panel(name, mat, centre, normal, w, h, coll=None):
    """A flat quad facing `normal` (a wall normal key), w wide, h tall, UV 0..1 upright."""
    r = Vector(RIGHT[normal])
    up = Vector((0, 1, 0))
    c = Vector(centre)
    pts = [c - r * w / 2 - up * h / 2, c + r * w / 2 - up * h / 2, c + r * w / 2 + up * h / 2, c - r * w / 2 + up * h / 2]
    bm = bmesh.new()
    vs = [bm.verts.new(B(tuple(p))) for p in pts]
    f = bm.faces.new(vs)
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = uv
    return finish(name, bm, mat, coll or ART, keep_uv=True)


# ---------------------------------------------------------------- shared pieces of both rooms
def panel_uv(name, mat, centre, normal, w, h, v0, v1, coll=None):
    """A flat quad like panel(), its UV the band v0..v1 of the image (one row of an atlas)."""
    r = Vector(RIGHT[normal])
    up = Vector((0, 1, 0))
    c = Vector(centre)
    pts = [c - r * w / 2 - up * h / 2, c + r * w / 2 - up * h / 2, c + r * w / 2 + up * h / 2, c - r * w / 2 + up * h / 2]
    bm = bmesh.new()
    f = bm.faces.new([bm.verts.new(B(tuple(p))) for p in pts])
    uvl = bm.loops.layers.uv.new("UVMap")
    for lp, uv in zip(f.loops, ((0, v0), (1, v0), (1, v1), (0, v1))):
        lp[uvl].uv = uv
    return finish(name, bm, mat, coll or ART, keep_uv=True)


def ceiling_spots(R, specs, tag):
    """Gallery spots hung from the ceiling on stems (the hall's track-spot heads): specs [(pivot (game), aim (game), power W, cone deg)]. The heads
    are art (Metal_Dark cans, Lamp_Emit lenses); the lights are Blender spots for the bake and the stills."""
    h = R["h"]

    def heads(bm):
        for piv, aim, _, _ in specs:
            d = (Vector(aim) - Vector(piv)).normalized()
            cyl(bm, (piv[0], h, piv[2]), (piv[0], h - 0.02, piv[2]), 0.05, 0.05, 12)
            cyl(bm, (piv[0], h - 0.02, piv[2]), piv, 0.008, 0.008, 6)
            sphere(bm, piv, 0.03, 8)
            cyl(bm, tuple(Vector(piv) - d * 0.05), tuple(Vector(piv) + d * 0.13), 0.042, 0.05, 16)
    part(f"Spot_Heads_{tag}", "Metal_Dark", heads, smooth=True)

    def lenses(bm):
        for piv, aim, _, _ in specs:
            d = (Vector(aim) - Vector(piv)).normalized()
            cyl(bm, tuple(Vector(piv) + d * 0.13), tuple(Vector(piv) + d * 0.136), 0.04, 0.04, 16)
    part(f"Spot_Lenses_{tag}", "Lamp_Emit", lenses, smooth=True)
    for piv, aim, power, cone in specs:
        d = (Vector(aim) - Vector(piv)).normalized()
        LIGHTS.append(dict(name=f"Spot_Light_{tag}_{len(LIGHTS)}", kind="SPOT", pos=tuple(Vector(piv) + d * 0.14), aim=aim, power=power,
                           color=(1.0, 0.84, 0.62), size=0.035, cone=cone, blend=0.45))


def block_plinth(bm_base, bm_die, bm_cap, x0, x1, z0, z1, top):
    """The hall's block pedestal (procroom.js `plinth`): a white marble base, a dark marble die, a white marble cap; the collider's size."""
    cube(bm_base, (x0 - 0.02, 0.0, z0 - 0.02), (x1 + 0.02, 0.05, z1 + 0.02))
    cube(bm_base, (x0 - 0.005, 0.05, z0 - 0.005), (x1 + 0.005, 0.11, z1 + 0.005))
    cube(bm_die, (x0 + 0.025, 0.11, z0 + 0.025), (x1 - 0.025, top - 0.10, z1 - 0.025))
    cube(bm_cap, (x0 - 0.005, top - 0.10, z0 - 0.005), (x1 + 0.005, top - 0.065, z1 + 0.005))
    cube(bm_cap, (x0 - 0.02, top - 0.065, z0 - 0.02), (x1 + 0.02, top, z1 + 0.02))


def plinths(tag, boxes):
    """Block pedestals [(x0, x1, z0, z1, top)], one art piece per material, and a COL_ box each."""
    bms = [bmesh.new() for _ in range(3)]
    for b in boxes:
        block_plinth(*bms, *b)
    for bm, (nm, mat) in zip(bms, (("Base", "Marble_White"), ("Die", "Marble_Dark"), ("Cap", "Marble_White"))):
        finish(f"Plinths_{tag}_{nm}", bm, mat, ART)
    for i, (x0, x1, z0, z1, top) in enumerate(boxes):
        col_box(f"COL_{tag}_{i}", (x0 - 0.02, 0.0, z0 - 0.02), (x1 + 0.02, top, z1 + 0.02))


# ---------------------------------------------------------------- the natural-history hall
TREX = dict(model="models/characters/trex.glb", len=12.0, h=3.74)      # real size: the page shows it at scale 1
PLAT = dict(w=13.0, d=4.0, h=0.3, west_gap=1.0)                          # the platform, 1 m from the west wall, 4 m from the door wall
SPECIMEN = dict(size=1.0, top=0.9)                                       # the empty specimen plinths (Moonclaw-style creature cases, page-drawn)


def build_nathist():
    R = NH
    cx, cz = (R["x0"] + R["x1"]) / 2, SIDE_Z
    px0 = R["x0"] + PLAT["west_gap"]
    px1 = px0 + PLAT["w"]
    pcx = (px0 + px1) / 2
    pz0, pz1, ph = cz - PLAT["d"] / 2, cz + PLAT["d"] / 2, PLAT["h"]
    R["lay"] = [(pcx - 4.0, cz, 1.6, 1.6), (pcx + 4.0, cz, 1.6, 1.6)]
    R["lay_w"] = 240.0                       # W per m2 of laylight
    door_doric(R, R["door"], SIDE_Z, "MAIN HALL", "Plaque_Hall_NatHist", "hall_w")
    build_shell(R)
    build_mouldings(R)
    for n in ("+z", "-z"):
        for a in (cx - 5.5, cx + 5.5):
            salon(R, n, a, y=2.6, big="gilt-ornate", small="gilt-simple", top="dark-wood")
    FRAMES.append((R, "+x", cz, 3.2, 3.0, 2.2, "gilt-ornate"))
    for k in (-1, 1):
        FRAMES.append((R, "+x", cz + k * 3.1, 2.4, 1.2, 1.5, "dark-wood"))
    build_frames(R)
    # the platform: 13 x 4 x 0.3 m of sandstone with a white marble lip and a dark marble toe; a brass rail 15 cm in from its edge, 1 m high
    part("Platform_Body", "Stone", lambda bm: cube(bm, (px0 + 0.03, 0.0, pz0 + 0.03), (px1 - 0.03, ph - 0.05, pz1 - 0.03)))
    part("Platform_Lip", "Marble_White", lambda bm: cube(bm, (px0, ph - 0.05, pz0), (px1, ph, pz1)))
    part("Platform_Toe", "Marble_Dark", lambda bm: cube(bm, (px0 + 0.06, 0.0, pz0 + 0.06), (px1 - 0.06, 0.06, pz1 - 0.06)))
    col_box("COL_NatHist_Platform", (px0, 0.0, pz0), (px1, ph, pz1))
    ri = 0.15
    rx0, rx1, rz0, rz1, ry = px0 + ri, px1 - ri, pz0 + ri, pz1 - ri, ph + 1.0

    def rail(bm):
        for (a, b) in (((rx0, rz0), (rx1, rz0)), ((rx1, rz0), (rx1, rz1)), ((rx1, rz1), (rx0, rz1)), ((rx0, rz1), (rx0, rz0))):
            ln = math.hypot(b[0] - a[0], b[1] - a[1])
            k = max(1, round(ln / 1.6))
            for i in range(k):
                t = i / k
                x, z = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                cyl(bm, (x, ph, z), (x, ry, z), 0.022, 0.022, 10)
                cyl(bm, (x, ph, z), (x, ph + 0.04, z), 0.045, 0.045, 12)
            for y, r in ((ry, 0.028), (ph + 0.5, 0.012)):
                cyl(bm, (a[0], y, a[1]), (b[0], y, b[1]), r, r, 10)
        for x, z in ((rx0, rz0), (rx1, rz0), (rx1, rz1), (rx0, rz1)):
            sphere(bm, (x, ry, z), 0.04, 12)
    part("Platform_Rail", "Metal_Brass", rail, smooth=True)
    t = 0.04
    col_box("COL_NatHist_Rail_N", (rx0 - t, ph, rz0 - t), (rx1 + t, ry + 0.04, rz0 + t))
    col_box("COL_NatHist_Rail_S", (rx0 - t, ph, rz1 - t), (rx1 + t, ry + 0.04, rz1 + t))
    col_box("COL_NatHist_Rail_W", (rx0 - t, ph, rz0 + t), (rx0 + t, ry + 0.04, rz1 - t))
    col_box("COL_NatHist_Rail_E", (rx1 - t, ph, rz0 + t), (rx1 + t, ry + 0.04, rz1 - t))
    textured("Plaque_Trex", mk_image("Plaque_Trex", text_pixels("TYRANNOSAURUS REX", 1024, 96, (0.10, 0.07, 0.05), (0.92, 0.80, 0.52), border=4)))
    part("Platform_Plaque_Back", "Metal_Brass", lambda bm: cube(bm, (px1, 0.06, cz - 0.75), (px1 + 0.01, 0.24, cz + 0.75)))
    panel("Platform_Plaque", "Plaque_Trex", (px1 + 0.0105, 0.15, cz), "+x", 1.4, 1.4 * 96 / 1024)
    # Spot_trex: the platform's middle, on its top; the skeleton's long axis along the room's (x), its head toward the door (+x)
    empty("Spot_trex", (pcx, ph, cz), face=(1, 0), props={"scale": 1.0, "model": TREX["model"], "length_m": TREX["len"], "height_m": TREX["h"]})
    trex_standin(pcx, ph, cz)
    # the specimen plinths: empty, for the page's creatures; one either side of the platform's ends, along both long walls
    boxes = []
    s = SPECIMEN["size"] / 2
    k = 0
    for z, fz in ((R["z0"] + 1.6, 1), (R["z1"] - 1.6, -1)):
        for x in (pcx - 4.25, pcx + 6.75):
            boxes.append((x - s, x + s, z - s, z + s, SPECIMEN["top"]))
            k += 1
            empty(f"Spot_specimen_{k}", (x, SPECIMEN["top"], z), face=(0, fz), props={"scale": 1.0, "case": "creature specimen (Moonclaw style)"})
    plinths("Specimen", boxes)
    # light: four spots over the platform, one on each specimen plinth
    specs = [((pcx + k * 3.6, R["h"] - 0.45, cz + s2 * 3.0), (pcx + k * 2.2, 1.9, cz), 1000.0, 52.0) for k in (-1, 1) for s2 in (-1, 1)]
    for bx0, bx1, bz0, bz1, _ in boxes:
        xc, zc = (bx0 + bx1) / 2, (bz0 + bz1) / 2
        specs.append(((xc, R["h"] - 0.45, zc + (1.2 if zc < cz else -1.2)), (xc, SPECIMEN["top"] + 0.4, zc), 520.0, 32.0))
    ceiling_spots(R, specs, "NatHist")
    for z in (R["z0"] + 2.0, R["z1"] - 2.0):
        chandelier(R, "ph-chandelier-01", cx, z, 1.0, 240.0)
    bench(R, cx, R["z0"] + 1.6, (0, 1), 0)
    bench(R, cx, R["z1"] - 1.6, (0, -1), 1)
    pedestal_piece(R, "ph-bull-head", R["x0"] + 1.2, R["z0"] + 1.4, (1, 1), 0)
    pedestal_piece(R, "ph-horse-head", R["x0"] + 1.2, R["z1"] - 1.4, (1, -1), 1)
    pedestal_piece(R, "ph-ceramic-vase", R["x1"] - 1.2, R["z0"] + 1.4, (-1, 1), 2)
    pedestal_piece(R, "ph-brass-vase", R["x1"] - 1.2, R["z1"] - 1.4, (-1, -1), 3)
    # the way back to the hall: F at 0.7 m from the door; you arrive 1.4 m in, facing the room
    hx = R["x1"]
    empty("Link_hall_w", (hx - 0.7, 0.0, SIDE_Z))
    empty("Arrive_hall_w", (hx - 1.4, 0.0, SIDE_Z), face=(-1, 0))
    empty("Marker_from_hall_w", (hx - 1.4, 0.0, SIDE_Z), props={"kind": "Entrance", "room": "natural_history"})


def trex_standin(x, y, z):
    """Grey blocks of the skeleton's real size (12 m long, 3.74 m tall, head toward +x), in the bake for its contact shadow on the platform and in
    the review stills; never exported (the page draws and animates the real one)."""
    def boxes(bm):
        cube(bm, (x - 6.0, y + 2.0, z - 0.12), (x - 3.0, y + 2.3, z + 0.12))        # tail, two steps down to its tip
        cube(bm, (x - 3.0, y + 2.2, z - 0.2), (x - 0.8, y + 2.6, z + 0.2))
        cube(bm, (x - 1.2, y + 2.0, z - 0.55), (x + 2.4, y + 3.2, z + 0.55))        # body and ribs
        cube(bm, (x + 2.2, y + 2.6, z - 0.22), (x + 4.3, y + 3.2, z + 0.22))        # neck
        cube(bm, (x + 4.3, y + 2.6, z - 0.42), (x + 6.0, y + 3.74, z + 0.42))       # head
        for s in (-1, 1):
            cube(bm, (x - 0.5, y + 1.0, z + s * 0.5 - 0.16), (x + 0.4, y + 2.2, z + s * 0.5 + 0.16))   # thighs
            cube(bm, (x - 0.1, y, z + s * 0.5 - 0.11), (x + 0.25, y + 1.05, z + s * 0.5 + 0.11))        # shins
            cube(bm, (x - 0.1, y, z + s * 0.5 - 0.16), (x + 0.75, y + 0.08, z + s * 0.5 + 0.16))        # feet
    part("standin_trex", "Standin_Grey", boxes, coll=BAKE_STANDIN)


# ---------------------------------------------------------------- the history gallery
ERAS = [("egyptian_pharaoh", "EGYPT"), ("qin_terracotta", "QIN CHINA"), ("roman_legionary", "ROME"), ("viking_raider", "VIKINGS"),
        ("mongol_archer", "MONGOLS"), ("medieval_knight", "KNIGHTS"), ("japanese_samurai", "SAMURAI"), ("british_redcoat", "REDCOATS")]
ERA_PLINTH = dict(w=1.5, d=0.7, top=1.0, per=3, gap=0.45)      # three figures a plinth, 45 cm apart, on a 1 m top: the miniatures at scale 1


def vitrine(R, n, a, ln, i, pieces=()):
    """A glass vitrine on a dark wood stand against wall n: 0.85 m stand, 0.9 m case with brass edges, a case light along the back of its top; its
    COL_ box. `pieces` [(model id, offset along, target height)] stand on its deck."""
    nm = R["name"]
    d0, d1 = 0.03, 0.72
    s0, s1 = 0.85, 1.75
    a0, a1 = a - ln / 2, a + ln / 2
    part(f"Vitrine_{nm}_{i}_Stand", "Door_Wood", lambda bm: wall_box(bm, R, n, a0, a1, 0.06, s0, d0, d1))
    part(f"Vitrine_{nm}_{i}_Toe", "Metal_Dark", lambda bm: wall_box(bm, R, n, a0 + 0.04, a1 - 0.04, 0.0, 0.06, d0 + 0.04, d1 - 0.04))

    def frame(bm):
        e = 0.02
        for aa in (a0, a1 - e):
            for dd in (d0, d1 - e):
                wall_box(bm, R, n, aa, aa + e, s0, s1, dd, dd + e)
        for y in (s0, s1 - e):
            wall_box(bm, R, n, a0, a1, y, y + e, d0, d0 + e)
            wall_box(bm, R, n, a0, a1, y, y + e, d1 - e, d1)
            wall_box(bm, R, n, a0, a0 + e, y, y + e, d0, d1)
            wall_box(bm, R, n, a1 - e, a1, y, y + e, d0, d1)
        wall_box(bm, R, n, a0 + 0.02, a1 - 0.02, s1 - 0.06, s1 - 0.02, d0 + 0.02, d0 + 0.08)       # the lamp rail at the back of the top
    part(f"Vitrine_{nm}_{i}_Frame", "Metal_Brass", frame)
    part(f"Vitrine_{nm}_{i}_Deck", "Trim_Paint", lambda bm: wall_box(bm, R, n, a0 + 0.02, a1 - 0.02, s0, s0 + 0.02, d0 + 0.02, d1 - 0.02))
    part(f"Vitrine_{nm}_{i}_Lamp", "Lamp_Emit", lambda bm: wall_box(bm, R, n, a0 + 0.06, a1 - 0.06, s1 - 0.075, s1 - 0.06, d0 + 0.03, d0 + 0.07))

    def glass(bm):
        e = 0.005
        wall_box(bm, R, n, a0 + 0.02, a1 - 0.02, s0 + 0.02, s1 - 0.02, d1 - 0.012, d1 - 0.012 + e)
        wall_box(bm, R, n, a0 + 0.008, a0 + 0.008 + e, s0 + 0.02, s1 - 0.02, d0 + 0.02, d1 - 0.02)
        wall_box(bm, R, n, a1 - 0.008 - e, a1 - 0.008, s0 + 0.02, s1 - 0.02, d0 + 0.02, d1 - 0.02)
        wall_box(bm, R, n, a0 + 0.02, a1 - 0.02, s1 - 0.012, s1 - 0.012 + e, d0 + 0.02, d1 - 0.02)
    part(f"Vitrine_{nm}_{i}_Glass", "Vitrine_Glass", glass)
    p, q = on_wall(R, n, a0, 0.0, 0.0), on_wall(R, n, a1, s1, d1)
    col_box(f"COL_{nm}_Vitrine_{i}", tuple(min(p[k], q[k]) for k in range(3)), tuple(max(p[k], q[k]) for k in range(3)))
    OBSTACLES.append((R, n, a0 - 0.05, a1 + 0.05))
    LIGHTS.append(dict(name=f"Case_Light_{nm}_{i}", kind="AREA", pos=on_wall(R, n, a, s1 - 0.08, 0.2), aim=on_wall(R, n, a, s0, 0.5), power=40.0,
                       color=(1.0, 0.9, 0.75), size=(ln - 0.2, 0.25)))
    for k, (mid, off, th) in enumerate(pieces):
        p = on_wall(R, n, a + off, 0.0, 0.38)
        import_model(mid, f"Piece_{nm}_Vitrine_{i}_{k}", (p[0], p[2]), base_y=s0 + 0.02, face=(NVEC[n][0], NVEC[n][2]), target_h=th)


def build_history():
    R = HG
    cx, cz = (R["x0"] + R["x1"]) / 2, SIDE_Z
    R["lay"] = [(cx - 3.6, cz, 1.3, 1.6), (cx + 3.6, cz, 1.3, 1.6)]
    R["lay_w"] = 240.0
    door_arch(R, R["door"], SIDE_Z, "MAIN HALL", "Plaque_Hall_History", "hall_e")
    vitrine(R, "+z", cx - 3.5, 2.6, "N0", [("si-kangxi-baluster-vase", 0.0, None)])
    vitrine(R, "+z", cx + 3.5, 2.6, "N1", [("si-xianglu", 0.0, 0.30)])
    build_shell(R)
    build_mouldings(R)
    for n in ("+z", "-z"):
        for a in (cx - 3.5, cx + 3.5):
            FRAMES.append((R, n, a, 2.95, 1.6, 1.05, "gilt-ornate" if n == "+z" else "dark-wood"))
        FRAMES.append((R, n, cx, 2.6, 1.0, 1.3, "gilt-simple"))
    for k in (-1, 1):
        FRAMES.append((R, "+x", cz + k * 3.6, 2.3, 1.4, 1.8, "gilt-simple"))
        FRAMES.append((R, "-x", cz + k * 3.4, 2.4, 1.1, 1.4, "dark-wood"))
    build_frames(R)
    import_model("ph-ornate-mirror", "Mirror_History", (R["x1"] - 0.03, cz), base_y=1.55, face=(-1, 0), target_h=1.3)
    # the eight era plinths, two rows of four either side of the aisle, in time order: down the north row from the door, back up the south row
    W, D, top = ERA_PLINTH["w"], ERA_PLINTH["d"], ERA_PLINTH["top"]
    xs = [cx - 4.0, cx - 1.0, cx + 2.0, cx + 5.0]
    rows = [(cz - 3.0, 1, xs), (cz + 3.0, -1, xs[::-1])]
    boxes, specs, k = [], [], 0
    rows_h = len(ERAS)
    atlas = np.zeros((96 * rows_h, 768, 3), np.float32)
    for r, (era, label) in enumerate(ERAS):
        atlas[r * 96:(r + 1) * 96] = text_pixels(label, 768, 96, (0.10, 0.07, 0.05), (0.92, 0.80, 0.52), border=4)
    textured("Plaque_Eras", mk_image("Plaque_Eras", atlas))
    e = 0
    for z, fz, row in rows:
        for x in row:
            era, label = ERAS[e]
            boxes.append((x - W / 2, x + W / 2, z - D / 2, z + D / 2, top))
            n = "+z" if fz > 0 else "-z"                  # the way the plinth's face toward the aisle looks (panel()'s normal key)
            v0 = 1 - (e + 1) / rows_h
            panel_uv(f"Era_Plaque_{e}", "Plaque_Eras", (x, top - 0.28, z + fz * (D / 2 - 0.025 + 0.0065)), n, 0.9, 0.1125, v0, v0 + 1 / rows_h)
            for j in range(ERA_PLINTH["per"]):
                k += 1
                off = (j - (ERA_PLINTH["per"] - 1) / 2) * ERA_PLINTH["gap"]
                p = (x + off, top, z)
                empty(f"Spot_warrior_{k:02d}", p, face=(0, fz), props={"scale": 1.0, "era": era})
                WARRIOR_BOXES.append(p)
            specs.append(((x, R["h"] - 0.35, z + fz * 1.3), (x, top + 0.3, z), 760.0, 36.0))
            e += 1
    plinths("Era_Plinth", boxes)

    def plaque_backs(bm):
        for (x0, x1, z0, z1, t), (z, fz, _) in zip(boxes, [rows[0]] * 4 + [rows[1]] * 4):
            zf = (z0 + z1) / 2 + fz * ((z1 - z0) / 2 - 0.025)          # the die's face toward the aisle
            cube(bm, ((x0 + x1) / 2 - 0.48, t - 0.34, min(zf, zf + fz * 0.006)), ((x0 + x1) / 2 + 0.48, t - 0.22, max(zf, zf + fz * 0.006)))
    part("Era_Plaque_Backs", "Metal_Brass", plaque_backs)
    ceiling_spots(R, specs, "History")
    # busts on column pedestals against the south wall, between the frames; the winged monster on its plinth under the mirror
    pedestal_piece(R, "si-houdon-washington", cx - 3.5, R["z1"] - 0.8, (0, -1), 0)
    pedestal_piece(R, "ph-marble-bust", cx + 3.5, R["z1"] - 0.8, (0, -1), 1)
    x = R["x1"] - 1.4
    part("Monster_Plinth", "Marble_Dark", lambda bm: cube(bm, (x - 0.5, 0.0, cz - 0.5), (x + 0.5, 0.41, cz + 0.5)))
    part("Monster_Plinth_Lip", "Marble_White", lambda bm: cube(bm, (x - 0.52, 0.41, cz - 0.52), (x + 0.52, 0.45, cz + 0.52)))
    col_box("COL_History_Monster_Plinth", (x - 0.52, 0.0, cz - 0.52), (x + 0.52, 0.45, cz + 0.52))
    import_model("si-winged-monster", "Piece_History_Monster", (x, cz), base_y=0.45, face=(-1, 0))
    chandelier(R, "ph-chandelier-02", cx, cz, 1.1, 240.0)
    hx = R["x0"]
    empty("Link_hall_e", (hx + 0.7, 0.0, SIDE_Z))
    empty("Arrive_hall_e", (hx + 1.4, 0.0, SIDE_Z), face=(1, 0))
    empty("Marker_from_hall_e", (hx + 1.4, 0.0, SIDE_Z), props={"kind": "Entrance", "room": "history"})


WARRIOR_BOXES = []


def warrior_standins():
    """The soldiers' size (0.43 to 0.54 m miniatures at scale 1), for the review stills only: hidden in the bake, never exported."""
    def boxes(bm):
        for (x, y, z) in WARRIOR_BOXES:
            cube(bm, (x - 0.07, y, z - 0.05), (x + 0.07, y + 0.40, z + 0.05))
            cube(bm, (x - 0.045, y + 0.40, z - 0.045), (x + 0.045, y + 0.50, z + 0.045))
    part("standin_warriors", "Standin_Grey", boxes, coll=STANDIN)


# ---------------------------------------------------------------- lights, world
def add_lights():
    lights = bpy.data.collections.new("Lights")
    bpy.context.scene.collection.children.link(lights)
    for s in LIGHTS:
        d = bpy.data.lights.new(s["name"], s["kind"])
        d.energy, d.color = s["power"], s["color"]
        ob = bpy.data.objects.new(s["name"], d)
        ob.location = B(s["pos"])
        lights.objects.link(ob)
        if s["kind"] == "AREA":
            d.shape = "RECTANGLE"
            d.size, d.size_y = s["size"]
        else:
            d.shadow_soft_size = s["size"]
        if s["kind"] == "SPOT":
            d.spot_size, d.spot_blend = math.radians(s["cone"]), s["blend"]
        if "aim" in s:
            d3 = (Vector(s["aim"]) - Vector(s["pos"])).normalized()
            q = B(d3).to_track_quat("-Z", "Y")
            if s["kind"] == "AREA" and abs(d3.y) > 0.99:
                q = B(d3).to_track_quat("-Z", "X")        # straight down: keep the rectangle's x along game x
            ob.rotation_euler = q.to_euler()


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("Night")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.012, 0.016, 0.035, 1)
    bg.inputs["Strength"].default_value = 0.0


def arrival():
    return [NH["x1"] - 1.4, 0.0, SIDE_Z]


def ensure_marker():
    st = bpy.data.collections["Standins"]
    ob = bpy.data.objects.get("standin_arrival_marker")
    if ob is None:
        me = bpy.data.meshes.new("standin_arrival_marker")
        bm = bmesh.new()
        a = arrival()
        cube(bm, (a[0] - 0.1, a[1], a[2] - 0.1), (a[0] + 0.1, a[1] + 0.2, a[2] + 0.1))
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("standin_arrival_marker", me)
        st.objects.link(ob)
    ob.hide_render = True
    return ob


def stage_axes():
    """The marker-cube check: game (x, y, z) = Blender (x, -z, y) = glTF (x, y, z)."""
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
    a = arrival()
    want = [a[0], a[1] + 0.1, a[2]]
    bl = sum((v.co for v in ob.data.vertices), Vector()) / len(ob.data.vertices)
    print(f"AXES glTF centre {tuple(round(v, 3) for v in centre)}, game point {tuple(want)}, Blender {tuple(round(v, 3) for v in bl)}")
    assert all(abs(centre[i] - want[i]) < 1e-4 for i in range(3))
    assert abs(bl.x - want[0]) < 1e-4 and abs(bl.y + want[2]) < 1e-4 and abs(bl.z - want[1]) < 1e-4
    print("AXES PASS: game (x, y, z) = Blender (x, -z, y) = glTF (x, y, z)")


def build_all():
    global ART, STANDIN, BAKE_STANDIN, LAYOUT_C, DOORS_C, MCAT
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.lights, bpy.data.cameras):
        for d in list(coll):
            coll.remove(d)
    for d in (IMG_CACHE, MATS, TILES, PROPKEYS, MODEL_TRIS):
        d.clear()
    for d in (DOORS, FRAMES, LIGHTS, OBSTACLES, WARRIOR_BOXES):
        d.clear()
    MCAT = None
    sc = bpy.context.scene
    ART, STANDIN, BAKE_STANDIN, LAYOUT_C, DOORS_C = (bpy.data.collections.new(n) for n in ("Art", "Standins", "Bake_Standins", "Layout", "Doors"))
    for c in (ART, STANDIN, BAKE_STANDIN, LAYOUT_C, DOORS_C):
        sc.collection.children.link(c)
    make_materials()
    build_nathist()
    build_history()
    warrior_standins()
    add_lights()
    setup_world()
    ensure_marker()
    for ob in LAYOUT_C.objects:
        ob.hide_render = True
    split_for_check()
    for ob, (mid, n) in sorted(MODEL_TRIS.items()):
        print(f"MODEL {ob}: {mid}, {n} triangles (whole)")


def split_for_check():
    """tools/blender/check_layout.py works one box per object. A piece made of separate parts (a room's skirting runs, a row of plinth dies, a door
    surround's two jambs) has a box that spans floor where no collider stands, or covers an arrival point. Each Art piece whose box would fail the
    check's STRAY or CLEAR rule against the COL_ boxes is cut into its loose parts (`<name>`, `<name>_p1`, ...), each part keeping its materials. Only
    Art is cut: the Export objects are merged by material from Art, so the GLB holds the same triangles either way. Also run on its own
    (`--stage split`) on a saved .blend."""
    sys.path.insert(0, str(ROOT / "tools/blender"))
    import check_layout as cl

    def box(ob):
        g = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        return {"min": [min(p.x for p in g), min(p.z for p in g), min(-p.y for p in g)], "max": [max(p.x for p in g), max(p.z for p in g), max(-p.y for p in g)]}

    stand = [c for c in (box(o) for o in bpy.data.objects if o.name.startswith("COL_") and o.type == "MESH") if cl._standing(c)]
    marks = [(o.matrix_world.translation.x, -o.matrix_world.translation.y) for o in bpy.data.objects if o.name.startswith("Marker_")]

    def fails(p):
        if not cl._stands(p):
            return False
        if any(cl._in_plan(p, x, z, cl.CLEAR_R) for x, z in marks):
            return True
        for x in cl._samples(p["min"][0], p["max"][0], cl.STEP / 2):
            for z in cl._samples(p["min"][2], p["max"][2], cl.STEP / 2):
                if not any(cl._in_plan(c, x, z, cl.TOL) for c in stand):
                    return True
        return False

    art = bpy.data.collections["Art"]
    done = []
    for ob in list(art.objects):
        if ob.type != "MESH" or ob.name.startswith("decor_") or not fails(box(ob)):
            continue
        src = bmesh.new()
        src.from_mesh(ob.data)
        src.faces.index_update()
        seen, groups = set(), []
        for f in src.faces:
            if f.index in seen:
                continue
            comp, stack = set(), [f]
            seen.add(f.index)
            while stack:
                u = stack.pop()
                comp.add(u.index)
                for v in u.verts:
                    for w in v.link_faces:
                        if w.index not in seen:
                            seen.add(w.index)
                            stack.append(w)
            groups.append(comp)
        src.free()
        if len(groups) < 2:
            continue
        mats = list(ob.data.materials)
        name = ob.name
        for k in range(len(groups) - 1, -1, -1):                   # the first part last: it keeps the original mesh
            bm = bmesh.new()
            bm.from_mesh(ob.data)
            bm.faces.index_update()
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in groups[k]], context="FACES")
            if k == 0:
                bm.to_mesh(ob.data)
                bm.free()
                continue
            me = bpy.data.meshes.new(f"{name}_p{k}")
            for m in mats:
                me.materials.append(m)
            bm.to_mesh(me)
            bm.free()
            nob = bpy.data.objects.new(f"{name}_p{k}", me)
            nob.matrix_world = ob.matrix_world.copy()
            art.objects.link(nob)
        done.append(f"{name} ({len(groups)})")
    print("SPLIT for the layout check:", done)
    return done


# ---------------------------------------------------------------- bake
GROUPS = [["Floor_Parquet", "Floor_Stone", "Floor_Border", "Ceiling_Paint"],                               # 0: floors and ceilings
          ["Wall_Paint_NatHist", "Wall_Paint_History", "Wainscot_Wood", "Trim_Paint", "Marble_Dark"],      # 1: walls, wainscot, mouldings, dark marble
          ["Marble_White", "Stone", "Frame_Gold", "Frame_Wood", "Door_Wood", "Plaque_Hall_NatHist", "Plaque_Hall_History", "Plaque_Trex",
           "Plaque_Eras", "Metal_Brass", "Metal_Dark", "Bench_Paint"],                                       # 2: marble, stone, frames, doors, plaques, metal
          ["Prop_*"]]                                       # 3: the Chronicle models, each through its own UVs in a cell of a grid (see lightmap_uv)
PAGES = [1024, 2048, 1792, 1024]                            # fixed: found by --stage size (the smallest page giving >= 30 px/m), then kept, because
                                                            # Blender's island packer is not exactly repeatable
WHITE_CAP = 12.0                                            # a map's white point: its 99.5th percentile texel, at most 12 x its 90th (the hall's rule)
FLAT_UV = ("Plaque_",)                                      # flat quads with their own 0..1 UVs: smart project folds a lone quad into a sliver, and one
                                                            # sliver is enough for average_islands_scale to blow it up and the packer to shrink the rest to 0
OWN_UV = ("Prop_",)                                         # lightmapped through the model's own UVs: a scan's 20 000 triangles would make thousands of
                                                            # smart-project islands; each model gets a square cell of the map, the same model twice shares it
HIDE_IN_BAKE = ("Laylight_Glass", "Vitrine_Glass")
SHELL = ("Wall_", "Floor_", "Ceiling_")
NO_CULL = ("Chandelier_", "Piece_", "Bench_", "Mirror_")


def in_room(gx, gy, gz, e, ceiling=False):
    for R in ROOMS:
        top = R["h"] + WALL_T - e if ceiling else R["h"] + e
        if R["x0"] - e <= gx <= R["x1"] + e and -e <= gy <= top and R["z0"] - e <= gz <= R["z1"] + e:
            return True
    return False


def trim_outside(bm, ceiling=False):
    """Drop the shell faces never seen from inside; a ceiling keeps only its underside (the laylight linings cover the openings' sides)."""
    e = 0.001
    bad = []
    for f in bm.faces:
        c = f.calc_center_median()
        if (ceiling and f.normal.z > -0.5) or not in_room(c.x, c.z, -c.y, e, ceiling):
            bad.append(f)
    bmesh.ops.delete(bm, geom=bad, context="FACES")


def cull_flush(bm):
    """Drop faces lying flat against a wall, the floor or the ceiling and facing into it."""
    e = 1e-3
    bad = []
    for f in bm.faces:
        c, n = f.calc_center_median(), f.normal
        gx, gy, gz = c.x, c.z, -c.y
        nx, ny, nz = n.x, n.z, -n.y
        for R in ROOMS:
            if not (R["x0"] - 0.3 <= gx <= R["x1"] + 0.3 and R["z0"] - 0.3 <= gz <= R["z1"] + 0.3):
                continue
            if (nx > 0.9 and abs(gx - R["x1"]) <= e) or (nx < -0.9 and abs(gx - R["x0"]) <= e) or (nz > 0.9 and abs(gz - R["z1"]) <= e) \
                    or (nz < -0.9 and abs(gz - R["z0"]) <= e) or (ny < -0.9 and abs(gy) <= e) or (ny > 0.9 and abs(gy - R["h"]) <= e):
                bad.append(f)
                break
    bmesh.ops.delete(bm, geom=bad, context="FACES")


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
    """The Art collection merged by material (one mesh per material), faces never seen dropped. The door leaves stay their own objects."""
    art = bpy.data.collections["Art"]
    if "Export" in bpy.data.collections:
        for o in list(bpy.data.collections["Export"].objects):
            bpy.data.objects.remove(o)
        bpy.data.collections.remove(bpy.data.collections["Export"])
    exp = bpy.data.collections.new("Export")
    bpy.context.scene.collection.children.link(exp)
    by_mat = {}
    for ob in art.objects:
        for idx, slot in enumerate(ob.material_slots):
            mname = slot.material.name
            bm = by_mat.setdefault(mname, bmesh.new())
            tmp = bmesh.new()
            tmp.from_mesh(ob.data)
            bmesh.ops.delete(tmp, geom=[f for f in tmp.faces if f.material_index != idx], context="FACES")
            for f in tmp.faces:
                f.material_index = 0
            if ob.name.startswith(SHELL):
                trim_outside(tmp, ceiling=ob.name.startswith("Ceiling"))
            elif not ob.name.startswith(NO_CULL):
                cull_flush(tmp)
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
    M = ob.matrix_world
    return sum(p.area for p in ob.data.polygons) * abs(M.to_3x3().determinant()) ** (2 / 3)


def lightmap_uv(objs, page=None):
    """One atlas for `objs`: smart-project islands at equal texel density, packed with MARGIN_PX, on the fixed `page` (or, with None, the smallest
    square page giving >= 30 px/m). The OWN_UV objects (the models) keep their own UVs instead, each fitted into a square cell of a grid; the
    packed islands then share the page with them (the grid takes the right-hand columns). Returns (page, density of the packed part)."""
    own = [o for o in objs if o.name.startswith(OWN_UV)]
    rest = [o for o in objs if o not in own]
    flat = [o for o in rest if o.name.startswith(FLAT_UV)]
    for o in objs:
        uvs = o.data.uv_layers
        if "lightmap" in uvs:
            uvs.remove(uvs["lightmap"])
        uvs.new(name="lightmap", do_init=o in own or o in flat)    # the models' and the plaques' start as a copy of UVMap
        uvs.active = uvs["lightmap"]
        uvs["UVMap"].active_render = True
    g = math.ceil(math.sqrt(len(own))) if own else 0
    for i, o in enumerate(own):                                    # the model's UVs, fitted into cell i of a g x g grid
        S = page or 2048
        d = o.data.uv_layers["lightmap"].data
        us = np.array([x.uv for x in d])
        lo, hi = us.min(axis=0), us.max(axis=0)
        c = 1.0 / g
        m = MARGIN_PX / S
        sc = (c - 2 * m) / max(hi - lo)
        us = (us - lo) * sc + np.array([(i % g) * c + m, (i // g) * c + m])
        d.foreach_set("uv", us.ravel())
        print(f"  {o.name}: own UVs in cell {i} of {g}x{g}, {S * c * math.sqrt(1.0 / max(world_area(o), 1e-6)):.0f} px per sqrt(m2) of surface")
    chosen = (page, 0.0)
    if rest:
        if [o for o in rest if o not in flat]:
            select_only([o for o in rest if o not in flat])
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
            bpy.ops.object.mode_set(mode="OBJECT")
        select_only(rest)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.average_islands_scale()
        for S in ((page,) if page else (1024, 1152, 1280, 1408, 1536, 1792, 2048)):
            if bpy.context.mode != "EDIT_MESH":                    # every try packs every island again (the UV selection does not outlive a mode switch)
                bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.select_all(action="SELECT")
            bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / S, shape_method="CONCAVE")
            bpy.ops.object.mode_set(mode="OBJECT")
            a3 = sum(world_area(o) for o in rest)
            au = sum(uv_area(o, "lightmap") for o in rest)
            dens = S * math.sqrt(au / a3)
            print(f"  page {S}: {a3:.1f} m2, {dens:.1f} px/m")
            chosen = (S, dens)
            if dens >= 30:
                break
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
    return chosen


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
    path = str(stage_work() / "dn.exr")
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=sc.name)
    r = bpy.data.images.load(path)
    a = np.empty(S * S * 4, np.float32)
    r.pixels.foreach_get(a)
    bpy.data.images.remove(r)
    bpy.data.objects.remove(cam)
    bpy.data.scenes.remove(sc)
    return a.reshape(S, S, 4)


def group_objects(exp, n):
    objs = []
    for pat in GROUPS[n]:
        if pat.endswith("*"):
            objs += [o for k, o in sorted(exp.items()) if k.startswith(pat[:-1])]
        elif pat in exp:
            objs.append(exp[pat])
    if "Door_Wood" in GROUPS[n]:
        objs += sorted(bpy.data.collections["Doors"].objects, key=lambda o: o.name)
    return objs


def bake_visibility():
    """What the bake sees: the merged Export objects, the door leaves, the T. rex stand-in (its contact shadow); not the unmerged Art, not the
    figures' stand-ins (they are only in the stills)."""
    for c, hide in (("Art", True), ("Standins", True), ("Bake_Standins", False), ("Doors", False), ("Export", False)):
        bpy.data.collections[c].hide_render = hide
    bpy.data.collections["Art"].hide_viewport = True


def stage_size():
    """Lay out every map's lightmap UVs with no fixed page and print the smallest page that gives >= 30 px/m (how PAGES was found). No bake."""
    exp = make_export_objects()
    for n in [int(v) for v in arg("--maps", "0,1,2,3").split(",")]:
        objs = group_objects(exp, n)
        S, dens = lightmap_uv(objs, PAGES[n] if n == 3 else None)
        print(f"SIZE map {n}: page {S}, {dens:.1f} px/m, {[o.name for o in objs]}")


def stage_bake():
    import time
    exp = make_export_objects()
    bake_visibility()
    setup_cycles(SAMPLES, bake=True)
    report = {}
    for n in range(len(GROUPS)):
        t0 = time.time()
        objs = group_objects(exp, n)
        print(f"lightmap {n}: {[o.name for o in objs]}")
        S, dens = lightmap_uv(objs, PAGES[n])
        img = bpy.data.images.new(f"LM_{n}", S, S, alpha=False, float_buffer=True)
        img.colorspace_settings.name = "Non-Color"
        mats = sorted({s.material for o in objs for s in o.material_slots}, key=lambda m: m.name)
        for m in mats:
            node = m.node_tree.nodes.new("ShaderNodeTexImage")
            node.name = "BAKE_TARGET"
            node.image = img
            m.node_tree.nodes.active = node
            node.select = True
        for m in HIDE_IN_BAKE:
            if m in exp:
                exp[m].hide_render = True
        select_only(objs)
        for o in objs:
            o.data.uv_layers.active = o.data.uv_layers["lightmap"]
        bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
        for m in HIDE_IN_BAKE:
            if m in exp:
                exp[m].hide_render = False
        rgb = denoise_image(img, S)[..., :3]
        peak = rgb.max(axis=2)
        pc = np.percentile(peak[peak > 1e-5], [50, 90, 99, 99.5, 100]) if (peak > 1e-5).any() else [1.0] * 5
        scale = float(min(pc[3], WHITE_CAP * pc[1]))
        out = np.ones((S, S, 4), np.float32)
        out[..., :3] = srgb_encode(rgb / scale)
        png = bpy.data.images.new(f"LM_{n}_png", S, S, alpha=False)
        png.colorspace_settings.name = "Non-Color"
        png.pixels.foreach_set(out.ravel())
        png.filepath_raw = str(stage_work() / f"{SCENE}_{n}.png")
        png.file_format = "PNG"
        png.save()
        for m in mats:
            m["lightmap"] = LM_URL.format(n)
            m["lightmap_intensity"] = round(math.pi * scale, 4)
            for nd in [nd for nd in m.node_tree.nodes if nd.name.startswith("BAKE_TARGET")]:
                m.node_tree.nodes.remove(nd)
        report[n] = {"size": S, "px_per_m": round(dens, 1), "scale": round(scale, 4), "p50_p90_p99_p995_max": [round(float(v), 3) for v in pc],
                     "samples": SAMPLES, "device": bpy.context.scene.cycles.device, "seconds": round(time.time() - t0),
                     "materials": [m.name for m in mats]}
        print("  baked", report[n])
        bpy.data.images.remove(img)
        bpy.data.images.remove(png)
    (stage_work() / "lightmaps.json").write_text(json.dumps(report, indent=1))
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Art"].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


# ---------------------------------------------------------------- privacy
KEEP_PROPS = {"lightmap", "lightmap_intensity"}
LAYOUT_PREFIX = ("DoorLeaf_", "Marker_", "Spot_")


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private():
    """The .blend, the GLB and the stills are public: strip other add-ons' custom properties (some hold paths of the machine's user folder),
    work-folder paths in render settings and image paths, and the file browser's remembered folder."""
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
    base = BLEND.parent
    for im in bpy.data.images:                    # the glTF importer packs a .gltf's textures under their absolute paths: unpack the ones whose file is in
        fp = im.filepath.replace("\\", "/")       # blender/models/ (the path goes relative below); a .glb's embedded ones and scaled ones stay packed
        if im.packed_file and fp and not fp.startswith(("//generated/", "//packed/")) and Path(bpy.path.abspath(fp)).is_file() \
                and not im.is_dirty and max(im.size) <= 1024:
            im.unpack(method="REMOVE")
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
            for pf in im.packed_files:
                try:
                    set_path(pf, "filepath", "//packed/" + bpy.path.clean_name(im.name) + ".png")
                except Exception:
                    pass
    for scr in bpy.data.screens:
        for a in scr.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"_" * 1000
                    sp.params.directory = b"//"


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    scrub_private()
    bpy.ops.wm.save_mainfile()


# ---------------------------------------------------------------- export
def stage_export():
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    bpy.data.collections["Art"].hide_viewport = True
    leaves = list(bpy.data.collections["Doors"].objects)
    stash = {o.name: {k: o[k] for k in o.keys()} for o in leaves}      # the leaves' layout properties go to the JSON, not into the GLB's extras
    for o in leaves:
        for k in list(o.keys()):
            del o[k]
    bpy.ops.object.select_all(action="DESELECT")
    for o in list(exp.objects) + leaves:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = stage_work() / f"{SCENE}_raw.glb"
    scrub_private()
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_animations=False,
                              # Draco (the page has the loader, as for the store's floors): the scans' 250 000 triangles are 9 MB uncompressed. 14-bit
                              # positions and UVs (a lightmap texel of the 2048 page is 1/2048), 10-bit normals
                              export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6, export_draco_position_quantization=14,
                              export_draco_normal_quantization=10, export_draco_texcoord_quantization=14, export_draco_generic_quantization=12)
    for o in leaves:
        for k, v in stash[o.name].items():
            o[k] = v
    print("EXPORTED", raw, raw.stat().st_size)
    bpy.data.collections["Art"].hide_viewport = False
    exp.hide_viewport = exp.hide_render = True
    sys.path.insert(0, str(ROOT / "tools/blender"))
    import export_scene
    export_scene.write(SCENE)
    save_blend()


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
    cam.clip_start, cam.clip_end = 0.05, 200
    ob = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = B(loc)
    if target is not None:
        ob.rotation_euler = (B(target) - B(loc)).to_track_quat("-Z", "Y").to_euler()
    return ob


def strip_jpeg_comments(path):
    """Blender writes render metadata as JPEG comment segments even with every stamp off; drop them."""
    b = path.read_bytes()
    out, i = bytearray(b[:2]), 2
    while i < len(b) and b[i] == 0xFF and b[i + 1] != 0xDA:
        n = int.from_bytes(b[i + 2:i + 4], "big")
        if b[i + 1] != 0xFE:
            out += b[i:i + 2 + n]
        i += 2 + n
    out += b[i:]
    path.write_bytes(bytes(out))


PLAN_X0, PLAN_X1 = NH["x0"] - 0.6, HG["x1"] + 0.6


def stage_render():
    sc = bpy.context.scene
    STILLS.mkdir(parents=True, exist_ok=True)
    scrub_private()
    for c in ("Export",):
        if c in bpy.data.collections:
            bpy.data.collections[c].hide_render = True
    for c in ("Standins", "Bake_Standins", "Doors"):              # the grey stand-ins show where the page's live figures stand
        bpy.data.collections[c].hide_render = False
    bpy.data.collections["Art"].hide_render = False
    bpy.data.objects["standin_arrival_marker"].hide_render = True
    setup_cycles(arg("--render-samples", 128, int))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = arg("--noise", 0.03, float)
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    expo = arg("--exposure", 0.0, float)
    which = arg("--only", "all")
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    a = arrival()
    hc = (HG["x0"] + HG["x1"]) / 2
    shots = {
        "1_arrival": look_cam("arrival", (a[0], 1.6, a[2]), (a[0] - 8, 1.6 + 8 * math.tan(math.radians(6)), a[2]), 75.0),
        "2_wide": look_cam("wide", (HG["x1"] - 0.5, 4.3, HG["z1"] - 0.5), (hc - 2.5, 0.7, SIDE_Z - 1.0), 75.0),
        "3_detail": look_cam("detail", (hc - 2.9, 1.65, SIDE_Z - 0.9), (hc - 4.0, 1.25, SIDE_Z - 3.0), 55.0),
    }
    plan = look_cam("plan", ((PLAN_X0 + PLAN_X1) / 2, 14, SIDE_Z), None, ortho=PLAN_X1 - PLAN_X0)
    plan.rotation_euler = (0, 0, 0)
    arts = [o for c in ("Art", "Standins", "Bake_Standins", "Doors") for o in bpy.data.collections[c].objects]
    cut = [o for o in arts if o.name.startswith(("Ceiling", "Laylight", "Cornice", "Chandelier"))]
    ph = round(1800 * (NH["z1"] - NH["z0"] + 1.2) / (PLAN_X1 - PLAN_X0))
    todo = [(k, v, (1920, 1080)) for k, v in shots.items()] + [("plan", plan, (1800, ph))]
    for key, cam, (w, h) in todo:
        if which not in ("all", key):
            continue
        sc.camera = cam
        sc.view_settings.exposure = expo + (1.0 if key == "plan" else 0.0)
        for o in arts:
            o.visible_camera = True
        for o in (cut if key == "plan" else []):
            o.visible_camera = False
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, arg("--scale", 100, int)
        sc.render.image_settings.file_format = "JPEG" if key != "plan" else "PNG"
        sc.render.image_settings.quality = 90
        path = STILLS / f"{key}.jpg" if key != "plan" else stage_work() / "plan.png"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 400_000 and q > 40 and key != "plan":
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        if key != "plan":
            strip_jpeg_comments(path)
        print("STILL", key, path.stat().st_size, "q", q)
    for o in arts:
        o.visible_camera = True
    bpy.data.collections["Standins"].hide_render = True
    (stage_work() / "plan.json").write_text(json.dumps({"x0": PLAN_X0, "x1": PLAN_X1, "zc": SIDE_Z, "w": 1800, "h": ph}))


if __name__ == "__main__":
    if STAGE in ("art", "all"):
        build_all()
        save_blend()
    if STAGE == "split":                              # a saved .blend built before split_for_check: cut its Art pieces (Export, the bake and the GLB are untouched)
        split_for_check()
        save_blend()
    if STAGE == "size":
        stage_size()
    if STAGE in ("bake", "all"):
        stage_bake()
    if STAGE in ("export", "all"):
        stage_export()
    if STAGE in ("axes", "all"):
        stage_axes()
        save_blend()
    if STAGE in ("render", "all"):
        stage_render()
