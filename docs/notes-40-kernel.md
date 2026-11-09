# notes-40-kernel: PLAN-4.0 part K, wave 1 (K0 to K3)

Branch `claude/40-kernel`, cut from main 4afcb33 (3.1.3 + the native tools). Measured on this
laptop with `python tools/native_share.py` (calls and seconds per side while the module group
runs) and `FK_NATIVE=check` (both searches, raise on any difference). Every number below is from
the tree's own kernel (`python tools/native_build.py`, `<tree>/fkroute.pyd`).

## What landed

- **K0** (on main already): `tools/native_build.py`, `tools/native_share.py`. Here: `lib.rs`
  split into `grid.rs` (NativeGrid, walk, hubs), `search.rs` (astar), `grow.rs` (grow), plus
  `physics.rs` and `hub.rs`; `lib.rs` keeps the types and the `#[pymodule]` block, one line per
  item (the lanes and layout branches add `mod lane;` / `mod place;` and one line each).
- **K1** the physics as data: `lanephys.table()` enumerates `moves` for every via, direction
  pair and underground end and `drop_lane` / `turn_drop_lane` / `mine_lane` for every argument;
  `steiner` hands it to `fkroute.physics(...)` once at import; the kernel keeps it in a OnceLock
  and `physics_lookup` reads it back. `test_native.test_physics_table_is_lanephys` compares every
  lookup. Nothing in Rust states a lane rule (the kernel does not read the table yet: K4's drop
  lane is its first reader). `steiner` ignores a kernel older than 0.3 (the signatures changed),
  so an old installed `fkroute` means the Python search, not an error.
