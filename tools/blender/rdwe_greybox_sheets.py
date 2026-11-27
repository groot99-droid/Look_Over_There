"""The Right Door, Wrong Exit greybox's review sheets, drawn over the Blender renders of tools/blender/build_rdwe_greybox.py (Pillow only).

    python tools/blender/rdwe_greybox_sheets.py --renders <build out dir> [--out docs/renders/rdwe_greybox] [--phase ABC]
                                                [--owner <png>] [--owner-rooms <png>]

For every scene: <out>/<scene>_plan.jpg (the orthographic plan with its doors, links, spots, cameras, labels, a scale bar and north; a
two-level room's levels side by side) and <out>/<scene>_still.jpg (eye height). Then <out>/graph.png (how the rooms connect: the notebook's
graph), <out>/README.md (rulings, every scene, every link, the open questions) and <out>/ROOMS.md (the Phase C list, one line a room).
--owner writes the phone sheet for phases A and B and the graph; --owner-rooms the phone sheet that lists the Phase C rooms.
Labels come from the same model the build used. Images are written fresh, with no metadata.
"""
import json
import math
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_rdwe_greybox as G  # noqa: E402

FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/Library/Fonts")]


def font(size, bold=False):
    names = (["arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf", "Arial.ttf"])
    for d in FONT_DIRS:
        for n in names:
            if (d / n).exists():
                return ImageFont.truetype(str(d / n), size)
    return ImageFont.load_default()


INK, BLUE, ORANGE, MAGENTA, GREEN, GREY, RED = (25, 25, 30), (20, 90, 200), (215, 110, 20), (190, 30, 150), (20, 150, 60), (110, 110, 115), (200, 30, 30)
SPOT_COL = {"computer": (200, 40, 40), "hide": (60, 60, 60), "agent": (120, 0, 0), "view": (20, 140, 120), "trick": (130, 60, 200)}


def text(dr, xy, s, f, fill=INK, anchor="mm", halo=3):
    dr.text(xy, s, font=f, fill=fill, anchor=anchor, stroke_width=halo, stroke_fill=(255, 255, 255), align="center")


def short(sid):
    return sid[5:] if sid.startswith("rdwe_") else sid


# ---------------------------------------------------------------- the plans
def plan_panel(S, pv, raw):
    ren = Image.open(raw).convert("RGB").resize((pv["W"], pv["H"]))
    im = ren
    sx = pv["W"] / (pv["x1"] - pv["x0"])
    P = lambda x, z: ((x - pv["x0"]) * sx, (z - pv["z0"]) * sx)
    lv = pv["level"]
    multi = len(S.levels) > 1
    here = (lambda y: (lv - 0.6 <= y < lv + 2.4)) if multi else (lambda y: True)
    dr = ImageDraw.Draw(im)
    sc = max(0.8, min(1.3, pv["W"] / 1300.0))
    f_room, f_link, f_spot, f_note = font(int(30 * sc), True), font(int(21 * sc), True), font(int(17 * sc)), font(int(19 * sc))
    for d in S.doors:
        if not here(d["hinge"][1]):
            continue
        w = d["props"]["width"]
        h0 = P(d["hinge"][0], d["hinge"][2])
        h1 = P(d["hinge"][0] + w * math.cos(d["yaw"]), d["hinge"][2] - w * math.sin(d["yaw"]))
        col = GREY if d["props"].get("opens") == "never" else ORANGE
        dr.line((h0, h1), fill=col, width=8)
        if d["props"].get("opens") == "never":
            mx, my = (h0[0] + h1[0]) / 2, (h0[1] + h1[1]) / 2
            dr.line((mx - 7, my - 7, mx + 7, my + 7), fill=RED, width=3)
            dr.line((mx - 7, my + 7, mx + 7, my - 7), fill=RED, width=3)
    for c in S.cams:
        x, y, z = c["pos"]
        if not here(y - 3.0):
            continue
        px, pz = P(x, z)
        fx, fz = c["face"]
        ln = math.hypot(fx, fz) or 1
        fx, fz = fx / ln, fz / ln
        dr.polygon([(px, pz), (px + 40 * fx - 18 * fz, pz + 40 * fz + 18 * fx), (px + 40 * fx + 18 * fz, pz + 40 * fz - 18 * fx)], fill=(250, 200, 60), outline=INK)
        text(dr, (px - fx * 22, pz - fz * 22), c["name"][7:], f_spot, INK, halo=2)
    for e in S.empties:
        n, (x, y, z) = e["name"], e["pos"]
        if not here(y):
            continue
        px, pz = P(x, z)
        if n.startswith("Link_"):
            dr.ellipse((px - 10, pz - 10, px + 10, pz + 10), fill=BLUE, outline=(255, 255, 255), width=2)
        elif n.startswith("Arrive_"):
            fx, fz = e["face"]
            ln = math.hypot(fx, fz) or 1
            fx, fz = fx / ln, fz / ln
            dr.line((px, pz, px + fx * 28, pz + fz * 28), fill=BLUE, width=3)
            dr.ellipse((px - 4, pz - 4, px + 4, pz + 4), fill=BLUE)
            text(dr, (px + fx * 58, pz + fz * 58), n[7:], f_link, BLUE)
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
    span = pv["x1"] - pv["x0"]
    bar = 1 if span < 10 else 2 if span < 18 else 5 if span < 45 else 10
    bx, by = 24, pv["H"] - 26
    n_seg = 4 if bar < 5 else 2
    for i in range(n_seg):
        x0 = bx + i * bar * sx
        dr.rectangle((x0, by - 10, x0 + bar * sx, by), fill=INK if i % 2 == 0 else (255, 255, 255), outline=INK, width=2)
    text(dr, (bx + n_seg * bar * sx / 2, by - 26), f"{n_seg * bar} m", font(20, True), INK, halo=3)
    nx, ny = pv["W"] - 34, 44
    dr.polygon([(nx, ny - 24), (nx + 12, ny + 8), (nx - 12, ny + 8)], fill=INK)
    text(dr, (nx, ny + 26), "N", font(22, True), INK)
    if multi:
        text(dr, (pv["W"] / 2, 28), S.level_names.get(lv, f"level y {lv:g}"), font(28, True), INK)
    return im


