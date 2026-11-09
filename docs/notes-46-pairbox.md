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

## The change

`fkcore/pairs.py`: both `_ground` calls pass `box`. No ROUTER bump (the ground inside the box is
the same set of tiles; only the time changes).

## Measured

(filled in from the no-stands flower and the fk-t6 rebuild)
