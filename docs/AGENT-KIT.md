# The agent kit: what a V1 player run gets (draft, 2026-10-20)

Rory's goal: the toolkit game-ready for an agent. This is the agent-facing side, drafted in v5.
Putting it into `C:\fk-player` and the host's kickoff waits for Rory's go (through the supervising
session).

## The run folder (`kickoff/new_run.py`)

```
<run>\AGENTS.md          the brief: agent/prompts/core-v1.md (the V1 successor of fk-player's core.md)
<run>\GOAL.md, FRICTION.md
<run>\docs\              TOOLKIT.md (commands, verdicts, checks), LANGUAGE.md (.fk and the templates),
                         EXAMPLES.md + examples\ (three factories that build clean on paper)
<run>\bin\fk.cmd, fk.py  the agent's one command
<run>\.toolkit\fkcore\   the toolkit, pinned at a sha (git archive): the design steps run here
<run>\game\              the game codebase: nauvis.surface, nauvis.build.fkb, plant.fk + plant-w3.json,
                         nauvis.fkp (the plant's pole chain), map.terrain.json (written at kickoff)
<run>\run.json           where the game is: host, host_game, host_toolkit (fk-v5-<sha>), the brief's md5
```

The toolkit is pinned per run on both sides, so files a running session uses never change under
it (CLAUDE.md). A run with `"host": "local"` plays a laptop test server (the rehearsal).

## `fk`, the one command (`agent/fk.py`)

| command | runs | what |
|---|---|---|
| `fk build [--from S --to S]` | design on the laptop, diff + apply on the host | the flow (`nauvis.build.fkb`); split at the first game step, the floorplan replayed on the host |
| `fk rates/check/explain/unfold FILE.fk ...` | laptop | the model on paper |
| `fk split-to-chest`, `chests-to-net`, `net-to-chests`, `merge`, `insert` | laptop | rewiring, source and layout only |
| `fk look AREA [--design]` | host (design: laptop) | the area live against the design (fair play: only the area) |
| `fk measure AREA`, `fk adopt X,Y --into F/NET` | host | live rates against the model; a hand fix into the source |
| `fk alerts`, `fk stats`, `fk chart`, `fk read-terrain` | host | the alert panel; the free reads; the bare ground |
| `fk chat`, `fk say TEXT` | host | Rory |

Every command ends with `fkcore poll`: chat lines since the last command, and the game's new
alerts and reminders. Those are the only unasked channels in play (CORE-V1 decision 11).

Built today: build (both halves), rates, check, explain, unfold, render, split-to-chest, chat,
say, poll (chat part), look --design. Coming from the workers: the live look, alerts, stats,
chart (worker sense), read-terrain and @patch (worker terrain). Still to do: the CLI of measure,
adopt, merge, insert, chests-to-net and net-to-chests (the functions exist).

## The V1 kickoff (host side; drafted, not wired)

1. Retire `world.zip` (never deleted). Make the map from the **fk-play scenario** with the
   kickoff's map-gen settings (`--start-server-load-scenario fk-play --map-gen-settings
   map-gen-w3.json`) instead of `--create`: the lab surface, `/lab` and the chat journal come with
   the map. Under the current lab drop-in (`factorio.service.d/lab.conf`), the kickoff would need
   the drop-in changed too: Rory's call.
2. `kickoff/setup_v1.py`: bootstrap, kit, starter rules. **No chat handler through RCON**: v4's
   `setup.py` still runs `fk/chat.py`'s `INSTALL_LUA`, a `script.on_event` over RCON, which is the
   pattern that made saves unjoinable on 2026-10-18. The scenario's `fk_chat.lua` replaces it.
   **No plant paste**: the plant is the game codebase's `plant` factory, so the run's first build
   pastes it.
3. `read-terrain` of the starting area into `game\map.terrain.json` (worker terrain).
4. `new_run.py` makes the run folder; the toolkit at the run's sha is deployed to
   `/home/computah/factorio/fk-v5-<sha>`; the first `fk build` pastes the plant and the pole
   chain, and the robots build them from the kit before the agent starts.

## Open for Rory

- Wiring this into `C:\fk-player` (template, prompts) and the host's kickoff.
- Where V1 runs happen: a fresh map per run (the kickoff), and what becomes of the test map.
- The reminder cadence for a persisting alert (default 10 min in the drafts).
