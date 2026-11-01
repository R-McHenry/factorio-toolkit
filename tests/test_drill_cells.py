"""3.0, drills in cells: a drill drops its ore on a fixed tile, so the router reaches it by a belt
over that tile (``steiner.DropSink``), never an inserter, and a cell's through-belt passes it. A
MinerRow whose own belt would leave its cell's frame lays no belt; a row anywhere else keeps it."""
import os
import shutil
import tempfile
import unittest

from fkcore import connect, expand, route, routed
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate_file

CAT = Catalog.load()

CELL = """
module DrillCell<resource=iron-ore> size 3x4 {
  port ore_in  : in  $resource @w3
  port ore_out : out $resource @e3
  stack ore_in -> ore_out
  d = MinerRow<n=1, resource=$resource> @(0, 0)
  net o: ore_in, d -> ore_out
}
"""
TWO_ROWS = """
module DrillTwo<resource=iron-ore> size 3x7 {
  port ore_in  : in  $resource @w3
  port ore_out : out $resource @e3
  stack ore_in -> ore_out
  n = MinerRow<n=1, resource=$resource> @(0, 0)
  s = MinerRow<n=1, resource=$resource> @(0, 3, rot 2)
  net o: ore_in, n, s -> ore_out
}
"""
LINE = """
col = Stack<cell={cell}, n=4> @(10, 8)
box = Chest<provider> @(30, 20)
net p: col.ore_out -> box
"""


class DropsTest(unittest.TestCase):
    """3.0: anything with the game's drop vector (a drill, a recycler) puts its output down on its
    drop tile: onto a belt the router lays there, or straight into a consumer standing on it."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkdrop-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        with open(os.path.join(self.dir, "drill.json"), "w", encoding="utf-8") as fh:
            fh.write('{"entities": [{"name": "electric-mining-drill", "x": 1.5, "y": 1.5, '
                     '"direction": 0}], "names": {"d": 0}}')

    def build(self, text):
        return DrillCellsTest.build(self, text)

    def test_the_drop_tile_is_the_game_s_vector(self):
        # measured: tools/laptop_server.py drops (2.0.77)
        self.assertEqual(CAT.drop_tile("electric-mining-drill", 1.5, 1.5, 0), (1, -1))
        self.assertEqual(CAT.drop_tile("electric-mining-drill", 1.5, 1.5, 4), (3, 1))
        self.assertEqual([CAT.drop_tile("recycler", 1, 2, d) for d in (0, 4, 8, 12)],
                         [(0, -1), (3, 1), (1, 4), (-2, 2)])
        self.assertIsNone(CAT.drop_tile("pumpjack", 1.5, 1.5, 0))
        self.assertIsNone(CAT.drop_tile("assembling-machine-1", 1.5, 1.5, 0))

    def test_a_drill_drops_straight_into_a_chest(self):
        flat, _lay, r = self.build(
            'm = Literal<file="drill.json", resource=iron-ore> @(10, 10)\n'
            "box = Chest<provider, limit=50> @(11, 9)\n"
            "net o items iron-ore: m.d -> box\n")
        self.assertEqual(r.failed, {})
        self.assertEqual([e for e in r.layout.entities.values() if e.owner.startswith("~o")], [])
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
        self.assertEqual((rep.nets["o"].status, rep.leaks), ("connected", []))

    def test_a_recycler_drops_on_its_tile_or_is_emptied_by_an_inserter(self):
        base = ("src = Chest<requester, item=iron-gear-wheel, rate=1/s> @(2, 10)\n"
                "r = Machine<entity=recycler, recipe=iron-gear-wheel-recycling> @(10, 10)\n"
                "box = Chest<provider, limit=50> @(20, 4)\n"
                "net g: src -> r\nnet o items iron-plate: r -> box\n")
        for wall, picks in (("", 0), ("wall = Chest<provider, limit=1> @(10, 9)\n", 1)):
            flat, lay, r = self.build(base + wall)
            self.assertEqual(r.failed, {}, wall)
            rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
            self.assertEqual(rep.nets["o"].status, "connected", wall)
            g = rep.graph
            # with its drop tile free, no inserter picks from the recycler; taken, one does
            self.assertEqual(len([a for a, b, via in g.edges()
                                  if a == "r/m0" and via == "pickup"]), picks, wall)

    def test_a_drill_s_lane_is_measured(self):
        from fkcore import fkp, lanes
        for belt, tiles, lane in ((4, [(0.5, -1.5), (1.5, -1.5)], "R"),     # across: the near one
                                  (12, [(0.5, -1.5), (-0.5, -1.5)], "L"),
                                  (0, [(0.5, -1.5), (0.5, -2.5)], "R"),     # in line: the right
                                  (8, [(0.5, -1.5), (0.5, -2.5)], "R")):
            ents = [fkp.Entity("d", "electric-mining-drill", 0.5, 0.5, 0, {"resource": "iron-ore"})]
            ents += [fkp.Entity(f"b{i}", "transport-belt", x, y, belt, {})
                     for i, (x, y) in enumerate(tiles)]
            got = [e.dst for e in lanes.build(ents, CAT).edges() if e.via == "mine"]
            self.assertEqual(got, [("b0", lane)], belt)

    def test_a_cell_of_wrapped_machines_stacks(self):
        """Rory's model: a wrapped machine (a Literal: an assembler and its own two inserters,
        named), a cell of it whose nets the router lays, a Stack of four."""
        with open(os.path.join(self.dir, "asm.json"), "w", encoding="utf-8") as fh:
            fh.write('{"entities": [{"name": "inserter", "x": 0.5, "y": 1.5, "direction": 12}, '
                     '{"name": "assembling-machine-2", "x": 2.5, "y": 1.5, '
                     '"recipe": "iron-gear-wheel"}, {"name": "inserter", "x": 4.5, "y": 1.5, '
                     '"direction": 12}], "names": {"a": 1}}')
        flat, _lay, r = self.build("""
