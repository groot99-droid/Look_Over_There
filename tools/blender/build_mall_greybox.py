"""The mall greybox (docs/BLENDER_AREAS.md, section 3, "The mall"): the eighteen scenes beyond part 1's `entrance` (the atrium) as plain grey
boxes, to scale, with the names the exporter reads (COL_, DoorLeaf_, Marker_, Link_/Arrive_, Zone_, Spot_, decor_) and the bathroom's
`Mirror_<n>` objects, so the owner can review the whole layout at once. It follows tools/blender/build_hotel_greybox.py and
tools/blender/build_grocery_greybox.py.

    blender -b --factory-startup --python tools/blender/build_mall_greybox.py -- [--scenes all|id,id,...] [--out <dir>] [--no-render]
    python tools/blender/build_mall_greybox.py --check <dir>      the gates on exported files, no Blender (links meet, steps, corridors, mirrors)
    python tools/blender/build_mall_greybox.py --preview <dir>    writes the layout files from the model alone, no Blender (for --check)

For each scene the Blender run builds the boxes into an empty file, writes <out>/world/<scene>.json through tools/blender/export_scene.py,
the greybox art to <out>/glb/<scene>.glb, a top-down orthographic plan per level (<out>/renders/<scene>_plan_L<y>.png, ceilings and
everything 2.4 m above the level hidden) and one eye-height still (1.55 m, <out>/renders/<scene>_still.png). The labels, scale bar and sheets
are drawn afterwards by tools/blender/mall_greybox_sheets.py from this same model.

Coordinates are GAME coordinates (metres, y up, north = -z); Blender (x, y, z) is game (x, -z, y). Every scene has its floor at y = 0 and its
own frame. The three wings are built along x with the atrium at the west end and then turned so that their north is the mall's (entrance's)
north: wing_books runs north from the atrium (turned 90 degrees), wing_cinema west (180), wing_entertainment east (0). The atrium itself is
part 1's (shared/city.js MALL, world/entrance.json: x -16 to 16, z -12 to 12, 7 m high, shopfronts SHOES, PHONES, FOOD COURT and CLOSED FOR
RENOVATION on the north wall at x -11, -4, 4 and 11, GIFTS and PHOTO on the west wall and OPTICIAN and TOYS on the east wall at z -6 and 4); it is
read here, never written. Its side of each link is listed in OUTSIDE for the coordinator.

The sky halls are the connector kit's painted-sky hall (branch claude/blender-hotel-kit: blender/kit/README.md, world/kit/sky_hall.json) as
plain boxes in the kit's own frame (the entry door's opening at the origin, the hall toward -z, 10 m by 2.4 m by 3.0 m), with the kit's door,
link and marker names, so the kit piece drops in at (0, 0, 0), yaw 0. Repetition reuses one mesh: every box is the same unit cube per material,
scaled (colliders and art share it), and every door leaf is one leaf mesh. Each COL_<name> box has its art twin <name>; decor_ boxes and the
mirrors have no collider. Zones are hidden boxes. Nothing here touches the manifest, index.html or shared/.
"""
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EYE = 1.55
T = 0.2                     # wall thickness
SLAB = 0.3                  # floor slab under every floor
DOOR_W, DOOR_H = 0.94, 2.16
KIT_W, KIT_LEAF, KIT_H = 1.1, 1.04, 2.12   # the kit's sky-hall door: a 1.1 m opening, a 1.04 m by 2.12 m leaf
MAX_RISE = 0.27
MIN_CORRIDOR = 1.6
WALKER_R = 0.28

MATS = {                    # flat greybox colours (linear RGB); no textures
    "floor": (0.58, 0.58, 0.56), "wall": (0.30, 0.30, 0.32), "ceiling": (0.62, 0.62, 0.62), "door": (0.62, 0.36, 0.16),
    "stair": (0.50, 0.46, 0.38), "furniture": (0.55, 0.47, 0.34), "counter": (0.42, 0.33, 0.24), "rail": (0.18, 0.18, 0.2),
    "tile": (0.80, 0.83, 0.85), "marble": (0.70, 0.68, 0.64), "glass": (0.70, 0.85, 0.90), "column": (0.45, 0.45, 0.45),
    "fake_door": (0.40, 0.28, 0.20), "lift": (0.30, 0.38, 0.52), "shutter": (0.36, 0.37, 0.40), "sign": (0.85, 0.80, 0.55),
    "sheet": (0.86, 0.85, 0.80), "scaffold": (0.60, 0.60, 0.62), "plank": (0.62, 0.46, 0.22), "hoarding": (0.66, 0.55, 0.36),
    "concrete": (0.50, 0.50, 0.49), "sky": (0.30, 0.52, 0.86), "mural": (0.55, 0.68, 0.80), "cobble": (0.42, 0.40, 0.38),
    "facade_a": (0.72, 0.55, 0.42), "facade_b": (0.78, 0.70, 0.52), "padding": (0.80, 0.30, 0.20), "carpet_red": (0.42, 0.16, 0.14),
    "carpet_blue": (0.14, 0.20, 0.40), "mirror": (0.90, 0.92, 0.94), "bookcase": (0.36, 0.24, 0.14), "parquet": (0.55, 0.38, 0.22),
    "exit": (0.10, 0.70, 0.25), "plant": (0.20, 0.42, 0.22), "hazard": (0.85, 0.65, 0.05), "water": (0.12, 0.38, 0.80),
}


# ================================================================ the model (pure Python; no bpy)
class Scene:
    def __init__(s, sid, title, size, levels=(0.0,), mood=""):
        s.id, s.title, s.size, s.levels, s.mood = sid, title, size, list(levels), mood
        s.boxes, s.empties, s.doors, s.labels, s.lights, s.corridors, s.flights, s.outlines = [], [], [], [], [], [], [], []
        s.links = {}            # door id -> text (where it goes), for the plan labels
        s.still = None          # (pos, face, pitch_deg)
        s.level_names = {}
        s.turn_deg = 0.0        # the wings: how far the built frame was turned (three's rotation.y)
        s._names = set()

    def uniq(s, n):
        base, k = n, 1
        while n in s._names:
            k += 1
            n = f"{base}_{k}"
        s._names.add(n)
        return n

    def solid(s, name, mn, mx, mat="wall", tags=()):
        if any(mn[i] >= mx[i] - 1e-6 for i in range(3)):
            return None
        n = s.uniq(name)
        s.boxes.append({"name": n, "min": [float(v) for v in mn], "max": [float(v) for v in mx], "mat": mat, "col": True, "tags": set(tags)})
        return n

    def decor(s, name, mn, mx, mat="furniture", tags=()):
        n = s.uniq("decor_" + name)
        s.boxes.append({"name": n, "min": [float(v) for v in mn], "max": [float(v) for v in mx], "mat": mat, "col": False, "tags": set(tags)})

    def art(s, name, mn, mx, mat, props=None):
        """An art-only object with its own name and custom properties (the bathroom's Mirror_<n>): no collider, no decor_ prefix."""
        n = s.uniq(name)
        s.boxes.append({"name": n, "min": [float(v) for v in mn], "max": [float(v) for v in mx], "mat": mat, "col": False, "tags": {"art"},
                        "props": dict(props or {})})

    def zone(s, kind, name, mn, mx):
        n = s.uniq(f"Zone_{kind}_{name}")
        s.boxes.append({"name": n, "min": list(mn), "max": list(mx), "mat": "hazard", "col": False, "zone": kind, "tags": set()})

    def empty(s, name, pos, face=None, props=None):
        s.empties.append({"name": s.uniq(name), "pos": [float(v) for v in pos], "face": face, "props": dict(props or {})})

    def link(s, door, at, arrive, face, to=""):
        s.empty(f"Link_{door}", at)
        s.empty(f"Arrive_{door}", arrive, face=face)
        s.links[door] = to

    def spot(s, kind, n, pos, face=(0, 1), props=None):
        s.empty(f"Spot_{kind}_{n}", pos, face=face, props=props)

    def mannequin(s, n, pos, face, role, what):
        """Spot_mannequin_<n>: the page draws a mannequin here. role: dressing (it never moves), npc (it can be spoken to) or monster (it moves
        while unseen), the mall's three kinds (docs/WORLD.md); what: how it stands."""
        s.spot("mannequin", n, pos, face=face, props={"role": role, "what": what})

    def marker(s, name, pos, kind="Spawn", props=None):
        p = {"kind": kind}
        p.update(props or {})
        s.empty(f"Marker_{name}", pos, props=p)

    def door(s, name, hinge, run, into, width=DOOR_W, height=DOOR_H, state="closed", props=None, swing=None):
        """A leaf with its origin at the hinge. `run`: the game direction (x, z) from the hinge along the closed leaf; `into`: the side it
        opens toward. closed_yaw_deg is three.js's rotation.y of the leaf (its local +x runs from the hinge along it); +swing_deg opens it
        toward `into` (the galleries' convention). `swing` overrides the size of the swing (the kit's doors swing 90)."""
        th = math.atan2(-run[1], run[0])
        op = math.atan2(-into[1], into[0])
        mag = 95.0 if swing is None else float(swing)
        sw = mag if math.sin(op - th) > 0 else -mag
        p = {"width": round(width, 3), "height": round(height, 3), "closed_yaw_deg": round(math.degrees(th), 1), "swing_deg": sw, "state": state}
        p.update(props or {})
        s.doors.append({"name": s.uniq("DoorLeaf_" + name), "hinge": [float(v) for v in hinge], "yaw": th, "props": p})

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
    """n steps from a floor at y_start up to y_end, one box per step (each as thick as its rise, so a flight above another leaves headroom).
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


def box(S, name, x0, x1, z0, z1, y0, y1, mat="furniture"):
    return S.solid(name, (x0, y0, z0), (x1, y1, z1), mat)


def double_door(S, name, axis, at, c0, into, width=1.6, height=2.2, y=0.0, props=None):
    """A pair of leaves filling a `width` opening centred on `at` along a wall on `axis` ('z': the wall runs along z at x = c0; 'x': along x at
    z = c0); `into` is the side they open toward."""
    half = width / 2
    p = dict(props or {})
    if axis == "z":
        S.door(f"{name}_A", (c0, y, at - half), (0, 1), into, width=half, height=height, props=p)
        S.door(f"{name}_B", (c0, y, at + half), (0, -1), into, width=half, height=height, props=p)
    else:
        S.door(f"{name}_A", (at - half, y, c0), (1, 0), into, width=half, height=height, props=p)
        S.door(f"{name}_B", (at + half, y, c0), (-1, 0), into, width=half, height=height, props=p)


def kit_door(S, name, side, a, c0, y=0.0, props=None):
    """A sky-hall door in a host scene: the kit's 1.04 m by 2.12 m leaf in its 1.1 m opening (the hole is cut by the caller), hinged at the
    left of the opening as you face out, opening into the host. side: the wall it is in (N, S, W, E); a: its centre along the wall; c0: the
    wall's inner face."""
    p = {"kind": "sky hall door"}
    p.update(props or {})
    h = KIT_LEAF / 2
    if side == "N":
        S.door(name, (a - h, y, c0), (1, 0), (0, 1), width=KIT_LEAF, height=KIT_H, props=p, swing=90)
    elif side == "S":
        S.door(name, (a + h, y, c0), (-1, 0), (0, -1), width=KIT_LEAF, height=KIT_H, props=p, swing=90)
    elif side == "W":
        S.door(name, (c0, y, a + h), (0, -1), (1, 0), width=KIT_LEAF, height=KIT_H, props=p, swing=90)
    else:
        S.door(name, (c0, y, a - h), (0, 1), (-1, 0), width=KIT_LEAF, height=KIT_H, props=p, swing=90)


def single_door(S, name, side, a, c0, y=0.0, width=DOOR_W, height=DOOR_H, props=None):
    """One leaf in a hole on `side` (N, S, W, E) centred on `a`, hinged on the wall's inner face c0, opening into the room."""
    h = width / 2
    if side == "N":
        S.door(name, (a - h, y, c0), (1, 0), (0, 1), width=width, height=height, props=props)
    elif side == "S":
        S.door(name, (a + h, y, c0), (-1, 0), (0, -1), width=width, height=height, props=props)
    elif side == "W":
        S.door(name, (c0, y, a + h), (0, -1), (1, 0), width=width, height=height, props=props)
    else:
        S.door(name, (c0, y, a - h), (0, 1), (-1, 0), width=width, height=height, props=props)


def door_link(S, did, side, a, c0, to, y=0.0, near=0.6, far=1.3):
    """The Link_ (F) just inside a door on `side`, and the Arrive_ a step further in, facing into the room."""
    if side == "N":
        S.link(did, (a, y, c0 + near), (a, y, c0 + far), (0, 1), to)
    elif side == "S":
        S.link(did, (a, y, c0 - near), (a, y, c0 - far), (0, -1), to)
    elif side == "W":
        S.link(did, (c0 + near, y, a), (c0 + far, y, a), (1, 0), to)
    else:
        S.link(did, (c0 - near, y, a), (c0 - far, y, a), (-1, 0), to)


