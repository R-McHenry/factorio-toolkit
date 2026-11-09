# 43-hierarchy: the reroute leftovers, the two check lines, the examples (PLAN-ORGANIC D2 open items, D3, D4, R3's text)

Branch `claude/43-hierarchy`, cut from main `90e20a0` (3.1.4 + wave 1). Measured 2026-11-09 on
this laptop with main's `fkroute.pyd`; the designers' games read from copies (`tools/buildbench.py`
copies fen's `lab-session\megabelt\work\fen\game` itself; ridge's copied to the session scratch).
Nothing under `lab-session\` was written.

## What landed

### D2. The no-op route step (fen 18.9 s -> 4.2 s)

Measured first, as the brief asked, with `buildbench --from route` on fen's copy: the first build
of a copy re-keys its fluid columns (76.8 s, the 3.1.5 pass-through rule keys them anew once); the
second is the no-op. `--top N` (new) prints more than six frames, which is where the time hid:

| fen no-op route step | seconds | summary | where (stack samples of 194) |
|---|---|---|---|
| before (main 90e20a0) | 18.9 (20.5 under the deeper sampler) | `1 routed, 362 kept, 191 pass-through (362 pinned, 1 laid from the compiled store)` | `connect.graph` 109: `_port_joints` 105, of them `_fluid_port_joints` 58 (`facing` 32, `_box_key` 39); `connect.connect` 59; `_standing` 28; the fluid `Pass` built for the one net's judge 28 (`_world` 28); `_repair`'s judge of that one net 31; `design.read_all` 36 |
| after, first build (keys `rx` anew, 1 stored) | 5.7 | `0 routed, 362 kept, 192 pass-through (362 pinned)` | |
| after, no-op | **4.2** | `0 routed, 362 kept, 192 pass-through (362 pinned)` | `design.read_all` 15 of 40, `route_layout` 16, `seal_checks` 4, `connect.graph` 3 |

Three pieces, each measured on the profile above:

1. **A fluid direct join is a pass-through** (`fluid_route._direct`, called beside `_abut` in the
   fluid loop of `_route_layout`): a fluid net whose endpoint boxes all join as they stand (fen's
   `rx/f5_gas3`: the LightCol's `gas_out` port onto the `Pump` Rory placed outside it; a boiler
   onto its engine) is connected and lays nothing. It was routed every build (`0 pipes, 1 direct
   join`), pinned by nothing, the one "routed" net of fen's no-op; and because it was in `lay_now`
   its unit went through the store, the fluid `Pass` was built for its judge (a whole-layout
   connect graph) and `_repair` judged it (another). The line now reads `routed rx/f5_gas3: 1 -> 1,
   nothing to lay (its boxes join directly)`. A net of port ends alone stays `_abut`'s; a port end
   and a machine end are joined through the port's edge (`port_edges`), as the world joins them.
2. **One index for the fluid port joints** (`connect._port_joints` / `_fluid_port_joints`): every
   fluid port's edge scanned every box of the graph for the connections facing it and re-hashed
   every join into a `done` set; fen has 592 fluid ports, so each whole-layout graph cost about
   2 s in that alone, three graphs a no-op. The index of connections by (tile, target) and the
   `done` set are built once per graph and shared; a join an edge removes is discarded from both.
   Same joins, same order (`_box_key` is the same key).
3. **A net laid with no carrier is a pass-through in the summary** (`Routed.passthrough`, and
   flow's "laid from the compiled store" count leaves them out): nothing was searched or laid and
   nothing will pin it, so counting it as routed is the "it re-routed" misread.

What is left of the 4.2 s: reading the 554 net files (`design.read_all`, 1.5 s), `_standing`'s
one connect graph and report (0.3 s), seal and port checks, writing the net files. Nothing of it
is routing; the standing judge is no longer the piece to take.

The **zero-carrier connection nets** of the brief's item 2 (fen's 151 `c/a_in_N`) are the stacked
fluid cells' port-to-port nets: they were already pass-throughs after 3.1.5's `_abut` rule (fen's
no-op before this branch: `191 pass-through`, none "laid from the store"); item 3 is the rule for
the one that was not (the direct join). The brief's "151 laid from the store" was 3.1.4's reading.

### D2. The pair's tail (`_serving_only`)

A lane pair (`A|B`) laid this build is now trimmed at lay time as a wide or pinned net is: what
serves no end of either member goes (`_pair`, `_serving_only` over `fkpmod.net_names`, the three
call sites in `_route_layout`'s lay paths), the rule `_standing` judges a committed pair by. A lane
pin's stub stays, as everywhere.

Measured on ridge's copy, the pair `rx/steelE|rx/bka` routed fresh (its store entry removed, the
net unrouted, built, built again):

| tree | laid | first rebuild |
|---|---|---|
| main 90e20a0 | 289 carriers (`rx/steelE: 57 belts, 2 underground ends, 3 merges; rx/bka: 85 belts ...`) | `0 routed, 739 kept`: 289 kept |
| this branch | 289 carriers, the same line | `0 routed, 739 kept`: 289 kept |

The judge's trim of notes-42 (298 -> 289 on cfb10f0) does not reproduce on 90e20a0: the stub rule
of 3.1.5 (stubs are not idle) was what trimmed it. The lay-time trim stands as the rule and trimmed
nothing here; a pair that does carry a tail is now trimmed once, when laid, not on the rebuild.

No ROUTER bump: no stored route is laid differently. A unit that holds a direct-join fluid net
keys anew once (its `nets` part no longer lists the net: fen's `rx` stored 1 entry on the first
build after, none on the next), as 3.1.5's abutting nets did.

### D3. The two check lines

- **`no-pole-spot`** (`cover.cover_power_units`, `_why_not`): an entity of a sealed unit that no
  free tile inside the unit's frame can hold a pole for. `_why_not` takes the unit's frame (it read
  `lay.size`, None for a unit's sub-layout: the FRICTION 11-08 traceback) and says `N outside the
  13x3 frame at 40,12`; the unit's uncovered entities become one line each on the step's report,
  a twin unit's included (the twin carries its dark entities by relative position). The last pass
  may still power it from outside; the line says the cell does not:
  `no-pole-spot c0/b: no free tile inside c0's 3x3 frame at 0,0 holds a medium-electric-pole that
  powers it (all 25 spots a medium-electric-pole could power it from are taken: 1 on entities (c0);
  24 outside the 3x3 frame at 0,0); a sealed module powers its own frame: move it into the parent,
  or leave a tile free beside it`.
- **`port-not-in-line`** (`elaborate._port_checks`, now given `cat`; `_stem_blockers`,
  `_child_tiles`): a pinned pair port (`a | b`, not `X | X`) whose straight run of `lanephys.STEM`
  tiles inward from the port tile something of the module stands in. The children's footprints
  come from their hints and own frames turned as `expand._module_frame` turns them; the run ends
  at the frame's edge or at a child's pinned port tile (a Stack's cells' included: the column it
  feeds stands in line), and a child's other tile in it is named:
  `port-not-in-line port blue/0/t_in: @s11 (sulfur | chemical-science-pack): a pair's belt runs
  straight for 3 tiles inside the frame from its port, and 11,2 (pole) stands in that line; put
  the port in line with the column it feeds`. The number is read from `lanephys.STEM` (3), never
  written. On the examples it fires on blue6.fk alone (4 lines, the pinned pole in the stacked
  pair's line: the chapter's aside says so now); on fen's and ridge's world designs: see the
  table below.

Both warn, never gate (`Check` lines on the step's report; the elaborator's `flat.checks`).

### D4 and R3. The examples

- **EXAMPLES.md chapter 11**: the route quote is the build's (`85 routed, 0 kept, 33 pass-through`;
  it quoted 3.1.4's `118 routed`), a paragraph on what a pass-through is, and the two-round story
  measured on `red-chain.fk`: `p1 = Plas2 @(0, 1)` inside `PlasPair`, then
  `compiled chain/pl: not in the store; PlasPair's last entry (faca6bf7) differs in instances, net
  coal_/goals, net gas/reserved, net plastic_a_/starts, standing`, `chain/pl/p1: 3 nets laid from
  the store`, `6 routed, 79 kept, 33 pass-through (83 pinned, 3 laid from the compiled store),
  0 failed`, the build clean (127 connected). The paragraph also says what a move that breaks a
  route looks like (`p2 = Plas2 @(13, 0)`: PlasPair's own `no-route`) and what moving the whole
  module reads (`80 routed, 0 kept, 5 patched, 33 pass-through (80 pinned, 79 laid from the
  compiled store)`). The "what goes wrong" paragraph names `no-pole-spot` and `port-not-in-line`.
- **The layout chapter** (chapter 9, `layout.fk`): "Two rounds", with the round-2 report quoted
  from a run (`11 instances, 0 placed now, 11 kept`, `per net, real -> estimated: ...`, `real belts
  40 -> estimated 4 over 8 nets`) and the second build (`0 routed, 7 kept, 1 patched`, 51 belt
  pieces, `90 entities, 86 edges`). The numbers of notes-41-price held exactly when rebuilt.
- `tests/test_examples_docs.py::TwoRoundsTest` runs both stories (red-chain built, edited, built
  again; the mall stripped, laid out, built, `--from out`, built) and keeps every quoted line.

Nine inside-changes of red-chain were tried before `p1 @(0, 1)`; the table is worth keeping, it
is the warning's claim in numbers (every failure is the changed module's own):

| change | result |
|---|---|
| `Plas2`'s `b2` beacon one tile down | `0 routed, 85 kept`; `stored chain, chain/pl, chain/pl/p1` (the routes still fit: nothing laid) |
| `p2 @(13, 0)` / `@(12, 1)` / `@(11, 0)` | `chain/pl` routes 4, p2 from the store (or keyed anew), 1 to 2 of PlasPair's nets fail: no column left for `plastic_b_` |
| `p1 @(0, 1)` | clean: the story above |
| `p1 @(0, 2)` | 1 failed (PlasPair's) |
| `m1` turned `rot 1` in `Plas2` | both Plas2 miss the store, 2 open (Plas2's gas) |
| `ga @(20, 21)`, `cur @(40, 26)` in `RedMod` | `chain` misses the store (`differs in catalog, instances, ...`), 2 failed (RedMod's), the stop fires |
| `red2 @(12, 12)`, `red n=2` in `RedPair` | `chain/rp` reroutes, its cells from the store, 2 failed (RedPair's) |
| `chain = RedMod @(3, 4)` | clean: 79 laid from the store, 1 routed, 5 patched |

### Tools

`tools/buildbench.py --top N`: the frames printed per slow step (default 6, as before).

## Numbers for the bars

| bar | before | after |
|---|---|---|
| fen's copy no-op build reads `0 routed` | `1 routed, 362 kept, 191 pass-through (... 1 laid from the compiled store)` | `0 routed, 362 kept, 192 pass-through (362 pinned)` |
| fen's no-op route step seconds | 18.9 (20.5) | 4.2 |
| ridge's pair on the first rebuild | 289 laid, 289 kept | 289 laid, 289 kept |
| `port-not-in-line` lines on the designers' worlds (copies, `fk check world.fk`) | | fen 0, ridge 0 (blue6.fk is the one example that prints any: 4) |

## Tests

- `tests.test_flow tests.test_design tests.test_route tests.test_compiled tests.test_cover
  tests.test_route_units tests.test_fluid_ports tests.test_circuits tests.test_port_line
  tests.test_fluid_route`: 166 tests, OK (88 s).
- `tests.test_examples_docs` (every example builds and is quoted right; `TwoRoundsTest`, the two
  stories above): 7 tests, OK (37 s).
- New: `tests/test_port_line.py` (5: a chest in the stem, a free stem, `X | X` is not checked, a
  column in line, a column off the line named with its tiles), `test_cover.UnitsTest.
  test_an_entity_no_spot_inside_its_unit_powers_is_a_check_line` (the frame-filling beacon, its
  twin, no NO_POWER, the layout audited), `test_fluid_route.DirectJoinTest` (an InfinityPipe
  on a plant's connection: a pass-through, connected, no carrier), `test_examples_docs.
  TwoRoundsTest` (2).

## Decided here (within the plan; say if otherwise)

- The biggest piece of the no-op was not the standing judge but the connect graphs' fluid port
  joints and the one direct-join net that dragged the fluid world and a judge in; those were taken,
  `_standing` (0.3 s now) was left alone.
- `connect.py` is touched (the index), outside the brief's named files: the win was 6 of 20 s and
  the change is local to `_port_joints`; the joins come out identical.
- A zero-carrier net laid from the store counts as a pass-through in the summary even when no
  rule names why it laid nothing (there is no such net on the five designers' bases now; the rule
  is for the next one).
- `port-not-in-line` reads a child's *pinned* ports only; an unpinned port is chosen at layout and
  cannot be in or out of line yet. The run walks inward from the port tile, so an `in` pair's stem
  outside the module (the parent's ground) is the parent's business when it places the module.
- The ridge pair's lay-time trim trimmed nothing (the judge's trim was the stub bug, fixed in
  3.1.5); the rule stays because it is the same rule the judge applies, and a tail laid once is
  trimmed once, at lay time.

## Open

- `catalog` differs in a unit's key between two builds of the same copy when an instance inside it
  moved (`chain` after `ga` or `cur` moved; `chain/pl/p2` after p2 moved: "differs in catalog,
  standing"). `compiled.py`'s key parts are not this branch's; worth a look by whoever owns them:
  a moved twin should differ in `standing` alone.
- `design.read_all` is a third of fen's remaining 4.2 s (554 net files read one by one); the net
  files are flow's and design's, not this branch's.
- TOOLKIT.md's check list ("What is where") does not name `no-pole-spot` or `port-not-in-line`;
  chapter 11 does. BUILDING.md's "ports in line" rule says "four tiles" where `lanephys.STEM` is 3.
  Both are the docs part's files.
- The `port-not-in-line` test covers a chest, a child module in and off the line and a one-lane
  port; a Stack child's cells' ports go through the same `_child_tiles` recursion but have no test
  of their own.
- `fk check` on the designers' worlds reports the lines above; whether the designers' pairs are
  in line is their call (the brief: checks warn, never gate).

## Files touched outside the part

- `fkcore/connect.py`: `_port_joints` builds one connection index and one `done` set for every
  fluid port edge; `_fluid_port_joints` takes them (`index=None` keeps the old shape).
- `fkcore/flow.py`: the summary's "laid from the compiled store" count leaves pass-throughs out
  (`through` computed before `comp`); nothing else.
- `fkcore/elaborate.py`: `elaborate()` passes `cat` to `_port_checks` (one argument).
- `tests/test_cover.py`, `tests/test_fluid_route.py`, `tests/test_examples_docs.py`: a test each.
