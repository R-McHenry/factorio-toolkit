"""The V2 lane graph and flow solver (CORE-V2.md "Lane physics" and "Flow").

Small hand-built layouts in .fkp text check each rule as measured in the game
(docs/LAB-LANES-20261020.md); Rory's two benchmarks, read from his ghosts on nauvis
(games/v2-bench), check the solver on real designs: the smelter stack (opposing splitters
side-loading ore and coal onto opposing belts) and the 4-to-4 balancer. Directions follow the
.fkp: N E S W; an inserter faces the side it picks from; both ends of an underground face the flow.
"""
import json
import os
import unittest

from fkcore import fkp, lanes
from fkcore import throughput as tp
from fkcore.catalog import Catalog

CAT = Catalog.load()
INF = float("inf")
BENCH = os.path.join(os.path.dirname(__file__), "..", "games", "v2-bench")
ORE, COAL, PLATE = "iron-ore", "coal", "iron-plate"


def L(rows):
    return fkp.loads("fkp 1 factory t\n" + "\n".join(rows))


def belt_row(prefix, y, x0, x1, d="E", name="transport-belt"):
    return [f"e {prefix}{x} {name} {x}.5,{y}.5 {d} net=a" for x in range(x0, x1)]


def both(rate, item=PLATE):
    return {"L": {item: rate}, "R": {item: rate}}


def at(key, table):
    return {(key, lane): t for lane, t in table.items()}


def got(res, key, item=PLATE, table="delivered"):
    rows = getattr(res, table)
    return sum(rows.get((key, lane), {}).get(item, 0.0) for lane in ("L", "R", ""))


