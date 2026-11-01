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
