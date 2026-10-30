# Toolkit 2.0.67: the archive's map, a vertical axis that never stops rising, and the best path

Rory, 2026-10-29:
- **Two axes.** "an even easier way to frame this then distance metric will just be basically
  vertical and horizontal position. This tech tree option can be used to accurately place each
  cell along an axis towards the end of the game ... Then later we can have horizontal distance
  based on how far off track a cell is from the main best path that reaches some high vertical
  point quickly."
- **One dimension.** "make sure that the positive material axis and the research axis fold into
  the same dimension, so getting more of an item is always still counting as pushing the game
  forward far past the last research".

## Worth: one currency (`Tree.values`)

Every item's worth is in raw units, from the game's own recipes, which the dump now reads with
their amounts.
- **Raw things.** An ore, a chunk or a fruit is 1, and a unit of fluid 0.1.
- **Anything made.** Its cheapest recipe's ingredients over its products, net of what the recipe
  gives back.
- **Home first.** Nauvis's raws and everything made from them are priced first, then the rest
  from off-world raws and chunks, never cheapening what home priced. Otherwise asteroid crushing
  and lava casting put iron ore at 0.04 and every early count at almost nothing.
- **In the Space Age game:** iron ore 1, gear 2, red science 3, green 7, blue 25.75, rocket part
  121. A breeding item (pentapod eggs) is worth nothing net.

## V: how far up the game (`explore.vertical`)

**V = log2 of the cell's worth**, where the worth is:
- what it has made: each item's count (its level's lower bound) times its worth;
- plus the worth of the science packs its research implies: the research behind everything it has
  made, from nothing researched, beyond the packs it has already made.

Research is just the packs it took, so it's on the same axis. More of any item always raises V,
far past the last research. On the planner:

| what | V |
|---|---|
| the opus base | 18.15 |
| the same, 3 more levels of plates | 18.18 |
| the same, with one cryogenic pack | 21.06 |
| a fresh start, one red pack | 1.6 |
| a fresh start, one rocket part | 16.7 |
| a fresh start, one promethium pack | 21.8 |

## H and the best path (`Archive.positions`)

- **Cell paths.** Each round records every cell it passes, in order, so each cell keeps `path`,
  the cells from the root to it.
- **The best path.** The path of the cell with the highest V, the earliest at a tie.
- **H.** A cell's Manhattan distance to the nearest best-path cell no higher than itself. On the
  path, it's 0.

`fk sim explore archive` is now the map: V, H, and `*` on the best path, highest V first.
`--pick track` starts rounds from a band of V picked uniformly (eight bands between the lowest
and the highest), then from a cell in it weighted 1/(1+H). The default, `--pick uniform`, stays
impartial. The goal walk is unchanged (2.0.66's science-weighed steps).

## Tests

`tests/test_techcost.py` adds:
- worth from home first, with a cheap far route that must not price plates;
- V rising with more of an item, and with an item far up the tree;
- the best path, H, and every band picked by `--pick track`.
