"""Renders the Overworld's four sky backdrops (docs/BLENDER.md, R3; docs/BLENDER_AREAS.md section 4, "Skies"): four 4096 x 2048 equirect panoramas,

    world/backdrops/overworld_clear_day.webp   docs/WORLD.md's "clear with no clouds"
    world/backdrops/overworld_sunset.webp      "sunrise and sunset": one warm low sun in the west-south-west, 11 degrees up (just clear of the ridges), for the evening and the morning
    world/backdrops/overworld_night.webp       "a bright starry night": stars, the Milky Way, the moon, lit windows
    world/backdrops/overworld_painted.webp     "drifting anime clouds": a stylised, hand-painted sky of cel-shaded cumulus

The ground in the lower half is the parking-lot backdrop's (tools/blender/build_parking_lot_backdrop.py, draft PR #91): the same seeded height
function, fields, copses, farmhouses and the town past the back hedge, taken from the same point (the lot's Spawn marker at eye height), so the five
backdrops agree. One thing is added: the store, far off to the north, so that the Overworld's scenes that do not hold the store's model (the hills,
the road, the market, the playground) still see it there. It is drawn 2.4 times its size 360 m north of the arrival point; from the lot itself the
store's own model, 16 m away, covers it completely.

Re-runnable, from the repo root:

    blender -b --factory-startup --python tools/blender/build_overworld_skies.py -- --stage skies --work <work> [--bd-samples 128] [--only clear_day,night]
        (builds the ground, the town and the store in a new scene, runs the orientation self-check before each sky, renders <work>/sky_<name>.png,
         and saves blender/scenes/overworld_skies.blend, which is not committed)
    python tools/blender/build_overworld_skies.py --stage pack --work <work>                 (the PNGs -> WebP, each at most 1 MB)
    python tools/blender/build_overworld_skies.py --stage check [--only ...]                 (the gates on the WebPs: size, bytes, where the sun is)
    python tools/blender/build_overworld_skies.py --stage sheet --work <work> --out <png>    (an owner sheet: all four panoramas and flat views)
    python tools/blender/build_overworld_skies.py --stage previews --work <work>             (two JPEG stills per sky -> docs/renders/overworld_skies/)

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
except ImportError:                       # the pack, check, sheet and previews stages run in plain Python (numpy and Pillow)
    bpy = None

ROOT = Path(__file__).resolve().parents[2]
LOT = ROOT / "world/parking_lot.json"
BLEND = ROOT / "blender/scenes/overworld_skies.blend"
STILLS = ROOT / "docs/renders/overworld_skies"
OUT = ROOT / "world/backdrops"
W, H = 4096, 2048
SKIES = ("clear_day", "sunset", "night", "painted")

if "--" in sys.argv:
    args = sys.argv[sys.argv.index("--") + 1:]
else:
    args = sys.argv[1:] if bpy is None else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


STAGE = arg("--stage", "skies")
DEVICE = arg("--device", "auto")


def stage_work():
    d = Path(arg("--work", str(Path(os.environ.get("TEMP", "/tmp")) / "farway_overworld_skies")))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- the lot, from its collision file (as the parking-lot backdrop reads it)
def lot_extent():
    doc = json.loads(LOT.read_text())
    by = {}
    for c in doc["colliders"]:
        by.setdefault(c["s"], []).append(c)
    asphalt = by["Ground_LOT_Exterior_asphalt"][0]
    grass = by["Ground_LOT_Exterior_grass"]
    store = [c for k, v in by.items() if k.startswith("Wall_L4_Store") for c in v]
    ext = {
        "floor": round(asphalt["max"][1], 2),
        "grass": (min(g["min"][0] for g in grass), min(g["min"][2] for g in grass), max(g["max"][0] for g in grass), max(g["max"][2] for g in grass)),
        # the store's footprint and wall height (its four outer walls), for the far store's proportions
        "store": (min(c["min"][0] for c in store), min(c["min"][2] for c in store), max(c["max"][0] for c in store), max(c["max"][2] for c in store),
                  max(c["max"][1] for c in store) - asphalt["max"][1]),
    }
    spawn = next(m for m in doc["markers"] if m["kind"] == "Spawn")["position"]
    ext["spawn"] = spawn
    ext["centre"] = (spawn[0], spawn[1] + 1.6, spawn[2])
    return ext


EXT = lot_extent()
CX, CY, CZ = EXT["centre"]
FLOOR = EXT["floor"]
GRASS_R = min(abs(EXT["grass"][0] - CX), abs(EXT["grass"][2] - CX), abs(EXT["grass"][1] - CZ), abs(EXT["grass"][3] - CZ))


# ---------------------------------------------------------------- noise and heights: the parking-lot backdrop's, unchanged (same seeds, same ground)
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


TOWN_BEARING = math.radians(188.0)
TOWN_R = (430.0, 1250.0)
TOWN_HALF = math.radians(34.0)
STORE_DIST, STORE_SCALE = 360.0, 2.4          # the far store: this far north of the arrival point, this many times its size


def bearing_of(dx, dz):
    return np.mod(np.arctan2(dx, -dz), 2 * math.pi)


def town_mask(dx, dz):
    r = np.hypot(dx, dz)
    d = np.abs(np.mod(bearing_of(dx, dz) - TOWN_BEARING + math.pi, 2 * math.pi) - math.pi)
    return (1 - smooth(TOWN_HALF * 0.75, TOWN_HALF * 1.5, d)) * smooth(TOWN_R[0] - 120, TOWN_R[0] + 40, r) * (1 - smooth(TOWN_R[1], TOWN_R[1] + 500, r))


def height(dx, dz):
    x, z = dx + CX, dz + CZ
    r = np.hypot(dx, dz)
    ramp = smooth(GRASS_R * 0.85, GRASS_R * 2.2, r)
    roll = fbm(N1, x / 430.0, z / 430.0, 5)
    hills = 95.0 * (roll - 0.30) + 0.03 * np.maximum(r - GRASS_R, 0)
    ridges = smooth(1400, 6000, r) * (1000.0 * fbm(N2, x / 2300.0, z / 2300.0, 4) ** 1.6 + 0.03 * r)
    far = smooth(8000, 16000, r) * 1100.0 * fbm(N3, x / 5200.0, z / 5200.0, 3)
    wild = ramp * np.maximum(hills, 0.0) + ridges + far
    tm = town_mask(dx, dz)
    slope = 0.11 * np.maximum(r - (TOWN_R[0] - 60), 0) + 6.0 * (fbm(N4, x / 260.0, z / 260.0, 3) - 0.5)
    return FLOOR - 0.05 + wild * (1 - tm) + np.maximum(slope, 0) * tm


def woods(dx, dz):
    x, z = dx + CX, dz + CZ
    w = smooth(0.56, 0.68, fbm(N3, x / 300.0, z / 300.0, 4))
    return w * (1 - town_mask(dx, dz)) * smooth(GRASS_R, GRASS_R * 1.3, np.hypot(dx, dz))


# ---------------------------------------------------------------- the four skies: the sun (or moon) as compass bearing and elevation, and the light
SKY = {
    "clear_day": dict(sun=(215.0, 52.0), energy=4.2, sun_col=(1.0, 0.95, 0.86), amb=(0.45, 0.58, 0.82), haze=(0.62, 0.72, 0.86), L=5200.0,
                      lit=0.0, lamp=0.0, boost=None),
    "sunset": dict(sun=(255.0, 11.0), energy=3.4, sun_col=(1.0, 0.56, 0.30), amb=(0.34, 0.30, 0.42), haze=(0.80, 0.56, 0.50), L=4600.0,
                   lit=5.0, lamp=6.0, boost=None),
    "night": dict(sun=(150.0, 26.0), energy=0.06, sun_col=(0.70, 0.78, 1.0), amb=(0.012, 0.016, 0.034), haze=(0.016, 0.022, 0.045), L=3800.0,
                  lit=14.0, lamp=10.0, boost=None),
    "painted": dict(sun=(200.0, 46.0), energy=4.6, sun_col=(1.0, 0.96, 0.88), amb=(0.50, 0.64, 0.90), haze=(0.66, 0.80, 0.96), L=6000.0,
                    lit=0.0, lamp=0.0, boost=(1.35, 1.10)),
}


def sun_column(bearing):
    """The picture column (0..W) a compass bearing falls on: north in the middle, east three quarters across."""
    return ((0.5 + bearing / 360.0) % 1.0) * W


# ================================================================ the stages without Blender
def stage_pack():
    from PIL import Image
    work = Path(arg("--work", "."))
    OUT.mkdir(parents=True, exist_ok=True)
    for k in arg("--only", ",".join(SKIES)).split(","):
        im = Image.open(work / f"sky_{k}.png").convert("RGB")
        assert im.size == (W, H), im.size
        dst = OUT / f"overworld_{k}.webp"
        for q in (95, 92, 90, 88, 85, 82, 80, 77, 74, 70, 66, 62, 58, 54, 50):
            im.save(dst, "WEBP", quality=q, method=6)           # Pillow writes no EXIF or XMP chunk unless given one
            if dst.stat().st_size <= 1_000_000:
                break
        print(f"{dst.relative_to(ROOT).as_posix()}  {im.size}  q{q}  {dst.stat().st_size / 1e3:.0f} KB")


def stage_check():
    """The gates on the packed files: 4096 x 2048, at most 1 MB, a plain RIFF/WEBP with no EXIF or XMP chunk, ground below the horizon, and
    the sun (by day, at sunset, painted) or the moon (at night) in the column its bearing gives (middle north, right east)."""
    from PIL import Image
    ok = True
    for k in arg("--only", ",".join(SKIES)).split(","):
        p = OUT / f"overworld_{k}.webp"
        b = p.read_bytes()
        im = Image.open(p)
        size_ok = im.size == (W, H)
        bytes_ok = len(b) <= 1_000_000
        chunks, i = [], 12
        while i + 8 <= len(b):
            cid, n = b[i:i + 4].decode("latin-1"), int.from_bytes(b[i + 4:i + 8], "little")
            chunks.append(cid)
            i += 8 + n + (n & 1)
        meta_ok = b[:4] == b"RIFF" and b[8:12] == b"WEBP" and not ({"EXIF", "XMP "} & set(chunks))
        a = np.asarray(im.convert("RGB"), np.float32)
        lum = a.mean(-1)
        # the sun's or moon's disc: a saturated spot at the column its bearing gives and the row its elevation gives, and not at the
        # mirrored bearings (a left-right or front-back flip would move it there)
        bearing, el = SKY[k]["sun"]
        row = int(round(H / 2 - el / 90.0 * (H / 2)))

        def spot(bear):
            c = int(round(sun_column(bear))) % W
            return float(lum[row - 2: row + 3, [(c + d) % W for d in range(-2, 3)]].mean())
        here, flips = spot(bearing), [spot(360.0 - bearing), spot(bearing + 180.0), spot(180.0 - bearing)]
        sun_ok = here >= 240 and max(f for f, bb in zip(flips, (360.0 - bearing, bearing + 180.0, 180.0 - bearing))
                                       if abs((bb - bearing + 180) % 360 - 180) > 3) < 0.8 * here
        ground = float(lum[H // 2 + 40: H // 2 + 400].mean())
        line = (f"{p.name}: {im.size[0]} x {im.size[1]} {'ok' if size_ok else 'WRONG'}; {len(b):,} bytes {'ok' if bytes_ok else 'OVER 1 MB'}; "
                f"chunks {chunks} {'ok' if meta_ok else 'METADATA'}; {'moon' if k == 'night' else 'sun'} at bearing {bearing:.0f}, {el:.0f} up "
                f"(column {sun_column(bearing):.0f}, row {row}): {here:.0f}, at the mirrored bearings {[round(f) for f in flips]} "
                f"{'ok' if sun_ok else 'WRONG'}; mean ground below the horizon {ground:.0f}")
        print(line)
        ok &= size_ok and bytes_ok and meta_ok and sun_ok
    print("CHECK", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


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


def load_pano(work, k):
    from PIL import Image
    src = OUT / f"overworld_{k}.webp"
    return Image.open(src if src.exists() else work / f"sky_{k}.png").convert("RGB")


NAMES = {"clear_day": "clear day", "sunset": "sunset (and sunrise)", "night": "night", "painted": "painted (drifting anime clouds)"}


def stage_sheet():
    from PIL import Image, ImageDraw
    work = Path(arg("--work", "."))
    dst = Path(arg("--out", str(work / "owner_overworld_skies.png")))
    pw, ph = 2000, 1000
    vw, vh = 500, 282
    pad, lab = 16, 30
    rows = []
    for k in SKIES:
        pano = load_pano(work, k)
        rows.append(("pano", k, pano.resize((pw, ph), Image.LANCZOS)))
        rows.append(("views", k, [Image.fromarray(equirect_view(pano, yaw, size=(vw, vh), pitch_deg=8.0)) for yaw in (0, 90, 180, 270)]))
    hgt = pad + 40 + sum(lab + (ph if kind == "pano" else vh) + pad for kind, _, _ in rows)
    sheet = Image.new("RGB", (pw + 2 * pad, hgt), (24, 24, 28))
    dr = ImageDraw.Draw(sheet)
    dr.text((pad, pad + 6), "Farway Overworld: the four default sky backdrops (R3). Each 4096 x 2048 equirect, middle north (-z), right east (+x). "
            "Defaults the owner can replace.", fill=(255, 255, 255))
    y = pad + 40
    views = ("north (the store, far off)", "east", "south (the town)", "west")
    for kind, k, im in rows:
        if kind == "pano":
            kb = (OUT / f"overworld_{k}.webp").stat().st_size / 1e3 if (OUT / f"overworld_{k}.webp").exists() else 0
            dr.text((pad, y + 8), f"{NAMES[k]}: world/backdrops/overworld_{k}.webp, {kb:.0f} KB, shown at {pw} x {ph}", fill=(235, 235, 235))
            y += lab
            sheet.paste(im, (pad, y))
            for frac, t in ((0.0, "S"), (0.25, "W"), (0.5, "N"), (0.75, "E")):
                dr.text((pad + int(frac * pw) + 4, y + 4), t, fill=(255, 60, 60))
            y += ph + pad
        else:
            dr.text((pad, y + 8), f"{NAMES[k]}: flat 90-degree views out of the panorama", fill=(200, 200, 200))
            y += lab
            for i, v in enumerate(im):
                x = pad + i * vw
                sheet.paste(v, (x, y))
                dr.text((x + 6, y + 6), views[i], fill=(255, 255, 255))
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


# two review stills per sky: (yaw, pitch, what it shows)
PREVIEWS = {
    "clear_day": ((0.0, 6.0, "north"), (180.0, 4.0, "south")),
    "sunset": ((255.0, 8.0, "west"), (0.0, 6.0, "north")),
    "night": ((150.0, 14.0, "southeast"), (0.0, 18.0, "north")),
    "painted": ((0.0, 14.0, "north"), (200.0, 20.0, "south")),
}


def stage_previews():
    from PIL import Image
    work = Path(arg("--work", "."))
    STILLS.mkdir(parents=True, exist_ok=True)
    for k in arg("--only", ",".join(SKIES)).split(","):
        pano = load_pano(work, k)
        for i, (yaw, pitch, what) in enumerate(PREVIEWS[k], start=1):
            v = Image.fromarray(equirect_view(pano, yaw, hfov=75.0, size=(1920, 1080), pitch_deg=pitch))
            p = STILLS / f"{k}_{i}_{what}.jpg"
            v.save(p, "JPEG", quality=86)
            strip_jpeg_meta(p)
            print("STILL", p.relative_to(ROOT).as_posix(), p.stat().st_size)


if bpy is None:
    {"pack": stage_pack, "check": stage_check, "sheet": stage_sheet, "previews": stage_previews}.get(
        STAGE, lambda: print("without Blender only --stage pack, check, sheet and previews run"))()
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


def orientation_test(hide, label):
    """Three glowing markers far out (red east, green north, blue south) on a black sky, rendered small: the picture's middle column must be green,
    three quarters across red, and the edges blue (docs/BLENDER.md R3: the middle faces north, the right east). Run before every sky's render,
    with that sky's camera and render settings."""
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
    keep_res = (sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage)
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 256, 128, 100
    keep = sc.cycles.samples
    sc.cycles.samples = 4
    sc.render.image_settings.file_format = "PNG"
    path = stage_work() / f"orient_test_{label}.png"
    sc.render.filepath = str(path)
    keep_vt = sc.view_settings.view_transform
    sc.view_settings.view_transform = "Standard"
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(str(path))
    a = np.empty(256 * 128 * 4, np.float32)
    im.pixels.foreach_get(a)
    a = a.reshape(128, 256, 4)[64]                               # the horizon row

    def centre(ch):
        on = np.nonzero(a[:, ch] > 0.5 * a[:, ch].max())[0]
        if on.size and on.max() - on.min() > 128:
            on = np.where(on < 128, on + 256, on)
        return int(round(on.mean())) % 256
    col_of = {c: centre(i) for i, c in enumerate(("red", "green", "blue"))}
    print(f"ORIENT {label}: columns of the markers on the horizon row:", col_of)
    assert abs(col_of["green"] - 128) <= 4, "north is not in the middle"
    assert abs(col_of["red"] - 192) <= 4, "east is not three quarters across (the right)"
    assert min(col_of["blue"], 255 - col_of["blue"]) <= 4, "south is not at the edges"
    print(f"ORIENT PASS {label}: middle north (-z), right east (+x)")
    bpy.data.images.remove(im)
    for o in list(tmp.objects):
        bpy.data.objects.remove(o)
    bpy.data.collections.remove(tmp)
    sc.world = keep_world
    bpy.data.worlds.remove(w)
    sc.cycles.samples = keep
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = keep_res
    sc.view_settings.view_transform = keep_vt
    for c in hide:
        c.hide_render = False


