# Toolkit 2.1.10: fluid ports, and recipe probabilities

PLAN-2.1, part F: a port may carry a fluid. A sealed cell can take its acid, water or gas from
outside, and a Stack can run one pipe through all its cells.

## Fluid ports

`port acid_in : in sulfuric-acid @w0` is one pipe connection across the frame's edge. It has no
lanes.

- The module's pipe reaches the tile inside the edge, and the parent's pipe the tile outside.
  The port is a `pipe` in the elaborated machine list, where a belt's port is a `transport-belt`.
- The fluid router (`fluid_route`) treats a fluid port as a carrier and an attach point. It routes
  each net in its own sealed frame, and it reserves the port's tiles for that net.
- The connect graph (`connect._fluid_port_joints`) joins the two sides across the edge through
  the port, so the check sees one net and no SPILL. Each port has two boxes, inside and outside;
  `connect.port_box` says which one gives and which one takes.
- `stack acid_in -> acid_out` works for a fluid pair. The pipe runs through each cell, and one
  cell's pipe joins the next one's at their shared edge. The stack's own nets lay nothing
  ("nothing to lay (its ports meet on one edge)").

Refused, each with a plain message:

- `inout` on a fluid: a fluid port is `in` or `out`, the way its net runs.
- A pair (`water | water`) or a lane pin (`@w4L`): pipes have no lanes.
- Two fluids, or a fluid and an item, on one port: a port each.
- A Stack whose NEAR and FAR ports carry different fluids.

## Uranium takes acid

- The electric drill has a fluid box now (`fluidboxes.json`, read from the game). It is live only
  on an ore that needs a fluid, which is uranium on Nauvis.
- `facts.required_fluid` gives the ore's fluid and how much an ore takes: one acid an ore (the
  game's `fluid_amount` is per 10 ores).
- A `MinerRow` on uranium needs that acid: 0.25/s a drill, at the drill's 0.25 ore/s.
- A burner drill on uranium is refused: it has no fluid box.

## Product probabilities (data fix, its own commit)

`catalog.json` had no product probabilities. `fk rates` gave uranium processing a whole U-235 for
each craft: 5.00/min from one centrifuge, where the game makes 0.035/min.

- `tools/read_facts.py --products` reads every recipe's products from the game (on a laptop
  server) and writes in the 121 probabilities below 1. They are uranium processing, the
  recyclers' 0.25, asteroid crushing, and Gleba's seeds and bacteria. It writes the recyclers'
  `extra_count_fraction` too.
- `catalog.expected` is a product's expected amount. `recipe_rates`, `craft_rate` and
  `cost.item_cost` use it.
- U-238 is now 0.993 a craft and U-235 0.007, so one centrifuge makes 4.97/min and 0.035/min.
- With the odds read in, `item_cost` found iron ore through `iron-ore-recycling` (ore back at
  0.25), so an ore cost 4 and a gear 8. A mined ore now costs 1, and a recycling recipe is never
  the way to make an item. A plate is 1 again, a gear 2 and an assembling-machine-2 54.

## Checked

- `tests/test_fluid_ports.py`, 15 tests:
  - each refusal;
  - the port boxes' directions;
  - the drill's fluid box, live on uranium only;
  - the acid a uranium MinerRow needs, and the burner drill's refusal;
  - three routed cases. A plastic cell takes its gas from outside: 4 of 4 nets connected. An acid
    cell takes water in and sends acid out to a battery plant: 9 of 9. A Stack of three acid
    drill cells: 12 of 12, 0 SPILL, and the stack's acid nets lay nothing.
- `tests/test_probabilities.py`, 5 tests; `test_machine_kind` expects the centrifuge's odds.
- Full suite: 1315 tests OK.
- Lab, on a laptop server (`python tools/laptop_server.py fluidports`). A Stack of three 7x7 acid
  drill cells sat on a copy of a uranium patch from the server's own Nauvis. Its acid came from
  an infinity pipe outside the Stack.
  - Every drill held acid (200 each) and was working.
  - Ore over 61 s: 59.5/min mined and 55.5/min into the chest. The model says 45/min at full
    speed, or 58.5/min with the lab force's mining productivity (+30%).
  - Acid: 90 used for 60 mining cycles. A drill draws 10 at a time, so one acid an ore predicts
    60 to 90.
- Golden: 54 of 54 identical against 2.0.78. No golden file uses a fluid port.

## Not done

- The lab flow doesn't set an infinity pipe's fluid. The check sets it by hand, as
  `tools/lab_fluids.py start` does.
- `fk measure` reads crafting machines only, so the check reads drills from the force's
  statistics.
- A narrow drill cell can fail to route its ore: 4x6, 5x6 and 6x7 cells give `UNREACHED`, while
  7x7 routes. The belt router merges a port's belt and a drill's ore only where a splitter fits.
  This was there before.
