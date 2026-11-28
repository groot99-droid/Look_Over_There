"""The grocery greybox (docs/BLENDER_AREAS.md, section 2, "The grocery, the rest"): the four scenes beyond part 1's main_floor as plain grey
boxes, to scale, with the names the exporter reads (COL_, DoorLeaf_, Marker_, Link_/Arrive_, SecCam_, Zone_, Spot_, decor_), so the owner can
review the whole layout at once. It follows tools/blender/build_hotel_greybox.py.

    blender -b --factory-startup --python tools/blender/build_grocery_greybox.py -- [--scenes all|id,id,...] [--out <dir>] [--no-render]
    python tools/blender/build_grocery_greybox.py --check <dir>      the gates on exported files, no Blender (links meet, steps, corridors)
    python tools/blender/build_grocery_greybox.py --preview <dir>    writes the layout files from the model alone, no Blender (for --check)

For each scene the Blender run builds the boxes into an empty file, writes <out>/world/<scene>.json through tools/blender/export_scene.py,
the greybox art to <out>/glb/<scene>.glb, a top-down orthographic plan per level (<out>/renders/<scene>_plan_L<y>.png, ceilings and
everything 2.4 m above the level hidden) and one eye-height still (1.55 m, <out>/renders/<scene>_still.png). The labels, scale bar and sheets
are drawn afterwards by tools/blender/grocery_greybox_sheets.py from this same model.

Coordinates are GAME coordinates (metres, y up, north = -z); Blender (x, y, z) is game (x, -z, y). Every scene has its floor at y = 0.
All four scenes share main_floor's x and z (shared/city.js GROCERY: the hall is x -12 to 12, z -9 to 9, its walls 0.2 m thick), so the
openings meet it exactly:
  - aisles lies north of main_floor: its south wall IS main_floor's north wall (z -9.2 to -9.0), and its opening is the 3.6 m gap between
    main_floor's two cooler banks (x -1.8 to 1.8, under the security camera at x 0, y 3.4).
  - back_of_house lies east of main_floor: its west wall IS main_floor's east wall (x 12.0 to 12.2), and its staff door is main_floor's
    closed pair of staff doors (z -6.3 to -4.7, 2.2 m high).
  - second_floor is the mezzanine over aisles' west side (x -24 to -4, z -44.2 to -14.2; in aisles its slab top is at y 5).
  - basement lies under back_of_house (the same x and z; back_of_house's floor is 4 m above it): its stairs and the freight lift's shaft
    stand under back_of_house's.
Repetition reuses one mesh: every box is the same unit cube per material, scaled (colliders and art share it), and every door leaf is one leaf
mesh. Each COL_<name> box has its art twin <name>; decor_ boxes have no collider. Zones are hidden boxes. Nothing here touches the manifest,
index.html or shared/.
"""
import json
import math
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
    "tile": (0.80, 0.83, 0.85), "lift": (0.30, 0.38, 0.52), "fake_door": (0.40, 0.28, 0.20), "column": (0.45, 0.45, 0.45),
    "gondola": (0.78, 0.78, 0.76), "endcap": (0.55, 0.10, 0.08), "rack": (0.20, 0.32, 0.55), "beam": (0.75, 0.42, 0.08),
    "pallet": (0.52, 0.40, 0.24), "freezer": (0.70, 0.80, 0.86), "plant": (0.34, 0.42, 0.36), "glass": (0.70, 0.85, 0.90),
    "cart_red": (0.75, 0.06, 0.05), "monitor": (0.05, 0.05, 0.06), "safe": (0.35, 0.50, 0.40), "dock": (0.55, 0.50, 0.12),
    "water": (0.12, 0.38, 0.80), "below": (0.48, 0.48, 0.46),
}


# ================================================================ the model (pure Python; no bpy)
class Scene:
    def __init__(s, sid, title, size, levels=(0.0,), mood=""):
        s.id, s.title, s.size, s.levels, s.mood = sid, title, size, list(levels), mood
        s.boxes, s.empties, s.doors, s.labels, s.lights, s.corridors, s.flights, s.outlines = [], [], [], [], [], [], [], []
        s.links = {}            # door id -> text (where it goes), for the plan labels
        s.still = None          # (pos, face, pitch_deg)
        s.level_names = {}
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

    def zone(s, kind, name, mn, mx):
        n = s.uniq(f"Zone_{kind}_{name}")
        s.boxes.append({"name": n, "min": list(mn), "max": list(mx), "mat": "water", "col": False, "zone": kind, "tags": set()})

    def empty(s, name, pos, face=None, props=None):
        s.empties.append({"name": s.uniq(name), "pos": [float(v) for v in pos], "face": face, "props": dict(props or {})})

    def link(s, door, at, arrive, face, to=""):
        s.empty(f"Link_{door}", at)
        s.empty(f"Arrive_{door}", arrive, face=face)
        s.links[door] = to

    def spot(s, kind, n, pos, face=(0, 1), props=None):
        s.empty(f"Spot_{kind}_{n}", pos, face=face, props=props)

    def seccam(s, n, pos, face, props=None):
        """A security camera (restricted areas): SecCam_<nn> at its mount, facing `face`; the exporter writes it to `cameras`."""
        s.empty(f"SecCam_{n:02d}", pos, face=face, props=props)

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
    """n steps from a floor at y_start up to y_end, one box per step (each as thick as its rise, so a flight above a floor leaves headroom).
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
    S.flights.append({"name": name, "y_start": y_start, "y_end": y_end, "n": n, "rise": round(rise, 4), "tread": tread,
                      "end": start + direction * n * tread})


def box(S, name, x0, x1, z0, z1, y0, y1, mat="furniture"):
    return S.solid(name, (x0, y0, z0), (x1, y1, z1), mat)


def double_door(S, name, axis, at, c0, c1, into, width=1.6, height=2.2, props=None):
    """A pair of leaves filling a `width` opening centred on `at` along a wall on `axis` ('z': the wall runs along z at x = c0; 'x': along x at
    z = c0); `into` is the side they open toward. Returns the two leaf names' base."""
    half = width / 2
    p = dict(props or {})
    if axis == "z":
        S.door(f"{name}_A", (c0, 0.0, at - half), (0, 1), into, width=half, height=height, props=p)
        S.door(f"{name}_B", (c0, 0.0, at + half), (0, -1), into, width=half, height=height, props=p)
    else:
        S.door(f"{name}_A", (at - half, 0.0, c0), (1, 0), into, width=half, height=height, props=p)
        S.door(f"{name}_B", (at + half, 0.0, c0), (-1, 0), into, width=half, height=height, props=p)


# ---------------------------------------------------------------- main_floor, as part 1 built it (shared/city.js GROCERY; read only)
MF = {"x0": -12.0, "x1": 12.0, "z0": -9.0, "z1": 9.0, "h": 4.0,
      "opening": (-1.8, 1.8, 3.0),            # aisles' opening in main_floor's north wall: x from, x to, height (between the cooler banks)
      "staff": (-6.3, -4.7, 2.2),             # main_floor's staff doors on its east wall: z from, z to, height (build_main_floor.py STAFF)
      "camera": (0.0, 3.4, -8.7)}             # its security camera (shared/city.js CAMERA)


