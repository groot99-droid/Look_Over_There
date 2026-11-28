"""Renders the Overworld parking lot's edge-of-world backdrops (docs/BLENDER.md, R3): the endless hills and the town beyond the hedges, as two
4096 x 2048 equirect panoramas, world/backdrops/parking_lot_day.webp and parking_lot_night.webp.

Re-runnable, from the repo root:

    blender -b --factory-startup --python tools/blender/build_parking_lot_backdrop.py -- --stage survey --work <work>
        (optional: imports world/L4.glb and world/Exterior.glb read-only and renders what the lot's own model covers from the same point, with its sky dome
         hidden, as a transparent panorama <work>/survey.png; used for the owner sheet's in-game preview only)
    blender -b --factory-startup --python tools/blender/build_parking_lot_backdrop.py -- --stage backdrops --work <work> [--bd-samples 128]
        (builds the hills and the town in a new scene, runs the orientation self-check, renders <work>/backdrop_day.png and backdrop_night.png,
         and saves blender/scenes/parking_lot_backdrop.blend)
    python tools/blender/build_parking_lot_backdrop.py --stage pack-backdrops --work <work>     (the PNGs -> WebP, each at most 1 MB)
    python tools/blender/build_parking_lot_backdrop.py --stage sheet --work <work> --out <png>  (an owner sheet: both panoramas and flat views)
    python tools/blender/build_parking_lot_backdrop.py --stage previews --work <work>           (two small JPEG stills -> docs/renders/parking_lot/)

Nothing of the store is used or changed: Look_Over_There.blend and world/*.glb are never written. The lot's extent comes from world/parking_lot.json
(the asphalt, the hedges, the lot's grass), so no coordinate of the lot is typed in here. The panoramas are taken from the lot's arrival point (the Spawn marker
by the table) at eye height (1.6 m over the floor, y 9.6); the playable area is not in this scene at all, so nothing of it is in the pictures.

Axes: a game point (x, y, z) is Blender (x, -z, y). The picture's middle column faces north (game -z, Blender +Y) and its right-hand side faces
east (game +x, Blender +X); `orientation_test` checks this before every render.

Everything here is procedural (numpy noise and Blender's own shader nodes): no image, model or HDRI from anywhere else.
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
    from mathutils import Vector
except ImportError:                       # the pack, sheet and previews stages run in plain Python (numpy and Pillow)
    bpy = None

ROOT = Path(__file__).resolve().parents[2]
SCENE = "parking_lot"
LOT = ROOT / f"world/{SCENE}.json"
BLEND = ROOT / f"blender/scenes/{SCENE}_backdrop.blend"
STILLS = ROOT / f"docs/renders/{SCENE}"
W, H = 4096, 2048

if "--" in sys.argv:
    args = sys.argv[sys.argv.index("--") + 1:]
else:
    args = sys.argv[1:] if bpy is None else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "backdrops")
DEVICE = arg("--device", "auto")


def stage_work():
    d = Path(arg("--work", str(Path(os.environ.get("TEMP", "/tmp")) / f"farway_{SCENE}_backdrop")))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- the lot, from its collision file
def lot_extent():
    doc = json.loads(LOT.read_text())
    by = {}
    for c in doc["colliders"]:
        by.setdefault(c["s"], []).append(c)
    asphalt = by["Ground_LOT_Exterior_asphalt"][0]
    hedges = by["Hedges_LOT_Exterior"]
    grass = by["Ground_LOT_Exterior_grass"]
    floor = asphalt["max"][1]
    ext = {
        "floor": round(floor, 2),
        "asphalt": (asphalt["min"][0], asphalt["min"][2], asphalt["max"][0], asphalt["max"][2]),
        "hedge_back_z": max(h["max"][2] for h in hedges),                          # the tall hedge across the back of the lot
        "hedge_top": max(h["max"][1] for h in hedges),
        "hedge_x": (min(h["min"][0] for h in hedges), max(h["max"][0] for h in hedges)),
        "grass": (min(g["min"][0] for g in grass), min(g["min"][2] for g in grass), max(g["max"][0] for g in grass), max(g["max"][2] for g in grass)),
    }
    # the point the panoramas are taken from: the lot's arrival point (its Spawn marker, by the table), at eye height. The asphalt's own middle
    # (0, 62.9) is inside one of the city set's towers that stand in the lot (Site_ITN_City, x -18 .. 9, z 52 .. 67, 91 m tall), so it cannot be used.
    spawn = next(m for m in doc["markers"] if m["kind"] == "Spawn")["position"]
    ext["spawn"] = spawn
    ext["centre"] = (spawn[0], spawn[1] + 1.6, spawn[2])
    return ext


EXT = lot_extent()
CX, CY, CZ = EXT["centre"]
FLOOR = EXT["floor"]
GRASS_R = min(abs(EXT["grass"][0] - CX), abs(EXT["grass"][2] - CX), abs(EXT["grass"][1] - CZ), abs(EXT["grass"][3] - CZ))   # the model's own grass reaches this far


# ---------------------------------------------------------------- noise and heights (numpy, seeded: the same every run)
class VNoise:
    def __init__(self, seed):
        self.v = np.random.default_rng(seed).random((256, 256))

    def __call__(self, x, z):
        xi, zi = np.floor(x), np.floor(z)
        fx, fz = x - xi, z - zi
        fx, fz = fx * fx * (3 - 2 * fx), fz * fz * (3 - 2 * fz)
        i0, j0 = xi.astype(np.int64) & 255, zi.astype(np.int64) & 255
        i1, j1 = (i0 + 1) & 255, (j0 + 1) & 255
        v = self.v
        a = v[i0, j0] * (1 - fx) + v[i1, j0] * fx
        b = v[i0, j1] * (1 - fx) + v[i1, j1] * fx
        return a * (1 - fz) + b * fz


N1, N2, N3, N4 = VNoise(11), VNoise(23), VNoise(37), VNoise(41)


def fbm(n, x, z, octaves, gain=0.5):
    s, amp, tot, f = 0.0, 1.0, 0.0, 1.0
    for o in range(octaves):
        s = s + amp * n(x * f + 17.3 * o, z * f - 9.1 * o)
        tot += amp
        amp *= gain
        f *= 2.03
    return s / tot


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


TOWN_BEARING = math.radians(arg("--town-bearing", 188.0, float))   # the town lies past the tall back hedge (south, game +z), a little west of it
TOWN_R = (430.0, 1250.0)
TOWN_HALF = math.radians(34.0)


def bearing_of(dx, dz):
    """Compass bearing (0 north = game -z, 90 east = +x) of game offsets from the centre."""
    return np.mod(np.arctan2(dx, -dz), 2 * math.pi)


def town_mask(dx, dz):
    r = np.hypot(dx, dz)
    d = np.abs(np.mod(bearing_of(dx, dz) - TOWN_BEARING + math.pi, 2 * math.pi) - math.pi)
    return (1 - smooth(TOWN_HALF * 0.75, TOWN_HALF * 1.5, d)) * smooth(TOWN_R[0] - 120, TOWN_R[0] + 40, r) * (1 - smooth(TOWN_R[1], TOWN_R[1] + 500, r))


def height(dx, dz):
    """Ground height (game y) at offsets from the centre: flat out to the lot model's grass, then rolling hills that climb in tiers to far ridges."""
    x, z = dx + CX, dz + CZ
    r = np.hypot(dx, dz)
    ramp = smooth(GRASS_R * 0.85, GRASS_R * 2.2, r)
    roll = fbm(N1, x / 430.0, z / 430.0, 5)                                  # 0..1, about 0.5
    hills = 95.0 * (roll - 0.30) + 0.03 * np.maximum(r - GRASS_R, 0)
    ridges = smooth(1400, 6000, r) * (1000.0 * fbm(N2, x / 2300.0, z / 2300.0, 4) ** 1.6 + 0.03 * r)
    far = smooth(8000, 16000, r) * 1100.0 * fbm(N3, x / 5200.0, z / 5200.0, 3)
    wild = ramp * np.maximum(hills, 0.0) + ridges + far
    # the town sits on one long slope facing the lot, so its roofs climb in rows above the back hedge
    tm = town_mask(dx, dz)
    slope = 0.11 * np.maximum(r - (TOWN_R[0] - 60), 0) + 6.0 * (fbm(N4, x / 260.0, z / 260.0, 3) - 0.5)
    return FLOOR - 0.05 + wild * (1 - tm) + np.maximum(slope, 0) * tm


