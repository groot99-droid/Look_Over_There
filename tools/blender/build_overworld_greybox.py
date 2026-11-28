"""The Overworld greybox (docs/BLENDER_AREAS.md, section 4, "The Overworld"): the six Overworld scenes and the market beyond part 1's
`parking_lot` as plain grey boxes, to scale, with the names the exporter reads (COL_, DoorLeaf_, Marker_, Link_/Arrive_, Zone_, Spot_, decor_)
and the playground's moving parts as `Play_<equipment>_<part>` objects with their pivots set, so the owner can review the whole layout at once.
It follows tools/blender/build_hotel_greybox.py and tools/blender/build_mall_greybox.py.

    blender -b --factory-startup --python tools/blender/build_overworld_greybox.py -- [--scenes all|id,id,...] [--out <dir>] [--no-render]
    python tools/blender/build_overworld_greybox.py --check <dir>      the gates on exported files, no Blender (links, steps, corridors, clear
                                                                      ground, moving parts, the hills tile's edges)
    python tools/blender/build_overworld_greybox.py --preview <dir>    writes the layout files from the model alone, no Blender (for --check)

For each scene the Blender run builds the boxes into an empty file, writes <out>/world/<scene>.json through tools/blender/export_scene.py,
the greybox art to <out>/glb/<scene>.glb, a top-down orthographic plan per level or segment (<out>/renders/<scene>_plan_<key>.png, roofs and
everything 2.4 m above the level hidden) and one eye-height still (1.55 m, <out>/renders/<scene>_still.png). The labels, scale bar and sheets
are drawn afterwards by tools/blender/overworld_greybox_sheets.py from this same model.

Coordinates are GAME coordinates (metres, y up, north = -z); Blender (x, y, z) is game (x, -z, y). Every scene has its own frame with its floor
at y = 0. Two of them are sets that stay part of the lot (docs/BLENDER_AREAS.md: "It can stay part of the lot"): `table_and_chairs` and
`bus_station` are built in their own frame as their own collection and file, and ATTACH says where each goes in parking_lot's frame (floor
y 9.6, yaw 0). The lot itself is part 1's (tools/make_parking_lot.mjs over the store's Exterior model, world/parking_lot.json, shared/city.js
BUS_LOT, shared/forest.js FOREST_ROAD_LOT, index.html's table); it is read here, never written. Its side of each link is listed in OUTSIDE for
the coordinator.

Repetition reuses one mesh: every box is the same unit cube per material, scaled (colliders and art share it). Each COL_<name> box has its art
twin <name>, except the few colliders that are only ground or edge (`Ground_` slabs under a set, the hills' collision columns under the hills'
surface, and the invisible `Edge_` walls); decor_ boxes and the Play_ parts have no collider (the page moves the parts). Context boxes (ctx_:
the lot round a set, for the stills) are rendered only, never exported. Nothing here touches the manifest, index.html or shared/.
"""
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EYE = 1.55
T = 0.2                     # wall thickness
SLAB = 0.3                  # ground slab under every scene
DOOR_W, DOOR_H = 0.94, 2.16
MAX_RISE = 0.27
MIN_CORRIDOR = 1.6
WALKER_R = 0.28
LOT_Y = 9.6                 # parking_lot's floor

MATS = {                    # flat greybox colours (linear RGB); no textures. The Overworld is plastic and bright (docs/WORLD.md).
    "floor": (0.58, 0.58, 0.56), "wall": (0.30, 0.30, 0.32), "ceiling": (0.62, 0.62, 0.62), "door": (0.62, 0.36, 0.16),
    "stair": (0.50, 0.46, 0.38), "furniture": (0.55, 0.47, 0.34), "counter": (0.42, 0.33, 0.24), "rail": (0.18, 0.18, 0.2),
    "grass": (0.30, 0.62, 0.30), "hedge": (0.10, 0.36, 0.14), "paving": (0.66, 0.64, 0.60), "asphalt": (0.20, 0.20, 0.22),
    "path": (0.78, 0.70, 0.55), "rubber": (0.62, 0.22, 0.20), "sand": (0.86, 0.78, 0.52), "bark": (0.36, 0.24, 0.14),
    "leaf": (0.45, 0.78, 0.55), "pastel_leaf": (0.95, 0.62, 0.80), "timber": (0.62, 0.46, 0.26), "roof": (0.55, 0.20, 0.18),
    "steel": (0.55, 0.57, 0.60), "plastic_red": (0.85, 0.15, 0.12), "plastic_blue": (0.12, 0.35, 0.85), "plastic_yellow": (0.95, 0.80, 0.10),
    "plastic_green": (0.15, 0.70, 0.30), "plastic_white": (0.92, 0.90, 0.86), "pink": (0.97, 0.66, 0.77), "mint": (0.62, 0.88, 0.78),
    "yellow": (1.0, 0.88, 0.54), "blue": (0.61, 0.78, 1.0), "glass": (0.70, 0.85, 0.90), "sign": (0.85, 0.80, 0.55),
    "awning_a": (0.85, 0.25, 0.25), "awning_b": (0.20, 0.45, 0.85), "awning_c": (0.95, 0.70, 0.15), "awning_d": (0.55, 0.30, 0.75),
    "awning_e": (0.95, 0.45, 0.70), "awning_f": (0.25, 0.70, 0.55), "facade": (0.80, 0.74, 0.66), "fake_door": (0.40, 0.28, 0.20),
    "window": (0.35, 0.50, 0.62), "lamp": (0.95, 0.95, 0.80), "store": (0.74, 0.74, 0.72), "line": (0.95, 0.85, 0.20),
}


# ================================================================ the model (pure Python; no bpy)
class Scene:
    def __init__(s, sid, title, size, levels=(0.0,), mood=""):
        s.id, s.title, s.size, s.levels, s.mood = sid, title, size, list(levels), mood
        s.boxes, s.empties, s.doors, s.labels, s.lights, s.corridors, s.flights, s.outlines = [], [], [], [], [], [], [], []
        s.kerbs, s.parts, s.meshes, s.clear = [], [], [], []
        s.links = {}            # door id -> text (where it goes), for the plan labels
        s.still = None          # (pos, face, pitch_deg)
        s.level_names = {}
        s.segments = None       # a long scene's plan in pieces: [(key, x0, x1, z0, z1)]
        s.plan_sun = (2.0, 1.0)  # the plan's sun: degrees off straight down (the hills' plan is lit low, to show the relief)
        s.attach = None         # a set that stays part of the lot: (scene, (x, y, z), yaw_deg)
        s.plan_rect = None      # a set's plan: the part of its frame to show (x0, x1, z0, z1), the lot round it included
        s._names = set()

    def uniq(s, n):
        base, k = n, 1
        while n in s._names:
            k += 1
            n = f"{base}_{k}"
        s._names.add(n)
        return n

    def solid(s, name, mn, mx, mat="wall", tags=(), art=True):
        """A collider with its art twin; art=False is a collider only (a Ground_ slab under a set, the hills' columns, an Edge_ wall)."""
        if any(mn[i] >= mx[i] - 1e-6 for i in range(3)):
            return None
        n = s.uniq(name)
        s.boxes.append({"name": n, "min": [float(v) for v in mn], "max": [float(v) for v in mx], "mat": mat, "col": True, "art": art, "tags": set(tags)})
        return n

    def edge(s, name, mn, mx):
        return s.solid("Edge_" + name, mn, mx, "wall", art=False)

    def decor(s, name, mn, mx, mat="furniture", tags=()):
        n = s.uniq("decor_" + name)
        s.boxes.append({"name": n, "min": [float(v) for v in mn], "max": [float(v) for v in mx], "mat": mat, "col": False, "art": True, "tags": set(tags)})

    def ctx(s, name, mn, mx, mat="asphalt", tags=()):
        """Context for the stills and plans only (the lot round a set): rendered, never exported to the layout file or the GLB."""
        n = s.uniq("ctx_" + name)
        s.boxes.append({"name": n, "min": [float(v) for v in mn], "max": [float(v) for v in mx], "mat": mat, "col": False, "art": True,
                        "ctx": True, "tags": set(tags)})

    def zone(s, kind, name, mn, mx):
        n = s.uniq(f"Zone_{kind}_{name}")
        s.boxes.append({"name": n, "min": list(mn), "max": list(mx), "mat": "rubber", "col": False, "art": False, "zone": kind, "tags": set()})

    def empty(s, name, pos, face=None, props=None):
        s.empties.append({"name": s.uniq(name), "pos": [float(v) for v in pos], "face": face, "props": dict(props or {})})

    def link(s, door, at, arrive, face, to=""):
        s.empty(f"Link_{door}", at)
        s.empty(f"Arrive_{door}", arrive, face=face)
        s.links[door] = to

    def spot(s, kind, n, pos, face=(0, 1), props=None):
        s.empty(f"Spot_{kind}_{n}", pos, face=face, props=props)

    def marker(s, name, pos, kind="Spawn", props=None):
        p = {"kind": kind}
        p.update(props or {})
        s.empty(f"Marker_{name}", pos, props=p)

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

    def part(s, equipment, part, pivot, boxes, axis, motion, range_deg, props=None):
        """A moving part: Play_<equipment>_<part>, one art object (no collider) whose origin is its pivot, so the page can turn it in place.
        boxes: [(min, max, mat)] in scene coordinates. axis: the game axis it turns about (x, y or z; xz for a rocker); motion: pendulum,
        tilt, spin or rock; range_deg: how far it goes each way."""
        p = {"equipment": equipment, "part": part, "axis": axis, "motion": motion, "range_deg": float(range_deg)}
        p.update(props or {})
        n = s.uniq(f"Play_{equipment}_{part}")
        s.parts.append({"name": n, "pivot": [float(v) for v in pivot], "boxes": [([float(v) for v in a], [float(v) for v in b], m) for a, b, m in boxes],
                        "props": p})
        return n

    def mesh(s, name, verts, faces, mat):
        """An art-only mesh in scene coordinates (the hills' surface)."""
        s.meshes.append({"name": s.uniq("decor_" + name), "verts": verts, "faces": faces, "mat": mat})

    def kerb(s, box_name, y0):
        """A single step up onto something (a platform, a sandbox's boards, a base): the gate holds its rise to MAX_RISE."""
        s.kerbs.append({"name": box_name, "from": y0})

    def label(s, text, x, z, y=0.0, kind="room"):
        s.labels.append({"text": text, "x": x, "z": z, "y": y, "kind": kind})

    def light(s, x, y, z, power=250.0):
        s.lights.append((x, y, z, power))

    def corridor(s, name, x0, x1, z0, z1, y=0.0):
        s.corridors.append({"name": name, "min": [x0, y, z0], "max": [x1, y, z1]})


def wall(S, name, axis, c0, c1, a0, a1, y0, y1, holes=(), mat="wall", tags=()):
    """A wall along `axis` ('x': runs along x over [a0, a1], thick over z in [c0, c1]; 'z': runs along z, thick over x) from y0 to y1, with
    rectangular holes (h0, h1, yb, yt) in run coordinates. It becomes as few boxes as the holes allow."""
    cuts = sorted({a0, a1, *[min(max(v, a0), a1) for h in holes for v in h[:2]]})
    k = 0
    for i in range(len(cuts) - 1):
        u0, u1 = cuts[i], cuts[i + 1]
        if u1 - u0 < 1e-6:
            continue
        mid = (u0 + u1) / 2
        gaps = sorted((h[2], h[3]) for h in holes if h[0] < mid < h[1])
        spans, y = [], y0
        for yb, yt in gaps:
            if yb > y + 1e-6:
                spans.append((y, yb))
            y = max(y, yt)
        if y < y1 - 1e-6:
            spans.append((y, y1))
        for ya, yb in spans:
            k += 1
            if axis == "x":
                S.solid(f"{name}_{k}", (u0, ya, c0), (u1, yb, c1), mat, tags)
            else:
                S.solid(f"{name}_{k}", (c0, ya, u0), (c1, yb, u1), mat, tags)


def shell(S, nm, x0, x1, z0, z1, y0=0.0, h=3.0, holes=None, ceiling=True, floor=True, fmat="floor", wmat="wall", cmat="ceiling", sides="NSWE"):
    """A room: floor slab (top at y0), ceiling, and the four walls OUTSIDE the interior [x0, x1] x [z0, z1]. holes: {side: [(a, w, hh, yb)]},
    a = the hole's centre along the wall, w its width, hh its height, yb its bottom above y0 (default 0)."""
    holes = holes or {}

    def hs(side):
        return [(a - w / 2, a + w / 2, y0 + (rest[0] if rest else 0.0), y0 + (rest[0] if rest else 0.0) + hh) for a, w, hh, *rest in holes.get(side, [])]
    if floor:
        S.solid(f"{nm}_Floor", (x0 - T, y0 - SLAB, z0 - T), (x1 + T, y0, z1 + T), fmat)
    if ceiling:
        S.solid(f"{nm}_Ceiling", (x0 - T, y0 + h, z0 - T), (x1 + T, y0 + h + 0.2, z1 + T), cmat, ("ceiling",))
    if "N" in sides:
        wall(S, f"{nm}_Wall_N", "x", z0 - T, z0, x0 - T, x1 + T, y0, y0 + h, hs("N"), wmat)
    if "S" in sides:
        wall(S, f"{nm}_Wall_S", "x", z1, z1 + T, x0 - T, x1 + T, y0, y0 + h, hs("S"), wmat)
    if "W" in sides:
        wall(S, f"{nm}_Wall_W", "z", x0 - T, x0, z0, z1, y0, y0 + h, hs("W"), wmat)
    if "E" in sides:
        wall(S, f"{nm}_Wall_E", "z", x1, x1 + T, z0, z1, y0, y0 + h, hs("E"), wmat)


