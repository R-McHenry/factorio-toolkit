"""2.1 m2m (DESIGN-M2M.md, releases 1 and 2): the many-to-many router's baseline (``route --m2m``:
the hub without side-loads, then augmenting runs), the max-flow of a laid net (``fkcore.maxflow``,
the ``MAXFLOW`` line) and the hourglass bench (``tools/hourglass.py``): a column of producers, a
column of consumers, one net between them."""
import os
import sys
import unittest

from fkcore import expand, fkp, lang, lanes, maxflow, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import hourglass  # noqa: E402

CAT = Catalog.load()


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


class HourglassTest(unittest.TestCase):
    """Every case of the bench: reach, the max-flow against the demand, the waist."""

    @classmethod
    def setUpClass(cls):
        cls.rows = {name: hourglass.measure(name, CAT) for name in hourglass.CASES}

    def test_reach_on_every_case(self):
        for name, m in self.rows.items():
            with self.subTest(case=name):
                self.assertFalse(m["failed"], m["line"])
                self.assertTrue(m["reach"], m["line"])

    def test_maxflow_meets_demand(self):
        for name, m in self.rows.items():
            with self.subTest(case=name):
                self.assertGreaterEqual(m["maxflow"], m["demand"] - 1e-6, m["line"])

    def test_eight_to_eight_has_a_waist_of_one(self):
        m = self.rows["8to8"]
        self.assertEqual(m["waist"], 1)
        self.assertEqual(m["runs"], 0)
        self.assertEqual(m["splitters"], 2)          # one merge, one split: the hub as today

    def test_the_waist_is_a_band_of_lanes(self):
        # one lane a run: the waist is the flow in lanes, rounded up
        for name, m in self.rows.items():
            with self.subTest(case=name):
                need = -(-m["demand"] // 7.5)
                self.assertGreaterEqual(m["narrow"], need)
        self.assertEqual(self.rows["16to16"]["narrow"], 3)

    def test_drivers_drop_on_the_left_lane(self):
        for name, m in self.rows.items():
            if name == "8to8":
                continue                              # one lane: laid as today
            lg = lanes.build(m["layout"], CAT)
            onto = {e.dst[1] for e in lg.edges() if e.via == "drop"
                    and e.src[0].startswith("~plates/") and e.dst[1]}
            with self.subTest(case=name):
                self.assertEqual(onto, {"L"})

    def test_maxflow_line(self):
        m = self.rows["16to16"]
        line = next(ln for ln in m["lines"] if ln.startswith("MAXFLOW"))
        self.assertIn("22.4 of 22.4/s", line)
        self.assertIn("m2m: ", m["line"])

    def test_table(self):
        text = hourglass.table(list(self.rows.values()))
        self.assertIn("waist", text.splitlines()[0])
        self.assertEqual(len(text.splitlines()), 2 + len(hourglass.CASES))


class BalancerTest(unittest.TestCase):
    """The comparison: Rory's balancer (n belts, layers of splitters alternating by one) at the
    waist, fed by a merge tree per producer group and feeding a split tree per consumer group."""

    def test_n_minus_one_layers_reach_for_even_n_only(self):
        for n in range(2, 10):
            full = all(len(v) == n for v in hourglass.balancer_reach(n).values())
            with self.subTest(n=n):
                self.assertEqual(full, n % 2 == 0)
                self.assertEqual(hourglass.balancer_layers(n), n - 1 if n % 2 == 0 else n)
        # n = 3, two layers: the last input never meets the pair (0, 1)
        self.assertEqual(hourglass.balancer_reach(3)[2], {1, 2})

    def test_the_plan(self):
        plan, ins, outs = hourglass.balancer_plan(4, 0, 0)
        self.assertEqual(sum(p["name"] == "splitter" for p in plan), 2 + 1 + 2)
        self.assertEqual((len(ins), len(outs)), (4, 4))
        self.assertEqual(outs[0], (4, 0))

    def test_every_case_through_a_balancer(self):
        for name in hourglass.CASES:
            m = hourglass.measure(name, CAT, router="balancer")
            with self.subTest(case=name):
                self.assertTrue(m["reach"], m["line"])
                self.assertGreaterEqual(m["maxflow"], m["demand"] - 1e-6)


class GateTest(unittest.TestCase):
    """Without --m2m the router is as it was; with it, only many-to-many nets above a lane."""

    def test_without_m2m_nothing_changes(self):
        flat, lay, bounds, blocked, _mid = hourglass.build("uneven", CAT)
        r = route.route_layout(flat, lay, CAT, bounds=bounds)
        self.assertFalse(any(ln.startswith("MAXFLOW") for ln in r.lines))
        self.assertFalse(any("m2m:" in ln for ln in r.lines))
        self.assertFalse(route._M2M)
        # above one lane, the router as it was puts the net on both lanes by a side-load
        lg = lanes.build(r.layout, CAT)
        self.assertTrue(any(e.via == "side" for e in lg.edges()
                            if e.src[0].startswith("~plates/")))

    def test_one_lane_lays_as_today(self):
        flat, lay, bounds, _b, _mid = hourglass.build("8to8", CAT)
        a = route.route_layout(flat, lay, CAT, bounds=bounds)
        b = route.route_layout(flat, lay, CAT, bounds=bounds, m2m=True)
        self.assertEqual(sorted(map(repr, a.layout.entities.values())),
                         sorted(map(repr, b.layout.entities.values())))
        self.assertFalse(any(ln.startswith("MAXFLOW") for ln in b.lines))

    def test_width_is_a_minimum_lane_count(self):
        src = hourglass.source([0.8] * 8, 8).replace("net plates:", "net plates width 4:")
        flat = flat_of(src)
        lay, _notes = expand.expand_factory(flat, CAT)
        box = (-8, -8, 29, 24)
        r = route.route_layout(flat, lay, CAT, bounds=box, m2m=True)
        self.assertEqual(r.failed, {})
        self.assertEqual(r.maxflow, {})
        free = maxflow.of_net(flat, r.layout, CAT, "plates", unbounded=True)
        self.assertGreaterEqual(free.lanes, 4 - 1e-6)
        self.assertFalse(any(ln.startswith("ribbon") for ln in r.lines))
        # without --m2m it is a ribbon, as before
        r = route.route_layout(flat, lay, CAT, bounds=box)
        self.assertTrue(any(ln.startswith("ribbon") for ln in r.lines))


class MaxflowTest(unittest.TestCase):
    """fkcore.maxflow on hand-laid nets."""

    def lay(self, ents):
        flat = flat_of("a = Chest<requester, item=iron-plate, rate=2/s> @(0, 0)\n"
                       "b = Chest<requester, item=iron-plate, rate=2/s> @(0, 2)\n"
                       "c = Chest<provider, rate=2/s> @(6, 0)\n"
                       "d = Chest<provider, rate=2/s> @(6, 2)\n"
                       "net n: a, b -> c, d\n")
        lay, _notes = expand.expand_factory(flat, CAT)
        for e in ents:
            lay.add(e)
        return flat, lay

    @staticmethod
    def belt(k, x, y, d, name="transport-belt"):
        return fkp.Entity(f"~n/b{k}", name, x + 0.5, y + 0.5, d, {"net": "n"})

    @staticmethod
    def ins(k, x, y, d):
        return fkp.Entity(f"~n/i{k}", "fast-inserter", x + 0.5, y + 0.5, d, {"net": "n"})

    def test_one_belt_past_every_machine(self):
        # a belt down x=2 then east along y=3 and up x=4: a and b drop on it, c and d take off it
        ents = [self.ins(0, 1, 0, 12), self.ins(1, 1, 2, 12), self.ins(2, 5, 0, 12),
                self.ins(3, 5, 2, 12)]
        ents += [self.belt(0, 2, 0, 8), self.belt(1, 2, 1, 8), self.belt(2, 2, 2, 8),
                 self.belt(3, 2, 3, 4), self.belt(4, 3, 3, 4), self.belt(5, 4, 3, 0),
                 self.belt(6, 4, 2, 0), self.belt(7, 4, 1, 0), self.belt(8, 4, 0, 0)]
        flat, lay = self.lay(ents)
        f = maxflow.of_net(flat, lay, CAT, "n")
        self.assertAlmostEqual(f.demand, 4.0)
        self.assertAlmostEqual(f.value, 4.0)
        self.assertTrue(f.met)
        u = maxflow.of_net(flat, lay, CAT, "n", unbounded=True)
        self.assertAlmostEqual(u.lanes, 1.0)          # one run: one lane
        self.assertTrue(all(k.startswith("~n/b") for k in u.cut), u.cut)

    def test_short_names_the_cut(self):
        ents = [self.ins(0, 1, 0, 12), self.ins(1, 1, 2, 12), self.ins(2, 5, 0, 12),
                self.ins(3, 5, 2, 12)]
        ents += [self.belt(0, 2, 0, 8), self.belt(1, 2, 1, 8), self.belt(2, 2, 2, 8),
                 self.belt(3, 2, 3, 4), self.belt(4, 3, 3, 4), self.belt(5, 4, 3, 0),
                 self.belt(6, 4, 2, 0), self.belt(7, 4, 1, 0), self.belt(8, 4, 0, 0)]
        flat, lay = self.lay(ents)
        supply, take = maxflow.rates_of(flat, "n")
        supply = {k: 6.0 for k in supply}           # 12/s on one lane: it binds at the run
        take = {k: 6.0 for k in take}
        mine = [e for e in lay.entities.values() if e.owner == "~n"]
        mine += [lay.entities[k] for k in set(supply) | set(take)]
        f = maxflow.solve(mine, CAT, supply, take)
        self.assertAlmostEqual(f.value, 5.0)           # two fast inserters' worth in, 2.5 each
        self.assertFalse(f.met)
        self.assertTrue(f.cut)


if __name__ == "__main__":
    unittest.main()
