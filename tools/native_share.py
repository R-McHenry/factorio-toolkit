"""native_share: how much of the router's search runs in the Rust kernel while test modules run.

    python tools/native_share.py tests.test_route [tests.test_x ...]

Wraps ``steiner``'s four search entry points (the native and the Python grow, the native and the
Python A*) and ``route``'s two hub searches, runs the named test modules, and prints calls and
seconds per side plus why each grow fell back to Python (a sink of its own, a grid the kernel
does not know, a tile that is no int). A native hub search runs its grows inside the kernel, so
they are not counted as grows. The measure PLAN-4.0 part K is judged by: the router modules at 0
Python grows, 0 Python A* and 0 Python hub searches. Stdlib only; run from the v5 tree.
"""
from __future__ import annotations

import os
import sys
import time
import unittest

sys.path.insert(0, os.getcwd())
from fkcore import route, steiner  # noqa: E402

counts = {"grow_native": 0, "grow_py": 0, "astar_native": 0, "astar_py": 0, "hub_native": 0, "hub_py": 0}
times = {k: 0.0 for k in counts}
why = {}

_gn, _gp, _an, _ap = steiner._grow_native, steiner._grow_py, steiner._astar_native, steiner._astar_py
_hn, _hp = route._hub_search_native, route._hub_search_py


def _wrap(name, fn):
    def w(*a, **k):
        t0 = time.perf_counter()
        try:
            return fn(*a, **k)
        finally:
            counts[name] += 1
            times[name] += time.perf_counter() - t0
    return w


def _grow_native(grid, root, sinks, *a, **k):
    out = _gn(grid, root, sinks, *a, **k)
    if out is steiner._UNSUPPORTED:
        counts["grow_native"] -= 1
        reasons = []
        for s in sinks:
            if type(s) not in (steiner.TapSink, steiner.FixedSink, steiner.DropSink):
                reasons.append(type(s).__name__)
        if not sinks:
            reasons.append("no-sinks")
        if steiner._native_grid(grid) is None:
            reasons.append("grid-subclass")
        key = ",".join(sorted(set(reasons))) or "other"
        why[key] = why.get(key, 0) + 1
    return out


def _hub_native(*a, **k):
    out = _hn(*a, **k)
    if out is steiner._UNSUPPORTED:
        counts["hub_native"] -= 1
    return out


def main(names):
    steiner._grow_native = _wrap("grow_native", _grow_native)
    steiner._grow_py = _wrap("grow_py", _gp)
    steiner._astar_native = _wrap("astar_native", _an)
    steiner._astar_py = _wrap("astar_py", _ap)
    route._hub_search_native = _wrap("hub_native", _hub_native)
    route._hub_search_py = _wrap("hub_py", _hp)
    t0 = time.perf_counter()
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    res = unittest.TextTestRunner(verbosity=0).run(suite)
    print(f"wall {time.perf_counter() - t0:.1f}s  tests {res.testsRun} failures "
          f"{len(res.failures)} errors {len(res.errors)}")
    for k in counts:
        print(f"{k:14s} calls {counts[k]:5d}  time {times[k]:7.2f}s")
    print("grow fallbacks by reason:", why or "none")
    return 1 if (res.failures or res.errors) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
