# 2.1.33: beacons, the lab's friction, and the 9-bay loop builds at a bay's pace

This release also carries 2.1.32, the megabase session's work, which was never committed on its
own (the two share route.py, elaborate.py and others). Entry numbers are
lab-session\fk-run\FRICTION.md's.

## 2.1.32: rails, signals and the bay grid (the megabase session)

- **Rail tiles** (29, fkcore/railtiles.py): every ground rail piece in every direction takes the
  tiles measured on the lab, not its bounding box; the router no longer lays belts on curves.
- **Turned rails and stops** (31, 32): a facing kind with no direction is north, so it turns with
  its Literal; a straight or half-diagonal rail compares its direction mod 8.
- **Rail signals** (36, 37, 40, fkcore/railsignals.py): a one-way network's signals planned from
  its rails and stops: entrance chains before each intersection, an exit signal past it, a chain
  half way along a segment two trains fit.
- **Setup work on a big grid** (33, 38): a capture parsed once per file text; port checks, the
  hold, direct claims and the store's names indexed once; size elaborates the base once. Elaborate
  20.8 s -> 4 s, size 41 s -> 3 s on gridb.
- **Turned twins** (39): a unit turned 180 degrees is keyed in its unturned frame, so a turned bay
  takes the first one's routes, turned.
- buildbench `--script` (34).

## 2.1.33

### The language

- **Beacons** (2): a placed beacon reaches a machine whose box touches its box grown by the
  beacon's supply distance (3); its bonus is effectivity 1.5 x the 1/sqrt(n) profile x its
  modules, up to the same unplaced module, turns included. `beacons=N` (and `beacon=MODULE`) sets
  it where the layout can't say. Both read from the game into facts.json (`tools/read_facts.py`).
  LANGUAGE.md has the paragraph.

### Checks

- A relay chest that only takes says it should be a `Buffer` (3).
- A port that takes one item on both lanes, fed by a one-lane net with several drivers, says
  `width 2` or `lanes A | B` (19).
- `literal-box` (30): a Literal box that cuts an entity and leaves it out, when no other Literal
  of any file keeps the same entity at the same spot.
- Captured wires across Literal cuts are laid as the capture had them (20), and a misaligned
  Literal says so (`wire-cut`).

### Build speed (35)

- **Route**: a net's search sees only its box plus 16 tiles; ends, claims, owned frames and laid
  entities sit in tile-bucket indexes. Per net 2.7 s -> 1.7, 2.6 -> 0.9, 6.5 -> 4.9; per unit:
  fits 12.2 s -> 0.21, net_frames 3.35 -> 0.15. pubay cold: 638 nets in 20.5 s, 0 failed. The
  9-bay loop (4282 nets), which routed 28+ min, now moves at a single bay's pace in 30 s probes;
  the whole loop has not been timed end to end.
- **The rate model** settles each part of its graph on its own, with its own damping and
  restarts. The loop is 9 parts; one bay swung and held all nine to 1640 passes: 18.6 s -> 4.1 s
  a solve, the same answers (util within 1.5e-11, no binding changed).
- **Passes**: a unit skips any net order it has tried (the same order on the same ground lays the
  same routes). pmbay's two nets that each block the other swung for 10 passes; now 6. pm1 cold
  route 18.7 s -> 12.0 s, the same 244 routed and 2 failed.

## Checked

- New: tests/test_beacons, test_cut_wires, test_rate_parts, test_route_cycle (and 2.1.32's
  test_rail_signals, test_rail_tiles, test_route_ground).
- Targeted modules only (Rory: not the full suite): the route and sealed-module modules, the 20
  rate-model modules (318 tests), literal, ports, buffers, lab, sense, compile_once.

## Known limits

- pmbay's `green2|redc` still fails: the two nets want the same tiles. A design gap, not the
  router's.
- FRICTION 41 (gridb's route killed for memory) is not measured yet.
