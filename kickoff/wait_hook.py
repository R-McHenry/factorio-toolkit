"""wait_hook.py RUN: a PreToolUse hook that blocks shell waits (Rory, 2026-10-23: "dont wait" and
wait commands are blocked; 2026-10-24: `fk wait` is the one wait, from a fixed budget).

A Bash, PowerShell or Monitor command that sleeps (`sleep`, `Start-Sleep`, a loop of short sleeps)
or waits another way (`timeout N`, `Wait-Job`, `fk build --wait`; 3.0) is denied, and the reason
the player reads names the `fk wait` form for it. `fk wait` goes through: it waits
from the run's wait budget and asks first (agent/fk.py). claude_loop.py names this hook in every
Claude run's --settings (2.0.11). Each block is one line in RUN\\.loop\\wait-hook.log.
"""
import json
import os
import re
import sys
from datetime import datetime

#: 3.0: the hidden waits too, each with its budgeted form: `timeout N CMD` (fk wait 2m -- CMD),
#: PowerShell's Wait-Job / Wait-Process, and a foreground `fk build --wait` (fk wait build)
WAIT = re.compile(r"\bsleep\s+\d|\bStart-Sleep\b|\btimeout\s+(/t\s+)?\d|\bWait-(Job|Process)\b"
                  r"|\bfk\s+build\b[^\n|;&]*--wait\b", re.I)
REASON = ("Use fk wait: fk wait 90s, fk wait build (the background build's end), "
          "fk wait 2m -- COMMAND (a command with a cap).")


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if data.get("tool_name") not in ("Bash", "PowerShell", "Monitor"):
        return 0
    command = (data.get("tool_input") or {}).get("command") or ""
    if not WAIT.search(command):
        return 0
    if len(sys.argv) > 1:
        try:
            with open(os.path.join(sys.argv[1], ".loop", "wait-hook.log"), "a",
                      encoding="utf-8") as f:
                who = "worker" if data.get("agent_id") else "player"
                f.write(f"{datetime.now():%H:%M:%S} {who}: {' '.join(command.split())[:160]}\n")
        except OSError:
            pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": REASON}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
