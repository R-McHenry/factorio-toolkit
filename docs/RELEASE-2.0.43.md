# Toolkit 2.0.43: the root design - plots are sealed instances (PLAN-GLOBAL phase B)

Rory, 2026-10-26: "Phase B of PLAN-GLOBAL.md is yours." The plan's five bullets (and §5's
decisions) are what this release does.

    Done when: run 1343's world (plant, base, outpost) migrated with migrate-surface composes to
    the same layout, key for key, as from its place lines; a game folder with only place lines
    builds exactly as before; the old checks (overlap, outside plot) still fire from the root
    design.

## 1. The surface file takes `design FILE`

    surface  nauvis
    mode     play
    terrain  none
    catalog  base
    design   nauvis.fk

`design` names the world's root `.fk`, and its top-level sealed instances are the plots. A
surface that has no `design` keeps reading its `place` lines exactly as before; with both,
**`design` wins** and the place lines are not read (the build's `read_surface` report says so, and
`design_notes`/`lines_places` keep both lists for a caller that wants them).

## 2. A factory file's body is a module

`import Outpost from "outpost.fk"` no longer needs `outpost.fk` to declare `module Outpost { ... }`:
when the file defines no module of that name, **its body is the module**. A file may give its own
frame with a `size WxH` line at the top, and a file of module definitions with no body of its own
still refuses a name it doesn't define:

    # outpost.fk - a plot file, no wrapping
    size 84x114
    smelt = SmelterArray<n=3, units=2, recipe=iron-plate> @(4, 4)
    ...

The plot's frame comes from its **placement line** (`outpost = Outpost @(18, 24) size 84x114`), or
from the file's `size` line. An instance line's `size` seals the instance as a module's own `size`
does (2.0.40), so a plot with no ports is still closed, and its ports take the placement's frame.

## 3. The plot list is derived from the root

Every **top-level sealed instance** of the root `.fk` is a plot: its name is the factory name (what
the place line used to name), the file it is imported from is the plot's `.fk` (its stem names
`.fk` and `.fkp`), and the instance line carries what the place line carried:

    import Plant from "plant.fk"
    import Base  from "base.fk"

    plant = Plant @(-34, -39) size 17x16
    base  = Base  @(8, 12)    size 70x56 gap 6
    boot  = Boot  @(-40, -10) size 20x26 temporary until main.running
    pad   = Pad   @(100, 100) size 6x6 retired
    iron  = Iron  @(-168, 64) size 144x140 @patch("iron-ore#2")

- `@(x, y, rot r)`, `size`, `@patch(...)` are the placement; `gap N` (§5's decision: tiles kept
  free around a plot for the root's routes, default 0) rides on the line and is recorded on the
  plot in the surface `.fkp` as `gap=N`. Root routing comes in phase C.
- `retired` and `temporary [until ...]` are flags on the instance line (the place-line
  lifecycles); a retired plot's `.fkp` is not read and its rectangle is free.
- A patch with its number is written quoted (`@patch("iron-ore#2")`) since `#` starts a comment.
- The plot's own file is its layout record: **one `.fk` per plot** (a second plot of one file is
  reported, not guessed). A module declared in the root itself, an instance of a template, a plot
  with no frame and one with no `@(x, y)` are reported as notes, and a `DESIGN` check line names
  each (`stop_on invariant` does not stop on them: they are advice, like every other check).

Every per-factory step (`place`, `route`, `size`, cover, apply, look, rates) runs on the derived
list unchanged, because the list is the same `Place` records the place lines gave.

## 4. Keys stay

A plot's layout is still its own `.fkp`, with its keys relative to its instance (`smelt/m0`,
`~ore/b3`), so the composed surface is `nauvis:base/smelt/m0` and the live world reads as before.
On `games/nauvis` (plant, boot, main) the composed surface is **1122 entities before and after**
the migration, and `Surface.rows()` - every key, name, position, direction and net - is
**identical**, with the same three plots and no problems.

## 5. `fk migrate-surface GAME`

Writes `<surface>.fk` from the game codebase's place lines and puts `design <surface>.fk` in the
surface file. The place lines stay as the record they were migrated from (commented out, with a
note), and nothing else in the surface changes:

    $ fk migrate-surface <run>
    migrate-surface <run>: wrote nauvis.fk (3 plots: boot, main, plant)
      plant = plant @-34,-39 size 17x16 (placed)
      boot = boot @-40,-10 size 20x26 (temporary until main.running)
      main = main @8,12 size 70x56 (placed)
      nauvis.surface: `design nauvis.fk` added, 3 place lines kept as comments
      the design derives 3 plots; `fk build` reads it from now on (`place` lines no longer place anything)

It refuses a surface that already has a `design`, one with no place lines, and a folder that
already has the root file. The imports it writes are the file stems in CamelCase
(`iron-smelt.fk` -> `IronSmelt`), the plot's name added where two files share a stem.

## Verified

`tests/test_root.py` (15 new): the migrated world composes to the same layout **key for key**
(1122 rows, plots and their boxes/params equal, no problems); the derivation names the same plots
as the place lines (module, x, y, w, h, rot, gap, patch, lifecycle - `boot` stays `temporary until
main.running`); the place lines stay as comments and a later `place` line is ignored while the
design is present; a place-lines-only game has its plot list as before; the flow builds the world
before and after the migration with **byte-identical** `main.fkp`, `plant.fkp`, `boot.fkp` and
`nauvis.fkp`, and the second build's `read_surface` says "design nauvis.fk: 3 plots from its
top-level sealed instances"; **overlap** (`plots main and plant overlap`) and **outside plot**
(`... is outside plot main`) still fire, now from an edit of the root design; a file body is a
module and its `size` line is its frame (and a placement `size` seals and frames an empty file);
`retired`/`temporary` flags, a quoted `@patch("iron-ore#2")`, `gap 6` riding to the plot line, and
the derivation notes (a second plot of one file, a module declared in the root, no frame, no hint).
`migrate-surface` refuses a second migration and a surface with no place lines.

The full suite: **975 tests, OK** (960 before, plus 15).

## Not in this release

The rest of `PLAN-GLOBAL.md`: root nets between plots (phase C: the world netlist, the floorplan
routing the root's nets with each plot's ports as attach points, `gap` respected, `--module` scope
on a plot), one rate model for the world (D), the example and the lab (E), docs and runs (F). The
root `.fk`'s own nets are elaborated but not routed yet.
