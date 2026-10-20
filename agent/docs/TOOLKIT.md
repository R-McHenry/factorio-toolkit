# The toolkit

`bin\` is on your PATH: `fk` is the one command, and it reaches the game for you. Your world is
`game\`: the factories (`.fk`), the surface file, the build script. Edit those with normal file
tools. The `.fkp` files beside them are the layouts the toolkit writes: read them, never edit them.

## The loop

```
fk rates main.fk                 the factory's numbers on paper: every machine's utilization, every
                                 net's supply and demand, what limits it (the binding chain)
fk check main.fk                 the netlist checks (UNFED, UNCONSUMED, TYPE, ...)
fk build                         the whole build script: lay out, route, power, check, paste
fk build --to report_checks      design only: everything up to the checks, nothing pasted
fk look X0,Y0,X1,Y1              that area now, against the design
fk look X0,Y0,X1,Y1 --design     the design alone, as it will be built
```

One thing `fk rates` gets wrong: it shares a short net in proportion to what each machine wants,
but the game doesn't. The machine that reaches the items first (the first inserters along a belt,
one side of a splitter) takes its fill, and the ones further on get what is left, or nothing. So a
net that is short on paper starves its far machines rather than slowing them all a little: give it
more supply than demand, and give a chest on it a `limit=` (`SHARED_SINK` says where).

`fk build` runs the steps of `game\nauvis.build.fkb` in order and prints one line per step. Each
step writes its report to `game\out\<step>.txt`: read the one that matters
(`out\report_checks.txt`, `out\route.txt`, `out\apply.txt`). A build changes only what changed
in the source: unchanged rows and routes stay where they are.

After `fk build`, the ghosts are in the game and the robots build them from the network's stock.
Before the paste, `out\report_bom.txt` says what the network can't cover: its `STOCK:` line, and
LOW_STOCK / LOCKED per item. A ghost that stays is a blocked build, not a slow one: `fk look`
marks it GHOST SHORT or GHOST LOCKED (below), and waiting won't change that.

Every command ends with the game's new alerts (grouped per kind), Rory's new chat lines and the
research line (`RESEARCH: NONE` when nothing researches).

## What `fk look` says

Every designed entity in the area gets a verdict:

- `OK`: there, as designed
- `GHOST`: its ghost is there and the network holds the item: robots are on their way
- `GHOST SHORT`: its ghost is there and the network holds none (or too few) of the item: robots
  can't build it until you make the item (an assembler row into a provider chest) or bring it
- `GHOST LOCKED`: its ghost is there and the item's recipe isn't researched: `fk tech ITEM` says
  which technology opens it and what it costs
- `MISSING`: nothing there (destroyed, or never built; the next build restores it)
- `WRONG`: something else stands on its tiles
- `DRIFT`: there but turned, or with another recipe
- `WRONG_ITEM`: a belt carries an item its net doesn't (old items from a rebuild): `fk fresh
  X0,Y0,X1,Y1` takes those belts up, and the next build lays them fresh

Anything in the area that the design doesn't explain is:

- `CLAIMED`: inside a claim (the starter kit)
- `MARKED`: something placed by hand, kept for now (it is listed under "changes here", with who
  placed it, and a hint when it looks like a fix to a net)
- `NOBODY`: nobody owns it; the next build removes it

## The checks

Checks are report lines, never errors: the build goes on and tells you. Read them; most are worth
fixing in the source.

- `UNFED` / `UNCONSUMED`: a machine's input has no net feeding it / its output goes nowhere
- `TYPE`: a net names a machine that has no endpoint for the net's items
- `SUSHI_SINK`: a sushi net reaches a machine that doesn't take every item on it
- `CLOG`: a mixed belt that machines feed, or an unlimited chest fed two or more items by
  separate nets: an item that comes faster than it is used can fill it and stop the others.
  Mixed belts and chests are fine where nothing comes faster than it is used (a one-off crafter
  on a requester chest is)
- `UNLIMITED`: provider or storage chests without `limit=`: what reaches them goes into the
  network without end. `Chest<provider, limit=4>` keeps 4 stacks, and what feeds it stops when it
  is full
- `SHARED_SINK`: such a chest on a net with machines: whoever stands first on the belt gets its
  fill, so the machines can starve
- `RIP`: the build takes up a lot, and the robots need minutes for it (the structures, the items
  in them, and how long: `out\diff.txt`). It goes faster if you stop what feeds it first and let
  it run a few minutes to empty its belts and chests. When the same things come back elsewhere, a
  factory moved: `fk merge` joins factories where they stand
- `DOUBLE`: one machine input or output on two nets
- `ASSERT` / `TARGET`: a rate you asserted, or the surface's target, is not met on paper
- `UNROUTED`: no belt route was found for a net (the reason follows: often a row is boxed in;
  leave a few tiles free around a row's head, where its belts attach)
- `OPEN` / `LEAK`: a net's route doesn't reach every machine / touches another net
- `NO_POWER`: a factory's poles don't reach a grid with generation (`floorplan --bridge-power`
  in the build script joins it to the plant's grid)
- `NO_ROBOTS`: a logistic chest outside every logistic area of the main robot network (robots
  won't serve it), or entities outside its construction area (robots won't build them). The kit's
  roboport at 8,8 serves chests 25 tiles each way and builds 55 tiles each way; `cover robots`
  gives a factory with chests its own roboport, which joins the network when it stands within 50
  tiles of another one on both axes. Grow outward: the next factory within reach of the last.
- `ON_TERRAIN`: something designed stands on water or a cliff
- `MISPLACED` / `UNPLACED`: the paste did not land where the design says
- `LOW_STOCK`: the network holds fewer of an item than the build still needs
- `LOCKED`: an item to build, or a machine's recipe, isn't researched (the technology and its
  cost follow)

## When you need something

```
fk explain main.fk gears         one row as its template and as the entities and nets it becomes
fk build --to diff               what the next build would take up, and how long the robots need
fk fresh X0,Y0,X1,Y1             belts there with old items on them are taken up; the next build
                                 lays them fresh
