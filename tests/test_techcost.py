"""2.0.66 (Rory, 2026-10-29): "a tech tree scanner that can generically pick up initial cost
behind stuff like fluoroketone ... calculate the total cost in science to unlock it, and ... alter
the manhattan metric space to penalize any connections between cells with fewer corresponding
science then is required". The game side was checked on a laptop planner (Space Age): from the opus
run's base, a fluoroketone barrel is 55 techs and 76,630 packs, a step of 100; a rocket part 6."""
import random
import shutil
import tempfile
import unittest

from fkcore import explore, techcost

RED, GREEN = "automation-science-pack", "logistic-science-pack"

# a small game: plates from ore at home; gears enabled; a tech for green, one for the far thing,
# which also needs ice from a planet another tech unlocks; a barrel recipe already enabled
DATA = {
    "techs": {
        "green": {"pre": [], "packs": {RED: 75}, "unlocks": ["green"], "places": []},
        "rocketry": {"pre": ["green"], "packs": {RED: 500, GREEN: 500}, "unlocks": ["fuel"],
                     "places": []},
        "cold-planet": {"pre": ["rocketry"], "packs": {RED: 1000, GREEN: 1000},
                        "unlocks": [], "places": ["cold"]},
        "egg-tech": {"pre": [], "packs": {RED: 10}, "unlocks": ["egg"], "places": []},
        "trigger": {"pre": [], "packs": {}, "unlocks": ["boiler"], "places": [],
                    "trigger": "craft-item", "trigger_item": "gear"},
        "endless": {"pre": [], "packs": {RED: 1}, "unlocks": [], "places": [], "infinite": True},
    },
    "recipes": {
        "plate": {"ins": ["ore"], "outs": ["plate"], "default": True},
        "gear": {"ins": ["plate"], "outs": ["gear"], "default": True},
        "green": {"ins": ["gear"], "outs": [GREEN], "default": False},
        "red": {"ins": ["gear"], "outs": [RED], "default": True},
        "fuel": {"ins": ["plate", "ice"], "outs": ["fuel"], "default": False},
        "barrel": {"ins": ["fuel"], "outs": ["fuel-barrel"], "default": True},
        "egg": {"ins": ["egg"], "outs": ["egg"], "default": False},
        "boiler": {"ins": ["plate"], "outs": ["boiler"], "default": False},
    },
    "resources": {"ore-patch": ["ore"], "ice-patch": ["ice"]},
    "tile_fluids": {},
    "planets": {"nauvis": {"entities": ["ore-patch"], "tiles": []},
                "cold": {"entities": ["ice-patch"], "tiles": []}},
    "chunks": [], "collectors": [], "turns": [["fuel", "ash"]],
}


class TreeTest(unittest.TestCase):
    def setUp(self):
        self.tree = techcost.Tree(DATA)

    def need(self, item, researched=()):
        c = self.tree.costs(set(researched))
        return self.tree.packs(c[item]) if item in c else None

    def test_what_it_costs_from_nothing(self):
        self.assertEqual(self.need("plate"), {})
        self.assertEqual(self.need(GREEN), {RED: 75})
        # an enabled barrel recipe costs what its contents cost: the planet, and what leads to it
        self.assertEqual(self.need("fuel-barrel"), {RED: 1575, GREEN: 1500})
        self.assertEqual(self.need("ash"), self.need("fuel"))      # it burns or spoils into it
        self.assertEqual(self.need("boiler"), {})                  # a trigger: make a gear
        self.assertEqual(self.need("egg"), {RED: 10})              # it breeds: no egg first

    def test_what_is_researched_is_free(self):
        self.assertEqual(self.need("fuel-barrel", {"green", "rocketry"}), {RED: 1000, GREEN: 1000})
        self.assertEqual(self.need("fuel-barrel", {"green", "rocketry", "cold-planet"}), {})


class MetricTest(unittest.TestCase):
    def test_a_step_costs_the_science_levels_the_cell_lacks(self):
        need = {RED: 1575, GREEN: 1500}
        made = {RED: 500, GREEN: 0}
        levels = {RED: 8, "plate": 12}                  # 500 red made: level 8
        # red: floor(log2(500 + 1575)) = 11, 3 short; green: floor(log2(1500)) = 10, 11 short
        self.assertEqual(explore.deficit(levels, made, need, 2), 3 + 11)
        self.assertEqual(explore.step_cost(levels, "fuel-barrel", need, made, 2), 15)
        self.assertEqual(explore.step_cost(levels, "plate", None, made, 2), 1)   # already made
        self.assertIsNone(explore.step_cost(levels, "nothing", None, made, 2))
        self.assertEqual(explore.step_cost(levels, "gear", {}, made, 2), 1)

    def test_the_walk_keeps_far_items_out_of_a_short_goal(self):
        d = tempfile.mkdtemp(prefix="fktech-")
        self.addCleanup(shutil.rmtree, d, True)
        a = explore.Archive(d)
        tree = techcost.Tree(DATA)
        needs = {i: tree.packs(t) for i, t in tree.costs(set()).items()}
        go = {"plate": 12, "gear": 10, RED: 8}
        made = {"plate": 5000, "gear": 1100, RED: 500}
        seen = set()
        for k in range(300):
            goal = a.pick_goal(go, [], 4, random.Random(k), needs=needs, made=made)
            seen |= set(goal)
            self.assertNotIn("fuel-barrel", goal)       # 15 steps, more than the walk has
        self.assertIn(GREEN, seen)                      # 75 red: no science level short
        far = set()
        for k in range(300):
            far |= set(a.pick_goal(go, [], 40, random.Random(k), needs=needs, made=made))
        self.assertIn("fuel-barrel", far)               # within a long enough walk


if __name__ == "__main__":
    unittest.main()
