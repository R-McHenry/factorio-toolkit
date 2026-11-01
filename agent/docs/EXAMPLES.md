# Examples

Small factories that build cleanly, each in `docs\examples\`. Copy one into `game\`, give it
ground, check it on paper, build it:

```
copy docs\examples\library-lines.fk game\library-lines.fk
# in game\world.fk (your base's plot):   import Lines from "library-lines.fk"
#                                        lines = Lines @(6, 6) size 40x30
fk check library-lines.fk
fk rates library-lines.fk
fk build --to report_checks          # design only: read out\report_checks.txt
fk build                             # the paste
fk look 68,-42 108,-12
```

A factory goes in `world.fk`, your base's file: one plot, 2000x2000 tiles, so the ground is not the
limit. It can have a plot of its own instead: `import Gears from "gears.fk"` and
`gears = Gears @(70, -40) size 16x16` in `nauvis.fk`, at map coordinates, and it keeps its own
`.fkp`. `size WxH` is the factory's frame.

The examples that import cells take them from `cells.fk` beside them. `docs\examples\cells.fk` is
the library as the toolkit ships it; in `game\` your own `cells.fk` is used, with whatever you
changed in it. Each example also builds where it stands (`fk rates docs\examples\mall-loop.fk`).

## Five pieces of a base

These five use the language as it stands: lines are Stacks of cells, most of them from the
library, and the rest is the parts the router can't guess. Each one routes every net and connects
on paper; on paper alone they have no generator, so `NO_POWER` is the one line they share (in the
base, `floorplan --bridge-power` joins them to the grid).

### plastic-cell.fk: a cell of your own around a Machine

```
kind Plastics = Machine<entity=chemical-plant, recipe=plastic-bar>

module PlasticCell<fuel=coal> size 12x5 {
  port c_in    : in  $fuel         @s0
  port c_out   : out $fuel         @n0
  port gas_in  : in  petroleum-gas @s5
  port gas_out : out petroleum-gas @n5
  port p_in    : in  plastic-bar   @n11
  port p_out   : out plastic-bar   @s11
  stack c_in -> c_out, gas_in -> gas_out, p_out -> p_in
  plant = Plastics @(5, 1)
  net c: c_in -> plant, c_out
  net g: gas_in -> plant, gas_out
  net p: p_in, plant -> p_out
}

gas   = InfinityPipe<fluid=petroleum-gas, rate=80/s> @(7, 26)
coal  = Chest<requester, item=coal, rate=4/s> @(2, 26)
line  = Stack<cell=PlasticCell, n=4> @(2, 4)
box   = Chest<provider, limit=8> @(18, 26)
net fuel:    coal -> line.c_in
net gas_:    gas -> line.gas_in
net plastic: line.p_out -> box
```

A cell is yours to write when the library has none for the machine. `Machine` takes any crafting
building, and a `kind` gives it a name. The gas runs up through all four cells on one pipe (a
fluid port pair: each cell's pipe meets the next one's at their shared edge, and the nets between
them lay nothing), the coal up the west belt, the plastic back down the east one. On paper: four
plants at full speed, 480 plastic/min, on 80 gas/s and 4 coal/s. The `InfinityPipe` is the lab's
free gas: in the base the gas comes from a refinery's net. A cell names its machine: for an
assembler, write another cell.

### library-lines.fk: two lines of library cells

```
import SmelterPair, AsmCell1 from "cells.fk"

kind CableCell = AsmCell1<recipe=copper-cable, ins=copper-plate, out=copper-cable>

ore   = Chest<requester, item=copper-ore, rate=3/s> @(4, 2)
coal  = Chest<requester, item=coal, rate=0.3/s>     @(14, 2)
smelt = Stack<cell=SmelterPair, n=5, plate=copper-plate, ore=copper-ore> @(10, 8)
cable = Stack<cell=CableCell, n=3>                  @(30, 8)
box   = Chest<provider, limit=8>                    @(36, 22)

