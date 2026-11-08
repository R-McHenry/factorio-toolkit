# 3.1: surfaces, world reads, placements, one store (draft)

3.1 is PLAN-3.1 (`..\assessment-20261108\PLAN-3.1.md`), Rory's direction of 2026-11-08: one
consistent toolkit release with documentation to match, the fractured state of 3.0.x recovered
from, nothing old migrated. Built as three waves on branches `claude/31-*`, merged onto main 3.0.3
(`fa99ec8`) with `v3.1.0-dev.N` tags between. The language is unchanged. Read with the notes per
wave: `docs\notes-31-surface.md`, `notes-31-store.md`, `notes-31-world.md`, and the placements
note.

## Wave 1

### The lab is a surface (31-surface)

- **`surface.mode` is gone; a surface file has properties.** `free` (things are free: ghosts
  revived by script, nothing built by robots, direct destroy, a look may take the whole design,
  notify defaults to `all`) and `force NAME` (whose the paste is, default `player`). A file
  without `free` is a base. Every former lab-mode branch in `apply`, `flow`, `look`, `alerts`,
  `fresh`, `freereads` and `__main__` is a property check; `agent/fk.py` picks the run's build
  script from the first surface that is not free.
- **`fkcore/lab.py` is sorted into three modules.** `fkcore/alone.py`: a module built alone on a
  slot of any surface (`fk alone NAME [--surface S] [--size] [--keep] | --measure | --clear |
  --list`), its workspace `<run>/<surface>/NAME`, the slots file `<run>/<surface>/slots.json`.
  `fkcore/standin.py`: the god-mode stand-ins by name, only where things are free (`fk standin
  NAME supply|feed|ore`). `fkcore/lab.py`: `fk lab` as a thin alias, `alone --surface lab` then
  `supply` and `feed`, its flags unchanged so `lab-session\labq.sh` and `region.py` keep working.
  `fk capture slot NAME [--surface S]` added; `fk capture lab NAME` kept.
- **`fk migrate-surface [--mode-only]`** writes an old `mode` line as the properties. The
  tolerant parser still reads `mode play|lab` for this release, with a note.
- **`tools/lab_*.py` renamed** to what they are (`bench_live.py`, `check_buffers.py`,
  `fluids_live.py`, `robot_kit.py`, `kxm_live.py`, `measure_lanes.py`, `check_library.py`,
  `check_ribbons.py`, `sense_live.py`, `hourglass_live.py`); none deleted.
- Tests: `test_lab.py` rewritten to the surface model (alone, standin, the alias), `test_surface.py`
  (the properties, the old line, `migrate_mode`), `test_root.py` (migrate-surface).

### One compile store (31-store)

- **One store**, `out\compiled\<module>\<key>.json` with a `current` pointer per module, in place
  of 3.0's design store (`out\design\modules`) and the router's flat `out\compiled\<key>.json`.
  The base is the router store (nested units, twins, 180-degree twins); `fk compile`,
  `--reuse-lab`, the research check and the per-module folder moved onto it.
- **One key**, `route.unit_key`: `compiled.ROUTER` (`"3.1"`; `route.COMPILE_VERSION` is gone),
  the frame and what stands in it, each net's ends, items, lanes, taps and flags, the children's
  keys, the catalog and terrain facts, the router's settings, seeds and held routes.
