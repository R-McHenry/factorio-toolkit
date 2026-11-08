# 31-surface: the lab is a surface (PLAN-3.1 wave 1, 2026-11-08)

Branch `claude/31-surface`, cut from main `fa99ec8` (3.0.3). Rory's requirement (11-08): the lab
concept ballooned; a lab is just another game surface where things are free, with a source and
docs like any base and no toolkit machinery of its own. Lab features become general tools or stay
as small named god-mode conveniences, and the docs must make plain how to paste a blueprint on
the lab surface.

## What changed

**`surface.mode` is gone; a surface file has properties.** `fkcore/surface.py`: `SurfaceFile.mode`
is removed, `free: bool` is added, `force` stays, `force_name` (the force, default `player`)
replaces `apply.force_for(mode)` everywhere, `notify_mode` defaults to `all` when `free`,
`load_game` takes the first surface that is not free (was: the play-mode one). A `free` line is
bare, or `free yes|no`. An old `mode` line still reads for one release (`mode lab` -> `free` and
`force lab` unless a `force` line is there; `mode play` -> nothing) and lands a note in
`sf.notes`, which `read_surface` prints. `surface.properties(sf)` gives the property lines
(`PROPERTY_LINES`) for a surface file written from another, and `surface.migrate_mode(text)`
rewrites the mode line as the properties with a dated comment.

**Every lab-mode branch is a property check.** `apply.apply(..., free=False, force=None)` (was
`mode="play"`); `ApplyReport.free` (was `.mode`), its head line says `(free, force lab)` or
`(robots, force player)` and the detail line `free:` or `robots:`. `flow.py`: `read_surface`
reports the properties and notes; `s_cover_robots`, `_reach`, the diff's roboport read, unreached
check and rip estimate, `_force` and `s_apply` all branch on `ctx.surface.free` /
`force_name`. `look.py`: a look without an area is allowed on a free surface; the vision read's
`play` flag is `not sf.free`. `alerts.py`, `fresh.py`, `freereads.py`, `__main__.py` (`stats`,
`chart`, `stock`, `capital`, `_force_surface`): `sf.force_name`. `agent/fk.py` `_script()` skips a
`free` surface (or an old `mode lab`) when picking the run's build script.

**`fk migrate-surface GAME`** (`__main__._migrate_surface`, `_migrate_modes`): after the design
migration, or alone when there is nothing to migrate for the design, every `*.surface` of the
game with a `mode` line gets it written as the properties; `--mode-only` does only that. A failed
design migration still changes nothing (the mode pass runs after it succeeds).

**`fkcore/lab.py` is sorted into three modules.**

