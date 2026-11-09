# 40-layout: routability-driven layout (PLAN-4.0 part P, wave 1: P1 to P3)

Branch `claude/40-layout`, cut from main 4afcb33 (3.1.3 + PLAN-4.0). Measured 2026-11-08 on this
laptop, fkroute built from the tree (`python tools/native_build.py`, 0.2.0 + `place`).

## What shipped

- `fkcore/layout.py`: the spec (instances with a footprint and attach groups per rotation, nets
  with weighted terminals, the box), the Python reference `_place_py` (the Lagrangian loop in
  integer milli-tiles), `build_spec` from a Flat (fragments turned per rotation as `placer.shape`
  turns them; a single machine's attach is the ring where its inserter stands; a sealed module's
  ports are fixed terminals at their edge tiles), `hint_line` (textual: replace an `@(...)` or add
  one after `Kind<...>`, before a trailing comment), `layout_file` and `fk layout`.
- `native/fkroute/src/place.rs`: `field` (the walk with a price per tile entered, dense distances
  and predecessors) and `place` (the loop, step for step with the Python). Registered in `lib.rs`
  with one `mod place;` and two `add_function` lines, nothing else touched.
- `fk layout FILE [MODULE] [--all] [--write] [--sweeps N] [--plot WxH]` in `__main__`; the old V1
  `fk layout FILE [--render]` (wrote the .fkp; the build's `place` step does that, nothing called
  it) gave up the name.
- `agent/docs/examples/layout.fk`, the section in EXAMPLES.md chapter 9, the LANGUAGE.md instance
  row, the TOOLKIT.md command row; `tests/test_examples_docs.py` lays `layout.fk` out with
  `--write` before its paper build (`LAID_OUT`), so the quoted summary stays the build's.
- `tests/test_layout.py`: adjacency, the crowded fan-out spreading, ports kept and never covered,
  no-fit as None, determinism and no overlaps on random specs, Python/Rust parity on random specs
  and `FK_NATIVE=check`, `hint_line`, the `--write` round trip (the written mall elaborates with
  every instance placed and a paper build routes every net), the CLI, the docs quote.

## The numbers

| case | frame | hand layout | `fk layout` | sweeps | fkroute | Python |
|---|---|---|---|---|---|---|
| mall.fk (11 instances, 8 nets) | 34x44 | 132 carriers, 8/8 routed | **96 carriers, 8/8 routed** (135 entities, 5 underground pairs) | 22 | 1.0 to 1.5 s | 46.8 s |
| line11.fk (18 instances, 12 nets) | 44x11 | 179 carriers, 12/12 routed (tier line; its paper build stops at floorplan: the roboport runs off the 11-tall plot) | 76 carriers on 9 nets, **3 failed** (`fe_`, `gw`, `o2`: `UNREACHED fe/c0` etc.) | 40 (the cap) | 0.9 s | not run |

Carriers = belts, undergrounds and splitters in the built .fkp (the tier line's count for line11).
Estimated belts (the relaxed distance, tiles): mall 52 -> 13, line11 65 -> 24.

The mall meets the plan's bar (no more carriers than the hand layout) in wave 1. line11 does not
yet: in an 11-tall strip the loop boxes the iron chest `fe` in on three sides (gm west, blt north,
ins south), and the one free ring tile has no tile behind it for the belt, so the router cannot
reach it. The relaxation counts a ring tile as reachable when it is free; the router needs the
inserter's tile **and** the belt's tile behind it.

## Open (P4, wave 2)

- A ring tile should count only with its outward neighbour free (the belt behind the inserter),
  or the ring should be the distance-2 ring with the distance-1 tile required free. Both
  implementations change in `free_tiles`/`fits`; the spec format can stay (the outward step is
  the step away from the footprint's box). Expect the mall numbers to move; re-quote the example.
- grove.fk (a real lab module) and the lab bays' generators (`lab-session\baygen.py`) are untried.
- MODULE mode (a sealed module laid out inside its frame, ports fixed) is built and typed but has
  no example or test beyond the spec-level `ports stay` test.
- The Python reference is 45x slower than the kernel on the mall (a field per candidate per
  incident net); it is the reference, not the tool, and FK_NATIVE=0 still works.
- The weight is `ceil(rate / one yellow belt)`, at least 1; every mall net weighs 1. A net riding
  another's belt (`lanes`) counts for each of its parts.