def shutter_front(S, name, side, a, c0, sign, width=4.8, height=3.2):
    """A shuttered shopfront on a wall's inner face: the shutter (solid, 0.12 m), the sign over it (art), its name on the plan."""
    w = width / 2
    if side == "N":
        S.solid(f"Shutter_{name}", (a - w, 0.0, c0), (a + w, height, c0 + 0.12), "shutter")
        S.decor(f"Sign_{name}", (a - w + 0.2, height + 0.25, c0), (a + w - 0.2, height + 0.85, c0 + 0.08), "sign")
        S.label(sign, a, c0 + 1.0, kind="note")
    elif side == "S":
        S.solid(f"Shutter_{name}", (a - w, 0.0, c0 - 0.12), (a + w, height, c0), "shutter")
        S.decor(f"Sign_{name}", (a - w + 0.2, height + 0.25, c0 - 0.08), (a + w - 0.2, height + 0.85, c0), "sign")
        S.label(sign, a, c0 - 1.0, kind="note")
    elif side == "W":
        S.solid(f"Shutter_{name}", (c0, 0.0, a - w), (c0 + 0.12, height, a + w), "shutter")
        S.decor(f"Sign_{name}", (c0, height + 0.25, a - w + 0.2), (c0 + 0.08, height + 0.85, a + w - 0.2), "sign")
        S.label(sign, c0 + 1.2, a, kind="note")
    else:
        S.solid(f"Shutter_{name}", (c0 - 0.12, 0.0, a - w), (c0, height, a + w), "shutter")
        S.decor(f"Sign_{name}", (c0 - 0.08, height + 0.25, a - w + 0.2), (c0, height + 0.85, a + w - 0.2), "sign")
        S.label(sign, c0 - 1.2, a, kind="note")


def sheeted(S, name, x0, x1, z0, z1, h, mat="sheet"):
    """Something under a dust sheet: one solid box in the sheet's colour."""
    return box(S, f"Sheeted_{name}", x0, x1, z0, z1, 0.0, h, mat)


def scaffold(S, name, x0, x1, z0, z1, decks=(2.0, 4.0), sheet=False, bay=2.0):
    """A scaffold run (tube posts, plank decks, a guard rail on each deck) over [x0, x1] x [z0, z1], posts at both z edges every `bay` m along
    x. `sheet`: a dust sheet hung down the open (z1) face, art only."""
    n = max(1, int(round((x1 - x0) / bay)))
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / n
        for z in (z0, z1):
            S.solid(f"Scaffold_{name}_Post", (x - 0.05, 0.0, z - 0.05), (x + 0.05, decks[-1] + 1.0, z + 0.05), "scaffold")
    for d in decks:
        S.solid(f"Scaffold_{name}_Deck", (x0, d - 0.06, z0), (x1, d, z1), "plank")
        S.solid(f"Scaffold_{name}_Rail", (x0, d + 0.95, z1 - 0.04), (x1, d + 1.0, z1 + 0.04), "scaffold")
    if sheet:
        S.decor(f"DustSheet_{name}", (x0, 0.5, z1 + 0.06), (x1, decks[-1], z1 + 0.08), "sheet")
    S.outlines.append({"x0": x0, "x1": x1, "z0": z0, "z1": z1, "text": "scaffold"})


def turn(S, deg):
    """Turn a whole scene about y by `deg` (three's rotation.y): a point (x, z) goes to (x cos + z sin, -x sin + z cos)."""
    th = math.radians(deg)
    c, s = round(math.cos(th), 12), round(math.sin(th), 12)
    R = lambda x, z: (x * c + z * s + 0.0, -x * s + z * c + 0.0)

    def rbox(mn, mx):
        (ax, az), (bx, bz) = R(mn[0], mn[2]), R(mx[0], mx[2])
        mn[0], mx[0] = min(ax, bx), max(ax, bx)
        mn[2], mx[2] = min(az, bz), max(az, bz)
    for b in S.boxes:
        rbox(b["min"], b["max"])
    for cdr in S.corridors:
        rbox(cdr["min"], cdr["max"])
    for e in S.empties:
        e["pos"][0], e["pos"][2] = R(e["pos"][0], e["pos"][2])
        if e["face"]:
            e["face"] = R(*e["face"])
    for d in S.doors:
        d["hinge"][0], d["hinge"][2] = R(d["hinge"][0], d["hinge"][2])
        d["yaw"] += th
        y = math.degrees(d["yaw"]) % 360.0
        d["props"]["closed_yaw_deg"] = round(y - 360.0 if y > 180.0 + 1e-6 else y, 1) + 0.0
    for lb in S.labels:
        lb["x"], lb["z"] = R(lb["x"], lb["z"])
    S.lights = [(R(x, z)[0], y, R(x, z)[1], p) for x, y, z, p in S.lights]
    for o in S.outlines:
        (ax, az), (bx, bz) = R(o["x0"], o["z0"]), R(o["x1"], o["z1"])
        o["x0"], o["x1"], o["z0"], o["z1"] = min(ax, bx), max(ax, bx), min(az, bz), max(az, bz)
    pos, face, pitch = S.still
    px, pz = R(pos[0], pos[2])
    S.still = ((px, pos[1], pz), R(*face), pitch)
    S.turn_deg = deg


# ---------------------------------------------------------------- the atrium (part 1: shared/city.js MALL, world/entrance.json; read only)
ATRIUM = {"x0": -16.0, "x1": 16.0, "z0": -12.0, "z1": 12.0, "h": 7.0,
          "fronts": {"SHOES": ("N", -11.0), "PHONES": ("N", -4.0), "FOOD COURT": ("N", 4.0), "CLOSED FOR RENOVATION": ("N", 11.0),
                     "GIFTS": ("W", -6.0), "PHOTO": ("W", 4.0), "OPTICIAN": ("E", -6.0), "TOYS": ("E", 4.0)},
          "front_w": 4.8}
WING_DOOR_W, WING_DOOR_H = 2.4, 2.6      # the glass doors between the atrium and each wing


# ---------------------------------------------------------------- the three wings (concourses off the atrium)
WX, WZ, WH = 20.0, 7.0, 6.0              # 40 m by 14 m, 6 m high
BAYS = (-16.0, -8.0, 0.0, 8.0, 16.0)


def wing(sid, title, cfg):
    """A 40 m by 14 m concourse, built with the atrium's doors at the west end (x -20) and turned afterwards. cfg: names (the shuttered fronts,
    north then south, five each, west to east), doors ((bay x, side, door id, target, width, kind)), end (door id, target, width, kind) at the east
    end, scaffolds, sheeted things, mannequins, the turn."""
    S = Scene(sid, title, "40 m by 14 m, 6 m high: a concourse of shuttered fronts off the atrium", mood="abandoned, mid-build")
    holes = {"N": [], "S": [], "W": [(0.0, WING_DOOR_W, WING_DOOR_H)], "E": []}
    door_bays = {(d[1], d[0]) for d in cfg["doors"]}
    for bx, side, did, to, w, kind in cfg["doors"]:
        holes[side].append((bx, w, DOOR_H if w < 1.5 else 2.4))
    eid, eto, ew, ekind = cfg["end"]
    holes["E"].append((0.0, ew, 2.6 if ew > 1.5 else DOOR_H))
    shell(S, "Wing", -WX, WX, -WZ, WZ, 0.0, WH, holes, fmat="marble")
    S.decor("Skylight", (-WX + 2.0, WH - 0.02, -2.5), (WX - 2.0, WH, 2.5), "glass", ("ceiling",))
    # the atrium's glass doors (west end)
    double_door(S, "entrance", "z", 0.0, -WX, (1, 0), width=WING_DOOR_W, height=WING_DOOR_H, props={"kind": "mall doors (glass)"})
    S.link("entrance", (-WX + 0.7, 0.0, 0.0), (-WX + 1.4, 0.0, 0.0), (1, 0), "entrance (the atrium)")
    S.marker("Spawn", (-WX + 1.4, 0.0, 0.0))
    # pilasters between the bays, on both long walls
    for x in (-12.0, -4.0, 4.0, 12.0):
        for zf, zi in ((-WZ, -WZ + 0.3), (WZ - 0.3, WZ)):
            S.solid("Pilaster", (x - 0.2, 0.0, zf), (x + 0.2, WH, zi), "column")
    # the bays: a shuttered front, or a door with the shutter rolled up over it
    for side, zc in (("N", -WZ), ("S", WZ)):
        names = cfg["names"][side]
        for k, bx in enumerate(BAYS):
            if (side, bx) in door_bays:
                continue
            shutter_front(S, f"{side}{k + 1}", side, bx, zc, names[k])
    for bx, side, did, to, w, kind in cfg["doors"]:
        zc = -WZ if side == "N" else WZ
        sg = 1 if side == "N" else -1
        dh = DOOR_H if w < 1.5 else 2.4
        # the front round the door: glazing beside it, the shutter rolled up above it, the shop's sign
        for xa, xb in ((bx - 2.4, bx - w / 2 - 0.05), (bx + w / 2 + 0.05, bx + 2.4)):
            S.solid(f"Front_{did}", (xa, 0.0, min(zc, zc + sg * 0.12)), (xb, 3.2, max(zc, zc + sg * 0.12)), "glass")
        S.solid(f"Front_{did}_Over", (bx - w / 2 - 0.05, dh, min(zc, zc + sg * 0.12)), (bx + w / 2 + 0.05, 3.2, max(zc, zc + sg * 0.12)), "shutter")
        S.decor(f"Sign_{did}", (bx - 2.2, 3.45, min(zc, zc + sg * 0.08)), (bx + 2.2, 4.05, max(zc, zc + sg * 0.08)), "sign")
        if w > 1.5:
            double_door(S, did, "x", bx, zc, (0, sg), width=w, height=dh, props={"kind": kind})
        else:
            single_door(S, did, side, bx, zc, width=w, props={"kind": kind})
        door_link(S, did, side, bx, zc, to)
        hw = max(0.9, w / 2 + 0.1)
        S.corridor(f"to_{did}", bx - hw, bx + hw, min(zc + sg * 0.15, -sg * 3.0), max(zc + sg * 0.15, -sg * 3.0))
        S.label(to.split(" ")[0], bx, zc + sg * 2.0, kind="room")
    # the east end: the wing's big door
    if ew > 1.5:
        double_door(S, eid, "z", 0.0, WX, (-1, 0), width=ew, height=2.6, props={"kind": ekind})
    else:
        single_door(S, eid, "E", 0.0, WX, width=ew, props={"kind": ekind})
    door_link(S, eid, "E", 0.0, WX, eto)
    S.label(eto.split(" ")[0], WX - 3.0, -1.5, kind="room")
    for extra in cfg.get("end_decor", []):
        extra(S)
    # scaffolding, things under dust sheets, the mannequins
    for sc in cfg["scaffolds"]:
        scaffold(S, sc[4], *sc[:4], **(sc[5] if len(sc) > 5 else {}))
    for nm, x0, x1, z0, z1, h in cfg["sheeted"]:
        sheeted(S, nm, x0, x1, z0, z1, h)
    for k, (pos, face, role, what) in enumerate(cfg["mannequins"], 1):
        S.mannequin(k, pos, face, role, what)
    S.corridor("concourse", -WX + 0.2, WX - 0.2, -3.0, 3.0)
    S.label(title.split(":")[0].upper(), 0.0, 0.0)
    for x in range(-16, 17, 8):
        S.light(x, WH - 0.4, 0.0, 400)
    S.still = ((-WX + 1.4, 0.0, 0.0), (1.0, 0.0), 4)
    turn(S, cfg["turn"])
    return S


def _books_end(S):
    """wing_books' east end: a plywood hoarding across the last bay, CLOSED FOR RENOVATION, with the site door to the construction zone."""
    S.solid("Hoarding_Face", (WX - 0.12, 0.0, -WZ), (WX, 3.0, -0.65), "hoarding")
    S.solid("Hoarding_Face", (WX - 0.12, 0.0, 0.65), (WX, 3.0, WZ), "hoarding")
    S.solid("Hoarding_Face_Over", (WX - 0.12, DOOR_H + 0.04, -0.65), (WX, 3.0, 0.65), "hoarding")


def _cinema_end(S):
    """wing_cinema's east end: the marquee over the cinema's doors."""
    S.decor("Marquee", (WX - 1.2, 3.2, -4.0), (WX, 4.2, 4.0), "sign")
    S.solid("Poster_Case", (WX - 0.15, 0.6, -5.8), (WX, 2.4, -4.6), "glass")
    S.solid("Poster_Case", (WX - 0.15, 0.6, 4.6), (WX, 2.4, 5.8), "glass")


def _ent_end(S):
    """wing_entertainment's east end: the food court's sign over its doors."""
    S.decor("FoodCourt_Sign", (WX - 0.1, 3.2, -3.5), (WX, 4.2, 3.5), "sign")


