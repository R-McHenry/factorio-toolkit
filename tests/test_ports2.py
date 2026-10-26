"""2.0.41 (PLAN-GLOBAL phase A): whole-belt ports and recorded port tiles.

1. **A net ending at an ``X | X`` port is laid and rated on both lanes.** The declaration existed
   since 2.0.30, but 2.0's net was one lane: the port's carrier carried ``net=A`` and the crossing
   route behind it ran one lane at 7.5/s. Now the carrier says ``net=A|A`` (both lanes are the
   net's), so a two-sided source (a ``MinerRow`` drops onto both lanes) crosses at 15/s on yellow,
   and ``CAPACITY`` rates the **port's width**: an ``X | X`` port is 15/s, a one-lane port (``@e4L``)
   7.5/s. A rear: a both-lane port also asks for both lanes' flow.
2. **A port tile faces its partner unless pinned**: the tile of the declared side nearest the other
   end's attach point, instead of the middle of that side.
3. **Port tiles are recorded in the .fkp** (``port <inst>.<name> at x,y dir D lane L|R|LR items
   ...``, in the module's own frame) and kept like a committed route: a rebuild reads the tile back,
   so a parent change never moves a port, and the module's inside routes stay byte for byte.
"""
import unittest

from fkcore import expand, fkp as fkpmod, lang, route, routed
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

#: A plot exporting 15/s: a two-sided MinerRow drops 15 drills on each lane (0.5/s a drill), so its
#: own belt carries 15/s. Through an ``X | X`` out port and an ``X | X`` in port, the crossing net is
#: laid on both lanes.
PLOT = """
module Plot size 50x10 {
  port ore : out iron-ore | iron-ore @e
  row = MinerRow<n=30, resource=iron-ore> @(1, 1)
  net dig: row -> ore
}
module Base size 16x10 {
  port ore : in iron-ore | iron-ore @w
  box = Chest<provider, limit=8> @(12, 4)
  net into: ore -> box
}
plot = Plot @(0, 0)
base = Base @(70, 0)
net ore: plot.ore -> base.ore
"""

ONE_LANE = PLOT.replace("out iron-ore | iron-ore @e", "out iron-ore @e") \
                .replace("in iron-ore | iron-ore @w", "in iron-ore @w")

#: A small rib: the west port's partner is the feed chest, which stands 4 rows below the module's
#: middle (an unpinned port faced its partner before 2.0.41; the middle was h // 2).
RIB = """
module Rib size 16x10 {
  port iron : in iron-plate @w
  port gear : out iron-gear-wheel @e
  g = AsmRow<n=1, recipe=iron-gear-wheel> @(2, 1)
  net fe: iron -> g
  net g: g -> gear
}
feed = Chest<requester, item=iron-plate, rate=4> @(0, 14)
rib = Rib @(40, 10)
box = Chest<provider, limit=8> @(70, 10)
net ore: feed -> rib.iron
net out: rib.gear -> box
"""


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def build(text, previous=None):
    """(flat, the placed layout, the routed layout): one build of ``text``, reading ``previous``'s
    port records and pinned entities like a rebuild does."""
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t", layout=previous)
    lay, notes = expand.expand_factory(flat, CAT, previous)
    return flat, lay, route.route_layout(flat, lay, CAT)


def carrier(flat, key):
    """The layout key of a port's carrier belt."""
    inst, _slash, name = key.rpartition("/")
    return f"{inst}/port_{name}"


def inside(r, prefix, oy):
    """A module's own routed carriers, relative to its origin (its inside routes)."""
    return sorted((k, e.name, e.dir, round(e.x, 3), round(e.y - oy, 3))
                  for k, e in r.layout.entities.items() if k.startswith(prefix))


