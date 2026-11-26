"""The stalker's and the Mawcrawler's clips as pose functions (plain Python, no bpy), for build_creatures.py and
offline checks. Poses are in Blender armature space as common.Animator plays them (see warrior_clips.py); the
characters face -Y, left is +X. warrior_clips.deform turns a pose into bone deform matrices.

`amp` (0..1] scales the big moves; the build lowers it only when the weights cannot keep every edge within the
stretch gate at full size.
"""
import math

import numpy as np

from warrior_clips import keyed

sin, cos, pi = math.sin, math.cos, math.pi


# ---------------------------------------------------------------- the stalker
def stalker_clips(names, amp=1.0):
    """[(name, frames, pose_at)]: idle (2.5 s), walk (1.33 s), stalk (2.67 s, a slow crouched creep), freeze (1 s,
    the pose it holds while it is watched)."""
    CLAWS = [n for n in names if n.startswith("claw")]
    # its rest pose is a stride: the right foot 0.35 m behind, the left 0.35 m ahead (about 18 degrees each way)
    NEUTRAL = {"R": -18.0, "L": 19.0}
    a = amp

    def claws(p, amount):
        for c in CLAWS:
            p[c] = {"rot": {"X": amount * (1.0 if c.endswith(("_1.L", "_1.R")) else 0.6)}}
        return p

    def idle(f, n=60):
        ph = 2 * pi * f / n
        p = {"chest": {"rot": {"X": 2 * sin(ph)}}, "upper_chest": {"rot": {"X": 1.5 * sin(ph + 0.3)}},
             "neck": {"rot": {"Z": 6 * sin(ph), "X": 2 * sin(2 * ph)}},
             "head": {"rot": {"Z": 6 * sin(ph + 0.6), "Y": 5 * sin(2 * ph + 1)}},
             "mouth_a": {"rot": {"X": 6 * max(0.0, sin(2 * ph))}},
             "upperarm.L": {"rot": {"X": 3 * sin(ph + 1)}}, "upperarm.R": {"rot": {"X": 3 * sin(ph + 2)}}}
        return claws(p, 6 * a * (0.5 + 0.5 * sin(2 * ph)))

    def walk(f, n=32, stride=24.0, crouch=0.0):
        ph = 2 * pi * f / n
        s = sin(ph)
        # with both legs under the hips it stands about 5 cm taller than in its striding rest pose
        p = {"root": {"loc": (0, 0, 0.045 - 0.02 * abs(cos(ph)) - crouch)}, "pelvis": {"rot": {"Z": 5 * s}},
             "chest": {"rot": {"Z": -6 * s}}, "neck": {"rot": {"Z": 3 * s}}, "head": {"rot": {"Z": -4 * s}}}
        for sd, sg in (("L", 1), ("R", -1)):
            sw = sg * s
            lift = max(0.0, sw)
            p[f"thigh.{sd}"] = {"rot": {"X": NEUTRAL[sd] - stride * a * sw - 18 * crouch / 0.1}}
            p[f"shin.{sd}"] = {"rot": {"X": 38 * a * lift + 25 * crouch / 0.1}}
            p[f"foot.{sd}"] = {"rot": {"X": -20 * a * lift}}
            p[f"upperarm.{sd}"] = {"rot": {"X": 16 * a * sw}}
            p[f"forearm.{sd}"] = {"rot": {"X": -6 * a * max(0.0, -sw)}}
        return p

    def stalk(f, n=64):
        p = walk(f, n, stride=12.0, crouch=0.1)
        ph = 2 * pi * f / n
        p["spine2"] = {"rot": {"X": 10}}
        p["chest"] = {"rot": {"X": 8, "Z": p["chest"]["rot"]["Z"] * 0.5}}
        p["neck"] = {"rot": {"X": -14, "Z": 4 * sin(ph / 2)}}
        p["head"] = {"rot": {"X": -10, "Z": 3 * sin(ph)}}
        for sd in "LR":
            p[f"upperarm.{sd}"] = {"rot": {"X": (-28 + 6 * sin(ph + (0 if sd == "L" else pi))) * a}}
            p[f"forearm.{sd}"] = {"rot": {"X": -18 * a}}
        return claws(p, 10 * a)

    FREEZE = {"thigh.L": {"rot": {"X": 4}}, "thigh.R": {"rot": {"X": -6}}, "spine2": {"rot": {"X": 6}},
              "chest": {"rot": {"X": 5, "Z": 8}}, "neck": {"rot": {"X": -10, "Z": -6}},
              "head": {"rot": {"Y": 22, "X": -8}}, "mouth_a": {"rot": {"X": 14}},
              "upperarm.L": {"rot": {"X": -40 * a, "Y": -10 * a}}, "forearm.L": {"rot": {"X": -30 * a}},
              "upperarm.R": {"rot": {"X": -55 * a, "Y": 12 * a}}, "forearm.R": {"rot": {"X": -20 * a}}}
    claws(FREEZE, 8 * a)  # claws curled, reaching: a spread (negative) tears the webbing between them

    return [("idle", 60, idle), ("walk", 32, walk), ("stalk", 64, stalk), ("freeze", 24, lambda f: FREEZE)]


