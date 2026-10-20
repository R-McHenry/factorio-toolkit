"""rehearse_v1: a V1 kickoff and the agent's first steps, on a laptop test world (nothing on the server).

    python tools/rehearse_v1.py [--keep-run]

1. A fresh map from the fk-play scenario with the kickoff's map-gen settings (world 3's seed), on a
   laptop test server (tools/laptop_server.py: killed at the end, whatever happens).
2. kickoff/setup_v1.py: bootstrap, kit, starter rules.
3. kickoff/new_run.py: a run folder in local mode (out/rehearsal-run), the toolkit pinned at HEAD.
4. As the agent, with the run's own ``bin/fk.py`` only:
   - ``fk build``: the plant and its pole chain pasted as ghosts (play mode); robots build them
     from the kit (5 s check-ins, at most 5 min); ``fk look`` at the plant.
   - examples/gears.fk on a plot near spawn, ``fk build``, the robots, ``fk look``.
   - a chat line, which shows at the end of the next command.
5. Numbers into out/rehearsal.json; the server's log in out/laptop-server/rehearsal/.
"""
from __future__ import annotations

import json
import os
import re
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
RUN = os.path.join(ROOT, "out", "rehearsal-run")
#: the gear plot: 30,-20 puts its requester outside the kit's logistic square, so cover
#: robots must give it a roboport (rehearsal 2 found the chest unserved there)
GEARS_AT = os.environ.get("FK_REHEARSE_GEARS_AT", "30,-20 16x16")
REPORT = {}


def note(step, **kw):
    REPORT.setdefault(step, {}).update(kw)
    print(f"[{step}] " + ", ".join(f"{k}={v}" for k, v in kw.items()), flush=True)


