# Factorio strategy guide

What has worked, collected 2026-10-21 from three sources:
- Rory's advice, 10-15..21, in his sessions and in-game chat;
- the notes the Claude players left after their runs (0534, 2005, the lead world);
- what those runs actually did.

It is advice with reasons, not rules: use what fits the map in front of you.

## The shape of a game

Progress comes in turning points. Each one makes the next part of the game cheap, so it pays to
reach it fully rather than hover just short of it.

1. **Bootstrap:** the first drills, then plates.
2. **Logistics researched and a mall up.** From here you can craft everything a big factory needs.
3. **Construction robots made in the base.** This is the chance to explode: a positive feedback
   loop where more robots build more of everything faster.
4. **Exponential growth:** double and triple science, robot production and mining, then double it
   all again.
5. **A base that can take on anything.** After exponential growth, the next turning point depends on
   what the run is for. By now there is enough mall, production and construction capacity that any
   part of the game can be approached with a clear plan:
   - a purple science factory to unlock beacons, then beacon the whole base;
   - a rush to Vulcanus to build a new base there;
   - a rocket and a ship. These need a well-stocked mall fed by belted furnace stacks and
     belt-based circuit factories, with every raw material factory an array, not one-off machines.
     The lead world's first rocket took the silo, 50 rocket parts, and steel hauled 150 tiles. A
     space platform starter pack is 20 steel, 20 processing units and 60 foundations.
   - growing the base massively as a planned, expandable system. Another iron stack takes seconds
     to add, and you're confident the power, building materials and planned space are there to do
     it again and again, indefinitely.

With a good strategy, every build pays off right away or soon after, and that return pays for the
next step. Low volume, a missing mall, power trouble and idle labs are all strategy problems, and
much of the big work in past runs never paid off because the strategy was off.

## Pace

Speedruns give the scale (Rory, 2026-10-21): Factorio 1.x about 1 h 18 min, 2.0 about 6 h, a
rocket in about 43 minutes. Use them to estimate the science per minute each later tier of research
needs. That gives the factory you would need at the rocket, a rough upper target, and a smooth
exponential ramp from the start up to it. A player working things out mid-game will be much slower
than record pace. Following the same rate targets per tech level, rather than per hour, still keeps
the ramp right.

## Bootstrap

- **Guard the starter iron.** Recent kits had plates and ore but no drill, and a drill needs plates.
  Spend first on what makes more iron:
  - one lab, which triggers the red science tech;
  - about 35 red packs for automation and electric-mining-drill;
  - then 4 to 6 drills.

  One run spent every plate on belts and circuits first and stood at 0 iron with nothing able to
  mine.
- **Use a chest -> assembler -> chest crafter for the first few multi-ingredient crafts**, not
  belt-fed crafters. Then start small:
  - 1 coal drill and 4 iron drills feeding a smelter;
  - the plates go to a small factory that makes belts;
  - with a few hundred belts in hand, build one factory that turns ore into plates, then science,
    all by belt.
- **Research logistics before any big belt build.** The router uses undergrounds and splitters, and
  while they are locked those routes stay open. One run couldn't finish logistics because the open
  route was the copper belt its red science needed.
- **Short on belts or undergrounds?** Take down something non-essential for a while (a science
  block, an old relay) and rebuild it later.

## Research

- **Idle labs mean progress has stopped.** Keep the queue long. Research what moves you forward
  (automation, electric mining, logistics, fast inserter, automation-2, electric energy
  distribution, construction and logistic robotics) and skip what doesn't (damage upgrades nobody
  uses).
- **When research stalls, check which pack the labs are waiting for** and scale that pack's makers.
  Twice overnight, robots weren't the limit as the player thought: labs were waiting on green or
  blue.

## The mall

- **The mall is the main track, not a side project.** It makes everything you need to keep
  expanding: belts, undergrounds, splitters, inserters, poles, assemblers, furnaces, drills, and
  later robots and roboports.
- **A well-laid mall needs a few hundred belts at most.** Rory's best layout:
  - machines in rows, with no gap between neighbouring chains and a 1-tile gap only where one
    machine feeds the next;
  - rows facing a shared corridor.

  Malls with 8-tile gaps and ingredients far apart burned through thousands of belts.
- **Inputs and output:** one iron net and one copper net in. Feed them by belt from the mall's own
  furnaces where you can, since requester chests are scarce. Out goes one products net, a sushi
  belt, into one provider chest with a limit per item.
- **Fast inserters on mall machines.** Rory has asked for this three times.
- **A one-off crafter suits rare items.** Switch it off when done: one ran on to 43 chemical plants.
- **The belt mall is how the early friction ends.** Early one-off crafters are fiddly by design, and
  the way out is a belt-based mall, not better one-off crafters. Before logistic chests unlock you
  can only run a few one-offs anyway. When a crafter switches recipes, circuits in the game stop its
  inserters from carrying the wrong items, not a script.

## Growing

- **The volume targets:**
  - about 10 red and 10 green science assemblers before blue;
  - with blue, 8 to 15 each of blue, advanced circuit and engine assemblers;
  - one pack a second of each colour eats about 1,200 iron and 600 copper plates a minute.

  Size the next step with `fk rates` / `fk plan` (or `n=auto`), build it, then double it.
