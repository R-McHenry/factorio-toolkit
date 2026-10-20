"""laptop_server: a short-lived Factorio server on the laptop, for what the server's lab can't host.

    from tools.laptop_server import LaptopServer
    with LaptopServer("chat", scenario="fk-play") as srv:      # or save=PATH, or map_gen=PATH
        with srv.rcon() as r:
            ...

It is the laptop's own Factorio (Steam, 2.0.77) as a headless server with its own ``--config``:
write-data under ``v5/out/laptop-server/<name>/`` (never %APPDATA%\\Factorio: the player's client
holds that lock), its own UDP and RCON ports, no autosave, not public. The scenario is copied from
``scenario/`` into its write-data. The server is killed when the block ends, also on an error, so
nothing outlives the script that started it. ``FK_SCRIPT_OUTPUT`` is pointed at its
script-output for snapshots.

Checks it can run on its own (each starts a server, checks, stops it):
    python tools/laptop_server.py chat      the scenario loads, and a chat line reaches storage.fk_chat
    python tools/laptop_server.py own       1.2 through fkcore.apply in play mode: the toolkit's own
                                            dropped rows go (a built assembler, an unbuilt ghost), and a
                                            belt laid under another net with the old net's plates is
                                            ordered out with a fresh ghost on it
"""
from __future__ import annotations

import os
import secrets
import shutil
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from fkcore import link  # noqa: E402

EXE = os.environ.get("FK_LAPTOP_FACTORIO",
                     r"C:\Program Files (x86)\Steam\steamapps\common\Factorio\bin\x64\factorio.exe")
BASE = os.path.join(ROOT, "out", "laptop-server")