# ---------------------------------------------------------------- aisles
AX0, AX1, AZ0, AZ1, AH = -24.0, 24.0, -49.2, -9.2, 8.5        # 48 m by 40 m, 8.5 m high (the mezzanine stands in its west half)
MEZ = {"x0": -24.0, "x1": -4.0, "z0": -44.2, "z1": -14.2, "y": 5.0, "h": 3.2}   # second_floor's footprint, and its floor's height in aisles
LAND = {"x0": -4.0, "x1": -0.6, "z0": -24.0, "z1": -21.2}      # the landing at the top of the stairs and the escalator, in front of the mezzanine
STAIR_LANE, ESC_LANE = (-3.8, -2.2), (-2.0, -0.8)
OPEN_STAIR, OPEN_ESC = -22.0, -23.3                           # the glass doors in the mezzanine's front, centres along z
CLEAR = {"x0": -0.4, "x1": 10.8, "z0": -35.0, "z1": -24.6}     # the red-cart clearing (IMG_3027, a label only), in the middle of the hall
GZ0, GZ1 = -45.6, -12.6                                       # the gondola runs: north and south cross aisles beyond them
G_EAST = [1.8 + 3.6 * i for i in range(6)]                    # gondola centres (1.2 m wide, 2.4 m aisles), east of the stairs
G_WEST = [-21.1 + 3.6 * i for i in range(5)]                  # and under the mezzanine
GW, GH = 1.2, 1.9


def mezzanine_front(S, y0, h, nm, doors_into):
    """The mezzanine's glazed front on x -4.2 to -4.0: a 1.1 m rail with glass above, and two glass doors (stairs, escalator) at the landing."""
    holes = [(OPEN_STAIR - 0.5, OPEN_STAIR + 0.5, y0, y0 + DOOR_H), (OPEN_ESC - 0.5, OPEN_ESC + 0.5, y0, y0 + DOOR_H)]
    wall(S, f"{nm}_Rail", "z", -4.2, -4.0, MEZ["z0"], MEZ["z1"], y0, y0 + 1.1, holes, "rail")
    wall(S, f"{nm}_Glass", "z", -4.2, -4.0, MEZ["z0"], MEZ["z1"], y0 + 1.1, y0 + h, holes, "glass")
    for did, zc in (("stairs", OPEN_STAIR), ("escalator", OPEN_ESC)):
        S.door(f"glass_{did}", (-4.0, y0, zc - 0.5), (0, 1), doors_into, width=1.0, height=DOOR_H, props={"kind": "glass door"})


def gondola_runs(x, z0, z1, cut):
    """A gondola's runs from z0 to z1, broken where it would cross the clearing `cut` (x0, x1, z0, z1)."""
    if cut and x + GW / 2 > cut["x0"] and x - GW / 2 < cut["x1"]:
        return [(z0, cut["z0"]), (cut["z1"], z1)]
    return [(z0, z1)]


def gondolas(S, xs, tag, cut=None, food=True, cols=()):
    k = 0
    for x in xs:
        for za, zb in gondola_runs(x, GZ0, GZ1, cut):
            k += 1
            box(S, f"Gondola_{tag}{k}", x - GW / 2, x + GW / 2, za + 0.3, zb - 0.3, 0.0, GH, "gondola")
            box(S, f"Endcap_{tag}{k}", x - GW / 2, x + GW / 2, za, za + 0.3, 0.0, GH, "endcap")
            box(S, f"Endcap_{tag}{k}", x - GW / 2, x + GW / 2, zb - 0.3, zb, 0.0, GH, "endcap")
            if food:
                S.spot("food", f"{tag}{k}", (x + GW / 2 + 0.55, 0.0, (za + zb) / 2), face=(-1, 0), props={"shelf": f"Gondola_{tag}{k}", "side": "east"})
    return k


