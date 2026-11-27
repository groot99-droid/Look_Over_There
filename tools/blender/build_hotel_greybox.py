"""The hotel greybox (docs/BLENDER_AREAS.md, section 1, step 1): every scene of the apartment tower as plain grey boxes, to scale, with the
names the exporter reads (COL_, DoorLeaf_, Marker_, Link_/Arrive_, Zone_, Spot_, decor_), so the owner can review the whole layout at once.

    blender -b --factory-startup --python tools/blender/build_hotel_greybox.py -- [--scenes all|id,id,...] [--out <dir>] [--no-render]
    python tools/blender/build_hotel_greybox.py --check <dir>      the gates on exported files, no Blender (links meet, steps, corridors)
    python tools/blender/build_hotel_greybox.py --preview <dir>    writes the layout files from the model alone, no Blender (for --check)

For each scene the Blender run builds the boxes into an empty file, writes <out>/world/<scene>.json through tools/blender/export_scene.py
(the room layouts go to <out>/world/rooms/<layout>.json), the greybox art to <out>/glb/<scene>.glb, a top-down orthographic plan per level
(<out>/renders/<scene>_plan_L<y>.png, ceilings and everything 2.4 m above the level hidden) and one eye-height still (1.55 m,
<out>/renders/<scene>_still.png). The labels, scale bar and sheets are drawn afterwards by tools/blender/hotel_greybox_sheets.py from this
same model, so the plan's mapping is fixed here: plan_view(scene) gives the bounds and the pixel size.

Coordinates in this file are GAME coordinates (metres, y up, north = -z); Blender (x, y, z) is game (x, -z, y). Every scene has its floor
at y = 0. Repetition reuses one mesh: every box is the same unit cube per material, scaled (colliders and art share it), and every door
leaf is one leaf mesh. Each COL_<name> box has its art twin <name>; decor_ boxes have no collider. Zones are hidden boxes.

The scenes and their links are in SCENES and PAIRS below; the sizes and room lists are docs/BLENDER_AREAS.md's [DEFAULT]s unless
docs/renders/hotel_greybox/README.md says otherwise. Nothing here touches the manifest, index.html or shared/.
"""
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EYE = 1.55
T = 0.2                     # wall thickness
SLAB = 0.3                  # floor slab under every floor
DOOR_W, DOOR_H = 0.94, 2.16
MAX_RISE = 0.27
MIN_CORRIDOR = 1.6
WALKER_R = 0.28

MATS = {                    # flat greybox colours (linear RGB); no textures
    "floor": (0.58, 0.58, 0.56), "wall": (0.30, 0.30, 0.32), "ceiling": (0.62, 0.62, 0.62), "door": (0.62, 0.36, 0.16),
    "stair": (0.50, 0.46, 0.38), "furniture": (0.55, 0.47, 0.34), "counter": (0.42, 0.33, 0.24), "rail": (0.18, 0.18, 0.2),
    "water": (0.12, 0.38, 0.80), "tile": (0.80, 0.83, 0.85), "carpet_red": (0.42, 0.16, 0.14), "carpet_green": (0.16, 0.36, 0.18),
    "carpet_tan": (0.55, 0.46, 0.33), "marble": (0.70, 0.68, 0.64), "lift": (0.30, 0.38, 0.52), "fake_door": (0.40, 0.28, 0.20),
    "column": (0.45, 0.45, 0.45), "grate": (0.08, 0.08, 0.08), "roof": (0.36, 0.36, 0.36), "pad": (0.20, 0.55, 0.45),
    "safe": (0.35, 0.50, 0.40), "parapet": (0.40, 0.40, 0.42),
}


# ================================================================ the model (pure Python; no bpy)
class Scene:
    def __init__(s, sid, title, size, kind="scene", levels=(0.0,), mood=""):
        s.id, s.title, s.size, s.kind, s.levels, s.mood = sid, title, size, kind, list(levels), mood
        s.boxes, s.empties, s.doors, s.labels, s.lights, s.corridors, s.flights, s.outlines = [], [], [], [], [], [], [], []
        s.links = {}            # door id -> text (where it goes), for the plan labels
        s.still = None          # (pos, face, pitch_deg)
        s.sky = None            # world colour for an open-sky scene
        s.steps_always = True   # show Step_ boxes on the plan even above the cut
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

    def decor(s, name, mn, mx, mat="furniture"):
        n = s.uniq("decor_" + name)
        s.boxes.append({"name": n, "min": list(mn), "max": list(mx), "mat": mat, "col": False, "tags": set()})

    def zone(s, kind, name, mn, mx):
        n = s.uniq(f"Zone_{kind}_{name}")
        s.boxes.append({"name": n, "min": list(mn), "max": list(mx), "mat": "water", "col": False, "zone": kind, "tags": set()})

    def empty(s, name, pos, face=None, props=None):
        s.empties.append({"name": s.uniq(name), "pos": [float(v) for v in pos], "face": face, "props": dict(props or {})})

    def link(s, door, at, arrive, face, to="", label_at=None):
        s.empty(f"Link_{door}", at)
        s.empty(f"Arrive_{door}", arrive, face=face)
        s.links[door] = to

    def spot(s, kind, n, pos, face=(0, 1), props=None):
        s.empty(f"Spot_{kind}_{n}", pos, face=face, props=props)

    def marker(s, name, pos, kind="Spawn", props=None):
        p = {"kind": kind}
        p.update(props or {})
        s.empty(f"Marker_{name}", pos, props=p)

    def door(s, name, hinge, run, into, width=DOOR_W, height=DOOR_H, state="closed", props=None):
        """A leaf with its origin at the hinge. `run`: the game direction (x, z) from the hinge along the closed leaf; `into`: the side it
        opens toward. closed_yaw_deg is three.js's rotation.y of the leaf (its local +x runs from the hinge along it); +swing_deg opens it
        toward `into` (the galleries' convention)."""
        th = math.atan2(-run[1], run[0])
        op = math.atan2(-into[1], into[0])
        swing = 95.0 if math.sin(op - th) > 0 else -95.0
        p = {"width": round(width, 3), "height": round(height, 3), "closed_yaw_deg": round(math.degrees(th), 1), "swing_deg": swing, "state": state}
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


def shell(S, nm, x0, x1, z0, z1, y0=0.0, h=3.0, holes=None, ceiling=True, floor=True, fmat="floor", wmat="wall", sides="NSWE"):
    """A room: floor slab (top at y0), ceiling, and the four walls OUTSIDE the interior [x0, x1] x [z0, z1]. holes: {side: [(a, w, hh, yb)]},
    a = the hole's centre along the wall, w its width, hh its height, yb its bottom above y0 (default 0)."""
    holes = holes or {}

    def hs(side):
        return [(a - w / 2, a + w / 2, y0 + (rest[0] if rest else 0.0), y0 + (rest[0] if rest else 0.0) + hh) for a, w, hh, *rest in holes.get(side, [])]
    if floor:
        S.solid(f"{nm}_Floor", (x0 - T, y0 - SLAB, z0 - T), (x1 + T, y0, z1 + T), fmat)
    if ceiling:
        S.solid(f"{nm}_Ceiling", (x0 - T, y0 + h, z0 - T), (x1 + T, y0 + h + 0.2, z1 + T), "ceiling", ("ceiling",))
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
    tops = []
    for i in range(n):
        a, b = start + direction * i * tread, start + direction * (i + 1) * tread
        top = y_start + rise * (i + 1)
        lo, hi = min(a, b), max(a, b)
        if axis == "z":
            S.solid(f"Step_{name}_{i:02d}", (lane0, top - rise, lo), (lane1, top, hi), mat)
        else:
            S.solid(f"Step_{name}_{i:02d}", (lo, top - rise, lane0), (hi, top, lane1), mat)
        tops.append(round(top, 4))
    S.flights.append({"name": name, "y_start": y_start, "y_end": y_end, "n": n, "rise": round(rise, 4), "tread": tread})


def box(S, name, x0, x1, z0, z1, y0, y1, mat="furniture"):
    return S.solid(name, (x0, y0, z0), (x1, y1, z1), mat)


# ---------------------------------------------------------------- the room layouts (world/rooms/<layout>.json)
# A room's frame: the origin is the middle of its door opening, on the CORRIDOR face of the shared wall, at floor level; the room lies toward -z.
# The corridor door that opens onto it says where that frame goes: room_x, room_z (the origin, in the corridor scene) and room_yaw_deg (three's
# rotation.y). The room's door wall (z from -0.2 to 0) is the corridor's wall, so the two overlap exactly when the room is placed.
ROOMS = {  # layout: (width, depth, x offset of the interior's middle from the door)
    "motel_a": (4.0, 6.0, 0.8), "motel_b": (5.0, 6.0, 0.0), "green_room": (5.0, 7.0, 0.0), "clue_room": (5.0, 6.0, 0.0), "empty_room": (6.0, 8.0, 0.0),
    "apartment": (6.0, 5.0, -1.5),          # part 1's apartment (shared/city.js APARTMENT): its door is 1.5 m east of its middle; not built here
}
ROOM_H = 2.8


