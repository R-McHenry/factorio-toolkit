# 31-placements: the registry of what was pasted (PLAN-3.1 wave 2, 2026-11-08)

Branch `claude/31-placements`, cut from main `85c6313` (3.1.0-dev.2). Rory's requirements (11-08):

1. Agents either track objects in the world with the toolkit, or they don't; then a conflicting
   design must produce a MISMATCH, never a silently adjusted plan or a build over or around. The
   toolkit converges the world onto one clean design. "Several small adjustments at those points
   beat a big world-object tracking system."
2. "Make sure to support the use case where it's easy to pull a selection of world objects from
   the registry right into new source, so that when the new blueprint is placed it can mate and
   directly overlap with some of that stuff."

## The registry file

`out/placements/<surface>.json`, one file per surface, next to the per-entity record
`out/own/<surface>.json` (`fkcore.own`, which stays underneath: what the applies pasted, entity by
entity; placements are the per-artifact layer above it). It lives in `out` because it is a record
of the world, not a design input (nothing in `game/` reads it to lay anything out; it syncs with
`out/own` between laptop and host), and per surface because areas are. `fkcore/placements.py`.

```json
{"surface": "nauvis", "about": "...", "placements": [
 {"id": "iron", "surface": "nauvis", "module": "smelting", "instance": "iron",
  "artifact": "store:3f2a9c...", "origin": [40, -20], "rot": 0, "area": [40, -20, 70, 10],
  "tick": 123456, "label": "fk build nauvis.build.fkb", "source": "build", "file": null,
  "count": 212}]}
```

- `id`: the factory's name on the surface for a build; `shared` for the surface's own entities
  (cover roboports, shared infra); the slot's NAME for a build alone; `--as NAME` or the file's
  stem (`std`, `std-2`, ...) for `fk paste`; the module or `--as NAME` for `fk register`.
- `artifact`: `store:<key>` when the module has a compile store entry (`fkcore.compiled`'s
  `current`), else `rows:<sha>` over the pasted rows relative to the origin; `null` after a
  register of something no module stands for.
- `source`: `build` | `alone` | `paste` | `register`; `file`: the file `fk paste` pasted.
- One record per paste, replaced on a rebuild: the same id replaces (a build's plot, a slot, a
  `--as` name), and a `fk paste` of the same file whose origin lands inside an existing record
  of that module takes that record's id. Nothing piles up.

Who writes it: `fk build`'s apply (`flow.s_apply`: `placements.from_apply` over the pasted rows,
one record per plot plus `shared`), a build alone (`alone.record_placement`, into the *game's*
registry for that surface, once the flow's apply step ran), `fk paste`, `fk register`.

## The commands

```
fk placements                                   the registry, every surface
fk paste FILE --at X,Y [--rot R] [--as NAME] [--surface S] [--force F]
fk register X0,Y0,X1,Y1 MODULE[/INSTANCE]  |  fk register AREA --as NAME
fk capture --from PLACEMENT_ID|AREA --into FILE [--names]
fk look PLACEMENT_ID            fk diff PLACEMENT_ID|AREA
fk adopt PLACEMENT_ID|AREA [--write]           (fk adopt X,Y[;X,Y] --into FACTORY/NET stays V1)
```

All run on the host (`agent/fk.py` HOST: `paste`, `register`, `diff`, `placements`; `capture`,
`look`, `adopt` as before).

**`fk paste captured/std.json --at 100,50`** pastes a Literal file (a capture's `.json` with
`bp` and/or `entities`, or a blueprint string `.bp`/`.txt`) as ghosts with its origin, the
file's (0,0), at 100,50, turned `--rot R` quarter turns clockwise about it (3.0.1: origins, not
edges), with its settings and circuit wires; on a free surface the ghosts are revived.

```
paste captured/std.json: 2 entities as ghosts on nauvis (force player), origin 100,50, 2 placed by the game; robots build them
  placement std: std at 100,50, area 100,50,114,63, 2 entities, rows:7c1e... (paste of captured/std.json, tick 777)
  fk look std / fk diff std judge its area; fk capture --from std --into FILE writes it as source again, anchored where it stands
```

**`fk register 8,-2,20,10 mini`** says what stands in the area is that artifact (built by hand,
Lua or an older toolkit). It records a placement and reports the differences against the design
(the diff's own report). When MODULE names a factory placed on the surface (or its module), the
standing entities become the toolkit's own too (`out/own`: the design's keys where they stand as
designed, `<factory>/registered/<name><k>` for the rest), so the next build converges them:
differences are laid fresh, taken up or swapped as for any build, no MISMATCH. `--as NAME` for
something no module stands for records the placement alone (its entities are `placed`, explained,
and a design laid over them is a MISMATCH naming it).