- **Belts carry the big flows, robots build and handle one-offs.** Logistic robots become a
  throughput cap: 50 robots carrying plates 100 tiles starved science for hours. Put smelting and
  its consumers in one factory where you can.
- **Find the next ore patch before you need it.** Use radar, and roboport chains (each roboport
  within 50 tiles of the last) to reach new patches; put a storage chest near far builds.
- **Keep the rest of the base growing alongside science.** A big science block with too little
  smelting and too little of the materials it's built from stalls.

## Robots

- **Build robots early and keep building them.** Everything builds and moves faster with more.
- **Robots in a chest do nothing.** An inserter puts them into a roboport.
- **More robots raise the cap now; robot speed research raises it later.**

## Power

- **Plan generation before demand catches up.** Steam is boilers plus engines from an offshore
  pump, ideally as its own small factory. The nuclear plant's fuel saver keeps the reactor hot with
  an empty fuel slot, and that is normal.
- **Solar alone can't carry roboports through the night.** The 2005 run lost its base when biters
  took its reactor.
- **Rebuilds can cut power.** A changed layout re-lays poles, and if the old ones go before the new
  ones stand, part of the base goes dark and its roboports with it. Both overnight players lost
  power this way. Get the new grid standing first.
- **Use medium or steel poles once you have them**, not wood.

## Chests and buffers

- **Limit chests.** Unlimited chests fill with thousands of items the rest of the base needs.
  Hundreds of items sitting still usually mean something is overproducing.
- **A chest at the head of a belt takes everything** (SHARED_SINK). Give science its own supply,
  and tap storage from another.
- **Mixed items work where every sink takes all of them**: one chest feeding one machine by one
  inserter, or a products belt into one chest. One inserter from a multi-item chest into labs that
  take every pack can't clog either, since the inserter only takes what the lab will accept. On a
  belt into machines that each take only some items, the mix jams sooner or later (the CLOG
  warning).
- **Requesters and providers are a fixed budget** until late research. Count them before
  designing.

## Rebuilds

- **Establish a backbone first, so later work doesn't rip it up.** A main bus can be the spine for
  items, power and roboport coverage, with fixed poles and roboports along it. Factories off its side
  are built and torn down without cutting the main flow. Other shapes come later: a city-block grid
  gives power and roboports but no item backbone without trains; a freeform base needs a hand-placed
  bus plus robot and power scaffolding.
- **Prefer patches to rebuilds.** Pin what stands and change only the part that needs changing,
  rather than regenerating the whole base. Routing a new section into the old one, even as a bit of
  spaghetti, beats ripping everything up. As a fallback, leave old poles and roboports standing
  until the new ones are up.
- **The design wins.** Build over what stands there. Temporary builds go in sanctioned space and
  come out when they're done.
- **Rebuilt belts, pipes and inserter hands can hold old items.** `fk fresh` clears them.
- **Drain before a big rip:** shut the input and let the factory run its buffers down. Large rips
  take a while.
- **Moving a factory:** robots take its machines to other ghosts first. Free what the move needs
  before you start.
- **Grow in steps.** Adding a consumer re-routes its whole net, and re-laying iron, coal and plates
  at once stopped iron for 20 minutes.

## Defense (on maps with biters)

- **Landmines are the gold standard on Nauvis.** Turrets protect the early game. Once landmines are
  unlocked they are the best offensive and defensive weapon for the rest of the game.
- **Attacking a nest with landmines:**
  1. Prepare: about 50 spare landmines and 50 spare robots.
  2. Place all 50 at once, as close to the spawners and worms as possible.
  3. When the wave has landed, deconstruct the leftover landmine ghosts and keep the mines that
     stand.

  Why: the enemies attack the robots, and robots only trade well when they outnumber them, so they
  have to go in one big wave. After it, replacement robots trickle in one at a time and lose.
- **Landmines only help where the enemy comes**, close to the base. One out of reach still ties up a
  robot and a mine.
- **Before landmines, turrets go where the damage happens, not up against nests.** Clusters around
  the base held the 10-16 base (5 clusters of 8), with the danger corners left alone. Yellow ammo
  doesn't stop big biters. A belt or inserter loop of ammo keeps turrets fed, with fast inserters on
  the magazine assemblers. Fortify before you put a roboport near a nest.

## Playing well

- **Keep something running.** Every round should place something that runs. Planning that leaves
  nothing going is lost time.
- **Look around instead of pausing.** Check several parts of the factory: idle robots, stock
  levels, starving machines. They suggest what to do next.
- **Some things that look wrong are fine:** an idle machine, a hot reactor with no fuel cell,
  ghosts waiting for a robot trip. Ghosts that wait on missing items or locked recipes are a
  blocked build.
- **Investigate any way you like:** code, scripts, Lua reads. The game rule is only about changing
  the world: build through ghosts and robots, with nothing created or refilled by script.
- **A script may carry out one specific multi-step build action.** A process that runs over time and
  can be automated in the game belongs in the game (circuits, the mall), not in a script that
  manages the base or keeps everything stocked through one-off crafters.
- **Grow helpers into a small library of reusable features** in your codebase rather than many
  one-off scripts, so they scale with the base instead of piling up as debt.
