"""The store's rebake (docs/BLENDER.md, R4): lightmaps for one of the store's floors, with no change to its geometry.

  blender -b --factory-startup --python tools/blender/bake_store.py -- --scene B1 --stage bake --samples 512 --work <dir>
  blender -b --factory-startup --python tools/blender/bake_store.py -- --scene B1 --stage render --render-samples 128 --work <dir>
  blender -b --factory-startup --python tools/blender/bake_store.py -- --scene B1 --stage compare --a <old glb> --b world/B1.glb
  python tools/store_lightmap_glb.py B1 <work folder>          # writes the lightmap UVs into world/B1.glb and the WebP lightmaps

Run from the repo root. How it keeps the geometry: the store file (blender/Look_Over_There.blend) is not opened or changed at all. The bake scene is built from the shipped world/<scene>.glb itself, not
from the .blend: every glTF primitive becomes one Blender mesh whose vertex i is the glTF vertex i (Draco decoded with the glTF add-on's own
Draco library), so the lightmap UV found for each Blender vertex is the TEXCOORD_1 of that glTF vertex. Islands are only cut where the GLB
already splits its vertices, so no vertex needs two lightmap UVs. tools/store_lightmap_glb.py then adds TEXCOORD_1 as a new accessor next to
the Draco data and the lightmap extras to the baked materials; every byte of the existing buffers, accessors and primitives stays as it was.
The light is the floor's own: the GLB's glowing tubes (M_Fluorescent, at their exported emissive strength) and the store file's world
(a flat grey, 0.0509 at strength 1). The store file has no lamp objects on its floors (B1, L2).

Outputs (in --work, default <system temp>/farway_store_<scene>): <scene>_<n>.png (8-bit, sRGB-encoded, each map's white point at its 99.5th
percentile texel), <scene>_uv1.bin and <scene>_bake.json (which primitive has which UV1, which material goes on which map, the scales),
and with --stage render the three review stills, written to docs/renders/<scene>/.
"""
import bpy
import bmesh
import ctypes
import glob
import json
import math
import os
import struct
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


SCENE = arg("--scene", "B1")
STAGE = arg("--stage", "bake")
SAMPLES = int(arg("--samples", "512"))
RSAMPLES = int(arg("--render-samples", "128"))
ROOT = Path(arg("--root", ".")).resolve()
WORK = Path(arg("--work", os.path.join(tempfile.gettempdir(), f"farway_store_{SCENE}")))
WORK.mkdir(parents=True, exist_ok=True)
SCRATCH = Path(tempfile.mkdtemp(prefix=f"farway_store_{SCENE}_"))     # the GLB's images and the denoiser's EXR: not outputs
GLB = ROOT / "world" / f"{SCENE}.glb"
MARGIN_PX = 8
LM_URL = "world/lightmaps/" + SCENE + "_{}.webp"
MAX_PAGE = 2048
DENSITY = 32.0                                      # px/m wanted indoors (R1); the packer settles lower if four 2048 pages cannot hold it

# Which baked materials share a map. Anything baked that is not named goes on the last map.
GROUPS = {
    "B1": [["M_D_floor_B1", "M_D_floor_L1", "M_D_stains", "M_Door", "M_Pipes"],
           ["M_D_ceil_B1", "M_D_ceil_L1", "M_D_trim"],
           ["M_D_wall_B1", "M_D_wall_L1"],
           []],
    "L2": [["M_D_floor_L2", "M_D_floor_L3", "M_D_ceil_L1", "M_D_stains", "M_Door"],
           ["M_D_ceil_L2", "M_D_ceil_L3", "M_D_trim"],
           ["M_D_wall_L2", "M_D_wall_L3"],
           []],                                     # the 150 door leaves, the frames, the housings, the dead panel, the rails
}[SCENE]
PAGE_MARGIN = {"B1": {1: 4, 3: 4}, "L2": {1: 4, 3: 4}}[SCENE]   # the trim's and the props' thousands of small islands: 4 px between islands there, 8 px elsewhere
EXTERIOR_SCALE = 0.12                               # faces that look out of the building (seen from nowhere inside) get this fraction of the density
# Lamp parts: allowed to clip to white (they sit against the glowing tubes); every other material keeps its 99.5th percentile under the map's white.
HOT = {"M_Fixture_Housing", "M_Fluorescent_Dead"}
# Never baked: they stay as exported (the water keeps its see-through surface, glass stays glass, the lit tubes and the exit sign glow).
# Glass (transmission or alpha blend), anything glowing and any mesh that is skinned or drawn in more than one place are left out on every floor anyway.
# On L2 the loose props (the textured furniture models) also stay on the page's lights: their lightmap UVs would put the GLB over its
# size budget (L2's 150 door leaves alone carry 78 000 vertices of lightmap UV). They still cast light and shadow in the bake.
PROPS_L2 = {"SchoolChair_01", "WetFloorSign_01", "cardboard_box_01", "classic_laptop", "classic_laptop_screen", "dustpan", "fire_hydrant",
            "fire_hydrant_aged", "industrial_storage_cart", "korean_fire_extinguisher_01_body", "korean_public_payphone_01", "metal_office_desk",
            "metal_trash_can", "metal_trash_can_rust", "metal_trash_can_rust.001", "plastic_broom", "plunger", "steel_frame_shelves_01", "wooden_bucket_01"}
NEVER = {"B1": {"M_Water", "M_Fluorescent", "M_X_exit"},
         "L2": {"M_Fluorescent", "M_X_exit"} | PROPS_L2}[SCENE]
# The plan view hides what starts above this height (Blender z, metres): the ceiling and what hangs from it.
CEILING_CUT = {"B1": -0.75, "L2": 5.45}[SCENE]


