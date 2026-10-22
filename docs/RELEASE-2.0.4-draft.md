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