module GearCellW size 7x3 {
  port in_in   : in  iron-plate @s0
  port in_out  : out iron-plate @n0
  port out_in  : in  iron-gear-wheel @n6
  port out_out : out iron-gear-wheel @s6
  stack in_in -> in_out, out_out -> out_in
  w = Literal<file="asm.json"> @(1, 0)
  net i: in_in -> w.a, in_out
  net g: out_in, w.a -> out_out
}
src = Chest<requester, item=iron-plate, rate=4/s> @(0, 30)
col = Stack<cell=GearCellW, n=4> @(10, 8)
out = Chest<provider, limit=100> @(30, 30)
net p: src -> col.in_in
net q: col.out_out -> out
""")
        self.assertEqual(r.failed, {})
        self.assertEqual(self.connected_all(flat, r), set())
        # the router used the Literals' own inserters and laid none of its own on the cells
        self.assertEqual(len([e for e in r.layout.entities.values() if e.name == "inserter"]), 8)
        self.assertEqual([c.code for c in flat.checks if c.code != "no-limit"], [])

    def connected_all(self, flat, r):
        return DrillCellsTest.connected(self, flat, r)


class DrillCellsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkdrill-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def build(self, text):
        path = os.path.join(self.dir, "t.fk")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        flat = elaborate_file(path, CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        return flat, lay, route.route_layout(flat, lay, CAT)

    def connected(self, flat, r):
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat), flat._port_edges)
        self.assertEqual(rep.leaks, [])
        return {n for n, x in rep.nets.items() if x.status != "connected"}

    def test_a_stack_of_drill_cells_routes_and_connects(self):
        for src, cell in ((CELL, "DrillCell"), (TWO_ROWS, "DrillTwo")):
            with self.subTest(cell=cell):
                flat, lay, r = self.build(src + LINE.format(cell=cell))
                self.assertEqual(r.failed, {})
                self.assertEqual(self.connected(flat, r), set())
                # the drill's net lays no inserter: the belt passes the drop tile
                ins = [e for e in r.layout.entities.values()
                       if e.key.startswith("~col/") and CAT.kind(e.name) == "inserter"]
                self.assertEqual(ins, [])

    def test_the_cell_row_lays_no_belt_and_its_drill_is_a_drop_driver(self):
        flat, lay, _r = self.build(CELL + LINE.format(cell="DrillCell"))
        self.assertFalse(any(k.startswith("col/0/d/outb") for k in lay.entities))
        job = route.jobs(flat, lay, CAT)["col/0/o"]
        self.assertEqual(job.drops, {"col/0/d/m0": (11, 11)})
        self.assertIn((11, 11), job.ends())

    def test_a_row_outside_a_cell_keeps_its_belt(self):
        _flat, lay, _r = self.build("""
ore = MinerRow<n=4, resource=iron-ore> @(10, 2)
box = Chest<provider> @(30, 4)
net o: ore -> box
""")
        self.assertTrue(any(k.startswith("ore/outb") for k in lay.entities))

    def test_the_ore_rides_the_lane_next_to_its_drill(self):
        for src, cell, lanes in ((CELL, "DrillCell", {"L"}), (TWO_ROWS, "DrillTwo", {"L", "R"})):
            with self.subTest(cell=cell):
                flat, _lay, r = self.build(src + LINE.format(cell=cell))
                lg = routed.solve(flat, r.layout, CAT).lg
                got = {e.dst[1] for es in lg.out.values() for e in es
                       if e.via == "mine" and e.src[0].startswith("col/0/")}
                self.assertEqual(got, lanes)


if __name__ == "__main__":
    unittest.main()
