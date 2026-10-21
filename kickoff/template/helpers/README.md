# helpers: your reusable features

This folder is yours to grow. Put a helper here when you'd otherwise write the same script a second
time: a probe that reads the game, a calculation, one build action you repeat. Grown this way they
scale with the base, where a pile of one-off scripts turns into debt.

```
python -m helpers                 every feature, one line each
python -m helpers grids           run one (its arguments follow)
```

Run them from the run folder. A feature is a function in a module here, registered with
`@feature` in `helpers/__init__.py`'s way. Each has a docstring (its first line is what `python -m
helpers` lists) and takes plain arguments. Game reads go through `game.lua(...)`, which sends a Lua
chunk with your `fk lua`. The chunks live in `lua/`, one file per read, so you can also run them
alone (`fk lua --file helpers/lua/grids.lua`). Stdlib only.

Fair play, in Rory's words: a process over time that can be automated in the game belongs in the
game (circuits, a mall), not in a helper. A helper may read anything, compute anything, and do one
specific multi-stage build action (through `fk build`, ghosts and robots). It must not manage the
base or keep everything stocked through one-off crafters.

The seeds below came from what the first players wrote again and again:

| feature | what it says |
|---|---|
| `grids` | the electric networks by pole count, and every roboport without power |
| `machines [STATUS]` | each machine with its recipe and status (only those in STATUS, e.g. `no_power`) |
| `stock ITEM ...` | how many of each item the robot network holds |
| `labs` | what the labs wait for, pack by pack |
