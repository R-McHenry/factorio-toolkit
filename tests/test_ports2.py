"""2.0.41 (PLAN-GLOBAL phase A): whole-belt ports and recorded port tiles.

1. **A net ending at an ``X | X`` port is laid and rated on both lanes.** The declaration existed
   since 2.0.30, but 2.0's net was one lane: the port's carrier carried ``net=A`` and the crossing
   route behind it ran one lane at 7.5/s. Now the carrier says ``net=A|A`` (both lanes are the
   net's), so a two-sided source (a ``MinerRow`` drops onto both lanes) crosses at 15/s on yellow,
   and ``too-thin`` rates the **port's width**: an ``X | X`` port is 15/s, a one-lane port (``@e4L``)
   7.5/s. A rear: a both-lane port also asks for both lanes' flow.
2. **A port tile faces its partner unless pinned**: the tile of the declared side nearest the other
   end's attach point, instead of the middle of that side.
3. **Port tiles are recorded in the .fkp** (``port <inst>.<name> at x,y dir D lane L|R|LR items
   ...``, in the module's own frame) and kept like a committed route: a rebuild reads the tile back,
   so a parent change never moves a port, and the module's inside routes stay byte for byte.
"""
import types
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


def port_at(flat, lay, key):
    """2.0.48: a port is an edge; this is the tile just inside it (as x, y centers) and the
    direction the items cross it (0 N, 4 E, 8 S, 12 W), as the carrier belt of 2.0.41 had them."""
    pe = expand.port_edges(flat, lay, CAT)[key]
    d = {(0, -1): 0, (1, 0): 4, (0, 1): 8, (-1, 0): 12}[(pe.dst[0] - pe.src[0], pe.dst[1] - pe.src[1])]
    return types.SimpleNamespace(x=pe.inside[0] + 0.5, y=pe.inside[1] + 0.5, dir=d)


