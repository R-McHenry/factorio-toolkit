# CORE-V2: lanes and throughput (draft)

The V2 core, from the brainstorm with Rory on 2026-10-20. V1 (`CORE.md`) is the base and stays true
except where this file says otherwise. Marks: **(Rory)** = his decision, **[proposed]** = mine,
waiting for his OK, **[open]** = still to settle, **[lab]** = a game fact to measure on a laptop
test server (`tools/laptop_server.py`, Factorio 2.0.77) before code relies on it.

## The versions

| version | a net is | the router | the model |
|---|---|---|---|
| V1 | connected or not; one net per belt, both lanes | trees of belts, splitters and undergrounds; no side-loads | nominal, no capacity |
| V2 | one lane (half a belt), so a belt holds up to two nets; a two-sided MinerRow's ore takes both | as V1, lane-aware; lays no side-loads; two nets that share a belt somewhere share it everywhere | capacity per connector, the load, routed rates |
| 2.x | as V2 | knows side-loads: 2-to-1 merges, and lane separation (a splitter, then an underground side-load per net) | as V2 |
| V2.1 | k lanes in one step (2, 3, ...): the bus | lays k-lane nets | as V2 |

V2.1 goes from one lane straight to k lanes, not "a full belt, then several" (Rory). It is
unconventional: an agent may plan a bus of 5 iron lanes and 3 copper lanes, where a person never
plans odd lane counts. [open, V2.1: steer to whole belts, or let it be]

## Words

- **lane** (Rory): one side of a belt, L or R looking downstream (the game's transport lines 1 and
  2). It carries half the tier's belt rate: yellow 7.5/s, red 15, blue 22.5, turbo 30.
- **width**: the lanes a net takes. V2: 1, and 2 for a two-sided MinerRow. V2.1: any.
- **tier**: transport, fast, express, turbo (belts, undergrounds and splitters alike).
- **connector** [proposed]: one lane of one carrier on a net's route (a belt, an underground pair,
  a splitter), and each inserter, side-load joint and pump. The report groups a run of connectors
  that carry the same flow.
- **flow**: what the rate model says a connector carries, in items/s.
- **capacity**: the most a connector can carry.
- **load** = flow / capacity. **A net's load** is the largest over its connectors (Rory), at its
  **critical connector**.
- **binds**: a connector binds when its capacity is what stops more flow; a machine binds when its
  speed, duty, inputs or outputs do.

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

- A lane holds at most one net, so a belt holds at most two. The layout assigns nets to lanes (Rory).
- Lanes are layout, never source: the `.fk` names no lane. A template sets lanes by its own
  geometry and enforces them at its inputs (Rory); the router records the lane its net's items
  are on.
- The two-sided MinerRow stays: it is the 99.9% template (Rory). [proposed] Its ore is one net on
  both lanes, north drills on L, south drills on R.
- `.fkp` [proposed]: a belt, underground or splitter line carries `net=iron|coal` (L|R),
  `net=iron|` (L only) or `net=|coal`. A V1 `net=iron` means both lanes, so every V1 layout stays
  valid and nothing in the world changes until a design uses lanes. Inserters, pipes and pumps
  keep one `net=`.
- Invariants [proposed]: two nets on one lane; a belt line with a lane net beside a whole-belt net.
- Checks: `LANE` [proposed]: a net's items land on a lane the layout gives another net (`LEAK` at
  lane level). `UG_SIDELOAD` goes: a side-loaded underground is a valid connection for the
  open-side lane and a blocked one for the other (Rory). `SHARED_BELT` (1.1 spec, never built)
  goes: two nets on one belt is normal now.
- `WRONG_LANE` goes (Rory): an item gets no leniency for being on the right belt in the wrong net.
  An item on a lane whose net doesn't carry it is `WRONG_ITEM`, per lane. The snapshot already
  reads each lane, and only adds them up today.

## The router in V2.0 (Rory)

- No side-loads. It lays none today: the routed redgreen layout has 665 belt, 77 turn and 13
  underground edges, and not one side-load.
- Two nets that share a belt on one connector share it on every connector: the router lays them as
  one pair.
- Otherwise one net per routed belt, on one lane. The templates own the lane joins at their inputs.
- The tier comes from the model, per net, with flags: only yellow; at most N red belts; minimize
  (the slowest tier that carries the flow) or maximize (the fastest available).
  [open: per net or per connector]
- No direct insertion where a net's flow is above a threshold: a lane, or what the lab finds.
  Inserters bind early.
- 2.x: side-loads as merges (the smelter stack's side-loader) and lane separation (a splitter,
  then each branch side-loads an underground that passes only its own net).

## Throughput [proposed; still being brainstormed]

**Flow per connector.** V2 routes are trees: a merge tree from the drivers into a trunk and a split
tree from it to the consumers, plus the rows' own belts with one inserter tap per machine. On a
tree, every connector's flow follows from the nominal model's endpoint rates:

    flow(c) = min(what the drivers upstream of c put on its lane, what the consumers downstream of c take)