def flight(S, name, lane0, lane1, start, direction, axis, y_start, y_end, n, tread, mat="stair"):
    """n steps from a floor at y_start up to y_end, one box per step (each as thick as its rise, so the space under a flight stays open).
    axis 'z': the steps run along z from `start` in `direction` (+1/-1), across x in [lane0, lane1]; axis 'x' likewise."""
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


def box(S, name, x0, x1, z0, z1, y0, y1, mat="furniture", tags=()):
    return S.solid(name, (x0, y0, z0), (x1, y1, z1), mat, tags)


def single_door(S, name, side, a, c0, y=0.0, width=DOOR_W, height=DOOR_H, props=None, state="closed"):
    """One leaf in a hole on `side` (N, S, W, E) centred on `a`, hinged on the wall's inner face c0, opening into the room."""
    h = width / 2
    if side == "N":
        S.door(name, (a - h, y, c0), (1, 0), (0, 1), width=width, height=height, props=props, state=state)
    elif side == "S":
        S.door(name, (a + h, y, c0), (-1, 0), (0, -1), width=width, height=height, props=props, state=state)
    elif side == "W":
        S.door(name, (c0, y, a + h), (0, -1), (1, 0), width=width, height=height, props=props, state=state)
    else:
        S.door(name, (c0, y, a - h), (0, 1), (-1, 0), width=width, height=height, props=props, state=state)


def grounds(S, nm, x0, x1, z0, z1, mat="grass", hedge_h=1.6, gaps=None, edge_h=3.0):
    """An open-air scene's ground: the slab (Ground_<nm>, its top at y 0) over [x0 - 2, x1 + 2] x [z0 - 2, z1 + 2], a hedge round the inside of
    the edge, 1.2 m thick, with gaps {side: [(centre, width)]}, and invisible Edge_ walls round the slab's rim, so nobody walks off it. The
    hedges are the groundskeepers' (Spot_groundskeeper)."""
    gaps = gaps or {}
    S.solid(f"Ground_{nm}", (x0 - 2.0, -SLAB, z0 - 2.0), (x1 + 2.0, 0.0, z1 + 2.0), mat)
    HT = 1.2

    def hs(side):
        return [(c - w / 2, c + w / 2, 0.0, hedge_h + 1.0) for c, w in gaps.get(side, [])]
    wall(S, "Hedge_N", "x", z0 - HT, z0, x0 - HT, x1 + HT, 0.0, hedge_h, hs("N"), "hedge")
    wall(S, "Hedge_S", "x", z1, z1 + HT, x0 - HT, x1 + HT, 0.0, hedge_h, hs("S"), "hedge")
    wall(S, "Hedge_W", "z", x0 - HT, x0, z0, z1, 0.0, hedge_h, hs("W"), "hedge")
    wall(S, "Hedge_E", "z", x1, x1 + HT, z0, z1, 0.0, hedge_h, hs("E"), "hedge")
    S.edge("N", (x0 - 2.0, 0.0, z0 - 2.0), (x1 + 2.0, edge_h, z0 - 1.8))
    S.edge("S", (x0 - 2.0, 0.0, z1 + 1.8), (x1 + 2.0, edge_h, z1 + 2.0))
    S.edge("W", (x0 - 2.0, 0.0, z0 - 1.8), (x0 - 1.8, edge_h, z1 + 1.8))
    S.edge("E", (x1 + 1.8, 0.0, z0 - 1.8), (x1 + 2.0, edge_h, z1 + 1.8))


def walk_gap(S, did, side, a, c0, to, inward):
    """A walk-through gap in a hedge: the Link_ (F, or walking through it, as the forest's gap) in the gap, the Arrive_ 2.6 m inside, facing in.
    c0: the hedge's inner face; inward: +1 or -1 along the gap's axis."""
    if side in "WE":
        S.link(did, (c0 - inward * 0.6, 0.0, a), (c0 + inward * 2.6, 0.0, a), (inward, 0), to)
    else:
        S.link(did, (a, 0.0, c0 - inward * 0.6), (a, 0.0, c0 + inward * 2.6), (0, inward), to)


def facade(S, n, side, a, c0, width=7.6, height=6.0, depth=1.2, label=True):
    """A "more to come" facade that does not open (docs/WORLD.md): a front with a fake door, two windows and a MORE TO COME sign, its back
    to the edge. side: which way its front faces (N, S, W, E); c0: the line of its front; Spot_facade_<n> in front of it is where the page
    can swap in a real entrance once something is added."""
    w = width / 2
    if side == "W":
        S.solid(f"Facade_{n}", (c0, 0.0, a - w), (c0 + depth, height, a + w), "facade")
        S.decor(f"Facade_{n}_Door", (c0 - 0.05, 0.0, a - 0.6), (c0, 2.4, a + 0.6), "fake_door")
        S.decor(f"Facade_{n}_Sign", (c0 - 0.05, 2.8, a - 2.4), (c0, 3.5, a + 2.4), "sign")
        for dz in (-2.6, 2.6):
            S.decor(f"Facade_{n}_Window", (c0 - 0.04, 1.0, a + dz - 0.8), (c0, 2.2, a + dz + 0.8), "window")
        S.spot("facade", n, (c0 - 1.5, 0.0, a), face=(-1, 0), props={"opens": "no", "what": "more to come"})
        S.label("MORE TO COME", c0 - 2.6, a, kind="note")
    elif side == "S":
        S.solid(f"Facade_{n}", (a - w, 0.0, c0 - depth), (a + w, height, c0), "facade")
        S.decor(f"Facade_{n}_Door", (a - 0.6, 0.0, c0), (a + 0.6, 2.4, c0 + 0.05), "fake_door")
        S.decor(f"Facade_{n}_Sign", (a - 2.4, 2.8, c0), (a + 2.4, 3.5, c0 + 0.05), "sign")
        for dx in (-2.6, 2.6):
            S.decor(f"Facade_{n}_Window", (a + dx - 0.8, 1.0, c0), (a + dx + 0.8, 2.2, c0 + 0.04), "window")
        S.spot("facade", n, (a, 0.0, c0 + 1.5), face=(0, 1), props={"opens": "no", "what": "more to come"})
        if label:
            S.label("MORE TO COME", a, c0 + 2.6, kind="note")
    else:
        raise ValueError(side)


def keeper(S, n, pos, face, mood):
    """Spot_groundskeeper_<n>: a groundskeeper tends the hedge here, facing it. mood: watches (turns to watch you) or ignores (docs/WORLD.md)."""
    S.spot("groundskeeper", n, pos, face=face, props={"mood": mood, "what": "tends the hedge"})


def minigame(S, eq, pos, face, parts, what, zone):
    S.spot("minigame", eq, pos, face=face, props={"equipment": eq, "parts": ",".join(parts), "pays": "money", "what": what})
    S.clear.append({"equipment": eq, "rect": zone})
    S.outlines.append({"x0": zone[0], "x1": zone[1], "z0": zone[2], "z1": zone[3], "text": "clear ground"})


def lamp(S, name, x, z, h=4.5):
    S.solid(f"Lamp_{name}", (x - 0.08, 0.0, z - 0.08), (x + 0.08, h, z + 0.08), "steel")
    S.decor(f"Lamp_{name}_Head", (x - 0.3, h, z - 0.3), (x + 0.3, h + 0.25, z + 0.3), "lamp")


def bench(S, name, x0, x1, z0, z1, mat="timber"):
    S.solid(f"Bench_{name}", (x0, 0.0, z0), (x1, 0.45, z1), mat)


# ---------------------------------------------------------------- the lot (part 1: world/parking_lot.json, shared/city.js, shared/forest.js; read only)
LOT = {"asphalt": (-62.0, 62.0, 27.75, 98.0), "store_front_z": 27.35, "store_doors": (-2.7, 2.7), "table": (-8.0, 41.0), "spawn": (-8.0, 43.6),
       "shelter": (-43.4, 46.4), "bus_at": (-42.4, 44.2), "hedge_south": (98.0, 99.5), "forest_post": (-30.0, 96.6), "forest_at": (-30.0, 95.6)}
# the two sets that stay part of the lot: where each one's origin goes in parking_lot's frame (floor y 9.6), and its yaw
ATTACH = {"table_and_chairs": ("parking_lot", (-8.0, LOT_Y, 41.0), 0.0), "bus_station": ("parking_lot", (-46.0, LOT_Y, 46.0), 0.0)}


# ---------------------------------------------------------------- table_and_chairs: the spawn (a set in the lot)
CHAIRS = [("E", 1.35, 0.0, "pink"), ("W", -1.35, 0.0, "mint"), ("S", 0.0, 1.35, "yellow"), ("N", 0.0, -1.35, "blue")]


def table_and_chairs():
    S = Scene("table_and_chairs", "The table and chairs: the spawn, facing the store", "a set 3.2 m by 3.2 m in the lot, the table's centre at the "
              "lot's (-8, 9.6, 41)", mood="dreamcore, the first thing you see")
    S.attach = ATTACH["table_and_chairs"]
    # the lot's own ground under the set (a collider only: in the game the lot's asphalt is there), and the lot round it for the stills
    S.solid("Ground_lot", (-4.0, -0.2, -4.0), (4.0, 0.0, 4.5), "asphalt", art=False)
    S.ctx("Lot_asphalt", (-30.0, -0.06, -14.0), (40.0, -0.001, 14.0), "asphalt")
    zf = LOT["store_front_z"] - 41.0                       # the store's south wall, in the set's frame
    dx0, dx1 = LOT["store_doors"][0] + 8.0, LOT["store_doors"][1] + 8.0
    S.ctx("Store_front_W", (-18.3, 0.0, zf - 0.2), (dx0, 4.5, zf), "store")
    S.ctx("Store_front_E", (dx1, 0.0, zf - 0.2), (34.3, 4.5, zf), "store")
    S.ctx("Store_doors", (dx0, 0.0, zf - 0.1), (dx1, 3.4, zf), "glass")
    S.ctx("Store_over_doors", (dx0, 3.4, zf - 0.2), (dx1, 4.5, zf), "store")
    S.ctx("Store_canopy", (0.0, 3.7, zf), (16.0, 3.85, 33.0 - 41.0), "store")
    for px in (-7.5, -2.5, 2.5, 7.5):                    # the canopy's posts (Canopy_L4_Store_posts at z 32.71 to 32.95)
        S.ctx("Store_canopy_post", (px + 8.0 - 0.12, 0.0, 32.71 - 41.0), (px + 8.0 + 0.12, 3.7, 32.95 - 41.0), "store")
    S.plan_rect = (-6.0, 17.0, -15.5, 5.5)
    # the table (a round top on one leg: a collider box round it, the top and the leg as art) and four chairs, as index.html draws them
    S.solid("Table", (-0.85, 0.0, -0.85), (0.85, 0.8, 0.85), "plastic_white", art=False)
    S.decor("Table_Top", (-0.85, 0.73, -0.85), (0.85, 0.79, 0.85), "plastic_white")
    S.decor("Table_Leg", (-0.1, 0.0, -0.1), (0.1, 0.73, 0.1), "steel")
    for nm, cx, cz, mat in CHAIRS:
        S.solid(f"Chair_{nm}", (cx - 0.25, 0.0, cz - 0.25), (cx + 0.25, 0.9, cz + 0.25), mat, art=False)
        S.decor(f"Chair_{nm}_Seat", (cx - 0.23, 0.43, cz - 0.23), (cx + 0.23, 0.49, cz + 0.23), mat)
        S.decor(f"Chair_{nm}_Post", (cx - 0.04, 0.0, cz - 0.04), (cx + 0.04, 0.43, cz + 0.04), "steel")
        ox, oz = (0.2 if cx > 0 else -0.2 if cx < 0 else 0.0), (0.2 if cz > 0 else -0.2 if cz < 0 else 0.0)   # the back, away from the table
        if ox:
            S.decor(f"Chair_{nm}_Back", (cx + ox - 0.025, 0.49, cz - 0.23), (cx + ox + 0.025, 0.99, cz + 0.23), mat)
        else:
            S.decor(f"Chair_{nm}_Back", (cx - 0.23, 0.49, cz + oz - 0.025), (cx + 0.23, 0.99, cz + oz + 0.025), mat)
    # the spawn: 2.6 m south of the table, facing the store (lot.L4.front_doors>overworld arrives at the lot's (-8, 9.6, 43.6), facing (0, -1))
    S.marker("Spawn", (0.0, 0.0, 2.6))
    S.label("TABLE", 0.0, 0.0)
    S.label("spawn: facing the store", 0.0, 3.4, kind="note")
    S.label("the store's glass doors (part 1)", (dx0 + dx1) / 2, zf + 1.2, kind="note")
    S.corridor("round_the_table", -3.2, 3.2, 1.9, 3.6)
    S.still = ((0.0, 0.0, 4.6), (0.0, -1.0), -6)
    return S


