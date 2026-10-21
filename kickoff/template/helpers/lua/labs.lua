-- what the labs wait for, pack by pack
local f = game.forces.player
local res = f.current_research
if not res then rcon.print('nothing researches') return end
local n, waiting, lack = 0, 0, {}
for _, l in pairs(game.surfaces.nauvis.find_entities_filtered{type = 'lab', force = 'player'}) do
  n = n + 1
  if l.status == defines.entity_status.missing_science_packs then
    waiting = waiting + 1
    local inv = l.get_inventory(defines.inventory.lab_input)
    for _, ing in pairs(res.research_unit_ingredients) do
      if inv.get_item_count(ing.name) == 0 then lack[ing.name] = (lack[ing.name] or 0) + 1 end
    end
  end
end
local out = {string.format('%s %d%%: %d of %d labs wait', res.name, math.floor(f.research_progress * 100), waiting, n)}
for pack, k in pairs(lack) do out[#out + 1] = string.format('  %s missing in %d', pack, k) end
rcon.print(table.concat(out, '\n'))
