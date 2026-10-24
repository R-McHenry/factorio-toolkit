# Toolkit 2.0.12: a watchdog, base health in the world line, no unrouted pastes

The first three fixes ranked in the solo run's review (`..\assessment-20261023\SOLO-RUN-REVIEW.md`,
section 5). Together they would have saved about 13 of that run's 29 hours.

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

## Tests

- `tests/test_watchdog.py`: the restart and its three lines, a quiet live loop, STOP and an empty
  goal, the backoff, the lock's pid checks, the detach, one watchdog per run, and a real detached
  watchdog that outlives its starter and ends on STOP.
- `tests/test_claude_loop.py` `HealthTest`: each alarm and fact, Lua's empty tables, and a failed
  health read.
- `tests/test_workers.py`: the wake notes once each time, and the watchdog in `.toolkit`.
- `tests/test_connect.py` `SinkTest`: cut_off, the `sinks` line and NO_SINK, and UNUSED.
- `tests/test_upgrade_run.py` `StopsTest`: the template's stops, and an old script's.

Nothing in the live run or the game changed. A live run gets all of this through upgrade_run.
