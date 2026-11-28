"""Places a connector-kit piece (blender/kit/<piece>.blend, made by tools/blender/build_kit.py) into a scene's .blend, from that scene's build script.

    import kit_place
    kit_place.place("elevator", suffix="L4", at=(0.0, 4.0, -14.0), yaw_deg=180.0)            # layout only: COL_, DoorLeaf_, Link_/Arrive_, Spot_, Zone_, Marker_
    kit_place.place("safe_house", suffix="roof", at=(-8.0, 0.0, -5.8), yaw_deg=0.0, art=True)  # also the art meshes, to bake into the scene's own lightmap

`at` is where the piece's origin goes in the scene (game axes: x, y up, z), `yaw_deg` the piece's turn about y as three.js's rotation.y (a kit point
(x, z) lands at (at.x + x cos a + z sin a, at.z - x sin a + z cos a)). The layout objects are APPENDED (real objects, so
tools/blender/export_scene.py writes them into the scene's world/<scene>.json), each name given `_<suffix>`: DoorLeaf_lift becomes DoorLeaf_lift_L4,
Link_lift Link_lift_L4, COL_Car_Floor COL_Car_Floor_L4, Spot_call_1 Spot_call_1_L4. A door's closed_yaw_deg turns with it.
With art=False the scene shows the piece by its GLB, world/kit/<piece>.glb, placed by the page at the same `at` and `yaw_deg` (blender/kit/README.md).
"""
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[2]
PREFIXES = ("COL_", "DoorLeaf_", "Link_", "Arrive_", "Spot_", "Zone_", "Marker_")


def place(piece, suffix, at, yaw_deg=0.0, art=False, collection=None):
    path = ROOT / f"blender/kit/{piece}.blend"
    want = ["Layout"] + (["Art"] if art else [])
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.collections = [c for c in src.collections if c in want]
    m = Matrix.Translation(Vector((at[0], -at[2], at[1]))) @ Matrix.Rotation(math.radians(yaw_deg), 4, "Z")
    target = collection or bpy.context.scene.collection
    made = []
    for coll in dst.collections:
        for ob in list(coll.objects):
            base = ob.name.split(".")[0]
            if coll.name == "Layout" and not base.startswith(PREFIXES):
                continue
            ob.name = f"{base}_{suffix}"
            # an appended object is in no scene yet, so its matrix_world has not been evaluated (it reads as identity): an empty placed by its
            # location would land on `at`. Its own transform is matrix_basis (the kit's layout and art objects have no parent).
            ob.matrix_world = m @ (ob.matrix_basis.copy() if ob.parent is None else ob.matrix_world)
            if base.startswith("DoorLeaf_") and "closed_yaw_deg" in ob.keys():
                y = (float(ob["closed_yaw_deg"]) + yaw_deg + 180.0) % 360.0 - 180.0
                ob["closed_yaw_deg"] = round(y, 1)
            target.objects.link(ob)
            made.append(ob.name)
        bpy.data.collections.remove(coll)
    return made
