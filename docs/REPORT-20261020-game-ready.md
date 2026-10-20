# The toolkit, game-ready for an agent (2026-10-20)

Rory's goal, through the supervising session: the toolkit game-ready for an agent, tested in the
server's lab where he can watch, laptop worlds only where the lab can't give it. Done on v5 `main`
(299 tests): four workers in their own worktrees (sense, terrain, fluids, router), merged, and the
lead's own pieces (the shared apply, the agent kit, robot coverage, measure, the rehearsals). Nothing
is wired into `C:\fk-player` or the host's kickoff yet: that waits for Rory's go.

## In the game: the lab surface of the test map

Every lab game, diffed with the merged toolkit (`main` e61ddb9), is 1:1:

| game | where (lab) | what | diff |
|---|---|---|---|
| lab-merge | 200,400 | iron + gears, lab rules; Rory's power adopted | OK 122 |
| lab-play | 200..250, 590..645 | gears + red science, **play rules**: ghosts built by robots from a kit | OK 134 |
| lab-sense | 310,420 | the live look, notify, alerts (worker sense) | OK 120 |
| lab-terrain | 460..700, 400..640 | a real iron patch, pond and cliffs transplanted from nauvis (worker terrain) | OK 386 |
| lab-fluids | 740..860, 400..560 | water -> boilers -> engines, sulfur (worker fluids) | OK 49 |
| lab-kxm | 880..1010, 400..640 | a 3 -> 2 sushi net through a hub (worker router) | OK 55, MARKED 1 |
| lab-redgreen | 200,200 | the bench's red-green build; Rory's power kept as his mark | OK 1014, MARKED 1 |

Measured against the nominal model (`fk measure`, fair play: the area only):
- red science 15.96/min against 18.00 (0.89) on lab-play;
- sulfur 1.971/s against 2.0 at full speed (0.986) on lab-fluids;
- gears 2.0-2.3x the model: the model caps a requester at its declared `rate`, the robots deliver more.

## In the game: a V1 run, rehearsed on a laptop world

`tools/rehearse_v1.py`: a fresh world-3 map from the fk-play scenario on a laptop test server, the
kickoff's `setup_v1.py`, a run folder from `new_run.py`, then only the agent's own `fk`:
- setup: bootstrap 16/16, kit 6 chests with nothing short, 50 + 50 robots, speed 1 / cargo 1;
- `fk read-terrain`: 256x256 at spawn, 2262 water tiles, the patches;
- `fk build`: the plant and its pole chain as ghosts, built by robots in 15 s; the live look OK
  29/29; the reactor fed by its own requester (19 cells delivered, 2 in the reactor, 117 C after 45 s);
- the example gears factory placed outside the kit's logistic square: `cover robots` gave it a
  roboport, the requester asks for iron-plate:75 in a network, robots built it in 20 s, the look
  OK 34/34; the first gears after 75 s (the early grid is solar), 27 in the next 30 s, `fk measure`
  77.96/min against the model's 37.50; Rory's chat line shows at the end of the next command.

The four rehearsals before it found what the paper could not, all fixed: requesters asked for
nothing; the blueprint paste refuses the offshore pump; robots flying through a look read as
MARKED; a chest outside the robot network was never served.

## What is built (CORE-V1 categories)

1. **In-game validation**: link, apply 1:1, look parity, watcher, adopt, measure (this morning's
   bench), and now every flow game above.
2. **Sensing**: `look --source world` (fair play: the area), notify nearby/all/off, the alert panel
   pushed with reminders (`remind <duration>`; 2 alerts new, reminded at 20 s, cleared 11 s after
   their causes went), the free reads `stats` and `chart`, never turned into alerts.
3. **The lab scenario**: the test map runs it; Rory uses `/lab`. The chat journal is now scenario
   code too (`fk_chat.lua`, checked on a laptop server).
4. **Terrain**: `read-terrain` from a live map (nauvis 576x576: water 2906, iron 2 patches, ...),
   `@patch` for MinerRow (6/6 drills on ore), the terrain as an obstacle for routes, poles and
   bridges (`ON_TERRAIN`, `OFF_ORE`).
5. **The agent side** (drafts in v5): the brief `agent/prompts/core-v1.md`, TOOLKIT, LANGUAGE,
   EXAMPLES; `fk`, the one command; the run template, `new_run.py`, `setup_v1.py`, `kickoff-v1.sh`
   (`docs/AGENT-KIT.md`).
6. **Fluids**: pipes and pipe-to-ground as the router's plug-in, fluid boxes read from the game
   (60 live entities checked), pipe tracing and fluid LEAKs.
7. **Router gaps**: k->m nets through a hub (spm10's iron 1->26 connects 608/608, the mall 20->1),
   the underground guard (14 adversarial cases, 13 of which the old router failed).

Also new: `cover robots` and `NO_ROBOTS`; `fkcore.apply` (the only world write) with its lab and
play rules; `measure`; the CLI of adopt, merge, insert, chests-to-net, net-to-chests.

## Rory's edits

He powered the lab builds with the editor: three energy interfaces. The two at lab-merge are its
infra now (`rory/e0`, `rory/e1`), the one at the red-green build is his mark (it straddles the
plot edge). The lab tools' area clear skips anything a player placed, so no test removes them.

## Findings

- v4's live kickoff (`v4-hand/kickoff/setup.py`) still installs the chat handler over RCON
  (`script.on_event`), the pattern behind the 10-18 unjoinable saves. `setup_v1.py` does not; the
  scenario keeps the journal.
- The game expires its own alerts in 10-30 s, so with a 10 min reminder only lasting conditions
  (a speaker, missing materials) ever get one.
- Entities placed through RCON have no last_user: a mark of them names `unknown`.
- `literal.read_entities` drops a blueprint's underground type, so a Literal's tunnels can't be
  paired (the plant has none).
- Rotated plots: a factory frame that grows when routed shifts; no game uses rotated plots yet.
- `ChemPlant<n=2>` places one plant; a machine to a machine (a chem plant into a chest) isn't routed.
- v4's `stamps/steam_power.py` puts a boiler's east water connection on the wrong row (the game
  has both on the south row).

## Open for Rory

- The go to wire the kit into `C:\fk-player` (template, prompt) and the host's kickoff
  (`kickoff-v1.sh` starts the map from the fk-play scenario, which changes what the service runs).
- Where V1 runs happen: a fresh map per run, and what becomes of the test map.
- The reminder cadence (10 min in the drafts) and `watch sanctioned: mark` (now 2 h by default).
- The offline-player alert test: `python3 tools/lab_sense.py --steps alerts --force player`
  while Rory is offline and on the player force.
