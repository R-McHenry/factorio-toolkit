# fk-play: freeplay plus the lab and the chat journal

Factorio 2.0 freeplay (the same libraries in the same order as `data/base/script/freeplay/control.lua`)
plus two libs of the fk toolkit:
- `fk_lab.lua`: the `lab` surface on the `lab` force and the `/lab` command (CORE-V1.md §6.5,
  Rory's decision 12).
- `fk_chat.lua`: every console chat line kept in `storage.fk_chat` (the last 200), which
  `fkcore.chat` reads so a player's message reaches the agent's next command.

`tests/test_lab_scenario.py` checks the Lua's block structure and the rules below, offline.

In the game:
- **The test map since 2026-10-20 04:34** runs this scenario, as of v5 2853de2, without `fk_chat`. It
  has the lab surface and force, peaceful with lab tiles, and 252 of 275 technologies researched
  for lab. A scenario's script lives in the save, so that map keeps the version it was made with.
- **`fk_chat`** was checked on a laptop test server (`python tools/laptop_server.py chat`): the
  scenario loads, and a chat line reaches `storage.fk_chat`.

Rules it keeps:
- `/lab` and the chat handler are registered in scenario code at script load (event_handler's
  `add_commands` and `events`, from on_init and on_load), never through RCON or the console. v4
  installed its chat handler with an RCON `script.on_event`, the pattern that made saves unjoinable
  on 2026-10-18.
- The lab is its own surface and its own force:
  - the surface is peaceful, with no enemies, lab tiles and always day;
  - the force has its own research, all of it done, and its own production statistics, chart and
    alerts;
  - it is friends and cease-fire with `player`.
- `/lab` moves the player who typed it there as a spectator on the lab force, and back again to
  the same surface, position, force and character. From the console or RCON it does nothing.

To use it: copy this folder into the server's `scenarios/` and start a new map from it
(`--start-server-load-scenario fk-play` with the kickoff's `--map-gen-settings`) instead of
kickoff's `--create`. A scenario's script lives in the save, so clients need nothing installed.
