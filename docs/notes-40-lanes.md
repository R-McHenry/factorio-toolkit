# notes-40-lanes: the lane router, wave 1 (N0, N1)

Branch `claude/40-lanes`, 2026-11-08/09, laptop. PLAN-4.0 part N; the spec is
docs/DESIGN-LANE-ROUTER.md, the Python reference `fkcore/lanesearch.py`, the kernel's leg
`native/fkroute/src/lane.rs` (`fkroute.lane_astar`), the tests `tests/test_lane_state.py`, the
measurement `tools/lane_measure.py`.

## What landed

- `lanephys.entry(carrier, d, src, feeds)`: the move kind of one feed (turn, side, ug_side,
  straight or none), which `fed` now uses; `lanephys.table()`: the rules enumerated as data
  (192 move rows, drop 16, turn_drop 32, mine 16) for a kernel that states none.
- `lanesearch`: the state `(x, y, h, ex, L, R)`; the moves step/turn/jump/split (kept), stub,
  side-load into the tree or a host, ride, leave, drop (drop_lane, turn_drop_lane), tap; goals in
  lanes (`Fixed` with `need`, `Tap`); hosts as data with entries and hops precomputed from the
  table and checked downstream; a `LaneTree` per net with `propagate` (own belts by `fed`, rides
  by the move that entered them) after every leg; a job routed in every net order; each tree the
  next nets' host; shared taps; riders' items followed along the hosts past their goals.