fk merge . A,B --into C          two factories become one, both kept where they stand
fk chests-to-net . C PROV REQ    a robot link (provider chest to requester chest) becomes a belt
fk net-to-chests . C NET --provider P --requester R
                                 a belt becomes a robot link
fk unfold main.fk gears          turn a row into a Literal (its entities pinned as they are)
fk split-to-chest . main NET box --at X,Y [--requester --item I]
                                 a chest joins a net as one more endpoint (a buffer, a tap)
fk adopt X,Y --into main/NET     a belt you placed by hand becomes part of that net's route
fk measure X0,Y0,X1,Y1 [--seconds 30]
                                 what the machines in an area really make, against the model
fk stats [--items iron-plate,copper-plate] [--window 10min]
                                 production statistics (free to read)
fk chart                         how much of the map is explored (free to read)
fk alerts                        the alert panel now (new alerts also come by themselves)
fk lua "CODE"                    run a Lua chunk in the game: its rcon.print comes back (read,
                                 investigate; see "Reading the game yourself")
fk lua --file probe.lua          the same with a file of yours
fk research                      what can be researched now, cheapest first, and what is running
fk research TECH [TECH...]       queue research (labs and science packs do the rest)
fk tech NAME                     a technology, or what opens an item or recipe: cost (or what to
                                 craft or build for it), what to research first
fk recipes [NAME...] [--enabled] the locked recipes (or the enabled ones) and what opens each
fk read-terrain --surface nauvis --area X0,Y0,X1,Y1
                                 read more bare ground into map.terrain.json
fk chat                          Rory's messages since you last looked
fk say "text"                    one line in the game chat
```

Every command takes `--help`.

## Reading the game yourself

`fk lua` sends a Lua chunk to the game over RCON and prints what it `rcon.print`s:

```
fk lua "rcon.print(game.forces.player.current_research and game.forces.player.current_research.name or 'none')"
fk lua "local n = 0 for _, g in pairs(game.surfaces.nauvis.find_entities_filtered{type='entity-ghost'}) do n = n + 1 end rcon.print(n)"
```

The chunk is sent as one line, so keep `--` comments on lines of their own. A big answer is
better written to a file (`helpers.write_file('mine.json', helpers.table_to_json(t))`) on the
game host and read there. For a script of your own, the game host is `computah-ct`
(`ssh computah-ct`); `run.json` names the toolkit there (`host_toolkit`: `fkcore.link.Rcon` is
the RCON client) and your game codebase there (`host_game`).

Use it to look and to understand. Changes go through the game: `fk build` (ghosts and robots),
and a script of yours can fix things the same way, by taking up the belts that carry stale items
so the next build lays them again (`fk fresh` does just that). Nothing is created, refilled or
moved by script. The link refuses Lua that registers an event handler, a command or an
interface: that made every save unjoinable once.

## The surface file

`game\nauvis.surface` places each factory on the map:

```
place iron = iron plot 40,-20 30x30          # factory iron, from iron.fk, on its own plot
place main = main plot 80,0 120x80
claim kit box 2,6 23,21 "the starter kit"    # a claim: keep it, never build over it
watch plots:      keep                        # something placed by hand in a plot: kept, listed
watch sanctioned: mark 2h                     # ... outside every plot: marked for two hours
target automation-science-pack 10/min         # a rate the whole surface should make
```

A factory's `@(x, y)` positions are inside its own plot: (0, 0) is the plot's top-left corner.
Plots never overlap. A factory can be moved by changing its plot alone.

## The build script

`game\nauvis.build.fkb` is the list of steps `fk build` runs: one step per line, each reading
what the steps before it made. Keep it, or tweak it: leave `apply` out while you design, or add
`stop_on UNFED` before a big paste so a check stops the build. `fk build --from route --to
report_checks` runs part of it. `route --hand inserter` links machines with plain inserters
instead of fast ones (rows take `inserter=inserter` for the same).
