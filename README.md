# v5: the V1 core toolkit

The Factorio V1 core (`..\CORE-V1.md`, decisions 1-12). The one-page spec is [CORE.md](CORE.md).
Python stdlib only; nothing here talks to the game.

## Where V1 lives

- **This repo** (`C:\Users\Admin\zybo\factorio-design\v5`, its own git repo like `v4-hand`): the
  toolkit. `fkcore/` is the core (catalog, `.fk` parser, elaborator, templates, rate model, `.fkp`,
  blueprint codec, compose); `tests/` are its tests.
- **A game codebase** (one per game, CORE-V1 §4.1): `.fk` factories, their `.fkp` layouts, the
  surface file, `build.fkb`, `out/`. Kickoff will create one per run. Until then `games/spm10/` is
  the paper one: spm10 rewritten as a V1 factory.
- **The components codebase** (one, shared): starts as `components/` here when the first component
  exists, and moves to its own repo when a second game needs it.

Copied, not imported, from `C:\fk-lead\repo` at d6018d3: `fk/catalog.py` and `fk/catalog-v5.json`,
the tokenizer of `fkc/lang.py`, the blueprint codec of `fk/trace.py`, the rate model's approach in
`fkc/flow.py`, the stamp geometry in `fk/stamps/`. Each file says what it took.

## Run

```
python -m unittest                       # from this folder
python -m fkcore rates games/spm10/main.fk
```