# ---------------------------------------------------------------- the ground, the trees and the town: the parking-lot backdrop's, unchanged
def mesh_from(name, verts, faces, coll, attrs=None, mats=None, mat_index=None):
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
    rs = np.concatenate([np.geomspace(0.02, GRASS_R * 0.5, 40, endpoint=False), np.linspace(GRASS_R * 0.5, 700, 70, endpoint=False), np.geomspace(700, 30000, 190)])
    na = 1440
    th = np.linspace(0, 2 * math.pi, na, endpoint=False)
    R, T = np.meshgrid(rs, th, indexing="ij")
    dx, dz = R * np.sin(T), -R * np.cos(T)
    y = height(dx, dz)
    verts = np.stack([CX + dx, -(CZ + dz), y], -1).reshape(-1, 3)
    ii, jj = np.meshgrid(np.arange(len(rs) - 1), np.arange(na), indexing="ij")
    a = ii * na + jj
    b = ii * na + (jj + 1) % na
    faces = np.stack([a, (ii + 1) * na + jj, (ii + 1) * na + (jj + 1) % na, b], -1).reshape(-1, 4)
    fx, fz = dx[:-1].ravel(), dz[:-1].ravel()
    wd = woods(fx, fz)
    meadow = fbm(N2, (fx + CX) / 90.0, (fz + CZ) / 90.0, 2)
    tint = np.stack([0.11 + 0.05 * meadow, 0.24 + 0.05 * meadow, 0.055 + 0.02 * meadow], -1)
    tint = tint * (1 - 0.62 * wd[:, None])
    tm = town_mask(fx, fz)
    tint = tint * (1 - 0.35 * tm[:, None]) + np.array([0.16, 0.16, 0.14]) * 0.35 * tm[:, None]
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
    """Faces (quads) with a colour and a material slot each: 0 wall, 1 roof, 2 window, 3 lit window, 4 lamp (the store: its sign)."""

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

        def P(u, w, y):
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
    if not big:
        rise = rng.uniform(2.2, 3.6)
        o = 0.35
        ridge = top + rise
        parts.quad([P(-hw - o, -hd - o, top - 0.2), P(hw + o, -hd - o, top - 0.2), P(hw + o, 0, ridge), P(-hw - o, 0, ridge)], roof, 1)
        parts.quad([P(hw + o, hd + o, top - 0.2), P(-hw - o, hd + o, top - 0.2), P(-hw - o, 0, ridge), P(hw + o, 0, ridge)], roof, 1)
        parts.quad([P(-hw, -hd, top), P(-hw, 0, ridge - 0.1), P(-hw, 0, ridge - 0.1), P(-hw, hd, top)], wall, 0)
        parts.quad([P(hw, hd, top), P(hw, 0, ridge - 0.1), P(hw, 0, ridge - 0.1), P(hw, -hd, top)], wall, 0)
        if rng.random() < 0.5:
            parts.box((gx + 0.5 * hw * math.cos(rot), gz + 0.5 * hw * math.sin(rot)), 0.35, 0.35, top, ridge + 0.9, rot, wall * 0.8, 0)
    else:
        parts.box(c, hw + 0.15, hd + 0.15, top, top + 0.6, rot, wall * 0.9, 0, 1, roof)
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
    parts = Parts()
    lamps = Parts()
    axis = TOWN_BEARING
    ua = np.array([math.cos(axis), math.sin(axis)])
    fwd = np.array([math.sin(axis), -math.cos(axis)])
    n = 0
    cell = 15.0
    for i in range(-80, 81):
        for j in range(0, 70):
            if j % 5 == 0 or i % 7 == 0:
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
    for (dist, side, kind) in ((TOWN_R[0] + 260, -60.0, "church"), (TOWN_R[0] + 520, 210.0, "tower"), (TOWN_R[0] + 120, 120.0, "silo")):
        p = np.array([CX, CZ]) + fwd * dist + ua * side
        gy = float(height(np.array([p[0] - CX]), np.array([p[1] - CZ]))[0])
        if kind == "church":
            parts.box((p[0], p[1]), 6.0, 13.0, gy - 0.5, gy + 11, axis + math.pi / 2, WALLS[4] * 0.9, 0, 1, ROOFS[3])
            parts.box((p[0] + 15 * fwd[0], p[1] + 15 * fwd[1]), 3.5, 3.5, gy - 0.5, gy + 26, axis, WALLS[4] * 0.85, 0)
            tip = (p[0] + 15 * fwd[0], p[1] + 15 * fwd[1])
            for k in range(4):
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


