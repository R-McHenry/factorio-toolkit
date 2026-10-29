# Toolkit 2.0.61: the speedrun planner, and a brief for a player with the whole picture

Rory, 2026-10-29: "a speedrun planning tool for the player ... another session of the game they
can run with the same seed, and they should be able to run deterministic playback sequences of
blueprint + destruction actions, as well as save or restore a save state, and also generate a
state by pasting down buildings for free", and "tickrate acceleration should be a feature of the
speedrun planner". And an Opus 5.5 run "that has a full picture rather than zoomed into the game",
which looks at other runs in a conversation with him.

## `fk sim`: the speedrun planner

`fkcore/sim.py`, on the laptop: a headless Factorio server of the laptop's own install (as
`tools/laptop_server.py` runs it), kept in the run's `sim\` folder (config, write-data, save states,
RCON password, `state.json`). It stays up between commands and never touches the live game.

- **The same map.** `fk sim fetch` copies the run's start, `v1-RUN-start.zip`, which the kickoff now
  keeps beside the run's save (`kickoff-v1.sh`, step 6). That's the same seed and the same first
  tick. `fk sim fetch --live NAME` saves the live game and copies that.
- **Deterministic.** The game stands still (`game.tick_paused`) except while `run N` / `until T`
  moves it on (`game.ticks_to_run`), so every action lands on a known tick.
- **Fast.** `speed X` sets `game.speed`, up to 1000. At 100 the laptop runs about 21 times real time:
  3600 ticks in 1.6-2.8 s on the starterbus run's map.
- **Save states.** `save NAME`, `load NAME`, `saves`.
- **Free building.** `place FILE @X,Y` builds a laid-out design (`.fkp`) or a blueprint (`.txt`,
  `.json`) at once: what's in the way (trees, rocks) is removed, landfill is laid on water, every
  ghost is revived, and the modules it asks for are put in. `paste` lays the same as ghosts for the
  robots. `remove AREA` destroys everything there (cliffs and enemies too). `decon AREA` orders it
  out. The game still refuses what it refuses in the run (a cliff, an enemy base, a drill off its
  ore), and `place` says how many didn't stand.
- **Playback.** `play SCRIPT` runs `from`, `speed`, `at T` / `at +N`, `run`, `place`, `paste`,
  `remove`, `decon` and `save` lines in order, printing each with its tick.
- **Any game command on it.** `fk sim game stats | look | lua ...` points the toolkit's link at the
  planner.
- **Watching.** Every save state is an ordinary save Rory can open in his own game.
  `start --spectate` puts the server on port 34199, listed on the LAN, starts it at speed 1, and
  `start` / `status` print the address to join (`192.168.1.31:34199` on this laptop). A joining
  client simulates every tick too: speed 1 to 3 while someone watches; at 100 the client falls behind
  and is dropped.

Checked on the laptop with the starterbus run's final save as the start. Two runs of the same minute
from the same state gave the same game: tick 8280187, 251332 iron plates, 98736 copper plates,
50100 gears and 124303 entities, both times. Two plays of the same script, which removed ground,
placed a furnace line free, ran, saved and ran, also matched entity for entity (124494). An
electric-furnace row placed on water built all 60 of its entities with its 12 modules (its 4 drills
off ore didn't stand, as in the game). On ground with cliffs and an enemy base, the game refused
part of it and the report said so.

## `agent/prompts/opus-v1.md`

The brief for a Claude (Opus 5.5) player that Rory talks with: the whole project is open to it (the
runs before, their notes and friction, the design record, the toolkit's source, read-only; DeepSeek's
reasoning stays closed), the cells and the auto counts, and the planner. It has no goal loop or
hand-over: Rory drives the conversation.

## Tests

`tests/test_sim.py` (4): the playback script and its refusals (a Windows path keeps its
backslashes), the planner's folder, the Lua.
