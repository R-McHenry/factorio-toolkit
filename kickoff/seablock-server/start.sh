#!/bin/sh
# Sea Block test server: game port 34198, rcon 127.0.0.1:27016 (password in rcon.pw). Log: server.log
# It starts what current-map names (kickoff-v1.sh --instance sb writes it: a scenario to make a new
# map from, then the run's save), else the test map saves/sb-test.zip.
cd /home/computah/sb
[ -f rcon.pw ] || head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n' > rcon.pw
F=/home/computah/factorio/server/factorio/bin/x64/factorio
MAP=$(cat current-map 2>/dev/null || echo "--start-server saves/sb-test.zip")
exec setsid $F -c config/config.ini --mod-directory mods $MAP \
  --port 34198 --rcon-bind 127.0.0.1:27016 --rcon-password "$(cat rcon.pw)" \
  --server-settings server-settings.json > server.log 2>&1 < /dev/null
