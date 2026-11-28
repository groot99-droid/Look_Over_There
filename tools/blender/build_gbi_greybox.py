"""The Going back in greybox (docs/BLENDER_AREAS.md, section 6, "Going back in: 15 chambers and 5 safe houses"): the 15 new chambers as plain
boxes, to scale, with the names the exporter reads (COL_, DoorLeaf_, Marker_, Link_/Arrive_, Zone_, Spot_), the connector kit's pieces placed
from their own layout files (world/kit/<piece>.json), the five safe houses from the kit, and every hazard's moving part as its own object,
`Hazard_<kind>_<n>`, with the two ends of its travel as `Spot_hazard_<kind>_<n>_a` / `_b` and its `Zone_hazard_<kind>_<n>` box. It follows
the Overworld's greybox build (tools/blender/build_overworld_greybox.py) and the hotel's.

    blender -b --factory-startup --python tools/blender/build_gbi_greybox.py -- [--scenes all|id,id,...] [--out <dir>] [--no-render]
    python tools/blender/build_gbi_greybox.py --check <dir> [--glb <dir>]   the gates on exported files, no Blender (links both ways, one
                                                                           arrival and one way on, spots, monster distance, footprints,
                                                                           overlaps, door and corridor clearances, every spot reachable,
                                                                           hazards, steps; and, when both are there, the Blender export
                                                                           against the model)
    python tools/blender/build_gbi_greybox.py --preview <dir>             writes the layout files from the model alone, no Blender

For each chamber the Blender run builds the boxes into an empty file, writes <out>/world/<scene>.json through tools/blender/export_scene.py,
the greybox art to <out>/glb/<scene>.glb and one eye-height still (1.55 m, <out>/renders/<scene>_still.png). The plans, the floor panels, the
owner's sheet and the README are drawn afterwards by tools/blender/gbi_greybox_sheets.py from this same model (no Blender).

Coordinates are GAME coordinates (metres, y up, north = -z); Blender (x, y, z) is game (x, -z, y). Every chamber fills the store's footprint
(x -26.3 to 26.3, z -22.35 to 27.35, its outer walls 0.2 m inside that) at its floor's height: B1 -3, L1 0, L2 3.2, L3 6.4, L4 9.6
(docs/BLENDER_AREAS.md: "at its floor's height", not y 0).

The kit's pieces are placed as tools/blender/kit_place.py places them (a kit point (x, z) lands at (at.x + x cos yaw + z sin yaw,
at.z - x sin yaw + z cos yaw), every name given `_<suffix>`, a door's closed_yaw_deg turned with it), but from the pieces' exported layout files
rather than their .blend, so the same placement serves the Blender run, --preview and --check. Each kit collider gets a grey art twin here; in the
game the page draws world/kit/<piece>.glb at the same `at` and `yaw` (blender/kit/README.md, "How a scene links a piece", option 2). A piece's
links that make no sense inline are left out (the sky hall's `entry`, walked through; the stair door's `hall_far`); the kit's markers are left
out (each chamber has its own Marker_Arrival).

Materials are swappable on purpose (Secret Operations reskins these chambers): every box uses one of a few role materials, named after the
store's own per-floor set (M_D_floor_<F>, M_D_wall_<F>, M_D_ceil_<F>, M_D_trim, M_D_door, M_Water, M_Fluorescent) plus M_GBI_furn_<F>,
M_GBI_kit, M_GBI_vent and M_GBI_hazard_<kind>. A reskin replaces those materials by name. Nothing here touches the manifest, index.html or
shared/, and world/gbi_L4_4.json and world/gbi_L3_1.json (made from L4 and L3 by tools/make_chambers.mjs) are read, never written.
"""
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EYE = 1.55
T = 0.2                     # wall thickness
SLAB = 0.2                  # floor slab under every chamber (the store's floors are 0.2 m)
DOOR_W, DOOR_H = 0.94, 2.16
HOLE_W, HOLE_H = 1.0, 2.2
MAX_RISE = 0.27
MIN_CORRIDOR = 1.6
WALKER_R = 0.28
MONSTER_MIN = 16.0

FOOT = (-26.3, 26.3, -22.35, 27.35)                 # the store's footprint (x0, x1, z0, z1)
X0, X1, Z0, Z1 = -26.1, 26.1, -22.15, 27.15         # a chamber's inside, its outer walls 0.2 m thick inside the footprint
FLOORS = ["L4", "L3", "L2", "L1", "B1"]             # top down, the order of the run
FLOOR_Y = {"B1": -3.0, "L1": 0.0, "L2": 3.2, "L3": 6.4, "L4": 9.6}
CEIL_H = {"B1": 3.0, "L1": 2.8, "L2": 3.0, "L3": 3.2, "L4": 4.5}   # [MY CALL] 2.8 to 3.2 m (the rule); L4 keeps the store showroom's 4.5 m
LOOK = {"B1": "pools: white tile, flooded floors, columns", "L1": "offices: yellowed walls, carpet, cubicles and private offices",
        "L2": "L2's look: a loop of doors, narrow rooms, cardboard and desks", "L3": "white plaster: bright, empty, few walls",
        "L4": "showroom: white floor, display islands, gondolas and racking"}
HAZARD_KINDS = ["crush", "lava", "tide", "gas", "blade"]
HAZARD_NAMES = {"crush": "crushing walls", "lava": "floor is lava", "tide": "high tides", "gas": "toxic gas", "blade": "moving chainsaw blades"}
PUZZLE = {"B1": "a fuse to carry to the fuse box", "L1": "a pair of loud switches", "L2": "a code digit on a note",
          "L3": "a fuse box", "L4": "a power panel"}

# Flat greybox colours (linear RGB) for every material the chambers use. Role materials are per floor (see the docstring).
COLORS = {
    "M_D_floor_B1": (0.80, 0.84, 0.86), "M_D_wall_B1": (0.86, 0.90, 0.92), "M_D_ceil_B1": (0.70, 0.74, 0.76), "M_GBI_furn_B1": (0.55, 0.66, 0.72),
    "M_D_floor_L1": (0.46, 0.40, 0.24), "M_D_wall_L1": (0.78, 0.68, 0.34), "M_D_ceil_L1": (0.74, 0.72, 0.62), "M_GBI_furn_L1": (0.42, 0.40, 0.36),
    "M_D_floor_L2": (0.36, 0.34, 0.30), "M_D_wall_L2": (0.62, 0.58, 0.48), "M_D_ceil_L2": (0.60, 0.58, 0.54), "M_GBI_furn_L2": (0.58, 0.44, 0.28),
    "M_D_floor_L3": (0.86, 0.86, 0.84), "M_D_wall_L3": (0.95, 0.95, 0.93), "M_D_ceil_L3": (0.92, 0.92, 0.90), "M_GBI_furn_L3": (0.80, 0.80, 0.78),
    "M_D_floor_L4": (0.82, 0.82, 0.80), "M_D_wall_L4": (0.90, 0.90, 0.88), "M_D_ceil_L4": (0.85, 0.85, 0.84), "M_GBI_furn_L4": (0.95, 0.42, 0.05),
    "M_D_trim": (0.60, 0.62, 0.64), "M_D_door": (0.42, 0.30, 0.18), "M_Water": (0.20, 0.45, 0.70), "M_Fluorescent": (1.0, 0.97, 0.86),
    "M_GBI_kit": (0.48, 0.44, 0.52), "M_GBI_vent": (0.40, 0.42, 0.44),
    "M_GBI_hazard_crush": (0.55, 0.12, 0.10), "M_GBI_hazard_lava": (1.0, 0.30, 0.02), "M_GBI_hazard_tide": (0.10, 0.35, 0.65),
    "M_GBI_hazard_gas": (0.45, 0.80, 0.15), "M_GBI_hazard_blade": (0.75, 0.75, 0.80),
}
ROLES = ("floor", "wall", "ceil", "furn")
STILL_POWER = {"B1": 150.0, "L1": 260.0, "L2": 240.0, "L3": 110.0, "L4": 190.0}   # the stills' greybox lights (W per point light), white floors lower           # per-floor roles; the others are one material for every floor


def matname(floor, role):
    if role in ("floor", "wall", "ceil"):
        return f"M_D_{role}_{floor}"
    if role == "furn":
        return f"M_GBI_furn_{floor}"
    return {"trim": "M_D_trim", "door": "M_D_door", "water": "M_Water", "lamp": "M_Fluorescent", "kit": "M_GBI_kit", "vent": "M_GBI_vent"}.get(
        role, f"M_GBI_hazard_{role}" if role in HAZARD_KINDS else role)


def _r(v):
    return round(v, 3) + 0.0


# ================================================================ the model (pure Python; no bpy)
class Scene:
    def __init__(s, sid, floor, idx, title, mood):
        s.id, s.floor, s.idx, s.title, s.mood = sid, floor, idx, title, mood
        s.Y, s.H = FLOOR_Y[floor], CEIL_H[floor]
        s.boxes, s.empties, s.doors, s.labels, s.corridors, s.flights, s.kerbs, s.hazards = [], [], [], [], [], [], [], []
        s.kits = []             # [{piece, sfx, at, yaw, role}] for the plans and the README
        s.links = {}            # door id -> text (where it goes)
        s.arrival = None        # (door id or None, (x, y, z)); None door = the run's start (Marker_Arrival)
        s.onward = None         # door id of the one way on
        s.safe = False
        s.still = None          # (pos, face, pitch_deg)
        s._names = set()

    def uniq(s, n):
        base, k = n, 1
        while n in s._names:
            k += 1
            n = f"{base}_{k}"
        s._names.add(n)
        return n

    def solid(s, name, mn, mx, mat="wall", tags=(), art=True):
        if any(mn[i] >= mx[i] - 1e-6 for i in range(3)):
            return None
        n = s.uniq(name)
        s.boxes.append({"name": n, "min": [float(v) for v in mn], "max": [float(v) for v in mx], "mat": mat, "col": True, "art": art, "tags": set(tags)})
        return n

    def decor(s, name, mn, mx, mat="furn", tags=()):
        n = s.uniq("decor_" + name)
        s.boxes.append({"name": n, "min": [float(v) for v in mn], "max": [float(v) for v in mx], "mat": mat, "col": False, "art": True, "tags": set(tags)})

    def zone(s, kind, name, mn, mx, full=None):
        n = s.uniq(full or f"Zone_{kind}_{name}")
        s.boxes.append({"name": n, "min": [float(v) for v in mn], "max": [float(v) for v in mx], "mat": "water", "col": False, "art": False,
                        "zone": kind, "tags": set()})
        return n

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
        opens toward. closed_yaw_deg is three.js's rotation.y of the leaf (its local +x runs from the hinge along it)."""
        th = math.atan2(-run[1], run[0])
        op = math.atan2(-into[1], into[0])
        mag = 95.0 if swing is None else float(swing)
        sw = mag if math.sin(op - th) > 0 else -mag
        p = {"width": round(width, 3), "height": round(height, 3), "closed_yaw_deg": round(math.degrees(th), 1) + 0.0, "swing_deg": sw, "state": state}
        p.update(props or {})
        s.doors.append({"name": s.uniq("DoorLeaf_" + name), "hinge": [float(v) for v in hinge], "yaw": th, "props": p})

    def label(s, text, x, z, kind="room"):
        s.labels.append({"text": text, "x": x, "z": z, "kind": kind})

    def corridor(s, name, x0, x1, z0, z1):
        s.corridors.append({"name": name, "min": [x0, s.Y, z0], "max": [x1, s.Y, z1]})

    # ---- the pieces of a chamber
    def wall(s, name, axis, c0, c1, a0, a1, y0, y1, holes=(), mat="wall", tags=()):
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
                    s.solid(f"{name}_{k}", (u0, ya, c0), (u1, yb, c1), mat, tags)
                else:
                    s.solid(f"{name}_{k}", (c0, ya, u0), (c1, yb, u1), mat, tags)

    def part(s, name, axis, line, a0, a1, gaps=(), h=None, mat="wall", thick=T):
        """An inside wall on `line` (centred), along `axis` from a0 to a1, full height unless h is given. gaps: [(centre, width, kind[, state])]
        with kind 'open' (to the top of the wall) or 'door' (a HOLE_W by HOLE_H hole with a leaf, opening toward +z for an 'x' wall and +x for a
        'z' wall; the interior doors can be shut, trapped or barricaded)."""
        Y = s.Y
        top = Y + (s.H if h is None else h)
        holes = []
        for g in gaps:
            c, w, kind = g[0], g[1], g[2]
            if kind == "open":
                holes.append((c - w / 2, c + w / 2, Y, top))
            else:
                holes.append((c - HOLE_W / 2, c + HOLE_W / 2, Y, Y + HOLE_H))
                st = g[3] if len(g) > 3 else "closed"
                hh = DOOR_W / 2
                props = {"kind": "chamber door", "barricade": "yes"}
                if axis == "x":
                    s.door(f"{name}_{_tag(c)}", (c - hh, Y, line + thick / 2), (1, 0), (0, 1), state=st, props=props)
                else:
                    s.door(f"{name}_{_tag(c)}", (line + thick / 2, Y, c + hh), (0, -1), (1, 0), state=st, props=props)
        s.wall(name, axis, line - thick / 2, line + thick / 2, a0, a1, Y, top, holes, mat)

    def block(s, name, x0, x1, z0, z1, h, mat="furn", y0=0.0):
        return s.solid(name, (x0, s.Y + y0, z0), (x1, s.Y + y0 + h, z1), mat)

    def column(s, name, x, z, w=1.0, mat="wall"):
        return s.solid(name, (x - w / 2, s.Y, z - w / 2), (x + w / 2, s.Y + s.H, z + w / 2), mat)


