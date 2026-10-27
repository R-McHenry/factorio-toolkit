# Toolkit 2.0.46: a bus base, and the three things it needed

Rory, 2026-10-26: "Try and build a solid bus base demo ... an iron bus and a copper bus, a smelting
spine fed by mines for filling both busses, then a mall spine, and a science one ... a circuits bus
that is fed by a spine factory that uses copper and iron from the bus."

## The demo: `agent/docs/examples/busbase.fk`

Three buses run east: circuits (1 belt), iron (2), copper (1). West of their heads, two iron
smelting spines and a copper one (8 drills, a coal drill and 12 furnaces each) fill the iron and
copper buses at their mouths. North of the buses, three sealed spine factories take what they need
by taps:

- **circuits**: copper and iron off the buses, 3 cable and 2 circuit assemblers, into the circuit
  bus's mouth;
- **mall**: iron and circuits into belts, inserters, assemblers, drills and pipes, a chest each with
  a slot limit;
- **science**: iron, copper and circuits into red and green packs.

On a laptop server (`fk lab`): 43 nets routed (0.7 s offline), 1995 entities pasted, all 1995
standing, no ghosts. Run at 8x and measured over 8 game minutes:

| game minute | red/min | green/min | circuits/min | mall |
|---|---|---|---|---|
| 10 | 11.1 | 19.6 | 92 | filling its chests |
| 25 | 17.9 | 29.0 | 46 | belts, assemblers full; drills still making |
| 30 (final code) | 28.9 | 29.7 | 29.7 | all full, gears topping up |
| 40 | 30.0 | 30.0 | 30.0 | all full |

The model says 30 red, 30 green and 33.5 circuits a minute. Early on the mall's makers take what
they can (taps take in bus order: circuits, mall, science), then stop as their chests fill (at
minute 12: inserters 200 and pipes 200, each at its slot limit), and science comes up to the
model's rate. The smelters slow down as the buses fill.

## 1. A staircase stands in front of what it connects to

The connection list packed every load and tap at the bus's head in list order, so each spine's
plates ran back along the bus to it. Now a staircase stands **in front of its endpoint**: a sealed
module's port (at its pin along the side, or the module's middle), or a row's head, never before the
staircase written ahead of it (the list order is still the order along the bus), with `length`
following. Only an endpoint beside the bus on its staircases' side (north of a bus running east,
east of one running south) is faced; anything else keeps the packed place, so a bus never grows
into something in line with it (the first try of this rule ran a bus into a rib at its end).

In the demo the taps land at n22, n66, n116 (iron), n28, n122 (copper) and n24, n78 (circuits): under
each spine's pinned port. bus4ribs' taps move to n7, n13, n32, n52 (in front of its ribs), and
bus4.fk's to n30, n36.

## 2. Several buses with mouths

A connection's name is its net's name, so two buses each with an `in1` collided ("net in1 already
exists"). Where a scope has several buses with mouths, every mouth's net is named by its bus:
`febus_in1`, `febus_in2`, `cubus_in1`, `cbus_in1`. A single bus keeps the plain `in1`, so existing
designs' route keys don't change.

## 3. The contract of an out port into a bus

`fk contract` read an out port into a mouth or a load as `0.0/s (got 0.0)`: the bus pool absorbs
the port's nets, whose own rows have no delivered or can_make. It now reads what the module's
makers put through the port, at full speed and as solved (`fe_a: out iron-plate 3.8/s via febus
mouth in1 (got 2.1)`), and every bus end is named by its bus (`febus mouth in1`, `cubus tap n28`;
a bus called `bus` reads `bus tap n7` as before).

## Verified

- `tests/test_busbase.py` (5): the demo routes clean, no check lines, six sealed spines; each tap
  in front of its port; every mouth net named by its bus; the contract through the mouths; an
  endpoint in line with the bus keeps the packed place, one beside it is faced.
- Moved expectations: `test_contract` (bus4ribs' taps), `test_bus_map` (bus4's taps).
- The full suite: **985 tests, OK** (980 before, plus 5).
- The lab runs above, the last one on this release's code.
