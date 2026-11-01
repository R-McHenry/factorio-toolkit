# Toolkit 2.1.19: the live run's 2.1 friction

From the live run's FRICTION.md and notes (`assessment-20261031\PLAN-2.2.md`): the lab feeds a
sealed module's open ports, a net may end into a Literal's own belt, unpinned ports are placed, a
build reads its source once, ground the terrain never read is named, a long route says how far it
is, and `fk adopt` floors tiles.

## The lab feeds a lone sealed module

`fk lab . NAME` on a file that is one sealed module and no instances now places that module at
(4, 4) on a plot 4 tiles wider each side (unless `--size` is given), and feeds every open port:

- an in belt port gets a `loader-1x1` on the tile outside the frame, fed by an infinity chest;
  a lane pair port (`items | right`) gets a belt with a loader and chest on each side, one item a
  lane;
- an out belt port gets a loader taking into an infinity chest that deletes what it gets;
- a fluid port gets an infinity pipe (`at-least` 100% for in, `at-most` 0 for out).

Every loader stands on one whole tile outside every frame. A port a net binds outside its module
is left alone, and so is one whose tiles are taken or inside a frame. The report says how many
ports were fed and which were skipped. `capture` leaves loaders out like the other lab sources.

Tried live: an LDS block (13 made), a lane pair circuit block (44 circuits), and plastic from a
fluid port (46 plastic).

## A net into a Literal's own belt (~4115k, Rory's 42-lab block)

A JSON Literal's `names` may name a belt. It is a belt end: a net into it is routed into the belt
from behind (name the first belt of the Literal's line), and a net out of it starts in front (name
the last) and carries what the net declares (`net out items iron-plate: blk.last -> box`). The
hand-over is no SPILL. Before, a named belt was refused as "no machine".

## Unpinned ports on one side (~4480k, LabArea)

A sealed module with several `@e` ports (no position) was left unplaced ("ports b_in and g_in share
the tile"), and every port net said "no driver role is placed". Each now takes a free tile until
the build chooses it facing its partner. The live run's LabArea with its three ports unpinned: 72 of
72 nets connected.

## A build reads its source once (~4300k)

world.fk was read by `elaborate` and again by `size`, so an edit during a build gave a layout of
half of each. The whole build now reads every source file as it first read it
(`fkcore.snapshot`), and at the end names any file that changed under it: build again to lay it.

## Ground the terrain has not read (~4245k)

The terrain file stopped at x480 and cu2p was routed on to x498, over cliffs, with nothing said.
`floorplan` now gives one `no-terrain` line for the entities on ground outside the terrain's area
(or in a chunk not generated when it was read), with the box and the `fk read-terrain --area` to
run.

## Route progress (~4525k)

A real paste routed for 15+ minutes with no output. The route step now prints a line every 30 s:
`route: 120s in, pass 1, net 17 of 42 (area/b)`.

## Already in 2.1

An `Assembler` on a fluid recipe with assembling-machine-1 is refused at elaborate (`no-fluidbox`).

## fk adopt floors tiles

`fk adopt` turned negative entity positions into tiles with `int()`, which moves them one tile
toward zero. It now floors them.
