# The factory language (`.fk`)

A factory file says what the factory is: its machines and its nets. Where everything goes on the
ground, the belts and the poles are the toolkit's job (`fk build`); you give each machine or line a
position.

```
# smelting.fk: iron ore into plates, on a line of furnace cells from your library
import FurnaceCell from "cells.fk"

ore   = MinerRow<n=4, resource=iron-ore>  @(10, 2, rot 2)     # 4 drills, turned 180
col   = Stack<cell=FurnaceCell, n=8, plate=iron-plate, ore=iron-ore> @(10, 12)   # 8 furnaces
box   = Chest<provider, limit=4>          @(30, 40)

net ore_:   ore -> col.ore_in             # the drills' ore goes up the line
net plates: col.pl_out -> box             # the plates into a provider chest (robots take them)
```

## Instances

`name = Kind<param=value, ...> @(x, y)` or `@(x, y, rot r)`. The position is the instance's
top-left tile inside the factory's plot; `rot` turns it r quarter turns clockwise (0 to 3).
`@patch(iron-ore)` instead of a position puts a miner row on that ore.

## The library

The language has a small core. The everyday kinds are source you can read and change:

- **the prelude** names the kinds every file gets (`Assembler`, `Furnace`, `Buffer`,
  `PowerSwitch`, ...) and what `machine=auto` may pick for them;
- **your `game\cells.fk`** holds the cells your lines are made of, most of them with parameters.

Both are `.fk` like any factory. Change them, copy a kind or a cell and rename it, or add your own.

### `Machine`: one machine of any building

```
cen  = Machine<entity=centrifuge, recipe=uranium-processing> @(4, 2)
plas = Machine<entity=chemical-plant, recipe=plastic-bar>    @(10, 2)
gear = Machine<entity=assembling-machine-2, recipe=iron-gear-wheel> @(16, 2)
```

- `Machine<entity, recipe>` is one machine of any crafting building the game has: the assemblers,
  the furnaces, the chemical plant, the refinery, the centrifuge. Its size, power, fluid boxes and
  rates come from the game's data.
- `machine=` is the same as `entity=`.
- A furnace may take `ore=` in place of `recipe=`. A burner takes `fuel=` (coal if not given).
- A recipe with a fluid the building has no fluid box for is refused (`no-fluidbox`): an
  assembling-machine-1 never runs lubricant. An assembling-machine-2 takes one fluid in and one
  out.
- The router lays its inserters, and its pipes for fluids. A single machine needs no cell: place
  it where you want it.

`Entity<name=...>` is any other building, one that moves no items: a lamp, a speaker, a display
panel, a beacon, a solar panel, a roboport you want on a wire. It is placed, powered and wireable;
its size, power and circuit connectors come from the game. A crafter is refused there (write
`Machine`).

### `kind`: a name with defaults

`kind NAME = KIND<params>` names a kind, a module or another kind with some of its parameters
set. It goes at the top of a file, outside any module:

```
kind Asm2  = Machine<entity=assembling-machine-2>
kind Gears = Asm2<recipe=iron-gear-wheel>
g = Gears @(4, 2)                                 # an assembling-machine-2 on gears, named g
h = Gears<machine=assembling-machine-3> @(8, 2)   # the instance's own parameters win
kind CopperCell = FurnaceCell<plate=copper-plate, ore=copper-ore>   # a kind of a module
```

- The instance keeps its own name, so a net still names `g`.
- A kind can name a kind, and a loop of kinds is refused. `kind Furnace = Furnace<fuel=wood>`
  builds on the prelude's `Furnace`.
- `import Gears from "lib.fk"` brings in a kind. Importing a kind of a module brings the module
  too, and a module from another file brings that file's kinds.
- Refused: a kind of `Literal` or `Bus`, a kind inside a module, and a kind and a module of one
  name.

### The prelude

Every file gets the prelude without an import. The toolkit's has these kinds:

| kind | is |
|---|---|
| `Assembler`, `Furnace`, `ChemPlant`, `Refinery` | `Machine`s: an assembling-machine-1, a stone furnace on coal, a chemical plant, an oil refinery on basic oil processing. `Assembler<recipe=gear, machine=assembling-machine-2>` changes the building |
| `Buffer` | a steel chest that is a buffer (Buffers, below) |
| `PowerSwitch`, `Accumulator` | for power domains (Power, below) |
| `RobotCounter` | a roboport that puts its robots on its wire: `signal-X`/`-Y` logistic robots free/total, `signal-Z`/`-T` construction, `signal-R` roboports |
| `ColourLamp` | a small lamp that takes its colour from `signal-red`, `-green` and `-blue` |
| `Alarm` | a programmable speaker: a siren heard everywhere, and an alert on the map; give it `cb.circuit_condition` and its own `alert_message` |
| `Display` | a display panel, always shown, on the map too; give it `bp.text`, or `cb.parameters` (messages with conditions) |

The last four are `Entity` with raw settings (Circuits, below). Add a preset of your own the same
way, with no toolkit release.

Your run has `game\prelude.fk`, and it lies over the toolkit's: a kind or tiers line in yours
replaces the toolkit's of that name, and any name yours doesn't have comes from the toolkit's, so
kinds added in a new release reach you without a copy. A kind or tiers line of the same name in a
file wins over both, for that file. A prelude holds kind and tiers lines only.

### `tiers`: what `machine=auto` may pick

```
tiers Assembler: assembling-machine-1, assembling-machine-2, assembling-machine-3
tiers Spin: centrifuge                # for kind Spin = Machine<entity=centrifuge>
```

`tiers KIND: E1, E2, ...` lists what `machine=auto` (or `entity=auto`) may pick for that kind and
the kinds built on it, the first being the default. The prelude has the lines for `Assembler`,
`Furnace` (stone or steel) and the rows.

