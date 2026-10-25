# Toolkit 2.0.29: a port is a lane (2.0.28's port was a belt end)

Rory, 2026-10-25, correcting phase 1 the day it shipped: "ports are all at the lane level, so
x,y,direction still can have two ports for the two belt lanes. And the current bus design, the taps
are all two ports each."

2.0.28 modelled a port as a belt end: one name, an item list, and `iron-ore | coal` as one port
carrying two items. That is wrong — the interface is finer than the belt. A port is **one lane**, so a
belt end's two lanes are two ports at one `(tile, direction)`, and a bus tap (a belt end) is two
lane-ports, not one.

## The statement now

```
port iron : in  iron-plate      @w      # one lane; the build picks the tile and the lane
port feed : in  iron-ore | coal @s      # the pair: the two lanes of one belt end (left, right)
port out_ : out iron-plate      @n0L    # a pinned tile and lane
```

- **A port is `(side, pos, lane)`**, lane L or R looking downstream (as `fkcore.lanes` names them),
  and a tile has two: `@s4L` and `@s4R` are different ports. `@s4` alone leaves the lane to the build,
  which chooses it facing the partner with the tile (phase 3; `@s4L` pins both).
- **`A | B` is the pair**, exactly as `lanes A | B`: what comes before the bar is the left lane, after
  it the right. `,` is several items on **one** lane (a mixed lane), so `port feed : in iron-ore,
  copper-ore | coal @s` is a mixed left lane and coal on the right. An item may not be on both lanes.
- **The inside of a pair is two nets paired with `lanes`** — one lane each, each naming its item,
  `lanes ore_ | coal_` to say they share the belt. A net that names a pair and declares no items takes
  everything the port carries (a ref adds all it makes, as any instance ref does), so a lane's net
  names its item.

## What it changes in the model

- `PortInst` carries the pair (`items` = left lane, `right` = right lane) and the pinned `lane`;
  its conduit machine makes and takes **both lanes' items** at no rate, so the rates model still joins
  one pool per item — a lane is a pool by item, which is what the lane physics needs.
- `PORT` gains the lane rule: a lane holds one port, two lanes a tile. A pair takes both lanes; a
  pinned one-lane port takes the one it names; two pinned ports on one lane is
  `@s4L is already m/a's lane: one port a lane, two lanes a tile`. An unpinned lane cannot collide
  yet, because the build has not chosen it.
- The refusal names the pair: `feed (in iron-ore | coal)`.
- Everything 2.0.28 did is unchanged: sealing, the ref-past-the-ports refusal, the crossing net split
  at the port, the `PORT` checks, `size` as the frame.

## The bus, for phase 2

Rory settled it with the correction: **the bus gets no port names** — its connection list *is* its
lane-port map. Today `templates.bus` gives each tap and each load one `MSpec` and one role, i.e. one
belt end; phase 2 makes each two lane-ports, so a full belt on a tap is two entries in the list, and
`lanes A | B` becomes the way to fill a tap's two lanes. Recorded in `PLAN-MODULES.md` §4.1, §4.9 and
§10.4; no bus code changed here.

## Tests (29 in `tests/test_ports.py`)

New `LaneTest`: a pair is two lane-ports that bind by item (outside `net a: mine -> burn.feed` binds
iron-ore, `net b` binds coal); `rates` pools each lane's item through the port with no `UNDERFED`; two
ports on one tile, one lane each, do not collide; two on one lane do; a pair takes both lanes and
collides with neither; the refusal names the pair. The syntax tests cover `@n0L`, `A | B`, a mixed
lane, a pair with a lane (`a pair is both lanes`) and an item on both lanes. The baseline test is
unchanged: no existing `.fk` has a port, so every machine, net and check line is still exactly what
2.0.27's elaboration produced.

## Still open

A bare ref or `gears.*` on a sealed module is refused (2.0.28). Whether it should mean the module's
ports instead is the one question left from the correction; it is §10.4 of the plan.
