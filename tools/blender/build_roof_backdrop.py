"""Renders the hotel roof's skyline backdrops (docs/BLENDER.md R3; docs/BLENDER_AREAS.md section 1: "the city skyline at night"): the city round the
apartment tower, as two 4096 x 2048 equirect panoramas from the roof's centre, world/backdrops/roof_night.webp and roof_day.webp.

Re-runnable, from the repo root:

    blender -b --factory-startup --python tools/blender/build_roof_backdrop.py -- --stage backdrops --work <work> [--bd-samples 128]
        (builds the city in a new scene, runs the orientation self-check, renders <work>/backdrop_night.png and backdrop_day.png)
    python tools/blender/build_roof_backdrop.py --stage pack-backdrops --work <work>    (the PNGs -> WebP, each at most 1 MB)
    python tools/blender/build_roof_backdrop.py --stage previews --work <work>          (flat views out of each panorama -> <work>/view_<set>_<dir>.jpg)

Where from: the roof is the top of the street's apartment tower (shared/city.js, BUILDINGS `tower`: x -28 to -8, z -30 to -8, 38 m high), so the
pictures are taken from the tower's middle (-18, -19), at the roof's floor plus eye height (y 38 + 1.55), in the street's own axes. Hallam Row and
its buildings are read from shared/city.js (no coordinate typed in): the road, the sidewalks, the lamp posts and the eleven buildings, each with its
own height and colour. Round them the city is procedural (seeded numpy): blocks of low and mid-rise buildings, rising with distance, high-rises
scattered through it and a downtown of towers to the north-north-east, out to 4 km, hazing with distance. The roof itself (the playable area) is not in the scene.

Night: a deep sky warmed by the city's glow low down, stars, the moon in the south-east (bearing 135 degrees, 34 degrees up: the roof's bake lights
the roof from there), lit windows (about one in ten, warm and cool), the street lamps, red beacons on the tall towers. Day: a clear, hazy sky,
the sun in the south-south-west, the windows dark glass.

Axes: a game point (x, y, z) is Blender (x, -z, y). The picture's middle column faces north (game -z, Blender +Y) and its right-hand side faces
east (game +x, Blender +X); `orientation_test` checks this before the renders. Everything is procedural: no image, model or HDRI from anywhere.
"""
import json
import math
import os
import re
import sys
from pathlib import Path

import numpy as np

try:
    import bpy
    import bmesh
    from mathutils import Vector
except ImportError:                       # the pack and previews stages run in plain Python (numpy and Pillow)
    bpy = None

ROOT = Path(__file__).resolve().parents[2]
SCENE = "roof"
W, H = 4096, 2048
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else (sys.argv[1:] if bpy is None else [])


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "backdrops")
DEVICE = arg("--device", "auto")
MOON_BEARING, MOON_ELEV = 135.0, 34.0              # as tools/blender/build_hotel_floor3_roof.py lights the roof
SUN_BEARING, SUN_ELEV = 200.0, 38.0


def stage_work():
    d = Path(arg("--work", str(Path(os.environ.get("TEMP", "/tmp")) / "farway_roof_backdrop")))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- the street, from shared/city.js
def city():
    src = (ROOT / "shared/city.js").read_text(encoding="utf-8")
    def num(s):
        return float(int(s, 16)) if s.startswith("0x") else float(s)
    blds = []
    for m in re.finditer(r"\{id: \"(\w+)\", side: \"(\w)\", z0: (-?[\d.]+), z1: (-?[\d.]+), depth: ([\d.]+), h: ([\d.]+), color: (0x[0-9a-fA-F]+)", src):
        i, side, z0, z1, depth, h, col = m.groups()
        blds.append({"id": i, "side": side, "z0": num(z0), "z1": num(z1), "depth": num(depth), "h": num(h), "color": int(col, 16)})
    g = lambda name: re.search(name + r"\s*=\s*([^;]+);", src).group(1)
    road = {k: num(v) for k, v in re.findall(r"(\w+): (-?[\d.]+)", g(r"export const ROAD"))}
    walk = num(re.search(r"WALK = ([\d.]+)", src).group(1))
    front = num(re.search(r"FRONT = ([\d.]+)", src).group(1))
    lamps = [num(v) for v in re.search(r"LAMP_ZS = \[([^\]]+)\]", src).group(1).split(",")]
    world = {k: num(v) for k, v in re.findall(r"(\w+): (-?[\d.]+)", re.search(r"WORLD = \{([^}]+)\}", src).group(1))}
    assert blds and any(b["id"] == "tower" for b in blds), "shared/city.js BUILDINGS not found"
    return {"buildings": blds, "road": road, "walk": walk, "front": front, "lamps": lamps, "world": world}


