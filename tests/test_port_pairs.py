"""2.1.3: two nets into a cell's paired port (``f_in : in iron-ore | coal``), one per lane.

The runs fed SmelterPair's ``f_in`` and ChemCell's ``ea_in`` from two nets whose drivers were
module ports, and route failed: ``expand`` bound the one-item driver port to the pair itself, so
the route took it for a belt already paired. And the module's own ``lanes`` line is enough: two
nets meeting at a paired port share a belt without a top-level ``lanes`` line."""
import os
import shutil
import tempfile
import unittest

from fkcore import connect, expand, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate_file

CAT = Catalog.load()
ROOT = os.path.join(os.path.dirname(__file__), "..")
CELLS = os.path.join(ROOT, "kickoff", "template", "game", "cells.fk")

BOXES = """
import SmelterPair from "cells.fk"
module OreBox size 3x3 {
  port o_out : out iron-ore @s1
  c = Chest<requester, item=iron-ore, rate=2/s> @(1, 0)
  net o: c -> o_out
}
module CoalBox size 3x3 {
  port c_out : out coal @s1
  c = Chest<requester, item=coal, rate=0.5/s> @(1, 0)
  net k: c -> c_out
}
col = Stack<cell=SmelterPair, n=6> @(10, 8)
box = Chest<provider> @(16, 30)
net p: col.pw_out, col.pe_out -> box
src = OreBox @(4, 0)
"""

CASES = {
    # the 10-31 run: a module port drives one lane, a chest the other, with a top-level pair
    "port_and_chest": BOXES + """
coal = Chest<requester, item=coal, rate=0.5/s> @(14, 2)
net ore_: src.o_out -> col.f_in
net fuel: coal -> col.f_in
lanes ore_ | fuel
""",
    # the same with no top-level lanes line: the port's own lanes pair them
    "no_lanes_line": BOXES + """
coal = Chest<requester, item=coal, rate=0.5/s> @(14, 2)
net ore_: src.o_out -> col.f_in
net fuel: coal -> col.f_in
""",
    # both lanes driven by module ports (eng.en_out and adv.ac_out into chem.ea_in)
    "two_ports": BOXES + """
cb = CoalBox @(16, 0)
net ore_: src.o_out -> col.f_in
net fuel: cb.c_out -> col.f_in
""",
}


class PortPairTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="fkpairs-")
        shutil.copy(CELLS, cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def flat(self, name):
        path = os.path.join(self.dir, f"{name}.fk")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(CASES[name])
        return elaborate_file(path, CAT)

    def test_each_routes_and_connects(self):
        for name in CASES:
            with self.subTest(case=name):
                flat = self.flat(name)
                self.assertEqual(flat.lane_of.get("ore_"), "ore_|fuel")
                lay, _notes = expand.expand_factory(flat, CAT)
                r = route.route_layout(flat, lay, CAT)
                self.assertEqual(r.failed, {})
                rep = connect.connect(r.layout, CAT, connect.endpoints(flat), flat._port_edges)
                self.assertEqual({n for n, x in rep.nets.items() if x.status != "connected"},
                                 set())

    def test_a_driver_port_binds_its_own_net(self):
        flat = self.flat("two_ports")
        _frag, binding = expand.fragment_of(flat, "src", CAT)
        self.assertEqual(binding["o_out!"], "ore_")

    def test_one_net_of_both_items_is_no_pair(self):
        path = os.path.join(self.dir, "one.fk")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('import SmelterPair from "cells.fk"\n'
                     'src = Chest<requester, item="iron-ore,coal", rate=1/s> @(10, 2)\n'
                     'col = Stack<cell=SmelterPair, n=2> @(10, 8)\n'
                     'net f: src -> col.f_in\n')
        self.assertNotIn("f", elaborate_file(path, CAT).lane_of)


if __name__ == "__main__":
    unittest.main()
