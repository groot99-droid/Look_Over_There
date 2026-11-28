"""Shared helpers for the character builds (tools/blender/characters/build_*.py).

Blender 5.2, run in the background:
  blender -b --factory-startup -P tools/blender/characters/build_trex.py
Every build reads its source from blender/characters/source/ (the owner's Meshy files, unchanged) and writes
models/characters/<name>.glb. Geometry and textures are kept: nothing is decimated or remeshed (docs/BLENDER.md rule 5).

Axes: the glTF files are y up with +z forward. Blender's importer turns a glTF point (x, y, z) into (x, -z, y),
so in Blender the characters face -Y and their left is +X. Bone names use .L for +X and .R for -X.
"""
import math
import os

import bpy
from mathutils import Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SRC = os.path.join(REPO, "blender", "characters", "source")
OUT = os.path.join(REPO, "models", "characters")
FPS = 24
AX = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}


def g2b(p):
    """glTF (y up, +z forward) to Blender (z up, -y forward)."""
    x, y, z = p
    return Vector((x, -z, y))


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.frame_start = 0


def import_glb(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o not in before]


def select(objs, active=None):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or objs[0]


def apply_transforms(objs):
    select(objs)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def islands(mesh):
    """Loose parts of a mesh as lists of vertex indices: connected through edges, and through vertices at the same
    position (the glTF importer splits vertices along UV seams, which would cut one bone into many parts)."""
    n = len(mesh.vertices)
    par = list(range(n))
    first = {}
    for v in mesh.vertices:
        k = (round(v.co.x, 5), round(v.co.y, 5), round(v.co.z, 5))
        if k in first:
            par[v.index] = first[k]
        else:
            first[k] = v.index

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    for e in mesh.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            par[b] = a
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return sorted(groups.values(), key=len, reverse=True)


# ---------------------------------------------------------------- armature
def build_armature(name, bones):
    """bones: list of (name, head, tail, parent or None, deform), Blender coordinates."""
    arm = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, arm)
    bpy.context.scene.collection.objects.link(ob)
    select([ob])
    bpy.ops.object.mode_set(mode="EDIT")
    made = {}
    for bn, h, t, p, d in bones:
        b = arm.edit_bones.new(bn)
        b.head, b.tail = Vector(h), Vector(t)
        b.use_deform = d
        if p:
            b.parent = made[p]
        made[bn] = b
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob


def seg_dist(p, a, b):
    ab = b - a
    L = ab.length_squared
    t = 0.0 if L == 0 else max(0.0, min(1.0, (p - a).dot(ab) / L))
    return (a + ab * t - p).length


