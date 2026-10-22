# Toolkit 2.0.4 (draft): point fixes

- **Single ghosts carry what the paste would have given them** (A1, the second lead run): on
  uncharted ground the paste is refused, and each entity placed one by one as a ghost now carries
  its recipe, underground end, requester requests, circuit conditions and settings, filters, fuel
  and item requests, and wires; a setting the game won't put on a ghost (a requester's
  trash-not-requested, a chest's bar) is named in `out\apply.txt` under SETTINGS. A design entity
  that stands but is ordered out for new settings gets its ghost too.
- `fk stage` carries the file each Literal reads (relay.json beside relay.fk, or stage 7's
  plant-40mw.json) with the source: `edit` keeps it in the stage it edits, the stages replayed
  after it get it, and a stage that adds or edits a Literal checks, measures and applies with its
  file (the lead-v2 run: every check said "relay.fk Literal: No such file" and the horizon had no
  rates). A file outside the codebase or in out\ is not carried.
- **A changed requester's request is pasted again** (A3, the second lead run): raising a standing
  requester's `max=` or `rate=` in the source left the game's request at its old count until
  `python -m helpers settle shop force`; the record's settings signature now includes
  `request_filters` (and `trash`), so the next `fk build` orders the chest up and its paste writes
  the new request. `max=` also caps `count`: `max=4` used to write `count: 10, max_count: 4`,
  which the game refuses; the count is clamped to `max_count` in the source and, defensively, in
  the codec for a hand-written config.
- `fill=N` (A7): every inserter that feeds the machine now takes the same `if=ITEM<N` condition on
  the same red wire as the inserter that takes its product into the chest, so the machine is held
  too and finishes at most the craft in progress. A machine with no input inserter to gate (fed by
  a belt or the ground) gets a `LIMIT` line: it keeps crafting past N, and `keep=` may suit better.
- **`fk wait built` waits on a bound, and a look flags an unpaired underground belt** (A11, the
  second lead run): workers hand-rolled their own polling loops (one waited forever on a mall
  deadlock) because the toolkit had no bounded wait. `fk wait built [AREA] --max 5m` polls the
  area through the game link until no ghosts are left (or the named entity's are gone), then
  prints one line: 0 clear, 1 the bound expired with ghosts left, 2 a link error. `fk look` also
  prints an `UNPAIRED` line for each built underground belt whose partner is missing or is
  another end of the same kind (the mall's six outputs never formed a tunnel), with its position.
