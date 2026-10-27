# Toolkit 2.0.48: a port is an edge

Rory, 2026-10-26: "I think a 3 tall cell should have 3 tiles of routing space. Did modules end up
with a boundary that occupies a grid cell? I think our boundaries should be along an edge so that a
port occupies zero area", and "make the port belt a hypothetical thing ... just a hypothetical
connector on the other side".

## What was wrong

Since 2.0.36 a sealed module's port was a **tile**: a carrier belt standing on the frame's edge
tile, inside the frame, carrying both the module's net and the parent's, with the tiles just inside
and just outside it kept free. A 3-tall cell lost two of its three rows to its ports, the router
put no inserter on a port belt, and two modules meeting on an edge had two port belts side by side
with a "net" between them that had nothing to lay. The stacks work (a line of 3-tall cells) ran
into all three.

## The model now

A port is a place on the frame's **edge**, taking no tile. The belt crosses the edge there:

- the module's own route reaches the tile **just inside** the edge; its port role is attached at
  the tile just outside, as the hypothetical belt across the edge that feeds it (an `in` port) or
  that it feeds (an `out` port);
- the parent's route reaches the tile **just outside**; its role is attached at the tile just
  inside, the hypothetical first belt across the edge;
- so the router's own rules (a route starts on the tile a driver's belt points into, and ends on
  the tile behind a consumer's first belt) lay each side up to the edge, and the last belt of one
  points across it into the first belt of the other.

Every tile of a module's frame is its own route's. Two ports that meet on one edge (a module's
`out` port against the next one's `in` port) are a net that **lays nothing**: its driver's belt
already points into its consumer's first belt.

## What changed underneath

- `expand`: a sealed module's fragment has no entities, only its two roles per port, attached
  across the edge. `expand.port_edges(flat, lay, cat)` gives each port's `PortEdge`: the tiles
  just inside and outside, and the crossing (`src` -> `dst`) as the items go.
- `connect`: `graph(..., ports=)` / `connect(..., ports=)` thread each port into the one
  belt-to-belt edge it crosses, as a node keyed as the netlist keys the port: the consumer of the
  net its items leave and the driver of the one they enter, a joint, not a LEAK. Ports on one
  edge chain. `endpoints` no longer aliases a port to a carrier.
- `route`: a route's last belt may point across a port's edge (`_crossings`); a net whose ports
  abut lays nothing (`_abuts`, reported "nothing to lay (its ports meet on one edge)"); every
  judgement and patch sees the ports. SEAL: a carrier of another net inside a sealed frame ("a net
  crosses a sealed frame only at a port's edge"). PORT: a machine on the tile just inside or just
  outside a port's edge.
- `routed`: a port's capacity is read on the lanes of the belt just inside its edge.
- `fkp`: a port record no longer needs a carrier in the layout (the record format is unchanged:
  `at x,y` is still the tile just inside the edge, in the module's own frame).
- `flow`: the report step's connectivity sees the ports.

## Verified

- The four-rib example: 18 nets connected, no LEAK, SEAL or PORT; each rib's own route starts on
  the tile inside its west edge, the bus tap's belt points at it from the tile outside.
- The bus base: 35 nets routed, no check lines, the same contract; 1691 entities, where 2.0.47
  laid 1760 (the port belts, and the belts around them, are gone).
- `tests/test_modules3.py` and `tests/test_ports2.py` now describe the edge: a port's two roles
  attached across it and no entity; the routes meeting across it, connected with no LEAK; the
  15/s crossing rated on the belt inside the edge; a turned module's recorded edge; pins and
  records as before.
- The full suite: **992 tests, OK**.
