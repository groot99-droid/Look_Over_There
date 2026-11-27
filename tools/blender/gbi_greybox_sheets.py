"""The Going back in greybox's review sheets, drawn from the model in tools/blender/build_gbi_greybox.py (no Blender here; Pillow only).

    python tools/blender/gbi_greybox_sheets.py [--renders <build out dir>] [--out docs/renders/gbi_greybox] [--owner <png>]

Writes <out>/<chamber>_plan.png for each of the 15 chambers (top-down, to scale: walls, low furniture, the kit's pieces, doors, the arrival and
the way on, every spot, each hazard's part and its travel, the zones, a scale bar and north), <out>/<floor>_panel.png for each floor (its four
chambers in the run's order, the existing one drawn from its own layout file, and the safe house), <out>/<chamber>_still.jpg from the Blender
stills when --renders is given, and with --owner one tall sheet of the five floor panels for a phone. The README is written by hand.
Images are written fresh, with no metadata.
"""
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_gbi_greybox as G  # noqa: E402

ROOT = G.ROOT
FONT_DIRS = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu"), Path("/Library/Fonts")]


def font(size, bold=False):
    names = (["arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf", "Arial.ttf"])
    for d in FONT_DIRS:
        for n in names:
            if (d / n).exists():
                return ImageFont.truetype(str(d / n), size)
    return ImageFont.load_default()


INK, WALL, LOW, KIT, FLOOR_BG = (25, 25, 30), (60, 62, 68), (150, 150, 155), (120, 80, 170), (244, 243, 238)
IN_COL, OUT_COL, SAFE_COL = (20, 150, 60), (230, 110, 10), (20, 150, 120)
HAZ_COL = {"crush": (170, 30, 30), "lava": (240, 90, 0), "tide": (30, 100, 200), "gas": (110, 170, 20), "blade": (120, 120, 140)}
SPOT_STYLE = {  # kind: (letter, colour)
    "locker": ("L", (30, 90, 200)), "loot": ("$", (200, 150, 0)), "puzzle": ("P", (130, 60, 200)), "object": ("O", (0, 140, 160)),
    "monster": ("M", (200, 30, 30)), "vent": ("V", (90, 90, 90)), "shop": ("S", SAFE_COL), "stash": ("B", SAFE_COL), "save": ("W", SAFE_COL),
    "craft": ("C", SAFE_COL), "respawn": ("R", SAFE_COL),
}


def text(dr, xy, s, f, fill=INK, anchor="mm", halo=3):
    dr.text(xy, s, font=f, fill=fill, anchor=anchor, stroke_width=halo, stroke_fill=(255, 255, 255), align="center")


def arrow(dr, a, b, col, w=3, head=10):
    dr.line((a, b), fill=col, width=w)
    ang = math.atan2(b[1] - a[1], b[0] - a[0])
    for s in (2.6, -2.6):
        dr.line((b, (b[0] + head * math.cos(ang + s), b[1] + head * math.sin(ang + s))), fill=col, width=w)


class Frame:
    """Maps game (x, z) to pixels for one chamber's plan: north up (-z up), the footprint plus a margin."""
    def __init__(s, ppm, margin=1.2, top=0):
        s.ppm, s.m, s.top = ppm, margin, top
        s.x0, s.z0 = G.FOOT[0] - margin, G.FOOT[2] - margin
        s.W = int(round((G.FOOT[1] - G.FOOT[0] + 2 * margin) * ppm))
        s.H = int(round((G.FOOT[3] - G.FOOT[2] + 2 * margin) * ppm)) + top

    def p(s, x, z):
        return ((x - s.x0) * s.ppm, (z - s.z0) * s.ppm + s.top)

    def rect(s, mn, mx):
        a, b = s.p(mn[0], mn[2]), s.p(mx[0], mx[2])
        return (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))


def _band(c, Y):
    return c["min"][1] < Y + 1.5 and c["max"][1] > Y + 0.3


