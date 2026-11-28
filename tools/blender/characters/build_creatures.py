"""The City's stalker (the owner's Meshy "Moonclaw Stalker") and the randomly spawning Mawcrawler, animated.

  blender -b --factory-startup -P tools/blender/characters/build_creatures.py

Both Meshy rigs suit their bodies (checked joint by joint against the mesh): the stalker's is a biped with a
hunched spine, long arms with four claws per hand, digitigrade legs and three small chains in the mouth; the
Mawcrawler's is a body, a neck, upper and lower jaws, a short tail and six legs of five bones each. So the rigs
and Meshy's weights are kept, fixed only where a clip stretches them (see fit); the bones get readable names.
Clips (creature_clips.py), each held to the stretch gate (no triangle edge past 2x in any frame):
  stalker: idle, walk, stalk (slow creep), freeze (the pose it holds while watched)
  mawcrawler: idle, crawl, lunge, spawn (climbing out of the floor)
Writes models/characters/stalker.glb and models/characters/mawcrawler.glb.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402

import common as C  # noqa: E402
import creature_clips as CC  # noqa: E402
import numpy as np  # noqa: E402
import skinweights as SW  # noqa: E402
import warrior_clips as WC  # noqa: E402

GATE = 2.0  # no triangle edge may stretch or squash past 2x in any frame of any clip
MIN_LEN = 1e-3  # edges shorter than 1 mm at rest are not measured (as in the node check)


# Meshy bone -> name. In the source the stalker faces +Z; x > 0 is its left (.L).
STALKER = {"Bone_000": "root", "Bone_001": "pelvis", "Bone_006": "spine1", "Bone_005": "spine2",
           "Bone_004": "spine3", "Bone_003": "chest", "Bone_002": "upper_chest", "Bone_018": "neck",
           "Bone_017": "head", "Bone_030": "mouth_a", "Bone_029": "mouth_a_end", "Bone_032": "mouth_b",
           "Bone_031": "mouth_b_end", "Bone_034": "mouth_c", "Bone_033": "mouth_c_end",
           "Bone_023": "shoulder.R", "Bone_022": "upperarm.R", "Bone_021": "forearm.R", "Bone_020": "hand.R",
           "Bone_019": "palm.R", "Bone_028": "shoulder.L", "Bone_027": "upperarm.L", "Bone_026": "forearm.L",
           "Bone_025": "hand.L", "Bone_024": "palm.L",
           "Bone_011": "thigh.R", "Bone_010": "shin.R", "Bone_009": "foot.R", "Bone_008": "toe.R", "Bone_007": "toe_end.R",
           "Bone_016": "thigh.L", "Bone_015": "shin.L", "Bone_014": "foot.L", "Bone_013": "toe.L", "Bone_012": "toe_end.L"}
for side, chains in (("R", [("037", "036", "035"), ("041", "040", "039", "038"), ("045", "044", "043", "042"),
                            ("049", "048", "047", "046")]),
                     ("L", [("052", "051", "050"), ("056", "055", "054", "053"), ("060", "059", "058", "057"),
                            ("064", "063", "062", "061")])):
    for ci, ch in enumerate(chains):
        for k, b in enumerate(ch):
            STALKER[f"Bone_{b}"] = f"claw{ci + 1}_{k + 1}.{side}"

MAW = {"Bone_000": "root", "Bone_001": "body", "Bone_003": "neck", "Bone_002": "maw", "Bone_041": "jaw_upper",
       "Bone_040": "jaw_upper_end", "Bone_043": "jaw_lower", "Bone_042": "jaw_lower_end", "Bone_005": "tail",
       "Bone_004": "tail_end"}
for leg, (l, r) in {"front": ("034 033 032 031 030", "039 038 037 036 035"),
                    "mid": ("017 016 015 014 013 012", "011 010 009 008 007 006"),
                    "rear": ("029 028 027 026 025 024", "023 022 021 020 019 018")}.items():
    for side, ids in (("L", l), ("R", r)):
        for k, b in enumerate(ids.split()):
            MAW[f"Bone_{b}"] = f"leg_{leg}{k + 1}.{side}"


def load(src, names):
    C.reset()
    objs = C.import_glb(os.path.join(C.SRC, src))
    mesh = max((o for o in objs if o.type == "MESH"), key=lambda o: len(o.data.polygons))
    arm = next(o for o in objs if o.type == "ARMATURE")
    for pb in arm.pose.bones:
        pb.custom_shape = None
    for o in objs:  # the importer's helpers (a bone-display sphere, empties) are not part of the character
        if o is not mesh and o is not arm:
            bpy.data.objects.remove(o, do_unlink=True)
    tris = C.tri_count(mesh)
    print(src, "armature matrix", [list(r) for r in arm.matrix_world], "mesh parent", mesh.parent and mesh.parent.name)
    missing = [b.name for b in arm.data.bones if b.name not in names]
    assert not missing, f"unnamed bones: {missing}"
    for b in arm.data.bones:  # renaming a bone renames its vertex group too
        b.name = names[b.name]
    assert all(g.name in arm.data.bones for g in mesh.vertex_groups), "a vertex group lost its bone"
    return mesh, arm, tris


def finish(name, mesh, arm, A, tris0, extra=None):
    extra = dict(extra or {}, stretch=C.stretch_gate(mesh, arm, A, MIN_LEN, GATE))
    C.maybe_dump(name, mesh, arm, A)
    C.export_glb(os.path.join(C.OUT, name + ".glb"), [arm, mesh])
    assert C.tri_count(mesh) == tris0, "triangles changed"
    info = C.report(name, mesh, arm, A, dict(source_tris=tris0, **(extra or {})))
    print("REPORT", json.dumps(info))
    blend = os.environ.get("CHAR_BLEND")
    if blend:
        bpy.ops.wm.save_as_mainfile(filepath=blend.replace(".blend", f"_{name}.blend"))
    return info


def limb_of(n):
    """The stalker's limbs: 1/2 left/right arm (shoulder to claws), 3/4 left/right leg, 0 the rest."""
    b, _, sd = n.partition(".")
    if b.startswith(("claw", "hand", "palm", "forearm", "upperarm", "shoulder")):
        return 1 if sd == "L" else 2
    if b.startswith(("thigh", "shin", "foot", "toe")):
        return 3 if sd == "L" else 4
    return 0


