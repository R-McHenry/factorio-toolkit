# 43-territory: the T fixes, pins on ore, the world command (PLAN-ORGANIC T, wave 2)

Step 1 sha: 23aaf45 (the three fixes, measured; the integrating session's two paper builds run from it)

Branch `claude/43-territory`, cut from main 90e20a0 (3.1.4 + wave 1). Measured 2026-11-09 on this
laptop, fkroute built from the tree (`python tools/native_build.py`), the open flower
`tests/data/flower/flower_open.fk` laid out with `fk layout flower_open.fk FlowerOpen` (900x1024);
the "alone" seconds are `place_seeds` with nothing else running.

## Step 1: the three fixes

### What landed

- **Cells touch (T1 revisited).** `TParams.room` (per cent, default 150): a declared frame is
  the claim (the cell holds it outright, as in wave 1) and the need is `room` per cent of its
  area (`build_tspec`: `max(need_of, w * h * room // 100)`), so neighbouring cells meet. Two
  things in the weight adaptation had to change for that to hold, both in `Diagram.adapt`
  (Python and Rust alike):
  - the **dead zone**: a framed seed's cell is exactly its frame for every weight below the one
    that wins the ring outside the frame, and a step that moved the area not at all was halved
    like a step that moved it the wrong way, so a cell once sunk to its frame never grew back
    (the probe's keep-home floor on framed seeds hid this; the floor itself over-sized small
    cells, 147 % and 170 % of need on the territory.fk pair, and is not applied to framed seeds);
    now a step with no effect doubles;
  - **never under**: a small frame's ring comes whole (an 8x8 frame's cell is 64 or 116 tiles,
    never 96), so a cell the rounds leave under its need takes the weight that gave it the least
    cell at or over its need. The report flags `(under its need)` and `(over its need)` apart
    (was `off its need`).
- **Ports where the belt leaves the frame.** Wave 1 projected a port onto its **cell's**
  boundary and walked between the boundaries; with the room factor that made the ground between
  a frame and its cell's edge (up to 22 tiles a side) free, and two frames anywhere inside two
  touching cells read as one belt apart: the territory.fk pair was placed with its frames abutting
  so that the real route failed (`1 unrouted` in the paper build). Now a terminal is the tile
  outside the frame at a pinned `@side[pos]` (the tile `fits` keeps free), or, unpinned, outside
  the frame's side at the tile nearest the partner (the 2.0.41 rule); the walk crosses the net's
  own two cells for free and pays `trespass` inside a third's (`_World.term_cell`, `field`,
  `eval_net`; `place.rs` the same). The estimate is the belt the router lays. **Decided here**:
  the plan's T3 wording ("each port on its cell's boundary facing its partner") is read as the
  cells being the ground the belt crosses, not the place the belt starts.
- **Weights from the contract.** `territory.net_weights(flat, cat, spec)` and `port_rate(flat,
  key, item, make)`: no rate model. Behind a port, the makers' full-speed output (`Machine.makes`)
  upstream of it or the consumers' appetite (`Machine.needs`) downstream, found by following
  `_in_hold` / `_out_hold` through every port met on the way (a sub-module's port, a Stack cell's
  pass-through `ore_in -> f, ore_out`), each machine counted once. A net's rate per item is the
  smaller of the known sides (supply, demand), the items summed over a pair's two lanes; the
  weight is that over a yellow belt's throughput (as `layout._weights` counts), rounded up, at
  least 1; a fluid net weighs 1 (a pipe is one carrier). `build_tspec` no longer calls
  `layout._weights` (the rate model took 3-7 s on the flower and gave 1 everywhere).
- **The plateau rule.** `TParams.plateau` (default 5): a step is done when nothing moved (as
  before) or when the Lagrangian has not fallen for `plateau` sweeps on it; the next step
  follows, and on the finest step the loop ends. The cap (`sweeps`, 60) stays the last resort.
  Found with a trace (`FK_TRACE_SEEDS=1` prints one line per sweep from either kernel): wave 1's
  loop never left **step 32** on the flower (something always moved by 32 or 64 tiles, the
  Lagrangian oscillating between 32 M and 37 M), so all of its 60 sweeps ran on the coarsest
  lattice and the 8-tile grid, which is why wave 1 saw "the grid did not matter". The brief's
  rule (the plateau at the finest step only) would never have fired; applying it per step is the
  decided difference.
- **Two cuts in the sweep's cost**, needed once the loop reached the fine steps (a sweep on the
  4-tile grid costs about four times one on the 8-tile grid): the four rotations are offered on
  the coarse steps only (8 and up; a turn swaps a 200-tile module's ports to another side, no
  fine move), and an accepted move routes only the moved seed's nets again (the other nets'
  terminals stand on their own frames and did not move; what the moved frame does to their paths
  the candidate step ignored too, and the sweep's end routes every net).

