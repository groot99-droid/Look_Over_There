"""The warriors' clips as pose functions (plain Python and numpy, no bpy), for build_warriors.py and offline checks.

A pose is {bone: {"rot": {"X": deg, "Y": deg, "Z": deg}, "loc": (x, y, z)}} in Blender armature space, as
common.Animator plays it: turns about the bone's head (X, then Y, then Z), then a move. The figures face -Y and their
left is +X; positive X turns an upward bone forward and a downward bone back.

The figures are toy soldiers sculpted in one piece, arms and weapons against the body, so they move like toys
coming alive: the legs step, the body sways and lunges from the spine, and only the weapon arm swings a little
(in the attack), so weapons and shields sculpted onto the body move with it. Each clip has a ladder of sizes
(LADDERS); the build plays each one at the largest size its figure passes both gates at (no edge past 2x, no cut
in the mesh opening a crack).
"""
import math

import numpy as np

sin, pi = math.sin, math.pi
FRAMES = {"idle": 48, "march": 24, "attack": 22, "freeze": 6}


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def lerp_pose(a, b, t):
    out = {}
    for bn in set(a) | set(b):
        pa, pb = a.get(bn, {}), b.get(bn, {})
        ra, rb = pa.get("rot", {}), pb.get("rot", {})
        out[bn] = {"rot": {k: ra.get(k, 0.0) * (1 - t) + rb.get(k, 0.0) * t for k in set(ra) | set(rb)},
                   "loc": tuple(x * (1 - t) + y * t for x, y in zip(pa.get("loc", (0, 0, 0)), pb.get("loc", (0, 0, 0))))}
        xa = {tuple(round(float(c), 6) for c in v): d for v, d in pa.get("axis", [])}
        xb = {tuple(round(float(c), 6) for c in v): d for v, d in pb.get("axis", [])}
        if xa or xb:  # extra turns about fixed axes: [(axis, deg), ...]
            out[bn]["axis"] = [(k, xa.get(k, 0.0) * (1 - t) + xb.get(k, 0.0) * t) for k in sorted(set(xa) | set(xb))]
    return out


def keyed(keys, f):
    if f <= keys[0][0]:
        return keys[0][1]
    for (f0, p0), (f1, p1) in zip(keys, keys[1:]):
        if f0 <= f <= f1:
            return lerp_pose(p0, p1, smooth((f - f0) / (f1 - f0)))
    return keys[-1][1]


FULL = {"idle": (1.0,), "march": (1.0,), "attack": (1.0, 1.0, 1.0), "freeze": (1.0,)}
# Each clip's sizes, largest first: the build plays each clip at the largest one its figure's weights pass
# (no edge past 2x, no cut opening a crack). idle: (sway,); march: (stride,); attack: (legs, weapon arm, body).
LADDERS = {"idle": [(1.0,), (0.7,), (0.45,)],
           "march": [(1.0,), (0.85,), (0.7,), (0.55,), (0.45,), (0.35,), (0.25,)],
           "attack": [(1.0, 1.0, 1.0), (0.85, 0.85, 0.9), (0.7, 0.7, 0.8), (0.55, 0.55, 0.7), (0.4, 0.55, 0.6),
                      (0.25, 0.45, 0.5), (0.4, 0.0, 0.6), (0.25, 0.0, 0.5), (0.15, 0.0, 0.4)],
           "freeze": [(1.0,)]}


