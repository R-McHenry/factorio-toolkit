"""stats_sample: one stats sample of a run, and its page (2.1, Rory 2026-10-31: run stats).

    python stats_sample.py RUN [--now] [--no-page]

``fkcore stats . --sample`` through the run's own toolkit where the game is (the host, or this
machine for a laptop server): the scenario recorder's new samples, or (a map made before the
recorder) one read-only RCON read when 5 game minutes have passed since the last sample, and the
capital read every 10 game minutes. Then the run's ``game\\out\\stats`` and ``game\\out\\capital``
come back here, and the stats page is written here, ``game\\out\\stats\\index.html``, with the
run's toolkit (the page's work stays on the laptop). Nothing in the game changes, and nothing is
registered in it.

The goal loop (claude_loop.py) calls ``sample`` every 5 game minutes. A run with no loop (one
driven from a conversation) can run this file on a schedule: it is safe to run at any time and
as often as you like, since it keeps only what is due, and it never touches the player's alerts
or chat cursor. ``--now`` takes a sample at once.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shlex
import subprocess
import sys
import tarfile

#: ticks between two samples (fkcore.runstats.EVERY)
EVERY = 5 * 60 * 60


def _env(run, cfg, link):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
               PYTHONPATH=os.path.join(run, ".toolkit"))
    env.pop("FK_LINK", None)
    if link:
        env["FK_LINK"] = "on"
    if cfg.get("host") == "local" or link:
        env.update({k: v for k, v in (cfg.get("env") or {}).items() if v})
    return env


def _lines(text):
    return [ln for ln in (text or "").splitlines() if ln.strip()]


def sample(run, cfg=None, now=False, page=True, timeout=60):
    """One sample of ``run`` -> (the sampler's lines, ok)."""
    run = os.path.abspath(run)
    if cfg is None:
        with open(os.path.join(run, "run.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
    game = os.path.join(run, "game")
    args = ["stats", ".", "--sample"] + (["--now"] if now else [])
    if cfg.get("host") == "local":
        r = subprocess.run([sys.executable, "-m", "fkcore"] + args, cwd=game,
                           env=_env(run, cfg, True), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        lines, ok = _lines(r.stdout) + _lines(r.stderr), r.returncode == 0
    else:
        host, hg = cfg.get("host", "computah-ct"), cfg["host_game"]
        cmd = (f"cd {shlex.quote(hg)} && FK_LINK=on PYTHONPATH={shlex.quote(cfg['host_toolkit'])} "
               f"timeout 45 python3 -m fkcore " + " ".join(shlex.quote(a) for a in args))
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", host, cmd], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        lines, ok = _lines(r.stdout) + _lines(r.stderr), r.returncode == 0
        # the samples and the capital history come back here (only those two folders)
        t = subprocess.run(["ssh", "-o", "BatchMode=yes", host,
                            f"cd {shlex.quote(hg)} && tar -cf - $(ls -d out/stats out/capital "
                            "2>/dev/null)"], capture_output=True, timeout=timeout)
        if t.returncode == 0 and t.stdout:
            with tarfile.open(fileobj=io.BytesIO(t.stdout)) as tar:
                keep = [m for m in tar.getmembers() if (m.isfile() or m.isdir())
                        and m.name.split("/")[:2] in (["out", "stats"], ["out", "capital"])
                        and ".." not in m.name.split("/")]
                tar.extractall(game, members=keep, filter="data")
        elif t.returncode:
            lines.append(f"stats: the samples were not copied back ({t.returncode})")
    kept = any(" kept from " in ln for ln in lines)
    if page and ok and (kept or not os.path.exists(os.path.join(game, "out", "stats",
                                                                "index.html"))):
        p = subprocess.run([sys.executable, "-m", "fkcore", "stats", ".", "--page"], cwd=game,
                           env=_env(run, cfg, False), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        lines += _lines(p.stdout)[-1:] if p.returncode == 0 else \
            [f"stats page: not written ({(_lines(p.stderr) or [p.returncode])[-1]})"]
    return lines, ok


def next_due(run):
    """The game tick the next sample is due at, from the run's ``game\\out\\stats\\state.json``
    (the later of the last sample and the recorder's last line, plus 5 game minutes), or None
    when nothing was sampled yet."""
    try:
        with open(os.path.join(run, "game", "out", "stats", "state.json"), encoding="utf-8") as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        return None
    ticks = [int((st.get(k) or {}).get("tick") or 0) for k in ("last", "recorder")
             if isinstance(st.get(k), dict)]
    return max(ticks) + EVERY if ticks else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run")
    ap.add_argument("--now", action="store_true")
    ap.add_argument("--no-page", action="store_true")
    a = ap.parse_args(argv)
    lines, ok = sample(a.run, now=a.now, page=not a.no_page)
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
