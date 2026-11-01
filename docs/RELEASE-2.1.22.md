# Toolkit 2.1.22: many-to-many routing on both lanes

Rory, 2026-10-31: "filling both sides now and having the router select". `route --m2m` now fills
both lanes of every belt and picks each driver's lane; `route --m2m left` is version 1 (the left
lane only). Nothing changes without `--m2m` (the golden examples: 60 of 60 identical).

## The router picks the lane

- A driver's inserter may stand on either side of its belt. An inserter across a belt fills the
  far lane, so the side is the lane: on the belt's right, the left lane; on its left, the right.
  The hub takes the taps its search finds; an added run may start from a driver on either side.
- No side-loads are laid and a splitter keeps the lanes, so the left and right lanes are two
  networks on the same belts. A run keeps its lanes end to end, so it is searched lane by lane:
  its start upstream of the cut on that lane (a split belt's lane, or the lane its new inserter
  drops on), its end downstream on it (a merge belt's lane; a consumer picks from both). The
  cheaper of the two is laid.
- A run that raises no flow is banned and the search tried again (12 at most), instead of ending
  the search, so the router passes over lanes that don't help.

## The max-flow on the lane graph

`maxflow.solve(..., lanes=True)` (and `of_net`): a node per lane of the lane graph as it is. An
inserter drops onto one lane and picks from both; straights, turns, tunnels and splitters keep
the lanes; a side-load puts both onto the near lane. A belt end that supplies or takes does so on
either lane. `Flow.S` and `Flow.T` still name carriers; `Flow.lane_S` and `Flow.lane_T` name
lanes, and the cut names lanes (`key:L`). The `MAXFLOW` line of an m2m net counts lanes this way.

## The bench

Every router's max-flow is now counted on the lane graph. `tools/hourglass.py --left` adds the
version 1 row; `tools/hourglass_png.py` draws four panels (m2m, m2m-left, today, balancer).
Cost by case:

| case | m2m | m2m left | today | balancer |
|---|---|---|---|---|
| 8to8 | 81 | 81 | 81 | 108 |
| 16to16 | 192 (waist 2) | 287 (waist 4) | 145, short 15.0 of 22.4/s | 249 |
| 16to4 | 111 | 143 | 123 | 151 |
| 4to16 | 105 | 137 | 138 | 139 |
| uneven | 81 | 108 | 96 | 125 |
| wall | 113 | 140 | 113 | 149 |

Every m2m case meets its demand with full reach and no side-load; 16to16's waist is two belts,
22.4/s over 15 a belt rounded up. Not measured yet: how evenly a splitter really shares (the
max-flow is the best case).
