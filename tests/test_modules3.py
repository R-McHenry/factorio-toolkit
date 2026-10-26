"""2.0.36 (PLAN-MODULES phase 3): a sealed module's ports are tiles the router can meet, it routes
inside its frame, and SEAL reports a crossing that is not at a port.
"""
import unittest

from fkcore import expand, fkp as fkpmod, lang, route
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

DESIGN = """
module GearRib size 16x10 {
  port iron : in iron-plate @w
  port gear : out iron-gear-wheel @e
  g = AsmRow<n=1, recipe=iron-gear-wheel> @(2, 1)
  net fe: iron -> g
  net g: g -> gear
}
feed = Chest<requester, item=iron-plate, rate=4> @(0, 10)
bus = Bus<belts=2, item=iron-plate>(in1: feed, fg: rib.iron) @(20, 10)
rib = GearRib @(40, 10)
box = Chest<provider, limit=8> @(60, 10)
net out: rib.gear -> box
"""

PLAIN = """
module GearRib {
  c = Chest<requester, item=iron-plate, rate=2> @(0, 0)
  g = AsmRow<n=1, recipe=iron-gear-wheel> @(4, 0)
  b = Chest<provider, limit=8> @(20, 0)
  net fe: c -> g
  net g: g -> b
}
rib = GearRib @(40, 0)
"""


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def lay_of(text):
    flat = flat_of(text)
    return flat, expand.expand_factory(flat, CAT)[0]


def routed(text):
    flat = flat_of(text)
    lay, _notes = expand.expand_factory(flat, CAT)
    return flat, route.route_layout(flat, lay, CAT)


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


class SealTest(unittest.TestCase):
    def test_a_sealed_module_routes_inside_its_frame(self):
        flat, r = routed(DESIGN)
        self.assertEqual(r.failed, {})
        self.assertFalse([ln for ln in r.lines if ln.startswith("SEAL")], r.lines)
        x0, y0, x1, y1 = expand.frame_of(flat, r.layout, "rib", CAT)
        self.assertEqual((x0, y0, x1, y1), (40, 10, 56, 20))
        for net in ("rib/fe", "rib/g"):
            keys = [k for k, e in r.layout.entities.items() if e.attrs.get("net") == net]
            self.assertTrue(keys, net)
            for k in keys:
                for t in fkpmod.tiles_of(CAT, r.layout.entities[k]):
                    self.assertTrue(x0 <= t[0] < x1 and y0 <= t[1] < y1, (k, t))
        for net in ("fg", "in1", "out"):
            keys = [k for k, e in r.layout.entities.items() if e.attrs.get("net") == net]
            self.assertTrue(keys, net)
            for k in keys:
                for t in fkpmod.tiles_of(CAT, r.layout.entities[k]):
                    self.assertFalse(x0 <= t[0] < x1 and y0 <= t[1] < y1, (k, t))

    def test_the_route_meets_the_port_tile(self):
        _flat, r = routed(DESIGN)
        port = r.layout.entities["rib/port_iron"]
        self.assertEqual((port.x, port.y), (40.5, 15.5))       # the west edge, middle row
        kinds = ("transport-belt", "underground-belt", "splitter")
        last = [e for e in r.layout.entities.values()
                if e.attrs.get("net") == "fg" and e.name in kinds
                and e.x == 39.5 and e.y == 15.5]
        self.assertEqual(len(last), 1)                         # the carrier west of the port
        self.assertEqual(last[0].dir, 4)                       # facing the port
        first = [e for e in r.layout.entities.values()
                 if e.attrs.get("net") == "rib/fe" and e.name in kinds
                 and e.x == 41.5 and e.y == 15.5]
        self.assertEqual(len(first), 1)                        # the carrier inside it

    def test_a_portless_module_routes_as_one_block(self):
        _flat, r = routed(PLAIN)
        self.assertEqual(r.failed, {})
        self.assertFalse([ln for ln in r.lines if ln.startswith("SEAL")])
        self.assertFalse([k for k in r.layout.entities if "/port_" in k])
        self.assertIn("rib/g", r.routed)

    def test_seal_reports_a_crossing_outside_a_port(self):
        flat, r = routed(DESIGN)
        stray = fkpmod.Entity("rib/stray", "transport-belt", 42.5, 12.5, 4, {"net": "fg"})
        r.layout.entities[stray.key] = stray
        lines = route.seal_checks(flat, r.layout, CAT)
        self.assertEqual(len(lines), 1)
        self.assertIn("rib/stray (fg) stands inside sealed module rib", lines[0])


    def test_a_ribs_internal_route_is_the_same_after_a_parent_move(self):
        moved = DESIGN.replace("rib = GearRib @(40, 10)", "rib = GearRib @(40, 60)")
        moved = moved.replace("box = Chest<provider, limit=8> @(60, 10)", "box = Chest<provider, limit=8> @(60, 60)")
        _f1, a = routed(DESIGN)
        _f2, b = routed(moved)

        def inside(r, ox, oy):
            out = []
            for k, e in r.layout.entities.items():
                if e.attrs.get("net") in ("rib/fe", "rib/g") and k.startswith("~"):
                    out.append((k.rsplit("/", 1)[-1], round(e.x - ox, 3), round(e.y - oy, 3), e.dir))
            return sorted(out)
        self.assertEqual(inside(a, 40, 10), inside(b, 40, 60))
        self.assertEqual(b.failed, {})

    def test_a_port_whose_inside_tile_is_taken_is_a_port_line(self):
        tight = DESIGN.replace("size 16x10", "size 12x8").replace("@(2, 1)", "@(1, 1)")
        _flat, r = routed(tight)
        lines = " ".join(ln for ln in r.lines if ln.startswith("PORT"))
        self.assertIn("rib.iron", lines)
        self.assertIn("rib/g/m0", lines)


if __name__ == "__main__":
    unittest.main()