def _free_port(kind=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LaptopServer:
    def __init__(self, name, scenario=None, save=None, map_gen=None, boot_s=40):
        self.name, self.scenario, self.save, self.map_gen, self.boot_s = (name, scenario, save,
                                                                          map_gen, boot_s)
        self.dir = os.path.join(BASE, name)
        self.write = os.path.join(self.dir, "write")
        self.pw_file = os.path.join(self.dir, "rcon.pw")
        self.port = _free_port(socket.SOCK_DGRAM)
        self.rcon_port = _free_port()
        self.proc = None

    def _files(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        os.makedirs(os.path.join(self.write, "scenarios"))
        if self.scenario:
            shutil.copytree(os.path.join(ROOT, "scenario", self.scenario),
                            os.path.join(self.write, "scenarios", self.scenario))
        with open(os.path.join(self.dir, "config.ini"), "w", encoding="utf-8") as fh:
            fh.write("[path]\nread-data=__PATH__executable__/../../data\n"
                     f"write-data={self.write.replace(os.sep, '/')}\n")
        with open(os.path.join(self.dir, "server-settings.json"), "w", encoding="utf-8") as fh:
            fh.write('{"name": "fk5 laptop test", "description": "short-lived test server", '
                     '"visibility": {"public": false, "lan": false}, '
                     '"require_user_verification": false, "max_players": 0, "auto_pause": false, '
                     '"autosave_interval": 0}')
        with open(self.pw_file, "w", encoding="utf-8") as fh:
            fh.write(secrets.token_hex(12))

    def __enter__(self):
        self._files()
        with open(self.pw_file, encoding="utf-8") as fh:
            pw = fh.read().strip()
        args = [EXE, "--config", os.path.join(self.dir, "config.ini"), "--port", str(self.port),
                "--rcon-bind", f"127.0.0.1:{self.rcon_port}", "--rcon-password", pw,
                "--server-settings", os.path.join(self.dir, "server-settings.json")]
        if self.save:
            args += ["--start-server", self.save]
        else:
            args += ["--start-server-load-scenario", self.scenario or "fk-play"]
        if self.map_gen:
            args += ["--map-gen-settings", self.map_gen]
        self.log = open(os.path.join(self.dir, "server.log"), "w", encoding="utf-8")
        self.proc = subprocess.Popen(args, stdout=self.log, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL)
        os.environ["FK_SCRIPT_OUTPUT"] = os.path.join(self.write, "script-output")
        link.OUT_DIR = os.environ["FK_SCRIPT_OUTPUT"]
        t0 = time.time()
        while time.time() - t0 < self.boot_s:
            if self.proc.poll() is not None:
                raise RuntimeError(f"the server exited ({self.proc.returncode}): see {self.log.name}")
            try:
                with self.rcon() as r:
                    if r.lua("rcon.print(game.tick)").strip().isdigit():
                        return self
            except (OSError, link.LinkError):
                pass
            time.sleep(1)
        self.__exit__(None, None, None)
        raise RuntimeError(f"no RCON answer within {self.boot_s} s: see {self.log.name}")

    def rcon(self):
        return link.Rcon("127.0.0.1", self.rcon_port, self.pw_file)

    def __exit__(self, *exc):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait(timeout=10)
        if getattr(self, "log", None):
            self.log.close()
        return False


def check_chat():
    from fkcore import chat
    with LaptopServer("chat", scenario="fk-play") as srv:
        with srv.rcon() as r:
            before = chat.read(r)
            r.call("hello from the laptop test server")       # plain RCON text is console chat
            time.sleep(1.5)
            after = chat.read(r)
            info = r.lua("rcon.print(script.level.level_name .. ' ' .. tostring(game.get_surface('lab') ~= nil)"
                         " .. ' ' .. tostring(game.forces['lab'] ~= nil))").strip()
    print(f"scenario: {info}")
    print(f"journal before: {before['journal']}, {len(before['messages'])} messages")
    print(f"journal after:  {after['journal']}, messages {after['messages']}")
    ok = after["journal"] and any("hello from the laptop" in m.get("message", "")
                                  for m in after["messages"])
    print("chat journal:", "OK" if ok else "NOT recorded")
    return 0 if ok else 1


def check_own():
    """The mini factory (tests/test_fkp.py) pasted on the lab surface under play rules and built
    (revived: test setup), then a chest left as a ghost; then a design that drops the assembler
    m1 and the chest and lays the iron belt row under net cable while belt b2 holds iron plates."""
    from fkcore import apply as applymod, compose, fkp
    from fkcore.catalog import Catalog
    from tests.test_fkp import MINI
    cat, s, f = Catalog.load(), "lab", "lab"
    watch = {"plots": "keep", "sanctioned": "mark 2h", "notify": "off"}

    def composed(text):
        return compose.compose(fkp.loads("fkp 1 surface lab\nplot mini at 10,0 rot 0 size 7x7\n"),
                               {"mini": fkp.loads(text)}, cat)

    def at(r, x, y):
        return r.lua(f"local o = {{}} for _, e in pairs(game.get_surface('{s}').find_entities_filtered"
                     f"{{position = {{{x}, {y}}}, radius = 0.3}}) do o[#o + 1] = (e.type == "
                     "'entity-ghost' and ('ghost:' .. e.ghost_name) or e.name) .. "
                     "(e.to_be_deconstructed() and '(decon)' or '') end "
                     "rcon.print(table.concat(o, ' '))").strip()

    v2 = (MINI.replace("e gears/m1 assembling-machine-1 4.5,3.5 recipe=iron-gear-wheel\n", "")
          .replace("~iron/", "~cable/").replace("net=iron", "net=cable"))
    nets1 = {"mini/iron": ["iron-plate"], "mini/gear": ["iron-gear-wheel"]}
    nets2 = {"mini/cable": ["copper-cable"], "mini/gear": ["iron-gear-wheel"]}
    with LaptopServer("own", scenario="fk-play") as srv:
        with srv.rcon() as r:
            r.lua(link.lua_generate_area(s, f, (-32, -32, 64, 64)))
            rep = applymod.apply(r, composed(MINI), cat, mode="play", force=f, policy=watch,
                                 net_items=nets1)
            r.lua(link.lua_revive(s, (0, -10, 40, 20)))
            rep = applymod.apply(r, composed(MINI + "e extra/c0 wooden-chest 16.5,5.5\n"), cat,
                                 mode="play", force=f, policy=watch, net_items=nets1, own=rep.own)
            ghost = at(r, 26.5, 5.5)
            r.lua(f"local b = game.get_surface('{s}').find_entity('transport-belt', {{14.5, 0.5}}) "
                  "b.get_transport_line(1).insert_at_back({name = 'iron-plate', count = 1}) "
                  "rcon.print('ok')")
            rep = applymod.apply(r, composed(v2), cat, mode="play", force=f, policy=watch,
                                 net_items=nets2, own=rep.own)
            got = {"chest before": ghost, "m1": at(r, 14.5, 3.5), "chest": at(r, 26.5, 5.5),
                   "b2": at(r, 14.5, 0.5)}
    print("\n".join(rep.lines()))
    want = {"chest before": "ghost:wooden-chest", "m1": "assembling-machine-1(decon)",
            "chest": "", "b2": "ghost:transport-belt transport-belt(decon)"}
    for k, v in want.items():
        print(f"{k:<13} {got[k] or '(nothing)':<45} {'OK' if got[k] == v else 'NOT ' + repr(v)}")
    return 0 if got == want and rep.dropped == 2 and len(rep.relaid) == 1 else 1


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "chat"
    raise SystemExit({"chat": check_chat, "own": check_own}[what]())
