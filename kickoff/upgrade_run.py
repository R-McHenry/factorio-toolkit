"""upgrade_run: move a running V1 run onto a newer toolkit. **Only with Rory's approval**: files a
running session uses never change under it (CLAUDE.md), so this is the explicit exception.

    python kickoff/upgrade_run.py RUN_DIR --sha SHA [--dry]

Between two of the player's turns, from the commit SHA (git archive, like new_run.py):
- `.toolkit\\fkcore`, `bin\\fk.py`, `bin\\fk.cmd`, `docs\\`, `AGENTS.md` (the brief), `CLAUDE.md`
  for a Claude player, and `launch.json`, replaced; the old ones are kept in
  `.upgrade-<old sha>\\`;
- `run.json`: `toolkit_sha` and `host_toolkit` (`fk-v5-SHA`, deployed first), plus an `upgrades`
  entry {from, to, at};
- `game\\nauvis.build.fkb`, if it still runs `report_bom --stock none` before the diff: that line
  moved after the diff as `report_bom --stock live` (the template's order), the old script kept
  beside it as `nauvis.build.fkb.before-<sha>`. The player's factories and surface are untouched.
- 1.1: a run whose own toolkit copy routed direct insertion with plain inserters (the 0534
  player's patch of route.py) keeps that: its build script's `route` line gets `--hand inserter`.
  The player's other patches (inserter=, item="a,b", a third lab belt) are 1.1 features. A Claude
  player's goal loop and hook (claude_loop.py, claude_hook.py) come into `.toolkit` too.
- 1.2: nothing in the run's game files changes. The record of the toolkit's own entities
  (`game\\out\\own\\<surface>.json`) starts at the next build, from the .fkp files last written.
  The host's toolkit must be 1.2 too: bin\\fk.py sends `fk lua` chunks to `fkcore lua --file -`.

It prints what the player should be told: which commands are new, which docs to read again.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from new_run import CLAUDE, LAUNCH  # noqa: E402

REPLACED = (".toolkit", "bin", "docs", "AGENTS.md", "CLAUDE.md", "launch.json")


def _archive(sha, dest, paths):
    tar = subprocess.run(["git", "-C", ROOT, "archive", "--format=tar", sha] + list(paths),
                         stdout=subprocess.PIPE, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        t.extractall(dest, filter="data")


def _script(text):
    """The build script with report_bom --stock live after the diff (None: nothing to change)."""
    lines = text.splitlines(True)
    bom = [i for i, l in enumerate(lines) if l.startswith("report_bom")]
    diff = [i for i, l in enumerate(lines) if l.startswith("diff ")]
    if not bom or not diff or (bom[0] > diff[0] and "--stock live" in lines[bom[0]]):
        return None
    del lines[bom[0]]
    d = [i for i, l in enumerate(lines) if l.startswith("diff ")][0]
    lines.insert(d + 1, "report_bom      --stock live              # still to build vs the "
                        "network's stock and research (LOW_STOCK, LOCKED)\n")
    return "".join(lines)


def _hand(text):
    """The build script with ``--hand inserter`` on its route line (None: nothing to change)."""
    lines = text.splitlines(True)
    for i, l in enumerate(lines):
        if l.startswith("route") and "--hand" not in l:
            body, sep, note = l.partition("#")
            lines[i] = f"{body.rstrip()} --hand inserter" + (f"   {sep}{note}" if sep else "\n")
            return "".join(lines)
    return None


def _plain_hands(run):
    """Did the run's own toolkit copy route direct insertion with plain inserters?"""
    path = os.path.join(run, ".toolkit", "fkcore", "route.py")
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as fh:
        return '_HANDS = (("inserter",)' in fh.read()


