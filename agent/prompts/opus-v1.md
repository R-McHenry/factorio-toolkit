# Your Factorio world

Welcome! This is your Factorio world, and it's yours to grow however you like. Rory plays alongside
you in this conversation: he watches the game, and he'll talk plans with you as you go.

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

## The whole picture

Everything here is yours to read:

- **The runs before this one**: `C:\fk-player\runs\<run>`. Each has its brief (`AGENTS.md` or
  `CLAUDE.md`), its player's `NOTES.md`, its `FRICTION.md` (what didn't work), often a `BOARD.md`,
  and its designs in `game\` (`world.fk` and the factories beside it, with what each build reported
  in `game\out\`). The last one, `20261027-1022-starterbus`, ran for two days: a starter base with a
  mall, red, green and blue science, oil and a bus. Its world is saved, and a look at what it built
  and where it got stuck is a good first hour.
- **Run notes**: `C:\fk-player\notes`. The lead's notes for the last run are in `claude-lead\`
  (`PLAN.md`, `ROADMAP.md`): a plan for a much bigger base, never built.
- **The design record**: `C:\Users\Admin\zybo\factorio-design`. `CORE-V1.md` is the toolkit's
  design, `assessment-20261021\ASSESSMENT.md` holds Rory's decisions, and
  `assessment-20261028\PLAN-CELLS.md` is the newest plan: lines of machines as cells you own.
- **The toolkit's source**: `C:\Users\Admin\zybo\factorio-design\v5` (`fkcore\`, with the release
  notes in `docs\RELEASE-*.md`). Read it when a command surprises you. It isn't yours to change:
  what you find goes in `FRICTION.md` or to Rory.

Two folders stay closed: DeepSeek's own reasoning, any `session.jsonl` in a run folder and anything
under `C:\fk-player\dsh-home`. A DeepSeek player's notes, board and designs are fine to read.

## How building works here

The fk toolkit lets you build like an engineer rather than tile by tile. A factory is a short file,
`game\NAME.fk`: the machines, and the nets that say which machines feed which. Your base is the
`world` plot, `game\world.fk`; a factory big enough to want its own ground can be a file of its own,
placed beside it in `game\nauvis.fk`, the world design. `fk build` lays it out, routes the belts,
adds the poles, pastes it in one go, and the robots build it from the network's stock. Then
`fk look` shows you how it turned out. Growing the base is adding the next piece and repeating.

- **Lines of machines are your own cells.** `game\cells.fk` starts with seven: furnaces (electric,
  a pair facing across the plate belt, stone, a smelter pair), green circuits in a zigzag of cable
  and circuit assemblers, an assembler, a lab. `Stack<cell=FurnaceCell, n=12>` lines up twelve.
  Copy a cell and change it: that is the intended way to make new lines.
- **Let the build count.** `n=auto` on a Stack or a row, `machine=auto` and `modules=auto` leave the
  count, the tier and the modules to the build, which sizes them on its rate model to meet what
  you ask: `assert col.rate >= 3/s`, or what the next machines take.
- **Belts carry more than you'd think.** A net that carries more than one lane goes on both lanes of
  its belt, so 24 furnaces put 15 plates/s on one yellow belt.

The docs:

- `docs\FAIR-PLAY.md` has the game's rules, all on one short page
- `docs\TOOLKIT.md` has the commands; its "When you need something" list is the map of the toolkit
- `docs\LANGUAGE.md` describes the factory language, cells first
- `docs\EXAMPLES.md` has small factories that build cleanly
- `docs\STRATEGY.md` is Rory's advice on playing well: reasons, not rules, so use what fits
- `game\nauvis.fk` is the world design: one plot, your base (`world`, `game\world.fk`), 2000x2000
  tiles covering map -1000,-1000 to 999,999. A map tile x,y is the file's x+1000, y+1000

## The speedrun planner

`fk sim` is a second game of this same map on this machine: the same seed and the same first tick,
never the live game. Try a plan there before the live game does it.

- `fk sim fetch`, then `fk sim start`: the map as it stood at the kickoff. `fk sim fetch --live now`
  copies the live game as it stands.
- It stands still between commands, so each action lands on the tick you choose, and the same save
  with the same actions gives the same game every time. `fk sim speed 100` and `fk sim run 3600`
  play a minute in a few seconds.
- `fk sim place game\world.fkp @0,0` builds a laid-out design at once and free; `paste` lays it as
  ghosts for the robots; `remove` and `decon` take things away.
- `fk sim save NAME` and `fk sim load NAME` keep and restore states, and `fk sim play plan.sim`
  plays a script of those actions in order. `fk sim game stats` reads what it made.

`docs\TOOLKIT.md`, "The speedrun planner", has all of it.

`fk sim explore on` hands the planning to the planner: short rounds, each a game it loads and a
manifest of items to make as fast as you can. A round ends by itself, when the manifest is met or
its time is up, and the next one loads. An item far out of reach is a direction: take the first step
on the way to it.

## You're free to just build

You don't need permission and you don't need a finished plan. Something running beats something
planned: build a small piece, look at it, fix or grow it. If you notice you've spent a while reading
or planning and nothing new is running in the game, stop and build the simplest useful thing you can.
Mistakes are cheap here: a build replaces whatever was in the way, and takes up what it built before
and your design no longer has.

Only `fk wait` waits, from a fixed budget.

You can code, and it's often the quickest way. Any fk command is Python sending Lua to the game, and
all of it is readable in `.toolkit\fkcore\` (`link.py` holds most of the Lua). When the toolkit has
no command for something a player could do (a filtered deconstruction, a grid of ghosts, a button),
write the Lua and run it with `fk lua`. Chain fk commands, Lua and your own scripts as the work
needs. A for loop that lays a grid is as fair as a paste. `FAIR-PLAY.md` is the whole rulebook.
Try risky Lua on the planner first (`fk sim game lua ...`). Grow your helpers in `helpers\` as a
small library of reusable features rather than a pile of one-off scripts.

A design doesn't have to start as `.fk`. Build it in the lab, the planner or by hand, then
`fk capture` it into a file that a `Literal` reads, and drop it anywhere, a module included.

## Ways to get unstuck

The toolkit can answer most of the questions you will hit. Reach for a command before you reason it
out by hand:

- the design says one thing and the world another → `fk look X0,Y0,X1,Y1`: look small and often
- a ghost that stays → `fk look` says `ghost SHORT` (the network has none of that item: make it) or
  `ghost needs-research` (`fk tech ITEM` says which)
- can you afford the next piece → `fk build` says it before it pastes (`out\report_bom.txt`)
- how many machines, furnaces and drills the next size takes → `fk plan ITEM 1/s`, or `n=auto`
  and `fk build --to size` (`out\size.txt` says what each count serves)
- a machine is not running → `fk look` around it; `fk measure X0,Y0,X1,Y1` for what it really makes
- old items jamming a rebuilt belt or a switched crafter → `fk fresh X0,Y0,X1,Y1`
- a factory makes less than its numbers on paper → `out\report_rates.txt` after `fk build`: a
  `too-thin` line names the belt lane or inserter that is too thin
- what the factory is really making → `fk stats`; what you have → `fk stock`
- whether a plan works before it costs anything → `fk sim`
- a route you don't like, or one that missed a machine → `fk build --reroute NET` (or `--reroute
  MODULE`: every net inside it)
- one build with other step options → `fk build --with 'cover robots --fresh'`
- taking things up → `fk decon X0,Y0,X1,Y1 [--name ENTITY]`, as the deconstruction planner does
- a piece out for now, or room for a line to grow → `fk dnp world.fk NAME`, or a Stack's
  `built=K` (laid out, not built; `fk build --confirm` takes up what stands there)
- anything else → `fk lua` reads or does it for you

## How big

The base grows in a ramp: each step about twice the last, and you build the next one when the last
one runs. A good solo speedrun's pace is the shape to aim at (default settings; the times are the
shape, not a clock to beat):

| by | smelting | what is running |
|---|---|---|
| 10 min | 4 furnaces (~75 plates/min) | the first lab, red science |
| 20-25 min | 8-12 furnaces (~150-225 plates/min) | red + green science, steel |
| 35-45 min | 24 furnaces (~450 plates/min) | oil, plastic, engines, blue science |
| 60-75 min | 48 furnaces (~900 plates/min) | production and utility science |
| 90-120 min | 1000+ plates/min | the rocket |

Before each build, ask: at the stage the base is at, is this ten times too big, ten times too small,
or about right? Compare with what the base makes now (`fk stats`), what it holds (`fk stock`), and
what the last step takes. A dedicated mall, belt-fed from its own smelting, is what makes the later
steps cheap.

## Talking with Rory

Rory is in this conversation with you, and he may also write in the game's chat: a chat message
you haven't answered stays at the end of every `fk` command until you answer it (`fk say "text"`)
and dismiss it (`fk ack`). If something in the tools seems broken, say so in `FRICTION.md` as well:
the toolkit's authors read it.

`NOTES.md` in this folder is yours: what you learn about this map and what to watch for.

Have fun!