# ---------------------------------------------------------------- the Mawcrawler
LEGS = [(leg, sd) for leg in ("front", "mid", "rear") for sd in "LR"]
GROUP_A = {("front", "L"), ("mid", "R"), ("rear", "L")}  # tripod gait


def maw_clips(names, heads, amp=1.0):
    """[(name, frames, pose_at)]: idle (2 s), crawl (1.33 s), lunge (1.25 s, the bite), spawn (2 s, climbing out of
    the floor: it starts 1.75 m below the root)."""
    H = {n: np.asarray(h, float) for n, h in zip(names, heads)}
    a = amp

    def axis(leg, sd):  # turning +deg about it raises the leg
        d = H[f"leg_{leg}5.{sd}"] - H[f"leg_{leg}1.{sd}"]
        d[2] = 0
        d /= np.linalg.norm(d)
        x = np.cross(d, (0, 0, 1))
        return tuple(x / np.linalg.norm(x))

    AX = {k: axis(*k) for k in LEGS}

    def leg_pose(p, leg, sd, swing, lift, fold=0.0):
        """swing: degrees forward; lift: degrees up at the hip; fold: degrees the knee curls in."""
        sg = 1 if sd == "L" else -1
        p[f"leg_{leg}1.{sd}"] = {"rot": {"Z": -sg * swing}, "axis": [(AX[(leg, sd)], lift)]}
        if fold:
            p[f"leg_{leg}3.{sd}"] = {"axis": [(AX[(leg, sd)], -fold)]}
        return p

    def idle(f, n=48):
        ph = 2 * pi * f / n
        p = {"root": {"loc": (0, 0, 0.02 * sin(ph))}, "body": {"rot": {"X": 1.5 * sin(ph)}},
             "neck": {"rot": {"X": 3 * sin(ph + 0.5), "Z": 4 * sin(ph)}},
             "jaw_lower": {"rot": {"X": 6 * max(0.0, sin(2 * ph))}}, "jaw_upper": {"rot": {"X": -3 * max(0.0, sin(2 * ph))}},
             "tail": {"rot": {"Z": 6 * sin(ph)}}}
        for i, (leg, sd) in enumerate(LEGS):
            leg_pose(p, leg, sd, 2 * sin(ph + i), 2 * max(0.0, sin(ph + i * 1.3)))
        return p

    def crawl(f, n=32):
        ph = 2 * pi * f / n
        p = {"root": {"loc": (0, 0, 0.03 * abs(sin(2 * ph)))}, "body": {"rot": {"Y": 3 * sin(ph)}},
             "neck": {"rot": {"Z": 4 * sin(ph)}}, "tail": {"rot": {"Z": -8 * sin(ph)}},
             "jaw_lower": {"rot": {"X": 4 + 4 * sin(2 * ph)}}}
        for leg, sd in LEGS:
            q = ph if (leg, sd) in GROUP_A else ph + pi
            leg_pose(p, leg, sd, 16 * a * cos(q), 22 * a * max(0.0, -sin(q)))
        return p

    CROUCH = {"root": {"loc": (0, 0.25, -0.18)}, "neck": {"rot": {"X": -14}}, "jaw_upper": {"rot": {"X": -20}},
              "jaw_lower": {"rot": {"X": 30}}}
    LUNGE = {"root": {"loc": (0, -0.65, 0.05)}, "neck": {"rot": {"X": 10}}, "jaw_upper": {"rot": {"X": -30}},
             "jaw_lower": {"rot": {"X": 45}}}
    BITE = {"root": {"loc": (0, -0.6, 0.0)}, "neck": {"rot": {"X": 14}}, "jaw_upper": {"rot": {"X": 4}},
            "jaw_lower": {"rot": {"X": -4}}}
    for leg, sd in LEGS:
        front = leg == "front"
        leg_pose(CROUCH, leg, sd, -6, 0, 0)
        leg_pose(LUNGE, leg, sd, (25 if front else -10) * a, (18 if front else 0) * a)
        leg_pose(BITE, leg, sd, (20 if front else -8) * a, 0)
    lunge_keys = [(0, {}), (10, CROUCH), (15, LUNGE), (19, BITE), (30, {})]

    # spawn: it climbs out of the floor, legs first folded up against the body, reaching, then planted
    FOLDED = {"root": {"loc": (0, 0, -1.75)}, "neck": {"rot": {"X": -20}}, "jaw_lower": {"rot": {"X": 20}}}
    REACH = {"root": {"loc": (0, 0, -0.95)}, "neck": {"rot": {"X": -10}}, "jaw_lower": {"rot": {"X": 20}}}
    RISE = {"root": {"loc": (0, 0, -0.15)}, "body": {"rot": {"X": -6}}}
    for leg, sd in LEGS:
        front = leg == "front"
        leg_pose(FOLDED, leg, sd, 0, 40 * a, 20 * a)
        leg_pose(REACH, leg, sd, 10 if front else 0, (10 if front else 40) * a, (0 if front else 20) * a)
        leg_pose(RISE, leg, sd, 4 if front else 0, 0 if front else 12 * a, 0)
    spawn_keys = [(0, FOLDED), (18, REACH), (34, RISE), (48, {})]

    return [("idle", 48, idle), ("crawl", 32, crawl), ("lunge", 30, lambda f: keyed(lunge_keys, f)),
            ("spawn", 48, lambda f: keyed(spawn_keys, f))]
