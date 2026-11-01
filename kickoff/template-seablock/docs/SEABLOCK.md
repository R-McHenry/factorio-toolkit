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
  - half a vanilla robot's speed (0.03; speed 1 research adds 35%);
  - cargo 1, which cargo 1 research raises to 2;
  - a 0.5 MJ battery.
  - Their recipe is open from the start, in an assembler: 4 iron plates, 2 gears and 3 basic
    circuits.
- **The early roboport:**
  - logistics radius 15 and construction radius 32 (a vanilla roboport has 25 and 55);
  - 2 charging pads at 250 kW;
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
