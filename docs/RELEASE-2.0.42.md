# Toolkit 2.0.42: a pin beats a recorded port tile, pins count from 0

Review of 2.0.41 (PLAN-GLOBAL phase A), 2026-10-26. Phase A's three items work: a 15/s crossing
through an `X | X` port, a tile facing its partner, the record kept across a parent move. Three
things around the record did not, and are fixed here.

## 1. The pin wins (2.0.41 said so and didn't)

A committed record was read before the pin, so a source that pinned a port to another tile kept
the carrier on the old one. The `PORT` line said "the pin wins (a rebuild records 0,1)", but the
rebuild recorded the old tile again, so the line came back on every build.

Now a record that disagrees with the pin is dropped: the carrier goes to the pinned tile, the
`.fkp` records it, and the line is printed once:

    PORT      rib/iron: the committed tile 0,4 is dropped: the pin @w2 moves it to 0,2

## 2. A port moved to another side is chosen again

A port changed from `@w` to `@n` kept its west-edge record silently, with no line at all. A record
must now stand on the declared side's edge of the frame as it is now (the side, and a frame that
shrank under it); otherwise it is dropped and the tile chosen again, facing the partner:

    PORT      rib/iron: the committed tile 0,4 is dropped: it is not on the n edge of the 16x10
              frame: the port is chosen again

`expand.record_misfit` is the one rule; the build and the `PORT` check both use it.

## 3. A pin counts from 0

The `PORT` check (2.0.28: "its w edge runs 0..9") and the docs (2.0.29: `@n0L`) count a pin's tile
from 0, but the layout placed it at `pos - 1`. So every pinned port stood one tile before its pin,
and `@w0` failed with "off the frame". The layout now counts from 0 as well, and LANGUAGE.md says
so. **A design that pins a port moves that port one tile along its side**; no example or game in
the repository pins one (only tests did), and no run uses ports yet.

## Verified

- `tests/test_ports2.py` (15, +3): the pin moves the carrier and the record, and the next build has
  no `PORT` line; a port moved from `@w` to `@n` lands on the north edge with one `PORT` line;
  `@w0` is the side's first tile. The pinned-tile and disagreement tests moved to 0-based tiles.
- The full suite: **960 tests, OK** (957 before, plus 3).
