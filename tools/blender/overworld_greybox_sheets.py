"""The Overworld greybox's review sheets, drawn over the Blender renders of tools/blender/build_overworld_greybox.py (no Blender here; Pillow only).
It follows tools/blender/hotel_greybox_sheets.py and mall_greybox_sheets.py.

    python tools/blender/overworld_greybox_sheets.py --renders <build out dir> [--out docs/renders/overworld_greybox] [--owner <png>]

For every scene: <out>/<scene>_plan.jpg (the orthographic plan with its labels, doors, links, spots, clear ground, a scale bar and north; a
scene with two levels, or the long road in four pieces, has them side by side) and <out>/<scene>_still.jpg (the eye-height still). Then
<out>/overview.png (how the scenes join the parking lot, the street and the forest, and the four skies) and <out>/README.md (every scene, its
size, links and spots, where the two sets attach, the defaults, the open questions). --owner also writes a one-page sheet for a phone. Labels
come from the same model the build used, so they sit where the boxes are. Images are written fresh, with no metadata.
"""
import json
import math
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_overworld_greybox as G  # noqa: E402

FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/Library/Fonts")]


def font(size, bold=False):
    names = (["arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf", "Arial.ttf"])
    for d in FONT_DIRS:
        for n in names:
            if (d / n).exists():
                return ImageFont.truetype(str(d / n), size)
    return ImageFont.load_default()


INK, BLUE, ORANGE, MAGENTA, GREEN, GREY, RED = (25, 25, 30), (20, 90, 200), (215, 110, 20), (190, 30, 150), (20, 150, 60), (110, 110, 115), (200, 30, 30)
SPOT_COL = {"shop": (200, 40, 40), "puzzle": (130, 60, 200), "minigame": (20, 140, 160), "groundskeeper": (40, 120, 40), "toy": (215, 110, 20),
            "facade": (120, 90, 60)}
WALK_MPS = 4.0              # docs/GAMEPLAY.md: you walk at 4 m/s


def text(dr, xy, s, f, fill=INK, anchor="mm", halo=3):
    dr.text(xy, s, font=f, fill=fill, anchor=anchor, stroke_width=halo, stroke_fill=(255, 255, 255), align="center")


def dashed_rect(dr, x0, y0, x1, y1, col, dash=10, w=2):
    for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
        ln = math.hypot(bx - ax, by - ay)
        n = max(1, int(ln / dash))
        for i in range(0, n, 2):
            t0, t1 = i / n, min(1, (i + 1) / n)
            dr.line((ax + (bx - ax) * t0, ay + (by - ay) * t0, ax + (bx - ax) * t1, ay + (by - ay) * t1), fill=col, width=w)


