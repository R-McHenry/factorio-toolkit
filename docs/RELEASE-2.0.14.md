# Toolkit 2.0.14: `any` — the inserter and the pole the network can build

Rory, 2026-10-25: "The toolkit should let whatever inserter be easy to use, same with power poles.
Right now the bad habit is agents using lots of fast inserters when they only have regular inserters,
or similar with power poles."

What the run of that morning did: its script said `route --hand inserter` (a patch someone had to
remember), `cover power --pole medium-electric-pole`, and each row said `inserter=inserter`. Even so
`report_bom` found 4 fast inserters pasted **LOCKED** (research at 81%, none in the network, 50 plain
inserters in the kit), and the burner row they fed stood dead; a single `Assembler<inserter=inserter>`
got fast hands from the router anyway, because that parameter only ever reached rows.

- **`any`** (also `auto`, `whatever`) names a *family* instead of a prototype, wherever a prototype
  was named: `inserter=any` on an instance, `route --hand any`, `cover power --pole any`,
  `floorplan --bridge-power any`. `fkcore.avail` chooses: the best one robots can build **now** for
  what the design needs (so a tier the network holds two of is not chosen for forty), else the best
  one that is not LOCKED, else the family's default with the reason (blind, that is still a fast
  inserter or a medium pole: a rate report or a lab has no snapshot and is not silently downgraded).
  Best first: a fast inserter where the network can build one, a medium pole where it can build one;
  that is the tier Rory asks for where it is affordable, and never a ghost the network cannot build.
- **The snapshot** is `out/avail.json`: the design half of a play build runs on the laptop, where
  there is no game link (`agent/fk.py` splits at `diff`), so the host writes it — `report_bom --stock
  live` every build, and `fk avail --save` before the first one (the wrapper does that itself when
  no snapshot is there yet). Like `out/force.json` it is the last read, and the note says when it is
  missing.
- **The build says what it took**: `inserter=any: fast-inserter (the network holds 40)` lands in
  `out\route.txt`, `out\place.txt` and `out\cover_power.txt`, so a player learns the mechanism from
  the log instead of a stanza of rules.
- **A standing route gives up the hand nobody can build.** A route that stands keeps its carriers
  (2.0), so a run that pasted fast inserters while none was researched kept exactly those ghosts
  where they stood. `route --hand any` now renames a standing short hand the network cannot build to
  the one it can, in place and without re-routing (`out\route.txt`: `rehanded 2 standing inserters
  robots cannot build, to inserter`). An inserter that stands built is left alone: it works, and its
  speed is not worth losing.
- `inserter=` is checked now (a name that is not an inserter says so instead of laying a belt where
  a hand belongs), and `cover power --pole` / `floorplan --bridge-power` name the four poles instead
  of failing in `fkcore.cover`.
- The template build script uses `--hand any`, `--pole any` and `--bridge-power any`; an upgrade
  rewrites a run's `--hand inserter` (its own old patch) to `--hand any`.
- `LANGuage.md`, `TOOLKIT.md` and `STRATEGY.md` say it in one place each, and `LANGUAGE.md` says
  what was true all along: `inserter=` on a single machine does nothing (its hands are the router's).

Not done, and why: the family is a *tier* choice, not a stock accountant. `any` does not check that
the ingredients for the tier it chose are in the network, and a design that names `fast-inserter`
outright still pastes a LOCKED ghost if the network holds none — `report_bom` says so before the
paste, and `stop_on LOW_STOCK` holds it.