def plan_sheet(S, renders, out):
    panels = [plan_panel(S, pv, renders / f"{S.id}_plan_{pv['key']}.png") for pv in G.plan_views(S)]
    if len(panels) == 1:
        body = panels[0]
    else:
        gap = 16
        w = sum(p.width for p in panels) + gap * (len(panels) - 1)
        body = Image.new("RGB", (w, max(p.height for p in panels)), (255, 255, 255))
        x = 0
        for p in panels:
            body.paste(p, (x, 0))
            x += p.width + gap
    if body.width > 2200:
        body = body.resize((2200, int(body.height * 2200 / body.width)), Image.LANCZOS)
    side = 640
    rows = [f"{door}  ->  {to}" for door, to in S.links.items()]
    spots = {}
    for e in S.empties:
        if e["name"].startswith("Spot_"):
            k = e["name"].split("_")[1]
            spots[k] = spots.get(k, 0) + 1
    head = 124
    nline = sum(len(textwrap.wrap(r, 50)) for r in rows) + 26
    H = max(body.height + head, head + 30 + 28 * nline)
    im = Image.new("RGB", (body.width + side, H), (255, 255, 255))
    im.paste(body, (0, head))
    dr = ImageDraw.Draw(im)
    text(dr, (16, 30), f"{S.id}  -  {S.title}", font(32, True), INK, anchor="lm", halo=0)
    text(dr, (16, 70), f"Phase {S.phase}.  {S.size}.", font(21), GREY, anchor="lm", halo=0)
    text(dr, (16, 102), "Top-down, orthographic; ceilings and anything 2.4 m above the floor left out.", font(18), GREY, anchor="lm", halo=0)
    x, y = body.width + 18, head + 6
    f, fb = font(20), font(22, True)

    def line(s, ff=f, col=INK, wrap=50):
        nonlocal y
        for part in textwrap.wrap(s, wrap) or [""]:
            dr.text((x, y), part, font=ff, fill=col)
            y += 27
    line(S.line, f, INK)
    y += 10
    line("EXITS (press F at the blue dot)", fb)
    for r in rows:
        line(r, f, BLUE)
    y += 8
    if spots:
        line("SPOTS", fb)
        line(", ".join(f"{k} x{v}" for k, v in sorted(spots.items())), f, MAGENTA)
    if S.cams:
        line(f"CAMERAS: {len(S.cams)} SecCam (yellow wedges)", fb)
    y += 8
    line("KEY", fb)
    line("orange bar: a door leaf, from its hinge (every one different)", f, ORANGE)
    line("grey bar with a red cross: a door that never opens", f, GREY)
    line("blue dot: Link_ (press F); blue tick: Arrive_, the way you face", f, BLUE)
    line("square: Spot_; green triangle: the spawn", f, MAGENTA)
    im.save(out / f"{S.id}_plan.jpg", quality=86, optimize=True)