class LaneRulesTest(unittest.TestCase):
    """The edges of the lane graph, one measured rule each."""

    def edges(self, rows, via):
        lg = lanes.build(L(rows), CAT)
        return {(e.src, e.dst) for e in lg.edges() if e.via == via}

    def test_drop_across_fills_the_far_lane(self):
        rows = ["e a/b0 transport-belt 0.5,0.5 E net=a",
                "e a/i0 fast-inserter 0.5,-0.5 N net=a",       # on the belt's left, drops south
                "e a/i1 fast-inserter 1.5,1.5 S net=a",        # a second belt, from its right
                "e a/b1 transport-belt 1.5,0.5 E net=a"]
        drops = self.edges(rows, "drop")
        self.assertIn((("a/i0", ""), ("a/b0", "R")), drops)
        self.assertIn((("a/i1", ""), ("a/b1", "L")), drops)

    def test_drop_in_line_fills_the_right_lane(self):
        rows = ["e a/b0 transport-belt 1.5,0.5 E net=a",
                "e a/i0 fast-inserter 0.5,0.5 W net=a",        # behind it: the belt flows away
                "e a/b1 transport-belt 3.5,0.5 E net=a",
                "e a/i1 fast-inserter 4.5,0.5 E net=a"]        # ahead of it: the belt flows toward
        drops = self.edges(rows, "drop")
        self.assertIn((("a/i0", ""), ("a/b0", "R")), drops)
        self.assertIn((("a/i1", ""), ("a/b1", "R")), drops)

    def test_drop_onto_a_turn_fills_the_inside_lane(self):
        # 2.1.25, measured on 2.0.77: from either outer side of a turn, the inside lane (the m2m
        # 4to16 hub's last producer dropped onto its corner, the lab saw it on the full lane)
        left = ["e a/b0 transport-belt 0.5,-0.5 S net=a",       # south, then east: a left turn
                "e a/b1 transport-belt 0.5,0.5 E net=a",
                "e a/b2 transport-belt 1.5,0.5 E net=a",
                "e a/i0 fast-inserter -0.5,0.5 W net=a",        # behind the turn's way out
                "e a/i1 fast-inserter 0.5,1.5 S net=a"]         # below it
        drops = self.edges(left, "drop")
        self.assertIn((("a/i0", ""), ("a/b1", "L")), drops)
        self.assertIn((("a/i1", ""), ("a/b1", "L")), drops)
        right = ["e a/b0 transport-belt 0.5,-0.5 S net=a",      # south, then west: a right turn
                 "e a/b1 transport-belt 0.5,0.5 W net=a",
                 "e a/b2 transport-belt -0.5,0.5 W net=a",
                 "e a/i0 fast-inserter 1.5,0.5 E net=a",
                 "e a/i1 fast-inserter 0.5,1.5 S net=a"]
        drops = self.edges(right, "drop")
        self.assertIn((("a/i0", ""), ("a/b1", "R")), drops)
        self.assertIn((("a/i1", ""), ("a/b1", "R")), drops)
        # from its inner sides, over the belt coming in or going out: the outside lane (the
        # m2m hub's corner producer, a long-handed inserter over the belt coming in)
        inner = ["e a/b0 transport-belt -0.5,0.5 E net=a",      # east, then south: a right turn
                 "e a/b1 transport-belt 0.5,0.5 S net=a",
                 "e a/b2 transport-belt 0.5,1.5 S net=a",
                 "e a/i0 long-handed-inserter -1.5,0.5 W net=a",
                 "e a/i1 long-handed-inserter 0.5,2.5 S net=a"]
        drops = self.edges(inner, "drop")
        self.assertIn((("a/i0", ""), ("a/b1", "L")), drops)
        self.assertIn((("a/i1", ""), ("a/b1", "L")), drops)

    def test_an_underground_exit_takes_a_drop(self):
        rows = ["e a/u0 underground-belt 0.5,0.5 E net=a ug=in",
                "e a/u1 underground-belt 3.5,0.5 E net=a ug=out",
                "e a/i0 fast-inserter 3.5,-0.5 N net=a"]
        self.assertIn((("a/i0", ""), ("a/u1", "R")), self.edges(rows, "drop"))

    def test_drill_drops_on_its_near_lane(self):
        rows = belt_row("a/b", 3, 0, 4) + ["e d/m0 electric-mining-drill 1.5,1.5 S",
                                           "e d/m1 electric-mining-drill 1.5,5.5 N"]
        mines = self.edges(rows, "mine")
        self.assertIn((("d/m0", ""), ("a/b1", "L")), mines)
        self.assertIn((("d/m1", ""), ("a/b1", "R")), mines)

    def test_side_load_is_two_to_one_upstream_lane_first(self):
        rows = belt_row("a/b", 0, 0, 4) + [f"e s/b{j} transport-belt 2.5,{-j - 0.5} S net=s"
                                            for j in range(2)]
        lg = lanes.build(L(rows), CAT)
        side = {(e.src, e.dst): e.rank for e in lg.edges() if e.via == "side"}
        # the source flows south onto an east belt: both its lanes onto L; its R lane (the west
        # half) enters further upstream, so it goes first (measured: 14 to 2)
        self.assertEqual(side, {(("s/b0", "R"), ("a/b2", "L")): 1,
                                (("s/b0", "L"), ("a/b2", "L")): 2})

    def test_underground_side_load_passes_the_open_side_only(self):
        entrance = ["e a/u0 underground-belt 2.5,0.5 E net=a ug=in",
                    "e a/u1 underground-belt 5.5,0.5 E net=a ug=out"]
        src = [f"e s/b{j} transport-belt 2.5,{-j - 0.5} S net=s" for j in range(2)]
        self.assertEqual(self.edges(entrance + src, "ug_side"), {(("s/b0", "R"), ("a/u0", "L"))})
        exit_ = ["e a/u0 underground-belt -0.5,0.5 E net=a ug=in",
                 "e a/u1 underground-belt 2.5,0.5 E net=a ug=out"]
        self.assertEqual(self.edges(exit_ + src, "ug_side"), {(("s/b0", "L"), ("a/u1", "L"))})

    def test_inserter_rates_as_measured(self):
        self.assertAlmostEqual(lanes.inserter_rate("fast-inserter"), 2.5)
        self.assertAlmostEqual(lanes.inserter_rate("inserter"), 60 / 70)
        self.assertAlmostEqual(lanes.inserter_rate("long-handed-inserter"), 1.2)
        self.assertAlmostEqual(lanes.inserter_rate("burner-inserter"), 60 / 76)
        self.assertAlmostEqual(lanes.inserter_rate("fast-inserter", hand=3), 7.5)
        self.assertAlmostEqual(lanes.inserter_rate("bulk-inserter", bulk_hand=4), 10.0)
        self.assertAlmostEqual(lanes.inserter_rate("stack-inserter"), 12.5)
        self.assertAlmostEqual(lanes.inserter_rate("fast-inserter", hand=3, onto_belt=True),
                               7.5 * 0.75)
        self.assertIsNone(lanes.inserter_rate("modded-inserter"))
        self.assertAlmostEqual(lanes.lane_rate(CAT, "transport-belt"), 7.5)
        self.assertAlmostEqual(lanes.lane_rate(CAT, "turbo-transport-belt"), 30.0)