WINGS = {
    "wing_books": {
        "title": "Books wing: the concourse north of the atrium",
        "turn": 90.0,
        "names": {"N": ["CARDS & GIFTS", "BOOKSTORE", "CALENDARS", "STATIONERY", "COMICS"],
                  "S": ["PRINT SHOP", "MAPS", "(a painted-sky door)", "LIBRARY CAFE", "STAFF ONLY"]},
        "doors": [(-8.0, "N", "bookstore", "bookstore", 1.8, "shop doors"),
                  (0.0, "S", "scene_2909", "scene_2909 (the sky court)", DOOR_W, "unmarked door between the shutters"),
                  (16.0, "S", "service_corridor", "service_corridor (staff only)", DOOR_W, "staff door")],
        "end": ("construction", "construction (the site door in the hoarding)", 1.2, "site door"),
        "end_decor": [_books_end],
        "scaffolds": [(5.0, 11.0, -WZ + 0.35, -5.5, "books_N", {"sheet": True}), (13.0, 19.0, -WZ + 0.35, -5.5, "books_NE"),
                      (-19.0, -13.0, 5.5, WZ - 0.35, "books_SW")],
        "sheeted": [("Bench", -13.0, -11.0, 3.6, 4.3, 0.55), ("Bench", 3.0, 5.0, 3.6, 4.3, 0.55), ("BookCart", -5.0, -3.0, -4.6, -3.6, 1.3),
                    ("Planter", 11.2, 12.8, 3.4, 5.0, 1.0)],
        "mannequins": [((-12.0, 0.0, -4.4), (0, 1), "dressing", "in a sheet, by the stationery shutter"),
                       ((-6.4, 0.0, -5.6), (0, 1), "npc", "in the bookstore's doorway, holding a book"),
                       ((8.0, 0.0, 4.6), (0, -1), "monster", "facing the concourse, under the library cafe sign")],
    },
    "wing_cinema": {
        "title": "Cinema wing: the concourse west of the atrium",
        "turn": 180.0,
        "names": {"N": ["ARCADE TOKENS", "RESTROOMS", "VIDEO RENTAL", "POSTERS", "STAFF ONLY"],
                  "S": ["CANDY", "COSTUMES", "(a painted-sky door)", "RECORDS", "PHOTO BOOTH"]},
        "doors": [(-8.0, "N", "mirror_bathroom", "mirror_bathroom (the restrooms)", DOOR_W, "restroom door"),
                  (0.0, "S", "scene_3012", "scene_3012 (the painted-sky street)", DOOR_W, "unmarked door between the shutters"),
                  (16.0, "N", "service_corridor", "service_corridor (staff only)", DOOR_W, "staff door")],
        "end": ("cinema_lobby", "cinema_lobby", 2.4, "cinema doors (glass)"),
        "end_decor": [_cinema_end],
        "scaffolds": [(-19.0, -13.0, -WZ + 0.35, -5.5, "cin_NW", {"sheet": True}), (4.0, 8.0, -WZ + 0.35, WZ - 0.35, "cin_bridge",
                                                                                    {"decks": (4.0,), "bay": 4.0}),
                      (9.5, 14.5, 5.5, WZ - 0.35, "cin_S")],
        "sheeted": [("TicketKiosk", -13.0, -11.0, 3.4, 4.8, 1.6), ("PopcornCart", 11.2, 12.6, -4.6, -3.6, 1.2), ("Bench", -5.0, -3.0, 3.6, 4.3, 0.55)],
        "mannequins": [((-4.0, 0.0, -4.4), (0, 1), "dressing", "a cinema usher, by the restroom door"),
                       ((6.0, 0.0, 4.4), (0, -1), "monster", "under the scaffold bridge, facing the concourse"),
                       ((17.2, 0.0, 3.2), (-1, 0), "dressing", "in front of a poster case, by the cinema's doors")],
    },
    "wing_entertainment": {
        "title": "Entertainment wing: the concourse east of the atrium",
        "turn": 0.0,
        "names": {"N": ["BOWLING", "LASER TAG", "(a painted-sky door)", "PRIZE COUNTER", "KARAOKE"],
                  "S": ["CLAW MACHINES", "(a painted-sky door)", "MINI GOLF", "VR ZONE", "STAFF ONLY"]},
        "doors": [(0.0, "N", "scene_2991", "scene_2991 (the soft play and the carousel)", DOOR_W, "unmarked door between the shutters"),
                  (-8.0, "S", "scene_3008", "scene_3008 (the escalator well)", DOOR_W, "unmarked door between the shutters"),
                  (16.0, "S", "service_corridor", "service_corridor (staff only)", DOOR_W, "staff door")],
        "end": ("food_court", "food_court", 2.4, "food court doors (glass)"),
        "end_decor": [_ent_end],
        "scaffolds": [(-19.0, -13.0, -WZ + 0.35, -5.5, "ent_NW"), (5.0, 11.0, 5.5, WZ - 0.35, "ent_S", {"sheet": True})],
        "sheeted": [("KiddieRide_Car", -13.6, -12.4, 3.4, 4.6, 1.2), ("KiddieRide_Horse", -5.0, -3.6, 3.5, 4.5, 1.4),
                    ("ClawMachine", 3.2, 4.8, -4.6, -3.6, 1.9), ("ClawMachine", 11.2, 12.8, -4.6, -3.6, 1.9)],
        "mannequins": [((-16.0, 0.0, -4.6), (0, 1), "dressing", "a bowler mid-swing, in front of the bowling shutter"),
                       ((-12.0, 0.0, 4.9), (0, -1), "npc", "beside the kiddie ride, a coin in its hand"),
                       ((14.0, 0.0, -4.4), (-1, 0), "monster", "between the claw machines, facing the atrium")],
    },
}


# ---------------------------------------------------------------- the shops you can enter
def bookstore():
    S = Scene("bookstore", "Bookstore", "20 m by 16 m, 3.6 m high: freestanding bookcases, wall shelves, two window displays", mood="abandoned shop")
    x0, x1, z0, z1, h = -10.0, 10.0, -8.0, 8.0, 3.6
    shell(S, "Shop", x0, x1, z0, z1, 0.0, h, holes={"S": [(0.0, 1.8, 2.4)], "E": [(5.0, DOOR_W, DOOR_H)]}, fmat="carpet_blue")
    double_door(S, "wing_books", "x", 0.0, z1, (0, -1), width=1.8, height=2.4, props={"kind": "shop doors"})
    door_link(S, "wing_books", "S", 0.0, z1, "wing_books (the concourse)")
    S.marker("Spawn", (0.0, 0.0, z1 - 1.3))
    single_door(S, "bookstore_desk", "E", 5.0, x1, props={"kind": "door marked INFORMATION"})
    door_link(S, "bookstore_desk", "E", 5.0, x1, "bookstore_desk (the front desk)")
    # wall shelves, the freestanding runs, the display tables
    S.solid("Shelf_N", (x0, 0.0, z0), (x1, 2.4, z0 + 0.4), "bookcase")
    S.solid("Shelf_W", (x0, 0.0, z0 + 0.4), (x0 + 0.4, 2.4, 6.0), "bookcase")
    S.solid("Shelf_E", (x1 - 0.4, 0.0, z0 + 0.4), (x1, 2.4, 4.2), "bookcase")
    for x in (-7.2, -4.2, 4.2, 7.2):
        S.solid("Bookcase_Run", (x - 0.4, 0.0, -5.8), (x + 0.4, 1.8, 1.6), "bookcase")
        S.decor("Run_Sign", (x - 0.35, 1.8, -0.2), (x + 0.35, 2.2, -0.15), "sign")
    for xa, xb in ((-3.2, -2.0), (2.0, 3.2)):
        for za, zb in ((-4.0, -2.6), (-0.6, 0.8)):
            sheeted(S, "Display_Table", xa, xb, za, zb, 0.8)
    # the two window displays either side of the doors, on low plinths
    S.solid("Window_Plinth", (x0 + 0.4, 0.0, 7.0), (-1.6, 0.4, z1), "furniture")
    S.solid("Window_Plinth", (1.6, 0.0, 7.0), (x1 - 0.4, 0.4, z1), "furniture")
    S.decor("Window_Glass", (x0 + 0.4, 0.4, z1 - 0.04), (-1.0, 2.6, z1), "glass")
    S.decor("Window_Glass", (1.0, 0.4, z1 - 0.04), (x1 - 0.4, 2.6, z1), "glass")
    S.mannequin(1, (-5.5, 0.4, 7.4), (0, 1), "dressing", "in the window display, reading, its back to the shop")
    S.mannequin(2, (5.5, 0.4, 7.4), (0, 1), "dressing", "in the window display, an armful of books")
    S.mannequin(3, (-5.7, 0.0, -2.0), (1, 0), "monster", "browsing between the bookcase runs")
    S.mannequin(4, (8.4, 0.0, -6.8), (-1, 0), "npc", "in the back corner, on its knees by the bottom shelf")
    S.corridor("main_aisle", -1.6, 1.6, -7.55, 6.9)
    S.corridor("back_aisle", x0 + 0.45, x1 - 0.45, -7.55, -5.85)
    S.corridor("front_aisle", x0 + 0.45, x1 - 0.45, 1.8, 6.9)
    for xa, xb in ((x0 + 0.45, -7.65), (-6.75, -4.65), (4.65, 6.75), (7.65, x1 - 0.45)):
        S.corridor("run_aisle", xa, xb, -5.8, 1.6)
    S.label("BOOKSTORE", 0.0, 3.6)
    S.label("window display", -5.5, 6.5, kind="note")
    S.label("window display", 5.5, 6.5, kind="note")
    S.label("wall shelves", 0.0, -7.2, kind="note")
    for x in (-6, 0, 6):
        for z in (-4, 3):
            S.light(x, h - 0.3, z, 160)
    S.still = ((0.0, 0.0, z1 - 1.3), (0.0, -1.0), -2)
    return S


def bookstore_desk():
    S = Scene("bookstore_desk", "The bookstore's front desk", "12 m by 8 m, 3.2 m high: the cash desk, the back counter, the office", mood="abandoned shop")
    x0, x1, z0, z1, h = -6.0, 6.0, -4.0, 4.0, 3.2
    shell(S, "Desk", x0, x1, z0, z1, 0.0, h, holes={"W": [(2.0, DOOR_W, DOOR_H)]}, fmat="carpet_blue")
    single_door(S, "bookstore", "W", 2.0, x0, props={"kind": "door marked INFORMATION"})
    door_link(S, "bookstore", "W", 2.0, x0, "bookstore (the shop floor)")
    S.marker("Spawn", (x0 + 1.3, 0.0, 2.0))
    box(S, "Cash_Desk", -3.0, 3.0, -1.2, -0.6, 0.0, 1.05, "counter")
    box(S, "Cash_Desk_Return", 2.4, 3.0, -0.6, 1.6, 0.0, 1.05, "counter")
    S.decor("Till", (-0.4, 1.05, -1.1), (0.4, 1.3, -0.7), "rail")
    box(S, "Back_Counter", -5.6, 2.6, z0, -3.4, 0.0, 0.9, "counter")
    S.decor("Special_Orders", (-5.6, 1.4, z0), (2.6, 2.6, -3.8), "bookcase")
    # the back office in the north-east corner
    S.solid("Office_Wall_W", (3.0, 0.0, z0), (3.2, h, -1.6), "wall")
    wall(S, "Office_Wall_S", "x", -1.8, -1.6, 3.2, x1, 0.0, h, [(4.13, 5.07, 0.0, DOOR_H)])
    S.door("office", (4.13, 0.0, -1.6), (1, 0), (0, -1), props={"kind": "office"})
    box(S, "Office_Desk", 4.4, 5.8, -3.8, -3.0, 0.0, 0.75, "furniture")
    box(S, "Filing_Cabinet", 3.3, 3.8, -3.9, -3.3, 0.0, 1.3, "column")
    S.label("office", 4.6, -2.4, kind="note")
    for k, x in enumerate((-4.5, -3.3, -2.1), 1):
        S.decor("Queue_Post", (x - 0.05, 0.0, 1.6), (x + 0.05, 0.95, 1.7), "rail")
    S.decor("Queue_Rope", (-4.5, 0.85, 1.62), (-2.1, 0.9, 1.68), "carpet_red")
    sheeted(S, "Returns_Trolley", 4.4, 5.2, 0.2, 1.2, 1.1)
    S.mannequin(1, (0.0, 0.0, -2.3), (0, 1), "npc", "the clerk, behind the till")
    S.mannequin(2, (5.1, 0.0, -2.4), (-1, 0), "dressing", "in the office, its back to the door")
    S.spot("puzzle", 1, (0.0, 0.0, -0.1), face=(0, -1), props={"what": "the till drawer"})
    S.corridor("customers", x0 + 0.45, x1 - 0.2, 1.75, 3.95)
    S.corridor("staff_aisle", -5.5, 2.8, -3.35, -1.25)
    S.label("FRONT DESK", 0.0, 0.4)
    S.label("back counter", -1.5, -3.1, kind="note")
    for x in (-3, 3):
        S.light(x, h - 0.3, 0.0, 150)
    S.still = ((x0 + 1.3, 0.0, 2.0), (1.0, -0.45), -4)
    return S


