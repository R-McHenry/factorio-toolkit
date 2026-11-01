# Toolkit 2.1, the library: cells with parameters, a sushi gate, and `fk check` naming the cell

PLAN-2.1.md, "Rows in 2.1": new lines are Stacks of cells, and the library gives the cells. Rows
still build.

## The cells

The kickoff template's `game\cells.fk` now takes parameters. Each smelting cell defaults to iron,
so every old line still builds as it did.

- `StoneFurnaceCell<plate, ore, fuel=coal>` and `SmelterPair<plate, ore, fuel=coal>`: copper, brick
  and steel as well as iron. Ore and fuel share the belt, a lane each.
- `FurnaceCell<plate, ore>` and `FurnacePair<plate, ore>`: electric.
- `SmeltColumn<plate, ore>`: three FurnaceCells, a cell of cells.
- `AsmCell<recipe, ins, out>`: two ingredients, `$ins[0] | $ins[1]`, a lane each. `AsmCell1` takes
  one. `GearCell` is now `kind GearCell = AsmCell1<recipe=iron-gear-wheel, ...>`.
- `LabCell<packs>` and `LabColumn<packs>` (six LabCells): `packs=` is a list of two.
- `AcidDrillCell`: one drill on uranium with its acid ports (7x7).
- `GateCell<item, items, amount=auto>` and `GateCellR` (the right lane): a requester that loads a
  sushi loop while the loop holds less than `amount`.
- `MallCell<recipe, items>`: one maker on the loop and its provider chest.
- `BeltEndBuffer<items>` and `ChestEndBuffer<items>`: `module ... buffer`, the loop's end.
- `Hysteresis<in, out, lo, hi>`: a latch with no ports. Name its parts from outside:
  `wire level green: acc -> shed.latch.in`, `when shed.hold.S = 0`.

Importing a kind now brings its module too (`import GearCell` brings AsmCell1).

## The gate's amount

`when W.ITEM < auto` on a net is worked out from the netlist at elaboration. The loop is every net
reached through ports and buffers. Each machine on it that takes ITEM by its recipe adds 40 s of
its take, and at least two crafts. `fk check` says the number and the machines. A condition may
also compare with a module parameter (`< $amount`).

An auto mall's recipes change by circuit, so the netlist fixes none. Its gate gets a `gate-auto`
check and holds at 0. Write the amount, or build a circuit gate. The circuit gate is not built.

`auto` on a machine's own `when` is refused. A sushi net that ends in a buffer's loop is no
SUSHI_SINK. A buffer whose sources are all gated reads "steady" in `fk rates`.

## `fk check`

- `row-cell`: a new row (not yet in the committed layout) could be a Stack of a library cell. It
  names the cell and its parameters, for SmelterArray, SmelterRow, AsmRow (two ingredients or
  one), LabRow and CircuitStack.
- `gate-auto`: what `auto` became and why.
- `limited-why` no longer fires on a Stack's own nets.

## Measured on the lab

A laptop lab, 10 game minutes each, items a minute. The lab force has +10% steel productivity and
+30% mining productivity.

| line | cell | row | model |
|---|---|---|---|
| SmelterPair, copper | 150.0 | 150.0 (SmelterArray) | 150 |
| SmelterPair, steel | 33.1 | 33.1 (SmelterArray) | 30, +10% |
| StoneFurnaceCell, brick | 75.0 | 75.0 (SmelterRow) | 75 |
| FurnaceCell, copper | 150 | 150 (SmelterRow) | 150 |
| FurnacePair, steel | 32.8 | 32.8 (SmelterRow) | 30, +10% |
| SmeltColumn x2, copper | 225 | 225 (SmelterRow n=6) | 225 |
| AsmCell, transport belt | 440 | 450 (AsmRow) | 480 |
| GearCell | 240 | 225 (AsmRow) | 240 |
| LabCell x6, packs | 42.0 | 42.0 (LabRow 6) | 42 |
| LabColumn x2, packs | 81.7 | 84.0 (LabRow 12) | 84 |
| AcidDrillCell, uranium ore | 58.4 | 58.2 (MinerRow) | 45, +30% = 58.5 |

The belt line is held by each assembler's input inserter, in the cell and the row alike. One lab
in the LabColumn ran at two thirds.

The sushi mall (`tests\library\mall.fk`): three gates (auto: 160 iron, 40 copper, 40 gears), four
MallCells (gears, cable, belts, pipes) and a BeltEndBuffer. Over 30 game minutes it made gears
100%, cable 99%, belts 90% and pipes 100% of the model. Every maker crafted in every 2-minute
window, so the belt never stopped. The loop held about the gate plus a hand of each item.

On one shared lane the first source along the belt takes every gap, and the sources after it
starve (belts at 0-41%). `GateCellR` gives the bulk item the other lane. With a ChestEndBuffer the
chest's contents are out of the gates' sight and piled up; use the BeltEndBuffer.

## Known limits

- A requester for two items loads both nets: use one chest per item.
- The router can't split a paired-lane belt.
- Narrow drill cells don't route ore.
- LabCell takes two packs.

## Checked

- `tests/test_library.py`: each line in `tests/library` elaborates, rates as its row, routes and
  connects. The auto gates are 160/40/40, a loop with no maker is a `gate-auto` line, `auto` on a
  machine and a word for `$amount` are refused, the old names still work, a kind brings its module,
  and Hysteresis builds with its wires.
- `tools/lab_library.py cells|labs|acid|mall` measures them on a laptop lab.
- Golden: every corpus file is identical to 2.1.12.