def plan_panel(S, pv, raw, title=None):
    """One plan view: the render, with the model's labels on it."""
    im = Image.open(raw).convert("RGB").resize((pv["W"], pv["H"]))
    sx = pv["W"] / (pv["x1"] - pv["x0"])
    P = lambda x, z: ((x - pv["x0"]) * sx, (z - pv["z0"]) * sx)
    lv = pv["level"]
    multi = len(S.levels) > 1
    here = lambda y: (lv - 0.6 <= y < lv + 2.4) if multi else True
    inside = lambda x, z: pv["x0"] <= x <= pv["x1"] and pv["z0"] <= z <= pv["z1"]
    dr = ImageDraw.Draw(im)
    small = pv["ppm"] < 6 or S.segments
    f_room, f_link, f_spot, f_note = font(26 if small else 30, True), font(17 if small else 19, True), font(14 if small else 15), font(16 if small else 18)
    for o in S.outlines:
        a, b = P(o["x0"], o["z0"]), P(o["x1"], o["z1"])
        dashed_rect(dr, min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]), GREY, w=3)
    if S.id == "endless_hills":                              # the relief: contours every 0.5 m, from the same height function
        step = 0.5
        lvl = lambda x, z: math.floor(G.hill_h(x, z) / step)
        for zi in range(int(pv["z0"]), int(pv["z1"])):
            for xi in range(int(pv["x0"]), int(pv["x1"])):
                if not (-G.HILL_HALF <= xi < G.HILL_HALF and -G.HILL_HALF <= zi < G.HILL_HALF):
                    continue
                a = lvl(xi, zi)
                if a != lvl(xi + 1, zi) or a != lvl(xi, zi + 1):
                    px, pz = P(xi, zi)
                    dr.rectangle((px - 1, pz - 1, px + 1, pz + 1), fill=(40, 100, 50))
    for d in S.doors:
        if not here(d["hinge"][1]):
            continue
        w = d["props"]["width"]
        h0 = P(d["hinge"][0], d["hinge"][2])
        h1 = P(d["hinge"][0] + w * math.cos(d["yaw"]), d["hinge"][2] - w * math.sin(d["yaw"]))
        dr.line((h0, h1), fill=ORANGE, width=7)
    for p in S.parts:
        px, pz = P(p["pivot"][0], p["pivot"][2])
        dr.ellipse((px - 5, pz - 5, px + 5, pz + 5), outline=MAGENTA, width=3)
    for e in S.empties:
        n, (x, y, z) = e["name"], e["pos"]
        if not here(y) or not inside(x, z):
            continue
        px, pz = P(x, z)
        if n.startswith("Link_"):
            dr.ellipse((px - 9, pz - 9, px + 9, pz + 9), fill=BLUE, outline=(255, 255, 255), width=2)
        elif n.startswith("Arrive_"):
            fx, fz = e["face"]
            ln = math.hypot(fx, fz) or 1
            fx, fz = fx / ln, fz / ln
            dr.line((px, pz, px + fx * 26, pz + fz * 26), fill=BLUE, width=3)
            dr.ellipse((px - 4, pz - 4, px + 4, pz + 4), fill=BLUE)
            text(dr, (px + fx * 58, pz + fz * 58), n[7:], f_link, BLUE)
        elif n.startswith("Spot_"):
            kind = n.split("_")[1]
            col = SPOT_COL.get(kind, MAGENTA)
            dr.rectangle((px - 7, pz - 7, px + 7, pz + 7), fill=col, outline=(255, 255, 255), width=2)
            if kind == "shop":
                lab = f"shop {n.split('_')[-1]} ({e['props'].get('stock', '')})"
            elif kind == "minigame":
                lab = "mini-game"
            elif kind == "groundskeeper":
                lab = f"groundskeeper ({e['props'].get('mood', '')})"
            elif kind == "toy":
                lab = ""
            else:
                lab = n[5:]
            if lab:
                text(dr, (px, pz - 19), lab, f_spot, col, halo=2)
        elif n.startswith("Marker_") and e["props"].get("kind") in ("Spawn", "Entrance"):
            dr.polygon([(px, pz - 14), (px + 12, pz + 9), (px - 12, pz + 9)], fill=GREEN, outline=(255, 255, 255))
            text(dr, (px + 30, pz + 20), e["props"]["kind"].lower(), f_spot, GREEN, halo=2)
    for lb in S.labels:
        if not here(lb["y"]) or not inside(lb["x"], lb["z"]):
            continue
        f = f_room if lb["kind"] == "room" else f_note
        text(dr, P(lb["x"], lb["z"]), lb["text"], f, INK if lb["kind"] == "room" else GREY)
    # scale bar and north
    span = pv["x1"] - pv["x0"]
    bar = 1 if span < 10 else 2 if span < 18 else 5 if span < 45 else 10 if span < 120 else 20
    bx, by = 24, pv["H"] - 30
    n_seg = 4 if bar < 5 else 2
    if S.segments:
        bar, n_seg = 5, 2
    for i in range(n_seg):
        x0 = bx + i * bar * sx
        dr.rectangle((x0, by - 10, x0 + bar * sx, by), fill=INK if i % 2 == 0 else (255, 255, 255), outline=INK, width=2)
    text(dr, (bx + n_seg * bar * sx / 2, by - 26), f"{n_seg * bar} m", font(20, True), INK, halo=3)
    nx, ny = pv["W"] - 40, 50
    dr.polygon([(nx, ny - 26), (nx + 13, ny + 8), (nx - 13, ny + 8)], fill=INK)
    text(dr, (nx, ny + 28), "N", font(22, True), INK)
    if title:
        text(dr, (pv["W"] / 2, 30), title, font(24 if S.segments else 30, True), INK)
    return im


def seg_title(S, k, pv):
    a, b = -pv["z1"], -pv["z0"]
    return f"{max(0, a):.0f} to {min(G.ROAD_L, b):.0f} m"


