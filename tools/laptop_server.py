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


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "chat"
    raise SystemExit({"chat": check_chat}[what]())