# ---------------------------------------------------------------- bus_station: "just a ride", in place of the lot's shelter (a set in the lot)
def bus_station():
    S = Scene("bus_station", "The bus station: just a ride to Hallam Row", "a set 14 m by 4 m (a 0.15 m platform) with a 3.5 m bus bay, in the lot "
              "in place of the shelter", mood="dreamcore, a plastic station")
    S.attach = ATTACH["bus_station"]
    S.solid("Ground_lot", (-8.0, -0.2, -3.0), (8.0, 0.0, 7.0), "asphalt", art=False)
    S.ctx("Lot_asphalt", (-16.0, -0.06, -12.0), (16.0, -0.001, 12.0), "asphalt")
    S.ctx("Lot_post_stop2", (5.96, 0.0, -4.79), (6.04, 2.375, -4.71), "steel")          # the lot's own bus stop post (Post_stop2 at (-40, 41.25))
    S.ctx("Lot_hedge", (-14.0, 0.1, 8.5), (2.0, 1.2, 10.5), "hedge")                   # the lot's hedge row at z 54.5 to 56.5
    p = S.solid("Platform", (-7.0, 0.0, -1.5), (7.0, 0.15, 2.5), "paving")
    S.kerb(p, 0.0)
    y = 0.15
    # the shelter: its back to the lot (north), open to the bay (south); glass sides, a roof, a bench
    S.solid("Shelter_Back", (-2.6, y, -1.3), (2.6, 2.6, -1.15), "glass")
    S.solid("Shelter_Side_W", (-2.6, y, -1.15), (-2.45, 2.6, 0.6), "glass")
    S.solid("Shelter_Side_E", (2.45, y, -1.15), (2.6, 2.6, 0.6), "glass")
    S.solid("Shelter_Roof", (-2.8, 2.6, -1.5), (2.8, 2.75, 1.0), "plastic_blue", ("ceiling",))
    S.solid("Shelter_Bench", (-1.6, y, -1.1), (1.6, 0.6, -0.65), "timber")
    S.solid("Timetable", (3.4, y, -0.1), (4.6, 2.2, 0.0), "sign")
    S.solid("Ticket_Machine", (-4.6, y, -0.9), (-3.9, 1.6, -0.4), "plastic_red")
    S.solid("Stop_Sign_Pole", (5.8, y, 1.9), (5.9, 2.8, 2.0), "steel")
    S.decor("Stop_Sign", (5.9, 2.2, 1.7), (5.95, 2.8, 2.2), "plastic_yellow")
    S.decor("Bay_Lines", (-7.0, 0.0, 2.5), (7.0, 0.01, 6.0), "line")
    S.decor("Bay_Kerb_Paint", (-7.0, 0.15, 2.4), (7.0, 0.151, 2.5), "plastic_white")
    # the ride: F on the platform's edge by the bay; coming back off the bus you stand on the platform facing the lot and the store
    S.link("bus_stop", (0.0, y, 1.9), (0.0, y, 0.9), (0, -1), "Hallam Row (city.street), by bus")
    S.label("BUS STATION", 0.0, -2.6)
    S.label("bus bay", 0.0, 4.4, kind="note")
    S.label("timetable", 4.0, -0.7, kind="note")
    S.label("tickets", -4.25, -1.4, kind="note")
    S.label("the lot's bus stop post (part 1)", 6.0, -5.6, kind="note")
    S.corridor("platform", -7.0, 5.5, 0.6, 2.5, y=y)
    S.light(0.0, 2.4, -0.2, 60)
    S.plan_rect = (-9.0, 9.0, -7.0, 8.0)
    S.still = ((-4.0, 0.0, 5.2), (0.55, -1.0), 0)
    return S


# ---------------------------------------------------------------- market: five stalls and the buy-back counter
STALLS = [  # (n, stock, x centre, side the stall's back is on, awning)
    (1, "weapons", -16.0, "N", "awning_a"), (2, "gear", 0.0, "N", "awning_b"), (3, "food", 16.0, "N", "awning_c"),
    (4, "keycards", -8.0, "S", "awning_d"), (5, "cosmetics", 8.0, "S", "awning_e"),
]
MX, MZ = 32.0, 22.0


def stall(S, n, stock, xc, side, aw):
    """A market stall 8 m wide and 4.2 m deep: a back wall with shelves, two side walls, a counter at the front, a striped awning and a sign.
    The keeper's side (Spot_shop_<n>) is behind the counter, facing out."""
    x0, x1 = xc - 4.0, xc + 4.0
    sg = -1 if side == "N" else 1                        # the back wall is at z = sg * 20
    zb = sg * 20.0
    zc = sg * 16.4                                       # the counter's outer face
    lo = lambda a, b: (min(a, b), max(a, b))
    S.solid(f"Stall{n}_Back", (x0, 0.0, lo(zb, zb + sg * 0.2)[0]), (x1, 2.8, lo(zb, zb + sg * 0.2)[1]), "timber")
    for xa, xb in ((x0, x0 + 0.15), (x1 - 0.15, x1)):
        S.solid(f"Stall{n}_Side", (xa, 0.0, lo(zb, zc)[0]), (xb, 2.8, lo(zb, zc)[1]), "timber")
    S.solid(f"Stall{n}_Shelves", (x0 + 0.4, 0.0, lo(zb, zb - sg * 0.45)[0]), (x1 - 0.4, 1.9, lo(zb, zb - sg * 0.45)[1]), "furniture")
    S.solid(f"Stall{n}_Counter", (x0 + 0.15, 0.0, lo(zc, zc - sg * 0.6)[0]), (x1 - 0.15, 1.0, lo(zc, zc - sg * 0.6)[1]), "counter")
    S.solid(f"Stall{n}_Awning", (x0 - 0.3, 2.8, lo(zb + sg * 0.2, zc - sg * 1.6)[0]), (x1 + 0.3, 2.95, lo(zb + sg * 0.2, zc - sg * 1.6)[1]), aw, ("ceiling",))
    zs = zc - sg * 1.6
    S.decor(f"Stall{n}_Sign", (x0 + 0.5, 2.95, lo(zs, zs + sg * 0.1)[0]), (x1 - 0.5, 3.6, lo(zs, zs + sg * 0.1)[1]), "sign")
    S.spot("shop", n, (xc, 0.0, sg * 18.2), face=(0, -sg), props={"stock": stock, "what": f"the {stock} stall's keeper, behind the counter"})
    S.label(stock.upper(), xc, sg * 13.6)
    S.corridor(f"front_of_{stock}", x0, x1, lo(zc - sg * 0.65, zc - sg * 3.6)[0], lo(zc - sg * 0.65, zc - sg * 3.6)[1])


def market():
    S = Scene("market", "The Market: weapons, gear, food, keycards, cosmetics and the buy-back", "64 m by 44 m inside its hedge: five stalls round "
              "a square, a buy-back kiosk in the middle, three facades", mood="dreamcore, a plastic market square")
    grounds(S, "Market", -MX, MX, -MZ, MZ, mat="paving", gaps={"W": [(0.0, 6.0)]})
    for st in STALLS:
        stall(S, *st)
    # the buy-back kiosk (docs/WORLD.md: lost ammo, consumables and perks are bought back here): four counters round its keeper, a roof
    for nm, a, b in (("N", (-2.0, -2.0), (2.0, -1.6)), ("S", (-2.0, 1.6), (2.0, 2.0)), ("W", (-2.0, -1.6), (-1.6, 1.6)), ("E", (1.6, -1.6), (2.0, 1.6))):
        S.solid(f"Kiosk_Counter_{nm}", (a[0], 0.0, a[1]), (b[0], 1.0, b[1]), "counter")
    for cx in (-2.45, 2.3):
        for cz in (-2.45, 2.3):
            S.solid("Kiosk_Post", (cx, 0.0, cz), (cx + 0.15, 2.6, cz + 0.15), "steel")
    S.solid("Kiosk_Roof", (-2.8, 2.6, -2.8), (2.8, 2.8, 2.8), "awning_f", ("ceiling",))
    for nm, a, b in (("N", (-1.6, -2.82), (1.6, -2.8)), ("S", (-1.6, 2.8), (1.6, 2.82))):
        S.decor(f"Kiosk_Sign_{nm}", (a[0], 2.8, a[1]), (b[0], 3.4, b[1]), "sign")
    S.spot("shop", 6, (0.0, 0.0, 0.0), face=(-1, 0), props={"stock": "buy-back", "what": "buys back lost ammo, consumables and perks"})
    S.label("BUY-BACK", 0.0, 3.6)
    # picnic tables between the stalls
    for k, (tx, tz) in enumerate(((-16.0, 5.0), (16.0, 5.0), (-16.0, -5.0), (16.0, -5.0)), 1):
        S.solid(f"Picnic_{k}_Table", (tx - 1.0, 0.0, tz - 0.4), (tx + 1.0, 0.75, tz + 0.4), "timber")
        S.solid(f"Picnic_{k}_Bench", (tx - 1.0, 0.0, tz - 1.05), (tx + 1.0, 0.45, tz - 0.75), "timber")
        S.solid(f"Picnic_{k}_Bench", (tx - 1.0, 0.0, tz + 0.75), (tx + 1.0, 0.45, tz + 1.05), "timber")
    # three "more to come" facades along the east side, their backs to the hedge
    for k, fz in enumerate((-9.0, 0.0, 9.0), 1):
        facade(S, k, "W", fz, 29.0)
    for k, (lx, lz) in enumerate(((-26.0, -14.0), (26.0, -14.0), (-26.0, 14.0), (26.0, 14.0), (0.0, -11.6), (0.0, 11.6)), 1):
        lamp(S, k, lx, lz)
    keeper(S, 1, (-20.0, 0.0, 21.5), (0, 1), "watches")
    keeper(S, 2, (24.0, 0.0, -21.5), (0, -1), "ignores")
    keeper(S, 3, (-31.5, 0.0, 14.0), (-1, 0), "watches")
    walk_gap(S, "lot", "W", 0.0, -MX, "parking_lot (the lot's east edge)", 1)
    S.label("to the parking lot", -26.0, 3.0, kind="note")
    S.corridor("entrance", -33.2, -27.0, -2.5, 2.5)
    S.corridor("aisle_W", -30.5, -24.0, -11.0, 11.0)
    S.corridor("aisle_E", 21.0, 27.0, -11.0, 11.0)
    S.corridor("aisle_mid", -12.0, 12.0, -10.5, -4.0)
    for x in (-16, 0, 16):
        S.light(x, 2.4, -18.0, 80)
    S.still = ((-29.0, 0.0, 0.5), (1.0, -0.05), -2)
    return S


# ---------------------------------------------------------------- playground: real equipment, each a mini-game; moving parts on their pivots
PX, PZ = 50.0, 38.0
PLOTS = {"swing": (-36.0, -20.0), "slide": (-12.0, -20.0), "seesaw": (12.0, -20.0), "merry_go_round": (36.0, -20.0),
         "monkey_bars": (-36.0, 20.0), "sandbox": (-12.0, 20.0), "spring_riders": (12.0, 20.0), "climbing_frame": (36.0, 20.0)}


def _rel(cx, y, cz, a, b, mat):
    return ((cx + a[0], y + a[1], cz + a[2]), (cx + b[0], y + b[1], cz + b[2]), mat)


def eq_swing(S):
    cx, cz = PLOTS["swing"]
    S.solid("Swing_Bar", (cx - 3.0, 2.4, cz - 0.06), (cx + 3.0, 2.52, cz + 0.06), "steel")
    for x in (-3.0, 3.0):
        for z in (-0.9, 0.9):
            S.solid("Swing_Leg", (cx + x - 0.06, 0.0, cz + z - 0.06), (cx + x + 0.06, 2.4, cz + z + 0.06), "steel")
    parts = []
    for k, sx in ((1, -1.2), (2, 1.2)):
        px, py, pz = cx + sx, 2.4, cz
        boxes = [_rel(px, py, pz, (-0.24, -2.0, -0.02), (-0.2, 0.0, 0.02), "steel"), _rel(px, py, pz, (0.2, -2.0, -0.02), (0.24, 0.0, 0.02), "steel"),
                 _rel(px, py, pz, (-0.26, -2.04, -0.13), (0.26, -1.98, 0.13), "plastic_red")]
        parts.append(S.part("swing", f"seat{k}", (px, py, pz), boxes, "x", "pendulum", 35, {"length_m": 2.0}))
    S.decor("Swing_Pad", (cx - 3.4, 0.0, cz - 4.0), (cx + 3.4, 0.012, cz + 4.0), "rubber")
    minigame(S, "swing", (cx + 4.4, 0.0, cz + 2.2), (-1, 0), parts, "swing high: the higher, the more it pays", (cx - 5.5, cx + 5.5, cz - 5.0, cz + 5.0))
    S.label("SWING", cx, cz - 6.0)


