# Toolkit 2.0.57: SmelterPair, the smelter stack as a cell

`assessment-20261028\PLAN-CELLS.md`, step 4: rebuild `SmelterArray` and `CircuitStack` as cells,
check them on the lab against today's kinds, then remove the kinds.

## SmelterPair

A sixth starter cell in `game\cells.fk`: two stone furnaces back to back on one middle belt with
ore and coal on its two lanes, and plates out on the two outer belts. Twelve cells (24 furnaces)
take one yellow lane of ore, as a column of Rory's smelter stack does. Several lines on one
`lanes ore_ | fuel` pair make a bigger smelter: the router splits the pair to every line. It
joins their plates onto both lanes when they carry more than one (2.0.54). No foot, no splitters
in the cell.

On the lab (`lab-demos/compare`, slot 2000,0), fed by the same chests, twice:

| | plates/min | model |
|---|---|---|
| `SmelterArray<n=24>` | 446.5, 444.5 | 450 |
| `Stack<cell=SmelterPair, n=12>` | 452.5, 450.5 | 450 |

## CircuitStack stays, for now

A circuit cell (a cable, circuit and cable assembler each side, cable handed straight in) made
298 circuits/min to `CircuitStack<n=8>`'s 451. Eight circuit assemblers take 12 copper/s. Fed by
`lanes iron | copper`, the copper rides one lane of the shared belt as far as the split, 7.5/s.
The stack's foot brings copper on a whole belt and side-loads half onto each column's feed belt.
The router can't lay that, because a net belongs to one lane pair. So the circuit cell waits for
one router feature: one net split onto the lanes of several pair belts.

## Not removed

Neither kind is removed yet. The live starterbus run's `world.fk` and `campus.fk` use them (5
lines), so removing them waits until those are rewritten.

## Tests

`tests/test_cells.py`: SmelterPair's line routes and connects and draws no CLOG at its crossings.
