# Toolkit 2.0.39: `route --module X`, a sealed module's patch scope (phase 4, closed)

PLAN-MODULES phase 4's second half: a rebuild can be scoped to one sealed module. Changing a rib
re-routes **its frame and the parent nets ending at its ports**, and every other committed route goes
to the router as it stands (the patch machinery of 2.0's "pin what stands"), so a rib change never
moves the rest of the base.

## What the scope is

`fkcore.flow._module_pinned(flat, previous, cat, path)` returns the patch the router wants:

- **routed again**: every net of X's own (its scope's name or under `X/`, e.g. `rib0/fe`, `rib0/g`)
  and every parent net whose end is one of X's ports (the bus tap that feeds the rib, the chest net
  its gears go to);
- **pinned as it stands**: every other committed route from the previous `.fkp` — a second rib's
  internal routes, its tap, its output, the mouth feeding the bus — byte for byte where it was.

`route --module X` is the build-script spelling (`s_route` takes the option); the route step then
reports the same counts as ever, with the pinned routes in `patched`/`kept`.

## Verified

`tests/test_module_scope.py` (3):

- the scope is exactly `rib0/fe`, `rib0/g`, `r0` and `g0` for a moved rib0, while `rib1/fe`,
  `rib1/g`, `r1`, `g1` and `in1` are pinned;
- after moving rib0 down three tiles and rebuilding in that scope, **rib1's four routes carry the
  same keys, belts, tiles and directions as before**, rib0's `r0` moved, with no routing failure and
  no `LEAK`, `SEAL` or `PORT`;
- a name that is not a sealed instance reports nothing and pins everything (the call is a no-op).

The full suite keeps only the same 170 pre-existing failure/error lines as the 2.0.27 tree, and the
elaboration baseline is unchanged.

## Phase 4 is closed

The contract report (2.0.38) and `--module X` (this release) are both in; the plan's phase 4 is done.
Phase 5 (the surface link on the same ports) and 2.1 (the pair bus) are next.
