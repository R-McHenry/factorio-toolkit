"""save_map: save the running map under a name (server/factorio/saves/NAME.zip), one RCON call.

    python3 kickoff/save_map.py NAME

``game.server_save`` is the server's own save; nothing is registered.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fkcore import link  # noqa: E402


def main(argv):
    name = argv[0]
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise SystemExit(f"save_map: a plain file name, got {name!r}")
    with link.Rcon() as r:
        print(r.lua(f"game.server_save('{name}') rcon.print('saving {name}')").strip())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
