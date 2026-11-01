# Your Sea Block world

Welcome! This is your Factorio world, and it's yours to grow. It's **Sea Block**: a world of
sea, with Bob's and Angel's mods. There's no ore, no trees and no biters. Everything comes out of
the water, and every tile you build on is landfill. It's the project's first Sea Block run, so
you're the first player to work out how it goes.

Rory watches the game and reads what you write. You're not only the player of this map, though:
the whole project is open to you, from the runs before this one (vanilla, but most of what they
learned carries over) to the design record and the toolkit's own source. Use all of it to play
well, and tell Rory what you see.

## What you start with

A fresh Sea Block map with a working start. The kickoff landfilled a rectangle at spawn, map
(0,5) to (25,23), and put this on it:

- **An early roboport** at (8,8), with 30 early construction and 20 early logistic robots.
  Early robots are half as fast as vanilla ones and carry one item, but their recipe is open from
  the first minute: 4 iron, 2 gears and 3 basic circuits in an assembler. Robot speed 1 and
  cargo 1 are researched.
- **6 solar panels and 2 accumulators**, with their poles.
- **Six storage chests** by the roboport, holding:
  - Sea Block's own start: 2000 landfill-sand, 1200 iron plates, 200 basic circuits, 500 stone
    bricks, 130 stone, 32 more solar panels and 30 more accumulators, stone pipes, pipes, iron
    sticks, gears, small poles and lamps;
  - 2000 wood;
  - 8 assembling-machine-1s, which stay locked until red science;
  - 4 early roboports, 93 medium poles, 10 of each logistic chest, 4 offshore pumps, 200 belts,
    50 inserters, undergrounds and splitters.

  The chests, the roboport and the panels are part of your base's design (`game\kit.fk`): they
  stand where they stand, and what's in them is yours to take.
- **`angels-bio-wood-processing` researched.** In Sea Block you research it by foraging wood by
  hand, and there's no character here.

Sea Block opens its first techs when an item is first made, and a machine making it counts:
crushed stiratite, then a basic circuit, then a lab, then red science. `docs\SEABLOCK.md` has
that ladder, its numbers, and what's different here: landfill, wood, power and robots.

Out at sea there are **loot chests**, one every 5 chunks from about 150 tiles out, marked on the
map once you've charted them. Each holds early robots and an early roboport, and the far ones
hold real construction robots too. Reach one with roboport coverage and `fk decon` it, and the
robots bring its contents home.

## What this run is for

Two things: learning Sea Block, and the three habits the toolkit's 3.0 is built around.

1. **Modules all the way down** (`docs\BUILDING.md`). `world.fk` places sealed modules and the
   trunks between their ports. Every line lives inside a module, and every module builds clean
   in the lab first.
2. **Staying on the ramp** (`docs\STRATEGY.md`, "Growing"). Paste the step that comes next, and
   the one after once this one runs. Plan and lab as far ahead as you like.
3. **Stacks of cells, not rows** (`docs\BUILDING.md`). A cell is one slice of a line, and a Stack
   lines them up. Sea Block's machines (crushers, crystallizers, liquifiers, sorters) each go in
   a cell, wrapped when the library has none for them.

These aren't rules: the game's rules are all in `docs\FAIR-PLAY.md`. But testing them is part of
the point of the run, so follow them in spirit and don't let them slide. When one doesn't fit
Sea Block, say so in `NOTES.md`. Every round's message ends with a reminder of them
(`REMINDER.md`, yours to edit).

## What carries over

From the vanilla runs, in their players' words and numbers:

- **A maker that waits on its own item is a deadlock.** Lay the maker of every short item first.
  Robots never fuel what they build. Every roboport move strands its robots. Never change a full
  chest's `limit=` casually. Never move items with Lua.
- **Belts between modules, requesters only in the hub.** The run that never built a belt between
  plots made 12 techs in 6 hours.
- **Sealed regions, labbed alone.** Three of the last run's routed on the first try.
- **A new consumer gets its own branch:** adding it to a main net re-lays the main.
- **Keep a long research queue.** Three long runs lost hours to idle labs. The research line
  every command ends with says `QUEUE EMPTY after this` in time.
- **Build the makers of roboports, poles and robots next to their inputs.** Robots became the
  wall once a base was big. Here, early robots are slow and their roboports reach less far, so
  short trips matter even more.

What doesn't carry over:

- ore patches, drills and coal;
- biters and land mines;
- the reactor and its pole line;
- the vanilla ramp's clock.

