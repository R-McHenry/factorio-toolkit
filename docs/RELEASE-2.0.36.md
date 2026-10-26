# Toolkit 2.0.36: sealed modules route in their frames, and SEAL (phase 3)

PLAN-MODULES phase 3: a module that declares `size WxH` and `port` lines is **sealed**. Its port tiles
are chosen and recorded, its own nets are routed inside its frame, and `SEAL` reports any net that
crosses the boundary anywhere but a port. The lab geometry from 2.0.28–2.0.35 (the ports' sides and
the tap kinds) carries over unchanged.

## The port is a tile with a carrier

Each declared port is one tile on its side's edge (the `pos` in the declaration if pinned, else the
middle of the side), holding a carrier belt that faces **into** the module for an `in` port and **out**
for an `out` one. Two roles share the same tile and direction:

- the **inside role** work's the module's own net (an `in` port drives it, an `out` port consumes it),
- the **outside role** work's the parent's net (an `in` port consumes it, an `out` port drives it).

So the router's jobs meet the port from both sides (the parent's route ends at the tile outside, the
module's route starts at the tile inside) and the carrier is the only thing between them.

## The frame rules a net

`route_layout` now knows the sealed modules. A net whose name lives inside a sealed module
(`rib/fe`, `rib/g`) is routed with **its module's frame free and bounded by that frame**; every other
net keeps the frame blocked. That is the whole of sealing: a crossing can only be a port, because
nothing else can reach the frame's tiles. The two crossings the router has to allow -- the port
carrier, and a bus's mouth (a belt end of the bus itself) -- are joints in the leak check: a carrier
that is a consumer of the net the items leave and a driver of the net they enter is no `LEAK`.

## SEAL

`fkcore.route.seal_checks(flat, lay, cat)` walks each sealed module's frame and reports:
a net's carrier standing inside the frame that does not belong to the module; or one of the module's
own nets' carriers standing outside its frame. The route step appends its lines (`SEAL …`) to the
build's report, so a pinned or hand-made crossing shows up.

## Verified

- `tests/test_modules3.py` (8): each port's carrier tile, direction and two roles; the recorded
  carriers in the layout; a portless module stays out of the layout and routes as one block; **a
  sealed module's nets route entirely inside its frame** (every carrier of `rib/fe` and `rib/g` is in
  the 12x8 frame, and `fg`/`in1`/`out` are entirely outside it); **the route meets the port tile**
  (the parent's carrier at (39.5,14.5) faces the port at (40.5,14.5), the module's own at (41.5,14.5)
  inside); **SEAL** reports a stray `fg` belt inside the frame; and **a rib's internal route is
  byte-identical after a parent move** (the same carriers and directions relative to the frame,
  whether the module sits at y 10 or y 60).
- On the example design all five nets route with no `LEAK`, no `SEAL` and no failures: `in1` 19 belts
  + 1 inserter, `fg` 20 belts, `rib/fe` 11 belts + 2 underground ends, `rib/g` 8 + 2, `out` 11 + 1.
- The elaboration baseline over the 42 existing designs is unchanged (no existing design has a sealed
  module), and the full suite keeps only the 170 pre-existing failure/error lines.

## Not in this slice

The lab run of a sealed module through the real paste/revive path (next), and phase 3's remaining
scaffolding (the `--module` build scope and the contract report are phases 4–5).
