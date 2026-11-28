"""The museum's toy warriors: the owner's two Meshy friezes split into their eight figures, each rigged and animated.

  blender -b --factory-startup -P tools/blender/characters/build_warriors.py

Each frieze is cut into loose parts; the large parts are the figures, and every small part (a spear, a bow, a
shield, an arrow, a plume) joins the figure it is closest to. Neither frieze has a shared base or ground plate,
so nothing is deleted and no hole is left at the feet. Each figure keeps its miniature size (about 0.45 m), gets
its origin between its feet and faces +Z in the GLB.
Rig: a small humanoid armature (hips, spine, chest, neck, head, and per side thigh, shin, foot, upper arm,
forearm, hand), placed from measurements of each figure.
Weights (skinweights.Humanoid): Blender's automatic (heat) weights give each point a limb; the mesh is cut where
limbs that move apart are fused (a hand on a thigh, the legs under a coat, an arm on the belt, a weapon on the
helmet); each separate weapon near a hand, and the fused shield (a box), is held rigidly by its hand; the rest is
anchored at the bone cores and blended harmonically across the joints. The clips (warrior_clips.py) are then
played through the armature: no triangle edge may stretch or squash past 2x in any frame (the stretch gate) and no
cut may open a crack wider than 1.2 % of the figure's height (the crack gate); each clip plays at the largest of
its sizes (warrior_clips.LADDERS) that passes both. Clips: idle, march,
attack, freeze. Writes models/characters/warrior_<era>_<kind>.glb.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import common as C  # noqa: E402
import numpy as np  # noqa: E402
import skinweights as SW  # noqa: E402
import warrior_clips as WC  # noqa: E402

GATE = 2.0  # no triangle edge may stretch or squash past 2x in any frame of any clip
FIT = 1.95  # the weight fit aims a little lower, so rounding in three.js never reads 2.0 as over
MIN_LEN = 3e-4  # edges shorter than 0.3 mm at rest are not measured (as in the node check)

# Measured on the sources (glTF metres, in frieze space; left = +x = the figure's own left).
# sh/el/ha: shoulder, elbow, hand (x, y); the depth is found on the mesh. weapon: the hand of the main weapon.
# shields: boxes (xmin, xmax, ymin, ymax, zmin) made rigid to a hand; discs: (centre, normal, radius, back, front).
# grips: a weapon fused to the body, made rigid to a hand: ((haft end, haft end, radius, [head boxes (lo, hi)]), hand)
# (the Viking's bearded axe, resting on his shoulder against the helmet).
FRIEZES = {
    "warriors_through_the_ages.glb": [
        dict(name="warrior_egyptian_pharaoh", look="Egyptian pharaoh, nemes headdress, khopesh",
             sh=((-0.410, 0.085), (-0.330, 0.085)), el=((-0.425, 0.025), (-0.298, 0.040)),
             ha=((-0.432, -0.025), (-0.335, 0.025)), weapon="R"),
        dict(name="warrior_viking_raider", look="Viking raider, spangenhelm, bearded axe and round shield",
             sh=((-0.139, 0.107), (-0.052, 0.107)), el=((-0.170, 0.050), (-0.034, 0.052)),
             ha=((-0.181, 0.092), (-0.018, 0.004)), weapon="R",
             # the round shield, turned 31 degrees: a disc (centre, normal, radius, depth behind and in front of
             # its plane) so the whole rim, which curves back, is held
             discs=[(((-0.0228, 0.0027, 0.0359), (0.52, -0.002, 0.854), 0.09, -0.026, 0.03), "L")],
             grips=[(((-0.200, 0.083, 0.043), (-0.045, 0.208, -0.080), 0.0075,
                      [((-0.172, 0.128, -0.03), (-0.124, 0.197, 0.03))]), "R")]),
        dict(name="warrior_qin_terracotta", look="Qin dynasty terracotta soldier with a ji halberd",
             sh=((0.140, 0.095), (0.230, 0.095)), el=((0.124, 0.058), (0.242, 0.034)),
             ha=((0.127, 0.040), (0.170, 0.016)), weapon="R"),
        dict(name="warrior_british_redcoat", look="18th-century British redcoat, tricorne and musket",
             sh=((0.346, 0.107), (0.437, 0.107)), el=((0.334, 0.052), (0.449, 0.052)),
             ha=((0.361, 0.031), (0.382, 0.073)), weapon="R",
             # the slung musket, sculpted onto the coat from the right hip to above the left shoulder (stock, barrel)
             grips=[(((0.3065, -0.0608, 0.0045), (0.3615, 0.0332, 0.0215), 0.013, []), "R"),
                    (((0.3615, 0.0332, 0.0215), (0.4795, 0.2332, 0.0295), 0.006, []), "R")]),
    ],
    "warriors_across_empires.glb": [
        dict(name="warrior_medieval_knight", look="Late-medieval knight in plate, sallet helm, sword",
             sh=((-0.442, 0.137), (-0.346, 0.134)), el=((-0.454, 0.074), (-0.322, 0.074)),
             ha=((-0.400, 0.065), (-0.360, 0.045)), weapon="L"),
        dict(name="warrior_japanese_samurai", look="Samurai in o-yoroi with kabuto, hand on the katana",
             sh=((-0.179, 0.098), (-0.083, 0.098)), el=((-0.200, 0.032), (-0.062, 0.032)),
             ha=((-0.212, -0.062), (-0.098, 0.008)), weapon="L"),
        dict(name="warrior_mongol_archer", look="Mongol horse archer, fur hat, spear, bow and quiver",
             sh=((0.088, 0.110), (0.209, 0.110)), el=((0.061, 0.074), (0.230, 0.032)),
             ha=((0.049, 0.092), (0.203, -0.040)), weapon="R"),
        dict(name="warrior_roman_legionary", look="Roman legionary, crested galea, gladius and scutum",
             sh=((0.330, 0.092), (0.439, 0.092)), el=((0.312, 0.020), (0.457, 0.020)),
             ha=((0.306, -0.044), (0.463, -0.047)), weapon="R"),
    ],
}
ONLY = os.environ.get("WARRIORS_ONLY", "")  # comma-separated names, for quick reruns


def figure_split(path):
    """Import a frieze and return [figure objects] ordered left to right (-x to +x), and the triangle total."""
    from mathutils.kdtree import KDTree
    objs = C.import_glb(path)
    src = next(o for o in objs if o.type == "MESH")
    C.apply_transforms([src])
    me = src.data
    total = C.tri_count(src)
    parts = C.islands(me)
    owner = {}
    for k, part in enumerate(parts):
        for i in part:
            owner[i] = k
    ptris = [0] * len(parts)
    for poly in me.polygons:
        ptris[owner[poly.vertices[0]]] += len(poly.vertices) - 2
    V = me.vertices

    def xc(part):
        return sum(V[i].co.x for i in part) / len(part)

    big = sorted((k for k in range(len(parts)) if ptris[k] >= 1000), key=lambda k: xc(parts[k]))
    seeds = []  # big parts whose x centres are close are one figure (the knight's armour is in two pieces)
    for k in big:
        if seeds and abs(xc(parts[k]) - xc(parts[seeds[-1][0]])) < 0.06:
            seeds[-1].append(k)
        else:
            seeds.append([k])
    trees = []
    for grp in seeds:
        idx = [i for k in grp for i in parts[k]]
        kd = KDTree(len(idx))
        for j, i in enumerate(idx):
            kd.insert(V[i].co, j)
        kd.balance()
        trees.append(kd)
    for k in range(len(parts)):  # each small part joins the figure it touches (closest vertex)
        if k in big:
            continue
        best = min((min(kd.find(V[i].co)[2] for i in parts[k]), gi) for gi, kd in enumerate(trees))
        seeds[best[1]].append(k)
    import bmesh
    figs = []
    for grp in seeds:  # one copy of the frieze per figure, with everything that is not that figure deleted
        keep = {i for k in grp for i in parts[k]}
        ob = src.copy()
        ob.data = src.data.copy()
        bpy.context.scene.collection.objects.link(ob)
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.verts.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in keep], context="VERTS")
        bm.to_mesh(ob.data)
        bm.free()
        figs.append(ob)
    bpy.data.objects.remove(src, do_unlink=True)
    assert sum(C.tri_count(f) for f in figs) == total, "triangles lost in the split"
    return figs, total


def open_edges_near_feet(ob, y0):
    """Boundary edges within 1 cm of the soles (a hole where a base was cut off would show here)."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    n = sum(1 for e in bm.edges if e.is_boundary and min(v.co.z for v in e.verts) < y0 + 0.01)
    bm.free()
    return n