def room_layout(lay):
    w, d, ox = ROOMS[lay]
    titles = {"motel_a": "Motel room A (Room 1 in the photos)", "motel_b": "Motel room B (Room 2: two beds)", "green_room": "Green room (floor 2)",
              "clue_room": "Clue room (floor 3)", "empty_room": "Empty room (floor 3)"}
    S = Scene(lay, titles[lay], f"{w:g} m by {d:g} m, {ROOM_H:g} m high", kind="room")
    x0, x1, z0, z1 = ox - w / 2, ox + w / 2, -0.2 - d, -0.2
    fm = {"motel_a": "carpet_red", "motel_b": "carpet_red", "green_room": "carpet_green"}.get(lay, "carpet_tan")
    shell(S, "Room", x0, x1, z0, z1, 0.0, ROOM_H, holes={"S": [(0.0, DOOR_W, DOOR_H)]}, fmat=fm)
    S.marker("Door", (0.0, 0.0, -0.8), "Entrance")
    S.label("door to the corridor", 0.0, 0.6, kind="door")
    if lay == "motel_a":
        S.solid("Bath_Wall_N", (x0, 0, -4.3), (-0.65, ROOM_H, -4.2))
        S.solid("Bath_Wall_N_b", (0.05, 0, -4.3), (0.7, ROOM_H, -4.2))
        S.solid("Bath_Wall_E", (0.6, 0, z0), (0.7, ROOM_H, -4.3))
        box(S, "Bed", 0.8, 2.8, -4.0, -2.4, 0, 0.55)
        box(S, "Nightstand", 2.3, 2.8, -4.6, -4.1, 0, 0.6)
        box(S, "Dresser_TV", x0, -0.7, -3.6, -1.6, 0, 0.8)
        S.spot("bed", 1, (1.8, 0, -1.8), face=(0, -1))
        S.spot("hide", 1, (-0.3, 0, -5.4), props={"where": "bathroom"})
        S.label("bathroom", -0.3, -5.2)
        S.label("bed", 1.8, -3.2)
    elif lay == "motel_b":
        S.solid("Closet_Wall_E_a", (-1.3, 0, -1.4), (-1.2, ROOM_H, -1.2))
        S.solid("Closet_Wall_E_b", (-1.3, 0, -0.4), (-1.2, ROOM_H, z1))
        S.solid("Closet_Wall_S", (x0, 0, -1.5), (-1.2, ROOM_H, -1.4))
        box(S, "Bed_1", -2.4, -1.4, -5.0, -3.0, 0, 0.55)
        box(S, "Bed_2", 1.4, 2.4, -5.0, -3.0, 0, 0.55)
        box(S, "Nightstand", -0.25, 0.25, -5.0, -4.5, 0, 0.6)
        box(S, "Dresser", 1.5, 2.5, -1.6, -1.1, 0, 0.9)
        S.spot("bed", 1, (-1.9, 0, -2.4), face=(0, -1))
        S.spot("bed", 2, (1.9, 0, -2.4), face=(0, -1))
        S.spot("hide", 1, (-1.9, 0, -0.8), props={"where": "closet"})
        S.label("closet", -1.9, -0.6)
        S.label("beds", 0.0, -4.0)
    elif lay == "green_room":
        S.solid("Nook_Wall_S", (x0, 0, -5.7), (-1.3, ROOM_H, -5.6))
        S.solid("Nook_Wall_E", (-1.4, 0, z0), (-1.3, ROOM_H, -6.6))
        box(S, "Bed", -0.8, 0.8, z0, -5.2, 0, 0.55)
        box(S, "Armchair", 1.4, 2.2, -4.0, -3.2, 0, 0.8)
        box(S, "Wardrobe", 1.8, x1, -2.6, -1.6, 0, 2.0)
        S.spot("bed", 1, (1.3, 0, -6.2), face=(-1, 0))
        S.spot("hide", 1, (-1.95, 0, -6.45), props={"where": "wardrobe nook"})
        S.label("nook", -1.95, -6.2)
        S.label("bed", 0.0, -6.3)
    elif lay == "clue_room":
        box(S, "Desk", x0, -1.3, -4.0, -2.4, 0, 0.75)
        box(S, "Table", -0.6, 0.6, -3.8, -2.8, 0, 0.75)
        S.solid("Pinboard", (-1.5, 1.0, z0), (1.5, 2.2, z0 + 0.05), "fake_door")
        S.spot("clue", 1, (-0.8, 0, -5.4), face=(0, -1))
        S.spot("clue", 2, (1.8, 0, -1.2), face=(1, 0))
        S.spot("clue", 3, (1.5, 0, -4.5), face=(1, 0))
        S.spot("puzzle", 1, (0.0, 0, -1.8), face=(0, -1))
        S.label("pinboard", 0.0, -5.8)
    elif lay == "empty_room":
        box(S, "Chair", 1.8, 2.3, -6.0, -5.5, 0, 0.9)
        S.label("empty", 0.0, -4.0)
    S.light(ox, ROOM_H - 0.3, (z0 + z1) / 2, 120)
    S.still = ((0.0, 0.0, -0.6), (0.0, -1.0), -6)
    return S


def room_footprint(lay, ox_frame, z_frame, yaw180):
    w, d, ox = ROOMS[lay]
    if not yaw180:
        return (ox_frame + ox - w / 2, ox_frame + ox + w / 2, z_frame - 0.2 - d, z_frame - 0.2)
    return (ox_frame - ox - w / 2, ox_frame - ox + w / 2, z_frame + 0.2, z_frame + 0.2 + d)


# ---------------------------------------------------------------- the corridor floors
CORR_X, CORR_Z, CORR_H = 20.0, 1.1, 2.8
DOOR_XS = (-16.0, -8.0, 0.0, 8.0, 16.0)


def corridor_floor(sid, title, rooms, fmat, lift, east, features, mood, extra_doors=()):
    """A 40 m by 2.2 m corridor: rooms on both sides (DOOR_XS, north then south), the elevator at the west end when `lift`, and at the east end
    either a stairwell up (east = ('up', door id, target)) or a door to the stairwell (east = ('down', door id, target)).
    features: (kind, side, x) with kind alcove | closet; extra_doors: (door id, side, x, target) for doors to other scenes."""
    S = Scene(sid, title, "a corridor 40 m by 2.2 m, 2.8 m high, with rooms on both sides", mood=mood)
    x0, x1, z0, z1 = -CORR_X, CORR_X, -CORR_Z, CORR_Z
    holes = {"N": [], "S": [], "W": [], "E": []}
    for k, a in enumerate(DOOR_XS):
        holes["N"].append((a, DOOR_W, DOOR_H))
        holes["S"].append((a, DOOR_W, DOOR_H))
    for kind, side, a in features:
        holes[side].append((a, 1.2 if kind == "alcove" else 0.8, 2.4 if kind == "alcove" else DOOR_H))
    for did, side, a, to in extra_doors:
        holes[side].append((a, DOOR_W, DOOR_H))
    if lift:
        holes["W"].append((0.0, 1.2, 2.2))
    holes["E"].append((0.0, DOOR_W, DOOR_H))
    shell(S, "Corridor", x0, x1, z0, z1, 0.0, CORR_H, holes, fmat=fmat)
    S.corridor("corridor", x0, x1, z0, z1)
    S.label(title.split(":")[0], -10.0, 0.0)
    for x in range(-18, 20, 6):
        S.light(x, CORR_H - 0.3, 0.0, 60)
    # the room doors
    n = 0
    for side in ("N", "S"):
        for a in DOOR_XS:
            num, lay = rooms[n]
            n += 1
            sgn = -1 if side == "N" else 1
            zf = sgn * (CORR_Z + T)                          # the room-side face of the wall
            if side == "N":
                S.door(f"room_{num}", (a - DOOR_W / 2, 0.0, zf), (1, 0), (0, -1),
                       props={"room": str(num), "room_layout": lay, "room_x": a, "room_z": -CORR_Z, "room_yaw_deg": 0.0})
            else:
                S.door(f"room_{num}", (a + DOOR_W / 2, 0.0, zf), (-1, 0), (0, 1),
                       props={"room": str(num), "room_layout": lay, "room_x": a, "room_z": CORR_Z, "room_yaw_deg": 180.0})
            fp = room_footprint(lay, a, sgn * CORR_Z, side == "S")
            S.outlines.append({"x0": fp[0], "x1": fp[1], "z0": fp[2], "z1": fp[3], "text": f"{num}\n{lay}"})
    # alcoves and closets: the neighbour's game's hide spots
    hid = 0
    for kind, side, a in features:
        sgn = -1 if side == "N" else 1
        zin, zback = sgn * (CORR_Z + T), sgn * (CORR_Z + T + 1.0)
        lo, hi = min(zin, zback), max(zin, zback)
        S.solid(f"Alcove_Floor", (a - 0.8, -SLAB, min(lo, sgn * CORR_Z) - (T if sgn < 0 else 0)), (a + 0.8, 0.0, max(hi, sgn * CORR_Z) + (T if sgn > 0 else 0)), fmat)
        S.solid(f"Alcove_Back", (a - 0.8, 0.0, min(zback, zback + sgn * T)), (a + 0.8, 2.6, max(zback, zback + sgn * T)))
        S.solid(f"Alcove_Side", (a - 0.8, 0.0, lo), (a - 0.6, 2.6, hi))
        S.solid(f"Alcove_Side", (a + 0.6, 0.0, lo), (a + 0.8, 2.6, hi))
        S.solid(f"Alcove_Ceiling", (a - 0.8, 2.4, lo), (a + 0.8, 2.6, hi), "ceiling", ("ceiling",))
        hid += 1
        if kind == "closet":
            if side == "N":
                S.door(f"closet_{hid}", (a - 0.4, 0.0, -CORR_Z), (1, 0), (0, -1), width=0.8, props={"kind": "closet"})
            else:
                S.door(f"closet_{hid}", (a + 0.4, 0.0, CORR_Z), (-1, 0), (0, 1), width=0.8, props={"kind": "closet"})
        S.spot("hide", hid, (a, 0.0, sgn * (CORR_Z + T + 0.5)), face=(0, -sgn), props={"where": kind})
        S.label(kind, a, sgn * (CORR_Z + T + 1.6), kind="note")
    # doors to other scenes off the corridor
    for did, side, a, to in extra_doors:
        sgn = -1 if side == "N" else 1
        if side == "N":
            S.door(did, (a - DOOR_W / 2, 0.0, -CORR_Z - T), (1, 0), (0, -1))
        else:
            S.door(did, (a + DOOR_W / 2, 0.0, CORR_Z + T), (-1, 0), (0, 1))
        S.link(did, (a, 0.0, sgn * 0.5), (a, 0.0, 0.0), (0, -sgn), to)
    # the west end: the elevator (a placeholder car behind a lift door) or a blank wall
    if lift:
        lid, lto = lift
        shell(S, "LiftCar", -22.4, -20.2, -1.1, 1.1, 0.0, 2.4, ceiling=True, sides="NSW", wmat="lift", fmat="lift")
        S.label("lift car (placeholder)", -21.3, 1.8, kind="note")
        S.door(lid, (-CORR_X, 0.0, -0.6), (0, 1), (1, 0), width=1.2, height=2.2, props={"kind": "elevator"})
        S.link(lid, (-19.4, 0.0, 0.0), (-18.8, 0.0, 0.0), (1, 0), lto)
        S.marker("Spawn", (-18.8, 0.0, 0.0))
        S.still = ((-18.8, 0.0, 0.0), (1.0, 0.0), -2)
    # the east end
    way, eid, eto = east
    if way == "up":
        sx0, sx1 = CORR_X + T, 26.6
        S.door("stairwell", (CORR_X, 0.0, -DOOR_W / 2), (0, 1), (1, 0))
        S.solid("Stairwell_Floor", (CORR_X, -SLAB, -1.2), (sx1 + T, 0.0, 1.2), fmat)
        S.solid("Stairwell_Ceiling", (CORR_X, 6.0, -1.2), (sx1 + T, 6.2, 1.2), "ceiling", ("ceiling",))
        S.solid("Stairwell_Wall_N", (CORR_X, 0.0, -1.2), (sx1 + T, 6.0, -1.0))
        S.solid("Stairwell_Wall_S", (CORR_X, 0.0, 1.0), (sx1 + T, 6.0, 1.2))
        S.solid("Stairwell_Wall_W_up", (CORR_X, CORR_H, -1.0), (sx0, 6.0, 1.0))
        wall(S, "Stairwell_Wall_E", "z", sx1, sx1 + T, -1.0, 1.0, 0.0, 6.0, [(-DOOR_W / 2, DOOR_W / 2, 3.2, 3.2 + DOOR_H)])
        flight(S, f"{sid}_up", -1.0, 1.0, 21.4, +1, "x", 0.0, 3.2, 13, 0.28)
        land0 = 21.4 + 13 * 0.28
        S.solid("Landing_Top", (land0, 2.9, -1.0), (sx1, 3.2, 1.0), "stair")
        S.door(eid, (sx1, 3.2, -DOOR_W / 2), (0, 1), (-1, 0))
        S.link(eid, (26.0, 3.2, 0.0), (25.5, 3.2, 0.0), (-1, 0), eto)
        S.label("stairwell", 23.0, 0.0)
        S.light(23.5, 5.6, 0.0, 120)
        if not lift:
            S.marker("Spawn", (25.5, 3.2, 0.0))
    else:
        S.door(eid, (CORR_X, 0.0, -DOOR_W / 2), (0, 1), (1, 0), props={"kind": "stair door"})
        S.link(eid, (19.4, 0.0, 0.0), (18.8, 0.0, 0.0), (-1, 0), eto)
        shell(S, "StairLanding", CORR_X + T, 21.6, -1.0, 1.0, 0.0, CORR_H, sides="NSE", fmat=fmat)     # the top landing behind the door
        S.label("top landing", 20.9, 1.8, kind="note")
        if not lift:
            S.marker("Spawn", (18.8, 0.0, 0.0))
            S.still = ((18.8, 0.0, 0.0), (-1.0, 0.0), -2)
    return S


