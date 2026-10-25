# Toolkit 2.0.24: the sushi warning works; the rate model did not

Rory, 2026-10-25: "see if you can figure out if the sushi net warning is working. It looks like the
agent is investigating red herrings after it broke the smelter iron input by putting iron and coal
into one requester on the same net".

**The warning works.** The 1133 player's `smelter.fk` feeds one requester of iron-ore and coal into
the row, and the design's own checks say it:

> `CLOG  net feed: iron-ore, coal share one belt: one that comes faster than it is used can fill it
> and stop the others ...`

It is in `out/report_checks.txt` on every build. The player ignored it and spent twenty minutes on
`recipe=nil` furnaces — a red herring, since a stone furnace with no recipe smelts whatever it
receives (its own notes reached that conclusion in the end).

**The rate model did not.** For exactly that design `report_rates` said the cell ran at `0.000/min`,
`coal not taken on feed`, `iron-ore short on feed` — a second, contradictory diagnosis that reads as
a broken net. Two bugs behind it:

1. **A multi-item source on one net decayed to zero.** `potential(k, skip)` skipped only the one
   item's grant, so a chest driving iron-ore and coal on the same belt had each item's grant computed
   from the *other* item's (2.5/3 and 0.18/3): the pair multiplied itself down geometrically and the
   solver settled at 3e-13 after 62 passes. Fixed: a machine's grants on one net are skipped together
   (they travel on one belt), in the solver and in the measure pass. The same cell now reads 3.00/s
   supply for each item, 2.50/s iron-ore and 0.18/s coal delivered, 2.50/s plates, furnaces at 1.00 —
   identical to the two-chest design.
2. **"not taken on NET" read as a fault.** The line is the binding text for an output limited by what
   the net takes; it now says what it takes (`firearm-magazine: out takes 0.20/s`).

Tests: `tests/test_sushi_rates.py` — the warning fires; the mixed cell delivers like two chests; a
sushi source supplies each item at its own rate (the coal appetite does not cap the iron); the report
no longer calls a consumed item unwanted. `tests/test_rates.py` follows the new wording.
