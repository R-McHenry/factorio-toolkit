#!/bin/bash
# setup-commons.sh: the shared save and its gateway, host side (computah-ct, as root). Run once.
#
#   setup-commons.sh SHA [--dry]
#     SHA  the v5 toolkit, deployed at /home/computah/factorio/fk-v5-SHA (git archive)
#
# What it makes (it touches no other server: its own instance folder, ports and units):
#   /home/computah/commons/instance   the server's write-data: saves, script-output, mods (base
#                                     game only), rcon.pw; game UDP 34201, RCON 127.0.0.1:27121
#   /home/computah/commons/host-run   the host's own game codebase (the single-player template):
#                                     its one build lays the reactor and its pole line, the shared
#                                     start's furniture, as kickoff-v1.sh does
#   /home/computah/commons/gateway    gateway.json, docs/ (skill.md, heartbeat.md), data/
#   /home/computah/commons/toolkit    a link to toolkit-SHA beside it, fkcore at SHA (a later
#                                     toolkit: copy it in, move the link, restart fk-gateway)
#   fk-commons.service, fk-gateway.service, fk-commons-restart.path + .service (the gateway's
#   watchdog asks for a restart by writing gateway/data/restart/commons; it has no sudo)
# Steps: 1. the folders and files; 2. a new map from the fk-play scenario with the kickoff's
# world-3 map-gen, started by hand; 3. setup_v1.py (bootstrap, kit, rules); 4. the host run's
# first build (the plant), robots build it; 5. saved as commons.zip, the hand-started server
# stopped; 6. the units enabled and started.
set -euo pipefail
SHA=${1:?toolkit sha}
DRY=${2:-}
F=/home/computah/factorio
C=/home/computah/commons
I=$C/instance
TK=$F/fk-v5-$SHA
K=$TK/kickoff/commons
BIN=$F/2.1.24/bin/x64/factorio
AS="env FK_RCON_PORT=27121 FK_RCON_PW_FILE=$I/rcon.pw FK_SCRIPT_OUTPUT=$I/script-output"

run() { if [ "$DRY" = "--dry" ]; then echo "  would: $*"; else eval "$@"; fi; }
say() { echo "setup-commons: $*"; }

[ -d "$TK/fkcore" ] || { say "no toolkit at $TK (deploy v5 at $SHA first)"; exit 1; }
[ -x "$BIN" ] || { say "no Factorio at $BIN"; exit 1; }
[ -e "$I/saves" ] && { say "$I/saves exists: the commons is already set up"; exit 1; }

say "1. folders, config, settings, mods (base only), the scenario, the gateway's files"
run mkdir -p $I/saves $I/mods $I/scenarios $I/script-output $C/gateway/docs $C/gateway/data/restart $C/toolkit-$SHA
run cp -r $TK/fkcore $C/toolkit-$SHA/fkcore
run "printf '[path]\nread-data=__PATH__executable__/../../data\nwrite-data=$I\n' > $I/config.ini"
run "[ -f $I/rcon.pw ] || head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n' > $I/rcon.pw"
run chmod 600 $I/rcon.pw
run cp $K/server-settings.json $I/server-settings.json
run "[ -f $F/instance-2.1/server-adminlist.json ] && cp $F/instance-2.1/server-adminlist.json $I/server-adminlist.json || echo '[]' > $I/server-adminlist.json"
run "printf '{\"mods\": [{\"name\": \"base\", \"enabled\": true}, {\"name\": \"elevated-rails\", \"enabled\": false}, {\"name\": \"quality\", \"enabled\": false}, {\"name\": \"space-age\", \"enabled\": false}, {\"name\": \"recycler\", \"enabled\": false}]}\n' > $I/mods/mod-list.json"
run cp -r $TK/scenario/fk-play $I/scenarios/fk-play
run cp $K/gateway.json $C/gateway/gateway.json
run cp $K/skill.md $K/heartbeat.md $C/gateway/docs/
run ln -sfn toolkit-$SHA $C/toolkit
run chown -R computah:computah $C

say "2. a new map from fk-play (world-3 map-gen), started by hand"
MAPSET=""
[ -f $F/instance/map-settings.json ] && MAPSET="--map-settings $F/instance/map-settings.json"
run "su computah -c 'cd $I && setsid $BIN -c $I/config.ini --port 34201 --start-server-load-scenario fk-play --map-gen-settings $K/map-gen-w3.json $MAPSET --server-settings $I/server-settings.json --rcon-bind 127.0.0.1:27121 --rcon-password \$(cat $I/rcon.pw) > $I/first-start.log 2>&1 < /dev/null &'"
if [ "$DRY" != "--dry" ]; then
  SECONDS=0
  until su computah -c "$AS timeout 4 python3 $TK/kickoff/setup_v1.py --dry" > /dev/null 2>&1; do
    [ $SECONDS -lt 60 ] || { say "the server did not answer RCON within 60 s: $I/first-start.log"; exit 1; }
    sleep 1
  done
fi

say "3. the starter world: bootstrap, kit, rules"
run "su computah -c '$AS timeout 20 python3 $TK/kickoff/setup_v1.py'"

say "4. the host run: the reactor and its pole line as ghosts, robots build them (up to 5 min)"
G=$C/host-run/game
run mkdir -p $C/host-run
run cp -r $TK/kickoff/template/game $G
run chown -R computah:computah $C/host-run
run "su computah -c 'cd $G && FK_LINK=on PYTHONPATH=$TK $AS timeout 60 python3 -m fkcore read-terrain . --surface nauvis --area=-192,-192,192,192 --name map'"
run "su computah -c 'cd $G && FK_LINK=on PYTHONPATH=$TK $AS timeout 120 python3 -m fkcore build nauvis.build.fkb'"
run "su computah -c 'cd $G && PYTHONPATH=$TK $AS timeout 320 python3 $TK/kickoff/wait_built.py nauvis -36,-41,24,24 300'" \
  || say "   the plant is not finished yet: the robots keep building it"

say "5. saved as commons.zip; the hand-started server stopped"
run "su computah -c '$AS timeout 10 python3 $TK/kickoff/save_map.py commons'"
if [ "$DRY" != "--dry" ]; then
  for _ in $(seq 1 30); do [ -f $I/saves/commons.zip ] && break; sleep 1; done
  [ -f $I/saves/commons.zip ] || { say "no $I/saves/commons.zip"; exit 1; }
  sleep 2
  pkill -u computah -f -- '[-]-port 34201' || true
  for _ in $(seq 1 20); do pgrep -u computah -f -- '[-]-port 34201' > /dev/null || break; sleep 1; done
  # a server started from a scenario saves itself under the scenario's name on the way out:
  # the unit loads the newest save, which must be commons.zip
  rm -f $I/saves/fk-play.zip
  touch $I/saves/commons.zip
fi

say "6. the units"
run cp $K/fk-commons.service $K/fk-gateway.service $K/fk-commons-restart.path $K/fk-commons-restart.service /etc/systemd/system/
run systemctl daemon-reload
run systemctl enable --now fk-commons.service fk-commons-restart.path
if [ "$DRY" != "--dry" ]; then
  SECONDS=0
  until su computah -c "$AS timeout 4 python3 $TK/kickoff/setup_v1.py --dry" > /dev/null 2>&1; do
    [ $SECONDS -lt 60 ] || { say "fk-commons did not answer RCON within 60 s"; exit 1; }
    sleep 1
  done
fi
run systemctl enable --now fk-gateway.service
say "done: the gateway listens on 10.77.0.2:8911 (zybo's Caddy publishes it)"
