"""The Right Door, Wrong Exit greybox (docs/BLENDER_AREAS.md, section 7, step 1): the seven rooms that exist, remade larger and psychedelic
(Phase A), the set pieces (Phase B: the finale's hide-and-seek map and the repeating room with its one-angle door), and the proposed new rooms
(Phase C, one line each in docs/renders/rdwe_greybox/ROOMS.md) as plain boxes, to scale, with the names the exporter reads (COL_, DoorLeaf_,
Marker_, Link_/Arrive_, SecCam_, Zone_, Spot_, decor_), so the owner can review the whole layout and the way the rooms join at once.
The method is tools/blender/build_overworld_greybox.py's and build_hotel_greybox.py's: one model in pure Python, three ways to run it.

    blender -b --factory-startup --python tools/blender/build_rdwe_greybox.py -- [--scenes all|A|B|C|id,id,...] [--out <dir>] [--no-render]
    python tools/blender/build_rdwe_greybox.py --check <dir> [--phase A|AB|ABC]   the gates on exported files, no Blender
    python tools/blender/build_rdwe_greybox.py --preview <dir> [--phase ...]      writes the layout files from the model alone, no Blender

For each scene the Blender run builds the boxes into an empty file, writes <out>/world/<scene>.json through tools/blender/export_scene.py,
the greybox art to <out>/glb/<scene>.glb, a top-down orthographic plan per level (<out>/renders/<scene>_plan_L<y>.png, ceilings and anything
2.4 m above the level hidden) and one eye-height still (1.55 m, <out>/renders/<scene>_still.png). The labels, scale bars, the connection graph
and the sheets are drawn afterwards by tools/blender/rdwe_greybox_sheets.py from this same model.

Coordinates are GAME coordinates (metres, y up, north = -z); Blender (x, y, z) is game (x, -z, y). Every scene has its own frame with its floor
at y = 0 (the hallway's well goes below it). Repetition reuses one mesh: every box is one unit cube per material, scaled, and every door leaf
is one leaf mesh. Each COL_<name> box has its art twin <name>; decor_ boxes have no collider; zones are hidden boxes.

The rules of section 7 are built in and gated:
- every door is different: each DoorLeaf_ has a `look` (form, finish, handle) no other door in the set has, and its own width and height;
- exits are fixed: each exit has exactly one Link_<door> (an exit that is not a door, such as the couch or the grate, is a Link_ alone), and
  a leaf with no link is a door that never opens (`opens: never`) or the arrival side of a link (`arrival_of`);
- there is no true exit: every room can reach every other (the finale aside, whose one way out is the ending), and the only links that leave
  the set are the way in (the forest house and the Overworld gate), the finale's ending, the Secret Operations door, and the six god rooms'
  reserved doors.
The six Greek-god rooms (Nyx, Selene, Hypnos, Morpheus, Oneiros, Thanatos) are built elsewhere; they have reserved doors here, not boxes.
Nothing here touches the manifest, index.html, shared/ or games/rdwe/.
"""
import json
import math
import random
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_scene  # noqa: E402  (camera_doc is pure Python; collect/write need Blender)

EYE = 1.55
T = 0.2                     # wall thickness
SLAB = 0.3                  # floor slab
DOOR_W, DOOR_H = 0.94, 2.16
MAX_RISE = 0.27
MIN_CORRIDOR = 1.6
WALKER_R = 0.28
MAX_EXTENT = 52.0           # a store floor: the most one indoor scene should be

MATS = {                    # flat greybox colours (linear RGB): psychedelic, so the owner sees each room's identity; no textures
    "floor": (0.55, 0.55, 0.53), "wall": (0.34, 0.34, 0.36), "ceiling": (0.66, 0.66, 0.64), "door": (0.62, 0.36, 0.16),
    "stair": (0.50, 0.46, 0.38), "furniture": (0.55, 0.47, 0.34), "void": (0.004, 0.004, 0.006), "lamp": (1.0, 0.85, 0.55),
    # dining: cream walls, green shag, maple, the dark green stairs
    "cream": (0.80, 0.70, 0.50), "shag": (0.08, 0.32, 0.06), "maple": (0.62, 0.36, 0.14), "china": (0.92, 0.92, 0.95),
    "stair_green": (0.04, 0.16, 0.05), "photo": (0.55, 0.38, 0.62),
    # hallway: grey-beige plaid, tan carpet, mossy pixel stone, amber
    "plaid": (0.55, 0.52, 0.44), "carpet_tan": (0.48, 0.36, 0.20), "moss": (0.14, 0.34, 0.10), "amber": (1.0, 0.55, 0.10),
    # teal rooms
    "teal": (0.02, 0.38, 0.36), "teal_cream": (0.85, 0.80, 0.62), "fleck": (0.26, 0.15, 0.08), "orange": (0.95, 0.30, 0.04),
    "cognac": (0.50, 0.18, 0.05), "plant": (0.10, 0.45, 0.10), "grid": (0.10, 1.0, 0.25), "window": (1.0, 0.95, 0.70),
    # flooded
    "tile": (0.88, 0.88, 0.84), "sky": (0.25, 0.50, 0.95), "water": (0.10, 0.40, 0.85), "red": (1.0, 0.05, 0.05),
    "rail": (0.70, 0.72, 0.75), "cardboard": (0.50, 0.36, 0.18), "frame": (0.40, 0.26, 0.12),
    # trampoline
    "pad": (0.98, 0.45, 0.12), "bed": (0.05, 0.05, 0.06), "yellow": (1.0, 0.85, 0.05), "concrete": (0.48, 0.48, 0.46),
    "truss": (0.12, 0.12, 0.14),
    # grocery
    "vinyl": (0.75, 0.74, 0.70), "shelf": (0.42, 0.44, 0.47), "cart": (0.90, 0.04, 0.04), "chrome": (0.80, 0.82, 0.85),
    # the set pieces and the new rooms: a loud palette
    "pink": (1.0, 0.25, 0.60), "violet": (0.45, 0.12, 0.85), "acid": (0.70, 1.0, 0.05), "cyan": (0.05, 0.85, 0.95),
    "magenta": (0.95, 0.05, 0.75), "lilac": (0.70, 0.55, 0.95), "mint": (0.45, 0.95, 0.70), "peach": (1.0, 0.62, 0.45),
    "sun": (1.0, 0.75, 0.10), "navy": (0.04, 0.06, 0.30), "blood": (0.40, 0.02, 0.04), "office": (0.62, 0.64, 0.60),
    "server": (0.06, 0.30, 0.12), "glass": (0.70, 0.85, 0.90), "steel": (0.55, 0.57, 0.60), "black": (0.03, 0.03, 0.035),
    "white": (0.92, 0.92, 0.92), "wood": (0.45, 0.28, 0.12), "statue": (0.85, 0.84, 0.80), "moon": (0.95, 0.95, 1.0),
    "washer": (0.90, 0.92, 0.95), "locker": (0.25, 0.45, 0.70), "map": (0.85, 0.80, 0.55), "book": (0.55, 0.12, 0.10),
}
EMISSIVE = {"lamp": 2.0, "amber": 3.0, "grid": 2.5, "window": 2.0, "red": 3.0, "sky": 0.8, "moon": 3.0, "sun": 1.5, "cyan": 0.6}


# ================================================================ the model (pure Python; no bpy)
class Scene:
    def __init__(s, sid, title, size, phase, line="", levels=(0.0,), mood="", cluster=""):
        s.id, s.title, s.size, s.phase, s.line, s.levels, s.mood, s.cluster = sid, title, size, phase, line, list(levels), mood, cluster
        s.boxes, s.empties, s.doors, s.labels, s.lights, s.corridors, s.flights, s.kerbs, s.cams = [], [], [], [], [], [], [], [], []
        s.links = {}            # door id -> text (where it goes), for the plan labels
        s.still = None          # (pos, face, pitch_deg)
        s.level_names = {}
        s.need_spots = {}       # kind -> how many at least (the "spots present" gate)
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

    def decor(s, name, mn, mx, mat="furniture", tags=()):
        n = s.uniq("decor_" + name)
        s.boxes.append({"name": n, "min": [float(v) for v in mn], "max": [float(v) for v in mx], "mat": mat, "col": False, "art": True, "tags": set(tags)})

    def zone(s, kind, name, mn, mx):
        n = s.uniq(f"Zone_{kind}_{name}")
        s.boxes.append({"name": n, "min": list(mn), "max": list(mx), "mat": "water", "col": False, "art": False, "zone": kind, "tags": set()})

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

    def seccam(s, n, pos, face, props=None):
        """A security camera, SecCam_<nn>: an empty on the wall, its -Y axis the way it looks (exported to `cameras`)."""
        s.cams.append({"name": f"SecCam_{n:02d}", "pos": [float(v) for v in pos], "face": face, "props": dict(props or {})})

    def leaf(s, name, hinge, run, into, width=DOOR_W, height=DOOR_H, state="closed", props=None):
        th = math.atan2(-run[1], run[0])
        op = math.atan2(-into[1], into[0])
        sw = 95.0 if math.sin(op - th) > 0 else -95.0
        p = {"width": round(width, 3), "height": round(height, 3), "closed_yaw_deg": round(math.degrees(th), 1), "swing_deg": sw, "state": state}
        p.update(props or {})
        s.doors.append({"name": s.uniq("DoorLeaf_" + name), "hinge": [float(v) for v in hinge], "yaw": th, "props": p})

    def label(s, text, x, z, y=0.0, kind="room"):
        s.labels.append({"text": text, "x": x, "z": z, "y": y, "kind": kind})

    def light(s, x, y, z, power=150.0):
        s.lights.append((x, y, z, power))

    def corridor(s, name, x0, x1, z0, z1, y=0.0):
        s.corridors.append({"name": name, "min": [x0, y, z0], "max": [x1, y, z1]})

    def kerb(s, box_name, y0):
        s.kerbs.append({"name": box_name, "from": y0})


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


def shell(S, nm, x0, x1, z0, z1, y0=0.0, h=3.0, holes=None, ceiling=True, floor=True, fmat="floor", wmat="wall", cmat="ceiling", sides="NSWE",
          wall_y0=None):
    """A room: floor slab (top at y0), ceiling, and the four walls OUTSIDE the interior [x0, x1] x [z0, z1]. holes: {side: [(a, w, hh, yb)]},
    a = the hole's centre along the wall, w its width, hh its height, yb its bottom above y0."""
    holes = holes or {}
    wy0 = y0 if wall_y0 is None else wall_y0

    def hs(side):
        return [(a - w / 2, a + w / 2, y0 + yb, y0 + yb + hh) for a, w, hh, yb in holes.get(side, [])]
    if floor:
        S.solid(f"{nm}_Floor", (x0 - T, y0 - SLAB, z0 - T), (x1 + T, y0, z1 + T), fmat)
    if ceiling:
        S.solid(f"{nm}_Ceiling", (x0 - T, y0 + h, z0 - T), (x1 + T, y0 + h + 0.2, z1 + T), cmat, ("ceiling",))
    if "N" in sides:
        wall(S, f"{nm}_Wall_N", "x", z0 - T, z0, x0 - T, x1 + T, wy0, y0 + h, hs("N"), wmat)
    if "S" in sides:
        wall(S, f"{nm}_Wall_S", "x", z1, z1 + T, x0 - T, x1 + T, wy0, y0 + h, hs("S"), wmat)
    if "W" in sides:
        wall(S, f"{nm}_Wall_W", "z", x0 - T, x0, z0, z1, wy0, y0 + h, hs("W"), wmat)
    if "E" in sides:
        wall(S, f"{nm}_Wall_E", "z", x1, x1 + T, z0, z1, wy0, y0 + h, hs("E"), wmat)


def flight(S, name, lane0, lane1, start, direction, axis, y_start, y_end, n, tread, mat="stair"):
    """n steps from a floor at y_start up to y_end, one box per step (each as thick as its rise, so the space under a flight stays open)."""
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


# ---------------------------------------------------------------- doors: every door different, every exit one Link_
FORMS = ["panelled", "flush", "louvred", "half-glazed", "ledged and braced", "round-topped", "studded", "quilted", "mirror-faced", "porthole",
         "six-panel", "stable (split)"]
FINISHES = ["oak", "teal paint", "mint paint", "pink laminate", "brushed steel", "cream gloss", "cherry red", "bottle green", "lilac", "black lacquer",
            "birch", "orange vinyl", "sky blue", "mustard", "plum"]
HANDLES = ["brass knob", "chrome lever", "push plate", "ring pull", "no handle", "glass knob"]
NLOOK = len(FORMS) * len(FINISHES) * len(HANDLES)          # 1080: enough that no two doors in the set need share a look
WIDTHS = [0.94, 0.86, 1.0, 0.9, 1.06, 0.82, 1.12]
HEIGHTS = [2.16, 2.04, 2.3, 2.1, 2.24, 2.4]


def _h(*parts):
    return zlib.crc32("|".join(parts).encode())


