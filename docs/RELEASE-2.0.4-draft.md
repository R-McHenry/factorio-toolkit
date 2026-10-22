# Toolkit 2.0.4 (draft): point fixes

- `fk stage` carries the file each Literal reads (relay.json beside relay.fk, or stage 7's
  plant-40mw.json) with the source: `edit` keeps it in the stage it edits, the stages replayed
  after it get it, and a stage that adds or edits a Literal checks, measures and applies with its
  file (the lead-v2 run: every check said "relay.fk Literal: No such file" and the horizon had no
  rates). A file outside the codebase or in out\ is not carried.
