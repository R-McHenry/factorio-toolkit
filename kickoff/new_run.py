"""new_run: make a V1 player run folder. This is the kickoff's laptop side, drafted in v5; wiring it
into C:\\fk-player and the host's kickoff waits for Rory's go.

    python kickoff/new_run.py RUN_DIR [--prompt core-v1] [--sha HEAD]
        [--host computah-ct --host-root /home/computah/factorio/v1-runs]
        [--local --rcon-port P --pw-file F --script-output D]     (a laptop test server)
        [--player claude --workers claude [--worker-model inherit]]   (a lead and its workers)

RUN_DIR gets:
  AGENTS.md            the brief (agent/prompts/<prompt>.md), GOAL.md, FRICTION.md,
                       REMINDER.md (a line or two every round's message ends with)
  docs/                TOOLKIT.md, LANGUAGE.md, EXAMPLES.md (agent/docs)
  bin/fk.cmd, fk.py    the agent's one command (agent/)
  .toolkit/fkcore/     the toolkit at SHA (git archive): the design steps run on the laptop
  game/                the game codebase (kickoff/template/game): the world design (one plot),
                       the surface, the build script, the base's file with the reactor and the kit
                       in it
  helpers/             the player's reusable features (kickoff/template/helpers, 1.7: Rory,
                       2026-10-21, helpers grow as a library, not a pile of one-off scripts)
  run.json             where the game is: host, host_game, host_toolkit, the toolkit's sha, the
                       brief and its md5, the start time
  launch.json          for C:\\fk-player\\launch.ps1: the preflight command (one that reaches
                       the game) with the text its output must hold, and the first message
  CLAUDE.md            with --player claude: the rules for a Claude Code session playing in this
                       folder (it reads CLAUDE.md, not AGENTS.md; Rory, 2026-10-20: an Opus agent
                       plays directly, no DeepSeek)
  play.cmd             with --player claude: starts the goal loop (.toolkit/claude_loop.py and
                       its hook claude_hook.py, from SHA) for this folder; kickoff-v1.ps1 opens it.
                       The loop starts .toolkit/watchdog.py, which opens it again when the loop
                       dies (2.0.12), and takes the run's stats every 5 game minutes with
                       .toolkit/stats_sample.py into game/out/stats (2.1)
  NOTES.md             with --notes FILE: what the players before wrote down for the next one
                       (kickoff-v1.ps1 passes the newest run's NOTES.md)
  .claude/agents/worker.md
                       with --workers claude (2.0: Rory, 2026-10-21, a lead player plus worker
                       players): Claude Code's project subagent, the worker brief
                       (agent/prompts/worker-v1.md) as its body. The player is the lead (brief
                       agent/prompts/lead-v1.md unless --prompt says otherwise): it hands each
                       design or in-game action to a worker and reads back its short report, so
                       its own conversation stays short. reports/ is where workers put longer
                       findings.

Everything comes from the toolkit at SHA (git archive: the brief, the docs, bin, the template and
fkcore), so a run is what that commit says, whatever the working tree holds. The toolkit is
pinned per run, on both sides, so files a running session uses never change under it. On the
host the run needs the toolkit at SHA in /home/computah/factorio/fk-v5-<sha> (deploy it with
`git archive`) and the game codebase in host_game (kickoff-v1.sh makes it); fk's first command
pulls it. Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
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


def _archive(sha, dest, paths=("fkcore",)):
    tar = subprocess.run(["git", "-C", ROOT, "archive", "--format=tar", sha] + list(paths),
                         stdout=subprocess.PIPE, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        t.extractall(dest, filter="data")


#: what launch.ps1 sends: a preflight that reaches the game (stats: a free read) and the first turn
LAUNCH = {
    "preflight": "fk stats",
    "expect": "stats nauvis",
    "first": ("Play Factorio as your AGENTS.md describes.\n\n"
              "The base works, you can get started.\n\n"
              "You're free to act: no permission needed and no finished plan needed. Get something "
              "small running early (docs\\EXAMPLES.md has a few that build cleanly), then grow it."),
}


#: what a lead player is sent first (2.0): the same start, said to the one who hands out the work
LEAD_FIRST = ("Lead the Factorio run as your AGENTS.md describes.\n\n"
              "The base works, you can get started.\n\n"
              "You're free to act: no permission needed and no finished plan needed. Start a worker "
              "on something small that runs early (docs\\EXAMPLES.md has a few that build cleanly), "
              "then grow it.")

#: the worker (2.0): a Claude Code project subagent. It runs in the lead's permission mode (auto),
#: spawns no workers of its own, and reads no CLAUDE.md: its brief is the file's body
WORKER = """---
name: worker
description: One short, well-scoped task in this Factorio run - build a piece with fk, change something in the game, find something out or measure it. It works in this folder and reports back what it learned (numbers, what worked, what didn't, what it saw). Give it the task, where it happens, what done looks like, and what it needs to know.
model: {model}
disallowedTools: Agent
omitClaudeMd: true
---

"""


def write_worker(run, agent, model="inherit", brief="worker-v1"):
    """``<run>/.claude/agents/worker.md`` from ``agent/prompts/<brief>.md`` under ``agent`` (an
    archive of the toolkit). -> the brief's md5."""
    with open(os.path.join(agent, "prompts", f"{brief}.md"), encoding="utf-8") as fh:
        body = fh.read()
    folder = os.path.join(run, ".claude", "agents")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "worker.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(WORKER.format(model=model) + body)
    return hashlib.md5(body.encode("utf-8")).hexdigest()


#: a Claude Code player's goal loop and what it runs, copied into the run's .toolkit: its hooks,
#: (2.0.12) the watchdog the loop starts, which starts play.cmd again when the loop dies, and
#: (2.1) the stats sampler. The game's side of the run stats needs nothing here: a new map starts
#: from the fk-play scenario (kickoff-v1.sh), whose fk_stats.lua records every 5 game minutes
LOOP = ("claude_loop.py", "claude_hook.py", "wait_hook.py", "watchdog.py", "stats_sample.py")

#: a Claude Code player's goal loop, in its own window
PLAY = """@echo off
title Factorio player (Claude) - {name}
python "{loop}" "{run}"{args}
echo.
echo The player loop has stopped (play.log says why).
pause
"""


#: a Claude Code player's own file: it reads CLAUDE.md in its folder
CLAUDE = """# Your Factorio run

`AGENTS.md` is your brief: read it first, then `NOTES.md` if there is one, then `docs\\FAIR-PLAY.md`
(the rules), `docs\\STRATEGY.md`, `docs\\BUILDING.md` (the base's layout) and `docs\\TOOLKIT.md`.

`fk` is your command: `bin\\fk.cmd <command>` in PowerShell, or `python bin/fk.py <command>` in
Git Bash.
"""


def make(run, prompt="core-v1", sha="HEAD", host="computah-ct",
         host_root="/home/computah/factorio/v1-runs", local=None, player="deepseek", notes=None,
         workers=None, worker_model="inherit", effort="", pack=None):
    if os.path.exists(run) and os.listdir(run):
        raise SystemExit(f"new_run: {run} exists and is not empty")
    if workers not in (None, "claude"):
        raise SystemExit(f"new_run: --workers {workers}: only claude workers are built (DeepSeek waits)")
    if workers and player != "claude":
        raise SystemExit("new_run: workers are Claude Code subagents: they need --player claude")
    sha = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", sha], stdout=subprocess.PIPE,
                         check=True, text=True).stdout.strip()
    src = os.path.join(run, ".kit")
    _archive(sha, src, ("agent", "kickoff/template")
             + ((f"kickoff/template-{pack}",) if pack else ())
             + (tuple(f"kickoff/{name}" for name in LOOP) if player == "claude" else ()))
    agent = os.path.join(src, "agent")
    brief = os.path.join(agent, "prompts", f"{prompt}.md")
    if not os.path.exists(brief):
        raise SystemExit(f"new_run: no brief agent/prompts/{prompt}.md at {sha}")
    shutil.copy(brief, os.path.join(run, "AGENTS.md"))
    # 3.0: REMINDER.md rides on every round's message (claude_loop); the run's own, to edit
    for name in ("GOAL.md", "FRICTION.md", "REMINDER.md"):
        if os.path.exists(os.path.join(agent, "run", name)):
            shutil.copy(os.path.join(agent, "run", name), os.path.join(run, name))
    if notes:
        shutil.copy(notes, os.path.join(run, "NOTES.md"))
    shutil.copytree(os.path.join(agent, "docs"), os.path.join(run, "docs"))
    os.makedirs(os.path.join(run, "bin"))
    shutil.copy(os.path.join(agent, "fk.py"), os.path.join(run, "bin", "fk.py"))
    shutil.copy(os.path.join(agent, "bin", "fk.cmd"), os.path.join(run, "bin", "fk.cmd"))
    _archive(sha, os.path.join(run, ".toolkit"))
    shutil.copytree(os.path.join(src, "kickoff", "template", "game"), os.path.join(run, "game"),
                    ignore=shutil.ignore_patterns("out"))
    if pack:   # the pack's overlay (kickoff/template-PACK): its game files over the template's
        over = os.path.join(src, "kickoff", f"template-{pack}")
        shutil.copytree(os.path.join(over, "game"), os.path.join(run, "game"), dirs_exist_ok=True)
        with open(os.path.join(over, "DROP"), encoding="utf-8") as fh:
            for drop in fh.read().split():
                os.remove(os.path.join(run, "game", drop))
    shutil.copytree(os.path.join(src, "kickoff", "template", "helpers"),
                    os.path.join(run, "helpers"), ignore=shutil.ignore_patterns("__pycache__"))
    if player == "claude":
        loop = os.path.join(run, ".toolkit", "claude_loop.py")
        for name in LOOP:
            shutil.copy(os.path.join(src, "kickoff", name), os.path.join(run, ".toolkit", name))
        with open(os.path.join(run, "play.cmd"), "w", encoding="ascii", newline="\r\n") as fh:
            fh.write(PLAY.format(name=os.path.basename(os.path.abspath(run)), loop=os.path.abspath(loop),
                                 run=os.path.abspath(run),
                                 args=f" --effort {effort}" if effort else ""))
    worker_md5 = None
    if workers:
        worker_md5 = write_worker(run, agent, worker_model)
        os.makedirs(os.path.join(run, "reports"))
    shutil.rmtree(src)
    with open(os.path.join(run, "launch.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(dict(LAUNCH, first=LEAD_FIRST) if workers else LAUNCH, fh, indent=1)
    if player == "claude":
        with open(os.path.join(run, "CLAUDE.md"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(CLAUDE)
    name = os.path.basename(os.path.abspath(run))
    with open(os.path.join(run, "AGENTS.md"), "rb") as fh:
        md5 = hashlib.md5(fh.read()).hexdigest()
    cfg = {"prompt": prompt, "prompt_md5": md5, "toolkit_sha": sha, "player": player,
           "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if pack:
        cfg["pack"] = pack
    if workers:
        cfg["workers"] = {"backend": workers, "model": worker_model, "brief": "worker-v1",
                          "brief_md5": worker_md5}
    if notes:
        cfg["notes_from"] = os.path.abspath(notes)
    if local:
        cfg.update(host="local", env=local)
    else:
        cfg.update(host=host, host_game=f"{host_root}/{name}/game",
                   host_toolkit=f"/home/computah/factorio/fk-v5-{sha}")
    with open(os.path.join(run, "run.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(cfg, fh, indent=1)
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("run")
    ap.add_argument("--prompt", help="the brief, agent/prompts/NAME.md (default core-v1, or "
                                      "lead-v1 with --workers)")
    ap.add_argument("--sha", default="HEAD")
    ap.add_argument("--host", default="computah-ct")
    ap.add_argument("--host-root", default="/home/computah/factorio/v1-runs")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--player", default="deepseek", choices=("deepseek", "claude"))
    ap.add_argument("--rcon-port")
    ap.add_argument("--pw-file")
    ap.add_argument("--script-output")
    ap.add_argument("--notes", help="a NOTES.md to start the run with (the last player's)")
    ap.add_argument("--workers", choices=("none", "claude"), default="none",
                    help="claude: the player leads, Claude Code subagents work (2.0)")
    ap.add_argument("--worker-model", default="inherit",
                    help="the workers' model: inherit (the lead's), sonnet, opus or a model id")
    ap.add_argument("--effort", default="", help="the Claude player's --effort (low, medium, high, ...)")
    ap.add_argument("--pack", help="a mod pack: kickoff/template-PACK over the template (seablock)")
    a = ap.parse_args(argv)
    workers = None if a.workers == "none" else a.workers
    prompt = a.prompt or ("lead-v1" if workers else "core-v1")
    local = None
    if a.local:
        local = {"FK_RCON_PORT": a.rcon_port, "FK_RCON_PW_FILE": a.pw_file,
                 "FK_SCRIPT_OUTPUT": a.script_output}
    cfg = make(a.run, prompt, a.sha, a.host, a.host_root, local, a.player, a.notes, workers,
               a.worker_model, a.effort, **({"pack": a.pack} if a.pack else {}))
    print(json.dumps(cfg, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