def build_store(coll, mats):
    """The store, far off to the north: a big box with the proportions of the lot's store (its walls in world/parking_lot.json), its glass front,
    entrance canopy and a red sign band facing south toward the lot, STORE_SCALE times its size, STORE_DIST m north of the arrival point.
    Slots: 0 walls, 1 roof, 2 glass, 3 lit glass (lit at night and at sunset), 4 the sign (lit at night and at sunset)."""
    x0, z0, x1, z1, wall_h = EXT["store"]
    s = STORE_SCALE
    h = wall_h * s                                                 # its wall height; everything on the front is in parts of it
    hw, hd = 0.5 * (x1 - x0) * s, 0.5 * (z1 - z0) * s
    c = (CX, CZ - STORE_DIST - hd)                                 # its front (south) face STORE_DIST m north of the arrival point
    fx = np.array([c[0] - hw, c[0] + hw, c[0] - hw, c[0] + hw, c[0]])
    fz = np.array([c[1] - hd, c[1] - hd, c[1] + hd, c[1] + hd, c[1] + hd])
    gh = height(fx - CX, fz - CZ)
    g0, base = float(gh.max()), float(gh.min()) - 0.4              # it stands level on the highest corner; its walls go down into the ground
    p = Parts()
    wall, roof, trim = (0.80, 0.80, 0.78), (0.42, 0.43, 0.45), (0.86, 0.86, 0.86)
    P = p.box(c, hw, hd, base, g0 + 1.12 * h, 0.0, wall, 0, 1, roof)                   # the body and its parapet
    f = hd + 0.06                                                  # the front face, a little proud of the wall
    p.quad([P(-0.55 * hw, f, g0 + 0.03 * h), P(0.55 * hw, f, g0 + 0.03 * h), P(0.55 * hw, f, g0 + 0.62 * h), P(-0.55 * hw, f, g0 + 0.62 * h)],
           (0, 0, 0), 3)                                           # the glass front
    for side in (-1, 1):                                           # a run of high windows either side of it
        for i in range(5):
            u = side * (0.62 * hw + i * 0.07 * hw)
            p.quad([P(u - 0.022 * hw, f, g0 + 0.66 * h), P(u + 0.022 * hw, f, g0 + 0.66 * h), P(u + 0.022 * hw, f, g0 + 0.92 * h),
                    P(u - 0.022 * hw, f, g0 + 0.92 * h)], (0, 0, 0), 2)
    # the raised middle of the front, and on it the sign band
    p.box((c[0], c[1] + hd + 0.5 * s), 0.42 * hw, 0.5 * s, base, g0 + 1.55 * h, 0.0, trim, 0, 1, roof)
    sf = hd + 1.0 * s + 0.08
    p.quad([P(-0.36 * hw, sf, g0 + 0.98 * h), P(0.36 * hw, sf, g0 + 0.98 * h), P(0.36 * hw, sf, g0 + 1.42 * h), P(-0.36 * hw, sf, g0 + 1.42 * h)],
           (0.78, 0.10, 0.10), 4)
    p.quad([P(-0.40 * hw, sf, g0 + 0.03 * h), P(0.40 * hw, sf, g0 + 0.03 * h), P(0.40 * hw, sf, g0 + 0.80 * h), P(-0.40 * hw, sf, g0 + 0.80 * h)],
           (0, 0, 0), 3)                                           # the doors' glass under it
    cz = c[1] + hd + 1.0 * s + 2.6 * s                             # the entrance canopy on its posts
    p.box((c[0], cz), 0.30 * hw, 2.6 * s, g0 + 0.80 * h, g0 + 0.88 * h, 0.0, trim, 0)
    for u in (-0.28 * hw, 0.28 * hw):
        p.box((c[0] + u, cz + 2.3 * s), 0.3, 0.3, base, g0 + 0.80 * h, 0.0, (0.55, 0.55, 0.56), 0)
    top = g0 + 1.55 * h - FLOOR
    ob = p.done("bd_store", coll, mats)
    print("STORE", {"centre": [round(c[0], 1), round(c[1], 1)], "half": [round(hw, 1), round(hd, 1)], "height": round(top, 1),
                    "front_dist": STORE_DIST, "scale": s})
    return ob


