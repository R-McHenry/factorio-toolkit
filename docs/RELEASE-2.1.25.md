# 2.1.25: an inserter dropping onto a turn, measured; the lab now agrees with the rules

Rory, 2026-11-01: "exact balance isnt ususally that important if the flow can still get to
equilibrium. that equilibrium backpressure might be where the mismatch is". The mismatch was 2.1.24's
4to16: 84% in the lab while the game's rules (`fkcore.throughput`) said 100%.

## It wasn't the back-pressure

The lab's lanes at equilibrium showed it. The last producer in 4to16 drops onto the corner of a
left turn, and 584 plates were waiting at it while the others held 4. In the game, everything it
dropped was on the turn's left lane. `fkcore.lanes` had put it on the right lane, as for a straight
belt in line. That lane was the one with room, so by the rules the producer was never held back.

## The rule, measured on 2.0.77 (`fkcore/lanes.py`, `_turn`)

An inserter dropping onto a turning belt fills:

- **from either outer side, the inside lane**: a left turn's left lane, a right turn's right lane;
- **from an inner side, the outside lane**: this is a long-handed inserter reaching over the belt
  that comes in or goes out.

Drops onto straight belts are unchanged (across: the far lane; in line: the right lane). The 2.1.25
measurements re-checked those too. `tests/test_throughput.py` `test_drop_onto_a_turn_fills_the_inside_lane`
covers all four sides.

## The lab (`tools/hourglass_lab.py --big`, 300 s warm-up, 240 s measured)

| case | demand | game 2.1.24 | game 2.1.25 | rules 2.1.25 | short in the game | short by the rules |
|---|---|---|---|---|---|---|
| 4to16 | 8.8 | 7.4 (84%) | 8.8 (100%) | 8.8 | none | none |
| 16to16 | 22.4 | 20.8 | 21.2 | 21.5 | c0 0.50, c6 1.06 | c0 0.50 |
| 24to24 | 48 | 45.8 | 45.8 | 44.5 | c23 0.20, c15 1.41 | |
| 32to16 | 64 | 61.4 | 61.4 | 61.5 | | |
| 32to32 | 64 | 59.4 | 60.2 | 61.2 | c3 0, c12 0.64 | c3 0.5, c12 0.75 |

Wherever a consumer is short, the rules now name the same consumers as the game, and the totals are
within 1/s. The small cases, the balancer and today's router are unchanged, at 100% (today's router at
its one belt).

## The bench (`tools/hourglass.py --big`)

m2m reads lanes through the same model, so its layouts move a little:

- 4to16 now spends two side runs (cost 105 -> 120) to deliver 8.8 by the rules. 2.1.24's
  layout only looked complete.
- 16to16: cost 199 -> 192, rules 21.0 -> 21.5.
- 24to24: cost 335 -> 328.
- 32to32: cost 431 -> 438, rules 61.8 -> 61.2.

## Golden

59 of 60 are identical. `tests/golden/live-20261030/world.fk` differs in four diagnosis lines. In
the live base, `blue/en1` and `blue/en2` (0.18 each by the old reading) now read 0 and 0.36.
`labs/b`, `red_s` and `bpk` name another lane or rate. These are the live base's drops onto turns,
read by the measured rule.

## Open

- m2m still leaves one or two consumers short on the big cases (93-96%). As Rory says, exact
  balance matters less than reaching equilibrium. Every case reaches one, and the rules now
  predict it.
