# Sea Block

Sea Block (0.6, on Factorio 2.0 with Bob's and Angel's mods) is a world of sea. There's no ore,
no trees, no cliffs and no biters, and worms are switched off for this run. Everything comes out
of the water: water gives slag and mineral water, those give the Angel's ores, and the ores are
crushed and smelted into plates. Every tile you build on is landfill.

The numbers below were read from this run's game. `fk catalog show NAME` and `fk tech ITEM` tell
you more about any one of them.

## Landfill

- Water counts as ground that costs landfill. A build puts a landfill tile ghost under every
  entity tile that stands on water, and robots lay it before they build the entity. An offshore
  pump keeps its water side.
- Sea Block's landfill is the item `landfill-sand`, which lays the `sand-3` tile: one item per
  tile, so a 3x3 machine takes 9. `out\report_bom.txt` counts it like any other item.
- The kit holds 2000. The `landfill` tech (10 red, after water washing 1) unlocks its recipe:
  10 stone make 1.
- The kickoff landfilled the kit's own rectangle, map (0,5) to (25,23). Everything else is open
  water.

## The opening, as Sea Block's techs set it

Sea Block's first techs open when an item is first made, and a machine making it counts. Each
step's first craft opens the next step:

1. **Water.** Offshore pumps (4 in the kit) stand at the water's edge.
2. **Slag or mineral water.** Two routes, both open from the start:
   - an electrolyser (300 kW) turns 100 water into 1 slag, plus oxygen and hydrogen, which a
     flare stack burns off;
   - a liquifier turns 10 stone and 100 water into 100 mineral water, and a crystallizer turns
     200 mineral water into saphirite (`angels-ore1`) and stiratite (`angels-ore3`), by chance.
3. **Crushing.** The burner ore crusher makes 2 stone from 1 slag, and crushed ore (plus a
   stone) from 2 ore. **The first crushed stiratite** opens the plate recipes: 3 crushed
   saphirite smelt into 2 iron plates, 3 crushed stiratite into 2 copper plates, plus copper
   cable.
4. **Basic circuits.** 1 wood makes a wooden board, and the board plus 3 cable makes a basic
   circuit. `angels-bio-wood-processing` is already researched. **The first circuit** opens
   inserters, pipes, gears, iron sticks, burner inserters, iron chests, basic belts and the lab.
5. **The lab** takes 10 gears, 10 circuits and 4 basic belts. **The first lab** opens red
   science: 1 gear and 1 basic circuit, 5 s.
6. **Red science.** Most of the early techs cost 20 red and take 15 s each:
   - automation: assembling-machine-1 and the electric ore crusher, 10 red;
   - steam power, logistics, fluid control, basic chemistry, sulfur processing 1, water
     washing 1, landfill, long inserters, lamp, military, wood processing 2 and green algae.

   Slag processing 1 is the gate: every other tech waits on it. Ore crushing (20 red, after
   slag processing) opens the ore sorting facility and smelting from sorted ore.

Until red science, Sea Block keeps every recipe locked that would eat the starting iron,
circuits and bricks. Those 1200 plates and 200 circuits are the budget for the first machines.

## Wood is the early bottleneck

- In Sea Block a player forages wood by hand. There's no character here, so the kit's
  **2000 wood** is all there is until the base grows its own.
- Each basic circuit costs 1 wood, so each red pack costs 1 wood.
- A burner crusher (100 kW) burns a wood every 20 s, and a stone furnace (90 kW) about every
  22 s.
- Ways to stretch it:
  - electric crushers (automation) take no wood, and nor does any electric machine;
  - green and brown algae, composting and the arboretum (`angels-bio-processing-brown`, then
    `angels-bio-arboretum-1`, whose wood sawing turns trees into wood) make wood again;
  - charcoal from wood bricks is the fuel after that.
- Plan the wood loop early, and keep the kit's wood for circuits.

## Power

- Solar to start: the kickoff built 6 panels and 2 accumulators, and the chests hold 32 more
  panels (60 kW each) and 30 more accumulators. Together that's about 2.3 MW in daylight.