# ---------------------------------------------------------------- materials, per sky
def hazed(nt, surf, cfg, emissive=False):
    """Mix a surface shader toward the horizon haze by its distance from the camera: fac = 1 - exp(-d / L)."""
    cd = nt.nodes.new("ShaderNodeCameraData")
    dv = nt.nodes.new("ShaderNodeMath")
    dv.operation = "DIVIDE"
    dv.inputs[1].default_value = -cfg["L"]
    ex = nt.nodes.new("ShaderNodeMath")
    ex.operation = "EXPONENT"
    sub = nt.nodes.new("ShaderNodeMath")
    sub.operation = "SUBTRACT"
    sub.inputs[0].default_value = 1.0
    nt.links.new(cd.outputs["View Distance"], dv.inputs[0])
    nt.links.new(dv.outputs[0], ex.inputs[0])
    nt.links.new(ex.outputs[0], sub.inputs[1])
    haze = nt.nodes.new("ShaderNodeEmission")
    haze.inputs["Color"].default_value = (*cfg["haze"], 1)
    if emissive:
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


def boosted(nt, col, cfg):
    """The painted sky's ground: the same colours, more saturated and a little brighter, so it sits under a painted sky."""
    if not cfg["boost"]:
        return col
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Saturation"].default_value, hsv.inputs["Value"].default_value = cfg["boost"]
    nt.links.new(col, hsv.inputs["Color"])
    return hsv.outputs["Color"]


