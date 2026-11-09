# 43-hull: the achieved hull and the shape example (PLAN-ORGANIC H5, H6, wave 2)

Branch `claude/43-hull`, cut from main 90e20a0 (3.1.4 + wave 1), merged with main 66b8801 (44-levels,
43-mines, 43-hierarchy) before the report. One sitting, 2026-11-09.

## What landed

- **`fkcore/hull.py`** (new, stdlib): `out/frames.json` beside the design, one entry per sealed
  module instance path in the module's own unturned frame: the hull as row runs, its box and area,
  the frame it was clipped to (`source` declared / territory / hull, its area and runs), the
  declared frame's area and size, the corner it stood at, and the build it came from (factory,
  unit key, time). `inside_sha(flat, path)` stamps the entry with the module instance's inside
  (its module, parameters, declared frame, ports, every instance under it with kind, parameters,
  hint, count and Literal signature, every net written in it); the instance's own place is not in
  it, so a moved twin keeps its hull. `Resolver` (bound to the Flat as `flat._hull` and to every
  module `Inst` and `PortInst` as `_hull` by `bind(flat)`) resolves a path **hull, then territory,
  then declaration**: `achieved(path)` reads frames.json when the stamp matches the design now,
  `assigned(path)` reads part T's `out/territories.json` (the cell's runs moved by its corner and
  unturned into the module's frame; read only while the instance's corner hint equals the cell's
  `at`), `frame_for(path, hull=True)` and `source(path)`. The files are read once per Flat: the
  overlay a build reads is fixed for its life (the hull it records is the next build's, never a
  later step's of the same build: that one-entity drift showed up as busbase's pole count).
- **`record(...)`**, the one call in `route._route_layout` after routing: once every unit is
  laid, at the head of the `if sealed_units:` block (`hull_lines = hullmod.record(flat, lay, cat,
  new, sealed, compiled, own_all, failed, store, cinfo)`, then `lines += hull_lines` after the
  compile summary). For every sealed unit with a declared frame, no failed net and no net of its
  own the build did not lay (held, skipped): its entities (owner under the unit) and the carriers
  of its nets and its unsealed scopes' nets (`~net` owners, innermost sealed unit),
  `Frame.from_tiles(...).grow(1 + gap)`, clipped to the unit's claim (`claim_shape_of`: its
  territory or its declaration, the frame its own nets were searched in), moved and unturned
  into the module's frame. Nothing is recorded without a `store` (a bare `route_layout` call in
  a test writes no file). The report: `hull      m: 102 of the 408 tiles of its declared frame
  (25 %), 306 left free` per new or changed hull (at most 12, then `... and N more`), and
  `hull      2 sealed modules in out/frames.json: 1 new or changed` (or `unchanged`).