CITY = city()
TOWER = next(b for b in CITY["buildings"] if b["id"] == "tower")


def bbox(b):
    x = -CITY["front"] if b["side"] == "w" else CITY["front"]
    x0, x1 = (x - b["depth"], x) if b["side"] == "w" else (x, x + b["depth"])
    return x0, x1, min(b["z0"], b["z1"]), max(b["z0"], b["z1"])


_tx0, _tx1, _tz0, _tz1 = bbox(TOWER)
CX, CZ = (_tx0 + _tx1) / 2, (_tz0 + _tz1) / 2
CY = TOWER["h"] + 1.55


def stage_pack_backdrops():
    """The backdrop PNGs -> world/backdrops/roof_night.webp and roof_day.webp (4096 x 2048), as good a WebP as fits in 1 MB."""
    from PIL import Image
    work = stage_work()
    out = ROOT / "world/backdrops"
    out.mkdir(parents=True, exist_ok=True)
    for k in ("night", "day"):
        im = Image.open(work / f"backdrop_{k}.png").convert("RGB")
        assert im.size == (W, H), im.size
        dst = out / f"{SCENE}_{k}.webp"
        for q in (95, 92, 90, 88, 85, 82, 80, 77, 74, 70, 66, 62, 58, 54, 50):
            im.save(dst, "WEBP", quality=q, method=6)
            if dst.stat().st_size <= 1_000_000:
                break
        print(f"{dst.relative_to(ROOT).as_posix()}  {im.size}  q{q}  {dst.stat().st_size / 1e3:.0f} KB")


def equirect_view(pano, yaw_deg, hfov=90.0, size=(960, 540), pitch_deg=4.0):
    """A flat (rectilinear) view out of an equirect picture whose middle column is north and right-hand side east. yaw 0 north, 90 east."""
    a = np.asarray(pano, np.float32)
    Hh, Ww = a.shape[:2]
    w, h = size
    f = (w / 2) / math.tan(math.radians(hfov) / 2)
    xs, ys = np.meshgrid(np.arange(w) - w / 2 + 0.5, h / 2 - np.arange(h) - 0.5)
    d = np.stack([xs, ys, np.full_like(xs, f)], -1)
    p = math.radians(pitch_deg)
    y2 = d[..., 1] * math.cos(p) + d[..., 2] * math.sin(p)
    z2 = -d[..., 1] * math.sin(p) + d[..., 2] * math.cos(p)
    lon = np.arctan2(d[..., 0], z2) + math.radians(yaw_deg)
    lat = np.arctan2(y2, np.hypot(d[..., 0], z2))
    u = (0.5 + lon / (2 * math.pi)) % 1.0 * Ww
    v = np.clip((0.5 - lat / math.pi) * Hh, 0, Hh - 1)
    u0 = np.floor(u).astype(int) % Ww
    v0 = np.floor(v).astype(int)
    u1, v1 = (u0 + 1) % Ww, np.minimum(v0 + 1, Hh - 1)
    fu, fv = (u - np.floor(u))[..., None], (v - v0)[..., None]
    out = (a[v0, u0] * (1 - fu) + a[v0, u1] * fu) * (1 - fv) + (a[v1, u0] * (1 - fu) + a[v1, u1] * fu) * fv
    return out.clip(0, 255).astype(np.uint8)


def stage_previews():
    from PIL import Image
    work = stage_work()
    for k in ("night", "day"):
        src = ROOT / f"world/backdrops/{SCENE}_{k}.webp"
        pano = Image.open(src if src.exists() else work / f"backdrop_{k}.png").convert("RGB")
        for name, yaw in (("north", 0), ("east", 90), ("south", 180), ("west", 270)):
            v = Image.fromarray(equirect_view(pano, yaw, hfov=90.0, size=(960, 540), pitch_deg=2.0))
            v.save(work / f"view_{k}_{name}.jpg", quality=86)
    print("PREVIEWS", work)


if bpy is None:
    {"pack-backdrops": stage_pack_backdrops, "previews": stage_previews}.get(STAGE, lambda: print("without Blender only pack-backdrops and previews run"))()
    sys.exit(0)


# ================================================================ Blender from here on
def B(p):
    return Vector((p[0], -p[2], p[1]))


def setup_cycles(samples):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = samples
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces, cy.transmission_bounces = 6, 3, 2, 2
    cy.use_denoising = True
    cy.denoiser = "OPENIMAGEDENOISE"
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.02
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


def new_nodes(idb):
    try:
        idb.use_nodes = True
    except Exception:
        pass
    nt = idb.node_tree
    nt.nodes.clear()
    return nt