def aisles():
    S = Scene("aisles", "Aisles", "48 m by 40 m, 8.5 m high: long gondola aisles, the red-cart clearing, the mezzanine's underside on the west",
              levels=(0.0, MEZ["y"]), mood="open by day, abandoned by night")
    S.level_names = {0.0: "the shop floor", MEZ["y"]: "the landing (y 5)"}
    ox0, ox1, oh = MF["opening"]
    shell(S, "Aisles", AX0, AX1, AZ0, AZ1, 0.0, AH, holes={"S": [((ox0 + ox1) / 2, ox1 - ox0, oh)]})
    S.link("main_floor", (0.0, 0.0, AZ1 - 0.7), (0.0, 0.0, AZ1 - 1.4), (0, -1), "main_floor (the opening in its north wall)")
    S.marker("Spawn", (0.0, 0.0, AZ1 - 1.4))
    S.label("opening from main_floor", 0.0, AZ1 + 1.0, kind="note")
    S.corridor("opening", ox0 + 0.01, ox1 - 0.01, AZ1 - 0.2, AZ1 + 0.2)
    # the mezzanine's underside: the slab (y 4.7 to 5), its front columns and two rows of columns inside gondolas, the glazed front above
    S.solid("Mezzanine_Slab", (MEZ["x0"], MEZ["y"] - SLAB, MEZ["z0"]), (MEZ["x1"], MEZ["y"], MEZ["z1"]), "floor")
    for zc in (-14.6, -20.0, -28.0, -36.0, -43.8):
        S.solid("Mezz_Column", (-4.4, 0.0, zc - 0.2), (-4.0, MEZ["y"] - SLAB, zc + 0.2), "column")
    for zc in (-18.0, -29.2, -40.4):
        S.solid("Mezz_Column", (-14.0, 0.0, zc - 0.2), (-13.6, MEZ["y"] - SLAB, zc + 0.2), "column")
    mezzanine_front(S, MEZ["y"], AH - MEZ["y"], "Mezz_Front", (-1, 0))
    S.outlines.append({"x0": MEZ["x0"], "x1": MEZ["x1"], "z0": MEZ["z0"], "z1": MEZ["z1"], "text": "second_floor over here\n(mezzanine slab, y 5)"})
    # the stairs and the escalator up to the landing, side by side, rising north
    flight(S, "stairs_up", *STAIR_LANE, -15.9, -1, "z", 0.0, MEZ["y"], 19, 0.28)
    flight(S, "escalator_up", *ESC_LANE, -15.8, -1, "z", 0.0, MEZ["y"], 20, 0.27)
    S.solid("Landing", (LAND["x0"], MEZ["y"] - SLAB, LAND["z0"]), (LAND["x1"], MEZ["y"], LAND["z1"]), "floor")
    S.solid("Landing_Rail_N", (LAND["x0"], MEZ["y"], LAND["z0"] - 0.1), (LAND["x1"], MEZ["y"] + 1.1, LAND["z0"]), "rail")
    S.solid("Landing_Rail_E", (LAND["x1"] - 0.1, MEZ["y"], LAND["z0"]), (LAND["x1"], MEZ["y"] + 1.1, LAND["z1"]), "rail")
    S.link("stairs_up", (-3.5, MEZ["y"], OPEN_STAIR), (-3.0, MEZ["y"], -21.6), (0, 1), "second_floor (stairs)")
    S.link("escalator_up", (-3.5, MEZ["y"], OPEN_ESC), (-1.4, MEZ["y"], -21.6), (0, 1), "second_floor (escalator)")
    S.label("stairs", -3.0, -14.9, kind="note")
    S.label("escalator", -1.4, -14.3, kind="note")
    S.label("landing (y 5)", -2.3, -24.8, MEZ["y"], kind="note")
    # the long aisles: gondolas running north to south, red end caps, broken by the clearing; under the mezzanine too
    gondolas(S, G_EAST, "E", cut=CLEAR)
    gondolas(S, G_WEST, "W")
    for i, x in enumerate([AX1 - 0.4]):
        box(S, "Wall_Shelving_E", x - 0.2, AX1, GZ0, GZ1, 0.0, 2.2, "gondola")
    box(S, "Wall_Shelving_N", -3.0, 22.0, AZ0, AZ0 + 0.6, 0.0, 2.2, "gondola")
    for k, x in enumerate((0.0, 12.0), 1):
        S.spot("food", f"N{k}", (x + 4.0, 0.0, AZ0 + 1.2), face=(0, -1), props={"shelf": "Wall_Shelving_N", "side": "south"})
    S.spot("food", "WallE", (AX1 - 1.0, 0.0, -30.0), face=(1, 0), props={"shelf": "Wall_Shelving_E", "side": "west"})
    # the red-cart clearing: carts the page draws, in a ring
    cx, cz = (CLEAR["x0"] + CLEAR["x1"]) / 2, (CLEAR["z0"] + CLEAR["z1"]) / 2
    for k in range(8):
        a = 2 * math.pi * k / 8
        S.spot("cart", k + 1, (cx + 3.2 * math.cos(a), 0.0, cz + 3.2 * math.sin(a)), face=(-math.sin(a), math.cos(a)), props={"color": "red", "where": "the clearing"})
    S.decor("Clearing_Mark", (cx - 4.6, 0.0, cz - 4.6), (cx + 4.6, 0.01, cz + 4.6), "cart_red")
    S.label("RED-CART CLEARING", cx, cz - 0.9)
    S.label("(IMG_3027, a label only)", cx, cz + 0.6, kind="note")
    # a cart corral by the opening, the camera heads (the page draws them, as main_floor's), and the night's threats
    box(S, "Cart_Corral", 4.0, 7.0, -10.4, -9.4, 0.0, 1.0, "rail")
    for k, x in enumerate((4.6, 5.5, 6.4), 1):
        S.spot("cart", f"corral_{k}", (x, 0.0, -11.0), face=(0, 1), props={"where": "the corral by the opening"})
    for k, (x, z, f, mz) in enumerate(((-6.0, -48.4, (0, 1), AZ0), (23.3, -11.0, (-0.7, -0.7), AZ1), (-23.3, -11.0, (0.7, -0.7), AZ1)), 1):
        S.spot("camhead", k, (x, 0.0, z), face=f, props={"mount_height": 3.6, "what": "a camera head like main_floor's (code)"})
    for k, (x, z) in enumerate(((cx, cz), (-8.4, -46.6), (22.0, -47.2)), 1):
        S.spot("monster", k, (x, 0.0, z), face=(0, 1), props={"when": "night", "what": "a night threat (code)"})
    S.label("AISLES", 14.0, -16.0)
    S.label("under the mezzanine", -14.0, -16.0, kind="note")
    for c in range(len(G_EAST) - 1):               # the aisles between the east gondolas, and the cross aisles
        x0, x1 = G_EAST[c] + GW / 2, G_EAST[c + 1] - GW / 2
        for za, zb in ((GZ0, CLEAR["z0"]), (CLEAR["z1"], GZ1)):
            S.corridor(f"aisle_E{c + 1}_{'n' if za == GZ0 else 's'}", x0 + 0.01, x1 - 0.01, za, zb)
    for c in range(len(G_WEST) - 1):
        S.corridor(f"aisle_W{c + 1}", G_WEST[c] + GW / 2 + 0.01, G_WEST[c + 1] - GW / 2 - 0.01, GZ0, GZ1)
    S.corridor("front_cross_aisle", AX0 + 0.01, AX1 - 0.01, GZ1 + 0.01, -10.81)
    S.corridor("back_cross_aisle", AX0 + 0.01, AX1 - 0.61, AZ0 + 0.61, GZ0 - 0.01)
    S.corridor("mezzanine_front_walk", G_WEST[-1] + GW / 2 + 0.01, -4.41, GZ0, GZ1)
    S.still = ((0.0, 0.0, AZ1 - 1.4), (-0.25, -1.0), 6)
    for x in range(-20, 24, 8):
        for z in (-14, -22, -30, -38, -46):
            S.light(x, MEZ["y"] - 0.6 if x < -4 else AH - 0.5, z, 350 if x > -4 else 120)
    S.light(-2.3, MEZ["y"] + 2.5, -22.5, 120)
    return S


