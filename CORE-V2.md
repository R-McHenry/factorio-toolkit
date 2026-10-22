# CORE-V2: lanes and throughput (draft)

The V2 core, from the brainstorm with Rory on 2026-10-20. V1 (`CORE.md`) is the base and stays true
except where this file says otherwise. Marks: **(Rory)** = his decision, **[proposed]** = mine,
waiting for his OK, **[open]** = still to settle, **[lab]** = a game fact to measure on a laptop
test server (`tools/laptop_server.py`, Factorio 2.0.77) before code relies on it.

## The versions

Releases are the only version numbers (Rory, 2026-10-21). The major is the design generation:
1.x was the V1 core (the last, 1.7, shipped the round's first pieces), and the round that
completes V2 ships as 2.0: lanes (a net is one lane, so two nets can share a belt), throughput,
side-loading smelter arrays, circuits and inserter limits in the source, and the lead and worker
player harness. Buses (thick buses, the main bus, multi-lane nets) are a core feature of their
own: release 2.1; what of them already landed stays (the Bus template of 1.6). A feature goes by
its name until a release ships it, and each release note says which named features it delivers.
The repo name `v5`, the deploy folders `fk-v5-<sha>` and the `.fkp` format version are not
release numbers.

| release | a net is | the router | the model |
|---|---|---|---|
| 1.x (V1) | connected or not; one net per belt, both lanes | trees of belts, splitters and undergrounds; no side-loads | nominal, no capacity |
| 2.0 (V2) | one lane (half a belt), so a belt holds up to two nets; a two-sided MinerRow's ore takes both | as V1, lane-aware; tier per connector; side-loads only where two nets join to share a belt; two nets that share a belt somewhere share it everywhere | the flow solver: flow, load, starved and blocked machines, routed rates |
| side-load-aware routing (a name, no release yet) | as 2.0 | knows side-loads: 2-to-1 merges, and lane separation (a splitter, then an underground side-load per net) | as 2.0 |
| 2.1: buses | k lanes in one step (2, 3, ...): thick buses and the main bus | lays k-lane nets, through the bus templates | as 2.0 |

Multi-lane nets go from one lane straight to k lanes, not "a full belt, then several" (Rory). It
is unconventional: an agent may plan a bus of 5 iron lanes and 3 copper lanes, where a person
never plans odd lane counts. [open, 2.1: steer to whole belts, or let it be]

**Multi-lane nets (2.1, buses) next, and how (Rory, 2026-10-20):** go straight to multi-lane
nets, but do not route them with the general router. Two ways to support them:

1. **A bus router**: lays a net as a parallel bus of k belts, with undergrounds and splitters
   where needed, as one unit.
2. **Main-bus templates with single-belt inputs and outputs** (simpler, more versatile, more
   future-proof): a balancer, a bus run, a tap that takes one belt off the bus, a merge onto it.
   The router keeps laying single-belt nets between template ends; the templates make the thick
   part. Rory's 4-to-4 balancer (`games/v2-bench`) is the first one, and it is already measured
   (throughput-unlimited in 7 setups).

**Proper distribution (Rory, 2026-10-20):** in a k-to-m hub every input should reach every
output through a splitter network (a balancer), so each driver feeds each consumer evenly. Today
the hub is a merge tree into one trunk and a split tree out of it: the last driver to join gets
half the trunk, the others a quarter each (Rory's join case, below), and every consumer draws the
mix the trunk happens to carry. A k-to-m balancer in place of the trunk fixes both, and is where
the bus templates and the hub meet.

**The bus** [built, 2026-10-21: `Bus<belts, length, item, load=, tap=>`, `fkcore/fragments.py`
`bus`, `tests/test_bus.py`]: Rory's 4-belt bus demo (`agent/docs/examples/bus4.json`, read from
the lead world) as the first main-bus template, the second way above. At his parameters the
template lays his demo's bus entity for entity, splitter priorities included. A net goes through a
bus instance by naming its **ports**: each load and tap is an endpoint (`net iron1: smelt ->
bus.load1`, `net fe: bus.tap1 -> gears`) whose role is one belt beside the bus with one attach
point, so the general router lays single-belt nets to and from it and never the bus; its frame is
no ground of its own for the router (its belts and splitters are entities), so a net crosses a
4-belt bus by a yellow underground between its two outer rows. The bus is a net of its own, named
as the instance: its loads drive it, its taps consume it, its belts and splitters carry it.
`connect` reads a port as a **joint** (a consumer of one net and a driver of the next: no LEAK),
and the bus's net is OPEN where a load sits after a tap. V1's rate model solves every net through
a bus as one pool (what the loads bring, the taps share); V2 sees the bus as laid: its lanes (a
yellow belt 15/s, 7.5 a lane) and its splitters' priorities (the lane graph ranks a preferred
input first and fills a preferred output first; the required flows, without capacities, split
evenly, so a staircase's far belt doesn't read as binding while the others stand empty), and
`CAPACITY` names the victims beyond the bus.

