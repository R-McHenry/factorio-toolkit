# 3.0.3: one toolkit again

3.0.3 is the recovery release of 2026-11-08 (`..\assessment-20261108\RECONCILE-20261108.md`): the
lab's branch `claude/lab-30` merged onto main, the version strings made consistent, and the rules
that let the toolkit fracture taken out of `CLAUDE.md`. Read against main `b08c955` + this commit.

## What changed

- **The lab's megahub work is on main** (`claude/lab-30`, 12 files, +408/-53, written 11-07..11-08
  on 3.0.2):
  - circuits: a gated net with no inserter or pump is switched at its trunk belt, the first belt
    every head reaches, so a production switch can sit on a belt (`fkcore/circuits.py`,
    `tests/test_circuits.py`);
  - rail signals: 25-tile rail-signal blocks along a segment (`fkcore/railsignals.py`,
    `tests/test_rail_signals.py`);
  - compiled keys leave out rails other modules own, so a bay's compiled route survives a grid
    change beside it (`fkcore/route.py`);
  - `FK_RCON_TIMEOUT` sets the RCON timeout (`fkcore/link.py`);
  - `fk lab NAME --keep`: lay over what stands and route only the stale nets (`fkcore/lab.py`,
    `tests/test_lab.py`);
  - cover and flow fixes (`fkcore/cover.py` +199, `fkcore/flow.py` +62, `tests/test_cover.py`).
- **Version strings.** `fkcore.__version__` is `3.0.3`; `route.COMPILE_VERSION` is `route-3.0.3`
  (it was `route-3.0.2-lab` on the branch) and `compiled.ROUTER` is `3.0.3`. Every compiled module
  and stored inside is laid once more on its next build.
- **`CLAUDE.md`:** the full test suite is no longer demanded before a merge (Rory, 11-08: never
  run it; targeted modules only). Main is the only integration point, the `v5` folder stays on
  `main`, release numbers are assigned on main at merge time, and whoever merges updates
  `..\STATE.md` in the same commit.

## Not in this release

- Nothing is migrated (Rory, 11-08). The live Opus run stays on 2.1.30, the runner on its vendored
  2.1.30 copy, old saves and designs are reference.
- The lab is still a mode in the toolkit (`surface.mode == "lab"` in `apply.py`, `flow.py`,
  `surface.py`; `fkcore/lab.py` 750 lines; `fk lab`, `fk capture lab`; ten `tools/lab_*.py`).
  Rory, 11-08: a lab is just another game surface where things are free, with a source and docs
  like any base; no planet gets toolkit machinery of its own. Taking the lab mode out is the next
  design item, with PLAN-BUILD's placements and the fluids plan.
- Open from 3.0.1: one compile store; the Rust kernel learning 3.0's tap rules.

## Upgrading

A run pins this commit as any other (`kickoff/upgrade_run.py`). The lab run `lab-session\fk-run`
pins `1635ebf` plus the lab-30 files, which is this release minus the version bump; its scripts
now import `..\v5` (main) instead of the `v5-lab30` worktree.
