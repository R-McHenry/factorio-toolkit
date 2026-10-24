# Toolkit 2.0.9: waiting is the last resort (Rory's hard rule)

Rory, 2026-10-23: "we also need to just have some hard rules about waiting. That just cannot be a go
to activity in any circumstance, whether a delay or waiting to complete. only after seeing that
there is no way to progress but wait can that ever be an option", and "that also includes loops with
short waits peppered in".

- **The player briefs, core-v1 and lead-v1,** each get a section, "Waiting is the last resort". It
  rules out sleeps, delays, waiting for a worker, build, layout, robots or background command to
  finish, and loops of short sleeps. While something runs, the player does something else that
  moves the game forward. Only when nothing else can move the game forward does it wait, on a
  condition with a short limit, never a fixed sleep.
- **The lead brief** has the 5-minute line folded into it: the loop still says when a lead has
  waited 5 minutes on its workers.
- **The worker brief** gets the same rule in three lines.
- **The Stop hook under test** (`C:\fk-player\notes\stop_hook.py`) says it in every nudge.
