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
