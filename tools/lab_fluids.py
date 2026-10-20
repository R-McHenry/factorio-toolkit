"""lab_fluids: the lab fixtures and the measure for games/lab-fluids (the fluid nets, live).

Run on the game host from a deployed v5 dir:  python3 tools/lab_fluids.py STEP [...]
Every game call is one RCON command with the link's 5 s timeout; nothing registers anything.
Everything happens on the ``lab`` surface, inside the fluids worker's region (``REGION``); a
step refuses any tile or entity outside it.

The flow (``FK_LINK=on python3 -m fkcore build games/lab-fluids/lab.build.fkb``) builds the
design. What lab ground and the lab rules leave to a fixture, and nothing else:

  water    the surface file's ``lake-*`` claims become water tiles (lab ground has none, and an
           offshore pump is placed only on a shore): run before the build
  start    coal into every boiler (its coal has no net: UNFED), and each infinity pipe set to the
           fluid its .fkp line names (the lab's free materials): run after the build
  measure  two samples ``--seconds`` apart: sulfur made (the lab force's production statistics),
           steam made, what the steam engines generate (energy_generated_last_tick), and the fluid
           in the machines' boxes; sulfur against the chemical plant's full-speed rate
  info     what stands in the region, and which chunks of the apply's generation square exist

Each step announces itself in game chat ([fk5 fluids] ...), for Rory watching with /lab.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from fkcore import compose, fkp, link  # noqa: E402
from fkcore import surface as surfacemod  # noqa: E402
from fkcore.catalog import Catalog  # noqa: E402

GAME = os.path.join(os.path.dirname(HERE), "games", "lab-fluids")
SURF, FORCE = "lab", "lab"
REGION = (740, 400, 860, 560)          # x0, y0, x1, y1: the fluids worker's lab region
COAL = 50


def say(r, text):
    return r.lua(link.lua_say(f"[fk5 fluids] {text}"))


def inside(x, y):
    return REGION[0] <= x < REGION[2] and REGION[1] <= y < REGION[3]


def lakes(game=GAME):
    """{claim name: [(x, y)]} of the surface file's lake-* claims (the pumps' water)."""
    sf = surfacemod.load(os.path.join(game, "lab.surface"))
    out = {}
    for name, c in sorted(sf.claims.items()):
        if name.startswith("lake-"):
            out[name] = [(x, y) for x in range(c.x0, c.x1) for y in range(c.y0, c.y1)]
    return out


def composed(game=GAME, cat=None):
    cat = cat or Catalog.load()
    sf = surfacemod.load(os.path.join(game, "lab.surface"))
    lay = fkp.load(os.path.join(game, "lab.fkp"))
    facs = {}
    for p in sf.places.values():
        f = fkp.load(os.path.join(game, f"{p.module}.fkp"))
        f.name = p.factory
        facs[p.factory] = f
    return compose.compose(lay, facs, cat)


def fixtures(s):
    """(boilers [(x, y)], infinity pipes [(x, y, fluid)], machines {key: (name, x, y)}) of the
    composed design, all inside REGION."""
    boilers, pipes, machines = [], [], {}
    for key in sorted(s.entities, key=fkp.natural_key):
        e = s.entities[key]
        if not inside(e.x, e.y):
            raise SystemExit(f"{key} at {e.x},{e.y} is outside the region {REGION}")
        if e.name == "boiler":
            boilers.append((float(e.x), float(e.y)))
        elif e.name == "infinity-pipe":
            pipes.append((float(e.x), float(e.y), e.attrs["fluid"]))
        if e.name in ("offshore-pump", "boiler", "steam-engine", "chemical-plant",
                      "infinity-pipe"):
            machines[key] = (e.name, float(e.x), float(e.y))
    return boilers, pipes, machines


def lua_water(tiles):
    data = json.dumps([[x, y] for x, y in tiles])
    return f"""
