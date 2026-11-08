"""A factory's netlist on its routed layout, through the V2 flow solver (fkcore.routed, CORE-V2.md):
the routed rates and the too-thin lines that report_rates adds once a factory is laid out."""
import os
import unittest

from fkcore import avail, connect, expand, fkp, lang, route, routed
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate, elaborate_file

CAT = Catalog.load()
REDGREEN = os.path.join(os.path.dirname(__file__), "..", "games", "redgreen")

#: four green-circuit assemblers fed from two requester chests: the cables come through one fast
#: inserter (2.5/s) and reach each assembler by a long-handed inserter (1.2/s), where an
#: assembler-1 on green circuits wants 3/s
CIRCUITS = """
cables = Chest<requester, item=copper-cable, rate=20/s> @(2, 2)
plates = Chest<requester, item=iron-plate, rate=10/s>   @(2, 6)
circ   = AsmRow<n=4, recipe=electronic-circuit>         @(8, 2)
box    = Chest<provider, rate=3/s>                      @(2, 14)
net cable_in: cables -> circ
net plate_in: plates -> circ
net circuits: circ -> box
"""


class CircuitRowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        avail.install(None)     # nothing read (another test's snapshot would size the hands: route._TAPS)
        f = lang.parse(CIRCUITS, "t.fk")
        cls.flat = elaborate(f, dict(f.modules), CAT, "t")
        lay, _notes = expand.expand_factory(cls.flat, CAT)
        cls.lay = route.route_layout(cls.flat, lay, CAT).layout
        cls.r = routed.solve(cls.flat, cls.lay, CAT)
        cls.lines, cls.checks = routed.report(cls.r, "t")

    def test_the_layout_connects(self):
        rep = connect.connect(self.lay, CAT, connect.endpoints(self.flat))
        self.assertEqual({n.status for n in rep.nets.values()}, {"connected"})

    def test_the_inserters_bind(self):
        self.assertEqual([(c.code, c.where) for c in self.checks],
                         [("too-thin", "t net cable_in"), ("too-thin", "t net cable_in")])
        fast, long_ = sorted((str(c) for c in self.checks), key=lambda s: "long" in s)
        # what the design asks: the row at its nominal 0.75, 9 cables/s, 2.25 an assembler
        self.assertIn("9.00/s required where its fast-inserters carry 2.50/s (ratio 3.60): "
                      "~cable_in/i0", fast)
        self.assertIn("2.25/s required where its long-handed-inserters carry 1.20/s (ratio 1.88)",
                      long_)
        self.assertIn("it delivers 2.50/s of copper-cable to its consumers, 9.00/s nominal", fast)

    def test_routed_rates(self):
        # the chest's one inserter lets 2.5 cables/s through: 0.83 circuits/s where 3 are nominal;
        # belt order gives the first two assemblers all their long-handed inserters carry
        made = sum(self.r.util(k) for k in self.flat.insts["circ"].machines)
        self.assertAlmostEqual(made, 2.5 / 3, places=3)
        self.assertAlmostEqual(self.r.model.util["circ/m0"], 0.75)
        self.assertEqual([round(self.r.util(f"circ/m{k}"), 3) for k in range(2)], [0.4, 0.4])
        row = next(l for l in self.lines if l.strip().startswith("circ "))
        self.assertIn("4 of 4 starved of copper-cable", row)

    def test_more_hand_lifts_it(self):
        # a force with the inserter capacity research (hand 2): 5 cables/s through the chest's
        # inserter, 2.4 into each assembler
        r = routed.solve(self.flat, self.lay, CAT, hand=2)
        made = sum(r.util(k) for k in self.flat.insts["circ"].machines)
        self.assertAlmostEqual(made, 5.0 / 3, places=3)


class RedgreenRoutedTest(unittest.TestCase):
    """The committed redgreen layout delivers what the nominal model says: no too-thin line. Its
    circuit row's long-handed cable inserters (1.2/s) do bind one assembler, but the other takes
    up its share (belt order), so nothing downstream is short."""

    @classmethod
    def setUpClass(cls):
        cls.flat = elaborate_file(os.path.join(REDGREEN, "main.fk"), CAT)
        cls.lay = fkp.load(os.path.join(REDGREEN, "main.fkp"))
        cls.r = routed.solve(cls.flat, cls.lay, CAT)
        cls.lines, cls.checks = routed.report(cls.r, "main")

    def test_no_capacity_line(self):
        self.assertEqual(self.checks, [])
        self.assertTrue(self.lines[0].startswith("routed main (V2: the lanes and inserters as laid)"))

    def test_every_row_runs_as_nominal(self):
        for path, inst in self.flat.insts.items():
            us = [self.r.util(k) for k in inst.machines if self.r.util(k) is not None]
            if not us:
                continue
            nominal = min(self.r.model.util[k] for k in inst.machines)
            self.assertAlmostEqual(sum(us) / len(us), nominal, delta=2e-3, msg=path)

    def test_the_circuit_rows_cable_inserter_binds_one_assembler(self):
        self.assertTrue(self.r.res.binds(("circ/l1", "")))
        self.assertEqual(sorted(round(self.r.util(f"circ/m{k}"), 3) for k in range(2)),
                         [0.1, 0.4])

    def test_the_machines_settle(self):
        res = self.r.res
        self.assertTrue(res.settled)
        self.assertLess(res.outer, 80)
        self.assertIn(f"the machines settled in {res.outer} rounds", self.lines[0])