# ------------------------------------------------------------------ the GLB, read and Draco-decoded
def read_glb(path):
    b = Path(path).read_bytes()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    off = 20 + n
    bn = struct.unpack("<I", b[off:off + 4])[0]
    return j, b[off + 8:off + 8 + bn]


CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def draco_lib():
    """The Draco bridge library the glTF add-on itself decodes with (found by the add-on's own path rule)."""
    import io_scene_gltf2
    try:
        from io_scene_gltf2.io.com.library import dll_path
        p = dll_path("bf_intern_draco_bridge", "Draco")
    except Exception:
        p = None
    cands = [str(p)] if p else []
    for base in {bpy.utils.resource_path("LOCAL"), os.path.dirname(bpy.app.binary_path), os.path.dirname(io_scene_gltf2.__file__)}:
        cands += glob.glob(os.path.join(base, "**", "*draco_bridge*"), recursive=True) + glob.glob(os.path.join(base, "**", "*extern_draco*"), recursive=True)
    cands += glob.glob(os.path.join(os.path.dirname(bpy.app.binary_path), "lib", "*draco_bridge*"))
    for p in cands:
        if p and os.path.isfile(p):
            lib = ctypes.CDLL(p)
            V, U32, SZ, B = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_size_t, ctypes.c_bool
            alias = {"decoderGetAttributeByteLength": "decoderAttributeByteLength", "decoderGetIndicesByteLength": "decoderIndicesByteLength"}
            for name, res, args in (("decoderCreate", V, []), ("decoderRelease", None, [V]), ("decoderDecode", B, [V, ctypes.c_char_p, SZ]),
                                    ("decoderGetVertexCount", U32, [V]), ("decoderGetIndexCount", U32, [V]),
                                    ("decoderReadAttribute", B, [V, U32, SZ, ctypes.c_char_p]), ("decoderGetAttributeByteLength", SZ, [V, U32]),
                                    ("decoderCopyAttribute", None, [V, U32, V]), ("decoderReadIndices", B, [V, SZ]),
                                    ("decoderGetIndicesByteLength", SZ, [V]), ("decoderCopyIndices", None, [V, V])):
                f = getattr(lib, name, None) or getattr(lib, alias[name])
                f.restype, f.argtypes = res, args
                setattr(lib, "_" + name, f)
            print("draco library:", os.path.basename(p))
            return lib
    raise RuntimeError("the glTF add-on's Draco library was not found")


def decode_prim(j, BIN, prim, lib):
    """{semantic: array} and the indices of one primitive, Draco-decoded (or read plainly when it has no Draco)."""
    ext = prim.get("extensions", {}).get("KHR_draco_mesh_compression")
    out = {}
    if not ext:
        for sem, ai in prim["attributes"].items():
            out[sem] = read_accessor(j, BIN, ai)
        return out, read_accessor(j, BIN, prim["indices"]).reshape(-1)
    bv = j["bufferViews"][ext["bufferView"]]
    data = BIN[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]]
    d = lib._decoderCreate()
    try:
        if not lib._decoderDecode(d, data, len(data)):
            raise RuntimeError("draco decode failed")
        for sem, ai in prim["attributes"].items():
            acc = j["accessors"][ai]
            if sem not in ext["attributes"]:
                out[sem] = read_accessor(j, BIN, ai)
                continue
            uid = ext["attributes"][sem]
            if not lib._decoderReadAttribute(d, uid, acc["componentType"], acc["type"].encode()):
                raise RuntimeError(f"draco attribute {sem} failed")
            nb = lib._decoderGetAttributeByteLength(d, uid)
            buf = ctypes.create_string_buffer(nb)
            lib._decoderCopyAttribute(d, uid, ctypes.cast(buf, ctypes.c_void_p))
            a = np.frombuffer(buf.raw, CT[acc["componentType"]]).reshape(-1, NC[acc["type"]]).copy()
            assert len(a) == acc["count"], (sem, len(a), acc["count"])
            out[sem] = a
        ia = j["accessors"][prim["indices"]]
        if not lib._decoderReadIndices(d, ia["componentType"]):
            raise RuntimeError("draco indices failed")
        nb = lib._decoderGetIndicesByteLength(d)
        buf = ctypes.create_string_buffer(nb)
        lib._decoderCopyIndices(d, ctypes.cast(buf, ctypes.c_void_p))
        idx = np.frombuffer(buf.raw, CT[ia["componentType"]]).copy()
        assert len(idx) == ia["count"]
    finally:
        lib._decoderRelease(d)
    return out, idx


