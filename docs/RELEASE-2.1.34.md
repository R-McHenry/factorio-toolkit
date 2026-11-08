# 2.1.34: the router's hot loops in Rust

This is the merge of `claude/rust-route` (the native router) with `claude/lab-megabase` (2.1.31 to
2.1.33) on main.

## fkroute: a native kernel (native/fkroute)

- **What runs in Rust** (PyO3, abi3, one wheel for Python 3.8 and later):
  - `steiner._astar`;
  - the hub walks (`_walk`, `_hubs`);
  - `steiner.grow` whole: starts, A*, attach, reroutes and taps.

  m2m's own sinks keep the Python `grow` on top of the native A*.
- **Speed:** `tests.test_route` takes 2.05 s, down from 17.9 s before this work. A* went from
  10.7 s to 0.65 s, and `grow` from about 11.5 s to 0.37 s.
- **fkcore stays standard library only:**
  - a machine without the wheel runs the Python search, now about 10 s on `tests.test_route`
    thanks to the per-entity ground cache below;
  - `FK_NATIVE=0` forces Python;
  - `FK_NATIVE=check` runs both and raises on any difference.
- **Parity:** native and Python lay the same trees, move for move, including the heap's tie order,
  the cost sums and the soft ground. `tests/test_native.py` checks this on hundreds of random
  fields. It is skipped when the wheel isn't installed.
- **The lane-pair join:** the kernel obeys 2.1.31's `Grid.no_bend` (a lane pair's join runs
  straight on: no turn and no tunnel). The rule covers A*'s belts only, in Python and Rust alike.
  A splitter may still stand on the join tile, and a step `grow` lays itself (from a dropped
  split) may turn there.
- **Build:**

  ```
  cd native/fkroute
  python -m maturin build --release -i python
  pip install target/wheels/fkroute-*.whl
  ```

  This needs Rust (rustup) and `pip install maturin`.

## Per-entity ground

`_ground` reads each entity's tiles, belt fronts and hand tiles from a memo on the catalog, keyed
by the entity's value. It keeps the first-owner rule of `_belt_fronts` and `_hand_tiles`, and
2.1.33's box index of the other nets' ends.

## Negotiated routing (opt-in, FK_NEGOTIATE=1)

PathFinder-style negotiation, run inside each compile unit before its passes:

- **How it works:**
  - every net is routed as if alone, but a belt may cross another net's route by paying
    `(1 + history) * (1 + pres * nets there) - 1` a tile;
  - `pres` doubles each round and history grows on contested tiles, for up to 8 rounds;
  - splitters and taps never stand on soft tiles;
  - nets still clashing after the last round are laid again on hard ground.
- **Fallback:** the passes run only when negotiation leaves a net unrouted, and the better result
  is kept.
- **Results on 148 test layouts:** the same 909 nets routed, 9 % fewer undergrounds, 1.6 % more
  carriers, about twice the time.
- **Status:** off by default, because the time doesn't pay for itself yet.
