# The factory language (`.fk`)

A factory file says what the factory is: its machines and its nets. Where everything goes on the
ground, the belts and the poles are the toolkit's job (`fk build`); you give each machine or line a
position.

```
# smelting.fk: iron ore into plates, on a line of furnace cells of your own
import FurnaceCell from "cells.fk"

ore   = MinerRow<n=4, resource=iron-ore>  @(10, 2, rot 2)     # 4 drills, turned 180
col   = Stack<cell=FurnaceCell, n=8>      @(10, 12)           # 8 electric furnaces in a line
box   = Chest<provider>                   @(30, 40)

net ore_:   ore -> col.ore_in             # the drills' ore goes up the line
net plates: col.pl_out -> box             # the plates into a provider chest (robots take them)
```

## Instances

`name = Kind<param=value, ...> @(x, y)` or `@(x, y, rot r)`. The position is the instance's
top-left tile inside the factory's plot; `rot` turns it r quarter turns clockwise (0 to 3).
`@patch(iron-ore)` instead of a position puts a miner row on that ore.

## Lines of machines: your own cells

A line of machines is a **Stack of cells you write**. A cell is a `module` with ports: one slice
of the line, its belts running straight across it from edge to edge, so cells stacked edge to edge
make one long line (Stacks, below, has the rules). Your `game\cells.fk` starts with seven:

| cell | what |
|---|---|
| `FurnaceCell` | an electric furnace, ore up one belt, plates down the other: one lane of plates, about 12 to a yellow lane |
| `FurnacePair` | two electric furnaces facing each other across the plate belt: both lanes, 24 furnaces to a yellow belt |
| `StoneFurnaceCell` | a stone furnace, ore and coal on the two lanes of one belt |
| `SmelterPair` | two stone furnaces back to back on one ore and coal belt, plates out both sides: 24 furnaces to a yellow lane of ore. Several lines on one ore and coal pair make a big smelter (it replaces `SmelterArray`) |
| `CircuitCell` | green circuits: a column of cable assemblers beside a column of circuit assemblers, offset a row so each circuit assembler takes cable from two (3 to 2). Copper up the middle on both lanes, iron up the outer belts, circuits back down beside them. Two cells: 480 circuits/min (it replaces `CircuitStack`) |
| `GearCell` | an assembler, one ingredient in, its product out |
| `LabCell` | a lab, red and green packs on the two lanes of one belt |

They are yours: copy one, change its recipe and its ports' items, add modules or a machine, and
rename it. `import FurnaceCell from "cells.fk"` brings one into a factory, and `col =
Stack<cell=FurnaceCell, n=12>` lines up twelve. A single machine needs no cell (`Assembler`,
`Furnace`, `Lab`): place it where you want it, and the router lays its belts and inserters. Several
single machines on one net work too, and the router gives the net both lanes when it carries more
than one (Nets, below).

The built-in kinds:

