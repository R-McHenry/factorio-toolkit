"""A factory's netlist on its routed layout, through the V2 flow solver (fkcore.routed, CORE-V2.md):
the routed rates and the CAPACITY lines that report_rates adds once a factory is laid out."""
import os
import unittest

from fkcore import connect, expand, fkp, lang, route, routed
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
                         [("CAPACITY", "t net cable_in"), ("CAPACITY", "t net cable_in")])
        fast, long_ = sorted((str(c) for c in self.checks), key=lambda s: "long" in s)
        self.assertIn("12.00/s required where its fast-inserters carry 2.50/s (ratio 4.80): "
                      "~cable_in/i0", fast)
        self.assertIn("3.00/s required where its long-handed-inserters carry 1.20/s (ratio 2.50)",
                      long_)
        self.assertIn("it delivers 2.50/s of copper-cable, 9.00/s nominal", fast)

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
    """The committed redgreen layout delivers what the nominal model says: no CAPACITY line. Its
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


if __name__ == "__main__":
    unittest.main()
