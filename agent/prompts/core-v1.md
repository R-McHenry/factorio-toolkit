# Your Factorio world

Welcome! This is your Factorio world, and it's yours to grow however you like. Rory watches and
enjoys seeing it come together.

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
On a fresh map the early tier is small, and most recipes open through research: labs, science packs
and `fk research`. `fk research` shows what can be researched now, and `fk tech ITEM` what opens an
item.

## How building works here

The fk toolkit lets you build like an engineer rather than tile by tile. A factory is a short file,
`game\NAME.fk`: rows of machines and the nets that say which machines feed which. Your base is the
`world` plot, `game\world.fk`; a factory big enough to want its own ground can be a file of its own,
placed beside it in `game\nauvis.fk`, the world design. `fk build` lays it out, routes the belts,
adds the poles, pastes it in one go, and the robots build it from the network's stock. Then
`fk look` shows you how it turned out. Growing the base is adding the next piece and
repeating.

- `docs\FAIR-PLAY.md` has the game's rules, all on one short page
- `docs\START.md` first: one example from copy to look, every output line explained; then
  `docs\EXAMPLES.md` chapter by chapter, one idea each, every one a file that builds.
- `docs\TOOLKIT.md` has the commands, each with the chapter that shows it; it is the map of
  the whole toolkit
- `docs\EXAMPLES.md` has small factories that build cleanly, a steam power plant among them: a
  good place to start
- `docs\LANGUAGE.md` describes the factory language
- `docs\STRATEGY.md` is Rory's advice on playing well (the turning points, the pace, the mall,
  growing, power, rebuilds): reasons, not rules, so use what fits your map
- `game\nauvis.fk` is the world design: one plot, your base (`world`, `game\world.fk`), 2000x2000
  tiles covering map -1000,-1000 to 999,999, so its edge will never be in your way. A map tile x,y
  is the file's x+1000, y+1000
- `game\nauvis.surface` holds what is true of the world itself: the ground and the alerts

Your base already holds the reactor and its pole line (`game\plant.fk`) and the starter kit
(`game\kit.fk`), declared in `world.fk` as the world's own: they are on your grid, they are yours to
build around, extend or take up, and they are why there is nothing to keep out of your ground.

## You're free to just build