def draw_boxes(dr, fr, boxes, Y, kitnames=set()):
    """Floor-level solids, lowest first: low ones (under 1.6 m) light grey, the rest dark, the kit's purple."""
    order = sorted(boxes, key=lambda b: b["max"][1])
    for b in order:
        if not _band(b, Y) and not (b["max"][1] > Y + 0.1 and b["max"][1] <= Y + 0.3):
            continue
        h = b["max"][1] - Y
        col = KIT if b["name"] in kitnames else (WALL if h >= 1.6 else LOW if h > 0.35 else (205, 205, 200))
        dr.rectangle(fr.rect(b["min"], b["max"]), fill=col)


def chamber_image(S, ppm, detail=True, title=True):
    top = int(ppm * 3.2) if title else 0
    fr = Frame(ppm, top=top)
    im = Image.new("RGB", (fr.W, fr.H), (255, 255, 255))
    dr = ImageDraw.Draw(im, "RGBA")
    fs = max(11, int(ppm * 0.95))
    f_lab, f_small, f_title, f_spot = font(fs, True), font(max(10, int(fs * 0.8))), font(int(fs * 1.35), True), font(max(9, int(fs * 0.75)), True)
    dr.rectangle(fr.rect((G.X0, 0, G.Z0), (G.X1, 0, G.Z1)), fill=FLOOR_BG)
    # zones under everything
    for b in S.boxes:
        if not b.get("zone"):
            continue
        k = b["zone"]
        if k == "water":
            dr.rectangle(fr.rect(b["min"], b["max"]), fill=(90, 160, 230, 90))
        elif k == "safe":
            dr.rectangle(fr.rect(b["min"], b["max"]), fill=(40, 200, 150, 70), outline=SAFE_COL, width=2)
        elif k == "hazard":
            kind = b["name"].split("_")[2]
            c = HAZ_COL[kind]
            r = fr.rect(b["min"], b["max"])
            dr.rectangle(r, fill=(*c, 55))
            step = max(6, int(ppm * 0.9))
            for t in range(int(r[0]) - int(r[3] - r[1]), int(r[2]), step):        # hatching
                x0, y0, x1, y1 = t, r[3], t + (r[3] - r[1]), r[1]
                if x0 < r[0]:
                    y0 -= r[0] - x0
                    x0 = r[0]
                if x1 > r[2]:
                    y1 += x1 - r[2]
                    x1 = r[2]
                if x1 > x0:
                    dr.line((x0, y0, x1, y1), fill=(*c, 120), width=1)
    kitnames = {b["name"] for b in S.boxes if any(t.startswith("kit:") for t in b["tags"])}
    solids = [b for b in S.boxes if b["col"] and "slab" not in b["tags"]]
    draw_boxes(dr, fr, solids, S.Y, kitnames)
    for b in S.boxes:                                         # the pools' water and the blades' slots
        if b["name"].startswith("decor_Blade_Slot"):
            dr.rectangle(fr.rect(b["min"], b["max"]), fill=(90, 90, 100))
    # doors: the leaf as a thick line along its closed position
    for d in S.doors:
        th = math.radians(d["props"]["closed_yaw_deg"])
        hx, _, hz = d["hinge"]
        w = d["props"]["width"]
        ex, ez = hx + math.cos(th) * w, hz - math.sin(th) * w
        col = (160, 100, 40) if d["props"].get("kind") != "vent" else (90, 90, 90)
        dr.line((fr.p(hx, hz), fr.p(ex, ez)), fill=col, width=max(3, int(ppm * 0.28)))
    # hazards: the part at its origin, an arrow to the far end of its travel
    for h in S.hazards:
        c = HAZ_COL[h["kind"]]
        mn, mx = h["box"]
        o = h["origin"]
        if h["kind"] in ("tide", "lava") and mx[0] - mn[0] > 3:
            pass
        else:
            dr.rectangle(fr.rect([o[0] + mn[0], 0, o[2] + mn[2]], [o[0] + mx[0], 0, o[2] + mx[2]]), fill=c)
        a, b = fr.p(h["a"][0], h["a"][2]), fr.p(h["b"][0], h["b"][2])
        if math.hypot(b[0] - a[0], b[1] - a[1]) > 4:
            arrow(dr, a, b, c, w=max(2, int(ppm * 0.18)), head=max(8, int(ppm * 0.7)))
        if detail:
            lx, lz = (h["a"][0] + h["b"][0]) / 2, (h["a"][2] + h["b"][2]) / 2
            text(dr, fr.p(lx, lz + 1.4), f"{h['kind'].upper()} {h['n']}", f_small, fill=c)
    # labels
    for l in S.labels:
        if l["kind"] == "title":
            continue
        if (l["kind"] == "note" and not detail) or l["text"] == "DOOR":
            continue
        col = KIT if l["kind"] == "kit" else SAFE_COL if l["kind"] == "safe" else (70, 70, 80) if l["kind"] == "note" else INK
        text(dr, fr.p(l["x"], l["z"]), l["text"], f_small if l["kind"] in ("note", "kit") else f_lab, fill=col)
    # spots
    rr = max(5, int(ppm * 0.55))
    for e in S.empties:
        n = e["name"]
        if not n.startswith("Spot_"):
            continue
        kind = n.split("_")[1]
        if kind in ("hazard", "call", "panel"):
            continue
        if kind not in SPOT_STYLE:
            continue
        letter, col = SPOT_STYLE[kind]
        if e["props"].get("of") == "safe_house":
            if not detail:
                continue
            col = SAFE_COL
        x, y = fr.p(e["pos"][0], e["pos"][2])
        dr.ellipse((x - rr, y - rr, x + rr, y + rr), fill=col, outline=(255, 255, 255), width=2)
        dr.text((x, y), letter, font=f_spot, fill=(255, 255, 255), anchor="mm")
    # the arrival and the way on
    ra = max(8, int(ppm * 0.9))
    ax, _, az = S.arrival[1]
    x, y = fr.p(ax, az)
    dr.ellipse((x - ra, y - ra, x + ra, y + ra), outline=IN_COL, width=max(3, int(ppm * 0.3)))
    text(dr, (x, y - ra - fs * 0.7), "IN", f_lab, fill=IN_COL)
    e = next(e for e in S.empties if e["name"] == f"Link_{S.onward}")
    x, y = fr.p(e["pos"][0], e["pos"][2])
    dr.ellipse((x - ra, y - ra, x + ra, y + ra), outline=OUT_COL, width=max(3, int(ppm * 0.3)))
    text(dr, (x, y + ra + fs * 0.7), "OUT", f_lab, fill=OUT_COL)
    # outline, title, scale bar, north
    dr.rectangle(fr.rect((G.FOOT[0], 0, G.FOOT[2]), (G.FOOT[1], 0, G.FOOT[3])), outline=INK, width=2)
    if title:
        text(dr, (fr.W / 2, top * 0.32), f"{S.id}   {S.title}", f_title, halo=0)
        text(dr, (fr.W / 2, top * 0.75), f"{S.floor} at y {S.Y:g}, ceiling {S.H:g} m", f_small, halo=0)
    sb0 = fr.p(G.FOOT[0] + 1.0, G.FOOT[3] + 0.6)
    dr.line((sb0, (sb0[0] + 10 * ppm, sb0[1])), fill=INK, width=3)
    for k in (0, 5, 10):
        dr.line(((sb0[0] + k * ppm, sb0[1] - 4), (sb0[0] + k * ppm, sb0[1] + 4)), fill=INK, width=2)
    text(dr, (sb0[0] + 5 * ppm, sb0[1] - fs * 0.6), "10 m", f_small)
    nx, ny = fr.p(G.FOOT[1] - 3.0, G.FOOT[3] + 0.6)
    arrow(dr, (nx, ny + ppm * 0.45), (nx, ny - ppm * 0.9), INK, w=3, head=max(6, int(ppm * 0.4)))
    text(dr, (nx + ppm * 1.0, ny), "N", f_small)
    return im


