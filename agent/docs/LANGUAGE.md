# The factory language (`.fk`)

A factory file says what the factory is: its machines and its nets. Where everything goes on the
ground, the belts and the poles are the toolkit's job (`fk build`); you give each row a position.

```
# smelting.fk: iron ore and coal into plates
ore   = MinerRow<n=4, resource=iron-ore>   @(10, 2, rot 2)     # a row of 4 drills, turned 180
coal  = MinerRow<n=2, resource=coal>       @(18, 2, rot 2)
smelt = SmelterRow<n=8, recipe=iron-plate> @(10, 12)
box   = Chest<provider>                    @(4, 22)

net ore_:   ore -> smelt                  # the drills' ore goes to the furnaces
net fuel:   coal -> smelt
net plates: smelt -> box                  # the plates into a provider chest (robots take them)

assert smelt.rate >= 2/s
```

## Instances

`name = Kind<param=value, ...> @(x, y)` or `@(x, y, rot r)`. The position is the instance's
top-left tile inside the factory's plot; `rot` turns it r quarter turns clockwise (0 to 3).
`@patch(iron-ore)` instead of a position puts a miner row on that ore.

The templates:

| kind | what | belts |
|---|---|---|
| `MinerRow<n, resource>` | n electric drills facing a belt between them; 3 tiles per pair, 7 tall. `drill=burner-mining-drill, fuel=coal`: n burner drills in one row (2 tiles each, 5 tall), a fuel belt north with one inserter per drill: they mine without power | the ore leaves at the row's head; a burner row's fuel comes in at its head too |
| `SmelterRow<n, recipe>` | n stone furnaces, 2 tiles each; ore and fuel (coal) in | 2 in, 1 out |
| `AsmRow<n, recipe>` | n assemblers, 3 tiles each, 7 to 9 tall | up to 3 in (the third under the product belt, by long-handed inserters), 1 out |
| `Lab`, `Lab<rate=2/min>` | one lab, its inserters laid like an Assembler's: several Labs around one multi-item requester chest each take their packs by one inserter, no belt | by inserters next to it |
| `LabRow<n>`, `LabRow<n, rate=2/min>` | n labs, 3 tiles each. Without `rate=` a lab takes every pack that reaches it; with it, at most that much of each pack (one research unit of 30 s takes a pack of each kind in 30 s: `rate=2/min`), and science rows that make more back up | 1 to 3 science belts in (the third by long-handed inserters) |
| `Assembler<recipe>` | one assembler | by inserters next to it |
| `Furnace<recipe>` | one furnace | |
| `Chest<provider, limit=4>`, `Chest<requester, item=iron-plate, rate=2/s>`, `Chest<storage>`, `Chest<plain>` | a logistic chest: the robots' end of a net (`plain`: an iron chest off the network; `max=` on a requester caps its request). `limit=` is how many slots it fills (its bar in the game): what feeds a full chest stops. A requester takes several items too: `item="iron-plate,copper-plate"`; `trash` on a requester sends back what it no longer asks for. A requester can drive a net (it feeds what's on the net); a provider or storage chest is only a net's end (the first lead run's `net packs: px -> lab` with a provider `px` said TYPE). A product's chest is best a provider: robots put leftovers of any item into the nearest storage chest, and those fill its slots | |
| `OffshorePump<rate=1200/s>` | water from the lake: it stands on the shore, open to the water (rot 3 faces west, water west of it) | pipes |
| `Boiler<fuel=coal>` | one boiler, 3x2: water in and out at its short ends, steam out of its long north side (rot 0), coal by an inserter beside it; 60 steam/s on 0.45 coal/s | pipes |
| `SteamEngine` | one steam engine, 3x5 standing (rot 0): steam at both short ends, so engines join end to end; 900 kW on 30 steam/s, two per boiler | pipes |
| `Pumpjack<n>`, `ChemPlant<recipe>`, `Refinery<recipe>` | fluid machines | pipes |
| `Reactor<read=temperature, signal=S>`, `HeatExchanger`, `SteamTurbine` | nuclear power: a reactor heats the exchangers it touches (`net heat items heat: reactor -> hx`, no route), 10 MW each, 103 steam/s for 1.7 turbines | pipes, an inserter for the cells |
| `Constant<signals="S=N, T=M">` | a constant combinator (Circuits, below) | wires |
| `Literal<file="x.json">` | entities exactly as given (the plant is one). The file: a blueprint string (`.txt`), JSON `{"bp": "0e..."}`, or an entity list `[{"name": "roboport", "x": 2, "y": 2, "direction": 0}]`. Its frame is its entities' box, so a lone roboport needs a pole of its own beside it | |
| `Bus<belts=4, length, item, load=s11, tap=n26\|s33>` | Rory's bus: `belts` belts of one item, `length` tiles, running east at rot 0. Its loads and taps are ports (below) | one belt per port, beside the bus |

