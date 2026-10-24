# Toolkit 2.0.12: a watchdog, base health, no unrouted pastes, hand settings seen, an unbounded lab, a wait budget

Items 1-3 are the first three fixes ranked in the solo run's review
(`..\assessment-20261023\SOLO-RUN-REVIEW.md`, section 5). Together they would have saved about 13
of that run's 29 hours. Items 4-6 are Rory's, from 2026-10-24.

## 1. The loop's watchdog

On 2026-10-22 at 22:40 the loop's process went away with no line in play.log. The game ran 10.6 hours
with nobody playing, until the supervising session noticed at 09:18.

- **What it does.** `kickoff/watchdog.py` looks at the run every minute. It restarts play.cmd when
  the loop should run and has gone quiet:
  - there is no STOP file and GOAL.md has text;
  - play.log has been silent for 15 minutes;
  - and no live loop process holds `claude-loop.lock`.
- **A quiet loop is left alone.** A long build or a usage-limit backoff keeps the lock, so it isn't
  restarted. The lock's pid has to be a running Python process that is older than the lock file,
  so a pid Windows has handed to another process doesn't count.
- **One line in three places.**
  - play.log, for the record: `watchdog: play.log silent since 22:40 and no loop running: play.cmd
    started again`.
  - The game chat, for Rory: `[agent] watchdog: the player's loop stopped around 22:40; started it
    again at 22:55.`, sent through the run's toolkit (`fkcore say`).
  - `INBOX-watchdog.md`, for the player: its first round hands it over.
- **Repeated failures back off.** If the loop doesn't come back from a restart, the wait before the
  next one doubles: 15, 30, 60 minutes, then every 120.
- **How it stays alive.** The loop starts it as it starts (`watchdog.py RUN --detach`). The detach
  starts the watchdog again as a process of its own and then exits:
  - no console, so closing a window doesn't reach it;
  - its parent is gone, so a tree kill of the loop's window doesn't reach it;
  - it breaks away from any job that allows it.

  It keeps the laptop awake, as the loop does: a dead loop no longer does. It has one lock per run
  (`.loop\watchdog.lock`) and its own log (`.loop\watchdog.log`).
- **How it ends.** A STOP file ends it. The next loop start brings a new one. A loop that ended at
  its `--hours` or `--rounds` limit is restarted too: STOP is the way to end a run. Closing the
  window is not.
- **Where it comes from.** new_run and upgrade_run copy watchdog.py into `.toolkit` (the new
  `new_run.LOOP` list). kickoff-v1.ps1 ends every watchdog before it starts a new run, so an old
  run's watchdog can't bring its loop back.

## 2. Base health in the world line

From 13:55 to 16:09 on 2026-10-23 the base was dead (no coal, the reactor out of fuel), and the world
line spoke only of ghosts, robots and research. 5 logistic robots sat in a storage chest, and 500
plastic and 401 sulfur sat at 14.5,-0.5, for hours.

- **The read.** `claude_loop.STATUS_LUA` now also reads the base's health, inside a pcall so that a
  mistake there never costs the rest of the line:
  - iron and copper plates made in the last minute;
  - each reactor's fuel in minutes at full burn, counting the chests its inserters take from (the
    kit's reactor is fed from chests);
  - boilers with no fuel;
  - assemblers and furnaces that stand, counted by their status;
  - robots in chests;
  - items in chests outside every logistic network, with the three biggest kinds and where the
    most of each sits.
- **Alarms lead the line,** and they block: the line is noted again when they change.
  - `BASE DEAD: no iron or copper plates made in the last minute`. A map that has never made plates
    says `no plates made yet` instead.
  - `REACTOR FUEL OUT`.
  - `REACTOR FUEL LOW: about N min left at full burn` (under 30 minutes).
  - `ROBOTS IN CHESTS: ... while the network has none of them`.
- **Facts end the line,** and they don't block:
  - `plates/min: iron 373, copper 210`;
  - `makers stalled 20 of 85: 10 no ingredients, 7 output full, 2 no power`;
  - spare robots in chests;
  - boilers without fuel;
  - items outside every network.