net ore_:  ore -> smelt.f_in
net fuel:  coal -> smelt.f_in
lanes ore_ | fuel
net plates: smelt.pw_out, smelt.pe_out -> cable.in_in
net wire:   cable.out_out -> box
```

The library's cells make iron unless you say. The smelter Stack passes `plate=` and `ore=` to
every SmelterPair, so they smelt copper; the cable line is a `kind` of `AsmCell1` with all three
of its parameters set. Ore and coal share one belt into the smelters, a lane each, and the two
plate belts of the SmelterPairs join into the cable line's feed. On paper: 3 ore/s make 180
plates/min, the three cable assemblers take 180 and make 360 cable/min. The ore runs a little
short of ten furnaces, and `fk rates` shows it where the belt does: the first four pairs at 98%,
the last at 89%.

### ribbon-bus.fk: four belts of plates, side by side

```
import SmeltColumn from "cells.fk"

ore  = Chest<requester, item=iron-ore, rate=7.5/s> @(0, 4)
cols = Stack<cell=SmeltColumn, n=4, plate=iron-plate, ore=iron-ore> @(4, 0)
box  = Boxes @(60, 30)

net feed: ore -> cols.ore_in
net each plates: cols[*].pl -> box
```

(`Boxes` is a sealed module of four provider chests with an `in` port each; the file has it.)

Cells within cells: each `SmeltColumn` is a Stack of three FurnaceCells with the ore along its
foot, and four columns stand side by side, sharing the ore. `net each` gives each column's plates
a net of its own, `plates_0` to `plates_3`, column k to the box's port k, and the router lays the
four belts as one ribbon: side by side, in order, through two bus turns, 179 belts.
`out\route.txt` has a `ribbon plates` line that says so. On paper the 12 furnaces make 450
plates/min, 112.5 to each belt. `fk look --design --zoom 4` shows it whole:

```
    0 +^Fv^FvFF+FF....
    4 v^Fv^FvFF+FF....
    8 v^Fv^FvFF.FF+...
   12 >>>>>>>>>>>>....
   16 ...>>>>>>>>>>>>v
   20 ............+..v
   24 ..............+v
   28 ...............v
   32 ...............C
cells: F furnace, C chest, ^ belt north, > belt east, v belt south, + pole, . free
```

On the lab, the eight-column bus this one is cut from fed each chest from its own column, traced
back in the game.

### power-shed.fk: a lab field behind a power switch

```
import LabColumn, Hysteresis from "cells.fk"

power main: cover all                 # everything the labs domain doesn't name
power labs: cover field               # the lab field, its own network

s1 = Entity<name=solar-panel> @(0, 0)          # and s2, s3, s4
acc  = Accumulator<read=A> @(0, 5)
acc2 = Accumulator         @(3, 5)

signal A = signal-A
signal S = signal-S
shed = Hysteresis<in=A, out=S, lo=20, hi=80> @(8, 6)
wire level green: acc -> shed.latch.in
sw = PowerSwitch @(12, 5) when shed.hold.S = 0

copper feed: main -> sw.left
copper load: sw.right -> labs

red   = Chest<requester, item=automation-science-pack, rate=1/s> @(18, 26)
green = Chest<requester, item=logistic-science-pack, rate=1/s>   @(18, 28)
field = Stack<cell=LabColumn, n=2> @(24, 6)
net r: red -> field.r_in
net g: green -> field.g_in
```

Two power domains: `main` (the solar panels, the accumulators and everything else) and `labs`
(twelve labs), whose only power comes through the switch. The library's `Hysteresis` is a decider
whose output feeds back to its input: the shed signal turns on when the charge falls below 20%,
and stays on until the charge is back above 80%, so the switch doesn't flicker round one
threshold. The switch is closed while nothing is shed. `out\cover_power.txt` gives each domain its
poles (`domain labs: cover power-labs ... 4 poles`) and lays the two copper lines, adding a bridge
pole for the labs' side. No `no-source`, `power-short` or `switch-never` line: the labs have a
source through the switch, and the switch's signal moves with the charge. On the lab the same
latch opened its switch at 19.2% charge and closed it at 79.6%, once each way.

### mall-loop.fk: a sushi mall that never stops its belt

```
import GateCell, GateCellR, MallCell, BeltEndBuffer from "cells.fk"

