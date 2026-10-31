# The toolkit

`bin\` is on your PATH: `fk` is the one command, and it reaches the game for you. Your world is
`game\`: the factories (`.fk`, your base's plot among them), the world design `nauvis.fk` that
places the plots, the surface file `nauvis.surface`, the build script. Edit those with normal file
tools. The `.fkp` files beside them are the layouts the toolkit writes: read them, never edit them.

## The loop

```
fk rates main.fk                 the factory's numbers on paper: every machine's utilization, every
                                 net's supply and demand, what limits it (the binding chain)
fk check main.fk                 the netlist checks (no-feed, no-taker, cannot-carry, ...)
fk build                         the whole build script: lay out, route, power, check, paste
fk build --to report_checks      design only: everything up to the checks, nothing pasted
fk build --to diff               a dry run: the design against the world and what the build would
                                 take up; nothing written, nothing pasted
fk look X0,Y0,X1,Y1              that area now, against the design
fk look X0,Y0,X1,Y1 --design     the design alone, as it will be built
fk look AREA --zoom 16 --layers all --image
                                 zoomed out, with every layer, as a PNG (see "Zoom, layers and
                                 images")
```

Only `fk wait` waits, from a fixed budget. `fk wait 90s` waits that long, and `fk wait built
X0,Y0,X1,Y1` waits until the robots have built the area. It asks first: run it again, or add
`--sure`. The run has 30 minutes of waiting in all; `wait-budget.json` in your folder says how
much is spent.

A buffer (LANGUAGE.md, "Buffers") gets a line per item at the end of `fk rates`: what comes in
minus what goes out.

```
BUFFER b: +60.0/min iron-ore (filling: in 60.0, out 0.0)
BUFFER b: -52.5/min iron-ore (draining: in 60.0, out 112.5)
BUFFER e: +0.0/min iron-plate (steady, its gated sources top up what goes out: in 150.0, out 150.0)
BUFFER e: +unbounded/min iron-plate (filling: an unbounded source feeds it; gives 240.0/min)
```

Draining is the line to grow. The drill numbers are base rates; the game adds mining
productivity.

One thing `fk rates` gets wrong: it shares a short net in proportion to what each machine wants,
but the game doesn't. The machine that reaches the items first (the first inserters along a belt,
one side of a splitter) takes its fill, and the ones further on get what is left, or nothing. So a
net that is short on paper starves its far machines rather than slowing them all a little: give it
more supply than demand, and give a chest on it a `limit=` (`SHARED_SINK` says where). A bus
(`Bus<...>`, see LANGUAGE.md) is a pool on paper: what its loads bring, its taps share; along the
real bus the first tap takes its fill first.

After `fk build`, `out\report_rates.txt` also has the **routed** rates: what the belts and
inserters as laid let through, with the first machines along a belt served first, as in the game.
A belt lane carries 7.5 items/s (yellow; red 15, blue 22.5, turbo 30), a fast inserter 2.5/s, a
long-handed one 1.2/s, a plain one about 0.85/s, more with the inserter capacity research (the
build uses your force's, as the last build saw it; the report's last line says which). Each
routed section's first line says whether its machines settled; where they did not, its numbers
are approximate. `fk rates main.fk` shows the same routed section after its nominal one, on
`main.fkp` as the last build laid it out (`--hand N` for other inserter hands).

A net is one lane until it needs two. A line's inserters drop its products on one lane of its
belt, so one line of machines on one side carries at most 7.5/s on yellow, and the routed rates
count it so: each net's critical connector is its own lane. A net that carries more than a lane
and has two or more makers goes on both lanes: the router puts half its makers on each (2.0.54,
LANGUAGE.md "Nets"). Two nets can share a belt, one on each lane (`lanes ore_ | fuel`): one belt
to lay instead of two, and the two never stop each other, since a full lane holds only its own
items. A net on both lanes (a two-sided MinerRow's ore) gets one lane when it is side-loaded onto
a shared belt: 7.5/s there, and `too-thin` says so where it brings more. A mixed net from a
requester of several items is the jam to avoid: write it `split` (one lane per item) or feed each
maker by one inserter straight from the requester. An inserter that loads a belt from a chest of
several items is filtered to its net's items (2.0.76; the route report's `unfiltered` line names
one that can't be, a long-handed one where no fast inserter fits).

`fk build` runs the steps of `game\nauvis.build.fkb` in order and prints one line per step (one
build at a time in a run: a second `fk build` waits for the first). Each step writes its report
to `game\out\<step>.txt`: read the one that matters
(`out\report_checks.txt`, `out\route.txt`, `out\apply.txt`). A build changes only what changed
in the source: unchanged rows and routes stay where they are, and a net is patched when a machine
or a module's port is added to it, taken off it or moved (a chest one tile over, too).

Rebuilds keep what stands. The poles and roboports a build laid stay where they are wherever the
new design leaves their spot free, and new ones go only where something new needs them, so power
and the robot network keep running through a rebuild (`out\cover_power.txt` says how many were
kept; `fk build --with 'cover robots --fresh'` lays them all anew for one build).
Switching the pole kind (`cover power --pole small-electric-pole` while medium poles are short)
keeps the poles of the old kind the last build found standing and lays the new kind only where
the old one never stood. `--pole any` switches by itself, the way `--hand any` does: medium poles
while the network can build them (they are in the kit at the start), small ones when it cannot.
Small and medium poles are both 1x1, so a switch keeps what stands; `big-electric-pole` and
`substation` are 2x2 and are named by hand only.
Old poles and roboports the design no longer has stay up until the design's own stand there, and
the first build after that takes them up.

Routes stand too. A net with a new machine or port keeps its belts and gets only a branch to it,
laid into what stands: a splitter in place of a straight belt, the belt's end run on, a
belt side-loaded onto it (a new driver), or an inserter straight off the belt. A machine taken
off a net takes its branch with it; a machine moved gets a new branch where it stands, and a
machine set on a standing belt takes up only the belts under it and what they alone fed. A
belt two nets share is patched the same way: a new consumer of both gets a branch of both lanes,
and a new driver of one net side-loads onto that net's own lane. `out\route.txt` says `patched`
with how many of the net's carriers it kept. When no branch fits, a net with belts is never laid
anew by itself: its belts stand as they are, the new end alone fails (`FAILED net: its standing
route is kept as it is ...`, a `no-route` check), and `fk build --reroute NET` lays the net anew
when you want that. A net of inserters alone is laid anew (`routed again:`). The route follows the
net's ends, not its name: a net whose sink changed under the same name (`X -> lab` to `X -> px`)
is never kept as it was. So a patch is cheap: a row beside the others, a chest one tile over, one
more machine on a net, one more net into what stands. The design the next build keeps to is the
one the last full build wrote (`write_layout`, just before the paste); `fk build --to diff` and
`--to report_checks` write nothing, so try changes with them freely. Before `write_layout`
replaces a `.fkp`, it keeps the one before in `out\fkp-history\` (`world.<date>-<time>.fkp`, the
last 8 of each): copy one back over `world.fkp` to build to the layout before.

When a route you have stops pleasing you (spaghetti from patches, a branch you'd lay otherwise),
`fk build --reroute mall1/fe` lays that net anew, and `--reroute mall1` every net inside mall1
(`out\route.txt`: `routed again: asked`). A route that doesn't reach a machine of its net is laid
again by itself; `report_checks` says `partly-connected` if one ever still doesn't.

Room for routes. Most routes that failed in the 10-30 run had no room, not a router fault:
- A belt fed into a machine by an inserter takes 2 tiles beside it: one for the inserter, one
  for the belt. Two machines that share a belt between them need 3 tiles apart. A 1-tile gap
  holds only a direct inserter from one machine into the next, and a belt laid through that gap
  blocks it.
- A maker with two consumers fits between them, with a direct inserter on each side (A4b: ci5
  between ac5 and ac6 routed; with ci5 at the row's end it could not get past cb5).
- Keep a module's ports and new machines off the path of a main belt that stands. A port on the
  main's path lays the main anew (`routed again` in `out\route.txt`): look for it there after a
  dry run.
- For one far consumer of a main (coal at the brick furnaces), a requester at the hub costs
  less than another branch: a new end far down the main can lay all of it anew.
- A row takes 2 input belts (SmelterRow), and a LabRow's third can't branch in from beside the
  other two. `--reroute` on the three nets together lays them side by side.
- A patch that won't fit fails alone and leaves the rest standing. Move the new machine a few
  tiles, or `--reroute` the net it joins, before you redesign the whole block.

A net that finds no way through another net's belts may cross them by promotion: a straight run of
another route's belt turns into an underground pair under the crossing, pinned or not. Items and
lanes stay as they were. A belt is promoted only where nothing else changes: the run is straight
for two belts either side, no inserter or drill touches the three belts that change, nothing
side-loads onto them, and no underground of the same axis is within 6 tiles along the line. It's a
last resort: the router tries it only for a net that every other pass left unrouted.
`out\route.txt` names each one in a `promoted` line (`promoted  coal: ~coal/b40, ~coal/b41,
~coal/b42 are an underground pair now ...`), and the paste swaps those three belts for two
underground ends. Each promotion takes 2 undergrounds from stock.

Any step takes options for one build without editing the script: `fk build --with 'cover robots
--fresh'`, `fk build --with 'route --effort high' --with 'tier --allow yellow,red'` (repeat
`--with` as often as you like; the step's own options stay, the ones you add win).

Circuits come from the source (`LANGUAGE.md`, "Circuits"): the properties on objects (`set
NAME.out -> CHEST: logistic=ITEM<N`), a crafter's `guard`, wires and conditions. The build lays them on the layout just
before the floorplan (`out\floorplan.txt`, the `circuits` lines, says what each one set), and the
.fkp shows them on the entity lines (`if=`, `logistic=`, `read=`, `filter=`, `signals=`) and as
`wire` / `w` lines. Change a limit and the next build writes it on the inserters that stand: the
paste sets every setting, so nothing is taken up and robots make no trip; a rebuild never loses
them. Drills and offshore pumps are the exception: the game takes no settings from a paste on
them, so the build lays them fresh.

A build changes what stands in one of three ways, and `out\apply.txt` names each with why:

- **written in place:** new settings, or a hand edit set back. The paste writes them.
- **upgraded:** another entity of the same fast-replace group and size stands on a design
  entity's spot: inserter tiers (not the long-handed one), assembler 1, 2 and 3, belt,
  underground and splitter tiers, any chest to any other chest, stone to steel furnace, small to
  medium pole. Robots swap it, and its settings, wires and contents stay.
- **laid fresh:** everything else (another size or group, turned, a carrier that held another
  net's items): it is taken up and built new.

Wires follow the design too. After the paste, and again when `fk wait built` finds the robots
done, the build adds the design's missing red, green and copper wires and cuts the ones between
your design's entities that the design doesn't have. A pole robots build joins itself to the
poles in reach that its own paste didn't lay (another plot's, say); this takes that back. Wires
to anything outside the design are left alone. `out\apply.txt` gives one line, `wires: 3 added,
1 cut`; a circuit wire made by hand is named once as `by-hand` before it goes.

A build also takes back what it built before and your design no longer has: a row you replaced,
the old ground of a plot you moved or shrank, a factory you emptied, its unbuilt ghosts too. The
toolkit remembers what it pasted (`out\own\nauvis.json`), so this holds whatever `watch` says.
A belt or pipe it lays again under another net, while it still holds the old net's items or
fluid, is taken up and laid fresh in the same build.

On ground a paste can't use (uncharted ground, with no radar or character to chart it), each
entity is laid as a single ghost instead, carrying its recipe, underground end, requests, circuit
settings, filters, fuel and wires, so robots build it the same way. A setting the game won't put
on a ghost (a requester chest's trash-not-requested, a chest's bar) is named in `out\apply.txt`
under SETTINGS: set it in the game, or build again once a radar charts the ground.

After `fk build`, the ghosts are in the game and the robots build them from the network's stock.
Before the paste, `out\report_bom.txt` says what the network can't cover: its `STOCK:` line, and
short-stock / needs-research per item. A ghost that stays is a blocked build, not a slow one: `fk look`
marks it ghost SHORT or ghost needs-research (below), and waiting won't change that.

Every command ends with the game's new alerts (grouped per kind), Rory's new chat lines and the
research line: the research under way, its progress, the packs the labs used in the last game
minute and the time left at that pace, as in `research military-3 34%, 41 packs/min, ~22 min
left`. It is loud when nothing researches (`RESEARCH: NONE`), and when the labs used no pack in
the last minute while a research is queued (`RESEARCH STALLED`), with the cause when the game
shows it: `no lab holds military-science-pack`, `no lab holds all 4 packs (chemical-science-pack
missing in 9 of 12 labs)`, or the labs have no power.

## How many machines and drills for a rate

In a factory you write, `n=auto` on a row lets the build count it: the fewest machines that meet
the surface's `target` lines, your asserts and what the row's consumers take (LANGUAGE.md, "Counts
the build chooses"). `fk build --to size` shows the counts and what each serves in
`out\size.txt`; `fk rates FILE.fk` shows the rates at them.

`fk rates` checks a factory you have written; `fk plan` answers before you write one, from an
item and a rate or from the machines you want on that item:

```
fk plan chemical-science-pack --machines 15
                                 what 15 blue science assemblers take, every step down to the ore
fk plan chemical-science-pack 1/s
                                 the same for a rate (60/min, 0.5/h; a bare number is /s)
fk plan electronic-circuit 10/s --raw iron-plate,copper-plate
                                 the plates come from elsewhere: plan only the rest
```

One line per item of the recipe tree: the rate it takes (/s and /min), its recipe and machine, and
how many machines that is (`machines` as a fraction, `build` rounded up). Under an item that feeds
several recipes, `for ...` says how much each one takes, which is what its net carries to each row.
Then the raw inputs: ore and coal (furnace fuel included) with their electric mining drills, crude
oil with its pumpjacks, water with its offshore pumps. For 15 blue science assemblers that is 11.25
iron and 7.03 copper plates a second: 36 + 23 stone furnaces and 15 more for steel, then 23 iron,
15 copper and 7 coal drills.

The plan runs every machine at full speed, without modules or beacons: assembling-machine-2 for
crafting (a row's default is assembling-machine-1, two thirds as fast: `--asm
assembling-machine-1` gives a row's numbers), stone furnaces burning coal for smelting, chemical
plants, oil refineries, and electric drills at 0.5 ore/s. These change it:

- `--asm assembling-machine-1` or `--asm assembling-machine-3`
- `--furnace steel-furnace` or `--furnace electric-furnace` (no coal)
- `--mining-productivity N`: your research level, +10% ore a level
- `--recipe ITEM=RECIPE`: the recipe for an item that has several (the notes name them)

Petroleum gas comes from basic oil processing, the oil recipe the research opens first. With
`--recipe petroleum-gas=advanced-oil-processing` it comes from advanced oil processing, without
cracking, and the heavy and light oil nothing takes show as `surplus` (a refinery stops when one
of its outputs is full). Pumpjacks are counted at 100% yield, 10 crude oil a second each: a well's
yield is in its tooltip.

## Planning ahead: `fk stage`

`fk stage` keeps a plan of stages in git beside `game\`. `main` is what is built; the plan is one
commit per stage on top of it, and each commit's message is the stage's spec: its goal, what it
needs first, the rates it should reach, and the test that says it's done. A stage holds source only
(`.fk` files, the world design, the surface file, the build script, and the file each Literal reads,
such as relay.json), and its layout is computed when it is checked: `fk stage edit` keeps that file
in the stage it edits, the stages replayed after it get it, and a file outside `game\` or in `out\`
is not taken. A stage keeps its number however the plan changes.

```
fk stage list                    the stages in order, each one's plates per minute and state, and
                                 the horizon: the planned base against the built one
fk stage insert "oil plant" --goal "..." --needs "..." --rates "plastic-bar 30/min" --test "..."
                                 a new stage at the end (--after K, --first), with its folder
                                 stages\N: game\ as the stages before it leave it
fk stage edit N [--goal ...]     stages\N's .fk, surface and build script (and the spec given) into
                                 the plan; the stages after it replay onto it
fk stage check N [--render [X0,Y0,X1,Y1]]
                                 stage N built in stages\N through report_checks: its check lines,
                                 its rates against the stage before it and against its spec, and
                                 what it builds, with what the base before it makes of each item
                                 and the stock game\'s last build saw; nothing touches the world.
                                 --render draws the design it laid out (the plots it changes, or
                                 the area); stages\N\out\render.txt keeps it
fk stage next [--apply]          the next stage's spec and its diff; --apply puts it into game\
fk stage done [N]                game\ as it stands becomes main, with stage N done; the rest of
                                 the plan replays onto it
fk stage rebase [-m "why"]       game\ as it stands becomes main (a hand fix adopted); the plan
                                 replays onto it
fk stage drop N                  stage N leaves the plan
fk stage reorder N --after K     stage N moves (--first: to the front)
```

A stage folder is a scratch copy of the whole game folder, built layouts and terrain included:
design in it with normal file tools, `fk stage check N` it as often as you like, and `fk stage edit
N` takes its source into the plan. Until then its edits are its own ("unsaved edits" in the list),
so a worker can try a change there while another builds in `game\`.

Replaying is the key operation. When main moves (a stage done, a hand fix adopted), the plan is
replayed onto it, stage by stage. A stage whose files reality didn't touch replays cleanly; one
whose lines reality changed comes back with conflict markers in its files (`<<<<<<< what is built`
... `=======` ... `>>>>>>> stage 5`) and a CONFLICT in the list: settle them in its folder, then
`fk stage edit N`. Every rewrite keeps the plan before it as a tag (`plan/rev-N`), so you can see
how the plan changed. A stage finished out of order is fine: `fk stage done N` says which stages
before it stay planned.

The horizon is in plates per minute, iron plus copper, as the rate model's furnaces make them:
plates grow from the first drill on, and every part of the base is made of them. Science per
minute is shown beside it. A plan that reaches 1.5 to 2 times the built base stays about the same
span of play ahead at any size of base: nearer 2 while builds take long, nearer 1.5 while the base
is young and changes fast.

The plan's repository is `.stage\` and its folders are `stages\`, both in the run folder, outside
`game\`. `fk stage` changes `game\` only with `next --apply`.

## The lab: `fk lab`

The game has a second surface, the lab, where you try a design for real before it goes into the
base: its own force with the research done, building at once, free materials, and none of the
fair-play rules (`docs\FAIR-PLAY.md`, "The lab"). Rory watches it with `/lab`. While your
builders work and there seems to be nothing to do, the lab and planning (`fk stage`) are the two
things worth doing, and workers can do most of the lab work.

```
fk lab NAME                      NAME (a factory the world design places, or NAME.fk) built on
                                 its own lab slot: powered, its requester chests filled, burners
                                 given a first load of coal; says where Rory sees it
fk lab NAME --from stages\4      the same from a stage's folder (or a scratch copy of game\)
fk lab NAME --size 60x40         its plot size, when no plot places it (default 100x100)
fk lab NAME --measure 60         what its machines really make over 60 s, against the rate model
fk lab NAME --clear              its slot emptied and freed
fk lab --list                    the slots in use
fk lab NAME --copy-ore 272,-72,312,-40 --to 4,2
                                 the world's ore in that map area (shape and amounts) copied
                                 onto NAME's slot, its top-left at 4,2 of NAME's plot
fk lab NAME --ore iron-ore --area 0,0,30,20 [--amount 50000]
                                 that ore over that area of NAME's plot
fk lab NAME --clear-ore          every ore tile of NAME's slot taken up
```

- The lab has no edge, and a factory of any size fits. Each factory gets its own slot, sized to
  it in 200-tile cells, and keeps it while it fits; building it again empties the slot first,
  and `fk lab` generates the ground under it. Its workspace is `lab\NAME` in the run
  folder, never `game\`.
- Drill rows get their ore seeded under them, so a smelting block runs as designed. To try drills
  on a real patch's shape, build NAME once, copy the patch onto its slot (`--copy-ore`, the map
  area round the patch, `--to` where your design puts its corner), and build again: a rebuild
  keeps the slot's ore, and the drills are seeded only where there is none. A requester
  chest is filled with what it asks for, so the machines run as fast as they can: the measure
  shows what the machines do when their inputs keep up, where the rate model counts the
  `rate=` you wrote (the gears example: 120 gears a minute in the lab, 37.5 on paper at
  `rate=1.25/s`).
- Let it run a minute or two before `--measure`: a backlog that piled up while it started reads as
  speed. `--measure 60` takes a minute; it tops the requesters up first.
- A good worker task: "Try stage 4's mall in the lab (`fk lab mall --from stages\4`), let it run
  two minutes, measure it, and report what each maker makes and what it waits for."

## The speedrun planner: `fk sim`

A second game of your own map, on this machine: same seed, same first tick, yours to try a plan in
before the live game does it. It never touches the live game. It stands still between your
commands, so every action lands on a tick you chose, and the same save with the same actions
gives the same game every time. It runs as fast as the machine allows: about 20 times real time
on this laptop.

```
fk sim fetch                     your map as it stood right after the kickoff, as save state start
fk sim fetch --live now          the live game as it stands now, as save state now
fk sim start [NAME]              the planner from a save state (default start), paused
fk sim speed 100                 ticks run up to 100 times as fast (1 is real time)
fk sim run 3600 | until T        move the game on 3600 ticks (a minute), or to tick T
fk sim save NAME | load NAME     a save state of the game as it stands; back to one
fk sim saves | status | stop
fk sim place FILE @X,Y           a design built at once and free: a laid-out .fkp (game\world.fkp,
                                 a factory's), a blueprint string (.txt) or {"bp": ...} (.json),
                                 X,Y added to its own coordinates; modules put in, trees and rocks
                                 in the way removed, landfill laid under it on water
fk sim paste FILE @X,Y           the same as ghosts, for the robots to build
fk sim remove X0,Y0,X1,Y1        everything there gone at once (cliffs and enemies too)
fk sim decon X0,Y0,X1,Y1         everything there ordered out, for the robots
fk sim play plan.sim             a playback (below)
fk sim game stats | look | lua | research ...   any game command, on the planner
```

A playback is a file of actions, one a line, each on the tick the game stands at:

```
# plan.sim
from start                  # the save state it plays from (first, once)
speed 100
place game\mine.fkp @0,0     # free
at +1800                    # 1800 ticks on (or `at 36000`: to tick 36000)
paste game\smelt.fkp @40,0   # ghosts: the robots build it while the game runs
run 3600
save after-smelt
```

`fk sim play` prints each action with its tick. The game still refuses what it refuses in the
run: a building on a cliff or an enemy base, or a drill off its ore. `place` says how many didn't
stand and why. The planner's own files are in `sim\` of your run folder.

A save state loads at the tick it was saved at, every time. A save written while the game was
running (the fetched start, `fetch --live`) used to run on for tens to hundreds of ticks each time
it booted. The first boot of one now saves it again, paused, and says so.

### Explore mode: `fk sim explore`

Explore mode hands the planning to the planner and gives you a speedrun of short rounds. Each
round, it loads a game it picks and gives you a **manifest**: a few items, each with a total for
the base to have made, counting what it made before. Make them as fast as you can.

```
fk sim explore on [--budget 36000] [--minutes M] [--rise 0.1]
                                 the mode on, and the first round loaded with its manifest
                                 (--rise: how big a round's manifest is, 0.1 about 7% more of
                                 everything the base has made, research included)
fk sim explore status            the round: ticks used, minutes, and the manifest so far
fk sim explore next              the next round now
fk sim explore off               the mode off
```

Play as you would on the planner. `paste` your designs, `decon`, queue research with
`fk sim game research`, use `fk sim game lua` for anything else, and `run` the game. Every `run`
reports the manifest.

A round ends on its own: when the manifest is met, or when its budget of ticks (`--budget`) or of
your own time (`--minutes`) is spent. Its `run` stops there and says `ROUND N OVER`, and the next
round loads by itself with its manifest.

A manifest weighs the tech tree. An item behind research costs it the science the base hasn't made
yet, so short rounds name things the base's science nearly reaches. Some still name an item that
is far off: one fluoroketone barrel takes most of the tech tree and another planet. Don't skip it,
and don't wait on it. Think of the way that gets to it in the
end, and take the first step on that way this round: the research it needs, or the factory before
it. The round counts every step forward, whether the manifest is met or not.

`place` and `remove` are off while the mode is on (a round is played as the live game would be:
ghosts and robots), and so is `load`, since the planner picks the game.

Behind it, the planner keeps the best way to every state the rounds reach, so the good plans
collect without you tracking them.
- **Looking afterwards.** `fk sim explore archive` maps them: V is how far up the game a state
  is, in what its base has made, with the research that implies, so it never stops rising. H is
  how far off the best path it is.
- **Replaying.** `fk sim explore best --to plan.sim` writes the way to a state as a playback.
- **Where rounds start and what they ask.** Both are picked on this map, evenly across it: a
  round starts in a part of the map picked at random, and its manifest is a step `--rise` up V
  in a direction picked the same way. `--pick track` leans the starts toward the best path.
- **Starting over.** `fk sim explore reset`.

## What `fk look` says

Every designed entity in the area gets a verdict:

- `ok`: there, as designed
- `ghost`: its ghost is there and the network holds the item: robots are on their way
- `ghost SHORT`: its ghost is there and the network holds none (or too few) of the item: robots
  can't build it until you make the item (an assembler row into a provider chest) or bring it
- `ghost needs-research`: its ghost is there and the item's recipe isn't researched: `fk tech ITEM` says
  which technology opens it and what it costs
- `not-placed`: nothing there (destroyed, or never built; the next build restores it)
- `dnp`: DNP in the design and not built, as designed (counted, not listed); `dnp-standing`:
  DNP but built, kept as it stands until `fk build --confirm` takes it up
- `other-entity`: something else stands on its tiles
- `settings-changed`: there but turned, or with another recipe. A belt, underground, splitter, inserter,
  pipe-to-ground, pump or drill that stands turned (or as the other underground end) says
  `re-laid`: the next build orders it out and robots lay it again as designed
- `UNPAIRED`: a built underground belt with no partner in reach, or with another end of the same
  kind (two outputs) so no tunnel forms; the line gives its position. A ghost pair is not built
  and is not reported
- `other-item`: a belt or pipe holds an item or fluid its net doesn't (old items from a
  rebuild); on a belt two nets share, lane by lane (copper on the iron lane is wrong there). One
  the build laid under another net says so, and the next build renews it by itself; for the
  others, `fk fresh X0,Y0,X1,Y1` takes those belts up, and the next build lays them fresh

Anything in the area that the design doesn't explain is:

- `claimed`: inside a claim (the starter kit)
- `marked`: something placed by hand, kept for now (it is listed under "changes here", with who
  placed it, and a hint when it looks like a fix to a net)
- `unowned`: nobody owns it; the next build removes it. This is also what the toolkit built and
  your design no longer has ("the toolkit's own, dropped from the design")

### Zoom, layers and images

`fk look AREA --zoom N` draws N tiles in one cell (N is 1, 2, 4, 8, 16 or 32). Zoom 1 draws every
tile, as before; without a layer it is the same text as before.

- **A cell shows what matters most in it**, in this order: a machine (the commonest kind), a
  roboport, a turret, belt when at least half of what is in the cell is belt (its main direction:
  `^ > v <`), a tank `K`, a chest, an accumulator `Z`, a solar panel `Y`, a beacon `b`, a radar `r`,
  any belt, a pump `P`, an inserter, a combinator `c`, a pipe, a pole, a power switch `$`, a wall
  `#`. `?` is anything else, `.` free ground. A line under the render names the glyphs it shows.
- **From zoom 8 up, each plot is its outline** (`*---*`, `|`) with its name and how many machines
  stand in it, like the game's map view.
- **Zoom 8 and up, or more than 65536 tiles, is a map look.** It reads counts per cell, not every
  entity, so a look at the whole base is quick (a base of 1024 x 1024 tiles and 87,000 entities
  reads in about 1.3 s). It gives no verdicts: look at zoom 1 to 4 for those.
- **In play mode a zoomed-out look reads only charted chunks**, what your map view shows. An
  uncharted chunk is blank. The lab is all charted.

`--layers NAME,...` (or `--layers all`) adds one panel for each layer, design | live, each with
legend lines under it. A layer's marks go on free cells, and its points go over anything.

- **`robots`**: each roboport's logistic area in its network's key (`1`, `2`...) and its
  construction area as `,`. The legend gives each logistic network's robots: logistic and
  construction, busy and idle, in flight, docked and charging. `!` is a ghost outside every
  construction area: robots never build it.
- **`power`**: each electric network's pole supply area in its key, `X` a machine with no power,
  `~` one with low power, and each power switch, `$` on or `/` off.
- **`defense`**: turret ranges (`g` gun, `l` laser, `f` flamethrower, `a` artillery, `*` two
  kinds), `T` a turret and `0` one with no ammo, `x` land mines, `#` walls and `G` gates, `!` a wall
  outside every turret's range (a gap in the ring), `@` a nest and `w` a worm. The legend gives the
  ammo.
- **`pollution`**: each chunk's pollution in bands (`1` up to 20, `2` up to 100, `3` up to 500, `4`
  more), and `!` a nest the pollution reaches.
- **`pipes`**: each pipeline in its own letter, with its fluid and how full it is in the legend,
  `K` a tank, `P` a pump, and `!` a machine with a fluid connection nothing meets.
- **`recipes`**: each machine's recipe as a short tag on its top row (`gear`, `circ`, `adv`) and
  its status below it (`*` working, `n` no ingredients, `f` output full, `P` no power...). Zoomed
  out, a cell shows the recipe's key, or `!` when a machine there doesn't work. The tags are in
  `fkcore/data/recipe-tags.json`; a recipe it lacks gets one made from its name.
- **`tags`**: your design's plots (outlined) and instances (a letter on each one's corner).

The design side gets the layers the design knows: coverage, networks, turret ranges, recipes and
tags. Pollution and pipes are the game's only.

`--image` writes a PNG instead of the text renders, and prints its path (`out/look-X0_Y0_X1_Y1-zN.png`
under the game folder, or `--image PATH`). It has the same render and the same layers: cells in
colour, layers as tints and outlines, and labels. Read it like a screenshot. The legend lines stay
in the text.

## The checks

Checks are report lines, never errors: the build goes on and tells you. Read them; most are
worth fixing in the source. They come in two voices, and the capitals are the point.

### The loud ones: something will stop working

A belt that fills, machines that starve, a build that never happens. Read these now.

- `CLOG`: a net of two or more items (sushi), or an unlimited chest fed two or more items by
  separate nets: an item that comes faster than it is used can fill it and stop the others. No
  tool can tell whether what feeds a mixed net is limited, so its line goes in two ways only. One:
  the route is one inserter from the source straight into each sink, which takes only what that
  sink accepts (a requester beside a one-off crafter, `Lab`s around a requester of packs); the route
  step says so. A belt in between, or a second inserter, and it can clog again. Two: your design
  says it limits what goes on the net (`net NAME limited:`), which limits nothing itself. The
  fix that holds is `net NAME split:` (2.0.76): each item on a lane of its own, loaded by its own
  filtered inserter, the lanes side-loaded together; a full lane then stops only itself.
  `fk stage check` prints these lines (2.0.76), not just their count
- `SHARED_SINK`: such a chest on a net with machines: whoever stands first on the belt gets its
  fill, so the machines can starve
- `SUSHI_SINK`: a sushi net reaches a machine that doesn't take every item on it
- `SUSHI_LIMIT`: a `limit=` on a chest a mixed belt of makers feeds: when the chest holds that
  much the belt backs up with every item on it, so the limit only brings the stop sooner. A chest
  of many items works best unlimited, with the limit at each maker
- `SPILL`: a net's route touches another net, so its items end up on a belt that isn't its own
- `WRONG-LANE`: items on a lane the layout gives other nets (a belt of two nets with its lanes the
  wrong way round), nets on one lane that go to different sinks, or items on the closed side of a
  belt side-loaded onto an underground: only the lane on its open side gets through, and the other
  stops there
- `NO_POWER`: a factory's poles don't reach a grid with generation (`floorplan --bridge-power`
  in the build script joins it to the plant's grid). `stop_on no-power` holds the paste until it
  does
- `no-source` (cover power, 2.1): a power domain with no generator, and no copper line (through a
  switch or not) to a domain that has one. Its machines never run. The domain with `cover all`
  counts as fed, since it joins the world's grid
- `power-short` (cover power, 2.1): with every power switch open, a domain's machines want more at
  full load than its generators make (solar panels at their day's average, 42 kW). It names both
  numbers. Accumulators count as neither
- `switch-never` (2.1): a power switch whose `when` can't change. Only constants drive its wire,
  nothing does, or no driver puts the signal it reads there. The switch stays as it starts
- `domain-overlap` (cover power, 2.1): a machine no pole of its domain can power without its
  supply area reaching another domain's machines; or two domains name one instance, or two
  `cover all` lines. Give the domains a tile of room between them
- `TILE_SHARED (x, y): N pieces`: two pieces of one net's route on one tile, so one of them is
  never laid. Splitting the net in two (or giving it room) fixes it
- `UNREACHED` (diff, before the paste): entities the paste lays where no powered roboport's
  construction area reaches, counting the roboports the paste lays where robots reach: robots
  never build them. It names power-bridge poles among them, since a roboport powered only through
  such a bridge never gets its power
- `REACH` (report_bom, 2.1.3): the ghosts of this paste that no construction area of a roboport
  that stands reaches, counting a roboport the paste lays only when it stands in such an area and
  joins that network; roboports first, then by item. Robots never build them. `stop_on reach` in
  the build script holds such a paste. `fk build --to report_bom` lists them without pasting



### The rest: what is where

These describe a state - what is missing, what stands elsewhere, what happened - and the usual
answer is the next build. Nothing here is broken by itself.

- `no-feed` / `no-taker`: a machine's input has no net feeding it / its output goes nowhere
- `short-feed` (report_rates): a net's drivers make less than its consumers would take, so they
  run below speed; it names the net where the shortage starts (a short ore patch, not every step
  after it) and the `fk plan` line that sizes its drivers
- `cannot-carry`: a net names a machine that has no endpoint for the net's items (that machine is
  left off the route). The template's build script stops on it (2.1.3)
- `feed-rides-on` (report_rates): a sink at the end of a belt that brings it a product and also a
  feed, an item machines upstream on the same belt consume (sulfur riding the blue packs' belt
  into the packs' chest): what they don't take of the feed fills the sink and stops the belt for
  the product too. Give the product a belt of its own, or filter the sink's hands
  (`set packs.in: filter=chemical-science-pack`)
- `no-limit`: provider or storage chests without `limit=`: what reaches them goes into the
  network without end. `Chest<provider, limit=4>` keeps 4 stacks, and what feeds it stops when it
  is full. A chest a mixed belt of makers feeds gets a line of its own: it fills unless each maker
  is limited (`net NAME limited:` says your design limits them)
- `could-pair`: two single-item nets feed the same machines on two belts, a lane each: one belt carries
  both, one lane each (`lanes A | B`). Half of both belts is empty until you pair them. Whoever
  drives the nets, so a lab row fed red packs on one belt and green packs on another is named too
  (2.0.50); what is left alone is a pair into chests only, a pair a `SmelterArray` or a
  `CircuitStack` feeds (it side-loads its own two nets), and any flow that doesn't fit a lane (a
  requester without `rate=` is unbounded)
- `no-match`: a `set` that matches nothing (no such instance, no hand whose sink is the named one,
  or an `if=` with no chest to read), or an unknown property
- `CIRCUIT`: two settings for one field of one entity (it keeps the first), a `cb.` field that a
  typed property writes too (the `cb.` one wins), a `bp.` field the build writes itself, or a
  raw condition that isn't one
- `cannot-filter`: a `guard` whose input inserters can't filter (plain inserters; fast ones can)
- `no-signal` / `no-wire`: a condition reads a signal nothing on its wire makes, a name the game
  has no signal of, or one that never goes out on a wire where one is sent (`signal-each` in a
  `Constant`) / a wire nothing drives or reads, a wire's end on a building with no circuit
  connector (a pipe, a beacon), or a belt reading on no wire (its reading reaches nothing until
  the belt is wired)
- `wire-too-far` / `wires-share`: two entities of a wire further apart than a wire reaches, with
  no chain of poles and free tiles to carry it (2.1: a longer wire hops along poles, and the build
  adds poles in a gap) / two wires of one colour on one entity, so their signals add
- `gate-open` / `require-not-met`: a gated net the rate model takes as always open (no `behave` cycle on its
  wire) / a `behave` block's `require` that doesn't hold
- `taken-up`: the build takes up a lot, and the robots need minutes for it (the structures, the items
  in them, and how long: `out\diff.txt`). It goes faster if you stop what feeds it first and let
  it run a few minutes to empty its belts and chests. When the same things come back elsewhere, a
  factory moved: `fk merge` joins factories where they stand. `report_bom --stock live` says it
  too when the paste takes up machines, or belts and pipes that carry now, while what it lays is
  SHORT: those stop until the new ones are built (`stop_on short-stock` holds such a paste)
- `two-nets`: one machine input or output on two nets
- `rate-not-met` / `target-not-met`: a rate you asserted, or the surface's target, is not met on paper (or,
  after a build, as routed)
- `size`: an `n=auto` row can't meet a target, an assert or what its consumers ask (the line says
  what stops it: the row is at the top of its bounds, a requester chest gives its rate, a row with
  a written count runs at full speed); after the routing, a net of a sized row that asks more
  than its belts or inserters carry
- `does-not-fit`: a sized row runs past its plot or into another instance's frame at the count it got;
  the build stops at `place` when their entities would overlap
- `overlap`: two sealed modules' frames share tiles. Both modules' routes may use them, and each
  is in the way of the other's; a port that opens inside the other module's frame is named, since
  a net from outside both can't reach it. Only two entities on one tile stop the build
- `too-thin`: a machine (or a chest with a rate, or the labs) runs short of a net's item as laid,
  and some of the net's belt lanes or inserters run full: the line says what is required there,
  what they carry, and who runs short. Lanes count one at a time (7.5/s yellow); on a belt two
  nets share, each net has its own. A chest without a rate beside machines on a net takes what
  they leave, so it is never short and asks nothing of the belts. The ways past one: `tier
  minimize --allow yellow,red` in the build script (red lanes carry 15/s), a second row, or a
  second belt
- `no-route`: no belt route was found for a net (the reason follows: often a row is boxed in;
  leave a few tiles free around a row's head, where its belts attach). The default build script
  stops on it, so nothing is pasted
- `no-destination` (report_checks): a maker whose product reaches none of the consumers of its net, so
  what it makes has nowhere to go. The default build script stops on it too; report_checks'
  `sinks` line counts the makers that reach a sink
- `unused`: a declared net that no machine and no belt uses
- `partly-connected`: a net's route doesn't reach every machine (the line says how many of its driver->consumer pairs connect)
- `bootstrap` (report_checks): a net's own route needs a building item (a belt, an underground, a
  splitter, an inserter) whose only maker in the factory takes an item from that same net, so
  neither can be built first. The line names the item, how many the route lays, the maker and what
  it takes from the net: stock that item first, or build that maker first. No line when the item
  comes from outside or another maker is fed elsewhere
- `no-robots`: a logistic chest outside every logistic area of the main robot network (robots
  won't serve it), or entities outside its construction area (robots won't build them). The kit's
  roboport at 8,8 serves chests 25 tiles each way and builds 55 tiles each way; `cover robots`
  gives a factory a roboport only for the chests no roboport of that network reaches yet (the
  kit's, and every one joined to it), which joins the network when it stands within 50 tiles of
  another one on both axes. It puts a storage chest beside each roboport it places, so what the
  robots take up there is stored there and not at spawn (`cover robots --storage none` leaves
  the chest out). Grow outward: the next factory within reach of the last. It chains only from
  roboports that stand, or that it lays in reach of them (2.1.3): a roboport no robot could reach
  is not placed, and the factory's line says what stays uncovered. When a paste moves a roboport,
  the old one is ordered out (robots take it up and carry it to the new spot), and an old roboport
  is ordered out at once when the network holds none for the new ones; otherwise the old ones
  stand until the new ones do
- `on-water-or-cliff`: something designed stands on water or a cliff
- `no-water`: an offshore pump whose water side is dry ground (it gives no water)
- `by-hand`: the build replaces or removes something someone placed by hand: who (when the game
  names them), what, where, and on which design entity's tile. The design wins, so the build goes
  on; adopt it into your source, leave it out, or come back to it. A Claude lead hears it like
  chat (`out\hand.txt` keeps every one). It also names settings changed by hand on what the
  toolkit placed, with what the paste does: `rory_618 changed inserter at 14.5,0.5 (mall/i0):
  logistic=copper-plate>7 (the paste sets logistic=iron-plate<50)`. A build sets every setting
  back to the design's (condition, request, filter, chest limit, recipe), cuts a wire the design
  lacks and adds one it has. To keep it, write it into the source (`logistic=copper-plate>7`);
  `stop_on by-hand` holds a paste until you have
- `re-laid` (diff, before the paste): belts, undergrounds, splitters or inserters stand on their
  design tiles under the right name but facing another way (or as the other underground end), so
  their line stops there. A factory built over another keeps the old one's belts wherever the
  names match, facing the old ways. The build orders each out and lays it fresh; `out\apply.txt`
  lists them under re-laid. One a player turned by hand is also a `by-hand` line
- `not-where-designed` / `no-position`: the paste did not land where the design says
- `short-stock`: the network holds fewer of an item than the build still needs
- `needs-research`: an item to build, or a machine's recipe, isn't researched (the technology and its
  cost follow)

These describe a state - what is missing, what stands elsewhere, what happened - and the usual
## When you need something

```
fk stock                         what you have, per item (free to read): robots in chests count,
                                 and a robot in a chest does nothing until it is in a roboport
fk plan ITEM RATE                the machines, furnaces and drills a rate takes, every step down to
                                 the ore (fk plan ITEM --machines N: what N machines take)
fk build --to size               the counts of your n=auto rows and what each one serves
                                 (out\size.txt), nothing laid out
fk stage list                    the plan: the stages after what is built, and how far it reaches
                                 ("Planning ahead")
fk stage check N                 a planned stage built on paper in its own folder, stages\N
fk lab NAME --from stages\N      that stage built for real on its own lab slot; then
                                 fk lab NAME --measure 60 for what it really makes ("The lab")
fk explain main.fk gears         one row as its template and as the entities and nets it becomes
fk explain main.fk NET           one net: its items, drivers, consumers, lanes, buffers and the
                                 string its limited gives
fk build --to diff               what the next build would take up, and how long the robots need
                                 (a dry run: nothing written, nothing pasted)
fk fresh X0,Y0,X1,Y1             belts and pipes there with old items or fluid in them,
                                 inserters stuck holding an item their machine doesn't use, a
                                 crafter whose output holds what its recipe no longer makes, and
                                 a chest its crafters fill holding what none of them makes now,
                                 are taken up; the next build lays them fresh
fk merge . A,B --into C          two factories become one, both kept where they stand
fk chests-to-net . C PROV REQ    a robot link (provider chest to requester chest) becomes a belt
fk net-to-chests . C NET --provider P --requester R
                                 a belt becomes a robot link
fk unfold main.fk gears          turn a row into a Literal (its entities pinned as they are)
fk split-to-chest . main NET box --at X,Y [--requester --item I]
                                 a chest joins a net as one more endpoint (a buffer, a tap)
fk adopt X,Y --into main/NET     a belt you placed by hand becomes part of that net's route
fk dnp world.fk NAME[,NAME] [--off]
                                 do not populate: that piece stays laid out and routed but isn't
                                 built, and the model has nothing of it (--off: built again).
                                 A Stack's built=K does the same for its cells past K
                                 (LANGUAGE.md, "Laid out, not built")
fk build --confirm               also take up what stands built on DNP pieces (without it, it
                                 stays: fk look says dnp-standing)
fk build --reroute NET[,NET]     those nets laid anew (an instance's name: every net inside it)
fk build --with 'STEP OPTS'      a step's options for this build only (--with 'cover robots --fresh')
fk decon X0,Y0,X1,Y1 [--name E[,E]] [--cancel]
                                 the deconstruction planner, as you'd drag it: robots take up
                                 what stands there (only those entities, with --name), or the
                                 orders go back. What the design still has there, the next build
                                 lays again: take it out of the .fk as well
fk capture lab NAME              something built, as a file a Literal reads: a lab slot, an area
fk capture world X0,Y0,X1,Y1     of the game (fk sim game capture world ...: of the planner), or
fk capture design [FACTORY/]INST an instance of your laid-out design. Then
                                 X = Literal<file="captured/NAME.json"> @(x, y) puts it anywhere,
                                 inside a module too, and fk sim place takes the same file. The
                                 file names its machines (asm1, furnace1, ...): X.asm1 is a net end
fk measure X0,Y0,X1,Y1 [--seconds 30]
                                 what the machines in an area really make, against the model
fk stats [--items iron-plate,copper-plate] [--window 10min]
                                 production statistics (free to read), made and used per item;
                                 windows 5s, 1min, 10min, 1h, 10h, 50h, 250h and 1000h, as the
                                 production panel's. --fluids for fluids
fk stats --items iron-plate --window 1h --series 30
                                 the panel's graph too: made and used per minute in 30 points
                                 over the window, oldest first
fk stats --history               the run's history: the research first (rate and time left),
                                 then the latest 5-minute window (capital and how much of it
                                 works, the top items made and used per minute, power made and
                                 used per kind, the machines per state and the recipes that
                                 mostly stand) and the trend (the last 30 game minutes against
                                 the 30 before). The run keeps a sample every 5 game minutes by
                                 itself, in game\out\stats
fk stats --page                  the run's stats page, game\out\stats\index.html: every series
                                 over game time (research, capital, power, machine states, each
                                 item and fluid made and used)
fk stock                         what the base holds, per item: chests, roboports, your pack and
                                 the robots in the air (free to read). A robot in a chest is an
                                 item and does nothing; the line says how many are flying, how
                                 many in roboports and how many in chests
fk capital [--area X0,Y0,X1,Y1]  working capital (free to read): what the base owns in raw units,
                                 working against idle. Working: machines as they ran since the last
                                 read, robots in the air, research whose unlocks are in use. Idle:
                                 every item anywhere (malls' stock too), machines that stood, robots
                                 in roboports, research nothing uses. Belts, inserters, poles,
                                 chests, roboports and power are left out. The world line carries it
fk capital --park X0,Y0,X1,Y1 --why TEXT
                                 leave an area out of it on purpose (it stays in the report as
                                 parked); --unpark N counts it again, --weight TECH=W weighs a tech
fk chart                         how much of the map is explored (free to read)
fk alerts                        the alert panel now (new alerts also come by themselves)
fk lua "CODE"                    run a Lua chunk in the game: its rcon.print comes back (read,
                                 investigate; see "Reading the game yourself")
fk lua --file probe.lua          the same with a file of yours
fk research                      what can be researched now, cheapest first, and what is running
fk research TECH [TECH...]       queue research, each after its unfinished prerequisites (labs
                                 and science packs do the rest); --first puts them at the front
fk tech NAME                     a technology, or what opens an item or recipe: cost (or what to
                                 craft or build for it), what to research first
fk recipes [NAME...] [--enabled] the locked recipes (or the enabled ones) and what opens each
fk read-terrain --surface nauvis --area X0,Y0,X1,Y1
                                 read more bare ground into map.terrain.json: the new area is
                                 merged into what the file had (--replace: the area alone)
fk request X,Y|KEY ITEM N [--name E] [--inventory NAME]
                                 an item request on a standing entity (a turret's ammo, a
                                 machine's modules, a chest's stock): robots bring N of ITEM
                                 from the network. It only asks: it says when the network holds
                                 less, or no roboport's area reaches the entity
fk chat                          the chat messages you have not dismissed yet
fk say "text"                    one line in the game chat
fk ack                           dismiss them (the only way; until then they keep coming back)
```

A chat message is not shown once and gone: it appears at the end of every `fk` command until you
`fk ack`, so a pipe (`| Select-Object -First 30`) that drops it costs nothing. Answer first, then
ack: `fk say "on it: belting the ore now"`, do the work, `fk ack`.

Every command takes `--help`.

## Programming the game yourself

You can code, and the game is open to it at three levels. Use whichever fits what you're doing:

- **fk commands.** Each is Python sending Lua over RCON. All of it is readable in
  `.toolkit\fkcore\`: `link.py` holds most of the Lua chunks the commands send (`lua_decon_area`,
  `lua_paste`, `lua_snapshot`, ...), and `lab.py`, `sim.py` and `capture.py` hold their own.
  When a command does almost what you want, read its Lua and change it.
- **Lua** (`fk lua`), for anything the game API can do that no command does yet: a
  deconstruction order with a filter of your own, a ghost grid, a question about the base.
  Writing a few lines of Lua is often quicker than looking for a command that does the same.
- **Your own scripts.** Python or PowerShell that chains `fk` commands and Lua chunks: a loop
  that tries five layouts with `fk build --to report_checks` and keeps the best one, or a
  probe that reads many machines at once. The ones you'd write twice go in `helpers\`.

A planner who designs one factory at a time may never need more than the fk design commands. A
player expanding, scouting or fighting, or trying an odd build, usually gets more out of Lua and
scripts. The rules are the same either way (`FAIR-PLAY.md`): you build by ghosts, and you may press
any button a player could press. A Lua loop that places ghosts in a grid is a paste of your own,
and so is a Lua deconstruction order:

```
fk lua "local s = game.surfaces.nauvis for i = 0, 9 do for j = 0, 3 do s.create_entity{name = 'entity-ghost', inner_name = 'solar-panel', position = {100 + 3 * i + 1.5, 40 + 3 * j + 1.5}, force = 'player'} end end rcon.print('ok')"
fk lua "for _, e in pairs(game.surfaces.nauvis.find_entities_filtered{area = {{-30, 74}, {8, 96}}, name = 'transport-belt'}) do e.order_deconstruction('player') end"
```

What you place outside the design reads `marked` in `fk look` and is kept for now. To keep it for
good, `fk capture world X0,Y0,X1,Y1` it and put the file in your design as a `Literal`. A build made
that way (in the lab, in the planner, or by hand) goes anywhere afterwards, a module included.

`fk lua` sends a Lua chunk to the game over RCON and prints what it `rcon.print`s:

```
fk lua "rcon.print(game.forces.player.current_research and game.forces.player.current_research.name or 'none')"
fk lua "local n = 0 for _, g in pairs(game.surfaces.nauvis.find_entities_filtered{type='entity-ghost'}) do n = n + 1 end rcon.print(n)"
```

The chunk goes to the game as you wrote it, lines, comments, quotes and all, and a long one is
fine (a file of 40 kB works). A big answer is better written to a file
(`helpers.write_file('mine.json', helpers.table_to_json(t))`) on the game host and read there. For a script of your own, the game host is `computah-ct`
(`ssh computah-ct`); `run.json` names the toolkit there (`host_toolkit`: `fkcore.link.Rcon` is
the RCON client) and your game codebase there (`host_game`).

What a script of yours may and may not do is in `FAIR-PLAY.md`. (`fk fresh` is the toolkit's own
example of a multi-stage build action: it takes up the belts, inserters and crafter output that
hold stale items, so the next build lays them again.) The link refuses Lua that registers an event
handler, a command or an interface: that made every save unjoinable once. Reusable helpers go in
`helpers\` (its README says how). Try risky Lua on the planner first (`fk sim game lua ...`): it
is your map, and nothing there touches the real game.

## The surface file and the world design

The world is two files. `game\nauvis.surface` says what is true of the world itself, and
`game\nauvis.fk`, the **world design**, says where the plots go:

```
# nauvis.surface
surface  nauvis
mode     play                                 # fair play: you see where you look; alerts come to you
terrain  map                                  # map.terrain.json: the bare ground, read at kickoff
catalog  base
design   nauvis.fk                            # the plots, from the world design

watch plots:      keep                        # something placed by hand in a plot: kept, listed
watch sanctioned: mark 2h                     # ... outside every plot: marked for two hours
notify   nearby                               # alerts for what is built: nearby, all or off
target automation-science-pack 10/min         # a rate the whole surface should make
```

```
# nauvis.fk: the world design
import World from "world.fk"

world = World @(-1000, -1000) size 2000x2000  # your base, and the only plot there is
```

Every top-level sealed instance of `nauvis.fk` is a **plot**: the instance's name is the factory's
name, the file it is imported from is the plot's `.fk` (its layout is that file's `.fkp`), `@(x, y)`
is the plot's corner in **map coordinates**, and `size WxH` (or the file's own `size` line) is its
ground. `gap N`, `retired`, `temporary until ...` and `@patch(resource)` go on the instance line as
they went on a `place` line. `design` wins over `place` lines: while it is there, a plot is an
instance and a `place` line names nothing.

A plot owns every tile inside it, and a plot may not overlap another or hold the surface's own
buildings: that is why a template gives a new run **one** plot and declares what stands inside it.
The starter kit (`kit.fk`, a `Literal` of the kickoff's own entities) and the reactor with its pole
line (`plant.fk`) are part of the world design, so they are the plot's, and the ground is free for
the base's own factories.

A factory's own `@(x, y)` positions are inside its plot: (0, 0) is the plot's top-left corner.
Plots never overlap. A plot can be moved by changing its `@(x, y)` alone: the build takes up what
stood on the old ground.

Without a `design` line the older form still works, one plot per line:

```
place iron = iron plot 40,-20 30x30          # factory iron, from iron.fk, on its own plot
```

`fk migrate-surface` writes a world design from a surface's place lines, and `fk look --source
design` draws the surface as designed rather than as built.

## The build script

`game\nauvis.build.fkb` is the list of steps `fk build` runs: one step per line, each reading
what the steps before it made. Keep it, or tweak it: leave `apply` out while you design. Its
`stop_on no-route no-destination cannot-carry` holds a paste with a net unrouted, a maker whose
product reaches no sink, or a machine on a net whose items it takes none of (the 2.1.3 upgrade
adds `cannot-carry` to an older script); `stop_on reach` holds one with ghosts no robot reaches,
and `stop_on no-power` one whose poles reach no generation. Add `stop_on no-feed` before a big
paste so that check stops it too (`stop_on short-stock`
holds the paste until the network has what it lays: report_bom says when a paste would take up
running machines while their replacements are short). `size`, after `elaborate`, counts
the `n=auto` rows (`fk build --to size` stops there). `fk build --from route --to
report_checks` runs part of it (`report_rates:2` names the second `report_rates`). It starts
from the layout the last build left, or lays it out again when a source file changed since (and
says so); `fk look` says when the source has moved on from the `.fkp` files it judges.
`tier minimize --allow yellow,red` lays red belts where a yellow lane is too thin for what the
design asks (`--red 20` caps how many; `tier maximize` uses the fastest allowed everywhere; the
default `--allow yellow` keeps every belt yellow). A belt never goes down a tier unless you add
`--downgrade`.
`route --hand inserter` links machines with plain inserters
instead of fast ones (rows take `inserter=inserter` for the same). `--hand any` (the template's
line) is usually better: the router lays the **lowest** hand the network can build (a plain
inserter, 0.86/s), and the `hands` step raises only the connectors whose flow needs more
(`out\hands.txt`: `hand minimize ... 41 inserter, 8 fast-inserter; 8 changed`). The flow it reads is
the design's demand through every connector with no capacities (`routed.required`), so it does not
depend on the hand laid: a stone furnace (0.33/s all in) keeps plain hands, a gear assembler (2
plates/s in) gets fast ones. `hands maximize` takes the top rung everywhere; `hands minimize
--downgrade` may also take a standing fast hand back to plain; a rung the network cannot build now
is skipped and the line says so. A route that already
stands keeps its carriers, so `--hand any` renames the standing hands robots cannot build to the one
they can (`out\route.txt`: `rehanded 2 standing inserters robots cannot build, to inserter`), and
leaves a hand that stands built alone. `cover power --pole
any` and `floorplan --bridge-power any` do the same for poles: medium poles where the network can
build them, small ones otherwise. The choice is written to `out\avail.json` by `report_bom --stock
live` (and `fk avail --save`), the design half of a build runs on the laptop where there is no game
link, and `out\route.txt` / `out\cover_power.txt` say what was taken and why.