class Weights:
    """Per-vertex bone weights, written to vertex groups at the end (top 4 influences, normalised)."""

    def __init__(self, mesh_ob, arm_ob):
        self.ob, self.arm = mesh_ob, arm_ob
        self.w = [dict() for _ in mesh_ob.data.vertices]
        self.segs = {b.name: (b.head_local.copy(), b.tail_local.copy()) for b in arm_ob.data.bones}

    def nearest(self, co, names, power=4.0, topk=3, eps=1e-4):
        ds = sorted((seg_dist(co, *self.segs[n]), n) for n in names)[:topk]
        ws = [1.0 / (d + eps) ** power for d, _ in ds]
        s = sum(ws)
        return {n: w / s for (d, n), w in zip(ds, ws)}

    def distance(self, vidx, names, **kw):
        V = self.ob.data.vertices
        for i in vidx:
            self.w[i] = self.nearest(V[i].co, names, **kw)

    def rigid(self, vidx, bone):
        for i in vidx:
            self.w[i] = {bone: 1.0}

    def closest_bone(self, vidx, names, step=1):
        """The bone whose segment comes closest to any of these vertices."""
        V = self.ob.data.vertices
        best = (1e9, None)
        for i in vidx[::step]:
            for n in names:
                d = seg_dist(V[i].co, *self.segs[n])
                if d < best[0]:
                    best = (d, n)
        return best[1]

    def average(self, vidx):
        """Make a loose part move as one piece: every vertex gets the part's mean weights."""
        acc = {}
        for i in vidx:
            for n, w in self.w[i].items():
                acc[n] = acc.get(n, 0.0) + w
        top = sorted(acc.items(), key=lambda kv: -kv[1])[:2]
        s = sum(w for _, w in top) or 1.0
        avg = {n: w / s for n, w in top}
        for i in vidx:
            self.w[i] = dict(avg)

    def from_groups(self):
        """Read the weights already in the vertex groups (after Blender's automatic weights)."""
        names = {g.index: g.name for g in self.ob.vertex_groups}
        for v in self.ob.data.vertices:
            d = {}
            for g in v.groups:
                if g.weight > 1e-4 and names[g.group] in self.segs:
                    d[names[g.group]] = g.weight
            self.w[v.index] = d

    def write(self):
        ob = self.ob
        ob.vertex_groups.clear()
        deform = [b.name for b in self.arm.data.bones if b.use_deform]
        vg = {n: ob.vertex_groups.new(name=n) for n in deform}
        for i, d in enumerate(self.w):
            top = sorted(((n, w) for n, w in d.items() if n in vg), key=lambda kv: -kv[1])[:4]
            s = sum(w for _, w in top)
            if s <= 0:
                raise RuntimeError(f"vertex {i} of {ob.name} has no weight")
            for n, w in top:
                vg[n].add([i], w / s, "REPLACE")


def bind(mesh_ob, arm_ob):
    for m in list(mesh_ob.modifiers):
        if m.type == "ARMATURE":
            mesh_ob.modifiers.remove(m)
    mesh_ob.parent = arm_ob
    mesh_ob.matrix_parent_inverse = arm_ob.matrix_world.inverted()
    m = mesh_ob.modifiers.new("Armature", "ARMATURE")
    m.object = arm_ob


# ---------------------------------------------------------------- animation
def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def lerp_pose(a, b, t):
    """Blend two poses ({bone: {"rot": {"X": deg, ...}, "axis": [(Vector, deg), ...], "loc": (x, y, z)}}) by t (0..1)."""
    out = {}
    for bn in set(a) | set(b):
        pa, pb = a.get(bn, {}), b.get(bn, {})
        ra, rb = pa.get("rot", {}), pb.get("rot", {})
        rot = {k: ra.get(k, 0.0) * (1 - t) + rb.get(k, 0.0) * t for k in set(ra) | set(rb)}
        la, lb = Vector(pa.get("loc", (0, 0, 0))), Vector(pb.get("loc", (0, 0, 0)))
        out[bn] = {"rot": rot, "loc": tuple(la.lerp(lb, t))}
        xa = {tuple(round(c, 6) for c in v): d for v, d in pa.get("axis", [])}
        xb = {tuple(round(c, 6) for c in v): d for v, d in pb.get("axis", [])}
        if xa or xb:
            out[bn]["axis"] = [(Vector(k), xa.get(k, 0.0) * (1 - t) + xb.get(k, 0.0) * t) for k in set(xa) | set(xb)]
    return out


def keyed(keys, f):
    """Pose at frame f from a list of (frame, pose) keys, eased (smoothstep) between keys."""
    if f <= keys[0][0]:
        return keys[0][1]
    for (f0, p0), (f1, p1) in zip(keys, keys[1:]):
        if f0 <= f <= f1:
            return lerp_pose(p0, p1, smooth((f - f0) / (f1 - f0)))
    return keys[-1][1]