def woods(dx, dz):
    """0..1: how wooded a spot is (copses on the hills, none in the town)."""
    x, z = dx + CX, dz + CZ
    w = smooth(0.56, 0.68, fbm(N3, x / 300.0, z / 300.0, 4))
    return w * (1 - town_mask(dx, dz)) * smooth(GRASS_R, GRASS_R * 1.3, np.hypot(dx, dz))


# ================================================================ the stages without Blender
def stage_pack_backdrops():
    """The backdrop PNGs -> world/backdrops/parking_lot_day.webp and parking_lot_night.webp (4096 x 2048), as good a WebP as fits in 1 MB."""
    from PIL import Image
    work = Path(arg("--work", "."))
    out = ROOT / "world/backdrops"
    out.mkdir(parents=True, exist_ok=True)
    for k in ("day", "night"):
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
    d = np.stack([xs, ys, np.full_like(xs, f)], -1)                      # camera: x right, y up, z forward
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


def load_pano(work, k):
    from PIL import Image
    src = ROOT / f"world/backdrops/{SCENE}_{k}.webp"
    return Image.open(src if src.exists() else work / f"backdrop_{k}.png").convert("RGB")


def in_game(work, pano):
    """The panorama behind the lot's own model (the survey's transparent render), as the page would draw them; None without a survey."""
    from PIL import Image
    sv = work / "survey.png"
    if not sv.exists():
        return None
    s = Image.open(sv).convert("RGBA").resize(pano.size, Image.BILINEAR)
    base = pano.convert("RGBA")
    base.alpha_composite(s)
    return base.convert("RGB")


def stage_sheet():
    from PIL import Image, ImageDraw
    work = Path(arg("--work", "."))
    dst = Path(arg("--out", str(work / f"owner_{SCENE}.png")))
    pw, ph = 2400, 1200
    vw, vh = 600, 338
    rows = []
    for k in ("day", "night"):
        pano = load_pano(work, k)
        rows.append(("pano", k, pano.resize((pw, ph), Image.LANCZOS)))
        views = [Image.fromarray(equirect_view(pano, yaw, size=(vw, vh))) for yaw in (0, 90, 180, 270)]
        rows.append(("views", k, views))
        g = in_game(work, pano)
        if g is not None:
            rows.append(("game", k, [Image.fromarray(equirect_view(g, yaw, size=(vw, vh))) for yaw in (0, 90, 180, 270)]))
    pad, lab = 16, 30
    hgt = pad
    for kind, _, _ in rows:
        hgt += lab + (ph if kind == "pano" else vh) + pad
    sheet = Image.new("RGB", (pw + 2 * pad, hgt), (24, 24, 28))
    dr = ImageDraw.Draw(sheet)
    y = pad
    names = ("north (the store)", "east", "south (the back hedge, the town)", "west")
    for kind, k, im in rows:
        if kind == "pano":
            dr.text((pad, y + 8), f"{SCENE}_{k}.webp  4096 x 2048 equirect (middle north, right east), shown at {pw} x {ph}", fill=(235, 235, 235))
            y += lab
            sheet.paste(im, (pad, y))
            for frac, t in ((0.0, "S"), (0.25, "W"), (0.5, "N"), (0.75, "E")):
                dr.text((pad + int(frac * pw) + 4, y + 4), t, fill=(255, 60, 60))
            y += ph + pad
        else:
            what = "flat 90-degree views out of the backdrop alone" if kind == "views" else "the same views with the lot's own model in front (survey render, model's sky hidden), as the page would draw them"
            dr.text((pad, y + 8), f"{k}: {what}", fill=(235, 235, 235))
            y += lab
            for i, v in enumerate(im):
                x = pad + i * vw
                sheet.paste(v, (x, y))
                dr.text((x + 6, y + 6), names[i], fill=(255, 255, 255))
            y += vh + pad
    dst.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dst, optimize=True)
    print("SHEET", dst, sheet.size, dst.stat().st_size)


