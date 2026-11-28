"""The hotel's floor 1 (the motel), pure Python: which faces of the greybox's boxes a walker can see, and where the dressing goes.

Used by tools/blender/build_hotel_floor1.py (in Blender) and testable without Blender:

    python tools/blender/hotel_floor1_skin.py [scene ...]      prints the skin's quads per material and the dressing slots

The layout is the greybox's, unchanged: every collider, door, link, marker and spot comes from tools/blender/build_hotel_greybox.py's model
(build_hotel_greybox.build(scene)). This file adds only what the art needs:

- AIR: the boxes of open space a walker (or the camera) is in: the corridor, the door openings, the alcoves and closets, the lift's opening,
  the stairwell above its steps; in a room, the room's parts.
- skin(): every face of a collider that looks into the air, cut where another box meets it, so the exported shell is only what can be seen: the
  walls' backs, the slabs' undersides and the faces pressed against another box are never drawn. A door opening needs no hole cutting: there is no
  collider behind it, so nothing is drawn there. Each quad gets a material from where it looks (corridor, alcove, door reveal, stairwell...).
- the dressing slots: where the sconces, the brass numbers, the ice machine, the extinguisher cabinet and the exit signs go, all derived from the
  greybox's own numbers (DOOR_XS, CORR_X, CORR_Z, the alcoves' boxes), never typed in twice.

Coordinates are GAME coordinates (metres, y up, north = -z), as in the greybox.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_hotel_greybox as GB  # noqa: E402

CORRIDORS = ("floor_1_lower", "floor_1_upper")
ROOMS = ("motel_a", "motel_b")
SCENES = CORRIDORS + ROOMS
FRONT = 0.004            # a face is seen if the point this far in front of it is in the air
CHAIR = 0.9              # the corridor's chair rail: the wall's lower and upper finishes meet here
SCONCE_XS = (-18.0, -14.0, -10.0, -6.0, -2.0, 2.0, 6.0, 10.0, 14.0, 18.0)   # 2 m either side of every door (DOOR_XS = 0, +-8, +-16), both walls
SCONCE_Y = 2.0           # the shade's middle; every part of a sconce is above 1.8 m (the layout check's head height)
DEAD_SCONCES = {"floor_1_lower": [("S", 14.0), ("N", -10.0)], "floor_1_upper": [("N", -14.0)]}
# the connector kit's colliders in the layout (build_hotel_greybox._f1: the elevator's car and landing, `_F1`): the kit's own art covers them (the
# page draws world/kit/elevator.glb), so they are never part of this scene's skin
KIT = ("Car_", "Landing_Floor_", "Landing_Head_", "Landing_Jamb_")
STAIR_W = GB.KIT_STAIR_W  # the stair doors' openings (the kit's 1.1 m)


def model(scene):
    return GB.build(scene)


def colliders(M):
    return [{"name": b["name"], "min": list(b["min"]), "max": list(b["max"])} for b in M.boxes if b["col"]]


def box(region, mn, mx):
    return {"region": region, "min": [float(v) for v in mn], "max": [float(v) for v in mx]}


# ---------------------------------------------------------------- what the corridor scenes are made of (from the greybox model)
def features(M):
    """[(kind, side, x)] of the alcoves and closets, read off the model: each has an Alcove_Back box; a closet also has a closet door."""
    closets = {round(d["hinge"][0] + (0.4 if d["props"]["closed_yaw_deg"] == 0.0 else -0.4), 3): d for d in M.doors if d["props"].get("kind") == "closet"}
    out = []
    for b in M.boxes:
        if b["name"].startswith("Alcove_Back"):
            a = round((b["min"][0] + b["max"][0]) / 2, 3)
            side = "N" if b["max"][2] < 0 else "S"
            out.append(("closet" if a in closets else "alcove", side, a))
    return sorted(out, key=lambda f: f[2])


def room_doors(M):
    """[(number, layout, side, x)] of the motel room doors."""
    out = []
    for d in M.doors:
        p = d["props"]
        if "room" in p:
            out.append((p["room"], p["room_layout"], "N" if p["room_z"] < 0 else "S", float(p["room_x"])))
    return sorted(out, key=lambda r: (r[2], r[3]))


def air_corridor(M):
    X, Z, H, T = GB.CORR_X, GB.CORR_Z, GB.CORR_H, GB.T
    air = [box("corridor", (-X, 0, -Z), (X, H, Z))]
    for num, lay, side, a in room_doors(M):
        z0, z1 = ((-Z - T, -Z) if side == "N" else (Z, Z + T))
        air.append(box("doorhole", (a - GB.DOOR_W / 2, 0, z0), (a + GB.DOOR_W / 2, GB.DOOR_H, z1)))
    for kind, side, a in features(M):
        sg = -1 if side == "N" else 1
        z0, z1 = sorted((sg * Z, sg * (Z + T)))
        w = 0.4 if kind == "closet" else 0.6
        hh = GB.DOOR_H if kind == "closet" else 2.4
        air.append(box("doorhole" if kind == "closet" else "alcove", (a - w, 0, z0), (a + w, hh, z1)))
        zi0, zi1 = sorted((sg * (Z + T), sg * (Z + T + 1.0)))
        air.append(box(kind, (a - 0.6, 0, zi0), (a + 0.6, 2.4, zi1)))
    names = {b["name"] for b in M.boxes}
    # the lift (lower level): the opening in the west wall is the kit's elevator's: its landing lines the opening's reveals and soffit and lays its
    # sill across the wall's thickness, so no face of this scene is drawn in there (no air) and the two never fight
    air.append(box("doorhole", (X, 0, -STAIR_W / 2), (X + T, GB.DOOR_H, STAIR_W / 2)))       # the stair door at the east end
    steps = sorted((b for b in M.boxes if b["name"].startswith("Step_")), key=lambda b: b["min"][0])
    if steps:                                            # the lower level's stairwell: the air above each step, and the landing
        top = 6.0
        air.append(box("stair", (X + T, 0, -1.0), (steps[0]["min"][0], top, 1.0)))
        for s in steps:
            air.append(box("stair", (s["min"][0], s["max"][1], -1.0), (s["max"][0], top, 1.0)))
        land = next(b for b in M.boxes if b["name"] == "Landing_Top")
        air.append(box("stair", (land["min"][0], land["max"][1], -1.0), (land["max"][0], top, 1.0)))
        air.append(box("stairhole", (land["max"][0], land["max"][1], -STAIR_W / 2), (land["max"][0] + T, land["max"][1] + GB.DOOR_H, STAIR_W / 2)))
    elif "StairLanding_Floor" in names:                  # the upper level: the top landing behind the stair door
        air.append(box("stair", (X + T, 0, -1.0), (21.6, GB.CORR_H, 1.0)))
    return air


# ---------------------------------------------------------------- the rooms (room frame: the door at the origin, the room toward -z)
def room_dims(lay):
    w, d, ox = GB.ROOMS[lay]
    return ox - w / 2, ox + w / 2, -0.2 - d, -0.2


def air_room(lay, standin=False):
    x0, x1, z0, z1 = room_dims(lay)
    H = GB.ROOM_H
    if lay == "motel_a":
        air = [box("bedroom", (x0, 0, -4.2), (x1, H, z1)), box("bedroom", (0.7, 0, z0), (x1, H, -4.2)),
               box("bath", (x0, 0, z0), (0.6, H, -4.3)), box("doorway", (-0.65, 0, -4.3), (0.05, H, -4.2))]
    else:
        air = [box("bedroom", (x0, 0, z0), (x1, H, -1.5)), box("bedroom", (-1.2, 0, -1.5), (x1, H, z1)),
               box("closet", (x0, 0, -1.4), (-1.3, H, z1)), box("closet", (-1.3, 0, -1.2), (-1.2, H, -0.4))]
    if standin:                                          # the corridor outside the door, for the bake only (the light that comes in when it opens)
        air += [box("s_hole", (-GB.DOOR_W / 2, 0, -0.2), (GB.DOOR_W / 2, GB.DOOR_H, 0.0)),
                box("s_corridor", (-6.0, 0, 0.0), (6.0, GB.CORR_H, 2 * GB.CORR_Z))]
    return air


def room_standin_colliders(lay):
    """The corridor outside a room's door, as boxes (bake stand-ins only; never exported): its floor, ceiling, far wall, ends, and the door wall
    beyond the room's own."""
    x0, x1, z0, z1 = room_dims(lay)
    T, H, W = GB.T, GB.CORR_H, 2 * GB.CORR_Z
    out = [("SB_Floor", (-6.2, -0.3, -0.2), (6.2, 0.0, W + T)), ("SB_Ceiling", (-6.2, H, -0.2), (6.2, H + 0.2, W + T)),
           ("SB_Wall_Far", (-6.2, 0, W), (6.2, H, W + T)), ("SB_Wall_W", (-6.2, 0, 0), (-6.0, H, W)), ("SB_Wall_E", (6.0, 0, 0), (6.2, H, W)),
           ("SB_Wall_Near_W", (-6.2, 0, -0.2), (x0 - T, H, 0.0)), ("SB_Wall_Near_E", (x1 + T, 0, -0.2), (6.2, H, 0.0))]
    return [{"name": n, "min": list(a), "max": list(b)} for n, a, b in out]


