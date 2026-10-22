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
| lanes: a net is one lane, so two nets can share a belt | in |
| throughput players lean on (`CAPACITY`) | in |
| side-loading smelter arrays | in |
| circuits and inserter limits in the source | its session waits to be started |
| the lead and worker player harness, Claude workers | in |
| `CLOG` goes in two ways only | in |

Buses (thick buses, the main bus, multi-lane nets) are a core feature of their own: release 2.1
(Rory, 2026-10-21). What of them already landed stays, the Bus template of 1.6 as it is; no new
bus work goes into 2.0.

## Lanes, throughput and side-loading smelter arrays

Rory (2026-10-21): "a net is one lane, so two nets can share a belt". `CORE-V2.md` has the
design and its marks; the player docs say it in LANGUAGE.md ("Two nets on one belt", the
`SmelterArray` row), TOOLKIT.md (the routed rates, `CAPACITY`, `LANE`) and EXAMPLES.md
(`shared-belt.fk`, `smelter-array.fk`).

- **Lanes in the language.** `lanes ore_ | fuel` puts two nets on one belt, the first on its left
  lane. Every consumer on either net gets one input belt of both (a SmelterRow fed ore and coal
  that way has one belt, its inserters picking both lanes). Two single-item nets on the two
  lanes of a belt are no sushi net and draw no `CLOG`: a lane that backs up holds only its own
  item. A net shares a belt with one other at most; fluids and buses have no lanes to share.
- **The router lays a pair as one job** (`fkcore/pairs.py`): each net from its drivers to its
  side of a join, both side-loaded into it (2-to-1 merges: each net onto its own lane, as at the
  head of each column of Rory's stack), then one route of both lanes to every consumer.
  `out\route.txt` says where the join is: `routed ore_|fuel: 2 -> 1, join 8,8 E (ore_ on the left
  lane, fuel on the right); ...`. The three parts are pinned or routed again together.
- **The record.** `net=ore_|fuel` on a belt (left|right), `ore_+fuel` on an inserter, `ore_|` for
  one lane only; a V1 `net=iron` means both lanes as before, so every layout stays valid.
  `connect` reads a carrier's nets from it (a net side-loaded onto its pair is no LEAK).
- **The rate model per lane.** The routed rates give each net of a shared belt its own lane, 7.5/s
  on yellow, its own critical connector and its own `CAPACITY` line.
- **`LANE`** (a warning, the lane-level LEAK, in the routed rates): items on a lane the layout gives
  other nets, nets on one lane that go to different sinks, items on the closed side of a belt
  side-loaded onto an underground. It replaces 1.x's `UG_SIDELOAD`, which warned on every such
  belt because V1 tracked no lanes. `fk look` says `WRONG_ITEM` lane by lane on a shared belt.
- **`SmelterArray<n, recipe>`**: Rory's smelter stack (his ghost, `games/v2-bench`) as a template
  that tiles to any count, `n=auto` included. Units 11 tiles wide, two columns of furnaces each,
  fed by one belt with ore on one lane and coal on the other, side-loaded at its foot; up to 24
  furnaces a column (a yellow lane of ore; 12 steel furnaces), then a unit more to the east, the
  coal shared down the chain of splitters. Plain inserters, as in his ghost. At his size it is his
  ghost entity for entity, but for the westmost unit's dead-end coal pass-through and a coal port
  at the east end. Routed, the benchmark holds: 48 furnaces make 15 plates/s with every furnace
  at full speed and every side-load joint at a required ratio of exactly 1.00; at 25 a column
  (`units=1`) `CAPACITY` names the ore and plate lanes at 7.81 of 7.5.
- **Throughput settled** (CORE-V2 "Open"): the inserter speeds are the catalog's
  (`rotation_speed`, `bulk`, `stack_size_bonus`: the game's 2.0.77 values), so the lane graph
  rates any inserter the catalog has; `fk rates FILE.fk` shows the routed section after the
  nominal one, on `FILE.fkp` as the last build laid it out (`--hand N`); the joint solve of
  several items on one lane waits for a design that needs it (2.0's put one item on a lane).
- **`fk merge`** names a merged factory's shared belts per net (`south/ore_|south/fuel`);
  `chests-to-net` and `net-to-chests` refuse a net that shares a belt, with what to do.
- Tests: `tests/test_lanes_pairs.py`, `tests/test_smelter_array.py` (36 in all); the full suite
  619.

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

- Circuits in the source (its session waits to be started).
- Side-load-aware routing, a name: side-loads as merges anywhere and lane separation (a splitter,
  then an underground side-load per net). 2.0's router side-loads only at a pair's join.
- Route patching, a named feature: a net whose ends change is still routed again as a whole (its
  session waits to be started).
- DeepSeek workers; daisy-chained labs and turrets.
