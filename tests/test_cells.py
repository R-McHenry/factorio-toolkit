"""2.0.55: the starter cells every new run gets in game\\cells.fk (kickoff/template/game), each the
simplest Stack of one machine kind: stacked, routed and connected, with no false CLOG where a
paired belt crosses from one cell into the next. And an upgrade brings them to a run that has
none, never over a run's own."""
import json
import os
import shutil
import sys
import tempfile
import unittest

from fkcore import connect, expand, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate_file

CAT = Catalog.load()
ROOT = os.path.join(os.path.dirname(__file__), "..")
CELLS = os.path.join(ROOT, "kickoff", "template", "game", "cells.fk")

#: a line of each cell, fed and emptied by chests
LINES = {
    "FurnaceCell": """
        ore = Chest<requester, item=iron-ore, rate=2.5/s> @(10, 2)
        col = Stack<cell=FurnaceCell, n=8> @(10, 8)
        box = Chest<provider> @(20, 40)
        net o: ore -> col.ore_in
        net p: col.pl_out -> box""",
    "FurnacePair": """
        orea = Chest<requester, item=iron-ore, rate=2.5/s> @(10, 2)
        oreb = Chest<requester, item=iron-ore, rate=2.5/s> @(22, 2)
        col = Stack<cell=FurnacePair, n=4> @(10, 8)
        box = Chest<provider> @(16, 30)
        net a: orea -> col.oa_in
        net b: oreb -> col.ob_in
        net p: col.pl_out -> box""",
    "StoneFurnaceCell": """
        ore  = Chest<requester, item=iron-ore, rate=1/s> @(4, 2)
        coal = Chest<requester, item=coal, rate=0.5/s> @(14, 2)
        col  = Stack<cell=StoneFurnaceCell, n=6> @(10, 8)
        box  = Chest<provider> @(16, 30)
        net ore_: ore -> col.f_in
        net fuel: coal -> col.f_in
        lanes ore_ | fuel
        net p: col.pl_out -> box""",
    "SmelterPair": """
        ore  = Chest<requester, item=iron-ore, rate=2/s> @(4, 2)
        coal = Chest<requester, item=coal, rate=0.5/s> @(14, 2)
        col  = Stack<cell=SmelterPair, n=6> @(10, 8)
        box  = Chest<provider> @(16, 30)
        net ore_: ore -> col.f_in
        net fuel: coal -> col.f_in
        lanes ore_ | fuel
        net p: col.pw_out, col.pe_out -> box""",
    "CircuitCell": """
        fe0 = Chest<requester, item=iron-plate, rate=2/s> @(0, 2)
        fe1 = Chest<requester, item=iron-plate, rate=2/s> @(40, 2)
        cu0 = Chest<requester, item=copper-plate, rate=2.5/s> @(14, 2)
        cu1 = Chest<requester, item=copper-plate, rate=2.5/s> @(18, 2)
        cu2 = Chest<requester, item=copper-plate, rate=2.5/s> @(26, 2)
        cu3 = Chest<requester, item=copper-plate, rate=2.5/s> @(30, 2)
        col = Stack<cell=CircuitCell, n=2> @(10, 10)
        box1 = Chest<provider> @(6, 40)
        box2 = Chest<provider> @(16, 40)
        box3 = Chest<provider> @(26, 40)
        box4 = Chest<provider> @(36, 40)
        net few: fe0 -> col.wi_in
        net fee: fe1 -> col.ei_in
        net cu: cu0, cu1, cu2, cu3 -> col.cu_in
        net circuits: col.wo_out, col.eo_out -> box1, box2, box3, box4""",
    "GearCell": """
        pl  = Chest<requester, item=iron-plate, rate=2/s> @(10, 2)
        col = Stack<cell=GearCell, n=4> @(10, 8)
        box = Chest<provider> @(16, 30)
        net i: pl -> col.in_in
        net g: col.out_out -> box""",
    "LabCell": """
        red   = Chest<requester, item=automation-science-pack, rate=0.5/s> @(4, 2)
        green = Chest<requester, item=logistic-science-pack, rate=0.5/s> @(14, 2)
        labs  = Stack<cell=LabCell, n=6> @(10, 8)
        net r: red -> labs.p_in
        net g: green -> labs.p_in
        lanes r | g""",
    "DrillCell": """
        col = Stack<cell=DrillCell, n=4> @(10, 8)
        box = Chest<provider> @(30, 20)
        net p: col.ore_out -> box""",
    "DrillPair": """
        col = Stack<cell=DrillPair, n=4> @(10, 8)
        box = Chest<provider> @(30, 20)
        net p: col.ore_out -> box""",
    "WrappedDrillCell": """
        col = Stack<cell=WrappedDrillCell, n=4> @(10, 8)
        box = Chest<provider> @(30, 20)
        net p: col.ore_out -> box""",
}


class StarterCellsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="fkcells-")
        shutil.copy(CELLS, cls.dir)
        shutil.copy(os.path.join(os.path.dirname(CELLS), "drill.json"), cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def line(self, cell):
        path = os.path.join(self.dir, f"{cell}.fk")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f'import {cell} from "cells.fk"\n' + LINES[cell])
        return elaborate_file(path, CAT)

    def test_the_template_declares_them(self):
        # 2.1, the library: more cells, and GearCell is a kind of AsmCell1
        with open(CELLS, encoding="utf-8") as fh:
            f = lang.parse(fh.read(), "cells.fk")
        self.assertLessEqual(set(LINES), set(f.modules) | set(f.kinds))

    def test_each_line_routes_and_connects(self):
        for cell in LINES:
            with self.subTest(cell=cell):
                flat = self.line(cell)
                lay, _notes = expand.expand_factory(flat, CAT)
                r = route.route_layout(flat, lay, CAT)
                self.assertEqual(r.failed, {})
                rep = connect.connect(r.layout, CAT, connect.endpoints(flat), flat._port_edges)
                self.assertEqual({n for n, x in rep.nets.items() if x.status != "connected"},
                                 set())
                self.assertEqual(rep.leaks, [])

    def test_a_paired_crossing_draws_no_clog(self):
        for cell in ("StoneFurnaceCell", "SmelterPair", "LabCell"):
            with self.subTest(cell=cell):
                self.assertEqual([c for c in self.line(cell).checks if c.code == "CLOG"], [])

    def test_a_mixed_lane_crossing_still_does(self):
        # two items on ONE lane (`a, b`, no `|`) can clog where it crosses
        path = os.path.join(self.dir, "mixed.fk")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("""
module Mix size 7x3 {
  port m_in  : in  iron-ore, coal @s0
  port m_out : out iron-ore, coal @n0
  stack m_in -> m_out
  f = Furnace<recipe=iron-plate> @(2, 0)
  net m: m_in -> f, m_out
}
src = Chest<requester, item="iron-ore,coal", rate=1/s> @(10, 2)
col = Stack<cell=Mix, n=3> @(10, 8)
net s: src -> col.m_in
""")
        self.assertTrue(any(c.code == "CLOG" for c in elaborate_file(path, CAT).checks))


class UpgradeBringsCellsTest(unittest.TestCase):
    def plan(self, has_cells):
        sys.path.insert(0, os.path.join(ROOT, "kickoff"))
        import upgrade_run
        run = tempfile.mkdtemp(prefix="fkrun-")
        try:
            os.makedirs(os.path.join(run, "game"))
            with open(os.path.join(run, "run.json"), "w", encoding="utf-8") as fh:
                json.dump({"toolkit_sha": "0aa0c31", "player": "deepseek"}, fh)
            if has_cells:
                with open(os.path.join(run, "game", "cells.fk"), "w", encoding="utf-8") as fh:
                    fh.write("# the player's own\n")
            return upgrade_run.upgrade(run, "HEAD", dry=True)
        finally:
            shutil.rmtree(run, ignore_errors=True)

    def test_a_run_without_cells_gets_them(self):
        self.assertTrue(any("game/cells.fk" in line for line in self.plan(False)))

    def test_a_run_with_its_own_keeps_them(self):
        self.assertFalse(any("game/cells.fk" in line for line in self.plan(True)))


if __name__ == "__main__":
    unittest.main()
