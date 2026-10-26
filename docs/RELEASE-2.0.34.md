# Toolkit 2.0.34: tap kinds — the left tap (phase 2, third slice)

Rory, 2026-10-25: "there are three different tap types, a dual tap, a left tap and a right tap …
if instead of a belt we use an exiting underground, it will cut off one lane and only take left."
The lab measured all three on hand-built benches (dual 15.3/s on both lanes; the two UG taps ~7.5/s,
both delivering on the left lane). This slice puts the **left** tap in the port map; the right one is
refused until its frame row exists.

## The statement

```
bus = Bus<belts=4, item=iron-plate>(
        in1: smelt.plate,
        left fg: gears.iron,      # a left tap: a lone UG exit at the stub
        fb: belts.iron)           # a dual tap (the default): the belt stub
```

- The kind is written before the entry's name: `dual`, `left` or `right`, default `dual`. It is a
  **tap's** property: a kind on a load or a mouth is refused.
- A **left tap** replaces the stub belt with a lone underground **exit** at the stub tile. The exit's
  output is the tile beyond the stub, where the route's first belt goes; the role's attach point is
  the same stub tile, so nothing else in the layout moves. The exit takes only the lane on its open
  side, which is why a left tap is one belt of capacity (7.5/s) where a dual tap is two (15/s).
- The bus's params carry a `tapkind=` list parallel to `tap=` (only written when a tap is not dual),
  and the tap port's machine records its kind, so the pool, the nets and the rates are untouched.

## The paste question, settled

The lab's left tap originally existed only as a directly created entity, and a one-entity blueprint of
a lone exit pasted **0** entities — but that was the test site, not the exit: the spots had no
generated chunks (a plain belt pasted 0 there too). With the chunks generated, the toolkit's build
path pastes the exit as a **ghost** and the revive makes it a real, valid `ug=output` belt. So the
left tap is buildable through the same paste/revive path as everything else; the probe that "proved"
otherwise is recorded here so the next lab session generates chunks before pasting.

## Verified

`fk check` clean and `fk layout` 23 entities with no invariant failures on the left-tap example, with
the rates unchanged (the rib at full speed, `loads bring 4.000/s, taps would take 2.000/s`). 22 tests
in `tests/test_bus_map.py`, 5 new: the left tap's stub is an `underground-belt` with `ug=out` and its
attach is still the stub tile; a dual tap is the plain belt; a right tap is refused with the frame
reason; a kind on a load is refused; and the parser keeps the kind. The elaboration baseline over the
42 existing designs is unchanged, and the suite's pre-existing failure/error lines are the same set as
2.0.27's tree.

## The right tap is next

A right tap is a UG **entrance** at the stub, its **exit** one row further out, and the route meeting
the tile beyond that — which is one row outside the bus's frame (the stub row is the frame's edge).
The fragment must grow a row and shift its content by one for a bus with a right tap (north side) or
grow southward (south side), with `_port_tiles`/`bus_check` taking the offset. That is its own slice:
it changes the frame for those buses only, so existing designs stay put.
