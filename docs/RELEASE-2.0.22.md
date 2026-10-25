# Toolkit 2.0.22: a fresh run starts from the brief, not from the last player's playbook

Rory, 2026-10-25: "lets clean up some of the leftovers that previous runs have been writing to new
ones so that our intent is the main thing the fresh agent sees".

The 1035 run started with the 0317 run's `NOTES.md`, and those notes argued for exactly the behaviour
the new brief is against: "The third lab and several cells were repeatedly traded against each other",
"Next player: feed its two plate requesters and finish [the compact mall]". Its round-1 goal then
planned to take its own mine apart to recover five inserters.

- **No inherited `NOTES.md`.** `kickoff-v1.ps1` no longer passes the newest earlier run's notes to the
  new run: a run starts from the brief and the docs (`--notes` is still there for a deliberate carry).
- **The seed `GOAL.md` says the ramp:** look at the stage the base is at, then build the next step —
  about twice the last, only when the last runs, small enough that what the base makes can feed it.
  It no longer says "grow the factory ... pick the next piece".
- **The template's `helpers/__pycache__` is gone**: the run template is only what a run should start
  with.

A fresh run on this commit has: the brief (chests first = no belts; the ramp; the order-of-magnitude
question; robots light), the docs, the examples, the kit's world, and none of the previous players'
conclusions.
