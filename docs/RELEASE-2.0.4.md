# Toolkit 2.0.4 (2026-10-22): the second lead run's point fixes

The 2.0 run (`20261022-1036-lead-v2`) wrote its friction into a `FRICTION.md` beside its notes;
these are the point fixes it showed, done in parallel by seven dev workers on branches off `lead`.
Seven items from `toolkit-plan.md`'s stage A: seven branches merged, 747 tests OK (2.0.3 had 697).
A1 was also checked end to end on the laptop test server (Factorio 2.0.77, `tools/laptop_server.py
ghosts`); the rest are paper tests, and are listed as such where a game check would have helped.

## What a player sees

- **Single ghosts carry what the paste would have given them** (A1, the second lead run): on
  uncharted ground the paste is refused, and each entity placed one by one as a ghost now carries
  its recipe, underground end, requester requests, circuit conditions and settings, filters, fuel
  and item requests, and wires; a setting the game won't put on a ghost (a requester's
  trash-not-requested, a chest's bar) is named in `out\apply.txt` under SETTINGS. A design entity
  that stands but is ordered out for new settings gets its ghost too. The run's `helpers settle`
  and `helpers ugends` worked around exactly this; the laptop check shows all of it kept as ghosts
  and after a revive.
- **A stale checkpoint no longer pastes an old recipe** (A2): a build that starts after the layout
  steps (`--from diff` on the host) took `out/<step>/` as it stood even when the source had changed
  since, so write_layout wrote (and the paste laid) the old recipe. Each layout step now records
  the source it was laid from (`out/<step>/source.json`); a stale checkpoint (including an older
  toolkit's, which has no stamp) is laid out again, every step and checkpoint. `fk look` judges
  the new `.fkp` against the old game as DRIFT, and notes a placed module's `.fk` change not built
  yet.
- `fk stage` carries the file each Literal reads (relay.json beside relay.fk, or stage 7's
  plant-40mw.json) with the source: `edit` keeps it in the stage it edits, the stages replayed
  after it get it, and a stage that adds or edits a Literal checks, measures and applies with its
  file (the run: every check said "relay.fk Literal: No such file" and the horizon had no rates).
  A file outside the codebase or in out\ is not carried.
- **A changed requester's request is pasted again** (A3): raising a standing requester's `max=` or
  `rate=` in the source left the game's request at its old count until `helpers settle`; the
  record's settings signature now includes `request_filters` (and `trash`), so the next `fk build`
  orders the chest up and its paste writes the new request. `max=` also caps `count`: `max=4` used
  to write `count: 10, max_count: 4`, which the game refuses; the count is clamped to `max_count`
  in the source and, defensively, in the codec for a hand-written config.
- `fill=N` (A7): every inserter that feeds the machine now takes the same `if=ITEM<N` condition on
  the same red wire as the inserter that takes its product into the chest, so the machine is held
  too and finishes at most the craft in progress (the run made 9 for a fill of 6). A machine with
  no input inserter to gate (fed by a belt or the ground) gets a `LIMIT` line: it keeps crafting
  past N, and `keep=` may suit better.
- **`fk wait built` waits on a bound, and a look flags an unpaired underground belt** (A11): workers
  hand-rolled their own polling loops (one waited forever on a mall deadlock) because the toolkit
  had no bounded wait. `fk wait built [AREA] --max 5m [--name ENTITY]` polls the area through the
  game link until no ghosts are left, then prints one line: 0 clear, 1 the bound expired with
  ghosts left, 2 a link error. `fk look` also prints an `UNPAIRED` line for each built underground
  belt whose partner is missing or is another end of the same kind (the mall's six outputs never
  formed a tunnel), with its position. Off-game tested only; the pair read mirrors v4's
  live-tested `e.neighbours` and is pcall-guarded.
- **`BOOTSTRAP`** (A12, `report_checks`, a warning, never a gate): a net whose own route needs a
  building item (a belt, an underground, a splitter, an inserter) that only a maker fed from that
  same net makes, so neither can be built before the other. The mall's last ghosts were four
  underground belts carrying the mall's own iron, behind the only maker of undergrounds. One line
  per net, naming the item, how many the route lays, the maker and what it takes from the net;
  none when the item comes from outside or another maker is fed elsewhere. It names a factory that
  makes its own belts wherever it uses them, which is true as a from-zero warning.

## Left for 2.0.5

A4 (a burner row's first fuel load as the blueprint's item request), A5 (any chemical fuel: wood
and solid fuel, not coal only), A8 (recipe and settings set in place, on a standing machine), A9
(a bridge through ground no powered roboport reaches is re-routed), A10 (a route-length warning
for a move). A8 and A4 want a laptop game check before they ship.

## Docs

`agent/docs/TOOLKIT.md`: single ghosts on uncharted ground, a resumed build's checkpoints and the
look's note, `fk stage` and Literal files, `fk wait built`, `UNPAIRED`, `BOOTSTRAP`.
`agent/docs/LANGUAGE.md`: `fill=` holds the machine, and a changed request is re-pasted.