- Every entity on a line has the same size, the same energy (electric or burner) and the same
  fluid boxes at the same places, or the line is refused. So whatever the size step picks fits
  the same cell. An assembling-machine-1 goes with the -2 and -3: their boxes open only for a fluid
  recipe.
- On a fluid recipe it picks only machines with the boxes: `Assembler<recipe=lubricant,
  machine=auto>` picks from the -2 and -3.
- `Machine<entity=auto>` with no kind has no tier line, and is refused: write a kind and a tiers
  line for it.

### Cells with parameters

A cell is a sealed module whose belts run straight across it, so cells in a line make one long
line (`Stack`, under "Modules with ports"). With parameters, one cell serves iron and copper:

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
  string (`file="$name.json"`, `if="green.$in < $lo"`). It never stands for an instance, net or
  port name, a position or the `size`: a `$` there is refused.
- **Values** are words, numbers or lists. There is no arithmetic.
- **Lists.** `ins=iron-plate|copper-cable` is a list. `$ins` spreads it where an item list goes;
  `$ins[0]` picks one item, so each ingredient can get a lane of its own. An index past the end is
  refused, with the list's length.

  ```
  module AsmCell<recipe, ins, out> size 7x3 {
    port in_in   : in  $ins[0] | $ins[1] @s0     # two ingredients, one belt, a lane each
    port in_out  : out $ins[0] | $ins[1] @n0
    port out_in  : in  $out @n6
    port out_out : out $out @s6
    stack in_in -> in_out, out_out -> out_in
    a = Assembler<recipe=$recipe> @(2, 0)
    net i items $ins[0]: in_in -> a, in_out
    net j items $ins[1]: in_in -> a, in_out
    lanes i | j
    net o: out_in, a -> out_out
  }
  ```
- **Stacks pass them on.** A Stack gives every parameter other than `cell`, `n`, `head`, `built`,
  `duty` and `dnp` to each cell, and to the head when the head declares it. So a module can't
  declare a parameter of one of those six names. A Stack's `cell=` may name a kind of a module, as
  `CopperCell` above. The cell's ports are filled in before the Stack checks that each pair
  carries the same items.
- **Inside a module**, a parameter can pass one on: `f = FurnaceCell<plate=$plate, ore=$ore>`.
- **A cell names its machine.** Its size, inserters and pipes fit one machine's footprint, so it
  takes no size, and a machine of another footprint is another cell. `machine=auto` inside a cell
  picks from one tier line, so every pick fits.
- **Rebuilds.** The values are part of each instance's line in the `.fkp`, so changing one
  re-lays the instance as a changed recipe does. `machine=auto` and `modules=auto` inside a cell
  are one choice for each set of values: the iron line and the copper line choose apart.
- Every module still takes `duty=` and `dnp`; any other parameter it doesn't declare is refused.

### Your `game\cells.fk`

Your run starts with these cells. The smelting cells make iron unless you say. Import the ones
you use: `import SmelterPair, AsmCell from "cells.fk"`.

| cell | what | ports |
|---|---|---|
| `FurnaceCell<plate, ore>` | an electric furnace, ore up one belt, plates down the other: one lane of plates, about 12 to a yellow lane | `ore_in`/`ore_out`, `pl_in`/`pl_out` |
| `FurnacePair<plate, ore>` | two electric furnaces facing each other across the plate belt: both lanes, 24 furnaces to a yellow belt | `oa_*`, `ob_*`, `pl_*` |
| `StoneFurnaceCell<plate, ore, fuel=coal>` | a stone furnace, ore and fuel on the two lanes of one belt | `f_in`/`f_out`, `pl_in`/`pl_out` |
| `SmelterPair<plate, ore, fuel=coal>` | two stone furnaces back to back on one ore and fuel belt, plates out both sides: 24 furnaces to a yellow lane of ore | `f_*`, `pw_*`, `pe_*` |
| `SmeltColumn<plate, ore>` | three FurnaceCells in a column, the ore along its foot; stacked east, a bus of plate belts (Cells within cells, below) | `ore_in`/`ore_out`, `pl` |
| `AsmCell<recipe, ins, out>` | an assembler, two ingredients on the two lanes of one belt (`ins=A\|B`), its product down the other | `in_*`, `out_*` |
| `AsmCell1<recipe, ins, out>` | the same with one ingredient; `GearCell` is a kind of it | `in_*`, `out_*` |
| `CircuitCell` | green circuits: three cable assemblers to two circuit assemblers, handing straight across. Two cells: 480 circuits/min | `wi_*`, `wo_*`, `cu_*`, `eo_*`, `ei_*` |
| `LabCell<packs>` | a lab, two packs on the two lanes of one belt (red and green unless you say) | `p_in`/`p_out` |
| `LabColumn<packs>` | six LabCells and a header of one belt a pack; stacked east, a lab field | `r_*`, `g_*` |
| `DrillCell<resource>` | an electric drill dropping its ore onto the belt through the cell: one lane, 15 drills to a yellow lane | `ore_in`/`ore_out` |
| `DrillPair<resource>` | two drills facing each other across the ore belt: both lanes | `ore_in`/`ore_out` |
| `WrappedDrillCell<resource>` | a DrillCell built from a wrapped machine (`drill.json`, one drill named `d`): the way to build cells of any machine you captured | `ore_in`/`ore_out` |
| `AcidDrillCell` | an electric drill on uranium, its acid through the cell on a pipe | `acid_*`, `ore_*` |
| `GateCell<item, items, amount=auto>`, `GateCellR` | a sushi loop's source: loads its item while the loop holds less than `amount` (`GateCellR` on the right lane) | `s_in`/`s_out` |
| `MallCell<recipe, items>` | a maker on a sushi loop, and its provider chest | `s_in`/`s_out` |
| `BeltEndBuffer<items>`, `ChestEndBuffer<items>` | a sushi loop's end buffer: a belt through, or a chest | `i`, `o` |
| `Hysteresis<in, out, lo, hi>` | a latch: `out` turns on below `lo` and off again above `hi` | none: name its parts (Power, below) |

