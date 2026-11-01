"""2.1 m2m (DESIGN-M2M.md, releases 1 and 2): the many-to-many router's baseline (``route --m2m``:
the hub without side-loads, then augmenting runs), the max-flow of a laid net (``fkcore.maxflow``,
the ``MAXFLOW`` line) and the hourglass bench (``tools/hourglass.py``): a column of producers, a
column of consumers, one net between them. 2.1.21: on both lanes, the router picking each
driver's lane; ``route --m2m left`` is version 1, the left lane only."""
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


def side_loads(layout):
    """[(side-loading belt, belt)] of a layout's side-loads (2.1.24: m2m side-loads to fill a lane)."""
    lg = lanes.build(layout, CAT)
    return sorted({(e.src[0], e.dst[0]) for e in lg.edges() if e.via in ("side", "ug_side")})


def into_splitter_sides(layout):
    """[belt key] of the belts that point into a splitter from its side (a dead end)."""
    at = {}
    for e in layout.entities.values():
        for t in fkp.tiles_of(CAT, e):
            at[t] = e
    out = []
    for e in layout.entities.values():
        if e.name != "transport-belt" and e.attrs.get("ug") != "out":
            continue
        d = e.dir // 4 % 4
        t = (int(e.x // 1) + (0, 1, 0, -1)[d], int(e.y // 1) + (-1, 0, 1, 0)[d])
        o = at.get(t)
        if o is not None and o.name == "splitter" and o.dir != e.dir:
            out.append(e.key)
    return out


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

    def test_the_waist_is_a_band_of_belts(self):
        # two lanes a run: the waist is the flow in belts, rounded up
        for name, m in self.rows.items():
            with self.subTest(case=name):
                need = -(-m["demand"] // 15.0)
                self.assertGreaterEqual(m["narrow"], need)
        self.assertEqual(self.rows["16to16"]["narrow"], 2)

    def test_drivers_drop_on_both_lanes(self):
        lg = lanes.build(self.rows["16to16"]["layout"], CAT)
        onto = {e.dst[1] for e in lg.edges() if e.via == "drop"
                and e.src[0].startswith("~plates/") and e.dst[1]}
        self.assertEqual(onto, {"L", "R"})

    def test_side_loads_onto_plain_belts(self):
        # a side-load fills a lane of a plain belt fed from behind (a splitter there would cut it
        # off, and an underground keeps one lane of it): onto no splitter and no underground
        for name, m in self.rows.items():
            ents = m["layout"].entities
            with self.subTest(case=name):
                for _a, b in side_loads(m["layout"]):
                    self.assertEqual(ents[b].name, "transport-belt")
                self.assertEqual(into_splitter_sides(m["layout"]), [])

    def test_under_the_games_rules(self):
        # 2.1.24: what the consumers get as the game splits (fkcore.routed; the lab agrees):
        # every case but 16to16 in full, 16to16 short of its max-flow by one consumer's worth
        for name, m in self.rows.items():
            with self.subTest(case=name):
                want = m["demand"] - (1.5 if name == "16to16" else 0.0)
                self.assertGreaterEqual(m["played"], want - 1e-6, m["line"])
        self.assertIn("by the game's rules", self.rows["16to16"]["line"])

    def test_a_run_comes_first_out_of_its_split(self):
        # a run that leaves a belt by a splitter gets its output priority: the splitter passes on
        # what the run can't take (an even split starves the run, 2.1.24's lab)
        ents = self.rows["16to16"]["layout"].entities.values()
        firsts = [e for e in ents if e.name == "splitter" and "output_priority" in
                  (e.attrs.get("config") or "")]
        self.assertTrue(firsts)

    def test_maxflow_line(self):
        m = self.rows["16to16"]
        line = next(ln for ln in m["lines"] if ln.startswith("MAXFLOW"))
        self.assertIn("22.4 of 22.4/s", line)
        self.assertIn("m2m: ", m["line"])

    def test_table(self):
        text = hourglass.table(list(self.rows.values()))
        self.assertIn("waist", text.splitlines()[0])
        self.assertEqual(len(text.splitlines()), 2 + len(hourglass.CASES))


class BigTest(unittest.TestCase):
    """A higher-throughput case (2.1.23): 48/s, several belts' worth, no run cap in the way."""

    def test_twenty_four_to_twenty_four(self):
        m = hourglass.measure("24to24", CAT)
        self.assertTrue(m["reach"], m["line"])
        self.assertGreaterEqual(m["maxflow"], m["demand"] - 1e-6, m["line"])
        self.assertGreaterEqual(m["narrow"], 4)          # 48/s over 15 a belt, rounded up
        self.assertTrue(side_loads(m["layout"]))       # runs fill the collectors' empty lanes
        self.assertEqual(into_splitter_sides(m["layout"]), [])
        # under the game's rules (2.1.24): 44.5 of 48 (without the runs' priority, 37.4)
        self.assertGreaterEqual(m["played"], 44.0, m["line"])


class LeftTest(unittest.TestCase):
    """``route --m2m left``: version 1, every driver on the left lane, one lane a run."""

    @classmethod
    def setUpClass(cls):
        cls.rows = {name: hourglass.measure(name, CAT, router="m2m-left")
                    for name in hourglass.CASES}

    def test_reach_and_demand(self):
        for name, m in self.rows.items():
            with self.subTest(case=name):
                self.assertTrue(m["reach"], m["line"])
                self.assertGreaterEqual(m["maxflow"], m["demand"] - 1e-6, m["line"])

    def test_the_waist_is_a_band_of_lanes(self):
        # one lane a run: the waist is the flow in lanes, rounded up
        for name, m in self.rows.items():
            with self.subTest(case=name):
                need = -(-m["demand"] // 7.5)
                self.assertGreaterEqual(m["narrow"], need)
        # 3 by the max-flow; 2.1.24's runs under the game's rules widen it by one
        self.assertEqual(self.rows["16to16"]["narrow"], 4)

    def test_drivers_drop_on_the_left_lane(self):
        for name, m in self.rows.items():
            if name == "8to8":
                continue                              # one lane: laid as today
            lg = lanes.build(m["layout"], CAT)
            onto = {e.dst[1] for e in lg.edges() if e.via == "drop"
                    and e.src[0].startswith("~plates/") and e.dst[1]}
            with self.subTest(case=name):
                self.assertEqual(onto, {"L"})


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
        free = maxflow.of_net(flat, r.layout, CAT, "plates", unbounded=True, lanes=True)
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

    def test_lanes_a_belt_filled_from_one_side_carries_one_lane(self):
        ents = [self.ins(0, 1, 0, 12), self.ins(1, 1, 2, 12), self.ins(2, 5, 0, 12),
                self.ins(3, 5, 2, 12)]
        ents += [self.belt(0, 2, 0, 8), self.belt(1, 2, 1, 8), self.belt(2, 2, 2, 8),
                 self.belt(3, 2, 3, 4), self.belt(4, 3, 3, 4), self.belt(5, 4, 3, 0),
                 self.belt(6, 4, 2, 0), self.belt(7, 4, 1, 0), self.belt(8, 4, 0, 0)]
        flat, lay = self.lay(ents)
        f = maxflow.of_net(flat, lay, CAT, "n", lanes=True)
        self.assertAlmostEqual(f.value, 4.0)
        u = maxflow.of_net(flat, lay, CAT, "n", unbounded=True, lanes=True)
        self.assertAlmostEqual(u.lanes, 1.0)           # both drop on one side: one lane
        self.assertTrue(all(":" in k for k in u.cut), u.cut)

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
