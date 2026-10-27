# Toolkit 2.0.51: one plot, and the world's own furniture inside it

Rory, 2026-10-27: "kit in the design makes the most sense for sure. the reactor should be part of it
too. We can leave the reactor placed at the start ... the reactor can stay assembled", and "we
should be doing this on a fresh world with no other plot and kick off a fresh run".

## What was wrong

2.0.50 gave the run a 2000x2000 world plot, but it had to start at x 26: a plot may not overlap
another plot, and it may not hold the surface's own entities, and everything west of 26 was the
surface's - the plant's plot at -34,-39, its pole bridge, and the starter kit's claim, chests and
roboport. So the map had two owners: a surface that owned the west strip, and a design that owned
the rest. The base could not reach the oil wells or the west iron, and a player who moved the plot
over them stopped the build with an invariant.

## The model now

**A run's world is one plot, and what stands at the start is in the design.**

```
# nauvis.fk
import World from "world.fk"
world = World @(-1000, -1000) size 2000x2000    # map -1000,-1000 to 999,999
```

`world.fk` - the base's own file - holds the world's furniture as three placements:

```
import Plant from "plant.fk"
import Kit from "kit.fk"

plant = Plant @(966, 961)      # the reactor and its pole line, at map -34,-39
kit   = Kit @(1000, 1000)      # the kit, at map 0,0
```

- **`kit.fk`** is a `Literal` of `kit.json`: the roboport, six storage chests, six solar panels, two
  accumulators and the seven poles that power them - the exact entities `setup_v1.py` puts down
  before any robot exists (verified tile for tile against the live save's own entities).
- **`plant.fk`** is two `Literal`s of the same capture: the reactor block, assembled and running
  from the start, and the chain of poles from its west side to the kit. Its power is on the base's
  grid from the first build, because the pole line is part of the design instead of surface
  infrastructure.
- The kickoff is unchanged in *what it does*: it must build the roboport before robots exist, and it
  fills the chests with the 27 stacks of supplies. But it no longer owns anything: the design
  declares those entities, so the first build finds them standing and keeps them, and every tile
  inside the plot is the design's.
- `nauvis.surface` keeps only what is true of the world: `surface`, `mode`, `terrain`, `catalog`,
  `design nauvis.fk`, the watch policy and `notify`. The kit's claim is gone, and so is the bridge:
  with one plot there is nothing to bridge, so the template's `floorplan --bridge-power any` is now
  plain `floorplan`.

## What the plot holds

The whole start area: every ore tile in `map.terrain.json` (-192..192) is inside the plot - iron
1203/1203 tiles (1.33M), copper 373/373 (230k), coal 306/306 (210k), stone 386/386 (363k), and the
three crude-oil wells `setup_v1` creates at spawn. Nothing is reserved, so the ground the last runs
built on, the west iron and the oil are all the base's.

## What changed underneath

- `catalog`: `solar-panel` (3x3) and `accumulator` (2x2), the two prototypes the kit needs now that
  it is a design entity. Their sizes were read from the live run's own entities (their bounding
  boxes on the map), and `cover.GRID_SOURCE_TYPES` already named both types.
- `kickoff/template/game`: `nauvis.fk` (one plot), `world.fk` (the base's file, with the kit and the
  reactor), `kit.fk` and `kit.json` (new), `plant.fk` (reactor and bridge), `nauvis.surface`,
  `nauvis.build.fkb`, and the records: `nauvis.fkp` is the one plot line, `world.fkp` is the
  design's own layout, and `plant.fkp` (a plot that no longer exists) is gone.
- Nothing in `fkcore`'s plot or compose logic changed: a `Literal` placed inside a plot is the
  plot's, which is what made this a template change rather than a rule change.
- `tests/test_flow.py`: the template case now appends a first factory to the shipped `world.fk`
  (drills into furnaces east of the kit) instead of replacing it, so the kit and the reactor are
  exercised, and it asserts one plot and no `rates plant`.
- `tests/test_upgrade_run.py`: the template's `floorplan` no longer carries a bridge flag; `_pole`
  still upgrades a run that has one.
- Docs: `TOOLKIT.md`'s "The surface file and the world design", the three briefs, `EXAMPLES.md`, and
  the `setup_v1`/`new_run` docstrings.

## Verified

- The full suite: **1006 tests, OK**.
- The template builds offline to `report_checks`: **1 plot, 50 entities** (22 kit + 21 reactor + 7
  pole line), 0 LEAK, and "check lines this run: none".
- `cover power` adds **0 poles**: the design's own pole line already ties the reactor's grid to the
  kit's - and with the old surface bridge gone, nothing is left for a coverage step to invent.
- The kit matches the kickoff exactly: every position in `kit.json` was read back from the live
  save's entities (roboport at 8,8 covering tiles 6..9, the six chests at 2..4,8..9, the panels at
  8.5..16.5 x 15.5..19.5, the accumulators at 20..21, the seven poles), and the catalog's tiles for
  each agree with the game's bounding boxes.