On the lab each line made what the row it replaces makes, within 3% (the gear cell beat its row by
7%). They are yours: copy one, change its recipe, its ports' items or its machine, and rename it.
`fk explain FILE INST` shows any instance as its exact entities, with its size and where its belts
attach.

### Your `game\routing.fk`

Small pieces for steering the router: place one where a belt must go, and run the net through
it. Each is a sealed module (ports and one net), so the router lays each stretch on its own.
`import Waypoint, Merge, Split from "routing.fk"`.

| piece | what | ports |
|---|---|---|
| `Waypoint<item>` | one belt, 1x3: the net passes here | `i`, `o` (inout) |
| `Merge<a, b>` | two belts into one by a splitter; each item stays on the lane it came in on | `a`, `b` in, `o` out |
| `Split<item>` | one belt into two, by a splitter | `i`, `a`, `b` (inout) |
| `InlinePump<fluid>` | one pump in a pipe, 1x2: `net lub: oil -> pp -> engines` | `i`, `o` (inout) |

They run north to south; `rot 1` turns one to run east to west, `rot 3` west to east.

**Chained nets.** `net gear: gears -> wp -> red, belts` runs gear through the piece `wp`. A
chain's middle stages are pieces, one instance each, whose modules have `inout` ports: the first
one declared is the way in, the rest are ways out. The chain is one net laid in segments: `gear`
(to the way in) and `gear@wp` (from the way out); a piece with several ways out gives
`gear@sp.a`, `gear@sp.b`. The consumers after such a piece are shared, the first to its first
way out, and so on. A line under the net, `sp.b -> wp2 -> red`, takes one way out on to its own
pieces and consumers (a branch). The route step's `chain` line and `fk status` show the segments
together. Writing the segments as plain nets on the ports (`net a: x -> wp.i`, `net b: wp.o ->
y`) works too. Merge is not a chain piece: it joins two nets.

## Other kinds

| kind | what | belts |
|---|---|---|
| `MinerRow<n, resource>` | n electric drills facing a belt between them; 3 tiles per pair, 7 tall. `drill=burner-mining-drill, fuel=coal`: n burner drills in one row (2 tiles each, 5 tall), a fuel belt north with one inserter per drill: they mine without power. On uranium each drill takes one sulfuric acid an ore: give its net a pipe in. A burner drill can't mine uranium | the ore leaves at the row's head; a burner row's fuel comes in at its head too |
| `Lab`, `Lab<rate=2/min>` | one lab, its inserters laid like an Assembler's: several Labs around one multi-item requester chest each take their packs by one inserter, no belt | by inserters next to it |
| `Pole`, `Pole<pole=small-electric-pole>` | one pole, pinned: for a cell packed so tight that its pole's tile is part of its design (the power step keeps it and adds only what is missing) | none |
| `Roboport` | one roboport, 4x4: it takes construction and logistic robots into its robot inventory from a net, so the loader is a `Chest<requester, item="logistic-robot", request=50>` beside it and `net load: chest -> roboport`: the router lays the inserter. The kit's robots come out of a storage chest only into a roboport, so a build that takes up a roboport strands its robots until one of these stands again. `cover robots` counts it as coverage | by an inserter next to it |
| `Chest<provider, limit=4>`, `Chest<requester, item=iron-plate, rate=2/s>`, `Chest<storage>`, `Chest<plain>` | a logistic chest: the robots' end of a net (`plain`: an iron chest off the network). `limit=` is how many slots it fills (its bar in the game): what feeds a full chest stops. `max=` on a requester caps its request. A requester takes several items too: `item="iron-plate,copper-plate"`; `trash` on a requester sends back what it no longer asks for. A requester can drive a net (it feeds what's on the net); a provider or storage chest is only a net's end. A product's chest is best a provider: robots put leftovers of any item into the nearest storage chest, and those fill its slots | |
| `OffshorePump<rate=1200/s>` | water from the lake: it stands on the shore, open to the water (rot 3 faces west, water west of it) | pipes |
| `Boiler<fuel=coal>` | one boiler, 3x2: water in and out at its short ends, steam out of its long north side (rot 0), coal by an inserter beside it; 60 steam/s on 0.45 coal/s | pipes |
| `SteamEngine` | one steam engine, 3x5 standing (rot 0): steam at both short ends, so engines join end to end; 900 kW on 30 steam/s, two per boiler | pipes |
| `Pumpjack<n>` | crude oil. A machine that makes several fluids (`Refinery<recipe=advanced-oil-processing>`, the cracking plants) puts each on the net whose consumers take it: `net heavy: ref -> hcrack` carries only the heavy oil | pipes, one per fluid |
| `Reactor<read=temperature, signal=S>`, `HeatExchanger`, `SteamTurbine` | nuclear power: a reactor heats the exchangers it touches (`net heat items heat: reactor -> hx`, no route), 10 MW each, 103 steam/s for 1.7 turbines | pipes, an inserter for the cells |
| `InfinityPipe<fluid, rate=>` | a fluid from nowhere, for the lab only (its free materials) | pipes |
| `Pump<fluid=lubricant>` | one pump, 1x2, ending two nets: `net a: x -> pm` takes in at its back, `net b: pm -> y` leaves at its front (rot 0 pushes north). A pipe segment past 320x320 tiles carries nothing (`pipe-too-long`); a pump starts a new one. In a chain, use routing.fk's `InlinePump` | pipes |
| `Constant<signals="S=N, T=M">`, `Decider`, `Arithmetic` | combinators (Circuits, below) | wires |
| `Literal<file="x.json">` | entities exactly as given. The file: a blueprint string (`.txt`), JSON `{"bp": "0e..."}`, or an entity list `[{"name": "roboport", "x": 2, "y": 2, "direction": 0}]`. A listed entity sets itself too: `"request": {"logistic-robot": 50}` (a requester's request), `"recipe"`, or `"config"` (the game's fields as JSON). Its frame is its entities' box, so a lone roboport needs a pole of its own beside it. `fk capture` writes such a file from anything built: a lab slot, an area of the game or the planner, or an instance of your design. So a build made in the lab or by hand goes anywhere, inside a module too | |
| `Bus<belts=4, length, item, load=s11, tap=n26\|s33>` | Rory's bus: `belts` belts of one item, `length` tiles, running east at rot 0. Its loads and taps are ports (A bus, below) | one belt per port, beside the bus |

