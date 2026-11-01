"""2.1.26: the 20261030-2352 run's dry builds took 20+ min.

- The nominal rate model swung on its world for all 50000 passes at damping 0.5 (BeltMall2's
  gear -> yellow belt -> fast belt chain), ~5 min and twice a build, and reported a snapshot of the
  swing. A solve that has not settled after ``RESTARTS``' passes starts again with a smaller step.
- Its coal net (a pair: dozens of drills and furnaces) failed near its ends, then flooded the whole
  1554x1246 frame once per end, ~250 s a pass. A search past ``WALK_BUDGET`` stops and says so.
- A build writes each step's time to out/timings.txt.
"""
import os
import time
import unittest

from fkcore import rates, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate_file

CAT = Catalog.load()
HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.join(HERE, "golden", "live-20261101", "world.fk")


class SolverSettlesTest(unittest.TestCase):
    def test_the_live_world_settles_with_a_smaller_step(self):
        cwd = os.getcwd()
        os.chdir(os.path.dirname(LIVE))
        try:
            flat = elaborate_file(LIVE, CAT)
        finally:
            os.chdir(cwd)
        t = time.monotonic()
        model = rates.solve(flat)
        self.assertLess(time.monotonic() - t, 60)
        self.assertLess(model.residual, 1e-9)
        self.assertLess(model.passes, rates.RESTARTS[0][0] + 1000)
        # 2.1.27: it stops swinging at the first windows that show it, not at pass 1000
        self.assertLess(model.passes, 3 * rates.SWING_WINDOW + 400)
        self.assertEqual(model.damping, rates.RESTARTS[0][1])
        text = rates.report(model, "world")
        self.assertIn("damping 0.25: it swung at 0.5", text)
        self.assertNotIn("NOT SETTLED", text)

    def test_a_model_that_settles_keeps_the_first_step(self):
        path = os.path.join(os.path.dirname(HERE), "agent", "docs", "examples", "gears.fk")
        model = rates.solve(elaborate_file(path, CAT))
        self.assertEqual(model.damping, rates.DAMPING)
        self.assertNotIn("damping", rates.report(model).splitlines()[1])


class WalkBudgetTest(unittest.TestCase):
    def test_the_ladder_doubles_up_to_the_frame(self):
        boxes = route._ladder((40, 40, 60, 50), (0, 0, 200, 100))
        self.assertEqual(boxes[0], (30, 35, 70, 55))
        self.assertEqual(boxes[-1], (0, 0, 200, 100))
        for a, b in zip(boxes, boxes[1:]):
            self.assertTrue(b[0] <= a[0] and b[1] <= a[1] and b[2] >= a[2] and b[3] >= a[3])

    def test_a_net_too_big_for_its_frame_stops_at_the_budget(self):
        job = route.NetJob("n", starts=[((40, 40), 0)], goals=[((50, 44), 0)])
        seen = []
        saved_in, saved_budget = route._route_in, route.WALK_BUDGET

        def fake(cat, job, ents, frames, js, box, *a, **k):
            seen.append(box)
            return None, "no route"
        route._route_in = fake
        route.WALK_BUDGET = 2 * 10_000           # 2 ends: a box of 10000 tiles at most
        try:
            got, how = route._route_one(CAT, job, [], frozenset(), {}, (0, 0, 1000, 1000), 1000)
        finally:
            route._route_in, route.WALK_BUDGET = saved_in, saved_budget
        self.assertIsNone(got)
        self.assertNotIn((0, 0, 1000, 1000), seen)
        self.assertTrue(all(route._area(b) <= 10_000 for b in seen), seen)
        self.assertIn("walk budget", how)

    def test_within_the_budget_it_is_near_then_the_frame_as_before(self):
        job = route.NetJob("n", starts=[((40, 40), 0)], goals=[((50, 44), 0)])
        seen = []
        saved = route._route_in

        def fake(cat, job, ents, frames, js, box, *a, **k):
            seen.append(box)
            return None, "no route"
        route._route_in = fake
        try:
            route._route_one(CAT, job, [], frozenset(), {}, (0, 0, 300, 300), 1000)
        finally:
            route._route_in = saved
        self.assertEqual(seen, [route._near_box(job, (0, 0, 300, 300)), (0, 0, 300, 300)])


if __name__ == "__main__":
    unittest.main()