### The flower, before and after

The estimated belts are not one measure: before, the walk ran between the cells' boundaries
(two touching cells cost one belt whatever the frames did); after, between the frames' port
tiles (the belt the router lays). The weighted figure is the Lagrangian's estimate without the
price.

| | before (90e20a0) | after (room 150, plateau 5, contract weights) |
|---|---|---|
| inter-module nets with their cells touching | 0 of 27 | 21 of 27 (apart: circuit-works rg, circuit-ridge rp, fen-circuit acid and plastic x2, fen-mesa plastic) |
| estimated belts, start -> end | 21288 -> 9695 (boundary to boundary) | 15840 -> 8518 (frame to frame) |
| weighted belts | the same (every weight 1) | 31424 -> 17418 |
| hot tiles (worst) | 2168 (x9) | 3529 (x24: circuit's eight rim ore feeds, weight 3 each, on the edge tiles before its ports) |
| sweeps | 60 (the cap), all at step 32 | 51, on its own: step 32: 10, 16: 11, 8: 8, 4: 9, 2: 6, 1: 7 |
| place_seeds alone | 16.3 s | 34.6 s |
| cells at their need | 7 of 7 at 100 % (the frame) | 7 of 7 within 5 % |
| arrangement | circuit N-W (rot 3), works NE, fen E, core centre, mesa S, meadow W, ridge SW | circuit NW corner (rot 3), fen NE, works E, mesa S, meadow W, ridge W lower, core centre-west |

The corridor flower's hand arrangement (flower.fk): circuit N centre, fen E upper, works E lower,
mesa S, ridge W upper, meadow W lower. Fen is back beside circuit in the north-east (the
plastic and acid weigh 7 belts together) and works below it; meadow and ridge are swapped against
the hand layout (each has one belt from circuit, g_meadow and rp_ridge, weight 1, the rest to
the core and the rim: the two sides weigh the same to the placer). Circuit sits in the corner,
not the north centre: its eight rim feeds (24 belts) take the north edge's tiles nearest its
ports, and turned 3 (ports west) those tiles bunch at the corner, 24 belts on one tile.

**The time bar is not met** (well under 14 s): the loop now runs the fine steps wave 1 never
reached, 22 of the 51 sweeps on the 4-tile grid at about a second each. Where it goes, per sweep
at the 4-tile grid: 7 seeds x 8 moves x 1 rotation candidate evaluations, each the moved seed's
~8 nets walked in a window of the terminals' box plus 160 tiles a side (`window`: max(6, (gw +
gh) / 12) cells), and the seed's diagram recomputed in that window; then one full evaluation of
the 55 nets. The margin and the candidate set are the knobs left; neither was cut here, since
a route that cannot leave its window reads as unreached and the penalty moves modules for the
wrong reason.