def floor_rooms(start, layouts):
    return [(start + i, layouts[i % len(layouts)]) for i in range(10)]


# ---------------------------------------------------------------- the lobby
def lobby():
    S = Scene("lobby", "Lobby", "20 m by 22 m, 6 m high (the tower's footprint on the street: x -28 to -8, z -30 to -8)", mood="peaceful")
    x0, x1, z0, z1, h = -27.8, -8.2, -29.8, -8.2, 6.0
    shell(S, "Lobby", x0, x1, z0, z1, 0.0, h, holes={"E": [(-19.0, 1.8, 2.5)], "W": [(-12.0, DOOR_W, DOOR_H)]}, fmat="marble")
    # the front doors (the street's tower door is at x -8, z -19; DOOR_W 1.8, DOOR_H 2.5 in shared/city.js)
    S.door("front_A", (x1, 0.0, -19.9), (0, 1), (-1, 0), width=0.9, height=2.5, props={"kind": "front door"})
    S.door("front_B", (x1, 0.0, -18.1), (0, -1), (-1, 0), width=0.9, height=2.5, props={"kind": "front door"})
    S.link("street", (-8.9, 0.0, -19.0), (-9.6, 0.0, -19.0), (-1, 0), "city.street (the tower door)")
    S.marker("Spawn", (-9.6, 0.0, -19.0))
    S.still = ((-9.6, 0.0, -19.0), (-1.0, 0.05), 4)
    # the back door past the deli, to the narrow hall and the atrium (the manifest's hotel.lobby>atrium leaves by `back_hall`)
    S.door("back_hall", (x0, 0.0, -12.47), (0, 1), (1, 0))
    S.link("back_hall", (-27.1, 0.0, -12.0), (-26.5, 0.0, -12.0), (1, 0), "atrium (narrow hall)")
    # the loft over the deli, its stairs and rails, the posts under its edge
    S.solid("Loft_Slab", (x0, 2.75, -22.0), (-21.0, 3.0, z1), "floor")
    flight(S, "loft", -24.4, -23.2, -25.9, +1, "z", 0.0, 3.0, 12, 0.325)
    S.solid("Loft_Rail_N", (x0, 3.0, -22.0), (-24.4, 4.0, -21.9), "rail")
    S.solid("Loft_Rail_N", (-23.2, 3.0, -22.0), (-21.0, 4.0, -21.9), "rail")
    S.solid("Loft_Rail_E", (-21.1, 3.0, -21.9), (-21.0, 4.0, z1), "rail")
    for zc in (-21.7, -15.0, -8.6):
        S.solid("Loft_Post", (-21.4, 0.0, zc - 0.2), (-21.0, 2.75, zc + 0.2), "column")
    S.outlines.append({"x0": x0, "x1": -21.0, "z0": -22.0, "z1": z1, "text": "loft over the deli (y 3)"})
    # the deli under the loft
    box(S, "Deli_Counter", -25.0, -24.4, -20.5, -14.0, 0, 1.0, "counter")
    box(S, "Deli_Table", -23.4, -22.6, -19.4, -18.6, 0, 0.75)
    box(S, "Deli_Table", -23.4, -22.6, -16.4, -15.6, 0, 0.75)
    S.spot("shop", 3, (-26.2, 0.0, -17.2), face=(1, 0), props={"what": "deli"})
    S.label("deli", -23.0, -17.5)
    # reception on the north side, with the key board behind it
    box(S, "Reception_Desk", -19.0, -15.0, -26.0, -25.4, 0, 1.1, "counter")
    S.solid("Key_Board", (-19.0, 0.0, z0), (-15.0, 2.2, -29.4), "furniture")
    S.spot("npc", 1, (-17.0, 0.0, -27.6), face=(0, 1), props={"what": "receptionist"})
    S.label("reception", -17.0, -24.6)
    # two shops on the south side
    S.solid("Shop_Partition", (-17.2, 0.0, -11.7), (-17.0, 3.0, z1))
    S.solid("Shop_Partition", (-13.1, 0.0, -11.7), (-12.9, 3.0, z1))
    box(S, "Shop_A_Counter", -16.6, -13.6, -11.7, -11.2, 0, 1.0, "counter")
    box(S, "Shop_B_Counter", -12.5, -9.0, -11.7, -11.2, 0, 1.0, "counter")
    S.spot("shop", 1, (-15.1, 0.0, -10.0), face=(0, -1))
    S.spot("shop", 2, (-10.75, 0.0, -10.0), face=(0, -1))
    S.label("shop 1", -15.1, -9.2)
    S.label("shop 2", -10.75, -9.2)
    # facade doors that do not open: places for later features
    for k, xc in enumerate((-26.5, -12.0, -10.0), 1):
        S.solid("Facade_Door", (xc - 0.5, 0.0, z0), (xc + 0.5, 2.2, z0 + 0.06), "fake_door")
        S.spot("facade", k, (xc, 0.0, -29.0), face=(0, -1), props={"what": "facade door that does not open: a place for a later feature"})
    # the middle of the hall: a planter and two sofas by the front
    box(S, "Planter", -16.0, -14.0, -20.0, -18.0, 0, 0.8, "safe")
    box(S, "Sofa", -12.0, -10.0, -16.0, -15.2, 0, 0.8)
    box(S, "Sofa", -12.0, -10.0, -22.8, -22.0, 0, 0.8)
    S.spot("puzzle", 1, (-15.0, 0.0, -17.2), face=(0, -1))
    S.spot("puzzle", 2, (-9.4, 0.0, -27.0), face=(-1, 0))
    S.spot("dealer", 1, (-20.0, 0.0, -23.5), face=(1, 0))
    S.spot("dealer", 2, (-9.4, 0.0, -14.0), face=(-1, 0))
    S.spot("dealer", 3, (-23.0, 3.0, -10.5), face=(1, 0), props={"where": "on the loft"})
    S.label("LOBBY", -15.0, -21.5)
    for x, z in ((-12, -13), (-12, -25), (-18, -13), (-18, -25)):
        S.light(x, 5.6, z, 500)
    for x, z in ((-24.5, -12), (-24.5, -19), (-25, -26)):
        S.light(x, 2.5, z, 120)
    return S


# ---------------------------------------------------------------- the atrium
ATR = 18.0
GAL = 4.0
LEVELS = (0.0, 4.0, 8.0, 12.0)
LEVEL_NAME = {0.0: "sub floor", 4.0: "floor 1", 8.0: "floor 2", 12.0: "floor 3"}
ATR_H = 16.0