def _tag(v):
    return ("m" if v < 0 else "") + f"{abs(v):g}".replace(".", "p")


# ---------------------------------------------------------------- the connector kit, placed from world/kit/<piece>.json
_KIT = {}


def kit_doc(piece):
    if piece not in _KIT:
        _KIT[piece] = json.loads((ROOT / f"world/kit/{piece}.json").read_text())
    return _KIT[piece]


def _rot(x, z, yaw):
    a = math.radians(yaw)
    return x * math.cos(a) + z * math.sin(a), -x * math.sin(a) + z * math.cos(a)


SLAB_WORDS = ("Floor", "Ceiling", "ceil", "landing")


def kit(S, piece, sfx, at, yaw, keep_links=None, spot_props=None, role=""):
    """Places a kit piece: its colliders (each with a grey art twin), doors, the links in keep_links (all when None), spots and zones, named
    <name>_<sfx> as kit_place.py names them. at = (x, z) on the chamber's floor."""
    d = kit_doc(piece)
    ax, az = at
    ay = S.Y

    def P(p):
        dx, dz = _rot(p[0], p[2], yaw)
        return (_r(ax + dx), _r(ay + p[1]), _r(az + dz))

    def F(f):
        fx, fz = _rot(f[0], f[1], yaw)
        return (_r(fx), _r(fz))
    tag = f"kit:{sfx}"
    for c in d["colliders"]:
        pts = [P((x, y, z)) for x in (c["min"][0], c["max"][0]) for y in (c["min"][1], c["max"][1]) for z in (c["min"][2], c["max"][2])]
        mn = [min(p[i] for p in pts) for i in range(3)]
        mx = [max(p[i] for p in pts) for i in range(3)]
        tags = {tag} | ({"slab"} if any(w in c["s"] for w in SLAB_WORDS) else set())
        S.solid(f"{c['s']}_{sfx}", mn, mx, "kit", tags)
    for dr in d["doors"]:
        cy = (float(dr["closed_yaw_deg"]) + yaw + 180.0) % 360.0 - 180.0
        props = {k: v for k, v in dr.items() if k not in ("name", "level", "hinge")}
        props["closed_yaw_deg"] = round(cy, 1) + 0.0
        if dr["name"] == "DoorLeaf_hall_far" and piece == "stair_door":
            props["state"] = "closed"
        S.doors.append({"name": S.uniq(f"{dr['name']}_{sfx}"), "hinge": list(P(dr["hinge"])), "yaw": math.radians(cy), "props": props, "kit": sfx})
    for l in d["links"]:
        if keep_links is not None and l["door"] not in keep_links:
            continue
        S.empty(f"Link_{l['door']}_{sfx}", P(l["at"]))
        S.empty(f"Arrive_{l['door']}_{sfx}", P(l["arrive"]), face=F(l["face"]))
    for sp in d["spots"]:
        props = {k: v for k, v in sp.items() if k not in ("kind", "name", "position", "face", "yaw_deg", "scale")}
        props.update(spot_props or {})
        S.empty(f"{sp['name']}_{sfx}", P(sp["position"]), face=F(sp["face"]), props=props)
    for z in d["zones"]:
        pts = [P((x, y, zz)) for x in (z["min"][0], z["max"][0]) for y in (z["min"][1], z["max"][1]) for zz in (z["min"][2], z["max"][2])]
        S.zone(z["kind"], "", [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)], full=f"{z['name']}_{sfx}")
    S.kits.append({"piece": piece, "sfx": sfx, "at": (ax, ay, az), "yaw": yaw, "role": role})


def elevator(S, sfx, x, side, to, role):
    """The kit's elevator against the north (side 'N') or south ('S') outer wall: its car's back on the wall, the landing in the room, and a
    shaft round the car (side stubs, a header to the ceiling, and two fills beside the jambs) so nothing can be walked behind or above it."""
    yaw, z = (0.0, Z0 + 2.35) if side == "N" else (180.0, Z1 - 2.35)
    kit(S, "elevator", sfx, (x, z), yaw, role=role)
    H = S.H
    tag = f"kit:{sfx}"
    for nm, (x0, x1, z0, z1, y0, y1) in {"Shaft_E": (1.05, 1.25, -2.35, 0.06, 0, H), "Shaft_W": (-1.25, -1.05, -2.35, 0.06, 0, H),
                                         "Shaft_Fill_E": (0.68, 1.05, -0.25, 0.06, 0, H), "Shaft_Fill_W": (-1.05, -0.68, -0.25, 0.06, 0, H),
                                         "Shaft_Head": (-1.05, 1.05, -2.35, -0.25, 2.48, H), "Shaft_Head_Front": (-0.68, 0.68, -0.25, 0.06, 2.4, H)}.items():
        pts = [_rot(a, b, yaw) for a in (x0, x1) for b in (z0, z1)]
        S.solid(f"{nm}_{sfx}", (x + min(p[0] for p in pts), S.Y + y0, z + min(p[1] for p in pts)),
                (x + max(p[0] for p in pts), S.Y + y1, z + max(p[1] for p in pts)), "kit", {tag})
    S.links[f"lift_{sfx}"] = to
    S.label("LIFT", x, z + (-1.2 if side == "N" else 1.2), kind="kit")
    return f"lift_{sfx}"


def sky_hall(S, sfx, x, to, role, side="N"):
    """The painted-sky hall standing against the north outer wall, its entry door facing the room (you walk in), its EXIT door at the far end:
    F at the EXIT door's Link_ takes you on. Only the `exit` link is kept."""
    yaw, z = (0.0, Z0 + 10.4) if side == "N" else (180.0, Z1 - 10.4)
    kit(S, "sky_hall", sfx, (x, z), yaw, keep_links={"exit"}, role=role)
    S.links[f"exit_{sfx}"] = to
    S.label("SKY HALL", x, z - 5.2 if side == "N" else z + 5.2, kind="kit")
    return f"exit_{sfx}"


def stair_door(S, sfx, x, side, to, role):
    """The store's stair door from the kit against the north ('N') or south ('S') outer wall: its lit hallway behind the door, inside the
    footprint, its landing in the room. Only the `stair` link is kept (F at the stair door)."""
    yaw, z = (0.0, Z0 + 10.4) if side == "N" else (180.0, Z1 - 10.4)
    kit(S, "stair_door", sfx, (x, z), yaw, keep_links={"stair"}, role=role)
    S.links[f"stair_{sfx}"] = to
    S.label("STAIR DOOR", x, z - 5.2 if side == "N" else z + 5.2, kind="kit")
    return f"stair_{sfx}"


def safe_house(S, sfx, x, z, yaw):
    """The kit's safe house room (shop, stash, save, crafting bench, respawn pad, locker; Zone_safe), its doorway at (x, z), the room behind."""
    kit(S, "safe_house", sfx, (x, z), yaw, spot_props={"of": "safe_house"}, role="safe house")
    S.safe = True
    cx, cz = _rot(0.0, 1.6, yaw)
    S.label("SAFE HOUSE", x + cx, z + cz, kind="safe")


def outer_door(S, holes, did, side, a, to, kind="door", state="closed"):
    """A plain door in the outer wall that joins this chamber to another scene: a HOLE_W by HOLE_H hole, a leaf opening into the room, Link_
    0.6 m in front of it and Arrive_ 1.2 m in, facing into the room."""
    holes.setdefault(side, []).append((a, HOLE_W, HOLE_H))
    h = DOOR_W / 2
    Y = S.Y
    props = {"kind": kind}
    if side == "N":
        S.door(did, (a - h, Y, Z0), (1, 0), (0, 1), state=state, props=props)
        S.link(did, (a, Y, Z0 + 0.6), (a, Y, Z0 + 1.2), (0, 1), to)
    elif side == "S":
        S.door(did, (a + h, Y, Z1), (-1, 0), (0, -1), state=state, props=props)
        S.link(did, (a, Y, Z1 - 0.6), (a, Y, Z1 - 1.2), (0, -1), to)
    elif side == "W":
        S.door(did, (X0, Y, a + h), (0, -1), (1, 0), state=state, props=props)
        S.link(did, (X0 + 0.6, Y, a), (X0 + 1.2, Y, a), (1, 0), to)
    else:
        S.door(did, (X1, Y, a - h), (0, 1), (-1, 0), state=state, props=props)
        S.link(did, (X1 - 0.6, Y, a), (X1 - 1.2, Y, a), (-1, 0), to)
    S.label("DOOR", a if side in "NS" else (X0 + 2.0 if side == "W" else X1 - 2.0), (Z0 + 2.0 if side == "N" else Z1 - 2.0) if side in "NS" else a, kind="kit")
    return did


def perimeter(S, holes):
    """The chamber's shell: floor slab, ceiling, and the four outer walls outside [X0, X1] x [Z0, Z1], filling the store's footprint exactly."""
    Y, H = S.Y, S.H

    def hs(side):
        return [(a - w / 2, a + w / 2, Y, Y + hh) for a, w, hh in holes.get(side, [])]
    S.solid("Floor", (X0 - T, Y - SLAB, Z0 - T), (X1 + T, Y, Z1 + T), "floor", ("slab",))
    S.solid("Ceiling", (X0 - T, Y + H, Z0 - T), (X1 + T, Y + H + 0.2, Z1 + T), "ceil", ("slab", "ceiling"))
    S.wall("Wall_N", "x", Z0 - T, Z0, X0 - T, X1 + T, Y, Y + H, hs("N"))
    S.wall("Wall_S", "x", Z1, Z1 + T, X0 - T, X1 + T, Y, Y + H, hs("S"))
    S.wall("Wall_W", "z", X0 - T, X0, Z0, Z1, Y, Y + H, hs("W"))
    S.wall("Wall_E", "z", X1, X1 + T, Z0, Z1, Y, Y + H, hs("E"))


def vent(S, n, side, a, length, to):
    """A vent duct, 0.8 m square inside a 1.0 m casing, along an outer wall, its grille shut (crawling is not in the game yet;
    docs/BLENDER_AREAS.md: "build the ducts and leave them shut"). Spot_vent_<n> in front of the grille names where it would lead."""
    Y = S.Y
    if side == "E":
        S.solid(f"Vent_{n}", (X1 - 1.0, Y, a), (X1, Y + 1.0, a + length), "vent")
        S.door(f"vent_{n}", (X1 - 0.9, Y + 0.1, a), (1, 0), (0, -1), width=0.8, height=0.8, props={"kind": "vent", "locked": "crawling is not in the game yet"})
        S.spot("vent", n, (X1 - 0.5, Y, a - 0.9), face=(0, 1), props={"to": to, "state": "shut"})
        S.label("VENT", X1 - 2.2, a + length / 2, kind="note")
    elif side == "W":
        S.solid(f"Vent_{n}", (X0, Y, a), (X0 + 1.0, Y + 1.0, a + length), "vent")
        S.door(f"vent_{n}", (X0 + 0.1, Y + 0.1, a), (1, 0), (0, -1), width=0.8, height=0.8, props={"kind": "vent", "locked": "crawling is not in the game yet"})
        S.spot("vent", n, (X0 + 0.5, Y, a - 0.9), face=(0, 1), props={"to": to, "state": "shut"})
        S.label("VENT", X0 + 2.2, a + length / 2, kind="note")
    elif side == "N":
        S.solid(f"Vent_{n}", (a, Y, Z0), (a + length, Y + 1.0, Z0 + 1.0), "vent")
        S.door(f"vent_{n}", (a, Y + 0.1, Z0 + 0.1), (0, 1), (-1, 0), width=0.8, height=0.8, props={"kind": "vent", "locked": "crawling is not in the game yet"})
        S.spot("vent", n, (a - 0.9, Y, Z0 + 0.5), face=(1, 0), props={"to": to, "state": "shut"})
        S.label("VENT", a + length / 2, Z0 + 2.2, kind="note")


def hazard(S, kind, n, a, b, box, zone, motion, period, props=None, y_from=None, y_to=None):
    """A hazard: its moving part Hazard_<kind>_<n> (one art object, no collider: the page moves it and deals the damage), the two ends of its
    travel as Spot_hazard_<kind>_<n>_a / _b (on the floor, at the part's origin at each end of its travel), and Zone_hazard_<kind>_<n>.
    a, b: (x, z) of the origin at each end; box: (min, max) of the part relative to its origin; zone: (x0, x1, z0, z1, height)."""
    Y = S.Y
    name = f"Hazard_{kind}_{n}"
    p = {"hazard": name, "kind_of": HAZARD_NAMES[kind], "motion": motion, "period_s": float(period)}
    p.update(props or {})
    if y_from is not None:
        p["y_from"], p["y_to"] = _r(Y + y_from), _r(Y + y_to)
    S.empty(f"Spot_hazard_{kind}_{n}_a", (a[0], Y, a[1]), face=None, props=dict(p, end="a"))
    S.empty(f"Spot_hazard_{kind}_{n}_b", (b[0], Y, b[1]), face=None, props=dict(p, end="b"))
    x0, x1, z0, z1, hh = zone
    S.zone("hazard", f"{kind}_{n}", (x0, Y, z0), (x1, Y + hh, z1))
    S.hazards.append({"name": name, "kind": kind, "n": n, "origin": [a[0], Y + (y_from or 0.0), a[1]], "a": [a[0], Y, a[1]], "b": [b[0], Y, b[1]],
                      "box": box, "props": p, "zone": f"Zone_hazard_{kind}_{n}"})