- **One set of readers and writers.** The route step (any `--only`), `fk compile`, `fk lab`
  (`--keep`, measure) and `fk status` read and write the game's `out\compiled`; `route --store
  DIR` elsewhere, `--store none` or `--compiled no` nothing. Nets laid from the store count as
  `routed`. The route step's lines: `compiled  b: 2 nets laid from the store (Gears <key>)`,
  `compiled  stored a (out/compiled)`, and the summary's `K laid from the compiled store`.
- **Old stores** are not read and not migrated: a build whose `out` holds entries of either old
  format says so in one line, and `fk status` repeats it.
- Tests: `test_compile_once.py` (11) and `test_compiled.py` (9), with a hand-edited route file
  held (`fk hold`) as an input that changes the key.

### World reads are explicit (31-world)

- **The world no longer feeds the cover steps.** `out/standing.json` is gone; `cover power` and
  `cover robots` read nothing of what stands. Switching the pole kind lays the new kind everywhere
  the cover needs a pole (2.0.1 kept the built poles of the old kind). `cover_robots` lost the
  2.1.3 chain from standing roboports; a roboport goes where the design's chests need it. "A moved
  roboport is taken up" stopped: the old one is held like any other old entity until the design's
  own stand, or at once when the network holds too few roboports (`STOCK_OUT` stays). `REACH` and
  `UNREACHED` still read the roboports standing with power, as reports about a paste.
- **`fk read-terrain --surface S --area A --entities`** puts the tiles of every built entity in
  the area that the design does not own into `<name>.terrain.json` under `entities`, and
  `Terrain.blocked` includes them: routes, poles and roboports go round them from the next build
  on. Ghosts, trees, rocks, cliffs and units are never obstacles. Without `--entities` the file's
  entities stay as they were; `--replace` drops everything. A file written before 3.1 reads as
  `"entities": null`.
- **`fk robots [AREA] [--force F]`**: the standing roboports against the design's logistic
  chests: how many stand, with power, in how many networks; covered and uncovered chests;
  redundant roboports (greedy to a fixed point, a network bridge never redundant); the minimal set
  on free ground; roboports without power. A pure read, on the host.
- Tests: `test_cover.py`, `test_robots_reach.py`, `test_fixes_213.py`, `test_flow.py` adapted;
  `test_terrain.py` `EntitiesTest` and `test_robots.py` `StandingReportTest` added.

## Wave 2

### Placements (31-placements)

filled from docs/notes-31-placements.md at merge

## Wave 3

### Documentation (31-docs)

- `agent/docs/TOOLKIT.md` rewritten for 3.1 (1,270 lines to about 825): a command index, one
  compile store, one routing mode (`FK_NEGOTIATE=1` stays opt-in, one line), surfaces and their
  properties, "Building on the lab surface" with how to paste a blueprint there, "Bounds and
  obstacles" (the plot; `read-terrain --entities`; `fk robots`), the placements section.
  Everything about the 2.x design store, the lab mode and standing poles or roboports feeding the
  cover steps is gone.
- `LANGUAGE.md`: `InfinityPipe` is a stand-in where things are free, not "for the lab only";
  `fk capture` names the slot of a module built alone; MinerRow on uranium points at
  `AcidDrillCell`. `EXAMPLES.md`: "On the lab surface", the one blueprint-paste example.
  `BUILDING.md` and `README.md` to 3.1's names. `FAIR-PLAY.md` unchanged (its lab paragraph was
  fixed in wave 1).
- Fixtures: no test fixture and no `games/*/*.surface` carries a `mode` line (16 test modules
  edited, 12 game surface files migrated with `fk migrate-surface --mode-only`). `test_surface.py`
  and `test_root.py` keep theirs: they test the tolerant parser and the migration.
- `..\assessment-20261108\PLAN-BUILD.md` "What exists already" rewritten against 3.1.

## Not in this release

- Nothing is migrated (Rory, 11-08). The live Opus run (`20261030-2352-opus`) stays on 2.1.30,
  the runner on its vendored 2.1.30 copy; old saves, designs and the two old compile stores are
  reference.
- The tolerant `mode` branch in `surface.py` and `sf.notes` stay for this release; they can go in
  3.2 once no surface file in use carries a `mode` line.
- An unmarked hand edit of a route file as an input (it needs the step's own write stamp); pruning
  of compile store entries (PLAN-BUILD §2 keeps the last few per module and any a placement refers
  to); `fk compile` reporting per nested child.
- `fk robots` and `read-terrain --entities` were not checked against a laptop server (the Lua is
  read-only and `assert_safe`-checked). `minimal` lays on free ground with no obstacles: a lower
  bound, not a placement.
- The Rust kernel learning 3.0's tap rules (open since 3.0.1); the lab's own generators
  (`lab-session\baygen.py`, `netgen.py`, `slotin.py`) placing turned bays by their origin.

## Upgrading

- A run pins this release's commit as any other (`kickoff/upgrade_run.py`), and
  `fkcore.__version__` says `3.1.0`.
- **Every stored module is laid again once**: `compiled.ROUTER` is `3.1`, and the old stores are
  not read. The first build after the upgrade routes every sealed inside and stores it under
  `out\compiled\<module>\`.
- **Terrain files gain an `entities` line** on their next save (`null` until a `read-terrain
  --entities` fills it). Nothing else in them changes.
- **Old surface files**: `fk migrate-surface --mode-only GAME` writes a `mode play|lab` line as
  the properties (`mode lab` becomes `free` and `force lab` unless a `force` line is there; `mode
  play` becomes nothing, with a dated comment). Until then the line is read with a note.
- A design written before 3.0.1 still needs `fk migrate-origins FILE --write` first.
- The lab run (`lab-session\fk-run`) and its scripts import `..\v5` (main): `labq.sh` and
  `region.py` call `fk lab` with the same flags and need no change; `tools/lab_*.py` callers use
  the new names.
