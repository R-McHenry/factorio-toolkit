"""fkroute (native/fkroute, Rust) against steiner's Python search: the same trees, call for call.

Skipped when fkroute is not installed: fkcore stays stdlib only and runs the Python search.
"""
import os
import random
import unittest
from unittest import mock

from fkcore import arms, lanephys, steiner
from fkcore.steiner import DropSink, FixedSink, Grid, TapSink


def _case(seed):
    """A random field: obstacles, a foreign tunnel, a root and 1-4 sinks (fixed and tap)."""
    rnd = random.Random(seed)
    w, h = 24, 18
    occ = {(rnd.randrange(w), rnd.randrange(h)) for _ in range(rnd.randrange(40, 120))}
    spans = {0: set(), 1: set()}
    if rnd.random() < 0.5:                       # a foreign underground on a random line
        y = rnd.randrange(h)
        x = rnd.randrange(w - 5)
        spans[1] |= {(x + j, y) for j in range(5)}
    root = (0, rnd.randrange(h), 1, 0)
    occ.discard(root[:2])
    sinks, used = [], {root[:2]}
    for i in range(rnd.randrange(1, 5)):
        if rnd.random() < 0.3:
            x0, y0 = rnd.randrange(4, w - 4), rnd.randrange(2, h - 4)
            rect = (x0, y0, x0 + 3, y0 + 3)
            occ |= {(x, y) for x in range(x0, x0 + 3) for y in range(y0, y0 + 3)}
            sinks.append(TapSink(f"t{i}", rect, 1))
        else:
            t = (rnd.randrange(6, w), rnd.randrange(h))
            if t in used:
                continue
            used.add(t)
            occ.discard(t)
            sinks.append(FixedSink(f"s{i}", t, rnd.randrange(4)))
    return Grid(occ, (), spans), root, sinks


def _run(mode, grid, root, sinks, order=None):
    with mock.patch.dict(os.environ, {"FK_NATIVE": mode}):
        out = steiner.grow(grid, root, sinks, limit=20000, order=order)
    t = out["tree"]
    return (list(t.succ.items()), list(t.sink_at.items()), t.taps, sorted(t.reserved),
            t.sink_terminal, out["log"], out["cost"], out["counts"], out["problems"])


def _reversed_case(seed):
    """_case laid reversed (a collector): taps drop onto the belt, merges keep their spare
    outputs clear of the belts that stand; taps of k 1-2 with either inserter."""
    grid, root, sinks = _case(seed)
    rnd = random.Random(seed + 7)
    grid.drop_taps = True
    grid.keep_clear = {(rnd.randrange(24), rnd.randrange(18)) for _ in range(15)}
    for s in sinks:
        if isinstance(s, TapSink):
            s.k = rnd.randrange(1, 3)
            if rnd.random() < 0.3:
                s.inserters = ("long-handed-inserter", "inserter")
    return grid, root, sinks


def _taps_case(seed):
    """_case with 3.0's taps: k 1-3, the force's arms (range 1-2) on some, a long-handed hand
    first on some, and a drill's drop tile for a sink or two (PLAN-4.0 K2)."""
    grid, root, sinks = _case(seed)
    rnd = random.Random(seed + 31)
    for i, s in enumerate(sinks):
        if isinstance(s, TapSink):
            s.k = rnd.randrange(1, 4)
            if rnd.random() < 0.5:
                s.arms = arms.Arms(rnd.randrange(1, 3))
            if rnd.random() < 0.3:
                s.inserters = ("long-handed-inserter", "inserter")
        elif rnd.random() < 0.3:
            sinks[i] = DropSink(f"d{i}", s.tile)
    if rnd.random() < 0.5:
        grid.drop_taps = True
        grid.keep_clear = {(rnd.randrange(24), rnd.randrange(18)) for _ in range(15)}
    return grid, root, sinks


