"""Dresses and lights the mall's four painted-sky scenes (`scene_2909`, `scene_3012`, `scene_2991`, `scene_3008`; docs/BLENDER_AREAS.md section 3) in
Blender, bakes a day set and the emergency set, and exports world/<scene>.glb and world/<scene>.json.

Re-runnable, from the repo root, one scene a run:

    blender -b --python tools/blender/build_mall_sky.py -- --scene scene_2909 --stage art,check      (the art and the layout objects; .blend, layout file, check)
    blender -b blender/scenes/scene_2909.blend --python tools/blender/build_mall_sky.py -- --scene scene_2909 --stage bake [--samples 512]
    blender -b blender/scenes/scene_2909.blend --python tools/blender/build_mall_sky.py -- --scene scene_2909 --stage export
    blender -b blender/scenes/scene_2909.blend --python tools/blender/build_mall_sky.py -- --scene scene_2909 --stage axes
    blender -b blender/scenes/scene_2909.blend --python tools/blender/build_mall_sky.py -- --scene scene_2909 --stage render [--set night]
    python tools/blender/pack_scene.py scene_2909 --work <work>                                    (WebP lightmaps and textures -> world/)

`--stage art,check,bake,export,axes,render` runs several stages in one go; `--work <dir>` is the work folder (lightmap PNGs, the raw GLB, the
night stills).

The layout is the greybox's: tools/blender/build_mall_greybox.py (imported here; no coordinate of the layout is typed in) gives every collider,
door, link, marker and spot. None of the four scenes is turned, so the art is built in the scene's own (game) frame. Every greybox solid box
gets its art over it (one object per box, or a group of objects whose boxes together cover it), and everything added that a walker could bump
into stands on a greybox solid, sits within 4.5 cm of a wall, hangs overhead, or is passable (`decor_`). The same names (COL_, DoorLeaf_,
Link_/Arrive_, Marker_, Spot_) go into the .blend, and tools/blender/export_scene.py writes the same world/<scene>.json as the greybox does.

The look: dreamlike mall interiors under a painted sky. The ceilings are the connector kit's painted sky (claude/blender-hotel-kit,
tools/blender/build_kit.py `painted_sky_pixels`: the same recipe, palette and soft brushed clouds, so the sky halls and these scenes read as one
place), carried down a cove like a trompe-l'oeil vault; the walls above a cornice are the kit's sky mural (pale at the horizon, deep blue above).
Under them, the mall's own fabric (part 1's atrium and the wings: terrazzo in a dark border, beige plaster, painted steel shutters under
hand-painted signs), faded and empty, a little wrong.

Light, as in entrance: day = the working lamps (`Lamp_Emit`, on by day, off while the mall is locked) and the day's soft sky light; night = the
emergency fittings alone (`Emergency_Emit`, on only while the mall is locked). The painted sky glows softly at all hours (`Sky_Glow`, its own
material, never switched, not baked), so the scenes never go fully dark. Both sets bake to the same lightmap UVs: `lightmap` and
`lightmap_night`. The page draws the mannequins (`Spot_mannequin_<n>`): their places are left clear.
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
sys.path.insert(0, str(ROOT / "tools/blender"))
import build_mall_greybox as G          # noqa: E402  the layout model (pure Python)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


SCENES = ("scene_2909", "scene_3012", "scene_2991", "scene_3008")
SCENE = arg("--scene", "scene_2909")
assert SCENE in SCENES, SCENE
STAGE = arg("--stage", "all")
SAMPLES = arg("--samples", 512, int)
NIGHT_SAMPLES = arg("--night-samples", None, int) or int(SAMPLES * 1.5)
DEVICE = arg("--device", "auto")
TEX = ROOT / "blender/textures/mall_sky"
BLEND = ROOT / f"blender/scenes/{SCENE}.blend"
STILLS = ROOT / f"docs/renders/{SCENE}"
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"
MARGIN_PX = 8

GB = G.build(SCENE)                                   # the layout as the game reads it (these scenes are not turned)
assert abs(GB.turn_deg) < 1e-9
BOXL = {b["name"]: b for b in GB.boxes}
SOLIDS = [b for b in GB.boxes if b["col"]]
T, SLAB = G.T, G.SLAB
DOOR_H, DOOR_W, KIT_W, KIT_H = G.DOOR_H, G.DOOR_W, G.KIT_W, G.KIT_H

# each scene's rooms: name -> (x0, x1, z0, z1, floor y, ceiling height above it, the cornice (sky mural above), the cove's foot (vault above))
ROOMS = {
    "scene_2909": {"Court": (-12.0, 12.0, -12.0, 12.0, 0.0, 8.0, 4.2, 6.4)},
    "scene_3012": {"Street": (-16.0, 16.0, -6.0, 6.0, 0.0, 8.0, 3.4, 7.0)},
    "scene_2991": {"Play": (-16.0, 2.0, -7.0, 7.0, 0.0, 7.0, 2.8, 5.6), "Carousel": (2.2, 16.0, -7.0, 7.0, 0.0, 9.0, 2.8, 7.6)},
    "scene_3008": {"Well": (-8.0, 8.0, -12.0, 12.0, 0.0, 9.5, 7.9, 7.9)},
}[SCENE]
SEEN = {"scene_2909": (2.2, -0.2), "scene_3012": (2.2, 0.8), "scene_2991": (2.5, 0.8), "scene_3008": (6.7, 0.8)}[SCENE]   # (up, down): see cull
_xs = [v for b in GB.boxes for v in (b["min"][0], b["max"][0])]
_ys = [v for b in GB.boxes for v in (b["min"][1], b["max"][1])]
_zs = [v for b in GB.boxes for v in (b["min"][2], b["max"][2])]
ENV = ((min(_xs) - 1e-3, max(_xs) + 1e-3), (min(_ys) - 1e-3, max(_ys) + 1e-3), (min(_zs) - 1e-3, max(_zs) + 1e-3))


def B(p):
    """game (x, y, z) -> Blender (x, -z, y)"""
    return Vector((p[0], -p[2], p[1]))


def room_of(x, z):
    for k, r in ROOMS.items():
        if r[0] - 0.25 <= x <= r[1] + 0.25 and r[2] - 0.25 <= z <= r[3] + 0.25:
            return k
    return next(iter(ROOMS))


# ---------------------------------------------------------------- materials
IMG_CACHE, MATS, TILES = {}, {}, {}


def image(fn, srgb=True):
    key = (fn, srgb)
    if key not in IMG_CACHE:
        im = bpy.data.images.load(str(TEX / fn))
        im.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
        IMG_CACHE[key] = im
    return IMG_CACHE[key]


def material(name, color=(0.5, 0.5, 0.5), rough=0.8, metal=0.0, diff=None, img=None, tint=None, emit=None, alpha=None, tile=None):
    """A Principled material (entrance's): `tint` multiplies the diffuse texture by a constant colour (the exporter writes baseColorFactor)."""
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
    if diff or img is not None:
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = img if img is not None else image(diff, True)
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
        if alpha == "texture":
            nt.links.new(n.outputs["Alpha"], bsdf.inputs["Alpha"])
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit[0], 1)
        bsdf.inputs["Emission Strength"].default_value = emit[1]
    if alpha is not None:
        if alpha != "texture":
            bsdf.inputs["Alpha"].default_value = alpha
        for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, val)
            except (AttributeError, TypeError):
                pass
    TILES[name] = tile or 1.0
    MATS[name] = m
    return m


def emissive_image(name, img, strength, tile=1.0):
    """Emission only (the base colour black): the page shows the picture as it is, unlit (the painted sky, the EXIT sign)."""
    m = material(name, color=(0, 0, 0), rough=0.9, tile=tile)
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = img
    nt.links.new(nt.nodes["UV Map"].outputs["UV"], tx.inputs["Vector"])
    nt.links.new(tx.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = strength
    return m


LAMP_EMIT = 10.0          # Lamp_Emit's exported strength (lamp lenses, lanterns, bulbs, the cornice troughs): on by day, off while locked
EMERG_EMIT = 6.0          # Emergency_Emit's exported strength (the emergency heads): on only while the mall is locked
SKY_SHOW = 1.0            # Sky_Glow's exported strength: the page shows the painted sky's own colours, day and night
SKY_BAKE = {"day": 2.2, "night": 1.6}   # Sky_Glow in the bakes: the vault's soft light on the room under it (never switched off)
FACADES = {"Facade_Ochre": (0.95, 0.80, 0.56), "Facade_Rose": (0.93, 0.72, 0.70), "Facade_Mint": (0.72, 0.86, 0.76), "Facade_Blue": (0.72, 0.80, 0.92)}


def make_materials(gen):
    # the mall's surfaces: entrance's and the wings' textures and tints, so these rooms read as the same building
    material("Floor_Terrazzo", diff="terrazzo_tiles_diff_1k.jpg", tint=(0.92, 0.88, 0.84), rough=0.4, tile=2.0)
    material("Floor_Border", diff="terrazzo_tiles_diff_1k.jpg", tint=(0.42, 0.38, 0.36), rough=0.4, tile=2.0)
    material("Wall_Plaster", diff="beige_wall_001_diff_1k.jpg", tint=(0.92, 0.88, 0.80), rough=0.9, tile=2.4)
    material("Ceiling_Paint", diff="beige_wall_001_diff_1k.jpg", tint=(0.96, 0.95, 0.92), rough=0.95, tile=3.0)
    material("Trim_Paint", diff="plastered_wall_04_diff_1k.jpg", tint=(0.93, 0.92, 0.88), rough=0.55, tile=1.2)
    material("Shutter_Metal", diff="painted_metal_shutter_diff_1k.jpg", tint=(0.80, 0.80, 0.80), rough=0.5, metal=0.2, tile=2.0)
    material("Bench_Wood", diff="dark_wood_diff_1k.jpg", tint=(0.95, 0.85, 0.75), rough=0.6, tile=0.9)
    material("Cloth_Sheet", diff="rough_linen_diff_512.jpg", tint=(1.0, 0.94, 0.82), rough=1.0, tile=0.8)
    material("Metal_Dark", color=(0.05, 0.05, 0.055), rough=0.45, metal=0.7)
    material("Metal_Steel", color=(0.42, 0.43, 0.44), rough=0.45, metal=0.85)
    material("Plastic_White", color=(0.70, 0.70, 0.67), rough=0.5)
    material("Sign_Paint", img=gen["signs"], rough=0.7)
    material("Poster_Art", img=gen["posters"], rough=0.6)
    material("Door_Leaves", img=gen["doors"], rough=0.6)
    material("Decal_Dust", img=gen["dust"], alpha="texture", rough=1.0)
    material("Sky_Mural", img=gen["mural"], rough=0.9, tile=4.0)                    # the kit's Sky_Mural: the walls above the cornice
    emissive_image("Sky_Glow", gen["vault"], SKY_BAKE["day"], tile=6.0)              # the kit's laylight: the vault, a sky lit from behind
    material("Lamp_Emit", color=(1.0, 0.92, 0.80), rough=0.4, emit=((1.0, 0.90, 0.74), LAMP_EMIT))
    material("Emergency_Emit", color=(0.9, 0.95, 1.0), rough=0.3, emit=((0.85, 0.93, 1.0), EMERG_EMIT))
    emissive_image("Sign_Exit", gen["exit"], 3.0)
    if SCENE == "scene_2909":
        material("Court_Mosaic", img=gen["mosaic"], rough=0.35)
        material("Plant_Plastic", color=(0.20, 0.42, 0.20), rough=0.55)
        material("Awning_Stripe", img=gen["stripes"], rough=0.9, tile=1.0)
        material("Concrete", diff="concrete_floor_02_diff_1k.jpg", tint=(0.78, 0.76, 0.72), rough=0.8, tile=1.6)
    if SCENE == "scene_3012":
        material("Floor_Cobble", img=gen["cobble"], rough=0.7, tile=2.0)
        material("Floor_Pave", img=gen["paving"], rough=0.75, tile=2.4)
        for k, t in FACADES.items():
            material(k, diff="plastered_wall_04_diff_1k.jpg", tint=t, rough=0.85, tile=2.0)
        material("Window_Paint", img=gen["windows"], rough=0.3)
        material("Shop_Display", img=gen["displays"], rough=0.6)
        material("Glass_Clear", color=(0.55, 0.62, 0.62), rough=0.08, alpha=0.22)
        material("Awning_Stripe", img=gen["stripes"], rough=0.9, tile=1.0)
        material("Bunting", img=gen["bunting"], rough=0.8)
    if SCENE == "scene_2991":
        material("Floor_Rubber", img=gen["rubber"], rough=0.9, tile=2.4)
        material("Padding_Vinyl", img=gen["padding"], rough=0.5, tile=1.2)
        material("Net_Mesh", img=gen["net"], alpha="texture", rough=0.9, tile=0.6)
        material("Ball_Pit", img=gen["balls"], rough=0.4, tile=0.8)
        material("Slide_Plastic", color=(0.95, 0.70, 0.10), rough=0.35)
        material("Carousel_Paint", img=gen["carousel"], rough=0.45)
        material("Horse_Enamel", color=(0.86, 0.82, 0.74), rough=0.3)
        material("Brass", color=(0.72, 0.55, 0.26), rough=0.3, metal=0.9)
        material("Carousel_Red", color=(0.60, 0.12, 0.11), rough=0.4)
    if SCENE == "scene_3008":
        material("Escalator_Step", img=gen["treads"], rough=0.4, metal=0.6, tile=1.0)
        material("Glass_Clear", color=(0.55, 0.62, 0.62), rough=0.08, alpha=0.22)
        material("Rubber_Black", color=(0.02, 0.02, 0.025), rough=0.6)
        material("Plant_Plastic", color=(0.20, 0.42, 0.20), rough=0.55)
        material("Concrete", diff="concrete_floor_02_diff_1k.jpg", tint=(0.78, 0.76, 0.72), rough=0.8, tile=1.6)


# ---------------------------------------------------------------- geometry helpers (entrance's and the wings'; game axes)
FACE_DIRS = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+y": (0, 1, 0), "-y": (0, -1, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}


def cube(bm, gmin, gmax, skip=()):
    """An axis box from gmin to gmax (game frame); `skip` leaves out faces by their outward direction ('+y', '-z', ...), the box still spans
    the whole volume (so the layout check reads it as covering its collider)."""
    x0, y0, z0 = gmin
    x1, y1, z1 = gmax
    if not skip:
        a, b = B(gmin), B(gmax)
        c = (a + b) / 2
        s = Vector((abs(a.x - b.x), abs(a.y - b.y), abs(a.z - b.z)))
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(c) @ Matrix.Diagonal((s.x, s.y, s.z, 1.0)))
        return
    V = {(i, j, k): bm.verts.new(B((x1 if i else x0, y1 if j else y0, z1 if k else z0))) for i in (0, 1) for j in (0, 1) for k in (0, 1)}
    quads = {"+x": [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)], "-x": [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)],
             "+y": [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)], "-y": [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
             "+z": [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)], "-z": [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)]}
    for k, q in quads.items():
        if k in skip:
            continue
        f = bm.faces.new([V[c] for c in q])
        f.normal_update()
        want = B(FACE_DIRS[k]) - B((0, 0, 0))
        if f.normal.dot(want) < 0:
            f.normal_flip()
    # (skip at most two opposite faces: every corner stays on a face, so the mesh keeps the box's full extent)


def cyl(bm, p0, p1, r0, r1=None, seg=16, cap=True):
    a, b = B(p0), B(p1)
    d = b - a
    q = d.to_track_quat("Z", "Y")
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=seg, radius1=r0, radius2=r0 if r1 is None else r1, depth=d.length,
                          matrix=Matrix.Translation((a + b) / 2) @ q.to_matrix().to_4x4())


def sphere(bm, p, r, seg=10, scale=(1, 1, 1)):
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2 + 1, radius=r,
                              matrix=Matrix.Translation(B(p)) @ Matrix.Diagonal((scale[0], scale[2], scale[1], 1.0)))


def disc(bm, p, r, seg=16, up=False):
    """A flat disc facing down (a downlight's rim or lens), or up."""
    vs = [bm.verts.new(B((p[0] + r * math.cos(2 * math.pi * k / seg), p[1], p[2] - r * math.sin(2 * math.pi * k / seg)))) for k in range(seg)]
    f = bm.faces.new(vs)
    f.normal_update()
    if (f.normal.z > 0) != up:
        f.normal_flip()
    return f


def quad(bm, p0, p1, p2, p3):
    return bm.faces.new([bm.verts.new(B(p)) for p in (p0, p1, p2, p3)])


def box_uv(bm, tile):
    """UV0: box projection in metres / tile from world positions, so a texture runs on across the pieces of a wall."""
    uvl = bm.loops.layers.uv["UVMap"]
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for lp in f.loops:
            p = lp.vert.co
            gx, gy, gz = p.x, p.z, -p.y
            u, v = (gz, gy) if ax == 0 else ((gx, gy) if ax == 1 else (gx, gz))
            lp[uvl].uv = (u / tile, v / tile)


ART = STANDIN = DOORS_C = LAYOUT_C = None
HANDLED = set()                   # greybox solids whose art a builder has made


def finish(name, bm, mat, coll=None, smooth=False, tile=None, sharp_deg=35, keep_uv=False, keep_normals=False):
    for e in bm.edges:
        if smooth and len(e.link_faces) == 2:
            e.smooth = e.calc_face_angle(0.0) < math.radians(sharp_deg)
        else:
            e.smooth = not (len(e.link_faces) == 2 and e.calc_face_angle(0.0) > math.radians(1))
    for f in bm.faces:
        f.smooth = smooth
    if not (keep_uv or keep_normals):
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


def part(name, mat, build, smooth=False, tile=None, coll=None, keep_normals=False, keep_uv=False, sharp_deg=35):
    bm = bmesh.new()
    if keep_uv:
        bm.loops.layers.uv.new("UVMap")
    build(bm)
    return finish(name, bm, mat, coll, smooth, tile, sharp_deg=sharp_deg, keep_normals=keep_normals, keep_uv=keep_uv)


def boxart(name, mat, mn, mx, skip=(), tile=None, host=None):
    """One box of art; `host` names the greybox solid it dresses (so the fallback does not dress it again)."""
    if host:
        HANDLED.add(host)
    return part(name, mat, lambda bm: cube(bm, mn, mx, skip), tile=tile, keep_normals=bool(skip))


def solid_art(b, mat, skip=(), tile=None, name=None):
    return boxart(name or b["name"], mat, b["min"], b["max"], skip, tile, host=b["name"])


def dedupe_inner(bm):
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.verts.index_update()
    seen = {}
    for f in bm.faces:
        seen.setdefault(frozenset(v.index for v in f.verts), []).append(f)
    inner = [f for fs in seen.values() if len(fs) > 1 for f in fs]
    bmesh.ops.delete(bm, geom=inner, context="FACES_ONLY")
    bmesh.ops.delete(bm, geom=[e for e in bm.edges if not e.link_faces], context="EDGES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")


def orient_faces(ob, toward):
    tb = B(toward)
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    for f in bm.faces:
        if f.normal.dot(tb) < 0:
            f.normal_flip()
    bm.to_mesh(me)
    bm.free()


def panel_at(name, mat, centre, normal, w, h, uv=(0, 0, 1, 1), coll=None):
    """A flat quad facing `normal` (a unit game vector, horizontal), w wide, h tall, its UV the rectangle uv, the picture upright."""
    n = Vector(normal)
    r = Vector((n.z, 0.0, -n.x))                # facing the surface: your right hand
    up = Vector((0, 1, 0))
    c = Vector(centre)
    pts = [c - r * w / 2 - up * h / 2, c + r * w / 2 - up * h / 2, c + r * w / 2 + up * h / 2, c - r * w / 2 + up * h / 2]
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    f = quad(bm, *[tuple(p) for p in pts])
    u0, v0, u1, v1 = uv
    for lp, (s, t) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = (u0 + (u1 - u0) * s, v0 + (v1 - v0) * t)
    ob = finish(name, bm, mat, coll, keep_uv=True)
    orient_faces(ob, tuple(n))
    return ob


def flat_decal(bm, x0, x1, z0, z1, y=0.002, uv=(0, 0, 1, 1)):
    uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
    f = quad(bm, (x0, y, z1), (x1, y, z1), (x1, y, z0), (x0, y, z0))
    u0, v0, u1, v1 = uv
    for lp, (s, t) in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        lp[uvl].uv = (u0 + (u1 - u0) * s, v0 + (v1 - v0) * t)
    f.normal_update()
    if f.normal.z < 0:
        f.normal_flip()


def corrugated(bm, normal, a0, a1, y0, y1, plane, depth=0.012, pitch=0.075, step=0.025):
    """A roller shutter's curtain (entrance's) in a wall plane: normal '+x'/'-x' runs along z at x = plane (+ ripple toward the room), '+z'/'-z'
    runs along x at z = plane."""
    sgn = 1 if normal[0] == "+" else -1
    rows = int(math.ceil((y1 - y0) / step))
    vs = []
    for i in range(rows + 1):
        y = y0 + (y1 - y0) * i / rows
        off = plane + sgn * depth * 0.5 * (1 - math.cos(2 * math.pi * (y - y0) / pitch))
        if normal[1] == "x":
            vs.append((bm.verts.new(B((off, y, a0))), bm.verts.new(B((off, y, a1)))))
        else:
            vs.append((bm.verts.new(B((a0, y, off))), bm.verts.new(B((a1, y, off)))))
    for (p0, p1), (q0, q1) in zip(vs, vs[1:]):
        bm.faces.new((p0, p1, q1, q0))


def drape_box(bm, x0, x1, z0, z1, h, rng, hem=(0.06, 0.22), flare=0.03, folds=0.045, top=0.05, P=96):
    """A dust sheet thrown over a box-shaped thing (the wings'): a domed top and four skirts falling to a ragged hem, within x0..x1, z0..z1."""
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    hx, hz = (x1 - x0) / 2, (z1 - z0) / 2
    ph = rng.uniform(0, 6.3, 6)

    def perim(t, sx, sz):
        L_ = 2 * (sx + sz)
        s = (t % 1.0) * 2 * L_
        q = 2 * sx, 2 * sz
        if s < q[0]:
            return -sx + s, -sz
        s -= q[0]
        if s < q[1]:
            return sx, -sz + s
        s -= q[1]
        if s < q[0]:
            return sx - s, sz
        s -= q[0]
        return -sx, sz - s
    rings = []
    for f in [0.25, 0.55, 0.8, 0.94]:
        y = h + top * (1 - f * f)
        rings.append([(cx + perim(i / P, hx * f, hz * f)[0], y, cz + perim(i / P, hx * f, hz * f)[1]) for i in range(P)])
    m = 6
    for j in range(m + 1):
        u = j / m
        ring = []
        for i in range(P):
            t = i / P
            px, pz = perim(t, hx, hz)
            fold = folds * u * (math.sin(t * 37 + ph[0]) + 0.6 * math.sin(t * 83 + ph[1]))
            out = min(flare, max(-0.01, fold + flare * u * 0.5))
            nx_, nz_ = (px / hx if abs(abs(px) - hx) < 1e-6 else 0.0), (pz / hz if abs(abs(pz) - hz) < 1e-6 else 0.0)
            hm = hem[0] + (hem[1] - hem[0]) * (0.5 + 0.5 * math.sin(t * 11 + ph[2]) * math.sin(t * 5 + ph[3]))
            y = h - (h - hm) * u
            ring.append((cx + px + nx_ * out, y, cz + pz + nz_ * out))
        rings.append(ring)
    verts = [[bm.verts.new(B(p)) for p in r] for r in rings]
    cv = bm.verts.new(B((cx, h + top, cz)))
    for i in range(P):
        bm.faces.new((cv, verts[0][i], verts[0][(i + 1) % P]))
    for r0, r1 in zip(verts, verts[1:]):
        for i in range(P):
            bm.faces.new((r0[i], r1[i], r1[(i + 1) % P], r0[(i + 1) % P]))
    inside = B((cx, h * 0.3, cz))
    bm.normal_update()
    for f in bm.faces:
        if f.normal.dot(f.calc_center_median() - inside) < 0:
            f.normal_flip()


def loft(bm, rings, closed=True, cap_top=False, cap_bottom=False):
    """Faces between successive rings of game points (each ring the same length)."""
    vs = [[bm.verts.new(B(p)) for p in r] for r in rings]
    n = len(rings[0])
    for r0, r1 in zip(vs, vs[1:]):
        for i in range(n if closed else n - 1):
            bm.faces.new((r0[i], r0[(i + 1) % n], r1[(i + 1) % n], r1[i]))
    if cap_bottom:
        bm.faces.new(vs[0][::-1])
    if cap_top:
        bm.faces.new(vs[-1])
    return vs


# ---------------------------------------------------------------- generated pictures (own work, numpy, fixed seeds; the 5 x 7 font is entrance's)
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
    "&": ["01100", "10010", "10100", "01000", "10101", "10010", "01101"], "!": ["00100", "00100", "00100", "00100", "00100", "00000", "00100"],
    "'": ["00100", "00100", "01000", "00000", "00000", "00000", "00000"], "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    ">": ["01000", "00100", "00010", "00001", "00010", "00100", "01000"], "<": ["00010", "00100", "01000", "10000", "01000", "00100", "00010"],
    ",": ["00000"] * 5 + ["00100", "01000"], ":": ["00000", "00100", "00000", "00000", "00000", "00100", "00000"],
    "0": ["01110", "10011", "10101", "10101", "11001", "10001", "01110"], "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00110", "01000", "10000", "11111"], "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["10010", "10010", "10010", "11111", "00010", "00010", "00010"], "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["01110", "10000", "11110", "10001", "10001", "10001", "01110"], "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"], "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
}


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


def periodic_noise(h, w, rng, beta=2.2, lo=2.0):
    """Tileable fractal noise (the kit's): white noise shaped in the frequency domain (power ~ 1 / f^beta), normalised to 0..1."""
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