class BothLaneTest(unittest.TestCase):
    """Item 1: a net ending at an ``X | X`` port is laid and rated on both lanes."""

    def test_the_port_carrier_carries_the_net_on_both_lanes(self):
        flat, lay, _r = build(PLOT)
        port = flat.ports["plot/ore"]
        self.assertTrue(port.both)
        self.assertEqual(port.width_of("iron-ore"), 2)
        self.assertEqual(port.width_of("coal"), 0)
        self.assertEqual(lay.entities["plot/port_ore"].attrs["net"], "plot/dig|plot/dig")
        self.assertEqual(lay.ports["plot.ore"].lane, "LR")

    def test_a_one_lane_port_is_one_lane(self):
        flat, lay, _r = build(ONE_LANE)
        port = flat.ports["plot/ore"]
        self.assertFalse(port.both)
        self.assertEqual(port.width_of("iron-ore"), 1)
        self.assertEqual(lay.entities["plot/port_ore"].attrs["net"], "plot/dig")
        self.assertIn(lay.ports["plot.ore"].lane, ("L", "R"))

    def test_a_15_s_crossing_routes_through_one_port_on_both_lanes(self):
        flat, _lay, r = build(PLOT)
        self.assertEqual(r.failed, {})
        self.assertEqual([ln for ln in r.lines if ln.startswith(("SEAL", "FRAME", "PORT"))], [])
        rr = routed.solve(flat, r.layout, CAT)
        for key in ("plot/ore", "base/ore"):
            lanes = [(carrier(flat, key), lane) for lane in ("L", "R")]
            need = [rr.need.get(nid, {}).get("iron-ore", 0.0) for nid in lanes]
            self.assertEqual([round(x, 3) for x in need], [7.5, 7.5], key)   # 15/s in all
            self.assertEqual([rr.lg.nodes[nid].cap for nid in lanes], [7.5, 7.5])
        _lines, checks = routed.report(rr, "t")
        self.assertEqual([c for c in checks if c.code == "CAPACITY" and c.where.startswith("port")],
                         [])                      # a both-lane port carries the 15/s it is asked

    def test_a_one_lane_port_is_rated_at_one_lane(self):
        flat, _lay, r = build(ONE_LANE)
        self.assertEqual(r.failed, {})
        rr = routed.solve(flat, r.layout, CAT)
        _lines, checks = routed.report(rr)
        ports = [c for c in checks if c.code == "CAPACITY" and c.where.startswith("port")]
        self.assertEqual([c.where for c in ports], ["port base/ore", "port plot/ore"])
        for c in ports:
            self.assertIn("15.00/s asked through it", c.msg)
            self.assertIn("a one-lane port carries 7.50/s", c.msg)
            self.assertIn("declare it both lanes (item | item)", c.msg)

    def test_the_crossing_is_connected_with_no_leak(self):
        from fkcore import connect
        flat, _lay, r = build(PLOT)
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
        self.assertEqual(rep.leaks, [])
        self.assertEqual({n: x.status for n, x in rep.nets.items()},
                         {n: "connected" for n in rep.nets})


class PortTileTest(unittest.TestCase):
    """Item 2: a port tile faces its partner unless pinned."""

    def test_an_unpinned_port_faces_its_partner(self):
        flat, lay, _r = build(RIB)
        # the feed stands at y 14.5; the module at (40, 10) is 16x10, so the middle would be 15
        self.assertEqual(flat.port_tiles["rib/iron"], (0, 4, 12, "R"))
        self.assertEqual((lay.entities["rib/port_iron"].x, lay.entities["rib/port_iron"].y),
                         (40.5, 14.5))
        self.assertEqual(lay.ports["rib.iron"], fkpmod.PortRec("rib.iron", 0, 4, 4, "R",
                                                               "iron-plate"))

    def test_a_pinned_port_keeps_its_tile(self):
        flat, lay, r = build(RIB.replace("iron-plate @w", "iron-plate @w2"))
        self.assertEqual(lay.ports["rib.iron"], fkpmod.PortRec("rib.iron", 0, 1, 4, "R",
                                                               "iron-plate"))
        self.assertEqual((lay.entities["rib/port_iron"].x, lay.entities["rib/port_iron"].y),
                         (40.5, 11.5))
        self.assertFalse([ln for ln in r.lines if ln.startswith("PORT")])

    def test_a_turned_module_keeps_its_recorded_tile(self):
        # the rib turned a quarter turn clockwise: the recorded tile is in its own frame, so it
        # stays where the build first chose it, and the carrier lands where the turn puts it
        _f1, lay1, _r1 = build(RIB)
        turned = RIB.replace("rib = Rib @(40, 10)", "rib = Rib @(40, 10, rot 1)")
        _f2, lay2, r2 = build(turned, lay1)
        self.assertEqual(lay2.ports["rib.iron"], lay1.ports["rib.iron"])
        self.assertEqual(lay2.ports["rib.iron"], fkpmod.PortRec("rib.iron", 0, 4, 4, "R",
                                                                "iron-plate"))
        self.assertEqual(lay2.entities["rib/port_iron"].dir, 8)     # E in the own frame, turned
        self.assertEqual((lay2.entities["rib/port_iron"].x, lay2.entities["rib/port_iron"].y),
                         (45.5, 10.5))
        self.assertEqual([ln for ln in r2.lines if ln.startswith(("SEAL", "FRAME", "PORT"))], [])
        # a fresh build of the turned design (no record) chooses to face its partner instead
        _f3, lay3, _r3 = build(turned)
        self.assertEqual(lay3.ports["rib.iron"].y, 9)