class Animator:
    """Poses are given in armature space: {"X": deg, "Y": deg, "Z": deg} turns about Blender's axes (applied X, then
    Y, then Z) around the bone's head, on top of the rest pose. Positive X turns a forward-pointing bone down and
    a downward-pointing bone back; positive Z turns toward +Y from +X. Each clip is sampled on every frame."""

    def __init__(self, arm_ob):
        self.arm = arm_ob
        self.B = {b.name: b.matrix_local.to_quaternion() for b in arm_ob.data.bones}
        for pb in arm_ob.pose.bones:
            pb.rotation_mode = "QUATERNION"
        self.ad = arm_ob.animation_data_create()
        self.clips = []
        self.sources = []  # (name, frames, pose_at), for the stretch gate

    def set_pose(self, pose):
        for pb in self.arm.pose.bones:
            pb.rotation_quaternion = Quaternion()
            pb.location = Vector()
            pb.scale = Vector((1, 1, 1))
        for bn, spec in pose.items():
            pb = self.arm.pose.bones[bn]
            B = self.B[bn]
            Q = Quaternion()
            for ax in ("X", "Y", "Z"):
                deg = spec.get("rot", {}).get(ax, 0.0)
                if deg:
                    Q = Quaternion(AX[ax], math.radians(deg)) @ Q
            if "axis" in spec:  # extra turns about arbitrary axes: [(Vector, deg), ...]
                for axis, deg in spec["axis"]:
                    Q = Quaternion(Vector(axis).normalized(), math.radians(deg)) @ Q
            pb.rotation_quaternion = B.inverted() @ Q @ B
            if "loc" in spec:
                pb.location = B.inverted() @ Vector(spec["loc"])

    def clip(self, name, frames, pose_at):
        """pose_at(f) -> pose, sampled on frames 0..frames inclusive."""
        self.ad.action = None
        act = bpy.data.actions.new(name)
        act.use_fake_user = True
        self.ad.action = act
        for f in range(frames + 1):
            self.set_pose(pose_at(f))
            for pb in self.arm.pose.bones:
                pb.keyframe_insert("rotation_quaternion", frame=f, group=pb.name)
                pb.keyframe_insert("location", frame=f, group=pb.name)
        self.ad.action = None
        tr = self.ad.nla_tracks.new()
        tr.name = name
        st = tr.strips.new(name, 0, act)
        try:
            if getattr(st, "action_slot", None) is None and len(act.slots):
                st.action_slot = act.slots[0]
        except Exception:
            pass
        tr.mute = False
        self.clips.append((name, frames / FPS))
        self.sources.append((name, frames, pose_at))
        self.set_pose({})
        return act


# ---------------------------------------------------------------- stretch gate
def mute_nla(arm_ob):
    """Mute the clips' NLA tracks while poses are set by hand: an unmuted track would be evaluated on a depsgraph
    update and overwrite the pose with its own key at the current frame."""
    ad = arm_ob.animation_data
    if not ad:
        return []
    was = [(t, t.mute) for t in ad.nla_tracks]
    for t, _ in was:
        t.mute = True
    ad.action = None
    return was


def unmute_nla(arm_ob, was):
    for t, m in was:
        t.mute = m


def tri_edges(mesh_ob, min_len):
    """Unique edges of the mesh's triangles (quad diagonals included, as in the GLB) at least min_len long at rest."""
    me = mesh_ob.data
    me.calc_loop_triangles()
    E = set()
    for t in me.loop_triangles:
        a, b, c = t.vertices
        for u, v in ((a, b), (b, c), (c, a)):
            E.add((u, v) if u < v else (v, u))
    mw = mesh_ob.matrix_world
    rest = [mw @ v.co for v in me.vertices]
    return [(u, v, (rest[u] - rest[v]).length) for u, v in sorted(E) if (rest[u] - rest[v]).length >= min_len]


