# Factorio strategy guide

How to play Factorio 2.0 with Space Age well, from Rory. It's advice with reasons, not rules: use what
fits the map in front of you.

## The shape of a game

Progress comes in turning points. Each one makes the next part of the game cheap, so it pays to
reach it fully rather than hover just short of it.

1. **Bootstrap:** the first drills, then plates.
2. **Logistics researched and a mall up.** From here you can craft everything a big factory needs.
3. **Construction robots made in the base.** This is the chance to explode: a positive feedback
   loop where more robots build more of everything faster.
4. **Exponential growth:** double and triple science, robot production and mining, then double it
   all again.
5. **A base that can take on anything.** What comes next depends on what the run is for. There is
   now enough mall, production and construction capacity that any part of the game can be
   approached with a clear plan:
   - a purple science factory to unlock beacons, then beacon the whole base;
   - a rush to Vulcanus to build a new base there;
   - a rocket and a ship. These need a well-stocked mall fed by belted furnace stacks and
     belt-based circuit factories, with every raw material factory an array, not one-off machines;
   - growing the base massively as a planned, expandable system. Adding another iron stack takes
     seconds of your attention (robots still take a while to build it), and you're confident the
     power, building materials and planned space are there to do it again and again, indefinitely.

With a good strategy, every build pays off right away or soon after, and that return pays for the
next step. Low volume, a missing mall, power trouble and idle labs are all strategy problems.

## Pace

Here are the totals from this game's own tech tree. In Space Age the rocket silo needs only red,
green and blue.

| milestone | science, all research up to and including it |
|---|---|
| blue science unlocked | about 1,050 red and 900 green |
| rocket silo | about 4,200 red, 4,100 green and 2,650 blue (1,000 of each is the silo itself) |
| a rocket | the silo, then 50 rocket parts, each a processing unit, a low density structure and rocket fuel |

Speedruns reach a rocket in about 43 minutes, and the full 2.0 game in about 6 hours. At that pace,
science grows exponentially:

| stage | science per minute, each colour |
|---|---|
| the first red-only techs | about 10 |
| unlocking blue | 50 to 100 (about 10 red and 10 green assembling-machine-2) |
| researching the rocket silo | a few hundred |

Aim for those rates at each stage of the tech tree. The time it takes you matters less than
reaching the rate before the tier that needs it. One pack a second of each of red, green and blue
eats roughly 1,200 iron and 600 copper plates a minute, so the mining and smelting grow with it.

These figures count science only, and they understate the whole base. Science is the biggest single
cost, but the base itself takes a sizeable share on top: machines, belts, robots, power, and then
the rocket's materials and the silo. So run mining and smelting well above what science alone
implies, roughly one and a half to two times.

## Bootstrap

- **Guard the starter iron.** Spend the first plates on what makes more iron:
  - drills;
  - one lab, which triggers the red science tech;
  - the red packs for automation and electric-mining-drill.

  Belts and circuits come after.
- **Use a chest -> assembler -> chest crafter for the first few multi-ingredient crafts**, not
  belt-fed crafters. Then start small:
  - 1 coal drill and 4 iron drills feeding a smelter;
  - the plates go to a small factory that makes belts;
  - with a few hundred belts in hand, build one factory that turns ore into plates, then science,
    all by belt.
- **Research logistics before any big belt build.** The router uses undergrounds and splitters, and
  while they are locked those routes stay open.
- **Short on belts or undergrounds?** Take down something non-essential for a while and rebuild it
  later.

## Research

- **Idle labs mean progress has stopped.** Keep the queue long. Research what moves you forward
  (automation, electric mining, logistics, fast inserter, automation-2, electric energy
  distribution, construction and logistic robotics) and skip what doesn't.
- **When research stalls, check which pack the labs are waiting for** and scale that pack's makers.

## The mall

- **The mall is the wheels the rest of the game runs on.** It makes everything you need to keep
  expanding: belts, undergrounds, splitters, inserters, poles, assemblers, furnaces, drills, and
  later robots and roboports.
- **A well-laid mall needs a few hundred belts at most.** Rory's best layout:
  - machines in rows, with no gap between neighbouring chains and a 1-tile gap only where one
    machine feeds the next;
  - rows facing a shared corridor.