def existing_image(sid, ppm, title=True):
    """An existing chamber (the store's floor), drawn from its own layout file: what stands between knee and head height, and its doors."""
    floor, path = G.EXISTING[sid]
    doc = json.loads((ROOT / path).read_text())
    Y = G.FLOOR_Y[floor]
    top = int(ppm * 3.2) if title else 0
    fr = Frame(ppm, top=top)
    im = Image.new("RGB", (fr.W, fr.H), (255, 255, 255))
    dr = ImageDraw.Draw(im, "RGBA")
    fs = max(11, int(ppm * 0.95))
    f_lab, f_small, f_title = font(fs, True), font(max(10, int(fs * 0.8))), font(int(fs * 1.35), True)
    dr.rectangle(fr.rect((G.X0, 0, G.Z0), (G.X1, 0, G.Z1)), fill=(232, 232, 236))
    cols = [c for c in doc["colliders"] if c["max"][0] > G.FOOT[0] - 0.5 and c["min"][0] < G.FOOT[1] + 0.5 and c["max"][2] > G.FOOT[2] - 0.5
            and c["min"][2] < G.FOOT[3] + 0.5 and c["min"][1] < Y + 1.5 and c["max"][1] > Y + 0.3
            and not c["s"].startswith(("Site_", "Hedges_"))]                          # the exterior's city blocks and hedges are not the floor
    for c in sorted(cols, key=lambda c: c["max"][1]):
        h = c["max"][1] - Y
        x0, y0, x1, y1 = fr.rect([max(c["min"][0], G.FOOT[0]), 0, max(c["min"][2], G.FOOT[2])], [min(c["max"][0], G.FOOT[1]), 0, min(c["max"][2], G.FOOT[3])])
        dr.rectangle((x0, y0, max(x0 + 1, x1), max(y0 + 1, y1)), fill=(110, 110, 118) if h >= 1.6 else (170, 170, 175))
    for d in doc["doors"]:
        if abs(d["hinge"][1] - Y) > 0.5:
            continue
        th = math.radians(d["closed_yaw_deg"])
        hx, _, hz = d["hinge"]
        ex, ez = hx + math.cos(th) * d["width"], hz - math.sin(th) * d["width"]
        dr.line((fr.p(hx, hz), fr.p(ex, ez)), fill=(160, 100, 40), width=max(2, int(ppm * 0.2)))
    dr.rectangle(fr.rect((G.FOOT[0], 0, G.FOOT[2]), (G.FOOT[1], 0, G.FOOT[3])), outline=INK, width=2)
    # the arrival and the way on, from the notes (existing doors and the store's own arrive points)
    pts = {"gbi_L4_4": ((0.0, 25.6), (16.0, 8.0)), "gbi_L3_1": ((16.0, 8.0), (-16.5, -14.4)), "gbi_L2_1": ((-16.478, -14.278), (-0.5, 9.4)),
           "gbi_L1_1": ((-0.007, 9.708), (-0.5, -1.9)), "gbi_B1_1": ((0.009, -1.599), None)}[sid]
    ra = max(8, int(ppm * 0.9))
    for p, col, t in ((pts[0], IN_COL, "IN"), (pts[1], OUT_COL, "OUT")):
        if p is None:
            continue
        x, y = fr.p(*p)
        dr.ellipse((x - ra, y - ra, x + ra, y + ra), outline=col, width=max(3, int(ppm * 0.3)))
        text(dr, (x + ra * 2.2, y), t, f_lab, fill=col)
    text(dr, (fr.W / 2, fr.H * 0.5 + top / 2), "EXISTING FLOOR", f_title, fill=(90, 90, 100))
    text(dr, (fr.W / 2, fr.H * 0.5 + top / 2 + fs * 1.6), f"the store's {floor}, kept as it is", f_small, fill=(90, 90, 100))
    if title:
        text(dr, (fr.W / 2, top * 0.32), f"{sid}   the store's {floor}", f_title, halo=0)
        text(dr, (fr.W / 2, top * 0.75), "existing: " + ("built (tools/make_chambers.mjs)" if (ROOT / f"world/{sid}.json").exists() else
                                                         "to make from the floor, as gbi_L3_1 was"), f_small, halo=0)
    return im