def spots(S, locker, loot, puzzle, objects, monsters):
    """The chamber's own spots: Spot_locker_1 (the Lost and Found, docs/WORLD.md section 10), Spot_loot_<n>, Spot_puzzle_1, Spot_object_<n> (the
    missing objects) and Spot_monster_<n> (the wave)."""
    Y = S.Y
    S.spot("locker", 1, (locker[0], Y, locker[1]), face=locker[2] if len(locker) > 2 else (0, 1),
           props={"what": "the Lost and Found: your loadout, and your gear back after you die"})
    for i, p in enumerate(loot, 1):
        S.spot("loot", i, (p[0], Y, p[1]))
    S.spot("puzzle", 1, (puzzle[0], Y, puzzle[1]), face=puzzle[2] if len(puzzle) > 2 else (0, 1), props={"what": PUZZLE[S.floor]})
    for i, p in enumerate(objects, 1):
        S.spot("object", i, (p[0], Y, p[1]), props={"what": "a missing object"})
    for i, p in enumerate(monsters, 1):
        S.spot("monster", i, (p[0], Y, p[1]), props={"wave": f"{FLOORS.index(S.floor) * 4 + S.idx}"})


def arrive_at(S, door):
    e = next(e for e in S.empties if e["name"] == f"Arrive_{door}")
    S.arrival = (door, tuple(e["pos"]))
    S.marker("Arrival", e["pos"], kind="Entrance", props={"door": door})


def finish(S, holes, still):
    perimeter(S, holes)
    S.still = still
    S.label(S.title.upper(), 0.0, Z1 - 4.0 if S.arrival and S.arrival[1][2] < 0 else Z0 + 4.0, kind="title")


def blade_box():
    return ([-0.03, 0.0, -0.6], [0.03, 1.2, 0.6])


def blade_box_x():
    return ([-0.6, 0.0, -0.03], [0.6, 1.2, 0.03])


# ================================================================ the chambers
# Each chamber: the arrival on one side, the way on on the far side, the wave's monsters near the way on, a hazard or two, a locker near the
# arrival. Chamber 2 of each floor holds the floor's safe house.

# ---------------------------------------------------------------- L4: showroom
def gbi_L4_1():
    S = Scene("gbi_L4_1", "L4", 1, "Showroom floor", "the run's first chamber: a lit showroom, a lava band to cross on display islands")
    Y, holes = S.Y, {}
    S.marker("Arrival", (0.0, Y, 24.0), kind="Spawn", props={"what": "Going back in starts here (the options screen at the store's doors)"})
    S.arrival = (None, (0.0, Y, 24.0))
    for zc in (19.0, 14.0, 9.0):                                  # gondola rows, 1.8 m high
        for xa, xb in ((-22.0, -4.0), (4.0, 22.0)):
            S.block(f"Gondola_{_tag(zc)}_{_tag(xa)}", xa, xb, zc - 0.5, zc + 0.5, 1.8)
    for xc in (-18.0, -9.0, 0.0, 9.0, 18.0):                     # display islands, one step up, the way over the lava
        for zc in (-4.0, 2.0):
            b = S.block(f"Island_{_tag(xc)}_{_tag(zc)}", xc - 1.5, xc + 1.5, zc - 1.5, zc + 1.5, 0.27, "trim")
            S.kerbs.append({"name": b, "from": Y})
    hazard(S, "lava", 1, (-25.5, -1.0), (25.5, -1.0), ([-0.1, 0.0, -6.0], [0.1, 0.02, 6.0]), (X0, X1, -7.0, 5.0, 0.6), "advance", 30.0,
           {"what": "the band's floor turns to lava from the west wall to the east; the islands stay safe"})
    S.part("Bays_Front", "x", -9.0, X0, X1, gaps=[(-16.0, 1.0, "door"), (0.0, 8.0, "open"), (16.0, 1.0, "door", "open")], h=3.2)
    S.part("Bay_Divider_W", "z", -6.0, Z0, -9.1, gaps=[(-15.5, 2.0, "open")], h=3.2)
    S.part("Bay_Divider_E", "z", 6.0, Z0, -9.1, gaps=[(-15.5, 2.0, "open")], h=3.2)
    S.block("Cash_Desk", -3.0, 3.0, -16.0, -14.0, 1.1)
    for i, (xa, xb, za, zb) in enumerate(((19.0, 23.0, -19.0, -15.0), (12.0, 16.0, -14.0, -11.0)), 1):
        S.block(f"Display_{i}", xa, xb, za, zb, 0.9)
    up = elevator(S, "to_L4_2", -12.0, "N", "gbi_L4_2, by the elevator", "way on")
    S.onward = up
    vent(S, 1, "E", 13.0, 6.0, "gbi_L4_2 (shut: crawling is not in the game yet)")
    spots(S, (-6.0, 25.9, (0, -1)), [(-20.0, 16.5), (20.0, 11.5), (10.0, -18.0)], (24.0, -20.9, (0, -1)),
          [(-15.0, 6.5), (-20.0, -14.0), (22.0, -1.0)], [(16.0, -16.0), (-20.0, -12.0), (0.0, -19.0)])
    S.label("GONDOLAS", 0.0, 14.0)
    S.label("LAVA BAND: ISLANDS", 0.0, 4.6)
    S.label("NW BAY", -16.0, -12.0)
    S.label("NE BAY", 16.0, -12.0)
    S.corridor("aisle_19_14", -22.0, 22.0, 14.5, 18.5)
    S.corridor("centre_gap", -4.0, 4.0, 8.0, 20.0)
    finish(S, holes, ((0.0, Y, 24.0), (0.0, -1.0), -4))
    return S


def gbi_L4_2():
    S = Scene("gbi_L4_2", "L4", 2, "Room sets", "furniture showroom: mock rooms down both sides, a chainsaw slot in the aisle, the floor's safe house")
    Y, holes = S.Y, {}
    arr = elevator(S, "from_L4_1", 12.0, "S", "gbi_L4_1, by the elevator (back)", "arrival")
    arrive_at(S, arr)
    for zc in (20.0, 13.0, 6.0, -1.0, -8.0):                    # the mock rooms: three-walled bays, 3 m high, open to the aisle
        S.part(f"Set_W_{_tag(zc)}", "x", zc, X0, -14.0, h=3.0)
        S.part(f"Set_E_{_tag(zc)}", "x", zc, 14.0, X1, h=3.0)
    for i, zc in enumerate((23.5, 16.5, 9.5, 2.5, -4.5), 1):    # their furniture
        S.block(f"Sofa_W_{i}", -24.5, -22.5, zc - 1.6, zc + 0.4, 0.8)
        S.block(f"Bed_E_{i}", 22.0, 25.5, zc - 1.5, zc + 0.5, 0.6) if zc < 20 else None
    hazard(S, "blade", 1, (0.0, 18.0), (0.0, -6.0), blade_box(), (-1.2, 1.2, -6.8, 18.8, 1.4), "track", 12.0,
           {"what": "a chainsaw blade runs up and down a slot in the aisle"})
    S.decor("Blade_Slot_1", (-0.1, Y, -6.6), (0.1, Y + 0.005, 18.6), "trim")
    hazard(S, "blade", 2, (-12.0, -12.0), (6.0, -12.0), blade_box_x(), (-12.8, 6.8, -13.2, -10.8, 1.4), "track", 9.0,
           {"what": "a chainsaw blade runs across in front of the safe house"})
    S.decor("Blade_Slot_2", (-12.6, Y, -12.1), (6.6, Y + 0.005, -11.9), "trim")
    safe_house(S, "L4", -6.0, -16.75, 0.0)
    on = sky_hall(S, "to_L4_3", 10.0, "gbi_L4_3, through the painted-sky hall", "way on")
    S.onward = on
    spots(S, (16.0, 25.6, (0, -1)), [(-20.0, 16.5), (20.0, 2.5), (-20.0, -4.5)], (20.0, -19.5, (0, -1)),
          [(-20.0, 23.5), (20.0, 9.5), (-16.0, -19.0)], [(18.0, -16.0), (-18.0, -14.0), (3.0, -20.0)])
    S.label("ROOM SETS", -20.0, 10.0)
    S.label("ROOM SETS", 20.0, 6.0)
    S.label("AISLE", -6.0, 8.0)
    S.corridor("aisle", -13.9, 13.9, -8.0, 22.0)
    finish(S, holes, ((12.0, Y, 23.0), (0.0, -1.0), -4))
    return S


def gbi_L4_3():
    S = Scene("gbi_L4_3", "L4", 3, "Stockroom", "the racking behind the showroom: tall aisles, a cross aisle where the walls close")
    Y, holes = S.Y, {}
    arr = outer_door(S, holes, "from_L4_2", "S", -18.0, "gbi_L4_2's painted-sky hall (back)", kind="hall door")
    arrive_at(S, arr)
    for zc in (18.0, 12.0, 6.0, 0.0, -6.0):                     # racking, 4 m high, a 4 m cross aisle in the middle
        S.block(f"Rack_W_{_tag(zc)}", -22.0, -2.0, zc - 0.6, zc + 0.6, 4.0)
        S.block(f"Rack_E_{_tag(zc)}", 2.0, 22.0, zc - 0.6, zc + 0.6, 4.0)
    hazard(S, "crush", 1, (-1.9, 3.0), (-0.05, 3.0), ([0.0, 0.0, -2.4], [0.2, 3.0, 2.4]), (-2.0, 0.0, 0.6, 5.4, 3.2), "close", 8.0,
           {"what": "a rack end slides across the cross aisle and meets the other", "pair": "Hazard_crush_2"})
    hazard(S, "crush", 2, (1.9, 3.0), (0.05, 3.0), ([-0.2, 0.0, -2.4], [0.0, 3.0, 2.4]), (0.0, 2.0, 0.6, 5.4, 3.2), "close", 8.0,
           {"what": "a rack end slides across the cross aisle and meets the other", "pair": "Hazard_crush_1"})
    for i, (xa, xb, za, zb) in enumerate(((-20.0, -16.0, -18.0, -15.0), (-8.0, -4.0, -20.0, -17.0), (6.0, 10.0, -16.0, -13.0)), 1):
        S.block(f"Pallets_{i}", xa, xb, za, zb, 1.2)
    S.decor("Dock_Door", (-6.0, Y, Z0 + 0.0), (6.0, Y + 3.6, Z0 + 0.05), "trim")
    on = sky_hall(S, "to_L4_4", 20.0, "gbi_L4_4 (the store's L4), through the painted-sky hall", "way on")
    S.onward = on
    spots(S, (-14.0, 25.6, (0, -1)), [(-24.0, 9.0), (24.0, -2.0), (0.0, -16.0)], (-24.0, -20.9, (0, -1)),
          [(-12.0, 15.0), (12.0, 3.0), (-12.0, -3.0)], [(14.0, -18.0), (-14.0, -12.0), (0.0, -10.0)])
    S.label("RACKING", -12.0, 9.0)
    S.label("RACKING", 12.0, 9.0)
    S.label("CROSS AISLE", 0.0, 8.0)
    S.label("DOCK", -2.0, -19.0)
    for i, zc in enumerate((15.0, 9.0, 3.0, -3.0), 1):
        S.corridor(f"aisle_{i}", -22.0, 22.0, zc - 2.3, zc + 2.3)
    S.corridor("cross_aisle", -1.9, 1.9, -6.6, 18.6)
    finish(S, holes, ((0.0, Y, 25.0), (0.0, -1.0), -4))
    return S


# ---------------------------------------------------------------- L3: white plaster
def gbi_L3_2():
    S = Scene("gbi_L3_2", "L3", 2, "White gallery", "one bright plaster hall, free-standing walls and plinths, the floor's safe house")
    Y, holes = S.Y, {}
    arr = stair_door(S, "from_L3_1", -16.0, "S", "gbi_L3_1 (the store's L3), its stair door down (back)", "arrival")
    arrive_at(S, arr)
    safe_house(S, "L3", -20.7, 0.0, 90.0)
    for nm, axis, line, a0, a1 in (("W1", "x", 8.0, -8.0, 4.0), ("W2", "z", 8.0, -6.0, 10.0), ("W3", "x", -6.0, -16.0, -4.0),
                                   ("W4", "z", -10.0, -20.0, -13.0), ("W5", "x", -14.0, 6.0, 18.0), ("W6", "z", 18.0, 12.0, 22.0)):
        S.part(f"Plaster_{nm}", axis, line, a0, a1, thick=0.3)
    for i, (x, z) in enumerate(((-4.0, 14.0), (2.0, 18.0), (14.0, 4.0), (-14.0, -14.0), (22.0, -12.0)), 1):
        S.block(f"Plinth_{i}", x - 0.5, x + 0.5, z - 0.5, z + 0.5, 1.0)
    hazard(S, "blade", 1, (-6.0, -10.0), (14.0, -10.0), blade_box_x(), (-6.8, 14.8, -11.2, -8.8, 1.4), "track", 10.0,
           {"what": "a chainsaw blade runs along a slot across the gallery"})
    S.decor("Blade_Slot_1", (-6.6, Y, -10.1), (14.6, Y + 0.005, -9.9), "trim")
    on = outer_door(S, holes, "to_L3_3", "N", 14.0, "gbi_L3_3, by a door")
    S.onward = on
    spots(S, (-10.0, 25.0, (0, -1)), [(20.0, 20.0), (-22.0, -14.0), (2.0, 2.0)], (24.0, -12.0, (1, 0)),
          [(0.0, 20.0), (16.0, 0.0), (-18.0, -18.0)], [(10.0, -18.0), (20.0, -6.0), (-4.0, -16.0)])
    S.label("GALLERY", 0.0, 8.0 + 3.0)
    finish(S, holes, ((-16.0, Y, 15.0), (0.3, -1.0), -3))
    return S