def atrium():
    S = Scene("atrium", "Atrium", "36 m by 36 m, 16 m high, four galleries at y 0, 4, 8 and 12, the narrow hall from the lobby 10 m by 1.6 m",
              levels=LEVELS, mood="the hub")
    a = ATR
    pools_n = [(-12, 1), (-6, 2), (6, 3), (12, 4)]           # north wall: x, pool
    pools_w = [(-12, 5), (-6, 6), (6, 7), (12, 8)]           # west wall: z, pool
    pools_s = [(-6, 9), (0, 10), (6, 11)]                    # south wall: x, pool
    holes = {"N": [(x, DOOR_W, DOOR_H) for x, _ in pools_n], "W": [(z, DOOR_W, DOOR_H) for z, _ in pools_w] + [(0.0, DOOR_W, DOOR_H)],
             "S": [(x, DOOR_W, DOOR_H) for x, _ in pools_s], "E": [(0.0, 1.6, 2.6), (-12.0, DOOR_W, DOOR_H)]}
    for y in LEVELS:
        holes["S"] += [(-12.0, DOOR_W, DOOR_H, y), (12.0, DOOR_W, DOOR_H, y)]
    shell(S, "Atrium", -a, a, -a, a, 0.0, ATR_H, holes, fmat="marble")
    for x, k in pools_n:
        did = f"pool_{k:02d}"
        S.door(did, (x - DOOR_W / 2, 0.0, -a), (1, 0), (0, 1))
        S.link(did, (x, 0.0, -a + 0.7), (x, 0.0, -a + 1.4), (0, 1), f"sub_pool_{k:02d}")
    for z, k in pools_w:
        did = f"pool_{k:02d}"
        S.door(did, (-a, 0.0, z - DOOR_W / 2), (0, 1), (1, 0))
        S.link(did, (-a + 0.7, 0.0, z), (-a + 1.4, 0.0, z), (1, 0), f"sub_pool_{k:02d}")
    for x, k in pools_s:
        did = f"pool_{k:02d}"
        S.door(did, (x + DOOR_W / 2, 0.0, a), (-1, 0), (0, -1))
        S.link(did, (x, 0.0, a - 0.7), (x, 0.0, a - 1.4), (0, -1), f"sub_pool_{k:02d}")
    # the maze: a one-way door in (west wall, middle) and the door you come out of after solving it (east wall)
    S.door("maze", (-a, 0.0, -DOOR_W / 2), (0, 1), (1, 0), props={"one_way": "in: opens from the atrium only"})
    S.link("maze", (-a + 0.7, 0.0, 0.0), (-a + 1.4, 0.0, 0.0), (1, 0), "maze_01 (one way)")
    S.door("maze_exit", (a, 0.0, -12.0 - DOOR_W / 2), (0, 1), (-1, 0), props={"one_way": "out: opens from the maze only"})
    S.link("maze_exit", (a - 0.7, 0.0, -12.0), (a - 1.4, 0.0, -12.0), (-1, 0), "out of maze_07")
    # the escalators and the other staircase: doors on the south wall at every gallery
    for y in LEVELS:
        L = f"L{int(y)}"
        S.door(f"stairs_{L}", (-12.0 + DOOR_W / 2, y, a), (-1, 0), (0, -1))
        S.link(f"stairs_{L}", (-12.0, y, a - 0.7), (-12.0, y, a - 1.4), (0, -1), f"other_stairs ({LEVEL_NAME[y]})")
        S.door(f"escalators_{L}", (12.0 + DOOR_W / 2, y, a), (-1, 0), (0, -1))
        S.link(f"escalators_{L}", (12.0, y, a - 0.7), (12.0, y, a - 1.4), (0, -1), f"escalators ({LEVEL_NAME[y]})")
    # the galleries (y 4, 8, 12), 4 m deep on every side, with a rail on the edge of the void
    g = a - GAL
    for y in LEVELS[1:]:
        L = int(y)
        S.solid(f"Gallery_{L}_N", (-a, y - SLAB, -a), (a, y, -g), "floor")
        S.solid(f"Gallery_{L}_S", (-a, y - SLAB, g), (a, y, a), "floor")
        S.solid(f"Gallery_{L}_W", (-a, y - SLAB, -g), (-g, y, g), "floor")
        S.solid(f"Gallery_{L}_E", (g, y - SLAB, -g), (a, y, g), "floor")
        S.solid(f"Rail_{L}_N", (-g, y, -g - 0.1), (-1.3, y + 1.0, -g), "rail")
        S.solid(f"Rail_{L}_N", (1.3, y, -g - 0.1), (g, y + 1.0, -g), "rail")
        S.solid(f"Rail_{L}_S", (-g, y, g), (g, y + 1.0, g + 0.1), "rail")
        S.solid(f"Rail_{L}_W", (-g - 0.1, y, -g), (-g, y + 1.0, g), "rail")
        S.solid(f"Rail_{L}_E", (g, y, -g), (g + 0.1, y + 1.0, g), "rail")
        e, r = 0.01, g + 0.11                                  # the gallery's clear floor: the wall face to the rail
        S.corridor(f"gallery_{L}_N", -a + e, a - e, -a + e, -r, y)
        S.corridor(f"gallery_{L}_S", -a + e, a - e, r, a - e, y)
        S.corridor(f"gallery_{L}_W", -a + e, -r, -g + e, g - e, y)
        S.corridor(f"gallery_{L}_E", r, a - e, -g + e, g - e, y)
    for sx in (-1, 1):                                         # four columns in the void's corners, inside the rails
        for sz in (-1, 1):
            cx0, cz0 = (g - 0.6, g - 0.6)
            S.solid("Column", (min(sx * g, sx * cx0), 0.0, min(sz * g, sz * cz0)), (max(sx * g, sx * cx0), ATR_H, max(sz * g, sz * cz0)), "column")
    # the elevator shaft through all four galleries, its doors on the north side at every level; a placeholder car at the bottom
    sz0, sz1 = -g, -g + 2.6
    wall(S, "Shaft_N", "x", sz0, sz0 + 0.2, -1.3, 1.3, 0.0, ATR_H, [(-0.6, 0.6, y, y + 2.2) for y in LEVELS], "lift")
    S.solid("Shaft_W", (-1.3, 0.0, sz0 + 0.2), (-1.1, ATR_H, sz1), "lift")
    S.solid("Shaft_E", (1.1, 0.0, sz0 + 0.2), (1.3, ATR_H, sz1), "lift")
    S.solid("Shaft_S", (-1.1, 0.0, sz1 - 0.2), (1.1, ATR_H, sz1), "lift")
    S.solid("Lift_Car", (-1.05, 0.0, sz0 + 0.25), (1.05, 2.4, sz1 - 0.25), "lift")
    for y in LEVELS:
        L = f"L{int(y)}"
        S.door(f"lift_{L}", (-0.6, y, sz0), (1, 0), (0, -1), width=1.2, height=2.2, props={"kind": "elevator", "stop": LEVEL_NAME[y]})
        S.link(f"lift_{L}", (0.0, y, sz0 - 0.6), (0.0, y, sz0 - 1.3), (0, -1),
               {0.0: "the elevator's ground stop", 4.0: "floor_1_lower", 8.0: "floor_2_lower", 12.0: "floor_3"}[y])
        S.label(f"{LEVEL_NAME[y]} gallery (y {int(y)})", -a + 6.5 if not y else -a + 2.0, 8.0 if not y else -2.0, y, kind="room" if y else "note")
    # the narrow hall from the lobby's back door, east of the atrium
    hx0, hx1 = a + T, 28.0
    S.solid("Hall_Floor", (a, -SLAB, -1.0), (hx1 + T, 0.0, 1.0), "marble")
    S.solid("Hall_Ceiling", (a, 2.8, -1.0), (hx1 + T, 3.0, 1.0), "ceiling", ("ceiling",))
    S.solid("Hall_Wall_N", (hx0, 0.0, -1.0), (hx1 + T, 2.8, -0.8))
    S.solid("Hall_Wall_S", (hx0, 0.0, 0.8), (hx1 + T, 2.8, 1.0))
    wall(S, "Hall_Wall_E", "z", hx1, hx1 + T, -0.8, 0.8, 0.0, 2.8, [(-DOOR_W / 2, DOOR_W / 2, 0.0, DOOR_H)])
    S.door("lobby", (hx1, 0.0, -DOOR_W / 2), (0, 1), (-1, 0))
    S.link("lobby", (27.3, 0.0, 0.0), (26.6, 0.0, 0.0), (-1, 0), "lobby (back door)")
    S.corridor("narrow_hall", hx0, hx1, -0.8, 0.8)
    S.label("narrow hall", 23.0, -1.6, kind="note")
    S.marker("Spawn", (26.6, 0.0, 0.0))
    box(S, "Planter", -2.0, 2.0, -2.0, 2.0, 0, 0.6, "safe")
    S.label("ATRIUM floor (sub floor)", 0.0, 4.0)
    S.still = ((15.0, 0.0, 12.0), (-0.75, -0.66), 16)
    for x in (-10, 0, 10):
        for z in (-10, 0, 10):
            S.light(x, 15.4, z, 1500)
    for y in LEVELS:
        for x, z in ((-16, -16), (16, -16), (-16, 16), (16, 16), (0, 16), (-16, 0), (16, 0), (0, -16)):
            S.light(x, y + 3.2, z, 150)
    S.light(23.0, 2.5, 0.0, 80)
    return S


# ---------------------------------------------------------------- the key rooms off floor 2
def key_room(sid, title, what):
    S = Scene(sid, title, "14 m by 10 m, 3 m high", mood="the neighbour's floor")
    shell(S, title.split(" ")[0], -7.0, 7.0, -5.0, 5.0, 0.0, 3.0, holes={"S": [(0.0, DOOR_W, DOOR_H)]}, fmat="carpet_green")
    S.door("floor_2", (DOOR_W / 2, 0.0, 5.0), (-1, 0), (0, -1))
    S.link("floor_2", (0.0, 0.0, 4.4), (0.0, 0.0, 3.8), (0, -1), "floor_2 corridor")
    S.marker("Spawn", (0.0, 0.0, 3.8))
    S.still = ((0.0, 0.0, 3.8), (0.0, -1.0), -4)
    if what == "dining":
        for tx in (-4.0, 0.0, 4.0):
            for tz in (-1.5, 1.5):
                box(S, "Table", tx - 0.6, tx + 0.6, tz - 0.6, tz + 0.6, 0, 0.75)
                for cx in (tx - 0.95, tx + 0.95):
                    box(S, "Chair", cx - 0.225, cx + 0.225, tz - 0.225, tz + 0.225, 0, 0.9)
        box(S, "Buffet", -5.0, 5.0, -5.0, -4.2, 0, 0.9, "counter")
        S.spot("hide", 1, (-6.3, 0.0, -4.4))
        S.spot("clue", 1, (5.8, 0.0, 3.8), face=(1, 0))
        S.label("DINING ROOM", 0.0, 0.0)
        S.label("buffet", 0.0, -3.6)
    elif what == "reception":
        box(S, "Front_Desk", -3.0, 3.0, -1.0, -0.4, 0, 1.1, "counter")
        S.solid("Key_Cubbies", (-4.0, 0.0, -5.0), (4.0, 2.4, -4.6), "furniture")
        box(S, "Sofa", -6.5, -4.5, 2.5, 3.3, 0, 0.8)
        box(S, "Sofa", 4.5, 6.5, 2.5, 3.3, 0, 0.8)
        S.spot("npc", 1, (0.0, 0.0, -2.5), face=(0, 1), props={"what": "the night clerk"})
        S.spot("clue", 1, (6.2, 0.0, -4.2), face=(1, 0))
        S.spot("hide", 1, (-6.3, 0.0, -4.3))
        S.label("RECEPTION", 0.0, 1.5)
        S.label("key cubbies", 0.0, -4.0)
    else:
        box(S, "Table", -1.5, 1.5, -1.0, 1.0, 0, 0.9)
        S.solid("Key_Hooks", (-4.0, 1.0, -5.0), (4.0, 2.2, -4.9), "fake_door")
        box(S, "Safe", 5.4, 6.6, -4.6, -3.6, 0, 1.2, "lift")
        S.spot("puzzle", 1, (0.0, 0.0, -2.2), face=(0, -1))
        S.spot("key", 1, (0.0, 0.0, 1.8), face=(0, -1))
        S.label("KEY ROOM", 0.0, 2.6)
        S.label("key hooks", 0.0, -4.3)
        S.label("safe", 6.0, -3.0)
    for x in (-4, 0, 4):
        S.light(x, 2.7, 0, 150)
    return S


