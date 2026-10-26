"""2.0.39 (PLAN-MODULES phase 4): `route --module X`, a sealed module's patch scope.

Changing a rib re-routes its frame and the parent segments ending at its ports; every other committed
route is kept as it stands.
"""
import unittest

from fkcore import expand, flow, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

RIB = """
module GearRib size 16x10 {
  port iron : in iron-plate @w
  port gear : out iron-gear-wheel @e
  g = AsmRow<n=1, recipe=iron-gear-wheel> @(2, 1)
  net fe: iron -> g
  net g: g -> gear
}
"""

DESIGN = RIB + """
feed = Chest<requester, item=iron-plate, rate=16> @(0, 20)
bus  = Bus<belts=4, item=iron-plate>(in1: feed, r0: rib0.iron, r1: rib1.iron) @(10, 20)
rib0 = GearRib @(2, 5)
rib1 = GearRib @(30, 5)
box0 = Chest<provider, limit=8> @(19, 10)
box1 = Chest<provider, limit=8> @(47, 10)
net g0: rib0.gear -> box0
net g1: rib1.gear -> box1
"""

MOVED = DESIGN.replace("rib0 = GearRib @(2, 5)", "rib0 = GearRib @(2, 8)")


def build(text):
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay, _notes = expand.expand_factory(flat, CAT)
    return flat, lay


def routed(text):
    flat, lay = build(text)
    return flat, route.route_layout(flat, lay, CAT).layout


def carriers(lay, net):
    return sorted((e.key.rsplit("/", 1)[-1], e.name, e.x, e.y, e.dir)
                  for e in lay.entities.values() if e.owner == "~" + net)


class ModuleScopeTest(unittest.TestCase):
    def test_the_scope_is_the_ribs_nets_and_its_port_segments(self):
        _flat, prev = routed(DESIGN)
        flat2, lay2 = build(MOVED)
        pinned, again = flow._module_pinned(flat2, prev, CAT, "rib0")
        for net in ("rib0/fe", "rib0/g", "r0", "g0"):
            self.assertIn(net, again)
        for net in ("rib1/fe", "rib1/g", "r1", "g1", "in1"):
            self.assertNotIn(net, again)
            self.assertIn(net, pinned)

    def test_the_other_ribs_route_is_kept_as_it_stands(self):
        _flat, prev = routed(DESIGN)
        flat2, lay2 = build(MOVED)
        pinned, _again = flow._module_pinned(flat2, prev, CAT, "rib0")
        r = route.route_layout(flat2, lay2, CAT, patch=pinned)
        self.assertEqual(r.failed, {})
        self.assertFalse([ln for ln in r.lines if ln.startswith(("SEAL", "PORT"))], r.lines)
        self.assertEqual([lk.text for lk in []], [])
        # rib1's carriers stand exactly where they were, and rib0's moved with it
        for net in ("rib1/fe", "rib1/g", "r1", "g1"):
            self.assertEqual(carriers(r.layout, net), carriers(prev, net), net)
        self.assertNotEqual(carriers(r.layout, "r0"), carriers(prev, "r0"))

    def test_a_module_that_is_not_sealed_is_reported(self):
        _flat, prev = routed(DESIGN)
        flat2, lay2 = build(MOVED)
        pinned, again = flow._module_pinned(flat2, prev, CAT, "nope")
        self.assertEqual(again, {})
        self.assertIn("rib1/fe", pinned)


if __name__ == "__main__":
    unittest.main()