g1 = GateCellR<item=iron-plate,     items=iron-plate|copper-plate|iron-gear-wheel> @(4, 23)
g2 = GateCell<item=copper-plate,    items=iron-plate|copper-plate|iron-gear-wheel> @(6, 20)
g3 = GateCell<item=iron-gear-wheel, items=iron-plate|copper-plate|iron-gear-wheel> @(6, 17)
m1 = MallCell<recipe=iron-gear-wheel, items=iron-plate|copper-plate|iron-gear-wheel> @(6, 14)
m2 = MallCell<recipe=copper-cable,    items=iron-plate|copper-plate|iron-gear-wheel> @(6, 11)
m3 = MallCell<recipe=transport-belt,  items=iron-plate|copper-plate|iron-gear-wheel> @(6, 8)
m4 = MallCell<recipe=pipe,            items=iron-plate|copper-plate|iron-gear-wheel> @(6, 5)
e  = BeltEndBuffer<items=iron-plate|copper-plate|iron-gear-wheel> @(6, 2)

net l1 limited "the gates hold the loop": g1.s_out -> g2.s_in
...                                                  # l2 to l7, cell to cell
net back limited "the end buffer feeds the head": e.o -> g1.s_in
```

One belt of iron, copper and gears runs in a loop past four makers. Each gate loads its item only
while the whole loop (the belt, read whole, `hold-all`) holds less than its amount, and
`amount=auto` works that out from the makers' recipes: `fk check` says `auto holds iron-plate
below 160: 40 s of the 4/s its loop's machines take (m1/a, m3/a, m4/a)`, and 40 each of copper
and gears. The end buffer, a belt through, feeds what passed every maker back onto the head, so
nothing on the belt has nowhere to go. `fk rates` ends with a `BUFFER e` line per item, each
`steady`: the gates top up what the makers take. Iron, the bulk item, has the right lane to
itself (`GateCellR`); on one shared lane the first source along the belt takes every gap.

On the lab this file ran 30 game minutes: gears at 100% of the model, cable 99%, belts 90% and
pipes 100%, every maker crafting in every 2-minute window, so the belt never stopped. The loop held
about each gate's amount plus a hand of each item.

## More examples

These are older: most are written with rows, or as one factory fed by chests, before cells had
parameters. They still build, and they show the language's pieces one at a time; for a new design
take the line from the five above (a Stack of cells) and the shape from these. The rows in them
(`SmelterRow`, `SmelterArray`, `AsmRow`, `LabRow`, `CircuitStack`) are not for new designs:
LANGUAGE.md, "Rows, the older way", names the cell that replaces each. `MinerRow` is still the
drill line. `busbase.fk`, `blue6.fk` and `furnace-column.fk` are bases and lines of sealed
modules; the rest are single factories. The first three below together, next to the kit (whose grid the reactor feeds), give 9 nets,
all routed and connected, 0 SPILL.

### smelting.fk: ore to plates (26x26)

```
ore   = MinerRow<n=4, resource=iron-ore>   @(10, 2, rot 2)
coal  = MinerRow<n=2, resource=coal>       @(18, 2, rot 2)
smelt = SmelterRow<n=8, recipe=iron-plate> @(10, 12)
box   = Chest<provider, limit=4>           @(4, 22)

net ore_:   ore -> smelt
net fuel:   coal -> smelt
net plates: smelt -> box
```

On paper: 120 plates/min. The 4 drills give 2 ore/s and the 8 furnaces could take 2.5/s, so
the furnaces run at 80%, short of ore. The miner rows are turned (`rot 2`) so their ore leaves
west, where the router has room. It needs ore and coal under its drills: put its plot on the
patches.

