# Toolkit 2.0.64: explore mode (Go-Explore on the planner), and save states that load on their tick

## Explore mode: `fk sim explore`

Rory, 2026-10-29:
- **The cells.** "cells as low resolution snapshot of a game state such as floor(log(item))
  foreach item in total items produced. Then each time you reach a new cell, you can save the
  trajectory of actions that got there ... or if an existing cell is reached more quickly, then
  the previous trajectory is replaced with the new way."
- **The cell function stays as written.** "There is no loophole around getting to 10,000 iron
  quickly without research."
- **The goal.** "a future cell that is at least some N distance in manhattan", go and target
  "impartial", and a prior, if any, "based on the cells visited by our most successful runs".
- **The mode.** "just a mode of the sim where ... the sim picks [the state] by itself and gives
  the agent a goal cell".

### `fkcore/explore.py`

- **The cell.** `{item: floor(log_base(made))}` over the force's item production statistics
  (cumulative), base 2 by default (`--base`, smaller is finer). An item never made has no entry
  and counts as level -1 in a distance.
- **The archive** (`sim\explore\archive.json`). Per cell: its levels, the earliest tick it was
  reached at, its save state (`x<k>`), its trajectory (each action at its tick), its parent (the go
  cell of the episode that found it), its visits, and how many times it was beaten.
  - A new cell is saved.
  - A faster way replaces the trajectory and the save.
  - The root `x0` is never written over.
- **An episode.**
  - **The go cell.** Uniform over the archive. With `--prior K`, uniform over the cells on the
    way to the K furthest (most levels in all, then the earliest tick).
  - **The goal.** The go cell plus `--dist` steps of +1, each on an item picked uniformly from the
    items the archive has seen made and the items the force can make there. That's every enabled,
    non-hidden recipe's item products, read from the game.
  - **Reaching it.** Every goal item at its level or above.

### In the planner (`fkcore/sim.py`)

- **`explore on`.** Starts the archive from save state `start`, saved again paused as the root
  `x0`, and begins an episode.
- **`next`.** Loads a new go cell, at speed 100, and gives a new goal.
- **`status`, `archive [N]`, `best [CELL] [--to plan.sim]`, `off`, `reset`.**
- **While it's on:**
  - `run` / `until` run in chunks (600 ticks by default) and offer the cell after each. They report
    `new cell` / `faster cell`, `GOAL reached`, and the goal's shortfall, and say when the episode's
    budget (36000 ticks by default) is past.
  - `paste` and `decon` are recorded. A pasted file is kept by content under
    `sim\explore\files`, so a trajectory still plays when the player's file changes.
  - `fk sim game research | lua | decon` are recorded (the player's `fk` calls
    `fkcore sim . explore-game`).
  - `place` and `remove` are refused, since free building would make the cells a cheat. `load` is
    refused too: the planner picks the state.
- **Playback.** It gains a `game CMD ...` verb, so a trajectory with research and Lua plays back.
  `best` writes Lua chunks as files and plays `game lua --file`.

## Save states load on their tick

A save written while the game ran isn't paused: the fetched `start`, `fetch --live`, the live
game's own. Every boot of one ran on until the first RCON call paused it, at its saved speed, which
is 100 for a save made after `speed 100`. That's tens to hundreds of ticks, a different number each
time. The opus player saw the same drift.

`Sim.start` now reads whether the game was paused when it got there. If it wasn't, it saves the
state again under the same name, paused, and says so. On the opus run's `now.zip`, the first boot
re-saved it at tick 877699, and the next two booted at 877699.

## Checked on a laptop planner

On a copy of the opus run's live save (tick 877698), at base 1.05 so cells come quickly:
- Episode 1 from `x0`: a research action, then 1800 ticks, gave new cell `x1`.
- Episode 2 from `x1`: 1200 ticks gave `x2`. The archive is x0, x1 (parent x0), x2 (parent x1).
- `best` played back from `x0` reached the archived cell exactly, at the same tick (880098).

At base 2 a base 877k ticks in made no new cell in a minute: doubling a cumulative count takes
longer than that late in a game, as the cell function intends. Early in a game, cells come fast.

## Tests

`tests/test_explore.py`, 11 tests:
- the cell, the key, the distance and `reached`;
- new, faster and known cells, and the root kept;
- the goal's steps;
- the go cell impartial, and the prior following the best's ancestry;
- the plan playing back (Lua as a file);
- free building refused in explore mode.
