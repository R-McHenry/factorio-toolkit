# v5: the Factorio toolkit (development)

For sessions that work on the toolkit or the player harness. Players don't read this: each run in
`C:\fk-player\runs\<run>` has its own CLAUDE.md, brief and docs.

## What is where

- **Specs:** CORE.md (V1) and CORE-V2.md (lanes and throughput).
- **Rory's decisions:** `..\assessment-20261021\ASSESSMENT.md`, under "Decided with Rory".
- **`fkcore/`:** the core.
- **`agent/`:** what players get. `prompts/` holds the briefs (lead, worker, single player) and
  `docs/` the player docs.
- **`kickoff/`:** new runs (new_run.py, kickoff-v1), the player loop (claude_loop.py,
  claude_hook.py) and live upgrades (upgrade_run.py).
- **The rest:** `scenario/fk-play` (the lab), `tools/laptop_server.py` (a test server), and
  `games/` (paper games).

## What players get

- **FAIR-PLAY.md:** the game's rules, the only rules a player is given.
- **STRATEGY.md:** advice with reasons.
- **TOOLKIT.md, LANGUAGE.md and EXAMPLES.md:** how the toolkit works.
- **The briefs** point to these docs and give facts and tips, never rules or blockers.

A change to the game's rules goes in FAIR-PLAY.md and nowhere else.

## Building it

- **Tests:** `python -m unittest discover -s tests -t .` from this folder takes about 100 s, so run
  it in the background. Stdlib only.
- **Core ideas:**
  - a net is a declared object (name, items, drivers -> consumers), and machines join nets;
  - one source owns every tile;
  - the only tool write is a named paste;
  - checks warn, never gate;
  - each tool consumes the previous one's output;
  - power is its own step.
- **Versioning:** releases are the only version numbers, and the major is the design generation.
  1.x was V1, 2.0 is V2, buses are 2.1. A feature keeps a name until it ships. Each release gets a
  `vX.Y` tag and a `docs/RELEASE-X.Y.md`.

## Runs and the game

- **Deploys:** the host gets `/home/computah/factorio/fk-v5-<sha>`, never overwritten, and each
  run pins its own toolkit.
- **A live run changes only through an upgrade** (`kickoff/upgrade_run.py`):
  - toolkit and harness bug fixes go in at a quiet moment and are reported afterwards;
  - anything that would change Rory's rules, a run's direction or a brief's substance goes to the
    supervising session first;
  - new runs and retiring maps are Rory's call.
- **Check-ins:** take stale constraints out of a run's notes and goal, and give the next step
  forward.
- **Game calls:** take 5 s at most, and after a cancelled remote call, kill what it started. The
  host's CPU is shared with the server, so heavy compute stays on the laptop. Test on a laptop
  server, not the live game.
- **RCON and the console:** never register handlers or commands through them; it once made every
  save unjoinable.
- **DeepSeek:** never read its reasoning (session.jsonl, dsh-home, .ggc-transcripts).

## Working with Rory

Decide what his rules already cover, keep the work rolling and report with numbers. Follow the
agreed plan, and report new findings rather than detouring on them.
