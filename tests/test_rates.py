import os
import unittest

from fkcore import lang, rates
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate, elaborate_file

CAT = Catalog.load()
DATA = os.path.join(os.path.dirname(__file__), "data")


def model_of(text, **kw):
    f = lang.parse(text, "t.fk")
    return rates.solve(elaborate(f, dict(f.modules), CAT, "t"), **kw)


def util(model, path):
    us = {round(model.util[k], 12) for k in model.flat.insts[path].machines}
    assert len(us) == 1, us
    return us.pop()


class RedGreenHandCalcTest(unittest.TestCase):
    """spm10's red-green core, solved by hand (tests/data/red_green.fk).

    green 6 x AM1 (6 s at speed 0.5) = 0.5/s at full speed, needing 0.5 belts and 0.5 inserters
    a second. belts: 1 craft/s makes 2 belts -> util 1/4 (0.25 iron, 0.25 gears). ins: 1 craft/s
    -> util 1/2 (0.5 iron, 0.5 gears, 0.5 circuits). circ: 2 x 1/s -> util 1/4 (0.5 iron,
    1.5 cable). cable: 4 x 2/s -> util 3/16 (0.75 copper). red 5 x 0.1/s = 0.5/s at full speed
    (0.5 copper, 0.5 gears). gears: 0.5 + 0.25 + 0.5 = 1.25 of 3/s -> util 5/12 (2.5 iron).
    iron: 2.5 + 0.5 + 0.25 + 0.5 = 3.75 of 16 x 0.3125 = 5/s -> util 3/4, ore util 3/4.
    copper: 0.75 + 0.5 = 1.25 of min(4 drills x 0.5, 6 x 0.3125) = 1.875 -> util 2/3; its ore
    1.25 of 2/s -> 5/8. Fuel: 16 x 0.0225 x 3/4 = 0.27 of 1/s; 6 x 0.0225 x 2/3 = 0.09 of 0.5/s.
    """

    def test_hand_calc(self):
        m = rates.solve(elaborate_file(os.path.join(DATA, "red_green.fk"), CAT))
        expect = {"green": 1, "red": 1, "belts": 1 / 4, "ins": 1 / 2, "circ": 1 / 4,
                  "cable": 3 / 16, "gears": 5 / 12, "iron_smelt": 3 / 4, "iron_mine": 3 / 4,
                  "copper_smelt": 2 / 3, "copper_mine": 5 / 8, "coal_iron": 0.27,
                  "coal_copper": 0.18}
        for path, u in expect.items():
            self.assertAlmostEqual(util(m, path), u, places=9, msg=path)
        self.assertAlmostEqual(m.inst_rate("red") * 60, 30.0, places=9)
        self.assertAlmostEqual(m.inst_rate("green") * 60, 30.0, places=9)
        self.assertTrue(all(ok for _t, ok, *_rest in m.asserts))
        self.assertLess(m.passes, 200)


