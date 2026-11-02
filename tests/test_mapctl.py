"""3.0, ``fk map`` (Rory, 2026-11-02: "I also want the agent to be able to start over and save or
load games", "also a pause"): the live map's saves, loads, start-over and pause. The server's
stop and start are the host's (pkill, su, systemctl), so they are stubbed here; the RCON half is
a fake that keeps a tick and writes the saves it is asked for.
``tools/laptop_server.py map`` runs save, saves and pause on a real server."""
import os
import re
import shutil
import tempfile
import time
import unittest
from unittest import mock

from fkcore import mapctl


class FakeRcon:
    """game.server_save writes the file; tick_paused and storage.kickoff_setup are kept."""
    state = {}

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def lua(self, body):
        st = FakeRcon.state
        m = re.search(r"game\.server_save\('([^']+)'\)", body)
        if m:
            with open(os.path.join(st["saves"], m.group(1) + ".zip"), "w") as fh:
                fh.write(str(st["tick"]))
            return f"{st['tick']}\n"
        m = re.search(r"game\.tick_paused = (true|false)", body)
        if m:
            st["paused"] = m.group(1) == "true"
            return f"{st['tick']} {m.group(1)}\n"
        if "storage.kickoff_setup)" in body:
            return f"{st.get('setup', 'nil')}\n"
        if "storage.kickoff_setup" in body:            # the kickoff's own steps
            st["setup"] = "rules"
            return '{"speed_bonus": 0.35, "cargo_bonus": 1}' if "o.changes" in body else "ok\n"
        return f"{st['tick']}\n"


class MapTest(unittest.TestCase):
    def setUp(self):
        self.saves = tempfile.mkdtemp(prefix="fkmap-")
        self.addCleanup(shutil.rmtree, self.saves, True)
        FakeRcon.state = {"saves": self.saves, "tick": 1000}
        for f, text in (("v1-r-start.zip", "start"), ("v1-r.zip", "live")):
            with open(os.path.join(self.saves, f), "w") as fh:
                fh.write(text)
        self.m = mapctl.Map("/x/v1-runs/r/game", instance="sb", saves=self.saves, rcon=FakeRcon)
        self.calls = []
        self.m._running = lambda: True
        self.m._stop = lambda: self.calls.append("stop")
        self.m._start = lambda: (self.calls.append("start"), 5)[1]
        chown = mock.patch.object(mapctl.shutil, "chown", lambda *a: None)   # no computah here
        chown.start()
        self.addCleanup(chown.stop)

    def test_the_run_and_its_saves_come_from_the_game_folder(self):
        m = mapctl.Map("/home/computah/factorio/v1-runs/20261101-1642-seablock-v1/game",
                       instance="sb")
        self.assertEqual(m.own.replace("\\", "/"),
                         "/home/computah/sb/saves/v1-20261101-1642-seablock-v1.zip")
        self.assertTrue(m.start_save.endswith("-start.zip"))

    def test_save_and_list(self):
        self.assertEqual(self.m.save("iron-first"), ["map: saved as iron-first at tick 1000"])
        listed = "\n".join(self.m.list())
        for name in ("start", "live", "iron-first"):
            self.assertIn(name, listed)
        with self.assertRaises(mapctl.MapError):
            self.m.save("start")
        with self.assertRaises(mapctl.MapError):
            self.m.save("../x")

    def test_pause_and_resume(self):
        self.assertEqual(self.m.pause(True)[0], "map: paused at tick 1000 (fk map resume goes on)")
        self.assertTrue(FakeRcon.state["paused"])
        self.assertEqual(self.m.pause(False), ["map: running at tick 1000"])

    def test_load_keeps_the_map_first_then_runs_the_save(self):
        self.m.save("a")
        FakeRcon.state["tick"] = 2000
        time.sleep(0.01)
        out = self.m.load("a")
        self.assertEqual(self.calls, ["stop", "start"])
        self.assertTrue(out[0].startswith("map: saved as before-load-"))
        with open(self.m.own) as fh:
            self.assertEqual(fh.read(), "1000")              # a's map is the run's own save now
        kept = [f for f in os.listdir(self.saves) if f.startswith("play-before-load-")]
        self.assertEqual(len(kept), 1)
        with self.assertRaises(mapctl.MapError):
            self.m.load("nothing")

    def test_restart_sets_a_bare_start_up(self):
        out = self.m.restart()
        with open(self.m.own) as fh:
            self.assertEqual(fh.read(), "start")
        self.assertTrue(any(line.startswith("map: kickoff bootstrap") for line in out), out)
        self.assertTrue(os.path.exists(os.path.join(self.saves, "play-start-set-up.zip")))
        out = self.m.restart()
        self.assertIn("map: the start was set up already (rules)", out)

    def test_the_verbs(self):
        self.assertEqual(mapctl.run("/x/v1-runs/r/game", "saves", [], instance="sb",
                                    saves=self.saves, rcon=FakeRcon)[0],
                         "map: saves of this run (fk map load NAME):")
        with self.assertRaises(mapctl.MapError):
            mapctl.run("/x/v1-runs/r/game", "explode", [], saves=self.saves, rcon=FakeRcon)


if __name__ == "__main__":
    unittest.main()
