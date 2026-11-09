# notes-44-levels: the hierarchy measured (PLAN-ORGANIC D5, 2026-11-09)

Branch `claude/44-levels`, cut from main `90e20a0`. Rory's ask, 11-09: the megabelt design
session's player wrote up why its designs kept coming out flat and blamed the router; "the
modular hierarchy is a feature we've been hammering at so hard and it hasn't ever fully landed".
Its list, and where each item went:

| the player's point | where it lands |
|---|---|
| 1. nothing measures a flat level; a 107-net level reports "all connected" like any other, and the build report never says which level took the time | **here**: `fk check` says `flat`; the route step's `level` lines and the `flat` check |
| 2. the docs bury it: no number for how many nets one level should route | **here**: the warning box in its four places names the number; a BUILDING "Hierarchy" bullet; LANGUAGE's sealed row; TOOLKIT's route lines and checks list; EXAMPLES chapter 11 |
| 3. "done" rewards it (every net connected on paper) | the design session's briefs: `lab-session\megabelt\BRIEF.md` and `starter\BRIEF.md` now say done includes no `flat` line |
| 4. contracts force cross-wiring (4 columns, 3 iron ports) | the design session's contracts, not the toolkit |
| 5a. paired lanes must run straight between ports | BUILDING rule since 41-docs; the check `port-not-in-line` is `claude/43-hierarchy`'s D3 |
| 5b. a sealed module powers only its own frame; a pump or beacon with no room for a pole crashes | **here**, the crash: `cover._why_not` with no layout size (3.1.3's `TypeError`, fk-run2 FRICTION.md) now says `outside the 13x3 frame; a sealed cell powers only its own frame: free a tile inside it for a pole, or move the entity into the parent module`. The code stays `NO_POWER`; D3's own `no-pole-spot` line is 43-hierarchy's to name |
| 5c. adjacent fluid ports touch | **here**: `ports-touch`, two fluid ports of different fluids on adjacent tiles of one module side |
| 5d. a group whose ports face another frame goes unrouted | not reproduced: no log of it in the designers' notes; open for `claude/43-hierarchy` to measure with the designers' games |
| 5e. a stale store keeps old failures | the design database's memo (`--retry-failed changed`: a failed net is not searched again on the same ground, and the report says so with `route --again NET`); 42-reroute made a store miss name its cause. Nothing found to patch without the designers' log; open for 43-hierarchy |
| 6. "I didn't look" | the `level` lines are what to read first in a slow build (BUILDING says so) |

## What landed

- **`fk check`: `flat`** (`elaborate.LEVEL_NETS = 60`, `_level_checks`). A level is the top of a
  file or one sealed module, the innermost sealed module a net is written in, as `route._unit`
  reads it. A module instanced many times is named once with its widest instance's count. On the
  designers' `flower.fk` (6559 nets, 1261 sealed units):

  ```
  flat module Flower: 118 nets route at one level (the limit is 60): the router is handed all of them together in this frame, and its time grows with both. Seal a sub-unit (`module NAME size WxH { port ... }`) so each level routes a handful, build it alone, then compose (BUILDING.md "Hierarchy")
  flat module RiverCircuit: 107 nets ...
  flat module Core: 93 ... RiverMesa: 91 ... EngCol: 85 ... RimStrip: 78 ... BlueCol: 74 ... FrCol: 67 ... RedGroup: 65 ... RiverMeadow: 62
  ```

  Ten levels; the player's note saw eight. Nothing in `agent\docs\examples` is flagged: the
  widest levels there are belt-switch's `SteelMod` (55) and red-chain's `RedMod` (35).
- **The route step's `level` lines** (`route.Routed.levels`, timed round each unit's search in
  `_route_layout`; `flow._level_lines`): one per level that searched this build, slowest first,
  the twelve slowest shown and the rest counted; a twin or a stored unit searched nothing and has
  no line. Pass-through nets are left out of the count as the summary leaves them out.

  ```
  red-chain: 85 routed, 0 kept, 33 pass-through (0 pinned from the committed .fkp), 0 failed, 1 pass
    level     chain (RedMod): 9 nets searched, 0 failed, 2.7 s, frame 74x56
    level     the top level: 5 nets searched, 0 failed, 0.0 s, frame 87x71
    level     chain/pl/p1 (Plas2): 3 nets searched, 0 failed, 0.0 s, frame 11x8
  ```

  A level past `LEVEL_NETS` nets or `route.LEVEL_SECONDS = 60` s reads `; flat: over 60 nets or 60
  s` and is the check `flat` at the route step (so `report_checks` lists it and `stop_on flat`
  holds the paste).
- **`ports-touch`** (`elaborate._fluid_port_checks`): two fluid ports of different fluids on
  adjacent tiles of one side of a module. Two ports of one fluid may touch (3.1.4's stacked cells).
- **`cover._why_not` without a layout size** (the sealed unit's pass of `cover_power_units`):
  the frame's size from the pass's `frame`, and the sealed-cell sentence.
- **Docs:** the warning box in START, BUILDING, TOOLKIT and EXAMPLES chapter 11 gains "Each level
  routes a handful of nets: `fk check` says `flat` for a level past 60, and the build's `level`
  lines give every level's nets, seconds and frame (a minute at one level is too long)"; a
  BUILDING "Hierarchy" bullet; START's route.txt quote with its `level` line; TOOLKIT's route
  paragraph and checks list; LANGUAGE's sealed row; chapter 11's route.txt quote brought up to the
  3.1.5 summary (`85 routed, 0 kept, 33 pass-through`, it quoted the pre-reroute `118 routed`)
  with three `level` lines and a `flat` paragraph.
- **Tests:** `tests/test_levels.py` (11): the paper check at, past and under the limit, a module
  named once, sealed sub-units splitting the count; `ports-touch` three ways; the `level` lines
  on test_compiled's world of two twins, and the `flat` check with `LEVEL_SECONDS` patched to 0;
  `_why_not` with and without a size.

## Why 60

The player suggested 20 nets or 60 s. Measured: the docs' widest clean level, `SteelMod` (55
nets), builds in 2 s; `RedMod` (35) in 3 s; BUILDING's LabArea (72) routed in 12 s alone; the
flower's problem levels were 62 to 118 nets in frames up to 900x1024 and took 35 minutes. The
count alone is a weak signal (the frame and the nets' lengths matter as much), so 60 nets is the
paper line that separates every level the designers hit from every level in the docs, and the
seconds are the real judge at build time. Both are one constant each; change them in one place.

## Open

- 5d and 5e above: measure on the designers' games (`claude/43-hierarchy`).
- A `flat` check for the top level reads `the top level of NAME`; a world file's plot is not
  known on paper, so the paper line has no frame; the build's does.
- `fk status` could repeat the last build's `level` lines; it does not yet.
