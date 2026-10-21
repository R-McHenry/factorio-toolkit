# Toolkit 1.3 (2026-10-20): V2's first round, throughput on the routed layout

The first V2 pieces (`CORE-V2.md`, decided with Rory on 2026-10-20), merged from branch `v2`:
the build now says what the belts and inserters as laid let through, and can lay a faster belt
where yellow is too thin. There are no new rules: the `tier` step's default keeps every belt yellow,
and `CAPACITY` is a warning.

## New

- **Routed rates.** `report_rates` runs again after `route` in the default build script
  (`fkcore.routed`, on the flow solver `fkcore.throughput` over a lane graph `fkcore.lanes`). Per
  instance it gives the nominal and the routed utilization and the slowest machine; per net what
  its consumers asked and got and its critical connector; and the routed rate of every surface
  target. The solver follows the lane rules measured in the game (`docs/LAB-LANES-20261020.md`):
  the first machines along a belt are served first, splitters split evenly and send what one side
  refuses to the other, a side-load squeezes both lanes onto one, an underground side-load passes
  only its open side, a splitter half carries one lane. `--hand N` gives the force's inserter hand
  size (1 on paper).
- **`CAPACITY`** (a warning): a net delivers less as laid than on paper while some of its belt
  lanes, splitters or inserters run full. The line says what the design asks there, what they
  carry, and which machines run short.
- **The `tier` step**, after `route`: `tier minimize` gives each belt, underground pair and
  splitter on a net the slowest allowed tier that carries what the design asks; `tier maximize`
  the fastest allowed everywhere; `--allow yellow,red,...` the tiers it may use, `--red 10` at
  most 10 red. The kickoff template has `tier minimize --allow yellow`: nothing changes until the
  player allows red, so no locked belts are ghosted.
- **A module instance's `rot` turns its whole contents** (`fkcore.expand`, a V1 bug found on the
  way: `c = IronWorks @(40, 0, rot 2)` used to land unturned).

## Checked

- 404 tests at the merge, plus the module fix's (`python -m unittest`).
- The lane rules and inserter rates on a laptop test server (2.0.77, `tools/lab_lanes.py`).
- Rory's two designs against the solver, built on a laptop test server: his 4-to-4 balancer in 7
  setups and his smelter stack in 3 (`games/v2-bench`), all within 2%.
- `games/redgreen` as laid delivers its nominal rates: no `CAPACITY` line, `tier`: 0 changed.
- Rory's join case, several iron works and consumers on one net (`games/v2-bench/join-*.fk`): it
  routes as a hub; at 15/s the one-lane trunk delivers 7.5 and `tier minimize` carries all 15.

## Compatibility

Nothing a build writes changes while the script keeps every belt yellow: a running run's build
script has no `tier` line and runs `report_rates` before `place`, so it reports exactly as 1.2. To
see the routed rates there, add `report_rates` after `route`; to allow red belts, add
`tier minimize --allow yellow,red` after `route` (`kickoff/upgrade_run.py` prints this for the
player).

## Open

`CORE-V2.md` ("Open", "V2.1 next"): the lane notation in the `.fkp` and the `LANE` check; multi-lane
nets by bus templates or a bus router; proper distribution in a k-to-m hub; a joint solve of
several items on one lane; the catalog's inserter speeds and the force's hand sizes from the game.