class SolverTest(unittest.TestCase):
    def test_a_lane_caps_its_source(self):
        lg = lanes.build(L(belt_row("a/b", 0, 0, 5)), CAT)
        r = tp.solve(lg, supply={("a/b0", "L"): {PLATE: 10}},
                     demand={("a/b4", "L"): {PLATE: INF}})
        self.assertAlmostEqual(got(r, "a/b4"), 7.5)
        self.assertAlmostEqual(got(r, "a/b0", table="supplied"), 7.5)
        self.assertTrue(r.binds(("a/b2", "L")))
        self.assertAlmostEqual(r.required_ratio(("a/b2", "L")), 10 / 7.5)
        self.assertTrue(any(l.startswith("BLOCKED a/b0.L") for l in tp.report(r, lg)))

    def test_belt_order_serves_the_first_machines_first(self):
        rows = belt_row("a/b", 0, 0, 8)
        for k, x in enumerate((1, 3, 5)):
            rows += [f"e a/i{k} fast-inserter {x}.5,-0.5 S net=a", f"e c{k}/c0 wooden-chest {x}.5,-1.5"]
        lg = lanes.build(L(rows), CAT)
        r = tp.solve(lg, supply={("a/b0", "L"): {PLATE: 5}},
                     demand={(f"c{k}/c0", ""): {PLATE: 2} for k in range(3)})
        self.assertEqual([round(got(r, f"c{k}/c0"), 6) for k in range(3)], [2.0, 2.0, 1.0])
        self.assertEqual(set(r.starved()), {("c2/c0", "")})

    def test_inserter_rate_binds(self):
        # one fast inserter (2.5/s) feeds a chest that would take 4/s
        rows = belt_row("a/b", 0, 0, 3) + ["e a/i0 fast-inserter 1.5,-0.5 S net=a",
                                           "e c/c0 wooden-chest 1.5,-1.5"]
        lg = lanes.build(L(rows), CAT)
        r = tp.solve(lg, supply={("a/b0", "L"): {PLATE: 7}}, demand={("c/c0", ""): {PLATE: 4}})
        self.assertAlmostEqual(got(r, "c/c0"), 2.5)
        self.assertTrue(r.binds(("a/i0", "")))

    def test_splitter_sends_what_one_side_refuses_to_the_other(self):
        rows = belt_row("a/b", 0, 0, 3) + ["e a/s0 splitter 3.5,1 E net=a"]
        rows += belt_row("a/t", 0, 4, 8) + belt_row("a/u", 1, 4, 8)
        rows += ["e a/i0 fast-inserter 7.5,-0.5 S net=a", "e c/c0 wooden-chest 7.5,-1.5"]
        lg = lanes.build(L(rows), CAT)
        r = tp.solve(lg, supply={("a/b0", "L"): {PLATE: 6}},
                     demand={("c/c0", ""): {PLATE: 1}, ("a/u7", "L"): {PLATE: INF}})
        self.assertAlmostEqual(got(r, "c/c0"), 1.0)
        self.assertAlmostEqual(got(r, "a/u7"), 5.0)

    def test_side_load_squeezes_two_lanes_into_one_upstream_first(self):
        rows = belt_row("a/b", 0, 0, 6) + [f"e s/b{j} transport-belt 2.5,{-j - 0.5} S net=s"
                                            for j in range(4)]
        lg = lanes.build(L(rows), CAT)
        r = tp.solve(lg, supply={("s/b3", "L"): {PLATE: 5}, ("s/b3", "R"): {"copper-plate": 5}},
                     demand=at("a/b5", {"L": {PLATE: INF, "copper-plate": INF},
                                        "R": {PLATE: INF, "copper-plate": INF}}))
        end = r.delivered.get(("a/b5", "L"), {})
        self.assertAlmostEqual(end.get("copper-plate", 0.0), 5.0)     # the upstream lane first
        self.assertAlmostEqual(end.get(PLATE, 0.0), 2.5)
        self.assertNotIn(("a/b5", "R"), r.delivered)

    def test_underground_side_load_blocks_the_closed_side(self):
        rows = ["e a/u0 underground-belt 2.5,0.5 E net=a ug=in",
                "e a/u1 underground-belt 5.5,0.5 E net=a ug=out"] + belt_row("a/b", 0, 6, 9)
        rows += [f"e s/b{j} transport-belt 2.5,{-j - 0.5} S net=s" for j in range(4)]
        lg = lanes.build(L(rows), CAT)
        r = tp.solve(lg, supply={("s/b3", "L"): {PLATE: 5}, ("s/b3", "R"): {"copper-plate": 5}},
                     demand=at("a/b8", {"L": {PLATE: INF, "copper-plate": INF}}))
        self.assertEqual(r.delivered.get(("a/b8", "L")), {"copper-plate": 5.0})
        self.assertEqual(got(r, "s/b3", table="supplied"), 0.0)


