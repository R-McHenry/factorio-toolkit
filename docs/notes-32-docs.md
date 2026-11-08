# 32-docs: the player docs structured around examples (PLAN-DOCS, 2026-11-08)

Branch `claude/32-docs`, cut from main `43f7961` (3.1.1). Rory, 11-08: "the docs should probably
be structured around examples in the first place, it was a big problem for deepseek players the
way it is now." The DeepSeek win arm met 1,409 lines of reference first and the working files
last, spent about 100 turns reading docs and probing the cell library, and built first at turn
115. The plan is `..\assessment-20261108\PLAN-DOCS.md`.

## What changed

| file | before | after | what |
|---|---|---|---|
| `agent/docs/START.md` | (none) | 240 | the first hour with gears.fk, copy to look, every output line explained; the path through the chapters |
| `agent/docs/EXAMPLES.md` | 619 | 1232 | the spine: 14 chapters in PLAN-DOCS order, each the file, the command, the exact output, the new idea, "what goes wrong here" |
| `agent/docs/LANGUAGE.md` | 1165 | 424 | a reference appendix: every construct a table row with a snippet and the chapter that uses it; tutorial prose a chapter now carries is cut |
| `agent/docs/TOOLKIT.md` | 887 | 411 | the command index as tables (example line, chapter), one paragraph on packs, the build, route, store, build script, surfaces, placements, checks shortened to what the chapters do not cover |
| `agent/docs/examples/*.fk` | 22 files | 26 files | every file opens with a header: what it shows, `Run:`, `Expect:` (two to seven lines) |
| `agent/docs/examples/captured/mate-block.json` | | new | the chapter-14 capture, written by `capture.anchored` from the test fixture's block |
| `tests/test_examples_docs.py` | | 228 | the tests below |
| `agent/prompts/opus-v3.md` | | 4 lines | START.md first, then the chapters, then the references |
| `agent/docs/BUILDING.md` | | 1 line | the pointer to LANGUAGE.md "Wrapped machines" is now "Literals" |
| `kickoff/template/game/nauvis.surface` | | 1 line | the `mode play` line is a dated comment (PLAN-DOCS "Packs") |

STRATEGY.md's one pointer (LANGUAGE.md "Properties on objects") still resolves; FAIR-PLAY.md's
pointer (TOOLKIT.md "Building on the lab surface") still resolves. Nothing else in them changed.

### The four new examples (Rory's addendum, 11-08)

All four build on paper and are quoted in chapters 6, 9, 11 and 14; each imports only from
`beacon-cells.fk` or nothing, and each is a row in the test.

- `beacon-cells.fk` (chapter 6 aside, plot 44x40): `FurnB` and `GreenB` from the lab's
  `pucells.fk`, with the three kinds (`Asm3`, `EFurn`, `Beacon`), fed by two ore requesters into
  a box. 39 nets, 0 check lines. The rates show the beacon count per furnace: 99.08 plates/min
  with two beacons, 87.06 with one. The lab's cells are copied as they are; only the feeds are new.
- `red-chain.fk` (chapter 11 main, plot 92x76): `RedMod` from `redmod.fk` with `Plas2`, `RedB`,
  `PlasPair`, `RedPair` copied in, `FurnB`/`GreenB` imported from beacon-cells.fk, and stand-ins
  for the trunks (two ore requesters, an InfinityPipe at 160/s, a coal requester, two boxes). 127
  nets, 1003 entities, 8 stored modules, route step 3.2 s. One check line, `CLOG` on
  `chain/rp/gp`, which the lab file has too; the chapter says what quiets it. On paper the two
  outputs carry 2.83 + 1.84 red/s; the lab's 6.9/s is quoted as "measured in the lab (11-07)".
- `belt-switch.fk` (chapter 9 second example, plot 64x70): `SteelMod` from `steelmod.fk` and the
  bay's switch from `bay_steelbay.fk` (one SteelMod instead of two, so it fits a chapter). The
  paper build shows `gated net bay/out_: 1 carrier if=steel-plate>0 on bay/sw` in floorplan.txt,
  the 3.0.3 trunk-belt switch. The outer net into one chest is `limited "..."`; a version with
  two nets off the paired port (one chest a lane) did not route (`its two lanes come in paired,
  and no straight belt runs on from there past every machine to its end`), so the chapter says
  the hub takes each lane with a filtered inserter in the base. `feed-rides-on` on that net stays
  and is explained.
- `mate.fk` + `captured/mate-block.json` (chapter 14 main, plot 40x40): the MateRoundTripTest
  fixture as real files (the Literal at its anchor, a requester feeding `std.asm1`, a provider
  chest taking from it). 2 nets, 0 check lines. The design side is a real paper build; the game
  side (the capture command's lines, the diff's `ok` and `ghost`, the mismatch line) is by shape.

## What is quoted from a real paper build

