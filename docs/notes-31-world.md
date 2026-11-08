# 31-world: world reads are explicit (PLAN-3.1, wave 1)

Branch `claude/31-world`, cut from main `fa99ec8` (3.0.3). Rory's requirements of 2026-11-08, PLAN-3.1
points 2 and 3. Stdlib only; checks warn, never gate; library over language.

## What changed, and why

**(a) The world no longer feeds the cover steps.** The toolkit converges the world onto one clean
design, so what stands in the game must never move the plan by itself. `out/standing.json` is
gone: the diff no longer records the poles it found built nor the roboports standing with power,
and `cover power` / `cover robots` no longer read anything of the kind. In `fkcore.cover` the
`standing` parameter went (a pinned pole of another kind than `--pole` is laid again in the new
kind; 2.0.1 had kept the built ones of the old kind from the diff's record). In `fkcore.robots`
the 2.1.3 chain went with it: `cover_robots` lost `reach`, the `_Links` class, `_CHAIN` and
`in_frame`; a roboport goes where the design's chests need it, full stop. In `fkcore.apply`
"a moved roboport is taken up" stopped: `scaffold` lost `moved` and `MOVED_OUT`, so a roboport the
design moved is held like any other old one under the 1.7 rule (until the design's own stand, or
at once when the network holds too few roboports to build them: `STOCK_OUT` stays). What stands
and differs from the design is the diff's business: it reports a difference, the apply orders it
out. The diff still reads the roboports standing with power (`_read_roboports`, `ctx.roboports`),
for `REACH` (report_bom) and `UNREACHED` (diff) in the same build only; those are reports about
a paste, not inputs to a layout.

**(b) The world goes into a design only as explicit constraints.** Bounds existed already: the
plot, `--area`, a module's `size`. Obstacles are new: `fk read-terrain --surface S --area A
--entities` puts the tiles of every built entity in the area that the design does not own into
`<name>.terrain.json` under `entities` (`tick`, `area`, `count`, `names`, `tiles`), and
`Terrain.blocked` includes them, so routes, poles and roboports go round them from the next
build on. Owned is: on a tile of the composed design, or in the toolkit's own record
(`out/own/<surface>.json`). Ghosts, trees, rocks, cliffs, units and the like are never obstacles
(`terrain.NOT_OBSTACLES`). A read without `--entities` leaves the file's entities as they were;
one with it replaces them inside its area and keeps the rest; `--replace` drops everything. A
file written before 3.1 has `"entities": null` (none). The summary, `out/read_terrain.txt` and
the per-plot line say how many standing-entity tiles are in play and when they were read.

**(c) `fk robots`: how few roboports would do.** An agent that built too many roboports runs one
command and reads, numbers first, how many stand, how many have power, how many networks, which
chests of the design are covered and which not, which roboports are redundant, and how many
`cover robots` would lay for the same chests on free ground. Pure read: nothing in the world or
the design changes. It runs on the host (`agent/fk.py`: `HOST`, `AREA_FIRST`).

## The commands

```
fk read-terrain --surface nauvis --area X0,Y0,X1,Y1 [--name map] [--replace] [--entities]
fk robots [X0,Y0,X1,Y1] [--force F]        (fkcore: robots GAME [--area A] [--force F])
```

`fk robots` output (one screen):

```
robots nauvis area 0,0,60,20: 17 roboports stand (15 with power, 2 networks); 42 logistic chests in the design
  covered: 40 of 42 chests inside a powered roboport's logistic square; uncovered: main/box/c0 at 12.5,40.5; ...
  redundant: 9 of the 15 powered (every chest they reach another reaches too; taking them out splits no network), 3 of them reach no chest: 120,40; 160,40; ...
  minimal: 8 roboports would cover every chest (cover robots on these chests alone, free ground): 110,38; ...
  without power: 2 (they serve nothing): 300,20; 310,20
  nothing changed: the design says where roboports go (cover robots); a roboport the design does not have is the diff's difference
```

With an area: the chests inside it, and the roboports whose logistic square meets it. Redundant
is computed greedily to a fixed point (fewest chests first), coverage by powered roboports only,
and a roboport that bridges two parts of a network is not redundant. Lists show 8 entries, then
"... N more". Library: `robots.Standing`, `robots.lua_standing`, `robots.standing_rows`,
`robots.report` -> `StandingReport` (`.lines(surface)`), `robots.minimal`.

`read-terrain --entities` library: `terrain.owned_tiles(composed, own_rows, cat)`,
`terrain.obstacles(things, owned, area)`, `terrain.read_entities(rcon, surface, area, owned)`,
`terrain.with_entities(t, tiles, read)`; the file key `entities`; `Terrain.entities`,
`Terrain.entities_read`; `FrameGround.entities`.

## TOOLKIT.md text now wrong (for the docs wave)

- Lines 148-157 ("Rebuilds keep what stands"): "Switching the pole kind ... keeps the poles of the
  old kind the last build found standing and lays the new kind only where the old one never
  stood" is false now: the new kind is laid everywhere a pole of the cover is needed; the old ones
  come out as differences. Pinning of the same kind still holds.
- Lines 886-896 (`no-robots`): "It chains only from roboports that stand, or that it lays in
  reach of them: a roboport no robot could reach is not placed" and "When a paste moves a
  roboport, the old one is ordered out (robots take it up and carry it to the new spot)" are both
  false now. The old roboport stays until the design's own stand (or the stock rule). Whether
  robots reach a new roboport is `UNREACHED` / `REACH` (lines 785-791, still right).
- Line 1041 (`fk read-terrain`): add `--entities`.
- The command list: add `fk robots`.
- `docs/RELEASE-2.1.3.md` "Robots that can't reach" describes the removed behaviour (history,
  leave it; RELEASE-3.1 says what replaced it).
- `agent/prompts/opus-v1.md` line 141 (`cover robots --fresh`) is still right.

## For the docs: bounds and obstacles, in one paragraph

A design is laid out from its source and the terrain file, never from the live world. To keep a
factory in bounds, give it a plot (`place iron = iron plot 40,-20 30x30` in the surface file, or
the world design's plots): nothing of it is laid outside, and `fk route --area X0,Y0,X1,Y1`
reworks one region and leaves the rest standing. To make the design go round what stands in the
world, read it in on purpose: `fk read-terrain --surface nauvis --area X0,Y0,X1,Y1 --entities`
puts every built entity there that the design does not own into `map.terrain.json` as blocked
tiles (the file says when it was read and how many), and the next build routes, poles and
roboports round them. Without `--entities` only the bare ground (water, cliffs, ore) constrains
the layout. What the design has and the world lacks, or the world has and the design lacks, is
the diff's difference, never an input to a step; `fk robots [AREA]` reads the standing roboports
against the design's chests and says how few would do, changing nothing.

## Tests

- Adapted: `tests/test_cover.py` (switching the pole kind lays the new kind everywhere),
  `tests/test_robots_reach.py` (cover is pure; the scaffold holds a moved roboport; `REACH` and
  the stock rule unchanged), `tests/test_fixes_213.py` (no standing plumbing), `tests/test_flow.py`
  (the standing-poles test removed).
- Added: `tests/test_terrain.py` `EntitiesTest` (owned excluded; ghosts, trees, cliffs, units
  excluded; file round trip and `blocked`; merge keeps old entities unless the new read had them;
  the command reads them only with `--entities`), `tests/test_robots.py` `StandingReportTest`
  (coverage, redundancy to a fixed point with the bridge rule, minimal set, area cut, the read's
  rows and the Lua's safety).
- Run (2026-11-08): test_terrain, test_robots, test_robots_reach, test_cover (64 OK);
  test_power_domains, test_design, test_lab (54 OK); test_terrain_flow, test_flow, test_fixes_213,
  test_apply, test_sense, test_own (91 OK). Not run: the whole suite, golden.

## Open

- `fk robots` and `read-terrain --entities` are unchecked against a laptop server (the Lua is
  `assert_safe`-checked and read-only; `lua_standing` uses `logistic_cell.transmitting` as the
  power flag, as `lua_roboports` did).
- `minimal` lays on free ground with no obstacles: a lower bound to aim at, not a placement.
- The merged `entities.count` after two `--entities` reads over meeting areas adds both reads
  (an estimate); the tiles are exact.
- `s_cover_robots` keeps its `ctx.surface.mode == "lab"` line as it was, for 31-surface's merge.
- Terrain files gain a `"entities": null` line on their next save (one key, diffable).
