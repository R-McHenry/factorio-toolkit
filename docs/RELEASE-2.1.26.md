# 2.1.26: builds say where their time goes, the rate model settles, a hopeless route gives up fast

Rory, 2026-11-01: "it seems like a new run is stuck on dry runs which should not take long". The
20261030-2352 run's dry builds (`fk build --to diff`) ran past 20 minutes: the tool call's
timeout killed the first, and the next waited on its lock. Measured on a copy of its world
(`tests/golden/live-20261101`):

| step | 2.1.21 | 2.1.26 |
|---|---|---|
| read_surface .. size | 2.7 s | 2.7 s |
| report_rates (twice a build) | ~290 s each | 4.4 s |
| place | 3.5 s | 3.5 s |
| route: coal, a pass | 250-304 s, then failed | 6 s, then failed |
| route: passes | up to 45 (one per stale net + 2) | 2: the first and the promoting one |
| route, the whole step | 15+ min (stopped, never seen to end) | 49.5 s |
| the dry build, to its stop | 20+ min (killed) | 63 s (`stop_on no-route`: coal) |

## What changed

- **The rate model settles.** `rates.solve` damps each pass's change by 0.5. On this world the
  belt mall's gear -> yellow belt -> fast belt chain (BeltMall2: 8 machines) swung by 0.16 for
  all 50000 passes (~5 min), and the report was a snapshot of the swing. A solve that has not
  settled after 1000 passes starts again from the first grants at 0.25 (then 0.1 after 3000 more):
  this world settles in ~250 passes, ~1 s. A model that settles at 0.5 is solved exactly as
  before. The report's first line says when a smaller step was used, and `NOT SETTLED` when none
  settled.
- **A route search has a budget.** A net that fails in its own neighbourhood was searched again
  in the whole frame. The hub and join searches flood the frame once per end, so the world's coal
  (a pair net: 28 ends, a 1558x1250 frame, 54M tile visits) took ~250 s, every pass, and failed
  there too. When the whole frame would cost more than `route.WALK_BUDGET` (3M visits, ~15 s),
  the net is searched in boxes twice as big in turn as far as the budget allows, and fails saying
  how far it looked. Under the budget it is the neighbourhood, then the frame, as before.
- **No pass repeats the one before.** A route that leaves a net unrouted tries again, the failed
  nets first, up to once per stale net. When that order is the order it just ran (coal failed
  first in order), the next pass lays exactly the same, so the route goes on to its last,
  promoting pass. The score keeps the first of equal passes, so the result is the same.
- **Builds say where their time goes.** `out/timings.txt` has each step's time; a step of 10 s
  or more says it on its summary line (`[ 6/22] report_rates ... [287 s]`).
- **The route progress line names the slow net.** It named only the net starting, so 300 s on
  coal read as `net 2 of 43 (larea/b)`. A net of 30 s or more is now named when it ends:
  `route: 310s in, pass 1: coal took 304 s; next net 2 of 43 (larea/b)`.

## Benchmarks

- `tools/buildbench.py GAME_DIR [--to STEP] [--cap S]`: a copy of a run's design built offline to
  `report_checks`, each step and each net of 2 s or more timed, stopped at the cap (default 120
  s) with the step and net it was in.
- `tests/test_build_speed_2126.py`: the live world's model settles in under 2000 passes; the
  ladder and the budget.
- `tests/golden/live-20261101`: the world frozen as the golden check's second live design.

## Not changed

The coal net still does not route on this world: the build's `route.txt` says why. Its standing
route was stale (fe_el3/outb7 side-loads onto ~coal/b163), and laying it again fails; that is the
design's to fix, now in seconds.
