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
| lanes: a net is one lane, so two nets can share a belt | its session runs |
| throughput players lean on (`CAPACITY`) | the same session |
| side-loading smelter arrays | the same session |
| circuits and inserter limits in the source | in |
| the lead and worker player harness, Claude workers | in |
| the lead plans ahead: `fk stage`, the horizon, Rory's 5-minute wait | in |
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

## The lead plans ahead: `fk stage`

Rory (2026-10-21/22, `assessment-20261021\PLAN-AHEAD.md`): the lead should not stay in the present
the way workers do. Rather than wait for a worker or a process to finish, it designs and plans the
later stages straight away, and adjusts the plan as workers report back; adjusting the plan is the
key use case. The first lead run's lead waited about 35 minutes on each of two builders, a mall
design took 40 minutes in a crowded plot, and research ran dry four times. Rory: "in the next run
I don't want the lead waiting so much", with an absolute maximum wait of 5 minutes.

- **The plan in git, through `fk stage`** (Rory's decisions 1-3: a line of stages first, a stage is
  one buildable and testable piece, git with a wrapper). `main` is what is built; `plan` is one
  commit per stage on top of it, the message the stage's spec (goal, needs, rates, test, an
  optional milestone) with a `Stage: N` trailer, so numbers survive reorders. Commands: `list`,
  `check N`, `next [--apply]`, `done [N]`, `rebase`, `edit N`, `insert`, `drop N`, `reorder N`,
  and `horizon` (one line, for the loop). Each rewrite tags the old plan `plan/rev-N`.
- **Where it lives.** A run's `game\` was no git repository: `fk` keeps it in step with the host's
  copy by content. The repository is `<run>\.stage`, a bare one whose work tree is `game\`, so the
  sync never sees it. Main holds all of `game\` but `out\` (the built layouts too); a stage holds
  `.fk`, `.surface` and `.fkb` files only.
- **Replaying onto reality** is `git merge-tree` per stage, with no work tree and no half-done
  rebase left behind: a stage reality didn't touch replays cleanly; one it did keeps conflict
  markers labeled `what is built` / `stage N`, and `list` names it.
- **Stage folders, the scratch copies.** `<run>\stages\N` is `game\` as stage N leaves it, layouts
  and terrain included (the run's design workers had copied all of `game\` to try a change).
  `check N` builds it through `report_checks` with no game link, and reports the check lines,
  plates and science per minute against the stage before it, the spec's expected rates on paper,
  and the bill: what the stage builds beyond the stage before it (its last check, else the built
  base), each item with the rate the base before it makes it at ("made at 15/min before it (27 min
  of it)", or "no maker before it") and the network's stock as game\'s last build read it
  (`out\report_bom.txt`; a check reads no game). `--render` draws the design the check laid out,
  the plots the stage changes or an area, and `stages\N\out\render.txt` keeps it (`fk look
  --design` draws the committed layouts; the run's design worker wrote a script to read
  `out\floorplan` instead). A folder's own edits survive plan changes (a three-way merge) until
  `edit N` takes them in.
- **The horizon is multiplicative** (Rory's decision 4): `fk stage list` shows the planned base
  against the built one in plates per minute, iron plus copper, the rate model's furnaces at their
  utilization (requester chests aside). Plates rather than science per minute: plates grow from the
  first drill on, while science is 0 until the first lab line and a mall or oil stage adds none,
  and everything the base grows by is made of plates. Below 1.5x the line says planning is the
  next job. A stage with no rates (a conflict, a syntax error) is named, and the reach is the
  stages' before it.
- **The lead brief** gains "Plan ahead while workers build": design the later stages while workers
  build, a worker builds the next stage and reports how it differs, `done` replays the plan, the
  horizon, and Rory's longest wait, 5 minutes. TOOLKIT.md has "Planning ahead: `fk stage`".
- **The loop**: a lead that has waited 5 minutes (`WAIT`) while its workers run gets one note per
  wait, with each worker's minutes, tool calls and last command, and `fk stage horizon` when the
  run has a plan. `<run>\.loop\workers.txt` keeps those lines current (the run's RETRO: no way to see
  a long builder's progress without its transcript). It sits beside the no-research note.
- Tests: `tests\test_stage.py`, and the wait note in `tests\test_workers.py`.

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
- **Checked in the game** (the lead engineer, a laptop test server, 2.0.77, 2026-10-22: the
  codec's blueprint pasted, revived and captured back). The logistic and circuit conditions with
  every comparator (`<=` / `>=` / `!=` as the game's ≤ ≥ ≠), set filters, an inserter's hand
  reading, read ingredients and the constant combinator's sections survive. A belt's reading
  didn't: its 2.0 keys are `circuit_read_hand_contents` and `circuit_contents_read_mode`, which
  the codec now writes. The game drops an item signal's `type` on export (item is its default),
  and reading a blueprint counts a missing type as an item; settings the game holds otherwise
  than the tags say win, in `config`. An unwired belt keeps no reading at all, not even on its
  ghost, so a belt reading on no wire is a `WIRE` line.

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
- **The build says what it stops.** `report_bom --stock live` warns (RIP) when the paste would take
  up built machines while kinds it lays are SHORT (the burner row went before its 137 belts were
  made, and iron stood still), and points to `stop_on LOW_STOCK`. A build that stops writes "not
  run" into the reports of the steps it didn't reach, instead of leaving the last run's lines
  there; the stop_on step says which checks would stop the run and that none has (its old
  "stop_on: INVARIANT" read as the failure behind a worker's nonzero exit, which came from the
  worker's own shell chain).

## Not in 2.0 yet

- Lanes, throughput and side-loading smelter arrays (their session runs).
- From circuits: combinators beyond the constant one (fnet modules, a named feature), wires
  routed through poles, `behave` states in `fk look` (EXPECTED), a gated net's cycle in the rate
  model, a storage chest's filter, a first load of fuel for self-fuelling burner drills.
- DeepSeek workers; daisy-chained labs and turrets.
