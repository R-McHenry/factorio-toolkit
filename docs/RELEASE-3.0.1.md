# 3.0.1: origins, and the review's fixes

3.0.1 fixes what the independent review of 3.0.0 found
(`assessment-20261108\REVIEW-3.0.md`), and adds Rory's rule from 2026-11-08: coordinates hang
from origins, never from an edge or a corner.

## Origins, not edges

- **`@(x, y, rot r)` puts the instance's own origin at (x, y)**, its (0, 0), and turns its contents
  r quarter turns clockwise about that point. Until 3.0.1 the turned frame's top-left corner landed
  on (x, y), so a turned row or module that grew (one more drill, a wider cell) moved everything
  in it. Now nothing that stood moves. A turned 180 row lies up and to the left of its (x, y).
  - Unturned placements are unchanged.
  - A single machine (a chest, a pump, a turbine) has no frame to grow: its (x, y) is still its
    top-left tile at every rot.
  - Turned plots in a root design turn about their origin too.
- **A Literal's origin is its file's (0, 0)**, not its top-left entity. A blueprint that grows west
  or north keeps every entity where it was, and several Literals cut from one capture, at one
  `@(x, y)`, sit as they stood.
- **`fk capture` from the design** writes positions relative to the instance's own origin, so the
  Literal at the instance's `@(x, y)` lays the same tiles. A capture from the game keeps world
  positions, and its (0, 0) is the map's.
- **`fk migrate-origins FILE [--write]`** rewrites a design written before 3.0.1, and the files it
  imports, so it lays exactly what it laid. It reads the design the old way, then writes each
  turned instance's (and each Literal's) origin hint on its own line. A module that two instances
  would want written two ways (a parametric frame) gets the first one, plus a note.
- **The corpus is migrated.** The examples, games, templates and golden designs have 22 files
  rewritten. The golden check of the migrated corpus against 3.0.0 is 60 of 62 identical. The two
  live worlds differ only in the routed-rate table, whose solver stops at a different round from
  one run to the next; their elaborate and layout sections are identical.
- A turned instance whose frame can't be known is placed by its corner and says so: check
  `by-corner`.

A run that upgrades to 3.0.1 must run `fk migrate-origins` on its design first. Without it, every
turned row and every Literal whose file doesn't start at (0, 0) moves.

- **A turned `n=auto` row is migrated at the count its layout (`.fkp`) holds.** From then on it
  grows away from its origin, so a later count lays it differently than 3.0.0 would have. That is
  the point of the change. Without a `.fkp` the migration uses the count elaboration starts from,
  so check a turned `n=auto` row near a plot edge (`does-not-fit` says "a negative corner").
- `does-not-fit` and the other size lines name a row by its `@(x, y)` as written (its origin, and
  its rot).
- **The lab's own generators** (`lab-session\baygen.py`, `netgen.py`, `slotin.py`) write turned
  bays by their corner. They run on the lab's own toolkit copy and are not changed here. When the
  lab moves to 3.0.1, they need the same rule: place a turned bay by its origin.

## The review's fixes

- **Both compile-once stores laid again.** `route.COMPILE_VERSION` is now `route-3.0.1` and
  `compiled.ROUTER` is `3.0.1`. Modules stored by the 2.1.31 or the 11-01 3.0 router are routed
  again once (the lab's `out\compiled` held 54).
- **A world net's group try lifts only the modules it enters.** In 3.0.0, the top level counted
  every sealed module as nested, so a failing world net that ran beside a bay lifted the bay's
  belts and laid them again. Now a nested unit's nets are lifted only when the failing net's way
  enters that unit's frame, or the net ends on it (a routing.fk Waypoint's port).
- **`FK_NEGOTIATE=1` goes through route-once.** 2.1's pass loop is gone. Negotiation now proposes a
  unit's routes, and each proposal is laid when its net comes up, if it still fits the ground. So
  seeds, held nets, the failure memo and the group budget apply to negotiated nets too. A seeded
  or remembered net is not negotiated.
- **`fkcore.__version__` says 3.0.1.** 3.0.0 still said 2.1.34.
- New tests: `tests.test_route_units` (a world net beside a module, negotiation through route-once,
  a seed not negotiated) and `tests.test_origins` (turns about the origin, a module that grows,
  nested turns, single machines, Literal file origins, migration equivalence). All of them fail on
  3.0.0 and pass on 3.0.1.

## Still open

- One compile-once store instead of two (the review recommends the router's as the base).
- The Rust kernel learning 3.0's tap rules (29 % of `tests.test_route`'s grows fall back to Python).
- Re-bench the megaloop route on 3.0.x against 2.1.34's 101 s / 57 s.
- `claude/lane-physics` (cut from 2.1.34) to be moved onto 3.0.1.
- PLAN-BUILD (`assessment-20261108\PLAN-BUILD.md`).