def strip_jpeg_meta(path):
    """Drop a JPEG's comment (FE) and APP1 (E1: EXIF/XMP) segments."""
    b = path.read_bytes()
    out, i = bytearray(b[:2]), 2
    while i < len(b) and b[i] == 0xFF and b[i + 1] != 0xDA:
        n = int.from_bytes(b[i + 2:i + 4], "big")
        if b[i + 1] not in (0xFE, 0xE1):
            out += b[i:i + 2 + n]
        i += 2 + n
    out += b[i:]
    path.write_bytes(bytes(out))


def stage_previews():
    """Two review stills for docs/renders/parking_lot/: the view south past the back hedge (the town) by day and by night, 1920 x 1080 JPEG."""
    from PIL import Image
    work = Path(arg("--work", "."))
    STILLS.mkdir(parents=True, exist_ok=True)
    for i, k in enumerate(("day", "night"), start=1):
        v = Image.fromarray(equirect_view(load_pano(work, k), 180.0, hfov=75.0, size=(1920, 1080), pitch_deg=3.0))
        p = STILLS / f"{i}_{k}_south.jpg"
        v.save(p, "JPEG", quality=86)
        strip_jpeg_meta(p)
        print("STILL", p.relative_to(ROOT).as_posix(), p.stat().st_size)


if bpy is None:
    {"pack-backdrops": stage_pack_backdrops, "sheet": stage_sheet, "previews": stage_previews}.get(
        STAGE, lambda: print("without Blender only --stage pack-backdrops, sheet and previews run"))()
    sys.exit(0)


# ================================================================ Blender from here on
def B(p):
    """A game point (x, y, z) -> Blender (x, -z, y)."""
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
    print("CYCLES device:", cy.device, [d.name for d in prefs.devices if d.use] if gpu else "CPU")


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
    sc = bpy.context.scene
    tmp = bpy.data.collections.new("OrientTest")
    sc.collection.children.link(tmp)
    for name, p, col in (("east", (CX + 400, CY, CZ), (1, 0, 0)), ("north", (CX, CY, CZ - 400), (0, 1, 0)), ("south", (CX, CY, CZ + 400), (0, 0, 1))):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=80.0)
        bmesh.ops.translate(bm, vec=B(p), verts=bm.verts)
        me = bpy.data.meshes.new(f"orient_{name}")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(emit_material(f"orient_{name}", col, 5.0))
        ob = bpy.data.objects.new(f"orient_{name}", me)
        tmp.objects.link(ob)
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
    a = a.reshape(128, 256, 4)[64]                               # the horizon row

    def centre(ch):                                              # the middle of the marker's run of bright pixels (the seam wraps for south)
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


# ---------------------------------------------------------------- the survey: what the lot's own model covers (read-only import of world/Exterior.glb)
def stage_survey():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for g in ("L4", "Exterior"):                               # the page loads both for the lot (shared/farway.manifest.js)
        bpy.ops.import_scene.gltf(filepath=str(ROOT / f"world/{g}.glb"))
    sky = [o for o in bpy.data.objects if o.name.startswith("Sky_LOT_Exterior")]
    for o in sky:
        o.hide_render = True
    print("SURVEY lot extent from world/parking_lot.json:", json.dumps(EXT))
    sc = bpy.context.scene
    setup_cycles(arg("--samples", 24, int))
    w = bpy.data.worlds.new("grey")
    nt = new_nodes(w)
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (0.8, 0.85, 0.95, 1)
    bg.inputs["Strength"].default_value = 1.2
    nt.links.new(bg.outputs[0], nt.nodes.new("ShaderNodeOutputWorld").inputs["Surface"])
    sc.world = w
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sc.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(40), 0, math.radians(30))
    pano_camera()
    sc.render.film_transparent = True
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 2048, 1024, 100
    sc.view_settings.view_transform = "Standard"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    path = stage_work() / "survey.png"
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print("SURVEY", path, path.stat().st_size, "hidden:", [o.name for o in sky])


# ---------------------------------------------------------------- the backdrop world
def mesh_from(name, verts, faces, coll, attrs=None, mats=None, mat_index=None):
    """A mesh object from numpy arrays: verts (n, 3) in Blender coordinates, faces (m, k) vertex indices (all quads or all triangles);
    attrs: {name: (m, 3) colours per face}."""
    me = bpy.data.meshes.new(name)
    nv, nf = len(verts), len(faces)
    k = faces.shape[1]
    me.vertices.add(nv)
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    me.loops.add(nf * k)
    me.loops.foreach_set("vertex_index", faces.astype(np.int32).ravel())
    me.polygons.add(nf)
    me.polygons.foreach_set("loop_start", (np.arange(nf) * k).astype(np.int32))
    me.polygons.foreach_set("loop_total", np.full(nf, k, np.int32))
    me.update(calc_edges=True)
    me.validate()
    for an, col in (attrs or {}).items():
        at = me.color_attributes.new(an, "FLOAT_COLOR", "CORNER")
        c4 = np.concatenate([np.repeat(col.astype(np.float32), k, axis=0), np.ones((nf * k, 1), np.float32)], 1)
        at.data.foreach_set("color", c4.ravel())
    for m in mats or []:
        me.materials.append(m)
    if mat_index is not None:
        me.polygons.foreach_set("material_index", mat_index.astype(np.int32))
    me.polygons.foreach_set("use_smooth", np.zeros(nf, bool))
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def build_terrain(coll):
    """A polar grid round the centre, from right under the camera out to 30 km (finer near, coarser far): the lower half of the picture is
    ground everywhere, so wherever the lot's own model leaves a gap the page shows grass, not sky."""
    rs = np.concatenate([np.geomspace(0.02, GRASS_R * 0.5, 40, endpoint=False), np.linspace(GRASS_R * 0.5, 700, 70, endpoint=False), np.geomspace(700, 30000, 190)])
    na = 1440
    th = np.linspace(0, 2 * math.pi, na, endpoint=False)
    R, T = np.meshgrid(rs, th, indexing="ij")
    dx, dz = R * np.sin(T), -R * np.cos(T)                   # bearing T from north (game -z) toward east (+x)
    y = height(dx, dz)
    verts = np.stack([CX + dx, -(CZ + dz), y], -1).reshape(-1, 3)
    ii, jj = np.meshgrid(np.arange(len(rs) - 1), np.arange(na), indexing="ij")
    a = ii * na + jj
    b = ii * na + (jj + 1) % na
    faces = np.stack([a, (ii + 1) * na + jj, (ii + 1) * na + (jj + 1) % na, b], -1).reshape(-1, 4)
    fx, fz = dx[:-1].ravel(), dz[:-1].ravel()                 # each face's tint from its first corner
    wd = woods(fx, fz)
    meadow = fbm(N2, (fx + CX) / 90.0, (fz + CZ) / 90.0, 2)
    tint = np.stack([0.11 + 0.05 * meadow, 0.24 + 0.05 * meadow, 0.055 + 0.02 * meadow], -1)
    tint = tint * (1 - 0.62 * wd[:, None])
    tm = town_mask(fx, fz)
    tint = tint * (1 - 0.35 * tm[:, None]) + np.array([0.16, 0.16, 0.14]) * 0.35 * tm[:, None]       # yards, lanes and gardens in the town
    ob = mesh_from("bd_terrain", verts, faces, coll, {"tint": tint})
    print("TERRAIN", len(verts), "verts", len(faces), "faces")
    return ob


