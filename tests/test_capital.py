"""fkcore.capital on fixture reads (no game): the working capital and its parts."""
import os
import tempfile
import unittest

from fkcore import capital
from fkcore.catalog import Catalog

CAT = Catalog.load()

# the shape of lua_read: two assemblers (one ran), a drill that stood, robots, stock, research
RAW = {
    "tick": 36000, "force": "player", "surface": "nauvis",
    "rows": [
        {"u": 1, "n": "assembling-machine-2", "t": "assembling-machine", "z": 0, "st": "working",
         "pf": 130, "rc": "iron-gear-wheel", "e": 0.5, "sp": 0.75},
        {"u": 2, "n": "assembling-machine-2", "t": "assembling-machine", "z": 0,
         "st": "item_ingredient_shortage", "pf": 10, "rc": "iron-gear-wheel", "e": 0.5, "sp": 0.75,
         "m": {"speed-module": 1}},
        {"u": 3, "n": "electric-mining-drill", "t": "mining-drill", "z": 0, "st": "waiting_for_space_in_destination"},
        {"u": 4, "n": "assembling-machine-2", "t": "assembling-machine", "z": 1, "st": "no_power",
         "pf": 0, "rc": "copper-cable", "e": 0.5, "sp": 0.75},
    ],
    "items": {"0": {"iron-plate": 400, "logistic-robot": 2}, "1": {"copper-plate": 100}},
    "placed": {"0": {"transport-belt": 100, "inserter": 10}},
    "port": {"0": {"construction-robot": 6}},
    "flying": {"0": {"construction-robot": 4}},
    "techs": {
        "automation": {"packs": {"automation-science-pack": 10}, "un": ["assembling-machine-1",
                                                                         "long-handed-inserter"]},
        "automation-2": {"packs": {"automation-science-pack": 40, "logistic-science-pack": 40},
                         "un": ["assembling-machine-2"]},
        "oil-processing": {"packs": {"automation-science-pack": 100, "logistic-science-pack": 100},
                           "un": ["oil-refinery", "chemical-plant"]},
        "physical-projectile-damage-1": {"packs": {"automation-science-pack": 10},
                                         "fx": ["ammo-damage", "turret-attack"]},
        "steam-power": {"packs": {}, "un": ["boiler"]},
    },
    "research": {"name": "logistics-2", "pct": 0.5,
                 "packs": {"automation-science-pack": 200, "logistic-science-pack": 200}},
}
# the read before, 30 s earlier: assembler 1 made 30 gears since (30 x 0.5 / 0.75 = 20 s of 30)
LAST = {"tick": 34200, "crafts": {"1": [100, "iron-gear-wheel"], "2": [10, "iron-gear-wheel"]},
        "robots": {"construction-robot": 0.2}}


class CapitalTest(unittest.TestCase):
    def setUp(self):
        self.cap = capital.score(RAW, CAT, LAST, whys=["cable row, waiting for power"])

    def test_machines(self):
        p = self.cap.parts["machines"]
        a2, drill, sm = 54.0, 27.5, 52.5
        self.assertAlmostEqual(p["total"], 2 * a2 + sm + drill)
        self.assertAlmostEqual(p["working"], a2 * 2 / 3)
        self.assertEqual(self.cap.makers, (1, 3))
        self.assertIn("waiting_for_space_in_destination", self.cap.stood)

    def test_robots_average_two_reads(self):
        p = self.cap.parts["robots"]
        r = 10 * capital.cost.item_cost(CAT, "construction-robot")
        self.assertAlmostEqual(p["total"], r)
        self.assertAlmostEqual(p["working"], r * (0.4 + 0.2) / 2)
        self.assertEqual(self.cap.robot_share, {"construction-robot": 0.4})

    def test_stock_is_idle_and_parked_left_out(self):
        p = self.cap.parts["stock"]
        self.assertEqual(p["working"], 0.0)
        self.assertEqual(self.cap.piles[0][1], "iron-plate")
        # the parked assembler and the parked copper plates: on neither side
        self.assertAlmostEqual(self.cap.parked, 54.0 + 100)
        self.assertEqual(self.cap.parks, [(154.0, "cable row, waiting for power")])
        self.assertGreater(self.cap.infra, 0)

    def test_research(self):
        unused = [t for _r, t in self.cap.unused]
        # automation-2: an assembler 2 works; automation: long-handed inserters? none placed,
        # assembler 1 none: unused; oil: unused; projectile damage: military, no turret
        self.assertNotIn("automation-2", unused)
        self.assertIn("oil-processing", unused)
        self.assertIn("automation", unused)
        self.assertIn("physical-projectile-damage-1", unused)
        dmg = dict((t, r) for r, t in self.cap.unused)["physical-projectile-damage-1"]
        self.assertAlmostEqual(dmg, 10 * 3.0 * capital.MILITARY_WEIGHT)
        self.assertEqual(self.cap.techs, (1, 4))            # steam power took no packs
        self.assertEqual(self.cap.research[0], "logistics-2")
        self.assertAlmostEqual(self.cap.research[1], 0.5 * (200 * 3 + 200 * 7))

    def test_weights(self):
        cap = capital.score(RAW, CAT, LAST, weights={"oil-processing": 0})
        self.assertNotIn("oil-processing", [t for _r, t in cap.unused])

    def test_share_and_lines(self):
        cap = self.cap
        self.assertAlmostEqual(cap.share, cap.working / (cap.working + cap.idle))
        text = "\n".join(capital.lines(cap, None, "nauvis"))
        self.assertIn("parked 1:", text)
        self.assertIn("unused: oil-processing", text)
        self.assertTrue(capital.line(cap).startswith("working capital "))

    def test_first_read_goes_by_status(self):
        cap = capital.score(RAW, CAT, None)
        self.assertAlmostEqual(cap.parts["machines"]["working"], 54.0)

    def test_growth(self):
        hist = [(0, 100.0, 1000.0), (36000, 150.0, 1000.0)]
        mins, span, _ = capital.growth(hist, 108000, 200.0)
        self.assertAlmostEqual(span, 30.0)                   # nearest half an hour back: tick 0
        self.assertAlmostEqual(mins, 30.0)                   # 100 -> 200 in 30 min
        self.assertEqual(capital.growth(hist, 108000, 100.0)[0], None)  # shrank
        self.assertIsNone(capital.growth([], 108000, 100.0))

    def test_store(self):
        with tempfile.TemporaryDirectory() as d:
            st = capital.Store(d)
            st.keep(self.cap)
            self.assertEqual(st.last()["tick"], 36000)
            self.assertEqual(st.history()[0][0], 36000)
            cfg = st.config
            cfg["parked"].append({"area": [0, 0, 10, 10], "why": "x"})
            st.save_config(cfg)
            self.assertEqual(capital.Store(d).config["parked"][0]["why"], "x")
            self.assertTrue(os.path.exists(os.path.join(d, "out", "capital", "park.json")))


if __name__ == "__main__":
    unittest.main()
