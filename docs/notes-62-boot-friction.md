# 62-boot-friction: the bootstrap stages' FRICTION.md (2026-11-11)

The source is `lab-session\fk-boot-w3\FRICTION.md`: 21 entries from the base plan's S2-S7 builds
on toolkit 3.2.9 (fk-sim's `.toolkit`), plus the one open entry of `lab-session\fk-run2`. Main
3.4.1 changed nothing in routing or checks since 3.2.9 (3.3 and 3.4 are the commons), so every
entry was open on main. Each fixed one has a test that fails on main and passes here.

## Fixed on this branch

| Entry | Fix | Test |
|---|---|---|
| hands minimize demotes filtered fast inserters | `hands.assign`: a hand with `filter=` never goes below a rung that filters (`FILTERING`: fast, bulk, stack). Main turned the router's filtered loaders into plain inserters carrying `filter=`, which a 2.0 inserter can't hold. | `test_split_lanes` (hands_minimize_keeps_...) |
| hands minimize doesn't know a line's rate | The build had `route --hand inserter`, which fixes every tap, so `hands` said "0 short hands" and nothing else. It now names the fixed hands that carry less than their connector needs and says `route --hand any` lets it raise them. Also: the stage's requesters had no `rate=` (the `no-rate` lines), so the model ran them at 0/s. | `test_hands` RouteHandTest |
| cover power lays poles for dnp pieces | The cover still lays them (ready, as 2.0.63 wants), but a pole that only DNP pieces need is DNP itself. Rory 11-11: "a system that automatically removes power poles needs to ensure that it never causes something to de power". `cover._dnp_poles` keeps a greedy cover of the built electric entities and the wire paths back to the layout's own poles, then proves it (`_keeps_power`): every built entity any pole powered is still powered, and the kept poles that power built entities are in one component with the kept roots. When the proof fails, poles go one at a time, newest first, under the same check. The summary says "N only for DNP pieces". | `test_dnp` DnpCoverTest |
| renaming an instance's kind crashes the pinned routes; re-kinding a Stack's cell leaves feeds unroutable | `flow._pinned_routes` reads the old layout's jobs without re-kinded instances, and routes again every net with an end on, or inside, one ("gear changed kind since the committed .fkp (Assembler -> Literal)"). `route.jobs` also skips an instance the new flat calls a Literal. | `test_rekind` (new) |
| a net's last belt on a port tile faces the way it came | `connect._port_joints`: the carrier outside a port feeds it only if the belt graph says it moves its items onto the port's belt. Main threaded any carrier in, so a sideways belt read connected. Now the route reads open and is patched. | `test_boot_friction` PortFeedTest |
| `--reroute` laid an underground on a terrain-blocked tile | `route._standing`: a committed carrier on ground the terrain now blocks (a roboport entered in the terrain after the route was laid) is taken up, and its net patched round it. | `test_terrain_flow` (kept_route_on_newly_blocked_ground) |
| `route --only stale --retry-failed always` left a net half routed | Under `--retry-failed always` a standing belt route whose new end can't be patched is laid again whole, not held. | `test_route` (patch_that_cannot_be_laid) |
| route lays a splitter over its own belt | `_Patch.add_consumer`: a branch that lays two pieces on one tile, or one on a standing entity it doesn't replace, is refused. The patch fails (held, or laid again) instead of writing a malformed stage. A backstop: the cause (a split start's side tile is free ground to the branch search) is not fixed. | merge set (no repro) |
| a chest with more than four nets: no-route, no reason | New elaborate check `crowded-ends`: more nets end at an entity than it has side tiles. Rory 11-11: check for an easy merge into a sushi net. When the entity is a chest and the nets into it end nowhere else, the check gives the one merged line in the module's own names ("`net n0 items iron-gear-wheel, copper-cable, ...: a0, a1, ... -> box` in place of n0, ..."); otherwise the generic merge advice. | `test_boot_friction` CrowdedEndsTest (the merged net routes) |
| no long-handed maker, nothing said so | `report_bom` marks each item that nothing built in the design makes ("no maker"), and `short-stock` says so. Paper stock: `report_bom --stock FILE`. | `test_boot_friction` NoMakerBomTest |
| path dependence: a net routed on old history fails from a clean slate | `fk build --fresh` (Rory 11-11: "build fresh sounds very good"): no committed .fkp, last route, failure memo or compiled module is read; every net is laid anew. Refused with `--from` past the first step. | `test_boot_friction` FreshBuildTest |
| no check that what is laid out is in robot reach; route knows nothing of reach; a logistic gate outside every logistic area; trees past reach | Rory 11-11: "roboport reach should be easy to do in the toolkit without the game". `read-terrain --entities` records every roboport on the surface. floorplan runs `robots.check_reach`: from the powered ones, grown by the design's own roboports that join them, `out-of-reach` per plot and `no-robots` per logistic chest or `logistic=` gate outside every logistic area. `read_terrain map --reach` blocks every tile no powered roboport builds, and the tiles under trees and rocks that reach past them (the sim's reachmask.py). | `test_reach_offline` (new, 9) |
| two instances overlapping, no check | Rory 11-11: "Overlapping frames should be a warning ... best for the build script to define it case by case". Two declared frames that share tiles warn (`overlap`) while their hulls don't yet. `place --overlap a+b` in the build script marks a pair as meant (compaction): place writes a line in place of the warning, and `overlap-clash` names each tile both lay an entity on. The docs' hull example (EXAMPLES chapter 6, step 2) now names its pair. | `test_module_overlap` OverlapLeaveTest; `test_hull` |
| two fluid sources, "1 of 2" | `fluid_route._judge` names the first unreached pair ("; unreached D -> C and N more"). | none |