ICO = None


def ico():
    global ICO
    if ICO is None:
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
        v = np.array([x.co[:] for x in bm.verts])
        f = np.array([[x.index for x in fc.verts] for fc in bm.faces])
        bm.free()
        ICO = (v, f)
    return ICO


def build_trees(coll, rng):
    """Copses and hedgerow trees on the hills, out to 3 km (past that the woods are only in the ground's tint)."""
    n = 60000
    r = GRASS_R * 0.95 + rng.gamma(1.4, 520, n)
    t = rng.uniform(0, 2 * math.pi, n)
    dx, dz = r * np.sin(t), -r * np.cos(t)
    keep = (r < 3200) & (rng.random(n) < 0.05 + 0.95 * woods(dx, dz))
    dx, dz, r = dx[keep][:14000], dz[keep][:14000], r[keep][:14000]
    m = len(dx)
    rad = rng.uniform(3.0, 6.5, m)
    gy = height(dx, dz)
    v0, f0 = ico()
    sx = rad[:, None] * np.array([1.0, 1.0, 1.15])[None]
    verts = (v0[None] * sx[:, None]) + np.stack([CX + dx, -(CZ + dz), gy + rad * 1.05], -1)[:, None]
    faces = (f0[None] + (np.arange(m) * len(v0))[:, None, None]).reshape(-1, 3)
    g = rng.uniform(0.7, 1.2, m)
    tint = np.stack([0.05 * g, 0.12 * g, 0.035 * g], -1)
    ob = mesh_from("bd_trees", verts.reshape(-1, 3), faces, coll, {"tint": np.repeat(tint, len(f0), 0)})
    print("TREES", m)
    return ob


WALLS = np.array([[0.80, 0.77, 0.70], [0.86, 0.84, 0.78], [0.62, 0.30, 0.22], [0.74, 0.66, 0.50], [0.70, 0.71, 0.70], [0.83, 0.75, 0.60]])
ROOFS = np.array([[0.22, 0.20, 0.20], [0.45, 0.20, 0.13], [0.30, 0.26, 0.24], [0.16, 0.17, 0.19], [0.52, 0.27, 0.17]])


class Parts:
    """Faces (quads) with a colour and a material slot each: 0 wall, 1 roof, 2 window, 3 lit window, 4 lamp."""

    def __init__(self):
        self.v, self.f, self.c, self.m = [], [], [], []
        self.n = 0

    def quad(self, pts, col, slot):
        self.v.extend(pts)
        self.f.append([self.n, self.n + 1, self.n + 2, self.n + 3])
        self.c.append(col)
        self.m.append(slot)
        self.n += 4

    def box(self, c, hw, hd, y0, y1, rot, col, slot, roof_slot=None, roof_col=None, top=True):
        ca, sa = math.cos(rot), math.sin(rot)

        def P(u, w, y):                                     # local (u along the width, w along the depth) -> Blender
            gx, gz = c[0] + u * ca - w * sa, c[1] + u * sa + w * ca
            return (gx, -gz, y)
        for (u0, w0), (u1, w1) in (((-hw, -hd), (hw, -hd)), ((hw, -hd), (hw, hd)), ((hw, hd), (-hw, hd)), ((-hw, hd), (-hw, -hd))):
            self.quad([P(u0, w0, y0), P(u1, w1, y0), P(u1, w1, y1), P(u0, w0, y1)], col, slot)
        if top:
            self.quad([P(-hw, -hd, y1), P(-hw, hd, y1), P(hw, hd, y1), P(hw, -hd, y1)], roof_col if roof_col is not None else col,
                      roof_slot if roof_slot is not None else slot)
        return P

    def done(self, name, coll, mats):
        v = np.array(self.v, float)
        f = np.array(self.f)
        return mesh_from(name, v, f, coll, {"tint": np.array(self.c, float)}, mats, np.array(self.m))


