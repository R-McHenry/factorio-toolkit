# Your Factorio world

Welcome! This is your Factorio world, and it's yours to grow. Rory plays alongside you in this
conversation: he watches the game, and he'll talk plans with you as you go.

You're not only the player of this map. The whole project is open to you: the runs before this one,
the notes their players kept, the design record and the toolkit's own source. Use all of it to play
well, and tell Rory what you see.

## What you start with

A fresh map with a working start:

- a roboport at spawn with 50 construction and 50 logistic robots (speed and cargo upgrade 1)
- solar panels and accumulators, and a nuclear reactor that is already built and running (it idles at
  temperature when nothing needs power, which is normal). The reactor and its pole line are part of
  your base's design (`game\plant.fk`), so its power is on your grid from the first build
- six starter chests by the roboport: burner mining drills (they mine on coal, no power needed),
  roboports, assemblers, poles, logistic chests, belts, undergrounds, splitters, inserters, pipes,
  plates, ore, coal and stone. They are part of the design too (`game\kit.fk`): they stand where
  they stand, and the supplies in them are yours to take
- electronics and steam power already researched

Everything after that, you make: robots build what you plan, and the factory you design feeds itself.
Most recipes open through research: labs, science packs and `fk research`. `fk research` shows what
can be researched now, and `fk tech ITEM` what opens an item.

## What this run is for

The last run was the best so far by a wide margin: blue science at 4.9 game hours, 95 techs,
the first purple, yellow, nuclear power and rocket-silo tech, and no losses to biters. This run
refines that recipe, and it tests three habits the last run reached only late:

1. **Modules all the way down** (`docs\BUILDING.md`). `world.fk` places sealed modules and the
   trunks between their ports; every line lives inside a module, and every module builds clean in
   the lab first.
2. **Staying on the ramp** (`docs\STRATEGY.md`, "Growing"). Paste the step that comes next, and
   the one after once this one runs. Plan and lab as far ahead as you like.
3. **Stacks of cells, not rows** (`docs\BUILDING.md`). `MinerRow` is still the drill line.

These aren't rules: the game's rules are all in `docs\FAIR-PLAY.md`. But testing them is the
point of the run, so follow them in spirit and don't let them slide. When one doesn't fit, say so
in `NOTES.md` and to Rory. Every round's message ends with a reminder of them (`REMINDER.md`,
yours to edit with Rory).

## What carries over

From the last three runs, in their players' words and numbers:

- **Scaffolding first:** a pinned roboport grid on L-inf squares with ore at the corners, medium
  poles, one hub for every logistic chest, then the belt mall and the auto mall. The last run's
  first 550k ticks are the template (`docs\BUILDING.md`, "Bootstrap").
- **Land mines before ~2M ticks:** military science right after green, explosives from the first
  chemical plant, rings around the hotspots, waves of mine ghosts against nests.
- **Belts between modules, requesters only in the hub.** The run that never built a belt between
  plots made 12 techs in 6 hours.
- **Sealed regions, labbed alone.** Three of the last run's routed on the first try.
- **The planner for anything new and risky.** Both blocks the last run tried there went in live
  without rework; the fluid blocks that cost the most never went through it.
- **A maker that waits on its own item is a deadlock;** lay the maker of every short item first;
  robots never fuel what they build; every roboport move strands its robots; never change a full
  chest's `limit=` casually; never move items with Lua.
- **A new consumer gets its own branch:** adding it to a main net re-lays the main.

And three habits for what kept going wrong across the long runs:

- **Keep a long research queue.** Queue several techs whenever you touch research, and check the
  queue before any long stretch. Three long runs lost hours to idle labs, the last one 8.5 game
  hours. The research line every command ends with says `QUEUE EMPTY after this` in time.
- **Build the big smelting columns when blue starts.** The last run had nearly a rocket's worth
  of parts and stopped on plates (~80 iron/min against ~420) and concrete.
- **Build the makers of roboports, poles and robots next to their inputs.** Robots became the
  wall once the base was big; keep their trips short and carry flows by belt.

## Start in the lab

Rory wants this run to open with planning: a base whose first stages were laid out, labbed and
timed on the planner grows past a hurried one within the first hours.

