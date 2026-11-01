# Fair play

The game's rules for this world, and Rory's three rules for how the base is built, all in one
place. The other docs are advice (`STRATEGY.md`) and how-to (`TOOLKIT.md`, `LANGUAGE.md`,
`EXAMPLES.md`).

## Changing the world

- **Everything you build goes in as ghosts, and robots build them.** That covers `fk build` and any
  paste of your own. Nothing is created, refilled or moved by script.
- **A process over time that the game can automate belongs in the game:** circuits, a mall,
  inserters, logistic requests. It doesn't belong in a script that runs it for you.
- **A script may do one specific multi-stage build action** (`fk fresh` is one). It must never
  manage the base or keep everything stocked through one-off crafters.
- **Pressing a button a player could press is fine**, such as launching a rocket from its silo
  with `fk lua`.
- **Moving items by script is never a player's button.** No `fk lua` that inserts, removes or
  transfers items: not to unjam a belt, not to fill a machine, not to empty a chest. Robots move
  them: ask with `fk request ENTITY ITEM N` (an item request, the game's own: robots bring the
  items from the network), or build the inserters, requests and belts that do it.
- **Big combinator signal tables may be filled by script after the paste.** That is an exception,
  for speed.
- **Wires may be added and cut by script.** The build does it itself, so the red, green and
  copper wires between the design's entities match the design (Rory, 2026-10-31).

## Seeing the world

- **Free to read any time:**
  - the alerts panel (new alerts come to you on their own, with reminders while one stays open);
  - production statistics (`fk stats`), with the production panel's graphs;
  - whole-base statistics: what the base holds (`fk stock`) and its working capital
    (`fk capital`);
  - the charted map (`fk chart`);
  - research (`fk research`).
- **Everything else you see where you look** (`fk look`, `fk sense`), like a player at the screen.
  Investigating with your own code and `fk lua` reads is fine. A script that watches the whole base
  and tells you what broke is not: to keep an eye on a far part of the base, build it in the game
  with circuits and a programmable speaker.

## How the base is built (Rory, 2026-11-01)

Three rules for the design, from the first paste. Every 2.x run broke at least one of them, and
each cost a day. `STRATEGY.md` says why.

- **Modules all the way down.** `world.fk` holds the plant, the kit, sealed module instances and
  the trunks between their ports, and nothing else: no loose machine, chest or Stack at the top.
  A region is a sealed module of sealed modules. Each module builds clean in the lab
  (`fk lab NAME`) before it goes into the world.
- **Not past the ramp.** Paste the step the speedrun ramp says comes next (`STRATEGY.md`,
  "Growing"), sized to it, and the step after only once this one runs. Designing, labbing and
  planner runs (`fk sim`) of later steps are free; pasting them early is not allowed.
- **Stacks of cells, not rows.** Lines are `Stack`s of cells. The rows `SmelterRow`,
  `SmelterArray`, `AsmRow`, `LabRow` and `CircuitStack` are not used; `MinerRow` is (there is no
  drill cell). A template of any kind new to the run goes into the world only after it built
  and measured clean in the lab (`fk lab NAME --measure 60`).

## The lab

On a lab surface (`/lab`), none of this applies: materials are free, building is direct, and
watching and measuring are global. The rules above are for the real game. `fk lab` builds and
measures a design there (`docs\TOOLKIT.md`, "The lab").
