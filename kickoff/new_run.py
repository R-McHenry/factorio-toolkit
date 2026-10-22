"""new_run: make a V1 player run folder. This is the kickoff's laptop side, drafted in v5; wiring it
into C:\\fk-player and the host's kickoff waits for Rory's go.

    python kickoff/new_run.py RUN_DIR [--prompt core-v1] [--sha HEAD]
        [--host computah-ct --host-root /home/computah/factorio/v1-runs]
        [--local --rcon-port P --pw-file F --script-output D]     (a laptop test server)

RUN_DIR gets:
  AGENTS.md            the brief (agent/prompts/<prompt>.md), GOAL.md, FRICTION.md
  docs/                TOOLKIT.md, LANGUAGE.md, EXAMPLES.md (agent/docs)
  bin/fk.cmd, fk.py    the agent's one command (agent/)
  .toolkit/fkcore/     the toolkit at SHA (git archive): the design steps run on the laptop
  game/                the game codebase (kickoff/template/game): the surface, the build script,
                       the plant
  helpers/             the player's reusable features (kickoff/template/helpers, 2.0: Rory,
                       2026-10-21, helpers grow as a library, not a pile of one-off scripts)
  run.json             where the game is: host, host_game, host_toolkit, the toolkit's sha, the
                       brief and its md5, the start time
  launch.json          for C:\\fk-player\\launch.ps1: the preflight command (one that reaches
                       the game) with the text its output must hold, and the first message
  CLAUDE.md            with --player claude: the rules for a Claude Code session playing in this
                       folder (it reads CLAUDE.md, not AGENTS.md; Rory, 2026-10-20: an Opus agent
                       plays directly, no DeepSeek)
  play.cmd             with --player claude: starts the goal loop (.toolkit/claude_loop.py and
                       its hook claude_hook.py, from SHA) for this folder; kickoff-v1.ps1 opens it
  NOTES.md             with --notes FILE: what the players before wrote down for the next one
                       (kickoff-v1.ps1 passes the newest run's NOTES.md)

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


#: a Claude Code player's goal loop, in its own window
PLAY = """@echo off
title Factorio player (Claude) - {name}
python "{loop}" "{run}"
echo.
echo The player loop has stopped (play.log says why).
pause
"""


#: a Claude Code player's own file: it reads CLAUDE.md in its folder
CLAUDE = """# Your Factorio run

`AGENTS.md` is your brief: read it first, then `NOTES.md` if there is one (what the players before
you wrote down), then `docs\\TOOLKIT.md`.

`fk` is your command: `bin\\fk.cmd <command>` in PowerShell, or `python bin/fk.py <command>` in
Git Bash.
"""


def make(run, prompt="core-v1", sha="HEAD", host="computah-ct",
         host_root="/home/computah/factorio/v1-runs", local=None, player="deepseek", notes=None):
    if os.path.exists(run) and os.listdir(run):
        raise SystemExit(f"new_run: {run} exists and is not empty")
    sha = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", sha], stdout=subprocess.PIPE,
                         check=True, text=True).stdout.strip()
    src = os.path.join(run, ".kit")
    _archive(sha, src, ("agent", "kickoff/template")
             + (("kickoff/claude_loop.py", "kickoff/claude_hook.py") if player == "claude" else ()))
    agent = os.path.join(src, "agent")
    brief = os.path.join(agent, "prompts", f"{prompt}.md")
    if not os.path.exists(brief):
        raise SystemExit(f"new_run: no brief agent/prompts/{prompt}.md at {sha}")
    shutil.copy(brief, os.path.join(run, "AGENTS.md"))
    for name in ("GOAL.md", "FRICTION.md"):
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
    shutil.copytree(os.path.join(src, "kickoff", "template", "helpers"),
                    os.path.join(run, "helpers"), ignore=shutil.ignore_patterns("__pycache__"))
    if player == "claude":
        loop = os.path.join(run, ".toolkit", "claude_loop.py")
        shutil.copy(os.path.join(src, "kickoff", "claude_loop.py"), loop)
        shutil.copy(os.path.join(src, "kickoff", "claude_hook.py"),
                    os.path.join(run, ".toolkit", "claude_hook.py"))
        with open(os.path.join(run, "play.cmd"), "w", encoding="ascii", newline="\r\n") as fh:
            fh.write(PLAY.format(name=os.path.basename(os.path.abspath(run)), loop=os.path.abspath(loop),
                                 run=os.path.abspath(run)))
    shutil.rmtree(src)
    with open(os.path.join(run, "launch.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(LAUNCH, fh, indent=1)
    if player == "claude":
        with open(os.path.join(run, "CLAUDE.md"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(CLAUDE)
    name = os.path.basename(os.path.abspath(run))
    with open(os.path.join(run, "AGENTS.md"), "rb") as fh:
        md5 = hashlib.md5(fh.read()).hexdigest()
    cfg = {"prompt": prompt, "prompt_md5": md5, "toolkit_sha": sha, "player": player,
           "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
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
    ap.add_argument("--prompt", default="core-v1")
    ap.add_argument("--sha", default="HEAD")
    ap.add_argument("--host", default="computah-ct")
    ap.add_argument("--host-root", default="/home/computah/factorio/v1-runs")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--player", default="deepseek", choices=("deepseek", "claude"))
    ap.add_argument("--rcon-port")
    ap.add_argument("--pw-file")
    ap.add_argument("--script-output")
    ap.add_argument("--notes", help="a NOTES.md to start the run with (the last player's)")
    a = ap.parse_args(argv)
    local = None
    if a.local:
        local = {"FK_RCON_PORT": a.rcon_port, "FK_RCON_PW_FILE": a.pw_file,
                 "FK_SCRIPT_OUTPUT": a.script_output}
    cfg = make(a.run, a.prompt, a.sha, a.host, a.host_root, local, a.player, a.notes)
    print(json.dumps(cfg, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
