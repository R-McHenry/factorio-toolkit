"""3.0: route lays each net once, a failed net gets its group try on a budget, and the build
script sets the order (--first) and the nets left to the player (--skip)."""
import unittest
from unittest import mock

from fkcore import expand, fkp, fluid_route, lang, route
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

    def test_a_net_that_failed_on_this_ground_is_not_searched_again(self):
        r, fake = self.run_fake(group_budget=0, first=["y"])
        self.assertEqual(list(r.memo), ["x"])
        again, fake = self.run_fake(group_budget=0, first=["y"], memo=r.memo)
        self.assertEqual(fake.calls, ["y"])                 # x: its last reason stands
        self.assertIn("not searched again", again.failed["x"])
        self.assertIn("route --again x", again.failed["x"])
        self.assertEqual(again.memo, r.memo)                # still remembered
        _r, fake = self.run_fake(group_budget=0, first=["y"], memo=r.memo, again=["x"])
        self.assertEqual(fake.calls, ["y", "x"])
        # other ground: x waits for the end of the pass (where it failed last), then is searched
        other = {"x": dict(r.memo["x"], key="other ground")}
        moved, fake = self.run_fake(group_budget=0, memo=other)
        self.assertEqual(fake.calls, ["y", "x"])
        self.assertNotIn("not searched again", moved.failed["x"])
        self.assertEqual(moved.memo, r.memo)

    def test_retry_failed_is_the_scripts_choice(self):
        # route --retry-failed: changed (the default, above), always, never
        r, _fake = self.run_fake(group_budget=0, first=["y"])
        _a, fake = self.run_fake(group_budget=0, first=["y"], memo=r.memo, retry="always")
        self.assertEqual(fake.calls, ["y", "x"])            # searched though its ground stands
        other = {"x": dict(r.memo["x"], key="other ground")}
        never, fake = self.run_fake(group_budget=0, memo=other, retry="never")
        self.assertEqual(fake.calls, ["y"])                 # not searched though its ground moved
        self.assertIn("--retry-failed never", never.failed["x"])
        self.assertEqual(never.failed["x"].count("not searched again"), 1)
        twice, _fake = self.run_fake(group_budget=0, memo={"x": dict(r.memo["x"],
                                                                    why=never.failed["x"])},
                                     retry="never")
        self.assertEqual(twice.failed["x"].count("not searched again"), 1)   # said once
        _n, fake = self.run_fake(group_budget=0, memo=other, retry="never", again=["x"])
        self.assertIn("x", fake.calls)                      # --again still searches it

    def test_patterns(self):
        self.assertTrue(route._named("mall/fe", ["mall/*"]))
        self.assertFalse(route._named("mall2/fe", ["mall/*"]))
        self.assertTrue(route._named("coal", ["x", "coal"]))


class FluidBudgetTest(unittest.TestCase):
    """3.0: the fluid nets get one pass, and passes in another order only while they fit in
    the build script's budget."""

    def run_fluid(self, budget, pass_s):
        flat, lay = two()
        clock = [0.0]
        calls = []

        class W:
            occ, box = set(), None

            def snapshot(self):              # 3.1.4: the pass keeps the world between tries
                return ({}, {0: set(), 1: set()}, {0: set(), 1: set()})

            def restore(self, snap):
                pass

        def route_net(w, owners, g, flat, cat, net, ends, base, extra, *a):
            calls.append(net)
            clock[0] += pass_s / 2
            if net == "b" and extra:                       # b fails once a is laid
                return None, "a is in the way"
            return [net], "fake"
        with mock.patch.object(fluid_route, "_ends", lambda *a: [("k", "water", "in", None)]), \
                mock.patch.object(fluid_route, "_world", lambda *a: (W(), {}, None)), \
                mock.patch.object(fluid_route, "_route_net", route_net), \
                mock.patch("time.monotonic", lambda: clock[0]):
            added, _how, failed = fluid_route.route(flat, lay, CAT, ["a", "b"],
                                                    box=(0, 0, 30, 14), budget=budget)
        return added, failed, calls

    def test_a_second_pass_that_fits_the_budget(self):
        added, failed, calls = self.run_fluid(budget=3, pass_s=1)
        self.assertEqual(calls, ["a", "b", "b", "a"])
        self.assertEqual((sorted(added), failed), (["a", "b"], {}))

    def test_one_pass_when_another_would_go_past_it(self):
        added, failed, calls = self.run_fluid(budget=3, pass_s=10)
        self.assertEqual(calls, ["a", "b"])
        self.assertIn("not tried again in another order", failed["b"])
        added, failed, calls = self.run_fluid(budget=None, pass_s=10)
        self.assertEqual(calls, ["a", "b", "b", "a"])           # no budget: as before


if __name__ == "__main__":
    unittest.main()
