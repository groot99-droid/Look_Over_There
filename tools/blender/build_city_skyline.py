"""The Intern city's towers made a distant skyline (the owner, 2026-11-27: "The towers should be on the horizon relative to the bus stop").

    blender -b --factory-startup --python tools/blender/build_city_skyline.py -- --source <Exterior.glb> --layout <L4.json> [--work <dir>]
    python tools/webp_glb.py <work>/city/city_skyline_raw.glb world/city_skyline.glb 90
    python tools/split_exterior.py --city <work>/city       (splices the city's meshes without the towers, and the lighter tree, into Exterior.glb)

The sources are world/Exterior.glb and world/L4.json as they were before the towers moved (git show fa23443:world/Exterior.glb, and
fa23443:world/L4.json for the towers' boxes). The 26 towers of the city set
(world/L4.json's Site_ITN_City boxes over 20 m tall, but the walls and the blocks that line the Intern's street, x 88 to 152, z 24 to 112)
stood round the Intern's street: five on the lot's asphalt, one through the store's east end. Each tower's faces (its concrete box and its
windows, found as the islands of City_concrete, City_glassdark, City_glasslit and City_glasslit2 whose middles lie on its footprint) are
moved, as they are, to a skyline on the horizon from the bus station (the set at parking_lot's (-46, 9.6, 46)), the way the bus goes to
Hallam Row: south past the back hedge, bearing 188 degrees, where the Overworld's skies (#117) and the lot's backdrop (#91) paint the town.

Forced perspective: the towers are scaled to 0.35 and stood in two rows on an arc 312 m and 330 m from the bus station, bearings 168 to 208
degrees, their feet 1.5 m under the lawn. At that size and distance they look as they would at about a kilometre, and they stay inside the
store model's sky box (x -360 to 360, z -330 to 390), which L4 and gbi_L4_4 still draw, so the same skyline shows from the lot, through the
store's glass doors and from the Original's lot. The camera's far plane is 1500 m. No colliders: nobody walks there.

Outputs in <work>/city/: city_skyline_raw.glb (the skyline, merged by material, its own file), city_rest.glb (City_concrete and the three
window meshes without the towers, at their own nodes' places), city_tree.glb (the Intern street's tree, its leaves thinned: a fifth of its
leaf cards kept, each scaled up 2.2 times, so its 42,080 leaf triangles become about 8,400 and the eight trees fit the 300k budget),
towers.json (each tower: where it stood, how many faces, where it went).
A game point (x, y, z) is Blender (x, -z, y).
"""
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return args[args.index(name) + 1] if name in args else default


SOURCE = Path(arg("--source", str(ROOT / "work/ctx/Exterior_towers.glb")))
LAYOUT = Path(arg("--layout", str(ROOT / "work/ctx/L4_towers.json")))      # world/L4.json with the towers' boxes (git show fa23443:world/L4.json)
WORK = Path(arg("--work", str(ROOT / "work"))) / "city"
CITY_MESHES = ("City_concrete", "City_glassdark", "City_glasslit", "City_glasslit2")
STREET = (88.0, 152.0, 24.0, 112.0)                      # the blocks that line the Intern's street stay where they are
BUS = (-46.0, 46.0)                                      # the bus station set's place in the lot (the greybox's ATTACH)
BEARING, SPREAD = 188.0, 20.0                            # the town's bearing in the skies, and the skyline's half-width in degrees
ROWS = (312.0, 330.0)
SCALE, SINK, FLOOR = 0.35, 1.5, 9.6
SKY_BOX = (-360.0, 360.0, -330.0, 390.0)                 # Sky_LOT_Exterior (x0, x1, z0, z1)
LEAF_KEEP, LEAF_GROW = 0.2, 2.2


def towers():
    doc = json.loads(LAYOUT.read_text())
    out = []
    for c in doc["colliders"]:
        if c["s"] != "Site_ITN_City" or c["max"][1] < 20.0 or min(c["max"][0] - c["min"][0], c["max"][2] - c["min"][2]) < 2.0:
            continue
        cx, cz = (c["min"][0] + c["max"][0]) / 2, (c["min"][2] + c["max"][2]) / 2
        if STREET[0] <= cx <= STREET[1] and STREET[2] <= cz <= STREET[3]:
            continue
        out.append(c)
    return sorted(out, key=lambda c: -c["max"][1])