- **Two frames per sealed unit in the router: the claim and the hull.** A frame is in the unit
  key (`width`, `height`, and `frame` for a tile set) and is the store's coordinate frame, and a
  key must be the same wherever the same inside is built: the lab build, `fk compile` and the
  world build before any hull exists all key the unit before they could know a hull. So the hull
  is **not** the unit's own frame: `expand.claim_shape_of(flat, lay, path, cat)` (new) is the
  unit's claim placed, and `_route_layout`'s frame setup builds `sealed[path]` from it (the
  key, `_UnitTurn`, the store's coordinates, `_fits`, the search box of the unit's own nets),
  while `frames`, `owned` and `owned_shape` (what every other net keeps out of, `try_route`,
  `seal_checks`) stay on `frame_shape_of` (the hull). That is a **second small call into my code
  in route.py**, one line (`sealed[path] = (x0, y0, x1, y1, claim_shape_of(...).tiles())`),
  beyond the brief's one; the alternatives were a hull in the key (every unit re-keyed once,
  `--reuse-lab` and `fk compile` missing the store: seven `test_compiled` failures) or no hull in
  the router at all (the parent's net never through the free ground). A hull frame also keeps
  its **claim's box** (`Frame.boxed`), so `frame_of` and every rectangle reader (the layout's
  extents, a half-turned unit's child boxes in its key) read the claim's box and only the tiles
  are the hull's. Measured on the L (below): build 2 `0 routed, 4 kept`, `hull ... unchanged`,
  nothing stored, one store entry.
- **The readers** (`fkcore/expand.py`): `own_frame(obj)` asks the bound resolver first (a port and
  the scope `fk layout FILE MODULE` lays out read territory then declaration, never the hull;
  `_declared_frame` is the old body); `frame_shape_of` and `planned_shape` go through
  `_placed_frame`: the resolved frame turned about the declared reference box (0, 0, W, H) with
  `Frame.turn(rot, size)` (a declared box keeps the fast path), moved to the corner, a hull boxed
  with its claim. `planned_shape` answers for module instances now (main's `size.fit` reads it:
  does-not-fit judges a module by its tiles, hull first); `planned_frame` stays None for modules
  (it is the box reader). `frame_overlaps` reads hulls through `frame_shape_of`: a corner in what
  a module left free is no `overlap`. `_own_frame` (the reference box for hints and turns) is
  unchanged and binds the Flat on the way. `fk explain` prints, after the declared polygon's rows,
  `territory N tiles (...)` rows when a cell differs from the declaration and `hull      102 tiles
  of the 408 (built alone, out/frames.json; 306 left free):` with the hull as rows of `#` over the
  declared box.
- **`fkcore/frame.py`**: `unturn(rot, size)` (the inverse of `turn`, tiles outside the box too),
  `minus(other)`, `boxed(box)` (a `_claim` slot; `moved` keeps it).
- **`fkcore/layout.py`**, one call in `layout_file` before `build_spec`: `laying_out(flat, module)`
  (module mode lays the inside out in the declared or assigned frame, never the hull; `Spec.blocked`
  is what lies outside it, as before).
- **`agent/docs/examples/shape.fk`** (H6), EXAMPLES.md chapter 6 "The achieved hull: shape.fk"
  (the file, `fk layout shape.fk Mod --write`, the build's `hull` lines, the summary, `fk explain`'s
  hull rows, step 2 with `Side` and the net through the free ground, the one-go build's `overlap`
  line), LANGUAGE.md's `module` row (`size WxH | shape (x,y) ...`) and two Modules rows (`shape`,
  "the frame read"). `tests/test_examples_docs.py`: `SIZES["shape"]`, `LAID_OUT` is a dict (the
  module laid out in module mode), `STEPS` (an example built twice: cut at its marker line, then
  whole; the summary quoted is the second build's).
- **Tests**: `tests/test_hull.py` (9): turn/unturn, `minus`, the L built on paper (the hull is the
  closure of what the unit laid, inside the polygon; the readers resolve it first; module mode
  does not; a turned instance records in its own frame), no-op then change (the hull dropped and
  re-recorded), territory.fk (the cell as the frame, the hulls, the next layout's footprints),
  shape.fk's two steps against the chapter's quotes.

## The numbers

Hull against the frame it was built in (all declared frames, except territory.fk's cells, which in
wave 1 equal the declared boxes):

| design | instance | frame | hull | % | left free |
|---|---|---|---|---|---|
| shape.fk | `m` (hexagon-ish polygon, 24x20 box) | 408 (declared) | 102 | 25 | 306 |
| shape.fk | `s` (6x6 box) | 36 (declared) | 12 | 33 | 24 |
| territory.fk | `a` (8x8, rot 3) | 64 (territory = declared) | 43 | 67 | 21 |
| territory.fk | `b` (8x8, rot 2) | 64 (territory = declared) | 18 | 28 | 46 |
| test L (20x16 box less 10x8) | `ell` | 240 (declared) | 67 | 27 | 173 |

shape.fk, step 2: `gears` runs 24 belts, 14 of them along row 15 inside `m`'s polygon and outside
its hull; `frame_overlaps` is empty. Built in one go: `overlap shape s: port i opens at 12,15,
inside m's frame` and `gears` unrouted (1 unrouted) until the next build.

The L, three builds: build 1 `4 routed`, `hull ell: 67 of the 240 tiles of its declared frame
(27 %), 173 left free`, 1 stored; build 2 `0 routed, 4 kept`, `hull ... unchanged`, 0 stored; the
machine moved a tile inside: `hull.source` reads `declared`, build 3 records a new hull.

## The merge with main 66b8801

`git merge main` after the work: one conflict, `tests/test_examples_docs.py` (43-mines'
`TERRAIN` beside my `LAID_OUT` dict and `STEPS`; both kept). route.py, EXAMPLES.md and LANGUAGE.md
merged on their own. Main's `size.fit` reads `planned_shape` and `own_frame` (43-mines): both keep
their signatures, and `planned_shape` now answers for modules (hull first), so does-not-fit judges
a module by its hull's tiles; `_module_shape` there stays as its fallback.

## Test runs (on the merged tree, 7c736f9)

- `tests.test_frame tests.test_hull tests.test_module_overlap tests.test_size tests.test_compiled
  tests.test_route_units tests.test_design`: 95 tests, OK (36 s).
- `tests.test_layout tests.test_examples_docs`: 31 tests, OK (93 s; shape.fk built in its two
  steps, main's two-round stories of chapters 9 and 11 unchanged by the hull: the claim is the
  key).
- `FK_NATIVE=check python -m unittest tests.test_frame tests.test_hull`: 30 tests, OK; before the
  merge, `FK_NATIVE=check tests.test_layout`: 11 OK (parity unchanged: no Rust touched).
- Before the merge, on 90e20a0 + this branch: the same seven modules plus the docs test green
  after the key fix; the three `test_compiled` failures and `--reuse-lab`'s of the hull-in-the-key
  attempt are what decided the claim/hull split above; busbase's one-entity drift is what
  decided the per-Flat snapshot.

## Decided here (say if otherwise)

- **The hull is clipped to the unit's claim** (its territory or its declaration), the frame its
  own nets are searched in, so a unit's inside may grow back within its claim on a rebuild and
  never a tile lies outside the declared or assigned frame; a no-op rebuild records the same hull.
  A changed inside drops the hull through its stamp until the next build records it again.
- **A second call in route.py.** The brief allowed one; `claim_shape_of` in the frame setup is
  the second (one line). Without it the hull cannot be the keep-out and compile-once hold at
  once (above). Say if the integrator wants it another way: the alternative that keeps route.py
  at one call is `frame_shape_of` returning the claim, with the hull read only by the parent's
  `fk layout`, `frame_overlaps`, `planned_shape` and `fk explain`, and shape.fk's step 2 told
  with `Side`'s port facing out and no net through the free ground.
- **The hull is stamped with the inside, not keyed by position.** The plan said "the build it came
  from"; the entry records that too, but what decides whether a hull is read is whether the module
  instance's inside is as it was built.
- **A unit with a held or skipped net keeps its last hull** (and its key): a player's hand-cut route
  is not what the module achieves, and recording it would re-key the unit when the hold is lifted
  (`test_compiled`'s hand-edit case).
- **Ports read territory then declaration, never the hull.** A used port lies on the hull by
  construction (its inside carrier stands on the frame's edge tile); an unused one keeps its
  declared place. The port readers run at elaboration too, before any Flat is bound.
- **The store does not keep the hull** (`compiled.py` untouched): the plan's "the store keeps the
  hull with the unit" would put a build's output into the key's inputs; `out/frames.json` alone
  serves, one entry per instance.
- **`planned_frame` stays None for modules** (the box reader); main's `size.fit` reads
  `planned_shape` and judges by tiles, which closes wave 1's open item from both sides.
- **The one-go build of shape.fk is told, not hidden**: the docs test builds it in the chapter's two
  steps (`STEPS`), the chapter quotes the one-go build's `overlap` line.

## Open

- A hull is recorded only for a module with a declared frame (`size` or `shape`); a sealed module
  with ports and no `size` keeps its children's box.
- A territory larger than the declared box: the module's own layout box in module mode is still
  the declared box (`build_spec`'s box is `inst.size`); the cell beyond the claim is the frame for
  the router and the parent, not for the inside's layout. Wave 1 cells equal the frames, so
  nothing shows yet.
- **A parent's belt in a polygon's notch re-keys the unit once** (wave 1's rule, seen here): the
  key's `standing` part takes every entity in the claim's *box* (`unit_parts`: `x0 <= e.x < x1
  and y0 <= e.y < y1`), so the L's second build stores a second entry that differs in
  `standing` and `catalog` only (the parent's `gears` belt through the notch; nothing searched,
  its nets stand). The same will happen to a trunk laid through a module's hull-free ground. The
  fix is one line in `unit_parts`, route.py's: filter `standing` by the claim's tiles
  (`sealed[u][4]`), not its box. `tests.test_hull.HullRefinesTest` pins the present behaviour
  (differs in at most `standing`, `catalog`; never `frame`, `width`, `height`).
- `fk lab` / `fk alone` build a copy of the design in a workspace: their hulls go to the
  workspace's `out/frames.json`, not the game's. The world build records every unit's hull itself.
- T1's "a module built alone has its hull as its need": `hull.achieved(flat, path)` is there for
  `territory.build_tspec`; it still takes the declared size.
- `expand.py`'s `@patch` taken tiles (near `_patch_count`) read `planned_frame` boxes, so a module's
  tiles are not taken there; `planned_shape` would give the hull.
- `fk look` draws declared frames; whether it draws hulls was not checked.
- `Record.frame` in `placements.py` is still unfilled.

## Files touched outside part H

- `fkcore/route.py`: one import (`from . import hull as hullmod`, and `claim_shape_of` added to
  the `from .expand import` line), the one call in `_route_layout` (`hull_lines =
  hullmod.record(...)` at the head of the `if sealed_units:` block, `lines += hull_lines` after
  the compile summary), and the second call in the frame setup (`sealed[path] = (x0, y0, x1, y1,
  claim_shape_of(flat, lay, path, cat).tiles())`). No other line.
- `fkcore/layout.py`: `from .hull import laying_out; laying_out(flat, module)` in `layout_file`
  before `build_spec`.
- `tests/test_examples_docs.py`: `SIZES`, `LAID_OUT` (a dict), `STEPS`, the two-step build in
  `paper_build`.
