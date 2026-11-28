"""The Secret Operations greybox's review sheets, drawn over the Blender renders of tools/blender/build_secretops_greybox.py (no Blender here;
Pillow only). It follows tools/blender/overworld_greybox_sheets.py.

    python tools/blender/secretops_greybox_sheets.py --renders <build out dir> [--out docs/renders/secretops_greybox] [--owner <png>]
                                                     [--checks <CHECKS.txt>]

For every scene: <out>/<scene>_plan.jpg (the orthographic plan with its labels, doors, links, keycards, cameras and what they see, agents and
their beats, cover, ammo, loot, breakers, a scale bar and north) and <out>/<scene>_still.jpg (the eye-height still). Then <out>/overview.png (the
graph: how the scenes join each other and the world, with the keycard each door asks for) and <out>/README.md. --owner also writes a one-page
sheet for a phone. A scene with no Blender plan render is drawn from the model's boxes instead (the same top-down view). Labels come from the
same model the build used, so they sit where the boxes are. Images are written fresh, with no metadata.
"""
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_secretops_greybox as G  # noqa: E402

FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/Library/Fonts")]


def font(size, bold=False):
    names = (["arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf", "Arial.ttf"])
    for d in FONT_DIRS:
        for n in names:
            if (d / n).exists():
                return ImageFont.truetype(str(d / n), size)
    return ImageFont.load_default()


INK, BLUE, RED, GREY, WHITE = (25, 25, 30), (20, 90, 200), (205, 30, 30), (110, 110, 115), (255, 255, 255)
SPOT = {"agent": ((205, 30, 30), "A"), "ammo": ((230, 175, 0), "a"), "loot": ((20, 150, 60), "L"), "breaker": ((235, 110, 0), "B"),
        "reader": ((150, 0, 0), "K"), "puzzle": ((130, 60, 200), "P"), "filed": ((90, 90, 95), "F"), "chair": ((20, 20, 20), "C"),
        "admin": ((0, 120, 160), "AD"), "core": ((200, 0, 120), "CORE"), "locker": ((40, 100, 150), "Lk")}
TIER = {1: (215, 140, 0), 2: (215, 60, 0), 3: (175, 0, 60)}
AREA_ORDER = ["service_entry", "hidden_entry", "b2_entry", "checkpoint_1", "corridors_a", "labs_a", "breaker_room", "checkpoint_2",
              "corridors_b", "labs_b", "checkpoint_3", "registrar_hall", "control_room"]


def text(dr, xy, s, f, fill=INK, anchor="mm", halo=3):
    dr.text(xy, s, font=f, fill=fill, anchor=anchor, stroke_width=halo, stroke_fill=WHITE, align="center")


def dashed(dr, pts, col, dash=12, w=3, closed=False):
    pts = list(pts) + ([pts[0]] if closed else [])
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        ln = math.hypot(bx - ax, by - ay)
        n = max(1, int(ln / dash))
        for i in range(0, n, 2):
            t0, t1 = i / n, min(1, (i + 1) / n)
            dr.line((ax + (bx - ax) * t0, ay + (by - ay) * t0, ax + (bx - ax) * t1, ay + (by - ay) * t1), fill=col, width=w)


def raster(S, pv):
    """The plan from the model's boxes (when there is no Blender render): each box's top, the higher drawn over the lower, shaded by height."""
    im = Image.new("RGB", (pv["W"], pv["H"]), (246, 246, 246))
    dr = ImageDraw.Draw(im)
    sx = pv["W"] / (pv["x1"] - pv["x0"])
    bs = [b for b in S.boxes if b["art"] and not G.plan_hidden(S, b, 0.0)]
    for b in sorted(bs, key=lambda b: b["max"][1]):
        c = G.MATS[b["mat"]]
        k = 0.75 + 0.25 * min(1.0, max(0.0, (b["max"][1] + 0.3) / 3.0))
        col = tuple(int(min(1.0, v ** (1 / 2.2) * k) * 255) for v in c)
        x0, x1 = (b["min"][0] - pv["x0"]) * sx, (b["max"][0] - pv["x0"]) * sx
        z0, z1 = (b["min"][2] - pv["z0"]) * sx, (b["max"][2] - pv["z0"]) * sx
        dr.rectangle((x0, z0, x1, z1), fill=col, outline=(70, 70, 70) if b["max"][1] > 0.05 else None)
    return im


