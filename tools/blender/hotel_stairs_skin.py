"""The hotel's last pieces, pure Python: which faces of the greybox's boxes a walker can see, for the escalators, the other staircase and the
two room layouts clue_room and empty_room (tools/blender/build_hotel_stairs.py builds them in Blender).

    python tools/blender/hotel_stairs_skin.py [scene ...]      prints the skin's quads per material

The layout is the greybox's (build_hotel_greybox.build(scene)): every collider, door, link, marker and spot comes from its model. This file adds
only what the art needs:

- AIR: the boxes of open space a walker (or the camera) is in: the hall or the stairwell, the door openings; in a room, the room, and for the
  room's bake only, the corridor outside its door.
- skin(): every face of a shell collider that looks into the air, cut where another box meets it, so the exported shell is only what can be seen
  (the walls' backs, the slabs' undersides above a ceiling and the faces pressed together are never drawn). The steps, balustrades, newels,
  guards and the furniture are not shell: their art is the build's own (PROP_COLLIDERS).
- the material of each quad, from where it looks.

The same skin() as tools/blender/hotel_floor1_skin.py (floor 1, the motel), so the hotel's scenes are cut the same way.
Coordinates are GAME coordinates (metres, y up, north = -z), as in the greybox.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_hotel_greybox as GB  # noqa: E402

HALLS = ("escalators", "other_stairs")
ROOMS = ("clue_room", "empty_room")
SCENES = HALLS + ROOMS
FRONT = 0.004            # a face is seen if the point this far in front of it is in the air
PROP_COLLIDERS = ("Step_", "Balustrade_", "Fill_", "Newel_", "Guard_", "Desk", "Table", "Pinboard", "Chair")
HALL_H = 15.2
LEVELS = GB.LEVELS


def model(scene):
    return GB.build(scene)


def colliders(M):
    return [{"name": b["name"], "min": list(b["min"]), "max": list(b["max"])} for b in M.boxes if b["col"]]


def box(region, mn, mx):
    return {"region": region, "min": [float(v) for v in mn], "max": [float(v) for v in mx]}


def doors(M):
    """[(name, y, side)] of the scene's doors to the atrium: side 'N' or 'S' (which wall)."""
    out = []
    for d in M.doors:
        out.append((d["name"], d["hinge"][1], "N" if d["hinge"][2] < 0 else "S"))
    return sorted(out, key=lambda t: t[1])


# ---------------------------------------------------------------- the air
def air_hall(scene, M):
    T, W2, H = GB.T, GB.DOOR_W / 2, GB.DOOR_H
    if scene == "escalators":
        x0, x1, z0, z1 = -3.0, 3.0, -4.4, 4.4
    else:
        x0, x1, z0, z1 = -2.6, 2.6, -3.0, 3.0
    air = [box("hall", (x0, 0, z0), (x1, HALL_H, z1))]
    for name, y, side in doors(M):
        za, zb = (z0 - T, z0) if side == "N" else (z1, z1 + T)
        air.append(box("doorhole", (-W2, y, za), (W2, y + H, zb)))
    return air


def room_dims(lay):
    w, d, ox = GB.ROOMS[lay]
    return ox - w / 2, ox + w / 2, -0.2 - d, -0.2


def air_room(lay, standin=False):
    x0, x1, z0, z1 = room_dims(lay)
    air = [box("room", (x0, 0, z0), (x1, GB.ROOM_H, z1))]
    if standin:                                          # the corridor outside the door, for the bake only (the light that comes in when it opens)
        air += [box("s_hole", (-GB.DOOR_W / 2, 0, -0.2), (GB.DOOR_W / 2, GB.DOOR_H, 0.0)),
                box("s_corridor", (-6.0, 0, 0.0), (6.0, GB.CORR_H, 2 * GB.CORR_Z))]
    return air


def room_standin_colliders(lay):
    """The floor 3 corridor outside a room's door, as boxes (bake stand-ins only; never exported): its floor, ceiling, far wall, ends, and the door
    wall beyond the room's own."""
    x0, x1, z0, z1 = room_dims(lay)
    T, H, W = GB.T, GB.CORR_H, 2 * GB.CORR_Z
    out = [("SB_Floor", (-6.2, -0.3, -0.2), (6.2, 0.0, W + T)), ("SB_Ceiling", (-6.2, H, -0.2), (6.2, H + 0.2, W + T)),
           ("SB_Wall_Far", (-6.2, 0, W), (6.2, H, W + T)), ("SB_Wall_W", (-6.2, 0, 0), (-6.0, H, W)), ("SB_Wall_E", (6.0, 0, 0), (6.2, H, W)),
           ("SB_Wall_Near_W", (-6.2, 0, -0.2), (x0 - T, H, 0.0)), ("SB_Wall_Near_E", (x1 + T, 0, -0.2), (6.2, H, 0.0))]
    return [{"name": n, "min": list(a), "max": list(b)} for n, a, b in out]


# ---------------------------------------------------------------- the skin (as hotel_floor1_skin.skin)
def _inside(p, b, e=1e-4):
    return all(b["min"][i] + e < p[i] < b["max"][i] - e for i in range(3))


