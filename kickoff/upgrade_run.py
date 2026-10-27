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
- 1.6: the build script gets the template's `size` line after `elaborate` (the build counts the
  `n=auto` rows); a script without one says so when a factory has such a row. The host's
  toolkit must be 1.6 too: it replays the size step for `--from diff`.
- 1.7: the build script's `write_layout` moves to just before `apply`, as in the template, so
  `fk build --to diff` writes nothing (a dry run had made its design the one the next build kept
  to). A run without `helpers\\` gets the template's (the player's reusable features); one that
  has it keeps its own. The host's toolkit must be 1.7 too: it runs `write_layout` now.
- 2.0 (in progress): a run with workers (run.json `workers`) gets the new worker brief in
  `.claude\\agents\\worker.md` (the old one kept in `.upgrade-<old sha>\\`).
- 2.0.12: the build script gets the template's `stop_on no-route no-destination` (the stops it lacks),
  and a Claude player's `.toolkit` the loop's watchdog (watchdog.py), which the loop starts.

It prints what the player should be told: which commands are new, which docs to read again.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from new_run import CLAUDE, LAUNCH, LEAD_FIRST, LOOP, write_worker  # noqa: E402

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
                        "network's stock and research (short-stock, needs-research)\n")
    return "".join(lines)


#: the template's size line (1.6): the build counts the n=auto rows
SIZE_LINE = ("size                                      # n=auto rows: the fewest machines for the "
             "targets, asserts and consumers (out/size.txt)\n")


def _size(text):
    """The build script with the size step after elaborate (None: nothing to change)."""
    lines = text.splitlines(True)
    steps = [line.split("#")[0].split()[:1] for line in lines]
    if ["size"] in steps or ["elaborate"] not in steps:
        return None
    i = steps.index(["elaborate"])
    if not lines[i].endswith("\n"):
        lines[i] += "\n"
    lines.insert(i + 1, SIZE_LINE)
    return "".join(lines)


def _write_last(text):
    """The build script with ``write_layout`` just before ``apply`` (1.7), so ``--to diff`` and
    ``--to report_bom`` write nothing (None: nothing to change)."""
    lines = text.splitlines(True)
    steps = [line.split("#")[0].split()[:1] for line in lines]
    if ["write_layout"] not in steps or ["apply"] not in steps:
        return None
    w, a = steps.index(["write_layout"]), steps.index(["apply"])
    if w > a or not any(steps[w + 1:a]):
        return None                    # after the paste, or no step between: --to diff writes none
    line = lines.pop(w)
    if not line.endswith("\n"):
        line += "\n"
    lines.insert(a - 1, line)
    return "".join(lines)


#: the template's second stop_on line (2.0.12): no paste with a net unrouted, or a maker whose
#: product reaches no sink
STOPS = ("no-route", "no-destination")
#: what an older run's script may still say for a stop (2.0.52's rename): read either way, so an
#: upgrade adds only the stops the run really lacks
OLD_STOPS = {"unrouted": "no-route", "no_sink": "no-destination", "no sink": "no-destination",
             "invariant": "malformed"}


def _stops(text):
    """The build script with a ``stop_on`` line for the template's stops it lacks (2.0.12), after
    its last stop_on line or at its end (None: nothing to change)."""
    lines = text.splitlines(True)
    steps = [line.split("#")[0].split() for line in lines]
    have = {OLD_STOPS.get(a.lower(), a.lower())
            for s in steps if s[:1] == ["stop_on"] for a in s[1:]}
    need = [c for c in STOPS if c not in have]
    if not need:
        return None
    at = max([i for i, s in enumerate(steps) if s[:1] == ["stop_on"]] or [len(lines) - 1])
    if lines and not lines[at].endswith("\n"):
        lines[at] += "\n"
    lines.insert(at + 1, f"{'stop_on':<16}{' '.join(need):<26}# and no paste with a net unrouted, "
                         "or a maker whose product reaches no sink\n")
    return "".join(lines)


