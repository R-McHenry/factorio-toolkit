# Toolkit 2.1.5: Machine, Entity, kind, the prelude, and tiers

Two parts, built and checked one after the other.

## Machine, Entity, kind and the prelude

Draft for phase 5 of `assessment-20261031\PLAN-2.1.md` ("A. Machine", "B. kind", "I. The
prelude"); the integrator gives the number.

### What a player can write now

- **`Machine<entity, recipe>`** is one machine of any crafting building in the catalog: assemblers,
  furnaces, the chemical plant, the refinery and the centrifuge.
  `m = Machine<entity=centrifuge, recipe=uranium-processing>` was not writable before.
  - `machine=` means `entity=`.
  - A furnace may take `ore=` in place of `recipe=`.
  - A burner takes `fuel=`, coal if not given. An electric machine ignores it.
  - Size, power, fluid boxes and rates come from the catalog, `facts.json` and `fluidboxes.json`.
- **`Entity<name=...>`** is any other building that moves no items: a lamp, a speaker, a display
  panel, a beacon. It is placed, powered and wireable. Its raw `cb.` and `bp.` settings come in a
  later release.
- **`kind NAME = KIND<params>`** names a kind, a module or another kind with some parameters set.
  - The instance's own parameters win, and `machine=` on an instance overrides the kind's
    `entity=`.
  - The instance keeps its own name: a ref is still `a`, not `a.m0`.
  - Kinds can name kinds. `kind Furnace = Furnace<fuel=wood>` builds on the prelude's `Furnace`.
  - `import Gears from "lib.fk"` imports a kind. A module from another file brings that file's
    kinds with it.
- **The prelude.** `fkcore/prelude.fk` declares `Assembler`, `Furnace`, `ChemPlant` and `Refinery`
  as kinds of `Machine`, with the defaults that were in Python. Every file gets it with no import.
  - A run's `game/prelude.fk` wins over the toolkit's. It is found in the file's folder or above
    it, as `prelude.fk` or `game/prelude.fk`.
  - A file's own kind or module of the same name wins over the prelude's.
  - The kickoff template has a copy, and `upgrade_run.py` copies it into a run that has none.

### New refusals

- `no-fluidbox`: a recipe with a fluid the building has no fluid box for.
  `Assembler<recipe=lubricant>` used to pass and build an assembling-machine-1 that never ran
  (20261030-2352, ~2360k). An assembling-machine-2 takes one fluid in and one out.
- `Machine`: an unknown entity, a building that doesn't craft, no `recipe=`, `ore=` on a
  non-furnace, and `entity=` with `machine=`.
- `Entity`: an unknown entity, and a crafter (write `Machine`).
- `kind`: a cycle, a target that is no kind, module or core kind, a kind of `Literal` or `Bus`, a
  kind inside a module, and a kind and a module of one name.

### Inside

- `templates.py`: `Machine` and `Entity` are core kinds. The `Assembler`, `Furnace`, `ChemPlant`
  and `Refinery` templates are gone. `ChemPlant<n=>` went with them: it placed one plant
  whatever n said, and no design used it.
- `expand._SINGLE` and `elaborate._SINGLE_KINDS` are one list, `templates.SINGLE`. An instance is
  single when its kind resolves to one of them.
- An instance of a kind keeps its written `kind` and `params`, so `.fkp` lines and netlists don't
  change. `Inst.core` and `Inst.kparams` hold the core kind and the merged parameters, and the
  router, fragments and circuits read those.
- `modules=auto` on a `ChemPlant` or `Refinery` now keeps a module pick: their slots were looked
  up on an assembling-machine-1 before.
- A file imported as a module (its body) now brings its own modules. The kickoff template's
  `nauvis.fk` with a `Mall` module in `world.fk` failed with `unknown template Mall`.
- `tools/golden.py` leaves `prelude.fk` out of the corpus: it is a library, not a design.
- The default inserter stays in Python. It is a row's (`fragments`) and the router's choice of
  hand, not a fixed prototype a kind could carry.

### Checks

- Golden: 54 of 54 identical against 2.0.78.
- `tests/test_machine_kind.py`: the centrifuge, the synonym, fuel and ore, every refusal, the
  prelude kinds, kinds of kinds, of a row, of a core kind and of a module, the run's prelude, a
  file's own kind and module, imported kinds, and a body imported with its modules.
- Lab, on a laptop server (`LaptopServer("machine")`, fk-play): `cen = Machine<entity=centrifuge,
  recipe=uranium-processing>` fed from a requester and `chem = ChemPlant<recipe=plastic-bar>` on an
  infinity pipe of gas and a coal requester, each into a provider chest. 53 entities, all 5 nets
  routed, diff ok 53. Over the second 30 game seconds the plant made 33 crafts and the centrifuge
  2, and both stayed `working`. Full speed is 30 and 2.5; the 3 extra are likely the lab force's
  researched plastic productivity.

### Found, not changed

- The catalog's `uranium-processing` gives one uranium-235 and one uranium-238 a craft, with no
  probability (the game: 0.7% and 99.3%). So `fk rates` overstates a centrifuge's U-235 by about
  140 times. That is a game-facts fix for its own commit.

## tiers

Draft for phase 6 of `assessment-20261031\PLAN-2.1.md` ("C. tiers"); the integrator gives the
number. It comes after the `Machine`, `kind` and prelude release.

### What changed

- **`tiers KIND: E1, E2, ...`** says what `machine=auto` may pick for a kind, and for every kind
  built on it. The first entity is the default pick.
- **The prelude has the six lines** that were the `TIERS` dict in `elaborate.py`: `Assembler`,
  `Furnace`, and the rows `AsmRow`, `CircuitStack`, `SmelterRow` and `SmelterArray`. The dict is
  gone. (`fkcore/tiers.py` is the belt tiers, and it is unchanged.)
- **A file's own tiers line wins** over the prelude's of the same name. Tiers lines come with the
  file they are in, as kinds do.
- **Elaboration checks every tiers line.** Each entity must exist and have the same size, the same
  energy (electric or burner) and the same fluid boxes at the same places as the first. A cell's
  belts and pipes are laid for one machine, so a tier must fit the same cell.
  - An assembling-machine-1 has no fluid boxes, and the -2 and -3 have boxes the game opens only
    for a fluid recipe. Those go together: on any other recipe none of them has a box.
- **On a fluid recipe, `machine=auto` picks only machines with the boxes.**
  `Assembler<recipe=lubricant, machine=auto>` picks from assembling-machine-2 and -3. It used to
  pick an assembling-machine-1 that never ran.
- **`entity=auto`** works as `machine=auto` does on a `Machine` kind.
- `Machine<entity=auto>` with no kind has no tier line, and is refused as before with the kinds
  that have one. Write a kind and a tiers line for it:
  `kind Spin = Machine<entity=centrifuge>` and `tiers Spin: centrifuge`.

### New refusals

- A tiers line with an unknown entity, or entities of another size, energy or set of fluid boxes.
- A tiers line inside a module, an entity listed twice, and two lines for one kind in a file.

### Checks

- Golden: 54 of 54 identical against 2.0.78. No corpus file has a `machine=auto`, so the choices
  were also compared directly, 2.1.2 against this tree, on 14 snippets: every `machine=auto` and
  `modules=auto` on `Assembler`, `Furnace`, the four rows and a cell used twice. Menus, picks,
  machines and parameters are identical, except `Assembler<recipe=lubricant, machine=auto>` (above).
- `tests/test_machine_kind.py`, `TiersTest`: the prelude's lines, a kind built on one, a file's own
  line, `entity=auto`, a tier of one's own, the fluid recipe, no tier, every refusal, and tiers
  imported with their file.