def miner_line(tiers):
    """18 drills (0.5 ore/s each) above an east belt, then 29 furnaces below it, fed by fast
    inserters: 9 ore/s made, 9.06 asked, all on the belt's left lane. ``tiers``: {x: belt name}."""
    rows, machines = [], {}
    for k in range(18):
        rows.append(f"e d/m{k} electric-mining-drill {3 * k + 1.5},1.5 S")
        machines[(f"d/m{k}", "")] = tp.Machine({}, {ORE: 0.5})
    start = 3 * 18
    for k in range(29):
        x = start + 2 * k
        rows += [f"e f/i{k} fast-inserter {x}.5,4.5 N net=ore", f"e f/m{k} stone-furnace {x + 1},6"]
        machines[(f"f/m{k}", "")] = tp.Machine({ORE: 0.3125})
    for x in range(0, start + 2 * 29):
        rows.append(f"e a/b{x} {tiers.get(x, 'transport-belt')} {x}.5,3.5 E net=ore")
    return lanes.build(L(rows), CAT), machines


class MinerLineTest(unittest.TestCase):
    """Rory's router case: at most X red belts on a line of miners into smelters. The flow rises
    along the drills, peaks between the last drill and the first furnace, and falls along the
    furnaces: red in the middle carries it, red at the ends does not."""

    def run_line(self, red):
        lg, machines = miner_line({x: "fast-transport-belt" for x in red})
        r = tp.solve(lg, machines=machines)
        return sum(r.delivered.get((f"f/m{k}", ""), {}).get(ORE, 0.0) for k in range(29)), r

    def test_red_in_the_middle(self):
        yellow, r = self.run_line(())
        self.assertAlmostEqual(yellow, 7.5, places=6)
        # over a yellow lane: from the 16th drill's tile to the 5th furnace's
        over = [x for x in range(112) if r.required_ratio((f"a/b{x}", "L")) > 1 + 1e-9]
        self.assertEqual((over[0], over[-1], len(over)), (46, 62, 17))
        middle, _r = self.run_line(over)
        ends, _r = self.run_line(list(range(9)) + list(range(104, 112)))     # 17 red as well
        self.assertAlmostEqual(middle, 9.0, places=6)          # every drill's ore gets through
        self.assertAlmostEqual(ends, 7.5, places=6)


def ghost_entities(name):
    with open(os.path.join(BENCH, name), encoding="utf-8") as fh:
        return json.load(fh)["ghosts"]


class _Ent:
    def __init__(self, key, name, x, y, d, ug=None):
        self.key, self.name, self.x, self.y, self.dir = key, name, x, y, d
        self.attrs = {"ug": ug} if ug else {}


def _ug(g):
    return {"input": "in", "output": "out"}.get(g.get("ug"))