def cinema_lobby():
    S = Scene("cinema_lobby", "Cinema lobby", "24 m by 16 m, 6 m high: box office, concessions, a balcony at y 3 to screens 3 to 5", levels=(0.0, 3.0),
              mood="abandoned, lit by the marquee")
    S.level_names = {0.0: "lobby floor (y 0)", 3.0: "balcony (y 3)"}
    x0, x1, z0, z1, h = -12.0, 12.0, -8.0, 8.0, 6.0
    shell(S, "Lobby", x0, x1, z0, z1, 0.0, h, holes={"S": [(0.0, 2.4, 2.6)]}, fmat="carpet_red")
    double_door(S, "wing_cinema", "x", 0.0, z1, (0, -1), width=2.4, height=2.6, props={"kind": "cinema doors (glass)"})
    door_link(S, "wing_cinema", "S", 0.0, z1, "wing_cinema (the concourse)")
    S.marker("Spawn", (0.0, 0.0, z1 - 1.3))
    # the balcony along the north wall, its rail, the stair up the east side
    S.solid("Balcony_Slab", (x0, 2.7, z0), (x1, 3.0, -5.0), "floor")
    S.solid("Balcony_Rail", (x0, 3.0, -5.1), (9.5, 4.0, -5.0), "rail")
    S.solid("Balcony_Rail", (11.9, 3.0, -5.1), (x1, 4.0, -5.0), "rail")
    flight(S, "balcony", 9.6, 11.8, -1.4, -1, "z", 0.0, 3.0, 12, 0.3)
    S.solid("Stair_Wall", (9.4, 0.0, -5.0), (9.5, 1.0, -1.4), "rail")
    for k, x in enumerate((-8.0, -2.0, 4.0), 3):
        S.solid(f"Screen_{k}_Door", (x - 0.8, 3.0, z0), (x + 0.8, 5.4, z0 + 0.06), "fake_door")
        S.label(f"SCREEN {k}", x, -7.2, 3.0, kind="note")
    # the concessions under the balcony, the box office, the ground-floor screens
    box(S, "Concession_Counter", -7.0, 7.0, -6.8, -6.0, 0.0, 1.1, "counter")
    box(S, "Back_Counter", -7.0, 7.0, z0, -7.6, 0.0, 0.9, "counter")
    S.decor("Menu_Board", (-6.0, 1.8, z0), (6.0, 2.6, -7.94), "sign")
    box(S, "Box_Office", -10.0, -6.5, 3.5, 6.5, 0.0, 2.6, "counter")
    S.decor("Box_Office_Glass", (-6.52, 1.0, 3.6), (-6.48, 2.4, 6.4), "glass")
    for z in (4.0, 5.0, 6.0):
        S.decor("Queue_Post", (-5.2, 0.0, z - 0.05), (-5.1, 0.95, z + 0.05), "rail")
    S.solid("Screen_1_Door", (x0, 0.0, -2.0), (x0 + 0.06, 2.4, 0.0), "fake_door")
    S.solid("Screen_2_Door", (x1 - 0.06, 0.0, 2.0), (x1, 2.4, 4.0), "fake_door")
    S.label("SCREEN 1", x0 + 1.4, -1.0, kind="note")
    S.label("SCREEN 2", x1 - 1.4, 3.0, kind="note")
    for z in (-1.0, 4.0):
        S.decor("Poster", (x0, 1.0, z + 1.5), (x0 + 0.04, 2.4, z + 2.5), "sign")
    sheeted(S, "Cardboard_Standee", -11.5, -10.5, -4.0, -3.4, 1.9)
    S.mannequin(1, (-4.6, 0.0, 4.0), (-1, 0), "dressing", "first in the queue at the box office")
    S.mannequin(2, (-4.6, 0.0, 5.0), (-1, 0), "dressing", "second in the queue")
    S.mannequin(3, (-4.6, 0.0, 6.0), (-1, 0), "monster", "last in the queue; it is not always there")
    S.mannequin(4, (0.0, 0.0, -7.2), (0, 1), "npc", "behind the concession counter")
    S.mannequin(5, (-6.0, 3.0, -5.6), (0, 1), "monster", "at the balcony rail, looking down at the doors")
    S.corridor("lobby", -5.5, 9.2, -5.6, 7.6)
    S.corridor("balcony", x0 + 0.1, 9.2, z0 + 0.1, -5.15, 3.0)
    S.label("CINEMA LOBBY", 2.0, 1.0)
    S.label("box office", -8.25, 5.0, kind="note")
    S.label("concessions (under the balcony)", 0.0, -5.4, kind="note")
    S.label("BALCONY", -2.0, -6.4, 3.0)
    S.label("stairs up", 10.7, -0.8, kind="note")
    for x in (-8, 0, 8):
        S.light(x, h - 0.4, 2.0, 400)
        S.light(x, 2.5, -6.0, 90)
        S.light(x, 5.4, -6.5, 120)
    S.still = ((0.0, 0.0, z1 - 1.3), (-0.15, -1.0), 8)
    return S


def food_court():
    S = Scene("food_court", "Food court", "30 m by 24 m, 6 m high: ten shuttered stalls, twenty tables", mood="abandoned")
    x0, x1, z0, z1, h = -15.0, 15.0, -12.0, 12.0, 6.0
    shell(S, "Court", x0, x1, z0, z1, 0.0, h, holes={"S": [(0.0, 2.4, 2.6)], "W": [(0.0, 2.4, 2.6)], "N": [(12.5, DOOR_W, DOOR_H)]}, fmat="tile")
    double_door(S, "wing_entertainment", "x", 0.0, z1, (0, -1), width=2.4, height=2.6, props={"kind": "food court doors (glass)"})
    door_link(S, "wing_entertainment", "S", 0.0, z1, "wing_entertainment (the concourse)")
    double_door(S, "entrance", "z", 0.0, x0, (1, 0), width=2.4, height=2.6, props={"kind": "the FOOD COURT shopfront's doors"})
    door_link(S, "entrance", "W", 0.0, x0, "entrance (the atrium's FOOD COURT shopfront)")
    single_door(S, "service_corridor", "N", 12.5, z0, props={"kind": "kitchen door, staff only"})
    door_link(S, "service_corridor", "N", 12.5, z0, "service_corridor (the kitchens' door)")
    S.marker("Spawn", (0.0, 0.0, z1 - 1.3))
    names_n = ["NOODLES", "PIZZA", "BURGERS", "TACOS", "PRETZELS", "SMOOTHIES"]
    names_e = ["CHICKEN", "SUSHI", "GYROS", "ICE CREAM"]
    for k, xa in enumerate(range(-14, 10, 4)):
        xb = xa + 4
        S.solid("Stall_Partition", (xa - 0.1, 0.0, z0), (xa + 0.1, 3.2, -9.5), "wall")
        box(S, "Stall_Counter", xa + 0.1, xb - 0.1, -9.9, -9.5, 0.0, 1.1, "counter")
        S.solid("Stall_Shutter", (xa + 0.1, 1.1, -9.6), (xb - 0.1, 3.2, -9.5), "shutter")
        S.decor("Stall_Sign", (xa + 0.3, 3.3, -9.6), (xb - 0.3, 3.9, -9.5), "sign")
        S.label(names_n[k], xa + 2.0, -10.8, kind="note")
    S.solid("Stall_Partition", (9.9, 0.0, z0), (10.1, 3.2, -9.5), "wall")
    for k, za in enumerate(range(-8, 8, 4)):
        zb = za + 4
        S.solid("Stall_Partition", (12.5, 0.0, za - 0.1), (x1, 3.2, za + 0.1), "wall")
        box(S, "Stall_Counter", 12.1, 12.5, za + 0.1, zb - 0.1, 0.0, 1.1, "counter")
        S.solid("Stall_Shutter", (12.1, 1.1, za + 0.1), (12.2, 3.2, zb - 0.1), "shutter")
        S.decor("Stall_Sign", (12.1, 3.3, za + 0.3), (12.2, 3.9, zb - 0.3), "sign")
        S.label(names_e[k], 13.6, za + 2.0, kind="note")
    S.solid("Stall_Partition", (12.5, 0.0, 7.9), (x1, 3.2, 8.1), "wall")
    S.decor("Fascia", (x0, 3.95, -9.6), (12.2, 4.6, -9.5), "sign")
    # twenty tables, two benches each, in four blocks either side of the cross aisles
    k = 0
    for x in (-11.0, -7.5, -4.0, 4.0, 7.5):
        for z in (-6.5, -3.5, 3.5, 6.5):
            k += 1
            box(S, "Table", x - 0.5, x + 0.5, z - 0.5, z + 0.5, 0.0, 0.75, "furniture")
            box(S, "Bench", x - 0.6, x + 0.6, z - 0.95, z - 0.6, 0.0, 0.45, "counter")
            box(S, "Bench", x - 0.6, x + 0.6, z + 0.6, z + 0.95, 0.0, 0.45, "counter")
            if k % 3 == 0:
                S.decor("Chairs_Stacked", (x - 0.3, 0.75, z - 0.3), (x + 0.3, 1.5, z + 0.3), "sheet")
    box(S, "Tray_Return", 9.5, 11.5, 10.6, 11.6, 0.0, 1.4, "counter")
    sheeted(S, "Kiddie_Train", -13.8, -11.8, 9.4, 11.2, 1.3)
    S.mannequin(1, (-7.5, 0.45, -4.27), (0, 1), "dressing", "seated, a tray in front of it")
    S.mannequin(2, (4.0, 0.45, 2.73), (0, 1), "dressing", "seated, facing the doors")
    S.mannequin(3, (7.5, 0.45, 7.27), (0, -1), "monster", "seated with its back to you")
    S.mannequin(4, (-4.0, 0.0, -8.6), (0, -1), "npc", "queuing at the burger stall")
    S.mannequin(5, (11.2, 0.0, -2.0), (1, 0), "dressing", "at the chicken counter")
    S.corridor("north_south", -1.2, 1.2, -9.3, z1 - 0.2)
    S.corridor("east_west", x0 + 0.2, 12.0, -1.2, 1.2)
    S.corridor("stall_fronts", x0 + 0.2, 12.0, -9.3, -7.55)
    S.corridor("kitchen_door", 10.2, x1 - 0.2, z0 + 0.2, -8.2)
    S.label("FOOD COURT", 0.0, 2.0)
    S.label("stalls (shutters down)", -2.0, -11.0)
    for x in (-10, 0, 10):
        for z in (-6, 6):
            S.light(x, h - 0.4, z, 400)
    S.still = ((0.0, 0.0, z1 - 1.3), (0.25, -1.0), 3)
    return S


def construction():
    S = Scene("construction", "Construction zone", "24 m by 18 m, 6.5 m high: a bare shell mid-build, a scaffold deck at y 3, a lift pit",
              levels=(0.0, 3.0), mood="mid-build, nobody here")
    S.level_names = {0.0: "site floor (y 0)", 3.0: "scaffold deck (y 3)"}
    x0, x1, z0, z1, h = -12.0, 12.0, -9.0, 9.0, 6.5
    shell(S, "Site", x0, x1, z0, z1, 0.0, h, holes={"S": [(-3.0, 1.2, DOOR_H)], "N": [(-5.0, KIT_W, DOOR_H, 3.0)]}, floor=False,
          wmat="concrete", fmat="concrete")
    S.solid("Hoarding_Inner", (x0, 0.0, z1 - 0.1), (-3.65, 3.0, z1), "hoarding")
    S.solid("Hoarding_Inner", (-2.35, 0.0, z1 - 0.1), (x1, 3.0, z1), "hoarding")
    # the floor, with the lift pit cut into it
    px0, px1, pz0, pz1, pd = 7.5, 10.5, 2.0, 5.0, 1.2
    base = -pd - SLAB
    S.solid("Site_Floor_N", (x0 - T, base, z0 - T), (x1 + T, 0.0, pz0), "concrete")
    S.solid("Site_Floor_S", (x0 - T, base, pz1), (x1 + T, 0.0, z1 + T), "concrete")
    S.solid("Site_Floor_W", (x0 - T, base, pz0), (px0, 0.0, pz1), "concrete")
    S.solid("Site_Floor_E", (px1, base, pz0), (x1 + T, 0.0, pz1), "concrete")
    S.solid("Pit_Floor", (px0, base, pz0), (px1, -pd, pz1), "concrete")
    for nm, mn, mx in (("N", (px0 - 0.3, 0.0, pz0 - 0.35), (px1 + 0.3, 1.0, pz0 - 0.3)), ("S", (px0 - 0.3, 0.0, pz1 + 0.3), (px1 + 0.3, 1.0, pz1 + 0.35)),
                       ("W", (px0 - 0.35, 0.0, pz0 - 0.3), (px0 - 0.3, 1.0, pz1 + 0.3)), ("E", (px1 + 0.3, 0.0, pz0 - 0.3), (px1 + 0.35, 1.0, pz1 + 0.3))):
        S.solid(f"Pit_Barrier_{nm}", mn, mx, "hazard")
    S.zone("hazard", "lift_pit", (px0, -pd, pz0), (px1, 0.0, pz1))
    S.label("lift pit (1.2 m)", (px0 + px1) / 2, pz1 + 0.9, kind="note")
    # the column grid and the beams overhead
    for x in (-6.0, 0.0, 6.0):
        for z in (-3.0, 3.0):
            S.solid("Column", (x - 0.25, 0.0, z - 0.25), (x + 0.25, h, z + 0.25), "column")
    for x in (-6.0, 0.0, 6.0):
        S.decor("Beam", (x - 0.15, h - 0.5, z0), (x + 0.15, h, z1), "column", ("ceiling",))
    # the site door from the wing (south) and the scaffold deck along the north wall, with its stair and the door to the sky hall
    single_door(S, "wing_books", "S", -3.0, z1, width=1.2, props={"kind": "site door in the hoarding"})
    door_link(S, "wing_books", "S", -3.0, z1, "wing_books (the hoarding at the wing's end)")
    S.marker("Spawn", (-3.0, 0.0, z1 - 1.3))
    S.solid("Deck", (-11.0, 2.9, z0), (-1.0, 3.0, -5.2), "plank")
    S.solid("Deck_Rail", (-9.8, 3.0, -5.3), (-1.0, 4.0, -5.2), "scaffold")
    S.solid("Deck_Rail", (-1.1, 3.0, z0), (-1.0, 4.0, -5.3), "scaffold")
    S.solid("Deck_Rail", (-11.0, 3.0, z0), (-10.9, 4.0, -5.2), "scaffold")      # the west end, over the 1 m gap to the wall
    for x in (-9.75, -5.5, -1.05):
        S.solid("Deck_Post", (x - 0.05, 0.0, -5.3), (x + 0.05, 2.9, -5.2), "scaffold")
    flight(S, "deck", -11.0, -9.8, -1.6, -1, "z", 0.0, 3.0, 12, 0.3)
    S.solid("Stair_Rail", (-9.8, 0.0, -5.2), (-9.75, 1.0, -1.6), "scaffold")
    kit_door(S, "sky_hall_04", "N", -5.0, z0, y=3.0)
    door_link(S, "sky_hall_04", "N", -5.0, z0, "sky_hall_04 (an unfinished doorway onto a painted sky)", y=3.0)
    S.label("scaffold deck (y 3)", -6.0, -7.0, 3.0)
    S.label("site stair", -10.4, -0.9, kind="note")
    # half-built stud walls, materials, plant
    for k in range(6):
        x = -11.0 + k * 1.2
        S.solid("Stud", (x, 0.0, 5.0), (x + 0.05, 3.0, 5.1), "plank")
    S.solid("Stud_Plate", (-11.0, 0.0, 5.0), (-4.95, 0.05, 5.1), "plank")
    S.solid("Stud_Plate", (-11.0, 2.95, 5.0), (-4.95, 3.0, 5.1), "plank")
    S.solid("Plasterboard", (-11.0, 0.05, 5.1), (-8.6, 2.95, 5.12), "sheet")
    box(S, "Plasterboard_Pallet", 1.0, 3.0, 6.4, 8.0, 0.0, 1.0, "sheet")
    box(S, "Cement_Mixer", 4.0, 5.0, 6.6, 7.8, 0.0, 1.4, "hazard")
    box(S, "Scissor_Lift", 2.0, 4.4, -2.0, -0.8, 0.0, 2.0, "hazard")
    box(S, "Pallet", -8.0, -6.8, -8.6, -7.4, 0.0, 0.9, "plank")
    box(S, "Pallet", 9.0, 11.4, -8.6, -6.8, 0.0, 1.2, "plank")
    S.decor("Cable_Reel", (6.6, 0.0, -6.0), (7.4, 0.8, -5.2), "plank")
    S.mannequin(1, (-3.0, 3.0, -6.4), (0, 1), "monster", "on the deck in a hi-vis vest, facing the stair")
    S.mannequin(2, (-7.0, 0.0, 5.6), (0, 1), "dressing", "propped against the stud wall")
    S.mannequin(3, (-5.5, 0.0, 5.6), (0, 1), "dressing", "propped against the stud wall, no arms")
    S.corridor("from_the_door", -4.0, -2.0, -1.4, z1 - 0.2)
    S.corridor("to_the_stair", -10.8, -2.0, -1.4, 0.4)
    S.corridor("deck", -9.6, -1.4, z0 + 0.1, -5.4, 3.0)
    S.label("CONSTRUCTION", 2.0, 0.5)
    S.label("stud wall", -7.4, 4.4, kind="note")
    for x in (-6, 6):
        for z in (-4, 4):
            S.light(x, h - 0.7, z, 350)
    S.light(-5.0, 5.6, -7.0, 120)
    S.still = ((-3.0, 0.0, z1 - 1.3), (-0.45, -1.0), 10)
    return S


