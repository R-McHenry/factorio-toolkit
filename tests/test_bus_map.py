"""2.0.32 (PLAN-MODULES phase 2, first slice): a Bus's connection list is its port map.

The named entries are nets, written in port order; direction comes from the netlist; the staircases
take their positions from the order and `length` follows; a tap written before any load is an
``ORDER`` line. The taps are the dual kind (the lab measured 15/s on both lanes); the mouth ports and
the left/right UG taps come next.
"""
import unittest

from fkcore import lang, rates
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate

CAT = Catalog.load()

RIB = """
module GearRib size 12x8 {
  port iron : in iron-plate @w
  port gear : out iron-gear-wheel @e
  g = AsmRow<n=1, recipe=iron-gear-wheel> @(1, 1)
  net fe: iron -> g
  net g: g -> gear
}
"""

MAP = """
feed = Chest<requester, item=iron-plate, rate=4> @(0, 0)
bus = Bus<belts=2, item=iron-plate>(fe: feed, fg: rib.iron) @(20, 0)
rib = GearRib @(40, 0)
box = Chest<provider, limit=8> @(60, 0)
net out: rib.gear -> box
"""

HAND = """
feed = Chest<requester, item=iron-plate, rate=4> @(0, 0)
bus = Bus<belts=2, item=iron-plate, load=n3, tap=n9, length=10> @(20, 0)
rib = GearRib @(40, 0)
box = Chest<provider, limit=8> @(60, 0)
net fe: feed -> bus.load1
net fg: bus.tap1 -> rib.iron
net out: rib.gear -> box
"""


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


