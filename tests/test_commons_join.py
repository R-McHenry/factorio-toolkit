"""3.4 (PLAN-COMMONS): a run folder on a shared save (kickoff/join.py), the plot line
(commons.set_plot), a replica's mods (sim), the run's fk link settings."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from fkcore import commons
from fkcore import sim as simmod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "kickoff"))
import join  # noqa: E402


def _fk():
    spec = importlib.util.spec_from_file_location("agent_fk", os.path.join(ROOT, "agent", "fk.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSharedGameFolder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.game = os.path.join(self.tmp.name, "game")
        shutil.copytree(os.path.join(ROOT, "kickoff", "template", "game"), self.game)

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, name):
        with open(os.path.join(self.game, name), encoding="utf-8") as fh:
            return fh.read()

    def test_the_shared_start_is_in_nobodys_design(self):
        join.shape_game(self.game)
        left = set(os.listdir(self.game))
        # the kit, the plant and the two layouts that hold them as the run's own entities: a
        # build that found them there and not in the design ordered the shared start taken up
        self.assertFalse(left & {"plant.fk", "kit.fk", "kit.json", "plant-w3.json", "nauvis.fkp",
                                 "world.fkp"})
        self.assertTrue({"cells.fk", "routing.fk", "prelude.fk", "nauvis.build.fkb",
                         "nauvis.surface"} <= left)
        world = self.read("world.fk")
        self.assertNotIn("import", world)
        self.assertIn("world = World @(0, 0) size 64x64    # not claimed yet", self.read("nauvis.fk"))
        surface = self.read("nauvis.surface")
        self.assertIn("surface  nauvis", surface)
        self.assertIn("design   nauvis.fk", surface)

    def test_a_plot_given_at_once(self):
        join.shape_game(self.game, (36, -24, 68, 8))
        self.assertIn("\nworld = World @(36, -24) size 32x32\n", self.read("nauvis.fk"))

    def test_a_claim_moves_the_plot_line(self):
        join.shape_game(self.game)
        line = commons.set_plot(self.game, [100, -50, 228, 78])
        self.assertEqual(line, "world = World @(100, -50) size 128x128")
        text = self.read("nauvis.fk")
        self.assertIn(f"\n{line}\n", text)
        self.assertEqual(text.count("world = World"), 1)
        self.assertIn('import World from "world.fk"', text)
        os.remove(os.path.join(self.game, "nauvis.fk"))
        self.assertIsNone(commons.set_plot(self.game, [0, 0, 1, 1]))


class TestReplicaMods(unittest.TestCase):
    def test_a_replica_runs_the_shared_saves_mods(self):
        with tempfile.TemporaryDirectory() as run, \
                mock.patch.dict(os.environ, {"FK_PACK": ""}):
            s = simmod.Sim(run)
            os.makedirs(s.root)
            self.assertEqual(s._mods(), [])                       # no word from a gateway: its own
            self.assertFalse(os.path.exists(os.path.join(s.write, "mods", "mod-list.json")))
            with open(os.path.join(s.root, "mods.json"), "w") as fh:
                json.dump({"mods": ["base"]}, fh)
            self.assertEqual(s._mods(), ["mods: base"])
            with open(os.path.join(s.write, "mods", "mod-list.json")) as fh:
                got = {m["name"]: m["enabled"] for m in json.load(fh)["mods"]}
            self.assertEqual(got, {"base": True, "elevated-rails": False, "quality": False,
                                   "space-age": False, "recycler": False})
            with open(os.path.join(s.root, "mods.json"), "w") as fh:
                json.dump({"mods": ["base", "space-age", "quality", "elevated-rails"]}, fh)
            s._mods()
            with open(os.path.join(s.write, "mods", "mod-list.json")) as fh:
                got = {m["name"]: m["enabled"] for m in json.load(fh)["mods"]}
            self.assertEqual(got["space-age"], True)
            self.assertEqual(got["recycler"], False)


class TestTheRunsLink(unittest.TestCase):
    def test_a_shared_run_says_gateway_and_its_key_file_is_the_runs(self):
        fk = _fk()
        local = fk._link_env({"env": {"FK_RCON_PORT": "27015", "FK_RCON_PW_FILE": ""}})
        self.assertEqual(local, {"FK_LINK": "on", "FK_RCON_PORT": "27015"})
        shared = fk._link_env({"env": {"FK_LINK": "gateway", "FK_GATEWAY": "https://h/v1/saves/c",
                                       "FK_GATEWAY_KEY_FILE": ".gateway-key"}})
        self.assertEqual(shared["FK_LINK"], "gateway")
        self.assertEqual(shared["FK_GATEWAY_KEY_FILE"], os.path.join(fk.RUN, ".gateway-key"))


if __name__ == "__main__":
    unittest.main()