def stretch_gate(mesh_ob, arm_ob, anim, min_len, limit=2.0, step=1, allow=None):
    """Play every clip through the armature modifier and measure each triangle edge: its posed length over its rest
    length, or the inverse when it shrinks (the same measure as the node check). Fails the build when any frame of
    any clip takes an edge past `limit`; returns {clip: (worst, frame, edges over 1.5x, edges over 2x)}."""
    edges = tri_edges(mesh_ob, min_len)
    out, bad = {}, []
    muted = mute_nla(arm_ob)
    for name, frames, pose_at in anim.sources:
        worst = (0.0, 0, 0, 0)
        for f in list(range(0, frames + 1, step)) + ([frames] if frames % step else []):
            anim.set_pose(pose_at(f))
            bpy.context.view_layer.update()
            dg = bpy.context.evaluated_depsgraph_get()
            ev = mesh_ob.evaluated_get(dg)
            me = ev.to_mesh()
            mw = ev.matrix_world
            P = [mw @ v.co for v in me.vertices]
            ev.to_mesh_clear()
            w, n15, n2 = 0.0, 0, 0
            for u, v, L0 in edges:
                r = (P[u] - P[v]).length / L0
                q = max(r, 1.0 / max(r, 1e-6))
                if q > w:
                    w = q
                n15 += q > 1.5
                n2 += q > 2.0
            if w > worst[0]:
                worst = (round(w, 2), f, n15, n2)
        out[name] = worst
        lim = (allow or {}).get(name, limit)
        if worst[0] > lim:
            bad.append((name, worst))
    anim.set_pose({})
    unmute_nla(arm_ob, muted)
    bpy.context.view_layer.update()
    print("STRETCH", mesh_ob.name, out)
    if bad:
        raise RuntimeError(f"stretch gate: {mesh_ob.name} {bad} past {limit}x")
    return out


def dump(path, mesh_ob, arm_ob, anim, extra=None):
    """Rest mesh, bones, weights and every clip's bone deform matrices, for working out weights outside Blender."""
    import numpy as np
    me = mesh_ob.data
    me.calc_loop_triangles()
    mw = mesh_ob.matrix_world
    verts = np.array([list(mw @ v.co) for v in me.vertices], dtype=np.float64)
    tris = np.array([list(t.vertices) for t in me.loop_triangles], dtype=np.int32)
    A = arm_ob.matrix_world
    bones = list(arm_ob.data.bones)
    names = [b.name for b in bones]
    heads = np.array([list(A @ b.head_local) for b in bones])
    tails = np.array([list(A @ b.tail_local) for b in bones])
    parents = np.array([names.index(b.parent.name) if b.parent else -1 for b in bones])
    deform = np.array([b.use_deform for b in bones])
    W = np.zeros((len(verts), len(bones)))
    gi = {g.index: g.name for g in mesh_ob.vertex_groups}
    for v in me.vertices:
        for g in v.groups:
            n = gi[g.group]
            if n in names:
                W[v.index, names.index(n)] = g.weight
    data = dict(verts=verts, tris=tris, names=np.array(names), heads=heads, tails=tails, parents=parents,
                deform=deform, weights=W)
    inv = {b.name: (A @ b.matrix_local).inverted() for b in bones}
    muted = mute_nla(arm_ob)
    for name, frames, pose_at in anim.sources:
        M = np.zeros((frames + 1, len(bones), 4, 4))
        for f in range(frames + 1):
            anim.set_pose(pose_at(f))
            bpy.context.view_layer.update()
            for k, b in enumerate(bones):
                pb = arm_ob.pose.bones[b.name]
                M[f, k] = np.array(A @ pb.matrix @ inv[b.name])
        data["clip_" + name] = M
    anim.set_pose({})
    unmute_nla(arm_ob, muted)
    bpy.context.view_layer.update()
    for k, v in (extra or {}).items():
        data[k] = np.asarray(v)
    np.savez_compressed(path, **data)
    print("dumped", path)


