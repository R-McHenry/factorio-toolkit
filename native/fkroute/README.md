# fkroute: native router kernels

Rust (PyO3) versions of fkcore's hot loops. fkcore stays pure Python: when `fkroute` is not
installed, or `FK_NATIVE=0` is set, every kernel runs its Python original.

- `astar`: `fkcore.steiner._astar`, one A* from many start states to the nearest target sink.
  A port of the Python search, step for step, with Python's tie-break (heap order
  `(f, -g, state)`), so it returns the same path. Tap sinks call back into Python for their goal
  test (it needs the tree); everything else runs native.
- `grow`: `fkcore.steiner.grow`, the whole forward tree search (starts, A*, attach, the reroute
  rounds), taps included, for plain `FixedSink` / `TapSink` sinks. It keeps Python's quirks: the
  `succ` dict's order, and `sink_terminal` holding only the end attached last (`Tree.copy()` does
  not copy it). Sinks of their own (m2m's) run the Python `grow`, whose steps use `astar`.
- `walk`: `fkcore.route._walk`, belt distances over a bounded grid (the same dict, in the same
  order), used by the hub, join and ribbon searches.
- `hubs`: `fkcore.route._hubs` after its seeds: every walk and the candidate ranking in one call.

`FK_NATIVE=check` runs every kernel both ways and raises on any difference.

Build and install into the current Python (from this folder):

    python -m maturin develop --release

or build a wheel: `python -m maturin build --release` (it lands in `target/wheels`).

Parity: `python -m unittest tests.test_native` (v5) routes the same layouts both ways and
compares every carrier.