- `fkcore/alone.py` (new): a module built alone on a slot of any surface. `slots(game,
  surface)`, `slot_of`, `cells`, `prepare(game, name, src, size, surface)`, `build(...) ->
  Built` (lines, flow code and ctx, workspace, slot, plot, force, free), `clear`, `layout`
  (the workspace design laid out again, no game), `measure_alone` (the measure on any surface),
  `lua_clear(surface, area)`, `box`. The workspace is `<run>/<surface>/NAME` with
  `<surface>.surface` (the surface's property lines from `game/<surface>.surface`, else
  `DEFAULTS` for the lab, plus one `place` line) and `<surface>.build.fkb` (`SCRIPT`, or the
  source's own `<surface>.build.fkb`); the slots file is `<run>/<surface>/slots.json`. For the
  lab this is exactly `lab/NAME/lab.surface`, `lab/NAME/lab.build.fkb` and `lab/slots.json`, what
  `region.py` reads. A sealed module alone is wrapped in `alone_wrap.fk` (was `lab_feed.fk`).
  On a free surface the slot is emptied first (a direct destroy) and its chunks generated; on a
  surface that is not free nothing is destroyed and robots build the ghosts. `--keep` is a
  general option (the slot stands, only stale nets route).
- `fkcore/standin.py` (new): the god-mode stand-ins, by name, only where things are free
  (`require_free`): `supply` / `lua_supply(surface, force, box)` (power, requesters, burners'
  coal, module requests), `feeds` / `lua_feed(surface, force, ents)` / `feed` (infinity chest and
  loader at an open belt port, infinity pipe at a fluid port), `ore` / `lua_ore_*(surface, ...)`,
  `lua_unbounded(surface)` (the edge off). Nothing here is implied by a surface.
- `fkcore/lab.py` (rewritten, thin): `fk lab` = `alone --surface lab`, the edge taken off first,
  then `standin.supply` and `standin.feed` unless `--keep`; `--measure` tops the requesters up
  then `alone.measure_alone`; `--clear`, `--list`, `--ore` forward. `SURFACE`, `FORCE`,
  `LabError` (= `AloneError`), `build`, `measure` (was `measure_lab`), `clear`, `slots`, `ore`,
  `workspace` keep their names for the tools that call them.

**Commands.** `fk alone GAME NAME [--surface S] [--from] [--size] [--keep] [--with] |
--measure S | --clear | --list`; `fk standin GAME NAME supply|feed|ore [--surface S] [ore
flags]`; `fk lab ...` unchanged in its flags (labq.sh: `fk lab NAME --size WxH`, `--measure 60`;
region.py: `fk lab NAME --size WxH --keep --with ...` both work); `fk capture slot NAME
[--surface S]` added, `fk capture lab NAME` kept (the force comes from the slot's surface file).
`agent/fk.py` routes `alone` like `lab` (push, remote, pull) and `standin` as a host command.

## The surface file (3.1)

```
surface  lab          # the game surface
free                  # things are free: ghosts revived by script, nothing built by robots,
                      # direct destroy, a look may take the whole design; notify defaults to all
force    lab          # whose the paste is (default player)
terrain  none
catalog  base
design   lab.fk       # or place lines
watch plots: keep / watch sanctioned: mark 2h / notify / remind / target / robots / claim as before
```

A file without `free` is a base: robots build, fair play applies, a look needs an area.

## Building on the lab surface (for TOOLKIT.md; written there already as a section)

The lab is a game surface like any other, with a surface file like any base's: `surface lab`,
`free` and `force lab`. To paste a blueprint there, build a module alone on it: `fk alone NAME
--surface lab` gives NAME.fk a workspace `lab\NAME` with a surface file that places it on a slot
of its own, runs the build script there, and the apply pastes it and revives it. The same command
builds a module alone on any surface (`--surface nauvis`: robots build it, nothing is destroyed).
Power, stock and infinity feeds are not part of a build: they are god-mode stand-ins you ask for
by name, `fk standin NAME supply|feed|ore`, and only where things are free. `fk lab NAME` is the
alias that does both: the build alone on the lab, then `supply` and `feed`. `--keep` lays the
design over what stands and routes only the stale nets; `--measure 60` reads what it makes.

## Tools: renamed, none deleted

Each served a game surface, not the lab mode, so each is a general tool under a name without
"lab" (docstrings say what it was): `lab_bench.py` -> `bench_live.py`; `lab_buffers.py` ->
`check_buffers.py`; `lab_fluids.py` -> `fluids_live.py` (games/lab-fluids' fixtures;
`tests/test_lab_fluids_tool.py` follows); `lab_kit.py` -> `robot_kit.py` (a robot kit on a free
surface so a robot build can be watched; its surface file is one without `free` and with `force
lab`); `lab_kxm.py` -> `kxm_live.py`; `lab_lanes.py` -> `measure_lanes.py`; `lab_library.py` ->
`check_library.py`; `lab_ribbons.py` -> `check_ribbons.py`; `lab_sense.py` -> `sense_live.py`;
`hourglass_lab.py` -> `hourglass_live.py`. `check_buffers`, `check_library`, `check_ribbons` call
`standin.lua_supply(lab.SURFACE, lab.FORCE, box)` and `alone.box`. `tools/laptop_server.py` calls
`apply(..., free=True, force="lab")` / plain `apply(...)`.

## Tests

Rewritten: `tests/test_lab.py` (AloneTest, StandinTest, LabAliasTest: 20 tests), `test_lab_feed.py`
and `test_lab_ore.py` (alone/standin), `test_surface.py` (free, force_name, the old mode line,
`migrate_mode`, `load_game`, `properties`), `test_root.py` (+ a migrate-surface test with a `mode
lab` file). Fixed for the signature change: `test_apply.py`, `test_own.py`, `test_circuits.py`,
`test_dnp.py`, `test_in_place.py`, `test_turned.py`, `test_robots_reach.py`, `test_flow.py`,
`test_lab_fluids_tool.py`. Run (targeted, in the background), all green: test_surface, test_lab,
test_lab_ore, test_lab_feed, test_apply, test_own, test_robots_reach, test_turned, test_look,
test_alerts, test_lab_megabase, test_root, test_in_place, test_dnp, test_circuits, test_flow,
test_cover, test_robots, test_width2, test_avail, test_hands, test_fluid_route, test_lab_scenario,
test_lab_fluids_tool (and the second pass named in the report).

## Left open, for the integrator

- **Old `mode` lines in fixtures.** About 25 test modules and `games/lab-*/lab.surface` still
  write `mode play` / `mode lab`; they read through the tolerant parser (a note, never an error).
  I left them (other wave-1 branches touch several of those tests). `fk migrate-surface
  --mode-only` on each `games/lab-*` folder, and a sweep of the test fixtures, can go in the docs
  wave or a follow-up; then the tolerant branch and `sf.notes` can go in 3.2.
- **`compiled_store`** stays `out/compiled` in `alone.py`; 31-store replaces it with the one
  store (one line, `alone.compiled_store`).
- **Terrain for a module alone** is `none` (a slot is bare ground); a slot on a surface with a
  real terrain is not checked against water or ore. 31-world's `read-terrain --entities` is the
  natural way to give it obstacles.
- **`region.py` and wrapped modules**: a sealed module wrapped alone writes `alone_wrap.fkp`, not
  `NAME.fkp`; region.py reads `lab/NAME/NAME.fkp`, as it did with `lab_feed.fkp` before (no
  change in behaviour, noted for the lab session).
- **s_cover_robots' standing-roboport logic** is untouched apart from the lab-mode line (31-world).
- Docs beyond the fixed text (TOOLKIT.md section "Building on the lab surface", the surface file
  example, FAIR-PLAY.md's lab paragraph, CORE.md §6 bullets) wait for 31-docs: LANGUAGE.md still
  says `InfinityPipe` is "for the lab only"; the `fk lab` lines in TOOLKIT.md's command list
  (~line 951, 985) and BUILDING.md's "Lab every module first" still read fine.
