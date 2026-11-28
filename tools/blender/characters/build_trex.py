"""The museum's tyrannosaur skeleton (the owner's Meshy model "Tyrant Bones"), rigged and animated.

  blender -b --factory-startup -P tools/blender/characters/build_trex.py

Meshy's rig was not a theropod rig (no jaw, one arm on the midline, a chain along the belly ribs, legs pushed to
one side), so it is replaced: pelvis, spine, chest, neck, head, jaw, a nine-bone tail, two legs (thigh, shin,
foot) and two small arms. The skull, spine and tail are one piece of the mesh and are weighted by distance to the
bones; every other loose piece (each leg bone, each arm, each rib) moves rigidly with its bone. The jaw is cut
from the skull along the gap between the teeth (vertices doubled in place, no face added or removed), and the
skull, spine and tail are weighted harmonically between anchors at the bone cores. Every clip must keep each
triangle edge within 2x of its rest length (the stretch gate).
Scaled 2.2x in the file: 12 m long, 3.74 m tall, real size. Clips: idle, walk, roar, return_to_pose.
Writes models/characters/trex.glb.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import common as C  # noqa: E402
import numpy as np  # noqa: E402
import skinweights as SW  # noqa: E402

MIN_LEN = 1e-3 * 2.2  # edges shorter than 2.2 mm at rest are not measured (as in the node check)
MARGIN = 0.3  # the middle 40 % of each axial bone is its core

S = 2.2  # 5.47 m -> 12.0 m long

C.reset()
objs = C.import_glb(os.path.join(C.SRC, "tyrant_bones.glb"))
mesh = max((o for o in objs if o.type == "MESH"), key=lambda o: len(o.data.polygons))
tris0 = C.tri_count(mesh)
# drop Meshy's armature and weights, keep the mesh where it is
mw = mesh.matrix_world.copy()
mesh.parent = None
mesh.matrix_world = mw
for m in list(mesh.modifiers):
    mesh.modifiers.remove(m)
mesh.vertex_groups.clear()
for o in objs:
    if o is not mesh:
        bpy.data.objects.remove(o, do_unlink=True)
mesh.scale = (S, S, S)
C.apply_transforms([mesh])
mesh.name = mesh.data.name = "trex"


def P(x, y, z):  # a point measured on the source (glTF metres) -> Blender, at real size
    return C.g2b((x * S, y * S, z * S))


spine = [(0.13, 1.33, 0.03), (0.13, 1.34, 0.32), (0.13, 1.36, 0.66), (0.12, 1.37, 0.95), (0.12, 1.37, 1.15)]
neck = [(0.12, 1.37, 1.15), (0.12, 1.40, 1.45), (0.12, 1.45, 1.70), (0.12, 1.48, 1.92)]
tail = [(0.13, 1.33, 0.03), (0.14, 1.27, -0.40), (0.13, 1.19, -0.80), (0.08, 1.18, -1.15), (0.0, 1.23, -1.50),
        (-0.09, 1.30, -1.82), (-0.19, 1.42, -2.12), (-0.35, 1.53, -2.41), (-0.57, 1.62, -2.62), (-0.73, 1.69, -2.735)]
bones = [("root", P(0.12, 0, 0.03), P(0.12, 0, 0.6), None, False),
         ("pelvis", P(*spine[0]), P(*spine[1]), "root", True),
         ("spine1", P(*spine[1]), P(*spine[2]), "pelvis", True),
         ("spine2", P(*spine[2]), P(*spine[3]), "spine1", True),
         ("chest", P(*spine[3]), P(*spine[4]), "spine2", True)]
par = "chest"
for i in range(3):
    bones.append((f"neck{i + 1}", P(*neck[i]), P(*neck[i + 1]), par, True))
    par = f"neck{i + 1}"
bones += [("head", P(*neck[3]), P(0.11, 1.45, 2.70), "neck3", True),
          ("jaw", P(0.11, 1.37, 1.98), P(0.11, 1.18, 2.62), "head", True)]
par = "pelvis"
for i in range(9):
    bones.append((f"tail{i + 1}", P(*tail[i]), P(*tail[i + 1]), par, True))
    par = f"tail{i + 1}"
legs = {"L": [(0.35, 1.29, 0.17), (0.49, 0.79, 0.46), (0.52, 0.37, -0.10), (0.57, 0.03, 0.20)],
        "R": [(-0.06, 1.29, 0.09), (-0.30, 0.88, 0.30), (-0.33, 0.37, -0.10), (-0.42, 0.03, 0.18)]}
for sd, pts in legs.items():
    bones += [(f"thigh.{sd}", P(*pts[0]), P(*pts[1]), "pelvis", True),
              (f"shin.{sd}", P(*pts[1]), P(*pts[2]), f"thigh.{sd}", True),
              (f"foot.{sd}", P(*pts[2]), P(*pts[3]), f"shin.{sd}", True)]
bones += [("arm.L", P(0.29, 0.99, 1.37), P(0.30, 0.74, 1.55), "chest", True),
          ("arm.R", P(-0.13, 0.98, 1.29), P(-0.13, 0.73, 1.49), "chest", True)]
arm = C.build_armature("trex_rig", bones)

def jaw_line(zg):  # the gap between the teeth rows, measured on the source's side view (glTF metres)
    pts = [(1.97, 1.385), (2.30, 1.35), (2.45, 1.30), (2.62, 1.25), (2.80, 1.25)]
    if zg <= pts[0][0]:
        return pts[0][1]
    for (z0, y0), (z1, y1) in zip(pts, pts[1:]):
        if z0 <= zg <= z1:
            return y0 + (y1 - y0) * (zg - z0) / (z1 - z0)
    return pts[-1][1]


def below_jaw_line(co):
    co = co / S
    zg, yg = -co.y, co.z
    return zg > 1.97 and yg < jaw_line(zg)


# ---- cut the jaw from the skull by topology: in the source the teeth rows are joined by faces, which would string
# out when the mouth opens. Each face goes to the jaw or the skull by where most of its corners lie, and the
# vertices on the border between the two are split (doubled in place): no face is added, removed or moved.
import bmesh  # noqa: E402

bm = bmesh.new()
bm.from_mesh(mesh.data)
bm.faces.ensure_lookup_table()
jaw_face = {f.index: sum(below_jaw_line(v.co) for v in f.verts) * 2 > len(f.verts) for f in bm.faces}
cut = [e for e in bm.edges if len(e.link_faces) == 2 and jaw_face[e.link_faces[0].index] != jaw_face[e.link_faces[1].index]]
bmesh.ops.split_edges(bm, edges=cut)
bm.verts.ensure_lookup_table()
JAW = [v.index for v in bm.verts if v.link_faces and all(jaw_face[f.index] for f in v.link_faces)]
bm.to_mesh(mesh.data)
bm.free()
assert C.tri_count(mesh) == tris0, "the jaw cut changed the triangles"
print("trex: jaw cut along", len(cut), "edges")

# ---- weights
W = C.Weights(mesh, arm)
parts = C.islands(mesh.data)  # welded by position: the jaw cut does not make the skull a separate part here
V = mesh.data.vertices
body = parts[0]
axial = ["pelvis", "spine1", "spine2", "chest", "neck1", "neck2", "neck3", "head"] + [f"tail{i + 1}" for i in range(9)]
jaw_set = set(JAW)
njaw = sum(1 for i in body if i in jaw_set)
limbs = [f"{b}.{s}" for s in "LR" for b in ("thigh", "shin", "foot")] + ["arm.L", "arm.R"]
taken = {}
for part in parts[1:]:
    lo = Vector((min(V[i].co[k] for i in part) for k in range(3)))
    hi = Vector((max(V[i].co[k] for i in part) for k in range(3)))
    for bn in limbs:
        a, b = W.segs[bn]
        mid = (a + b) / 2
        if all(lo[k] - 0.02 <= mid[k] <= hi[k] + 0.02 for k in range(3)) and len(part) > taken.get(bn, (0, None))[0]:
            taken[bn] = (len(part), part)
limb_parts = {id(p): bn for bn, (n, p) in taken.items()}
for part in parts[1:]:
    bn = limb_parts.get(id(part))
    if bn:
        W.rigid(part, bn)
    else:  # ribs, belly ribs and small bits: follow the spine as one piece each
        W.distance(part, ["pelvis", "spine1", "spine2", "chest", "neck1"])
        W.average(part)
# The skull, spine and tail (one piece) get harmonic weights instead (skinweights.harmonic): anchored at the core
# of each bone of the axial chain, the jaw anchored to the jaw and the skull to the head, and blended smoothly by
# length in between, so no short edge takes a whole change of weight (the distance weights strung the neck out).
names, heads, tails, parents, deform = C.bone_arrays(arm)
Wv = np.array([[W.w[i].get(n, 0.0) for n in names] for i in range(len(V))])
verts, tris, _ = C.mesh_arrays(mesh)
jawv = np.zeros(len(V), bool)
jawv[JAW] = True
sk = SW.Skin(verts, tris, deform, labels=jawv.astype(int), min_len=MIN_LEN)  # the jaw cut stays open
Pt = sk.P
bodyp = np.zeros(sk.n, bool)
bodyp[sk.wid[body]] = True
ax = [names.index(n) for n in axial]
D = np.full((sk.n, len(names)), np.inf)
D[:, ax] = SW.seg_dist(Pt, heads[ax], tails[ax])
lab = D.argmin(1)
ab = tails[lab] - heads[lab]
t = ((Pt - heads[lab]) * ab).sum(1) / (ab * ab).sum(1)
first = np.array([parents[j] < 0 or parents[j] not in ax for j in range(len(names))])
haschild = np.array([any(parents[c] == j and c in ax for c in range(len(names))) for j in range(len(names))])
anch = (t >= np.where(first[lab], -np.inf, MARGIN)) & (t <= np.where(haschild[lab], 1 - MARGIN, np.inf))
jawp = sk.to_welded(jawv[:, None].astype(float))[:, 0] > 0.999
lab[jawp] = names.index("jaw")
anch[jawp] = True
A0 = np.zeros((sk.n, len(names)))
A0[np.arange(sk.n), lab] = 1.0
A0[~bodyp] = sk.to_welded(Wv)[~bodyp]  # the loose bones keep their rigid weights
Wh, _ = SW.harmonic(Pt, sk.E, sk.L0, A0, ~bodyp | anch, MIN_LEN)
C.set_group_weights(mesh, names, deform, sk.to_verts(SW.limit(Wh, 4)))
C.bind(mesh, arm)
print("trex: parts", len(parts), "limb parts", {k: v[0] for k, v in taken.items()}, "jaw verts", njaw,
      "axial anchors", int((anch & bodyp).sum()), "of", int(bodyp.sum()))

# ---- clips (Blender axes: X across the body, -Y forward, Z up)
A = C.Animator(arm)
TAIL = [f"tail{i + 1}" for i in range(9)]
sin, cos, pi = math.sin, math.cos, math.pi


def idle(f, n=72):
    ph = 2 * pi * f / n
    p = {"chest": {"rot": {"X": 1.2 * sin(ph)}}, "spine2": {"rot": {"X": 0.8 * sin(ph)}},
         "neck1": {"rot": {"X": 2.5 * sin(ph + 0.4)}}, "neck2": {"rot": {"X": 1.5 * sin(ph + 0.6), "Z": 3 * sin(ph)}},
         "head": {"rot": {"Z": 6 * sin(ph + 1.0), "X": 2 * sin(2 * ph)}},
         "jaw": {"rot": {"X": 4 * max(0.0, sin(2 * ph))}},
         "arm.L": {"rot": {"X": 6 * sin(ph)}}, "arm.R": {"rot": {"X": 6 * sin(ph + 0.5)}}}
    for k, t in enumerate(TAIL):
        p[t] = {"rot": {"Z": 2.5 * sin(ph - 0.35 * k), "X": 0.8 * sin(ph - 0.3 * k)}}
    return p


def walk(f, n=40):
    ph = 2 * pi * f / n
    s = sin(ph)
    p = {"root": {"loc": (0, 0, -0.06 * abs(cos(ph)) + 0.03)},
         "pelvis": {"rot": {"Y": 3 * s, "Z": 4 * s}},
         "chest": {"rot": {"Z": -3 * s}},
         "neck1": {"rot": {"X": 2 * cos(2 * ph), "Z": -2 * s}}, "head": {"rot": {"X": -2 * cos(2 * ph), "Z": -2 * s}},
         "arm.L": {"rot": {"X": 10 * s}}, "arm.R": {"rot": {"X": -10 * s}}}
    for sd, sg in (("L", 1), ("R", -1)):
        sw = sg * s  # >0: this leg swings forward
        lift = max(0.0, sin(ph if sg > 0 else ph + pi))
        p[f"thigh.{sd}"] = {"rot": {"X": -16 * sw}}
        p[f"shin.{sd}"] = {"rot": {"X": 24 * lift}}
        p[f"foot.{sd}"] = {"rot": {"X": 16 * sw - 14 * lift}}
    for k, t in enumerate(TAIL):
        p[t] = {"rot": {"Z": -3.5 * sin(ph - 0.4 * k), "X": 1.2 * cos(2 * ph - 0.3 * k)}}
    return p


ROAR_UP = {"neck1": {"rot": {"X": -8}}, "neck2": {"rot": {"X": -8}}, "neck3": {"rot": {"X": -6}},
           "head": {"rot": {"X": -14}}, "jaw": {"rot": {"X": 8}}, "chest": {"rot": {"X": -4}},
           "tail1": {"rot": {"X": 3}}, "tail2": {"rot": {"X": 3}}}
ROAR_OUT = {"neck1": {"rot": {"X": 6}}, "neck2": {"rot": {"X": 5}}, "neck3": {"rot": {"X": 2}},
            "head": {"rot": {"X": -4}}, "jaw": {"rot": {"X": 38}}, "chest": {"rot": {"X": 3}},
            "arm.L": {"rot": {"X": -20}}, "arm.R": {"rot": {"X": -20}},
            "tail1": {"rot": {"X": 6}}, "tail2": {"rot": {"X": 5}}, "tail3": {"rot": {"X": 4}}}
ROAR_KEYS = [(0, {}), (14, ROAR_UP), (22, ROAR_OUT), (54, ROAR_OUT), (72, {})]


def roar(f):
    p = C.keyed(ROAR_KEYS, f)
    if 22 <= f <= 54:  # the shake while it roars
        e = math.sin(pi * (f - 22) / 32)
        q = dict(p)
        q["head"] = {"rot": dict(p["head"]["rot"], Z=5 * e * sin(2 * pi * (f - 22) / 6))}
        q["jaw"] = {"rot": dict(p["jaw"]["rot"], X=p["jaw"]["rot"].get("X", 0) + 3 * e * sin(2 * pi * f / 4))}
        return q
    return p


ALIVE = walk(10)  # mid-stride, head turned: the pose it is caught in when the lights come back
ALIVE["head"] = {"rot": {"Z": 14, "X": -6}}
ALIVE["jaw"] = {"rot": {"X": 14}}


def back(f, n=36):
    return C.lerp_pose(ALIVE, {}, C.smooth(f / n))


A.clip("idle", 72, idle)
A.clip("walk", 40, walk)
A.clip("roar", 72, roar)
A.clip("return_to_pose", 36, back)

stretch = C.stretch_gate(mesh, arm, A, MIN_LEN, 2.0)
C.maybe_dump("trex", mesh, arm, A)
os.makedirs(C.OUT, exist_ok=True)
C.export_glb(os.path.join(C.OUT, "trex.glb"), [arm, mesh])
assert C.tri_count(mesh) == tris0, "triangles changed"
info = C.report("trex", mesh, arm, A, {"source_tris": tris0, "scale": S, "jaw_verts": njaw, "stretch": stretch})
out = os.environ.get("CHAR_REPORT")
if out:
    json.dump(info, open(out, "w"), indent=1)
print("REPORT", json.dumps(info))
blend = os.environ.get("CHAR_BLEND")
if blend:
    bpy.ops.wm.save_as_mainfile(filepath=blend)
