"""2.0.36 (PLAN-MODULES phase 3.1): a sealed module's ports are tiles the router can meet.

The carrier belt and the two roles of each port, and the module's own instance in the layout, so the
parent's route ends at the port's outside tile and the module's own net starts at its inside one.
Routing inside the frame (bounds) and the SEAL check are the next slices.
"""
import unittest

from fkcore import expand, lang
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

RIB = """
module GearRib size 12x8 {
  port iron : in iron-plate @w
  port gear : out iron-gear-wheel @e
  g = AsmRow<n=1, recipe=iron-gear-wheel> @(1, 1)
  net fe: iron -> g
  net g: g -> gear
}
feed = Chest<requester, item=iron-plate, rate=4> @(0, 0)
rib = GearRib @(40, 0)
box = Chest<provider, limit=8> @(60, 0)
net fg: feed -> rib.iron
net out: rib.gear -> box
"""

PLAIN = """
module GearRib {
  g = AsmRow<n=1, recipe=iron-gear-wheel> @(1, 1)
}
rib = GearRib @(40, 0)
"""


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def lay_of(text):
    flat = flat_of(text)
    return flat, expand.expand_factory(flat, CAT)[0]


class PortTileTest(unittest.TestCase):
    def test_each_port_is_a_carrier_on_its_side_and_two_roles(self):
        flat = flat_of(RIB)
        frag, binding = expand.fragment_of(flat, "rib", CAT)
        self.assertEqual(sorted(frag.roles), ["gear", "gear!", "iron", "iron!"])
        self.assertEqual(frag.roles["iron"].attach, [(0.5, 4.5, 4)])    # west edge, facing in (east)
        self.assertEqual(frag.roles["iron!"].attach, [(0.5, 4.5, 4)])
        self.assertEqual(frag.roles["gear"].attach, [(11.5, 4.5, 4)])   # east edge, facing out (east)
        self.assertEqual(frag.roles["iron"].side, "out")                # the module net's driver
        self.assertEqual(frag.roles["iron!"].side, "in")                # the parent net's consumer
        self.assertEqual(frag.roles["gear"].side, "in")
        self.assertEqual(frag.roles["gear!"].side, "out")
        self.assertEqual(binding["iron"], "rib/fe")
        self.assertEqual(binding["iron!"], "fg")
        self.assertEqual(binding["gear"], "rib/g")
        self.assertEqual(binding["gear!"], "out")
        belts = {e.local: e for e in frag.entities}
        self.assertEqual(belts["port_iron"].dir, 4)                     # an in port faces in
        self.assertEqual(belts["port_gear"].dir, 4)

    def test_the_layout_records_the_module_and_its_port_carriers(self):
        _flat, lay = lay_of(RIB)
        self.assertIn("rib", lay.insts)
        self.assertIn("rib/port_iron", lay.entities)
        self.assertIn("rib/port_gear", lay.entities)
        self.assertEqual((lay.entities["rib/port_iron"].x, lay.entities["rib/port_iron"].y),
                         (40.5, 4.5))
        self.assertEqual((lay.entities["rib/port_gear"].x, lay.entities["rib/port_gear"].y),
                         (51.5, 4.5))

    def test_a_module_without_a_frame_stays_out_of_the_layout(self):
        _flat, lay = lay_of(PLAIN)
        self.assertNotIn("rib", lay.insts)


if __name__ == "__main__":
    unittest.main()