# ---------------------------------------------------------------- connector-kit pieces in a scene's layout (blender/kit/README.md)
# The dressed scenes place the kit with tools/blender/kit_place.py, which appends the piece's layout objects moved, turned and given `_<suffix>`.
# kit_layout() writes the same records into this model from the piece's own layout file (world/kit/<piece>.json), so `--preview` gives the
# file the dressed scene exports. `doors` renames a kit door to the scene's door id (the scene's link keeps its id); `cols` picks the colliders.
def kit_point(at, yaw_deg, p):
    """A kit point (x, y, z) in the scene, for the piece placed at `at`, turned by `yaw_deg` (three.js rotation.y)."""
    a = math.radians(yaw_deg)
    c, s = round(math.cos(a), 12), round(math.sin(a), 12)
    return (at[0] + p[0] * c + p[2] * s, at[1] + p[1], at[2] - p[0] * s + p[2] * c)


def kit_face(yaw_deg, f):
    a = math.radians(yaw_deg)
    c, s = round(math.cos(a), 12), round(math.sin(a), 12)
    return (f[0] * c + f[1] * s, -f[0] * s + f[1] * c)


def kit_layout(S, piece, suffix, at, yaw_deg, cols=lambda n: True, doors=None, spots=True, zones=True, markers=True, mat="wall"):
    kit = json.loads((ROOT / f"world/kit/{piece}.json").read_text())
    for c in kit["colliders"]:
        if cols(c["s"]):
            p, q = kit_point(at, yaw_deg, c["min"]), kit_point(at, yaw_deg, c["max"])
            S.solid(f"{c['s']}_{suffix}", [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)], mat)
    for d in kit["doors"]:
        if doors is None or d["name"][len("DoorLeaf_"):] not in doors:
            continue
        yaw = (d["closed_yaw_deg"] + yaw_deg + 180.0) % 360.0 - 180.0
        pr = {"width": d["width"], "height": d["height"], "closed_yaw_deg": round(yaw, 1), "swing_deg": d["swing_deg"], "state": d["state"]}
        pr.update({k: v for k, v in d.items() if k not in pr and k not in ("name", "level", "hinge")})
        S.doors.append({"name": S.uniq("DoorLeaf_" + doors[d["name"][len("DoorLeaf_"):]]), "hinge": [float(v) for v in kit_point(at, yaw_deg, d["hinge"])],
                        "yaw": math.radians(yaw), "props": pr})
    for sp in kit["spots"] if spots else []:
        extra = {k: v for k, v in sp.items() if k not in ("kind", "name", "position", "face", "yaw_deg", "scale")}
        S.empty(f"{sp['name']}_{suffix}", kit_point(at, yaw_deg, sp["position"]), face=kit_face(yaw_deg, sp["face"]), props=extra)
    for z in kit["zones"] if zones else []:
        p, q = kit_point(at, yaw_deg, z["min"]), kit_point(at, yaw_deg, z["max"])
        S.zone(z["kind"], f"{z['name'][len('Zone_' + z['kind'] + '_'):]}_{suffix}", [min(p[i], q[i]) for i in range(3)], [max(p[i], q[i]) for i in range(3)])
    for m in kit["markers"] if markers else []:
        S.marker(f"{m['name']}_{suffix}", kit_point(at, yaw_deg, m["position"]), m["kind"])


# ---------------------------------------------------------------- the roof
def roof():
    S = Scene("roof", "Roof", "24 m by 24 m, open sky", mood="peaceful")
    S.sky = (0.015, 0.02, 0.05)
    a = 12.0
    S.solid("Roof_Floor", (-a - 0.3, -SLAB, -a - 0.3), (a + 0.3, 0.0, a + 0.3), "roof")
    S.solid("Parapet_N", (-a - 0.3, 0.0, -a - 0.3), (a + 0.3, 1.1, -a), "parapet")
    S.solid("Parapet_S", (-a - 0.3, 0.0, a), (a + 0.3, 1.1, a + 0.3), "parapet")
    S.solid("Parapet_W", (-a - 0.3, 0.0, -a), (-a, 1.1, a), "parapet")
    S.solid("Parapet_E", (a, 0.0, -a), (a + 0.3, 1.1, a), "parapet")
    S.solid("Stair_Bulkhead", (6.0, 0.0, 6.0), (10.0, 2.8, 10.0), "wall")
    S.door("floor_3", (6.0, 0.0, 8.0 - DOOR_W / 2), (0, 1), (-1, 0))
    S.link("floor_3", (5.4, 0.0, 8.0), (4.8, 0.0, 8.0), (-1, 0), "floor_3 (stairs down)")
    S.marker("Spawn", (4.8, 0.0, 8.0))
    S.label("stair bulkhead", 8.0, 10.8, kind="note")
    # the safe house (from the kit later): shop, stash, save, crafting, respawn, locker
    shell(S, "SafeHouse", -11.0, -5.0, -11.0, -6.0, 0.0, 2.8, holes={"S": [(-8.0, 1.0, DOOR_H)]}, fmat="carpet_tan", wmat="safe")
    box(S, "SH_Counter", -10.8, -9.0, -10.8, -10.2, 0, 1.0, "counter")
    box(S, "SH_Stash", -6.0, -5.2, -10.8, -10.0, 0, 1.0)
    box(S, "SH_Bench", -5.8, -5.2, -8.6, -7.0, 0, 0.9)
    box(S, "SH_Locker", -10.8, -10.3, -7.4, -6.6, 0, 2.0, "lift")
    S.decor("Respawn_Pad", (-8.6, 0.0, -9.2), (-7.4, 0.04, -8.0), "pad")
    S.zone("safe", "safe_house", (-11.0, 0.0, -11.0), (-5.0, 2.8, -6.0))
    S.spot("shop", 1, (-9.9, 0.0, -9.5), face=(0, -1))
    S.spot("stash", 1, (-5.6, 0.0, -9.4), face=(0, -1))
    S.spot("save", 1, (-7.0, 0.0, -10.4), face=(0, -1))
    S.spot("craft", 1, (-6.3, 0.0, -7.8), face=(1, 0))
    S.spot("respawn", 1, (-8.0, 0.0, -8.6))
    S.spot("locker", 1, (-9.8, 0.0, -7.0), face=(-1, 0))
    S.label("safe house", -8.0, -5.2, kind="note")
    box(S, "HVAC", -3.0, 0.0, 4.0, 6.0, 0, 1.4, "column")
    box(S, "HVAC", 1.0, 3.0, -9.0, -7.0, 0, 1.2, "column")
    box(S, "Water_Tank", 8.0, 11.0, -11.0, -8.0, 0, 2.5, "column")
    S.spot("puzzle", 1, (0.0, 0.0, 0.0), face=(0, -1))
    S.label("ROOF (skyline backdrop all round)", 0.0, 2.0)
    S.still = ((4.8, 0.0, 8.0), (-0.8, -0.6), 3)
    S.light(-8.0, 2.5, -8.5, 100)
    S.light(7.0, 3.0, 7.0, 60)
    return S


# ---------------------------------------------------------------- the sub-floor pools
POOLS = {  # k: basin (x0, x1, z0, z1), shallow length, puzzle spot (x, z), room height
    1: ((-6, 6, -8, 4), 2.5, (-8.5, -8.5), 3.2), 2: ((-8, -1, -8, 5), 3.0, (6.0, -6.0), 4.0), 3: ((1, 8, -8, 5), 3.0, (-6.0, -6.0), 3.2),
    4: ((-7, 7, -6, 3), 2.0, (0.0, -8.5), 4.0), 5: ((-4, 4, -9, 6), 4.0, (-7.0, 0.0), 3.2), 6: ((-8, 8, -9, -1), 1.5, (0.0, 3.0), 4.0),
    7: ((-8, 3, -8, 6), 3.0, (6.5, 0.0), 3.2), 8: ((-3, 8, -9, 2), 2.5, (-7.0, -5.0), 4.0), 9: ((-9, 9, -9, 0), 2.0, (-6.0, 5.0), 3.2),
    10: ((-5, 5, -7, 7), 4.0, (-8.0, -8.0), 4.0), 11: ((-7, 7, -9, 5), 3.0, (8.0, 7.0), 3.2),
}
POOL_SHALLOW, POOL_DEEP = 1.2, 2.4