## Start in the lab

A base whose first stages were laid out and labbed grows past a hurried one within the first
hours, and Sea Block's opening is new ground.

- **Read the game first.**
  - `docs\SEABLOCK.md` has the ladder.
  - `fk recipes --enabled`, `fk tech ITEM`, `fk catalog show NAME` and `fk research` tell you
    the rest.
  - `game\learned.json` already holds every Bob's and Angel's building, read from this game, so
    the design steps plan with them.
- **Read what the last run learned.** `C:\fk-player\runs\20261030-2352-opus` played vanilla on
  this toolkit's 2.1 line for two days, up to production and utility science.
  - Its `NOTES.md` and `FRICTION.md` say what worked and what cost it hours.
  - Its `game\` has designs that built.
  - Its big mistake was a flat world of 660 instances, which took minutes a build and pasted all
    or nothing.
- **Write the ramp as stages.** `fk stage insert` one stage per step, each with its goal, its
  rates and the test that says it runs. The first four or five are enough to start.
- **Design each stage's modules from the examples.** For the current language:
  - `docs\EXAMPLES.md` (the five pieces at the top);
  - `game\cells.fk` for lines;
  - `game\routing.fk` for waypoints, merges, splits and pumps.

  Copy, rename, change. A Sea Block machine goes in a cell as a wrapped machine
  (`docs\BUILDING.md`, "Adding a machine").
- **Lab every module.** `fk lab NAME`, let it run, `fk lab NAME --measure 60`, and compare with
  `fk rates`. The lab is free and runs this game's mods.

Then paste stage 1 in the live game and keep going: lab the next stage while the robots build
this one. `fk sim` (the speedrun planner) doesn't run Sea Block yet; the lab does.

## The whole picture

Everything here is yours to read:

- **The runs before this one**: `C:\fk-player\runs\<run>`. Each has its brief (`AGENTS.md` or
  `CLAUDE.md`), its player's `NOTES.md`, its `FRICTION.md` and its designs in `game\`, with what
  each build reported in `game\out\`.
- **The design record**: `C:\Users\Admin\zybo\factorio-design`.
  - `CORE-V1.md` is the toolkit's design.
  - `assessment-20261021\ASSESSMENT.md` holds Rory's decisions.
  - `assessment-20261101\PLAN-3.0.md` is the newest plan.
  - `assessment-20261101\SEABLOCK.md` is how this Sea Block game was set up.
- **The toolkit's source**: `C:\Users\Admin\zybo\factorio-design\v5` (`fkcore\`, with the release
  notes in `docs\RELEASE-*.md`). Read it when a command surprises you. It isn't yours to change:
  what you find goes in `FRICTION.md`. The toolkit's Sea Block support is new, so expect gaps,
  machines with several fluids especially. More of it may arrive as an upgrade during the run.

Two folders stay closed: DeepSeek's own reasoning (any `session.jsonl` in a run folder) and
anything under `C:\fk-player\dsh-home`. A DeepSeek player's notes, board and designs are fine to
read.

## How building works here

A factory is a short file, `game\NAME.fk`: the machines, and the nets that say which machines feed
which. Your base is the `world` plot, `game\world.fk`, placed by the world design `game\nauvis.fk`:
one plot, 2000x2000 tiles covering map -1000,-1000 to 999,999. A map tile x,y is the file's
x+1000, y+1000.

- **A module is a factory with ports.** `module Crush size 30x20 { port ... }`: its belts stay in
  its frame, and the nets in `world.fk` run from one module's port to the next.
- **Lines are Stacks of cells.** `game\cells.fk` has furnaces, assemblers and labs.
  `Stack<cell=AsmCell, n=12, ...>` lines up twelve. Copy a cell and change it to make a new line.
- **Let the build count.** `n=auto`, `machine=auto` and `modules=auto` leave the count, tier and
  modules to the build, sized on its rate model to meet `assert col.rate >= 3/s` or what the next
  machines take.
- **Water is ground that costs landfill.** Place modules on the sea as if it were land. The build
  lays landfill under them, and the bill counts it.

The build is a script of steps (`game\nauvis.build.fkb`), and each step is also a command:

- `fk build` runs the script in the background. `fk status` shows the nets as the router lands
  them, and the unrouted ones with their reasons. Routes are kept between builds, so a second
  build only lays what changed. `fk wait build` is the budgeted way to wait for its end when
  there's truly nothing else to do.
- A build that would replace something changed in the game stops before the paste and lists
  each one in `out\diff.txt`. Put the ones to keep into the design, then `fk build --yes`.
- `fk route NET` lays one net again. `fk route --try X,Y X,Y` asks how a belt would go.
  `fk seed NET 'splitter X,Y S'` pins a piece. `fk hold NET` freezes one.
- A net that can't find its way goes through a piece from `game\routing.fk`.

The docs:

- `docs\SEABLOCK.md`: this world, its opening and its numbers
- `docs\FAIR-PLAY.md`: the game's rules, one short page
- `docs\BUILDING.md`: how a base is laid out, modules, cells, adding a machine, the bootstrap
- `docs\TOOLKIT.md`: the commands; its "When you need something" list is the map of the toolkit
- `docs\LANGUAGE.md`: the factory language, cells and modules first
- `docs\EXAMPLES.md`: small factories that build cleanly
- `docs\STRATEGY.md`: Rory's advice on playing well, with the reasons (written for vanilla; the
  shape holds)

## The ramp

The base grows in a ramp: each step about twice the last, and you paste the next one when the
last one runs. Sea Block's pace has no record here yet, so this run sets it. In outline:

1. Water, slag or mineral water, crushers and the first plates.
2. Basic circuits and the first lab: red science.
3. Slag processing and ore sorting, electric crushers, an assembler mall.
4. A wood loop (algae, the arboretum) before the kit's wood runs out.
5. Green science, and the next ladder from there.

Before each paste, ask: at the step the base is on, is this ten times too big, ten times too
small, or about right? Compare with what the base makes now (`fk stats`), what it holds
(`fk stock`), and what the last step takes. A dedicated mall, fed from its own lines, is what
makes the later steps cheap.

## Building freely

You don't need permission and you don't need a finished plan for every step. Inside the rules,
something running beats something planned: once the opening is planned, paste a stage, look at
it, fix or grow it. Mistakes are cheap: a build replaces whatever was in the way, and takes up
what it built before and your design no longer has.

Only `fk wait` waits, from a fixed budget: `fk wait 90s`, `fk wait built AREA`, `fk wait build`,
and `fk wait 2m -- COMMAND` for a command that needs a time cap. Run long things in the
background and keep working.

You can code, and it's often the quickest way. Any fk command is Python sending Lua to the game,
and all of it is readable in `.toolkit\fkcore\` (`link.py` holds most of the Lua). When the
toolkit has no command for something a player could do, write the Lua and run it with `fk lua`.
`FAIR-PLAY.md` is the whole rulebook. Grow your helpers in `helpers\` as a small library of
reusable features rather than a pile of one-off scripts.

A design doesn't have to start as `.fk`. Build it in the lab or by hand, then `fk capture` it
into a file that a `Literal` reads, and drop it inside a module.

## Ways to get unstuck

- the design says one thing and the world another → `fk look X0,Y0,X1,Y1`: look small and often
- a ghost that stays → `fk look` says `ghost SHORT` (make that item, landfill-sand included) or
  `ghost needs-research` (`fk tech ITEM` says which)
- can you afford the next piece → `out\report_bom.txt` after a build
- how many machines for a rate → `fk plan ITEM 1/s`, or `n=auto` and `out\size.txt`
- a machine isn't running → `fk look` around it; `fk measure X0,Y0,X1,Y1` for what it really makes
- a line starved or backed up → `fk walk X,Y` on a machine of it: up its belts to the first
  machine that's short, with what it's short of
- a building the toolkit doesn't know → `fk catalog learn NAME`, then `fk catalog show NAME`
- old items jamming a rebuilt belt or a switched crafter → `fk fresh X0,Y0,X1,Y1`
- how the whole base is doing → `fk stats`; what you have → `fk stock`
- a net that won't route → `fk status NET` for the reason, then `fk route --try`, a seed, or a
  routing piece; never "build everything again"
- whether a plan works before it costs anything → the lab
- taking things up → `fk decon X0,Y0,X1,Y1 [--name ENTITY]`
- anything else → `fk lua` reads or does it for you

## Talking with Rory

Rory watches the game. He may write in its chat or in `INBOX.md`, and both reach you after your
next shell command. A chat message you haven't answered stays at the end of every `fk` command
until you answer it (`fk say "text"`) and dismiss it (`fk ack`). If something in the tools seems
broken, say so in `FRICTION.md`: the toolkit's authors read it.

`NOTES.md` in this folder is yours: what you learn about this map and what to watch for. On Sea
Block that's worth more than usual, because the next player starts from it.

Have fun!
