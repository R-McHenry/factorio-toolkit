# 40-layout: routability-driven layout (PLAN-4.0 part P, wave 1: P1 to P3, and P4's rules)

Branch `claude/40-layout`, cut from main 4afcb33 (3.1.3 + PLAN-4.0). Measured 2026-11-08 on this
laptop, fkroute built from the tree (`python tools/native_build.py`).

## What shipped

- `fkcore/layout.py`: the spec (instances with a footprint and attach groups per rotation, nets
  with weighted terminals, the box), the Python reference `_place_py` (the Lagrangian loop in
  integer milli-tiles), `build_spec` from a Flat (fragments turned per rotation as `placer.shape`
  turns them; a sealed module's ports are fixed terminals at their edge tiles; a module without a
  size, a Stack, is one rigid body whose children's belt ends on the scope's nets are its attach
  points; a `lanes A | B` pair is one net), `hint_line` (textual: replace an `@(...)` or add one
  after `Kind<...>`, before a trailing comment), `layout_file` and `fk layout`.
- `native/fkroute/src/place.rs`: `field` (the walk with a price per tile entered, dense distances
  and predecessors) and `place` (the loop, step for step with the Python). Registered in `lib.rs`
  with one `mod place;` and two `add_function` lines.
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

## The attach rules (what the router needs, found case by case)

The first cut took a machine's attach as the ring where its inserter stands and counted a ring
tile usable when free. The router then failed the mall's `gears` ("no free tile is reached from
every driver and consumer (no hub)") and three of line11's nets: machines packed at 1-tile gaps
where a multi-consumer net has no belt room. The rules now, the same in Python and Rust:

1. A machine's attach group is the ring **two** tiles out (the belt's tiles); a tile counts only
   when it and its inward neighbour (the inserter's tile) are free. The relaxed route runs belt
   tile to belt tile over the free ground the router's hub needs.
2. A one-tile attach (a row's belt end, a port) may not take another instance's one-tile attach
   tile (a zero-length belt the router cannot lay; a pair needs a trunk), and the tile beyond it,
   away from the footprint, is free and inside the box (where its belt arrives or goes on).
3. A `lanes A | B` pair is one net in the spec (its ports' shared tiles are no crowding; the MST
   over its drivers is the trunk that collects them).
4. The sweeps cap is 150 (was 40): line11 was still improving at 40 and routes only past ~120;
   the mall stops on its own at 13.

## The numbers

| case | frame | hand layout | `fk layout` from no hints | sweeps | fkroute | Python |
|---|---|---|---|---|---|---|
| mall.fk (11 instances, 8 nets) | 34x44 | 132 carriers, 8/8 routed, 178 entities | **52 carriers, 8/8 routed**, 91 entities, 2 underground pairs | 13 | 1.0 s | ~60 s |
| line11.fk (18 instances, 12 nets) | 44x11 | 179 carriers, 12/12 routed (tier line; its paper build stops at floorplan: the roboport runs off the 11-tall plot) | **94 carriers, 12/12 routed** (tier line, the same floorplan stop) | 123 | 5.6 s | not run |
| grove.fk `Grove` (4 Stacks of 3 GreenB, 6 beacons, 12 ports; module mode) | 46x40 (its frame) | 256 carriers, 76/76 routed, 443 entities | Stacks in the hand layout's columns (x 2, 12, 22, 32) at y 17 (hand: y 10); **70/76 routed**, 6 unrouted: the pairs `cu1|fe1`, `cu2|fe2`, `cu3|fe3` ("no side-load point on the stem of 4 belts"); 522 entities, 334 carriers with those retries | 33 | 0.5 s | not run |

Carriers = belts, undergrounds and splitters in the built .fkp (the tier line's count where the
build stops at floorplan). Estimated belts (the relaxed distance, tiles): mall 62 -> 4, line11
110 -> 25, grove 20 -> 20 (the Stacks start where they end).

The mall and line11 meet the plan's bar (every net routed, no more carriers than the hand layout).
Grove does not yet: a paired belt that collects two module ports needs a straight stem of four
belts before its side-load, and the layout puts each Stack's foot one tile above its ports (the
relaxed cost is shortest there). The hand layout leaves eight tiles of trunk.

## Open

- The pair's stem (grove): a pair-aware terminal (the stem of four belts the side-load needs,
  from `lanephys`) or a per-net minimum length for pairs. Lane physics belongs to the lanes
  branch (`claude/40-lanes`); the layout should read it from there, not hard-code 4.
- The lab bays' generators (`lab-session\baygen.py`) are untried as users of `fk layout`.
- MODULE mode has grove as its case and the spec-level `ports stay` test; no example in the
  docs beyond the one line in chapter 9.
- The Python reference is ~60x slower than the kernel on the mall (a field per candidate per
  incident net); it is the reference, not the tool, and FK_NATIVE=0 still works.
- The weight is `ceil(rate / one yellow belt)`, at least 1; every mall net weighs 1.
- A Stack with a turned module inside, or a module whose frame does not start at its origin, is
  skipped with a note; a Literal and an `@patch` row are never moved.
