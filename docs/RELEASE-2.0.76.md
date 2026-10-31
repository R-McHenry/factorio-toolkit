# Toolkit 2.0.76: shared belts that don't jam

Rory, 2026-10-31: "figure out why we keep getting shared belt jams. The fk toolkit should be both
providing a warning and alternate way to route where it uses filtered inserters to load onto two
different lanes with one inserter per lane and some merging structure."

## Why the belts jammed

The runs' jams (10-29: bq -> bsc engines/circuits/sulfur, the blue belt full of plastic; 10-30: a
furnace's stone and coal on one belt, no fuel) had three causes in the toolkit:

1. **The loading inserter was never filtered.** The router lays an inserter from a requester onto a
   net's belt with no filter, so it put *everything* the chest held on the belt, items of other
   nets included (the plastic no sink on that belt took). Nothing in the toolkit set a filter
   except a circuit guard.
2. **`lanes A | B` from one chest didn't separate anything.** The pair router already lays the
   right shape (one inserter per lane, the two belts side-loaded together), but both inserters
   were unfiltered, so both lanes got both items and the pair was a sushi belt in disguise.
3. **The warning was out of sight.** `CLOG` is in elaborate's `ADVICE` family, and
   `fk stage check` printed only advice counts, never the lines, so a player checking a stage saw
   `CLOG 1` among the totals and no text.

Long-handed inserters made 1. worse: the router uses one where no fast inserter reaches, and a
long-handed inserter can't take a filter at all (10-29's "sushi belt with long-handed inserters,
which clogged with plastic").

## What changed

- **Filtered loads** (`route._filter_loads`): after routing, every route inserter that picks from a
  machine making items its net doesn't carry gets `filter=` its net's items (up to the fast
  inserter's 5). One with a filter already (`filter=circuit`) is left alone. A loader that can't
  take the filter (long-handed or plain, or more than 5 items) gets a route report line,
  `unfiltered NET: ... can clog it`. A rebuild adds the filter to standing loaders (a settings
  change, no re-lay).
- **Fast hands first for those sources**: the router tries fast inserters alone for a multi-item
  source before it lets a long-handed one load it.
- **`net NAME split:`** (LANGUAGE.md "Nets"): one net per item (`NAME_<item>`), paired two to a belt
  as `lanes` pairs, an odd last item on a belt of its own. With the filters each lane gets its own
  inserter and item, and `fkcore.pairs` side-loads the lanes together. A full lane stops only
  itself.
- **The warning**: `CLOG`'s line names the fix (`net blue split:`), and `fk stage check` prints the
  loud advice lines (`CLOG`, `SHARED_SINK`, `SUSHI_LIMIT`) as well as the counts.

## Verified

- `tests/test_split_lanes.py` (12 tests): a sushi loader filtered to its net's items, a pair from one
  chest one item per lane, a single-item chest left unfiltered, the filter through `.fkp` into the
  blueprint fields, split's nets and pairs, the routed split with a filtered loader per lane, the
  `unfiltered` line.
- `tests/data/elaboration-baseline.json`: 8 designs' digests moved, and each was checked to differ
  only by `CLOG`'s new last sentence.
- The full suite: **1139 tests, OK** (on 2.0.75).

## Not done

- Nothing reaches a run until it is upgraded (`kickoff/upgrade_run.py`).
- Not tried in the live game or the lab yet: the in-game check is a split net from a requester
  into two assemblers (`fk lab`), watching each lane hold one item.