def painted_sky_pixels(S=1024, seed=7, soft=1.0, flat=False, dim=1.0):
    """The connector kit's painted sky (tools/blender/build_kit.py on claude/blender-hotel-kit, the same recipe and palette): a blue that pales
    toward the bottom of the picture, and soft brushed clouds; tileable both ways. `flat`: no gradient (the ceiling's)."""
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


def text_mask(text, h, w, rng, fill=0.62, maxw=0.9, painted=True):
    """A line of capitals in the 5 x 7 pixel font, centred in an h x w mask; `painted` rounds the strokes off like a brush's (entrance's)."""
    adv = 6
    units = max(1, len(text) * adv - 1)
    s = max(1, int(min(w * maxw / units, h * fill / 7)))
    m = np.zeros((h, w), np.float32)
    x = (w - units * s) // 2
    y0 = (h - 7 * s) // 2
    for ch in text:
        g = GLYPHS.get(ch, GLYPHS[" "])
        jy = int(rng.integers(-max(1, s // 5), max(1, s // 5) + 1)) if painted else 0
        for r, row in enumerate(g):
            for c, v in enumerate(row):
                if v == "1":
                    m[max(0, y0 + jy + r * s):max(0, y0 + jy + (r + 1) * s), x + c * s:x + (c + 1) * s] = 1
        x += adv * s
    if painted:
        k = max(1, s // 3)
        m = blur(m, k, 2)
        m = np.clip((m - 0.5) * 6 + (vnoise(h, w, rng, 4, 16) - 0.5) * 1.2 + 0.5, 0, 1)
    return m


def put_text(img, text, y0, y1, x0, x1, col, rng, fill=0.62, maxw=0.9, painted=False):
    m = text_mask(text, y1 - y0, x1 - x0, rng, fill, maxw, painted)
    img[y0:y1, x0:x1] = img[y0:y1, x0:x1] * (1 - m[..., None]) + np.array(col) * m[..., None]


def age(img, rng, amount=1.0, chips=0.0, bleach=0.0):
    """Faded, grimy, sun-bleached toward the top; chipped paint showing the primer (the wings')."""
    h, w = img.shape[:2]
    n = vnoise(h, w, rng, 5, 6)
    img = img * (0.82 + 0.3 * amount * n[..., None])
    if bleach:
        g = img.mean(axis=2, keepdims=True)
        f = (np.linspace(1, 0, h)[:, None, None] * bleach)
        img = img * (1 - f) + (g * 0.9 + 0.12) * f
    if chips:
        c = (vnoise(h, w, rng, 3, 24) > 1 - chips).astype(np.float32)
        img = img * (1 - c[..., None] * 0.7) + np.array([0.55, 0.52, 0.46]) * c[..., None] * 0.7
    return np.clip(img, 0, 1)


SIGN_STYLE = [((0.36, 0.10, 0.12), (0.93, 0.86, 0.70)), ((0.10, 0.16, 0.36), (0.92, 0.92, 0.90)), ((0.12, 0.30, 0.18), (0.98, 0.84, 0.32)),
              ((0.86, 0.84, 0.78), (0.62, 0.10, 0.08)), ((0.10, 0.36, 0.36), (0.95, 0.90, 0.78)), ((0.06, 0.06, 0.07), (0.98, 0.58, 0.18)),
              ((0.40, 0.46, 0.52), (0.96, 0.96, 0.96)), ((0.62, 0.14, 0.10), (0.99, 0.86, 0.22))]     # entrance's eight board colours
SIGN_W, SIGN_R, SIGN_ROWS = 1024, 128, 16
SIGNS = {   # key -> (text, style): every painted board in the scene, one atlas row each
    "scene_2909": {"w0": ("GARDEN CENTRE", 2), "w1": ("UMBRELLAS", 1), "e0": ("SUNGLASSES", 5), "e1": ("KITES & BALLOONS", 7),
                   "court": ("THE SKY COURT", 4), "band": ("BANDSTAND", 3), "s0": ("POSTCARDS", 0), "s1": ("ICE CREAM", 6)},
    "scene_3012": {"N1": ("BAKERY", 0), "N2": ("FLORIST", 2), "N3": ("HATTER", 1), "N4": ("TOYS", 7), "S1": ("CLOCKMAKER", 4),
                   "S2": ("SWEETS", 3), "S3": ("BOOKS", 5), "S4": ("TEA ROOM", 6), "street": ("HIGH STREET", 1), "arch": ("THIS WAY", 4)},
    "scene_2991": {"play": ("SOFT PLAY", 2), "carousel": ("CAROUSEL", 7), "party": ("PARTY ROOM", 3), "tokens": ("TOKENS", 5)},
    "scene_3008": {"W_-9": ("SHOE REPAIR", 0), "E_-9": ("PERFUME", 4), "W_6": ("KEYS CUT", 1), "E_6": ("WATCHES", 7),
                   "gallery": ("TRAVEL AGENT", 2), "gal_n0": ("PHOTO BOOTH", 6), "gal_n1": ("OPTICIAN", 3), "info": ("INFORMATION", 1)},
}[SCENE]
SIGN_KEYS = list(SIGNS)


def signs_pixels():
    """Every painted sign of the scene, one per row of a 1024 x 2048 atlas: a faded board colour, the name in hand-painted capitals, sun-bleaching
    toward the top, grime and chipped paint (entrance's recipe)."""
    W_, R = SIGN_W, SIGN_R
    rng = np.random.default_rng(17 + len(SCENE))
    img = np.zeros((R * SIGN_ROWS, W_, 3), np.float32)
    img[:] = (0.5, 0.5, 0.5)
    for i, key in enumerate(SIGN_KEYS):
        text, st = SIGNS[key]
        bg, fg = SIGN_STYLE[st % len(SIGN_STYLE)]
        row = np.zeros((R, W_, 3), np.float32)
        row[:] = bg
        if text == "SOFT PLAY":
            row[:] = (0.98, 0.92, 0.55)
            cols = [(0.90, 0.15, 0.15), (0.10, 0.45, 0.85), (0.15, 0.65, 0.25), (0.95, 0.50, 0.05)]
            full = text_mask(text, R, W_, rng, fill=0.66, maxw=0.86, painted=True)
            xs = np.nonzero(full.max(axis=0) > 0.5)[0]
            if len(xs):
                x0, x1 = xs.min(), xs.max()
                band = ((np.arange(W_) - x0) / max(1, (x1 - x0)) * len(text)).astype(int)
                for j in range(len(text)):
                    sel = (band == j)[None, :] * full
                    row = row * (1 - sel[..., None]) + np.array(cols[j % 4]) * sel[..., None]
        else:
            m = text_mask(text, R, W_, rng, fill=0.62 if len(text) < 14 else 0.5)
            row = row * (1 - m[..., None]) + np.array(fg) * m[..., None]
        n = vnoise(R, W_, rng, 5, 6)
        fade = np.linspace(1.12, 0.92, R)[:, None, None]
        row = row * (0.78 + 0.35 * n[..., None]) * fade
        chips = (vnoise(R, W_, rng, 3, 24) > 0.76).astype(np.float32)
        row = row * (1 - chips[..., None] * 0.6) + np.array([0.55, 0.52, 0.46]) * chips[..., None] * 0.6
        row[:3] = row[-3:] = row[:, :3] = row[:, -3:] = np.array(bg) * 0.5
        img[i * R:(i + 1) * R] = row
    return np.clip(img, 0, 1)


def sign_uv(key):
    r = SIGN_KEYS.index(key)
    return (0.0, 1 - (r + 1) / SIGN_ROWS, 1.0, 1 - r / SIGN_ROWS)


# the poster atlas, 2048 x 2048: eight 512 x 768 cells (two rows of four), then four 512 x 512 squares
PW = 2048


def cell_px(i):
    if i < 8:
        return (i % 4) * 512, (i // 4) * 768, 512, 768
    j = i - 8
    return j * 512, 1536, 512, 512


def cell_uv(i, sub=(0, 0, 1, 1)):
    x, y, w, h = cell_px(i)
    s0, t0, s1, t1 = sub
    return ((x + w * s0) / PW, 1 - (y + h * t1) / PW, (x + w * s1) / PW, 1 - (y + h * t0) / PW)


def notice(h, w, rng, title, lines, paper=(0.92, 0.90, 0.84), ink=(0.55, 0.08, 0.06)):
    """A printed notice taped up (the wings'): a title, lines of text, tape at the corners, curled and yellowed."""
    img = np.ones((h, w, 3), np.float32) * np.array(paper)
    put_text(img, title, int(h * 0.06), int(h * 0.2), 20, w - 20, ink, rng, fill=0.7, maxw=0.9)
    img[int(h * 0.22):int(h * 0.225), 30:w - 30] = ink
    y = int(h * 0.28)
    lh = int(h * 0.075)
    for ln in lines:
        put_text(img, ln, y, y + lh, 30, w - 30, (0.15, 0.14, 0.13), rng, fill=0.7, maxw=0.88)
        y += lh
    while y < h * 0.9:
        ww = int(rng.uniform(0.5, 0.85) * (w - 60))
        img[y + lh // 3:y + lh // 3 + 4, 30:30 + ww] = (0.45, 0.44, 0.42)
        y += lh // 2
    for (ty, tx) in ((0, 0), (0, w - 60), (h - 30, 0), (h - 30, w - 60)):
        img[ty:ty + 30, tx:tx + 60] = img[ty:ty + 30, tx:tx + 60] * 0.6 + np.array([0.85, 0.8, 0.6]) * 0.4
    return age(img, rng, 0.8)


def travel_poster(h, w, rng, title, tagline, c0, c1):
    """A faded holiday poster: a painted sky over a sea or hills, a sun, the title in the pixel font."""
    yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
    img = np.array(c0) * (1 - yy[..., None]) + np.array(c1) * yy[..., None]
    d = np.sqrt(((xx - 0.68) * w / h) ** 2 + (yy - 0.36) ** 2)
    sun = np.clip((0.08 - d) * 80, 0, 1)
    img = img * (1 - sun[..., None]) + np.array([1.0, 0.93, 0.7]) * sun[..., None]
    ridge = 0.62 + 0.06 * np.sin(np.linspace(0, 7, w)) + 0.03 * (rs(rng.random((1, 17)), 1, w)[0] - 0.5)
    land = (yy > ridge[None, :]).astype(np.float32)
    img = img * (1 - land[..., None]) + np.array([0.16, 0.38, 0.52]) * land[..., None] * (0.8 + 0.3 * yy[..., None])
    put_text(img, title, int(h * 0.06), int(h * 0.17), 24, w - 24, (0.98, 0.96, 0.88), rng, fill=0.8, maxw=0.9)
    put_text(img, tagline, int(h * 0.86), int(h * 0.92), 30, w - 30, (0.98, 0.96, 0.88), rng, fill=0.7, maxw=0.85)
    img[:6] = img[-6:] = img[:, :6] = img[:, -6:] = (0.92, 0.9, 0.85)
    return age(img, rng, 1.0, 0.0, bleach=0.45)


def directory_pixels(names, title="DIRECTORY"):
    h, w = 768, 512
    rng = np.random.default_rng(19)
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (0.09, 0.11, 0.14)
    put_text(img, title, 30, 120, 0, w, (0.95, 0.80, 0.35), rng, fill=0.5, maxw=0.8)
    img[128:132, 30:-30] = (0.95, 0.80, 0.35)
    rh = (h - 170) // max(1, len(names))
    for i, name in enumerate(names):
        put_text(img, f"{i + 1} {name}", 150 + i * rh, 150 + (i + 1) * rh, 0, w, (0.90, 0.90, 0.86), rng, fill=0.42, maxw=0.92)
    n = vnoise(h, w, rng, 5, 6)
    img = img * (0.8 + 0.3 * n[..., None])
    img[:6] = img[-6:] = img[:, :6] = img[:, -6:] = (0.35, 0.36, 0.38)
    return np.clip(img, 0, 1)


def window_sky(h, w, rng):
    """A shop window that shows only sky: the slightly wrong one."""
    sky = painted_sky_pixels(256, seed=int(rng.integers(0, 99)), dim=0.95)
    return rs(sky, h, w)


def shop_display(h, w, rng, kind):
    """A shop window's display seen through dusty glass (own drawing): shelves of loaves, buckets of flowers, hats on stands, toys, clocks,
    jars of sweets, books, a tea room's tables."""
    img = np.ones((h, w, 3), np.float32) * np.array([0.16, 0.12, 0.10])
    yy, xx = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
    pal = {"bakery": [(0.80, 0.58, 0.30), (0.70, 0.46, 0.22), (0.90, 0.76, 0.50)], "flowers": [(0.90, 0.25, 0.35), (0.98, 0.85, 0.25), (0.65, 0.35, 0.80), (0.95, 0.95, 0.92)],
           "hats": [(0.25, 0.20, 0.18), (0.70, 0.62, 0.45), (0.55, 0.15, 0.15), (0.20, 0.28, 0.45)], "toys": [(0.90, 0.15, 0.15), (0.15, 0.45, 0.85), (0.98, 0.80, 0.10), (0.20, 0.65, 0.30)],
           "clocks": [(0.85, 0.80, 0.65), (0.55, 0.40, 0.20), (0.75, 0.65, 0.35)], "sweets": [(0.95, 0.45, 0.65), (0.55, 0.85, 0.60), (0.98, 0.85, 0.40), (0.70, 0.55, 0.95)],
           "books": [(0.55, 0.12, 0.10), (0.12, 0.20, 0.40), (0.20, 0.35, 0.22), (0.70, 0.60, 0.35), (0.82, 0.78, 0.70)], "tea": [(0.92, 0.90, 0.85), (0.60, 0.75, 0.80), (0.85, 0.70, 0.75)]}[kind]
    for sy in (0.38, 0.68, 0.94):                                                  # three shelves
        img[int(h * sy):int(h * sy) + 8] = (0.42, 0.32, 0.22)
        x = 10
        while x < w - 30:
            c = np.array(pal[int(rng.integers(0, len(pal)))]) * rng.uniform(0.75, 1.05)
            bw = int(rng.uniform(26, 60))
            bh = int(h * rng.uniform(0.1, 0.2))
            y1 = int(h * sy)
            if kind in ("clocks", "flowers", "sweets", "tea"):
                cy, cx, r = y1 - bh // 2, x + bw // 2, min(bw, bh) // 2
                m = ((np.mgrid[0:h, 0:w][0] - cy) ** 2 + (np.mgrid[0:h, 0:w][1] - cx) ** 2) < r * r
                img[m] = c
                if kind == "clocks":
                    img[cy - 2:cy + 2, cx:cx + r - 4] = (0.1, 0.1, 0.1)
                    img[cy - r + 4:cy, cx - 1:cx + 2] = (0.1, 0.1, 0.1)
            elif kind == "hats":
                img[y1 - bh // 3:y1, x:x + bw] = c
                img[y1 - bh:y1 - bh // 3, x + bw // 5:x + bw - bw // 5] = c * 0.9
            else:
                img[y1 - bh:y1, x:x + bw] = c
                if kind == "bakery":
                    img[y1 - bh:y1 - bh + 5, x + 3:x + bw - 3] = c * 1.15
            x += bw + int(rng.uniform(4, 14))
    dust = np.clip(vnoise(h, w, rng, 6, 4) * 0.9 - 0.2 + np.linspace(-0.1, 0.3, h)[:, None], 0, 0.7)
    img = img * (1 - dust[..., None]) + np.array([0.78, 0.76, 0.70]) * dust[..., None]
    return np.clip(img, 0, 1)


def posters_pixels():
    """The scene's poster atlas: notices, holiday posters, rule boards, a directory; the street's shop windows (cells of 512 x 768)."""
    rng = np.random.default_rng(61 + len(SCENE))
    img = np.zeros((PW, PW, 3), np.float32)
    img[:] = (0.5, 0.5, 0.5)

    def put(i, arr):
        x, y, w, h = cell_px(i)
        img[y:y + h, x:x + w] = rs(arr, h, w) if arr.shape[:2] != (h, w) else arr
    put(10, notice(512, 512, rng, "PARDON OUR DUST", ["THIS AREA IS BEING", "REPAINTED", "SEE YOU SOON"]))
    put(11, notice(512, 512, rng, "PLEASE", ["DO NOT TOUCH", "THE SKY"], paper=(0.95, 0.92, 0.3), ink=(0.1, 0.1, 0.1)))
    if SCENE == "scene_2909":
        put(0, notice(768, 512, rng, "BAND TONIGHT", ["SUNDAY 3PM", "ON THE BANDSTAND", "ALL WELCOME"], paper=(0.95, 0.88, 0.45), ink=(0.1, 0.15, 0.45)))
        put(1, travel_poster(768, 512, rng, "SUNNY ALL YEAR", "UNDER OUR SKY", (0.36, 0.56, 0.82), (0.95, 0.85, 0.65)))
        put(2, notice(768, 512, rng, "NO BALL GAMES", ["IN THE COURT", "BY ORDER"], paper=(0.95, 0.95, 0.92), ink=(0.75, 0.05, 0.05)))
        put(3, travel_poster(768, 512, rng, "THE SKY COURT", "THE SUN NEVER SETS", (0.30, 0.50, 0.80), (0.92, 0.80, 0.62)))
        put(7, directory_pixels(["GARDEN CENTRE", "UMBRELLAS", "SUNGLASSES", "KITES & BALLOONS", "POSTCARDS", "ICE CREAM", "BANDSTAND"]))
        put(8, window_sky(512, 512, rng))
        put(9, window_sky(512, 512, rng))
    elif SCENE == "scene_3012":
        for i, k in enumerate(("bakery", "flowers", "hats", "toys", "clocks", "sweets", "books", "tea")):
            put(i, shop_display(768, 512, rng, k))
        put(8, notice(512, 512, rng, "TO LET", ["ENQUIRE", "WITHIN"], paper=(0.95, 0.92, 0.85), ink=(0.6, 0.08, 0.06)))
        put(9, notice(512, 512, rng, "CLOSED", ["BACK IN", "FIVE MINUTES"], paper=(0.95, 0.95, 0.92), ink=(0.1, 0.1, 0.1)))
    elif SCENE == "scene_2991":
        put(0, notice(768, 512, rng, "SOFT PLAY RULES", ["NO SHOES", "NO RUNNING", "AGES 2 TO 8", "HAVE FUN"], paper=(0.98, 0.85, 0.30), ink=(0.85, 0.1, 0.1)))
        put(1, notice(768, 512, rng, "CAROUSEL", ["1 TOKEN A RIDE", "HOLD ON TIGHT", "STAY SEATED"], paper=(0.85, 0.3, 0.6), ink=(1.0, 0.95, 0.5)))
        put(2, notice(768, 512, rng, "BIRTHDAY PARTIES", ["BOOK NOW", "AT THE DESK"], paper=(0.15, 0.2, 0.45), ink=(0.95, 0.85, 0.3)))
        put(3, notice(768, 512, rng, "SORRY", ["BALL PIT", "CLOSED FOR", "CLEANING"]))
        put(7, travel_poster(768, 512, rng, "FUN FOR ALL", "COME AND PLAY", (0.40, 0.62, 0.90), (0.98, 0.88, 0.55)))
    else:
        put(0, travel_poster(768, 512, rng, "FLY AWAY", "THE SKY IS CLOSER THAN YOU THINK", (0.30, 0.52, 0.86), (0.96, 0.82, 0.60)))
        put(1, travel_poster(768, 512, rng, "ISLAND BREAKS", "TWO WEEKS OF SUN", (0.25, 0.55, 0.80), (0.95, 0.88, 0.62)))
        put(2, notice(768, 512, rng, "OUT OF ORDER", ["ESCALATOR STOPPED", "PLEASE USE", "THE STAIRS"], paper=(0.95, 0.92, 0.3), ink=(0.1, 0.1, 0.1)))
        put(3, notice(768, 512, rng, "STAND ON THE RIGHT", ["HOLD THE HANDRAIL", "CARRY DOGS"]))
        put(7, directory_pixels(["SHOE REPAIR", "PERFUME", "KEYS CUT", "WATCHES", "TRAVEL AGENT", "PHOTO BOOTH", "OPTICIAN"], "LEVEL GUIDE"))
    return np.clip(img, 0, 1)


DOOR_CELLS = {"unmarked": 0, "panel": 1, "house_green": 2, "house_red": 3, "house_blue": 4}


def doors_pixels():
    """The door leaves' atlas (2048 x 1024, five cells of 400 x 1024): the unmarked door to the wing (dull paint, scuffs), the kit's white panel
    door (to the sky halls), three painted house doors with a glazed light (the street's fronts)."""
    H_, W_ = 1024, 2048
    rng = np.random.default_rng(71)
    img = np.zeros((H_, W_, 3), np.float32)
    cw = 400
    yy, xx = np.mgrid[0:H_, 0:cw] / np.array([H_, cw])[:, None, None]
    for kind, i in DOOR_CELLS.items():
        c = np.zeros((H_, cw, 3), np.float32)
        if kind == "unmarked":
            c[:] = (0.62, 0.58, 0.50)
        elif kind == "panel":
            c[:] = (0.90, 0.90, 0.88)
            for (a0, a1, b0, b1) in ((0.12, 0.88, 0.07, 0.42), (0.12, 0.88, 0.52, 0.93)):
                fr = (xx > a0) & (xx < a1) & (yy > b0) & (yy < b1)
                inner = (xx > a0 + 0.03) & (xx < a1 - 0.03) & (yy > b0 + 0.012) & (yy < b1 - 0.012)
                c[fr & ~inner] = (0.72, 0.72, 0.70)
        else:
            base = {"house_green": (0.16, 0.36, 0.26), "house_red": (0.52, 0.14, 0.12), "house_blue": (0.14, 0.24, 0.44)}[kind]
            c[:] = base
            gl = (xx > 0.18) & (xx < 0.82) & (yy > 0.06) & (yy < 0.30)
            c[gl] = np.array([0.55, 0.72, 0.88]) * (0.8 + 0.2 * vnoise(H_, cw, rng, 3, 4)[gl][..., None])
            for (a0, a1, b0, b1) in ((0.15, 0.85, 0.36, 0.62), (0.15, 0.85, 0.68, 0.93)):
                fr = (xx > a0) & (xx < a1) & (yy > b0) & (yy < b1)
                inner = (xx > a0 + 0.035) & (xx < a1 - 0.035) & (yy > b0 + 0.014) & (yy < b1 - 0.014)
                c[fr & ~inner] = np.array(base) * 0.6
            knock = (np.abs(xx - 0.5) < 0.05) & (np.abs(yy - 0.42) < 0.012)
            c[knock] = (0.75, 0.6, 0.25)
        kick = yy > 0.93
        c[kick] = c[kick] * 0.6 + 0.15
        scuff = vnoise(H_, cw, rng, 4, 8) > 0.7
        c[scuff & (yy > 0.75)] *= 0.85
        c[:, :6] = c[:, -6:] = c[:6] = c[-6:] = c[:, :6].mean(axis=(0, 1)) * 0.6
        img[:, i * cw:(i + 1) * cw] = age(c, rng, 0.5)
    return np.clip(img, 0, 1)


def door_uv(kind):
    i = DOOR_CELLS[kind]
    return (i * 400 / 2048, 0.0, ((i + 1) * 400 - 1) / 2048, 1.0)


def exit_pixels():
    h, w = 96, 256
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (0.02, 0.45, 0.16)
    m = text_mask("EXIT", h, w, np.random.default_rng(1), fill=0.66, maxw=0.8, painted=False)
    img = img * (1 - m[..., None]) + np.array([0.95, 1.0, 0.95]) * m[..., None]
    img[:4] = img[-4:] = img[:, :4] = img[:, -4:] = (0.01, 0.2, 0.07)
    return np.clip(blur(img, 1, 1), 0, 1).astype(np.float32)


def dust_pixels():
    """Dust drifted against a wall's foot (the wings'): dense at the wall (v = 1), thinning out into the room (v = 0); it tiles along u."""
    h, w = 128, 512
    rng = np.random.default_rng(43)
    n = rs(np.tile(rng.random((9, 9)), (1, 2))[:, :17], h, w)
    n2 = vnoise(h, w, rng, 4, 8)
    v = np.linspace(0, 1, h)[::-1][:, None]
    a = np.clip(0.5 * v ** 2.2 + (n - 0.5) * 0.25 * v + (n2 - 0.5) * 0.15, 0, 0.5)
    rgba = np.zeros((h, w, 4), np.float32)
    rgba[..., :3] = np.array([0.52, 0.47, 0.40]) * (0.85 + 0.3 * n2[..., None])
    rgba[..., 3] = a
    return rgba


def mosaic_pixels():
    """The sky court's floor: a terrazzo sun in a ring of rays and a compass of the four winds, in the floor's colours (own drawing)."""
    S = 1024
    rng = np.random.default_rng(83)
    yy, xx = (np.mgrid[0:S, 0:S] - S / 2 + 0.5) / (S / 2)
    r = np.sqrt(xx ** 2 + yy ** 2)
    a = np.arctan2(yy, xx)
    cream, sand, ochre, blue, dark = (np.array(c) for c in ((0.88, 0.85, 0.78), (0.78, 0.70, 0.58), (0.80, 0.60, 0.30), (0.40, 0.52, 0.66), (0.36, 0.33, 0.31)))
    img = np.ones((S, S, 3)) * cream
    img[r > 0.92] = dark
    img[(r > 0.86) & (r <= 0.92)] = sand
    rays = (np.cos(a * 16) > 0.2) & (r > 0.34) & (r < 0.78)
    img[rays] = sand
    star = (r < 0.80) & (np.abs(np.cos(a * 2)) ** 18 * 0.8 + 0.12 > r * 0.8)
    img[star & (r > 0.3)] = blue
    img[(r < 0.30)] = ochre
    img[(r < 0.30) & (r > 0.27)] = dark
    img[(r > 0.78) & (r < 0.80)] = dark
    chips = rng.random((S, S))
    img = img * (0.92 + 0.12 * chips[..., None]) * (0.9 + 0.12 * vnoise(S, S, rng, 5, 4)[..., None])
    return np.clip(img, 0, 1).astype(np.float32)


def stripes_pixels():
    """Awning canvas: wide faded stripes, cream and a colour per row (four rows: red, green, blue, ochre), a scalloped hem at the bottom."""
    h, w = 1024, 512
    rng = np.random.default_rng(89)
    img = np.zeros((h, w, 3), np.float32)
    cols = [(0.70, 0.16, 0.14), (0.16, 0.42, 0.30), (0.18, 0.30, 0.55), (0.80, 0.58, 0.18)]
    xx = np.arange(w)[None, :]
    for k, c in enumerate(cols):
        st = ((xx // 64) % 2 == 0)
        row = np.where(st[..., None], np.array(c), np.array([0.92, 0.88, 0.78]))
        img[k * 256:(k + 1) * 256] = np.repeat(row, 256, axis=0)
    img = age(img, rng, 0.9, bleach=0.3)
    return np.clip(img, 0, 1).astype(np.float32)


def cobble_pixels():
    """Cobbles for the painted street's road: rounded setts in staggered rows, dark joints, worn tops (own drawing; it tiles)."""
    S = 1024
    rng = np.random.default_rng(97)
    n = 10
    cs = S / n
    yy, xx = np.mgrid[0:S, 0:S] + 0.5
    row = (yy // cs).astype(int)
    xo = xx + (row % 2) * cs / 2
    u, v = (xo % cs) / cs - 0.5, (yy % cs) / cs - 0.5
    d = np.maximum(np.abs(u), np.abs(v))
    stone = np.clip((0.47 - d) * 18, 0, 1)
    cid = (row * 31 + (xo // cs).astype(int) * 17) % 97
    tone = 0.75 + 0.35 * (np.sin(cid * 12.9898) * 43758.5453 % 1.0)[..., None]
    base = np.array([0.48, 0.45, 0.42]) * tone
    dome = 1 - 0.35 * (u ** 2 + v ** 2)
    img = base * dome[..., None] * stone[..., None] + np.array([0.16, 0.15, 0.14]) * (1 - stone[..., None])
    img = img * (0.88 + 0.2 * periodic_noise(S, S, rng, 2.5, lo=4.0)[..., None])
    return np.clip(img, 0, 1).astype(np.float32)


def paving_pixels():
    """Pavement flags, 0.6 m (four to a 2.4 m tile), pale and stained, thin joints (it tiles)."""
    S = 1024
    rng = np.random.default_rng(101)
    n = 4
    t = S // n
    img = np.zeros((S, S, 3), np.float32)
    for i in range(n):
        for j in range(n):
            v = rng.uniform(0.62, 0.76)
            img[i * t:(i + 1) * t, j * t:(j + 1) * t] = (v, v * 0.98, v * 0.94)
    yy, xx = np.mgrid[0:S, 0:S]
    img[((yy % t) < 4) | ((xx % t) < 4)] = (0.30, 0.29, 0.27)
    img = img * (0.86 + 0.22 * periodic_noise(S, S, rng, 2.2, lo=3.0)[..., None])
    return np.clip(img, 0, 1).astype(np.float32)


def windows_pixels():
    """The house fronts' upper windows (2048 x 1024, four cells 512 x 1024): a sash window that shows the painted sky inside the house (the
    slightly wrong one), net curtains, closed shutters, a dark empty room."""
    H_, W_ = 1024, 2048
    rng = np.random.default_rng(103)
    img = np.zeros((H_, W_, 3), np.float32)
    cw = 512
    yy, xx = np.mgrid[0:H_, 0:cw] / np.array([H_, cw])[:, None, None]
    sky = rs(painted_sky_pixels(512, seed=11, dim=0.95), H_, cw)
    for k in range(4):
        c = np.zeros((H_, cw, 3), np.float32)
        if k == 0:
            c[:] = sky
        elif k == 1:
            c[:] = (0.20, 0.18, 0.17)
            pleat = 0.5 + 0.5 * np.sin(xx * 60)
            net = (yy > 0.12)
            c[net] = (np.array([0.86, 0.84, 0.78]) * (0.82 + 0.18 * pleat[..., None]))[net]
        elif k == 2:
            c[:] = (0.20, 0.36, 0.30)
            slat = ((yy * 40) % 1.0) < 0.25
            c[slat] *= 0.6
            c[np.abs(xx - 0.5) < 0.01] = (0.1, 0.15, 0.12)
        else:
            c[:] = (0.07, 0.07, 0.08)
            c = c + np.array([0.25, 0.32, 0.40]) * np.clip(1 - yy - xx * 0.5, 0, 1)[..., None] * 0.35
        if k != 2:                                                           # the sash bars
            c[(np.abs(xx - 0.5) < 0.014) | (np.abs(yy - 0.5) < 0.008)] = (0.92, 0.92, 0.88)
        c[(xx < 0.04) | (xx > 0.96) | (yy < 0.025) | (yy > 0.975)] = (0.92, 0.92, 0.88)
        img[:, k * cw:(k + 1) * cw] = age(c, rng, 0.5)
    return np.clip(img, 0, 1).astype(np.float32)


def bunting_pixels():
    """Bunting flags: a strip of triangles' colours (u across the flags)."""
    h, w = 64, 512
    cols = [(0.85, 0.20, 0.18), (0.98, 0.82, 0.25), (0.20, 0.45, 0.80), (0.25, 0.65, 0.35), (0.95, 0.95, 0.92), (0.80, 0.40, 0.70)]
    img = np.zeros((h, w, 3), np.float32)
    for k in range(8):
        img[:, k * 64:(k + 1) * 64] = cols[k % len(cols)]
    return age(img, np.random.default_rng(107), 0.6, bleach=0.3).astype(np.float32)


def rubber_pixels():
    """Soft-play safety flooring: 0.6 m interlocking rubber tiles in faded pastels (four to a 2.4 m tile), fine speckle, the jigsaw joints."""
    S = 1024
    rng = np.random.default_rng(109)
    n = 4
    t = S // n
    cols = [(0.55, 0.70, 0.85), (0.85, 0.65, 0.55), (0.65, 0.80, 0.60), (0.88, 0.82, 0.55)]
    img = np.zeros((S, S, 3), np.float32)
    for i in range(n):
        for j in range(n):
            img[i * t:(i + 1) * t, j * t:(j + 1) * t] = cols[(i + j * 3) % 4]
    yy, xx = np.mgrid[0:S, 0:S]
    jig = ((yy % t) < 3 + 3 * (np.sin(xx / t * 2 * math.pi * 3) > 0.6)) | ((xx % t) < 3 + 3 * (np.sin(yy / t * 2 * math.pi * 3) > 0.6))
    img[jig] *= 0.55
    img = img * (0.85 + 0.25 * rng.random((S, S))[..., None]) * (0.9 + 0.15 * periodic_noise(S, S, rng, 2.2, lo=3.0)[..., None])
    return np.clip(img, 0, 1).astype(np.float32)


def padding_pixels():
    """Soft-play padding (the wings'): square vinyl cushions in red, yellow, blue and green with stitched seams and a soft shine (it tiles)."""
    S = 512
    rng = np.random.default_rng(59)
    n = 2
    t = S // n
    cols = [(0.85, 0.12, 0.10), (0.98, 0.78, 0.10), (0.10, 0.38, 0.80), (0.12, 0.62, 0.25)]
    img = np.zeros((S, S, 3), np.float32)
    yy, xx = np.mgrid[0:t, 0:t] / t
    pillow = 1 - 0.25 * ((xx - 0.5) ** 2 + (yy - 0.5) ** 2) * 4
    shine = np.clip(1 - np.sqrt((xx - 0.35) ** 2 + (yy - 0.3) ** 2) * 3, 0, 1) * 0.25
    for i in range(n):
        for j in range(n):
            c = np.array(cols[(i * n + j + i) % 4])
            img[i * t:(i + 1) * t, j * t:(j + 1) * t] = c * pillow[..., None] + shine[..., None]
    g = np.mgrid[0:S, 0:S]
    seam = (g[0] % t < 6) | (g[1] % t < 6)
    img[seam] *= 0.45
    stitch = ((g[0] % t == 14) | (g[1] % t == 14)) & ((g.sum(axis=0) // 8) % 2 == 0)
    img[stitch] = img[stitch] * 0.5 + 0.4
    return age(img, rng, 0.6)


def net_pixels():
    """Safety netting: a diamond mesh of dark cord, open between (alpha); it tiles."""
    S = 256
    yy, xx = np.mgrid[0:S, 0:S] + 0.5
    u, v = (xx + yy) / 32.0, (xx - yy) / 32.0
    d = np.minimum(np.abs(u - np.round(u)), np.abs(v - np.round(v)))
    a = np.clip((0.09 - d) * 40, 0, 1)
    rgba = np.zeros((S, S, 4), np.float32)
    rgba[..., :3] = (0.10, 0.12, 0.14)
    rgba[..., 3] = a * 0.95
    return rgba


def balls_pixels():
    """A ball pit's surface from above: packed plastic balls in red, yellow, blue and green with a highlight each (it tiles)."""
    S = 512
    rng = np.random.default_rng(113)
    img = np.ones((S, S, 3), np.float32) * 0.12
    cols = np.array([(0.85, 0.15, 0.12), (0.98, 0.80, 0.12), (0.12, 0.40, 0.85), (0.15, 0.65, 0.25), (0.92, 0.45, 0.70)])
    yy, xx = np.mgrid[0:S, 0:S]
    for _ in range(900):
        cx, cy, r = rng.uniform(0, S), rng.uniform(0, S), rng.uniform(13, 18)
        dx = (xx - cx + S / 2) % S - S / 2
        dy = (yy - cy + S / 2) % S - S / 2
        d2 = dx ** 2 + dy ** 2
        m = d2 < r * r
        sh = np.clip(1 - d2 / (r * r), 0, 1) ** 0.4
        hi = np.clip(1 - ((dx + r * 0.35) ** 2 + (dy + r * 0.35) ** 2) / (r * r * 0.12), 0, 1)
        c = cols[int(rng.integers(0, len(cols)))]
        img[m] = (c * (0.45 + 0.55 * sh[..., None]) + hi[..., None] * 0.35)[m]
    return age(np.clip(img, 0, 1), rng, 0.4)


def carousel_pixels():
    """The carousel's painted parts (1024 x 1024): the valance (top half: scallops in red and cream with gold lines), the centre column's panels
    (bottom half: mirrors and painted clouds in gilt frames)."""
    S = 1024
    rng = np.random.default_rng(127)
    img = np.zeros((S, S, 3), np.float32)
    yy, xx = np.mgrid[0:S // 2, 0:S] / np.array([S // 2, S])[:, None, None]
    val = np.where((((xx * 16) % 1.0) < 0.5)[..., None], np.array([0.70, 0.14, 0.14]), np.array([0.92, 0.86, 0.72]))
    sc = (yy > 0.72) & ((((xx * 16) % 1.0 - 0.5) ** 2 + (yy - 0.72) ** 2 * 6) > 0.09)
    val[sc] = (0.12, 0.10, 0.09)
    val[(np.abs(yy - 0.12) < 0.02) | (np.abs(yy - 0.66) < 0.015)] = (0.85, 0.66, 0.25)
    img[:S // 2] = val
    sky = rs(painted_sky_pixels(256, seed=21), S // 2, S // 2)
    pan = np.zeros((S // 2, S, 3), np.float32)
    for k in range(4):
        x0 = k * S // 4
        if k % 2 == 0:
            pan[:, x0:x0 + S // 4] = sky[:, :S // 4]
        else:
            m = np.linspace(0.55, 0.85, S // 2)[:, None, None]
            pan[:, x0:x0 + S // 4] = np.array([0.70, 0.74, 0.78]) * m
        pan[:, x0:x0 + 10] = pan[:, x0 + S // 4 - 10:x0 + S // 4] = (0.85, 0.66, 0.25)
    pan[:10] = pan[-10:] = (0.85, 0.66, 0.25)
    img[S // 2:] = pan
    return age(img, rng, 0.6, bleach=0.2).astype(np.float32)


def treads_pixels():
    """An escalator step from above (512 x 512): ribbed aluminium cleats, a yellow demarcation line along the back and both sides."""
    S = 512
    rng = np.random.default_rng(131)
    xx = np.mgrid[0:S, 0:S][1]
    yy = np.mgrid[0:S, 0:S][0]
    rib = (xx % 12) < 6
    img = np.where(rib[..., None], np.array([0.62, 0.63, 0.64]), np.array([0.30, 0.31, 0.32])).astype(np.float32)
    yel = (yy < 28) | (xx < 22) | (xx > S - 22)
    img[yel] = (0.85, 0.70, 0.12)
    img = img * (0.85 + 0.2 * vnoise(S, S, rng, 4, 4)[..., None])
    return np.clip(img, 0, 1).astype(np.float32)


def stage_work():
    d = Path(arg("--work", str(Path(os.environ.get("TEMP", "/tmp")) / f"farway_{SCENE}")))
    if not d.is_absolute():
        d = ROOT / d
    d.mkdir(parents=True, exist_ok=True)
    return d


def mk_image(name, arr, srgb=True):
    """A packed image from a float array (rows top to bottom), written as a PNG first (entrance's)."""
    h, w = arr.shape[:2]
    has_a = arr.shape[2] == 4
    im = bpy.data.images.new(name + "_gen", w, h, alpha=has_a)
    im.alpha_mode = "STRAIGHT"
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


def make_generated():
    tag = SCENE.split("_")[1]
    g = {"signs": mk_image(f"Sky{tag}_Signs", signs_pixels()), "posters": mk_image(f"Sky{tag}_Posters", posters_pixels()),
         "doors": mk_image("SkyMall_Door_Leaves", doors_pixels()), "exit": mk_image("Exit_Sign", exit_pixels()),
         "dust": mk_image("Wall_Dust", dust_pixels()),
         "mural": mk_image("Painted_Sky", painted_sky_pixels(dim=0.88)), "vault": mk_image("Painted_Sky_Ceiling", painted_sky_pixels(seed=8, flat=True))}
    if SCENE == "scene_2909":
        g["mosaic"] = mk_image("Court_Mosaic", mosaic_pixels())
        g["stripes"] = mk_image("Awning_Stripes", stripes_pixels())
    if SCENE == "scene_3012":
        g.update(cobble=mk_image("Cobbles", cobble_pixels()), paving=mk_image("Paving", paving_pixels()), windows=mk_image("House_Windows", windows_pixels()),
                 displays=g["posters"], stripes=mk_image("Awning_Stripes", stripes_pixels()), bunting=mk_image("Bunting", bunting_pixels()))
    if SCENE == "scene_2991":
        g.update(rubber=mk_image("Rubber_Tiles", rubber_pixels()), padding=mk_image("SoftPlay_Padding", padding_pixels()),
                 net=mk_image("Net_Mesh", net_pixels()), balls=mk_image("Ball_Pit", balls_pixels()), carousel=mk_image("Carousel_Paint", carousel_pixels()))
    if SCENE == "scene_3008":
        g["treads"] = mk_image("Escalator_Treads", treads_pixels())
    return g


# ---------------------------------------------------------------- dressing inside a greybox solid (a bench's slats, the soft play's frame)
INSIDE = {}                       # art object name -> greybox solids it sits inside (their faces do not hide its faces in the cull)
_INSIDE_NOW = []


class inside:
    def __init__(self, *names):
        self.names = set(names)

    def __enter__(self):
        _INSIDE_NOW.append(self.names)
        for n in self.names:
            HANDLED.add(n)

    def __exit__(self, *a):
        _INSIDE_NOW.pop()


_finish0 = finish


def finish(name, bm, mat, coll=None, smooth=False, tile=None, sharp_deg=35, keep_uv=False, keep_normals=False):   # noqa: F811
    ob = _finish0(name, bm, mat, coll, smooth, tile, sharp_deg, keep_uv, keep_normals)
    if _INSIDE_NOW:
        INSIDE[ob.name] = set().union(*_INSIDE_NOW)
    return ob


# ---------------------------------------------------------------- things on a wall: a wall is named by the way it faces (into the room) and its plane
NV = {"+x": (1, 0, 0), "-x": (-1, 0, 0), "+z": (0, 0, 1), "-z": (0, 0, -1)}


def mount(n, plane, a, y, d):
    """The point d in front of a wall's face: n '+x' (a west wall at x = plane, the room to +x), '-x', '+z', '-z'; a runs along the wall."""
    s = 1 if n[0] == "+" else -1
    return (plane + s * d, y, a) if n[1] == "x" else (a, y, plane + s * d)


def wall_box(bm, n, plane, a0, a1, y0, y1, d0, d1):
    p, q = mount(n, plane, a0, y0, d0), mount(n, plane, a1, y1, d1)
    cube(bm, [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)])


def wall_panel(name, mat, n, plane, a, y, d, w, h, uv=(0, 0, 1, 1)):
    return panel_at(name, mat, mount(n, plane, a, y, d), NV[n], w, h, uv)


def shutter_flat(tag, n, plane, a, w, y0, h, sign_key=None, d=0.02, gear_d=0.045, frame=True):
    """A shuttered shopfront flat on a wall (everything within 4.5 cm of it): the curtain, its guides and roller box, a painted frame, the
    fascia board and its sign over it."""
    a0, a1 = a - w / 2, a + w / 2
    y1 = y0 + h
    ob = part(f"Shutter_{tag}", "Shutter_Metal", lambda bm: corrugated(bm, n, a0, a1, y0 + 0.05, y1 - 0.28, mount(n, plane, 0, 0, d)[0 if n[1] == "x" else 2]),
              keep_normals=True)
    orient_faces(ob, NV[n])

    def gear(bm):
        wall_box(bm, n, plane, a0, a1, y0, y0 + 0.05, 0.0, d + 0.02)
        wall_box(bm, n, plane, a0, a1, y1 - 0.3, y1, 0.0, gear_d)
        for s_ in (a0, a1 - 0.05):
            wall_box(bm, n, plane, s_, s_ + 0.05, y0, y1 - 0.3, 0.0, d + 0.02)
    part(f"ShutterGear_{tag}", "Metal_Dark", gear)
    if frame:
        part(f"ShopFrame_{tag}", "Trim_Paint", lambda bm: [wall_box(bm, n, plane, a0 - 0.18, a0 - 0.02, y0, y1 + 0.75, 0.0, 0.035),
                                                           wall_box(bm, n, plane, a1 + 0.02, a1 + 0.18, y0, y1 + 0.75, 0.0, 0.035),
                                                           wall_box(bm, n, plane, a0 - 0.18, a1 + 0.18, y1 + 0.02, y1 + 0.1, 0.0, 0.035)])
    if sign_key:
        part(f"SignBoard_{tag}", "Metal_Dark", lambda bm: wall_box(bm, n, plane, a0, a1, y1 + 0.12, y1 + 0.72, 0.0, 0.03))
        wall_panel(f"Sign_{tag}", "Sign_Paint", n, plane, a, y1 + 0.42, 0.0305, w - 0.1, 0.52, sign_uv(sign_key))


EXITS = []


def exit_sign(tag, n, plane, a, y):
    """An EXIT box over a door (emissive, always on; in both bakes' light)."""
    part(f"Exit_{tag}_Housing", "Metal_Dark", lambda bm: wall_box(bm, n, plane, a - 0.26, a + 0.26, y - 0.1, y + 0.1, 0.0, 0.08))
    wall_panel(f"Exit_{tag}_Face", "Sign_Exit", n, plane, a, y, 0.0805, 0.44, 0.16)
    EXITS.append((mount(n, plane, a, y, 0.1), NV[n]))


EMERG = []


def emergency(tag, n, plane, a, y, d=0.0):
    """A twin-head emergency fitting on a wall (the wings'), aimed both ways along the wall and down."""
    part(f"Emergency_{tag}_Body", "Plastic_White", lambda bm: wall_box(bm, n, plane, a - 0.2, a + 0.2, y - 0.06, y + 0.06, d, d + 0.09))
    heads = []
    for k in (-1, 1):
        p = Vector(mount(n, plane, a + k * 0.14, y + 0.12, d + 0.07))
        aim = Vector(mount(n, plane, a + k * 5.0, max(0.0, y - 4.0), d + 4.0))
        heads.append((tuple(p), tuple((aim - p).normalized())))
    EMERG.extend(heads)
    part(f"Emergency_{tag}_Heads", "Plastic_White", lambda bm: [cyl(bm, tuple(Vector(p) - Vector(dd) * 0.06), tuple(Vector(p) + Vector(dd) * 0.03), 0.045, 0.055, 12)
                                                                for p, dd in heads], smooth=True)
    part(f"Emergency_{tag}_Lenses", "Emergency_Emit", lambda bm: [cyl(bm, tuple(Vector(p) + Vector(dd) * 0.03), tuple(Vector(p) + Vector(dd) * 0.036), 0.046, 0.046, 12)
                                                                  for p, dd in heads])


SPOTS_DAY, POINTS_DAY, AREAS_DAY = [], [], []      # the day set's lamps: (pos, aim, watts, cone) / (pos, watts, radius) / (pos, aim, w, h, watts)


def flood(tag, n, plane, a, y, target, watts=400.0, cone=60.0):
    """A floodlight on a bracket high on a wall (Lamp_Emit lens), aimed at a point: one of the day set's lamps."""
    p = Vector(mount(n, plane, a, y, 0.35))
    dv = (Vector(target) - p).normalized()
    part(f"Flood_{tag}_Bracket", "Metal_Dark", lambda bm: [wall_box(bm, n, plane, a - 0.04, a + 0.04, y - 0.04, y + 0.04, 0.0, 0.3),
                                                          cyl(bm, tuple(p - dv * 0.16), tuple(p + dv * 0.02), 0.13, 0.15, 12)])
    part(f"Flood_{tag}_Lens", "Lamp_Emit", lambda bm: cyl(bm, tuple(p + dv * 0.02), tuple(p + dv * 0.03), 0.125, 0.125, 12))
    SPOTS_DAY.append((tuple(p + dv * 0.05), tuple(dv), watts, cone))


# ---------------------------------------------------------------- the shell: walls in three bands (mall plaster, sky mural, the vault), the coves
def wall_faces(b):
    """The faces of a greybox wall box that look into a room: [(room, n, plane, a0, a1, thickness range)]."""
    mn, mx = b["min"], b["max"]
    out = []
    for k, r in ROOMS.items():
        x0, x1, z0, z1 = r[:4]
        if mx[2] - mn[2] > mx[0] - mn[0]:                      # runs along z: a west or east wall
            if abs(mx[0] - x0) < 1e-3:
                out.append((k, "+x", x0, max(mn[2], z0), min(mx[2], z1), (mn[0], mx[0])))
            if abs(mn[0] - x1) < 1e-3:
                out.append((k, "-x", x1, max(mn[2], z0), min(mx[2], z1), (mn[0], mx[0])))
        else:
            if abs(mx[2] - z0) < 1e-3:
                out.append((k, "+z", z0, max(mn[0], x0), min(mx[0], x1), (mn[2], mx[2])))
            if abs(mn[2] - z1) < 1e-3:
                out.append((k, "-z", z1, max(mn[0], x0), min(mx[0], x1), (mn[2], mx[2])))
    return [f for f in out if f[4] - f[3] > 1e-3]


def mural_uv(n, corn, top):
    def fn(bm):
        uvl = bm.loops.layers.uv["UVMap"]
        tile = max(2.0, (top - corn) * 1.6)
        for f in bm.faces:
            for lp in f.loops:
                p = lp.vert.co
                gx, gy, gz = p.x, p.z, -p.y
                along = gz if n[1] == "x" else gx
                lp[uvl].uv = (along / tile, (gy - corn) / max(1e-6, top - corn) * 0.96 + 0.02)
    return fn


def build_walls():
    for b in GB.boxes:
        n = b["name"]
        if not b["col"] or "_Wall_" not in n:
            continue
        HANDLED.add(n)
        faces = wall_faces(b)
        mn, mx = list(b["min"]), list(b["max"])
        if not faces:                                           # (no face into a room: plain plaster)
            boxart(n, "Wall_Plaster", mn, mx)
            continue
        thick_ax = 0 if mx[2] - mn[2] > mx[0] - mn[0] else 2
        pieces = []
        if len(faces) == 2:                                     # a wall between two rooms: each half takes its room's bands
            mid = (mn[thick_ax] + mx[thick_ax]) / 2
            for f in faces:
                a, c = list(mn), list(mx)
                if f[1][0] == "+":
                    a[thick_ax] = mid
                else:
                    c[thick_ax] = mid
                pieces.append((f, a, c))
        else:
            pieces.append((faces[0], mn, mx))
        for (room, nn, plane, a0, a1, _), a, c in pieces:
            fy, h, corn, cv0 = ROOMS[room][4:8]
            bands = [("", "Wall_Plaster", a[1], min(c[1], fy + corn)), ("_Mural", "Sky_Mural", max(a[1], fy + corn), min(c[1], fy + cv0)),
                     ("_Vault", "Sky_Glow", max(a[1], fy + cv0), c[1])]
            for suf, mat, y0, y1 in bands:
                if y1 - y0 < 1e-3:
                    continue
                nm = f"{n}{'_' + room if len(pieces) == 2 else ''}{suf}"
                lo, hi = (a[0], y0, a[2]), (c[0], y1, c[2])
                if mat == "Sky_Mural":
                    part(nm, mat, lambda bm: cube(bm, lo, hi), keep_uv=False)
                    ob = bpy.data.objects[nm]
                    _remap(ob, mural_uv(nn, fy + corn, fy + cv0))
                else:
                    boxart(nm, mat, lo, hi)


def _remap(ob, fn):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    if not bm.loops.layers.uv.get("UVMap"):
        bm.loops.layers.uv.new("UVMap")
    fn(bm)
    bm.to_mesh(ob.data)
    bm.free()


def build_vault():
    """The ceilings (the painted sky, lit from behind) and, round each room, a cove that carries the sky down to the walls like a vault, with
    a white moulding at its foot and at the ceiling's edge."""
    for b in GB.boxes:
        if b["col"] and b["name"].endswith("_Ceiling"):
            solid_art(b, "Sky_Glow")
    for k, (x0, x1, z0, z1, fy, h, corn, cv0) in ROOMS.items():
        r = h - cv0
        if r < 0.05:
            continue
        nseg = 7
        rings = []
        for i in range(nseg + 1):
            th = math.pi / 2 * i / nseg
            d = r * (1 - math.cos(th))
            y = fy + cv0 + r * math.sin(th) - (0.004 if i == nseg else 0.0)
            rings.append([(x0 + d, y, z0 + d), (x1 - d, y, z0 + d), (x1 - d, y, z1 - d), (x0 + d, y, z1 - d), (x0 + d, y, z0 + d)])

        def cove(bm, rings=rings, r=r):
            uvl = bm.loops.layers.uv["UVMap"]
            vs = loft(bm, rings, closed=False)
            per = []
            for ring in rings:
                acc, u = [0.0], 0.0
                for p, q in zip(ring, ring[1:]):
                    u += math.hypot(q[0] - p[0], q[2] - p[2])
                    acc.append(u)
                per.append(acc)
            for f in bm.faces:
                for lp in f.loops:
                    for j, row in enumerate(vs):
                        if lp.vert in row:
                            i = row.index(lp.vert)
                            lp[uvl].uv = (per[j][i] / 6.0, j / nseg * r * math.pi / 2 / 6.0)
                            break
            bm.normal_update()
            c = B(((x0 + x1) / 2, fy + cv0, (z0 + z1) / 2))
            for f in bm.faces:
                if f.normal.dot(c - f.calc_center_median()) < 0:
                    f.normal_flip()
        part(f"decor_Sky_Cove_{k}", "Sky_Glow", cove, keep_uv=True, keep_normals=True, smooth=True)

        def mould(bm, y, d0, d1, inset=0.0):
            xa, xb, za, zb = x0 + inset, x1 - inset, z0 + inset, z1 - inset
            for (p0, p1) in (((xa, za), (xb, za + d1)), ((xa, zb - d1), (xb, zb)), ((xa, za), (xa + d1, zb)), ((xb - d1, za), (xb, zb))):
                cube(bm, (p0[0], y - 0.06, p0[1]), (p1[0], y + 0.06, p1[1]))
        part(f"decor_Vault_Moulding_{k}", "Trim_Paint", lambda bm: [mould(bm, fy + cv0, 0.0, 0.09), mould(bm, fy + h - 0.06, 0.0, 0.1, inset=r - 0.02)])


def build_wall_trim():
    """Along every wall face: terrazzo skirting at the floor, the cornice (a moulded ledge whose top hides the day's uplight trough) under the
    sky mural."""
    for b in GB.boxes:
        if not b["col"] or "_Wall_" not in b["name"]:
            continue
        for room, n, plane, a0, a1, _ in wall_faces(b):
            fy, h, corn, cv0 = ROOMS[room][4:8]
            y0, y1 = b["min"][1], b["max"][1]
            tag = f"{b['name']}_{room}"
            if y0 <= fy + 1e-3 and y1 > fy + 0.2:
                part(f"Skirting_{tag}", "Floor_Border", lambda bm: wall_box(bm, n, plane, a0, a1, fy, fy + 0.12, 0.0, 0.015))
            if y0 < fy + corn - 0.1 and y1 > fy + corn + 0.1:
                part(f"Cornice_{tag}", "Trim_Paint", lambda bm: [wall_box(bm, n, plane, a0, a1, fy + corn - 0.16, fy + corn, 0.0, 0.06),
                                                               wall_box(bm, n, plane, a0, a1, fy + corn, fy + corn + 0.06, 0.0, 0.14)])
                part(f"Trough_{tag}", "Lamp_Emit", lambda bm: quad(bm, mount(n, plane, a0, fy + corn + 0.061, 0.02), mount(n, plane, a1, fy + corn + 0.061, 0.02),
                                                                   mount(n, plane, a1, fy + corn + 0.061, 0.12), mount(n, plane, a0, fy + corn + 0.061, 0.12)))
                ob = bpy.data.objects[f"Trough_{tag}"]
                orient_faces(ob, (0, 1, 0))
                c = mount(n, plane, (a0 + a1) / 2, fy + corn + 0.09, 0.08)
                if a1 - a0 > 0.6:
                    AREAS_DAY.append((c, (NV[n][0] * 0.35, 1.0, NV[n][2] * 0.35), a1 - a0 - 0.1, 0.08, TROUGH_W * (a1 - a0)))


TROUGH_W = 30.0          # the uplight troughs on the cornice: watts a metre (the day set)


def floor_slab(b, mat, step=2.0, uv=None, name=None):
    """A floor box as art: its top cut into a grid (so the cull can drop the squares under things and the lightmap unwraps evenly) and its
    sides; no underside."""
    HANDLED.add(b["name"])
    mn, mx = b["min"], b["max"]

    def build(bm):
        xs = np.linspace(mn[0], mx[0], max(1, int(math.ceil((mx[0] - mn[0]) / step))) + 1)
        zs = np.linspace(mn[2], mx[2], max(1, int(math.ceil((mx[2] - mn[2]) / step))) + 1)
        for xa, xb in zip(xs, xs[1:]):
            for za, zb in zip(zs, zs[1:]):
                quad(bm, (xa, mx[1], zb), (xb, mx[1], zb), (xb, mx[1], za), (xa, mx[1], za))
        quad(bm, (mn[0], mn[1], mn[2]), (mx[0], mn[1], mn[2]), (mx[0], mx[1], mn[2]), (mn[0], mx[1], mn[2]))
        quad(bm, (mn[0], mn[1], mx[2]), (mn[0], mx[1], mx[2]), (mx[0], mx[1], mx[2]), (mx[0], mn[1], mx[2]))
        quad(bm, (mn[0], mn[1], mn[2]), (mn[0], mx[1], mn[2]), (mn[0], mx[1], mx[2]), (mn[0], mn[1], mx[2]))
        quad(bm, (mx[0], mn[1], mn[2]), (mx[0], mn[1], mx[2]), (mx[0], mx[1], mx[2]), (mx[0], mx[1], mn[2]))
        dedupe_inner(bm)
        bm.normal_update()
        c = B(((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2))
        for f in bm.faces:
            if f.normal.dot(f.calc_center_median() - c) < 0:
                f.normal_flip()
    ob = part(name or b["name"], mat, build, keep_normals=True)
    if uv:
        _remap(ob, uv)
    return ob


def border_strips(tag, x0, x1, z0, z1, y, w=0.5, mat="Floor_Border", gaps=()):
    """A dark terrazzo border (a decal 2 mm up) round the inside of a rectangle, in lengths of at most 4 m; `gaps`: (x0, x1, z0, z1) left out."""
    def ok(a0, a1, b0, b1):
        return not any(a0 < g[1] and a1 > g[0] and b0 < g[3] and b1 > g[2] for g in gaps)

    def build(bm):
        k = 0
        for (a0, a1, b0, b1) in ((x0, x1, z0, z0 + w), (x0, x1, z1 - w, z1), (x0, x0 + w, z0 + w, z1 - w), (x1 - w, x1, z0 + w, z1 - w)):
            along_x = (a1 - a0) >= (b1 - b0)
            L_ = (a1 - a0) if along_x else (b1 - b0)
            nseg = max(1, int(math.ceil(L_ / 4.0)))
            for i in range(nseg):
                if along_x:
                    p0, p1, q0, q1 = a0 + (a1 - a0) * i / nseg, a0 + (a1 - a0) * (i + 1) / nseg, b0, b1
                else:
                    p0, p1, q0, q1 = a0, a1, b0 + (b1 - b0) * i / nseg, b0 + (b1 - b0) * (i + 1) / nseg
                if ok(p0, p1, q0, q1):
                    flat_decal(bm, p0, p1, q0, q1, y + 0.002 + 0.0003 * (k % 2))
                    k += 1
    part(f"Border_{tag}", mat, build, keep_normals=True)


def dust_strips(tag, x0, x1, z0, z1, y, gaps=()):
    """Dust drifted along the foot of the walls (an alpha decal, the wings'), in 4 m lengths."""
    def build(bm):
        uvl = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
        k = 0
        for side in ("N", "S", "W", "E"):
            if side in "NS":
                z = z0 if side == "N" else z1
                xs = np.linspace(x0 + 0.05, x1 - 0.05, max(2, int((x1 - x0) / 4)) + 1)
                for xa, xb in zip(xs, xs[1:]):
                    if any(xa < g[1] and xb > g[0] and min(z, z + (0.9 if side == "N" else -0.9)) < g[3] and max(z, z + (0.9 if side == "N" else -0.9)) > g[2] for g in gaps):
                        continue
                    yy = y + 0.004 + 0.0003 * (k % 2)
                    zi = z + (0.9 if side == "N" else -0.9)
                    f = quad(bm, (xa, yy, z), (xb, yy, z), (xb, yy, zi), (xa, yy, zi))
                    for lp, (s, t) in zip(f.loops, ((xa / 4, 1), (xb / 4, 1), (xb / 4, 0), (xa / 4, 0))):
                        lp[uvl].uv = (s, t)
                    k += 1
            else:
                x = x0 if side == "W" else x1
                zs = np.linspace(z0 + 0.05, z1 - 0.05, max(2, int((z1 - z0) / 4)) + 1)
                for za, zb in zip(zs, zs[1:]):
                    xi = x + (0.9 if side == "W" else -0.9)
                    if any(min(x, xi) < g[1] and max(x, xi) > g[0] and za < g[3] and zb > g[2] for g in gaps):
                        continue
                    yy = y + 0.004 + 0.0003 * (k % 2)
                    f = quad(bm, (x, yy, za), (x, yy, zb), (xi, yy, zb), (xi, yy, za))
                    for lp, (s, t) in zip(f.loops, ((za / 4, 1), (zb / 4, 1), (zb / 4, 0), (za / 4, 0))):
                        lp[uvl].uv = (s, t)
                    k += 1
        bm.normal_update()
        for f in bm.faces:
            if f.normal.z < 0:
                f.normal_flip()
    part(f"Decal_Dust_{tag}", "Decal_Dust", build, keep_uv=True, keep_normals=True)


# ---------------------------------------------------------------- doors: casings on the room's side, EXIT over the way back to the wing
def door_geom(d):
    th = d["yaw"]
    run = (math.cos(th), -math.sin(th))
    w = d["props"]["width"]
    c = (d["hinge"][0] + run[0] * w / 2, d["hinge"][2] + run[1] * w / 2)
    room = room_of(*c)
    r = ROOMS[room]
    rc = ((r[0] + r[1]) / 2, (r[2] + r[3]) / 2)
    if abs(run[0]) > 0.5:                     # the leaf runs along x: a north or south wall
        n = "+z" if rc[1] > c[1] else "-z"
        plane, a = d["hinge"][2], c[0]
    else:
        n = "+x" if rc[0] > c[0] else "-x"
        plane, a = d["hinge"][0], c[1]
    return n, plane, a, d["hinge"][1], "sky hall" in d["props"].get("kind", "")


def build_door_surrounds():
    for d in GB.doors:
        n, plane, a, y, kit = door_geom(d)
        ow = KIT_W if kit else DOOR_W
        oh = KIT_H if kit else DOOR_H
        mat = "Trim_Paint"
        tag = d["name"].replace("DoorLeaf_", "")
        part(f"Casing_{tag}_L", mat, lambda bm: wall_box(bm, n, plane, a - ow / 2 - 0.1, a - ow / 2, y, y + oh + 0.1, 0.0, 0.04))
        part(f"Casing_{tag}_R", mat, lambda bm: wall_box(bm, n, plane, a + ow / 2, a + ow / 2 + 0.1, y, y + oh + 0.1, 0.0, 0.04))
        part(f"Casing_{tag}_Head", mat, lambda bm: wall_box(bm, n, plane, a - ow / 2 - 0.1, a + ow / 2 + 0.1, y + oh, y + oh + 0.12, 0.0, 0.045))
        if not kit:
            exit_sign(tag, n, plane, a, y + oh + 0.42)


def leaf_mesh(w, h, uvr, edge_uv):
    """A door leaf in its own frame (the wings'): x from the hinge along the leaf (0..w), y across (-0.025..0.025), z up; both faces show the
    picture; a lever each side."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    t = 0.025
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((w / 2, 0, h / 2)) @ Matrix.Diagonal((w, 2 * t, h, 1)))
    u0, v0, u1, v1 = uvr
    for f in bm.faces:
        f.normal_update()
        if abs(f.normal.y) > 0.9:
            for lp in f.loops:
                x, z = lp.vert.co.x, lp.vert.co.z
                s = x / w if f.normal.y < 0 else 1 - x / w
                lp[uvl].uv = (u0 + (u1 - u0) * s, v0 + (v1 - v0) * z / h)
        else:
            for lp in f.loops:
                lp[uvl].uv = edge_uv
    old = set(bm.faces)
    kx, kz = w - 0.09, 1.0
    for sgn in (-1, 1):
        bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=0.012, radius2=0.012, depth=0.12,
                              matrix=Matrix.Translation((kx - 0.05, sgn * (t + 0.04), kz)) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
        bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.01, radius2=0.01, depth=0.04,
                              matrix=Matrix.Translation((kx, sgn * (t + 0.02), kz)) @ Matrix.Rotation(math.pi / 2, 4, "X"))
    for f in bm.faces:
        if f not in old:
            for lp in f.loops:
                lp[uvl].uv = (DOOR_CELLS["house_red"] * 400 / 2048 + 0.18, 0.58)      # the brass knocker's colour
    return bm


def build_door_leaves():
    for d in GB.doors:
        p = d["props"]
        w, h = p["width"], p["height"]
        kind = "panel" if "sky hall" in p.get("kind", "") else "unmarked"
        uvr = door_uv(kind)
        bm = leaf_mesh(w, h, uvr, (uvr[0] + 0.002, 0.5))
        for f in bm.faces:
            f.smooth = False
        me = bpy.data.meshes.new(d["name"])
        bm.to_mesh(me)
        bm.free()
        me.materials.append(MATS["Door_Leaves"])
        ob = bpy.data.objects.new(d["name"], me)
        ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z")
        for k, v in p.items():
            ob[k] = v
        DOORS_C.objects.link(ob)


def build_layout():
    for b in GB.boxes:
        if b.get("zone") or not b["col"]:
            continue
        me = bpy.data.meshes.new("COL_" + b["name"])
        bm = bmesh.new()
        cube(bm, b["min"], b["max"])
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("COL_" + b["name"], me)
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


FALLBACK = {"wall": "Wall_Plaster", "mural": "Wall_Plaster", "floor": "Floor_Terrazzo", "marble": "Floor_Terrazzo", "stair": "Floor_Border",
            "furniture": "Bench_Wood", "counter": "Bench_Wood", "column": "Trim_Paint", "concrete": "Floor_Border", "sky": "Sky_Glow",
            "rail": "Metal_Steel", "shutter": "Shutter_Metal", "sign": "Trim_Paint", "padding": "Trim_Paint", "sheet": "Cloth_Sheet"}


def build_fallback():
    """Any greybox solid no builder dressed: its box, in a material of its kind (so every collider has art over it)."""
    left = [b for b in SOLIDS if b["name"] not in HANDLED]
    for b in left:
        solid_art(b, FALLBACK.get(b["mat"], "Trim_Paint"))
    if left:
        print("FALLBACK art for", [b["name"] for b in left])


def mannequins():
    return [e for e in GB.empties if e["name"].startswith("Spot_mannequin")]


# ---------------------------------------------------------------- furniture shared by the scenes
def bench(b, back):
    """A slatted park bench on its greybox box: cast ends, five seat slats at 0.45 m, a backrest on the `back` side ('+x', '-x', '+z', '-z')
    that stays inside the box's plan."""
    mn, mx = b["min"], b["max"]
    y0, y1 = mn[1], mx[1]
    along_x = (mx[0] - mn[0]) > (mx[2] - mn[2])
    with inside(b["name"]):
        def ends(bm):
            if along_x:
                for x in (mn[0] + 0.04, mx[0] - 0.1):
                    cube(bm, (x, y0, mn[2] + 0.02), (x + 0.06, y1 - 0.02, mx[2] - 0.02))
            else:
                for z in (mn[2] + 0.04, mx[2] - 0.1):
                    cube(bm, (mn[0] + 0.02, y0, z), (mx[0] - 0.02, y1 - 0.02, z + 0.06))
        part(f"{b['name']}_Ends", "Metal_Dark", ends)

        def slats(bm):
            for k in range(4):
                if along_x:
                    za = mn[2] + 0.03 + k * (mx[2] - mn[2] - 0.06) / 4
                    cube(bm, (mn[0], y1 - 0.04, za + 0.01), (mx[0], y1, za + (mx[2] - mn[2] - 0.06) / 4 - 0.01))
                else:
                    xa = mn[0] + 0.03 + k * (mx[0] - mn[0] - 0.06) / 4
                    cube(bm, (xa + 0.01, y1 - 0.04, mn[2]), (xa + (mx[0] - mn[0] - 0.06) / 4 - 0.01, y1, mx[2]))
            if back:                                                         # the backrest: three slats rising from the back edge
                for k in range(3):
                    ya, yb = y1 + 0.08 + k * 0.13, y1 + 0.18 + k * 0.13
                    if back == "+z":
                        cube(bm, (mn[0], ya, mx[2] - 0.05), (mx[0], yb, mx[2]))
                    elif back == "-z":
                        cube(bm, (mn[0], ya, mn[2]), (mx[0], yb, mn[2] + 0.05))
                    elif back == "+x":
                        cube(bm, (mx[0] - 0.05, ya, mn[2]), (mx[0], yb, mx[2]))
                    else:
                        cube(bm, (mn[0], ya, mn[2]), (mn[0] + 0.05, yb, mx[2]))
        part(b["name"], "Bench_Wood", slats)
        if back:
            def posts(bm):
                for t in (0.12, 0.88):
                    if back in ("+z", "-z"):
                        x = mn[0] + (mx[0] - mn[0]) * t
                        z = mx[2] - 0.05 if back == "+z" else mn[2]
                        cube(bm, (x - 0.03, y1 - 0.04, z - (0.0 if back == "-z" else 0.0)), (x + 0.03, y1 + 0.47, z + 0.05))
                    else:
                        z = mn[2] + (mx[2] - mn[2]) * t
                        x = mx[0] - 0.05 if back == "+x" else mn[0]
                        cube(bm, (x, y1 - 0.04, z - 0.03), (x + 0.05, y1 + 0.47, z + 0.03))
            part(f"{b['name']}_Posts", "Metal_Dark", posts)


def plastic_tree(tag, cx, cz, y0, y_top, r, rng, mat="Plant_Plastic"):
    """A faded plastic tree (decor: passable): a trunk and a canopy of too-round blobs."""
    part(f"decor_{tag}_Trunk", "Bench_Wood", lambda bm: [cyl(bm, (cx, y0, cz), (cx + 0.04, y_top - r * 0.8, cz - 0.03), 0.07, 0.045, 10),
                                                       cyl(bm, (cx + 0.02, y_top - r * 1.3, cz), (cx + 0.45, y_top - r * 0.6, cz + 0.2), 0.035, 0.02, 6),
                                                       cyl(bm, (cx, y_top - r * 1.1, cz), (cx - 0.4, y_top - r * 0.5, cz - 0.25), 0.035, 0.02, 6)], smooth=True)

    def blobs(bm):
        for k in range(7):
            a = 2 * math.pi * k / 7 + rng.uniform(-0.3, 0.3)
            rr = r * (0.55 if k else 0.0)
            sphere(bm, (cx + math.cos(a) * rr, y_top - r * 0.55 + rng.uniform(-0.2, 0.25) * r, cz + math.sin(a) * rr), r * rng.uniform(0.45, 0.6), 12)
        sphere(bm, (cx, y_top - r * 0.35, cz), r * 0.6, 12)
    part(f"decor_{tag}_Canopy", mat, blobs, smooth=True, sharp_deg=80)


def planter(b, rng, tree=True, fern=False):
    mn, mx = b["min"], b["max"]
    with inside(b["name"]):
        part(b["name"], "Floor_Border", lambda bm: cube(bm, mn, (mx[0], mx[1] - 0.04, mx[2])))
        part(f"{b['name']}_Rim", "Trim_Paint", lambda bm: [cube(bm, (mn[0], mx[1] - 0.04, mn[2]), (mx[0], mx[1], mn[2] + 0.06)),
                                                           cube(bm, (mn[0], mx[1] - 0.04, mx[2] - 0.06), (mx[0], mx[1], mx[2])),
                                                           cube(bm, (mn[0], mx[1] - 0.04, mn[2] + 0.06), (mn[0] + 0.06, mx[1], mx[2] - 0.06)),
                                                           cube(bm, (mx[0] - 0.06, mx[1] - 0.04, mn[2] + 0.06), (mx[0], mx[1], mx[2] - 0.06))])
        part(f"{b['name']}_Soil", "Bench_Wood", lambda bm: cube(bm, (mn[0] + 0.06, mx[1] - 0.07, mn[2] + 0.06), (mx[0] - 0.06, mx[1] - 0.05, mx[2] - 0.06)), tile=0.3)
    cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
    if fern:
        def fronds(bm):
            for k in range(11):
                a = 2 * math.pi * k / 11
                p = (cx + math.cos(a) * 0.35, mx[1] + 0.32, cz + math.sin(a) * 0.3)
                sphere(bm, p, 0.32, 10, scale=(1.0, 0.25, 0.45))
        part(f"decor_{b['name']}_Fern", "Plant_Plastic", fronds, smooth=True, sharp_deg=80)


# ================================================================ scene_2909: the sky court
def scene_2909():
    rng = np.random.default_rng(2909)
    x0, x1, z0, z1 = -12.0, 12.0, -12.0, 12.0
    for n in ("Floor_N", "Floor_S", "Floor_W", "Floor_E"):
        floor_slab(BOXL[n], "Floor_Terrazzo")
    border_strips("walls", x0, x1, z0, z1, 0.0, w=0.45, gaps=[(-0.8, 0.8, z1 - 0.6, z1), (-0.8, 0.8, z0, z0 + 0.6)])
    border_strips("court_lip", -6.35, 6.35, -6.35, 6.35, 0.0, w=0.35)
    dust_strips("walls", x0, x1, z0, z1, 0.0, gaps=[(-1.0, 1.0, z1 - 1.0, z1), (-1.0, 1.0, z0, z0 + 1.0)])
    for b in GB.boxes:
        if b["name"].startswith("Step_court"):
            solid_art(b, "Floor_Border")
    cf = BOXL["Court_Floor"]
    ri = cf["max"][0]
    floor_slab(cf, "Court_Mosaic", step=ri * 2 / 4, uv=lambda bm: [setattr(lp[bm.loops.layers.uv["UVMap"]], "uv", ((lp.vert.co.x + ri) / (2 * ri), (lp.vert.co.y + ri) / (2 * ri)))
                                                                  for f in bm.faces for lp in f.loops])
    # the bandstand: a timber deck with a white skirt, four cast-iron columns, a striped canvas roof with a fringe, globe lamps, a rail
    bs = BOXL["Bandstand"]
    solid_art(bs, "Bench_Wood")
    by = bs["max"][1]
    part("decor_Bandstand_Skirt", "Trim_Paint", lambda bm: [cube(bm, (bs["min"][0] - 0.02, bs["min"][1], bs["min"][2] - 0.02), (bs["max"][0] + 0.02, by - 0.02, bs["min"][2])),
                                                           cube(bm, (bs["min"][0] - 0.02, bs["min"][1], bs["max"][2]), (bs["max"][0] + 0.02, by - 0.02, bs["max"][2] + 0.02)),
                                                           cube(bm, (bs["min"][0] - 0.02, bs["min"][1], bs["min"][2]), (bs["min"][0], by - 0.02, bs["max"][2])),
                                                           cube(bm, (bs["max"][0], bs["min"][1], bs["min"][2]), (bs["max"][0] + 0.02, by - 0.02, bs["max"][2]))])
    for b in GB.boxes:
        if b["name"].startswith("Bandstand_Post"):
            mn, mx = b["min"], b["max"]
            cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
            HANDLED.add(b["name"])
            part(b["name"], "Trim_Paint", lambda bm: [cyl(bm, (cx, mn[1], cz), (cx, mn[1] + 0.18, cz), 0.09, 0.08, 12), cyl(bm, (cx, mn[1] + 0.18, cz), (cx, mx[1] - 0.15, cz), 0.06, 0.05, 12),
                                                      cyl(bm, (cx, mx[1] - 0.15, cz), (cx, mx[1], cz), 0.05, 0.09, 12)], smooth=True)
    rf = 2.35

    def roof(bm):
        y_e, y_a = 2.05, 3.05
        cube(bm, (-rf, 1.8, -rf), (rf, y_e, rf), skip=("+y",))
        for (a, b_, c) in (((-rf, y_e, -rf), (rf, y_e, -rf), (0, y_a, 0)), ((rf, y_e, -rf), (rf, y_e, rf), (0, y_a, 0)),
                           ((rf, y_e, rf), (-rf, y_e, rf), (0, y_a, 0)), ((-rf, y_e, rf), (-rf, y_e, -rf), (0, y_a, 0))):
            bm.faces.new([bm.verts.new(B(p)) for p in (a, b_, c)])
    ob = part("decor_Bandstand_Roof", "Awning_Stripe", roof, keep_normals=True)
    orient_faces(ob, (0, 1, 0))
    _remap(ob, lambda bm: [setattr(lp[bm.loops.layers.uv["UVMap"]], "uv", ((math.atan2(-lp.vert.co.y, lp.vert.co.x) / (2 * math.pi)) * 8, 0.27 + 0.2 * (lp.vert.co.z - 1.8)))
                           for f in bm.faces for lp in f.loops])

    def fringe(bm):
        for k in range(48):
            t = k / 48
            for side in range(4):
                p = [(-rf + 2 * rf * t, -rf), (rf, -rf + 2 * rf * t), (rf - 2 * rf * t, rf), (-rf, rf - 2 * rf * t)][side]
                q = [(1, 0), (0, 1), (-1, 0), (0, -1)][side]
                w = 2 * rf / 48 * 0.45
                quad(bm, (p[0], 1.8, p[1]), (p[0] + q[0] * w, 1.8, p[1] + q[1] * w), (p[0] + q[0] * w * 0.5, 1.62, p[1] + q[1] * w * 0.5), (p[0], 1.8, p[1]))
    ob = part("decor_Bandstand_Fringe", "Trim_Paint", fringe, keep_normals=True)
    part("decor_Bandstand_Finial", "Trim_Paint", lambda bm: [cyl(bm, (0, 3.0, 0), (0, 3.35, 0), 0.03, 0.02, 8), sphere(bm, (0, 3.4, 0), 0.08, 10)], smooth=True)

    def rail(bm, a, b_):
        if True:
            cyl(bm, (a[0], by + 0.75, a[1]), (b_[0], by + 0.75, b_[1]), 0.02, 0.02, 6, cap=False)
            L_ = math.hypot(b_[0] - a[0], b_[1] - a[1])
            for k in range(int(L_ / 0.3) + 1):
                t = k / int(L_ / 0.3)
                cyl(bm, (a[0] + (b_[0] - a[0]) * t, by, a[1] + (b_[1] - a[1]) * t), (a[0] + (b_[0] - a[0]) * t, by + 0.75, a[1] + (b_[1] - a[1]) * t), 0.01, 0.01, 5, cap=False)
    e = 1.95
    for k, (a, b_) in enumerate((((-e, -e), (e, -e)), ((-e, -e), (-e, e)), ((e, -e), (e, e)))):
        part(f"decor_Bandstand_Rail_{k}", "Metal_Dark", lambda bm: rail(bm, a, b_))
    globes = [(sx * 1.55, 1.55, sz * 1.55) for sx in (-1, 1) for sz in (-1, 1)]
    part("decor_Bandstand_Globes", "Lamp_Emit", lambda bm: [sphere(bm, p, 0.11, 12) for p in globes], smooth=True)
    part("decor_Bandstand_GlobeRods", "Metal_Dark", lambda bm: [cyl(bm, (p[0], p[1] + 0.1, p[2]), (p[0], 1.8, p[2]), 0.008, 0.008, 5) for p in globes])
    POINTS_DAY.extend((p, 22.0, 0.1) for p in globes)
    part("decor_MusicStands", "Metal_Dark", lambda bm: [[cyl(bm, (x, by, z), (x, by + 1.05, z), 0.008, 0.008, 5), cube(bm, (x - 0.2, by + 1.0, z - 0.01), (x + 0.2, by + 1.25, z + 0.01))]
                                                       for x, z in ((-1.0, 0.6), (1.0, 0.6), (0.0, 1.2))])
    # planters with plastic trees; the benches round the edge
    for b in GB.boxes:
        if b["name"].startswith("Planter"):
            planter(b, rng)
            cx, cz = (b["min"][0] + b["max"][0]) / 2, (b["min"][2] + b["max"][2]) / 2
            plastic_tree(b["name"], cx, cz, b["max"][1] - 0.07, 4.4, 1.25, rng)
    for b in GB.boxes:
        if b["name"].startswith("Bench"):
            cx, cz = (b["min"][0] + b["max"][0]) / 2, (b["min"][2] + b["max"][2]) / 2
            back = ("+z" if cz > 0 else "-z") if abs(cz) > abs(cx) else ("+x" if cx > 0 else "-x")
            bench(b, back)
    # the walls: shuttered fronts on three sides, arched windows painted with sky on the north wall, the way out
    for nm, n, plane, a, key in (("W0", "+x", x0, -5.0, "w0"), ("W1", "+x", x0, 5.0, "w1"), ("E0", "-x", x1, -5.0, "e0"), ("E1", "-x", x1, 5.0, "e1"),
                                 ("S0", "-z", z1, -7.0, "s0"), ("S1", "-z", z1, 7.0, "s1")):
        shutter_flat(nm, n, plane, a, 4.0, 0.0, 2.9, key)
    for k, a in enumerate((-6.5, 6.5)):
        n, plane = "+z", z0
        wall_panel(f"SkyWindow_{k}", "Poster_Art", n, plane, a, 2.15, 0.01, 2.2, 2.6, cell_uv(8 + k))

        def frame(bm, a=a):
            wall_box(bm, n, plane, a - 1.25, a - 1.1, 0.7, 3.45, 0.0, 0.04)
            wall_box(bm, n, plane, a + 1.1, a + 1.25, 0.7, 3.45, 0.0, 0.04)
            wall_box(bm, n, plane, a - 1.3, a + 1.3, 0.6, 0.85, 0.0, 0.045)
            wall_box(bm, n, plane, a - 1.25, a + 1.25, 3.45, 3.6, 0.0, 0.04)
            wall_box(bm, n, plane, a - 0.04, a + 0.04, 0.85, 3.45, 0.0, 0.03)
            wall_box(bm, n, plane, a - 1.1, a + 1.1, 2.1, 2.16, 0.0, 0.03)
        part(f"SkyWindow_{k}_Frame", "Trim_Paint", frame)
    for k, (a, cell) in enumerate(((-2.8, 1), (2.8, 3))):
        part(f"PosterFrame_N{k}", "Metal_Dark", lambda bm: wall_box(bm, "+z", z0, a - 0.5, a + 0.5, 0.75, 2.35, 0.0, 0.03))
        wall_panel(f"Poster_N{k}", "Poster_Art", "+z", z0, a, 1.55, 0.0305, 0.88, 1.4, cell_uv(cell))
    part("SignBoard_court", "Metal_Dark", lambda bm: wall_box(bm, "+z", z0, -2.0, 2.0, 2.55, 3.15, 0.0, 0.03))
    wall_panel("Sign_court", "Sign_Paint", "+z", z0, 0.0, 2.85, 0.0305, 3.9, 0.5, sign_uv("court"))
    part("Directory_Frame", "Metal_Dark", lambda bm: wall_box(bm, "-z", z1, -3.25, -1.95, 0.85, 2.75, 0.0, 0.04))
    wall_panel("Directory_Face", "Poster_Art", "-z", z1, -2.6, 1.8, 0.0405, 1.2, 1.8, cell_uv(7))
    wall_panel("Notice_S0", "Poster_Art", "-z", z1, 2.6, 1.55, 0.004, 0.5, 0.75, cell_uv(0))
    wall_panel("Notice_S1", "Poster_Art", "-z", z1, 3.4, 1.5, 0.004, 0.5, 0.75, cell_uv(2))
    wall_panel("Notice_W", "Poster_Art", "+x", x0, 0.0, 1.55, 0.004, 0.55, 0.55, cell_uv(11))
    wall_panel("Notice_E", "Poster_Art", "-x", x1, 0.0, 1.55, 0.004, 0.55, 0.55, cell_uv(10))
    # light: floods on the corners above the cornice (day), the emergency fittings (night)
    for k, (n, plane, a) in enumerate((("+x", x0, -10.5), ("+x", x0, 10.5), ("-x", x1, -10.5), ("-x", x1, 10.5))):
        flood(f"C{k}", n, plane, a, 5.6, (0.0, 0.0, 0.0), 900.0, 50.0)
    for k, (n, plane, a) in enumerate((("+x", x0, 0.0), ("-x", x1, 0.0), ("-z", z1, -4.5), ("-z", z1, 4.5), ("+z", z0, -3.6), ("+z", z0, 3.6))):
        emergency(f"E{k}", n, plane, a, 3.5)


# ================================================================ scene_3012: the painted-sky street
FRONT_MATS = ["Facade_Ochre", "Facade_Rose", "Facade_Mint", "Facade_Blue"]


def house_front(b, side, k):
    """One house front of the indoor street: stucco in its colour, quoins, a plinth, a string course and a cornice; a shop window under its
    awning, a cottage window under its balcony, sash windows above (one shows sky inside the house), the door that does not open, the fascia
    board with the shop's name."""
    mn, mx = b["min"], b["max"]
    xa, hh = mn[0], mx[1]
    n = "+z" if side == "N" else "-z"
    plane = mx[2] if side == "N" else mn[2]
    mat = FRONT_MATS[(k + (1 if side == "S" else 0) * 2) % 4]
    tag = f"{side}{k + 1}"
    solid_art(b, mat, tile=2.0)
    part(f"Quoins_{tag}", "Trim_Paint", lambda bm: [wall_box(bm, n, plane, xa + 0.02, xa + 0.3, 0.45, hh - 0.3, 0.0, 0.03),
                                                    wall_box(bm, n, plane, xa + 7.7, xa + 7.98, 0.45, hh - 0.3, 0.0, 0.03)])
    part(f"Plinth_{tag}", "Floor_Border", lambda bm: wall_box(bm, n, plane, xa, xa + 8.0, 0.0, 0.45, 0.0, 0.04))
    part(f"String_{tag}", "Trim_Paint", lambda bm: [wall_box(bm, n, plane, xa, xa + 8.0, 3.3, 3.42, 0.0, 0.08), wall_box(bm, n, plane, xa, xa + 8.0, hh - 0.32, hh, 0.0, 0.16),
                                                    wall_box(bm, n, plane, xa, xa + 8.0, hh - 0.42, hh - 0.32, 0.0, 0.07)])
    # the shop window (x +5.2..+7.2) under the awning, its display behind glass, a stall riser; the fascia and the sign above
    a = xa + 6.2
    wall_panel(f"Display_{tag}", "Shop_Display", n, plane, a, 1.45, 0.004, 1.9, 1.75, cell_uv(k + (4 if side == "S" else 0)))
    wall_panel(f"Glass_{tag}", "Glass_Clear", n, plane, a, 1.45, 0.025, 1.9, 1.75)
    part(f"ShopFrame_{tag}", "Trim_Paint", lambda bm: [wall_box(bm, n, plane, a - 1.08, a - 0.95, 0.45, 2.45, 0.0, 0.04), wall_box(bm, n, plane, a + 0.95, a + 1.08, 0.45, 2.45, 0.0, 0.04),
                                                       wall_box(bm, n, plane, a - 1.08, a + 1.08, 0.45, 0.58, 0.0, 0.045), wall_box(bm, n, plane, a - 1.08, a + 1.08, 2.32, 2.45, 0.0, 0.04),
                                                       wall_box(bm, n, plane, a - 0.02, a + 0.02, 0.58, 2.32, 0.0, 0.03)])
    part(f"SignBoard_{tag}", "Metal_Dark", lambda bm: wall_box(bm, n, plane, xa + 5.0, xa + 7.4, 2.78, 3.26, 0.0, 0.04))
    wall_panel(f"Sign_{tag}", "Sign_Paint", n, plane, xa + 6.2, 3.02, 0.0405, 2.3, 0.4, sign_uv(tag))
    # the cottage window under the balcony (x +1..+3)
    c = xa + 2.0
    wall_panel(f"LowWindow_{tag}", "Window_Paint", n, plane, c, 1.5, 0.01, 1.5, 1.4, (0.25 + 0.0005, 0, 0.5 - 0.0005, 1))
    part(f"LowWindowFrame_{tag}", "Trim_Paint", lambda bm: [wall_box(bm, n, plane, c - 0.85, c + 0.85, 0.7, 0.8, 0.0, 0.045), wall_box(bm, n, plane, c - 0.85, c - 0.75, 0.8, 2.2, 0.0, 0.035),
                                                            wall_box(bm, n, plane, c + 0.75, c + 0.85, 0.8, 2.2, 0.0, 0.035), wall_box(bm, n, plane, c - 0.85, c + 0.85, 2.2, 2.32, 0.0, 0.035)])
    # the upper windows: first floor (a French window behind the balcony, two sashes), and an attic row on the tall fronts
    rows = [(3.6, 4.9)] + ([(5.35, 6.3)] if hh >= 6.4 else [])
    wins = []
    for (wy0, wy1) in rows:
        for (wa, wb) in ((xa + 1.3, xa + 2.7), (xa + 3.45, xa + 4.55), (xa + 5.6, xa + 6.9)):
            wins.append((wa, wb, wy0, wy1))
    hsh = (k * 7 + (3 if side == "S" else 0)) % 5
    for i, (wa, wb, wy0, wy1) in enumerate(wins):
        cell = 0 if (i + hsh) % 5 == 0 else (1 + (i + k) % 3)
        wall_panel(f"Window_{tag}_{i}", "Window_Paint", n, plane, (wa + wb) / 2, (wy0 + wy1) / 2, 0.01, wb - wa, wy1 - wy0, (cell * 0.25 + 0.0005, 0, (cell + 1) * 0.25 - 0.0005, 1))
    part(f"WindowFrames_{tag}", "Trim_Paint", lambda bm: [[wall_box(bm, n, plane, wa - 0.1, wb + 0.1, wy0 - 0.1, wy0, 0.0, 0.06), wall_box(bm, n, plane, wa - 0.08, wb + 0.08, wy1, wy1 + 0.14, 0.0, 0.05),
                                                           wall_box(bm, n, plane, wa - 0.08, wa, wy0, wy1, 0.0, 0.035), wall_box(bm, n, plane, wb, wb + 0.08, wy0, wy1, 0.0, 0.035)]
                                                          for wa, wb, wy0, wy1 in wins])
    # the balcony and the awning over the shop (decor: overhead)
    bz0, bz1 = (plane, plane + 0.8) if side == "N" else (plane - 0.8, plane)
    zo = bz1 if side == "N" else bz0
    part(f"decor_Balcony_{tag}", "Trim_Paint", lambda bm: [cube(bm, (xa + 1.0, 3.0, bz0), (xa + 3.0, 3.15, bz1)),
                                                          cube(bm, (xa + 1.1, 2.85, bz0), (xa + 1.25, 3.0, (bz0 + bz1) / 2 + (0.2 if side == "N" else -0.2))),
                                                          cube(bm, (xa + 2.75, 2.85, bz0), (xa + 2.9, 3.0, (bz0 + bz1) / 2 + (0.2 if side == "N" else -0.2)))])

    def railing(bm):
        for (p, q) in (((xa + 1.05, zo), (xa + 2.95, zo)), ((xa + 1.05, bz0 if side == "S" else bz1), (xa + 1.05, plane)), ((xa + 2.95, zo), (xa + 2.95, plane))):
            cyl(bm, (p[0], 4.05, p[1]), (q[0], 4.05, q[1]), 0.02, 0.02, 6, cap=False)
            L_ = math.hypot(q[0] - p[0], q[1] - p[1])
            m_ = max(1, int(L_ / 0.14))
            for j in range(m_ + 1):
                t = j / m_
                cyl(bm, (p[0] + (q[0] - p[0]) * t, 3.15, p[1] + (q[1] - p[1]) * t), (p[0] + (q[0] - p[0]) * t, 4.05, p[1] + (q[1] - p[1]) * t), 0.008, 0.008, 4, cap=False)
    part(f"decor_BalconyRail_{tag}", "Metal_Dark", railing)
    s_ = 1 if side == "N" else -1
    row = (k + (2 if side == "S" else 0)) % 4

    def awning(bm):
        uvl = bm.loops.layers.uv["UVMap"]
        v0, v1 = 1 - (row + 1) * 0.25 + 0.01, 1 - row * 0.25 - 0.01
        pts = [(xa + 5.0, 3.05, plane), (xa + 7.4, 3.05, plane), (xa + 7.4, 2.55, plane + s_ * 0.85), (xa + 5.0, 2.55, plane + s_ * 0.85)]
        f = quad(bm, *pts)
        for lp, (u, v) in zip(f.loops, ((0, v1), (2.4 / 0.75, v1), (2.4 / 0.75, v0 + 0.06), (0, v0 + 0.06))):
            lp[uvl].uv = (u, v)
        f = quad(bm, (xa + 5.0, 2.55, plane + s_ * 0.85), (xa + 7.4, 2.55, plane + s_ * 0.85), (xa + 7.4, 2.35, plane + s_ * 0.86), (xa + 5.0, 2.35, plane + s_ * 0.86))
        for lp, (u, v) in zip(f.loops, ((0, v0 + 0.06), (2.4 / 0.75, v0 + 0.06), (2.4 / 0.75, v0), (0, v0))):
            lp[uvl].uv = (u, v)
        for xx in (xa + 5.0, xa + 7.4):
            f = bm.faces.new([bm.verts.new(B(p)) for p in ((xx, 3.05, plane), (xx, 2.55, plane + s_ * 0.85), (xx, 2.55, plane))])
            for lp in f.loops:
                lp[uvl].uv = (0.1, v0 + 0.1)
    part(f"decor_Awning_{tag}", "Awning_Stripe", awning, keep_uv=True, keep_normals=True)
    part(f"decor_AwningArms_{tag}", "Metal_Dark", lambda bm: [cyl(bm, (xx, 2.7, plane), (xx, 2.58, plane + s_ * 0.8), 0.012, 0.012, 5) for xx in (xa + 5.1, xa + 7.3)])
    for b2 in GB.boxes:                                                   # the door that does not open (the greybox's box)
        if b2["name"] == f"Front_{tag}_Door":
            dm, dx = b2["min"], b2["max"]
            kind = ("house_green", "house_red", "house_blue")[(k + (1 if side == "S" else 0)) % 3]
            u0, v0_, u1, v1_ = door_uv(kind)
            HANDLED.add(b2["name"])

            def door(bm):
                uvl = bm.loops.layers.uv["UVMap"]
                cube(bm, dm, dx)
                for f in bm.faces:
                    f.normal_update()
                    for lp in f.loops:
                        p = lp.vert.co
                        gx, gy = p.x, p.z
                        lp[uvl].uv = (u0 + (u1 - u0) * (gx - dm[0]) / (dx[0] - dm[0]), v0_ + (v1_ - v0_) * gy / dx[1]) if abs(f.normal.y) > 0.9 else (u0 + 0.01, 0.5)
            part(b2["name"], "Door_Leaves", door, keep_uv=True)
            part(f"DoorCase_{tag}", "Trim_Paint", lambda bm: [wall_box(bm, n, plane, dm[0] - 0.14, dm[0] - 0.02, 0.0, 2.55, 0.0, 0.045), wall_box(bm, n, plane, dx[0] + 0.02, dx[0] + 0.14, 0.0, 2.55, 0.0, 0.045),
                                                              wall_box(bm, n, plane, dm[0] - 0.18, dx[0] + 0.18, 2.42, 2.6, 0.0, 0.045)])
    part(f"Doorstep_{tag}", "Floor_Border", lambda bm: wall_box(bm, n, plane, xa + 3.3, xa + 4.7, 0.0, 0.06, 0.0, 0.045))


def scene_3012():
    rng = np.random.default_rng(3012)
    x0, x1, z0, z1 = -16.0, 16.0, -6.0, 6.0
    floor_slab(BOXL["Street_Floor"], "Floor_Cobble")
    part("Pavement_N", "Floor_Pave", lambda bm: [flat_decal(bm, xa, xb, -5.4, -3.95, 0.003 + 0.0003 * (i % 2)) for i, (xa, xb) in enumerate(zip(np.linspace(x0, x1, 9), np.linspace(x0, x1, 9)[1:]))], keep_normals=True)
    part("Pavement_S", "Floor_Pave", lambda bm: [flat_decal(bm, xa, xb, 3.95, 5.4, 0.003 + 0.0003 * (i % 2)) for i, (xa, xb) in enumerate(zip(np.linspace(x0, x1, 9), np.linspace(x0, x1, 9)[1:]))], keep_normals=True)
    part("Kerb", "Floor_Border", lambda bm: [flat_decal(bm, xa, xb, za, zb, 0.004) for xa, xb in zip(np.linspace(x0, x1, 9), np.linspace(x0, x1, 9)[1:])
                                             for za, zb in ((-3.95, -3.75), (3.75, 3.95))], keep_normals=True)
    part("Threshold", "Floor_Terrazzo", lambda bm: [flat_decal(bm, x0, x0 + 2.4, -1.4, 1.4, 0.005), flat_decal(bm, x1 - 2.4, x1, -4.0, -2.0, 0.005), flat_decal(bm, x1 - 2.4, x1, 2.0, 4.0, 0.005)],
         keep_normals=True)
    for side in ("N", "S"):
        for k in range(4):
            house_front(BOXL[f"Front_{side}{k + 1}"], side, k)
    # the street lamps on the greybox's posts; the lanterns overhead
    for b in GB.boxes:
        if b["name"].startswith("Lamp_Post"):
            mn, mx = b["min"], b["max"]
            cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
            HANDLED.add(b["name"])
            part(b["name"], "Metal_Dark", lambda bm: [cyl(bm, (cx, 0.0, cz), (cx, 0.12, cz), 0.13, 0.12, 12), cyl(bm, (cx, 0.12, cz), (cx, 0.55, cz), 0.1, 0.075, 12),
                                                      cyl(bm, (cx, 0.55, cz), (cx, mx[1] - 0.1, cz), 0.05, 0.045, 10), cyl(bm, (cx, mx[1] - 0.1, cz), (cx, mx[1], cz), 0.06, 0.08, 10)], smooth=True)
            part(f"decor_{b['name']}_Lantern", "Metal_Dark", lambda bm: [cube(bm, (cx - 0.17, 3.6, cz - 0.17), (cx + 0.17, 3.66, cz + 0.17)),
                                                                         cyl(bm, (cx, 4.08, cz), (cx, 4.3, cz), 0.21, 0.04, 4), cyl(bm, (cx, 4.3, cz), (cx, 4.42, cz), 0.025, 0.01, 6),
                                                                         [cube(bm, (cx + sx * 0.15 - 0.012, 3.66, cz + sz * 0.15 - 0.012), (cx + sx * 0.15 + 0.012, 4.08, cz + sz * 0.15 + 0.012)) for sx in (-1, 1) for sz in (-1, 1)]])
            part(f"decor_{b['name']}_Glass", "Lamp_Emit", lambda bm: cube(bm, (cx - 0.135, 3.66, cz - 0.135), (cx + 0.135, 4.06, cz + 0.135)))
            POINTS_DAY.append(((cx, 3.86, cz), 55.0, 0.12))
    # the cafe tables under their sheets, the bistro chairs
    for b in GB.boxes:
        if b["name"].startswith("Sheeted_Cafe_Table"):
            mn, mx = b["min"], b["max"]
            HANDLED.add(b["name"])
            part(b["name"], "Cloth_Sheet", lambda bm: drape_box(bm, mn[0] + 0.02, mx[0] - 0.02, mn[2] + 0.02, mx[2] - 0.02, mx[1], rng, hem=(0.08, 0.3)), smooth=True, keep_normals=True)
            cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
            part(f"{b['name']}_Foot", "Metal_Dark", lambda bm: cyl(bm, (cx, 0.0, cz), (cx, 0.03, cz), 0.25, 0.25, 16))
        if b["name"].startswith("Cafe_Chair"):
            mn, mx = b["min"], b["max"]
            cx, cz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
            with inside(b["name"]):
                part(b["name"], "Metal_Dark", lambda bm: [cyl(bm, (cx, 0.41, cz), (cx, 0.45, cz), 0.2, 0.2, 16)] +
                     [cyl(bm, (cx + sx * 0.15, 0.0, cz + sz * 0.15), (cx + sx * 0.13, 0.41, cz + sz * 0.13), 0.012, 0.012, 5) for sx in (-1, 1) for sz in (-1, 1)] +
                     [cyl(bm, (mx[0] - 0.03, 0.45, cz + s * 0.17), (mx[0] - 0.03, 0.85, cz + s * 0.15), 0.012, 0.012, 5) for s in (-1, 1)] +
                     [cyl(bm, (mx[0] - 0.03, 0.85, cz - 0.15), (mx[0] - 0.03, 0.85, cz + 0.15), 0.014, 0.014, 6), cyl(bm, (mx[0] - 0.03, 0.7, cz - 0.16), (mx[0] - 0.03, 0.7, cz + 0.16), 0.01, 0.01, 6)])
                part(f"{b['name']}_Seat", "Bench_Wood", lambda bm: cyl(bm, (cx, 0.445, cz), (cx, 0.455, cz), 0.19, 0.19, 16))
    # the arch at the east end, between the two sky-hall doors, and the street's name by the way in
    ab = BOXL["decor_Arch"]

    def arch(bm):
        nseg = 16
        ring_o, ring_i = [], []
        for i in range(nseg + 1):
            t = i / nseg
            z = -4.2 + 8.4 * t
            y = 2.6 + 1.0 * math.sin(math.pi * t)
            ring_o.append((z, y + 0.3))
            ring_i.append((z, y))
        for (za, ya), (zb, yb), (zc, yc), (zd, yd) in zip(ring_i, ring_i[1:], ring_o[1:], ring_o):
            for xx in (ab["min"][0], ab["max"][0] - 0.005):
                quad(bm, (xx, ya, za), (xx, yb, zb), (xx, yc, zc), (xx, yd, zd))
            quad(bm, (ab["min"][0], ya, za), (ab["max"][0], ya, za), (ab["max"][0], yb, zb), (ab["min"][0], yb, zb))
            quad(bm, (ab["min"][0], yd, zd), (ab["min"][0], yc, zc), (ab["max"][0], yc, zc), (ab["max"][0], yd, zd))
    ob = part("decor_Arch", "Trim_Paint", arch, keep_normals=True)
    for k, za in enumerate((-4.55, 4.2)):
        part(f"Arch_Pier_{k}", "Trim_Paint", lambda bm: wall_box(bm, "-x", x1, za, za + 0.35, 0.0, 2.6, 0.0, 0.045))
    wall_panel("Sign_arch", "Sign_Paint", "-x", x1, 0.0, 2.95, 0.05, 2.2, 0.32, sign_uv("arch"))
    part("SignBoard_arch", "Metal_Dark", lambda bm: wall_box(bm, "-x", x1, -1.15, 1.15, 2.76, 3.14, 0.0, 0.045))
    part("SignBoard_street", "Metal_Dark", lambda bm: wall_box(bm, "+x", x0, 1.3, 3.5, 2.5, 2.88, 0.0, 0.03))
    wall_panel("Sign_street", "Sign_Paint", "+x", x0, 2.4, 2.69, 0.0305, 2.1, 0.32, sign_uv("street"))
    wall_panel("Notice_W0", "Poster_Art", "+x", x0, -2.2, 1.5, 0.004, 0.55, 0.55, cell_uv(8))
    wall_panel("Notice_W1", "Poster_Art", "+x", x0, -3.0, 1.45, 0.004, 0.55, 0.55, cell_uv(11))
    # bunting across the street, overhead
    def bunting(bm):
        uvl = bm.loops.layers.uv["UVMap"]
        for x in (-12.0, -4.0, 4.0, 12.0):
            za, zb = -5.4 + 0.05, 5.4 - 0.05
            nflag = 24
            for i in range(nflag):
                t0, t1 = i / nflag, (i + 0.8) / nflag
                y0_ = 4.65 - 0.45 * math.sin(math.pi * t0)
                y1_ = 4.65 - 0.45 * math.sin(math.pi * t1)
                p0, p1 = (x + 0.15 * math.sin(t0 * 6), y0_, za + (zb - za) * t0), (x + 0.15 * math.sin(t1 * 6), y1_, za + (zb - za) * t1)
                pm = ((p0[0] + p1[0]) / 2, (y0_ + y1_) / 2 - 0.22, (p0[2] + p1[2]) / 2)
                f = bm.faces.new([bm.verts.new(B(p)) for p in (p0, p1, pm)])
                c = (i % 8) / 8 + 1 / 16
                for lp in f.loops:
                    lp[uvl].uv = (c, 0.5)
    part("decor_Bunting", "Bunting", bunting, keep_uv=True, keep_normals=True)
    part("decor_Bunting_Cord", "Metal_Dark", lambda bm: [[cyl(bm, (x + 0.15 * math.sin(t0 * 6), 4.65 - 0.45 * math.sin(math.pi * t0), -5.35 + 10.7 * t0),
                                                                 (x + 0.15 * math.sin(t1 * 6), 4.65 - 0.45 * math.sin(math.pi * t1), -5.35 + 10.7 * t1), 0.005, 0.005, 4, cap=False)
                                                             for t0, t1 in zip(np.linspace(0, 1, 13), np.linspace(0, 1, 13)[1:])] for x in (-12.0, -4.0, 4.0, 12.0)])
    # light: a low warm 'sun' from the painted east end down the street (day), the emergency fittings (night) on the fronts and the end walls
    SPOTS_DAY.append(((15.2, 7.3, 0.0), tuple((Vector((-10.0, 0.0, 0.0)) - Vector((15.2, 7.3, 0.0))).normalized()), 2600.0, 46.0))
    for k, (n, plane, a) in enumerate((("+z", -5.4, -8.0), ("+z", -5.4, 8.0), ("-z", 5.4, 0.0), ("-z", 5.4, -12.0), ("-z", 5.4, 12.0))):
        emergency(f"F{k}", n, plane, a, 3.0)
    emergency("W", "+x", x0, -1.6, 2.7)
    emergency("E", "-x", x1, 0.0, 4.0)


# ================================================================ scene_2991: the soft play and the carousel
def clip_poly(poly, x0, x1, z0, z1):
    """A polygon [(x, z)] clipped to a rectangle (Sutherland-Hodgman)."""
    def clip(pts, inside_fn, inter):
        out = []
        for i in range(len(pts)):
            p, q = pts[i - 1], pts[i]
            if inside_fn(q):
                if not inside_fn(p):
                    out.append(inter(p, q))
                out.append(q)
            elif inside_fn(p):
                out.append(inter(p, q))
        return out

    def ix(xc):
        return lambda p, q: (xc, p[1] + (q[1] - p[1]) * (xc - p[0]) / (q[0] - p[0]))

    def iz(zc):
        return lambda p, q: (p[0] + (q[0] - p[0]) * (zc - p[1]) / (q[1] - p[1]), zc)
    pts = poly
    for f, it in ((lambda p: p[0] >= x0, ix(x0)), (lambda p: p[0] <= x1, ix(x1)), (lambda p: p[1] >= z0, iz(z0)), (lambda p: p[1] <= z1, iz(z1))):
        pts = clip(pts, f, it)
        if not pts:
            break
    return pts


def prism(bm, poly, y0, y1):
    """A vertical prism over a convex polygon [(x, z)]: top, bottom and sides."""
    top = [bm.verts.new(B((x, y1, z))) for x, z in poly]
    bot = [bm.verts.new(B((x, y0, z))) for x, z in poly]
    bm.faces.new(top)
    bm.faces.new(bot[::-1])
    n = len(poly)
    for i in range(n):
        bm.faces.new((bot[i], bot[(i + 1) % n], top[(i + 1) % n], top[i]))


def horse(tag, px, pz, y, tang, colour_mat="Horse_Enamel"):
    """A carousel horse as generic shapes (decor): a long rounded body on the pole, a neck and a head block leaning forward, a saddle, four
    folded legs as rods; no face, no figure."""
    tx, tz = tang
    fwd = Vector((tx, 0, tz))

    def P(f, up, s=0.0):
        side = Vector((-tz, 0, tx))
        q = Vector((px, y, pz)) + fwd * f + Vector((0, up, 0)) + side * s
        return (q.x, q.y, q.z)

    def body(bm):
        ang = math.atan2(tz, tx)
        bmesh.ops.create_uvsphere(bm, u_segments=14, v_segments=8, radius=1.0,
                                  matrix=Matrix.Translation(B(P(0, 0))) @ Matrix.Rotation(-ang, 4, "Z") @ Matrix.Diagonal((0.42, 0.13, 0.17, 1)))
        cyl(bm, P(0.3, 0.05), P(0.52, 0.42), 0.09, 0.065, 10)
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(B(P(0.6, 0.47))) @ Matrix.Rotation(-ang, 4, "Z") @ Matrix.Rotation(0.5, 4, "Y") @
                              Matrix.Diagonal((0.24, 0.1, 0.12, 1)))
        for f_, s in ((0.24, 0.07), (0.24, -0.07), (-0.26, 0.07), (-0.26, -0.07)):
            k = 1 if f_ > 0 else -1
            cyl(bm, P(f_, -0.08, s), P(f_ + k * 0.2, -0.3, s), 0.03, 0.025, 6)
            cyl(bm, P(f_ + k * 0.2, -0.3, s), P(f_ + k * 0.05, -0.45, s), 0.025, 0.02, 6)
        cyl(bm, P(-0.4, 0.04), P(-0.58, -0.22), 0.04, 0.015, 6)
    part(f"decor_Horse_{tag}", colour_mat, body, smooth=True, sharp_deg=60)
    part(f"decor_Horse_{tag}_Saddle", "Carousel_Red", lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=1.0,
                                                                                          matrix=Matrix.Translation(B(P(-0.02, 0.12))) @ Matrix.Rotation(-math.atan2(tz, tx), 4, "Z") @ Matrix.Diagonal((0.17, 0.15, 0.05, 1))),
         smooth=True)


def scene_2991():
    rng = np.random.default_rng(2991)
    # floors: rubber tiles in the soft play (a terrazzo threshold by the wing's door), terrazzo in the carousel hall
    floor_slab(BOXL["Play_Floor"], "Floor_Rubber")
    floor_slab(BOXL["Carousel_Floor"], "Floor_Terrazzo")
    part("Threshold", "Floor_Terrazzo", lambda bm: flat_decal(bm, -8.6, -5.4, 5.0, 7.0, 0.004), keep_normals=True)
    border_strips("carousel", 2.2, 16.0, -7.0, 7.0, 0.0, w=0.45, gaps=[(15.0, 16.0, -1.0, 1.0)])
    dust_strips("carousel", 2.2, 16.0, -7.0, 7.0, 0.0, gaps=[(14.8, 16.0, -1.0, 1.0), (2.2, 3.2, -3.0, 3.0)])
    cx = 9.0

    def ring(bm):
        n = 48
        for i in range(n):
            a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
            for r0, r1 in ((4.6, 5.0),):
                quad(bm, (cx + r0 * math.cos(a0), 0.004, r0 * math.sin(a0)), (cx + r0 * math.cos(a1), 0.004, r0 * math.sin(a1)),
                     (cx + r1 * math.cos(a1), 0.004, r1 * math.sin(a1)), (cx + r1 * math.cos(a0), 0.004, r1 * math.sin(a0)))
        bm.normal_update()
        for f in bm.faces:
            if f.normal.z < 0:
                f.normal_flip()
    part("Carousel_FloorRing", "Floor_Border", ring, keep_normals=True)
    # the play room's walls: padded panels to 1.2 m (within 4 cm of the wall), a fake PARTY ROOM door painted on the west wall
    for nm, n, plane, a0, a1 in (("N", "+z", -7.0, -15.9, 1.9), ("S0", "-z", 7.0, -15.9, -8.2), ("S1", "-z", 7.0, -5.8, 1.9)):
        segs = np.linspace(a0, a1, max(2, int((a1 - a0) / 1.2)) + 1)
        if nm == "S0":
            segs = [s for s in segs if not (-13.9 < s < -12.1)]
        part(f"WallPads_{nm}", "Padding_Vinyl", lambda bm: [wall_box(bm, n, plane, sa + 0.01, sb - 0.01, 0.12, 1.2, 0.0, 0.04) for sa, sb in zip(segs, segs[1:]) if sb - sa < 1.5])
    wall_panel("FakeDoor_Party", "Door_Leaves", "-z", 7.0, -13.0, 1.05, 0.02, 0.94, 2.1, door_uv("house_blue"))
    part("FakeDoor_Party_Case", "Trim_Paint", lambda bm: [wall_box(bm, "-z", 7.0, -13.6, -13.5, 0.0, 2.2, 0.0, 0.04), wall_box(bm, "-z", 7.0, -12.5, -12.4, 0.0, 2.2, 0.0, 0.04),
                                                          wall_box(bm, "-z", 7.0, -13.6, -12.4, 2.1, 2.22, 0.0, 0.04)])
    part("SignBoard_party", "Metal_Dark", lambda bm: wall_box(bm, "-z", 7.0, -14.2, -11.8, 2.35, 2.75, 0.0, 0.03))
    wall_panel("Sign_party", "Sign_Paint", "-z", 7.0, -13.0, 2.55, 0.0305, 2.3, 0.34, sign_uv("party"))
    part("SignBoard_play", "Metal_Dark", lambda bm: wall_box(bm, "-z", 7.0, -9.0, -5.0, 2.58, 3.18, 0.0, 0.03))
    wall_panel("Sign_play", "Sign_Paint", "-z", 7.0, -7.0, 2.88, 0.0305, 3.9, 0.5, sign_uv("play"))
    wall_panel("Notice_rules", "Poster_Art", "-z", 7.0, -9.6, 1.6, 0.045, 0.6, 0.9, cell_uv(0))
    wall_panel("Notice_parties", "Poster_Art", "-z", 7.0, -4.4, 1.6, 0.045, 0.6, 0.9, cell_uv(2))
    wall_panel("Notice_pit", "Poster_Art", "+z", -7.0, -3.0, 1.65, 0.045, 0.6, 0.9, cell_uv(3))
    # the soft play frame: padded posts, two decks, steps up, roof beams, netting on every side (all inside the greybox's box)
    sf = BOXL["SoftPlay_Frame"]
    fx0, fx1, fz0, fz1 = sf["min"][0], sf["max"][0], sf["min"][2], sf["max"][2]
    with inside("SoftPlay_Frame"):
        xs, zs = np.linspace(fx0 + 0.1, fx1 - 0.1, 5), np.linspace(fz0 + 0.1, fz1 - 0.1, 3)
        posts = [(x, z) for x in xs for z in zs if x in (xs[0], xs[-1]) or z in (zs[0], zs[-1])]
        part("SoftPlay_Posts", "Padding_Vinyl", lambda bm: [cyl(bm, (x, 0.0, z), (x, 3.1, z), 0.09, 0.09, 12) for x, z in posts], smooth=True)
        xm = (fx0 + fx1) / 2

        def decks(bm):
            cube(bm, (fx0 + 0.1, 1.0, fz0 + 0.1), (xm, 1.15, fz1 - 0.1))
            cube(bm, (xm, 2.1, fz0 + 0.1), (fx1 - 0.1, 2.25, fz1 - 0.1))
            cube(bm, (fx0 + 0.1, 3.05, fz0 + 0.1), (fx1 - 0.1, 3.2, fz0 + 0.3))
            cube(bm, (fx0 + 0.1, 3.05, fz1 - 0.3), (fx1 - 0.1, 3.2, fz1 - 0.1))
            cube(bm, (fx0 + 0.1, 3.05, fz0 + 0.3), (fx0 + 0.3, 3.2, fz1 - 0.3))
            cube(bm, (fx1 - 0.3, 3.05, fz0 + 0.3), (fx1 - 0.1, 3.2, fz1 - 0.3))
            for k in range(3):                                                 # padded steps from the floor to the first deck, and on to the second
                cube(bm, (fx0 + 0.9 + k * 0.5, 0.0, fz1 - 1.1), (fx0 + 1.4 + k * 0.5, 0.33 * (k + 1), fz1 - 0.15))
                cube(bm, (xm - 1.5 + k * 0.5, 1.15, fz0 + 0.15), (xm - 1.0 + k * 0.5, 1.15 + 0.33 * (k + 1), fz0 + 1.1))
            cube(bm, (fx0 + 2.6, 1.15, fz0 + 1.6), (fx0 + 3.0, 1.75, fz0 + 2.0))             # a padded roller pillar
        part("SoftPlay_Decks", "Padding_Vinyl", decks)

        def nets(bm):
            uvl = bm.loops.layers.uv["UVMap"]
            for (p, q) in (((fx0 + 0.02, fz0 + 0.02), (fx1 - 0.02, fz0 + 0.02)), ((fx0 + 0.02, fz1 - 0.02), (fx1 - 0.02, fz1 - 0.02)),
                           ((fx0 + 0.02, fz0 + 0.02), (fx0 + 0.02, fz1 - 0.02)), ((fx1 - 0.02, fz0 + 0.02), (fx1 - 0.02, fz1 - 0.02))):
                L_ = math.hypot(q[0] - p[0], q[1] - p[1])
                segs = [(0.0, 1.0, 0.0, 3.2)]
                if p[0] == q[0] == fx1 - 0.02:                                # the slide's mouth and the way in on the east side
                    segs = [(0.0, (-3.05 - fz0) / L_, 0.0, 3.2), ((-1.95 - fz0) / L_, 1.0, 0.0, 3.2), ((-3.05 - fz0) / L_, (-1.95 - fz0) / L_, 0.0, 2.25)]
                if p[1] == q[1] == fz1 - 0.02:
                    segs = [(0.0, 0.62, 0.0, 3.2), (0.82, 1.0, 0.0, 3.2), (0.62, 0.82, 2.1, 3.2)]
                for t0, t1, ya, yb in segs:
                    a_ = (p[0] + (q[0] - p[0]) * t0, p[1] + (q[1] - p[1]) * t0)
                    b_ = (p[0] + (q[0] - p[0]) * t1, p[1] + (q[1] - p[1]) * t1)
                    f = quad(bm, (a_[0], ya, a_[1]), (b_[0], ya, b_[1]), (b_[0], yb, b_[1]), (a_[0], yb, a_[1]))
                    for lp, (s, t) in zip(f.loops, ((t0 * L_, ya), (t1 * L_, ya), (t1 * L_, yb), (t0 * L_, yb))):
                        lp[uvl].uv = (s / 0.6, t / 0.6)
        part("SoftPlay_Frame", "Net_Mesh", nets, keep_uv=True, keep_normals=True)

    def top_net(bm):
        uvl = bm.loops.layers.uv["UVMap"]
        for (p, q) in (((fx0, fz0), (fx1, fz0)), ((fx1, fz0), (fx1, fz1)), ((fx1, fz1), (fx0, fz1)), ((fx0, fz1), (fx0, fz0))):
            L_ = math.hypot(q[0] - p[0], q[1] - p[1])
            f = quad(bm, (p[0], 3.2, p[1]), (q[0], 3.2, q[1]), (q[0], 4.2, q[1]), (p[0], 4.2, p[1]))
            for lp, (s, t) in zip(f.loops, ((0, 0), (L_, 0), (L_, 1), (0, 1))):
                lp[uvl].uv = (s / 0.6, t / 0.6)
        f = quad(bm, (fx0, 4.2, fz0), (fx1, 4.2, fz0), (fx1, 4.2, fz1), (fx0, 4.2, fz1))
        for lp, (s, t) in zip(f.loops, ((0, 0), (7, 0), (7, 5), (0, 5))):
            lp[uvl].uv = (s / 0.6, t / 0.6)
    part("decor_SoftPlay_Net", "Net_Mesh", top_net, keep_uv=True, keep_normals=True)
    part("decor_SoftPlay_NetPosts", "Padding_Vinyl", lambda bm: [cyl(bm, (x, 3.2, z), (x, 4.2, z), 0.04, 0.04, 8) for x in (fx0 + 0.05, fx1 - 0.05) for z in (fz0 + 0.05, fz1 - 0.05)])

    def slide(bm):
        n = 14
        for i in range(n):
            t0, t1 = i / n, (i + 1) / n

            def pt(t, z, up=0.0):
                x = -7.0 + 1.35 * t
                y = 2.25 - 2.1 * (t - 0.18 * math.sin(math.pi * t)) + up
                return (x, y, z)
            for (za, zb, ua, ub) in ((-2.9, -2.1, 0.0, 0.0), (-2.92, -2.9, 0.0, 0.28), (-2.1, -2.08, 0.28, 0.0)):
                if ua == ub == 0.0:
                    quad(bm, pt(t0, za), pt(t0, zb), pt(t1, zb), pt(t1, za))
                else:
                    quad(bm, pt(t0, za, ua), pt(t0, zb, ub), pt(t1, zb, ub), pt(t1, za, ua))
            quad(bm, pt(t0, -2.92, 0.28), pt(t0, -2.9, 0.28), pt(t1, -2.9, 0.28), pt(t1, -2.92, 0.28))
            quad(bm, pt(t0, -2.1, 0.28), pt(t0, -2.08, 0.28), pt(t1, -2.08, 0.28), pt(t1, -2.1, 0.28))
    ob = part("decor_Slide", "Slide_Plastic", slide, keep_normals=True)
    for nm in ("decor_Slide",):
        HANDLED.add(nm)
    # the ball pit: padded rims with a roll on top, the balls a third of the way up, strays on the floor
    for b in GB.boxes:
        if b["name"].startswith("BallPit_Rim"):
            mn, mx = b["min"], b["max"]
            solid_art(b, "Padding_Vinyl")
            along_x = (mx[0] - mn[0]) > (mx[2] - mn[2])
            c_ = ((mn[2] + mx[2]) / 2) if along_x else ((mn[0] + mx[0]) / 2)
            with inside(b["name"]):
                if along_x:
                    part(f"{b['name']}_Roll", "Padding_Vinyl", lambda bm: cyl(bm, (mn[0], mx[1], c_), (mx[0], mx[1], c_), 0.1, 0.1, 12), smooth=True)
                else:
                    part(f"{b['name']}_Roll", "Padding_Vinyl", lambda bm: cyl(bm, (c_, mx[1], mn[2]), (c_, mx[1], mx[2]), 0.1, 0.1, 12), smooth=True)
    pf = BOXL["decor_BallPit_Floor"]

    def balls(bm):
        x0_, x1_, z0_, z1_ = pf["min"][0], pf["max"][0], pf["min"][2], pf["max"][2]
        nx_, nz_ = 18, 18
        vs = [[bm.verts.new(B((x0_ + (x1_ - x0_) * i / nx_, 0.3 + 0.035 * math.sin(i * 1.7 + j * 0.9) * math.sin(j * 2.3) + 0.05 * (1 - abs(2 * i / nx_ - 1)) * (1 - abs(2 * j / nz_ - 1)),
                                    z0_ + (z1_ - z0_) * j / nz_))) for j in range(nz_ + 1)] for i in range(nx_ + 1)]
        for i in range(nx_):
            for j in range(nz_):
                bm.faces.new((vs[i][j], vs[i][j + 1], vs[i + 1][j + 1], vs[i + 1][j]))
        bm.normal_update()
        for f in bm.faces:
            if f.normal.z < 0:
                f.normal_flip()
    part("decor_BallPit_Balls", "Ball_Pit", balls, keep_normals=True, tile=0.8)
    pts = [(rng.uniform(-6.0, 0.0), rng.uniform(-6.8, -1.6)) for _ in range(60)]
    pts = [p for p in pts if not (-5.05 < p[0] < -0.95 and -6.05 < p[1] < -1.95) and math.hypot(p[0] + 6.2, p[1] + 0.8) > 0.8]
    part("decor_StrayBalls", "Ball_Pit", lambda bm: [sphere(bm, (x, 0.04, z), 0.04, 8) for x, z in pts], smooth=True, tile=0.08)
    # the parents' benches; the toddlers' mat and its foam shapes (decor: passable, soft)
    for b in GB.boxes:
        if b["name"].startswith("Parent_Bench"):
            bench(b, "-x")
    tm = BOXL["decor_Toddler_Mat"]
    part("decor_Toddler_Mat", "Padding_Vinyl", lambda bm: cube(bm, (tm["min"][0], 0.0, tm["min"][2]), (tm["max"][0], 0.06, tm["max"][2])))
    part("decor_Foam_Shapes", "Padding_Vinyl", lambda bm: [cyl(bm, (-11.2, 0.06, 2.8), (-11.2, 0.36, 2.8), 0.3, 0.3, 16), cube(bm, (-10.2, 0.06, 2.4), (-9.7, 0.46, 2.9)),
                                                         cube(bm, (-9.6, 0.06, 2.5), (-9.2, 0.36, 2.9)), cube(bm, (-8.9, 0.06, 4.2), (-8.4, 0.56, 4.7)),
                                                         cyl(bm, (-10.6, 0.36, 4.3), (-9.8, 0.36, 4.3), 0.25, 0.25, 14)], smooth=True, sharp_deg=50)

    def wedge(bm):
        quad(bm, (-11.8, 0.06, 4.0), (-11.0, 0.06, 4.0), (-11.0, 0.06, 4.8), (-11.8, 0.06, 4.8))
        quad(bm, (-11.8, 0.06, 4.0), (-11.8, 0.46, 4.0), (-11.0, 0.46, 4.0), (-11.0, 0.06, 4.0))
        quad(bm, (-11.8, 0.46, 4.0), (-11.8, 0.06, 4.8), (-11.0, 0.06, 4.8), (-11.0, 0.46, 4.0))
        bm.faces.new([bm.verts.new(B(p)) for p in ((-11.8, 0.06, 4.0), (-11.8, 0.06, 4.8), (-11.8, 0.46, 4.0))])
        bm.faces.new([bm.verts.new(B(p)) for p in ((-11.0, 0.06, 4.0), (-11.0, 0.46, 4.0), (-11.0, 0.06, 4.8))])
    part("decor_Foam_Wedge", "Padding_Vinyl", wedge)
    # the carousel: a round deck (as the greybox's two boxes, cut to a circle, and four fills), the painted centre, brass poles, the horses,
    # the canopy with its scalloped valance and bulbs
    R = 4.3
    circ = [(cx + R * math.cos(2 * math.pi * i / 64), R * math.sin(2 * math.pi * i / 64)) for i in range(64)]
    p1, p2 = BOXL["Carousel_Platform"], BOXL["Carousel_Platform_2"]
    HANDLED.update({p1["name"], p2["name"]})
    part(p1["name"], "Bench_Wood", lambda bm: prism(bm, clip_poly(circ, p1["min"][0], p1["max"][0], p1["min"][2], p1["max"][2]), 0.0, 0.3))
    part(p2["name"], "Bench_Wood", lambda bm: [prism(bm, clip_poly(circ, p2["min"][0], p2["max"][0], za, zb), 0.0, 0.3) for za, zb in ((p2["min"][2], p1["min"][2]), (p1["max"][2], p2["max"][2]))])

    def fills(bm):
        for sx in (-1, 1):
            for sz in (-1, 1):
                xa_, xb_ = (cx + 2.5, cx + R) if sx > 0 else (cx - R, cx - 2.5)
                za_, zb_ = (2.5, R) if sz > 0 else (-R, -2.5)
                poly = clip_poly(circ, xa_, xb_, za_, zb_)
                poly = [p for p in poly]
                if len(poly) >= 3:
                    prism(bm, poly, 0.0, 0.3)
    part("decor_Carousel_Fill", "Bench_Wood", fills)

    def skirt(bm):
        uvl = bm.loops.layers.uv["UVMap"]
        n = 64
        for i in range(n):
            a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
            f = quad(bm, (cx + (R + 0.01) * math.cos(a0), 0.0, (R + 0.01) * math.sin(a0)), (cx + (R + 0.01) * math.cos(a1), 0.0, (R + 0.01) * math.sin(a1)),
                     (cx + (R + 0.01) * math.cos(a1), 0.3, (R + 0.01) * math.sin(a1)), (cx + (R + 0.01) * math.cos(a0), 0.3, (R + 0.01) * math.sin(a0)))
            for lp, (u, v) in zip(f.loops, ((i / 4, 0.52), ((i + 1) / 4, 0.52), ((i + 1) / 4, 0.62), (i / 4, 0.62))):
                lp[uvl].uv = (u, v)
        bm.normal_update()
        for f in bm.faces:
            c = f.calc_center_median()
            if f.normal.dot(c - B((cx, 0.15, 0))) < 0:
                f.normal_flip()
    part("decor_Carousel_Skirt", "Carousel_Paint", skirt, keep_uv=True, keep_normals=True)
    ce = BOXL["Carousel_Centre"]
    HANDLED.add(ce["name"])

    def centre(bm):
        uvl = bm.loops.layers.uv["UVMap"]
        n = 24
        y0_, y1_ = ce["min"][1], ce["max"][1]
        for i in range(n):
            a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
            f = quad(bm, (cx + 0.48 * math.cos(a0), y0_, 0.48 * math.sin(a0)), (cx + 0.48 * math.cos(a1), y0_, 0.48 * math.sin(a1)),
                     (cx + 0.48 * math.cos(a1), y1_, 0.48 * math.sin(a1)), (cx + 0.48 * math.cos(a0), y1_, 0.48 * math.sin(a0)))
            for lp, (u, v) in zip(f.loops, ((i / 6, 0.02), ((i + 1) / 6, 0.02), ((i + 1) / 6, 0.48), (i / 6, 0.48))):
                lp[uvl].uv = (u, v)
        bm.normal_update()
        for f in bm.faces:
            if f.normal.dot(f.calc_center_median() - B((cx, 3.0, 0))) < 0:
                f.normal_flip()
    part(ce["name"], "Carousel_Paint", centre, keep_uv=True, keep_normals=True)
    part("Carousel_CentreTrim", "Brass", lambda bm: [cyl(bm, (cx, 0.3, 0), (cx, 0.5, 0), 0.5, 0.5, 24), cyl(bm, (cx, 2.0, 0), (cx, 2.08, 0), 0.5, 0.5, 24),
                                                     cyl(bm, (cx, 5.85, 0), (cx, 6.0, 0), 0.5, 0.5, 24)], smooth=True)
    for b in GB.boxes:
        if b["name"].startswith("Horse_Pole"):
            mn, mx = b["min"], b["max"]
            hx, hz = (mn[0] + mx[0]) / 2, (mn[2] + mx[2]) / 2
            HANDLED.add(b["name"])
            part(b["name"], "Brass", lambda bm: [cyl(bm, (hx, mn[1], hz), (hx, mx[1], hz), 0.03, 0.03, 10), cyl(bm, (hx, mn[1], hz), (hx, mn[1] + 0.06, hz), 0.045, 0.045, 10),
                                                 cyl(bm, (hx, mx[1] - 0.06, hz), (hx, mx[1], hz), 0.045, 0.045, 10)], smooth=True)
            a = math.atan2(hz, hx - cx)
            k = int(round(a / (math.pi / 4))) % 8
            horse(f"{k}", hx, hz, 1.25 + 0.25 * math.sin(k * 1.9), (-math.sin(a), math.cos(a)))
    part("decor_Carousel_Canopy_Underside", "Trim_Paint", lambda bm: disc(bm, (cx, 4.6, 0), R + 0.1, 48), keep_normals=True)

    def canopy(bm):
        uvl = bm.loops.layers.uv["UVMap"]
        n = 48
        rings = [((R + 0.1), 4.6, 0.0), ((R + 0.1), 5.2, 0.5), (0.55, 6.35, 0.5), (0.2, 6.5, 0.5)]
        for i in range(n):
            a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
            for (ra, ya, va), (rb, yb, vb) in zip(rings, rings[1:]):
                f = quad(bm, (cx + ra * math.cos(a0), ya, ra * math.sin(a0)), (cx + ra * math.cos(a1), ya, ra * math.sin(a1)),
                         (cx + rb * math.cos(a1), yb, rb * math.sin(a1)), (cx + rb * math.cos(a0), yb, rb * math.sin(a0)))
                if ya < 5.0:
                    uvs = ((i / 3, 0.52 + 0.47 * 0), ((i + 1) / 3, 0.52), ((i + 1) / 3, 0.99), (i / 3, 0.99))
                else:
                    uvs = ((i / 6, 0.55), ((i + 1) / 6, 0.55), ((i + 1) / 6, 0.75), (i / 6, 0.75))
                for lp, uv in zip(f.loops, uvs):
                    lp[uvl].uv = uv
        bm.normal_update()
        for f in bm.faces:
            if f.normal.dot(f.calc_center_median() - B((cx, 4.0, 0))) < 0:
                f.normal_flip()
    part("decor_Carousel_Canopy", "Carousel_Paint", canopy, keep_uv=True, keep_normals=True)
    bulbs = [(cx + (R + 0.13) * math.cos(2 * math.pi * i / 40), 4.68, (R + 0.13) * math.sin(2 * math.pi * i / 40)) for i in range(40)]
    bulbs += [(cx + r_ * math.cos(2 * math.pi * i / 12 + 0.13), 4.58, r_ * math.sin(2 * math.pi * i / 12 + 0.13)) for r_ in (1.6, 3.0) for i in range(12)]
    on = [rng.random() > 0.15 for _ in bulbs]
    part("decor_Carousel_Bulbs", "Lamp_Emit", lambda bm: [sphere(bm, p, 0.035, 8) for p, o in zip(bulbs, on) if o], smooth=True)
    part("decor_Carousel_BulbsDead", "Metal_Dark", lambda bm: [sphere(bm, p, 0.035, 8) for p, o in zip(bulbs, on) if not o], smooth=True)
    for k in range(8):
        a = 2 * math.pi * k / 8
        POINTS_DAY.append(((cx + 2.6 * math.cos(a), 4.45, 2.6 * math.sin(a)), 40.0, 0.2))
    part("decor_Carousel_Crown", "Brass", lambda bm: [cyl(bm, (cx, 6.5, 0), (cx, 6.62, 0), 0.25, 0.08, 12), sphere(bm, (cx, 6.72, 0), 0.1, 10)], smooth=True)
    # the carousel hall's walls: its sign, a poster, the token machine's board
    part("SignBoard_carousel", "Metal_Dark", lambda bm: wall_box(bm, "+z", -7.0, 7.0, 11.0, 2.0, 2.6, 0.0, 0.03))
    wall_panel("Sign_carousel", "Sign_Paint", "+z", -7.0, 9.0, 2.3, 0.0305, 3.9, 0.5, sign_uv("carousel"))
    wall_panel("Notice_carousel", "Poster_Art", "+z", -7.0, 12.6, 1.55, 0.045, 0.6, 0.9, cell_uv(1))
    wall_panel("Poster_fun", "Poster_Art", "-z", 7.0, 9.0, 1.55, 0.045, 0.9, 1.35, cell_uv(7))
    part("SignBoard_tokens", "Metal_Dark", lambda bm: wall_box(bm, "-z", 7.0, 4.0, 6.4, 2.1, 2.5, 0.0, 0.03))
    wall_panel("Sign_tokens", "Sign_Paint", "-z", 7.0, 5.2, 2.3, 0.0305, 2.3, 0.34, sign_uv("tokens"))
    # light: floods on the walls high over the soft play and the carousel (day), the emergency fittings (night)
    for k, (n, plane, a, tgt) in enumerate((("+z", -7.0, -11.0, (-10.5, 0.0, -2.0)), ("-z", 7.0, -13.0, (-10.0, 0.0, 2.0)), ("+z", -7.0, -2.0, (-3.0, 0.0, -3.5)),
                                            ("-z", 7.0, 0.0, (-2.0, 0.0, 2.0)), ("+z", -7.0, 13.5, (cx, 0.0, 0.0)), ("-z", 7.0, 13.5, (cx, 0.0, 0.0)))):
        flood(f"F{k}", n, plane, a, 4.4 if a < 2 else 6.0, tgt, 600.0 if a < 2 else 800.0, 55.0)
    for k, (n, plane, a, y) in enumerate((("+x", -16.0, 2.5, 2.4), ("-z", 7.0, -12.5, 2.4), ("+z", -7.0, -6.0, 2.4), ("-z", 7.0, 0.8, 2.4),
                                          ("+z", -7.0, 5.5, 3.2), ("-z", 7.0, 12.5, 3.2), ("-x", 16.0, 3.5, 3.2))):
        emergency(f"E{k}", n, plane, a, y)


# ================================================================ scene_3008: the escalator well
def scene_3008():
    rng = np.random.default_rng(3008)
    x0, x1, z0, z1, gy = -8.0, 8.0, -12.0, 12.0, 4.5
    floor_slab(BOXL["Well_Floor"], "Floor_Terrazzo")
    border_strips("lower", x0, x1, z0, z1, 0.0, w=0.45, gaps=[(-0.8, 0.8, z1 - 0.6, z1)])
    dust_strips("lower", x0, x1, z0, z1, 0.0, gaps=[(-1.0, 1.0, z1 - 1.0, z1)])
    # the gallery: terrazzo on top, a painted soffit with downlights under it, a fascia at its edge; glass balustrades with a steel handrail
    gs = BOXL["Gallery_Slab"]
    floor_slab(gs, "Floor_Terrazzo", step=2.0)
    border_strips("gallery", x0, x1, z0, -3.0, gy, w=0.4, gaps=[(-0.8, 0.8, z0, z0 + 0.6), (x1 - 0.6, x1, -8.3, -6.7), (-2.8, -1.2, -3.6, -3.0), (1.2, 2.8, -3.6, -3.0)])
    part("Gallery_Soffit", "Ceiling_Paint", lambda bm: [flat_decal(bm, xa, xb, za, zb, gy - SLAB - 0.002) for xa, xb in zip(np.linspace(x0, x1, 5), np.linspace(x0, x1, 5)[1:])
                                                        for za, zb in zip(np.linspace(z0, -3.0, 4), np.linspace(z0, -3.0, 4)[1:])], keep_normals=True)
    orient_faces(bpy.data.objects["Gallery_Soffit"], (0, -1, 0))
    part("Gallery_Fascia", "Trim_Paint", lambda bm: cube(bm, (x0, gy - SLAB - 0.05, -3.0), (x1, gy + 0.02, -2.96)))
    downs = [(x, gy - SLAB - 0.004, z) for x in (-6.0, -2.0, 2.0, 6.0) for z in (-10.5, -7.5, -4.5)]
    part("Gallery_Downlight_Rims", "Trim_Paint", lambda bm: [disc(bm, (p[0], p[1] - 0.001, p[2]), 0.16, 16) for p in downs], keep_normals=True)
    part("Gallery_Downlights", "Lamp_Emit", lambda bm: [disc(bm, (p[0], p[1] - 0.004, p[2]), 0.12, 16) for p in downs], keep_normals=True)
    SPOTS_DAY.extend(((p[0], p[1] - 0.05, p[2]), (0.0, -1.0, 0.0), 160.0, 110.0) for p in downs)
    for b in GB.boxes:
        if b["name"].startswith("Gallery_Rail"):
            mn, mx = b["min"], b["max"]
            HANDLED.add(b["name"])
            zc = (mn[2] + mx[2]) / 2
            part(b["name"], "Metal_Steel", lambda bm: [cube(bm, (mn[0], mn[1], mn[2] + 0.01), (mx[0], mn[1] + 0.08, mx[2] - 0.01)),
                                                       cyl(bm, (mn[0], mx[1] - 0.03, zc), (mx[0], mx[1] - 0.03, zc), 0.03, 0.03, 10)] +
                 [cube(bm, (x - 0.015, mn[1] + 0.08, zc - 0.015), (x + 0.015, mx[1] - 0.05, zc + 0.015)) for x in np.linspace(mn[0] + 0.05, mx[0] - 0.05, max(2, int((mx[0] - mn[0]) / 1.4)) + 1)], smooth=True)
            ob = part(f"{b['name']}_Glass", "Glass_Clear", lambda bm: quad(bm, (mn[0] + 0.05, mn[1] + 0.08, zc), (mx[0] - 0.05, mn[1] + 0.08, zc),
                                                                         (mx[0] - 0.05, mx[1] - 0.07, zc), (mn[0] + 0.05, mx[1] - 0.07, zc)), keep_normals=True)
            orient_faces(ob, (0, 0, 1))
    # the two stopped escalators: steps on the greybox's step boxes (0.2 m deep, so the check reads them as steps), risers, skirts and side
    # cladding, glass balustrades, black handrails with their newels, the comb plates at both landings (all but the steps passable: decor)
    for fl in GB.flights:
        steps = sorted([b for b in GB.boxes if b["name"].startswith(f"Step_{fl['name']}_")], key=lambda b: b["name"])
        lane0, lane1 = steps[0]["min"][0], steps[0]["max"][0]
        for b in steps:
            mn, mx = b["min"], b["max"]
            HANDLED.add(b["name"])
            part(b["name"], "Escalator_Step", lambda bm: cube(bm, (mn[0], mx[1] - 0.199, mn[2]), (mx[0], mx[1], mx[2])), tile=0.6)
        part(f"decor_{fl['name']}_Risers", "Metal_Dark", lambda bm: [quad(bm, (lane0, b["max"][1] - 0.25, b["max"][2]), (lane1, b["max"][1] - 0.25, b["max"][2]),
                                                                          (lane1, b["max"][1] - 0.199, b["max"][2]), (lane0, b["max"][1] - 0.199, b["max"][2])) for b in steps[1:]], keep_normals=True)
        orient_faces(bpy.data.objects[f"decor_{fl['name']}_Risers"], (0, 0, 1))
        zb, zt = steps[0]["max"][2], steps[-1]["min"][2]                            # the foot (z +4.2) and the head (z -3.0) of the flight

        def line(z):                                                                  # the nosing line's height at z
            return min(gy, max(0.0, (zb - z) / (zb - zt) * gy))
        for side, xb_ in (("out", lane0 - 0.08 if lane0 < 0 else lane1 + 0.08), ("in", lane1 + 0.08 if lane0 < 0 else lane0 - 0.08)):
            zz = np.linspace(zb + 0.8, zt - 0.8, 24)

            def glass(bm, xb_=xb_, zz=zz):
                for za, zc in zip(zz, zz[1:]):
                    quad(bm, (xb_, line(za) + 0.15, za), (xb_, line(zc) + 0.15, zc), (xb_, line(zc) + 0.92, zc), (xb_, line(za) + 0.92, za))
            ob = part(f"decor_{fl['name']}_{side}_Glass", "Glass_Clear", glass, keep_normals=True)
            orient_faces(ob, (1, 0, 0))

            def clad(bm, xb_=xb_, zz=zz):
                for za, zc in zip(zz, zz[1:]):
                    quad(bm, (xb_, line(za) - 0.05, za), (xb_, line(zc) - 0.05, zc), (xb_, line(zc) + 0.15, zc), (xb_, line(za) + 0.15, za))
                    if side == "out":                                                # the truss's side panel, down to the floor
                        quad(bm, (xb_ + (-0.07 if lane0 < 0 else 0.07), 0.0, za), (xb_ + (-0.07 if lane0 < 0 else 0.07), 0.0, zc),
                             (xb_ + (-0.07 if lane0 < 0 else 0.07), line(zc) - 0.05, zc), (xb_ + (-0.07 if lane0 < 0 else 0.07), line(za) - 0.05, za))
            part(f"decor_{fl['name']}_{side}_Skirt", "Metal_Steel", clad, keep_normals=True)

            def rail(bm, xb_=xb_, zz=zz):
                pts = [(xb_, line(z) + 1.0, z) for z in zz]
                for p, q in zip(pts, pts[1:]):
                    cyl(bm, p, q, 0.04, 0.04, 8, cap=False)
                for p, d_ in ((pts[0], 1), (pts[-1], -1)):                          # the newel: the rail turns down round a half circle
                    prev = p
                    for k in range(1, 9):
                        t = math.pi * k / 8
                        q = (xb_, p[1] - 0.2 * (1 - math.cos(t)), p[2] + d_ * 0.2 * math.sin(t))
                        cyl(bm, prev, q, 0.04, 0.04, 8, cap=False)
                        prev = q
            part(f"decor_{fl['name']}_{side}_Handrail", "Rubber_Black", rail, smooth=True)
        part(f"decor_{fl['name']}_CombFoot", "Metal_Steel", lambda bm: flat_decal(bm, lane0, lane1, zb, zb + 0.6, 0.006), keep_normals=True)
        part(f"decor_{fl['name']}_CombHead", "Metal_Steel", lambda bm: flat_decal(bm, lane0, lane1, zt - 0.6, zt, gy + 0.006), keep_normals=True)
    # between the escalators: the interdeck, a sloped steel cover at handrail height, and its side panels down to the floor
    for nm in ("decor_Escalator_Skirt", "decor_Escalator_Skirt_2", "decor_Escalator_Middle"):
        HANDLED.add(nm)
    zb, zt = 4.2, -3.0

    def interdeck(bm):
        zz = np.linspace(zb + 0.8, zt, 20)
        for za, zc in zip(zz, zz[1:]):
            ya, yc = min(gy, max(0.0, (zb - za) / (zb - zt) * gy)) + 0.98, min(gy, max(0.0, (zb - zc) / (zb - zt) * gy)) + 0.98
            quad(bm, (-1.32, ya, za), (1.32, ya, za), (1.32, yc, zc), (-1.32, yc, zc))
    ob = part("decor_Interdeck", "Metal_Steel", interdeck, keep_normals=True)
    orient_faces(ob, (0, 1, 0))
    part("decor_Escalator_Middle", "Metal_Steel", lambda bm: cube(bm, (-1.32, 0.0, 3.4), (1.32, 0.98, 4.2 + 0.8)))
    a_frame = ((0.0, 0.0, 5.6),)
    for (ax_, ay_, az_) in a_frame:
        part("decor_OutOfOrder_Frame", "Metal_Dark", lambda bm: [cyl(bm, (ax_ + sx * 0.3, 0.0, az_ + sz * 0.25), (ax_ + sx * 0.3, 0.9, az_), 0.012, 0.012, 5) for sx in (-1, 1) for sz in (-1, 1)])
        for sz in (-1, 1):
            ob = panel_at(f"decor_OutOfOrder_{sz}", "Poster_Art", (ax_, 0.5, az_ + sz * 0.12), (0, 0.27, sz), 0.55, 0.82, cell_uv(2))
    # shuttered shops below and on the gallery; their signs; the travel agent's blade sign
    for b in GB.boxes:
        nm = b["name"]
        if nm.startswith("Shutter_") and b["col"]:
            mn, mx = b["min"], b["max"]
            west = mn[0] < 0
            n = "+x" if west else "-x"
            plane = x0 if west else x1
            HANDLED.add(nm)
            a0, a1 = mn[2], mx[2]
            ob = part(nm, "Shutter_Metal", lambda bm: corrugated(bm, n, a0 + 0.06, a1 - 0.06, mn[1] + 0.06, mx[1] - 0.32, plane + (0.07 if west else -0.07)), keep_normals=True)
            orient_faces(ob, NV[n])

            def gear(bm, mn=mn, mx=mx):
                cube(bm, mn, (mx[0], mn[1] + 0.06, mx[2]))
                cube(bm, (mn[0], mx[1] - 0.32, mn[2]), (mx[0], mx[1], mx[2]))
                cube(bm, (mn[0], mn[1], mn[2]), (mx[0], mx[1], mn[2] + 0.06))
                cube(bm, (mn[0], mn[1], mx[2] - 0.06), (mx[0], mx[1], mx[2]))
            part(f"{nm}_Gear", "Metal_Dark", gear)
            part(f"{nm}_Frame", "Trim_Paint", lambda bm: [wall_box(bm, n, plane, a0 - 0.2, a0, mn[1], mx[1] + 0.85, 0.0, 0.04), wall_box(bm, n, plane, a1, a1 + 0.2, mn[1], mx[1] + 0.85, 0.0, 0.04)])
    for b in GB.boxes:
        nm = b["name"]
        if nm.startswith("decor_Sign_"):
            key = nm[len("decor_Sign_"):]
            mn, mx = b["min"], b["max"]
            west = mn[0] < 0
            n = "+x" if west else "-x"
            plane = x0 if west else x1
            part(nm + "_Board", "Metal_Dark", lambda bm: cube(bm, mn, mx))
            wall_panel(nm, "Sign_Paint", n, plane, (mn[2] + mx[2]) / 2, (mn[1] + mx[1]) / 2, 0.081, mx[2] - mn[2] - 0.08, mx[1] - mn[1] - 0.1, sign_uv(key))
    part("Blade_gallery", "Metal_Dark", lambda bm: [cube(bm, (x0, 6.55, -5.95), (x0 + 1.15, 7.25, -5.9)), cyl(bm, (x0, 7.35, -5.925), (x0 + 1.2, 7.35, -5.925), 0.015, 0.015, 6)])
    for sgn in (-1, 1):
        ob = panel_at(f"Blade_gallery_{sgn}", "Sign_Paint", (x0 + 0.6, 6.9, -5.925 + sgn * 0.0255), (0, 0, sgn), 1.1, 0.62, (0.27, sign_uv("gallery")[1], 0.73, sign_uv("gallery")[3]))
    for nm, a, key in (("G0", -5.0, "gal_n0"), ("G1", 5.0, "gal_n1")):
        shutter_flat(nm, "+z", z0, a, 3.0, gy, 2.55, key)
    for k, (a, cell) in enumerate(((-3.2, 0), (3.2, 1))):
        part(f"PosterFrame_{k}", "Metal_Dark", lambda bm: wall_box(bm, "+z", z0, a - 0.5, a + 0.5, 0.75, 2.35, 0.0, 0.03))
        wall_panel(f"Poster_{k}", "Poster_Art", "+z", z0, a, 1.55, 0.0305, 0.88, 1.4, cell_uv(cell))
    part("Directory_Frame", "Metal_Dark", lambda bm: wall_box(bm, "+x", x0, -1.3, 0.0, 0.85, 2.75, 0.0, 0.04))
    wall_panel("Directory_Face", "Poster_Art", "+x", x0, -0.65, 1.8, 0.0405, 1.2, 1.8, cell_uv(7))
    wall_panel("Notice_rails", "Poster_Art", "-z", z1, 2.4, 1.55, 0.004, 0.5, 0.75, cell_uv(3))
    wall_panel("Notice_touch", "Poster_Art", "+z", z0, 3.0, gy + 1.5, 0.004, 0.55, 0.55, cell_uv(11))
    # the planter under the gallery, the dead information kiosk, the gallery's bench
    planter(BOXL["Planter"], rng, tree=False, fern=True)
    kb = BOXL["Info_Kiosk"]
    mn, mx = kb["min"], kb["max"]
    with inside("Info_Kiosk"):
        part("Info_Kiosk", "Bench_Wood", lambda bm: cube(bm, mn, (mx[0], mx[1] - 0.05, mx[2])))
        part("Info_Kiosk_Top", "Trim_Paint", lambda bm: [cube(bm, (mn[0], mx[1] - 0.05, mn[2]), mx), cube(bm, (mn[0] + 0.05, 0.0, mn[2] - 0.0), (mx[0] - 0.05, 0.1, mn[2] + 0.02))])
    part("Info_Kiosk_Post", "Metal_Dark", lambda bm: [cyl(bm, (0.0, mx[1], (mn[2] + mx[2]) / 2), (0.0, 2.0, (mn[2] + mx[2]) / 2), 0.03, 0.03, 8),
                                                      cube(bm, (-0.72, 1.62, -0.24), (0.72, 2.12, -0.16)), cube(bm, (-0.3, mx[1], -0.5), (0.3, mx[1] + 0.35, -0.42))])
    for sgn, zc in ((1, -0.155), (-1, -0.245)):
        panel_at(f"Sign_info_{sgn}", "Sign_Paint", (0.0, 1.87, zc), (0, 0, sgn), 1.38, 0.42, sign_uv("info"))
    bench(BOXL["Gallery_Bench"], "-z")
    # light: floods high on the walls over the escalators (day), the emergency fittings on both levels (night)
    for k, (n, plane, a, tgt) in enumerate((("+x", x0, 2.0, (0.0, 1.0, 1.0)), ("-x", x1, 2.0, (0.0, 1.0, 1.0)), ("+x", x0, 9.0, (0.0, 0.0, 8.0)), ("-x", x1, 9.0, (0.0, 0.0, 8.0)),
                                            ("+x", x0, -5.0, (-3.0, gy, -7.0)), ("-x", x1, -10.5, (3.0, gy, -7.0)))):
        flood(f"F{k}", n, plane, a, 7.45, tgt, 900.0, 55.0)
    for k, (n, plane, a, y) in enumerate((("+x", x0, 1.5, 3.4), ("-x", x1, 1.5, 3.4), ("-z", z1, -3.5, 3.4), ("-z", z1, 3.5, 3.4), ("+z", z0, -6.0, 3.6),
                                          ("+x", x0, -4.0, 7.3), ("-x", x1, -11.0, 7.3), ("+z", z0, 1.8, 7.3))):
        emergency(f"E{k}", n, plane, a, y)


BUILD = {"scene_2909": scene_2909, "scene_3012": scene_3012, "scene_2991": scene_2991, "scene_3008": scene_3008}


# ---------------------------------------------------------------- lights, world, light sets
DAYSKY_W = 7.0                 # the day's soft sky light under each vault (W per m2 of the room): a large area facing down (the day set)
EMERG_W = 180.0                # each emergency head (the wings')
EXIT_W = 2.0


def add_lights():
    cols = {}
    for name in ("Lights_Day", "Lights_Night", "Lights_Always"):
        c = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(c)
        cols[name] = c

    def light(coll, name, kind, pos, energy, color, size, aim=None, cone=None):
        d = bpy.data.lights.new(name, kind)
        d.energy, d.color = energy, color
        d.shadow_soft_size = size
        ob = bpy.data.objects.new(name, d)
        ob.location = B(pos)
        if aim is not None:
            ob.rotation_euler = (B(aim) - B((0, 0, 0))).to_track_quat("-Z", "Y").to_euler()
        if cone:
            d.spot_size, d.spot_blend = math.radians(cone[0]), cone[1]
        cols[coll].objects.link(ob)
        return ob, d

    for k, (x0, x1, z0, z1, fy, h, corn, cv0) in ROOMS.items():
        ob, d = light("Lights_Day", f"DaySky_{k}", "AREA", ((x0 + x1) / 2, fy + h - 0.25, (z0 + z1) / 2), DAYSKY_W * (x1 - x0) * (z1 - z0), (0.92, 0.95, 1.0), 0.0, aim=(0, -1, 0))
        d.shape, d.size, d.size_y = "RECTANGLE", (x1 - x0) * 0.9, (z1 - z0) * 0.9
    for i, (p, dv, w, cone) in enumerate(SPOTS_DAY):
        light("Lights_Day", f"Spot_{i}", "SPOT", p, w, (1.0, 0.90, 0.76), 0.08, aim=dv, cone=(cone, 0.5))
    for i, (p, w, r) in enumerate(POINTS_DAY):
        light("Lights_Day", f"Point_{i}", "POINT", p, w, (1.0, 0.86, 0.66), r)
    for i, (p, aim, w_, h_, watts) in enumerate(AREAS_DAY):
        ob, d = light("Lights_Day", f"Trough_{i}", "AREA", p, watts, (1.0, 0.92, 0.80), 0.0, aim=aim)
        d.shape, d.size, d.size_y = "RECTANGLE", w_, h_
    for i, (p, dv) in enumerate(EMERG):
        light("Lights_Night", f"Emergency_{i}", "SPOT", tuple(Vector(p) + Vector(dv) * 0.045), EMERG_W, (0.86, 0.93, 1.0), 0.03, aim=dv, cone=(75, 0.45))
    for i, (p, nn) in enumerate(EXITS):
        ob, d = light("Lights_Always", f"Exit_{i}", "AREA", p, EXIT_W, (0.3, 1.0, 0.45), 0.0, aim=nn)
        d.shape, d.size, d.size_y = "RECTANGLE", 0.44, 0.16


def setup_world():
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("World")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
    bg.inputs["Strength"].default_value = 0.0


def set_emit(mname, strength):
    m = bpy.data.materials.get(mname)
    if m:
        m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = strength


def apply_light_set(name):
    """day: the day's lamps and sky light (Lamp_Emit on, Emergency_Emit off); night: the emergency heads alone (the mall locked); the painted
    sky glows in both; export: the toggled materials at the strength the page switches on and off, the sky at the page's strength."""
    day = name == "day"
    for c, on in (("Lights_Day", day), ("Lights_Night", name == "night"), ("Lights_Always", True)):
        if c in bpy.data.collections:
            bpy.data.collections[c].hide_render = not on
    set_emit("Lamp_Emit", LAMP_EMIT if name in ("day", "export") else 0.0)
    set_emit("Emergency_Emit", EMERG_EMIT if name in ("night", "export") else 0.0)
    set_emit("Sky_Glow", SKY_BAKE.get(name, SKY_SHOW))


def arrive():
    """The arrival from the wing (the way in)."""
    e = next(e for e in GB.empties if e["name"].startswith("Arrive_wing_"))
    return e["pos"], e["face"]


def ensure_marker():
    st = bpy.data.collections["Standins"]
    ob = bpy.data.objects.get("standin_arrival_marker")
    if ob is None:
        me = bpy.data.meshes.new("standin_arrival_marker")
        bm = bmesh.new()
        a, _ = arrive()
        cube(bm, (a[0] - 0.1, a[1], a[2] - 0.1), (a[0] + 0.1, a[1] + 0.2, a[2] + 0.1))
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("standin_arrival_marker", me)
        st.objects.link(ob)
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
    a, _ = arrive()
    want = [a[0], a[1] + 0.1, a[2]]
    print(f"AXES glTF centre {tuple(round(v, 3) for v in centre)}, game point {tuple(want)}")
    assert all(abs(centre[i] - want[i]) < 1e-4 for i in range(3)), "the exporter's axes disagree with (x, -z, y)"
    print("AXES PASS: game (x, y, z) = Blender (x, -z, y) = glTF (x, y, z)")
    os.remove(path)


def build_all():
    global ART, STANDIN, DOORS_C, LAYOUT_C
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.lights, bpy.data.cameras):
        for d in list(coll):
            coll.remove(d)
    for d in (IMG_CACHE, MATS, TILES, INSIDE):
        d.clear()
    for lst in (EMERG, EXITS, SPOTS_DAY, POINTS_DAY, AREAS_DAY):
        lst.clear()
    HANDLED.clear()
    sc = bpy.context.scene
    ART, STANDIN, DOORS_C, LAYOUT_C = (bpy.data.collections.new(n) for n in ("Art", "Standins", "Doors", "Layout"))
    for c in (ART, STANDIN, DOORS_C, LAYOUT_C):
        sc.collection.children.link(c)
    make_materials(make_generated())
    build_walls()
    build_vault()
    build_wall_trim()
    build_door_surrounds()
    BUILD[SCENE]()
    build_fallback()
    build_door_leaves()
    build_layout()
    add_lights()
    setup_world()
    apply_light_set("day")
    ensure_marker()
    LAYOUT_C.hide_render = True
    (stage_work() / "inside.json").write_text(json.dumps({k: sorted(v) for k, v in INSIDE.items()}))
    INSIDE_TXT.clear()
    INSIDE_TXT.append(json.dumps({k: sorted(v) for k, v in INSIDE.items()}))
    tris = sum(len(p.vertices) - 2 for o in ART.objects for p in o.data.polygons)
    print(f"ART {len(ART.objects)} objects, about {tris} triangles; {len(EMERG)} emergency heads, {len(SPOTS_DAY)} spots, {len(POINTS_DAY)} points, {len(AREAS_DAY)} troughs")


INSIDE_TXT = []


def save_inside_text():
    """The dressing-inside-a-solid map travels in the .blend as a text block (the cull at the bake reads it)."""
    if INSIDE_TXT:
        t = bpy.data.texts.get("inside.json") or bpy.data.texts.new("inside.json")
        t.clear()
        t.write(INSIDE_TXT[0])


def load_inside():
    t = bpy.data.texts.get("inside.json")
    if t:
        return json.loads(t.as_string())
    p = stage_work() / "inside.json"
    return json.loads(p.read_text()) if p.exists() else {}


# ---------------------------------------------------------------- layout file and the layout check
def stage_layout():
    import export_scene
    export_scene.write(SCENE, ROOT / f"world/{SCENE}.json")


def stage_check():
    import check_layout
    code = check_layout.main(["--scene", SCENE, "--collection", "Art"])
    print("CHECK_LAYOUT exit", code)
    # the mannequins' places and every link's two points: no art within 0.45 m that reaches from their floor to head height (the art of one of
    # the greybox's own standing solids, such as a bench or the carousel's deck and what stands on it, is the layout's, not the dressing's)
    parts = check_layout.blender_parts("Art")
    world = json.loads((ROOT / f"world/{SCENE}.json").read_text())
    pts = [(s["name"], s["position"]) for s in world["spots"] if s["kind"] == "mannequin"]
    pts += [(f"Link_{l['door']}.at", l["at"]) for l in world["links"]] + [(f"Link_{l['door']}.arrive", l["arrive"]) for l in world["links"]]
    stand = [c for c in world["colliders"] if c["max"][1] > 0.2 and c["min"][1] < 0.5 and "_Wall_" not in c["s"] and "Floor" not in c["s"]]
    for fl in GB.flights:                                   # a flight of steps is the layout's too: what stands on its lane
        st = [c for c in world["colliders"] if c["s"].startswith(f"Step_{fl['name']}_")]
        if st:
            stand.append({"s": fl["name"], "min": [min(c["min"][i] for c in st) for i in range(3)], "max": [max(c["max"][i] for c in st) for i in range(3)]})

    def on_layout(q):
        return any(c["min"][0] - 0.05 <= q["min"][0] and q["max"][0] <= c["max"][0] + 0.05 and c["min"][2] - 0.05 <= q["min"][2]
                   and q["max"][2] <= c["max"][2] + 0.05 for c in stand)
    bad = 0
    for name, p in pts:
        hit = [q["name"] for q in parts if not on_layout(q) and q["max"][1] - q["min"][1] > 0.03 and q["min"][1] < p[1] + 1.8 and q["max"][1] > p[1] + 0.02 and q["min"][0] - 0.45 < p[0] < q["max"][0] + 0.45
               and q["min"][2] - 0.45 < p[2] < q["max"][2] + 0.45]
        print(f"{'PASS' if not hit else 'FAIL'}  KEEP   {name} ({p[0]:.2f}, {p[1]:.2f}, {p[2]:.2f}): " + ("clear within 0.45 m" if not hit else "art " + ", ".join(hit)))
        bad += bool(hit)
    print(f"KEEP {'PASS' if not bad else 'FAIL'}: {len(pts) - bad} of {len(pts)} places clear")
    if code or bad:
        sys.exit(1)


# ---------------------------------------------------------------- bake
SHELL = ["Floor_Terrazzo", "Floor_Border", "Wall_Plaster", "Sky_Mural", "Ceiling_Paint", "Decal_Dust", "Court_Mosaic", "Floor_Cobble", "Floor_Pave", "Floor_Rubber"]
NO_BAKE = ("Lamp_Emit", "Emergency_Emit", "Sign_Exit", "Sky_Glow")
PAGES = [2048, 2048]
NIGHT_OFFSET = 2
UV_SCALE = {"Decal_Dust": 0.6}
TWO_SIDED = ("Cloth_Sheet", "Net_Mesh", "Glass_Clear", "Awning_Stripe", "Bunting")


def _inside(p, b, e=1e-4):
    return all(b["min"][i] + e < p[i] < b["max"][i] - e for i in range(3))


def cull(bm, mname, oname, inside_map):
    """Drop the faces nobody sees: a face whose point 1 cm in front lies inside a greybox solid (other than the ones the piece is built inside)
    or outside the scene's envelope (the outer skin, the joints between wall pieces, the faces flat on a floor or a wall, the backs of fronts);
    faces looking up from above SEEN[0] or down from below SEEN[1] (two-sided sheets, nets and glass aside)."""
    ign = set(inside_map.get(oname, ()))
    boxes = [b for b in SOLIDS if b["name"] not in ign]
    bad = []
    for f in bm.faces:
        cw, nw = f.calc_center_median(), f.normal
        g = (cw.x, cw.z, -cw.y)
        gn = (nw.x, nw.z, -nw.y)
        q = (g[0] + gn[0] * 0.01, g[1] + gn[1] * 0.01, g[2] + gn[2] * 0.01)
        # the face is hidden if points spread over it (the centre, and four points 70 % of the way to its corners) all lie, 1 cm in front,
        # inside greybox solids: a long wall behind a row of fronts is hidden though its centre sits on the seam between two of them
        pts = [q] + [(c.x * 0.7 + cw.x * 0.3 + nw.x * 0.01, c.z * 0.7 + cw.z * 0.3 + nw.z * 0.01, -(c.y * 0.7 + cw.y * 0.3) - nw.y * 0.01)
                     for c in [v.co for v in f.verts][:4]] if len(f.verts) >= 4 else [q]
        out = not all(ENV[i][0] < q[i] < ENV[i][1] for i in range(3)) or any(_inside(q, b) for b in boxes) or             (len(pts) > 1 and all(any(_inside(p_, b) for b in boxes) for p_ in pts[1:]))
        if not out and mname not in TWO_SIDED and mname not in NO_BAKE:
            out = (gn[1] > 0.5 and g[1] > SEEN[0]) or (gn[1] < -0.5 and g[1] < SEEN[1])
        if out:
            bad.append(f)
    bmesh.ops.delete(bm, geom=bad, context="FACES")


def make_export_objects():
    art = bpy.data.collections["Art"]
    inside_map = load_inside()
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
        tmp.normal_update()
        cull(tmp, mname, ob.name, inside_map)
        me = bpy.data.meshes.new("tmp")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    out = {}
    for mname, bm in by_mat.items():
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        if not bm.faces:
            bm.free()
            continue
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
    """One atlas for `objs` (entrance's): smart-project islands at equal texel density (UV_SCALE shrinks a few), packed with MARGIN_PX."""
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
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        sc = UV_SCALE.get(o.name)
        if sc:
            d = o.data.uv_layers["lightmap"].data
            us = np.array([x.uv for x in d]) * sc
            d.foreach_set("uv", us.ravel())
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    best = None
    for shape in ("CONCAVE", "CONVEX", "AABB"):
        bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN_PX / page, shape_method=shape)
        bpy.ops.object.mode_set(mode="OBJECT")
        au_ = sum(uv_area(o, "lightmap") for o in objs)
        print(f"  pack {shape}: {au_:.4f} of the page")
        if best is None or au_ > best[0] * 1.02:
            best = (au_, shape, {o.name: np.array([x.uv for x in o.data.uv_layers["lightmap"].data]) for o in objs})
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in objs:
        o.data.uv_layers["lightmap"].data.foreach_set("uv", best[2][o.name].ravel())
    print(f"  kept {best[1]}")
    plain = [o for o in objs if o.name not in UV_SCALE]
    a3 = sum(area3d(o) for o in plain)
    au = sum(uv_area(o, "lightmap") for o in plain)
    dens = page * math.sqrt(au / a3)
    small = {o.name: round(page * math.sqrt(uv_area(o, "lightmap") / max(1e-9, area3d(o))), 1) for o in objs if o.name in UV_SCALE}
    print(f"  page {page}: {a3:.1f} m2, {dens:.1f} px/m; scaled: {small}")
    return page, dens, small


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
    path = str(stage_work() / "dn.exr")
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


def bake_set(n, objs, S, light_set, samples):
    apply_light_set(light_set)
    bpy.context.scene.cycles.samples = samples
    img = bpy.data.images.new(f"LM_{n}_{light_set}", S, S, alpha=False, float_buffer=True)
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
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=MARGIN_PX, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
    for o in objs:
        for slot in o.material_slots:
            nt = slot.material.node_tree
            for nd in [nd for nd in nt.nodes if nd.name.startswith("BAKE_TARGET")]:
                nt.nodes.remove(nd)
    a = denoise_image(img, S)
    bpy.data.images.remove(img)
    return a[..., :3].copy()


def encode_map(rgb, light_set, S, idx):
    Gc, Cc = CURVE[light_set]
    tex = Gc * rgb / (Cc + Gc * rgb)
    out = np.ones((S, S, 4), np.float32)
    out[..., :3] = srgb_encode(tex)
    png = bpy.data.images.new(f"LM_{idx}_png", S, S, alpha=False)
    png.colorspace_settings.name = "Non-Color"
    png.pixels.foreach_set(out.ravel())
    png.filepath_raw = str(stage_work() / f"{SCENE}_{idx}.png")
    png.file_format = "PNG"
    png.save()
    bpy.data.images.remove(png)


def stage_bake():
    import time
    stage_work()
    exp = make_export_objects()
    leaves = sorted(bpy.data.collections["Doors"].objects, key=lambda o: o.name)
    bpy.data.collections["Art"].hide_render = True
    bpy.data.collections["Art"].hide_viewport = True
    setup_cycles(SAMPLES, bake=True)
    groups = [[m for m in SHELL if m in exp], [m for m in exp if m not in SHELL and m not in NO_BAKE]]
    report = {}
    for n, mats in enumerate(groups):
        objs = [exp[m] for m in mats] + (leaves if n == 1 else [])
        print(f"lightmap {n}: {[o.name for o in objs]}")
        S, dens, small = lightmap_uv(objs, PAGES[n])
        for light_set, idx, samples in (("day", n, SAMPLES), ("night", n + NIGHT_OFFSET, NIGHT_SAMPLES)):
            t0 = time.time()
            rgb = bake_set(n, objs, S, light_set, samples)
            peak = rgb.max(axis=2)
            sel = peak > 1e-5
            pc = np.percentile(peak[sel], [50, 90, 99, 99.5, 100]) if sel.any() else [1.0] * 5
            print(f"  {light_set} texel percentiles p50 p90 p99 p99.5 max:", [round(float(v), 4) for v in pc])
            encode_map(rgb, light_set, S, idx)
            np.save(stage_work() / f"{SCENE}_{idx}_raw.npy", rgb.astype(np.float16))
            report[idx] = {"map": n, "set": light_set, "size": S, "curve_G_C": list(CURVE[light_set]), "px_per_m": round(dens, 1), "px_per_m_scaled": small,
                           "p50_p90_p99_p995_max": [round(float(v), 4) for v in pc], "samples": samples, "device": bpy.context.scene.cycles.device,
                           "seconds": round(time.time() - t0), "materials": mats + ([o.name for o in leaves] if n == 1 else [])}
            print("  baked", report[idx])
    (stage_work() / "lightmaps.json").write_text(json.dumps(report, indent=1))
    apply_light_set("day")
    bpy.data.collections["Art"].hide_render = False
    bpy.data.collections["Art"].hide_viewport = False
    bpy.data.collections["Export"].hide_render = True
    bpy.data.collections["Export"].hide_viewport = True
    save_blend()


# ---------------------------------------------------------------- brightness: how the page shows the maps (the hotel lobby's shoulder)
# The page draws a baked material unlit, no tone mapping: texture x base colour x texel x intensity / pi. The bake's light L is written with a
# shoulder, texel = G L / (C + G L), and intensity = pi C: the page shows texture x G L where the light is ordinary and rolls off toward texture x C
# under a lamp, never clipping. CAP lowers one bright material.
CURVES = {"scene_2909": {"day": (2.4, 1.3), "night": (3.0, 1.1)}, "scene_3012": {"day": (2.4, 1.3), "night": (3.0, 1.1)},
          "scene_2991": {"day": (2.4, 1.3), "night": (3.0, 1.1)}, "scene_3008": {"day": (2.4, 1.3), "night": (3.0, 1.1)}}
CURVE = dict(CURVES[SCENE])
CAP = {"day": {}, "night": {}}
if SCENE == "scene_2991":
    CAP["day"]["Sign_Paint"] = 0.72                 # the SOFT PLAY and CAROUSEL boards under the floods


def set_intensities():
    rep = json.loads((stage_work() / "lightmaps.json").read_text())
    for idx, r in rep.items():
        idx = int(idx)
        st = r["set"]
        key, kkey = ("lightmap", "lightmap_intensity") if st == "day" else ("lightmap_night", "lightmap_night_intensity")
        for nm in r["materials"]:
            ob = bpy.data.objects.get(nm)
            mats = [bpy.data.materials.get(nm)] if bpy.data.materials.get(nm) else ([s.material for s in ob.material_slots] if ob else [])
            for m in mats:
                if m is None:
                    continue
                m[key] = LM_URL.format(idx)
                m[kkey] = round(math.pi * CURVE[st][1] * CAP[st].get(m.name, 1.0), 4)


def scrub_ui_paths():
    for sc in bpy.data.screens:
        for a in sc.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"_" * 1000
                    sp.params.directory = b"//"


KEEP_PROPS = {"lightmap", "lightmap_intensity", "lightmap_night", "lightmap_night_intensity"}
LAYOUT_PREFIX = ("DoorLeaf_", "Spot_", "Marker_", "Link_", "Arrive_")
SYS_KEEP = ("cycles", "eevee")


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private(keep_layout=True):
    """The .blend, the GLB and the stills are public: strip other add-ons' custom properties, make image paths relative, clear the operators'
    remembered paths, turn every stamp off (the lobby's)."""
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
                    if kind == "objects" and st is idb and keep_layout and idb.name.startswith(LAYOUT_PREFIX):
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
        for pf in im.packed_files:
            if pf.filepath and not pf.filepath.startswith("//"):
                try:
                    rel = "//" + os.path.relpath(Path(bpy.path.abspath(pf.filepath)), base).replace("\\", "/")
                except ValueError:
                    rel = "//" + Path(pf.filepath).name
                set_path(pf, "filepath", rel)
        if im.packed_file or im.source != "FILE" or not im.filepath:
            continue
        p = Path(bpy.path.abspath(im.filepath))
        try:
            rel = "//" + os.path.relpath(p, base).replace("\\", "/")
        except ValueError:
            rel = "//" + p.name
        set_path(im, "filepath", rel)
    scrub_ui_paths()
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
                except Exception as e:
                    print("  could not clear", op, attr, e)


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    save_inside_text()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
    scrub_private()
    bpy.ops.wm.save_mainfile()


# ---------------------------------------------------------------- export
def stage_export():
    set_intensities()
    exp = bpy.data.collections["Export"]
    exp.hide_viewport = exp.hide_render = False
    bpy.data.collections["Art"].hide_viewport = True
    leaves = sorted(bpy.data.collections["Doors"].objects, key=lambda o: o.name)
    stash = {o.name: {k: o[k] for k in o.keys()} for o in leaves}
    for o in leaves:
        for k in list(o.keys()):
            del o[k]
    apply_light_set("export")
    bpy.ops.object.select_all(action="DESELECT")
    for o in list(exp.objects) + leaves:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(iter(exp.objects))
    raw = stage_work() / f"{SCENE}_raw.glb"
    scrub_private()
    bpy.ops.export_scene.gltf(filepath=str(raw), export_format="GLB", use_selection=True, export_extras=True, export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT", export_image_format="AUTO",
                              export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False, export_animations=False)
    for o in leaves:
        for k, v in stash[o.name].items():
            o[k] = v
    print("EXPORTED", raw, raw.stat().st_size)
    apply_light_set("day")
    bpy.data.collections["Art"].hide_viewport = False
    exp.hide_viewport = exp.hide_render = True
    save_blend()


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
    cam.clip_start, cam.clip_end = 0.05, 200
    ob = bpy.data.objects.new(name, cam)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = B(loc)
    if target is not None:
        ob.rotation_euler = (B(target) - B(loc)).to_track_quat("-Z", "Y").to_euler()
    else:
        ob.rotation_euler = (0, 0, 0)
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


SHOTS = {   # (camera, target, vertical fov): 2_wide, 3_detail, 4_more, in the scene's frame
    "scene_2909": [((-11.3, 2.3, 2.0), (6.0, 0.9, -2.5), 78.0), ((3.6, 1.3, 4.6), (0.0, 0.6, 0.0), 62.0), ((0.0, 1.5, 9.5), (0.0, 7.0, -5.0), 80.0)],
    "scene_3012": [((14.4, 2.2, -2.6), (-10.0, 1.6, 1.4), 74.0), ((-5.2, 1.6, 2.4), (-9.6, 2.3, -5.4), 66.0), ((-2.0, 1.4, 0.0), (3.0, 6.0, 0.0), 82.0)],
    "scene_2991": [((15.0, 2.3, 5.6), (-6.0, 1.4, -2.0), 74.0), ((3.6, 1.5, 5.2), (9.0, 1.6, 0.0), 64.0), ((-5.0, 1.5, 3.0), (-11.0, 1.3, -4.0), 66.0)],
    "scene_3008": [((6.6, 6.2, -11.0), (-1.5, 1.6, 6.0), 76.0), ((3.9, 1.5, 7.6), (-1.0, 1.8, 1.0), 64.0), ((0.0, 1.5, 11.0), (0.0, 8.0, -4.0), 82.0)],
}[SCENE]


def stage_render():
    sc = bpy.context.scene
    STILLS.mkdir(parents=True, exist_ok=True)
    scrub_private()
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
        bpy.data.collections["Export"].hide_viewport = True
    bpy.data.collections["Layout"].hide_render = True
    light_set = arg("--set", "day")
    apply_light_set(light_set)
    setup_cycles(arg("--render-samples", 128, int))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = arg("--noise", 0.03, float)
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = arg("--view", "AgX")
    if sc.view_settings.view_transform == "AgX":
        try:
            sc.view_settings.look = "AgX - Medium High Contrast"
        except TypeError:
            pass
    expo = arg("--exposure", 0.0, float)
    which = arg("--only", "all")
    for o in [o for o in bpy.data.objects if o.type == "CAMERA"]:
        bpy.data.objects.remove(o)
    a, f = arrive()
    shots = {"1_arrival": look_cam("arrival", (a[0], a[1] + 1.6, a[2]), (a[0] + f[0] * 3, a[1] + 1.75, a[2] + f[1] * 3), 75.0),
             "2_wide": look_cam("wide", *SHOTS[0]), "3_detail": look_cam("detail", *SHOTS[1]), "4_more": look_cam("more", *SHOTS[2])}
    x0, x1, z0, z1, ytop = ENV[0][0], ENV[0][1], ENV[2][0], ENV[2][1], ENV[1][1]
    plan = look_cam("plan", ((x0 + x1) / 2, ytop + 10, (z0 + z1) / 2), None, ortho=max(x1 - x0, (z1 - z0) * 1920 / 1080) + 0.6)
    arts = list(bpy.data.collections["Art"].objects) + list(bpy.data.collections["Doors"].objects)
    todo = [(k, v, (1920, 1080)) for k, v in shots.items()] + [("5_plan", plan, (1920, 1080))]
    suffix = "" if light_set == "day" else "_" + light_set
    for key, cam, (w, h) in todo:
        if which not in ("all", key) and not (which == "review" and key in ("1_arrival", "2_wide", "3_detail")):
            continue
        sc.camera = cam
        sc.view_settings.exposure = expo + (0.6 if key == "5_plan" else 0.0)
        for o in arts:
            o.visible_camera = True
        if key == "5_plan":
            for o in arts:
                if o.name.endswith("_Ceiling") or "_Vault" in o.name or o.name.startswith(("decor_Sky_Cove", "decor_Bunting", "decor_Carousel_Canopy", "decor_Carousel_Crown",
                                                                                            "decor_Bandstand_Roof", "decor_Bandstand_Fringe", "decor_SoftPlay_Net",
                                                                                            "decor_Awning", "decor_Balcony", "decor_Lamp_Post")):
                    o.visible_camera = False
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, arg("--scale", 100, int)
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 90
        to_docs = key in ("1_arrival", "2_wide", "3_detail") and light_set == "day" and not arg("--work-stills")
        path = STILLS / f"{key}.jpg" if to_docs else stage_work() / f"{key}{suffix}.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        q = 90
        while path.stat().st_size > 400_000 and q > 40 and to_docs:
            q -= 5
            sc.render.image_settings.quality = q
            bpy.data.images["Render Result"].save_render(str(path), scene=sc)
        strip_jpeg_comments(path)
        print("STILL", key, path.name, path.stat().st_size, "q", q)
    for o in arts:
        o.visible_camera = True
    apply_light_set("day")


if __name__ == "__main__":
    ST = set(STAGE.split(","))
    if ST & {"art", "all"}:
        build_all()
        save_blend()
    if ST & {"layout", "art", "all"}:
        stage_layout()
    if ST & {"check", "all"}:
        stage_check()
    if ST & {"bake", "all"}:
        stage_bake()
    if ST & {"export", "all"}:
        stage_export()
    if ST & {"axes", "all"}:
        stage_axes()
    if ST & {"render", "all"}:
        stage_render()