def house(parts, rng, c, rot, lit_p, big=False):
    hw, hd = rng.uniform(3.0, 5.0), rng.uniform(3.5, 5.0)
    floors = int(rng.choice([1, 2, 2, 2, 3])) if not big else int(rng.integers(3, 5))
    fh = 2.9
    gx, gz = c
    corners = np.array([[gx + sx * hw, gz + sz * hd] for sx in (-1, 1) for sz in (-1, 1)])
    base = float(height(corners[:, 0] - CX, corners[:, 1] - CZ).min()) - 0.4
    top = base + 0.4 + floors * fh
    wall = WALLS[rng.integers(len(WALLS))] * rng.uniform(0.85, 1.05)
    roof = ROOFS[rng.integers(len(ROOFS))] * rng.uniform(0.8, 1.1)
    P = parts.box(c, hw, hd, base, top, rot, wall, 0, top=big)
    if not big:                                              # a gable roof along the width
        rise = rng.uniform(2.2, 3.6)
        o = 0.35
        ridge = top + rise
        parts.quad([P(-hw - o, -hd - o, top - 0.2), P(hw + o, -hd - o, top - 0.2), P(hw + o, 0, ridge), P(-hw - o, 0, ridge)], roof, 1)
        parts.quad([P(hw + o, hd + o, top - 0.2), P(-hw - o, hd + o, top - 0.2), P(-hw - o, 0, ridge), P(hw + o, 0, ridge)], roof, 1)
        parts.quad([P(-hw, -hd, top), P(-hw, 0, ridge - 0.1), P(-hw, 0, ridge - 0.1), P(-hw, hd, top)], wall, 0)
        parts.quad([P(hw, hd, top), P(hw, 0, ridge - 0.1), P(hw, 0, ridge - 0.1), P(hw, -hd, top)], wall, 0)
        if rng.random() < 0.5:                               # a chimney
            parts.box((gx + 0.5 * hw * math.cos(rot), gz + 0.5 * hw * math.sin(rot)), 0.35, 0.35, top, ridge + 0.9, rot, wall * 0.8, 0)
    else:
        parts.box(c, hw + 0.15, hd + 0.15, top, top + 0.6, rot, wall * 0.9, 0, 1, roof)
    # windows on both long faces (w = -hd and w = +hd), a little proud of the wall
    for side in (-1, 1):
        w = side * (hd + 0.04)
        nwin = max(2, int(2 * hw / 2.4))
        for fl in range(floors):
            y0 = base + 0.4 + fl * fh + 0.95
            for i in range(nwin):
                u = -hw + (i + 0.5) * (2 * hw / nwin)
                lit = rng.random() < lit_p
                a, b = (u - 0.5, u + 0.5) if side > 0 else (u + 0.5, u - 0.5)
                parts.quad([P(a, w, y0), P(b, w, y0), P(b, w, y0 + 1.2), P(a, w, y0 + 1.2)], (0.0, 0.0, 0.0), 3 if lit else 2)
    return top


def build_town(coll, rng, mats):
    """The town on its slope past the back hedge: houses on a street grid that faces the lot, a high street of shops and flats, a church with a
    spire, a water tower; and farmhouses dotted over the hills. A few windows are lit (material slot 3), and the streets have lamps (slot 4)."""
    parts = Parts()
    lamps = Parts()
    axis = TOWN_BEARING                                       # the grid's streets run across and up the slope
    ua = np.array([math.cos(axis), math.sin(axis)])             # game (x, z) across the slope (perpendicular to the bearing)
    fwd = np.array([math.sin(axis), -math.cos(axis)])           # game (x, z) away from the lot
    n = 0
    cell = 15.0
    for i in range(-80, 81):
        for j in range(0, 70):
            if j % 5 == 0 or i % 7 == 0:                        # streets
                if (i + j) % 3 == 0:
                    p = np.array([CX, CZ]) + fwd * (TOWN_R[0] + j * cell) + ua * (i * cell)
                    if town_mask(np.array([p[0] - CX]), np.array([p[1] - CZ]))[0] > 0.5 and rng.random() < 0.25:
                        gy = float(height(np.array([p[0] - CX]), np.array([p[1] - CZ]))[0])
                        lamps.box((p[0], p[1]), 0.5, 0.5, gy + 4.5, gy + 5.5, 0, (0, 0, 0), 4)
                continue
            p = np.array([CX, CZ]) + fwd * (TOWN_R[0] + j * cell + rng.uniform(-3, 3)) + ua * (i * cell + rng.uniform(-3, 3))
            tm = town_mask(np.array([p[0] - CX]), np.array([p[1] - CZ]))[0]
            if rng.random() > tm * 0.92:
                continue
            core = abs(i) < 14 and 6 < j < 26
            rot = axis + (math.pi / 2 if rng.random() < 0.2 else 0) + rng.uniform(-0.06, 0.06)
            house(parts, rng, (p[0], p[1]), rot, 0.05, big=core and rng.random() < 0.6)
            n += 1
    # the church and its spire, the water tower
    for (dist, side, kind) in ((TOWN_R[0] + 260, -60.0, "church"), (TOWN_R[0] + 520, 210.0, "tower"), (TOWN_R[0] + 120, 120.0, "silo")):
        p = np.array([CX, CZ]) + fwd * dist + ua * side
        gy = float(height(np.array([p[0] - CX]), np.array([p[1] - CZ]))[0])
        if kind == "church":
            P = parts.box((p[0], p[1]), 6.0, 13.0, gy - 0.5, gy + 11, axis + math.pi / 2, WALLS[4] * 0.9, 0, 1, ROOFS[3])
            parts.box((p[0] + 15 * fwd[0], p[1] + 15 * fwd[1]), 3.5, 3.5, gy - 0.5, gy + 26, axis, WALLS[4] * 0.85, 0)
            tip = (p[0] + 15 * fwd[0], p[1] + 15 * fwd[1])
            for k in range(4):                                   # the spire: four triangles (quads with a doubled tip)
                a0, a1 = math.pi / 4 + k * math.pi / 2, math.pi / 4 + (k + 1) * math.pi / 2
                q = [(tip[0] + 4.9 * math.cos(a0), -(tip[1] + 4.9 * math.sin(a0)), gy + 26), (tip[0] + 4.9 * math.cos(a1), -(tip[1] + 4.9 * math.sin(a1)), gy + 26),
                     (tip[0], -tip[1], gy + 48), (tip[0], -tip[1], gy + 48)]
                parts.quad(q, ROOFS[3], 1)
        elif kind == "tower":
            for k in range(4):
                a = math.pi / 4 + k * math.pi / 2
                parts.box((p[0] + 4.5 * math.cos(a), p[1] + 4.5 * math.sin(a)), 0.4, 0.4, gy - 0.5, gy + 22, 0, (0.55, 0.56, 0.58), 0)
            parts.box((p[0], p[1]), 6.5, 6.5, gy + 22, gy + 30, axis, (0.72, 0.74, 0.76), 0, 1, (0.5, 0.52, 0.54))
        else:
            parts.box((p[0], p[1]), 3.5, 3.5, gy - 0.5, gy + 18, axis, (0.68, 0.66, 0.62), 0, 1, (0.4, 0.38, 0.36))
    # farmhouses over the hills, a barn beside some
    farms = 0
    for _ in range(400):
        r = rng.uniform(GRASS_R * 1.15, 3500)
        t = rng.uniform(0, 2 * math.pi)
        dx, dz = r * math.sin(t), -r * math.cos(t)
        if town_mask(np.array([dx]), np.array([dz]))[0] > 0.05 or woods(np.array([dx]), np.array([dz]))[0] > 0.3:
            continue
        rot = rng.uniform(0, math.pi)
        house(parts, rng, (CX + dx, CZ + dz), rot, 0.18)
        if rng.random() < 0.6:
            house(parts, rng, (CX + dx + 14 * math.cos(rot + 1.4), CZ + dz + 14 * math.sin(rot + 1.4)), rot + 0.1, 0.0)
        farms += 1
        if farms >= 70:
            break
    ob = parts.done("bd_town", coll, mats)
    lo = lamps.done("bd_lamps", coll, mats)
    print("TOWN", n, "houses,", farms, "farms,", len(lamps.f), "lamp faces")
    return ob, lo