def still(S, renders, out):
    im = Image.open(renders / f"{S.id}_still.png").convert("RGB")
    dr = ImageDraw.Draw(im)
    (pos, face, pitch) = S.still
    text(dr, (20, im.height - 28), f"{S.id}: eye height {G.EYE} m", font(28, True), INK, anchor="lm")
    im.save(out / f"{S.id}_still.jpg", quality=84, optimize=True)


# ---------------------------------------------------------------- the graph: how the rooms connect
GW, GH = 2600, 1900
POS = {   # node centres on the GW by GH canvas, by cluster
    "WAY IN": (110, 960),
    "rdwe_dining": (330, 960), "rdwe_hallway": (600, 960), "rdwe_teal": (870, 960), "rdwe_teal2": (1140, 960), "rdwe_flooded": (1410, 960),
    "rdwe_trampoline": (1680, 960), "GODS": (1880, 800), "rdwe_grocery": (2220, 960), "rdwe_finale": (2470, 1110), "ENDING": (2470, 1270),
    # the house (top left)
    "rdwe_long_table": (200, 760), "rdwe_tiny_kitchen": (110, 590), "rdwe_birthday_party": (360, 590), "rdwe_attic": (380, 420),
    "rdwe_kids_bedroom": (500, 260), "rdwe_giant_chair": (130, 420), "rdwe_upside_room": (250, 260),
    # the halls (top middle)
    "rdwe_door_hall": (730, 760), "rdwe_stretching_hall": (720, 580), "rdwe_bending_hall": (760, 410), "rdwe_stair_loop": (900, 250),
    "rdwe_tilted_hall": (1180, 160), "rdwe_three_doors": (1000, 640), "rdwe_painted_door": (1010, 470), "rdwe_anamorphic_room": (1270, 470),
    # the teal wing (bottom middle)
    "rdwe_void_room": (820, 1150), "rdwe_lights_out": (560, 1180), "rdwe_green_grid": (1130, 1150), "rdwe_ames_room": (1270, 1310),
    "rdwe_shrink_hall": (1270, 1480), "rdwe_moon_window": (1040, 1640), "rdwe_mirror_room": (760, 1560), "rdwe_dont_look": (560, 1720),
    "rdwe_waiting_room": (560, 1390), "rdwe_wrong_clock": (560, 1560 - 0), "rdwe_crossroads": (1560, 620),
    # the institution (right)
    "rdwe_changing_rooms": (1560, 1150), "rdwe_laundromat": (1800, 1150), "rdwe_motel_room": (2040, 1150), "rdwe_office_night": (2040, 1330),
    "rdwe_elevator_lobby": (1830, 460), "rdwe_map_room": (2120, 330), "rdwe_vending_room": (2160, 620), "rdwe_melting_library": (2380, 330),
    "rdwe_repeating_room": (2290, 160), "SECRET OPS": (2520, 60),
}
POS["rdwe_wrong_clock"] = (380, 1480)
POS["rdwe_dont_look"] = (560, 1700)
POS["rdwe_waiting_room"] = (300, 1320)
EDGE_COL = {"doors": (70, 70, 80), "stairs": (215, 110, 20), "one_way": (190, 30, 150), "hatch": (150, 100, 40), "lift": (20, 90, 200)}
FILL = {"A": (255, 238, 170), "B": (255, 200, 225), "C": (255, 255, 255)}
BW, BH = 210, 58


def _box(n):
    x, y = POS[n]
    w = BW if n not in ("WAY IN", "ENDING", "SECRET OPS", "GODS") else 180
    return x - w / 2, y - BH / 2, x + w / 2, y + BH / 2


def _anchor(a, b):
    x0, y0, x1, y1 = _box(a)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ox, oy = POS[b]
    dx, dy = ox - cx, oy - cy
    if abs(dx) * (y1 - y0) > abs(dy) * (x1 - x0):
        t = (x1 - cx) / abs(dx) if dx else 0
    else:
        t = (y1 - cy) / abs(dy) if dy else 0
    return cx + dx * t, cy + dy * t


