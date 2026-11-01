"""2.1.28: fk.py's pull skips the files the last pull left as they are (size and mtime), and fk
lua pulls nothing. On the 20261030-2352 run a pull opened all ~450 files of game\\ (~6 s), and a
player's lua call took 8-10 s of which ~0.2 s was the game."""
import importlib.util
import io
import json
import os
import shutil
import tarfile
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..")
_spec = importlib.util.spec_from_file_location("fk_agent_2128", os.path.join(ROOT, "agent", "fk.py"))
fk_agent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fk_agent)

T0 = 1_700_000_000


class PullTest(unittest.TestCase):
    def setUp(self):
        self.run_dir = tempfile.mkdtemp(prefix="fksync-")
        self.addCleanup(shutil.rmtree, self.run_dir, True)
        self.game = os.path.join(self.run_dir, "game")
        os.makedirs(os.path.join(self.game, "out"))
        with open(os.path.join(self.run_dir, "run.json"), "w", encoding="utf-8") as fh:
            json.dump({"host": "gamehost", "host_game": "/srv/run/game",
                       "host_toolkit": "/srv/tk"}, fh)
        stamp = os.path.join(self.game, "out", ".synced")
        for name, value in (("RUN", self.run_dir), ("GAME", self.game), ("STAMP", stamp)):
            p = mock.patch.object(fk_agent, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.host = {"a.fk": (b"design a\n", T0), "out/alerts.json": (b"[]\n", T0)}
        self.calls = []

    def fake_run(self, argv, input=None, stdout=None, **_kw):
        self.calls.append(argv[-1])
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for rel, (data, mtime) in self.host.items():
                info = tarfile.TarInfo("./" + rel)
                info.size, info.mtime = len(data), mtime
                tar.addfile(info, io.BytesIO(data))
        return mock.Mock(returncode=0, stdout=buf.getvalue())

    def pull(self):
        cfg = fk_agent._config()
        taken = []
        real = tarfile.TarFile.extractall

        def spy(tar, path=".", members=None, **kw):
            members = list(members or [])
            taken.extend(m.name for m in members if m.isfile())
            return real(tar, path, members=members, **kw)
        with mock.patch.object(fk_agent.subprocess, "run", self.fake_run), \
                mock.patch.object(tarfile.TarFile, "extractall", spy):
            fk_agent.pull(cfg)
        return taken

    def read(self, rel):
        with open(os.path.join(self.game, rel), "rb") as fh:
            return fh.read()

    def test_a_second_pull_takes_only_what_changed(self):
        self.assertEqual(sorted(self.pull()), ["./a.fk", "./out/alerts.json"])
        self.assertEqual(self.pull(), [])                   # nothing changed: nothing written
        self.host["out/alerts.json"] = (b'["new"]\n', T0 + 60)
        self.assertEqual(self.pull(), ["./out/alerts.json"])
        self.assertEqual(self.read("out/alerts.json"), b'["new"]\n')

    def test_an_edit_here_is_kept(self):
        self.pull()
        path = os.path.join(self.game, "a.fk")
        with open(path, "wb") as fh:
            fh.write(b"edited here\n")
        os.utime(path, (time.time(), time.time()))
        self.assertEqual(self.pull(), [])
        self.assertEqual(self.read("a.fk"), b"edited here\n")

    def test_lua_does_not_pull(self):
        self.pull()
        self.calls.clear()
        with mock.patch.object(fk_agent.subprocess, "run", self.fake_run):
            self.assertEqual(fk_agent.main(["lua", "rcon.print(game.tick)"]), 0)
        self.assertTrue(any("fkcore lua" in c for c in self.calls))
        self.assertFalse(any(c.startswith("tar -cf -") for c in self.calls), self.calls)


if __name__ == "__main__":
    unittest.main()
