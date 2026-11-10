# 3.3: shared saves through a gateway, and a replica to work on

3.3 is step 1 of PLAN-COMMONS (`..\assessment-20261110\PLAN-COMMONS.md`), Rory's direction of
2026-11-10. Outside agents (OpenClaw/Moltbook agents, AI Village's Opus agents) play a few shared
live saves together. They install the toolkit on their own machines, design and debug on a
private replica of the save with full RCON, and reach the shared save itself only through its
fk-gateway. The gateway holds the save's RCON, journals every call and serves the game's answer
files. Branch `claude/60-gateway`.

## FK_LINK=gateway

- `FK_LINK=gateway`, `FK_GATEWAY=https://HOST/v1/saves/commons`, and the agent's key in
  `FK_GATEWAY_KEY` or `FK_GATEWAY_KEY_FILE`: every game command works as with `FK_LINK=on`.
  - `link.connect()` opens the link the env names: an `Rcon`, or a `Relay` for a gateway.
  - `open_from_env` and `fk read-terrain` use it.
- `link.Relay` has `Rcon`'s calls (`call`, `lua`, a context manager).
  - The Lua still goes as one `/sc` line, and `assert_safe` still refuses registering Lua before
    anything leaves.
  - The protocol (one save per base URL; `Authorization: Bearer KEY`; `X-FK-Toolkit: <version>`):

    | Call | Answer |
    |---|---|
    | `GET hello` | `{"save", "factorio", "toolkit"}` |
    | `POST rcon {"cmd"}` | `{"reply"}` |
    | `GET out/<path>[?remove=1]` | an answer file under script-output, 404 until it's written |
    | `GET save` | the save as it stands, a zip |

- `link.read_answer(r, "fk5/<tag>.json", what, keep, wait)` reads the game's answer file from the
  gateway for a `Relay`, else from `OUT_DIR`. It waits for the file and for its JSON to be whole.
  - `read_output` uses it, and so do `measure.read` and `terrain.read`, which read the file
    themselves.
  - The stats recorder's file (`fk-stats/samples.jsonl`) can't be tailed through a gateway, so
    `runstats.sample` takes its RCON sample there.
- Host-only setup (`kickoff_setup`) and the `tools/*_live.py` scripts keep `link.Rcon`: they never
  go through a gateway.

## fk replica

```
fk replica GAME            # setup if needed, pull the shared save, start it paused
fk replica GAME setup      # download Factorio's headless server (the gateway's version)
fk replica GAME pull       # the shared save as it stands, as save state live (--name)
```

- The replica is the run's planner (`fk sim`) started from the shared save. Everything `fk sim`
  does works on it: `save`, `load`, `speed`, `run`, `place`, `stop`, and any Lua through
  `FK_LINK=on` with `fk sim env`.
- `setup` downloads `https://factorio.com/get-download/<version>/headless/<build>`. That's a free
  download with no account, as long as the request carries a User-Agent (factorio.com answers
  Python's default with 403).
  - It's unpacked under `FK_HOME` (default `~/.fk`) as `factorio/<version>/`.
  - The planner remembers the binary in `sim\factorio.json`.
  - `Sim` now takes its binary from `FK_LAPTOP_FACTORIO`, else that file, else the laptop's
    Steam Factorio.
- Builds: `linux64`, and `linux-arm64` from 2.1.24. The headless server is Linux only; on
  Windows or macOS run the toolkit in WSL or a Linux container, or point `FK_LAPTOP_FACTORIO` at
  a Factorio you have.
- At the end, `fk replica` prints the env that points the toolkit at the replica, and how to
  switch back to the shared save.

## Measured

- `tests.test_gateway_link`: 15 tests. They run against a stub gateway on localhost (hello, lua
  as one line, the registering guard, a wrong key's 401, answer files with `remove`, a late file,
  give-up) and a fake headless download (the URL, the User-Agent, the unpack, `sim\factorio.json`,
  the off-Linux refusal, the pull).
- End to end in WSL (Ubuntu, x86_64, Python 3.12):
  - the setup: a stub gateway serving `megahub-20261108-final.zip` (2.1.24);
  - `fk replica GAME` downloaded the real 2.1.24 headless server, pulled the save and started it
    paused;
  - a Lua call through `FK_LINK=on` with `fk sim env` answered from the replica;
  - `fk sim stop` stopped it.
  - the whole of `fk replica GAME` took 29 s (download, unpack, pull of 14.4 MB, boot);
  - the start re-saved paused at tick 20685076;
  - the Lua answered `20685076 surfaces 2 paused true`.

  ```
  replica: Factorio at /tmp/fkrep/home/factorio/2.1.24/factorio/bin/x64/factorio
  replica: the shared save as save state live (14.4 MB)
  sim: running from save state live, paused at tick 20685076 (it was saved running, ...)
  replica: point the toolkit at it with  FK_RCON_HOST=127.0.0.1 FK_RCON_PORT=56667 ... FK_LINK=on
  ```
