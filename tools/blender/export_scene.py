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
| `SecCam_<nn>` empty                | `cameras`: {id, style, level, position, facing_deg, mount_height_above_floor, pan, tilt, zoom, ...} (L1's shape; see camera()) |
| `Zone_<kind>_<name>` mesh          | `zones`: {kind, name, min, max}                                                                      |
| `Spot_<kind>[_<n>]` empty          | `spots`: {kind, name, position, face, yaw_deg, scale, + the empty's other custom properties}         |

A camera's `facing_deg` is its empty's -Y axis as the page's yaw (index.html aimFeed: it looks along (sin, cos) of it), and its custom
properties may be groups (pan, tilt, zoom) or arrays (view_range_m), written as objects and lists, as in world/L1.json. A mesh named SecCam_
(its rig, which the page moves and smashes) is art, not a camera. A spot's `face` is its empty's -Y axis as game (x, z), as for Arrive_; `yaw_deg` is the same direction as a three.js rotation.y: a model whose
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


CAM_ZOOM = "u=0.5+0.5*sin(2*pi*(cycles*t/loop+phase)); z=smoothstep(0.35,0.65,u); lens=wide+(tele-wide)*z"


def camera(scene, name, position, face, props):
    """A SecCam_<nn> empty as world/L1.json writes a camera: at the empty, facing its -Y axis (facing_deg as a spot's yaw_deg), sweeping as its
    custom properties say (pan_amplitude_deg, pan_cycles, pan_phase, tilt_base_deg, tilt_wobble_deg, tilt_cycles, tilt_phase, zoom_cycles,
    zoom_phase, lens_wide_mm, lens_tele_mm, loop_seconds, mount_height_above_floor, style), with L1's values where it has none."""
    g = lambda k, d: float(props.get(k, d))
    fov = lambda mm: round(2 * math.degrees(math.atan(20.25 / 2 / mm)), 2)
    wide, tele = g("lens_wide_mm", 22.0), g("lens_tele_mm", 70.0)
    return {"id": name, "style": str(props.get("style", "security_camera_01")), "level": scene, "position": position,
            "facing_deg": round(math.degrees(math.atan2(face[0], face[1])), 1) + 0.0, "mount_height_above_floor": g("mount_height_above_floor", 2.8),
            "pan": {"amplitude_deg": g("pan_amplitude_deg", 45.0), "cycles": int(g("pan_cycles", 1)), "phase": g("pan_phase", 0.0)},
            "tilt": {"base_deg": g("tilt_base_deg", -15.0), "wobble_deg": g("tilt_wobble_deg", 4.0), "cycles": int(g("tilt_cycles", 2)), "phase": g("tilt_phase", 0.0)},
            "zoom": {"lens_wide_mm": wide, "lens_tele_mm": tele, "cycles": int(g("zoom_cycles", 2)), "phase": g("zoom_phase", 0.0),
                     "fov_v_wide_deg": fov(wide), "fov_v_tele_deg": fov(tele), "formula": CAM_ZOOM},
            "loop_seconds": g("loop_seconds", 20.0), "aspect": "16:9", "view_range_m": [0.03, 80]}


CAM_DEFAULTS = {"style": "security_camera_01", "mount_height_above_floor": 2.8, "pan": {"amplitude_deg": 45.0, "cycles": 1, "phase": 0.0},
                "tilt": {"base_deg": -18.0, "wobble_deg": 4.0, "cycles": 2, "phase": 0.5},
                "zoom": {"lens_wide_mm": 22, "lens_tele_mm": 70, "cycles": 2, "phase": 0.2}, "loop_seconds": 20, "aspect": "16:9",
                "view_range_m": [0.03, 40]}


def camera_doc(scene, name, position, face, props=None):
    """One SecCam_<nn> as the page reads cameras (world/L1.json's shape: id, level, position, facing_deg, pan, tilt, zoom, loop_seconds).
    face: the way it looks, game (x, z); facing_deg is three's rotation.y of it. Each camera's sweep starts at its own phase. The empty's
    custom properties are added as they are (a nested pan/tilt/zoom is not read from them). Pure Python: build scripts use it for --preview."""
    c = {"id": name, "level": scene, "position": [round(v, 3) + 0.0 for v in position],
         "facing_deg": round(math.degrees(math.atan2(face[0], face[1])), 1) + 0.0}
    c.update(json.loads(json.dumps(CAM_DEFAULTS)))
    digits = "".join(ch for ch in name if ch.isdigit())
    k = int(digits) if digits else 0
    c["pan"]["phase"] = round((k * 0.137) % 1.0, 3)
    c["tilt"]["phase"] = round((k * 0.291) % 1.0, 3)
    for kk, v in (props or {}).items():
        if kk not in c and isinstance(v, (int, float, str)):
            c[kk] = v
    return c


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
        elif n.startswith("SecCam_") and ob.type == "EMPTY":
            if "pan" not in ob.keys():                  # flat custom properties (the grocery's and the mall's cameras): camera() fills in L1's sweep
                out["cameras"].append(camera(scene, n, _g(ob.matrix_world.translation), facing(ob), ob))
                continue
            # grouped properties (pan, tilt, zoom as groups; the secret-operations scenes): written as they are
            f = facing(ob)
            c = {"id": n, "level": scene, "position": _g(ob.matrix_world.translation), "facing_deg": round(math.degrees(math.atan2(f[0], f[1])), 1) + 0.0}
            for k in ob.keys():
                v = ob[k]
                v = v.to_dict() if hasattr(v, "to_dict") else v.to_list() if hasattr(v, "to_list") else v
                if k not in c and isinstance(v, (int, float, str, dict, list)):
                    c[k] = v
            out["cameras"].append(c)
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
    print(f"EXPORT_SCENE {path.name}: {len(d['colliders'])} colliders, {len(d['doors'])} doors, {len(d['cameras'])} cameras, {len(d['markers'])} markers, "
          f"{len(d['links'])} links, {len(d['zones'])} zones, {len(d['spots'])} spots")
    return d


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    sc = a[a.index("--scene") + 1] if "--scene" in a else None
    assert sc, "--scene <id>"
    write(sc, a[a.index("--out") + 1] if "--out" in a else None)
