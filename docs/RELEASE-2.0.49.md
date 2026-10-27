# Toolkit 2.0.49: a line of cells (stacks)

Rory, 2026-10-26: a "more generic linear template, with each unit programmed routed and validated
like any other module, but this one is special and has matching input and output ports on opposite
sides so that it can stack linearly", and "it should be possible to do it with every belt routing
as 3 belts in a row, no bends or undergrounds". In a packed cell the power is part of the design:
"a power pole and two undergrounds in every row".

## What was wrong

- A repeated unit (a cell) had to be copied by hand: N instances of the module and N-1 nets
  written out between them, each of them a net the source owned.
- Inside a small cell the router looked for a tree or a hub: turns and undergrounds wherever it
  could, and in a 3-row cell there is no room for either, so a cell that needed a straight belt
  could fail to route at all.
- A tile the design needs for itself (a pole's, in a cell packed tight) was an obstacle: the
  router went round it or gave up, and the power step then added its own pole elsewhere.
- A product whose sink sits at the end of a belt that also brings it a feed (sulfur riding the
  blue science packs' belt) failed silently: the feed fills the chest and the belt stops for the
  product too.

## The model now

**A cell says how it stacks.** In a module, `stack NEAR -> FAR[, NEAR -> FAR ...]` pairs a port
on the edge toward the line's head (NEAR) with the port on the opposite edge at the same pinned
tile (FAR): one port `in` and one `out`, carrying the same items. The two ports meet on the shared
edge when cells stand side by side.

```
module Cell size 9x3 {
  port f_in  : in  iron-plate      @s1       # the feed: in at the south edge,
  port f_out : out iron-plate      @n1       # on to the next cell at the north edge
  port g_in  : in  iron-gear-wheel @n7       # the product: from the cell beyond,
  port g_out : out iron-gear-wheel @s7       # back toward the head
  stack f_in -> f_out, g_out -> g_in
  ...
}
line = Stack<cell=Cell, n=12> @(0, 4)
```

**`Stack<cell=CELL, n=N, head=HEAD>` is a module of its own.** Elaboration builds it: the head
(optional) and N cells edge to edge, growing toward the FAR edge, and for each pair one net
between each cell's FAR port and the next cell's NEAR port. Nothing new is routed through those
nets: 2.0.48 made a port an edge, so a cell's FAR and the next one's NEAR meet on one edge and the
net **lays nothing**. Every cell is an ordinary sealed instance, routed, contracted and checked
like any other (`line/0`, `line/1` ... in the reports).

- `line.P` names the head's port P; with no head, the first cell's NEAR port P or the last cell's
  FAR port P.
- The last cell's FAR ports are ends: nothing need come out of them, and they draw no PORT line.
- The items flow as the ports' directions say: a feed head to tail, a product tail to head.

**Inside a cell every belt runs straight.** A cell's nets are marked straight, and the router
tries a single straight run from its start to its goal first, one inserter per machine (a fast
one where it reaches, long-handed where only that does), before any tree or hub. A port of two
items (`sulfur | chemical-science-pack`, with `lanes A | B` inside) is one belt that comes in
already paired: it runs straight on, both lanes, and every machine hands on or off it.

**`Pole` pins a pole.** `Pole<pole=medium-electric-pole>` is one electric pole, part of the
design. A straight run tunnels under it (an entrance on the tile before, an exit on the tile
after, within an underground's reach), and the power step keeps the pole and adds only what is
missing. It moves no items.

**`CARRYOVER`** (a `report_rates` line): a sink at the end of a belt that brings it a product and
also a feed, an item machines upstream on the same belt consume. What they don't take of the feed
fills the sink, and the belt stops for the product too. A sink whose `set` hands are filtered
(`set packs.in: filter=chemical-science-pack`) takes it out of the warning.

## What changed underneath

- `lang`: the `stack` statement (`Module.stacks`); `Stack` is a template name like any other.
- `elaborate`: `_stack_module` builds a `Stack` as a module (head, cells, the nets between them)
  and expands it like any module instance; `Flat.stacks`, `stack_alias` (a ref to a stack names
  an end cell's port), `stack_ends` (the dead ends, no PORT line).
- `expand`: a pair port binds the pair's lane key (`lane_of`), so a paired port is one belt of
  both lanes; `Pole` is a single-machine template.
- `route`: `NetJob.straight` (every net inside a stack cell), `_straight` (one straight belt, one
  inserter per machine, a tunnel under a taken tile), `_prejoined` (a pair whose two nets come in
  already paired runs on as one straight belt: "paired at its port"), and `pairs`/`route` carry
  `allow` so the crossings a sealed frame permits reach the pair search too.
- `rates`/`flow`: `rates.carryover` and its `CARRYOVER` line in `report_rates`, with
  `_filtered_out` reading the sink's `set ... filter=`.
- `templates`: `Pole`.
- Docs: a "Stacks" section in `LANGUAGE.md`, `CARRYOVER` in `TOOLKIT.md`, and `EXAMPLES.md` with
  every example marked current or older, plus `docs\examples\blue6.fk` and its section.
- Tests: `tests/test_stacks.py` (10) and `tests/data/stacks/` - the four-cell line, the blue
  stack, the hand-patched unit as a Literal, and the CARRYOVER cases.

## Verified

- The full suite: **1002 tests, OK** (2.0.48: 992).
- The four-cell line: 6 joins lay nothing (3 joins x 2 pairs), each cell's two nets 3 straight
  belts, connected, 0 LEAK; the product runs from each cell into the one before it.
- `blue6.fk`: every cell belt heads north, 4 underground ends = a tunnel under each cell's pole,
  the paired port's net "paired at its port", no SEAL, FRAME or PORT line from the routing, 0
  LEAK. On the lab at 1825, 420: 223 entities, every inserter powered, sulfur on the left lane
  and packs on the right, the chest holding packs only; without the filter, `CARRYOVER` says the
  sulfur would fill the packs' chest.
- `blue2cell.json`: the cell patched by hand on the lab loads as a `Literal` and lays out 18x6
  with its 6 machines.
- Every example that was in `agent/docs/examples/` on 2.0.48 gives the same `fk check` first line
  as it did there.

## Open

`fk check blue6.fk` still prints 25 netlist lines (`DOUBLE`, `SUSHI_SINK`, `CLOG`, `PORT`). They
come from one place: a port of two items publishes both items on both nets of its pair, so each
net looks like a sushi belt to the netlist even though the pair splits it one lane each. The
routed model and the tests are clean. The fix is for a pair port to bind *its left lane's net* to
the left item and the right lane's to the right one, so the netlist sees what the belt carries;
that is 2.0.50 work.
