# Toolkit 2.0.65: explore rounds that end on their own, and a manifest instead of cells

Rory, 2026-10-29:
- **The stop.** "it shouldnt make the agent wait until it gets to the goal cell, it should have an
  early stop mode that tells the agent its worked on the cell goal long enough and its time for a
  new round".
- **No stall stop.** "get rid of stall though".
- **What the player sees.** "the player shouldnt be exposed to cells beyond the goal its given
  which is just a material manifest".

## A round ends on its own

`explore.round_end` says why a round is over, on whichever comes first:
- **The manifest is met.**
- **The budget is spent.** `--budget` ticks since the round's start, 36000 by default.
- **The minutes are up.** `--minutes`, the agent's own time, off by default.

A `run` in a round:
- stops at the budget (`explore.ticks_left`), and says so ("ran 1800 ticks ... (of the 5000
  asked)");
- ends the round there with `ROUND N OVER: <why>. Manifest: ...`;
- with `--auto on` (the default), loads the next round in the same output. With `--auto off` it
  says `fk sim explore next`.

## A manifest, not cells

The player's output names no cell.
- **The manifest.** Each goal item with the total for the base to have made and what it has made
  so far, in real counts: `iron-plate 700 of 1,024; rail 0 of 1`. A goal level L is
  `ceil(base^L)` (`explore.manifest`).
- **The checks.** The cell check after each chunk is silent. New cells and faster ways still go
  into the archive.
- **`ROUND N`.** Says the game loaded, its tick, the manifest and when the round ends.
- **`status`.** Shows the round's ticks and minutes used, and its manifest.
- **The archive.** `archive`, `best` and `reset` stay, to look at it afterwards.

## Checked on a laptop planner

On a copy of the opus run's live save:
- Round 1 at budget 1800 stopped a `run 5000` at 1800 ticks and said the budget was spent.
- Round 2 loaded by itself.
- Both showed only their manifests.

The planner and the live server both run Space Age (base, elevated-rails, quality, space-age), so a
manifest can name a Space Age item whose recipe is enabled (a fluoroketone barrel, say), most of
the tech tree away. Rory: "if the goal seems unreachable, then just consider the path that
eventually gets there and do whatever the first step to get there is". Every `ROUND` text says so,
and so do `TOOLKIT.md` and the brief. The archive keeps every cell the step reaches.

## Docs

- **`TOOLKIT.md`.** "Explore mode" is the player's view now: rounds, manifests, how a round ends,
  and the archive mentioned only as where the plans collect.
- **The brief.** One paragraph to match.

## Tests

`tests/test_explore.py` adds:
- the manifest in counts;
- a round ending on its manifest, its budget or its minutes, and `ticks_left`.
