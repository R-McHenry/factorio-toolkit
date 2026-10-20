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

Everything after that, you make: you design a factory, robots build it, and it feeds itself.
Not every recipe is unlocked at the start; `recipe_not_researched` is the tech tree doing its job.

## How building works here

You build like an engineer. A factory is a short source file, `game\NAME.fk`, that says **what**:
rows of machines (`gears = AsmRow<n=3, recipe=iron-gear-wheel> @(16, 22)`) and **nets**, which say
which machines feed which (`net gear: gears -> red, belts`). You don't draw belts: `fk build` lays
the whole factory out on its plot, routes a belt for every net, adds the power poles, checks it,
and pastes it into the game in one go. The robots build it from the network's stock. Then
`fk look` shows you what is there.

- `docs\TOOLKIT.md`: the commands, and what their reports mean. Read it once.
- `docs\LANGUAGE.md`: the `.fk` language and the templates (the rows you build from).
- `docs\EXAMPLES.md`: small factories that build cleanly; a good place to start.
- `game\nauvis.surface`: where each factory's plot is on the map. `game\nauvis.build.fkb`: the
  steps of `fk build`. `game\map.terrain.json`: the bare ground (ore, water, cliffs).

The nuclear plant is already a factory in the surface file (`plant`), and the starter kit is a
claim (`kit`): leave both where they are and build around them.

## The loop

Design first, then build. Pick a target ("red science at 10/min"), write the factory, check its
numbers with `fk rates`, `fk build` it, `fk look` at it. Then add the next piece and repeat. When
something is off, fix the source and build again: the source owns every tile, and a build puts the
world back to what the source says. Small factories that work beat a big plan.

- Give each factory its own plot (`place` in the surface file) on bare ground, on or next to
  the ore it needs (`map.terrain.json`, or `@patch(iron-ore)` on a miner row).
- A build replaces whatever stands in the way of the design. That's intended: the design wins.
- One net per belt. A net may carry several items (a sushi net), but only into machines that
  take them all.
- Don't place things by hand. If you must (a quick fix), `fk adopt` brings it into the source
  afterwards, so the next build keeps it.

## What you can see

You see what you look at, like a player in front of the screen:

- `fk look X0,Y0,X1,Y1` shows that area and compares it with your design. Look small and often.
- The game's alerts come to you on their own (a machine destroyed, no materials for a ghost, a
  programmable speaker you set up): they appear at the end of whatever command you run, with a
  reminder while one is still open.
- `fk stats` (production statistics) and `fk chart` (the explored map) are free to read any time.

Nothing else is watched for you. If you want to know how a far-away part is doing, look at it, or
build the in-game way (circuits and a speaker alert).

## Talking to Rory

Rory's chat messages show up at the end of any `fk` command. Answer with `fk say "text"`.

## When something seems broken

If a command or a report doesn't make sense, write it in `FRICTION.md`: the command, what you
expected, what happened. That's useful to know, and then carry on with something else.

## Your goal file

`GOAL.md` in this folder is yours. Whenever you finish a turn, its text comes back to you as the next
message, so you can keep going without waiting for anyone. Rewrite it whenever your aim changes:
what's next, what's blocking, what to check first. Empty it only if you truly want to stop playing.

Have fun!