def _hand(text):
    """The build script with ``--hand any`` on its route line: direct insertion takes the lowest
    hand the network can build now, and the ``hands`` step raises the connectors the flow needs more
    of (2.0.14/2.0.15), instead of the fast inserter a 1.1 toolkit laid whether the network held one
    or not, or the plain one a 1.1 upgrade had to patch in by hand. None: nothing to change."""
    lines = text.splitlines(True)
    for i, l in enumerate(lines):
        if l.startswith("route"):
            body, sep, note = l.partition("#")
            if re.search(r"--hand\s+any\b", body):
                return None
            body = re.sub(r"--hand\s+\S+", "--hand any", body) if "--hand" in body \
                else f"{body.rstrip()} --hand any"
            lines[i] = body.rstrip() + (f"   {sep}{note}" if sep else "\n")
            return "".join(lines)
    return None


def _hands_step(text):
    """The build script with a ``hands minimize`` line right after its route line (2.0.15): every
    short hand is the lowest rung the network can build, raised only where the routed flow needs a
    faster one. None: nothing to change."""
    lines = text.splitlines(True)
    heads = [l.split("#")[0].split()[:1] for l in lines]
    if any(h == ["hands"] for h in heads):
        return None
    for i, head in enumerate(heads):
        if head == ["route"]:
            lines.insert(i + 1, "hands           minimize                  # every short hand: the "
                                "lowest rung the network can build, raised where the flow needs "
                                "more (out/hands.txt)\n")
            return "".join(lines)
    return None


def _pole(text):
    """The build script's poles as ``any``: ``cover power --pole any`` and ``floorplan
    --bridge-power any`` (2.0.14), so the coverage step takes the pole the network can build, as
    ``--hand any`` does for hands, instead of the medium pole every template used to name. None:
    nothing to change."""
    lines = text.splitlines(True)
    changed = False
    for i, l in enumerate(lines):
        body, sep, note = l.partition("#")
        words = body.split()
        if words[:2] == ["cover", "power"]:
            new = re.sub(r"--pole\s+\S+", "--pole any", body) if "--pole" in body \
                else f"{body.rstrip()} --pole any"
        elif words[:1] == ["floorplan"]:
            new = re.sub(r"--bridge-power(\s+\S+)?", "--bridge-power any", body) \
                if "--bridge-power" in body else f"{body.rstrip()} --bridge-power any"
        else:
            continue
        if new.rstrip() != body.rstrip():
            lines[i] = new.rstrip() + (f"   {sep}{note}" if sep else "\n")
            changed = True
    return "".join(lines) if changed else None