## Already on main

- `fk-run2`: cover power's `_why_not` crash on a cell's edge beacon was fixed in 3.1.x.
- Literal names with dashes: the refusal has said "a name is a word without dashes (asm10)" since
  2.1.10.
- Build exits 0 with an open net / `NO_POWER`: by design ("checks warn, never gate"). The build
  script can gate: `stop_on partly-connected` / `stop_on NO_POWER` (flow's `stop_on` step). The sim's
  `steps.sh` could use these in place of grepping the logs.
- write_layout keeps dnp rows: `fk build`'s apply never pastes them (`apply.scope_rows`); the
  sim's own replay pasted them.
- Two overlapping instances: `place` has an `overlap` check for sealed modules, judged on the
  achieved hulls (41-hull). Blue1 over Sci's declared frame didn't fire because their hulls didn't
  share tiles yet.

## Open (not fixed here)

- **Two fluid sources, "1 of 2".** `fluid_route._judge` now names the first unreached pair
  (this branch, no test). Still open: the box its pipes stop at (`connect.fluid_reach`), and
  keeping the best try's reason, not the first.
- **A chest never feeds a machine directly.** Rory 11-11: "the router being smart enough to use one inserter when a source and dest are a tile apart". On branch `claude/63-direct-share` (see below).
- **cover power rework.** Rory 11-11. The plan is `..\assessment-20261111\PLAN-POWER.md` ("all 25 spots taken" is P2's kind ladder; P1: the world's poles from read-terrain --entities as roots; P2: one PowerProblem, a pole-kind ladder for "all 25 spots taken"; P3: route keeps a pole spot; P4-P6: module power ports, switches and generators, the live check).
- `_keep_failed` should not put back a route whose ends moved ("standing oil2/l: unrouted; its last route stands").
- Two test modules fail on main as well as here: `test_dnp`
  (`test_a_scaling_row_grows_where_it_stands` expects a "kept (" line route no longer writes) and
  `test_port_unpinned` (`lab.prepare` is gone). Neither is in the merge set.