# ---------------------------------------------------------------- second_floor (the mezzanine)
def second_floor():
    S = Scene("second_floor", "Second floor (the mezzanine)", "30 m by 20 m (20 m east to west, 30 m north to south), 3.2 m high, glazed over the aisles",
              mood="open by day, abandoned by night")
    x0, x1, z0, z1, h = MEZ["x0"], MEZ["x1"] - 0.2, MEZ["z0"], MEZ["z1"], MEZ["h"]
    shell(S, "Mezzanine", x0, x1, z0, z1, 0.0, h, sides="NSW")
    S.solid("Front_Floor", (x1, -SLAB, z0 - T), (MEZ["x1"], 0.0, z1 + T), "floor")
    mezzanine_front(S, 0.0, h, "Front", (1, 0))
    # the landing outside the glass doors, railed all round: the stairs and the escalator go down from its south edge
    S.solid("Landing", (LAND["x0"], -SLAB, LAND["z0"]), (LAND["x1"], 0.0, LAND["z1"]), "floor")
    S.solid("Landing_Rail_N", (LAND["x0"], 0.0, LAND["z0"] - 0.1), (LAND["x1"], 1.1, LAND["z0"]), "rail")
    S.solid("Landing_Rail_E", (LAND["x1"] - 0.1, 0.0, LAND["z0"]), (LAND["x1"], 1.1, LAND["z1"]), "rail")
    S.solid("Landing_Rail_S", (LAND["x0"], 0.0, LAND["z1"] - 0.15), (LAND["x1"], 1.1, LAND["z1"]), "rail")
    for i in range(6):                              # the tops of the two flights, going down (art: the flights are in aisles)
        y = -0.26 * (i + 1)
        S.decor(f"Stair_Down_{i}", (STAIR_LANE[0], y - 0.26, LAND["z1"] + 0.28 * i), (STAIR_LANE[1], y, LAND["z1"] + 0.28 * (i + 1)), "stair")
        S.decor(f"Escalator_Down_{i}", (ESC_LANE[0], y - 0.25, LAND["z1"] + 0.27 * i), (ESC_LANE[1], y, LAND["z1"] + 0.27 * (i + 1)), "stair")
    S.link("stairs_down", (-3.0, 0.0, -21.8), (-4.9, 0.0, OPEN_STAIR), (-1, 0), "aisles (stairs down)")
    S.link("escalator_down", (-1.4, 0.0, -21.8), (-4.9, 0.0, OPEN_ESC), (-1, 0), "aisles (escalator down)")
    S.marker("Spawn", (-4.9, 0.0, OPEN_STAIR))
    S.label("landing", -2.3, -24.6, kind="note")
    # the view down: the aisles below, as art only (beyond the glass; nothing to walk on)
    yb = -MEZ["y"]
    S.decor("Below_Floor", (-4.0, yb - 0.02, AZ0), (AX1, yb, AZ1), "below", tags=("below",))
    for x in G_EAST:
        for za, zb in gondola_runs(x, GZ0, GZ1, CLEAR):
            S.decor("Below_Gondola", (x - GW / 2, yb, za), (x + GW / 2, yb + GH, zb), "gondola", tags=("below",))
    cx, cz = (CLEAR["x0"] + CLEAR["x1"]) / 2, (CLEAR["z0"] + CLEAR["z1"]) / 2
    S.decor("Below_Clearing", (cx - 4.6, yb, cz - 4.6), (cx + 4.6, yb + 0.01, cz + 4.6), "cart_red", tags=("below",))
    for k in range(8):
        a = 2 * math.pi * k / 8
        px, pz = cx + 3.2 * math.cos(a), cz + 3.2 * math.sin(a)
        S.decor("Below_Cart", (px - 0.3, yb, pz - 0.45), (px + 0.3, yb + 1.0, pz + 0.45), "cart_red", tags=("below",))
    S.label("the aisles, 5 m below (art only)", 5.0, -30.0, kind="note")
    # homeware: low gondolas and display tables in the north half
    for k, x in enumerate((-21.0, -17.4, -13.8, -10.2), 1):
        box(S, f"Homeware_Gondola_{k}", x - 0.6, x + 0.6, -42.0, -31.0, 0.0, 1.5, "gondola")
        box(S, f"Homeware_Endcap_{k}", x - 0.6, x + 0.6, -31.3, -31.0, 0.0, 1.5, "endcap")
    for k, (x, z) in enumerate(((-7.6, -40.0), (-7.6, -34.0)), 1):
        box(S, f"Display_Table_{k}", x - 0.9, x + 0.9, z - 0.9, z + 0.9, 0.0, 0.8, "furniture")
    S.label("HOMEWARE", -15.6, -29.4)
    # the closed café in the south-west corner: a counter with its shutter down, tables with the chairs up on them, a low barrier
    S.solid("Cafe_Wall_N", (x0, 0.0, -24.4), (-17.0, 3.0, -24.2))
    S.solid("Cafe_Wall_E", (-17.2, 0.0, -24.2), (-17.0, 3.0, -19.6))
    box(S, "Cafe_Counter", -23.4, -17.8, -23.6, -22.8, 0.0, 1.1, "counter")
    S.solid("Cafe_Shutter", (-23.4, 1.1, -23.0), (-17.8, 2.6, -22.8), "fake_door")
    S.solid("Cafe_Barrier", (-17.0, 0.0, -24.2), (-14.0, 0.9, -24.0), "rail")
    for k, (x, z) in enumerate(((-21.6, -19.0), (-19.0, -19.0), (-21.6, -16.4), (-19.0, -16.4), (-15.8, -16.4)), 1):
        box(S, f"Cafe_Table_{k}", x - 0.4, x + 0.4, z - 0.4, z + 0.4, 0.0, 0.75)
        S.decor(f"Cafe_Chairs_Up_{k}", (x - 0.35, 0.75, z - 0.35), (x + 0.35, 1.2, z + 0.35))
    S.label("CLOSED CAFE", -20.3, -21.4)
    S.label("shutter down", -20.6, -24.2, kind="note")
    # what the page places: a camera head, carts, the night's threats, and the lookout over the aisles
    S.spot("camhead", 1, (-23.3, 0.0, -43.5), face=(0.7, 0.7), props={"mount_height": 2.9, "what": "a camera head (code)"})
    S.spot("cart", 1, (-6.0, 0.0, -27.0), face=(0, 1), props={"where": "left by the glass"})
    S.spot("monster", 1, (-12.0, 0.0, -36.5), face=(0, 1), props={"when": "night", "what": "a night threat (code)"})
    S.spot("monster", 2, (-15.2, 0.0, -19.0), face=(-1, 0), props={"when": "night", "what": "a night threat (code)"})
    S.spot("lookout", 1, (-4.8, 0.0, -30.0), face=(1, 0), props={"what": "the view down over the aisles and the clearing"})
    S.corridor("glass_walk", -6.6, -4.21, z0 + 0.01, z1 - 0.01)
    hx = (-21.0, -17.4, -13.8, -10.2)
    for k in range(3):
        S.corridor(f"homeware_aisle_{k + 1}", hx[k] + 0.61, hx[k + 1] - 0.61, -42.0, -31.0)
    S.corridor("cross_walk", x0 + 0.01, -4.21, -30.9, -25.0)
    S.still = ((-5.0, 0.0, -29.8), (1.0, 0.0), -32)
    for x in (-20, -14, -8):
        for z in (-40, -32, -24, -17):
            S.light(x, h - 0.3, z, 150)
    S.light(-2.3, 2.2, -22.5, 60)
    for x in (0.0, 8.0, 16.0):
        for z in (-40.0, -30.0, -20.0):
            S.light(x, -1.5, z, 500)
    return S


# ---------------------------------------------------------------- back_of_house
BX0, BX1, BZ0, BZ1, BH = 12.2, 42.2, -9.0, 15.0, 4.5          # 30 m by 24 m, 4.5 m high, east of main_floor
ROOMS_Z = 7.0                                                 # the staff rooms' north wall (z 7.0 to 7.2); the rooms run to the south wall
RACK_ROWS = [(-8.9, -7.8), (-5.2, -4.1), (-1.5, -0.4), (2.2, 3.3)]
RACK_X = (15.6, 30.0)
LIFT = {"x0": 37.4, "x1": 41.0, "z0": 10.2, "z1": 14.0, "door": (38.0, 40.4), "h": 2.4}   # the freight lift's car, and its gate on the car's north side
STAIR = {"x0": 32.4, "x1": 35.8, "door_x": 34.1, "foot": 13.0, "top": 8.8}   # the flight rises north from z 13 (foot) to 8.8 (the landing)             # the basement stairwell under back_of_house's stair door


