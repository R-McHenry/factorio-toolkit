# Toolkit 2.0.58: CircuitCell, green circuits in a zigzag

Rory, 2026-10-28: "a really smart one that has cells ratioed at 2:3 ... the positions are staggered
so then each circuit factory gets fed by two of the copper cables factories", "one of the rows is
offset by 1 so it overlaps 2 machines", and "the best layout is a row of cable assemblers next to a
row of circuit assemblers ... a nice zigzag rather than a long line".

## CircuitCell

A seventh starter cell in `game\cells.fk`, 23x9. Each side of a middle copper belt has a column of
three cable assemblers (rows 0, 3, 6) beside a column of two circuit assemblers offset a row (rows
1 and 5). Each circuit assembler faces two cable assemblers across one row of inserters, and the
middle one hands to both: 2 + 1 cable/s into each circuit assembler, the 3 it uses. Copper comes
up the middle belt on both lanes to both cable columns. Iron comes up each outer belt, reached by a
long-handed inserter over the circuits belt beside it, which takes the circuits back down. The
cable is three nets a side, `w0 -> wa`, `w1 -> wa, wb` and `w2 -> wb`, so the router lays one
inserter for each cable assembler and circuit assembler that touch.

On the lab (`lab-demos/compare`, slot 2000,0), against the CircuitStack row, both with eight circuit
assemblers and their requester chests stocked:

| | circuits/min |
|---|---|
| `CircuitStack<n=8>` | 449.5 |
| `Stack<cell=CircuitCell, n=2>` | 479.4 (eight assembling-machine-1s make 480) |

The first try, one feed belt of iron and copper on two lanes, made 298. The copper rode one lane
(7.5/s for the 12 it needs). Copper on its own belt, both lanes, is what fixed it.

## One item from several nets

A single machine may now take one item from several nets: each net gets a role, an inserter of its
own (`expand.belts`; before, a machine got a role only for an item's first net, so the second net
had nowhere to attach). `two-nets` stays quiet for it when each of those nets carries only that
item. A product on two nets, or a net carrying more than the one item, still draws the line.

## Not removed

`SmelterArray` and `CircuitStack` both have cells that match or beat them now (SmelterPair, 2.0.57;
CircuitCell). The kinds stay until the live run's five lines that use them are rewritten.

## Tests

`tests/test_cells.py`: CircuitCell's line routes and connects.