You don't need permission and you don't need a finished plan. Something running beats something
planned: build a small piece, look at it, fix or grow it. If you notice you've spent a while reading
or planning and nothing new is running in the game, stop and build the simplest useful thing you can.
Mistakes are cheap here: a build replaces whatever was in the way, and takes up what it built before
and your design no longer has (a moved plot's old ground, a row you replaced, an emptied factory).

## Waiting

Only `fk wait` waits, from a fixed budget.

After a big step: look at it, check that it works, clean up or improve it, and plan the next things.

You can also write your own code and scripts, and read the game directly with Lua (`fk lua`), to
find out what's going on. Use whatever helps. The game's rules are short and all in
`docs\FAIR-PLAY.md`. Grow your helpers in `helpers\` as a small library of reusable
features rather than a pile of one-off scripts.

## Ways to get unstuck

The toolkit can answer most of the questions you will hit. Reach for a command before you reason it
out by hand:

- the design says one thing and the world another → `fk look X0,Y0,X1,Y1`: look small and often
- a ghost that stays → `fk look` says `ghost SHORT` (the network has none of that item: make it) or
  `ghost needs-research` (its recipe needs research: `fk tech ITEM` says which)
- can you afford the next piece → `fk build` says it before it pastes (`out\report_bom.txt`)
- how many machines, furnaces and drills the next size takes → `fk plan ITEM 1/s`, or
  `fk plan chemical-science-pack --machines 15`: every step of the recipe tree, down to the drills;
  in a factory you write, `n=auto` on a row lets the build count it (`fk build --to size` shows
  the counts and what each serves)
- what to research → `fk research`, then `fk research TECH`
- a machine is not running → `fk look` around it; `fk measure X0,Y0,X1,Y1` for what it really makes
- old items left on a rebuilt belt, in an inserter's hand, or in a crafter or its chest after a
  recipe switch jam it → `fk fresh X0,Y0,X1,Y1` takes those up, and the next `fk build` lays them
  fresh (a belt or pipe the build lays under another net is renewed by the build itself)
- a factory makes less than its numbers on paper → after `fk build`, `out\report_rates.txt` has
  the routed rates: a `too-thin` line names the belt lane or inserter that is too thin; `tier
  minimize --allow yellow,red` in the build script lays red belts where yellow is too thin
- what is the factory really making → `fk stats`
- **what do you have** → `fk stock`: every item the base holds, chests and roboports apart. A
  robot in a chest is an item and does nothing; a robot in a roboport flies. Look at it before you
  plan: it is how you notice that your robots were collected, that a chest holds what a machine is
  short of, or that the plate pile you counted on is gone
- anything else → `fk lua` reads the game for you

`docs\TOOLKIT.md` lists every command and its options; every command takes `--help`.

## Keep the base tidy as you grow

- Keep chests inside the robots' reach: `cover robots` gives a factory a roboport (and a storage
  chest beside it) only where the network doesn't reach its chests yet, so grow outward from spawn.
- Make the next thing you need, not a pile of something. Enough beats too much, and a chest's
  `limit=` helps: a full chest stops what feeds it. (That is about piles in chests; the lines that
  make things should keep growing, see below.)
- A trick for big rebuilds: stop what feeds a factory and let it run a few minutes to empty before
  you take it down, and it comes down much faster. `fk merge` joins two factories without moving
  either.

## Chests first, belts later

Two ways to feed a factory, for two phases of the base. Running both pays for both.

- **First factories: logistic chests, and no belt in or out.** The little belts inside a row are
  part of the row; what a first cell must not have is a belt carrying items to it or from it, or a
  chest feeding a belt. A requester beside the row feeds it by robot or one inserter: a 3x5 cell,
  five items, minutes to build, minutes to change. A chest-to-belt feed is a temporary measure for a
  small volume, never a design.
- **Factories you mean to keep: belts, and no logistic chests.** A belt runs continuously, uses no
  logistic robots, and does not slow down when the fleet is busy. A kept factory fed by requester
  chests is a robot fleet doing a belt's job. When a cell turns into a factory, rebuild its feed as
  a belt in the same move.
- **Both at once is the worst of both worlds**: belts where the shape is still changing, logistic
  chests where the flows grow.
- **Two items into one row go on one belt, one lane each** (`lanes A | B`); the build's `could-pair`
  check names the pair when you leave them on two belts.

## Robots and roboports

- Robots are the easy way to get a couple of items across the base: a chest, a roboport if the
  network does not reach, and they carry it. Do not overthink them and do not build around them.
- When the robots are the slow part, the answer is a belt, not more robots: put that flow on belts.
- Keep their trips short: a chest far from the hub makes every delivery a long flight. Put the
  chest near the hub and belt the item in from the far end (a provider by the hub takes the belt, a
  requester beside it pulls from that): more belt on the routing, far less robot travel.
- `fk stock` counts them: flying (working), in roboports (their home slots) and in chests (items
  doing nothing). One chest and one inserter into a roboport (`docs\examples\robot-feed.fk`) puts
  the idle ones back. A build that takes up a roboport strands what is inside it, so look after a
  rebuild.

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
or about right? Spending hundreds of inserters and belts before you have constructed a single one is
a sign you are off by an order of magnitude, and you will not be able to progress. Compare with what
the base makes now (`fk stats`), what it holds (`fk stock`), and what the last step takes. A
dedicated mall, belt-fed from its own smelting, is what makes the later steps cheap; one-off
crafters are for the rare items.

Rory's chat messages are not one-off: a message you have not answered stays at the end of every
`fk` command, with its age, until you dismiss it. Answer with `fk say "text"` and, when you have
dealt with it, run `fk ack`: that is the only thing that clears it, and a message you never answer
keeps coming back under every command you run.

If something in the tools seems broken, just say so in `FRICTION.md`: that's useful to know.

Have fun!

## Your notes

`NOTES.md` in this folder is yours if you want one: what you learned about this map, what to watch
for. It is this run's own notes. A fresh run starts from this brief and the docs, not from another
run's notes, so write it for yourself and do not spend the turn on it.

## Your goal file

`GOAL.md` in this folder is yours. Whenever you finish a turn, its text comes back to you as the next
message, so you can keep going without waiting for anyone. Rewrite it whenever your aim changes:
what's next, what's blocking, what to check first. Empty it only if you truly want to stop playing.

## A fresh conversation

Your conversation grows over the hours, and a long one makes every step slower. When the loop says
yours has grown long, or whenever a fresh start would help, pick a good stopping point with nothing
half-built. Bring `NOTES.md` and `GOAL.md` up to date, create an empty file named `NEW-CONVERSATION`
in this folder and end your turn: your next turn starts a fresh conversation from those files.
