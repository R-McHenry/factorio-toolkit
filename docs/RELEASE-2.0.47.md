# Toolkit 2.0.47: spines across the bus, and a circuit stack

Rory, 2026-10-26, on 2.0.46's bus base: "I dont want to instill the habit of building every factory
parralel to the bus instead of the natural choice of perpendicular", and "also try and use smelter
and green circuit factories that fill both sides of the output belt".

## The bus base, rebuilt across the bus

`agent/docs/examples/busbase.fk` now stands every spine perpendicular to the buses: its machines in
columns running north-south, its belts straight down to the loads and taps at its south edge. Each
spine is taller than it is wide along the bus (a test holds it to that).

- **smelting**: a drill column beside a `SmelterArray` (furnaces on both sides of each plate belt):
  24 furnaces onto the iron bus (7.5 plates/s), 12 onto the copper bus, each by a load in front of
  its port;
- **circuits**: a `CircuitStack<n=4>` (below), loaded onto the circuit bus;
- **mall** and **science**: columns of single machines and turned rows (`AsmRow ... rot 3`).

On a laptop server: 35 nets routed in 0.5 s, 1760 entities, all standing, no ghosts. Measured over
4 game minutes:

| from game minute | red/min | green/min | iron stack | circuit stack |
|---|---|---|---|---|
| 12 | 0 | 12.7 | 450 plates/min | 77/min |
| 30 | 30.2 | 30.0 | 450 plates/min | 54/min |

The model says 30 red and 30 green. Red starts late: the circuit stack takes copper first, and
science is the last tap on the copper bus.

## CircuitStack

`CircuitStack<n, machine=assembling-machine-1>` is the smelter stack's shape for green circuits:
two columns of circuit assemblers around one output belt, each handed cable directly by the two
cable assemblers above and below it (4 cable/s for the 3 it uses), iron and copper on the two lanes
of the stack's own feed belts, side-loaded at its foot by the same splitter geometry as
`SmelterArray`'s, widened for 3-wide assemblers. 14 tiles wide, 12 tall per assembler in a column
plus 6 for the foot; up to 14 circuit assemblers (a lane of iron per column).

- In the netlist each circuit assembler is one machine taking iron and the copper its cable
  assemblers turn into cable (1.5 a circuit); the cable assemblers are entities of the stack.
- On a laptop server a 6-assembler stack made 240 circuits a minute against the model's 320, on
  the build's chosen inserters; the bus base gives its stack `inserter=fast-inserter`.

## The judge: a template's own intermediate maker

`fkcore.connect` reported the stack's cable hand-offs as LEAKs (copper into a machine that is no
consumer, cable out of one that is no driver). `_relay` now passes a machine that is no endpoint of
the netlist, stands in the instance of a consumer of the net, and makes an ingredient of that
consumer's recipe: a cable assembler before a circuit assembler. A stray machine of the same
instance whose product the consumer doesn't use is still a LEAK (`test_connect`'s transport-belt
maker beside a gear consumer: the first, broader rule hid it, and the suite caught it).

## STRATEGY.md

Two tips: build a factory off a bus across it, not along it, and fill both sides of an output belt.

## Verified

- `tests/test_circuit_stack.py` (6): the stack's machines and rates; the output inserters on both
  sides of one belt, two cable assemblers a circuit; it routes and judges clean; the rate model
  feeds it; too many for one stack is refused; only a template's intermediate maker is a relay.
- `tests/test_busbase.py` (6): the rebuilt base routes clean; every load and tap in front of its
  port; every spine perpendicular; the contract; mouth names (moved to a small design of its own).
- The full suite: **992 tests, OK**.
