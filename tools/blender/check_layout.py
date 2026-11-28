"""The layout check (docs/BLENDER.md, "Checks before a scene is handed over", 1): does the Blender art stand where the game's colliders are?

Run it on a saved scene, from the repo root:

    blender -b blender/scenes/<scene>.blend --python tools/blender/check_layout.py -- --scene <scene> [--collection Art]

It compares each visible mesh's world box, in GAME coordinates (metres, y up; Blender (x, y, z) is game (x, z, -y)), with the scene's collision
file world/<scene>.json and prints one PASS or FAIL line per rule. The exit code is 1 when anything fails.

Rules (a collider is a box {s, min, max}; "solid art" is every visible mesh whose name does not start with decor_):
  1. COVER   every collider, except the invisible edge walls named Edge_*, is covered by solid art within 5 cm: every sample point of its volume
             (every 10 cm, both faces included) lies within 5 cm of the world box of some solid mesh.
  2. STRAY   no solid art taller than 0.2 m above the floor, reaching below head height, stands where no collider does: its floor plan lies within a
             collider that stands (starts near the floor and rises above 0.2 m), widened by 5 cm. A mesh named decor_* is exempt: it is passable.
  3. CLEAR   the arrival points, door spots and markers (every `arrive` and `at` in the scene's constants, every marker of the collision file) are clear:
             no standing collider and no solid art within the walker's radius (0.28 m).
`python tools/blender/check_layout_test.py` tests the rules without Blender.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOL = 0.05          # metres: how close art must be to a collider
STAND_H = 0.2       # solid art taller than this (above the floor) must stand on a collider
HEAD = 1.8          # art that starts above this height hangs overhead and is not tested for standing
CLEAR_R = 0.28      # the walker's radius (index.html: R)
STEP = 0.1          # floor-plan sampling step for the cover rule (metres)
DECOR = "decor_"
EDGE = "Edge_"


def _samples(a, b, step):
    n = max(1, int(math.ceil((b - a) / step)))
    return [a + (b - a) * i / n for i in range(n + 1)] if b - a > 1e-9 else [a]


def _touch(a, b, tol):
    return all(a["min"][i] <= b["max"][i] + tol and a["max"][i] >= b["min"][i] - tol for i in range(3))


def _in_plan(p, x, z, grow):
    return p["min"][0] - grow <= x <= p["max"][0] + grow and p["min"][2] - grow <= z <= p["max"][2] + grow


def _standing(c):
    return c["max"][1] > STAND_H and c["min"][1] < 0.5


def _stands(p):
    return (p["max"][1] - max(p["min"][1], 0.0)) > STAND_H and p["min"][1] < HEAD


def _walk_up(world, x, z, reach):
    """A spot with a `reach` is an F prompt that works from up to `reach` away (the forest's signpost back to the lot). When a standing collider (the
    thing itself, which the page may draw) covers the spot, the walker stands beside it: the nearest point within reach, in eight directions, that is
    clear of standing colliders by the walker's radius. The CLEAR rule then checks that point against the colliders and the art."""
    stand = [c for c in world.get("colliders", []) if _standing(c)]
    if not any(_in_plan(c, x, z, CLEAR_R) for c in stand):
        return x, z
    d = CLEAR_R
    while d <= reach + 1e-9:
        for k in range(8):
            px, pz = round(x + d * math.cos(k * math.pi / 4), 3), round(z + d * math.sin(k * math.pi / 4), 3)
            if not any(_in_plan(c, px, pz, CLEAR_R) for c in stand):
                return px, pz
        d += 0.05
    return x, z


