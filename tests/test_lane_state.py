"""PLAN-4.0 N1: the lane-state search (``fkcore.lanesearch``) on synthetic fields, every result
confirmed by the lane graph (``fkcore.lanes.reach`` over the carriers laid: the judge is the
verdict), and the Rust leg (``fkroute.lane_astar``) against the Python one."""
import os
import random
import unittest
from unittest import mock

from fkcore import connect, lanephys, lanes, lanesearch as ls, steiner
from fkcore.catalog import Catalog
from fkcore.fkp import Entity
from fkcore.steiner import Grid

CAT = Catalog.load()
N, E, S, W = 0, 1, 2, 3
A, B, F = 1, 2, ls.FOREIGN
LABEL = {A: "a", B: "b", F: "f"}
_UG = {"input": "in", "output": "out"}


def _ents(net, plan, count):
    """steiner's plan entities as keyed fkp entities (route._carriers' keys)."""
    out = []
    for p in plan:
        letter = {"transport-belt": "b", "underground-belt": "u", "splitter": "s"}.get(p["name"], "i")
        key = f"~{net}/{letter}{count.get(letter, 0)}"
        count[letter] = count.get(letter, 0) + 1
        attrs = {"net": net}
        if p.get("belt_to_ground_type"):
            attrs["ug"] = _UG[p["belt_to_ground_type"]]
        out.append(Entity(key, p["name"], p["x"], p["y"], int(p["direction"]), attrs))
    return out


def judge(res, job, hosts=(), machines=()):
    """{tile: {"L": labels, "R": labels}} the lane graph gives every carrier laid or standing,
    from the drivers' belt ends (both lanes, as declared), the drop inserters and the hosts'
    labelled lanes; ``machines`` [(rect, name)] stand for the sources and consumers."""
    ents, seeds, count = [], [], {}
    for me, tree in res.trees.items():
        net = job.nets[me - 1]
        mine = _ents(net, tree.entities(net=net), count)
        ents += mine
        for e in mine:
            if CAT.kind(e.name) == "inserter" and "->" in str(e.attrs.get("net", "")) or \
                    e.name in ("inserter", "long-handed-inserter") and e.key.split("/")[-1][0] == "i":
                pass
        for s, (init, how) in tree.roots.items():
            if how[0] == "start":
                key = f"drv/{net}{len(seeds)}"
                h = s[2]
                ents.append(Entity(key, "transport-belt", s[0] - steiner.DX[h] + 0.5,
                                   s[1] - steiner.DY[h] + 0.5, h * 4, {"net": net}))
                for ln, v in zip("LR", init):
                    if v:
                        seeds.append(((key, ln), LABEL[v]))
        for e in mine:
            if CAT.kind(e.name) == "inserter":
                link = tree_link(tree, e)
                if link == "drop":
                    seeds.append(((e.key, ""), LABEL[me]))
    for i, (t, h, kind, lanes_) in enumerate(hosts):
        key = f"host/{i}"
        attrs = {}
        name = "transport-belt"
        if kind in ("ug_in", "ug_out"):
            name, attrs["ug"] = "underground-belt", kind[3:]
        ents.append(Entity(key, name, t[0] + 0.5, t[1] + 0.5, h * 4, attrs))
        for ln, v in zip("LR", lanes_):
            if v:
                seeds.append(((key, ln), LABEL[v]))
    for i, (rect, name) in enumerate(machines):
        x0, y0, x1, y1 = rect
        ents.append(Entity(f"m/{i}", name, (x0 + x1) / 2, (y0 + y1) / 2, 0, {}))
    lg = lanes.build(ents, CAT)
    got = lanes.reach(lg, seeds)
    g = lg.graph
    out = {}
    for t, key in g.at.items():
        if g.nodes[key].kind in ("transport-belt", "underground-belt", "splitter"):
            out[t] = {ln: set(got.get((key, ln), ())) for ln in "LR"}
    return out, lg