def back_of_house():
    S = Scene("back_of_house", "Back of house (restricted)", "30 m by 24 m, 4.5 m high (staff rooms 3 m)", mood="restricted: staff only")
    za, zb, zh = MF["staff"]
    zc = (za + zb) / 2
    shell(S, "BOH", BX0, BX1, BZ0, BZ1, 0.0, BH, holes={"W": [(zc, zb - za, zh)]})
    # the staff door from main_floor: its closed pair, now opening (into back_of_house)
    double_door(S, "staff", "z", zc, BX0, None, (1, 0), width=zb - za, height=zh, props={"kind": "staff door"})
    S.link("main_floor", (BX0 + 0.6, 0.0, zc), (BX0 + 1.3, 0.0, zc), (1, 0), "main_floor (its staff door, east wall)")
    S.marker("Spawn", (BX0 + 1.3, 0.0, zc))
    S.label("staff door from main_floor", BX0 + 2.6, zc + 1.0, kind="note")
    S.zone("restricted", "back_of_house", (BX0, 0.0, BZ0), (BX1, BH, BZ1))
    # the stockroom: four rows of pallet racking (uprights and two beam levels as one box a row), forklift aisles between
    for k, (r0, r1) in enumerate(RACK_ROWS, 1):
        box(S, f"Racking_{k}", RACK_X[0], RACK_X[1], r0, r1, 0.0, 4.0, "rack")
        S.decor(f"Racking_Beam_{k}", (RACK_X[0], 1.6, r0 - 0.02), (RACK_X[1], 1.75, r1 + 0.02), "beam")
        S.decor(f"Racking_Beam_{k}", (RACK_X[0], 3.2, r0 - 0.02), (RACK_X[1], 3.35, r1 + 0.02), "beam")
        if k > 1:
            S.spot("food", f"stock_{k}", (22.8, 0.0, r0 - 0.6), face=(0, 1), props={"where": "stockroom racking", "shelf": f"Racking_{k}"})
    S.label("STOCKROOM", 22.8, -6.5)
    S.label("racking", 22.8, -3.0, kind="note")
    # the loading dock: three dock doors on the east wall (they do not open), levellers, pallets waiting
    for k, zd in enumerate((-6.5, -1.5, 3.5), 1):
        S.solid("Dock_Door", (BX1 - 0.06, 0.0, zd - 1.4), (BX1, 3.2, zd + 1.4), "fake_door")
        S.decor(f"Dock_Leveller_{k}", (BX1 - 2.2, 0.0, zd - 1.1), (BX1, 0.02, zd + 1.1), "dock")
        S.solid("Dock_Bumper", (BX1 - 0.3, 0.2, zd - 1.6), (BX1 - 0.06, 0.6, zd - 1.4), "rail")
        S.solid("Dock_Bumper", (BX1 - 0.3, 0.2, zd + 1.4), (BX1 - 0.06, 0.6, zd + 1.6), "rail")
        S.spot("dock", k, (BX1 - 1.0, 0.0, zd), face=(1, 0), props={"what": "a dock door that does not open: a truck later"})
    for k, (x, z, hh) in enumerate(((33.4, -8.0, 1.4), (33.4, -6.6, 0.9), (35.0, 1.0, 1.6), (33.4, 1.0, 0.15)), 1):
        box(S, "Pallet", x - 0.6, x + 0.6, z - 0.5, z + 0.5, 0.0, hh, "pallet")
    S.label("LOADING DOCK", 38.0, -4.0)
    # the staff rooms along the south wall: break room, lockers, the manager's office, the basement stairs, the freight lift's lobby
    rooms = [("break", BX0, 20.0, 16.1), ("lockers", 20.2, 25.0, 22.6), ("office", 25.2, 32.0, 28.6), ("stairs", 32.2, 36.0, STAIR["door_x"])]
    holes = [(d - DOOR_W / 2, d + DOOR_W / 2, 0.0, DOOR_H) for _, _, _, d in rooms] + [(LIFT["door"][0] - 0.2, LIFT["door"][1] + 0.2, 0.0, 2.6)]
    wall(S, "Rooms_Wall_N", "x", ROOMS_Z, ROOMS_Z + T, BX0, BX1, 0.0, 3.0, holes)
    S.solid("Rooms_Ceiling", (BX0, 3.0, ROOMS_Z), (BX1, 3.2, BZ1), "ceiling", ("ceiling",))
    for xw in (20.0, 25.0, 32.0, 36.0):
        S.solid("Rooms_Partition", (xw, 0.0, ROOMS_Z + T), (xw + T, 3.0, BZ1), "wall")
    for name, a0, a1, d in rooms:
        if name == "stairs":
            S.door("basement_stairs", (d - DOOR_W / 2, 0.0, ROOMS_Z + T), (1, 0), (0, 1), props={"kind": "stair door"})
        else:
            S.door(name, (d - DOOR_W / 2, 0.0, ROOMS_Z + T), (1, 0), (0, 1))
    # break room
    box(S, "Break_Table", 14.4, 17.2, 10.4, 11.6, 0.0, 0.75)
    for x in (14.8, 16.8):
        for z in (9.9, 12.1):
            box(S, "Break_Chair", x - 0.22, x + 0.22, z - 0.22, z + 0.22, 0.0, 0.9)
    box(S, "Break_Counter", BX0, 13.0, 8.4, 14.6, 0.0, 0.9, "counter")
    box(S, "Vending", 18.6, 19.8, 14.2, 15.0, 0.0, 1.9, "lift")
    box(S, "Break_Fridge", BX0, 12.95, 7.4, 8.3, 0.0, 1.85, "lift")       # the dressing's fridge, at the counter's north end
    S.spot("hide", 1, (18.9, 0.0, 9.4), face=(0, 1), props={"where": "behind the break room door"})
    S.label("BREAK ROOM", 16.1, 13.6)
    # lockers
    box(S, "Lockers_W", 20.2, 20.7, 8.0, 14.6, 0.0, 1.9, "lift")
    box(S, "Lockers_E", 24.5, 25.0, 8.0, 14.6, 0.0, 1.9, "lift")
    box(S, "Locker_Bench", 22.2, 23.0, 9.6, 13.4, 0.0, 0.45)
    for k, (x, z, f) in enumerate(((21.2, 9.4, (-1, 0)), (21.2, 12.8, (-1, 0)), (24.0, 9.4, (1, 0)), (24.0, 12.8, (1, 0))), 1):
        S.spot("locker", k, (x, 0.0, z), face=f)
    S.label("LOCKERS", 22.6, 14.4)
    # the manager's office: a desk facing a bank of camera monitors (the page shows the SecCam_ feeds on it)
    box(S, "Office_Desk", 26.6, 29.4, 11.0, 11.8, 0.0, 0.75)
    S.solid("Monitor_Bank", (25.4, 0.8, 13.2), (31.8, 2.4, 13.6), "monitor")
    box(S, "Monitor_Shelf", 25.4, 31.8, 13.2, BZ1, 0.0, 0.8, "counter")    # the console runs under the bank (the dressing stands the CRTs on it)
    box(S, "Office_Cabinet", 30.6, 31.8, 7.4, 8.4, 0.0, 1.3)
    S.spot("monitor", 1, (28.6, 0.0, 12.6), face=(0, 1), props={"what": "the camera monitors: the SecCam_ feeds (code)"})
    S.spot("hide", 2, (31.2, 0.0, 9.6), face=(-1, 0), props={"where": "behind the office cabinet"})
    S.label("MANAGER'S OFFICE", 28.6, 9.0)
    S.label("camera monitors", 28.6, 14.4, kind="note")
    # the stair door: the top landing behind it (the stairs down are in basement)
    S.link("basement_stairs", (STAIR["door_x"], 0.0, ROOMS_Z - 0.6), (STAIR["door_x"], 0.0, ROOMS_Z - 1.3), (0, -1), "basement (stairs down)")
    S.solid("Stair_Rail", (STAIR["x0"], 0.0, STAIR["top"]), (STAIR["x1"], 1.0, STAIR["top"] + 0.15), "rail")
    S.decor("Stair_Well", (STAIR["x0"], 0.0, STAIR["top"] + 0.15), (STAIR["x1"], 0.01, BZ1), "stair")
    S.label("stairs down", 34.1, 12.4)
    # the freight lift: its gate on the car's north side, the car behind (a placeholder), the keycard reader by the gate
    shell(S, "LiftCar", LIFT["x0"], LIFT["x1"], LIFT["z0"] + T, LIFT["z1"], 0.0, LIFT["h"] + 0.4, sides="SWE", wmat="lift", fmat="lift", floor=False)
    wall(S, "Lift_Wall_N", "x", LIFT["z0"], LIFT["z0"] + T, 36.2, BX1, 0.0, 3.0, [(LIFT["door"][0], LIFT["door"][1], 0.0, LIFT["h"])], "lift")
    dw = LIFT["door"][1] - LIFT["door"][0]
    S.door("freight_lift", (LIFT["door"][0], 0.0, LIFT["z0"]), (1, 0), (0, 1), width=dw, height=LIFT["h"], props={"kind": "freight lift gate"})
    S.solid("Keycard_Reader", (40.9, 1.1, LIFT["z0"] - 0.08), (41.2, 1.5, LIFT["z0"]), "monitor")
    S.spot("keycard", 1, (41.05, 0.0, LIFT["z0"] - 0.7), face=(0, -1),
           props={"requires": "keycard_tier_1", "opens": "secret_ops", "what": "the reader: swipe keycard_tier_1 and the lift goes on past the basement"})
    S.link("freight_down", (38.6, 0.0, LIFT["z0"] - 0.6), (38.6, 0.0, LIFT["z0"] - 1.4), (0, -1), "basement (the freight lift)")
    S.link("secret_ops", (39.8, 0.0, LIFT["z0"] - 0.6), (39.8, 0.0, LIFT["z0"] - 1.4), (0, -1),
           "secret_ops/service_entry (grocery.backhouse>secret_ops, needs keycard_tier_1)")
    S.label("FREIGHT LIFT", 39.2, 12.1)
    S.label("keycard reader", 41.3, 9.0, kind="note")
    # the security cameras (restricted): high in the corners, facing in
    cams = [((12.6, 3.6, -8.6), (0.7, 0.7), 0.1), ((41.8, 3.6, -8.6), (-0.7, 0.7), 0.4), ((12.6, 3.6, 6.6), (0.7, -0.7), 0.7),
            ((36.6, 2.6, 7.6), (0.6, 0.8), 0.2), ((25.6, 2.6, 7.6), (0.6, 0.8), 0.55)]
    for k, (p, f, ph) in enumerate(cams, 1):
        S.seccam(k, p, f, {"mount_height_above_floor": round(p[1], 2), "pan_amplitude_deg": 40.0, "pan_cycles": 1, "pan_phase": ph, "tilt_base_deg": -18.0})
    for k, (x, z) in enumerate(((27.0, -6.5), (39.0, 5.0)), 1):
        S.spot("monster", k, (x, 0.0, z), face=(0, -1), props={"when": "night", "what": "a night threat (code)"})
    S.label("BACK OF HOUSE (restricted)", 27.0, 5.2)
    S.corridor("staff_entry_aisle", BX0 + 0.01, RACK_X[0] - 0.01, BZ0 + 0.01, RACK_ROWS[-1][1])
    for k in range(len(RACK_ROWS) - 1):
        S.corridor(f"rack_aisle_{k + 1}", RACK_X[0], RACK_X[1], RACK_ROWS[k][1] + 0.01, RACK_ROWS[k + 1][0] - 0.01)
    S.corridor("forklift_aisle", BX0 + 0.01, BX1 - 0.31, RACK_ROWS[-1][1] + 0.01, ROOMS_Z - 0.01)
    S.corridor("lift_lobby", 36.21, BX1 - 0.01, ROOMS_Z + T + 0.01, LIFT["z0"] - 0.09)
    S.still = ((BX0 + 1.2, 0.0, 5.2), (1.0, -0.32), 2)
    for x in (16, 23, 30, 37):
        for z in (-6, 0, 5):
            S.light(x, BH - 0.4, z, 220)
    for x, z in ((16, 11), (22.6, 11), (28.6, 10), (34.1, 12), (39.2, 8.6)):
        S.light(x, 2.6, z, 100)
    return S


