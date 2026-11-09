# 46-pairbox: the pair router's ground inside its box (the flower's lab columns)

Branch `claude/46-pairbox`, cut from main 0f768a9 (3.2.0), 2026-11-09 midday, from the T6 flower
(`lab-session\fk-t6`).

## What failed

The core's eight lab columns (`LabCol5`, 11x44: five pack belts in at the west edge, three trunks
turning north in six rows to a stack whose pair ports stand on adjacent columns x3 and x4) failed
their red|green pair in every flower build, and routed clean in every build of the core alone: at
the flower's position, on its terrain, with its `territories.json`, with the stands, turned or
not. The ground the pair router saw was the same in both (dumped tile for tile: blocked, frames,
terrain, the job's ends, the box). What differed was time:

- alone, `b|p` is laid first (the order is ends then name) at 378,702, on the row `r|g` comes in
  on; `r|g` fails; the group pass lifts the four nets in its way, lays `r|g` first and `b|p` round
  it: `laid again with 4 nets in its way, all routed (0.8 s)`;
- in the flower the same group pass reads `not settled in the budget, left alone (3.6 s)`: the
  route step's `--group-budget` is 3 s a failed net, and each part route of a pair cost several
  times more there.

The cost: `pairs.route_lanes` and `_laid_lanes` built their ground with `routemod._ground(...)`
and no `box`, so every part route (up to 48 a pair, over six trunk roots, twice per group try)
walked every net's ends of the whole layout, 5749 jobs in the flower against 624 alone. 2.1.33
had given `_route_in` the box for the same reason; the pair router kept the old call.

## The changes

Three costs that grew with the layout, found one under the other by profiling the column's
routing in the flower against the same column alone:

1. `fkcore/pairs.py`: both `_ground` calls pass `box` (the pair router read every net's ends of
   the whole layout per part route).
2. `fkcore/route.py` `_ends_index`: the pair router routes a trunk and each part with a copy of
   the jobs dict and one or two jobs swapped in (`_laid_lanes`, `_side_part`: a member net added,
   the pair's job replaced), and every copy rebuilt the index over every net; profiled, 6.2 of
   the column's 7.7 s were there. A copy with at most six jobs changed, added or dropped reads
   the one index with those jobs laid over it (`_ground` skips their old ends, adds their new).
   After this the column's pair search took 1.8 s in the flower against 1.9 s alone.
3. `fkcore/route.py` `_serving_only`: the tail judge built a connect graph of the whole layout
   (48,000 entities, 1.8 s a call) for every pair it trimmed; a group retry trims each pair it
   re-lays, so the column's retry spent its 3 s there. The graph is now of what stands within
   `_CLIP` tiles of the laid carriers (the judge walks from the net's own ends, machines the
   carriers touch).

Also `fkcore/link.py` `read_output`: the game writes its answer file after the RCON reply, on
its own thread, and the flower's paste answer (8.8 MB, 48,560 ghosts) landed a second after the
toolkit tried to read it, so the apply step died at the read and the ghosts were never revived
(the diff's snapshot of the same area the same). The read now waits for the file, and for its
JSON to be whole, up to `FILE_WAIT` (180 s, `FK_FILE_WAIT`; the 10 MB answer took 30 s to land).

No ROUTER bump: the ground is the same set of tiles and the judge the same verdict; only the
time changes.

## The route step's fixed cost (measured, not changed here)

The whole route step of the no-stands flower under cProfile (406 s, 3312 nets, 3248 laid from
the store): `seal_checks` 278 s (every entity's tiles against every sealed module's frame,
49 M `Frame.contains` calls), the design database's `read_all` 30 s and `_write_nets` 34 s
(11,448 file opens), `connect.graph` 44 s over 832 calls, the fluid search 29 s. The searching
itself was 45 s. `seal_checks` wants an index of frame tiles to modules instead of the double
loop; that is a round of its own.

## Measured

The flower's seven modules without the stands (`flower_ground.fk` with the rivers and the core
only, the stands' feeds out), routed from scratch with the store warm, on this laptop:

| toolkit | lab columns | the column's level | the group retry | route step |
|---|---|---|---|---|
| 3.2.0 | 8 of 8 failed | 7-8 s | `not settled in the budget (3.6-4.3 s)` | 254 s |
| 1 (pairs' box) | 8 failed | 7.5 s | 3.8 s | 254 s |
| 1 + 2 (one ends index) | 3 failed | 5.1 s | 3.4 s | 195 s |
| 1 + 2 + 3 (the judge clipped) | **0 failed** | under the twelve shown | settled | 190 s |

The two nets left failed in the last build are fen's lubricant pipes to the core and to works at
`--effort normal` (the long-pipe search limit; fk-t6 builds at `--effort high`, where they route).
The core alone: 334 nets, 0 failed, unchanged.
