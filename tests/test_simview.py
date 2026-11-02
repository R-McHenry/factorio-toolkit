"""3.0, the sim view (Rory, 2026-11-02: "a tree of all the save states as a directed graph, with
their x,y based on our hor vert metrics"): the lineage, the places (explore's V and H) and the
page's graph, with the planner faked."""
import json
import os
import shutil
import tempfile
import unittest

from fkcore import simview


class FakeSim:
    def __init__(self, root, made, running=True):
        self.root = root
        self.write = os.path.join(root, "write")
        self.saves = os.path.join(self.write, "saves")
        os.makedirs(os.path.join(self.write, "script-output", "fk5"), exist_ok=True)
        os.makedirs(self.saves, exist_ok=True)
        self.state_file = os.path.join(root, "state.json")
        self._made, self.running = made, running

    def state(self):
        return {"save": "start", "head": "a"} if self.running else None

    def names(self):
        return sorted(f[:-4] for f in os.listdir(self.saves) if f.endswith(".zip"))

    def made(self):
        return {"tick": self._made.get("_tick", 60), "made": {k: v for k, v in self._made.items()
                                                              if k != "_tick"},
                "can": [], "researched": []}

    def lua(self, body, timeout=30.0):
        if "helpers.write_file" in body:
            tag = body.split("'fk5/")[1].split(".json'")[0]
            with open(os.path.join(self.write, "script-output", "fk5", f"{tag}.json"), "w") as fh:
                json.dump({"tick": 60, "box": [0, 0, 4, 4],
                           "e": [["transport-belt", "transport-belt", 1.5, 1.5, 4, 1, 1, False]],
                           "land": [[0, 0], [1, 0], [2, 0], [5, 0], [1, 2]]}, fh)
            return "1"
        if "game.speed" in body:
            return "1"
        return "false"


class SimViewTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fksimview-")
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_land_runs(self):
        self.assertEqual(simview._runs([[0, 0], [1, 0], [2, 0], [5, 0], [1, 2]]),
                         {"0": [[0, 2], [5, 5]], "2": [[1, 1]]})

    def test_record_keeps_the_parent_and_the_map(self):
        s = FakeSim(self.root, {"iron-plate": 100, "_tick": 600})
        self.assertEqual(simview.record(s, "a", "start"), "")
        self.assertEqual(simview.record(s, "a", "a"), "")     # saved over itself: parent kept
        lin = simview.Lineage(self.root)
        self.assertEqual(lin.data["a"]["parent"], "start")
        self.assertEqual(lin.data["a"]["tick"], 600)
        self.assertEqual(lin.view("a")["land"], {"0": [[0, 2], [5, 5]], "2": [[1, 1]]})

    def test_places_v_up_h_off_the_best_line(self):
        rows = {"start": {"made": {}, "parent": None, "tick": 0},
                "a": {"made": {"iron-plate": 64}, "parent": "start", "tick": 10},
                "b": {"made": {"iron-plate": 1024, "gear": 64}, "parent": "a", "tick": 20},
                "side": {"made": {"copper-plate": 512}, "parent": "a", "tick": 15}}
        pos, line, exact = simview.place(rows, None)
        self.assertFalse(exact)
        self.assertEqual(line, ["start", "a", "b"])
        self.assertGreater(pos["b"][0], pos["a"][0])
        self.assertEqual(pos["b"][1], 0)
        self.assertGreater(pos["side"][1], 0)                 # off the line

    def test_the_graph_has_the_live_game(self):
        s = FakeSim(self.root, {"iron-plate": 200, "_tick": 900})
        simview.record(s, "a", "start")
        open(os.path.join(s.saves, "a.zip"), "w").close()
        open(os.path.join(s.saves, "old.zip"), "w").close()
        g = simview.graph(s)
        names = [n["name"] for n in g["nodes"]]
        self.assertIn("(live)", names)
        live = [n for n in g["nodes"] if n["name"] == "(live)"][0]
        self.assertEqual(live["parent"], "a")
        self.assertEqual(g["unmeasured"], ["old"])
        self.assertTrue([n for n in g["nodes"] if n["name"] == "a"][0]["view"])


if __name__ == "__main__":
    unittest.main()