def service_corridor():
    S = Scene("service_corridor", "Service corridor", "a back corridor 46 m by 2 m, 3 m high, and an 10 m spur to the freight lift",
              mood="back of house, the hidden network")
    x0, x1, z0, z1, h = -26.0, 20.0, -1.0, 1.0, 3.0
    doors = [(-22.0, "wing_cinema", "wing_cinema (its staff door)"), (-8.0, "wing_books", "wing_books (its staff door)"),
             (4.0, "wing_entertainment", "wing_entertainment (its staff door)"), (12.0, "food_court", "food_court (the kitchens' door)")]
    shell(S, "Corridor", x0, x1, z0, z1, 0.0, h, holes={"S": [(a, DOOR_W, DOOR_H) for a, _, _ in doors], "N": [(19.0, 2.0, h), (-15.0, 4.0, h)]},
          fmat="concrete", wmat="concrete")
    for a, did, to in doors:
        single_door(S, did, "S", a, z1, props={"kind": "staff door"})
        door_link(S, did, "S", a, z1, to, near=0.5, far=1.2)
    S.marker("Spawn", (-8.0, 0.0, z1 - 1.2))
    # the bin bay off the north side, out of the way
    shell(S, "BinBay", -17.0, -13.0, -2.4, -1.2, 0.0, h, sides="NWE", fmat="concrete", wmat="concrete")
    box(S, "Bin", -16.8, -15.4, -2.4, -1.5, 0.0, 1.3, "plant")
    box(S, "Bin", -15.2, -13.8, -2.4, -1.5, 0.0, 1.3, "plant")
    S.label("bins", -15.0, -3.2, kind="note")
    # the spur to the freight lift (the hidden network: the kit's service corridor and freight lift later)
    shell(S, "Spur", 18.0, 20.0, -12.0, -1.0, 0.0, h, holes={"N": [(19.0, 1.2, 2.2)]}, sides="NWE", fmat="concrete", wmat="concrete")
    shell(S, "FreightCar", 17.9, 20.1, -14.6, -12.2, 0.0, 2.4, sides="NWE", fmat="lift", wmat="lift")
    S.door("network_A", (18.4, 0.0, -12.0), (1, 0), (0, 1), width=0.6, height=2.2, props={"kind": "freight lift gate", "needs": "keycard_tier_1"})
    S.door("network_B", (19.6, 0.0, -12.0), (-1, 0), (0, 1), width=0.6, height=2.2, props={"kind": "freight lift gate", "needs": "keycard_tier_1"})
    S.link("network", (19.0, 0.0, -11.4), (19.0, 0.0, -10.7), (0, 1), "the hidden network (the freight lift, keycard_tier_1)")
    S.spot("keycard", 1, (18.4, 0.0, -11.0), face=(0, -1), props={"what": "the freight lift's keycard reader", "needs": "keycard_tier_1"})
    S.label("freight lift (placeholder car)", 19.0, -13.4, kind="note")
    # the far end, the pipes overhead
    S.solid("Fire_Door", (x0, 0.0, -0.6), (x0 + 0.06, 2.1, 0.6), "fake_door")
    S.label("fire door (shut)", x0 + 1.6, -0.2, kind="note")
    S.decor("Pipe", (x0, 2.6, -0.9), (x1, 2.75, -0.75), "column", ("ceiling",))
    S.decor("Pipe", (x0, 2.45, -0.6), (x1, 2.55, -0.5), "plant", ("ceiling",))
    S.decor("Cable_Tray", (18.1, 2.6, -12.0), (18.3, 2.7, -1.0), "rail", ("ceiling",))
    S.mannequin(1, (-14.2, 0.0, -1.0), (0, 1), "dressing", "dumped by the bins, one arm off")
    S.mannequin(2, (-24.8, 0.0, 0.0), (1, 0), "monster", "at the far end by the fire door, facing down the corridor")
    S.corridor("corridor", x0 + 0.1, x1 - 0.05, z0 + 0.05, z1 - 0.05)
    S.corridor("spur", 18.05, 19.95, -11.95, z0 + 0.05)
    S.label("SERVICE CORRIDOR", -2.0, -2.2)
    S.label("spur", 17.0, -6.0, kind="note")
    for x in range(-24, 20, 6):
        S.light(x, h - 0.3, 0.0, 60)
    S.light(19.0, 2.6, -6.0, 60)
    S.still = ((-8.0, 0.0, -0.2), (1.0, 0.0), 0)
    return S


# ---------------------------------------------------------------- the photo scenes (the photos are labels only; each is a painted-sky space)
def scene_2909():
    S = Scene("scene_2909", "The sky court (IMG_2909, a label only)", "24 m by 24 m, 8 m high under a painted sky, a court sunk 1 m in the middle",
              mood="liminal, painted sky")
    x0, x1, z0, z1, h = -12.0, 12.0, -12.0, 12.0, 8.0
    shell(S, "Court", x0, x1, z0, z1, 0.0, h, holes={"S": [(0.0, DOOR_W, DOOR_H)], "N": [(0.0, KIT_W, DOOR_H)]}, floor=False,
          wmat="mural", cmat="sky")
    single_door(S, "wing_books", "S", 0.0, z1, props={"kind": "unmarked door"})
    door_link(S, "wing_books", "S", 0.0, z1, "wing_books (the concourse)")
    kit_door(S, "sky_hall_01", "N", 0.0, z0)
    door_link(S, "sky_hall_01", "N", 0.0, z0, "sky_hall_01 (a painted-sky hall)")
    S.marker("Spawn", (0.0, 0.0, z1 - 1.3))
    # the floor round the sunken court, the three steps down (one ring of boxes a step), the court's floor
    r, base = 6.0, -1.0 - SLAB
    S.solid("Floor_N", (x0 - T, base, z0 - T), (x1 + T, 0.0, -r), "marble")
    S.solid("Floor_S", (x0 - T, base, r), (x1 + T, 0.0, z1 + T), "marble")
    S.solid("Floor_W", (x0 - T, base, -r), (-r, 0.0, r), "marble")
    S.solid("Floor_E", (r, base, -r), (x1 + T, 0.0, r), "marble")
    for i in range(3):
        ro, ri, top = r - 0.4 * i, r - 0.4 * (i + 1), -0.25 * (i + 1)
        S.solid(f"Step_court_N_{i:02d}", (-ro, base, -ro), (ro, top, -ri), "stair")
        S.solid(f"Step_court_S_{i:02d}", (-ro, base, ri), (ro, top, ro), "stair")
        S.solid(f"Step_court_W_{i:02d}", (-ro, base, -ri), (-ri, top, ri), "stair")
        S.solid(f"Step_court_E_{i:02d}", (ri, base, -ri), (ro, top, ri), "stair")
    for sd in "NSWE":
        S.flights.append({"name": f"court_{sd}", "y_start": -1.0, "y_end": 0.0, "n": 4, "rise": 0.25, "tread": 0.4, "down": True})
    ri = r - 1.2
    S.solid("Court_Floor", (-ri, base, -ri), (ri, -1.0, ri), "marble")
    # the bandstand in the court, the planters with their plastic trees, the benches round the edge
    S.solid("Bandstand", (-2.0, -1.0, -2.0), (2.0, -0.75, 2.0), "furniture")
    for sx in (-1.85, 1.85):
        for sz in (-1.85, 1.85):
            S.solid("Bandstand_Post", (sx - 0.08, -0.75, sz - 0.08), (sx + 0.08, 1.8, sz + 0.08), "column")
    S.decor("Bandstand_Roof", (-2.3, 1.8, -2.3), (2.3, 2.1, 2.3), "facade_a")
    for sx in (-9.0, 9.0):
        for sz in (-9.0, 9.0):
            box(S, "Planter", sx - 0.8, sx + 0.8, sz - 0.8, sz + 0.8, 0.0, 0.7, "concrete")
            S.decor("Tree_Trunk", (sx - 0.12, 0.7, sz - 0.12), (sx + 0.12, 2.8, sz + 0.12), "furniture")
            S.decor("Tree_Canopy", (sx - 1.3, 2.6, sz - 1.3), (sx + 1.3, 4.4, sz + 1.3), "plant")
    for x in (-4.0, 4.0):
        for z in (-7.2, 7.2):
            box(S, "Bench", x - 1.2, x + 1.2, z - 0.25, z + 0.25, 0.0, 0.45, "counter")
    for x in (-7.2, 7.2):
        box(S, "Bench", x - 0.25, x + 0.25, -1.2, 1.2, 0.0, 0.45, "counter")
    S.mannequin(1, (-4.0, 0.45, 7.2), (0, -1), "dressing", "seated on a bench, looking at the bandstand")
    S.mannequin(2, (7.2, 0.45, 0.0), (-1, 0), "dressing", "seated, a shopping bag at its feet")
    S.mannequin(3, (0.0, -0.75, -0.6), (0, 1), "npc", "on the bandstand, a conductor's baton raised")
    S.mannequin(4, (-3.2, -1.0, 3.2), (1, -1), "monster", "down in the court, facing the bandstand")
    S.corridor("ring_N", -8.0, 8.0, z0 + 0.2, -7.5)
    S.corridor("ring_S", -8.0, 8.0, 7.5, z1 - 0.2)
    S.corridor("ring_W", x0 + 0.2, -7.5, -8.0, 8.0)
    S.corridor("ring_E", 7.5, x1 - 0.2, -8.0, 8.0)
    S.corridor("court", -4.7, 4.7, 2.15, 4.7, -1.0)
    S.label("SKY COURT", 0.0, 9.6)
    S.label("sunken court (y -1)", 0.0, 3.3, kind="note")
    S.label("bandstand", 0.0, -2.6, kind="note")
    for x in (-6, 6):
        for z in (-6, 6):
            S.light(x, h - 0.5, z, 600)
    S.light(0.0, 1.6, 0.0, 120)
    S.still = ((0.0, 0.0, z1 - 1.3), (0.0, -1.0), 12)
    return S


