"""wait_built: wait until an area has no ghosts left (robots built them): 5 s check-ins.

    python3 kickoff/wait_built.py SURFACE X0,Y0,X1,Y1 [LIMIT_S]

A future factory state, so a longer wait in short check-ins (CLAUDE.md); every check is one RCON
call with the link's 5 s timeout. Exit 0 when none are left, 1 when some are after LIMIT_S.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fkcore import link  # noqa: E402


def main(argv):
    surface, area = argv[0], [int(v) for v in argv[1].split(",")]
    limit = float(argv[2]) if len(argv) > 2 else 240.0
    x0, y0, x1, y1 = area
    lua = (f"rcon.print(game.get_surface('{surface}').count_entities_filtered{{area = "
           f"{{{{{x0},{y0}}},{{{x1},{y1}}}}}, type = 'entity-ghost'}})")
    t0 = time.time()
    with link.Rcon() as r:
        left = int(r.lua(lua).strip())
        while left and time.time() - t0 < limit:
            time.sleep(5)
            left = int(r.lua(lua).strip())
    print(f"wait_built: {left} ghosts left in {argv[1]} after {round(time.time() - t0)} s")
    return 0 if left == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
