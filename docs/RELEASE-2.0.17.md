# Toolkit 2.0.17: the lane pairing is a check, and chests first, belts later

Rory, 2026-10-25, on the 0928 run: "the agent made a smelter that had two separate belts with one
lane each, a big red flag that the new two lane router didnt land", and "it should not use belts for
its first factories, and not use logistic chests for its later factories. over reliance on combined
belt and logistic chest bases gives the worst of both worlds. Logistic chests can lead to factories
as small as 3x5 that use only 5 items total. Belt based factories run continuously without using up
logistic robots and going slow."

- **`LANES` check.** The two-lane router is real: pairing the 0928 smelter's ore and coal nets takes
  it from 74 belts to 61 and one inserter per furnace instead of two. But the design has to say
  `lanes ore_ | fuel`, nothing else ever mentioned it, and the build said nothing. Now a check names
  the two chest-fed nets that feed one machine set on belts of their own and gives the exact line:
  "one belt carries both (`lanes fuel | ore_`), one lane each". Scoped to chest-fed pairs (two raw
  feeds out of the network), so a mall's own product belts are not nagged; only pairs whose flows
  fit a lane are named.
- **`STRATEGY.md`: "Chests first, belts later".** The two feed styles belong to two phases: chests
  for the first factories (a 3x5 cell, five items, minutes to change) and belts for the ones you
  mean to keep (they run continuously, use no logistic robots, and don't slow down when the fleet is
  busy). Running both pays for both.
- **The core-v1 brief** gets the same four lines, and `LANGUAGE.md` / `TOOLKIT.md` get the pairing
  rule and the `LANES` line.

Tests: `tests/test_lanes_check.py` (two chest feeds are named, a paired design is quiet, product
belts are not advice, and the pairing saves 13 belts in the route).
