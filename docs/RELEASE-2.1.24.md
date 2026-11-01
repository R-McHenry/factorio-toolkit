# 2.1.24: m2m fills both lanes, runs come first out of their splits, the game's rules check it

Rory, 2026-11-01: "continue with that next step and maybe some practical tests". The next step
was filling the empty lanes of the crossing runs. The practical test is the real game: the
hourglass bench built on a laptop server, with every consumer's rate measured.

## What changed (`route --m2m`, `fkcore/m2m.py`)

- **A side-load fills a lane.** A splitter keeps the lanes, and a column of producers on one side
  of its belt fills one lane, so every run carried one. A run may now end by side-loading a plain
  belt on a lane that nothing feeds yet, so one belt carries both lanes. No splitter is put on a
  side-loaded belt, and `_improve` never rips the belt a side-load leans on.
- **A run comes first out of its split.** The game's splitter splits evenly until an output backs
  up; the max-flow sends a run what it needs. The splitter a run leaves by now gets the output
  priority on the run's side (`config`, carried through `route._carriers` to the blueprint).
- **The game's rules check the result.** Once the max-flow is met, the net is solved as the game
  runs it (`fkcore.throughput`, through `_Ctx.played`). While its consumers get less than the
  demand, runs are added from the drivers that are held back to the consumers that are short, and
  a run is kept only when what they get rises. The route line says `by the game's rules A -> B`.

## The bench (`tools/hourglass.py --big`, new column `rules`)

| case | max-flow | rules, no priority | rules 2.1.24 | cost 2.1.23 | cost 2.1.24 |
|---|---|---|---|---|---|
| 16to16 | 22.4 | 18.7 | 21.0 | 192 | 199 |
| 24to24 | 48 | 37.4 | 44.5 | 363 | 335 |
| 32to16 | 64 | 54.5 | 61.5 | 693 | 688 |
| 32to32 | 64 | 46.8 | 61.8 | 537 | 431 |

"No priority" is 2.1.24 with the runs' splitters splitting evenly (16to16's 18.7 is 2.1.23's own
layout). The small cases (8to8, 16to4, 4to16, uneven, wall) are unchanged and deliver in full under the
rules. The balancer delivers 100% everywhere it lays. Today's router delivers its one belt (15/s).

## The lab (`tools/hourglass_lab.py`, new)

Every layout is pasted on a laptop server's lab surface (never the live game). Each producer gets
exactly its rate's worth into its chest, and each consumer gives up at most its rate's worth from
a chest that starts a stack full. After 300 s of warm-up, what reached each consumer is measured
over 240 s.

| case | router | demand | real game | rules | lowest consumer |
|---|---|---|---|---|---|
| 16to16 | m2m | 22.4 | 20.8 (93%) | 21.0 | 0.32 of its rate |
| 24to24 | m2m | 48 | 45.8 (95%) | 44.5 | 0.10 |
| 32to16 | m2m | 64 | 61.4 (96%) | 61.5 | 0.78 |
| 32to32 | m2m | 64 | 59.4 (93%) | 61.8 | 0 |
| 4to16 | m2m | 8.8 | 7.4 (84%) | 8.8 | 0 |
| every case | balancer | | 100% | 100% | 1.00 |
| every case | today | | = its max-flow | same | |

The game's rules (`fkcore.routed`) predict the real game to a few percent, and exactly on 16to16
(18.7, with the same three consumers short, before this release's changes). So the bench's
`rules` column stands in for the lab. 4to16 is the exception; see below.

## Open

- **m2m does not balance exactly yet.** Its max-flow is met everywhere, but the game delivers
  93-97% on the busy cases, with a few consumers starved. The balancer delivers 100% at a higher
  cost (and doesn't lay the big cases).
- **4to16** delivers 84% in the lab while the rules say 100%: consumers c13 to c15 starve. The
  same after a 900 s warm-up, so it isn't the start. Somewhere the game and `fkcore.throughput`
  differ (on that layout: a U-turn past the first consumers, an underground under it).
