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
| circuits and inserter limits in the source | in (branch `claude/circuits-263046`) |
| the lead and worker player harness, Claude workers | in |
| `CLOG` goes in two ways only | in |

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

## STRATEGY.md and the versions

- `docs\STRATEGY.md` is Rory's revised guide, as is: no run history, pace figures computed from
  the tech tree, the mall as the wheels the rest of the game runs on, "more, then enough", wood
  poles, overproduction as a mall problem, building with the future in mind, defensive
  minefields. The brief points to it as Rory's advice on playing well.
- `CORE-V2.md`, "The versions": releases in the table, buses and multi-lane nets as release 2.1,
  "side-load-aware routing" a name; `SHARED_BELT` (an earlier spec's lane-pair check, never
  built) is superseded by V2 lanes, in CORE.md too.

## Circuits in the source

Rory (2026-10-21): "circuit wiring in the source, with all circuit and logic conditions in the .fk
code, inserter limits included", and "Recipe-switch smarts (inserters that don't carry the wrong
item) belong in circuits in the game, not in scripted toolkit actions". The draft was
`drafts\reactor-1.1` (CIRCUITS-1.1.md, plant.fk), with fnet's rules: one wire net is one colour,
a signal is declared (pinned or left to the build), checks warn and never gate. `LANGUAGE.md`,
"Circuits", has the syntax; `fkcore.circuits` is the code.

- **Limits at the makers replace the mall scripts.** Both lead runs set their mall's limits by Lua
  after every rebuild (`malllimits.lua`, 2005 and 2039), and the 2039 one fixed chest bars by hand
  ("a limit change is not re-pasted"). Now `keep=N` on a maker puts a logistic condition (the
  network holds fewer than N of the product) on every inserter that takes its product into a
  chest or onto a belt that ends in one; `fill=N` counts in the chest it fills straight, by a red
  wire. They are real limits and quiet no `CLOG`: `limited` still does that, written separately.
  `fill=N` is also the one-off crafter's stop at N the 2039 worker asked for (`count=N`: 86 gears
  for 50, 38 furnaces for 8).
- **Recipe-switch safety in the game.** `guard` on a crafter: it reads its recipe's ingredients
  onto a red wire to its input inserters, which set their filters from them, so a recipe switched
  in the game changes what they carry (the 2039 run's inserters held the old item and stalled a
  switched crafter many times).
- **Wires, signals, conditions.** `signal`, `wire NAME red|green: drivers -> consumers`, `when` on
  a net (every inserter and pump of its route) or on a machine, reading a wire, `network.ITEM` or
  an instance's own signals; `Constant<signals=...>`; a chest's contents and a belt's reading;
  `behave` blocks (`require` checked with catalog numbers, `GATED` without a cycle). New checks:
  `SIGNAL`, `WIRE`, `WIRE_REACH`, `WIRE_LEAK`, `GATED`, `REQUIRE`, `LIMIT`, `GUARD`.
- **The record.** The .fkp's entity lines carry `if=`, `logistic=`, `read=`, `filter=`,
  `signals=`, and `wire` / `w` lines its wires (the draft's format); the codec writes them as the
  blueprint's `control_behavior` and wires and reads them back exactly. They are laid again from
  the source on every build, just before the floorplan.
- **A changed setting reaches the world.** The record of what the applies pasted (`out\own`)
  keeps a signature of each entity's circuit settings and chest bar; an apply orders out an
  entity whose settings changed, and the paste lays it fresh with the new ones. A record from
  before 2.0 has none, so nothing is laid fresh until the next apply writes them.
- **The worked example.** `games\plant`: plant.fk (the starter reactor and its fuel saver, with
  `Reactor`, `HeatExchanger`, `SteamTurbine`, `Chest<plain>`, a heat net by contact) builds
  offline, entity for entity and wire for wire, into plant-w3.json, the blueprint the kickoff
  pastes: 28 entities, 9 wires (`tests\test_plant.py`).
- **Not checked in the game yet:** the 2.0 blueprint keys for a logistic condition, set filters
  and read ingredients, and the game's comparators for `<=` / `>=` / `!=` (written as the
  blueprint string format has them). The reactor's and the plain inserter's settings are exactly
  plant-w3.json's. A lab check on a laptop server settles the rest.

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

- Lanes, throughput and side-loading smelter arrays (their session waits to be started).
- From circuits: combinators beyond the constant one (fnet modules, a named feature), wires
  routed through poles, `behave` states in `fk look` (EXPECTED), a gated net's cycle in the rate
  model, a storage chest's filter, a first load of fuel for self-fuelling burner drills.
- Route patching, a named feature: a net whose ends change is still routed again as a whole (its
  session waits to be started).
- DeepSeek workers; daisy-chained labs and turrets.