def upgrade(run, sha, dry=False):
    cfg_path = os.path.join(run, "run.json")
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    sha = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", sha], stdout=subprocess.PIPE,
                         check=True, text=True).stdout.strip()
    old = cfg.get("toolkit_sha", "unknown")
    plan = [f"run {run}: toolkit {old} -> {sha}"]
    script = os.path.join(run, "game", "nauvis.build.fkb")
    new_script, changes = None, []
    if os.path.exists(script):
        with open(script, encoding="utf-8") as fh:
            text = fh.read()
        new_script = _script(text)
        if new_script:
            changes.append("report_bom --stock live after the diff")
        sized = _size(new_script or text)
        if sized:
            new_script = sized
            changes.append("size after elaborate (the build counts the n=auto rows)")
        last = _write_last(new_script or text)
        if last:
            new_script = last
            changes.append("write_layout just before apply (--to diff writes nothing)")
        stops = _stops(new_script or text)
        if stops:
            new_script = stops
            changes.append("stop_on no-route no-destination (no paste with a net unrouted)")
        hand = _hand(new_script or text)
        if hand:
            new_script = hand
            changes.append("route --hand any (the lowest hand the network can build)")
        step = _hands_step(new_script or text)
        if step:
            new_script = step
            changes.append("hands minimize after route (raised only where the flow needs it)")
        pole = _pole(new_script or text)
        if pole:
            new_script = pole
            changes.append("cover power --pole any, --bridge-power any (the pole it can build)")
    plan += [f"  replace {p} (old kept in .upgrade-{old}/)" for p in REPLACED
             if os.path.exists(os.path.join(run, p)) or p in (".toolkit", "bin", "docs")]
    if new_script:
        plan.append("  game/nauvis.build.fkb: " + "; ".join(changes)
                    + f" (old kept as nauvis.build.fkb.before-{sha})")
    helpers = not os.path.exists(os.path.join(run, "helpers"))
    if helpers:
        plan.append("  helpers/: the template's (the run has none)")
    plan.append(f"  run.json: toolkit_sha {sha}, host_toolkit /home/computah/factorio/fk-v5-{sha}")
    if dry:
        return plan
    src = os.path.join(run, f".kit-{sha}")
    claude = cfg.get("player") == "claude"
    _archive(sha, src, ("agent", "fkcore")
             + (tuple(f"kickoff/{name}" for name in LOOP) if claude else ())
             + (("kickoff/template/helpers",) if helpers else ()))
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
        for name in LOOP:
            shutil.copy(os.path.join(src, "kickoff", name), os.path.join(run, ".toolkit", name))
    os.makedirs(os.path.join(run, "bin"))
    shutil.copy(os.path.join(agent, "fk.py"), os.path.join(run, "bin", "fk.py"))
    shutil.copy(os.path.join(agent, "bin", "fk.cmd"), os.path.join(run, "bin", "fk.cmd"))
    shutil.copytree(os.path.join(agent, "docs"), os.path.join(run, "docs"))
    workers = cfg.get("workers")
    if workers and workers.get("backend") == "claude":
        old_worker = os.path.join(run, ".claude", "agents", "worker.md")
        if os.path.exists(old_worker):
            shutil.copy(old_worker, os.path.join(keep, "worker.md"))
        workers["brief_md5"] = write_worker(run, agent, workers.get("model", "inherit"),
                                            workers.get("brief", "worker-v1"))
    if helpers:
        shutil.copytree(os.path.join(src, "kickoff", "template", "helpers"),
                        os.path.join(run, "helpers"),
                        ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(os.path.join(agent, "prompts", f"{cfg.get('prompt', 'core-v1')}.md"),
                os.path.join(run, "AGENTS.md"))
    with open(os.path.join(run, "launch.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(dict(LAUNCH, first=LEAD_FIRST) if workers else LAUNCH, fh, indent=1)
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
  Toolkit 1.7 is in: a rebuild keeps what stands. The poles and roboports a build laid stay
  where the new design leaves them room, new ones go only where something new needs them, and
  old ones stay up until the new ones stand, so power and robots keep running (`cover power
  --fresh` lays them all anew). `fk build --to diff` is a dry run now: the design is written just
  before the paste. `fk fresh` also takes up a crafter's old product (and its chest's). `Lab`
  beside a multi-item chest takes its packs by one inserter, and a products belt into chests that
  take anything draws no CLOG. `MinerRow<drill=burner-mining-drill>` mines on the coal its belt
  brings. docs\\STRATEGY.md is what worked in earlier runs; helpers\\ is the place for reusable
  features (its README says how).
  It has 1.6: `n=auto` on a row leaves its count to the build (the new `size` step after
  `elaborate` gives it the fewest machines that meet your targets and asserts; out\\size.txt says
  why each count), and `Bus<belts=4, length, item, load=, tap=>` is Rory's bus as a template
  (`net iron1: smelt -> bus.load1`, `net fe: bus.tap1 -> gears`); docs\\LANGUAGE.md has both.
  It has 1.5: `fk plan ITEM RATE` (or `fk plan ITEM --machines N`) sizes a factory before
  you write it, every step of the recipe tree down to the drills; the world line says which pack
  the labs wait for; docs\\examples has compact-mall.fk and Rory's bus (bus4.json).
  It has 1.4.2: fk syncs by content (a background fk no longer undoes an edit), the world
  line names ghosts no powered roboport reaches (UNREACHED), no-water flags a dry offshore pump,
  a Literal reads a bare entity list, and `trash` on a requester sends back what it no longer
  asks for. It has 1.4.1: The routed rates in out\\report_rates.txt settle now (its first line says
  so), too-thin names only what runs short of a net's item, and `tier` never lowers a belt's tier
  (unless --downgrade) and allows only yellow unless you add --allow.
  It has 1.4: Machines that stand within 3 tiles of each other are now joined by an
  inserter, not a belt, whenever one machine feeds several (or several feed one): place a
  producer next to what takes its output and the router does the rest. docs\\examples\\early-mall.fk
  is an early-tier mall built that way (24 of its 30 nets are single inserters; 83 belts).
  It also has 1.3: The build can now say what your belts and inserters as laid let through: add
  a line `report_rates` after `route` in game\\nauvis.build.fkb, and out\\report_rates.txt gets
  the routed rates; a too-thin line names a belt lane, splitter or inserter that is too thin for
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