def plan_panel(S, pv, raw):
    if raw and Path(raw).exists():
        im = Image.open(raw).convert("RGB").resize((pv["W"], pv["H"]))
    else:
        im = raster(S, pv)
    sx = pv["W"] / (pv["x1"] - pv["x0"])
    P = lambda x, z: ((x - pv["x0"]) * sx, (z - pv["z0"]) * sx)
    dr = ImageDraw.Draw(im, "RGBA")
    f_room, f_link, f_spot, f_note = font(30, True), font(21, True), font(17, True), font(19)
    # zones
    for b in S.boxes:
        if b.get("zone") in ("water", "hazard"):
            a, c = P(b["min"][0], b["min"][2]), P(b["max"][0], b["max"][2])
            col = (30, 120, 220) if b["zone"] == "water" else (220, 0, 0)
            dr.rectangle((a[0], a[1], c[0], c[1]), outline=col + (255,), width=4)
        elif b.get("zone") == "trigger":
            a, c = P(b["min"][0], b["min"][2]), P(b["max"][0], b["max"][2])
            dashed(dr, [(a[0], a[1]), (c[0], a[1]), (c[0], c[1]), (a[0], c[1])], (130, 60, 200, 255), w=2, closed=True)
    # cameras: a wedge of what each sees (its pan), then the camera
    for c in S.cams:
        x, _, z = c["pos"]
        yaw = math.atan2(c["face"][0], c["face"][1])
        amp = math.radians(c["props"]["pan"]["amplitude_deg"] + 25)
        rng = 7.0
        pts = [P(x, z)] + [P(x + rng * math.sin(yaw + t), z + rng * math.cos(yaw + t)) for t in [-amp + k * amp / 6 for k in range(13)]]
        dr.polygon(pts, fill=(230, 40, 40, 24))
        px, pz = P(x, z)
        dr.ellipse((px - 9, pz - 9, px + 9, pz + 9), fill=(230, 40, 40, 255), outline=WHITE, width=2)
        ex, ez = P(x + 1.0 * math.sin(yaw), z + 1.0 * math.cos(yaw))
        dr.line((px, pz, ex, ez), fill=(230, 40, 40, 255), width=4)
        text(dr, (px, pz - 20), c["name"][7:] + " " + c["props"]["circuit"], font(14, True), fill=(170, 0, 0), halo=2)
    # patrol routes
    for route, names in S.patrols.items():
        pts = [P(e["pos"][0], e["pos"][2]) for n in names for e in S.empties if e["name"] == n]
        dashed(dr, pts, (205, 30, 30, 220), w=3, closed=len(pts) > 2)
        for p in pts:
            dr.ellipse((p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5), fill=(205, 30, 30, 255))
        if pts:
            text(dr, (pts[0][0], pts[0][1] + 16), f"beat {route}", font(15, True), fill=(170, 0, 0), halo=2)
    # doors
    for d in S.doors:
        hx, _, hz = d["hinge"]
        yaw = d["yaw"]
        w = d["props"]["width"]
        a = P(hx, hz)
        b = P(hx + w * math.cos(yaw), hz - w * math.sin(yaw))
        kc = d["props"].get("keycard_tier")
        dr.line((a[0], a[1], b[0], b[1]), fill=(TIER[kc] if kc else (150, 80, 20)) + (255,), width=7)
    # space labels and notes
    for lb in S.labels:
        x, y = P(lb["x"], lb["z"])
        if lb["kind"] == "room":
            text(dr, (x, y), lb["text"], f_room, fill=(30, 30, 40))
        else:
            text(dr, (x, y), lb["text"], f_note, fill=(60, 60, 140))
    # links: where F is, an arrow the way you arrive, where it goes and the card it needs
    for e in S.empties:
        if not e["name"].startswith("Link_"):
            continue
        did = e["name"][5:]
        arr = next(a for a in S.empties if a["name"] == "Arrive_" + did)
        to, fore, card = S.links[did]
        p, q = P(e["pos"][0], e["pos"][2]), P(arr["pos"][0], arr["pos"][2])
        fx, fz = arr["face"]
        tip = P(arr["pos"][0] + 1.6 * fx, arr["pos"][2] + 1.6 * fz)
        dr.ellipse((p[0] - 11, p[1] - 11, p[0] + 11, p[1] + 11), fill=BLUE + (255,), outline=WHITE, width=3)
        dr.line((q[0], q[1], tip[0], tip[1]), fill=BLUE + (255,), width=5)
        ang = math.atan2(tip[1] - q[1], tip[0] - q[0])
        dr.polygon([tip, (tip[0] - 16 * math.cos(ang - 0.45), tip[1] - 16 * math.sin(ang - 0.45)),
                    (tip[0] - 16 * math.cos(ang + 0.45), tip[1] - 16 * math.sin(ang + 0.45))], fill=BLUE + (255,))
        side = did.split("_")[-1] if did.split("_")[-1] in ("west", "east") else ""
        lab = f"to {to}" + (f" ({side})" if side else "") + (f"  [card {card}]" if card else "")
        lx = min(max(p[0], 160), pv["W"] - 160)
        ly = p[1] + (-34 if fz > 0 else 34) if abs(fz) > 0.5 else p[1] - 30
        text(dr, (lx, min(max(ly, 18), pv["H"] - 18)), lab, f_link, fill=TIER[card] if card else BLUE)
    # spots
    for e in S.empties:
        if not e["name"].startswith("Spot_"):
            continue
        kind = e["name"].split("_")[1]
        if kind == "patrol":
            continue
        col, ch = SPOT.get(kind, ((60, 60, 60), kind[:2]))
        x, y = P(e["pos"][0], e["pos"][2])
        r = 13 if len(ch) < 3 else 20
        if kind == "agent":
            dr.polygon([(x, y - 16), (x - 14, y + 11), (x + 14, y + 11)], fill=col + (255,), outline=WHITE)
        else:
            dr.ellipse((x - r, y - r, x + r, y + r), fill=col + (255,), outline=WHITE, width=2)
        text(dr, (x, y + (3 if kind == "agent" else 0)), ch, font(14 if len(ch) < 3 else 13, True), fill=WHITE, halo=0)
        if kind == "breaker":
            text(dr, (x, y + 26), e["props"]["circuit"], f_spot, fill=(200, 90, 0))
    # cover outlines: full cover heavy, half cover light
    for b in S.boxes:
        if "cover" in b["tags"] and not b["name"].startswith("Rack_"):
            a, c = P(b["min"][0], b["min"][2]), P(b["max"][0], b["max"][2])
            dr.rectangle((a[0], a[1], c[0], c[1]), outline=(0, 0, 0, 255) if "cover_full" in b["tags"] else (90, 90, 90, 255),
                         width=4 if "cover_full" in b["tags"] else 2)
    # scale bar and north
    m = 5 if pv["x1"] - pv["x0"] > 30 else 2
    x0, y0 = 30, pv["H"] - 34
    for k in range(2):
        dr.rectangle((x0 + k * m * sx, y0, x0 + (k + 1) * m * sx, y0 + 12), fill=(INK if k % 2 == 0 else WHITE) + (255,), outline=INK)
    text(dr, (x0 + m * sx, y0 - 16), f"{2 * m} m", font(20, True), halo=2)
    nx_, ny_ = pv["W"] - 44, 50
    dr.polygon([(nx_, ny_ - 30), (nx_ - 13, ny_ + 4), (nx_ + 13, ny_ + 4)], fill=INK)
    text(dr, (nx_, ny_ + 22), "N", font(22, True))
    return im