On the split side that is the consumers below it, on the merge side the drivers above it, and on the
trunk the whole net. Along a row's input belt it falls after each tap. Each lane is its own
connector: a two-sided MinerRow's north drills fill L, its south drills R. [open: a route that is
not a tree]

**Capacity per connector.** A lane: its tier's lane rate. A side-load joint: the target lane, since
both incoming lanes squeeze into it. An inserter: its rate (below). A pump: its rate. A pipe: none.

**Load.** load(c) = flow(c) / capacity(c), and the net's load is the largest (Rory). Below 1, the
route carries what the machines ask and the machines bind. Above 1, the carriers bind, and the
load says by how much: 1.33 needs a lane a third faster, or a second lane in V2.1.

**Routed rates.** Solve the model again with every connector over 1 as a cap on the endpoints
behind it (the consumers it leads to, or the drivers it drains), shared by appetite like a short
net in V1. Caps only lower flows, so only the connectors over 1 in the nominal pass can bind (a
sink takes what is left: check those once more). The binding chain names the connector.

**Report.** `report_rates` runs before routing (the rows' own connectors: an inserter that can't
keep up already shows here) and again after `route` (the routed ones). `CAPACITY` is a warning per
net over 1, naming the critical connector, its flow and its capacity.

**The tier choice reads the loads.** Minimize: each connector gets the slowest tier at or above its
flow. Only yellow: no choice, and the loads report. At most N red: upgrade the highest loads
first. Maximize: the fastest tier available everywhere. A tunnel's two ends change tier together;
the router lays tunnels at the yellow reach, so any upgrade fits.

An example, on paper: a MinerRow of 20 drills (10 ore/s, 5 on each lane) into a row of 32 stone
furnaces that takes ore on one lane of an ore|coal belt.

| connector | flow | capacity | load |
|---|---|---|---|
| the miner belt, L and R | 5/s each | 7.5/s | 0.67 |
| the smelter row's head: both ore lanes side-loaded onto L | 10/s | 7.5/s | **1.33** |
| one furnace's feeder (a fast inserter) | 0.33/s | about 2.3/s | 0.14 |

Net ore has a load of 1.33 at the smelter row's head, so the report has a `CAPACITY` line, and the
routed model runs the row at 75%. In the game, the first 24 furnaces run and the last 8 starve. A
red input lane, a second smelter row, or V2.1's two lanes fixes it.

## Inserters

- Rule of thumb (Rory): 60 x rotation speed x hand size items/s. Measured (2.0.77, a force with
  no research, then with bonuses): it holds chest to chest within 4% (the fast and bulk inserters
  make 2.5 a hand, not 2.4), and from a full moving belt up to hand 2 (fast at hand 3: 93%). Onto
  a moving belt it holds at hands 1 and 2, then falls off (fast at hand 3: 75%, bulk at hand 4:
  60%, onto yellow). [proposed] The rate is the rule of thumb, with the measured factor when
  dropping onto a belt at hand 3 and up.
- The prototype values (rotation 0.013 burner, 0.014 inserter, 0.02 long-handed, 0.04 fast, bulk
  and stack) were read from the game; the catalog doesn't carry them yet.
- The table is big (Rory): burner, inserter, long-handed, fast, bulk and stack, with the hand size
  set by research (the force's inserter and bulk bonuses), and quality later. On paper the hand is
  1; live, it is the force's. A bulk inserter's hand is 1 + the bulk bonus, a stack inserter's
  5 + it.
- An inserter is one connector, one lane: two nets through one inserter share its rate.
  [open: one net, or several, through a shared inserter]

## The benchmark (Rory)

The smelter stack with opposing splitters side-loading onto opposing belts: the design that proves
V2 out, and a template after that. [open: its exact layout. A blueprint string of it would let the
toolkit import it as a `Literal`, judge its lanes and loads, and compare that with the lab]

## Lab tests (a laptop test server, never the live game)

Done on 2026-10-20 (`tools/lab_lanes.py`, `docs/LAB-LANES-20261020.md`): inserter drop lanes
across and along belts and onto turns, underground ends and splitter halves; pickup from a
two-item belt into a furnace, an assembler and a chest; side-loads onto belts and onto both
underground ends; splitters; drill drops; inserter rates per type at three research levels,
chest to chest, from a moving belt and onto one; a full yellow belt; the prototype values.

Still to measure: a single lane per tier and the faster loaders; dropping onto a faster belt at
hand 3 and up; a splitter with one output blocked; a machine's fluid port.

## Open

1. Connector: one per lane of each carrier (as above), or something else?
2. A shared inserter (a furnace fed ore and coal by one inserter from an ore|coal belt): one merged
   net, or several nets into a machine that takes them all?
3. The tier per net, or per connector (a red trunk with yellow branches)?
4. A route that is not a tree.
5. V2.1: steer to whole belts, or let an agent plan odd lane counts?
6. The benchmark's exact layout.
7. When the model should share by position (the game's first come, first served) instead of by
   appetite.