def eq_slide(S):
    cx, cz = PLOTS["slide"]
    flight(S, "slide_ladder", cz - 0.5, cz + 0.5, cx - 2.8, 1, "x", 0.0, 1.5, 6, 0.3)
    S.solid("Slide_Platform", (cx - 1.0, 1.42, cz - 0.6), (cx + 0.2, 1.5, cz + 0.6), "plastic_yellow")
    for x in (-1.0, 0.08):
        for z in (-0.6, 0.48):
            S.solid("Slide_Post", (cx + x, 0.0, cz + z), (cx + x + 0.12, 1.42, cz + z + 0.12), "steel")
    S.solid("Slide_Rail_N", (cx - 1.0, 1.5, cz - 0.62), (cx + 0.2, 2.3, cz - 0.56), "steel")
    S.solid("Slide_Rail_S", (cx - 1.0, 1.5, cz + 0.56), (cx + 0.2, 2.3, cz + 0.62), "steel")
    # the chute: seven boxes down to the ground, 0.2 m apart (0.1 m at the end), so it can be walked up as well as slid down
    tops = [0.1, 0.3, 0.5, 0.7, 0.9, 1.1, 1.3]
    seg = 4.0 / 7
    for i, top in enumerate(tops):
        x1 = cx + 4.2 - i * seg
        S.solid(f"Step_slide_chute_{i:02d}", (x1 - seg, top - 0.1, cz - 0.35), (x1, top, cz + 0.35), "plastic_blue")
    S.flights.append({"name": "slide_chute", "y_start": 0.0, "y_end": 1.5, "n": 7, "rise": 0.2, "tread": round(seg, 3)})
    S.decor("Slide_Pad", (cx - 3.4, 0.0, cz - 1.6), (cx + 5.4, 0.012, cz + 1.6), "rubber")
    minigame(S, "slide", (cx + 5.4, 0.0, cz + 1.4), (-1, 0), [], "slide down against the clock (no moving part: the page slides you)",
             (cx - 5.3, cx + 6.7, cz - 3.1, cz + 3.1))
    S.label("SLIDE", cx + 0.7, cz - 4.2)


def eq_seesaw(S):
    cx, cz = PLOTS["seesaw"]
    S.solid("Seesaw_Fulcrum", (cx - 0.15, 0.0, cz - 0.25), (cx + 0.15, 0.55, cz + 0.25), "steel")
    piv = (cx, 0.6, cz)
    boxes = [_rel(cx, 0.6, cz, (-2.0, -0.05, -0.15), (2.0, 0.05, 0.15), "plastic_green")]
    for x in (-1.7, 1.7):
        boxes.append(_rel(cx, 0.6, cz, (x - 0.03, 0.05, -0.15), (x + 0.03, 0.4, 0.15), "steel"))
        boxes.append(_rel(cx, 0.6, cz, (x + (0.1 if x < 0 else -0.4) - 0.0, 0.05, -0.15), (x + (0.4 if x < 0 else -0.1), 0.1, 0.15), "plastic_red"))
    parts = [S.part("seesaw", "plank", piv, boxes, "z", "tilt", 15, {"length_m": 4.0})]
    S.decor("Seesaw_Pad", (cx - 2.8, 0.0, cz - 1.2), (cx + 2.8, 0.012, cz + 1.2), "rubber")
    minigame(S, "seesaw", (cx, 0.0, cz + 1.8), (0, -1), parts, "keep it level with a friend, or against a weight", (cx - 4.5, cx + 4.5, cz - 2.5, cz + 2.5))
    S.label("SEESAW", cx, cz - 3.4)


def eq_merry_go_round(S):
    cx, cz = PLOTS["merry_go_round"]
    b = S.solid("MGR_Base", (cx - 0.4, 0.0, cz - 0.4), (cx + 0.4, 0.15, cz + 0.4), "steel")
    S.kerb(b, 0.0)
    piv = (cx, 0.15, cz)
    r = lambda a, b_, m: _rel(cx, 0.15, cz, a, b_, m)
    boxes = [r((-1.6, 0.0, -0.66), (1.6, 0.12, 0.66), "plastic_yellow"), r((-0.66, 0.0, -1.6), (0.66, 0.12, 1.6), "plastic_yellow"),
             r((-1.13, 0.0, -1.13), (1.13, 0.12, 1.13), "plastic_yellow"), r((-0.06, 0.12, -0.06), (0.06, 0.95, 0.06), "steel")]
    for a in range(4):
        th = math.radians(45 + 90 * a)
        x, z = 1.15 * math.cos(th), 1.15 * math.sin(th)
        boxes.append(r((x - 0.03, 0.12, z - 0.03), (x + 0.03, 0.9, z + 0.03), "steel"))
        boxes.append(r((min(0, x) - 0.03, 0.87, min(0, z) - 0.03), (max(0, x) + 0.03, 0.93, max(0, z) + 0.03), "steel"))
    parts = [S.part("merry_go_round", "deck", piv, boxes, "y", "spin", 360, {"radius_m": 1.6})]
    S.decor("MGR_Pad", (cx - 2.8, 0.0, cz - 2.8), (cx + 2.8, 0.012, cz + 2.8), "rubber")
    minigame(S, "merry_go_round", (cx - 3.3, 0.0, cz + 2.0), (1, 0), parts, "spin it up and hold on", (cx - 4.1, cx + 4.1, cz - 4.1, cz + 4.1))
    S.label("MERRY-GO-ROUND", cx, cz - 5.0)


def eq_monkey_bars(S):
    cx, cz = PLOTS["monkey_bars"]
    for z0, z1 in ((-0.33, -0.27), (0.27, 0.33)):
        S.solid("MonkeyBars_Rail", (cx - 2.4, 2.05, cz + z0), (cx + 2.4, 2.15, cz + z1), "steel")
    for x in (-2.4, 2.32):
        for z in (-0.33, 0.25):
            S.solid("MonkeyBars_Upright", (cx + x, 0.0, cz + z), (cx + x + 0.08, 2.15, cz + z + 0.08), "steel")
    for k in range(11):
        x = -2.0 + 0.4 * k
        S.decor("MonkeyBars_Rung", (cx + x - 0.02, 2.07, cz - 0.27), (cx + x + 0.02, 2.11, cz + 0.27), "plastic_red")
    # a small platform at each end, up three steps
    for sg, nm in ((-1, "W"), (1, "E")):
        xa, xb = (cx - 3.2, cx - 2.4) if sg < 0 else (cx + 2.4, cx + 3.2)
        S.solid(f"MonkeyBars_Platform_{nm}", (xa, 0.0, cz - 0.6), (xb, 0.75, cz + 0.6), "plastic_blue")
        flight(S, f"monkey_{nm}", cz - 0.6, cz + 0.6, cx + sg * 4.1, -sg, "x", 0.0, 0.75, 3, 0.3)
    S.decor("MonkeyBars_Pad", (cx - 4.4, 0.0, cz - 1.8), (cx + 4.4, 0.012, cz + 1.8), "rubber")
    minigame(S, "monkey_bars", (cx, 0.0, cz + 1.8), (0, -1), [], "cross without dropping (no moving part: the rungs are art)",
             (cx - 6.6, cx + 6.6, cz - 2.9, cz + 2.9))
    S.label("MONKEY BARS", cx, cz - 3.6)


def eq_sandbox(S):
    cx, cz = PLOTS["sandbox"]
    for nm, a, b in (("N", (-3.0, -3.0), (3.0, -2.8)), ("S", (-3.0, 2.8), (3.0, 3.0)), ("W", (-3.0, -2.8), (-2.8, 2.8)), ("E", (2.8, -2.8), (3.0, 2.8))):
        k = S.solid(f"Sandbox_Board_{nm}", (cx + a[0], 0.0, cz + a[1]), (cx + b[0], 0.25, cz + b[1]), "timber")
        S.kerb(k, 0.0)
    S.decor("Sandbox_Sand", (cx - 2.8, 0.0, cz - 2.8), (cx + 2.8, 0.02, cz + 2.8), "sand")
    dx, dz = cx + 1.4, cz - 1.2
    S.solid("Sandbox_Digger_Base", (dx - 0.2, 0.0, dz - 0.2), (dx + 0.2, 0.5, dz + 0.2), "plastic_yellow")
    seat = S.part("sandbox", "digger_seat", (dx, 0.5, dz), [_rel(dx, 0.5, dz, (-0.25, 0.0, -0.25), (0.25, 0.08, 0.25), "plastic_yellow"),
                                                         _rel(dx, 0.5, dz, (-0.25, 0.08, 0.2), (0.25, 0.5, 0.25), "plastic_yellow")],
                  "y", "spin", 180)
    arm = S.part("sandbox", "digger_arm", (dx, 0.75, dz - 0.25), [_rel(dx, 0.75, dz - 0.25, (-0.04, -0.04, -1.2), (0.04, 0.04, 0.0), "steel"),
                                                               _rel(dx, 0.75, dz - 0.25, (-0.15, -0.55, -1.4), (0.15, -0.1, -1.1), "plastic_red")],
                 "x", "tilt", 30, {"parent": seat})
    S.spot("puzzle", 1, (cx - 1.4, 0.0, cz + 1.2), face=(0, -1), props={"what": "something buried in the sand"})
    minigame(S, "sandbox", (cx - 1.4, 0.0, cz - 1.2), (1, 0), [seat, arm], "dig up what is buried, with the digger or by hand",
             (cx - 5.0, cx + 5.0, cz - 5.0, cz + 5.0))
    S.label("SANDBOX", cx, cz + 4.2)


def eq_spring_riders(S):
    cx, cz = PLOTS["spring_riders"]
    parts = []
    for k, (x, what, mat) in enumerate(((-2.0, "horse", "plastic_red"), (0.0, "duck", "plastic_yellow"), (2.0, "bee", "plastic_blue")), 1):
        b = S.solid(f"Rider{k}_Base", (cx + x - 0.3, 0.0, cz - 0.3), (cx + x + 0.3, 0.1, cz + 0.3), "steel")
        S.kerb(b, 0.0)
        r = lambda a, b_, m: _rel(cx + x, 0.1, cz, a, b_, m)
        boxes = [r((-0.07, 0.0, -0.07), (0.07, 0.35, 0.07), "steel"), r((-0.45, 0.35, -0.15), (0.45, 0.7, 0.15), mat),
                 r((0.3, 0.7, -0.12), (0.55, 1.0, 0.12), mat), r((0.2, 0.85, -0.25), (0.25, 0.9, 0.25), "steel")]
        parts.append(S.part("spring_riders", f"rider{k}", (cx + x, 0.1, cz), boxes, "xz", "rock", 20, {"what": what}))
    S.decor("Riders_Pad", (cx - 3.2, 0.0, cz - 1.4), (cx + 3.2, 0.012, cz + 1.4), "rubber")
    minigame(S, "spring_riders", (cx, 0.0, cz - 1.7), (0, 1), parts, "ride out the bucking: a race between the three",
             (cx - 4.5, cx + 4.5, cz - 2.3, cz + 2.3))
    S.label("SPRING RIDERS", cx, cz + 3.2)


def eq_climbing_frame(S):
    cx, cz = PLOTS["climbing_frame"]
    for x in (-2.0, 1.92):
        for z in (-2.0, 1.92):
            S.solid("Frame_Post", (cx + x, 0.0, cz + z), (cx + x + 0.08, 2.45, cz + z + 0.08), "plastic_green")
    for y in (0.75, 2.35):
        S.solid("Frame_Rail_N", (cx - 2.0, y, cz - 2.0), (cx + 2.0, y + 0.1, cz - 1.92), "plastic_green")
        S.solid("Frame_Rail_S", (cx - 2.0, y, cz + 1.92), (cx + 2.0, y + 0.1, cz + 2.0), "plastic_green")
        S.solid("Frame_Rail_W", (cx - 2.0, y, cz - 1.92), (cx - 1.92, y + 0.1, cz + 1.92), "plastic_green")
        # the steps come in on the east side: both east rails have a gap for them (headroom on the steps)
        S.solid("Frame_Rail_E", (cx + 1.92, y, cz - 1.92), (cx + 2.0, y + 0.1, cz - 0.6), "plastic_green")
        S.solid("Frame_Rail_E", (cx + 1.92, y, cz + 0.6), (cx + 2.0, y + 0.1, cz + 1.92), "plastic_green")
    S.solid("Frame_Deck", (cx - 1.5, 1.42, cz - 1.5), (cx + 1.5, 1.5, cz + 1.5), "timber")
    flight(S, "frame_steps", cz - 0.6, cz + 0.6, cx + 3.3, -1, "x", 0.0, 1.5, 6, 0.3)
    for k in range(5):
        y = 0.35 + 0.4 * k
        S.decor("Frame_Bar", (cx - 1.96, y, cz - 1.96), (cx + 1.96, y + 0.04, cz - 1.92), "plastic_green")
    piv = (cx, 2.0, cz - 1.88)
    boxes = [_rel(*piv, (-0.3, -0.03, 0.0), (0.3, 0.03, 0.04), "plastic_red"), _rel(*piv, (-0.03, -0.3, 0.0), (0.03, 0.3, 0.04), "plastic_red"),
             _rel(*piv, (-0.22, -0.22, 0.0), (0.22, 0.22, 0.03), "plastic_red")]
    parts = [S.part("climbing_frame", "wheel", piv, boxes, "z", "spin", 360, {"what": "a ship's wheel on the north rail"})]
    S.decor("Frame_Pad", (cx - 3.0, 0.0, cz - 3.0), (cx + 4.2, 0.012, cz + 3.0), "rubber")
    minigame(S, "climbing_frame", (cx - 3.6, 0.0, cz), (1, 0), parts, "climb to the deck and steer: a race to the top",
             (cx - 4.5, cx + 5.8, cz - 4.5, cz + 4.5))
    S.label("CLIMBING FRAME", cx, cz + 5.4)


