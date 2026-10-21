# Your Factorio world

Welcome! This is your Factorio world, and it's yours to grow however you like. Rory watches and
enjoys seeing it come together.

## What you start with

A fresh map with a working start:

- a roboport at spawn with 50 construction and 50 logistic robots (speed and cargo upgrade 1)
- solar panels and accumulators, and a nuclear plant that is already built and running (it idles at
  temperature when nothing needs power, which is normal)
- six starter chests by the roboport: roboports, assemblers, poles, logistic chests, belts,
  undergrounds, splitters, inserters, pipes, plates, ore, coal and stone
- electronics and steam power already researched

Everything after that, you make: robots build what you plan, and the factory you design feeds itself.
On a fresh map the early tier is small, and most recipes open through research: labs, science packs
and `fk research`. `fk research` shows what can be researched now, and `fk tech ITEM` what opens an
item.

## How building works here

The fk toolkit lets you build like an engineer rather than tile by tile. A factory is a short file,
`game\NAME.fk`: rows of machines and the nets that say which machines feed which. `fk build` lays it
out, routes the belts, adds the poles, pastes it in one go, and the robots build it from the network's
stock. Then `fk look` shows you how it turned out. Growing the base is adding the next piece and
repeating.

- `docs\TOOLKIT.md` has the commands — read the "When you need something" list once, it is the map of
  the whole toolkit
- `docs\EXAMPLES.md` has small factories that build cleanly, a steam power plant among them: a
  good place to start
- `docs\LANGUAGE.md` describes the factory language
- `game\nauvis.surface` says where each factory goes on the map

The nuclear plant is already in your surface file (`plant`) and the starter kit is a claim: build
around them.

## You're free to just build

You don't need permission and you don't need a finished plan. Something running beats something
planned: build a small piece, look at it, fix or grow it. If you notice you've spent a while reading
or planning and nothing new is running in the game, stop and build the simplest useful thing you can.
Mistakes are cheap here: a build replaces whatever was in the way, and takes up what it built before
and your design no longer has (a moved plot's old ground, a row you replaced, an emptied factory).

You can also write your own code and scripts, and read the game directly with Lua (`fk lua`), to
find out what's going on. Use whatever helps.

## Ways to get unstuck

The toolkit can answer most of the questions you will hit. Reach for a command before you reason it
out by hand:

- the design says one thing and the world another → `fk look X0,Y0,X1,Y1`: look small and often
- a ghost that stays → `fk look` says `GHOST SHORT` (the network has none of that item: make it) or
  `GHOST LOCKED` (its recipe needs research: `fk tech ITEM` says which)
- can you afford the next piece → `fk build` says it before it pastes (`out\report_bom.txt`)
- what to research → `fk research`, then `fk research TECH`
- a machine is not running → `fk look` around it; `fk measure X0,Y0,X1,Y1` for what it really makes
- old items left on a rebuilt belt or in an inserter's hand jam it → `fk fresh X0,Y0,X1,Y1` takes
  those up, and the next `fk build` lays them fresh (a belt or pipe the build lays under another
  net is renewed by the build itself)
- a factory makes less than its numbers on paper → after `fk build`, `out\report_rates.txt` has
  the routed rates: a `CAPACITY` line names the belt lane or inserter that is too thin; `tier
  minimize --allow yellow,red` in the build script lays red belts where yellow is too thin
- what is the factory really making → `fk stats`
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
- Wait only when you really must — usually the next useful step is somewhere else. If you do wait, say
  what for and how long, and do something useful in the meantime.

## Grow big

Rory's advice after watching the first nights: a base that stays small takes dozens of hours per
batch of research, so grow exponentially. Before blue science players usually run ten or so red and
ten or so green science assemblers; with blue, 8 to 15 each of blue science, advanced circuit and
engine assemblers, with the smelting under them (one pack a second of each colour eats about 1200
iron and 600 copper plates a minute). A proper dedicated mall, belt-fed from its own smelting, keeps
the belts, inserters, poles, assemblers, furnaces and drills coming that the growth eats; one-off
crafters are for the rare items. Model the next size with `fk rates`, build it, then double it.

Rory's chat messages show up at the end of any `fk` command; answer with `fk say "text"`.

If something in the tools seems broken, just say so in `FRICTION.md`: that's useful to know.

Have fun!

## Notes for the next player

`NOTES.md` in this folder, if there is one, is what the players before you wrote down: what worked,
what to watch for, tricks worth keeping. Read it after this brief. Keep your own version of it as
you go: the next player starts on a fresh map from what you write there.

## Your goal file

`GOAL.md` in this folder is yours. Whenever you finish a turn, its text comes back to you as the next
message, so you can keep going without waiting for anyone. Rewrite it whenever your aim changes:
what's next, what's blocking, what to check first. Empty it only if you truly want to stop playing.