@unittest.skipUnless(steiner._native is not None, "fkroute not installed")
class NativeParity(unittest.TestCase):
    def test_random_fields(self):
        """200 random fields: the native grow gives the Python tree, log and all."""
        for seed in range(200):
            grid, root, sinks = _case(seed)
            if not sinks:
                continue
            with self.subTest(seed=seed):
                self.assertEqual(_run("1", grid, root, sinks), _run("0", grid, root, sinks))

    def test_grow_runs_native(self):
        grid, root, sinks = _case(1)
        with mock.patch.object(steiner, "_grow_py", side_effect=AssertionError("python grow ran")):
            with mock.patch.dict(os.environ, {"FK_NATIVE": "1"}):
                steiner.grow(grid, root, sinks, limit=20000)

    def test_reversed_and_ordered(self):
        """Laid reversed (drop_taps, keep_clear), k > 1, long-handed first, a fixed order."""
        for seed in range(150):
            grid, root, sinks = _reversed_case(seed)
            if not sinks:
                continue
            order = list(range(len(sinks)))[::-1] if seed % 3 == 0 else None
            with self.subTest(seed=seed):
                self.assertEqual(_run("1", grid, root, sinks, order),
                                 _run("0", grid, root, sinks, order))

    def test_taps_30(self):
        """PLAN-4.0 K2: k > 1 taps (counted in the search state), the force's arms, a long hand
        first, DropSink, forward and laid reversed: the same trees both ways."""
        kinds = {"k>1": 0, "arms": 0, "drop": 0, "armtap": 0}
        for seed in range(200):
            grid, root, sinks = _taps_case(seed)
            if not sinks:
                continue
            with self.subTest(seed=seed):
                a = _run("1", grid, root, sinks)
                self.assertEqual(a, _run("0", grid, root, sinks))
                kinds["k>1"] += any(isinstance(s, TapSink) and s.k > 1 for s in sinks)
                kinds["arms"] += any(isinstance(s, TapSink) and s.arms for s in sinks)
                kinds["drop"] += any(isinstance(s, DropSink) for s in sinks)
                kinds["armtap"] += any(t[4] is not None for t in a[2])
        for k, n in kinds.items():
            self.assertGreater(n, 5, k)

    def test_taps_30_run_native(self):
        """A forward tree with k > 1, arms and a drop sink grows in the kernel, no Python grow
        and no A* callback."""
        grid, root, sinks = _case(2)
        sinks = [TapSink("m", (12, 6, 15, 9), 2, ("inserter",), arms=arms.Arms(2)), DropSink("d", (20, 3))]
        grid.occ |= {(x, y) for x in range(12, 15) for y in range(6, 9)}
        grid.occ.discard((20, 3))
        with mock.patch.object(steiner, "_grow_py", side_effect=AssertionError("python grow ran")), \
                mock.patch.object(steiner, "_astar_py", side_effect=AssertionError("python astar ran")):
            with mock.patch.dict(os.environ, {"FK_NATIVE": "1"}):
                out = steiner.grow(grid, root, sinks, limit=20000)
        self.assertEqual(out["problems"], [], out["log"])
        self.assertEqual(len(out["tree"].taps), 2)

    def test_soft_ground(self):
        """Negotiated ground: belts pay to step on soft tiles, splitters and taps keep off them;
        the same trees both ways, and a soft tile costs what it says."""
        crossed = 0
        for seed in range(150):
            grid, root, sinks = (_reversed_case if seed % 2 else _case)(seed)
            if not sinks:
                continue
            rnd = random.Random(seed + 99)
            soft = {(rnd.randrange(24), rnd.randrange(18)): rnd.choice((0.5, 2.0, 9.0))
                    for _ in range(60)}
            with steiner.soft_ground(soft):
                g2 = Grid(grid.occ, (), grid.spans)
            g2.drop_taps, g2.keep_clear = grid.drop_taps, grid.keep_clear
            self.assertIs(g2.soft, soft)
            with self.subTest(seed=seed):
                a = _run("1", g2, root, sinks)
                self.assertEqual(a, _run("0", g2, root, sinks))
                tiles = {(s[0], s[1]) for s, _mv in a[0]}
                crossed += bool(tiles & set(soft))
                for s, mv in a[0]:
                    if mv[0] == "split":
                        _n, m = steiner.Tree.split_tiles(s, mv[1])
                        self.assertNotIn(m, soft)
                self.assertFalse({q for q, *_r in a[2]} & set(soft))
        self.assertGreater(crossed, 10)             # belts did step on soft tiles
        self.assertEqual(Grid(set()).soft, {})      # outside soft_ground: none

    def test_fed_tiles(self):
        """PLAN-LANES phase 2: tiles other belts feed (a pair's join from both sides, or one
        side-load) take only the carriers lanephys allows (``Grid.lane_ok``); the same trees both
        ways, and every carrier a tree puts on a fed tile holds what the tile needs, by
        lanephys.fed itself. The masks count the outside feeds only: right where the tree starts
        (half the seeds feed the root, as a pair's join), a parity exercise mid-path (the tree's
        own belt into the tile is phase 3's)."""
        A, B, E = {"a"}, {"b"}, set()
        checked = roots = 0
        for seed in range(150):
            grid, root, sinks = (_reversed_case if seed % 2 else _case)(seed)
            if not sinks:
                continue
            rnd = random.Random(seed + 55)
            spec = {}
            for _ in range(40):
                t, h = (rnd.randrange(24), rnd.randrange(18)), rnd.randrange(4)
                if rnd.random() < 0.6:          # a pair's join: A from the left, B from the right
                    spec[t] = ({"L": A, "R": B},
                               [((h + 1) % 4 * 4, {"L": A, "R": A}),
                                ((h + 3) % 4 * 4, {"L": B, "R": B})])
                else:                           # A on one lane, side-loaded from the left
                    spec[t] = ({"L": A, "R": E}, [((h + 1) % 4 * 4, {"L": E, "R": A})])
            if seed % 4 < 2:                    # the root is a join, heading its own way
                h = root[2]
                spec[root[:2]] = ({"L": A, "R": B}, [((h + 1) % 4 * 4, {"L": A, "R": A}),
                                                    ((h + 3) % 4 * 4, {"L": B, "R": B})])
            grid.lane_ok = {t: lanephys.tile_mask(need, feeds) for t, (need, feeds) in spec.items()}
            with self.subTest(seed=seed):
                a = _run("1", grid, root, sinks)
                self.assertEqual(a, _run("0", grid, root, sinks))
                succ = dict(a[0])
                for s, mv in a[0]:
                    if mv[0] == "split":
                        for t in steiner.Tree.split_tiles(s, mv[1]):
                            if t in spec:
                                need, feeds = spec[t]
                                out, lost = lanephys.fed("splitter", s[2] * 4, feeds)
                                self.assertFalse(lost)
                for s in set(succ) | {c for mv in succ.values() for c in mv[1:]
                                      if isinstance(c, tuple)}:
                    t = (s[0], s[1])
                    if t not in spec:
                        continue
                    mv = succ.get(s)
                    carrier, d = ("ug_out", s[2]) if s[3] else \
                        ("ug_in", s[2]) if mv and mv[0] == "jump" else \
                        ("belt", mv[1][2]) if mv and mv[0] == "step" else ("belt", s[2])
                    need, feeds = spec[t]
                    out, lost = lanephys.fed(carrier, d * 4, feeds)
                    if s == tuple(root) and len(feeds) == 2:
                        self.assertEqual((carrier, d), ("belt", root[2]))   # straight on
                        roots += 1
                    self.assertFalse(lost, (seed, s, carrier, d))
                    self.assertEqual({k: set(v) for k, v in out.items() if v},
                                     {k: v for k, v in need.items() if v}, (seed, s, carrier, d))
                    checked += 1
        self.assertGreater(checked, 10)             # trees did cross fed tiles
        self.assertGreater(roots, 20)               # and left joins straight on

    def test_join_runs_straight_on(self):
        """The pair's join by the rules alone: only a belt running straight on holds A|B; an
        entrance holds it too when A rides one lane and the other side is an empty stub."""
        A, B, E = {"a"}, {"b"}, set()
        for h in range(4):
            feeds = [((h + 1) % 4 * 4, {"L": A, "R": A}), ((h + 3) % 4 * 4, {"L": B, "R": B})]
            m = lanephys.tile_mask({"L": A, "R": B}, feeds)
            self.assertEqual(m, 1 << lanephys.mask_bit("belt", h))
        feeds = [(4, {"L": E, "R": A}), (12, {"L": E, "R": E})]
        m = lanephys.tile_mask({"L": A, "R": E}, feeds)
        self.assertEqual(m, 1 << lanephys.mask_bit("belt", 0) | 1 << lanephys.mask_bit("ug_in", 0))

    def test_walk_and_hubs(self):
        """route._walk and route._hubs: the same dict (in the same order) and the same hubs."""
        from fkcore import route
        for seed in range(150):
            grid, _root, _sinks = _case(seed)
            rnd = random.Random(seed + 1000)
            box = (-1, -2, 23, 17)
            bg = route._Bounded(grid.occ, box, grid.spans)
            free = [(x, y) for x in range(box[0], box[2]) for y in range(box[1], box[3])
                    if (x, y) not in grid.occ]
            near_d = [rnd.sample(free, rnd.randrange(1, 3)) for _ in range(rnd.randrange(1, 4))]
            near_c = [rnd.sample(free, rnd.randrange(1, 3)) for _ in range(rnd.randrange(1, 4))]
            ends = set(rnd.sample(free, 3))
            with self.subTest(seed=seed):
                ng = route._native_box_grid(bg)
                self.assertIsNotNone(ng)
                for s in near_d + near_c + [[(-5, 3)]]:          # one seed outside the box
                    py = route._walk_py(bg, s)
                    self.assertEqual(list(steiner._native.walk(ng, s, 5)), list(py.items()))
                got = [(tuple(t), f) for t, f in steiner._native.hubs(ng, near_d, near_c, list(ends), 6)]
                self.assertEqual(got, route._hubs_py(bg, ends, near_d, near_c, 6))

    def test_check_mode_raises_on_a_difference(self):
        grid, root, sinks = _case(3)
        real = steiner._astar_native

        def off(tree, starts, sinks_, targets, limit):
            got = real(tree, starts, sinks_, targets, limit)
            return None if got and got is not steiner._UNSUPPORTED else got
        with mock.patch.object(steiner, "_astar_native", off), \
                mock.patch.object(steiner, "_grow_native", lambda *a: steiner._UNSUPPORTED):
            with self.assertRaises(AssertionError):
                _run("check", grid, root, sinks)

    def test_check_mode_compares_grow(self):
        grid, root, sinks = _case(3)
        real = steiner._grow_native

        def off(*a):
            got = real(*a)
            got["tree"].succ.popitem()
            return got
        with mock.patch.object(steiner, "_grow_native", off):
            with self.assertRaises(AssertionError):
                _run("check", grid, root, sinks)

    def test_physics_table_is_lanephys(self):
        """PLAN-4.0 K1: the kernel's lane physics is lanephys's table, every lookup for every
        argument; the table was taken at import and is taken once."""
        n = steiner._native
        self.assertTrue(n.physics_ready())
        self.assertFalse(n.physics(lanephys.table()))        # already set: the first import won
        for via in lanephys.VIAS:
            for s in lanephys.DIRS:
                for d in lanephys.DIRS:
                    for ug in ("in", "out"):
                        self.assertEqual(n.physics_lookup("moves", via, s, d, ug),
                                         lanephys.moves(via, s, d, ug), (via, s, d, ug))
        for a in lanephys.DIRS:
            for b in lanephys.DIRS:
                self.assertEqual(n.physics_lookup("drop_lane", a, b), lanephys.drop_lane(a, b))
                self.assertEqual(n.physics_lookup("mine_lane", a, b), lanephys.mine_lane(a, b))
                for c in lanephys.DIRS:
                    self.assertEqual(n.physics_lookup("turn_drop_lane", a, b, c),
                                     lanephys.turn_drop_lane(a, b, c))
        with self.assertRaises(ValueError):
            n.physics_lookup("moves", "drop", 0, 4, "in")

    def test_unknown_grid_falls_back(self):
        class Odd(Grid):
            def blocked(self, t):
                return t in self.occ
        grid, root, sinks = _case(5)
        odd = Odd(grid.occ, (), grid.spans)
        self.assertIsNone(steiner._native_grid(odd))
        self.assertEqual(_run("1", odd, root, sinks), _run("0", odd, root, sinks))


if __name__ == "__main__":
    unittest.main()
