"""lane_measure: the lane-state search (fkcore.lanesearch) against pairs.route_lanes on the pair
jobs the pairs modules route (PLAN-4.0 N1's one-off measurement; PLAN-LANES phase 4's table).

    python tools/lane_measure.py [--modules M ...] [--limit N]

Runs the pairs test modules (test_lanes_pairs, test_lane_goal, test_port_pairs by default) with
``pairs.route_lanes`` wrapped: every pair job it lays is also handed to ``lanesearch.route`` on
the same ground, box and spans, and the two are compared: routed, carriers, cost
(``pairs._cost``: belts, undergrounds, splitters, as the search prices them) and seconds. A
Markdown table on stdout; nothing is wired into the build. Stdlib only.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TREE = os.path.dirname(HERE)
sys.path.insert(0, TREE)

from fkcore import lanesearch as ls  # noqa: E402
from fkcore import pairs, route as routemod  # noqa: E402

ROWS = []
A, B = 1, 2


def lane_job(job):
    """A pairs NetJob (parts (left, right, pair)) as a LaneJob, or (None, why)."""
    left, right, pair = job.parts
    if left.drops or right.drops:
        return None, "drills (DropSink)"
    wide = bool(job.wide)
    if wide:
        nets = [job.net]
        starts = {A: [(t, h, (A, A)) for t, h in left.starts + right.starts]}
        sources = {A: list(left.sources + right.sources)}
        need = (A, A)
        ids = {A}
    elif job.pin:
        nets = [job.net]
        starts = {A: [(t, h, (A, A)) for t, h in left.starts + right.starts]}
        sources = {A: list(left.sources + right.sources)}
        need = (A, 0) if job.pin == "L" else (0, A)
        ids = {A}
    else:
        nets = [left.net, right.net]
        starts = {A: [(t, h, (A, A)) for t, h in left.starts],
                  B: [(t, h, (B, B)) for t, h in right.starts]}
        sources = {A: list(left.sources), B: list(right.sources)}
        need = (A if left.drivers() else 0, B if right.drivers() else 0)
        ids = {A, B} if left.drivers() and right.drivers() else ({A} if left.drivers() else {B})
    goals = [ls.Fixed(f"g{i}", t, h, need) for i, (t, h) in enumerate(pair.goals)]
    goals += [ls.Tap(key, rect, ids, 1, routemod._HANDS[-1]) for key, rect in pair.taps]
    if not goals:
        return None, "no belt goal or tap"
    return ls.LaneJob(nets, starts, sources, goals), ""


def measure(cat, job, ents, frames, js, box, limit, terrain, avoid, spans, allow, got, text, took):
    laid = got or []
    kind = "wide" if job.wide else "pin" if job.pin else "pair"
    row = {"net": job.net, "kind": kind, "old_ok": got is not None, "old_n": len(laid),
           "old_cost": pairs._cost(cat, laid)[0] if got is not None else None, "old_s": took,
           "new_ok": False, "new_n": 0, "new_cost": None, "new_s": 0.0, "why": ""}
    ROWS.append(row)
    if got is not None and "direct insertion" in text:
        row["why"] = "direct insertion"
        return
    lj, why = lane_job(job)
    if lj is None:
        row["why"] = why
        return
    blocked = routemod._ground(cat, ents, frames, js, job.net, terrain) | (set(avoid) - set(job.ends()))
    sp = routemod._ug_spans(cat, ents) if spans is None else spans
    t0 = time.time()
    res = None
    near = routemod._near_box(job, box)
    for b in ([near, box] if near is not None else [box]):
        grid = routemod._Bounded(blocked, b, sp)
        res = ls.route(grid, lj, limit=limit)
        if not res.problems:
            break
    row["new_s"] = round(time.time() - t0, 3)
    row["new_ok"] = not res.problems
    plan = res.entities(lj)
    carriers = routemod._carriers(job, plan, job.net)
    row["new_n"] = len(carriers)
    row["new_cost"] = pairs._cost(cat, carriers)[0]
    row["why"] = "; ".join(res.problems)[:80]
    row["order"] = res.order
    row["rides"] = sum(len(t.rides) for t in res.trees.values())


def wrapped(real):
    def route_lanes(cat, job, ents, frames, js, box, limit, terrain=(), avoid=(), spans=None,
                    allow=frozenset()):
        t0 = time.time()
        got, text = real(cat, job, ents, frames, js, box, limit, terrain, avoid, spans, allow)
        took = round(time.time() - t0, 3)
        try:
            measure(cat, job, list(ents), frames, js, box, limit, terrain, avoid, spans, allow,
                    got, text, took)
        except Exception as exc:        # the measurement never breaks the test it rides
            ROWS.append({"net": job.net, "kind": "?", "old_ok": got is not None, "old_n": len(got or []),
                         "old_cost": None, "old_s": took, "new_ok": False, "new_n": 0,
                         "new_cost": None, "new_s": 0.0, "why": f"error: {exc!r}"[:80]})
        return got, text
    return route_lanes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--modules", nargs="*",
                    default=["tests.test_lanes_pairs", "tests.test_lane_goal", "tests.test_port_pairs"])
    ap.add_argument("--limit", type=int, default=60000)
    a = ap.parse_args(argv)
    real = pairs.route_lanes
    pairs.route_lanes = wrapped(real)
    pairs.route = lambda *args, **kw: pairs.route_lanes(*args, **kw)
    try:
        suite = unittest.defaultTestLoader.loadTestsFromNames(a.modules)
        out = io.StringIO()
        result = unittest.TextTestRunner(stream=out, verbosity=0).run(suite)
    finally:
        pairs.route_lanes = real
    seen, rows = set(), []
    for r in ROWS:
        key = (r["net"], r["old_n"], r["old_cost"], r["new_n"], r["new_cost"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)
    print(f"tests: {result.testsRun} run, {len(result.failures)} failed, {len(result.errors)} errors")
    print()
    print("| job | kind | route_lanes | carriers | cost | s | lanesearch | carriers | cost | s | order | rides | note |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['net']} | {r['kind']} | {'ok' if r['old_ok'] else 'FAIL'} | {r['old_n']} | "
              f"{r['old_cost'] if r['old_cost'] is not None else ''} | {r['old_s']} | "
              f"{'ok' if r['new_ok'] else 'FAIL'} | {r['new_n']} | "
              f"{r['new_cost'] if r['new_cost'] is not None else ''} | {r['new_s']} | "
              f"{r.get('order', '')} | {r.get('rides', '')} | {r['why']} |")
    both = [r for r in rows if r["old_ok"] and r["new_ok"]]
    print()
    print(f"jobs {len(rows)}; route_lanes routed {sum(r['old_ok'] for r in rows)}, lanesearch routed "
          f"{sum(r['new_ok'] for r in rows)}; on the {len(both)} both route: carriers "
          f"{sum(r['old_n'] for r in both)} -> {sum(r['new_n'] for r in both)}, cost "
          f"{sum(r['old_cost'] for r in both):.1f} -> {sum(r['new_cost'] for r in both):.1f}, "
          f"cheaper {sum(r['new_cost'] < r['old_cost'] for r in both)}, dearer "
          f"{sum(r['new_cost'] > r['old_cost'] for r in both)}, equal "
          f"{sum(r['new_cost'] == r['old_cost'] for r in both)}; seconds "
          f"{sum(r['old_s'] for r in rows):.2f} -> {sum(r['new_s'] for r in rows):.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