- **Read what the last run learned.** `C:\fk-player\runs\20261030-2352-opus` played this toolkit's
  2.1 line for two days: a booted base, a mall, oil, and science up to production and utility
  packs, with the rocket silo next in its queue. Its
  `NOTES.md` (the lessons at the top, and the log) and `FRICTION.md` say what worked and what cost
  it hours. Its `game\` has designs that built: `labarea.fk`, `ldsblock.fk`, `greenblock.fk`,
  `blueline.fk`, `c4plant.fk` and its `cells.fk`. Its big mistake was a flat world of 660
  instances that took minutes a build and pasted all or nothing.
- **Write the ramp as stages.** `fk stage insert` one stage per step of the ramp below, each with
  its goal, its rates and the test that says it runs. The first four or five are enough to start.
- **Design each stage's modules from the examples.** `docs\EXAMPLES.md` (the five pieces at the
  top are the current language), `game\cells.fk` for lines, `game\routing.fk` for waypoints,
  merges, splits and pumps. Copy, rename, change.
- **Lab every module.** `fk lab NAME`, let it run, `fk lab NAME --measure 60`, and compare with
  `fk rates`. Rory watches the lab; tell him where it stands.
- **Play the opening on the planner.** `fk sim fetch`, `fk sim start`, then `paste` the first
  stages as ghosts and `run` them at speed: how long the robots take, where the kit runs short, when
  each stage starts running. Fix the plan there, where it's free.

Then paste stage 1 in the live game and keep going: lab the next stage while the robots build this
one.

## The whole picture

Everything here is yours to read:

- **The runs before this one**: `C:\fk-player\runs\<run>`. Each has its brief (`AGENTS.md` or
  `CLAUDE.md`), its player's `NOTES.md`, its `FRICTION.md`, and its designs in `game\` (with what
  each build reported in `game\out\`).
- **The design record**: `C:\Users\Admin\zybo\factorio-design`. `CORE-V1.md` is the toolkit's
  design, `assessment-20261021\ASSESSMENT.md` holds Rory's decisions, and
  `assessment-20261101\PLAN-3.0.md` is the newest plan: the build as steps you type, one net or
  one region at a time.
- **The toolkit's source**: `C:\Users\Admin\zybo\factorio-design\v5` (`fkcore\`, with the release
  notes in `docs\RELEASE-*.md`). Read it when a command surprises you. It isn't yours to change:
  what you find goes in `FRICTION.md` or to Rory.

Two folders stay closed: DeepSeek's own reasoning, any `session.jsonl` in a run folder and anything
under `C:\fk-player\dsh-home`. A DeepSeek player's notes, board and designs are fine to read.

## How building works here

A factory is a short file, `game\NAME.fk`: the machines, and the nets that say which machines feed
which. Your base is the `world` plot, `game\world.fk`, placed by the world design `game\nauvis.fk`
(one plot, 2000x2000 tiles covering map -1000,-1000 to 999,999; a map tile x,y is the file's
x+1000, y+1000).

- **A module is a factory with ports.** `module Smelt size 30x20 { port ... }`: its belts stay in
  its frame, and the nets in `world.fk` run from one module's port to the next.
- **Lines are Stacks of cells.** `game\cells.fk` has furnaces (electric, a pair across the plate
  belt, stone, a smelter pair), green circuits, assemblers, labs. `Stack<cell=FurnacePair, n=12>`
  lines up twelve. Copy a cell and change it to make a new line.
- **Let the build count.** `n=auto`, `machine=auto` and `modules=auto` leave the count, tier and
  modules to the build, sized on its rate model to meet `assert col.rate >= 3/s` or what the next
  machines take.
- **Belts carry more than you'd think.** A net that carries more than one lane goes on both lanes,
  so 24 furnaces put 15 plates/s on one yellow belt.

The build is a script of steps (`game\nauvis.build.fkb`), and each step is also a command:

- `fk build` runs the script in the background; `fk status` shows the nets as the router lands
  them, the unrouted ones with their reasons. Routes are kept between builds, so a second build
  only lays what changed. Keep working while it runs; `fk wait build` is the budgeted way to wait
  for its end when there is truly nothing else to do.
- A build that would replace something changed in the game (a pump, an upgraded inserter, a
  filter) stops before the paste and lists each one in `out\diff.txt`. Put the ones to keep into
  the design, then `fk build --yes` pastes over the rest.
- `fk route NET` lays one net again, every other route kept; `fk route --try X,Y X,Y` asks how a
  belt would go; `fk seed NET 'splitter X,Y S'` pins a piece and the router lays the rest through it;
  `fk hold NET` freezes one.
- A net that can't find its way goes through a piece from `game\routing.fk` (`Waypoint`, `Split`,
  `InlinePump`): `net gear: gears -> wp -> red`.
- `route --area X0,Y0,X1,Y1` in the script (or `fk build --with "route --area ..."`) reworks one
  area and leaves every other route as it stands.

One thing to know: the world build still lays a sealed module's inside belts itself (compiling
each module once is planned, not shipped). Kept routes make the second build of a module fast, and
the lab tells you first whether it routes at all.

The docs:

- `docs\FAIR-PLAY.md`: the game's rules, one short page
- `docs\BUILDING.md`: how the base is laid out (backbone, hub, producers, bus, consumers), belts
  versus chests, modules, cells and the bootstrap
- `docs\TOOLKIT.md`: the commands; its "When you need something" list is the map of the toolkit
- `docs\LANGUAGE.md`: the factory language, cells and modules first
- `docs\EXAMPLES.md`: small factories that build cleanly
- `docs\STRATEGY.md`: Rory's advice on playing well, with the reasons

## The speedrun planner

`fk sim` is a second game of this same map on this machine: the same seed and the same first tick,
never the live game. Try a plan there before the live game does it.

- `fk sim fetch`, then `fk sim start`: the map as it stood at the kickoff. `fk sim fetch --live now`
  copies the live game as it stands.
- It stands still between commands, so each action lands on the tick you choose, and the same save
  with the same actions gives the same game every time. `fk sim speed 100` and `fk sim run 3600`
  play a minute in a few seconds.
- `fk sim paste game\world.fkp @-1000,-1000` lays a laid-out design as ghosts for the robots (a
  `.fkp` is in the design's own tiles, so `world.fkp` goes at the plot's corner); `place` builds it
  at once and free (for a quick look, not for timing); `remove` and `decon` take things away.
- `fk sim save NAME` and `fk sim load NAME` keep and restore states, and `fk sim play plan.sim`
  plays a script of those actions in order. `fk sim game stats` reads what it made.

`docs\TOOLKIT.md`, "The speedrun planner", has all of it, and explore mode (`fk sim explore on`):
short rounds, each with a manifest of items to make as fast as you can.

## The ramp

The base grows in a ramp: each step about twice the last, and you paste the next one when the last
one runs. A good solo speedrun's pace is the shape (default settings; the times are the shape, not
a clock to beat):

| by | smelting | what is running |
|---|---|---|
| 10 min | 4 furnaces (~75 plates/min) | the first lab, red science |
| 20-25 min | 8-12 furnaces (~150-225 plates/min) | red + green science, steel |
| 35-45 min | 24 furnaces (~450 plates/min) | oil, plastic, engines, blue science |
| 60-75 min | 48 furnaces (~900 plates/min) | production and utility science |
| 90-120 min | 1000+ plates/min | the rocket |

Before each paste, ask: at the row the base is on, is this ten times too big, ten times too small,
or about right? Compare with what the base makes now (`fk stats`), what it holds (`fk stock`), and
what the last step takes. A dedicated mall, belt-fed from its own smelting, is what makes the later
steps cheap.

## Building freely

You don't need permission and you don't need a finished plan for every step. Inside the rules,
something running beats something planned: once the opening is planned, paste a stage, look at
it, fix or grow it. Mistakes are cheap: a build replaces whatever was in the way, and takes up
what it built before and your design no longer has.

Only `fk wait` waits, from a fixed budget: `fk wait 90s`, `fk wait built AREA`, `fk wait build`,
and `fk wait 2m -- COMMAND` for a command that needs a time cap. Run long things in the
background and keep working.

You can code, and it's often the quickest way. Any fk command is Python sending Lua to the game, and
all of it is readable in `.toolkit\fkcore\` (`link.py` holds most of the Lua). When the toolkit has
no command for something a player could do (a filtered deconstruction, a grid of ghosts, a button),
write the Lua and run it with `fk lua`. `FAIR-PLAY.md` is the whole rulebook. Try risky Lua on the
planner first (`fk sim game lua ...`). Grow your helpers in `helpers\` as a small library of
reusable features rather than a pile of one-off scripts.

A design doesn't have to start as `.fk`. Build it in the lab, the planner or by hand, then
`fk capture` it into a file that a `Literal` reads, and drop it inside a module.

## Ways to get unstuck

- the design says one thing and the world another → `fk look X0,Y0,X1,Y1`: look small and often
- a ghost that stays → `fk look` says `ghost SHORT` (make that item) or `ghost needs-research`
  (`fk tech ITEM` says which)
- can you afford the next piece → `out\report_bom.txt` after a build
- how many machines for a rate → `fk plan ITEM 1/s`, or `n=auto` and `out\size.txt`
- a machine is not running → `fk look` around it; `fk measure X0,Y0,X1,Y1` for what it really makes
- old items jamming a rebuilt belt or a switched crafter → `fk fresh X0,Y0,X1,Y1`
- a factory makes less than its numbers on paper → `out\report_rates.txt`: a `too-thin` line names
  the lane or inserter that is too thin
- how the whole base is doing → `fk stats`: research, capital and how much of it works, what is
  made and used, power, machines by state, in one report; what you have → `fk stock`
- a net that won't route → `fk status NET` for the reason, then `fk route --try`, a seed, or a
  routing piece; never "build everything again"
- whether a plan works before it costs anything → the lab and `fk sim`
- taking things up → `fk decon X0,Y0,X1,Y1 [--name ENTITY]`
- a piece out for now, or room for a line to grow → `fk dnp world.fk NAME`, or a Stack's `built=K`
- anything else → `fk lua` reads or does it for you

## Talking with Rory

Rory is in this conversation with you, and he may also write in the game's chat: a chat message
you haven't answered stays at the end of every `fk` command until you answer it (`fk say "text"`)
and dismiss it (`fk ack`). If something in the tools seems broken, say so in `FRICTION.md` as well:
the toolkit's authors read it.

`NOTES.md` in this folder is yours: what you learn about this map and what to watch for.

Have fun!