# ---------------------------------------------------------------- weights as arrays, and the cut
def mesh_arrays(mesh_ob):
    """World rest positions (V, 3), triangles (T, 3) as vertex ids and the loop of each triangle corner (T, 3)."""
    import numpy as np
    me = mesh_ob.data
    me.calc_loop_triangles()
    mw = mesh_ob.matrix_world
    verts = np.array([list(mw @ v.co) for v in me.vertices], dtype=np.float64)
    tris = np.array([list(t.vertices) for t in me.loop_triangles], dtype=np.int64)
    loops = np.array([list(t.loops) for t in me.loop_triangles], dtype=np.int64)
    return verts, tris, loops


def bone_arrays(arm_ob):
    import numpy as np
    A = arm_ob.matrix_world
    bones = list(arm_ob.data.bones)
    names = [b.name for b in bones]
    heads = np.array([list(A @ b.head_local) for b in bones])
    tails = np.array([list(A @ b.tail_local) for b in bones])
    parents = np.array([names.index(b.parent.name) if b.parent else -1 for b in bones])
    deform = np.array([b.use_deform for b in bones])
    return names, heads, tails, parents, deform


def group_weights(mesh_ob, names):
    """The vertex-group weights as an array (V, bones)."""
    import numpy as np
    W = np.zeros((len(mesh_ob.data.vertices), len(names)))
    gi = {g.index: g.name for g in mesh_ob.vertex_groups}
    col = {n: j for j, n in enumerate(names)}
    for v in mesh_ob.data.vertices:
        for g in v.groups:
            j = col.get(gi[g.group])
            if j is not None:
                W[v.index, j] = g.weight
    return W


def set_group_weights(mesh_ob, names, deform, W, k=4):
    """Write (V, bones) weights to the vertex groups: deform bones only, k strongest per vertex, normalised."""
    import numpy as np
    import skinweights as SW
    W = np.where(np.asarray(deform, bool)[None], W, 0.0)
    W = SW.limit(W, k)
    if (W.sum(1) < 0.5).any():
        raise RuntimeError(f"{mesh_ob.name}: {(W.sum(1) < 0.5).sum()} vertices have no weight")
    mesh_ob.vertex_groups.clear()
    groups = {j: mesh_ob.vertex_groups.new(name=n) for j, n in enumerate(names) if deform[j]}
    for i in range(len(W)):
        for j in W[i].nonzero()[0]:
            groups[int(j)].add([i], float(W[i, j]), "REPLACE")


