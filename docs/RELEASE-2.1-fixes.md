# Toolkit 2.1.2 (draft): fixes from the runs

PLAN-2.1, "Fixes from the runs (review of 2026-10-31)". Each fix comes from something a player hit.

## A paired port driven by two nets

A module port `A | B` fed by two single-item nets failed: "its two lanes come in paired", or the
second item went unrouted. `expand._module_fragment` bound the port's outer side through `lane_of`
only for `in` ports, and nothing paired the two nets unless the top level had a `lanes` line.

- `elaborate._port_pairs` pairs them: two distinct single-item nets, one per lane of a paired
  port, become a `lanes` pair (`flat.pairs`, `flat.lane_of`). A bus, a sushi net, a fluid or a net
  already in a pair is left alone.
- `expand` binds both sides of a paired port through `lane_of`, `in` and `out` alike.
- The module's own `lanes` line is enough; no line is needed outside.
- `could-pair` no longer names a pair the port already makes (tests/test_ports' BURNER case).

## Robots that can't reach

- `REACH` (report_bom): the ghosts of this paste that no standing roboport's construction area
  reaches. A roboport the paste lays counts only when it stands in such an area and its logistic
  area meets that network's. Roboports first, then by item. `stop_on reach` holds the paste.
- The diff step reads the standing roboports (`robots.lua_roboports`) into
  `out/standing.json` ("roboports").
- `cover robots` chains only from those roboports, or from the ones it lays in reach of them
  (up to 12 stepping stones). A roboport out of reach is not placed; the factory's line says so.
- The scaffold rule (apply): a roboport the paste moves is ordered out at once (robots carry it to
  the new spot). An old roboport is also ordered out when the network holds too few roboports for
  the new ghosts, so the scaffold never leaves the network with none to build. The apply report
  says how many and why ("scaffold: N old roboport(s) ordered out now, ...").

## `fk request ENTITY ITEM N`

An item-request proxy, the game's own way to ask robots for items: a turret's ammo, a machine's
modules, a chest's stock. ENTITY is `X,Y` or a design key. It only asks: it moves no item. It says
when the network holds less than N (SHORT) and when no roboport's area reaches the entity
(UNREACHED). A second request on the same entity joins the first proxy. It runs on the host, like
`apply`.

FAIR-PLAY.md now says it: moving items by script is never a player's button; `fk request` is.

## The small ones

- `cannot-carry` is in the template's `stop_on`, and the 2.1.2 upgrade adds it to a run's script.
- `stop_on` treats `no-power` and `NO_POWER` (dash or underscore, any case) alike, so
  `stop_on no-power` holds a paste.
- `fk read-terrain --area` merges into the file: the new area wins tile by tile, the rest stays.
  `--replace` writes the area alone, as before.
- `fk capture lab NAME` takes only what stands inside its own slot. A neighbour's entity whose
  box crossed the edge used to come too.
- TOOLKIT.md lists `TILE_SHARED` with the checks.
- The dry run (`fk build --to report_bom`) leaving its routes in `world.fkp`: not reproduced,
  neither through `flow.run` nor through the player's `fk.py`. `tests/test_fixes_212.py` pins it:
  both leave every `.fkp` byte for byte.

## Checked

- `tests/test_port_pairs.py`, `tests/test_robots_reach.py`, `tests/test_fixes_212.py`, and the
  updated `tests/test_ports.py` and `tests/test_upgrade_run.py`.
- The laptop server (`python tools/laptop_server.py fixes`): capture of one slot, the roboport
  read, REACH with and without the paste's roboport, a request asked and a request short, one
  proxy for two requests, robots bringing the ammo, a request on empty ground refused, the moved
  roboport and the stockless scaffold ordered out, and the old roboport held when stock is there.
- The golden check against 2.0.78.
