# 41-hull: frames as tile sets (PLAN-ORGANIC part H, wave 1: H1 to H4)

Branch `claude/41-hull`, cut from main cfb10f0 (3.1.4, fkroute 0.4.0). Two sittings on
2026-11-09: the first wrote H1 to H4 and a draft `tests/test_frame.py` and was held at Rory's
pause with six of its tests failing (the WIP commit 46bbc37); the second (this note) went through
the WIP as untested, fixed the tests and the code, and ran the bars.

## What landed

- **H1, `fkcore/frame.py`** (stdlib, pure): `Frame`, a tile set run-length by row with its
  bounding box. From a box (`from_box(w, h)` or `from_box(x0, y0, x1, y1)`: the fast path, a
  box stays a box through `turn`, `moved`, `is_box`), a polygon (`from_polygon`: integer vertices
  in the module's own frame, scanline over tile centres by the even-odd rule, a centre on an edge
  is outside), a run list (`from_runs([(y, x0, x1)])`: part T's territory form, `runs()` gives it
  back unchanged) or a tile set (`from_tiles`: an achieved hull). `turn(rot)` about the origin
  exactly as `compose.turn` turns a point of the bounding box; `grow(n)`; `contains` / `in`;
  `boundary(side)` (the outermost tile per column for n/s, per row for e/w), `boundary_at`,
  `boundary_near` (where `@n12` lands when column 12 is off the frame), `nearest_boundary(point,
  side=None)`; `overlap`, `overlaps_box`, `clip`, `area`, `size`; `rows_text()` as rows of `#`
  and `.`. `shape_problem(verts)` says why a polygon is no frame (too few corners, a corner behind
  the origin, a repeated corner, every corner on one line, a fold, a crossing) or None.
- **H2, the module line.** `module Ell shape (0,0) (20,0) (20,8) (10,8) (10,16) (0,16) { ... }`
  where `size WxH` stands (`lang.py`: three or more whole-number corners is the grammar, `size`
  and `shape` together a syntax error; `Module.shape`, and `Module.size` is the polygon's bounding
  box). A polygon that is no frame is a `bad-shape` check line, once per module, and the module
  is read as its box (`elaborate._module_shape`); `Inst.shape` and `PortInst.shape` carry it. An
  instance's `@(x, y, rot)` turns the polygon about its origin as it turns the box.
- **H3, ports on any frame.** `expand._port_tile(port, frame)` takes the module's `Frame`
  (`expand.own_frame(inst)`: the shape, else the size box, cached per polygon): on a box `@n12` is
  edge tile 12 as always; on a polygon it is `boundary("n")` at column 12, and a column the frame
  does not reach is `port-off-frame` (elaborate `_port_checks`, a check line naming the tile it
  moved to) with the port on the nearest boundary tile of that side. An unpinned port faces its
  partner on the side's boundary (`_side_tiles` is `frame.boundary(side)`); `record_misfit`
  re-chooses a 2.0.41 record that is not on the boundary any more. The record stays the tile in
  the module's own frame, as the parent reads it.