### shared-belt.fk: ore and coal on one belt (26x23)

The same smelting with one input belt: `lanes ore_ | fuel` puts the ore on the belt's left lane
and the coal on its right.

```
ore   = MinerRow<n=4, resource=iron-ore>   @(10, 2, rot 2)
coal  = MinerRow<n=2, resource=coal>       @(18, 2, rot 2)
smelt = SmelterRow<n=8, recipe=iron-plate> @(10, 12)
box   = Chest<provider, limit=4>           @(4, 22)

net ore_:   ore -> smelt
net fuel:   coal -> smelt
net plates: smelt -> box
lanes ore_ | fuel
```

The router joins the two nets once, side-loading each onto its lane (`out\route.txt`: `routed
ore_|fuel: ... join 8,8 E (ore_ on the left lane, fuel on the right)`), and lays one belt on to
the row; each furnace's one inserter takes both. Two nets, not one sushi net: a lane that backs
up holds only its own item, so there is no `CLOG`. The routed rates show the ore's lane at 2 of
its 7.5/s, and that the furnaces are served in belt order: the first 6 run at full speed, the
7th at 40% and the last gets no ore.

### smelter-array.fk: Rory's smelter stack (33x50)

```
ore   = MinerRow<n=16, resource=iron-ore>     @(2, 0, rot 2)
coal  = MinerRow<n=2, resource=coal>          @(30, 0, rot 2)
smelt = SmelterArray<n=24, recipe=iron-plate> @(6, 12)
box1  = Chest<provider, limit=8>              @(4, 48)
box2  = Chest<provider, limit=8>              @(8, 48)
box3  = Chest<provider, limit=8>              @(12, 48)

net ore_:   ore -> smelt
net fuel:   coal -> smelt
net plates: smelt -> box1, box2, box3
```

7.5 plates/s from 24 stone furnaces on plain inserters, every furnace at full speed. Its ore and
plates attach at the foot of the array (the south side at rot 0) and its coal at the east end.
Three chests because one chest's inserter takes 2.5/s: the routed rates name the chests'
inserters as the critical connectors, at exactly their rate. At 48 furnaces it eats a full yellow
belt of ore (15/s); more than that, and it grows a second unit east, with its own ore and plate
belts.

### gears.fk: plates in, gears out, robots at both ends (16x16)

```
inbox = Chest<requester, item=iron-plate, rate=1.25/s> @(2, 2)
gears = AsmRow<n=2, recipe=iron-gear-wheel>           @(6, 2)
box   = Chest<provider, limit=4>                      @(2, 12)

net plates_in: inbox -> gears
net gear:      gears -> box
```

On paper: 37.5 gears/min, limited by the 1.25 plates/s the requester asks for (`rate=`). The
chest feeds the row with one inserter (a route of one inserter).

### beltless.fk: a first cell with no belts (13x7)

```
fe   = Chest<requester, item=iron-plate, request=400>  @(0, 0)
gear = Assembler<recipe=iron-gear-wheel>                @(2, 0)
red  = Assembler<recipe=automation-science-pack>        @(6, 0)
lab1 = Lab                                              @(10, 0)
cu   = Chest<requester, item=copper-plate, request=200> @(6, 4)
net fe:    fe -> gear
net gears: gear -> red
net cu:    cu -> red
net packs: red -> lab1
```

Every transfer is one inserter, laid by the router between the machines: a fast one across a
one-tile gap, a long-handed one across two or three, and **no belt at all**. On paper 6 packs/min;
built in the lab it measured 6.00/min against the model at both a one-tile and a three-tile spacing.
This is the shape of a first factory: chests in, nothing belted in or out. Give the machines 1 to 3
free tiles between them and the whole cell routes itself.

### red.fk: red science into labs (30x30)