def _routed(src):
    f = lang.parse(src, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay, _notes = expand.expand_factory(flat, CAT)
    lay = route.route_layout(flat, lay, CAT).layout
    return routed.solve(flat, lay, CAT)


class CouplingTest(unittest.TestCase):
    """The machine coupling settles where the carriers hold a machine (lead review of 1.4)."""

    def test_a_maker_held_by_its_output_inserter(self):
        # an assembler-1 on cables makes 2/s, and its plain output inserter takes 0.857/s: it runs
        # at 0.429. 1.4 gave its input no share of the machine's capacity (inf x 0 = nan), so its
        # plates stopped every few rounds and it swung around 0.59
        r = _routed("""
plates = Chest<requester, item=copper-plate, rate=10/s> @(2, 2)
cable  = AsmRow<n=1, recipe=copper-cable, inserter=inserter> @(8, 2)
box    = Chest<provider> @(2, 12)
net plate_in: plates -> cable
net cab: cable -> box
""")
        self.assertTrue(r.res.settled)
        self.assertAlmostEqual(r.util("cable/m0"), 60 / 70 / 2, places=4)
        self.assertEqual(r.res.limits(("cable/m0", "")), [("out", "copper-cable")])

    def test_a_requester_feeds_each_item_on_its_own(self):
        # one requester puts 0.05/s of each part on; an engine assembler wants 0.15 pipes/s, so it
        # runs at a third, held by its pipes. 1.4 tied the chest's items together like a recipe's,
        # and the chest and the engine held each other down to nothing
        r = _routed("""
parts = Chest<requester, item="steel-plate,pipe,iron-gear-wheel", rate=0.05/s> @(2, 2)
eng   = AsmRow<n=1, recipe=engine-unit, machine=assembling-machine-2> @(8, 2)
box   = Chest<provider> @(2, 12)
net engin: parts -> eng
net engs: eng -> box
""")
        self.assertTrue(r.res.settled)
        self.assertAlmostEqual(r.util("eng/m0"), 1 / 3, places=4)
        self.assertEqual(r.res.limits(("eng/m0", "")), [("in", "pipe")])
        lines, _checks = routed.report(r, "t")
        row = next(l for l in lines if l.strip().startswith("eng "))
        self.assertIn("1 of 1 starved of pipe", row)
        self.assertAlmostEqual(r.util("parts/c0"), 0.5, places=4)    # its pipes all go

    def test_an_overflow_chest_is_no_consumer(self):
        # copper for a cable maker, and the rest into a chest without a rate. 1.4 asked the
        # chest's inserter for the whole surplus (10/s), called it binding, and named the cable
        # maker short of copper, which its own output inserter holds
        r = _routed("""
plates = Chest<requester, item=copper-plate, rate=10/s> @(2, 2)
cable  = AsmRow<n=1, recipe=copper-cable, inserter=inserter> @(8, 2)
box    = Chest<provider> @(2, 14)
cbox   = Chest<provider> @(16, 14)
net cu: plates -> cable, box
net cab: cable -> cbox
""")
        self.assertEqual(r.asked(("box/c0", "")), 0.0)
        _lines, checks = routed.report(r, "t")
        self.assertEqual([c.where for c in checks], ["t net cab"])     # the chest at its end
        self.assertIn("cable/o0; it delivers 0.86/s of copper-cable to its consumers, 2.00/s "
                      "nominal; cbox/c0 gets 0.86/s, 2.00/s nominal", str(checks[0]))

    def test_a_fluid_holds_a_machine_and_an_unbounded_requester_gives_what_it_needs(self):
        # 5 gas/s for a plastic plant that wants 20/s: it runs at 0.25 (V1's nominal), and the
        # coal requester without a rate is asked for what that takes
        r = _routed("""
gas   = InfinityPipe<fluid=petroleum-gas, rate=5/s> @(0, 0)
coal  = Chest<requester, item=coal> @(2, 8)
plast = Assembler<recipe=plastic-bar, machine=chemical-plant> @(6, 2)
box   = Chest<provider> @(14, 8)
net gasn: gas -> plast
net coaln: coal -> plast
net plastic: plast -> box
""")
        self.assertAlmostEqual(r.base["plast/m0"], 0.25, places=6)
        self.assertAlmostEqual(r.util("plast/m0"), 0.25, places=6)
        lines, checks = routed.report(r, "t")
        self.assertEqual(checks, [])
        coal = next(l for l in lines if l.strip().startswith("coaln "))
        self.assertIn("0.250/s required of 2.500/s", coal)          # not "unbounded"

    def test_not_settled_says_so(self):
        r = _routed(CIRCUITS)
        r.res.settled, r.res.outer, r.res.moved = False, 80, 0.0123
        lines, _checks = routed.report(r, "t")
        self.assertIn("the machines did NOT settle in 80 rounds (a utilization still moves by "
                      "0.0123 a round): the routed rates are approximate", lines[0])


if __name__ == "__main__":
    unittest.main()