def gbi_L3_3():
    S = Scene("gbi_L3_3", "L3", 3, "Colonnade", "white columns either side of a long hall you must walk the length of, where the walls close")
    Y, holes = S.Y, {}
    arr = outer_door(S, holes, "from_L3_2", "S", 0.0, "gbi_L3_2 (back)")
    arrive_at(S, arr)
    S.part("Hall_S", "x", 5.0, X0, X1, gaps=[(18.0, 3.0, "open")])
    S.part("Hall_N", "x", 1.0, X0, X1, gaps=[(-18.0, 3.0, "open")])
    for i, xc in enumerate((-6.0, 6.0), 1):
        hazard(S, "crush", i, (xc, 1.5), (xc, 4.5), ([-1.0, 0.0, -0.2], [1.0, 3.0, 0.2]), (xc - 1.2, xc + 1.2, 1.1, 4.9, 3.2), "close", 7.0 + i,
               {"what": "a plaster slab slides across the hall and meets the far wall"})
    for xc in (-20.0, -12.0, -4.0, 4.0, 12.0, 20.0):
        for zc in (-16.0, -8.0, 11.0, 19.0):
            S.column(f"Column_{_tag(xc)}_{_tag(zc)}", xc, zc)
    on = elevator(S, "to_L3_4", -14.0, "N", "gbi_L3_4, by the elevator", "way on")
    S.onward = on
    spots(S, (4.0, 25.6, (0, -1)), [(-22.0, 23.0), (22.0, -20.0), (0.0, 3.0)], (24.0, 15.0, (1, 0)),
          [(-8.0, 15.0), (8.0, -12.0), (-24.0, -4.0)], [(8.0, -19.0), (-22.0, -10.0), (16.0, -4.0)])
    S.label("THE HALL", 12.0, 3.0)
    S.label("COLONNADE", 0.0, 15.0)
    S.label("COLONNADE", 0.0, -12.0)
    S.corridor("hall", -24.0, 24.0, 1.1, 4.9)
    finish(S, holes, ((0.0, Y, 25.5), (0.0, -1.0), -3))
    return S


def gbi_L3_4():
    S = Scene("gbi_L3_4", "L3", 4, "White maze", "white plaster walls that fold the room into one long path; lava chases you down a leg; the stairs down")
    Y, holes = S.Y, {}
    arr = elevator(S, "from_L3_3", 14.0, "S", "gbi_L3_3, by the elevator (back)", "arrival")
    arrive_at(S, arr)
    S.part("Maze_A", "x", 16.0, X0, 6.0)
    S.part("Maze_B", "x", 8.0, -14.0, X1)
    S.part("Maze_C", "x", 0.0, X0, 10.0)
    S.part("Maze_D", "x", -8.0, -10.0, X1)
    S.part("Maze_V1", "z", 0.0, 0.1, 5.0)
    S.part("Maze_V2", "z", -6.0, 11.0, 15.9)
    S.part("Maze_V3", "z", 16.0, -7.9, -3.0)
    S.part("Maze_V4", "z", -20.0, -5.0, -0.1)
    hazard(S, "lava", 1, (24.0, -4.0), (-8.0, -4.0), ([-0.1, 0.0, -3.8], [0.1, 0.02, 3.8]), (-10.0, X1, -7.9, -0.1, 0.6), "advance", 25.0,
           {"what": "the floor turns to lava down this leg from the east, chasing you west"})
    on = stair_door(S, "down", -12.0, "N", "gbi_L2_1 (the store's L2): its stairwell from L3", "way on")
    S.onward = on
    spots(S, (18.0, 25.8, (0, -1)), [(-22.0, 12.0), (20.0, 4.0), (-20.0, -16.0)], (-24.0, 24.0, (-1, 0)),
          [(0.0, 12.0), (-16.0, 4.0), (8.0, -15.0)], [(-4.0, -15.0), (12.0, -18.0), (-23.0, -4.0)])
    S.label("1", 16.0, 21.0, kind="note")
    S.label("2", -10.0, 12.0, kind="note")
    S.label("3", 4.0, 4.0, kind="note")
    S.label("4: LAVA LEG", 8.0, -4.0, kind="note")
    S.label("5", 0.0, -15.0, kind="note")
    for nm, x0, x1, z0, z1 in (("leg_1", X0, X1, 16.1, 23.4), ("leg_2", -14.0, X1, 8.1, 10.9), ("leg_3", X0, 10.0, 5.1, 7.9),
                               ("leg_4", -10.0, 15.8, -7.9, -0.1), ("leg_5", -10.0, X1, -22.15 + 0.1, -8.1)):
        S.corridor(nm, x0, x1, z0, z1)
    finish(S, holes, ((14.0, Y, 23.0), (-1.0, -0.2), -3))
    return S


# ---------------------------------------------------------------- L2: the loop of doors
def gbi_L2_2():
    S = Scene("gbi_L2_2", "L2", 2, "Door grid", "a grid of small rooms, a door on every side; gas drifts down the middle row; the floor's safe house")
    Y, holes = S.Y, {}
    arr = stair_door(S, "from_L2_1", 16.0, "S", "gbi_L2_1 (the store's L2), its stair door down (back)", "arrival")
    arrive_at(S, arr)
    safe_house(S, "L2", -12.0, 21.75, 180.0)
    xs = (-17.4, -8.7, 0.0, 8.7, 17.4)
    cells = (-21.75, -13.05, -4.35, 4.35, 13.05, 21.75)
    states = ["closed", "open", "ajar"]
    k = 0
    for zl in (8.0, 0.0, -8.0):
        gaps = []
        for c in cells:
            k += 1
            gaps.append((c, 1.0, "door", states[k % 3]) if k % 4 else (c, 1.6, "open"))
        S.part(f"Grid_X_{_tag(zl)}", "x", zl, X0, X1, gaps=gaps)
    for xl in xs:
        for (za, zb, zc) in ((Z0, -8.1, -15.1), (-7.9, -0.1, -4.0), (0.1, 7.9, 4.0)):
            k += 1
            g = [(zc, 1.0, "door", states[k % 3])] if k % 3 else [(zc, 1.6, "open")]
            S.part(f"Grid_Z_{_tag(xl)}_{_tag(zc)}", "z", xl, za, zb, gaps=g)
    for i, (x, z) in enumerate(((-13.0, -18.0), (4.35, -14.0), (21.75, -4.0), (-21.75, 4.0), (13.05, 4.5)), 1):
        S.block(f"Boxes_{i}", x - 0.8, x + 0.8, z - 0.6, z + 0.6, 0.9)
    hazard(S, "gas", 1, (24.0, -4.0), (-24.0, -4.0), ([-2.0, 0.0, -3.5], [2.0, 2.6, 3.5]), (X0, X1, -7.9, -0.1, S.H), "drift", 40.0,
           {"what": "a cloud of gas drifts down the middle row of rooms from the east"})
    on = sky_hall(S, "to_L2_3", -22.0, "gbi_L2_3, through the painted-sky hall", "way on")
    S.onward = on
    vent(S, 1, "E", -18.0, 5.0, "gbi_L2_3 (shut: crawling is not in the game yet)")
    spots(S, (20.5, 25.8, (0, -1)), [(-13.0, 4.0), (13.0, -4.0), (4.35, -19.0)], (21.75, -13.0, (1, 0)),
          [(-21.75, -4.0), (4.35, 4.0), (-4.35, -18.0)], [(13.0, -18.0), (-13.0, -14.0), (-4.35, -4.0)])
    S.label("HALL", 4.0, 14.0)
    S.label("GAS ROW", 0.0, -2.0)
    S.corridor("hall", -8.0, 14.0, 8.1, 21.0)
    finish(S, holes, ((16.0, Y, 15.0), (-0.3, -1.0), -3))
    return S


def gbi_L2_3():
    S = Scene("gbi_L2_3", "L2", 3, "Long loop", "rings inside rings: the way on is only reached by walking the loops, blades in two legs")
    Y, holes = S.Y, {}
    arr = outer_door(S, holes, "from_L2_2", "S", 20.0, "gbi_L2_2's painted-sky hall (back)", kind="hall door")
    arrive_at(S, arr)
    # ring 1 (x -22..22, z -18..23), ring 2 (x -14..14, z -10..15), the core room (x -6..6, z -2..7)
    S.part("Ring1_S", "x", 23.0, -22.1, 22.1, gaps=[(0.0, 3.0, "open")])
    S.part("Ring1_N", "x", -18.0, -22.1, 22.1, gaps=[(18.0, 3.0, "open")])
    S.part("Ring1_W", "z", -22.0, -17.9, 22.9)
    S.part("Ring1_E", "z", 22.0, -17.9, 22.9)
    S.part("Ring2_S", "x", 15.0, -14.1, 14.1, gaps=[(-10.0, 1.0, "door", "closed")])
    S.part("Ring2_N", "x", -10.0, -14.1, 14.1, gaps=[(0.0, 3.0, "open")])
    S.part("Ring2_W", "z", -14.0, -9.9, 14.9)
    S.part("Ring2_E", "z", 14.0, -9.9, 14.9)
    S.part("Core_S", "x", 7.0, -6.1, 6.1, gaps=[(0.0, 1.0, "door", "closed")])
    S.part("Core_N", "x", -2.0, -6.1, 6.1)
    S.part("Core_W", "z", -6.0, -1.9, 6.9)
    S.part("Core_E", "z", 6.0, -1.9, 6.9)
    S.part("Outer_Stop_W", "x", 0.0, X0, -22.1)                  # the outer corridor is cut on both sides: the way on is through ring 1
    S.part("Outer_Stop_E", "x", 0.0, 22.1, X1)
    S.block("Core_Table", -2.0, 2.0, 3.5, 5.5, 0.75)
    hazard(S, "blade", 1, (16.0, -20.1), (-16.0, -20.1), blade_box_x(), (-16.8, 16.8, -22.0, -18.2, 1.4), "track", 14.0,
           {"what": "a chainsaw blade runs the length of the north corridor"})
    S.decor("Blade_Slot_1", (-16.6, Y, -20.2), (16.6, Y + 0.005, -20.0), "trim")
    hazard(S, "blade", 2, (-18.0, 19.0), (18.0, 19.0), blade_box_x(), (-18.8, 18.8, 17.8, 20.2, 1.4), "track", 12.0,
           {"what": "a chainsaw blade runs the south leg of the ring"})
    S.decor("Blade_Slot_2", (-18.6, Y, 18.9), (18.6, Y + 0.005, 19.1), "trim")
    on = outer_door(S, holes, "to_L2_4", "N", -20.0, "gbi_L2_4, by a door")
    S.onward = on
    spots(S, (23.5, 25.8, (0, -1)), [(-24.0, 10.0), (18.0, 0.0), (-10.0, 10.0)], (0.0, 1.0, (0, -1)),
          [(-18.0, -2.0), (8.0, -14.0), (-24.0, -10.0)], [(-10.0, -14.0), (18.0, -14.0), (-24.0, 18.0)])
    S.label("OUTER", 0.0, 25.2)
    S.label("RING", 0.0, 19.0 - 1.6)
    S.label("INNER", 0.0, 11.0)
    S.label("CORE", 0.0, 2.5)
    S.corridor("outer_S", X0, X1, 23.1, 27.0)
    S.corridor("outer_N", X0, X1, -22.0, -18.1)
    S.corridor("ring_S", -21.9, 21.9, 15.1, 22.9)
    finish(S, holes, ((0.0, Y, 26.0), (0.0, -1.0), -3))
    return S


