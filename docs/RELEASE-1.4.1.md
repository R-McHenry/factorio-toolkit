# Toolkit 1.4.1 (2026-10-21): the routed rates settle, CAPACITY names the right connector

Fixes from the lead's review of the V2 code in 1.3/1.4 (run offline on a copy of the 2005 run's
game: unchanged scripts were byte-identical; with `tier minimize --allow yellow` and a second
`report_rates` after `route`, the problems below). No new rules: checks warn, never gate. It also
carries what main got after 1.4: direct insertion never costs a net (`d7fdc07`) and the Claude
loop's watcher reading a laptop-hosted run's world (`b41d121`).

## Fixed

- **The machine coupling settles** (`fkcore/throughput.py`). On the 2005 base it used all 40
  rounds and capping at 40 or 41 moved 15 of 88 machines by up to 0.12. Three causes:
  - an endpoint served in full jumped to a grant of 1, so near its supply it swung between
    "unlimited" and the real supply; now it gets what it asked and a margin, halved each time it
    turns from served to short or back, and each grant moves by its own step, halved when it
    turns. The 2005 base (a copy from 01:06) settles in 47 rounds (cap 80), 6.0 s instead of 16 s;
    other step and margin factors give the same utilizations within 0.0003;
  - a machine node got item shares of its capacity, and infinite capacity times a share of 0 is
    NaN: a cable maker held by its output inserter lost its copper every few rounds (it read 0.59;
    it is 0.43);
  - a requester chest was a machine whose items a recipe tied: a chest of three parts and the
    engine assembler it feeds held each other down to nothing (0.0009; it is 0.333). A requester is
    now a source per item.
  The report says "the machines settled in N rounds", or that they did NOT and the routed rates
  are approximate; "limited by" now names the endpoints that hold a machine, never blank.
  Unchanged items are not solved again within a coupling round.
- **CAPACITY names the right connector and the right victims** (`fkcore/routed.py`). A chest
  without a rate on a net where something else takes the item is overflow: nothing is required
  into it and it is never short (the inserter into the copper chest was named binding for the
  net's whole surplus). A line now needs a consumer short of the net's item: a machine that item
  holds below nominal (not one held by another input or by its output backing up), a sink with a
  rate, or the labs together.
- **The inserter hand size is the force's** (`--hand auto`, the default for `report_rates` and
  `tier`): read over the game link, else from `out/force.json`, which every `diff` writes on the
  game host (the agent kit designs on the laptop, where there is no link), else 1, and the report
  says which. `--hand N` still sets it.
- **`tier` keeps what is built** (`fkcore/tiers.py`). Minimize and maximize never put a belt
  below its tier unless `--downgrade`; a tier's reach (`max_distance` 5/7/9/11) must cover an
  underground pair's tunnel (a red pair 6 apart stays red); after assigning, the pairing is
  checked as the game does it and a pair whose partner would change keeps its old names; budgets
  count only gains. `--allow` defaults to yellow (a bare `tier minimize` could ghost turbo belts).
- **The flow script**: a step run twice adds its report after the first's in `out/<step>.txt`
  (it overwrote it); the second `report_rates` adds only new checks (`CAPACITY`, a `TARGET` the
  routed rates miss and the nominal ones meet), no repeated `ASSERT` or `TARGET`; `--from`/`--to`
  take `NAME:K` for the K-th time a step runs (also in `fk build`); a bad or bare `--red`,
  `--hand`, `--allow` is a script error, not a traceback or ignored.

## Not changed

V1's rate model (`fkcore/rates.py`) ties a requester's items together the same way: that
engine assembler and its chest are 0.000 nominal, as is the 2005 run's blue science
(CORE-V2.md, Open 7). The invariant check still does not look at underground pairing; `tier` no
longer breaks it.

## Checked

- 430 tests (`python -m unittest discover -s tests`): new ones for the coupling (the cable maker,
  the engine and its requester, redgreen settling, the not-settled wording), overflow chests, a
  fluid-bound plant fed by a requester without a rate, the tiers (red stays red, budgets, a red
  pair 6 apart, a pairing revert, pinned keys), the flow script (a step run twice, `NAME:K`, bad
  numbers) and the kickoff template's script, its plant a Literal with fluids, through the second
  `report_rates`.
- The 2005 run's game, copied at 01:06 and run offline (no link) with `tier minimize --allow
  yellow` and a second `report_rates`: every factory settles (base 47 rounds, shop 21, oil 1).

## Handing it to a running run

As for 1.2: deploy as `fk-v5-SHA`, then `kickoff/upgrade_run.py RUN --sha SHA` (only with Rory's
approval; the lead decides).