def points_of(world, constants):
    """(label, x, z) of every arrival point, door spot and marker the scene names."""
    pts = [(f"marker {m['name']}", m["position"][0], m["position"][2]) for m in world.get("markers", []) if "position" in m]
    for i, m in enumerate(m for m in world.get("markers", []) if "position" in m):
        if m.get("kind") == "Entrance" and m.get("width"):
            pts[i] = pts[i] + ("door",)              # a door in a wall's face (the street's doors): see the CLEAR rule

    def walk(o, path):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "arrive" and isinstance(v, list) and len(v) == 3:
                    pts.append((f"{'.'.join(path) or 'constants'}.arrive", v[0], v[2]))
                elif k == "at" and isinstance(v, list) and len(v) == 2 and "half" in o:
                    continue                                  # a placed building's middle (the meadow's shed and house: at, half, height), not a spot to
                                                              # walk to: its collider stands on it (rule 1 covers it) and its door is checked
                elif k == "at" and isinstance(v, list) and len(v) == 2:
                    x, z = _walk_up(world, v[0], v[1], o["reach"]) if "reach" in o else (v[0], v[1])
                    label = f"{'.'.join(path) or 'constants'}.at"
                    pts.append((label if (x, z) == (v[0], v[1]) else f"{label} ({v[0]:.2f}, {v[1]:.2f}), reach {o['reach']}: its walk-up spot", x, z))
                else:
                    walk(v, path + [k])
    walk(constants or {}, [])
    return pts


def check(parts, world, constants=None, tol=TOL, points3=()):
    """parts: [{name, min:[x,y,z], max:[x,y,z]}] in game coordinates. Returns [(ok, rule, text)]."""
    res = []
    colliders = world.get("colliders", [])
    solid = [p for p in parts if not p["name"].startswith(DECOR)]

    # 1. every collider is covered by art
    for c in colliders:
        if c["s"].startswith(EDGE):
            continue
        cand = [p for p in solid if _touch(p, {"min": c["min"], "max": c["max"]}, tol)]
        if not cand:
            res.append((False, "COVER", f"{c['s']}: no art touches it"))
            continue
        step = max(STEP, ((c["max"][0] - c["min"][0]) * (c["max"][1] - c["min"][1]) * (c["max"][2] - c["min"][2]) / 150000.0) ** (1 / 3))
        miss, total = None, 0
        for x in _samples(c["min"][0] + 0.005, c["max"][0] - 0.005, step):
            for y in _samples(c["min"][1] + 0.005, c["max"][1] - 0.005, step):
                for z in _samples(c["min"][2] + 0.005, c["max"][2] - 0.005, step):
                    total += 1
                    if not any(p["min"][0] - tol <= x <= p["max"][0] + tol and p["min"][1] - tol <= y <= p["max"][1] + tol and p["min"][2] - tol <= z <= p["max"][2] + tol for p in cand):
                        miss = miss or (x, y, z)
        if miss:
            res.append((False, "COVER", f"{c['s']}: no art within {tol * 100:.0f} cm of its box at x {miss[0]:.2f}, y {miss[1]:.2f}, z {miss[2]:.2f}"))
        else:
            res.append((True, "COVER", f"{c['s']}: {len(cand)} mesh(es) cover it ({total} sample points, every one within {tol * 100:.0f} cm of art)"))

    # 2. no tall solid art without a collider under it
    stand = [c for c in colliders if _standing(c)]
    bad = []
    for p in solid:
        if not _stands(p):
            continue
        for x in _samples(p["min"][0], p["max"][0], STEP / 2):
            for z in _samples(p["min"][2], p["max"][2], STEP / 2):
                if not any(_in_plan(c, x, z, tol) for c in stand) and not any(_in_plan(c, x, z, tol) and c["min"][1] - tol <= p["min"][1] < c["max"][1] - tol
                                                                             for c in colliders):   # or it sits in a collider at its own height (a flight's upper steps)
                    bad.append(f"{p['name']} at x {x:.2f}, z {z:.2f}")
                    break
            else:
                continue
            break
    n_tall = sum(1 for p in solid if _stands(p))
    if bad:
        res += [(False, "STRAY", f"{b}: solid art over {STAND_H} m tall with no collider (name it {DECOR}* if it is passable)") for b in bad]
    else:
        res.append((True, "STRAY", f"{n_tall} tall solid mesh(es), each over a collider; {len(parts) - len(solid)} {DECOR}* mesh(es) exempt"))

    # 3. the arrival points, door spots and markers are clear
    blockers = [("collider " + c["s"], c) for c in stand] + [("art " + p["name"], p) for p in solid if _stands(p)]
    pts = points_of(world, constants)
    for label, x, z, *door in pts:
        hit = [n for n, b in blockers if _in_plan(b, x, z, CLEAR_R)]
        if hit and door:
            # An Entrance marker with a width stands in the face of the wall it opens (world/street.json: x = +-8, the buildings' street fronts), so its own
            # spot always touches that wall. It is clear when it lies on the face of every collider that blocks it, and the walker's spot in front of it
            # (one radius and 3 cm out, on the open side) is clear of colliders and solid art.
            on_face = all(abs(x - c["min"][0]) < 0.01 or abs(x - c["max"][0]) < 0.01 or abs(z - c["min"][2]) < 0.01 or abs(z - c["max"][2]) < 0.01
                          for n, c in blockers if n.startswith("collider ") and _in_plan(c, x, z, CLEAR_R))
            r = CLEAR_R + 0.03
            for dx, dz in ((r, 0), (-r, 0), (0, r), (0, -r)):
                if on_face and not any(_in_plan(b, x + dx, z + dz, CLEAR_R) for n, b in blockers):
                    res.append((True, "CLEAR", f"{label} ({x:.2f}, {z:.2f}): a door in a wall's face; its walk-up spot ({x + dx:.2f}, {z + dz:.2f}) is clear within {CLEAR_R:.2f} m"))
                    break
            else:
                res.append((False, "CLEAR", f"{label} ({x:.2f}, {z:.2f}): blocked by " + ", ".join(hit) + " (a door, and no clear walk-up spot in front of it)"))
            continue
        res.append((not hit, "CLEAR", f"{label} ({x:.2f}, {z:.2f}): " + ("clear within %.2f m" % CLEAR_R if not hit else "blocked by " + ", ".join(hit))))
    # points with a height (--links: every link's F spot and arrival): blocked only by what stands in the body's height above them
    for label, x, y, z in points3:
        hit = [n for n, b in [("collider " + c["s"], c) for c in colliders] + [("art " + p["name"], p) for p in solid]
               if _in_plan(b, x, z, CLEAR_R) and b["min"][1] < y + 1.6 and b["max"][1] > y + 0.3]
        res.append((not hit, "CLEAR", f"{label} ({x:.2f}, {y:.2f}, {z:.2f}): " + ("clear within %.2f m" % CLEAR_R if not hit else "blocked by " + ", ".join(hit))))
    if not pts and not points3:
        res.append((False, "CLEAR", "no arrival points or markers found to check"))
    return res


