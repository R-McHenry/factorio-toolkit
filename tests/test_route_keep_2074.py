"""2.0.74: the 10-30 run's MIL step (515k). Adding a sealed module (Mil, three ports on the iron,
coal, copper and stone mains) and a steel row re-laid four main nets whole: ~620 belts, 549 of them
short, robots tore the old mains up first and the base stopped.

- A new port end was none of its module's machines, so the patch skipped it and its judge found it
  apart: a port consumer is now patched in like any other.
- A belt route the patch can't join to a new end is held: it stands as it is and only that end
  fails; ``fk build --reroute NET`` still lays it again on purpose.
- A moved end, or a machine set on a standing belt, goes to the patch instead of re-laying the net.
"""
import os
import re
import shutil
import tempfile
import unittest

from fkcore import flow, fkp
from fkcore.catalog import Catalog

CAT = Catalog.load()

MODS = """module M size 30x14 {
  port fe_in : in iron-plate @w5
  ga = Assembler<recipe=iron-gear-wheel> @(4, 1)
  box = Chest<provider, limit=4> @(20, 2)
  net fe: fe_in -> ga
  net g: ga -> box
}
src = Chest<requester, item=iron-plate, request=20> @(1, 52)
m = M @(14, 0)
net feed: src -> m.fe_in
"""

ROWS = """ore   = MinerRow<n=4, resource=iron-ore> @(2, 2)
smelt = SmelterRow<n=4, recipe=iron-plate> @(2, 14)
coal  = Chest<requester, item=coal, rate=1/s> @(26, 14)
box   = Chest<provider, limit=4> @(30, 24)
net ore: ore -> smelt
net fuel: coal -> smelt
net plates: smelt -> box
"""


class KeepTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fk2074-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.write("nauvis.surface", "surface nauvis\nmode play\nterrain none\n"
                                     "place t = t plot 0,0 60x60\n")
        self.write("nauvis.build.fkb", "read_surface nauvis\nread_terrain none\nelaborate\n"
                                       "place --keep pinned\nroute --only stale\nfloorplan\n"
                                       "report_checks\nwrite_layout\n")

    def write(self, name, text):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def read(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8") as fh:
            return fh.read()

    def build(self):
        code, ctx = flow.run(os.path.join(self.dir, "nauvis.build.fkb"), cat=CAT,
                             echo=lambda _l: None)
        self.assertEqual(code, 0, ctx.log)
        return self.read("out/route.txt"), self.read("out/report_checks.txt")

    def route_of(self, net):
        lay = fkp.load(os.path.join(self.dir, "t.fkp"))
        return {(e.name, e.x, e.y, e.dir) for e in lay.entities.values() if e.owner == f"~{net}"}

    def test_a_new_module_port_is_patched_into_a_standing_net(self):
        self.write("t.fk", MODS)
        self.build()
        first = self.route_of("feed")
        self.write("t.fk", MODS.replace("net feed: src -> m.fe_in",
                                        "m2 = M @(14, 20)\nnet feed: src -> m.fe_in, m2.fe_in"))
        route_txt, checks = self.build()
        self.assertRegex(route_txt, r"patched   feed: 1 -> 2, m2\.fe_in!: a splitter in place of "
                                    r"~feed/b\d+, \d+ belts; \d+ of \d+ carriers kept")
        self.assertNotIn("stale     feed", route_txt)
        # every belt that stood, stands, but the one the splitter took the place of
        self.assertEqual(len(first & self.route_of("feed")), len(first) - 1)
        self.assertNotIn("partly-connected", checks)

    def test_a_moved_chest_is_patched_and_its_net_keeps_its_belts(self):
        self.write("t.fk", ROWS)
        self.build()
        first = self.route_of("plates")
        self.write("t.fk", ROWS.replace("@(30, 24)", "@(31, 24)"))
        route_txt, checks = self.build()
        self.assertNotIn("its ends moved", route_txt)
        self.assertRegex(route_txt, r"patched   plates: ")
        kept = len(first & self.route_of("plates"))
        self.assertGreaterEqual(kept, len(first) - 3, route_txt)  # the old end's few carriers
        self.assertNotIn("partly-connected", checks)


if __name__ == "__main__":
    unittest.main()
