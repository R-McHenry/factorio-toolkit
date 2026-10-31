# Toolkit 2.0.70: whole-base statistics are free to read, and the panel's graphs

Rory, 2026-10-30: "for fair play we can allow global statistics in regular runs too. The in game
factorio shows produced and consumed broken down by item and gives a time series data, so I guess
we should give that too."

## Fair play

`FAIR-PLAY.md` now lists whole-base statistics among the free reads: what the base holds
(`fk stock`) and its working capital (`fk capital`, 2.0.69), next to the production statistics,
which now include the panel's graphs. Watching the whole base for what broke is still not a free
read.

## `fk stats --series N` and `--fluids`

- **`--series N`** (with `--items`) adds the production panel's graph. The window's 300 samples
  are summed into N points, oldest first, and each point is shown per minute for made and used.
  Every window the panel has works: 5s, 1min, 10min, 1h, 10h, 50h, 250h and 1000h.
- **`--fluids`** reads the fluid statistics instead of the items'.

On the opus run's sim save sr1-d12i (two reads, 0.03 s together):

    stats nauvis: force player, window 1h, tick 4630061: 2 items
      iron-plate                          327        331    19635    19852      243038      239102
      per minute over the window, oldest first, 12 points of 5 min each (the production panel's graph):
      iron-plate made                   290 296 301 293 298 297 362 386 377 378 333 314
      iron-plate used                   297 305 294 291 300 303 441 405 368 325 315 319
    stats nauvis: force player, window 10h ... (--fluids --series 6)
      petroleum-gas made                241 258 357 451 429 725
      water made                        209 308 370 531 986 1440
