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
  run.json             where the game is: host, host_game, host_toolkit, the toolkit's sha, the
                       brief and its md5, the start time

The toolkit is pinned per run, on both sides, so files a running session uses never change under
it. On the host the run needs the toolkit at SHA in /home/computah/factorio/fk-v5-<sha> (deploy it
with `git archive`) and the game codebase in host_game; fk's first command pulls, and the push
after it sends game/ there. Stdlib only.
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


def make(run, prompt="core-v1", sha="HEAD", host="computah-ct",
         host_root="/home/computah/factorio/v1-runs", local=None):
    if os.path.exists(run) and os.listdir(run):
        raise SystemExit(f"new_run: {run} exists and is not empty")
    sha = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", sha], stdout=subprocess.PIPE,
                         check=True, text=True).stdout.strip()
    agent = os.path.join(ROOT, "agent")
    brief = os.path.join(agent, "prompts", f"{prompt}.md")
    os.makedirs(run, exist_ok=True)
    shutil.copy(brief, os.path.join(run, "AGENTS.md"))
    for name in ("GOAL.md", "FRICTION.md"):
        shutil.copy(os.path.join(agent, "run", name), os.path.join(run, name))
    shutil.copytree(os.path.join(agent, "docs"), os.path.join(run, "docs"))
    os.makedirs(os.path.join(run, "bin"))
    for name in ("fk.py", "fk.cmd"):
        shutil.copy(os.path.join(agent, name if name == "fk.py" else os.path.join("bin", name)),
                    os.path.join(run, "bin", name))
    _archive(sha, os.path.join(run, ".toolkit"))
    shutil.copytree(os.path.join(HERE, "template", "game"), os.path.join(run, "game"),
                    ignore=shutil.ignore_patterns("out"))
    name = os.path.basename(os.path.abspath(run))
    with open(brief, "rb") as fh:
        md5 = hashlib.md5(fh.read()).hexdigest()
    cfg = {"prompt": prompt, "prompt_md5": md5, "toolkit_sha": sha,
           "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
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
    ap.add_argument("--rcon-port")
    ap.add_argument("--pw-file")
    ap.add_argument("--script-output")
    a = ap.parse_args(argv)
    local = None
    if a.local:
        local = {"FK_RCON_PORT": a.rcon_port, "FK_RCON_PW_FILE": a.pw_file,
                 "FK_SCRIPT_OUTPUT": a.script_output}
    cfg = make(a.run, a.prompt, a.sha, a.host, a.host_root, local)
    print(json.dumps(cfg, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
