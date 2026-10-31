# Toolkit 2.1.14: ribbons, belts side by side

Rory's smelter bus is eight columns of plates. Until now the router laid each column's belt on its
own: eight belts, each finding its own way to the consumers. Now
belts that belong together are laid as one **ribbon**: side by side, in order, all the way.

Three things make a ribbon:
- the nets of a `net each`, belt k carrying net k;
- `bundle NAME: a, b, c`, nets you declared, belt 0 carrying `a`;
- a wide net, `net plates width 8:`, four belts of its own.

What the router keeps:
- the belts stay adjacent and in order;
- a turn is nested, the inner belt first, and no belt crosses another;
- at a crossing every belt goes under together, side by side, all the same length;
- a belt joins and leaves from the side, at its own offset; the outer belt leaves first, and the
  rest don't close up.

A ribbon with no path is unrouted, every net of it. It is never split into loose belts.

A wide net's drivers are dealt out at the head in the order they stand, so no belt gets more
than its two lanes (15/s on yellow). Its consumers are split the same way. With fewer drivers or
consumers than belts it says so; a group of drivers too fast for one belt is refused.

Refused: a bundle's nets running different ways, a net in two ribbons, a fluid net, a `lanes`
pair, a bus, a bundle of one net, and an odd width (`width 3`).

How it routes: `fkcore.steiner.ribbon` searches the ribbon's centre line with a footprint as wide
as the ribbon. A turn is an n by n square; a crossing is one jump of every belt; a belt drops out
at its own consumer. Each belt's way in from its driver, and on to a consumer the ribbon doesn't
reach, is an ordinary route. `fkcore.ribbons` plans the ribbons and lays them; `route` routes
them first and re-routes a whole ribbon in its repair pass. The judge (`connect`) checks a wide
net as dealt: every driver reaches a consumer, and every consumer is reached.

The route report adds a line per ribbon (TOOLKIT.md): its head and tail, turns, crossings, belts,
and how its belts joined and left it. Each net's line says which belt of the ribbon it is.

In the lab (`tools/lab_ribbons.py`, a laptop server): the eight-column bus to a row of eight
chests, 533 belts, two turns. Every chest k is fed from column k, traced back in the game, and
takes in what its column makes (112.5 plates/min each where the ore keeps up).

- New: `fkcore/ribbons.py`; `steiner.ribbon`; `lang` `bundle`; `elaborate.ribbons(flat)`;
  `connect.Dealt`.
- Tests: `tests/test_ribbons.py` (a 4-belt ribbon with two turns and a crossing; belts ending one
  by one; refusals; a gap too narrow is unrouted; a width 4 net dealt out; the 8-belt bus).
- `tests/nest/bus-ribbon.fk`: the bus routed as a ribbon.