- **K2** 3.0's taps: `TapSink.pick` / `taps_at` step for step in `search.rs` (the tail
  `6 + 4(k-1)`, straight hands, then the force's vector pairs, then a long hand two out), the
  inserters as a `(name, reach, tap cost)` table in the call (`steiner._Inserters`: reach from
  `arms.REACH`, cost from `COSTS`), the arms as `(range, pairs)` per sink (`arms.pairs(arms,
  straight=False)` with each pair's heading), the heuristic from the range, k > 1 counted in the
  search key `(x, y, d, ex, taps)` exactly as Python's `key()` (a trace and a pick per neighbour
  near such a sink), the exit-can't-turn rule, `DropSink`. `astar` runs the tap goal natively
  for a plain `TapSink`; a subclass (m2m's `LeftTap`, `_EndTap`) is kind 2 and keeps its Python
  goal as the callback (and still falls back to Python when it wants k > 1 as a target, as
  before). `grow` takes all of them.
- **K3** reversed trees and the hub: `_grow_native` no longer refuses `drop_taps` (the kernel
  had `keep_clear`, the spare tiles and `tapped` since 0.2; what it lacked was 3.0's pick).
  `fkroute.hub_search`: `hubs` candidates, then per candidate the reversed tree (occ + the hub's
  front tile, `keep_clear` = the standing belts, `drop_taps`) and the forward tree (occ + the
  reversed tree's tiles + the tiles its reversed carriers point into less the front tile, its
  tunnels added to the spans), each side over `route._grow_attempts`' sink lists (first that
  routes, else the last), until `_HUB_WINS` candidates route; the cheapest wins. It returns the
  two trees (and the first failure's tree) and Python rebuilds `Tree`s and lays the plan, so the
  plan entities and the report string are Python's as before. `route._grow` is now a loop over
  `_grow_attempts` (the same lists, the same stop rule) so Python and the kernel try the same
  sequence. m2m's hub (`tap=LeftTap`) stays Python.

### A note on the plan's wording

PLAN-4.0 K2 says "an underground exit takes a drop, an entrance does not". Python's 3.0
`TapSink.pick` has no such rule: every tile of the tail may take a tap, underground ends
included (steiner's docstring: "a tap's inserter drops onto its belt, an underground exit
included, measured on 2.0.77"). The 0.2 kernel skipped the tile before a jump when `drop_taps`
(2.1's rule), which is why it refused reversed trees. Parity is the law: the kernel now mirrors
Python's pick with no tunnel rule. m2m's `LeftTap.pick` keeps its own tunnel skip and stays a
Python goal (K4).

## Numbers

`native_share` on the plan's three module groups (wall: the unittest run inside the tool).

| group | before (0.2.0) | after K2 | after K3 |
|---|---|---|---|
| test_route (25 tests) | wall 5.1 s; grow 272 native (0.57 s) / 110 Python (0.33 s); A* 413 native (0.23 s) / 0 Python; fallbacks drop_taps 110 | wall 2.5 s; grow 272 / 110 (0.14 s); A* 413 (0.08 s) / 0; drop_taps 110 | wall 2.2 s (4.0 s in a second run); grow 187 native (0.47 s) / 0 Python; A* 1 / 0; hub 26 native (0.11 s) / 0 Python; no fallback |
| pairs: test_lanes_pairs, test_lane_goal, test_port_pairs (40 tests) | wall 7.3 s; grow 481 (0.33 s) / 288 (1.48 s); A* 1089 (1.29 s) / 0; drop_taps 288 | wall 5.2 s; grow 481 (0.29 s) / 288 (0.52 s); A* 1089 (0.37 s) / 0; drop_taps 288 | wall 6.8 s (9.7 s); grow 748 (0.94 s) / 0; A* 3 / 0; hub 3 (0.01 s) / 0; no fallback |
| taps: test_route_taps, test_steiner_split_tap, test_route_promote (13 tests) | wall 4.6 s; grow 11 / 57 (3.46 s); A* 140 / 108 Python (3.44 s); drop_taps 12, drop_taps+k>1 21, k>1 24 | wall 1.2 s; grow 35 (0.05 s) / 33 (0.04 s); A* 82 (0.03 s) / 0 Python; drop_taps 12, drop_taps+k>1 21 | wall 1.3 s; grow 2 / 0; A* 0 / 0; hub 14 (0.15 s) / 0; no fallback |

After K3 the grows a hub runs happen inside `hub_search` and are not counted as grows, which is
why the grow counts drop (272 -> 187) while the A* count goes to 1-3 (the remaining A*s are
`route._new_branch`'s patches, native). The same groups with `FK_NATIVE=0` (the pure Python
search): test_route 17.0 s, pairs 30.6 s. Wall times move by 30 % between runs on this laptop
(route 2.2 s and 4.0 s, pairs 6.8 s and 9.7 s, the same code); the search seconds are the
steadier measure. The pairs group's search time did not fall from K2 to K3 (0.81 s over both
sides -> 0.94 s native): its cost is the 48-part enumeration around the search, as the plan
says, not the search itself.

The "before" row differs from the plan's table (measured on the same laptop the night before)
only in wall time: this run had the machine to itself.

`FK_NATIVE=check` after K2: test_native (13), test_route (25), test_route_taps (6),
test_steiner_split_tap (3), test_lanes_pairs (30), test_lane_goal (6): all green.

`FK_NATIVE=check` after K3 (both searches on every call, raise on any difference), all green:
test_native (16 tests, 29.6 s), test_route (25, 11.2 s), test_route_taps (6, 2.7 s),
test_steiner_split_tap (3), test_lanes_pairs (30, 3.3 s), test_lane_goal (6, 39.2 s),
test_route_promote (4, 0.5 s), test_port_pairs (4, 3.6 s), test_route_units (3), test_route_cycle
(1), test_route_ground (2), test_m2m (23, 36.9 s: its hub takes the Python path, its grows the
native A* with the LeftTap callback), test_bob_inserters (25, 2.7 s).

## The real workload (the integrating session, after the merge as 55655de)

The four megabelt modules built alone offline (`tools/buildbench.py` on a copy of each
`lab-session\fk-run2\lab\<module>` with `out/` and the .fkp removed, `--script lab.build.fkb`,
`--to report_checks`), the route step's time, 0.2.0 then 0.3.0:

| module | nets | route step 0.2.0 | route step 0.3.0 |
|---|---|---|---|
| grove (4 GreenB stacks, pairs) | 76 | 2.8 s (one pair net 1.0 s) | 1.2 s |
| spring | | 0.9 s | 0.7 s |
| plasticcol | | 0.3 s | 0.2 s |
| redcol | | 0.7 s | 0.4 s |

## Wave 2 (K4 and K5), branch `claude/40-kernel2`

Cut from main 55655de (fkroute 0.3.0); merged main again after `claude/40-layout` landed
(`place.rs`, `fk layout`). fkroute 0.4.0. Same laptop, same tools.

### What landed

- **K4** m2m's sinks as native kinds. `search.rs` knows `LeftTap` (kind 4) and `_EndTap` (kind
  5) beside the plain tap: a `TapSpec` carries its pick rule and its avoid tiles. `LeftTap`'s
  rule is `LeftTap.pick` step for step (a tail of 6, no tap off the tile before a tunnel when laid
  reversed, one fixed side); the side is *read from the physics table*: for a state heading d laid
  reversed the belt runs d + 2, and of its two sides the kernel takes the one whose inserter,
  dropping towards the belt, fills the lane the sink names by `drop_lane` (`to_sinks`, once per
  sink). Nothing in Rust says "the belt's right". `_EndTap`'s rule is its goal: the run's last
  belt points into none of the belts it is handed. Python hands them over by a small protocol on
  the sink class (`native_kind`, `native_extra()`), so `steiner` imports nothing of `m2m`;
  `m2m.LeftTap` now names its lane (`lane = "L"`) and derives its side from `lanephys.drop_lane`
  too (`_drop_side`), the same answer as the `(d + 3) % 4` it hard-coded. `route._hub_search`
  lost its `tap is TapSink` gate: m2m's hub (`tap=LeftTap`) runs in `hub_search`. maxflow, the
  played-rules pass and the augment orchestration stay Python, as planned; the augment loop's
  A* runs native with no callback.
- **K5** entities out. `grow` returns `(tree, entities, reversed, counts, problems, cost)`: the
  forward and the reversed view exactly as `Tree.entities` / `_entities_reversed` lay them
  (`grow.rs`: `entities`, `Tree::counts`, `Tree::problems` string for string; the tap entity via
  `_tap_ent`'s rules: it faces its pickup and keeps the vectors that are not its direction's
  default pair, which the kernel derives from the inserter's reach as `arms.default` does).
  `hub_search` returns the winner's two entity lists and counts, or the first failure's problem
  strings; no tree leaves it. `steiner.grow(net=)` returns a `_Grown` dict: a native result's
  `"tree"` and a Python result's `"entities"` / `"reversed"` are built on first access, so the
  router (`_tree_job`, `_hub_trees`, `_hub_search_native`, hourglass) reads the views and builds
  no `Tree` for a native result; the Python hub's `_forward_ground` still asks for one (its own
  step; the kernel's hub lays that ground itself). Check mode compares the tree and the log as
  before and the entity views, counts, problems and cost on top.
- `native_share` counts `astar_callback` (native A*s with a Python goal among their targets) and
  names fallbacks by `_sink_spec`; m2m's searches were always counted (same entry points).
- Tests: `test_m2m_left_taps` (LeftTap parity on 150 random reversed fields with Python's pick
  forbidden; every tap on the left lane by `lanephys.drop_lane`), `test_m2m_end_taps` (_EndTap
  parity in the augment loop's A*, Python's goal forbidden), `test_m2m_hub_runs_native`,
  `test_entities_out` (every field kind, `_tree_from_native` forbidden, key order included); the
  native hub test forbids a Tree too.

### Numbers

`native_share` (calls / seconds per side; wall is the unittest run inside the tool):

| group | before (0.3.0) | after K4 | after K5 |
|---|---|---|---|
| test_route (25) | wall 4.3 s; grow 187 native (0.74 s) / 0; A* 1 / 0; hub 26 native (0.20 s) / 0 | wall 2.9 s; grow 187 (0.58 s); hub 26 (0.15 s); callbacks 0 | wall 4.1 s; grow 187 (0.77 s); hub 26 (0.22 s) |
| pairs (40) | wall 8.7 s; grow 748 (1.08 s) / 0; A* 3; hub 3 (0.01 s) | wall 13.8 s; grow 748 (1.77 s) | wall 11.0 s; grow 748 (1.13 s) |
| taps (13) | wall 1.4 s; grow 2; hub 14 (0.19 s) | wall 1.7 s; hub 14 (0.23 s) | wall 1.4 s; hub 14 (0.17 s) |
| test_m2m (23) | wall 23.5 s; grow 124 native (0.10 s) / **60 Python (0.51 s, all LeftTap)**; A* **872 native (0.46 s), with the LeftTap/_EndTap callbacks** / 0; hub 4 native (0.02 s) / **12 Python (0.50 s)** | wall 38.3 s; grow 89 native (0.15 s) / 0; A* 180 native (0.21 s) / 0, **0 callbacks**; hub 16 native (0.39 s) / 0 | wall 16.7 s (21.9 s in a second run); grow 89 (0.06 s); A* 180 (0.10 s); hub 16 (0.24 s) |

The three router groups were already at 0 Python grows / A* / hubs after wave 1; K4 takes m2m
there too (the A* count falls 872 -> 180 because the 60 Python grows' steps were A*s: they now
run inside the kernel's grow). What K5 saves is the Python rebuild inside each native call
(`_tree_from_native`, `tree.cost()`, `counts()`, `problems()`, `entities()`): on test_m2m the
native grow seconds fall 0.15 -> 0.06 and the hub 0.39 -> 0.24; on the three router groups the
search seconds are within this laptop's noise (route 0.58 -> 0.77, pairs 1.77 -> 1.13: two
runs of the same code move by that much, see wave 1), i.e. the rebuild was never a visible share
there. The walls are dominated by the tests' own Python (m2m's max-flow and played pass): the
same test_m2m ran 23.5 s, 38.3 s, 16.7 s and 21.9 s across the four measurements.

`FK_NATIVE=check` after K4 and again after K5, all green: test_native (19 after K4: 66.9 s
native-only / 58.2 s check; 20 after K5: 65.7 s / 51.7 s), test_m2m (23: 59.2 s after K4, 28.3 s
after K5), test_route (25), test_route_taps (6, 6.5 s / 3.7 s), test_steiner_split_tap (3),
test_lanes_pairs (30, 6.2 s / 3.5 s), test_lane_goal (6, 41.6 s / 23.7 s); after K5 also
test_route_promote (4), test_port_pairs (4), test_route_units (3), test_route_cycle (1),
test_route_ground (2).

After merging main twice (`claude/40-layout`: `place.rs`; `claude/40-lanes`: `lane.rs`), the
kernel rebuilt as 0.4.0 with all three branches' modules, `FK_NATIVE=check` green again on
test_native (20, 57.4 s), test_m2m (23, 36.7 s), test_route, test_route_taps, test_steiner_split_tap,
test_lanes_pairs, test_lane_goal (34.3 s), and on the merged branches' own test_lane_state (16,
56.3 s check / 42.1 s native) and test_layout (11, 134.0 s check / 34.3 s native). test_m2m with
`FK_NATIVE=0` (the pure Python search): 51.1 s wall against 25-32 s native.

## Open

- K6 (the ground) only if the profile asks: the route step on the real workloads is the
  measure (`tools/buildbench.py` on grove alone and a lab bay), not yet re-run on 0.4.0.
- `_forward_ground` (the Python hub's step) still builds a `Tree` from the kernel's raw tree
  when the Python hub runs (a sink the kernel does not know, or FK_NATIVE=0); the native hub
  needs none.
- An installed `fkroute` older than 0.4 is ignored (`_NATIVE_NEEDS`), as before with 0.3.
