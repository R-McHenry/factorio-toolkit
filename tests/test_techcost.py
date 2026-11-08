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


def worth_data():
    """DATA with amounts: 1 ore -> 1 plate, 2 plates -> 1 gear, 1 gear -> 1 red; green 2 gears;
    fuel 1 plate + 4 ice -> 2; and a cheap far route to plates (1 ice -> 10 plates) that home's
    price must not take."""
    import copy
    d = copy.deepcopy(DATA)
    amounts = {"plate": ({"ore": 1}, {"plate": 1}), "gear": ({"plate": 2}, {"gear": 1}),
               "green": ({"gear": 2}, {GREEN: 1}), "red": ({"gear": 1}, {RED: 1}),
               "fuel": ({"plate": 1, "ice": 4}, {"fuel": 2}),
               "barrel": ({"fuel": 1}, {"fuel-barrel": 1}), "egg": ({"egg": 1}, {"egg": 2}),
               "boiler": ({"plate": 5}, {"boiler": 1})}
    for name, (ina, outa) in amounts.items():
        d["recipes"][name]["ina"], d["recipes"][name]["outa"] = ina, outa
    d["recipes"]["ice-plates"] = {"ins": ["ice"], "outs": ["plate"], "ina": {"ice": 1},
                                  "outa": {"plate": 10}, "default": True}
    return d


class WorthTest(unittest.TestCase):
    """2.0.67 (Rory: "make sure that the positive material axis and the research axis fold into
    the same dimension, so getting more of an item is always still counting as pushing the game
    forward far past the last research")."""

    def test_worth_in_raw_units_from_home_first(self):
        v = techcost.Tree(worth_data()).values()
        self.assertEqual((v["ore"], v["plate"], v["gear"], v[RED], v[GREEN]), (1, 1, 2, 2, 4))
        self.assertEqual(v["fuel"], 2.5)                       # (1 plate + 4 ice) / 2
        self.assertEqual(v["ice"], 1)                          # off-world, priced after home
        self.assertEqual(v["egg"], 0)                          # it breeds: nothing in, net

    def test_power_keeps_a_breeding_loop_above_nothing(self):
        # 3.0 (Rory, 11-02: "adding power consumption in as some cost"): with each craft's
        # power, the egg that breeds costs its craft (2 s at 150 kW = 0.3 MJ, over 2 eggs net 1)
        d = worth_data()
        for r in d["recipes"].values():
            r["energy"], r["jps"] = 1.0, 100e3
        d["recipes"]["egg"]["energy"], d["recipes"]["egg"]["jps"] = 2.0, 150e3
        v = techcost.Tree(d).values()
        self.assertAlmostEqual(v["egg"], 0.3)
        self.assertAlmostEqual(v["plate"], 1.1)                # 1 ore + 0.1 MJ
        self.assertAlmostEqual(v["gear"], 2 * 1.1 + 0.1)

    def test_vertical_folds_research_into_material(self):
        tree = techcost.Tree(worth_data())
        base = explore.vertical({"plate": 10, "gear": 8}, tree, 2)
        more = explore.vertical({"plate": 12, "gear": 8}, tree, 2)
        self.assertGreater(more, base)                         # more of an item: always higher
        far = explore.vertical({"plate": 10, "gear": 8, "fuel-barrel": 0}, tree, 2)
        # one barrel implies the planet's research: 1575 red, 1500 green beyond what was made
        self.assertGreater(far, base + 1)
        self.assertEqual(explore.vertical({}, tree, 2), 0.0)

    def test_positions_and_the_track_pick(self):
        d = tempfile.mkdtemp(prefix="fktech-")
        self.addCleanup(shutil.rmtree, d, True)
        a = explore.Archive(d)
        import json
        import os
        os.makedirs(a.root)
        with open(os.path.join(a.root, "techtree.json"), "w") as fh:
            json.dump(worth_data(), fh)
        rows = {"r": {"plate": 5}, "a": {"plate": 8}, "b": {"plate": 11, "gear": 6},
                "side": {"plate": 5, "boiler": 3}}
        paths = {"r": ["r"], "a": ["r", "a"], "b": ["r", "a", "b"], "side": ["r", "side"]}
        keys = {n: explore.key(lv) for n, lv in rows.items()}
        for n, lv in rows.items():
            a.cells[keys[n]] = {"levels": lv, "tick": 100, "save": n, "traj": [],
                                "path": [keys[p] for p in paths[n]]}
        pos, path = a.positions()
        self.assertEqual(path, [keys["r"], keys["a"], keys["b"]])
        self.assertEqual(pos[keys["b"]][1], 0)
        self.assertEqual(pos[keys["side"]][1], 4)              # 3 levels of boiler, from -1
        self.assertGreater(pos[keys["b"]][0], pos[keys["a"]][0])
        a.data["settings"] = {"pick": "track"}
        got = {a.pick_go(random.Random(k)) for k in range(200)}
        self.assertEqual(got, set(keys.values()))              # every band is picked from


