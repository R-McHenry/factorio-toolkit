# Toolkit 2.0.4 (draft): point fixes

- `fk stage` carries the file each Literal reads (relay.json beside relay.fk) with the source, so
  a stage that adds or edits a Literal checks, measures and applies with its file (the lead-v2 run:
  every check said "relay.fk Literal: No such file" and the horizon had no rates).