FURNITURE = ("Bed", "Nightstand", "Dresser")              # room colliders whose art is the furniture, not the shell


# ---------------------------------------------------------------- the skin
def _inside(p, b, e=1e-4):
    return all(b["min"][i] + e < p[i] < b["max"][i] - e for i in range(3))


def _within(p, b, e=1e-7):
    return all(b["min"][i] - e <= p[i] <= b["max"][i] + e for i in range(3))


def skin(cols, air, cutouts=(), splits_y=(), skip=FURNITURE):
    """Every collider face that looks into the air, as merged rectangles: [{coll, axis, side, p, b: (u0, u1), c: (v0, v1), region}].
    axis is the face's normal axis (0 x, 1 y, 2 z), side its sign; (b, c) are the other two axes in order. `cutouts`: boxes whose faces are
    left open (recesses the dressing fills); `splits_y`: heights where a wall's finish changes (each wall face is cut there)."""
    arch = [c for c in cols if not c["name"].startswith(skip)]
    everything = arch + list(air) + list(cutouts)
    out = []
    for C in sorted(arch, key=lambda c: c["name"]):
        for a in range(3):
            bi, ci = [i for i in range(3) if i != a]
            for side in (-1, 1):
                p = C["max"][a] if side > 0 else C["min"][a]
                cuts = {bi: {C["min"][bi], C["max"][bi]}, ci: {C["min"][ci], C["max"][ci]}}
                for o in everything:
                    if o is C or not (o["min"][a] - 0.01 <= p <= o["max"][a] + 0.01):
                        continue
                    for k in (bi, ci):
                        for v in (o["min"][k], o["max"][k]):
                            if C["min"][k] < v < C["max"][k]:
                                cuts[k].add(v)
                if a != 1:
                    for y in splits_y:
                        if C["min"][1] < y < C["max"][1]:
                            cuts[1].add(y)
                ub, uc = sorted(cuts[bi]), sorted(cuts[ci])
                cells = {}
                for i in range(len(ub) - 1):
                    for j in range(len(uc) - 1):
                        if ub[i + 1] - ub[i] < 1e-6 or uc[j + 1] - uc[j] < 1e-6:
                            continue
                        c = [0.0, 0.0, 0.0]
                        c[a], c[bi], c[ci] = p, (ub[i] + ub[i + 1]) / 2, (uc[j] + uc[j + 1]) / 2
                        f = list(c)
                        f[a] += side * FRONT
                        reg = next((A["region"] for A in air if _within(f, A)), None)
                        if reg is None or any(_inside(f, o) for o in arch if o is not C):
                            continue
                        if any(_within(c, o, 1e-6) for o in cutouts):
                            continue
                        dup = False
                        for o in arch:                    # two boxes with the same face here: the first by name draws it
                            if o is C or o["name"] > C["name"]:
                                continue
                            q = o["max"][a] if side > 0 else o["min"][a]
                            if abs(q - p) < 1e-6 and o["min"][bi] - 1e-6 <= c[bi] <= o["max"][bi] + 1e-6 and o["min"][ci] - 1e-6 <= c[ci] <= o["max"][ci] + 1e-6:
                                dup = True
                                break
                        if not dup:
                            cells[(i, j)] = reg
                # merge the cells of this face into rectangles of one region and one finish band
                used = set()
                for (i, j) in sorted(cells, key=lambda t: (t[1], t[0])):
                    if (i, j) in used:
                        continue
                    reg = cells[(i, j)]
                    i1 = i
                    while (i1 + 1, j) in cells and (i1 + 1, j) not in used and cells[(i1 + 1, j)] == reg and not _band_break(a, bi, ub[i1 + 1], splits_y):
                        i1 += 1
                    j1 = j
                    while all((k, j1 + 1) in cells and (k, j1 + 1) not in used and cells[(k, j1 + 1)] == reg for k in range(i, i1 + 1)) \
                            and not _band_break(a, ci, uc[j1 + 1], splits_y):
                        j1 += 1
                    for k in range(i, i1 + 1):
                        for m in range(j, j1 + 1):
                            used.add((k, m))
                    out.append({"coll": C["name"], "axis": a, "side": side, "p": p, "bi": bi, "ci": ci,
                                "b": (ub[i], ub[i1 + 1]), "c": (uc[j], uc[j1 + 1]), "region": reg})
    return out


