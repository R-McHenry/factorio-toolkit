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

## Open

- K4 (m2m's sinks) and K5 (entities out) are wave 2. The kernel's physics table has no reader
  until K4's drop lane.
- `hub_search` returns trees, not entities, so Python still rebuilds a `Tree` per hub search
  (two for the winner, one or two for a first failure); K5 removes that.
