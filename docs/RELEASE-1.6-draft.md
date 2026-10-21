# Toolkit 1.6 (draft, 2026-10-21): the build counts the rows

Rory (2026-10-21): "the original factory source code should have been parametric for number of
bldgs, maybe we just need a solver that's better at setting those parameters to meet constraints
during a build." That is his principle "Design first: from a target rate, the model and layout".
Until now a count was written by hand and the rate model only checked it. Now a row may leave
its count to the build. No new rules: checks warn, never gate. Branch `size`; not merged, not
deployed, `__version__` not bumped (the lead decides).

## New

- **`n=auto`** on `MinerRow`, `SmelterRow`, `AsmRow` and `LabRow` (`fkcore/lang.py`,
  `fkcore/elaborate.py`); `n=auto 4..30` keeps it within bounds, plain `auto` is 1..100. Anything
  else written `auto` is an elaboration error ("auto is the count of a row"). Without a size step
  an auto row is elaborated at the count its `.fkp` laid out last, else its low bound, so `fk
  measure` and the other readers of the built layout see what was built.
- **The `size` step** (`fkcore/size.py`; in every build script of the repo, the kickoff template's
  too, right after `elaborate`). It gives every auto row the fewest machines that meet
  - every `target` line of the surface file (what the whole surface makes, as TARGET counts it),
  - every `assert INST.rate >= R` (also `>` and `==`; `<=` and `<` are checked, never grown for),
  - what the row's consumers ask: a net an auto row drives carries what the machines on it would
    take at their potential, plus what a sink with a `rate=` takes; a sink without a rate takes
    what is left and asks nothing,
  - for an auto sink row (`LabRow<n=auto, rate=...>`): the labs take what reaches them.

  All factories of the surface are sized together (a target is the surface's). How: a seed by
  fk plan's demand propagation on the design's own nets and recipes (consumers before producers,
  duty, requester chests at their rate and fixed rows first, auto rows the rest, evenly); then
  the real rate model: while a constraint fails, more machines on the row its binding chain names
  (spread evenly over the auto rows of one net); then each row gives back machines, consumers
  first, while everything still holds. A growth that doesn't help (a row at full speed whose inputs
  then run short) is dropped, and the reason comes from where the chain really stops. It runs in
  `--from` replays like elaborate, and takes 6 to 8 model solves on the designs below (0.05 s;
  0.5 s for the redgreen game).
- **`out/size.txt`**: `sized: gears n=1 (auto), red n=10 (auto), labs n=10 (auto)`, then per row
  its count, its seed, its bounds and what it serves (the constraint that breaks at one machine
  fewer, nearest first: `net iron_p: iron-plate for gears (for target automation-science-pack
  1/s)`; at a low bound, how much of it is used and what holds it), the committed count when it
  changed ("the row grows by 2"), every constraint met or not and why, and the nets of sized rows
  that carry more than a yellow lane on paper. `fk build --to size` previews it.
- **`SIZE`**: a constraint the counts can't meet with an auto row on the way, one line per blocker:
  "red is at n=5, the top of its auto 1..5"; "more red would run short: plates is a requester chest
  at 1.000/s (its rate=) (through net gear: ...; net pl: ...)". After route, `report_rates` adds
  one for a net of a sized row whose critical connector is asked more than it carries: "at the
  sized counts (iron n=32) it asks 10.00/s where its yellow lanes carry 7.50/s (ratio 1.33)". And
  `elaborate` says when a script with auto rows has no size step.
