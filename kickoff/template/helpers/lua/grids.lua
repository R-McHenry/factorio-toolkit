-- the electric networks by pole count, and every roboport without power
local s = game.surfaces.nauvis
local grids = {}
for _, p in pairs(s.find_entities_filtered{type = 'electric-pole', force = 'player'}) do
  local id = p.electric_network_id or -1
  grids[id] = grids[id] or {n = 0, x = p.position.x, y = p.position.y}
  grids[id].n = grids[id].n + 1
end
local out = {}
for id, g in pairs(grids) do
  out[#out + 1] = string.format('grid %d: %d poles, e.g. at %.1f,%.1f', id, g.n, g.x, g.y)
end
for _, r in pairs(s.find_entities_filtered{type = 'roboport', force = 'player'}) do
  if not r.logistic_network then
    out[#out + 1] = string.format('roboport %.0f,%.0f has no power (%.1f MJ)', r.position.x,
                                  r.position.y, r.energy / 1e6)
  end
end
rcon.print(table.concat(out, '\n'))