def fit(mesh, arm, clips_at, amps, limbs=None):
    """Meshy's weights, fixed where the clips stretch them: a point of one limb keeps no weight of another limb (the
    stalker's long claws hang beside its feet and Meshy gave the toes some of their weight), then Skin.relax smooths
    the weights around every edge a clip stretches or squashes past 1.8x. The first amplitude whose clips stay within
    the gate wins. Returns (amp, per clip)."""
    names, heads, tails, parents, deform = C.bone_arrays(arm)
    verts, tris, _ = C.mesh_arrays(mesh)
    sk = SW.Skin(verts, tris, deform, min_len=MIN_LEN)
    W = sk.to_welded(C.group_weights(mesh, names))
    W /= W.sum(1, keepdims=True)
    if limbs is not None:
        ch = np.array([limbs(n) for n in names])
        g = np.stack([W[:, ch == c].sum(1) for c in range(5)], 1).argmax(1)
        for c in (1, 2, 3, 4):  # arms never take a leg's weight or the other arm's, legs never an arm's
            other = [h for h in (1, 2, 3, 4) if h != c and {c, h} != {3, 4}]
            W[np.ix_(g == c, np.isin(ch, other))] = 0.0
        W /= W.sum(1, keepdims=True)
    best = None
    for amp in amps:
        sk.clips = {}
        for n, fr, pa in clips_at(names, heads, amp):
            sk.add_clip(n, np.array([WC.deform(names, heads, parents, pa(f)) for f in range(fr + 1)]))
        Wr, per, it = sk.relax(W, 1.8, iters=200)
        worst = max(v[0] for v in per.values())
        print(mesh.name, "amp", amp, "relaxed", per)
        if best is None or worst < best[0]:
            best = (worst, amp, Wr, per)
        if worst <= GATE:
            break
    worst, amp, Wr, per = best
    C.set_group_weights(mesh, names, deform, sk.to_verts(Wr))
    return amp, per


reports = []

# ---------------------------------------------------------------- the stalker
mesh, arm, tris0 = load("moonclaw_stalker.glb", STALKER)
mesh.name = mesh.data.name = "stalker"
arm.name = "stalker_rig"
amp, _ = fit(mesh, arm, lambda n, h, a: CC.stalker_clips(n, a), (1.0, 0.8, 0.65), limb_of)
A = C.Animator(arm)
for name, frames, pose_at in CC.stalker_clips([b.name for b in arm.data.bones], amp):
    A.clip(name, frames, pose_at)
reports.append(finish("stalker", mesh, arm, A, tris0, dict(amp=amp)))

# ---------------------------------------------------------------- the Mawcrawler
mesh, arm, tris0 = load("the_mawcrawler.glb", MAW)
mesh.name = mesh.data.name = "mawcrawler"
arm.name = "mawcrawler_rig"
amp, _ = fit(mesh, arm, CC.maw_clips, (1.0, 0.8, 0.65))
A = C.Animator(arm)
names, heads = C.bone_arrays(arm)[:2]
for name, frames, pose_at in CC.maw_clips(names, heads, amp):
    A.clip(name, frames, pose_at)
reports.append(finish("mawcrawler", mesh, arm, A, tris0, dict(amp=amp)))
out = os.environ.get("CHAR_REPORT")
if out:
    json.dump(reports, open(out, "w"), indent=1)
