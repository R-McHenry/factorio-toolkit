# 2.1.27: the steps after route spend less, the rate model is solved once

Rory, 2026-11-01: "you can start looking at other build slowness and optimizations to be done".
Measured with `tools/buildbench.py` on the 20261030-2352 world (the benchmark copy of 2.1.26),
each step from its checkpoint, 30 s probes:

| step | 2.1.26 | 2.1.27 |
|---|---|---|
| cover_power | 30+ s (still running at the probe's cap) | 11.5 s |
| the nominal rate model (`rates.solve`, live world) | 6.5 s, 1233 passes | 1.6 s, 533 passes |
| hands | 7.8 s | 7.8 s (it solves the model the others reuse) |
| tier | 8.2 s | 4.2 s |
| report_rates (2nd): one coupling round | ~1.2 s, 7 inner rounds an item | ~1.0 s, 4 |

## What changed

- **cover_power lays its poles once.** `s_cover_power` ran `cover.cover_power` and then
  `apply_cover`, which ran the whole cover again (~30 s each on this world); it now applies the
  poles the first run laid. The prune's wire groups (`_groups`) look only at poles in the
  neighbouring cells of a grid (cell = the longest reach) instead of every pair, and
  `_Ground.free` checks a spot in one pass. Same poles, same report.
- **The rate model is solved once per build.** hands, tier and both report_rates each ran
  `rates.solve` on the same netlist (~3 s apiece here). `Ctx.model(factory)` keeps it per flat;
  `hands.assign` and `tiers.assign` take it as `model=`.
- **A swinging rate solve restarts sooner.** 2.1.26 restarted a solve that had not settled at
  pass 1000 with a smaller step. It now also restarts when the largest change over 100 passes is
  not half the one over the 100 before (`rates.SWING_WINDOW`, `SWING_DROP`): the live world swung
  by 0.05-0.2 all its first 1000 passes and restarts at pass 200. A solve that settles is solved
  as before.
- **The machine coupling's item solves start warm.** `throughput.solve` solves every item twice
  each outer round from little changed supply and demand. Each item's solve now starts from where
  its last one ended (at least two rounds, so a stale start cannot pass for settled): 7 inner
  rounds to 4. The coupling itself still needs ~51 rounds on this world, and the frozen live world
  (`tests/golden/live-20261101`) does not settle within the 60 s budget at all; what it reports
  then depends on how many rounds fit. That is the next one to look at.
- **buildbench measures without slowing the build.** Its sampler used `traceback.extract_stack`,
  which stats every source file (linecache) and took ~0.3 s a sample, holding the build back;
  it now walks the frames.

## Checked

- golden: 60 of 61 identical with 2.1.26; the live world differs only in where its unsettled
  coupling stopped (2.1.26: round 62, 2.1.27: round 79, both "did NOT settle"); its model line says 533 passes, not 1233.
- tests: test_build_speed_2126 (the live world's model now settles in under 700 passes),
  test_cover, test_power_domains.
