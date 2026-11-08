# 2.1.31: the megabase bays in the lab, and sealed modules compile once

Two pieces of work on `claude/lab-megabase`: the fixes the megabase bays needed in the lab
(lab-session\fk-run\FRICTION.md, entries marked "Fixed in 2.1.31"), and PLAN-3.0 §4, sealed
modules compile once.

## Sealed modules compile once (PLAN-3.0 §4)

The lab megaloop (two bays as sealed blocks: 302 sealed units, 1364 nets, none outside them)
routed every unit's nets as one todo list in one pass loop. One net that failed anywhere made
every pass lay all 725 belt nets again, and twin modules (each bay's two chains, 296 cells) were
each searched on their own.

- **Compile units.** `_route_layout` routes per unit: each sealed module's own nets (those whose
  innermost sealed module it is) in passes of their own, innermost first, then the nets outside
  every sealed module. Retries and the promoting pass stay inside the failing net's unit;
  `retries` counts passes per unit.
- **Twins.** A unit's compile key hashes `COMPILE_VERSION`, its frame's size, the instances placed
  in it, every entity standing in it (its children's routes included), the terrain in it, and
  each own net's ends and items, all relative to the frame. A unit whose key matches a unit laid
  whole earlier in the build takes that unit's routes, moved and renamed to its own nets
  (`_moved_routes`). They are laid only on free tiles (`_fits`), and `_repair` judges them as it
  judges any route.
- **The store.** A unit routed whole is written to `<store>\<key>.json`: the route step's
  `--store DIR`, by default `out\compiled` beside the build script. `fk lab` uses its game
  folder's, so the world build lays a module the lab routed, wherever it stands now.
  `--store none` lays every module afresh. A stored module of another `COMPILE_VERSION` is laid
  again.
- `out\route.txt` has a `compile` line (units, nets, laid as a twin, from the store, stored), and
  a reused net says `laid as ... (compiled once, PLAN-3.0 §4)`.

## The lab fixes

See FRICTION.md 1, 4-7, 9-13, 17, 21-23, 27, 28: the lab's own build script (`lab.build.fkb`,
`--with`), `tier maximize --all`, a paired port's nets by both items, lane-pair joins off
underground entrances, `get_fluid_contents` on 2.1.24, the fastest loader for open ports,
`fk capture world --surface/--force` with world positions and boxes in world tiles, shared rail
tiles, a Literal's own edges, a Literal's combinator as a wire end, Literal pole colours, one
parse per imported file, the lab keeping its .fkp files, and a revive that skips invalid ghosts.

## Checked

- tests/test_compile_once (new): twins, nested twins and their parents, another ground laid
  alone, the store across builds and positions, the version check, the free-tile check.
- tests: the 46 route and sealed-module modules (643 tests), then the whole suite.
- The megaloop's route step, offline from its placed layout (no game, `--effort normal`, nothing
  pinned), 1280 nets each time, 0 failed:

  | router | time | passes | modules |
  |---|---|---|---|
  | 2.1.30 | 495 s | 4 of all 725 belt nets | - |
  | 2.1.31, empty store | 101 s | per module | 15 routed, 287 as a twin |
  | 2.1.31, store filled | 57 s | 1 | 302 from the store |

  Both 2.1.31 layouts equal 2.1.30's entity for entity (keys, positions, directions, attrs),
  with no invariant problem. What is left in the 57 s is mostly the fluid nets (49), which
  compile units don't cover yet.
- Found on the way: a lane pair's inserter is written `a+b` and its belts `a|b`; a moved route
  first wrote every carrier's `net=` as the job's name (`a|b`), 105 invariant lines on the
  megaloop. A moved carrier now renames its own `net=` (`_moved_entity`, the store too).
