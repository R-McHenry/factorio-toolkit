# Toolkit 2.0.77: a splitter's branch gets its inserter

Rory, 2026-10-31: "diagnose any routing failures that happen and see if we can make a toolkit fix,
or maybe just figure out some margin rules to prevent it".

## The fault

The 10-30 run's Sci0 (`net cu: cu_in -> red1, red2`) was `partly-connected` on every build from
~100k on: red2 never got copper and red science ran at half. The route was the same each time
(15 belts, 1 splitter, 1 inserter), whatever the player moved.

The copper trunk ran west in the one free row between red1 and red2. `steiner.grow` cut a splitter
one tile short of them. A* tested the goal for red2 (a `TapSink`) against the tree *before* the
splitter was laid, and planned red2's inserter on the splitter's second tile. `_attach` then laid
the splitter, picked again, found that tile taken and laid no inserter, but still counted red2
reached. `Tree.problems` didn't check taps, so the route said `routed` and only `report_checks`
saw the gap. The branch's belt ran west into nothing.

Reproduced offline on 9e808bc from the run's `world-h0.fk` with sci/cu's carriers dropped from
its `.fkp`: `routed sci/cu: 1 -> 2, 18 belts, 2 underground ends, 1 splitters, 1 inserters`, and
report_checks `partly-connected ... unreached sci/cu_in -> sci/red2/m0`.

## What changed

- **A start state names the tiles its move takes** (`steiner._starts`, `_Patch.out_starts`: a
  splitter's two). `_astar` passes them to the goal test, so `TapSink.pick` plans no tap on them.
  `route._new_branch` makes the same choice when it lays the patch's branch.
- **`Tree.problems` names a tap sink with too few inserters** (`UNTAPPED name: j of k inserters`),
  so a tree like that fails, and the route tries the next hub or hand, instead of passing as routed.
- **TOOLKIT.md, "Room for routes"**: the run's other failures had no room, not a router fault (a
  belt in a 1-tile gap, a shared maker at a row's end, a port on a main's path, a far consumer
  on a main, a third belt into a row). Plain tips with the run's cases.

Same repro on 2.0.77: `routed sci/cu: 1 -> 2, 22 belts, 2 underground ends, 0 splitters, 2
inserters`; 39 of 39 nets connected.

## Checked

- `tests/test_steiner_split_tap.py`: the Sci0 geometry (red1 and red2 one row apart, the trunk
  between them). It fails on 2.0.76 (only red1 tapped, no problem reported) and passes now.
- Full suite: 1141 tests OK.
- The run's A4 draft (cb5o, ci5o) still fails on 2.0.77, as expected: cb5o has no room once the coal
  patch to pl2 takes the corridor. That's layout, covered by the new tips.
