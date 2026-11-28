"""The grocery greybox's review sheets, drawn over the Blender renders of tools/blender/build_grocery_greybox.py (no Blender here; Pillow only).
It follows tools/blender/hotel_greybox_sheets.py.

    python tools/blender/grocery_greybox_sheets.py --renders <build out dir> [--out docs/renders/grocery_greybox] [--owner <png>]

For every scene: <out>/<scene>_plan.jpg (the orthographic plan with its labels, doors, links, spots, cameras, a scale bar and north; aisles'
two levels side by side) and <out>/<scene>_still.jpg (the eye-height still). Then <out>/overview.png (how the scenes join main_floor, to
scale and as a diagram) and <out>/README.md (every scene, its size, links and spots, the defaults, the open questions). --owner also writes a
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
import build_grocery_greybox as G  # noqa: E402

FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/Library/Fonts")]


def font(size, bold=False):
    names = (["arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf", "Arial.ttf"])
    for d in FONT_DIRS:
        for n in names:
            if (d / n).exists():
                return ImageFont.truetype(str(d / n), size)
    return ImageFont.load_default()


INK, BLUE, ORANGE, MAGENTA, GREEN, GREY, RED = (25, 25, 30), (20, 90, 200), (215, 110, 20), (190, 30, 150), (20, 150, 60), (110, 110, 115), (200, 30, 30)
SPOT_COL = {"monster": (200, 40, 40), "food": (20, 140, 120), "cart": (215, 60, 30), "hide": (60, 60, 60), "camhead": (90, 90, 160),
            "locker": (150, 100, 40), "keycard": (190, 30, 150), "monitor": (90, 90, 160)}


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
        if multi and lv > 0:
            continue
        a, b = P(o["x0"], o["z0"]), P(o["x1"], o["z1"])
        dashed_rect(dr, a[0], a[1], b[0], b[1], GREY, w=3)
        text(dr, ((a[0] + b[0]) / 2, a[1] + 60), o["text"], f_note, GREY)
    for d in S.doors:
        if not here(d["hinge"][1]):
            continue
        w = d["props"]["width"]
        h0 = P(d["hinge"][0], d["hinge"][2])
        h1 = P(d["hinge"][0] + w * math.cos(d["yaw"]), d["hinge"][2] - w * math.sin(d["yaw"]))
        dr.line((h0, h1), fill=ORANGE, width=7)
    for e in S.empties:
        n, (x, y, z) = e["name"], e["pos"]
        if not here(y) and not n.startswith("SecCam_"):
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
            text(dr, (px + fx * 56, pz + fz * 56), n[7:], f_link, BLUE)
        elif n.startswith("SecCam_"):
            fx, fz = e["face"]
            ln = math.hypot(fx, fz) or 1
            ang = math.atan2(fz / ln, fx / ln)
            pts = [(px, pz)] + [(px + 70 * math.cos(ang + t), pz + 70 * math.sin(ang + t)) for t in (-0.35, 0.35)]
            dr.polygon(pts, outline=RED, width=2)
            dr.rectangle((px - 8, pz - 8, px + 8, pz + 8), fill=RED, outline=(255, 255, 255), width=2)
            text(dr, (px - 70 * math.cos(ang), pz - 70 * math.sin(ang) + 2), n, f_spot, RED, halo=2)
        elif n.startswith("Spot_"):
            kind = n.split("_")[1]
            col = SPOT_COL.get(kind, MAGENTA)
            dr.rectangle((px - 7, pz - 7, px + 7, pz + 7), fill=col, outline=(255, 255, 255), width=2)
            text(dr, (px, pz - 19), n[5:], f_spot, col, halo=2)
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
    side = 600
    rows = [f"{door}  ->  {to}" for door, to in S.links.items()]
    spots, cams = {}, 0
    for e in S.empties:
        if e["name"].startswith("Spot_"):
            k = e["name"].split("_")[1]
            spots[k] = spots.get(k, 0) + 1
        cams += e["name"].startswith("SecCam_")
    head = 96
    H = max(body.height + head, head + 60 + 28 * (2 * len(rows) + len(spots) + 18))
    im = Image.new("RGB", (body.width + side, H), (255, 255, 255))
    im.paste(body, (0, head))
    dr = ImageDraw.Draw(im)
    text(dr, (16, 30), f"{S.id}  -  {S.title}", font(32, True), INK, anchor="lm", halo=0)
    text(dr, (16, 70), f"{S.size}.  Top-down, orthographic; ceilings and anything 2.4 m above the floor are left out.", font(19), GREY, anchor="lm", halo=0)
    x, y = body.width + 18, head + 10
    f, fb = font(19), font(21, True)

    def line(s, ff=f, col=INK):
        nonlocal y
        for part in textwrap.wrap(s, 50) or [""]:
            dr.text((x, y), part, font=ff, fill=col)
            y += 26
    line("LINKS (press F at the blue dot)", fb)
    for r in rows:
        line(r, f, BLUE)
    y += 10
    if spots:
        line("SPOTS (the page places these)", fb)
        line(", ".join(f"{k} x{v}" for k, v in sorted(spots.items())), f, MAGENTA)
        y += 10
    if cams:
        line(f"SECURITY CAMERAS: {cams} SecCam_ (restricted)", fb, RED)
        y += 10
    line("KEY", fb)
    line("orange bar: door leaf (from its hinge)", f, ORANGE)
    line("blue dot: Link_ (press F); blue tick: Arrive_ and the way you face", f, BLUE)
    line("square: Spot_; green triangle: Marker_Spawn", f, MAGENTA)
    line("red square and cone: SecCam_ and where it faces", f, RED)
    line("dashed grey: a scene above this one", f, GREY)
    im.save(out / f"{S.id}_plan.jpg", quality=88, optimize=True)        # no comment or APP1 segment


def still(S, renders, out):
    im = Image.open(renders / f"{S.id}_still.png").convert("RGB")
    dr = ImageDraw.Draw(im)
    (pos, face, pitch) = S.still
    text(dr, (20, im.height - 28), f"{S.id}: eye height {G.EYE} m, from ({pos[0]:g}, {pos[2]:g})", font(26, True), INK, anchor="lm")
    im.save(out / f"{S.id}_still.jpg", quality=86, optimize=True)


# ---------------------------------------------------------------- the overview: to scale on the left, a diagram on the right
FOOT = {   # scene: (x0, x1, z0, z1, style), in the shared frame (main_floor's)
    "main_floor": (G.MF["x0"], G.MF["x1"], G.MF["z0"], G.MF["z1"], "built"),
    "aisles": (G.AX0, G.AX1, G.AZ0, G.AZ1, "new"),
    "second_floor": (G.MEZ["x0"], G.MEZ["x1"], G.MEZ["z0"], G.MEZ["z1"], "above"),
    "back_of_house": (G.BX0, G.BX1, G.BZ0, G.BZ1, "new"),
    "basement": (G.BX0, G.BX1, G.KZ0, G.KZ1, "below"),
}
DIAG = {"street": (1880, 1500), "main_floor": (1880, 1180), "aisles": (1880, 800), "second_floor": (1500, 470), "back_of_house": (2290, 1180),
        "basement": (2290, 1500), "secret_ops": (2290, 800)}
CONN_COL = {"doors": (60, 60, 70), "opening": (60, 60, 70), "stairs": (215, 110, 20), "escalator": (215, 160, 20), "freight_lift": (20, 90, 200),
            "service_corridor": (190, 30, 150)}
DIAG_EDGES = [("street", "main_floor", "doors", "built (part 1)"), ("main_floor", "aisles", "opening", "north wall opening"),
              ("aisles", "second_floor", "stairs", "stairs"), ("aisles", "second_floor", "escalator", "escalator"),
              ("main_floor", "back_of_house", "doors", "staff door"), ("back_of_house", "basement", "stairs", "stairs"),
              ("back_of_house", "basement", "freight_lift", "freight lift"),
              ("back_of_house", "secret_ops", "service_corridor", "freight lift + keycard_tier_1")]


def overview(out, sizes):
    W, H = 2700, 1720
    im = Image.new("RGB", (W, H), (250, 250, 248))
    dr = ImageDraw.Draw(im)
    # to scale: every footprint in main_floor's frame (north up)
    s = 18.0
    ox, oz = 80 - G.AX0 * s, 120 - G.AZ0 * s
    P = lambda x, z: (ox + x * s, oz + z * s)
    order = ["aisles", "back_of_house", "main_floor", "basement", "second_floor"]
    fills = {"built": (225, 232, 240), "new": (255, 255, 255)}
    for sid in order:
        x0, x1, z0, z1, st = FOOT[sid]
        a, b = P(x0, z0), P(x1, z1)
        if st in fills:
            dr.rectangle((a, b), fill=fills[st], outline=INK, width=4)
        else:
            dashed_rect(dr, a[0], a[1], b[0], b[1], BLUE if st == "above" else GREEN, dash=14, w=4)
    for sid, (x0, x1, z0, z1, st) in FOOT.items():
        a, b = P(x0, z0), P(x1, z1)
        cx = (a[0] + b[0]) / 2 if sid != "aisles" else P(10.0, 0)[0]
        cy = {"aisles": a[1] + 50, "second_floor": (a[1] + b[1]) / 2, "basement": b[1] - 60, "back_of_house": a[1] + 50, "main_floor": (a[1] + b[1]) / 2}[sid]
        sub = {"built": "part 1 (built)", "new": sizes.get(sid, ""), "above": "mezzanine over aisles, 5 m up", "below": "4 m below back_of_house"}[st]
        text(dr, (cx, cy), sid, font(30, True), INK)
        text(dr, (cx, cy + 34), sub, font(20), GREY)
    # where the links are, on the footprints
    marks = [((0.0, -9.1), "opening"), ((12.1, -5.5), "staff door"), ((-2.3, -22.6), "stairs + escalator"), ((34.1, 7.1), "stairs"),
             ((39.2, 10.3), "freight lift"), ((0.0, 9.1), "front door (street)")]
    for (x, z), t in marks:
        px, pz = P(x, z)
        dr.ellipse((px - 11, pz - 11, px + 11, pz + 11), fill=BLUE, outline=(255, 255, 255), width=3)
        text(dr, (px, pz + 26 if z > 0 else pz - 26), t, font(20, True), BLUE)
    a = P(G.AX0, G.MF["z1"] + 4)
    for i in range(2):
        dr.rectangle((a[0] + i * 10 * s, a[1], a[0] + (i + 1) * 10 * s, a[1] + 12), fill=INK if i % 2 == 0 else (255, 255, 255), outline=INK, width=2)
    text(dr, (a[0] + 10 * s, a[1] + 34), "20 m", font(22, True), INK, halo=0)
    text(dr, (60, 60), "To scale, top-down, north up: every scene in main_floor's frame", font(26, True), INK, anchor="lm", halo=0)
    text(dr, (60, 1650), "white: new here; blue-grey: main_floor (part 1); dashed: second_floor above aisles (blue), basement below back_of_house (green)",
         font(20), GREY, anchor="lm", halo=0)
    # the diagram
    bw, bh = 330, 110

    def boxof(sid):
        x, y = DIAG[sid]
        return x - bw / 2, y - bh / 2, x + bw / 2, y + bh / 2

    def anchor(sid, other):
        x0, y0, x1, y1 = boxof(sid)
        ox_, oy_ = DIAG[other]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        dx, dy = ox_ - cx, oy_ - cy
        if abs(dx) * (y1 - y0) > abs(dy) * (x1 - x0):
            return (x1 if dx > 0 else x0), cy
        return cx, (y1 if dy > 0 else y0)
    done = {}
    for a_, b_, kind, note in DIAG_EDGES:
        k = done.get((a_, b_), 0)
        done[(a_, b_)] = k + 1
        p, q = anchor(a_, b_), anchor(b_, a_)
        off = (k - 0.5) * 26 if (a_, b_) in (("aisles", "second_floor"), ("back_of_house", "basement")) else 0
        horiz = abs(p[0] - q[0]) > abs(p[1] - q[1])
        p = (p[0], p[1] + off) if horiz else (p[0] + off, p[1])
        q = (q[0], q[1] + off) if horiz else (q[0] + off, q[1])
        dr.line((p, q), fill=CONN_COL[kind], width=6)
        mx, my = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
        text(dr, (mx + (0 if horiz else (70 if off >= 0 else -70) + (40 if not off else 0)), my + (-22 + 2 * off if horiz else 0)), note, font(19, True), CONN_COL[kind])
    for sid in DIAG:
        x0, y0, x1, y1 = boxof(sid)
        mine = sid in G.SCENES
        fill = (255, 255, 255) if mine else (225, 232, 240)
        dr.rounded_rectangle((x0, y0, x1, y1), 14, fill=fill, outline=INK, width=4 if mine else 2)
        text(dr, ((x0 + x1) / 2, y0 + 30), sid if sid != "secret_ops" else "secret_ops/\nservice_entry", font(27, True), INK, halo=0)
        sub = sizes.get(sid) or {"street": "city (part 1)", "main_floor": "part 1, built", "secret_ops": "area 8, not built"}.get(sid, "")
        if sid != "secret_ops":
            text(dr, ((x0 + x1) / 2, y0 + 72), sub, font(19), GREY, halo=0)
    text(dr, (1900, 60), "How they join (grey boxes: not in this set)", font(26, True), INK, halo=0)
    text(dr, (2070, 1650), "Lines: grey doors and openings, orange stairs, yellow escalator, blue freight lift, pink the keycard route.",
         font(19), GREY, halo=0)
    im.save(out / "overview.png", optimize=True)
    return im


SHORT = {"aisles": "48 x 40 m, 8.5 m high", "second_floor": "30 x 20 m mezzanine", "back_of_house": "30 x 24 m, restricted",
         "basement": "30 x 20 m, restricted"}


# ---------------------------------------------------------------- the README
DEFAULTS = [
    ("aisles", "48 m by 40 m; long repeating aisles and the red-cart clearing (IMG_3027) in the middle; an opening from main_floor's north side",
     "Kept: 48 m by 40 m inside, 8.5 m high (the mezzanine stands in its west half). Eleven gondola lines run north to south (1.2 m wide, 2.4 m "
     "aisles, red end caps); the clearing is 11.2 m by 10.4 m at the middle, the three gondolas through it broken. The opening is in main_floor's "
     "north wall, the 3.6 m gap between its cooler banks, 3 m high, under its camera."),
    ("second_floor", "30 m by 20 m; a mezzanine with homeware, a closed café and a view down over the aisles; stairs and an escalator from aisles",
     "Kept: 30 m north to south by 20 m east to west, 3.2 m high, over aisles' west half at y 5. The east side is glass over a 1.1 m rail, with "
     "the aisles below as art. Homeware in the north half, the café in the south-west (counter shutter down, chairs up on the tables)."),
    ("back_of_house", "30 m by 24 m; racking, a loading dock, a break room, lockers, a manager's office with camera monitors; SecCam; the staff "
     "door, a freight lift and a keycard reader", "Kept: 30 m by 24 m, 4.5 m high, east of main_floor (its west wall is main_floor's east wall). "
     "Four rows of racking, three dock doors (shut), the four staff rooms 3 m high along the south wall, five SecCam_ cameras, a Zone_restricted "
     "over all of it."),
    ("basement", "30 m by 20 m; cold storage, a plant room and pallets; stairs and the freight lift from back_of_house",
     "Kept: 30 m by 20 m, 3.7 m high, under back_of_house's south 20 m (its floor is 4 m below). Two walk-in freezers, the plant room with the "
     "breaker board, nine pallet stacks, two SecCam_ cameras, a Zone_restricted."),
]
CHANGES = [
    "All four scenes use main_floor's x and z, so they fit round it as one building: aisles north, back_of_house east, second_floor over aisles' "
    "west half, basement under back_of_house. Each scene's floor is still at y 0.",
    "The escalator is stairs (one box a step, 0.25 m), as the hotel's escalators are.",
    "The freight lift serves back_of_house, basement and Secret Operations: in back_of_house its gate has two press-F points, `freight_down` (to "
    "the basement) and `secret_ops` (on past the basement, once keycard_tier_1 is swiped at the reader, Spot_keycard_1).",
    "Camera heads on the shop floors (aisles, second_floor) are `Spot_camhead` (the page draws them, as on main_floor); the restricted scenes have "
    "`SecCam_` cameras that go to the file's `cameras` list (a separate exporter commit: SecCam_ empties now export in world/L1.json's shape).",
    "Spot kinds the table does not name: `food`, `cart`, `camhead`, `monster` (night threats, `when: night`), `hide`, `locker`, `monitor` (the "
    "office's camera monitors), `keycard`, `dock` (shut dock doors, a truck later), `breaker` (the store's breakers) and `lookout` (the view "
    "down from the mezzanine).",
    "No `Spot_checkout`: the checkout stays on main_floor (part 1).",
]
QUESTIONS = [
    "Scale: main_floor fills the street's grocery building (24 m by 18 m), but aisles (48 m by 40 m) and back_of_house (30 m by 24 m) behind it are much "
    "bigger than that building. Keep it (bigger inside, liminal, as the hotel's atrium), or shrink them?",
    "The opening into aisles is the gap between main_floor's coolers, under its camera. main_floor's north wall (shared/city.js) needs that opening cut "
    "when the coordinator wires the link. Is that the place, or should it be at one end of the north wall?",
    "The staff door is main_floor's existing closed pair on its east wall. Should it open freely by day, or only for staff (a job, or a key)?",
    "The freight lift's two press-F points: down to the basement, and on to Secret Operations with keycard_tier_1. Or should the basement need the "
    "keycard too, or the stairs be the only way down?",
    "Should second_floor's café be enterable behind its counter, or stay shut (shutter down)?",
    "The red-cart clearing holds eight red carts in a ring (the page places them). More, fewer, or a different arrangement from the photo?",
]


def readme(out, docs):
    L = ["# Grocery greybox (docs/BLENDER_AREAS.md, section 2: the grocery, the rest)", "",
         "Plain grey boxes, to scale, for the four grocery scenes beyond part 1's `main_floor`: `aisles`, `second_floor`, `back_of_house` and "
         "`basement`. There are no reference photos, so each scene is built from its written description; IMG_3027 is only a label. This is for "
         "review: no scene or link has been added to the manifest, and the greybox GLBs are in `glb/` here, not in `world/`.", "",
         "- Built by `tools/blender/build_grocery_greybox.py` (it follows the hotel greybox's build), which writes `world/<scene>.json` through "
         "`tools/blender/export_scene.py`, the GLB, the plans and the stills. The labels and these sheets come from `tools/blender/grocery_greybox_sheets.py`.",
         "- `python tools/blender/build_grocery_greybox.py --check .` runs the gates on the exported files: every link meets its other side (the "
         "links that leave this set are listed), every step rises at most 0.27 m, every corridor and aisle is at least 1.6 m wide and clear, and "
         "the restricted scenes have cameras.",
         "- `CHECKS.txt`: the gates, `node tools/worlddoc.mjs check` on every file (0 errors; every warning says a scene or link is new to the "
         "manifest), `node --test shared/*.test.js`, and the privacy grep.",
         "- `overview.png`: the four scenes round main_floor, to scale, and how they join. For each scene, `<scene>_plan.jpg` (top-down, scale "
         "bar, rooms, doors, links, spots and cameras labelled) and `<scene>_still.jpg` (eye height, 1.55 m).", "",
         "## Scenes", "", "| Scene | Size | Links (door: where it goes) | Colliders, doors, cameras, spots | Mood |", "|---|---|---|---|---|"]
    for sid in G.SCENES:
        S = G.build(sid)
        d = docs.get(sid, {})
        spots = {}
        for sp in d.get("spots", []):
            spots[sp["kind"]] = spots.get(sp["kind"], 0) + 1
        sp = ", ".join(f"{k} x{v}" for k, v in sorted(spots.items())) or "none"
        links = "; ".join(f"`{k}`: {v}" for k, v in S.links.items()) or "none"
        L.append(f"| `{sid}` | {S.size} | {links} | {len(d.get('colliders', []))} colliders, {len(d.get('doors', []))} doors, "
                 f"{len(d.get('cameras', []))} cameras; zones: {len(d.get('zones', []))}; spots: {sp} | {S.mood} |")
    L += ["", "## How it sits round main_floor", "",
          "All four scenes use `main_floor`'s x and z (shared/city.js: its hall is x -12 to 12, z -9 to 9, walls 0.2 m thick), so the openings "
          "meet it exactly. Each scene's floor is at y 0.", "",
          "- `aisles` lies north of main_floor. Its south wall is main_floor's north wall (z -9.2 to -9.0); its opening is x -1.8 to 1.8, 3 m high, "
          "the gap between main_floor's cooler banks (x -9.6 to -2 and 2 to 9.6), under main_floor's camera (x 0, y 3.4).",
          "- `back_of_house` lies east of main_floor. Its west wall is main_floor's east wall (x 12.0 to 12.2); its staff door is main_floor's "
          "closed pair (z -6.3 to -4.7, 2.2 m high), now two leaves that open into back_of_house.",
          "- `second_floor` is the mezzanine over aisles' west half (x -24 to -4, z -44.2 to -14.2). In aisles its slab top is at y 5; the stairs "
          "(19 steps of 0.263 m) and the escalator (20 of 0.25 m) climb to a landing in front of its glass, x -4 to -0.6, z -24 to -21.2.",
          "- `basement` lies under back_of_house's south 20 m (z -5 to 15); back_of_house's floor is 4 m above it. Its stairwell (15 steps of "
          "0.267 m) stands under back_of_house's stair door, and the freight lift's shaft under back_of_house's (x 37.4 to 41, z 10.2 to 14).", "",
          "## Links", "",
          "Each pair is one link. Pressing F at one side's `Link_<door>` puts you at the other side's `Arrive_<door>`, facing its -Y axis. "
          "Every pair has both sides built (the gate checks it).", "", "| From | To | Connector | Note |", "|---|---|---|---|"]
    for (a, da), (b, db), kind, note in G.PAIRS:
        L.append(f"| `{a}.{da}` | `{b}.{db}` | {kind} | {note} |")
    L += ["", "Links that leave this set (the coordinator wires the other side):", ""]
    for (s, dd), note in G.OUTSIDE.items():
        L.append(f"- `{s}.{dd}`: {note}")
    L += ["", "## The defaults ([DEFAULT] in docs/BLENDER_AREAS.md)", "", "| Scene | Default | Kept or changed |", "|---|---|---|"]
    for s, dflt, k in DEFAULTS:
        L.append(f"| {s} | {dflt} | {k} |")
    L += ["", "Choices the table left open:", ""] + [f"- {c}" for c in CHANGES]
    L += ["", "## Open questions for the owner", ""] + [f"{i}. {q}" for i, q in enumerate(QUESTIONS, 1)]
    L += ["", "## Not done here", "",
          "- `main_floor` is untouched: its north and east walls (shared/city.js, its test holds world/main_floor.json to it) still have no opening; "
          "the coordinator cuts them with the links, at the places listed above.",
          "- Placeholders: the freight lift is a car behind a gate (the connector kit's service corridor and freight lift replace it later); "
          "the escalator is stairs; the dock doors do not open.",
          "- Light: one greybox set. Part 1's two sets (by day fluorescent and open, by night freezer glow and emergency lights) come with dressing.",
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
    para("Grocery greybox: ready to look at", f_t, wrap=30)
    para("The four scenes past the main floor (aisles, second floor, back of house, basement), plain grey boxes to scale, all joined. "
         "Nothing is wired into the game yet.", f_b, GREY)
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
    out = Path(a[a.index("--out") + 1]) if "--out" in a else G.ROOT / "docs/renders/grocery_greybox"
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
        plan_sheet(S, renders / "renders", out)
        still(S, renders / "renders", out)
    overview(out, sizes)
    readme(out, docs)
    if "--owner" in a:
        owner_sheet(a[a.index("--owner") + 1], out, renders / "renders")
    print("sheets written to", out)


if __name__ == "__main__":
    main(sys.argv[1:])