def hazed(nt, surf, night, L, emissive=False):
    """Mix a surface shader toward the horizon haze by its distance from the camera: fac = 1 - exp(-d / L)."""
    cd = nt.nodes.new("ShaderNodeCameraData")
    dv = nt.nodes.new("ShaderNodeMath")
    dv.operation = "DIVIDE"
    dv.inputs[1].default_value = -L
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = "EXPONENT"
    sub = nt.nodes.new("ShaderNodeMath")
    sub.operation = "SUBTRACT"
    sub.inputs[0].default_value = 1.0
    nt.links.new(cd.outputs["View Distance"], dv.inputs[0])
    nt.links.new(dv.outputs[0], ex.inputs[0])
    nt.links.new(ex.outputs[0], sub.inputs[1])
    haze = nt.nodes.new("ShaderNodeEmission")
    haze.inputs["Color"].default_value = (*(HAZE_N if night else HAZE_D), 1)
    if emissive:                                                # a light shows through the haze rather than turning into it
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = 0.35
        nt.links.new(sub.outputs[0], mul.inputs[0])
        sub = mul
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(sub.outputs[0], mix.inputs[0])
    nt.links.new(surf, mix.inputs[1])
    nt.links.new(haze.outputs[0], mix.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mix.outputs[0], out.inputs["Surface"])


HAZE_D = (0.62, 0.72, 0.86)
HAZE_N = (0.016, 0.022, 0.045)