def tree_link(tree, e):
    q = (int(e.x // 1), int(e.y // 1))
    if any(d[0] == q for d in tree.drops):
        return "drop"
    return "tap"


def labels(lanes_):
    return {ln: ({LABEL[v]} if v else set()) for ln, v in zip("LR", lanes_)}


def final(res):
    """{tile: (L, R)} what the job leaves on every carrier: each tree's own belts, then what
    rides them (a rider's state holds the host's lanes and its own)."""
    out = {}
    for me in res.order:
        tree = res.trees[me]
        for s in tree.states():
            out[(s[0], s[1])] = (tree.lanes[s], me, s)
    return out


class JudgeMixin:
    def agree(self, res, job, hosts=(), machines=()):
        """The judge's labels equal the search's on every carrier laid or ridden."""
        got, _lg = judge(res, job, hosts, machines)
        for t, (lanes_, me, s) in final(res).items():
            self.assertIn(t, got, (me, s))
            self.assertEqual(got[t], labels(lanes_), (job.nets[me - 1], s, lanes_))
        return got


def grid(w=20, h=16, occ=()):
    occ = set(occ)
    occ |= {(x, y) for x in range(-1, w + 1) for y in (-1, h)}
    occ |= {(x, y) for x in (-1, w) for y in range(-1, h + 1)}
    return Grid(occ, (), {0: set(), 1: set()})


class PairTest(unittest.TestCase, JudgeMixin):
    def test_two_side_loads_onto_an_empty_stub(self):
        """A's belt end (both lanes) and B's: the consumer wants A on L and B on R. Today's join
        comes out of the search: A side-loads an empty stub's belt, B side-loads the same tile
        from the other side (or rides A's belt), and the judge agrees."""
        job = ls.LaneJob(["a", "b"], starts={A: [((0, 5), E, (A, A))], B: [((0, 9), E, (B, B))]},
                         goals=[ls.Fixed("c", (12, 7), E, (A, B))])
        res = ls.route(grid(), job)
        self.assertEqual(res.problems, [])
        ta, tb = res.trees[A], res.trees[B]
        stubs = [s for s, (init, how) in ta.roots.items() if how[0] == "stub"]
        self.assertEqual(len(stubs), 1)
        self.assertEqual(ta.lanes[stubs[0]], (0, 0))
        join = ta.succ[stubs[0]][1]
        self.assertEqual(ta.lanes[join], (A, 0))
        self.assertIn(("side", join), ta.succ.values())
        end = next(s for s, i in tb.sink_at.items())
        self.assertEqual(tb.lanes[end], (A, B))
        self.assertTrue(tb.rides)
        got = self.agree(res, job)
        self.assertEqual(got[(12, 7)], {"L": {"a"}, "R": {"b"}})

    def test_a_side_loads_bs_belt_mid_way(self):
        """B's belt carries B on one lane already (a port's declaration); A joins it mid-way and
        rides to the consumer: no stub, one side-load."""
        job = ls.LaneJob(["a", "b"], starts={A: [((0, 2), E, (A, A))], B: [((0, 9), E, (0, B))]},
                         goals=[ls.Fixed("c", (16, 9), E, (A, B))])
        res = ls.route(grid(), job, orders=[(B, A)])
        self.assertEqual(res.problems, [])
        ta, tb = res.trees[A], res.trees[B]
        self.assertFalse([s for s, (i, how) in ta.roots.items() if how[0] == "stub"])
        self.assertEqual(sum(1 for mv in ta.succ.values() if mv[0] == "enter"), 1)
        self.assertGreater(len(ta.rides), 3)
        self.assertEqual(tb.lanes[next(iter(tb.sink_at))], (0, B))
        got = self.agree(res, job)
        self.assertEqual(got[(16, 9)], {"L": {"a"}, "R": {"b"}})
        self.assertEqual(res.shared(), [(A, ta.shared())])

    def test_cheaper_of_both_orders(self):
        """Routed in both orders, the cheaper is kept."""
        job = ls.LaneJob(["a", "b"], starts={A: [((0, 5), E, (A, A))], B: [((0, 9), E, (B, B))]},
                         goals=[ls.Fixed("c", (12, 7), E, (A, B))])
        res = ls.route(grid(), job)
        one = ls.route(grid(), job, orders=[res.order])
        other = ls.route(grid(), job, orders=[res.order[::-1]])
        self.assertEqual((res.problems, res.cost), ([], one.cost))
        self.assertEqual(other.problems, [])
        self.assertLessEqual(res.cost, other.cost)


class HostTest(unittest.TestCase, JudgeMixin):
    def hosts(self, y=5, x0=4, x1=16, lanes_=(F, 0)):
        return [((x, y), E, "belt", lanes_) for x in range(x0, x1)]

    def test_a_ride_on_a_hosts_free_lane(self):
        """A standing belt carries another design's item on its left lane; the net side-loads it
        from the right, rides its free lane and reaches a consumer at its end."""
        hosts = self.hosts()
        g = grid(occ={t for t, *_r in hosts})
        job = ls.LaneJob(["a"], starts={A: [((2, 12), N, (A, A))]},
                         goals=[ls.Fixed("c", (15, 5), E, (ls.ANY, A))])
        res = ls.route(g, job, hosts=hosts)
        self.assertEqual(res.problems, [])
        t = res.trees[A]
        end = next(iter(t.sink_at))
        self.assertIn(end, t.rides)
        self.assertEqual(t.lanes[end], (F, A))
        self.assertGreaterEqual(len(t.rides), 2)
        self.assertEqual([mv[0] for mv in t.succ.values()].count("enter"), 1)
        got = self.agree(res, job, hosts)
        self.assertEqual(got[(15, 5)], {"L": {"f"}, "R": {"a"}})
        self.assertEqual(res.shared(), [(A, t.shared())])

    def test_a_host_whose_lane_is_taken_is_not_entered(self):
        """Both lanes held: no ride, the net lays its own belt to a consumer of its own."""
        hosts = self.hosts(lanes_=(F, F))
        g = grid(occ={t for t, *_r in hosts} | {(x, 6) for x in range(4, 16)})
        job = ls.LaneJob(["a"], starts={A: [((2, 12), N, (A, A))]},
                         goals=[ls.Fixed("c", (18, 2), E, (A, ls.ANY))])
        res = ls.route(g, job, hosts=hosts)
        self.assertEqual(res.problems, [])
        self.assertFalse(res.trees[A].rides)
        self.agree(res, job, hosts)

    def test_an_underground_side_loaded_from_the_closed_side_loses_the_lane(self):
        """A host's underground entrance heading south, entered from the west: only the lane on
        its open (north) side goes through, onto the near lane. The net on its left lane gets
        through; the net on its right lane alone loses everything, so the goal is not met (in a
        one-tile corridor: given room, the search moves the items to the open lane by a stub
        side-load first, which is right too)."""
        hosts = [((8, 4), S, "ug_in", (0, 0)), ((8, 7), S, "ug_out", (0, 0)),
                 ((8, 8), S, "belt", (0, 0)), ((8, 9), S, "belt", (0, 0))]
        wall = {(x, y) for x in range(0, 20) for y in range(3, 11) if x != 7 and x != 8} \
            | {(7, y) for y in range(5, 11)} | {(8, 3), (8, 10)} | {(8, 5), (8, 6)} \
            | {(6, y) for y in range(0, 5)} | {(8, y) for y in range(0, 3)}
        g = grid(occ=wall | {t for t, *_r in hosts})
        for start, ok in (((A, 0), True), ((0, A), False)):
            job = ls.LaneJob(["a"], starts={A: [((7, 0), S, start)]},
                             goals=[ls.Fixed("c", (8, 9), S, (ls.ANY, A))])
            res = ls.route(g, job, hosts=hosts, limit=5000)
            with self.subTest(start=start):
                if ok:
                    self.assertEqual(res.problems, [])
                    t = res.trees[A]
                    end = next(iter(t.sink_at))
                    self.assertEqual(t.lanes[end], (0, A))      # onto the near (right) lane
                    got = self.agree(res, job, hosts)
                    self.assertEqual(got[(8, 9)], {"L": set(), "R": {"a"}})
                else:
                    self.assertTrue(res.problems)
                    self.assertFalse(res.trees[A].sink_at)


class DropTest(unittest.TestCase, JudgeMixin):
    def test_a_drop_onto_a_turn_takes_the_turns_lane(self):
        """A on its right lane turns left at (4, 5); the consumer wants both lanes. The only
        inserter that fits drops onto the turn from its outer side, which fills the inside lane
        (turn_drop_lane), not the lane a straight belt would take; the judge agrees."""
        occ = {(x, 5) for x in range(5, 20)} | {(x, 4) for x in range(0, 20) if x != 4} \
            | {(x, 6) for x in range(0, 20) if x != 4} | {(x, 7) for x in range(0, 20) if x != 4} \
            | {(3, 1), (5, 1), (3, 2), (5, 2), (3, 3), (5, 3)}
        g = grid(occ=occ)
        job = ls.LaneJob(["a"], starts={A: [((0, 5), E, (0, A))]}, sources={A: [("box", (4, 7, 5, 8))]},
                         goals=[ls.Fixed("c", (4, 1), N, (A, A))])
        res = ls.route(g, job)
        self.assertEqual(res.problems, [])
        t = res.trees[A]
        self.assertEqual(len(t.drops), 1)
        q, _name, _g, key, tile = t.drops[0]
        self.assertEqual((q, tile, key), ((4, 6), (4, 5), "box"))
        turn = next(s for s in t.own() if (s[0], s[1]) == (4, 5))
        self.assertEqual(t.out_heading(turn), N)
        self.assertTrue(t.is_turn(turn, t.preds()))
        self.assertEqual(t.lanes[turn], (A, A))
        self.assertEqual(lanephys.turn_drop_lane(E * 4, N * 4, S * 4), "L")
        self.assertEqual(lanephys.drop_lane(N * 4, N * 4), "R")       # what a straight belt took
        got = self.agree(res, job, machines=[((4, 7, 5, 8), "iron-chest")])
        self.assertEqual(got[(4, 1)], {"L": {"a"}, "R": {"a"}})

    def test_a_machine_driver_starts_the_net_by_a_drop(self):
        """A chest drives the net: an inserter onto a new belt, the lane the table names."""
        g = grid()
        job = ls.LaneJob(["a"], sources={A: [("box", (2, 7, 3, 8))]},
                         goals=[ls.Fixed("c", (12, 7), E, (A, ls.ANY))])
        res = ls.route(g, job)
        self.assertEqual(res.problems, [])
        t = res.trees[A]
        self.assertEqual(len(t.drops), 1)
        root = next(s for s, (init, how) in t.roots.items() if how[0] == "drop")
        q = t.roots[root][1][1]
        lane = lanephys.drop_lane(ls._towards(q, root) * 4, t.out_heading(root) * 4)
        self.assertEqual(t.lanes[root], (A, 0) if lane == "L" else (0, A))
        self.assertEqual(t.out_heading(root), root[2])          # a drop root never turns
        self.agree(res, job, machines=[((2, 7, 3, 8), "iron-chest")])


class TapTest(unittest.TestCase, JudgeMixin):
    def test_a_tap_wants_the_item_on_some_lane(self):
        g = grid(occ={(x, y) for x in range(10, 13) for y in range(6, 9)})
        job = ls.LaneJob(["a"], starts={A: [((0, 7), E, (0, A))]},
                         goals=[ls.Tap("m", (10, 6, 13, 9), {A})])
        res = ls.route(g, job)
        self.assertEqual(res.problems, [])
        t = res.trees[A]
        self.assertEqual(len(t.taps), 1)
        end = next(iter(t.sink_at))
        self.assertIn(A, t.lanes[end])
        self.agree(res, job, machines=[((10, 6, 13, 9), "assembling-machine-1")])


class TableTest(unittest.TestCase):
    def test_the_table_as_data_is_the_table(self):
        """lanephys.table(): every row agrees with the function it enumerates."""
        t = lanephys.table()
        li = {"L": 0, "R": 1}
        for via, s, d, ug, edges, blocked in t["moves"]:
            e, b = lanephys.moves(lanephys.VIAS[via], s * 4, d * 4, "in" if ug == 0 else "out")
            self.assertEqual(edges, tuple((li[a], li[c]) for a, c, _r in e))
            self.assertEqual(blocked, -1 if b is None else li[b])
        for a, b, lane in t["drop"]:
            self.assertEqual(lane, li[lanephys.drop_lane(a * 4, b * 4)])
        for a, b, lane in t["mine"]:
            self.assertEqual(lane, li[lanephys.mine_lane(a * 4, b * 4)])
        for a, b, side, lane in t["turn_drop"]:
            self.assertEqual(lane, li[lanephys.turn_drop_lane(a * 4, b * 4, side * 4)])
        self.assertEqual(len(t["turn_drop"]), 32)

    def test_entry_is_what_fed_uses(self):
        """``entry`` classifies a feed as ``fed`` does: one side with nothing behind turns."""
        self.assertEqual(lanephys.entry("belt", 0, 4, [(4,)]), "turn")
        self.assertEqual(lanephys.entry("belt", 0, 4, [(4,), (0,)]), "side")
        self.assertEqual(lanephys.entry("belt", 0, 4, [(4,), (12,)]), "side")
        self.assertEqual(lanephys.entry("ug_in", 0, 4, [(4,)]), "ug_side")
        self.assertIsNone(lanephys.entry("ug_out", 0, 0, [(0,)]))
        self.assertIsNone(lanephys.entry("belt", 0, 8, [(8,)]))
        self.assertIsNone(lanephys.entry("splitter", 0, 4, [(4,)]))


def _field(seed):
    """A random field: obstacles, one or two nets from belt ends or chests, one or two Fixed
    goals stated in lanes, sometimes a standing host belt with a foreign passenger."""
    rnd = random.Random(seed)
    w, h = 22, 16
    occ = {(rnd.randrange(w), rnd.randrange(h)) for _ in range(rnd.randrange(20, 70))}
    hosts, machines = [], []
    if rnd.random() < 0.4:
        y, x0 = rnd.randrange(2, h - 2), rnd.randrange(0, 6)
        x1 = min(w - 1, x0 + rnd.randrange(6, 14))
        lanes_ = rnd.choice([(F, 0), (0, F), (0, 0)])
        hosts = [((x, y), E, "belt", lanes_) for x in range(x0, x1)]
        occ |= {t for t, *_r in hosts}
    two = rnd.random() < 0.6
    ids = [A, B] if two else [A]
    starts, sources = {}, {}
    used = {t for t, *_r in hosts}
    for me in ids:
        if rnd.random() < 0.3:
            x, y = rnd.randrange(1, 5), rnd.randrange(1, h - 1)
            if (x, y) in used:
                x, y = 1, 0
            rect = (x, y, x + 1, y + 1)
            occ.add((x, y))
            used.add((x, y))
            sources[me] = [(f"box{me}", rect)]
            machines.append((rect, "iron-chest"))
        else:
            y = rnd.randrange(0, h)
            lanes_ = rnd.choice([(me, me), (me, 0), (0, me)])
            starts[me] = [((0, y), E, lanes_)]
            occ.discard((0, y))
            occ.add((-1, y))                     # the driver's belt behind the end
            used.add((0, y))
        if rnd.random() < 0.3:
            y = rnd.randrange(0, h)
            if (0, y) not in used:
                starts.setdefault(me, []).append(((0, y), E, (me, me)))
                occ.discard((0, y))
                occ.add((-1, y))
                used.add((0, y))
    goals = []
    for _ in range(rnd.randrange(1, 3)):
        t = (rnd.randrange(12, w), rnd.randrange(h))
        if t in used:
            continue
        used.add(t)
        occ.discard(t)
        if two:
            need = rnd.choice([(A, B), (A, B), (A, 0), (0, B), (A, ls.ANY)])
        else:
            need = rnd.choice([(A, A), (A, 0), (0, A), (A, ls.ANY), (ls.ANY, A)])
        goals.append(ls.Fixed(f"c{len(goals)}", t, rnd.randrange(4), need))
    g = grid(w, h, occ)
    job = ls.LaneJob(["a", "b"] if two else ["a"], starts, sources, goals)
    return g, job, hosts, machines


class RandomFieldsTest(unittest.TestCase, JudgeMixin):
    def test_the_search_and_the_judge_agree(self):
        """Every lane the search predicts on every carrier it lays or rides is what the lane
        graph gives it; every goal met holds by the judge's labels too."""
        routed = met = 0
        for seed in range(80):
            g, job, hosts, machines = _field(seed)
            with mock.patch.dict(os.environ, {"FK_NATIVE": "0"}):
                res = ls.route(g, job, hosts=hosts, limit=8000)
            with self.subTest(seed=seed):
                got = self.agree(res, job, hosts, machines)
                if res.problems:
                    continue
                for me, tree in res.trees.items():
                    for s, i in tree.sink_at.items():
                        goal = job.goals[i]
                        have = tuple(next(iter(got[(s[0], s[1])][ln]), None) for ln in "LR")
                        back = {"a": A, "b": B, "f": F, None: 0}
                        self.assertTrue(ls.lanes_ok(goal.need, back[have[0]], back[have[1]], me),
                                        (seed, me, s, goal.need, have))
                        met += 1
                routed += 1
        self.assertGreater(routed, 30)
        self.assertGreater(met, 60)


@unittest.skipUnless(steiner._native is not None and hasattr(steiner._native, "lane_astar"),
                     "fkroute.lane_astar not installed")
class NativeParityTest(unittest.TestCase):
    def test_random_fields(self):
        """The kernel's leg gives the Python leg's path on every field, so the trees agree."""
        for seed in range(120):
            g, job, hosts, _m = _field(seed)
            with mock.patch.dict(os.environ, {"FK_NATIVE": "1"}):
                a = ls.route(g, job, hosts=hosts, limit=8000)
            with mock.patch.dict(os.environ, {"FK_NATIVE": "0"}):
                b = ls.route(g, job, hosts=hosts, limit=8000)
            with self.subTest(seed=seed):
                self.assertEqual(a.key(), b.key())
                self.assertEqual((a.cost, a.problems, a.log), (b.cost, b.problems, b.log))

    def test_check_mode_runs_both_and_agrees(self):
        g, job, hosts, _m = _field(3)
        with mock.patch.dict(os.environ, {"FK_NATIVE": "check"}):
            res = ls.route(g, job, hosts=hosts, limit=8000)
        self.assertIsNotNone(res)

    def test_check_mode_raises_on_a_difference(self):
        g, job, hosts, _m = _field(1)
        real = ls._leg_native

        def off(sp, starts, targets, limit):
            got = real(sp, starts, targets, limit)
            return None if got and got is not steiner._UNSUPPORTED else got
        with mock.patch.object(ls, "_leg_native", off):
            with mock.patch.dict(os.environ, {"FK_NATIVE": "check"}):
                with self.assertRaises(AssertionError):
                    ls.route(g, job, hosts=hosts, limit=8000)

    def test_the_leg_runs_native(self):
        g, job, hosts, _m = _field(1)
        with mock.patch.object(ls, "_leg_py", side_effect=AssertionError("python leg ran")):
            with mock.patch.dict(os.environ, {"FK_NATIVE": "1"}):
                ls.route(g, job, hosts=hosts, limit=8000)


if __name__ == "__main__":
    unittest.main()