def pano_camera():
    cam = bpy.data.cameras.get("pano") or bpy.data.cameras.new("pano")
    cam.type = "PANO"
    for owner in (cam, getattr(cam, "cycles", None)):
        if owner is not None and hasattr(owner, "panorama_type"):
            owner.panorama_type = "EQUIRECTANGULAR"
    cam.clip_start, cam.clip_end = 0.1, 60000
    ob = bpy.data.objects.get("pano") or bpy.data.objects.new("pano", cam)
    if ob.name not in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.link(ob)
    ob.location = B((CX, CY, CZ))
    ob.rotation_euler = (math.pi / 2, 0, 0)                    # looking north (+Y), its right is east (+X)
    bpy.context.scene.camera = ob
    return ob


def emit_material(name, col, strength):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = new_nodes(m)
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*col, 1)
    e.inputs["Strength"].default_value = strength
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0], o.inputs["Surface"])
    return m


def orientation_test(hide):
    """Three glowing markers far out (red east, green north, blue south) on a black sky, rendered small: the picture's middle column must be green,
    three quarters across red, and the edges blue (docs/BLENDER.md R3: the middle faces north, the right east)."""
    import bmesh as _bm
    sc = bpy.context.scene
    tmp = bpy.data.collections.new("OrientTest")
    sc.collection.children.link(tmp)
    for name, p, col in (("east", (CX + 400, CY, CZ), (1, 0, 0)), ("north", (CX, CY, CZ - 400), (0, 1, 0)), ("south", (CX, CY, CZ + 400), (0, 0, 1))):
        bm = _bm.new()
        _bm.ops.create_cube(bm, size=80.0)
        _bm.ops.translate(bm, vec=B(p), verts=bm.verts)
        me = bpy.data.meshes.new(f"orient_{name}")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(emit_material(f"orient_{name}", col, 5.0))
        tmp.objects.link(bpy.data.objects.new(f"orient_{name}", me))
    w = bpy.data.worlds.new("black")
    nt = new_nodes(w)
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 0.0
    nt.links.new(bg.outputs[0], nt.nodes.new("ShaderNodeOutputWorld").inputs["Surface"])
    keep_world = sc.world
    sc.world = w
    for c in hide:
        c.hide_render = True
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 256, 128, 100
    keep = sc.cycles.samples
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
    sc.world = keep_world
    bpy.data.worlds.remove(w)
    sc.cycles.samples = keep
    for c in hide:
        c.hide_render = False


# ---------------------------------------------------------------- the city: one mesh of boxes, each face with its building's attributes
class Boxes:
    """Many boxes in one mesh: per face a material slot (0 facade, 1 roof), and attributes `bid` (the building's random number), `tint` (its colour),
    `lit` (the share of its windows lit at night); UVs in metres along the facade (u) and up it (v), for the window grid."""
    def __init__(s):
        s.v, s.f, s.uv, s.slot, s.bid, s.tint, s.lit = [], [], [], [], [], [], []

    def box(s, x0, x1, z0, z1, y0, y1, bid, tint, lit, top=True):
        def q(pts, uvs, slot):
            k = len(s.v)
            s.v += [tuple(B(p)) for p in pts]
            s.f.append((k, k + 1, k + 2, k + 3))
            s.uv.append(uvs)
            s.slot.append(slot)
            s.bid.append(bid)
            s.tint.append(tint)
            s.lit.append(lit)
        h = y1 - y0
        sides = [((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), x1 - x0),     # south face (+z), seen from the south
                 ((x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0), x1 - x0),     # north
                 ((x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1), z1 - z0),     # east
                 ((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0), z1 - z0)]     # west
        off = (bid * 97.0) % 3.0
        for a, b, c, d, ln in sides:
            q([a, b, c, d], [(off, y0), (off + ln, y0), (off + ln, y0 + h), (off, y0 + h)], 0)
        if top:
            q([(x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0)], [(x0, z1), (x1, z1), (x1, z0), (x0, z0)], 1)

    def done(s, name, coll, mats):
        me = bpy.data.meshes.new(name)
        me.from_pydata(s.v, [], s.f)
        me.update()
        uvl = me.uv_layers.new(name="UVMap")
        uvl.data.foreach_set("uv", np.array([c for uvs in s.uv for c in uvs], np.float32).ravel())
        for nm, vals, typ in (("bid", s.bid, "FLOAT"), ("lit", s.lit, "FLOAT")):
            at = me.attributes.new(nm, typ, "FACE")
            at.data.foreach_set("value", np.array(vals, np.float32))
        at = me.attributes.new("tint", "FLOAT_COLOR", "FACE")
        at.data.foreach_set("color", np.array([(*t, 1.0) for t in s.tint], np.float32).ravel())
        for m in mats:
            me.materials.append(m)
        me.polygons.foreach_set("material_index", np.array(s.slot, np.int32))
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)
        return ob


