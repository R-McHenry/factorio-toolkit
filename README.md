# v5: the V1 core toolkit

The Factorio V1 core (`..\CORE-V1.md`, decisions 1-12). The one-page spec is [CORE.md](CORE.md).
Python stdlib only; nothing here talks to the game.

## Where V1 lives

- **This repo** (`C:\Users\Admin\zybo\factorio-design\v5`, its own git repo like `v4-hand`): the
  toolkit. `fkcore/` is the core (catalog, `.fk` parser, elaborator, templates and fragments, rate
  model, `.fkp`, blueprint codec, compose, connectivity, router, power cover, flow runner, surface
  file, literal import, merge/rewire, scene and sense); `scenario/fk-play/` the lab scenario (not
  deployed); `tests/` the tests.
- **A game codebase** (one per game, CORE-V1 §4.1): `.fk` factories, their `.fkp` layouts, the
  surface file, `build.fkb`, `out/`. Kickoff will create one per run. Until then, on paper:
  `games/spm10` (spm10 as one V1 factory, rates only), `games/redgreen` (the red-green part placed
  and built through the flow), `games/nauvis` (plant + boot + main on one surface),
  `games/merge` (two factories linked by robots, for merge and rewiring).
- **The components codebase** (one, shared): starts as `components/` here when the first component
  exists, and moves to its own repo when a second game needs it.

Copied, not imported, from `C:\fk-lead\repo` at d6018d3: `fk/catalog.py` and `fk/catalog-v5.json`,
the tokenizer of `fkc/lang.py`, the blueprint codec of `fk/trace.py`, the rate model's approach in
`fkc/flow.py`, the stamp geometry in `fk/stamps/`. Each file says what it took.

## Run

```
python -m unittest                                   # from this folder
python -m fkcore rates games/spm10/main.fk
python -m fkcore build games/nauvis/nauvis.build.fkb   # the whole flow; reports in out/
python -m fkcore look games/nauvis --source design
```
