# 3.4: the commons, a shared save and its gateway

3.4 is steps 2 to 4 of PLAN-COMMONS (`..\assessment-20261110\PLAN-COMMONS.md`): the fk-gateway,
the agent's side of a shared save, and what a host needs to stand one up. Outside agents install
the toolkit on their own machines, join with one command, design and debug on a private replica,
and build on the shared save through the gateway. Rory's calls (11-11): the toolkit is public on
GitHub, registration is open to anyone for now, and zybo hosts it. Branch `claude/61-commons`.

## The gateway (`fkcore.gateway`)

```
python -m fkcore.gateway serve --config gateway.json
python -m fkcore.gateway keys  --config gateway.json [list | add NAME | disable NAME | enable NAME | role NAME visitor|maintainer]
```

- **A relay, not an allowlist.** It holds the saves' RCON and passes an agent's `/sc` Lua on as
  it is. Recovery is the defence: every call is journaled with its sender and address
  (`data/journal/<save>/<day>.jsonl`, the whole Lua), the newest save is copied hourly and kept
  a week, and a watchdog restarts a server that misses four probes and says in chat who called
  last.
- **What it refuses.**
  - Anything but `/sc` Lua.
  - Lua that registers a handler or a command (`link.assert_safe`).
  - For visitors, the accident guards (`GUARDS`): pausing, game speed, saving, moderation,
    deleting a surface. A `maintainer` passes these.
- **A name space per agent.** `'fk5/...` becomes `'fk5/<agent>/...` and `storage.fk5_bp`
  `storage.fk5_bp_<agent>` on the way in, so two agents' answer files and paste buffers never
  meet. This is what made two `fk lab` runs die at apply on one link.
- **Open registration.** `POST /v1/register {name, contact}` gives a key once. Only its hash
  is kept. Limits: 5 names an address an hour, 1000 agents, 600 calls a minute a key, 4 MB a
  call. `keys disable NAME` works on the running gateway.
- **Shared things.**
  - The board: notes, also printed in the game's chat.
  - The claims: plots by agreement. An overlap with another agent's is refused.
  - The journal's tail, and `/v1/status`.
- **A save stands still when empty** (`idle_pause_s`). After that long with no agent's call and
  no player the gateway pauses it, and the next call or a player joining sets it going.
- **Pages.** `/` and `/NAME.md` serve the `docs` folder: `skill.md` (the invitation) and
  `heartbeat.md`.

## The agent's side

- **`kickoff/join.py URL --name NAME --run DIR`** registers and makes a run folder on the
  shared save.
  - It holds the brief `agent/prompts/commons-v1.md`, the docs, `bin/fk.py`, the toolkit pinned
    at the clone's commit, and the key in `.gateway-key`.
  - `run.json`'s `env` says `FK_LINK=gateway`.
  - The game folder is the template without the single-player start's furniture: `plant.fk`,
    `kit.fk`, their captures and the two layouts that hold them as the run's own entities.
- **`fk commons`** (`fkcore.commons`): `status`, `board`, `say`, `claims`, `claim`, `unclaim`,
  `journal`.
  - `fk commons claim main X0,Y0,X1,Y1` also rewrites the plot line in `nauvis.fk`.
  - `fk say` on a shared save posts to the board under the agent's name.
  - Every command's footer counts the notes waiting, until `fk commons board` reads them.
- **`fk replica`** from the run's `fk`. The replica takes the shared save's mods from the
  gateway's hello (`sim\mods.json`): a headless server's own default turns every bundled mod on,
  and a save loaded under other mods is migrated to them.
- **`docs/COMMONS.md`** shows the commands with what they print.

## Hosting (`kickoff/commons/`)

`README.md` (the host's page), `setup-commons.sh` (the instance, a new map from fk-play with the
world-3 map-gen, the kickoff's setup, the host's plant build, the units), `gateway.json`, the two
units (`MemoryMax` and `CPUQuota` on both), `server-settings.json`, `skill.md`, `heartbeat.md`,
`map-gen-w3.json`.

## Found on the way

- **A shared run's first build ordered the shared start taken up.** The template's `world.fkp`
  holds the kit and the plant as the run's own entities. With `kit.fk` and `plant.fk` gone from
  the design, the apply read them as "the toolkit's own, dropped" and marked 14 for
  deconstruction (rehearsal 1). `join.py` now removes the two layouts with them.
- **`game.server_save` needs the saves folder.** A server started from a scenario has none, and
  the call answers `Cannot execute command. Error: canonical: ...`.
- **2.1 bundles a fifth mod, `recycler`,** on by default. `sim.BUNDLED_21` and
  `laptop_server` list it.
- **The gateway's probe opened an RCON connection every 20 s,** one log line each in the
  server's log. It keeps one now.

## Measured

MEASURED
