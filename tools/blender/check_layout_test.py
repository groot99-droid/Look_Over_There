"""Tests for tools/blender/check_layout.py (no Blender needed):  python tools/blender/check_layout_test.py"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_layout as cl


def box(name, mn, mx):
    return {"name": name, "min": list(mn), "max": list(mx)}


WORLD = {"colliders": [
    {"s": "Floor", "min": [-3, -1, -3], "max": [3, 0, 3]},
    {"s": "Wall_N", "min": [-3, 0, -3], "max": [3, 2.8, -2.8]},
    {"s": "Crate", "min": [1, 0, 1], "max": [2, 1, 2]},
    {"s": "Edge_E", "min": [3, 0, -3], "max": [3.2, 9, 3]},
], "markers": [{"name": "Spawn", "position": [-1.5, 0, 0]}]}
CONST = {"door": {"at": [0, 2.4]}, "arrive": [-1.5, 0, 0]}
GOOD = [box("Floor", (-3, -1, -3), (3, 0, 3)), box("Wall_N", (-3, 0, -3), (3, 2.8, -2.8)), box("Crate", (1, 0, 1), (2, 1, 2)),
        box("decor_rug", (-1, 0, -1), (0.5, 0.01, 0.5)), box("Lamp", (1.4, 1, 1.4), (1.6, 1.3, 1.6))]


def run(parts, world=WORLD, const=CONST):
    return cl.check(parts, world, const)


def failed(res, rule=None):
    return [r for r in res if not r[0] and (rule is None or r[1] == rule)]


class LayoutCheck(unittest.TestCase):
    def test_good_scene_passes(self):
        res = run(GOOD)
        self.assertEqual(failed(res), [], res)
        self.assertTrue(any(r[1] == "CLEAR" for r in res))

    def test_collider_without_art_fails(self):
        res = run([p for p in GOOD if p["name"] != "Crate"])
        self.assertEqual([r[2].split(":")[0] for r in failed(res, "COVER")], ["Crate"])

    def test_art_that_stops_short_fails(self):
        parts = copy.deepcopy(GOOD)
        parts[2]["max"][1] = 0.9           # 10 cm lower than the collider
        self.assertEqual(len(failed(run(parts), "COVER")), 1)
        parts[2]["max"][1] = 0.97          # 3 cm: inside the 5 cm allowance
        self.assertEqual(failed(run(parts), "COVER"), [])

    def test_hole_in_the_floor_plan_fails(self):
        parts = [p for p in GOOD if p["name"] != "Crate"] + [box("Crate_a", (1, 0, 1), (2, 1, 1.3)), box("Crate_b", (1, 0, 1.7), (2, 1, 2))]
        res = failed(run(parts), "COVER")
        self.assertEqual(len(res), 1)
        self.assertIn("no art within 5 cm", res[0][2])

    def test_edge_walls_need_no_art(self):
        self.assertFalse(any("Edge_E" in r[2] for r in run(GOOD) if r[1] == "COVER"))

    def test_decor_does_not_cover(self):
        parts = [p for p in GOOD if p["name"] != "Crate"] + [box("decor_Crate", (1, 0, 1), (2, 1, 2))]
        self.assertEqual(len(failed(run(parts), "COVER")), 1)

    def test_tall_solid_art_without_collider_fails(self):
        parts = GOOD + [box("Statue", (-2, 0, 1), (-1.6, 1.5, 1.4))]
        res = failed(run(parts), "STRAY")
        self.assertEqual(len(res), 1)
        self.assertIn("Statue", res[0][2])

    def test_decor_and_low_and_overhead_art_may_stand_anywhere(self):
        parts = GOOD + [box("decor_Statue", (-2, 0, 1), (-1.6, 1.5, 1.4)), box("Mat", (-2, 0, 1), (-1.6, 0.15, 1.4)), box("Chandelier", (-2, 2.0, 1), (-1.6, 2.6, 1.4)),
                        box("Ceiling", (-3, 2.8, -3), (3, 3, 3))]
        self.assertEqual(failed(run(parts), "STRAY"), [])

    def test_art_may_overhang_a_collider_by_5_cm_only(self):
        parts = GOOD + [box("Handle", (2, 0.5, 1.2), (2.04, 0.9, 1.4))]
        self.assertEqual(failed(run(parts), "STRAY"), [])
        parts = GOOD + [box("Handle", (2, 0.5, 1.2), (2.12, 0.9, 1.4))]
        self.assertEqual(len(failed(run(parts), "STRAY")), 1)

    def test_blocked_arrival_point_fails(self):
        parts = GOOD + [box("Crate2", (-1.6, 0, -0.1), (-1.4, 1, 0.1))]
        world = copy.deepcopy(WORLD)
        world["colliders"].append({"s": "Crate2", "min": [-1.6, 0, -0.1], "max": [-1.4, 1, 0.1]})
        res = failed(run(parts, world), "CLEAR")
        self.assertTrue(res and "blocked by" in res[0][2], res)

    def test_door_spot_next_to_a_wall_is_clear_but_not_inside_the_walker_radius(self):
        self.assertEqual(failed(run(GOOD), "CLEAR"), [])
        world = copy.deepcopy(WORLD)
        world["colliders"].append({"s": "Wall_S", "min": [-3, 0, 2.5], "max": [3, 2.8, 2.7]})
        parts = GOOD + [box("Wall_S", (-3, 0, 2.5), (3, 2.8, 2.7))]
        self.assertTrue(any("door.at" in r[2] for r in failed(run(parts, world), "CLEAR")))

    def test_points_come_from_the_constants_and_the_markers(self):
        labels = [p[0] for p in cl.points_of(WORLD, CONST)]
        self.assertIn("marker Spawn", labels)
        self.assertIn("door.at", labels)
        self.assertIn("constants.arrive", labels)

    def test_report_exit_count(self):
        self.assertEqual(cl.report(run(GOOD)), 0)
        self.assertGreater(cl.report(run(GOOD[:1])), 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