def inside_belt(flat, lay, key):
    """The key of the route belt on the tile just inside port ``key``'s edge."""
    pe = expand.port_edges(flat, lay, CAT)[key]
    return next(k for k, e in lay.entities.items()
                if (int(e.x // 1), int(e.y // 1)) == tuple(pe.inside))


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
        self.assertEqual(lay.ports["plot.ore"].lane, "LR")
        lay = _r.layout                       # 2.0.48: no carrier; the route's belt inside the edge
        self.assertEqual(lay.entities[inside_belt(flat, lay, "plot/ore")].attrs["net"], "plot/dig")

    def test_a_one_lane_port_is_one_lane(self):
        flat, lay, _r = build(ONE_LANE)
        port = flat.ports["plot/ore"]
        self.assertFalse(port.both)
        self.assertEqual(port.width_of("iron-ore"), 1)
        self.assertIn(lay.ports["plot.ore"].lane, ("L", "R"))
        lay = _r.layout
        self.assertEqual(lay.entities[inside_belt(flat, lay, "plot/ore")].attrs["net"], "plot/dig")

    def test_a_15_s_crossing_routes_through_one_port_on_both_lanes(self):
        flat, _lay, r = build(PLOT)
        self.assertEqual(r.failed, {})
        self.assertEqual([ln for ln in r.lines if ln.startswith(("crosses-frame", "FRAME", "port"))], [])
        rr = routed.solve(flat, r.layout, CAT)
        for key in ("plot/ore", "base/ore"):
            lanes = [(inside_belt(flat, r.layout, key), lane) for lane in ("L", "R")]
            need = [rr.need.get(nid, {}).get("iron-ore", 0.0) for nid in lanes]
            self.assertEqual([round(x, 3) for x in need], [7.5, 7.5], key)   # 15/s in all
            self.assertEqual([rr.lg.nodes[nid].cap for nid in lanes], [7.5, 7.5])
        _lines, checks = routed.report(rr, "t")
        self.assertEqual([c for c in checks if c.code == "too-thin" and c.where.startswith("port")],
                         [])                      # a both-lane port carries the 15/s it is asked

    def test_an_unpinned_port_is_as_wide_as_its_belt(self):
        # 2.0.54: written one item, but the two-sided row fills both lanes inside it, so it
        # carries the 15/s
        flat, _lay, r = build(ONE_LANE)
        self.assertEqual(r.failed, {})
        rr = routed.solve(flat, r.layout, CAT)
        _lines, checks = routed.report(rr)
        self.assertEqual([c for c in checks if c.code == "too-thin" and c.where.startswith("port")],
                         [])

    def test_a_port_pinned_to_one_lane_is_rated_at_one_lane(self):
        pinned = ONE_LANE.replace("out iron-ore @e", "out iron-ore @e4L") \
                         .replace("in iron-ore @w", "in iron-ore @w4L")
        flat, _lay, r = build(pinned)
        self.assertEqual(r.failed, {})
        rr = routed.solve(flat, r.layout, CAT)
        _lines, checks = routed.report(rr)
        ports = [c for c in checks if c.code == "too-thin" and c.where.startswith("port")]
        self.assertEqual([c.where for c in ports], ["port base/ore", "port plot/ore"])
        for c in ports:
            self.assertIn("15.00/s asked through it", c.msg)
            self.assertIn("a one-lane port carries 7.50/s", c.msg)
            self.assertIn("declare it both lanes (item | item)", c.msg)

    def test_the_crossing_is_connected_with_no_leak(self):
        from fkcore import connect
        flat, _lay, r = build(PLOT)
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat),
                              expand.port_edges(flat, r.layout, CAT))
        self.assertEqual(rep.leaks, [])
        self.assertEqual({n: x.status for n, x in rep.nets.items()},
                         {n: "connected" for n in rep.nets})


class PortTileTest(unittest.TestCase):
    """Item 2: a port tile faces its partner unless pinned."""

    def test_an_unpinned_port_faces_its_partner(self):
        flat, lay, _r = build(RIB)
        # the feed stands at y 14.5; the module at (40, 10) is 16x10, so the middle would be 15
        self.assertEqual(flat.port_tiles["rib/iron"], (0, 4, 12, "R"))
        self.assertEqual((port_at(flat, lay, "rib/iron").x, port_at(flat, lay, "rib/iron").y),
                         (40.5, 14.5))
        self.assertEqual(lay.ports["rib.iron"], fkpmod.PortRec("rib.iron", 0, 4, 4, "R",
                                                               "iron-plate"))

    def test_a_pinned_port_keeps_its_tile(self):
        # 2.0.42: a pin counts from 0 along the side, as the PORT check and @n0L do
        flat, lay, r = build(RIB.replace("iron-plate @w", "iron-plate @w2"))
        self.assertEqual(lay.ports["rib.iron"], fkpmod.PortRec("rib.iron", 0, 2, 4, "R",
                                                               "iron-plate"))
        self.assertEqual((port_at(flat, lay, "rib/iron").x, port_at(flat, lay, "rib/iron").y),
                         (40.5, 12.5))
        self.assertFalse([ln for ln in r.lines if ln.startswith("port")])

    def test_a_turned_module_keeps_its_recorded_tile(self):
        # the rib turned a quarter turn clockwise: the recorded tile is in its own frame, so it
        # stays where the build first chose it, and the carrier lands where the turn puts it
        _f1, lay1, _r1 = build(RIB)
        turned = RIB.replace("rib = Rib @(40, 10)", "rib = Rib @(50, 10, rot 1)")   # 3.0.1: its origin
        _f2, lay2, r2 = build(turned, lay1)
        self.assertEqual(lay2.ports["rib.iron"], lay1.ports["rib.iron"])
        self.assertEqual(lay2.ports["rib.iron"], fkpmod.PortRec("rib.iron", 0, 4, 4, "R",
                                                                "iron-plate"))
        self.assertEqual(port_at(_f2, lay2, "rib/iron").dir, 8)     # E in the own frame, turned
        self.assertEqual((port_at(_f2, lay2, "rib/iron").x, port_at(_f2, lay2, "rib/iron").y),
                         (45.5, 10.5))
        self.assertEqual([ln for ln in r2.lines if ln.startswith(("crosses-frame", "FRAME", "port"))], [])
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
        self.assertEqual((port_at(_f2, lay2, "rib/iron").x, port_at(_f2, lay2, "rib/iron").y),
                         (40.5, 64.5))
        self.assertEqual([ln for ln in r2.lines if ln.startswith(("crosses-frame", "FRAME", "port"))], [])

    def test_a_pin_and_a_record_that_disagree_is_a_port_line(self):
        _f1, lay1, _r1 = build(RIB)
        # the source now pins the port two rows above the committed tile: the pin wins
        _f2, _lay2, r2 = build(RIB.replace("iron-plate @w", "iron-plate @w2"), lay1)
        lines = [ln for ln in r2.lines if ln.startswith("port")]
        self.assertEqual(len(lines), 1, r2.lines)
        self.assertIn("rib/iron", lines[0])
        self.assertIn("the committed tile 0,4 is dropped: the pin @w2 moves it to 0,2", lines[0])

    def test_the_pin_wins_over_a_record(self):
        # 2.0.42: 2.0.41 printed "the pin wins" and kept the carrier on the committed tile
        _f1, lay1, _r1 = build(RIB)
        _f2, lay2, r2 = build(RIB.replace("iron-plate @w", "iron-plate @w2"), lay1)
        self.assertEqual((port_at(_f2, lay2, "rib/iron").x, port_at(_f2, lay2, "rib/iron").y),
                         (40.5, 12.5))
        self.assertEqual((lay2.ports["rib.iron"].x, lay2.ports["rib.iron"].y), (0, 2))
        self.assertEqual(r2.failed, {})
        # the next build reads the new record: the line is gone
        _f3, _lay3, r3 = build(RIB.replace("iron-plate @w", "iron-plate @w2"), lay2)
        self.assertFalse([ln for ln in r3.lines if ln.startswith("port")])

    def test_a_port_moved_to_another_side_is_chosen_again(self):
        _f1, lay1, _r1 = build(RIB)
        _f2, lay2, r2 = build(RIB.replace("iron-plate @w", "iron-plate @n"), lay1)
        rec = lay2.ports["rib.iron"]
        self.assertEqual(rec.y, 0)                              # on the north edge now
        self.assertEqual(port_at(_f2, lay2, "rib/iron").y, 10.5)
        lines = [ln for ln in r2.lines if ln.startswith("port")]
        self.assertEqual(len(lines), 1, r2.lines)
        self.assertIn("not on the n edge", lines[0])
        self.assertEqual(r2.failed, {})

    def test_a_pin_at_zero_is_the_first_tile(self):
        _flat, lay, r = build(RIB.replace("iron-plate @w", "iron-plate @w0"))
        self.assertEqual((lay.ports["rib.iron"].x, lay.ports["rib.iron"].y), (0, 0))
        self.assertEqual(r.failed, {})

    def test_a_record_for_a_port_that_is_gone_is_a_port_check(self):
        _f1, lay1, _r1 = build(RIB)
        # the port is renamed: the committed record for the old name has no port any more
        renamed = RIB.replace("port iron : in iron-plate @w", "port input : in iron-plate @w") \
                     .replace("net fe: iron -> g", "net fe: input -> g") \
                     .replace("feed -> rib.iron", "feed -> rib.input")
        f = lang.parse(renamed, "t.fk")
        flat = elaborate(f, dict(f.modules), CAT, "t", layout=lay1)
        gone = [c for c in flat.checks if c.code == "port" and "declares no such port" in c.msg]
        self.assertEqual(len(gone), 1, flat.checks)
        self.assertIn("rib/iron", gone[0].where)


if __name__ == "__main__":
    unittest.main()
