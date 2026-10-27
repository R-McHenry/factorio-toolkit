"""2.0.46: the bus base example (agent/docs/examples/busbase.fk) and what it needed.

Rory, 2026-10-26: "build a solid bus base demo ... an iron bus and a copper bus, a smelting spine fed
by mines for filling both busses, then a mall spine, and a science one ... a circuits bus that is fed
by a spine factory that uses copper and iron from the bus". It needed three things:

1. **A staircase stands in front of what it connects to**, not packed at the head: a spine's tap is
   under its port, so its plates don't run back along the bus. Only an endpoint beside the bus on
   its staircases' side counts, so a bus never grows into something in line with it.
2. **Several buses each have an in1**: their mouths' nets are named by the bus (febus_in1).
3. **The contract of an out port into a bus** reads what the module's makers put through it; the
   pool absorbed the port's nets, whose own rows read 0.0.
"""
import os
import unittest

from fkcore import contract, expand, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate, load

CAT = Catalog.load()
BASE = os.path.join(os.path.dirname(__file__), "..", "agent", "docs", "examples", "busbase.fk")


def flat_of_file(path):
    f, modules = load(path)
    return elaborate(f, modules, CAT, "busbase")


class BusBaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flat = flat_of_file(BASE)
        lay, _notes = expand.expand_factory(cls.flat, CAT)
        cls.routed = route.route_layout(cls.flat, lay, CAT)

    def test_it_routes_clean(self):
        self.assertEqual(self.routed.failed, {})
        bad = [ln for ln in self.routed.lines if ln.startswith(("SEAL", "FRAME", "PORT"))
               or "LEAK" in ln and " 0 LEAK" not in ln]
        self.assertEqual(bad, [])
        self.assertEqual([c for c in self.flat.checks], [])
        self.assertEqual(sorted(self.flat.sealed), ["circ", "cu_a", "fe_a", "fe_b", "mall", "sci"])

    def test_each_tap_stands_in_front_of_its_spines_port(self):
        # ports pinned @sN along the spine's south side: spine x + N - the bus's head x
        febus, cubus, cbus = (self.flat.insts[b].params for b in ("febus", "cubus", "cbus"))
        self.assertEqual(febus["tap"], ["n22", "n66", "n116"])     # circ 66+6, mall 110+6, sci 160+6
        self.assertEqual(cubus["tap"], ["n28", "n122"])            # circ 66+12, sci 160+12
        self.assertEqual(cbus["tap"], ["n24", "n78"])              # mall 110+14, sci 160+18 (head 100)

    def test_every_bus_has_its_own_mouth_net(self):
        for net in ("febus_in1", "febus_in2", "cubus_in1", "cbus_in1"):
            self.assertIn(net, self.flat.nets)
        self.assertNotIn("in1", self.flat.nets)

    def test_the_contract_reads_the_smelters_through_the_mouths(self):
        lines = {ln.split(":")[0]: ln for ln in contract.contract(self.flat)}
        self.assertIn("fe_a: out iron-plate 3.8/s via febus mouth in1 (got 2.1)", lines["fe_a"])
        self.assertIn("out electronic-circuit 2.0/s via cbus mouth in1", lines["circ"])
        self.assertIn("in iron-plate 3.2/s via febus tap n116 (got 3.2)", lines["sci"])


class InLineTest(unittest.TestCase):
    def test_an_endpoint_in_line_with_the_bus_keeps_the_packed_place(self):
        text = """
module Rib size 16x10 {
  port iron : in iron-plate @w
  g = AsmRow<n=1, recipe=iron-gear-wheel> @(2, 1)
  net fe: iron -> g
}
feed = Chest<requester, item=iron-plate, rate=4> @(0, 0)
bus  = Bus<belts=2, item=iron-plate>(in1: feed, fg: rib.iron) @(20, 0)
rib  = Rib @(40, 0)
"""
        f = lang.parse(text, "t.fk")
        flat = elaborate(f, dict(f.modules), CAT, "t")
        self.assertEqual(flat.insts["bus"].params["tap"], ["n5"])  # packed: the rib is in line
        beside = text.replace("rib  = Rib @(40, 0)", "rib  = Rib @(40, -20)")
        f = lang.parse(beside, "t.fk")
        flat = elaborate(f, dict(f.modules), CAT, "t")
        self.assertEqual(flat.insts["bus"].params["tap"], ["n20"])  # beside it: under its port


if __name__ == "__main__":
    unittest.main()
