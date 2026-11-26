"""Pictures of the game's other scenes for the museum hall's frames (scene `galleries`): views of the store floors and the exterior, rendered from their
world GLBs (world/B1.glb, L1.glb .. L4.glb, Exterior.glb). The other half of the pictures are the review stills of the built scenes (docs/renders/<scene>/).

    blender -b --factory-startup --python tools/blender/render_galleries_views.py -- --mode candidates --out <dir>     (small test renders of many views)
    blender -b --factory-startup --python tools/blender/render_galleries_views.py -- --mode final --out <dir>          (the chosen VIEWS at 1024 x 768)

`candidates` finds places to stand by ray casting (a floor below, a ceiling 2.2 to 9 m above, a long free view) plus each floor's security cameras
(world/<scene>.json `cameras`), renders each at 480 x 360 and writes candidates.json; the chosen ones are copied into VIEWS below. The floors are lit by
their own emissive fittings (strengthened, as the page's lamps are), the exterior by a low evening sun and its lit windows. Cycles, OptiX when present.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
SCENES = ["B1", "L1", "L2", "L3", "L4", "Exterior"]
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None, cast=str):
    return cast(args[args.index(name) + 1]) if name in args else default


# the chosen views (from a candidates run, 2026-11-26): camera location and look-at point in game axes, horizontal fov, exposure
VIEWS = [
    {"id": "B1_01", "scene": "B1", "loc": [-11.91, -0.81, 21.04], "target": [-2.33, -3.68, 21.04], "fov": 80.0, "exposure": 0.0},
    {"id": "B1_03", "scene": "B1", "loc": [-14.2, -0.69, -1.85], "target": [-14.2, -3.56, 7.73], "fov": 80.0, "exposure": 0.0},
    {"id": "B1_02", "scene": "B1", "loc": [6.35, -0.81, -3.55], "target": [3.87, -3.68, -12.8], "fov": 80.0, "exposure": 0.0},
    {"id": "L1_02", "scene": "L1", "loc": [11.17, 1.6, -1.11], "target": [20.37, 0.8, 2.7], "fov": 80.0, "exposure": 0.0},
    {"id": "L1_07", "scene": "L1", "loc": [-22.37, 2.51, 8.59], "target": [-22.37, -0.36, 18.16], "fov": 80.0, "exposure": 0.0},
    {"id": "L1_00", "scene": "L1", "loc": [-9.83, 1.6, 10.89], "target": [0.13, 0.8, 10.89], "fov": 80.0, "exposure": 0.0},
    {"id": "L2_00", "scene": "L2", "loc": [-0.83, 4.8, 19.89], "target": [-10.8, 4.0, 19.89], "fov": 80.0, "exposure": 0.0},
    {"id": "L2_05", "scene": "L2", "loc": [-24.83, 4.8, -10.11], "target": [-24.83, 4.0, -0.15], "fov": 80.0, "exposure": 0.0},
    {"id": "L2_09", "scene": "L2", "loc": [-6.5, 5.71, -2.04], "target": [0.27, 2.84, -8.82], "fov": 80.0, "exposure": 0.0},
    {"id": "L3_00", "scene": "L3", "loc": [-18.8, 8.0, 7.85], "target": [-8.83, 7.2, 7.85], "fov": 80.0, "exposure": 0.0},
    {"id": "L3_04", "scene": "L3", "loc": [-18.8, 8.0, -4.15], "target": [-8.83, 7.2, -4.15], "fov": 80.0, "exposure": 0.0},
    {"id": "L4_00", "scene": "L4", "loc": [-22.1, 11.69, 18.15], "target": [-12.89, 10.89, 21.96], "fov": 80.0, "exposure": 0.0},
    {"id": "L4_08", "scene": "L4", "loc": [-21.81, 13.49, 6.38], "target": [-12.23, 10.62, 6.38], "fov": 80.0, "exposure": 0.0},
    {"id": "L4_04", "scene": "L4", "loc": [1.9, 11.2, 21.15], "target": [-1.91, 10.4, 30.36], "fov": 80.0, "exposure": 0.0},
    {"id": "L4_09", "scene": "L4", "loc": [20.28, 13.49, -9.62], "target": [10.7, 10.62, -9.62], "fov": 80.0, "exposure": 0.0},
    {"id": "Exterior_07", "scene": "Exterior", "loc": [-8.0, 11.2, 43.6], "target": [-3.01, 10.7, 34.95], "fov": 80.0, "exposure": 0.0},
    {"id": "Exterior_05", "scene": "Exterior", "loc": [-40.0, 11.25, 24.0], "target": [-30.79, 10.46, 20.19], "fov": 80.0, "exposure": 0.0},
    {"id": "Exterior_03", "scene": "Exterior", "loc": [-48.0, 11.19, 48.0], "target": [-55.05, 10.39, 40.95], "fov": 80.0, "exposure": 0.0},
]


def B(p):
    return Vector((p[0], -p[2], p[1]))


def setup_gpu(samples):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.use_denoising = True
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for t in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = t
            prefs.refresh_devices()
        except Exception:
            continue
        if [d for d in prefs.devices if d.type != "CPU"]:
            for d in prefs.devices:
                d.use = d.type != "CPU"
            sc.cycles.device = "GPU"
            break
    sc.view_settings.view_transform = "AgX"
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    for p in sc.render.bl_rna.properties:
        if p.identifier.startswith("use_stamp") and not p.is_readonly:
            setattr(sc.render, p.identifier, False)


def load(scene):
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.images, bpy.data.cameras, bpy.data.lights):
        for d in list(coll):
            coll.remove(d)
    bpy.ops.import_scene.gltf(filepath=str(ROOT / f"world/{scene}.glb"))
    w = bpy.context.scene.world or bpy.data.worlds.new("W")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    if scene == "Exterior":
        sky = nt.nodes.new("ShaderNodeTexSky")
        for attr, val in (("sky_type", "NISHITA"), ("sun_elevation", math.radians(7)), ("sun_rotation", math.radians(210))):
            try:
                setattr(sky, attr, val)
            except (AttributeError, TypeError):
                pass
        nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = 0.35
        sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
        sun.data.energy, sun.data.color = 2.2, (1.0, 0.72, 0.48)
        sun.rotation_euler = (math.radians(83), 0, math.radians(210))
        bpy.context.scene.collection.objects.link(sun)
    else:
        bg.inputs["Color"].default_value = (0.02, 0.022, 0.025, 1)
        bg.inputs["Strength"].default_value = 1.0
    for m in bpy.data.materials:                     # the page's lamps are bright; the imported emission strength is 1
        if not m.use_nodes:
            continue
        for n in m.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED" and "Emission Strength" in n.inputs:
                if n.inputs["Emission Strength"].default_value > 0 and (n.inputs["Emission Color"].is_linked or max(n.inputs["Emission Color"].default_value[:3]) > 0.01):
                    n.inputs["Emission Strength"].default_value = 12.0 if ("Fluor" in m.name or "lamp" in m.name.lower()) else 3.0


def ray(sc, dg, o, d, dist=200.0):
    hit, loc, nor, idx, ob, mx = sc.ray_cast(dg, o, d, distance=dist)
    return (hit, (loc - o).length if hit else dist)


def candidates(scene):
    sc = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    obs = [o for o in sc.objects if o.type == "MESH"]
    lo = Vector((min((o.matrix_world @ Vector(c)).x for o in obs for c in o.bound_box), min((o.matrix_world @ Vector(c)).y for o in obs for c in o.bound_box), 0))
    hi = Vector((max((o.matrix_world @ Vector(c)).x for o in obs for c in o.bound_box), max((o.matrix_world @ Vector(c)).y for o in obs for c in o.bound_box), 0))
    if scene == "Exterior":
        lo, hi = Vector((-60, -60, 0)), Vector((60, 70, 0))
    found = []
    doc = ROOT / f"world/{scene}.json"
    cams = json.loads(doc.read_text()).get("cameras", []) if doc.exists() else []
    if scene == "Exterior":
        cams = json.loads((ROOT / "world/parking_lot.json").read_text()).get("markers", [])
    step = 3.0 if scene != "Exterior" else 8.0
    levels = sorted({round(z, 1) for z in [0.0, 3.0, 6.4, 9.6, 12.0]})
    x = lo.x + step / 2
    while x < hi.x:
        y = lo.y + step / 2
        while y < hi.y:
            for zl in (levels if scene != "Exterior" else [9.6, 0.0]):
                o = Vector((x, y, zl + 1.2))
                hd, dd = ray(sc, dg, o, Vector((0, 0, -1)), 6)
                hu, du = ray(sc, dg, o, Vector((0, 0, 1)), 12)
                if not hd or dd > 2.5:
                    continue
                if scene != "Exterior" and (not hu or not (2.2 <= dd + du <= 9.0)):
                    continue
                eye = Vector((x, y, o.z - dd + 1.6))
                best = (0, None)
                for k in range(16):
                    a = 2 * math.pi * k / 16
                    d = Vector((math.cos(a), math.sin(a), -0.08)).normalized()
                    h, L = ray(sc, dg, eye, d, 80)
                    if L > best[0]:
                        best = (L, d)
                if best[0] > 9:
                    found.append((best[0], eye, best[1]))
            y += step
        x += step
    found.sort(key=lambda t: -t[0])
    pick = []
    for L, e, d in found:
        if all((e - p[1]).length > 9 for p in pick):
            pick.append((L, e, d))
        if len(pick) >= 7:
            break
    out = [(e, e + d * 10) for L, e, d in pick]
    for c in cams[:4]:                                   # the security cameras (and the parking lot's markers): a high corner view
        p = c.get("position")
        if not p:
            continue
        e = B(p) + (Vector((0, 0, 1.6)) if scene == "Exterior" else Vector((0, 0, -0.15)))
        best = (0, None)
        for k in range(24):
            a = 2 * math.pi * k / 24
            d = Vector((math.cos(a), math.sin(a), -0.3 if scene != "Exterior" else -0.05)).normalized()
            h, L = ray(sc, dg, e, d, 80)
            if L > best[0]:
                best = (L, d)
        if best[1] is not None:
            out.append((e, e + best[1] * 10))
    return [([round(e.x, 2), round(e.z, 2), round(-e.y, 2)], [round(t.x, 2), round(t.z, 2), round(-t.y, 2)]) for e, t in out]


def shoot(loc, target, fov, path, res, expo):
    sc = bpy.context.scene
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.lens_unit = "FOV"
    cam.data.angle = math.radians(fov)
    cam.data.clip_start = 0.05
    cam.data.clip_end = 900
    sc.collection.objects.link(cam)
    cam.location = B(loc)
    cam.rotation_euler = (B(target) - B(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 92
    sc.view_settings.exposure = expo
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam)


def main():
    out = Path(arg("--out"))
    out.mkdir(parents=True, exist_ok=True)
    mode = arg("--mode", "candidates")
    if mode == "candidates":
        setup_gpu(arg("--samples", 24, int))
        res = {}
        for s in SCENES:
            load(s)
            cs = candidates(s)
            res[s] = cs
            for k, (e, t) in enumerate(cs):
                for expo in (0.0,):
                    shoot(e, t, 80.0, out / f"{s}_{k:02d}.jpg", (480, 360), expo)
            print("CANDIDATES", s, len(cs))
        (out / "candidates.json").write_text(json.dumps(res, indent=1))
    else:
        setup_gpu(arg("--samples", 128, int))
        views = json.loads(Path(arg("--views")).read_text()) if arg("--views") else VIEWS
        for s in SCENES:
            mine = [v for v in views if v["scene"] == s]
            if not mine:
                continue
            load(s)
            for v in mine:
                shoot(v["loc"], v["target"], v.get("fov", 75.0), out / f"{v['id']}.jpg", (1024, 768), v.get("exposure", 0.0))
                print("VIEW", v["id"])


main()