def _band_break(a, k, v, splits_y):
    return a != 1 and k == 1 and any(abs(v - y) < 1e-9 for y in splits_y)


def quad_points(q):
    """The rectangle's four corners (game coordinates), counter-clockwise seen from the air (its normal points into the air)."""
    a, bi, ci, p, s = q["axis"], q["bi"], q["ci"], q["p"], q["side"]
    (b0, b1), (c0, c1) = q["b"], q["c"]
    pts = []
    for bb, cc in ((b0, c0), (b1, c0), (b1, c1), (b0, c1)):
        v = [0.0, 0.0, 0.0]
        v[a], v[bi], v[ci] = p, bb, cc
        pts.append(v)
    return pts


def area(q):
    return (q["b"][1] - q["b"][0]) * (q["c"][1] - q["c"][0])


def y0_of(q):
    """The quad's lowest height: its y range is `b` on an x-facing face (bi = y) and `c` on a z-facing one (ci = y). The finish split used to
    read c[0] everywhere, so the corridor's end walls (x-facing) all got the lower finish (found by the floor 2 job)."""
    return q["b"][0] if q["bi"] == 1 else q["c"][0]


# ---------------------------------------------------------------- materials of the skin
def corridor_material(q):
    a, s, reg, cn = q["axis"], q["side"], q["region"], q["coll"]
    if reg in ("lift",):
        return "Lift_Ceiling" if (a == 1 and s < 0) else "Lift_Shaft"
    if reg == "lifthole":
        return "Lift_Steel"
    if reg in ("stair", "stairhole"):
        if reg == "stairhole" and a != 1:
            return "Jamb_Steel"
        if cn.startswith(("Step_", "Landing_Top")) or (a == 1 and s > 0):
            return "Stair_Concrete"
        if a == 1 and s < 0:
            return "Stair_Ceiling"
        return "Stair_Paint"
    if reg == "doorhole":
        if a == 1 and s > 0:
            return "Threshold"
        return "Door_Jamb"
    if a == 1:
        if s > 0:
            return "Carpet_Runner" if reg == "corridor" else "Carpet_Field"
        return "Ceiling_Popcorn"
    if reg == "alcove":
        return "Wall_Upper" if y0_of(q) >= CHAIR - 1e-6 else "Wall_Lower"
    if reg == "closet":
        return "Closet_Paint"
    return "Wall_Upper" if y0_of(q) >= CHAIR - 1e-6 else "Wall_Lower"


