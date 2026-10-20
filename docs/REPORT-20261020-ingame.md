# V1 in the game: lab test bench (2026-10-20)

Rory's go, as the supervising session relayed it: in-game testing, no play, on the same server
session, with the live world shelved first. No player or DSH agent ran; nothing was registered
through RCON (`fkcore.link.assert_safe` refuses such Lua); every game call was one RCON command
with a 5 s timeout. The bench is `tools/lab_bench.py`, deployed as
`/home/computah/factorio/fk-v5-570dc52`; its JSON is `/tmp/fk5-bench.json` on computah-ct.

## The shelve and the test map

- The running world (tick 6,171,302) was saved as `server/factorio/saves/shelved-20261020.zip`
  (2.34 MB, zip test OK). The other session re-saved it at 04:29:59 just before it stopped the
  service, and kept `instance/saves/world-shelved-20261020.zip`, which is md5-identical to
  `instance/saves/world.zip`. The old world's 5 autosaves (03:40 to 04:20 UTC) are copied to
  `server/factorio/saves/shelved-20261020-autosaves/`, made before the lab map's first autosave.
- The test map runs on the same `factorio.service`, port, settings and RCON, through the drop-in
  `/etc/systemd/system/factorio.service.d/lab.conf` (it starts `server/factorio/saves/lab-test.zip`,
  made from the `fk-play` scenario of v5 1a22eda, byte-identical to `scenario/fk-play`).
- **Rory joins it the usual way.** `/lab` goes to the lab surface (as a spectator, on the lab
  force), and `/lab` again comes back. The bench's build stands on the lab surface around
  (200, 200)..(263, 250).
- **Back to the old world:**
  ```
  rm /etc/systemd/system/factorio.service.d/lab.conf
  systemctl daemon-reload
  systemctl restart factorio
  ```
  The service then starts `instance/saves/world.zip` again (the shelved world). Make a copy of
  `lab-test.zip` first if it should be kept.

## What passed (numbers from the bench)

| step | result |
|---|---|
| scenario | level `fk-play`; surfaces nauvis + lab; forces player, enemy, neutral, lab; lab force 252 of 275 technologies researched; lab surface peaceful with lab tiles |
| game link | snapshot of empty ground = 0; a 3-entity named paste lands exactly where designed (offset 0,0); revive 3, decon marks 3, destroy 3, 0 left |
| **apply + diff** | games/redgreen main (1014 entities) composed onto a lab plot: one superforced paste, **1014/1014 ghosts where designed** (no correction), 1014 revived (lab: free materials), 0 failed, 2.5 s. **Diff after the build: OK 1014, nothing else: 1:1** |
| look parity | live and design rendered by the same renderer over 53 rows: **identical, 0 tiles differ** |
| watcher | an unkeyed belt in sanctioned space: marked `unknown@10150` until tick 442150 (2 h); an unkeyed fix in the plot next to net `belt`: kept (mark, no expiry), hint "looks like a fix to it"; the same look with strict policy: **2 NOBODY**; notify all pushed 2 lines |
| adopt | the fix adopted as `~belt/a0`: the next look is **OK 1015, MARKED 1** (the sanctioned belt), 0 invariant failures |
| measure | one gear assembler fed by an infinity chest on an energy interface: **0.997 gears/s against the model's 1.0** (10 crafts in 602 ticks) |
| alerts | a damaged chest on nauvis gives Rory (connected, player force) 1 alert in `LuaPlayer.get_alerts`; the lab force has 0 players and `LuaForce` has no `get_alerts`: **alerts are per player only** |

## What broke, and was fixed on the spot

1. **The first paste placed nothing.** A new surface has almost no generated chunks.
   `link.lua_generate` requests, generates and charts them first (225 chunks).
2. **17 drills were not placed** (997 of 1014). The game places a drill only on ore, and the lab
   has none. `link.lua_seed` puts each drill row's designed resource under its tiles (153 tiles),
   and the paste then placed all 1014.
3. **22 furnaces read as DRIFT** ("recipe None"). A furnace reports no recipe while idle and has no
   recipe setting, so `sense` no longer compares furnace recipes.
4. **The pasted poles were not wired.** All 40 of the layout's poles came out with 0 copper wires,
   one electric network each: a blueprint without wires builds unwired poles. That answers the
   power worker's open question. The codec now derives the wires (a minimum spanning forest within
   wire reach, written as the game's own `[[a, 5, b, 5]]`; the format was taken from a blueprint
   the game exported). The next paste gave **40 poles, 40 wired, 1 electric network**. Wires stay
   derived, so the `.fkp` round trip is unchanged.
5. Large blueprints go in RCON-sized chunks through `storage.fk5_bp`, then one build (`link.paste`).

## Not done, or still open

- **`/lab` by hand:** the scenario's surface and force are verified. The command itself needs a
  player typing it: Rory's test.
- **Alerts for an offline player:** run `python3 tools/lab_bench.py --steps alerts` after Rory
  disconnects. With no player in a force there is nothing to read, so the agent's force needs a
  player (connected or offline) for the alert push.
- Wires through robots rather than revive: the blueprint now carries them, so ghosts should be
  built wired; to be seen on the first robot-built apply.
- The bench builds with revive (lab rules); a real apply goes through robots and stock.
