"""FRICTION 11-11 (the bootstrap stages, fk-boot-w3): an instance whose kind changed keeps no
committed route. ``seed = Seed`` became ``seed = Literal<file="seed.json">`` and the rebuild
crashed in ``flow._pinned_routes`` ("Literal has no fragment geometry yet": the old layout's jobs
were read with the new kind's geometry); a Stack's ``LabCell`` became ``LabCell3`` and every cell
feed came back partly-connected, pinned to the old cell's ports, even with ``--reroute``. Now
every net with an end on (or inside) a re-kinded instance is routed again and says why."""
import json
import os
import shutil
import tempfile
import unittest

from fkcore import flow
from fkcore.catalog import Catalog

CAT = Catalog.load()

#: plates in on a belt from the west edge, an assembler making gears, gears out on the east edge
GEAR = [{"name": "transport-belt", "x": 0.5, "y": 1.5, "direction": 4},
        {"name": "inserter", "x": 1.5, "y": 1.5, "direction": 12},
        {"name": "assembling-machine-2", "x": 3.5, "y": 1.5, "recipe": "iron-gear-wheel"},
        {"name": "inserter", "x": 5.5, "y": 1.5, "direction": 12},
        {"name": "transport-belt", "x": 6.5, "y": 1.5, "direction": 4},
        {"name": "small-electric-pole", "x": 1.5, "y": 0.5}]

BEFORE = """\
src  = Chest<requester, item=iron-plate, rate=1/s> @(0, 2)
gear = Assembler<recipe=iron-gear-wheel> @(12, 2)
dst  = Chest<provider> @(28, 2)
net fe: src -> gear
net g: gear -> dst
"""
AFTER = """\
src  = Chest<requester, item=iron-plate, rate=1/s> @(0, 2)
gear = Literal<file="lit.json"> @(12, 2)
dst  = Chest<provider> @(28, 2)
net fe items iron-plate: src -> gear.in
net g items iron-gear-wheel: gear.out -> dst
"""


class RekindTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkrekind-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.write("nauvis.surface", "surface nauvis\nterrain none\nplace t = t plot 0,0 40x12\n")
        self.write("nauvis.build.fkb", "read_surface nauvis\nread_terrain none\nelaborate\n"
                                       "place --keep pinned\nroute --only stale\nfloorplan\n"
                                       "report_checks\nwrite_layout\n")
        self.write("lit.json", json.dumps({"entities": GEAR, "ports": {
            "in": {"carrier": 0, "side": "w"}, "out": {"carrier": 4, "side": "e"}}}))

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
        return ctx

    def test_a_rekinded_instance_routes_its_nets_again(self):
        self.write("t.fk", BEFORE)
        self.build()
        self.assertIn("2 nets: 2 connected", self.read("out/report_checks.txt"))
        self.write("t.fk", AFTER)
        self.build()                                    # crashed: no fragment geometry yet
        route_txt = self.read("out/route.txt")
        self.assertIn("gear changed kind since the committed .fkp (Assembler -> Literal)",
                      route_txt)
        self.assertNotIn("kept      fe:", route_txt)
        self.assertIn("2 nets: 2 connected", self.read("out/report_checks.txt"))


if __name__ == "__main__":
    unittest.main()
