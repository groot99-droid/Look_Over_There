"""The mall greybox's review sheets, drawn over the Blender renders of tools/blender/build_mall_greybox.py (no Blender here; Pillow only).
It follows tools/blender/hotel_greybox_sheets.py and grocery_greybox_sheets.py.

    python tools/blender/mall_greybox_sheets.py --renders <build out dir> [--out docs/renders/mall_greybox] [--owner <png>]

For every scene: <out>/<scene>_plan.jpg (the orthographic plan with its labels, doors, links, spots, a scale bar and north; a scene with two
levels has them side by side) and <out>/<scene>_still.jpg (the eye-height still). Then <out>/overview.png (how the scenes join entrance, and
the painted-sky loop) and <out>/README.md (every scene, its size, links and spots, the defaults, the open questions). --owner also writes a
one-page sheet for a phone. Labels come from the same model the build used, so they sit where the boxes are. Images are written fresh, with
no metadata.
"""
import json
import math
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_mall_greybox as G  # noqa: E402

FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/Library/Fonts")]


def font(size, bold=False):
    names = (["arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf", "Arial.ttf"])
    for d in FONT_DIRS:
        for n in names:
            if (d / n).exists():
                return ImageFont.truetype(str(d / n), size)
    return ImageFont.load_default()


INK, BLUE, ORANGE, MAGENTA, GREEN, GREY, RED = (25, 25, 30), (20, 90, 200), (215, 110, 20), (190, 30, 150), (20, 150, 60), (110, 110, 115), (200, 30, 30)
SPOT_COL = {"mannequin": (200, 40, 40), "puzzle": (130, 60, 200), "mirror": (20, 140, 160), "keycard": (190, 30, 150)}


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
    pv = G.plan_view(S, lv)
    im = Image.open(raw).convert("RGB").resize((pv["W"], pv["H"]))
    sx = pv["W"] / (pv["x1"] - pv["x0"])
    P = lambda x, z: ((x - pv["x0"]) * sx, (z - pv["z0"]) * sx)
    multi = len(S.levels) > 1
    here = lambda y: (lv - 0.6 <= y < lv + 2.4) if multi else True
    dr = ImageDraw.Draw(im)
    f_room, f_link, f_spot, f_note = font(30, True), font(19, True), font(15), font(18)
    for o in S.outlines:
        a, b = P(o["x0"], o["z0"]), P(o["x1"], o["z1"])
        dashed_rect(dr, min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]), GREY, w=3)
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
            ln = math.hypot(fx, fz) or 1
            fx, fz = fx / ln, fz / ln
            dr.line((px, pz, px + fx * 26, pz + fz * 26), fill=BLUE, width=3)
            dr.ellipse((px - 4, pz - 4, px + 4, pz + 4), fill=BLUE)
            text(dr, (px + fx * 58, pz + fz * 58), n[7:], f_link, BLUE)
        elif n.startswith("Spot_"):
            kind = n.split("_")[1]
            col = SPOT_COL.get(kind, MAGENTA)
            dr.rectangle((px - 7, pz - 7, px + 7, pz + 7), fill=col, outline=(255, 255, 255), width=2)
            lab = n[5:] if kind != "mannequin" else f"mannequin {n.split('_')[-1]} ({e['props'].get('role', '')})"
            text(dr, (px, pz - 19), lab, f_spot, col, halo=2)
        elif n.startswith("Marker_") and e["props"].get("kind") in ("Spawn", "Entrance"):
            dr.polygon([(px, pz - 14), (px + 12, pz + 9), (px - 12, pz + 9)], fill=GREEN, outline=(255, 255, 255))
            text(dr, (px + 30, pz + 20), e["props"]["kind"].lower(), f_spot, GREEN, halo=2)
    for lb in S.labels:
        if not here(lb["y"]):
            continue
        f = f_room if lb["kind"] == "room" else f_note
        text(dr, P(lb["x"], lb["z"]), lb["text"], f, INK if lb["kind"] == "room" else GREY)
    # scale bar and north
    span = pv["x1"] - pv["x0"]
    bar = 1 if span < 10 else 2 if span < 18 else 5 if span < 45 else 10
    bx, by = 24, pv["H"] - 30
    n_seg = 4 if bar < 5 else 2
    for i in range(n_seg):
        x0 = bx + i * bar * sx
        dr.rectangle((x0, by - 10, x0 + bar * sx, by), fill=INK if i % 2 == 0 else (255, 255, 255), outline=INK, width=2)
    text(dr, (bx + n_seg * bar * sx / 2, by - 26), f"{n_seg * bar} m", font(20, True), INK, halo=3)
    nx, ny = pv["W"] - 40, 50
    dr.polygon([(nx, ny - 26), (nx + 13, ny + 8), (nx - 13, ny + 8)], fill=INK)
    text(dr, (nx, ny + 28), "N", font(22, True), INK)
    if multi:
        text(dr, (pv["W"] / 2, 30), S.level_names.get(lv, f"y {lv:g}"), font(30, True), INK)
    return im


