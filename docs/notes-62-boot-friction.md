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
| cover power lays poles for dnp pieces | The cover still lays them (ready, as 2.0.63 wants), but a pole that only DNP pieces need is DNP itself. Kept: a greedy cover of the built electric entities and the shortest wire paths back to the layout's own poles. The summary says "N only for DNP pieces". | `test_dnp` DnpCoverTest |
| renaming an instance's kind crashes the pinned routes; re-kinding a Stack's cell leaves feeds unroutable | `flow._pinned_routes` reads the old layout's jobs without re-kinded instances, and routes again every net with an end on, or inside, one ("gear changed kind since the committed .fkp (Assembler -> Literal)"). `route.jobs` also skips an instance the new flat calls a Literal. | `test_rekind` (new) |
| a net's last belt on a port tile faces the way it came | `connect._port_joints`: the carrier outside a port feeds it only if the belt graph says it moves its items onto the port's belt. Main threaded any carrier in, so a sideways belt read connected. Now the route reads open and is patched. | `test_boot_friction` PortFeedTest |
| `--reroute` laid an underground on a terrain-blocked tile | `route._standing`: a committed carrier on ground the terrain now blocks (a roboport entered in the terrain after the route was laid) is taken up, and its net patched round it. | `test_terrain_flow` (kept_route_on_newly_blocked_ground) |
| `route --only stale --retry-failed always` left a net half routed | Under `--retry-failed always` a standing belt route whose new end can't be patched is laid again whole, not held. | `test_route` (patch_that_cannot_be_laid) |
| route lays a splitter over its own belt | `_Patch.add_consumer`: a branch that lays two pieces on one tile, or one on a standing entity it doesn't replace, is refused. The patch fails (held, or laid again) instead of writing a malformed stage. A backstop: the cause (a split start's side tile is free ground to the branch search) is not fixed. | merge set (no repro) |
| a chest with more than four nets: no-route, no reason | New elaborate check `crowded-ends`: more nets end at an entity than it has side tiles ("6 nets end at this 1x1 passive-provider-chest ... merge nets"). | `test_boot_friction` CrowdedEndsTest |
| no long-handed maker, nothing said so | `report_bom` marks each item that nothing built in the design makes ("no maker"), and `short-stock` says so. Paper stock: `report_bom --stock FILE`. | `test_boot_friction` NoMakerBomTest |

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

- **Robot reach offline.** `floorplan`'s `robots.check_surface` judges reach only against roboports
  in the surface's own layouts. The sim's roboports stand in the world, and the terrain's
  `entities` record has tiles and name counts but no positions, so nothing was judged. Needs
  roboport positions in `read-terrain`, then `robots.reach` in floorplan and a `logistic=` gate
  check (a gated hand outside every logistic area never fires). A `reach` obstacle for route
  (the sim's `reachmask.py`) builds on the same data.
- **Overlap of declared frames.** Add a softer `overlap` line when two sealed modules' claims
  share tiles and their hulls don't yet.
- **Two fluid sources, "1 of 2".** `fluid_route._judge` keeps only the counts. The unreached
  pair, and the box its pipes stop at (`connect.fluid_reach`), are available there. Also keep the
  best try's reason, not the first.
- **cover power: "all 25 spots taken".** A fallback pole (`--fallback medium-electric-pole`,
  availability-checked) for the entities no `--pole` spot can power.
- **Path dependence.** `build --fresh` (route everything, drop failed, retry always, clear
  `out\design`) for module tests. `_keep_failed` should not put back a route whose ends moved
  ("standing oil2/l: unrouted; its last route stands").
- **A chest never feeds a machine directly.** A feature: one hand chest -> machine with no belt.
- Two test modules fail on main as well as here: `test_dnp`
  (`test_a_scaling_row_grows_where_it_stands` expects a "kept (" line route no longer writes) and
  `test_port_unpinned` (`lab.prepare` is gone). Neither is in the merge set.