def plan_sheet(S, renders, out):
    views = G.plan_views(S)
    titles = []
    for k, pv in enumerate(views):
        if S.segments:
            titles.append(seg_title(S, k, pv))
        elif len(S.levels) > 1:
            titles.append(S.level_names.get(pv["level"], f"y {pv['level']:g}"))
        else:
            titles.append(None)
    panels = [plan_panel(S, pv, renders / f"{S.id}_plan_{pv['key']}.png", t) for pv, t in zip(views, titles)]
    if len(panels) == 1:
        body = panels[0]
    else:
        w = sum(p.width for p in panels) + 12 * (len(panels) - 1)
        h = max(p.height for p in panels)
        body = Image.new("RGB", (w, h), (255, 255, 255))
        x = 0
        for p in panels:
            body.paste(p, (x, 0))
            x += p.width + 12
        if body.width > 2400:
            body = body.resize((body.width * 3 // 4, body.height * 3 // 4), Image.LANCZOS)
    side = 640
    rows = [f"{door}  ->  {to}" for door, to in S.links.items()]
    spots = {}
    for e in S.empties:
        if e["name"].startswith("Spot_"):
            k = e["name"].split("_")[1]
            spots[k] = spots.get(k, 0) + 1
    parts = [f"{p['name']}: {p['props']['motion']} about {p['props']['axis']}, +/-{p['props']['range_deg']:g} deg" for p in S.parts]
    head = 96
    H = max(body.height + head, head + 60 + 26 * (2 * len(rows) + 2 * len(parts) + len(spots) + 26))
    im = Image.new("RGB", (body.width + side, H), (255, 255, 255))
    im.paste(body, (0, head))
    dr = ImageDraw.Draw(im)
    text(dr, (16, 30), f"{S.id}  -  {S.title}", font(30, True), INK, anchor="lm", halo=0)
    text(dr, (16, 70), f"{S.size}.  Top-down, orthographic; roofs, crowns and anything 2.4 m above the floor are left out.", font(18), GREY,
         anchor="lm", halo=0)
    x, y = body.width + 18, head + 10
    f, fb = font(19), font(21, True)

    def line(s, ff=f, col=INK):
        nonlocal y
        for part in textwrap.wrap(s, 54) or [""]:
            dr.text((x, y), part, font=ff, fill=col)
            y += 26
    if S.attach:
        sc, (ox, oy, oz), yaw = S.attach
        line("A SET THAT STAYS PART OF THE LOT", fb)
        line(f"Its origin goes at {sc}'s ({ox:g}, {oy:g}, {oz:g}), yaw {yaw:g}. The lot round it (grey, ctx_) is for the picture only.", f, GREY)
        y += 8
    line("LINKS (press F at the blue dot)", fb)
    for r in rows or ["none: the spawn marker is the way in"]:
        line(r, f, BLUE)
    y += 10
    if spots:
        line("SPOTS (the page places these)", fb)
        line(", ".join(f"{k} x{v}" for k, v in sorted(spots.items())), f, MAGENTA)
        y += 6
    if parts:
        line("MOVING PARTS (origin = pivot, magenta ring)", fb)
        for p in parts:
            line(p, f, MAGENTA)
        y += 6
    line("KEY", fb)
    line("orange bar: door leaf (from its hinge)", f, ORANGE)
    line("blue dot: Link_ (press F, or walk through the gap); blue tick: Arrive_ and the way you face", f, BLUE)
    line("square: Spot_; green triangle: Marker_ Spawn", f, MAGENTA)
    if S.clear:
        line("dashed grey: a piece's clear ground", f, GREY)
    if S.id == "endless_hills":
        line("dark green dots: contours every 0.5 m; the tile's lowest dip is by the centre, its highest tops in the corners", f, GREEN)
    im.save(out / f"{S.id}_plan.jpg", quality=88, optimize=True)        # no comment or APP1 segment


def still(S, renders, out):
    im = Image.open(renders / f"{S.id}_still.png").convert("RGB")
    dr = ImageDraw.Draw(im)
    (pos, face, pitch) = S.still
    text(dr, (20, im.height - 28), f"{S.id}: eye height {G.EYE} m, from ({pos[0]:g}, {pos[2]:g})", font(26, True), INK, anchor="lm")
    im.save(out / f"{S.id}_still.jpg", quality=86, optimize=True)


# ---------------------------------------------------------------- the overview: the hub round the lot (left), the skies (right)
HUB = {  # scene: (x, y) centre on the left panel
    "tree_house": (170, 600), "playground": (520, 600), "parking_lot": (1000, 600), "market": (1480, 600),
    "street": (560, 200), "bus_station": (890, 680), "table_and_chairs": (1110, 680), "store": (1000, 200),
    "road": (810, 940), "forest": (810, 1180), "endless_hills": (1190, 940), "addon": (170, 260),
}
CONN_COL = {"walk": (20, 150, 60), "bus": (215, 110, 20), "gate": (130, 60, 200), "doors": (60, 60, 70), "set": (110, 110, 115)}


def overview(out, sizes):
    W, H = 2640, 1460
    im = Image.new("RGB", (W, H), (250, 250, 248))
    dr = ImageDraw.Draw(im)
    dims = {"parking_lot": (460, 300), "street": (300, 96), "forest": (300, 96), "store": (360, 96), "addon": (300, 96),
            "bus_station": (200, 84), "table_and_chairs": (200, 84)}

    def boxof(sid):
        x, y = HUB[sid]
        w, h = dims.get(sid, (300, 110))
        return x - w / 2, y - h / 2, x + w / 2, y + h / 2

    def edge_pt(sid, toward):
        x0, y0, x1, y1 = boxof(sid)
        ox, oy = HUB[toward]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        dx, dy = ox - cx, oy - cy
        if abs(dx) * (y1 - y0) > abs(dy) * (x1 - x0):
            return (x1 if dx > 0 else x0), cy
        return cx, (y1 if dy > 0 else y0)

    def conn(a, b, kind, lab=None, two_way=True):
        p, q = edge_pt(a, b), edge_pt(b, a)
        dr.line((p, q), fill=CONN_COL[kind], width=6)
        if lab:
            text(dr, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2 + 30), lab, font(16, True), CONN_COL[kind], halo=3)
    conn("tree_house", "playground", "walk", "walk")
    conn("playground", "parking_lot", "walk", "walk:\nwest edge")
    conn("parking_lot", "market", "walk", "walk:\neast edge")
    conn("tree_house", "addon", "gate", "trunk door, locked")
    conn("road", "forest", "walk", "walk: (0, 0, 6) facing north")
    # the road and the hills leave by the lot's south hedge; the bus rides to the street; the store is part 1's
    for sid, lab in (("road", "the old signpost (x -30)"), ("endless_hills", "a stile (x 30)")):
        p, q = edge_pt("parking_lot", sid), edge_pt(sid, "parking_lot")
        p = (HUB[sid][0], boxof("parking_lot")[3])
        dr.line((p, (p[0], boxof(sid)[1])), fill=CONN_COL["walk"], width=6)
        text(dr, (p[0], p[1] + 40), "walk: " + lab, font(17, True), CONN_COL["walk"], halo=3)
    bx0, by0, bx1, by1 = boxof("bus_station")
    sx0, sy0, sx1, sy1 = boxof("street")
    dr.line(((bx0 + 24, by0), (bx0 + 24, 330), (HUB["street"][0], 330), (HUB["street"][0], sy1)), fill=CONN_COL["bus"], width=6, joint="curve")
    text(dr, (640, 310), "bus: just a ride", font(17, True), CONN_COL["bus"], halo=3)
    tx0, ty0, tx1, ty1 = boxof("table_and_chairs")
    st0, sty0, st1, sty1 = boxof("store")
    dr.line(((HUB["store"][0], sty1), (HUB["store"][0], boxof("parking_lot")[1])), fill=CONN_COL["doors"], width=6)
    text(dr, (HUB["store"][0] + 120, 280), "glass doors: options", font(17, True), CONN_COL["doors"], halo=3)
    for sid in HUB:
        x0, y0, x1, y1 = boxof(sid)
        mine = sid in G.SCENES
        fill = (255, 255, 255) if mine else (225, 232, 240)
        dr.rounded_rectangle((x0, y0, x1, y1), 14, fill=fill, outline=INK, width=4 if mine else 2)
        name = {"store": "Look Over There (the store)", "addon": "tree house addon", "forest": "forest (built)", "street": "street (city, built)"}.get(sid, sid)
        if sid == "parking_lot":
            text(dr, (HUB[sid][0], y0 + 30), "parking_lot (part 1, built)", font(26, True), INK, halo=0)
            text(dr, (HUB[sid][0], y0 + 64), "124 x 70 m of asphalt, floor y 9.6", font(18), GREY, halo=0)
            continue
        text(dr, (HUB[sid][0], y0 + 26), name, font(22 if mine else 20, True), INK, halo=0)
        sub = sizes.get(sid) or {"store": "part 1: the Original, Going back in", "addon": "reserved, not built", "forest": "dreamcore_forest",
                                 "street": "Hallam Row"}.get(sid, "")
        for i, part in enumerate(textwrap.wrap(sub, 30)[:3]):
            text(dr, (HUB[sid][0], y0 + 56 + 22 * i), part, font(16), GREY, halo=0)
    # the two sets drawn inside the lot
    for sid in ("bus_station", "table_and_chairs"):
        x0, y0, x1, y1 = boxof(sid)
        dashed_rect(dr, x0 - 6, y0 - 6, x1 + 6, y1 + 6, CONN_COL["set"], w=2)
    text(dr, (60, 50), "The Overworld round the parking lot. North up. Grey: part 1's, built; white: this greybox.", font(24, True), INK, anchor="lm", halo=0)
    lines = ["Lines: green walk (a gap in a hedge, F or walk through), orange the bus, purple a gate, grey a door.",
             "table_and_chairs and bus_station are sets that stay part of the lot (dashed); every other scene is its own file, floor y 0.",
             f"West to east (tree house, playground, lot, market) is about {sizes['_cross_m']:.0f} m: {sizes['_cross_s'] / 60:.1f} minutes at walking pace; "
             f"the road adds {G.ROAD_L:.0f} m ({G.ROAD_L / WALK_MPS / 60:.0f} minutes)."]
    for i, s in enumerate(lines):
        text(dr, (60, 1300 + 34 * i), s, font(20), GREY, anchor="lm", halo=0)
    # the skies
    lx = 2160
    dr.line(((1720, 40), (1720, 1420)), fill=(200, 200, 200), width=2)
    text(dr, (lx, 50), "Four skies: R3 backdrops, defaults the owner can replace", font(24, True), INK, halo=0)
    sky_cols = {"clear_day": ((110, 170, 240), (200, 228, 255)), "sunset": ((250, 140, 90), (120, 80, 160)), "night": ((10, 14, 40), (40, 50, 100)),
                "painted": ((140, 200, 245), (255, 220, 240))}
    y = 120
    for key, title, what in SKIES:
        top, bot = sky_cols[key]
        for k in range(160):
            t = k / 159
            c = tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3))
            dr.line(((lx - 400, y + k), (lx + 400, y + k)), fill=c)
        if key == "night":
            for sx, sy in ((lx - 300, y + 30), (lx - 120, y + 70), (lx + 60, y + 25), (lx + 250, y + 90), (lx + 330, y + 40), (lx - 220, y + 120)):
                dr.ellipse((sx - 3, sy - 3, sx + 3, sy + 3), fill=(255, 255, 240))
        if key == "painted":
            for cx0, cy0 in ((lx - 250, y + 60), (lx + 120, y + 40), (lx + 280, y + 100)):
                dr.ellipse((cx0 - 70, cy0 - 22, cx0 + 70, cy0 + 22), fill=(255, 255, 255))
        dr.rectangle((lx - 400, y, lx + 400, y + 160), outline=INK, width=2)
        text(dr, (lx, y + 52), title, font(26, True), (255, 255, 255) if key == "night" else INK, halo=0 if key == "night" else 2)
        text(dr, (lx, y + 92), f"world/backdrops/overworld_{key}.webp", font(18), (230, 230, 230) if key == "night" else INK, halo=0 if key == "night" else 2)
        for i, part in enumerate(textwrap.wrap(what, 70)):
            text(dr, (lx, y + 182 + 24 * i), part, font(17), GREY, halo=0)
        y += 300
    text(dr, (lx, 1360), "Every Overworld scene and both sets use the same four.", font(18), GREY, halo=0)
    im.save(out / "overview.png", optimize=True)
    return im


