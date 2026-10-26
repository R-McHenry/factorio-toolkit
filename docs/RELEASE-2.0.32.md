# Toolkit 2.0.32: the bus's connection list is its port map (phase 2, first slice)

Rory, 2026-10-25: "the bus's port list is the order … like a VHDL port map. Drop the beside hint."
and "in order to keep it simple lets force the programmer to put names on all the ports in the list
when its defined, so the name gives it the name and the positions give it an order. that keeps the
commited routes simple too." This slice implements the list, the names, the order, the inferred
direction and the `ORDER` line — the mouths, the straight loads and the UG tap kinds come next.

## The statement

```
bus = Bus<belts=2, item=iron-plate>(
        fe: feed,                 # a load: a maker of iron-plate
        fg: rib.iron) @(20, 0)    # a tap: an in port
rib = GearRib @(40, 0)
```

- **Each named entry is one net**, named by its key (`fe`, `fg`), between the bus's port at that
  position and the entry's endpoint. The names are ordinary net names: they appear in `.fkp` routes,
  rates and the checks, so a reordered list moves positions but never renames a route.
- **Direction comes from the netlist**: an `out` port or a machine that makes the bus's item is a
  load; an `in` port or a machine that takes it is a tap. An `inout` port, or an endpoint that both
  makes and takes the item, is refused — the bus cannot tell which it is.
- **Position is the written order.** The lowering walks the list, giving each staircase a band that
  clears the one before by two tiles (Rory: "they need to be spaced out by at least 2 spaces between
  them"), and `length` follows; `length=` stays a pin and is refused when it is short of the list.
- **A tap before any load is an `ORDER` line** ("fg is a tap before any load: nothing upstream feeds
  the bus there"). ORDER is structural, as agreed: the nominal pool has no position, so starvation
  stays `CAPACITY`'s job in the routed model.
- The list **replaces** `load=`/`tap=` on that bus (both at once are refused), only a `Bus` takes one,
  and a connection name must not collide with an existing net.

## What the lowering does

At elaboration, after every instance is expanded (so the endpoints resolve), `_bus_conns` resolves
each entry, classifies it, computes the positions, writes the bus's `load=`/`tap=`/`length` params and
builds the bus's port machines and the one net per entry — the same form a design writes by hand.
Everything downstream (`_bus_nets`, the pool, the `.fkp`, the router) sees the hand-written shape:
`fk layout` on the example above builds 31 entities with no invariant failures, and the rate model
pools the list exactly as it pools the pinned form (the rib at full speed, `loads bring 4.000/s,
taps would take 2.000/s`).

## Tests (12 in `tests/test_bus_map.py`)

The list binds the ports in order and names the nets; it pools the way the pinned form does (same
drivers, consumers and utilizations, the rib at 1.0 and 2.0/s delivered); a tap before a load is
ORDER; a list replaces `load=`/`tap=`; only a Bus takes one; an `inout` port is ambiguous; a
connection name may not shadow a net; an unknown endpoint, a missing `item=` and a too-short `length`
are refused; the parser keeps the order and refuses a repeated name. The elaboration baseline over
the 42 existing designs is unchanged, and the full suite's pre-existing failure/error lines are the
same set as 2.0.27's tree.

## Not in this slice

- The four **mouth ports** `in1..in4` (a belt end at the head, in line, no staircase) — model and
  fragment.
- The **first N loads straight onto one belt each** (a mouth per belt).
- The **left/right UG taps** in the source (the lab has the geometry: lone exit / entrance + exit,
  both 7.5/s on the left lane) and the pair (`item=a | b`) bus.
- The **bus-to-bus** connection: when it comes, direction cannot be inferred from the netlist, so the
  source must name it and the toolkit must refuse it otherwise — a blocking error, not a warning.