- The leg in Rust, step for step (heap `(f, -g, state)`, the same move order and cost sums);
  `FK_NATIVE=check` runs both and raises on a difference. The table goes in with each call
  (main's `fkroute.physics` landed after this branch was cut; see "Open").
- `tests/data/line11.fk` and `mall-shared.fk` from the October branch, the future bar.

## What the synthetic fields showed (and fixed)

Every case in `test_lane_state` is confirmed by `lanes.reach` over the carriers laid. Found by
the judge on random fields, each a modelling gap, each now a rule of the search:

- a belt's heading is where its move goes: a Fixed end turns into its consumer, a driver
  attached straight into a tree belt feeds it from behind (not the way the belt arrived);
- a belt a stub side-loads keeps the heading the stub gave it (its next step is straight);
- a drop root never turns (its lane hangs on its heading);
- a ride's lanes are recomputed when the net's own lanes upstream change (a second driver
  raising A to both lanes into B's stub was refused once propagate saw it);
- a rider's items flow on along the host past its goal: through a splitter to the other output,
  to the chain's end; those are ride states of the tree (free goals included), later nets see
  them, and a forward leg never rides into its own ride tiles;
- a splitter half feeds its front once (not once per half), else a straight output looked like
  a two-sided side-load;
- the tile ahead of a belt end is the consumer's belt; the other nets' belt ends and the net's
  own later drivers' ends are blocked until they attach;
- an entry into a host that a hand or a drill feeds (a curve, or an unfed belt with items) is
  never made: it would move the host's own items;
- with a host to ride the Manhattan heuristic over-estimated (ride 0.15 a tile), so it is
  scaled by the ride price when hops exist;
- the kernel saw a chain's end as an own belt (only tiles with hops were hosts) and turned off it.

The one-tile-corridor underground case: given room, the search moved the items to the open
lane by a stub side-load first and went through, which is right; the test forbids the room.

## Tests

`python -m unittest tests.test_lane_state` (16 tests): pairs (two side-loads onto a stub, a
mid-way side-load with a ride, the cheaper of both orders), hosts (a ride on a free lane, both
lanes taken, the closed side of an underground), drops (onto a turn by turn_drop_lane, a machine
driver by a drop), a tap, the table as data, 80 random fields vs the judge, 120 random fields
Python vs Rust, check mode. Kept green: test_lanephys, test_lanes_check, test_lanes_pairs,
test_lane_goal, test_port_pairs, test_split_lanes, test_native (79 tests).

## The measurement (tools/lane_measure.py)

`python tools/lane_measure.py`: the pairs modules run with `pairs.route_lanes` wrapped; every
pair job it lays is also handed to `lanesearch.route` on the same ground, box and spans (the
near box first, then the whole box, as `_route_one`), both orders of the pair, and compared by
`pairs._cost` (belts, undergrounds by the pair, splitters: the search's own prices) and seconds
(laptop, the native leg). Nothing is wired into the build.

The three named modules (test_lanes_pairs, test_lane_goal, test_port_pairs; 40 tests, 7 distinct
jobs: the modules reroute the same layouts):

| job | kind | route_lanes | carriers | cost | s | lanesearch | carriers | cost | s | order | rides |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ore_\|fuel (SMELT) | pair | ok | 24 | 28.0 | 0.317 | ok | 24 | 28.0 | 0.017 | (1, 2) | 2 |
| ore_\|fuel (+smelt2) | pair | ok | 29 | 33.0 | 0.249 | ok | 36 | 40.0 | 0.022 | (1, 2) | 11 |
| ore_\|fuel (shared-belt.fk) | pair | ok | 41 | 47.0 | 0.342 | ok | 47 | 53.0 | 0.043 | (2, 1) | 22 |
| plates (furnace line) | wide | ok | 147 | 133.0 | 5.066 | ok | 129 | 105.0 | 0.159 | (1,) | 0 |
| ore_ (furnace line) | wide | ok | 177 | 167.0 | 2.474 | ok | 130 | 100.0 | 0.150 | (1,) | 0 |
| ore_\|fuel (port_pairs) | pair | ok | 31 | 38.0 | 0.450 | ok | 35 | 38.0 | 0.026 | (2, 1) | 28 |
| ore_\|fuel (port_pairs) | pair | ok | 34 | 42.0 | 0.469 | ok | 55 | 59.0 | 0.019 | (1, 2) | 2 |

7 of 7 routed both ways; carriers 483 -> 456, cost 488 -> 423 (cheaper 2, dearer 3, equal 2);
seconds 9.37 -> 0.44.

The wider set (test_width2, test_stacks, test_smelter_array, test_stack_auto, test_split_lanes,
test_lanes_check; 58 tests, 11 distinct jobs):

| job | kind | route_lanes | carriers | cost | s | lanesearch | carriers | cost | s | order | rides |
|---|---|---|---|---|---|---|---|---|---|---|---|
| plates | pin | ok | 16 | 16.0 | 0.156 | ok | 14 | 14.0 | 0.003 | (1,) | 0 |
| plates | pin | ok | 16 | 16.0 | 0.180 | ok | 16 | 16.0 | 0.003 | (1,) | 0 |
| plates | wide | ok | 147 | 133.0 | 4.851 | ok | 129 | 105.0 | 0.163 | (1,) | 0 |
| ore_ | wide | ok | 177 | 167.0 | 2.873 | ok | 130 | 100.0 | 0.114 | (1,) | 0 |
| plates | wide | ok | 114 | 98.0 | 1.935 | ok | 72 | 52.0 | 0.116 | (1,) | 0 |
| ore_ | wide | ok | 171 | 177.0 | 1.436 | FAIL | 137 | 134.0 | 0.121 | (1,) | 0 |
| ci\|pl | pair | ok | 22 | 28.0 | 0.465 | ok | 17 | 19.0 | 0.033 | (2, 1) | 15 |
| fe_a\|ge_a | pair | ok | 26 | 24.0 | 0.382 | ok | 25 | 23.0 | 0.014 | (2, 1) | 11 |
| eng\|sul | pair | ok | 18 | 15.0 | 0.076 | ok | 15 | 12.0 | 0.004 | (1, 2) | 6 |
| blue_engine_unit\|blue_advanced_circuit | pair | ok | 23 | 19.0 | 0.068 | ok | 20 | 18.0 | 0.005 | (1, 2) | 10 |
| ore_\|fuel | pair | ok | 15 | 13.0 | 0.121 | ok | 15 | 13.0 | 0.003 | (2, 1) | 3 |

10 of 11 routed (route_lanes 11); on the 10: carriers 574 -> 453, cost 529 -> 372 (cheaper 8,
dearer 0, equal 2); seconds 12.54 -> 0.58. The failure: the two-sided furnace line's `ore_`
(24 drivers): two drivers (`ore3/c0`, `ore4/c0`) end "breaks the lanes" (the attach's path was
found, propagation then refused it): open, below.

What the numbers say: the wide nets come out far cheaper (one tree with every driver attached
by a side-load where it fits, no join construct: 147 -> 129, 177 -> 130, 114 -> 72 carriers);
the pairs with machine consumers (the stack cells' and the lab's) a little cheaper; the three
smelter-row pairs dearer (29 -> 36, 41 -> 47, 34 -> 55): there the old join (both nets into one
root, found among 48 layouts) beats routing A's whole tree first and B against it, which
neither order nor the stub's price repairs. That is the case for N3 to close (a rip-up round
over the pair, or the second net's cost fed back into the first's search). The time is not in
question: 10 to 30x faster on every job, and the 30 s the wide net first took was
`_tree_entries`' trial propagations (6410 of them; now none for a one-id tree).

## Python vs Rust

`FK_NATIVE=check` on the 16 tests and the 120 parity fields: no difference. 40 random fields
(132 legs): Python leg 5.15 s in the leg, 5.54 s in all; native leg 0.55 s in the leg (the
argument marshalling and the tap callbacks included), 1.15 s in all: 9.4x on the leg, 4.8x end
to end; what is left is the Python bookkeeping (hosts, entries, propagate), N2's incremental
labels and the kernel's next step.

## Open for wave 2

- **Wiring pairs (N3):** `pairs.route_lanes` -> one `LaneJob` (ids, starts with their lanes,
  sources, goals in lanes); the carriers keyed under the pair as today (`~A|B/l*`, `/r*`, the
  trunk); `_lanes_hold` stays as the judge. `tools/lane_measure.lane_job` is the conversion.
- **`_widen`:** a wide net is one net with two driver groups and the goal (X, X); the groups
  come out of the attach legs, so `_halves` and `_one_net`'s relabelling go.
- **The grove case** (coordinator, 11-09): `fk layout grove.fk Grove` puts each Stack's foot one
  tile above its ports, and `pairs.route_lanes` then fails three pairs with "no side-load point
  on the stem of 4 belts". With side-load as a search move a pair needs no fixed stem length:
  that is the case to show when N3 wires the pairs.
- **Negotiation over lane slots (N4):** the resource `(tile, lane)` for belts; pres and hist on
  it; the kernel's `soft` is per tile today.
- **m2m (N5):** `LeftTap` as the drop rule's lane choice.
- **Not in the search yet:** a splitter branch off a host (October A6e), riding through a
  splitter with a goal on the other output as a chosen move (it is a free ride today), a drop
  onto a host the kernel then follows (a drop_host start is a ride root), FOREIGN passengers
  carried off a host (a ride leaves only when the net is alone aboard), rip-up and re-route
  (steiner's improve rounds), `k > 1` taps and arms on the lane goal (TapSink's geometry is
  reused with k, arms not).
- **The two-sided furnace line's `ore_`** (24 drivers, 171 carriers under route_lanes): two
  drivers "break the lanes" (the search's path passed its own merge checks, `propagate` then
  refused the attach). A search/propagate disagreement to find with the judge on that layout;
  the job still routes 22 of 24 drivers.
- **The kernel:** the leg is native, the tree bookkeeping (propagate, entries, attach, the
  orders) Python; with one-id trees skipping the trial propagations, a 130-belt wide net
  routes in 0.16 s. `lane.rs` should read `physics::table()` (main's K1) instead of taking the
  table in the call.
- **The October bar:** `line11.fk` (12 nets; the October router: two belts of four materials,
  circuits on the iron belt, copper on the gear belt, 99-111 entities, `best_of` 36-47 s on 8
  processes) and `mall-shared.fk` (9 nets; iron|gears on one belt, green on its own; the old
  router failed 3 of 9). No test on them yet: they need N3's wiring (a job per shared belt) and
  N4's negotiation.
