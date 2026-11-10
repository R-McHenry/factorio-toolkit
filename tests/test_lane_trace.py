"""53-lanetrace (Rory, 2026-11-10: "the lane model should only have one way to know what nets are
on lanes and it's by tracing all of it"): ``lanes.contents`` traces items from where they are
made along the lane physics, wanted or not; the pair router judges a layout by it (no part's belt
end stamped as its own net), and report_checks' ``LANE-MIX`` names a lane that holds an item none
of its nets carries, at the belt it comes off. The T6 flower's case: a column's paired belt runs
on out of a one-item port, its leftovers ride along, and a side-load stacks them onto one lane."""
import types
import unittest

from fkcore import connect, expand, fkp, flow, lanes, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate
from fkcore.fkp import Entity
from tests.test_lanes_pairs import SMELT

CAT = Catalog.load()
N, E, S, W = 0, 4, 8, 12


def belt(key, x, y, d):
    return Entity(key, "transport-belt", x + 0.5, y + 0.5, d, {})


def traced(ents, seeds, key):
    """{lane: items} on belt ``key`` from ``seeds`` {belt key: (left items, right items)}."""
    lg = lanes.build(ents, CAT)
    got = lanes.contents(lg, CAT, seeds=[((k, ln), items) for k, (li, ri) in seeds.items()
                                         for ln, items in (("L", li), ("R", ri))])
    return {ln: set(got.get((key, ln), ())) for ln in "LR"}


class Contents(unittest.TestCase):
    """A trunk east along y=5 (t0, t1, t2); feeds from the north side-load its left lane, from
    the south its right."""

    def test_two_one_item_feeds_make_two_lanes(self):
        ents = [belt("t0", 5, 5, E), belt("t1", 6, 5, E), belt("a", 5, 4, S), belt("b", 5, 6, N)]
        got = traced(ents, {"a": (["iron-plate"], ["iron-plate"]),
                            "b": (["coal"], ["coal"])}, "t1")
        self.assertEqual(got, {"L": {"iron-plate"}, "R": {"coal"}})

    def test_a_feed_that_carries_two_items_puts_both_on_one_lane(self):
        """The leak: B's belt still carries its pair's leftover iron on one lane."""
        ents = [belt("t0", 5, 5, E), belt("t1", 6, 5, E), belt("a", 5, 4, S), belt("b", 5, 6, N)]
        got = traced(ents, {"a": (["copper-plate"], ["copper-plate"]),
                            "b": (["iron-plate"], ["coal"])}, "t1")
        self.assertEqual(got, {"L": {"copper-plate"}, "R": {"iron-plate", "coal"}})

    def test_items_ride_on_past_where_nothing_picks_them(self):
        ents = [belt(f"t{i}", 5 + i, 5, E) for i in range(6)]
        got = traced(ents, {"t0": (["iron-plate"], ["copper-plate"])}, "t5")
        self.assertEqual(got, {"L": {"iron-plate"}, "R": {"copper-plate"}})

    def test_a_turn_keeps_its_lanes(self):
        ents = [belt("a0", 5, 5, E), belt("a1", 6, 5, S), belt("a2", 6, 6, S)]
        got = traced(ents, {"a0": (["iron-plate"], ["coal"])}, "a2")
        self.assertEqual(got, {"L": {"iron-plate"}, "R": {"coal"}})

    def test_a_machine_passes_on_only_what_it_makes(self):
        """The smelter pair routed: plates come off the smelters, no ore or coal rides onto the
        plate belt, and the trunk's lanes hold ore and coal apart."""
        flat = elaborate(*_parsed(SMELT), CAT, "t")
        lay, _n = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})
        lg = lanes.build(list(r.layout.entities.values()), CAT)
        have = lanes.contents(lg, CAT)
        plates = [k for k, e in r.layout.entities.items()
                  if e.attrs.get("net") == "plates" and CAT.kind(e.name) == "transport-belt"]
        self.assertTrue(plates)
        for k in plates:
            for ln in "LR":
                self.assertLessEqual(set(have.get((k, ln), ())), {"iron-plate"})
        self.assertEqual(_mix(flat, r.layout), [])


