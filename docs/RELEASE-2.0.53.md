# Toolkit 2.0.53: advanced oil, electric furnaces, modules, and your own templates

Rory, 2026-10-28: templates should be the player's own, not look like the toolkit's; electric
furnaces should be easy to put in a template or a line; advanced oil did not come out as three
nets. A cleanup pass from the live run's friction.

## Advanced oil comes out as three nets

The starterbus run's FRICTION.md (2026-11-02, round 69): `ref = Refinery<recipe=advanced-oil-processing>`
with `net heavy5: ref -> hcrack`, `net light5: ref, hcrack -> lcrack`, `net gas5: ref, lcrack -> ...`
stopped at route. A net with no `items` took everything its drivers make, so each of the three nets
took all three oils (`two-nets ref/m0: heavy-oil (out) is on 3 nets`) and the router could attach
only one output box.

Now a net with no `items` whose drivers make two or more fluids takes the fluids its consumers take
(a pipe holds one fluid): `heavy` gets the heavy oil, `light` the light oil, `gas` the gas, and the
refinery has one port per fluid. A net whose consumers take none of them (a chest) keeps them all,
as before; a declared `items` always wins. A crude + water -> refinery -> heavy and light cracking ->
sulfur chain routes with every net connected.

`two-nets` now says what to do: name each net's items (`net ore_ items iron-ore: ...`). That covers
the other case from run 0042's friction, one requester holding ore and coal feeding a SmelterRow's
two nets: the furnaces take both, so only the source can say which net carries which.

## Electric furnaces

- `SmelterRow<n, recipe, machine=electric-furnace>` lays them at 3 tiles each, as an AsmRow, ore in
  and plates out, no fuel. Before, it laid them at the stone furnace's 2-tile pitch and `fk layout`
  crashed (`centre ... is inconsistent with size (3, 3)`).
- `agent/docs/examples/furnace-column.fk`: a column of the player's own cells, one electric furnace
  each between an ore belt and a plate belt, `Stack<cell=FurnaceCell, n=8>`. Eight furnaces with two
  productivity modules each, routed and connected.

## `modules=`

A common parameter on every machine and row: `modules=speed-module` fills every slot of its
machines, `modules=productivity-module|speed-module` names them slot by slot. The paste carries the
module requests in the game's `items` field (Codex's lab format, 2026-10-28: robots fill them, and an
unchanged rebuild keeps them), and the rate model counts each module's speed and productivity.
A machine with no slots (assembling-machine-1, burner furnaces) or too many modules is refused at
elaboration. The slots are a table in `fkcore/templates.py` (`MODULE_SLOTS`), since the catalog has
none. Beacons are not modelled: a beacon is still a Literal.

`fk lab` puts the requested modules straight into their slots (no robot flies on the lab), as it
stocks requester chests: `modules put in: 16` in its report.

## Your own templates

LANGUAGE.md now calls the template table "the built-in kinds", a starting kit, and says first that
a `module` you write is a template of your own and `Stack` lines up as many as you want: write the
module before reaching for a Literal or a generator script.

## Not changed

- The pipe router can still fail a dense oil block: on a tight layout it lays a pipe-to-ground pair
  that the judge then refuses (`routed, but the judge says: 1 of 2 driver->consumer pairs
  connected`). Spacing the plants apart routes it. A router fix is its own change.
- 2.1's multi-lane nets (a net wider than one lane) are not in this release.

## Tests

`tests/test_cleanup_2053.py` (10): the oil chain's nets and route, one-fluid drivers unchanged, a
chest keeping every fluid, the electric SmelterRow's pitch, module requests on rows and single
machines, the rates with speed and productivity, the refusals, and the furnace column example routed.
Full suite: 1016 tests, OK.
