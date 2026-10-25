# Toolkit 2.0.15: the lowest hand, raised only where the flow needs one

Rory, 2026-10-25, after 2.0.14 laid the choice of a *family*: "The default should probably be
lowest, and it would go higher if it senses a bottleneck in thruput model at the inserter. model
might not be ready for that yet, you can assess."

**The assessment: the model is ready for this, in the main stroke.** The pieces it needs are all
there and were used as they are:

- `fkcore.routed.required` is the flow through **every connector** with the machines at nominal
  rates and **no capacities**, so what a given inserter must pass does not depend on the hand that
  is laid: the question is well posed, not circular. It is the same table `tier` already reads for
  belt lanes and the one behind every `CAPACITY` line.
- `fkcore.lanes.inserter_rate` gives each prototype's items/s with the force's hand sizes, the bulk
  and stack bonuses, and the drop-onto-a-moving-belt derating, and `lanes.build` already computes
  that derating per inserter from the geometry.
- `fkcore.tiers` is the working template for a per-connector pass with "never below what stands",
  a report line and a note when the top rung does not fit.

What it does not model, and why the pass is raise-only by default: an inserter picking off a moving
belt is slower and more erratic than one picking from a chest (only the drop is derated); a
connector that binds on paper may be buffered in the game; and a connector's share of two items is
summed (conservative: it raises sooner). A bulk or stack inserter is modelled, but the router does
not lay one yet, so the ladder stops at fast — `hands --allow inserter,fast-inserter,bulk-inserter`
already asks for more if a design wants it.

What changed:

- **`hands` is a build step** (`hands minimize`, in the template right after `route`): every short
  hand is the lowest rung, raised only where the connector's required flow exceeds what the rung
  carries. `out/hands.txt`: `hand minimize (allowed: inserter, fast-inserter): 41 short hands on
  nets; 33 inserter, 8 fast-inserter; 8 changed` and `raised for the flow: gears/f0 (gears), ...`.
- **`minimize` never goes below the hand that stands** in the committed `.fkp`, so an upgraded base
  keeps its fast inserters and only new ones come in plain; `--downgrade` takes them back (useful to
  reclaim fast inserters from a base that never needed them). `hands maximize` is the old
  fast-everywhere. A rung the network cannot build now is skipped, and the line says what that cost.
- **Every default is the lowest buildable now**: `route --hand any` (the default), and a row with no
  `inserter=` (a `SmelterArray` keeps its own plain default). `any` therefore means "the cheapest
  that can be built", and `best` is the escape hatch that asks for a fast inserter directly.
- A hand the design names itself is never touched: `inserter=fast-inserter` on a row, every tap
  when the script says `route --hand fast-inserter`, and every `Literal`'s entities (a Literal is
  pinned as it is, as `fkcore.tiers` pins it): the kickoff plant's own inserters stay as they are.
- `upgrade_run.py` adds the `hands` step to a run's script, after its route line.

**On the live base** (a dry run of the 2026-10-25 run's own design, `--to hands`): 24 short hands,
all fast, **0 changed, 19 kept from the committed .fkp** — an upgraded base keeps every hand it has,
and only new blocks come in plain and get raised by the flow. That is the point of raise-only: the
upgrade is not a rebuild of the inserters it already paid for.
- `TOOLKIT.md`, `LANGUAGE.md` and `STRATEGY.md` say it in one place each; `docs/RELEASE-2.0.14.md`
  keeps the record of the family (its `any` was "best buildable", which this release replaces with
  "cheapest buildable").

Tests: `tests/test_hands.py` (11: a gear row is raised to fast, a stone furnace row stays plain, a
named hand is left alone, an unbuildable rung is skipped, maximize, downgrade, arg checks), the
`test_avail` cases moved to the new order, and `test_upgrade_run`'s hands step.
