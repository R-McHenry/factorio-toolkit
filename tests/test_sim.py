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

    def test_the_lua_is_safe(self):
        for text in (sim._lua_fill((0, 0, 10, 10)), sim._lua_clear_marked((0, 0, 10, 10)),
                     sim._lua_tiles((0, 0, 10, 10))):
            link.assert_safe("/sc " + text)
            self.assertNotIn("script.on_", text)            # nothing registered, ever


if __name__ == "__main__":
    unittest.main()