def tint_material(name, cfg, ground=False):
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
        hue = nt.nodes.new("ShaderNodeValToRGB")
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
        hr = nt.nodes.new("ShaderNodeMapRange")
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
    nt.links.new(boosted(nt, col, cfg), bs.inputs["Color"])
    hazed(nt, bs.outputs[0], cfg)
    return m


def glow_material(name, cfg, on, rgb, strength, off_rgb=None):
    """Lit at night and at sunset (an emission through the haze); by day either dark glass (off_rgb None) or a plain painted colour."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = new_nodes(m)
    if on and strength > 0:
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = (*rgb, 1)
        e.inputs["Strength"].default_value = strength
        hazed(nt, e.outputs[0], cfg, emissive=True)
    elif off_rgb is not None:
        d = nt.nodes.new("ShaderNodeBsdfDiffuse")
        d.inputs["Color"].default_value = (*off_rgb, 1)
        hazed(nt, d.outputs[0], cfg)
    else:
        g = nt.nodes.new("ShaderNodeBsdfPrincipled")
        g.inputs["Base Color"].default_value = (0.03, 0.04, 0.05, 1) if cfg["energy"] > 1 else (0.004, 0.005, 0.007, 1)
        g.inputs["Roughness"].default_value = 0.15
        hazed(nt, g.outputs[0], cfg)
    return m


def lamp_material(name, cfg):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = new_nodes(m)
    if cfg["lamp"] > 0:
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = (1.0, 0.62, 0.25, 1)
        e.inputs["Strength"].default_value = cfg["lamp"]
        hazed(nt, e.outputs[0], cfg, emissive=True)
    else:
        t = nt.nodes.new("ShaderNodeBsdfTransparent")
        o = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(t.outputs[0], o.inputs["Surface"])
    return m


def assign(objs, k):
    cfg = SKY[k]
    lit = cfg["lit"] > 0
    ground = tint_material(f"bd_ground_{k}", cfg, ground=True)
    trees = tint_material(f"bd_trees_{k}", cfg)
    walls, roofs = tint_material(f"bd_walls_{k}", cfg), tint_material(f"bd_roofs_{k}", cfg)
    window = glow_material(f"bd_window_{k}", cfg, False, (0, 0, 0), 0)
    lit_window = glow_material(f"Window_Lit_{k}", cfg, lit, (1.0, 0.70, 0.36), cfg["lit"])
    town = [walls, roofs, window, lit_window, lamp_material(f"bd_lamp_{k}", cfg)]
    store = [walls, roofs, window, glow_material(f"bd_store_glass_{k}", cfg, lit, (1.0, 0.86, 0.62), cfg["lit"] * 0.5),
             glow_material(f"bd_store_sign_{k}", cfg, lit, (1.0, 0.16, 0.12), cfg["lit"] * 0.9, off_rgb=(0.62, 0.07, 0.06))]
    for ob in objs:
        me = ob.data
        if ob.name == "bd_terrain":
            me.materials.clear()
            me.materials.append(ground)
        elif ob.name == "bd_trees":
            me.materials.clear()
            me.materials.append(trees)
        else:
            for i, mt in enumerate(store if ob.name == "bd_store" else town):
                me.materials[i] = mt


# ---------------------------------------------------------------- the skies (world shaders, seen by camera rays only)
def dir_of(bearing, elev):
    b, e = math.radians(bearing), math.radians(elev)
    return Vector((math.sin(b) * math.cos(e), math.cos(b) * math.cos(e), math.sin(e)))     # Blender: +Y north, +X east, +Z up


class Sky:
    """Small node-building helpers over one world's node tree. dirn is the view direction (unit), up its Z."""

    def __init__(self, nt):
        self.nt = nt
        tc = nt.nodes.new("ShaderNodeTexCoord")
        self.dirn = tc.outputs["Generated"]
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(self.dirn, sep.inputs[0])
        self.x, self.y, self.up = sep.outputs["X"], sep.outputs["Y"], sep.outputs["Z"]

    def math(self, op, a, b=None, v=None):
        n = self.nt.nodes.new("ShaderNodeMath")
        n.operation = op
        self.nt.links.new(a, n.inputs[0])
        if b is not None:
            self.nt.links.new(b, n.inputs[1])
        elif v is not None:
            n.inputs[1].default_value = v
        return n.outputs[0]

    def rng(self, val, f0, f1, t0=0.0, t1=1.0, steps=False):
        n = self.nt.nodes.new("ShaderNodeMapRange")
        if steps:
            n.interpolation_type = "SMOOTHSTEP"
        n.inputs["From Min"].default_value, n.inputs["From Max"].default_value = f0, f1
        n.inputs["To Min"].default_value, n.inputs["To Max"].default_value = t0, t1
        self.nt.links.new(val, n.inputs["Value"])
        return n.outputs[0]

    def ramp(self, fac, stops, constant=False):
        r = self.nt.nodes.new("ShaderNodeValToRGB")
        self.nt.links.new(fac, r.inputs["Fac"])
        cr = r.color_ramp
        if constant:
            cr.interpolation = "CONSTANT"
        cr.elements[0].position, cr.elements[0].color = stops[0][0], (*stops[0][1], 1)
        cr.elements[1].position, cr.elements[1].color = stops[-1][0], (*stops[-1][1], 1)
        for p, c in stops[1:-1]:
            e = cr.elements.new(p)
            e.color = (*c, 1)
        return r.outputs["Color"]

    def mix(self, fac, a, b, blend="MIX", rgb=None):
        mx = self.nt.nodes.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        mx.blend_type = blend
        mx.clamp_result = False
        mx.clamp_factor = blend == "MIX"
        self.nt.links.new(fac, mx.inputs[0])
        self.nt.links.new(a, mx.inputs[6])
        if b is not None:
            self.nt.links.new(b, mx.inputs[7])
        else:
            mx.inputs[7].default_value = (*rgb, 1)
        return mx.outputs[2]

    def add(self, col, fac, rgb):
        return self.mix(fac, col, None, "ADD", rgb)

    def dot(self, d):
        n = self.nt.nodes.new("ShaderNodeVectorMath")
        n.operation = "DOT_PRODUCT"
        n.inputs[1].default_value = d
        self.nt.links.new(self.dirn, n.inputs[0])
        return n.outputs["Value"]

    def glow(self, d, terms):
        dv = self.dot(d)
        c = self.math("MAXIMUM", dv, v=0.0)
        tot = None
        for pw, k in terms:
            t = self.math("MULTIPLY", self.math("POWER", c, v=pw), v=k)
            tot = t if tot is None else self.math("ADD", tot, t)
        return tot, dv

    def disc(self, dv, radius_deg, edge_deg, strength):
        return self.rng(dv, math.cos(math.radians(radius_deg + edge_deg)), math.cos(math.radians(radius_deg)), 0.0, strength)

    def plane(self, lift, scale, stretch=(1.0, 1.0), offset=(0.0, 0.0)):
        """The view direction projected onto a cloud deck overhead: (x, y) / (z + lift) * scale, so clouds shrink and crowd toward the horizon."""
        zc = self.math("ADD", self.math("MAXIMUM", self.up, v=0.0), v=lift)
        px = self.math("ADD", self.math("MULTIPLY", self.math("DIVIDE", self.x, zc), v=scale * stretch[0]), v=offset[0])
        py = self.math("ADD", self.math("MULTIPLY", self.math("DIVIDE", self.y, zc), v=scale * stretch[1]), v=offset[1])
        cv = self.nt.nodes.new("ShaderNodeCombineXYZ")
        self.nt.links.new(px, cv.inputs["X"])
        self.nt.links.new(py, cv.inputs["Y"])
        return cv.outputs[0]

    def noise(self, vec, scale, detail, rough, w=None):
        n = self.nt.nodes.new("ShaderNodeTexNoise")
        if w is not None:
            n.noise_dimensions = "4D"
            n.inputs["W"].default_value = w
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        self.nt.links.new(vec, n.inputs["Vector"])
        return n.outputs["Fac"]

    def stars(self, col, layers, above):
        for scale, keep, k in layers:
            vo = self.nt.nodes.new("ShaderNodeTexVoronoi")
            vo.inputs["Scale"].default_value = scale
            vo.inputs["Randomness"].default_value = 0.85
            self.nt.links.new(self.dirn, vo.inputs["Vector"])
            pt = self.math("POWER", self.rng(vo.outputs["Distance"], 0.13, 0.0), v=2.0)
            sc_ = self.nt.nodes.new("ShaderNodeSeparateColor")
            self.nt.links.new(vo.outputs["Color"], sc_.inputs[0])
            sel = self.rng(sc_.outputs[0], keep, 1.0)                # one bright point in the few cells whose random value is over keep
            br = self.math("MULTIPLY", self.math("MULTIPLY", pt, sel), above)
            col = self.add(col, self.math("MULTIPLY", br, v=k), (0.95, 0.96, 1.0))
        return col


