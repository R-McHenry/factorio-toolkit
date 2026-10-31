# Toolkit 2.1 (run stats, planned as 2.1.1): every run records its own history

Rory, 2026-10-31: every new run records its own history from the first minute, whatever the
player does. Capital and reinvestment, items and fluids made and used, power made per generator
class and used per machine type, the research rate, and machine states, every 5 game minutes.
The research rate is the stat most worth seeing at a glance, so it is also in every command's
research line.

## A sample

A sample is the game's cumulative counts (`fkcore.runstats.SAMPLE_LUA`):

- items and fluids made and used, from the force's production statistics;
- power made and used per entity, in joules, from each electric network's statistics, summed
  over the networks. A network's input is what its machines used, its output what was made (checked
  on a laptop server: an assembler's 150 kW shows as input, the energy interface's as output);
- the research under way, its progress, its cost and how many technologies are done;
- how many machines of each kind, and of each recipe, stand in each state. An idle furnace counts
  under its last recipe.

Each sample stores the change since the last one, so a late or missed sample loses nothing: that
stretch is one long window. The first sample counts from the map's start. A count that goes down
(a save loaded again, another map) shows as a gap. A network whose counts went down (it merged or
split) starts over and is left out of that one window.

## Where samples come from

- **New runs:** the fk-play scenario has a recorder, `fk_stats.lua`. An `on_nth_tick` handler,
  registered at script load through event_handler like fk_chat and fk_lab, appends a line to
  `script-output/fk-stats/samples.jsonl` every 5 game minutes, on the server only. It only reads,
  keeps nothing in `storage`, and runs in a `pcall`. It keeps going while nothing on the laptop
  runs. kickoff-v1.sh already copies the scenario into the server for each new map, so new runs
  need nothing else.
- **Runs already going:** a map keeps the script it was made with, and nothing may be registered
  over RCON. So the same sample function is sent as a read-only RCON call, at most once per 5
  game minutes. Since the counts are totals, nothing is lost while the laptop is away.

`fk stats --sample` takes what is due: the recorder's new lines, or, when the recorder has written
nothing for this map lately, the RCON read. It also runs the capital read (`fkcore.capital`) every
10 game minutes into `out/capital/history.jsonl`. It skips the footer, so a sampler that runs on
its own never takes the player's alerts or chat. `--now` samples at once.

The samples go to `game/out/stats/`: `items.jsonl`, `fluids.jsonl`, `power.jsonl`,
`research.jsonl` and `machines.jsonl`, plus `state.json`. `fk` pulls `out/stats` only for stats
commands, since it grows all run long.

## The loop, and runs without one

`claude_loop.py` takes the sample every 5 game minutes, by the tick its watcher reads, through
`kickoff/stats_sample.py`. That runs the sample where the game is, copies `out/stats` and
`out/capital` back, and writes the page on the laptop. play.log says what each sample kept.

The live run is driven from a conversation, with no loop. For it, an upgrade can schedule
`python <run>\.toolkit\stats_sample.py <run>`. Any interval works, since it keeps only what is
due; every 5 minutes is enough. `upgrade_run.py` copies stats_sample.py with the loop files. The
run's save is not changed.

## The research line

Every command ends with it. It now gives the packs the labs used in the last game minute and the
time left at that pace:

    research fast-inserter 56%, 4 packs/min, ~3 min left; queue: logistic-science-pack; 2 labs

A queued research whose labs used no pack in the last minute is loud, with the cause when the game
shows it:

    RESEARCH STALLED: fast-inserter 56%, 0 packs/min in the last minute: no lab holds automation-science-pack; ...

The other causes are `no lab holds all 4 packs (X missing in 9 of 12 labs)` (the 10-30 run's
military-3) and labs without power. A read from an older host toolkit keeps the old line.

## Viewing it

- `fk stats --history`: the research first, then the latest window (capital and the share that
  works, the top items made and used per minute, power made and used per kind with the balance,
  machines per state, recipes that mostly stand), then the trend (the last 30 game minutes against
  the 30 before) and the totals.
- `fk stats --page`: `game/out/stats/index.html`, a static page with inline SVG charts: research
  progress and packs per minute by colour, capital and reinvestment, power per class and per
  machine type and the balance, machine states per machine and per recipe, and every item and
  fluid made and used. Long runs are merged into at most 240 windows, with totals kept. Light and
  dark themes; the big charts read out values on hover.

## Checked on a laptop server

`python tools/laptop_server.py stats`, a fresh map from fk-play with a small base (an energy
interface, solar panels, two assemblers, an electric furnace, two labs on red techs, and a second
network):

- the recorder wrote one line at each of 5, 10 and 15 game minutes (3 lines, 3.4 kB);
- the RCON read at the same ticks gave the same windows and the same numbers, to the unit
  (largest relative difference 0) for items, fluids and power;
- each sample took 0.03-0.10 s;
- the research line: `research fast-inserter 56%, 4 packs/min, ~3 min left`. With the packs taken
  out of the labs and 2 game minutes on: `RESEARCH STALLED: ... no lab holds
  automation-science-pack`;
- `fk stats --history` and the page (28 kB) came from the samples.

A map made from the 2.0.78 scenario, which has no recorder, was played 11 minutes and saved. On it
(`stats SAVE.zip`), two RCON samples 5 game minutes apart came out alike, and no recorder file
appeared.

`stats_sample.py` on a local run folder, with the recorder: it kept one sample per 5 game
minutes, ran the capital at 5 and 15, wrote the page, and said "nothing new" when called early.
`fk stats --history` and `fk stats --sample` went through the run's `bin\fk.py`.

No played save of a real run was on hand outside `C:\fk-player`, so the capital and stats path has
not been run on a big base here.

## Tests

`tests/test_runstats.py`: the scenario and the RCON read run the same Lua, which registers nothing;
deltas, late samples, resets and changed networks; the recorder file's offsets and first read; the
sampler's choices (RCON every 5 game minutes, the recorder when it is live, `--now`, capital every
10); the history, the page and the buckets; the research line's rate, time left and stall causes.
`tests/test_lab_scenario.py`: the recorder's rules.
