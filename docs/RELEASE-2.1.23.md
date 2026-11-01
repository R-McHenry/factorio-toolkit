# Toolkit 2.1.23: many-to-many at higher throughput

Rory, 2026-11-01: "lets see some higher throughput example with more lanes". Only `route --m2m`
changes (the golden examples don't use it).

## No fixed run cap

An m2m net may add `_RUNS_A_LANE` (5) runs a lane of its demand, or 24 where that is more. A run
adds one driver's worth or one lane, so a 64/s net needs about 30: under the old cap of 24 the
32-to-16 case stopped at 45.5 of 64/s.

## Higher-throughput cases on the bench

`tools/hourglass.py --big` (and `hourglass_png.py --big`) adds three cases, producers at 2/s (one
fast inserter's worth: a chest has one tile a side):

| case | demand | lanes | waist (fewest) | splitters | cost | time |
|---|---|---|---|---|---|---|
| 24to24 | 48/s | 6.4 | 5 belts (4) | 28 | 363 | 4 s |
| 32to16 | 64/s | 8.5 | 7 belts (5) | 44 | 693 | 24 s |
| 32to32 | 64/s | 8.5 | 7 belts (5) | 38 | 537 | 11 s |

Every one meets its demand with full reach and no side-load; today's router stops at one belt
(15/s). The waist is wider than it needs: many crossing runs carry one lane (the lane images show
the other one grey). The images draw m2m and today only: the bench's balancer harness lays no
more than a few belts.
