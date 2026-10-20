# fk-play: freeplay plus the lab

Factorio 2.0 freeplay (the same libraries in the same order as `data/base/script/freeplay/control.lua`)
plus `fk_lab.lua`: the `lab` surface on the `lab` force and the `/lab` command (CORE-V1.md §6.5,
Rory's decision 12). Written and checked offline only: `tests/test_lab_scenario.py` checks the Lua's
block structure and the rules below. **It has not run in Factorio yet, and is not deployed.**

Rules it keeps:
- `/lab` is registered in scenario code at script load (`add_commands`, called by event_handler
  from on_init and on_load), never through RCON or the console.
- The lab is its own surface (peaceful, no enemies, lab tiles) and its own force (its own
  research, all of it done; its own production statistics, chart and alerts), friends and
  cease-fire with `player`.
- `/lab` moves the player who typed it there as a spectator on the lab force and back again to
  the same surface, position, force and character. From the console or RCON it does nothing.

To use it (waits for Rory's go): copy this folder into the server's `scenarios/` and start a new
map from it (`--start-server-load-scenario fk-play` with the same `--map-gen-settings`) instead of
kickoff's `--create`. A scenario's script lives in the save, so clients need nothing installed.
Then check in the game: `/lab` and `/lab` again as a spectator, and as a player with a character;
the lab force's research and production statistics stay apart from `player`'s.
