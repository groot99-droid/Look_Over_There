"""Going back in, dressing pass, pure Python: which faces of a chamber's greybox boxes a walker can see, and how the chamber meets the
connector kit's pieces. Used by tools/blender/build_gbi_dress.py (in Blender) and testable without Blender:

    python tools/blender/gbi_dress_skin.py [scene ...]      prints each chamber's skin per material, its kit hulls and casings

The layout is the greybox's (tools/blender/build_gbi_greybox.build(scene)), unchanged; this file adds only what the art needs:

- the colliders sorted into what the shell draws (walls, partitions, columns, the elevator's shaft), what the dressing draws (furniture,
  racks, islands, plinths, the vent ducts) and what the kit's own GLB draws (every collider a kit piece brought);
- HULLS: the space each kit piece's GLB fills. The shell draws nothing inside a hull (the kit draws its own floor, walls and doorway);
- CASINGS: art-only boxes round the kit pieces whose GLB has no outside (the painted-sky hall, the stair door's hallway and the top of its
  landing) and round the safe house (its own outside is baked dark for a roof at night, so the chamber covers it 1 cm out, in its own light);
- skin(): every face of a shell box or casing that looks into the chamber's air, cut where another box meets it.

Coordinates are GAME coordinates (metres, y up, north = -z), as in the greybox.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_gbi_greybox as GB  # noqa: E402

SCENES = ("gbi_L4_1", "gbi_L4_2", "gbi_L4_3", "gbi_L3_2", "gbi_L3_3", "gbi_L3_4")
FRONT = 0.004            # a face is seen if the point this far in front of it is in the air
# colliders the dressing draws (their art is furniture, not shell); everything else that is not the kit's is shell
FURNITURE = ("Gondola_", "Island_", "Cash_Desk", "Display_", "Sofa_", "Bed_", "Rack_", "Pallets_", "Plinth_", "Vent_")
SOLID_FURNITURE = ("Gondola_", "Island_", "Cash_Desk", "Plinth_", "Vent_", "Pallets_", "Bed_")   # their art fills the box: no shell drawn under them


def model(scene):
    return GB.build(scene)


def kit_tag(b):
    return next((t for t in b["tags"] if t.startswith("kit:")), None)


def is_kit(b):
    """A collider a kit piece brought (its art is the kit's GLB). The elevator's shaft (Shaft_*) is the greybox's own: the shell draws it."""
    return kit_tag(b) is not None and not b["name"].startswith("Shaft_")


def is_furniture(b):
    return b["name"].startswith(FURNITURE)


def colliders(M):
    return [b for b in M.boxes if b["col"]]


def shell_boxes(M):
    return [{"name": b["name"], "min": list(b["min"]), "max": list(b["max"])} for b in colliders(M) if not is_kit(b) and not is_furniture(b)]


def _rot(x, z, yaw):
    a = math.radians(yaw)
    return x * math.cos(a) + z * math.sin(a), -x * math.sin(a) + z * math.cos(a)


def place_box(k, mn, mx):
    """A kit-frame box (x, y, z) -> its game box at the placement k = {at, yaw}."""
    ax, ay, az = k["at"]
    pts = []
    for x in (mn[0], mx[0]):
        for z in (mn[2], mx[2]):
            dx, dz = _rot(x, z, k["yaw"])
            pts.append((ax + dx, az + dz))
    return ([round(min(p[0] for p in pts), 4), round(ay + mn[1], 4), round(min(p[1] for p in pts), 4)],
            [round(max(p[0] for p in pts), 4), round(ay + mx[1], 4), round(max(p[1] for p in pts), 4)])


# kit-frame boxes per piece (blender/kit/README.md; world/kit/<piece>.json): what its GLB fills (hull) and the casings the chamber adds
KIT_SHAPES = {
    "elevator": {"hull": [((-1.05, -0.12, -2.35), (1.05, 2.48, -0.25)), ((-0.68, 0.0, -0.25), (0.68, 2.4, 0.0))], "casing": []},
    "sky_hall": {"hull": [((-1.4, 0.0, -10.4), (1.4, 3.25, 0.0))],
                 "casing": [("body", (-1.4, 0.0, -10.4), (1.4, 3.25, -0.2)), ("front_w", (-1.4, 0.0, -0.2), (-0.55, 3.25, 0.0)),
                            ("front_e", (0.55, 0.0, -0.2), (1.4, 3.25, 0.0)), ("head", (-0.55, 2.16, -0.2), (0.55, 3.25, 0.0))]},
    "stair_door": {"hull": [((-1.4, -0.3, -10.4), (1.4, 2.9, -0.2)), ((-1.35, -0.2, -0.2), (1.35, 2.92, 1.6))],
                   "casing": [("hall", (-1.4, -0.3, -10.4), (1.4, 2.9, -0.2)), ("landing_roof", (-1.35, 2.9, -0.2), (1.35, 2.92, 1.6))]},
    "safe_house": {"hull": [((-3.21, 0.0, -5.41), (3.21, 3.01, 0.01))],
                   "casing": [("body", (-3.21, 0.0, -5.41), (3.21, 3.01, -0.2)), ("front_w", (-3.21, 0.0, -0.2), (-0.5, 3.01, 0.01)),
                              ("front_e", (0.5, 0.0, -0.2), (3.21, 3.01, 0.01)), ("head", (-0.5, 2.16, -0.2), (0.5, 3.01, 0.01))]},
}


def hulls(M):
    out = []
    for k in M.kits:
        for mn, mx in KIT_SHAPES[k["piece"]]["hull"]:
            a, b = place_box(k, mn, mx)
            out.append({"name": f"hull_{k['sfx']}", "min": a, "max": b, "piece": k["piece"]})
    return out


def casings(M):
    out = []
    for k in M.kits:
        for nm, mn, mx in KIT_SHAPES[k["piece"]]["casing"]:
            a, b = place_box(k, mn, mx)
            out.append({"name": f"Casing_{k['sfx']}_{nm}", "min": a, "max": b, "piece": k["piece"], "casing": True})
    return out


def outer_holes(M):
    """The plain doors in the outer wall (outer_door): their holes, as air, and a backing box behind each (the door opens onto a wall)."""
    air, backs = [], []
    for d in M.doors:
        if d.get("kit") or d["props"].get("kind") not in ("door", "hall door"):
            continue
        h = d["hinge"]
        th = math.radians(d["props"]["closed_yaw_deg"])
        rx, rz = math.cos(th), -math.sin(th)
        cx, cz = h[0] + rx * GB.DOOR_W / 2, h[2] + rz * GB.DOOR_W / 2
        Y = M.Y
        if abs(cz - GB.Z0) < 1e-6 or abs(cz - GB.Z1) < 1e-6:
            z0, z1 = (GB.Z0 - GB.T, GB.Z0) if abs(cz - GB.Z0) < 1e-6 else (GB.Z1, GB.Z1 + GB.T)
            air.append({"region": "doorhole", "min": [cx - GB.HOLE_W / 2, Y, z0], "max": [cx + GB.HOLE_W / 2, Y + GB.HOLE_H, z1]})
            zb = z0 - 0.02 if z0 < GB.Z0 else z1
            backs.append({"name": f"Backing_{d['name'][9:]}", "min": [cx - 0.6, Y, zb], "max": [cx + 0.6, Y + 2.4, zb + 0.02], "casing": True})
        else:
            x0, x1 = (GB.X0 - GB.T, GB.X0) if abs(cx - GB.X0) < 1e-6 else (GB.X1, GB.X1 + GB.T)
            air.append({"region": "doorhole", "min": [x0, Y, cz - GB.HOLE_W / 2], "max": [x1, Y + GB.HOLE_H, cz + GB.HOLE_W / 2]})
            xb = x0 - 0.02 if x0 < GB.X0 else x1
            backs.append({"name": f"Backing_{d['name'][9:]}", "min": [xb, Y, cz - 0.6], "max": [xb + 0.02, Y + 2.4, cz + 0.6], "casing": True})
    return air, backs


def air_of(M):
    Y, H = M.Y, M.H
    air = [{"region": "room", "min": [GB.X0, Y, GB.Z0], "max": [GB.X1, Y + H, GB.Z1]}]
    holes, _ = outer_holes(M)
    return air + holes


def _inside(p, b, e=1e-4):
    return all(b["min"][i] + e < p[i] < b["max"][i] - e for i in range(3))


def _within(p, b, e=1e-7):
    return all(b["min"][i] - e <= p[i] <= b["max"][i] + e for i in range(3))


def skin(M):
    """Every face of a shell box or a casing that looks into the air (and not into a kit hull), as merged rectangles:
    [{coll, axis, side, p, bi, ci, b: (u0, u1), c: (v0, v1), region, casing}]."""
    arch = shell_boxes(M)
    _, backs = outer_holes(M)
    cas = casings(M) + backs
    solid = arch + cas
    hl = hulls(M)
    air = air_of(M)
    kitc = [{"name": b["name"], "min": b["min"], "max": b["max"]} for b in colliders(M) if is_kit(b)]
    furn = [{"name": b["name"], "min": b["min"], "max": b["max"]} for b in colliders(M) if is_furniture(b)]
    full = [f for f in furn if f["name"].startswith(SOLID_FURNITURE)]
    everything = solid + air + hl + kitc
    out = []
    for C in sorted(solid, key=lambda c: c["name"]):
        own_hull = [h for h in hl if C.get("casing") and C["name"].startswith("Casing_" + h["name"][5:] + "_")]
        for a in range(3):
            bi, ci = [i for i in range(3) if i != a]
            for side in (-1, 1):
                p = C["max"][a] if side > 0 else C["min"][a]
                cuts = {bi: {C["min"][bi], C["max"][bi]}, ci: {C["min"][ci], C["max"][ci]}}
                for o in everything + furn:
                    if o is C or not (o["min"][a] - 0.01 <= p <= o["max"][a] + 0.01):
                        continue
                    for k in (bi, ci):
                        for v in (o["min"][k], o["max"][k]):
                            if C["min"][k] < v < C["max"][k]:
                                cuts[k].add(v)
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
                        if reg is None:
                            continue
                        if any(_within(f, h, -1e-6) for h in hl if h not in own_hull) or any(_inside(f, h) for h in own_hull):
                            continue
                        if any(_inside(f, o) for o in solid + kitc + full if o is not C):
                            continue
                        dup = False
                        for o in solid:                   # two boxes with the same face here: the first by name draws it
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
                    while (i1 + 1, j) in cells and (i1 + 1, j) not in used and cells[(i1 + 1, j)] == reg:
                        i1 += 1
                    j1 = j
                    while all((k, j1 + 1) in cells and (k, j1 + 1) not in used and cells[(k, j1 + 1)] == reg for k in range(i, i1 + 1)):
                        j1 += 1
                    for k in range(i, i1 + 1):
                        for m in range(j, j1 + 1):
                            used.add((k, m))
                    out.append({"coll": C["name"], "axis": a, "side": side, "p": p, "bi": bi, "ci": ci,
                                "b": (ub[i], ub[i1 + 1]), "c": (uc[j], uc[j1 + 1]), "region": reg, "casing": bool(C.get("casing"))})
    return out


def quad_points(q):
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


def material(q, floor):
    """The shell's role materials (Secret Operations swaps them by name): the floor slab's top, the ceiling's underside, every other face
    the floor's wall; the casings round the kit pieces are M_GBI_kit."""
    if q["casing"]:
        return f"M_D_wall_{floor}" if q["coll"].startswith("Backing_") else "M_GBI_kit"
    if q["coll"] == "Floor" and q["axis"] == 1 and q["side"] > 0:
        return f"M_D_floor_{floor}"
    if q["coll"] == "Ceiling" and q["axis"] == 1 and q["side"] < 0:
        return f"M_D_ceil_{floor}"
    return f"M_D_wall_{floor}"


SHELL_MATS = ("M_D_floor_", "M_D_wall_", "M_D_ceil_", "M_GBI_kit")


def summary(scene):
    M = model(scene)
    q = skin(M)
    by = {}
    for x in q:
        m = material(x, M.floor)
        n, a = by.get(m, (0, 0.0))
        by[m] = (n + 1, a + area(x))
    print(f"SKIN {scene}: {len(q)} quads, {sum(area(x) for x in q):.1f} m2; kit {[(k['piece'], k['sfx']) for k in M.kits]}")
    for m, (n, a) in sorted(by.items()):
        print(f"  {m:18s} {n:4d} quads {a:8.1f} m2")
    print("  furniture:", sorted({b['name'].split('_')[0] for b in colliders(M) if is_furniture(b)}))


if __name__ == "__main__":
    for sc in (sys.argv[1:] or SCENES):
        summary(sc)