def room_material(q):
    a, s, reg = q["axis"], q["side"], q["region"]
    if reg.startswith("s_"):
        if a == 1:
            return "SB_Carpet" if s > 0 else "SB_Ceiling"
        return "SB_Wall"
    if a == 1:
        if s > 0:
            return "Tile_Floor" if reg == "bath" else "Carpet_Room"
        return "Ceiling_Room"
    if reg == "bath":
        return "Tile_Wall"
    return "Wall_Room"


# ---------------------------------------------------------------- the dressing slots
def sconces(scene, M):
    """[(side, x, dead)]: both walls, 2 m either side of every door, clear of the alcove and closet openings (checked)."""
    holes = [(side, a, 0.8) for _, side, a in [(k, s, x) for k, s, x in features(M)]]
    dead = DEAD_SCONCES.get(scene, [])
    out = []
    for side in ("N", "S"):
        for x in SCONCE_XS:
            assert not any(s == side and abs(x - a) < w + 0.3 for s, a, w in holes), (scene, side, x)
            assert not any(abs(x - d) < GB.DOOR_W / 2 + 0.3 for d in GB.DOOR_XS)
            out.append((side, x, (side, x) in dead))
    return out


def recesses(scene):
    """The built-in pieces set into the corridor walls, clear of doors, sconces' plates and the lift: (what, side, x0, x1, y0, y1, depth)."""
    if scene == "floor_1_lower":
        return [("ice", "N", -19.62, -18.86, 0.0, 1.62, 0.19), ("extinguisher", "S", -19.55, -19.15, 1.0, 1.7, 0.12)]
    return [("ice", "S", 18.38, 19.14, 0.0, 1.62, 0.19), ("extinguisher", "N", 18.6, 19.0, 1.0, 1.7, 0.12)]