def pool(k):
    sid = f"sub_pool_{k:02d}"
    (bx0, bx1, bz0, bz1), shallow, (px, pz), h = POOLS[k]
    S = Scene(sid, f"Sub-floor pool {k}", f"20 m by 20 m, {h:g} m high, a {bx1 - bx0:g} m by {bz1 - bz0:g} m pool", mood="peaceful, flooded")
    a, base = 10.0, -POOL_DEEP - SLAB
    shell(S, "Pool", -a, a, -a, a, 0.0, h, holes={"S": [(0.0, DOOR_W, DOOR_H)]}, floor=False, fmat="tile", wmat="tile")
    # the deck round the basin: solid down to the basin's floor slab, so its sides are the basin's walls
    S.solid("Deck_N", (-a - T, base, -a - T), (a + T, 0.0, bz0), "tile")
    S.solid("Deck_S", (-a - T, base, bz1), (a + T, 0.0, a + T), "tile")
    S.solid("Deck_W", (-a - T, base, bz0), (bx0, 0.0, bz1), "tile")
    S.solid("Deck_E", (bx1, base, bz0), (a + T, 0.0, bz1), "tile")
    # in from the south end: four steps to the shallow floor, four more to the deep end
    zs = bz1 - 1.2
    zm = zs - shallow
    S.solid("Shallow_Floor", (bx0, base, zm), (bx1, -POOL_SHALLOW, zs), "tile")
    _down_flight(S, f"{sid}_in", bx0, bx1, bz1, 0.0, -POOL_SHALLOW, 5, 0.3, base)
    _down_flight(S, f"{sid}_deep", bx0, bx1, zm, -POOL_SHALLOW, -POOL_DEEP, 5, 0.3, base)
    zd = zm - 1.2
    S.solid("Deep_Floor", (bx0, base, bz0), (bx1, -POOL_DEEP, zd), "tile")
    S.zone("water", "pool", (bx0, -POOL_DEEP, bz0), (bx1, -0.1, bz1))
    S.decor("Water", (bx0, -0.12, bz0), (bx1, -0.1, bz1), "water")
    if k % 2:
        S.zone("water", "deck", (-a, 0.0, -a), (a, 0.12, a))
    # the underwater ways on, toward B1 (swimming is not in the game yet: these stay shut)
    if k > 1:
        S.decor("Grate_prev", (bx0 + 0.5, -POOL_DEEP, bz0 + 0.5), (bx0 + 1.5, -POOL_DEEP + 0.03, bz0 + 1.5), "grate")
        S.link("under_prev", (bx0 + 1.0, -POOL_DEEP, bz0 + 1.0), (bx0 + 1.0, -POOL_DEEP, bz0 + 1.7), (0, 1), f"sub_pool_{k - 1:02d} (underwater)")
    nxt = f"sub_pool_{k + 1:02d} (underwater)" if k < 11 else "lot.B1 (underwater, the long way)"
    S.decor("Grate_next", (bx1 - 1.5, -POOL_DEEP, bz0 + 0.5), (bx1 - 0.5, -POOL_DEEP + 0.03, bz0 + 1.5), "grate")
    S.link("under_next" if k < 11 else "under_b1", (bx1 - 1.0, -POOL_DEEP, bz0 + 1.0), (bx1 - 1.0, -POOL_DEEP, bz0 + 1.7), (0, 1), nxt)
    S.door("atrium", (DOOR_W / 2, 0.0, a), (-1, 0), (0, -1))
    S.link("atrium", (0.0, 0.0, a - 0.7), (0.0, 0.0, a - 1.3), (0, -1), "atrium (sub floor gallery)")
    S.marker("Spawn", (0.0, 0.0, a - 1.3))
    if k % 2 == 0:                                                        # the even pools have a grid of columns
        for cx in (-7.5, -2.5, 2.5, 7.5):
            for cz in (-7.5, -2.5, 2.5, 7.5):
                if bx0 - 0.9 < cx < bx1 + 0.9 and bz0 - 0.9 < cz < bz1 + 0.9:
                    continue
                if abs(cx) < 1.6 and cz > 5:
                    continue
                if math.hypot(cx - px, cz - pz) < 1.2:
                    continue
                S.solid("Column", (cx - 0.25, 0.0, cz - 0.25), (cx + 0.25, h, cz + 0.25), "tile")
    S.spot("puzzle", 1, (px, 0.0, pz), face=(0, -1))
    S.label(f"POOL {k}", (bx0 + bx1) / 2, (bz0 + bz1) / 2 + 1.0)
    S.label("shallow", (bx0 + bx1) / 2, (zm + zs) / 2, kind="note")
    S.label("deep", (bx0 + bx1) / 2, (bz0 + zd) / 2 - 0.5, kind="note")
    S.still = ((0.0, 0.0, a - 1.3), (0.0, -1.0), -8)
    for x in (-5, 5):
        for z in (-5, 5):
            S.light(x, h - 0.3, z, 300)
    return S


def _down_flight(S, name, lane0, lane1, start, y_top, y_bot, n, tread, base):
    """Steps going DOWN into the basin toward -z from `start` (the first step just below y_top); solid down to the basin's slab."""
    rise = (y_top - y_bot) / n
    assert rise <= MAX_RISE + 1e-9
    for i in range(n - 1):
        top = y_top - rise * (i + 1)
        S.solid(f"Step_{name}_{i:02d}", (lane0, base, start - (i + 1) * tread), (lane1, top, start - i * tread), "stair")
    S.flights.append({"name": name, "y_start": y_bot, "y_end": y_top, "n": n, "rise": round(rise, 4), "tread": tread, "down": True})


# ---------------------------------------------------------------- the atrium anomaly maze
MAZE_PHOTO = {1: "IMG_2988", 2: "IMG_2989", 3: "IMG_2990", 4: "IMG_2910", 5: "IMG_2986", 6: "IMG_3015", 7: "IMG_3036"}


def maze(k):
    sid = f"maze_{k:02d}"
    n = 8 if k % 2 else 7
    p = 16.0 / n
    S = Scene(sid, f"Anomaly maze {k} ({MAZE_PHOTO[k]}, a label only)", f"16 m by 16 m, 3 m high, {n} by {n} cells of {p:.2f} m", mood="hostile, one way")
    a, h = 8.0, 3.0
    rnd = random.Random(1000 + k)
    r_in, r_out = n // 2, (k * 3 + 1) % n
    # a perfect maze, carved from the entry cell; the odd ones have a room of 2 by 2 cells in the middle
    right = [[True] * n for _ in range(n)]      # wall on the east side of cell (i, j)
    down = [[True] * n for _ in range(n)]       # wall on the south side
    seen, stack = {(0, r_in)}, [(0, r_in)]
    while stack:
        i, j = stack[-1]
        nb = [(i + di, j + dj) for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)) if 0 <= i + di < n and 0 <= j + dj < n and (i + di, j + dj) not in seen]
        if not nb:
            stack.pop()
            continue
        ni, nj = rnd.choice(nb)
        if ni != i:
            right[min(i, ni)][j] = False
        else:
            down[i][min(j, nj)] = False
        seen.add((ni, nj))
        stack.append((ni, nj))
    room = k % 2 == 1
    if room:
        c = n // 2 - 1
        right[c][c] = right[c][c + 1] = down[c][c] = down[c + 1][c] = False
    S.solid("Maze_Floor", (-a - T, -SLAB, -a - T), (a + T, 0.0, a + T), "floor")
    S.solid("Maze_Ceiling", (-a - T, h, -a - T), (a + T, h + 0.2, a + T), "ceiling", ("ceiling",))
    zc_in, zc_out = -a + (r_in + 0.5) * p, -a + (r_out + 0.5) * p
    shell(S, "Maze", -a, a, -a, a, 0.0, h, holes={"W": [(zc_in, DOOR_W, DOOR_H)], "E": [(zc_out, DOOR_W, DOOR_H)]}, floor=False, ceiling=False)
    gx = lambda i: -a + i * p
    for j in range(n - 1):                      # walls between rows j and j + 1, merged into runs along x
        i = 0
        while i < n:
            if down[i][j]:
                i0 = i
                while i < n and down[i][j]:
                    i += 1
                S.solid("Maze_Wall", (max(-a, gx(i0) - 0.1), 0.0, gx(j + 1) - 0.1), (min(a, gx(i) + 0.1), h, gx(j + 1) + 0.1))
            else:
                i += 1
    for i in range(n - 1):                      # walls between columns i and i + 1, merged into runs along z
        j = 0
        while j < n:
            if right[i][j]:
                j0 = j
                while j < n and right[i][j]:
                    j += 1
                S.solid("Maze_Wall", (gx(i + 1) - 0.1, 0.0, max(-a, gx(j0) - 0.1)), (gx(i + 1) + 0.1, h, min(a, gx(j) + 0.1)))
            else:
                j += 1
    for i in range(n):
        for j in range(n):
            S.corridor(f"cell_{i}_{j}", gx(i) + 0.1, gx(i + 1) - 0.1, gx(j) + 0.1, gx(j + 1) - 0.1)
    S.door("entry", (-a, 0.0, zc_in - DOOR_W / 2), (0, 1), (1, 0), props={"one_way": "in: it does not open from this side"})
    S.link("entry", (-a + 0.6, 0.0, zc_in), (-a + 1.0, 0.0, zc_in), (1, 0), "from the atrium (or the elevator's glitch)" if k == 1 else f"from maze_{k - 1:02d}")
    S.door("way_on", (a, 0.0, zc_out - DOOR_W / 2), (0, 1), (-1, 0), props={"one_way": "out: opens when the puzzle is solved"})
    S.link("way_on", (a - 0.6, 0.0, zc_out), (a - 1.0, 0.0, zc_out), (-1, 0), f"maze_{k + 1:02d}" if k < 7 else "atrium (maze exit)")
    S.marker("Spawn", (-a + 1.0, 0.0, zc_in))
    if room:
        S.spot("puzzle", 1, (0.0, 0.0, 0.0), face=(0, -1))
        S.label("room", 0.0, 1.2, kind="note")
    else:
        S.spot("puzzle", 1, (gx(n - 2) + p / 2, 0.0, zc_out), face=(1, 0))
    S.label("ENTRY", -a + 1.6, zc_in - 0.7, kind="note")
    S.label("WAY ON", a - 1.8, zc_out - 0.7, kind="note")
    # the still looks down the first open passage from the entry cell
    look = (1.0, 0.0) if not right[0][r_in] else (0.25, 1.0) if r_in < n - 1 and not down[0][r_in] else (0.25, -1.0)
    S.still = ((-a + 0.5, 0.0, zc_in), look, -2)
    for x in (-4, 4):
        for z in (-4, 4):
            S.light(x, h - 0.3, z, 90)
    S.light(-a + 1.0, h - 0.4, zc_in, 40)
    return S


