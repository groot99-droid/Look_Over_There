"""The museum hall's picture hang (scene `galleries`), in plain Python so that both tools/blender/build_galleries.py (in Blender) and
tools/blender/make_galleries_paintings.py (the pictures atlas, Pillow) read the same frames.

frames(constants) -> [(wall normal, along, centre y, w, h, style, lit, group)], in build order. `group` names the hang a frame belongs to
(a bay of a long wall, the north wall, the door wall): no picture repeats within one.
"""
FRAME_DEPTH = {"gilt-ornate": 0.14, "gilt-simple": 0.09, "dark-wood": 0.075, "black-lacquer": 0.05, "thin-metal": 0.022}   # each profile's last s: the opening's inset
SMALL = {"gilt-ornate": "gilt-simple", "gilt-simple": "dark-wood", "dark-wood": "dark-wood", "black-lacquer": "thin-metal"}     # build_layout.ROOM_STYLE frame_small
BAY_ERA = ["gilt-simple", "gilt-ornate", "dark-wood", "black-lacquer"]   # the bays from the door north: Renaissance, Baroque, 19th century, modern (the Chronicle's order)
SALON = [(0.0, 1.75, 1.6, 1.2, "main"), (-1.45, 1.6, 0.7, 0.9, "small"), (1.45, 1.6, 0.7, 0.9, "small"),        # (along, centre y, w, h, role): the eye row ...
         (-1.2, 2.75 + 0.275, 0.75, 0.55, "small"), (0.0, 2.75 + 0.35, 0.95, 0.7, "main"), (1.2, 2.75 + 0.275, 0.75, 0.55, "small")]   # ... and the row above it,
#                                                                                                             bottom-aligned on 2.75 m (build_layout._vertical)


def bays(k):
    rows = sorted({z for _, z in k["homes"]})
    step = rows[1] - rows[0]
    return [z - step / 2 for z in rows] + [rows[-1] + step / 2], rows, step


def frames(k):
    bz, rows, step = bays(k)
    side_z = rows[1] - step / 2                       # the wing's doorways have the middle bay of the long walls
    out = []
    for n in ("+x", "-x"):
        for era, zb in zip(BAY_ERA, sorted(bz, reverse=True)):
            if abs(zb - side_z) < 1e-6:
                continue
            for da, yc, w, h, role in SALON:
                st = era if role == "main" else SMALL[era]
                out.append((n, zb + da, yc, w, h, st, role == "main" and yc < 2.5, f"{n}{zb:+.0f}"))
    dx = k["door"]["at"][0]
    for s in (-1, 1):
        out.append(("-z", dx + s * 4.0, 2.15, 1.25, 0.95, "gilt-simple", True, "door"))
    out.append(("+z", 0.0, 2.7, 3.3, 2.4, "gilt-ornate", True, "north"))
    for s in (-1, 1):
        out.append(("+z", s * 3.4, 2.3, 1.0, 1.3, "gilt-simple", True, "north"))
    return out


def opening(f):
    """The canvas of a frame: (w, h) of its opening (the frame's inner edge)."""
    n, a, yc, w, h, st = f[:6]
    d = FRAME_DEPTH[st]
    return w - 2 * d, h - 2 * d