def _parsed(text):
    f = lang.parse(text, "t.fk")
    return f, dict(f.modules)


def _mix(flat, lay):
    ports = expand.port_edges(flat, lay, CAT) if flat.ports else None
    rep = connect.connect(lay, CAT, connect.endpoints(flat), ports)
    ctx = types.SimpleNamespace(cat=CAT)
    return flow._lane_mix_checks(ctx, "t", flat, lay, rep, ports)


#: The T6 Ridge shape, small: a column's cells pass iron | copper up a paired belt; the column
#: hands it out of a one-item port as copper; the copper belt's end carries the iron too.
LEAK = """
module Cell size 3x3 {
  port i : in iron-plate | copper-plate @s0
  port o : out iron-plate | copper-plate @n0
  stack i -> o
  box = Chest<provider> @(2, 1)
  net a items iron-plate: i -> box, o
  net c items copper-plate: i -> o
  lanes a | c
}
module Col size 5x10 {
  port ac_in : in  iron-plate | copper-plate @s1
  port c_out : out copper-plate @n1
  cells = Stack<cell=Cell, n=2> @(1, 2)
  net a items iron-plate:   ac_in -> cells.i
  net c items copper-plate: ac_in -> cells.i
  lanes a | c
  net cx items copper-plate: cells.o -> c_out
}
fe = Chest<infinity, item=iron-plate, rate=5/s> @(2, 24)
cu = Chest<infinity, item=copper-plate, rate=5/s> @(8, 24)
col = Col @(2, 6)
out = Chest<provider> @(4, 1)
net fe_in items iron-plate: fe -> col.ac_in
net cu_in items copper-plate: cu -> col.ac_in
lanes fe_in | cu_in
net cu_out: col.c_out -> out
"""


class LaneMix(unittest.TestCase):
    def test_a_one_item_port_off_a_paired_belt_is_named(self):
        flat = elaborate(*_parsed(LEAK), CAT, "t")
        lay, _n = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})
        got = _mix(flat, r.layout)
        self.assertTrue(got, "no LANE-MIX")
        first = got[0]
        self.assertEqual(first.code, "LANE-MIX")
        self.assertIn("iron-plate reaches", first.msg)
        self.assertIn("does not carry: it comes off", first.msg)


#: LEAK's copper port paired with a coal feed: its belt end carries the iron on, so a side-load
#: of it would put iron on the copper lane.
PAIRED_LEAK = LEAK.replace("net cu_out: col.c_out -> out\n", """coal = Chest<infinity, item=coal, rate=5/s> @(14, 2)
net coal_in items coal: coal -> out
net cu_out items copper-plate: col.c_out -> out
lanes coal_in | cu_out
""")


class PairJudge(unittest.TestCase):
    def test_a_pair_is_not_laid_on_a_feed_that_brings_another_item(self):
        flat = elaborate(*_parsed(PAIRED_LEAK), CAT, "t")
        lay, _n = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        self.assertIn("coal_in|cu_out", r.failed)
        self.assertIn("holds iron-plate, which cu_out does not carry", r.failed["coal_in|cu_out"])
        self.assertNotIn("fe_in|cu_in", r.failed)

    def test_a_pair_after_the_nets_that_feed_its_unit(self):
        flat = elaborate(*_parsed(PAIRED_LEAK), CAT, "t")
        lay, _n = expand.expand_factory(flat, CAT)
        js = route.jobs(flat, lay, CAT)
        order = route._feed_order(js, ["coal_in|cu_out", "fe_in|cu_in"])
        self.assertEqual(order, ["fe_in|cu_in", "coal_in|cu_out"])


if __name__ == "__main__":
    unittest.main()
