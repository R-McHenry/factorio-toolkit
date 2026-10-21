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
| `MinerRow<n, resource>` | n electric drills facing a belt between them; 3 tiles per pair, 7 tall | the ore leaves at the row's head |
| `SmelterRow<n, recipe>` | n stone furnaces, 2 tiles each; ore and fuel (coal) in | 2 in, 1 out |
| `AsmRow<n, recipe>` | n assemblers, 3 tiles each, 7 to 9 tall | up to 3 in (the third under the product belt, by long-handed inserters), 1 out |
| `LabRow<n>`, `LabRow<n, rate=2/min>` | n labs, 3 tiles each. Without `rate=` a lab takes every pack that reaches it; with it, at most that much of each pack (one research unit of 30 s takes a pack of each kind in 30 s: `rate=2/min`), and science rows that make more back up | 1 to 3 science belts in (the third by long-handed inserters) |
| `Assembler<recipe>` | one assembler | by inserters next to it |
| `Furnace<recipe>` | one furnace | |
| `Chest<provider, limit=4>`, `Chest<requester, item=iron-plate, rate=2/s>`, `Chest<storage>` | a logistic chest: the robots' end of a net. `limit=` is how many slots it fills (its bar in the game): what feeds a full chest stops. A requester takes several items too: `item="iron-plate,copper-plate"`; `trash` on a requester sends back what it no longer asks for | |
| `OffshorePump<rate=1200/s>` | water from the lake: it stands on the shore, open to the water (rot 3 faces west, water west of it) | pipes |
| `Boiler<fuel=coal>` | one boiler, 3x2: water in and out at its short ends, steam out of its long north side (rot 0), coal by an inserter beside it; 60 steam/s on 0.45 coal/s | pipes |
| `SteamEngine` | one steam engine, 3x5 standing (rot 0): steam at both short ends, so engines join end to end; 900 kW on 30 steam/s, two per boiler | pipes |
| `Pumpjack<n>`, `ChemPlant<recipe>`, `Refinery<recipe>` | fluid machines | pipes |
| `Literal<file="x.json">` | entities exactly as given (the plant is one). The file: a blueprint string (`.txt`), JSON `{"bp": "0e..."}`, or an entity list `[{"name": "roboport", "x": 2, "y": 2, "direction": 0}]`. Its frame is its entities' box, so a lone roboport needs a pole of its own beside it | |

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
  it is used; one that piles up fills the belt and stops the others (`CLOG` says where that can
  happen). Into a machine it must take every item (else `SUSHI_SINK`).
- `X.*` means X's free endpoints, the ones no other net holds yet: `net out: mall.* -> chest`.
- A machine is on at most one net per item and direction.
- Several drivers merge onto the net; several consumers split off it. The router lays the
  splitters.

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