- **Notes that wake the player.** A dead base, fuel out and fuel low are notes too, the way no
  research is. They wake a lead that waits on its workers, once each time they start: `[The base is
  dead: no iron or copper plates in the last minute.]`, `[The reactor is out of fuel.]` and `[The
  reactor's fuel is low: under 30 minutes at full burn.]`.
- **Checked on a laptop server** (`python tools/laptop_server.py health`, Factorio 2.0.77):
  - 2 cells in the reactor and 3 in its chest read as 16.7 minutes;
  - the 5 robots and the 904 items showed;
  - the unpowered assembler read `no power`;
  - after 75 game seconds with nothing made, the line led with BASE DEAD;
  - the read took 0.01 s.

  It also showed that an inserter that hasn't moved yet has no `drop_target`, so the read finds a
  reactor's chests by the inserters' drop and pickup positions instead. And a reactor burned fuel
  with no heat being used, so "at full burn" is the real rate.

## 3. No paste with an unrouted net

Mall4 went out with its products belt UNROUTED: no output, and inserters to nowhere (Rory,
23:23-23:30). The solo player then added `stop_on UNROUTED` to its own script.

- **The default build script** (`kickoff/template/game/nauvis.build.fkb`) now stops on two more
  checks: `stop_on UNROUTED NO_SINK`. An unrouted net stops the build at `route` or
  `report_checks`, before the paste.
- **NO_SINK and the `sinks` line.** report_checks has a new line per factory, `sinks     41 of 44
  makers on a net reach a sink with what they make; none reached: ...`. A maker counts when it is an
  assembler, a furnace or a drill. `NO_SINK` is reported for a maker that reaches none of the
  consumers of a net it drives, while that net's other pairs do connect. A net none of whose pairs
  connect already has its UNROUTED line. The check is `fkcore.connect.cut_off`.
- **UNUSED.** A declared net with no driver, consumer or carrier is now `UNUSED`, not `UNROUTED`.
  Otherwise one net nothing uses would hold every paste. The 2005 run had one (`oil net coalin`).
- **Upgrades.** upgrade_run adds the stops a run's script lacks, after its last stop_on line. The
  solo run's script gets only NO_SINK.
- **The post-paste side is in the game.** A maker whose output can't leave shows `output full` in
  the world line's stalled makers.
- **TOOLKIT.md** lists NO_SINK and UNUSED, and says that the default script stops on them.

## 4. Settings changed by hand are seen, and so is what the paste does to them

Rory: "it needs to be able to see my circuit changes and know that it is overriding them too".
A diff judged an entity by its name, position and direction only. So a condition, wire, filter,
request or recipe that Rory changed on an entity the toolkit placed went unseen. The solo run had
one at 21:52 on 10-23: "a couple circuit tweaks I did since some of the inserters are out of
roboport range".

- **What a paste does.** On a laptop server (2.0.77), a paste over a standing inserter and
  requester chest wrote the design's logistic condition, request, chest limit and recipe over the
  ones set by hand, and placed nothing. Where the design has none, a request is cleared, but a
  condition and a wire stay.
- **The diff reads them** (`fkcore/settings.py`). It blueprints the area in the game, which is the
  game's own export of each entity's settings, the same fields a paste reads. It compares them with
  the fields the paste would write, for every entity that stands where the design has it:
  - recipe, control behaviour (conditions, readings), filters, requests and chest limit;
  - the circuit wires between entities.
  
  What the game exports by default is dropped first (signal-S on every wired inserter, an empty
  request section).
- **The line, plain:** `rory_618 changed inserter at 14.5,0.5 (mall/i0): logistic=copper-plate>7
  (the paste sets logistic=iron-plate<50)`. Where the design has none: `(the design has none:
  the paste clears it)` for a request, or `... leaves it` for a wire or a condition.
- **Where it goes.** It is a hand edit, so it is a `HAND` line in the diff before the paste, it
  goes into `out\hand.txt` after the apply, and the loop hands it to the player. That note now
  reads `[A build replaced, removed or set back what someone did by hand]`.