def caption(sid):
    if sid in G.EXISTING:
        return {"gbi_L4_4": "in: sky hall from L4_3 (new, proposed at the glass doors) | out: the store's stairs down to L3_1 (built)",
                "gbi_L3_1": "in: the stairs from L4_4 (built) | out: its stair door down, to L3_2 (proposed)",
                "gbi_L2_1": "in: the stairs from L3_4 (new) | out: its stair door down, to L2_2 (proposed)",
                "gbi_L1_1": "in: the stairs from L2_4 (new) | out: its stair door down, to L1_2 (proposed)",
                "gbi_B1_1": "in: the stairs from L1_4 (new) | out: a new door to B1_2 (open question)"}[sid]
    S = G.build(sid)
    conn = {}
    for a, b, k in G.PAIRS:
        conn[a] = k
        conn[b] = k
    for (s, d), (k, o, n) in G.OUTSIDE.items():
        conn[(s, d)] = k
    i = "spawn (the run's start)" if S.arrival[0] is None else conn.get((sid, S.arrival[0]), "?")
    o = conn.get((sid, S.onward), "?")
    hz = ", ".join(f"{h['kind']} {h['n']}" for h in S.hazards)
    return f"in: {i} | out: {o} | hazards: {hz}" + (" | SAFE HOUSE" if S.safe else "")


