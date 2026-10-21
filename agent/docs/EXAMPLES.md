# Examples

Small factories that build cleanly, each in `docs\examples\`. Copy one into `game\`, give it
a plot in `nauvis.surface`, check it on paper, build it:

```
copy docs\examples\gears.fk game\gears.fk
# add to game\nauvis.surface:   place gears = gears plot 70,-40 16x16
fk rates gears.fk
fk build --to report_checks          # design only: read out\report_checks.txt
fk build                             # the paste
fk look 68,-42 88,-22
```

The first three together on plots next to each other give 9 nets, all routed and connected, 0 LEAK.
Their power joins the plant's grid (`floorplan --bridge-power`).

## smelting.fk: ore to plates (26x26)

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

## gears.fk: plates in, gears out, robots at both ends (16x16)

```
inbox = Chest<requester, item=iron-plate, rate=1.25/s> @(2, 2)
gears = AsmRow<n=2, recipe=iron-gear-wheel>           @(6, 2)
box   = Chest<provider, limit=4>                      @(2, 12)

net plates_in: inbox -> gears
net gear:      gears -> box
```

On paper: 37.5 gears/min, limited by the 1.25 plates/s the requester asks for (`rate=`). The
chest feeds the row with one inserter (a route of one inserter).

## red.fk: red science into labs (30x30)

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

## sized.fk: the same red science, counted by the build (42x32)

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
its gear, 1 copper), and `SIZE` names the requester that stops it until the `rate=` go up. The
rows grow east: the 42x32 plot holds 11 of each, and `FIT` says when one runs past it. On paper:
4 nets, all routed and connected.

## mall.fk: a mall of single machines (34x44)

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

## early-mall.fk: an early-tier mall (49x24)

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

## compact-mall.fk: rows packed tight, one chest for every product (50x16)

Rory's layout (2026-10-21): "a row with gaps of zero, except 1 for an ingredient dependency", in
several rows. A well-laid mall needs a few hundred belts at most, never thousands: big gaps between
machines and ingredients made far from where they are used are what cost the belts. And to save
logistic chests (before space science a requester can't be made, and the starter kit's run out):
one copper net and one products net.

- a chain (gear, then belt, then underground) stands in a line with a 1-tile gap between each
  maker and what takes its output: that gap holds the one inserter that links them
- chains stand shoulder to shoulder with no gap
- two rows face one 4-tile corridor: the iron comes in at its middle, and every product goes out
  along it into one chest (`Chest<provider, limit=16>`) at its west end
- each circuit maker stands between its cable maker and the machine it feeds; one copper net
  reaches every cable maker
- a maker whose product also feeds a neighbour stays on that link (one net per item and
  direction), so the chest gets its pipes and yellow belts from makers of their own

On paper: 20 nets, all routed, 17 of them single inserters; 152 belts, 18 underground ends and 2
splitters bring the iron and copper in and the products out. It uses 1 provider chest where one
chest per product took 8: with the two plate requesters, 3 logistic chests instead of 11, and in a
base whose plates come by belt from a smelter row or a bus tap, only the 1. The products belt is
sushi, so the build says `CLOG`: it runs while each product is taken about as fast as it is made;
one that piles up fills the chest and the belt and stops the others, so limit production there.
More products: another pair of rows below, the same way.

## bus4.fk: Rory's 4-belt bus, a river of iron (54x25)

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

## steam.fk: a steam power plant, 3.6 MW (16x26)

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