- **Inputs and output:** one iron net and one copper net in. Feed them by belt from the mall's own
  furnaces where you can, since requester chests are scarce. Out goes one products net, a sushi
  belt, into one provider chest with no slot limit. The per-item limits sit at the makers (inserter
  conditions on each product's output).
- **Fast inserters on mall machines.**
- **A one-off crafter suits rare items.** Switch it off when it has made what you need.
- **The belt mall is how the early friction ends.** Early one-off crafters are fiddly by design, and
  the way out is a belt-based mall, not better one-off crafters. Before logistic chests unlock you
  can only run a few one-offs anyway. When a crafter switches recipes, circuits in the game stop its
  inserters from carrying the wrong items, not a script.

## Growing

- **The volume targets:**
  - about 10 red and 10 green science assemblers before blue;
  - with blue, 8 to 15 each of blue, advanced circuit and engine assemblers.

  Size the next step with `fk rates` / `fk plan` (or `n=auto`), build it, then double it.
- **More, then enough.** Early on you always want more: more robots, more plates, more of
  everything. Once the base is big enough that you're managing it, robots and every material get
  capped: you want as much as you need.
- **Belts carry the big flows; robots build and handle one-offs.** Logistic robots become a
  throughput cap if they carry the main plate flows. Put smelting and its consumers in one factory
  where you can.
- **Find the next ore patch before you need it.** Use radar, and roboport chains (each roboport
  within 50 tiles of the last) to reach new patches; put a storage chest near far builds.
- **Keep the rest of the base growing alongside science.** A big science block with too little
  smelting and too few building materials stalls.

## Robots

- **Build robots early and keep building them** until you have enough to manage; then cap them.
- **Robots in a chest do nothing.** An inserter puts them into a roboport.
- **More robots raise the cap at first; robot speed research raises it later.**

## Power

- **Plan generation before demand catches up.** Steam is boilers plus engines from an offshore
  pump. Put up a big steam plant well before the nuclear plant's fuel runs low. The nuclear plant's
  fuel saver keeps the reactor hot with an empty fuel slot, which is normal.
- **Wood poles are cheap and easy to make.** The kit's medium poles go quickly, and wood poles give
  you as much early power distribution as you need.
- **Rebuilds can cut power.** A changed layout re-lays poles, and if the old ones go before the new
  ones stand, part of the base goes dark with its roboports. Get the new grid standing first (see
  "Building with the future in mind").

## Chests and buffers

- **Chests full of items are a problem because robots can't move that much easily.** Limit chests
  that take one item.
- **Overproduction is a mall problem.** Raw materials can't really be overproduced, so build plenty
  and don't worry about it. Spending raw materials on machines and buildings you don't need is what
  costs you, so limit the mall's outputs.
- **Leave a multi-item sink chest unlimited.** A slot limit can't stop a mixed belt from clogging:
  when the chest fills, the belt backs up with every item on it. The limit belongs at the makers,
  and the chest should keep as much room as it can so it never fills.
- **A chest at the head of a belt takes everything** (SHARED_SINK). Give science its own supply,
  and tap storage from another.
- **Mixed items work where every sink takes all of them.** One chest feeding one machine by one
  inserter works, and so does a products belt into one chest.
  - A single inserter from a multi-item chest straight into labs can't clog either. An inserter
    takes only what its sink accepts, but only when both the source and the sink touch that one
    inserter. Once it drops onto a belt, or hands on through another inserter, it no longer knows
    what the end sink needs, and the mix can jam.
  - On a belt into machines that each take only some items, the mix jams sooner or later (the CLOG
    warning).
- **Requesters and providers are a fixed budget** until late research. Count them before
  designing.

## Building with the future in mind

- **Some structures can be designed future-proof**, so they stay intact while the factories around
  them get rebuilt. Good candidates are the power tree and the main material supply. A main bus can
  be the spine for items, power and roboport coverage, with fixed poles and roboports along it, and
  factories off its side built and torn down without cutting the main flow. Other shapes come
  later: a city-block grid gives power and roboports but no item backbone without trains; a
  freeform base needs a hand-placed bus plus robot and power scaffolding.
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
- **Grow in steps.** Adding a consumer re-routes its whole net, so change one net at a time.

## Defense (on maps with biters)

- **Check early whether the map has biters.** If it does, defense has to grow with the base.
- **Landmines are the gold standard on Nauvis.** Turrets protect the early game. Once landmines are
  unlocked they are the best offensive and defensive weapon for the rest of the game.
- **Defensive mines:** keep laying them around the base into a thick minefield. They don't tie up
  robots.
- **Attacking a nest with landmines:**
  1. Prepare: about 50 spare landmines and 50 spare robots.
  2. Place all 50 at once, as close to the spawners and worms as possible.
  3. When the wave has landed, deconstruct the leftover landmine ghosts and keep the mines that
     stand.

  Why: the enemies attack the robots, and robots only trade well when they outnumber them, so they
  have to go in one big wave. After it, replacement robots trickle in one at a time and lose. A mine
  ghost left out there only keeps a robot and a mine tied up.
- **Before landmines, turrets go where the damage happens, not up against nests.** Clusters around
  the base, with the danger corners left alone. Yellow ammo doesn't stop big biters. A belt or
  inserter loop of ammo keeps turrets fed, with fast inserters on the magazine assemblers. Fortify
  before you put a roboport near a nest.

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
