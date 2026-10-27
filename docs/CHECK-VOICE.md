# The voice of the checks: a survey

Rory, 2026-10-27: "search through their toolkit for loud warnings like MISSING and try and come up
with more comfortable replacements that are neutral and descriptive and less loud and frantic.
MISSING can probably become not-placed." And: "some warnings like CLOG should stay loud."

So this is a survey of every label the toolkit prints at a player, and a decision for each. The
rule I used:

- **Stay loud** (capitals): the label means the base can jam, starve, stop building, or put items
  on the wrong belt. Someone has to act now, and the word should feel like it.
- **Calm** (lowercase, hyphenated, descriptive): the label describes a *state* - where something
  is, what is not there, what happened - and the usual answer is the next build, not a rescue.
  These say what is observed, not what is feared.

Two labels per line below: what it means today, and the word I propose.

## Stay loud (8)

| label | what it says | why it keeps its voice |
|---|---|---|
| `CLOG` | two or more items share one belt or chest, and one that comes faster than it is used fills it and stops the others | the base backs up and the rest of the line stops with it |
| `SHARED_SINK` | an unlimited chest shares a net with machines: whoever stands first gets its fill, so the machines starve | silent starvation, hours later |
| `SUSHI_SINK` | a net reaches a machine that does not take every item on it, so the net backs up at that machine | a jam that only shows when the belt fills |
| `SUSHI_LIMIT` | a `limit=` on a chest a mixed belt feeds: the slot limit only brings the stall sooner | it makes `CLOG` arrive earlier, not later |
| `SPILL` | one net's items reach another net (today `LEAK`) | wrong items on a belt, the failure that looks like magic |
| `WRONG-LANE` | items sit on a belt lane the layout gives other nets (today `LANE`) | the same wrong-items symptom, one level down |
| `NO_POWER` | a factory's poles reach no grid with generation | nothing in the factory runs |
| `UNREACHED` | the paste lays entities where no powered roboport reaches, so they stay ghosts for ever | the build silently does not happen |

## Calm (the descriptive rest)

| label | what it says | becomes |
|---|---|---|
| `MISSING` | a designed entity is not standing | `not-placed` |
| `UNPLACED` | a design entity has no `@(x, y)` hint, so it has no position | `no-position` |
| `MISPLACED` | ghosts stand somewhere other than the design says | `not-where-designed` |
| `WRONG` | a different entity stands on a designed tile | `other-entity` |
| `WRONG_ITEM` | a belt or chest holds another item than the net carries | `other-item` |
| `GHOST` | a ghost stands (waiting for robots) | `ghost` |
| `MARKED` | something built by hand stands, marked for later | `marked` |
| `CLAIMED` | the tile is inside a claim | `claimed` |
| `NOBODY` | the tile is outside every plot and claim | `unowned` |
| `DRIFT` | settings differ from the design | `settings-changed` |
| `OK` | it is as designed | `ok` |
| `UNFED` | a machine's input has no net | `no-feed` |
| `UNDERFED` | a net's drivers make less than its consumers take | `short-feed` |
| `UNCONSUMED` | a machine's output goes nowhere | `no-taker` |
| `NO_SINK` | a maker's product reaches none of its net's consumers | `no-destination` |
| `UNROUTED` | no belt route was found for a net | `no-route` |
| `OPEN` | a net's route reaches some of its machines, not all | `partly-connected` |
| `UNUSED` | a declared net that nothing uses | `unused` |
| `TYPE` | a net names a machine with no endpoint for its items | `cannot-carry` |
| `DOUBLE` | one machine input or output sits on two nets | `two-nets` |
| `CARRYOVER` | a feed rides a product's belt into the product's sink | `feed-rides-on` |
| `LANES` | two single-item nets feed the same machines on two belts, each using a lane, so half of both is empty. **Advice, not a fault** (it is in `ADVICE`, and the stage step leaves it out of the fault list): the two belts can be one | `could-pair` |
| `ORDER` | a bus tap stands before any load, so nothing feeds the bus there | `tap-too-early` |
| `UNLIMITED` | a provider or storage chest has no `limit=` | `no-limit` |
| `UNBOUNDED` | a supply has no `rate=` | `no-rate` |
| `ASSERT` | a rate you asserted is not met | `rate-not-met` |
| `TARGET` | the surface's target rate is not met | `target-not-met` |
| `SIZE` | an `n=auto` row cannot meet what is asked, or its net asks more than its belts carry | `size` |
| `FIT` | a sized row runs past its plot or into another frame | `does-not-fit` |
| `CAPACITY` | a machine runs short of a net's item as laid, with its lanes or inserters full | `too-thin` |
| `TURNED` | belts or inserters stand under the right name facing another way; the build re-lays them | `re-laid` |
| `RIP` | the build takes up a lot and the robots need minutes | `taken-up` |
| `HAND` | the build replaces or removes something placed by hand | `by-hand` |
| `INVARIANT` | a structure is malformed (a tile owned twice, a plot outside its ground) | `malformed` |
| `PORT` | a port is unused, misdirected or off its frame | `port` |
| `SEAL` | a net crosses a sealed frame outside a port | `crosses-frame` |
| `BOOTSTRAP` | a net's route needs an item whose only maker takes from that same net | `bootstrap` |
| `NO_ROBOTS` | a chest or entity is outside the robots' areas | `no-robots` |
| `POWER_SPLIT` | one grid splits into pieces that cannot share power | `power-split` |
| `ON_TERRAIN` | something designed stands on water or a cliff | `on-water-or-cliff` |
| `OFF_WATER` | an offshore pump's water side is dry | `no-water` |
| `OFF_ORE` | a drill has no ore in its mining area | `no-ore` |
| `LOW_STOCK` | the network holds fewer of an item than the build still needs | `short-stock` |
| `LOCKED` | an item or recipe is not researched | `needs-research` |
| `SELECT` | a `set` matches nothing, or names an unknown property | `no-match` |
| `GUARD` | a `guard`'s inserters cannot filter | `cannot-filter` |
| `SIGNAL` | a condition reads a signal nothing makes | `no-signal` |
| `WIRE` | a wire nothing drives or reads | `no-wire` |
| `WIRE_REACH` | two ends of a wire are further apart than a wire reaches | `wire-too-far` |
| `WIRE_LEAK` | two wires of one colour on one entity, so their signals add | `wires-share` |
| `GATED` | a gated net the rate model takes as always open | `gate-open` |
| `REQUIRE` | a `behave` block's `require` does not hold | `require-not-met` |
| `TERRAIN` | there is no terrain file, so the layout is not checked against the ground | `no-terrain` |

