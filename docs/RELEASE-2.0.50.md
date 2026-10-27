# Toolkit 2.0.50: the paired run, whoever drives it, and a world to build it in

Rory, 2026-10-27, from the 2.0.49 review: "we want the paired runs encouraged but that shouldnt also
be related to chest feeding. it would probably be better for the player to build their own lab
linear stack template." And "for the world plot, lets just make it extremely big, like -1000 to
1000." And "You can merge in template world so we are deploying all the latest with the templates
and examples."

## Part 1: `LANES` is about the nets

### What was wrong

2.0.17's `LANES` named a pair of single-item nets only when a **chest** drove both, because pairing
a machine's product with a net of its own puts that product on two nets, and the check stayed with
the network's raw feeds. But the waste is the same whoever makes the item, and the runs' lab rows
were the case it kept quiet: the last run's outpost fed its six labs red packs on one belt and green
packs on another, and the build said nothing.

### Measured on that outpost

`C:\fk-player\runs\20261025-1343-core-v1\game\outpost.fk`, offline build to `report_checks`, with
`lanes packs | greenpacks` added:

| | two belts (as built) | one paired belt |
|---|---|---|
| entities at `place` | 386 | 362 (-24: the `in2` row's 18 belts and its 6 inserters) |
| entities routed | 1379 | 1228 (**-151, -11%**) |
| nets connected | 29 of 34 | 29 of 34 |
| LEAK | 0 | 0 |
| route time | 1 min 3 s | 6 min 35 s |

The pair lays as it should: `routed packs|greenpacks: 2 -> 1, join 47,53 N (packs on the left lane,
greenpacks on the right)`. The cost is the join search - a pair job tries joins around both nets -
and because the tile budget changes, one other net falls differently (3 passes instead of 6).

### The rule now

Any pair of single-item nets into the same machines is named, whoever drives them. Left alone, and
why:

- a pair into **chests only**: two products into one provider chest are not a run's feed, and one
  belt of two products buys nothing but a mixed chest;
- a pair a **`SmelterArray` or a `CircuitStack`** feeds: they side-load two nets onto their own feed
  belts, so pairing hands the fragment one belt where it needs two (a paired SmelterArray loses its
  machines and says so in a note);
- a flow that does not fit a lane (a requester without `rate=` is unbounded), a fluid, and nets
  already paired.

The line names every row it feeds, in sorted order: 2.0.17 picked one instance out of a `frozenset`,
so a pair that fed two rows said `smelt_a` or `smelt_b` from one process to the next - and the
elaboration baseline is a hash of it.

### Lab rows

No lab stack template ships: a line of lab cells is a design of the player's own, `Stack<cell=...>`
the way `docs\examples\blue6.fk` is one. `LANGUAGE.md` says so beside `LabRow` (1 to 3 belts in, each
a pair of packs), and `LANES` now names a lab row's two pack belts like any other pair.

`busbase.fk` follows its own advice: the green row's inserters and belts share one belt
(`lanes insn | beltn`). 0 check lines, 38 nets connected, 1741 entities composed, 7 s.

## Part 2: the world design template, with 2000x2000 of ground

A new run starts from a **world design** instead of a row of `place` lines:

```
# nauvis.fk
plant = Plant @(-34, -39) size 17x16        # the nuclear plant, running from the start
world = World @(26, -1000) size 2000x2000   # your base
```

- `world.fk` is the base's own file: empty, with a header on sealed modules, ports and the nets
  between them, and on pairing a row's two feeds (`lanes A | B`).
- The plot is 2000x2000 tiles, from the kit's east side out to x 2025: the ground will not run out,
  so a layout never meets an edge.
- It starts at x 26 because the world's west side is already spoken for, and a plot may not overlap
  another plot or hold shared infrastructure: the plant's plot stands at -34,-39, its pole bridge
  runs to 5,7, and the starter kit's claim and roboport are at 2,6..25,27 and 8,8. `nauvis.fk` says
  so on the line.
- The template's records are regenerated to match (`nauvis.fkp`'s world plot line, and `world.fkp`,
  the empty plot), so the recorded surface and the design agree from the first build.
- Docs and briefs follow: `TOOLKIT.md`'s surface section is now "The surface file and the world
  design", `EXAMPLES.md` puts a factory in `world.fk` or on a plot of its own, and the three briefs
  say where the plots live and that the kit and the plant stand west of the base's edge.
- `tests/test_flow.py`'s template case builds its factory in `world.fk`: a design wins over a `place`
  line, so the line it used to append would have named a factory nothing reads.

### What the plot holds

The map's start area (the last run's `map.terrain.json`, -192..192), inside the plot:

| | tiles | amount |
|---|---|---|
| copper ore | 373 / 373 | 230,288 |
| coal | 306 / 306 | 209,820 |
| iron ore | 527 / 1203 | 268,216 of 1,326,680 |
| stone | 274 / 386 | 177,439 |
| crude oil | 0 / 3 | 0 of 900,000 |

All the copper and coal and 44% of the iron are in the base's plot; the three crude oil wells
(6..16, -10) and the rest of the iron are west of it, in the strip the plant, the bridge and the kit
own. An oil outpost there is a plot of its own - the supported pattern, one `import` and one line in
`nauvis.fk` - and the map beyond the read area is unread, so `read-terrain` grows with the base.

## Verified

- The full suite: **1006 tests, OK** (2.0.49: 1002; the four new ones are the widened `LANES`).
- The elaboration baseline is regenerated: 21 designs gain a `LANES` line and nothing else moves.
- The template builds offline to `report_checks`: 2 plots, 29 entities, no problems, and the records
  the build writes are the ones the template ships.
- `blue6`, the four-cell line and every example still route, connect and check as they did on
  2.0.49.

## Open

2.0.49's `blue6` netlist noise is unchanged: a port of two items publishes both items on both nets of
its pair, so `fk check blue6.fk` prints sushi lines the routed build does not have. Binding each
lane's net to that lane's item is 2.0.51 work.