`duty=0.5` on any instance caps it (a machine that runs only part of the time). `modules=speed-module`
on a machine or row fills every module slot of its machines; `modules=productivity-module|speed-module`
names them slot by slot. The paste asks for them and the robots put them in, and `fk rates` counts
their speed and productivity. Slots: assembling-machine-2 2, assembling-machine-3 4,
electric-furnace 2, chemical-plant 3, oil-refinery 3, electric-mining-drill 3, pumpjack 2, lab 2,
beacon 2; an assembling-machine-1 or a burner has none. Productivity modules go only into the
recipes the game allows them in (intermediates, science packs, uranium fuel cells).

### Rows, the older way

`AsmRow<n, recipe>`, `SmelterRow<n, recipe>`, `LabRow<n>`, `SmelterArray<n, recipe>` and
`CircuitStack<n>` are rows the toolkit lays for you. They still build, exactly as before, and a
design that has them keeps working; they are not for new designs. Each has a library cell that
replaces it (`SmelterPair`, `FurnaceCell`/`FurnacePair`, `AsmCell`, `LabCell`/`LabColumn`,
`CircuitCell`), and `fk check` names it (`row-cell`). `MinerRow` is not one of these: it is the
drill line, and it is also what a drill cell holds (`DrillCell`, `DrillPair`): in a cell whose
frame its own belt would leave, a MinerRow lays no belt, and its drills drop their ore onto the
cell's through-belt. A row is **counterflow**: every belt of a row attaches at
its head, the west end at rot 0, so leave a few free tiles there.

`inserter=inserter` on a row puts plain inserters in place of the fast ones; `inserter=any` (or
`auto`, `whatever`) lets the build pick: the lowest hand the network can build now, and the
`hands` step raises the connectors whose flow needs a faster one (`out/avail.json`, written by
`report_bom --stock live`; `out/hands.txt` says what it took and why). A row without `inserter=`
does the same, so say `inserter=fast-inserter` only when you want fast hands and nothing else.
The router's direct insertion takes the same family, as `route --hand any` in the build script; a
single machine's `inserter=` does nothing (its inserters are the router's: that is what `--hand`
is for).

## Counts the build chooses: `n=auto`

`n=auto` on a `Stack` (its cells) or a `MinerRow` (and on the rows) leaves its count to the
build. The `size` step (right after `elaborate` in the build script) gives each auto line the
fewest machines, and each auto Stack the fewest cells, that meet:

- the surface file's `target` lines (what the whole surface makes),
- the factory's `assert INST.rate >= R` lines,
- what the line's consumers ask: a net an auto line drives carries what the machines on it take,
  and what a chest or labs with a `rate=` take. A chest or labs without a rate take what is
  left and ask nothing, so a line that only feeds those grows for a target or an assert,
- for `LabRow<n=auto, rate=...>`: the labs take what the science rows make.

A Stack's count is searched on the rate model itself: at each count the model measures every
target, assert and ask, one more cell goes to the Stack that gets them closest, and once they hold
each Stack gives back the cells it can spare. A cell can be any machines, so nothing is guessed
from a recipe: `col = Stack<cell=FurnaceCell, n=auto>` feeding a gear assembler that takes 3
plates/s gets five cells. `out\size.txt` says what each count serves.

`machine=auto` and `modules=auto` leave a choice to the same step. `machine=auto` picks from the
kind's `tiers` line (The library, above). `modules=auto` picks no modules, speed modules, or
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
import AsmCell, AsmCell1 from "cells.fk"
red   = Stack<cell=AsmCell, n=10, recipe=automation-science-pack,
              ins=copper-plate|iron-gear-wheel, out=automation-science-pack> @(16, 34)
gears = Stack<cell=AsmCell1, n=auto, recipe=iron-gear-wheel, ins=iron-plate,
              out=iron-gear-wheel>                                 @(30, 34)   # as red takes
fe    = Chest<requester, item=iron-plate, rate=4/s>                @(30, 50)
cu    = Chest<requester, item=copper-plate, rate=1/s>              @(14, 50)
box   = Chest<provider, limit=4>                                   @(20, 50)
net plates: fe -> gears.in_in
net gear:   gears.out_out -> red.in_in
net copper: cu -> red.in_in
net packs:  red.out_out -> box
```

`fk build --to size` shows the counts without laying anything out: `out\size.txt` lists each
line's count and what it serves (`net gear: iron-gear-wheel for red`, `target ... 1/s`), and
says when a constraint can't be met (`size`: a line at the top of its bounds, a requester chest at
its rate, a line whose count you wrote at full speed). `fk rates FILE.fk` sizes the same way before
it shows the rates. Counts sized to a rate balance a net exactly, so `fk rates` may name either
side of it as what binds (the ore is exactly what the furnaces' output needs).

Lines grow, and you arrange them: a line that grows runs further from its head, so leave it
room. When a sized line runs past its plot or into another instance, the size step says so
(`does-not-fit`, both and how far), and the build stops at `place` if their entities overlap.
After the routing, `report_rates` says (`size`) when a net of a sized line asks more than its belts
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
- **Uses.** It's the quick way to take something out for now, and it makes a scaling line.
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
  the limit belongs at each maker. Buffers, below, has the patterns that work.
- `net NAME limited "WHY": ...` (also after `items a, b`) says your design limits what each maker
  puts on the net, and the string says how (`limited "each source loads while the loop holds less
  than its amount"`). It only quiets `CLOG` and `no-limit` for it: it limits nothing itself. The
  limits are `set` properties on the makers' hands (Properties on objects, below), or gates on a
  wire. `fk explain FILE NET` and `fk check` show the string; a bare `limited` still works, and
  `fk check` asks for the string on a sushi net (an `advice limited-why` line). `CLOG` stays the
  one warning a sushi net gets, and only `limited` clears it.
