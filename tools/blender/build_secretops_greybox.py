"""The Secret Operations greybox (docs/BLENDER_AREAS.md, section 8, "Secret Operations (Project Never Land)"): the area's unique scenes as plain
boxes, to scale, with the names the exporter reads (COL_, DoorLeaf_, Link_/Arrive_, SecCam_, Zone_, Spot_, decor_) and the boss fight's parts as
their own objects (Rack_<n>, FloorPanel_<x>_<z>, SecCam_<nn>, CeilingPanel_<x>_<z>), so the owner can review the whole base at once. The reskinned
Going back in chambers that Secret Operations also uses are not here (they are the gbi greybox's). It follows the method of
tools/blender/build_overworld_greybox.py (one model in plain Python, a Blender run that exports it, a --preview and a --check without Blender).

    blender -b --factory-startup --python tools/blender/build_secretops_greybox.py -- [--scenes all|id,id,...] [--out <dir>] [--no-render]
    python tools/blender/build_secretops_greybox.py --preview <dir>        writes <dir>/world/<scene>.json from the model alone, no Blender
    python tools/blender/build_secretops_greybox.py --check <dir> [--against <dir2>]
                                                                          the gates on the layout files in <dir>/world (links both ways, the
                                                                          graph, overlaps, clearances, routes, required objects, the floor-panel
                                                                          grid, cameras and breakers, shooter readability); --against also
                                                                          compares them with another run's files (the Blender export with the
                                                                          preview), to the millimetre

For each scene the Blender run builds the boxes into an empty file, writes <out>/world/<scene>.json through tools/blender/export_scene.py,
the greybox art to <out>/glb/<scene>.glb, a top-down orthographic plan (<out>/renders/<scene>_plan_L0.png, ceilings and everything 2.4 m up
hidden) and one eye-height still (1.55 m, <out>/renders/<scene>_still.png). The labels, scale bar and sheets are drawn afterwards by
tools/blender/secretops_greybox_sheets.py from this same model.

Coordinates are GAME coordinates (metres, y up, north = -z); Blender (x, y, z) is game (x, -z, y). Every scene has its own frame with its floor
at y = 0. Rooms are cut from one occupancy grid (10 cells a metre): each scene is a list of spaces (rooms, corridors, bays) and openings, and
carve() makes the floor slabs, the 0.2 m walls round the spaces, the ceilings and the lintels, sills and glass of the openings as as few boxes
as the shape allows, so no two boxes overlap. Two spaces that touch are one room; a 0.2 m gap between them is a wall.

Every box is the same unit cube per material, scaled (colliders and art share it). Each COL_<name> box has its art twin <name>; decor_ boxes
(the pink stripe, signs, scanner arches) and the camera rigs (SecCam_<nn>_rig, which the page moves and smashes) have no collider. Nothing
here touches the manifest, index.html or shared/.
"""
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EYE = 1.55
T = 0.2                     # wall thickness
SLAB = 0.3                  # floor slab
Q = 10                      # grid cells a metre
DOOR_W, DOOR_H = 0.94, 2.16
MAX_RISE = 0.27
MIN_CORRIDOR = 1.6
MIN_OPENING = 1.0           # a doorway's clear width (a 0.94 m leaf in it)
WALKER_R = 0.28
H_ROOM = (2.8, 3.2)         # docs/BLENDER_AREAS.md, Scale: ceilings 2.8 to 3.2 m (spaces tagged "tall" are the stated exceptions)
FORE_MIN, BACK_MIN = 12.0, 6.0   # an agent's spawn is this far from where you arrive going deeper (fore), and from where you come back (back)
CAM_Y = 0.35                # a camera hangs this far under its ceiling
PANEL = 2.0                 # the arena's floor panels

MATS = {                    # flat greybox colours (linear RGB); no textures. Clinical, cold and institutional (docs/WORLD.md: surveillance, control)
    "concrete": (0.42, 0.42, 0.42), "service": (0.30, 0.34, 0.38), "steel": (0.50, 0.52, 0.55), "tile": (0.78, 0.82, 0.84),
    "lab": (0.86, 0.86, 0.84), "lab_floor": (0.62, 0.64, 0.66), "corridor": (0.62, 0.62, 0.60), "corridor_floor": (0.36, 0.37, 0.38),
    "checkpoint": (0.22, 0.26, 0.32), "checkpoint_floor": (0.30, 0.30, 0.32), "ceiling": (0.70, 0.70, 0.70), "door": (0.55, 0.36, 0.18),
    "keycard_door": (0.62, 0.12, 0.10), "glass": (0.70, 0.85, 0.90), "crate": (0.55, 0.42, 0.24), "barrier": (0.85, 0.70, 0.10),
    "furniture": (0.45, 0.40, 0.34), "bench": (0.75, 0.75, 0.72), "locker": (0.35, 0.45, 0.40), "machine": (0.28, 0.30, 0.30),
    "breaker": (0.85, 0.42, 0.10), "monitor": (0.08, 0.10, 0.14), "chair": (0.15, 0.15, 0.17), "cell": (0.48, 0.47, 0.44),
    "server_green": (0.10, 0.42, 0.22), "server_floor": (0.08, 0.20, 0.13), "panel_a": (0.16, 0.30, 0.20), "panel_b": (0.12, 0.24, 0.16),
    "rack": (0.05, 0.07, 0.06), "pink": (0.97, 0.36, 0.62), "pit": (0.03, 0.03, 0.04), "water": (0.25, 0.55, 0.65), "sign": (0.85, 0.80, 0.55),
    "cam": (0.92, 0.92, 0.92), "hazard": (0.90, 0.75, 0.05), "lamp": (0.95, 0.95, 0.85),
}


# ================================================================ the model (pure Python; no bpy)
class Scene:
    def __init__(s, sid, title, size, mood=""):
        s.id, s.title, s.size, s.mood = sid, title, size, mood
        s.boxes, s.empties, s.doors, s.labels, s.lights, s.corridors, s.flights, s.cams = [], [], [], [], [], [], [], []
        s.spaces, s.openings, s.pits = [], [], []
        s.links = {}            # door id -> (where it goes, fore?, keycard tier or 0)
        s.still = None          # (pos, face, pitch_deg)
        s.levels = [0.0]
        s.patrols = {}          # route -> [spot names, in order]
        s._names = set()
        s._n = {}

    def uniq(s, n):
        base, k = n, 1
        while n in s._names:
            k += 1
            n = f"{base}_{k}"
        s._names.add(n)
        return n

    def num(s, prefix):
        s._n[prefix] = s._n.get(prefix, 0) + 1
        return s._n[prefix]

    def solid(s, name, mn, mx, mat="concrete", tags=(), art=True, props=None):
        """A collider with its art twin (art=False: a collider only). props go on the art object (the GLB's extras)."""
        if any(mn[i] >= mx[i] - 1e-6 for i in range(3)):
            return None
        n = s.uniq(name)
        s.boxes.append({"name": n, "min": [float(v) for v in mn], "max": [float(v) for v in mx], "mat": mat, "col": True, "art": art,
                        "tags": set(tags), "props": dict(props or {})})
        return n

    def decor(s, name, mn, mx, mat="sign", tags=()):
        n = s.uniq("decor_" + name)
        s.boxes.append({"name": n, "min": [float(v) for v in mn], "max": [float(v) for v in mx], "mat": mat, "col": False, "art": True,
                        "tags": set(tags), "props": {}})

    def zone(s, kind, name, mn, mx):
        n = s.uniq(f"Zone_{kind}_{name}")
        s.boxes.append({"name": n, "min": list(mn), "max": list(mx), "mat": "hazard", "col": False, "art": False, "zone": kind, "tags": set(),
                        "props": {}})

    def empty(s, name, pos, face=None, props=None):
        s.empties.append({"name": s.uniq(name), "pos": [float(v) for v in pos], "face": face, "props": dict(props or {})})

    def spot(s, kind, n, pos, face=(0, 1), props=None):
        s.empty(f"Spot_{kind}_{n}", pos, face=face, props=props)
        return f"Spot_{kind}_{n}"

    def door(s, name, hinge, run, into, width=DOOR_W, height=DOOR_H, state="closed", props=None, swing=None):
        """A leaf with its origin at the hinge. `run`: the game direction (x, z) from the hinge along the closed leaf; `into`: the side it
        opens toward. closed_yaw_deg is three.js's rotation.y of the leaf (its local +x runs from the hinge along it); +swing_deg opens it
        toward `into` (the galleries' convention)."""
        th = math.atan2(-run[1], run[0])
        op = math.atan2(-into[1], into[0])
        mag = 95.0 if swing is None else float(swing)
        sw = mag if math.sin(op - th) > 0 else -mag
        p = {"width": round(width, 3), "height": round(height, 3), "closed_yaw_deg": round(math.degrees(th), 1), "swing_deg": sw, "state": state}
        p.update(props or {})
        s.doors.append({"name": s.uniq("DoorLeaf_" + name), "hinge": [float(v) for v in hinge], "yaw": th, "props": p})

    def label(s, text, x, z, kind="room"):
        s.labels.append({"text": text, "x": x, "z": z, "kind": kind})

    def light(s, x, y, z, power=250.0):
        s.lights.append((x, y, z, power))


# ---------------------------------------------------------------- spaces, openings and the carve
def sp(name, x0, x1, z0, z1, h=3.0, kind="room", f="concrete", w="concrete", c="ceiling", floor=True, ceiling=True, tags=(), label=None):
    return {"name": name, "x0": x0, "x1": x1, "z0": z0, "z1": z1, "h": h, "kind": kind, "fmat": f, "wmat": w, "cmat": c, "floor": floor,
            "ceiling": ceiling, "tags": set(tags), "label": name.replace("_", " ") if label is None else label}


def op(x0, x1, z0, z1, top=2.4, sill=0.0, leaf=None, state="closed", props=None):
    """An opening through the 0.2 m gap between two spaces: a doorway (sill 0), or a window (a sill, glass up to `top`). leaf: (name, into)
    hangs a door leaf in it, opening toward `into` (dx, dz)."""
    return {"x0": x0, "x1": x1, "z0": z0, "z1": z1, "top": top, "sill": sill, "leaf": leaf, "state": state, "props": dict(props or {})}


def qi(v):
    return int(round(v * Q))


def cells_of(r):
    return [(i, j) for i in range(qi(r["x0"]), qi(r["x1"])) for j in range(qi(r["z0"]), qi(r["z1"]))]


def grid_rects(cells):
    """cells: {(i, j): key}. As few axis-aligned rectangles of one key each as a row-run merge gives: [(i0, i1, j0, j1, key)], ends exclusive."""
    rows = {}
    for (i, j), key in cells.items():
        rows.setdefault(j, []).append((i, key))
    if not rows:
        return []
    out, active = [], {}
    for j in range(min(rows), max(rows) + 2):
        runs = []
        row = sorted(rows.get(j, []))
        for i, key in row:
            if runs and runs[-1][1] == i and runs[-1][2] == key:
                runs[-1][1] = i + 1
            else:
                runs.append([i, i + 1, key])
        now = {(a, b, k) for a, b, k in runs}
        for r in list(active):
            if r not in now:
                out.append((r[0], r[1], active.pop(r), j, r[2]))
        for r in now:
            if r not in active:
                active[r] = j
    return out


def interior(S):
    """{cell: index of the space that owns it} (the tallest space wins where two overlap), and {cell: opening} for the openings."""
    inside = {}
    for k, s in enumerate(S.spaces):
        for c in cells_of(s):
            if c not in inside or S.spaces[inside[c]]["h"] < s["h"]:
                inside[c] = k
    opn = {}
    for o in S.openings:
        for c in cells_of(o):
            assert c not in inside, (S.id, "opening over a space", o)
            opn[c] = o
    return inside, opn


def carve(S):
    """The floor slabs, walls, ceilings, lintels, sills and glass of S.spaces and S.openings, as boxes with no overlaps."""
    inside, opn = interior(S)
    tq = qi(T)
    near = {}                                                   # wall cell -> (height, wall mat, floor mat)
    for (i, j), k in inside.items():
        s = S.spaces[k]
        for di in range(-tq, tq + 1):
            for dj in range(-tq, tq + 1):
                n = (i + di, j + dj)
                if n in inside or n in opn:
                    continue
                if n not in near or near[n][0] < s["h"]:
                    near[n] = (s["h"], s["wmat"], s["fmat"])
    pit = set()
    for r in S.pits:
        pit.update(cells_of({"x0": r[0], "x1": r[1], "z0": r[2], "z1": r[3]}))
    oinfo = {}
    for o in S.openings:                                        # an opening's height and floor come from the spaces either side
        hs = [S.spaces[inside[(i + di, j + dj)]] for (i, j) in cells_of(o) for di in (-tq - 1, 0, tq + 1) for dj in (-tq - 1, 0, tq + 1)
              if (i + di, j + dj) in inside]
        assert hs, (S.id, "opening touches no space", o)
        top = max(hs, key=lambda s: s["h"])
        oinfo[id(o)] = (top["h"], top["wmat"], top["fmat"])
    fl = {}
    for c, k in inside.items():
        if S.spaces[k]["floor"] and c not in pit:
            fl[c] = S.spaces[k]["fmat"]
    for c, v in near.items():
        if c not in pit:
            fl[c] = v[2]
    for c, o in opn.items():
        if c not in pit:
            fl[c] = oinfo[id(o)][2]
    for n, (i0, i1, j0, j1, m) in enumerate(sorted(grid_rects(fl), key=lambda r: (r[2], r[0]))):
        S.solid(f"Floor_{n + 1:03d}", (i0 / Q, -SLAB, j0 / Q), (i1 / Q, 0.0, j1 / Q), m, ("floor",))
    for n, (i0, i1, j0, j1, (h, m)) in enumerate(sorted(grid_rects({c: (v[0], v[1]) for c, v in near.items()}), key=lambda r: (r[2], r[0]))):
        S.solid(f"Wall_{n + 1:03d}", (i0 / Q, 0.0, j0 / Q), (i1 / Q, h, j1 / Q), m, ("wall",))
    ce = {c: (S.spaces[k]["h"], S.spaces[k]["cmat"]) for c, k in inside.items() if S.spaces[k]["ceiling"]}
    for n, (i0, i1, j0, j1, (h, m)) in enumerate(sorted(grid_rects(ce), key=lambda r: (r[2], r[0]))):
        S.solid(f"Ceiling_{n + 1:03d}", (i0 / Q, h, j0 / Q), (i1 / Q, h + 0.2, j1 / Q), m, ("ceiling",))
    for o in S.openings:
        h, wm, _ = oinfo[id(o)]
        x0, x1, z0, z1 = o["x0"], o["x1"], o["z0"], o["z1"]
        if o["top"] < h - 1e-6:
            S.solid(f"Lintel_{S.num('lintel'):02d}", (x0, o["top"], z0), (x1, h, z1), wm, ("lintel",))
        if o["sill"] > 0:
            S.solid(f"Sill_{S.num('sill'):02d}", (x0, 0.0, z0), (x1, o["sill"], z1), wm, ("wall",))
            S.solid(f"Glass_{S.num('glass'):02d}", (x0, o["sill"], z0), (x1, o["top"], z1), "glass", ("glass",))
        if o["leaf"]:
            name, into = o["leaf"]
            p = dict(o["props"])
            if abs(z1 - z0) <= 0.25 + 1e-6:                     # the wall runs along x
                cx = (x0 + x1) / 2
                if into[1] > 0:
                    S.door(name, (cx - DOOR_W / 2, 0.0, z1), (1, 0), (0, 1), state=o["state"], props=p)
                else:
                    S.door(name, (cx + DOOR_W / 2, 0.0, z0), (-1, 0), (0, -1), state=o["state"], props=p)
            else:
                cz = (z0 + z1) / 2
                if into[0] > 0:
                    S.door(name, (x1, 0.0, cz + DOOR_W / 2), (0, -1), (1, 0), state=o["state"], props=p)
                else:
                    S.door(name, (x0, 0.0, cz - DOOR_W / 2), (0, 1), (-1, 0), state=o["state"], props=p)
    for s in S.spaces:
        if s["kind"] == "corridor":
            S.corridors.append({"name": s["name"], "min": [s["x0"], 0.0, s["z0"]], "max": [s["x1"], 0.0, s["z1"]]})
        if s["label"]:
            S.label(s["label"], (s["x0"] + s["x1"]) / 2, (s["z0"] + s["z1"]) / 2)
    return inside, opn


