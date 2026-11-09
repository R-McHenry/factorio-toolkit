# 3.2: territories, frames and hulls, the hierarchy contract

3.2 is PLAN-ORGANIC (`..\assessment-20261108\PLAN-ORGANIC.md`), Rory's direction of 2026-11-08
night: routing-informed placement, irregular modules and automatic module placement, together an
optimized, organic-looking base; and, rolled in at his word on 11-09, the rerouting
investigation's results, the design sessions' hierarchy issues, and a warning in the docs that
every router issue is a hierarchy issue the designer owns. Built as two waves on branches
`claude/41-*` and `claude/43-*` (one agent per part, this session merging), with `claude/42-reroute`,
`claude/44-levels` and `claude/45-pairports` from Rory's own sessions, merged onto main 3.1.4
(`cfb10f0`). Read with the notes per part: `docs\notes-41-{territory,hull,mines,price}.md`,
`notes-42-reroute.md`, `notes-43-{territory,hull,mines,hierarchy}.md`, `notes-44-levels.md`.
The plan's "Wave 1 outcome" and "Wave 2 outcome" tables hold the measurements.

## The language

- **`shape (x,y) (x,y) ...` on the module line**, where `size WxH` stands: a module's frame is a
  polygon (whole-number corners in the module's own frame, closed, simple; a polygon that is no
  frame is the check `bad-shape` and the module is read as its box). `size` stays as the box
  shorthand. An instance's `@(x, y, rot)` turns the polygon about its origin as it turns a box.
  The one language addition of the release.
- **`@patch("iron-ore#2")`**: a patch may be named by number (the placer numbers a resource's
  patches largest first, ties by amount then north-west first). Plain `@patch(iron-ore)` is as
  before. A sealed module instance with no `@(x, y)` is placed by territory (below).

## Placement: territories (part T)

- **`fk layout FILE.fk` places sealed modules as territories.** A scope whose sealed modules have
  no `@(x, y)` hint is handed to `fkcore.territory`: each module is a seed with an area need (its
  declared frame is the claim, `TParams.room`, 150 %, of it the need), its territory its cell in
  a capacity-constrained power diagram (`fkroute.voronoi`: additively weighted Voronoi on a
  coarse grid, weights adapted until every cell holds its need, clipped by the plot and the
  obstacles, pruned to the piece holding its seed; fixed instances are seeds that do not move),
  and the routability Lagrangian of 4.0 moves the seeds (`fkroute.place_seeds`: offers of +-s and
  +-2s on each axis, rotations on the coarse steps, a plateau rule per step, the walk's fields
  windowed). A net's cost is the walk between its two frames' port tiles, free inside the net's
  own two cells and priced `trespass` in a third's. Net weights come from the declared port
  rates and the machines behind each port (`territory.net_weights`), not the rate model.
- **Pins on ore.** A module carrying `@patch(RES)` is pinned: its seed the patch's centroid, its
  cell the patch grown to its need, and **ore is a wall for every other seed**; water and cliffs
  from the terrain file are obstacles.
- **`fk layout nauvis.fk [--write] [--all]`** on a surface file: its plot is the box, its terrain
  (`terrain NAME`: `NAME.terrain.json` beside the design, what `read_terrain` reads; nothing is
  read from the world) the ground, its `@` instances fixed unless `--all`. The report prints one
  line per module (`name = Kind @(x, y, rot r)`), the estimated belts before and after, the hot
  tiles, the ports no partner reaches, each cell against its need and which inter-module nets
  have their cells touching; `--write` puts the hints in the file; `out\territories.json` holds
  each cell as row runs (`pinned` and `terrain` noted). `FK_TRACE_SEEDS=1` prints one line per
  sweep; `FK_NATIVE=check` runs Python and Rust and raises on a difference.
- Measured: the megabelt's open flower (six rivers and the core unplaced, 900x1024) tessellates
  in 35 s; its paper build routes 49 nets short against the corridor layout's 48 with the
  inter-module belt within 9 % of it (wave 1 was 68 % over); on the lab's ground with 28 stand-in
  mines pinned, 45 (notes-43-territory). `agent/docs/examples/territory.fk`.

## Frames and hulls (part H)

- **A frame is a tile set** (`fkcore/frame.py`: `Frame`, run-length by row; from a box, a
  polygon, a run list or a tile set; `turn`, `grow`, `boundary(side)`, `nearest_boundary`,
  `overlap`, `clip`) wherever the toolkit reads one: ports on any frame (`@n12` is the frame's
  outermost tile in column 12; a column off the frame is `port-off-frame`), the router's
  keep-out, `crosses-frame`, `frame_overlaps` (the shared tiles counted), `fk look`'s outline,
  `fk explain`'s rows of `#` and `.`, `does-not-fit` by tiles.
- **The achieved hull** (`fkcore/hull.py`): after a sealed unit's build alone, its hull (entities,
  carriers, the 1-tile closure, `gap`, clipped to the frame it was routed in) is recorded in
  `out\frames.json`, stamped with a fingerprint of the module's inside so a changed inside drops
  it. The readers resolve a module's frame **hull, then claim** (its declaration when it has one,
  else its territory: a cell is the claim plus room, the ground its belts may cross). In the
  router the unit's own frame (its key, store coordinates, search box) is its claim, and the hull
  is what every other net keeps out of: a parent routes through what a module left free.