LEGEND = [("agent", "agent spawn (beat: dashed)"), ("ammo", "ammo"), ("loot", "loot"), ("breaker", "breaker"), ("reader", "keycard reader"),
          ("puzzle", "puzzle"), ("filed", "phase 2 filing spot")]


def legend(w):
    im = Image.new("RGB", (w, 120), WHITE)
    dr = ImageDraw.Draw(im)
    f = font(19)
    x, y = 20, 22
    for kind, what in LEGEND:
        col, ch = SPOT[kind]
        if kind == "agent":
            dr.polygon([(x + 12, y - 12), (x, y + 10), (x + 24, y + 10)], fill=col)
        else:
            dr.ellipse((x, y - 12, x + 24, y + 12), fill=col)
        dr.text((x + 32, y), what, font=f, fill=INK, anchor="lm")
        x += 50 + int(dr.textlength(what, font=f))
        if x > w - 260:
            x, y = 20, y + 36
    items = [((20, 90, 200), "link: F here, arrow = where you stand coming in"), ((230, 40, 40), "camera + what it sweeps (circuit)"),
             ((215, 60, 0), "keycard door (card tier)"), ((0, 0, 0), "full cover (heavy) / half cover (light)")]
    x, y = 20, y + 38
    for col, what in items:
        dr.rectangle((x, y - 8, x + 24, y + 8), fill=col)
        dr.text((x + 32, y), what, font=f, fill=INK, anchor="lm")
        x += 50 + int(dr.textlength(what, font=f))
        if x > w - 300:
            x, y = 20, y + 34
    return im.crop((0, 0, w, y + 24))