def gbi_L2_4():
    S = Scene("gbi_L2_4", "L2", 4, "Split halls", "three long halls side by side, cross passages between them; the walls close in the middle hall; the stairs down")
    Y, holes = S.Y, {}
    arr = outer_door(S, holes, "from_L2_3", "S", -20.0, "gbi_L2_3 (back)")
    arrive_at(S, arr)
    S.part("Hall_Wall_W", "z", -9.0, -16.0, Z1, gaps=[(14.0, 2.4, "open"), (-6.0, 1.0, "door", "ajar")])
    S.part("Hall_Wall_E", "z", 9.0, -16.0, Z1, gaps=[(4.0, 2.4, "open"), (20.0, 1.0, "door", "closed")])
    for i, xc in ((1, -1.0), (2, 1.0)):
        hazard(S, "crush", i, (-8.5 if i == 1 else 8.5, -2.0), (-0.3 if i == 1 else 0.3, -2.0),
               ([0.0, 0.0, -2.0], [0.4, 2.8, 2.0]) if i == 1 else ([-0.4, 0.0, -2.0], [0.0, 2.8, 2.0]),
               (-8.9, 0.0, -4.0, 0.0, S.H) if i == 1 else (0.0, 8.9, -4.0, 0.0, S.H), "close", 9.0,
               {"what": "the middle hall's walls close in", "pair": f"Hazard_crush_{3 - i}"})
    for i, (x0, x1, z0, z1, h) in enumerate(((-24.0, -21.0, 6.0, 9.0, 0.9), (-16.0, -13.0, -10.0, -8.0, 0.75), (20.0, 24.0, 12.0, 14.0, 0.75),
                                            (13.0, 16.0, -14.0, -11.0, 0.9), (-4.0, -2.0, 12.0, 16.0, 0.9), (3.0, 6.0, 20.0, 22.0, 0.75)), 1):
        S.block(f"Desk_{i}", x0, x1, z0, z1, h)
    on = stair_door(S, "down", 0.0, "N", "gbi_L1_1 (the store's L1): its stairwell from L2", "way on")
    S.onward = on
    spots(S, (-16.5, 25.8, (0, -1)), [(-20.0, -10.0), (20.0, 20.0), (20.0, -19.0)], (-24.0, 4.0, (-1, 0)),
          [(0.0, 18.0), (20.0, -4.0), (-14.0, -19.0)], [(6.0, -19.0), (20.0, 8.0), (-4.0, -8.0)])
    S.label("WEST HALL", -17.0, 0.0)
    S.label("MIDDLE HALL", 0.0, 8.0)
    S.label("EAST HALL", 17.0, 0.0)
    S.corridor("west_hall", -12.5, -9.1, -16.0, 26.0)
    S.corridor("middle_hall", -1.8, 2.8, 0.1, 26.0)
    S.corridor("east_hall", 9.1, 12.9, -16.0, 26.0)
    finish(S, holes, ((-20.0, Y, 25.5), (0.4, -1.0), -3))
    return S


# ---------------------------------------------------------------- L1: offices
def gbi_L1_2():
    S = Scene("gbi_L1_2", "L1", 2, "Cubicle farm", "an open office of low cubicles, private offices along the north wall, gas down an aisle; the floor's safe house")
    Y, holes = S.Y, {}
    arr = stair_door(S, "from_L1_1", -16.0, "S", "gbi_L1_1 (the store's L1), its stair door down (back)", "arrival")
    arrive_at(S, arr)
    safe_house(S, "L1", 20.7, 14.0, -90.0)
    for cx in (-18.0, -12.0, -6.0, 0.0, 6.0, 12.0):              # pods 3 m square of 1.4 m partitions, open to the south
        for cz in (6.0, 0.0, -6.0, -12.0):
            t = f"{_tag(cx)}_{_tag(cz)}"
            S.solid(f"Pod_Back_{t}", (cx - 1.55, Y, cz - 1.55), (cx + 1.55, Y + 1.4, cz - 1.45), "trim")
            S.solid(f"Pod_Side_W_{t}", (cx - 1.55, Y, cz - 1.45), (cx - 1.45, Y + 1.4, cz + 1.5), "trim")
            S.solid(f"Pod_Side_E_{t}", (cx + 1.45, Y, cz - 1.45), (cx + 1.55, Y + 1.4, cz + 1.5), "trim")
            S.solid(f"Pod_Desk_{t}", (cx - 1.4, Y, cz - 1.4), (cx + 1.4, Y + 0.75, cz - 0.7), "furn")
    S.part("Offices_Front", "x", -16.0, X0, -6.0, gaps=[(-23.0, 1.0, "door", "closed"), (-17.0, 1.0, "door", "ajar"), (-10.0, 1.0, "door", "open")])
    S.part("Office_Wall_1", "z", -20.0, Z0, -16.1)
    S.part("Office_Wall_2", "z", -14.0, Z0, -16.1)
    S.part("Office_Wall_3", "z", -6.0, Z0, -16.1)
    hazard(S, "gas", 1, (22.0, -3.0), (-22.0, -3.0), ([-2.0, 0.0, -1.4], [2.0, 2.4, 1.4]), (X0, X1, -4.4, -1.6, S.H), "drift", 35.0,
           {"what": "gas from a ceiling vent drifts west down the aisle"})
    on = elevator(S, "to_L1_3", 12.0, "N", "gbi_L1_3, by the elevator", "way on")
    S.onward = on
    spots(S, (-12.0, 25.6, (0, -1)), [(-18.0, 6.5), (6.0, -11.5), (-23.0, -19.0)], (24.0, -20.9, (0, -1)),
          [(0.0, 0.5), (-11.0, -19.0), (18.0, 2.0)], [(18.0, -14.0), (-6.0, -9.0), (0.0, -19.0)])
    S.label("CUBICLES", -3.0, 10.0)
    S.label("OFFICES", -16.0, -20.0)
    S.label("GAS AISLE", 16.0, -3.0)
    S.corridor("gas_aisle", X0, X1, -4.45, -1.6)
    S.corridor("south_hall", X0, 20.6, 7.6, 14.0)
    finish(S, holes, ((-16.0, Y, 15.0), (0.4, -1.0), -3))
    return S


def gbi_L1_3():
    S = Scene("gbi_L1_3", "L1", 3, "Corridor offices", "two corridors cross in the middle, offices in every quarter, the walls close in the north leg")
    Y, holes = S.Y, {}
    arr = elevator(S, "from_L1_2", -10.0, "S", "gbi_L1_2, by the elevator (back)", "arrival")
    arrive_at(S, arr)
    # the east-west spine (z 0..3) and the north-south spine (x -1.5..1.5)
    S.part("Spine_N_W", "x", -0.1, X0, -1.7, gaps=[(-22.0, 1.0, "door", "closed"), (-14.0, 1.0, "door", "ajar"), (-6.0, 1.0, "door", "closed")])
    S.part("Spine_N_E", "x", -0.1, 1.7, X1, gaps=[(10.0, 2.0, "open")])
    S.part("Spine_S_W", "x", 3.1, X0, -1.7, gaps=[(-10.0, 2.0, "open")])
    S.part("Spine_S_E", "x", 3.1, 1.7, X1, gaps=[(6.0, 1.0, "door", "closed"), (14.0, 1.0, "door", "open"), (22.0, 1.0, "door", "ajar")])
    S.part("Spine_W_N", "z", -1.6, Z0, -0.2)
    S.part("Spine_E_N", "z", 1.6, Z0, -0.2)
    S.part("Spine_W_S", "z", -1.6, 3.2, Z1)
    S.part("Spine_E_S", "z", 1.6, 3.2, Z1)
    S.part("Office_NW_1", "z", -18.0, Z0, -0.2)
    S.part("Office_NW_2", "z", -10.0, Z0, -0.2)
    S.part("Office_SE_1", "z", 10.0, 3.2, Z1)
    S.part("Office_SE_2", "z", 18.0, 3.2, Z1)
    for i, (x0, x1, z0, z1) in enumerate(((-24.0, -20.0, -8.0, -6.0), (-16.0, -12.0, -12.0, -10.0), (-8.0, -4.0, -16.0, -14.0),
                                         (4.0, 8.0, 14.0, 16.0), (12.0, 16.0, 20.0, 22.0), (20.0, 24.0, 8.0, 10.0),
                                         (6.0, 10.0, -8.0, -6.0), (20.0, 24.0, -10.0, -8.0)), 1):
        S.block(f"Desk_{i}", x0, x1, z0, z1, 0.75)
    for i in (1, 2):
        hazard(S, "crush", i, (-1.1 if i == 1 else 1.1, -12.0), (0.2 if i == 1 else -0.2, -12.0),
               ([-0.4, 0.0, -2.0], [-0.2, 2.7, 2.0]) if i == 1 else ([0.2, 0.0, -2.0], [0.4, 2.7, 2.0]),
               (-1.5, 1.5, -14.0, -10.0, S.H), "close", 6.0,
               {"what": "the north leg's walls close", "pair": f"Hazard_crush_{3 - i}"})
    on = sky_hall(S, "to_L1_4", 18.0, "gbi_L1_4, through the painted-sky hall", "way on")
    S.onward = on
    vent(S, 1, "N", 4.0, 5.0, "gbi_L1_4 (shut: crawling is not in the game yet)")
    spots(S, (-14.5, 25.8, (0, -1)), [(-22.0, -10.0), (0.0, -20.0), (14.0, 15.0)], (24.0, -2.0, (1, 0)),
          [(-6.0, -10.0), (22.0, 20.0), (-20.0, 10.0)], [(10.0, -16.0), (-14.0, -14.0), (14.0, 10.0)])
    S.label("RECEPTION", -14.0, 14.0)
    S.label("OPEN OFFICE", 12.0, -4.0 - 6.0)
    S.label("OFFICES", -14.0, -4.0 - 2.0)
    S.label("OFFICES", 14.0, 6.0)
    S.label("NORTH LEG", 0.0, -16.0, kind="note")
    S.corridor("spine_ew", X0, X1, 0.0, 3.0)
    S.corridor("spine_ns", -1.5, 1.5, Z0, Z1)
    finish(S, holes, ((-10.0, Y, 23.0), (0.0, -1.0), -3))
    return S


def gbi_L1_4():
    S = Scene("gbi_L1_4", "L1", 4, "Conference ring", "a ring corridor round the conference room, offices outside it, a blade in the west leg; the stairs down")
    Y, holes = S.Y, {}
    arr = outer_door(S, holes, "from_L1_3", "S", 18.0, "gbi_L1_3's painted-sky hall (back)", kind="hall door")
    arrive_at(S, arr)
    S.part("Conf_S", "x", 10.0, -10.1, 10.1, gaps=[(0.0, 1.0, "door", "closed")])
    S.part("Conf_N", "x", -6.0, -10.1, 10.1, gaps=[(6.0, 1.0, "door", "ajar")])
    S.part("Conf_W", "z", -10.0, -5.9, 9.9)
    S.part("Conf_E", "z", 10.0, -5.9, 9.9)
    S.block("Conf_Table", -6.0, 6.0, 0.0, 4.0, 0.75)
    S.part("Ring_S", "x", 18.0, -18.1, 18.1, gaps=[(10.0, 2.4, "open")])
    S.part("Ring_N", "x", -14.0, -18.1, 18.1, gaps=[(-14.0, 2.4, "open"), (12.0, 1.0, "door", "closed")])
    S.part("Ring_W", "z", -18.0, -13.9, 17.9, gaps=[(4.0, 1.0, "door", "open")])
    S.part("Ring_E", "z", 18.0, -13.9, 17.9, gaps=[(-4.0, 1.0, "door", "closed")])
    for i, (x0, x1, z0, z1) in enumerate(((-24.0, -20.0, 20.0, 22.0), (-6.0, -2.0, 22.0, 24.0), (20.0, 24.0, 6.0, 8.0),
                                         (20.0, 24.0, -10.0, -8.0), (-4.0, 0.0, -20.0, -18.0), (12.0, 16.0, -20.0, -18.0)), 1):
        S.block(f"Desk_{i}", x0, x1, z0, z1, 0.75)
    hazard(S, "blade", 1, (-14.0, 14.0), (-14.0, -10.0), blade_box(), (-15.2, -12.8, -10.8, 14.8, 1.4), "track", 12.0,
           {"what": "a chainsaw blade runs the ring's west leg"})
    S.decor("Blade_Slot_1", (-14.1, Y, -10.6), (-13.9, Y + 0.005, 14.6), "trim")
    hazard(S, "gas", 1, (-8.0, 8.0), (8.0, -4.0), ([-2.0, 0.0, -2.0], [2.0, 2.4, 2.0]), (-9.9, 9.9, -5.9, 9.9, S.H), "fill", 30.0,
           {"what": "the conference room fills with gas once its doors are shut"})
    on = stair_door(S, "down", -22.0, "N", "gbi_B1_1 (the store's B1): its stairwell from L1", "way on")
    S.onward = on
    spots(S, (21.5, 25.8, (0, -1)), [(-6.0, 7.0), (22.0, -18.0), (-22.0, 24.5)], (0.0, -20.9, (0, -1)),
          [(14.0, 2.0), (-22.0, 4.0), (8.0, -18.0)], [(-14.0, -2.0), (14.0, -10.0), (-10.0, -18.0)])
    S.label("CONFERENCE", 0.0, 6.5)
    S.label("RING", 14.0, 13.0)
    S.label("OFFICES", 0.0, 21.0)
    S.corridor("ring_w", -17.9, -10.1, -13.9, 17.9)
    S.corridor("ring_e", 10.1, 17.9, -13.9, 17.9)
    finish(S, holes, ((18.0, Y, 25.5), (-0.5, -1.0), -3))
    return S


