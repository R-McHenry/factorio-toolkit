# Toolkit 2.0.41: whole-belt ports and recorded port tiles (PLAN-GLOBAL phase A)

Rory, 2026-10-26: "Phase A of PLAN-GLOBAL.md is yours." `PLAN-GLOBAL.md` (§4, "Phase A") has the
three items; this release is all three.

    Done when: a 15/s crossing net routes and rates through one port, the tile faces its partner,
    and after a parent move the port tile and the module's inside routes are unchanged.

## 1. A net ending at an `X | X` port is laid and rated on both lanes

`port plate : out iron-plate | iron-plate @e` existed since 2.0.30 (V1's `Belt[X]`: one item, both
lanes), but 2.0's net is one lane: the port's carrier carried a plain `net=A` and the crossing
behind it ran one lane at 7.5/s. A plot exporting 15/s could not use the width it declared.

Now the declaration is what the layout and the model read:

- **Laid**: the `X | X` port's carrier carries `net=A|A` — both of the belt end's lanes are the
  net's, exactly as a V1 `net=A` belt reads. A source that fills both lanes (a two-sided
  `MinerRow` drops 15 drills on each lane) crosses the port at 15/s on yellow, and the routes on
  both sides of the port carry it on both lanes.
- **Rated**: `CAPACITY` rates a **port's width**, not a lane of it: a one-lane port (`@e4L`, or a
  lone `@e4`) is 7.5/s of a yellow belt end, an `X | X` port 15/s. A crossing net that asks more
  than its port's width is short *at the port*, whatever the route behind it carries:

      CAPACITY    port plot/ore: 15.00/s asked through it, and a one-lane port carries 7.50/s
                  (one yellow lane of its belt end): declare it both lanes (item | item) or give
                  it a second port

- **Lane graph**: the port's tile is a belt tile whose two lanes are labelled (`plot/dig|plot/dig`
  for `X | X`), so both lanes of the crossing are in the lane graph and in `routed`'s per-lane
  needs.
- **One-lane ports and lane pairs are unchanged**: a one-lane port keeps its plain `net=A` (the
  lane the route takes is the lane it crosses on — the width is the `CAPACITY` line above), and a
  pair (`iron-ore | coal`) is still two lanes with two nets.

## 2. A port tile faces its partner unless pinned

A lone port's tile was the middle of its declared side (`h // 2`). Now the build chooses the tile
of that side **nearest the other end's attach point** — the outside net's end, the parent's, which
is the one that moves — and, for a one-lane port, the lane on the partner's side. `@w4` (or
`@w4L`) pins the tile, and a pin always wins; the build then records the pinned tile.

## 3. Port tiles are recorded in the .fkp and kept like committed routes

A new factory record, written once the tile is chosen and read back by every rebuild:

    port rib.iron at 0,4 dir E lane R items iron-plate
    port both.plate at 19,5 dir E lane LR items iron-plate|iron-plate
    port burn.feed at 6,9 dir N lane LR items iron-ore|coal

`<inst>.<name>` is the port; `at` the tile **in the module's own frame** (0,0 is the frame's
top-left, whatever the parent does with it), `dir` the carrier's direction there, `lane` `L`, `R`
or `LR`, and `items` what it carries (`|` splits a pair's lanes). Since the tile is in the
module's frame, **a parent change never moves a port**: moving or turning the instance keeps the
record, the port tile and the module's inside routes byte for byte. On a parent move, the
crossing's outside segment is what changed.

The record travels with every step that writes a layout (place, route, hands, tiers, unfold), so
`fk build --place` → `route` → `hands` → `tiers` keeps it. `PORT` gains two lines: a committed
tile and a pin that disagree ("the pin wins"), and a record whose port the source no longer
declares ("drop the port line"). `.fkp` files written before this release have no `port` lines and
read exactly as before.

## Verified

`tests/test_ports2.py` (12 new): the carrier says `A|A` and `lane LR` and reads as both lanes; the
15/s crossing (two-sided `MinerRow<n=30>` → `X | X` out port → `X | X` in port → a base) routes
with no `SEAL`/`FRAME`/`PORT` line and 7.5/s required on **each** port lane (15/s in all), with no
`CAPACITY` line for the port; the same design with one-lane ports gives two `CAPACITY` lines,
"15.00/s asked through it, and a one-lane port carries 7.50/s"; the crossing is connected with no
LEAK; an unpinned port lands on the partner's row (own tile 0,4 — the middle would be 0,5) and a
pinned `@w2` keeps its tile; a turned instance keeps its recorded tile (own 0,4, carrier at
45.5,10.5 facing S) where a fresh build would choose to face its partner (own 0,9); the `port`
line round-trips through `dumps`/`loads` and passes `invariants`; a parent move keeps
`lay.ports` and the inside routes identical; a pin/record disagreement and a record for a renamed
port are `PORT` lines. `tests/test_modules3.py`'s port-tile expectations moved with the choice
(the middle row → the partner's row), and the "taken inside tile" check pins its port so the row
still stands under it.

The full suite: **957 tests, OK** (945 before, plus 12).

## Not in this release

The rest of `PLAN-GLOBAL.md`: the root design (plots as sealed instances, phase B), root nets
between plots (C), one rate model for the world (D), the example and the lab (E), and the docs
and runs (F). A port's lane is recorded and used to rate it; making a one-lane port's carrier say
*which* lane it is (so the route must meet that lane) is 2.1's lane-directed routing, not this
slice.
