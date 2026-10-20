-- fk_lab: the lab of the fk toolkit (CORE-V1.md 6.5, Rory's decision 12), an event_handler lib.
--
-- The lab is a separate SURFACE ("lab") in the same game, on its own FORCE ("lab"), so its
-- research and production statistics never mix with the real game's: both are per force, and so
-- are its chart, alerts and logistic network. No enemies and peaceful; new chunks are lab tiles.
-- The lab force has every technology researched, for prototyping. Agents build there through
-- the game link (lab mode allows direct building); nothing here builds.
--
-- /lab moves the player who types it to the lab, as a spectator and on the lab force (to see the
-- lab's chart, alerts and stats), and /lab again brings them back: the same surface, position
-- and force, and their character if they had one. A /lab from the console or RCON has no player
-- and does nothing. The command is added in add_commands, which event_handler calls from
-- on_init and on_load, i.e. at script load on every machine.
local LAB = "lab"

local lab = {}

local function state()
  storage.fk_lab = storage.fk_lab or {players = {}}
  return storage.fk_lab
end

local function ensure_lab()
  local surface = game.get_surface(LAB)
  if not surface then
    surface = game.create_surface(LAB, {
      seed = 1,
      width = 2048,
      height = 2048,
      peaceful_mode = true,
      no_enemies_mode = true,
      starting_area = "none",
      default_enable_all_autoplace_controls = false,
    })
    surface.generate_with_lab_tiles = true
    surface.always_day = true
  end
  local force = game.forces[LAB]
  if not force then
    force = game.create_force(LAB)
    force.research_all_technologies()
    local player_force = game.forces["player"]
    force.set_friend(player_force, true)
    force.set_cease_fire(player_force, true)
    player_force.set_friend(force, true)
    player_force.set_cease_fire(force, true)
  end
  return surface, force
end

local function go(player)
  local data = state()
  local surface, force = ensure_lab()
  if player.surface.name ~= LAB then
    data.players[player.index] = {
      surface = player.surface.name,
      position = {x = player.position.x, y = player.position.y},
      force = player.force.name,
      character = player.character,
    }
    if player.character then
      -- detach: the character stays where it stood until /lab brings the player back
      player.set_controller({type = defines.controllers.spectator})
    end
    player.force = force
    player.teleport({0, 0}, surface)
    player.print("[fk] the lab: /lab again to go back")
  else
    local back = data.players[player.index] or {surface = "nauvis", position = {x = 0, y = 0},
                                                force = "player"}
    player.teleport(back.position, back.surface)
    player.force = back.force
    if back.character and back.character.valid then
      player.set_controller({type = defines.controllers.character, character = back.character})
    end
    data.players[player.index] = nil
    player.print("[fk] back on " .. back.surface)
  end
end

lab.add_commands = function()
  commands.add_command("lab", "Watch the fk lab surface; /lab again to go back.", function(cmd)
    if not cmd.player_index then
      return -- console or RCON: there is no player to move
    end
    local player = game.get_player(cmd.player_index)
    if player and player.valid then
      go(player)
    end
  end)
end

lab.on_init = function()
  state()
  ensure_lab()
end

lab.on_configuration_changed = function()
  state()
  ensure_lab()
end

lab.events = {}

return lab
