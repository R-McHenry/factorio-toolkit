# CORE: the V1 core on one page

The spec for Rory's sign-off. {RM - approved} Reasons and history: `..\CORE-V1.md` (decisions 1-12). Marks: **[built]**
= implemented and tested in this repo (`python -m unittest`), **[spec]** = agreed, not built yet.

## Objects

| object | is | lives in |
|---|---|---|
| machine | key, prototype, recipe. **Endpoints** `(machine, item, in/out)` come from the recipe, plus fuel for burners, the resource for drills, packs for labs | `.fk` + `.fkp` |
| net | **name** (its identity), **items** (declared, else the drivers' products; 2+ items = **sushi**), **drivers -> consumers** (endpoint sets). Never leaves its factory | `.fk` |
| carrier | belt, underground, splitter, inserter, pipe, pipe-to-ground, pump, loader. **Exactly one net** | `.fkp` (`net=`) |
| route | a net's carriers: any connected graph joining every driver to every consumer and touching no other net. One inserter is a route | derived |
| coverage | power, robots (later defense); its entities are keyed under it | `.fk` + `.fkp` |
| boundary | ore patch (drills), water (offshore pump), logistic network (chests, optional `rate`) | `.fk` |
| factory | a top-level module: its own nets, frame, `.fkp`, coverage, boundary | `.fk` file |
| plot / claim / mark | a factory's box on a surface (never overlapping) / a named box with a reason and expiry / an automatic claim the watcher writes for a foreign change | surface `.fkp` |

Every world entity is exactly one of: a layout entity, inside a claim, under a mark, or **NOBODY**.
Endpoint rule: a machine is on at most one net per (item, direction).

## `.fk`, the factory source [built: parse, elaborate, flatten]

```
inst    := name '=' Kind ('<' param (',' param)* '>')? hint*     # template, boundary or sub-module
net     := 'net' name ('items' item (',' item)*)? ':' refs '->' refs
refs    := ref (',' ref)*      ref := name ('.' name)* ('.*')?
assert  := 'assert' ref '.rate' ('>='|'<='|'>'|'<'|'==') N ('/s'|'/min')
cover   := ('power'|'robots') name ':' 'cover' ('all' | refs) (',' param)*
module  := 'module' Name '{' stmt* '}'                          # a sub-module, a template written in .fk
import  := 'import' Name (',' Name)* 'from' "file.fk"           # inside the same game codebase
param   := name '=' value | flag        hint := '@(' x ',' y (',' 'rot' r)? ')' | '@patch(' resource ')'
```

- A ref names an instance (all its machines) or a machine in a sub-module (`mall.belts`). On a net it
  contributes only endpoints of the net's items: `iron_smelt` as a driver adds `(m, iron-plate, out)`.
- `X.*` = X's **free** endpoints: those no other net already holds. `net mall_out: mall.* -> chest`
  takes every mall product not used inside the mall.
- Kinds: `MinerRow<n, resource>`, `SmelterRow<n, recipe, fuel>`, `AsmRow<n, recipe>`, `LabRow<n>`,
  `Assembler`, `Furnace`, `ChemPlant`, `Refinery<recipe>`, `Pumpjack<rate>`, `OffshorePump<rate>`,
  `Chest<provider|storage|requester, item, rate>`, `Literal` (its entities are pinned in the `.fkp`,
  or `Literal<file="x.json", box="x0,y0,x1,y1">` imports a blueprint or entity list [built]), and
  modules. `duty=` caps any instance (a mall runs only while the network restocks).
- `@(x, y, rot r)` puts the instance's frame, turned r quarter turns clockwise, with its top-left at
  (x, y) of its module's frame. On a sub-module instance it turns the module's whole contents inside
  the module's frame (its origin and its placed children's frames), the way a plot turns a factory;
  each child's own rot adds to it [built].
- **Templates expand visibly** [built: AsmRow, SmelterRow, MinerRow, LabRow, single machines]: an
  instance's fragment (machines, the belts and inserters of each role, attach points) is written into
  the `.fkp` under its keys, every carrier `net=` the net its role is bound to. Rows are counterflow
  (all attach points at the head). AsmRow takes up to three input belts, the third south of the
  product belt by long-handed inserters (Rory, 2026-10-19); SmelterRow and LabRow up to two.
  `explain X` shows both views; `unfold X` makes it a `Literal` and keeps every `.fkp` line.

## Keys

`<surface>:<factory path>/<owner>/<local>`. The owner is an instance path (`red`, `iron/smelt`), a net
(`~gear`) or a coverage object (`power`). `nauvis:main/red/m3`, `nauvis:main/~gear/b12`,
`nauvis:claim/boom-test`, `nauvis:mark/Rory_618@4512000`. The world matches the composed layout **by
position + name**; no unit numbers, no per-run state.