def places(n):
    """Where each tower goes, tallest first: the middle of the back row, then alternately either side; the lower ones in the front row."""
    back = (n + 1) // 2
    front = n - back
    out = []
    for row, count in ((ROWS[1], back), (ROWS[0], front)):
        bs = [BEARING + SPREAD * (2 * k / max(count - 1, 1) - 1) for k in range(count)]
        order = sorted(range(count), key=lambda k: abs(bs[k] - BEARING))
        for k in order:
            if row == ROWS[0]:
                b = bs[k] + SPREAD / max(count, 1)              # the front row sits between the back row's towers
            else:
                b = bs[k]
            out.append((BUS[0] + row * math.sin(math.radians(b)), BUS[1] - row * math.cos(math.radians(b)), b))
    return out


def islands(bm):
    seen, out = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, isl = [f], []
        seen.add(f.index)
        while stack:
            g = stack.pop()
            isl.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        out.append(isl)
    return out


def game(v):
    return (v.x, v.z, -v.y)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(SOURCE))
    T = towers()
    print("TOWERS", len(T))
    obs = {o.name: o for o in bpy.data.objects if o.type == "MESH"}
    # which islands of which city mesh belong to which tower
    owned = {k: [] for k in range(len(T))}                   # tower -> [(mesh name, material, world verts list of faces)]
    keep_faces = {}
    for name in CITY_MESHES:
        ob = obs[name]
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.faces.index_update()
        mw = ob.matrix_world
        drop = set()
        for isl in islands(bm):
            pts = [game(mw @ v.co) for f in isl for v in f.verts]
            cx, cz = sum(p[0] for p in pts) / len(pts), sum(p[2] for p in pts) / len(pts)
            hit = [k for k, c in enumerate(T) if c["min"][0] - 1 <= cx <= c["max"][0] + 1 and c["min"][2] - 1 <= cz <= c["max"][2] + 1]
            if hit:
                k = hit[0]
                for f in isl:
                    owned[k].append((name, ob.data.materials[f.material_index].name, [mw @ lp.vert.co for lp in f.loops],
                                     [tuple(lp[bm.loops.layers.uv.active].uv) for lp in f.loops] if bm.loops.layers.uv.active else None))
                    drop.add(f.index)
        keep_faces[name] = len(bm.faces) - len(drop)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index in drop], context="FACES")
        bm.to_mesh(ob.data)
        bm.free()
        print(f"CITY {name}: {len(drop)} faces were towers', {keep_faces[name]} stay")
    # any other city mesh with faces on a tower's footprint would be left behind: there must be none
    for name, ob in obs.items():
        if name in CITY_MESHES or not name.startswith("City_"):
            continue
        mw = ob.matrix_world
        for v in ob.data.vertices:
            p = game(mw @ v.co)
            if any(c["min"][0] < p[0] < c["max"][0] and c["min"][2] < p[2] < c["max"][2] and p[1] > FLOOR + 3 for c in T):
                raise SystemExit(f"{name} has geometry on a tower's footprint")
    # the skyline
    P = places(len(T))
    rep, bms, mats = [], {}, {}
    for k, c in enumerate(T):
        cx, cz = (c["min"][0] + c["max"][0]) / 2, (c["min"][2] + c["max"][2]) / 2
        tx, tz, b = P[k]
        y0 = min(p.z for _n, _m, ps, _u in owned[k] for p in ps) if owned[k] else FLOOR
        for name, mname, ps, uvs in owned[k]:
            bm = bms.setdefault(mname, bmesh.new())
            mats[mname] = bpy.data.materials[mname]
            vs = []
            for p in ps:
                gx, gy, gz = p.x, p.z, -p.y
                nx = tx + (gx - cx) * SCALE
                nz = tz + (gz - cz) * SCALE
                ny = FLOOR - SINK + (gy - y0) * SCALE
                vs.append(bm.verts.new(Vector((nx, -nz, ny))))
            try:
                f = bm.faces.new(vs)
            except ValueError:
                continue
            if uvs:
                ul = bm.loops.layers.uv.get("UVMap") or bm.loops.layers.uv.new("UVMap")
                for lp, uv in zip(f.loops, uvs):
                    lp[ul].uv = uv
        h = (c["max"][1] - FLOOR) * SCALE
        foot = [abs(c["max"][0] - c["min"][0]) * SCALE / 2, abs(c["max"][2] - c["min"][2]) * SCALE / 2]
        assert SKY_BOX[0] < tx - foot[0] < tx + foot[0] < SKY_BOX[1] and SKY_BOX[2] < tz - foot[1] < tz + foot[1] < SKY_BOX[3], (k, tx, tz)
        rep.append({"tower": k + 1, "stood": [round(cx, 1), round(cz, 1)], "height_m": round(c["max"][1] - FLOOR, 1), "faces": len(owned[k]),
                    "now": [round(tx, 1), round(tz, 1)], "bearing_from_bus": round(b, 1),
                    "distance_from_bus_m": round(math.hypot(tx - BUS[0], tz - BUS[1]), 1), "height_now_m": round(h, 1)})
        print("TOWER", rep[-1])
    sky = bpy.data.collections.new("Skyline")
    bpy.context.scene.collection.children.link(sky)
    sky_obs = []
    for mname, bm in bms.items():
        bm.normal_update()
        me = bpy.data.meshes.new(f"Skyline_{mname}")
        bm.to_mesh(me)
        bm.free()
        me.materials.append(mats[mname])
        ob = bpy.data.objects.new(f"Skyline_{mname}", me)
        sky.objects.link(ob)
        sky_obs.append(ob)
    (WORK / "towers.json").write_text(json.dumps(rep, indent=1))

    def export(objs, path):
        bpy.ops.object.select_all(action="DESELECT")
        for o in objs:
            o.hide_set(False)
            o.select_set(True)
        bpy.context.view_layer.objects.active = objs[0]
        bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_extras=False, export_yup=True,
                                  export_apply=False, export_texcoords=True, export_normals=True, export_materials="EXPORT",
                                  export_image_format="AUTO", export_cameras=False, export_lights=False, export_draco_mesh_compression_enable=False,
                                  export_animations=False)
        print("EXPORTED", path.name, path.stat().st_size)
    export(sky_obs, WORK / "city_skyline_raw.glb")
    export([obs[n] for n in CITY_MESHES], WORK / "city_rest.glb")
    # the Intern street's tree: keep a fifth of the leaf cards, each grown about its own middle
    tree = next(o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith("City_tree_small_02"))
    bm = bmesh.new()
    bm.from_mesh(tree.data)
    bm.faces.index_update()
    leaf_i = next(i for i, m in enumerate(tree.data.materials) if "leaves" in m.name)
    rng = np.random.default_rng(5)
    leaves = [isl for isl in islands(bm) if isl[0].material_index == leaf_i]
    before = sum(len(f.verts) - 2 for isl in leaves for f in isl)
    drop, kept = [], 0
    for isl in leaves:
        if rng.random() < LEAF_KEEP:
            vs = {v for f in isl for v in f.verts}
            c = sum((v.co for v in vs), Vector()) / len(vs)
            for v in vs:
                v.co = c + (v.co - c) * LEAF_GROW
            kept += sum(len(f.verts) - 2 for f in isl)
        else:
            drop += isl
    bmesh.ops.delete(bm, geom=drop, context="FACES")
    bm.to_mesh(tree.data)
    bm.free()
    print(f"TREE leaves: {len(leaves)} cards, {before} triangles -> {kept}")
    tree.name = "City_tree_small_02"
    export([tree], WORK / "city_tree.glb")
    print("CITY_SKYLINE ALL DONE")


if __name__ == "__main__":
    main()