def plan_sheet(S, renders, out):
    pv = G.plan_views(S)[0]
    raw = Path(renders) / "renders" / f"{S.id}_plan_{pv['key']}.png" if renders else None
    panel = plan_panel(S, pv, raw)
    W = max(panel.width, 1400)
    head = Image.new("RGB", (W, 120), WHITE)
    dr = ImageDraw.Draw(head)
    dr.text((24, 18), f"{S.id}", font=font(42, True), fill=INK)
    dr.text((24, 72), S.title, font=font(24), fill=GREY)
    lg = legend(W)
    words, line, lines = S.size.split(), "", []
    for w_ in words:
        if len(line) + len(w_) > 110:
            lines.append(line)
            line = w_
        else:
            line = (line + " " + w_).strip()
    lines.append(line)
    sheet = Image.new("RGB", (W, head.height + panel.height + 24 + 30 * len(lines) + lg.height + 10), WHITE)
    sheet.paste(head, (0, 0))
    sheet.paste(panel, ((W - panel.width) // 2, head.height))
    dr = ImageDraw.Draw(sheet)
    for k, l in enumerate(lines):
        dr.text((24, head.height + panel.height + 12 + 30 * k), l, font=font(21), fill=INK)
    sheet.paste(lg, (0, head.height + panel.height + 24 + 30 * len(lines)))
    sheet.save(out / f"{S.id}_plan.jpg", quality=88)
    return sheet


def still(S, renders, out):
    raw = Path(renders) / "renders" / f"{S.id}_still.png" if renders else None
    if not raw or not raw.exists():
        return None
    im = Image.open(raw).convert("RGB")
    dr = ImageDraw.Draw(im)
    text(dr, (24, 30), f"{S.id}: eye height {G.EYE} m", font(30, True), anchor="lm")
    im.save(out / f"{S.id}_still.jpg", quality=88)
    return im


# ---------------------------------------------------------------- the graph
POS = {"freight": (1, 0), "pool": (0, 0), "lab": (2, 0), "rdwe": (4, 0),
       "service_entry": (0.5, 1), "b2_entry": (2, 1), "hidden_entry": (4, 1),
       "checkpoint_1": (1.25, 2), "corridors_a": (2.5, 3), "breaker_room": (4.0, 3.9), "labs_a": (0.8, 3.9),
       "checkpoint_2": (2.5, 4.8), "corridors_b": (2.5, 5.8), "labs_b": (0.8, 5.8),
       "checkpoint_3": (2.5, 6.8), "registrar_hall": (2.5, 7.8), "control_room": (2.5, 8.8)}
OUTER = {"freight": ("grocery", "freight lift", ("service_entry", "freight_lift")), "pool": ("the Intern", "pool dive", ("service_entry", "pool_dive")),
         "lab": ("laboratory", "B2 door", ("b2_entry", "laboratory")), "rdwe": ("RDWE", "repeating room", ("hidden_entry", "repeating_room"))}
NICE = {"service_entry": "service entry", "hidden_entry": "hidden entry", "b2_entry": "B2 entry", "checkpoint_1": "checkpoint 1",
        "corridors_a": "corridors A", "labs_a": "labs A", "breaker_room": "breaker room", "checkpoint_2": "checkpoint 2",
        "corridors_b": "corridors B", "labs_b": "labs B", "checkpoint_3": "checkpoint 3", "registrar_hall": "REGISTRAR HALL (boss)",
        "control_room": "control room + cell"}


def overview(path, W=1400):
    cx, cy = W / 5.2, 150
    H = int(cy * 9.6) + 160
    im = Image.new("RGB", (W, H), WHITE)
    dr = ImageDraw.Draw(im)
    pos = {k: (70 + v[0] * cx + 60, 150 + v[1] * cy) for k, v in POS.items()}
    dr.text((30, 24), "Secret Operations: how the scenes join", font=font(40, True), fill=INK)
    dr.text((30, 78), "Each line is a door, both ways. A number is the keycard tier the door asks for. Dashed: from the rest of Farway.",
            font=font(22), fill=GREY)
    for k, (a, lab, side) in OUTER.items():
        dashed(dr, [pos[k], pos[side[0]]], (120, 120, 120), w=4)
    for a, b, kind, card, note in G.PAIRS:
        pa, pb = pos[a[0]], pos[b[0]]
        col = TIER[card] if card else (70, 70, 80)
        dr.line((pa, pb), fill=col, width=9 if card else 5)
        if a[1].endswith("_west"):
            mx, my = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
            dr.text((mx, my - 4), "2 doors", font=font(20, True), fill=INK, anchor="mm", stroke_width=4, stroke_fill=WHITE)
        if card:
            mx, my = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
            dr.ellipse((mx - 21, my - 21, mx + 21, my + 21), fill=col, outline=WHITE, width=3)
            dr.text((mx, my), str(card), font=font(26, True), fill=WHITE, anchor="mm")
    for k, (a, lab, side) in OUTER.items():
        x, y = pos[k]
        dr.rounded_rectangle((x - 118, y - 36, x + 118, y + 36), 14, fill=(236, 236, 236), outline=(150, 150, 150), width=3)
        dr.text((x, y - 10), a, font=font(22, True), fill=INK, anchor="mm")
        dr.text((x, y + 16), lab, font=font(18), fill=GREY, anchor="mm")
    for sid in AREA_ORDER:
        x, y = pos[sid]
        boss = sid == "registrar_hall"
        col = (215, 240, 220) if boss else (225, 232, 245) if sid.startswith(("corr", "labs")) else (245, 230, 215) if sid.startswith("check") else (240, 240, 240)
        w = 190 if boss else 140
        dr.rounded_rectangle((x - w, y - 38, x + w, y + 38), 16, fill=col, outline=INK, width=4 if boss else 3)
        dr.text((x, y), NICE[sid], font=font(27, True), fill=INK, anchor="mm")
    y = H - 70
    for t, col in ((1, TIER[1]), (2, TIER[2]), (3, TIER[3])):
        x = 40 + (t - 1) * 300
        dr.ellipse((x, y - 18, x + 36, y + 18), fill=col)
        dr.text((x + 18, y), str(t), font=font(22, True), fill=WHITE, anchor="mm")
        dr.text((x + 48, y), f"keycard tier {t}", font=font(22), fill=INK, anchor="lm")
    im.save(path)
    return im


# ---------------------------------------------------------------- the owner's one-page sheet (a phone)
RULINGS_SHORT = [
    "13 unique scenes (3 entries, 3 checkpoints, 2 corridor and 2 lab sections, breaker room, Registrar hall, control room + cell). The "
    "reskinned chambers are the Going back in greybox's.",
    "The hidden entry skips checkpoint 1 (no card), has no cameras and leads into Corridors A.",
    "Cards: tier 1 into Corridors A, tier 2 into Corridors B (three tier-2 doors), tier 3 into the arena. A tier-3 card lies in Labs B.",
    "Arena: 40 m x 20 m panel field (200 panels, 2 m) over an 8 m pit, fixed landings at both ends, 48 racks, 12 cameras, 4 breakers.",
    "Its ceiling over the field is 50 panels the page can open on the glitched phase 3 sky (that sky is not made yet).",
]
QUESTIONS_SHORT = [
    "There is no keycard_tier_3 flag yet: add one, or let tier 3 be admin-only / the Labs B drop?",
    "Should the lab's B2 door need a keycard (tier 1), or the lab job alone?",
    "Can a filed player land in the cell during phase 2 (one Spot_filed is in it)?",
    "The arena is 7 m high (Scale says 2.8 to 3.2 m for rooms): keep it tall?",
]


def owner_sheet(path, out, docs):
    W = 1400
    ov = Image.open(out / "overview.png")
    ov = ov.resize((W, int(ov.height * W / ov.width)))
    thumbs = []
    for sid in AREA_ORDER:
        f = out / f"{sid}_plan.jpg"
        im = Image.open(f)
        tw = W // 2 - 30
        im = im.resize((tw, int(im.height * tw / im.width)))
        thumbs.append(im)
    rows = [thumbs[i:i + 2] for i in range(0, len(thumbs), 2)]
    th = sum(max(t.height for t in r) + 20 for r in rows)
    f = font(26)

    def wrap(s, width=88):
        out_, line = [], ""
        for w_ in s.split():
            if len(line) + len(w_) + 1 > width:
                out_.append(line)
                line = w_
            else:
                line = (line + " " + w_).strip()
        return out_ + [line]
    rl = [l for r in RULINGS_SHORT for l in wrap("- " + r)]
    ql = [l for r in QUESTIONS_SHORT for l in wrap("- " + r)]
    tx = 60 + 40 * (len(rl) + len(ql)) + 140
    sheet = Image.new("RGB", (W, ov.height + th + tx + 40), WHITE)
    sheet.paste(ov, (0, 0))
    dr = ImageDraw.Draw(sheet)
    y = ov.height + 10
    dr.text((30, y), "Rulings", font=font(34, True), fill=INK)
    y += 50
    for l in rl:
        dr.text((30, y), l, font=f, fill=INK)
        y += 40
    y += 20
    dr.text((30, y), "Open questions", font=font(34, True), fill=INK)
    y += 50
    for l in ql:
        dr.text((30, y), l, font=f, fill=(150, 30, 30))
        y += 40
    y += 30
    for r in rows:
        x = 20
        for t in r:
            sheet.paste(t, (x, y))
            x += t.width + 20
        y += max(t.height for t in r) + 20
    sheet.save(path)


# ---------------------------------------------------------------- README
def readme(out, docs, checks_txt):
    L = ["# Secret Operations greybox (docs/BLENDER_AREAS.md, section 8: Secret Operations, Project Never Land)", "",
         "Plain grey boxes, to scale, for the unique scenes of Secret Operations: the three entries, the three keycard checkpoints, two corridor "
         "sections and two lab sections (open-ended, more than one route each), the breaker room, the control room with its cell, and the "
         "Registrar's hall, the boss arena. There are no reference photos, so each scene is built from docs/WORLD.md's description. The "
         "reskinned Going back in chambers that the base also uses are not here: they are the Going back in greybox's. This is for review: no "
         "scene or link has been added to the manifest, and the greybox GLBs are in `glb/` here, not in `world/`.", "",
         "- Built by `tools/blender/build_secretops_greybox.py` (the method of the Overworld's greybox build: one model in plain Python, a "
         "Blender run that writes `world/<scene>.json` through `tools/blender/export_scene.py`, the GLB, the plan and the still). The labels "
         "and these sheets come from `tools/blender/secretops_greybox_sheets.py`.",
         "- `python tools/blender/build_secretops_greybox.py --check .` runs the gates on the exported files: every link has its other side and "
         "every scene is reached from each entry; no two colliders overlap; corridors and aisles are at least 1.6 m wide and clear, doorways "
         "1 m, ceilings 2.8 to 3.2 m (the dock and the arena are tall on purpose), steps 0.27 m at most; every link, arrival and spot stands "
         "on floor a walker can reach, all on one piece; the open-ended sections have at least three links and a loop; the required objects "
         "are there; the arena's floor panels tile the field exactly; every restricted scene has cameras and every camera a breaker; agents "
         "spawn away from where you arrive, and every scene with agents has cover and ammo. `--against <preview dir>` also compares the "
         "Blender export with the model's preview, to the millimetre.",
         "- `CHECKS.txt`: those gates, `node tools/worlddoc.mjs check` on every file (0 errors; the warnings say a scene or a link is new to the "
         "manifest), `node --test shared/*.test.js` and the privacy grep.",
         "- `overview.png`: how the scenes join each other and the rest of Farway, with the keycard each door asks for. For each scene, "
         "`<scene>_plan.jpg` (top-down, scale bar, labels, doors, links, keycards, cameras and their sweep, agents and their beats, cover, "
         "ammo, loot, breakers) and `<scene>_still.jpg` (eye height, 1.55 m).", "",
         "## Scenes", "", "| Scene | Size | Links (door: where it goes) | Colliders, doors, cameras, spots | Mood |", "|---|---|---|---|---|"]
    for sid in AREA_ORDER:
        S, d = G.build(sid), docs[sid]
        links = "; ".join(f"`{k}`: {v[0]}" + (f" (card {v[2]})" if v[2] else "") for k, v in S.links.items())
        nsp = {}
        for s in d["spots"]:
            nsp[s["kind"]] = nsp.get(s["kind"], 0) + 1
        spots = ", ".join(f"{k} x{v}" for k, v in sorted(nsp.items()))
        L.append(f"| `{sid}` | {S.size} | {links} | {len(d['colliders'])} colliders, {len(d['doors'])} doors, {len(d['cameras'])} cameras; "
                 f"spots: {spots} | {S.mood} |")
    L += ["", "## The graph", "",
          "Each pair is one link. Pressing F at one side's `Link_<door>` puts you at the other side's `Arrive_<door>`, facing its -Y axis. "
          "Every pair has both sides built (the gate checks it). The card is the keycard tier the door's reader asks for (its `keycard_tier` "
          "property and a `Spot_reader` beside it); 0 is none. A reader is on the side you come from going deeper; coming back the door opens "
          "from inside.", "",
          "```",
          "grocery freight lift --+",
          "Intern pool dive ------+--> service_entry --+",
          "lab B2 door -------------> b2_entry --------+--> checkpoint_1 =[1]=> corridors_a --+--> labs_a (2 doors) =[2]=> labs_b",
          "RDWE repeating room ----> hidden_entry ----(no card)----------------------------+   |                         | (2 doors)",
          "                                                          corridors_a --> breaker_room =[2]=> corridors_b <-+",
          "                                                          corridors_a --> checkpoint_2 =[2]=> corridors_b",
          "                                                                corridors_b --> checkpoint_3 =[3]=> registrar_hall --> control_room (+ cell)",
          "```", "",
          "| From | To | Connector | Card | Note |", "|---|---|---|---|---|"]
    for a, b, kind, card, note in G.PAIRS:
        L.append(f"| `{a[0]}.{a[1]}` | `{b[0]}.{b[1]}` | {kind} | {card or '-'} | {note} |")
    L += ["", "Links that leave this area (the coordinator wires the other side; nothing here edits the manifest):", "",
          "| Link | Connector | Ids | The other side |", "|---|---|---|---|"]
    for (s, dd), (kind, ids, note) in G.OUTSIDE.items():
        L.append(f"| `{s}.{dd}` | {kind} | {ids} | {note} |")
    L += ["", "The manifest's `service_entry` and `hidden_entry` (the `secret_ops` stub) have no coordinates yet, so there was nothing to keep: "
          "the arrival points above are new, and the coordinator copies them into `grocery.backhouse>secret_ops`, `intern.pool_dive>secret_ops` "
          "and `rdwe.repeating_room>secret_ops` as their `to.arrive` and `to.face`.", ""]
    L += RULINGS + QUESTIONS + NOT_DONE
    if checks_txt:
        L += ["", "## Gate output", "", "See `CHECKS.txt`."]
    (out / "README.md").write_text("\n".join(L) + "\n", encoding="utf-8")


RULINGS = ["## Rulings (my calls, the owner can change any)", "",
           "- **Scenes.** 13 unique scenes: `service_entry`, `hidden_entry`, `b2_entry`, `checkpoint_1` to `checkpoint_3`, `corridors_a`, "
           "`corridors_b`, `labs_a`, `labs_b`, `breaker_room`, `control_room` and `registrar_hall`. With the reskinned chambers that is the "
           "\"about 12 scenes plus the boss\" of docs/WORLD.md.",
           "- **Progression.** The three entries meet at checkpoint 1 (service entry and B2 entry) or skip it (the hidden entry). Tier 1 opens "
           "Corridors A; tier 2 opens Corridors B by three doors (checkpoint 2, Labs A to Labs B, the breaker room's back door); tier 3 opens "
           "the Registrar's hall. A reader is on the side you come from; coming back, doors open from inside.",
           "- **The hidden entry** is \"the one entrance with no clearance\": its maintenance door into Corridors A has no reader, so it "
           "skips checkpoint 1. It is also the base's blind spot: no cameras, no agents, two stash spots.",
           "- **The B2 entry** is a decontamination airlock and a staff locker room behind the lab's sealed door (the lab is at y 0, so the "
           "\"B2\" stairs are the link itself; the scene's floor is at y 0 like every other).",
           "- **The pool dive** arrives at the top of the pool's steps; the pool is 1.6 m deep with six 0.267 m steps and a `Zone_water`. Diving "
           "back is a link whose F side stays shut until swimming exists, as the plan says for every swimming route.",
           "- **Keycard 3** has no flag in the manifest yet (only `keycard_tier_1` and `keycard_tier_2`). The tier-3 door asks for 3 and a "
           "`Spot_loot` in Labs B's specimen room carries `keycard_tier: 3`, so the card can be found inside the base as well as bought.",
           "- **Cameras and breakers.** Every restricted scene has cameras (54 in all), each `SecCam_<nn>` an empty exported to `cameras` in "
           "world/L1.json's format (pan, tilt, zoom, loop) plus its own rig object `SecCam_<nn>_rig` to sweep and smash. Each camera is on a "
           "circuit: the breaker room's three breakers cut A (entries, checkpoint 1, Corridors A, the breaker room), B (the labs) and C "
           "(checkpoints 2 and 3, Corridors B). The arena has its own four breakers R1 to R4, one a wall, for phase 1; the control room has R5.",
           "- **export_scene.py** now writes `SecCam_<nn>` empties to `cameras` (its table promised it; no scene had any). The change is "
           "additive: a camera's custom properties go through as objects and lists. Other areas' exports are unchanged.",
           "- **Agents** are `Spot_agent_<n>` (role spawn, guard or phase_1) and their beats `Spot_patrol_<route>_<k>` (walked in order, looped); "
           "the page draws the suit character. No spawn is within 12 m of an arrival going deeper or 6 m of one coming back.",
           "- **Arrivals** stand 1.4 m inside their door. Coming in by a side door of a corridor you would face its far wall, so those "
           "arrivals look the longer way along the corridor instead (every arrival has at least 2 m clear ahead; the gate checks it).",
           "- **Shooter readability.** Full cover (pillars, crates 1.4 m, racks, cabinets, tanks, glass cubicles) and half cover (barriers "
           "1.1 m, benches 0.95 m, low crates) in every combat space; the long corridors of Corridors A and B get alcoves to step into, since "
           "the corridor lanes stay clear; glass windows and cubicles keep sightlines without being open ground. Ammo and loot in every scene.",
           "- **The Registrar's hall** is 47 m by 20 m and 7 m high (a stated exception to the 3.2 m ceilings): a 40 m by 20 m field of 200 "
           "`FloorPanel_<x>_<z>` (2 m, checkered) over an 8 m pit with a `Zone_hazard`, fixed landings at both ends (you never arrive on a "
           "panel), four rows of 48 `Rack_<n>` with 3 m aisles and a 4 m central aisle, 12 cameras on the four walls, the pink stripe at "
           "1.2 to 1.5 m round every wall, the control room's window and the cell's bars on the east wall. Each panel carries `panel_x`, "
           "`panel_z` and `under_rack` (1 where a rack stands on it), each rack `rack` and `hp`; the `Spot_core` at the centre has "
           "`keep_panels`.",
           "- **Phase 3's sky.** The ceiling over the field is 50 `CeilingPanel_<x>_<z>` objects the page can open on a sky. **Phase 3 needs a "
           "second, glitched sky backdrop for the arena (R3); it is not made here.**",
           "- **The control room** has one chair (`Chair_control`, the only chair; `Spot_chair_1` where you sit) facing a wall of monitors, "
           "an Admin console spot (`Spot_admin_1`, unlocked by beating the Registrar), and the cell beside it: 4 m by 4 m, its door locked "
           "(`locked`, `puzzle: cell`, opens from inside), a window from the control room, three `Spot_puzzle` parts (a vent grate, a loose "
           "tile, a code panel), a `Zone_trigger_cell` and a camera watching it. In the arena the control room and the cell are its east wall.",
           "- **Phase 2 filing.** Each scene but the hidden entry and the arena has one `Spot_filed` (11 in all, one of them in the cell) for "
           "the page to no-clip players to.", ""]
QUESTIONS = ["## Open questions for the owner", "",
             "1. **Keycard tier 3:** add a `keycard_tier_3` flag (the Market sells it, and Labs B drops one), or should the vault door take "
             "something else?",
             "2. **The lab's B2 door:** should it need keycard tier 1, like the grocery's lift, or is holding the lab job enough? (The B2 "
             "entry leads to checkpoint 1 either way.)",
             "3. **Filing into the cell:** one of the phase 2 filing spots is in the cell, so a filed player may have to solve it. Keep?",
             "4. **The arena's height:** 7 m, so the racks, the cameras and the opening ceiling read as a hall. Keep it, or 3.2 m like the rest?",
             "5. **The hidden entry:** no cameras and no agents, as the base's blind spot. Or should one camera be there to find?", ""]
NOT_DONE = ["## Not done here", "",
            "- Dressing, light baking and review renders (step 2), the manifest wiring and the page (the coordinator's).",
            "- The reskinned chambers (the Going back in greybox's), the glitched phase 3 sky (R3), the agents' model and behaviour.",
            "- Swimming (the pool dive back) and crawling: built for, shut."]


def main(a):
    renders = Path(a[a.index("--renders") + 1]) if "--renders" in a else None
    out = Path(a[a.index("--out") + 1]) if "--out" in a else G.ROOT / "docs/renders/secretops_greybox"
    out.mkdir(parents=True, exist_ok=True)
    wd = renders / "world" if renders and (renders / "world").exists() else G.ROOT / "world"
    docs = {sid: json.loads((wd / f"{sid}.json").read_text()) for sid in G.SCENES}
    for sid in AREA_ORDER:
        S = G.build(sid)
        plan_sheet(S, renders, out)
        still(S, renders, out)
    overview(out / "overview.png")
    readme(out, docs, "--checks" in a)
    if "--owner" in a:
        owner_sheet(Path(a[a.index("--owner") + 1]), out, docs)
    print(f"sheets written to {out}")


if __name__ == "__main__":
    main(sys.argv)
