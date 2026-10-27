"""2.0.49: stacks, a line of cells, each a sealed module routed and checked like any other.

Rory, 2026-10-26: "a more generic linear template, with each unit programmed routed and validated
like any other module, but this one is special and has matching input and output ports on
opposite sides so that it can stack linearly", and "it should be possible to do it with every belt
routing as 3 belts in a row, no bends or undergrounds".

- `stack NEAR -> FAR` in a module pairs a port on the edge toward the head with the one opposite;
  `Stack<cell=CELL, n=N, head=HEAD>` places N cells edge to edge, a net per pair between
  neighbours, which lays nothing (2.0.48: ports are edges, and the two meet on one);
- a ref to the stack names the head's port, or with no head the first cell's NEAR / the last
  cell's FAR port; the last cell's FAR ports are dead ends, no port line;
- inside a cell a net's belt runs straight across, port edge to port edge, one inserter per
  machine; a paired port (`A | B`, a `lanes` pair) comes in paired and runs straight on;
- `Pole` pins a pole where a packed cell needs it; a straight run tunnels under it;
- feed-rides-on: a feed riding a product's belt into the product's sink, unless its hands filter it.
"""
import os
import unittest

from fkcore import connect, expand, lang, rates, route
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate, load

CAT = Catalog.load()
DATA = os.path.join(os.path.dirname(__file__), "data", "stacks")

CELL = """
module Cell size 9x3 {
  port f_in  : in  iron-plate @s1
  port f_out : out iron-plate @n1
  port g_in  : in  iron-gear-wheel @n7
  port g_out : out iron-gear-wheel @s7
  stack f_in -> f_out, g_out -> g_in
  a = Assembler<recipe=iron-gear-wheel> @(3, 0)
  net f: f_in -> a, f_out
  net g: g_in, a -> g_out
}
"""

LINE = CELL + """
feed = Chest<requester, item=iron-plate, rate=4> @(1, 20)
box  = Chest<provider, limit=8> @(7, 20)
line = Stack<cell=Cell, n=4> @(0, 4)
net fe: feed -> line.f_in
net out: line.g_out -> box
"""


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def routed(flat):
    lay, _ = expand.expand_factory(flat, CAT)
    return route.route_layout(flat, lay, CAT)


class ElaborationTest(unittest.TestCase):
    def test_cells_edge_to_edge_and_a_net_per_pair(self):
        flat = flat_of(LINE)
        self.assertEqual(flat.stacks["line"], ("Cell", 4, None))
        self.assertEqual(sorted(p for p in flat.sealed if p.startswith("line/")),
                         ["line/0", "line/1", "line/2", "line/3"])
        # far = north: the first cell at the bottom, the rest above it
        self.assertEqual([flat.insts[f"line/{k}"].hints["at"][:2] for k in range(4)],
                         [(0, 9), (0, 6), (0, 3), (0, 0)])
        self.assertEqual([(k for k, _i in flat.nets[f"line/f_out_{k}"].drivers).__next__()
                          for k in (1, 2, 3)], ["line/0/f_out", "line/1/f_out", "line/2/f_out"])
        # the product runs the other way: from each cell's g_out into the one before it
        self.assertEqual(flat.nets["line/g_in_1"].drivers[0][0], "line/1/g_out")
        self.assertEqual(flat.nets["line/g_in_1"].consumers[0][0], "line/0/g_in")

    def test_refs_to_the_stack_name_its_end_cells(self):
        flat = flat_of(LINE)
        self.assertEqual(flat.nets["fe"].consumers[0][0], "line/0/f_in")
        self.assertEqual(flat.nets["out"].drivers[0][0], "line/0/g_out")

    def test_dead_ends_are_no_port_lines(self):
        flat = flat_of(LINE)
        self.assertIn("line/3/f_out", flat.stack_ends)
        self.assertFalse([c for c in flat.checks if c.code == "port"])

    def test_a_pair_must_meet_across_the_cell(self):
        bad = LINE.replace("port f_out : out iron-plate @n1", "port f_out : out iron-plate @n2")
        with self.assertRaises(ElabError) as cm:
            flat_of(bad)
        self.assertIn("same pinned tile", str(cm.exception))


