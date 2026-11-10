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

- **Tests:** stdlib only, run from this folder. Run the modules that cover the change
  (`python -m unittest tests.test_x`), in the background when they take more than a few seconds.
  Never run the whole suite. Small fixes can share one release.
- **Main is the only integration point.** This folder stays checked out on `main`. A branch is
  merged within a day or two of its last commit, or `..\STATE.md` gets a dated line saying which
  branch, why it waits and who merges it. Release numbers are assigned on main at merge time, and
  whoever merges updates `..\STATE.md` in the same commit. Nothing (lab, run, host) deploys from a
  dirty tree: install from a commit and record its sha.
- **Start of a session:** `python tools/branches.py` prints main's version, every branch with
  commits not on main, dirty worktrees, and whether STATE.md is older than the last tag.
- **The merge set** runs in the background before every merge to main (about 2 minutes):
  test_route, test_route_cycle, test_route_policy, test_route_taps, test_route_promote,
  test_route_ground, test_route_units, test_steiner_split_tap, test_native, test_compile_once,
  test_compiled, test_design, test_flow, test_lab, test_lab_megabase, test_walk, test_golden,
  test_literal_ports, test_friction_30, test_circuits, test_cover, test_rail_signals,
  test_terrain, test_robots, test_robots_reach, test_terrain_flow, test_apply, test_sense,
  test_own, test_surface, test_placements, test_frame, test_hull, test_territory, test_layout,
  test_placer_mixed, test_connect, test_pair_ports, test_cleanpaste, test_pair_leak, test_gateway_link, plus the branch's own new tests.
- **Core ideas:**
  - a net is a declared object (name, items, drivers -> consumers), and machines join nets;
  - one source owns every tile;
  - the only tool write is a named paste;
  - checks warn, never gate;
  - each tool consumes the previous one's output;
  - power is its own step.
- **Versioning:** releases are the only version numbers, and the major is the design generation.
  1.x was V1, 2.0 is V2, buses are 2.1, and 3.0 is the build the player owns (step commands, the design
  database, each net routed once). A feature keeps a name until it ships. Each release gets a
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