- **What the player does.** To keep a change, write it into the source (the line uses the
  source's words where it can). `stop_on HAND` holds a paste until then. Otherwise the build
  overrides it, knowing.
- **Checked on a laptop server** (`python tools/laptop_server.py settings`). A design with a
  condition, a filter, a reading on a wire, a request, a limit and a constant combinator, pasted
  and built:
  - a diff finds no difference;
  - after 5 changes by Lua, it names each one (the added wire on both of its ends);
  - after the paste, the condition, request, limit and recipe are the design's again, and the
    added wire is still there.

## 5. The lab has no edge

Rory: "the lab should be allowed to have infinite size, and I think it works already but make
sure they can generate chunks easily".

- **The surface.** The scenario creates the lab with width and height 0, and on load it takes the
  edge off a lab made before (it was 2048 tiles square). A save keeps the script it was made
  with, so `fk lab` also does it through the game link before each build (`lab.lua_unbounded`).
  The game reads 0 back as 2000000.
- **Slots.** A slot is sized to its factory, in 200-tile cells with 10 to spare (a 450 x 300
  factory takes 3 x 2 cells). A new one goes to the free cells nearest the middle, ring by ring,
  with no last slot and no size cap; 2.0.3 had a 9 x 9 grid and 190 x 190 at most. A factory that
  outgrew its slot gets a new one, and the old one is emptied. 2.0.3's `[x, y]` slots read as
  one cell.
- **Chunks.** `fk lab NAME` generates the chunks under the whole slot itself (apply's lab mode
  already did so under the design), so nothing is left for the player to do.
- **Checked on a laptop server** (`python tools/laptop_server.py lab`). The lab was set back to
  2048 x 2048 and 100 slots were taken. Then the smelting example was built as a 450 x 300
  factory:
  - its slot was -1300,900, past the old edge;
  - the build said "the lab has no edge now (it was 2048x2048)" and generated 247 chunks;
  - the diff was OK for all 137 entities, in 0.4 s.

## 6. `fk wait`, from a fixed budget

Rory changed 2.0.11's rule: instead of "don't wait", `fk wait` is the only allowed wait, with a
fixed budget of wait time and an "are you sure" question.

- **The hook.** `kickoff/wait_hook.py` still blocks `sleep`, `Start-Sleep` and sleep loops, now
  with the reason "Use fk wait.". `fk wait` goes through.
- **`fk wait 90s`** (or `5m`) waits that long. **`fk wait built [AREA]`** waits on the host until
  the robots have built the area, at most what is left of the budget (its `--max` is capped).
- **It asks first:** "Are you sure you want to wait? N min of wait budget left. Run it again (or
  add --sure) to wait." The same wait run again within 2 minutes, or `--sure`, waits.
- **The budget.** It spends the time it actually waited. A wait cut off by a tool timeout counts
  what it ran. When the budget is spent, `fk wait` refuses (exit 2).
- **One number, two places to change it.** It is 30 minutes a run, `WAIT_BUDGET_MIN` in
  `agent/fk.py`. The run's `wait-budget.json` keeps what is spent, and a `budget_min` written
  there wins.
- **The briefs and TOOLKIT.md** now say "Only `fk wait` waits, from a fixed budget." (core-v1,
  lead-v1, worker-v1). The after-a-big-step line stays.

## Tests

- `tests/test_watchdog.py`: the restart and its three lines, a quiet live loop, STOP and an empty
  goal, the backoff, the lock's pid checks, the detach, one watchdog per run, and a real detached
  watchdog that outlives its starter and ends on STOP.
- `tests/test_claude_loop.py` `HealthTest`: each alarm and fact, Lua's empty tables, and a failed
  health read.
- `tests/test_workers.py`: the wake notes once each time, and the watchdog in `.toolkit`.
- `tests/test_connect.py` `SinkTest`: cut_off, the `sinks` line and NO_SINK, and UNUSED.
- `tests/test_upgrade_run.py` `StopsTest`: the template's stops, and an old script's.
- `tests/test_settings.py`: the game's export against the design, its defaults, a changed
  condition and request, a request the design lacks, an added wire, and the hand edit line.
- `tests/test_lab.py`: slots of any size and no last one, a 2.0.3 slot, and a build that takes
  the edge off and generates its chunks.
- `tests/test_wait_budget.py`: the question, `--sure`, the budget spent and refused, a cut-off
  wait, and `wait built` capped; `tests/test_workers.py`: the hook lets `fk wait` through.

Nothing in the live run or the game changed. A live run gets all of this through upgrade_run.
