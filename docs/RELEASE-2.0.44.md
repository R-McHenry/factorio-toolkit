# Toolkit 2.0.44: one file holds several plots again, and a migration that loses a plot changes nothing

Review of 2.0.43 (PLAN-GLOBAL phase B), 2026-10-26. Phase B works on run 1343's world: a copy of
its game folder, built with 2.0.43 before and after `fk migrate-surface`, gives the same 2187
composed entities row for row, and every `.fkp` byte-identical. One thing did not carry over from
`place` lines, and the migration did not notice.

## 1. Several plots of one file

`place` lines could place one file many times, each plot its own factory reading the file's `.fk`
and `.fkp`. Run 20261021-0110 placed `relay.fk` 14 times and `radar.fk` 4 times. 2.0.43's
derivation kept the first plot of each file and dropped the rest with a `DESIGN` note ("one .fk
per plot"). Migrating a copy of that run's game folder wrote "27 plots" and derived **11**: 16
relays and radars gone from the world, with only a warning.

The rule is gone: every top-level sealed instance of an imported file is a plot, however many share
the file, exactly as place lines placed them. The flow was already keyed by plot (factory), with
the file read for each, so nothing else changed. `migrate` writes one import per file.

## 2. A migration that would lose a plot changes nothing

`fk migrate-surface` now derives the plot list from what it wrote and compares it with the place
lines' (name, file, position, size, rot, gap, patch, lifecycle). Any difference restores the surface
file, removes the root file and exits 2, naming each plot:

    error: the design would not give back the place lines' plots, so nothing was changed:
      pad-1: placed by a place line, not by the design

## Verified

- A copy of run 20261021-0110's game folder: 27 place lines, 27 plots derived after the migration
  (11 before this release).
- `tests/test_root.py` (17, +2): three plots of one file migrate with one import and all three
  derived, rot kept; a place line the design cannot express (`pad-1`: an instance name has no dash)
  leaves the surface file byte-identical and no root file. The derivation-notes test now expects
  two plots of `a.fk`.
- The full suite: **977 tests, OK** (975 before, plus 2).

## Seen, not changed

Rebuilding run 1343's committed world with 2.0.43 (no migration involved) swaps its 49 small poles
for 31 medium ones: the power step's pole choice on the laptop, not phase B. No machine or belt
moves.
