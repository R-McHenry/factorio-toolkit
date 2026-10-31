# Toolkit 2.0.69: working capital

Rory, 2026-10-30: measure "what percentage of stuff is reinvested already, versus just sitting
idle", counting everything in resources. Science is valuable spent, not as a rate. Malls count
against the metric, and leaving anything out is a deliberate choice.

## `fk capital`: what the base owns, working against idle

Everything the force owns is priced in raw units (`cost.item_cost`: an iron plate is 1, an
assembling-machine-2 54, a red pack 3). The headline is working / (working + idle).

- **Machines** (assemblers, furnaces, silos, drills, labs, beacons) and their modules. Each counts
  as working for its share of the time since the last read, from its finished crafts. Drills,
  labs and beacons, and a first read, go by status. The idle part is broken down by status.
- **Robots.** In the air works, in a roboport waits. The share is averaged over two reads.
- **Research.** A researched tech is worth its packs. It works when something it unlocks is in
  use: a working machine runs one of its recipes, or a product of one is placed, working or flying.
  A bonus tech works while what it boosts does. Military-only techs weigh 0.25, and
  `--weight TECH=W` sets any weight. The research under way counts for what has gone into it.
  Infinite techs are left out for now.
- **Stock.** Every item anywhere is idle: chests (a mall's too), belts, machine inputs and
  outputs, inserter hands, robot cargo, the ground, the pack. There is no satisfied state.
- **Left out.** Belts, inserters, poles, pipes, chests, roboports, power and turrets are counted on
  neither side, and are only reported.
- **Parked.** `fk capital --park X0,Y0,X1,Y1 --why TEXT` leaves an area out on purpose. It is
  always reported as parked, and `--unpark N` counts it again.
- **Growth.** Each read is kept in `out/capital/history.jsonl`. The report says how fast the
  working capital doubles, measured over about the last half hour of game time.

`--area` reads a lab slot alone, and `fk sim game capital` reads the planner (it keeps its own
history). The read is one Lua pass over the force's entities.

## In the world line

The loop reads `fk capital --brief` every 2 minutes (`CAPITAL`) and ends the world line with it:

    working capital 42% of 445k raw units (machines 26% of 6.1k, robots 32% of 4.1k, research 67%
    of 272k, stock 162k idle; makers 94 of 240 ran); growth: not enough reads yet

(the opus save below; once the history holds half an hour, the growth reads "the working capital
doubles every N min (over M min)".)

## Checked on a laptop server

`python tools/laptop_server.py capital SAVE.zip` was run on the opus run's sim save sr1-d12i,
tick 4.63M (21 game hours). Each read took 0.1 s.

    capital nauvis: tick 4632635: 41.6% working, 185k of 445k raw units
      machines   1.6k working of 6.1k  (94 of 240 makers ran, 69.7 at full time); idle: 1.2k full
                 output, 1.1k missing science packs, 759 no minable resources, ...
      robots     1.3k working of 4.1k
      research   182k working of 272k  (40 of 83 techs in use); unused: research-speed-4 16k,
                 low-density-structure 9.3k, processing-unit 9.3k, ...
      stock         0 working of 162k; most: 1573 chemical-science-pack (33k), 3068 stone-brick
                 (31k), 1655 advanced-circuit (13k), ...
      left out: 38k in belts, inserters, poles, pipes, chests, roboports, power and turrets

In raw units, research is most of what a mid-game base owns: 61% here. Machines are about 1%.