## Not warnings at all (already neutral, or markers that must stay terse)

- `EMPTY`, `FULL`, `DAMAGED`, `DECON`, `ATTACK`, `UNCOVERED`, `FLUID_DRY`, `FLUID_OPEN`,
  `NET_SPLIT`, `UNPAIRED`, `WRONG_LANE`, `WRONG_TYPE`, `NO_NETWORK`, `TRESPASS`: these are the
  per-tile markers of `fk look`'s render, where a word is one cell of a grid. They stay as they
  are; shortening them further would cost the render its alignment.
- `fk look`'s `GHOST SHORT` / `GHOST LOCKED` become `ghost short` / `ghost needs-research` with the
  rest.
- Report words that are sentences, not codes (`routed`, `kept`, `failed`, `turn capped`), keep
  their words but not their volume: `failed` becomes `not routed` where it is a route that did not
  find a way.

## What applying it touches

- `fkcore`: the string in every `Check(...)` and the few comparisons that read a code back
  (`ADVICE`, `stop_on`, `stage`'s filters, `_stops` in `upgrade_run`). About 90 literals.
- `agent/docs`: the "The checks" glossary in `TOOLKIT.md`, plus every mention in `LANGUAGE.md`,
  `EXAMPLES.md`, `STRATEGY.md` and the three briefs (`LANES`, `CARRYOVER`, `GHOST SHORT`, ...).
- Build scripts: `stop_on UNROUTED NO_SINK` becomes `stop_on no-route no-destination` in
  `kickoff/template/game/nauvis.build.fkb`, and `upgrade_run._stops` learns the new words so it can
  still patch an older run.
- Tests: the codes asserted in `test_lanes_check`, `test_lanes_pairs`, `test_ports`, `test_apply`,
  `test_look`, `test_flow` and friends, and `tests/data/elaboration-baseline.json` (its digest
  covers the check lines, so it is regenerated - 21 entries changed for `LANES` last time).
- Pinned runs keep the old words: a run's toolkit is its own commit, so a live run keeps `MISSING`
  until it is upgraded. That is the one place the old voice stays, and it is the argument for doing
  this now rather than after the next run starts.

## Recommendation

Apply it in one release (2.0.52) rather than piecemeal: half a vocabulary is worse than either
whole one. The danger family keeps its capitals, so the loud/shout distinction survives; everything
that only describes a state stops shouting.