PALETTE = [(0.42, 0.40, 0.38), (0.55, 0.50, 0.44), (0.36, 0.30, 0.27), (0.50, 0.36, 0.30), (0.30, 0.33, 0.37), (0.60, 0.58, 0.54),
           (0.26, 0.28, 0.30), (0.46, 0.44, 0.40), (0.40, 0.30, 0.24), (0.52, 0.54, 0.56)]


def build_city(coll, rng):
    bx = Boxes()
    n_street = 0
    for b in CITY["buildings"]:                                             # Hallam Row: the street's own buildings
        if b["id"] == "tower":
            continue
        x0, x1, z0, z1 = bbox(b)
        c = b["color"]
        tint = ((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255)
        tint = tuple(v ** 2.2 for v in tint)
        bx.box(x0, x1, z0, z1, 0.0, b["h"], rng.random(), tint, 0.06 + 0.08 * rng.random())       # the stores are shut at night
        n_street += 1
    # the city beyond: a street grid of blocks (88 m: 72 m of buildings, 16 m of street), each block cut into lots
    down = np.array([CX + 420.0, CZ - 1250.0])                              # downtown: north-north-east of the tower, 1.3 km off
    keep_out = [bbox(b) for b in CITY["buildings"]]                         # Hallam Row's own buildings (and the tower) stand where they are
    road = CITY["road"]
    n, tall = 0, []
    R = 4000.0
    for gx in np.arange(-R, R, 88.0):
        for gz in np.arange(-R, R, 88.0):
            bx0, bz0 = gx + 8.0, gz + 8.0
            mid = np.array([bx0 + 36, bz0 + 36])
            d = math.hypot(mid[0] - CX, mid[1] - CZ)
            if d > R or d < 30:
                continue
            dd = math.hypot(*(mid - down))
            lot = 18.0 if d < 900 else 24.0 if d < 2000 else 36.0
            for lx in np.arange(bx0, bx0 + 72 - 1e-6, lot):
                for lz in np.arange(bz0, bz0 + 72 - 1e-6, lot):
                    x0, z0 = lx + rng.uniform(0.5, 2.5), lz + rng.uniform(0.5, 2.5)
                    x1, z1 = lx + lot - rng.uniform(0.5, 2.5), lz + lot - rng.uniform(0.5, 2.5)
                    if any(x1 > a - 3 and x0 < b_ + 3 and z1 > c - 3 and z0 < e + 3 for a, b_, c, e in keep_out):
                        continue                                            # a building of the street's own
                    if x1 > -CITY["front"] - 1 and x0 < CITY["front"] + 1 and z1 > road["z0"] - 20 and z0 < road["z1"] + 20:
                        continue                                            # the road and its sidewalks
                    if rng.random() < 0.08:
                        continue                                            # a gap: a car park, a yard
                    near = min(1.0, max(0.0, (d - 220.0) / 700.0))           # low streets round the tower, rising with distance
                    base = 7.0 + (6.0 + 18.0 * near) * rng.random() ** 2
                    core = math.exp(-(dd / 800.0) ** 2)
                    h = base + near * 34.0 * rng.random() ** 3 + core * 280.0 * rng.random() ** 1.6
                    if d > 350 and rng.random() < 0.012 * near:
                        h += 45 + 110 * rng.random() ** 1.5                  # high-rises out in the city
                    h = round(h / 3.4) * 3.4 + 1.2
                    tint = PALETTE[int(rng.integers(len(PALETTE)))]
                    j = 0.85 + 0.3 * rng.random()
                    tint = tuple(min(1.0, v * j) for v in tint)
                    office = h > 60
                    bid = rng.random()
                    bx.box(x0, x1, z0, z1, 0.0, h, bid, tint, (0.16 if office else 0.08) + 0.12 * rng.random() ** 2)
                    if h > 45 and rng.random() < 0.5:                         # a setback crown
                        ix, iz = (x1 - x0) * 0.2, (z1 - z0) * 0.2
                        h2 = h + 6.8 * (1 + int(rng.integers(3)))
                        bx.box(x0 + ix, x1 - ix, z0 + iz, z1 - iz, h, h2, bid, tint, 0.2)
                        h = h2
                    else:                                                     # a rooftop plant room
                        if rng.random() < 0.5:
                            ix, iz = (x1 - x0) * 0.3, (z1 - z0) * 0.3
                            bx.box(x0 + ix, x1 - ix, z0 + iz, z1 - iz, h, h + 3.0, bid, tint, 0.0)
                    if h > 110:
                        tall.append(((x0 + x1) / 2, h + 0.5, (z0 + z1) / 2))
                    n += 1
    ob = bx.done("City", coll, [bpy.data.materials["Facade"], bpy.data.materials["Roofs"]])
    print(f"CITY {n_street} street buildings, {n} city buildings, {len(tall)} towers over 90 m")
    return ob, tall


def build_street(coll, night):
    """Hallam Row's ground: the road, the sidewalks, the street lamps (glowing at night), and the ground everywhere else."""
    r, wk = CITY["road"], CITY["walk"]
    m_ground, m_road, m_walk, m_lamp = (bpy.data.materials[n] for n in ("Ground", "Road", "Sidewalk", "LampHead"))
    def plane(name, x0, x1, z0, z1, y, mat):
        bm = bmesh.new()
        vs = [bm.verts.new(B(p)) for p in ((x0, y, z1), (x1, y, z1), (x1, y, z0), (x0, y, z0))]
        bm.faces.new(vs)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)
    plane("Ground", CX - 6000, CX + 6000, CZ - 6000, CZ + 6000, -0.02, m_ground)
    plane("Road", r["x0"], r["x1"], r["z0"], r["z1"], 0.0, m_road)
    plane("Walk_W", r["x0"] - wk, r["x0"], r["z0"], r["z1"], 0.12, m_walk)
    plane("Walk_E", r["x1"], r["x1"] + wk, r["z0"], r["z1"], 0.12, m_walk)
    bm = bmesh.new()
    for z in CITY["lamps"]:
        for s in (-1, 1):
            bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=5, radius=0.35, matrix=__import__("mathutils").Matrix.Translation(B((s * 5.5, 4.2, z))))
    me = bpy.data.meshes.new("Street_Lamps")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(m_lamp)
    coll.objects.link(bpy.data.objects.new("Street_Lamps", me))
    if night:
        for z in CITY["lamps"]:
            for s in (-1, 1):
                d = bpy.data.lights.new(f"Street_{z}_{s}", "POINT")
                d.energy, d.color, d.shadow_soft_size = 450.0, (1.0, 0.62, 0.30), 0.3
                o = bpy.data.objects.new(d.name, d)
                o.location = B((s * 5.5, 4.0, z))
                coll.objects.link(o)