**The weights the flower gets** (yellow belts; the rim ore feeds are the furnace columns'
appetite, the taps the makers' output):

| weight | nets |
|---|---|
| 7 | ridge_stone1 |
| 5 | ridge_tap2 (stone-brick, rail) |
| 4 | circuit_tap1, mesa_fe_ore1, ridge_fe_ore1-5 |
| 3 | circuit_cu_ore1-5, circuit_fe_ore1-3, fen_coal, fen_plastic_out1, fen_plastic_out2, meadow_fe_ore1, mesa_cu_ore1-3, ridge_stone2, ridge_tap1, works_fe_ore1-2 |
| 2 | circuit_rg_works, circuit_tap2, fen_plastic_mesa, fen_tap, meadow_tap, mesa_tap, works_tap1 |
| 1 | the rest: the fluids (crude, water, acid, lubricant), g_meadow, rp_ridge, pu, fen_fecu, meadow_cu_ore1, the science belts, lds, rf, works_tap2, ridge_tap3, fen_sb_works |

**The room factor**, measured before the terminals moved to the frames (boundary-to-boundary
belts; plateau 5, all at the cap of 60, the four runs side by side so no seconds):

| room | touching | estimated belts | hot tiles | cells off their need |
|---|---|---|---|---|
| 125 | 23 of 27 | 3879 | 1807 (x9) | 3 over (circuit 115 %, meadow 137 %, ridge 125 %: a cell near the plot's edge cannot shrink below what the walls give it) |
| 150 | 23 of 27 | 3962 | 1918 (x7) | 0 |
| 200 | 24 of 27 | 4520 | 2093 (x13) | 0 |

150 is the default: every cell at its need, the belts within 2 % of 125's. In the same series:
plateau 3 stopped at 31 sweeps with 7197 belts (the fine steps cut short), 8 reached the cap with
4207; weights all 1 gave 10634 belts, 22 of 27 touching and works N-E with fen E (the wave-1
ring): the weights are what brings fen beside circuit.

**territory.fk** (the example): `a = Maker @(28, 0)`, `b = Taker @(32, 16, rot 3)`, cells 95 of
96 and 122 of 96 (over), 1 of 1 nets touching, 4 estimated belts, 9 sweeps, 0.0 s; the paper
build routes its 4 nets: `24 entities, 19 edges` (wave 1: 30 and 25, the frames apart).

## Step 2: T4 pins on ore, T5 the command on a surface

### What landed

- **T4, pins.** `Seed.pin` (the cell as row runs) and `Seed.patch` (its name). A module
  instance with `@patch(RES)` is pinned when the design has ground to read: `placer.patch` for
  `RES#k`, else `placer.nearest_patch` to the box's centre (there is no position to be near
  before the layout; the notes say so). Its frame is centred on the patch's centroid at rot 0
  (clipped into the box; an `@(x, y)` written beside the pin is taken as the position), its
  cell is `pin_cell`: the patch's tiles and the frame's, grown ring by ring (`grow_to_need`,
  4-neighbours, inside the box, off the water) to the need, as runs (`runs_from_tiles`). In the
  diagram (`Diagram(..., pins=)`, Python and Rust) a pinned cell is `fixed_owner` over any wall
  (the ore under it is a wall for everyone else), the seed is **static** (fixed or pinned:
  competes for nothing, no weight, no prune), and `fits` keeps every other frame off the pinned
  cell's rectangles (`rects_of_runs`, both kernels) as off the ore and the water. `fkroute.voronoi`
  takes `pins=` (eleventh argument); `place_seeds`' seed tuple carries the runs as its eighth
  element. The report reads `pinned on iron-ore#1` on the cell line and `name = Kind @(x, y)` for
  the pinned module too; `--write` puts `@(x, y)` beside `@patch(...)` (the grammar takes both;
  `fk build` then places it there and the pin stays the design's word). `territories.json` gets
  one key per pinned cell, `"pinned": "iron-ore#1"`, and `"terrain": "<name>"` at the top; the
  runs and the rest are as wave 1 wrote them (part H's `Frame.from_runs` reads them unchanged).
- **T5, the command on a surface.** `fk layout nauvis.fk [--write] [--all]` on the top level:
  `surface_ground(path, flat)` reads the surface file beside the design (`place <factory> =
  <module> plot x,y WxH`, the module being the design's file name) for the plot, which is the box
  (`layout_file` found it already through `_plot_of`), and `<terrain>.terrain.json` beside the
  design for the ground: `terrain.frame_ground` puts water, cliffs and ore into the plot's frame,
  the blocked tiles become rectangles (`rects_of_runs`) and the ore too, for every seed but the
  pinned. `world_scope(flat, module, all_)` counts `@patch` modules as the world placer's and,
  with `--all`, every framed module (so a placed world can be laid out again). The report adds
  `ground <name>: N blocked tiles (water, cliffs), M ore tiles in K patches` and the notes
  `no-terrain` (no file: the pins are notes, the modules movable), `no-patch` (no such patch).
  Water and cliffs are obstacles exactly as `voronoi` took blocked rectangles in wave 1.
- `fkcore/layout.py`: one argument added to the one call I may touch
  (`territory.world_scope(flat, module, all_)`).

### Measured

`tests/test_territory.py` `PinsTest` on a synthetic 120x120 terrain (iron-ore#1 20x14 at 70,20,
iron-ore#2 8x8 at 10,100, copper 12x10 at 40,90, a lake across y 60..66 with a 20-tile gap): the
two mines pinned on their patches (frames centred within a tile of the centroids, cells 576 of
576 holding every patch tile), the smelter's cell and frame off every ore and water tile, every
net reaching its consumers, `--write` writing 3 hints that read back with the pin kept; without
the terrain file the pins are notes. The report:

```
layout world: 3 modules, 3 placed now, 0 kept, 0 fixed; 2 nets; plot 120x120 (--plot); territories (fkroute)
  mine = Mine @(68, 19) @patch(iron-ore)
  mine2 = Mine @(2, 96) @patch("iron-ore#2")
  smelt = Smelt @(72, 38, rot 1)
  ground t: 600 blocked tiles (water, cliffs), 464 ore tiles in 3 patches; ore is blocked ground for every module but a pinned one
  cell mine: 576 tiles of 576 needed (100 %)  pinned on iron-ore#1
  cell mine2: 576 tiles of 576 needed (100 %)  pinned on iron-ore#2
  cell smelt: 600 tiles of 600 needed (100 %)
  estimated belts 208 -> 133 over 2 nets; every net reaches its consumers; 135 hot tiles ...; 20 sweeps
  shared boundary: 1 of 2 nets between modules have their cells touching; apart: ore2 (mine2|smelt)
```

Parity: the random `voronoi` specs pin one seed half the time and the random `place_seeds`
specs 40 % of the time; `FK_NATIVE=check` agrees. `tests.test_territory`: 21 tests, 50 s with
the kernel.

### Step 3, toward T6: what to run

The lab's ground is not in any terrain file this tree can read (`lab-session\fk-run2\game` has
`terrain map` in its surface file and no `map.terrain.json`), so the surface file and the
command are described, not written:

1. On the lab server: `fk read-terrain map --area 2100,-600,3100,600` into the game folder of the
   flower copy (the area the flower needs: 900x1024 plus a margin; adjust y to where the water
   is wanted).
2. `nauvis.surface` beside the design: `surface lab`, `free`, `force lab`, `terrain map`,
   `place flower_ground = flower_ground plot 2100,-512 900x1024`.
3. `flower_ground.fk`, written by `python tests/data/flower/ground_flower.py` (in the tree): the
   open flower with the rim ports replaced by stand-in modules, one per rim feed: `Stand<res>`
   (40x40, a 45/s source of the ore, `@patch(RES)`: copper, iron, stone, coal; a `A | B` pair feed
   gets two stands and a `lanes` line), `Well` on `@patch(crude-oil)` (a pumpjack), `Shore` for
   the water (an offshore pump, not pinned: water is no patch), their out ports feeding the
   rivers' in ports. It elaborates to 36 seeds (7 + 28 stands + 1 shore) and 55 nets, weights 1
   to 5; without a terrain file its 28 pins are notes and the stands move like modules.
4. `fk layout flower_ground.fk --write` (the plot from the surface file), then the docs template
   through `report_checks`. Copy the flower's `.fk` files beside it; `out/territories.json` is
   written beside the design.

## Open

- The time bar: 34.6 s alone against well under 14 s (above).
- `fk look` drawing the cells: `vision.design_tags` draws plots and instances from the composed
  surface and the .fkp files; the territories live in `out/territories.json` beside the design,
  so drawing them is a new layer reading that file (a `_territories(frame, path)` beside
  `_tags`), not one call into the outline drawing. Open.
- A docs example on the terrain fixture (`patch.terrain.json` has iron-ore#1 and #2): the
  chapter quotes the synthetic test's report; an example file needs `TERRAIN` and `LAID_OUT`
  entries in `tests/test_examples_docs.py` (not this part's file). Open.
- The lab's terrain read east of x 2100 and the T6 run itself (the integrating session's;
  `ground_flower.py` is the generator, above). The stands' sizes (40x40) and rates (45/s) are
  placeholders for the MinerRows the design will hold.
- A pinned module's frame may stand on water (the pin does not call `fits`); the cell grows off
  the water, the frame does not move. A check line would say so.
- Circuit's rim feeds: an unpinned edge port takes the edge tile nearest its partner's port,
  so a module turned with its ports along the edge bunches every feed on one tile (x24). The
  rim's ports stand for mines that are not in the design; T4's pins replace them on real ground.
- The six nets apart: circuit's belts to works and ridge (weight 2 and 1), fen's plastic and
  acid to circuit (3, 3, 1) and plastic to mesa (2). Fen touches circuit's cell corner-wise in
  the north-east but the walk from fen's south ports to circuit's ports runs round the core.
- The paper comparison is the integrating session's (the two 18-minute builds from the step-1
  sha).

## Decided here

- The plateau rule applies per step, not at the finest step only.
- The keep-home floor is not applied to framed seeds; the dead zone is fixed in the step rule
  and a cell is never left under its need when a weight over it was seen.
- Terminals are the frames' port tiles, the cells the ground a belt crosses (free in its own
  two, `trespass` in a third's).
- Rotations on the coarse steps only; an accepted move routes only the moved seed's nets again.
- Weights are in yellow belts, as the instance placer's, and a fluid net weighs 1.

## Files touched outside the part

- `fkcore/layout.py`, the one call the brief allows: `territory.world_scope(flat, module,
  all_)` gains the `all_` argument (step 2). Nothing else; step 1 touched no file outside the
  part. The merge of main (6b2334f, then 66b8801) brought nothing to `territory.py`,
  `territory.rs`, `place_seeds` or `layout_file`.
