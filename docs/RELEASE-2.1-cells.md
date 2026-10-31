# Toolkit 2.1.x: cells within cells

Draft for the "cells within cells" phase of `assessment-20261031\PLAN-2.1.md` ("E. Cells within
cells"); the integrator gives the number.

## What a player can write now

- **`cols[2].pl`** names cell 2's port P (cells count from 0). **`cols[-1].pl`** is the last
  cell's.
- **`cols[*].pl`** names every cell's port. In an ordinary net it is one net with all of them as
  endpoints: `net plates: cols[*].pl -> box` merges every column's plates.
- **`net each NAME: A[*].P -> B[*].Q`** is one net per cell, cell k with cell k. The nets are
  `NAME_0`, `NAME_1`, ...
  - One side may name a list of ports instead: a sealed module's ports, in their written order.
    `net each plates: cols[*].pl -> box`, where `Boxes` has eight `in` ports, sends column k's
    plates to port k.
  - The netlist keeps them together: `flat.each[NAME]` lists the nets in cell order, and each
    one's `FlatNet.group` is NAME. The ribbon release routes a group as one ribbon.
- **Cells within cells.** A cell may hold a Stack, and the module is stacked like any cell. An
  outer Stack's `n=auto` counts its cells. A Stack inside a cell takes a number.
- **An import brings what a module is built of.** `import SmeltColumn from "cells.fk"` brings
  the modules of that file it uses (`FurnaceCell`), through instances, `cell=`, `head=` and kinds.
  A module of the importer's own name wins. Before, the inner Stack's cell was "not a module".

## New refusals

- An index past the end: `cols[4].pl: cols has 4 cells, [0] to [3] (or [-1] to [-4] from the end)`.
- `[k]` on anything but a Stack: `box[0]: box is a Chest, not a Stack`.
- `[*]` outside a net (an assert, a cover, a wire).
- An each net whose sides count differently: `both sides need the same count, and they have
  cols[*].pl 4 cells, box 5 ports`.
- An each net over an `n=auto` Stack, an each net with no `[*]`, a side that is one endpoint,
  `.*` in an each net, and `split` with `each`.
- A net of the name an each net gives (`plates_1` beside `net each plates`).
- `n=auto` (or `built=auto`) on a Stack inside a Stack's cell.

## A short line serves its cells in order

Both of the 20261030 run's lab lines (`eiron`, `ecopper`, Stacks of 12 `FurnacePair`) ran their
last cell at half. The model said 96% for all 24 furnaces.

**Why:** the rate model shares a short net by appetite: every consumer runs at the same fraction.
The nets of a Stack's chain are joined through their ports into one pool, so all 24 furnaces
shared the shortfall. On the belt the ore passes cell 0's inserters before it reaches cell 1's,
so the first cells take what they need and the last get what is left.

**The fix** (`rates._lines`, `_in_order`): a pool that runs along a Stack's chain is served as a
tree of its nets. At each net the machines' inserters take first, sharing by appetite as before,
and the rest goes on. Where it goes on two ways or more (a splitter: up into a column and on along
the foot), each way gets an even share, and what one can't take goes to the others. A pool gets
this only when it has a chain port in it, is fed at one net by all its drivers, and its nets form
a tree; every other net is shared as before. `flat.chain` holds the chain ports.

The `eiron` line at 7.2 ore/s a lane: cells 0 to 10 at 37.5/min, cell 11 at 19.5/min (52%).

## Checks

- Golden: 53 of 54 identical against 2.0.78. The one change is `agent/docs/examples/furnace-column.fk`:
  six drills (3 ore/s) feed eight furnaces with productivity modules (0.5625 ore/s each). The
  model had all eight at 67%. Now cells 0 to 4 run full, cell 5 at a third and cells 6 and 7 wait.
  That is what the belt does, as on the run's lab lines and the bus below. EXAMPLES.md says so.
- `tests/test_cells_within.py`: every ref form, `net each` both ways, nesting, the outer
  `n=auto`, the import, every refusal, and the model on a short line, a short bus, and the bus as
  measured.
- Full suite: `Ran 1367 tests in 251.444s`, OK.

## Lab, on a laptop server (`LaptopServer("cells")`, fk-play)

**The bus** (`tests/nest/bus.fk`): eight `SmeltColumn`s, each a Stack of three `FurnaceCell`s
with the ore along its foot, stacked east; `net each plates` takes each column's plates to its own
chest. 509 entities, all 120 nets routed, diff ok 509.

One requester and its inserter fed it 5.78 ore/s, short of the 15 the 24 furnaces take. Over
120 s, plates/min per furnace (cells 0, 1, 2), measured against the model at the measured feed:

| column | measured | model |
|---|---|---|
| 0 | 37.5 37.5 37.5 | 37.5 37.5 37.5 |
| 1 | 37.5 37.5 37.5 | 37.5 37.5 37.5 |
| 2 | 37.5 24.5 0 | 37.5 23.5 0 |
| 3 | 31.0 0 0 | 30.5 0 0 |
| 4 | 15.5 0 0 | 15.2 0 0 |
| 5 | 7.5 0 0 | 7.6 0 0 |
| 6 | 4.0 0 0 | 3.8 0 0 |
| 7 | 2.0 0 0 | 3.8 0 0 |

Each splitter along the foot sends half of what reaches it up its column. The last column's
belt runs on to a dead end, which takes half until it is full (some 100 items at 0.03/s), so its
2.0 is on the way to the model's 3.8. A second build, run 9 minutes first, got 5.18 ore/s and the
same shape: columns 3 to 6 at 24.0, 12.0, 6.0 and 3.0 to the model's 24.8, 12.4, 6.2 and 3.1.

The model before this release had every furnace at 38%: 14.4/min each.

**The lab field** (`tests/nest/labs.fk`): four `LabColumn`s, each a Stack of six `LabCell`s
with a red and a green header along its foot, chained east. 232 entities, all 84 nets routed,
diff ok 232. The lab force researched logistics-2 (30 s units at speed 3.5: 7 packs/min of each
a lab). Two requesters and their inserters fed 114 packs/min of each, for 24 labs that take 168.
Working share per lab over 60 s, bottom to top:

- column 0: 1.00 1.00 1.00 1.00 1.00 1.00
- column 1: 1.00 1.00 1.00 0.35 1.00 0.00
- column 2: 1.00 1.00 1.00 0.98 0.00 0.00
- column 3: 0.98 1.00 0.00 0.00 0.00 0.00

16.3 labs' worth, the feed's 114/min. Each column fills from the bottom and the last labs wait,
as the furnaces do. The model has no per-lab prediction: a lab is a sink, and the model gives the
field's total (114/min at this feed).

## Found, not changed

- A requester of two items (`item="a, b"`) feeding two nets loads each net with an unfiltered
  inserter, so both belts carried green packs and the red labs starved. The lab field uses a
  chest per pack.
- The router can't split a belt of two paired lanes (`r | g`) to two ports ("its two lanes come
  in paired, and no straight belt runs on"). `LabColumn` carries red and green on two header
  belts, which the router joins into each column.
- `assert X.rate` on a sealed module instance fails in the model (a `KeyError` on its ports).
- The rate model's per-net rows for a net between two ports show 0 (the each nets among them);
  the machines' rates are right.
- Labs are sinks, so the model doesn't serve them in order; a lab field's last labs aren't
  predicted.