# ---------------------------------------------------------------- helpers for what stands in the spaces
INWARD = {"N": (0, 1), "S": (0, -1), "W": (1, 0), "E": (-1, 0)}


def edge_link(S, did, side, a, c0, to, fore, keycard=0, props=None, leaf=True, reader_off=1.2):
    """A door to another scene in the wall on `side` (N, S, W, E) of a space, centred on `a` along the wall, the wall's inner face at c0. The
    leaf stays shut (pressing F at Link_<did> loads the other scene; you come in at Arrive_<did>, 1.4 m inside, facing into the room).
    keycard: the tier its reader asks for (a Spot_reader beside it)."""
    fx, fz = INWARD[side]
    h = DOOR_W / 2
    p = {"goes_to": to, "link_door": did}
    if keycard:
        p["keycard_tier"] = keycard
    p.update(props or {})
    if leaf:
        if side == "N":
            S.door(did, (a - h, 0.0, c0), (1, 0), (0, 1), props=p)
        elif side == "S":
            S.door(did, (a + h, 0.0, c0), (-1, 0), (0, -1), props=p)
        elif side == "W":
            S.door(did, (c0, 0.0, a + h), (0, -1), (1, 0), props=p)
        else:
            S.door(did, (c0, 0.0, a - h), (0, 1), (-1, 0), props=p)
    pt = (lambda d: (a, 0.0, c0 + fz * d)) if side in "NS" else (lambda d: (c0 + fx * d, 0.0, a))
    S.empty(f"Link_{did}", pt(0.7))
    S.empty(f"Arrive_{did}", pt(1.4), face=(fx, fz))
    S.links[did] = (to, fore, keycard)
    if keycard:
        if side in "NS":
            S.spot("reader", did, (a + reader_off, 0.0, c0 + fz * 0.45), face=(-fx, -fz), props={"keycard_tier": keycard, "door": did})
        else:
            S.spot("reader", did, (c0 + fx * 0.45, 0.0, a + reader_off), face=(-fx, -fz), props={"keycard_tier": keycard, "door": did})


def block(S, kind, x0, x1, z0, z1, h, mat=None, cover=None, props=None):
    """Something solid on the floor. kind names it (Crate, Barrier, Pillar, Bench, ...); cover: 'half' (under 1.3 m: crouch behind it) or
    'full' (stand behind it) for the shooter's gates; None for furniture that is not cover."""
    mats = {"Crate": "crate", "Barrier": "barrier", "Pillar": "concrete", "Bench": "bench", "Shelf": "furniture", "Desk": "furniture",
            "Lockers": "locker", "Hood": "lab", "Tank": "glass", "Trafo": "machine", "Breaker": "breaker", "Console": "monitor",
            "Monitors": "monitor", "Cubicle": "glass", "Cabinet": "rack", "Forklift": "machine", "Pallet": "crate", "Planter": "concrete",
            "Bunk": "cell", "Chair": "chair"}
    tags = {"cover", "cover_" + cover} if cover else set()
    return S.solid(f"{kind}_{S.num(kind):02d}", (x0, 0.0, z0), (x1, h, z1), mat or mats.get(kind, "furniture"), tags, props=props)


def cam(S, x, z, face, circuit, h=3.0, y=None):
    """A security camera, SecCam_<nn>: an empty at the lens (its -Y the way it looks, exported to `cameras` in world/L1.json's format) and its
    rig, SecCam_<nn>_rig, a separate art object the page sweeps and smashes. On the wall at (x, z), hung CAM_Y under the ceiling h."""
    n = len(S.cams) + 1
    nm = f"SecCam_{n:02d}"
    y = h - CAM_Y if y is None else y
    ln = math.hypot(*face)
    f = (face[0] / ln, face[1] / ln)
    ph = ((n * 0.37) % 1.0, (n * 0.61) % 1.0, (n * 0.23) % 1.0)
    props = {"rig": nm + "_rig", "style": "security_camera_01", "mount_height_above_floor": round(y, 2), "circuit": circuit,
             "pan": {"amplitude_deg": 40.0, "cycles": 1, "phase": round(ph[0], 3)},
             "tilt": {"base_deg": -18.0, "wobble_deg": 4.0, "cycles": 2, "phase": round(ph[1], 3)},
             "zoom": {"lens_wide_mm": 22.0, "lens_tele_mm": 50.0, "cycles": 1, "phase": round(ph[2], 3),
                      "formula": "u=0.5+0.5*sin(2*pi*(cycles*t/loop+phase)); z=smoothstep(0.35,0.65,u); lens=wide+(tele-wide)*z"},
             "loop_seconds": 20.0, "aspect": "16:9", "view_range_m": [0.03, 40.0]}
    S.cams.append({"name": nm, "pos": [float(x), float(y), float(z)], "face": f, "props": props})
    S.decor(nm + "_rig", (x - 0.15, y - 0.12, z - 0.15), (x + 0.15, y + 0.12, z + 0.15), "cam", ("camera",))
    S.boxes[-1]["name"] = nm + "_rig"                         # the rig keeps the page's name (no decor_ prefix): the page moves it
    S._names.add(nm + "_rig")


def agent(S, n, x, z, face=(0, 1), role="spawn"):
    return S.spot("agent", n, (x, 0.0, z), face=face, props={"role": role})


def patrol(S, route, pts):
    """An agent's beat: Spot_patrol_<route>_<k>, walked in order and looped."""
    S.patrols[route] = []
    for k, (x, z) in enumerate(pts, 1):
        S.patrols[route].append(S.spot("patrol", f"{route}_{k}", (x, 0.0, z), props={"route": route, "order": k, "loop": 1}))


def restricted(S, h=3.0):
    xs = [v for s in S.spaces for v in (s["x0"], s["x1"])]
    zs = [v for s in S.spaces for v in (s["z0"], s["z1"])]
    S.zone("restricted", S.id, (min(xs), 0.0, min(zs)), (max(xs), h, max(zs)))


