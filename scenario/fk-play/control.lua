-- fk-play: Factorio 2.0 freeplay plus the fk toolkit's lab (CORE-V1.md 6.5, Rory's decision 12).
-- The same libraries base freeplay loads (data/base/script/freeplay/control.lua), in the same
-- order, then fk_lab. A scenario's script is saved into the map, so every joining client runs it:
-- /lab is registered here at script load, never through RCON or the console (an RCON-registered
-- handler made every save unjoinable on 2026-10-18).
local handler = require("event_handler")
handler.add_lib(require("__base__/script/freeplay/freeplay"))

if script.active_mods["space-age"] then
  handler.add_lib(require("space-finish-script"))
else
  handler.add_lib(require("silo-script"))
end

handler.add_lib(require("fk_lab"))
