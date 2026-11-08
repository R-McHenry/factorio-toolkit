# The toolkit (3.1)

`bin\` is on your PATH: `fk` is the one command, and it reaches the game for you. Your world is
`game\`: the factories (`.fk`, your base's plot among them), the world design `nauvis.fk` that
places the plots, the surface file `nauvis.surface`, the build script `nauvis.build.fkb`. Edit
those with normal file tools. The `.fkp` files beside them are the layouts the toolkit writes:
read them, never edit them. The language is in `LANGUAGE.md`, worked files in `EXAMPLES.md`, the
game's rules in `FAIR-PLAY.md`. Every command takes `--help`.

## Commands

Design, on paper (no game):

```
fk check FILE.fk                 the netlist checks (no-feed, no-taker, cannot-carry, ...) and advice
fk rates FILE.fk [--hand N]      every machine's utilization, every net's supply and demand, buffers;
                                 then the routed rates on FILE.fkp as last laid out
fk plan ITEM RATE|--machines N   the machines, furnaces and drills a rate takes, down to the ore
fk explain FILE.fk INST|NET      one instance as its entities and nets; one net and what limits it
fk contract FILE.fk              every sealed module's ports with the rates they need and get
fk unfold FILE.fk INST           turn an instance into a Literal (its entities pinned as they are)
fk dnp FILE.fk NAME[,NAME] [--off]   do not populate: laid out and routed, not built
fk migrate-origins FILE [--write]    a design written before 3.0.1 laid as it was laid
fk migrate-surface [--mode-only]     a surface file written before 3.1 (`mode`) as properties
```

The build and its steps:

```
fk build [--to STEP] [--from STEP] [--with 'STEP OPTS'] [--reroute NET] [--confirm] [--yes] [--wait]
                                 the build script, in the background (game\out\build.log)
fk status [NET]                  the nets as the router left them, the unrouted with reasons, the
                                 compiled store, the build log's last lines
fk route NET[,NET] [--with ...]  lay those nets again now, every other route kept; nothing pasted
fk route --try X,Y X,Y           how a belt would go from tile A to tile B; nothing laid
fk place | fk report KIND        one step of the script alone (report_checks, report_rates, ...)
fk hold NET | fk unhold NET      keep a net's route as it stands in every build / let it go
fk unroute NET                   drop a net's route; the next build routes it again
fk seed NET ['splitter X,Y S' ...]   pin a piece of a net; the router lays the rest through it
fk compile MODULE                route a sealed module's inside once and store it
fk wait 90s | built AREA | build | 2m -- CMD   the one way to wait (a fixed budget)
```

Looking at the world:

```
fk look X0,Y0,X1,Y1 [--design] [--zoom N] [--layers all] [--image]   that area, against the design
fk walk X,Y [--up 3] [--down 2]  what the machine there waits on, up and down its belts
fk walk X,Y --frame X0,Y0,X1,Y1  a module frame drawn on the base: ready port lines
fk measure X0,Y0,X1,Y1 [--seconds 30]   what the machines there really make, against the model
fk robots [X0,Y0,X1,Y1]          the roboports that stand against the design's chests: how few would do
fk placements                    the registry of what was pasted where (Placements)
fk paste FILE --at X,Y [--rot R] [--as NAME]      a captured file or blueprint string as ghosts, recorded
fk register X0,Y0,X1,Y1 MODULE[/INSTANCE] | --as NAME   what stands there is that artifact
fk capture --from ID|AREA --into FILE             what stands, as a Literal file anchored where it stands
fk diff ID|X0,Y0,X1,Y1           the diff of a placement or an area; fk look ID works too
fk adopt ID|AREA [--write]       `set` lines proposed for settings changed in the world
fk read-terrain --surface S --area A [--entities] [--replace]   bare ground, and what stands, as constraints
fk stats | --items A,B | --history | --page   production, the run's history (free reads)
fk stock | fk capital | fk chart | fk alerts | fk research [TECH] | fk tech NAME | fk recipes
fk chat | fk say "text" | fk ack  the game chat; ack dismisses what you have read
fk lua "CODE" | --file F         a Lua chunk in the game; its rcon.print comes back
```

Changing the world besides the build:

```
fk alone NAME [--surface S] [--size WxH] [--keep] | --measure S | --clear | --list
                                 a module built alone on a slot of a surface (default lab)
fk standin NAME supply|feed|ore  god-mode stand-ins on it, where things are free
fk lab NAME [...]                alone --surface lab, then supply and feed ("the lab surface")
fk capture slot|lab NAME | world AREA | design [FACTORY/]INST [--to FILE]
                                 something built, as a file a Literal reads
