"""buildbench: how long a run's design build takes, step by step and net by net. Stdlib only.

    python tools/buildbench.py GAME_DIR [--to STEP] [--cap S] [--slow S] [--tree PATH]

Copies GAME_DIR (a run's ``game\\``, without ``out/fkp-history``) to a temporary folder and runs
PATH's fkcore build there (default: this tree), offline, from ``read_surface`` to STEP (default
``report_checks``, the end of the design half). Prints each step's time, and each route net that
took ``--slow`` seconds or more (default 2). At ``--cap`` seconds (default 120) it stops and
says which step and net it was in, so a slow build costs the cap, not its length. Exit 0 when
it reached STEP, 3 when the cap stopped it.

2.1.26: the 20261030-2352 run's dry builds ran 20+ min (a rate model that never settled, ~5 min
twice; coal's route flooding the whole frame, ~250 s a pass) and nothing said where.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("game")
    ap.add_argument("--to", default="report_checks")
    ap.add_argument("--cap", type=float, default=120.0)
    ap.add_argument("--slow", type=float, default=2.0)
    ap.add_argument("--tree", default=os.path.dirname(HERE))
    a = ap.parse_args(argv)
    sys.path.insert(0, os.path.abspath(a.tree))
    from fkcore import flow, route
    from fkcore.__main__ import main as fkmain

    tmp = tempfile.mkdtemp(prefix="buildbench-")
    game = os.path.join(tmp, "game")
    shutil.copytree(a.game, game, ignore=shutil.ignore_patterns("fkp-history"))
    began = time.monotonic()
    where = {"step": None, "net": None, "net_at": 0.0}

    def say(text):
        print(f"{time.monotonic() - began:7.1f}s  {text}", file=sys.__stdout__, flush=True)

    for name, fn in list(flow.STEPS.items()):
        def timed(ctx, args, name=name, fn=fn):
            where["step"], t = name, time.monotonic()
            try:
                return fn(ctx, args)
            finally:
                net_done(time.monotonic())
                say(f"step {name:<14} {time.monotonic() - t:8.1f} s")
        flow.STEPS[name] = timed

    def net_done(now):
        if where["net"] is not None and now - where["net_at"] >= a.slow:
            say(f"  net {where['net']:<30} {now - where['net_at']:8.1f} s")
        where["net"] = None

    orig = route._progress

    def progress(attempt, k, order, net):
        now = time.monotonic()
        net_done(now)
        where["net"], where["net_at"] = f"p{attempt + 1} {net}", now
        orig(attempt, k, order, net)
    route._progress = progress

    def cap():
        time.sleep(a.cap)
        net = f", net {where['net']} for {time.monotonic() - where['net_at']:.0f} s" \
            if where["net"] else ""
        say(f"CAP {a.cap:g} s: stopped in step {where['step']}{net}")
        shutil.rmtree(tmp, ignore_errors=True)
        os._exit(3)
    threading.Thread(target=cap, daemon=True).start()

    os.chdir(game)
    import io
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        code = fkmain(["build", "nauvis.build.fkb", "--from", "read_surface", "--to", a.to])
    say(f"done to {a.to}: exit {code}")
    os.chdir(tmp)
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