def sky_world(k):
    cfg = SKY[k]
    w = bpy.data.worlds.get("BackdropSky") or bpy.data.worlds.new("BackdropSky")
    nt = new_nodes(w)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    S = Sky(nt)
    sd = dir_of(*cfg["sun"])
    above = S.rng(S.up, 0.0, 0.12)
    if k == "clear_day":
        # the parking-lot backdrop's day sky: pale at the horizon to blue overhead, the sun and its glow, no clouds
        col = S.ramp(S.up, [(0.0, (0.74, 0.82, 0.93)), (0.05, (0.60, 0.72, 0.90)), (0.25, (0.33, 0.52, 0.84)), (0.6, (0.18, 0.36, 0.74)), (1.0, (0.12, 0.27, 0.64))])
        g, dv = S.glow(sd, ((6.0, 0.10), (60.0, 0.35), (2000.0, 3.0)))
        col = S.add(col, g, (1.0, 0.93, 0.80))
        col = S.add(col, S.disc(dv, 0.55, 0.07, 40.0), (1.0, 0.97, 0.9))
    elif k == "sunset":
        # warm toward the low sun, cool and violet away from it; a few long thin clouds lit gold on the sun's side and plum on the other
        warm = S.ramp(S.up, [(0.0, (1.00, 0.56, 0.30)), (0.04, (0.98, 0.50, 0.34)), (0.12, (0.80, 0.46, 0.46)), (0.30, (0.42, 0.36, 0.58)),
                             (0.65, (0.18, 0.22, 0.48)), (1.0, (0.10, 0.13, 0.34))])
        cool = S.ramp(S.up, [(0.0, (0.62, 0.46, 0.58)), (0.05, (0.50, 0.42, 0.60)), (0.20, (0.30, 0.30, 0.54)), (0.6, (0.15, 0.19, 0.44)), (1.0, (0.10, 0.13, 0.34))])
        flat = Vector((sd.x, sd.y, 0.0)).normalized()
        toward = S.math("POWER", S.math("MAXIMUM", S.math("MULTIPLY", S.math("ADD", S.dot(flat), v=1.0), v=0.5), v=0.0), v=2.2)
        col = S.mix(toward, cool, warm)
        g, dv = S.glow(sd, ((3.0, 0.20), (24.0, 0.45), (400.0, 1.2), (6000.0, 4.0)))
        col = S.add(col, g, (1.0, 0.62, 0.30))
        sunlit = S.math("MINIMUM", S.math("ADD", S.math("MULTIPLY", g, v=0.9), S.math("MULTIPLY", toward, v=0.6)), v=1.0)
        n = S.noise(S.plane(0.04, 0.55, stretch=(0.22, 1.0), offset=(3.1, -7.4)), 1.0, 5.0, 0.55)
        dens = S.math("MULTIPLY", S.rng(n, 0.56, 0.68, steps=True), S.rng(S.up, 0.005, 0.03))
        dens = S.math("MULTIPLY", dens, S.rng(S.up, 0.32, 0.12))                       # low cloud: none overhead
        dens = S.math("MULTIPLY", dens, S.rng(dv, math.cos(math.radians(5.0)), math.cos(math.radians(2.5)), 1.0, 0.0))   # none over the sun
        ccol = S.mix(sunlit, S.ramp(S.up, [(0.0, (0.40, 0.28, 0.40)), (0.3, (0.30, 0.24, 0.40))]), S.ramp(S.up, [(0.0, (1.00, 0.70, 0.42)), (0.3, (0.98, 0.56, 0.46))]))
        col = S.mix(S.math("MULTIPLY", dens, v=0.85), col, ccol)
        col = S.add(col, S.disc(dv, 1.3, 0.12, 14.0), (1.0, 0.80, 0.52))               # the low sun, drawn large
    elif k == "night":
        # the parking-lot backdrop's night, brighter: more and brighter stars, the Milky Way across the sky, the moon and its halo, the town's glow
        col = S.ramp(S.up, [(0.0, (0.030, 0.036, 0.070)), (0.05, (0.016, 0.022, 0.052)), (0.25, (0.006, 0.009, 0.026)), (1.0, (0.002, 0.003, 0.010))])
        g, dv = S.glow(sd, ((8.0, 0.012), (120.0, 0.05), (3000.0, 0.25)))
        col = S.add(col, g, (0.75, 0.82, 1.0))
        mw = Vector((0.55, -0.35, 0.76)).normalized()             # the band's pole: the band rises in the north-east and arcs over toward the south-west
        band = S.math("EXPONENT", S.math("MULTIPLY", S.math("POWER", S.math("DIVIDE", S.dot(mw), v=0.16), v=2.0), v=-1.0))
        mott = S.rng(S.noise(S.dirn, 5.0, 8.0, 0.62), 0.38, 0.72)
        dust = S.rng(S.noise(S.dirn, 11.0, 6.0, 0.6, w=2.0), 0.52, 0.62, 1.0, 0.35)    # dark dust lanes along the band
        mwv = S.math("MULTIPLY", S.math("MULTIPLY", S.math("MULTIPLY", band, mott), dust), above)
        col = S.add(col, S.math("MULTIPLY", mwv, v=0.05), (0.62, 0.66, 0.86))
        col = S.stars(col, ((140.0, 0.972, 11.0), (330.0, 0.955, 1.8), (600.0, 0.93, 0.5)), above)
        # dense faint stars inside the band
        vo = nt.nodes.new("ShaderNodeTexVoronoi")
        vo.inputs["Scale"].default_value = 520.0
        vo.inputs["Randomness"].default_value = 0.9
        nt.links.new(S.dirn, vo.inputs["Vector"])
        sc_ = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(vo.outputs["Color"], sc_.inputs[0])
        pt = S.math("POWER", S.rng(vo.outputs["Distance"], 0.12, 0.0), v=2.0)
        sel = S.rng(sc_.outputs[0], 0.55, 1.0)
        col = S.add(col, S.math("MULTIPLY", S.math("MULTIPLY", S.math("MULTIPLY", pt, sel), S.math("MULTIPLY", band, above)), v=0.9), (0.9, 0.92, 1.0))
        seas = S.rng(S.noise(S.dirn, 260.0, 3.0, 0.5), 0.42, 0.62, 1.0, 0.72)
        col = S.add(col, S.math("MULTIPLY", S.math("MULTIPLY", S.disc(dv, 0.84, 0.08, 1.0), seas), v=2.4), (0.95, 0.94, 0.88))
        tg, _ = S.glow(dir_of(math.degrees(TOWN_BEARING), 0.0), ((10.0, 1.0),))
        col = S.add(col, S.math("MULTIPLY", S.math("MULTIPLY", tg, S.rng(S.up, 0.16, 0.0)), v=0.05), (1.0, 0.62, 0.32))
    else:
        # painted: a saturated cerulean sky, pale and minty at the horizon, and big cel-shaded cumulus in three flat tones (lit, mid, shadow)
        # with crisp edges, plus a few high brush-stroke wisps. The light side is the side toward the sun: two noise taps a little apart.
        col = S.ramp(S.up, [(0.0, (0.80, 0.92, 0.98)), (0.04, (0.58, 0.84, 0.98)), (0.18, (0.24, 0.62, 0.96)), (0.5, (0.08, 0.40, 0.90)), (1.0, (0.04, 0.26, 0.76))])
        g, dv = S.glow(sd, ((8.0, 0.08), (90.0, 0.30), (3000.0, 2.0)))
        col = S.add(col, g, (1.0, 0.96, 0.86))
        col = S.add(col, S.disc(dv, 1.1, 0.04, 30.0), (1.0, 0.98, 0.92))
        # high wisps first (behind the cumulus)
        wv = S.plane(0.10, 0.30, stretch=(1.0, 0.18), offset=(-5.0, 2.0))
        wisp = S.math("MULTIPLY", S.rng(S.noise(wv, 1.6, 6.0, 0.6), 0.60, 0.70, steps=True), S.rng(S.up, 0.02, 0.10))
        col = S.add(col, S.math("MULTIPLY", wisp, v=0.35), (0.95, 0.97, 1.0))
        flat = Vector((sd.x, sd.y, 0.0)).normalized()
        o = 0.10                                                           # the second tap, this far toward the sun on the deck
        cv = S.plane(0.08, 0.80, offset=(11.0, 4.0))
        cv2 = S.plane(0.08, 0.80, offset=(11.0 + o * flat.x, 4.0 + o * flat.y))
        n1 = S.noise(cv, 1.0, 4.0, 0.52, w=0.7)
        n2 = S.noise(cv2, 1.0, 4.0, 0.52, w=0.7)
        dens = S.rng(n1, 0.535, 0.555)                                     # crisp, painted edges
        dens = S.math("MULTIPLY", dens, S.rng(S.up, 0.0, 0.018))
        dens = S.math("MULTIPLY", dens, S.rng(dv, math.cos(math.radians(7.0)), math.cos(math.radians(3.5)), 1.0, 0.0))   # the sun stays clear
        lit = S.rng(S.math("SUBTRACT", n1, n2), -0.020, 0.020)             # > 0.5: the side toward the sun
        core = S.rng(n1, 0.56, 0.66)                                       # deep inside a cloud: a touch shaded
        shade = S.math("SUBTRACT", lit, S.math("MULTIPLY", core, v=0.25))
        ccol = S.ramp(shade, [(0.0, (0.56, 0.62, 0.86)), (0.38, (0.80, 0.85, 0.97)), (0.62, (1.0, 1.0, 0.98)), (1.0, (1.0, 1.0, 0.98))], constant=True)
        rim = S.math("MULTIPLY", S.rng(n1, 0.535, 0.545, 1.0, 0.0), S.rng(lit, 0.5, 0.7))  # a bright rim on the sunny edge
        ccol = S.add(ccol, S.math("MULTIPLY", rim, v=0.12), (1.0, 0.96, 0.86))
        col = S.mix(dens, col, ccol)
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(col, bg.inputs["Color"])
    amb = nt.nodes.new("ShaderNodeBackground")
    amb.inputs["Color"].default_value = (*cfg["amb"], 1)
    amb.inputs["Strength"].default_value = 1.0
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(amb.outputs[0], mix.inputs[1])
    nt.links.new(bg.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    bpy.context.scene.world = w
    return w


# ---------------------------------------------------------------- saving
KEEP_SYS = ("cycles", "eevee")


def set_path(owner, attr, value):
    setattr(owner, attr, ("_" * 1000) if isinstance(getattr(owner, attr), str) else b"_" * 1000)
    setattr(owner, attr, value)


def scrub_private():
    """The .blend could be shared: drop every custom property, blank the render output path and every stamp, and the file browser's folder."""
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
                for kk in list(st.keys()):
                    if st is not idb and kk.startswith(KEEP_SYS):
                        continue
                    try:
                        del st[kk]
                        dropped += 1
                    except Exception as e:
                        print("  could not drop custom property", idb.name, kk, e)
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
        bpy.data.images.remove(im)


def save_blend():
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    scrub_private()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    scrub_private()
    bpy.ops.wm.save_mainfile(compress=True)
    print("BLEND", BLEND.relative_to(ROOT).as_posix(), BLEND.stat().st_size)


def stage_skies():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.name = "overworld_skies"
    print("LOT", json.dumps(EXT), "grass radius", GRASS_R)
    coll = bpy.data.collections.new("Backdrop")
    sc.collection.children.link(coll)
    rng = np.random.default_rng(1208)                          # the parking-lot backdrop's seed: the same trees, town and farms
    terrain = build_terrain(coll)
    trees = build_trees(coll, rng)
    placeholder = [bpy.data.materials.new(f"slot_{i}") for i in range(5)]
    town, lamps = build_town(coll, rng, placeholder)
    store = build_store(coll, placeholder)
    objs = [terrain, trees, town, lamps, store]
    setup_cycles(arg("--bd-samples", 128, int))
    pano_camera()
    sun = bpy.data.objects.new("bd_sun", bpy.data.lights.new("bd_sun", "SUN"))
    coll.objects.link(sun)
    scale = arg("--scale", 100, int)
    for k in arg("--only", ",".join(SKIES)).split(","):
        cfg = SKY[k]
        assign(objs, k)
        d = dir_of(*cfg["sun"])
        sun.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        sun.data.energy = cfg["energy"]
        sun.data.color = cfg["sun_col"]
        sun.data.angle = math.radians(0.6)
        sky_world(k)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, scale
        sc.view_settings.view_transform = "Standard"
        sc.view_settings.look = "None"
        sc.view_settings.exposure = arg(f"--exposure-{k}", 0.0, float)
        orientation_test([coll], k)
        sc.render.image_settings.file_format = "PNG"
        sc.render.image_settings.color_mode = "RGB"
        sc.render.image_settings.color_depth = "8"
        path = stage_work() / f"sky_{k}.png"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print("SKY", k, path, path.stat().st_size)
    if arg("--save", "1") == "1":
        assign(objs, "clear_day")
        sky_world("clear_day")
        save_blend()


if __name__ == "__main__":
    if STAGE == "skies":
        stage_skies()
    else:
        print("in Blender only --stage skies runs")
