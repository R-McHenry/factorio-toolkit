# Toolkit 2.0.11: don't wait

Rory, 2026-10-23: "No stories about wait and crazy prose. Lets just give it something it can
understand, 'dont wait' and wait commands are blocked".

- `kickoff/wait_hook.py`, a PreToolUse hook in every Claude run's settings (claude_loop.settings),
  denies any Bash, PowerShell or Monitor command that sleeps (`sleep`, `Start-Sleep`, loops of short
  sleeps) or runs `fk wait`. The reason the player reads is "Don't wait.". Each block is a line in
  `.loop\wait-hook.log`. new_run and upgrade_run copy it into `.toolkit`.
- The briefs' waiting sections are now: "Don't wait. Wait commands are blocked." and "After a big
  step: look at it, check that it works, clean up or improve it, and plan the next things."
- TOOLKIT.md no longer lists `fk wait built`.
