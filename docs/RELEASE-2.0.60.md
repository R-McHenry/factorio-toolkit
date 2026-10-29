# Toolkit 2.0.60: machine=auto and modules=auto, chosen by cost

Rory, 2026-10-29: the size step "should have the rate model, and just optimise the params to get
the desired rate". After 2.0.59's Stack counts, the next parameters are machine tier and modules,
chosen in the same search with a cost.

## Two new choices

- `machine=auto` picks the tier from machines of the same size, so a cell's layout holds:
  assembling-machine-1/2/3 for an `Assembler`, `AsmRow` or `CircuitStack`, stone or steel for a
  burner `Furnace`, `SmelterRow` or `SmelterArray`. Another kind refuses it.
- `modules=auto` picks no modules, speed modules, or productivity modules where the recipe takes
  them (Factorio 2.0's intermediate products, `elaborate.PRODUCTIVE`). A machine with no slots gets
  none.
- One source line's choice holds for every copy of it: a choice inside a cell is one for the whole
  Stack. Its key is `<module>.<instance>.<param>`.

## The cost

`fkcore/cost.py`: an item costs its recipe's ingredients per unit made, down to the raw resources
(ores, coal, stone, wood: 1 each; fluids 0). So an iron plate is 1, a gear 2, a green circuit 2.5,
an assembling-machine-2 54 and a productivity module 52.5. A design costs its machines and their
modules. The route's belts and inserters and the poles aren't known yet when the size step runs.

`size --payback 2h` in the build script adds what the design draws over that time: its sources'
output at raw cost, scaled to the rate its targets and asserts ask. A design that runs past them
into a chest that takes all is counted at the rate asked. That's where productivity modules pay
for themselves.

## The search

Around the counts (`size._size_counts`, 2.0.59's search), every combination of picks, up to
`COMBOS` (64), is sized and measured. Past that, the search takes one choice at a time with the
others held, until none changes. Of the combinations that meet every want, the cheapest wins.
Picks that build the same design (modules on a machine with no slots) count once. `out\size.txt`
gives the pick, its cost, and the next three options.

Three gears a second (`AsmRow<n=auto, machine=auto, modules=auto>`, `assert g.rate >= 3/s`):

| cost | chosen | next |
|---|---|---|
| to build | 3 x assembling-machine-1, no modules (190) | 2 x assembling-machine-2 (219) |
| plus 2 h of draw | 2 x assembling-machine-3, 4 productivity modules each: 5.17 plates/s for 3 gears/s | assembling-machine-2 with productivity |
| plus 10 h | the same, by more | |

Through a build, the chosen machines are laid with their module requests in the paste.

## Tests

`tests/test_choices.py` (7): the costs, elaborated at the first pick or the step's, cheapest to
build, productivity over two hours, one option per design, a choice in a cell for the whole Stack,
and a kind with no tier refused.