# ---------------------------------------------------------------- B1: pools
def gbi_B1_2():
    S = Scene("gbi_B1_2", "B1", 2, "Lido", "a white-tiled pool hall under columns; the tide rises in the pool; the floor's safe house")
    Y, holes = S.Y, {}
    arr = outer_door(S, holes, "from_B1_1", "S", 0.0, "gbi_B1_1 (the store's B1): a new door there (open question)")
    arrive_at(S, arr)
    safe_house(S, "B1", -20.7, 18.0, 90.0)
    S.part("Pool_N", "x", -14.2, -16.3, 16.3, gaps=[(0.0, 3.0, "open")], h=1.1, mat="trim")
    S.part("Pool_S", "x", 12.2, -16.3, 16.3, gaps=[(-8.0, 3.0, "open"), (8.0, 3.0, "open")], h=1.1, mat="trim")
    S.part("Pool_W", "z", -16.2, -14.1, 12.1, gaps=[(0.0, 3.0, "open")], h=1.1, mat="trim")
    S.part("Pool_E", "z", 16.2, -14.1, 12.1, gaps=[(0.0, 3.0, "open")], h=1.1, mat="trim")
    S.zone("water", "pool", (-16.1, Y, -14.1), (16.1, Y + 0.3, 12.1))
    S.decor("Pool_Water", (-16.1, Y + 0.28, -14.1), (16.1, Y + 0.3, 12.1), "water")
    for xc in (-12.0, -4.0, 4.0, 12.0):
        for zc in (-10.0, -2.0, 6.0):
            S.column(f"Column_{_tag(xc)}_{_tag(zc)}", xc, zc, 0.6)
    for xc in (-20.0, 20.0):
        for zc in (-16.0, -8.0, 0.0, 8.0):
            S.column(f"Column_{_tag(xc)}_{_tag(zc)}", xc, zc, 0.6)
    hazard(S, "tide", 1, (0.0, -1.0), (0.0, -1.0), ([-16.0, 0.0, -13.0], [16.0, 0.05, 13.0]), (-16.1, 16.1, -14.1, 12.1, 1.6), "rise", 45.0,
           {"what": "the pool's water rises to chest height and falls"}, y_from=0.3, y_to=1.4)
    on = outer_door(S, holes, "to_B1_3", "N", 16.0, "gbi_B1_3, by a door")
    S.onward = on
    spots(S, (4.0, 25.6, (0, -1)), [(-22.0, -18.0), (22.0, 20.0), (8.0, -6.0)], (24.0, -12.0, (1, 0)),
          [(-10.0, 4.0), (22.0, 4.0), (-8.0, -19.0)], [(10.0, -18.0), (-18.0, -12.0), (0.0, -8.0)])
    S.label("POOL", 0.0, 2.0)
    S.corridor("south_walk", -16.0, 26.0, 12.4, 22.0)
    finish(S, holes, ((0.0, Y, 25.5), (0.0, -1.0), -4))
    return S


def gbi_B1_3():
    S = Scene("gbi_B1_3", "B1", 3, "Baths", "bath cells off a tiled corridor; the tide in the west bath, gas down the corridor")
    Y, holes = S.Y, {}
    arr = outer_door(S, holes, "from_B1_2", "S", -16.0, "gbi_B1_2 (back)")
    arrive_at(S, arr)
    S.part("Corridor_N", "x", 3.9, X0, X1, gaps=[(-20.0, 1.0, "door", "open"), (0.0, 2.4, "open"), (20.0, 1.0, "door", "closed")])
    S.part("Corridor_S", "x", 8.1, X0, X1, gaps=[(-16.0, 2.4, "open"), (0.0, 1.0, "door", "ajar"), (16.0, 1.0, "door", "closed")])
    S.part("Bath_N_W", "z", -13.0, Z0, 3.8)
    S.part("Bath_N_E", "z", 13.0, Z0, 3.8)
    S.part("Bath_S_W", "z", -8.0, 8.2, Z1)
    S.part("Bath_S_E", "z", 8.0, 8.2, Z1)
    for nm, (x0, x1, z0, z1) in {"W": (-24.0, -15.0, -20.0, -2.0), "M_W": (-11.0, -4.0, -6.0, 1.5), "M_E": (4.0, 11.0, -6.0, 1.5),
                                 "E": (15.0, 24.0, -20.0, -2.0), "SM": (-6.0, 6.0, 12.0, 24.0), "SE": (10.0, 24.0, 12.0, 24.0)}.items():
        S.zone("water", f"bath_{nm}", (x0, Y, z0), (x1, Y + 0.3, z1))
        S.decor(f"Bath_Water_{nm}", (x0, Y + 0.28, z0), (x1, Y + 0.3, z1), "water")
    hazard(S, "tide", 1, (-19.5, -11.0), (-19.5, -11.0), ([-4.5, 0.0, -9.0], [4.5, 0.05, 9.0]), (-24.0, -15.0, -20.0, -2.0, 1.6), "rise", 40.0,
           {"what": "the west bath floods to the ceiling's lip and drains"}, y_from=0.3, y_to=1.4)
    hazard(S, "gas", 1, (24.0, 6.0), (-24.0, 6.0), ([-2.0, 0.0, -2.0], [2.0, 2.6, 2.0]), (X0, X1, 4.0, 8.0, S.H), "drift", 30.0,
           {"what": "gas drifts west down the tiled corridor"})
    on = sky_hall(S, "to_B1_4", 0.0, "gbi_B1_4, through the painted-sky hall", "way on")
    S.onward = on
    vent(S, 1, "W", -10.0, 5.0, "gbi_B1_4 (shut: crawling is not in the game yet)")
    spots(S, (-12.0, 25.6, (0, -1)), [(20.0, -10.0), (0.0, 20.0), (16.0, 20.0)], (-22.0, 14.0, (-1, 0)),
          [(-20.0, -16.0), (8.0, -4.0), (20.0, 12.0)], [(6.0, -16.0), (20.0, -18.0), (-8.0, -10.0)])
    S.label("WEST BATH", -19.5, -1.0)
    S.label("EAST BATH", 19.5, -1.0)
    S.label("CORRIDOR", -8.0, 6.0)
    S.label("ENTRY", -17.0, 18.0)
    S.corridor("corridor", X0, X1, 4.0, 8.0)
    finish(S, holes, ((-24.5, Y, 6.0), (1.0, 0.0), -3))
    return S


def gbi_B1_4():
    S = Scene("gbi_B1_4", "B1", 4, "The drain", "wave 20, the run's end: a walkway round a flooding basin, a blade along the last dash, the EXIT hall out")
    Y, holes = S.Y, {}
    arr = outer_door(S, holes, "from_B1_3", "S", 0.0, "gbi_B1_3's painted-sky hall (back)", kind="hall door")
    arrive_at(S, arr)
    S.part("Basin_N", "x", -8.2, -14.3, 14.3, gaps=[(-6.0, 3.0, "open"), (6.0, 3.0, "open")], h=1.1, mat="trim")
    S.part("Basin_S", "x", 14.2, -14.3, 14.3, gaps=[(0.0, 3.0, "open")], h=1.1, mat="trim")
    S.part("Basin_W", "z", -14.2, -8.1, 14.1, gaps=[(3.0, 3.0, "open")], h=1.1, mat="trim")
    S.part("Basin_E", "z", 14.2, -8.1, 14.1, gaps=[(3.0, 3.0, "open")], h=1.1, mat="trim")
    S.zone("water", "basin", (-14.1, Y, -8.1), (14.1, Y + 0.3, 14.1))
    S.decor("Basin_Water", (-14.1, Y + 0.28, -8.1), (14.1, Y + 0.3, 14.1), "water")
    for xc in (-7.0, 7.0):
        for zc in (-1.0, 9.0):
            S.column(f"Column_{_tag(xc)}_{_tag(zc)}", xc, zc, 0.8)
    for xc in (-22.0, 22.0):
        for zc in (-14.0, -2.0, 10.0, 20.0):
            S.column(f"Column_{_tag(xc)}_{_tag(zc)}", xc, zc, 0.8)
    hazard(S, "tide", 1, (0.0, 3.0), (0.0, 3.0), ([-14.0, 0.0, -11.0], [14.0, 0.05, 11.0]), (-14.1, 14.1, -8.1, 14.1, 1.6), "rise", 35.0,
           {"what": "the basin floods over its rim onto the walkway and drains"}, y_from=0.3, y_to=1.4)
    hazard(S, "blade", 1, (-20.0, -10.0), (20.0, -10.0), blade_box_x(), (-20.8, 20.8, -11.2, -8.8 + 0.5, 1.4), "track", 10.0,
           {"what": "a chainsaw blade runs across in front of the EXIT hall"})
    S.decor("Blade_Slot_1", (-20.6, Y, -10.1), (20.6, Y + 0.005, -9.9), "trim")
    hazard(S, "blade", 2, (19.0, 22.0), (19.0, -6.0), blade_box(), (17.8, 20.2, -6.8, 22.8, 1.4), "track", 12.0,
           {"what": "a chainsaw blade runs the east walkway"})
    S.decor("Blade_Slot_2", (18.9, Y, -6.6), (19.1, Y + 0.005, 22.6), "trim")
    on = sky_hall(S, "to_overworld", 0.0, "the Overworld: the run is over (the results screen)", "way on")
    S.onward = on
    spots(S, (4.0, 25.6, (0, -1)), [(-22.0, 23.5), (22.0, -18.0), (-22.0, -18.0)], (-24.5, 4.0, (-1, 0)),
          [(0.0, 3.0), (24.0, 4.0), (-18.0, -4.0)], [(10.0, -16.0), (-10.0, -16.0), (24.0, -6.0), (-24.0, -6.0)])
    S.label("BASIN", 0.0, 4.0)
    S.label("WALKWAY", -18.0, 18.0)
    S.label("THE LAST DASH", 12.0, -12.6, kind="note")
    S.corridor("north_walk", -14.0, 14.0, -11.5, -8.4)
    S.corridor("west_walk", -21.4, -14.4, -8.0, 14.0)
    finish(S, holes, ((0.0, Y, 25.5), (0.0, -1.0), -4))
    return S


SCENES = {f.__name__: f for f in (gbi_L4_1, gbi_L4_2, gbi_L4_3, gbi_L3_2, gbi_L3_3, gbi_L3_4, gbi_L2_2, gbi_L2_3, gbi_L2_4,
                                  gbi_L1_2, gbi_L1_3, gbi_L1_4, gbi_B1_2, gbi_B1_3, gbi_B1_4)}
EXISTING = {"gbi_L4_4": ("L4", "world/gbi_L4_4.json"), "gbi_L3_1": ("L3", "world/gbi_L3_1.json"), "gbi_L2_1": ("L2", "world/L2.json"),
            "gbi_L1_1": ("L1", "world/L1.json"), "gbi_B1_1": ("B1", "world/B1.json")}   # the existing floors (read only, for the plans and the notes)
RUN = [f"gbi_{f}_{i}" for f in FLOORS for i in range(1, 5)]

# Every link between two chambers of this set: (scene, door) <-> (scene, door), and the connector.
PAIRS = [
    (("gbi_L4_1", "lift_to_L4_2"), ("gbi_L4_2", "lift_from_L4_1"), "elevator"),
    (("gbi_L4_2", "exit_to_L4_3"), ("gbi_L4_3", "from_L4_2"), "painted-sky hall"),
    (("gbi_L3_2", "to_L3_3"), ("gbi_L3_3", "from_L3_2"), "door"),
    (("gbi_L3_3", "lift_to_L3_4"), ("gbi_L3_4", "lift_from_L3_3"), "elevator"),
    (("gbi_L2_2", "exit_to_L2_3"), ("gbi_L2_3", "from_L2_2"), "painted-sky hall"),
    (("gbi_L2_3", "to_L2_4"), ("gbi_L2_4", "from_L2_3"), "door"),
    (("gbi_L1_2", "lift_to_L1_3"), ("gbi_L1_3", "lift_from_L1_2"), "elevator"),
    (("gbi_L1_3", "exit_to_L1_4"), ("gbi_L1_4", "from_L1_3"), "painted-sky hall"),
    (("gbi_B1_2", "to_B1_3"), ("gbi_B1_3", "from_B1_2"), "door"),
    (("gbi_B1_3", "exit_to_B1_4"), ("gbi_B1_4", "from_B1_3"), "painted-sky hall"),
]

# Links whose other side is not in this set: an existing chamber (its file is the coordinator's: tools/make_chambers.mjs), the Overworld, or the
# run's start. (scene, door): (connector, the other side, the proposal for it). Arrive points on the existing floors are the store's own.
OUTSIDE = {
    ("gbi_L4_3", "exit_to_L4_4"): ("painted-sky hall", "gbi_L4_4",
                                   "new in gbi_L4_4: you come in by the store's sealed glass doors and stand just inside them, at (0, 9.6, 25.6) "
                                   "facing north (0, -1) [proposal]; back: F there returns to this hall's EXIT end"),
    ("gbi_L3_2", "stair_from_L3_1"): ("stair door", "gbi_L3_1",
                                      "gbi_L3_1's own stair door down, DoorLeaf_Stair_L2_L3_down (unlinked in gbi today), leads here [proposal: "
                                      "in Going back in the floor's real stairs down are its chamber 1's way on]; back: arrive in gbi_L3_1 at "
                                      "(-16.478, 6.4, -15.078) facing (0, -1), where the store's L2 link arrives"),
    ("gbi_L3_4", "stair_down"): ("stair door", "gbi_L2_1",
                                 "the stairs arrive in L2's real stairwell: (-16.478, 6.4, -14.278) facing (0, 1), where the store's L3 stair door "
                                 "down arrives; back: gbi_L2_1's DoorLeaf_Stair_L2_L3_up leads here"),
    ("gbi_L2_2", "stair_from_L2_1"): ("stair door", "gbi_L2_1",
                                      "gbi_L2_1's own stair door down, DoorLeaf_Stair_L1_L2_down, leads here [proposal]; back: arrive in "
                                      "gbi_L2_1 at (-0.007, 3.2, 10.508) facing (0, 1)"),
    ("gbi_L2_4", "stair_down"): ("stair door", "gbi_L1_1",
                                 "the stairs arrive in L1's real stairwell: (-0.007, 3.2, 9.708) facing (0, -1), where the store's L2 stair door "
                                 "down arrives; back: gbi_L1_1's DoorLeaf_Stair_L1_L2_up leads here"),
    ("gbi_L1_2", "stair_from_L1_1"): ("stair door", "gbi_L1_1",
                                      "gbi_L1_1's own stair door down, DoorLeaf_Stair_B1_L1_down, leads here [proposal]; back: arrive in "
                                      "gbi_L1_1 at (0.009, 0.0, -0.799) facing (0, 1)"),
    ("gbi_L1_4", "stair_down"): ("stair door", "gbi_B1_1",
                                 "the stairs arrive in B1's real stairwell: (0.009, 0.0, -1.599) facing (0, -1), where the store's L1 stair door "
                                 "down arrives; back: gbi_B1_1's DoorLeaf_Stair_B1_L1_up leads here"),
    ("gbi_B1_2", "from_B1_1"): ("door", "gbi_B1_1",
                                "B1 has no second door: gbi_B1_1 needs a new one for its way on (open question; proposal: a painted-sky hall "
                                "from the kit on B1's north wall); back: F at this door returns there"),
    ("gbi_B1_4", "exit_to_overworld"): ("painted-sky hall", "overworld",
                                        "the run's end: the EXIT hall takes you out to the Overworld's results screen and the lot, as the "
                                        "Original's walk-out does [proposal]"),
}
START = ("gbi_L4_1", "Marker_Arrival: Going back in starts here, from the options screen at the store's glass doors (the manifest's "
         "startChamber moves from gbi_L4_4 to gbi_L4_1)")