SKIES = [
    ("clear_day", "Clear day", "docs/WORLD.md's 'clear with no clouds': the v0 lot's sky; the default for a first visit."),
    ("sunset", "Sunset", "docs/WORLD.md's 'sunrise and sunset': one warm low sun, rendered for the evening and reused for the morning."),
    ("night", "Night", "docs/WORLD.md's 'a bright starry night'."),
    ("painted", "Painted", "docs/BLENDER_AREAS.md's default; taken as WORLD.md's 'drifting anime clouds', painted, as the sky halls are."),
]

SHORT = {"table_and_chairs": "a set in the lot, 3.2 x 3.2 m", "bus_station": "a set in the lot, 14 x 4 m",
         "market": "64 x 44 m, 5 stalls + buy-back", "playground": "100 x 76 m, 8 pieces", "tree_house": "44 x 44 m, house at y 4",
         "road": f"{G.ROAD_L:.0f} x 24 m", "endless_hills": "a 200 x 200 m tile that repeats"}


# ---------------------------------------------------------------- the README
DEFAULTS = [
    ("table_and_chairs", "the spawn: a table and chairs facing the store; it can stay part of the lot; its own collection",
     "Kept as a set that stays part of the lot: its own collection and file (world/table_and_chairs.json) in its own frame, the table's centre at "
     "the origin. It attaches at parking_lot's (-8, 9.6, 41), yaw 0, where index.html draws the table today (OW_TABLE), and copies that table: "
     "a 0.85 m round top on one leg, four chairs 1.35 m out (pink, mint, yellow, blue), their backs away from the table. Marker_Spawn is 2.6 m "
     "south of the table, so lot.L4.front_doors>overworld still arrives at (-8, 9.6, 43.6) facing the store. The page can drop its drawn table "
     "for this set's GLB."),
    ("market", "[DEFAULT id] stalls for weapons, gear, food, keycards and cosmetics; Spot_shop per stall",
     "Kept the id. 64 m by 44 m inside a hedge, paved: five stalls 8 m wide (weapons, gear, food on the north side; keycards and cosmetics on "
     "the south), each with a back wall and shelves, a counter, a striped awning and a sign, and its Spot_shop_<n> behind the counter facing "
     "out (with `stock`). A sixth counter, the buy-back kiosk in the middle (Spot_shop_6, stock buy-back): docs/WORLD.md says the Market is "
     "also where lost ammo, consumables and perks are bought back. Four picnic tables, six lamps, three facades on the east side. Reached "
     "through a 6 m gap in its west hedge from the lot's east edge."),
    ("playground", "swing, slide, seesaw, merry-go-round, monkey bars, sandbox, spring riders, climbing frame; clear ground round each; moving "
     "parts Play_<equipment>_<part> with their pivots",
     "Built: 100 m by 76 m of grass inside a hedge, a path down the middle, four pieces either side, each on a 24 m plot with its clear ground "
     "(the dashed rect: the piece and 2 m to 2.5 m round it) on a rubber pad. Moving parts, 10 objects: Play_swing_seat1 and seat2 (pendulum "
     "about x, pivot on the top bar at 2.4 m), Play_seesaw_plank (tilt about z, pivot on the fulcrum at 0.6 m), Play_merry_go_round_deck (spin "
     "about y), Play_spring_riders_rider1 to rider3 (rock, pivot at the spring's foot), Play_sandbox_digger_seat (spin about y) and "
     "Play_sandbox_digger_arm (tilt about x, its `parent` the seat), Play_climbing_frame_wheel (spin about z). Each is one object whose origin "
     "is its pivot, with custom properties equipment, part, axis, motion, range_deg and pivot; the moving parts have no collider (the page "
     "moves them). The slide and the monkey bars have no moving part. Spot_minigame_<equipment> per piece lists its parts and pays money."),
    ("tree_house", "a puzzle and an entrance to its own addon later (overworld.treehouse>addon)",
     "Built: a 44 m glade in a wild hedge round one big tree. A platform at y 4 round the trunk, up 16 steps of 0.25 m; on it a house 6.5 m by "
     "8 m with the trunk through it, and a porch. The puzzle (Spot_puzzle_1) is a carved board on the house's west wall. The addon's entrance "
     "is a small door in the trunk (DoorLeaf_addon, 0.94 m by 1.6 m, closed, `locked`), and its link `addon` is off this set. Reached from the "
     "playground's west gap."),
    ("bus_station", "just a ride: a small station in place of the lot's shelter",
     "Kept as a set that stays part of the lot, like the table: its own collection and file, attached at parking_lot's (-46, 9.6, 46), yaw 0, "
     "over the shelter index.html draws at (-43.4, 46.4). A 14 m by 4 m platform 0.15 m up, a glass shelter with a bench (its back to the "
     "lot), a timetable, a ticket machine, a stop sign and a 3.5 m bus bay on the south side. The bus links keep their ids; only their lot-side "
     "points move to the station's Link_bus_stop and Arrive_bus_stop."),
    ("road", "the road to the forest, replacing the signpost walk (overworld.road>forest; you arrive in the forest at (0, 0, 6) facing north)",
     f"Built: {G.ROAD_L:.0f} m [DEFAULT] of straight road, 8 m of asphalt between grass verges and hedges, 24 m across, lamps every 40 m, three "
     "benches, two facades. Its frame runs north (-z), as the forest's path does: the lot's end at z 0, the forest's at z -480, behind a wall "
     "of pastel trees with a bright gap. You start on it from the lot's old signpost (shared/forest.js FOREST_ROAD_LOT, by the south hedge) "
     f"and walk {G.ROAD_L / WALK_MPS / 60:.0f} minutes to the forest."),
    ("endless_hills", "[DEFAULT] one ground tile of about 200 m by 200 m that repeats without a seam, with Spot_toy for the kickable toys "
     "and little puzzles",
     "Kept 200 m by 200 m. The ground is 2500 collision columns 4 m square (Ground_Hills_<i>_<j>) under one smooth surface on a 2 m grid "
     "(decor_Hills_Surface, the art); both come from one height function, a sum of cosines that repeats every 200 m and is even about the "
     "edges, so the heights and the slopes along opposite edges are the same and the tile repeats without a seam. Heights run 4.3 m from "
     "the lowest dip to the highest top; no two neighbouring columns differ by more than 0.26 m, across the seams too. No edge walls: the page "
     "repeats the tile and wraps your position. 12 Spot_toy (with `what`, physics kickable), 4 Spot_puzzle, a facade alone on a rise, and the "
     "way back: a signpost by the tile's centre, at the same place on every repeat, so it is never more than 140 m away."),
    ("Also", "hedges with Spot_groundskeeper; \"more to come\" facades that do not open",
     "11 Spot_groundskeeper on the hedges of the market, the playground, the tree house's glade and the road, each facing its hedge, with "
     "`mood` watches or ignores (docs/WORLD.md). 8 facades: three in the market, two in the playground, two along the road, one on the hills; "
     "each a front with a fake door, windows and a MORE TO COME sign, solid, and a Spot_facade_<n> in front where the page can swap in a "
     "real entrance."),
    ("Skies", "four sky backdrops (clear day, sunset, night, painted), defaults the owner can replace; R3 renders for the dressing step",
     "Listed, not rendered (R3, with dressing): world/backdrops/overworld_clear_day.webp, overworld_sunset.webp, overworld_night.webp and "
     "overworld_painted.webp, 4096 by 2048 equirectangular, north in the middle column, shared by every Overworld scene and both sets, and "
     "named in the area's manifest entry by the coordinator. The stills here use one plain greybox sky."),
]
CHOICES = [
    "Every scene is its own file with its own frame and its floor at y 0. table_and_chairs and bus_station are sets that stay part of the lot: "
    "their frames go into parking_lot's at the points in the attach table, and their `Ground_lot` colliders (no art) stand for the lot's "
    "asphalt under them, so each file also passes on its own.",
    "How the scenes join the lot. Every Overworld scene is open air, so each joins by a walk link (docs/WORLD.md's connectors: walk, as the "
    "forest's gap and the signpost walk are): a gap in a hedge, F there (or walking through it), and you arrive 2.6 m inside the other side, "
    "facing in. The playground off the lot's west edge, the market off its east edge, the road from the old signpost and the hills from a "
    "stile in its south hedge, the tree house off the playground's west end. The lot's sides are listed for the coordinator; the lot is not "
    "touched here.",
    "Link ids. Reused: overworld.bus>city and city.bus>overworld (the station's points), overworld.road>forest (the road's far end), "
    "overworld.treehouse>addon (the trunk door), overworld.lot>forest (its door forest_road now leads to the road's start, not the forest) and "
    "forest.road>lot (it now arrives at the road's forest end; the coordinator may rename it forest.road>road). New: overworld.lot>market, "
    "overworld.market>lot, overworld.lot>playground, overworld.playground>lot, overworld.playground>treehouse, overworld.treehouse>playground, "
    "overworld.lot>hills, overworld.hills>lot, overworld.lot>road and overworld.road>lot (or the reused overworld.lot>forest for the first of "
    "these).",
    "Ten minutes. The hub is meant to take about ten minutes to cross end to end. As built, west to east (the tree house, the playground, "
    "the lot's asphalt and the market) is about {cross:.0f} m, {crossmin:.1f} minutes at the walking pace of 4 m/s; the road is {road:.0f} m more "
    "({roadmin:.0f} minutes) and the hills never end. The lot's own grass already runs to 400 m either way, so the coordinator can stretch the "
    "walk by where the lot's gaps go. Open question 1.",
    "Spot kinds the table does not name: `minigame` (one per playground piece), `puzzle` (the sandbox's buried thing, the tree house's board, "
    "the hills' four), `facade`.",
    "Steps: the tree house's 16, the slide's ladder (6) and chute (7, so it can be walked up), the monkey bars' end steps (3 each) and the "
    "climbing frame's (6) are one box a step; the bus platform (0.15 m), the sandbox's boards (0.25 m) and the bases under the merry-go-round "
    "and the spring riders are kerbs, one step each.",
    "The moving parts have no collider; the page moves them and decides what you can stand on. The swing's frame, the seesaw's fulcrum, the "
    "merry-go-round's base, the riders' bases and the digger's post are solid.",
    "Light: one greybox set for the stills, a clear day. The four skies come with dressing (R3).",
]
QUESTIONS = [
    "Ten minutes end to end: as built, the tree house to the market is about {cross:.0f} m ({crossmin:.1f} minutes' walk), and the road "
    "{road:.0f} m more. Should the walk be longer: bigger scenes, a longer road, or the lot's gaps further out on its grass?",
    "The joins: the playground (and the tree house beyond it) west of the lot, the market east, the road and the hills through the lot's "
    "south hedge. Is that the map you want?",
    "The table and the bus station stay part of the lot as sets (no scene to load). Should the bus station be a scene of its own instead?",
    "The market has a sixth counter, a buy-back kiosk, for lost ammo, consumables and perks (docs/WORLD.md). Keep it, or fold it into the gear "
    "stall?",
    "The playground: eight pieces in two rows. The slide and the monkey bars have no moving parts; I added a digger in the sandbox and a "
    "ship's wheel on the climbing frame so those two have one. Right pieces, and the right mini-games?",
    "The endless hills: 4.3 m from dip to top, gentle because each 4 m column may rise at most 0.27 m from the next (2500 columns). Taller "
    "hills need smaller columns, so more of them. And the tile is mirror-symmetric, which is how its edges match. Is that all right?",
    "The skies: docs/WORLD.md lists clear with no clouds, drifting anime clouds, sunrise and sunset, and a starry night; the default four are "
    "clear day, sunset, night and painted. Is 'painted' the anime clouds, and is one render enough for sunrise and sunset?",
    f"The road: {G.ROAD_L:.0f} m and straight, running north like the forest's path. Longer, shorter, or with bends?",
    "Groundskeepers (11) and facades (8): enough, and in the right places?",
]


