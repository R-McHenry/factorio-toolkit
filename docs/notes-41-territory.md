# 41-territory: the world placer (PLAN-ORGANIC part T, wave 1: T1 to T3 on declared frames)

Branch `claude/41-territory`, cut from main cfb10f0 (3.1.4, fkroute 0.4.0). Measured 2026-11-09 on
this laptop, fkroute built from the tree (`python tools/native_build.py`).

## What landed

- `fkcore/territory.py`: the spec (`Seed`: a module instance with its declared size, its need,
  its longest rigid body, its ports in its own frame; `TNet`; the scope's own ports as edge
  terminals; `TParams`), the power diagram (`Grid`, `wall_dist2`, `Diagram`, `voronoi_py` and
  `voronoi`), the Python reference of the seeds' sweep (`_World`, `_place_seeds_py`, `place_seeds`),
  `need_of` (T1), `build_tspec` from a Flat, `world_scope`, `layout_world` (the command's report,
  `out/territories.json`, `--write`).
- `native/fkroute/src/territory.rs`: `Grid`, `wall_dist2` (Meijster's exact squared distance
  transform), `Diagram` (assign, prune to the piece holding the seed, capacity-constrained
  weights), `runs_of`, `fkroute.voronoi`. `native/fkroute/src/place.rs`: `fkroute.place_seeds`,
  the sweep over seeds beside the instance loop (`place` and `field` untouched). `lib.rs`: one
  `mod territory;` and two `add_function` lines.
- `fkcore/layout.py`: `layout_file` hands a scope whose sealed modules have no `@` to
  `territory.layout_world` (the only change there besides nothing); the instance placer keeps
  everything else.
- `tests/test_territory.py`; `tests/data/flower/` (the megabelt rivers and core copied from
  `lab-session\fk-run2\game` as read-only reference data, `open_flower.py` writing
  `flower_open.fk`: the six rivers and the core unplaced, no corridors, the flower's rim ports
  with a side and no tile).
- TOOLKIT.md's `fk layout` row and LANGUAGE.md's instance row mention territories.

## How it works (what the plan says, where this differs)

- **The need (T1).** A declared `size WxH` is the need (its area) and the claim: the cell holds
  the frame outright and the weights stop at the frame's area, so a declared module's territory
  *is* its frame in wave 1. A module without a size needs 3x its instances' footprints (the
  `ROOM` factor `build_spec` uses) and its frame (from `_own_frame`) is the claim inside a larger
  cell; its longest rigid body is recorded as `min_width` in territories.json, not enforced beyond
  the frame (the frame is the rigid body). Hulls (part H) replace the declaration in wave 2.
- **The cells (T2).** Integer arithmetic throughout: seed points in half-tiles, weights in
  quarter-tile^2, costs in milli-tiles. A tile nearer a wall (a blocked rectangle, a fixed frame's
  outside, the ring outside the box) than any seed's power distance is nobody's, so cells shrink
  to their need and the ground between them stays free. A cell is pruned to the 4-connected piece
  holding its seed. A fixed seed (an `@` instance) competes for nothing: its cell is exactly its
  frame. Weights adapt per call: shortfall x gain / 16, the gain halved when the shortfall changes
  sign, 40 rounds, cap (2 x the box's long side)^2.
- **The sweep (T3).** PLAN-4.0's loop over seeds: +-s and +-2s on each axis and the four
  rotations, steps 32, 16, 8, 4, 2, 1, the grid 8 tiles a cell for the two coarse steps and 4
  after, the territories cut at 1 at the end. A net's cost is the walk between its ports on
  their cells' boundaries: a pinned `@side[pos]` projected onto the cell (the outermost cell tile
  of that column or row), an unpinned port the boundary tile of its side nearest its partner's
  pinned port tile (else its seed); the scope's unpinned edge port the edge tile nearest the
  partner. The walk's fields are windowed (the terminals' bounding box plus a margin of max(6,
  (gw + gh) / 12) cells). Two rules the plan did not spell out, found on the first paper build:
  - the walk treats every placed seed's declared frame as closed (the real router keeps out of a
    sealed frame) except the terminals' own cells, and prices the rest of a cell `trespass`
    (1 tile per tile) so belts prefer the free ground between territories;
  - `fits` demands, for every pinned port, the tile outside the frame free (in the box, off the
    blocked ground and every other frame) and one more tile in the box beyond it, and no frame
    over a pinned edge port's tile; a terminal no route reaches costs 2 x (w + h) tiles, so an
    arrangement that strands a port is never the cheap one (PLAN-4.0's loop counted it as free).
- **Parity.** `FK_NATIVE=check` runs both and raises on any difference; the kernel is a speed-up
  only (`FK_NATIVE=0` runs the Python).

## The numbers

MEASUREMENTS

## Open

OPEN