def tint_material(name, night, L, ground=False):
    """Diffuse with the mesh's `tint` colour; the ground also gets fields (Voronoi cells) and their hedgerows (the cells' edges)."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = new_nodes(m)
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "tint"
    col = at.outputs["Color"]
    if ground:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        vor = nt.nodes.new("ShaderNodeTexVoronoi")
        vor.inputs["Scale"].default_value = 1 / 110.0
        nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
        hue = nt.nodes.new("ShaderNodeValToRGB")                   # a field's crop: grass, pale hay, deep green, olive
        cr = hue.color_ramp
        cr.interpolation = "CONSTANT"
        cr.elements[0].position, cr.elements[0].color = 0.0, (1.0, 1.0, 1.0, 1)
        for p, c in ((0.35, (1.25, 1.18, 0.8)), (0.55, (0.82, 0.9, 0.85)), (0.75, (1.6, 1.4, 0.75)), (0.9, (1.08, 1.0, 0.75))):
            e = cr.elements.new(p)
            e.color = (*c, 1)
        nt.links.new(vor.outputs["Color"], hue.inputs["Fac"])
        mul = nt.nodes.new("ShaderNodeMix")
        mul.data_type = "RGBA"
        mul.blend_type = "MULTIPLY"
        mul.inputs[0].default_value = 1.0
        nt.links.new(col, mul.inputs[6])
        nt.links.new(hue.outputs["Color"], mul.inputs[7])
        edge = nt.nodes.new("ShaderNodeTexVoronoi")
        edge.feature = "DISTANCE_TO_EDGE"
        edge.inputs["Scale"].default_value = 1 / 110.0
        nt.links.new(tc.outputs["Object"], edge.inputs["Vector"])
        hr = nt.nodes.new("ShaderNodeMapRange")                     # hedgerows about 3 m wide
        hr.inputs["From Min"].default_value, hr.inputs["From Max"].default_value = 0.012, 0.03
        hr.inputs["To Min"].default_value, hr.inputs["To Max"].default_value = 1.0, 0.0
        nt.links.new(edge.outputs["Distance"], hr.inputs["Value"])
        mx = nt.nodes.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        nt.links.new(hr.outputs[0], mx.inputs[0])
        nt.links.new(mul.outputs[2], mx.inputs[6])
        mx.inputs[7].default_value = (0.035, 0.075, 0.025, 1)
        col = mx.outputs[2]
    bs = nt.nodes.new("ShaderNodeBsdfDiffuse")
    nt.links.new(col, bs.inputs["Color"])
    hazed(nt, bs.outputs[0], night, L)
    return m


def window_material(name, night, lit, L):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = new_nodes(m)
    if night and lit:
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = (1.0, 0.70, 0.36, 1)
        e.inputs["Strength"].default_value = arg("--lit", 14.0, float)
        hazed(nt, e.outputs[0], night, L, emissive=True)
    else:
        g = nt.nodes.new("ShaderNodeBsdfPrincipled")
        g.inputs["Base Color"].default_value = (0.03, 0.04, 0.05, 1) if not night else (0.004, 0.005, 0.007, 1)
        g.inputs["Roughness"].default_value = 0.15
        hazed(nt, g.outputs[0], night, L)
    return m


def lamp_material(name, night, L):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = new_nodes(m)
    if night:
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = (1.0, 0.62, 0.25, 1)
        e.inputs["Strength"].default_value = arg("--lamp", 10.0, float)
        hazed(nt, e.outputs[0], night, L, emissive=True)
    else:
        t = nt.nodes.new("ShaderNodeBsdfTransparent")
        o = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(t.outputs[0], o.inputs["Surface"])
    return m


# the sun (by day) and the moon (by night), as compass bearing and elevation in degrees
SUN = (arg("--sun-bearing", 215.0, float), arg("--sun-elev", 52.0, float))
MOON = (arg("--moon-bearing", 150.0, float), arg("--moon-elev", 26.0, float))


def dir_of(bearing, elev):
    b, e = math.radians(bearing), math.radians(elev)
    return Vector((math.sin(b) * math.cos(e), math.cos(b) * math.cos(e), math.sin(e)))     # Blender: +Y north, +X east, +Z up


def math_node(nt, op, a, b=None, v=None):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    nt.links.new(a, n.inputs[0])
    if b is not None:
        nt.links.new(b, n.inputs[1])
    elif v is not None:
        n.inputs[1].default_value = v
    return n.outputs[0]


def sky_world(night):
    """The painted sky for camera rays: by day a clear sky, pale at the horizon to blue overhead, with the sun and its glow; by night a deep navy
    with stars, the moon and its halo, and a faint warm glow over the town. Every other ray sees a plain sky light."""
    w = bpy.data.worlds.get("BackdropSky") or bpy.data.worlds.new("BackdropSky")
    nt = new_nodes(w)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    dirn = tc.outputs["Generated"]
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(dirn, sep.inputs[0])
    up = sep.outputs["Z"]
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(up, ramp.inputs["Fac"])
    cr = ramp.color_ramp
    if night:
        stops = [(0.0, (0.030, 0.036, 0.070)), (0.05, (0.016, 0.022, 0.052)), (0.25, (0.006, 0.009, 0.026)), (1.0, (0.002, 0.003, 0.010))]
    else:
        stops = [(0.0, (0.74, 0.82, 0.93)), (0.05, (0.60, 0.72, 0.90)), (0.25, (0.33, 0.52, 0.84)), (0.6, (0.18, 0.36, 0.74)), (1.0, (0.12, 0.27, 0.64))]
    cr.elements[0].position, cr.elements[0].color = stops[0][0], (*stops[0][1], 1)
    cr.elements[1].position, cr.elements[1].color = stops[-1][0], (*stops[-1][1], 1)
    for p, c in stops[1:-1]:
        e = cr.elements.new(p)
        e.color = (*c, 1)
    col = ramp.outputs["Color"]

    def add_col(col, fac, rgb):
        mx = nt.nodes.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        mx.blend_type = "ADD"
        mx.clamp_result = False
        mx.clamp_factor = False
        nt.links.new(fac, mx.inputs[0])
        nt.links.new(col, mx.inputs[6])
        mx.inputs[7].default_value = (*rgb, 1)
        return mx.outputs[2]

    def glow(d, terms):
        dot = nt.nodes.new("ShaderNodeVectorMath")
        dot.operation = "DOT_PRODUCT"
        dot.inputs[1].default_value = d
        nt.links.new(dirn, dot.inputs[0])
        c = math_node(nt, "MAXIMUM", dot.outputs["Value"], v=0.0)
        tot = None
        for pw, k in terms:
            t = math_node(nt, "MULTIPLY", math_node(nt, "POWER", c, v=pw), v=k)
            tot = t if tot is None else math_node(nt, "ADD", tot, t)
        return tot, dot.outputs["Value"]

    above = nt.nodes.new("ShaderNodeMapRange")
    above.inputs["From Min"].default_value, above.inputs["From Max"].default_value = 0.0, 0.12
    nt.links.new(up, above.inputs["Value"])
    if not night:
        g, dv = glow(dir_of(*SUN), ((6.0, 0.10), (60.0, 0.35), (2000.0, 3.0)))
        col = add_col(col, g, (1.0, 0.93, 0.80))
        disc = nt.nodes.new("ShaderNodeMapRange")                     # the sun's disc, 1.2 degrees across
        disc.inputs["From Min"].default_value, disc.inputs["From Max"].default_value = math.cos(math.radians(0.62)), math.cos(math.radians(0.55))
        disc.inputs["To Max"].default_value = 40.0
        nt.links.new(dv, disc.inputs["Value"])
        col = add_col(col, disc.outputs[0], (1.0, 0.97, 0.9))
    else:
        md = dir_of(*MOON)
        g, dv = glow(md, ((8.0, 0.012), (120.0, 0.05), (3000.0, 0.25)))
        col = add_col(col, g, (0.75, 0.82, 1.0))
        # stars: two layers of Voronoi cells on the view direction, one bright point in a few cells, fading toward the horizon
        for scale, keep, k in ((140.0, 0.975, 8.0), (330.0, 0.96, 1.2)):
            vo = nt.nodes.new("ShaderNodeTexVoronoi")
            vo.inputs["Scale"].default_value = scale
            vo.inputs["Randomness"].default_value = 0.85
            nt.links.new(dirn, vo.inputs["Vector"])
            pt = nt.nodes.new("ShaderNodeMapRange")
            pt.inputs["From Min"].default_value, pt.inputs["From Max"].default_value = 0.13, 0.0
            nt.links.new(vo.outputs["Distance"], pt.inputs["Value"])
            pt2 = math_node(nt, "POWER", pt.outputs[0], v=2.0)
            sc_ = nt.nodes.new("ShaderNodeSeparateColor")
            nt.links.new(vo.outputs["Color"], sc_.inputs[0])
            sel = nt.nodes.new("ShaderNodeMapRange")
            sel.inputs["From Min"].default_value, sel.inputs["From Max"].default_value = keep, 1.0
            nt.links.new(sc_.outputs[0], sel.inputs["Value"])
            br = math_node(nt, "MULTIPLY", math_node(nt, "MULTIPLY", pt2, sel.outputs[0]), above.outputs[0])
            col = add_col(col, math_node(nt, "MULTIPLY", br, v=k), (0.95, 0.96, 1.0))
        disc = nt.nodes.new("ShaderNodeMapRange")                     # the moon, 1.8 degrees across (drawn larger than life), with soft grey seas
        disc.inputs["From Min"].default_value, disc.inputs["From Max"].default_value = math.cos(math.radians(0.92)), math.cos(math.radians(0.84))
        nt.links.new(dv, disc.inputs["Value"])
        seas = nt.nodes.new("ShaderNodeTexNoise")
        seas.inputs["Scale"].default_value = 260.0
        seas.inputs["Detail"].default_value = 3.0
        nt.links.new(dirn, seas.inputs["Vector"])
        sr = nt.nodes.new("ShaderNodeMapRange")
        sr.inputs["From Min"].default_value, sr.inputs["From Max"].default_value = 0.42, 0.62
        sr.inputs["To Min"].default_value, sr.inputs["To Max"].default_value = 1.0, 0.72
        nt.links.new(seas.outputs["Fac"], sr.inputs["Value"])
        col = add_col(col, math_node(nt, "MULTIPLY", math_node(nt, "MULTIPLY", disc.outputs[0], sr.outputs[0]), v=2.4), (0.95, 0.94, 0.88))
        town = dir_of(math.degrees(TOWN_BEARING), 0.0)            # the town's glow, low over the horizon past the back hedge
        tg, _ = glow(town, ((10.0, 1.0),))
        low = nt.nodes.new("ShaderNodeMapRange")
        low.inputs["From Min"].default_value, low.inputs["From Max"].default_value = 0.16, 0.0
        nt.links.new(up, low.inputs["Value"])
        col = add_col(col, math_node(nt, "MULTIPLY", math_node(nt, "MULTIPLY", tg, low.outputs[0]), v=0.05), (1.0, 0.62, 0.32))
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(col, bg.inputs["Color"])
    amb = nt.nodes.new("ShaderNodeBackground")
    amb.inputs["Color"].default_value = (0.45, 0.58, 0.82, 1) if not night else (0.012, 0.016, 0.034, 1)
    amb.inputs["Strength"].default_value = 1.0
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(amb.outputs[0], mix.inputs[1])
    nt.links.new(bg.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    bpy.context.scene.world = w
    return w


def assign(objs, night):
    L = 5200.0 if not night else 3800.0
    ground = tint_material(f"bd_ground_{'night' if night else 'day'}", night, L, ground=True)
    trees = tint_material(f"bd_trees_{'night' if night else 'day'}", night, L)
    town = [tint_material(f"bd_walls_{'night' if night else 'day'}", night, L), tint_material(f"bd_roofs_{'night' if night else 'day'}", night, L),
            window_material(f"bd_window_{'night' if night else 'day'}", night, False, L),
            window_material(f"Window_Lit_{'night' if night else 'day'}", night, True, L), lamp_material(f"bd_lamp_{'night' if night else 'day'}", night, L)]
    for ob in objs:
        me = ob.data
        if ob.name == "bd_terrain":
            me.materials.clear()
            me.materials.append(ground)
        elif ob.name == "bd_trees":
            me.materials.clear()
            me.materials.append(trees)
        else:
            for i, mt in enumerate(town):
                me.materials[i] = mt


KEEP_SYS = ("cycles", "eevee")


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private():
    """The .blend is public: drop every custom property, blank the render output path and every stamp, and the file browser's remembered folder."""
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
                    if st is not idb and k.startswith(KEEP_SYS):
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
    for scr in bpy.data.screens:
        for a in scr.areas:
            for sp in a.spaces:
                if sp.type == "FILE_BROWSER" and getattr(sp, "params", None):
                    sp.params.directory = b"_" * 1000
                    sp.params.directory = b"//"
    for im in list(bpy.data.images):
        bpy.data.images.remove(im)                              # no images in this scene: the render results are not kept


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    scrub_private()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    scrub_private()
    bpy.ops.wm.save_mainfile(compress=True)
    print("BLEND", BLEND.relative_to(ROOT).as_posix(), BLEND.stat().st_size)