- The electrolyser alone takes 300 kW, and the early roboport up to 520 kW while it charges, so
  put the kit's panels out early.
- Steam power is a red tech. Its boilers burn chemical fuel, which means wood or charcoal at
  first.

## Robots

- **Early robots** (`fk-early-construction-robot`, `fk-early-logistic-robot`):
  - three quarters of a vanilla robot's speed (0.045; speed research adds to it);
  - cargo 1, which cargo 1 research raises to 2;
  - a 1.2 MJ battery.
  - Their recipe is open from the start, in an assembler: 4 iron plates, 2 gears and 3 basic
    circuits.
- **The early roboport:**
  - logistics radius 20 and construction radius 44 (a vanilla roboport has 25 and 55);
  - 4 charging pads at 400 kW, 5 robot and 5 repair slots;
  - recipe: 30 iron, 15 gears, 20 circuits and 20 stone bricks;
  - it upgrades in place to a roboport.
- The kit has 30 early construction robots, 20 early logistic robots and 4 more early roboports.
  More robots are a recipe away.
- **Loot chests:**
  - an iron chest on a 5x5 islet once every 5 chunks, from about 150 tiles out;
  - each is marked `loot N` on the map once charted;
  - ring N holds 10xN early construction robots, half as many early logistic robots and an early
    roboport; from ring 3 it also holds real construction robots.
  - They're yours: reach one with roboport coverage (landfill and poles out to it), then
    `fk decon` it, and the robots bring its contents home.

## Inserters turn corners and reach further

Bob's inserters let every inserter pick up from and drop onto any tile beside it, each chosen on
its own. There's no special item for it:
- **From the start:** an inserter can turn a corner, picking from the north and dropping east,
  say. A corner swing is a quarter turn, so it's about twice as fast as a straight one (measured
  in this game: a plain inserter 1.2/s straight, 2.5/s round a corner; fast 3.75 and 7.5).
- **`bob-long-inserters-1`** (20 red, after logistics): any inserter reaches 1 or 2 tiles for each
  end. No long-handed item is needed. `bob-long-inserters-2` (50 red, green and blue) reaches 3.
- `bob-more-inserters-1` adds the diagonals, and `bob-near-inserters` the belt's near lane. The
  router doesn't use those yet.

The build reads which of these the force has (`fk avail --save` and every `report_bom --stock
live`, into `out\avail.json`). The router uses what's there:
- a straight plain hand first;
- then a corner, or a reach of 2 once long-1 is in;
- a long-handed inserter only where none of those fits.

So two chests on a diagonal take one corner inserter and no belt. After long-1, two chests three
tiles apart take one plain inserter. A route that stands keeps its hands; `fk route NET` lays it
again with the new reach. In the .fkp a hand with its own vectors reads `pick=0,-1 drop=1,0`
(tiles from its own tile, x east, y south). The paste writes them, and robot-built ghosts keep
them. A vector the force hasn't researched is a `needs-research` line that names the tech.

## Pipes

