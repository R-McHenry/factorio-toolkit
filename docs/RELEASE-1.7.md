# Toolkit 1.7 (2026-10-21): rebuilds keep what stands, and the round-2 pieces

Rory's decisions after the first V1 runs (`assessment-20261021\ASSESSMENT.md`, "Decided with
Rory"), the pieces that don't need a session of their own. No new rules: checks warn, never gate,
and the brief stays as short as it was. 554 tests OK.

## Pin and patch: a rebuild that doesn't cut power

Rory: "Pin what stands and make patch changes rather than regenerating the base. The toolkit was
meant to support this, so find out why players didn't use it." What the runs' play.log, NOTES and
FRICTION showed:

- Routes were already pinned (`route --only stale`: a net whose ends did not move keeps its belts).
- The covers were not. `cover power` laid every pole anew on each build, and greedy cover with a
  shifted centroid put them elsewhere: a new grid on every rebuild, and the old poles went before
  the new ones stood. `cover robots` moved roboports the same way. Both overnight players lost
  power and robots to it.
- `fk build --to diff`, the players' dry run, ran `write_layout`: the design they tried became the
  one the next build kept to, so a tried-and-dropped change re-routed nets that stood.
- A net whose ends change (a consumer added) is routed again as a whole (not changed here, below).

What changed:

- **`cover power` keeps the committed poles** (`fkcore/cover.py`, the flow passes the committed
  `.fkp`'s own `power/p<k>`). A pole stays where its spot is still free (no new entity or terrain
  under it) and the pole type is the same; new poles go only where coverage is missing, numbered
  after the kept ones. A standing pole goes only when it powers nothing and joins nothing; a new
  pole never replaces one. The bridges laid to a pole that went are looked at again. On the
  redgreen game, labs moved 2 tiles down: 37 of 40 poles stay (a fresh lay kept 32 of 39 in
  place). `out\cover_power.txt` says "N kept where they stand"; `cover power --fresh` lays them
  all anew, as before.
- **`cover robots` keeps the committed roboports** (`fkcore/robots.py`) that still fit and still
  reach a chest of the factory, and the storage chest beside each where it still fits; new ones
  only where no kept one reaches. `--fresh` as for power.
- **Scaffolding, the accepted fallback** (`fkcore/apply.py` `scaffold`): an apply leaves a
  `NOBODY` pole or roboport that stands on no tile of the design up while the design's own poles
  (or roboports) in its area are not all built; the first apply after they stand takes it up. One
  under a design tile goes at once (the paste needs its ground), and so does an old ghost (a
  `Verdict.ghost` flag). `out\apply.txt`: "scaffold: N old poles and roboports stay up until the
  design's own stand here". The own record keeps them meanwhile, so they stay `NOBODY`.
- **The template writes the design just before the paste**, after `diff` and `report_bom`: `fk
  build --to diff` is a dry run that writes nothing. `fk build` runs `write_layout` on the host
  now (the split is still at the first game step) and pulls the `.fkp` files back.
- TOOLKIT.md: "Rebuilds keep what stands", patches are cheap, `--to diff` writes nothing.

## The rest of the round

- **`docs\STRATEGY.md`**: the strategy guide from the assessment, as is, pointed to once from the
  brief ("what worked in earlier runs: advice with reasons, use what fits your map").
- **Fair play in Rory's words**, in the brief and TOOLKIT.md: a process over time that can be
  automated in the game belongs in the game (circuits, a mall), not in a script; a script may do
  one specific multi-stage build action, never manage the base or keep everything stocked through
  one-off crafters. Helpers grow in `helpers\` as a library.
- **The kit stays small, plus 10 burner mining drills** (`kickoff/setup_v1.py`): a player that
  spends its plates first can still mine. `MinerRow<drill=burner-mining-drill, fuel=coal>` has its
  own geometry now (2x2 drills in a one-sided row, a fuel belt north, one inserter per drill; it
  took the parameters before but laid 3x3 electric positions and failed).
- **`fk fresh` takes up a crafter's old product** (`link.lua_stale_crafters`): an assembler whose
  output holds what its recipe no longer makes, and a chest its crafters' inserters fill holding
  what none of them makes now (a chest also fed from a belt or a chest is left alone: what belongs
  there is unknown). Robots carry the contents to storage; the next build lays them again.
  Recipe-switch smarts beyond that belong in circuits in the game, not in toolkit scripts.
- **Labs from a chest**: `Lab<rate=>` is one lab whose inserters the router lays, so labs around
  one multi-item requester take their packs by one inserter each (`sci: 1 -> 3, 3 inserters
  (direct insertion)`, no belt). One inserter into an all-accepting multi-sink raises no `CLOG`:
  a sushi net whose every consumer is a chest that takes any item. Into machines, or labs on a
  mixed belt, it still does. Daisy-chained labs and turrets wait.
- **Mixed chests** (assessment decision 7): `SUSHI_LIMIT` for a `limit=` on a chest a mixed belt
  of makers feeds (a full chest stops the whole belt; the limit belongs at each maker); such a
  chest gets its own `UNLIMITED` line instead of the plain one that told the player to add that
  limit; `net NAME limited:` says the source limits each maker, which silences `CLOG` and
  `UNLIMITED` for it and implements no limit. The compact-mall example loses its `limit=16`.
- **Helpers** (`kickoff/template/helpers` -> `<run>\helpers`): a README (what goes there, fair
  play), `python -m helpers [FEATURE]`, `game.lua()` through the run's own `fk lua`, and four seed
  probes the first players wrote again and again: grids, machines, stock, labs.
- `kickoff/upgrade_run.py` 1.7: the build script's `write_layout` moves before `apply`, a run
  without `helpers\` gets the template's, and TELL says what changed.
- The four merged worktrees under `.worktrees\` are removed (their branches `bus`, `size`,
  `fk-plan`, `fix-141` stay, all contained in main).

## Deploy

Nothing is deployed and nothing runs in the game: Rory starts the next run. A new run from main
gets all of it from the kickoff (the kit, the template's script and helpers, the docs and brief).
The host toolkit must be this commit too, as the kickoff deploys it (`fk-v5-SHA`): the host runs
`write_layout` now. An old run would need `upgrade_run.py` (only with Rory's approval).

## Not in 1.7

- The three large pieces of the round, proposed as sessions of their own and not started yet:
  V2 in full (lane-pair belts, thick and main buses with the backbone of fixed poles and
  roboports, side-loading smelter arrays, throughput players lean on), circuits in the source
  (wire nets, conditions, inserter limits instead of malllimits.lua-style scripts), and the lead
  and worker player harness (Claude or DeepSeek workers; a Claude lead sees only a DeepSeek
  worker's final output).
- Route patching: a net whose ends change is routed again as a whole. Keeping its laid belts and
  routing only the new branch into them is a router change of its own.
- The pace tool (optional): science-per-minute targets per tech tier from the speedrun times.
- Daisy-chained labs and turrets.