def upgrade(run, sha, dry=False):
    cfg_path = os.path.join(run, "run.json")
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    sha = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", sha], stdout=subprocess.PIPE,
                         check=True, text=True).stdout.strip()
    old = cfg.get("toolkit_sha", "unknown")
    plan = [f"run {run}: toolkit {old} -> {sha}"]
    script = os.path.join(run, "game", "nauvis.build.fkb")
    new_script, hand = None, False
    if os.path.exists(script):
        with open(script, encoding="utf-8") as fh:
            text = fh.read()
        new_script = _script(text)
        if _plain_hands(run):
            hand = _hand(new_script or text)
            new_script = hand or new_script
    plan += [f"  replace {p} (old kept in .upgrade-{old}/)" for p in REPLACED
             if os.path.exists(os.path.join(run, p)) or p in (".toolkit", "bin", "docs")]
    if new_script:
        plan.append("  game/nauvis.build.fkb: " + ("route --hand inserter (its own route.py "
                    "used plain inserters)" if hand else "report_bom --stock live after the diff")
                    + f" (old kept as nauvis.build.fkb.before-{sha})")
    plan.append(f"  run.json: toolkit_sha {sha}, host_toolkit /home/computah/factorio/fk-v5-{sha}")
    if dry:
        return plan
    src = os.path.join(run, f".kit-{sha}")
    claude = cfg.get("player") == "claude"
    _archive(sha, src, ("agent", "fkcore")
             + (("kickoff/claude_loop.py", "kickoff/claude_hook.py") if claude else ()))
    keep = os.path.join(run, f".upgrade-{old}")
    os.makedirs(keep, exist_ok=True)
    for p in REPLACED:
        cur = os.path.join(run, p)
        if os.path.exists(cur):
            shutil.move(cur, os.path.join(keep, p))
    agent = os.path.join(src, "agent")
    os.makedirs(os.path.join(run, ".toolkit"))
    shutil.copytree(os.path.join(src, "fkcore"), os.path.join(run, ".toolkit", "fkcore"))
    if claude:
        for name in ("claude_loop.py", "claude_hook.py"):
            shutil.copy(os.path.join(src, "kickoff", name), os.path.join(run, ".toolkit", name))
    os.makedirs(os.path.join(run, "bin"))
    shutil.copy(os.path.join(agent, "fk.py"), os.path.join(run, "bin", "fk.py"))
    shutil.copy(os.path.join(agent, "bin", "fk.cmd"), os.path.join(run, "bin", "fk.cmd"))
    shutil.copytree(os.path.join(agent, "docs"), os.path.join(run, "docs"))
    shutil.copy(os.path.join(agent, "prompts", f"{cfg.get('prompt', 'core-v1')}.md"),
                os.path.join(run, "AGENTS.md"))
    with open(os.path.join(run, "launch.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(LAUNCH, fh, indent=1)
    if cfg.get("player") == "claude":
        with open(os.path.join(run, "CLAUDE.md"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(CLAUDE)
    shutil.rmtree(src)
    if new_script:
        shutil.copy(script, f"{script}.before-{sha}")
        with open(script, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new_script)
    cfg["upgrades"] = list(cfg.get("upgrades") or []) + [
        {"from": old, "to": sha, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}]
    cfg["toolkit_sha"] = sha
    if cfg.get("host_toolkit"):
        cfg["host_toolkit"] = f"/home/computah/factorio/fk-v5-{sha}"
    with open(cfg_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(cfg, fh, indent=1)
    return plan


TELL = """Tell the player (its next message; a Claude player's INBOX.md):
  Toolkit 1.3 is in. The build can now say what your belts and inserters as laid let through: add
  a line `report_rates` after `route` in game\\nauvis.build.fkb, and out\\report_rates.txt gets
  the routed rates; a CAPACITY line names a belt lane, splitter or inserter that is too thin for
  what your design asks (a yellow lane carries 7.5/s, a fast inserter 2.5/s). To lay red belts
  where yellow is too thin, add `tier minimize --allow yellow,red` after `route` (`--red 20` caps
  how many). A module placed with rot now turns its whole contents. Details in
  docs\\TOOLKIT.md."""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run")
    ap.add_argument("--sha", required=True)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)
    print("\n".join(upgrade(a.run, a.sha, a.dry)))
    if not a.dry:
        print(TELL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
