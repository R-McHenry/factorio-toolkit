# Toolkit 2.1.9: a run's prelude lies over the toolkit's

Until now a run's `game\prelude.fk` replaced the toolkit's `fkcore\prelude.fk` whole. A run that
got its prelude at one release never saw a kind added in a later one: `Buffer` (2.1.8) was unknown
to every run whose prelude was copied at 2.1.5, and the circuit presets, `PowerSwitch` and the
library would have gone the same way.

Now a file gets both, nearest first:
- its own kind and tiers lines (and its imports');
- the run's `game\prelude.fk`;
- the toolkit's `fkcore\prelude.fk`.

A line in the run's prelude replaces the toolkit's line of that name, as before. A name the run's
prelude doesn't have comes from the toolkit's. Nothing changes for a run that has no prelude of its
own, or for a file whose names its run's prelude already covers.

- `fkcore.elaborate.preludes(src)`: the preludes a file gets, nearest first.
- Test: `tests/test_machine_kind.py`, a run prelude with only `Assembler` gets the toolkit's
  `Furnace`, its tiers, and `Buffer`.
