# Toolkit 2.0.4 (draft): point fixes

- **`fk wait built` waits on a bound, and a look flags an unpaired underground belt** (A11, the
  second lead run): workers hand-rolled their own polling loops (one waited forever on a mall
  deadlock) because the toolkit had no bounded wait. `fk wait built [AREA] --max 5m` polls the
  area through the game link until no ghosts are left (or the named entity's are gone), then
  prints one line: 0 clear, 1 the bound expired with ghosts left, 2 a link error. `fk look` also
  prints an `UNPAIRED` line for each built underground belt whose partner is missing or is
  another end of the same kind (the mall's six outputs never formed a tunnel), with its position.