class MapTest(unittest.TestCase):
    def test_the_list_binds_ports_in_order_and_names_the_nets(self):
        flat = flat_of(RIB + MAP)
        bus = flat.insts["bus"]
        self.assertEqual(bus.params["load"], ["n3"])
        self.assertEqual(bus.params["tap"], ["n9"])
        self.assertEqual(bus.params["length"], 10)
        self.assertEqual(flat.nets["fe"].drivers, [("feed/c0", "iron-plate")])
        self.assertEqual(flat.nets["fe"].consumers, [("bus/load1", "iron-plate")])
        self.assertEqual(flat.nets["fg"].drivers, [("bus/tap1", "iron-plate")])
        self.assertEqual(flat.nets["fg"].consumers, [("rib/iron", "iron-plate")])
        self.assertEqual([c for c in flat.checks if c.code == "ORDER"], [])

    def test_a_mouth_feeds_the_bus_in_line(self):
        flat = flat_of(RIB + MAP.replace("fe: feed", "in1: feed"))
        self.assertEqual(flat.insts["bus"].params["mouth"], ["in1"])
        self.assertEqual(flat.nets["in1"].drivers, [("feed/c0", "iron-plate")])
        self.assertEqual(flat.nets["in1"].consumers, [("bus/in1", "iron-plate")])
        self.assertEqual([c for c in flat.checks if c.code == "ORDER"], [])

    def test_a_mouth_is_upstream_of_every_tap(self):
        flat = flat_of(RIB + MAP.replace("(fe: feed, fg: rib.iron)", "(fg: rib.iron, in1: feed)"))
        self.assertEqual([c for c in flat.checks if c.code == "ORDER"], [])

    def test_a_mouth_must_be_a_source(self):
        with self.assertRaises(ElabError) as cm:
            flat_of(RIB + MAP.replace("fe: feed", "in1: rib.iron"))
        self.assertIn("a mouth is an input", str(cm.exception))

    def test_a_mouth_past_the_belt_count(self):
        with self.assertRaises(ElabError) as cm:
            flat_of(RIB + MAP.replace("fe: feed", "in3: feed"))
        self.assertIn("this bus has belts 1..2", str(cm.exception))

    def test_the_mouth_is_a_belt_end_on_the_head(self):
        from fkcore import expand
        flat = flat_of(RIB + MAP.replace("fe: feed", "in1: feed"))
        lay, notes = expand.expand_factory(flat, CAT)
        self.assertFalse([n for n in notes if n.startswith("bus")], notes)
        frag, binding = expand.fragment_of(flat, "bus", CAT)
        self.assertEqual(binding["in1"], "in1")
        self.assertEqual(frag.roles["in1"].attach, [(0.5, 1.5, 4)])   # the head tile, facing east

    def test_the_bus_pools_the_list_the_way_it_pools_penned_ports(self):
        listed, hand = flat_of(RIB + MAP), flat_of(RIB + HAND)
        for name in ("fe", "fg", "bus"):
            self.assertEqual(listed.nets[name].drivers, hand.nets[name].drivers)
            self.assertEqual(listed.nets[name].consumers, hand.nets[name].consumers)
        a, b = rates.solve(listed), rates.solve(hand)
        self.assertAlmostEqual(a.util["rib/g/m0"], b.util["rib/g/m0"])
        self.assertAlmostEqual(a.util["rib/g/m0"], 1.0)          # fed through the pool
        self.assertAlmostEqual(a.nets[("bus", "iron-plate")].delivered, 2.0, places=6)
        self.assertEqual(rates.underfed(a), [])

    def test_a_tap_before_any_load_is_an_order_line(self):
        flat = flat_of(RIB + MAP.replace("(fe: feed, fg: rib.iron)", "(fg: rib.iron, fe: feed)"))
        order = [c for c in flat.checks if c.code == "ORDER"]
        self.assertEqual(len(order), 1)
        self.assertIn("fg is a tap before any load", order[0].msg)

    def test_a_connection_list_replaces_load_and_tap_pins(self):
        with self.assertRaises(ElabError) as cm:
            flat_of(RIB + MAP.replace("item=iron-plate>", "item=iron-plate, load=n3>"))
        self.assertIn("replaces load=/tap=", str(cm.exception))

    def test_only_a_bus_takes_a_connection_list(self):
        with self.assertRaises(ElabError) as cm:
            flat_of(RIB + MAP + "\nrib2 = GearRib(fe: feed)\n")
        self.assertIn("is a Bus's port map", str(cm.exception))

    def test_an_inout_port_is_ambiguous(self):
        text = """
module M size 8x6 {
  port both : inout iron-plate @w
  n = AsmRow<n=1, recipe=pipe> @(1, 1)
  net a: both -> n
}
feed = Chest<requester, item=iron-plate, rate=2> @(0, 0)
bus = Bus<belts=2, item=iron-plate>(x: m.both) @(20, 0)
m = M @(40, 0)
"""
        with self.assertRaises(ElabError) as cm:
            flat_of(text)
        self.assertIn("needs an in port (a tap) or an out port (a load)", str(cm.exception))

    def test_a_connection_named_like_an_existing_net(self):
        with self.assertRaises(ElabError) as cm:
            flat_of(RIB + MAP + "\nnet fe: feed -> rib.iron\n")
        self.assertIn("net fe already exists", str(cm.exception))

    def test_a_connection_that_names_nothing(self):
        with self.assertRaises(ElabError) as cm:
            flat_of(RIB + MAP.replace("fe: feed", "fe: nope"))
        self.assertIn("nope names nothing", str(cm.exception))

    def test_a_bus_without_item(self):
        with self.assertRaises(ElabError) as cm:
            flat_of(RIB + MAP.replace(", item=iron-plate", ""))
        self.assertIn("needs item=", str(cm.exception))

    def test_a_short_length_is_refused(self):
        with self.assertRaises(ElabError) as cm:
            flat_of(RIB + MAP.replace("item=iron-plate>", "item=iron-plate, length=5>"))
        self.assertIn("short of the connection list", str(cm.exception))


class SyntaxTest(unittest.TestCase):
    def test_the_list_parses_in_order(self):
        f = lang.parse("bus = Bus<belts=2, item=iron-plate>(a: b.c, d: e) @(0, 0)", "t.fk")
        inst = f.body.insts[0]
        self.assertEqual([(n, str(r)) for n, r in inst.conns], [("a", "b.c"), ("d", "e")])

    def test_a_connection_name_twice(self):
        with self.assertRaises(lang.FkSyntaxError) as cm:
            lang.parse("bus = Bus<belts=2, item=iron-plate>(a: b, a: c)", "t.fk")
        self.assertIn("connection a given twice", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