- `net NAME split: ...` (also after `items a, b`) gives each item of a mixed net a lane of its own:
  the net becomes one net per item, `NAME_<item>` (`blue_engine_unit`), paired two to a belt as
  `lanes` pairs in item order, and an odd last item gets a belt to itself. Each lane is loaded by
  its own inserter filtered to its item, and the router side-loads the two lanes together. A full
  lane holds only its own item, so it never stops the other: use it where `CLOG` says a mixed belt
  can fill, typically a requester of several items feeding makers by belt. Every inserter that
  loads a belt from a chest of several items is filtered to its net's items anyway, so nothing the
  net doesn't carry gets on the belt.
- `net NAME any: ...` (also after `items a, b`) is connected when each driver reaches some
  consumer and each consumer is reached by some driver, instead of every driver reaching every
  consumer. Use it for a belt that passes through a module (in at one port, out at another,
  machines taking and adding on the way) and for an output that splits to two ends: there a
  driver past the split reaches only its own tail, and the plain rule would call the net
  `partly-connected`. It changes the check, not the route.
- `X.*` means X's free endpoints, the ones no other net holds yet: `net out: mall.* -> chest`.
- A machine is on at most one net per item and direction, with one exception: a single machine
  (`Assembler`, `Furnace`, a chest...) may take one item from several nets, each carrying only that
  item, as `CircuitCell`'s circuit assemblers take cable from two cable assemblers
  (`net k0: w0 -> wa` and `net k1: w1 -> wa, wb`). Each net gets an inserter of its own.
- Several drivers merge onto the net; several consumers split off it. The router lays the
  splitters.