def read_accessor(j, BIN, i):
    a = j["accessors"][i]
    bv = j["bufferViews"][a["bufferView"]]
    dt = np.dtype(CT[a["componentType"]])
    nc = NC[a["type"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", dt.itemsize * nc)
    raw = np.frombuffer(BIN, np.uint8, count=stride * (a["count"] - 1) + dt.itemsize * nc, offset=start)
    return np.lib.stride_tricks.as_strided(raw, (a["count"], nc * dt.itemsize), (stride, 1)).copy().view(dt).reshape(a["count"], nc)


def door_poses(j):
    """{node index: rotation} that closes every door leaf the way the page does when it loads the floor (index.html: the leaf's local
    rotation becomes a yaw of closed_yaw_deg about +Y; the export may hold it open or ajar). Read from world/<scene>.json's doors."""
    p = ROOT / "world" / f"{SCENE}.json"
    if not p.exists():
        return {}
    names = {nd.get("name"): i for i, nd in enumerate(j["nodes"])}
    out = {}
    for d in json.loads(p.read_text()).get("doors", []):
        i = names.get(d.get("name"))
        if i is not None and "matrix" not in j["nodes"][i] and "closed_yaw_deg" in d:
            a = math.radians(d["closed_yaw_deg"])
            out[i] = [0.0, math.sin(a / 2), 0.0, math.cos(a / 2)]
    return out


def node_matrices(j, rot=None):
    """World matrix (glTF space) of every node; `rot` replaces some nodes' local rotation (the doors, closed)."""
    W = {}
    rot = rot or {}

    def local(i):
        nd = j["nodes"][i]
        if "matrix" in nd:
            return np.array(nd["matrix"], float).reshape(4, 4).T
        t = nd.get("translation", [0, 0, 0]); r = rot.get(i, nd.get("rotation", [0, 0, 0, 1])); s = nd.get("scale", [1, 1, 1])
        x, y, z, w = r
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        M = np.eye(4); M[:3, :3] = R * np.array(s)[None, :]; M[:3, 3] = t
        return M

    def walk(i, P):
        W[i] = P @ local(i)
        for c in j["nodes"][i].get("children", []):
            walk(c, W[i])
    for sc in j["scenes"]:
        for r in sc["nodes"]:
            walk(r, np.eye(4))
    return W


G2B = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)     # glTF (x, y, z) -> Blender (x, -z, y)


# ------------------------------------------------------------------ bake materials from the GLB's own materials
def glb_images(j, BIN):
    paths = {}
    d = SCRATCH / "glb_images"
    d.mkdir(exist_ok=True)
    for i, im in enumerate(j.get("images", [])):
        bv = j["bufferViews"][im["bufferView"]]
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(im.get("mimeType"), "png")
        p = d / f"img_{i}.{ext}"
        p.write_bytes(BIN[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]])
        paths[i] = str(p)
    return paths


def tex_node(nt, j, info, imgs, colorspace):
    t = j["textures"][info["index"]]
    src = t.get("extensions", {}).get("EXT_texture_webp", {}).get("source", t.get("source"))
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = bpy.data.images.load(imgs[src], check_existing=True)
    n.image.colorspace_settings.name = colorspace
    uvn = nt.nodes.new("ShaderNodeUVMap"); uvn.uv_map = "UVMap"
    tt = info.get("extensions", {}).get("KHR_texture_transform")
    if tt:                                           # glTF's transform is on v-down UVs: u' = o + s*u (rotation ignored: none in the store)
        mp = nt.nodes.new("ShaderNodeMapping")
        so = tt.get("scale", [1, 1]); of = tt.get("offset", [0, 0])
        mp.inputs["Scale"].default_value = (so[0], so[1], 1)
        mp.inputs["Location"].default_value = (of[0], 1 - so[1] - of[1], 0)
        nt.links.new(uvn.outputs[0], mp.inputs[0]); nt.links.new(mp.outputs[0], n.inputs[0])
    else:
        nt.links.new(uvn.outputs[0], n.inputs[0])
    return n


def make_material(j, mi, imgs):
    m = j["materials"][mi]
    mat = bpy.data.materials.new("BK_" + m["name"])
    mat.use_nodes = True
    nt = mat.node_tree
    bs = nt.nodes["Principled BSDF"]
    pbr = m.get("pbrMetallicRoughness", {})
    f = pbr.get("baseColorFactor", [1, 1, 1, 1])
    bs.inputs["Base Color"].default_value = f
    bs.inputs["Metallic"].default_value = 0.0           # the bake wants the light a matte surface gets (a metal's diffuse pass is black); the page shows base colour x light
    bs.inputs["Roughness"].default_value = pbr.get("roughnessFactor", 1.0)
    alpha_from = None
    if "baseColorTexture" in pbr:
        tn = tex_node(nt, j, pbr["baseColorTexture"], imgs, "sRGB")
        mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"; mix.inputs["Factor"].default_value = 1
        mix.inputs["A"].default_value = f; nt.links.new(tn.outputs["Color"], mix.inputs["B"])
        nt.links.new(mix.outputs["Result"], bs.inputs["Base Color"])
        alpha_from = tn
    mode = m.get("alphaMode", "OPAQUE")
    if mode != "OPAQUE":
        if alpha_from is not None:
            mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = f[3]
            nt.links.new(alpha_from.outputs["Alpha"], mul.inputs[0]); nt.links.new(mul.outputs[0], bs.inputs["Alpha"])
        else:
            bs.inputs["Alpha"].default_value = f[3]
    tr = m.get("extensions", {}).get("KHR_materials_transmission")
    if tr:
        bs.inputs["Transmission Weight"].default_value = tr.get("transmissionFactor", 0)
    ef = m.get("emissiveFactor", [0, 0, 0])
    es = m.get("extensions", {}).get("KHR_materials_emissive_strength", {}).get("emissiveStrength", 1.0)
    if max(ef) > 0:
        bs.inputs["Emission Color"].default_value = (*ef, 1)
        bs.inputs["Emission Strength"].default_value = es
        if "emissiveTexture" in m:
            tn = tex_node(nt, j, m["emissiveTexture"], imgs, "sRGB")
            mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"; mix.inputs["Factor"].default_value = 1
            mix.inputs["A"].default_value = (*ef, 1); nt.links.new(tn.outputs["Color"], mix.inputs["B"])
            nt.links.new(mix.outputs["Result"], bs.inputs["Emission Color"])
    mat.use_backface_culling = not m.get("doubleSided", False)
    return mat