The router lays copper pipes (`bob-copper-pipe`, 1 copper plate) and copper pipes-to-ground
(an underground reach of 11, as iron's). That keeps iron for everything else. `route --pipe
stone` lays Sea Block's stone pipes (stone bricks), and `--pipe iron` the vanilla ones. Pipes of
every material join each other.

## Several inserters on one machine

Early on, only plain inserters (1.2/s) are available, and many Sea Block machines need more than
that. Where the best inserter the network can build is too slow for a machine on a belt, the
router lays 2 or 3 of them into or out of it. A cable assembler gets two out of it. A requester
chest gets up to three loaders, its belt wrapping round it. A liquifier eating 10 stone/s gets
three in. That's still short (`too-thin` says by how much): three plain inserters move 3.6/s, so
feed it from more chests.

A route that already stands keeps its inserters. `fk route NET` (or `route --again NET`) lays a
net again with the extra ones.

## Huge chests: buffers that feed many machines

Angel's storage adds big plain chests, both with an inventory bar:
- `angels-silo`, 4x4 with 256 slots: tech `angels-ore-silos`, red science after steel and
  advanced ore crushing; recipe 20 stone bricks, 20 iron plates, 10 steel;
- `angels-warehouse`, 6x6 with 768 slots: tech `angels-warehouses`, red, after the silo; recipe
  100 bricks, 100 iron, 50 steel.

Their logistic versions need logistic system 3, so they come much later.

A huge chest is a `Buffer` with another chest. It has 16 (silo) or 24 (warehouse) edge tiles for
inserters, so many machines can take from it directly, each taking only what its recipe uses:

```
module Hub size 24x24 {
  qf  = Chest<requester, item=iron-plate, request=50>   @(1, 1)
  qc  = Chest<requester, item=copper-plate, request=50> @(22, 1)
  hub = Buffer<chest=angels-silo, bar=60>               @(10, 10)
  g1  = Assembler<recipe=iron-gear-wheel> @(3, 7)
  ...                                     # g2..g4, and k1..k4 making copper-cable
  box = Chest<provider> @(22, 22)
  wire hw red: hub                                       # the silo's contents on a wire
  net fe: qf -> hub when hw.iron-plate < 400             # top up iron to 400
  net cu: qc -> hub when hw.copper-plate < 400
  net fd items iron-plate:   hub -> g1, g2, g3, g4
  net cd items copper-plate: hub -> k1, k2, k3, k4
  net out: g1, g2, g3, g4, k1, k2, k3, k4 -> box
}
```

This routes on paper: 5 nets, every machine reached. Notes on it:
- **Name each out net's items** (`net fd items iron-plate:`). With two items in the chest and no
  `items`, both go on both nets (`two-nets`, `CLOG`).
- **Without circuits, use `bar=` for the limit.** `bar=60` lets the silo fill 60 of its 256 slots;
  when it is full, what feeds it stops. Circuit network is a green tech (and bio paper), and only
  then do `wire` and `when` gates work in the game.
- **With circuits, a gated hub is a smart chest.** Each source tops up its own item to an amount
  (`when hw.ITEM < N`), and each machine takes what it needs from the shared chest. That is the
  sushi pattern "sources gated on what the buffer holds" (LANGUAGE.md "Sushi patterns") with a
  bigger box.
- **Put machines right against the chest** for direct insertion: one inserter from chest to
  machine, no belt, and it takes only what the recipe uses. Machines further out get a belt
  from the chest, and the inserter loading that belt must filter, or it loads everything the
  chest holds. Basic and long-handed inserters can't filter; fast and bulk inserters can. Until
  you have them, hold one item per chest where a belt leaves it. The build says `unfiltered`
  when it lays a hand that can't filter.
- **As a buffer belt:** a silo between a slow, steady maker (a crystallizer line, crushers) and
  users that come and go holds 256 stacks (25,600 plates at 100 a stack) without a bar, enough
  to keep them running through a gap.

## What carries over from vanilla play, and what doesn't

Carries over:
- modules, cells and the lab;
- the ramp (each step about twice the last);
- the deadlock rules (a maker that waits on its own item; lay the maker of every short item
  first);
- robots never fuel what they build;
- a long research queue;
- makers of robots and roboports next to their inputs.

Doesn't carry over:
- ore patches, drills and `MinerRow`;
- coal;
- biters and land mines;
- the reactor and oil wells: Angel's petrochem makes oil products from gas later;
- the vanilla ramp's timings: Sea Block's pace is its own, and this is the first run of it.

The toolkit plans Sea Block's fluid machines (electrolyser, crystallizer, liquifier) with the
game's own fluid boxes: they matched for all 2400 of its fluid recipes. They're still newer
ground than vanilla machines, so lab each one in a cell before it goes in the base. If one won't
route, building it by hand in the lab and wrapping it with `fk capture` gets you a cell that
works. What doesn't route goes in `FRICTION.md`. `InfinityPipe<fluid=...>` feeds a test design
its own fluid.

`fk sim` (the planner) runs this game with its mods too.
