# Toolkit 2.1 m2m: the many-to-many router, baseline (`route --m2m`)

The design is `assessment-20261031\DESIGN-M2M.md`. This builds its releases 1 and 2: the hourglass
bench, the `MAXFLOW` line, and the baseline router (the hub without side-loads, then augmenting
runs). Rory's principle: there is no trunk rule and no pinch point. The constraints are lane reach
(every producer reaches every consumer), capacity (a max-flow, one lane a run) and the ground. The
objective is belt cost. The one-belt waist comes out on its own when the flow fits a lane.

Nothing changes without the option. The golden check: the 54 designs of 2.1.12 are identical
(`tools/golden.py compare ..\21-golden\out\golden\2.1.12 out\golden\m2m`: 54 of 54; the six
examples added since 2.1.12 are only in the new snapshot).

## What it does

`route --m2m` (flow's `s_route`, like `--ug`; `route.route_layout(..., m2m=True)`) lays a net here
when it has two or more drivers and two or more consumers, and either its flow is above one lane
or its `width` is above 2. Every other net routes as before. The net is not a lane pair, a pinned
lane or a fluid.

1. **The hub, without side-loads.** Every driver merges into a trunk, at splitters and inserter
   drops, and the trunk splits to every consumer, as the hub has always done. Above one lane the
   net is no longer put on both lanes by a side-load. A driver's inserter stands on the belt's
   right, looking downstream, so it drops on the left lane (`m2m.LeftTap`). A driver that makes
   more than a long-handed inserter moves (1.2/s) gets a fast one. If no hub routes with left-lane
   taps, the hub's own taps are kept, and the line says so.
2. **Measure.** `fkcore.maxflow` gives the max-flow over the net's runs and splitters, one lane a
   run, against the demand. It also gives the two sides of the cut where the flow binds.
3. **Augment** while the flow falls short. One A* (steiner's own step) searches from every start
   at once to every target at once:
   - a start is a straight belt upstream of the cut, which becomes a splitter and the run leaves
     from its spare half; or a driver with items to spare, which gets a new inserter on the run's
     right;
   - a target is a straight belt downstream of the cut, which becomes a merge splitter and the run
     feeds its spare half; or a consumer that can take more, which gets a new inserter off the run.

   A run is kept only when the max-flow rises. Adding runs never removes a path, so reach holds.
4. **Improve.** Each added run that no other run splits or merges on is ripped up. Then it is
   searched again, or dropped when the rest meets the demand without it, while that lowers the
   cost and keeps the flow.

There is no grouping rule. Which drivers share a run comes out of the search.

**`width` above 2** on an ordinary net is a minimum lane count under `--m2m`, not a ribbon. The
router adds runs until the carriers alone pass that many lanes. `net each` and `bundle` stay
ribbons. Without `--m2m` a wide net is a ribbon, as before.

**The `MAXFLOW` line**, one per m2m net in `out\route.txt`:

```
MAXFLOW   plates: 22.4 of 22.4/s, the narrowest cut 3 lanes
```

When the net falls short, the line adds the shortfall and the carriers at the cut. The route step
then gives a `maxflow` check with the same reason. The net's `routed` line ends with
`m2m: 7 runs added, max-flow 7.5 -> 22.4 of 22.4/s`.

## The hourglass bench

`python tools/hourglass.py [--today] [--draw] [--lines] [--only CASE]` generates each case offline.
There is a column of producers (requester chests at a rate, x=0, every 2 tiles) and a column of
consumers (provider chests at a rate, x=20). One net runs from every producer to every consumer.
Each case prints one row:

- the demand, and the max-flow of what was laid, one lane a run;
- reach: `connect`'s verdict, every producer to every consumer, with no SPILL;
- the waist: the runs crossing the line midway between the columns; `narrow` is the fewest runs
  across any line of the gap;
- belts, underground ends, splitters and inserters;
- the runs added, the belt cost (steiner's costs) and the route time.

`--today` adds the router without `--m2m`, its max-flow counted on both lanes. `--draw` draws each
case as text. The baseline, on the laptop:

```
case    router    P->C  demand  maxflow  reach  waist  narrow  belts  ug  splitters  inserters  runs   cost  secs
------  ------  ------  ------  -------  -----  -----  ------  -----  --  ---------  ---------  ----  -----  ----
8to8    m2m       8->8     6.4      6.4    yes      1       1     43   0          2         16     0   81.0   0.2
8to8    today     8->8     6.4      6.4    yes      1       1     43   0          2         16     0   81.0   0.1
16to16  m2m     16->16    22.4     22.4    yes      3       3    119   0         17         33     7  236.0   3.0
16to16  today   16->16    22.4     15.0    yes      1       1     78   0          1         32     0  145.0   0.5
16to4   m2m      16->4     8.8      8.8    yes      2       2     82   2          5         20     1  143.0   0.4
16to4   today    16->4     8.8      8.8    yes      1       1     68   4          1         20     0  123.0   0.3
4to16   m2m      4->16     8.8      8.8    yes      2       2     76   2          5         20     2  137.0   0.4
4to16   today    4->16     8.8      8.8    yes      2       2     89   2          1         20     0  138.0   0.3
uneven  m2m       8->8     9.2      9.2    yes      2       2     64   0          4         16     1  108.0   1.2
uneven  today     8->8     9.2      9.2    yes      1       1     61   0          1         16     0   96.0   0.2
wall    m2m     12->12    12.0     12.0    yes      2       2     68   4          4         24     1  140.0   0.6
wall    today   12->12    12.0     12.0    yes      1       1     62   0          1         24     0  113.0   0.2
```

The cases: 8 to 8 at 6.4/s (under a lane), 16 to 16 at 22.4/s (three lanes), 16 to 4 and 4 to 16
at 8.8/s, uneven rates (2.4 down to 0.4/s, 9.2/s in all), and 12 to 12 at 12/s with a wall three
tiles thick across the gap and one free tile in it.

- **The waist is the flow in lanes, rounded up**, in every case: 1, 3, 2, 2, 2, 2. The hourglass
  comes out. Merges narrow from the producer column to the runs that cross, and splits widen out
  to the consumers. Where the flow fits a lane, the waist is the one-belt trunk, and the net lays
  exactly as today.
- **16 to 16** is the case today's router can't carry. One belt on both lanes gives 15 of
  22.4/s; the baseline meets it with three runs across. It pays for it with 17 splitters (cost
  236 against 145). The augmenting runs pile up near the producer column, where the cut keeps
  moving as runs are added.
- **The wall**: both runs go under it, 5-tile tunnels, rather than through the one-tile gap. A
  tunnel is cheaper than the detour at steiner's costs.
- **Lopsided, uneven and the wall**: one or two runs added. 16 to 4, uneven and the wall cost
  12-24% more than today's trunk on both lanes; 4 to 16 costs the same. That is the price of
  the left lane only.

## What is not in it

- **Side-loads, both lanes and lane balancing** (version 1 is left lane only). Below two lanes
  the baseline needs two runs where today's side-loaded trunk needs one.
- **The even split of a splitter.** A real network can carry less than its max-flow, because a
  splitter divides evenly. The lab measures that gap; it is the next release.
- **The balancer comparison** (a standard 2x2, 4x4 or 8x8 module dropped at the waist) is not
  built.
- **Belt ends.** The router takes a driver or consumer belt end (a port) as a source or sink of
  its own rate. Only machines get new inserters, so a port with spare flow can be split from but
  not given a second run of its own.
- **Not negotiated with other nets.** Like every net, an m2m net is routed one at a time, on the
  ground the nets before it left.

## Code

- `fkcore/maxflow.py`: `solve(ents, cat, supply, take, unbounded=False)` returns a `Flow` with
  `value`, `demand`, `cut`, `S`, `T`, `lanes` and `met`. Also `of_net(flat, lay, cat, net)` and
  `rates_of(flat, net)`.
- `fkcore/m2m.py`: `route` (the hub, augment, improve), `spec_of` (each end's rate), `report` (the
  `MAXFLOW` line) and `LeftTap`.
- `fkcore/route.py`:
  - `route_layout(..., m2m=False)`;
  - `NetJob.m2m`, `_mark_m2m`, `Routed.maxflow`;
  - `_grow`, `_hub_trees` and `_hub_search` take `tap=` (the driver sink kind; default
    `TapSink`, as before).
- `fkcore/flow.py`: `route --m2m`, and a `maxflow` check for a net that falls short.
- `tools/hourglass.py`: the bench.
- Tests: `tests/test_m2m.py` checks:
  - reach on every case, max-flow meets demand, the 8 to 8 waist of 1, and the 16 to 16 waist of 3;
  - left-lane drops, the `MAXFLOW` line, and the table;
  - nothing changes without `--m2m`, and one lane lays as today;
  - `width 4` gives four lanes, not a ribbon;
  - the max-flow on hand-laid belts, and the cut when short.