- **`FIT`**: a sized row whose frame, at its `@(x, y)` hint, runs past its plot or into another
  instance's frame: "n=13 (auto) makes it 26x7 at @(16, 14): its frame overlaps copper's (14x7 at
  @(40, 14)) on 2x7 tiles". Rows grow; where they stand is the player's. Nothing is moved, and
  `place` stops on overlapping entities as before (the writer's invariant).
- **`LabRow<n, rate=>`** (`fkcore/templates.py`, `fkcore/rates.py`, `fkcore/routed.py`): each lab
  takes at most `rate` of each pack it is fed (a research unit of 30 s: `rate=2/min`), so science
  rows that make more back up, and `n=auto` has something to size labs by. Without `rate=` a lab
  takes every pack that reaches it, as before, and `n=auto` on it stays at its low bound (the
  report says why).
- **`fk rates FILE.fk`** (and `check`, `explain`, `layout`, `unfold`) size the auto rows first,
  with the surface file beside the file when it places it (its targets, its other factories), and
  `fk rates` prints the `sized:` line.
- `fkcore.routed.critical` and `word` (public), `fkcore.expand.planned_frame` (where a hinted
  instance's frame lands before anything is placed), `rates.Model.sink_share`.
- Docs: LANGUAGE.md "Counts the build chooses: `n=auto`", TOOLKIT.md (`fk build --to size`, the
  SIZE and FIT checks, and that `fk plan`'s default machine is assembling-machine-2 where a row's is
  assembling-machine-1), EXAMPLES.md and `docs\examples\sized.fk`, a line in the brief's "Ways to
  get unstuck", CORE.md.

## `fk plan` stays a front-end; it is not the size step's seed

The question was whether `fk plan` stays as a front-end for questions before a design exists, or
becomes the size step's seed only. The evidence (`size.size` with each seed, the same model after
it):

| design | auto rows | netlist seed: rows off | plan.plan seed: rows off | solves: netlist / plan / no seed |
|---|---|---|---|---|
| red science 1/s, every row auto (a pure recipe tree) | 7 | 0 | 0 | 7 / 7 / 17 |
| red science, red n=10 written, no target | 6 | 0 | 0 | 6 / 6 / 14 |
| redgreen, red and green n=10 written, the rest auto (shared iron, copper, gear nets) | 12 | 0 | 0 | 8 / 8 / 27 |
| redgreen, every row auto, both targets 10/min | 14 | 0 | 1 (iron_smelt 4, not 5) | 7 / 13 / 19 |
| red science 1/s, red at duty 0.5 | 7 | 0 | 1 (red 10, not 20) | 7 / 8 / 17 |
| red science 1/s and a second iron row of its own for 3 pipe assemblers | 8 | 0 | 2 (8 and 8, not 7 and 10) | 8 / 13 / 23 |

The plan.plan seed is `fk plan` run on the design's own recipes and machine, one plan per target
and per written row's inputs, the machines per recipe summed and spread over the auto rows of that
recipe. All three starts reach the same counts (the model decides), so the seed is a matter of
solves and of what the report can say. Plan's recipe tree has no place for what makes the counts
differ: which row feeds which consumer (two iron rows on two nets), duty, rows written with a
count, requester chests at a rate. The netlist seed is the same propagation rule (consumers before
producers, a recipe's count from its most-asked product, plan's whole-machine rounding) on the
design's nets, and it was exact on all six. So the size step seeds itself, and `fk plan` stays what
it was built for: the question before a design exists ("how many miners for 15 blue science
assemblers?", `--machines N`), which no design-bound step can answer. On a pure tree both say the
same numbers when the machine matches: `fk plan automation-science-pack 1/s --asm
assembling-machine-1` gives 10 red, 1 gear, 6.4 iron and 3.2 copper furnaces, 4 and 2 drills, the
size step's 10, 1, 7, 4, 4, 2. With `fk plan`'s default machine (assembling-machine-2) it says 6.67
red and 0.67 gear assemblers, two thirds of what a row on its own default (assembling-machine-1)
takes; TOOLKIT.md now says so.

## Numbers checked by hand (tests/test_size.py, 32 tests)

- Red science 1/s, every row auto: red 10 (0.1/s an assembling-machine-1), gears 1, iron 7 (6.4
  stone furnaces), copper 4 (3.2), iron ore 4, copper ore 2, coal 1 (0.216/s); seeded right, 0
  growth steps, and from n=1 or n=30 everywhere the grow and trim steps reach the same.
- A shared iron net is sized from both its consumers: the gears' 2/s and two written circuit
  assemblers' 2/s: 13 furnaces (12.8), 8 drills.
- Red n=10 written and no target: the rows under it the same as above. Duty 0.5 on red: 20.
- A provider chest with `rate=2/s`: 7 furnaces, 4 drills; without a rate: 1 of each, and `assert
  smelt.rate >= 2/s` then gives 7 (and 5 drills: the furnaces run full into the chest).
- `n=auto 1..5` on red: 5, at its top, the SIZE line says so, and the rows under it are sized for
  5. A requester at 1/s: red 5, the fewest for the 0.5/s it can get, and the SIZE line names it.
- `LabRow<n=auto, rate=2/min>`: 30 labs for 1 pack/s. 10 labs at that rate hold 12 red assemblers
  to 1/3 pack/s ("not taken on packs").
- FIT: a 12-drill row into the coal row next to it, 20 furnaces into a chest, 32 past a 60-wide
  plot; in a build, a 13-furnace row into the copper row: FIT, then `place` stops (INVARIANT).
- After route: a 32-furnace row for five written gear assemblers puts 10/s on one yellow lane:
  SIZE. A rebuild keeps every count and lays out nothing new; a new target grows a row and says
  by how much; `--from place` sizes again.

## Deploy

The kickoff template's build script now has the `size` line, and `fk build` replays the source
steps (size among them) on the game host for `--from diff`: a run on this template needs the 1.6
toolkit on the host as well as on the laptop (an older one refuses the script: "unknown step
'size'"). A running run keeps its script until an upgrade: `kickoff/upgrade_run.py` now adds the
template's `size` line after `elaborate` (old script kept beside it, as for its other edits). With
no `n=auto` in its source a run builds exactly as before. Its TELL text for 1.6 is the release's
to write; `__version__` is still 1.5.

## Known, not done

- On a net sized to the exact need both sides bind, and the plain rate model may name the input
  (`fk rates`: "iron-ore short on left/ore_" where the furnaces' output is all taken and more
  drills would not help). The utilizations are right either way. Inside the size step an auto row
  makes 1e-7 more than its recipe says, so its decisions see the tie as the producer's slack.
  Fixing the attribution in `rates.solve` (name the output side when the output net takes no more)
  changes `model.binding`, which `routed` reads for fluid-bound machines: its own change, with its
  own tests.
- No module or beacon; `ChemPlant<n>` and `Pumpjack<n>` take no `n=auto` (their `n` lays one
  machine in V1). `Assembler` groups are not rows, so they have no count to size.
- A sized `@patch` MinerRow is placed by `place` on its ore, which says when that many drills
  don't fit there; FIT checks only rows with an `@(x, y)` hint.
- The default top of 100 is a guard against a runaway count, not a design rule.
