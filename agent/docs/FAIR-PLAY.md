# Fair play

The game's rules for this world, all in one place. The other docs are advice (`STRATEGY.md`) and
how-to (`TOOLKIT.md`, `LANGUAGE.md`, `EXAMPLES.md`).

## Changing the world

- **Everything you build goes in as ghosts, and robots build them.** That covers `fk build` and any
  paste of your own. Nothing is created, refilled or moved by script.
- **A process over time that the game can automate belongs in the game:** circuits, a mall,
  inserters, logistic requests. It doesn't belong in a script that runs it for you.
- **A script may do one specific multi-stage build action** (`fk fresh` is one). It must never
  manage the base or keep everything stocked through one-off crafters.
- **Pressing a button a player could press is fine**, such as launching a rocket from its silo
  with `fk lua`.
- **Big combinator signal tables may be filled by script after the paste.** That is an exception,
  for speed.

## Seeing the world

- **Free to read any time:**
  - the alerts panel (new alerts come to you on their own, with reminders while one stays open);
  - production statistics (`fk stats`);
  - the charted map (`fk chart`);
  - research (`fk research`).
- **Everything else you see where you look** (`fk look`, `fk sense`), like a player at the screen.
  Investigating with your own code and `fk lua` reads is fine. A script that watches the whole base
  and tells you what broke is not: to keep an eye on a far part of the base, build it in the game
  with circuits and a programmable speaker.

## The lab

On a lab surface (`/lab`), none of this applies: materials are free, building is direct, and
watching and measuring are global. The rules above are for the real game.
