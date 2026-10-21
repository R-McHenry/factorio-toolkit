-- how many of each item ({ITEMS}, a comma list) the robot network holds
local nets = game.forces.player.logistic_networks.nauvis or {}
local out = {}
for item in string.gmatch('{ITEMS}', '[^,]+') do
  local n = 0
  for _, net in pairs(nets) do n = n + net.get_item_count(item) end
  out[#out + 1] = item .. ' ' .. n
end
rcon.print(table.concat(out, ', '))