def door_size(sid, did):
    k = _h(sid, did)
    return WIDTHS[k % len(WIDTHS)], HEIGHTS[(k // 7) % len(HEIGHTS)]


def exitdoor(S, did, side, a, room, y=0.0, to="", width=None, height=None, look=None, fake=False, arrival_of=None, leaf=True,
             state="closed", link=True, at_in=0.75, arr_in=1.9, backing=True, props=None):
    """A door on wall `side` (N, S, W, E) of the room rect `room` = (x0, x1, z0, z1), centred on `a` along the wall, its floor at y.
    Returns the hole for shell(); adds the leaf (hinged on the wall's inner face, opening into the room, unless leaf=False), the Link_ and
    Arrive_ inside (F at at_in m from the wall, you arrive arr_in m in, facing into the room), and a black backing outside the hole."""
    w0, h0 = door_size(S.id, did)
    w = width or w0
    hh = height or h0
    x0, x1, z0, z1 = room
    p = {"exit": did} if not fake else {"opens": "never"}
    if arrival_of:
        p = {"arrival_of": arrival_of}
    if look:
        p["look"] = look
    p.update(props or {})
    if side == "N":
        c0, inward = z0, (0, 1)
    elif side == "S":
        c0, inward = z1, (0, -1)
    elif side == "W":
        c0, inward = x0, (1, 0)
    else:
        c0, inward = x1, (-1, 0)
    half = w / 2
    if leaf:
        if side == "N":
            S.leaf(did, (a - half, y, c0), (1, 0), (0, 1), w, hh, state, p)
        elif side == "S":
            S.leaf(did, (a + half, y, c0), (-1, 0), (0, -1), w, hh, state, p)
        elif side == "W":
            S.leaf(did, (c0, y, a + half), (0, -1), (1, 0), w, hh, state, p)
        else:
            S.leaf(did, (c0, y, a - half), (0, 1), (-1, 0), w, hh, state, p)
    if link and not fake:
        fx, fz = inward
        if side in "NS":
            S.link(did, (a, y, c0 + fz * at_in), (a, y, c0 + fz * arr_in), inward, to)
        else:
            S.link(did, (c0 + fx * at_in, y, a), (c0 + fx * arr_in, y, a), inward, to)
    if backing:                                            # the black past the door: never an open hole to nothing
        bw = w / 2 + 0.25
        if side == "N":
            S.solid(f"Beyond_{did}", (a - bw, y - 0.05, c0 - T - 0.35), (a + bw, y + hh + 0.15, c0 - T - 0.15), "void")
        elif side == "S":
            S.solid(f"Beyond_{did}", (a - bw, y - 0.05, c0 + T + 0.15), (a + bw, y + hh + 0.15, c0 + T + 0.35), "void")
        elif side == "W":
            S.solid(f"Beyond_{did}", (c0 - T - 0.35, y - 0.05, a - bw), (c0 - T - 0.15, y + hh + 0.15, a + bw), "void")
        else:
            S.solid(f"Beyond_{did}", (c0 + T + 0.15, y - 0.05, a - bw), (c0 + T + 0.35, y + hh + 0.15, a + bw), "void")
    return side, (a, w + 0.04, hh + 0.04, y)


def holes_of(hl, y0=0.0):
    out = {}
    for side, (a, w, hh, y) in hl:
        out.setdefault(side, []).append((a, w, hh, y - y0))
    return out


def auto_lights(S, x0, x1, z0, z1, y, step=7.0, power=140.0):
    nx, nz = max(1, round((x1 - x0) / step)), max(1, round((z1 - z0) / step))
    for i in range(nx):
        for j in range(nz):
            S.light(x0 + (i + 0.5) * (x1 - x0) / nx, y, z0 + (j + 0.5) * (z1 - z0) / nz, power)


# ================================================================ PHASE A: the seven rooms that exist, remade larger and psychedelic
def dining():
    S = Scene("rdwe_dining", "The Dining Room, the anchor", "16 m by 20 m, 4.2 m high (was 5.4 by 6.4 by 2.45); the stairwell climbs 3 m to "
              "the dark door", "A", line="Remade 3x: the giant round table, the photo wall, the china towers; the steep green stairs in the back wall.",
              levels=(0.0, 3.0), mood="the anchor: they said to wait in the dining room", cluster="spine")
    S.level_names = {0.0: "the room (y 0)", 3.0: "the top of the stairs (y 3)"}
    X, Z, H = 8.0, 10.0, 4.2
    R = (-X, X, -Z, Z)
    hl = [exitdoor(S, "house", "S", 0.0, R, to="the forest house's door, and the Overworld gate (the way in)", look="the front door: white "
                   "six-panel, a brass knocker, the guests never knocked"),
          exitdoor(S, "pantry", "E", -4.0, R, to="rdwe_long_table"),
          exitdoor(S, "loop", "W", 5.0, R, to="arrival only: the grocery's EXIT door comes back here (the loop)", arrival_of="rdwe_grocery.exit",
                   look="a door that was not there before: cream like the wall, no frame, no handle")]
    # the stairwell: a 1.6 m opening in the back wall, 12 steps of 0.25 up to a landing, the dark door at its end
    SX0, SX1 = -1.3, 0.3
    hl.append(("N", ((SX0 + SX1) / 2, SX1 - SX0, 3.4, 0.0)))
    shell(S, "Dining", -X, X, -Z, Z, h=H, holes=holes_of(hl), fmat="shag", wmat="cream", cmat="ceiling")
    zt = -Z - 12 * 0.36
    flight(S, "stairs", SX0, SX1, -Z, -1, "z", 0.0, 3.0, 12, 0.36, mat="stair_green")
    S.solid("Landing", (SX0, 2.7, zt - 1.6), (SX1, 3.0, zt), "stair_green")
    wall(S, "Well_W", "z", SX0 - T, SX0, zt - 1.6, -Z - T, 0.0, 5.6, (), "stair_green")
    wall(S, "Well_E", "z", SX1, SX1 + T, zt - 1.6, -Z - T, 0.0, 5.6, (), "stair_green")
    S.solid("Well_Ceiling", (SX0 - T, 5.6, zt - 1.6 - T), (SX1 + T, 5.8, -Z - T), "stair_green", ("ceiling",))
    top = (SX0, SX1, zt - 1.6, zt)
    hl2 = exitdoor(S, "stairs", "N", (SX0 + SX1) / 2, top, y=3.0, to="rdwe_hallway (the corridor the stairs never reached)", at_in=0.6,
                   arr_in=1.3, look="the dark door at the top of the stairs: a black panel, a hair of light round it", width=0.9, height=2.0)
    wall(S, "Well_N", "x", zt - 1.6 - T, zt - 1.6, SX0 - T, SX1 + T, 3.0, 5.6, [(hl2[1][0] - hl2[1][1] / 2, hl2[1][0] + hl2[1][1] / 2, 3.0,
                                                                              3.0 + hl2[1][2])], "stair_green")
    S.solid("Well_Under_Landing", (SX0, 0.0, zt - 1.6), (SX1, 2.7, zt), "stair_green")
    # the giant round table (object distortion: 4.4 m across, 1.25 m high) and four arrow-back chairs to match
    S.solid("Table", (-2.2, 0.0, -2.2), (2.2, 1.25, 2.2), "maple")
    for nm, cx, cz in (("N", 0.0, -3.4), ("S", 0.0, 3.4), ("W", -3.4, 0.0), ("E", 3.4, 0.0)):
        S.solid(f"Chair_{nm}", (cx - 0.6, 0.0, cz - 0.6), (cx + 0.6, 0.75, cz + 0.6), "maple")
        if cx:
            S.solid(f"Chair_{nm}_Back", (cx + (0.45 if cx > 0 else -0.6), 0.75, cz - 0.6), (cx + (0.6 if cx > 0 else -0.45), 2.4, cz + 0.6), "maple")
        else:
            S.solid(f"Chair_{nm}_Back", (cx - 0.6, 0.75, cz + (0.45 if cz > 0 else -0.6)), (cx + 0.6, 2.4, cz + (0.6 if cz > 0 else -0.45)), "maple")
    # the sideboard and its green lamp (west wall), the photo wall (north wall, west of the stairs), the china towers (east wall)
    S.solid("Sideboard", (-X, 0.0, -2.5), (-X + 0.9, 1.3, 1.5), "maple")
    S.decor("Lamp", (-X + 0.25, 1.3, -1.2), (-X + 0.65, 2.0, -0.8), "lamp")
    for k in range(6):
        S.decor(f"Photo_{k + 1}", (-7.0 + k * 0.95, 1.4 + (k % 2) * 0.5, -Z), (-6.4 + k * 0.95, 2.1 + (k % 2) * 0.5, -Z + 0.04), "photo")
    for k, (cz, hgt, dx) in enumerate(((5.0, 3.2, 0.0), (6.4, 2.6, 0.1), (7.8, 3.6, -0.1), (2.4, 2.2, 0.05))):
        S.solid(f"China_Tower_{k + 1}", (X - 0.9 + dx, 0.0, cz - 0.4), (X - 0.1 + dx, hgt, cz + 0.4), "china")
    S.decor("Curtains", (X - 0.06, 0.2, -8.0), (X, H - 0.2, -5.6), "white")
    S.spot("photo", 1, (-6.5, 0.0, -8.6), face=(0, -1), props={"what": "the photograph that changed: find it when the lamp clicks off"})
    S.spot("photo", 2, (-4.6, 0.0, -8.6), face=(0, -1), props={"what": "a second changing photograph"})
    S.spot("photo", 3, (-2.7, 0.0, -8.6), face=(0, -1), props={"what": "a third changing photograph"})
    S.spot("lamp", 1, (-6.4, 0.0, -1.0), face=(-1, 0), props={"what": "the green lamp: it clicks off every 28 s"})
    S.need_spots = {"photo": 3}
    S.marker("Spawn", (0.0, 0.0, 7.6), props={"what": "the first room: you start at the front, looking at the stairs"})
    S.label("DINING ROOM", 0.0, 5.2)
    S.label("table 4.4 m", 0.0, 0.0, kind="note")
    S.label("china towers", 6.4, 6.0, kind="note")
    S.label("photo wall", -4.6, -7.6, kind="note")
    S.label("sideboard + lamp", -5.6, 0.6, kind="note")
    S.label("stairs up 3 m", -0.5, -12.0, kind="note")
    S.label("the dark door", -0.5, -16.4, y=3.0)
    S.corridor("front", -6.0, 6.0, 5.5, 9.0)
    S.corridor("to_stairs", -1.4, 1.4, -9.8, -4.0)
    auto_lights(S, -X, X, -Z, Z, H - 0.4)
    S.still = ((0.0, 0.0, 9.0), (0.0, -1.0), -4)
    return S


def hallway():
    S = Scene("rdwe_hallway", "The Hallway, the descent", "a corridor 38 m by 3.2 m, 3.4 m high, from a lower landing up 6 steps; the mossy well "
              "goes 2 m down at the far end", "A", line="Remade wider and taller, 49 m end to end: the plaid corridor of doors that do not feel right; "
              "three of them open now.", levels=(0.0,), mood="the descent: the hum gets louder", cluster="spine")
    W2, H = 1.6, 4.6
    L0, C0, C1 = -4.0, 2.4, 40.0                     # the landing from x -4, the corridor floor (y 1.2) from 2.4 to 40, the well to 45
    E = 45.0
    R = (L0, E, -W2, W2)
    hl = [exitdoor(S, "dining", "W", 0.0, R, to="rdwe_dining (back down the green stairs)", look="the landing door: green baize, worn "
                   "through at the push plate")]
    yC = 1.2
    sides = {"door_a": ("N", 9.0, "rdwe_kids_bedroom"), "door_c": ("N", 21.0, "rdwe_door_hall"), "door_b": ("N", 33.0, "rdwe_upside_room")}
    for did, (sd, a, to) in sides.items():
        hl.append(exitdoor(S, did, sd, a, R, y=yC, to=to))
    for k, (sd, a) in enumerate((("S", 6.0), ("S", 15.0), ("N", 27.0), ("S", 24.0), ("S", 36.0), ("N", 15.0)), 1):
        hl.append(exitdoor(S, f"wrong_{k}", sd, a, R, y=yC, fake=True))
    shell(S, "Hall", L0, E, -W2, W2, h=H, holes=holes_of(hl), fmat="carpet_tan", wmat="plaid", wall_y0=-2.2, floor=False)
    S.solid("Landing_Floor", (L0, -SLAB, -W2), (C0, 0.0, W2), "carpet_tan")
    flight(S, "up", -W2, W2, 0.0, 1, "x", 0.0, yC, 6, 0.4, mat="carpet_tan")
    S.solid("Corridor_Floor", (C0, -2.2, -W2), (C1, yC, W2), "carpet_tan")
    # the well: 8 steps down 0.25 from the corridor floor, a landing at -0.8 at the end, mossy pixel-block stone
    flight(S, "well", -0.8, 0.8, C1 + 8 * 0.35, -1, "x", -0.8, yC, 8, 0.35, mat="moss")
    S.solid("Well_Landing", (C1 + 8 * 0.35, -2.2, -W2), (E, -0.8, W2), "moss")
    for nm, z0, z1 in (("N", -W2, -0.8), ("S", 0.8, W2)):
        S.solid(f"Well_Side_{nm}", (C1, -2.2, z0), (C1 + 8 * 0.35, yC, z1), "moss")
    S.solid("Well_Under", (C1, -2.2, -0.8), (C1 + 8 * 0.35, -0.8, 0.8), "moss")
    S.link("well", (E - 0.8, -0.8, 0.0), (E - 1.9, -0.8, 0.0), (-1, 0), "rdwe_teal (down the well, into the teal room)")
    S.decor("Amber_Bars", (C1 - 1.0, H - 0.25, -1.2), (E, H - 0.05, 1.2), "amber")
    for k in range(9):
        x = 4.0 + k * 4.0
        S.decor(f"Tube_{k + 1}", (x - 0.6, H - 0.12, -0.2), (x + 0.6, H - 0.04, 0.2), "lamp")
    S.spot("hum", 1, (24.0, yC, 0.0), face=(1, 0), props={"what": "the fluorescents flicker one at a time; the hum peaks here"})
    S.label("HALLWAY", 22.0, 0.0, y=yC)
    S.label("landing (y 0)", -2.0, 0.0, kind="note")
    S.label("well down to y -0.8", 43.0, 0.0, kind="note")
    S.corridor("corridor", 3.0, 39.5, -W2, W2, y=yC)
    for k in range(8):
        S.light(-2.0 + k * 6.3, H - 0.4, 0.0, 90)
    S.still = ((-2.6, 0.0, 0.0), (1.0, 0.0), 4)
    return S


def teal():
    S = Scene("rdwe_teal", "Teal Room, Square Door, the glitch", "14 m by 18 m, 4 m high (was 5.2 by 7.4 by 2.5)", "A",
              line="Remade 2.5x: the empty teal box, the giant orange angular sofa (sleep on it to go on), the black square doorway that "
                   "swallows light now leads somewhere.", mood="the glitch: no dust, the window's sun never moves", cluster="spine")
    X, Z, H = 7.0, 9.0, 4.0
    R = (-X, X, -Z, Z)
    hl = [exitdoor(S, "well", "S", -3.0, R, to="rdwe_hallway (up the well)", look="a low door at the foot of the well: mossy stone-grey, "
                   "iron ring"),
          exitdoor(S, "void", "N", 3.4, R, to="rdwe_void_room", width=1.4, height=2.9, state="closed",
                   look="the square doorway: no leaf, a slab of black flush with the wall that swallows light")]
    shell(S, "Teal", -X, X, -Z, Z, h=H, holes=holes_of(hl), fmat="fleck", wmat="teal", cmat="teal_cream")
    # the sofa: 5.6 m long, angular, against the back wall left of centre; F on the cushions is the way on (sleep)
    S.solid("Sofa_Base", (-5.6, 0.0, -Z), (0.0, 1.05, -Z + 2.2), "orange")
    S.solid("Sofa_Back", (-5.6, 1.05, -Z), (0.0, 2.3, -Z + 0.6), "orange")
    S.solid("Sofa_Arm_W", (-5.6, 1.05, -Z + 0.6), (-5.0, 1.6, -Z + 2.2), "orange")
    S.solid("Sofa_Arm_E", (-0.6, 1.05, -Z + 0.6), (0.0, 1.6, -Z + 2.2), "orange")
    S.link("sleep", (-2.8, 0.0, -Z + 2.75), (-2.8, 0.0, -Z + 3.8), (0, 1), "rdwe_teal2 (close your eyes on the couch, just for a minute)")
    S.decor("Fake_Window", (-X, 1.6, -1.6), (-X + 0.05, 3.2, 1.6), "window")
    S.solid("Plant", (X - 1.4, 0.0, -Z), (X - 0.2, 1.8, -Z + 1.2), "plant")
    S.spot("window", 1, (-X + 1.0, 0.0, 0.0), face=(-1, 0), props={"what": "the fake window: its sun never moves"})
    S.spot("watch", 1, (2.0, 0.0, 2.0), face=(0, -1), props={"what": "the watch whose second hand ticks backward"})
    S.label("TEAL ROOM", 0.0, 3.0)
    S.label("orange sofa (sleep)", -2.8, -6.0, kind="note")
    S.label("black square doorway", 3.4, -7.4, kind="note")
    S.corridor("floor", -4.0, 4.0, -3.0, 6.5)
    auto_lights(S, -X, X, -Z, Z, H - 0.4)
    S.still = ((-3.0, 0.0, 7.0), (0.25, -1.0), -3)
    return S


def teal2():
    S = Scene("rdwe_teal2", "Teal Room, Arched Door, the mutation", "8 m by 22 m, 5.5 m high (was 3.8 by 6.6 by 2.6): narrower and wrong", "A",
              line="Remade tall and narrow: wake by the cognac sofa, the arch that keeps growing, and the peeled wallpaper's green grid is a door.",
              mood="the mutation: the room breathes", cluster="spine")
    X, Z, H = 4.0, 11.0, 5.5
    R = (-X, X, -Z, Z)
    hl = [exitdoor(S, "arch", "N", 1.4, R, to="rdwe_flooded (through the arch before it finishes)", width=1.3, height=3.4, state="open",
                   look="the tall arch: round-topped, no leaf, it grows and snaps back"),
          exitdoor(S, "grid", "E", 3.0, R, to="rdwe_green_grid", look="a door under peeled wallpaper: the glowing green grid shows through")]
    shell(S, "Teal2", -X, X, -Z, Z, h=H, holes=holes_of(hl), fmat="fleck", wmat="teal", cmat="teal_cream")
    S.solid("Sofa", (-X, 0.0, -2.2), (-X + 1.0, 0.85, 2.2), "cognac")
    S.solid("Sofa_Back", (-X, 0.85, -2.2), (-X + 0.35, 1.5, 2.2), "cognac")
    S.link("sleep", (-X + 1.6, 0.0, 0.0), (-X + 2.2, 0.0, 1.0), (0.6, -0.8), "arrival only: you wake beside the sofa (from rdwe_teal's couch)")
    S.solid("Plant_Tall", (X - 1.0, 0.0, -Z), (X - 0.2, 3.2, -Z + 0.8), "plant")
    for k, cz in enumerate((-6.0, 6.0, -1.0), 1):
        S.decor(f"Peel_{k}", (X - 0.04, 1.2, cz - 0.6), (X, 2.6, cz + 0.6), "grid")
        S.spot("grid", k, (X - 1.0, 0.0, cz), face=(1, 0), props={"what": "wallpaper peeled back: the green grid under it"})
    S.label("TEAL ROOM, ARCHED", 0.0, 6.0)
    S.label("cognac sofa", -2.6, 0.0, kind="note")
    S.label("the arch", 1.4, -9.6, kind="note")
    S.corridor("length", -1.8, 1.8, -9.0, 9.0)
    auto_lights(S, -X, X, -Z, Z, H - 0.4, step=6.0)
    S.still = ((-1.6, 0.0, 1.0), (0.25, -1.0), 6)
    return S


def flooded():
    S = Scene("rdwe_flooded", "Flooded Corridor, the decay", "a corridor 50 m by 5 m, 4 m high (was 34 by 3.2 by 2.9), water over the floor", "A",
              line="Remade 1.5x: white tile and steel rails, the painted sky down the left, the empty frames down the right (one frame is a door), "
                   "the red door that never opens, the grate that gives way.", mood="the decay: the corridor groans", cluster="spine")
    X0, X1, Z, H = 0.0, 50.0, 2.5, 4.0
    R = (X0, X1, -Z, Z)
    hl = [exitdoor(S, "arch", "W", 0.0, R, to="arrival only: out of rdwe_teal2's arch", arrival_of="rdwe_teal2.arch",
                   look="the back of the arch, seen from the corridor: teal, round-topped, already sealing"),
          exitdoor(S, "frame", "S", 30.0, R, to="rdwe_changing_rooms", width=0.9, height=2.0,
                   look="an empty picture frame, door-sized, its canvas a door"),
          exitdoor(S, "red_door", "E", 0.0, R, fake=True, width=1.0, height=2.1, look="the red door: lit red, it never opens (the lure)")]
    shell(S, "Flooded", X0, X1, -Z, Z, h=H, holes=holes_of(hl), fmat="tile", wmat="tile", cmat="white")
    S.zone("water", "floor", (X0, 0.0, -Z), (X1, 0.08, Z))
    S.solid("Rail_N", (X0 + 1.0, 0.9, -Z + 0.05), (X1 - 1.0, 0.98, -Z + 0.12), "rail")
    for k, (r0, r1) in enumerate(((X0 + 1.0, 29.2), (30.8, X1 - 1.0)), 1):       # the south rail stops either side of the frame door
        S.solid(f"Rail_S_{k}", (r0, 0.9, Z - 0.12), (r1, 0.98, Z - 0.05), "rail")
    S.decor("Painted_Sky", (X0 + 1.0, 1.4, -Z), (X1 - 4.0, H - 0.2, -Z + 0.03), "sky")
    for k in range(14):
        x = 3.0 + k * 3.2
        if abs(x - 30.0) > 1.0:
            S.decor(f"Frame_{k + 1}", (x - 0.4, 1.6, Z - 0.03), (x + 0.4, 2.6, Z), "frame")
    for k, (x, hz) in enumerate(((6.0, 1.3), (11.0, 1.0), (17.5, 1.2)), 1):
        S.solid(f"Heap_{k}", (x - 1.2, 0.0, -Z + 0.15), (x + 1.2, hz, -Z + 1.5), "cardboard")
    S.decor("Grate", (X1 - 4.0, 0.0, -0.6), (X1 - 2.8, 0.09, 0.6), "black")
    S.link("grate", (X1 - 3.4, 0.0, 0.0), (X1 - 6.0, 0.0, 0.0), (1, 0), "rdwe_trampoline (the grate gives way: the fall down the shaft)")
    S.spot("photo", 1, (6.0, 0.0, -0.6), face=(0, -1), props={"what": "three photographs on the first heap: hang them in the frames"})
    S.spot("frame", 1, (12.6, 0.0, 1.4), face=(0, 1), props={"what": "an empty frame to hang a photograph in"})
    S.need_spots = {"photo": 1}
    S.label("FLOODED CORRIDOR", 24.0, 0.0)
    S.label("painted sky", 30.0, -1.6, kind="note")
    S.label("frames", 36.0, 1.6, kind="note")
    S.label("grate", 46.6, -1.3, kind="note")
    S.label("red door", 48.6, 1.6, kind="note")
    S.corridor("corridor", 2.0, 44.0, -0.8, 1.6)
    for k in range(8):
        S.light(3.0 + k * 6.4, H - 0.3, 0.0, 120)
    S.still = ((2.0, 0.0, 0.0), (1.0, 0.0), 0)
    return S


def trampoline():
    S = Scene("rdwe_trampoline", "Trampoline Park, the macro-structure", "30 m by 50 m, 9 m high (one cell was 14 by 28; the page repeats it)", "A",
              line="Remade 2x: the grid of black beds in orange pads, the padded columns, the truss ceiling; the red glow on the horizon is the "
                   "way on, and new doors lead to the god rooms and a padded vent.", mood="the macro-structure: it goes on forever", cluster="spine")
    X, Z, H = 15.0, 25.0, 9.0
    R = (-X, X, -Z, Z)
    hl = [exitdoor(S, "gods", "W", -8.0, R, to="the six god rooms (reserved: Nyx, Selene, Hypnos, Morpheus, Oneiros, Thanatos, built elsewhere)",
                   look="a tall marble door with a meander frieze (reserved for the god rooms)", width=1.2, height=2.4),
          exitdoor(S, "bounce", "E", 6.0, R, to="rdwe_crossroads", look="a padded vent door, orange foam, at floor level")]
    shell(S, "Park", -X, X, -Z, Z, h=H, holes=holes_of(hl), fmat="concrete", wmat="pad", cmat="truss")
    # the beds: 6 by 9, black in orange frames (art only: the page bounces you in Zone_trigger_beds)
    for i in range(6):
        for j in range(9):
            x0, z0 = -11.0 + i * 3.8, -21.0 + j * 4.2
            S.decor(f"Bed_{i}_{j}", (x0, 0.0, z0), (x0 + 3.0, 0.02, z0 + 3.4), "bed")
            S.decor(f"BedFrame_{i}_{j}", (x0 - 0.2, 0.0, z0 - 0.2), (x0 + 3.2, 0.012, z0 + 3.6), "pad")
    S.zone("trigger", "beds", (-11.2, 0.0, -21.2), (11.8, 0.3, 17.2))
    for k, z in enumerate((-16.0, -6.0, 4.0, 14.0), 1):
        S.solid(f"Column_{k}", (-13.6, 0.0, z - 0.5), (-12.6, H, z + 0.5), "pad")
    for nm, x0, x1 in (("W", -X, -X + 0.6), ("E", X - 0.6, X)):
        S.solid(f"AngledWall_{nm}", (x0, 0.0, -Z + 4.0), (x1, 2.4, -Z + 12.0), "pad")
    # you land on the apron under the vent (one way in), the red glow far north is the way on (one way out)
    S.decor("Vent", (-1.0, H - 0.1, 20.0), (1.0, H, 22.0), "black")
    S.link("vent", (0.0, 0.0, 22.6), (0.0, 0.0, 21.0), (0, -1), "arrival only: you fall out of the vent from rdwe_flooded's grate")
    S.decor("Red_Glow", (-0.6, 1.0, -23.6), (0.6, 2.2, -23.0), "red")
    S.link("glow", (0.0, 0.0, -22.0), (0.0, 0.0, -20.6), (0, -1), "rdwe_grocery (walk to the red glow: the anomaly)")
    S.spot("scuff", 1, (2.0, 0.0, 19.0), face=(0, -1), props={"what": "the same scuff mark passes under your feet: the page wraps you back"})
    S.spot("beacon", 1, (0.0, 0.0, -21.0), face=(0, -1), props={"what": "the red glow appears after 110 m walked"})
    S.label("TRAMPOLINE PARK", 0.4, -0.5)
    S.label("concrete apron (you land here)", 0.0, 22.0, kind="note")
    S.label("red glow", 0.0, -24.2, kind="note")
    S.label("padded columns", -12.0, -11.0, kind="note")
    S.corridor("apron", -10.0, 10.0, 18.0, 24.0)
    auto_lights(S, -X, X, -Z, Z, H - 0.5, step=10.0, power=400)
    S.still = ((0.0, 0.0, 22.0), (0.0, -1.0), 2)
    return S


GROCERY_N, GROCERY_CELL = 10, 5.0


def _grocery_maze():
    """A perfect maze on 10 by 10 cells of 5 m (as games/rdwe/scenes/grocery.js grows its aisles), with the 2 by 2 cells in the middle open
    (the red-cart clearing). walls_h[r][c]: the wall on the north side of cell (r, c) (r = 0 is the north row); walls_v[r][c]: on its west."""
    n = GROCERY_N
    rnd = random.Random(7731)
    wh = [[True] * n for _ in range(n + 1)]
    wv = [[True] * (n + 1) for _ in range(n)]
    seen = [[False] * n for _ in range(n)]
    stack = [(n - 1, 3)]
    seen[n - 1][3] = True
    while stack:
        r, c = stack[-1]
        opts = [(r + dr, c + dc, dr, dc) for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)) if 0 <= r + dr < n and 0 <= c + dc < n and not seen[r + dr][c + dc]]
        if not opts:
            stack.pop()
            continue
        nr, nc, dr, dc = opts[rnd.randrange(len(opts))]
        if dr == -1:
            wh[r][c] = False
        elif dr == 1:
            wh[r + 1][c] = False
        elif dc == -1:
            wv[r][c] = False
        else:
            wv[r][c + 1] = False
        seen[nr][nc] = True
        stack.append((nr, nc))
    for r in (4, 5):                                       # the clearing: the middle 2 by 2 cells open into each other
        wv[r][5] = False
    for c in (4, 5):
        wh[5][c] = False
    return wh, wv