# ---------------------------------------------------------------- basement
KZ0, KZ1, KH = -5.0, 15.0, 3.7                                # 30 m by 20 m, under back_of_house's south part; its floor is 4 m below
BOH_Y = 4.0


def basement():
    S = Scene("basement", "Basement (restricted)", "30 m by 20 m, 3.7 m high (back_of_house's floor is 4 m above)", mood="restricted: cold, humming")
    x0, x1, z0, z1 = BX0, BX1, KZ0, KZ1
    sw0, sw1 = STAIR["x0"] - T, STAIR["x1"] + T                                   # the stairwell's walls, x 32.2 to 36.0
    # the shell; the ceiling leaves out the stairwell, whose own ceiling is higher
    shell(S, "Basement", x0, x1, z0, z1, 0.0, KH, ceiling=False, fmat="floor")
    for nm, a0, a1, b0, b1 in (("W", x0 - T, sw0, z0 - T, z1 + T), ("E", sw1, x1 + T, z0 - T, z1 + T), ("M", sw0, sw1, z0 - T, ROOMS_Z)):
        S.solid(f"Basement_Ceiling_{nm}", (a0, KH, b0), (a1, KH + 0.3, b1), "ceiling", ("ceiling",))
    S.zone("restricted", "basement", (x0, 0.0, z0), (x1, KH, z1))
    # the stairwell up to back_of_house's stair door: one flight north from the south wall to a landing at y 4, the door at its north end
    sh = BOH_Y + 3.0
    wall(S, "Stairwell_Wall_W", "z", sw0, STAIR["x0"], ROOMS_Z, z1, 0.0, sh, [(STAIR["foot"] + 0.2, STAIR["foot"] + 1.8, 0.0, DOOR_H)])
    S.solid("Stairwell_Wall_E", (STAIR["x1"], 0.0, ROOMS_Z), (sw1, sh, z1), "wall")
    wall(S, "Stairwell_Wall_N", "x", ROOMS_Z, ROOMS_Z + T, sw0, sw1, 0.0, sh, [(STAIR["door_x"] - DOOR_W / 2, STAIR["door_x"] + DOOR_W / 2, BOH_Y, BOH_Y + DOOR_H)])
    S.solid("Stairwell_Wall_S_up", (sw0, KH, z1), (sw1, sh, z1 + T), "wall")
    S.solid("Stairwell_Ceiling", (sw0, sh, ROOMS_Z), (sw1, sh + 0.2, z1 + T), "ceiling", ("ceiling",))
    flight(S, "stairs_up", STAIR["x0"], 34.0, STAIR["foot"], -1, "z", 0.0, BOH_Y, 15, 0.28)
    S.solid("Stair_Landing", (STAIR["x0"], BOH_Y - SLAB, ROOMS_Z + T), (STAIR["x1"], BOH_Y, STAIR["top"]), "stair")
    S.solid("Stair_Rail", (34.0, BOH_Y, STAIR["top"] - 0.15), (STAIR["x1"], BOH_Y + 1.0, STAIR["top"]), "rail")
    S.door("back_of_house", (STAIR["door_x"] - DOOR_W / 2, BOH_Y, ROOMS_Z + T), (1, 0), (0, 1), props={"kind": "stair door"})
    S.link("back_of_house", (STAIR["door_x"], BOH_Y, ROOMS_Z + 0.8), (33.2, BOH_Y, 8.3), (0, 1), "back_of_house (stairs up)")
    S.label("stairs up to back_of_house", 34.1, 14.4, kind="note")
    S.label("landing (y 4)", 35.0, 8.4, BOH_Y, kind="note")
    # the freight lift: the shaft under back_of_house's, its gate on the north side
    shell(S, "LiftCar", LIFT["x0"], LIFT["x1"], LIFT["z0"] + T, LIFT["z1"], 0.0, LIFT["h"] + 0.4, sides="SWE", wmat="lift", fmat="lift", floor=False)
    wall(S, "Lift_Wall_N", "x", LIFT["z0"], LIFT["z0"] + T, sw1, x1 + T, 0.0, KH, [(LIFT["door"][0], LIFT["door"][1], 0.0, LIFT["h"])], "lift")
    S.solid("Lift_Wall_W", (sw1, 0.0, LIFT["z0"] + T), (LIFT["x0"] - T, KH, z1), "lift")
    S.door("freight_lift", (LIFT["door"][0], 0.0, LIFT["z0"]), (1, 0), (0, 1), width=LIFT["door"][1] - LIFT["door"][0], height=LIFT["h"], props={"kind": "freight lift gate"})
    S.link("freight_up", (39.2, 0.0, LIFT["z0"] - 0.6), (39.2, 0.0, LIFT["z0"] - 1.4), (0, -1), "back_of_house (the freight lift)")
    S.marker("Spawn", (39.2, 0.0, LIFT["z0"] - 1.4))
    S.label("FREIGHT LIFT", 39.2, 12.1)
    # cold storage: two walk-in freezers along the north wall, insulated, doors on their south side
    for k, (a0, a1) in enumerate(((x0, 18.0), (18.2, 24.0)), 1):
        dx = (a0 + a1) / 2
        wall(S, f"Freezer_{k}_Wall_S", "x", 2.8, 3.0, a0, a1, 0.0, 3.0, [(dx - 0.6, dx + 0.6, 0.0, DOOR_H)], "freezer")
        S.solid(f"Freezer_{k}_Ceiling", (a0, 3.0, z0), (a1, 3.2, 3.0), "freezer", ("ceiling",))
        S.door(f"freezer_{k}", (dx - 0.6, 0.0, 3.0), (1, 0), (0, 1), width=1.2, props={"kind": "freezer door"})
        box(S, f"Freezer_{k}_Shelf_N", a0 + 0.2, a1 - 0.2, z0, z0 + 0.6, 0.0, 2.2, "freezer")
        box(S, f"Freezer_{k}_Shelf_W", a0, a0 + 0.6, z0 + 0.6, 2.2, 0.0, 2.2, "freezer")
        S.spot("food", f"cold_{k}", (dx + 0.6, 0.0, -2.6), face=(0, -1), props={"where": "cold storage"})
        S.light(dx, 2.6, -1.0, 60)
    S.solid("Freezer_Divide", (18.0, 0.0, z0), (18.2, 3.0, 2.8), "freezer")
    S.solid("Freezer_Wall_E", (24.0, 0.0, z0), (24.2, 3.0, 3.0), "freezer")
    S.label("COLD STORAGE", 18.1, -0.6)
    # the plant room in the north-east: boilers, the chiller, electrical panels, the breaker board
    wall(S, "Plant_Wall_W", "z", 28.0, 28.2, z0, 3.0, 0.0, KH, [(0.0, 1.0, 0.0, DOOR_H)])
    S.solid("Plant_Wall_S", (28.0, 0.0, 3.0), (x1, KH, 3.2), "wall")
    S.door("plant_room", (28.2, 0.0, 0.5 - DOOR_W / 2 - 0.03), (0, 1), (1, 0), props={"kind": "plant room door"})
    box(S, "Boiler", 30.0, 32.0, -4.4, -2.4, 0.0, 2.6, "plant")
    box(S, "Boiler", 33.0, 35.0, -4.4, -2.4, 0.0, 2.6, "plant")
    box(S, "Chiller", 37.0, 41.6, -4.6, -1.6, 0.0, 2.0, "plant")
    box(S, "Electrical_Panels", x1 - 0.5, x1, 0.0, 2.6, 0.0, 2.2, "monitor")
    S.decor("Pipes", (28.2, 3.0, -1.2), (x1, 3.3, -0.9), "plant")
    box(S, "Pump_Set", 32.6, 35.4, 0.8, 1.8, 0.0, 1.1, "plant")           # the dressing's pump set on its plinth
    S.spot("breaker", 1, (41.2, 0.0, 1.3), face=(1, 0), props={"what": "the store's breakers: the lights, by night the emergency lights (code)"})
    S.label("PLANT ROOM", 35.0, 0.6)
    # pallets in the south-west, stacked at different heights
    for k, (x, z, hh) in enumerate(((14.2, 8.4, 1.6), (15.8, 8.4, 0.9), (14.2, 11.0, 1.2), (19.0, 9.0, 1.6), (19.0, 12.0, 0.15), (23.4, 9.2, 1.0),
                                    (23.4, 12.4, 1.6), (27.8, 9.6, 1.3), (27.8, 12.8, 0.6)), 1):
        box(S, "Pallet", x - 0.6, x + 0.6, z - 0.5, z + 0.5, 0.0, hh, "pallet")
    S.label("PALLETS", 21.0, 14.2)
    S.spot("hide", 1, (16.9, 0.0, 13.6), face=(0, -1), props={"where": "between the pallet stacks"})
    S.spot("hide", 2, (29.6, 0.0, -4.4), face=(-1, 0), props={"where": "behind the boilers"})
    S.spot("monster", 1, (21.0, 0.0, 5.0), face=(1, 0), props={"when": "night", "what": "a night threat (code)"})
    S.spot("monster", 2, (35.5, 0.0, 5.0), face=(-1, 0), props={"when": "night", "what": "a night threat (code)"})
    for k, (p, f, ph) in enumerate((((12.6, 3.2, 3.8), (0.8, 0.6), 0.3), ((sw0 - 0.3, 3.2, 3.8), (-0.8, 0.6), 0.65)), 1):
        S.seccam(k, p, f, {"mount_height_above_floor": round(p[1], 2), "pan_amplitude_deg": 40.0, "pan_cycles": 1, "pan_phase": ph, "tilt_base_deg": -18.0})
    S.label("BASEMENT (restricted)", 21.0, 5.2)
    S.corridor("service_corridor", x0 + 0.01, x1 - 0.01, 3.21, 6.99)
    S.still = ((41.6, 0.0, 5.6), (-1.0, -0.12), 0)
    for x in (15, 21, 27, 33, 39):
        S.light(x, KH - 0.3, 5.2, 110)
    for x, z in ((16, 11), (24, 11), (34.1, 12.5), (34.1, 9.0), (35, -1)):
        S.light(x, KH - 0.4 if z != 9.0 else BOH_Y + 2.4, z, 90)
    return S