def smelter_stack(units, bands):
    """Rory's unit (x 86..96 of his ghost), tiled ``units`` times westward of its own coal, with
    ``bands`` bands of 2 furnaces per column (the ghost's bottom band, repeated north)."""
    unit = [g for g in ghost_entities("smelter-stack-ghosts.json") if 86 <= g["x"] < 97]
    ents = []
    for u in range(units):
        dx = 11 * u
        for i, g in enumerate(unit):
            ents.append(_Ent(f"u{u}/{g['n']}{i}", g["n"], g["x"] + dx, g["y"], g["d"], _ug(g)))
        for b in range(1, bands):
            dy = -4 * b
            for i, g in enumerate(unit):
                if 108 <= g["y"] < 112 and g["n"] not in ("transport-belt", "underground-belt"):
                    ents.append(_Ent(f"u{u}/b{b}/{g['n']}{i}", g["n"], g["x"] + dx, g["y"] + dy,
                                     g["d"]))
            for y in range(108, 112):
                for x, d in ((86, 0), (91, 8), (96, 0)):
                    ents.append(_Ent(f"u{u}/b{b}/belt{x}_{y}", "transport-belt", x + dx + 0.5,
                                     y + dy + 0.5, d))
    tile = {}
    for e in ents:
        for t in CAT.tiles(e.name, e.x, e.y, e.dir):
            tile[t] = e.key
    lg = lanes.build(ents, CAT)
    supply, demand = {}, {}
    for u in range(units):
        dx = 11 * u
        supply.update(at(tile[(89 + dx, 117)], both(7.5, ORE)))         # a full belt of ore
        demand.update(at(tile[(91 + dx, 117)], both(INF)))              # plates out
    return lg, ents, tile, supply, demand


def stack_machines(ents):
    return {(e.key, ""): tp.Machine({ORE: 0.3125, COAL: 0.0225}, {PLATE: 0.3125})
            for e in ents if e.name == "stone-furnace"}


class SmelterStackTest(unittest.TestCase):
    """Rory's benchmark: at 24 furnaces per column a unit eats a full yellow belt of ore and makes
    a full belt of plates, every ore lane at exactly its capacity."""

    def solve(self, units, bands, coal=7.5, lanes_=("L", "R")):
        lg, ents, tile, supply, demand = smelter_stack(units, bands)
        east = 11 * (units - 1)
        for lane in lanes_:                                             # coal from the east
            supply[(tile[(93 + east, 113)], lane)] = {COAL: coal}
        r = tp.solve(lg, supply=supply, demand=demand, machines=stack_machines(ents))
        plates = [round(got(r, tile[(91 + 11 * u, 117)]), 6) for u in range(units)]
        return r, lg, tile, plates

    def test_the_ghost_reads_as_rory_described_it(self):
        lg, _ents, tile, _s, _d = smelter_stack(2, 1)
        side = [e for e in lg.edges() if e.via == "side"]
        self.assertEqual(len(side), 16)          # 2 units x 2 splitters x 2 belts x both lanes
        self.assertEqual(lg.problems, [])
        # in each unit the west belt gets ore on L and coal on R, the east one coal L, ore R
        for u in (0, 1):
            west, east = tile[(89 + 11 * u, 114)], tile[(90 + 11 * u, 114)]
            into = {(e.dst[0], e.dst[1]) for e in side if e.dst[0] in (west, east)}
            self.assertEqual(into, {(west, "L"), (west, "R"), (east, "L"), (east, "R")})

    def test_24_furnaces_per_column_make_a_full_belt(self):
        r, lg, tile, plates = self.solve(2, 12)
        self.assertEqual(plates, [15.0, 15.0])
        self.assertTrue(all(abs(u - 1) < 1e-9 for u in r.util.values()))
        self.assertEqual(r.starved(), {})
        # the 2-to-1 side-load joints run at exactly their capacity
        west = tile[(89, 114)]
        self.assertAlmostEqual(r.load((west, "L")), 1.0, places=6)
        self.assertAlmostEqual(r.required_ratio((west, "L")), 1.0, places=6)

    def test_26_per_column_still_15(self):
        r, lg, _tile, plates = self.solve(1, 13)
        self.assertEqual(plates, [15.0])
        running = sum(1 for u in r.util.values() if u > 1 - 1e-3)
        self.assertEqual(running, 48)                     # 24 per column, as the lanes allow
        self.assertTrue(any(line.startswith("BINDS") for line in tp.report(r, lg)))

    def test_scarce_coal_splits_down_the_chain(self):
        # 2 coal/s for three units that want 1.08 each: the east unit's splitter keeps half,
        # the next one half of the rest, and the last unit's pass-through is a dead end
        _r, _lg, _tile, plates = self.solve(3, 12, coal=1.0)
        self.assertAlmostEqual(plates[2], 1.0 / 0.0225 * 0.3125, places=3)
        self.assertAlmostEqual(plates[1], 0.5 / 0.0225 * 0.3125, places=3)
        self.assertAlmostEqual(plates[0], 0.5 / 0.0225 * 0.3125, places=3)

    def test_one_coal_inserter_feeds_three_units(self):
        # the lab setup (docs/LAB-LANES-20261020.md): one fast inserter puts 2.5 coal/s on the
        # coal belt's right lane. The east unit takes its 1.08 and the rest is shared by the
        # other two: 0.71 each. Measured, once settled: 9.69, 9.68 and 15.0 plates/s.
        _r, _lg, _tile, plates = self.solve(3, 12, coal=2.5, lanes_=("R",))
        self.assertAlmostEqual(plates[2], 15.0, places=6)
        share = (2.5 - 48 * 0.0225) / 2
        self.assertAlmostEqual(plates[1], share / 0.0225 * 0.3125, places=3)
        self.assertAlmostEqual(plates[0], share / 0.0225 * 0.3125, places=3)