## `.fkp` v1, the layout record [built: format, invariants, compose, tile index, blueprint codec]

```
fkp 1 factory main                                           # factory frame; tiles 0..W, 0..H
size 120x80
inst gears AsmRow n=3 recipe=iron-gear-wheel at 10,-40 rot 0 sig 7f3a01c2d4
cover power power pole=medium-electric-pole
e gears/m0 assembling-machine-1 11.5,-38.5 N recipe=iron-gear-wheel
e gears/i0 fast-inserter 11.5,-36.5 S net=iron
e ~gear/u3 underground-belt 14.5,-31.5 N net=gear ug=in
e power/p7 medium-electric-pole 12.5,-34.5
```
```
fkp 1 surface nauvis                                         # surface frame
plot main at 10,40 rot 0 size 120x80
claim boom-test box -20,40 -10,50 until 4500000 "explosives trial"
mark Rory_618@4512000 tiles 3,4 3,5 until 4620000
e robots/r0 roboport 60,30                                    # shared infra, owner robots
```

- Canonical form: the writer emits header, records, then `e` lines in key order; comments are dropped
  (the `.fkp` is tool-written). `load(save(x)) == x` and `save(load(text)) == text` for canonical text.
- **Compose** = every plot's `.fkp` rotated (`rot` 0-3, quarter turns clockwise) and moved so its
  box's top-left lands on the plot origin, keys prefixed `<surface>:<factory>/`, plus the surface's own
  lines. Computed, never stored.
- **Blueprint**: one entity per `e` line, `tags = {src: key, net}`; `recipe`, underground `type` and
  `direction` map to the game's fields; record lines ride in the blueprint `description`.
  `.fkp -> blueprint -> .fkp` is byte-identical.

## Invariants vs checks

- **Invariants** (the writer refuses; the only thing that stops a flow by itself): two entities on a
  tile (also across plots), two plots overlapping, an entity outside its factory's `size`, a key whose
  owner doesn't resolve, a duplicate key, a carrier with no net or two nets, an unparseable line.
- **Checks** (report lines, never gates unless `build.fkb` says `stop_on`): `UNFED`, `UNCONSUMED`,
  `TYPE` (a ref adds no endpoint of the net's items), `SUSHI_SINK` (a sushi net reaches a consumer
  that doesn't take every item on it), `DOUBLE` (an endpoint on two nets), `UNBOUNDED` (a source with
  no rate), `ASSERT` (a nominal rate assert failed); [built: connect] `UNROUTED`, `OPEN`, `LEAK`,
  `UG_SIDELOAD` (a belt side-loads onto an underground: lane-dependent, and V1 tracks no lanes);
  [built: cover, floorplan, report_bom] `NO_POWER`, `POWER_SPLIT`, `LOW_STOCK`; [built: cover robots]
  `NO_ROBOTS`; later `BOT_SCIENCE` (a pack made from bot-fed chests), 1.1 `SHARED_BELT`.
  1.1 [built] limited production (Rory, 2026-10-20: in the game a sink takes what reaches it first,
  never a proportional share). The lines say what can happen, never how to build: mixed belts and
  chests are fine where production is limited. `CLOG` (a sushi net that machines drive, or an
  unlimited chest fed two or more items by separate nets; a net only requester chests drive is
  limited), `UNLIMITED` (provider or storage chests without `limit=`, the chest's bar in the paste;
  one line per factory), `SHARED_SINK` (such a chest on a net with machines); and the diff's `RIP`
  (what the next apply takes up: structures, the items in them and the robot minutes, with the
  drain-first trick, and the moved-factory hint pointing to `fk merge` when the same names come
  back as new ghosts). `fk fresh AREA` takes up the belts with `WRONG_ITEM` (stale items from a
  rebuild) so the next build lays them fresh: the scripted fix that goes through the game, and a
  look now lists where they are. The 0534 player's own patches are features: `inserter=` on rows,
  `item="a,b"` on a requester, a third lab belt, and `route --hand inserter`. See
  docs/RELEASE-1.1.md.
  1.2 [built] (what 1.1 left of the 0534 run's FRICTION.md, all six with tests; none deferred):
  the toolkit's own entities (`fkcore.own`, `out/own/<surface>.json`: what the applies pasted,
  seeded once from the .fkp files last written) are no foreign change: one the design dropped is
  `NOBODY` whatever the watch policy (a replaced row, a moved, shrunk or emptied plot, its unbuilt
  ghosts too), and the apply's default scope reaches it; a carrier the record shows under
  another net that holds what its new net doesn't carry (`WRONG_ITEM`, pipes' fluid too) is
  ordered out before the paste, which lays it fresh; a moved endpoint makes its net's route
  stale; `cover robots` counts the surface's network and puts a storage chest beside each
  roboport it places; `floorplan --bridge-power` lays a bridge again around a plot laid over it;
  `fk lua` takes any chunk (stdin over ssh, its lines kept). See docs/RELEASE-1.2.md.