def _arrow(dr, p, q, col, at=0.62):
    mx, my = p[0] + (q[0] - p[0]) * at, p[1] + (q[1] - p[1]) * at
    ang = math.atan2(q[1] - p[1], q[0] - p[0])
    dr.polygon([(mx + 18 * math.cos(ang), my + 18 * math.sin(ang)), (mx + 13 * math.cos(ang + 2.5), my + 13 * math.sin(ang + 2.5)),
                (mx + 13 * math.cos(ang - 2.5), my + 13 * math.sin(ang - 2.5))], fill=col)


def graph(out, ids):
    im = Image.new("RGB", (GW, GH), (250, 250, 247))
    dr = ImageDraw.Draw(im)
    built = set(ids)
    for (a, da), (b, db), kind, note in G.PAIRS:
        if a not in built or b not in built:
            continue
        p, q = _anchor(a, b), _anchor(b, a)
        col = EDGE_COL[kind]
        spine = kind == "one_way" or (a in G.PHASE_A and b in G.PHASE_A)
        dr.line((p, q), fill=col, width=6 if spine else 3)
        if kind == "one_way":
            _arrow(dr, p, q, col)
    outs = [("rdwe_dining", "WAY IN", "doors", True), ("rdwe_finale", "ENDING", "one_way", False), ("rdwe_repeating_room", "SECRET OPS", "doors", False),
            ("rdwe_trampoline", "GODS", "doors", False), ("GODS", "rdwe_grocery", "one_way", False)]
    for a, b, kind, rev in outs:
        if (a not in built and a in POS and a.startswith("rdwe")) or (b.startswith("rdwe") and b not in built):
            continue
        p, q = _anchor(a, b), _anchor(b, a)
        col = (120, 150, 200) if kind == "doors" else EDGE_COL["one_way"]
        dr.line((p, q), fill=col, width=4)
        if kind == "one_way" or rev:
            _arrow(dr, q, p, col) if rev else _arrow(dr, p, q, col)
    for sid, door in G.SELF:                                 # the rooms that loop on themselves
        if sid in built:
            x0, y0, x1, y1 = _box(sid)
            dr.arc((x1 - 30, y0 - 34, x1 + 24, y0 + 14), 180, 90, fill=EDGE_COL["one_way"], width=4)
    fb, fs = font(21, True), font(16)
    for n in POS:
        if n.startswith("rdwe") and n not in built:
            continue
        x0, y0, x1, y1 = _box(n)
        if n.startswith("rdwe"):
            S = G.build(n)
            dr.rounded_rectangle((x0, y0, x1, y1), 12, fill=FILL[S.phase], outline=INK, width=3)
            text(dr, ((x0 + x1) / 2, (y0 + y1) / 2 - 8), short(n), fb, INK, halo=0)
            text(dr, ((x0 + x1) / 2, (y0 + y1) / 2 + 15), f"{len(S.links)} exits", fs, GREY, halo=0)
        else:
            dr.rounded_rectangle((x0, y0, x1, y1), 12, fill=(225, 235, 250) if n != "GODS" else (235, 235, 235), outline=GREY, width=3)
            lab = {"WAY IN": "WAY IN\nforest house, gate", "ENDING": "THE ENDING\ngrocery main floor", "SECRET OPS": "SECRET OPS\nhidden entry",
                   "GODS": "6 GOD ROOMS\nreserved (elsewhere)"}[n]
            text(dr, ((x0 + x1) / 2, (y0 + y1) / 2), lab, font(17, True), INK, halo=0)
    text(dr, (330, 860), "THE HOUSE", font(30, True), GREY, halo=0)
    text(dr, (900, 860), "THE HALLS", font(30, True), GREY, halo=0)
    text(dr, (1000, 1790), "THE TEAL WING", font(30, True), GREY, halo=0)
    text(dr, (2000, 1450), "THE INSTITUTION", font(30, True), GREY, halo=0)
    text(dr, (GW / 2, GH - 66), "Right Door, Wrong Exit: how the rooms connect (a graph of connections, not of space).  Thick: the story's spine.  "
                                "Yellow: Phase A remakes; pink: Phase B set pieces; white: Phase C new rooms.", font(22), INK, halo=0)
    text(dr, (GW / 2, GH - 32), "Lines: grey doors, orange stairs, brown hatch, blue lifts, pink one way (arrow); a pink loop: the room leads "
                                "back into itself.", font(22), INK, halo=0)
    im.save(out / "graph.png", optimize=True)
    return im


