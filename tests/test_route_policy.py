"""3.0: route lays each net once, a failed net gets its group try on a budget, and the build
script sets the order (--first) and the nets left to the player (--skip)."""
import unittest
from unittest import mock

from fkcore import expand, fkp, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

TWO = """
sx = Chest<requester, item=iron-plate, rate=4> @(2, 4)
dx = Chest<provider, limit=8> @(20, 4)
sy = Chest<requester, item=copper-plate, rate=4> @(2, 8)
dy = Chest<provider, limit=8> @(20, 8)
net x: sx -> dx
net y: sy -> dy
"""


def two():
    f = lang.parse(TWO, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay, _notes = expand.expand_factory(flat, CAT)
    return flat, lay


def belt(net, x, y):
    return fkp.Entity(f"~{net}/b{x}_{y}", "transport-belt", x + 0.5, y + 0.5, 4, {"net": net})


class Fake:
    """A stand-in search: y always lays a belt at x's first end; x fails while any y belt
    stands. Records the order of searches."""

    def __init__(self):
        self.calls = []

    def __call__(self, cat, job, ents, *a, **k):
        self.calls.append(job.net)
        if job.net == "y":
            return [belt("y", 5, 5)], "fake"           # beside x's source chest at 2,4
        if any(e.owner == "~y" for e in ents):
            return None, "y is in the way"
        return [belt("x", 5, 4)], "fake"


class PolicyTest(unittest.TestCase):
    def run_fake(self, **policy):
        flat, lay = two()
        fake = Fake()
        with mock.patch.object(route, "_route_one", fake), \
                mock.patch.object(route, "_route_promoted", lambda *a, **k: None), \
                mock.patch.object(route, "_repair", lambda *a, **k: None), \
                mock.patch.object(route, "_guarded", lambda *a, **k: None):   # its own search
            r = route.route_layout(flat, lay, CAT, bounds=(0, 0, 30, 14), **policy)
        return r, fake

    def test_first_sets_the_order(self):
        _r, fake = self.run_fake(group_budget=0)
        self.assertEqual(fake.calls[:2], ["x", "y"])
        _r, fake = self.run_fake(group_budget=0, first=["y"])
        self.assertEqual(fake.calls[:2], ["y", "x"])

    def test_each_net_once_with_no_budget(self):
        r, fake = self.run_fake(group_budget=0, first=["y"])
        self.assertEqual(fake.calls, ["y", "x"])          # no second pass
        self.assertIn("x", r.failed)
        self.assertEqual(r.passes, 2)                     # the promoting search ran for x

    def test_the_group_try_lays_the_failed_net_first(self):
        r, fake = self.run_fake(first=["y"])
        self.assertEqual(r.failed, {}, r.lines)
        line = next(l for l in r.lines if l.startswith("group     x:"))
        self.assertIn("all routed", line)
        # y, x fails, x's way with y lifted, then the group: x, y
        self.assertEqual(fake.calls, ["y", "x", "x", "x", "y"])

    def test_skip_leaves_a_net_to_the_player(self):
        r, fake = self.run_fake(skip=["y"])
        self.assertNotIn("y", fake.calls)
        self.assertEqual(r.failed, {})
        self.assertTrue(any(l.startswith("manual    y:") for l in r.lines), r.lines)
        self.assertFalse(any(e.owner == "~y" for e in r.layout.entities.values()))

    def test_patterns(self):
        self.assertTrue(route._named("mall/fe", ["mall/*"]))
        self.assertFalse(route._named("mall2/fe", ["mall/*"]))
        self.assertTrue(route._named("coal", ["x", "coal"]))


if __name__ == "__main__":
    unittest.main()
