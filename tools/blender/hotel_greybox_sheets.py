"""The hotel greybox's review sheets, drawn over the Blender renders of tools/blender/build_hotel_greybox.py (no Blender here; Pillow only).

    python tools/blender/hotel_greybox_sheets.py --renders <build out dir> [--out docs/renders/hotel_greybox] [--owner <png>]

For every scene: <out>/<scene>_plan.jpg (the orthographic plan with its labels, doors, links, spots, a scale bar and north; the atrium's four
galleries side by side) and <out>/<scene>_still.jpg (the eye-height still). Then <out>/overview.png (how the scenes join) and
<out>/README.md (every scene, its size, links and spots, the defaults, the open questions). --owner also writes a one-page sheet for a phone.
Labels come from the same model the build used, so they sit where the boxes are. Images are written fresh, with no metadata.
"""
import json
import math
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_hotel_greybox as G  # noqa: E402

FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/Library/Fonts")]


def font(size, bold=False):
    names = (["arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf", "Arial.ttf"])
    for d in FONT_DIRS:
        for n in names:
            if (d / n).exists():
                return ImageFont.truetype(str(d / n), size)
    return ImageFont.load_default()


INK, BLUE, ORANGE, MAGENTA, GREEN, GREY = (25, 25, 30), (20, 90, 200), (215, 110, 20), (190, 30, 150), (20, 150, 60), (110, 110, 115)
SPOT_COL = {"dealer": (200, 40, 40), "shop": (20, 140, 120), "puzzle": (130, 60, 200), "hide": (60, 60, 60), "bed": (150, 100, 40)}


def text(dr, xy, s, f, fill=INK, anchor="mm", halo=3):
    dr.text(xy, s, font=f, fill=fill, anchor=anchor, stroke_width=halo, stroke_fill=(255, 255, 255), align="center")


def dashed_rect(dr, x0, y0, x1, y1, col, dash=10, w=2):
    for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
        ln = math.hypot(bx - ax, by - ay)
        n = max(1, int(ln / dash))
        for i in range(0, n, 2):
            t0, t1 = i / n, min(1, (i + 1) / n)
            dr.line((ax + (bx - ax) * t0, ay + (by - ay) * t0, ax + (bx - ax) * t1, ay + (by - ay) * t1), fill=col, width=w)