# ---------------------------------------------------------------- the escalators and the other staircase
def escalators():
    S = Scene("escalators", "Escalators", "6 m by 8.8 m, 15.2 m high: three escalator runs between the galleries", levels=(0.0,), mood="connector")
    x0, x1, z0, z1, h = -3.0, 3.0, -4.4, 4.4, 15.2
    holes = {"S": [(0.0, DOOR_W, DOOR_H, 0.0), (0.0, DOOR_W, DOOR_H, 8.0)], "N": [(0.0, DOOR_W, DOOR_H, 4.0), (0.0, DOOR_W, DOOR_H, 12.0)]}
    shell(S, "Escalators", x0, x1, z0, z1, 0.0, h, holes)
    S.solid("Landing_4", (x0, 3.7, z0), (x1, 4.0, -2.4), "floor")
    S.solid("Landing_8", (x0, 7.7, 2.4), (x1, 8.0, z1), "floor")
    S.solid("Landing_12", (x0, 11.7, z0), (x1, 12.0, -2.4), "floor")
    flight(S, "esc_0_4", -2.8, -1.6, 2.4, -1, "z", 0.0, 4.0, 16, 0.3)
    flight(S, "esc_4_8", -0.6, 0.6, -2.4, +1, "z", 4.0, 8.0, 16, 0.3)
    flight(S, "esc_8_12", 1.6, 2.8, 2.4, -1, "z", 8.0, 12.0, 16, 0.3)
    for y, zl, za, side, face in ((0.0, 3.8, 3.2, "S", (0, -1)), (4.0, -3.8, -3.2, "N", (0, 1)), (8.0, 3.8, 3.2, "S", (0, -1)), (12.0, -3.8, -3.2, "N", (0, 1))):
        L = f"L{int(y)}"
        if side == "S":
            S.door(f"atrium_{L}", (DOOR_W / 2, y, z1), (-1, 0), (0, -1))
        else:
            S.door(f"atrium_{L}", (-DOOR_W / 2, y, z0), (1, 0), (0, 1))
        S.link(f"atrium_{L}", (0.0, y, zl), (0.0, y, za), face, f"atrium ({LEVEL_NAME[y]} gallery)")
        S.light(0.0, y + 2.8, (zl + za) / 2, 120)
    S.marker("Spawn", (0.0, 0.0, 3.2))
    S.label("ESCALATORS (3 runs)", 0.0, 0.0)
    S.label("up to y 4", -2.2, -1.0, kind="note")
    S.label("y 4 to 8", 0.0, 1.0, kind="note")
    S.label("y 8 to 12", 2.2, -1.0, kind="note")
    S.still = ((0.0, 0.0, 3.2), (-0.35, -1.0), 22)
    return S


def other_stairs():
    S = Scene("other_stairs", "The other staircase", "5.2 m by 6 m, 15.2 m high: a switchback, two flights a level, a half landing between", mood="connector")
    x0, x1, z0, z1, h = -2.6, 2.6, -3.0, 3.0, 15.2
    shell(S, "Stairs", x0, x1, z0, z1, 0.0, h, holes={"S": [(0.0, DOOR_W, DOOR_H, y) for y in LEVELS]})
    S.solid("Spine", (-0.1, 0.0, -1.0), (0.1, h, 1.4), "wall")
    for k in range(3):
        y = 4.0 * k
        flight(S, f"st_{k}_a", x0, -0.1, 1.4, -1, "z", y, y + 2.0, 8, 0.3)
        S.solid(f"Half_Landing_{k}", (x0, y + 2.0 - SLAB, z0), (x1, y + 2.0, -1.0), "floor")
        flight(S, f"st_{k}_b", 0.1, x1, -1.0, +1, "z", y + 2.0, y + 4.0, 8, 0.3)
        S.solid(f"Landing_{int(y + 4)}", (x0, y + 4.0 - SLAB, 1.4), (x1, y + 4.0, z1), "floor")
    for y in LEVELS:
        L = f"L{int(y)}"
        S.door(f"atrium_{L}", (DOOR_W / 2, y, z1), (-1, 0), (0, -1))
        S.link(f"atrium_{L}", (0.0, y, 2.5), (0.0, y, 2.0), (0, -1), f"atrium ({LEVEL_NAME[y]} gallery)")
        S.light(0.0, y + 2.8, 2.2, 100)
        S.light(0.0, y + 4.6, -2.0, 60)
    S.marker("Spawn", (0.0, 0.0, 2.0))
    S.label("OTHER STAIRS", 0.0, -2.0)
    S.label("up", -1.35, 0.2, kind="note")
    S.label("up", 1.35, 0.2, kind="note")
    S.still = ((1.2, 0.0, 2.3), (-0.3, -1.0), 18)
    return S


# ---------------------------------------------------------------- the scenes and how they join
def _f1(sid):
    lower = sid.endswith("lower")
    feats = [("alcove", "N", -12.0), ("closet", "S", -4.0), ("alcove", "S", 12.0), ("closet", "N", 4.0)] if lower else \
            [("closet", "N", -12.0), ("alcove", "S", -4.0), ("alcove", "N", 12.0), ("closet", "S", 4.0)]
    rooms = floor_rooms(101 if lower else 111, ["motel_a", "motel_b"])
    if lower:
        S = corridor_floor(sid, "Floor 1, lower: the motel", rooms, "carpet_red", ("lift", "atrium (floor 1 gallery)"),
                           ("up", "stairs_up", "floor_1_upper"), feats, "the neighbour hunts")
    else:
        S = corridor_floor(sid, "Floor 1, upper: the motel", rooms, "carpet_red", None, ("down", "stairs_down", "floor_1_lower"), feats, "the neighbour hunts")
    # Dressed (tools/blender/build_hotel_floor1.py) with the connector kit (blender/kit/README.md), as tools/blender/kit_place.py places it, the
    # same way as _f3:
    # - lower: the elevator at (-20, 0, 0), yaw 90: the kit's car (parked here; the page moves it) and landing replace the LiftCar shell and the
    #   plain lift door; the door record keeps the id `lift` (the link's), the kit's own Link_/Arrive_/Marker_ are left out (the greybox's stay);
    # - the stair door at every stair door, yaw -90: lower `stairwell` (20, 0, 0) and `stairs_up` (26.6, 3.2, 0), upper `stairs_down` (20, 0, 0).
    #   The corridor, the top landing and the upper landing are the landings, so only the kit's door record is used (no `stair_door_landing`
    #   node, no colliders), and each opening widens from 0.94 m to the kit's 1.1 m. The door ids stay the greybox's, so every link still meets.
    drop = ("LiftCar_", "Corridor_Wall_E_", "Stairwell_Wall_E_")
    gone = {b["name"] for b in S.boxes if b["name"].startswith(drop)} | {"DoorLeaf_lift", "DoorLeaf_stairwell", "DoorLeaf_stairs_up", "DoorLeaf_stairs_down"}
    S.boxes = [b for b in S.boxes if b["name"] not in gone]
    S.doors = [d for d in S.doors if d["name"] not in gone]
    S._names -= gone
    S.labels = [lb for lb in S.labels if not lb["text"].startswith("lift car")]
    sw, sh = KIT_STAIR_W, DOOR_H
    x0, x1, sx1 = -CORR_X, CORR_X, 26.6
    wall(S, "Corridor_Wall_E", "z", x1, x1 + T, -CORR_Z, CORR_Z, 0.0, CORR_H, [(-sw / 2, sw / 2, 0.0, sh)])
    if lower:
        wall(S, "Stairwell_Wall_E", "z", sx1, sx1 + T, -1.0, 1.0, 0.0, 6.0, [(-sw / 2, sw / 2, 3.2, 3.2 + sh)])
        kit_layout(S, "elevator", "F1", (x0, 0.0, 0.0), 90.0, doors={"lift": "lift"}, zones=False, markers=False, mat="lift")
        kit_layout(S, "stair_door", "F1", (x1, 0.0, 0.0), -90.0, cols=lambda n: False, doors={"stair": "stairwell"}, spots=False, zones=False, markers=False)
        kit_layout(S, "stair_door", "F1_top", (sx1, 3.2, 0.0), -90.0, cols=lambda n: False, doors={"stair": "stairs_up"}, spots=False, zones=False, markers=False)
        S.label("elevator (kit)", -21.3, 1.8, kind="note")
        # the kit's call-button spot stands 0.22 m from the north wall here (the corridor is 2.2 m wide; the kit's landing was drawn for the
        # atrium's wider galleries), inside a walker's 0.28 m: it moves 8 cm toward the corridor's middle, still beside the button (as on floor 3)
        for e in S.empties:
            if e["name"] == "Spot_call_1_F1":
                e["pos"][2] = round(e["pos"][2] + 0.08, 3)
        # the kit landing's frame stands 6 cm proud of the west wall, so the clear corridor starts 8 cm in from it
        S.corridors[0]["min"][0] = x0 + 0.08
    else:
        kit_layout(S, "stair_door", "F1U", (x1, 0.0, 0.0), -90.0, cols=lambda n: False, doors={"stair": "stairs_down"}, spots=False, zones=False, markers=False)
    return S


KIT_STAIR_W = 1.1           # the connector kit's stair-door opening (blender/kit/README.md); the greybox's own doors are DOOR_W


def _f2(sid):
    lower = sid.endswith("lower")
    rooms = floor_rooms(201 if lower else 211, ["green_room"])
    if lower:
        feats = [("alcove", "S", -12.0), ("closet", "S", 4.0), ("alcove", "S", 12.0), ("closet", "N", -4.0)]
        extra = [("dining", "N", -12.0, "dining"), ("reception", "N", 12.0, "reception")]
        return corridor_floor(sid, "Floor 2, lower: green carpet", rooms, "carpet_green", ("lift", "atrium (floor 2 gallery)"),
                              ("up", "stairs_up", "floor_2_upper"), feats, "the neighbour hunts", extra)
    feats = [("closet", "N", -12.0), ("alcove", "N", 4.0), ("alcove", "N", 12.0), ("closet", "S", 12.0)]
    extra = [("key_room", "S", -12.0, "key_room")]
    return corridor_floor(sid, "Floor 2, upper: green carpet", rooms, "carpet_green", None, ("down", "stairs_down", "floor_2_lower"), feats,
                          "the neighbour hunts", extra)