def plan_sheet(S, renders, out):
    panels = [plan_panel(S, lv, renders / f"{S.id}_plan_L{int(lv)}.png") for lv in S.levels]
    if len(panels) == 1:
        body = panels[0]
    else:
        w, h = panels[0].size
        body = Image.new("RGB", (w * len(panels), h), (255, 255, 255))
        for i, p in enumerate(panels):
            body.paste(p, (i * w, 0))
        body = body.resize((body.width * 3 // 4, body.height * 3 // 4), Image.LANCZOS)
    side = 620
    rows = [f"{door}  ->  {to}" for door, to in S.links.items()]
    spots, mann = {}, []
    for e in S.empties:
        if e["name"].startswith("Spot_"):
            k = e["name"].split("_")[1]
            spots[k] = spots.get(k, 0) + 1
            if k == "mannequin":
                mann.append(f"{e['name'].split('_')[-1]}. {e['props']['role']}: {e['props']['what']}")
    head = 96
    H = max(body.height + head, head + 60 + 26 * (2 * len(rows) + 2 * len(mann) + len(spots) + 20))
    im = Image.new("RGB", (body.width + side, H), (255, 255, 255))
    im.paste(body, (0, head))
    dr = ImageDraw.Draw(im)
    text(dr, (16, 30), f"{S.id}  -  {S.title}", font(32, True), INK, anchor="lm", halo=0)
    text(dr, (16, 70), f"{S.size}.  Top-down, orthographic; ceilings and anything 2.4 m above the floor are left out.", font(19), GREY, anchor="lm", halo=0)
    x, y = body.width + 18, head + 10
    f, fb = font(19), font(21, True)

    def line(s, ff=f, col=INK):
        nonlocal y
        for part in textwrap.wrap(s, 52) or [""]:
            dr.text((x, y), part, font=ff, fill=col)
            y += 26
    line("LINKS (press F at the blue dot)", fb)
    for r in rows:
        line(r, f, BLUE)
    y += 10
    if spots:
        line("SPOTS (the page places these)", fb)
        line(", ".join(f"{k} x{v}" for k, v in sorted(spots.items())), f, MAGENTA)
        y += 6
    if mann:
        line("MANNEQUINS (role: how it stands)", fb)
        for m in mann:
            line(m, f, RED)
        y += 6
    if S.turn_deg:
        line(f"Built along x with the atrium at the west end, then turned {S.turn_deg:g} degrees so north is the mall's north.", f, GREY)
        y += 6
    line("KEY", fb)
    line("orange bar: door leaf (from its hinge)", f, ORANGE)
    line("blue dot: Link_ (press F); blue tick: Arrive_ and the way you face", f, BLUE)
    line("square: Spot_; green triangle: Marker_ Spawn or Entrance", f, MAGENTA)
    line("dashed grey: a scaffold run", f, GREY)
    im.save(out / f"{S.id}_plan.jpg", quality=88, optimize=True)        # no comment or APP1 segment


def still(S, renders, out):
    im = Image.open(renders / f"{S.id}_still.png").convert("RGB")
    dr = ImageDraw.Draw(im)
    (pos, face, pitch) = S.still
    text(dr, (20, im.height - 28), f"{S.id}: eye height {G.EYE} m, from ({pos[0]:g}, {pos[2]:g})", font(26, True), INK, anchor="lm")
    im.save(out / f"{S.id}_still.jpg", quality=86, optimize=True)


# ---------------------------------------------------------------- the overview: the mall round the atrium (left), the painted-sky loop (right)
MALL = {  # scene: (x, y) centre on the left panel
    "construction": (825, 190), "bookstore_desk": (440, 220), "scene_2909": (1220, 300),
    "bookstore": (440, 440), "wing_books": (825, 440), "scene_2991": (1250, 560),
    "cinema_lobby": (160, 780), "wing_cinema": (480, 780), "entrance": (825, 780), "wing_entertainment": (1170, 780), "food_court": (1480, 780),
    "mirror_bathroom": (330, 1020), "scene_3012": (630, 1020), "scene_3008": (1170, 1020),
}
LOOP = [("scene_2909", None), ("sky_hall_01", "sky_hall"), ("scene_3012", "sky_hall"), ("sky_hall_02", "sky_hall"), ("scene_3008", "sky_hall"),
        ("sky_hall_03", "sky_hall"), ("mirror_bathroom", "mirror"), ("construction", None), ("sky_hall_04", "sky_hall"), ("scene_2991", "sky_hall")]
CONN_COL = {"doors": (60, 60, 70), "service": (190, 30, 150), "sky_hall": (20, 120, 210), "mirror": (20, 160, 150), "entrance": (60, 60, 70)}
OFF = {"scene_2909": "off wing_books", "scene_3012": "off wing_cinema", "scene_3008": "off wing_entertainment", "mirror_bathroom": "off wing_cinema",
       "construction": "off wing_books", "scene_2991": "off wing_entertainment"}


def overview(out, sizes):
    W, H = 2640, 1460
    im = Image.new("RGB", (W, H), (250, 250, 248))
    dr = ImageDraw.Draw(im)
    bw, bh = 270, 84

    def boxof(sid, pos):
        x, y = pos
        w = 300 if sid == "entrance" else bw
        h = 130 if sid == "entrance" else bh
        return x - w / 2, y - h / 2, x + w / 2, y + h / 2

    def anchor(a, b):
        x0, y0, x1, y1 = boxof(a, MALL[a])
        ox, oy = MALL[b]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        dx, dy = ox - cx, oy - cy
        if abs(dx) * (y1 - y0) > abs(dy) * (x1 - x0):
            return (x1 if dx > 0 else x0), cy
        return cx, (y1 if dy > 0 else y0)
    # the service corridor: a bar under the mall, a line up to each door it has
    sy = 1200
    dr.rounded_rectangle((60, sy - 30, 1560, sy + 30), 12, fill=(255, 240, 250), outline=CONN_COL["service"], width=4)
    text(dr, (810, sy), "service_corridor: " + sizes["service_corridor"], font(24, True), CONN_COL["service"], halo=0)
    for sid, xr in (("wing_cinema", 480), ("wing_books", 1000), ("wing_entertainment", 1280), ("food_court", 1480)):
        x0, y0, x1, y1 = boxof(sid, MALL[sid])
        if sid == "wing_books":
            dr.line(((x1, (y0 + y1) / 2), (xr, (y0 + y1) / 2), (xr, sy - 30)), fill=CONN_COL["service"], width=4, joint="curve")
        elif sid == "wing_entertainment":
            dr.line(((xr, y1), (xr, sy - 30)), fill=CONN_COL["service"], width=4)
        else:
            dr.line(((xr, y1), (xr, sy - 30)), fill=CONN_COL["service"], width=4)
    dr.line(((1560, sy), (1600, sy)), fill=CONN_COL["service"], width=4)
    text(dr, (1600, sy + 60), "hidden network\n(freight lift,\nkeycard_tier_1)", font(19, True), CONN_COL["service"], halo=0)
    # the doors between the mall's scenes (the sky halls are drawn on the right)
    for (a, da), (b, db), kind, note in G.PAIRS:
        if kind != "doors":
            continue
        p, q = anchor(a, b), anchor(b, a)
        dr.line((p, q), fill=CONN_COL["doors"], width=5)
    for sid in ("wing_books", "wing_cinema", "wing_entertainment"):
        p, q = anchor("entrance", sid), anchor(sid, "entrance")
        dr.line((p, q), fill=CONN_COL["doors"], width=7)
    # food_court to the atrium's FOOD COURT shopfront: over the entertainment wing
    fx0, fy0, fx1, fy1 = boxof("food_court", MALL["food_court"])
    ex0, ey0, ex1, ey1 = boxof("entrance", MALL["entrance"])
    dr.line(((MALL["food_court"][0], fy0), (MALL["food_court"][0], 680), (905, 680), (905, ey0)), fill=CONN_COL["doors"], width=5, joint="curve")
    text(dr, (1360, 700), "the atrium's FOOD COURT shopfront", font(18, True), CONN_COL["doors"], halo=0)
    for sid, (x, y) in MALL.items():
        x0, y0, x1, y1 = boxof(sid, (x, y))
        mine = sid in G.SCENES
        dr.rounded_rectangle((x0, y0, x1, y1), 14, fill=(255, 255, 255) if mine else (225, 232, 240), outline=INK, width=4 if mine else 2)
        text(dr, (x, y0 + 26), sid, font(24, True), INK, halo=0)
        text(dr, (x, y0 + 60), sizes.get(sid, "part 1 (the atrium, built)"), font(17), GREY, halo=0)
    text(dr, (MALL["entrance"][0], MALL["entrance"][1] + 40), "front door: the street", font(17), GREY, halo=0)
    text(dr, (60, 50), "The mall round the atrium (part 1's entrance, grey). North up; each wing runs out from its side of the atrium.",
         font(24, True), INK, anchor="lm", halo=0)
    text(dr, (60, 1300), "Lines: dark grey doors, pink the service corridor's staff doors. Every scene is its own file with its floor at y 0.",
         font(20), GREY, anchor="lm", halo=0)
    text(dr, (60, 1334), "Photo names (IMG_2909, 3012, 2991 + 3014, 3008 + 3010) are labels only: there are no photos.", font(20), GREY, anchor="lm", halo=0)
    # the painted-sky loop
    lx = 2160
    dr.line(((1720, 40), (1720, 1420)), fill=(200, 200, 200), width=2)
    text(dr, (2160, 50), "The painted-sky loop: the kit's sky halls", font(24, True), INK, halo=0)
    ys = [150, 260, 370, 480, 590, 700, 810, 1000, 1110, 1220]
    for i, ((sid, kind), y) in enumerate(zip(LOOP, ys)):
        if kind and i:
            col = CONN_COL[kind]
            dr.line(((lx, ys[i - 1] + 34), (lx, y - 34)), fill=col, width=6)
            if kind == "mirror":
                text(dr, (lx + 150, (ys[i - 1] + y) / 2), f"out through Mirror_{G.PORTAL_MIRROR}", font(18, True), col, halo=0)
        sky = sid.startswith("sky_hall")
        w = 230 if sky else 300
        dr.rounded_rectangle((lx - w / 2, y - 34, lx + w / 2, y + 34), 12, fill=(225, 238, 252) if sky else (255, 255, 255),
                             outline=CONN_COL["sky_hall"] if sky else INK, width=3)
        text(dr, (lx, y - 8), sid, font(22, True), INK, halo=0)
        text(dr, (lx, y + 18), "10 x 2.4 m, the kit's" if sky else sizes.get(sid, ""), font(15), GREY, halo=0)
        if sid in OFF:
            text(dr, (lx - 175, y), OFF[sid], font(16), GREY, anchor="rm", halo=0)
    text(dr, (lx, 1320), "Each sky hall: entry door at one end, EXIT door at the other.\nThe kit piece drops in at (0, 0, 0), yaw 0.",
         font(18), GREY, halo=0)
    im.save(out / "overview.png", optimize=True)
    return im


SHORT = {"wing_books": "40 x 14 m, runs north", "wing_cinema": "40 x 14 m, runs west", "wing_entertainment": "40 x 14 m, runs east",
         "bookstore": "20 x 16 m", "bookstore_desk": "12 x 8 m", "cinema_lobby": "24 x 16 m, balcony at 3 m", "food_court": "30 x 24 m",
         "construction": "24 x 18 m, deck at 3 m", "service_corridor": "46 x 2 m, 3 m high, a 10 m spur to the freight lift",
         "scene_2909": "the sky court, 24 x 24 m", "scene_3012": "the painted-sky street, 32 x 12 m", "scene_2991": "soft play + carousel, 32 x 14 m",
         "scene_3008": "the escalator well, 16 x 24 m", "mirror_bathroom": "10 x 8 m, six mirrors",
         **{f"sky_hall_{k:02d}": "10 x 2.4 x 3 m (the kit's)" for k in range(1, 5)}}


# ---------------------------------------------------------------- the README
DEFAULTS = [
    ("wing_books, wing_cinema, wing_entertainment", "about 40 m by 14 m each; shuttered fronts, scaffolding, dust sheets; off the atrium",
     "Kept: 40 m by 14 m, 6 m high, a skylight strip down the middle. Five 8 m bays a side: a shuttered front with its sign, or a door with the "
     "shutter rolled up over it. Two or three scaffold runs each (tube posts, plank decks at 2 m and 4 m; the cinema wing's is a bridge over the "
     "concourse at 4 m), dust sheets over benches, kiosks, kiddie rides and claw machines, a hung sheet on one scaffold. A pair of 2.4 m glass "
     "doors at the atrium end. books runs north from the atrium, cinema west, entertainment east."),
    ("food_court", "the food court named on the atrium's shopfronts", "Built: 30 m by 24 m, 6 m high. Ten stalls (six on the north wall, four on "
     "the east), counters with their shutters down; twenty tables with benches. Three doors: the atrium's FOOD COURT shopfront (west), the end of "
     "the entertainment wing (south), and the kitchens' door to the service corridor (north-east)."),
    ("construction", "a scaffolded zone mid-build", "Built: 24 m by 18 m, 6.5 m high, a bare concrete shell: a 6 m column grid, beams overhead, a "
     "3 m by 3 m lift pit 1.2 m deep behind barriers (Zone_hazard), half-built stud walls, plasterboard, a cement mixer and a scissor lift, and a "
     "scaffold deck along the north wall at 3 m, up a 12-step site stair, with an unfinished doorway onto sky_hall_04. Entered by the site door "
     "in the hoarding across the end of the books wing."),
    ("service_corridor", "a back corridor for the hidden network", "Built: 46 m by 2 m, 3 m high, concrete, pipes overhead, a bin bay, a shut fire "
     "door; staff doors to the three wings and the food court's kitchens; a 10 m spur to a placeholder freight lift whose gate needs keycard_tier_1 "
     "(Spot_keycard_1). The lift is the way into the hidden network (off this set)."),
    ("sky_hall_01 to sky_hall_04", "painted-sky hall connectors, from the kit", "Kept: the kit's sky_hall (claude/blender-hotel-kit, world/kit/sky_hall.json) "
     "as boxes in its own frame and with its names: 10 m by 2.4 m inside, 3.0 m high, the entry door's opening at the origin, the hall toward -z, "
     "DoorLeaf_entry and DoorLeaf_exit (1.04 m by 2.12 m in 1.1 m openings, swing 90), Link_/Arrive_ entry and exit, Marker_Entry and Marker_Exit. "
     "The kit piece goes in each sky_hall scene at (0, 0, 0), yaw 0, replacing every box; its GLB and lightmap are the kit's. The host scenes' "
     "doors onto a sky hall are the kit's 1.1 m openings with a 1.04 m leaf."),
]
CHOICES = [
    "Every scene is its own file with its own frame and its floor at y 0. The three wings are built along x with the atrium at the west end "
    "and then turned (books 90 degrees, cinema 180, entertainment 0), so each plan's north is the mall's north.",
    "How the wings meet the atrium. entrance's eight shopfronts (shared/city.js MALL.shops, in mallProps' order: SHOES, PHONES, FOOD COURT, "
    "CLOSED FOR RENOVATION on the north wall at x -11, -4, 4, 11; GIFTS and PHOTO on the west wall and OPTICIAN and TOYS on the east wall at "
    "z -6 and 4) name no wing, so each wing opens in a gap where there is no shopfront, beside the fronts that suit it: books in the north "
    "wall's middle gap (between PHONES and FOOD COURT, behind the fountain), cinema in the west wall's gap between GIFTS and PHOTO, "
    "entertainment in the east wall's gap between OPTICIAN and TOYS. All eight shopfronts stay.",
    "The FOOD COURT shopfront opens into food_court (its shutter goes up), so the food court is reached from the atrium as its sign says, and "
    "also from the far end of the entertainment wing. CLOSED FOR RENOVATION stays shut: construction is reached through the hoarding at the "
    "end of the books wing.",
    "Shops off their wings: the bookstore off the books wing (its front desk, bookstore_desk, through an INFORMATION door in its east wall), "
    "the cinema lobby at the far end of the cinema wing, the mirror bathroom behind the cinema wing's RESTROOMS bay, the food court at the far "
    "end of the entertainment wing.",
    "The photo scenes are painted-sky spaces (docs/WORLD.md: the other painted-sky spaces are hall connectors). With no photos, each is my "
    "guess at an abandoned mall space: scene_2909 a sky court, 24 m square under a painted sky, sunk 1 m in the middle round a bandstand, "
    "with plastic trees; scene_3012 a painted-sky street, a fake old town of house fronts with balconies, lamp posts and sheeted cafe tables; "
    "scene_2991 (with IMG_3014) a soft-play court and, through a 6 m opening, a carousel hall; scene_3008 (with IMG_3010) an escalator well, "
    "a lower concourse and a gallery 4.5 m up joined by two stopped escalators. Each opens off a wing through an unmarked door between "
    "two shutters: 2909 off books, 3012 off cinema, 2991 and 3008 off entertainment.",
    "The sky halls join the odd ones into a loop: sky_hall_01 from the sky court (2909) to the painted-sky street (3012); sky_hall_02 from the "
    "street to the escalator well's gallery (3008); sky_hall_03 from the gallery to the mirror bathroom, coming out through the portal mirror; "
    "sky_hall_04 from the construction zone's scaffold deck to the carousel hall (2991). So the three wings also join behind the shops.",
    f"The mirror bathroom: six mirrors over the basins, each its own object Mirror_1 to Mirror_6 (art only, in the GLB, with custom properties "
    f"`mirror`, `portal` and `portal_to`). Mirror_{G.PORTAL_MIRROR} is the portal [DEFAULT]: the link `mirror` stands in front of it and "
    "pairs with sky_hall_03's EXIT door. The exporter does not write mirrors to the layout file, so each also has a Spot_mirror_<n> in front of "
    "it (with `mirror` and `portal`), and Spot_puzzle_1 is the puzzle: which mirror is the way through.",
    "Mannequins: Spot_mannequin_<n> in 16 scenes, each with `role` (dressing, npc or monster, the three docs/WORLD.md gives) and `what` "
    "(how it stands); the mix is my default. The page draws them.",
    "Spot kinds the table does not name: `puzzle` (the bookstore desk's till drawer, the mirror bathroom), `mirror`, and `keycard` (the "
    "freight lift's reader).",
    "The escalators in scene_3008 are stairs (one box a step, 18 steps of 0.25 m), as the hotel's and the grocery's are. The sky court's "
    "steps down are rings of boxes, three steps of 0.25 m on each side.",
    "Light: one greybox set for the stills. The day set and the emergency set (the mall locks you in at 20:00) come with dressing.",
]
QUESTIONS = [
    "The wings open in the gaps between the atrium's shopfronts (books behind the fountain, cinema between GIFTS and PHOTO, entertainment "
    "between OPTICIAN and TOYS), so all eight fronts stay. Or should a wing go through a shopfront instead (the cinema through PHOTO, "
    "entertainment through TOYS)?",
    "The atrium's FOOD COURT shopfront opens into the food court, which is also at the end of the entertainment wing. Keep both ways in? And "
    "should CLOSED FOR RENOVATION open into the construction zone too (now only the books wing's hoarding does)?",
    "Scale: each wing is 40 m long off a 32 m by 24 m atrium, bigger inside than the building on the street, as the hotel and the grocery "
    "are. Keep it, or shorten the wings?",
    "The photo scenes are my guesses (2909 a sunken sky court, 3012 a painted-sky street, 2991 with 3014 a soft play and a carousel, 3008 "
    "with 3010 an escalator well). Do they match the photos? If not, a line on what each photo shows is enough to rebuild them.",
    "The sky-hall loop runs sky court, street, escalator well, mirror bathroom, with construction to the carousel on its own. Is that the "
    "order you want, and should the mirror's way be one way (out of the mirror only)?",
    f"The mirror puzzle: six mirrors, Mirror_{G.PORTAL_MIRROR} the way through. How many mirrors, which one, and what gives it away "
    "(a reflection that is wrong, one that is right)?",
    "Mannequins: 49 spots, each marked dressing, npc or monster. Too many or too few, and is the mix right?",
    "At night the mall locks you in. Should the service corridor's freight lift (the hidden network, keycard_tier_1) be a way out, or "
    "locked too?",
]


def readme(out, docs):
    L = ["# Mall greybox (docs/BLENDER_AREAS.md, section 3: the mall)", "",
         "Plain grey boxes, to scale, for the eighteen mall scenes beyond part 1's `entrance` (the atrium): the three wings, the bookstore and "
         "its front desk, the cinema lobby, the four photo scenes, the mirror bathroom, the food court, the construction zone, the service "
         "corridor and four sky halls. There are no reference photos, so each scene is built from its written description, and a photo name "
         "is only a label. This is for review: no scene or link has been added to the manifest, and the greybox GLBs are in `glb/` here, not "
         "in `world/`.", "",
         "- Built by `tools/blender/build_mall_greybox.py` (it follows the hotel's and the grocery's greybox builds), which writes "
         "`world/<scene>.json` through `tools/blender/export_scene.py`, the GLB, the plans and the stills. The labels and these sheets come "
         "from `tools/blender/mall_greybox_sheets.py`.",
         "- `python tools/blender/build_mall_greybox.py --check .` runs the gates on the exported files: every link meets its other side (the "
         "links that leave this set, to entrance and the hidden network, are listed), every scene is reachable from entrance, every step rises "
         "at most 0.27 m with one box a step, every corridor, aisle and doorway is at least 1.6 m wide and clear, and the bathroom's GLB has "
         "Mirror_1 to Mirror_6 as separate objects with the portal marked.",
         "- `CHECKS.txt`: the gates, `node tools/worlddoc.mjs check` on every file (0 errors; every warning says a scene or link is new to the "
         "manifest), `node --test shared/*.test.js`, and the privacy grep.",
         "- `overview.png`: how the scenes join entrance, and the painted-sky loop. For each scene, `<scene>_plan.jpg` (top-down, scale bar, "
         "rooms, doors, links, spots and mannequins labelled) and `<scene>_still.jpg` (eye height, 1.55 m).", "",
         "## Scenes", "", "| Scene | Size | Links (door: where it goes) | Colliders, doors, spots | Mood |", "|---|---|---|---|---|"]
    for sid in G.SCENES:
        S = G.build(sid)
        d = docs.get(sid, {})
        spots = {}
        for sp in d.get("spots", []):
            spots[sp["kind"]] = spots.get(sp["kind"], 0) + 1
        sp = ", ".join(f"{k} x{v}" for k, v in sorted(spots.items())) or "none"
        links = "; ".join(f"`{k}`: {v}" for k, v in S.links.items()) or "none"
        L.append(f"| `{sid}` | {S.size} | {links} | {len(d.get('colliders', []))} colliders, {len(d.get('doors', []))} doors; "
                 f"zones: {len(d.get('zones', []))}; spots: {sp} | {S.mood} |")
    L += ["", "## Links", "",
          "Each pair is one link. Pressing F at one side's `Link_<door>` puts you at the other side's `Arrive_<door>`, facing its -Y axis. "
          "Every pair has both sides built (the gate checks it).", "", "| From | To | Connector | Note |", "|---|---|---|---|"]
    for (a, da), (b, db), kind, note in G.PAIRS:
        L.append(f"| `{a}.{da}` | `{b}.{db}` | {kind} | {note} |")
    L += ["", "Links that leave this set (the coordinator wires the other side; entrance is part 1's, in shared/city.js, and is not touched here):", ""]
    for (s, dd), note in G.OUTSIDE.items():
        L.append(f"- `{s}.{dd}`: {note}")
    L += ["", "## The defaults ([DEFAULT] in docs/BLENDER_AREAS.md)", "", "| Scene | Default | Kept or changed |", "|---|---|---|"]
    for s, dflt, k in DEFAULTS:
        L.append(f"| {s} | {dflt} | {k} |")
    L += ["", "Choices the table left open:", ""] + [f"- {c}" for c in CHOICES]
    L += ["", "## Open questions for the owner", ""] + [f"{i}. {q}" for i, q in enumerate(QUESTIONS, 1)]
    L += ["", "## Not done here", "",
          "- `entrance` is untouched: its north, west and east walls (shared/city.js MALL; its test holds world/entrance.json to it) still have "
          "no openings, and its FOOD COURT shutter is still down. The coordinator cuts them with the links, at the places listed above.",
          "- The kit's sky hall is not linked in: the sky_hall scenes are its plain-box stand-ins, in its frame and with its names.",
          "- Placeholders: the freight lift is a car behind a gate (the kit's service corridor and freight lift replace it later); the escalators "
          "are stairs; the house fronts' doors, the screens' doors and the stalls do not open.",
          "- Light: one greybox set. The day and emergency sets come with dressing, one scene at a time.",
          "- The manifest, `index.html`, `shared/` and the tests are untouched. `node tools/worlddoc.mjs check` warns that each scene and link is "
          "new; that is expected until the coordinator adds them.", ""]
    (out / "README.md").write_text("\n".join(L), encoding="utf-8")


def owner_sheet(path, out, renders):
    W = 1080
    f_t, f_h, f_b = font(52, True), font(38, True), font(32)
    blocks = []

    def para(s, f, col=INK, wrap=48, gap=10):
        for p in textwrap.wrap(s, wrap):
            blocks.append(("t", p, f, col))
        blocks.append(("gap", gap))
    para("Mall greybox: ready to look at", f_t, wrap=30)
    para("The eighteen mall scenes round the atrium: three wings, the bookstore, its desk, the cinema, the food court, the construction zone, "
         "the service corridor, four photo scenes, the mirror bathroom and four sky halls. Plain grey boxes to scale, all joined. Nothing is "
         "wired into the game yet.", f_b, GREY)
    blocks.append(("img", Image.open(out / "overview.png")))
    blocks.append(("gap", 20))
    para("What it looks like at eye height", f_h)
    grid = []
    for s in ("wing_books", "wing_cinema", "wing_entertainment", "bookstore", "cinema_lobby", "food_court", "construction", "scene_2909",
              "scene_3012", "scene_2991", "scene_3008", "mirror_bathroom"):
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


def main(a):
    renders = Path(a[a.index("--renders") + 1])
    out = Path(a[a.index("--out") + 1]) if "--out" in a else G.ROOT / "docs/renders/mall_greybox"
    out.mkdir(parents=True, exist_ok=True)
    docs = {}
    for sid in G.SCENES:
        f = G.out_path(renders, sid)
        if f.exists():
            docs[sid] = json.loads(f.read_text())
    sizes = {}
    for sid in G.SCENES:
        S = G.build(sid)
        sizes[sid] = SHORT.get(sid, S.size)
        if (renders / "renders" / f"{sid}_still.png").exists():
            plan_sheet(S, renders / "renders", out)
            still(S, renders / "renders", out)
    overview(out, sizes)
    readme(out, docs)
    if "--owner" in a:
        owner_sheet(a[a.index("--owner") + 1], out, renders / "renders")
    print("sheets written to", out)


if __name__ == "__main__":
    main(sys.argv[1:])
