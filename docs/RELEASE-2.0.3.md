# Toolkit 2.0.3 (2026-10-22): the lab, first class

Rory, for the 2.0 run: "the lead should be using the lab and planning rather then waiting if there
is seemingly nothing to do" and "the lead can send workers to do most of the lab work too". The
game always had the lab (a `lab` surface, a `lab` force with its research done, `/lab` for Rory,
`mode lab` in the toolkit), but a player had no way to use it: a lab build meant a surface file and
build script of its own, the host's shell to run them, and Lua for power. Checked end to end in
the 2.0 run first (the example smelter on the lab surface, nauvis untouched: 137 of 137 built,
then 150 plates a minute measured), then built as one command.

## `fk lab`

- `fk lab NAME [--from DIR] [--size WxH]` (`fkcore.lab`): NAME, a factory of `game\` or of DIR (a
  stage's folder, a scratch copy; `bin\fk.py` sends DIR to the host first), goes into a
  workspace of its own, `<run>\lab\NAME`, never `game\`, with a surface file that places it on
  its own slot of the lab and the lab's build script. The slot is emptied, the flow builds it
  (lab apply: chunks generated, drill rows' ore seeded, ghosts revived at once), and the lab gives
  it what it can't get there: power (an electric energy interface beside one of its poles), its
  requester chests filled with what they ask for, and a first load of coal for burners.
- `fk lab NAME --measure 60`: the requesters topped up, then what its machines make over 60 s
  against the rate model (`fkcore.measure`). In the lab the requesters are full, so it shows what
  the machines do when their inputs keep up: the gears example made 120 a minute where the model
  counts its `rate=1.25/s` (37.5).
- `fk lab NAME --clear`, `fk lab --list`.
- Slots: 200 x 200 tiles each on a 9 x 9 grid inside the lab, which is 2048 tiles square
  (-1024..1024): a first try past its edge left 10 ghosts on out-of-map tiles.
- A request is about a minute's worth, so the first version's "stock once" ran dry before the
  measure (0 gears measured); the chests are now filled.
- `flow.run(..., link=)`: the lab build lends its open game link to the flow, which doesn't close
  it.
- Checked on a laptop test server (2.0.77): the smelter (OK 137, 8 furnaces given coal, 144
  plates a minute) and the gears (OK 33, 4,800 plates stocked, 120 gears a minute), a rebuild
  (138 entities emptied first) and a clear.

## The codebase's own surface and script

`bin\fk.py` took the alphabetically first `*.build.fkb` as the run's build script, and
`surface.load_game` the first `*.surface`, so a `lab.build.fkb` or `lab.surface` copied into
`game\` would have taken every `fk build` and `fk look` of nauvis. Both now take the play-mode
surface's own.

## Docs

`docs\TOOLKIT.md` "The lab: `fk lab`" and a line under "When you need something";
`docs\FAIR-PLAY.md` "The lab" points to it; the lead brief's "Plan ahead while workers build" has
the lab beside `fk stage`, with Rory's two lines.