[open, for 2.1: which bus templates come next (the balancer); whether the bus router is needed
now the bus template exists; a balancer per k-to-m hub, and which sizes; several items on one bus
(today a second item is a second bus beside it); the lab: the staircases' priorities as measured
in the game (the solver has the game's documented behaviour, not a measurement yet)]

## Words

- **lane** (Rory): one side of a belt, L or R looking downstream (the game's transport lines 1 and
  2). It carries half the tier's belt rate: yellow 7.5/s, red 15, blue 22.5, turbo 30.
- **width**: the lanes a net takes. 2.0: 1, and 2 for a two-sided MinerRow. 2.1: any.
- **tier**: transport, fast, express, turbo (belts, undergrounds and splitters alike).
- **connector** (Rory): one lane of one carrier (a belt, an underground, a splitter half), or one
  inserter, side-load joint or pump. The report groups a run of connectors that carry the same flow.
- **capacity**: the most a connector can carry, in items/s.
- **flow**: what the flow solver says a connector carries. **required**: what it would carry with
  no capacities anywhere.
- **load** = flow / capacity, at most 1. **required ratio** = required / capacity; a net's required
  ratio is the largest over its connectors (Rory), at its **critical connector**.
- **binds**: a connector binds when it runs at capacity while a consumer below it is starved; a
  machine binds when its speed, duty, inputs or outputs do.
- **starved** consumer: it gets less than its demand. **blocked** driver: its output backs up.

## Lane physics

Every row was measured on 2026-10-20 on a laptop test server (2.0.77, `tools/lab_lanes.py`;
the numbers in `docs/LAB-LANES-20261020.md`), and every rule Rory gave holds.

| where | what happens to the lanes |
|---|---|
| straight belt, turn, underground pair, splitter | every item keeps its lane |
| a belt into the side of a belt (side-load) | a 2-to-1 merge: both incoming lanes go onto the target's near lane (Rory). It is the smelter stack's side-loader. A belt fed from one side with nothing behind it is a turn instead (V1's `curve`), and keeps its lanes |
| a belt into the side of an underground, either end | the incoming lane on the open side goes through, onto the near lane; the lane on the closed side is blocked (Rory). With a splitter ahead of it, this is the only way to split two nets off one belt |
| inserter drop | a belt across the inserter's line: the far lane (an inserter on the belt's right fills the left lane, and the other way round). A belt along the inserter's line: always the right lane, whichever way the inserter faces (Rory; Factorio 2.0, a later version may let you pick). The same onto a turn, a splitter half and either underground end: an exit takes drops from every side, which V1's judge denies (v4's B-120) |
| inserter pickup | both lanes. An inserter has one lane: from a belt with two nets it merges them, unless it is filtered or its target takes only one net's items (Rory). Measured: into a chest it takes both; into a furnace both its ore and its fuel; into an assembler on gears only the iron. Every inserter has 5 filter slots in 2.0.77 |
| drill drop | the near lane (the drop point is 0.3 tiles past the drill's front edge) |
| pipes | 2.0 pipes are one tank per segment: no lanes, and no throughput worth modeling (Rory). A pump and an offshore pump move 1200/s (measured); a machine's fluid port is the other limit [lab: not measured yet] |

## Nets, carriers and the record

- A lane or an inserter can carry several nets, as long as they all go to the same sink (Rory):
  one inserter feeding a furnace ore from one lane and coal from the other carries two nets into
  one furnace. The nets on a lane share its capacity. Most lanes carry one net, so a belt mostly
  holds one or two.
- Lanes are layout, never source: the `.fk` names no lane. A template sets lanes by its own
  geometry and enforces them at its inputs (Rory); the router records the lane its net's items
  are on. [built, 2.0] The source says only which two nets share a belt, `lanes A | B` (A on the
  left lane, B on the right: Rory, 2026-10-21, "a net is one lane, so two nets can share a
  belt"), and the router lays them so (`fkcore/pairs.py`, below). `SmelterArray`, Rory's stack,
  sets its own feed belts' lanes; no other template has lanes of its own yet.
- The two-sided MinerRow stays: it is the 99.9% template (Rory). [proposed] Its ore is one net on
  both lanes, north drills on L, south drills on R.
- `.fkp` [built, 2.0: `fkcore/fkp.py` `net_names`, `net_lanes`]: a belt, underground or splitter
  line carries `net=iron|coal` (L|R), `net=iron|` (L only) or `net=|coal`, and `net=ore+fuel|`
  for two nets on one lane. A V1 `net=iron` means both lanes, so every V1 layout stays valid and
  nothing in the world changes until a design uses lanes. Inserters, pipes and pumps keep their
  `net=` (`+` for several: a shared belt's inserters are `ore+fuel`). A pair's route is owned
  `~ore|fuel` (its nets' own parts `~ore|fuel/l*` and `/r*`), so the three parts are pinned or
  routed again together. `connect` reads a carrier's nets from it: `ore` side-loaded onto
  `ore|fuel` is no LEAK, `ore|fuel` into a belt of `ore` leaks the fuel.
- Checks [built, 2.0: `fkcore/routed.py` `lane_checks`, in the routed rates]: `LANE` when the
  design asks a lane to carry an item none of its nets carries (a pair's lanes swapped), nets
  share a lane without going to the same sinks, or a net's items reach the closed side of a
  side-loaded underground (`LaneGraph.closed`: they stop there). `UG_SIDELOAD` went from
  `connect`: a side-loaded underground is a valid connection for the open-side lane and a blocked
  one for the other (Rory), which the lane graph says and V1's graph can't. `SHARED_BELT`, the
  lane-pair belt check of an earlier spec that was never built, goes: V2 lanes supersede that
  spec.
- `WRONG_LANE` goes (Rory): an item gets no leniency for being on the right belt in the wrong net.
  An item on a lane whose nets don't carry it is `WRONG_ITEM`, per lane [built, 2.0:
  `fkcore/sense.py` reads each lane of a belt whose `net=` has lanes; others as before].

## The router in 2.0 (Rory)

- No side-loads. It lays none today: the routed redgreen layout has 665 belt, 77 turn and 13
  underground edges, and not one side-load. [2.0: one place, a pair's join, below.]
- Two nets that share a belt on one connector share it on every connector: the router lays them as
  one pair. [built, 2.0: `fkcore/pairs.py`, `tests/test_lanes_pairs.py`] `lanes A | B` makes
  them one job, `A|B`, laid in three parts: A from its drivers to the tile left of a join H, B to
  the tile right of it, both side-loaded into H's sides (a belt fed from both sides with nothing
  behind it takes both as 2-to-1 merges: all of A onto H's left lane, all of B onto its right,
  as at the head of each of Rory's stack columns), then one route of both lanes from H to every
  consumer on either net (belts, turns, undergrounds and splitters keep the lanes). The joins are
  ranked by walking distance (A's drivers to H's left, B's to its right, ahead of H to the
  consumers) and the first where all three parts route is laid. Every consumer on either net
  gets the one belt of both (`fkcore.expand.belts`): a SmelterRow fed ore and coal by a pair
  has one input belt, its fast inserters picking both lanes.
- Otherwise one net per routed belt, on one lane. The templates own the lane joins at their inputs.
- The tier is chosen per connector, from the model, with flags: only yellow; at most N red belts;
  minimize (the slowest tier that carries the flow) or maximize (the fastest available). [built:
  the `tier` step after `route`, below]
- No direct insertion where a net's flow is above a threshold: a lane, or what the lab finds.
  Inserters bind early.
- Side-load-aware routing (a later feature, no release yet): side-loads as merges (the smelter
  stack's side-loader) and lane separation (a splitter, then each branch side-loads an underground
  that passes only its own net).

## Flow [built, first slice: `fkcore/lanes.py`, `fkcore/throughput.py`, `tests/test_throughput.py`]

The flow model works per net on the **lane graph** of a layout: one node per connector (each lane
of each belt, underground and splitter half, each inserter, each pump), and the machines at the
ends. An edge is one way items move, by the lane physics above. Every connector i has a capacity
c_i: a lane its tier's lane rate, an inserter its rate (below), a pump 1200/s, a pipe none.

The rate model gives each driver d a supply s_d and each consumer k a demand r_k (items/s,
nominal). The solver finds the flow f_i on every connector that the game would settle to:

1. **Bounds.** 0 <= f_i <= c_i. A driver puts out at most s_d; a consumer takes at most r_k.
2. **Conservation.** In steady state a connector stores nothing: what enters it leaves it, onward
   or into the inserters that pick from it.
3. **Belt order.** First come, first served along a lane: the inserters that pick from it are served
   in belt order, each taking min(what is left, its demand, its rate).
4. **Splitters** split each lane evenly between their outputs; when one output can't take its half,
   the other takes the rest. When both outputs are full, they take evenly from the two inputs.
5. **Merges.** Where a lane is offered more than it carries, it serves its inputs by rank: what
   already flows on it from behind first, then side-loaded lanes in the order they enter it (the one
   entering further upstream first: measured, 14 to 2), then drops; evenly within a rank (a
   splitter's two inputs, an inserter's two lanes).
6. **Back-pressure.** What a connector is offered but can't pass backs up: everything above it
   carries less, a splitter above it sends more to its other output, and a driver whose output
   backs up slows down.

**The solver** (Rory): start from an even split along the topology (every splitter halves, every
consumer asks its demand, no capacities), then repeat until the flows stop changing:

- backward, from the consumers up: each connector's acceptance a_i = min(c_i, what its own
  inserters want + the acceptance of what it feeds); a consumer accepts its demand;
- forward, from the drivers down in topological order: each connector passes min(its inflow, a_i),
  serving the inserters that pick from it first, then splitting among its outputs evenly but never
  above an output's acceptance (water-filling); a merge admits its inputs by rank up to its
  acceptance;
- what an input offered but was not admitted lowers its acceptance for the next round, so the
  splitter above it sends that part the other way.

Flows only fall toward what the capacities admit, so it settles; a cap on rounds covers a ring of
belts.

**What it reports**, once it settles:

- per connector: flow, capacity, load; whether it binds.
- per consumer: delivered / demand. Below 1 it is starved, and belt order says which ones: the
  last ones along the lane.
- per driver: delivered / supply. Below 1 it is blocked: its output backs up and it slows.
- per net: delivered / min(supply, demand), its binding connectors, and its required ratio (from
  the first pass, with no capacities): how much faster its critical connector would have to be.
- for the whole factory: the same over every net.

**Machines.** The solver couples items through machines (a furnace takes ore and coal and makes
plates) the way V1's rate model couples nets: each side of a machine is judged against the other
side's potential (it asks for inputs as fast as its outputs let it run and offers products as fast
as its inputs let it run), from everything at full speed until both hold. Belt order also closes
V1's known gap: V1 shares a short net by appetite, while the game serves the first machines along
the belt (agent `TOOLKIT.md`).

How it settles (1.4.1, after the lead's review of 1.4: on the 2005 run's base the coupling used
all 40 rounds and the answer moved with the round cap). Each endpoint of a machine has a grant. An
endpoint short of what it asked is granted what it got; one served in full is granted what it
asked and a margin more, so the machine tries a little faster the next round (an all-or-nothing
jump to 1 swung between "unlimited" and the real supply). The margin halves each time the endpoint
turns from served to short or back; each grant moves by its own step, halved each time it turns
and grown again (x1.2) while it keeps its way. The base settles in 47 rounds (cap 80), and any
step and margin factors tried give the same utilizations within 0.0003. Two bugs went with it: a
machine node got item shares of its capacity (its input and output both cross it) and infinite
capacity times a share of 0 is NaN, which stopped a cable maker's copper every few rounds; and a
requester chest was a machine whose items a recipe tied, so a chest of three parts and the engine
assembler it feeds held each other down to nothing. A requester is now a source per item. The
report says "the machines settled in N rounds", or that they did NOT and the routed rates are
approximate; "limited by" names the endpoints whose grant holds the machine.

**The netlist on its layout** [built: `fkcore/routed.py`, `tests/test_routed.py`]. Every netlist
machine the layout holds goes on the lane graph: a crafter or drill as a `Machine` (needs and
products times its duty, or its nominal utilization where V1 has it bound by a fluid; fluids left
out, pipes being tanks), a requester chest as a source at its rate (without one, unbounded: the
carriers decide), a sink as a demand for the items of the nets feeding it (its rate split over
them, or without end). `report_rates` runs again after `route` in the default flow (Rory): the
nominal model as before, then the routed section (per instance the nominal and routed
utilization and the lowest machine, per net and item what its consumers asked and got and its
critical connector), and the routed rate of each surface target; its checks are only the new ones
(the nominal `ASSERT` and `TARGET` lines are the first run's), and its report follows the first
run's in `out/report_rates.txt`. The inserter hand sizes are the force's (`--hand auto`, the
default): read over the game link, else as the last `diff` saved them (`out/force.json`; the agent
kit designs on the laptop, without a link), else 1; `--hand N` / `--bulk-hand N` set them.

**`CAPACITY`** (a warning): one line per net and kind of connector (a belt tier's lanes, an
inserter type) that binds, when a consumer runs short of the net's item: a machine the item holds
below its nominal utilization, a sink with a rate that gets less than it asks, or the labs and
turrets together. The line says what is required there, what the connector carries, the ratio,
the connectors, what the net delivers to its consumers against nominal and who runs short. A
machine held by something else (another input, its output backing up) asks less and is no victim;
an overflow chest (a chest without a rate on a net where something else takes the item too) takes
what is left, so nothing is required of the carriers into it and it is never short (1.4.1: the
inserter into a provider chest beside a cable maker was named binding for the net's whole
surplus). A connector that binds while another machine takes up the slack (belt order) costs
nothing and gives no line: redgreen's circuit row has a long-handed cable inserter at 1.2/s binding one assembler,
the other makes up for it, and the build has no `CAPACITY` line. Four green-circuit assemblers fed
from one requester chest get two: the chest's one fast inserter (2.5 cables/s of 12 required) and
the assemblers' long-handed ones (1.2 of 3).

**Several items on one lane** share its capacity: where they meet, by the rank of their inputs
(within what the lane can pass on), and down the lane in the shares they met with. A tighter spot
further down cuts them in those shares, where the game would hold back the later one first: a
limit of this first version, until a joint solve of all items. [settled for 2.0] 2.0's designs
put one item on a lane: a pair is two nets, one a lane; Rory's stack's feed belts carry ore on
one lane and coal on the other; a row drops one product on one lane. Several items meet only in
an inserter that takes from both lanes, whose capacity the shares split (the stack's inserters,
ore and coal into one furnace: the solver's plates match the lab's within 2%), and on a sushi
net's lane, where `CLOG` already warns. So the joint solve waits for a design that needs it (a
sushi lane run near its capacity).

**Later: Rory's "giga brain option".** The full matrix of driver-to-consumer paths, with a flow per
path: for nets that share lanes toward different sinks, and for the router. A linear-algebra or
max-flow formulation could solve the same physics. For now max-flow is a check: the solver never
delivers more than the max flow.

**Tier per connector** (Rory) [built: `fkcore/tiers.py`, the flow step `tier`,
`tests/test_tiers.py`]. The tiers come from what the design asks: the required flows with every
machine at V1's nominal rate (`routed.required`; with the coupled machines a lane that binds today
would throttle what feeds it and never ask for more). `tier minimize` gives each belt, underground
pair and splitter on a net the slowest allowed tier that carries its required flow, `tier maximize`
the fastest allowed on every one that carries anything, `tier yellow` only yellow; `--allow
yellow,red,...` the tiers it may use (default yellow: a bare `tier minimize` never ghosts a belt the
force can't make), `--red N` (`--blue`, `--turbo`) at most N entities gain a tier, the highest
required ratios first, the rest a tier down. Minimize and maximize never put a belt below the tier
it has unless `--downgrade` (1.4.1: a rebuild with slightly other flows turned red belts yellow
and back), and what a belt already has never counts against a budget. A tunnel's two ends change
tier together and count as two, never to a tier whose reach (`max_distance`: 5, 7, 9, 11) is
shorter than the tunnel; after that the pairing is checked as the game does it, and a pair whose
partner a change would alter (a red entrance between a yellow pair's ends) keeps its old names.
A Literal's entities keep theirs. The step runs after `route` and before the second
`report_rates`; the kickoff template has `tier minimize --allow yellow`, `games/redgreen` `tier
minimize` (no lane of it is too thin: 0 changed).

The router test case (Rory): at most X red belts on a line of Y miners into Z smelters. The flow
rises along the miners, peaks between the last miner and the first smelter, and falls along the
smelters, so the red belts go in the middle and the ends stay yellow. Measured on the solver
(18 drills, 29 furnaces): minimize turns tiles 46 to 62 red and the line carries 9/s instead of
7.5; a budget of 10 keeps one stretch around the peak (more than 7.6/s), 10 at the ends gives 7.5.
A smelter row of 26 furnaces into four chests: its output lane asks 8.12/s of yellow's 7.5;
minimize turns 11 belts red and the row runs at its nominal rate; a red budget of 5 gains nothing
(the greedy order does not yet test whether a partial stretch helps).

An example, on paper: a MinerRow of 20 drills (10 ore/s, 5 on each lane) into a row of 32 stone
furnaces that takes ore on one lane of an ore|coal belt.

| connector | required | capacity | required ratio |
|---|---|---|---|
| the miner belt, L and R | 5/s each | 7.5/s | 0.67 |
| the smelter row's head: both ore lanes side-loaded onto L | 10/s | 7.5/s | **1.33** |
| one furnace's feeder (a fast inserter) | 0.33/s | 2.5/s | 0.13 |

The solver delivers 7.5/s past the row's head: the first 24 furnaces run and the last 8 starve
(belt order), and the drills are blocked to 75%. A red input lane, a second smelter row, or
2.1's two-lane nets fix it.

## Inserters

- Rule of thumb (Rory): 60 x rotation speed x hand size items/s. Measured (2.0.77, a force with
  no research, then with bonuses): it holds chest to chest within 4% (the fast and bulk inserters
  make 2.5 a hand, not 2.4), and from a full moving belt up to hand 2 (fast at hand 3: 93%). Onto
  a moving belt it holds at hands 1 and 2, then falls off (fast at hand 3: 75%, bulk at hand 4:
  60%, onto yellow). [built: `lanes.inserter_rate`] The rate is the rule of thumb, with the
  measured factor when dropping onto a belt at hand 3 and up.
- The prototype values (rotation 0.013 burner, 0.014 inserter, 0.02 long-handed, 0.04 fast, bulk
  and stack) were read from the game; [built, 2.0] the catalog carries them (`rotation_speed`,
  `extension_speed`, `bulk`, `stack_size_bonus`, `filter_count` on the six inserters of
  `fkcore/data/catalog.json`), and the lane graph rates an inserter from its catalog row, so a
  new one in the catalog needs no table.
- The table is big (Rory): burner, inserter, long-handed, fast, bulk and stack, with the hand size
  set by research (the force's inserter and bulk bonuses), and quality later. On paper the hand is
  1; live, it is the force's. A bulk inserter's hand is 1 + the bulk bonus, a stack inserter's
  5 + it.
- An inserter is one connector with one lane: every net through it shares its rate, and they all
  go to its one target (Rory).

## The benchmark: Rory's smelter stack

Rory pasted it as ghosts on nauvis (x 86 to 109, y 108 to 117, 105 ghosts; read once, read-only,
saved as `games/v2-bench/smelter-stack-ghosts.json`): a unit 11 tiles wide that tiles east to west,
pasted twice with the start of a third. One unit (F a stone furnace, `i>` an inserter dropping
east, `U` an underground entrance and `u` an exit, `S` a splitter half, each with its flow):

```
      86 87 88 89 90 91 92 93 94 95 96
108    ^  .  F  F  .  v  .  F  F  .  ^
109    ^ i>  F  F i>  v i<  F  F i<  ^
110    ^ i>  F  F i> Uv i<  F  F i<  ^
111    ^  .  F  F  .  .  .  F  F  .  ^
112    ^  .  .  .  v  < S<  .  .  .  ^
113    ^ U< u< Sv Sv U< S< u<  .  .  ^
114    ^  <  <  <  >  >  >  >  >  >  ^
115    .  .  . S^ S^ uv  .  .  .  .  .
116    .  .  .  ^  .  v  .  .  .  .  .
117    .  .  .  ^  .  v  .  .  .  .  .
```

- Ore comes in from the south at x 89, and a splitter facing north (y 115) halves it.
- Coal runs west along y 113 through every unit, passing under the input columns by undergrounds.
  In each unit a splitter facing west (x 92) sends half of what reaches it round to a splitter
  facing south (y 113), and passes the rest west to the next unit.
- The two splitters face each other across y 114, where two belts run apart. Each gets ore
  side-loaded from the south and coal from the north, so each carries ore on one lane and coal on
  the other: 2-to-1 merges, both lanes of a splitter output onto one lane (V1's judge sees the same
  8 side-load edges in the two units).
- The west belt turns north at x 86 and the east one at x 96: the two input columns. One plain
  inserter per furnace picks both lanes into it: two nets through one inserter into one sink.
- The plates go onto the middle belt (x 91, flowing south): the west column's inserters fill its
  left lane, the east column's its right. An underground (y 110 to 115) takes it under the
  manifold and out to the south.
- The stack grows north (the ghost has 2 furnaces per column). At 24 per column a unit eats a full
  yellow belt of ore (15/s) and makes a full belt of plates, with every ore lane at exactly its
  capacity.

What V2 has to get right on it: the 2-to-1 side-loads (a required ratio of exactly 1 at 24
furnaces per column, so a 25th starves), the coal chain of splitters (an even split first, then
each unit takes its fuel and passes the rest on), the underground pass-throughs, and two nets
through one inserter.

**The template** [built, 2.0: `SmelterArray<n, recipe>`, `fkcore/fragments.py`
`smelter_array`, `tests/test_smelter_array.py`]: Rory's stack at any count, the feature
"side-loading smelter arrays". At his size (2 units, 2 furnaces per column) it is his ghost entity for
entity, but for two things: the westmost unit has no coal pass-through (his leads nowhere; the
splitter then sends all its coal to its own furnaces) and the coal comes in at the east end by
an underground of its own (his comes from the start of a third unit). A unit holds up to 24
furnaces a column, as many as a yellow lane of the recipe's ore feeds (12 steel furnaces);
`n` beyond that adds units east, the furnaces spread evenly, the extra ones west; `units=K`
sets the units. Each unit has its own ore port and plate port at its foot, the coal one port at
the east end; the ore and coal nets are two nets of the source, and the template side-loads
them onto its feed belts' lanes (`net=ore|fuel` west, `fuel|ore` east). `n=auto` sizes it like
any row. Routed from a MinerRow of 30 drills: 48 furnaces make 15 plates/s, every furnace at
1.0 and every side-load joint at a required ratio of exactly 1.00; forced to 25 a column
(`units=1, n=50`, 16 ore/s), 48 furnaces' worth runs and `CAPACITY` names the ore splitter's
lanes and the plate lanes at 7.81 of 7.5 (the shortfall settles as a column's top furnace
starved of ore and a bottom one blocked by its plate lane, half each).

Rory's second benchmark is a 4-to-4 balancer (`games/v2-bench/balancer-4x4-ghosts.json`): three
layers of two splitters flowing north, the outer belts jogging in at the middle layer and the inner
ones crossing under it by undergrounds.

Both were built on a laptop test server and measured against the solver
(`docs/LAB-LANES-20261020.md`): the balancer in 7 setups (any 3 inputs into any 3 outputs, 1 into
4, 4 into 1 ...) and the stack in 3 (2 units at 24 furnaces per column, 1 unit at 26, 3 units on
one coal inserter) all match, within 2%: the balancer is throughput-unlimited, a unit makes 15
plates/s, 26 per column still make 15, and one coal inserter (2.5/s) gives the east unit its full
1.08 coal/s and shares the rest between the other two (9.86 plates/s each solved, 9.69 measured
once settled, which takes the game about 3000 s).

## Many factories, one net (Rory's join case)

Rory: "taking a few factories that produce iron, a few that consume it, and combining them all and
merging that all with one net." A subagent tried it on paper (`games/v2-bench/join-*.fk`,
`tests/test_join.py`):

- **It is easy to write.** Each factory is a module with no chest net of its own; one top-level
  net names rows inside the modules: `net iron: a.smelt, b.smelt, c.smelt -> g.gears, p.pipes,
  s.sticks`. It elaborates with no check line but `UNLIMITED` on the consumers' chests. `fk merge`
  of six separate factories, then deleting their chest pairs and nets and adding the same line,
  gives the same netlist and the same route.
- **It routes.** The router lays it as a hub, every driver merging into one trunk that splits to
  every consumer: `routed iron: 3 -> 3, 175 belts, 2 underground ends, 2 merges, 2 splitters`,
  connected (480 of 480 pairs), no LEAK.
- **The trunk is one lane.** The rows drop their plates on one lane, and merging keeps it there:
  at 3.75/s everything arrives; at 15/s the trunk delivers 7.5, and `CAPACITY` names the trunk's
  yellow lanes and the hub's yellow splitters. `tier minimize` turns 51 belts and splitters red
  and all 15/s arrive. Beyond turbo's 30/s a lane it needs multi-lane nets (2.1).
- **The merge tree is not fair.** Two even merge splitters give the last driver half the trunk and
  the other two a quarter each, as in the game: with a thin trunk the last factory runs at 0.75
  and the others at 0.375.
- **Found on the way** (not fixed): a module instance's `rot` is ignored (`expand._origin`, a V1
  bug: it lands unturned, with no check line); a row bound to two nets for one item
  (`DOUBLE`) takes the first and the other reads `no driver role is placed`; the routed report
  adds up a consumer's item from every net it sits on; a whole-module ref as a consumer takes its
  chests too (by design, and `CLOG` says so); `chests-to-net` joins one provider to one requester
  and does not check the net's name.
- **A first-class `fk join`** could gather the drivers and consumers of the named nets wherever
  they sit in the module tree, drop the robot-link chests and their nets, write one top-level net,
  and print the joined rate against one lane of the trunk's tier. It does not have to exist yet
  (Rory).

The solver had the hub's splitters wrong until this case: it gave a splitter lane both halves'
capacity, so a yellow splitter passed 10/s on one side into a red belt. Now every edge into or out
of a splitter half carries at most one lane of its tier, and its tier and `CAPACITY` line read the
fullest half.

## Lab tests (a laptop test server, never the live game)

Done on 2026-10-20 (`tools/lab_lanes.py`, `docs/LAB-LANES-20261020.md`): inserter drop lanes
across and along belts and onto turns, underground ends and splitter halves; pickup from a
two-item belt into a furnace, an assembler and a chest; side-loads onto belts and onto both
underground ends; splitters; drill drops; inserter rates per type at three research levels,
chest to chest, from a moving belt and onto one; a full yellow belt; the prototype values.

Still to measure: the benchmark's throughput; whether items already on a lane go ahead of a
side-load; a single lane per tier and the faster loaders; dropping onto a faster belt at hand 3
and up; a splitter with one output blocked; a machine's fluid port.

## Open

1. The joint solve of several items on one lane (now: shares fixed where they meet). [settled
   for 2.0: "Several items on one lane", above; it waits for a design that needs it]
2. A ring of belts (the solver caps its rounds; not tested).
3. The `.fkp` lane notation and the `LANE` check. [built, 2.0: above]
4. Multi-lane nets (2.1): steer to whole belts, or let an agent plan odd lane counts?
5. The path matrix (the "giga brain option"): when it is worth building.
6. The next slices. [built] The catalog's inserter speeds (2.0); the router's tier per connector
   (1.4); `fk rates` (the agent's command) showing the routed section too (2.0: on FILE.fkp as
   the last build laid it out).
7. V1's rate model ties a requester chest's items together the way 1.4's routed one did: a chest
   of three parts and the engine assembler it feeds are 0.000 nominal (the 2005 run's blue
   science). Found in 1.4.1; `fkcore/rates.py` is V1 and was left alone.
