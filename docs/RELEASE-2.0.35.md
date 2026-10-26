# Toolkit 2.0.35: the right tap (phase 2, fourth slice)

Rory, 2026-10-25: "instead of an exiting underground use an entering underground, and then the next
tile is the exit, and then belt after that as usual." The lab measured it at ~7.4/s on the left lane,
like the left tap. This slice puts it in the port map and makes `right` buildable.

## The statement

```
bus = Bus<belts=4, item=iron-plate>(
        in1: smelt.plate,
        right fg: gears.iron,     # a right tap: a UG entrance at the stub, its exit one row out
        fb: belts.iron)
```

- A **right tap** is a UG **entrance** at the stub tile and its **exit** one row further out (north
  for a north-side tap, south for a south-side one), the route meeting the tile beyond the exit.
  The exit takes only the lane on its open side, so it is one belt of capacity like the left tap.
- That exit row is **outside the bus's edge rows**, so the fragment **grows the frame by one row** for
  a bus that has a right tap: for a north-side tap it shifts the whole bus down one row (so the exit
  sits at the frame's top row); for a south-side one the extra row is at the bottom. A bus with right
  taps on both sides grows by two. Buses without right taps are untouched — same frame, same
  entities, so existing designs stay exactly where they were.
- The tap's role (the net binding and the attach point) is the exit's tile, so the layout's route
  starts from the exit's output and the carrier chain is entrance → exit → route.

## Verified

`fk check` clean and `fk layout` 24 entities with no invariant failures on the right-tap example, with
the rates unchanged (`loads bring 4.000/s, taps would take 2.000/s`). The 22 tests in
`tests/test_bus_map.py` include the right tap's fragment now: an `ug=in` entrance at the stub (shifted
to row 1), an `ug=out` exit at row 0, the role's attach on the exit's tile, the frame one row taller
(5 rows for a 2-belt bus), and the same binding. A dual tap's entity, role and size are unchanged, so
the elaboration baseline over the 42 existing designs still passes and the suite's pre-existing
failure/error lines are the same set as 2.0.27's tree.

## Lab check (the real paste/revive path)

The right-tap design, laid out locally and pasted on the lab after generating its chunks: **24 ghosts,
23 revived, 0 failed**, and the tap's pieces are a valid ug=input at (945.5, 605.5) with its
ug=output one row out at (945.5, 604.5), plus 15 belts. So the frame row and the entrance/exit pair
survive the build path the toolkit actually uses.

## One thing to watch in the lab

The right tap's frame is one row taller than a dual/left bus's, so a design that mixes a right tap with
a pinned `length`/frame assumption needs re-checking; the lowering's computed `length` already accounts
for the tap bands, not the extra row. The lab check (via `fk lab`, the real paste/revive path) should
come with the phase-2 pair bus, so one build exercises mouths, taps of all three kinds and the pool.
