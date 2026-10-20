"""rehearse_perception: the first V1 run's blind spot, on a laptop world (nothing on the server).

    python tools/rehearse_perception.py

A fresh world-3 map from fk-play with the kit and the starter rules (as a run starts), the plant
built, then the example factories smelting.fk and red.fk placed near spawn: they need items the
kit lacks (electric drills, more belts) and recipes nobody researched. What the agent's own fk
must now say: the build's STOCK line with LOW_STOCK and LOCKED, GHOST SHORT / GHOST LOCKED in a
look, the grouped no-material alerts with what the network holds, RESEARCH: NONE in every
footer, and fk research / tech / recipes. The output is printed and kept in
out/rehearse-perception.txt.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from tools.laptop_server import LaptopServer  # noqa: E402
from kickoff import new_run, setup_v1  # noqa: E402

MAPGEN = os.path.join(os.path.dirname(ROOT), "v4-hand", "kickoff", "map-gen-w3.json")
RUN = os.path.join(ROOT, "out", "perception-run")
OUT = []


def fk(*args, timeout=240):
    p = subprocess.run([sys.executable, os.path.join(RUN, "bin", "fk.py")] + list(args),
                       env=dict(os.environ, FK_RUN=RUN), stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, timeout=timeout)
    OUT.append(f"$ fk {' '.join(args)}   (exit {p.returncode})\n{p.stdout}")
    print(f"$ fk {' '.join(args)}   (exit {p.returncode})")
    return p.stdout


def main():
    shutil.rmtree(RUN, ignore_errors=True)
    with LaptopServer("perception", scenario="fk-play", map_gen=MAPGEN, boot_s=120) as srv:
        env = {"FK_RCON_PORT": str(srv.rcon_port), "FK_RCON_PW_FILE": srv.pw_file,
               "FK_SCRIPT_OUTPUT": os.path.join(srv.write, "script-output")}
        with srv.rcon() as r:
            setup_v1.run(r)
        new_run.make(RUN, local=env, player="claude")
        fk("build")
        game = os.path.join(RUN, "game")
        for name in ("smelting.fk", "red.fk"):
            shutil.copy(os.path.join(ROOT, "agent", "docs", "examples", name), os.path.join(game, name))
        with open(os.path.join(game, "nauvis.surface"), "a", encoding="utf-8") as fh:
            fh.write("\nplace smelting = smelting plot 30,-40 26x26\nplace red = red plot 60,-40 30x30\n")
        text = fk("build")
        with open(os.path.join(game, "out", "report_bom.txt"), encoding="utf-8") as fh:
            OUT.append("== out/report_bom.txt\n" + fh.read())
        time.sleep(20)                         # the robots take what the network holds
        fk("look", "28,-42,92,-8")
        fk("alerts")
        fk("research")
        fk("tech", "electric-mining-drill", "automation-science-pack", "assembling-machine-1")
        fk("recipes", "assembling-machine-1", "electric-mining-drill", "lab", "transport-belt")
        fk("research", "automation")
    with open(os.path.join(ROOT, "out", "rehearse-perception.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(OUT))
    print("\n".join(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
