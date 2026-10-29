# Toolkit 2.0.55: lines of machines are your own cells

Rory, 2026-10-28: the player owns its templates. A line of machines is a `Stack` of the player's
own cells; the toolkit's row kinds keep working but go unmentioned; basic machines get starter
cells, as the simplest examples of a Stack (`assessment-20261028\PLAN-CELLS.md`, step 2).

## Starter cells

Every new run's `game\cells.fk` (from `kickoff/template/game`) starts with five cells, the
player's to copy and change:

| cell | what |
|---|---|
| `FurnaceCell` | an electric furnace, ore up one belt, plates down the other: one lane |
| `FurnacePair` | two electric furnaces facing across the plate belt: both lanes, 15/s on yellow |
| `StoneFurnaceCell` | a stone furnace, ore and coal on the two lanes of one belt |
| `GearCell` | an assembler, one ingredient in, its product out |
| `LabCell` | a lab, red and green packs on the two lanes of one belt |

`import FurnaceCell from "cells.fk"` and `Stack<cell=FurnaceCell, n=12>` make a line. An upgrade
copies `cells.fk` into a run that has none and leaves a run's own alone.

## The docs teach cells first

- LANGUAGE.md opens with a line of cells. A new section, "Lines of machines: your own cells",
  lists the starter cells and says how to make your own. The built-in table no longer has
  `AsmRow`, `SmelterRow`, `LabRow`, `SmelterArray` or `CircuitStack`. One "Older kinds" paragraph
  says they still build and a design that has them keeps working.
- The `n=auto` section says a Stack's `n` is written: the build doesn't count cells yet (plan step
  6). The module and import examples use an assembler and a Stack.
- EXAMPLES.md points to the cell examples (`furnace-column.fk`, `blue6.fk`). STRATEGY.md's "fill
  both lanes" points to `FurnacePair` and to the router's two lanes. TOOLKIT.md's lane paragraph
  has 2.0.54's both lanes.

## No false CLOG between cells

Where a paired belt (`A | B`) crosses from one cell into the next, the stack's crossing net
carries both items. Each stays on its own lane there, so the crossing can't clog. It no longer
draws `CLOG`; two items mixed on one lane (`A, B`) still do.

## Not changed

- The row kinds build exactly as before; the live run keeps every route.
- MinerRow stays the way to put drills on a patch until drill cells (plan step 5).
- A module takes no parameters, so a starter cell has one recipe; you copy it to change it.

## Tests

`tests/test_cells.py` (6): the template declares the five cells, each line routes and connects, no
CLOG on paired crossings and still one on a mixed lane, and an upgrade brings `cells.fk` only to a
run without one.