# ---------------------------------------------------------------- the README and ROOMS.md
RULINGS = [
    "Ids: `rdwe_<room>` for every scene, so they never clash with the hotel's `dining` (world/dining.json) or the grocery's scenes. The six god "
    "rooms keep their own ids (their PRs); the graph reserves `rdwe_nyx` to `rdwe_thanatos` between the trampoline park and the grocery.",
    "Count: 7 remakes + 2 set pieces + 34 new rooms + 6 god rooms = 49 rooms, the \"about 50\" of docs/WORLD.md. Section 7's \"about 43 new\" "
    "is the 2 + 34 + 6 + 1 (the hide-and-seek map counted with its wings).",
    "The story stays the spine: dining > hallway > teal > teal2 > flooded > trampoline > (the god rooms) > grocery, with each room's present "
    "exit kept. Sleeping, the arch, the grate and the red glow are one way (they were one-way moments in the clips); the green stairs and "
    "the well go both ways. The grocery's EXIT is the loop back to the dining room, as in the game today.",
    "The finale is entered through the grocery's locked entrance doors once every room is done (the doors behind you in the clip). Its only way "
    "out, `win`, opens when every camera is off and leads to grocery.main_floor: the manifest's `rdwe.finale>grocery`, the one ending. That "
    "is the only exit from the set besides the Secret Operations door; everywhere else, every room can reach every other (gated).",
    "New exits on the remakes, for multi-choice: the dining room's pantry; three of the hallway's side doors (the other six never open); the "
    "teal room's black doorway; teal2's peeled wallpaper; a frame in the flooded corridor; a padded vent in the trampoline park; the grocery's "
    "stockroom. Each remake also has its present exit unchanged.",
    "The red door in the flooded corridor still never opens (it is the lure); the vending room's EXIT door and the hallway's and the hall of "
    "doors' wrong doors are leaves with `opens: never`.",
    "Every door is different: each leaf carries `look` (a form, a finish and a handle; the story doors have their own words) and a width and "
    "height from a small set; the gate fails on two leaves with the same look. Exits that are not doors (the couch, the grate, the red glow, "
    "the attic hatch) are a Link_ alone.",
    "The repeating room's north door (`again`) arrives through its own south door, so you are back in the same room; the stair loop's top door "
    "arrives at the foot of its own stairs. Both are links inside one scene (SELF).",
    "The door seen from one angle is a lilac door at the end of a 2 m recess on the repeating room's east wall, hidden behind a free-standing "
    "baffle; Spot_view_1 marks the one place it shows from. Its link `secret_ops` is the manifest's `rdwe.repeating_room>secret_ops`.",
    "The finale's map is 48 m by 44 m: a hall and four wings (offices, a house, a server room, aisles), Spot_computer x4 (one a wing), ten "
    "SecCam_ (the exporter now writes cameras), Spot_hide x12, Spot_agent x6 at the vents (the late swarm), Spot_seeker x1, and the server "
    "room as Zone_restricted.",
    "Psychedelic in greybox means saturated flat colours per room (cream and shag green, teal, orange, tile white, padded orange, loud pinks "
    "and acids for the new rooms) and the remakes at 1.2x to 3x their old size, with distorted key objects (the 4.4 m dining table, the 5.6 m "
    "sofa). The look itself is the dressing pass.",
    "The trampoline park is built once, 30 m by 50 m; the page still wraps you to make it go on forever. The beds are art with a Zone_trigger "
    "over them, so the page can bounce you.",
]
QUESTIONS = [
    "Which Phase C rooms should be dressed first? My pick for a first five: the hall of doors, the Ames room, the moon in the window, the "
    "mirror room and the elevator lobby (one of each kind of trick). See ROOMS.md.",
    "The god rooms: should they sit between the trampoline park and the grocery (as the graph reserves), or hang off one room as a wing?",
    "The finale is entered from the grocery's entrance once every room is done. Is \"every room\" right, or a number of rooms (say 20)?",
    "Sleeping, the arch, the grate and the red glow are one way. Should any of them go back (for co-op friends who join late)?",
    "The repeating room is reached by lift 3 of the elevator lobby or through the melting library. Deep enough, or should it be further in?",
    "The hallway keeps six doors that never open. Should some of them open later (as gates for the room mini-games)?",
]
NOTES_COORD = [
    "Nothing is wired: no manifest change, and `games/rdwe/` is untouched. How a Blender room loads in the RDWE engine is still the "
    "coordinator's to design (section 7); these files are in the same format as everything else. The greybox GLBs are in `glb/` here, not in "
    "world/.",
    "`world/rdwe_*.json`: 43 layout files. `node tools/worlddoc.mjs check` gives 0 errors on each; the warnings say a scene or a link is new.",
    "The manifest's `rdwe.finale>grocery` names `from: {room: \"grocery\"}`; the greybox puts that ending on `rdwe_finale.win`. The grocery's "
    "own way on is `rdwe_grocery.entrance` (to the finale) and `exit` (the loop).",
    "export_scene.py now writes `SecCam_<nn>` empties to `cameras` in world/L1.json's shape (a separate commit); index.html's aimFeed can "
    "read them as they are.",
    "Door leaves carry `exit` (their link's door id), `look`, and either `opens: never` or `arrival_of: <scene>.<door>` (the arrival side of a "
    "one-way link, which does not open back). `opens_when` marks the finale's two locked doors.",
    "The god rooms' doors are reserved: `rdwe_trampoline.gods` (out) and `rdwe_grocery.gods` (in). Their PRs decide their own order.",
]


