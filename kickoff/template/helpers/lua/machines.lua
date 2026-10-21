-- each machine with its recipe and status; {ONLY}: a comma list of statuses to keep (empty: all)
local names = {}
for k, v in pairs(defines.entity_status) do names[v] = k end
local only = {}
for w in string.gmatch('{ONLY}', '[^,]+') do only[w] = true end
local out = {}
for _, e in pairs(game.surfaces.nauvis.find_entities_filtered{
    type = {'assembling-machine', 'furnace', 'lab', 'mining-drill'}, force = 'player'}) do
  local st = names[e.status] or '?'
  if next(only) == nil or only[st] then
    local r = '-'
    if e.type == 'assembling-machine' then
      local rc = e.get_recipe()
      r = rc and rc.name or 'no recipe'
    elseif e.type == 'furnace' and e.previous_recipe then
      r = e.previous_recipe.name
    end
    out[#out + 1] = string.format('%s at %.1f,%.1f: %s, %s', e.name, e.position.x, e.position.y, r, st)
  end
end
rcon.print(#out > 0 and table.concat(out, '\n') or 'none')