class BalancerTest(unittest.TestCase):
    """Rory's 4-to-4 balancer (three layers of splitters, flowing north): full belts in on some
    inputs, open ends on some outputs."""

    @classmethod
    def setUpClass(cls):
        ghosts = sorted(ghost_entities("balancer-4x4-ghosts.json"), key=lambda g: (g["y"], g["x"]))
        ents = [_Ent(f"g/{g['n']}{i}", g["n"], g["x"], g["y"], g["d"], _ug(g))
                for i, g in enumerate(ghosts)]
        cls.lg = lanes.build(ents, CAT)
        tile = {(int(e.x // 1), int(e.y // 1)): e.key for e in ents}
        cls.ins = [tile[(x, 134)] for x in range(106, 110)]
        cls.outs = [tile[(x, 120)] for x in range(106, 110)]

    def flows(self, fed, taken):
        supply, demand = {}, {}
        for k in fed:
            supply.update(at(self.ins[k], both(7.5)))
        for k in taken:
            demand.update(at(self.outs[k], both(INF)))
        r = tp.solve(self.lg, supply=supply, demand=demand)
        return ([round(got(r, self.ins[k], table="supplied"), 6) for k in range(4)],
                [round(got(r, self.outs[k]), 6) for k in range(4)])

    def test_it_is_throughput_unlimited(self):
        self.assertEqual(self.flows([0, 1, 2, 3], [0, 1, 2, 3]), ([15.0] * 4, [15.0] * 4))
        self.assertEqual(self.flows([0, 1, 2], [0, 1, 2]), ([15, 15, 15, 0], [15, 15, 15, 0]))
        self.assertEqual(self.flows([0, 1, 3], [1, 2, 3]), ([15, 15, 0, 15], [0, 15, 15, 15]))
        self.assertEqual(self.flows([0, 1], [2, 3]), ([15, 15, 0, 0], [0, 0, 15, 15]))

    def test_it_balances(self):
        self.assertEqual(self.flows([0], [0, 1, 2, 3]), ([15, 0, 0, 0], [3.75] * 4))
        self.assertEqual(self.flows([0, 1, 2, 3], [0]), ([3.75] * 4, [15, 0, 0, 0]))
        self.assertEqual(self.flows([0, 1, 2, 3], [0, 3]), ([7.5] * 4, [15, 0, 0, 15]))


if __name__ == "__main__":
    unittest.main()