def plan_panel(S, lv, raw):
    """One level's plan: the render, with the model's labels on it."""
    pv0 = G.plan_view(S, lv)
    ren = Image.open(raw).convert("RGB").resize((pv0["W"], pv0["H"]))
    sx, sz = pv0["W"] / (pv0["x1"] - pv0["x0"]), pv0["H"] / (pv0["z1"] - pv0["z0"])
    pv = dict(pv0)                                     # widened to show the rooms loaded behind the doors (outside the render)
    for o in S.outlines:
        pv["x0"], pv["x1"] = min(pv["x0"], o["x0"] - 1.0), max(pv["x1"], o["x1"] + 1.0)
        pv["z0"], pv["z1"] = min(pv["z0"], o["z0"] - 1.0), max(pv["z1"], o["z1"] + 1.0)
    pv["W"], pv["H"] = int(round((pv["x1"] - pv["x0"]) * sx)), int(round((pv["z1"] - pv["z0"]) * sz))
    im = Image.new("RGB", (pv["W"], pv["H"]), (236, 236, 236))
    im.paste(ren, (int(round((pv0["x0"] - pv["x0"]) * sx)), int(round((pv0["z0"] - pv["z0"]) * sz))))
    P = lambda x, z: ((x - pv["x0"]) * sx, (z - pv["z0"]) * sz)
    multi = len(S.levels) > 1
    here = lambda y: (lv - 0.6 <= y < lv + 2.4) if multi else True
    dr = ImageDraw.Draw(im)
    f_room, f_link, f_spot, f_note = font(30, True), font(19, True), font(16), font(18)
    for o in S.outlines:
        a, b = P(o["x0"], o["z0"]), P(o["x1"], o["z1"])
        dashed_rect(dr, a[0], a[1], b[0], b[1], GREY)
        text(dr, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), o["text"], f_note, GREY)
    for d in S.doors:
        if not here(d["hinge"][1]):
            continue
        w = d["props"]["width"]
        h0 = P(d["hinge"][0], d["hinge"][2])
        h1 = P(d["hinge"][0] + w * math.cos(d["yaw"]), d["hinge"][2] - w * math.sin(d["yaw"]))
        dr.line((h0, h1), fill=ORANGE, width=7)
    for e in S.empties:
        n, (x, y, z) = e["name"], e["pos"]
        if not here(y):
            continue
        px, pz = P(x, z)
        if n.startswith("Link_"):
            dr.ellipse((px - 9, pz - 9, px + 9, pz + 9), fill=BLUE, outline=(255, 255, 255), width=2)
        elif n.startswith("Arrive_"):
            fx, fz = e["face"]
            dr.line((px, pz, px + fx * 26, pz + fz * 26), fill=BLUE, width=3)
            dr.ellipse((px - 4, pz - 4, px + 4, pz + 4), fill=BLUE)
            door = n[7:]
            text(dr, (px + fx * 52, pz + fz * 52), door, f_link, BLUE)
        elif n.startswith("Spot_"):
            kind = n.split("_")[1]
            col = SPOT_COL.get(kind, MAGENTA)
            dr.rectangle((px - 7, pz - 7, px + 7, pz + 7), fill=col, outline=(255, 255, 255), width=2)
            text(dr, (px, pz - 20), n[5:], f_spot, col, halo=2)
        elif n.startswith("Marker_") and e["props"].get("kind") == "Spawn":
            dr.polygon([(px, pz - 14), (px + 12, pz + 9), (px - 12, pz + 9)], fill=GREEN, outline=(255, 255, 255))
            text(dr, (px, pz + 26), "spawn", f_spot, GREEN, halo=2)
    for lb in S.labels:
        if not here(lb["y"]):
            continue
        f = f_room if lb["kind"] == "room" else f_note
        text(dr, P(lb["x"], lb["z"]), lb["text"], f, INK if lb["kind"] == "room" else GREY)
    # scale bar and north
    span = pv["x1"] - pv["x0"]
    bar = 1 if span < 10 else 2 if span < 18 else 5 if span < 45 else 10
    bx, by = 24, pv["H"] - 30
    for i in range(4 if bar < 5 else 2):
        x0 = bx + i * bar * sx
        dr.rectangle((x0, by - 10, x0 + bar * sx, by), fill=INK if i % 2 == 0 else (255, 255, 255), outline=INK, width=2)
    n_seg = 4 if bar < 5 else 2
    text(dr, (bx + n_seg * bar * sx / 2, by - 26), f"{n_seg * bar} m", font(20, True), INK, halo=3)
    nx, ny = pv["W"] - 40, 50
    dr.polygon([(nx, ny - 26), (nx + 13, ny + 8), (nx - 13, ny + 8)], fill=INK)
    text(dr, (nx, ny + 28), "N", font(22, True), INK)
    if multi:
        text(dr, (pv["W"] / 2, 30), f"gallery y {int(lv)} ({G.LEVEL_NAME[lv]})", font(30, True), INK)
    return im


def links_text(S):
    out = []
    for door, to in S.links.items():
        out.append(f"{door}  ->  {to}")
    return out