def fk(*args, timeout=240):
    env = dict(os.environ, FK_RUN=RUN)
    t0 = time.time()
    p = subprocess.run([sys.executable, os.path.join(RUN, "bin", "fk.py")] + list(args), env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    return p.returncode, p.stdout, time.time() - t0


def ghosts(r, area):
    x0, y0, x1, y1 = area
    return int(r.lua(f"rcon.print(game.surfaces.nauvis.count_entities_filtered{{area = {{{{{x0},{y0}}},"
                     f"{{{x1},{y1}}}}}, type = 'entity-ghost'}})").strip())


def wait_built(r, area, limit_s=300):
    t0, left = time.time(), ghosts(r, area)
    while left and time.time() - t0 < limit_s:
        time.sleep(5)
        left = ghosts(r, area)
    return left, round(time.time() - t0)


def verdicts(text):
    m = re.search(r"tick \d+: ([^\n]*)", text)
    return m.group(1) if m else text.strip().splitlines()[0] if text.strip() else ""


def judge():
    """The world against the design: the build script's own diff step, on the game side (until
    the live ``fk look`` lands, this is how the agent asks)."""
    code, text, s = fk("build", "--from", "diff", "--to", "diff")
    with open(os.path.join(RUN, "game", "out", "diff.txt"), encoding="utf-8") as fh:
        diff = fh.read()
    return code, text, diff


def main(argv):
    shutil.rmtree(RUN, ignore_errors=True)
    with LaptopServer("rehearsal", scenario="fk-play", map_gen=MAPGEN, boot_s=120) as srv:
        env = {"FK_RCON_PORT": str(srv.rcon_port), "FK_RCON_PW_FILE": srv.pw_file,
               "FK_SCRIPT_OUTPUT": os.path.join(srv.write, "script-output")}
        with srv.rcon() as r:
            note("map", tick=r.lua("rcon.print(game.tick)").strip(),
                 level=r.lua("rcon.print(script.level.level_name)").strip())
            got = setup_v1.run(r)
            note("setup", bootstrap=got["bootstrap"], kit=got["kit"],
                 robots=(got["rules"]["construction_robots"], got["rules"]["logistic_robots"]),
                 speed=got["rules"]["speed_bonus"], cargo=got["rules"]["cargo_bonus"])
            cfg = new_run.make(RUN, local=env)
            note("run", toolkit=cfg["toolkit_sha"], folder=RUN)

            code, text, s = fk("build")
            REPORT["build1_text"] = text
            apply_txt = open(os.path.join(RUN, "game", "out", "apply.txt"), encoding="utf-8").read()
            note("build plant", exit=code, seconds=round(s, 1), apply=apply_txt.splitlines()[1:3])
            plant = (-36, -41, 8, 10)
            left, waited = wait_built(r, plant)
            note("robots plant", ghosts_left=left, waited_s=waited)
            code, text, diff = judge()
            REPORT["diff1_text"] = diff
            note("diff plant", exit=code, verdicts=verdicts(diff))
            def power():
                return r.lua("local s = game.surfaces.nauvis local n = {} for _, p in pairs(s.find_entities_filtered{"
                             "type = 'electric-pole'}) do if p.electric_network_id then n[p.electric_network_id] = true end end "
                             "local k = 0 for _ in pairs(n) do k = k + 1 end "
                             "local re = s.find_entities_filtered{name = 'nuclear-reactor'}[1] "
                             "local fuel = re and re.get_fuel_inventory().get_item_count() or 0 "
                             "local req = s.find_entities_filtered{name = 'requester-chest', area = {{-36, -41}, {-16, -22}}}[1] "
                             "local cells = req and req.get_inventory(defines.inventory.chest).get_item_count('uranium-fuel-cell') or 0 "
                             "rcon.print(k .. ' ' .. (re and string.format('%.0f', re.temperature) or '-') .. ' ' .. fuel .. ' ' .. cells)").split()
            t0 = time.time()
            p = power()
            while float(p[1]) < 100 and time.time() - t0 < 150:      # the reactor heating: 5 s check-ins
                time.sleep(5)
                p = power()
            note("power", networks=p[0], reactor_temperature=p[1], fuel_in_reactor=p[2],
                 cells_in_requester=p[3], waited_s=round(time.time() - t0))

            shutil.copy(os.path.join(ROOT, "agent", "docs", "examples", "gears.fk"),
                        os.path.join(RUN, "game", "gears.fk"))
            # inside the kit roboport's logistic square (8,8 +- 25: x and y from -17 to 33); at
            # 30,-20 (rehearsal 2) the requester stood outside every logistic network
            with open(os.path.join(RUN, "game", "nauvis.surface"), "a", encoding="utf-8") as fh:
                fh.write(f"\nplace gears = gears plot {GEARS_AT}\n")
            code, text, s = fk("build")
            REPORT["build2_text"] = text
            apply_txt = open(os.path.join(RUN, "game", "out", "apply.txt"), encoding="utf-8").read()
            note("build gears", exit=code, seconds=round(s, 1), apply=apply_txt.splitlines()[1:3])
            gx, gy = (int(v) for v in GEARS_AT.split()[0].split(","))
            gears_area = (gx - 2, gy - 2, gx + 18, gy + 18)
            left, waited = wait_built(r, gears_area)
            note("robots gears", ghosts_left=left, waited_s=waited)
            r.call("hello from Rory's side (the rehearsal)")
            time.sleep(1)
            req = r.lua("local c = game.surfaces.nauvis.find_entities_filtered{name = 'requester-chest', "
                        f"area = {{{{{gears_area[0]}, {gears_area[1]}}}, {{{gears_area[2]}, {gears_area[3]}}}}}}}[1] if not c then rcon.print('none') return end "
                        "local out = {} local sec = c.get_logistic_sections() "
                        "for i = 1, sec.sections_count do for _, f in pairs(sec.get_section(i).filters) do "
                        "out[#out + 1] = (f.value and f.value.name or '?') .. ':' .. (f.min or 0) end end "
                        "rcon.print(table.concat(out, ',') .. ' network=' .. tostring(c.logistic_network ~= nil))").strip()
            note("requester", request=req)
            code, text, diff = judge()
            REPORT["diff2_text"] = diff
            REPORT["footer2_text"] = text
            note("diff gears", exit=code, verdicts=verdicts(diff),
                 chat_in_footer="hello from Rory" in text)
            def made():
                return int(r.lua("local st = game.forces.player.get_item_production_statistics('nauvis') "
                                 "rcon.print(st.get_input_count('iron-gear-wheel'))").strip())
            t0 = time.time()
            while made() == 0 and time.time() - t0 < 120:              # the first gears: 5 s check-ins
                time.sleep(5)
            first = round(time.time() - t0)
            time.sleep(30)
            note("gears made", first_after_s=first, count_30s_later=made(),
                 plates_in_inbox=r.lua("local c = game.surfaces.nauvis.find_entities_filtered{name = 'requester-chest', "
                                       f"area = {{{{{gears_area[0]}, {gears_area[1]}}}, {{{gears_area[2]}, {gears_area[3]}}}}}}}[1] rcon.print(c and c.get_inventory(defines.inventory.chest)"
                                       ".get_item_count('iron-plate') or -1)").strip())
            code, text, s = fk("measure", "--area", ",".join(str(v) for v in gears_area),
                               "--seconds", "30", timeout=120)
            REPORT["measure_text"] = text
            note("measure", exit=code, lines=[l for l in text.splitlines() if "gears/" in l])
    with open(os.path.join(ROOT, "out", "rehearsal.json"), "w", encoding="utf-8") as fh:
        json.dump(REPORT, fh, indent=1, default=str)
    print("report: out/rehearsal.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
