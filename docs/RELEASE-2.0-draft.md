# Toolkit 2.0 (draft): V2 complete

The draft of the 2.0 release note. It grows as the round's pieces land on main. It becomes
`docs/RELEASE-2.0.md`, with `__version__` "2.0" and the tag `v2.0`, on the release that completes
the round (Rory, 2026-10-21: releases are the only version numbers, the major is the design
generation; `CORE-V2.md`, "The versions"). 1.7 (tagged, `docs/RELEASE-1.7.md`) already shipped the
round's first pieces: pin and patch, burner drills, `fk fresh` for crafters, labs from a chest,
mixed chests, helpers, STRATEGY.md and fair play in Rory's words. No new rules: checks warn, never
gate, and the briefs stay short.

| named feature in 2.0 | state |
|---|---|
| lanes: a net is one lane, so two nets can share a belt | its session waits to be started |
| throughput players lean on (`CAPACITY`) | the same session |
| side-loading smelter arrays | the same session |
| circuits and inserter limits in the source | its session waits to be started |
| the lead and worker player harness, Claude workers | in |
| `CLOG` goes in two ways only | in |
| route patching: a net with a new end keeps its route | in |

Buses (thick buses, the main bus, multi-lane nets) are a core feature of their own: release 2.1
(Rory, 2026-10-21). What of them already landed stays, the Bus template of 1.6 as it is; no new
bus work goes into 2.0.

## The lead and worker players (Claude workers)

Rory (2026-10-21): the next run is one run, all Claude, a Claude lead player with Claude worker
subagents. The lead plans, sets strategy and decides, and keeps its own conversation short; each
worker carries out one design or in-game action and reports back briefly. The overnight players'
conversations had grown to 500-800k tokens of context, so a round was slow and cost a few dollars.