- **H4, the readers.** `expand.frame_shape_of(flat, lay, path, cat)` is the placed instance's
  Frame (own frame turned about its origin, moved to the record); `frame_of` is its box,
  `planned_shape` / `planned_frame` the same before placing. Through it: the router's keep-out
  and the sealed unit's blocked tiles (`route._route_layout`, `try_route`: inside the box but
  outside the polygon is the parent's ground), `crosses-frame` and `FRAME` (`seal_checks`, the
  FRAME line says "N tiles of the box: its shape"), `frame_overlaps` (now `(a, b, box, n)`: the
  shared tiles' box and count; two polygons whose boxes meet but whose tiles do not are no
  overlap; the `overlap` line reads "share 32 tiles in 8x6 at ..." and as before for boxes),
  the fluid pass's frames, the placer's taken tiles (`_taken`), the empty-slot tiles
  (`flow._empty_slots`), the store's unit key (a polygon unit keys by its tiles too; a box adds
  nothing), `fk explain` (a polygon prints `frame  240 tiles of the 20x16 box` and the rows; a
  box prints no rows), `fk look` (`rows` per frame, drawn filled, at any rotation),
  `layout._shapes(frag, frame)` (a sealed instance's footprint per rotation is its frame turned)
  and `layout.build_spec(module=...)` (inside a polygon, the box's tiles outside the shape are
  `Spec.blocked`; `box_from` says "the shape of Ell (240 tiles in its 20x16 box)").
  `placements.Record.frame` (row runs in map coordinates) makes `contains` read the frame when
  a record has one.

## Decisions taken here (say if otherwise)

- **A polygon's tiles are the ones whose centres it holds.** With whole-number corners an
  axis-aligned edge never meets a centre, so a box and an L rasterise exactly; a 1:1 slope has
  centres on the edge, and those tiles are outside (the frame is conservative: a half tile is the
  parent's ground, and the module's machines must stand on whole tiles anyway).
- **Every corner on one line is "no area", not a fold.** The WIP named the fold; the test wanted
  the area. Both are true; the area is the useful word, so it is checked first. A bowtie still
  reads as a crossing (its signed area is zero too, so the crossing test cannot be the area).
- **`Record.frame` is the field, not yet filled.** Nothing in wave 1 makes a plot a polygon: a
  surface's `place` is a box and the world's shaped modules live inside one plot. T5's
  territories (`out/territories.json`) and H5's hulls are what will fill it; the registry's
  "under a design" test is ready for them.
- **The store does not keep the declared frame yet.** The declared frame is derivable from the
  design, and the frame the store should keep is the achieved hull (H5). The unit key already
  tells a polygon from its box.
- **Docs wait for H6** (`shape.fk`, EXAMPLES chapter 6, LANGUAGE's module row): docs around
  examples, and the example is H6's.
- `fk look` draws a declared frame at any rotation now (it drew modules at rotation 0 only and
  fell back to the entities' extent otherwise); the box it draws is the frame turned about the
  instance's origin, as the build places it.

## Test runs

- `tests.test_frame`: 21 tests, OK (the WIP's six failures: five were the test's own arithmetic,
  one the code's "no area").
- `tests.test_simview tests.test_look tests.test_module_overlap`: 30 tests, OK.
- Neighbours (`test_lang test_elaborate test_placer test_size test_examples_docs test_agent_kit`):
  63 tests, OK (56 s).
- The merge set (CLAUDE.md's list plus `test_module_overlap`, `test_layout`), in the background:
  394 tests, OK (249 s, with the neighbours running beside it). It ran on the WIP's code;
  the two code changes since (the "no area" early return, `fk look` at any rotation) are
  covered by `test_frame`, `test_simview` and `test_look`.
- `FK_NATIVE=check python -m unittest tests.test_layout` (kernel/Python parity): 11 tests, OK
  (123 s). `tests.test_frame` under `FK_NATIVE=check` (the L's polygon footprint and its
  `blocked` notch through both kernels): 21 OK; its `ReadersTest` under `FK_NATIVE=0`: 7 OK.
- By hand, `python -m fkcore check` and `fk explain shape.fk ell` on an L-shaped module: 0 check
  lines, the frame printed as 16 rows with the notch as `.`.

## Open

- H5 (the achieved hull into the store and `out/frames.json`; `fk layout FILE MODULE` inside the
  assigned territory) and H6 (the example and the docs) are wave 2.
- `size.py`'s does-not-fit reads `planned_frame` (the box) and is M's file: a polygon instance
  past its plot is judged by its box there until M or wave 2 reads `planned_shape`.
- `corner_hint` / `origin_hint` work on the turned bounding box, as the plan says; a polygon's
  corner hint is its box's.
- `fk look` draws ports at rotation 0 only, as before.

## Files touched outside part H

- `tests/test_module_overlap.py`: the `frame_overlaps` tuple gained the shared tiles' count.
- `fkcore/layout.py`: `_shapes(frag, frame=None)` and `build_spec`'s `blocked` / `own_frame`
  (H4 as the plan names it); `usable` / `fits` (R's) untouched. No change to `placer.py`,
  `size.py`, `territory.py` or any Rust.