# ---------------------------------------------------------------- the scenes and how they join
SCENES = {"aisles": aisles, "second_floor": second_floor, "back_of_house": back_of_house, "basement": basement}

# Every link between two scenes of this set: (scene, door) <-> (scene, door). Pressing F at one side's Link_ puts you on the other side's Arrive_.
PAIRS = [
    (("aisles", "stairs_up"), ("second_floor", "stairs_down"), "stairs", "19 steps of 0.263 m up the mezzanine's front"),
    (("aisles", "escalator_up"), ("second_floor", "escalator_down"), "escalator", "an escalator as 20 steps of 0.25 m, beside the stairs"),
    (("back_of_house", "basement_stairs"), ("basement", "back_of_house"), "stairs", "the stair door by the office; 15 steps of 0.267 m"),
    (("back_of_house", "freight_down"), ("basement", "freight_up"), "freight_lift", "the freight lift, one stop down"),
]
# Links that leave this set: the other side is main_floor (part 1, shared/city.js) or Secret Operations; the coordinator wires both.
OUTSIDE = {
    ("aisles", "main_floor"): "main_floor's north wall, the 3.6 m gap between its cooler banks (x -1.8 to 1.8, 3 m high, under its camera). "
                              "main_floor's side, for the coordinator: F at (0, 0, -8.3), arrive at (0, 0, -7.8) facing (0, 1); its Wall_N "
                              "(shared/city.js) needs that opening cut",
    ("back_of_house", "main_floor"): "main_floor's staff doors on its east wall (z -6.3 to -4.7, 2.2 m). main_floor's side, for the coordinator: "
                                     "F at (11.4, 0, -5.5), arrive at (10.7, 0, -5.5) facing (-1, 0); its Wall_E needs that opening cut",
    ("back_of_house", "secret_ops"): "secret_ops/service_entry by the freight lift: the manifest's grocery.backhouse>secret_ops (service_corridor, "
                                     "requires keycard_tier_1); the reader is Spot_keycard_1 by the gate",
}


