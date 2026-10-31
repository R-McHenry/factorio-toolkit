# Toolkit 2.1 (draft): `tiers`

Draft for phase 6 of `assessment-20261031\PLAN-2.1.md` ("C. tiers"); the integrator gives the
number. It comes after the `Machine`, `kind` and prelude release.

## What changed

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

## New refusals

- A tiers line with an unknown entity, or entities of another size, energy or set of fluid boxes.
- A tiers line inside a module, an entity listed twice, and two lines for one kind in a file.

## Checks

- Golden: 54 of 54 identical against 2.0.78. No corpus file has a `machine=auto`, so the choices
  were also compared directly, 2.1.2 against this tree, on 14 snippets: every `machine=auto` and
  `modules=auto` on `Assembler`, `Furnace`, the four rows and a cell used twice. Menus, picks,
  machines and parameters are identical, except `Assembler<recipe=lubricant, machine=auto>` (above).
- `tests/test_machine_kind.py`, `TiersTest`: the prelude's lines, a kind built on one, a file's own
  line, `entity=auto`, a tier of one's own, the fluid recipe, no tier, every refusal, and tiers
  imported with their file.
