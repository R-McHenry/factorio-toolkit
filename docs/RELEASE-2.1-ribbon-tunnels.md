# Toolkit 2.1 (ribbon tunnels): each belt under on its own, and deeper

Until now a ribbon crossed anything by taking every belt under together, all the same length,
and no tunnel reached past yellow's 5 tiles. Now:

- **Each belt tunnels on its own.** A belt goes under only what blocks its own line. Its tunnel
  starts on the free tile before the block and ends on a free tile after it. The other belts stay
  on the surface beside it. The ribbon keeps its shape: belt k stays k tiles from belt 0, in order.
  A crossing that blocks every belt is still every belt under together.
- **Reach follows the tier.** A tunnel reaches as far as the fastest tier the ribbon may lay:
  yellow 5 tiles, red 7, blue 9, turbo 11. `route --ug yellow|red|blue|turbo|any` sets it. `any`,
  the default, is the fastest underground the network can build sixteen of (out/avail.json), else
  yellow. Each tunnel is laid with the slowest tier that reaches it, so a 5-tile one stays yellow.
- **The tier step keeps them.** `tier` never gives a tunnel an underground that falls short, in
  every mode, `yellow` and `--downgrade` included. A test checks it on a ribbon.

Each tunnel is straight, never through a turn. Its two ends are on free tiles. It never covers
another underground on its line (the interleave rule). A tunnel may run on past its block when that
saves belts, up to its tier's reach.

The route report's ribbon line now says which belts went under and where:
`1 crossing (2 belts under: belt 2 102,27 to 102,32, belt 3 103,27 to 103,32)`. A tunnel past 5
tiles adds its length and tier: `(7 tiles red)`.

In the lab (`tools/lab_ribbons.py --rock`, a laptop server): a 2x2 rock in front of belts 2 and 3
of the eight-belt bus. Only those two go under it, 5 tiles, and the other six run on beside it.
Every chest k is still fed from column k, traced back in the game through the tunnels, and takes
in what its column makes (112.5 plates/min where the ore keeps up). Without the rock nothing
changes: two turns, no tunnels, 533 belts.

- `steiner.ribbon`: the tunnel move replaces the all-together jump; it returns `tunnels` and
  `counts["under"]`.
- `route.route_layout(..., ug=...)`, `ribbons.ug_tiers`, flow `route --ug`.
- Tests: `tests/test_ribbons.py` `TunnelTest` (eight belts under six rows on red, unrouted on
  yellow; eight rows fit blue, not yellow or red; a rock under two belts, only they go under; the
  search on its own; the tier step keeps red).
