"""The hotel's floor 2 (green carpet), pure Python: which faces of the greybox's boxes a walker can see, and where the dressing goes.

Used by tools/blender/build_hotel_floor2.py (in Blender) and testable without Blender:

    python tools/blender/hotel_floor2_skin.py [scene ...]      prints the skin's quads per material and the dressing slots

Floor 1's method (tools/blender/hotel_floor1_skin.py on its branch), for floor 2's six scenes: the corridors `floor_2_lower` and `floor_2_upper`,
the three key rooms off them (`dining`, `reception`, `key_room`, 14 m by 10 m each) and the room layout `green_room`. The layout is the greybox's
(build_hotel_greybox.build(scene)); this file adds only what the art needs:

- model(): the greybox's model, which already holds the connector kit's records (build_hotel_greybox.kit_floor2: the elevator on the lower
  level, the stair door at every stair door). The kit's colliders (suffix _F2) are its own art's, so the skin leaves them out.
- AIR: the boxes of open space a walker (or the camera) is in.
- skin(): every face of a collider that looks into the air, cut where another box meets it, so the exported shell is only what can be seen.
- the dressing slots (sconces, recesses, pictures), all derived from the greybox's own numbers.

Coordinates are GAME coordinates (metres, y up, north = -z), as in the greybox.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_hotel_greybox as GB  # noqa: E402

CORRIDORS = ("floor_2_lower", "floor_2_upper")
KEYROOMS = ("dining", "reception", "key_room")
ROOMS = ("green_room",)
SCENES = CORRIDORS + KEYROOMS + ROOMS
FRONT = 0.004            # a face is seen if the point this far in front of it is in the air
CHAIR = 0.95             # the dado rail: the cream wainscot below, the green wall above
KEY_DADO = 1.0           # the key rooms' dado
SW = 1.1                 # the stair doors' openings (the kit's stair door)
SCONCE_XS = (-18.0, -14.0, -10.0, -6.0, -2.0, 2.0, 6.0, 10.0, 14.0, 18.0)   # 2 m either side of every room door, both walls
SCONCE_Y = 2.0           # the shade's middle; every part of a sconce is above 1.8 m (the layout check's head height)
DEAD_SCONCES = {"floor_2_lower": [("N", 6.0), ("S", -18.0)], "floor_2_upper": [("S", -6.0), ("N", 14.0)]}
FURNITURE = ("Bed", "Nightstand", "Dresser", "Armchair", "Wardrobe", "Desk", "Table", "Chair", "Buffet", "Front_Desk", "Key_Cubbies", "Sofa",
             "Key_Hooks", "Safe", "Key_Cabinets", "Key_Cage", "Console")    # colliders whose art is the furniture, not the shell


def model(scene):
    return GB.build(scene)


def is_kit(name):
    """A collider the connector kit brought (kit_layout's suffix): its art is the kit's, so the shell never draws it."""
    return name.endswith(("_F2", "_F2_top"))


def colliders(M, kit=True):
    return [{"name": b["name"], "min": list(b["min"]), "max": list(b["max"])} for b in M.boxes if b["col"] and (kit or not is_kit(b["name"]))]


def box(region, mn, mx):
    return {"region": region, "min": [float(v) for v in mn], "max": [float(v) for v in mx]}


# ---------------------------------------------------------------- what the corridor scenes are made of (from the greybox model)
def features(M):
    """[(kind, side, x)] of the alcoves and closets, read off the model: each has an Alcove_Back box; a closet also has a closet door."""
    closets = {("N" if d["hinge"][2] < 0 else "S", round(d["hinge"][0] + (0.4 if d["props"]["closed_yaw_deg"] == 0.0 else -0.4), 3))
               for d in M.doors if d["props"].get("kind") == "closet"}
    out = []
    for b in M.boxes:
        if b["name"].startswith("Alcove_Back"):
            a = round((b["min"][0] + b["max"][0]) / 2, 3)
            side = "N" if b["max"][2] < 0 else "S"
            out.append(("closet" if (side, a) in closets else "alcove", side, a))
    return sorted(out, key=lambda f: f[2])


def room_doors(M):
    """[(number, layout, side, x)] of the room doors."""
    out = []
    for d in M.doors:
        p = d["props"]
        if "room" in p:
            out.append((p["room"], p["room_layout"], "N" if p["room_z"] < 0 else "S", float(p["room_x"])))
    return sorted(out, key=lambda r: (r[2], r[3]))


def scene_doors(M):
    """[(door id, side, x)] of the doors to the key rooms (dining, reception, key_room): a 0.94 m leaf like a room's, hinged on the room side."""
    out = []
    Z = GB.CORR_Z + GB.T
    for d in M.doors:
        p = d["props"]
        if "room" in p or p.get("kind") or abs(abs(d["hinge"][2]) - Z) > 1e-6:
            continue
        side = "N" if d["hinge"][2] < 0 else "S"
        a = d["hinge"][0] + (GB.DOOR_W / 2 if side == "N" else -GB.DOOR_W / 2)
        out.append((d["name"][len("DoorLeaf_"):], side, round(a, 3)))
    return sorted(out, key=lambda r: (r[1], r[2]))


def is_lower(M):
    return any(b["name"].startswith("Step_") for b in M.boxes)


def air_corridor(M):
    X, Z, H, T = GB.CORR_X, GB.CORR_Z, GB.CORR_H, GB.T
    air = [box("corridor", (-X, 0, -Z), (X, H, Z))]
    for a, side in [(r[3], r[2]) for r in room_doors(M)] + [(r[2], r[1]) for r in scene_doors(M)]:
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
    lower = is_lower(M)
    if lower:                                            # the lift's opening; the kit's car stands behind it (its own GLB)
        air.append(box("lifthole", (-X - T, 0, -0.6), (-X, 2.2, 0.6)))
    air.append(box("stairdoor", (X, 0, -SW / 2), (X + T, GB.DOOR_H, SW / 2)))       # the kit's stair door at the east end
    if lower:                                            # the stairwell: the air above each step, and the landing
        steps = sorted((b for b in M.boxes if b["name"].startswith("Step_")), key=lambda b: b["min"][0])
        top = 6.0
        air.append(box("stair", (X + T, 0, -1.0), (steps[0]["min"][0], top, 1.0)))
        for s in steps:
            air.append(box("stair", (s["min"][0], s["max"][1], -1.0), (s["max"][0], top, 1.0)))
        land = next(b for b in M.boxes if b["name"] == "Landing_Top")
        air.append(box("stair", (land["min"][0], land["max"][1], -1.0), (land["max"][0], top, 1.0)))
        air.append(box("stairhole", (land["max"][0], land["max"][1], -SW / 2), (land["max"][0] + T, land["max"][1] + GB.DOOR_H, SW / 2)))
    else:                                                # the upper level: the top landing behind the stair door
        air.append(box("stair", (X + T, 0, -1.0), (21.6, GB.CORR_H, 1.0)))
    return air


# ---------------------------------------------------------------- the key rooms (14 m by 10 m, the door in the south wall at x 0)
KX, KZ, KH = 7.0, 5.0, 3.0


def air_keyroom():
    return [box("hall", (-KX, 0, -KZ), (KX, KH, KZ)), box("doorhole", (-GB.DOOR_W / 2, 0, KZ), (GB.DOOR_W / 2, GB.DOOR_H, KZ + GB.T))]


DINING_WINDOWS = [("W", -2.5), ("W", 2.5), ("E", -2.5), ("E", 2.5)]
DWIN = (1.3, 0.55, 2.65, 0.15)                           # width, sill, head, depth


def keyroom_cutouts(scene):
    if scene != "dining":
        return []
    w, y0, y1, d = DWIN
    out = []
    for side, zc in DINING_WINDOWS:
        x = -KX if side == "W" else KX
        out.append({"min": [x - 0.01, y0, zc - w / 2], "max": [x + 0.01, y1, zc + w / 2]})
    return out


# ---------------------------------------------------------------- the green room (room frame: the door at the origin, the room toward -z)
def room_dims(lay):
    w, d, ox = GB.ROOMS[lay]
    return ox - w / 2, ox + w / 2, -0.2 - d, -0.2


def air_room(lay, standin=False):
    x0, x1, z0, z1 = room_dims(lay)
    H = GB.ROOM_H
    air = [box("bedroom", (x0, 0, -5.6), (x1, H, z1)), box("bedroom", (-1.3, 0, z0), (x1, H, -5.6)),
           box("nook", (x0, 0, z0), (-1.4, H, -5.7)), box("nook", (-1.4, 0, -6.6), (-1.3, H, -5.7))]
    if standin:                                          # the corridor outside the door, for the bake only (the light that comes in when it opens)
        air += [box("s_hole", (-GB.DOOR_W / 2, 0, -0.2), (GB.DOOR_W / 2, GB.DOOR_H, 0.0)),
                box("s_corridor", (-6.0, 0, 0.0), (6.0, GB.CORR_H, 2 * GB.CORR_Z))]
    return air


def room_standin_colliders(lay):
    """The corridor outside a room's door, as boxes (bake stand-ins only; never exported)."""
    x0, x1, z0, z1 = room_dims(lay)
    T, H, W = GB.T, GB.CORR_H, 2 * GB.CORR_Z
    out = [("SB_Floor", (-6.2, -0.3, -0.2), (6.2, 0.0, W + T)), ("SB_Ceiling", (-6.2, H, -0.2), (6.2, H + 0.2, W + T)),
           ("SB_Wall_Far", (-6.2, 0, W), (6.2, H, W + T)), ("SB_Wall_W", (-6.2, 0, 0), (-6.0, H, W)), ("SB_Wall_E", (6.0, 0, 0), (6.2, H, W)),
           ("SB_Wall_Near_W", (-6.2, 0, -0.2), (x0 - T, H, 0.0)), ("SB_Wall_Near_E", (x1 + T, 0, -0.2), (6.2, H, 0.0))]
    return [{"name": n, "min": list(a), "max": list(b)} for n, a, b in out]


GWIN = (-5.3, -4.3, 0.9, 2.2)                             # the green room's window in the east wall: z0, z1, y0, y1


def room_cutouts(lay):
    x0, x1, z0, z1 = room_dims(lay)
    return [{"min": [x1 - 0.01, GWIN[2], GWIN[0]], "max": [x1 + 0.01, GWIN[3], GWIN[1]]}]


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
    """The rectangle's four corners (game coordinates)."""
    a, bi, ci, p = q["axis"], q["bi"], q["ci"], q["p"]
    (b0, b1), (c0, c1) = q["b"], q["c"]
    pts = []
    for bb, cc in ((b0, c0), (b1, c0), (b1, c1), (b0, c1)):
        v = [0.0, 0.0, 0.0]
        v[a], v[bi], v[ci] = p, bb, cc
        pts.append(v)
    return pts


def y0_of(q):
    """The quad's lowest height (its y range is `b` or `c`, whichever axis is y)."""
    return q["b"][0] if q["bi"] == 1 else q["c"][0]


def area(q):
    return (q["b"][1] - q["b"][0]) * (q["c"][1] - q["c"][0])


# ---------------------------------------------------------------- materials of the skin
def corridor_material(q):
    a, s, reg, cn = q["axis"], q["side"], q["region"], q["coll"]
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
    if reg == "stairdoor":
        return "Threshold" if (a == 1 and s > 0) else "Jamb_Steel"
    if reg == "doorhole":
        return "Threshold" if (a == 1 and s > 0) else "Door_Jamb"
    if a == 1:
        if s > 0:
            return "Carpet_Green" if reg == "corridor" else "Carpet_Field"
        return "Ceiling_Plaster"
    if reg == "closet":
        return "Closet_Paint"
    return "Wall_Green" if y0_of(q) >= CHAIR - 1e-6 else "Wainscot"


def keyroom_material(q):
    a, s, reg = q["axis"], q["side"], q["region"]
    if reg == "doorhole":
        return "Threshold" if (a == 1 and s > 0) else "Door_Jamb"
    if a == 1:
        return "Carpet_Hall" if s > 0 else "Ceiling_Hall"
    return "Wall_Hall" if y0_of(q) >= KEY_DADO - 1e-6 else "Wainscot"


def room_material(q):
    a, s, reg = q["axis"], q["side"], q["region"]
    if reg.startswith("s_"):
        if a == 1:
            return "SB_Carpet" if s > 0 else "SB_Ceiling"
        return "SB_Wall"
    if a == 1:
        return "Carpet_Room" if s > 0 else "Ceiling_Room"
    return "Wall_Room"


# ---------------------------------------------------------------- the dressing slots
def sconces(scene, M):
    """[(side, x, dead)]: both walls, 2 m either side of every room door, clear of the alcove, closet and key-room openings (checked)."""
    holes = [(side, a, 0.8) for _, side, a in features(M)] + [(side, a, 0.54) for _, side, a in scene_doors(M)]
    dead = DEAD_SCONCES.get(scene, [])
    out = []
    for side in ("N", "S"):
        for x in SCONCE_XS:
            assert not any(s == side and abs(x - a) < w + 0.3 for s, a, w in holes), (scene, side, x)
            assert not any(abs(x - d) < GB.DOOR_W / 2 + 0.3 for d in GB.DOOR_XS)
            out.append((side, x, (side, x) in dead))
    return out


def recesses(scene):
    """The pieces set into the corridor walls, clear of doors, sconces' plates and the lift: (what, side, x0, x1, y0, y1, depth)."""
    if scene == "floor_2_lower":
        return [("extinguisher", "N", -19.55, -19.15, 1.0, 1.7, 0.12)]
    return [("extinguisher", "S", 18.6, 19.0, 1.0, 1.7, 0.12)]


def cutouts(scene):
    out = []
    Z = GB.CORR_Z
    for what, side, x0, x1, y0, y1, d in recesses(scene):
        z = -Z if side == "N" else Z
        out.append({"min": [x0, y0, z - 0.01], "max": [x1, y1, z + 0.01]})
    return out


def pictures(scene, M):
    """[(side, x)]: framed landscapes on the long walls where the wall is free (no door, opening, sconce or recess within reach)."""
    busy = [(s, a, 0.95) for _, _, s, a in room_doors(M)] + [(s, a, 1.1) for _, s, a in features(M)] + [(s, a, 1.0) for _, s, a in scene_doors(M)]
    busy += [(s, (x0 + x1) / 2, 0.9) for _, s, x0, x1, *_ in recesses(scene)]
    out = []
    for side in ("N", "S"):
        for x in (-12.0, -4.0, 4.0, 12.0):
            if not any(s == side and abs(x - a) < w for s, a, w in busy):
                out.append((side, x))
    return out


def scene_skin(scene, standin=False):
    M = model(scene)
    cols = colliders(M, kit=False)
    if scene in CORRIDORS:
        return skin(cols, air_corridor(M), cutouts(scene), splits_y=(CHAIR,)), M
    if scene in KEYROOMS:
        return skin(cols, air_keyroom(), keyroom_cutouts(scene), splits_y=(KEY_DADO,)), M
    if standin:
        allc = cols + room_standin_colliders(scene)
        q = skin(allc, air_room(scene, True), room_cutouts(scene))
        return [x for x in q if x["region"].startswith("s_")], M
    return skin(cols, air_room(scene), room_cutouts(scene)), M


def material_of(scene):
    return corridor_material if scene in CORRIDORS else keyroom_material if scene in KEYROOMS else room_material


def summary(scene):
    q, M = scene_skin(scene)
    matf = material_of(scene)
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
        print("  scene doors", scene_doors(M))
        print("  sconces", [(s, x) for s, x, d in sconces(scene, M) if d], "dead of", len(sconces(scene, M)))
        print("  recesses", recesses(scene))
        print("  pictures", pictures(scene, M))
    elif scene in ROOMS:
        sq, _ = scene_skin(scene, True)
        print(f"  stand-in skin: {len(sq)} quads, {sum(area(x) for x in sq):.1f} m2")


if __name__ == "__main__":
    for sc in (sys.argv[1:] or SCENES):
        summary(sc)
