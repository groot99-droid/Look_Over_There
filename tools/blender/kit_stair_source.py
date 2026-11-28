"""Reads the store's stair door out of blender/Look_Over_There.blend, read-only, for the connector kit (docs/BLENDER_AREAS.md, "The connector kit").

    blender -b --factory-startup blender/Look_Over_There.blend --python tools/blender/kit_stair_source.py -- [--key L1_L2]

The store's stair doors were made by tools/blender/backrooms_L1_stairdoors.py: for each staircase, the parts on the LOWER level are one mesh per
material slot (`Stair_<key>_lower_<part>`: landing, wallLo, wallHi, ceil, housing, tube) built from axis-aligned boxes, plus the leaf
`DoorLeaf_Stair_<key>_up` (origin at the hinge). This script never saves the file. It writes blender/kit/stair_door_source.json: every box of those
meshes (its world box, Blender axes), each mesh's material and what that material is made of (base colour, image file name, roughness, emission),
and the leaf. tools/blender/build_kit.py builds the kit's stair door from that file, so its boxes are the store's boxes.
"""
import json
import sys
from pathlib import Path

import bpy
import bmesh

ROOT = Path(bpy.data.filepath).resolve().parents[1] if bpy.data.filepath else Path.cwd()
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
KEYS = [args[args.index("--key") + 1]] if "--key" in args else ["B1_L1", "L1_L2", "L2_L3", "L3_L4"]


def mat_info(m):
    if m is None:
        return None
    out = {"name": m.name}
    if m.use_nodes and m.node_tree:
        for nd in m.node_tree.nodes:
            if nd.type == "BSDF_PRINCIPLED":
                bc = nd.inputs["Base Color"]
                out["base_color"] = [round(v, 4) for v in bc.default_value]
                out["roughness"] = round(nd.inputs["Roughness"].default_value, 3)
                out["metallic"] = round(nd.inputs["Metallic"].default_value, 3)
                for k in ("Emission Color", "Emission"):
                    if k in nd.inputs:
                        out["emission"] = [round(v, 4) for v in nd.inputs[k].default_value]
                if "Emission Strength" in nd.inputs:
                    out["emission_strength"] = round(nd.inputs["Emission Strength"].default_value, 3)
            elif nd.type == "TEX_IMAGE" and nd.image:
                out.setdefault("images", []).append({"name": nd.image.name, "file": Path(nd.image.filepath).name, "packed": bool(nd.image.packed_file),
                                                     "size": list(nd.image.size)})
            elif nd.type == "MIX" or nd.type == "MIX_RGB":
                vals = [list(i.default_value) for i in nd.inputs if hasattr(i.default_value, "__len__") and len(i.default_value) == 4]
                if vals:
                    out.setdefault("mix_colors", []).append([[round(v, 4) for v in c] for c in vals])
            elif nd.type == "MAPPING":
                out["mapping_scale"] = [round(v, 4) for v in nd.inputs["Scale"].default_value]
    else:
        out["diffuse"] = [round(v, 4) for v in m.diffuse_color]
    return out


def components(ob):
    """Each connected piece of the mesh as its world box (Blender axes) and its face count."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    mw = ob.matrix_world
    seen, out = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, isl = [v], []
        seen.add(v.index)
        while stack:
            a = stack.pop()
            isl.append(a)
            for e in a.link_edges:
                b = e.other_vert(a)
                if b.index not in seen:
                    seen.add(b.index)
                    stack.append(b)
        pts = [mw @ a.co for a in isl]
        faces = {f.index for a in isl for f in a.link_faces}
        out.append({"min": [round(min(p[i] for p in pts), 4) for i in range(3)], "max": [round(max(p[i] for p in pts), 4) for i in range(3)],
                    "verts": len(isl), "faces": len(faces)})
    bm.free()
    return out


res = {"source": "blender/Look_Over_There.blend (read-only)", "made_by": "tools/blender/backrooms_L1_stairdoors.py", "blender": bpy.app.version_string,
       "stairs": {}}
for key in KEYS:
    parts = {}
    for ob in bpy.data.objects:
        if ob.type == "MESH" and ob.name.startswith(f"Stair_{key}_lower_"):
            parts[ob.name] = {"part": ob.name[len(f"Stair_{key}_lower_"):], "materials": [mat_info(s.material) for s in ob.material_slots],
                              "location": [round(v, 4) for v in ob.matrix_world.translation], "parent": ob.parent.name if ob.parent else None,
                              "polys": len(ob.data.polygons), "uv_layers": [u.name for u in ob.data.uv_layers], "boxes": components(ob)}
    leaf = bpy.data.objects.get(f"DoorLeaf_Stair_{key}_up")
    col = bpy.data.objects.get(f"COL_StairDoor_{key}_lower")
    res["stairs"][key] = {
        "parts": parts,
        "leaf": None if leaf is None else {"name": leaf.name, "hinge": [round(v, 4) for v in leaf.matrix_world.translation],
                                           "rotation_z_deg": round(leaf.matrix_world.to_euler().z * 57.29578, 2),
                                           "boxes": components(leaf) if leaf.type == "MESH" else [],
                                           "materials": [mat_info(s.material) for s in leaf.material_slots],
                                           "props": {k: (leaf[k] if isinstance(leaf[k], (int, float, str)) else str(leaf[k])) for k in leaf.keys()}},
        "collider": None if col is None else {"name": col.name, "boxes": components(col)},
    }
    print("STAIR", key, {n: (len(p["boxes"]), p["materials"][0]["name"] if p["materials"] and p["materials"][0] else None) for n, p in parts.items()},
          "leaf", leaf is not None, "col", col is not None)
for sc in bpy.data.scenes:
    if "bk_doors" in sc.keys():
        res["bk_doors_stair"] = [d for d in json.loads(sc["bk_doors"]) if d["name"].startswith("DoorLeaf_Stair")]
        break
out = Path.cwd() / "blender/kit/stair_door_source.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(res, indent=1))
print("WROTE", out, out.stat().st_size)
