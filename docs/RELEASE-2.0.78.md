# Toolkit 2.0.78: crossing a belt by promoting it to an underground

Rory, 2026-10-31: "maybe we should make it some kind of a mutation option for a belt that is
blocking a path to be modified into an underground. Even if its pinned, it could still have an
easy or default way for it to still sometimes get promoted to underground as long as that does not
affect inserter connectivity".

## Promotion

A net that finds no route is tried once more (`route._route_promoted`), with every promotable tile
of another net's route as ground it may cross. That happens in one extra routing pass, run only
when the usual passes (each one moving the failed nets to the front) still leave a net unrouted,
and in the judge's repair when re-routing around the fault finds nothing. A first version tried
it in the first pass: redgreen's nets then took promotions they didn't need (they route after a
reorder), and three flow tests caught it.

For each tile its route takes, that net's three belts there (behind, on, ahead) become an
underground entrance and exit with fresh keys (`_promote`): the same items on the same lanes,
under the crossing. Pinned (standing) routes are promoted the same way as routes laid this run.

A tile is promotable (`_promotable`) only where nothing but the belt changes:

- a route carrier of another net (`~net/...`), never a template's own belt;
- a straight run of five plain belts of one name, owner and heading (two behind, two ahead), and
  an underground of that tier in the catalog;
- no inserter (any net) picks from or drops onto the three belts that change, and no drill drops
  onto them;
- nothing feeds them but the belt behind (no side-load, no splitter);
- no underground end of the same axis within 6 tiles along the line, so the game pairs the new
  ends with each other;
- the tile is in no frame, terrain or net end.

Two crossings on one run whose pairs would overlap fail the promotion. The promotion pass is kept
only if it routes more nets than the best pass without it. `out\route.txt` has a `promoted` line
per pair, and the routed net's line names each crossing.

## An exit facing what stands (steiner)

The 10-30 run's A4 draft lost cb5o this way: its tap branch ended on an underground exit pointing
into the coal belt. `_settle_leaves` turns a plain belt leaf off another net's belt, but an exit
can't turn, so the judge refused the net (SPILL). A forward tap branch now never ends on an exit
whose tile ahead is taken (`TapSink.goal`).

## Checked

- `tests/test_route_promote.py`: a band of six belts across the whole box (too wide for a yellow
  tunnel) fails without promotion ("no hub") and routes with it. Each column gets an entrance and
  an exit 2 tiles apart, keeps its heading and still carries end to end, and there is one
  `promoted` line per column. A belt an inserter touches isn't promotable, and a net that routes
  promotes nothing.
- `tests/test_steiner_split_tap.py`: the exit rule.
- The 10-30 run's A4 draft (the player had given it up: "Not pasted"), from a clean `out`: 105 of
  105 nets connected, 0 SPILL; cb5o 1 -> 3 and ci5o 1 -> 2 route with no promotion.
- Full suite: 1146 tests OK.