```
iron   = Chest<requester, item=iron-plate, rate=1/s>   @(2, 2)
copper = Chest<requester, item=copper-plate, rate=1/s> @(2, 12)
gears  = AsmRow<n=1, recipe=iron-gear-wheel>          @(8, 2)
red    = AsmRow<n=3, recipe=automation-science-pack>  @(8, 12)
labs   = LabRow<n=3>                                  @(8, 23)

net plates: iron -> gears
net copp:   copper -> red
net gear:   gears -> red
net packs:  red -> labs

assert red.rate >= 9/min
```

On paper: 18 red science/min (three assemblers at full speed), the assert passes. `red` takes two
belts (gears and copper); every row's head is at x = 8, so the router has the columns 0..7 for
its belts. To grow it: more `red` (n=5), and a second `gears` row feeding the same `gear` net.

### sized.fk: the same red science, counted by the build (42x32)

```
iron   = Chest<requester, item=iron-plate, rate=2/s>    @(2, 2)
copper = Chest<requester, item=copper-plate, rate=1/s>  @(2, 12)
gears  = AsmRow<n=auto, recipe=iron-gear-wheel>         @(8, 2)
red    = AsmRow<n=auto, recipe=automation-science-pack> @(8, 12)
labs   = LabRow<n=auto, rate=6/min>                     @(8, 23)

net plates: iron -> gears
net copp:   copper -> red
net gear:   gears -> red
net packs:  red -> labs

assert red.rate >= 60/min
```

`fk build --to size` (`out\size.txt`): `sized: gears n=1 (auto), red n=10 (auto), labs n=10
(auto)`. Ten red assemblers make the asserted 1 pack/s, one gear assembler makes the 1 gear/s
they take, and ten labs at 6 packs a minute each (a 10 s research unit) take what the red rows
make. A higher assert, or a `target automation-science-pack 1.5/s` line in the surface file,
grows them as far as the plates allow: the requesters' rates are what 1 pack/s takes (2 iron for
its gear, 1 copper), and `size` names the requester that stops it until the `rate=` go up. The
rows grow east: the 42x32 plot holds 11 of each, and `does-not-fit` says when one runs past it. On paper:
4 nets, all routed and connected.

### mall.fk: a mall of single machines (34x44)

A mall doesn't need rows: `Assembler<recipe>` stands anywhere, rows and single machines mix, and
the router lays the belts between them.

```
fein  = Chest<requester, item=iron-plate, rate=2/s>   @(0, 11)
cuin  = Chest<requester, item=copper-plate, rate=1/s> @(0, 26)
gear  = Assembler<recipe=iron-gear-wheel>             @(6, 2)
belt  = Assembler<recipe=transport-belt>              @(13, 2)
ins   = Assembler<recipe=inserter>                    @(20, 10)
cable = Assembler<recipe=copper-cable>                @(6, 25)
circ  = Assembler<recipe=electronic-circuit>          @(13, 18)
pipe  = AsmRow<n=2, recipe=pipe>                      @(6, 33)
bbox  = Chest<provider, limit=4>                      @(18, 3)
ibox  = Chest<provider, limit=4>                      @(25, 11)
pbox  = Chest<provider, limit=4>                      @(14, 34)

net fe:    fein -> gear, circ, belt, ins, pipe
net cu:    cuin -> cable
net gears: gear -> belt, ins
net cab:   cable -> circ
net circs: circ -> ins
net belts: belt -> bbox
net inss:  ins -> ibox
net pipes: pipe -> pbox
```

On paper: 8 nets, all routed, 179 entities (126 belts). A chest one tile from its machine (`bbox`,
`ibox`) gets a single inserter, no belt. A net with many machines (`fe`) needs a few free tiles
around them for its belts: packed tighter, it doesn't route. A requester feeds its net through
one inserter; a busy net can take a second requester (several drivers merge onto one net).

### early-mall.fk: an early-tier mall (49x24)

Yellow and red belts, undergrounds and splitters, inserters (plain, fast, long-handed), assemblers,
drills, pipes and pipes-to-ground, each into its own chest (`limit=2`). It saves belts by where
things stand:

