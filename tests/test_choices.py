"""2.0.60: ``machine=auto`` and ``modules=auto``, chosen by the size step around the counts: the
cheapest picks that meet every want, at what they cost to build in raw resources (fkcore.cost),
plus ``payback`` seconds of what they draw for the rate asked."""
import os
import shutil
import tempfile
import unittest

from fkcore import size
from fkcore.catalog import Catalog
from fkcore.cost import item_cost
from fkcore.elaborate import ElabError, elaborate_file

CAT = Catalog.load()
CELLS = os.path.join(os.path.dirname(__file__), "..", "kickoff", "template", "game", "cells.fk")

GEARS = """pl  = Chest<requester, item=iron-plate, rate=10/s> @(0, 0)
g   = AsmRow<n=auto, recipe=iron-gear-wheel, machine=auto, modules=auto> @(4, 4)
box = Chest<provider> @(30, 4)
net i: pl -> g
net o: g -> box
assert g.rate >= 3/s
"""


class ChoicesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkchoices-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def sized(self, text, payback=0.0):
        sz = size.size({"t": size.maker(self.write("t.fk", text), CAT)}, cat=CAT, payback=payback)
        picks = {k.rsplit(".", 1)[1]: v for (_f, k, v, _menu) in sz.picks}
        return sz, picks, {r.path: r.n for r in sz.rows}

    def test_costs_follow_the_recipes(self):
        self.assertEqual(item_cost(CAT, "iron-gear-wheel"), 2.0)
        self.assertEqual(item_cost(CAT, "electronic-circuit"), 2.5)
        self.assertEqual(item_cost(CAT, "assembling-machine-2"), 54.0)

    def test_elaborated_at_the_first_pick_or_the_steps(self):
        path = self.write("t.fk", GEARS)
        flat = elaborate_file(path, CAT)
        self.assertEqual(flat.machines["g/m0"].prototype, "assembling-machine-1")
        self.assertNotIn("modules", flat.machines["g/m0"].extra)
        flat = elaborate_file(path, CAT, sizes={"<factory>.g.machine": "assembling-machine-2",
                                                "<factory>.g.modules": "productivity-module"})
        m = flat.machines["g/m0"]
        self.assertEqual((m.prototype, m.extra["modules"]),
                         ("assembling-machine-2", ["productivity-module"] * 2))
        self.assertAlmostEqual(m.makes["iron-gear-wheel"], 0.75 * 0.9 * 1.08 / 0.5)

    def test_cheapest_to_build(self):
        sz, picks, counts = self.sized(GEARS)
        self.assertEqual((picks["machine"], picks["modules"], counts["g"]),
                         ("assembling-machine-1", None, 3))
        self.assertTrue(all(w.ok for w in sz.wants))

    def test_over_two_hours_productivity_pays(self):
        _sz, picks, counts = self.sized(GEARS, payback=7200)
        self.assertEqual((picks["machine"], picks["modules"], counts["g"]),
                         ("assembling-machine-3", "productivity-module", 2))

    def test_the_same_design_is_one_option(self):
        sz, _picks, _counts = self.sized(GEARS)
        built = [tuple(sorted(p.items())) for _s, p, _c, _b, _u in sz.tried]
        self.assertEqual(len(built), len(set(built)))
        self.assertEqual(len(built), 7)      # AM1 has no slots: 1 + 3 + 3

    def test_a_choice_in_a_cell_is_the_whole_stacks(self):
        shutil.copy(CELLS, self.dir)
        cells = open(CELLS, encoding="utf-8").read()
        cells = cells.replace("f = Furnace<recipe=iron-plate, machine=electric-furnace>",
                              "f = Furnace<recipe=iron-plate, machine=electric-furnace, "
                              "modules=auto>")
        with open(os.path.join(self.dir, "cells.fk"), "w", encoding="utf-8") as fh:
            fh.write(cells)
        sz, picks, counts = self.sized("""import FurnaceCell from "cells.fk"
ore = Chest<requester, item=iron-ore, rate=5/s> @(10, 2)
col = Stack<cell=FurnaceCell, n=auto 1..20> @(10, 8)
box = Chest<provider> @(40, 80)
net o: ore -> col.ore_in
net p: col.pl_out -> box
assert col.rate >= 2/s
""", payback=36000)
        self.assertEqual(picks["modules"], "productivity-module")
        mods = {tuple(m.extra.get("modules", ())) for k, m in sz.flats["t"].machines.items()
                if m.prototype == "electric-furnace"}
        self.assertEqual(mods, {("productivity-module", "productivity-module")})
        self.assertTrue(all(w.ok for w in sz.wants))

    def test_no_tier_for_a_kind_without_one(self):
        path = self.write("t.fk", "c = ChemPlant<recipe=sulfur, machine=auto>\n")
        with self.assertRaises(ElabError) as cm:
            elaborate_file(path, CAT)
        self.assertIn("machine=auto", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
