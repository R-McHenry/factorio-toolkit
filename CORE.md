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
  `Chest<provider|storage|requester, item, rate>`, `Literal` (its entities are pinned in the `.fkp`;
  `Literal<file>` for a blueprint import is [spec]), and modules. `duty=` caps any instance (a
  mall runs only while the network restocks).
- **Templates expand visibly** [built: AsmRow, SmelterRow, MinerRow, LabRow, single machines]: an
  instance's fragment (machines, the belts and inserters of each role, attach points) is written into
  the `.fkp` under its keys, every carrier `net=` the net its role is bound to. Rows are counterflow
  (all attach points at the head) and take one or two input belts in V1. `explain X` shows both
  views; `unfold X` makes it a `Literal` and keeps every `.fkp` line.

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
  no rate), `ASSERT` (a nominal rate assert failed); later `UNROUTED`, `LEAK`, `NO_POWER`, `NO_ROBOTS`,
  `LOW_STOCK`, `BOT_SCIENCE` (a pack made from bot-fed chests), 1.1 `SHARED_BELT`.

## Rate model (nominal, V1) [built]

On the flat netlist: every net balances per item. Supply = drivers' rate x utilization. A short net
is shared in proportion to appetite; a net with surplus lets consumers rise to full speed. A sink
(chest, lab) takes what is left, up to its `rate`. A producer slows when its nets can't absorb its
output. Damped fixed point; reports per machine utilization + the binding endpoint, per net per item
supply / demand / delivered, the binding chain, and every `assert`. No capacity in V1: routed
throughput is V2.

## Flow script `build.fkb` [spec]

Straight-line, one contained tool per line, each reads the previous checkpoint `out/<step>.fkp` and
writes its own plus `out/<step>.txt`: `read_surface`, `read_terrain`, `run_models`, `elaborate`,
`report_rates`, `place`, `route`, `cover power|robots`, `floorplan`, `report_checks`, `report_bom`,
`write_layout`, `diff`, `apply`, `stop_on <check ...>` (default: invariants only). `fk build <surface>
[--from X --to Y]`; every line is also a command on its own.

## Diff verdicts [spec]

Per tile: `OK`, `GHOST`, `MISSING`, `WRONG` (another entity), `DRIFT` (direction, ug type, config),
`CLAIMED`, `MARKED`, `NOBODY`. Per carrier: `WRONG_ITEM`. After robots finish, the diff inside the
applied scope is empty: that is 1:1.

## Watch, notify, fair play [spec]

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