fk adopt X,Y --into FACTORY/NET  a belt placed by hand becomes part of that net's route
fk fresh X0,Y0,X1,Y1             belts, inserters and crafters holding stale items taken up
fk decon X0,Y0,X1,Y1 [--name E] [--cancel]   the deconstruction planner, as you'd drag it
fk request X,Y|KEY ITEM N        an item request on a standing entity: robots bring N
fk merge . A,B --into C          two factories become one, where they stand
fk chests-to-net . C PROV REQ | fk net-to-chests . C NET --provider P --requester R
fk split-to-chest . FACTORY NET NAME --at X,Y [--requester --item I]   a chest joins a net
fk catalog learn NAME... | --mod M | --all-mods | show [NAME] | forget NAME   a building the catalog lacks
fk stage list|insert|edit|check|next|done|rebase|drop|reorder   the staged plan ("Planning ahead")
fk map save|saves|load|restart|pause|resume   the live map
fk sim ...                       the speedrun planner, your own copy of the map
```

Every command ends with the game's new alerts (grouped per kind), Rory's new chat lines and the
research line: the research under way, its progress, the packs the labs used in the last game
minute and the time left at that pace (`research military-3 34%, 41 packs/min, ~22 min left`).
It is loud when nothing researches (`RESEARCH: NONE`) and when the labs used no pack in the last
minute while a research is queued (`RESEARCH STALLED`, with the cause when the game shows it). A
chat message comes back at the end of every command until you `fk ack`: answer first (`fk say`),
do the work, then ack.

## The loop

Design on paper, build, look. `fk rates` and `fk check` run on the laptop with no game; `fk
build` runs the script and pastes; `fk look` compares what stands with the design.

### Waiting

Only `fk wait` waits, from a fixed budget. `fk wait 90s` waits that long, `fk wait built
X0,Y0,X1,Y1` until the robots have built the area, `fk wait build` until the background build is
done (its exit code), and `fk wait 2m -- COMMAND` runs a command and stops it at the cap (in place
of `timeout`). It asks first: run it again, or add `--sure`. The run has 30 minutes of waiting in
all; `wait-budget.json` in your folder says how much is spent. Anything long goes in the
background while you keep working.

### What `fk rates` says

Every machine's utilization, every net's supply and demand and what limits it (the binding
chain), then a line per buffer item (LANGUAGE.md, "Buffers"): what comes in minus what goes out.
Draining is the line to grow. Drill numbers are base rates; the game adds mining productivity.

```
BUFFER b: +60.0/min iron-ore (filling: in 60.0, out 0.0)
BUFFER b: -52.5/min iron-ore (draining: in 60.0, out 112.5)
BUFFER e: +0.0/min iron-plate (steady, its gated sources top up what goes out: in 150.0, out 150.0)
```

One thing it gets wrong on purpose: it shares a short net in proportion to what each machine
wants, but the game doesn't. The machine that reaches the items first (the first inserters along
a belt, one side of a splitter) takes its fill, and the ones further on get what is left. So a net
that is short on paper starves its far machines: give it more supply than demand, and give a chest
on it a `limit=` (`SHARED_SINK` says where). A bus is a pool on paper; along the real bus the first
tap takes its fill first.

After `fk build`, `out\report_rates.txt` also has the **routed** rates: what the belts and
inserters as laid let through, with the first machines along a belt served first. A belt lane
carries 7.5 items/s (yellow; red 15, blue 22.5, turbo 30), a fast inserter 2.5/s, a long-handed
one 1.2/s, a plain one about 0.85/s, more with the inserter capacity research (the build uses
your force's as the last build saw it). `fk rates main.fk` shows the same routed section after
its nominal one, on `main.fkp` as the last build laid it out.

A net is one lane until it needs two. A line's inserters drop on one lane, so one line on one side
carries at most 7.5/s on yellow, and the routed rates count it so. A net that carries more and has
two or more makers goes on both lanes (the router puts half its makers on each). Two nets can
share a belt, one on each lane (`lanes ore_ | fuel`): one belt instead of two, and a full lane
holds only its own items. A mixed net from a requester of several items is the jam to avoid:
write it `split` or feed each maker by one inserter straight from the requester. An inserter that
loads a belt from a chest of several items is filtered to its net's items (`unfiltered` in the
route report names one that can't be).

With Bob's inserters (Sea Block; the pack's `SEABLOCK.md`), an inserter may pick up and drop on
any side and reach further after research. The router lays only what the force has researched, as
the last stock read saw it (`out\avail.json`).

### The build

`fk build` runs the steps of `game\nauvis.build.fkb` in order, in the background: it returns at
once and writes one line per step to `game\out\build.log` (its last line: `fk build: done, exit
N`). `fk status` shows the nets as the router lands them and the log's last lines; `fk build
--wait` runs it here instead. One build at a time in a run: a second waits for the first. Each
step writes `game\out\<step>.txt`: read the one that matters (`report_checks.txt`, `route.txt`,
`apply.txt`). `fk build --to report_checks` is design only, nothing pasted; `fk build --to diff`
is a dry run: the design against the world and what the build would take up, nothing written.

A build changes only what changed in the source. Unchanged rows and routes stay where they are,
and a net is patched when a machine or a port is added to it, taken off it or moved. Any step
takes options for one build without editing the script: `fk build --with 'cover robots --fresh'`,
`--with 'route --effort high' --with 'tier --allow yellow,red'` (repeat `--with`; the step's own
options stay, yours win).

A build never quietly undoes what was changed in the game. The diff step lists every hand edit
the paste would replace, remove or set back (a pump you placed, an inserter upgraded by hand, a
filter), and `stop_on by-hand` in the build script holds the paste there; `out\diff.txt` names
each one. Put the ones to keep into the design (`fk adopt`, a Literal, a `set` line) and build
again, or `fk build --yes` pastes over them for that one build.

**Rebuilds keep what the design keeps.** The poles and roboports a build laid stay wherever the
new design leaves their spot free and the cover still wants one there; new ones go only where
something new needs them (`out\cover_power.txt` says how many were kept; `--with 'cover power
--fresh'` or `'cover robots --fresh'` lays them all anew for one build). Switching the pole kind
(`cover power --pole small-electric-pole`) lays the new kind everywhere the cover needs a pole;
the old ones come out as differences in the diff. `--pole any` switches by itself: medium poles
while the network can build them, small ones when it cannot. Old poles and roboports the design no
longer has stay up until the design's own stand there, and the first build after that takes them
up (a roboport comes out at once only when the network holds none for the new ones). Nothing in
the world moves the plan: a pole or roboport that stands where the design has none is the diff's
difference, never an input ("Bounds and obstacles", below, is how you make the world a constraint
on purpose).

