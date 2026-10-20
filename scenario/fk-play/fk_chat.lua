-- fk_chat: the chat journal of the fk toolkit, an event_handler lib (CORE-V1.md 6.5: chat is the
-- player's channel to the agent).
--
-- Every console chat line is kept in storage.fk_chat (the last 200, oldest first) with its tick and
-- the player's name, so the toolkit can read what arrived since its last read (fkcore.chat, one
-- RCON read, nothing written). The handler is registered here, in scenario code that every
-- joining client runs, never through RCON: v4 installed the same handler with an RCON
-- script.on_event (fk/chat.py INSTALL_LUA), the pattern that made saves unjoinable on 2026-10-18.
local MAX = 200

local chat = {}

local function journal()
  storage.fk_chat = storage.fk_chat or {}
  return storage.fk_chat
end

chat.on_init = function()
  journal()
end

chat.on_configuration_changed = function()
  journal()
end

chat.events = {
  [defines.events.on_console_chat] = function(event)
    local name = ""
    if event.player_index then
      local player = game.get_player(event.player_index)
      if player then
        name = player.name
      end
    end
    local t = journal()
    t[#t + 1] = {tick = event.tick, name = name, message = event.message}
    while #t > MAX do
      table.remove(t, 1)
    end
  end,
}

return chat
