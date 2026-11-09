# 41-mines: covering a patch, off the wrong resource (PLAN-ORGANIC M, wave 1: M1 and M2)

Branch `claude/41-mines`, cut from main `cfb10f0` (3.1.4). Part M of
`..\assessment-20261108\PLAN-ORGANIC.md`: a pinned mining row is placed and sized to cover its
patch, and no drill takes a second resource. Wave 1 is M1 (the resource rule) and M2 (`n=auto`
from the patch); M3 (patches from the design) and M4 (the smelting example) are wave 2.

## What landed

**M1, the resource rule** (`fkcore/placer.py`, `fkcore/expand.py`, `fkcore/flow.py`).
`placer.place_on_patch(frag, cat, ore, blocked, taken, box, other)` has a second hard rule next
to "every drill's body on the row's resource": a drill's **mining area** (`mining_area`, 5x5 for
an electric drill from `MINING_RADIUS`) holds no tile of another resource. `other` is
`placer.others(drill, resource, ground.ore)`: {tile: resource} of every other resource the drill
would mine, by `resource_categories` in facts.json against the resource's category (crude oil
under an electric drill is not "another resource": the drill cannot mine it; a resource the facts
don't know counts). `_judge` records per drill which other resource its area reaches
(`Spot.mixed`, `Spot.clean`), and the spot key is `(-len(mixed), reach, reach_amount,
under_amount, -y, -x, -rot)`: a clean spot beats every mixed one, then the fewest drills touching,
then the old key. `largest_fit` carries `other` through.