def report(res):
    for ok, rule, text in res:
        print(f"{'PASS' if ok else 'FAIL'}  {rule:6s} {text}")
    bad = sum(1 for r in res if not r[0])
    print(f"{'PASS' if not bad else 'FAIL'}: {len(res) - bad} of {len(res)} checks passed" + (f", {bad} failed" if bad else ""))
    return bad


def blender_parts(collection):
    import bpy
    from mathutils import Vector
    out = []
    coll = bpy.data.collections[collection]
    for ob in coll.all_objects:
        if ob.type != "MESH" or ob.hide_render or ob.hide_get():
            continue
        pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
        g = [(p.x, p.z, -p.y) for p in pts]                   # Blender (x, y, z) -> game (x, z, -y): y is up in the game
        out.append({"name": ob.name, "min": [min(q[i] for q in g) for i in range(3)], "max": [max(q[i] for q in g) for i in range(3)]})
    return out


def main(argv):
    def arg(n, d=None):
        return argv[argv.index(n) + 1] if n in argv else d
    scene = arg("--scene", "apartment")
    wp = ROOT / f"world/{scene}.json"
    if not wp.exists() and (ROOT / f"world/rooms/{scene}.json").exists():      # the hotel's room layouts (world/rooms/<layout>.json)
        wp = ROOT / f"world/rooms/{scene}.json"
    world = json.loads(wp.read_text())
    lay = ROOT / f"blender/layout/{scene}.json"
    constants = json.loads(lay.read_text()).get("constants") if lay.exists() else {}
    if arg("--boxes"):
        parts = json.loads(Path(arg("--boxes")).read_text())
    else:
        parts = blender_parts(arg("--collection", "Art"))
    pts3 = []
    if "--links" in argv:                                       # opt-in: the layout file's own links (every F spot and arrival), at their height
        pts3 = [(f"link {l['door']}.{k}", *l[k]) for l in world.get("links", []) for k in ("at", "arrive")]
    print(f"layout check: scene {scene}, {len(parts)} visible meshes, {len(world['colliders'])} colliders")
    return 1 if report(check(parts, world, constants, points3=pts3)) else 0


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    code = main(args)
    sys.stdout.flush()
    sys.exit(code)
