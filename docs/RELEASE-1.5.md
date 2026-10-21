# Toolkit 1.5 (2026-10-21): growing big

For Rory's morning advice to the two overnight players: grow exponentially (about 10 red and 10
green science assemblers before blue, 8 to 15 each of blue, advanced circuit and engine
assemblers), a proper compact mall, and a main bus. No new rules: checks warn, never gate.

## New

- **`fk plan ITEM RATE` and `fk plan ITEM --machines N`** (`fkcore/plan.py`, 55ae296, built in its
  own session): the forward ratio calculator. From a target rate (or the machines you want on an
  item) to every step of the recipe tree: the rate each item takes, its machine and how many (a
  fraction and rounded up), what each item's net carries to each consumer, and the raw inputs
  with their drills, pumpjacks and offshore pumps (furnace fuel included). `fk plan
  chemical-science-pack --machines 15`: 0.94 blue/s on 11.25 iron and 7.03 copper plates a second,
  36 + 23 stone furnaces and 15 for steel, 23 iron, 15 copper and 7 coal drills, 8 pumpjacks.
  Full speed, no modules or beacons; `--asm`, `--furnace`, `--mining-productivity`, `--recipe`,
  `--raw` change its terms. Rory asked whether an agent can work out "how many iron miners for
  15 blue science factories": now one command.
- **The world line says which pack the labs wait for** (`kickoff/claude_loop.py`, 9659789): "8 of
  11 labs wait for packs (logistic-science-pack missing in 8); 3 of 4 logistic-science-pack makers
  short of ingredients", and RESEARCH STALLED when every lab waits, again every 10 minutes. Both
  players' research had stood on one starved pack while the line said "11%"; with the new line
  both went for that pack within seconds.
- **`docs\examples\compact-mall.fk`** (9125139): Rory's layout, rows with no gap between chains and
  a 1-tile gap inside one (that gap holds the inserter that links a maker to what takes its
  output), two rows facing one iron corridor: 23 nets, 21 single inserters, 64 route carriers
  (`early-mall.fk`: 104).
- **`docs\examples\bus4.json` and `bus4.fk`** (9125139): Rory's 4-belt bus demo with priority
  loading and unloading, read from the lead world as a Literal (splitter priorities kept). A Bus
  template that nets load into and tap out of is being built in its own session.
- **The brief's "Grow big"** (8b93bd6): Rory's advice for new runs, and a line on `fk plan` in
  "Ways to get unstuck".