# ------------------------------------------------------------------ the bake scene
def build_scene():
    j, BIN = read_glb(GLB)
    lib = draco_lib()
    doors = door_poses(j)
    W = node_matrices(j, doors)                      # the bake sees the doors shut, as the page shows them on arrival
    imgs = glb_images(j, BIN)
    print(f"{len(doors)} door leaves closed for the bake")
    sc = bpy.context.scene                           # run with --factory-startup and no .blend: the empty start scene becomes the bake scene
    if bpy.data.filepath:
        raise RuntimeError("run the bake and the stills without a .blend (the store file is only opened by verify_world.py)")
    for o in list(sc.collection.all_objects):
        bpy.data.objects.remove(o)
    src = bpy.data.collections.get(f"Level_{SCENE}")
    lights = bpy.data.collections.new("Lights"); sc.collection.children.link(lights)
    for o in (src.all_objects if src else []):                        # the floor's own lights, as the store file has them
        if o.type == "LIGHT" and not o.hide_render:
            c = o.copy(); c.parent = None; c.matrix_world = o.matrix_world.copy(); lights.objects.link(c)
    w = bpy.data.scenes.get("World_All").world if bpy.data.scenes.get("World_All") else None
    if w is None:                                    # run without the store file: its world as it is (a flat grey background, 0.0509, strength 1)
        w = bpy.data.worlds.new("World"); w.use_nodes = True
        bg = w.node_tree.nodes["Background"]; bg.inputs["Color"].default_value = (0.05087609, 0.05087609, 0.05087609, 1); bg.inputs["Strength"].default_value = 1.0
    sc.world = w
    art = bpy.data.collections.new("Art"); sc.collection.children.link(art)
    use = {}
    for ni, nd in enumerate(j["nodes"]):
        if "mesh" in nd:
            use.setdefault(nd["mesh"], []).append(ni)
    mats = {}
    prims = []                                       # (object, mesh index, primitive index, material index, eligible)
    mat_ok = {}
    for mi_, mesh in enumerate(j["meshes"]):
        for pi, p in enumerate(mesh["primitives"]):
            skinned = "JOINTS_0" in p["attributes"]
            for ni in use.get(mi_, []):
                elig = not skinned and len(use[mi_]) == 1
                mt = p.get("material")
                if mt is not None:
                    mat_ok[mt] = mat_ok.get(mt, True) and elig
                if skinned:
                    continue                         # the cameras' heads (the page moves them): small, left out of the bake
                attrs, idx = decode_prim(j, BIN, p, lib)
                P = attrs["POSITION"].astype(np.float64)
                M = G2B @ W[ni]
                Pw = (np.c_[P, np.ones(len(P))] @ M.T)[:, :3]
                me = bpy.data.meshes.new(f"m{mi_}_{pi}_{ni}")
                tri = idx.reshape(-1, 3).astype(np.int64)
                me.vertices.add(len(Pw)); me.vertices.foreach_set("co", Pw.astype(np.float32).ravel())
                me.loops.add(len(tri) * 3); me.loops.foreach_set("vertex_index", tri.ravel().astype(np.int32))
                me.polygons.add(len(tri)); me.polygons.foreach_set("loop_start", np.arange(0, len(tri) * 3, 3, dtype=np.int32))
                me.update(calc_edges=True)
                if "TEXCOORD_0" in attrs:
                    uv = attrs["TEXCOORD_0"].astype(np.float64)
                    lu = uv[tri.ravel()]; lu[:, 1] = 1 - lu[:, 1]
                    me.uv_layers.new(name="UVMap").data.foreach_set("uv", lu.astype(np.float32).ravel())
                if "NORMAL" in attrs:
                    Nn = attrs["NORMAL"].astype(np.float64) @ np.linalg.inv(M[:3, :3])
                    Nn /= np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-9)
                    me.normals_split_custom_set_from_vertices([tuple(v) for v in Nn])
                if mt is not None:
                    if mt not in mats:
                        mats[mt] = make_material(j, mt, imgs)
                    me.materials.append(mats[mt])
                o = bpy.data.objects.new(me.name, me); art.objects.link(o)
                prims.append([o, mi_, pi, mt, elig])
    def bakeable(mt):
        m = j["materials"][mt]
        if not mat_ok.get(mt) or m["name"] in NEVER or max(m.get("emissiveFactor", [0, 0, 0])) > 0:
            return False                             # used by a moving or repeated mesh, or glowing: stays as exported
        if m.get("extensions", {}).get("KHR_materials_transmission"):
            return False                             # glass
        return m.get("alphaMode", "OPAQUE") != "BLEND" or m["name"] == "M_D_stains"
    baked = {mt for mt in mat_ok if bakeable(mt)}
    print(f"bake scene: {len(prims)} primitive objects, {len(lights.objects)} lights, {len(baked)} materials to bake")
    return j, sc, prims, baked, lights


def select_only(objs):
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def vertex_uvs(o, name):
    """Per-vertex UV of a layer, and how many vertices carry two different UVs."""
    me = o.data
    lv = np.empty(len(me.loops), np.int32); me.loops.foreach_get("vertex_index", lv)
    uv = np.empty(len(me.loops) * 2, np.float32); me.uv_layers[name].data.foreach_get("uv", uv); uv = uv.reshape(-1, 2)
    V = np.full((len(me.vertices), 2), np.nan)
    V[lv] = uv
    bad = np.abs(V[lv] - uv).max(axis=1) > 1e-6
    return V, lv, uv, set(np.unique(lv[bad]).tolist())


def components(me):
    """Faces grouped by shared vertices (the GLB's own islands)."""
    bm = bmesh.new(); bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    comp = [-1] * len(bm.faces); c = 0
    for f in bm.faces:
        if comp[f.index] >= 0:
            continue
        st = [f]; comp[f.index] = c
        while st:
            a = st.pop()
            for v in a.verts:
                for g in v.link_faces:
                    if comp[g.index] < 0:
                        comp[g.index] = c; st.append(g)
        c += 1
    bm.free()
    return np.array(comp), c


