"""2.0.64: Go-Explore on the speedrun planner (fkcore.explore). Rory, 2026-10-29: cells are
floor(log(item)) for each item in total items produced; a new cell keeps the trajectory that got
there, a faster way replaces it; the sim picks the go cell and a goal cell at least N away
(Manhattan), impartially, and the agent plays. The game side was checked on a laptop planner
(a replayed trajectory reaches the archived cell at the same tick)."""
import os
import random
import shutil
import tempfile
import unittest

from fkcore import explore, sim


class CellTest(unittest.TestCase):
    def test_floor_log_of_what_was_made(self):
        self.assertEqual(explore.cell({"iron-plate": 1024, "gear": 1023, "x": 1, "none": 0}),
                         {"iron-plate": 10, "gear": 9, "x": 0})
        self.assertEqual(explore.cell({"iron-plate": 1024}, base=4), {"iron-plate": 5})
        self.assertEqual(explore.cell({"iron-plate": 10000}, base=10), {"iron-plate": 4})

    def test_key_distance_and_reached(self):
        a, b = {"iron": 3, "gear": 1}, {"iron": 5, "circuit": 0}
        self.assertEqual(explore.key(a), "gear=1,iron=3")
        self.assertEqual(explore.levels_of(explore.key(a)), a)
        self.assertEqual(explore.distance(a, b), 2 + 2 + 1)      # an item never made is -1
        self.assertTrue(explore.reached({"iron": 5, "gear": 2}, {"iron": 5}))
        self.assertFalse(explore.reached({"iron": 4}, {"iron": 5, "gear": 0}))
        self.assertEqual(explore.count_text(10, 2), "1,024+")
        self.assertEqual(explore.count_text(-1, 2), "none")


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkexplore-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.a = explore.Archive(self.dir)
        self.a.data["root"] = "x0"
        self.a.cells[explore.key({"iron": 3})] = {"levels": {"iron": 3}, "tick": 100, "save": "x0",
                                                  "traj": [], "visits": 0, "parent": None}

    def test_new_faster_and_known(self):
        saved = []
        self.a.start_episode(explore.key({"iron": 3}), {"iron": 5}, 100)
        self.a.record(150, "paste", ["f.fkp", 0, 0])
        lv = {"iron": 4}
        self.assertEqual(self.a.offer(lv, 400, self.a.episode["traj"], saved.append), "new")
        self.assertEqual(self.a.offer(lv, 500, [], saved.append), None)       # slower: kept
        self.assertEqual(self.a.offer(lv, 300, [{"tick": 120, "verb": "decon",
                                                 "args": [0, 0, 1, 1]}], saved.append), "faster")
        self.assertEqual(saved, ["x1", "x1"])          # the faster way replaces the cell's save
        row = self.a.cells[explore.key(lv)]
        self.assertEqual((row["tick"], row["traj"][0]["verb"], row["beaten"]), (300, "decon", 1))
        # the root is never written over
        self.assertEqual(self.a.offer({"iron": 3}, 50, [], saved.append), "faster")
        self.assertEqual(self.a.cells[explore.key({"iron": 3})]["save"], "x2")

    def test_the_goal_is_dist_steps_on_known_and_makeable_items(self):
        rng = random.Random(1)
        goal = self.a.pick_goal({"iron": 3}, ["gear", "circuit"], 6, rng)
        go = {"iron": 3}
        self.assertEqual(sum(lv - go.get(i, -1) for i, lv in goal.items()), 6)
        self.assertTrue(set(goal) <= {"iron", "gear", "circuit"})
        self.assertEqual(explore.distance(go, dict(go, **goal)), 6)

    def test_go_is_impartial_and_the_prior_follows_the_best(self):
        for k, lv, tick, parent in (("a", {"iron": 4}, 200, explore.key({"iron": 3})),
                                    ("b", {"iron": 5}, 300, None),
                                    ("c", {"iron": 6}, 400, None)):
            self.a.cells[explore.key(lv)] = {"levels": lv, "tick": tick, "save": k, "traj": [],
                                             "parent": parent}
        self.a.cells[explore.key({"iron": 5})]["parent"] = explore.key({"iron": 4})
        self.a.cells[explore.key({"iron": 6})]["parent"] = explore.key({"iron": 5})
        rng = random.Random(3)
        seen = {self.a.pick_go(rng) for _ in range(200)}
        self.assertEqual(len(seen), 4)                      # every cell can be the go cell
        self.a.data["settings"] = {"prior": 1}
        self.a.cells["stray"] = {"levels": {"gear": 2}, "tick": 50, "save": "s", "traj": [],
                                 "parent": None}
        pool = {self.a.pick_go(rng) for _ in range(200)}
        self.assertEqual(pool, set(self.a.ancestry(self.a.best(1)[0][0])))
        self.assertNotIn("stray", pool)

    def test_the_plan_plays(self):
        lv = {"iron": 4}
        self.a.start_episode(explore.key({"iron": 3}), {"iron": 5}, 100)
        self.a.record(150, "paste", ["f.fkp", 3, 4])
        self.a.record(160, "game", ["lua", "game.print('a b')"])
        self.a.record(170, "game", ["research", "automation"])
        self.a.offer(lv, 400, self.a.episode["traj"], lambda _n: None)
        text = self.a.plan(explore.key(lv))
        steps = sim.play_lines(text)
        self.assertEqual([s[1] for s in steps],
                         ["from", "speed", "at", "paste", "at", "game", "at", "game", "at"])
        self.assertEqual(steps[0][2], ["x0"])
        self.assertEqual(steps[5][2][:2], ["lua", "--file"])
        with open(steps[5][2][2], encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "game.print('a b')")
        self.assertEqual(steps[-1][2], [("=", 400)])


class FairTest(unittest.TestCase):
    def test_free_building_is_off_in_explore_mode(self):
        d = tempfile.mkdtemp(prefix="fkexplore-")
        self.addCleanup(shutil.rmtree, d, True)
        s = sim.Sim(d)
        a = s.archive()
        a.data["on"] = True
        a.write()
        for call in (lambda: s.place("x.fkp", (0, 0), None), lambda: s.remove((0, 0, 1, 1)),
                     lambda: s.load("x0")):
            with self.assertRaises(sim.SimError):
                call()


if __name__ == "__main__":
    unittest.main()