def depth_at(verts, x, y, r=0.008, band=0.02):
    """The depth (glTF z) of the front-most surface near (x, y), less half a band: a joint inside a limb."""
    zs = [-v.y for v in verts if (v.x - x) ** 2 + (v.z - y) ** 2 < r * r]
    if not zs:
        return None
    zmax = max(zs)
    front = sorted(z for z in zs if z >= zmax - band)
    return front[len(front) // 2] - 0.004


def slice_centre(verts, y, side=None, cx=0.0, h=0.006):
    pts = [v for v in verts if abs(v.z - y) < h and (side is None or (v.x - cx) * side > 0.002)]
    if not pts:
        return None
    return Vector((sum(v.x for v in pts) / len(pts), sum(-v.y for v in pts) / len(pts)))


def build_figure(fig, spec):
    me = fig.data
    V = [fig.matrix_world @ v.co for v in me.vertices]  # Blender coords; glTF (x, y, z) = (x, co.z, -co.y)
    y0 = min(v.z for v in V)
    ytop = max(v.z for v in V)
    (shR, shL) = spec["sh"]
    ys = (shR[1] + shL[1]) / 2
    cx = (shR[0] + shL[0]) / 2
    core = [v for v in V if abs(v.x - cx) < 0.03]
    cz = sum(-v.y for v in core) / len(core)
    # move the figure so its feet are at the origin
    off = Vector((cx, -cz, y0))
    fig.location -= off
    C.apply_transforms([fig])
    V = [v - off for v in V]

    def G(x, y, z):  # frieze-space glTF point -> Blender, relative to the figure's origin
        return C.g2b((x - cx, y - y0, z - cz))

    H = ys - y0  # shoulder height
    yh, yk, ya = y0 + 0.62 * H, y0 + 0.32 * H, y0 + 0.06 * H
    Vg = [Vector((v.x + cx, v.z + y0, -v.y + cz)) for v in V]  # back to frieze glTF space (x, y, z) for measuring
    Vm = [Vector((g.x, -g.z, g.y)) for g in Vg]  # (x, -z, y) so depth_at/slice_centre read glTF depth as -y

    def spine_z(y):
        pts = [g for g in Vg if abs(g.y - y) < 0.006 and abs(g.x - cx) < 0.02]
        return sum(g.z for g in pts) / len(pts) if pts else cz

    bones = [("root", G(cx, y0, cz), G(cx, y0, cz + 0.06), None, False)]
    sp = [yh, y0 + 0.75 * H, y0 + 0.90 * H, ys + 0.02 * H, ys + 0.10 * H]
    names = ["hips", "spine", "chest", "neck"]
    par = "root"
    for i, n in enumerate(names):
        bones.append((n, G(cx, sp[i], spine_z(sp[i])), G(cx, sp[i + 1], spine_z(sp[i + 1])), par, True))
        par = n
    bones.append(("head", G(cx, sp[4], spine_z(sp[4])), G(cx, ytop, spine_z(sp[4])), "neck", True))
    for sd, sg in (("L", 1), ("R", -1)):
        pts = []
        for y in (yh, yk, ya):
            c = slice_centre(Vm, y, sg, cx)
            pts.append((c.x, y, c.y) if c else (cx + sg * 0.02, y, cz))
        hip = (cx + sg * abs(pts[0][0] - cx) * 0.8, yh, pts[0][2])
        toe_z = max((g.z for g in Vg if g.y < y0 + 0.012 and (g.x - cx) * sg > 0.003), default=cz + 0.03)
        bones += [(f"thigh.{sd}", G(*hip), G(*pts[1]), "hips", True),
                  (f"shin.{sd}", G(*pts[1]), G(*pts[2]), f"thigh.{sd}", True),
                  (f"foot.{sd}", G(*pts[2]), G(pts[2][0], y0 + 0.004, toe_z - 0.005), f"shin.{sd}", True)]
        i = 1 if sd == "L" else 0
        s, e, h = spec["sh"][i], spec["el"][i], spec["ha"][i]
        zs = [depth_at(Vm, *s) or cz, depth_at(Vm, *e) or cz, depth_at(Vm, *h) or cz]
        hv = Vector((h[0], h[1], zs[2])) - Vector((e[0], e[1], zs[1]))
        tip = Vector((h[0], h[1], zs[2])) + hv.normalized() * 0.018
        bones += [(f"upperarm.{sd}", G(s[0], s[1], zs[0]), G(e[0], e[1], zs[1]), "chest", True),
                  (f"forearm.{sd}", G(e[0], e[1], zs[1]), G(h[0], h[1], zs[2]), f"upperarm.{sd}", True),
                  (f"hand.{sd}", G(h[0], h[1], zs[2]), G(*tip), f"forearm.{sd}", True)]
    arm = C.build_armature(spec["name"] + "_rig", bones)
    fig.name = me.name = spec["name"]

    # Blender's automatic (heat) weights are the starting point; skinweights.Humanoid cuts and re-weights
    C.select([fig, arm], arm)
    heat_ok = True
    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    except Exception as ex:  # noqa: BLE001
        heat_ok = False
        print("heat weighting failed:", ex)
    names, heads, tails, parents, deform = C.bone_arrays(arm)
    heat = C.group_weights(fig, names)
    verts, tris, loops = C.mesh_arrays(fig)
    held_by = [""] * len(verts)  # a fused shield is held rigidly by its hand (a box around it)
    for (x0, x1, yb0, yb1, zmin), sd in spec.get("shields", []):
        for i, g in enumerate(Vg):
            if x0 <= g.x <= x1 and yb0 <= g.y <= yb1 and g.z >= zmin:
                held_by[i] = f"hand.{sd}"
    Pg = np.array([tuple(g) for g in Vg])
    for (c, n, r, back, front), sd in spec.get("discs", []):
        n = np.array(n) / np.linalg.norm(n)
        dd = (Pg - np.array(c)) @ n
        rho = np.linalg.norm(Pg - np.array(c) - dd[:, None] * n, axis=1)
        for i in np.nonzero((rho < r) & (dd > back) & (dd < front))[0]:
            held_by[i] = f"hand.{sd}"
    # a weapon sculpted onto the body: a capsule round its haft and boxes round its head, held by one hand
    for (a, b, r, boxes), sd in spec.get("grips", []):
        sel = SW.seg_dist(Pg, np.array([a]), np.array([b]))[:, 0] < r
        for lo, hi in boxes:
            sel |= ((Pg >= np.array(lo)) & (Pg <= np.array(hi))).all(1)
        for i in np.nonzero(sel)[0]:
            held_by[i] = f"hand.{sd}"
    fit_dump = os.environ.get("CHAR_FIT_DUMP")  # a folder: save the weight solve's inputs, for offline work
    if fit_dump:
        os.makedirs(fit_dump, exist_ok=True)
        np.savez_compressed(os.path.join(fit_dump, spec["name"] + ".npz"), verts=verts, tris=tris, loops=loops,
                            heat=heat, names=np.array(names), heads=heads, tails=tails, parents=parents,
                            deform=deform, held_by=np.array(held_by), weapon=spec["weapon"])
        if os.environ.get("CHAR_FIT_DUMP_ONLY"):
            return arm, None
    hum = SW.Humanoid(verts, tris, heat, names, heads, tails, parents, deform, held_by=held_by)
    amps, cfg, Wp, per = hum.fit(lambda a: WC.clip_matrices(names, heads, parents, spec["weapon"], a), WC.LADDERS,
                                 gate=FIT)
    # cut the Blender mesh where the solve cut it, then give each vertex its point's weights
    loop_point = np.zeros(len(fig.data.loops), np.int64)
    loop_point[loops.ravel()] = hum.corner_point.ravel()
    vert_point = C.split_vertices(fig, loop_point)
    for m in list(fig.modifiers):
        if m.type == "ARMATURE":
            fig.modifiers.remove(m)
    C.set_group_weights(fig, names, deform, Wp[vert_point])
    C.bind(fig, arm)
    return arm, dict(heat_ok=heat_ok, held_parts=hum.parts, cut_edges=hum.ncut, taken_from_arms=hum.arm_relabelled,
                     anchors=cfg, amps=amps, fit={c: dict(stretch=v[0][0], crack_mm=round(v[1][0] * 1000, 1))
                                                  for c, v in per.items()},
                     crack_gate_mm=round(SW.OPEN_GATE * hum.height * 1000, 1), height=round(ytop - y0, 4),
                     open_edges_at_feet=open_edges_near_feet(fig, 0.0))


def clips(arm, spec, amps):
    A = C.Animator(arm)
    for name, frames, pose_at in WC.clips(spec["weapon"], amps):
        A.clip(name, frames, pose_at)
    return A


reports = []
for src, specs in FRIEZES.items():
    C.reset()
    figs, total = figure_split(os.path.join(C.SRC, src))
    assert len(figs) == len(specs), f"{src}: {len(figs)} figures found, {len(specs)} expected"
    split_tris = [C.tri_count(f) for f in figs]
    for fig, spec in zip(figs, specs):
        if ONLY and spec["name"] not in ONLY.split(","):
            continue
        # work on this figure alone: hide the others from heat weighting and export
        for other in figs:
            other.hide_set(other is not fig)
        arm, info = build_figure(fig, spec)
        if info is None:  # CHAR_FIT_DUMP_ONLY: inputs saved, nothing built
            arm.hide_set(True)
            fig.hide_set(True)
            continue
        A = clips(arm, spec, info["amps"])
        info["stretch"] = C.stretch_gate(fig, arm, A, MIN_LEN, GATE)
        C.maybe_dump(spec["name"], fig, arm, A)
        C.export_glb(os.path.join(C.OUT, spec["name"] + ".glb"), [arm, fig])
        info.update(source=src, look=spec["look"], weapon_hand=spec["weapon"])
        reports.append(C.report(spec["name"], fig, arm, A, info))
        print("REPORT", json.dumps(reports[-1]))
        arm.hide_set(True)
        fig.hide_set(True)
    print("SPLIT", src, "total", total, "per figure", split_tris)
    blend = os.environ.get("CHAR_BLEND")
    if blend:
        bpy.ops.wm.save_as_mainfile(filepath=blend.replace(".blend", "_" + src.replace(".glb", ".blend")))
out = os.environ.get("CHAR_REPORT")
if out:
    json.dump(reports, open(out, "w"), indent=1)
