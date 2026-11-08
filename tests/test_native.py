"""fkroute (native/fkroute, Rust) against steiner's Python search: the same trees, call for call.

Skipped when fkroute is not installed: fkcore stays stdlib only and runs the Python search.
"""
import os
import random
import unittest
from unittest import mock

from fkcore import steiner
from fkcore.steiner import FixedSink, Grid, TapSink


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