def scene_3012():
    S = Scene("scene_3012", "The painted-sky street (IMG_3012, a label only)", "32 m by 12 m, 8 m high: a fake old-town street of house fronts under a painted sky",
              mood="liminal, painted sky")
    x0, x1, z0, z1, h = -16.0, 16.0, -6.0, 6.0, 8.0
    shell(S, "Street", x0, x1, z0, z1, 0.0, h, holes={"W": [(0.0, DOOR_W, DOOR_H)], "E": [(-3.0, KIT_W, DOOR_H), (3.0, KIT_W, DOOR_H)]},
          fmat="cobble", wmat="mural", cmat="sky")
    single_door(S, "wing_cinema", "W", 0.0, x0, props={"kind": "unmarked door"})
    door_link(S, "wing_cinema", "W", 0.0, x0, "wing_cinema (the concourse)")
    kit_door(S, "sky_hall_01", "E", -3.0, x1)
    door_link(S, "sky_hall_01", "E", -3.0, x1, "sky_hall_01 (back to the sky court)")
    kit_door(S, "sky_hall_02", "E", 3.0, x1)
    door_link(S, "sky_hall_02", "E", 3.0, x1, "sky_hall_02 (on to the escalator well)")
    S.marker("Spawn", (x0 + 1.3, 0.0, 0.0))
    # the house fronts along both sides: four a side, of different heights, each with a door that does not open and a balcony
    for side, za, zb in (("N", z0, z0 + 0.6), ("S", z1 - 0.6, z1)):
        for k, (xa, hh) in enumerate(((-16.0, 5.5), (-8.0, 7.0), (0.0, 6.0), (8.0, 6.5))):
            mat = "facade_a" if (k + (side == "S")) % 2 else "facade_b"
            S.solid(f"Front_{side}{k + 1}", (xa, 0.0, za), (xa + 8.0, hh, zb), mat)
            fz = (zb, zb + 0.05) if side == "N" else (za - 0.05, za)
            S.solid(f"Front_{side}{k + 1}_Door", (xa + 3.4, 0.0, fz[0]), (xa + 4.6, 2.4, fz[1]), "fake_door")
            bz = (zb, zb + 0.8) if side == "N" else (za - 0.8, za)
            S.decor(f"Balcony_{side}{k + 1}", (xa + 1.0, 3.0, bz[0]), (xa + 3.0, 3.15, bz[1]), "facade_a")
            S.decor(f"Awning_{side}{k + 1}", (xa + 5.0, 2.6, bz[0]), (xa + 7.4, 2.7, bz[1]), "carpet_red")
    # lamp posts, the cafe tables under their sheets
    for x in (-12.0, -6.0, 0.0, 6.0, 12.0):
        for z in (-4.0, 4.0):
            S.solid("Lamp_Post", (x - 0.09, 0.0, z - 0.09), (x + 0.09, 3.6, z + 0.09), "rail")
            S.decor("Lamp_Head", (x - 0.25, 3.6, z - 0.25), (x + 0.25, 4.0, z + 0.25), "sign")
    for x in (-9.0, 3.0):
        for z in (-4.8, 4.8):
            sheeted(S, "Cafe_Table", x - 0.4, x + 0.4, z - 0.4, z + 0.4, 0.75)
            box(S, "Cafe_Chair", x + 0.6, x + 1.05, z - 0.22, z + 0.22, 0.0, 0.45, "furniture")
    S.decor("Arch", (x1 - 0.3, 2.6, -4.2), (x1, 3.2, 4.2), "facade_b")
    S.mannequin(1, (3.82, 0.45, 4.8), (-1, 0), "dressing", "seated at a cafe table")
    S.mannequin(2, (-8.17, 0.45, -4.8), (-1, 0), "dressing", "seated at a cafe table, a cup raised")
    S.mannequin(3, (2.0, 0.0, 0.0), (-1, 0), "monster", "in the middle of the street, facing the way you came in")
    S.mannequin(4, (13.0, 0.0, 2.0), (-1, 0), "npc", "by the sky-hall doors, as if waiting for someone")
    S.corridor("street", x0 + 0.2, x1 - 0.2, -3.85, 3.85)
    S.label("PAINTED-SKY STREET", 0.0, 0.0)
    S.label("house fronts (doors do not open)", 0.0, -4.9, kind="note")
    S.label("house fronts", 0.0, 4.9, kind="note")
    for x in (-12, -4, 4, 12):
        S.light(x, h - 0.5, 0.0, 500)
    for x in (-12, 0, 12):
        S.light(x, 3.5, 0.0, 80)
    S.still = ((x0 + 1.3, 0.0, 0.0), (1.0, 0.0), 6)
    return S


def scene_2991():
    S = Scene("scene_2991", "The soft play and the carousel (IMG_2991 with IMG_3014, labels only)",
              "32 m by 14 m: a soft-play court 18 m by 14 m (7 m high, painted sky) open to a carousel hall 14 m by 14 m (9 m high)",
              mood="liminal, painted sky")
    z0, z1 = -7.0, 7.0
    shell(S, "Play", -16.0, 2.0, z0, z1, 0.0, 7.0, holes={"S": [(-7.0, DOOR_W, DOOR_H)], "E": [(0.0, 6.0, 5.0)]}, fmat="tile", wmat="mural", cmat="sky")
    shell(S, "Carousel", 2.2, 16.0, z0, z1, 0.0, 9.0, holes={"E": [(0.0, KIT_W, DOOR_H)]}, sides="NSE", fmat="marble", wmat="mural", cmat="sky")
    S.solid("Carousel_Wall_W_Top", (2.0, 7.0, z0), (2.2, 9.0, z1), "mural")
    single_door(S, "wing_entertainment", "S", -7.0, z1, props={"kind": "unmarked door"})
    door_link(S, "wing_entertainment", "S", -7.0, z1, "wing_entertainment (the concourse)")
    kit_door(S, "sky_hall_04", "E", 0.0, 16.0)
    door_link(S, "sky_hall_04", "E", 0.0, 16.0, "sky_hall_04 (back to the construction zone)")
    S.marker("Spawn", (-7.0, 0.0, z1 - 1.3))
    # the soft play: the frame (solid, padded), the drained ball pit, the parents' benches
    box(S, "SoftPlay_Frame", -14.0, -7.0, -6.5, -1.5, 0.0, 3.2, "padding")
    S.decor("SoftPlay_Net", (-14.0, 3.2, -6.5), (-7.0, 4.2, -1.5), "sheet")
    S.decor("Slide", (-7.0, 0.0, -3.0), (-5.6, 2.4, -2.0), "sign")
    for nm, mn, mx in (("N", (-5.0, 0.0, -6.0), (-1.0, 0.5, -5.8)), ("S", (-5.0, 0.0, -2.2), (-1.0, 0.5, -2.0)),
                       ("W", (-5.0, 0.0, -5.8), (-4.8, 0.5, -2.2)), ("E", (-1.2, 0.0, -5.8), (-1.0, 0.5, -2.2))):
        S.solid(f"BallPit_Rim_{nm}", mn, mx, "padding")
    S.decor("BallPit_Floor", (-4.8, 0.0, -5.8), (-1.2, 0.05, -2.2), "sign")
    for z in (-4.0, -1.0, 2.0, 5.0):
        box(S, "Parent_Bench", -15.8, -15.3, z - 1.0, z + 1.0, 0.0, 0.45, "counter")
    S.decor("Toddler_Mat", (-12.0, 0.0, 2.0), (-8.0, 0.04, 5.0), "padding")
    S.label("soft play (padded frame)", -10.5, -0.9, kind="note")
    S.label("ball pit (drained)", -3.0, -1.4, kind="note")
    # the carousel: a round platform as two boxes, the centre pole, eight horse poles, its canopy
    cx = 9.0
    S.solid("Carousel_Platform", (cx - 4.0, 0.0, -2.5), (cx + 4.0, 0.3, 2.5), "furniture")
    S.solid("Carousel_Platform", (cx - 2.5, 0.0, -4.0), (cx + 2.5, 0.3, 4.0), "furniture")
    S.solid("Carousel_Centre", (cx - 0.5, 0.3, -0.5), (cx + 0.5, 6.0, 0.5), "sign")
    for k in range(8):
        a = math.pi * k / 4
        hx, hz = cx + 3.0 * math.cos(a), 3.0 * math.sin(a)
        S.solid("Horse_Pole", (hx - 0.04, 0.3, hz - 0.04), (hx + 0.04, 4.5, hz + 0.04), "sign")
        S.decor("Horse", (hx - 0.2, 1.1, hz - 0.5), (hx + 0.2, 1.8, hz + 0.5), "sheet")
    S.decor("Carousel_Canopy", (cx - 4.2, 4.5, -4.2), (cx + 4.2, 5.2, 4.2), "facade_a")
    S.mannequin(1, (-15.55, 0.45, 2.0), (1, 0), "dressing", "a parent on the bench, watching the soft play")
    S.mannequin(2, (cx + 1.5, 0.3, 2.6), (1, 0), "dressing", "beside a horse on the carousel")
    S.mannequin(3, (cx - 1.4, 0.3, -1.0), (-1, 0), "monster", "on the carousel, facing the soft play")
    S.mannequin(4, (-6.2, 0.0, -0.8), (0, 1), "monster", "at the foot of the slide")
    S.corridor("play", -15.2, 1.8, -1.3, z1 - 0.2)
    S.corridor("opening", 1.8, 4.8, -2.9, 2.9)
    S.corridor("carousel_N", 2.4, 15.8, z0 + 0.2, -4.1)
    S.corridor("carousel_S", 2.4, 15.8, 4.1, z1 - 0.2)
    S.corridor("carousel_E", 13.1, 15.8, z0 + 0.2, z1 - 0.2)
    S.label("SOFT PLAY", -9.0, 3.0)
    S.label("CAROUSEL", cx, 5.6)
    for x, z, p in ((-11, -3, 400), (-11, 4, 400), (-3, 3, 400), (cx, -5, 500), (cx, 5, 500), (14, 0, 300)):
        S.light(x, 6.2, z, p)
    S.light(cx, 4.2, 0.0, 150)
    S.still = ((-12.0, 0.0, 3.0), (1.0, -0.12), 6)
    return S


def scene_3008():
    S = Scene("scene_3008", "The escalator well (IMG_3008 with IMG_3010, labels only)",
              "16 m by 24 m, 9.5 m high under a painted sky: a lower concourse, a gallery at y 4.5, two stopped escalators", levels=(0.0, 4.5),
              mood="liminal, painted sky")
    S.level_names = {0.0: "lower concourse (y 0)", 4.5: "gallery (y 4.5)"}
    x0, x1, z0, z1, h, gy = -8.0, 8.0, -12.0, 12.0, 9.5, 4.5
    shell(S, "Well", x0, x1, z0, z1, 0.0, h, holes={"S": [(0.0, DOOR_W, DOOR_H)], "N": [(0.0, KIT_W, DOOR_H, gy)], "E": [(-7.5, KIT_W, DOOR_H, gy)]},
          fmat="marble", wmat="mural", cmat="sky")
    single_door(S, "wing_entertainment", "S", 0.0, z1, props={"kind": "unmarked door"})
    door_link(S, "wing_entertainment", "S", 0.0, z1, "wing_entertainment (the concourse)")
    kit_door(S, "sky_hall_02", "N", 0.0, z0, y=gy)
    door_link(S, "sky_hall_02", "N", 0.0, z0, "sky_hall_02 (back to the painted-sky street)", y=gy)
    kit_door(S, "sky_hall_03", "E", -7.5, x1, y=gy)
    door_link(S, "sky_hall_03", "E", -7.5, x1, "sky_hall_03 (on to the mirror bathroom)", y=gy)
    S.marker("Spawn", (0.0, 0.0, z1 - 1.3))
    # the gallery, its rail (open at the escalators' heads), the two stopped escalators (stairs, one box a step)
    S.solid("Gallery_Slab", (x0, gy - SLAB, z0), (x1, gy, -3.0), "floor")
    for xa, xb in ((x0, -2.7), (-1.3, 1.3), (2.7, x1)):
        S.solid("Gallery_Rail", (xa, gy, -3.1), (xb, gy + 1.0, -3.0), "rail")
    flight(S, "esc_up", -2.6, -1.4, 4.2, -1, "z", 0.0, gy, 18, 0.4)
    flight(S, "esc_down", 1.4, 2.6, 4.2, -1, "z", 0.0, gy, 18, 0.4)
    S.decor("Escalator_Skirt", (-2.75, 0.0, -3.0), (-2.6, 1.0, 4.2), "rail")
    S.decor("Escalator_Skirt", (2.6, 0.0, -3.0), (2.75, 1.0, 4.2), "rail")
    S.decor("Escalator_Middle", (-1.4, 0.0, 3.4), (1.4, 1.0, 4.2), "rail")
    S.label("escalators (stopped)", 0.0, 5.0, kind="note")
    # shuttered fronts below and above, planters, a dead information kiosk
    for z in (-9.0, 6.0):
        shutter_front(S, f"W_{int(z)}", "W", z, x0, "SHOE REPAIR" if z < 0 else "KEYS CUT", width=4.0)
        shutter_front(S, f"E_{int(z)}", "E", z, x1, "PERFUME" if z < 0 else "WATCHES", width=4.0)
    S.solid("Shutter_Gallery_W", (x0, gy, -10.5), (x0 + 0.12, gy + 3.2, -6.5), "shutter")
    S.label("TRAVEL AGENT (gallery)", x0 + 1.8, -8.5, gy, kind="note")
    box(S, "Planter", -1.0, 1.0, -11.0, -9.0, 0.0, 0.8, "concrete")
    S.decor("Planter_Fern", (-0.8, 0.8, -10.8), (0.8, 1.6, -9.2), "plant")
    box(S, "Info_Kiosk", -0.8, 0.8, -1.0, 0.6, 0.0, 1.2, "counter")
    box(S, "Gallery_Bench", -6.5, -4.5, -11.6, -11.1, gy, gy + 0.45, "counter")
    S.mannequin(1, (-2.0, 2.25, 0.8), (0, 1), "monster", "halfway up the stopped escalator, facing down")
    S.mannequin(2, (3.6, gy, -3.6), (0, 1), "npc", "at the gallery rail, looking down")
    S.mannequin(3, (x0 + 0.8, 0.0, 6.0), (1, 0), "dressing", "in front of the KEYS CUT shutter")
    S.mannequin(4, (x1 - 0.8, 0.0, -9.0), (-1, 0), "dressing", "in front of the PERFUME shutter")
    S.corridor("lower_south", x0 + 0.2, x1 - 0.2, 4.3, z1 - 0.2)
    S.corridor("lower_west", x0 + 0.2, -3.0, z0 + 0.2, 4.3)
    S.corridor("lower_east", 3.0, x1 - 0.2, z0 + 0.2, 4.3)
    S.corridor("gallery", x0 + 0.2, x1 - 0.2, z0 + 0.7, -3.15, gy)
    S.label("ESCALATOR WELL", 0.0, 8.0)
    S.label("GALLERY", 0.0, -6.5, gy)
    S.label("under the gallery", -5.0, -6.0, kind="note")
    for x in (-4, 4):
        for z in (-8, 0, 8):
            S.light(x, h - 0.6, z, 500)
    S.light(0.0, 3.8, -8.0, 120)
    S.still = ((0.0, 0.0, z1 - 1.3), (0.0, -1.0), 14)
    return S