def scene_table(ids, docs):
    L = ["| Scene | Phase | Size | Exits (door: where it goes) | Colliders, doors, spots |", "|---|---|---|---|---|"]
    for sid in ids:
        S = G.build(sid)
        d = docs.get(sid, {})
        spots = {}
        for sp in d.get("spots", []):
            spots[sp["kind"]] = spots.get(sp["kind"], 0) + 1
        sp = ", ".join(f"{k} x{v}" for k, v in sorted(spots.items())) or "none"
        links = "; ".join(f"`{k}`: {v}" for k, v in S.links.items())
        cam = f", {len(d.get('cameras', []))} cameras" if d.get("cameras") else ""
        L.append(f"| `{sid}` | {S.phase} | {S.size} | {links} | {len(d.get('colliders', []))} colliders, {len(d.get('doors', []))} doors{cam}; "
                 f"spots: {sp} |")
    return L


def adjacency(ids):
    built = set(ids)
    out = {s: [] for s in ids}
    for (a, da), (b, db), kind, note in G.PAIRS:
        if a in built and b in built:
            out[a].append(f"{da} > {short(b)}" + (" (one way)" if kind == "one_way" else ""))
            if kind == "one_way":
                out[b].append(f"{db} < {short(a)} (arrival)")
            else:
                out[b].append(f"{db} > {short(a)}")
    for (s, d), txt in G.SELF.items():
        if s in built:
            out[s].append(f"{d} > itself")
    for (s, d), (k, lid, note) in G.OUTSIDE.items():
        if s in built:
            out[s].append(f"{d} > {note.split(':')[0]}")
    return [f"- **{short(s)}**: " + "; ".join(v) for s, v in out.items()]


def readme(out, docs, ids):
    L = ["# Right Door, Wrong Exit greybox (docs/BLENDER_AREAS.md, section 7, step 1)", "",
         "Plain boxes, to scale, for the Right Door, Wrong Exit rooms: the seven that exist remade larger and psychedelic (Phase A), the set pieces "
         "(Phase B: the finale's hide-and-seek map; the repeating room with the door seen from one angle) and 34 proposed new rooms, one minimal "
         "greybox each (Phase C, listed one line a room in `ROOMS.md`). Nothing is dressed and nothing is wired.", "",
         "- Built by `tools/blender/build_rdwe_greybox.py` on the rented box: it writes `world/<scene>.json` through `tools/blender/export_scene.py`, "
         "the GLB, the plans and the stills. These sheets come from `tools/blender/rdwe_greybox_sheets.py`.",
         "- `python tools/blender/build_rdwe_greybox.py --check .` runs the gates on the committed files: links meet on both sides (or are one way, "
         "or loop, or leave the set on purpose), every room is reachable and can get back (no true exit), no colliders overlap, every link, arrival, "
         "spot and spawn has clearance and a floor, steps rise at most 0.27 m, corridors are 1.6 m or wider, each room has the spots it needs, every "
         "door is different and every exit has its one Link_.",
         "- `CHECKS.txt`: the gates and `node tools/worlddoc.mjs check` on every file.",
         "- `graph.png`: how the rooms connect. For each scene, `<scene>_plan.jpg` (top-down: doors, links, spots and cameras labelled, a scale bar) "
         "and `<scene>_still.jpg` (eye height, 1.55 m).", "",
         "![how the rooms connect](graph.png)", "",
         "## Rulings (mine, under the owner's \"go with your judgment\")", ""] + [f"{i}. {r}" for i, r in enumerate(RULINGS, 1)]
    L += ["", "## Scenes", ""] + scene_table(ids, docs)
    L += ["", "## How the rooms connect", "",
          "Each line is a room and its exits (`door > where it goes`). Pressing F at one side's `Link_<door>` puts you at the other side's "
          "`Arrive_<door>`, facing its -Y axis. A one-way link's far side is an arrival door that does not open back.", ""] + adjacency(ids)
    L += ["", "### Every link", "", "| From | To | Kind | Note |", "|---|---|---|---|"]
    built = set(ids)
    for (a, da), (b, db), kind, note in G.PAIRS:
        if a in built and b in built:
            L.append(f"| `{a}.{da}` | `{b}.{db}` | {kind} | {note} |")
    L += ["", "Links inside one room, and links that leave the set:", ""]
    for (s, d), note in G.SELF.items():
        if s in built:
            L.append(f"- `{s}.{d}` (loop): {note}")
    for (s, d), (k, lid, note) in G.OUTSIDE.items():
        if s in built:
            L.append(f"- `{s}.{d}` ({k}): {note}. Manifest: {lid}")
    L += ["", "## Notes for the coordinator", ""] + [f"- {n}" for n in NOTES_COORD]
    L += ["", "## Open questions for the owner", ""] + [f"{i}. {q}" for i, q in enumerate(QUESTIONS, 1)]
    L += ["", "## Not done here", "",
          "- Dressing, light baking and review renders (step 2), one room at a time, for the rooms the owner picks.",
          "- The page-side tricks (the arch growing, the moving statue, the lap counter, the moon's scale, the cameras going off) are the "
          "coordinator's code; the greybox marks where each goes with a Spot_ and its `what`.",
          "- The Blender-side layout check (`tools/blender/check_layout.py`) needs each scene's .blend; the greybox builds into an empty file per "
          "scene and keeps no .blend.", ""]
    (out / "README.md").write_text("\n".join(L), encoding="utf-8")


