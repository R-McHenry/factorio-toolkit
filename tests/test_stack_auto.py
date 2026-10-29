"""2.0.59 (Rory, 2026-10-29: "it should have the rate model, and just optimise the params to get the
desired rate"): a Stack's ``n=auto``. The size step searches the Stacks' counts on the rate model:
the fewest cells that meet every target, assert and what the line's consumers ask."""
import os
import shutil
import tempfile
import unittest

from fkcore import size
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate_file

CAT = Catalog.load()
CELLS = os.path.join(os.path.dirname(__file__), "..", "kickoff", "template", "game", "cells.fk")

FURNACES = """import FurnaceCell from "cells.fk"
ore = Chest<requester, item=iron-ore, rate=5/s> @(10, 2)
col = Stack<cell=FurnaceCell, n=auto {bounds}> @(10, 8)
{tail}
"""
INTO_GEARS = """gears = Assembler<recipe=iron-gear-wheel, machine=assembling-machine-2> @(30, 70)
box = Chest<provider> @(40, 80)
net o: ore -> col.ore_in
net p: col.pl_out -> gears
net g: gears -> box"""
INTO_A_CHEST = """box = Chest<provider> @(40, 80)
net o: ore -> col.ore_in
net p: col.pl_out -> box
assert col.rate >= 2/s"""


class StackAutoTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkstackauto-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        shutil.copy(CELLS, self.dir)

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def sized(self, text):
        sz = size.size({"t": size.maker(self.write("t.fk", text), CAT)})
        return sz, {r.path: r for r in sz.rows}

    def test_elaborated_at_the_low_bound_or_the_size_steps_count(self):
        path = self.write("t.fk", FURNACES.format(bounds="2..20", tail=INTO_GEARS))
        flat = elaborate_file(path, CAT)
        self.assertEqual((flat.insts["col"].params["n"], flat.insts["col"].auto), (2, (2, 20)))
        flat = elaborate_file(path, CAT, sizes={"col": 6})
        self.assertEqual(len([p for p in flat.insts if p.count("/") == 1
                              and p.startswith("col/")]), 6)

    def test_sized_to_what_its_consumer_asks(self):
        # an assembling-machine-2 on gears takes 3 plates/s: five cells (3.125/s), not four
        sz, rows = self.sized(FURNACES.format(bounds="1..20", tail=INTO_GEARS))
        self.assertEqual((rows["col"].kind, rows["col"].n), ("Stack", 5))
        self.assertTrue(all(w.ok for w in sz.wants))
        self.assertIn("net p: iron-plate for gears", size.report(sz, CAT)[0][4])

    def test_sized_to_an_assert(self):
        sz, rows = self.sized(FURNACES.format(bounds="1..20", tail=INTO_A_CHEST))
        self.assertEqual(rows["col"].n, 4)                  # 2.5 plates/s; three make 1.875
        self.assertTrue(all(w.ok for w in sz.wants))

    def test_at_its_top(self):
        sz, rows = self.sized(FURNACES.format(bounds="1..3", tail=INTO_GEARS))
        self.assertEqual(rows["col"].n, 3)
        self.assertTrue(rows["col"].top)
        checks = size.report(sz, CAT)[1]
        self.assertEqual([c.code for c in checks], ["size"])
        self.assertIn("col at the top of its auto bounds", checks[0].msg)

    def test_two_stacks_together(self):
        cells = open(CELLS, encoding="utf-8").read()
        a = cells.index("module FurnaceCell")
        copper = cells[a:cells.index("}\n", a) + 2].replace("FurnaceCell", "CopperCell") \
            .replace("iron-ore", "copper-ore").replace("iron-plate", "copper-plate")
        with open(os.path.join(self.dir, "cells.fk"), "a", encoding="utf-8") as fh:
            fh.write("\n" + copper)
        sz, rows = self.sized("""import CircuitCell, CopperCell from "cells.fk"
cu    = Chest<requester, item=copper-ore, rate=10/s> @(60, 2)
fe    = Chest<requester, item=iron-plate, rate=2.5/s> @(0, 2)
fe2   = Chest<requester, item=iron-plate, rate=2.5/s> @(40, 2)
smelt = Stack<cell=CopperCell, n=auto 1..30> @(60, 8)
col   = Stack<cell=CircuitCell, n=auto 1..6> @(10, 10)
box   = Chest<provider> @(20, 80)
net ore: cu -> smelt.ore_in
net cp: smelt.pl_out -> col.cu_in
net few: fe -> col.wi_in
net fee: fe2 -> col.ei_in
net circuits: col.wo_out, col.eo_out -> box
assert col.rate >= 3/s
""")
        # 8 copper furnaces make 5 plates/s, 3.33 circuits/s; 7 would make 2.9
        self.assertEqual((rows["smelt"].n, rows["col"].n), (8, 2))
        self.assertTrue(all(w.ok for w in sz.wants))

    def test_a_single_machine_still_has_no_auto(self):
        path = self.write("t.fk", "f = Furnace<recipe=iron-plate, n=auto>\n")
        with self.assertRaises(ElabError) as cm:
            elaborate_file(path, CAT)
        self.assertIn("or Stack", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