def clips(weapon="R", amps=None):
    """[(name, frames, pose_at)]: idle (2 s, loops), march (1 s, loops), attack (0.92 s), freeze (the display pose
    held for 0.25 s: play it to snap a figure back onto its plinth). amps: {clip: sizes} (see LADDERS)."""
    a = dict(FULL, **(amps or {}))
    sway, = a["idle"]
    leg_m, = a["march"]
    leg, arm, body = a["attack"]
    w = weapon
    tw = -1 if w == "R" else 1  # the chest twists toward the weapon side

    def idle(f, n=FRAMES["idle"]):
        ph = 2 * pi * f / n
        return {"chest": {"rot": {"X": 1.5 * sway * sin(ph)}}, "spine": {"rot": {"X": 0.8 * sway * sin(ph)}},
                "head": {"rot": {"Z": 5 * sway * sin(ph + 1.0), "X": 1.5 * sway * sin(2 * ph)}}}

    def march(f, n=FRAMES["march"]):
        ph = 2 * pi * f / n
        s = sin(ph)
        # the whole toy rocks from foot to foot (a turn of the root, under every bone, so it bends nothing): the
        # march reads even for a figure whose robe lets its legs swing only a little
        p = {"root": {"loc": (0, 0, 0.004 * abs(s)), "rot": {"Y": -4 * s}}, "chest": {"rot": {"Z": 3 * leg_m * s}},
             "hips": {"rot": {"Z": -3 * leg_m * s}}, "head": {"rot": {"Z": -2 * s}}}
        for sd, sg in (("L", 1), ("R", -1)):
            sw = sg * s
            lift = max(0.0, sw)
            p[f"thigh.{sd}"] = {"rot": {"X": -18 * leg_m * sw}}
            p[f"shin.{sd}"] = {"rot": {"X": 24 * leg_m * lift}}
            p[f"foot.{sd}"] = {"rot": {"X": -8 * leg_m * lift}}
        return p

    b = body
    # the root leans the whole figure back, then into the blow (it bends nothing, so every figure gets all of it)
    ready = {"root": {"rot": {"X": -4}}, "spine": {"rot": {"X": -3 * b, "Z": -6 * tw * b}},
             "chest": {"rot": {"X": -5 * b, "Z": -10 * tw * b}}, "head": {"rot": {"X": 3 * b}}, f"upperarm.{w}": {"rot": {"X": -14 * arm}},
             f"forearm.{w}": {"rot": {"X": -10 * arm}},
             "thigh.L": {"rot": {"X": -6 * leg}}, "thigh.R": {"rot": {"X": 5 * leg}}}
    strike = {"spine": {"rot": {"X": 7 * b, "Z": 7 * tw * b}}, "chest": {"rot": {"X": 12 * b, "Z": 10 * tw * b}},
              "head": {"rot": {"X": -6 * b}}, f"upperarm.{w}": {"rot": {"X": 4 * arm}},
              "thigh.L": {"rot": {"X": -12 * leg}}, "thigh.R": {"rot": {"X": 8 * leg}},
              "shin.L": {"rot": {"X": 8 * leg}}, "root": {"loc": (0, -0.012, -0.002), "rot": {"X": 7}}}
    keys = [(0, {}), (8, ready), (12, strike), (15, strike), (22, {})]
    return [("idle", FRAMES["idle"], idle), ("march", FRAMES["march"], march),
            ("attack", FRAMES["attack"], lambda f: keyed(keys, f)), ("freeze", FRAMES["freeze"], lambda f: {})]


# ---------------------------------------------------------------- the same poses as bone deform matrices (numpy)
def _rot(axis, deg):
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    x, y, z = a
    C = 1 - c
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                     [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


AXES = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}


def deform(names, heads, parents, pose):
    """Each bone's deform matrix (armature space, rest to posed) for a pose, as common.Animator sets it."""
    B = len(names)
    D = [None] * B
    order, seen = [], set()

    def visit(i):
        if i in seen:
            return
        if parents[i] >= 0:
            visit(parents[i])
        seen.add(i)
        order.append(i)

    for i in range(B):
        visit(i)
    for i in order:
        spec = pose.get(names[i], {})
        R = np.eye(3)
        for ax in ("X", "Y", "Z"):
            d = spec.get("rot", {}).get(ax, 0.0)
            if d:
                R = _rot(AXES[ax], d) @ R
        for axis, d in spec.get("axis", []):
            if d:
                R = _rot(axis, d) @ R
        h = np.asarray(heads[i], float)
        M = np.eye(4)
        M[:3, :3] = R
        M[:3, 3] = h - R @ h
        T = np.eye(4)
        T[:3, 3] = spec.get("loc", (0, 0, 0))
        L = T @ M
        D[i] = D[parents[i]] @ L if parents[i] >= 0 else L
    return np.array(D)


def clip_matrices(names, heads, parents, weapon="R", amps=None):
    """{clip: (frames + 1, bones, 4, 4)} for the clips named in amps (all four when amps is None)."""
    want = set(amps) if amps else set(FULL)
    return {n: np.array([deform(names, heads, parents, pa(f)) for f in range(fr + 1)])
            for n, fr, pa in clips(weapon, amps) if n in want}