def stage_backdrops():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.name = "parking_lot_backdrop"
    print("LOT", json.dumps(EXT), "grass radius", GRASS_R)
    coll = bpy.data.collections.new("Backdrop")
    sc.collection.children.link(coll)
    rng = np.random.default_rng(1208)
    terrain = build_terrain(coll)
    trees = build_trees(coll, rng)
    placeholder = [bpy.data.materials.new(f"slot_{i}") for i in range(5)]
    town, lamps = build_town(coll, rng, placeholder)
    objs = [terrain, trees, town, lamps]
    setup_cycles(arg("--bd-samples", 128, int))
    pano_camera()
    orientation_test([coll])
    sun = bpy.data.objects.new("bd_sun", bpy.data.lights.new("bd_sun", "SUN"))
    coll.objects.link(sun)
    scale = arg("--scale", 100, int)
    only = arg("--only", "day,night").split(",")
    for night in (False, True):
        k = "night" if night else "day"
        if k not in only:
            continue
        assign(objs, night)
        d = dir_of(*(MOON if night else SUN))
        sun.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        sun.data.energy = 0.06 if night else 4.2
        sun.data.color = (0.70, 0.78, 1.0) if night else (1.0, 0.95, 0.86)
        sun.data.angle = math.radians(0.6)
        sky_world(night)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, scale
        sc.view_settings.view_transform = "Standard"
        sc.view_settings.look = "None"
        sc.view_settings.exposure = arg("--exposure-night" if night else "--exposure-day", 0.0, float)
        sc.render.image_settings.file_format = "PNG"
        sc.render.image_settings.color_mode = "RGB"
        sc.render.image_settings.color_depth = "8"
        path = stage_work() / f"backdrop_{k}.png"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print("BACKDROP", path, path.stat().st_size)
    if arg("--save", "1") == "1":
        assign(objs, False)
        sky_world(False)
        save_blend()


if __name__ == "__main__":
    if STAGE == "survey":
        stage_survey()
    elif STAGE == "backdrops":
        stage_backdrops()
    else:
        print("in Blender only --stage survey and --stage backdrops run")
