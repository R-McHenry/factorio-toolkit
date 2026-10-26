# Toolkit 2.0.31: `gears.*` is a sealed module's ports

Rory, 2026-10-25, on the last open ref question: "what are the options for the ref star? Maybe we can
use like a dot or arrow to seperate ports from sub objects." Answered the same day: keep `.`, and let
the star select the ports.

## The options, and why the dot won

- **`.`, star = ports (chosen).** `gears.iron` is a port; `gears.*` its free ports; bare `gears` all
  its ports; `gears.gears` stays refused. Sealing itself is the separator: under a sealed module only
  its ports are nameable, so a ref cannot be ambiguous — the module's port list is the reader's guide,
  as a VHDL entity's is.
- `/` (`gears/iron`, `gears/*`) would have matched the port's internal key and read as "through the
  interface", but it changes every port ref — the plan, PLOT-PORTS' `mall.to_bus`, the bus connection
  list — for readability only.
- `::` (`gears::iron`) reads as interface membership but puts `:` and `::` in one net line.
- `gears.ports.iron` needs a reserved word and longer refs.
- No star at all refuses a convenience the bus base already wants.
- `gears->iron` is out: `->` is already the net's direction and the `set` arrow.

## What the star selects

**The ports that fit the side**, not every port: a driver star takes `out`/`inout` ports, a consumer
star `in`/`inout` ports (an `inout` port fits both). Free-only, as `X.*` always was: a (port, item)
pair already on another net on that side is skipped, and a bare ref adds all of them, exactly the
bare-vs-star difference for an instance. A pair contributes both lanes (both items), filtered by the
net's declared items like any endpoint. Explicitly naming a port stays permissive, so `PORT` can still
warn "used against its direction".

A star that finds no port for its side is refused with the ports listed
(`has no output port: its ports are iron (in iron-plate)`) rather than the unhelpful "names nothing",
and a star that adds nothing because every port is taken is now a `TYPE` line ("takes no … that is
still free"), not a "items disagree" one.

## What did not change

Transparent modules keep `X.*` = their free machines, `size`, sealing, the refusal of `gears.gears`,
the crossing-net split and the `PORT` checks. The elaboration baseline over the 42 existing designs is
unchanged; the suite's 170 pre-existing failure/error lines are identical to 2.0.27's tree.

## Tests (36 in `tests/test_ports.py`)

New: a star is the ports that fit its side (a consumer gets the in port only, a driver the out port);
a bare ref is all its ports; a star is the *free* ports where a bare ref is all of them (the used one
is skipped, and the bare one draws `DOUBLE`); a star takes both lanes of a pair (one net feeding both
items through the pair); a star with no port for its side is refused with the port list.
