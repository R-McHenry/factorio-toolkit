#!/bin/bash
# kickoff-v1.sh: the V1 kickoff, host side (computah-ct, as root): a fresh world-3 map from the
# fk-play scenario, the starter world, the plant, then a saved map the service keeps running.
#
#   kickoff-v1.sh SHA RUN [--dry] [--pack PACK] [--instance sb]
#     SHA  the v5 toolkit of the run, deployed at /home/computah/factorio/fk-v5-SHA (git archive)
#     RUN  the run's name (<yyyymmdd-HHMM>-<prompt>): its game codebase is v1-runs/RUN/game
#     --dry  print every step, change nothing
#     --pack seablock  a mod pack (2026-11-01): setup_v1.py --pack (its kit: landfill, early
#            roboport and robots, no plant), the game codebase gets kickoff/template-PACK over
#            the template, and there is no plant to wait for. The server must already run the
#            pack's mods: factorio.service does not (see SEABLOCK.md for what it would take).
#     --instance sb  the Sea Block test server instead of factorio.service: /home/computah/sb
#            (its own write dir and mods, game port 34198, RCON 27016, start.sh). Steps 1-3 and 6
#            become: save and stop it, start a new map from fk-play there (its own scenarios
#            dir, default map-gen: Sea Block's sea), save it as sb/saves/v1-RUN.zip and make
#            start.sh start that save (sb/current-map). No join password (nobody else joins it).
#            The game codebase gets link.json, so fk on the host reaches this server.
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
#      start), and again at the end with the setup in it, which is also kept as
#      v1-RUN-start.zip: the run's start, for the speedrun planner (fk sim fetch).
#   7. joins open again.
# Unchanged: the unit file, rcon.pw, the shelved world (instance/saves/world.zip and its copies),
# the test map's save (server/factorio/saves/lab-test.zip), the v4 kickoff (kickoff.sh).
# Way back: the test map = lab.conf back from _retired in place of v1.conf; the shelved world = no
# drop-in at all (the unit starts instance/saves/world.zip). Then daemon-reload and restart.
set -euo pipefail
SHA=${1:?toolkit sha}
RUN=${2:?run name}
shift 2
DRY="" PACK="" INST=live
while [ $# -gt 0 ]; do
  case $1 in
    --dry) DRY=--dry ;;
    --pack) PACK=${2:?pack name}; shift ;;
    --instance) INST=${2:?instance}; shift ;;
    *) echo "kickoff-v1: unknown argument $1"; exit 2 ;;
  esac
  shift
done
case $INST in live|sb) ;; *) echo "kickoff-v1: --instance live or sb"; exit 2 ;; esac
F=/home/computah/factorio
K=$F/kickoff
I=$F/instance
TK=$F/fk-v5-$SHA
G=$F/v1-runs/$RUN/game
D=/etc/systemd/system/factorio.service.d
SAVE=$F/server/factorio/saves/v1-$RUN.zip
BIN=$F/server/factorio/bin/x64/factorio
AS="env FK_RCON_PW_FILE=$I/rcon.pw"
SB=/home/computah/sb
if [ $INST = sb ]; then
  SAVE=$SB/saves/v1-$RUN.zip
  AS="env FK_RCON_PORT=27016 FK_RCON_PW_FILE=$SB/rcon.pw FK_SCRIPT_OUTPUT=$SB/script-output"
fi
SETUP="$TK/kickoff/setup_v1.py${PACK:+ --pack $PACK}"
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

up_wait() {   # $1 = what to say when the server does not answer within 40 s
  [ "$DRY" = "--dry" ] && return 0
  SECONDS=0
  until su computah -c "$AS timeout 4 python3 $SETUP --dry" > /dev/null 2>&1; do
    [ $SECONDS -lt 40 ] || { say "$1"; exit 1; }
    sleep 1
  done
}
sb_stop() {   # the Sea Block test server: stop it and wait until it is gone
  run "pkill -u computah -f -- '[-]-port 34198' || true"
  [ "$DRY" = "--dry" ] && return 0
  for _ in $(seq 1 20); do pgrep -u computah -f -- '[-]-port 34198' > /dev/null || return 0; sleep 1; done
  say "the Sea Block test server did not stop"; exit 1
}
sb_start() {  # start.sh in the background: it starts what sb/current-map names
  run "su computah -c 'cd $SB && setsid sh start.sh > /dev/null 2>&1 < /dev/null &'"
}