- each machine stands within 3 tiles of what it feeds, so the link is one inserter (a fast one
  across a 1-tile gap, a long-handed one across 2 or 3): the yellow belt assembler hands belts to
  the underground, splitter and red belt assemblers around it, each yellow item to its red one, every
  machine to its chest
- gears and circuits are made beside what takes them: a gear assembler next to each red item,
  a circuit assembler under each splitter, a cable assembler beside each circuit one (two beside
  the one that feeds four machines: with one, the fast-inserter and drill assemblers waited 13
  minutes for circuits in the game)
- each iron or copper requester stands in the gap between two of its machines and feeds both by
  an inserter; only what is further away gets a belt

On paper: 30 nets, all routed: 24 of them are inserters only, and the 83 belts bring iron, copper
and circuits. Built in the game on a test server, every inserter link moves items and every chest
fills. The file is in `docs\examples\`; it is long, so open it there rather than copying it from
here.

### compact-mall.fk: rows packed tight, one chest for every product (50x16)

Rory's layout (2026-10-21): "a row with gaps of zero, except 1 for an ingredient dependency", in
several rows. A well-laid mall needs a few hundred belts at most, never thousands: big gaps between
machines and ingredients made far from where they are used are what cost the belts. And to save
logistic chests (before space science a requester can't be made, and the starter kit's run out):
one copper net and one products net.

- a chain (gear, then belt, then underground) stands in a line with a 1-tile gap between each
  maker and what takes its output: that gap holds the one inserter that links them
- chains stand shoulder to shoulder with no gap
- two rows face one 4-tile corridor: the iron comes in at its middle, and every product goes out
  along it into one chest (`Chest<provider>`, no limit) at its west end
- each circuit maker stands between its cable maker and the machine it feeds; one copper net
  reaches every cable maker
- a maker whose product also feeds a neighbour stays on that link (one net per item and
  direction), so the chest gets its pipes and yellow belts from makers of their own

On paper: 20 nets, all routed, 17 of them single inserters; 152 belts, 18 underground ends and 2
splitters bring the iron and copper in and the products out. It uses 1 provider chest where one
chest per product took 8: with the two plate requesters, 3 logistic chests instead of 11, and in a
base whose plates come by belt from a smelter row or a bus tap, only the 1. The products belt is
sushi. The chest has no limit: when a mixed belt's chest is full the whole belt stops, so a slot
limit only brings that sooner (`SUSHI_LIMIT`). What keeps it from filling is the limit at each
maker: `set ins.out -> pbox: logistic=inserter<100` puts a logistic condition on the hand that
takes its product into the chest, so it waits while the network holds 100 inserters. Name the chest
with `-> pbox`: a maker that also feeds a machine has two output hands, and the condition belongs on
the one whose job is the chest. With every maker on the net limited, `net products limited:` quiets
`CLOG`. More products: another pair
of rows below, the same way.

A one-off crafter that should stop at N: `set x.out -> box: if=inserter<50` (its chest hand waits
while the chest holds 50) and `set x: logistic=inserter<50` (the machine stops crafting), and
`guard` if you switch its recipe (its input inserters take only what the recipe takes). A wire at full length is the starter reactor's fuel saver in
`LANGUAGE.md` ("Circuits"): a red wire from the reactor's temperature to its fuel inserter.

### bus4.fk: Rory's 4-belt bus, a river of iron (54x25)

Rory: "a river of iron, that you keep adding more iron inputs to, and pull iron out when you need
it". Four belts run east. A load from the south merges into all four by a staircase of four
splitters (input priority on its feeder's side, output priority toward the far belt, so it fills
one belt after another), and two taps pull out by staircases of four splitters each, one going
north, one south, each taking from the far belt first.

```
bus   = Bus<belts=4, length=54, item=iron-plate, load=s11, tap=n26|s33> @(0, 10)
net iron1: smelt -> bus.load1             # the smelters' plates onto the bus
net fe:    bus.tap1 -> gears              # the gears take what they need first
net spare: bus.tap2 -> box                # the rest into the logistic network
```

The file adds a row of 8 stone furnaces south of the bus (its ore and coal from requesters), a
gear assembler north of it and a chest south of it. On paper: the furnaces bring 2.5 plates/s,
the gears take 2 and the chest the other 0.5; as routed, the same. At these parameters the
template is Rory's demo where he put it, 210 of its 227 entities: the other 17 are his feeder's and
taps' belts beyond the bus, which here are routes the router lays to and from the ports (40 belts
and 6 underground ends in all). `bus4.json` is his demo exactly as he placed it in the lead world
(`Literal<file="bus4.json">` pastes it as it is). To grow it: make it longer, add loads and taps
(`load=s11|s40`), and a net for each.

### busbase.fk: a bus base, smelting, circuits, mall and science (172x82)

Three buses run east along the bottom: circuits (1 belt), iron (2 belts), copper (1 belt). Every
spine factory stands north of them and runs **perpendicular** to the bus: its machines in columns
running north-south, its belts coming straight down to its loads and taps, each of which stands in
front of the spine's port. Build spines across the bus like this, not along it: a spine grows away
from the bus, and the next one fits beside it.

- **smelting**: a drill column beside a smelter stack (`SmelterArray`: furnaces on both sides of
  each plate belt), loaded onto the iron bus (24 furnaces, 7.5 plates/s) and the copper bus (12);
- **circuits**: a `CircuitStack<n=4>`: circuit assemblers on both sides of one output belt, handed
  cable directly by the cable assemblers above and below them, loaded onto the circuit bus;
- **mall**: iron and circuits into belts, inserters, assemblers, drills and pipes, a chest each
  with a slot limit, so each maker stops when its chest is full;
- **science**: iron, copper and circuits into 30 red and 30 green packs a minute. The green row
  takes its inserters and its belts on one belt, a lane each (`lanes insn | beltn`): the build's
  `could-pair` check would name the pair on two belts.

```
cbus  = Bus<belts=1, item=electronic-circuit>(cl: circ.circ, mc: mall.circ, sc: sci.circ) @(70, 66)
febus = Bus<belts=2, item=iron-plate>(fl: fe.plate, ci: circ.iron, mi: mall.iron, si: sci.iron) @(0, 72)
cubus = Bus<belts=1, item=copper-plate>(kl: cu.plate, cc: circ.copper, sc2: sci.copper) @(0, 79)
```

On paper: 38 nets routed in seven seconds and all of them connected, 0 SPILL, 1741
entities composed; on the lab it stands whole and by game minute 30 science runs at the
model's rates (30 red and 30 green a minute), the iron stack at its full 7.5 plates/s, and the
mall's makers have stopped with their chests full.
`fk contract busbase.fk`:

```
circ: out electronic-circuit 4.0/s via cbus load n11 (got 0.6) | in copper-plate 0.8/s via cubus tap n89 (got 0.8) | ...
fe: out iron-plate 7.5/s via febus load n16 (got 4.3)
sci: in electronic-circuit 0.5/s via cbus tap n74 (got 0.5) | in copper-plate 0.5/s via cubus tap n138 (got 0.5) | ...
```

To grow it: add a spine north of the buses, beside the last one, and an entry for each port it
takes from, in order along the bus; a new item gets a bus of its own, loaded by the spine that
makes it.

### blue6.fk: blue science as a stack of cells

A cell is 18x6: two units of an engine assembler and an advanced circuit assembler handing straight
into a blue science assembler (a long-handed inserter brings the red circuits over the belt of
sulfur and packs), and one pinned `Pole` on that belt, which tunnels under it: the one pole powers
the inserters beside both blue science assemblers, where no other tile reaches. Every belt runs
straight across the cell. The stack is `Stack<cell=BlueCell6, n=2>`: four blue science assemblers.

```
blue = Stack<cell=BlueCell6, n=2> @(14, 6)
net su:  sulf -> blue.t_in                  # sulfur onto the left lane: its inserter drops from the east
net out: blue.t_out -> packs
set packs.in: filter=chemical-science-pack  # the packs' chest takes packs, never the sulfur beside them
```

On the lab: 223 entities, every inserter powered, sulfur on the left lane and packs on the
right, the chest holding packs only. Without the filter, `feed-rides-on` says the sulfur would fill the
packs' chest and stop the belt.

### furnace-column.fk: electric furnaces, a column of your own cells (31x41)

Your own template: a 7x3 cell of one electric furnace between an ore belt and a plate belt, and
`Stack<cell=FurnaceCell, n=8>` lines up eight of them. The ore runs up through every cell and the
plates come back down; the furnaces need no coal and each holds two productivity modules
(`modules=`), which the robots bring with the paste. Six drills feed it (3 ore/s, 3.24 plates/s).
That is ore for 5.3 furnaces, and the belt serves them in order: `fk rates` has the first five
full, the sixth at a third and the last two waiting.

```
module FurnaceCell size 7x3 {
  port ore_in  : in  iron-ore   @s0
  port ore_out : out iron-ore   @n0
  port pl_in   : in  iron-plate @n6
  port pl_out  : out iron-plate @s6
  stack ore_in -> ore_out, pl_out -> pl_in
  f = Furnace<recipe=iron-plate, machine=electric-furnace, modules=productivity-module> @(2, 0)
  net o: ore_in -> f, ore_out
  net p: pl_in, f -> pl_out
}
col = Stack<cell=FurnaceCell, n=8> @(10, 12)
```

The same furnaces as one row: `SmelterRow<n=8, recipe=iron-plate, machine=electric-furnace>` (3
tiles each, ore in, plates out).

### robot-feed.fk: the kit's robots back into a roboport (12x8)

The robots the kit starts with, and the ones a build takes up with a roboport, sit in a storage
chest as items: nothing flies. This puts them back into service.

```
port  = Roboport @(0, 0)
botin = Chest<requester, item="logistic-robot", request=50, rate=1/s> @(5, 1)
net load: botin -> port
```

The chest asks the network for the robots and the router lays the one inserter between the chest
and the roboport (no belt: they are neighbours). On paper it moves them as fast as the inserter's
hand; the roboport's own square covers the chest. Place it on free ground inside the network, next
to what it serves; `cover power` powers the roboport. `request=50` covers the kit's 50 logistic
robots; add a second chest with `item="construction-robot"` in the same way if those are stranded.
Check it with `fk stats` (robots count as items in a chest) and `fk lua` on the roboport's robot
inventory.

### steam.fk: a steam power plant, 3.6 MW (16x26)

```
pump = OffshorePump<rate=1200/s>               @(0, 17, rot 3)
b1   = Boiler<fuel=coal>                       @(2, 13)
b2   = Boiler<fuel=coal>                       @(10, 13)
e1   = SteamEngine                             @(2, 0)
e2   = SteamEngine                             @(2, 5)
e3   = SteamEngine                             @(10, 0)
e4   = SteamEngine                             @(10, 5)
coal = Chest<requester, item=coal, rate=1/s>   @(6, 22)

net water: pump -> b1, b2
net steam: b1, b2 -> e1, e2, e3, e4
net fuel:  coal -> b1, b2
```

On paper: two boilers at full speed (120 steam/s, 0.9 coal/s) run four engines at 900 kW each.
The router lays the water and the steam as pipes (pipe-to-ground where they cross), and the coal
as a belt with an inserter into each boiler; `cover power` joins the engines to the grid. Place
the plot so the pump stands on the shore: at rot 3 it faces west, so water must lie west of its
tile (`game\map.terrain.json` has the water). One pump feeds 20 boilers and each boiler runs two
engines: to grow it, add boilers and engines to the same water and steam nets. Coal by belt from
coal drills works the same way (`net fuel: drills -> b1, b2`).