def build(sid):
    return SCENES[sid]()


# ---------------------------------------------------------------- the layout file as the exporter writes it, from the model alone (--preview)
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
    b = Path(path).read_bytes()
    n = struct.unpack_from("<I", b, 12)[0]
    doc = json.loads(b[20:20 + n].decode("utf-8"))
    return {nd.get("name", ""): {"extras": nd.get("extras", {}), "t": nd.get("translation", [0.0, 0.0, 0.0])} for nd in doc.get("nodes", [])}


def _blocked(cols, p, r=WALKER_R):
    x, y, z = p
    for c in cols:
        if c["min"][1] < y + 1.5 and c["max"][1] > y + 0.5 and c["min"][0] - r < x < c["max"][0] + r and c["min"][2] - r < z < c["max"][2] + r:
            return c
    return None


def _overlap(a, b):
    v = 1.0
    for i in range(3):
        d = min(a["max"][i], b["max"][i]) - max(a["min"][i], b["min"][i])
        if d <= 0:
            return 0.0
        v *= d
    return v


def reach_grid(S, cols, step=0.2):
    """Flood fill on a step-metre grid at the chamber's floor: a cell is open when a walker (WALKER_R) standing on its centre touches no
    collider between knee and head height (as shared/worlddoc.js's blocked()). Door leaves are not colliders, so a doorway is open."""
    nx, nz = int(round((X1 - X0) / step)), int(round((Z1 - Z0) / step))
    Y = S.Y
    grid = bytearray(nx * nz)                                         # 1 = blocked
    r = WALKER_R
    for c in cols:
        if not (c["min"][1] < Y + 1.5 and c["max"][1] > Y + 0.5):
            continue
        i0 = max(0, int(math.floor((c["min"][0] - r - X0) / step - 0.5)) + 1)
        i1 = min(nx - 1, int(math.ceil((c["max"][0] + r - X0) / step - 0.5)) - 1)
        k0 = max(0, int(math.floor((c["min"][2] - r - Z0) / step - 0.5)) + 1)
        k1 = min(nz - 1, int(math.ceil((c["max"][2] + r - Z0) / step - 0.5)) - 1)
        for i in range(i0, i1 + 1):
            x = X0 + (i + 0.5) * step
            if not (c["min"][0] - r < x < c["max"][0] + r):
                continue
            for k in range(k0, k1 + 1):
                z = Z0 + (k + 0.5) * step
                if c["min"][2] - r < z < c["max"][2] + r:
                    grid[k * nx + i] = 1

    def cell(p):
        return min(nx - 1, max(0, int((p[0] - X0) / step))), min(nz - 1, max(0, int((p[2] - Z0) / step)))

    def fill(start):
        seen = bytearray(nx * nz)
        i, k = cell(start)
        best = None
        for di in range(-2, 3):                                       # start on the nearest open cell
            for dk in range(-2, 3):
                ii, kk = i + di, k + dk
                if 0 <= ii < nx and 0 <= kk < nz and not grid[kk * nx + ii]:
                    dd = di * di + dk * dk
                    if best is None or dd < best[0]:
                        best = (dd, ii, kk)
        if best is None:
            return seen
        todo = [(best[1], best[2])]
        seen[best[2] * nx + best[1]] = 1
        while todo:
            i, k = todo.pop()
            for ii, kk in ((i + 1, k), (i - 1, k), (i, k + 1), (i, k - 1)):
                if 0 <= ii < nx and 0 <= kk < nz:
                    j = kk * nx + ii
                    if not grid[j] and not seen[j]:
                        seen[j] = 1
                        todo.append((ii, kk))
        return seen

    def reached(seen, p):
        i, k = cell(p)
        for di in range(-2, 3):
            for dk in range(-2, 3):
                ii, kk = i + di, k + dk
                if 0 <= ii < nx and 0 <= kk < nz and seen[kk * nx + ii]:
                    return True
        return False
    return fill, reached