def area3d(o):
    return sum(p.area for p in o.data.polygons)


def uv_area(o, name):
    me = o.data
    uv = np.empty(len(me.loops) * 2, np.float32); me.uv_layers[name].data.foreach_get("uv", uv); uv = uv.reshape(-1, 3, 2)
    a = uv[:, 1] - uv[:, 0]; b = uv[:, 2] - uv[:, 0]
    return float(np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]).sum() / 2)


def unwrap(objs):
    """A lightmap UV ("LM") on every object, cut only where the GLB splits its vertices."""
    for o in objs:
        o.data.uv_layers.new(name="LM")
        o.data.uv_layers.active = o.data.uv_layers["LM"]
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.0, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    fixed = 0
    for o in objs:                                   # a piece smart_project cut through a shared vertex: unwrapped whole instead (one island per piece)
        _, _, _, bad = vertex_uvs(o, "LM")
        if not bad:
            continue
        comp, _ = components(o.data)
        lv = np.empty(len(o.data.loops), np.int32); o.data.loops.foreach_get("vertex_index", lv)
        badc = set(comp[np.isin(lv.reshape(-1, 3), list(bad)).any(axis=1)].tolist())
        sel = np.isin(comp, list(badc))
        o.data.polygons.foreach_set("select", sel)
        vs = np.zeros(len(o.data.vertices), bool); vs[lv.reshape(-1, 3)[sel].ravel()] = True
        o.data.vertices.foreach_set("select", vs)
        bpy.context.tool_settings.mesh_select_mode = (False, False, True)
        fixed += len(badc)
        select_only([o])
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.mark_seam(clear=True)
        bpy.ops.uv.unwrap(method="CONFORMAL", margin=0.0, fill_holes=False)
        bpy.ops.object.mode_set(mode="OBJECT")
    print(f"  unwrap: {fixed} pieces unwrapped whole")
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode="OBJECT")
    ext_area = 0.0
    for o in objs:                                   # pieces that face out of the building: shrunk, so the room gets the texels
        comp, nc = components(o.data)
        ext = exterior_faces(o)
        uv = np.empty(len(o.data.loops) * 2, np.float32); o.data.uv_layers["LM"].data.foreach_get("uv", uv); uv = uv.reshape(-1, 3, 2)
        ar = np.empty(len(o.data.polygons), np.float32); o.data.polygons.foreach_get("area", ar)
        frac = np.bincount(comp, weights=ar * ext, minlength=nc) / np.maximum(np.bincount(comp, weights=ar, minlength=nc), 1e-12)
        shrink = frac[comp] > 0.5
        if shrink.any():
            for c in np.unique(comp[shrink]):
                f = comp == c
                cen = uv[f].reshape(-1, 2).mean(axis=0)
                uv[f] = cen + (uv[f] - cen) * EXTERIOR_SCALE
            o.data.uv_layers["LM"].data.foreach_set("uv", uv.ravel())
            ext_area += float(ar[shrink].sum())
        o["exterior"] = shrink.astype(np.int8).tobytes()
    print(f"  {ext_area:.0f} m2 face out of the building (shrunk x{EXTERIOR_SCALE})")
    return ext_area


BVH = None


def exterior_faces(o):
    """1 for a face that looks out of the level: a ray 60 m out of its front hits nothing, and its back either sees nothing either or meets
    the rest of its own wall or slab within 0.4 m (the outer skin of the shell)."""
    from mathutils.bvhtree import BVHTree
    global BVH
    if BVH is None:
        verts, polys = [], []
        for ob in bpy.context.scene.objects:
            if ob.type != "MESH":
                continue
            b0 = len(verts); me = ob.data
            co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get("co", co)
            verts += [tuple(v) for v in co.reshape(-1, 3).tolist()]
            lv = np.empty(len(me.loops), np.int32); me.loops.foreach_get("vertex_index", lv)
            polys += [tuple(t) for t in (lv.reshape(-1, 3) + b0).tolist()]
        BVH = BVHTree.FromPolygons(verts, polys, epsilon=0.0)
    me = o.data
    out = np.zeros(len(me.polygons), np.float32)
    for i, p in enumerate(me.polygons):
        c, n = p.center, p.normal
        if n.length < 0.5:
            continue
        if BVH.ray_cast(c + n * 0.003, n, 60.0)[0] is not None:
            continue
        back = BVH.ray_cast(c - n * 0.003, -n, 60.0)
        if back[0] is None or back[3] < 0.4:
            out[i] = 1
    return out


def pack(objs, S, margin, ext_area):
    select_only(objs)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=margin / S, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    a3 = sum(area3d(o) for o in objs) - ext_area * (1 - EXTERIOR_SCALE ** 2)    # the density of the inside faces
    return S * math.sqrt(sum(uv_area(o, "LM") for o in objs) / a3)


def choose_page(objs, margin, ext_area):
    sizes = (512, 768, 1024, 1280, 1536, 1792, 2048)
    d = pack(objs, 1024, margin, ext_area)
    want = next((S for S in sizes if d * S / 1024 >= DENSITY), MAX_PAGE)
    for S in sizes[sizes.index(want):]:
        d = pack(objs, S, margin, ext_area)
        if d >= DENSITY * 0.97 or S == MAX_PAGE:
            return S, d
    return MAX_PAGE, d