class RecordTest(unittest.TestCase):
    """Item 3: port tiles are recorded in the .fkp and kept like committed routes."""

    def test_the_port_line_is_written_and_reads_back(self):
        flat, lay, _r = build(RIB)
        text = fkpmod.dumps(lay, CAT)
        self.assertIn("port rib.iron at 0,4 dir E lane R items iron-plate", text)
        again = fkpmod.loads(text)
        self.assertEqual(again.ports, lay.ports)
        self.assertEqual(fkpmod.invariants(lay, CAT, nets=flat.nets), [])

    def test_a_parent_move_keeps_the_port_and_the_inside_routes(self):
        _f1, lay1, r1 = build(RIB)
        moved = RIB.replace("rib = Rib @(40, 10)", "rib = Rib @(40, 60)") \
                   .replace("@(0, 14)", "@(0, 64)").replace("@(70, 10)", "@(70, 60)")
        _f2, lay2, r2 = build(moved, lay1)
        self.assertEqual(lay2.ports, lay1.ports)                # same tile, own frame
        self.assertEqual(r2.failed, {})
        self.assertEqual(inside(r1, "~rib/", 10), inside(r2, "~rib/", 60))
        self.assertEqual((lay2.entities["rib/port_iron"].x, lay2.entities["rib/port_iron"].y),
                         (40.5, 64.5))
        self.assertEqual([ln for ln in r2.lines if ln.startswith(("SEAL", "FRAME", "PORT"))], [])

    def test_a_pin_and_a_record_that_disagree_is_a_port_line(self):
        _f1, lay1, _r1 = build(RIB)
        # the source now pins the port two rows above the committed tile: the pin wins
        _f2, _lay2, r2 = build(RIB.replace("iron-plate @w", "iron-plate @w2"), lay1)
        lines = [ln for ln in r2.lines if ln.startswith("PORT")]
        self.assertEqual(len(lines), 1, r2.lines)
        self.assertIn("rib/iron", lines[0])
        self.assertIn("the committed tile 0,4 and the pin @w2 disagree", lines[0])
        self.assertIn("the pin wins", lines[0])

    def test_a_record_for_a_port_that_is_gone_is_a_port_check(self):
        _f1, lay1, _r1 = build(RIB)
        # the port is renamed: the committed record for the old name has no port any more
        renamed = RIB.replace("port iron : in iron-plate @w", "port input : in iron-plate @w") \
                     .replace("net fe: iron -> g", "net fe: input -> g") \
                     .replace("feed -> rib.iron", "feed -> rib.input")
        f = lang.parse(renamed, "t.fk")
        flat = elaborate(f, dict(f.modules), CAT, "t", layout=lay1)
        gone = [c for c in flat.checks if c.code == "PORT" and "declares no such port" in c.msg]
        self.assertEqual(len(gone), 1, flat.checks)
        self.assertIn("rib/iron", gone[0].where)


if __name__ == "__main__":
    unittest.main()