# ---------------------------------------------------------------- the mirror bathroom: a portal and a puzzle
MIRROR_X = (-3.75, -2.25, -0.75, 0.75, 2.25, 3.75)
PORTAL_MIRROR = 4                       # the one mirror that is a way through ([DEFAULT]; the page decides how the puzzle shows which)


def mirror_bathroom():
    S = Scene("mirror_bathroom", "The mirror bathroom", "10 m by 8 m, 3 m high: six mirrors over the basins, four stalls", mood="a portal and a puzzle")
    x0, x1, z0, z1, h = -5.0, 5.0, -4.0, 4.0, 3.0
    shell(S, "Restroom", x0, x1, z0, z1, 0.0, h, holes={"S": [(-3.6, DOOR_W, DOOR_H)]}, fmat="tile", wmat="tile")
    single_door(S, "wing_cinema", "S", -3.6, z1, props={"kind": "restroom door"})
    door_link(S, "wing_cinema", "S", -3.6, z1, "wing_cinema (the concourse)")
    S.marker("Spawn", (-3.6, 0.0, z1 - 1.3))
    # the vanity, and over it six mirrors as separate objects, Mirror_1 to Mirror_6 (art only; the wall behind them collides)
    box(S, "Vanity", -4.6, 4.6, z0, -3.4, 0.0, 0.85, "counter")
    for k, x in enumerate(MIRROR_X, 1):
        portal = k == PORTAL_MIRROR
        S.art(f"Mirror_{k}", (x - 0.65, 1.0, z0), (x + 0.65, 2.2, z0 + 0.03), "mirror",
              props={"mirror": k, "portal": 1 if portal else 0, "portal_to": "sky_hall_03" if portal else ""})
        S.decor(f"Basin_{k}", (x - 0.25, 0.85, -3.9), (x + 0.25, 0.95, -3.5), "tile")
        S.spot("mirror", k, (x, 0.0, -2.95), face=(0, -1), props={"mirror": f"Mirror_{k}", "portal": 1 if portal else 0})
        S.label(f"Mirror_{k}", x, -4.6, kind="note")
    S.link("mirror", (MIRROR_X[PORTAL_MIRROR - 1], 0.0, -2.95), (MIRROR_X[PORTAL_MIRROR - 1], 0.0, -2.35), (0, 1),
           f"sky_hall_03 (through Mirror_{PORTAL_MIRROR}, once the puzzle is solved)")
    S.spot("puzzle", 1, (0.0, 0.0, -1.6), face=(0, -1), props={"what": "which mirror is a way through: the one whose reflection is right"})
    # four stalls along the south wall, east of the door
    for k in range(4):
        a = -2.2 + 1.8 * k
        S.solid("Stall_Partition", (a, 0.0, 2.45), (a + 0.05, 2.1, z1), "fake_door")
        S.solid("Stall_Front", (a, 0.0, 2.4), (a + 0.55, 2.1, 2.45), "fake_door")
        S.solid("Stall_Front", (a + 1.25, 0.0, 2.4), (a + 1.8, 2.1, 2.45), "fake_door")
        S.door(f"stall_{k + 1}", (a + 0.55, 0.0, 2.4), (1, 0), (0, 1), width=0.7, height=1.9, props={"kind": "stall"})
        S.decor("Toilet", (a + 0.6, 0.0, 3.3), (a + 1.2, 0.45, z1), "tile")
    S.solid("Stall_Partition", (x1 - 0.05, 0.0, 2.45), (x1, 2.1, z1), "fake_door")
    S.decor("Hand_Dryer", (x0, 1.1, -1.0), (x0 + 0.25, 1.5, -0.6), "column")
    S.mannequin(1, (3.75, 0.0, -2.9), (0, -1), "monster", "at the end basin, facing its mirror")
    S.corridor("room", x0 + 0.1, x1 - 0.1, -3.35, 2.35)
    S.corridor("entry", x0 + 0.1, -2.25, 2.25, z1 - 0.1)
    S.label("MIRROR BATHROOM", 0.0, 0.6)
    S.label("stalls", 1.4, 3.6, kind="note")
    S.light(-2.5, h - 0.3, -1.0, 150)
    S.light(2.5, h - 0.3, -1.0, 150)
    S.light(1.4, h - 0.3, 3.2, 60)
    S.still = ((-3.6, 0.0, z1 - 1.3), (0.55, -1.0), -3)
    return S


# ---------------------------------------------------------------- the sky halls: the kit's painted-sky hall, in the kit's frame
def sky_hall(k):
    sid = f"sky_hall_{k:02d}"
    S = Scene(sid, f"Painted-sky hall {k} (the connector kit's sky_hall)", "10 m by 2.4 m, 3.0 m high: the kit's sky hall, an EXIT door at the far end",
              mood="connector, painted sky")
    ends = SKY_HALLS[sid]
    # the kit's colliders, by the kit's names
    S.solid("Sky_Ceiling", (-1.4, 3.0, -10.4), (1.4, 3.25, 0.0), "ceiling", ("ceiling",))
    S.solid("Sky_Floor", (-1.2, -0.3, -10.2), (1.2, 0.0, -0.2), "parquet")
    S.solid("Sky_Wall_W", (-1.4, 0.0, -10.4), (-1.2, 3.0, 0.0), "mural")
    S.solid("Sky_Wall_E", (1.2, 0.0, -10.4), (1.4, 3.0, 0.0), "mural")
    for i, (za, zb) in enumerate(((-0.2, 0.0), (-10.4, -10.2))):
        S.solid(f"Sky_End_{3 * i}", (-1.2, 0.0, za), (-0.55, 3.0, zb), "mural")
        S.solid(f"Sky_End_{3 * i + 1}", (0.55, 0.0, za), (1.2, 3.0, zb), "mural")
        S.solid(f"Sky_End_{3 * i + 2}", (-0.55, DOOR_H, za), (0.55, 3.0, zb), "mural")
    S.decor("Laylight", (-0.9, 2.98, -8.6), (0.9, 3.0, -1.8), "sky", ("ceiling",))
    S.decor("Wainscot_W", (-1.2, 0.0, -10.2), (-1.18, 1.0, -0.2), "sheet")
    S.decor("Wainscot_E", (1.18, 0.0, -10.2), (1.2, 1.0, -0.2), "sheet")
    S.decor("Exit_Sign", (-0.4, 2.25, -10.2), (0.4, 2.5, -10.15), "exit")
    S.door("entry", (-0.52, 0.0, -0.1), (1, 0), (0, -1), width=KIT_LEAF, height=KIT_H, props={"kind": "hall door"}, swing=90)
    S.door("exit", (0.52, 0.0, -10.3), (-1, 0), (0, 1), width=KIT_LEAF, height=KIT_H, props={"kind": "EXIT door"}, swing=90)
    S.link("entry", (0.0, 0.0, -0.7), (0.0, 0.0, -1.1), (0, -1), ends["entry"])
    S.link("exit", (0.0, 0.0, -9.7), (0.0, 0.0, -9.3), (0, 1), ends["exit"])
    S.marker("Entry", (0.0, 0.0, -1.1), kind="Entrance")
    S.marker("Exit", (0.0, 0.0, -9.3), kind="Exit")
    if k % 2 == 0:
        S.mannequin(1, (0.3, 0.0, -5.6), (0, 1), "monster", "halfway down the hall, facing the entry door")
    S.corridor("hall", -1.15, 1.15, -10.15, -0.25)
    S.label(f"SKY HALL {k}", 0.0, -5.2)
    S.label("entry", 0.0, -0.9, kind="note")
    S.label("EXIT", 0.0, -9.5, kind="note")
    S.light(0.0, 2.7, -3.0, 70)
    S.light(0.0, 2.7, -7.4, 70)
    S.still = ((0.0, 0.0, -1.1), (0.0, -1.0), 2)
    return S


SKY_HALLS = {   # which scene each end of a sky hall opens onto
    "sky_hall_01": {"entry": "scene_2909 (the sky court's north door)", "exit": "scene_3012 (the painted-sky street, east end)"},
    "sky_hall_02": {"entry": "scene_3012 (the painted-sky street, east end)", "exit": "scene_3008 (the escalator well's gallery)"},
    "sky_hall_03": {"entry": "scene_3008 (the escalator well's gallery, east door)", "exit": f"mirror_bathroom (out of Mirror_{PORTAL_MIRROR})"},
    "sky_hall_04": {"entry": "construction (the doorway off the scaffold deck)", "exit": "scene_2991 (the carousel hall's east door)"},
}


# ---------------------------------------------------------------- the scenes and how they join
SCENES = {
    "wing_books": lambda: wing("wing_books", WINGS["wing_books"]["title"], WINGS["wing_books"]),
    "wing_cinema": lambda: wing("wing_cinema", WINGS["wing_cinema"]["title"], WINGS["wing_cinema"]),
    "wing_entertainment": lambda: wing("wing_entertainment", WINGS["wing_entertainment"]["title"], WINGS["wing_entertainment"]),
    "bookstore": bookstore, "bookstore_desk": bookstore_desk, "cinema_lobby": cinema_lobby,
    "scene_2909": scene_2909, "scene_3012": scene_3012, "scene_2991": scene_2991, "scene_3008": scene_3008,
    "mirror_bathroom": mirror_bathroom, "food_court": food_court, "construction": construction, "service_corridor": service_corridor,
    **{f"sky_hall_{k:02d}": (lambda k=k: sky_hall(k)) for k in range(1, 5)},
}

# Every link between two scenes of this set: (scene, door) <-> (scene, door). Pressing F at one side's Link_ puts you on the other side's Arrive_.
PAIRS = [
    (("wing_books", "bookstore"), ("bookstore", "wing_books"), "doors", "the bookstore's doors on the wing's west side"),
    (("bookstore", "bookstore_desk"), ("bookstore_desk", "bookstore"), "doors", "the INFORMATION door in the bookstore's east wall"),
    (("wing_books", "construction"), ("construction", "wing_books"), "doors", "the site door in the hoarding at the wing's far (north) end"),
    (("wing_books", "scene_2909"), ("scene_2909", "wing_books"), "doors", "an unmarked door between two shutters"),
    (("wing_cinema", "cinema_lobby"), ("cinema_lobby", "wing_cinema"), "doors", "the cinema's glass doors at the wing's far (west) end"),
    (("wing_cinema", "mirror_bathroom"), ("mirror_bathroom", "wing_cinema"), "doors", "the RESTROOMS bay"),
    (("wing_cinema", "scene_3012"), ("scene_3012", "wing_cinema"), "doors", "an unmarked door between two shutters"),
    (("wing_entertainment", "food_court"), ("food_court", "wing_entertainment"), "doors", "the food court's glass doors at the wing's far (east) end"),
    (("wing_entertainment", "scene_2991"), ("scene_2991", "wing_entertainment"), "doors", "an unmarked door between two shutters"),
    (("wing_entertainment", "scene_3008"), ("scene_3008", "wing_entertainment"), "doors", "an unmarked door between two shutters"),
    (("wing_books", "service_corridor"), ("service_corridor", "wing_books"), "service", "the wing's STAFF ONLY door"),
    (("wing_cinema", "service_corridor"), ("service_corridor", "wing_cinema"), "service", "the wing's STAFF ONLY door"),
    (("wing_entertainment", "service_corridor"), ("service_corridor", "wing_entertainment"), "service", "the wing's STAFF ONLY door"),
    (("food_court", "service_corridor"), ("service_corridor", "food_court"), "service", "the kitchens' door behind the stalls"),
    (("scene_2909", "sky_hall_01"), ("sky_hall_01", "entry"), "sky_hall", "the sky court's north door"),
    (("sky_hall_01", "exit"), ("scene_3012", "sky_hall_01"), "sky_hall", "out by the EXIT door onto the painted-sky street"),
    (("scene_3012", "sky_hall_02"), ("sky_hall_02", "entry"), "sky_hall", "the street's east end, south door"),
    (("sky_hall_02", "exit"), ("scene_3008", "sky_hall_02"), "sky_hall", "out by the EXIT door onto the escalator well's gallery"),
    (("scene_3008", "sky_hall_03"), ("sky_hall_03", "entry"), "sky_hall", "the gallery's east door"),
    (("sky_hall_03", "exit"), ("mirror_bathroom", "mirror"), "mirror", f"out by the EXIT door and through Mirror_{PORTAL_MIRROR} into the bathroom; back the same way once solved"),
    (("construction", "sky_hall_04"), ("sky_hall_04", "entry"), "sky_hall", "the unfinished doorway off the scaffold deck (y 3)"),
    (("sky_hall_04", "exit"), ("scene_2991", "sky_hall_04"), "sky_hall", "out by the EXIT door into the carousel hall"),
]


