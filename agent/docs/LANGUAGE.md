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
| `LabRow<n>` | n labs, 3 tiles each | 1 or 2 science belts in |
| `Assembler<recipe>` | one assembler | by inserters next to it |
| `Furnace<recipe>` | one furnace | |
| `Chest<provider>`, `Chest<requester, item=iron-plate, rate=2/s>`, `Chest<storage>` | a logistic chest: the robots' end of a net | |
| `OffshorePump`, `Pumpjack<n>`, `ChemPlant<recipe>`, `Refinery<recipe>` | fluid machines | pipes |
| `Literal<file="x.json">` | entities exactly as given (the plant is one) | |

Rows are **counterflow**: every belt of a row attaches at its head, the west end at rot 0. Leave
a few free tiles at a row's head and between rows: the router lays the belts there. `fk explain
FILE INST` shows any row as its exact entities, with its size and where its belts attach.

`duty=0.5` on any instance caps it (a row that runs only part of the time).

## Nets

`net NAME: drivers -> consumers`. A net is one belt (or one pipe): the drivers put items on it,
the consumers take them.

- A ref names an instance (`gears`): only the endpoints of the net's items count, so
  `net iron: smelt -> gears, circ` takes the plates of `smelt`.
- `net NAME items a, b: ...` declares the items; otherwise they are what the drivers make.
- Two or more items on one net is a **sushi** net: fine into a lab or a chest, which take
  everything; into a machine it must take every item (else `SUSHI_SINK`).
- `X.*` means X's free endpoints, the ones no other net holds yet: `net out: mall.* -> chest`.
- A machine is on at most one net per item and direction.
- Several drivers merge onto the net; several consumers split off it. The router lays the
  splitters.

## Checks on paper

`assert INST.rate >= 10/min` (or `/s`, `/h`): checked by the rate model (`fk rates`); a failed one
is an `ASSERT` line, not an error.

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
