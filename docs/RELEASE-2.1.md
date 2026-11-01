# Toolkit 2.1: a small core and a library

Rory, 2026-10-31: the language should be isolated core features, and everything that benefits from
being dynamic should be source in a library the player is invited to change, extend and duplicate.
2.1 is that revision, after 2.0.78. The plan is `assessment-20261031\PLAN-2.1.md`; each release has
its own notes, `docs/RELEASE-2.1.N.md`.

Every file written for 2.0.78 still builds. The golden check (`tools/golden.py`, 54 designs: the
examples, the paper games, the test data, the kickoff template and the live run's world) found
every design identical at each release, but one: from 2.1.12 the model serves a short line in
order, so `furnace-column.fk` has its first five furnaces full and the last two waiting, as the
belt does, where it had all eight at 67%.

## What a player can write now

- **`Machine<entity, recipe>`**: one machine of any crafting building, a centrifuge included.
  **`Entity<name=...>`**: any other building, placed, powered and wireable.
- **The library.** A prelude every file gets (`Assembler`, `Furnace`, `ChemPlant`, `Refinery`,
  `Buffer`, `PowerSwitch`, `Accumulator`, and presets for buildings set up with raw settings). A
  run's `game\prelude.fk` lies over the toolkit's.
- **`kind NAME = KIND<params>`** names a kind, a module or a kind with some parameters set.
- **`tiers KIND: ...`** says what `machine=auto` may pick, one footprint to a line.
- **Module parameters**: `module FurnaceCell<plate, ore>`, `$p`, lists with `$p[k]`, defaults, and
  Stacks that pass them to every cell.
- **The template's `cells.fk`** with parameters: furnace, smelter, assembler, lab, acid drill and
  sushi cells, and `Hysteresis`. `fk check` names the cell a new row could be.
- **Cells within cells**: `cols[2].pl`, `cols[*].pl` and `net each`; a module of Stacks stacks.
- **Ribbons**: belts side by side, in order, all the way: a `net each`, a `bundle`, or a
  `width 8` net.
- **Fluid ports**: a pipe across a frame's edge, and through a Stack.
- **Buffers**: `Buffer` and `module X buffer`, rated as filling, draining or steady.
  `limited "..."` says what limits a sushi net. `read=hold-all` reads a whole belt. `when W.ITEM <
  auto` works out a sushi gate's amount from the loop's recipes.
- **Open circuits**: `cb.` and `bp.` fields on any building, every signal the game has, a wire to
  any building with a connector, and wires longer than 9 tiles carried on poles.
- **Power domains**: one network per `power` line, `copper` lines, `PowerSwitch`,
  `Accumulator<read=>`, `Decider` and `Arithmetic`.
- **Names inside a Literal**: `automall.asm10` is a net end.

And from the toolkit's side:

- **Run stats**: every run records items, fluids, power (per class, per machine type, per domain),
  research and machine states every 5 game minutes, and capital every 10. `fk stats --history` and
  `--page` read them. The research line says the packs a minute and the time left, and why it
  stalls.
- **Vision**: `fk look --zoom N`, `--layers` (robots, power, defense, pollution, pipes, recipes,
  tags) and `--image`.
- **Settings in place**: a changed setting is written onto what stands, a tier change is an
  upgrade, and a wire pass matches the world's wires to the design's.
- **Fixes from the runs**: a paired port fed by two nets, `REACH` and robots that can't reach,
  `fk request ENTITY ITEM N`, and the small ones.
- **Game facts from the game**: `facts.json` and a catalog of every placeable entity, recipe
  probabilities included.

The player docs say all of it as it stands: LANGUAGE.md ("The library" first), TOOLKIT.md ("What
`fk look` says", "The run's history", the checks and the advice) and EXAMPLES.md, whose five
examples (`plastic-cell`, `library-lines`, `ribbon-bus`, `power-shed`, `mall-loop`) build on paper
in `tests/test_examples_21.py`.

## Measured on the lab

Each on a laptop server (Factorio 2.0.77), against the rate model.

- **Run stats**: the recorder and the RCON read gave the same windows to the unit; 0.03 to 0.10 s a
  sample.
- **Vision**: a base of 1024 x 1024 tiles and 87,040 entities read in 16 game calls; a look at
  zoom 16 with every layer took 2.7 s, zoom 32 1.2 s.
- **Settings in place**: 8 hand edits, 7 written in place and nothing ordered out; upgrades kept a
  chest's 30 plates and an assembler's recipe; a robot's join to another plot's pole cut.
- **`Machine`**: a centrifuge and a chemical plant on plastic, both working.
- **Module parameters**: four iron and four copper FurnaceCells, 37.49 plates/min a furnace to the
  model's 37.50.
- **Buffers**: a drill line filling at the model's rate; four assemblers on a gated sushi loop for
  an hour at 91 to 100% of the model, the belt never stopped.
- **Fluid ports**: three acid drill cells on a uranium patch, every drill working, 59.5 ore/min mined to
  the model's 58.5 with the lab's mining productivity.
- **Open circuits**: a speaker and a display panel 34 tiles away on one wire carried over three
  added poles, both following a chest's plates.
- **Cells within cells**: an eight-column smelter bus, each furnace within a plate a minute of the
  model at a short feed; a 24-lab field filling column by column.
- **Power domains**: two domains stayed two networks; the hysteresis switch opened at 19.2% and
  closed at 79.6%, once each way.
- **Ribbons**: the eight-column bus to eight chests, 533 belts, two turns, every chest fed from its
  own column.
- **The library**: every cell line within 3% of the row it replaces (the gear cell 7% above it);
  the sushi mall at 90 to 100% of the model for 30 game minutes.

## Known limits

- **Rows are frozen.** They build as in 2.0.78 and get nothing new. Drill cells in place of
  `MinerRow` come after 2.1.
- **`Machine` is crafters only.** Labs, drills and rocket silos keep their own kinds.
- **No loops in the language.** A cell for any number of ingredients needs one port per list item;
  `LabCell` takes two packs.
- **The rate model** takes a raw circuit condition, and any `when` without a `behave` cycle, as
  always open. A buffer is an unlimited supply and sink: stock over time is not modelled. Labs are
  sinks, so the last labs of a field aren't predicted. The per-net rows for a net between two
  ports read 0; the machines' rates are right.
- **A requester of two items** feeding two nets loads both with both items: use a chest per item.
- **The router can't split a belt of two paired lanes**; `LabColumn` carries its packs on two
  header belts for that reason.
- **A drill cell narrower than 7x7** can fail to route its ore.
- **The auto mall's circuit gate**, an amount worked out by circuit for recipes that change, is not
  built: write the amount.
- **Settings in place** don't reach a drill, pumpjack or offshore pump: those are laid fresh.
- **Circuits**: `when` on a speaker or a display panel (write `cb.circuit_condition`), radar links
  for very long wires, and merging a kind's object field with an instance's are not in 2.1.
- **Power domains**: between a robot building a pole that joins two domains and the next wire pass,
  they are one network for a moment.
- **Vision**: no trains and no player names. On a headless laptop server nothing is charted, so a
  play-mode look there is blank.
- **The golden check** compares netlists, rates and layouts, not blueprints.

## The releases

- 2.1.0: run stats, every run's history from the first minute.
- 2.1.1: game facts into data, and the catalog's every placeable entity.
- 2.1.2: vision: `fk look --zoom`, `--layers` and `--image`.
- 2.1.3: fixes from the runs: a paired port fed by two nets, `REACH`, `fk request`.
- 2.1.4: stats for a run with no loop.
- 2.1.5: `Machine`, `Entity`, `kind`, the prelude and `tiers`.
- 2.1.6: settings changed in place, upgrades, and the wire pass.
- 2.1.7: module parameters.
- 2.1.8: buffers, `limited "..."`, `read=hold-all` and names inside a Literal.
- 2.1.9: a run's prelude lies over the toolkit's.
- 2.1.10: fluid ports, and recipe probabilities.
- 2.1.11: open circuits: `cb.` and `bp.`, signals from the game, wires on poles.
- 2.1.12: cells within cells, and a short line served in order.
- 2.1.13: power domains and switching.
- 2.1.14: ribbons, belts side by side.
- 2.1.15: the library: cells with parameters, the sushi gate and mall, `row-cell`.
- 2.1.16: ribbon tunnels: each belt of a ribbon goes under on its own, its reach by belt tier.
- 2.1.17: the documents.
