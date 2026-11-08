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


def _run(mode, grid, root, sinks):
    with mock.patch.dict(os.environ, {"FK_NATIVE": mode}):
        out = steiner.grow(grid, root, sinks, limit=20000)
    t = out["tree"]
    return sorted(t.succ.items()), sorted(t.sink_at.items()), sorted(t.taps), out["log"]


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
        with mock.patch.object(steiner, "_astar_native", off):
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