local s = game.get_surface('lab')
local ts = {{}}
for _, t in pairs(helpers.json_to_table({json.dumps(data)})) do ts[#ts + 1] = {{name = 'water', position = t}} end
s.set_tiles(ts, false, false, true, false)
local n = 0
for _, t in pairs(ts) do if s.get_tile(t.position[1], t.position[2]).name == 'water' then n = n + 1 end end
rcon.print(n)
"""


def lua_start(boilers, pipes, coal=COAL):
    data = json.dumps({"boilers": [[x, y] for x, y in boilers],
                       "pipes": [[x, y, f] for x, y, f in pipes]})
    return f"""
local s = game.get_surface('lab')
local d = helpers.json_to_table({json.dumps(data)})
local fueled, set = 0, 0
for _, p in pairs(d.boilers) do
  local e = s.find_entity('boiler', {{p[1], p[2]}})
  if e then fueled = fueled + e.insert{{name = 'coal', count = {coal}}} end
end
for _, p in pairs(d.pipes) do
  local e = s.find_entity('infinity-pipe', {{p[1], p[2]}})
  if e then e.set_infinity_pipe_filter{{name = p[3], percentage = 1, mode = 'at-least'}} set = set + 1 end
end
rcon.print(fueled .. ' ' .. set)
"""


def lua_sample(machines):
    data = json.dumps({k: [n, x, y] for k, (n, x, y) in machines.items()})
    return f"""
local s = game.get_surface('lab')
local f = game.forces['lab']
local items = f.get_item_production_statistics('lab')
local fluids = f.get_fluid_production_statistics('lab')
local out = {{tick = game.tick, sulfur = items.get_input_count('sulfur'),
  steam = fluids.get_input_count('steam'), machines = {{}}}}
local watts = 0
for key, m in pairs(helpers.json_to_table({json.dumps(data)})) do
  local e = s.find_entity(m[1], {{m[2], m[3]}})
  if e then
    local row = {{status = e.status}}
    for k, v in pairs(defines.entity_status) do if v == e.status then row.status = k end end
    local box = {{}}
    for i = 1, #e.fluidbox do
      local c = e.fluidbox[i]
      box[#box + 1] = c and (c.name .. ' ' .. math.floor(c.amount)) or '-'
    end
    row.fluid = box
    if m[1] == 'steam-engine' then
      row.w = e.energy_generated_last_tick * 60
      watts = watts + row.w
    end
    if m[1] == 'chemical-plant' then row.crafted = e.products_finished end
    out.machines[key] = row
  end
end
out.engines_w = watts
rcon.print(helpers.table_to_json(out))
"""


LUA_INFO = """
local s = game.get_surface('lab')
local n = s.count_entities_filtered{area = {{%d, %d}, {%d, %d}}}
local have = {}
for cx = %d, %d do for cy = %d, %d do
  if s.is_chunk_generated({cx, cy}) then have[#have + 1] = cx .. ',' .. cy end
end end
rcon.print(helpers.table_to_json({entities = n, chunks = have, tick = game.tick}))
"""


def step_water(r, a):
    tiles = [t for ts in lakes().values() for t in ts]
    bad = [t for t in tiles if not inside(*t)]
    if bad:
        raise SystemExit(f"lake tiles outside the region: {bad[:4]}")
    say(r, f"setting {len(tiles)} lake tiles to water for the two offshore pumps")
    got = int(r.lua(lua_water(tiles)).strip())
    print(f"water: {got} of {len(tiles)} tiles are water")


def step_start(r, a):
    boilers, pipes, _m = fixtures(composed())
    got = r.lua(lua_start(boilers, pipes)).split()
    say(r, f"lab fixtures: {got[0]} coal into {len(boilers)} boilers, {got[1]} infinity pipe(s) "
           f"set to {', '.join(f for _x, _y, f in pipes)}")
    print(f"start: coal inserted {got[0]}, infinity pipes set {got[1]}")


def step_measure(r, a):
    _b, _p, machines = fixtures(composed())
    s0 = json.loads(r.lua(lua_sample(machines)))
    time.sleep(a.seconds)
    s1 = json.loads(r.lua(lua_sample(machines)))
    dt = (s1["tick"] - s0["tick"]) / 60.0
    sulfur = (s1["sulfur"] - s0["sulfur"]) / dt if dt else 0.0
    steam = (s1["steam"] - s0["steam"]) / dt if dt else 0.0
    full = 2.0                              # sulfur: 2 a craft, 1 s at crafting speed 1
    print(f"measure over {dt:.2f} s (ticks {s0['tick']}..{s1['tick']}): sulfur {sulfur:.3f}/s "
          f"(full speed {full}/s, ratio {sulfur / full:.3f}), steam {steam:.1f}/s, steam engines "
          f"{s1['engines_w'] / 1000:.1f} kW")
    for key in sorted(s1["machines"], key=fkp.natural_key):
        m = s1["machines"][key]
        print(f"  {key}: status {m['status']}, fluid {m['fluid']}"
              + (f", {m['w'] / 1000:.1f} kW" if "w" in m else "")
              + (f", crafted {m['crafted']}" if "crafted" in m else ""))
    say(r, f"measured over {dt:.1f} s: sulfur {sulfur:.2f}/s (full speed 2/s), steam "
           f"{steam:.0f}/s, engines {s1['engines_w'] / 1000:.0f} kW")
    with open("/tmp/fk5-fluids-measure.json", "w") as fh:
        json.dump({"before": s0, "after": s1, "seconds": dt, "sulfur_per_s": sulfur,
                   "steam_per_s": steam}, fh, indent=1)


def step_info(r, a):
    x0, y0, x1, y1 = REGION
    cx, cy = a.chunk
    got = json.loads(r.lua(LUA_INFO % (x0, y0, x1, y1, cx - 2, cx + 2, cy - 2, cy + 2)))
    print(f"info: {got['entities']} entities in the region; chunks of the square around "
          f"{cx},{cy} generated: {len(got['chunks'])} of 25: {' '.join(got['chunks'])}")


STEPS = {"water": step_water, "start": step_start, "measure": step_measure, "info": step_info}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", nargs="+", choices=sorted(STEPS))
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--chunk", default="25,14", help="centre chunk of the apply's square")
    a = ap.parse_args(argv)
    a.chunk = tuple(int(v) for v in a.chunk.split(","))
    with link.Rcon() as r:
        for name in a.steps:
            STEPS[name](r, a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
