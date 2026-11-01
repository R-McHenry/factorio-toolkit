# seablock-server

The Sea Block test server on computah-ct, `/home/computah/sb` (copies of its scripts, 2026-11-01).
It runs the live server's binary (`/home/computah/factorio/server/factorio`) with its own write
dir (`config/config.ini`), its own mods and its own ports: game 34198, RCON 127.0.0.1:27016
(`rcon.pw`).

- `start.sh` starts what `current-map` names (kickoff-v1.sh --instance sb writes it), else the
  test map `saves/sb-test.zip`. Stop it with `pkill -u computah -f -- '[-]-port 34198'`.
- `create.sh` writes `mods/mod-list.json` from the mods folder and makes a fresh test map.
- `mods.txt` is the mod set: Sea Block 0.6.0 (its 2.0 branch), Bob's 2.1.x, Angel's 2.0.x with
  their graphics mods, CircuitProcessing, LandfillPainting and fk-early-bots (C:\fk-mods, built by
  `C:\fk-mods\resolve.py`). A client joining needs exactly this set.
