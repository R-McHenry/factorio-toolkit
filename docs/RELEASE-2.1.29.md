# 2.1.29: fluid routing in seconds, and it says where it is

The 20261030-2352 player's dry builds sat silent for 10+ minutes after the belt passes (11-01
02:43 onward, the third time that night): fluid routing, with no progress line and no budget.
Measured on a copy of the run's world (17 fluid nets, a 1636x1329 frame), fluid_route alone,
started from its saved inputs:

| | 2.1.28 | 2.1.29 |
|---|---|---|
| ac_a | 7.0 s | 0.4 s |
| c4_crude | 13.5+ s (still going at the cap) | 0.4 s |
| all 17 nets | 12+ min (one net 738 s in a 950 s probe) | 27 s: 16 routed, c4_lub fails |

## What changed

- **The A* distance map covers the tree's own box.** Every join built a distance map to the tree
  by a BFS of the whole frame (2.2M tiles here), and every retry of a join built it again. The
  map is now a BFS of the goals' bounding box; a tile off it is its distance to that box plus the
  distance at the box's nearest tile, which is exactly the Manhattan distance, so the search,
  and every route, is the same. It is built once per join, not once per try.
- **Fluid retries stop when one does not help.** A failed net sent the whole fluid layout round
  again with the failures first, up to nets + 1 times. Now the retries stop at the first round
  that routes no more nets than the best before it. A world whose second order would have helped
  only on a third or later round can now lose that net (none seen).
- **Fluid routing reports progress** like the belt passes: `route: 40s in, fluid pass 1, net 3
  of 17 (c4_crude)`, and a net of 30 s or more is named when it ends.
- From the 2.1.28 work, not released before: route remembers entity tiles, natural keys and net
  names (catalog.tiles, fkp.natural_key, fkp.net_names: lru caches), and the promoting pass is
  called that instead of "pass 280".

## Checked

- The new distance map against the old BFS: 300 random boxes and goal sets, every tile of each
  box and 3 around it, no difference (tests/test_fluid_2129.py keeps a smaller copy).
- tests: the whole suite.
- The run's world: fluid_route from its saved inputs, 27 s, 16 of 17 routed; c4_lub (frm5/lub_in
  to c4_rf/lub_out) has no pipe route in this layout, as in 2.1.28's first passes.
