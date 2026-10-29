# Toolkit 2.0.62: the opus run's friction, and a player who codes

From the opus run's FRICTION.md and Rory, 2026-10-29: fix each problem, and give the player a
better workaround that also fits the next one. "Agents are very good at this so we want them in a
good position to do it, rather than any anti programming rules, compiled or hidden code, or an
unapproachable codebase."

## A net that gains a consumer is routed to it

**The bug.** A net driven by a port (the run's `mall1/fe`, from `fe_in`) gained three consumers.
The build kept its route as laid ("kept mall1/fe: its carriers are already laid (pinned)"), said
0 failed, and the new gear assembler starved. `report_checks` said `partly-connected`.

**The cause.** The keep check (`route._standing`) judges a committed route against the net's
ends, but it counted only machines as ends. A port driver had none, so no pair could be missing
and every route stood.

**The fix.** Ports count as ends (`route._placed`). The route is patched, or laid again when no
branch fits.

**The workaround, first class.**
- `fk build --reroute NET[,NET]` lays nets anew for one build. An instance's name covers every net
  inside it (`--reroute mall1`), and `all` covers everything. `route.txt` says `routed again: asked`.
- `fk build --with 'STEP OPTS'` adds options to any step for one build, without editing the script.
  The player's notes had "`cover robots --fresh` (one build, then restore the line)". Now it's
  `fk build --with 'cover robots --fresh'`.
- `--reroute` is `--with 'route --again NET'`. Both reach the host half of the build too.

## Pipes route inside a sealed module

**The bug.** The run's `Oil` module (pumpjacks, a refinery and a chem plant): every fluid net
failed with "every connection tile of its box is taken", whatever the rotation. The player moved oil
to world level.

**The cause.** The fluid router blocked every instance's whole frame for every net, the module's
own frame included.

**The fix.** As the belt router already does (`net_frames`), a fluid net inside a sealed module
routes in that module's frame (also its search box) and keeps off every other frame. The run's Oil
module now lays 12 pipes for crude and 4 for petroleum, with all 4 nets connected.

**Not in this release.** Fluid ports are still refused ("pipes have no lanes"), so a fluid can't
cross a module's frame. Water from outside into a module needs its pump inside, or a Literal.

## `fk capture`: build it anywhere, then make it a Literal

Rory: "it should be easy for a player to make a design in the lab, or simply separate build, and
turn it into a bp or literal that can then go anywhere".

| command | what it writes |
|---|---|
| `fk capture lab NAME` | the lab slot, as it stands in the game (the lab's energy interface left out) |
| `fk capture world X0,Y0,X1,Y1` | an area of the live game (`fk sim game capture world ...`: of the planner) |
| `fk capture design [FACTORY/]INST` | an instance of the laid-out design: its machines and its own nets' routes |

The game sources write `{"bp": "0e..."}`, and the design source an entity list with recipes and
configs. Both are what `Literal<file=...>` reads and what `fk sim place` takes, so a build goes into
a module, onto another plot, or into the planner. Default file: `game\captured\<what>.json`.

**Checked live (read-only).** Sci1 on the live map came back as 92 entities. The Literal read all
92, with 7 recipes and 26 chest requests. A design capture of the Oil module went into another
module as a Literal with every pipe.

## `fk decon`: the deconstruction planner, no Lua

`fk decon X0,Y0,X1,Y1 [--name ENTITY[,...]] [--cancel]` orders out what stands there (only those
entities, with `--name`), or takes the orders back. It reports what was ordered. It warns when a
roboport it orders out holds robots: they go to storage as items and do nothing. That is how the
run's 21 idle logistic robots most likely got into a chest, since the kickoff puts all 100 in the
roboport. Checked on the lab surface: the filter, the order and the cancel.

## A player who codes

- **`TOOLKIT.md`.** "Reading the game yourself" is now "Programming the game yourself". It covers
  three levels (fk commands, Lua, the player's own scripts), where the Lua every command sends
  lives (`.toolkit\fkcore\link.py` and others), and that a Lua loop of ghosts or a deconstruction
  order is a paste of your own under `FAIR-PLAY.md`. It also gives the capture route from an
  ad-hoc build into the design. The old "Use it to look and to understand. Changes go through
  `fk build`" is gone.
- **The brief (`opus-v1.md`).** Code is often the quickest way. Write the Lua for what no command
  does, chain commands and scripts, and try risky Lua on the planner first. A design doesn't have
  to start as `.fk`. "Ways to get unstuck" gains reroute, `--with` and decon.
- **`FAIR-PLAY.md`** is unchanged. It already allowed all of this.

## Tests

`tests/test_friction_2062.py`:
- the port net gaining a consumer;
- reroute by net, by instance, and an unknown name;
- `--with` parsing;
- pipes in a sealed module;
- capturing a design and dropping it into another module;
- the capture Lua.

Suite: 1064 OK.
