# 2.1.30: the promoting pass reuses what it can, the standing nets cost less

The 20261030-2352 player's dry build (11-01 02:43, 2.1.28): route's belt passes took ~150 s, in
three passes of all 278 nets: pass 1 (~60 s), pass 2 (~30 s, the failed nets first) and the
promoting pass (60+ s). Four nets fail in every pass (coal, fe3p, st3o, c4_suo: 5-14 s each, a
pass's search budget spent), and the promoting pass laid all 278 again to try promoting those.

## What changed

- **A pass in the last pass's order takes its answers.** The promoting pass runs in the order of
  the pass before it (route goes to it when another pass would repeat that order), on the same
  ground, so each net's plain search gives the last pass's answer, until a promotion succeeds
  and the ground changes. Those nets now take that answer instead of searching again; a failed
  net goes straight to its promoted search. The routes are the same. When no promotion
  succeeds, the promoting pass costs only its promoted searches.
- **Standing nets:** a patch that keeps every carrier of its net uses the graph just built for
  it, instead of building the same one again; connect's sorts use the remembered tuple keys.
  The run's world: the standing step 11.2 s -> 10.3 s (only 2 of its 15 patches keep every
  carrier; the rest rebuild the graph after each branch, ~0.1 s each, and stay as they were).

## Checked

- tests/test_route_promote: the promoting pass runs x's plain search once, not twice (it failed
  on 2.1.29: ['x', 'x']), with the same promotions.
- tests: the whole suite. golden against 2.1.29.
- Not measured on the run's world: reaching its promoting pass takes ~2 min, past what a probe
  should run; the player's next build's progress lines show it.
