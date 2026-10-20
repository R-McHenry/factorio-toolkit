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


def upgrade(run, sha, dry=False):
    cfg_path = os.path.join(run, "run.json")
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    sha = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", sha], stdout=subprocess.PIPE,
                         check=True, text=True).stdout.strip()
    old = cfg.get("toolkit_sha", "unknown")
    plan = [f"run {run}: toolkit {old} -> {sha}"]
    script = os.path.join(run, "game", "nauvis.build.fkb")
    new_script = None
    if os.path.exists(script):
        with open(script, encoding="utf-8") as fh:
            new_script = _script(fh.read())
    plan += [f"  replace {p} (old kept in .upgrade-{old}/)" for p in REPLACED
             if os.path.exists(os.path.join(run, p)) or p in (".toolkit", "bin", "docs")]
    if new_script:
        plan.append("  game/nauvis.build.fkb: report_bom --stock live after the diff (old kept "
                    f"as nauvis.build.fkb.before-{sha})")
    plan.append(f"  run.json: toolkit_sha {sha}, host_toolkit /home/computah/factorio/fk-v5-{sha}")
    if dry:
        return plan
    src = os.path.join(run, f".kit-{sha}")
    _archive(sha, src, ("agent", "fkcore"))
    keep = os.path.join(run, f".upgrade-{old}")
    os.makedirs(keep, exist_ok=True)
    for p in REPLACED:
        cur = os.path.join(run, p)
        if os.path.exists(cur):
            shutil.move(cur, os.path.join(keep, p))
    agent = os.path.join(src, "agent")
    os.makedirs(os.path.join(run, ".toolkit"))
    shutil.copytree(os.path.join(src, "fkcore"), os.path.join(run, ".toolkit", "fkcore"))
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


TELL = """Tell the player (its next message):
  The toolkit was upgraded between your turns. Re-read AGENTS.md ("When a build doesn't finish") and
  docs\\TOOLKIT.md. New: a look marks GHOST SHORT (the network holds none of the item) and GHOST
  LOCKED (its recipe is not researched); fk build's out\\report_bom.txt has a STOCK line with
  LOW_STOCK and LOCKED; alerts come grouped with what the network holds; every command ends with
  the research line; and fk research [TECH], fk tech NAME, fk recipes [NAME] are new."""


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
