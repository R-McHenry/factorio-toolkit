# 2.1.28: what the player waits on: place, fk lua, every pull

Rory, 2026-11-01: "use play and amount of time spent waiting as your estimate of what to
optimize". From the 20261030-2352 player's transcripts (tool call to result, per command):

| what | calls | each | share of the session |
|---|---|---|---|
| `fk lua` (10-31 23:42 .. 11-01 04:54) | 230 | median 10 s, ~0.2 s of it the game | 24% of 312 min |
| `fk lua` (10-31 06:31 .. 23:42) | 577 | avg 23 s | 22% of 1030 min |
| a dry build on 2.1.21 (11-01) | 1 | 20+ min (fixed in 2.1.26) | |
| place, the first build on 2.1.27 | 1 | 31 s of the build's 38 | |

Measured on a copy of the run:

| step | 2.1.27 | 2.1.28 |
|---|---|---|
| place (the run's world) | 34.5 s | 0.5 s |
| a pull (every host command) | 6.0 s | 2.3 s |
| `fk lua` | push + game + pull, 8-10 s | push + game, ~1-2 s |

## What changed

- **place finds a port's partner in its own module.** Choosing a port's tile looks up where the
  other ends of its nets stand; for a partner that is another module's port, `_point_of` computed
  `port_edges` of every module (each expanding its fragment) to read that one port. It now
  computes the partner module's edges only (`expand._module_edges`). Same place report, same
  layout.
- **A pull skips what the last pull left as it is.** `fk.py`'s pull hashed every file of game\
  that the host also has and wrote every host-made file again, ~450 files, each command. A file
  whose size and mtime (a pull keeps the host's) match the host's is now neither hashed nor
  written; an edit here still wins, as before.
- **fk lua pulls nothing.** A chunk runs in the game and writes nothing in game\; the next
  command's pull brings the footer's cursors.

## Checked

- place: the run's world on 2.1.27 and 2.1.28 gives the same out\place.txt, layout-source.json
  and place checkpoint.
- pull: after two pulls on a copy of the run, all 418 files the host has match it (sha1).
- tests: test_sync_2128 (new), test_agent_kit, the port and module tests; golden against 2.1.27: 60 of 61 identical, the live world differing only in where its unsettled coupling stopped (round 72, 2.1.27 79).