def readme(out, docs, nums):
    fmt = lambda s: s.format(**nums)
    L = ["# Overworld greybox (docs/BLENDER_AREAS.md, section 4: the Overworld)", "",
         "Plain grey boxes, to scale, for the Overworld beyond part 1's `parking_lot`: the spawn's table and chairs, the market, the "
         "playground, the tree house, the bus station, the road to the forest and the endless hills. There are no reference photos, so each "
         "scene is built from its written description. This is for review: no scene or link has been added to the manifest, and the "
         "greybox GLBs are in `glb/` here, not in `world/`.", "",
         "- Built by `tools/blender/build_overworld_greybox.py` (it follows the hotel's and the mall's greybox builds), which writes "
         "`world/<scene>.json` through `tools/blender/export_scene.py`, the GLB, the plans and the stills. The labels and these sheets come "
         "from `tools/blender/overworld_greybox_sheets.py`.",
         "- `python tools/blender/build_overworld_greybox.py --check .` runs the gates on the exported files: every link has its other side "
         "(the links that leave this set are listed), every scene is reached from the lot, every step and kerb rises at most 0.27 m with one "
         "box a step, every path, aisle and gap is at least 1.6 m wide and clear, each playground piece has its own clear ground, the "
         "playground's GLB has every Play_ part as its own node on its pivot, and the hills tile's opposite edges have the same heights.",
         "- `CHECKS.txt`: the gates, `node tools/worlddoc.mjs check` on every file (0 errors; the warnings say a scene or link is new to the "
         "manifest, or that an open-air scene is larger than an indoor one should be), `node --test shared/*.test.js`, and the privacy grep.",
         "- `overview.png`: how the scenes join the lot, the street and the forest, and the four skies. For each scene, `<scene>_plan.jpg` "
         "(top-down, scale bar, labels, doors, links, spots, clear ground and pivots) and `<scene>_still.jpg` (eye height, 1.55 m).", "",
         "## Scenes", "", "| Scene | Size | Links (door: where it goes) | Colliders, doors, spots | Mood |", "|---|---|---|---|---|"]
    for sid in G.SCENES:
        S = G.build(sid)
        d = docs.get(sid, {})
        spots = {}
        for sp in d.get("spots", []):
            spots[sp["kind"]] = spots.get(sp["kind"], 0) + 1
        sp = ", ".join(f"{k} x{v}" for k, v in sorted(spots.items())) or "none"
        links = "; ".join(f"`{k}`: {v}" for k, v in S.links.items()) or "none (Marker_Spawn)"
        extra = f"; moving parts: {len(S.parts)}" if S.parts else ""
        L.append(f"| `{sid}` | {S.size} | {links} | {len(d.get('colliders', []))} colliders, {len(d.get('doors', []))} doors; spots: {sp}{extra} | {S.mood} |")
    L += ["", "## The sets that stay part of the lot", "", "| Set | Attaches to | At (its origin) | Yaw | Its points in the lot's frame |", "|---|---|---|---|---|"]
    for sid, (sc, (x, y, z), yaw) in G.ATTACH.items():
        S = G.build(sid)
        pts = []
        for e in S.empties:
            if e["name"].startswith(("Marker_", "Link_", "Arrive_")):
                pts.append(f"{e['name']} ({x + e['pos'][0]:g}, {y + e['pos'][1]:g}, {z + e['pos'][2]:g})")
        L.append(f"| `{sid}` | `{sc}` | ({x:g}, {y:g}, {z:g}) | {yaw:g} | {'; '.join(pts)} |")
    L += ["", "Each set is its own collection (Art, Layout) in its own file; the coordinator places its GLB and its colliders at that point in "
          "the lot (add the point to every position, with no turn), drops the lot's `Ground_lot` stand-in, and removes what index.html draws "
          "there today (the table and chairs in overworldProps, the shelter at BUS_LOT.shelter).", ""]
    L += ["## Links", "",
          "Each pair is one link. Pressing F at one side's `Link_<door>` (or walking through a walk gap) puts you at the other side's "
          "`Arrive_<door>`, facing its -Y axis. Every pair has both sides built (the gate checks it).", "", "| From | To | Connector | Note |", "|---|---|---|---|"]
    for (a, da), (b, db), kind, note in G.PAIRS:
        L.append(f"| `{a}.{da}` | `{b}.{db}` | {kind} | {note} |")
    L += ["", "Links that leave this set (the coordinator wires the other side; parking_lot, street and forest are part 1's and are not touched "
          "here). Lot points are in parking_lot's frame (floor y 9.6):", "", "| Link | Connector | Ids | The other side |", "|---|---|---|---|"]
    for side in G.OUTSIDE:
        kind, ids, note = G.outside_note(side)
        L.append(f"| `{side[0]}.{side[1]}` | {kind} | {ids} | {note} |")
    L += ["", "## The defaults ([DEFAULT] and the table in docs/BLENDER_AREAS.md)", "", "| Scene | The plan says | Kept or built |", "|---|---|---|"]
    for s, dflt, k in DEFAULTS:
        L.append(f"| {s} | {dflt} | {k} |")
    L += ["", "Every [DEFAULT] here, in one list:", "",
          "- `market` as the scene id (the plan's [DEFAULT id]).",
          "- The hills tile: 200 m by 200 m (the plan's [DEFAULT]), 4 m collision columns, 4.3 m of height.",
          f"- The road's length: {G.ROAD_L:.0f} m, straight.",
          "- The four skies: clear day, sunset, night, painted (the plan's default), and their file names.",
          "- Every size: the market 64 m by 44 m, the playground 100 m by 76 m with 24 m plots, the tree house's glade 44 m and its platform "
          "at y 4, the bus station's 14 m platform.",
          "- Where each scene joins the lot (the gaps and the stile), and where the two sets attach.",
          "- The buy-back kiosk as a sixth Spot_shop.",
          "- The two extra moving parts: the sandbox's digger and the climbing frame's wheel.",
          "- The counts: 11 groundskeepers, 8 facades, 12 toys, 6 puzzles.", ""]
    L += ["## Skies (R3, for the dressing step)", "", "| Sky | File | What it is |", "|---|---|---|"]
    for key, title, what in SKIES:
        L.append(f"| {title} | `world/backdrops/overworld_{key}.webp` | {what} |")
    L += ["", "Each is a 4096 by 2048 equirectangular render, north (game -z) in the middle column, as docs/BLENDER.md's R3 asks. One set of four "
          "serves every Overworld scene and both sets; the coordinator names them in the area's manifest entry, and the page switches between "
          "them. They are defaults the owner can replace with his own pictures.", ""]
    L += ["Choices the table left open:", ""] + [f"- {fmt(c)}" for c in CHOICES]
    L += ["", "## Open questions for the owner", ""] + [f"{i}. {fmt(q)}" for i, q in enumerate(QUESTIONS, 1)]
    L += ["", "## Not done here", "",
          "- `parking_lot` is untouched (world/parking_lot.json, tools/make_parking_lot.mjs, index.html, shared/city.js, shared/forest.js): its "
          "hedge gap for the road, the stile for the hills, its east and west gaps, and the sets' placement are the coordinator's, at the points "
          "listed above. The parking-lot backdrop is draft PR #91's.",
          "- The forest is untouched: its signpost back still goes to the lot until the coordinator points forest.road>lot at the road.",
          "- Placeholders: the bus is not modelled (it is a ride); the trunk door stays locked; the facades do not open; the toys are spots, not "
          "objects.",
          "- The four skies are listed, not rendered (R3, with dressing). Light: one greybox set.",
          "- The manifest, `index.html`, `shared/` and the tests are untouched. `node tools/worlddoc.mjs check` warns that each scene and link is "
          "new; that is expected until the coordinator adds them.", ""]
    (out / "README.md").write_text("\n".join(L), encoding="utf-8")