KIND_OF = {"house": "the house", "halls": "the halls", "teal": "the teal wing", "inst": "the institution"}


def rooms_md(out):
    L = ["# Right Door, Wrong Exit: the proposed new rooms (Phase C)", "",
         "One line a room, in list order. Each has a minimal greybox (a shell, its doors and links, one or two key boxes for its trick, and the "
         "trick's Spot_), none dressed. The owner picks which rooms to dress. Super Liminal style, after docs/WORLD.md: object distortion and "
         "off-looking objects, perspective shifting, distorted halls, multi-choice navigation, psychological puzzles, environmental storytelling.",
         "", "| # | Room | Where | Size | The room, in one line |", "|---|---|---|---|---|"]
    for i, sid in enumerate(G.PHASE_C, 1):
        S = G.build(sid)
        L.append(f"| {i} | `{sid}` | {KIND_OF.get(S.cluster, S.cluster)} | {S.size} | {S.line} |")
    L += ["", "Reserved, built elsewhere (not greyboxed here): the six god rooms, `rdwe_nyx`, `rdwe_selene`, `rdwe_hypnos`, `rdwe_morpheus`, "
          "`rdwe_oneiros`, `rdwe_thanatos`, between the trampoline park and the grocery.", "",
          "With the 7 remakes and the 2 set pieces that makes 49 rooms.", ""]
    (out / "ROOMS.md").write_text("\n".join(L), encoding="utf-8")


