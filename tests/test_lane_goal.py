"""PLAN-LANES phases 3 and 4: what a router's own belts carry, by the lane graph (``lanes.reach``),
and a pair routed by the lane goal (``pairs.route_lanes``): a trunk first, then A and B
side-loading its stem wherever the lane graph says the lanes come out right."""
import unittest

from fkcore import expand, lanes, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate
from fkcore.fkp import Entity
from tests.test_lanes_pairs import SMELT

CAT = Catalog.load()
N, E, S, W = 0, 4, 8, 12


def belt(key, x, y, d):
    return Entity(key, "transport-belt", x + 0.5, y + 0.5, d, {})


def carried(ents, seeds, key):
    """{lane: labels} on belt ``key`` from ``seeds`` {belt key: label} (both of its lanes)."""
    lg = lanes.build(ents, CAT)
    got = lanes.reach(lg, [((k, ln), lab) for k, lab in seeds.items() for ln in "LR"])
    return {ln: got.get((key, ln), set()) for ln in "LR"}


class Reach(unittest.TestCase):
    """The trunk heads east along y=5: t0 at x=5, t1, t2. A comes from the north (the trunk's
    left), B from the south (its right)."""

    def test_two_side_loads_make_the_pair(self):
        ents = [belt("t0", 5, 5, E), belt("t1", 6, 5, E), belt("a", 5, 4, S), belt("b", 5, 6, N)]
        self.assertEqual(carried(ents, {"a": "l", "b": "r"}, "t1"), {"L": {"l"}, "R": {"r"}})

    def test_one_side_feed_with_nothing_behind_turns(self):
        """No stub: A alone into the root makes it a turn, A on both lanes (the judge's call)."""
        ents = [belt("t0", 5, 5, E), belt("t1", 6, 5, E), belt("a", 5, 4, S)]
        self.assertEqual(carried(ents, {"a": "l"}, "t1"), {"L": {"l"}, "R": {"l"}})

    def test_an_empty_root_belt_is_the_stub(self):
        """A into the second belt, the empty root behind it: a side-load, A on the left lane."""
        ents = [belt("t0", 5, 5, E), belt("t1", 6, 5, E), belt("t2", 7, 5, E), belt("a", 6, 4, S)]
        self.assertEqual(carried(ents, {"a": "l"}, "t2"), {"L": {"l"}, "R": set()})

    def test_side_loads_apart_on_the_stem(self):
        """A at t1 and B at t2: still A left, B right downstream."""
        ents = [belt("t0", 5, 5, E), belt("t1", 6, 5, E), belt("t2", 7, 5, E),
                belt("t3", 8, 5, E), belt("a", 6, 4, S), belt("b", 7, 6, N)]
        self.assertEqual(carried(ents, {"a": "l", "b": "r"}, "t3"), {"L": {"l"}, "R": {"r"}})


def _route(text):
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay, _n = expand.expand_factory(flat, CAT)
    return route.route_layout(flat, lay, CAT)


class LaneGoal(unittest.TestCase):
    def test_the_smelter_pair_by_the_lane_goal(self):
        r = _route(SMELT)
        self.assertEqual(r.failed, {})
        line = next(x for x in r.lines if "ore_|fuel" in x)
        self.assertIn("trunk", line)
        self.assertIn("(ore_ on the left lane, fuel on the right", line)
        # the judge's lane graph over the whole layout: ore on the left, coal on the right of
        # every trunk belt a smelter's inserter picks from
        lg = lanes.build(list(r.layout.entities.values()), CAT)
        trunk = {e.key for e in r.layout.entities.values()
                 if e.key.startswith("~ore_|fuel/") and e.key.rsplit("/", 1)[1][:1] not in "lr"}
        # A's and B's own belts seed their labels on both lanes
        seeds = [((e.key, ln), e.key.rsplit("/", 1)[1][:1])
                 for e in r.layout.entities.values()
                 if e.key.startswith(("~ore_|fuel/l", "~ore_|fuel/r"))
                 and CAT.kind(e.name) in ("transport-belt", "underground-belt", "splitter")
                 for ln in "LR"]
        self.assertTrue(seeds)
        got = lanes.reach(lg, seeds)
        # the smelters pick from their own input belts, fed by the trunk
        picks = {ed.src for eds in lg.inn.values() for ed in eds
                 if ed.via == "pickup" and ed.src[1] in ("L", "R") and got.get(ed.src)}
        self.assertTrue(picks)
        self.assertTrue(trunk)
        for node in picks:
            self.assertLessEqual(got.get(node, set()), {"l"} if node[1] == "L" else {"r"})

    def test_an_empty_root_is_kept_as_the_stub(self):
        """A wide net whose groups side-load past the root: the root stays, named ``z0``."""
        from tests.test_width2 import furnace_line
        r = _route(furnace_line(False))
        self.assertEqual(r.failed, {})
        line = next(x for x in r.lines if x.split()[1] == "plates:")
        stubs = [k for k in r.layout.entities if k.startswith("~plates/z")]
        self.assertNotIn("stem belt 0", line)       # this layout side-loads past its root
        self.assertEqual(len(stubs), 1)


if __name__ == "__main__":
    unittest.main()