- Measured: hulls 25 to 67 % of the declared frames; `agent/docs/examples/shape.fk` (a hexagon-ish
  polygon, a second module in its notch, a parent's net through the free ground), EXAMPLES
  chapter 6.

## Mines (part M)

- **A drill's mining area stays off a second resource.** `placer.place_on_patch` keeps every
  drill's body on the row's resource and its mining area off any other; where no spot is clean
  the row goes where the fewest drills reach the other ore and those drills are left out (the
  check `mixed-patch` names them). The game's drills have no resource filter: measured on a
  2.1.24 laptop server, `filter_count` 0 on every drill, so the filtered-row path stays off by
  fact. A machine left out at place is no end of its net (`left out at place`, apart from `not
  in the layout`), so the standing drills route.
- **`MinerRow<n=auto> @patch(RES)`** sizes the row from the patch: the most drills that stand
  that way along its long axis (`n=auto lo..hi` bounds it). `placer.patches`, `patch`,
  `nearest_patch` read the design's terrain for the territory placer's pins.
- EXAMPLES chapter 3 "On the ore": `patch.terrain.json`, `ore-patch.fk`, `mixed-patch.fk`.

## Prices from the router (part R)

- **The pair stem**: a `lanes A | B` consumer terminal demands a straight run of `lanephys.STEM`
  free tiles before the side-load, in the layout's `usable` (Python and Rust). Grove: 68 of 76
  nets to 76 of 76 at 236 carriers against the hand layout's 256.
- **`fk layout --from [OUT]`**: each routed net's real carrier count replaces its relaxed
  estimate, and the negotiation's history (`FK_NEGOTIATE=1`, `out\design\<factory>\pressure.json`)
  seeds the price field; the report shows real -> estimated. The loop is by hand: layout, build,
  layout `--from`, build (the layout chapter shows two rounds on the mall).

## The hierarchy contract (parts D and D5)

- **The warning**, in START.md, BUILDING.md "Hierarchy", TOOLKIT.md "How route works" and "Sealed
  modules compile once", and EXAMPLES chapter 11: the router is given one sealed module at a time
  and the trunks between modules, never a base; a net that fails, a route step that takes minutes,
  a unit that reroutes when something else changed is a design issue, and the fix is in the
  hierarchy. BUILDING "Hierarchy" takes the designers' lab rules (one belt per column, a paired
  port straight into its column, a sealed cell powers its own frame, fluids on the short sides).
- **The hierarchy measured** (`44-levels`): `fk check` says `flat module X: N nets route at one
  level (the limit is 60)`; the route step prints a `level` line per level that searched and a
  level past 60 nets or `route.LEVEL_SECONDS` (60 s) is the check `flat`; `ports-touch` for two
  fluid ports of different fluids on adjacent tiles.
- **Why a unit rerouted, on the report** (`42-reroute`): a store miss names the key parts that
  differ from the module's last entry (`not in the store; Gears's last entry differs in
  instances, net g/sources`), `out\design\<factory>\units.json` makes a build-to-build key diff
  a file diff (`tools\unit_keys.py`); a no-op reads `0 routed, N kept, M pass-through`
  (pass-through nets counted apart); a lane pin's stub is not an idle carrier; abutting fluid
  ports are pass-throughs and the fluid judge sees only its ground.
- **The reroute leftovers** (`43-hierarchy`): fluid direct joins and zero-carrier nets are
  pass-throughs, one index for the fluid port joints, a pair's tail trimmed at lay time; fen's
  no-op route step 18.9 s -> 4.2 s and `0 routed`. Check lines `no-pole-spot` (an entity in a
  sealed cell that no free tile inside its frame can power from; the 3.1.3 cover crash) and
  `port-not-in-line` (a pair port whose stem something of the module stands in). Chapter 11's
  two-round story: a module changed inside reroutes only itself.
- **Pairs on one belt** (`45-pairports`): a pair already on one belt with no machine on the way
  routes as one plain net (every tap of the flower failed on the stack cell's straight rule).

## Not in this release

- The flower on the lab ground beside the corridor flower (T6's paste), `fk look` drawing the
  cells, a docs example on `patch.terrain.json` for the pins, a check line for a pinned frame on
  water; the territory sweep's 35 s against the plan's 14 s.
- R4 (the real router as the last sweep's evaluator, the lane search's prices as lambda) waits
  with `claude/40-lanes2` (N3, N4) at Rory's word.
- The drill filter: no drill of the game has one; the codec's field shape is a guess for a modded
  drill. `tools/read_facts.py` fails on 2.1.24 after the entities (facts.json stays 2.0.77).
- Open on the report: a unit's `catalog` key part differs between two builds after an inner
  instance moved; `design.read_all` is 1.5 s of fen's 4.2; `unit_parts`' `standing` part filters
  by the claim's box, so a parent belt through a polygon's notch re-keys the unit once.
- Nothing is migrated: old runs, saves and the 2.1.30 players are reference.

## Upgrading

- A run pins this release's commit as any other (`kickoff/upgrade_run.py RUN --sha SHA`), and
  `fkcore.__version__` says `3.2.0`. No ROUTER bump: stored routes are read as they stand; a unit
  holding a direct-join fluid net keys anew once.
- New files beside a design: `out\territories.json` (written by `fk layout`) and
  `out\frames.json` (written by the route step for sealed units built alone). Nothing reads the
  world on the way.
- The merge set (`CLAUDE.md`) gains `test_frame`, `test_hull`, `test_territory`, `test_layout`,
  `test_placer_mixed`, `test_connect`, `test_pair_ports`.
- The Rust kernel (`fkroute` 0.4.0, `native/fkroute`) gains `voronoi` and `place_seeds`; a tree
  without the kernel runs the Python reference (slow on a world, exact).
