# Toolkit 2.0.18: `fk stock` — what the base holds, and which robots are doing nothing

Rory, 2026-10-25: "make sure the agent is looking at the items it has, thats how it should tell
things like that it picked up robots and be able to decide on its own a policy for roboports".

In the 0928 run the player needed three Lua probes to find that 28 of the kit's 50 logistic robots
were sitting in a storage chest: the toolkit had `fk stats` (what the base *makes*) but nothing that
lists what it *holds*, and the player's own `helpers stock` only answered about the items it named.
So it never saw the robots, and when a probe finally showed them it had no way to load them.

- **`fk stock`** (a free read, like `stats` and `chart`): every item the base holds, largest first,
  with chests and roboports apart. Robots get their own line and a sentence:

  ```
  logistic-robot                      50  (22 in roboports, 28 in chests) - the ones in chests
                                           are idle: an inserter into a roboport starts them
  ```

  and a base with no robots in any roboport says so, since that is a base where nothing flies.
- **The core-v1 brief** gains "what do you have → `fk stock`" in its problem list, and a short
  "Robots and roboports" section: the count tells you which robots are in service and which are
  items, `docs\examples\robot-feed.fk` puts them back, a roboport is where the fleet lives (taking
  one up strands what is inside it), and `cover robots` decides where roboports go rather than
  scattering them.
- **`STRATEGY.md`, `TOOLKIT.md`** list the command where a player looks for it.

Tests: `tests/test_stock.py` (the robot line says where they are and that the chest ones are idle,
a fleetless base is called out, a full fleet is quiet, largest first). The Lua was run against the
live map: it reads 50 logistic robots, 22 in roboports and 28 in the chest.
