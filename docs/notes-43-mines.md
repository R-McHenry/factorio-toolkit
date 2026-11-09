# 43-mines: patches from the design, the drill filter, the smelting example (PLAN-ORGANIC M3, M4)

Branch `claude/43-mines`, cut from main 90e20a0 (3.1.4 + wave 1). Wave 2 of part M: M3 (patches
from the design), M4 (the smelting chapter's mixed patch), and wave 1's leftover (the drill filter
confirmed on a laptop server), plus `size.py`'s `does-not-fit` on a polygon (the hull agent's open
item in this part's file). Written 2026-11-09, 05:50 to 06:40.

## For the territory agent: the patch reader (M3)

One plain function in `fkcore/placer.py`, pure, stdlib, nothing read from the world:

```python
from fkcore import placer

placer.patches(terrain, resource=None)   # -> [OrePatch], largest first per resource, n from 1
placer.patch(terrain, "iron-ore#2")      # -> OrePatch or None ("iron-ore" is #1)
placer.nearest_patch(terrain, "iron-ore", (x, y), need=0)   # nearest centroid with >= need tiles
```

`terrain` is any of: a `terrain.Terrain` (what `terrain.load(path)` gives), the path of the
`.terrain.json` the design names (`read-terrain`, `<name>.terrain.json`), that file's dict, a
`terrain.FrameGround` (then the tiles are in that plot's frame) or a `{resource: {tile: amount}}`
mapping. `OrePatch` is frozen: `resource`, `n` (the `#k`, 1 the largest: the same numbering
`terrain.patches` and the surface file's `place ... patch iron-ore#2` use), `tiles` (frozenset of
(x, y)), `amount`, `box` (x0, y0, x1, y1, half-open), `centroid` (the mean of the tile centres,
floats), `name` (`iron-ore#2`), `size`, `len()`. Committed in the first hour (4624de4).

M3 as the plan states it (`fk layout` and `fk build` read the same terrain file, nothing reads the
world on the way) already held: `flow.s_size` and `flow.s_place` both take `ctx.ground`, the one
`read_terrain` step's file, through `terrain.frame_ground`; `fk layout` has no world read. The
patch reader is the piece the pins needed.

## The drill filter (M1 leftover): confirmed, there is none

Measured 2026-11-09 05:55 on a laptop server (`tools/laptop_server.py`, scenario fk-play; the
laptop's Factorio is **2.1.24** now, base + space-age + quality + elevated-rails + recycler; the
live game was not touched; the probe scripts were scratch files, not committed):

| what | answer |
|---|---|
| `prototypes.entity[d].filter_count` for the four drills | `0` (a number, not nil) for electric-mining-drill, burner-mining-drill, big-mining-drill, pumpjack |
| `LuaEntity.filter_slot_count` on a placed electric drill | 0 |
| `set_filter(1, 'iron-ore')`, `set_filter(1, prototypes.entity['iron-ore'])` | "Callable only on entities that have filters." (a table gives "Invalid EntityID: expected LuaEntityPrototype, LuaEntity or string", so a drill filter would be a resource entity, not an item) |
| `mining_drill_filter_mode` | nil (settable, no effect) |
| a blueprint of the drill (`create_blueprint`, `export_stack`) | `{"entity_number", "name", "position"}` and nothing else |
| `import_stack` of a drill carrying `filter {filters, mode}` (the codec's guess), `filters [..]`, `use_filters + filters`, `filter_mode`, `mining_drill_filter_mode` | every one dropped: the entity comes back with name and position only |
| the facts read's entity row (`tools/read_facts.py`'s `_ENTITIES` Lua, 146 placeable entities) | `electric-mining-drill {'type': 'mining-drill', 'filter_count': 0, 'mining_drill_radius': 2.49, 'mining_speed': 0.5, 'resource_categories': ['basic-solid'], 'module_slots': 3}` |
| two drills over iron with copper under the south row of their area, 9600 ticks at speed 10 | both belts `iron-ore x3` (the mining target was iron; not a filter test, the drills have none) |

So in 2.1.24 no drill has resource filter slots, and M1's fallback is the rule: on a mixed patch
the touching drills are **left out** and the `mixed-patch` line says so. The filtered path stays
behind `placer.filter_slots` (a drill's `filter_count` in facts.json): a modded drill with slots
would take it, with the codec's field shape still a guess (no game writes one, so none can be
read back). The facts line itself: `facts.json` keeps `filter_count` only when it is non-zero
(`read_facts.build_facts`), so the 2.0.77 row's missing key and the 2.1.24 read's `0` mean the
same thing. The blueprint field writer for a drill is `codec.control_behavior` (the
`resource_filter` branch writes `fields["filter"]`, called from `codec._entity_json` for every
entity row); its comment now records the measurement, the shape stays marked UNCONFIRMED, and
nothing was added to `codec._CIRCUIT_FIELDS`. `test_placer_mixed` asserts `filter_slots` is 0 for
all four drills and keeps the mocked-slot test with the guess spelled out as a guess.

`python tools/read_facts.py --dry` on the 2.1.24 server reads the entities and then fails in
`_THINGS`: `LuaRecipePrototype doesn't contain key category` (2.1 moved it); the facts.json re-read
is blocked by that reader line, which is not this part's. facts.json stays 2.0.77.

## M4: the smelting chapter's mixed patch

`agent/docs/EXAMPLES.md` chapter 3 gains "On the ore: ore-patch.fk and mixed-patch.fk", with four
new files in `agent/docs/examples/`:

- `patch.terrain.json`: the fixture, surface nauvis, area 0,0..60,80, two 30x7 iron strips (500
  ore a tile: `iron-ore#1` at 0,10..29,16 and `#2` at 0,50..29,56, 105.0k each), a copper streak
  under the west end of the first (`copper-ore#2`, 0..5 at y 17) and copper under the whole south
  edge of the second (`copper-ore#1`, 0..29 at y 57). The shape is `tests/test_placer_mixed.py`'s
  IRON, COPPER_WEST and COPPER_SOUTH, the second strip moved down 40.
- `ore-patch.fk`: `MinerRow<n=auto 4..30, resource=iron-ore> @patch(iron-ore)` into a provider
  chest, plot 60x40 at 0,0.
- `mixed-patch.fk`: the same row written `n=8`, plot 60x40 at 0,40.
- `patch.build.fkb`: `read_surface nauvis`, `read_terrain patch`, `elaborate`, `size`, `place`.

Their real output (the chapter quotes these lines, `tests/test_examples_docs.py` checks them):

| | |
|---|---|
| `size.txt` | `sized: ore n=14 (auto 4..30)`; `@patch(iron-ore): the iron-ore in the plot spans 30x7, long axis E-W; 14 drills stand on it with their mining areas off other resources, the row E-W at 7,10 rot 0, 161 ore tiles in reach (80.5k)` |
| `place.txt`, ore-patch | `placed ore: @patch(iron-ore) at 7,10 rot 0, the row runs E-W (...): 14/14 drills on iron-ore, 126 ore tiles under them (63.0k), 161 in their mining areas (80.5k)` |
| `place.txt`, mixed-patch | `placed ore: @patch(iron-ore) at 1,10 rot 0, the row runs E-W (...): 8/8 drills on iron-ore, 72 ore tiles under them (36.0k), 98 in their mining areas (49.0k); 4 left out (mixed-patch)` |
| the check line | `mixed-patch mixed-patch ore: 4 of 8 drills' mining areas reach copper-ore (m4, m5, m6, m7) at 1,10 rot 0, the spot where the fewest do; electric-mining-drill has no resource filter slots in facts.json, so they are left out: 4 of 8 drills placed` |

**Found by building the example through the whole paper script** (route and report_checks, not
in the fixture's script): with four drills left out, the net does not route. `route`: `no-route
mixed-patch net ore_: its route does not connect 4 driver->consumer pairs`; `report_checks`:
`no-route mixed-patch net ore_: 0 of 8 driver->consumer pairs connected; 1 segment, 11 carriers;
not in the layout: ore/m4, ore/m5, ore/m6, ore/m7`, the summary `1 nets: 0 connected, 0 open, 1
unrouted`, and the `sinks` line reads `4 of 8 makers on a net reach a sink with what they make;
none reached: ore/m0 (net ore_), ore/m1 ..., ore/m2 ..., ore/m3 ...` (the count and the list
disagree: the four standing drills are the cut-off ones, the four left out are counted as
reaching). The left-out drills are still the Flat's drivers of the net, so the router searches
for them and the whole net fails; the four drills that stand get no route to the chest. The same
strip with `n=auto 4..30` gives `sized: ore n=4 (auto 4..30)`, the row turned N-S at 1,10 rot 1
(`4/4 drills on iron-ore`), and `1 nets: 1 connected, 0 open, 0 unrouted`. The chapter says this
under "What goes wrong here" and the fix it names is the row written for the patch (`n=auto`).
The defect itself is in `expand.expand_factory` / the route step (both no-go files here): see
Open.

`tests/test_examples_docs.py`: `TERRAIN = {"ore-patch": "0,0 60x40", "mixed-patch": "0,40
60x40"}`; `paper_build` gives those two the fixture's script and `terrain patch`, the summary-line
test skips them, and `test_the_patch_examples_build_on_their_terrain` asserts the quoted size,
place and check lines are the build's (and `14/14`, `4 of 8 drills placed`, `; 4 left out
(mixed-patch)`). The LANGUAGE.md `@patch` row and TOOLKIT.md's `mixed-patch` entry say the game's
drills have no filter (2.1.24) and that the ore comes from the terrain file the surface names.

## `does-not-fit` judges a polygon by its tiles

`size.fit` (my file; the hull agent's open item) collects frames as `Frame`s: a row's from
`expand.planned_shape` (its box), a sealed module's declared `shape` or `size` from
`expand.own_frame(inst)` turned about its origin and moved to its `@(x, y, rot)` hint
(`size._module_shape`; before, `planned_frame` gave None for every module, so a sized row running
into a declared module frame was never reported). The overlap is `Frame.overlap`: a box of
shared tiles reads `on 2x7 tiles` as before, a polygon's `on 34 tiles in 12x7`, and the other
frame is named `20x16` or `240 tiles of 20x16`. The past-the-plot check is unchanged (a row is a
box). `tests/test_size.py` `test_a_polygon_module_is_judged_by_its_tiles`: a 40x7 smelter row in
an L's notch fits (its box overlaps the L's box on 8x7); moved two columns west it shares a 2x7
box; moved up as well, 34 tiles in 12x7.

Writing that test found a crash in `size._consumers_first` (the seed's consumer order): a sealed
module instance on a net (`net feed: src -> ell.fe_in`) raised `KeyError: 'ell'`, because a
module's port machine belongs to the module instance, which is not a leaf. The order now takes
leaves only (a module's demand reaches the rows through the rate model's grow step as before).

## Tests

| run | result |
|---|---|
| `tests.test_placer_mixed` (12 -> 14: `PatchesTest`) | 14 OK, 0.8 s |
| `tests.test_placer_mixed tests.test_size` | 46 OK, 13.2 s (before the polygon test) |
| `tests.test_size tests.test_stack_auto tests.test_placer_mixed tests.test_choices tests.test_dnp` (after the polygon test and the seed fix) | 73 run, 13.6 s, 72 OK; the one failure, `test_dnp.DnpBuildTest.test_a_scaling_row_grows_where_it_stands` (`'kept ('` not in route.txt: the summary reads `12 kept, 6 pass-through (12 pinned ...)` since 42-reroute), fails the same way on main 90e20a0 (run there read-only, 0.4 s): not this branch's |
| `tests.test_examples_docs` (5 -> 6: the patch examples) | 6 OK, 28.5 s |
| `tests.test_design tests.test_placer tests.test_terrain tests.test_terrain_flow tests.test_smelter_array` | 54 OK, 31.3 s |

Never the whole suite. No Rust touched; `fkroute.pyd` is main's copy, unchanged.

## Decided here

- `placer.patches` takes the terrain in any of its forms rather than a `Terrain` only, so the
  territory agent can hand it the path the design names, the loaded terrain, or a plot's ground.
  The centroid is the plain mean of the tile centres (not ore-weighted): a seed in half-tiles is
  what part T's sweep wants, and the ore amount is on the record for whoever weighs it.
- The drill filter: measured absent, so nothing was "turned on"; the path's switch stays the
  facts row (`filter_count`), the codec's shape stays a marked guess, and the docs say drills
  are left out. The 2.0.77 facts.json was not replaced by a 2.1.24 read (the reader fails on
  2.1, and a wholesale facts change is the integrating session's call, not this part's).
- The mixed-patch example is built through `place` by its own five-step script, because that is
  where its lines are and because the net cannot route with left-out drivers (above). The chapter
  states the failure and the fix (`n=auto`) instead of hiding the step.
- `size.fit` now includes declared module frames (boxes too), not only polygons: a row grown into
  a sealed module's box is as much `does-not-fit` as one grown into another row.

## Open

- **Left-out drills break their net's route** (M1's fallback as it stands): `expand._on_patch`
  drops the drills from the layout (`_put(skip=)`) but they stay the Flat's drivers, so `route`
  fails the whole net and `report_checks` names them `not in the layout`. The fix belongs where
  the drills are dropped: take them out of the net's drivers (and the rates model's makers) when
  `more["skip"]` is set, or hand the route step a left-out set. Both files are no-go for this
  part. Until then a mixed row is best written `n=auto` (the chapter's answer). The `sinks` line's
  count disagrees with its list in that case (`flow._sinks`, cosmetic, wave-1 open item).
- `tools/read_facts.py` does not run against Factorio 2.1.24 (`LuaRecipePrototype.category`);
  facts.json stays 2.0.77 until that is fixed.
- The codec's `resource_filter` field shape is unconfirmable in base + Space Age (no drill has
  slots); a modded drill with `filter_count > 0` would exercise it first.
- `placer.cover` sizes against `expand.planned_frame`, which is None for modules: a row counted
  by its patch is not kept off a declared module frame at `size` time (place's `_taken` catches
  the collision). Same shape as the `fit` gap fixed here; left, since `patch_cover` is in
  `expand.py`.

## Files touched outside this part

- `fkcore/codec.py`: the comment on the `resource_filter` branch (no code change).
- `tests/test_examples_docs.py`: `TERRAIN`, `paper_build`'s script and surface for those two,
  the new test (the brief: "keeps the quotes as the other chapters do").
- `agent/docs/LANGUAGE.md` (`@patch` row) and `agent/docs/TOOLKIT.md` (`mixed-patch` entry):
  one clause each.
- `tests/test_size.py`: the polygon test (size.py is this part's; the test module covers it).