def _within(p, b, e=1e-7):
    return all(b["min"][i] - e <= p[i] <= b["max"][i] + e for i in range(3))


def skin(cols, air, cutouts=(), splits_y=(), skip=PROP_COLLIDERS):
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
    a, bi, ci, p = q["axis"], q["bi"], q["ci"], q["p"]
    (b0, b1), (c0, c1) = q["b"], q["c"]
    pts = []
    for bb, cc in ((b0, c0), (b1, c0), (b1, c1), (b0, c1)):
        v = [0.0, 0.0, 0.0]
        v[a], v[bi], v[ci] = p, bb, cc
        pts.append(v)
    return pts


def area(q):
    return (q["b"][1] - q["b"][0]) * (q["c"][1] - q["c"][0])


# ---------------------------------------------------------------- materials of the skin
DADO = 1.2               # the escalator hall's tiled dado on the ground floor (8 rows of 15 cm tile); the stairwell's painted dado band at every landing


def hall_splits(scene):
    if scene == "escalators":
        return (DADO,)
    return tuple(y + DADO for y in LEVELS)


def yrange(q):
    """A wall quad's span in y."""
    return q["b"] if q["bi"] == 1 else q["c"]


def escalators_material(q):
    a, s, reg, cn = q["axis"], q["side"], q["region"], q["coll"]
    if reg == "doorhole":
        return "Door_Jamb"
    if cn.startswith("Landing_"):
        if a == 1 and s > 0:
            return {"Landing_4": "Carpet_Motel", "Landing_8": "Carpet_Green", "Landing_12": "Carpet_Apart"}[cn]
        if a == 1:
            return "Soffit_Plaster"
        return "Fascia_Paint"
    if a == 1:
        return "Floor_Tile" if s > 0 else "Ceiling_Hall"
    if yrange(q)[1] <= DADO + 1e-6:
        return "Wall_Tile"
    return "Wall_Hall"


def stairs_material(q):
    a, s, reg, cn = q["axis"], q["side"], q["region"], q["coll"]
    if reg == "doorhole":
        return "Door_Jamb"
    if a == 1:
        if s > 0:
            return "Stair_Floor"
        return "Stair_Ceiling"
    if cn.startswith(("Landing_", "Half_Landing_")):
        return "Stair_Edge"
    lo = yrange(q)[0]
    band = max([y for y in LEVELS if y <= lo + 1e-6] or [0.0])
    return "Stair_Dado" if lo < band + DADO - 1e-6 else "Stair_Paint"


def room_material(lay, q):
    a, s, reg = q["axis"], q["side"], q["region"]
    if reg.startswith("s_"):
        if a == 1:
            return "SB_Carpet" if s > 0 else "SB_Ceiling"
        return "SB_Wall"
    if a == 1:
        if s > 0:
            return "Carpet_Clue" if lay == "clue_room" else "Floor_Bare"
        return "Ceiling_Room"
    return "Wall_Clue" if lay == "clue_room" else "Wall_Stripped"


def material(scene, q):
    if scene == "escalators":
        return escalators_material(q)
    if scene == "other_stairs":
        return stairs_material(q)
    return room_material(scene, q)


# ---------------------------------------------------------------- the rooms' cut-outs (windows set into a wall)
WIN_Y0, WIN_Y1 = 0.95, 2.05


def window(lay):
    """(wall, a0, a1): the room's window, its wall ('W' or 'N') and its span along the wall."""
    return ("W", -3.8, -2.6) if lay == "clue_room" else ("W", -6.3, -4.9)


def room_cutouts(lay):
    x0, x1, z0, z1 = room_dims(lay)
    side, a0, a1 = window(lay)
    return [{"min": [x0 - 0.01, WIN_Y0, a0], "max": [x0 + 0.01, WIN_Y1, a1]}]


def scene_skin(scene, standin=False):
    M = model(scene)
    cols = colliders(M)
    if scene in HALLS:
        return skin(cols, air_hall(scene, M), splits_y=hall_splits(scene)), M
    if standin:
        allc = cols + room_standin_colliders(scene)
        q = skin(allc, air_room(scene, True), room_cutouts(scene))
        return [x for x in q if x["region"].startswith("s_")], M
    return skin(cols, air_room(scene), room_cutouts(scene)), M


def summary(scene):
    q, M = scene_skin(scene)
    by = {}
    for x in q:
        m = material(scene, x)
        n, a = by.get(m, (0, 0.0))
        by[m] = (n + 1, a + area(x))
    print(f"SKIN {scene}: {len(q)} quads, {sum(area(x) for x in q):.1f} m2")
    for m, (n, a) in sorted(by.items()):
        print(f"  {m:18s} {n:4d} quads {a:7.1f} m2")
    if scene in ROOMS:
        sq, _ = scene_skin(scene, True)
        print(f"  stand-in skin: {len(sq)} quads, {sum(area(x) for x in sq):.1f} m2")


if __name__ == "__main__":
    for sc in (sys.argv[1:] or SCENES):
        summary(sc)