def split_vertices(mesh_ob, loop_point):
    """Cut the mesh: every (vertex, point) pair found among the loops becomes its own vertex at the same place, so
    faces on two sides of a cut no longer share it. Polygons, loops (their order), UVs, materials, smooth shading
    and custom normals are kept; no face is added or removed. Returns the point of each new vertex."""
    import numpy as np
    me = mesh_ob.data
    nl = len(me.loops)
    lv = np.zeros(nl, np.int64)
    me.loops.foreach_get("vertex_index", lv)
    lp = np.asarray(loop_point, np.int64)
    pairs, new_v = np.unique(np.stack([lv, lp], 1), axis=0, return_inverse=True)
    new_v = new_v.ravel()
    if len(pairs) == len(me.vertices):  # nothing to cut
        return pairs[:, 1]
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)[pairs[:, 0]]
    ls = np.zeros(len(me.polygons), np.int64)
    lt = np.zeros(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", ls)
    me.polygons.foreach_get("loop_total", lt)
    faces = [list(new_v[s:s + t]) for s, t in zip(ls, lt)]
    normals = None
    try:
        normals = [tuple(c.vector) for c in me.corner_normals]
    except Exception:  # noqa: BLE001
        pass
    uvs = {}
    for uv in me.uv_layers:
        a = np.zeros(nl * 2)
        uv.data.foreach_get("uv", a)
        uvs[uv.name] = a
    mat_idx = np.zeros(len(me.polygons), np.int64)
    me.polygons.foreach_get("material_index", mat_idx)
    smooth = np.zeros(len(me.polygons), bool)
    me.polygons.foreach_get("use_smooth", smooth)
    m2 = bpy.data.meshes.new(me.name)
    m2.from_pydata(co.tolist(), [], faces)
    for name, a in uvs.items():
        m2.uv_layers.new(name=name).data.foreach_set("uv", a)
    for mat in me.materials:
        m2.materials.append(mat)
    m2.polygons.foreach_set("material_index", mat_idx)
    m2.polygons.foreach_set("use_smooth", smooth)
    if normals is not None:
        m2.normals_split_custom_set(normals)
    m2.update()
    old = mesh_ob.data
    mesh_ob.data = m2
    bpy.data.meshes.remove(old)
    m2.name = mesh_ob.name
    return pairs[:, 1]


# ---------------------------------------------------------------- export
def scrub():
    """No custom properties anywhere (they could carry local paths or user data into the public repo)."""
    colls = [bpy.data.objects, bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.images,
             bpy.data.textures, bpy.data.actions, bpy.data.scenes, bpy.data.collections, bpy.data.node_groups]
    for coll in colls:
        for idb in coll:
            for k in list(idb.keys()):
                try:
                    del idb[k]
                except Exception:
                    pass
    for ob in bpy.data.objects:
        if ob.type == "ARMATURE":
            for b in ob.data.bones:
                for k in list(b.keys()):
                    del b[k]
            for pb in ob.pose.bones:
                for k in list(pb.keys()):
                    del pb[k]
    for img in bpy.data.images:
        img.filepath = ""  # packed or in memory: no path travels with it


def export_glb(path, objs, webp=True):
    if os.environ.get("CHAR_NOEXPORT"):
        print("export skipped", path)
        return
    scrub()
    select(objs)
    bpy.context.scene.frame_set(0)
    opts = dict(filepath=path, export_format="GLB", use_selection=True, export_yup=True, export_apply=False,
                export_animations=True, export_animation_mode="NLA_TRACKS", export_force_sampling=True,
                export_frame_step=1, export_skins=True, export_def_bones=False, export_reset_pose_bones=True,
                export_extras=False, export_cameras=False, export_lights=False, export_optimize_animation_size=False,
                export_image_format="WEBP" if webp else "AUTO", export_image_quality=90,
                export_image_webp_fallback=False, export_materials="EXPORT", export_normals=True,
                export_texcoords=True, export_tangents=False, export_morph=False)
    known = {p.identifier for p in bpy.ops.export_scene.gltf.get_rna_type().properties}
    dropped = sorted(k for k in opts if k not in known)
    if dropped:
        print("export: options not in this Blender:", dropped)
    bpy.ops.export_scene.gltf(**{k: v for k, v in opts.items() if k in known})
    print("wrote", path, os.path.getsize(path))


def maybe_dump(name, mesh_ob, arm_ob, anim, extra=None):
    d = os.environ.get("CHAR_DUMP")
    if d:
        os.makedirs(d, exist_ok=True)
        dump(os.path.join(d, name + ".npz"), mesh_ob, arm_ob, anim, extra)


def report(name, mesh_ob, arm_ob, anim, extra=None):
    bb = [mesh_ob.matrix_world @ v.co for v in mesh_ob.data.vertices]  # the rest pose, not the evaluated mesh
    mn = [min(v[i] for v in bb) for i in range(3)]
    mx = [max(v[i] for v in bb) for i in range(3)]
    # glTF axes: x = x, y = Blender z, z = -Blender y
    d = {"name": name, "tris": tri_count(mesh_ob), "verts": len(mesh_ob.data.vertices),
         "bones": len(arm_ob.data.bones), "deform_bones": sum(1 for b in arm_ob.data.bones if b.use_deform),
         "clips": [(n, round(s, 3)) for n, s in anim.clips],
         "gltf_min": [round(mn[0], 4), round(mn[2], 4), round(-mx[1], 4)],
         "gltf_max": [round(mx[0], 4), round(mx[2], 4), round(-mn[1], 4)]}
    if extra:
        d.update(extra)
    return d