def floor_panel(floor, ppm):
    ids = [f"gbi_{floor}_{i}" for i in range(1, 5)]
    ims = [existing_image(s, ppm) if s in G.EXISTING else chamber_image(G.build(s), ppm, detail=False) for s in ids]
    w, h = ims[0].size
    cap_h = int(ppm * 2.4)
    head = int(ppm * 5.0)
    W, H = 2 * w + int(ppm * 1.5), head + 2 * (h + cap_h) + int(ppm * 1.0)
    im = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(im)
    fs = max(11, int(ppm * 0.95))
    f_head, f_sub, f_cap = font(int(fs * 2.0), True), font(int(fs * 1.05)), font(max(10, int(fs * 0.85)))
    text(dr, (W / 2, head * 0.33), f"{floor}: chambers {FLOOR_ORDER(floor)}", f_head, halo=0)
    text(dr, (W / 2, head * 0.72), f"{G.LOOK[floor]}; floor at y {G.FLOOR_Y[floor]:g}", f_sub, halo=0)
    for k, (s, ci) in enumerate(zip(ids, ims)):
        cx, cy = (k % 2) * (w + int(ppm * 1.5)), head + (k // 2) * (h + cap_h)
        im.paste(ci, (cx, cy))
        cap = caption(s)
        for j, line in enumerate(_wrap(cap, f_cap, w - 10, dr)[:2]):
            dr.text((cx + w / 2, cy + h + fs * 0.75 + j * fs * 1.05), line, font=f_cap, fill=(60, 60, 70), anchor="mm")
    return im


def FLOOR_ORDER(floor):
    return "1 > 2 > 3 > 4 (top left, top right, bottom left, bottom right)"


def _wrap(s, f, width, dr):
    words, lines, cur = s.split(" "), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if dr.textlength(t, font=f) > width and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def legend(W, ppm):
    fs = max(12, int(ppm * 1.0))
    f, fb = font(fs), font(fs, True)
    items = [("IN", IN_COL, "ring: the arrival"), ("OUT", OUT_COL, "ring: the one way on")] + [
        (v[0], v[1], k if k != "stash" else "stash (B)") for k, v in SPOT_STYLE.items() if k not in ("stash",)] + [("B", SAFE_COL, "stash")]
    names = {"locker": "locker (the Lost and Found)", "loot": "loot", "puzzle": "puzzle", "object": "missing object", "monster": "monster (the wave)",
             "vent": "vent (shut)", "shop": "shop", "save": "save", "craft": "crafting", "respawn": "respawn"}
    rows = [items[i:i + 4] for i in range(0, len(items), 4)]
    H = int(fs * 2.2) * (len(rows) + 3)
    im = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(im, "RGBA")
    text(dr, (W / 2, fs * 1.2), "Going back in greybox: 15 new chambers, 5 safe houses (plain boxes, no dressing, no bake)", font(int(fs * 1.25), True), halo=0)
    y = fs * 3.2
    colw = W / 4
    for row in rows:
        for j, (letter, col, what) in enumerate(row):
            x = colw * j + fs * 1.5
            if letter in ("IN", "OUT"):
                dr.ellipse((x - fs * 0.6, y - fs * 0.6, x + fs * 0.6, y + fs * 0.6), outline=col, width=3)
            else:
                dr.ellipse((x - fs * 0.6, y - fs * 0.6, x + fs * 0.6, y + fs * 0.6), fill=col)
                dr.text((x, y), letter, font=font(int(fs * 0.8), True), fill=(255, 255, 255), anchor="mm")
            dr.text((x + fs * 1.1, y), names.get(what, what), font=f, fill=INK, anchor="lm")
        y += fs * 2.0
    x = fs * 1.0
    for k, c in HAZ_COL.items():
        dr.rectangle((x, y - fs * 0.5, x + fs * 1.4, y + fs * 0.5), fill=(*c, 140))
        dr.text((x + fs * 1.8, y), G.HAZARD_NAMES[k], font=f, fill=INK, anchor="lm")
        x += dr.textlength(G.HAZARD_NAMES[k], font=f) + fs * 3.4
    y += fs * 2.0
    x = fs * 1.0
    for col, what in ((WALL, "wall (1.6 m and up)"), (LOW, "low: furniture, cubicles, half walls"), (KIT, "connector kit"),
                      ((90, 160, 230), "water"), ((40, 200, 150), "safe zone")):
        dr.rectangle((x, y - fs * 0.5, x + fs * 1.4, y + fs * 0.5), fill=col)
        dr.text((x + fs * 1.8, y), what, font=f, fill=INK, anchor="lm")
        x += dr.textlength(what, font=f) + fs * 3.4
    return im


def main(argv):
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else ROOT / "docs/renders/gbi_greybox"
    out.mkdir(parents=True, exist_ok=True)
    for sid in G.SCENES:
        chamber_image(G.build(sid), 22.0).save(out / f"{sid}_plan.png", optimize=True)
    panels = []
    for fl in G.FLOORS:
        p = floor_panel(fl, 11.0)
        p.save(out / f"{fl}_panel.png", optimize=True)
        panels.append(p)
    if "--renders" in argv:
        rd = Path(argv[argv.index("--renders") + 1]) / "renders"
        for sid in G.SCENES:
            f = rd / f"{sid}_still.png"
            if f.exists():
                Image.open(f).convert("RGB").resize((1200, 675), Image.LANCZOS).save(out / f"{sid}_still.jpg", quality=86)
    if "--owner" in argv:
        W = max(p.size[0] for p in panels)
        leg = legend(W, 11.0)
        chain = Image.new("RGB", (W, 70), (255, 255, 255))
        dc = ImageDraw.Draw(chain)
        dc.text((W / 2, 35), "the run, top down: L4 1 > 2 > 3 > 4 (stairs) > L3 1 > ... > B1 4 > out to the Overworld", font=font(17, True),
                fill=INK, anchor="mm")
        H = leg.size[1] + chain.size[1] + sum(p.size[1] + 30 for p in panels)
        sheet = Image.new("RGB", (W, H), (255, 255, 255))
        y = 0
        for part in [leg, chain] + panels:
            sheet.paste(part, ((W - part.size[0]) // 2, y))
            y += part.size[1] + (30 if part in panels else 0)
            if part in panels:
                ImageDraw.Draw(sheet).line((40, y - 15, W - 40, y - 15), fill=(200, 200, 205), width=3)
        dest = Path(argv[argv.index("--owner") + 1])
        dest.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(dest, optimize=True)
        sheet.save(out / "owner_gbi_greybox.png", optimize=True)
        print(f"owner sheet {sheet.size[0]} x {sheet.size[1]} px")
    print(f"wrote sheets to {out}")


if __name__ == "__main__":
    main(sys.argv)