class RoutingTest(unittest.TestCase):
    def test_a_line_routes_straight_and_its_joins_lay_nothing(self):
        flat = flat_of(LINE)
        r = routed(flat)
        self.assertEqual(r.failed, {})
        joins = [ln for ln in r.lines if "nothing to lay" in ln]
        self.assertEqual(len(joins), 6)                     # 3 joins x 2 pairs
        for k in range(4):
            belts = [e for key, e in r.layout.entities.items()
                     if e.attrs.get("net") in (f"line/{k}/f", f"line/{k}/g") and e.name == "transport-belt"]
            self.assertEqual(len(belts), 6, k)              # 3 straight tiles each
            self.assertEqual({e.dir for e in belts if e.attrs["net"] == f"line/{k}/f"}, {0})
            self.assertEqual({e.dir for e in belts if e.attrs["net"] == f"line/{k}/g"}, {8})
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat), flat._port_edges)
        self.assertEqual(rep.leaks, [])
        self.assertTrue(all(n.connected for n in rep.nets.values()))

    def test_the_blue_stack_routes_straight_under_its_poles(self):
        f, m = load(os.path.join(DATA, "blue6.fk"))
        flat = elaborate(f, m, CAT, "blue6")
        r = routed(flat)
        self.assertEqual(r.failed, {})
        self.assertEqual([ln for ln in r.lines if ln.startswith(("crosses-frame", "FRAME", "port"))], [])
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat), flat._port_edges)
        self.assertEqual(rep.leaks, [])
        for key, e in r.layout.entities.items():
            net = e.attrs.get("net") or ""
            if key.startswith("~blue/") and e.name in ("transport-belt", "underground-belt"):
                self.assertEqual(e.dir, 0, key)           # every cell belt heads north
        ugs = [e for k, e in r.layout.entities.items()
               if k.startswith("~blue/") and e.name == "underground-belt"]
        self.assertEqual(len(ugs), 4)                     # one tunnel under each cell's pole
        poles = [e for k, e in r.layout.entities.items() if k.endswith("/pole/m0")]
        self.assertEqual(len(poles), 2)

    def test_a_paired_port_runs_its_pair_straight_on(self):
        f, m = load(os.path.join(DATA, "blue6.fk"))
        flat = elaborate(f, m, CAT, "blue6")
        r = routed(flat)
        line = next(ln for ln in r.lines if ln.startswith("routed    blue/0/ts|blue/0/tp"))
        self.assertIn("paired at its port", line)


class CarryoverTest(unittest.TestCase):
    def test_a_feed_riding_into_the_products_chest(self):
        f, m = load(os.path.join(DATA, "blue.fk"))
        rows = rates.carryover(rates.solve(elaborate(f, m, CAT, "blue")))
        self.assertEqual([r[:4] for r in rows],
                         [("out", "sulfur", "chemical-science-pack", "packs/c0")])

    def test_filtered_hands_keep_it_out(self):
        f, m = load(os.path.join(DATA, "blue6.fk"))
        self.assertEqual(rates.carryover(rates.solve(elaborate(f, m, CAT, "blue6"))), [])


class MosaicTest(unittest.TestCase):
    def test_the_hand_patched_unit_loads_as_a_literal(self):
        f, m = load(os.path.join(DATA, "blue2cell.fk"))
        flat = elaborate(f, m, CAT, "u")
        lay, _ = expand.expand_factory(flat, CAT)
        self.assertEqual(lay.size, (18, 6))
        self.assertEqual(len([k for k in flat.machines]), 6)


if __name__ == "__main__":
    unittest.main()
