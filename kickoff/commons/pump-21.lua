local s = game.surfaces.nauvis
local f = game.forces.player
local g = s.find_entities_filtered{type = 'entity-ghost', ghost_name = 'offshore-pump', position = {-25.5, -37.5}, radius = 0.6}[1]
if not g then rcon.print('pump-21: no pump ghost at -25.5,-37.5: nothing to do') return end
g.destroy()
local a = s.create_entity{name = 'entity-ghost', inner_name = 'offshore-pump', position = {-26.5, -36.5}, direction = defines.direction.north, force = f}
local b = s.create_entity{name = 'entity-ghost', inner_name = 'pipe', position = {-26.5, -35.5}, force = f}
rcon.print('pump-21: the pump ghost moved to -26.5,-36.5 (' .. tostring(a ~= nil) .. '), a pipe ghost at -26.5,-35.5 (' .. tostring(b ~= nil) .. ')')