def _f3(sid):
    rooms = floor_rooms(301, ["apartment"])
    return corridor_floor(sid, "Floor 3: the apartments", rooms, "carpet_tan", ("lift", "atrium (floor 3 gallery)"), ("up", "roof", "roof"),
                          [("alcove", "N", -5.5), ("alcove", "S", -2.5)], "peaceful")


SCENES = {
    "lobby": lobby, "atrium": atrium,
    "floor_1_lower": lambda: _f1("floor_1_lower"), "floor_1_upper": lambda: _f1("floor_1_upper"),
    "floor_2_lower": lambda: _f2("floor_2_lower"), "floor_2_upper": lambda: _f2("floor_2_upper"),
    "dining": lambda: key_room("dining", "Dining room (IMG_2903, a label only)", "dining"),
    "reception": lambda: key_room("reception", "Reception (IMG_2984, a label only)", "reception"),
    "key_room": lambda: key_room("key_room", "Key room (IMG_2985 and its PNG redesign, labels only)", "key"),
    "floor_3": lambda: _f3("floor_3"), "roof": roof,
    **{f"sub_pool_{k:02d}": (lambda k=k: pool(k)) for k in range(1, 12)},
    **{f"maze_{k:02d}": (lambda k=k: maze(k)) for k in range(1, 8)},
    "escalators": escalators, "other_stairs": other_stairs,
    **{lay: (lambda lay=lay: room_layout(lay)) for lay in ("motel_a", "motel_b", "green_room", "clue_room", "empty_room")},
}

# Every link between two hotel scenes: (scene, door) <-> (scene, door). Pressing F at one side's Link_ puts you on the other side's Arrive_.
PAIRS = [
    (("lobby", "back_hall"), ("atrium", "lobby"), "doors", "the back door past the deli, then the narrow hall (the manifest's hotel.lobby>atrium)"),
    (("atrium", "lift_L4"), ("floor_1_lower", "lift"), "elevator", "the elevator to floor 1 (hotel.atrium>floors)"),
    (("atrium", "lift_L8"), ("floor_2_lower", "lift"), "elevator", "the elevator to floor 2"),
    (("atrium", "lift_L12"), ("floor_3", "lift"), "elevator", "the elevator to floor 3"),
    (("floor_1_lower", "stairs_up"), ("floor_1_upper", "stairs_down"), "stairs", "hotel.floor_1_stairs"),
    (("floor_2_lower", "stairs_up"), ("floor_2_upper", "stairs_down"), "stairs", "floor 2's stairs"),
    (("floor_2_lower", "dining"), ("dining", "floor_2"), "doors", ""),
    (("floor_2_lower", "reception"), ("reception", "floor_2"), "doors", ""),
    (("floor_2_upper", "key_room"), ("key_room", "floor_2"), "doors", ""),
    (("floor_3", "roof"), ("roof", "floor_3"), "stairs", "stairs up to the roof"),
    (("atrium", "maze"), ("maze_01", "entry"), "one_way", "hotel.atrium>maze: one way in (and the elevator's glitch)"),
    *[((f"maze_{k:02d}", "way_on"), (f"maze_{k + 1:02d}", "entry"), "one_way", "one way, once solved") for k in range(1, 7)],
    (("maze_07", "way_on"), ("atrium", "maze_exit"), "one_way", "out of the maze, once solved"),
    *[(("atrium", f"pool_{k:02d}"), (f"sub_pool_{k:02d}", "atrium"), "doors", "the sub-floor gallery's pool doors") for k in range(1, 12)],
    *[((f"sub_pool_{k:02d}", "under_next"), (f"sub_pool_{k + 1:02d}", "under_prev"), "pool_route", "underwater; shut until swimming exists") for k in range(1, 11)],
    *[(("atrium", f"escalators_L{y}"), ("escalators", f"atrium_L{y}"), "escalator", "") for y in (0, 4, 8, 12)],
    *[(("atrium", f"stairs_L{y}"), ("other_stairs", f"atrium_L{y}"), "stairs", "") for y in (0, 4, 8, 12)],
]
# Links that leave the hotel or stay inside one scene: the other side is not a hotel greybox scene.
OUTSIDE = {
    ("lobby", "street"): "city.street, the tower's door (x -8, z -19): the street is built by code (shared/city.js); the manifest's city.street>hotel_lobby",
    ("sub_pool_11", "under_b1"): "lot.B1's pools, underwater, the long way (hotel.sub_pools>lot.B1); B1 is part 1's scene and is not touched",
    ("atrium", "lift_L0"): "the elevator's ground stop: the car moves between the atrium's four stops (code); no other scene",
}


def build(sid):
    return SCENES[sid]()


def plan_view(S, level=0.0, ppm_target=1700.0):
    """The plan's bounds (x0, x1, z0, z1) with a margin, and its pixel size: the Blender render and the sheets share this mapping."""
    xs = [v for b in S.boxes if b["col"] or b["name"].startswith("decor_") for v in (b["min"][0], b["max"][0])]
    zs = [v for b in S.boxes if b["col"] or b["name"].startswith("decor_") for v in (b["min"][2], b["max"][2])]
    m = 2.0
    x0, x1, z0, z1 = min(xs) - m, max(xs) + m, min(zs) - m, max(zs) + m
    span = max(x1 - x0, z1 - z0)
    ppm = ppm_target / span
    return {"x0": x0, "x1": x1, "z0": z0, "z1": z1, "W": int(round((x1 - x0) * ppm)), "H": int(round((z1 - z0) * ppm)), "ppm": ppm}


def plan_hidden(S, b, level):
    """Is box b left out of the plan for `level`? (ceilings, and anything that starts 2.4 m or more above the level, steps aside)"""
    if "ceiling" in b["tags"]:
        return True
    if S.steps_always and b["name"].startswith("Step_") and len(S.levels) == 1:
        return False
    return b["min"][1] >= level + 2.4


# ---------------------------------------------------------------- the layout file as the exporter writes it, from the model alone (--preview)
def _r(v):
    return round(v, 3) + 0.0


def doc_of(S):
    out = {"scene": S.id, "colliders": [], "doors": [], "cameras": [], "markers": [], "links": [], "zones": [], "spots": []}
    def face(f):
        if not f:
            return [0.0, 1.0]
        ln = math.hypot(*f) or 1.0
        return [_r(f[0] / ln), _r(f[1] / ln)]
    empt = {e["name"]: e for e in S.empties}
    items = sorted([("C", b["name"], b) for b in S.boxes] + [("E", e["name"], e) for e in S.empties] + [("D", d["name"], d) for d in S.doors], key=lambda t: t[1])
    cols = {b["name"] for b in S.boxes if b["col"]}
    for kind, n, o in sorted(items + [("K", "COL_" + b["name"], b) for b in S.boxes if b["col"]], key=lambda t: t[1]):
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
                out["links"].append({"door": n[5:], "at": [_r(v) for v in o["pos"]], "arrive": [_r(v) for v in a["pos"]], "face": face(a["face"])})
            elif n.startswith("Spot_"):
                f = face(o["face"])
                sp = {"kind": n.split("_")[1], "name": n, "position": [_r(v) for v in o["pos"]], "face": f,
                      "yaw_deg": round(math.degrees(math.atan2(f[0], f[1])), 1) + 0.0, "scale": float(o["props"].get("scale", 1.0))}
                for k, v in o["props"].items():
                    if k not in sp:
                        sp[k] = v
                out["spots"].append(sp)
    return out


def out_path(base, sid):
    return Path(base) / ("world/rooms" if SCENES and sid in ROOMS else "world") / f"{sid}.json"


# ---------------------------------------------------------------- the gates on exported files (--check)
def check(base, ids=None):
    """Links meet, steps keep to the rise, corridors are wide and clear. Reads <base>/world/...json; prints one line per gate; True if all pass."""
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
    print(f"GATE links: {len(PAIRS)} pairs, {len(PAIRS) * 2} sides, {len(OUTSIDE)} that leave the hotel or the scene; {len(have)} links in the files")
    # steps: every Step_<flight>_<nn> collider, in order, keeps to MAX_RISE, from the floor it starts on to the floor it reaches
    nsteps, worst = 0, 0.0
    for sid in ids:
        S = build(sid)
        cols = {c["s"]: c for c in docs.get(sid, {}).get("colliders", [])}
        for fl in S.flights:
            steps = sorted((n, c) for n, c in cols.items() if n.startswith(f"Step_{fl['name']}_"))
            tops = [c["max"][1] for _, c in steps]
            if fl.get("down"):
                seq = [fl["y_end"]] + tops + [fl["y_start"]]
            else:
                seq = [fl["y_start"]] + tops + ([fl["y_end"]] if not tops or abs(tops[-1] - fl["y_end"]) > 1e-6 else [])
            rises = [abs(seq[i + 1] - seq[i]) for i in range(len(seq) - 1)]
            nsteps += len(steps)
            worst = max([worst] + rises)
            if not steps or any(r > MAX_RISE + 1e-6 for r in rises):
                bad.append(f"steps {sid}/{fl['name']}: rises {rises}")
    print(f"GATE steps: {nsteps} step boxes, the highest rise {worst:.3f} m (at most {MAX_RISE} m)")
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
    print(f"GATE corridors: {ncor} corridor and passage rects, the narrowest {narrow:.2f} m (at least {MIN_CORRIDOR} m), none blocked")
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
    base = Path(a[a.index("--out") + 1]) if "--out" in a else ROOT / "work/hotel_greybox"
    render = "--no-render" not in a
    for sub in ("world/rooms", "glb", "renders"):
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
            bsdf.inputs["Roughness"].default_value = 0.8 if name != "water" else 0.15
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
            arts.append((boxobj(b["name"], b, "Art"), b))
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
        cy.max_bounces = 6
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
        if S.sky:
            world(S.sky, 1.0)
            add_light("SUN", (0, 0, 30), 0.6, "Moon", rot=(math.radians(50), 0, math.radians(30)))
        else:
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
    print("HOTEL_GREYBOX device", dev, "scenes", len(ids))
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
        print(f"HOTEL_GREYBOX done {sid}: {len(S.boxes)} boxes, {len(S.doors)} doors, {len(S.empties)} empties")
    print("HOTEL_GREYBOX ALL DONE")


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
        sys.exit(0 if check(Path(sys.argv[sys.argv.index("--check") + 1])) else 1)
    else:
        print(__doc__)