def _ent(x, z, fx, fz):
    return f"F at ({x:g}, 0, {z:g}), arrive at ({x + 0.7 * fx:g}, 0, {z + 0.7 * fz:g}) facing ({fx:g}, {fz:g})"


# Links that leave this set: the other side is part 1's entrance (shared/city.js MALL; the coordinator cuts its walls and wires the links), or
# the hidden network (not built).
OUTSIDE = {
    ("wing_books", "entrance"): "entrance's north wall, the 3.2 m gap between the PHONES and FOOD COURT shopfronts behind the fountain (x -1.6 to 1.6): "
                                "a 2.4 m opening x -1.2 to 1.2, 2.6 m high. entrance's side, for the coordinator: " + _ent(0, -11.3, 0, 1),
    ("wing_cinema", "entrance"): "entrance's west wall, the 5.2 m gap between the GIFTS and PHOTO shopfronts (z -3.6 to 1.6): a 2.4 m opening "
                                 "z -2.2 to 0.2, 2.6 m high. entrance's side, for the coordinator: " + _ent(-15.3, -1, 1, 0),
    ("wing_entertainment", "entrance"): "entrance's east wall, the 5.2 m gap between the OPTICIAN and TOYS shopfronts (z -3.6 to 1.6): a 2.4 m "
                                        "opening z -2.2 to 0.2, 2.6 m high. entrance's side, for the coordinator: " + _ent(15.3, -1, -1, 0),
    ("food_court", "entrance"): "entrance's FOOD COURT shopfront (north wall, x 1.6 to 6.4): its shutter goes up on a 2.4 m opening x 2.8 to 5.2, "
                                "2.6 m high. entrance's side, for the coordinator: " + _ent(4, -11.3, 0, 1),
    ("service_corridor", "network"): "the hidden network: the freight lift at the spur's end (the connector kit's service corridor and freight "
                                     "lift, not built yet); keycard_tier_1 at the reader, Spot_keycard_1. Its other end is for Secret Operations' plan",
}


def build(sid):
    return SCENES[sid]()


def plan_view(S, level=0.0, ppm_target=1700.0):
    """The plan's bounds (x0, x1, z0, z1) with a margin, and its pixel size: the Blender render and the sheets share this mapping."""
    bs = [b for b in S.boxes if b["col"] or b["name"].startswith("decor_")]
    xs = [v for b in bs for v in (b["min"][0], b["max"][0])]
    zs = [v for b in bs for v in (b["min"][2], b["max"][2])]
    m = 2.0
    x0, x1, z0, z1 = min(xs) - m, max(xs) + m, min(zs) - m, max(zs) + m
    span = max(x1 - x0, z1 - z0)
    ppm = ppm_target / span
    return {"x0": x0, "x1": x1, "z0": z0, "z1": z1, "W": int(round((x1 - x0) * ppm)), "H": int(round((z1 - z0) * ppm)), "ppm": ppm}


def plan_hidden(S, b, level):
    """Is box b left out of the plan for `level`? (ceilings, and anything that starts 2.4 m or more above the level; on a one-level plan the
    steps always show)"""
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
    items = sorted([("C", b["name"], b) for b in S.boxes] + [("E", e["name"], e) for e in S.empties] + [("D", d["name"], d) for d in S.doors]
                   + [("K", "COL_" + b["name"], b) for b in S.boxes if b["col"]], key=lambda t: t[1])
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
    """The node names and extras in a .glb (its JSON chunk), without Blender."""
    b = Path(path).read_bytes()
    n = struct.unpack_from("<I", b, 12)[0]
    doc = json.loads(b[20:20 + n].decode("utf-8"))
    return {nd.get("name", ""): nd.get("extras", {}) for nd in doc.get("nodes", [])}


def check(base, ids=None, glb_dir=None):
    """Links meet, steps keep to the rise, corridors are wide and clear, the mirrors are separate objects. Reads <base>/world/<scene>.json (and
    the bathroom's GLB); prints one line per gate; True if all pass."""
    ids = ids or list(SCENES)
    docs, bad = {}, []
    for sid in ids:
        f = out_path(base, sid)
        if not f.exists():
            bad.append(f"missing {f}")
            continue
        docs[sid] = json.loads(f.read_text())
    have = {(sid, l["door"]) for sid, d in docs.items() for l in d.get("links", [])}
    paired = set()
    for a, b, kind, note in PAIRS:
        for side in (a, b):
            paired.add(side)
            if side[0] in docs and side not in have:
                bad.append(f"link {side[0]}.{side[1]} ({kind} to {b if side == a else a}) is not in {side[0]}.json")
    for side in sorted(have):
        if side not in paired and side not in OUTSIDE:
            bad.append(f"link {side[0]}.{side[1]} has no other side in PAIRS")
    for side in OUTSIDE:
        if side[0] in docs and side not in have:
            bad.append(f"link {side[0]}.{side[1]} (off this set) is not in {side[0]}.json")
    print(f"GATE links: {len(PAIRS)} pairs, {len(PAIRS) * 2} sides, {len(OUTSIDE)} that leave this set; {len(have)} links in the files")
    for (s, dd) in sorted(OUTSIDE):
        print(f"  off this set: {s}.{dd} -> {'entrance' if dd == 'entrance' else 'the hidden network (freight lift, not built)'}")
    # every scene can be reached from the atrium through the pairs
    graph = {sid: set() for sid in SCENES}
    for (a, _), (b, _), _, _ in PAIRS:
        graph[a].add(b)
        graph[b].add(a)
    seen, todo = set(), [s for (s, dd) in OUTSIDE if dd == "entrance"]
    while todo:
        s = todo.pop()
        if s not in seen:
            seen.add(s)
            todo += list(graph[s])
    if set(SCENES) - seen:
        bad.append(f"not reachable from entrance: {sorted(set(SCENES) - seen)}")
    print(f"GATE navigable: {len(seen)} of {len(SCENES)} scenes reachable from entrance through the links")
    # steps: every Step_<flight>_<nn> collider, in order, keeps to MAX_RISE, from the floor it starts on to the floor it reaches
    nsteps, worst = 0, 0.0
    for sid in ids:
        S = build(sid)
        cols = {c["s"]: c for c in docs.get(sid, {}).get("colliders", [])}
        for fl in S.flights:
            steps = sorted((n, c) for n, c in cols.items() if n.startswith(f"Step_{fl['name']}_"))
            tops = [c["max"][1] for _, c in steps]
            if fl.get("down"):                              # steps down into a sunken floor: from the floor above, each step, the floor below
                seq, want = [fl["y_end"]] + tops + [fl["y_start"]], fl["n"] - 1
            else:
                seq, want = [fl["y_start"]] + tops + ([fl["y_end"]] if not tops or abs(tops[-1] - fl["y_end"]) > 1e-6 else []), fl["n"]
            rises = [abs(seq[i + 1] - seq[i]) for i in range(len(seq) - 1)]
            nsteps += len(steps)
            worst = max([worst] + rises)
            if len(steps) != want or any(r > MAX_RISE + 1e-6 for r in rises):
                bad.append(f"steps {sid}/{fl['name']}: {len(steps)} boxes, rises {rises}")
    print(f"GATE steps: {nsteps} step boxes, one box a step, the highest rise {worst:.3f} m (at most {MAX_RISE} m)")
    # corridors: at least MIN_CORRIDOR wide, and no standing collider inside
    ncor, narrow = 0, 99.0
    for sid in ids:
        S = build(sid)
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
    print(f"GATE corridors: {ncor} corridor, aisle and doorway rects, the narrowest {narrow:.2f} m (at least {MIN_CORRIDOR} m), none blocked")
    # the mirrors: Mirror_1 to Mirror_6 are separate objects in the bathroom's GLB, one of them the portal
    if "mirror_bathroom" in ids:
        dirs = [Path(glb_dir)] if glb_dir else [Path(base) / "glb", Path(base) / "docs/renders/mall_greybox/glb"]
        g = next((d / "mirror_bathroom.glb" for d in dirs if (d / "mirror_bathroom.glb").exists()), None)
        if g is None:
            print("GATE mirrors: no mirror_bathroom.glb next to the layout files (a --preview run): skipped")
        else:
            nodes = glb_nodes(g)
            want = [f"Mirror_{k}" for k in range(1, len(MIRROR_X) + 1)]
            miss = [m for m in want if m not in nodes]
            portal = [m for m in want if m in nodes and int(nodes[m].get("portal", 0)) == 1]
            if miss or portal != [f"Mirror_{PORTAL_MIRROR}"]:
                bad.append(f"mirrors: missing {miss}, portal {portal}")
            print(f"GATE mirrors: {len(want) - len(miss)} of {len(want)} Mirror_<n> nodes in mirror_bathroom.glb, the portal {portal}")
    nman = sum(1 for d in docs.values() for s in d.get("spots", []) if s["kind"] == "mannequin")
    print(f"  mannequin spots: {nman} in {sum(1 for d in docs.values() if any(s['kind'] == 'mannequin' for s in d.get('spots', [])))} scenes")
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
    base = Path(a[a.index("--out") + 1]) if "--out" in a else ROOT / "work/mall_greybox"
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
            bsdf.inputs["Roughness"].default_value = 0.8 if name not in ("water", "glass", "mirror") else 0.04
            if name == "mirror":
                bsdf.inputs["Metallic"].default_value = 1.0
            if name == "glass":                               # shopfront glazing and skylights: see-through in the stills
                for key in ("Transmission Weight", "Transmission"):
                    if key in bsdf.inputs:
                        bsdf.inputs[key].default_value = 1.0
                        break
                if "IOR" in bsdf.inputs:
                    bsdf.inputs["IOR"].default_value = 1.05
            if name in ("sky", "exit"):                       # the painted sky and the EXIT sign glow a little, so the stills read
                for key in ("Emission Color", "Emission"):
                    if key in bsdf.inputs:
                        bsdf.inputs[key].default_value = (*c, 1.0)
                        break
                if "Emission Strength" in bsdf.inputs:
                    bsdf.inputs["Emission Strength"].default_value = 0.6 if name == "sky" else 2.0
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
            ob = boxobj(b["name"], b, "Art")
            for k, val in b.get("props", {}).items():
                ob[k] = val
            arts.append((ob, b))
            if b["col"]:
                ob = boxobj("COL_" + b["name"], b, "Layout", hide=True)
                ob.display_type = "WIRE"
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
        cy.max_bounces = 8
        cy.transmission_bounces = 8
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

    def render_plan(S, arts, level, path):
        pv = plan_view(S, level)
        for ob, b in arts:
            ob.hide_render = plan_hidden(S, b, level) if "tags" in b and b.get("name") else False
        for ob in list(bpy.data.objects):
            if ob.type in ("LIGHT", "CAMERA"):
                bpy.data.objects.remove(ob, do_unlink=True)
        world((1.0, 1.0, 1.0), 0.45)
        add_light("SUN", (0, 0, 50), 1.6, "Plan_Sun", rot=(math.radians(2), math.radians(1), 0))    # straight down: no wall shadows on the plan
        cam = camera("Plan_Cam")
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = max(pv["x1"] - pv["x0"], pv["z1"] - pv["z0"])
        cam.data.sensor_fit = "AUTO"
        cam.data.clip_start, cam.data.clip_end = 0.1, 200.0
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
        world((0.6, 0.6, 0.62), 0.08)
        for i, (x, y, z, p) in enumerate(S.lights):
            add_light("POINT", B((x, y, z)), p, f"L{i}", size=0.4)
        (pos, face, pitch) = S.still
        cam = camera("Still_Cam")
        cam.data.lens, cam.data.sensor_width = 16.0, 36.0
        cam.data.clip_start = 0.05
        cam.location = B((pos[0], pos[1] + EYE, pos[2]))
        yaw = math.atan2(face[0], face[1])                                 # the -Y (empty) convention: a camera looks down its -Z
        cam.rotation_euler = (math.radians(90 + pitch), 0, math.pi + yaw)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1600, 900, 100
        sc.cycles.samples = 64
        add_light("POINT", B((pos[0], pos[1] + 2.0, pos[2])), 40, "CamFill", size=0.5)
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
    print("MALL_GREYBOX device", dev, "scenes", len(ids))
    for sid in ids:
        S = build(sid)
        arts = realize(S)
        p = out_path(base, sid)
        p.parent.mkdir(parents=True, exist_ok=True)
        export_scene.write(sid, p)
        export_glb(arts, base / "glb" / f"{sid}.glb")
        if render:
            for lv in S.levels:
                render_plan(S, arts, lv, base / "renders" / f"{sid}_plan_L{int(lv)}.png")
            render_still(S, arts, base / "renders" / f"{sid}_still.png")
        print(f"MALL_GREYBOX done {sid}: {len(S.boxes)} boxes, {len(S.doors)} doors, {len(S.empties)} empties")
    print("MALL_GREYBOX ALL DONE")


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
