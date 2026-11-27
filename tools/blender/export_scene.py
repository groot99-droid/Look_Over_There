"""Writes a Blender-first scene's layout, world/<scene>.json, from the names in its .blend (docs/BLENDER_AREAS.md, "The exporter and its names").

    blender -b blender/scenes/<scene>.blend --python tools/blender/export_scene.py -- --scene <scene> [--out world/<scene>.json]

The format is the page's (world/L1.json): `scene`, `colliders`, `doors`, `cameras`, `markers`, plus `links`, `zones` and `spots` for the coordinator
(the page ignores keys it does not know). A game point (x, y, z) is Blender (x, -z, y).

| Blender object                     | Written as                                                                                          |
|------------------------------------|-----------------------------------------------------------------------------------------------------|
| `COL_<name>` mesh (a box)          | `colliders`: {s: <name>, min, max} (its world box, in game axes)                                     |
| `DoorLeaf_<name>` (origin = hinge) | `doors`: {name, level, hinge, width, height, closed_yaw_deg, swing_deg, state, + its other custom properties} |
| `Marker_<name>` empty, `kind`      | `markers`: {name, room, level, kind, position}                                                       |
| `Link_<id>` + `Arrive_<id>`        | `links`: {door: <id>, at, arrive, face} (face: the Arrive empty's -Y axis, as game (x, z))          |
| `SecCam_<nn>`                      | `cameras` (none of the scenes built so far has one)                                                  |
| `Zone_<kind>_<name>` mesh          | `zones`: {kind, name, min, max}                                                                      |
| `Spot_<kind>[_<n>]` empty          | `spots`: {kind, name, position, face, yaw_deg, scale, + the empty's other custom properties}         |

A spot's `face` is its empty's -Y axis as game (x, z), as for Arrive_; `yaw_deg` is the same direction as a three.js rotation.y: a model whose
front is +z, given `rotation.y = yaw_deg * PI / 180`, faces `face`. `scale` is the empty's custom property `scale` (1 when it has none).

Everything is read from the whole file (any collection); numbers are rounded to the millimetre. It fails on a Link_ without its Arrive_.
Can also be imported from a build script: `export_scene.collect(scene)` returns the dict, `export_scene.write(scene, path)` writes it.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _g(v):
    """Blender (x, y, z) -> game (x, y, z) = (x, z, -y), rounded to the mm."""
    return [round(v[0], 3), round(v[2], 3), round(-v[1], 3) + 0.0]


def _box(ob):
    from mathutils import Vector
    pts = [_g(ob.matrix_world @ Vector(c)) for c in ob.bound_box]
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]


def collect(scene):
    import bpy
    from mathutils import Vector
    def facing(ob):
        f = _g(ob.matrix_world.to_3x3() @ Vector((0, -1, 0)))
        ln = math.hypot(f[0], f[2]) or 1.0
        return [round(f[0] / ln, 3) + 0.0, round(f[2] / ln, 3) + 0.0]

    out = {"scene": scene, "colliders": [], "doors": [], "cameras": [], "markers": [], "links": [], "zones": [], "spots": []}
    obs = sorted(bpy.data.objects, key=lambda o: o.name)
    arrive = {o.name[len("Arrive_"):]: o for o in obs if o.name.startswith("Arrive_")}
    for ob in obs:
        n = ob.name
        if n[-4:-3] == "." and n[-3:].isdigit():          # a copy Blender renamed (name.001): never part of the layout
            continue
        if n.startswith("COL_") and ob.type == "MESH":
            mn, mx = _box(ob)
            out["colliders"].append({"s": n[4:], "min": mn, "max": mx})
        elif n.startswith("DoorLeaf_"):                   # the leaf itself (a mesh the page swings, origin at the hinge) or an empty
            d = {"name": n, "level": scene, "hinge": _g(ob.matrix_world.translation), "width": float(ob.get("width", 0.94)),
                 "height": float(ob.get("height", 2.16)), "closed_yaw_deg": float(ob.get("closed_yaw_deg", 0.0)),
                 "swing_deg": float(ob.get("swing_deg", 0.0)), "state": str(ob.get("state", "closed"))}
            for k in ob.keys():                           # the leaf's other custom properties, as for spots (the hotel's room doors: room_layout, room, ...)
                if k not in d and isinstance(ob[k], (int, float, str)):
                    d[k] = ob[k]
            out["doors"].append(d)
        elif n.startswith("Marker_"):
            out["markers"].append({"name": n[7:], "room": str(ob.get("room", scene)), "level": scene, "kind": str(ob.get("kind", "Spawn")),
                                   "position": _g(ob.matrix_world.translation)})
        elif n.startswith("Link_"):
            key = n[5:]
            assert key in arrive, f"{n} has no Arrive_{key}"
            a = arrive[key]
            out["links"].append({"door": key, "at": _g(ob.matrix_world.translation), "arrive": _g(a.matrix_world.translation), "face": facing(a)})
        elif n.startswith("Zone_") and ob.type == "MESH":
            kind = n.split("_")[1]
            mn, mx = _box(ob)
            out["zones"].append({"kind": kind, "name": n, "min": mn, "max": mx})
        elif n.startswith("Spot_") and ob.type == "EMPTY":
            f = facing(ob)
            sp = {"kind": n.split("_")[1], "name": n, "position": _g(ob.matrix_world.translation), "face": f,
                  "yaw_deg": round(math.degrees(math.atan2(f[0], f[1])), 1) + 0.0, "scale": float(ob.get("scale", 1.0))}
            for k in ob.keys():
                if k not in sp and isinstance(ob[k], (int, float, str)):
                    sp[k] = ob[k]
            out["spots"].append(sp)
    return out


def write(scene, path=None):
    path = Path(path) if path else ROOT / f"world/{scene}.json"
    d = collect(scene)
    path.write_text(json.dumps(d, indent=1) + "\n")
    print(f"EXPORT_SCENE {path.name}: {len(d['colliders'])} colliders, {len(d['doors'])} doors, {len(d['markers'])} markers, {len(d['links'])} links, "
          f"{len(d['zones'])} zones, {len(d['spots'])} spots")
    return d


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    sc = a[a.index("--scene") + 1] if "--scene" in a else None
    assert sc, "--scene <id>"
    write(sc, a[a.index("--out") + 1] if "--out" in a else None)