def check(base, ids=None, glb_dir=None):
    ids = ids or list(SCENES)
    docs, bad = {}, []
    for sid in ids:
        f = out_path(base, sid)
        if not f.exists():
            bad.append(f"missing {f}")
            continue
        docs[sid] = json.loads(f.read_text())
    models = {sid: build(sid) for sid in ids}
    # ---- links both ways
    have = {(sid, l["door"]) for sid, d in docs.items() for l in d.get("links", [])}
    paired = set()
    for a, b, kind in PAIRS:
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
    print(f"GATE links: {len(PAIRS)} pairs inside the set ({len(PAIRS) * 2} sides, both present), {len(OUTSIDE)} that leave it; {len(have)} links in "
          f"the files, every one accounted for")
    for side in sorted(OUTSIDE):
        kind, other, note = OUTSIDE[side]
        print(f"  off this set: {side[0]}.{side[1]} ({kind}) -> {other}")
    # ---- one arrival and one way on, and the run is one chain
    chain = []
    for sid in ids:
        S, d = models[sid], docs.get(sid)
        if d is None:
            continue
        doors = {l["door"] for l in d["links"]}
        want = {S.onward} | ({S.arrival[0]} if S.arrival[0] else set())
        spawn = [m for m in d["markers"] if m["kind"] == "Spawn"]
        if doors != want:
            bad.append(f"{sid}: links {sorted(doors)}, want exactly the arrival and the way on {sorted(want)}")
        if S.arrival[0] is None and (sid != START[0] or len(spawn) != 1):
            bad.append(f"{sid}: no arrival link and not the run's start")
        if sid == START[0] and S.arrival[0] is not None:
            bad.append(f"{sid}: the run's start should arrive by its Marker_Arrival")
        chain.append(sid)
    nxt = {"gbi_L4_4": "gbi_L3_1"}                                   # built: gbi.gbi_L4_4.stairs_down
    for a, b, kind in PAIRS:
        nxt[a[0]] = b[0]
    for (s, dd), (kind, other, note) in OUTSIDE.items():
        if s not in models:
            continue
        if models[s].onward == dd:
            nxt[s] = other                                           # this chamber's way on leaves the set
        elif models[s].arrival[0] == dd:
            nxt[other] = s                                           # an existing chamber's way on (proposed) arrives here
    walk, s = [START[0]], START[0]
    while s in nxt and len(walk) < 40:
        s = nxt[s]
        walk.append(s)
    run_ok = [w for w in walk if w in RUN] == RUN and walk[-1] == "overworld"
    if not run_ok:
        bad.append(f"the run's chain is {walk}")
    print(f"GATE one arrival and one way on: {len(chain)} chambers, each with exactly its arrival and its way on (gbi_L4_1 arrives by its "
          f"spawn); the chain runs {' > '.join(w.replace('gbi_', '') for w in walk)}")
    # ---- spots
    want = {"locker": 1, "loot": 1, "puzzle": 1, "object": 1, "monster": 1}
    safe_kinds = ("shop", "stash", "save", "craft", "respawn", "locker")
    nsafe = 0
    for sid, d in docs.items():
        S = models[sid]
        own = [s for s in d["spots"] if s.get("of") != "safe_house"]
        for k, n in want.items():
            c = sum(1 for s in own if s["kind"] == k)
            if (k == "locker" and c != 1) or c < n:
                bad.append(f"{sid}: {c} Spot_{k}")
        if S.safe:
            nsafe += 1
            sh = [s for s in d["spots"] if s.get("of") == "safe_house"]
            for k in safe_kinds:
                if sum(1 for s in sh if s["kind"] == k) != 1:
                    bad.append(f"{sid}: safe house Spot_{k} missing")
            if not any(z["kind"] == "safe" for z in d["zones"]):
                bad.append(f"{sid}: safe house has no Zone_safe")
    floors_safe = sorted({models[s].floor for s in docs if models[s].safe})
    if len(floors_safe) != 5 or nsafe != 5:
        bad.append(f"safe houses: {nsafe} on floors {floors_safe}")
    print(f"GATE spots: every chamber has Spot_locker x1 and at least one Spot_loot, Spot_puzzle, Spot_object and Spot_monster; {nsafe} safe "
          f"houses ({', '.join(floors_safe)}) each with shop, stash, save, craft, respawn, locker and a Zone_safe")
    # ---- monster distance
    worst = 99.0
    for sid, d in docs.items():
        ax, _, az = models[sid].arrival[1]
        for s in d["spots"]:
            if s["kind"] == "monster":
                dd = math.hypot(s["position"][0] - ax, s["position"][2] - az)
                worst = min(worst, dd)
                if dd < MONSTER_MIN:
                    bad.append(f"{sid}: {s['name']} is {dd:.1f} m from the arrival")
    print(f"GATE monster distance: every Spot_monster at least {MONSTER_MIN:g} m from its chamber's arrival (the nearest {worst:.1f} m)")
    # ---- footprints
    nf = 0
    for sid, d in docs.items():
        S = models[sid]
        for c in d["colliders"]:
            nf += 1
            if c["min"][0] < FOOT[0] - 1e-3 or c["max"][0] > FOOT[1] + 1e-3 or c["min"][2] < FOOT[2] - 1e-3 or c["max"][2] > FOOT[3] + 1e-3:
                bad.append(f"{sid}: {c['s']} leaves the footprint")
            if c["min"][1] < S.Y - 0.3 - 1e-3 or c["max"][1] > S.Y + S.H + 0.5 + 1e-3:           # the kit's 0.3 m floors and 3.25 m sky hall
                bad.append(f"{sid}: {c['s']} leaves the storey (y {c['min'][1]} to {c['max'][1]})")
        for k in ("links", "spots", "markers"):
            for e in d[k]:
                for p in ([e["at"], e["arrive"]] if k == "links" else [e["position"]]):
                    if abs(p[1] - S.Y) > 1e-3 or not (X0 < p[0] < X1 and Z0 < p[2] < Z1):
                        bad.append(f"{sid}: {e.get('name', e.get('door'))} at {p} is not on the chamber's floor")
    print(f"GATE footprints: {nf} colliders, every one inside x {FOOT[0]} to {FOOT[1]}, z {FOOT[2]} to {FOOT[3]} and its storey; every link, "
          f"spot and marker on its chamber's floor (B1 -3, L1 0, L2 3.2, L3 6.4, L4 9.6)")
    # ---- overlaps: no two solids share space (the floor and ceiling slabs, and a kit piece's own boxes, aside)
    nov = 0
    for sid in docs:
        S = models[sid]
        tags = {b["name"]: b["tags"] for b in S.boxes if b["col"]}
        cols = [c for c in docs[sid]["colliders"] if "slab" not in tags.get(c["s"], set())]
        nov += len(cols)
        for i, a in enumerate(cols):
            ka = next((t for t in tags.get(a["s"], ()) if t.startswith("kit:")), None)
            for b in cols[i + 1:]:
                kb = next((t for t in tags.get(b["s"], ()) if t.startswith("kit:")), None)
                if ka and ka == kb:
                    continue
                v = _overlap(a, b)
                if v > 1e-4:
                    bad.append(f"{sid}: {a['s']} and {b['s']} overlap ({v:.4f} m3)")
    print(f"GATE overlaps: {nov} standing colliders, no two sharing space (floor and ceiling slabs, and a kit piece's boxes among themselves, aside)")
    # ---- clearances: standing points (as tools/worlddoc.mjs), each door's two sides, the corridors
    ndoor, ncor, narrow = 0, 0, 99.0
    for sid, d in docs.items():
        S = models[sid]
        cols = d["colliders"]
        ctag = {b["name"]: b["tags"] for b in S.boxes if b["col"]}
        for l in d["links"]:
            for p, what in ((l["at"], "at"), (l["arrive"], "arrive")):
                b = _blocked(cols, p)
                if b:
                    bad.append(f"{sid}: link {l['door']} {what} {p} is inside {b['s']}")
        for s in d["spots"]:
            b = _blocked(cols, s["position"])
            if b:
                bad.append(f"{sid}: {s['name']} is inside {b['s']}")
        for dr in d["doors"]:
            ndoor += 1
            th = math.radians(dr["closed_yaw_deg"])
            rx, rz = math.cos(th), -math.sin(th)
            mx = dr["hinge"][0] + rx * dr["width"] / 2
            mz = dr["hinge"][2] + rz * dr["width"] / 2
            for sgn in (1, -1):
                px, pz = mx + sgn * (-rz) * 0.7, mz + sgn * rx * 0.7
                if not (X0 < px < X1 and Z0 < pz < Z1):
                    continue
                if dr.get("kind") == "vent":
                    continue
                b = _blocked(cols, (px, S.Y, pz), r=0.2)
                dk = next((d0.get("kit") for d0 in S.doors if d0["name"] == dr["name"]), None)
                if b and not (dk and f"kit:{dk}" in ctag.get(b["s"], set())):
                    bad.append(f"{sid}: {dr['name']} has {b['s']} within 0.7 m of its {'front' if sgn > 0 else 'back'}")
        for c in S.corridors:
            ncor += 1
            w = min(c["max"][0] - c["min"][0], c["max"][2] - c["min"][2])
            narrow = min(narrow, w)
            if w < MIN_CORRIDOR - 1e-6:
                bad.append(f"corridor {sid}/{c['name']} is {w:.2f} m wide")
            for k in cols:
                e = 0.005
                if k["min"][1] < S.Y + 1.5 and k["max"][1] > S.Y + 0.5 and k["min"][0] < c["max"][0] - e and k["max"][0] > c["min"][0] + e \
                        and k["min"][2] < c["max"][2] - e and k["max"][2] > c["min"][2] + e:
                    bad.append(f"corridor {sid}/{c['name']}: {k['s']} stands in it")
                    break
    print(f"GATE clearances: every link's two points and every spot clear of the colliders (walker radius {WALKER_R} m); {ndoor} doors, each with "
          f"0.7 m clear on both sides inside the chamber; {ncor} corridors and aisles, the narrowest {narrow:.2f} m (at least {MIN_CORRIDOR} m), none blocked")
    # ---- every spot, the way on and the safe house reachable from the arrival
    nreach = 0
    for sid, d in docs.items():
        S = models[sid]
        fill, reached = reach_grid(S, d["colliders"])
        seen = fill(S.arrival[1])
        targets = [(l["door"], l["at"]) for l in d["links"]] + [(s["name"], s["position"]) for s in d["spots"] if s["kind"] != "vent"]
        for nm, p in targets:
            nreach += 1
            if not reached(seen, p):
                bad.append(f"{sid}: {nm} at {p} cannot be walked to from the arrival")
    print(f"GATE reachable: from each chamber's arrival a walker reaches the way on and every spot ({nreach} points), doors open")
    # ---- hazards
    kinds, nh = {}, 0
    for sid, d in docs.items():
        S = models[sid]
        zones = {z["name"]: z for z in d["zones"]}
        if not S.hazards:
            bad.append(f"{sid}: no hazard")
        for h in S.hazards:
            nh += 1
            kinds[h["kind"]] = kinds.get(h["kind"], 0) + 1
            ends = [s for s in d["spots"] if s.get("hazard") == h["name"]]
            z = zones.get(h["zone"])
            if len(ends) != 2 or {s.get("end") for s in ends} != {"a", "b"}:
                bad.append(f"{sid}: {h['name']} has {len(ends)} travel ends")
            if z is None:
                bad.append(f"{sid}: {h['name']} has no {h['zone']}")
            else:
                for s in ends:
                    p = s["position"]
                    if not (z["min"][0] - 1e-3 <= p[0] <= z["max"][0] + 1e-3 and z["min"][2] - 1e-3 <= p[2] <= z["max"][2] + 1e-3):
                        bad.append(f"{sid}: {s['name']} is outside {h['zone']}")
    if set(kinds) != set(HAZARD_KINDS):
        bad.append(f"hazard kinds used: {sorted(kinds)}")
    print(f"GATE hazards: {nh} hazards, every chamber with at least one; each a Hazard_<kind>_<n> part with its two travel ends "
          f"(Spot_hazard_..._a/_b) inside its Zone_hazard; kinds: " + ", ".join(f"{k} x{kinds.get(k, 0)}" for k in HAZARD_KINDS))
    # ---- steps: the islands' kerbs
    nk, wr = 0, 0.0
    for sid, d in docs.items():
        cols = {c["s"]: c for c in d["colliders"]}
        for kb in models[sid].kerbs:
            nk += 1
            r = cols[kb["name"]]["max"][1] - kb["from"]
            wr = max(wr, r)
            if r > MAX_RISE + 1e-6:
                bad.append(f"{sid}: kerb {kb['name']} rises {r:.3f} m")
    print(f"GATE steps: {nk} kerbs (the display islands), the highest rise {wr:.3f} m (at most {MAX_RISE} m); no flights in these chambers")
    # ---- the hazards' parts in the GLBs, on their origins
    dirs = [Path(glb_dir)] if glb_dir else [Path(base) / "glb", Path(base) / "docs/renders/gbi_greybox/glb"]
    gl = [d for d in dirs if d.exists() and any(d.glob("gbi_*.glb"))]
    if not gl:
        print("GATE hazard parts: no GLBs next to the layout files (a --preview run): skipped")
    else:
        off, n = [], 0
        for sid in docs:
            g = gl[0] / f"{sid}.glb"
            if not g.exists():
                off.append(f"{sid}.glb missing")
                continue
            nodes = glb_nodes(g)
            for h in models[sid].hazards:
                n += 1
                nd = nodes.get(h["name"])
                if nd is None:
                    off.append(f"{h['name']} missing from {sid}.glb")
                elif max(abs(nd["t"][i] - h["origin"][i]) for i in range(3)) > 0.002:
                    off.append(f"{sid}.glb {h['name']} at {nd['t']}, origin {h['origin']}")
                elif nd["extras"].get("hazard") != h["name"]:
                    off.append(f"{sid}.glb {h['name']} has no hazard property")
        if off:
            bad.append("hazard parts: " + "; ".join(off))
        print(f"GATE hazard parts: {n - len(off)} of {n} Hazard_<kind>_<n> nodes in the chambers' GLBs, each its own object on its origin")
    # ---- the Blender export against the model (when the files came from Blender)
    same, diff = 0, []
    for sid, d in docs.items():
        m = doc_of(models[sid])
        if json.dumps(m, sort_keys=True) == json.dumps(d, sort_keys=True):
            same += 1
        else:
            for k in ("colliders", "doors", "markers", "links", "zones", "spots"):
                if json.dumps(m[k], sort_keys=True) != json.dumps(d[k], sort_keys=True):
                    diff.append(f"{sid}.{k}")
    print(f"GATE model: {same} of {len(docs)} files exactly as the model says" + (f" (differs: {', '.join(diff[:8])})" if diff else ""))
    if diff:
        bad.append("files differ from the model: " + ", ".join(diff[:12]))
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
    base = Path(a[a.index("--out") + 1]) if "--out" in a else ROOT / "work/gbi_greybox"
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
            m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
            c = COLORS.get(name, (0.5, 0.5, 0.5))
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
            bsdf.inputs["Roughness"].default_value = 0.15 if name == "M_Water" else 0.8
            if name in ("M_Fluorescent", "M_GBI_hazard_lava"):
                for key in ("Emission Color", "Emission"):
                    if key in bsdf.inputs:
                        bsdf.inputs[key].default_value = (*c, 1.0)
                        break
                if "Emission Strength" in bsdf.inputs:
                    bsdf.inputs["Emission Strength"].default_value = 1.5
            if name in ("M_Water", "M_GBI_hazard_gas") and "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = 0.55
            mats[name] = m
        return mats[name]

    def cube(mname):
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
    leaf_me.materials.append(mat("M_D_door"))

    sc = bpy.context.scene
    coll = {}

    def clear():
        for ob in list(bpy.data.objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        for c in list(bpy.data.collections):
            bpy.data.collections.remove(c)
        for lt in list(bpy.data.lights):
            bpy.data.lights.remove(lt)
        for cm in list(bpy.data.cameras):
            bpy.data.cameras.remove(cm)
        for me in list(bpy.data.meshes):
            if me.users == 0 and me.name.startswith("GB_hazard_"):
                bpy.data.meshes.remove(me)
        coll.clear()
        for cn in ("Art", "Layout", "Hazards"):
            c = bpy.data.collections.new(cn)
            sc.collection.children.link(c)
            coll[cn] = c

    def boxobj(name, b, coll_name, mname, hide=False):
        ob = bpy.data.objects.new(name, cube(mname))
        mn, mx = b["min"], b["max"]
        ob.location = (mn[0], -mx[2], mn[1])
        ob.scale = (mx[0] - mn[0], mx[2] - mn[2], mx[1] - mn[1])
        coll[coll_name].objects.link(ob)
        ob.hide_render = hide
        return ob

    def hazard_obj(S, h):
        """Hazard_<kind>_<n>: one mesh, its vertices relative to its origin (the travel's start), the object at the origin."""
        mn, mx = h["box"]
        org = h["origin"]
        piv = B(org)
        vs = [tuple(B((org[0] + x, org[1] + y, org[2] + z)) - piv) for x in (mn[0], mx[0]) for y in (mn[1], mx[1]) for z in (mn[2], mx[2])]
        me = bpy.data.meshes.new("GB_hazard_" + h["name"])
        me.from_pydata(vs, [], [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
        me.materials.append(mat(matname(S.floor, h["kind"])))
        me.validate()
        me.update()
        ob = bpy.data.objects.new(h["name"], me)
        ob.location = piv
        for k, val in h["props"].items():
            ob[k] = val
        ob["travel_a"] = [round(v, 3) for v in h["a"]]
        ob["travel_b"] = [round(v, 3) for v in h["b"]]
        ob["zone"] = h["zone"]
        coll["Hazards"].objects.link(ob)
        return ob

    def realize(S):
        clear()
        arts = []
        for b in S.boxes:
            mname = matname(S.floor, b["mat"])
            if b.get("zone"):
                ob = boxobj(b["name"], b, "Layout", mname, hide=True)
                ob.display_type = "WIRE"
                continue
            if b.get("art", True):
                ob = boxobj(b["name"], b, "Art", mname)
                ob["mat_role"] = b["mat"]
                arts.append((ob, b))
            if b["col"]:
                ob = boxobj("COL_" + b["name"], b, "Layout", mname, hide=True)
                ob.display_type = "WIRE"
        for h in S.hazards:
            arts.append((hazard_obj(S, h), {"name": h["name"]}))
        for d in S.doors:
            ob = bpy.data.objects.new(d["name"], leaf_me)
            ob.matrix_world = Matrix.Translation(B(d["hinge"])) @ Matrix.Rotation(d["yaw"], 4, "Z") @ Matrix.Diagonal((d["props"]["width"], 1, d["props"]["height"], 1))
            for k, val in d["props"].items():
                ob[k] = val
            coll["Art"].objects.link(ob)
            arts.append((ob, {"name": d["name"]}))
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

    def add_light(kind, loc, power, name, size=0.3):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = power
        ld.shadow_soft_size = size
        ob = bpy.data.objects.new(name, ld)
        ob.location = loc
        sc.collection.objects.link(ob)
        return ob

    def render_still(S, arts, path):
        for ob in list(bpy.data.objects):
            if ob.type in ("LIGHT", "CAMERA"):
                bpy.data.objects.remove(ob, do_unlink=True)
        world((0.6, 0.6, 0.62), 0.35)
        for x in range(-20, 21, 10):                                  # a grid of ceiling lights, greybox only (the bake comes with dressing)
            for z in range(-18, 25, 10):
                add_light("POINT", B((x, S.Y + S.H - 0.4, z)), STILL_POWER[S.floor], f"L_{x}_{z}", size=0.6)
        (pos, face, pitch) = S.still
        add_light("POINT", B((pos[0], S.Y + S.H - 0.4, pos[2])), STILL_POWER[S.floor] * 0.5, "L_cam", size=0.6)
        cd = bpy.data.cameras.new("Still_Cam")
        cam = bpy.data.objects.new("Still_Cam", cd)
        sc.collection.objects.link(cam)
        sc.camera = cam
        cam.data.lens, cam.data.sensor_width = 16.0, 36.0
        cam.data.clip_start, cam.data.clip_end = 0.05, 200.0
        cam.location = B((pos[0], pos[1] + EYE, pos[2]))
        ln = math.hypot(*face) or 1.0
        yaw = math.atan2(face[0] / ln, face[1] / ln)
        cam.rotation_euler = (math.radians(90 + pitch), 0, math.pi + yaw)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1600, 900, 100
        sc.cycles.samples = 48
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
    print("GBI_GREYBOX device", dev, "scenes", len(ids))
    for sid in ids:
        S = build(sid)
        arts = realize(S)
        p = out_path(base, sid)
        p.parent.mkdir(parents=True, exist_ok=True)
        export_scene.write(sid, p)
        export_glb(arts, base / "glb" / f"{sid}.glb")
        if render:
            render_still(S, arts, base / "renders" / f"{sid}_still.png")
        print(f"GBI_GREYBOX done {sid}: {len(S.boxes)} boxes, {len(S.hazards)} hazards, {len(S.doors)} doors, {len(S.empties)} empties")
    print("GBI_GREYBOX ALL DONE")


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