`expand._on_patch` acts on a mixed spot: the touching drills get the `resource_filter` attr (the
row's resource) when `placer.filter_slots(drill)` says the drill has filter slots, else they are
**left out** of the layout (`_put(..., skip=)`; `n` stays as written, the row's belt and route end
stay). Either way a `("mixed-patch", path, msg)` check comes back through `expand_factory`'s new
`checks` list, and `flow.s_place` prints it as a `mixed-patch` check line: the row, the drills,
the spot, and what was done:

```
mixed-patch t ore: 4 of 8 drills' mining areas reach copper-ore (m4, m5, m6, m7) at 1,10 rot 0, the spot where the fewest do; electric-mining-drill has no resource filter slots in facts.json, so they are left out: 4 of 8 drills placed
```

The place line ends `; 4 left out (mixed-patch)` or `; 4 filtered to iron-ore (mixed-patch)`.

**M2, covering a patch** (`placer.cover`, `expand.patch_cover`, `size.patch_counts`, `flow.s_size`).
`MinerRow<n=auto> @patch(RES)` takes its count from the patch: `placer.cover(make, lo, hi, ...)`
is the most drills `lo..hi` whose row has a **clean** spot (bodies on the resource, areas off every
other one, nothing on blocked or taken ground; every rotation tried, so the row lies along the
patch's long axis). `hi` is first cut to rows whose frame fits the ore's bounding box either way
round, then bisection: a shorter row of the same kind stands wherever a longer one does, so
fitting is monotone in `k`. `flow.s_size` gives `size.size(..., grounds=)` the terrain as each
plot sees it (the same `frame_ground` read `place` makes); `size.patch_counts` pins every `n=auto`
`@patch` MinerRow to its count (its bounds become `k..k` for the rates' search; the report shows
the written bounds) and `out\size.txt` says what the patch gave:

```
sized: ore n=14 (auto 4..30)
  1 n=auto row, 14 machines; every target and assert holds, and every net of an n=auto row carries what its consumers ask; 2 model solves, 0 growth steps after the seed

  row                  kind           n seed   bounds  serves
  ore                  MinerRow      14   14    4..30  its patch: what the ore holds (below)
                       @patch(iron-ore): the iron-ore in the plot spans 30x7, long axis E-W; 14 drills stand on it with their mining areas off other resources, the row E-W at 7,10 rot 0, 161 ore tiles in reach (80.5k)

  on their ore by place (@patch): ore n=14 (what the patch holds); place says when that many drills don't fit
```

and `place.txt` then reads `placed ore: @patch(iron-ore) at 7,10 rot 0, the row runs E-W (the
iron-ore in the plot spans 30x7, long axis E-W): 14/14 drills on iron-ore, 126 ore tiles under
them (63.0k), 161 in their mining areas (80.5k)` (the test fixture: a 30x7 iron strip with a
copper streak under its west end, `n=auto 4..30`).

When the patch gives no count (no terrain read yet, no ore in the plot, not even `lo` fits clean)
the line says why and `n sized by rates` as before. `taken` for the size step is the other
instances' planned frames (`expand.planned_frame`), since nothing is laid out yet.

**Docs:** the `@patch` and `n=auto` rows in `agent/docs/LANGUAGE.md`; `mixed-patch` in
`agent/docs/TOOLKIT.md`'s check list. `.fkp`: `resource_filter` is a typed attr
(`codec.CIRCUIT_ATTRS`), kept through `fkp.dumps`/`loads`.

## Tests

- `tests/test_placer_mixed.py`: 12 tests, green. A synthetic 30x7 iron strip (a 20-drill row
  covers it exactly) with: a copper streak at the west end (the row of 8 is placed east of it,
  clean; `n=auto 4..30` gives 14); copper along the whole south edge (no clean spot for 8: the
  south four are left out, the check line printed, or filtered when `filter_slots` is mocked to
  1, with the codec's field and the `.fkp` round trip checked); copper on both long edges (no
  clean spot for 3 or more drills; `n=auto` falls back to rates and says why); the fewest-touch
  key (copper south plus north-west: the row goes east); `others` skipping crude oil; `cover` on
  a patch of known size (20 along the long axis, the written top `4..12` holds, a tall patch turns
  the row); and two `flow.run` builds from a saved terrain file reading `out\size.txt`,
  `out\place.txt` and the checks file.
- Existing modules, all green against the branch: `test_placer`, `test_smelter_array`,
  `test_route_ground`, `test_terrain`, `test_terrain_flow`, `test_design`: 56 tests in 38 s.
  Codec-adjacent (`CIRCUIT_ATTRS` gained a name): `test_fkp`, `test_own`, `test_circuits`,
  `test_literal_ports`, run with `test_placer`, `test_smelter_array` and `test_placer_mixed`
  after the last commit: 131 tests in 4.8 s, green. Never the whole suite.

A fixture lesson worth keeping: the WIP's "no clean spot" cases used copper along the south edge
only, and failed because a 4-drill row **turned N-S** (7x6) stands on a 7-tall strip clear of
that edge, and a 2-drill row (7x3) sits in the middle row clear of both edges. The placer was
right; the fixtures now put copper on both edges and the floor is 3 drills.

## The drill-filter finding

The plan says "the 2.0 mining drill has a resource filter; to be confirmed on the lab server in
M1's first day, and if it has none the drill is left out and reported". No game server was
touched. What the toolkit's local game data says:

- `fkcore/data/facts.json` (version 2.0.77, read over RCON on a laptop server by
  `tools/read_facts.py`, base + Space Age): the four `mining-drill` rows (`burner-mining-drill`,
  `electric-mining-drill`, `big-mining-drill`, `pumpjack`) carry `mining_drill_radius`,
  `resource_categories`, `module_slots`, `drop_vector` and **no `filter_count`**. That is not
  evidence the prototype lacks it: the reader's Lua recorded `filter_count` for inserters only
  (`tools/dump_catalog.lua:125`, `tools/measure_lanes.py:177`; `read_facts.py` likewise before
  this branch). `fkcore/data/catalog.json` (2.0.77) has `filter_count` on the six inserters and
  nothing on drills, for the same reason.
- No blueprint fixture in the repo (`tests/golden/*/world.fkp`, `tests/data/**`) holds a mining
  drill with a filter field, so the blueprint field's name and shape could not be confirmed
  either.

So the filter is behind **one entity attr, `resource_filter`, off by default**: `expand._on_patch`
writes it only when `placer.filter_slots(drill)` is non-zero, and that reads the drill's
`filter_count` from facts.json, which no drill has today. Until the facts are re-read every mixed
row is handled the "no filter" way (drills left out, reported). `tools/read_facts.py` and
`fkcore/learn.py` now record `filter_count` for `mining-drill` prototypes (`p.filter_count`,
`MiningDrillPrototype::filter_count`), so a re-read flips the behaviour by itself where the game
has slots.

**What the integrating session must confirm on a laptop test server** (`tools/laptop_server.py`;
never the live game):

1. Re-run `python tools/read_facts.py` against it and look at the `electric-mining-drill` row of
   the new facts.json: a `filter_count` > 0 means the 2.0.77 drill has resource filter slots and
   M1 filters the touching drills instead of leaving them out, with no code change.
2. In the game, place an electric drill, set a resource filter in its GUI (if the GUI offers
   one), blueprint it, and export the string (`/c game.print(game.player.cursor_stack.export_stack())`).
   Decode it with `fkcore.codec.parse_blueprint` and read the entity's extra fields. Then fix the
   `resource_filter` branch of `codec.control_behavior` to that shape (today it writes a
   top-level `filter` of `{"filters": [{"index", "name"}], "mode": "whitelist"}`, a guess, marked
   UNCONFIRMED in the code), add the field's name to `codec._CIRCUIT_FIELDS` so a read-back
   blueprint drops it when it matches, and update the one assertion in
   `test_placer_mixed.test_a_drill_with_filter_slots_is_filtered_to_the_rows_resource` that spells
   the shape.
3. Paste a filtered row and watch a mixed tile: the filtered drill must put only the row's
   resource on the belt.

## Decisions taken here (within the plan)

- The rule is checked over the drill's **mining area**, not a tile margin: `placer.mining_area`
  is the game's `mining_drill_radius` from facts, so a big drill (6.49) or a burner drill (0.99)
  gets its own area.
- "Another resource" is one the drill can mine (its `resource_categories`): crude oil under a
  row of electric drills does not count. An unknown resource counts.
- A left-out drill does not change `n`: the row stays as written, the layout has fewer drills,
  the check line says how many. (The plan: "the drill is left out and reported".) The rates model
  still counts `n` drills; `place.txt`'s `4 of 8 drills placed` is the correction for the reader.
- `cover` sizes against the other instances' **planned** frames, since `size` runs before
  `place`; a row that then collides at `place` gets place's own report, as today.
- No new syntax: `n=auto`, `n=auto lo..hi` and `@patch(RES)` as they were.

## Open

- The blueprint field for a drill's resource filter (above): shape unconfirmed, off by default.
- M3 (wave 2): `fk layout` reads the same terrain file; nothing here reads the world.
- M4 (wave 2): the smelting chapter (`agent/docs/EXAMPLES.md` chapter 3) gains a mixed patch. It
  will need a terrain file for `docs\examples` with iron and a copper streak and a build script
  (`read_terrain`, `elaborate`, `size`, `place`), and will quote: the `placed ore: @patch(iron-ore)
  at X,Y rot R, the row runs E-W (...): 8/8 drills on iron-ore ...` line; the `mixed-patch`
  check line in the form above with its drill names and `4 of 8 drills placed`; and
  `size.txt`'s `sized: ore n=14 (auto 4..30)` with the `@patch(iron-ore): the iron-ore in the
  plot spans 30x7 ... 14 drills stand on it with their mining areas off other resources` line.
  The fixtures in `tests/test_placer_mixed.py` (IRON, COPPER_WEST, COPPER_SOUTH) are a ready
  shape for that terrain.
- `tools/dump_catalog.lua` (the catalog fixture's reader) still records `filter_count` for
  inserters only; the drill read went into `read_facts.py`/`learn.py`, where `filter_slots` reads
  it. Leave the catalog alone unless the catalog grows a need.
- With drills left out, `report_checks`'s `sinks` line counts the rates model's makers (`4 of 8
  makers on a net reach a sink`) while `no-route` names them `not in the layout: ore/m4 ...`;
  the sinks line could say the same. Cosmetic, not touched here.
- A row of a drill that mines two categories on a patch where both resources are the row's
  intent (Vulcanus calcite + tungsten) has no way to say "both are mine": `@patch(RES)` names one
  resource. Not in wave 1.
