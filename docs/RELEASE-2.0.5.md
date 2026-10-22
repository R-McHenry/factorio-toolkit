# Toolkit 2.0.5: what the live 2.0 run showed after 2.0.4

## Turned belts on a new factory's tiles are laid fresh (TURNED)

Rory, 2026-10-22, about the 2.0 run (`20261022-1036-lead-v2`): "there are some odd rotated belts
and broken belt connections, mostly around the sideloader iron stack".

**What stood.** The run's `south` factory (the 24-furnace SmelterArray `ism`, its 16 drills `iore`
and their routes) was built at 13:06 over the burner iron block `iron` (plot 17,83) it replaced.
The 13:46 diff had 26 turned DRIFTs in south: 25 belts and one inserter. Every one is a belt or an
inserter of the old block (`iron.fkp`) on the same tile, under the same name, facing the old
block's way (26 of 26). Among them:

- the drills' ore belt (`iore/outb0..10`) ran west into a pole instead of east;
- three of the array's east feed belts (`ism/feed0e14..16`) faced west and east mid-column;
- the feed corner `ism/feed0m2` faced south, so the coal splitter fed straight on and the ore
  splitter pushed into it head-on;
- `ism/out0b21`, the last plate belt before the output underground, faced west;
- the fuel line's run under the array (`~fuel/b19..23`) faced east.

The rest of the stack's gaps were ghosts waiting for belts the network didn't hold (SHORT).

**Why.** The live map is uncharted (no radar, no character), so `build_blueprint` places nothing
(`out\apply.txt`: "0 ghosts placed"). Every row goes through the single-ghost fallback, and that
fallback took a built entity of the row's name on its position as placed, whichever way it faced.
So the old belts stood as found, and every build kept them so. The diff said `DRIFT` for each one,
and the checks only said `DIFF DRIFT 37`.

Where a paste lands, it fixes them itself: a laptop test server (2.0.77) turned a belt, an inserter
and a splitter in place. A belt a quarter turn off, or an underground of the other end, got a
ghost and was ordered out. 17 more of the old block's belts had stood on south's tiles turned. The
1.2 rule (a carrier laid under another net that holds the old net's items is laid fresh) took those
up because their old items didn't fit. The 26 left held ore on the ore belts, coal on the fuel
belts, plates on the plate belts, or nothing.

**Not the cause:**

- the SmelterArray template: its geometry matches Rory's stack blueprint
  (`games\v2-bench\smelter-stack-ghosts.json`) row for row;
- the codec's 16 directions: the diff compares them right;
- 2.0.2's lane-pair patching;
- the removed UG_SIDELOAD check.

**The fix.**

- `apply` (play), after the paste, finds each design row of a belt, underground, splitter,
  inserter, pipe-to-ground, pump or drill whose entity still stands turned or as the other end. It
  also finds a ghost an earlier build left facing an older design's way. Each one is ordered out
  and gets its single ghost as designed (`apply.turned_rows`, `ApplyReport.turned`, an
  `out\apply.txt` line `TURNED n ...`).
- Generators, boilers and offshore pumps stay a DRIFT to read: a power plant is not taken up for a
  turn.
- The diff marks such verdicts `turned` (a `DRIFT ...; TURNED: the next build lays it fresh` line)
  and warns with a `TURNED` check before the paste, naming them.
- `sense.turn` is the one test of a turn for both.
- A turned one a player touched last (its `last_user`) is also a `HAND` line (Rory's 2.0 rule: the
  source wins, and the build says what it turns back).

**Tests:**

- `tests/test_turned.py`, from the run's own `south.fkp` and `iron.fkp`
  (`tests/data/south-over-iron`): the old block as it stood under the new design gives 43 turned,
  17 of them laid fresh by the 1.2 rule, and the other 26 are exactly the live diff's.
- An apply on a fake uncharted map orders those 26 out and ghosts them as designed. After robots,
  nothing is turned.
- Which kinds count, a hand-turned belt as a HAND line, and the `TURNED` check's text.
- On the laptop test server, `python tools/laptop_server.py turned`: six turned entities, the paste
  refused (simulated, see below), ordered out and ghosted by the game, built as designed after a
  revive, and a second apply turns nothing.

**Found on the way:** this laptop's lab ground takes a paste even on uncharted chunks.
`tools/laptop_server.py ghosts` (2.0.4 A1) now prints "NOT as designed" because its paste placed
all 10 ghosts. The single-ghost path it checks was not reached there. `turned` simulates the
refusal for that reason.

**Repairing a run that has them:** after the upgrade, one `fk build` lays them fresh (robots take
each up and build it again, one belt each way).