def owner_sheet(path, out, renders, nums):
    W = 1080
    f_t, f_h, f_b = font(52, True), font(38, True), font(32)
    blocks = []

    def para(s, f, col=INK, wrap=48, gap=10):
        for p in textwrap.wrap(s, wrap):
            blocks.append(("t", p, f, col))
        blocks.append(("gap", gap))
    para("Overworld greybox: ready to look at", f_t, wrap=30)
    para("The table and chairs, the market, the playground, the tree house, the bus station, the road to the forest and the endless hills. "
         "Plain grey boxes to scale, all joined to the parking lot. Nothing is wired into the game yet.", f_b, GREY)
    blocks.append(("img", Image.open(out / "overview.png")))
    blocks.append(("gap", 20))
    para("What it looks like at eye height", f_h)
    grid = []
    for s in G.SCENES:
        im = Image.open(renders / f"{s}_still.png").convert("RGB")
        grid.append((s, im.resize((520, 292), Image.LANCZOS)))
    blocks.append(("grid", grid))
    blocks.append(("gap", 20))
    para("Questions for you", f_h)
    for i, q in enumerate(QUESTIONS, 1):
        para(f"{i}. {q.format(**nums)}", f_b, INK, wrap=50, gap=18)
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
            H += ((len(b[1]) + 1) // 2) * 342
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


def crossing():
    """West to east across the hub: the tree house's glade, the playground, the lot's asphalt, the market (each one's inside, end to end)."""
    lot = G.LOT["asphalt"][1] - G.LOT["asphalt"][0]
    m = 2 * G.TX + 2 * G.PX + lot + 2 * G.MX
    return m, m / WALK_MPS


def main(a):
    renders = Path(a[a.index("--renders") + 1])
    out = Path(a[a.index("--out") + 1]) if "--out" in a else G.ROOT / "docs/renders/overworld_greybox"
    out.mkdir(parents=True, exist_ok=True)
    docs = {}
    for sid in G.SCENES:
        f = G.out_path(renders, sid)
        if f.exists():
            docs[sid] = json.loads(f.read_text())
    cm, cs = crossing()
    nums = {"cross": cm, "crossmin": cs / 60, "road": G.ROAD_L, "roadmin": G.ROAD_L / WALK_MPS / 60}
    sizes = {"_cross_m": cm, "_cross_s": cs}
    for sid in G.SCENES:
        S = G.build(sid)
        sizes[sid] = SHORT.get(sid, S.size)
        if (renders / "renders" / f"{sid}_still.png").exists():
            plan_sheet(S, renders / "renders", out)
            still(S, renders / "renders", out)
    overview(out, sizes)
    readme(out, docs, nums)
    if "--owner" in a:
        owner_sheet(a[a.index("--owner") + 1], out, renders / "renders", nums)
    print("sheets written to", out)


if __name__ == "__main__":
    main(sys.argv[1:])
