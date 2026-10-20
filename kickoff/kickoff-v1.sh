#!/bin/bash
# kickoff-v1.sh: the V1 kickoff, host side (computah-ct, as root): a fresh world-3 map from the
# fk-play scenario, the starter world, the plant, then a saved map the service keeps running.
#
#   kickoff-v1.sh SHA RUN [--dry]
#     SHA  the v5 toolkit of the run, deployed at /home/computah/factorio/fk-v5-SHA (git archive)
#     RUN  the run's name (<yyyymmdd-HHMM>-<prompt>): its game codebase is v1-runs/RUN/game
#     --dry  print every step, change nothing
#
# What it changes, in order (nothing is deleted; every replaced file goes to _retired/):
#   1. factorio.service stops (the running map saves itself on the way out, as always).
#   2. the drop-in factorio.service.d/lab.conf (the test map) moves to _retired/; a drop-in
#      v1.conf starts a NEW map from the fk-play scenario with the kickoff's world-3 map-gen
#      settings; the scenario dir gets this toolkit's scenario/fk-play (the lab, /lab, fk_chat).
#   3. joins closed (a one-off join password) until the setup is done, as kickoff.sh does.
#   4. setup_v1.py: bootstrap, kit, starter rules (players become spectators, no crash site).
#   5. the run's game codebase in v1-runs/RUN/game (the toolkit's template), the start area's
#      bare ground read into it (read-terrain), and its first build: the plant and its pole chain
#      pasted as ghosts, built by robots from the kit (5 s check-ins, at most 4 min).
#   6. the map saved as server/factorio/saves/v1-RUN.zip, and v1.conf rewritten to start that
#      save (no restart): a later restart resumes this map. This is done twice: right after the
#      new map answers (so no later failure leaves the service making a new map on every
#      start), and again at the end with the setup in it.
#   7. joins open again.
# Unchanged: the unit file, rcon.pw, the shelved world (instance/saves/world.zip and its copies),
# the test map's save (server/factorio/saves/lab-test.zip), the v4 kickoff (kickoff.sh).
# Way back: the test map = lab.conf back from _retired in place of v1.conf; the shelved world = no
# drop-in at all (the unit starts instance/saves/world.zip). Then daemon-reload and restart.
set -euo pipefail
SHA=${1:?toolkit sha}
RUN=${2:?run name}
DRY=${3:-}
F=/home/computah/factorio
K=$F/kickoff
I=$F/instance
TK=$F/fk-v5-$SHA
G=$F/v1-runs/$RUN/game
D=/etc/systemd/system/factorio.service.d
SAVE=$F/server/factorio/saves/v1-$RUN.zip
BIN=$F/server/factorio/bin/x64/factorio
AS="env FK_RCON_PW_FILE=$I/rcon.pw"
stamp=$(date -u +%Y%m%d-%H%M)
OLD=$F/_retired/v1-kickoff-$stamp

run() { if [ "$DRY" = "--dry" ]; then echo "  would: $*"; else eval "$@"; fi; }
say() { echo "kickoff-v1: $*"; }

[ -d "$TK/fkcore" ] || { say "no toolkit at $TK (deploy v5 at $SHA first)"; exit 1; }
[ -e "$G" ] && { say "$G exists: one run, one game codebase"; exit 1; }
conf() {   # $1 = the factorio arguments that pick the map
  cat <<EOF
# v1.conf: the V1 run $RUN (kickoff-v1.sh, $stamp). Way back: see kickoff-v1.sh's header.
[Service]
ExecStart=
ExecStart=/bin/bash -c '$BIN \\
  $1 \\
  --server-settings server-settings.json \\
  --rcon-bind 127.0.0.1:27015 \\
  --rcon-password "\$(cat $I/rcon.pw)" \\
  --server-id $I/server-id.json'
EOF
}

say "1. stop the server (the running map saves itself)"
run systemctl stop factorio
say "2. drop-ins: lab.conf -> $OLD/, v1.conf: a new map from fk-play; the scenario from $TK"
run mkdir -p "$OLD"
[ -f $D/lab.conf ] && run mv $D/lab.conf "$OLD/lab.conf"
[ -f $D/v1.conf ] && run mv $D/v1.conf "$OLD/v1.conf.before"
if [ "$DRY" = "--dry" ]; then
  echo "  would write $D/v1.conf:"; conf "--start-server-load-scenario fk-play --map-gen-settings $K/map-gen-w3.json --map-settings $I/map-settings.json" | sed 's/^/    /'
else
  conf "--start-server-load-scenario fk-play --map-gen-settings $K/map-gen-w3.json --map-settings $I/map-settings.json" > $D/v1.conf
fi
[ -d $F/server/factorio/scenarios/fk-play ] && run mv $F/server/factorio/scenarios/fk-play "$OLD/scenario-fk-play"
run cp -r $TK/scenario/fk-play $F/server/factorio/scenarios/fk-play
run chown -R computah:computah $F/server/factorio/scenarios/fk-play
say "3. joins closed until the setup is done"
run python3 $K/joins.py close-file
[ "$DRY" = "--dry" ] || trap 'python3 $K/joins.py restore-file; su computah -c "$AS timeout 8 python3 $K/joins.py open" || true' EXIT
run systemctl daemon-reload
run systemctl start factorio
if [ "$DRY" != "--dry" ]; then
  up=""; SECONDS=0
  while [ $SECONDS -lt 40 ]; do
    if t=$(su computah -c "$AS timeout 4 python3 $TK/kickoff/setup_v1.py --dry" 2>/dev/null); then up=1; break; fi
    sleep 1
  done
  [ -n "$up" ] || { say "the server did not answer RCON within 40 s"; exit 1; }
fi
run python3 $K/joins.py restore-file
pin() {    # save the running map and make v1.conf start that save from now on (no restart)
  run su computah -c "'$AS timeout 10 python3 $TK/kickoff/save_map.py v1-$RUN'"
  if [ "$DRY" = "--dry" ]; then
    echo "  would rewrite $D/v1.conf to start $SAVE"
  else
    for _ in $(seq 1 30); do [ -f "$SAVE" ] && break; sleep 1; done
    [ -f "$SAVE" ] || { say "no save at $SAVE"; exit 1; }
    conf "--start-server $SAVE" > $D/v1.conf
    systemctl daemon-reload
  fi
}
say "   the new map pinned: saved, and v1.conf starts the save"
pin
say "4. the starter world: bootstrap, kit, rules"
run su computah -c "'$AS timeout 20 python3 $TK/kickoff/setup_v1.py'"
say "5. the run's game codebase $G, the bare ground, the plant"
run mkdir -p $(dirname $G)
run cp -r $TK/kickoff/template/game $G
run chown -R computah:computah $F/v1-runs/$RUN
run su computah -c "'cd $G && FK_LINK=on PYTHONPATH=$TK $AS timeout 60 python3 -m fkcore read-terrain . --surface nauvis --area=-192,-192,192,192 --name map'"
run su computah -c "'cd $G && FK_LINK=on PYTHONPATH=$TK $AS timeout 120 python3 -m fkcore build nauvis.build.fkb'"
run su computah -c "'cd $G && PYTHONPATH=$TK $AS timeout 300 python3 $TK/kickoff/wait_built.py nauvis -36,-41,24,24 240'" \
  || say "   the plant is not finished yet: the robots keep building it"
say "6. save the map again as $SAVE, with the setup in it"
pin
say "7. joins open (on exit); done: the map runs, the run's game codebase is $G"