- **Kickoff**: `kickoff-v1.cmd -Player claude -Workers claude` (`-WorkerModel sonnet` or a model
  id for the workers; by default they run on the lead's model). `new_run.py --workers claude`
  makes the run: the lead's brief `agent\prompts\lead-v1.md` as AGENTS.md, the worker as Claude
  Code's project subagent `.claude\agents\worker.md` (the brief `agent\prompts\worker-v1.md`,
  `model: inherit`, `disallowedTools: Agent`, `omitClaudeMd: true`), `reports\` for longer
  findings, run.json `workers`, and a first message for a lead.
- **The briefs**, short and without new rules. The lead's is the core brief turned to leading:
  how to give a worker a task (what, where, what done looks like, what it needs to know), that a
  worker runs in the background and its report wakes the lead, that builds go one at a time, and
  that Rory's chat reaches the lead only. The worker's is the core brief cut down to a task: the
  folder, how building works, fair play, the ways to get unstuck, and the short report.
- **Small worker tasks win** (Rory, 2026-10-21, decision 13): workers are tools that save the
  lead's context, not a way to hand off the game. The lead stays the player: it decides, designs
  and knows its base. Its brief gives short, well-scoped examples (build this, find out that,
  measure this) and the reasons; the worker's report says what it learned (numbers, what worked,
  what didn't, what it saw) and brings bigger choices back to the lead. The first lead run had
  one worker carry a whole red science block (crafting every part, then the build) for over half
  an hour while the lead waited and research stood idle.
- **The loop** (`claude_loop.py`): workers' tool calls show indented in play.log, each report as
  "worker completed (task; tokens, tool calls, minutes): report", and every turn of the lead's
  in one process as a "turn report". When the lead's context passes `--fresh-at` tokens (default
  200k, after at least 3 rounds) the next round asks it to bring NOTES.md and GOAL.md up to date,
  and the round after starts a fresh conversation from them (old ids in claude-sessions.txt).
  A worker's own background command finishing wakes the worker, not the lead, so a waiting lead
  still gets notes at once (the first lead run: such tasks marked it busy, and INBOX.md waited
  for the worker's report). A round past `--turn-cap` (120 min) ends at its next quiet moment
  instead of being stopped with its workers mid-task; the lead hears once that the round is
  past its cap, and only a round still busy `GRACE` (60) minutes later is stopped. No research
  (nothing queued) is the one world fact that is also a note, so it wakes a lead that waits on
  its workers, once each time it starts (the first lead run's queue ran out twice while the lead
  waited: 33 and 9 minutes of idle labs).
- **The hook** keeps Rory's chat, INBOX.md and the world line for the lead: inside a worker (its
  hook input names an `agent_id`) it takes nothing; the lead gets them at its own next shell
  command or Agent call.
- **One build at a time**: `fk build` takes a lock in the run folder, so a second worker's build
  waits for the first instead of pasting over it.
- Checked with the real `claude -p` (Claude Code 2.1.299, Haiku, no game): the project agent
  loads headless, a worker's Bash call reaches the hook with `agent_id` and `agent_type: worker`,
  the Agent tool launches it in the background ("Async agent launched"), and its report comes in
  a `task_notification` and wakes the lead in the same process. Tests: `tests\test_workers.py`.
- DeepSeek workers wait (Rory, 2026-10-21). The seam is run.json `workers.backend`; a Claude
  lead would only ever see a DeepSeek worker's final output.

## CLOG goes in two ways only

Rory (2026-10-21): no tool can tell in general whether a source is limited. A mixed net's `CLOG`
goes away in exactly two ways:

- the route is one inserter from the source straight into each sink, which takes only what that
  sink accepts (`connect.one_inserter`); the route step clears the line and says "one hand". A belt
  in between, or a second inserter (a chain, a hub chest), keeps it;
- the source writes the net `limited`, which only silences it. Actual limits (circuits, chest
  limits) are written separately.

Nothing else: 1.1's exemption for a net only requester chests drive is gone (a requester refills
what its belt takes), and so is 1.7's for a net into chests that take any item (a full chest stops
the belt). A products belt into one chest draws `CLOG` again, with `UNLIMITED` or `SUSHI_LIMIT`
beside it as in 1.7.

## Route patching: a net with a new end keeps its route

Rory (2026-10-21): "Pin what stands and make patch changes rather than regenerating the base ...
routing a new section into the old one, even as a bit of spaghetti, beats ripping everything
up." 1.7 kept the poles and roboports; 2.0 keeps the routes. Before, a net with one consumer added
was routed again as a whole, and the first lead run's players re-laid iron, coal and plates at
once: iron stood for 20 minutes.

- **Kept, patched or routed again.** `route --only stale` hands the router the committed route of
  every net none of whose ends moved (`NetJob.moved_ends`: a belt end on another tile, or a
  machine on other tiles; an end added or dropped is no move). `fkcore.connect` judges each one
  against the netlist as it is now. A route that joins every driver to every consumer, leaks
  nowhere and has no carrier that serves no end stands as it is. Any other keeps what still
  serves, takes up what serves no end any more (a dropped end's branch), and gets one branch per
  new end from the router's own search (`steiner`), on the router's ground:
  - a new consumer, off where every standing driver reaches: a dead-end belt run on, a splitter
    in place of a straight belt, or an inserter straight off a belt (or off a driver machine);
  - a new driver, into where it reaches every consumer: side-loaded onto a belt (never a curve,
    which a second input would straighten), into the back of a belt nothing feeds, or an
    inserter onto a belt.

  The judge checks the patch too: every pair joined, no LEAK, every tunnel paired. `out\route.txt`
  says `patched   iron: 1 -> 5, gears2.in1: a splitter in place of ~iron/b39, 6 belts, 4
  underground ends; 54 of 55 carriers kept`, or, when no branch fits or the judge refuses it,
  `stale     p: routed again: <why>`, and the net is laid anew as before. Fluid nets are kept or
  routed again, never patched.
- **The net's ends decide, not its name.** The first lead run changed `net packs: X -> lab` to
  `X -> px` and kept the name: the old route stood, the build said OK, and the long-handed
  inserter still fed the lab (`full_output` on X). The pinning compared where the route's ends
  stand, read from the new netlist on both layouts, so a sink that changed in place looked the
  same. Now the judge reads the committed route: `stale     packs: routed again: its committed
  route would LEAK: ~packs/i0 drops into lab/m0, which is not a consumer of packs`.
- **Numbers.** Redgreen with a gear row added (`gears2`: a consumer of iron and a driver of
  gear): 10 nets kept, 2 patched. Iron keeps 54 of its 55 carriers (one belt became the
  splitter), gear all 69, with the new row's belt (41 belts, 8 underground ends) side-loaded onto
  its trunk; 12 of 12 nets connected, no LEAK. Before, both nets were laid again, and the new
  gear route had 146 carriers, 43 of them where the old ones stood. An unchanged rebuild keeps
  every route in every game in `games\` (no net is patched for nothing).
- Tests: `tests\test_route.py` `PatchTest` (an assembler added keeps all 19 carriers of its net;
  a dropped end's branch goes; a patch that can't be laid falls back to the full route), and
  `tests\test_flow.py` (redgreen with a row added; the same-name sink change). TOOLKIT.md,
  "Rebuilds keep what stands", says so.

## STRATEGY.md and the versions

- `docs\STRATEGY.md` is Rory's revised guide, as is: no run history, pace figures computed from
  the tech tree, the mall as the wheels the rest of the game runs on, "more, then enough", wood
  poles, overproduction as a mall problem, building with the future in mind, defensive
  minefields. The brief points to it as Rory's advice on playing well.
- `CORE-V2.md`, "The versions": releases in the table, buses and multi-lane nets as release 2.1,
  "side-load-aware routing" a name; `SHARED_BELT` (an earlier spec's lane-pair check, never
  built) is superseded by V2 lanes, in CORE.md too.

## From the first lead run's FRICTION.md and RETRO.md

- **`fk merge` keeps a module file other plots still place.** Merging `relay` into `south` took
  `relays.fk` away from `relay2` and `relay3`, twice, and the next build stopped with INVARIANT.
  Merging into a factory of the same name again names the new module apart (`CoalFactory2`)
  instead of wrapping `CoalFactory` in another `CoalFactory`.
- **`fk research` queues prerequisites.** Each technology goes after its unfinished prerequisites,
  queued with it in order (a queued one counts as on its way); a trigger technology in the way is
  named with what fires it. `--first` puts them at the front of the queue. Checked on a laptop
  test server (Factorio 2.0.77).
- **`fk fresh` names what waiting ghosts compete for.** It takes up stale carriers through the
  robots, which bring them back to storage; when more ghosts of a kind wait than the network
  holds, those ghosts may get them first, and the lines say so (the shop's two fast inserters went
  to the mall's ghosts, and the shop stood GHOST SHORT, unable to make inserters).
- **Docs:** a requester drives a net, a provider or storage chest only ends one; a product's chest
  is best a provider, since robots put any leftovers into the nearest storage chest.

## Not in 2.0 yet

- Lanes, throughput and side-loading smelter arrays; circuits in the source (their sessions wait
  to be started).
- DeepSeek workers; daisy-chained labs and turrets.