## Rate model (nominal, V1) [built]

On the flat netlist: every net balances per item. Supply = drivers' rate x utilization. A short net
is shared in proportion to appetite; a net with surplus lets consumers rise to full speed. A sink
(chest, lab) takes what is left, up to its `rate`. A producer slows when its nets can't absorb its
output. Damped fixed point; reports per machine utilization + the binding endpoint, per net per item
supply / demand / delivered, the binding chain, and every `assert`. No capacity in V1: routed
throughput is V2. 1.3 [built]: `report_rates` again after `route` gives the routed rates and
`CAPACITY`, and the `tier` step lays a belt tier per connector (`CORE-V2.md`,
docs/RELEASE-1.3.md). `plan ITEM RATE | --machines N` [built] goes the other way, from a target
rate to the machines, furnaces and drills of each item of its recipe tree, on a hand calc's terms:
full speed, no modules, one recipe per item (`fkcore/plan.py`).

## Flow script `build.fkb` [built; `diff` and `apply` live with the game link (FK_LINK=on); `run_models` reports and skips]

Straight-line, one contained tool per line, each reads the previous checkpoint and writes its own
(`out/<step>/<factory>.fkp`) plus `out/<step>.txt`: `read_surface`, `read_terrain` [built: a live
map's ore, water and cliffs; `ON_TERRAIN`, `OFF_ORE`], `run_models`, `elaborate`, `report_rates`,
`place` [built: hints, `@patch` for MinerRow], `route` [built: v4's steiner tree router per net,
splits, merges, direct insertion, k->m through a hub, the underground guard; fluid nets by the fluid
plug-in: pipes, pipe-to-ground; 1.2: a net is routed again when anything it is laid to moved],
`cover power` [built] `|robots` [built; 1.2: chests the surface's network reaches need no
roboport, a storage chest beside each one placed], `floorplan` [built, `--bridge-power`; 1.2: a
plot takes the bridge's poles, and the bridge is laid again around it],
`report_checks`, `report_bom`, `write_layout`, `diff`, `apply`, `stop_on <check ...>` (default:
invariants only). `fk build <surface> [--from X --to Y]`; every line is also a command on its own.
Merge, insert, chests-to-net and net-to-chests edit source and layout only [built, on paper].

## Diff verdicts [built: `sense`, live through the flow's `diff`, `look --source world` and `apply`]

Per tile: `OK`, `GHOST`, `MISSING`, `WRONG` (another entity), `DRIFT` (direction, ug type, config),
`CLAIMED`, `MARKED`, `NOBODY`. Per carrier: `WRONG_ITEM`. After robots finish, the diff inside the
applied scope is empty: that is 1:1. [1.2: the toolkit's own entities that the design dropped are
`NOBODY` under any policy; `WRONG_ITEM` covers a pipe's fluid, and names the net a carrier was
pasted under when that was another one.]

## Watch, notify, fair play [built: `sense` policies, notify nearby/all/off, the alert push with reminders, the free reads `stats` and `chart`; the `lab` scenario runs the test map, `/lab` used by Rory]

- Foreign change, per region: `mark [expiry]` (sanctioned space), `keep` (plots), `revert`, `strict`.
- Notify, per surface and actor: `nearby` (play default: only inside a look, sense or build), `all`
  (lab default), `off`.
- **`play`**: the diff, watcher and model-vs-world comparison read only where the agent looks or
  builds. Alerts panel, production statistics and charted map: free to read anywhere, never turned
  into alerts. **Pushed alerts are exactly the game's alert panel**, programmable-speaker alerts
  included, with occasional reminders while one persists. Building is ghosts and robots only.
- **`lab`**: the `lab` surface in the same game, on its own `lab` force (its own research and stats).
  Free materials, direct building, notify `all`, global diff, full-rate measuring. Rory watches with
  `/lab`, registered in scenario/mod code, never RCON.

## The writer rule

**No tool writes the world except a named paste** (`apply`, the flow's last step, or `raw --as`).
Anything else that changes the world is a foreign change: attributed, then handled by policy.
Nothing registers handlers or commands through RCON or the console.
