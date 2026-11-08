# 3.0.2: lanes by the belt model

3.0.2 ships PLAN-LANES (`assessment-20261108\PLAN-LANES.md`), Rory's goal from 2026-11-08: the
router routes lanes by the measured belt model, not by special rules like `no_bend` or by a
fixed join construct.

## What changed

- **The lane physics is one table, `fkcore/lanephys.py`.** These are the rules CORE-V2 measured
  on 2.0.77, written as functions on directions:
  - `moves` gives a move's lane edges and its blocked lane, for straight, turn, tunnel,
    splitter, side and ug_side;
  - `carry` gives what each lane holds after a move;
  - `drop_lane`, `turn_drop_lane` and `mine_lane` give where an inserter or a drill drops.

  `lanes.build`, the lane graph, reads the table and behaves as before. `test_lanephys`
  checks the table against CORE-V2's measured rows.
- **Fed tiles follow the belt model.** On a tile that other carriers feed, the search may place
  only the carriers that keep what the tile must hold (`lanephys.tile_mask`, held in
  `Grid.lane_ok`).
  - The check runs on steps, tunnels, a path's end, splitter starts and the belts `grow` lays
    when it drops a splitter.
  - `NetJob.lanes` declares a fed tile's feeds and needs. It replaces 2.1.31's `no_bend`.
  - The Rust kernel gets the verdict bits only, so no lane rule is written in Rust.
- **Lane pairs route by where each lane must end** (`pairs.route_lanes`). Each trunk root tries
  two orders:
  - the trunk first, then A and B side-load onto any belt of its stem;
  - A and B first into the root's sides, then the trunk.

  The lane graph judges every layout, and the cheapest valid one wins.
  - 2.1's fixed join (`_laid`) and `FK_LANE_ROUTE` are gone. Reports say "trunk" where they
    said "join".
  - An empty side's stub belt is kept as `~A|B/z0`, so rebuilds keep it.
- **New lane helper.** `lanes.reach` carries labels along the lane graph and stops at machines.

## Numbers

- **28 pair jobs.** Every one routes.
  - Pairs cost 42 less in all: 10 are cheaper and none dearer.
  - Wide nets cost 103 less: 7 are cheaper.
  - Pinned lanes cost the same.
- **Slower.** Pair routing takes 9.5 s, against 2.1's 2.6 s. Each root tries both orders, and
  the lane graph judges each try.
- **Python and Rust match.** They lay the same trees on 150 random fields with fed tiles.
  - The branch's tests pass both ways: 170 in Python, and 180 with `FK_NATIVE=check`.

## Upgrading

- **Compiled modules are routed again once.** `ROUTER` and `COMPILE_VERSION` are 3.0.2, because
  routes at pair joins change.
- **The kernel is 0.2.0, and it must be rebuilt.** Its call passes `[(tile, mask)]` where 0.1.0
  took the `no_bend` tile list. A mismatched kernel and toolkit fail at the call and fall back to
  Python, so nothing breaks, but it is slow. Rebuild with
  `python -m maturin develop --release` in `native/fkroute`.
- **No design change is needed.** The `lanes A | B` syntax is unchanged.
