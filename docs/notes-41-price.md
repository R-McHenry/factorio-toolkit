# 41-price: prices from the router (PLAN-ORGANIC part R: R1 to R3)

Branch `claude/41-price`, cut from main `cfb10f0` (3.1.4, fkroute 0.4.0). Measured 2026-11-09 on
this laptop, fkroute built from the tree (`python tools/native_build.py`). The layout's potential
learns from the real router: the lane fact a relaxation cannot see (R1), and what a built design
actually cost and fought over (R2), so the loop `fk layout --from out --write`, `fk build` can run
by hand (R3).

## What landed

### R1. The pair stem (`d99cda5`)

- `fkcore/lanephys.py`: `STEM = 3`, the room `pairs.joins` demands of a trunk root (its back,
  itself, the belt ahead; none the consumer's end): the one place the number is written.
- `fkcore/layout.py`: `SpecNet.stem` (default 0), `_State.stem_of` per consumer belt end, rule 5
  in `usable` (a `lanes A | B` pair's consumer belt end keeps `stem` free tiles straight beyond it,
  none another's belt end; the group's index is passed, not its tiles), `build_spec` fills
  `lanephys.STEM` for pair nets, the kernel takes `stems=` as an optional argument (the old shape
  still works).
- `native/fkroute/src/place.rs`: the same, step for step (`FK_NATIVE=check` parity holds).
- `tests/test_layout.py`: `StemTest`, parity on random specs with pairs, `GroveTest` (the bar),
  `tests/data/grove/` (grove.fk + flowercells.fk, a copy of fk-run2's).

### R2. Real costs and the negotiation's history as the start (`fk layout --from [OUT]`)

- **Real carriers per net** come from the design database's net files
  (`out/design/<factory>/nets/*.net`, `fkcore.design`: the status and the carriers the route step
  wrote per net), the same reader at the top level and in module mode: the spec's net names are
  the files' (`fe`; `g/cu0_|g/fe0_`). A routed net counts its belts, underground ends and
  splitters (0 when its ends met and nothing was laid: the mall's `cu`, `cab`, `inss`); an
  unrouted, held or skipped net, or one the build never saw, keeps its estimate and the report
  says so. The WIP's two readers (a module's unit from the compile store, the top level from the
  `.fkp` beside the file) are gone: the `.fkp` counts an instance's own belt (the mall's AsmRow
  has 12) as if it were a net's, and the store holds no net whose ends met.
- **The negotiation's history** (`route._negotiate`'s `hist`, the tiles clashing nets fought over,
  and the last round's `pres`) is kept per compile unit as `out/design/<factory>/pressure.json`
  (`design.write_pressure`, written by the route step from the new `Routed.pressure`): per unit
  path (`''` the top level) the store's module and key, the frame, the rounds, and
  `[x, y, hist]` tiles in the unit's own unturned frame, the store's terms (`_UnitTurn`). It is
  written when the step negotiated (FK_NEGOTIATE=1 is still the opt-in), left alone when a step
  laid nothing (every route kept: the fight that laid them still stands) and removed when a step
  laid routes without negotiating. `fk layout --from` seeds the price field from it:
  `Spec.price = [((x, y), alpha * hist)]`, `Params.alpha` (what a sweep adds per belt of overuse)
  per round a tile was fought over; Python and the kernel (`price=` optional) take it alike.
- **`--from` moves the placed instances** (as `--all`): a round of the loop re-prices and nudges
  what the last round placed; with every instance hinted, nothing else would move. A Literal, an
  `@patch` row and an instance no net pulls stay fixed as before.
- **The report** (the long path and the doubled arrow are gone):

  ```
  from out/design/layout/nets: 8 of 8 nets routed by the last build; 11 tiles fought over in 8 negotiation rounds seed the price field
  per net, real -> estimated: belts 4 -> 0, cab 0 -> 0, circs 5 -> 0, cu 0 -> 0, fe 36 -> 3, gears 12 -> 0, inss 0 -> 0, pipes 2 -> 1
  real belts 59 -> estimated 4 over 8 nets; every net reaches its consumers; 0 hot tiles; 4 sweeps
  ```

  Without a negotiation record the first line ends `no negotiation record (a build with
  FK_NEGOTIATE=1 writes design/layout/pressure.json): the price field starts at zero`; a net left
  out is named with its status (`fe (unrouted) keeps its estimate`); an `OUT` with no build of the
  file says `no net of layout was built there`.

### R3. The loop, by hand

`fk layout FILE --write`, `fk build`, then `fk layout FILE --from out --write`, `fk build`: the
tool never runs the build (each tool consumes the previous one's output). `LoopTest` runs the two
rounds on the mall (`agent/docs/examples/layout.fk` with its hints stripped, plot 34x44) in a temp
dir with FK_NEGOTIATE=1, checks the record and the report, and asserts the second build lays no
more of the nets' carriers than the first.

## The numbers

| case | `fk layout` | build | `--from out` |
|---|---|---|---|
| mall.fk (11 instances, 8 nets, 34x44) | 11 placed, estimated 62 -> 4, 13 sweeps, 0.7 s | **52 carriers** (the nets' 40; 12 are the AsmRow's own belt), 8/8 routed, 91 entities, 2 underground pairs | real 40 -> estimated 4; 0 placed, 11 kept (a local optimum: nothing moves); the second build keeps every route and patches `circs` 10 -> 9: 51 carriers (the nets' 39) |
| mall.fk, builds with FK_NEGOTIATE=1 | the same layout | 71 carriers (the nets' 59: `fe` 36, `gears` 12), 3 underground pairs; pressure: 11 tiles fought over, 8 rounds (the cap), pres 128 | real 59 -> estimated 4; the 11 seeds (0.5 tile each) move nothing; the second build keeps every route, patches `fe` 36 -> 35 and `gears` 12 -> 11: 69 (the nets' 57) |
| grove.fk `Grove` (4 Stacks, 6 beacons, 12 ports; module mode, 46x40) | 4 placed (c0..c3 at y 15/15/14/11), estimated 56 -> 74, 150 sweeps, 26 hot tiles | **236 carriers, 76/76 routed** (hand layout 256, 76/76; 3.1.4: 68/76), 422 entities, 0 underground pairs | Grove's 8 nets real 68 -> estimated 71 (the Stacks nudge to y 14/13/13/15; not written by the test); with FK_NEGOTIATE=1 the record has `g` (Grove, its key) and `g/c0/0` (GreenB), 1 round, no tile fought over |
| line11.fk (18 instances, 12 nets, 44x11; `--all` from its hand hints) | 18 placed, estimated 299 -> 46, every net reaches its consumers, 12 hot tiles, 150 sweeps, 3.5 s | not built here (its paper build stops at floorplan; 40-layout counted 94 carriers against 179 by hand, 12/12) | no pair, no `--from`: R1 to R3 change nothing for it |

The two-round mall numbers for the docs example (wave 2 writes the text): round 1 `estimated
belts 62 -> 4`, build `52 belt pieces` (the nets' 40); round 2 `real belts 40 -> estimated 4`,
`0 placed now, 11 kept`, build 51 (the nets' 39, `circs` patched). The negotiated pair is 71 ->
69 (the nets' 59 -> 57).

Tests: `tests.test_layout` (23: PlaceTest, StemTest, PriceTest, ParityTest with prices and check
mode, HintLineTest, CommandTest with `--from`, GroveTest with `--from`, LoopTest, ExampleTest),
`tests.test_route_units`, `tests.test_compiled`, `tests.test_compile_once`, `tests.test_design`,
`tests.test_native`: green. The docs quote (`ExampleTest`) is unchanged: `fk layout` without
`--from` prints what it printed.

## Decided here (within the plan; say if otherwise)

- The real carriers come from the net files, not the compile store or the `.fkp` (above).
- The history is a design-database record (`pressure.json`) beside the net files, one per factory,
  keyed inside by the store's module and key, rather than a file in the store: the top level has
  no unit key, and a `.json` in a store folder would count as an entry (`compiled.modules`).
- The seed is `alpha * hist`: one round a tile was contested counts as one sweep of one belt's
  overuse, in the Lagrangian's own units. On the mall that is half a tile per tile and moves
  nothing; `pres` (128 after 8 rounds) is recorded but not used, it would be 64 tiles a tile.
- `--from` implies `--all`.

## Open

- The seed's strength: the mall's 11 contested tiles at half a tile each push nothing; whether
  `hist` should be scaled (by the rounds, by `pres`, or by the net's weight) wants a case where
  the negotiation's fight is real (the mall's negotiated routes are worse than its plain ones:
  71 against 52 carriers, `fe` 36). R4's lane-search prices (`claude/40-lanes2`) are the planned
  source.
- Negotiation is still FK_NEGOTIATE=1 opt-in: a plain build leaves no record, and `--from` then
  reads the real carriers only.
- A round that moves nothing builds the same: every route kept, patches only. The loop's gain is
  where a build's real costs disagree with the relaxation (grove: the pairs 10 real against 12-14
  estimated); the real router as the inner evaluator of the last sweep (R4) is where that goes.
- The grove test does not write the `--from` round's nudge (c0..c3 to y 14/13/13/15, estimated
  74 -> 71) and build it; the hand-only loop on a module is untested beyond the report.
- `fk layout --from` reads one factory's files (`flat.name`); a surface with the module placed
  twice, or a world build, is the territories' wave.
