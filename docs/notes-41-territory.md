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

**The open flower** (`tests/data/flower/flower_open.fk`: six rivers and the core unplaced, no
corridors, 55 nets at the flower's level, 28 of them the rim ore feeds from the flower's own
unpinned edge ports; `fk layout flower_open.fk FlowerOpen`, the frame 900x1024):

| | |
|---|---|
| elaboration (not the layout's) | 4-9 s; `build_tspec` 3-7 s (the rate model over 6461 nets) |
| `place_seeds`, fkroute | **14.4 s** alone, 21.5 s with a paper build running beside it; 60 sweeps (the cap, it never stopped on its own) |
| of that, the final cut at 1 tile a cell (adapt + the unpriced walk over 55 nets) | 0.6 s |
| cells against their needs | all seven at 100 % (a declared frame is its own need) |
| estimated belts | 21288 -> 9695 tiles (the start lattice to the end), every net reaches its consumers |
| hot tiles | 2168 (every net to the core converges on a few core ports; 9 belts on the worst tile) |
| shared boundaries | 0 of 27 inter-module nets: the cells are the frames and the frames do not touch |
| the arrangement | circuit N (turned 3, its mouth east), works NE, fen E, core centre, mesa S, meadow W, ridge SW: the plan's ring order with fen/works and meadow/ridge swapped |

The grid did not matter here: cells (8, 8, 4, 4, 4, 4), (8,) alone and (8, 8, 4, 4, 2, 1) all
end at the same positions; (8,) alone took 21.7 s against 14.4 s (the coarse grid's windows are
small, but at step 1 the ports' cells on an 8-tile grid make every move look the same and the
sweep keeps trying). The Python reference takes 19 s for *one* sweep on the 8-tile grid: it is the
reference, not the tool.

**The paper build** of the laid-out open flower against the corridor flower (`fk build --to
report_checks`, the docs template, `terrain none`, plot 900x1024): both builds were started at
02:05 on 2026-11-09 in the session's scratchpad (`flower5\` the open flower with the seven hints
written, `flowerc\` the corridor `flower.fk`; `paper_open.log` and `paper_corridor.log` get the
summary line, the check-line counts and the carriers by net depth when each finishes) and were
still routing their rivers' insides (fen's units, after the core's lab fields at 15 to 30 s each)
when this note was written: a whole flower on paper routes some 6,500 nets, tens of minutes. The
comparison that matters is the carriers of the flower-level nets (net depth 1 in the .fkp, 55 of
them) against the corridor layout's 27 flows through four corridor modules; the rivers' insides
are the same files in both. To redo it: `python tests/data/flower/open_flower.py`, copy
`tests/data/flower/*.fk` to a game folder, `fk layout flower_open.fk FlowerOpen --write`, then
the docs template through `report_checks` with `place flower_open = flower_open plot 0,0
900x1024` in `nauvis.surface`.

**Synthetic.** `FK_NATIVE=check` parity: 30 random `voronoi` calls (fixed seeds, frames, blocked
rectangles, cells 1 to 8) and 12 random `place_seeds` specs (4 seeds, some placed, some fixed,
pinned and unpinned ports, edge terminals, obstacles, final cells 1 and 2) agree exactly; the
kernel is 15-20x the Python on those. `tests/test_territory.py`: 14 tests, 36 s with the kernel
(the flower test is most of it). The weight adaptation: with seeds spread out (4 in 100x100, at
least 35 tiles apart, needs 600-1800) 226 of 230 cells land within 5 % at 1 tile a cell; the four
that do not (at most 21 % over) are small needs far from any wall or neighbour, which the wall
model cannot shrink (a cell far from every wall has a minimum size: everything nearer its seed
than the walls). Crowded random seeds with incompatible needs stop at the cap, as the plan says.

**territory.fk** (the example, two 8x8 modules in 40x40): 9 sweeps, 0.0 s, the build 4 of 4 nets,
18 carriers.

## Open

- **Declared frames are their own need, so their cells are rectangles that do not touch.** Wave
  1 as the plan wrote it: the territory of a `size WxH` module is that box. The shared-boundary
  promise (ports on a common boundary) needs cells larger than the frames: the hull (H5) as the
  need with the frame as the claim, or a room factor on declared frames. Measured as a probe (the
  keep-home guard applied to framed seeds, so cells could not shrink to their frames): 20 of 27
  inter-river nets had their cells touching, at 123-161 % of need.
- **The weights are all 1.** `layout._weights` runs the rate model, and the flower's rim ports
  have nothing behind them on paper, so every net is one belt; the plan's ring order (fen NE for
  the plastic and acid into circuit) is not recovered. A port's declared pair or the contract's
  rates would weigh the nets without a fed design.
- **The sweep hits its cap (60) and does not settle.** 0.23 s a sweep on the flower alone;
  `--sweeps 150` ends at 10061 estimated belts, 300 at 9475, 150 with alpha 100 at 9485 (60: 9695;
  all with a paper build running beside, 51 to 109 s), every one at its cap: the price keeps
  moving the modules by a step and the unpriced estimate wanders within 6 %. PLAN-4.0's loop
  stops when nothing moves at step 1; with seven bodies and 55 nets of weight 1 something always
  moves. A plateau rule (stop when the Lagrangian has not improved for k sweeps) is the fix.
- **Unpinned edge ports collapse onto one tile.** The flower's 8 copper and iron feeds for
  circuit each take the edge tile nearest circuit's pinned rim port (that part is right), but
  nets to the core's pinned ports share the few tiles before them: 2168 hot tiles, which the price
  spreads only by moving whole modules.
- **The weight adaptation** is a proportional step on an observed rate (tiles per unit weight):
  stable, within 5 % where the geometry allows, 15 % on the 4-tile grid in one of 12 spread cases.
  A frameless seed keeps its home cell by a floor on its weight; a framed one may shrink to its
  frame.
- **Wave 2** (T4 to T6): pins on ore, `fk layout nauvis.fk` on the surface file, the build
  reading `out/territories.json` as the assigned frames, `fk look` drawing the cells, the lab
  ground east of x 2100.
- `min_width` (the longest rigid body) is recorded in territories.json and not enforced beyond
  the frame, which is the rigid body in wave 1.

## The paper comparison, measured after the merge (integrating session, 2026-11-09 02:42-03:19)

Both builds on main `c2596ef` (the agent's two died with its worktree), the docs template through
`report_checks`, `terrain none`, plot 900x1024, one after the other on this laptop:

| flower | nets | unrouted | carriers | on the flower-level nets |
|---|---|---|---|---|
| laid out by `fk layout` (the seven hints the agent wrote) | 6461 | 50 | 32759 | 4909 (depth 1) |
| the corridor `flower.fk` | 6559 (98 corridor pass-throughs) | 48 | 30899 | 1182 (depth 1) + 1737 inside the four corridors (depth 2 beyond the rivers' own) = 2919 |

Both took about 1100 s. 48 of the unrouted nets are the rivers' own and the same in both (the
designers' open failures); the laid-out flower adds 2 flower-level failures and 68 % more belt
on the inter-module flows. **The plan's bar (every inter-module net routed with no more carriers
than the corridor layout) is not met in wave 1.** The causes are the open points above, in
order: cells equal declared frames, so no two modules share a boundary and every inter-module
belt crosses open ground (0 of 27 nets touching); every weight is 1 on paper, so the ring order
is not recovered and the heavy flows do not pull; the sweep never settles. Wave 2 (hulls or a
room factor as the need, weights from the ports' contract rates, a plateau stop) reruns this
table before T4 starts.
