"""One hand per (driver machine, consumer machine) pair, whatever nets want it (Rory 11-11: "Direct
insertion should have been solved by the router being smart enough to use one inserter when a
source and dest are a tile apart")."""
import unittest
from unittest import mock

from fkcore import connect, expand, fkp, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

# a requester hub: one chest, an assembler on each side of it, so one free tile between the chest
# and each assembler, and no tile for a belt to leave by
HUB = """
q   = Chest<requester, item="iron-plate,iron-gear-wheel,copper-plate,wood,copper-cable"> @(5, 5)
n   = Assembler<recipe=iron-gear-wheel> @(4, 1)
e   = Assembler<recipe=transport-belt> @(7, 4)
s   = Assembler<recipe=copper-cable> @(4, 7)
w   = Assembler<recipe=small-electric-pole> @(1, 4)
"""


def build(text):
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay, _notes = expand.expand_factory(flat, CAT)
    return flat, lay


def routed(text):
    flat, lay = build(text)
    return flat, route.route_layout(flat, lay, CAT)


def status(flat, r):
    rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
    return {n: x.status for n, x in rep.nets.items()}, rep


def laid(r, kind=None):
    return {k: e for k, e in r.layout.entities.items()
            if k.startswith("~") and (kind is None or e.name == kind)}


def line(r, net):
    return next(l for l in r.lines if l.split()[1].rstrip(":") == net)


