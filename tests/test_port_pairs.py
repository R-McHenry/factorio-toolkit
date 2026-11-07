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


_DIRS = {0: (0, -1), 4: (1, 0), 8: (0, 1), 12: (-1, 0)}


def _pair_joins_on_undergrounds(lay):
    """[underground keys] of a pair's route entered by a belt of one of its single nets (A's or
    B's last belt pointing into it): the join side-loaded onto an underground."""
    at = {(float(e.x), float(e.y)): e for e in lay.entities.values()}
    out = []
    for e in lay.entities.values():
        net = e.attrs.get("net", "")
        if "underground" not in e.name or e.attrs.get("ug") != "in" or "|" not in net:
            continue
        for d, (dx, dy) in _DIRS.items():
            o = at.get((float(e.x) - dx, float(e.y) - dy))
            if o is not None and "belt" in o.name and o.dir == d and o.attrs.get("net") != net:
                out.append(e.key)
    return out


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
                # 2.1.31: the join is a belt that runs straight on, never an underground side-
                # loaded from both sides (that drops a lane: the PU bay's copper into G1)
                self.assertEqual(_pair_joins_on_undergrounds(r.layout), [])

    def test_a_driver_port_binds_its_own_net(self):
        flat = self.flat("two_ports")
        _frag, binding = expand.fragment_of(flat, "src", CAT)
        self.assertEqual(binding["o_out!"], "ore_")

    def test_a_net_on_the_right_lane_alone_binds_the_far_port(self):
        # 2.1.31 (the PU bay): red circuits ride the left lane up a line and end there, the units
        # made along it leave on the right lane at its far end; the net that takes them names the
        # last cell's paired port, and it bound nothing (the lookup took the left item only)
        path = os.path.join(self.dir, "far.fk")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("""
module Cell size 7x3 {
  port rp_in  : in  iron-plate | iron-gear-wheel @s0
  port rp_out : out iron-plate | iron-gear-wheel @n0
  stack rp_in -> rp_out
  a = Assembler<recipe=iron-gear-wheel> @(2, 0)
  net r items iron-plate: rp_in -> a, rp_out
  net g items iron-gear-wheel: rp_in, a -> rp_out
  lanes r | g
}
fe   = Chest<requester, item=iron-plate, rate=2/s> @(2, 14)
line = Stack<cell=Cell, n=2> @(4, 4)
box  = Chest<provider> @(4, 0)
net plates: fe -> line.rp_in
net gears items iron-gear-wheel: line.rp_out -> box
""")
        flat = elaborate_file(path, CAT)
        _frag, binding = expand.fragment_of(flat, "line/1", CAT)
        self.assertEqual(binding["rp_out!"], "gears")
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})

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