def lights_for(S):
    for s in S.spaces:
        w, d = s["x1"] - s["x0"], s["z1"] - s["z0"]
        nx, nz = max(1, int(w // 8)), max(1, int(d // 8))
        for a in range(nx):
            for b in range(nz):
                S.light(s["x0"] + w * (a + 0.5) / nx, s["h"] - 0.4, s["z0"] + d * (b + 0.5) / nz, 60.0 + 4.0 * min(w, d))


def clear_ahead(walk, pos, face, limit=30.0):
    t = 0.0
    while cell_of((pos[0] + face[0] * t, 0.0, pos[2] + face[1] * t)) in walk and t < limit:
        t += 0.1
    return t


def finish(S, still_door=None, pitch=-4.0):
    """The lights; every arrival that would face a wall (under 2 m clear ahead, as coming in by a side door of a corridor) turned to look
    the longer way along it; and the still: from the first fore arrival (or still_door's), looking the way you arrive."""
    lights_for(S)
    walk = walk_grid(S, doc_of(S)["colliders"])
    for e in S.empties:
        if e["name"].startswith("Arrive_") and clear_ahead(walk, e["pos"], e["face"]) < 2.0:
            fx, fz = e["face"]
            opts = [(-fz, fx), (fz, -fx)]
            e["face"] = max(opts, key=lambda f: clear_ahead(walk, e["pos"], f))
    if S.still is None:
        did = still_door or next(d for d, v in S.links.items() if v[1])
        e = next(e for e in S.empties if e["name"] == f"Arrive_{did}")
        S.still = (e["pos"], e["face"], pitch)
    return S


# ================================================================ the scenes
def service_entry():
    S = Scene("service_entry", "Service entry: the freight lift and the pool dive arrive here", "40.4 m by 16.4 m: a freight lift, a dock hall "
              "4 m high, a pool room and a guard office", mood="back of house, cold strip lights")
    S.spaces = [
        sp("freight_lift", -2.0, 2.0, -10.0, -6.6, 3.0, f="steel", w="steel", label="freight lift"),
        sp("dock", -10.0, 10.0, -6.4, 6.0, 4.0, f="concrete", w="service", tags={"tall"}, label="dock hall"),
        sp("pool_room", -22.0, -10.2, -6.4, 6.0, 3.2, f="tile", w="tile", label="pool room"),
        sp("guard_office", 10.2, 17.0, -6.4, -0.6, 3.0, w="service", label="guard office"),
    ]
    S.openings = [op(-1.6, 1.6, -6.6, -6.4, 2.6), op(-10.2, -10.0, -1.0, 1.0, 2.4),
                  op(10.0, 10.2, -4.4, -3.2, 2.2, leaf=("office", (1, 0)))]
    S.pits = [(-20.2, -12.8, -4.2, 3.2)]                       # the pool basin: no slab, its own walls and floor 1.6 m down
    carve(S)
    S.solid("Pool_floor", (-20.0, -1.9, -4.0), (-13.0, -1.6, 3.0), "tile", ("floor",))
    S.solid("Pool_wall_N", (-20.2, -1.9, -4.2), (-12.8, 0.0, -4.0), "tile", ("wall",))
    S.solid("Pool_wall_S", (-20.2, -1.9, 3.0), (-12.8, 0.0, 3.2), "tile", ("wall",))
    S.solid("Pool_wall_W", (-20.2, -1.9, -4.0), (-20.0, 0.0, 3.0), "tile", ("wall",))
    S.solid("Pool_wall_E", (-13.0, -1.9, -4.0), (-12.8, 0.0, 3.0), "tile", ("wall",))
    flight(S, "pool", 1.6, 3.0, -14.8, 1, "x", -1.6, 0.0, 6, 0.3, "tile")
    S.zone("water", "pool", (-20.0, -1.6, -4.0), (-13.0, -0.2, 3.0))
    S.label("pool, 1.6 m deep", -16.5, 2.2, "note")
    # the lift: you arrive in the car; its panel takes you back up
    S.empty("Link_freight_lift", (1.3, 0.0, -9.3))
    S.empty("Arrive_freight_lift", (0.0, 0.0, -8.2), face=(0, 1))
    S.links["freight_lift"] = ("grocery back_of_house", True, 0)
    S.decor("lift_panel", (1.7, 1.0, -9.6), (2.0, 1.5, -9.0), "monitor")
    # the pool dive: you climb out at the top of the steps; F at the edge would dive back (shut until swimming exists)
    S.empty("Link_pool_dive", (-12.2, 0.0, -2.0))
    S.empty("Arrive_pool_dive", (-12.2, 0.0, 2.3), face=(0, -1))
    S.links["pool_dive"] = ("the Intern (S8_H)", True, 0)
    edge_link(S, "checkpoint_1", "S", 4.0, 6.0, "checkpoint_1", fore=False)
    # dock cover and clutter
    block(S, "Crate", -7.5, -6.1, -3.5, -2.1, 1.4, cover="full")
    block(S, "Crate", -7.5, -6.5, -2.1, -1.1, 1.0, cover="half")
    block(S, "Crate", 5.5, 6.9, 1.0, 2.4, 1.4, cover="full")
    block(S, "Pallet", -3.0, -1.8, 2.0, 3.2, 1.0, cover="half")
    block(S, "Forklift", 2.0, 4.4, -3.5, -2.3, 2.0, cover="full")
    block(S, "Shelf", 4.0, 9.0, -6.4, -5.6, 2.4)
    block(S, "Pillar", -0.4, 0.4, -0.4, 0.4, 4.0, cover="full")
    block(S, "Desk", 12.0, 15.0, -6.4, -5.6, 0.9)
    block(S, "Bench", -21.4, -20.6, -5.5, -4.5, 0.45)
    agent(S, 1, 14.5, -2.6, face=(-1, 0), role="guard")
    patrol(S, "A", [(-4.0, 4.6), (8.0, 4.6), (8.0, -1.0), (-4.0, -4.6)])
    S.spot("ammo", 1, (-6.8, 0.0, -0.4))
    S.spot("ammo", 2, (8.4, 0.0, 3.2))
    S.spot("loot", 1, (16.0, 0.0, -5.0))
    S.spot("filed", 1, (-16.0, 0.0, 4.8), props={"phase": 2})
    cam(S, -9.7, -6.1, (1, 1), "A", h=4.0)
    cam(S, 9.7, 5.7, (-1, -1), "A", h=4.0)
    cam(S, -21.7, -6.1, (1, 1), "A", h=3.2)
    cam(S, 16.7, -0.9, (-1, -1), "A", h=3.0)
    restricted(S, 4.0)
    return finish(S, "freight_lift", pitch=-2.0)


def hidden_entry():
    S = Scene("hidden_entry", "Hidden entry: the one way in with no clearance, from the repeating room", "19.4 m by 19.4 m: a closet, a "
              "dog-leg maintenance passage and a storeroom; no cameras", mood="dusty, forgotten, unwatched")
    S.spaces = [
        sp("closet", -3.0, 3.0, -3.0, 3.0, 2.8, w="service"),
        sp("passage_1", 3.0, 12.0, -0.9, 0.9, 2.8, kind="corridor", w="service", label="maintenance passage"),
        sp("passage_2", 10.2, 12.0, 0.9, 10.0, 2.8, kind="corridor", w="service", label=""),
        sp("storeroom", 7.0, 16.0, 10.0, 16.0, 2.8, w="service"),
    ]
    carve(S)
    edge_link(S, "repeating_room", "W", 0.0, -3.0, "rdwe repeating_room", fore=True)
    edge_link(S, "corridors_a", "E", 13.0, 16.0, "corridors_a", fore=False, props={"maintenance": 1})
    block(S, "Shelf", -2.5, 2.5, -3.0, -2.4, 2.0)
    block(S, "Shelf", 7.5, 13.0, 15.4, 16.0, 2.2)
    block(S, "Crate", 8.0, 9.2, 12.0, 13.2, 1.2, cover="half")
    block(S, "Crate", 13.4, 14.6, 14.0, 15.2, 1.2, cover="half")
    S.spot("loot", 1, (-1.5, 0.0, -1.8), props={"stash": 1})
    S.spot("loot", 2, (9.0, 0.0, 14.6), props={"stash": 1})
    S.spot("ammo", 1, (14.5, 0.0, 11.0))
    S.label("no cameras: the base's blind spot", 6.5, 5.5, "note")
    return finish(S)


def b2_entry():
    S = Scene("b2_entry", "B2 entry: behind the laboratory's sealed B2 door", "34.4 m by 14.4 m: an airlock, a staff locker room, a sterile "
              "corridor and a scan room", mood="clinical, humming")
    S.spaces = [
        sp("airlock", -1.6, 1.6, -3.0, 0.0, 2.8, f="lab_floor", w="lab"),
        sp("locker_room", -6.0, 6.0, -14.0, -3.2, 3.0, f="lab_floor", w="lab", label="locker room"),
        sp("sterile_corridor", 6.0, 22.0, -9.0, -6.6, 3.0, kind="corridor", f="lab_floor", w="lab", label="sterile corridor"),
        sp("scan_room", 22.0, 28.0, -12.0, -3.6, 3.0, f="lab_floor", w="lab", label="scan room"),
    ]
    S.openings = [op(-0.7, 0.7, -3.2, -3.0, 2.3, leaf=("decon", (0, -1)))]
    carve(S)
    edge_link(S, "laboratory", "S", 0.0, 0.0, "lab laboratory (the B2 door)", fore=True)
    edge_link(S, "checkpoint_1", "E", -7.8, 28.0, "checkpoint_1", fore=False)
    block(S, "Lockers", -6.0, -5.4, -13.0, -4.0, 2.0)
    block(S, "Lockers", 5.4, 6.0, -13.6, -9.6, 2.0)
    block(S, "Lockers", 5.4, 6.0, -6.0, -3.6, 2.0)
    block(S, "Bench", -3.0, 3.0, -9.0, -8.4, 0.45)
    block(S, "Bench", -3.0, 3.0, -6.0, -5.4, 0.45)
    block(S, "Desk", 23.0, 25.5, -11.8, -11.0, 1.0, cover="half")
    block(S, "Barrier", 24.0, 25.2, -6.2, -5.6, 1.1, cover="half")
    S.decor("scanner_arch_L", (22.6, 0.0, -9.2), (22.8, 2.3, -9.0), "steel")
    S.decor("scanner_arch_R", (22.6, 0.0, -6.6), (22.8, 2.3, -6.4), "steel")
    S.spot("locker", 1, (-4.8, 0.0, -8.0), face=(-1, 0))
    agent(S, 1, 12.0, -7.8, face=(-1, 0))
    patrol(S, "B", [(-3.5, -12.6), (3.5, -12.6), (3.5, -7.2), (-3.5, -7.2)])
    S.spot("ammo", 1, (24.5, 0.0, -4.4))
    S.spot("loot", 1, (-4.6, 0.0, -13.2))
    S.spot("filed", 1, (3.6, 0.0, -10.6), props={"phase": 2})
    cam(S, 0.0, -13.7, (0, 1), "A")
    cam(S, 21.7, -8.7, (-1, 0), "A")
    cam(S, 27.7, -11.7, (-1, 1), "A")
    restricted(S)
    return finish(S)


def checkpoint_1():
    S = Scene("checkpoint_1", "Checkpoint 1: keycard tier 1", "24.4 m by 22.4 m: an outer hall the two keyed entries open into, two scanner "
              "lanes, a guard booth with a window, an inner hall and the tier-1 door", mood="security, flat white light")
    W, F = "checkpoint", "checkpoint_floor"
    S.spaces = [
        sp("outer_hall", -12.0, 12.0, 0.0, 10.0, 3.2, f=F, w=W, label="outer hall"),
        sp("booth", -3.0, 3.0, -4.6, -0.2, 3.0, f=F, w=W, label="guard booth"),
        sp("inner_w", -12.0, -3.2, -12.0, -0.2, 3.2, f=F, w=W, label=""),
        sp("inner_e", 3.2, 12.0, -12.0, -0.2, 3.2, f=F, w=W, label=""),
        sp("inner_hall", -12.0, 12.0, -12.0, -4.8, 3.2, f=F, w=W, label="inner hall"),
    ]
    S.openings = [op(-8.4, -7.0, -0.2, 0.0, 2.4), op(7.0, 8.4, -0.2, 0.0, 2.4),
                  op(-2.4, 2.4, -0.2, 0.0, 2.4, sill=1.1),
                  op(-0.6, 0.6, -4.8, -4.6, 2.2, leaf=("booth", (0, 1)))]
    carve(S)
    S.label("scanner lane", -7.7, 1.0, "note")
    S.label("scanner lane", 7.7, 1.0, "note")
    edge_link(S, "service_entry", "W", 6.0, -12.0, "service_entry", fore=True)
    edge_link(S, "b2_entry", "E", 6.0, 12.0, "b2_entry", fore=True)
    edge_link(S, "corridors_a", "N", 0.0, -12.0, "corridors_a", fore=False, keycard=1)
    block(S, "Barrier", -6.0, -3.0, 3.0, 3.6, 1.1, cover="half")
    block(S, "Barrier", 3.0, 6.0, 3.0, 3.6, 1.1, cover="half")
    block(S, "Planter", -1.0, 1.0, 6.0, 8.0, 1.0, cover="half")
    block(S, "Barrier", -9.5, -7.5, 7.0, 7.6, 1.1, cover="half")
    block(S, "Barrier", 7.5, 9.5, 7.0, 7.6, 1.1, cover="half")
    block(S, "Desk", -2.4, 2.4, -1.2, -0.6, 0.9)
    block(S, "Crate", -9.0, -7.6, -9.0, -7.6, 1.4, cover="full")
    block(S, "Crate", 7.6, 9.0, -9.0, -7.6, 1.4, cover="full")
    block(S, "Pillar", -6.4, -5.6, -3.0, -2.2, 3.2, cover="full")
    block(S, "Pillar", 5.6, 6.4, -3.0, -2.2, 3.2, cover="full")
    for x in (-8.5, -6.9, 6.9, 8.5):
        S.decor(f"scanner_arch_{x:+.1f}", (x - 0.05, 0.0, 0.0), (x + 0.05, 2.3, 0.6), "steel")
    agent(S, 1, 0.0, -3.0, face=(0, 1), role="guard")
    agent(S, 2, -9.5, -10.6, face=(1, 0))
    patrol(S, "A", [(-10.0, 1.4), (10.0, 1.4), (10.0, 9.0), (-10.0, 9.0)])
    S.spot("ammo", 1, (0.0, 0.0, 9.0))
    S.spot("ammo", 2, (10.4, 0.0, -10.6))
    S.spot("loot", 1, (-2.0, 0.0, -3.6))
    S.spot("filed", 1, (-10.4, 0.0, -2.0), props={"phase": 2})
    cam(S, -11.7, 9.7, (1, -1), "A", h=3.2)
    cam(S, 11.7, 9.7, (-1, -1), "A", h=3.2)
    cam(S, -11.7, -11.7, (1, 1), "A", h=3.2)
    cam(S, 11.7, -11.7, (-1, 1), "A", h=3.2)
    restricted(S, 3.2)
    return finish(S)


def corridors_a():
    S = Scene("corridors_a", "Corridors A: the first loop of the base", "41.2 m by 29.2 m: a ring of 2.4 m corridors round two blocks, a spine "
              "through the middle with an atrium, corner bays, an office and a store", mood="institutional, endless doors")
    C, CF = "corridor", "corridor_floor"
    S.spaces = [
        sp("ring_s", -20.4, 20.4, 12.0, 14.4, kind="corridor", f=CF, w=C, label="south corridor"),
        sp("ring_n", -20.4, 20.4, -14.4, -12.0, kind="corridor", f=CF, w=C, label="north corridor"),
        sp("ring_w", -20.4, -18.0, -12.0, 12.0, kind="corridor", f=CF, w=C, label=""),
        sp("ring_e", 18.0, 20.4, -12.0, 12.0, kind="corridor", f=CF, w=C, label=""),
        sp("spine", -1.2, 1.2, -12.0, 12.0, kind="corridor", f=CF, w=C, label=""),
        sp("atrium", -6.0, 6.0, -4.5, 4.5, f=CF, w=C),
        sp("bay_nw", -20.4, -15.4, -14.4, -9.4, f=CF, w=C, label=""), sp("bay_ne", 15.4, 20.4, -14.4, -9.4, f=CF, w=C, label=""),
        sp("bay_sw", -20.4, -15.4, 9.4, 14.4, f=CF, w=C, label=""), sp("bay_se", 15.4, 20.4, 9.4, 14.4, f=CF, w=C, label=""),
        sp("office", -14.0, -8.0, 6.0, 11.8, f=CF, w=C),
        sp("store", 6.0, 12.0, -11.8, -6.0, f=CF, w=C),
    ] + [sp(f"alcove_{n}", a - 1.0, a + 1.0, z0, z1, f=CF, w=C, label="") for n, a, z0, z1 in
         (("n1", -4.0, -15.6, -14.4), ("n2", 4.0, -15.6, -14.4), ("s1", -7.0, 14.4, 15.6), ("s2", 7.0, 14.4, 15.6))]
    S.openings = [op(-11.6, -10.4, 11.8, 12.0, 2.2, leaf=("office", (0, -1))), op(8.4, 9.6, -12.0, -11.8, 2.2, leaf=("store", (0, 1)))]
    carve(S)
    edge_link(S, "checkpoint_1", "S", 0.0, 14.4, "checkpoint_1", fore=True)
    edge_link(S, "hidden_entry", "E", 6.0, 20.4, "hidden_entry", fore=True, props={"maintenance": 1})
    edge_link(S, "breaker_room", "W", -4.0, -20.4, "breaker_room", fore=False)
    edge_link(S, "labs_a_west", "N", -10.0, -14.4, "labs_a", fore=False)
    edge_link(S, "labs_a_east", "N", 12.0, -14.4, "labs_a", fore=False)
    edge_link(S, "checkpoint_2", "E", -6.0, 20.4, "checkpoint_2", fore=False)
    for x0, z0 in ((-3.4, -2.4), (2.6, -2.4), (-3.4, 1.6), (2.6, 1.6)):
        block(S, "Pillar", x0, x0 + 0.8, z0, z0 + 0.8, 3.0, cover="full")
    block(S, "Barrier", -5.4, -4.4, -0.6, 0.6, 1.1, cover="half")
    block(S, "Barrier", 4.4, 5.4, -0.6, 0.6, 1.1, cover="half")
    block(S, "Crate", -17.4, -16.2, -11.4, -10.2, 1.2, cover="half")
    block(S, "Crate", 16.2, 17.4, -11.4, -10.2, 1.2, cover="half")
    block(S, "Crate", -17.4, -16.2, 10.2, 11.4, 1.2, cover="half")
    block(S, "Crate", 16.2, 17.4, 10.2, 11.4, 1.4, cover="full")
    block(S, "Desk", -13.4, -11.8, 6.6, 7.4, 0.9)
    block(S, "Shelf", 6.4, 11.6, -6.6, -6.0, 2.2)
    agent(S, 1, 0.0, -3.5, face=(0, 1))
    agent(S, 2, -19.2, 6.0, face=(0, -1))
    agent(S, 3, -13.0, 9.6, face=(1, 0), role="guard")
    patrol(S, "R", [(-19.2, -13.2), (19.2, -13.2), (19.2, 13.2), (-19.2, 13.2)])
    S.spot("ammo", 1, (-15.9, 0.0, -10.8))
    S.spot("ammo", 2, (15.8, 0.0, 10.8))
    S.spot("loot", 1, (9.0, 0.0, -8.4))
    S.spot("filed", 1, (-9.4, 0.0, 10.0), props={"phase": 2})
    cam(S, -20.1, 14.1, (1, 0), "A")
    cam(S, 20.1, -14.1, (-1, 0), "A")
    cam(S, -20.1, -14.1, (0, 1), "A")
    cam(S, 20.1, 14.1, (0, -1), "A")
    cam(S, -4.0, -4.2, (0, 1), "A")
    cam(S, 4.0, 4.2, (0, -1), "A")
    restricted(S)
    return finish(S)


def labs_a():
    S = Scene("labs_a", "Labs A: two labs either side of a glazed spine", "32.4 m by 21.2 m: a south hall, two labs with benches and fume "
              "hoods, a spine with windows into both, a north hall and the tier-2 door to Labs B", mood="clinical, too clean")
    L, LF = "lab", "lab_floor"
    S.spaces = [
        sp("hall_s", -16.0, 16.0, 8.0, 10.4, kind="corridor", f=LF, w=L, label="south hall"),
        sp("spine", -1.2, 1.2, -8.2, 8.0, kind="corridor", f=LF, w=L, label=""),
        sp("hall_n", -16.0, 16.0, -10.6, -8.2, kind="corridor", f=LF, w=L, label="north hall"),
        sp("lab_w", -16.0, -1.4, -8.0, 7.8, f=LF, w=L, label="lab west"),
        sp("lab_e", 1.4, 16.0, -8.0, 7.8, f=LF, w=L, label="lab east"),
    ]
    S.openings = [op(-12.0, -10.4, 7.8, 8.0), op(-5.0, -3.4, 7.8, 8.0), op(3.4, 5.0, 7.8, 8.0), op(10.4, 12.0, 7.8, 8.0),
                  op(-9.0, -7.4, -8.2, -8.0), op(7.4, 9.0, -8.2, -8.0),
                  op(-1.4, -1.2, -0.8, 0.8), op(1.2, 1.4, -0.8, 0.8),
                  op(-1.4, -1.2, -6.0, -2.0, 2.4, sill=1.0), op(-1.4, -1.2, 2.0, 6.0, 2.4, sill=1.0),
                  op(1.2, 1.4, -6.0, -2.0, 2.4, sill=1.0), op(1.2, 1.4, 2.0, 6.0, 2.4, sill=1.0)]
    carve(S)
    edge_link(S, "corridors_a_west", "S", -10.0, 10.4, "corridors_a", fore=True)
    edge_link(S, "corridors_a_east", "S", 10.0, 10.4, "corridors_a", fore=True)
    edge_link(S, "labs_b", "N", 0.0, -10.6, "labs_b", fore=False, keycard=2)
    for sgn in (-1, 1):
        for xa, xb in ((11.0, 14.0), (5.0, 8.0)):
            x0, x1 = sorted((sgn * xa, sgn * xb))
            block(S, "Bench", x0, x1, -5.0, -4.1, 0.95, cover="half")
            block(S, "Bench", x0, x1, 1.0, 1.9, 0.95, cover="half")
        for z0, z1 in ((-6.0, -3.0), (2.0, 5.0)):
            x0, x1 = sorted((sgn * 16.0, sgn * 15.2))
            block(S, "Hood", x0, x1, z0, z1, 2.2, cover="full")
        x0, x1 = sorted((sgn * 3.6, sgn * 2.8))
        block(S, "Tank", x0, x1, 4.0, 4.8, 2.4, cover="full")
    agent(S, 1, 10.0, -6.5, face=(0, 1))
    agent(S, 2, -10.0, -6.5, face=(0, 1))
    patrol(S, "N", [(-14.4, -9.4), (14.4, -9.4)])
    S.spot("ammo", 1, (-6.5, 0.0, 6.5))
    S.spot("ammo", 2, (6.5, 0.0, 6.5))
    S.spot("loot", 1, (-15.0, 0.0, 0.0), props={"sample": 1})
    S.spot("loot", 2, (15.0, 0.0, 0.0), props={"sample": 1})
    S.spot("filed", 1, (0.0, 0.0, -5.0), props={"phase": 2})
    cam(S, -15.7, -7.7, (1, 1), "B")
    cam(S, 15.7, -7.7, (-1, 1), "B")
    cam(S, -15.7, 9.2, (1, 0), "B")
    cam(S, 15.7, -9.4, (-1, 0), "B")
    restricted(S)
    return finish(S)


def checkpoint_2():
    S = Scene("checkpoint_2", "Checkpoint 2: keycard tier 2", "30.4 m by 26.4 m: an antechamber, a screening hall with a chicane of barriers, "
              "a guard booth with a window and the tier-2 vestibule", mood="security, harder")
    W, F = "checkpoint", "checkpoint_floor"
    S.spaces = [
        sp("antechamber", -14.0, -6.0, -4.0, 4.0, 3.0, f=F, w=W),
        sp("screening_hall", -5.8, 10.0, -8.0, 8.0, 3.2, f=F, w=W, label="screening hall"),
        sp("booth", 2.0, 8.0, -13.0, -8.2, 3.0, f=F, w=W, label="guard booth"),
        sp("vestibule", 10.2, 16.0, -2.0, 2.0, 3.0, f=F, w=W),
    ]
    S.openings = [op(-6.0, -5.8, -1.2, 1.2, 2.6), op(3.6, 7.6, -8.2, -8.0, 2.4, sill=1.1),
                  op(2.4, 3.4, -8.2, -8.0, 2.2, leaf=("booth", (0, -1))), op(10.0, 10.2, -1.0, 1.0, 2.4)]
    carve(S)
    edge_link(S, "corridors_a", "W", 0.0, -14.0, "corridors_a", fore=True)
    edge_link(S, "corridors_b", "E", 0.0, 16.0, "corridors_b", fore=False, keycard=2)
    block(S, "Barrier", -4.0, -1.0, -5.0, -4.4, 1.1, cover="half")
    block(S, "Barrier", 1.0, 4.0, 2.0, 2.6, 1.1, cover="half")
    block(S, "Barrier", -2.0, 1.0, 5.0, 5.6, 1.1, cover="half")
    block(S, "Barrier", 4.5, 7.5, -3.0, -2.4, 1.1, cover="half")
    block(S, "Barrier", 6.0, 8.6, 4.5, 5.1, 1.1, cover="half")
    block(S, "Pillar", -0.4, 0.4, -0.4, 0.4, 3.2, cover="full")
    block(S, "Desk", 3.6, 7.6, -9.0, -8.4, 0.9)
    block(S, "Crate", -13.4, -12.2, -3.4, -2.2, 1.2, cover="half")
    agent(S, 1, 5.0, -11.0, face=(0, 1), role="guard")
    agent(S, 2, 8.0, 6.5, face=(-1, 0))
    patrol(S, "C", [(-4.4, -6.6), (8.6, -6.6), (8.6, 6.6), (-4.4, 6.6)])
    S.spot("ammo", 1, (-7.0, 0.0, 3.0))
    S.spot("loot", 1, (7.0, 0.0, -12.4))
    S.spot("filed", 1, (-4.4, 0.0, 1.8), props={"phase": 2})
    cam(S, -13.7, -3.7, (1, 1), "C")
    cam(S, -5.5, 7.7, (1, -1), "C", h=3.2)
    cam(S, 9.7, 7.7, (-1, -1), "C", h=3.2)
    cam(S, 15.7, -1.7, (-1, 1), "C")
    restricted(S, 3.2)
    return finish(S)


def corridors_b():
    S = Scene("corridors_b", "Corridors B: a ladder of corridors", "44.4 m by 21.2 m: two long corridors joined by three cross corridors, the "
              "middle one through a server closet", mood="institutional, the hum louder")
    C, CF = "corridor", "corridor_floor"
    S.spaces = [
        sp("long_n", -22.0, 22.0, -10.4, -8.0, kind="corridor", f=CF, w=C, label="north corridor"),
        sp("long_s", -22.0, 22.0, 8.0, 10.4, kind="corridor", f=CF, w=C, label="south corridor"),
        sp("cross_w", -22.0, -19.6, -8.0, 8.0, kind="corridor", f=CF, w=C, label=""),
        sp("cross_c", -1.2, 1.2, -8.0, 8.0, kind="corridor", f=CF, w=C, label=""),
        sp("cross_e", 19.6, 22.0, -8.0, 8.0, kind="corridor", f=CF, w=C, label=""),
        sp("server_closet", -5.0, 5.0, -3.5, 3.5, f=CF, w=C, label="server closet"),
    ] + [sp(f"alcove_{n}{k}", a - 1.0, a + 1.0, z0, z1, f=CF, w=C, label="") for n, z0, z1 in (("n", -11.6, -10.4), ("s", 10.4, 11.6))
         for k, a in enumerate((-16.0, -5.0, 5.0, 16.0), 1)]   # alcoves to step into off the two long corridors (cover from their length)
    carve(S)
    edge_link(S, "checkpoint_2", "W", -9.2, -22.0, "checkpoint_2", fore=True)
    edge_link(S, "labs_b_west", "N", -11.0, -10.4, "labs_b", fore=False)
    edge_link(S, "labs_b_east", "N", 11.0, -10.4, "labs_b", fore=False)
    edge_link(S, "breaker_room", "S", -11.0, 10.4, "breaker_room", fore=False, keycard=2)
    edge_link(S, "checkpoint_3", "E", 9.2, 22.0, "checkpoint_3", fore=False)
    block(S, "Cabinet", -4.0, -3.2, -2.5, -0.5, 2.0, cover="full")
    block(S, "Cabinet", 3.2, 4.0, 0.5, 2.5, 2.0, cover="full")
    block(S, "Crate", -4.4, -3.4, 2.0, 3.0, 1.2, cover="half")
    block(S, "Crate", 3.4, 4.4, -3.0, -2.0, 1.2, cover="half")
    agent(S, 1, 3.8, -0.8, face=(-1, 0))
    agent(S, 2, 17.0, -9.2, face=(-1, 0))
    agent(S, 3, 12.0, 9.2, face=(-1, 0))
    patrol(S, "L", [(-20.8, -9.2), (20.8, -9.2), (20.8, 9.2), (-20.8, 9.2)])
    S.spot("ammo", 1, (-3.0, 0.0, -3.0))
    S.spot("ammo", 2, (0.0, 0.0, 9.2))
    S.spot("loot", 1, (2.6, 0.0, 3.0))
    S.spot("filed", 1, (-20.8, 0.0, 6.0), props={"phase": 2})
    cam(S, -21.7, -10.1, (1, 0), "C")
    cam(S, 21.7, 10.1, (-1, 0), "C")
    cam(S, 21.7, -10.1, (0, 1), "C")
    cam(S, -21.7, 10.1, (0, -1), "C")
    cam(S, -3.0, -3.2, (0, 1), "C")
    restricted(S)
    return finish(S)


def labs_b():
    S = Scene("labs_b", "Labs B: the open-plan lab", "36.4 m by 26.8 m: one big lab hall with glass test cubicles, a south hall, a specimen "
              "room and the tier-2 door back to Labs A", mood="clinical, something kept here")
    L, LF = "lab", "lab_floor"
    S.spaces = [
        sp("lab_hall", -18.0, 18.0, -10.0, 6.0, 3.2, f=LF, w=L, label="lab hall"),
        sp("hall_s", -18.0, 18.0, 6.2, 8.6, kind="corridor", f=LF, w=L, label="south hall"),
        sp("specimen_room", -18.0, -8.0, -18.0, -10.2, 3.0, f=LF, w=L, label="specimen room"),
    ]
    S.openings = [op(-15.0, -13.4, 6.0, 6.2), op(-1.0, 1.0, 6.0, 6.2), op(13.4, 15.0, 6.0, 6.2),
                  op(-14.0, -12.8, -10.2, -10.0, 2.2, leaf=("specimen", (0, -1)))]
    carve(S)
    edge_link(S, "corridors_b_west", "S", -10.0, 8.6, "corridors_b", fore=True)
    edge_link(S, "corridors_b_east", "S", 10.0, 8.6, "corridors_b", fore=True)
    edge_link(S, "labs_a", "W", -4.0, -18.0, "labs_a", fore=True, keycard=2)
    for x0 in (-10.0, -1.5, 7.0):
        block(S, "Cubicle", x0, x0 + 3.0, -7.0, -4.0, 2.6, cover="full")
    block(S, "Bench", -14.0, -11.0, -1.0, -0.1, 0.95, cover="half")
    block(S, "Bench", -6.0, -3.0, 1.0, 1.9, 0.95, cover="half")
    block(S, "Bench", 3.0, 6.0, -1.0, -0.1, 0.95, cover="half")
    block(S, "Bench", 11.0, 14.0, 1.0, 1.9, 0.95, cover="half")
    block(S, "Pillar", -4.4, -3.6, -3.0, -2.2, 3.2, cover="full")
    block(S, "Pillar", 3.6, 4.4, -3.0, -2.2, 3.2, cover="full")
    block(S, "Tank", -17.0, -16.0, -17.0, -16.0, 2.4, cover="full")
    block(S, "Tank", -12.0, -11.0, -17.0, -16.0, 2.4, cover="full")
    block(S, "Shelf", -17.4, -8.6, -18.0, -17.6, 2.0)
    agent(S, 1, 0.0, -8.5, face=(0, 1))
    agent(S, 2, 12.0, -8.5, face=(0, 1))
    agent(S, 3, -9.6, -14.4, face=(0, 1), role="guard")
    patrol(S, "S", [(-16.4, 7.4), (16.4, 7.4)])
    S.spot("ammo", 1, (-16.0, 0.0, 4.0))
    S.spot("ammo", 2, (16.0, 0.0, 4.0))
    S.spot("loot", 1, (-14.5, 0.0, -16.5), props={"keycard_tier": 3})
    S.spot("loot", 2, (8.5, 0.0, -2.8), props={"sample": 1})
    S.spot("filed", 1, (16.4, 0.0, -8.6), props={"phase": 2})
    cam(S, -17.7, -9.7, (1, 1), "B", h=3.2)
    cam(S, 17.7, -9.7, (-1, 1), "B", h=3.2)
    cam(S, -17.7, 7.4, (1, 0), "B")
    cam(S, -8.3, -17.7, (-1, 1), "B")
    restricted(S, 3.2)
    return finish(S)


def breaker_room():
    S = Scene("breaker_room", "Breaker room: cut the cameras", "28.2 m by 16.4 m: a plant room with three breaker panels (circuits A, B and C), "
              "two transformers and two ways in", mood="loud, hot, orange")
    S.spaces = [
        sp("plant_room", -9.0, 9.0, -6.0, 6.0, 3.2, w="service", label="plant room"),
        sp("way_a", -14.0, -9.0, -1.2, 1.2, 3.0, kind="corridor", w="service", label=""),
        sp("way_b", -1.2, 1.2, 6.0, 10.0, 3.0, kind="corridor", w="service", label=""),
    ]
    carve(S)
    edge_link(S, "corridors_a", "W", 0.0, -14.0, "corridors_a", fore=True)
    edge_link(S, "corridors_b", "S", 0.0, 10.0, "corridors_b", fore=True, keycard=2, reader_off=0.75)
    block(S, "Trafo", -5.0, -2.5, -3.0, -1.0, 2.0, cover="full")
    block(S, "Trafo", 2.5, 5.0, 1.0, 3.0, 2.0, cover="full")
    block(S, "Barrier", -1.0, 1.0, 3.0, 3.6, 1.1, cover="half")
    cuts = {"A": "service_entry,b2_entry,checkpoint_1,corridors_a,breaker_room", "B": "labs_a,labs_b", "C": "checkpoint_2,corridors_b,checkpoint_3"}
    for c, x in (("A", -6.0), ("B", 0.0), ("C", 6.0)):
        block(S, "Breaker", x - 1.0, x + 1.0, -6.0, -5.6, 2.0, props={"circuit": c})
        S.spot("breaker", c, (x, 0.0, -5.0), face=(0, -1), props={"circuit": c, "cuts": cuts[c]})
        S.label(f"breaker {c}", x, -4.2, "note")
    S.decor("cable_tray", (-8.6, 2.7, -5.4), (8.6, 2.8, -4.9), "steel")
    agent(S, 1, 7.5, -3.0, face=(-1, 0), role="guard")
    S.spot("ammo", 1, (-8.0, 0.0, 5.0))
    S.spot("loot", 1, (8.0, 0.0, 5.0))
    S.spot("filed", 1, (-3.0, 0.0, 4.0), props={"phase": 2})
    cam(S, -8.7, 5.7, (1, -1), "A", h=3.2)
    restricted(S, 3.2)
    return finish(S)


def checkpoint_3():
    S = Scene("checkpoint_3", "Checkpoint 3: keycard tier 3, the vault gate", "30.4 m by 26.4 m: an approach, a decontamination tunnel between "
              "two doors, a vault with twin guard booths and the tier-3 door to the Registrar", mood="security, final, cold")
    W, F = "checkpoint", "checkpoint_floor"
    S.spaces = [
        sp("approach", -16.0, -8.0, -2.0, 2.0, 3.0, kind="corridor", f=F, w=W),
        sp("decon", -7.8, -2.0, -1.2, 1.2, 2.8, kind="corridor", f="tile", w="tile", label="decon"),
        sp("vault", -1.8, 14.0, -8.0, 8.0, 3.2, f=F, w=W),
        sp("booth_n", 2.0, 8.0, -13.0, -8.2, 3.0, f=F, w=W, label="booth"),
        sp("booth_s", 2.0, 8.0, 8.2, 13.0, 3.0, f=F, w=W, label="booth"),
    ]
    S.openings = [op(-8.0, -7.8, -0.6, 0.6, 2.2, leaf=("decon_in", (1, 0))), op(-2.0, -1.8, -0.6, 0.6, 2.2, leaf=("decon_out", (1, 0))),
                  op(3.6, 7.6, -8.2, -8.0, 2.4, sill=1.1), op(3.6, 7.6, 8.0, 8.2, 2.4, sill=1.1),
                  op(2.3, 3.3, -8.2, -8.0, 2.2, leaf=("booth_n", (0, -1))), op(2.3, 3.3, 8.0, 8.2, 2.2, leaf=("booth_s", (0, 1)))]
    carve(S)
    S.zone("trigger", "decon", (-7.8, 0.0, -1.2), (-2.0, 2.8, 1.2))
    edge_link(S, "corridors_b", "W", 0.0, -16.0, "corridors_b", fore=True)
    edge_link(S, "registrar_hall", "E", 0.0, 14.0, "registrar_hall", fore=False, keycard=3)
    block(S, "Pillar", 4.6, 5.4, -4.4, -3.6, 3.2, cover="full")
    block(S, "Pillar", 4.6, 5.4, 3.6, 4.4, 3.2, cover="full")
    block(S, "Barrier", 8.5, 9.1, -2.0, 2.0, 1.1, cover="half")
    block(S, "Barrier", 1.0, 1.6, -5.0, -2.0, 1.1, cover="half")
    block(S, "Barrier", 1.0, 1.6, 2.0, 5.0, 1.1, cover="half")
    block(S, "Desk", 3.6, 7.6, -9.0, -8.4, 0.9)
    block(S, "Desk", 3.6, 7.6, 8.4, 9.0, 0.9)
    S.decor("vault_sign", (13.9, 2.4, -1.0), (14.0, 2.8, 1.0), "sign")
    agent(S, 1, 5.0, -11.0, face=(0, 1), role="guard")
    agent(S, 2, 5.0, 11.0, face=(0, -1), role="guard")
    agent(S, 3, 11.0, -6.0, face=(-1, 0))
    S.spot("ammo", 1, (-9.0, 0.0, 1.4))
    S.spot("loot", 1, (7.0, 0.0, 12.4))
    S.spot("filed", 1, (12.6, 0.0, 6.6), props={"phase": 2})
    cam(S, -15.7, -1.7, (1, 0), "C")
    cam(S, -2.3, 0.9, (-1, 0), "C", h=2.8)
    cam(S, -1.5, -7.7, (1, 1), "C", h=3.2)
    cam(S, 13.7, 7.7, (-1, -1), "C", h=3.2)
    restricted(S, 3.2)
    return finish(S)


# the arena: the field of panels and the rack rows (block starts along x; rows 1 and 3 are offset so no aisle runs straight across)
FIELD = (-20.0, 20.0, -10.0, 10.0)
RACK_ROWS = [(-7.0, -6.0, (-18.0, -12.0, -6.0, 0.0, 6.0, 12.0)), (-3.0, -2.0, (-15.0, -9.0, -3.0, 3.0, 9.0, 15.0)),
             (2.0, 3.0, (-18.0, -12.0, -6.0, 0.0, 6.0, 12.0)), (6.0, 7.0, (-15.0, -9.0, -3.0, 3.0, 9.0, 15.0))]
RACK_W, RACK_H = 1.2, 2.4
ARENA_H = 7.0


def registrar_hall():
    S = Scene("registrar_hall", "The Registrar's hall: the boss arena", "47.4 m by 20.4 m, 7 m high: a long green server hall with a pink stripe "
              "on the walls, 48 racks in four rows over a field of 200 floor panels, fixed landings at both ends, the control room's front "
              "and the cell at the east end, 12 cameras round every wall", mood="green, humming, watched")
    G, GF = "server_green", "server_floor"
    S.spaces = [
        sp("landing_w", -24.0, -20.0, -10.0, 10.0, ARENA_H, f=GF, w=G, tags={"tall"}, label=""),
        sp("field", FIELD[0], FIELD[1], FIELD[2], FIELD[3], ARENA_H, f=GF, w=G, floor=False, ceiling=False, tags={"tall"}, label=""),
        sp("landing_e", 20.0, 23.0, -10.0, 10.0, ARENA_H, f=GF, w=G, tags={"tall"}, label=""),
    ]
    S.pits = [(-20.0, 20.0, -10.0, 10.0)]
    carve(S)
    # the floor panels (deleted under you in phase 3) over a pit 8 m deep
    racks = []
    for z0, z1, starts in RACK_ROWS:
        for x0 in starts:
            racks += [(x0, x0 + RACK_W, z0, z1), (x0 + RACK_W, x0 + 2 * RACK_W, z0, z1)]
    nx, nz = int((FIELD[1] - FIELD[0]) / PANEL), int((FIELD[3] - FIELD[2]) / PANEL)
    for i in range(nx):
        for j in range(nz):
            x0, z0 = FIELD[0] + i * PANEL, FIELD[2] + j * PANEL
            under = int(any(r[0] < x0 + PANEL and r[1] > x0 and r[2] < z0 + PANEL and r[3] > z0 for r in racks))
            S.solid(f"FloorPanel_{i:02d}_{j:02d}", (x0, -SLAB, z0), (x0 + PANEL, 0.0, z0 + PANEL), "panel_a" if (i + j) % 2 else "panel_b",
                    ("floor", "panel"), props={"panel_x": i, "panel_z": j, "under_rack": under})
    S.solid("Pit_floor", (FIELD[0], -8.3, FIELD[2]), (FIELD[1], -8.0, FIELD[3]), "pit", ("floor",))
    S.solid("Pit_wall_N", (FIELD[0] - T, -8.3, FIELD[2] - T), (FIELD[1] + T, -SLAB, FIELD[2]), "pit", ("wall",))
    S.solid("Pit_wall_S", (FIELD[0] - T, -8.3, FIELD[3]), (FIELD[1] + T, -SLAB, FIELD[3] + T), "pit", ("wall",))
    S.solid("Pit_wall_W", (FIELD[0] - T, -8.3, FIELD[2]), (FIELD[0], -SLAB, FIELD[3]), "pit", ("wall",))
    S.solid("Pit_wall_E", (FIELD[1], -8.3, FIELD[2]), (FIELD[1] + T, -SLAB, FIELD[3]), "pit", ("wall",))
    S.zone("hazard", "pit", (FIELD[0], -8.0, FIELD[2]), (FIELD[1], -1.0, FIELD[3]))
    # the server racks (shot in phase 3)
    for n, (x0, x1, z0, z1) in enumerate(racks, 1):
        S.solid(f"Rack_{n:02d}", (x0, 0.0, z0), (x1, RACK_H, z1), "rack", ("cover", "cover_full", "rack"), props={"rack": n, "hp": 100})
    # the ceiling over the field: panels the page can open on the glitched sky in phase 3
    for i in range(int((FIELD[1] - FIELD[0]) / 4.0)):
        for j in range(int((FIELD[3] - FIELD[2]) / 4.0)):
            x0, z0 = FIELD[0] + 4.0 * i, FIELD[2] + 4.0 * j
            S.solid(f"CeilingPanel_{i:02d}_{j:02d}", (x0, ARENA_H, z0), (x0 + 4.0, ARENA_H + 0.2, z0 + 4.0), "ceiling", ("ceiling", "ceiling_panel"),
                    props={"ceiling_x": i, "ceiling_z": j})
    # the pink stripe round every wall
    S.decor("stripe_N", (-24.0, 1.2, -10.0), (23.0, 1.5, -9.97), "pink")
    S.decor("stripe_S", (-24.0, 1.2, 9.97), (23.0, 1.5, 10.0), "pink")
    S.decor("stripe_W", (-24.0, 1.2, -9.97), (-23.97, 1.5, 9.97), "pink")
    S.decor("stripe_E", (22.97, 1.2, -9.97), (23.0, 1.5, 9.97), "pink")
    # the control room's front and the cell at the east end (the rooms themselves are the control_room scene)
    S.decor("control_room_window", (22.94, 3.4, -4.5), (23.0, 5.6, 4.5), "glass")
    S.decor("control_room_sign", (22.94, 2.5, -1.2), (23.0, 2.9, 1.2), "sign")
    for k in range(7):
        S.decor(f"cell_bar_{k}", (22.9, 0.2, 5.2 + 0.3 * k), (23.0, 2.6, 5.26 + 0.3 * k), "steel")
    S.label("landing", -22.0, 3.0, "note")
    S.label("landing", 21.5, 3.0, "note")
    S.label("control room window", 21.0, -3.0, "note")
    S.label("cell (bars)", 21.5, 6.1, "note")
    edge_link(S, "checkpoint_3", "W", 0.0, -24.0, "checkpoint_3", fore=True)
    edge_link(S, "control_room", "E", 0.0, 23.0, "control_room", fore=False)
    # the breakers for the arena's own cameras (phase 1: cut them, smash the rest)
    brk = [("R1", (-10.6, -9.4, -10.0, -9.7), (-10.0, -9.2), (0, -1)), ("R2", (9.4, 10.6, 9.7, 10.0), (10.0, 9.2), (0, 1)),
           ("R3", (-24.0, -23.7, -6.6, -5.4), (-23.2, -6.0), (-1, 0)), ("R4", (22.7, 23.0, -8.6, -7.4), (22.2, -8.0), (1, 0))]
    for c, (x0, x1, z0, z1), (sx, sz), f in brk:
        block(S, "Breaker", x0, x1, z0, z1, 2.0, props={"circuit": c})
        S.spot("breaker", c, (sx, 0.0, sz), face=f, props={"circuit": c, "cuts": "registrar_hall"})
    for x in (-15.0, -5.0, 5.0, 15.0):
        cam(S, x, -9.75, (0, 1), "R1", y=3.2)
    for x in (-15.0, -5.0, 5.0, 15.0):
        cam(S, x, 9.75, (0, -1), "R2", y=3.2)
    for z in (-5.0, 5.0):
        cam(S, -23.75, z, (1, 0), "R3", y=3.2)
    for z in (-6.5, 6.5):
        cam(S, 22.75, z, (-1, 0), "R4", y=3.2)
    for n, (x, z, f) in enumerate([(-12.0, -8.5, (0, 1)), (0.0, -8.5, (0, 1)), (12.0, -8.5, (0, 1)), (-12.0, 8.5, (0, -1)), (0.0, 8.5, (0, -1)),
                                   (12.0, 8.5, (0, -1))], 1):
        agent(S, n, x, z, face=f, role="phase_1")
    S.spot("core", 1, (0.0, 0.0, 0.0), face=(-1, 0), props={"keep_panels": 1})
    S.spot("ammo", 1, (-22.5, 0.0, -8.0))
    S.spot("ammo", 2, (-22.5, 0.0, 8.0))
    S.spot("ammo", 3, (-19.0, 0.0, 4.5))
    S.spot("ammo", 4, (19.0, 0.0, -4.5))
    S.spot("loot", 1, (21.5, 0.0, -9.0))
    S.zone("trigger", "boss", (FIELD[0], 0.0, FIELD[2]), (FIELD[1], ARENA_H, FIELD[3]))
    for z0, z1 in ((-9.6, -7.0), (-6.0, -3.0), (-2.0, 2.0), (3.0, 6.0), (7.0, 9.6)):
        S.corridors.append({"name": f"aisle_{z0:+.0f}", "min": [FIELD[0], 0.0, z0], "max": [FIELD[1], 0.0, z1]})
    restricted(S, ARENA_H)
    S.label("panel field (pit 8 m under)", 0.0, -4.5, "note")
    return finish(S, pitch=2.0)


def control_room():
    S = Scene("control_room", "Control room and cell", "20.4 m by 10.4 m: an antechamber from the arena, the control room with its single chair "
              "facing a wall of monitors, and the cell beside it, a puzzle room you solve to leave", mood="dim, the monitors' glow, watched")
    S.spaces = [
        sp("antechamber", -10.0, -6.0, -1.4, 1.4, 3.0, kind="corridor", f="server_floor", w="server_green", label=""),
        sp("control", -5.8, 6.0, -5.0, 5.0, 3.0, f="server_floor", w="server_green", label="control room"),
        sp("cell", 6.2, 10.2, -2.0, 2.0, 2.8, f="cell", w="cell", label="cell"),
    ]
    S.openings = [op(-6.0, -5.8, -0.8, 0.8, 2.4),
                  op(6.0, 6.2, -0.6, 0.6, 2.2, leaf=("cell", (1, 0)), props={"locked": 1, "puzzle": "cell", "opens_from": "inside"}),
                  op(6.0, 6.2, 1.0, 1.8, 2.0, sill=1.0)]
    carve(S)
    S.zone("trigger", "cell", (6.2, 0.0, -2.0), (10.2, 2.8, 2.0))
    edge_link(S, "registrar_hall", "W", 0.0, -10.0, "registrar_hall", fore=True)
    S.solid("Chair_control", (-0.4, 0.0, 1.6), (0.4, 1.0, 2.4), "chair", props={"single_chair": 1})
    block(S, "Monitors", -4.0, 4.0, -5.0, -4.4, 2.6)
    block(S, "Console", -3.0, 3.0, -3.6, -2.8, 0.95, cover="half")
    block(S, "Cabinet", -5.8, -5.0, 2.6, 4.4, 2.0, cover="full")
    block(S, "Breaker", 5.6, 6.0, -4.0, -3.0, 2.0, props={"circuit": "R5"})
    block(S, "Bunk", 8.4, 10.2, 1.4, 2.0, 0.5)
    S.spot("chair", 1, (0.0, 0.0, 3.0), face=(0, -1), props={"single_chair": 1})
    S.spot("admin", 1, (0.0, 0.0, -2.2), face=(0, -1), props={"unlock": "admin_access"})
    S.spot("breaker", "R5", (5.0, 0.0, -3.5), face=(1, 0), props={"circuit": "R5", "cuts": "control_room"})
    for n, (x, z, what) in enumerate([(7.2, -1.2, "vent grate"), (9.4, 0.6, "loose tile"), (9.4, -1.2, "code panel")], 1):
        S.spot("puzzle", n, (x, 0.0, z), props={"room": "cell", "part": what})
    S.spot("filed", 1, (7.4, 0.0, 1.0), props={"phase": 2, "room": "cell"})
    agent(S, 1, 4.5, 3.6, face=(-1, 0), role="guard")
    S.spot("ammo", 1, (-4.4, 0.0, 4.0))
    S.spot("loot", 1, (4.6, 0.0, -1.6))
    cam(S, 5.7, 4.7, (-1, -1), "R5")
    cam(S, -5.5, -4.7, (1, 1), "R5")
    cam(S, 9.9, -1.7, (-1, 1), "R5", h=2.8)
    restricted(S)
    return finish(S)


def flight(S, name, lane0, lane1, start, direction, axis, y_start, y_end, n, tread, mat="concrete"):
    """n steps from a floor at y_start up to y_end, one box per step (each as thick as its rise). axis 'x': the steps run along x from
    `start` in `direction` (+1/-1), across z in [lane0, lane1]; axis 'z' likewise."""
    rise = (y_end - y_start) / n
    assert 0 < rise <= MAX_RISE + 1e-9, (name, rise)
    for i in range(n):
        a, b = start + direction * i * tread, start + direction * (i + 1) * tread
        top = y_start + rise * (i + 1)
        lo, hi = min(a, b), max(a, b)
        if axis == "z":
            S.solid(f"Step_{name}_{i:02d}", (lane0, top - rise, lo), (lane1, top, hi), mat)
        else:
            S.solid(f"Step_{name}_{i:02d}", (lo, top - rise, lane0), (hi, top, lane1), mat)
    S.flights.append({"name": name, "y_start": y_start, "y_end": y_end, "n": n, "rise": round(rise, 4), "tread": tread})


SCENES = {"service_entry": service_entry, "hidden_entry": hidden_entry, "b2_entry": b2_entry, "checkpoint_1": checkpoint_1,
          "corridors_a": corridors_a, "labs_a": labs_a, "breaker_room": breaker_room, "checkpoint_2": checkpoint_2, "corridors_b": corridors_b,
          "labs_b": labs_b, "checkpoint_3": checkpoint_3, "registrar_hall": registrar_hall, "control_room": control_room}

# Every link between two scenes of this area: (scene, door) <-> (scene, door), the connector, the card it needs (0: none) and a note.
PAIRS = [
    (("service_entry", "checkpoint_1"), ("checkpoint_1", "service_entry"), "doors", 0, "the dock hall's south door into the outer hall"),
    (("b2_entry", "checkpoint_1"), ("checkpoint_1", "b2_entry"), "doors", 0, "the scan room's east door into the outer hall"),
    (("checkpoint_1", "corridors_a"), ("corridors_a", "checkpoint_1"), "doors", 1, "the tier-1 door, north out of the inner hall"),
    (("hidden_entry", "corridors_a"), ("corridors_a", "hidden_entry"), "doors", 0, "the storeroom's maintenance door: no card, so the hidden "
     "entry skips checkpoint 1"),
    (("corridors_a", "labs_a_west"), ("labs_a", "corridors_a_west"), "doors", 0, "north corridor, west door"),
    (("corridors_a", "labs_a_east"), ("labs_a", "corridors_a_east"), "doors", 0, "north corridor, east door"),
    (("corridors_a", "breaker_room"), ("breaker_room", "corridors_a"), "doors", 0, "the west corridor's door"),
    (("corridors_a", "checkpoint_2"), ("checkpoint_2", "corridors_a"), "doors", 0, "the east corridor's north door"),
    (("checkpoint_2", "corridors_b"), ("corridors_b", "checkpoint_2"), "doors", 2, "the tier-2 door out of the vestibule"),
    (("labs_a", "labs_b"), ("labs_b", "labs_a"), "doors", 2, "a tier-2 door between the labs: the second way into Corridors B's side"),
    (("breaker_room", "corridors_b"), ("corridors_b", "breaker_room"), "doors", 2, "a tier-2 door: the breaker room joins the two corridor "
     "sections"),
    (("corridors_b", "labs_b_west"), ("labs_b", "corridors_b_west"), "doors", 0, "north corridor, west door"),
    (("corridors_b", "labs_b_east"), ("labs_b", "corridors_b_east"), "doors", 0, "north corridor, east door"),
    (("corridors_b", "checkpoint_3"), ("checkpoint_3", "corridors_b"), "doors", 0, "the east end of the ladder"),
    (("checkpoint_3", "registrar_hall"), ("registrar_hall", "checkpoint_3"), "doors", 3, "the tier-3 vault door into the arena's west landing"),
    (("registrar_hall", "control_room"), ("control_room", "registrar_hall"), "doors", 0, "the door under the control room's window"),
]

# Links that leave this area: (scene, door): (connector, link ids, the other side). The coordinator wires them; nothing here edits the manifest.
OUTSIDE = {
    ("service_entry", "freight_lift"): ("service_corridor", "reused: grocery.backhouse>secret_ops (planned, needs keycard_tier_1); new: "
                                        "secret_ops.service_entry>grocery for the ride back",
                                        "grocery back_of_house (planned, not built): its freight lift. Into service_entry: arrive "
                                        "(0, 0, -8.2) facing (0, 1), in the car"),
    ("service_entry", "pool_dive"): ("pool_dive", "reused: intern.pool_dive>secret_ops (planned, one way)",
                                     "the Intern's escape (intern S8_H, built as a game): you surface in the pool and climb out at "
                                     "(-12.2, 0, 2.3) facing (0, -1), along the pool. The F side (diving back) stays shut until swimming exists"),
    ("hidden_entry", "repeating_room"): ("gate", "reused: rdwe.repeating_room>secret_ops (planned); new: secret_ops.hidden_entry>rdwe back",
                                         "rdwe repeating_room (planned, RDWE's phase B). Into hidden_entry: arrive (-1.6, 0, 0) facing (1, 0)"),
    ("b2_entry", "laboratory"): ("doors", "new: lab.laboratory>secret_ops (needs a keycard, see the open questions) and secret_ops.b2_entry>lab",
                                 "laboratory (built): the sealed B2 door on its north wall (shared/lab.js LAB.b2, (0, -6); F within 1.6 m of "
                                 "(0, -5.4)); back in the lab you stand at (0, 0, -4.6) facing (0, 1). Into b2_entry: arrive (0, 0, -1.4) "
                                 "facing (0, -1)"),
}
ENTRIES = ["service_entry", "hidden_entry", "b2_entry"]

# What each scene must have, by name: (prefix or exact name, at least how many). Checked on the exported files (and the model for the GLB parts).
REQUIRED = {
    "breaker_room": [("Spot_breaker_", 3)],
    "control_room": [("Chair_control", 1), ("DoorLeaf_cell", 1), ("Spot_puzzle_", 3), ("Spot_chair_", 1), ("Zone_trigger_cell", 1),
                     ("Spot_admin_", 1)],
    "registrar_hall": [("Rack_", 40), ("FloorPanel_", 200), ("SecCam_", 12), ("Spot_breaker_", 4), ("CeilingPanel_", 1), ("Zone_hazard_pit", 1),
                       ("Spot_core_", 1), ("Spot_agent_", 4)],
    "checkpoint_1": [("Spot_reader_", 1)], "checkpoint_2": [("Spot_reader_", 1)], "checkpoint_3": [("Spot_reader_", 1)],
    "service_entry": [("Zone_water_pool", 1)],
}
OPEN_ENDED = ["corridors_a", "corridors_b", "labs_a", "labs_b"]


def build(sid):
    return SCENES[sid]()


def plan_views(S):
    """The plan to render: the scene with a 2 m margin, about 1700 px on its long side (the Blender render and the sheets share this)."""
    xs = [v for s in S.spaces for v in (s["x0"] - T, s["x1"] + T)]
    zs = [v for s in S.spaces for v in (s["z0"] - T, s["z1"] + T)]
    m = 2.0
    return [_view("L0", 0.0, min(xs) - m, max(xs) + m, min(zs) - m, max(zs) + m, 1700.0)]


def _view(key, lv, x0, x1, z0, z1, ppm_target):
    span = max(x1 - x0, z1 - z0)
    ppm = ppm_target / span
    return {"key": key, "level": lv, "x0": x0, "x1": x1, "z0": z0, "z1": z1, "W": int(round((x1 - x0) * ppm)), "H": int(round((z1 - z0) * ppm)), "ppm": ppm}


def plan_hidden(S, b, level):
    """Is box b left out of the plan? (ceilings, lintels, the camera rigs and anything that starts 2.4 m or more above the floor)"""
    if b["tags"] & {"ceiling", "lintel", "camera"}:
        return True
    return b["min"][1] >= level + 2.4


# ---------------------------------------------------------------- the layout file as the exporter writes it, from the model alone (--preview)
def _r(v):
    return round(v, 3) + 0.0


def _face(f):
    if not f:
        return [0.0, 1.0]
    ln = math.hypot(*f) or 1.0
    return [_r(f[0] / ln), _r(f[1] / ln)]


def doc_of(S):
    out = {"scene": S.id, "colliders": [], "doors": [], "cameras": [], "markers": [], "links": [], "zones": [], "spots": []}
    empt = {e["name"]: e for e in S.empties}
    items = sorted([("C", b["name"], b) for b in S.boxes if b.get("zone")] + [("E", e["name"], e) for e in S.empties]
                   + [("D", d["name"], d) for d in S.doors] + [("K", "COL_" + b["name"], b) for b in S.boxes if b["col"]]
                   + [("A", c["name"], c) for c in S.cams], key=lambda t: t[1])
    for kind, n, o in items:
        if kind == "K":
            out["colliders"].append({"s": o["name"], "min": [_r(v) for v in o["min"]], "max": [_r(v) for v in o["max"]]})
        elif kind == "C":
            out["zones"].append({"kind": o["zone"], "name": n, "min": [_r(v) for v in o["min"]], "max": [_r(v) for v in o["max"]]})
        elif kind == "A":
            f = _face(o["face"])
            c = {"id": n, "level": S.id, "position": [_r(v) for v in o["pos"]], "facing_deg": round(math.degrees(math.atan2(f[0], f[1])), 1) + 0.0}
            for k, v in o["props"].items():
                if k not in c:
                    c[k] = v
            out["cameras"].append(c)
        elif kind == "D":
            p = o["props"]
            d = {"name": n, "level": S.id, "hinge": [_r(v) for v in o["hinge"]], "width": float(p["width"]), "height": float(p["height"]),
                 "closed_yaw_deg": float(p["closed_yaw_deg"]), "swing_deg": float(p["swing_deg"]), "state": p["state"]}
            for k, v in p.items():
                if k not in d:
                    d[k] = v
            out["doors"].append(d)
        elif kind == "E":
            if n.startswith("Link_"):
                a = empt["Arrive_" + n[5:]]
                out["links"].append({"door": n[5:], "at": [_r(v) for v in o["pos"]], "arrive": [_r(v) for v in a["pos"]], "face": _face(a["face"])})
            elif n.startswith("Spot_"):
                f = _face(o["face"])
                sp_ = {"kind": n.split("_")[1], "name": n, "position": [_r(v) for v in o["pos"]], "face": f,
                       "yaw_deg": round(math.degrees(math.atan2(f[0], f[1])), 1) + 0.0, "scale": float(o["props"].get("scale", 1.0))}
                for k, v in o["props"].items():
                    if k not in sp_:
                        sp_[k] = v
                out["spots"].append(sp_)
    return out


def out_path(base, sid):
    return Path(base) / "world" / f"{sid}.json"


# ---------------------------------------------------------------- the gates on exported files (--check)
def _overlap(a, b, e=0.005):
    return all(a["min"][i] < b["max"][i] - e and a["max"][i] > b["min"][i] + e for i in range(3))


def walk_grid(S, cols):
    """The cells a walker can stand in at floor level: inside a space or a doorway, a collider's top within 6 cm of y 0 under the cell's
    centre, and no collider between knee and head within WALKER_R of it."""
    inside, opn = interior(S)
    cand = set(inside) | {c for c, o in opn.items() if o["sill"] == 0}
    floor, block_ = set(), set()
    for c in cols:
        i0, i1, j0, j1 = c["min"][0] * Q, c["max"][0] * Q, c["min"][2] * Q, c["max"][2] * Q
        if abs(c["max"][1]) <= 0.06:
            for i in range(int(math.floor(i0 - 0.5)), int(math.ceil(i1 + 0.5))):
                for j in range(int(math.floor(j0 - 0.5)), int(math.ceil(j1 + 0.5))):
                    if i0 <= i + 0.5 <= i1 and j0 <= j + 0.5 <= j1:
                        floor.add((i, j))
        if c["min"][1] < 1.5 and c["max"][1] > 0.5:
            r = WALKER_R * Q
            for i in range(int(math.floor(i0 - r - 1)), int(math.ceil(i1 + r + 1))):
                for j in range(int(math.floor(j0 - r - 1)), int(math.ceil(j1 + r + 1))):
                    if i0 - r < i + 0.5 < i1 + r and j0 - r < j + 0.5 < j1 + r:
                        block_.add((i, j))
    return {c for c in cand if c in floor and c not in block_}


def components(cells):
    comp, k = {}, 0
    for c in cells:
        if c in comp:
            continue
        k += 1
        todo = [c]
        comp[c] = k
        while todo:
            i, j = todo.pop()
            for n in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if n in cells and n not in comp:
                    comp[n] = k
                    todo.append(n)
    return comp, k


def cell_of(p):
    return (int(math.floor(p[0] * Q)), int(math.floor(p[2] * Q)))


def holes(walk, min_len):
    """Blocks the walkable cells go all the way round (each a loop: two routes past it) at least min_len m long; their lengths."""
    i0, i1 = min(c[0] for c in walk) - 1, max(c[0] for c in walk) + 1
    j0, j1 = min(c[1] for c in walk) - 1, max(c[1] for c in walk) + 1
    rest = {(i, j) for i in range(i0, i1 + 1) for j in range(j0, j1 + 1)} - walk
    comp, k = components(rest)
    size, edge = {}, set()
    for (i, j), n in comp.items():
        size[n] = size.get(n, 0) + 1
        if i in (i0, i1) or j in (j0, j1):
            edge.add(n)
    ext = {}
    for (i, j), n in comp.items():
        e = ext.setdefault(n, [i, i, j, j])
        e[0], e[1], e[2], e[3] = min(e[0], i), max(e[1], i), min(e[2], j), max(e[3], j)
    return sorted(round(max(ext[n][1] - ext[n][0], ext[n][3] - ext[n][2]) / Q + 0.1, 1) for n in size
                  if n not in edge and max(ext[n][1] - ext[n][0], ext[n][3] - ext[n][2]) / Q + 0.1 >= min_len)


def longest_run(walk):
    best = 0
    for axis in (0, 1):
        lines = {}
        for c in walk:
            lines.setdefault(c[1 - axis], []).append(c[axis])
        for v in lines.values():
            v.sort()
            run = 1
            for a, b in zip(v, v[1:]):
                run = run + 1 if b == a + 1 else 1
                best = max(best, run)
    return best / Q


def check(base, ids=None, against=None):
    """Prints one line per gate; True if all pass."""
    ids = ids or list(SCENES)
    docs, bad = {}, []
    for sid in ids:
        f = out_path(base, sid)
        if not f.exists():
            bad.append(f"missing {f}")
            continue
        docs[sid] = json.loads(f.read_text())
    models = {sid: build(sid) for sid in ids}
    # ---- links both ways, and the graph
    have = {(sid, l["door"]) for sid, d in docs.items() for l in d.get("links", [])}
    paired = set()
    for a, b, kind, card, note in PAIRS:
        for side in (a, b):
            paired.add(side)
            if side[0] in docs and side not in have:
                bad.append(f"link {side[0]}.{side[1]} ({kind} to {b if side == a else a}) is not in {side[0]}.json")
        ka, kb = models[a[0]].links.get(a[1]), models[b[0]].links.get(b[1])
        if ka and kb and (max(ka[2], kb[2]) != card or min(ka[2], kb[2]) not in (0, card)):
            bad.append(f"link {a} <-> {b}: keycard {ka[2]} / {kb[2]}, the pair says {card}")
        if ka and ka[0].split()[0] != b[0]:
            bad.append(f"link {a[0]}.{a[1]} says it goes to {ka[0]}, the pair says {b[0]}")
    for side in sorted(have):
        if side not in paired and side not in OUTSIDE:
            bad.append(f"link {side[0]}.{side[1]} has no other side in PAIRS or OUTSIDE")
    for side in OUTSIDE:
        if side[0] in docs and side not in have:
            bad.append(f"link {side[0]}.{side[1]} (off this area) is not in {side[0]}.json")
    print(f"GATE links: {len(PAIRS)} pairs inside the area ({len(PAIRS) * 2} sides, each in its file), {len(OUTSIDE)} that leave it; "
          f"{len(have)} links in the files, every one accounted for")
    graph = {sid: set() for sid in SCENES}
    for (a, _), (b, _), *_ in PAIRS:
        graph[a].add(b)
        graph[b].add(a)
    for e in ENTRIES:
        seen, todo = set(), [e]
        while todo:
            s = todo.pop()
            if s not in seen:
                seen.add(s)
                todo += list(graph[s])
        if set(SCENES) - seen:
            bad.append(f"from {e} not reachable: {sorted(set(SCENES) - seen)}")
    print(f"GATE graph: every one of the {len(SCENES)} scenes is reached from each of the {len(ENTRIES)} entries ({', '.join(ENTRIES)})")
    # ---- overlaps: no two colliders share volume (1 cm slack: the files are rounded to the millimetre)
    nover, ncol = 0, 0
    for sid, d in docs.items():
        cols = d["colliders"]
        ncol += len(cols)
        cs = sorted(cols, key=lambda c: c["min"][0])
        for i, a in enumerate(cs):
            for b in cs[i + 1:]:
                if b["min"][0] >= a["max"][0] - 0.005:
                    break
                if _overlap(a, b):
                    nover += 1
                    if nover <= 12:
                        bad.append(f"overlap {sid}: {a['s']} and {b['s']}")
    print(f"GATE overlaps: {ncol} colliders in {len(docs)} files, {nover} pairs share volume")
    # ---- clearances: corridors, doorways, ceilings, steps; every link, arrival and spot on one walkable piece of floor
    ncor, narrow, nop, slim, nwalk = 0, 99.0, 0, 99.0, 0
    for sid, d in docs.items():
        S, cols = models[sid], d["colliders"]
        for c in S.corridors:
            ncor += 1
            w = min(c["max"][0] - c["min"][0], c["max"][2] - c["min"][2])
            narrow = min(narrow, w)
            if w < MIN_CORRIDOR - 1e-6:
                bad.append(f"corridor {sid}/{c['name']} is {w:.2f} m wide")
            for k in cols:
                e = 0.005
                if k["min"][1] < 1.5 and k["max"][1] > 0.5 and k["min"][0] < c["max"][0] - e and k["max"][0] > c["min"][0] + e \
                        and k["min"][2] < c["max"][2] - e and k["max"][2] > c["min"][2] + e:
                    bad.append(f"corridor {sid}/{c['name']}: {k['s']} stands in it")
                    break
        for o in S.openings:
            if o["sill"] > 0:
                continue
            nop += 1
            w = max(o["x1"] - o["x0"], o["z1"] - o["z0"])
            slim = min(slim, w)
            if w < MIN_OPENING - 1e-6 or o["top"] < DOOR_H + 0.03:
                bad.append(f"doorway {sid} at ({o['x0']}, {o['z0']}): {w:.2f} m wide, {o['top']} m high")
        for s in S.spaces:
            if not (H_ROOM[0] - 1e-6 <= s["h"] <= H_ROOM[1] + 1e-6) and "tall" not in s["tags"]:
                bad.append(f"ceiling {sid}/{s['name']}: {s['h']} m")
        for fl in S.flights:
            steps = sorted((c["s"], c) for c in cols if c["s"].startswith(f"Step_{fl['name']}_"))
            tops = [fl["y_start"]] + [c["max"][1] for _, c in steps]
            if len(steps) != fl["n"] or any(abs(b - a) > MAX_RISE + 1e-6 for a, b in zip(tops, tops[1:])) or abs(tops[-1] - fl["y_end"]) > 1e-6:
                bad.append(f"steps {sid}/{fl['name']}: {len(steps)} boxes, tops {tops}")
        walk = walk_grid(S, cols)
        comp, _ = components(walk)
        pts = [(f"link {l['door']} at", l["at"]) for l in d["links"]] + [(f"link {l['door']} arrive", l["arrive"]) for l in d["links"]] \
            + [(s["name"], s["position"]) for s in d["spots"]]
        groups = set()
        for what, p in pts:
            c = cell_of(p)
            if c not in walk:
                bad.append(f"{sid}: {what} {p} is not on walkable floor (blocked, or no floor under it)")
            else:
                groups.add(comp[c])
                nwalk += 1
        if len(groups) > 1:
            bad.append(f"{sid}: the links and spots are on {len(groups)} separate pieces of floor")
    print(f"GATE clearances: {ncor} corridor and aisle rects, the narrowest {narrow:.2f} m (at least {MIN_CORRIDOR} m), none blocked; "
          f"{nop} doorways, the narrowest {slim:.2f} m (at least {MIN_OPENING} m) and {DOOR_H + 0.03:.2f} m high or more; ceilings "
          f"{H_ROOM[0]} to {H_ROOM[1]} m but the spaces marked tall (the dock 4 m, the arena 7 m); steps at most {MAX_RISE} m")
    nar, worst = 0, 99.0
    for sid, d in docs.items():
        walk = walk_grid(models[sid], d["colliders"])
        for l in d["links"]:
            t = clear_ahead(walk, l["arrive"], l["face"])
            nar += 1
            worst = min(worst, t)
            if t < 2.0:
                bad.append(f"{sid}: arriving by {l['door']} you face a wall {t:.1f} m away")
    print(f"GATE arrivals: {nar} arrivals, each with at least 2 m clear ahead (the least {worst:.1f} m): side doors into a corridor look along it")
    print(f"GATE walkable: {nwalk} links, arrivals and spots each on floor a walker (r {WALKER_R} m) can stand on, and in each scene all on one "
          f"connected piece of it (doors count as open)")
    # ---- open-ended: more than one route
    for sid in OPEN_ENDED:
        if sid not in docs:
            continue
        walk = walk_grid(models[sid], docs[sid]["colliders"])
        hs = holes(walk, 6.0)
        nl = len(docs[sid]["links"])
        print(f"  {sid}: {nl} links; {len(hs)} loops round blocks {', '.join(f'{h:g}' for h in hs)} m long")
        if nl < 3 or not hs:
            bad.append(f"{sid}: not open-ended ({nl} links, {len(hs)} loops)")
    print(f"GATE routes: {', '.join(OPEN_ENDED)} each have at least 3 links and at least one loop round a block 6 m long or more (a wall, a "
          f"bench row, a lab), so there is more than one way through")
    # ---- required objects, the panel grid, the arena's walls, cameras and breakers
    for sid, req in REQUIRED.items():
        if sid not in docs:
            continue
        d, S = docs[sid], models[sid]
        names = [c["s"] for c in d["colliders"]] + [x["name"] for x in d["doors"]] + [x["name"] for x in d["spots"]] \
            + [x["name"] for x in d["zones"]] + [x["id"] for x in d["cameras"]] + [b["name"] for b in S.boxes if b["art"]]
        for pre, n in req:
            got = len({x for x in names if x == pre or (pre.endswith("_") and x.startswith(pre))})
            if got < n:
                bad.append(f"{sid}: {got} {pre}* (needs {n})")
    if "control_room" in docs:
        chairs = [c for c in docs["control_room"]["colliders"] if c["s"].startswith("Chair")]
        if len(chairs) != 1:
            bad.append(f"control_room: {len(chairs)} chairs (one, single)")
    print(f"GATE required: " + "; ".join(f"{sid}: " + ", ".join(f"{p}*>={n}" for p, n in req) for sid, req in REQUIRED.items())
          + "; the control room has exactly one chair")
    if "registrar_hall" in docs:
        d = docs["registrar_hall"]
        nx, nz = int((FIELD[1] - FIELD[0]) / PANEL), int((FIELD[3] - FIELD[2]) / PANEL)
        pan = {c["s"]: c for c in d["colliders"] if c["s"].startswith("FloorPanel_")}
        miss = [f"{i:02d}_{j:02d}" for i in range(nx) for j in range(nz) if f"FloorPanel_{i:02d}_{j:02d}" not in pan]
        area = sum((c["max"][0] - c["min"][0]) * (c["max"][2] - c["min"][2]) for c in pan.values())
        off = [n for n, c in pan.items() if abs(c["max"][1]) > 1e-6 or c["min"][0] < FIELD[0] - 1e-6 or c["max"][0] > FIELD[1] + 1e-6
               or c["min"][2] < FIELD[2] - 1e-6 or c["max"][2] > FIELD[3] + 1e-6]
        others = [c["s"] for c in d["colliders"] if not c["s"].startswith("FloorPanel_") and abs(c["max"][1]) < 0.06
                  and c["min"][0] < FIELD[1] - 0.005 and c["max"][0] > FIELD[0] + 0.005 and c["min"][2] < FIELD[3] - 0.005 and c["max"][2] > FIELD[2] + 0.005]
        full = abs(area - (FIELD[1] - FIELD[0]) * (FIELD[3] - FIELD[2])) < 1e-3
        if miss or off or others or not full or len(pan) != nx * nz:
            bad.append(f"panel grid: missing {miss[:6]}, off {off[:6]}, other floor in the field {others[:6]}, area {area}")
        print(f"GATE panel grid: {len(pan)} of {nx} x {nz} FloorPanel_<x>_<z>, {PANEL:g} m each, tiling the field x {FIELD[0]:g} to {FIELD[1]:g}, "
              f"z {FIELD[2]:g} to {FIELD[3]:g} exactly ({area:.0f} m^2, no gap, no overlap, no other floor in it), tops at y 0, the pit 8 m under")
        racks = [c for c in d["colliders"] if c["s"].startswith("Rack_")]
        stand = [r for r in racks if not any(abs(p["max"][1] - r["min"][1]) < 1e-6 and p["min"][0] < r["max"][0] and p["max"][0] > r["min"][0]
                                             and p["min"][2] < r["max"][2] and p["max"][2] > r["min"][2] for p in pan.values())]
        if stand:
            bad.append(f"racks not on panels: {[r['s'] for r in stand][:5]}")
        walls = {"N": 0, "S": 0, "W": 0, "E": 0}
        for c in d["cameras"]:
            x, _, z = c["position"]
            k = "N" if z < -9.5 else "S" if z > 9.5 else "W" if x < -23.5 else "E" if x > 22.5 else None
            if k:
                walls[k] += 1
        if min(walls.values()) < 1:
            bad.append(f"arena cameras by wall {walls}")
        print(f"GATE arena: {len(racks)} Rack_<n> (each its own object, standing on panels), cameras on every wall ({', '.join(f'{k} {v}' for k, v in walls.items())})")
    ncam, circ = 0, {}
    brk = {}
    for sid, d in docs.items():
        for s in d["spots"]:
            if s["kind"] == "breaker":
                brk[s["circuit"]] = [x for x in str(s["cuts"]).split(",")]
    for sid, d in docs.items():
        S = models[sid]
        restr = any(z["kind"] == "restricted" for z in d["zones"])
        if restr and not d["cameras"]:
            bad.append(f"{sid}: restricted, no cameras")
        if d["cameras"] and not restr:
            bad.append(f"{sid}: cameras but not restricted")
        rigs = {b["name"] for b in S.boxes if "camera" in b["tags"]}
        for c in d["cameras"]:
            ncam += 1
            if c.get("rig") not in rigs:
                bad.append(f"{sid}: {c['id']} has no rig object")
            cc = c.get("circuit")
            circ.setdefault(cc, set()).add(sid)
            if cc not in brk or sid not in brk[cc]:
                bad.append(f"{sid}: {c['id']} is on circuit {cc}, which no breaker cuts here")
            for k in ("pan", "tilt", "zoom", "loop_seconds"):
                if k not in c:
                    bad.append(f"{sid}: {c['id']} has no {k}")
    for cc, scenes in brk.items():
        for s in scenes:
            if s in docs and s not in circ.get(cc, set()):
                bad.append(f"breaker {cc} cuts {s}, which has no camera on it")
    print(f"GATE cameras: {ncam} SecCam_<nn> in {sum(1 for d in docs.values() if d['cameras'])} restricted scenes (every restricted scene has "
          f"them, hidden_entry none), each with its own rig object, pan, tilt and zoom; every one on a circuit a breaker cuts: "
          + ", ".join(f"{c} {len(circ.get(c, ()))} scenes" for c in sorted(brk)))
    # ---- shooter readability: spawns kept off the arrivals, cover, ammo, sightlines
    lines = []
    for sid, d in docs.items():
        S = models[sid]
        arr = {l["door"]: l["arrive"] for l in d["links"]}
        agents = [s for s in d["spots"] if s["kind"] == "agent"]
        for a in agents:
            for door, p in arr.items():
                need = FORE_MIN if S.links[door][1] else BACK_MIN
                dd = math.hypot(a["position"][0] - p[0], a["position"][2] - p[2])
                if dd < need - 1e-6:
                    bad.append(f"{sid}: {a['name']} is {dd:.1f} m from the arrival by {door} (at least {need:g})")
        cover = [b for b in S.boxes if "cover" in b["tags"]]
        ammo = [s for s in d["spots"] if s["kind"] == "ammo"]
        if agents and (not ammo or not cover):
            bad.append(f"{sid}: agents with {len(ammo)} ammo spots and {len(cover)} cover")
        walk = walk_grid(S, d["colliders"])
        lr = longest_run(walk)
        nf = sum(1 for b in cover if "cover_full" in b["tags"])
        lines.append(f"  {sid}: {len(agents)} agents, {len(S.patrols)} patrol routes, cover {nf} full / {len(cover) - nf} half, ammo {len(ammo)}, "
                     f"loot {sum(1 for s in d['spots'] if s['kind'] == 'loot')}, longest straight line {lr:.1f} m")
    print(f"GATE shooter: every agent spawn at least {FORE_MIN:g} m from the arrivals going deeper and {BACK_MIN:g} m from those coming back; "
          f"every scene with agents has cover and ammo")
    for ln in lines:
        print(ln)
    # ---- the Blender export against the preview
    if against:
        diffs = 0
        for sid in ids:
            g = out_path(against, sid)
            if not g.exists() or sid not in docs:
                bad.append(f"compare: {g} missing")
                continue
            a, b = docs[sid], json.loads(g.read_text())
            dd = _diff(a, b)
            if dd:
                diffs += 1
                bad.append(f"compare {sid}: {dd[:3]}")
        print(f"GATE export: the {len(ids)} files match {against} (the model's preview) to the millimetre: {len(ids) - diffs} of {len(ids)}")
    nsp = {}
    for d in docs.values():
        for s in d.get("spots", []):
            nsp[s["kind"]] = nsp.get(s["kind"], 0) + 1
    print("  spots: " + ", ".join(f"{k} x{v}" for k, v in sorted(nsp.items())))
    for b in bad:
        print("  FAIL", b)
    print("GATES", "FAIL" if bad else "PASS")
    return not bad


def _diff(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        out = [f"{path}.{k}: only on one side" for k in set(a) ^ set(b)]
        for k in set(a) & set(b):
            out += _diff(a[k], b[k], f"{path}.{k}")
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}: {len(a)} vs {len(b)} items"]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += _diff(x, y, f"{path}[{i}]")
        return out
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return [] if abs(a - b) <= 0.0011 else [f"{path}: {a} vs {b}"]
    return [] if a == b else [f"{path}: {a!r} vs {b!r}"]


# ================================================================ Blender
def _blender_main(argv):
    import bpy
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import export_scene
    from mathutils import Matrix, Vector

    a = argv
    ids = list(SCENES) if "--scenes" not in a or a[a.index("--scenes") + 1] == "all" else a[a.index("--scenes") + 1].split(",")
    base = Path(a[a.index("--out") + 1]) if "--out" in a else ROOT / "work/secretops_greybox"
    if not base.is_absolute():
        base = ROOT / base
    render = "--no-render" not in a
    for sub in ("world", "glb", "renders"):
        (base / sub).mkdir(parents=True, exist_ok=True)

    def B(p):
        return Vector((p[0], -p[2], p[1]))

    mats, cubes = {}, {}

    def mat(name):
        if name not in mats:
            m = bpy.data.materials.new("GB_" + name)
            c = MATS[name]
            m.diffuse_color = (*c, 1.0)
            try:
                m.use_nodes = True
            except Exception:
                pass
            nt = m.node_tree
            bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf is None:
                for n in list(nt.nodes):
                    nt.nodes.remove(n)
                bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
                outn = nt.nodes.new("ShaderNodeOutputMaterial")
                nt.links.new(bsdf.outputs[0], outn.inputs[0])
            bsdf.inputs["Base Color"].default_value = (*c, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.8 if name not in ("glass", "water") else 0.04
            if name in ("glass", "water"):
                for key in ("Transmission Weight", "Transmission"):
                    if key in bsdf.inputs:
                        bsdf.inputs[key].default_value = 1.0
                        break
                if "IOR" in bsdf.inputs:
                    bsdf.inputs["IOR"].default_value = 1.05
            if name in ("lamp", "pink", "monitor"):
                for key in ("Emission Color", "Emission"):
                    if key in bsdf.inputs:
                        bsdf.inputs[key].default_value = (*c, 1.0) if name != "monitor" else (0.2, 0.5, 0.6, 1.0)
                        break
                if "Emission Strength" in bsdf.inputs:
                    bsdf.inputs["Emission Strength"].default_value = 0.6
            mats[name] = m
        return mats[name]

    def cube(mname):
        """One unit cube (corner at the origin) per material: every box of that colour is this mesh, scaled."""
        if mname not in cubes:
            me = bpy.data.meshes.new("GB_cube_" + mname)
            v = [(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)]
            f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
            me.from_pydata(v, [], f)
            me.update()
            me.materials.append(mat(mname))
            cubes[mname] = me
        return cubes[mname]

    leaf_me = {}

    def leaf(mname):
        if mname not in leaf_me:
            me = bpy.data.meshes.new("GB_door_leaf_" + mname)
            v = [(x, y, z) for x in (0, 1) for y in (-0.025, 0.025) for z in (0, 1)]
            me.from_pydata(v, [], [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
            me.update()
            me.materials.append(mat(mname))
            leaf_me[mname] = me
        return leaf_me[mname]

    sc = bpy.context.scene
    coll = {}
    for cn in ("Art", "Layout"):
        c = bpy.data.collections.new(cn)
        sc.collection.children.link(c)
        coll[cn] = c

    def clear():
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        for lt in list(bpy.data.lights):
            bpy.data.lights.remove(lt)
        for cm in list(bpy.data.cameras):
            bpy.data.cameras.remove(cm)

    def boxobj(name, b, coll_name, hide=False):
        ob = bpy.data.objects.new(name, cube(b["mat"]))
        mn, mx = b["min"], b["max"]
        ob.location = (mn[0], -mx[2], mn[1])
        ob.scale = (mx[0] - mn[0], mx[2] - mn[2], mx[1] - mn[1])
        coll[coll_name].objects.link(ob)
        ob.hide_render = hide
        return ob

    def realize(S):
        clear()
        arts = []
        for b in S.boxes:
            if b.get("zone"):
                ob = boxobj(b["name"], b, "Layout", hide=True)
                ob.display_type = "WIRE"
                continue
            if b.get("art", True):
                ob = boxobj(b["name"], b, "Art")
                for k, val in b.get("props", {}).items():
                    ob[k] = val
                arts.append((ob, b))
            if b["col"]:
                ob = boxobj("COL_" + b["name"], b, "Layout", hide=True)
                ob.display_type = "WIRE"
        for d in S.doors:
            ob = bpy.data.objects.new(d["name"], leaf("keycard_door" if d["props"].get("keycard_tier") else "door"))
            ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z") @ Matrix.Diagonal((d["props"]["width"], 1, d["props"]["height"], 1))
            for k, val in d["props"].items():
                ob[k] = val
            coll["Art"].objects.link(ob)
            arts.append((ob, {"min": [0, d["hinge"][1], 0], "tags": set(), "name": d["name"]}))
        for e in S.empties + S.cams:
            ob = bpy.data.objects.new(e["name"], None)
            ob.location = B(e["pos"])
            if e["face"]:
                ob.rotation_euler = (0, 0, math.atan2(e["face"][0], e["face"][1]))
            for k, val in e["props"].items():
                ob[k] = val
            ob.empty_display_size = 0.3
            coll["Layout"].objects.link(ob)
        bpy.context.view_layer.update()
        return arts

    def setup_cycles(samples):
        sc.render.engine = "CYCLES"
        cy = sc.cycles
        cy.samples = samples
        cy.use_adaptive_sampling = True
        cy.use_denoising = True
        cy.max_bounces = 6
        cy.transmission_bounces = 6
        prefs = bpy.context.preferences.addons["cycles"].preferences
        gpu = False
        for t in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
            try:
                prefs.compute_device_type = t
                prefs.refresh_devices()
            except Exception:
                continue
            if [d for d in prefs.devices if d.type != "CPU"]:
                for d in prefs.devices:
                    d.use = d.type != "CPU"
                gpu = True
                break
        cy.device = "GPU" if gpu else "CPU"
        sc.view_settings.view_transform = "Standard"
        for attr in dir(sc.render):
            if attr.startswith("use_stamp"):
                try:
                    setattr(sc.render, attr, False)
                except Exception:
                    pass
        sc.render.image_settings.file_format = "PNG"
        return cy.device

    def world(color, strength):
        w = bpy.data.worlds.get("GB_world") or bpy.data.worlds.new("GB_world")
        try:
            w.use_nodes = True
        except Exception:
            pass
        bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
        if bg is None:
            bg = w.node_tree.nodes.new("ShaderNodeBackground")
            o = w.node_tree.nodes.new("ShaderNodeOutputWorld")
            w.node_tree.links.new(bg.outputs[0], o.inputs[0])
        bg.inputs[0].default_value = (*color, 1.0)
        bg.inputs[1].default_value = strength
        sc.world = w

    def add_light(kind, loc, power, name, rot=None, size=0.3):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = power
        if kind != "SUN":
            ld.shadow_soft_size = size
        else:
            ld.angle = math.radians(2.0)
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        if rot:
            ob.rotation_euler = rot
        sc.collection.objects.link(ob)
        return ob

    def camera(name):
        cd = bpy.data.cameras.new(name)
        ob = bpy.data.objects.new(name, cd)
        sc.collection.objects.link(ob)
        sc.camera = ob
        return ob

    def strip():
        for ob in list(bpy.data.objects):
            if ob.type in ("LIGHT", "CAMERA"):
                bpy.data.objects.remove(ob, do_unlink=True)

    def render_plan(S, arts, pv, path):
        for ob, b in arts:
            ob.hide_render = plan_hidden(S, b, pv["level"]) if "tags" in b and b.get("name") else False
        strip()
        world((1.0, 1.0, 1.0), 0.45)
        add_light("SUN", (0, 0, 50), 1.6, "Plan_Sun", rot=(math.radians(2.0), math.radians(1.0), 0))
        cam_ = camera("Plan_Cam")
        cam_.data.type = "ORTHO"
        cam_.data.ortho_scale = max(pv["x1"] - pv["x0"], pv["z1"] - pv["z0"])
        cam_.data.sensor_fit = "AUTO"
        cam_.data.clip_start, cam_.data.clip_end = 0.1, 400.0
        cam_.location = ((pv["x0"] + pv["x1"]) / 2, -(pv["z0"] + pv["z1"]) / 2, pv["level"] + 60.0)
        cam_.rotation_euler = (0, 0, 0)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = pv["W"], pv["H"], 100
        sc.cycles.samples = 24
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)

    def render_still(S, arts, path):
        for ob, b in arts:
            ob.hide_render = False
        strip()
        world((0.05, 0.05, 0.06), 1.0)                                       # indoors: a dark world, the rooms lit by their own lights
        for i, (x, y, z, p) in enumerate(S.lights):
            add_light("POINT", B((x, y, z)), p, f"L{i}", size=0.6)
        (pos, face, pitch) = S.still
        cam_ = camera("Still_Cam")
        cam_.data.lens, cam_.data.sensor_width = 16.0, 36.0
        cam_.data.clip_start, cam_.data.clip_end = 0.05, 200.0
        cam_.location = B((pos[0], pos[1] + EYE, pos[2]))
        yaw = math.atan2(face[0], face[1])                                 # the -Y (empty) convention: a camera looks down its -Z
        cam_.rotation_euler = (math.radians(90 + pitch), 0, math.pi + yaw)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1600, 900, 100
        sc.cycles.samples = 64
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)

    def export_glb(arts, path):
        bpy.ops.object.select_all(action="DESELECT")
        for ob, b in arts:
            ob.hide_render = False
            ob.select_set(True)
        bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_extras=True, export_yup=True,
                                  export_apply=False, export_materials="EXPORT", export_cameras=False, export_lights=False)

    dev = setup_cycles(48)
    print("SECRETOPS_GREYBOX device", dev, "scenes", len(ids))
    for sid in ids:
        S = build(sid)
        arts = realize(S)
        p = out_path(base, sid)
        p.parent.mkdir(parents=True, exist_ok=True)
        export_scene.write(sid, p)
        export_glb(arts, base / "glb" / f"{sid}.glb")
        if render:
            for pv in plan_views(S):
                render_plan(S, arts, pv, base / "renders" / f"{sid}_plan_{pv['key']}.png")
            render_still(S, arts, base / "renders" / f"{sid}_still.png")
        print(f"SECRETOPS_GREYBOX done {sid}: {len(S.boxes)} boxes, {len(S.doors)} doors, {len(S.empties)} empties, {len(S.cams)} cameras")
    print("SECRETOPS_GREYBOX ALL DONE")


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
        inside = True
    except ImportError:
        inside = False
    if inside:
        _blender_main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    elif "--preview" in sys.argv:
        base = Path(sys.argv[sys.argv.index("--preview") + 1])
        for sid in SCENES:
            p = out_path(base, sid)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(doc_of(build(sid)), indent=1) + "\n")
        print(f"wrote {len(SCENES)} layout files under {base}")
    elif "--check" in sys.argv:
        a = sys.argv
        sys.exit(0 if check(Path(a[a.index("--check") + 1]), against=Path(a[a.index("--against") + 1]) if "--against" in a else None) else 1)
    else:
        print(__doc__)
