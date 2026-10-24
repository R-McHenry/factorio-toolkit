# Toolkit 2.0.13: the player's effort level

Rory, 2026-10-24: "lets try a new game with opus low effort". The players had run at Claude Code's
default effort.

- `claude_loop.py --effort LEVEL` passes `--effort` to each round's claude process, and the loop's
  start line names it.
- `new_run.py --effort` and `kickoff-v1.ps1 -Effort` write it into the run's play.cmd, so the
  watchdog's restarts keep it.