def plan_sheet(S, renders, out):
    panels = [plan_panel(S, lv, renders / f"{S.id}_plan_L{int(lv)}.png") for lv in S.levels]
    if len(panels) == 1:
        body = panels[0]
    else:
        w, h = panels[0].size
        body = Image.new("RGB", (w * 2, h * 2), (255, 255, 255))
        for i, p in enumerate(panels):
            body.paste(p.resize((w, h)), ((i % 2) * w, (i // 2) * h))
        body = body.resize((body.width * 3 // 4, body.height * 3 // 4), Image.LANCZOS)
    side = 560
    rows = links_text(S)
    spots = {}
    for e in S.empties:
        if e["name"].startswith("Spot_"):
            k = e["name"].split("_")[1]
            spots[k] = spots.get(k, 0) + 1
    rooms = [f"{d['props']['room']}: {d['props']['room_layout']}" for d in S.doors if "room_layout" in d["props"]]
    head = 96
    H = max(body.height + head, head + 60 + 28 * (len(rows) + len(spots) + len(rooms) // 2 + 14))
    im = Image.new("RGB", (body.width + side, H), (255, 255, 255))
    im.paste(body, (0, head))
    dr = ImageDraw.Draw(im)
    text(dr, (16, 30), f"{S.id}  -  {S.title}", font(32, True), INK, anchor="lm", halo=0)
    text(dr, (16, 70), f"{S.size}.  Top-down, orthographic; ceilings and anything 2.4 m above the floor are left out.", font(19), GREY, anchor="lm", halo=0)
    x, y = body.width + 18, head + 10
    f, fb = font(19), font(21, True)

    def line(s, ff=f, col=INK):
        nonlocal y
        for part in textwrap.wrap(s, 46) or [""]:
            dr.text((x, y), part, font=ff, fill=col)
            y += 26
    line("LINKS (press F at the blue dot)", fb)
    for r in rows:
        line(r, f, BLUE)
    y += 10
    if spots:
        line("SPOTS", fb)
        line(", ".join(f"{k} x{v}" for k, v in sorted(spots.items())), f, MAGENTA)
        y += 10
    if rooms:
        line("ROOMS BEHIND THE DOORS (loaded on opening)", fb)
        for i in range(0, len(rooms), 2):
            line("   ".join(rooms[i:i + 2]), f, GREY)
        y += 10
    line("KEY", fb)
    line("orange bar: door leaf (from its hinge)", f, ORANGE)
    line("blue dot: Link_ (press F); blue tick: Arrive_ and the way you face", f, BLUE)
    line("square: Spot_; green triangle: Marker_Spawn", f, MAGENTA)
    line("dashed grey: a room loaded behind a door, or a loft above", f, GREY)
    im.save(out / f"{S.id}_plan.jpg", quality=88, optimize=True)        # no comment or APP1 segment


def still(S, renders, out):
    im = Image.open(renders / f"{S.id}_still.png").convert("RGB")
    dr = ImageDraw.Draw(im)
    (pos, face, pitch) = S.still
    text(dr, (20, im.height - 28), f"{S.id}: eye height {G.EYE} m, from ({pos[0]:g}, {pos[2]:g})", font(26, True), INK, anchor="lm")
    im.save(out / f"{S.id}_still.jpg", quality=86, optimize=True)        # Pillow writes no comment or APP1 (EXIF) segment unless asked


# ---------------------------------------------------------------- the overview: how the scenes join
OV = {   # scene: (x, y) centre on a 2400 by 1800 canvas
    "roof": (1500, 110), "floor_3": (1500, 300),
    "floor_2_upper": (1500, 500), "key_room": (2050, 500), "floor_2_lower": (1500, 680), "dining": (2050, 640), "reception": (2050, 760),
    "floor_1_upper": (1500, 880), "floor_1_lower": (1500, 1060),
    "atrium": (820, 700), "escalators": (420, 520), "other_stairs": (420, 860), "lobby": (820, 1240),
}
for _k in range(1, 12):
    OV[f"sub_pool_{_k:02d}"] = (130 + (_k - 1) * 205, 1640)
for _k in range(1, 8):
    OV[f"maze_{_k:02d}"] = (110 + (_k - 1) * 172, 140)
CONN_COL = {"doors": (60, 60, 70), "elevator": (20, 90, 200), "stairs": (215, 110, 20), "one_way": (190, 30, 150), "pool_route": (20, 140, 200),
            "escalator": (215, 160, 20)}


def overview(out, sizes):
    W, H = 2400, 1800
    im = Image.new("RGB", (W, H), (250, 250, 248))
    dr = ImageDraw.Draw(im)
    bw = {"atrium": (300, 460)}
    def boxof(s):
        w, h = bw.get(s, (330 if not s.startswith(("sub_pool", "maze")) else (175 if s.startswith("sub_pool") else 128), 92 if not s.startswith(("sub_pool", "maze")) else 84))
        x, y = OV[s]
        return x - w / 2, y - h / 2, x + w / 2, y + h / 2
    def anchor(s, other):
        x0, y0, x1, y1 = boxof(s)
        ox, oy = OV[other]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if s == "atrium" and other in ("floor_1_lower", "floor_2_lower", "floor_3"):
            ys = {"floor_3": y0 + 60, "floor_2_lower": y0 + 170, "floor_1_lower": y0 + 280}
            return x1, ys[other]
        dx, dy = ox - cx, oy - cy
        if abs(dx) * (y1 - y0) > abs(dy) * (x1 - x0):
            return (x1 if dx > 0 else x0), cy
        return cx, (y1 if dy > 0 else y0)
    # edges first
    seen = set()
    for (a, da), (b, db), kind, note in G.PAIRS:
        key = (min(a, b), max(a, b), kind)
        if a.startswith("maze") or b.startswith("maze"):
            if a == "atrium" or b == "atrium":
                pass
        if key in seen and a != "atrium" and b != "atrium":
            continue
        seen.add(key)
        if a == "atrium" and b.startswith("sub_pool"):          # drawn below as one fan
            continue
        p, q = anchor(a, b), anchor(b, a)
        col = CONN_COL[kind]
        dr.line((p, q), fill=col, width=5 if kind != "pool_route" else 4)
        if kind == "one_way":
            mx, my = (p[0] * 0.4 + q[0] * 0.6), (p[1] * 0.4 + q[1] * 0.6)
            ang = math.atan2(q[1] - p[1], q[0] - p[0])
            dr.polygon([(mx + 16 * math.cos(ang), my + 16 * math.sin(ang)), (mx + 12 * math.cos(ang + 2.5), my + 12 * math.sin(ang + 2.5)),
                        (mx + 12 * math.cos(ang - 2.5), my + 12 * math.sin(ang - 2.5))], fill=col)
    # the atrium's eleven pool doors as one fan
    ax, ay = OV["atrium"][0], boxof("atrium")[3]
    for k in range(1, 12):
        px, py = OV[f"sub_pool_{k:02d}"][0], boxof(f"sub_pool_{k:02d}")[1]
        dr.line((ax - 100 + k * 17, ay, px, py), fill=(170, 170, 170), width=2)
    text(dr, (1230, 1470), "the atrium's sub-floor gallery has a door to each pool", font(22), GREY)
    # outside the hotel
    dr.line((anchor("lobby", "floor_1_lower")[0], OV["lobby"][1], 1300, OV["lobby"][1]), fill=CONN_COL["doors"], width=5)
    text(dr, (1420, OV["lobby"][1]), "street\n(tower door)", font(24, True), INK)
    x11 = boxof("sub_pool_11")[2]
    dr.line((x11, OV["sub_pool_11"][1], x11 + 60, OV["sub_pool_11"][1]), fill=CONN_COL["pool_route"], width=4)
    text(dr, (x11 + 95, OV["sub_pool_11"][1]), "B1", font(26, True), INK)
    for s in OV:
        x0, y0, x1, y1 = boxof(s)
        big = not s.startswith(("sub_pool", "maze"))
        fill = (255, 255, 255) if s in G.SCENES else (240, 240, 240)
        dr.rounded_rectangle((x0, y0, x1, y1), 14, fill=fill, outline=INK, width=3)
        text(dr, ((x0 + x1) / 2, y0 + (26 if big else 24)), s, font(26 if big else 21, True), INK, halo=0)
        sz = sizes.get(s, "")
        if big:
            for i, part in enumerate(textwrap.wrap(sz, 30)[:2 if s != "atrium" else 9]):
                text(dr, ((x0 + x1) / 2, y0 + 56 + i * 24), part, font(19), GREY, halo=0)
        else:
            text(dr, ((x0 + x1) / 2, y0 + 56), sz, font(17), GREY, halo=0)
    text(dr, (W / 2, 1735), "Hotel greybox: how the scenes join.  Lines: grey doors, blue elevator, orange stairs, yellow escalators, "
                            "pink one-way (arrow), light blue underwater (shut until swimming).", font(23), INK, halo=0)
    text(dr, (640, 40), "the anomaly maze: one way, 01 to 07, then out to the atrium", font(22), GREY, halo=0)
    text(dr, (1900, 1230), "ROOM LAYOUTS behind the corridor doors (world/rooms):\nmotel_a, motel_b (floor 1)\ngreen_room (floor 2)\n"
                           "clue_room, empty_room, part 1's apartment (floor 3)", font(22), INK, halo=0)
    im.save(out / "overview.png", optimize=True)
    return im


SHORT = {"lobby": "20 x 22 m, 6 m high, on the tower's footprint", "atrium": "36 x 36 m, 16 m high; galleries at y 0, 4, 8, 12; the elevator shaft; "
         "the narrow hall from the lobby", "escalators": "6 x 8.8 m, three runs", "other_stairs": "5.2 x 6 m, a switchback",
         "roof": "24 x 24 m, open sky", "dining": "14 x 10 m", "reception": "14 x 10 m", "key_room": "14 x 10 m"}


def short_size(S):
    if S.id in SHORT:
        return SHORT[S.id]
    if S.id.startswith("floor"):
        return "corridor 40 x 2.2 m, 10 doors"
    if S.id.startswith("sub_pool"):
        (bx0, bx1, bz0, bz1), _, _, h = G.POOLS[int(S.id[-2:])]
        return f"pool {bx1 - bx0:g} x {bz1 - bz0:g} m"
    if S.id.startswith("maze"):
        return "16 x 16 m"
    return S.size


# ---------------------------------------------------------------- the README
DEFAULTS = [
    ("lobby", "20 m by 22 m, 6 m high, on the tower's footprint (x -28 to -8, z -30 to -8)", "Kept. The walls stand inside the footprint, so the floor is 19.6 m by 21.6 m. The front doors are a 1.8 m pair at z -19 (the street's door size)."),
    ("atrium", "36 m by 36 m, galleries at y 0, 4, 8 and 12", "Kept, 16 m high. The galleries are 4 m deep on all four sides. The narrow hall from the lobby (10 m by 1.6 m) is built into this scene, on its east side."),
    ("floor_1/2 lower and upper", "a corridor 40 m by 2.2 m, rooms both sides, 10 doors a level", "Kept: 2.8 m high, doors every 8 m. The lower levels add a 6.4 m stairwell at the east end (the scene is 47 m long); the upper levels a 1.4 m landing."),
    ("dining, reception, key_room", "about 14 m by 10 m", "Kept: 14 m by 10 m, 3 m high."),
    ("floor_3", "one corridor, 10 doors, one level", "Kept, the same corridor as floors 1 and 2, with the stairwell up to the roof."),
    ("roof", "24 m by 24 m, open sky", "Kept: a 1.1 m parapet, the stair bulkhead and the kit's safe house as a 6 m by 5 m room."),
    ("sub_pool_01 to 11", "about 20 m by 20 m", "Kept, 3.2 m (odd) or 4 m (even) high; each pool differs in size and place, 1.2 m shallow and 2.4 m deep."),
    ("maze_01 to 07", "about 16 m by 16 m", "Kept, 3 m high: 8 by 8 cells of 2 m (odd) or 7 by 7 of 2.29 m (even); the odd ones have a 4 m room in the middle."),
    ("escalators, other_stairs", "connector-sized", "6 m by 8.8 m and 5.2 m by 6 m, both 15.2 m high, reaching all four galleries."),
    ("room layouts", "4 m by 6 m to 6 m by 8 m", "motel_a 4 x 6, motel_b 5 x 6, green_room 5 x 7, clue_room 5 x 6, empty_room 6 x 8 (all 2.8 m high)."),
]
CHANGES = [
    "The atrium has a second maze door, `maze_exit` on its east wall, where you come out after solving maze_07 (the table names only the way in).",
    "The elevator stops at the atrium's four galleries. Floors 1 and 2 have it on their lower level only; their upper levels are reached by the stairs.",
    "Spot kinds the table does not name: `npc` (the receptionists), `clue` and `key` (the key rooms, clue_room), `facade` (the lobby's three facade doors, places for later features), and the safe house's `stash`, `save`, `craft`, `respawn` and `locker`.",
    "The manifest's hotel stub lists `sub_pools` and `anomaly_maze`; the greybox uses `sub_pool_01` to `11` and `maze_01` to `07`, as docs/BLENDER_AREAS.md does.",
]
QUESTIONS = [
    "Scale: the lobby fills the tower's 20 m by 22 m footprint, but the atrium behind it is 36 m by 36 m, bigger than the tower. Keep it (bigger inside, liminal), or shrink it to about 20 m?",
    "The atrium's ground floor is the sub-floor gallery (y 0), and the lobby's hall comes in there. Fine, or should the lobby's hall arrive between the sub floor and floor 1?",
    "Floors 1 and 2: should the elevator also stop on their upper levels? Now it stops on the lower levels only.",
    "The anomaly maze is one fixed chain, maze_01 to maze_07 and then out. Or should each maze lead back to the atrium, with the elevator's glitch picking one?",
    "Rooms: floor 1 alternates motel_a and motel_b, floor 2 is all green_room, floor 3's doors point at part 1's apartment, with clue_room and empty_room as the other choices. Is that the mix you want?",
    "The pools: each has a shallow and a deep end, with steps down; the odd ones also have 12 cm of water over the whole floor. Is that the flooded look you want?",
    "The key rooms: dining and reception open off floor 2's lower level, the key room off its upper level. Is that right?",
]


def readme(out, docs):
    L = ["# Hotel greybox (docs/BLENDER_AREAS.md, section 1, step 1)", "",
         "Plain grey boxes, to scale, for every scene of the apartment tower: 31 scenes and 5 room layouts. There are no reference photos, so "
         "every scene is built from its written description, and a photo name in the table is only a label. This is for review: no scene or "
         "link has been added to the manifest, and the greybox GLBs are in `glb/` here, not in `world/`.", "",
         "- Built by `tools/blender/build_hotel_greybox.py`, which writes `world/<scene>.json` (the room layouts go to `world/rooms/<layout>.json`) "
         "through `tools/blender/export_scene.py`, the GLB, the plans and the stills. The labels and these sheets come from "
         "`tools/blender/hotel_greybox_sheets.py`.",
         "- `python tools/blender/build_hotel_greybox.py --check .` runs the gates on the exported files: every link meets its other side, "
         "every step rises at most 0.27 m, every corridor is at least 1.6 m wide and clear.",
         "- `CHECKS.txt`: the gates and `node tools/worlddoc.mjs check` on every file (0 errors; every warning says a scene or link is new to the manifest).",
         "- `overview.png`: how the scenes join. For each scene, `<scene>_plan.jpg` (top-down, scale bar, rooms, doors and links labelled) and "
         "`<scene>_still.jpg` (eye height, 1.55 m).", "",
         "## Scenes", "", "| Scene | Size | Links (door: where it goes) | Colliders, doors, spots | Mood |", "|---|---|---|---|---|"]
    for sid in G.SCENES:
        S = G.build(sid)
        d = docs.get(sid, {})
        spots = {}
        for sp in d.get("spots", []):
            spots[sp["kind"]] = spots.get(sp["kind"], 0) + 1
        sp = ", ".join(f"{k} x{v}" for k, v in sorted(spots.items())) or "none"
        links = "; ".join(f"`{k}`: {v}" for k, v in S.links.items()) or ("none: loaded behind a corridor door" if S.kind == "room" else "none")
        where = "world/rooms/" if S.kind == "room" else "world/"
        L.append(f"| `{sid}` ({where}) | {S.size} | {links} | {len(d.get('colliders', []))} colliders, {len(d.get('doors', []))} doors; spots: {sp} | {S.mood or 'room'} |")
    L += ["", "## Links between scenes", "",
          "Each pair is one link. Pressing F at one side's `Link_<door>` puts you at the other side's `Arrive_<door>`, facing its -Y axis. "
          "Every pair has both sides built (the gate checks it).", "", "| From | To | Connector | Note |", "|---|---|---|---|"]
    for (a, da), (b, db), kind, note in G.PAIRS:
        L.append(f"| `{a}.{da}` | `{b}.{db}` | {kind} | {note} |")
    L += ["", "Links that leave the hotel, or stay inside one scene:", ""]
    for (s, dd), note in G.OUTSIDE.items():
        L.append(f"- `{s}.{dd}`: {note}")
    L += ["", "## Room layouts behind the corridor doors", "",
          "A corridor door's `DoorLeaf_room_<n>` carries `room` (its number), `room_layout`, and where the room's frame goes: `room_x`, `room_z` "
          "(the frame's origin, the middle of the doorway on the corridor's face of the wall) and `room_yaw_deg` (three's rotation.y; 0 on the "
          "north side, 180 on the south). In `world/rooms/<layout>.json` the room lies toward -z from that origin; its door wall is the "
          "corridor's wall, so the two overlap exactly. The exporter now keeps a door's custom properties (a separate commit).", ""]
    L += ["## The defaults ([DEFAULT] in docs/BLENDER_AREAS.md)", "", "| Scene | Default | Kept or changed |", "|---|---|---|"]
    for s, dflt, k in DEFAULTS:
        L.append(f"| {s} | {dflt} | {k} |")
    L += ["", "Choices the table left open:", ""] + [f"- {c}" for c in CHANGES]
    L += ["", "## Open questions for the owner", ""] + [f"{i}. {q}" for i, q in enumerate(QUESTIONS, 1)]
    L += ["", "## Not done here", "",
          "- Placeholders: the elevator is a shaft with a box for a car, and each corridor has a closed lift car behind its lift door; the "
          "connector kit replaces them later. The escalators are stairs (one box a step).",
          "- The roof's skyline is an R3 backdrop, still to render. Swimming is not in the game, so the pools' underwater links stay shut.",
          "- The manifest, `index.html`, `shared/` and the tests are untouched. `node tools/worlddoc.mjs check` warns that each scene and link "
          "is new; that is expected until the coordinator adds them.", ""]
    (out / "README.md").write_text("\n".join(L), encoding="utf-8")


def owner_sheet(path, out, renders):
    W = 1080
    pics = ["lobby", "atrium", "floor_1_lower", "floor_2_lower", "sub_pool_01", "maze_03", "roof", "escalators"]
    f_t, f_h, f_b = font(52, True), font(38, True), font(32)
    blocks = []
    def para(s, f, col=INK, wrap=48, gap=10):
        for p in textwrap.wrap(s, wrap):
            blocks.append(("t", p, f, col))
        blocks.append(("gap", gap))
    para("Hotel greybox: ready to look at", f_t, wrap=30)
    para("31 scenes and 5 room layouts, plain grey boxes to scale, all joined. Nothing is wired into the game yet.", f_b, GREY)
    blocks.append(("img", Image.open(out / "overview.png")))
    blocks.append(("gap", 20))
    para("What it looks like at eye height", f_h)
    grid = []
    for s in pics:
        im = Image.open(renders / f"{s}_still.png").convert("RGB")
        grid.append((s, im.resize((520, 292), Image.LANCZOS)))
    blocks.append(("grid", grid))
    blocks.append(("gap", 20))
    para("Questions for you", f_h)
    for i, q in enumerate(QUESTIONS, 1):
        para(f"{i}. {q}", f_b, INK, wrap=50, gap=18)
    para("Silence means carry on with dressing, one scene at a time.", f_b, GREY)
    H = 40
    for b in blocks:
        if b[0] == "t":
            H += b[2].size + 12
        elif b[0] == "gap":
            H += b[1]
        elif b[0] == "img":
            H += int(b[1].height * (W - 40) / b[1].width) + 10
        else:
            H += ((len(b[1]) + 1) // 2) * (292 + 50)
    im = Image.new("RGB", (W, H + 40), (255, 255, 255))
    dr = ImageDraw.Draw(im)
    y = 40
    for b in blocks:
        if b[0] == "t":
            dr.text((28, y), b[1], font=b[2], fill=b[3])
            y += b[2].size + 12
        elif b[0] == "gap":
            y += b[1]
        elif b[0] == "img":
            o = b[1].resize((W - 40, int(b[1].height * (W - 40) / b[1].width)), Image.LANCZOS)
            im.paste(o, (20, y))
            y += o.height + 10
        else:
            for i, (s, g) in enumerate(b[1]):
                gx, gy = 13 + (i % 2) * 534, y + (i // 2) * 342
                im.paste(g, (gx, gy))
                dr.text((gx + 4, gy + 296), s, font=font(30, True), fill=INK)
            y += ((len(b[1]) + 1) // 2) * 342
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)


def main(a):
    renders = Path(a[a.index("--renders") + 1])
    out = Path(a[a.index("--out") + 1]) if "--out" in a else G.ROOT / "docs/renders/hotel_greybox"
    out.mkdir(parents=True, exist_ok=True)
    docs = {}
    for sid in G.SCENES:
        f = G.out_path(renders, sid)
        if f.exists():
            docs[sid] = json.loads(f.read_text())
    sizes = {}
    for sid in G.SCENES:
        S = G.build(sid)
        sizes[sid] = short_size(S)
        plan_sheet(S, renders / "renders", out)
        still(S, renders / "renders", out)
    overview(out, sizes)
    readme(out, docs)
    if "--owner" in a:
        owner_sheet(a[a.index("--owner") + 1], out, renders / "renders")
    print("sheets written to", out)


if __name__ == "__main__":
    main(sys.argv[1:])
