# Toolkit 2.0.33: the bus's mouths (phase 2, second slice)

Rory, 2026-10-25: "it should be the same as what a tap or load is, but four of them. Should look just
like a normal module's inputs basically, the list inputs are the only special ones." and "the bus
inputs could be driven without a loader all the way at the upstream end."

## The statement

```
bus = Bus<belts=4, item=iron-plate>(
        in1: smelt.plate,        # a mouth: belt 1 fed in line at the head
        in2: smelt2.plate,
        fg:  gears.iron,         # a staircase tap, in list order
        fb:  belts.iron) @(50, 0, rot 3)
```

- **A mouth is a belt end at the head**, one per belt, named `in1..in{belts}`. It is fed in line —
  no staircase and no entity of its own: the bus's own belt is the mouth, and the parent's belt runs
  into it from the head. Its role's attach point is the head tile facing east (north of the frame's
  belts after the rot), so the route meets it from outside the frame.
- **A mouth must be a source**: an out port, or a machine that makes the bus's item. A tap or a
  taker written as `in<k>` is refused ("a mouth is an input").
- **A mouth is at the head, so it is upstream of every tap**, whatever order the list writes it in:
  ORDER counts the mouths before it reads the staircases.
- The bus's template gained `mouth=in1|in2` (the used mouths; the fragment builds a role for each),
  and the fragment's frame and belts are unchanged — a mouth adds no entity, only a route endpoint.

## What it looks like in the model

The mouth's machine is a load port (`port=load`) named by the entry, so `_bus_nets` pools it exactly
as a staircase load: the net keeps the entry's name, the bus's own net gains it as a driver, and the
rates show the supply arriving at the head. On the example above (a chest feeding `in1`, a rib taking
the tap), `fk check` is clean, `fk layout` builds 23 entities with no invariant failures, and the
rates show the rib at full speed with `loads bring 4.000/s, taps would take 2.000/s`.

## Tests (17 in `tests/test_bus_map.py`)

New: a mouth feeds the bus in line (the entry's net names the mouth port, the bus's pool takes it);
a mouth is upstream of every tap (no ORDER whatever the list order); a mouth must be a source; an
`in<k>` past the belt count is refused; and the fragment binds the mouth to the head tile facing east
(`attach (0.5, 1.5, 4)`), laying out with no notes. The elaboration baseline over the 42 existing
designs is unchanged (no existing bus has mouths), and the suite's pre-existing failure/error lines
are the same set as 2.0.27's tree.

## Still phase 2

The **straight loads** (the first N loads as mouths, which this slice now makes expressible), the
**left/right UG taps** in the source (the lab geometry is validated: a lone exit / an entrance + exit,
both 7.5/s on the left lane), the **pair bus** (`item=a | b`), and the **bus-to-bus** connection with
its blocking direction check.