def texel_samples(objs, img_rgb, S):
    """Area-weighted samples of the baked light (max channel) over each material's inside faces, read at their lightmap UVs."""
    rng = np.random.default_rng(1)
    per = {}
    for o in objs:
        me = o.data
        uv = np.empty(len(me.loops) * 2, np.float32); me.uv_layers["LM"].data.foreach_get("uv", uv); uv = uv.reshape(-1, 3, 2)
        ar = np.empty(len(me.polygons), np.float32); me.polygons.foreach_get("area", ar)
        ext = np.frombuffer(o["exterior"], np.int8).astype(bool) if "exterior" in o else np.zeros(len(ar), bool)
        ar = np.where(ext, 0, ar).astype(np.float64)
        if ar.sum() <= 0:
            continue
        N = max(500, int(ar.sum() * 400))
        t = rng.choice(len(ar), N, p=ar / ar.sum())
        r1, r2 = rng.random(N), rng.random(N); sq = np.sqrt(r1)
        w = np.stack([1 - sq, sq * (1 - r2), sq * r2], 1)
        p = (uv[t] * w[:, :, None]).sum(1)
        x = np.clip((p[:, 0] * S).astype(int), 0, S - 1); y = np.clip((p[:, 1] * S).astype(int), 0, S - 1)
        per.setdefault(me.materials[0].name[3:], []).append(img_rgb[y, x].max(axis=1))
    return {k: np.concatenate(v) for k, v in per.items()}


def setup_cycles(sc, samples, bake):
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = samples
    cy.use_adaptive_sampling = not bake
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces, cy.transmission_bounces, cy.transparent_max_bounces = 8, 4, 3, 8, 16
    cy.use_denoising = not bake
    cy.denoiser = "OPENIMAGEDENOISE"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    gpu = False
    for t in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = t
            prefs.refresh_devices()
        except Exception:
            continue
        if any(d.type != "CPU" for d in prefs.devices):
            for d in prefs.devices:
                d.use = d.type != "CPU"
            gpu = True
            break
    cy.device = "GPU" if gpu else "CPU"
    print("CYCLES device:", cy.device)


def srgb_encode(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def denoise_image(img, S):
    sc = bpy.data.scenes.new("dn")
    ng = bpy.data.node_groups.new("dn", "CompositorNodeTree")
    ni = ng.nodes.new("CompositorNodeImage"); ni.image = img
    dn = ng.nodes.new("CompositorNodeDenoise")
    go = ng.nodes.new("NodeGroupOutput")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    ng.links.new(ni.outputs[0], dn.inputs["Image"]); ng.links.new(dn.outputs[0], go.inputs[0])
    sc.compositing_node_group = ng
    sc.render.resolution_x = sc.render.resolution_y = S
    sc.render.resolution_percentage = 100
    sc.render.engine = "CYCLES"; sc.cycles.samples = 1
    sc.render.use_stamp = False
    sc.render.image_settings.file_format = "OPEN_EXR"; sc.render.image_settings.color_depth = "32"
    cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam
    path = str(SCRATCH / "dn.exr"); sc.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=sc.name)
    r = bpy.data.images.load(path)
    a = np.empty(S * S * 4, np.float32); r.pixels.foreach_get(a)
    bpy.data.images.remove(r); bpy.data.scenes.remove(sc)
    return a.reshape(S, S, 4)


