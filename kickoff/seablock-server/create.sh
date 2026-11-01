#!/bin/sh
# Sea Block test instance: same binary as the live server, own write dir, mods and ports.
# usage: create.sh  -> mods/mod-list.json, then saves/sb-test.zip (log in create.log)
cd /home/computah/sb
F=/home/computah/factorio/server/factorio/bin/x64/factorio
python3 - <<'EOF'
import json, os
mods = [{"name": "base", "enabled": True}]
mods += [{"name": n, "enabled": False} for n in ("elevated-rails", "quality", "space-age")]
for d in sorted(os.listdir("mods")):
    if os.path.isdir("mods/" + d):
        mods.append({"name": d.rsplit("_", 1)[0], "enabled": True})
json.dump({"mods": mods}, open("mods/mod-list.json", "w"), indent=1)
EOF
rm -f saves/sb-test.zip
exec $F -c config/config.ini --mod-directory mods --create saves/sb-test.zip > create.log 2>&1
