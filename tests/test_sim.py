"""2.0.61: the speedrun planner (fkcore.sim). Offline: the playback script and the Lua; the game side
was checked on the laptop's own server with a real save (two runs of the same minute and two plays
of the same script from the same state gave the same game, plate for plate)."""
import os
import tempfile
import unittest

from fkcore import link, sim


class PlaybackTest(unittest.TestCase):
    def test_a_script_reads_in_order(self):
        steps = sim.play_lines("""
# a plan
from start
speed 100
place game/mine.fkp @0,0
at +1800
at 36000
paste game/smelt.fkp @40.5,-2
remove 0,0,10,10
decon -5,-5,5,5
run 3600
save after-smelt   # a comment
""")
        self.assertEqual([v for _i, v, _a in steps],
                         ["from", "speed", "place", "at", "at", "paste", "remove", "decon", "run",
                          "save"])
        self.assertEqual(steps[2][2], ["game/mine.fkp", (0.0, 0.0)])
        self.assertEqual(steps[3][2], [("+", 1800)])
        self.assertEqual(steps[4][2], [("=", 36000)])
        self.assertEqual(steps[5][2], ["game/smelt.fkp", (40.5, -2.0)])
        self.assertEqual(steps[6][2], [(0.0, 0.0, 10.0, 10.0)])
        self.assertEqual(steps[8][2], [3600])
        self.assertEqual(sim.play_lines(r"place game\mine.fkp @0,0")[0][2][0], r"game\mine.fkp")

    def test_refused(self):
        for text, why in (("jump 3", "one of"), ("speed", "takes 1"), ("place a.fkp 0,0", "@X,Y"),
                          ("remove 5,5,0,0", "X0,Y0,X1,Y1"), ("speed 2\nfrom start", "first")):
            with self.assertRaises(sim.SimError) as cm:
                sim.play_lines(text)
            self.assertIn(why, str(cm.exception))


class SimFilesTest(unittest.TestCase):
    def test_the_planner_lives_in_the_runs_sim_folder(self):
        run = tempfile.mkdtemp(prefix="fksim-")
        s = sim.Sim(run)
        self.assertEqual(s.root, os.path.join(run, "sim"))
        self.assertEqual(s.save_path("start"), os.path.join(run, "sim", "write", "saves",
                                                            "start.zip"))
        self.assertIsNone(s.state())
        self.assertEqual(s.names(), [])
        with self.assertRaises(sim.SimError) as cm:
            s.start("start")
        self.assertIn("fk sim fetch", str(cm.exception))
        with self.assertRaises(sim.SimError):
            s.save("two words")

    def test_a_packs_mods(self):
        # 3.0: a Sea Block run's planner loads Sea Block's mods, not this Factorio's defaults
        import json
        import shutil
        from unittest import mock
        run, src = tempfile.mkdtemp(prefix="fksim-"), tempfile.mkdtemp(prefix="fksim-mods-")
        self.addCleanup(shutil.rmtree, run, True)
        self.addCleanup(shutil.rmtree, src, True)
        with mock.patch.dict(os.environ, {"FK_PACK": "seablock", "FK_SIM_MODS": src}):
            with self.assertRaises(sim.SimError) as cm:
                sim.Sim(run)._mods()
            self.assertIn("no CircuitProcessing 2.0.0", str(cm.exception))
            with open(os.path.join(os.path.dirname(sim.__file__), "data", "packs", "seablock",
                                   "catalog.json"), encoding="utf-8") as fh:
                want = [m.rsplit(" ", 1) for m in json.load(fh)["mods"]]
            for n, ver in want:
                if n not in sim.BUILT_IN:
                    os.makedirs(os.path.join(src, f"{n}_{ver}"))
                    with open(os.path.join(src, f"{n}_{ver}", "info.json"), "w") as fh:
                        fh.write("{}")
            notes = sim.Sim(run)._mods()
        self.assertEqual(notes, ["pack seablock, 27 mods"])
        mods = os.path.join(run, "sim", "write", "mods")
        with open(os.path.join(mods, "mod-list.json"), encoding="utf-8") as fh:
            on = {m["name"]: m["enabled"] for m in json.load(fh)["mods"]}
        self.assertTrue(on["base"] and on["SeaBlock"] and on["angelsrefining"])
        self.assertFalse(on["space-age"] or on["quality"] or on["elevated-rails"])
        self.assertTrue(os.path.exists(os.path.join(mods, "SeaBlock_0.6.0", "info.json")))
        with mock.patch.dict(os.environ, {"FK_PACK": ""}):
            self.assertEqual(sim.Sim(run)._mods(), [])          # the base game: Factorio's own
        self.assertFalse(os.path.exists(mods))
        self.assertTrue(os.path.exists(os.path.join(src, "SeaBlock_0.6.0", "info.json")))

    def test_the_lua_is_safe(self):
        for text in (sim._lua_fill((0, 0, 10, 10)), sim._lua_clear_marked((0, 0, 10, 10)),
                     sim._lua_tiles((0, 0, 10, 10))):
            link.assert_safe("/sc " + text)
            self.assertNotIn("script.on_", text)            # nothing registered, ever


if __name__ == "__main__":
    unittest.main()
