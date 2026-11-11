"""rehearse_commons: a shared save, its gateway and two outside agents, on a laptop test world.

    python tools/rehearse_commons.py [--no-replica]

1. A fresh map from the fk-play scenario with the kickoff's map-gen (world 3), base game only, on
   a laptop test server (tools/laptop_server.py: killed at the end); kickoff/setup_v1.py; saved.
2. An fk-gateway over it, in this process (fkcore.gateway), registration open.
3. Two agents join with kickoff/join.py (out/rehearsal-commons/ann and bob), each with the run's
   own ``bin/fk.py`` only from there on:
   - ann claims a plot, reads its ground, builds examples/gears.fk on it; the shared robots
     build it; ``fk look``;
   - bob's claim over ann's is refused, the one beside it taken;
   - ann says what she built; bob's next command ends with the board's count; he reads it;
   - a pause is refused; the journal names both; ``fk commons status``;
   - ann's replica: ``fk replica`` pulls the save and starts it paused, ``fk sim game lua`` reads
     it, ``fk sim stop``.
4. Numbers into out/rehearsal-commons.json.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "kickoff"))

from tools.laptop_server import LaptopServer  # noqa: E402
from kickoff import setup_v1  # noqa: E402
from fkcore import gateway  # noqa: E402
import join  # noqa: E402

MAPGEN = os.environ.get("FK_MAPGEN") or os.path.join(os.path.dirname(ROOT), "v4-hand", "kickoff",
                                                     "map-gen-w3.json")
BASE = os.path.join(ROOT, "out", "rehearsal-commons")
#: inside the kit roboport's construction reach (8,8 +- 55), beside its logistic square
ANN, BOB = (36, -24, 68, 8), (68, -24, 100, 8)
REPORT = {}


def note(step, **kw):
    REPORT.setdefault(step, {}).update(kw)
    print(f"[{step}] " + ", ".join(f"{k}={v}" for k, v in kw.items()), flush=True)


def fk(run, *args, timeout=300):
    t0 = time.time()
    p = subprocess.run([sys.executable, os.path.join(run, "bin", "fk.py")] + list(args),
                       env=dict(os.environ, FK_RUN=run, FK_RCON_TIMEOUT="30"),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    return p.returncode, p.stdout, round(time.time() - t0, 1)


def ghosts(r, area):
    x0, y0, x1, y1 = area
    return int(r.lua(f"rcon.print(game.surfaces.nauvis.count_entities_filtered{{area = "
                     f"{{{{{x0},{y0}}},{{{x1},{y1}}}}}, type = 'entity-ghost'}})").strip())


def built(r, area):
    x0, y0, x1, y1 = area
    return int(r.lua(f"rcon.print(game.surfaces.nauvis.count_entities_filtered{{area = "
                     f"{{{{{x0},{y0}}},{{{x1},{y1}}}}}, force = 'player'}})").strip())


def main(argv):
    shutil.rmtree(BASE, ignore_errors=True)
    os.makedirs(BASE)
    ann, bob = os.path.join(BASE, "ann"), os.path.join(BASE, "bob")
    with LaptopServer("commons", scenario="fk-play", map_gen=MAPGEN, boot_s=120, mods=()) as srv:
        with srv.rcon() as r:
            got = setup_v1.run(r)
            note("setup", bootstrap=got["bootstrap"], kit=got["kit"])
            r.lua("game.server_save('commons') rcon.print('saved')")
            saves = os.path.join(srv.write, "saves")
            t0 = time.time()
            while not os.path.exists(os.path.join(saves, "commons.zip")) and time.time() - t0 < 20:
                time.sleep(0.5)
            gw = gateway.Gateway({
                "listen": ["127.0.0.1", 0], "data": os.path.join(BASE, "gateway"),
                "docs": os.path.join(ROOT, "kickoff", "commons"),
                "saves": {"commons": {
                    "rcon_port": srv.rcon_port, "pw_file": srv.pw_file,
                    "script_output": os.path.join(srv.write, "script-output"), "saves": saves,
                    "factorio": "2.1.24", "mods": ["base"],
                    "about": "survival on real ore, built together"}}})
            host, port = gw.serve(block=False)
            url = f"http://{host}:{port}/v1/saves/commons"
            note("gateway", url=url)
            try:
                rehearse(r, gw, url, ann, bob, "--no-replica" not in argv)
            finally:
                gw.close()
    with open(os.path.join(ROOT, "out", "rehearsal-commons.json"), "w", encoding="utf-8") as fh:
        json.dump(REPORT, fh, indent=1)
    return 0


def rehearse(r, gw, url, ann, bob, replica):
    join.join(url, "ann", ann, contact="the rehearsal")
    join.join(url, "bob", bob, contact="the rehearsal")
    note("join", agents=sorted(gw.keys.agents))

    area = ",".join(str(v) for v in ANN)
    code, text, s = fk(ann, "commons", "claim", "main", area, "gears")
    note("ann claims", exit=code, lines=text.strip().splitlines()[:2])
    code, text, s = fk(bob, "commons", "claim", "main", "60,0,90,30")
    note("bob over ann", exit=code, says=text.strip().splitlines()[-1][:160])
    code, text, s = fk(bob, "commons", "claim", "main", ",".join(str(v) for v in BOB))
    note("bob beside", exit=code)
    code, text, s = fk(ann, "commons", "claims")
    note("claims", lines=text.strip().splitlines()[:3])

    code, text, s = fk(ann, "read-terrain", "--surface", "nauvis", f"--area={area}", "--name",
                       "map", "--replace", "--entities")
    REPORT["terrain_text"] = text
    note("ann terrain", exit=code, seconds=s, last=text.strip().splitlines()[-1][:160] if text.strip() else "")
    shutil.copy(os.path.join(ROOT, "agent", "docs", "examples", "gears.fk"),
                os.path.join(ann, "game", "gears.fk"))
    with open(os.path.join(ann, "game", "world.fk"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write('import Gears from "gears.fk"\n\ngears = Gears @(4, 4)\n')
    code, text, s = fk(ann, "build", "--wait")
    REPORT["build_text"] = text
    try:
        apply_txt = open(os.path.join(ann, "game", "out", "apply.txt"), encoding="utf-8").read()
    except OSError:
        apply_txt = "(no apply.txt)"
    note("ann builds", exit=code, seconds=s, apply=apply_txt.splitlines()[1:3])
    t0, left = time.time(), ghosts(r, ANN)
    while left and time.time() - t0 < 240:
        time.sleep(5)
        left = ghosts(r, ANN)
    note("robots", ghosts_left=left, waited_s=round(time.time() - t0), standing=built(r, ANN))
    code, text, s = fk(ann, "look", area)
    REPORT["look_text"] = text
    note("ann looks", exit=code, first=[ln for ln in text.splitlines() if ln.strip()][:3])

    code, text, s = fk(bob, "stats")                     # the first command starts bob's count
    code, text, s = fk(ann, "say", "gears at 40,-20: two assemblers, plates in by robots")
    note("ann says", exit=code, out=text.strip().splitlines()[:1])
    code, text, s = fk(bob, "research")
    note("bob's footer", lines=[ln for ln in text.splitlines() if ln.startswith("BOARD")])
    code, text, s = fk(bob, "commons", "board")
    note("bob reads", lines=text.strip().splitlines()[:2])
    code, text, s = fk(bob, "lua", "game.tick_paused = true")
    note("a pause", exit=code, says=[ln for ln in text.splitlines() if "refused" in ln][:1])
    code, text, s = fk(bob, "commons", "journal", "4")
    note("journal", lines=[ln[:110] for ln in text.strip().splitlines()[:4]])
    gw.probe(gw.saves["commons"])
    code, text, s = fk(ann, "commons", "status")
    note("status", lines=text.strip().splitlines()[:1])
    calls = gw.journal_tail("commons", 500)
    note("calls", total=len(calls), ann=sum(1 for c in calls if c.get("who") == "ann"),
         bob=sum(1 for c in calls if c.get("who") == "bob"),
         slowest_ms=max((c.get("ms") or 0) for c in calls))

    if replica:
        r.lua("game.server_save('commons') rcon.print('saved')")
        time.sleep(3)
        code, text, s = fk(ann, "replica")
        REPORT["replica_text"] = text
        note("ann's replica", exit=code, seconds=s, lines=text.strip().splitlines()[:3])
        code, text, s = fk(ann, "sim", "game", "lua",
                           "rcon.print(game.tick .. ' paused ' .. tostring(game.tick_paused) .. "
                           "' gears ' .. game.surfaces.nauvis.count_entities_filtered{name = "
                           "'assembling-machine-1'})")
        note("replica lua", exit=code, out=text.strip().splitlines()[:1])
        code, text, s = fk(ann, "sim", "stop")
        note("replica stop", exit=code, out=text.strip().splitlines()[:1])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