def stage_bake():
    t0 = time.time()
    j, sc, prims, baked, lights = build_scene()
    names = {mt: j["materials"][mt]["name"] for mt in baked}
    page_of = {}
    for mt, nm in names.items():
        page_of[mt] = next((n for n, g in enumerate(GROUPS) if nm in g), len(GROUPS) - 1)
    pages = {}
    for o, mi_, pi, mt, elig in prims:
        if mt in page_of:
            pages.setdefault(page_of[mt], []).append(o)
    report = {"scene": SCENE, "pages": {}, "materials": {}, "prims": []}
    for n in sorted(pages):
        objs = pages[n]
        print(f"lightmap {n}: {len(objs)} objects, {sorted({names[mt] for o, _, _, mt, _ in prims if o in objs})}")
        ext_area = unwrap(objs)
        margin = PAGE_MARGIN.get(n, MARGIN_PX)
        S, dens = choose_page(objs, margin, ext_area)
        for o in objs:
            _, _, _, bad = vertex_uvs(o, "LM")
            if bad:
                raise RuntimeError(f"{o.name}: {len(bad)} vertices with two lightmap UVs")
        report["pages"][n] = {"size": S, "px_per_m": round(dens, 1), "m2": round(sum(area3d(o) for o in objs), 1), "m2_outside": round(ext_area, 1), "margin_px": margin}
        print(f"  page {S} px, {dens:.1f} px/m")
    setup_cycles(sc, SAMPLES, True)
    for n in sorted(pages):
        objs = pages[n]
        S = report["pages"][n]["size"]
        img = bpy.data.images.new(f"LM_{n}", S, S, alpha=False, float_buffer=True)
        img.colorspace_settings.name = "Non-Color"
        for m in {o.data.materials[0] for o in objs}:
            nd = m.node_tree.nodes.new("ShaderNodeTexImage"); nd.name = "BAKE_TARGET"; nd.image = img
            m.node_tree.nodes.active = nd
        for o in objs:
            o.data.uv_layers.active = o.data.uv_layers["LM"]
            if "UVMap" in o.data.uv_layers:
                o.data.uv_layers["UVMap"].active_render = True
        select_only(objs)
        tb = time.time()
        bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, margin=report["pages"][n]["margin_px"], margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
        secs = time.time() - tb
        a = denoise_image(img, S)
        rgb = a[..., :3]; peak = rgb.max(axis=2)
        pc = np.percentile(peak[peak > 1e-5], [50, 90, 99, 99.5, 100]) if (peak > 1e-5).any() else [1.0] * 5
        smp = texel_samples(objs, rgb, S)
        mats_pc = {k: [round(float(x), 4) for x in np.percentile(v, [50, 90, 99, 99.5])] for k, v in smp.items()}
        cool = np.concatenate([v for k, v in smp.items() if k not in HOT] or [peak[peak > 1e-5]])
        scale = float(np.percentile(cool, 99.5))     # white: the 99.5th percentile over the page's inside faces by area, lamp parts aside (what is hotter clips)
        report["pages"][n]["material_texels_p50_p90_p99_p995"] = mats_pc
        out = np.ones((S, S, 4), np.float32); out[..., :3] = srgb_encode(rgb / scale)
        png = bpy.data.images.new(f"LM_{n}_png", S, S, alpha=False)
        png.colorspace_settings.name = "Non-Color"
        png.pixels.foreach_set(out.ravel())
        png.filepath_raw = str(WORK / f"{SCENE}_{n}.png"); png.file_format = "PNG"; png.save()
        report["pages"][n].update(scale=round(scale, 5), seconds=round(secs), texel_p50_p90_p99_p995_max=[round(float(v), 4) for v in pc])
        print(f"  bake {n}: {S}x{S}, {SAMPLES} samples, {secs:.0f} s, texels {report['pages'][n]['texel_p50_p90_p99_p995_max']}")
        for m in {o.data.materials[0] for o in objs}:
            for nd in [nd for nd in m.node_tree.nodes if nd.name == "BAKE_TARGET"]:
                m.node_tree.nodes.remove(nd)
        bpy.data.images.remove(img); bpy.data.images.remove(png)
    # the lightmap UVs, per glTF vertex, in glTF's v-down convention
    blob = bytearray()
    for o, mi_, pi, mt, elig in prims:
        if mt not in page_of:
            continue
        V, _, _, bad = vertex_uvs(o, "LM")
        assert not bad and not np.isnan(V).any(), o.name
        V = V.copy(); V[:, 1] = 1 - V[:, 1]
        report["prims"].append({"mesh": mi_, "prim": pi, "offset": len(blob), "count": len(V)})
        blob += V.astype(np.float32).tobytes()
    (WORK / f"{SCENE}_uv1.bin").write_bytes(bytes(blob))
    for mt, nm in names.items():
        report["materials"][nm] = {"index": mt, "page": page_of[mt]}
    report["samples"] = SAMPLES
    report["lights"] = [{"name": o.name, "type": o.data.type, "W": o.data.energy} for o in lights.objects]
    report["seconds"] = round(time.time() - t0)
    report["device"] = sc.cycles.device
    (WORK / f"{SCENE}_bake.json").write_text(json.dumps(report, indent=1))
    print("BAKE_DONE", json.dumps({k: v for k, v in report.items() if k != "prims"}))


# ------------------------------------------------------------------ review stills
# game coordinates (x, y, z): eye, target, vertical field of view. "plan" hides the ceiling from the camera (its lamps still light the room).
VIEWS = {
    "B1": [["1_arrival", [25.0, -1.4, 21.0], [25.0, -1.4, 0.0], 75, False],           # B1 has no fixed arrival (the page spawns you on an open spot): the east hall's
                                                                                      # south end, eye height, facing north down its 40 m run
           ["2_wide", [30.0, 26.0, 40.0], [0.0, -3.0, 2.5], 50, True],               # the whole floor from above the south-east corner, ceiling hidden
           ["3_detail", [16.1, -1.4, -20.5], [11.12, -2.6, -21.12], 60, False]],     # the flooded north-east room: the chair and the blue ring in the water
    "L2": [["1_arrival", [-0.007, 4.8, 9.9], [-0.007, 4.5, 25.0], 75, False],         # where the stair from L1 lands (the manifest's arrival), eye height, looking south away from the stair door
           ["2_wide", [30.0, 32.0, 40.0], [0.0, 3.2, 2.5], 50, True],                # the whole floor from above the south-east corner, ceiling hidden
           ["3_detail", [8.6, 4.8, -2.04], [19.2, 4.3, -2.04], 60, False]],          # a corridor of the loop, looking east to a door
}


def g2b(p):
    return Vector((p[0], -p[2], p[1]))


def pool_view(prims):
    """Looking along one pool from 1.6 m above the floor, outside its long end."""
    import bmesh as _bm
    o = next(o for o, *_ in prims if o.data.materials and o.data.materials[0].name == "BK_M_Water")
    bm = _bm.new(); bm.from_mesh(o.data); bm.verts.ensure_lookup_table()
    seen, best = set(), None
    for v in bm.verts:
        if v.index in seen:
            continue
        st, pts = [v], []
        seen.add(v.index)
        while st:
            a_ = st.pop(); pts.append(a_.co.copy())
            for e in a_.link_edges:
                w = e.other_vert(a_)
                if w.index not in seen:
                    seen.add(w.index); st.append(w)
        xs = [q.x for q in pts]; ys = [q.y for q in pts]
        area = (max(xs) - min(xs)) * (max(ys) - min(ys))
        if best is None or area > best[0]:
            best = (area, min(xs), max(xs), min(ys), max(ys), pts[0].z)
    bm.free()
    _, x0, x1, y0, y1, z = best
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    floor = -3.0
    if x1 - x0 >= y1 - y0:                           # Blender (x, y) is game (x, -z)
        eye = [x1 + 1.2, floor + 1.6, -cy]; at = [x0, z, -cy]
    else:
        eye = [cx, floor + 1.6, -(y0 - 1.2)]; at = [cx, z, -y1]
    print("pool view", eye, at, "water at", round(z, 3))
    return eye, at