def playground():
    S = Scene("playground", "The playground: real equipment, each piece a mini-game that pays", "100 m by 76 m inside its hedge: eight pieces of "
              "equipment, each on its own clear ground, either side of a path", mood="dreamcore, too bright")
    grounds(S, "Playground", -PX, PX, -PZ, PZ, mat="grass", gaps={"E": [(0.0, 6.0)], "W": [(0.0, 6.0)]})
    S.decor("Path", (-PX, 0.0, -2.0), (PX, 0.01, 2.0), "path")
    for fn in (eq_swing, eq_slide, eq_seesaw, eq_merry_go_round, eq_monkey_bars, eq_sandbox, eq_spring_riders, eq_climbing_frame):
        fn(S)
    for k, (x0, z0) in enumerate(((-26.0, -4.2), (22.0, -4.2), (-26.0, 3.7), (22.0, 3.7)), 1):
        bench(S, k, x0, x0 + 2.0, z0, z0 + 0.5)
    for k, x in enumerate((-30.0, -6.0, 6.0, 30.0), 1):
        lamp(S, k, x, -3.0 if k % 2 else 3.0)
    # two "more to come" facades against the north hedge
    facade(S, 1, "S", -4.0, -PZ + 1.2, width=7.6, label=False)
    facade(S, 2, "S", 4.0, -PZ + 1.2, width=7.6, label=False)
    S.label("MORE TO COME (two facades)", 0.0, -PZ + 4.6, kind="note")
    keeper(S, 1, (-20.0, 0.0, -PZ + 0.5), (0, -1), "watches")
    keeper(S, 2, (-PX + 0.5, 0.0, 28.0), (-1, 0), "ignores")
    keeper(S, 3, (26.0, 0.0, PZ - 0.5), (0, 1), "watches")
    walk_gap(S, "lot", "E", 0.0, PX, "parking_lot (the lot's west edge)", -1)
    walk_gap(S, "tree_house", "W", 0.0, -PX, "tree_house (the path west)", 1)
    S.label("to the parking lot", 44.0, 4.4, kind="note")
    S.label("to the tree house", -44.0, 4.4, kind="note")
    S.corridor("path", -46.0, 46.0, -2.0, 2.0)
    S.corridor("gap_E", 45.0, 51.2, -2.5, 2.5)
    S.corridor("gap_W", -51.2, -45.0, -2.5, 2.5)
    S.still = ((46.0, 0.0, 1.0), (-1.0, -0.32), -3)
    return S


# ---------------------------------------------------------------- tree_house: a puzzle, and the way to its own addon later
TX = 22.0


def tree_house():
    S = Scene("tree_house", "The tree house: a puzzle, and a locked door in the trunk to its own addon", "a glade 44 m by 44 m round one big tree; "
              "the house 6.5 m by 8 m and a porch on a platform at y 4", levels=(0.0, 4.0), mood="dreamcore, a secret")
    S.level_names = {0.0: "ground (y 0)", 4.0: "the tree house (y 4)"}
    grounds(S, "Glade", -TX, TX, -TX, TX, mat="grass", gaps={"E": [(0.0, 6.0)]})
    for k, (x, z) in enumerate(((-14.0, -14.0), (14.0, -15.0), (-15.0, 13.0), (12.0, 15.0), (-17.0, 0.0), (0.0, -17.0), (2.0, 17.0)), 1):
        S.solid(f"Tree_{k}_Trunk", (x - 0.5, 0.0, z - 0.5), (x + 0.5, 5.0, z + 0.5), "bark")
        S.decor(f"Tree_{k}_Crown", (x - 3.0, 4.5, z - 3.0), (x + 3.0, 8.0, z + 3.0), "pastel_leaf", ("ceiling",))
    # the big tree, through the middle of the house
    S.solid("BigTree_Trunk", (-1.4, 0.0, -1.4), (1.4, 9.5, 1.4), "bark")
    S.decor("BigTree_Crown", (-8.0, 8.5, -8.0), (8.0, 12.5, 8.0), "leaf", ("ceiling",))
    S.decor("BigTree_Crown_Top", (-5.0, 12.5, -5.0), (5.0, 14.5, 5.0), "leaf", ("ceiling",))
    y = 4.0
    # the platform round the trunk (four boxes, so the trunk goes through), on four posts
    for nm, a, b in (("N", (-4.4, -4.4), (6.0, -1.4)), ("S", (-4.4, 1.4), (6.0, 4.4)), ("W", (-4.4, -1.4), (-1.4, 1.4)), ("E", (1.4, -1.4), (6.0, 1.4))):
        S.solid(f"Platform_{nm}", (a[0], y - 0.2, a[1]), (b[0], y, b[1]), "timber")
    for px, pz in ((-4.3, -4.3), (5.7, -4.3), (-4.3, 4.05), (5.7, 4.05)):
        S.solid("Platform_Post", (px, 0.0, pz), (px + 0.25, y - 0.2, pz + 0.25), "timber")
    # the house: x -4 to 2.5, z -4 to 4, 2.6 m high, its door in the east wall onto the porch
    shell(S, "House", -4.0, 2.5, -4.0, 4.0, y0=y, h=2.6, holes={"E": [(-2.6, 1.0, 2.2)]}, floor=False, wmat="timber", cmat="roof")
    single_door(S, "house", "E", -2.6, 2.5, y=y, props={"kind": "tree house door"}, state="ajar")
    # the porch: x 2.7 to 6, railed, open at the top of the stairs
    S.solid("Porch_Rail_N", (2.7, y, -4.4), (6.0, y + 1.0, -4.25), "timber")
    S.solid("Porch_Rail_S", (2.7, y, 4.25), (6.0, y + 1.0, 4.4), "timber")
    S.solid("Porch_Rail_E", (5.85, y, -4.25), (6.0, y + 1.0, 1.6), "timber")
    S.solid("Porch_Rail_E", (5.85, y, 3.4), (6.0, y + 1.0, 4.25), "timber")
    flight(S, "tree_stairs", 1.6, 3.4, 10.8, -1, "x", 0.0, y, 16, 0.3, mat="timber")
    S.decor("Stair_Rail_N", (6.0, 1.0, 1.55), (10.8, 1.06, 1.6), "timber")
    # the puzzle: a board of carved symbols on the west wall; the addon's door: a small locked door in the trunk
    S.decor("Puzzle_Board", (-4.0, y + 0.8, 1.6), (-3.88, y + 1.9, 3.6), "sign")
    S.spot("puzzle", 1, (-3.2, y, 2.6), face=(-1, 0), props={"what": "the carved board: the tree house's puzzle"})
    S.door("addon", (-0.47, y, 1.4), (1, 0), (0, 1), width=0.94, height=1.6, state="closed",
           props={"kind": "a small door in the trunk", "locked": "until the tree house addon"})
    S.link("addon", (0.0, y, 1.95), (0.0, y, 2.6), (0, 1), "the tree house addon (future_addon_treehouse, reserved)")
    S.decor("Lantern", (-0.15, y + 1.9, -3.9), (0.15, y + 2.2, -3.75), "lamp")
    keeper(S, 1, (-TX + 0.5, 0.0, 9.0), (-1, 0), "ignores")
    walk_gap(S, "playground", "E", 0.0, TX, "playground (the path east)", -1)
    S.label("TREE", 0.0, -2.2, y=0.0)
    S.label("stairs up (16 x 0.25 m)", 8.4, 4.4, y=0.0, kind="note")
    S.label("to the playground", 18.0, 4.0, y=0.0, kind="note")
    S.label("TREE HOUSE", -1.0, -2.7, y=y)
    S.label("porch", 4.3, 0.0, y=y)
    S.label("trunk door: the addon (locked)", 0.0, 3.3, y=y, kind="note")
    S.corridor("path", 10.9, 21.5, -0.5, 3.4)
    S.corridor("gap_E", 19.0, 23.2, -2.5, 2.5)
    S.corridor("porch", 2.75, 5.8, -4.2, 4.2, y=y)
    S.corridor("house_N", -3.95, 2.45, -3.95, -1.5, y=y)
    S.corridor("house_S", -3.8, 2.45, 1.75, 3.95, y=y)
    S.light(0.0, y + 2.3, -3.0, 60)
    S.light(-2.0, y + 2.3, 2.5, 60)
    S.still = ((16.0, 0.0, 7.0), (-0.92, -0.4), 12)
    return S


# ---------------------------------------------------------------- road: the road to the forest
ROAD_L = 480.0               # [DEFAULT] 480 m: two minutes' walk at 4 m/s