- **Both lanes**: a net that carries more than one lane (7.5/s on yellow) is laid on both lanes of
  its belt, 15/s. The router splits its drivers into two groups by where they stand and side-loads
  each group onto its own lane at a join, then runs both lanes to every consumer: 24 furnaces in a
  row put 15 plates/s on one yellow belt. `net NAME width 2:` asks for it outright. One driver
  brings one lane (its belt's), except a two-sided MinerRow; when no join fits, the net goes on one
  lane and the route report says so.
- **Whole belts side by side**: `net plates width 8:` is 8 lanes, four belts side by side, laid as
  a ribbon (below). The width is 1, 2 or an even number. The router deals the drivers out at the
  head, in the order they stand, so that no belt gets more than its two lanes (15/s on yellow), and
  splits the consumers the same way: each belt runs from its own drivers to its own consumers. So
  it needs at least one driver and one consumer per belt; with fewer it says so, and a group of
  drivers too fast for one belt is refused.
- **The lane it ends on**: `net NAME lane L:` (or `R`) puts the net's items on that lane, looking
  downstream, where it ends on a belt (a row's input belt, a port, a bus). Into a machine by an
  inserter the lane does nothing: an inserter takes from both.

## Two nets on one belt: `lanes`

A belt has two lanes, and a net is one lane: a line puts its products on one lane of its belt (7.5
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
- A port of two items on a module (`port f_in : in iron-ore | coal`) is such a pair. Two nets may
  feed its two lanes, one item each: they share one belt to it as if you had written `lanes A |
  B`, and the module's own `lanes` line inside is enough.
- Two single-item nets that feed the same machines on two belts, a lane each, are the case to
  pair: half of both belts is empty. The build's `could-pair` check names the pair, whoever drives
  them; `SmelterArray` and `CircuitStack` are the exception, since they side-load two nets onto
  their own feed belts and want them apart.

## Belts side by side: ribbons

A **ribbon** is several belts laid side by side as one: belt k beside belt k+1, in order, all the
way. Rory's eight-column smelter bus is the case: eight columns of plates, eight belts running
together to a row of consumers.

- The nets of a `net each` are a ribbon already, belt k carrying net k: `net each plates:
  cols[*].pl -> boxes` lays eight belts side by side.
- `bundle NAME: a, b, c` makes a ribbon of nets you declared yourself, belt 0 carrying `a`. They
  must run the same way: their drivers on one side, their consumers on the other.
- A wide net (`width 8`, above) is a ribbon of its own belts.

```
net each plates: cols[*].pl -> boxes        # eight belts, side by side
net a: m1 -> c1
net b: m2 -> c2
bundle ab: a, b                             # a and b side by side, a on the left
net plates width 8: smelt -> users          # four belts, the smelters dealt out among them
```

What the router keeps:

- the belts stay adjacent and in order;
- a turn is nested, the inner belt turning first, and no belt crosses another;
- each belt goes under only what blocks its own line, with a tunnel of its own, and the rest stay
  on the surface beside it, still in order (a crossing that blocks them all takes every belt
  under together, side by side); a tunnel is straight, never through a turn;
- a tunnel reaches as far as the fastest tier `route --ug` allows (yellow 5 tiles, red 7, blue 9,
  turbo 11; `any`, the default, is the fastest the network can build, else yellow), and each one
  is laid with the slowest tier that reaches it;
- each belt joins the ribbon from the side, at its own place, and leaves it the same way: the
  outer belt first, at its own offset, and the rest don't close up.

A ribbon that finds no path is reported unrouted, every net of it; it is never split into loose
belts. Refused: a ribbon's nets running different ways, a net in two ribbons, a fluid net, a
`lanes` pair, a bus, a bundle of one net, and a width that is odd.

## Buffers

A buffer is a role: one net fills it and another drains it. The rate model treats it as an
unlimited supply to the nets it drives and an unlimited sink to the nets that feed it, and gives
what it gains or loses a minute as a `BUFFER` line (TOOLKIT.md). It is a choice, never a need: a
belt is already a small buffer, and a line that makes what its users take runs without one.

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
  ports are its ends on the outside nets. Its inside is yours, chests with inserters or just a
  belt through, and the model doesn't join it to the outside. A buffer module needs ports.
- A buffer fed by an unbounded source (a requester with no rate) fills without end on paper,
  unless that net is gated (`when`): then the gate tops up what goes out, and the line is steady.
- A buffer never gets `no-taker` or `no-rate`, and a buffer whose nets are all `limited` gets no
  `SUSHI_LIMIT`. A sushi net with a buffer on it gets no `SUSHI_SINK`: what no machine takes ends
  in the buffer, or goes round by it. `CLOG` stays.
- Uses: the end of a sushi loop (below); a mine or a smelter line well ahead of its users, filling
  a chest robots or a later line draw on; an output kept apart from its users, so a line can be
  rebuilt without stopping them; a batch for a slow user, about 20 of what it feeds.

**Sushi patterns.** A mixed belt runs while no item piles up. Three ways that work, each written
`limited "..."`:

- one inserter from a buffer straight into each machine: it takes only what the machine uses;
- sources gated on what the buffer holds of their item: `wire bw red: b` and
  `net s_fe: fe -> b when bw.iron-plate < 40`;
- a loop: the machines take from one belt, its end goes into an end buffer that feeds its head,
  and each source loads only while the loop (the belt read `hold-all` plus the end buffer, on one
  wire) holds less than its amount. The belt never stops. The library's `GateCell`, `MallCell` and
  `BeltEndBuffer` build it (EXAMPLES.md, `mall-loop.fk`).

**The amount.** `when W.ITEM < auto` on a net works it out from the netlist: every machine on the
loop that takes ITEM by its recipe adds 40 s of its take, and at least two crafts. `fk check` says
the number and the machines (`advice gate-auto`). A condition may also compare with a module
parameter (`< $amount`). An auto mall whose recipes change by circuit fixes none in the netlist:
its gate gets a `gate-auto` line and holds at 0, so write the amount there. `auto` on a machine's
own `when` is refused.

Tips from the lab: gate each source well above what one lap needs (80 iron, 40 copper and 40 gears
ran four machines at 91 to 100% of the model; 60/20/20 left the cable and belt machines at 83% and
76%). A source must bring what the machines take: a fast inserter loads about 2/s onto a belt, a
bulk inserter more. Give the bulk item a lane of its own (`GateCellR`): on one shared lane the
first source along the belt takes every gap. A ChestEndBuffer's contents are out of the gates'
sight, so the BeltEndBuffer suits a loop better. A circuit wire reaches 9 tiles, so chain the wire
from the belt by the end buffer to the sources (or let the build carry it on poles).

## A bus

```
bus   = Bus<belts=4, length=54, item=iron-plate, load=s11, tap=n26|s33> @(0, 10)
net iron1: smelt -> bus.load1          # a smelter line loads the bus
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
- A yellow belt carries 15/s on its two lanes, 7.5 each. A line that puts its plates on one lane
  brings at most 7.5/s to a load; the routed rates and `too-thin` say where a lane is full. Grow a
  bus longer and add ports; a second item is a second bus beside it (a gap row between them), and
  a net crosses a 4-belt bus by an underground from one of its outer rows to the other.
- For many belts that run together from many makers (a smelter bus), a ribbon may suit better:
  each column keeps a belt of its own (Belts side by side, above).

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

- `port NAME : in|out|inout ITEM [| ITEM2] [@side[pos][L|R]]`. A port is a **lane** of one belt
  end. `item | item2` is the two lanes of the pair; the same item twice is one item on both. A net
  may name a port only in the module that declares it: naming one from outside the module is an
  error that says which `port` line to add. `inout` marks a pass-through port, for a piece a net
  can run through (chained nets, under routing.fk above): it takes the way its outside net runs.
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
  each in the way of what the other laid first. The module's internals are the module's own: a
  parent change never re-routes them (the same carriers, key for key, just moved), and `fk explain
  rib` shows both the template line and its plain entities.
- Width: a port is as wide as the belt just inside it carries its item: both lanes there make it
  a both-lane port (15/s on yellow), written `item | item` or not.

### Fluid ports

A port may carry a fluid: it is one pipe connection across the edge, with no lanes.

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
- `left NAME: …` and `right NAME: …` before the entry's name choose the tap kind: `dual` is the
  belt strap, two lanes, 15/s; `left` is a lone underground exit at the stub, `right` an
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
full speed, where in the netlist it crosses, and what it actually got: the at-a-glance proof every
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
  Every other parameter goes to the cells (Cells with parameters, above).
- `line.P` names the head's port P; with no head, the first cell's NEAR port P or the last cell's
  FAR port P. The last cell's FAR ports are ends: nothing need come out of them.
- Inside a cell each belt runs **straight across**, port edge to port edge, with one inserter per
  machine (fast where it reaches, long-handed where only that does). A port of two items
  (`sulfur | chemical-science-pack`, with `lanes A | B` inside) is one belt that comes in already
  paired and runs on straight.
- `Pole` pins a pole where a cell is packed so tight that no other tile reaches its inserters; a
  straight belt tunnels under it. `docs\examples\blue6.fk` is such a cell.
- A fluid port pair works the same way: `stack acid_in -> acid_out` runs one pipe through each
  cell, and each cell's pipe joins the next one's at their shared edge. Both ends carry the same
  fluid. The library's `AcidDrillCell` is one, and `docs\examples\plastic-cell.fk` another.
- A drill drops its ore on the tile in front of it, so a cell's through-belt that passes that tile
  takes the ore with no inserter (`DrillCell`, 3x4). Two drills facing one belt tile fill both
  lanes (`DrillPair`, 3x7). A belt across takes the ore on its near lane; one in line, heading
  away from the drill or towards it, on its right lane (measured). A recycler drops its output the
  same way, and one whose drop tile no belt can reach is emptied by an inserter. A drill (or a
  recycler) whose drop tile is a chest or a machine of its net feeds it straight: the net lays
  nothing.
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
  Both sides need the same count, and neither may be `n=auto`. Its nets are laid as one ribbon
  (Belts side by side, above).
- `[k]` follows a Stack and nothing else, an index past the last cell is refused, and `[*]` is
  written only in a net.
- `assert cols[2].rate >= ...` is what that cell's machines make of its out ports' items, and
  `cols[2].pl.rate` the same for one port.

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
  The router doesn't split a belt of two paired lanes, so the header carries red and green on a
  belt each and the router joins them into each column's belt. Feed each pack from a chest of its
  own.

## Circuits

Circuit wires, conditions and limits are written in the source like nets; the build lays them
(inserter conditions, readings, filters, the red and green wires) and pastes them with the rest.
Change one and the next build writes it on what stands: no script sets them.

### Properties on objects: `set`

A limit is a property of an object, and the source names the object.

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
- `set NET: read=hold-all` (a net's name as the selector): the belt a wire reads on that net reads
  its whole belt, not one tile (`hold`, the default, and `pulse` too).
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
- **On a kind**, raw settings make a preset (the prelude's `RobotCounter`, `Alarm` ...); the
  instance's own field wins over its kind's, field by field. An object field is replaced whole.
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
- `when` enables the building types it always did; on a speaker or a display panel write
  `cb.circuit_condition`.

### The two shorthands, and when to write `set` instead

- `keep=N` on a maker = `set NAME.out: logistic=ITEM<N`. It reads the **logistic network** (robots
  needed) and leaves the maker crafting into its output buffer.
- `fill=N` on a maker = `set NAME.out -> CHEST: if=ITEM<N` **and** `set NAME.in: if=ITEM<N`, both on
  the chest's red wire: the chest's own count holds the hand that fills it and every hand that feeds
  the machine, so the machine stops at most one craft past N. No robots, and the tightest of the
  two: this is the one to reach for.
- Write `set` yourself when a maker feeds more than one consumer and the condition belongs to one
  of them (`set ins.out -> ibox: ...`), or when you want any other circuit property on one hand.

The same things written out, for older mall code:

| shorthand | the same thing, written out |
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
  `Accumulator<read=S>` its charge, `Constant<signals="S=N, T=M">` its signals, a combinator's
  `out`, a net (one of its belts reads what is on it; the reading reaches nothing until the belt
  is on a wire), or any building whose `cb.` settings make it send (a `RobotCounter`).
- **Any building with a circuit connector** can be a wire's end: a roboport, a pump, a lamp, a
  speaker, a display panel, a train stop, an `Entity` of any kind. One without a connector (a
  pipe, a beacon) is a `no-wire` line.
- `when A < N` on a net gates it: every inserter and pump of its route moves items only while it
  holds. On an instance, it enables the machine itself. `A` is `WIRE.SIGNAL` (that wire),
  `network.ITEM` (the logistic network's count, no wire) or `INSTANCE.SIGNAL` (what that chest
  or machine puts out, on a red wire of its own). The comparisons are `<`, `>`, `<=`, `>=`, `=`
  and `!=`, against a whole number, another signal on the same wire, a module's `$p`, or `auto`
  on a sushi gate (Buffers, above).
- Signals are every signal the game has, by name: virtual signals (`signal-A`, `signal-alarm`),
  items, fluids, recipes, entities, qualities, space locations and asteroid chunks; or the names
  you declare with `signal`. A name that is several (an item, its recipe and its building) is the
  item. `signal-each`, `-anything` and `-everything` read in a condition but never go out on a wire,
  so a `Constant`, a reading or a raw output signal that sends one is a `no-signal` line; the
  parameter signals and `signal-unknown` are refused anywhere.
- The build wires each wire net's entities by the shortest wires. A wire reaches 9 tiles (a big
  pole 32, a power switch 10). **A longer one is carried on poles:** it hops along the poles of the
  area that carry no other wire of its colour, and where there is a gap the build adds a pole on a
  free tile (`circuit-poles/p1`, ...; the power cover's pole, else a medium pole), the fewest it
  can. The report says so (`wire stock red: 3 entities, 5 wires; on poles: spk/m0 to note/m0 34.0
  tiles over 3 poles (3 added)`). The added poles join the power network too. Only when no chain
  of poles and free tiles joins two ends is it a `wire-too-far` line.
- Two wires of one colour on one entity are one network in the game and their signals add
  (`wires-share`).
- `no-signal` says a condition reads a signal nothing on its wire makes, or a name that is no
  signal; `no-wire` a wire nothing drives or reads.
- The build matches the world's wires to these: it adds the ones missing and cuts the ones between
  your entities that the source lacks (TOOLKIT.md, "The loop").

### Deciders and arithmetic combinators

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
  comparison is `SIGNAL OP N` or `SIGNAL OP SIGNAL`, with `<`, `>`, `<=`, `>=`, `=` and `!=`. A
  condition that ends with `and` or `or` is refused.
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
- A wire inside an unsealed module is named from outside by its path: `shed.hold.S` in a
  `when`, `shed.latch.in` as a wire's end. A sealed module (one with a size or ports) keeps
  its inside to itself. That is how the library's `Hysteresis` is used (Power, below).

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

### What the language doesn't write yet: a Literal

Selector combinators, a machine's recipe set by a signal, and a requester's requests set by one
are not in the language yet. A `Literal` whose file is a blueprint string keeps every one of
them, with its settings and wires, as written. The circuit auto mall is one: one assembler, one
requester, one active provider and ten combinators that keep a stock list full
(`factorio-design\drafts\automall-20261030`, `gen_mall.py` writes it). Three things the game does
that a hand-written blueprint can get wrong (measured 2026-10-30):

- an assembler keeps no `input_networks` / `output_networks`: its recipe in and its ingredients
  out share every wire it is on;
- a requester takes its requests from the circuit with `"control_behavior":
  {"circuit_mode_of_operation": 1}`; `"set_requests": true` is ignored;
- a decider outputs `each` only when one of its conditions reads `each`.

**Wrapped machines.** A Literal of one machine, with its own inserters, and a name for it is a
wrapped machine: a cell places it and names it in its nets (`net i: in_in -> w.a, in_out`), and
the router lays the cell's belts past its inserters' hands, or past a drill's drop tile. A
blueprint holds no ore, so a Literal's drills mine what `resource=` says
(`Literal<file="drill.json", resource=$resource>`). The library's `WrappedDrillCell` is one.

**Names inside a Literal.** A JSON Literal file may name its machines: `"names": {"asm10": 37}`, a
name (no dashes) to the index of an entity in the file (from 0; the blueprint's entity order when
the file holds only `"bp"`). `automall.asm10` is then a net end like any machine's: `net out:
automall.asm10 -> box`, and the router reaches it from outside the Literal. `fk explain` lists the
names. `fk capture` writes them (`asm1`, `furnace1`, `drill1`, ... in file order). A named
**belt** is a belt end: a net into it (`net r: rr -> labs.r_in`) is routed into the belt from
behind, so name the first belt of the Literal's own line; a net out of it starts in front of it
(name the last), and carries what the net declares (`net out items iron-plate: blk.last -> box`).
The Literal's inserters pick from its own belts as built. A name of any other entity that is no
machine is refused when a net uses it.

**Ports of a Literal.** A JSON Literal file may also name its ports, the way a module declares
them: `"ports": {"heavy": {"carrier": 12, "side": "e"}}`, a pipe, pipe-to-ground or belt of the
file (its index, from 0) and the edge of the frame it meets (`n`, `e`, `s`, `w`, in the file's own
frame; a turned Literal turns them). `plant.heavy` is then a net end on that edge: `net heavy
items heavy-oil: plant.heavy -> crack` starts on the tile beside the carrier across the edge, and a
net into a port ends there, flowing in. The carrier's whole group of touching pipes (or belts)
carries the net, so the router lays no other net beside it: a refinery's three outputs, each a
port, never short. With ports a Literal is a sealed piece, and a module around it (a wrapper, a
buffer) routes like any other. `fk capture` writes a port for each belt and pipe that crosses the
edge of what it captures, named by where it is: `n1` the westmost on the north edge, `e1` the
northmost on the east. The names describe the piece, not a recipe, so they hold when the recipe
inside changes; keep them.

A port carries what the Literal's own machines put on it or take off it, as their recipes say:
a pipe the fluid of the machine box it reaches (advanced oil's `n1` heavy oil; basic oil's `n1`
nothing), a belt what inserters put on it or take from it. So a net needs no `items`
(`net q: g.e1 -> out` carries the gears), a net of another item there is `cannot-carry`, and the
port drives at the rate of the machines behind it. A port nothing inside explains carries what
its net says.

A blueprint Literal keeps its circuit settings (`if=`, `read=`, ...) and its wires; a wire longer
than the game's 9 tiles is dropped by the game.

## Checks on paper

`assert INST.rate >= 10/min` (or `/s`, `/h`): checked by the rate model (`fk rates`); a failed one
is an `rate-not-met` line, not an error. With `n=auto` lines the build sizes them to meet it.

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

A module instance's machines are named with a dot: `left.smelt`. An import brings the kinds and
tiers lines of its file, and the modules a module or kind it names is built of.

## Power

The build script's `cover power` step adds the poles every factory needs; `floorplan
--bridge-power` joins factories to the plant's grid. Don't put poles in the source.

### Power domains

A design with more than one `power` line has one electric network per line: a **domain**.

```
import Hysteresis from "cells.fk"
power main: cover all                 # everything no other domain names
power labs: cover field               # the lab field alone
acc  = Accumulator<read=A> @(1030, 1004)
shed = Hysteresis<in=A, out=S, lo=20, hi=80> @(1032, 1004)
wire level green: acc -> shed.latch.in
sw = PowerSwitch @(1036, 1004) when shed.hold.S = 0
copper feed: main -> sw.left
copper load: sw.right -> labs
```

- `power NAME: cover A, B` names instances, with their whole insides. A route's inserters go
  with the machine they feed or take from. `cover all` takes everything no other domain names.
  One `power` line is one network, as before.
- Each domain gets its own poles (`power-labs/p0`, ...). Poles are never wired across domains,
  and no pole is put where its supply area reaches another domain's machines. A machine with no
  such spot left is a `domain-overlap` line. If robots join a pole to another domain's, the wire
  pass after the build cuts that wire.
- `copper NAME: A -> B` lays a copper wire between two domains, or between a domain and a
  switch's side. It goes from the nearest pole in reach, or the build adds a bridge pole. Two
  domains joined with no switch are one network, and the report says so. A copper line that can't
  be laid is a `copper` line.
- `PowerSwitch` is a prelude kind. Its sides are `sw.left` and `sw.right`. It is closed (the
  sides joined) while its `when` holds.
- `Accumulator<read=S>` puts its charge (0 to 100) on its wire as S. The game charges a
  network's accumulators together, so one reads them all.
- The library's `Hysteresis<in, out, lo, hi>` is a latch: `out` turns on when `in` falls below
  `lo` and stays on until `in` is back above `hi`, so the switch doesn't flicker round one
  threshold. It has no ports: wire `in` into `shed.latch.in` and gate on `shed.hold.OUT`.
- Copper lines and domains are written at the top level, not inside a module.
- The checks: `no-source`, `power-short`, `switch-never`, `domain-overlap` and `copper`
  (TOOLKIT.md, "The checks").
- The run stats split power by domain: `power by domain: labs made 0 W, used 1.8 MW; main made
  3.1 MW, used 1.2 MW`. A network the build didn't lay is `rest`.
