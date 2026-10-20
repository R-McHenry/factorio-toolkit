"""The paper acceptance case (CORE-V1.md §12 step 2): spm10 as one V1 factory."""
import os
import unittest
from fractions import Fraction as F

from fkcore import rates
from fkcore.catalog import Catalog
from fkcore.elaborate import ADVICE, elaborate_file

CAT = Catalog.load()
HERE = os.path.dirname(__file__)
MAIN = os.path.join(HERE, "..", "games", "spm10", "main.fk")


class Spm10Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flat = elaborate_file(MAIN, CAT)
        cls.model = rates.solve(cls.flat)

    def per_min(self, model, path):
        return model.inst_rate(path) * 60

    def test_shape(self):
        flat = self.flat
        self.assertEqual(len(flat.machines), 142)       # spm10's machines, one key each
        self.assertEqual(len(flat.nets), 38)
        kinds = {i.kind for i in flat.insts.values()}
        self.assertFalse(kinds & {"BeltSplit", "LaneMerge", "ChestTap", "ChestEnd"})
        self.assertEqual([c.code for c in flat.checks if c.code not in ADVICE],
                         ["UNBOUNDED"])  # the packed circuit chest

    def test_nets_never_merge(self):
        # v4's model joined the cable, circuit, gear and pipe nets through the spine adapters into
        # one node ("main.cable.out copper-cable|electronic-circuit|iron-gear-wheel|pipe").
        items = {n: net.items for n, net in self.flat.nets.items()}
        self.assertEqual(items["cable_"], ["copper-cable"])
        self.assertEqual(items["circuit"], ["electronic-circuit"])
        self.assertEqual(items["gear"], ["iron-gear-wheel"])
        self.assertEqual(items["pipe"], ["pipe"])
        self.assertEqual(items["packs"], ["automation-science-pack", "logistic-science-pack"])
        sushi = sorted(n for n, net in self.flat.nets.items() if net.sushi)
        self.assertEqual(sushi, ["mall_out", "packs"])

    def test_sushi_sink_quiet_on_the_mall_chest(self):
        self.assertEqual(len(self.flat.nets["mall_out"].items), 20)
        self.assertNotIn("SUSHI_SINK", [c.code for c in self.flat.checks])

    def test_sushi_sink_fires_on_a_bad_sushi_input(self):
        bad = elaborate_file(os.path.join(HERE, "data", "bad_sushi.fk"), CAT)
        hits = [c for c in bad.checks if c.code == "SUSHI_SINK"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].where, "net feed")
        self.assertEqual(hits[0].msg, "pipes does not take iron-gear-wheel")

    def test_red_and_green_meet_10_per_min(self):
        m = self.model
        self.assertLess(m.passes, 1000)
        self.assertLess(m.residual, 1e-9)
        verdict = {text.split(".")[0]: ok for text, ok, *_r in m.asserts}
        self.assertEqual(verdict, {"red": True, "green": True, "blue": False})
        self.assertGreaterEqual(self.per_min(m, "red"), 10)
        self.assertGreaterEqual(self.per_min(m, "green"), 10)

    def test_iron_is_the_binding_net_and_balances(self):
        m = self.model
        st = m.nets[("iron_plate", "iron-plate")]
        self.assertAlmostEqual(st.supply, 5.0)          # 10 drills x 0.5 = 16 furnaces x 0.3125
        self.assertGreater(st.would_take, 2 * st.supply)  # the consumers would take > 10/s
        taken = sum(m.flat.machines[k].needs["iron-plate"] * m.util[k]
                    for k, _i in m.flat.nets["iron_plate"].consumers
                    if "iron-plate" in m.flat.machines[k].needs)
        self.assertAlmostEqual(taken, 5.0, places=6)    # every plate is used; bots_iron gets none
        self.assertAlmostEqual(st.to_sinks, 0.0, places=6)

    def test_plates_unbounded_hand_calc(self):
        m = rates.solve(self.flat, unbounded=["iron_plate", "copper_plate"])
        self.assertAlmostEqual(self.per_min(m, "red"), 30.0, places=6)
        self.assertAlmostEqual(self.per_min(m, "green"), 30.0, places=6)
        # Blue, by hand. Adv circuits (3 AM1 = 0.25/s, at full speed) are shared by blue (0.25/s at
        # full speed) and the mall's roboports (4.5/s x duty 0.02); steel (8 furnaces = 0.5/s) by
        # the engines (blue's 2 engines per craft: 1/6 x La of 0.2/s), the land-mine assembler
        # (0.1/s), the mall's two steel-chest cells (8/s x 0.02 each), the roboports and the medium
        # poles (0.02/s, limited by sticks). Storage + requester chests run on the steel chests
        # schest_i makes (0.02 Ls). La, Ls = the adv and steel levels:
        #   adv:   (1/4 + 9/100) La + (2/100) Ls = 1/4
        #   steel: (1/6 + 9/100) La + (1/10 + 32/100) Ls + 2/100 = 1/2
        a1, b1, c1 = F(1, 4) + F(9, 100), F(2, 100), F(1, 4)
        a2, b2, c2 = F(1, 6) + F(9, 100), F(1, 10) + F(32, 100), F(1, 2) - F(2, 100)
        la = (c1 * b2 - b1 * c2) / (a1 * b2 - b1 * a2)
        ls = (a1 * c2 - c1 * a2) / (a1 * b2 - b1 * a2)
        self.assertAlmostEqual(self.per_min(m, "blue"), float(10 * la), places=6)
        self.assertAlmostEqual(util(m, "oil/mine"), float(ls), places=6)
        self.assertAlmostEqual(util(m, "adv"), 1.0, places=9)
        self.assertAlmostEqual(util(m, "steel"), 1.0, places=9)


def util(model, path):
    return model.util[model.flat.insts[path].machines[0]]


if __name__ == "__main__":
    unittest.main()