def road():
    L = ROAD_L
    S = Scene("road", "The road to the forest", f"{L:g} m long, an 8 m road between grass verges and hedges, 24 m across; the lot's end at z 0, "
              f"the forest's at z -{L:g}", mood="dreamcore, a long straight road")
    S.solid("Ground_Road", (-14.0, -SLAB, -L - 2.0), (14.0, 0.0, 4.0), "grass")
    S.decor("Road_Asphalt", (-4.0, 0.0, -L), (4.0, 0.012, 3.0), "asphalt")
    S.decor("Road_Centre_Line", (-0.06, 0.012, -L), (0.06, 0.016, 3.0), "line")
    # hedges both sides, in 40 m lengths (gaps where the two facades stand)
    fac = {220: 1, 340: 2}                                # the facades stand in the middles of the 40 m lengths 220 m and 340 m out
    for k in range(int(L // 40)):
        z, z1 = -40.0 * k, -40.0 * (k + 1)
        mid = (z + z1) / 2
        S.solid("Hedge_W", (-13.2, 0.0, z1), (-12.0, 1.4, z), "hedge")
        if round(-mid) in fac:
            S.solid("Hedge_E", (12.0, 0.0, z1), (13.2, 1.4, mid - 4.2), "hedge")
            S.solid("Hedge_E", (12.0, 0.0, mid + 4.2), (13.2, 1.4, z), "hedge")
            facade(S, fac[round(-mid)], "W", mid, 12.0)
        else:
            S.solid("Hedge_E", (12.0, 0.0, z1), (13.2, 1.4, z), "hedge")
    # the lot's end: a hedge across with the gap you came through; the forest's end: a wall of pastel trees with a bright gap
    S.solid("Hedge_Lot_W", (-13.2, 0.0, 2.0), (-4.0, 1.6, 3.2), "hedge")
    S.solid("Hedge_Lot_E", (4.0, 0.0, 2.0), (13.2, 1.6, 3.2), "hedge")
    for k, x in enumerate((-11.0, -7.5, 7.5, 11.0), 1):
        S.solid(f"Forest_Tree_{k}", (x - 1.5, 0.0, -L - 1.5), (x + 1.5, 7.0, -L + 1.5), "bark")
        S.decor(f"Forest_Tree_{k}_Crown", (x - 3.0, 6.0, -L - 3.0), (x + 3.0, 10.0, -L + 3.0), "pastel_leaf", ("ceiling",))
    S.decor("Forest_Gap_Glow", (-4.0, 0.0, -L - 1.6), (4.0, 6.0, -L - 1.4), "lamp")
    for k in range(int(L // 40)):
        lamp(S, k + 1, 5.2 if k % 2 else -5.2, -20.0 - 40.0 * k)
    for k, bz in enumerate((-120.0, -240.0, -360.0), 1):
        bench(S, k, 7.5, 8.0, bz - 1.0, bz + 1.0)
    S.solid("Signpost_Forest", (-5.2, 0.0, -4.1), (-5.0, 2.4, -3.9), "timber")
    S.decor("Signpost_Forest_Board", (-5.0, 1.8, -4.3), (-4.0, 2.2, -3.7), "sign")
    S.solid("Signpost_Lot", (5.0, 0.0, -L + 3.9), (5.2, 2.4, -L + 4.1), "timber")
    S.decor("Signpost_Lot_Board", (4.0, 1.8, -L + 3.7), (5.0, 2.2, -L + 4.3), "sign")
    S.edge("W", (-14.0, 0.0, -L - 2.0), (-13.8, 3.0, 4.0))
    S.edge("E", (13.8, 0.0, -L - 2.0), (14.0, 3.0, 4.0))
    S.edge("Lot", (-13.8, 0.0, 3.8), (13.8, 3.0, 4.0))
    S.edge("Forest", (-13.8, 0.0, -L - 2.0), (13.8, 3.0, -L - 1.8))
    for k, (kx, kz, f, mood) in enumerate(((-11.4, -60.0, (-1, 0), "watches"), (11.4, -150.0, (1, 0), "ignores"), (-11.4, -300.0, (-1, 0), "ignores"),
                                           (11.4, -420.0, (1, 0), "watches")), 1):
        keeper(S, k, (kx, 0.0, kz), f, mood)
    S.link("lot", (0.0, 0.0, 2.6), (0.0, 0.0, -1.5), (0, -1), "parking_lot (the gap in its south hedge, by the old signpost)")
    S.link("forest", (0.0, 0.0, -L - 0.9), (0.0, 0.0, -L + 4.0), (0, 1), "forest (dreamcore_forest), arriving at (0, 0, 6) facing north")
    S.label("to the parking lot", 0.0, 6.5, kind="note")
    S.label("to the forest", 0.0, -L - 5.5, kind="note")
    for k in range(1, int(L // 80) + 1):
        S.label(f"{80 * k} m", -8.0, -80.0 * k, kind="note")
    S.label("ROAD", 0.0, -L / 2 + 20.0)
    S.corridor("road", -4.0, 4.0, -L - 1.4, 1.9)
    S.segments = [(f"S{k + 1}", -16.0, 16.0, -L / 4 * (k + 1) - 6.0 * (k == 3), -L / 4 * k + 8.0 * (k == 0)) for k in range(4)]
    S.still = ((0.0, 0.0, -1.5), (0.0, -1.0), 0)
    return S


# ---------------------------------------------------------------- endless_hills: one seamless 200 m tile that repeats, toys and little puzzles
HILL_HALF, HILL_CELL, HILL_ART = 100.0, 4.0, 2.0
HILL_SCALE = 0.535                       # sized so no two neighbouring 4 m columns differ by more than 0.27 m, across the seams too
HILL_BASE = -6.0


def hill_h(x, z):
    """The hills' height at (x, z): a sum of cosines in u = (x + 100) / 100 and v = (z + 100) / 100 with whole-number frequencies, so it repeats
    every 200 m and is even about the tile's edges: the heights along opposite edges are the same, and so are the slopes."""
    u, v = (x + HILL_HALF) / HILL_HALF, (z + HILL_HALF) / HILL_HALF
    c = math.cos
    p = math.pi
    return HILL_SCALE * (1.5 * c(p * u) + 1.2 * c(p * v) + 0.8 * c(2 * p * u) * c(p * v) + 0.5 * c(p * u) * c(3 * p * v) + 0.4 * c(3 * p * u)) - HILL_OFFSET


HILL_OFFSET = 0.0
HILL_OFFSET = (lambda f: f(0.0 + HILL_CELL / 2, 0.0 + HILL_CELL / 2))(hill_h)      # the arrival's column (by the tile's centre) is at y 0


def hill_top(x, z):
    """The top of the collision column under (x, z): the height at that 4 m column's centre, to the mm."""
    n = int(round(2 * HILL_HALF / HILL_CELL))
    i = min(n - 1, max(0, int((x + HILL_HALF) // HILL_CELL)))
    j = min(n - 1, max(0, int((z + HILL_HALF) // HILL_CELL)))
    return round(hill_h(-HILL_HALF + (i + 0.5) * HILL_CELL, -HILL_HALF + (j + 0.5) * HILL_CELL), 3)


TOYS = [(1, "ball", -18.0, -26.0), (2, "beach ball", 30.0, -8.0), (3, "traffic cone", 54.0, 42.0), (4, "wooden crate", -46.0, 18.0),
        (5, "hoop", 10.0, 62.0), (6, "wobbly block", -70.0, -54.0), (7, "rubber duck", 74.0, -66.0), (8, "kite", -30.0, 78.0),
        (9, "space hopper", 82.0, 14.0), (10, "skittles", -82.0, -10.0), (11, "football", 6.0, -74.0), (12, "giant die", 46.0, 82.0)]
PUZZLES = [(1, "stacking stones: stack them by size", -58.0, 50.0), (2, "a ring of mushrooms: step on them in order", 62.0, -34.0),
           (3, "a door frame standing alone: walk through it the right way", -38.0, -70.0), (4, "a hopscotch grid painted on the grass", 26.0, 34.0)]


def endless_hills():
    S = Scene("endless_hills", "The endless hills: one tile that repeats, so they never get you further away",
              "a 200 m by 200 m tile of rolling hills, 4.3 m from the lowest dip to the highest top, that repeats without a seam",
              mood="dreamcore, eerily beautiful")
    n = int(round(2 * HILL_HALF / HILL_CELL))
    for j in range(n):
        for i in range(n):
            x0, z0 = -HILL_HALF + i * HILL_CELL, -HILL_HALF + j * HILL_CELL
            top = round(hill_h(x0 + HILL_CELL / 2, z0 + HILL_CELL / 2), 3)
            S.solid(f"Ground_Hills_{i:02d}_{j:02d}", (x0, HILL_BASE, z0), (x0 + HILL_CELL, top, z0 + HILL_CELL), "grass", art=False)
    # the art: one smooth surface over the same heights (a 2 m grid, its edge rows equal on opposite sides)
    m = int(round(2 * HILL_HALF / HILL_ART))
    verts = [(-HILL_HALF + i * HILL_ART, hill_h(-HILL_HALF + i * HILL_ART, -HILL_HALF + j * HILL_ART), -HILL_HALF + j * HILL_ART)
             for j in range(m + 1) for i in range(m + 1)]
    faces = [(j * (m + 1) + i, j * (m + 1) + i + 1, (j + 1) * (m + 1) + i + 1, (j + 1) * (m + 1) + i) for j in range(m) for i in range(m)]
    S.mesh("Hills_Surface", verts, faces, "grass")
    # the way back: a signpost by the tile's centre, so it stands at the same place on every repeat of the tile
    ax, az = HILL_CELL / 2, HILL_CELL / 2                  # the arrival's column; the F spot is on the next column north, at its own top
    y0 = hill_top(ax, az)
    S.link("lot", (ax, hill_top(ax, az - 4.0), az - 4.0), (ax, y0, az), (0, -1), "parking_lot (the stile over its south hedge)")
    sx, sz = ax + 1.2, az - 4.0
    sy = hill_top(sx, sz)
    S.solid("Signpost_Lot", (sx - 0.1, sy - 0.3, sz - 0.1), (sx + 0.1, sy + 2.4, sz + 0.1), "timber")
    S.decor("Signpost_Lot_Board", (sx + 0.1, sy + 1.8, sz - 0.5), (sx + 0.15, sy + 2.2, sz + 0.5), "sign")
    for k, what, x, z in TOYS:
        S.spot("toy", k, (x, hill_top(x, z), z), face=(0, 1), props={"what": what, "physics": "kickable"})
    for k, what, x, z in PUZZLES:
        S.spot("puzzle", k, (x, hill_top(x, z), z), face=(0, 1), props={"what": what})
    # one "more to come" facade standing alone on a rise, dreamcore
    fx, fz = -66.0, 2.0
    fy = min(hill_top(fx + dx, fz + dz) for dx in (-4.0, 0.0, 4.0) for dz in (-1.0, 0.0, 1.0))
    S.solid("Facade_1", (fx - 3.8, fy - 0.5, fz - 1.2), (fx + 3.8, fy + 6.0, fz), "facade")
    S.decor("Facade_1_Door", (fx - 0.6, fy, fz), (fx + 0.6, fy + 2.4, fz + 0.05), "fake_door")
    S.decor("Facade_1_Sign", (fx - 2.4, fy + 2.8, fz), (fx + 2.4, fy + 3.5, fz + 0.05), "sign")
    S.spot("facade", 1, (fx, hill_top(fx, fz + 1.5), fz + 1.5), face=(0, 1), props={"opens": "no", "what": "more to come, alone on a rise"})
    S.label("MORE TO COME", fx, fz + 6.0, kind="note")
    S.label("the way back (signpost)", ax, az + 6.0, kind="note")
    for k, what, x, z in TOYS:
        S.label(what, x, z + 4.0, kind="note")
    S.plan_sun = (55.0, 30.0)
    S.still = ((ax, y0, az), (-0.75, -1.0), 2)              # toward the highest tops, in the tile's north-west corner
    return S


# ---------------------------------------------------------------- the scenes and how they join
SCENES = {"table_and_chairs": table_and_chairs, "market": market, "playground": playground, "tree_house": tree_house,
          "bus_station": bus_station, "road": road, "endless_hills": endless_hills}

# Every link between two scenes of this set: (scene, door) <-> (scene, door). Pressing F at one side's Link_ (or walking through a walk gap)
# puts you on the other side's Arrive_.
PAIRS = [
    (("playground", "tree_house"), ("tree_house", "playground"), "walk", "the path west out of the playground, through the gap in its hedge"),
]


def _lot(x, z, fx, fz, ax=None, az=None):
    ax = x + 1.4 * fx if ax is None else ax
    az = z + 1.4 * fz if az is None else az
    return f"F at ({x:g}, 9.6, {z:g}), arrive at ({ax:g}, 9.6, {az:g}) facing ({fx:g}, {fz:g})"


def _att(sid, door, kind):
    """A set's Link_ or Arrive_ in parking_lot's frame."""
    sc, (ox, oy, oz), yaw = ATTACH[sid]
    S = SCENES[sid]()
    e = next(e for e in S.empties if e["name"] == f"{kind}_{door}")
    return (round(ox + e["pos"][0], 3), round(oy + e["pos"][1], 3), round(oz + e["pos"][2], 3))


# Links that leave this set: the other side is part 1's (the parking lot, the street, the forest; the coordinator wires them and cuts the lot's
# hedge gaps) or a reserved addon. (scene, door): (connector, link ids, where the other side is)
OUTSIDE = {
    ("market", "lot"): ("walk", "new: overworld.lot>market and overworld.market>lot",
                        "parking_lot's east edge, where the asphalt meets the grass (x 62, z 76): " + _lot(61.0, 76.0, -1, 0)),
    ("playground", "lot"): ("walk", "new: overworld.lot>playground and overworld.playground>lot",
                            "parking_lot's west edge, where the asphalt meets the grass (x -62, z 76): " + _lot(-61.0, 76.0, 1, 0)),
    ("road", "lot"): ("walk", "reused: overworld.lot>forest (the lot's door forest_road, now to the road's start) and forest.road>lot's arrival",
                      "parking_lot's south hedge at the old signpost (shared/forest.js FOREST_ROAD_LOT, F at (-30, 95.6)): "
                      + _lot(-30.0, 95.6, 0, -1, -30.0, 93.0) + "; a gap is cut in the hedge (x -34 to -26) for the road"),
    ("road", "forest"): ("walk", "reused: overworld.road>forest (planned); forest.road>lot comes back to the road's end",
                         "forest (dreamcore_forest, built): you arrive at (0, 0, 6) facing north (0, -1), as today. The forest's signpost "
                         "back (door road_back, F at (2.6, 0, 8.4)) arrives at the road's forest end, (0, 0, -476) facing (0, 1)"),
    ("endless_hills", "lot"): ("walk", "new: overworld.lot>hills and overworld.hills>lot",
                               "parking_lot's south hedge, a stile at x 30 (the old signpost's mirror image): " + _lot(30.0, 95.6, 0, -1, 30.0, 93.0)),
    ("tree_house", "addon"): ("gate", "reused: overworld.treehouse>addon (planned) to future_addon_treehouse (reserved)",
                              "the tree house addon, not built: the trunk door stays locked; coming back you stand in front of it, facing out"),
    ("bus_station", "bus_stop"): ("bus", "reused: overworld.bus>city and city.bus>overworld (built); only their lot-side points move",
                                  "street (city, built): the bus arrives at (3.6, 0, 4) facing (0, -1), as today. In parking_lot's frame the "
                                  "station's F is at {at} and the bus back arrives at {arr} facing (0, -1) (today: F within 3.4 m of "
                                  "(-42.4, 44.2), arrive (-41, 9.6, 43))"),
}


def outside_note(side):
    kind, ids, note = OUTSIDE[side]
    if side == ("bus_station", "bus_stop"):
        note = note.format(at=_att("bus_station", "bus_stop", "Link"), arr=_att("bus_station", "bus_stop", "Arrive"))
    return kind, ids, note


def build(sid):
    return SCENES[sid]()


def plan_views(S):
    """The plans to render: one per level, or a long scene's segments. Each is (key, level, x0, x1, z0, z1) with a margin, and its pixel size;
    the Blender render and the sheets share this mapping."""
    out = []
    if S.segments:
        for key, x0, x1, z0, z1 in S.segments:
            out.append(_view(key, 0.0, x0, x1, z0, z1, 1300.0))
        return out
    bs = [b for b in S.boxes if (b.get("art") and not b.get("zone")) or b["name"].startswith("decor_")]
    xs = [v for b in bs for v in (b["min"][0], b["max"][0])] + [v[0] for m in S.meshes for v in m["verts"][:1] + m["verts"][-1:]]
    zs = [v for b in bs for v in (b["min"][2], b["max"][2])] + [v[2] for m in S.meshes for v in m["verts"][:1] + m["verts"][-1:]]
    m = 2.0
    if S.plan_rect:
        x0, x1, z0, z1 = S.plan_rect
        return [_view(f"L{int(lv)}", lv, x0, x1, z0, z1, 1700.0) for lv in S.levels]
    for lv in S.levels:
        out.append(_view(f"L{int(lv)}", lv, min(xs) - m, max(xs) + m, min(zs) - m, max(zs) + m, 1700.0))
    return out


def _view(key, lv, x0, x1, z0, z1, ppm_target):
    span = max(x1 - x0, z1 - z0)
    ppm = ppm_target / span
    return {"key": key, "level": lv, "x0": x0, "x1": x1, "z0": z0, "z1": z1, "W": int(round((x1 - x0) * ppm)), "H": int(round((z1 - z0) * ppm)), "ppm": ppm}


def plan_hidden(S, b, level):
    """Is box b left out of the plan for `level`? (roofs, crowns and anything that starts 2.4 m or more above the level; on a one-level plan
    the steps always show)"""
    if "ceiling" in b["tags"]:
        return True
    if b["name"].startswith("Step_") and len(S.levels) == 1:
        return False
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
    items = sorted([("C", b["name"], b) for b in S.boxes if b.get("art") or b.get("zone")] + [("E", e["name"], e) for e in S.empties]
                   + [("D", d["name"], d) for d in S.doors] + [("K", "COL_" + b["name"], b) for b in S.boxes if b["col"]], key=lambda t: t[1])
    for kind, n, o in items:
        if kind == "K":
            out["colliders"].append({"s": o["name"], "min": [_r(v) for v in o["min"]], "max": [_r(v) for v in o["max"]]})
        elif kind == "C" and o.get("zone"):
            out["zones"].append({"kind": o["zone"], "name": n, "min": [_r(v) for v in o["min"]], "max": [_r(v) for v in o["max"]]})
        elif kind == "D":
            p = o["props"]
            d = {"name": n, "level": S.id, "hinge": [_r(v) for v in o["hinge"]], "width": float(p["width"]), "height": float(p["height"]),
                 "closed_yaw_deg": float(p["closed_yaw_deg"]), "swing_deg": float(p["swing_deg"]), "state": p["state"]}
            for k, v in p.items():
                if k not in d:
                    d[k] = v
            out["doors"].append(d)
        elif kind == "E":
            if n.startswith("Marker_"):
                out["markers"].append({"name": n[7:], "room": str(o["props"].get("room", S.id)), "level": S.id, "kind": o["props"].get("kind", "Spawn"),
                                       "position": [_r(v) for v in o["pos"]]})
            elif n.startswith("Link_"):
                a = empt["Arrive_" + n[5:]]
                out["links"].append({"door": n[5:], "at": [_r(v) for v in o["pos"]], "arrive": [_r(v) for v in a["pos"]], "face": _face(a["face"])})
            elif n.startswith("Spot_"):
                f = _face(o["face"])
                sp = {"kind": n.split("_")[1], "name": n, "position": [_r(v) for v in o["pos"]], "face": f,
                      "yaw_deg": round(math.degrees(math.atan2(f[0], f[1])), 1) + 0.0, "scale": float(o["props"].get("scale", 1.0))}
                for k, v in o["props"].items():
                    if k not in sp:
                        sp[k] = v
                out["spots"].append(sp)
    return out


def out_path(base, sid):
    return Path(base) / "world" / f"{sid}.json"


# ---------------------------------------------------------------- the gates on exported files (--check)
def glb_nodes(path):
    """The node names, extras and translations in a .glb (its JSON chunk), without Blender."""
    b = Path(path).read_bytes()
    n = struct.unpack_from("<I", b, 12)[0]
    doc = json.loads(b[20:20 + n].decode("utf-8"))
    return {nd.get("name", ""): {"extras": nd.get("extras", {}), "t": nd.get("translation", [0.0, 0.0, 0.0])} for nd in doc.get("nodes", [])}


def _inside(c, rect, e=0.005):
    x0, x1, z0, z1 = rect
    return c["min"][0] < x1 - e and c["max"][0] > x0 + e and c["min"][2] < z1 - e and c["max"][2] > z0 + e


def check(base, ids=None, glb_dir=None):
    """Links pair, every scene is reached, steps keep to the rise, corridors are wide and clear, each playground piece has its clear ground,
    the moving parts are separate objects on their pivots, and the hills tile's edges match. Reads <base>/world/<scene>.json (and the
    playground's GLB); prints one line per gate; True if all pass."""
    ids = ids or list(SCENES)
    docs, bad = {}, []
    for sid in ids:
        f = out_path(base, sid)
        if not f.exists():
            bad.append(f"missing {f}")
            continue
        docs[sid] = json.loads(f.read_text())
    models = {sid: build(sid) for sid in ids}
    have = {(sid, l["door"]) for sid, d in docs.items() for l in d.get("links", [])}
    paired = set()
    for a, b, kind, note in PAIRS:
        for side in (a, b):
            paired.add(side)
            if side[0] in docs and side not in have:
                bad.append(f"link {side[0]}.{side[1]} ({kind} to {b if side == a else a}) is not in {side[0]}.json")
    for side in sorted(have):
        if side not in paired and side not in OUTSIDE:
            bad.append(f"link {side[0]}.{side[1]} has no other side in PAIRS or OUTSIDE")
    for side in OUTSIDE:
        if side[0] in docs and side not in have:
            bad.append(f"link {side[0]}.{side[1]} (off this set) is not in {side[0]}.json")
    print(f"GATE links: {len(PAIRS)} pair inside the set ({len(PAIRS) * 2} sides), {len(OUTSIDE)} that leave it; {len(have)} links in the files, "
          f"every one accounted for")
    for side in sorted(OUTSIDE):
        kind, lid, note = outside_note(side)
        print(f"  off this set: {side[0]}.{side[1]} ({kind}) -> {note.split(':')[0]}  [{lid}]")
    # every scene is reached from parking_lot: through a link off this set that ends in the lot, a pair, or as a set attached to the lot
    graph = {sid: set() for sid in SCENES}
    for (a, _), (b, _), _, _ in PAIRS:
        graph[a].add(b)
        graph[b].add(a)
    roots = [s for (s, dd), (k, lid, note) in OUTSIDE.items() if note.startswith("parking_lot")] + [s for s in SCENES if s in ATTACH]
    seen, todo = set(), list(roots)
    while todo:
        s = todo.pop()
        if s not in seen:
            seen.add(s)
            todo += list(graph[s])
    if set(SCENES) - seen:
        bad.append(f"not reachable from parking_lot: {sorted(set(SCENES) - seen)}")
    print(f"GATE navigable: {len(seen)} of {len(SCENES)} scenes reachable from parking_lot (table_and_chairs and bus_station stand in it)")
    # steps: every Step_<flight>_<nn> collider, in order, keeps to MAX_RISE, from the ground it starts on to the floor it reaches; every kerb too
    nsteps, worst = 0, 0.0
    for sid in ids:
        S = models[sid]
        cols = {c["s"]: c for c in docs.get(sid, {}).get("colliders", [])}
        for fl in S.flights:
            steps = sorted((n, c) for n, c in cols.items() if n.startswith(f"Step_{fl['name']}_"))
            tops = [c["max"][1] for _, c in steps]
            seq = [fl["y_start"]] + tops + ([fl["y_end"]] if not tops or abs(tops[-1] - fl["y_end"]) > 1e-6 else [])
            rises = [abs(seq[i + 1] - seq[i]) for i in range(len(seq) - 1)]
            nsteps += len(steps)
            worst = max([worst] + rises)
            if len(steps) != fl["n"] or any(r > MAX_RISE + 1e-6 for r in rises):
                bad.append(f"steps {sid}/{fl['name']}: {len(steps)} boxes, rises {rises}")
        for kb in S.kerbs:
            c = cols.get(kb["name"])
            if c is None:
                bad.append(f"kerb {sid}/{kb['name']} is not in the file")
                continue
            r = c["max"][1] - kb["from"]
            nsteps += 1
            worst = max(worst, r)
            if r > MAX_RISE + 1e-6:
                bad.append(f"kerb {sid}/{kb['name']} rises {r:.3f} m")
    nk = sum(len(models[s].kerbs) for s in ids)
    print(f"GATE steps: {nsteps - nk} step boxes in {sum(len(models[s].flights) for s in ids)} flights, one box a step, and {nk} kerbs; the highest "
          f"rise {worst:.3f} m (at most {MAX_RISE} m)")
    # the hills: no two neighbouring columns differ by more than MAX_RISE, across the tile's seams too (the tile repeats)
    if "endless_hills" in docs:
        cols = [c for c in docs["endless_hills"]["colliders"] if c["s"].startswith("Ground_Hills_")]
        grid = {(round((c["min"][0] + HILL_HALF) / HILL_CELL), round((c["min"][2] + HILL_HALF) / HILL_CELL)): c["max"][1] for c in cols}
        n = int(round(2 * HILL_HALF / HILL_CELL))
        hw = max(abs(grid[(i, j)] - grid[((i + di) % n, (j + dj) % n)]) for i in range(n) for j in range(n) for di, dj in ((1, 0), (0, 1)))
        if len(grid) != n * n or hw > MAX_RISE + 1e-6:
            bad.append(f"hills: {len(grid)} columns, the highest rise between neighbours {hw:.3f} m")
        print(f"GATE hills steps: {len(grid)} columns of {HILL_CELL:g} m; the highest rise between neighbours {hw:.3f} m, seams included (at most {MAX_RISE} m)")
    # corridors: at least MIN_CORRIDOR wide, and no standing collider inside
    ncor, narrow = 0, 99.0
    for sid in ids:
        S = models[sid]
        cols = docs.get(sid, {}).get("colliders", [])
        for c in S.corridors:
            ncor += 1
            w = min(c["max"][0] - c["min"][0], c["max"][2] - c["min"][2])
            narrow = min(narrow, w)
            if w < MIN_CORRIDOR - 1e-6:
                bad.append(f"corridor {sid}/{c['name']} is {w:.2f} m wide")
            y = c["min"][1]
            for k in cols:
                e = 0.005                                    # the files are rounded to the millimetre
                if k["min"][1] < y + 1.5 and k["max"][1] > y + 0.5 and k["min"][0] < c["max"][0] - e and k["max"][0] > c["min"][0] + e \
                        and k["min"][2] < c["max"][2] - e and k["max"][2] > c["min"][2] + e:
                    bad.append(f"corridor {sid}/{c['name']}: {k['s']} stands in it")
                    break
    print(f"GATE corridors: {ncor} path, aisle, platform and gap rects, the narrowest {narrow:.2f} m (at least {MIN_CORRIDOR} m), none blocked")
    # the playground: every piece has its own clear ground (no other piece's collider, bench, lamp or hedge in it, no two overlapping)
    if "playground" in docs:
        S = models["playground"]
        cols = docs["playground"]["colliders"]
        prefix = {"swing": "Swing_", "slide": ("Slide_", "Step_slide_"), "seesaw": "Seesaw_", "merry_go_round": "MGR_",
                  "monkey_bars": ("MonkeyBars_", "Step_monkey_"), "sandbox": "Sandbox_", "spring_riders": "Rider", "climbing_frame": ("Frame_", "Step_frame_")}
        for c in S.clear:
            own = prefix[c["equipment"]]
            for k in cols:
                if k["s"].startswith("Ground_") or k["s"].startswith(own):
                    continue
                if _inside(k, c["rect"]):
                    bad.append(f"clear ground {c['equipment']}: {k['s']} is in it")
                    break
        for i, a in enumerate(S.clear):
            for b in S.clear[i + 1:]:
                if _inside({"min": [a["rect"][0], 0, a["rect"][2]], "max": [a["rect"][1], 0, a["rect"][3]]}, b["rect"]):
                    bad.append(f"clear ground {a['equipment']} and {b['equipment']} overlap")
        # each moving part's reach stays on its piece's clear ground
        for p in S.parts:
            zone = next(c["rect"] for c in S.clear if c["equipment"] == p["props"]["equipment"])
            px, _, pz = p["pivot"]
            reach = max(math.hypot(v[0] - px, v[2] - pz) for a, b, m in p["boxes"] for v in (a, b))
            if p["props"]["motion"] == "pendulum":
                reach = max(reach, max(abs(a[1] - p["pivot"][1]) for a, b, m in p["boxes"]))
            if px - reach < zone[0] or px + reach > zone[1] or pz - reach < zone[2] or pz + reach > zone[3]:
                bad.append(f"moving part {p['name']} reaches {reach:.2f} m, past its clear ground")
        print(f"GATE clear ground: {len(S.clear)} pieces, each on its own clear ground with no other collider in it, none overlapping, every "
              f"moving part's reach inside its own")
    # the moving parts: separate Play_<equipment>_<part> nodes in the playground's GLB, each with its origin at its pivot
    if "playground" in ids:
        S = models["playground"]
        dirs = [Path(glb_dir)] if glb_dir else [Path(base) / "glb", Path(base) / "docs/renders/overworld_greybox/glb"]
        g = next((d / "playground.glb" for d in dirs if (d / "playground.glb").exists()), None)
        if g is None:
            print("GATE moving parts: no playground.glb next to the layout files (a --preview run): skipped")
        else:
            nodes = glb_nodes(g)
            off = []
            for p in S.parts:
                nd = nodes.get(p["name"])
                if nd is None:
                    off.append(f"{p['name']} missing")
                elif max(abs(nd["t"][i] - p["pivot"][i]) for i in range(3)) > 0.002:
                    off.append(f"{p['name']} at {nd['t']}, pivot {p['pivot']}")
                elif nd["extras"].get("equipment") != p["props"]["equipment"]:
                    off.append(f"{p['name']} has no equipment property")
            if off:
                bad.append("moving parts: " + "; ".join(off))
            eqs = sorted({p["props"]["equipment"] for p in S.parts})
            print(f"GATE moving parts: {len(S.parts) - len(off)} of {len(S.parts)} Play_<equipment>_<part> nodes in playground.glb on their pivots "
                  f"({len(eqs)} pieces: {', '.join(eqs)}; the slide and the monkey bars have none)")
    # the hills tile: its edges match. Columns along opposite edges have the same tops; the surface's edge rows are the same height
    if "endless_hills" in docs:
        cols = [c for c in docs["endless_hills"]["colliders"] if c["s"].startswith("Ground_Hills_")]
        xs = [v for c in cols for v in (c["min"][0], c["max"][0])]
        zs = [v for c in cols for v in (c["min"][2], c["max"][2])]
        span = (min(xs), max(xs), min(zs), max(zs))
        n = int(round(2 * HILL_HALF / HILL_CELL))
        grid = {(round((c["min"][0] + HILL_HALF) / HILL_CELL), round((c["min"][2] + HILL_HALF) / HILL_CELL)): c["max"][1] for c in cols}
        dx = max(abs(grid[(0, j)] - grid[(n - 1, j)]) for j in range(n))
        dz = max(abs(grid[(i, 0)] - grid[(i, n - 1)]) for i in range(n))
        S = models["endless_hills"]
        m = int(round(2 * HILL_HALF / HILL_ART))
        vs = S.meshes[0]["verts"]
        sx = max(abs(vs[j * (m + 1)][1] - vs[j * (m + 1) + m][1]) for j in range(m + 1))
        sz = max(abs(vs[i][1] - vs[m * (m + 1) + i][1]) for i in range(m + 1))
        slope = max(abs((hill_h(-HILL_HALF + 0.01, z) - hill_h(-HILL_HALF, z)) - (hill_h(HILL_HALF + 0.01, z) - hill_h(HILL_HALF, z)))
                    for z in [-HILL_HALF + k for k in range(0, 201, 5)])
        ok = span == (-HILL_HALF, HILL_HALF, -HILL_HALF, HILL_HALF) and dx < 1e-6 and dz < 1e-6 and sx < 1e-9 and sz < 1e-9 and slope < 1e-9
        if not ok:
            bad.append(f"hills edges: span {span}, columns west/east {dx}, north/south {dz}, surface {sx} {sz}, slope {slope}")
        tops = [c["max"][1] for c in cols]
        print(f"GATE hills tile: x {span[0]:g} to {span[1]:g}, z {span[2]:g} to {span[3]:g}; the {n} column tops along the west edge equal the east "
              f"edge's (largest difference {dx:.3f} m) and the north edge's the south's ({dz:.3f} m); the surface's edge rows match "
              f"({max(sx, sz):.1e} m) and so do the slopes across each seam; heights {min(tops):.2f} to {max(tops):.2f} m")
    nsp = {}
    for d in docs.values():
        for s in d.get("spots", []):
            nsp[s["kind"]] = nsp.get(s["kind"], 0) + 1
    print("  spots: " + ", ".join(f"{k} x{v}" for k, v in sorted(nsp.items())))
    for b in bad:
        print("  FAIL", b)
    print("GATES", "FAIL" if bad else "PASS")
    return not bad


# ================================================================ Blender
def _blender_main(argv):
    import bpy
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import export_scene
    from mathutils import Matrix, Vector

    a = argv
    ids = list(SCENES) if "--scenes" not in a or a[a.index("--scenes") + 1] == "all" else a[a.index("--scenes") + 1].split(",")
    base = Path(a[a.index("--out") + 1]) if "--out" in a else ROOT / "work/overworld_greybox"
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
            bsdf.inputs["Roughness"].default_value = 0.8 if name not in ("glass", "window") else 0.04
            if name == "glass":
                for key in ("Transmission Weight", "Transmission"):
                    if key in bsdf.inputs:
                        bsdf.inputs[key].default_value = 1.0
                        break
                if "IOR" in bsdf.inputs:
                    bsdf.inputs["IOR"].default_value = 1.05
            if name in ("lamp",):
                for key in ("Emission Color", "Emission"):
                    if key in bsdf.inputs:
                        bsdf.inputs[key].default_value = (*c, 1.0)
                        break
                if "Emission Strength" in bsdf.inputs:
                    bsdf.inputs["Emission Strength"].default_value = 1.5
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

    leaf_me = bpy.data.meshes.new("GB_door_leaf")
    v = [(x, y, z) for x in (0, 1) for y in (-0.025, 0.025) for z in (0, 1)]
    leaf_me.from_pydata(v, [], [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
    leaf_me.update()
    leaf_me.materials.append(mat("door"))

    sc = bpy.context.scene
    coll = {}
    for cn in ("Art", "Layout", "Context"):
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
        for me in list(bpy.data.meshes):
            if me.users == 0 and (me.name.startswith("GB_part_") or me.name.startswith("GB_mesh_")):
                bpy.data.meshes.remove(me)

    def boxobj(name, b, coll_name, hide=False):
        ob = bpy.data.objects.new(name, cube(b["mat"]))
        mn, mx = b["min"], b["max"]
        ob.location = (mn[0], -mx[2], mn[1])
        ob.scale = (mx[0] - mn[0], mx[2] - mn[2], mx[1] - mn[1])
        coll[coll_name].objects.link(ob)
        ob.hide_render = hide
        return ob

    def part_obj(p):
        """A Play_ part: one mesh of its boxes, its vertices relative to the pivot, the object at the pivot (so its origin is the pivot)."""
        bm_v, bm_f, mat_idx, mlist = [], [], [], []
        piv = B(p["pivot"])
        for mn, mx, mname in p["boxes"]:
            if mname not in mlist:
                mlist.append(mname)
            base_i = len(bm_v)
            for x in (mn[0], mx[0]):
                for y in (mn[1], mx[1]):
                    for z in (mn[2], mx[2]):
                        bm_v.append(tuple(B((x, y, z)) - piv))
            for f in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
                bm_f.append(tuple(base_i + k for k in f))
                mat_idx.append(mlist.index(mname))
        me = bpy.data.meshes.new("GB_part_" + p["name"])
        me.from_pydata(bm_v, [], bm_f)
        for mname in mlist:
            me.materials.append(mat(mname))
        for i, poly in enumerate(me.polygons):
            poly.material_index = mat_idx[i]
            poly.use_smooth = False
        me.validate()
        me.update()
        ob = bpy.data.objects.new(p["name"], me)
        ob.location = piv
        for k, val in p["props"].items():
            ob[k] = val
        ob["pivot"] = [round(v, 3) for v in p["pivot"]]
        coll["Art"].objects.link(ob)
        return ob

    def mesh_obj(m):
        me = bpy.data.meshes.new("GB_mesh_" + m["name"])
        me.from_pydata([tuple(B(v)) for v in m["verts"]], [], m["faces"])
        me.materials.append(mat(m["mat"]))
        for poly in me.polygons:
            poly.use_smooth = True
        me.update()
        ob = bpy.data.objects.new(m["name"], me)
        coll["Art"].objects.link(ob)
        return ob

    def realize(S):
        clear()
        arts = []
        for b in S.boxes:
            if b.get("zone"):
                ob = boxobj(b["name"], b, "Layout", hide=True)
                ob.display_type = "WIRE"
                continue
            if b.get("ctx"):
                ob = boxobj(b["name"], b, "Context")
                arts.append((ob, b))
                continue
            if b.get("art", True):
                ob = boxobj(b["name"], b, "Art")
                arts.append((ob, b))
            if b["col"]:
                ob = boxobj("COL_" + b["name"], b, "Layout", hide=True)
                ob.display_type = "WIRE"
        for p in S.parts:
            ob = part_obj(p)
            mn = [min(bx[0][i] for bx in p["boxes"]) for i in range(3)]
            arts.append((ob, {"min": mn, "tags": set(), "name": p["name"]}))
        for m in S.meshes:
            ob = mesh_obj(m)
            arts.append((ob, {"min": [0, -99.0, 0], "tags": set(), "name": m["name"]}))
        for d in S.doors:
            ob = bpy.data.objects.new(d["name"], leaf_me)
            ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z") @ Matrix.Diagonal((d["props"]["width"], 1, d["props"]["height"], 1))
            for k, val in d["props"].items():
                ob[k] = val
            coll["Art"].objects.link(ob)
            arts.append((ob, {"min": [0, d["hinge"][1], 0], "tags": set(), "name": d["name"]}))
        for e in S.empties:
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

    def render_plan(S, arts, pv, path):
        level = pv["level"]
        for ob, b in arts:
            ob.hide_render = plan_hidden(S, b, level) if "tags" in b and b.get("name") else False
        for ob in list(bpy.data.objects):
            if ob.type in ("LIGHT", "CAMERA"):
                bpy.data.objects.remove(ob, do_unlink=True)
        world((1.0, 1.0, 1.0), 0.45)
        a0, a1 = S.plan_sun
        add_light("SUN", (0, 0, 50), 1.6 if a0 < 10 else 2.6, "Plan_Sun", rot=(math.radians(a0), math.radians(a1), 0))
        cam = camera("Plan_Cam")
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = max(pv["x1"] - pv["x0"], pv["z1"] - pv["z0"])
        cam.data.sensor_fit = "AUTO"
        cam.data.clip_start, cam.data.clip_end = 0.1, 400.0
        cam.location = ((pv["x0"] + pv["x1"]) / 2, -(pv["z0"] + pv["z1"]) / 2, level + 60.0)
        cam.rotation_euler = (0, 0, 0)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = pv["W"], pv["H"], 100
        sc.cycles.samples = 24
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)

    def render_still(S, arts, path):
        for ob, b in arts:
            ob.hide_render = False
        for ob in list(bpy.data.objects):
            if ob.type in ("LIGHT", "CAMERA"):
                bpy.data.objects.remove(ob, do_unlink=True)
        world((0.50, 0.70, 0.98), 0.55)                                     # one clear-day greybox sky for every still; the four skies are R3
        add_light("SUN", (0, 0, 50), 1.9, "Still_Sun", rot=(math.radians(38), math.radians(18), math.radians(35)))
        for i, (x, y, z, p) in enumerate(S.lights):
            add_light("POINT", B((x, y, z)), p, f"L{i}", size=0.4)
        (pos, face, pitch) = S.still
        cam = camera("Still_Cam")
        cam.data.lens, cam.data.sensor_width = 16.0, 36.0
        cam.data.clip_start, cam.data.clip_end = 0.05, 900.0
        cam.location = B((pos[0], pos[1] + EYE, pos[2]))
        yaw = math.atan2(face[0], face[1])                                 # the -Y (empty) convention: a camera looks down its -Z
        cam.rotation_euler = (math.radians(90 + pitch), 0, math.pi + yaw)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1600, 900, 100
        sc.cycles.samples = 64
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)

    def export_glb(arts, path):
        bpy.ops.object.select_all(action="DESELECT")
        for ob, b in arts:
            if b.get("ctx"):
                continue
            ob.hide_render = False
            ob.select_set(True)
        bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_extras=True, export_yup=True,
                                  export_apply=False, export_materials="EXPORT", export_cameras=False, export_lights=False)

    dev = setup_cycles(48)
    print("OVERWORLD_GREYBOX device", dev, "scenes", len(ids))
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
        print(f"OVERWORLD_GREYBOX done {sid}: {len(S.boxes)} boxes, {len(S.parts)} parts, {len(S.doors)} doors, {len(S.empties)} empties")
    print("OVERWORLD_GREYBOX ALL DONE")


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
        sys.exit(0 if check(Path(a[a.index("--check") + 1]), glb_dir=a[a.index("--glb") + 1] if "--glb" in a else None) else 1)
    else:
        print(__doc__)