Rows are **counterflow**: every belt of a row attaches at its head, the west end at rot 0. Leave
a few free tiles at a row's head and between rows: the router lays the belts there. `fk explain
FILE INST` shows any row as its exact entities, with its size and where its belts attach.

`duty=0.5` on any instance caps it (a row that runs only part of the time). `inserter=inserter`
on a row puts plain inserters in place of the fast ones.

## Counts the build chooses: `n=auto`

`n=auto` on a `MinerRow`, `SmelterRow`, `AsmRow` or `LabRow` leaves its count to the build. The
`size` step (right after `elaborate` in the build script) gives each such row the fewest
machines that meet:

- the surface file's `target` lines (what the whole surface makes),
- the factory's `assert INST.rate >= R` lines,
- what the row's consumers ask: a net an auto row drives carries what the machines on it take,
  and what a chest or labs with a `rate=` take. A chest or labs without a rate take what is
  left and ask nothing, so a row that only feeds those grows for a target or an assert,
- for `LabRow<n=auto, rate=...>`: the labs take what the science rows make.

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
says when a constraint can't be met (`SIZE`: a row at the top of its bounds, a requester chest at
its rate, a row whose count you wrote at full speed). `fk rates FILE.fk` sizes the same way before
it shows the rates. Counts sized to a rate balance a net exactly, so `fk rates` may name either
side of it as what binds (the ore is exactly what the furnaces' output needs).

Rows grow, and you arrange them: a row that grows runs further east (at rot 0), so leave it
room. When a sized row runs past its plot or into another instance, the size step says so
(`FIT`, both rows and how far), and the build stops at `place` if their entities overlap. After
the routing, `report_rates` says (`SIZE`) when a net of a sized row asks more than its belts
carry: a yellow lane carries 7.5 items/s.

## Nets

`net NAME: drivers -> consumers`. A net is one belt (or one pipe): the drivers put items on it,
the consumers take them.

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
  on the net. It only quiets `CLOG` and `UNLIMITED` for it: it limits nothing itself. The limits
  are `keep=` on each maker (Circuits, below).
- `X.*` means X's free endpoints, the ones no other net holds yet: `net out: mall.* -> chest`.
- A machine is on at most one net per item and direction.
- Several drivers merge onto the net; several consumers split off it. The router lays the
  splitters.

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
  its fill first, and a load after a tap never reaches it (`OPEN` on the bus's net says so).
- A yellow belt carries 15/s on its two lanes, 7.5 each. A smelter row puts its plates on one
  lane, so one row into a load brings at most 7.5/s; the routed rates and `CAPACITY` say where
  a lane is full. Grow a bus longer and add ports; a second item is a second bus beside it (a
  gap row between them), and a net crosses a 4-belt bus by an underground from one of its outer
  rows to the other.

## Circuits

Circuit wires, conditions and limits are written in the source like nets; the build lays them
(inserter conditions, readings, filters, the red and green wires) and pastes them with the rest.
Change one and the next build lays the changed entities fresh: no script sets them.

### Limits at the makers

```
belt = Assembler<recipe=transport-belt, keep=200>    # the network keeps 200 belts
ins  = Assembler<recipe=inserter, fill=50>           # its chest holds at most 50 inserters
pipe = AsmRow<n=2, recipe=pipe, keep=100>
```

- `keep=N` on a maker (any machine or row): every inserter that takes its product out into a
  chest, straight in or onto the belt of a net that ends in a chest, runs while the logistic
  network holds fewer than N of it (a logistic condition; no wire). This is the mall's limit: on
  a products belt into one chest, each maker keeps its own item, and the chest stays unlimited.
  The maker's inserters must be in a logistic network (a roboport's orange area).
- `fill=N`: every inserter that takes its product straight into a chest runs while that chest
  holds fewer than N (a red wire from the chest and a circuit condition). It needs no robots, and
  it stops a one-off crafter at N in its chest: its inserter stops, then the machine.
- A limit where nothing goes into a chest (gears that feed machines only) is a `LIMIT` line.
- A limit is real, but it does not quiet `CLOG`: a mixed belt quiets when you write the net
  `limited` (once each maker on it has its limit).

### A crafter that switches recipes: `guard`

```
x = Assembler<recipe=iron-gear-wheel, guard>   @(10, 4)
```

`guard`: the machine puts its recipe's ingredients on a red wire to every inserter that feeds it,
and they take only those (their filters come from the wire). Switch the recipe and what they
carry follows in the game, so no hand is left holding the old item. A plain `inserter` can't
filter (`GUARD` says so); the fast inserters the router lays can.

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
  game keeps a belt's reading only while it is on a wire).
- `when A < N` on a net gates it: every inserter and pump of its route moves items only while it
  holds. On an instance, it enables the machine itself. `A` is `WIRE.SIGNAL` (that wire),
  `network.ITEM` (the logistic network's count, no wire) or `INSTANCE.SIGNAL` (what that chest
  or machine puts out, on a red wire of its own). The comparisons are `<`, `>`, `<=`, `>=`, `=`
  and `!=`, against a whole number or another signal on the same wire.
- Signals are virtual signals (`signal-A`, `signal-T`), items or fluids, by name, or the names
  you declare with `signal`.
- The build wires each wire net's entities by the shortest wires; a wire reaches 9 tiles
  (`WIRE_REACH` when two are further apart). Two wires of one colour on one entity are one
  network in the game and their signals add (`WIRE_LEAK`).
- `SIGNAL` says a condition reads a signal nothing on its wire makes, or a name that is no
  signal; `WIRE` a wire nothing drives or reads.

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
checked (`REQUIRE`), and a gated net whose wire has no `cycle` is a `GATED` line (the rate model
takes it as always open). The fuel saver above is the starter plant's: the reactor loads a cell
only below 550 C, so its fuel slot is empty while it coasts, and that is normal.

## Checks on paper

`assert INST.rate >= 10/min` (or `/s`, `/h`): checked by the rate model (`fk rates`); a failed one
is an `ASSERT` line, not an error. With `n=auto` rows the build sizes them to meet it.

## Modules and imports

```
module Smelting {                 # a reusable part, written like a factory
  ore   = MinerRow<n=4, resource=iron-ore> @(0, 0, rot 2)
  smelt = SmelterRow<n=8, recipe=iron-plate> @(0, 10)
  net ore_: ore -> smelt
}
left = Smelting @(0, 0)
import Mall from "mall.fk"
```

A module instance's machines are named with a dot: `left.smelt`.

## Power

The build script's `cover power` step adds the poles every factory needs; `floorplan
--bridge-power` joins factories to the plant's grid. Don't put poles in the source.
