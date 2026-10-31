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
| `Machine<entity, recipe>` | one machine of any crafting building: an assembler, a furnace, a chemical plant, a refinery, a centrifuge (`Machine<entity=centrifuge, recipe=uranium-processing>`). `machine=` is the same as `entity=`. A furnace may take `ore=` in place of `recipe=`; a burner takes `fuel=` (coal if not given). A recipe with a fluid the building has no fluid box for is refused (`no-fluidbox`): an assembling-machine-1 never runs lubricant | inserters, and pipes for fluids |
| `Assembler<recipe>`, `Furnace<recipe>` (or `ore=`), `ChemPlant<recipe>`, `Refinery` | kinds of `Machine` from the prelude (below): an assembling-machine-1, a stone furnace on coal, a chemical plant, an oil refinery on basic oil processing. `machine=` changes the building: `Assembler<recipe=gear, machine=assembling-machine-2>` | as `Machine` |
| `Entity<name=small-lamp>` | any other building that moves no items: a lamp, a speaker, a display panel, a beacon. It is placed, powered and wireable; its size, power and circuit connectors come from the game | wires |
| `Chest<provider, limit=4>`, `Chest<requester, item=iron-plate, rate=2/s>`, `Chest<storage>`, `Chest<plain>` | a logistic chest: the robots' end of a net (`plain`: an iron chest off the network; `max=` on a requester caps its request: the request's count is never above it, and a changed request on a standing chest is laid again by the next `fk build`). `limit=` is how many slots it fills (its bar in the game): what feeds a full chest stops. A requester takes several items too: `item="iron-plate,copper-plate"`; `trash` on a requester sends back what it no longer asks for. A requester can drive a net (it feeds what's on the net); a provider or storage chest is only a net's end (the first lead run's `net packs: px -> lab` with a provider `px` said cannot-carry). A product's chest is best a provider: robots put leftovers of any item into the nearest storage chest, and those fill its slots | |
| `OffshorePump<rate=1200/s>` | water from the lake: it stands on the shore, open to the water (rot 3 faces west, water west of it) | pipes |
| `Boiler<fuel=coal>` | one boiler, 3x2: water in and out at its short ends, steam out of its long north side (rot 0), coal by an inserter beside it; 60 steam/s on 0.45 coal/s | pipes |
| `SteamEngine` | one steam engine, 3x5 standing (rot 0): steam at both short ends, so engines join end to end; 900 kW on 30 steam/s, two per boiler | pipes |
| `Pumpjack<n>`, `ChemPlant<recipe>`, `Refinery<recipe>` | fluid machines (`ChemPlant` and `Refinery` are `Machine`s). A machine that makes several fluids (`Refinery<recipe=advanced-oil-processing>`, the cracking plants) puts each on the net whose consumers take it: `net heavy: ref -> hcrack` carries only the heavy oil | pipes, one per fluid |
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

`machine=auto` and `modules=auto` leave a choice to the same step. `machine=auto` picks from the
kind's `tiers` line in the prelude (Kinds and the prelude, below): machines of one size, energy and
fluid boxes, so a cell's layout holds. That is assembling-machine-1, -2 or -3 for an assembler, and
stone or steel for a burner furnace. On a fluid recipe it picks only machines with the fluid boxes.
`modules=auto` picks no modules, speed modules, or
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

## Laid out, not built: `dnp`

DNP is "do not populate", as on a circuit board. A DNP piece keeps its place and its routes, so
nothing else moves around it. It isn't built, though, and the model has nothing of it: it makes,
takes and asks for nothing, and a DNP pole or roboport covers nothing. Turn it back on and it's
built where it was laid.

```
gears = Assembler<recipe=iron-gear-wheel, dnp> @(24, 12)   # on any instance, a module too
dnp mall1, sci3.packs                                       # or a line: any instance, any depth
col   = Stack<cell=FurnaceCell, n=12, built=8> @(4, 2)      # 12 cells laid out, the first 8 built
col   = Stack<cell=FurnaceCell, n=12, built=auto> @(4, 2)   # as many as the targets take, of 12
```

- **What goes with it.** Everything inside a DNP instance goes with it, along with each belt,
  pipe and inserter that served only DNP machines. A trunk that also feeds a live machine stays.
- **Uses.** It's the quick way to take something out for now, and it makes a scaling row.
  `built=` grows the line within the frame you laid out for all of it, and `built=auto` lets the
  size step choose how many to build.
- **In the build.**
  - `out\route.txt`: `dnp N entities laid but not built`.
  - `out\report_rates.txt`: what the DNP machines would make at full speed.
  - `out\report_bom.txt`: never counts them.
- **In the game.** A ghost of a DNP piece is cancelled. What already stands built on one stays
  until `fk build --confirm`, which takes it up. `fk look` says `dnp-standing` for those, and
  counts the rest as `dnp`.
- **From the command line.** `fk dnp world.fk sci3` writes the `dnp` line for you, and
  `fk dnp world.fk sci3 --off` takes it back off.

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
- `net NAME limited "WHY": ...` (also after `items a, b`) says your design limits what each maker
  puts on the net, and the string says how (2.1: `limited "each source loads while the loop holds
  less than its amount"`). It only quiets `CLOG` and `no-limit` for it: it limits nothing itself.
  The limits are `set` properties on the makers' hands (Properties on objects, below), or gates on
  a wire. `fk explain FILE NET` and `fk check` show the string; a bare `limited` still works, and
  `fk check` asks for the string on a sushi net (an `advice limited-why` line). `CLOG` stays the
  one warning a sushi net gets, and only `limited` clears it.
- `net NAME split: ...` (2.0.76, also after `items a, b`) gives each item of a mixed net a lane of
  its own: the net becomes one net per item, `NAME_<item>` (`blue_engine_unit`), paired two to a
  belt as `lanes` pairs in item order, and an odd last item gets a belt to itself. Each lane is
  loaded by its own inserter filtered to its item, and the router side-loads the two lanes
  together. A full lane holds only its own item, so it never stops the other: use it where `CLOG`
  says a mixed belt can fill, typically a requester of several items feeding makers by belt.
  Every inserter that loads a belt from a chest of several items is filtered to its net's items
  anyway (2.0.76), so nothing the net doesn't carry gets on the belt.
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

## Buffers

2.1. A buffer is a role: one net fills it and another drains it. The rate model treats it as an
unlimited supply to the nets it drives and an unlimited sink to the nets that feed it, and gives
what it gains or loses a minute as a `BUFFER` line (TOOLKIT.md).

```
b = Buffer                          # a steel chest; Buffer<chest=iron-chest, bar=20>
net ore_: drills -> b               # BUFFER b: +60.0/min iron-ore (filling: in 60.0, out 0.0)
net feed: b -> smelt                # draining when smelt takes more than the drills bring

module LoopEnd buffer size 3x3 {    # a module whose ports are a buffer's ends
  port i : in iron-plate @w1
  port o : out iron-plate @e1
  net t limited "a belt through": i -> o
}
```

- `Buffer` is a chest, the prelude's `kind Buffer = Chest<plain, hold, chest=steel-chest>`:
  `Buffer<chest=, bar=, item=>` (the chest, how many of its slots it may fill, and what it holds
  when no net says). Its items are what the nets into it carry.
- `module NAME<p> buffer size WxH { ... }` (parameters first, `buffer` before or after `size`): its
  ports are its ends on the outside nets.
  Its inside is yours, and the model doesn't join it to the outside. A buffer module needs ports.
- A buffer fed by an unbounded source (a requester with no rate) fills without end on paper,
  unless that net is gated (`when`): then the gate tops up what goes out, and the line is steady.
- A buffer never gets `no-taker` or `no-rate`, and a buffer whose nets are all `limited` gets no
  `SUSHI_LIMIT`. A sushi net with a buffer on it gets no `SUSHI_SINK`: what no machine takes ends
  in the buffer, or goes round by it. `CLOG` stays.

**Sushi patterns.** A mixed belt runs while no item piles up. Three ways that work, each written
`limited "..."`:

- one inserter from a buffer straight into each machine: it takes only what the machine uses;
- sources gated on what the buffer holds of their item: `wire bw red: b` and
  `net s_fe: fe -> b when bw.iron-plate < 40`;
- a loop: the machines take from one belt, its end goes into an end buffer that feeds its head,
  and each source loads only while the loop (the belt read `hold-all` plus the end buffer, on one
  wire) holds less than its amount. The belt never stops. A circuit wire reaches 9 tiles, so
  chain the wire from the reader belt by the end buffer to the sources.

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
  same item twice is one item on both. Two nets may feed the two lanes of a paired port, one item
  each (2.1.3): they share one belt to it as if you had written `lanes A | B`, and the module's own
  `lanes` line inside is enough. A pair or a lane pin on a fluid is refused ("pipes have no
  lanes"), and a net may name a port only in the module that declares it: naming one from outside
  the module is an error that says which `port` line to add.
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
  them. A crossing anywhere but a port is a `crosses-frame` line. Two sealed modules may overlap:
  an `overlap` line says where, and the tiles both frames cover are both modules' to route on,
  each in the way of what the other laid first. The module's
  internals are the module's own: a parent change never re-routes them (the same carriers, key for
  key, just moved), and `fk explain rib` shows both the template line and its plain entities.
- Width: a port is as wide as the belt just inside it carries its item: both lanes there make it
  a both-lane port (15/s on yellow), written `item | item` or not.

### Fluid ports

A port may carry a fluid (2.1): it is one pipe connection across the edge, with no lanes.

```
module PlasCell size 12x10 {
  port gas_in : in petroleum-gas @w4   # one pipe in at the west edge
  plas = ChemPlant<recipe=plastic-bar> @(5, 3)
  cq   = Chest<requester, item=coal, request=20> @(2, 1)
  pbx  = Chest<storage> @(9, 1)
  net g: gas_in -> plas
  net c: cq -> plas
  net p: plas -> pbx
}
gas  = InfinityPipe<fluid=petroleum-gas, rate=30/s> @(0, 4)
cell = PlasCell @(6, 0)
net gas: gas -> cell.gas_in
```

- Inside, the module's pipe reaches the tile inside the edge; outside, the parent's pipe reaches
  the tile outside. The two join across the edge, and the check sees one connected net.
- A fluid port carries one fluid: `in water, sulfur` is refused (a port each).
- It is `in` or `out`, the way its net runs; `inout` is refused.
- No lanes: a pair (`water | water`) or a lane pin (`@w4L`) is refused.
- Uranium ore takes sulfuric acid. On uranium an electric drill's fluid box is live, and a
  `MinerRow` there needs one acid an ore: give its net a pipe in. A burner drill can't mine it.

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
- A fluid port pair works the same way (2.1): `stack acid_in -> acid_out` runs one pipe through
  each cell, and each cell's pipe joins the next one's at their shared edge. Both ends must carry
  the same fluid. A cell of acid drills on uranium:

  ```
  module AcidDrill size 7x7 {
    port acid_in  : in  sulfuric-acid @w0
    port acid_out : out sulfuric-acid @e0
    port ore_in   : in  uranium-ore   @w6
    port ore_out  : out uranium-ore   @e6
    stack acid_in -> acid_out, ore_in -> ore_out
    d = MinerRow<n=1, resource=uranium-ore> @(0, 1)
    net a: acid_in -> d, acid_out
    net o: ore_in, d -> ore_out
  }
  ```

  A narrower cell can fail to route the ore (`UNREACHED`): the belt router merges a port's belt
  and a drill's ore only with room for a splitter.
- Reports list a stack's cells as `line/0`, `line/1` ...: each cell is an instance of its own.
- On a short line the cells nearest the feed run full and the last ones get what is left, as on
  the belt: `fk rates` says so cell by cell. Off a Stack's chain, a short net is shared evenly.

### One cell, every cell: `line[k]`, `line[*]`, `net each`

A cell's port that doesn't chain (each column's plates, say) is named through its cell:

- `line[2].g_out` is cell 2's port (cells count from 0), and `line[-1].g_out` the last cell's.
- `line[*].g_out` is every cell's port. In an ordinary net that is one net with all of them as
  endpoints: `net plates: cols[*].pl -> box` merges every column's plates.
- `net each NAME: A[*].P -> B[*].Q` is one net per cell, cell k of A with cell k of B, named
  `NAME_0`, `NAME_1` ... One side may instead name a list of ports, a sealed module's: port k
  takes cell k (`net each plates: cols[*].pl -> boxes`, where `Boxes` has eight `in` ports).
  Both sides need the same count, and neither may be `n=auto`.
- `[k]` follows a Stack and nothing else, an index past the last cell is refused, and `[*]` is
  written only in a net.

### Cells within cells

A cell may hold a Stack, so a module of Stacks can be stacked too:

```
module SmeltColumn<plate, ore> size 11x15 {
  port ore_in  : in  $ore | $ore @w12        # the ore along the foot, west to east
  port ore_out : out $ore | $ore @e12
  port pl      : out $plate      @s9         # this column's plates, a belt of their own
  stack ore_in -> ore_out
  s = Stack<cell=FurnaceCell, n=3, plate=$plate, ore=$ore> @(3, 0)   # room for the splitter
  net o: ore_in -> s.ore_in, ore_out
  net p: s.pl_out -> pl
}
cols  = Stack<cell=SmeltColumn, n=8, plate=iron-plate, ore=iron-ore> @(4, 0)
net feed: ore -> cols.ore_in
net each plates: cols[*].pl -> boxes           # eight belts, one per column
```

- The outer Stack's `n=auto` counts its cells (columns). A Stack inside a cell takes a number:
  every copy of the cell is the same.
- Where the foot splits into a column, the column gets half of what reaches it, and more when the
  rest of the foot can't take its half. On a short feed the first columns run full and each one
  after gets half of the one before; `fk rates` says so. On the lab, eight of these columns fed
  5.8 ore/s measured within a plate a minute of the model in every furnace of columns 0 to 6.
- `import SmeltColumn from "cells.fk"` brings the modules of that file it is built of
  (`FurnaceCell` here), unless your file has its own of that name.
- A lab field is built the same way: a `LabColumn` holds a Stack of `LabCell`s and the packs
  along its foot, which it chains east, and `Stack<cell=LabColumn, n=6>` makes the rectangle.
  The router doesn't split a belt of two paired lanes, so carry red and green along the foot on
  a belt each (`port r_in : in automation-science-pack @w20`, and one for green) and let the
  router join them into each column's belt. Feed each from a chest of its own.

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
  `signals=`, and any raw field, `cb.FIELD=` or `bp.FIELD=` (next section).
- `set NET: read=hold-all` (2.1; a net's name as the selector): the belt a wire reads on that net
  reads its whole belt, not one tile (`hold`, the default, and `pulse` too).
- Every `set` reports the hands it hit (`on 2 hands (~out/i0, ~out/i1)`), and one that matches
  nothing is a `no-match` line, never a silent no-op.
- A limit is real, but it does not quiet `CLOG`: a mixed belt quiets when you write the net
  `limited`.

### Any setting of any building: `cb.` and `bp.`

The properties above are the short way to write the common cases. Anything else a building can
be set to is written as the game's blueprint names it:

- `cb.FIELD=VALUE` writes one field of the building's control behaviour (what its circuit
  connection does): `cb.read_robot_stats=true`, `cb.circuit_condition="iron-plate<50"`.
- `bp.FIELD=VALUE` writes any other blueprint field: a speaker's `parameters` and
  `alert_parameters`, a display panel's `text`, a lamp's `color`, a train stop's `station`.

They go in a `set` line, or as parameters of an instance or a kind:

```
box  = Chest<storage>                                     @(2, 4)
spk  = Alarm<bp.alert_parameters={show_alert: true, show_on_map: true,
             icon_signal_id: iron-plate, alert_message: "Iron plates low"}>   @(6, 4)
note = Display<cb.parameters=[{condition: "iron-plate<50", icon: iron-plate, text: "Iron low"},
                              {condition: "iron-plate>=50", icon: signal-check, text: "Iron OK"}]> @(40, 4)
set spk: cb.circuit_condition="iron-plate<50"
wire stock red: box -> spk, note
```

A value is written like JSON:

- a number (`5`, `-2.5`), `true` or `false`;
- a string in double quotes (`"Iron plates low"`; it can't hold a double quote), or a bare word,
  which is a string too (`signal-C`, `global`);
- an object `{key: value, ...}` (a key is a word or a quoted string) or a list `[value, ...]`;
  they can span lines.

Two conveniences, anywhere in a value, so you write signals and conditions as elsewhere:

- a string in a field that holds a signal (a name ending in `_signal` or `signal_id`, or `signal`
  or `icon`) becomes the game's signal, typed from the game's list: `icon: iron-plate` is
  `{"type": "item", "name": "iron-plate"}`;
- a string in a field that holds a condition (a name ending in `condition`) is `S<N` or `S>=T` as
  `if=` takes it; spaces around the comparator don't matter (`"signal-A < 50"`).

An object is taken as written, so `{type: recipe, name: iron-gear-wheel}` picks a type by hand.

- **In a module**, `$p` works in a raw value as anywhere else: alone as a value
  (`bp.text=$label`), or inside a quoted string (`cb.circuit_condition="signal-A < $lo"`), at any
  depth of an object or a list.
- **Field names** are the game's, as a blueprint exports them; copy them from a blueprint string
  of a building you set up by hand (`fk look` or the game's export).
- **On a kind**, raw settings make a preset (see "Kinds and the prelude"); the instance's own field
  wins over its kind's, field by field.
- **On what**: any instance's buildings, or a selector's hands (`set gear.in: cb.FIELD=...`). A
  module instance takes none; set them on its machines, or pass a `$p` in.
- **A `cb.` field and a typed property** that write the same field (`if=` and
  `cb.circuit_condition`): the `cb.` one goes in the blueprint, and a `CIRCUIT` line says so.
- **Refused** (`CIRCUIT`): `bp.` for a field the build writes itself (`name`, `position`,
  `direction`, `recipe`, `tags`, `wires`, `type`, `control_behavior`: write `cb.` fields for that),
  a field set twice to two values, and a condition string that isn't one. `no-signal`: a signal
  name the game hasn't got, or one that never goes out on a wire where one is sent.
- **Drift**: a raw field changed in the game is a hand edit, named before the next paste, as any
  other setting is.
- **The rate model** takes a raw condition as always open, as it takes a `when` with no `cycle`:
  it doesn't know what a building's circuit does. Say what you expect in a `behave` block.

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
  reading reaches nothing until the belt is on a wire), or any building whose `cb.` settings make
  it send (a `RobotCounter`).
- **Any building with a circuit connector** can be a wire's end: a roboport, a pump, a lamp, a
  speaker, a display panel, a train stop, an `Entity` of any kind. One without a connector (a
  pipe, a beacon) is a `no-wire` line.
- `when A < N` on a net gates it: every inserter and pump of its route moves items only while it
  holds. On an instance, it enables the machine itself. `A` is `no-wire.no-signal` (that wire),
  `network.ITEM` (the logistic network's count, no wire) or `INSTANCE.no-signal` (what that chest
  or machine puts out, on a red wire of its own). The comparisons are `<`, `>`, `<=`, `>=`, `=`
  and `!=`, against a whole number or another signal on the same wire.
- Signals are every signal the game has, by name: virtual signals (`signal-A`, `signal-alarm`),
  items, fluids, recipes, entities, qualities, space locations and asteroid chunks; or the names
  you declare with `signal`. A name that is several (an item, its recipe and its building) is the
  item. `signal-each`, `-anything` and `-everything` read in a condition but never go out on a wire,
  so a `Constant`, a reading or a raw output signal that sends one is a `no-signal` line; the
  parameter signals and `signal-unknown` are refused anywhere.
- The build wires each wire net's entities by the shortest wires. A wire reaches 9 tiles (a big
  pole 32). **A longer one is carried on poles:** it hops along the poles of the area that carry
  no other wire of its colour, and where there is a gap the build adds a pole on a free tile
  (`circuit-poles/p1`, ...; the power cover's pole, else a medium pole), the fewest it can. The
  report says so (`wire stock red: 3 entities, 5 wires; on poles: spk/m0 to note/m0 34.0 tiles over
  3 poles (3 added)`). The added poles join the power network too. Only when no chain of poles
  and free tiles joins two ends is it a `wire-too-far` line.
- Two wires of one colour on one entity are one network in the game and their signals add
  (`wires-share`).
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

### Deciders and arithmetic combinators (2.1)

```
signal A = signal-A
signal S = signal-S
latch = Decider<if="green.A < 20 or (red.S > 0 and green.A < 80)", out="S=1"> @(6, 2)
double = Arithmetic<calc="green.A * 2", out="S"> @(9, 2)
wire level green: acc -> latch.in
wire hold  red:   latch.out -> latch.in       # its own output back in: a latch
```

- `Decider<if="...", out="...">`: `if` is the condition as 2.0's decider takes it, `or` between
  groups of `and` (`and` binds first). A group may stand in parentheses after an `or`; `(A or B)
  and C` is refused, since the game has no such grouping: write `A and C or B and C`. Each
  comparison is `SIGNAL OP N` or `SIGNAL OP SIGNAL`, with `<`, `>`, `<=`, `>=`, `=` and `!=`.
- `red.S` and `green.S` read one colour only; a bare `S` reads both.
- `out` lists what it sends while the condition holds, separated by commas: `S=1` sends 1, `S`
  sends the input's count of S.
- `Arithmetic<calc="A OP B", out="S">`: `A` a signal (or `each`), `B` a signal or a whole number,
  `OP` one of `+ - * / % ^ << >> AND OR XOR`, with spaces round it.
- A combinator has two sides: `x.in` reads and `x.out` sends. A wire's consumer end is `x.in`
  and its driver end `x.out`; the wrong side is a `no-wire` line, and a bare `x` takes the
  side its end needs.
- A wire from a combinator's `out` to its own `in` is allowed. It is a latch's memory.
- The strings take a module's parameters: `if="green.$in < $lo"` in a module with `in` and `lo`.
- A wire inside an unsealed module is named from outside by its path: `shedder.hold.S` in a
  `when`, `shedder.latch.in` as a wire's end. A sealed module (one with a size or ports) keeps
  its inside to itself.

### Combinators the language doesn't write yet: a Literal

Selector combinators, a machine's recipe set by a signal, and a requester's requests set by one
are not in the language yet. A `Literal` whose file is a blueprint string keeps every one of
them, with its settings and wires, as written. The circuit
auto mall is one: one assembler, one requester, one active provider and ten combinators that keep
a stock list full (`factorio-design\drafts\automall-20261030`, `gen_mall.py` writes it). Three
things the game does that a hand-written blueprint can get wrong (measured 2026-10-30):

- an assembler keeps no `input_networks` / `output_networks`: its recipe in and its ingredients
  out share every wire it is on;
- a requester takes its requests from the circuit with `"control_behavior":
  {"circuit_mode_of_operation": 1}`; `"set_requests": true` is ignored;
- a decider outputs `each` only when one of its conditions reads `each`.

**Names inside a Literal** (2.1). A JSON Literal file may name its machines: `"names": {"asm10":
37}`, a name (no dashes) to the index of an entity in the file (from 0; the blueprint's entity
order when the file holds only `"bp"`). `automall.asm10` is then a net end like any machine's:
`net out: automall.asm10 -> box`, and the router reaches it from outside the Literal. `fk explain`
lists the names. `fk capture` writes them (`asm1`, `furnace1`, `drill1`, ... in file order). A
name of an entity that is no machine is refused when a net uses it. A blueprint Literal keeps its
circuit settings (`if=`, `read=`, ...) and its wires; a wire longer than the game's 9 tiles is
dropped by the game.

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

## Kinds and the prelude

`kind NAME = KIND<params>` gives a kind, a module or another kind a name with some of its
parameters set. It goes at the top of a file, outside any module:

```
kind Asm2  = Assembler<machine=assembling-machine-2>
kind Gears = Asm2<recipe=iron-gear-wheel>
g = Gears @(4, 2)                    # an assembling-machine-2 on gears, named g
h = Gears<machine=assembling-machine-3> @(8, 2)   # the instance's own parameters win
```

The instance keeps its own name, so a net still names `g`. A kind can name a kind; a loop of
kinds is refused. `import Gears from "lib.fk"` brings in a kind, and a module from another file
brings the kinds of its file with it.

`tiers KIND: E1, E2, ...` lists what `machine=auto` may pick for that kind and the kinds built on
it, the first being the default:

```
tiers Assembler: assembling-machine-1, assembling-machine-2, assembling-machine-3
tiers Spin: centrifuge                # for kind Spin = Machine<entity=centrifuge>
```

Every entity on a line must have the same size, the same energy (electric or burner) and the same
fluid boxes at the same places, or the line is refused. An assembling-machine-1 goes with the -2
and -3: their boxes open only for a fluid recipe.

Every file gets the **prelude** without an import: `Assembler`, `Furnace`, `ChemPlant` and
`Refinery` are kind lines in it, with the tiers lines. It is `game\prelude.fk` in your run, over the
toolkit's own: a kind or tiers line in yours replaces the toolkit's of that name, and any name
yours doesn't have comes from the toolkit's, so kinds added in a new release reach you without a
copy. Change yours, or write a kind or tiers line of the same name in a file, and that file uses
yours. A prelude holds kind and tiers lines only.

## Module parameters

A module can take parameters, so one cell serves iron and copper:

```
module FurnaceCell<plate, ore> size 7x3 {
  port ore_in  : in  $ore   @s0
  port ore_out : out $ore   @n0
  port pl_in   : in  $plate @n6
  port pl_out  : out $plate @s6
  stack ore_in -> ore_out, pl_out -> pl_in
  f = Furnace<recipe=$plate, machine=electric-furnace> @(2, 0)
  net o: ore_in -> f, ore_out
  net p: pl_in, f -> pl_out
}
one  = FurnaceCell<plate=copper-plate, ore=copper-ore> @(0, 0)
iron = Stack<cell=FurnaceCell, n=12, plate=iron-plate, ore=iron-ore> @(10, 0)
kind CopperCell = FurnaceCell<plate=copper-plate, ore=copper-ore>
cu   = Stack<cell=CopperCell, n=12> @(20, 0)
```

- **Declaring.** `module NAME<p, q=default> size WxH`. A parameter without a default is required:
  an instance that leaves it out is refused, naming it. A default is a word, a number, a string
  or a list.
- **Writing one.** `$p` stands for p's value wherever a word may stand: an item in a port, a net's
  `items` or another list, a parameter value, a signal, a `set` value, and inside a quoted
  string (`file="$name.json"`). It never stands for an instance, net or port name, a position or
  the `size`: a `$` there is refused.
- **Values** are words, numbers or lists. There is no arithmetic.
- **Lists.** `ins=iron-plate|copper-cable` is a list. `$ins` spreads it where an item list goes;
  `$ins[0]` picks one item, so each ingredient can get a lane of its own. An index past the end is
  refused, with the list's length.

  ```
  module AsmCell<recipe, ins, out> size 7x3 {
    port i_in  : in  $ins[0] | $ins[1] @s0     # two ingredients, one belt, a lane each
    port i_out : out $ins[0] | $ins[1] @n0
    port o_in  : in  $out @n6
    port o_out : out $out @s6
    stack i_in -> i_out, o_out -> o_in
    a = Assembler<recipe=$recipe> @(2, 0)
    net i items $ins split: i_in -> a, i_out
    net o: o_in, a -> o_out
  }
  ```
- **Stacks pass them on.** A Stack gives every parameter other than `cell`, `n`, `head`, `built`,
  `duty` and `dnp` to each cell, and to the head when the head declares it. So a module can't
  declare a parameter of one of those six names. A Stack's `cell=` may name a kind of a module, as
  `CopperCell` above. The cell's ports are filled in before the Stack checks that each pair
  carries the same items.
- **Inside a module**, a parameter can pass one on: `f = FurnaceCell<plate=$plate, ore=$ore>`.
- **A cell names its machine.** Its size, inserters and pipes fit one machine's footprint, so it
  takes no size, and a machine of another footprint is another cell.
- **Rebuilds.** The values are part of each instance's line in the `.fkp`, so changing one
  re-lays the instance as a changed recipe does. `machine=auto` and `modules=auto` inside a cell
  are one choice for each set of values: the iron line and the copper line choose apart.
- Every module still takes `duty=` and `dnp`; any other parameter it doesn't declare is refused.

The prelude also has presets for buildings the language has no kind of, made of `Entity` and raw
settings. Add your own the same way, with no toolkit release:

| kind | is | what it does |
|---|---|---|
| `RobotCounter` | a roboport | puts its robots on its wire: `signal-X`/`-Y` logistic robots free/total, `signal-Z`/`-T` construction, `signal-R` roboports |
| `ColourLamp` | a small lamp | takes its colour from `signal-red`, `-green` and `-blue` |
| `Alarm` | a programmable speaker | a siren heard everywhere, and an alert on the map; give it `cb.circuit_condition` and its own `alert_message` |
| `Display` | a display panel | always shows its text, on the map too; give it `bp.text`, or `cb.parameters` (messages with conditions) |

## Power

The build script's `cover power` step adds the poles every factory needs; `floorplan
--bridge-power` joins factories to the plant's grid. Don't put poles in the source.

### Power domains (2.1)

A design with more than one `power` line has one electric network per line: a **domain**.

```
power main: cover all                 # everything no other domain names
power labs: cover field               # the lab field alone
sw = PowerSwitch @(1036, 1004) when hold.S = 0
copper feed: main -> sw.left
copper load: sw.right -> labs
```

- `power NAME: cover A, B` names instances, with their whole insides. A route's inserters go
  with the machine they feed or take from. `cover all` takes everything no other domain names.
  One `power` line is one network, as before.
- Each domain gets its own poles (`power-labs/p0`, ...). Poles are never wired across domains,
  and no pole is put where its supply area reaches another domain's machines. A machine with no
  such spot left is a `domain-overlap` line.
- `copper NAME: A -> B` lays a copper wire between two domains, or between a domain and a
  switch's side. It goes from the nearest pole in reach, or the build adds a bridge pole. Two
  domains joined with no switch are one network, and the report says so.
- `PowerSwitch` is a prelude kind. Its sides are `sw.left` and `sw.right`. It is closed (the
  sides joined) while its `when` holds.
- `Accumulator<read=S>` puts its charge (0 to 100) on its wire as S. The game charges a
  network's accumulators together, so one reads them all.
- Copper lines and domains are written at the top level, not inside a module.
- The checks: `no-source`, `power-short`, `switch-never` and `domain-overlap` (TOOLKIT.md, "The
  checks").
- The run stats split power by domain: `power by domain: labs made 0 W, used 1.8 MW; main made
  3.1 MW, used 1.2 MW`. A network the build didn't lay is `rest`.
