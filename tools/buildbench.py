"""buildbench: where a run's design build spends its time, step by step and net by net. Stdlib only.

    python tools/buildbench.py GAME_DIR [--from STEP] [--to STEP] [--cap S] [--no-stop]
                               [--keep] [--in-place] [--slow S] [--tree PATH]

Copies GAME_DIR (a run's ``game\\``, without ``out/fkp-history``) to a temporary folder and runs
PATH's fkcore build there (default: this tree), offline, from STEP (default ``read_surface``; a
later step starts from the checkpoints the folder holds) to STEP (default ``report_checks``, the
end of the design half). It prints each step's time, each route net of ``--slow`` seconds or more
(default 2), and for each step of ``--slow`` or more the fkcore frames its stack samples (every
0.1 s) were in most. At ``--cap`` seconds (default 30: a slow action's first 30 s say where its
time goes) it stops with what it has. ``--no-stop`` drops the script's ``stop_on`` lines, to reach
the steps after a stop. ``--keep`` keeps the copy and prints where (its checkpoints let the next
probe start later with ``--from``); ``--in-place`` runs in GAME_DIR itself (a kept copy). Exit 0
when it reached STEP, 3 when the cap stopped it.

2.1.26: the 20261030-2352 run's dry builds ran 20+ min (a rate model that never settled; coal's
route flooding the whole frame) and nothing said where.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import io
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
    ap.add_argument("--from", dest="frm", default="read_surface")
    ap.add_argument("--to", default="report_checks")
    ap.add_argument("--cap", type=float, default=30.0)
    ap.add_argument("--slow", type=float, default=2.0)
    ap.add_argument("--tree", default=os.path.dirname(HERE))
    ap.add_argument("--no-stop", action="store_true")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--in-place", action="store_true")
    a = ap.parse_args(argv)
    sys.path.insert(0, os.path.abspath(a.tree))
    from fkcore import flow, route
    from fkcore.__main__ import main as fkmain

    if a.in_place:
        tmp, game = None, os.path.abspath(a.game)
    else:
        tmp = tempfile.mkdtemp(prefix="buildbench-")
        game = os.path.join(tmp, "game")
        shutil.copytree(a.game, game, ignore=shutil.ignore_patterns("fkp-history"))
    if a.no_stop:
        script = os.path.join(game, "nauvis.build.fkb")
        with open(script, encoding="utf-8") as fh:
            keep = [ln for ln in fh if not ln.lstrip().startswith("stop_on")]
        with open(script, "w", encoding="utf-8") as fh:
            fh.writelines(keep)
    began = time.monotonic()
    where = {"step": None, "net": None, "net_at": 0.0}
    samples = collections.Counter()           # (step, frame) -> samples
    main_id = threading.get_ident()

    def say(text):
        print(f"{time.monotonic() - began:7.1f}s  {text}", file=sys.__stdout__, flush=True)

    def hot(step, n=6):
        rows = sorted(((v, f) for (s, f), v in samples.items() if s == step), reverse=True)
        for v, f in rows[:n]:
            say(f"      {v:4} samples  {f}")

    def finish():
        if tmp is None:
            return
        if a.keep:
            say(f"kept: {game}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    for name, fn in list(flow.STEPS.items()):
        def timed(ctx, args, name=name, fn=fn):
            where["step"], t = name, time.monotonic()
            try:
                return fn(ctx, args)
            finally:
                net_done(time.monotonic())
                took = time.monotonic() - t
                say(f"step {name:<14} {took:8.1f} s")
                if took >= a.slow:
                    hot(name)
        flow.STEPS[name] = timed

    def net_done(now):
        if where["net"] is not None and now - where["net_at"] >= a.slow:
            say(f"  net {where['net']:<30} {now - where['net_at']:8.1f} s")
        where["net"] = None

    orig = route._progress

    def progress(attempt, k, order, net, *more, **kw):
        now = time.monotonic()
        net_done(now)
        where["net"], where["net_at"] = f"p{attempt + 1} {net}", now
        orig(attempt, k, order, net, *more, **kw)
    route._progress = progress

    def sampler():
        end = began + a.cap
        while time.monotonic() < end:
            time.sleep(0.1)
            f = sys._current_frames().get(main_id)
            step = where["step"]
            if f is None or step is None:
                continue
            # the frames themselves: traceback.extract_stack stats every source file (linecache)
            # and took ~0.3 s a sample, slowing the build it measured
            seen = set()
            while f is not None:
                c = f.f_code
                if os.sep + "fkcore" + os.sep in c.co_filename and "flow.py" not in c.co_filename:
                    seen.add(f"{os.path.basename(c.co_filename)}:{c.co_name}:{f.f_lineno}")
                f = f.f_back
            for x in seen:
                samples[(step, x)] += 1
        net = f", net {where['net']} for {time.monotonic() - where['net_at']:.0f} s" \
            if where["net"] else ""
        say(f"CAP {a.cap:g} s: stopped in step {where['step']}{net}")
        hot(where["step"], 10)
        finish()
        os._exit(3)
    threading.Thread(target=sampler, daemon=True).start()

    os.chdir(game)
    with contextlib.redirect_stdout(io.StringIO()):
        code = fkmain(["build", "nauvis.build.fkb", "--from", a.frm, "--to", a.to])
    say(f"done to {a.to}: exit {code}")
    os.chdir(HERE)
    finish()
    return 0


if __name__ == "__main__":
    sys.exit(main())
