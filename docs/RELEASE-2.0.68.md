# Toolkit 2.0.68: rounds start and aim by the map's coordinates

Rory, 2026-10-29: "lets make both the go and explore actions be based on selecting cells using
these coordinates as a basis".

## Go: uniform over the map's bins (`--pick grid`, the default)

The archive's cells are binned by V (eight equal bands from the lowest to the highest) and by H
(`explore.H_BANDS`: on the path, 1 off, 2-3, 4-7, 8-15, 16+). A round starts from an occupied bin
picked uniformly, then from a cell in it. A crowded corner of the map no longer outweighs its edges.
`--pick uniform` (every cell alike) and `--pick track` (V bands, weighted toward the best path) stay
as options.

## Explore: a goal picked in coordinates (`--rise`, `--steps`)

`Archive.pick_goal_vh`:
- **Candidates.** It draws 40 candidate cells, each a walk of +1 steps from the go cell until its V
  has risen by `--rise` (0.1 by default, about 7% more worth). A step is picked uniformly from
  those that keep V at most 2 x `rise` above the go cell, at most `--steps` of them (12 by default).
- **Far items stay out by themselves.** An item far up the tech tree overshoots a small rise on
  its own, since its research is folded into V. One fluoroketone barrel takes the opus base from
  V 18.15 to 21.06, so it never comes up. 2.0.66's science penalty isn't needed for this, and is
  used only as the fallback walk when no candidate rises at all.
- **The pick.** An H band picked uniformly among the candidates', then a candidate in it. Its
  changed items are the manifest, and the player still sees only that.
- **Items only.** Fluids are left out of the pool, since the cells count items made. Light oil in
  a manifest could never be met.

`explore.Worth` keeps V up step by step: a step costs only what it changes, one item's count and
the research a new item adds. It agrees with `vertical` exactly (tested on every kind of step), so
a goal takes about a second on the Space Age tree.

## Checked on a laptop planner

On a copy of the opus base, at base 1.05:
- **Rise 0.05:** an accumulator, magazines, a boiler.
- **Rise 0.1:** a rail ramp, ore, a laser turret, utility science.
- **Rise 0.5:** a crusher, metallurgic science.
- **Rounds.** Five ran end to end. Each started from a bin of the map and showed its manifest.

On a big base, a small rise is many small items. Tune it with `--rise` and `--steps`.

## Tests

`tests/test_techcost.py` adds:
- the incremental worth agreeing with `vertical`;
- goals rising by their rise, never past 2 x rise, never naming the far item or a fluid;
- go picks covering every bin of the map.
