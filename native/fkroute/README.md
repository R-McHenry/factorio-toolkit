# fkroute: native router kernels

Rust (PyO3) versions of fkcore's hot loops. fkcore stays pure Python: when `fkroute` is not
installed (or is older than 0.3), or `FK_NATIVE=0` is set, every kernel runs its Python original.
`FK_NATIVE=check` runs every kernel both ways and raises on any difference.

What the kernel covers (0.3.0, PLAN-4.0 part K, wave 1):

- `physics(table)`: the lane physics as data. `fkcore.steiner` hands it `lanephys.table()` once at
  import; the kernel keeps it in a OnceLock and states no lane rule of its own. `physics_lookup`
  reads it back (the parity test compares every lookup to `lanephys`).
- `astar`: `fkcore.steiner._astar`, one A* from many start states to the nearest target sink. A
  port of the Python search, step for step, with Python's tie-break (heap order `(f, -g, state)`),
  so it returns the same path. Sinks: a plain `FixedSink`, a plain `TapSink` with 3.0's goal run
  natively (the tail of `6 + 4(k-1)` tiles, k > 1 taps counted in the search key as Python's fifth
  state element, the force's arms as data per sink, inserter reach and tap cost by name from a
  table in the call), a `DropSink` (a drill's drop tile the tree may run through), and a
  `TapSink` subclass (m2m's `LeftTap`, `_EndTap`) whose goal is called back into Python.
- `grow`: `fkcore.steiner.grow`, the whole tree search (starts, A*, attach, the reroute rounds),
  forward or laid reversed (`drop_taps`, `keep_clear`, the merges' spare tiles), for plain
  `FixedSink` / `TapSink` / `DropSink` sinks. It keeps Python's quirks: the `succ` dict's order,
  and `sink_terminal` holding only the end attached last (`Tree.copy()` does not copy it). Sinks
  of their own (m2m's) run the Python `grow`, whose steps use `astar`.
- `walk`: `fkcore.route._walk`, belt distances over a bounded grid (the same dict, in the same
  order), used by the hub, join and ribbon searches.
- `hubs`: `fkcore.route._hubs` after its seeds: every walk and the candidate ranking in one call.
- `hub_search`: `fkcore.route._hub_search` with `_hub_trees`: the candidates, then per candidate
  the reversed tree to the drivers and the forward tree to the consumers over `_grow`'s passes
  (the sink lists Python enumerates), until three candidates route; the trees come back and
  Python lays the plan entities. m2m's hub (its own tap kind) stays Python.

Still Python: m2m's sinks (K4), the plan entities (K5), the pairs loop and its judge,
negotiation, patching, the ground.

Build it as this tree's own kernel (`<tree>/fkroute.pyd`, gitignored; found before any installed
one when Python runs from the tree):

    python tools/native_build.py          # cargo build --release, then the copy
    python tools/native_build.py --check  # which fkroute `import fkroute` finds from here

or install into the current Python (from this folder): `python -m maturin develop --release`.

Parity: `python -m unittest tests.test_native` (v5) routes random fields both ways and compares
every tree; `FK_NATIVE=check python -m unittest tests.test_route ...` does the same on the router
modules. `python tools/native_share.py tests.test_x ...` counts the grows, A*s and hub searches
per side and why a grow fell back.