```
register 8,-2,20,10 as mini: 20 entities stand there, recorded as mini (a factory of this surface)
  placement mini: mini at 10,0, area 8,-2,20,10, 20 entities, rows:... (register, tick 4200000)
  own: 20 standing entities are the toolkit's own under mini now (1 of them not where the design has them: the next build of mini takes them up or swaps them, as any difference)
differences against the design (as fk diff says them):
  sense area 8,-2,20,10 tick 4200000: ok 20, unowned 1
  unowned  wooden-chest 12.5,4.5 nauvis:mini/registered/wooden-chest0: the toolkit's own, dropped from the design: the next apply removes it
```

**`fk capture --from std --into captured/std.json`** (or `--from X0,Y0,X1,Y1`) blueprints the
placement's area in the game and writes a Literal file anchored where it stands: `anchor` (the
placement's origin, or the area's corner), `entities` relative to the anchor (`wx`, `wy`) with
their blueprint positions (`bx`, `by`: how each is set), `bp`, `names` (`asm1`, ...), `ports`.
It prints the lines to paste into a module:

```
capture: 2 entities into captured/std.json, anchored at 10,10 on nauvis: 1 assembling-machine-1, 1 iron-chest
  in a module whose frame is the world's (the world design, or a plot at 0,0):
    std = Literal<file="captured/std.json"> @(10, 10)
    net out: std.asm1 -> <your new instance>
  on a plot at X,Y: @(10 - X, 10 - Y). Placed there, its entities land on the standing ones (ok, mated) and your new ones are ghosts
  names: asm1
```

