# 45-pairports: a tap between two ports routes (the flower's paired-lane nets)

Branch `claude/45-pairports`, cut from main 66f2759 (8ed76ca plus the T6 notes), 2026-11-09 late
morning, from the T6 flower's paper build in `lab-session\fk-t6` (the open flower laid out by `fk
layout` on the lab's stand-in ground).

## What failed

Every paired-lane net at the flower's top level failed, in every flower build so far: the thirteen
`_a|_b` nets of the T6 build (the rivers' taps to the core, `circuit_rg_works`, `circuit_rp_ridge`,
`fen_sb_works`), the same thirteen in the open paper flower of 23aaf45, and in the corridor flower
every corridor's pass-through pair (`flower/ce/p_fen_tap_a|_b`, ...) plus `fen_fecu`. The line:

    its two lanes come in paired, and no straight belt runs on from there past every machine to
    its end; not searched past 643x855 tiles: the next box costs more than the route's walk budget

The rule is 2.0.48's for a stack cell: a pair that comes in on one belt (`_prejoined`: both nets
start where a paired port's belt crosses in) is laid as one straight belt, every machine along it
handing on or off by one inserter. A river's tap leaves its mouth as one belt of two items (a
`PairM` joins them at a paired `out` port) and goes to a port of the core, with no machine on the
way; nothing hands on or off it, so any belt keeps both lanes, but the straight rule was the only
way such a pair could be laid, and two ports a flower apart are never in line.

## The change (`fkcore/route.py`, `_route_in`)

When `_straight` finds no line and the joined job has no sources, taps or drops (no machine on the
way), the pair is routed as one plain `NetJob` from where it comes in to its goals (the port tiles,
deduplicated: each side's goals name the same port), through `_route_in` again with the pair's
name, so the carriers carry `net=a|b` as before. The line reads `... ; both lanes on one belt from
its paired port, no machine on the way`. A pair with machines on it keeps the straight rule and its
message.

`tests/test_pair_ports.py`: a `PairM` whose pair port feeds a `TapArm`-like `Arm` 28 tiles east and
14 south; the pair routes, the connect check holds.

## Also on the branch

`tests/data/flower/ground_flower.py` (T6's stand-ins): the `Well`'s pumpjack at frame offset (9, 9),
the middle of a 20x20 frame the pin centres on the patch, so it stands on the middle 3x3 site (it
stood at (5, 5): `no-ore` on both wells); the `Shore`'s offshore pump at (5, 0), the frame's north
edge, so a frame placed on a lake's south shore pumps from the two rows north of it. The same two
edits in `lab-session\fk-t6\game\flower_ground.fk`, where `fen_water` is placed by hand at the
lake at 2980..3040,-560..-500 (`@(885, 101)`; water is no patch, so the placer cannot pin it).

## Measured

The T6 flower (`lab-session\fk-t6`, the open flower on the lab's stand-in ground, 36 modules placed
by `fk layout`), paper-built through `report_checks`:

| toolkit | route step | summary | failed |
|---|---|---|---|
| main 8ed76ca (10:20) | 998 s, everything new | 3350 routed, 0 kept, 2432 pass-through, 24 failed | 13 paired-lane nets (every one at the top level), 8 lab columns `core/field/N/r\|g`, `works/frames`, the two wells' crude pipes |
| this branch 8fedc87 (10:55, the routes above kept from the design db) | 191 s | 13 routed, 3350 kept, 2432 pass-through, 11 failed | the 8 lab columns (`not searched again: it failed on this same ground`), the two crude pipes and the water pipe (the `Shore` now stands at the lake, 250 tiles from fen's port: `a fluid pass takes 33 s`) |

All thirteen pairs route (`13 routed`, each line `...; both lanes on one belt from its paired port,
no machine on the way`); the top level: `13 nets searched, 0 failed, 14.6 s`. `works/frames`
routed this time: it is order-dependent, not blocked (it routes alone, turned or not).

Not this branch's, found on the way:

- **The core's lab columns** (`LabCol5`, 11x44) fail in every flower build and route clean in every
  build of the core alone (at the flower's position, with its terrain, with `territories.json`
  present). In the flower `core/field/0/b|p` is laid first with its trunk at 378,702, on the row
  `r|g` comes in on (its ports at w34, w36), and `r|g` finds no trunk; alone `b|p` goes to
  379,706 and both route. The column is tight (three trunks turn north in six rows to the stack's
  adjacent ports x3 and x4), so the order and the tie-break decide it: a design with room (the
  column a few rows taller, or the pair ports not adjacent) would route either way.
- **Long pipes**: the fluid router's search (`limit` 60000, `--effort normal`) does not reach a
  port 250 tiles away across the plot (`--effort high`, 400000, is the knob to try; the outcome
  goes to STATE.md with the lab paste).
- `fk upgrade_run` does not carry `.toolkit\fkroute.pyd` (the kernel the T6 copy had been given by
  hand): copied back from `.upgrade-8ed76ca\.toolkit`.