# ---------------------------------------------------------------- the owner's phone sheets
def _sheet(blocks, path, W=1080):
    H = 40
    for b in blocks:
        if b[0] == "t":
            H += b[2].size + 12
        elif b[0] == "gap":
            H += b[1]
        elif b[0] == "img":
            H += int(b[1].height * (W - 40) / b[1].width) + 10
        elif b[0] == "grid":
            H += ((len(b[1]) + 1) // 2) * (292 + 96)
        elif b[0] == "row":
            H += max(b[1].height, 40 + 34 * len(b[3])) + 24
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
        elif b[0] == "grid":
            for i, (s, g, cap) in enumerate(b[1]):
                gx, gy = 13 + (i % 2) * 534, y + (i // 2) * 388
                im.paste(g, (gx, gy))
                dr.text((gx + 4, gy + 296), s, font=font(28, True), fill=INK)
                for k, part in enumerate(textwrap.wrap(cap, 34)[:2]):
                    dr.text((gx + 4, gy + 332 + k * 26), part, font=font(22), fill=GREY)
            y += ((len(b[1]) + 1) // 2) * 388
        elif b[0] == "row":
            th, title, lines = b[1], b[2], b[3]
            im.paste(th, (20, y))
            dr.text((20 + th.width + 18, y), title, font=font(30, True), fill=INK)
            for k, part in enumerate(lines):
                dr.text((20 + th.width + 18, y + 40 + k * 34), part, font=font(26), fill=GREY if k else INK)
            y += max(th.height, 40 + 34 * len(lines)) + 24
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)


def owner_sheet(path, out, renders):
    f_t, f_h, f_b = font(50, True), font(38, True), font(30)
    blocks = []

    def para(s, f, col=INK, wrap=50, gap=10):
        for p in textwrap.wrap(s, wrap):
            blocks.append(("t", p, f, col))
        blocks.append(("gap", gap))
    para("Right Door, Wrong Exit greybox", f_t, wrap=30)
    para("The 7 rooms remade larger, the finale's hide-and-seek map, the room that repeats, and 34 new rooms as plain boxes, all joined. "
         "Nothing dressed, nothing wired yet.", f_b, GREY)
    para("How the rooms connect", f_h)
    blocks.append(("img", Image.open(out / "graph.png")))
    para("Thick line: the story. Pink arrow: one way. Pink loop: the room leads back into itself. Yellow: the remakes; pink: the set pieces.",
         font(26), GREY, wrap=60)
    para("Phase A: the seven rooms, remade", f_h)
    grid = []
    for s in G.PHASE_A:
        S = G.build(s)
        grid.append((short(s), Image.open(renders / f"{s}_still.png").convert("RGB").resize((520, 292), Image.LANCZOS), S.size.split("(")[0]))
    blocks.append(("grid", grid))
    para("Phase B: the set pieces", f_h)
    grid = []
    for s in G.PHASE_B:
        S = G.build(s)
        grid.append((short(s), Image.open(renders / f"{s}_still.png").convert("RGB").resize((520, 292), Image.LANCZOS), S.title.split(":")[0]))
    blocks.append(("grid", grid))
    for s in G.PHASE_B:
        pl = Image.open(out / f"{s}_plan.jpg").convert("RGB")
        blocks.append(("img", pl))
    para("Questions for you", f_h)
    for i, q in enumerate(QUESTIONS, 1):
        para(f"{i}. {q}", f_b, INK, wrap=52, gap=16)
    para("Silence means I carry on: the rooms you pick get dressed, one at a time.", f_b, GREY)
    _sheet(blocks, path)


def owner_rooms(path, out, renders):
    f_t, f_h, f_b = font(50, True), font(36, True), font(30)
    blocks = []

    def para(s, f, col=INK, wrap=50, gap=10):
        for p in textwrap.wrap(s, wrap):
            blocks.append(("t", p, f, col))
        blocks.append(("gap", gap))
    para("RDWE: 34 new rooms to pick from", f_t, wrap=30)
    para("One line and one greybox each. Tell me which to dress (a number is enough). My first five: 8, 19, 21, 22, 31.", f_b, GREY)
    for i, sid in enumerate(G.PHASE_C, 1):
        S = G.build(sid)
        im = Image.open(renders / f"{sid}_still.png").convert("RGB").resize((300, 169), Image.LANCZOS)
        lines = textwrap.wrap(S.line, 40)[:4]
        blocks.append(("row", im, f"{i}. {short(sid)}", lines))
    para("Reserved, built elsewhere: the six god rooms (Nyx, Selene, Hypnos, Morpheus, Oneiros, Thanatos).", f_b, GREY)
    _sheet(blocks, path)


def main(a):
    renders = Path(a[a.index("--renders") + 1])
    out = Path(a[a.index("--out") + 1]) if "--out" in a else G.ROOT / "docs/renders/rdwe_greybox"
    ph = a[a.index("--phase") + 1] if "--phase" in a else "ABC"
    ids = G.phase_ids(ph)
    out.mkdir(parents=True, exist_ok=True)
    docs = {}
    for sid in ids:
        f = G.out_path(renders, sid)
        if f.exists():
            docs[sid] = json.loads(f.read_text())
    for sid in ids:
        S = G.build(sid)
        plan_sheet(S, renders / "renders", out)
        still(S, renders / "renders", out)
    graph(out, ids)
    readme(out, docs, ids)
    if "C" in ph:
        rooms_md(out)
    if "--owner" in a:
        owner_sheet(a[a.index("--owner") + 1], out, renders / "renders")
    if "--owner-rooms" in a:
        owner_rooms(a[a.index("--owner-rooms") + 1], out, renders / "renders")
    print("sheets written to", out)


if __name__ == "__main__":
    main(sys.argv[1:])