**`fk look ID` / `fk diff ID`**: the existing look and diff over the placement's area, headed by
`placement ID: MODULE at X,Y [rot R], area ..., N entities, ARTIFACT (source, tick T)`. Cheap:
the area is already there. `fk diff` is new as a command (the diff of the game's design over an
area or a placement, with the mismatch and hand-edit lines the build's diff step prints).

**`fk adopt ID|AREA [--write]`**: see below.

## The mismatch rule (one paragraph, for TOOLKIT.md)

A build pastes only onto tiles it can explain. A world entity standing (or pending as a ghost) on
a design entity's tiles that the toolkit did not paste there is a MISMATCH: the diff names it and
its owner (`placement <id>`, `hand edit by <player>`, or `unknown` when the game names no one),
the apply refuses those design tiles, one line per conflict with the command that would resolve
it (`fk register AREA MODULE`: it is that artifact; `fk capture --from ... --into FILE`: put it in
the source as a Literal the design mates with; `fk adopt X,Y --into FACTORY/NET`: a carrier into
its net; `fk decon AREA` or by hand: take it out), and pastes the rest. Mating is no mismatch: an
entity standing with the same name, position and direction as the design's is `ok`, as always,
and the toolkit's own (what an earlier build pasted, in `out/own`) still goes up to the design or
is laid fresh. Inside another placement's area, what the design does not match is `placed`
(explained, no mark, not a foreign change); elsewhere the watch policy (keep / mark / revert /
strict) applies as before. Nothing is built over or around: the design is right, or the source
changes.

Verdict words new in 3.1: `conflict` (the standing thing), `placed`; `other-entity` carries
`owner`. `sense.conflicts(rep)` lists the MISMATCHes; `ApplyReport.refused` holds them;
`hand_edits` no longer reports "on X's tile; this build replaces it" (it does not). Checks:
`mismatch` from `diff` and `apply`. The `upgrade in place` path (2.1) now applies to the
toolkit's own only.

## The mating workflow (ten lines)

1. Something stands in the world: a hand build, a `fk paste`, a registered legacy block.
2. `fk capture --from std --into captured/std.json` (or `--from X0,Y0,X1,Y1`).
3. The file is anchored where it stands; the command prints the Literal line.
4. Write the module: `std = Literal<file="captured/std.json"> @(10, 10)`.
5. Add what is new: `box = Chest<provider> @(22, 11)` and `net out: std.asm1 -> box`.
6. Place the module where its frame is the world's (the world design, or a plot at 0,0); on a
   plot at X,Y write `@(10 - X, 10 - Y)`.
7. `fk build`: the diff says `ok` for every standing entity of the block (mated).
8. The apply pastes everything; the game leaves the standing ones, the new carriers are ghosts.
9. No `mismatch` line: the design explains every tile it touches.
10. The placement is `mate` now (the build's record); `fk look mate` reads it.

`tests/test_placements.py::MateRoundTripTest` does exactly this against a fake link.

## What `fk adopt` does and does not do

- With `--into FACTORY/NET` and tiles: V1's carrier adoption, unchanged.
- `fk adopt ID|AREA`: a diff over the area (settings read too), then each world edit as far as a
  small step goes:
  - a changed setting on a standing design entity (`settings.Drift.fields`, new): a proposed
    `set` line printed as a diff of the module source, after the instance's line: a chest's
    limit `set gears: bp.bar=4`, a request `bp.request_filters=...`, an inserter's filter
    `bp.filters=...`, a control behaviour `set gears.out: cb.circuit_condition={...}` (the raw
    `cb.`/`bp.` settings of 2.1). `--write` appends them (`    # fk adopt`);
  - a changed recipe: said as the instance's parameter (`give gears recipe=pipe`), no set line;
  - a foreign carrier next to a design net: `fk adopt X,Y --into FACTORY/NET` (V1);
  - anything else: "needs a Literal patch", with the capture command that makes one.
- It does not rewrite instances, move entities or edit nets; it never writes without `--write`.
- The selector is the key's top instance (`gears`), `.out`/`.in` for an inserter by its local
  name (AsmRow's `o0` is an output hand); nested instances are joined with dots and may need a
  hand edit of the written line.

## For the docs wave (TOOLKIT.md text now wrong or missing)

- "The build replaces a hand edit and tells you" (2.0, Rory 10-21): on a design tile it now
  refuses the tile instead (MISMATCH); settings set back and foreign things ordered out under
  `revert`/`strict` are still reported as before. `stop_on by-hand` / `fk build --yes` still
  cover those; a MISMATCH has no `--yes`: the source changes, or the thing is registered,
  captured or taken out.
- Add the command list entries above, the registry file, the mismatch paragraph and the mating
  workflow. `fk capture` gains `--from`/`--into`/`--names`; `fk adopt` gains the id/area form and
  `--write`; `fk look` takes a placement id where it took an area.
- PLAN-BUILD §3-5 "what exists": placements exist as above; `own.json` did not become the
  registry, it stays underneath (per entity) and the registry is per artifact.

## Tests

`tests/test_placements.py` (23): the file round trip and replace rule, `unique_id`, `rows_key`,
`resolve`; `from_apply` one record per plot plus `shared`, the apply's `rows`/`tick`, a rebuild
replaces; a build alone records (and `build` records once the apply step ran); `paste_rows`
(origin, turn), the `fk paste` command (record, rebuild, `--as`, a second id, free surface
revive, `fk placements`); the mismatch rule (a placement as owner, `placed`, mating ok, the
toolkit's own still upgrades, the apply refuses the tile and the paste lacks it); `fk register`
(a factory: own rows and differences; `--as`: placement only); `fk diff ID` headed, `fk look ID`
resolves; `fk capture --from` (file, lines, by id); the capture-write-place-build round trip;
`adopt.propose`/`write_proposals` and the `fk adopt` command (diff lines, `--write`, carrier vs
Literal patch). Adapted: `test_sense.test_layout_verdicts` (a chest on a belt's tile is a
`conflict`, not `marked`), `test_own` (the hand edit on a design tile is refused, not replaced).
Run green: test_placements, test_sense, test_own, test_apply, test_in_place, test_lab (107);
test_flow, test_look, test_dnp, test_turned, test_circuits, test_robots_reach, test_literal,
test_capital, test_terrain_flow in the background (see the report).

## Open

- **Free surfaces**: an apply on a free surface (the lab) runs no diff before the paste, so no
  MISMATCH check there; `fk alone --keep` lays the design over what stands, as documented.
- **`default_area`** does not consult placements (the design's own placements are its plots,
  already in the area); left as is.
- **Old `out/own` only**: a hand build never registered and never pasted is `unknown` on a design
  tile; `fk register` is the way to track it. A `fk paste` placement later covered by a module
  Literal keeps its record (the build's record covers the same ground); `fk placements` lists both.
- **Store pruning** (31-store open item): entries a placement's `artifact` refers to should be
  kept; not implemented.
- **`fk diff ID` for a lab placement** judges against the game codebase's design, not the alone
  workspace's; `fk look ID` on the lab area works (the look reads the world). A placement on
  another surface than the game's own is reported with its surface in the head line.
- The Lua side (`fk paste` revive, `fk capture --from`, `fk register`'s snapshot) reuses existing
  link calls; unchecked against a laptop server in this branch.