class CoordinatesTest(unittest.TestCase):
    """2.0.68 (Rory: "make both the go and explore actions be based on selecting cells using these
    coordinates as a basis")."""

    def archive(self):
        import json
        import os
        d = tempfile.mkdtemp(prefix="fktech-")
        self.addCleanup(shutil.rmtree, d, True)
        a = explore.Archive(d)
        os.makedirs(a.root)
        data = worth_data()
        data["fluids"] = ["steam"]
        data["recipes"]["boil"] = {"ins": ["plate"], "outs": ["steam"], "ina": {"plate": 1},
                                   "outa": {"steam": 10}, "default": True}
        with open(os.path.join(a.root, "techtree.json"), "w") as fh:
            json.dump(data, fh)
        return a

    def test_the_incremental_worth_is_vertical(self):
        tree = techcost.Tree(worth_data())
        go = {"plate": 10, "gear": 8, RED: 3}
        w = explore.Worth(tree, 2, go)
        self.assertAlmostEqual(w.now, explore.vertical(go, tree, 2))
        for item in ("plate", RED, GREEN, "fuel-barrel", "boiler"):
            lv = dict(go)
            lv[item] = lv.get(item, -1) + 1
            self.assertAlmostEqual(w.after(item), explore.vertical(lv, tree, 2), msg=item)
        w.apply("fuel-barrel")
        w.apply(GREEN)
        lv = dict(go, **{"fuel-barrel": 0, GREEN: 0})
        self.assertAlmostEqual(w.now, explore.vertical(lv, tree, 2))
        self.assertIsNone(w.after("nothing"))

    def test_a_goal_rises_by_its_rise_and_never_far(self):
        a = self.archive()
        tree = a.tree()
        needs = {i: tree.packs(t) for i, t in tree.costs(set()).items()}
        go = {"plate": 10, "gear": 8, RED: 3}
        v0 = explore.vertical(go, tree, 2)
        a.data["settings"] = {"rise": 0.3, "steps": 12}
        for k in range(30):
            goal = a.pick_goal_vh(go, needs, {}, random.Random(k))
            self.assertTrue(goal)
            self.assertNotIn("fuel-barrel", goal)          # its research overshoots 2 x rise
            self.assertNotIn("steam", goal)                # a fluid: cells count items only
            v = explore.vertical(dict(go, **goal), tree, 2)
            self.assertTrue(v0 < v <= v0 + 0.6 + 1e-9, (goal, v0, v))

    def test_go_is_uniform_over_the_maps_bins(self):
        a = self.archive()
        rows = {"r": {"plate": 5}, "a": {"plate": 8}, "a2": {"plate": 8, "gear": 0},
                "a3": {"plate": 8, "gear": 1}, "side": {"plate": 5, "boiler": 3}}
        paths = {"r": ["r"], "a": ["r", "a"], "a2": ["r", "a", "a2"],
                 "a3": ["r", "a", "a2", "a3"], "side": ["r", "side"]}
        keys = {n: explore.key(lv) for n, lv in rows.items()}
        for n, lv in rows.items():
            a.cells[keys[n]] = {"levels": lv, "tick": 100, "save": n, "traj": [],
                                "path": [keys[p] for p in paths[n]]}
        got = {a.pick_go(random.Random(k)) for k in range(300)}
        self.assertEqual(got, set(keys.values()))


if __name__ == "__main__":
    unittest.main()