Every example was built with the template's steps through `report_checks` (no `run_models`,
terrain none, the plot size the chapter names, `FK_LINK=off`), plus `fk check` and `fk rates`
before and after the build, and for gears, sized, ribbon-bus, bus4ribs, blue6, busbase and
shared-belt also `fk status`, `fk look --source design`, `fk explain`, `fk contract`, `fk plan`
and `fk dnp` on the built game folder. All 26 examples build, every net routed, no SPILL. Quoted
exactly: every `check NAME:` and `NAME: N nets:` summary line, the check lines of every chapter's
"what goes wrong here", the `fk rates` tables and `BUFFER` lines, `out\route.txt` lines (the
shared belt's trunk, the ribbon, the compiled store, the `laid as ... laid it` lines), `out\
size.txt`, `out\cover_power.txt`, `out\floorplan.txt`'s gated-net lines, `fk status`'s store list,
`fk contract` for bus4ribs and busbase, `fk plan` for red science and iron plates, `fk explain`
for gears, `fk look --source design` at zoom 1 (gears) and zoom 4 (ribbon-bus). 14 of 14 chapters
quote real paper output; chapters 13 and 14 quote paper output for their files and describe the
game steps by shape.

Two things the paper build showed that the old EXAMPLES.md did not say:

- `power-shed.fk` gets `power-short` with the template's `cover robots` step: the roboport the
  cover adds to `main` wants 220 kW against the four panels' 168 kW average. Without `cover
  robots` (test_examples_21's script, and the lab, where the cover lays nothing) there is no such
  line. The chapter explains it rather than hiding it.
- `library-lines.fk`'s routed rates (after the build) show every furnace `blocked (output backs
  up)` at 0.000, which looks like a routed-rates artifact on Stacks; the chapter quotes the
  nominal rates only (98% and 89%, as before) and does not quote the routed section.

## Described by shape only (no game in this session)

`fk build`'s game steps (`diff`, `report_bom`, `apply`), `fk look --source world`, `fk lab` /
`fk alone` / `fk standin`, `fk measure`, `fk paste`, `fk register`, `fk capture --from`, `fk
adopt ID`, `fk robots`, `fk read-terrain --entities`, `fk diff ID` and the `MISMATCH` line. Each
is written as the format string in `fkcore` prints it (`alone.py`, `lab.py`, `standin.py`,
`apply.py`, `look.py`, `sense.py`, `measure.py`, `__main__.py`), with `N`, `X,Y`, `T` where the
game fills in numbers, and the chapters say "in the game" for them. START.md's gears walk-through
quotes the paper steps exactly and the game steps (apply, look) by shape.

## The tests

`tests/test_examples_docs.py`:

- `ExamplesBuildTest`: every `examples/*.fk` builds on paper (the same steps and plot sizes as
  above), every net routed, no `SPILL`/`no-route`/`malformed`/`cannot-carry`, and EXAMPLES.md
  quotes the build's `NAME: N nets: ...` summary line (whitespace squashed; START.md too for
  gears). Then the gates' amounts of mall-loop, the ribbon line of ribbon-bus, the two domain
  lines of power-shed and the gated-net line of belt-switch, each in the build and in the doc.
  About half a minute on the laptop (26 builds); run it in the background.
- `LibraryTableTest`: the chapter-7 table's cell column equals the modules and kinds of
  `examples/cells.fk`.
- `CommandsTest`: every `fk X` in START.md, EXAMPLES.md and TOOLKIT.md is a subcommand of
  `fkcore.__main__` or one of `agent/fk.py`'s own (build, look, wait, stage, lab, alone, sim, map,
  capture, catalog, route, place, report, compile, lua, stats).
- `HeadersTest`: every example opens with `# NAME.fk:` and has `Run:` and `Expect:` lines.

`tests/test_examples_21.py` is kept as it is (its five examples and the cells.fk identity).

Results (11-08, laptop): `python -m unittest tests.test_examples_docs tests.test_examples_21`:
`Ran 8 tests in 26.512s`, `OK`. The first run of the build test found four lines the chapters
had not quoted or had mistyped (shared-belt's `1 underground pairs`, and no summary line for
furnace-column, robot-feed and smelter-array); the test is what the plan asked for.

## Open

- The runner's `l0-lab-fk.md` brief (PLAN-DOCS "The briefs") is in the factorio-runner repo, not
  this one: it still needs its pointer to START.md.
- `agent/prompts/core-v1.md`, `lead-v1.md`, `opus-v1.md`, `worker-v1.md` still name TOOLKIT.md's
  "When you need something" list, which TOOLKIT.md no longer has (the command tables replace it);
  they are the older briefs and were not touched.
- START.md is 240 lines against the plan's "about 150": the quoted output blocks are long. The
  prose is short; cutting further would cut lines a player has to read anyway.
- `red-chain.fk`'s `CLOG` line on `chain/rp/gp` is in the lab's source too; a `RedPair` written
  with two nets and `lanes` (as `RedB` is inside) would quiet it. Left as the lab has it, and said.
- `fk look --source world` verdict lines and the lab's `stand-in supply: power ...` line are by
  shape; a session with a laptop server could quote them exactly.
- The kickoff template's `cells.fk` and `examples/cells.fk` are one file (test_examples_21); the
  beaconed cells live in `beacon-cells.fk`, not the library, so the library table is unchanged.
