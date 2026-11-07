"""2.1.31: the megabase PU bay in the design lab (lab-session/fk-run/FRICTION.md).

- Rails overlap where they meet (a curve's ends on a junction's straights); a captured station
  failed `place` with 144 "tile ... is already" lines.
- A captured build's inserters and belts are nets of their own (fkcore.literal nets them by
  connectivity), so every hand of a captured hub read SPILL."""
import unittest

from fkcore import fkp
from fkcore.catalog import Catalog
from fkcore.connect import connect, graph

CAT = Catalog.load()


def L(text, name="t"):
    return fkp.loads(f"fkp 1 factory {name}\n" + "\n".join(l.strip() for l in text.splitlines()))


def clashes(lines):
    return [p for p in lines if "is already" in p]


class RailsShareTiles(unittest.TestCase):
    LAY = """
        e r/straight-rail0 straight-rail 1,2 N
        e r/curved-rail-a0 curved-rail-a 1,2 N"""

    def test_two_rails_may_share_a_tile(self):
        self.assertTrue(fkp.rails_share("straight-rail", "curved-rail-a"))
        self.assertFalse(fkp.rails_share("straight-rail", "transport-belt"))
        lay = L(self.LAY)
        self.assertEqual(clashes(fkp.invariants(lay, CAT)), [])
        self.assertEqual(clashes(graph(lay, CAT).problems), [])

    def test_a_rail_and_a_belt_still_clash(self):
        lay = L(self.LAY + "\n e r/b0 transport-belt 0.5,1.5 E net=a")
        self.assertTrue(clashes(fkp.invariants(lay, CAT)))


class LiteralCarriers(unittest.TestCase):
    def leaks(self, hand):
        lay = L(f"""
            e W/b0 transport-belt 0.5,-0.5 E net=W/belt0
            e W/i0 bulk-inserter 0.5,0.5 N net={hand}
            e W/b1 transport-belt 0.5,1.5 E net=W/belt1""")
        return connect(lay, CAT).leaks

    def test_a_literals_hand_onto_its_own_belt_is_no_spill(self):
        self.assertEqual(self.leaks("W/hand0"), [])

    def test_another_nets_hand_still_spills(self):
        self.assertTrue(self.leaks("hub"))
        self.assertTrue(self.leaks("X/hand0"))


class LiteralWiresOnPoles(unittest.TestCase):
    # the bay's declared wire to the hub sorter hopped over a captured pole that carried the
    # sorter's own green chain, so the chests' contents set the inserters' filters
    def test_a_pole_a_literal_wired_is_used(self):
        from types import SimpleNamespace
        from fkcore import circuits
        lay = L("""
            e E/medium-electric-pole0 medium-electric-pole 0.5,0.5
            e E/medium-electric-pole1 medium-electric-pole 5.5,0.5
            e E/bulk-inserter0 bulk-inserter 2.5,2.5 N wire=2,medium-electric-pole0,2""")
        layer = SimpleNamespace(lay=lay, members={}, wires={})
        used = lambda k, c: circuits._Layer._pole_used(layer, k, c, "pstock")
        layer._literal_colours = lambda: circuits._Layer._literal_colours(layer)
        self.assertTrue(used("E/medium-electric-pole0", "green"))
        self.assertFalse(used("E/medium-electric-pole0", "red"))
        self.assertFalse(used("E/medium-electric-pole1", "green"))


class DiamondImport(unittest.TestCase):
    # the megabase loop imports a PU chain and an LDS chain, both built of pucells.fk's FurnB
    def test_two_files_of_one_cell_file(self):
        import os, shutil, tempfile
        from fkcore import elaborate
        d = tempfile.mkdtemp(prefix="fkdiamond-")
        self.addCleanup(shutil.rmtree, d, True)
        files = {
            "cells.fk": "module Cell size 4x4 {\n  port o : out iron-plate @s1\n}\n",
            "a.fk": 'import Cell from "cells.fk"\nmodule A size 8x8 {\n  port o : out iron-plate @s1\n'
                    "  c = Cell @(0, 0)\n  net x: c.o -> o\n}\n",
            "b.fk": 'import Cell from "cells.fk"\nmodule B size 8x8 {\n  port o : out iron-plate @s1\n'
                    "  c = Cell @(0, 0)\n  net x: c.o -> o\n}\n",
            "main.fk": 'import A from "a.fk"\nimport B from "b.fk"\na = A @(0, 0)\nb = B @(10, 0)\n'}
        for name, text in files.items():
            with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        _f, modules = elaborate.load(os.path.join(d, "main.fk"))
        self.assertEqual({"A", "B", "Cell"} <= set(modules), True)


if __name__ == "__main__":
    unittest.main()
