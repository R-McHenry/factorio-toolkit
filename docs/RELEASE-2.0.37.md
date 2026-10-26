# Toolkit 2.0.37: a port's approach tiles must be free (phase 3 hardening)

Rory, looking at the sealed-module design on the lab: "there is not a full 3x3 space for the assembler
to fit and it didn't place." He was right, and the cause was two things meeting:

- the rib's declared frame was **12x8** while its `AsmRow<n=1>` is **3x7** placed at `(1, 1)` -- the
  row's belts ran one tile past the frame's south edge, and the port on the west edge's middle row
  put its **inside approach tile** `(1, 4)` under the assembler's 3x3 (tiles 1..3, 3..5);
- `route_layout` routes **from** the port's attach tile, and a job's own ends are exempt from the
  blocked set, so it laid the route's first underground **on the assembler's tile** -- the paste then
  could not revive the machine and the design was built without it.

## The fix

- `fkcore.route.port_checks(flat, lay, cat)` reports a port whose **inside or outside approach tile**
  is taken by something that is neither the port's own carrier nor a route: `PORT rib.iron: its
  inside tile 41,14 is taken by rib/g/m0`. The route step appends those lines next to `SEAL`, so the
  problem shows up at build time instead of as a missing machine in the world.
- The example fixture (and the design pasted on the lab) now declares `size 16x10` with the row at
  `(2, 1)`: the row (3x7 at (2,1)) and the assembler (3x3 at (3.5,4.5)) sit clear of the ports at
  `(0,5)` and `(15,5)`, and `port_checks` is silent.

## Verified

- `tests/test_modules3.py` (9): the new test takes the tight 12x8 fixture and asserts the `PORT` line
  names the port and the assembler; the corrected fixture routes with no `SEAL`, no `PORT`, no
  failures and **no entity shares a tile with the assembler's 3x3**.
- Lab: the corrected design pasted **92 ghosts, 92 revived, 0 failed**, the assembler standing valid
  at (963.5, 651.5) with its full 3x3, 0 ghosts left.
- Full suite keeps only the same 170 pre-existing failure/error lines as the 2.0.27 tree; the
  elaboration baseline is unchanged.

## Note for module authors

A sealed module's frame must leave the port's approach tiles free: a machine (a 3x3 assembler in
front of the port, say) on either approach tile is now a `PORT` line, and the route will run through
it if it is built anyway.