**Routes stand too.** A net with a new machine or port keeps its belts and gets only a branch to
it: a splitter in place of a straight belt, the belt's end run on, a side-load (a new driver), or
an inserter straight off the belt. A machine taken off a net takes its branch with it; a machine
moved gets a new branch where it stands. `out\route.txt` says `patched` with how many carriers it
kept. When no branch fits, a net with belts is never laid anew by itself: its belts stand, the new
end alone fails (`FAILED net: its standing route is kept as it is ...`, a `no-route` check), and
`fk build --reroute NET` lays the net anew when you want that (`--reroute mall1`: every net inside
mall1). The route follows the net's ends, not its name. The design the next build keeps to is the
one the last full build wrote (`write_layout`, just before the paste); before it replaces a
`.fkp` it keeps the one before in `out\fkp-history\` (the last 8 of each).

**Room for routes.** Most routes that fail have no room:
- A belt fed into a machine by an inserter takes 2 tiles beside it. Two machines that share a
  belt between them need 3 tiles apart. A 1-tile gap holds only a direct inserter.
- Keep a module's ports and new machines off the path of a main belt that stands: a port on its
  path lays the main anew (`routed again` in `out\route.txt`).
- For one far consumer of a main, a requester at the hub costs less than another branch.
- A patch that won't fit fails alone and leaves the rest standing. Move the new machine a few
  tiles, or `--reroute` the net it joins, before you redesign the block.

A net that finds no way through another net's belts may cross by promotion: a straight run of the
other route turns into an underground pair under the crossing. Only where nothing else changes
(straight for two belts either side, no inserter or drill on the three belts, nothing side-loads
there). `out\route.txt` names each in a `promoted` line, and each takes 2 undergrounds from stock.

### How route works, and what you set

Each net is routed **once**, in order, and keeps what it laid. A net that fails is tried again
together with the nets laid near its ends (up to `--group-max 8`), in new orders, for up to
`--group-budget 3` seconds; if they don't all fit, the old routes stay and the net gets one last
search of its own. `--group-budget 0` routes every net once and alone. These go on the `route`
line of the build script or in `--with 'route ...'`:

- `--first coal,fe3p,mall/*` routes those nets first, in that order (names or patterns).
- `--skip st3o,oil/*` leaves those nets to you: route.txt says `manual`, and they never stop the
  build. Lay them yourself (a Literal, `fk adopt`).
- `--retry-failed changed` (the template's): a net that failed is not searched again while its
  ends and the ground around it stand as they did; its last reason stands, "not searched again".
  Change something near it, or name it (`--again NET`, `fk route NET`). `always` searches failed
  nets every build; `never` leaves them until you name one.
- `--failed keep` (the template's): a net that fails keeps the route that stood where its tiles
  are still free, so the paste goes on. `--failed drop` loses it.
- `--area X0,Y0,X1,Y1`: only nets with a belt or an end in that rectangle are routed again; every
  other route stands exactly as it is. The way to rework one region.
- `--ug red|blue|turbo` (default `any`, the fastest tier the network can build) lets a tunnel
  reach that far. `--pipe copper` lays fluid nets in that material (default the pack's).
  `--m2m` lays a net of several drivers and consumers above one lane as a network of runs, with a
  `MAXFLOW` line. `--hand any` lays the lowest hand the network can build ("The build script").
- Fluid nets get one pass too.

The route step writes one file per net as each one lands, `out\design\<factory>\nets\<net>.net`:
its status (routed, kept, patched, unrouted with the reason, held), its seed, then its carriers.
The next build starts from these files, even when the last one stopped mid-route, so it routes
only what changed.

- `fk status [NET]` reads them, during a build too: counts per status, the unrouted nets with
  reasons and times, the net the router is on now, and the compiled store's lines.
- `fk hold NET` keeps a net's route as it stands in every build (until `fk unhold`), even while a
  build runs: the router takes it when it reaches it. You may edit a net file by hand (its
  carriers, or `# status: held`); a held net is an input the router keys on. `fk unroute NET`
  drops a route.
- `fk seed NET 'splitter 9,30.5 S'` pins a piece of one net (pieces are written as a net file
  writes its carriers: name, x,y, direction, `ug=in|out` for an underground). Without pieces, the
  net file's carriers as they stand are the seed, so you can cut a route down to the part you
  like. The rest of the net is laid through the seed. The seed stays in the net file; `fk unroute
  NET` drops it. One belt only: not lane pairs, m2m nets or pipes. Seed little: a short run of
  plain belt where the line should pass helps; splitters and undergrounds box the router in. To
  keep a whole net, `fk hold` it; to keep a dense piece, make it a sealed module and compile it.
- A net the router can't find a way for can be sent through a piece from `game\routing.fk`:
  `import Waypoint, Merge, Split from "routing.fk"`, `wp = Waypoint<item=iron-gear-wheel> @(8,
  28)`, `net gear: gears -> wp -> red, belts`. Still one net, laid in stretches the route step and
  `fk status` show together (LANGUAGE.md, "Your `game\routing.fk`").
- `fk route --try X,Y X,Y` asks how a belt would run from tile A to tile B on the design as it
  stands, every heading tried at both ends. It prints the carriers, or why there is no way.
- `out\route.txt` has a `group` line for each net that got a group try, and whether it settled.

`FK_NEGOTIATE=1` in the environment turns on an opt-in negotiation pass before the nets are laid;
it is measured, not the default, and everything above applies to negotiated nets too.

A **ribbon** (a `net each`, a `bundle`, a `width 8` net) is routed as one: each net gets a line,
then one for the ribbon (where it starts and ends, its turns and crossings, which belts went under
and where, a tunnel's length and tier). A ribbon with no path fails every net of it and lays none.

### Sealed modules compile once

Each sealed module (one with ports or a `size`) is routed alone in its frame, the innermost first,
then the nets outside them: a net that fails in one module is tried again with that module's nets,
never the whole design's, and a world net's group try lifts only the modules it enters. A module
whose twin (the same module, the same things standing in its frame) was laid earlier in the build
takes the twin's routes, moved to its frame.

Every module routed whole is stored, in the one compile store `game\out\compiled\<module>\<key>.json`
(`current` beside it points at the last key laid). The key is a hash of everything the inside is
laid to: the frame's size and what stands in it, each net's ends, items, lanes and taps, the
children's keys, the catalog and terrain facts, the router's settings, seeds and held routes, and
the router version. A build that places the module lays the stored inside wherever it stands now
and routes only the nets that cross frames: a second copy, a move or a rebuild routes no inner
net. `out\route.txt` says `compiled  P: k nets laid from the store (MODULE key)` and `compiled
stored MODULE`, and the summary `N routed, M kept (... K laid from the compiled store)`. A stored
entry holding an entity the force can't build yet is not taken (`not researched here: routed
again`).

- `fk compile MODULE` routes the inside now, alone, and stores it; the next world build lays it.
  A build stores every sealed inside that routed whole, so you rarely need it.
- A module built alone on the lab (`fk lab`, `fk alone`) from your game folder writes the same
  store, so try a module on the lab, then place it in the world. `--with 'route --reuse-lab'`
  reads the lab builds' own stores too, for a lab built elsewhere.
- Change anything inside and the key changes: the module routes again and stores the new inside.
  Nothing to clear. `--with 'route --compiled no'` (or `--store none`) routes every inside afresh;
  `--store DIR` keeps the store elsewhere.
- Entries written by an older router (a flat `out\compiled\*.json`, or `out\design\modules`) are
  not read; the route step and `fk status` say so once. They are reference only.

### After the route: circuits, the paste, robots

Steps after a `later:` line in the build script run once the rest is done, the paste included:
reports only, off the critical path. Put the slow routed `report_rates` there.

Circuits come from the source (LANGUAGE.md, "Circuits"). The build lays them on the layout just
before the floorplan (`out\floorplan.txt`, the `circuits` lines), and the `.fkp` shows them on the
entity lines (`if=`, `logistic=`, `read=`, `filter=`) and as `wire` lines. Change a limit and the
next build writes it on the inserters that stand: the paste sets every setting, so robots make no
trip. Drills and offshore pumps take no settings from a paste, so the build lays them fresh.

A build changes what stands in one of three ways, and `out\apply.txt` names each with why:
**written in place** (new settings, or a hand edit set back), **upgraded** (another entity of the
same fast-replace group and size stands on a design entity's spot: inserter tiers, assembler 1 to
3, belt tiers, chests, stone to steel furnace, small to medium pole; robots swap it and its
settings stay), or **laid fresh** (everything else: taken up and built new).

Wires follow the design too: after the paste, and again when `fk wait built` finds the robots
done, the build adds the design's missing red, green and copper wires and cuts the ones between
your design's entities that the design doesn't have (a pole robots build joins itself to the
poles in reach; this takes that back). Wires to anything outside the design are left alone.
`out\apply.txt`: `wires: 3 added, 1 cut`.

A build also takes back what it built before and your design no longer has: a row you replaced,
the old ground of a plot you moved, a factory you emptied, its unbuilt ghosts too. The toolkit
remembers what it pasted (`out\own\nauvis.json`). A belt or pipe it lays again under another net,
while it still holds the old net's items, is taken up and laid fresh in the same build. On
uncharted ground each entity is laid as a single ghost carrying its settings; a setting the game
won't put on a ghost is named in `out\apply.txt` under SETTINGS.

After the paste, the robots build the ghosts from the network's stock. Before it,
`out\report_bom.txt` says what the network can't cover (`STOCK:`, short-stock and needs-research
per item). A ghost that stays is a blocked build, not a slow one: `fk look` marks it `ghost SHORT`
or `ghost needs-research`, and waiting won't change that.

## How many machines and drills for a rate

`n=auto` on a Stack or a MinerRow lets the build count it: the fewest machines that meet the
surface's `target` lines, your asserts and what the line's consumers take (LANGUAGE.md, "Counts
the build chooses"). `fk build --to size` shows the counts in `out\size.txt`; `fk rates` shows the
rates at them.

`fk plan` answers before you write a factory, from an item and a rate or from the machines you
want on that item:

```
fk plan chemical-science-pack --machines 15        what 15 blue science assemblers take, down to the ore
fk plan chemical-science-pack 1/s                  the same for a rate (60/min, 0.5/h; a bare number is /s)
fk plan electronic-circuit 10/s --raw iron-plate,copper-plate   the plates come from elsewhere
```

One line per item of the recipe tree: the rate it takes, its recipe and machine, how many machines
(`machines` as a fraction, `build` rounded up), and under an item that feeds several recipes
`for ...` says how much each takes. Then the raw inputs with their drills, pumpjacks and offshore
pumps. The plan runs every machine at full speed without modules: assembling-machine-2 for
crafting, stone furnaces on coal, electric drills at 0.5 ore/s. `--asm assembling-machine-1|3`,
`--furnace steel-furnace|electric-furnace`, `--mining-productivity N` (your research level) and
`--recipe ITEM=RECIPE` (an item with several recipes; `petroleum-gas=advanced-oil-processing`
shows the heavy and light oil as `surplus`) change it.

## Planning ahead: `fk stage`

`fk stage` keeps a plan of stages in git beside `game\`. `main` is what is built; the plan is one
commit per stage on top of it, each commit's message the stage's spec: goal, needs, rates, the
test that says it's done. A stage holds source only (`.fk`, the world design, the surface file,
the build script, each Literal's file); its layout is computed when it is checked.

```
fk stage list                    the stages in order, each one's plates per minute and state, and
                                 the horizon: the planned base against the built one
fk stage insert "oil plant" --goal "..." --needs "..." --rates "plastic-bar 30/min" --test "..."
                                 a new stage at the end (--after K, --first), with its folder stages\N
fk stage edit N [--goal ...]     stages\N's source into the plan; the stages after it replay onto it
fk stage check N [--render [AREA]]   stage N built in stages\N through report_checks: its checks,
                                 its rates against the stage before and its spec; --render draws it
fk stage next [--apply]          the next stage's spec and its diff; --apply puts it into game\
fk stage done [N]                game\ as it stands becomes main, stage N done; the rest replays
fk stage rebase [-m "why"]       game\ as it stands becomes main (a hand fix adopted)
fk stage drop N | reorder N --after K
```

A stage folder is a scratch copy of the whole game folder: design in it with normal file tools,
`check` it as often as you like, `edit` takes its source into the plan. When main moves, the plan
replays stage by stage; a stage whose lines reality changed comes back with conflict markers in
its files and a CONFLICT in the list: settle them, then `fk stage edit N`. Every rewrite keeps the
plan before it as a tag (`plan/rev-N`). The horizon is in plates per minute, iron plus copper; a
plan 1.5 to 2 times the built base stays about the same span of play ahead. The plan's repository
is `.stage\` and its folders `stages\`, both outside `game\`; `fk stage` changes `game\` only
with `next --apply`.

## Surfaces

A surface is a game surface with a surface file, `game\<surface>.surface`. The file says what is
true of the surface itself; the world design (`design`) says where the plots go.

```
# nauvis.surface
surface  nauvis                               # the game surface
terrain  map                                  # map.terrain.json: the bare ground, read at kickoff
catalog  base
design   nauvis.fk                            # the plots, from the world design

watch plots:      keep                        # something placed by hand in a plot: kept, listed
watch sanctioned: mark 2h                     # ... outside every plot: marked for two hours
notify   nearby                               # alerts for what is built: nearby, all or off
target automation-science-pack 10/min         # a rate the whole surface should make
```

The properties a surface may have:

- `free`: things are free there. A paste's ghosts are revived at once by script, nothing is built
  by robots, the slot of a module built alone is emptied by a direct destroy, a look may take the
  whole design as its area, and `notify` defaults to `all`. `cover robots` places nothing on a
  free surface. A file without `free` is a base: robots build, fair play applies, a look needs an
  area.
- `force NAME`: whose the paste is (default `player`). The lab's is `force lab`, with research done.
- `terrain NAME|none`, `catalog`, `design`, `notify nearby|all|off`, `remind`, `watch`, `target`,
  `robots`, `claim`, and `place` lines (the older form of plots, below).

The lab's file is `surface lab`, `free`, `force lab`; a planet's says what is true of it. A file
written before 3.1 had `mode play|lab` instead: it is still read for this release (with a note),
and `fk migrate-surface --mode-only` writes it as the properties.

```
# nauvis.fk: the world design
import World from "world.fk"
world = World @(-1000, -1000) size 2000x2000  # your base, and the only plot there is
```

Every top-level sealed instance of the world design is a **plot**: its name is the factory's, the
file it is imported from is the plot's `.fk` (its layout that file's `.fkp`), `@(x, y)` the
plot's corner in map coordinates, `size WxH` its ground. `gap N`, `retired`, `temporary until
...` and `@patch(resource)` go on the instance line. A plot owns every tile inside it, plots never
overlap, and a plot may not hold the surface's own buildings: that is why a template gives a new
run **one** plot and declares what stands inside it (the kit as a Literal, the plant). A factory's
own `@(x, y)` are inside its plot, (0, 0) its top-left corner. Move a plot by changing its
`@(x, y)`: the build takes up what stood on the old ground. Without a `design` line the older
form still works, `place iron = iron plot 40,-20 30x30` one plot per line, and `fk
migrate-surface` writes a world design from them.

Every `@(x, y)` is an origin (3.0.1): a turned instance turns about it, and a Literal's file
(0, 0) lands on it, so a row, module or blueprint that grows never moves what stood. `fk
migrate-origins FILE --write` rewrites a design written before 3.0.1.

### Building on the lab surface

The lab is a game surface like any other, with a surface file like any base's: `surface lab`,
`free`, `force lab`. None of the fair-play rules apply there (`FAIR-PLAY.md`, "The lab"), and Rory
watches it with `/lab`.

**To paste a blueprint on the lab**, build a module alone on it: `fk alone NAME --surface lab`
gives NAME.fk (or a factory the world design places) a workspace `lab\NAME` in your run folder
with a surface file that places it on a slot of its own, runs the build script there, and the
apply pastes it and revives it. `fk lab NAME` is the alias that also adds the stand-ins. A
blueprint you already have (a capture, a string) is a Literal: `x = Literal<file="captured/x.json">
@(0, 0)` in NAME.fk, then `fk lab NAME`, and it stands on its slot. The same `fk alone` builds a
module alone on any surface (`--surface nauvis`: robots build it, nothing is destroyed; the
surface's file gives its properties, the lab needs no file).

Power, stock and infinity feeds are not part of a build: they are god-mode stand-ins you ask for
by name, only where things are free.

```
fk lab NAME                      NAME built alone on its own lab slot, then the stand-ins:
                                 powered, its requester chests filled, burners given coal, every
                                 open port fed; says where Rory sees it
fk lab NAME --from stages\4      the same from a stage's folder (or a scratch copy of game\)
fk lab NAME --size 60x40         its plot size, when no plot places it (default 100x100)
fk lab NAME --keep               laid over what stands (the slot not emptied, nothing stocked),
                                 only the stale nets routed; --with "apply --area A" for one region
fk lab NAME --measure 60         what its machines really make over 60 s, against the rate model
fk lab NAME --clear | fk lab --list      its slot emptied and freed / the slots in use
fk standin NAME supply           power (an energy interface), the requesters' items, burners' coal,
                                 module requests; run again, it tops them up
fk standin NAME feed             an infinity chest and loader outside each open belt port, an
                                 infinity pipe outside each fluid port; out ports empty into a sink
fk standin NAME ore --copy-ore 272,-72,312,-40 --to 4,2     the world's ore there copied onto the slot
fk standin NAME ore --ore iron-ore --area 0,0,30,20 [--amount N] | --clear-ore
```

- A sealed module needs no lab file of its own: when NAME.fk only defines it, it is built alone
  with 4 tiles round it, and `feed` gives every port a source or a sink. In a lab file of your own,
  a sealed instance's port that no net binds is fed the same way.
- The lab has no edge. Each factory gets its own slot, sized to it in 200-tile cells, and keeps
  it while it fits; building it again empties the slot first. Drill rows get their ore seeded
  under them; `ore --copy-ore` puts a real patch's shape there instead.
- Let it run a minute or two before `--measure`: a backlog that piled up while it started reads
  as speed. `fk capture slot NAME` (or `capture lab NAME`) writes what stands on the slot as a
  Literal file.

## Bounds and obstacles

A design is laid out from its source and the terrain file, never from the live world. To keep a
factory in bounds, give it a plot (the world design's plots, or `place` lines): nothing of it is
laid outside, and `fk route --with "route --area X0,Y0,X1,Y1"` reworks one region and leaves the
rest standing. To make the design go round what stands in the world, read it in on purpose:

```
fk read-terrain --surface nauvis --area X0,Y0,X1,Y1 --entities
```

puts every built entity there that the design does not own into `map.terrain.json` as blocked
tiles (the file says when it was read and how many; `out\read_terrain.txt` too), and the next
build routes, poles and roboports round them. Ghosts, trees, rocks, cliffs and units are never
obstacles. A read without `--entities` leaves the file's entities as they were and merges the bare
ground (water, cliffs, ore) of the new area; `--replace` drops everything first. What the design
has and the world lacks, or the world has and the design lacks, is the diff's difference, never an
input to a step.

`fk robots [X0,Y0,X1,Y1]` reads the standing roboports against the design's logistic chests and
changes nothing: how many stand, how many have power and how many networks, which chests are
covered and which not, which roboports are redundant (every chest they reach another reaches too,
and taking them out splits no network), and how few would cover every chest (what `cover robots`
would lay on free ground: a lower bound to aim at, not a placement). With an area: the chests in
it and the roboports whose logistic square meets it.

## Placements (3.1)

A placement is one paste: which module (or file) stands where. The registry is
`out\placements\<surface>.json`, one record per paste: id, module and instance, artifact
(`store:<key>` from the compile store, else `rows:<sha>` of the pasted rows), origin, rotation,
area, tick, source (`build`, `alone`, `paste`, `register`). A rebuild of the same id replaces its
record; nothing piles up. Under it, `out\own\<surface>.json` still records every entity the
toolkit pasted. Every `fk build` apply, every build alone and every `fk paste` writes a record.

```
fk placements                                    the registry, every surface
fk paste FILE --at X,Y [--rot R] [--as NAME]     paste a captured Literal file or blueprint string as ghosts, origin at X,Y
fk register X0,Y0,X1,Y1 MODULE[/INSTANCE]        what stands there is that artifact; records it, reports the differences
fk register X0,Y0,X1,Y1 --as NAME                record something no module stands for
fk capture --from ID|AREA --into FILE [--names]  write what stands as source: a Literal file anchored where it stands
fk look ID          fk diff ID|AREA              the look and the diff over a placement's area, headed by its module and origin
fk adopt ID|AREA [--write]                       propose `set` lines for settings changed in the world; --write appends them
```

**The mismatch rule.** A build pastes only onto tiles it can explain. A world entity standing
(or pending as a ghost) on a design entity's tiles that the toolkit did not paste there is a
MISMATCH: the diff names it and its owner (`placement <id>`, `hand edit by <player>`, or
`unknown`), the apply refuses those design tiles, one line per conflict with the command that
resolves it (`fk register`: it is that artifact; `fk capture --from`: put it in the source as a
Literal the design mates with; `fk adopt X,Y --into FACTORY/NET`: a carrier into its net;
`fk decon` or by hand: take it out), and pastes the rest. There is no `--yes` for a mismatch: the
source changes, or the thing is registered, captured or taken out. Mating is no mismatch: an
entity standing with the same name, position and direction as the design's is `ok`, and the
toolkit's own (an earlier paste) is still taken up to the design or laid fresh. Inside another
placement's area what the design does not match is `placed` (explained, no mark); elsewhere the
watch policy (keep, mark, revert, strict) applies as before. Nothing is built over or around.

**Mating with what stands** (new source over standing objects):

1. Something stands in the world: a hand build, a `fk paste`, a registered legacy block.
2. `fk capture --from std --into captured/std.json` (or `--from X0,Y0,X1,Y1`). The file is
   anchored where it stands; the command prints the Literal line to paste.
3. Write the module: `std = Literal<file="captured/std.json"> @(10, 10)`, then what is new:
   `box = Chest<provider> @(22, 11)` and `net out: std.asm1 -> box`.
4. Place the module where its frame is the world's (the world design, or a plot at 0,0); on a
   plot at X,Y write `@(10 - X, 10 - Y)`.
5. `fk build`: the diff says `ok` for every standing entity of the block (mated), the apply
   pastes everything, the game leaves the standing ones and the new carriers are ghosts. No
   `mismatch` line, and the build's placement covers the block.

**`fk adopt ID|AREA`** reads the placement's settings and proposes source for each world edit it
can express: a changed limit, request, filter or circuit condition becomes a `set` line shown as
a diff of the module source (`--write` appends it); a changed recipe is said as the instance's
parameter; a foreign carrier beside a net is `fk adopt X,Y --into FACTORY/NET` (the V1 form,
unchanged); anything else is "needs a Literal patch", with the capture command that makes one.
It never writes without `--write`.

## Saving, loading and starting over: `fk map`

```
fk map save NAME        the live map saved as NAME (the game goes on)
fk map saves            the run's start, the map the server runs, and your saves
fk map load NAME        your map saved first (before-load-STAMP), then the server restarted on NAME
fk map restart          load start, set up as the kickoff set it up; kept as save start-set-up too
fk map pause | resume   the whole game stands still, or goes on
```

A load or restart restarts the server (about half a minute; anyone watching is dropped and joins
again). Your designs in `game\` stay as they are. Try a start-over in the planner first (`fk sim
load start`).

## The speedrun planner: `fk sim`

A second game of your own map, on this machine: same seed, same first tick, yours to try a plan
in. It never touches the live game, stands still between your commands, and runs about 20 times
real time on this laptop.

```
fk sim fetch [--live now]        your map as it stood after the kickoff (save state start), or now
fk sim start [NAME] | stop | status      the planner from a save state (default start), paused
fk sim kickoff                   the kickoff's setup on a bare start, saved as start
fk sim speed 100                 ticks run up to 100 times as fast (1 is real time)
fk sim run 3600 | until T        move the game on 3600 ticks (a minute), or to tick T
fk sim save NAME | load NAME | saves     a save state of the game as it stands; back to one
fk sim place FILE @X,Y           a design built at once and free: a .fkp, a blueprint string (.txt)
                                 or {"bp": ...} (.json), X,Y added to its own coordinates
fk sim paste FILE @X,Y           the same as ghosts, for the robots to build
fk sim remove AREA | decon AREA  everything there gone at once / ordered out, for the robots
fk sim play plan.sim             a playback: a file of actions, one a line (from, speed, place,
                                 at +N, paste, run, save)
fk sim game stats | look | lua | research ...   any game command, on the planner
```

A save state loads at the tick it was saved at, every time. The game still refuses what it refuses
in the run (a drill off its ore); `place` says how many didn't stand and why. A `.fkp` is in its
design's own tiles: `world.fkp` goes in at the world plot's corner. `place` and `paste` lay power
wires only, not circuit wires. The planner's files are in `sim\` of your run folder.

**Explore mode** (`fk sim explore on [--budget 36000] [--minutes M] [--rise 0.1]`) hands the
planning to the planner: short rounds, each loading a game it picks and giving you a manifest (a
few items, each with a total for the base to have made). Play as on the planner (`paste`, `decon`,
`fk sim game research`, `run`); every `run` reports the manifest, and a round ends when it is met
or its budget is spent (`ROUND N OVER`, the next loads by itself). A manifest may name something
far off: take the first step on the way to it this round. `status`, `next`, `off`, `archive` (the
states reached, V how far up the game, H how far off the best path), `best --to plan.sim` (a
playback to a state), `reset`. `place`, `remove` and `load` are off while the mode is on.

## What a line waits on: `fk walk`

`fk walk X,Y` reads the area around a machine (or belt) and walks its belts: each net in and out,
its items and how full each lane is, the machines that feed it and take from it and their state,
then one level further, as deep as `--up` and `--down` say. It marks where the flow stops: a
machine short of an input or with its output full, a belt empty or backed up, a lane that never
fills. The first starved machine upstream whose own inputs are fine is the place to look. It works
on any base, hand-built included (nets found from the belts as they stand, `n17`). `fk walk
X0,Y0,X1,Y1` lists every net in an area; a requester or provider chest ends the walk.

`fk walk X,Y --frame X0,Y0,X1,Y1` checks a module frame before you draw it: every belt that
crosses the edge comes out as a ready `port` line (side, position, items), and every underground
under the edge, inserter reaching over it or entity standing across it is listed. "sealable as
drawn" means only belts cross: grow the frame until it says so.

## What `fk look` says

Every designed entity in the area gets a verdict:

- `ok`: there, as designed
- `ghost`: its ghost is there and the network holds the item: robots are on their way
- `ghost SHORT`: the network holds none (or too few) of the item: make it or bring it
- `ghost needs-research`: the item's recipe isn't researched (`fk tech ITEM` says which)
- `not-placed`: nothing there (the next build restores it)
- `dnp`: DNP in the design and not built (counted, not listed); `dnp-standing`: DNP but built,
  kept until `fk build --confirm` takes it up
- `other-entity`: something else stands on its tiles
- `settings-changed`: there but turned, or with another recipe. A belt, underground, splitter,
  inserter, pipe-to-ground, pump or drill that stands turned says `re-laid`: the next build
  orders it out and lays it again as designed
- `UNPAIRED`: a built underground belt with no partner in reach, or with another end of the same
  kind, so no tunnel forms
- `other-item`: a belt or pipe holds an item its net doesn't (old items from a rebuild); on a
  shared belt, lane by lane. One the build laid under another net is renewed by itself; for the
  others, `fk fresh X0,Y0,X1,Y1` takes those belts up and the next build lays them fresh

Anything in the area the design doesn't explain is `claimed` (inside a claim, the starter kit),
`marked` (placed by hand, kept for now, listed under "changes here" with who placed it) or
`unowned` (nobody owns it; the next build removes it: this is also what the toolkit built and your
design no longer has).

### Zoom, layers and images

`fk look AREA --zoom N` draws N tiles in one cell (1, 2, 4, 8, 16 or 32); `--design` takes the
same options for the design alone. A cell shows what matters most in it: a machine, a roboport, a
turret, belt when at least half the cell is belt (its main direction `^ > v <`), a tank `K`, a
chest, an accumulator `Z`, a solar panel `Y`, a beacon `b`, a radar `r`, a pump `P`, an inserter,
a combinator `c`, a pipe, a pole, a power switch `$`, a wall `#`; `?` anything else, `.` free
ground. From zoom 8 up each plot is its outline with its name and machine count, like the map
view. Zoom 8 and up (and zoom 2 or 4 over more than 65536 tiles) reads counts per cell, not every
entity, so a look at the whole base is quick (1024 x 1024 tiles in about 1.3 s) and gives no
verdicts. On a surface that is not free a zoomed-out look reads only charted chunks; a free
surface is all charted.

`--layers NAME,...` (or `all`) adds a panel per layer, design | live, with legend lines:

- **`robots`**: each roboport's logistic area in its network's key and its construction area as
  `,`; the legend gives each network's robots. `!` is a ghost outside every construction area.
- **`power`**: each electric network's pole supply area, `X` a machine with no power, `~` low
  power, each switch `$` on or `/` off.
- **`defense`**: turret ranges (`g l f a`, `*` two kinds), `T` a turret and `0` one with no ammo,
  `x` mines, `#` walls, `G` gates, `!` a wall outside every turret's range, `@` a nest, `w` a worm.
- **`pollution`**: each chunk's pollution in bands 1 to 4, `!` a nest the pollution reaches.
- **`pipes`**: each pipeline in its own letter with its fluid and fill, `!` a machine with a
  fluid connection nothing meets.
- **`recipes`**: each machine's recipe as a short tag (`gear`, `circ`) and its status (`*`
  working, `n` no ingredients, `f` output full, `P` no power).
- **`tags`**: your design's plots (outlined) and instances (a letter on each one's corner).

`--image` writes a PNG instead of the text renders and prints its path
(`out/look-X0_Y0_X1_Y1-zN.png`, or `--image PATH`): the same render and layers in colour. Read it
like a screenshot.

## The checks

Checks are report lines, never errors: the build goes on and tells you. They come in two voices,
and the capitals are the point.

### The loud ones: something will stop working

- `CLOG`: a net of two or more items (sushi), or an unlimited chest fed two or more items by
  separate nets: an item that comes faster than it is used can fill it and stop the others. Two
  lines quiet it: the route is one inserter from the source straight into each sink, or your
  design says it limits what goes on the net (`net NAME limited "why":`). The fix that holds is
  `net NAME split:`: each item on a lane of its own, loaded by its own filtered inserter
- `SHARED_SINK`: a chest on a net with machines: whoever stands first on the belt gets its fill
- `SUSHI_SINK`: a sushi net reaches a machine that doesn't take every item on it
- `SUSHI_LIMIT`: a `limit=` on a chest a mixed belt of makers feeds: when the chest holds that
  much the belt backs up with every item on it. Such a chest works best unlimited, with the limit
  at each maker
- `SPILL`: a net's route touches another net, so its items end up on a belt that isn't its own
- `WRONG-LANE`: items on a lane the layout gives other nets, nets on one lane that go to different
  sinks, or items on the closed side of a belt side-loaded onto an underground
- `NO_POWER`: a factory's poles don't reach a grid with generation (`floorplan --bridge-power`
  joins it to the plant's grid; `stop_on no-power` holds the paste)
- `no-source` / `power-short` / `switch-never` / `domain-overlap` / `copper` (cover power): a
  domain with no generator and no copper line to one; a domain whose machines want more at full
  load than its generators make; a switch whose `when` can't change; a machine no pole of its
  domain can power without reaching another domain; a copper line that can't be laid
- `TILE_SHARED (x, y): N pieces`: two pieces of one net's route on one tile. Split the net or give
  it room
- `UNREACHED` (diff): entities the paste lays where no powered roboport's construction area
  reaches, counting the roboports the paste lays where robots reach: robots never build them
- `REACH` (report_bom): the ghosts of this paste that no construction area of a roboport that
  stands reaches, roboports first, then by item. `stop_on reach` holds such a paste; `fk build
  --to report_bom` lists them without pasting

### The rest: what is where

- `no-feed` / `no-taker`: a machine's input has no net feeding it / its output goes nowhere
- `short-feed` (report_rates): a net's drivers make less than its consumers would take; it names
  the net where the shortage starts and the `fk plan` line that sizes its drivers
- `cannot-carry`: a net names a machine that has no endpoint for the net's items (left off the
  route). The template's build script stops on it
- `feed-rides-on` (report_rates): a sink at the end of a belt that brings it a product and also a
  feed machines upstream consume: give the product its own belt, or filter the sink's hands
- `no-limit`: provider or storage chests without `limit=`: what reaches them goes into the
  network without end
- `could-pair`: two single-item nets feed the same machines on two belts, a lane each: one belt
  carries both (`lanes A | B`)
- `no-match`: a `set` that matches nothing, or an unknown property
- `CIRCUIT`, `cannot-filter`, `no-signal`, `no-wire`, `wire-too-far`, `wires-share`, `gate-open`,
  `require-not-met`, `gate-auto`, `limited`: the circuit lines (LANGUAGE.md, "Circuits")
- `taken-up`: the build takes up a lot and the robots need minutes for it (`out\diff.txt`); stop
  what feeds it first. When the same things come back elsewhere, a factory moved: `fk merge` joins
  factories where they stand
- `two-nets`: one machine input or output on two nets
- `rate-not-met` / `target-not-met`: a rate you asserted, or the surface's target, is not met
- `size`: an `n=auto` line can't meet a target, an assert or what its consumers ask; after the
  routing, a net of a sized line asks more than its belts carry
- `does-not-fit`: a sized line runs past its plot or into another instance's frame; the build stops
  at `place` when their entities would overlap
- `overlap`: two sealed modules' frames share tiles (both may route there, each in the other's way)
- `pipe-too-long`: one pipe segment spreads past 320x320 tiles; the game moves no fluid through
  it. The line says how many pumps at least: an `InlinePump` in the chain or a `Pump` between nets
- `too-thin`: a machine runs short of a net's item as laid and some of the net's lanes or
  inserters run full. `tier minimize --allow yellow,red` (red lanes carry 15/s), a second row, or a
  second belt
- `no-route`: no belt route was found for a net (the reason follows; often a row is boxed in)
- `no-destination` (report_checks): a maker whose product reaches none of its net's consumers. The
  default script stops on it
- `unused` / `partly-connected`: a net nothing uses / a route that doesn't reach every machine
- `bootstrap` (report_checks): a net's own route needs a building item whose only maker takes an
  item from that same net: stock that item first, or build that maker first
- `no-robots`: a logistic chest outside every logistic area of the main robot network, or entities
  outside its construction area. `cover robots` gives a factory a roboport only for the chests no
  roboport of the design reaches yet, where the design's chests need it; it places no storage
  chest, so put one in your hub. Whether robots reach a new roboport is `REACH` and `UNREACHED`;
  an old roboport the design no longer has stays until the design's own stand (or comes out at
  once when the network holds none for the new ones)
- `on-water-or-cliff` / `no-water`: something designed stands on water or a cliff / an offshore
  pump whose water side is dry
- `by-hand` (diff): the build removes or sets back something someone placed or changed (a thing
  on a design tile that the toolkit did not paste is a `mismatch` instead, and is refused, not
  replaced; see Placements)
  by hand: who, what, where, on which design entity's tile, and what the paste does
  (`rory_618 changed inserter at 14.5,0.5 (mall/i0): logistic=copper-plate>7 (the paste sets
  logistic=iron-plate<50)`). To keep it, write it into the source; `stop_on by-hand` holds the
  paste until you have. `out\hand.txt` keeps every one
- `re-laid` (diff): belts, undergrounds, splitters or inserters stand on their design tiles under
  the right name but facing another way; the build orders each out and lays it fresh
- `short-stock` / `needs-research`: the network holds fewer of an item than the build still needs
  / an item or a recipe isn't researched (the technology and its cost follow)

### Advice: `fk check`

`fk check FILE` prints the check lines, then `advice` lines, about how the source is written:
`limited-why` (a sushi net written `limited` with no string), `row-cell` (a row that could be a
Stack of a library cell, with the cell and its parameters), `gate-auto` (what each `auto` gate
became and why). Only `fk check` prints advice.

A refusal is not a check: a design the language can't take stops `fk check`, `fk rates` and the
build with one error line naming the file, the line and the fix (`no-fluidbox`, a missing module
parameter, an index past the end of a list).

## Reading the base

- `fk stock`: what the base holds, per item: chests, roboports, your pack and the robots in the
  air. A robot in a chest is an item and does nothing; the line says how many are flying, in
  roboports and in chests.
- `fk capital [--area A]`: working capital, what the base owns in raw units, working (machines as
  they ran since the last read, robots in the air, research in use) against idle (every item
  anywhere, machines that stood, robots in roboports, unused research). `--park AREA --why TEXT`
  leaves an area out on purpose; `--unpark N`, `--weight TECH=W`.
- `fk stats`: the whole base in one report: research and its rate, capital and the share that
  works, made and used a minute, power made and used by domain, machines by state, the trend.
  `--items iron-plate,copper-plate [--window 10min] [--series 30] [--fluids]`: the production
  panel's numbers and graph. `--history` and `--page` (below).
- `fk chart`: how much of the map is explored. `fk alerts`: the alert panel now. `fk research`:
  what can be researched, cheapest first, and what runs; `fk research TECH...` queues them
  (`--first` at the front). `fk tech NAME`: a technology, or what opens an item. `fk recipes
  [--enabled]`.
- `fk request X,Y|KEY ITEM N`: an item request on a standing entity (a turret's ammo, a machine's
  modules): robots bring N from the network. It only asks, and says when the network holds less.
- `fk catalog learn NAME`: a building the catalog lacks (Space Age, a mod), read from the game
  into `game\learned.json`; every step plans with it after (BUILDING.md, "Adding a machine").

### The run's history: `fk stats --history`

Every 5 game minutes a sample keeps what changed: items and fluids made and used, power made per
generator class and used per machine type (and per domain), the research under way and the packs
the labs used, machines of each kind and recipe working, short, full or unpowered. Capital is read
every 10. `fk stats --history` reads them: the research first, then the latest window, then the
trend (the last 30 game minutes against the 30 before). `fk stats --page` writes
`game\out\stats\index.html`, charts over game time. `--sample [--now]` takes a sample. The samples
are in `game\out\stats\`. The research line every command ends with comes from the same reads.

## Programming the game yourself

The game is open to your code at three levels:

- **fk commands.** Each is Python sending Lua over RCON, all readable in `.toolkit\fkcore\`:
  `link.py` holds most Lua chunks, `alone.py`, `standin.py`, `sim.py` and `capture.py` their own.
  When a command does almost what you want, read its Lua and change it.
- **Lua** (`fk lua`), for anything the game API can do that no command does yet: a deconstruction
  order with a filter of your own, a ghost grid, a question about the base.
- **Your own scripts**, Python or PowerShell that chain `fk` commands and Lua: a loop that tries
  five layouts with `fk build --to report_checks` and keeps the best. The ones you'd write twice
  go in `helpers\`.

The rules are the same either way (`FAIR-PLAY.md`): you build by ghosts, and you may press any
button a player could press. A Lua loop that places ghosts is a paste of your own:

```
fk lua "local s = game.surfaces.nauvis for i = 0, 9 do s.create_entity{name = 'entity-ghost', inner_name = 'solar-panel', position = {100 + 3 * i + 1.5, 41.5}, force = 'player'} end rcon.print('ok')"
fk lua "rcon.print(game.forces.player.current_research and game.forces.player.current_research.name or 'none')"
```

What you place outside the design reads `marked` in `fk look`. To keep it for good, `fk capture
world X0,Y0,X1,Y1` it and put the file in your design as a `Literal`. The chunk goes to the game
as you wrote it (a 40 kB file works); a big answer is better written to a file on the game host
(`helpers.write_file`). The host is `computah-ct`; `run.json` names the toolkit there
(`host_toolkit`) and your game codebase (`host_game`). The link refuses Lua that registers an
event handler, a command or an interface: that made every save unjoinable once. Try risky Lua on
the planner first (`fk sim game lua ...`).

## The build script

`game\nauvis.build.fkb` is the list of steps `fk build` runs, one per line, each reading what the
steps before it made (the template is in your game folder, with a comment per line). Keep it or
tweak it; leave `apply` out while you design.

- `stop_on no-destination cannot-carry by-hand` holds the paste on those checks. A net that
  doesn't route doesn't hold it (pasted without its new belt, `--failed keep`); add `stop_on
  no-route` to hold the paste until every net routes, `stop_on reach` for ghosts no robot reaches,
  `stop_on no-power`, `stop_on short-stock`.
- `size` counts the `n=auto` lines (`fk build --to size` stops there; `size --payback 2h` also
  counts what the design draws over two hours).
- `route --only stale --retry-failed changed --failed keep --effort normal --hand any` is the
  template's line ("How route works"). `--hand any` lays the **lowest** hand the network can build
  (a plain inserter), and `hands minimize` raises only the connectors whose flow needs more
  (`out\hands.txt`); `hands maximize` takes the top rung everywhere, `--downgrade` may take a
  standing fast hand back. Where even the best hand is too slow for a machine the router lays 2
  or 3 inserters between it and its belt.
- `tier minimize --allow yellow,red` lays red belts where a yellow lane is too thin (`--red N`
  caps how many; `tier maximize` uses the fastest allowed everywhere; a belt never goes down a
  tier without `--downgrade`).
- `cover robots` lays roboports over the design's logistic chests; `cover power --pole any` the
  poles, medium where the network can build them, else small (`floorplan --bridge-power any` the
  same for the bridge to the plant's grid). The choice is written to `out\avail.json` by
  `report_bom --stock live`.
- `diff --scope stale` and `apply --scope stale` paste only what changed; `apply --area A` for
  one region. `write_layout` writes the `.fkp` files the next build keeps to (`--to diff` writes
  nothing).
- `fk build --from route --to report_checks` runs part of it (`report_rates:2` names the second
  `report_rates`). It starts from the layout the last build left, or lays it out again when a
  source file changed since. `out\timings.txt` gives each step's time, and a step of 10 s or more
  says it on its line.
