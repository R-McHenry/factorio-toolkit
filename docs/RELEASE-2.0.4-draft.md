# Toolkit 2.0.4 (draft): point fixes

- **Single ghosts carry what the paste would have given them** (A1, the second lead run): on
  uncharted ground the paste is refused, and each entity placed one by one as a ghost now carries
  its recipe, underground end, requester requests, circuit conditions and settings, filters, fuel
  and item requests, and wires; a setting the game won't put on a ghost (a requester's
  trash-not-requested, a chest's bar) is named in `out\apply.txt` under SETTINGS. A design entity
  that stands but is ordered out for new settings gets its ghost too.
- **A changed requester's request is pasted again** (A3, the second lead run): raising a standing
  requester's `max=` or `rate=` in the source left the game's request at its old count until
  `python -m helpers settle shop force`; the record's settings signature now includes
  `request_filters` (and `trash`), so the next `fk build` orders the chest up and its paste writes
  the new request. `max=` also caps `count`: `max=4` used to write `count: 10, max_count: 4`,
  which the game refuses; the count is clamped to `max_count` in the source and, defensively, in
  the codec for a hand-written config.
