"""tools/branches.py: where the toolkit stands, for a session's first minute (3.1).

Prints main's sha, version and tag; every branch with commits not on main, how many and how old;
every worktree and whether it is dirty; and whether ``..\\STATE.md`` is older than main's last
tag. Read-only. Run it from anywhere::

    python tools/branches.py [--repo PATH]

REVIEW-3.0 (2026-11-08): 3.0 sat unmerged for a week because nothing announced it. This does.
Stdlib only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def git(repo, *args):
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=False)
    return out.stdout.strip()


def age(ts):
    then = dt.datetime.fromtimestamp(int(ts))
    d = dt.datetime.now() - then
    h = d.days * 24 + d.seconds // 3600
    return f"{d.days} d" if h >= 48 else f"{h} h"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=os.path.dirname(HERE))
    a = ap.parse_args(argv)
    repo = os.path.abspath(a.repo)
    sha = git(repo, "rev-parse", "--short", "main")
    tag = git(repo, "describe", "--tags", "--abbrev=0", "main")
    init = git(repo, "show", "main:fkcore/__init__.py")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', init)
    version = m.group(1) if m else "?"
    head_branch = git(repo, "branch", "--show-current")
    print(f"main {sha}  version {version}  last tag {tag}  (this checkout: {head_branch or 'detached'})")

    print("\nbranches with commits not on main:")
    any_ahead = False
    for line in git(repo, "for-each-ref", "--format=%(refname:short) %(committerdate:unix)",
                    "refs/heads").splitlines():
        name, ts = line.rsplit(" ", 1)
        if name == "main":
            continue
        ahead = git(repo, "rev-list", "--count", f"main..{name}")
        if ahead and int(ahead) > 0:
            any_ahead = True
            subject = git(repo, "log", "-1", "--format=%s", name)
            print(f"  {name:36} +{ahead:>3}  {age(ts):>5} old  {subject[:60]}")
    if not any_ahead:
        print("  none")

    print("\nworktrees:")
    wt, branch = None, None
    for line in git(repo, "worktree", "list", "--porcelain").splitlines() + [""]:
        if line.startswith("worktree "):
            wt = line.split(" ", 1)[1]
        elif line.startswith("branch "):
            branch = line.split(" ", 1)[1].replace("refs/heads/", "")
        elif line == "" and wt:
            if "/notes/pin-" not in wt.replace("\\", "/"):
                dirty = len(git(wt, "status", "--short").splitlines())
                mark = f"DIRTY {dirty}" if dirty else "clean"
                print(f"  {mark:9} {branch or 'detached':28} {wt}")
            wt, branch = None, None

    state = os.path.join(os.path.dirname(repo), "STATE.md")
    if os.path.exists(state):
        head = open(state, encoding="utf-8").readline().strip()
        tag_ts = git(repo, "log", "-1", "--format=%ct", tag) if tag else "0"
        state_ts = int(os.path.getmtime(state))
        stale = tag_ts and int(tag_ts) > state_ts
        print(f"\nSTATE.md: {head}" + ("  <- OLDER than main's last tag; update it" if stale else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
