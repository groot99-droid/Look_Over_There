"""Review stills of the characters: each exported GLB is imported back, posed and rendered (Cycles, CPU).

  blender -b --factory-startup -P tools/blender/characters/render_stills.py -- <out_dir> [name ...]

For each models/characters/<name>.glb it writes <out_dir>/<name>_rest.png (the display pose, from the front at
three quarters) and <out_dir>/<name>_pose.png (a frame of one of its clips). make_sheet.py turns them into the
JPEG stills and the contact sheet in docs/renders/characters/.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import common as C  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUTDIR = argv[0]
ONLY = set(argv[1:])
POSE = {"trex": ("roar", 34), "stalker": ("freeze", 0), "mawcrawler": ("lunge", 13)}  # warriors: attack, frame 12 (the strike)
os.makedirs(OUTDIR, exist_ok=True)


def setup():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 40
    sc.cycles.use_denoising = True
    sc.render.film_transparent = False
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.035, 0.036, 0.04, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    sc.world = w
    for name, rot, energy in (("key", (math.radians(50), 0, math.radians(-35)), 3.5),
                              ("rim", (math.radians(60), 0, math.radians(150)), 2.0)):
        L = bpy.data.lights.new(name, "SUN")
        L.energy = energy
        o = bpy.data.objects.new(name, L)
        o.rotation_euler = rot
        sc.collection.objects.link(o)


def frame_bounds(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        if o.type == "MESH":
            ev = o.evaluated_get(dg)
            me = ev.to_mesh()
            pts += [ev.matrix_world @ v.co for v in list(me.vertices)[:: max(1, len(me.vertices) // 4000)]]
            ev.to_mesh_clear()
    mn = Vector((min(p[i] for p in pts) for i in range(3)))
    mx = Vector((max(p[i] for p in pts) for i in range(3)))
    return mn, mx


def shoot(path, objs, wide):
    sc = bpy.context.scene
    mn, mx = frame_bounds(objs)
    ctr = (mn + mx) / 2
    size = mx - mn
    cam_d = Vector((-0.55, -1.0, 0.28)).normalized() if not wide else Vector((-1.0, -0.75, 0.3)).normalized()
    cam = bpy.data.objects.get("cam") or bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    rx, ry = (1200, 700) if wide else (600, 760)
    sc.render.resolution_x, sc.render.resolution_y = rx, ry
    r = size.length
    cam.location = ctr + cam_d * r * 3
    cam.rotation_euler = (-cam_d).to_track_quat("-Z", "Y").to_euler()
    # fit: project the box corners on the camera's axes
    m = cam.rotation_euler.to_matrix()
    right, up = m.col[0], m.col[1]
    corners = [Vector((x, y, z)) for x in (mn.x, mx.x) for y in (mn.y, mx.y) for z in (mn.z, mx.z)]
    w = max(abs((c - ctr).dot(right)) for c in corners) * 2
    h = max(abs((c - ctr).dot(up)) for c in corners) * 2
    cam.data.ortho_scale = max(w, h * rx / ry) * 1.12
    sc.camera = cam
    sc.render.filepath = path
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)


names = sorted(f[:-4] for f in os.listdir(C.OUT) if f.endswith(".glb"))
for name in names:
    if ONLY and name not in ONLY:
        continue
    C.reset()
    setup()
    objs = C.import_glb(os.path.join(C.OUT, name + ".glb"))
    for o in [o for o in objs if o.type == "MESH" and not any(m.type == "ARMATURE" for m in o.modifiers)]:
        objs.remove(o)  # the importer's bone-display sphere
        bpy.data.objects.remove(o, do_unlink=True)
    arm = next(o for o in objs if o.type == "ARMATURE")
    ad = arm.animation_data_create()
    ad.action = None
    for pb in arm.pose.bones:
        pb.matrix_basis.identity()
    bpy.context.scene.frame_set(0)
    wide = name in ("trex", "mawcrawler")
    shoot(os.path.join(OUTDIR, name + "_rest.png"), objs, wide)
    clip, frame = POSE.get(name, ("attack", 12))
    act = next(a for a in bpy.data.actions if a.name == clip or a.name.startswith(clip + "_"))
    ad.action = act
    try:
        if ad.action_slot is None and len(act.slots):
            ad.action_slot = act.slots[0]
    except Exception:
        pass
    bpy.context.scene.frame_set(frame)
    shoot(os.path.join(OUTDIR, name + "_pose.png"), objs, wide)
    print("rendered", name, clip, frame)