| kind | what | belts |
|---|---|---|
| `MinerRow<n, resource>` | n electric drills facing a belt between them; 3 tiles per pair, 7 tall. `drill=burner-mining-drill, fuel=coal`: n burner drills in one row (2 tiles each, 5 tall), a fuel belt north with one inserter per drill: they mine without power | the ore leaves at the row's head; a burner row's fuel comes in at its head too |
| `Pole`, `Pole<pole=small-electric-pole>` | one pole, pinned: for a cell packed so tight that its pole's tile is part of its design (the power step keeps it and adds only what is missing) | none |
| `Lab`, `Lab<rate=2/min>` | one lab, its inserters laid like an Assembler's: several Labs around one multi-item requester chest each take their packs by one inserter, no belt | by inserters next to it |
| `Roboport` | one roboport, 4x4: it takes construction and logistic robots into its robot inventory from a net, so the loader is a `Chest<requester, item="logistic-robot", request=50>` beside it and `net load: chest -> roboport`: the router lays the inserter (2.0.16). The kit's robots come out of a storage chest only into a roboport, so a build that takes up a roboport strands its robots until one of these stands again. `cover robots` counts it as coverage | by an inserter next to it |
| `Assembler<recipe>` | one assembler | by inserters next to it |
| `Furnace<recipe>` | one furnace | |
| `Chest<provider, limit=4>`, `Chest<requester, item=iron-plate, rate=2/s>`, `Chest<storage>`, `Chest<plain>` | a logistic chest: the robots' end of a net (`plain`: an iron chest off the network; `max=` on a requester caps its request: the request's count is never above it, and a changed request on a standing chest is laid again by the next `fk build`). `limit=` is how many slots it fills (its bar in the game): what feeds a full chest stops. A requester takes several items too: `item="iron-plate,copper-plate"`; `trash` on a requester sends back what it no longer asks for. A requester can drive a net (it feeds what's on the net); a provider or storage chest is only a net's end (the first lead run's `net packs: px -> lab` with a provider `px` said cannot-carry). A product's chest is best a provider: robots put leftovers of any item into the nearest storage chest, and those fill its slots | |
| `OffshorePump<rate=1200/s>` | water from the lake: it stands on the shore, open to the water (rot 3 faces west, water west of it) | pipes |
| `Boiler<fuel=coal>` | one boiler, 3x2: water in and out at its short ends, steam out of its long north side (rot 0), coal by an inserter beside it; 60 steam/s on 0.45 coal/s | pipes |
| `SteamEngine` | one steam engine, 3x5 standing (rot 0): steam at both short ends, so engines join end to end; 900 kW on 30 steam/s, two per boiler | pipes |
| `Pumpjack<n>`, `ChemPlant<recipe>`, `Refinery<recipe>` | fluid machines. A machine that makes several fluids (`Refinery<recipe=advanced-oil-processing>`, the cracking plants) puts each on the net whose consumers take it: `net heavy: ref -> hcrack` carries only the heavy oil | pipes, one per fluid |
| `Reactor<read=temperature, signal=S>`, `HeatExchanger`, `SteamTurbine` | nuclear power: a reactor heats the exchangers it touches (`net heat items heat: reactor -> hx`, no route), 10 MW each, 103 steam/s for 1.7 turbines | pipes, an inserter for the cells |
| `Constant<signals="S=N, T=M">` | a constant combinator (Circuits, below) | wires |
| `Literal<file="x.json">` | entities exactly as given (the plant is one). The file: a blueprint string (`.txt`), JSON `{"bp": "0e..."}`, or an entity list `[{"name": "roboport", "x": 2, "y": 2, "direction": 0}]`. A listed entity sets itself too: `"request": {"logistic-robot": 50}` (a requester's request), `"recipe"`, or `"config"` (the game's fields as JSON). Its frame is its entities' box, so a lone roboport needs a pole of its own beside it. `fk capture` writes such a file from anything built: a lab slot, an area of the game or the planner, or an instance of your design. So a build made in the lab or by hand goes anywhere, inside a module too | |
| `Bus<belts=4, length, item, load=s11, tap=n26\|s33>` | Rory's bus: `belts` belts of one item, `length` tiles, running east at rot 0. Its loads and taps are ports (below) | one belt per port, beside the bus |

**Older kinds.** `AsmRow<n, recipe>`, `SmelterRow<n, recipe>`, `LabRow<n>`, `SmelterArray<n,
recipe>` and `CircuitStack<n>` are rows the toolkit lays for you. They still build, and a design
that has them keeps working; new lines are Stacks of your own cells. A row is **counterflow**:
every belt of a row attaches at its head, the west end at rot 0, so leave a few free tiles there.
`fk explain FILE INST` shows any instance as its exact entities, with its size and where its belts
attach.

`duty=0.5` on any instance caps it (a machine that runs only part of the time). `inserter=inserter`
on a row puts plain inserters in place of the fast ones; `inserter=any` (or `auto`, `whatever`)
lets the build pick: the lowest hand the network can build now, and the `hands` step raises the
connectors whose flow needs a faster one (`out/avail.json`, written by `report_bom --stock live`;
`out/hands.txt` says what it took and why). A row without `inserter=` does the same, so say
`inserter=fast-inserter` only when you want fast hands and nothing else. The router's direct
insertion takes the same family, as `route --hand any` in the build script; a single machine's
`inserter=` does nothing (its inserters are the router's: that is what `--hand` is for).

`modules=speed-module` on a machine or row fills every module slot of its machines;
`modules=productivity-module|speed-module` names them slot by slot. The paste asks for them and
the robots put them in, and `fk rates` counts their speed and productivity. Slots:
assembling-machine-2 2, assembling-machine-3 4, electric-furnace 2, chemical-plant 3,
oil-refinery 3, electric-mining-drill 3, pumpjack 2; an assembling-machine-1 or a burner has none.
Productivity modules go only into intermediate recipes (plates, circuits, science packs), as in
the game.

## Counts the build chooses: `n=auto`

`n=auto` on a `Stack` (its cells) or a `MinerRow` (and on the older rows, `SmelterRow`,
`SmelterArray`, `AsmRow` and `LabRow`) leaves its count to the build. The `size` step (right after
`elaborate` in the build script) gives each auto row the fewest machines, and each auto Stack the
fewest cells, that meet:

- the surface file's `target` lines (what the whole surface makes),
- the factory's `assert INST.rate >= R` lines,
- what the row's consumers ask: a net an auto row drives carries what the machines on it take,
  and what a chest or labs with a `rate=` take. A chest or labs without a rate take what is
  left and ask nothing, so a row that only feeds those grows for a target or an assert,
- for `LabRow<n=auto, rate=...>`: the labs take what the science rows make.

A Stack's count is searched on the rate model itself: at each count the model measures every
target, assert and ask, one more cell goes to the Stack that gets them closest, and once they hold
each Stack gives back the cells it can spare. A cell can be any machines, so nothing is guessed
from a recipe: `col = Stack<cell=FurnaceCell, n=auto>` feeding a gear assembler that takes 3
plates/s gets five cells. `out\size.txt` says what each count serves.

`machine=auto` and `modules=auto` leave a choice to the same step. `machine=auto` picks the tier,
of the machines the same size so a cell's layout holds: assembling-machine-1, -2 or -3 for an
assembler, stone or steel for a burner furnace. `modules=auto` picks no modules, speed modules, or
productivity modules where the recipe takes them. One line's choice holds for every copy of it, so
a choice inside a cell is one for the whole Stack. Of the picks that meet every target, assert and
ask (each with its counts sized), the cheapest wins. Cheapest means what the machines and modules
cost to build in raw resources (an assembling-machine-2 is 54; `fkcore.cost`). With `size
--payback 2h` in the build script it also counts what the design draws over two hours, for the rate
asked of it, which is where productivity modules pay off. Three gears a second cost least as three
assembling-machine-1s; over two hours, as two assembling-machine-3s with productivity modules.
`out\size.txt` says what was chosen and what came next.

`n=auto 4..30` keeps the count within 4 and 30; plain `auto` is 1 to 100. Write the counts you
want as numbers and leave the rest `auto`:

```
red   = AsmRow<n=10, recipe=automation-science-pack>  @(16, 34)    # ten red science
gears = AsmRow<n=auto, recipe=iron-gear-wheel>        @(16, 22)    # as many as red takes
smelt = SmelterRow<n=auto, recipe=iron-plate>         @(16, 12)    # as many as gears take
ore   = MinerRow<n=auto, resource=iron-ore>           @(16, 2, rot 2)
```

`fk build --to size` shows the counts without laying anything out: `out\size.txt` lists each
row's count and what it serves (`net gear: iron-gear-wheel for red`, `target ... 1/s`), and
says when a constraint can't be met (`size`: a row at the top of its bounds, a requester chest at
its rate, a row whose count you wrote at full speed). `fk rates FILE.fk` sizes the same way before
it shows the rates. Counts sized to a rate balance a net exactly, so `fk rates` may name either
side of it as what binds (the ore is exactly what the furnaces' output needs).

Rows grow, and you arrange them: a row that grows runs further east (at rot 0), so leave it
room. When a sized row runs past its plot or into another instance, the size step says so
(`does-not-fit`, both rows and how far), and the build stops at `place` if their entities overlap. After
the routing, `report_rates` says (`size`) when a net of a sized row asks more than its belts
carry: a yellow lane carries 7.5 items/s.

## Nets

`net NAME: drivers -> consumers`. A net is one belt (or one pipe; one lane of a belt two nets
share, below): the drivers put items on it, the consumers take them.

- A ref names an instance (`gears`): only the endpoints of the net's items count, so
  `net iron: smelt -> gears, circ` takes the plates of `smelt`.
- `net NAME items a, b: ...` declares the items; otherwise they are what the drivers make.
- Two or more items on one net is a **sushi** net. It runs while each item comes no faster than
  it is used; one that piles up fills the belt and stops the others (`CLOG`). Into a machine it
  must take every item (else `SUSHI_SINK`). One inserter from the source straight into each sink
  can't clog: it takes only what its sink accepts. A mall's products belt into one chest: the
  chest goes best without `limit=`, since a full chest stops the whole belt (`SUSHI_LIMIT`), and
  the limit belongs at each maker.
- `net NAME limited: ...` (also after `items a, b`) says your design limits what each maker puts
  on the net. It only quiets `CLOG` and `no-limit` for it: it limits nothing itself. The limits
  are `set` properties on the makers' hands (Properties on objects, below).
- `X.*` means X's free endpoints, the ones no other net holds yet: `net out: mall.* -> chest`.
- A machine is on at most one net per item and direction, with one exception: a single machine
  (`Assembler`, `Furnace`, a chest...) may take one item from several nets, each carrying only that
  item, as `CircuitCell`'s circuit assemblers take cable from two cable assemblers
  (`net k0: w0 -> wa` and `net k1: w1 -> wa, wb`). Each net gets an inserter of its own.
- Several drivers merge onto the net; several consumers split off it. The router lays the
  splitters.
- **Both lanes** (2.0.54): a net that carries more than one lane (7.5/s on yellow) is laid on both
  lanes of its belt, 15/s. The router splits its drivers into two groups by where they stand and
  side-loads each group onto its own lane at a join, then runs both lanes to every consumer: 24
  furnaces in a row put 15 plates/s on one yellow belt. `net NAME width 2:` asks for it outright.
  One driver brings one lane (its belt's), except a two-sided MinerRow; when no join fits, the net
  goes on one lane and the route report says so.
- **The lane it ends on**: `net NAME lane L:` (or `R`) puts the net's items on that lane, looking
  downstream, where it ends on a belt (a row's input belt, a port, a bus). Into a machine by an
  inserter the lane does nothing: an inserter takes from both.

## Two nets on one belt: `lanes`

A belt has two lanes, and a net is one lane: a row puts its products on one lane of its belt (7.5
items/s on yellow). `lanes A | B` puts two nets on one belt, A on its left lane and B on its right
(looking downstream):

```
net ore_: ore -> smelt
net fuel: coal -> smelt
lanes ore_ | fuel        # one belt into smelt: ore on the left lane, coal on the right
```

- Every machine on either net gets the shared belt: one input belt instead of two, and one
  inserter per machine takes from both lanes what the machine uses.
- The router brings the two nets together once, at a join where each is side-loaded onto its own
  lane (both lanes of a net side-loaded go onto one: a net from a two-sided MinerRow carries at
  most 7.5/s there), and lays them on together to every consumer.
- They stay two nets: a lane that backs up holds only its own item and never stops the other, so
  a shared belt draws no `CLOG` (a sushi net, two items on one net, does).
- A net shares a belt with one other net at most; fluids have no lanes.
- The `.fkp` records a shared belt as `net=ore_|fuel` and its inserters as `net=ore_+fuel`.
- `SmelterArray` shares its own feed belts: give it its ore and its fuel on two nets of their
  own, and it side-loads them onto its lanes.
- A row fed two items on two nets (a SmelterRow's ore and coal, a lab row's packs, an AsmRow's
  gears and circuits) is the case to pair: two belts there carry a lane each, and half of both is
  empty. The build's `could-pair` check names the pair when you leave it on two belts, whoever drives
  them; `SmelterArray` and `CircuitStack` are the exception, since they side-load two nets onto
  their own feed belts and want them apart.

## A bus

```
bus   = Bus<belts=4, length=54, item=iron-plate, load=s11, tap=n26|s33> @(0, 10)
net iron1: smelt -> bus.load1          # a smelter row loads the bus
net fe:    bus.tap1 -> gears, belts    # a tap feeds machines
net spare: bus.tap2 -> box
```

Rory's bus, "a river of iron, that you keep adding more iron inputs to, and pull iron out when
you need it". Its frame is `belts` + 2 tall: the belts are its rows 1..4 here, and rows 0 and 5
are where the ports' belts meet it. A port is a side and a tile along the bus, counted from its
head (where its belts start): `s11` is a load from the south whose belt comes in at x 11. The
sides are compass sides where you place it (in a module, as the module is written): `n` and `s`
for a bus running east or west, `e` and `w` for one running south or north. Nets name the ports in
order: `bus.load1`, `bus.tap1`, `bus.tap2`.

- A load merges into every belt by a staircase of splitters, one per belt, that fills the far belt
  first and then the next; a tap takes from the far belt first. Each staircase takes `belts` tiles
  along the bus beside its port's tile, and no two ports may share one.
- The router lays the belts to a load and from a tap, never the bus itself. A port no net names
  keeps its staircase and gets no belt.
- The bus is a net of its own, named as the instance. `fk rates` treats it as a pool: what the
  loads bring is what the taps share, by appetite. In the game the first tap along the bus takes
  its fill first, and a load after a tap never reaches it (`partly-connected` on the bus's net says so).
- A yellow belt carries 15/s on its two lanes, 7.5 each. A smelter row puts its plates on one
  lane, so one row into a load brings at most 7.5/s; the routed rates and `too-thin` say where
  a lane is full. Grow a bus longer and add ports; a second item is a second bus beside it (a
  gap row between them), and a net crosses a 4-belt bus by an underground from one of its outer
  rows to the other.

## Modules with ports (sealed)

A module that declares `port` lines or a `size` is **sealed**: its nets are its own, and the only way
in or out is a port. A sealed module with no ports is a closed block: only robots reach it. Its
contents must fit its `size`; a machine or belt past the frame is a `FRAME` line.

```
module GearRib size 16x10 {
  port iron : in iron-plate @w        # plates in at the west edge
  port gear : out iron-gear-wheel @e  # gears out at the east edge
  g = Assembler<recipe=iron-gear-wheel> @(4, 3)
  net fe: iron -> g
  net g: g -> gear
}
```

- `port NAME : in|out|inout ITEM [| ITEM2] [@side[pos][L|R]]`. A port is a **lane** of one belt end:
  `Belt[… ]` is retired (a belt end is two lanes). `item | item2` is the two lanes of the pair; the
  same item twice is one item on both. A fluid port is refused ("pipes have no lanes"), and a net may
  name a port only in the module that declares it: naming one from outside the module is an error
  that says which `port` line to add.
- `size WxH` is the module's frame, and a port is a place on that frame's **edge**: it takes no
  tile. The belt crosses the edge there, from the tile just outside to the tile just inside (the
  other way for an `out` port): the module's own route reaches the tile inside, the parent's the
  tile outside. The place is `pos` along the side if the declaration pins one (`@w4`: counted from
  0, the side's first tile is `@w0`), else the one facing what the port connects to. The build
  records it in the `.fkp` and keeps it; a pin always wins, and a port moved to another side is
  chosen again (both a `port` line, once). A machine standing on the tile inside or outside a port
  leaves its route nowhere to meet it: a `port` line (`fk check`).
- Inside a sealed module the internal nets route **inside the frame**, every tile of it theirs;
  outside, a parent's route meets the port from the other side of the edge. Two ports that meet on
  one edge (one module's `out` port against the next one's `in` port) need nothing laid between
  them. A crossing anywhere but a port is a `crosses-frame` line. The module's
  internals are the module's own: a parent change never re-routes them (the same carriers, key for
  key, just moved), and `fk explain rib` shows both the template line and its plain entities.
- Width: a port is as wide as the belt just inside it carries its item: both lanes there make it
  a both-lane port (15/s on yellow), written `item | item` or not.

### The bus's connection list

A `Bus` may bind its ports with a list instead of `load=`/`tap=` pins: each entry is a named net,
written in port order, and the direction comes from the netlist:

```
bus = Bus<belts=4, item=iron-plate>(
        in1: smelt.plate,     # a mouth: belt 1 fed in line at the head (a source)
        in2: smelt2.plate,
        fg:  gears.iron,      # a tap: an in port
        fb:  belts.iron) @(10, 20)
```

- A name that is `in1..in{belts}` is a **mouth**: the bus's own belt end at the head, fed in line.
- Every other entry is a staircase: a maker (or an `out` port) loads, a taker (or an `in` port)
  taps. It stands **in front of what it connects to**: a sealed module's port (at its pin, or the
  module's middle), or a row's head. It never stands before the staircase written ahead of it, so
  the list order is still the order along the bus; `length` follows. Every staircase is on the
  bus's north side (as written at rot 0), so put the spines on that side.
- Several buses may each have mouths (an `in1` each): every mouth's net is then named by its bus
  (`febus_in1`, `febus_in2`), and a single bus keeps the plain `in1`.
- `left NAME: …` and `right NAME: …` before the entry's name choose the tap kind (2.0.34): `dual` is
  the belt strap, two lanes, 15/s; `left` is a lone underground exit at the stub, `right` an
  underground entrance with its exit one row out, each one lane, 7.5/s, both delivering on the left.
- A tap written before any load is an `tap-too-early` line; a mouth is at the head, so it always counts first.

### The contract

`fk contract FILE` prints every sealed module's contract, generated from the rate model:

```
contract bus4ribs: 4 sealed instances
  rib0: out iron-gear-wheel 1.0/s via box0/c0 (got 1.0) | in iron-plate 2.0/s via bus tap n7 (got 2.0)
  rib1: out iron-gear-wheel 1.0/s via box1/c0 (got 1.0) | in iron-plate 2.0/s via bus tap n13 (got 2.0)
```

Each port shows its direction, item and the rate it needs (an `in` port) or makes (an `out` port) at
full speed, where in the netlist it crosses, and what it actually got — the at-a-glance proof every
rib is fed through the bus. `agent/docs/examples/bus4ribs.fk` is the four-rib base it was written for.

### Stacks: a line of cells

A **cell** is a sealed module whose ports come in pairs on opposite edges, so that cells stack in a
line. `stack NEAR -> FAR` pairs a port on the edge toward the line's head (NEAR) with the one on
the opposite edge at the same tile (FAR); one cell's FAR meets the next one's NEAR on their shared
edge, and the net between them lays nothing. Items flow as the ports say: a feed `in` at NEAR and
`out` at FAR runs head to tail, a product the other way runs tail to head.

```
module Cell size 9x3 {
  port f_in  : in  iron-plate      @s1       # the feed: in at the south edge,
  port f_out : out iron-plate      @n1       # on to the next cell at the north edge
  port g_in  : in  iron-gear-wheel @n7       # the product: from the cell beyond,
  port g_out : out iron-gear-wheel @s7       # back toward the head
  stack f_in -> f_out, g_out -> g_in
  a = Assembler<recipe=iron-gear-wheel> @(3, 0)
  net f: f_in -> a, f_out
  net g: g_in, a -> g_out
}
line = Stack<cell=Cell, n=12> @(0, 4)         # head=HEAD: a module before the first cell
net fe:  feed -> line.f_in                     # the first cell's NEAR port
net out: line.g_out -> box
```

- `Stack<cell=CELL, n=N, head=HEAD>` places N cells edge to edge, growing toward the FAR edge, and
  the head (optional) before the first. A head has a FAR port of each pair, as if it were a cell.
- `line.P` names the head's port P; with no head, the first cell's NEAR port P or the last cell's
  FAR port P. The last cell's FAR ports are ends: nothing need come out of them.
- Inside a cell each belt runs **straight across**, port edge to port edge, with one inserter per
  machine (fast where it reaches, long-handed where only that does). A port of two items
  (`sulfur | chemical-science-pack`, with `lanes A | B` inside) is one belt that comes in already
  paired and runs on straight.
- `Pole` pins a pole where a cell is packed so tight that no other tile reaches its inserters; a
  straight belt tunnels under it. `docs\examples\blue6.fk` is such a cell.
- Reports list a stack's cells as `line/0`, `line/1` ...: each cell is an instance of its own.

## Circuits

Circuit wires, conditions and limits are written in the source like nets; the build lays them
(inserter conditions, readings, filters, the red and green wires) and pastes them with the rest.
Change one and the next build lays the changed entities fresh: no script sets them.

### Properties on objects: `set`

2.0.27: a limit is a property of an object, and the source names the object. `keep=` and `fill=`
are still there, as shorthands that lower to exactly these lines.

```
set belt.out            : logistic=transport-belt<200   # the hands that take belts out
set ins.out -> ibox     : if=inserter<50                # only the hand whose sink is ibox
set ins                 : logistic=inserter<50          # the machine itself (stops crafting)
set pipe.out            : logistic=pipe<100             # a row, all its output hands
```

- A selector is an instance name, and then:
  - `NAME.out`: the hands that take its product out (its own output hands, and the hands further
    down a net it drives);
  - `NAME.in`: the hands that feed it;
  - `-> NAME`: narrow to the hands whose sink is that instance. Use it whenever a maker feeds more
    than one consumer, so the condition lands on the hand you mean and not on all of them.
- Properties: `logistic=ITEM<N` (the logistic network's count, no wire), `if=ITEM<N` (a circuit
  condition; name the chest with `-> CHEST` so it reads that chest), `filter=`, `read=`, `signal=`,
  `signals=`.
- Every `set` reports the hands it hit (`on 2 hands (~out/i0, ~out/i1)`), and one that matches
  nothing is a `no-match` line, never a silent no-op.
- A limit is real, but it does not quiet `CLOG`: a mixed belt quiets when you write the net
  `limited`.

### The two shorthands, and when to write `set` instead

- `keep=N` on a maker = `set NAME.out: logistic=ITEM<N`. It reads the **logistic network** (robots
  needed) and leaves the maker crafting into its output buffer.
- `fill=N` on a maker = `set NAME.out -> CHEST: if=ITEM<N` **and** `set NAME.in: if=ITEM<N`, both on
  the chest's red wire: the chest's own count holds the hand that fills it and every hand that feeds
  the machine, so the machine stops at most one craft past N. No robots, and the tightest of the
  two: this is the one to reach for.
- Write `set` yourself when a maker feeds more than one consumer and the condition belongs to one
  of them (`set ins.out -> ibox: ...`), or when you want any other circuit property on one hand.

### Migrating old mall code (2.0.27 spelled the same things out)

| was | the same thing, written out |
|---|---|
| `belt = Assembler<recipe=transport-belt, keep=200>` | `set belt.out: logistic=transport-belt<200` |
| `ins = Assembler<recipe=inserter, keep=1000>` feeding a chest **and** a row | `set ins.out -> ibox: logistic=inserter<1000` (name the chest: a shared belt must not carry the row's condition) |
| `x = Assembler<..., fill=50>` straight into a chest | `set x.out -> ibox: if=inserter<50` and `set x.in: if=inserter<50` |
| `pipe = AsmRow<n=2, recipe=pipe, keep=100>` | `set pipe.out: logistic=pipe<100` |

The rule of thumb: the condition lives on the hand that has the job; `-> NAME` picks that hand, and
the machine's own `logistic=` is the way to stop the craft.

### A crafter that switches recipes: `guard`

```
x = Assembler<recipe=iron-gear-wheel, guard>   @(10, 4)
```

`guard`: the machine puts its recipe's ingredients on a red wire to every inserter that feeds it,
and they take only those (their filters come from the wire). Switch the recipe and what they
carry follows in the game, so no hand is left holding the old item. A plain `inserter` can't
filter (`cannot-filter` says so); the fast inserters the router lays can.

### Wires, signals and conditions

```
signal temp = signal-T                            # a signal, pinned to a game signal
signal stop                                       # or left to the build (it says which)
reactor = Reactor<read=temperature, signal=temp>  @(2, 5)
k       = Constant<signals="stop=1, iron-plate=50"> @(0, 0)
wire fuel_ctl red: reactor -> fuel                # drivers -> consumers; red or green
net fuel: cells -> reactor  when fuel_ctl.temp < 550       # a gated net
gears = Assembler<recipe=iron-gear-wheel> @(9, 0) when network.iron-gear-wheel < 400
```

- `wire NAME red|green: drivers -> consumers`: one network of one colour. A driver puts signals
  on it: a chest its contents, `Reactor<read=temperature, signal=S>` its temperature,
  `Constant<signals="S=N, T=M">` its signals, a net (one of its belts reads what is on it; the
  reading reaches nothing until the belt is on a wire).
- `when A < N` on a net gates it: every inserter and pump of its route moves items only while it
  holds. On an instance, it enables the machine itself. `A` is `no-wire.no-signal` (that wire),
  `network.ITEM` (the logistic network's count, no wire) or `INSTANCE.no-signal` (what that chest
  or machine puts out, on a red wire of its own). The comparisons are `<`, `>`, `<=`, `>=`, `=`
  and `!=`, against a whole number or another signal on the same wire.
- Signals are virtual signals (`signal-A`, `signal-T`), items or fluids, by name, or the names
  you declare with `signal`.
- The build wires each wire net's entities by the shortest wires; a wire reaches 9 tiles
  (`wire-too-far` when two are further apart). Two wires of one colour on one entity are one
  network in the game and their signals add (`wires-share`).
- `no-signal` says a condition reads a signal nothing on its wire makes, or a name that is no
  signal; `no-wire` a wire nothing drives or reads.

### What a loop is meant to do: `behave`

```
behave fuel_saver on fuel_ctl {
    state coasting: T >= 550 and not reactor.burning
    require 550 > hx.min_temperature
    expect reactor.status = no_fuel in coasting
    cycle full_load: burning 200 s, coasting 450 s, cells 1 per 650 s
    fails dark: T < 500 and not reactor.burning
}
```

A control loop makes states a rate model can't show, such as a hot reactor with no fuel. A
`behave` block names them where you will look: `require` lines with numbers the catalog knows are
checked (`require-not-met`), and a gated net whose wire has no `cycle` is a `gate-open` line (the rate model
takes it as always open). The fuel saver above is the starter plant's: the reactor loads a cell
only below 550 C, so its fuel slot is empty while it coasts, and that is normal.

## Checks on paper

`assert INST.rate >= 10/min` (or `/s`, `/h`): checked by the rate model (`fk rates`); a failed one
is an `rate-not-met` line, not an error. With `n=auto` rows the build sizes them to meet it.

## Modules and imports

```
import FurnaceCell from "cells.fk"
module Smelting {                 # a reusable part, written like a factory
  ore   = MinerRow<n=4, resource=iron-ore> @(0, 0, rot 2)
  smelt = Stack<cell=FurnaceCell, n=8> @(0, 10)
  net ore_: ore -> smelt.ore_in
}
left = Smelting @(0, 0)
import Mall from "mall.fk"
```

A module instance's machines are named with a dot: `left.smelt`.

## Power

The build script's `cover power` step adds the poles every factory needs; `floorplan
--bridge-power` joins factories to the plant's grid. Don't put poles in the source.
