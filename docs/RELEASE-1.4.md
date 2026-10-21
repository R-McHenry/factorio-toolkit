# Toolkit 1.4 (2026-10-20): machines handed to each other by inserters

1.3 (V2's first round: routed rates, `CAPACITY`, the `tier` step; `docs/RELEASE-1.3.md`) plus the
router's direct insertion between neighbours and the player docs for malls. As before there are no
new rules: the router does more by itself, and the docs show what that allows.

## New

- **A machine hands to every neighbour by an inserter of its own** (Rory, 2026-10-20: a mall placed
  with care should get inserters, not belts, between machines that stand next to each other).
  Direct insertion was only for a net of one machine driver and one consumer. Now a net with one
  machine driver gives every consumer within reach (a fast inserter across a 1-tile gap, a
  long-handed one across 2 or 3) an inserter of its own, and lays a belt tree only for the
  consumers left (`fkcore.route._hub_job`).
- **Several machines beside one consumer** hand to it by an inserter each, the same way (two cable
  assemblers beside one circuit assembler).
- **Direct inserters are claimed before any tree is laid.** The router lays nets with more belt
  ends first, so machine-to-machine nets came last and found their tiles under the trees; now
  every one-driver net claims its inserter tiles first and the others route around them
  (`_direct_claims`).
- **Malls in the player docs**: `docs\examples\mall.fk` (single machines and a row mixed, 179
  entities where one row per product took ~700) and `docs\examples\early-mall.fk`, the early tier:
  yellow and red belts, undergrounds, splitters, the three inserters, assemblers, drills, pipes.
  Each machine stands within 3 tiles of what it feeds, so 24 of its 30 nets are inserters only and
  83 belts bring the iron, copper and circuits (the 2005 run's rows mall: 547 belts for 10
  products). Its placement was found with the router itself as the judge (a local search).

## Compatibility

Pinned routes stay as they are (`route --only stale`); a net routed again may now get inserters
where it had belts. A 1.2 run's build script has no `tier` line and runs `report_rates` before
`place`, so the V2 steps add nothing to its builds until the player adds them (the upgrade note
says how).

## Checked

- 413 tests (`python -m unittest discover -s tests`).
- The early mall built in the game on a laptop test server (2.0.77, lab mode, its requesters
  topped up): all 66 inserters' pickup and drop targets are their net's machines or belts, none
  faces the wrong way, every product link moves items and all 13 chests fill. The fast-inserter
  and drill assemblers waited 13.5 minutes for circuits behind a cable-starved circuit assembler:
  the second cable assembler beside it, and the router's several-drivers case, came from that.

## Handing it to a running run

As for 1.2: deploy as `fk-v5-SHA`, then `kickoff/upgrade_run.py RUN --sha SHA` (only with Rory's
approval). From a 1.2 run it prints the note for 1.3 and 1.4 together.