class RuleTest(unittest.TestCase):
    SHORT = """
        src  = Chest<requester, item=iron-plate, rate=1.5/s>
        a    = AsmRow<n=1, recipe=pipe>                 # 1 iron/s at full speed
        b    = AsmRow<n=2, recipe=pipe>                 # 2 iron/s at full speed
        sink = Chest<provider>
        net iron: src -> a, b
        net pipes: a, b -> sink
    """

    def test_short_net_is_shared_in_proportion_to_appetite(self):
        m = model_of(self.SHORT)
        self.assertAlmostEqual(util(m, "a"), 0.5)
        self.assertAlmostEqual(util(m, "b"), 0.5)
        self.assertEqual(rates._why(m, "a/m0"), "iron-plate short on iron")

    def test_underfed_names_where_a_shortage_starts(self):
        # 2.0.1 (the first lead run: copper short all run, and nothing in the design said so)
        m = model_of(self.SHORT)
        self.assertEqual(rates.underfed(m), [("iron", "iron-plate", 1.5, 3.0)])
        # a short ore patch down a chain is one line, at the ore: the furnaces it starves don't
        # repeat it for the plates
        chain = model_of("""
            mine = MinerRow<n=1, resource=copper-ore>
            fuel = Chest<requester, item=coal, rate=5/s>
            smelt = SmelterRow<n=8, recipe=copper-plate, fuel=coal>
            cable = AsmRow<n=10, recipe=copper-cable>
            box = Chest<provider>
            net ore: mine -> smelt
            net coal: fuel -> smelt
            net plates: smelt -> cable
            net wire: cable -> box
        """)
        short = rates.underfed(chain)
        self.assertEqual([(n, i) for n, i, _c, _w in short], [("ore", "copper-ore")])
        # enough, or within 5%: nothing
        self.assertEqual(rates.underfed(model_of(self.SHORT.replace("rate=1.5/s", "rate=3/s"))), [])

    def test_a_consumer_limited_elsewhere_leaves_the_rest(self):
        text = self.SHORT.replace("net pipes: a, b -> sink", """
            cap = Chest<storage, rate=0.2/s>
            net pa: a -> cap
            net pb: b -> sink""")
        m = model_of(text)
        self.assertAlmostEqual(util(m, "a"), 0.2)        # its chest takes 0.2 pipes/s
        self.assertAlmostEqual(util(m, "b"), 0.65)       # (1.5 - 0.2) / 2

    def test_duty_weights_the_share(self):
        text = self.SHORT.replace("a    = AsmRow<n=1, recipe=pipe>",
                                  "a    = AsmRow<n=1, recipe=pipe, duty=0.5>")
        m = model_of(text)                                # appetites 0.5 and 2: 1.5 shared 1:4
        self.assertAlmostEqual(util(m, "a"), 0.5 * 0.6)
        self.assertAlmostEqual(util(m, "b"), 0.6)
        m = model_of(text, share="level")                 # same utilization for both
        self.assertAlmostEqual(util(m, "a"), 0.5)
        self.assertAlmostEqual(util(m, "b"), 0.5)

    def test_no_mutual_blame(self):
        # The chain that stuck the first solver: producer and consumer each blamed the other.
        m = model_of("""
            src   = Chest<requester, item=iron-plate>
            gears = AsmRow<n=3, recipe=iron-gear-wheel>
            red   = AsmRow<n=5, recipe=automation-science-pack>
            cu    = Chest<requester, item=copper-plate>
            labs  = LabRow<n=1>
            net iron: src -> gears
            net gear: gears -> red
            net copper: cu -> red
            net packs: red -> labs
        """)
        self.assertAlmostEqual(util(m, "red"), 1.0)
        self.assertAlmostEqual(util(m, "gears"), 0.5 / 3)

    def test_sink_rate_caps_the_producers(self):
        m = model_of("""
            src  = Chest<requester, item=iron-plate>
            mags = AsmRow<n=3, recipe=firearm-magazine>
            box  = Chest<storage, rate=0.2/s>
            net iron: src -> mags
            net out: mags -> box
        """)
        self.assertAlmostEqual(m.inst_rate("mags"), 0.2)
        # 2.0.24: the line says what the net takes; "not taken" read as a fault when the sink's
        # rate was simply the limit (and, with a sushi net, as if a consumed item were unwanted)
        self.assertEqual(rates._why(m, "mags/m0"), "firearm-magazine: out takes 0.20/s")

    def test_an_input_with_no_net_stops_the_machine(self):
        m = model_of("""
            src = Chest<requester, item=iron-plate>
            red = AsmRow<n=1, recipe=automation-science-pack>
            labs = LabRow<n=1>
            net x items iron-gear-wheel: src -> red
            net packs: red -> labs
        """)
        self.assertEqual(util(m, "red"), 0.0)
        self.assertEqual(rates._why(m, "red/m0"), "input copper-plate has no net")

    def test_unbounded_what_if(self):
        m = model_of(self.SHORT, unbounded=["iron"])
        self.assertAlmostEqual(util(m, "a"), 1.0)
        self.assertAlmostEqual(util(m, "b"), 1.0)
        with self.assertRaises(ValueError):
            model_of(self.SHORT, unbounded=["nope"])


class WaterfillTest(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(rates.waterfill([(1, 1), (1, 1)], 3), rates.INF)
        self.assertAlmostEqual(rates.waterfill([(1, 1), (1, 1)], 1), 0.5)
        self.assertAlmostEqual(rates.waterfill([(1, 0.1), (1, 1)], 1), 0.9)
        self.assertEqual(rates.waterfill([(1, 1)], 0), 0.0)


if __name__ == "__main__":
    unittest.main()
