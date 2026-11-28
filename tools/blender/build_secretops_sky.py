"""The Registrar's hall, phase 3: the glitched sky (docs/BLENDER_AREAS.md section 8, "Phase 3 needs a second sky backdrop for the arena,
glitched"; docs/WORLD.md: "the arena's sky and geometry glitch, like the four Overworld skies failing").

It is an R3 backdrop, like the four Overworld skies (docs/renders/overworld_skies on claude/blender-overworld-skies): one 4096 x 2048
equirectangular WebP, world/backdrops/registrar_hall_glitch.webp, the picture's middle column facing north (game -z), its right-hand side
east (game +x), its top row the zenith. The page shows it as the arena's background (shared/manifest.js: a scene's `backdrop`), so it is
seen wherever a CeilingPanel_ has been opened, from any angle, at no draw call and with nothing baked; the arena's GLB, layout and
lightmaps are unchanged.

    python tools/blender/build_secretops_sky.py --stage image --sources <dir of the four overworld_*.webp> --work <dir>
    python tools/blender/build_secretops_sky.py --stage check
    blender -b --factory-startup blender/scenes/registrar_hall.blend --python tools/blender/build_secretops_sky.py -- --stage stills --work <dir>

The picture is the four Overworld skies (clear day, sunset, night, painted) cut into torn bearing sectors that do not agree, band by band:
rows slid sideways, blocks copied out of place and posterised, the colour channels split, scanlines, the arena's green grid showing
through, a pink seam due north and a green one due east, and the Registrar's eye at the zenith (a pink ring round the pole, a dark pupil
and a green slit along the north-south line), looking down through the open ceiling. Everything below the horizon is dimmed.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def arg(name, default=None):
    return args[args.index(name) + 1] if name in args else default


OUT = ROOT / "world/backdrops/registrar_hall_glitch.webp"
W, H = 4096, 2048
SKIES = ("clear_day", "sunset", "night", "painted")
PINK, GREEN = (255, 92, 158), (80, 255, 140)
MAX_BYTES = 1_000_000


def col_of(bearing_deg):
    """The column of a compass bearing (0 north, 90 east): north is the middle column, east three quarters across."""
    return int(round(((0.5 + bearing_deg / 360.0) % 1.0) * W)) % W


def row_of(elev_deg):
    return int(round((90.0 - elev_deg) / 180.0 * H))


def make_image(src_dir, work):
    import numpy as np
    from PIL import Image
    rng = np.random.default_rng(3)
    skies = [np.asarray(Image.open(Path(src_dir) / f"overworld_{k}.webp").convert("RGB").resize((W, H), Image.LANCZOS), np.float32) / 255
             for k in SKIES]
    out = np.zeros((H, W, 3), np.float32)
    # 1. torn bearing sectors: each horizontal band picks its own sector edges and its own sky per sector
    y = 0
    while y < H:
        bh = int(rng.integers(24, 160))
        edges = np.sort(rng.integers(0, W, int(rng.integers(5, 10))))
        pick = rng.integers(0, 4, len(edges) + 1)
        x0 = 0
        for k, e in enumerate(list(edges) + [W]):
            out[y:y + bh, x0:e] = skies[pick[k]][y:y + bh, x0:e]
            x0 = e
        y += bh
    # 2. rows slid sideways (more of them toward the zenith)
    y = 0
    while y < H:
        bh = int(rng.integers(4, 48))
        if rng.random() < 0.25 + 0.35 * (1 - y / H):
            out[y:y + bh] = np.roll(out[y:y + bh], int(rng.integers(-600, 600)), axis=1)
        y += bh
    # 3. blocks copied out of place, posterised, channel-swapped
    for _ in range(260):
        bw, bh = int(rng.integers(32, 260)), int(rng.integers(16, 120))
        sx, sy = int(rng.integers(0, W - bw)), int(rng.integers(0, H // 2 - bh))
        dx, dy = int(rng.integers(0, W - bw)), int(rng.integers(0, H // 2 - bh))
        blk = out[sy:sy + bh, sx:sx + bw].copy()
        r = rng.random()
        if r < 0.35:
            blk = np.round(blk * 4) / 4
        elif r < 0.6:
            blk = blk[..., ::-1]
        elif r < 0.75:
            blk = 1.0 - blk
        out[dy:dy + bh, dx:dx + bw] = blk
    # 4. the colour channels split in some bands
    y = 0
    while y < H:
        bh = int(rng.integers(30, 140))
        if rng.random() < 0.4:
            s = int(rng.integers(8, 28))
            out[y:y + bh, :, 0] = np.roll(out[y:y + bh, :, 0], s, axis=1)
            out[y:y + bh, :, 2] = np.roll(out[y:y + bh, :, 2], -s, axis=1)
        y += bh
    # 5. the arena's green grid showing through, in some sectors (lines of latitude and longitude)
    yy, xx = np.mgrid[0:H, 0:W]
    grid = ((xx % 128) < 2) | ((yy % 128) < 2)
    sector = (np.floor(xx / 512) + np.floor(yy / 256)) % 3 == 0
    m = grid & sector & (yy < H // 2)
    out[m] = out[m] * 0.4 + np.array(GREEN, np.float32) / 255 * 0.6
    # 6. scanlines, and thin pink and green lines across
    out[(yy % 4) == 0] *= 0.82
    for _ in range(40):
        r0 = int(rng.integers(0, H // 2))
        c = np.array(PINK if rng.random() < 0.5 else GREEN, np.float32) / 255
        x0, x1 = sorted(rng.integers(0, W, 2))
        out[r0:r0 + 2, x0:x1] = c
    # 7. the seams: pink due north, green due east, from the horizon up
    for bear, c, top in ((0.0, PINK, 70.0), (90.0, GREEN, 40.0)):
        cx = col_of(bear)
        out[row_of(top):row_of(0.0), max(cx - 5, 0):cx + 5] = np.array(c, np.float32) / 255
    # 8. the Registrar's eye at the zenith: a pink ring round the pole, a dark pupil, a green slit along the north-south line
    elev = 90.0 - yy / H * 180.0
    out[(elev > 74.0) & (elev < 77.0)] = np.array(PINK, np.float32) / 255
    out[(elev > 77.0) & (elev < 84.0)] *= 0.35
    out[elev >= 84.0] = np.array((10, 8, 12), np.float32) / 255
    for bear in (0.0, 180.0):
        cx = col_of(bear)
        out[0:row_of(77.0), max(cx - 7, 0):cx + 7] = np.array(GREEN, np.float32) / 255
    # 9. below the horizon: dimmed, so the pit and the walls stay the arena's
    out[H // 2:] *= np.linspace(0.45, 0.15, H - H // 2)[:, None, None]
    out = np.clip(out, 0, 0.965)
    im = Image.fromarray((out * 255 + 0.5).astype(np.uint8))
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    im.save(work / "registrar_hall_glitch.png")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for q in (88, 84, 80, 76, 72, 68, 64, 60):
        im.save(OUT, "WEBP", quality=q, method=6)
        if OUT.stat().st_size <= MAX_BYTES:
            break
    print(f"{OUT.relative_to(ROOT)}  {W}x{H}  q{q}  {OUT.stat().st_size} bytes")


def check():
    """Size, shape and chunks of the WebP; the north and east seams in their columns; the eye round the zenith; brightness (the page shows
    the picture as it is: no light, no tone mapping)."""
    import numpy as np
    from PIL import Image
    ok = True
    b = OUT.read_bytes()
    chunks = []
    i = 12
    while i + 8 <= len(b):
        cid, n = b[i:i + 4], int.from_bytes(b[i + 4:i + 8], "little")
        chunks.append(cid.decode("latin1"))
        i += 8 + n + (n & 1)
    a = np.asarray(Image.open(OUT).convert("RGB"), np.float32) / 255
    res = [("size", len(b) <= MAX_BYTES, f"{len(b)} bytes (at most {MAX_BYTES})"),
           ("shape", a.shape[:2] == (H, W), f"{a.shape[1]} x {a.shape[0]} (2:1 equirect)"),
           ("chunks", not any(c in ("EXIF", "XMP ") for c in chunks), f"RIFF chunks {chunks} (no EXIF, no XMP)")]
    for bear, c, name in ((0.0, PINK, "north seam (pink)"), (90.0, GREEN, "east seam (green)")):
        cx = col_of(bear)
        y0, y1 = row_of(35.0), row_of(5.0)
        cols = [(cx + k) % W for k in range(-3, 4)]
        strip = a[y0:y1][:, cols].reshape(-1, 3)
        hit = float(np.mean(np.abs(strip - np.array(c) / 255).max(axis=1) < 0.12))
        mx = col_of(-bear if bear else 180.0)
        mirror = a[y0:y1][:, [(mx + k) % W for k in range(-3, 4)]].reshape(-1, 3)
        mhit = float(np.mean(np.abs(mirror - np.array(c) / 255).max(axis=1) < 0.12))
        res.append((name, hit > 0.6 and mhit < 0.3, f"column {cx}: {hit:.0%} of its pixels are the seam's colour; the mirrored bearing's column {mhit:.0%}"))
    ring = a[row_of(76.5):row_of(75.0)].reshape(-1, 3)
    rh = float(np.mean(np.abs(ring - np.array(PINK) / 255).max(axis=1) < 0.12))
    res.append(("eye", rh > 0.9, f"the pink ring round the zenith covers {rh:.0%} of its rows (elevation 75 to 76.5 degrees)"))
    up = a[: H // 2].max(axis=2)
    lin = np.where(up <= 0.04045, up / 12.92, ((up + 0.055) / 1.055) ** 2.4)
    p = np.percentile(lin, [50, 90, 99])
    res.append(("brightness", p[2] <= 0.98, f"upper half as shown (linear, max channel): p50 {p[0]:.3f}, p90 {p[1]:.3f}, p99 {p[2]:.3f}, max {lin.max():.3f}"))
    for name, good, text in res:
        ok &= good
        print(f"{'PASS' if good else 'FAIL'}  {name:10s} {text}")
    print("SKY CHECK", "PASS" if ok else "FAIL")
    return ok


# ================================================================ stills (Blender, on the box)
def stills(work):
    import bpy
    sys.path.insert(0, str(ROOT / "tools/blender"))
    import build_secretops_dress as D
    from mathutils import Vector
    D.SCENE = "registrar_hall"
    D.S = D.GB.build("registrar_hall")
    D.load_scene_file()
    sc = bpy.context.scene
    work = Path(work)
    # the world: the backdrop on camera rays only (the arena keeps its own light), north at the picture's middle column
    w = bpy.data.worlds.new("Glitch")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, 0, -math.pi / 2)        # Blender's equirect centre faces +X; north (game -z) is Blender +Y
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(OUT))
    bg = nt.nodes.new("ShaderNodeBackground")
    dark = nt.nodes.new("ShaderNodeBackground")
    dark.inputs["Strength"].default_value = 0.0
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    o = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], env.inputs["Vector"])
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(dark.outputs[0], mix.inputs[1])
    nt.links.new(bg.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], o.inputs["Surface"])
    D.stage_check()                    # the layout check on the arena as built (before phase 3 opens anything; the file is not saved)
    # phase 3 as the page might show it mid-fight: most ceiling panels open, a few floor panels gone
    import random
    rnd = random.Random(7)
    for ob in bpy.data.objects:
        if ob.name.startswith("CeilingPanel_") and rnd.random() < 0.7:
            ob.hide_render = True
        if ob.name.startswith("FloorPanel_") and rnd.random() < 0.12 and not ob.get("under_rack"):
            ob.hide_render = True
    if "Export" in bpy.data.collections:
        bpy.data.collections["Export"].hide_render = True
    for o2 in D.COLL["Arch"].objects:
        o2.hide_render = True
    D.export_strengths()
    D.setup_cycles(int(arg("--render-samples", "96")))
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.03
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.view_settings.view_transform = "AgX"
    for obj in [x for x in bpy.data.objects if x.type == "CAMERA"]:
        bpy.data.objects.remove(obj)
    d = ROOT / "docs/renders/registrar_hall_sky"
    d.mkdir(parents=True, exist_ok=True)
    shots = {"1_up_east": ((-22.6, 1.6, 0.0), (8.0, 14.0, 0.0), 75, "normal"),
             "2_up_north": ((4.0, 1.6, 8.0), (2.0, 24.0, -10.0), 85, "normal"),
             "3_north": ((0.0, 1.6, 7.5), (0.0, 9.0, -14.0), 75, "normal"),
             "4_alarm": ((-22.6, 1.6, 0.0), (8.0, 14.0, 0.0), 75, "alarm")}
    for key, (loc, tgt, fov, st) in shots.items():
        D.apply_set(st)
        sc.view_settings.exposure = 0.2 + (0.8 if st == "alarm" else 0.0)
        sc.camera = D.look_cam(key, loc, tgt, fov)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 1080, 100
        sc.render.image_settings.file_format = "JPEG"
        sc.render.image_settings.quality = 88
        path = d / f"{key}.jpg"
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        D.strip_jpeg_comments(path)
        print("STILL", key, path.stat().st_size)
    print("SKY STILLS DONE")


if __name__ == "__main__":
    st = arg("--stage", "check")
    try:
        import bpy  # noqa: F401
        stills(arg("--work", str(ROOT / "work")))
    except ImportError:
        if st == "image":
            make_image(arg("--sources"), arg("--work", str(ROOT / "work")))
        elif st == "check":
            sys.exit(0 if check() else 1)
        else:
            print(__doc__)