# ---------------------------------------------------------------- materials: facades with a window grid, haze with distance
HAZE_D = (0.66, 0.72, 0.80)
HAZE_N = (0.075, 0.050, 0.040)


def math_node(nt, op, a, b=None, v=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    for i, x in enumerate((a, b)):
        if x is None:
            if v is not None and i == 1:
                n.inputs[1].default_value = v
            continue
        if isinstance(x, (int, float)):
            n.inputs[i].default_value = x
        else:
            nt.links.new(x, n.inputs[i])
    return n.outputs[0]


def hazed(nt, surf, night, L, out, emissive=False):
    cd = nt.nodes.new("ShaderNodeCameraData")
    f = math_node(nt, "SUBTRACT", 1.0, math_node(nt, "EXPONENT", math_node(nt, "DIVIDE", cd.outputs["View Distance"], -L)))
    if emissive:
        f = math_node(nt, "MULTIPLY", f, 0.45)
    haze = nt.nodes.new("ShaderNodeEmission")
    haze.inputs["Color"].default_value = (*(HAZE_N if night else HAZE_D), 1)
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(f, mix.inputs[0])
    nt.links.new(surf, mix.inputs[1])
    nt.links.new(haze.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])


def facade_material(night):
    m = bpy.data.materials.get("Facade") or bpy.data.materials.new("Facade")
    nt = new_nodes(m)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(uv.outputs["UV"], sep.inputs[0])
    u, v = sep.outputs["X"], sep.outputs["Y"]
    tint = nt.nodes.new("ShaderNodeAttribute")
    tint.attribute_name = "tint"
    bid = nt.nodes.new("ShaderNodeAttribute")
    bid.attribute_name = "bid"
    lit = nt.nodes.new("ShaderNodeAttribute")
    lit.attribute_name = "lit"
    cu, cv = math_node(nt, "DIVIDE", u, 3.0), math_node(nt, "DIVIDE", v, 3.4)
    fu, fv = math_node(nt, "FRACT", cu), math_node(nt, "FRACT", cv)
    win = math_node(nt, "MULTIPLY", math_node(nt, "MULTIPLY", math_node(nt, "GREATER_THAN", fu, 0.22), math_node(nt, "LESS_THAN", fu, 0.78)),
                    math_node(nt, "MULTIPLY", math_node(nt, "GREATER_THAN", fv, 0.30), math_node(nt, "LESS_THAN", fv, 0.82)))
    win = math_node(nt, "MULTIPLY", win, math_node(nt, "GREATER_THAN", v, 3.0))           # no windows lit at street level (shops are shut)
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(math_node(nt, "FLOOR", cu), comb.inputs["X"])
    nt.links.new(math_node(nt, "FLOOR", cv), comb.inputs["Y"])
    nt.links.new(math_node(nt, "MULTIPLY", bid.outputs["Fac"], 1000.0), comb.inputs["Z"])
    wn = nt.nodes.new("ShaderNodeTexWhiteNoise")
    wn.noise_dimensions = "3D"
    nt.links.new(comb.outputs[0], wn.inputs["Vector"])
    on = math_node(nt, "MULTIPLY", win, math_node(nt, "LESS_THAN", wn.outputs["Value"], lit.outputs["Fac"]))
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    glass = (0.02, 0.025, 0.035) if night else (0.12, 0.15, 0.20)
    mixc = nt.nodes.new("ShaderNodeMix")
    mixc.data_type = "RGBA"
    nt.links.new(win, mixc.inputs[0])
    nt.links.new(tint.outputs["Color"], mixc.inputs[6])
    mixc.inputs[7].default_value = (*glass, 1)
    nt.links.new(mixc.outputs[2], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.8
    surf = bsdf.outputs["BSDF"]
    if night:
        warm = nt.nodes.new("ShaderNodeMix")
        warm.data_type = "RGBA"
        cool = math_node(nt, "GREATER_THAN", math_node(nt, "FRACT", math_node(nt, "MULTIPLY", wn.outputs["Value"], 7.0)), 0.7)
        nt.links.new(cool, warm.inputs[0])
        warm.inputs[6].default_value = (1.0, 0.70, 0.38, 1)
        warm.inputs[7].default_value = (0.70, 0.82, 1.0, 1)
        em = nt.nodes.new("ShaderNodeEmission")
        nt.links.new(warm.outputs[2], em.inputs["Color"])
        bright = math_node(nt, "MULTIPLY", on, math_node(nt, "ADD", 1.2, math_node(nt, "MULTIPLY", math_node(nt, "FRACT", math_node(nt, "MULTIPLY", wn.outputs["Value"], 13.0)), 2.2)))
        nt.links.new(bright, em.inputs["Strength"])
        add = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(surf, add.inputs[0])
        nt.links.new(em.outputs[0], add.inputs[1])
        surf = add.outputs[0]
    hazed(nt, surf, night, 2600.0 if night else 1700.0, out, emissive=night)
    return m


def plain_material(name, col, night, rough=0.9, L=None, emit=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = new_nodes(m)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if emit:
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = (*emit[0], 1)
        e.inputs["Strength"].default_value = emit[1]
        surf = e.outputs[0]
    else:
        b = nt.nodes.new("ShaderNodeBsdfPrincipled")
        b.inputs["Base Color"].default_value = (*col, 1)
        b.inputs["Roughness"].default_value = rough
        surf = b.outputs["BSDF"]
    if L:
        hazed(nt, surf, night, L, out, emissive=bool(emit))
    else:
        nt.links.new(surf, out.inputs["Surface"])
    return m


def ground_material(night):
    """The ground between the buildings: dark streets with, at night, the glow of street lamps along the grid (every 88 m) and a warm haze."""
    m = bpy.data.materials.get("Ground") or bpy.data.materials.new("Ground")
    nt = new_nodes(m)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.09, 0.09, 0.085, 1) if night else (0.13, 0.13, 0.125, 1)
    b.inputs["Roughness"].default_value = 0.9
    surf = b.outputs["BSDF"]
    if night:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Object"], sep.inputs[0])
        def street_glow(axis):
            f = math_node(nt, "FRACT", math_node(nt, "DIVIDE", math_node(nt, "SUBTRACT", axis, 0.0), 88.0))
            dist = math_node(nt, "ABSOLUTE", math_node(nt, "SUBTRACT", f, 4.0 / 88.0))
            return math_node(nt, "LESS_THAN", dist, 0.7 / 88.0)                 # a thin line of lamps down each street's middle
        g = math_node(nt, "MAXIMUM", street_glow(sep.outputs["X"]), street_glow(sep.outputs["Y"]))
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (1.0, 0.55, 0.22, 1)
        nt.links.new(math_node(nt, "MULTIPLY", g, 0.6), em.inputs["Strength"])
        add = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(surf, add.inputs[0])
        nt.links.new(em.outputs[0], add.inputs[1])
        surf = add.outputs[0]
    hazed(nt, surf, night, 2600.0 if night else 1700.0, out, emissive=night)
    return m


def dir_of(bearing, elev):
    b, e = math.radians(bearing), math.radians(elev)
    return (math.cos(e) * math.sin(b), math.sin(e), -math.cos(e) * math.cos(b))


def sky_world(night):
    """Night: a navy sky warmed low down by the city's glow, stars, the moon (a disc with a halo) and a few thin clouds lit from below. Day: a
    clear sky, pale and hazy at the horizon, the sun's disc."""
    w = bpy.data.worlds.get("Sky") or bpy.data.worlds.new("Sky")
    nt = new_nodes(w)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    z = sep.outputs["Z"]
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    mr = math_node(nt, "MULTIPLY_ADD", z, 0.5, None)
    nt.nodes[-1].inputs[2].default_value = 0.5
    nt.links.new(mr, ramp.inputs["Fac"])
    els = ramp.color_ramp.elements
    stops = ([(0.0, (0.030, 0.022, 0.018)), (0.5, (0.30, 0.17, 0.09)), (0.515, (0.20, 0.12, 0.08)), (0.56, (0.075, 0.058, 0.068)),
              (0.68, (0.022, 0.026, 0.050)), (1.0, (0.006, 0.009, 0.022))] if night else
             [(0.0, (0.30, 0.30, 0.30)), (0.5, (0.78, 0.82, 0.88)), (0.53, (0.62, 0.72, 0.86)), (0.65, (0.40, 0.56, 0.80)), (1.0, (0.20, 0.36, 0.70))])
    while len(els) > 1:
        els.remove(els[-1])
    els[0].position, els[0].color = stops[0][0], (*stops[0][1], 1)
    for p, c in stops[1:]:
        e = els.new(p)
        e.color = (*c, 1)
    col = ramp.outputs["Color"]
    d = dir_of(MOON_BEARING, MOON_ELEV) if night else dir_of(SUN_BEARING, SUN_ELEV)
    bd = B(d)
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(tc.outputs["Generated"], dot.inputs[0])
    dot.inputs[1].default_value = (bd.x, bd.y, bd.z)
    c = dot.outputs["Value"]
    if night:
        disc = math_node(nt, "GREATER_THAN", c, math.cos(math.radians(1.6)))                # the moon, drawn larger than life
        halo = math_node(nt, "POWER", math_node(nt, "MAXIMUM", c, 0.0), 300.0)
        add = math_node(nt, "ADD", math_node(nt, "MULTIPLY", disc, 3.0), math_node(nt, "MULTIPLY", halo, 0.25))
        wn = nt.nodes.new("ShaderNodeTexWhiteNoise")
        wn.noise_dimensions = "3D"
        sc_ = nt.nodes.new("ShaderNodeVectorMath")
        sc_.operation = "SCALE"
        nt.links.new(tc.outputs["Generated"], sc_.inputs[0])
        sc_.inputs["Scale"].default_value = 700.0
        fl = nt.nodes.new("ShaderNodeVectorMath")
        fl.operation = "FLOOR"
        nt.links.new(sc_.outputs[0], fl.inputs[0])
        nt.links.new(fl.outputs[0], wn.inputs["Vector"])
        stars = math_node(nt, "MULTIPLY", math_node(nt, "GREATER_THAN", wn.outputs["Value"], 0.9984), math_node(nt, "GREATER_THAN", z, 0.10))
        stars = math_node(nt, "MULTIPLY", stars, math_node(nt, "MINIMUM", math_node(nt, "MULTIPLY", z, 2.0), 1.0))
        add = math_node(nt, "ADD", add, math_node(nt, "MULTIPLY", stars, 0.4))
        mixm = nt.nodes.new("ShaderNodeMix")
        mixm.data_type = "RGBA"
        mixm.blend_type = "ADD"
        nt.links.new(math_node(nt, "MINIMUM", add, 3.0), mixm.inputs[0])
        nt.links.new(col, mixm.inputs[6])
        mixm.inputs[7].default_value = (0.92, 0.94, 1.0, 1)
        col = mixm.outputs[2]
        # thin clouds, lit orange from below by the city
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 3.0
        nz.inputs["Detail"].default_value = 6.0
        stretch = nt.nodes.new("ShaderNodeMapping")
        stretch.vector_type = "POINT"
        stretch.inputs["Scale"].default_value = (1.0, 1.0, 4.0)
        nt.links.new(tc.outputs["Generated"], stretch.inputs["Vector"])
        nt.links.new(stretch.outputs[0], nz.inputs["Vector"])
        band = math_node(nt, "MULTIPLY", math_node(nt, "GREATER_THAN", z, 0.03), math_node(nt, "LESS_THAN", z, 0.45))
        cl = math_node(nt, "MULTIPLY", math_node(nt, "MAXIMUM", math_node(nt, "SUBTRACT", nz.outputs["Fac"], 0.56), 0.0), 3.0)
        cl = math_node(nt, "MULTIPLY", math_node(nt, "MULTIPLY", cl, band), 0.5)
        mixc = nt.nodes.new("ShaderNodeMix")
        mixc.data_type = "RGBA"
        nt.links.new(cl, mixc.inputs[0])
        nt.links.new(col, mixc.inputs[6])
        mixc.inputs[7].default_value = (0.16, 0.10, 0.08, 1)
        col = mixc.outputs[2]
    else:
        disc = math_node(nt, "GREATER_THAN", c, math.cos(math.radians(0.8)))
        glow = math_node(nt, "POWER", math_node(nt, "MAXIMUM", c, 0.0), 60.0)
        add = math_node(nt, "ADD", math_node(nt, "MULTIPLY", disc, 40.0), math_node(nt, "MULTIPLY", glow, 0.5))
        mixm = nt.nodes.new("ShaderNodeMix")
        mixm.data_type = "RGBA"
        mixm.blend_type = "ADD"
        nt.links.new(math_node(nt, "MINIMUM", add, 40.0), mixm.inputs[0])
        nt.links.new(col, mixm.inputs[6])
        mixm.inputs[7].default_value = (1.0, 0.95, 0.85, 1)
        col = mixm.outputs[2]
    nt.links.new(col, bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    bpy.context.scene.world = w


def lights(coll, night):
    for o in [o for o in coll.objects if o.type == "LIGHT" and o.name in ("Sun", "Moon")]:
        bpy.data.objects.remove(o)
    d = bpy.data.lights.new("Moon" if night else "Sun", "SUN")
    if night:
        d.energy, d.color, d.angle = 0.25, (0.74, 0.82, 1.0), math.radians(0.6)
        v = dir_of(MOON_BEARING, MOON_ELEV)
    else:
        d.energy, d.color, d.angle = 4.5, (1.0, 0.95, 0.86), math.radians(0.6)
        v = dir_of(SUN_BEARING, SUN_ELEV)
    o = bpy.data.objects.new(d.name, d)
    o.rotation_euler = B((-v[0], -v[1], -v[2])).to_track_quat("-Z", "Y").to_euler()
    coll.objects.link(o)


def beacons(coll, tall, night):
    if not night or not tall:
        return
    bm = bmesh.new()
    import mathutils
    for x, y, z in tall:
        bmesh.ops.create_uvsphere(bm, u_segments=6, v_segments=4, radius=1.2, matrix=mathutils.Matrix.Translation(B((x, y + 1.0, z))))
    me = bpy.data.meshes.new("Beacons")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(bpy.data.materials["Beacon"])
    coll.objects.link(bpy.data.objects.new("Beacons", me))


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def stage_backdrops():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    setup_cycles(arg("--bd-samples", 128, int))
    sc.view_settings.view_transform = "Standard"
    for p in sc.render.bl_rna.properties:
        if p.identifier.startswith("use_stamp") and not p.is_readonly:
            setattr(sc.render, p.identifier, False)
    pano_camera()
    for night in (True, False):
        k = "night" if night else "day"
        for o in list(bpy.data.objects):
            if o.name != "pano":
                bpy.data.objects.remove(o)
        for c in list(bpy.data.collections):
            bpy.data.collections.remove(c)
        coll = bpy.data.collections.new("City")
        sc.collection.children.link(coll)
        facade_material(night)
        plain_material("Roofs", (0.16, 0.16, 0.16) if night else (0.34, 0.33, 0.31), night, L=2600.0 if night else 1700.0)
        ground_material(night)
        plain_material("Road", (0.05, 0.05, 0.05) if night else (0.12, 0.12, 0.12), night, L=2600.0)
        plain_material("Sidewalk", (0.20, 0.20, 0.19) if night else (0.45, 0.44, 0.42), night, L=2600.0)
        plain_material("LampHead", None, night, emit=((1.0, 0.70, 0.40), 25.0 if night else 0.0), L=2600.0)
        plain_material("Beacon", None, night, emit=((1.0, 0.05, 0.03), 30.0), L=4000.0)
        rng = np.random.default_rng(1919)
        city_ob, tall = build_city(coll, rng)
        build_street(coll, night)
        beacons(coll, tall, night)
        sky_world(night)
        lights(coll, night)
        if night:
            orientation_test([coll])
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, arg("--scale", 100, int)
        sc.view_settings.exposure = arg("--exposure-" + k, 0.0, float)
        sc.render.image_settings.file_format = "PNG"
        sc.render.image_settings.color_depth = "8"
        sc.render.image_settings.color_mode = "RGB"
        sc.render.filepath = str(stage_work() / f"backdrop_{k}.png")
        bpy.ops.render.render(write_still=True)
        print("BACKDROP", k, sc.render.filepath)
    set_path(sc.render, "filepath", "//")


if STAGE == "backdrops":
    stage_backdrops()
else:
    print("in Blender only --stage backdrops runs")
