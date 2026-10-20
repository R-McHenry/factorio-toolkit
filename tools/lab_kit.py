"""lab_kit: a robot kit on the lab surface, so play-rule builds can be watched there (Rory: "I like
to see stuff happening").

    python3 tools/lab_kit.py GAME_DIR [--clear X0,Y0,X1,Y1]

Built directly (lab rules: the lab force, free materials), from the game codebase's own design:
the surface .fkp's ``kit/r0`` roboport (with 50 construction and 20 logistic robots),
``kitpower/e0`` energy interface (20 MW) and ``kitpower/p0`` pole, and two storage chests inside
the surface file's ``kit`` claim, holding what the design needs (its bill of materials, twice) and
the plates its requesters ask for. ``--clear`` first destroys everything in that area of the lab
surface (never characters). Then ``fk build`` (play mode, ``force lab``) pastes the factories as
ghosts and the robots build them from the chests. One RCON call per step (fkcore.link).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from fkcore import fkp, link  # noqa: E402
from fkcore import surface as surfacemod  # noqa: E402

SURF, FORCE = "lab", "lab"
PLATES = {"iron-plate": 800, "copper-plate": 800}


def bom(game, sf):
    need = {}
    for p in sf.places.values():
        path = os.path.join(game, f"{p.module}.fkp")
        if os.path.exists(path):
            for e in fkp.load(path).entities.values():
                need[e.name] = need.get(e.name, 0) + 1
    return need


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("game")
    ap.add_argument("--clear")
    a = ap.parse_args(argv)
    surfaces = [f for f in os.listdir(a.game) if f.endswith(".surface")]
    sf = surfacemod.load(os.path.join(a.game, surfaces[0]))
    infra = fkp.load(os.path.join(a.game, f"{sf.name}.fkp")).entities
    port, eei, pole = infra["kit/r0"], infra["kitpower/e0"], infra["kitpower/p0"]
    claim = sf.claims["kit"]
    chests = [(claim.x0 + 1.5, claim.y0 + 1.5), (claim.x0 + 2.5, claim.y0 + 1.5)]
    need = bom(a.game, sf)
    stock = {name: 2 * n + 10 for name, n in need.items()}
    stock.update({k: v for k, v in PLATES.items()})
    stock["roboport"] = stock.get("roboport", 0) + 2
    stock["medium-electric-pole"] = stock.get("medium-electric-pole", 0) + 20
    with link.Rcon() as r:
        if a.clear:
            x0, y0, x1, y1 = (int(v) for v in a.clear.split(","))
            print("cleared", r.lua(link.lua_destroy(SURF, (x0, y0, x1, y1))).strip())
        print("chunks", r.lua(link.lua_generate(SURF, FORCE, (float(port.x), float(port.y)), 3)).strip())
        body = f"""
local s = game.get_surface('lab') local f = game.forces['lab']
local P = helpers.json_to_table({json.dumps(json.dumps([float(port.x), float(port.y)]))})
local E = helpers.json_to_table({json.dumps(json.dumps([float(eei.x), float(eei.y)]))})
local L = helpers.json_to_table({json.dumps(json.dumps([float(pole.x), float(pole.y)]))})
local C = helpers.json_to_table({json.dumps(json.dumps(chests))})
local S = helpers.json_to_table({json.dumps(json.dumps(sorted(stock.items())))})
local out = {{}}
local rp = s.create_entity{{name = 'roboport', position = P, force = f}}
if rp then
  local inv = rp.get_inventory(defines.inventory.roboport_robot)
  inv.insert{{name = 'construction-robot', count = 50}} inv.insert{{name = 'logistic-robot', count = 20}}
  out[#out + 1] = 'roboport'
end
local e = s.create_entity{{name = 'electric-energy-interface', position = E, force = f}}
if e then e.power_production = 20000000 / 60 e.electric_buffer_size = 20000000 out[#out + 1] = 'power 20 MW' end
if s.create_entity{{name = 'medium-electric-pole', position = L, force = f}} then out[#out + 1] = 'pole' end
local boxes = {{}}
for _, c in ipairs(C) do boxes[#boxes + 1] = s.create_entity{{name = 'storage-chest', position = c, force = f}} end
local short, i = {{}}, 1
for _, kv in ipairs(S) do
  local left = kv[2]
  while left > 0 and i <= #boxes do
    local n = boxes[i].get_inventory(defines.inventory.chest).insert{{name = kv[1], count = left}}
    if n == 0 then i = i + 1 else left = left - n end
  end
  if left > 0 then short[#short + 1] = kv[1] .. ':' .. left end
end
out[#out + 1] = #boxes .. ' chests, short {{' .. table.concat(short, ',') .. '}}'
rcon.print(table.concat(out, ' | '))
"""
        print("kit", r.lua(body).strip())
        print(r.lua(link.lua_say(f"[fk5 lead] play rules on the lab surface: a robot kit at "
                                 f"{port.x},{port.y}; fk build pastes ghosts, the robots build "
                                 "the factories. /lab to watch.")).strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