def build(sid):
    return SCENES[sid]()


def plan_view(S, level=0.0, ppm_target=1700.0):
    """The plan's bounds (x0, x1, z0, z1) with a margin, and its pixel size: the Blender render and the sheets share this mapping.
    The view-down art below second_floor's glass is left out of the bounds."""
    bs = [b for b in S.boxes if (b["col"] or b["name"].startswith("decor_")) and "below" not in b["tags"]]
    xs = [v for b in bs for v in (b["min"][0], b["max"][0])]
    zs = [v for b in bs for v in (b["min"][2], b["max"][2])]
    m = 2.0
    x0, x1, z0, z1 = min(xs) - m, max(xs) + m, min(zs) - m, max(zs) + m
    span = max(x1 - x0, z1 - z0)
    ppm = ppm_target / span
    return {"x0": x0, "x1": x1, "z0": z0, "z1": z1, "W": int(round((x1 - x0) * ppm)), "H": int(round((z1 - z0) * ppm)), "ppm": ppm}


def plan_hidden(S, b, level):
    """Is box b left out of the plan for `level`? (ceilings, the view-down art, and anything that starts 2.4 m or more above the level;
    on a one-level plan the steps always show)"""
    if "ceiling" in b["tags"] or "below" in b["tags"]:
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


def camera_entry(scene, name, pos, face, props):
    """export_scene.camera(), without Blender: the same dict."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import export_scene
    return export_scene.camera(scene, name, [_r(v) for v in pos], _face(face), props)


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
            elif n.startswith("SecCam_"):
                out["cameras"].append(camera_entry(S.id, n, o["pos"], o["face"], o["props"]))
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
def check(base, ids=None):
    """Links meet, steps keep to the rise, corridors are wide and clear. Reads <base>/world/<scene>.json; prints one line per gate; True if all pass."""
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
        print(f"  off this set: {s}.{dd} -> {'main_floor' if dd == 'main_floor' else 'secret_ops/service_entry'}")
    # steps: every Step_<flight>_<nn> collider, in order, keeps to MAX_RISE, from the floor it starts on to the floor it reaches
    nsteps, worst = 0, 0.0
    for sid in ids:
        S = build(sid)
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
    print(f"GATE steps: {nsteps} step boxes, the highest rise {worst:.3f} m (at most {MAX_RISE} m)")
    # corridors: at least MIN_CORRIDOR wide, and no standing collider inside
    ncor, narrow = 0, 99.0
    for sid in ids:
        S = build(sid)
        cols = docs.get(sid, {}).get("colliders", [])
        for c in S.corridors:
            ncor += 1
            w = min(c["max"][0] - c["min"][0], c["max"][2] - c["min"][2])
            if c["name"] == "opening":                     # a doorway through a wall: its width is along x, its depth the wall's
                w = c["max"][0] - c["min"][0]
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
    # cameras: the restricted scenes have SecCam_ cameras in the page's shape
    ncam = {sid: len(d.get("cameras", [])) for sid, d in docs.items()}
    for sid in ("back_of_house", "basement"):
        if sid in docs and not ncam[sid]:
            bad.append(f"{sid} is restricted and has no SecCam_ camera")
        for c in docs.get(sid, {}).get("cameras", []):
            if not all(k in c for k in ("id", "position", "facing_deg", "pan", "tilt", "zoom")):
                bad.append(f"camera {sid}/{c.get('id')} is missing a key the page reads")
    print(f"GATE cameras: {', '.join(f'{s} {n}' for s, n in ncam.items())}")
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
    base = Path(a[a.index("--out") + 1]) if "--out" in a else ROOT / "work/grocery_greybox"
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
            bsdf.inputs["Roughness"].default_value = 0.8 if name not in ("water", "glass") else 0.05
            if name == "glass":                               # the mezzanine's glazing: see-through in the stills
                for key in ("Transmission Weight", "Transmission"):
                    if key in bsdf.inputs:
                        bsdf.inputs[key].default_value = 1.0
                        break
                if "IOR" in bsdf.inputs:
                    bsdf.inputs["IOR"].default_value = 1.05
                if "Alpha" in bsdf.inputs:
                    bsdf.inputs["Alpha"].default_value = 0.15
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
    print("GROCERY_GREYBOX device", dev, "scenes", len(ids))
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
        print(f"GROCERY_GREYBOX done {sid}: {len(S.boxes)} boxes, {len(S.doors)} doors, {len(S.empties)} empties")
    print("GROCERY_GREYBOX ALL DONE")


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
