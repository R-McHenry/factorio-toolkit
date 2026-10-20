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

`fk build` runs the steps of `game\nauvis.build.fkb` in order and prints one line per step. Each
step writes its report to `game\out\<step>.txt`: read the one that matters
(`out\report_checks.txt`, `out\route.txt`, `out\apply.txt`). A build changes only what changed
in the source: unchanged rows and routes stay where they are.

After `fk build`, the ghosts are in the game and the robots build them from the network's stock.
`fk look` says GHOST for what is still waiting. Look again a little later, not in a loop.

## What `fk look` says

Every designed entity in the area gets a verdict:

- `OK`: there, as designed
- `GHOST`: its ghost is there, waiting for robots
- `MISSING`: nothing there (destroyed, or never built; the next build restores it)
- `WRONG`: something else stands on its tiles
- `DRIFT`: there but turned, or with another recipe
- `WRONG_ITEM`: a belt carries an item its net doesn't

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

## When you need something

```
fk explain main.fk gears         one row as its template and as the entities and nets it becomes
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
fk read-terrain --surface nauvis --area X0,Y0,X1,Y1
                                 read more bare ground into map.terrain.json
fk chat                          Rory's messages since you last looked
fk say "text"                    one line in the game chat
```

Every command takes `--help`.

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
report_checks` runs part of it.
