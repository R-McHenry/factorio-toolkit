# Toolkit 2.0.66: the tech tree scanner, and goals that weigh science

Rory, 2026-10-29: "a tech tree scanner that can generically pick up initial cost behind stuff like
fluoroketone. So basically we would calculate the total cost in science to unlock it, and maybe to
keep things simple we then basically just alter the manhattan metric space to penalize any
connections between cells with fewer corresponding science then is required."

## `fkcore/techcost.py`: what an item costs to unlock

`LUA_DUMP` reads the game's own prototypes, so it follows whatever mods the game runs. It changes
nothing in the game. What it reads:
- the technologies: prerequisites, packs, the recipes and space locations they unlock, triggers;
- the recipes: ingredients and products, enabled by default or not; hidden, recycling and
  parameter recipes are left out;
- where raw things come from:
  - resources;
  - trees, plants and rocks, through each planet's autoplace controls;
  - fluids pumped from tiles;
  - asteroid chunks, once an asteroid collector can be made;
  - what an item spoils or burns into.

`Tree.costs(researched)` gives, for every item, the cheapest set of technologies not yet
researched that lets the base make it, by pack count. It's found by relaxing to a fixed point.
- **A recipe** costs its unlocking technology, with its prerequisite closure, plus its
  ingredients' costs. So a barrel recipe that's already enabled still costs what its fluid costs.
- **A trigger technology** costs the item its trigger makes.
- **A breeding or catalyst ingredient** (an ingredient the recipe also makes: pentapod eggs,
  Kovarex) isn't required first.
- **Packs.** A shared prerequisite counts once. Infinite technologies are left out.
- **Coverage.** On the planner, every one of the 300 items the game can make or yield is
  reachable.

From the opus run's base (Space Age):

| item | technologies | packs |
|---|---|---|
| rocket part | 8 | 7,800 (red, green, blue) |
| tungsten plate | 17 | 13,800 (with space) |
| agricultural science | 21 | 13,800 |
| fluoroketone barrel | 55 | 76,630 (ten kinds of pack) |
| promethium science | 62 | 128,030 |

## The metric

`explore.step_cost`:
- **An item the cell has already made:** 1.
- **An item's first step:** 1 plus `explore.deficit`. For each pack p it needs,
  `floor(log(made_p + need_p))` less the cell's level of p, when that's short.

`Archive.pick_goal` walks from the go cell within `--dist`, picking each step uniformly among
those the budget still affords. The pool is every item the scanner finds reachable, so it's
impartial over the whole game, not just over what can be crafted now. Science picked earlier in
the walk lowers what later steps cost.

On the opus base at `--dist 4`:
- a fluoroketone barrel step costs 100, and a rocket part 6;
- research that's cheap next to the science already made (a gate, productivity modules,
  construction robots) costs 1, and that's where short goals go;
- far items come into reach only as `--dist` grows.

The planner dumps the tree once per archive (`sim\explore\techtree.json`) and reads the go state's
researched technologies each round.

## Tests

`tests/test_techcost.py`, on a small hand-made tree:
- costs from nothing, and from something researched;
- a barrel costing its contents, spoil and burn results, a trigger, and breeding;
- the deficit and the step cost;
- a 4-step walk never picking the far item, while a 40-step one does.