class DirectShareTest(unittest.TestCase):
    def assert_connected(self, flat, r):
        self.assertEqual(r.failed, {}, r.lines)
        self.assertEqual(fkp.invariants(r.layout, CAT, nets=flat.nets), [])
        st, rep = status(flat, r)
        self.assertEqual(set(st.values()), {"connected"}, rep.lines())
        self.assertEqual(rep.leaks, [])
        self.assertEqual(rep.checks, [])

    def test_the_hub_of_one_net_per_item_shares_its_hands(self):
        # iron-plate goes into n and e, gears into e; wood and cable both into w. Each pair is one
        # hand: gw rides on fe's hand into e, wd on cb's into w (both FAILED: "no free tile is
        # reached from every driver and consumer")
        flat, r = routed(HUB + """
net fe items iron-plate: q -> n, e
net gw items iron-gear-wheel: q -> e
net cu items copper-plate: q -> s
net wd items wood: q -> w
net cb items copper-cable: q -> w
""")
        self.assert_connected(flat, r)
        self.assertEqual(laid(r, "transport-belt"), {})
        hands = laid(r)
        self.assertEqual(len(hands), 4)
        self.assertEqual(sorted(e.attrs["net"] for e in hands.values()),
                         ["cb+wd", "cu", "fe", "fe+gw"])
        self.assertIn("its hand is shared with fe's (direct insertion)", line(r, "gw"))
        self.assertIn("its hand is shared with cb's (direct insertion)", line(r, "wd"))
        # a shared hand off the requester is filtered to every item of its nets, not to one
        # net's (gears would never reach e)
        by_net = {e.attrs["net"]: e for e in hands.values()}
        self.assertEqual(by_net["fe+gw"].attrs["filter"], "iron-plate|iron-gear-wheel")
        self.assertEqual(by_net["cb+wd"].attrs["filter"], "copper-cable|wood")
        self.assertEqual(by_net["fe"].attrs["filter"], "iron-plate")

    def test_a_rebuild_keeps_the_shared_hands(self):
        # route --only stale: fe's committed hand (filtered to both items) stands, and gw, which
        # has no carrier of its own to keep, rides on it again instead of failing
        from fkcore import flow
        text = HUB + """
net fe items iron-plate: q -> n, e
net gw items iron-gear-wheel: q -> e
net cu items copper-plate: q -> s
net wd items wood: q -> w
net cb items copper-cable: q -> w
"""
        flat, r = routed(text)
        _flat, lay = build(text)
        pinned, again = flow._pinned_routes(flat, lay, r.layout, CAT)
        self.assertEqual(again, {})
        r2 = route.route_layout(flat, lay, CAT, patch=pinned)
        self.assert_connected(flat, r2)
        self.assertIn("its hand is shared with fe's", line(r2, "gw"))
        self.assertEqual({k: e.attrs for k, e in laid(r2).items()},
                         {k: e.attrs for k, e in laid(r).items()})

    def test_a_shared_hand_saves_a_belt(self):
        # fe into g and c, cu into c: fe rode on cu's hand into c (it belted c, 6 belts, before)
        flat, r = routed("""
q   = Chest<requester, item="iron-plate,copper-cable"> @(5, 5)
g   = Assembler<recipe=iron-gear-wheel> @(7, 4)
c   = Assembler<recipe=electronic-circuit> @(1, 4)
net fe items iron-plate: q -> g, c
net cu items copper-cable: q -> c
""")
        self.assert_connected(flat, r)
        self.assertEqual(laid(r, "transport-belt"), {})
        self.assertEqual(sorted(e.attrs["net"] for e in laid(r).values()), ["cu+fe", "fe"])

    def test_two_chests_into_two_machines_each_beside_both(self):
        # several drivers and several consumers: every pair a hand, no belt (it laid 17 belts)
        flat, r = routed("""
q1  = Chest<requester, item=iron-plate> @(4, 0)
q2  = Chest<requester, item=iron-plate> @(4, 2)
a   = Assembler<recipe=iron-gear-wheel> @(0, 0)
b   = Assembler<recipe=iron-gear-wheel> @(6, 0)
net fe: q1, q2 -> a, b
""")
        self.assert_connected(flat, r)
        self.assertEqual(laid(r, "transport-belt"), {})
        self.assertEqual(len(laid(r, "fast-inserter")), 4)
        self.assertIn("4 inserters (direct insertion)", line(r, "fe"))

    def test_two_chests_each_beside_one_machine_still_belt_the_rest(self):
        # each chest beside one machine only: the netlist has each chest feed both machines, so
        # the pairs no hand joins are belted (a hand between two ends the belt joins is not laid)
        flat, r = routed("""
q1  = Chest<requester, item=iron-plate> @(5, 5)
q2  = Chest<requester, item=iron-plate> @(5, 15)
g   = Assembler<recipe=iron-gear-wheel> @(7, 4)
h   = Assembler<recipe=iron-gear-wheel> @(7, 14)
net fe: q1, q2 -> g, h
""")
        self.assert_connected(flat, r)
        self.assertTrue(laid(r, "transport-belt"))

    def test_an_adjacent_consumer_and_a_far_one(self):
        flat, r = routed("""
q   = Chest<requester, item=iron-plate> @(5, 5)
g   = Assembler<recipe=iron-gear-wheel> @(7, 4)
far = Assembler<recipe=iron-gear-wheel> @(20, 4)
net fe: q -> g, far
""")
        self.assert_connected(flat, r)
        self.assertIn("1 inserter (direct insertion), then ", line(r, "fe"))
        self.assertTrue(laid(r, "transport-belt"))

    def test_the_split_hub_goes_direct(self):
        # a requester's split: net, one pair per two items: one hand from the chest into each
        # assembler carries both nets of a pair (it wanted two, one per net, and failed), and the
        # cable net's hand into w carries the copper-plate|wood pair too
        flat, r = routed(HUB + """
net all items iron-plate, iron-gear-wheel, copper-plate, wood, copper-cable split: q -> n, e, s, w
""")
        self.assert_connected(flat, r)
        self.assertEqual(laid(r, "transport-belt"), {})
        self.assertEqual(len(laid(r)), 4)
        self.assertIn("1 hand shared with all_copper_cable's",
                      line(r, "all_copper_plate|all_wood"))

    def test_a_split_net_goes_direct_where_it_can_and_belts_the_rest(self):
        flat, r = routed("""
q   = Chest<requester, item="iron-plate,iron-gear-wheel"> @(15, 15)
n   = Assembler<recipe=iron-gear-wheel> @(14, 11)
e   = Assembler<recipe=transport-belt> @(17, 14)
far = Assembler<recipe=transport-belt> @(4, 20)
net all items iron-plate, iron-gear-wheel split: q -> n, e, far
""")
        self.assert_connected(flat, r)
        self.assertIn("2 inserters (direct insertion), then trunk",
                      line(r, "all_iron_plate|all_iron_gear_wheel"))
        keys = list(laid(r))
        self.assertEqual(len(keys), len(set(keys)))

    def test_a_rider_that_loses_its_hand_is_not_lost(self):
        # the hand a net rode on is laid without it (here: never tagged): the judge finds the
        # rider apart, and it is routed again on its own (B: a belt to c) or reported (the hub:
        # no way out of the chest)
        with mock.patch.object(route, "_with_rider", lambda e, net: e):
            flat, r = routed("""
q   = Chest<requester, item="iron-plate,copper-cable"> @(5, 5)
g   = Assembler<recipe=iron-gear-wheel> @(7, 4)
c   = Assembler<recipe=electronic-circuit> @(1, 4)
net fe items iron-plate: q -> g, c
net cu items copper-cable: q -> c
""")
            self.assert_connected(flat, r)
            self.assertNotIn("shared", line(r, "fe"))
            flat, r = routed(HUB + """
net fe items iron-plate: q -> n, e
net gw items iron-gear-wheel: q -> e
net cu items copper-plate: q -> s
net wd items wood: q -> w
net cb items copper-cable: q -> w
""")
        self.assertEqual(sorted(r.failed), ["gw", "wd"])
        self.assertIn("does not connect", r.failed["gw"])


if __name__ == "__main__":
    unittest.main()
