# Toolkit 2.1.7: module parameters

Draft for the "module parameters" phase of `assessment-20261031\PLAN-2.1.md` ("D. Module
parameters"); the integrator gives the number.

## What a player can write now

- **`module NAME<p, q=default> size WxH`** declares parameters. One without a default is
  required.
- **`$p`** stands for p's value wherever a word may stand: an item in a port, a net's `items` or
  another list, a parameter value, a signal, a `set` value, the text of `behave` and `expect`
  lines, and inside a quoted string.
- **Lists.** `ins=iron-plate|copper-cable` is a list. `$ins` spreads it where an item list goes,
  and `$ins[0]` picks one item. No arithmetic.
- **Instances.** `f = FurnaceCell<plate=copper-plate, ore=copper-ore>`. This replaces the refusal
  "a module instance takes only duty= and dnp".
- **Stacks pass parameters on.** `Stack<cell=FurnaceCell, n=12, plate=copper-plate,
  ore=copper-ore>` gives every parameter but `cell`, `n`, `head`, `built`, `duty` and `dnp` to each
  cell, and to the head when the head declares it. The cell is filled in before the Stack checks
  its ports.
- **Kinds of modules.** `kind CopperCell = FurnaceCell<plate=copper-plate, ore=copper-ore>` works,
  and a Stack's `cell=` (or `head=`) may name such a kind.
- **Inside a module** a parameter passes one on: `a = FurnaceCell<plate=$plate, ore=$ore>`.
- The header comes before the module's flags and frame: `module X<p> size WxH`.

## Identity

- A module instance's line in the `.fkp` carries its values, defaults included
  (`inst iron/0 FurnaceCell ore=iron-ore plate=iron-plate`). A Stack's line carries what it was
  written with. So a changed value re-lays the instance, as a changed recipe re-lays a row.
- `machine=auto` and `modules=auto` inside a parameterised module are one choice per set of values
  (`FurnaceCell<ore=iron-ore, plate=iron-plate>.f.modules`), so an iron and a copper line choose
  apart. A module without parameters keeps its key.

## New refusals

- A required parameter left out: `c: module FurnaceCell needs ore= (a parameter with no default)`.
- A parameter the module doesn't declare, on an instance, a kind or a Stack. A Stack's message
  names the cell's parameters.
- A module that declares `cell`, `n`, `head`, `built`, `duty` or `dnp`.
- An index past the end: `$ins[1]: ins is a list of 1 (iron-plate) in this AsmCell, so $ins[0] to
  $ins[0]`.
- `$p` where a name, a position or a size belongs: an instance, net, port, wire or signal name, a
  ref, `@(x, y)`, a port's side, `size`, `stack`, `lanes`, `set` and `dnp`.
- `$p` naming no parameter of its module, and `$p` outside a module (at the top level, in a kind
  line, or in a parameter's default).
- A flag for a value: `FurnaceCell<plate, ore=iron-ore>`.

## Inside

- `lang.py`: a `$name` token. The parser keeps `$p` and `$p[k]` as the strings `"$p"` and
  `"$p[k]"` (no word holds a `$`). `Module.params` holds the `MParam`s. `[` is read only after a
  `$p`, so `S[k].P` refs can come later.
- `elaborate.py`: `_with_args` checks an instance's values and `_Subst` makes a copy of the
  module's body with them, which is what is expanded. Ports, nets, signals and choices see only
  the substituted copy. `_stack_module` substitutes the cell and the head before its port checks.

## Checks

- Golden: 54 of 54 identical against 2.0.78.
- `tests/test_module_params.py`: the header and defaults, every refusal, one instance, two of one
  module, lists spread and indexed, values, signals, `set` and strings, a parameter passed on, a
  kind of a module, Stack forwarding, a kind as the cell, a kind of a Stack, the head, choices,
  and `tests/params/smelt.fk` elaborated, rated, routed and connected.
- Lab, on a laptop server (`LaptopServer("params")`, fk-play): `tests/params/smelt.fk`, the
  kickoff template's `FurnaceCell` with `plate` and `ore` as parameters, stacked four cells for
  iron (`Stack<cell=FurnaceCell, n=4, plate=iron-plate, ore=iron-ore>`) and four for copper
  (`Stack<cell=CopperCell, n=4>`), each fed by a requester. 148 entities, all 32 nets routed and
  connected, diff ok 148. Over 120 game seconds, after 2.5 minutes' running, each furnace made
  37.49 plates/min to the model's 37.50: 149.96/min of iron and 149.96/min of copper, to 150.0
  each. Over the first 60 s the furnaces read 36.98 to 37.98, each a craft either side.

## Not changed

- The kickoff template's `cells.fk` keeps its iron-only cells. The library release parameterises
  it.