def stage_render():
    j, sc, prims, baked, lights = build_scene()
    setup_cycles(sc, RSAMPLES, False)
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1920, 1080, 100
    sc.render.image_settings.file_format = "JPEG"; sc.render.image_settings.quality = 88
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.exposure = float(arg("--exposure-ev", "0"))
    sc.render.use_stamp = False
    views = json.loads(arg("--views", "null") or "null") or VIEWS[SCENE]
    out = ROOT / "docs" / "renders" / SCENE
    out.mkdir(parents=True, exist_ok=True)
    only = arg("--only")
    for name, eye, at, fov, plan in views:
        if only and name not in only.split(","):
            continue
        if eye is None:
            eye, at = pool_view(prims)
        for o, *_ in prims:                          # the ceiling and what hangs from it: hidden from the camera in the plan view only
            zmin = min((o.matrix_world @ Vector(c)).z for c in o.bound_box)
            o.visible_camera = not (plan and zmin > CEILING_CUT)
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name)); sc.collection.objects.link(cam)
        cam.data.sensor_fit = "VERTICAL"; cam.data.angle = math.radians(fov); cam.data.clip_start = 0.05; cam.data.clip_end = 300
        e, t = g2b(eye), g2b(at)
        cam.location = e
        cam.rotation_euler = (t - e).to_track_quat("-Z", "Y").to_euler()
        sc.camera = cam
        sc.render.filepath = str(out / f"{name}.jpg")
        t0 = time.time()
        bpy.ops.render.render(write_still=True, scene=sc.name)
        print("RENDERED", name, eye, at, f"{time.time() - t0:.0f} s")


# ------------------------------------------------------------------ geometry proof: decode both GLBs and compare every attribute
def stage_compare():
    a_path, b_path = arg("--a"), arg("--b")
    lib = draco_lib()
    ja, Ba = read_glb(ROOT / a_path); jb, Bb = read_glb(ROOT / b_path)
    res = {"meshes": len(ja["meshes"]), "prims": 0, "identical": 0, "diff": [], "uv1_added": 0}
    for mi_, (ma, mb) in enumerate(zip(ja["meshes"], jb["meshes"])):
        for pi, (pa, pb) in enumerate(zip(ma["primitives"], mb["primitives"])):
            res["prims"] += 1
            aa, ia = decode_prim(ja, Ba, pa, lib); ab, ib = decode_prim(jb, Bb, pb, lib)
            ok = np.array_equal(ia, ib)
            for sem in aa:
                ok = ok and sem in ab and aa[sem].dtype == ab[sem].dtype and np.array_equal(aa[sem], ab[sem])
            extra = set(ab) - set(aa)
            if extra - {"TEXCOORD_1"}:
                ok = False
            res["uv1_added"] += "TEXCOORD_1" in extra
            res["identical"] += ok
            if not ok:
                res["diff"].append([mi_, pi])
    res["same_mesh_count"] = len(ja["meshes"]) == len(jb["meshes"]) and all(len(x["primitives"]) == len(y["primitives"]) for x, y in zip(ja["meshes"], jb["meshes"]))
    res["same_nodes"] = ja["nodes"] == jb["nodes"] and ja.get("cameras") == jb.get("cameras") and ja.get("skins") == jb.get("skins") and ja.get("animations") == jb.get("animations")
    (WORK / "compare.json").write_text(json.dumps(res, indent=1))
    # a Draco-free copy of the new GLB, for the brightness check (tools that cannot decode Draco)
    jd = json.loads(json.dumps(jb)); blob = bytearray(Bb)
    for mesh in jd["meshes"]:
        for p in mesh["primitives"]:
            if "KHR_draco_mesh_compression" not in p.get("extensions", {}):
                continue
            attrs, idx = decode_prim(jb, Bb, p, lib)
            for sem, arr in list(attrs.items()) + [("_indices", idx.astype(np.uint32).reshape(-1, 1))]:
                blob += b"\0" * (-len(blob) % 4)
                jd["bufferViews"].append({"buffer": 0, "byteOffset": len(blob), "byteLength": arr.nbytes})
                blob += arr.tobytes()
                src = jb["accessors"][p["indices"] if sem == "_indices" else p["attributes"][sem]]
                acc = {k: v for k, v in src.items() if k not in ("bufferView", "byteOffset")}
                acc["bufferView"] = len(jd["bufferViews"]) - 1
                if sem == "_indices":
                    acc["componentType"] = 5125
                jd["accessors"].append(acc)
                if sem == "_indices":
                    p["indices"] = len(jd["accessors"]) - 1
                else:
                    p["attributes"][sem] = len(jd["accessors"]) - 1
            del p["extensions"]["KHR_draco_mesh_compression"]
    for k in ("extensionsUsed", "extensionsRequired"):
        if k in jd:
            jd[k] = [e for e in jd[k] if e != "KHR_draco_mesh_compression"]
    blob += b"\0" * (-len(blob) % 4)
    jd["buffers"][0]["byteLength"] = len(blob)
    js = json.dumps(jd, separators=(",", ":")).encode(); js += b" " * (-len(js) % 4)
    (WORK / f"{SCENE}_decoded.glb").write_bytes(b"glTF" + struct.pack("<II", 2, 28 + len(js) + len(blob)) + struct.pack("<I", len(js)) + b"JSON" + js
                                                + struct.pack("<I", len(blob)) + b"BIN\0" + bytes(blob))
    print("COMPARE", json.dumps(res))


if __name__ == "__main__":
    {"bake": stage_bake, "render": stage_render, "compare": stage_compare}[STAGE]()