def grocery():
    S = Scene("rdwe_grocery", "Grocery Store, the anomaly", "50 m by 50 m, 5 m high (was 38 by 46 by 4): a maze of shelving, 10 by 10 aisles "
              "of 5 m", "A", line="Remade 1.2x: the stripped store as a maze of empty shelving round the roped-off red cart; the lit EXIT closes the "
                                  "loop, and the locked entrance opens into the finale once the map is complete.",
              mood="the anomaly: the only thing that isn't supposed to be here", cluster="spine")
    X, Z, H = 25.0, 25.0, 5.0
    R = (-X, X, -Z, Z)
    cx = lambda c: -X + (c + 0.5) * GROCERY_CELL
    hl = [exitdoor(S, "entrance", "S", cx(4), R, to="rdwe_finale (the locked entrance doors open once every room is done)", width=2.4, height=2.4,
                   look="the entrance: a pair of glass sliding doors, chained shut", props={"opens_when": "the map is complete"}),
          exitdoor(S, "exit", "N", cx(7), R, to="rdwe_dining (the loop: you are back at the start)", width=1.1, height=2.15,
                   look="the fire exit: grey steel, a push bar, the lit EXIT sign"),
          exitdoor(S, "gods", "W", 22.5, R, to="arrival only (reserved): the last god room comes out here", look="a bronze door, a laurel wreath "
                   "for a handle (reserved: from the god rooms)"),
          exitdoor(S, "stockroom", "E", 2.5, R, to="rdwe_vending_room", look="a stockroom door: rubber flaps, black, STAFF ONLY")]
    shell(S, "Store", -X, X, -Z, Z, h=H, holes=holes_of(hl), fmat="vinyl", wmat="wall", cmat="ceiling")
    wh, wv = _grocery_maze()
    n, C, TH, SH = GROCERY_N, GROCERY_CELL, 0.4, 1.85
    posts = set()
    for r in range(1, n):                                   # inner horizontal shelf runs (the perimeter is the store's walls)
        for c in range(n):
            if wh[r][c]:
                z = -Z + r * C
                S.solid(f"Shelf_H_{r}_{c}", (-X + c * C + TH, 0.0, z - TH), (-X + (c + 1) * C - TH, SH, z + TH), "shelf")
                posts.update({(r, c), (r, c + 1)})
    for r in range(n):
        for c in range(1, n):
            if wv[r][c]:
                x = -X + c * C
                S.solid(f"Shelf_V_{r}_{c}", (x - TH, 0.0, -Z + r * C + TH), (x + TH, SH, -Z + (r + 1) * C - TH), "shelf")
                posts.update({(r, c), (r + 1, c)})
    for (r, c) in sorted(posts):
        if 0 < r < n and 0 < c < n:
            x, z = -X + c * C, -Z + r * C
            S.solid(f"Post_{r}_{c}", (x - TH, 0.0, z - TH), (x + TH, SH, z + TH), "shelf")
        elif r in (0, n) and 0 < c < n:
            x, z = -X + c * C, -Z + r * C
            z0, z1 = (-Z, -Z + TH) if r == 0 else (Z - TH, Z)
            S.solid(f"Post_{r}_{c}", (x - TH, 0.0, z0), (x + TH, SH, z1), "shelf")
        elif c in (0, n) and 0 < r < n:
            x, z = -X + c * C, -Z + r * C
            x0, x1 = (-X, -X + TH) if c == 0 else (X - TH, X)
            S.solid(f"Post_{r}_{c}", (x0, 0.0, z - TH), (x1, SH, z + TH), "shelf")
    # the clearing: the red cart roped off between four stanchions; the red tins in three dead ends
    S.solid("Cart", (-0.5, 0.0, -0.8), (0.5, 1.05, 0.8), "cart")
    for k, (sx, sz) in enumerate(((-2.2, -2.2), (2.2, -2.2), (-2.2, 2.2), (2.2, 2.2)), 1):
        S.solid(f"Stanchion_{k}", (sx - 0.1, 0.0, sz - 0.1), (sx + 0.1, 1.0, sz + 0.1), "chrome")
    S.decor("Caution_Tape", (-2.2, 0.85, -2.25), (2.2, 0.9, -2.15), "yellow")
    dead = []
    for r in range(n):
        for c in range(n):
            open_sides = (not wh[r][c]) + (not wh[r + 1][c]) + (not wv[r][c]) + (not wv[r][c + 1])
            if open_sides == 1 and (r, c) not in ((4, 4), (4, 5), (5, 4), (5, 5)):
                dead.append((r, c))
    pick = [dead[i] for i in (1, len(dead) // 2, len(dead) - 2)]
    for k, (r, c) in enumerate(pick, 1):
        S.spot("tin", k, (cx(c), 0.0, -Z + (r + 0.5) * C), face=(0, 1), props={"what": "a pyramid of tins in a dead end; one is red: put it in the cart"})
    S.spot("cart", 1, (0.0, 0.0, 1.6), face=(0, -1), props={"what": "the roped-off red cart: the three red tins go in it"})
    S.need_spots = {"tin": 3, "cart": 1}
    S.link("glow", (cx(4), 0.0, Z - 2.6), (cx(4), 0.0, Z - 3.4), (0, -1), "arrival only: from rdwe_trampoline's red glow (the locked doors behind you)")
    S.decor("Exit_Sign", (cx(7) - 0.5, 2.3, -Z), (cx(7) + 0.5, 2.7, -Z + 0.08), "red")
    S.label("GROCERY", cx(2), 0.0)
    S.label("red cart", 0.0, -1.6, kind="note")
    S.label("EXIT", cx(7), -Z + 3.0, kind="note")
    S.label("locked entrance", cx(4), Z - 1.0, kind="note")
    auto_lights(S, -X, X, -Z, Z, H - 0.4, step=10.0, power=300)
    S.still = ((cx(4), 0.0, Z - 3.4), (0.0, -1.0), 2)
    return S


# ================================================================ PHASE B: the set pieces
def repeating_room():
    S = Scene("rdwe_repeating_room", "The room that repeats, and the door seen from one angle", "12 m by 12 m, 3.2 m high; a recess 2 m deep "
              "behind a baffle on the east wall", "B", line="Go out the north door and you come back in the south one: the same room, a little "
              "changed each time. One door shows from one angle only: the way into Secret Operations.",
              mood="deep in the maze: the room that repeats", cluster="deep")
    X, Z, H = 6.0, 6.0, 3.2
    R = (-X, X, -Z, Z)
    hl = [exitdoor(S, "lift", "S", -2.5, R, to="rdwe_elevator_lobby (lift 3)"),
          exitdoor(S, "library", "W", 2.0, R, to="rdwe_melting_library"),
          exitdoor(S, "again", "N", 0.0, R, to="this room again: you come back in by the south door (it repeats)",
                   look="the north door: plain white flush, a number plate that changes every time"),
          exitdoor(S, "again_in", "S", 2.5, R, link=False, arrival_of="rdwe_repeating_room.again",
                   look="the south door: the north door again, seen from the other side, its number one higher")]
    RY0, RY1 = -3.8, -2.2                                  # the recess on the east wall, its door at its far end
    hl.append(("E", ((RY0 + RY1) / 2, RY1 - RY0, 2.6, 0.0)))
    shell(S, "Room", -X, X, -Z, Z, h=H, holes=holes_of(hl), fmat="peach", wmat="lilac", cmat="ceiling")
    for e in S.empties:                                    # the north door brings you back in by the south one
        if e["name"] == "Arrive_again":
            e["pos"], e["face"] = [2.5, 0.0, Z - 1.9], (0, -1)
    RE = X + T + 2.0                                       # the recess: inside x 6.2 to 8.2, z -3.8 to -2.2, 2.6 m high
    RM = (RY0 + RY1) / 2
    S.solid("Recess_Floor", (X + T, -SLAB, RY0), (RE + T, 0.0, RY1), "lilac")
    S.solid("Recess_Wall_N", (X + T, 0.0, RY0 - T), (RE + T, 2.6, RY0), "lilac")
    S.solid("Recess_Wall_S", (X + T, 0.0, RY1), (RE + T, 2.6, RY1 + T), "lilac")
    S.solid("Recess_Ceiling", (X + T, 2.6, RY0 - T), (RE + T, 2.8, RY1 + T), "ceiling", ("ceiling",))
    wall(S, "Recess_Wall_E", "z", RE, RE + T, RY0, RY1, 0.0, 2.6, [(RM - 0.5, RM + 0.5, 0.0, 2.2)], "lilac")
    S.leaf("secret_ops", (RE, 0.0, RM - 0.45), (0, 1), (-1, 0), 0.9, 2.12, "closed",
           {"exit": "secret_ops", "look": "the door from one angle: painted the wall's lilac, on the recess's end, seen only past the baffle",
            "seen_from": "Spot_view_1 only"})
    S.solid("Beyond_secret_ops", (RE + T + 0.15, -0.05, RY0 - 0.2), (RE + T + 0.35, 2.4, RY1 + 0.2), "void")
    S.link("secret_ops", (RE - 0.6, 0.0, (RY0 + RY1) / 2), (RE - 1.4, 0.0, (RY0 + RY1) / 2), (-1, 0),
           "secret_ops.hidden_entry (rdwe.repeating_room>secret_ops: the one entrance with no clearance)")
    S.solid("Baffle", (X - 1.25, 0.0, RY0 - 1.0), (X - 1.05, H, RY1 + 1.0), "lilac")
    S.spot("view", 1, (-3.5, 0.0, 4.5), face=(0.85, -0.53), props={"what": "the one place the recess's door shows from: past the baffle's "
                                                                    "south end"})
    for k, (x, z) in enumerate(((-3.0, -2.0), (0.0, 1.5), (-4.6, -4.6)), 1):
        S.spot("change", k, (x, 0.0, z), face=(0, -1), props={"what": "something here is different on each lap (the page swaps it)"})
    S.solid("Armchair", (-4.6, 0.0, 0.2), (-3.4, 0.9, 1.4), "pink")
    S.solid("Side_Table", (1.6, 0.0, -1.2), (2.4, 0.7, -0.4), "wood")
    S.need_spots = {"view": 1, "change": 3}
    S.label("REPEATING ROOM", -1.0, 3.0)
    S.label("baffle", 4.6, -0.2, kind="note")
    S.label("recess: Secret Ops", 7.4, -1.4, kind="note")
    S.corridor("through", -1.0, 1.0, -5.0, 5.0)
    auto_lights(S, -X, X, -Z, Z, H - 0.3, step=6.0, power=120)
    S.still = ((-3.5, 0.0, 4.5), (0.85, -0.53), 0)
    return S


def finale():
    S = Scene("rdwe_finale", "The finale: hide and seek", "48 m by 44 m, 4.5 m high: a hall and four wings (offices, the house, the server room, "
              "the aisles)", "B", line="The map opens into hide and seek: hack the four computers to blind the ten cameras; the agents swarm in "
                                       "late from the vents. Win, and the doors open on the grocery (the one ending).",
              mood="the finale: hide and seek", cluster="finale")
    X, Z, H = 24.0, 22.0, 4.5
    R = (-X, X, -Z, Z)
    hl = [exitdoor(S, "grocery", "S", 0.0, R, to="arrival only: through the grocery's entrance doors, once the map is complete",
                   arrival_of="rdwe_grocery.entrance", width=2.4, height=2.4, look="the grocery's glass doors, from the other side, unchained"),
          exitdoor(S, "win", "N", 0.0, R, to="grocery.main_floor (rdwe.finale>grocery: the one ending; opens when every camera is off)",
                   width=2.0, height=2.6, look="a pair of tall blue doors with a green EXIT light, sealed until the cameras are off",
                   props={"opens_when": "every SecCam is off"})]
    shell(S, "Finale", -X, X, -Z, Z, h=H, holes=holes_of(hl), fmat="vinyl", wmat="navy", cmat="ceiling")
    # the four wings off a central hall 12 m wide (x -6 to 6): partition walls with 2.4 m openings
    for nm, x in (("W", -6.0), ("E", 6.0)):
        wall(S, f"Hall_{nm}", "z", x - 0.1 if x < 0 else x, x if x < 0 else x + 0.1, -Z, Z, 0.0, H,
             [(-14.0, -11.6, 0.0, 2.6), (-2.4, 0.0, 0.0, 2.6), (8.0, 10.4, 0.0, 2.6), (14.0, 16.4, 0.0, 2.6)], "navy")
    for nm, x0, x1 in (("W", -X, -6.1), ("E", 6.1, X)):
        wall(S, f"Wing_{nm}", "x", -0.1, 0.1, x0, x1, 0.0, H, [((x0 + x1) / 2 - 1.2, (x0 + x1) / 2 + 1.2, 0.0, 2.6)], "navy")
    # NW offices: cubicle partitions; SW the house: a room with a bed and a wardrobe; NE servers: rack rows; SE aisles: shelves
    for i in range(3):
        for j in range(2):
            x0, z0 = -21.0 + i * 5.0, -18.0 + j * 8.0
            S.solid(f"Cubicle_{i}_{j}_A", (x0, 0.0, z0), (x0 + 3.0, 1.4, z0 + 0.1), "office")
            S.solid(f"Cubicle_{i}_{j}_B", (x0, 0.0, z0 + 0.1), (x0 + 0.1, 1.4, z0 + 3.0), "office")
            S.solid(f"Desk_{i}_{j}", (x0 + 0.1, 0.0, z0 + 0.1), (x0 + 1.5, 0.75, z0 + 0.8), "wood")
    S.solid("House_Bed", (-20.0, 0.0, 4.0), (-17.8, 0.6, 6.2), "pink")
    S.solid("House_Wardrobe", (-X, 0.0, 12.0), (-X + 0.7, 2.2, 14.0), "wood")
    S.solid("House_Table", (-14.0, 0.0, 10.0), (-11.0, 0.8, 12.0), "maple")
    S.solid("House_Sofa", (-10.0, 0.0, 17.0), (-7.0, 0.9, 18.2), "orange")
    for k in range(4):
        z = -18.0 + k * 4.4
        S.solid(f"Rack_{k + 1}", (9.0, 0.0, z), (21.0, 2.2, z + 1.0), "server")
    S.zone("restricted", "servers", (6.1, 0.0, -Z), (X, H, -0.1))
    for k in range(4):
        z = 3.0 + k * 4.6
        S.solid(f"Aisle_Shelf_{k + 1}", (9.0, 0.0, z), (21.0, 1.85, z + 0.8), "shelf")
    S.solid("Hall_Fountain", (-1.5, 0.0, -7.0), (1.5, 0.9, -4.0), "cyan")
    # the four computers to hack, one per wing; the ten cameras; hiding places; where the agents come in; where the seeker starts
    for k, (x, z, f, what) in enumerate(((-19.6, -16.6, (0, 1), "the offices' computer"), (-12.5, 12.8, (0, -1), "the house's computer, on the table"),
                                         (15.0, -2.2, (0, -1), "the server room's console"), (15.0, 19.0, (0, -1), "the aisles' till")), 1):
        S.spot("computer", k, (x, 0.0, z), face=f, props={"what": f"{what}: hack it to turn off cameras", "hack_s": 8})
    cams = [(-23.6, 3.8, -20.0, (1, 1)), (-23.6, 3.8, 0.0, (1, 0)), (-14.0, 3.8, 21.6, (0, -1)), (-6.4, 3.8, -10.0, (1, 0)),
            (6.4, 3.8, 10.0, (-1, 0)), (23.6, 3.8, -20.0, (-1, 1)), (23.6, 3.8, -5.0, (-1, 0)), (23.6, 3.8, 20.0, (-1, -1)),
            (0.0, 3.8, -21.6, (0, 1)), (0.0, 3.8, 21.6, (0, -1))]
    for k, (x, y, z, f) in enumerate(cams, 1):
        S.seccam(k, (x, y, z), f, {"what": "hide-and-seek camera: off when its wing's computer is hacked"})
        S.decor(f"Cam_{k:02d}", (x - 0.15, y - 0.15, z - 0.15), (x + 0.15, y + 0.15, z + 0.15), "black")
    hides = [(-16.5, -16.0), (-11.5, -8.0), (-21.0, 2.5), (-19.0, 16.0), (-8.5, 15.5), (-3.5, -19.5), (3.5, 19.0), (8.0, -19.5),
             (22.0, -3.5), (8.0, 6.5), (22.5, 15.0), (-4.5, 6.0)]
    for k, (x, z) in enumerate(hides, 1):
        S.spot("hide", k, (x, 0.0, z), face=(0, 1), props={"what": "a hiding place"})
    for k, (x, z) in enumerate(((-23.0, -10.0), (-23.0, 19.0), (23.0, -12.0), (23.0, 12.0), (-10.0, -21.0), (10.0, 21.0)), 1):
        S.spot("agent", k, (x, 0.0, z), face=(1 if x < 0 else -1, 0) if abs(x) > 20 else (0, 1 if z < 0 else -1),
               props={"what": "a vent the agents swarm out of, late"})
        if abs(x) > 20:                                    # the vent on the wall behind the spot
            wx = -X if x < 0 else X - 0.04
            S.decor(f"Vent_{k}", (wx, 0.2, z - 0.4), (wx + 0.04, 0.9, z + 0.4), "black")
        else:
            wz = -Z if z < 0 else Z - 0.04
            S.decor(f"Vent_{k}", (x - 0.4, 0.2, wz), (x + 0.4, 0.9, wz + 0.04), "black")
    S.spot("seeker", 1, (0.0, 0.0, 0.0), face=(0, 1), props={"what": "the seeker counts here (either side seeks, with friends)"})
    S.need_spots = {"computer": 4, "hide": 10, "agent": 6, "seeker": 1}
    S.label("HALL", 0.0, 2.0)
    S.label("OFFICES", -15.0, -6.0)
    S.label("THE HOUSE", -15.0, 8.0)
    S.label("SERVERS", 15.0, -9.0)
    S.label("AISLES", 15.0, 11.0)
    S.corridor("hall", -5.5, 5.5, -3.5, 3.5)
    auto_lights(S, -X, X, -Z, Z, H - 0.4, step=10.0, power=300)
    S.still = ((0.0, 0.0, 19.6), (0.0, -1.0), 0)
    return S


# ================================================================ PHASE C: the new rooms, one line and one minimal greybox each
def croom(sid, title, w, d, h, doors, keys, line, cluster, fmat="floor", wmat="wall", cmat="ceiling", trick=None, size=None, mood="",
          still=None, levels=(0.0,)):
    """A Phase C room: a shell w by d by h (x -w/2..w/2, z -d/2..d/2), its doors [(did, side, a, kw)], key boxes keys(S) for its trick and
    the trick's spot (kind, pos, face, what)."""
    S = Scene(sid, title, size or f"{w:g} m by {d:g} m, {h:g} m high", "C", line=line, mood=mood or "new", cluster=cluster, levels=levels)
    X, Z = w / 2, d / 2
    R = (-X, X, -Z, Z)
    hl = []
    for did, side, a, kw in doors:
        hl.append(exitdoor(S, did, side, a, R, to=kw.pop("to", ""), **kw))
    shell(S, "Room", -X, X, -Z, Z, h=h, holes=holes_of(hl), fmat=fmat, wmat=wmat, cmat=cmat)
    keys(S)
    if trick:
        kind, pos, face, what = trick
        S.spot(kind, 1, pos, face=face, props={"what": what})
        S.need_spots = {kind: 1}
    S.label(title.split(":")[0].upper(), 0.0, 0.0 if d < 30 else -2.0)
    auto_lights(S, -X, X, -Z, Z, h - 0.35, step=6.0, power=110)
    if still:
        S.still = still
    else:
        a = next(e for e in S.empties if e["name"].startswith("Arrive_"))
        S.still = ((a["pos"][0] - a["face"][0] * 0.6, a["pos"][1], a["pos"][2] - a["face"][1] * 0.6), a["face"], 0)
    return S


def D(**kw):
    return kw


def c_long_table():
    def keys(S):
        S.solid("Table", (-1.0, 0.0, -14.0), (1.0, 0.8, 14.0), "maple")
        for k in range(7):
            z = -12.0 + k * 4.0
            s = 0.55 + 0.25 * (6 - k) / 6 * 3                     # the chairs grow toward the far end, so it looks the same from either end
            S.solid(f"Chair_W_{k + 1}", (-1.2 - s, 0.0, z - s / 2), (-1.2, s, z + s / 2), "maple")
        S.solid("Far_Chair", (-0.8, 0.0, -16.6), (0.8, 3.2, -15.0), "maple")
    return croom("rdwe_long_table", "The long table: the same length from both ends", 8, 34, 3.2,
                 [("dining", "S", 0.0, D(to="rdwe_dining")), ("kitchen", "W", -10.0, D(to="rdwe_tiny_kitchen")),
                  ("party", "E", 8.0, D(to="rdwe_birthday_party"))], keys,
                 "Object distortion: a 28 m dining table whose chairs grow toward the far end, so it looks the same length whichever end you "
                 "stand at; the giant last chair hides nothing.", "house", fmat="shag", wmat="cream",
                 trick=("trick", (2.6, 0.0, 0.0), (-1, 0), "walk the length: the far end never gets closer until you stop looking"))


def c_tiny_kitchen():
    def keys(S):
        S.solid("Counter_Big", (-1.0, 0.0, -4.0), (5.0, 0.95, -3.4), "white")
        S.solid("Counter_Small", (-5.0, 0.0, -4.0), (-1.0, 0.5, -3.6), "white")
        S.decor("Ceiling_Drop", (-5.0, 2.0, -4.0), (-1.0, 3.0, 4.0), "ceiling", ("ceiling",))
    return croom("rdwe_tiny_kitchen", "The tiny kitchen: the far half is shrunk", 10, 8, 3.0,
                 [("table", "E", 0.0, D(to="rdwe_long_table")), ("back", "W", 2.0, D(to="rdwe_giant_chair", width=0.8, height=1.7))], keys,
                 "Object distortion: a kitchen whose west half is built at half scale, counters to the knee and a 1.7 m back door; walk in and you "
                 "feel you have grown.", "house", fmat="tile", wmat="mint",
                 trick=("trick", (-3.0, 0.0, 1.0), (-1, 0), "the half-scale end: everything here is the size of a doll's house"))


def c_birthday_party():
    def keys(S):
        S.solid("Party_Table", (-3.0, 0.0, -0.8), (3.0, 0.8, 0.8), "pink")
        S.decor("Cake", (-0.4, 0.8, -0.4), (0.4, 1.3, 0.4), "white")
        for k in range(8):
            S.decor(f"Balloon_{k + 1}", (-5.0 + k * 1.4, 2.4, -3.0 + (k % 3)), (-4.6 + k * 1.4, 2.9, -2.6 + (k % 3)), ["pink", "cyan", "acid", "violet"][k % 4])
    return croom("rdwe_birthday_party", "The birthday party: nobody came", 14, 10, 3.2,
                 [("table", "W", 0.0, D(to="rdwe_long_table")), ("attic", "N", 4.0, D(to="rdwe_attic"))], keys,
                 "Environmental storytelling: a party laid for guests who never came, the cake uncut, the balloons at the ceiling, name cards "
                 "for everyone you have met in the rooms.", "house", fmat="peach", wmat="pink",
                 trick=("cake", (0.0, 0.0, 2.0), (0, -1), "the cake: the candles light when you look away"))


def c_attic():
    def keys(S):
        for k, (x, z) in enumerate(((-4.0, -2.0), (-5.0, 2.6), (3.4, -2.6), (4.2, 2.0)), 1):
            S.solid(f"Photo_Boxes_{k}", (x - 0.6, 0.0, z - 0.5), (x + 0.6, 0.9, z + 0.5), "cardboard")
        S.decor("Hatch", (-0.6, 0.0, -0.6), (0.6, 0.02, 0.6), "black")
        S.link("hatch", (0.0, 0.0, 1.0), (1.2, 0.0, 1.2), (0, 1), "rdwe_kids_bedroom (down through the hatch)")
    return croom("rdwe_attic", "The attic: the dining room's photographs", 12, 8, 2.6,
                 [("party", "S", -3.0, D(to="rdwe_birthday_party"))], keys,
                 "Environmental storytelling: under the roof, boxes of the dining room's photographs, every one of you; a hatch in the floor drops "
                 "you into a child's bedroom.", "house", fmat="wood", wmat="wood",
                 trick=("photo", (-4.0, 0.0, -0.6), (0, -1), "a box of photographs: each one is the last room you were in"))


def c_kids_bedroom():
    def keys(S):
        S.solid("Bed", (-3.6, 0.0, -3.6), (-1.6, 0.5, -1.0), "cyan")
        S.solid("Toy_Chest", (2.0, 0.0, 2.6), (3.4, 0.6, 3.6), "sun")
        S.decor("Ceiling_Hatch", (-0.6, 2.75, -0.6), (0.6, 2.8, 0.6), "black")
        S.link("hatch", (0.0, 0.0, 0.0), (0.6, 0.0, 0.8), (0, 1), "arrival from rdwe_attic's hatch (and back up it)")
    return croom("rdwe_kids_bedroom", "The kid's bedroom: someone waited here", 8, 8, 2.8,
                 [("closet", "E", -2.0, D(to="rdwe_hallway (a side door)"))], keys,
                 "Environmental storytelling: a 90s child's bedroom, glow stars, a toy chest, notes under the bed counting days; the closet opens "
                 "on the hallway.", "house", fmat="lilac", wmat="cyan",
                 trick=("notes", (-2.6, 0.0, -0.4), (0, -1), "the notes under the bed: someone counted the days here"))


def c_giant_chair():
    def keys(S):
        S.solid("Chair_Back", (-7.8, 0.0, -7.0), (-1.0, 7.0, -5.6), "orange")
        flight(S, "cushions", 1.0, 5.0, 1.0, -1, "z", 0.0, 3.0, 12, 0.5, mat="orange")
        S.solid("Ledge", (1.0, 2.7, -7.0), (5.0, 3.0, -5.0), "orange")
        S.solid("Chair_Arm", (-1.0, 0.0, -5.6), (0.6, 2.6, 2.0), "orange")
    return croom("rdwe_giant_chair", "The giant armchair: climb it", 16, 14, 8.0,
                 [("kitchen", "S", -5.0, D(to="rdwe_tiny_kitchen")), ("high", "N", 3.0, D(to="rdwe_upside_room", y=3.0, at_in=0.6, arr_in=1.4))],
                 keys, "Object distortion: an armchair 7 m tall in a living room; climb its cushions (12 steps) to the door 3 m up the wall.",
                 "house", fmat="shag", wmat="cream", levels=(0.0, 3.0),
                 trick=("trick", (-5.0, 0.0, 4.0), (0, -1), "you are the size of a cat: the door is up the chair"))


def c_upside_room():
    def keys(S):
        S.decor("Ceiling_Table", (-1.2, 2.6, -0.8), (1.2, 3.2, 0.8), "wood", ("ceiling",))
        for k, (x, z) in enumerate(((-2.0, 0.0), (2.0, 0.0)), 1):
            S.decor(f"Ceiling_Chair_{k}", (x - 0.3, 2.8, z - 0.3), (x + 0.3, 3.4, z + 0.3), "wood", ("ceiling",))
        S.solid("Chandelier_Up", (-0.25, 0.0, -0.25), (0.25, 1.6, 0.25), "sun")
    return croom("rdwe_upside_room", "The upside-down room", 10, 10, 3.4,
                 [("chair", "W", 0.0, D(to="rdwe_giant_chair")), ("hall", "E", 0.0, D(to="rdwe_hallway (a side door)"))], keys,
                 "Perspective shifting: the furniture hangs from the ceiling and the chandelier stands up from the floor, so for a second you are on "
                 "the ceiling.", "house", fmat="ceiling", wmat="sun", cmat="shag",
                 trick=("trick", (0.0, 0.0, 2.4), (0, -1), "look up: the table is above you"))


def c_door_hall():
    W = [(-18, "fake"), (-14, "d3"), (-9, "fake"), (-4, "fake"), (1, "fake"), (10, "d9"), (16, "fake")]
    E = [(-18, "fake"), (-9, "fake"), (-4, "d6"), (6, "fake"), (16, "fake")]
    doors = [("hallway", "S", 0.0, D(to="rdwe_hallway (a side door)"))]
    k = 0
    for side, row in (("W", W), ("E", E)):
        for z, kind in row:
            if kind == "fake":
                k += 1
                doors.append((f"wrong_{k}", side, float(z), D(fake=True)))
            else:
                doors.append((kind, side, float(z), D(to={"d3": "rdwe_stretching_hall", "d9": "rdwe_painted_door", "d6": "rdwe_three_doors"}[kind])))

    def keys(S):
        S.solid("Bench", (-0.5, 0.0, -2.0), (0.5, 0.45, 2.0), "wood")
    return croom("rdwe_door_hall", "The hall of doors: twelve, and three open", 6, 44, 3.4, doors, keys,
                 "Multi-choice navigation: a hall of twelve doors, no two alike; nine never open, three lead on, and the notebook only marks "
                 "the ones you tried.", "halls", fmat="carpet_tan", wmat="plaid",
                 trick=("trick", (0.0, 0.0, 5.0), (0, -1), "twelve doors, no two alike: three open"))


def c_stretching_hall():
    def keys(S):
        for k in range(6):
            z = -18.0 + k * 7.0
            S.solid(f"Fin_W_{k + 1}", (-2.0, 0.0, z - 0.2), (-1.6, 3.0, z + 0.2), "white")
            S.solid(f"Fin_E_{k + 1}", (1.6, 0.0, z - 0.2), (2.0, 3.0, z + 0.2), "white")
    return croom("rdwe_stretching_hall", "The stretching hall: longer when you run", 4, 46, 3.0,
                 [("doors", "S", 0.0, D(to="rdwe_door_hall")), ("far", "N", 0.0, D(to="rdwe_bending_hall"))], keys,
                 "Distorted hall: 46 m of white fins that gets longer the faster you go and shorter if you walk backwards.", "halls",
                 fmat="white", wmat="white", trick=("trick", (0.0, 0.0, 0.0), (0, -1), "run and the far door recedes; walk and it comes"))


def c_bending_hall():
    def keys(S):
        S.solid("Core", (-6.0, 0.0, -6.0), (6.0, 3.0, 6.0), "violet")
    return croom("rdwe_bending_hall", "The bending hall: four right turns", 20, 20, 3.0,
                 [("start", "S", -8.0, D(to="rdwe_stretching_hall")), ("lap", "N", 8.0, D(to="rdwe_stair_loop", props={"shows": "on the third lap only"}))],
                 keys, "Distorted hall: a corridor that turns right four times round a solid core and comes back to itself; its one door is "
                       "there only on the third lap.", "halls", fmat="carpet_tan", wmat="lilac",
                 trick=("lap", (-8.0, 0.0, 0.0), (0, -1), "count the laps: the door shows on the third"))


def c_stair_loop():
    S = Scene("rdwe_stair_loop", "The stair loop: up four flights to where you started", "8 m by 14 m, 6.4 m high; one flight to a landing at y 3",
              "C", line="Distorted hall: climb the stairs to the landing's top door and you arrive at the bottom of the same stairs (a Penrose "
                        "loop); the landing's side door is the way on.", mood="new", cluster="halls", levels=(0.0, 3.0))
    S.level_names = {0.0: "the foot (y 0)", 3.0: "the landing (y 3)"}
    X, Z, H = 4.0, 7.0, 6.4
    R = (-X, X, -Z, Z)
    hl = [exitdoor(S, "hall", "S", 2.0, R, to="rdwe_bending_hall"),
          exitdoor(S, "top", "N", -2.0, R, y=3.0, to="this room again: you arrive at the foot of the stairs", at_in=0.6, arr_in=1.4),
          exitdoor(S, "landing", "E", -3.0, R, y=3.0, to="rdwe_tilted_hall", at_in=0.6, arr_in=1.4)]
    shell(S, "Stairs", -X, X, -Z, Z, h=H, holes=holes_of(hl), fmat="concrete", wmat="mint")
    flight(S, "up", -3.6, -1.2, 4.0, -1, "z", 0.0, 3.0, 12, 0.4, mat="stair")
    S.solid("Landing", (-X, 2.7, -Z), (X, 3.0, -0.8), "stair")
    S.solid("Under_Landing", (-X, 0.0, -Z), (-1.2, 2.7, -0.8), "mint")
    for e in S.empties:                                    # the top door brings you back to the foot of the stairs
        if e["name"] == "Arrive_top":
            e["pos"], e["face"] = [-2.4, 0.0, 5.7], (0, -1)
    S.spot("trick", 1, (2.0, 0.0, 1.0), face=(0, -1), props={"what": "the stairs climb four flights and arrive where they began"})
    S.need_spots = {"trick": 1}
    S.label("STAIR LOOP", 2.0, 3.0)
    S.label("landing y 3", 1.0, -4.0, y=3.0)
    S.corridor("foot", 0.0, 3.6, -0.6, 5.0)
    auto_lights(S, -X, X, -Z, Z, H - 0.4, step=6.0)
    S.still = ((2.0, 0.0, 5.6), (-0.4, -1.0), 10)
    return S


def c_tilted_hall():
    def keys(S):
        flight(S, "tilt", -3.0, 3.0, 11.0, -1, "z", 0.0, 0.9, 6, 26.0 / 6, mat="carpet_tan")
        for k in range(6):
            S.decor(f"Ceiling_Step_{k + 1}", (-3.0, 3.6 - 0.25 * k, 11.0 - (k + 1) * 26.0 / 6), (3.0, 4.0, 11.0 - k * 26.0 / 6), "ceiling", ("ceiling",))
    return croom("rdwe_tilted_hall", "The squashing hall: the floor rises, the ceiling falls", 6, 30, 4.0,
                 [("stairs", "S", 0.0, D(to="rdwe_stair_loop")), ("end", "N", 0.0, D(to="rdwe_crossroads", y=0.9))], keys,
                 "Distorted hall: the floor steps up and the ceiling steps down until the far door is half the height it looked from the start.",
                 "halls", fmat="carpet_tan", wmat="peach", trick=("trick", (0.0, 0.0, 13.0), (0, -1), "it looks level from here"))


def c_three_doors():
    def keys(S):
        S.solid("Plinth", (-0.5, 0.0, 0.5), (0.5, 1.0, 1.5), "white")
        for k, x in enumerate((-4.0, 0.0, 4.0), 1):
            S.decor(f"Sign_{k}", (x - 0.6, 2.5, -5.0), (x + 0.6, 2.9, -4.96), ["red", "sun", "cyan"][k - 1])
    return croom("rdwe_three_doors", "Three doors: pick one", 12, 10, 3.4,
                 [("back", "S", 0.0, D(to="rdwe_door_hall")), ("left", "N", -4.0, D(to="rdwe_mirror_room")),
                  ("middle", "N", 0.0, D(to="rdwe_waiting_room")), ("right", "N", 4.0, D(to="rdwe_lights_out"))], keys,
                 "Multi-choice navigation: a white room with three doors and a note on a plinth (one of these is right); each is right, for a "
                 "different room.", "halls", fmat="white", wmat="white",
                 trick=("note", (0.0, 0.0, 2.4), (0, -1), "the note: one of these is right"))


def c_painted_door():
    def keys(S):
        S.solid("Pillar", (1.0, 0.0, -2.0), (1.6, 3.4, -1.4), "white")
    return croom("rdwe_painted_door", "The painted door: real from one spot", 6, 24, 3.4,
                 [("doors", "S", 0.0, D(to="rdwe_door_hall")), ("painted", "N", 0.0, D(to="rdwe_anamorphic_room",
                                                                                         look="a door painted on the end wall, real from the mark"))],
                 keys, "Perspective shifting: a door painted on the end wall, flat and fake until you stand on the floor mark, when it is a door.",
                 "halls", fmat="white", wmat="teal_cream", trick=("view", (0.0, 0.0, 6.0), (0, -1), "the floor mark: from here the painting is a door"))


def c_anamorphic_room():
    def keys(S):
        for k, (x, y, z) in enumerate(((-2.0, 2.6, -2.0), (2.6, 2.2, -4.0), (3.2, 0.4, 0.5), (-3.4, 1.4, 2.0), (0.8, 3.2, -5.0)), 1):
            S.decor(f"Floating_Piece_{k}", (x - 0.4, y, z - 0.1), (x + 0.4, y + 0.4, z + 0.1), "acid")
        S.solid("Crate_1", (-5.0, 0.0, -5.0), (-3.8, 1.2, -3.8), "wood")
        S.solid("Crate_2", (4.0, 0.0, 3.6), (5.2, 0.8, 4.8), "wood")
    return croom("rdwe_anamorphic_room", "The anamorphic room: pieces that line up", 14, 14, 4.0,
                 [("painted", "W", 0.0, D(to="rdwe_painted_door")), ("word", "N", 3.0, D(to="rdwe_ames_room", props={"shows": "from Spot_view_1 only"}))],
                 keys, "Perspective shifting: floating shards scattered through the room line up into the outline of a door from one spot, and "
                       "only then does the north door exist.", "halls", fmat="navy", wmat="navy",
                 trick=("view", (-4.0, 0.0, 4.0), (0.6, -0.8), "from here the shards make a doorway"))


def c_void_room():
    def keys(S):
        S.solid("Lone_Chair", (1.6, 0.0, 0.6), (2.2, 0.9, 1.2), "white")
    return croom("rdwe_void_room", "The void: behind the black doorway", 10, 10, 4.0,
                 [("teal", "S", 0.0, D(to="rdwe_teal (back through the black)")), ("lit", "N", -3.0, D(to="rdwe_lights_out",
                                                                                                       look="the single lit door: a glowing outline, white"))],
                 keys, "Environmental storytelling: pitch black behind the teal room's doorway, one chair, and a single door lit at its edges.",
                 "teal", fmat="black", wmat="black", cmat="black",
                 trick=("dark", (0.0, 0.0, 1.5), (0, -1), "no light: only the lit door's outline"))


def c_lights_out():
    def keys(S):
        for k, (x, z) in enumerate(((-3.0, 2.0), (0.0, -2.0), (3.0, 2.0)), 1):
            S.solid(f"Switch_Post_{k}", (x - 0.15, 0.0, z - 0.15), (x + 0.15, 1.2, z + 0.15), "sun")
    S = croom("rdwe_lights_out", "Lights out: switches show different doors", 12, 12, 3.2,
              [("void", "W", -3.0, D(to="rdwe_void_room")), ("three", "S", 3.0, D(to="rdwe_three_doors"))], keys,
              "Psychological puzzle: a dark room of three switches; each lights the room differently and shows a different door, and the door "
              "you take is the one lit when you reach it.", "teal", fmat="navy", wmat="violet")
    for k, (x, z) in enumerate(((-3.0, 2.6), (0.0, -1.4), (3.0, 2.6)), 1):
        S.spot("switch", k, (x, 0.0, z), face=(0, -1), props={"what": "a light switch: it shows one door and hides another"})
    S.need_spots = {"switch": 3}
    return S


def c_green_grid():
    def keys(S):
        for k in range(8):
            z = -13.0 + k * 3.6
            S.solid(f"Stud_W_{k + 1}", (-3.0, 0.0, z - 0.15), (-2.7, 4.0, z + 0.15), "grid")
            S.solid(f"Stud_E_{k + 1}", (2.7, 0.0, z - 0.15), (3.0, 4.0, z + 0.15), "grid")
    return croom("rdwe_green_grid", "Inside the wall: the green grid", 6, 30, 4.0,
                 [("teal2", "S", 0.0, D(to="rdwe_teal2")), ("seam", "N", 0.0, D(to="rdwe_ames_room", look="a seam in the grid, pulled open like a door"))],
                 keys, "Environmental storytelling: the space behind the teal room's wallpaper, a glowing green wireframe between studs; the "
                       "rooms are being built from here.", "teal", fmat="black", wmat="black", cmat="grid",
                 trick=("grid", (0.0, 0.0, 4.0), (0, -1), "the grid is still drawing the room you left"))


def c_ames_room():
    def keys(S):
        for i in range(7):                                  # the back wall slants: deep (and tall) in the west corner, shallow and low in the east
            x0, x1 = -7.0 + 2.0 * i, -5.0 + 2.0 * i
            zi = -5.0 + 3.0 * i / 6.0
            if zi > -5.0 + 1e-6:
                S.solid(f"Slant_{i + 1}", (x0, 0.0, -5.0), (x1, 4.5, zi), "checker")
        S.decor("Ceiling_Slope", (-7.0, 2.4, -5.0), (7.0, 4.5, -4.8), "ceiling", ("ceiling",))
    MATS.setdefault("checker", (0.85, 0.85, 0.85))
    return croom("rdwe_ames_room", "The Ames room: you shrink across it", 14, 10, 4.5,
                 [("word", "S", -4.0, D(to="rdwe_anamorphic_room")), ("grid", "W", 0.0, D(to="rdwe_green_grid")),
                  ("small", "E", -1.5, D(to="rdwe_shrink_hall", width=0.8, height=1.9))], keys,
                 "Perspective shifting: a trapezoid room that looks square from the peephole; walk to the short corner and you seem to grow until "
                 "you fit its small door.", "teal", fmat="checker", wmat="magenta",
                 trick=("view", (0.0, 0.0, 4.2), (0, -1), "the peephole: from here the room is square"))


def c_shrink_hall():
    def keys(S):
        S.solid("Narrow_W_1", (-3.0, 0.0, 0.0), (-2.4, 3.6, 6.0), "pink")
        S.solid("Narrow_E_1", (2.4, 0.0, 0.0), (3.0, 3.6, 6.0), "pink")
        S.solid("Narrow_W_2", (-3.0, 0.0, -6.0), (-1.8, 3.6, 0.0), "pink")
        S.solid("Narrow_E_2", (1.8, 0.0, -6.0), (3.0, 3.6, 0.0), "pink")
        S.solid("Narrow_W_3", (-3.0, 0.0, -12.0), (-1.0, 3.6, -6.0), "pink")
        S.solid("Narrow_E_3", (1.0, 0.0, -12.0), (3.0, 3.6, -6.0), "pink")
        S.decor("Ceiling_Low", (-1.0, 2.2, -12.0), (1.0, 3.6, -6.0), "ceiling", ("ceiling",))
    return croom("rdwe_shrink_hall", "The shrinking hall: forced perspective", 6, 24, 3.6,
                 [("ames", "S", 0.0, D(to="rdwe_ames_room")), ("small", "N", 0.0, D(to="rdwe_moon_window", width=0.8, height=1.8))], keys,
                 "Distorted hall: 24 m that narrows from 6 m to 2 m and lowers to 2.2 m in steps, so from the big end the small door looks far "
                 "away and is not.", "teal", fmat="peach", wmat="pink",
                 trick=("trick", (0.0, 0.0, 8.0), (0, -1), "it looks 60 m long from here"))


def c_moon_window():
    def keys(S):
        S.decor("Window_Night", (-3.0, 1.2, -6.0), (3.0, 3.2, -5.96), "navy")
        S.decor("Moon", (-0.5, 2.0, -5.95), (0.5, 3.0, -5.9), "moon")
        S.solid("Pedestal", (2.6, 0.0, 2.6), (3.4, 1.0, 3.4), "white")
    S = croom("rdwe_moon_window", "The moon in the window: pick it up", 10, 12, 3.6,
              [("hall", "E", 0.0, D(to="rdwe_shrink_hall")), ("sill", "W", 2.0, D(to="rdwe_mirror_room"))], keys,
              "Object distortion (Super Liminal's trick): the moon in the window can be picked up; held close it is a ball, set on the pedestal "
              "it is the size of the room and the west door opens.", "teal", fmat="navy", wmat="lilac",
              trick=("moon", (0.0, 0.0, -4.0), (0, -1), "pick up the moon: its size is how far away you hold it"))
    S.spot("switch", 1, (3.0, 0.0, 1.8), face=(0, 1), props={"what": "the pedestal: the moon goes here"})
    return S


def c_mirror_room():
    def keys(S):
        S.solid("Glass_N", (-0.05, 0.0, -5.0), (0.05, 3.4, -0.8), "glass")
        S.solid("Glass_S", (-0.05, 0.0, 0.8), (0.05, 3.4, 5.0), "glass")
        S.solid("Sofa_W", (-6.5, 0.0, -4.6), (-3.5, 0.9, -3.6), "magenta")
        S.solid("Sofa_E", (3.5, 0.0, -4.6), (6.5, 0.9, -3.6), "magenta")
    return croom("rdwe_mirror_room", "The mirror room: the reflection's door is real", 16, 10, 3.4,
                 [("three", "S", -4.0, D(to="rdwe_three_doors")), ("moon", "W", 0.0, D(to="rdwe_moon_window")),
                  ("reflection", "S", 4.0, D(to="rdwe_dont_look", look="the door in the reflection: mirror-image of the way you came, real"))], keys,
                 "Psychological puzzle: the room is doubled across a glass line; the door on your side is the way back, the same door in the "
                 "reflection is the way on, and the gap in the mirror lets you through.", "teal", fmat="white", wmat="magenta",
                 trick=("trick", (-2.0, 0.0, 0.0), (1, 0), "the mirror's gap: step through to the reflection"))


def c_dont_look():
    def keys(S):
        S.solid("Statue", (3.0, 0.0, -0.5), (4.0, 2.4, 0.5), "statue")
        S.solid("Plinth_1", (-3.0, 0.0, -4.2), (-2.0, 1.2, -3.2), "statue")
        S.solid("Plinth_2", (-3.0, 0.0, 3.2), (-2.0, 1.2, 4.2), "statue")
    return croom("rdwe_dont_look", "Don't look away: the statue moves", 14, 10, 4.0,
                 [("mirror", "W", 0.0, D(to="rdwe_mirror_room")), ("statue", "E", 0.0, D(to="rdwe_wrong_clock"))], keys,
                 "Psychological puzzle: a gallery whose statue stands in front of the door and moves only when you are not looking; walk to the "
                 "door backwards.", "teal", fmat="marble_f", wmat="white",
                 trick=("statue", (0.0, 0.0, 0.0), (1, 0), "it is closer every time you blink"))


def c_waiting_room():
    def keys(S):
        for k in range(3):
            z = -2.0 + k * 1.8
            S.solid(f"Seats_{k + 1}", (-4.0, 0.0, z), (2.0, 0.45, z + 0.5), "cyan")
        S.solid("Ticket_Machine", (5.6, 0.0, 3.4), (6.4, 1.4, 4.2), "red")
        S.decor("Number_Display", (2.0, 2.2, -5.0), (4.0, 2.7, -4.96), "red")
    return croom("rdwe_waiting_room", "The waiting room: take a number", 14, 10, 3.0,
                 [("three", "W", 0.0, D(to="rdwe_three_doors")), ("number", "N", 3.0, D(to="rdwe_wrong_clock"))], keys,
                 "Psychological puzzle: rows of seats, a ticket machine and a number display; the door opens only when your number comes up, "
                 "and it counts down when you sit.", "teal", fmat="office", wmat="mint",
                 trick=("ticket", (5.0, 0.0, 2.6), (1, 0), "take a ticket: your number is the number of rooms left"))


def c_wrong_clock():
    def keys(S):
        for k in range(4):
            z = -4.5 + k * 3.0
            S.solid(f"Clock_{k + 1}", (5.0, 0.0, z - 0.3), (5.6, 2.4, z + 0.3), "wood")
    return croom("rdwe_wrong_clock", "The clock room: one runs backward", 12, 12, 4.5,
                 [("gallery", "W", 0.0, D(to="rdwe_dont_look")), ("waiting", "S", -3.0, D(to="rdwe_waiting_room")),
                  ("hands", "N", 3.0, D(to="rdwe_crossroads"))], keys,
                 "Psychological puzzle: a room of grandfather clocks; the one that runs backward is the teal room's watch, and stopping it "
                 "opens the north door.", "teal", fmat="wood", wmat="blood",
                 trick=("clock", (4.0, 0.0, -1.5), (1, 0), "the backward clock: stop it to open the north door"))


def c_crossroads():
    def keys(S):
        for nm, x0, x1, z0, z1 in (("NW", -16.0, -4.0, -16.0, -4.0), ("NE", 4.0, 16.0, -16.0, -4.0), ("SW", -16.0, -4.0, 4.0, 16.0), ("SE", 4.0, 16.0, 4.0, 16.0)):
            S.solid(f"Block_{nm}", (x0, 0.0, z0), (x1, 4.0, z1), "acid")
        S.solid("Lamp_Post", (-0.15, 0.0, -0.15), (0.15, 2.6, 0.15), "steel")
        S.decor("Skylight", (-3.0, 3.98, -3.0), (3.0, 4.0, 3.0), "sky", ("ceiling",))
    S = croom("rdwe_crossroads", "The crossroads: four corridors", 32, 32, 4.0,
              [("west", "W", 0.0, D(to="rdwe_tilted_hall")), ("north", "N", 0.0, D(to="rdwe_wrong_clock")),
               ("south", "S", 0.0, D(to="rdwe_trampoline (the padded vent)")), ("east", "E", 0.0, D(to="rdwe_elevator_lobby"))], keys,
              "Multi-choice navigation: four corridors meet under a painted skylight, each ending in a door to a different part of the house.",
              "inst", fmat="concrete", wmat="acid", trick=("trick", (2.0, 0.0, 2.0), (0, -1), "every arm looks like the one you came down"))
    S.corridor("arm_W", -15.0, -4.5, -3.5, 3.5)
    S.corridor("arm_E", 4.5, 15.0, -3.5, 3.5)
    return S


def c_changing_rooms():
    def keys(S):
        S.solid("Lockers", (-6.0, 0.0, 4.4), (2.0, 2.0, 5.0), "locker")
        S.solid("Bench", (-3.0, 0.0, -0.2), (3.0, 0.45, 0.2), "wood")
        S.zone("water", "puddles", (-7.0, 0.0, -5.0), (7.0, 0.03, -2.0))
    return croom("rdwe_changing_rooms", "The changing rooms: a pool that is not there", 14, 10, 3.0,
                 [("flooded", "N", -4.0, D(to="rdwe_flooded (the frame door)")), ("locker", "E", 2.0, D(to="rdwe_laundromat",
                                                                                                       look="a locker door, man-sized, number 13"))],
                 keys, "Environmental storytelling: wet changing rooms for a pool you never find, towels still damp, one locker big enough to "
                       "walk into.", "inst", fmat="tile", wmat="tile",
                 trick=("locker", (-1.0, 0.0, 3.4), (0, 1), "every locker holds the same towel, still warm"))


def c_laundromat():
    def keys(S):
        for k in range(6):
            x = -7.4 + k * 1.3
            S.solid(f"Washer_{k + 1}", (x, 0.0, -4.0), (x + 1.0, 1.0, -3.2), "washer")
        S.solid("Folding_Table", (-2.0, 0.0, 0.6), (2.0, 0.9, 1.6), "white")
    return croom("rdwe_laundromat", "The laundromat: the drum is a door", 16, 8, 3.2,
                 [("lockers", "W", 0.0, D(to="rdwe_changing_rooms")), ("drum", "N", 4.0, D(to="rdwe_motel_room", width=1.4, height=1.6,
                                                                                         look="a washing machine's round glass door, 1.4 m across"))],
                 keys, "Object distortion: a row of washers and one machine the size of a car; its round door is the way on, the drum still turning.",
                 "inst", fmat="vinyl", wmat="cyan",
                 trick=("trick", (4.0, 0.0, -1.6), (0, -1), "the big drum turns once every time you look away"))


def c_motel_room():
    def keys(S):
        S.solid("Bed", (-2.2, 0.0, 0.0), (0.4, 0.6, 2.4), "peach")
        S.solid("TV_Stand", (1.8, 0.0, 0.6), (2.8, 1.0, 1.8), "black")
    return croom("rdwe_motel_room", "The motel room: the TV shows this room", 6, 10, 2.8,
                 [("drum", "W", -2.0, D(to="rdwe_laundromat")), ("bathroom", "N", 1.5, D(to="rdwe_office_night"))], keys,
                 "Environmental storytelling: a motel room whose TV shows this room from the corner, with you in it, a second late.", "inst",
                 fmat="carpet_tan", wmat="peach", trick=("tv", (0.8, 0.0, 1.2), (1, 0), "the TV: you, a second ago"))


def c_office_night():
    def keys(S):
        for i in range(3):
            for j in range(2):
                x0, z0 = -9.0 + i * 6.0, -6.0 + j * 7.0
                S.solid(f"Partition_{i}_{j}", (x0, 0.0, z0), (x0 + 4.0, 1.4, z0 + 0.1), "office")
        S.decor("Monitor", (-0.2, 0.75, -5.6), (0.4, 1.1, -5.5), "cyan")
    return croom("rdwe_office_night", "The office at night: one monitor on", 24, 20, 3.0,
                 [("stairs", "W", -6.0, D(to="rdwe_motel_room")), ("lift", "N", 6.0, D(to="rdwe_elevator_lobby"))], keys,
                 "Environmental storytelling: an open-plan office after hours, every chair pushed in but one, and one monitor on with the "
                 "notebook's first entry typed out.", "inst", fmat="carpet_tan", wmat="office",
                 trick=("monitor", (0.0, 0.0, -4.6), (0, -1), "the lit monitor: the notebook's first entry"))


def c_elevator_lobby():
    def keys(S):
        S.solid("Call_Pillar", (-0.4, 0.0, 0.4), (0.4, 1.3, 1.2), "steel")
    return croom("rdwe_elevator_lobby", "The elevator lobby: four lifts, four places", 18, 10, 3.6,
                 [("crossroads", "S", 0.0, D(to="rdwe_crossroads")), ("lift_1", "N", -6.0, D(to="rdwe_office_night")),
                  ("lift_2", "N", -2.0, D(to="rdwe_map_room")), ("lift_3", "N", 2.0, D(to="rdwe_repeating_room")),
                  ("lift_4", "N", 6.0, D(to="rdwe_vending_room"))], keys,
                 "Multi-choice navigation: four lift doors, no two alike, and a call button with no numbers; each lift opens somewhere else.",
                 "inst", fmat="marble_f", wmat="steel",
                 trick=("buttons", (0.0, 0.0, 2.2), (0, -1), "the call button has no numbers"))


def c_map_room():
    def keys(S):
        S.solid("Map_Table", (-3.0, 0.0, -3.0), (3.0, 0.9, 3.0), "map")
    return croom("rdwe_map_room", "The map room: the notebook on a table", 12, 12, 3.4,
                 [("lift", "S", 0.0, D(to="rdwe_elevator_lobby")), ("door", "N", 0.0, D(to="rdwe_melting_library"))], keys,
                 "Environmental storytelling: a table-sized model of the rooms you have seen, joined by string not by space, the notebook "
                 "made real; the rooms you have not found are blank.", "inst", fmat="wood", wmat="map",
                 trick=("map", (0.0, 0.0, 4.0), (0, -1), "the map: a graph of connections, not of space"))


def c_vending_room():
    def keys(S):
        S.solid("Machine_1", (-3.8, 0.0, -4.0), (-2.8, 1.9, -3.2), "red")
        S.solid("Machine_2", (-2.6, 0.0, -4.0), (-1.6, 1.9, -3.2), "cyan")
        S.solid("Machine_3", (2.6, 0.0, -4.0), (3.6, 1.9, -3.2), "acid")
    return croom("rdwe_vending_room", "The vending room: the machine is the door", 8, 8, 3.0,
                 [("lift", "S", 0.0, D(to="rdwe_elevator_lobby")), ("machine", "N", 0.6, D(to="rdwe_grocery (the stockroom)", width=1.0, height=1.9,
                                                                                          look="a vending machine's glass front, lit, that swings open")),
                  ("real", "W", 0.0, D(fake=True, look="a plain door marked EXIT that never opens"))], keys,
                 "Psychological puzzle: a room of vending machines and a door marked EXIT that never opens; the machine in the middle swings "
                 "open on the grocery's stockroom.", "inst", fmat="vinyl", wmat="navy",
                 trick=("trick", (0.6, 0.0, -1.0), (0, -1), "the EXIT door is the only one that is not a door"))


def c_melting_library():
    def keys(S):
        for k, x in enumerate((-4.0, 4.0), 1):
            for j in range(3):
                dx = (j * 0.35) * (1 if k == 1 else -1)
                S.solid(f"Shelf_{k}_{j + 1}", (x - 0.4 + dx, j * 1.4, -4.0), (x + 0.4 + dx, (j + 1) * 1.4, 4.0), "book")
    return croom("rdwe_melting_library", "The melting library: shelves that sag", 14, 14, 5.0,
                 [("map", "S", -3.0, D(to="rdwe_map_room")), ("arch", "N", 3.0, D(to="rdwe_repeating_room"))], keys,
                 "Object distortion: two rows of shelves that lean and sag into each other like wax, the books sliding; the arch at the end is "
                 "the way deeper.", "inst", fmat="wood", wmat="blood",
                 trick=("book", (0.0, 0.0, 0.0), (0, -1), "every book has the same first line"))


MATS.setdefault("marble_f", (0.80, 0.78, 0.74))
MATS.setdefault("checker", (0.85, 0.85, 0.85))

# ---------------------------------------------------------------- the set, in the order of the lists (A, then B, then C)
SCENES = {
    "rdwe_dining": dining, "rdwe_hallway": hallway, "rdwe_teal": teal, "rdwe_teal2": teal2, "rdwe_flooded": flooded,
    "rdwe_trampoline": trampoline, "rdwe_grocery": grocery,
    "rdwe_repeating_room": repeating_room, "rdwe_finale": finale,
    "rdwe_long_table": c_long_table, "rdwe_tiny_kitchen": c_tiny_kitchen, "rdwe_birthday_party": c_birthday_party, "rdwe_attic": c_attic,
    "rdwe_kids_bedroom": c_kids_bedroom, "rdwe_giant_chair": c_giant_chair, "rdwe_upside_room": c_upside_room,
    "rdwe_door_hall": c_door_hall, "rdwe_stretching_hall": c_stretching_hall, "rdwe_bending_hall": c_bending_hall,
    "rdwe_stair_loop": c_stair_loop, "rdwe_tilted_hall": c_tilted_hall, "rdwe_three_doors": c_three_doors,
    "rdwe_painted_door": c_painted_door, "rdwe_anamorphic_room": c_anamorphic_room,
    "rdwe_void_room": c_void_room, "rdwe_lights_out": c_lights_out, "rdwe_green_grid": c_green_grid, "rdwe_ames_room": c_ames_room,
    "rdwe_shrink_hall": c_shrink_hall, "rdwe_moon_window": c_moon_window, "rdwe_mirror_room": c_mirror_room,
    "rdwe_dont_look": c_dont_look, "rdwe_waiting_room": c_waiting_room, "rdwe_wrong_clock": c_wrong_clock, "rdwe_crossroads": c_crossroads,
    "rdwe_changing_rooms": c_changing_rooms, "rdwe_laundromat": c_laundromat, "rdwe_motel_room": c_motel_room,
    "rdwe_office_night": c_office_night, "rdwe_elevator_lobby": c_elevator_lobby, "rdwe_map_room": c_map_room,
    "rdwe_vending_room": c_vending_room, "rdwe_melting_library": c_melting_library,
}
PHASE_A = [s for s in SCENES if s in ("rdwe_dining", "rdwe_hallway", "rdwe_teal", "rdwe_teal2", "rdwe_flooded", "rdwe_trampoline", "rdwe_grocery")]
PHASE_B = ["rdwe_repeating_room", "rdwe_finale"]
PHASE_C = [s for s in SCENES if s not in PHASE_A and s not in PHASE_B]
GODS = ["rdwe_nyx", "rdwe_selene", "rdwe_hypnos", "rdwe_morpheus", "rdwe_oneiros", "rdwe_thanatos"]   # reserved: built elsewhere

# How the rooms join. Each pair is one link: F at one side's Link_<door> puts you at the other side's Arrive_<door>. kind: doors, stairs,
# one_way (the first side leads to the second; the second side's Link_ is the arrival door, which does not open back), sleep, fall.
PAIRS = [
    # the story (the spine): the seven rooms in the order the game plays them, then the loop and the finale
    (("rdwe_dining", "stairs"), ("rdwe_hallway", "dining"), "stairs", "the green stairs up to the corridor they never reached"),
    (("rdwe_hallway", "well"), ("rdwe_teal", "well"), "stairs", "down the mossy well into the teal room"),
    (("rdwe_teal", "sleep"), ("rdwe_teal2", "sleep"), "one_way", "close your eyes on the couch: you wake in the arched room"),
    (("rdwe_teal2", "arch"), ("rdwe_flooded", "arch"), "one_way", "through the arch before it finishes; it seals behind you"),
    (("rdwe_flooded", "grate"), ("rdwe_trampoline", "vent"), "one_way", "the grate gives way: the fall down the shaft, out of a vent"),
    (("rdwe_trampoline", "glow"), ("rdwe_grocery", "glow"), "one_way", "walk to the red glow: the anomaly"),
    (("rdwe_grocery", "exit"), ("rdwe_dining", "loop"), "one_way", "the EXIT closes the loop: you are back in the dining room"),
    (("rdwe_grocery", "entrance"), ("rdwe_finale", "grocery"), "one_way", "the locked entrance opens once the map is complete: the finale"),
    # the house: off the dining room and the hallway's side doors
    (("rdwe_dining", "pantry"), ("rdwe_long_table", "dining"), "doors", ""),
    (("rdwe_long_table", "kitchen"), ("rdwe_tiny_kitchen", "table"), "doors", ""),
    (("rdwe_long_table", "party"), ("rdwe_birthday_party", "table"), "doors", ""),
    (("rdwe_birthday_party", "attic"), ("rdwe_attic", "party"), "stairs", "a door to the attic stairs"),
    (("rdwe_attic", "hatch"), ("rdwe_kids_bedroom", "hatch"), "hatch", "down through the floor hatch (and back up)"),
    (("rdwe_kids_bedroom", "closet"), ("rdwe_hallway", "door_a"), "doors", "the closet opens on the hallway"),
    (("rdwe_tiny_kitchen", "back"), ("rdwe_giant_chair", "kitchen"), "doors", ""),
    (("rdwe_giant_chair", "high"), ("rdwe_upside_room", "chair"), "doors", "the door 3 m up the wall"),
    (("rdwe_upside_room", "hall"), ("rdwe_hallway", "door_b"), "doors", ""),
    # the halls: off the hallway
    (("rdwe_hallway", "door_c"), ("rdwe_door_hall", "hallway"), "doors", ""),
    (("rdwe_door_hall", "d3"), ("rdwe_stretching_hall", "doors"), "doors", ""),
    (("rdwe_door_hall", "d6"), ("rdwe_three_doors", "back"), "doors", ""),
    (("rdwe_door_hall", "d9"), ("rdwe_painted_door", "doors"), "doors", ""),
    (("rdwe_stretching_hall", "far"), ("rdwe_bending_hall", "start"), "doors", ""),
    (("rdwe_bending_hall", "lap"), ("rdwe_stair_loop", "hall"), "doors", "the door that is there on the third lap"),
    (("rdwe_stair_loop", "landing"), ("rdwe_tilted_hall", "stairs"), "doors", ""),
    (("rdwe_tilted_hall", "end"), ("rdwe_crossroads", "west"), "doors", ""),
    (("rdwe_three_doors", "left"), ("rdwe_mirror_room", "three"), "doors", ""),
    (("rdwe_three_doors", "middle"), ("rdwe_waiting_room", "three"), "doors", ""),
    (("rdwe_three_doors", "right"), ("rdwe_lights_out", "three"), "doors", ""),
    (("rdwe_painted_door", "painted"), ("rdwe_anamorphic_room", "painted"), "doors", "the painted door, from its mark"),
    (("rdwe_anamorphic_room", "word"), ("rdwe_ames_room", "word"), "doors", "the door the shards draw"),
    # the teal wing: behind the teal rooms
    (("rdwe_teal", "void"), ("rdwe_void_room", "teal"), "doors", "into the black square doorway"),
    (("rdwe_void_room", "lit"), ("rdwe_lights_out", "void"), "doors", ""),
    (("rdwe_teal2", "grid"), ("rdwe_green_grid", "teal2"), "doors", "behind the peeled wallpaper"),
    (("rdwe_green_grid", "seam"), ("rdwe_ames_room", "grid"), "doors", ""),
    (("rdwe_ames_room", "small"), ("rdwe_shrink_hall", "ames"), "doors", ""),
    (("rdwe_shrink_hall", "small"), ("rdwe_moon_window", "hall"), "doors", ""),
    (("rdwe_moon_window", "sill"), ("rdwe_mirror_room", "moon"), "doors", ""),
    (("rdwe_mirror_room", "reflection"), ("rdwe_dont_look", "mirror"), "doors", "the door in the reflection"),
    (("rdwe_dont_look", "statue"), ("rdwe_wrong_clock", "gallery"), "doors", ""),
    (("rdwe_waiting_room", "number"), ("rdwe_wrong_clock", "waiting"), "doors", ""),
    (("rdwe_wrong_clock", "hands"), ("rdwe_crossroads", "north"), "doors", ""),
    # the institution: off the flooded corridor, the trampoline park and the grocery, down to the repeating room
    (("rdwe_flooded", "frame"), ("rdwe_changing_rooms", "flooded"), "doors", "the frame door"),
    (("rdwe_changing_rooms", "locker"), ("rdwe_laundromat", "lockers"), "doors", ""),
    (("rdwe_laundromat", "drum"), ("rdwe_motel_room", "drum"), "doors", "through the drum"),
    (("rdwe_motel_room", "bathroom"), ("rdwe_office_night", "stairs"), "doors", ""),
    (("rdwe_trampoline", "bounce"), ("rdwe_crossroads", "south"), "doors", "the padded vent"),
    (("rdwe_crossroads", "east"), ("rdwe_elevator_lobby", "crossroads"), "doors", ""),
    (("rdwe_elevator_lobby", "lift_1"), ("rdwe_office_night", "lift"), "lift", ""),
    (("rdwe_elevator_lobby", "lift_2"), ("rdwe_map_room", "lift"), "lift", ""),
    (("rdwe_elevator_lobby", "lift_3"), ("rdwe_repeating_room", "lift"), "lift", ""),
    (("rdwe_elevator_lobby", "lift_4"), ("rdwe_vending_room", "lift"), "lift", ""),
    (("rdwe_vending_room", "machine"), ("rdwe_grocery", "stockroom"), "doors", "the vending machine swings open on the stockroom"),
    (("rdwe_map_room", "door"), ("rdwe_melting_library", "map"), "doors", ""),
    (("rdwe_melting_library", "arch"), ("rdwe_repeating_room", "library"), "doors", ""),
]
# Links whose both ends are in one room (it loops on itself)
SELF = {("rdwe_stair_loop", "top"): "the top door arrives at the foot of the same stairs (a Penrose loop)",
        ("rdwe_repeating_room", "again"): "the north door arrives through the south door: the same room, changed"}
# Links that leave the set: the other side is not built here. (scene, door): (connector, link id, where the other side is)
OUTSIDE = {
    ("rdwe_dining", "house"): ("doors", "built: forest.house>rdwe and the Overworld gate DoorLeaf_Gate_RDW (both arrive in room dining)",
                               "the way in: the dreamcore house's door in the meadow, and the gate on L4; they arrive here, facing the stairs"),
    ("rdwe_finale", "win"): ("doors", "planned: rdwe.finale>grocery (its `from` names room grocery; the coordinator may move it to rdwe_finale)",
                             "grocery.main_floor: the one ending, once every camera is off"),
    ("rdwe_repeating_room", "secret_ops"): ("gate", "planned: rdwe.repeating_room>secret_ops", "secret_ops.hidden_entry: the one entrance with "
                                                                                                  "no clearance"),
    ("rdwe_trampoline", "gods"): ("doors", "reserved: the six god rooms (chapters H to M, built elsewhere)",
                                  "rdwe_nyx, the first god room; the god rooms' own doors decide their order"),
    ("rdwe_grocery", "gods"): ("doors", "reserved: the arrival from the last god room", "rdwe_thanatos, the last god room, comes out here"),
}


def phase_ids(ph):
    out = []
    for p in ph:
        out += {"A": PHASE_A, "B": PHASE_B, "C": PHASE_C}[p]
    return out


_LOOKS = {}


def build(sid):
    """The scene, with every door's look filled in (unique across the set: the explicit ones, then the rest in a fixed order)."""
    S = SCENES[sid]()
    if not _LOOKS:
        explicit = set()
        rest = []
        for s2 in SCENES:
            for d in SCENES[s2]().doors:
                if "look" in d["props"]:
                    explicit.add(d["props"]["look"])
                else:
                    rest.append((s2, d["name"]))
        k = 0
        for key in rest:                                  # mixed radix over a bijection, so the looks never repeat
            while True:
                j = (k * 397) % NLOOK
                k += 1
                f, fi, ha = j % len(FORMS), (j // len(FORMS)) % len(FINISHES), j // (len(FORMS) * len(FINISHES))
                lk = f"{FORMS[f]} {FINISHES[fi]} door, {HANDLES[ha]}"
                if lk not in explicit:
                    _LOOKS[key] = lk
                    break
    for d in S.doors:
        if "look" not in d["props"]:
            d["props"]["look"] = _LOOKS[(sid, d["name"])]
    return S


def plan_views(S):
    bs = [b for b in S.boxes if b.get("art") and not b.get("zone")]
    xs = [v for b in bs for v in (b["min"][0], b["max"][0])]
    zs = [v for b in bs for v in (b["min"][2], b["max"][2])]
    m = 1.2
    return [_view(f"L{int(lv)}", lv, min(xs) - m, max(xs) + m, min(zs) - m, max(zs) + m, 1500.0) for lv in S.levels]


def _view(key, lv, x0, x1, z0, z1, ppm_target):
    span = max(x1 - x0, z1 - z0)
    ppm = min(ppm_target / span, 110.0)
    return {"key": key, "level": lv, "x0": x0, "x1": x1, "z0": z0, "z1": z1, "W": int(round((x1 - x0) * ppm)), "H": int(round((z1 - z0) * ppm)), "ppm": ppm}


def plan_hidden(S, b, level):
    if "ceiling" in b["tags"]:
        return True
    if b["name"].startswith("Step_"):
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
                   + [("D", d["name"], d) for d in S.doors] + [("K", "COL_" + b["name"], b) for b in S.boxes if b["col"]]
                   + [("S", c["name"], c) for c in S.cams], key=lambda t: t[1])
    for kind, n, o in items:
        if kind == "K":
            out["colliders"].append({"s": o["name"], "min": [_r(v) for v in o["min"]], "max": [_r(v) for v in o["max"]]})
        elif kind == "C" and o.get("zone"):
            out["zones"].append({"kind": o["zone"], "name": n, "min": [_r(v) for v in o["min"]], "max": [_r(v) for v in o["max"]]})
        elif kind == "S":
            ff = _face(o["face"])
            out["cameras"].append(export_scene.camera_doc(S.id, n, o["pos"], ff, o["props"]))
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
def _blocked(cols, p, r=WALKER_R):
    x, y, z = p
    for c in cols:
        if c["min"][1] < y + 1.5 and c["max"][1] > y + 0.5 and c["min"][0] - r < x < c["max"][0] + r and c["min"][2] - r < z < c["max"][2] + r:
            return c
    return None


def _on_floor(cols, p):
    return any(abs(c["max"][1] - p[1]) <= 0.06 and c["min"][0] <= p[0] <= c["max"][0] and c["min"][2] <= p[2] <= c["max"][2] for c in cols)


def check(base, ids=None):
    """The gates: links pair (both ways where they are meant to), the set is navigable and has no true exit, colliders do not overlap, every
    link, arrival, spot and spawn has clearance and a floor, steps keep to the rise, corridors are wide and clear, the spots each room needs
    are there, every door is different, every exit has its one Link_. Reads <base>/world/<scene>.json; True if all pass."""
    ids = ids or list(SCENES)
    built = set(ids)
    docs, bad = {}, []
    for sid in ids:
        f = out_path(base, sid)
        if not f.exists():
            bad.append(f"missing {f}")
            continue
        docs[sid] = json.loads(f.read_text())
    models = {sid: build(sid) for sid in ids}
    have = {(sid, l["door"]) for sid, d in docs.items() for l in d.get("links", [])}
    paired, waiting = set(), []
    for a, b, kind, note in PAIRS:
        for side, other in ((a, b), (b, a)):
            paired.add(side)
            if side[0] in docs and side not in have:
                bad.append(f"link {side[0]}.{side[1]} ({kind} to {other[0]}) is not in {side[0]}.json")
            if side[0] in built and other[0] not in built:
                waiting.append(f"{side[0]}.{side[1]} -> {other[0]}")
    for side in sorted(have):
        if side not in paired and side not in OUTSIDE and side not in SELF:
            bad.append(f"link {side[0]}.{side[1]} has no other side in PAIRS, SELF or OUTSIDE")
    for side in list(OUTSIDE) + list(SELF):
        if side[0] in docs and side not in have:
            bad.append(f"link {side[0]}.{side[1]} is not in {side[0]}.json")
    npairs = sum(1 for a, b, _, _ in PAIRS if a[0] in built and b[0] in built)
    print(f"GATE links: {npairs} pairs with both sides built ({npairs * 2} sides, the one-way ones included), {sum(1 for s in SELF if s[0] in built)} "
          f"that loop on their own room, {sum(1 for s in OUTSIDE if s[0] in built)} that leave the set; {len(have)} links in the files, every one "
          f"accounted for")
    if waiting:
        print(f"  waiting for a later phase ({len(waiting)}): " + "; ".join(waiting))
    # navigable, and no true exit: from the dining room you reach every built room, and every room (the finale aside) reaches back to it
    fwd = {s: set() for s in built}
    for (a, _), (b, _), kind, _ in PAIRS:
        if a in built and b in built:
            fwd[a].add(b)
            if kind != "one_way":
                fwd[b].add(a)

    def reach(start, g):
        seen, todo = set(), [start]
        while todo:
            s = todo.pop()
            if s not in seen:
                seen.add(s)
                todo += list(g[s])
        return seen
    if "rdwe_dining" in built:
        r1 = reach("rdwe_dining", fwd)
        back = {s: set() for s in built}
        for s, outs in fwd.items():
            for t in outs:
                back[t].add(s)
        r2 = reach("rdwe_dining", back)
        full = set(ids) >= set(PHASE_A + PHASE_B + PHASE_C)
        if built - r1 and full:
            bad.append(f"not reachable from rdwe_dining: {sorted(built - r1)}")
        elif built - r1:
            print(f"  not reachable yet (their doors lead to rooms of a later phase): {', '.join(sorted(built - r1))}")
        stuck = sorted(built - r2 - {"rdwe_finale"})
        if stuck and full:
            bad.append(f"no way back to rdwe_dining from: {stuck}")
        elif stuck:
            print(f"  no way back yet (their other doors are in a later phase): {', '.join(stuck)}")
        print(f"GATE navigable: {len(r1)} of {len(built)} rooms reachable from rdwe_dining; {len(r2)} can get back to it (no true exit: the "
              f"finale's one way out is the ending)")
    # overlaps: no two colliders interpenetrate by more than 1 cm on every axis
    nov, novp = 0, 0
    for sid, d in docs.items():
        cols = d["colliders"]
        for i in range(len(cols)):
            a = cols[i]
            for j in range(i + 1, len(cols)):
                b = cols[j]
                if all(min(a["max"][k], b["max"][k]) - max(a["min"][k], b["min"][k]) > 0.01 for k in range(3)):
                    nov += 1
                    if nov <= 12:
                        bad.append(f"overlap {sid}: {a['s']} and {b['s']}")
        novp += len(cols) * (len(cols) - 1) // 2
    print(f"GATE overlaps: {nov} interpenetrating collider pairs of {novp} checked (none allowed)")
    # clearances: every link's F and arrival, every spot and spawn, clear of the colliders by the walker's radius with a floor under the feet;
    # and 1 m clear in front of every door, inside
    npts, nclear = 0, 0
    for sid, d in docs.items():
        cols = d["colliders"]
        pts = [(f"link {l['door']} at", l["at"]) for l in d["links"]] + [(f"link {l['door']} arrive", l["arrive"]) for l in d["links"]]
        pts += [(f"spot {s['name']}", s["position"]) for s in d["spots"]] + [(f"marker {m['name']}", m["position"]) for m in d["markers"]]
        for nm, p in pts:
            npts += 1
            b = _blocked(cols, p)
            if b:
                bad.append(f"clearance {sid}: {nm} {p} is inside {b['s']}")
            elif not _on_floor(cols, p):
                bad.append(f"clearance {sid}: {nm} {p} has no floor under it")
        for dr in d["doors"]:
            if dr.get("opens") == "never" and dr["name"] != "DoorLeaf_secret_ops":
                pass
            th = math.radians(dr["closed_yaw_deg"])
            hx, hy, hz = dr["hinge"]
            ex, ez = hx + dr["width"] * math.cos(th), hz - dr["width"] * math.sin(th)
            mx, mz = (hx + ex) / 2, (hz + ez) / 2
            sw = math.radians(dr["closed_yaw_deg"] + (90 if dr["swing_deg"] > 0 else -90))
            ix, iz = math.cos(sw), -math.sin(sw)                 # the side the leaf opens toward: into the room
            for dist in (0.5, 1.0):
                p = [mx + ix * dist, hy, mz + iz * dist]
                b = _blocked(cols, p, r=0.2)
                nclear += 1
                if b:
                    bad.append(f"door clearance {sid}: {dr['name']} is blocked {dist} m in by {b['s']}")
                    break
    print(f"GATE clearances: {npts} links, arrivals, spots and spawns clear by {WALKER_R} m with a floor under them; {nclear} door-front "
          f"points (0.5 and 1 m in) clear")
    # steps
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
    print(f"GATE steps: {nsteps} step boxes in {sum(len(models[s].flights) for s in ids)} flights, one box a step; the highest rise {worst:.3f} m "
          f"(at most {MAX_RISE} m)")
    # corridors
    ncor, narrow = 0, 99.0
    for sid in ids:
        cols = docs.get(sid, {}).get("colliders", [])
        for c in models[sid].corridors:
            ncor += 1
            w = min(c["max"][0] - c["min"][0], c["max"][2] - c["min"][2])
            narrow = min(narrow, w)
            if w < MIN_CORRIDOR - 1e-6:
                bad.append(f"corridor {sid}/{c['name']} is {w:.2f} m wide")
            y = c["min"][1]
            for k in cols:
                e = 0.005
                if k["min"][1] < y + 1.5 and k["max"][1] > y + 0.5 and k["min"][0] < c["max"][0] - e and k["max"][0] > c["min"][0] + e \
                        and k["min"][2] < c["max"][2] - e and k["max"][2] > c["min"][2] + e:
                    bad.append(f"corridor {sid}/{c['name']}: {k['s']} stands in it")
                    break
    print(f"GATE corridors: {ncor} corridor rects, the narrowest {narrow:.2f} m (at least {MIN_CORRIDOR} m), none blocked")
    # extent
    big = 0.0
    for sid, d in docs.items():
        cs = [c for c in d["colliders"] if not c["s"].startswith("Beyond_")]
        for i in (0, 2):
            sz = max(c["max"][i] for c in cs) - min(c["min"][i] for c in cs)
            big = max(big, sz)
            if sz > MAX_EXTENT + 1.0:
                bad.append(f"extent {sid}: {sz:.1f} m along {'xz'[i // 2]}")
    print(f"GATE extent: the largest room is {big:.1f} m across (a store floor, about {MAX_EXTENT:g} m, at most)")
    # spots present
    nsp = {}
    for sid, d in docs.items():
        kinds = {}
        for s in d["spots"]:
            kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
            nsp[s["kind"]] = nsp.get(s["kind"], 0) + 1
        for k, n in models[sid].need_spots.items():
            if kinds.get(k, 0) < n:
                bad.append(f"spots {sid}: {kinds.get(k, 0)} Spot_{k}, needs {n}")
        if not d["spots"]:
            bad.append(f"spots {sid}: none (each room needs its trick's spot)")
        if sid == "rdwe_finale" and len(d["cameras"]) < 8:
            bad.append(f"cameras rdwe_finale: {len(d['cameras'])} SecCam, needs 8 or more")
    ncam = sum(len(d["cameras"]) for d in docs.values())
    print(f"GATE spots: every room has its trick's spot and the ones it needs; {ncam} SecCam; " + ", ".join(f"{k} x{v}" for k, v in sorted(nsp.items())))
    # every door different; every exit one Link_
    looks, sizes, nd, nfake, narr = {}, {}, 0, 0, 0
    for sid, d in docs.items():
        lk = {l["door"] for l in d["links"]}
        for dr in d["doors"]:
            nd += 1
            key = dr.get("look")
            if not key:
                bad.append(f"door {sid}/{dr['name']} has no look")
            elif key in looks:
                bad.append(f"door {sid}/{dr['name']} looks like {looks[key]}: '{key}'")
            looks[key] = f"{sid}/{dr['name']}"
            did = dr["name"][len("DoorLeaf_"):]
            if dr.get("opens") == "never":
                nfake += 1
                if did in lk:
                    bad.append(f"door {sid}/{dr['name']} never opens but has a link")
            elif dr.get("arrival_of"):
                narr += 1
            elif did not in lk:
                bad.append(f"door {sid}/{dr['name']}: an exit with no Link_{did}")
    print(f"GATE doors: {nd} door leaves, no two with the same look; {nd - nfake - narr} exits with one Link_ each, {narr} arrival-only, "
          f"{nfake} that never open; every exit fixed")
    for b in bad:
        print("  FAIL", b)
    print("GATES", "FAIL" if bad else "PASS")
    return not bad


# ================================================================ Blender
def _blender_main(argv):
    import bpy
    from mathutils import Matrix, Vector

    a = argv
    sel = a[a.index("--scenes") + 1] if "--scenes" in a else "all"
    ids = list(SCENES) if sel == "all" else phase_ids(sel) if set(sel) <= set("ABC") else sel.split(",")
    base = Path(a[a.index("--out") + 1]) if "--out" in a else ROOT / "work/rdwe_greybox"
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
            bsdf.inputs["Roughness"].default_value = 0.8 if name not in ("glass", "water", "tile") else 0.1
            if name in EMISSIVE:
                for key in ("Emission Color", "Emission"):
                    if key in bsdf.inputs:
                        bsdf.inputs[key].default_value = (*c, 1.0)
                        break
                if "Emission Strength" in bsdf.inputs:
                    bsdf.inputs["Emission Strength"].default_value = EMISSIVE[name]
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
    v = [(x, y, z) for x in (0, 1) for y in (-0.03, 0.03) for z in (0, 1)]
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
            if b.get("art", True):
                ob = boxobj(b["name"], b, "Art")
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

    def drop_lights():
        for ob in list(bpy.data.objects):
            if ob.type in ("LIGHT", "CAMERA"):
                bpy.data.objects.remove(ob, do_unlink=True)

    def render_plan(S, arts, pv, path):
        level = pv["level"]
        for ob, b in arts:
            ob.hide_render = plan_hidden(S, b, level) if "tags" in b and b.get("name") else False
            if len(S.levels) > 1 and b.get("name") and "min" in b and b["min"][1] < level - 0.7 and level > 0 and not b["name"].startswith("Step_"):
                ob.hide_render = ob.hide_render or (b.get("max", [0, 99, 0])[1] < level - 0.7)
        drop_lights()
        world((1.0, 1.0, 1.0), 0.55)
        add_light("SUN", (0, 0, 50), 1.7, "Plan_Sun", rot=(math.radians(2), math.radians(1), 0))
        cam = camera("Plan_Cam")
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = max(pv["x1"] - pv["x0"], pv["z1"] - pv["z0"])
        cam.data.clip_start, cam.data.clip_end = 0.1, 200.0
        cam.location = ((pv["x0"] + pv["x1"]) / 2, -(pv["z0"] + pv["z1"]) / 2, level + 2.39)
        cam.data.clip_start = 0.0
        cam.rotation_euler = (0, 0, 0)
        cam.location.z = level + 60.0
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = pv["W"], pv["H"], 100
        sc.cycles.samples = 16
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)

    def render_still(S, arts, path):
        for ob, b in arts:
            ob.hide_render = False
        drop_lights()
        world((0.6, 0.6, 0.62), 0.12)
        for i, (x, y, z, p) in enumerate(S.lights):
            add_light("POINT", B((x, y, z)), p, f"L{i}", size=0.4)
        (pos, face, pitch) = S.still
        cam = camera("Still_Cam")
        cam.data.lens, cam.data.sensor_width = 16.0, 36.0
        cam.data.clip_start, cam.data.clip_end = 0.05, 300.0
        cam.location = B((pos[0], pos[1] + EYE, pos[2]))
        yaw = math.atan2(face[0], face[1])
        cam.rotation_euler = (math.radians(90 + pitch), 0, math.pi + yaw)
        add_light("POINT", B((pos[0], pos[1] + 2.0, pos[2])), 40, "CamFill", size=0.5)
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1280, 720, 100
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

    dev = setup_cycles(32)
    print("RDWE_GREYBOX device", dev, "scenes", len(ids))
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
        print(f"RDWE_GREYBOX done {sid}: {len(S.boxes)} boxes, {len(S.doors)} doors, {len(S.empties)} empties, {len(S.cams)} cameras")
    print("RDWE_GREYBOX ALL DONE")


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
        inside = True
    except ImportError:
        inside = False
    a = sys.argv
    ph = a[a.index("--phase") + 1] if "--phase" in a else "ABC"
    if inside:
        _blender_main(a[a.index("--") + 1:] if "--" in a else [])
    elif "--preview" in a:
        base = Path(a[a.index("--preview") + 1])
        for sid in phase_ids(ph):
            p = out_path(base, sid)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(doc_of(build(sid)), indent=1) + "\n")
        print(f"wrote {len(phase_ids(ph))} layout files under {base}")
    elif "--check" in a:
        sys.exit(0 if check(Path(a[a.index("--check") + 1]), phase_ids(ph)) else 1)
    else:
        print(__doc__)
