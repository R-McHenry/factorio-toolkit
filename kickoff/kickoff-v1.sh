#!/bin/bash
# kickoff-v1.sh: the V1 kickoff, host side (computah-ct, as root). A DRAFT in v5: it is not on the
# host and does not run until Rory says go (it changes what factorio.service starts).
#
# What changes from v4-hand/kickoff/kickoff.sh:
#   - the map comes from the fk-play scenario (--start-server-load-scenario fk-play) with the same
#     map-gen settings, so the lab surface, /lab and the chat journal are in the map's own script;
#   - setup_v1.py: bootstrap, kit and rules; no chat handler through RCON (v4's setup.py installs
#     one with script.on_event, the pattern that made saves unjoinable on 2026-10-18) and no plant
#     paste (the plant is a factory of the run's game codebase; the run's first fk build pastes it);
#   - the run's toolkit is deployed as its own versioned dir, fk-v5-<sha>, never over another.
#
#   sudo kickoff-v1.sh <toolkit sha> <run name>
set -euo pipefail
SHA=${1:?toolkit sha}
RUN=${2:?run name}
F=/home/computah/factorio
K=$F/kickoff
I=$F/instance
TK=$F/fk-v5-$SHA
AS="env FK_RCON_PW_FILE=$I/rcon.pw"
stamp=$(date -u +%Y%m%d-%H%M)
OLD="$F/_retired/world-before-kickoff-$stamp"

[ -d "$TK" ] || { echo "kickoff-v1: no toolkit at $TK (deploy v5 at $SHA first)"; exit 1; }
systemctl stop factorio
mkdir -p "$OLD"
[ -f $I/saves/world.zip ] && mv $I/saves/world.zip "$OLD/world.zip"
echo "kickoff-v1: old world -> $OLD"

# the scenario into the server's scenarios/, the map made from it; the first start creates it and
# saves world.zip, which every later start loads (the unit's own ExecStart)
rm -rf $F/server/factorio/scenarios/fk-play
cp -r $TK/scenario/fk-play $F/server/factorio/scenarios/fk-play
chown -R computah:computah $F/server/factorio/scenarios/fk-play
python3 $K/joins.py close-file
trap 'python3 $K/joins.py restore-file; su computah -c "$AS timeout 8 python3 $K/joins.py open" || true' EXIT
su computah -c "cd $I && timeout 60 $F/server/factorio/bin/x64/factorio \
  --start-server-load-scenario fk-play --map-gen-settings $K/map-gen-w3.json \
  --map-settings $I/map-settings.json --mod-directory $F/server/factorio/mods \
  --until-tick 1 --server-settings server-settings.json" | tail -3 || true
# (the step above needs checking: --until-tick is a benchmark flag; the parent session's lab map
#  was made by a drop-in ExecStart with --start-server-load-scenario and then saved by RCON)
systemctl start factorio

up=""
SECONDS=0
while [ $SECONDS -lt 30 ]; do
  if t=$(su computah -c "$AS timeout 3 python3 $TK/kickoff/setup_v1.py --dry" 2>/dev/null); then up=$t; break; fi
  sleep 1
done
[ -n "$up" ] || { echo "kickoff-v1: the server did not answer RCON within 30 s"; exit 1; }
python3 $K/joins.py restore-file
su computah -c "$AS timeout 20 python3 $TK/kickoff/setup_v1.py"
# the bare ground of the start area into the run's terrain file: read-terrain (worker terrain), then
# the run's game codebase on the host: /home/computah/factorio/v1-runs/$RUN/game (new_run.py on
# the laptop makes the run folder; its first fk command pulls this copy)
mkdir -p $F/v1-runs/$RUN && chown computah:computah $F/v1-runs/$RUN
echo "kickoff-v1: map up, kit and rules set; next on the laptop: new_run.py, then fk build"