def cutouts(scene):
    out = []
    Z = GB.CORR_Z
    for what, side, x0, x1, y0, y1, d in recesses(scene):
        z = -Z if side == "N" else Z
        out.append({"min": [x0, y0, z - 0.01], "max": [x1, y1, z + 0.01]})
    return out


def room_cutouts(lay):
    x0, x1, z0, z1 = room_dims(lay)
    wx0, wx1 = window_x(lay)
    return [{"min": [wx0, WIN_Y0, z0 - 0.01], "max": [wx1, WIN_Y1, z0 + 0.01]}]


WIN_Y0, WIN_Y1 = 0.95, 2.05


def window_x(lay):
    return (1.15, 2.45) if lay == "motel_a" else (-0.75, 0.75)


def scene_skin(scene, standin=False):
    M = model(scene)
    cols = colliders(M)
    if scene in CORRIDORS:
        return skin(cols, air_corridor(M), cutouts(scene), splits_y=(CHAIR,), skip=FURNITURE + KIT), M
    if standin:
        allc = cols + room_standin_colliders(scene)
        q = skin(allc, air_room(scene, True), room_cutouts(scene))
        return [x for x in q if x["region"].startswith("s_")], M
    return skin(cols, air_room(scene), room_cutouts(scene)), M


def summary(scene):
    q, M = scene_skin(scene)
    matf = corridor_material if scene in CORRIDORS else room_material
    by = {}
    for x in q:
        m = matf(x)
        n, a = by.get(m, (0, 0.0))
        by[m] = (n + 1, a + area(x))
    print(f"SKIN {scene}: {len(q)} quads, {sum(area(x) for x in q):.1f} m2")
    for m, (n, a) in sorted(by.items()):
        print(f"  {m:18s} {n:4d} quads {a:7.1f} m2")
    if scene in CORRIDORS:
        print("  features", features(M))
        print("  sconces", [(s, x) for s, x, d in sconces(scene, M) if d], "dead of", len(sconces(scene, M)))
        print("  recesses", recesses(scene))
    else:
        sq, _ = scene_skin(scene, True)
        print(f"  stand-in skin: {len(sq)} quads, {sum(area(x) for x in sq):.1f} m2")


if __name__ == "__main__":
    for sc in (sys.argv[1:] or SCENES):
        summary(sc)