if [ $INST = live ]; then
say "1. the running map saved under a known name (before-v1-$stamp), its autosaves kept; stop"
# a process started from a scenario saves itself under the scenario's name (fk-play.zip), not the
# save its drop-in names: the 2026-10-20 kickoff found the test map's last state only there
run su computah -c "'$AS timeout 10 python3 $TK/kickoff/save_map.py before-v1-$stamp'" || say "   (no answer: nothing to save)"
run mkdir -p "$OLD/autosaves"
run cp -p $F/server/factorio/saves/_autosave*.zip "$OLD/autosaves/" 2>/dev/null || true
[ "$DRY" = "--dry" ] || sleep 3
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
up_wait "the server did not answer RCON within 40 s"
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
say "   the new map pinned: saved, v1.conf starts the save, and the server restarts from it (so"
say "   its exits and autosaves go to that save, not to the scenario's name)"
pin
run systemctl restart factorio
up_wait "the server did not come back within 40 s"
else
say "1. the Sea Block test server: its map saved (before-v1-$stamp), then stopped"
run su computah -c "'$AS timeout 10 python3 $TK/kickoff/save_map.py before-v1-$stamp'" || say "   (no answer: nothing to save)"
[ "$DRY" = "--dry" ] || sleep 3
sb_stop
say "2. a new map from fk-play there (sb/scenarios/fk-play from $TK; Sea Block's own map-gen)"
run mkdir -p $SB/_retired
[ -d $SB/scenarios/fk-play ] && run mv $SB/scenarios/fk-play "$SB/_retired/scenario-fk-play-$stamp"
run mkdir -p $SB/scenarios
run cp -r $TK/scenario/fk-play $SB/scenarios/fk-play
[ -f $SB/current-map ] && run cp -p $SB/current-map "$SB/_retired/current-map-$stamp"
run "echo '--start-server-load-scenario fk-play' > $SB/current-map"
run chown -R computah:computah $SB/scenarios $SB/current-map
say "3. no join password: nobody else joins the test server"
sb_start
up_wait "the Sea Block test server did not answer RCON within 40 s"
pin() {    # save the running map and make start.sh start that save from now on (no restart)
  run su computah -c "'$AS timeout 10 python3 $TK/kickoff/save_map.py v1-$RUN'"
  if [ "$DRY" = "--dry" ]; then
    echo "  would write $SB/current-map to start $SAVE"
  else
    for _ in $(seq 1 30); do [ -f "$SAVE" ] && break; sleep 1; done
    [ -f "$SAVE" ] || { say "no save at $SAVE"; exit 1; }
    echo "--start-server $SAVE" > $SB/current-map
    chown computah:computah $SB/current-map
  fi
}
say "   the new map pinned: saved, start.sh starts the save, and the server restarts from it"
pin
sb_stop
sb_start
up_wait "the Sea Block test server did not come back within 40 s"
fi
say "4. the starter world: bootstrap, kit, rules${PACK:+ (pack $PACK)}"
run su computah -c "'$AS timeout 20 python3 $SETUP'"
say "5. the run's game codebase $G, the bare ground${PACK:-, the plant}"
run mkdir -p $(dirname $G)
run cp -r $TK/kickoff/template/game $G
if [ -n "$PACK" ]; then   # the pack's overlay: its game files over the template's, minus DROP
  run cp -r $TK/kickoff/template-$PACK/game/. $G/
  for f in $(cat $TK/kickoff/template-$PACK/DROP); do run rm -f $G/$f; done
fi
if [ $INST = sb ]; then   # fkcore.link reads it: fk on the host reaches this server, not 27015
  run "printf '{\"port\": 27016, \"pw_file\": \"%s\", \"script_output\": \"%s\"}\n' $SB/rcon.pw $SB/script-output > $G/link.json"
fi
run chown -R computah:computah $F/v1-runs/$RUN
run su computah -c "'cd $G && FK_LINK=on PYTHONPATH=$TK $AS timeout 60 python3 -m fkcore read-terrain . --surface nauvis --area=-192,-192,192,192 --name map'"
run su computah -c "'cd $G && FK_LINK=on PYTHONPATH=$TK $AS timeout 120 python3 -m fkcore build nauvis.build.fkb'"
if [ -z "$PACK" ]; then
  run su computah -c "'cd $G && PYTHONPATH=$TK $AS timeout 300 python3 $TK/kickoff/wait_built.py nauvis -36,-41,24,24 240'" \
    || say "   the plant is not finished yet: the robots keep building it"
fi
say "6. save the map again as $SAVE, with the setup in it; a copy kept as the run's start"
pin
# 2.0.61: the speedrun planner (fk sim fetch) starts from this copy: the map as it stood at the
# kickoff, which the live save leaves behind as soon as the game moves on
run cp -p "$SAVE" "${SAVE%.zip}-start.zip"
if [ $INST = live ]; then
  say "7. joins open (on exit); done: the map runs, the run's game codebase is $G"
else
  say "7. done: the Sea Block test server runs $SAVE, the run's game codebase is $G"
fi
