"""tools/transplant.py, its pure parts (no game): runs, batches, the region guard, the piece."""
import importlib.util
import json
import os
import unittest

from fkcore import link, terrain

_PATH = os.path.join(os.path.dirname(__file__), "..", "tools", "transplant.py")
_spec = importlib.util.spec_from_file_location("transplant", _PATH)
tp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tp)


class TransplantTest(unittest.TestCase):
    def test_runs_and_batches(self):
        self.assertEqual(tp.runs({(1, 0), (2, 0), (3, 0), (5, 0), (2, 1)}),
                         [[0, 1, 3], [0, 5, 5], [1, 2, 2]])
        rows = [[i, i, 1000] for i in range(500)]
        parts = tp.batches(rows)
        self.assertGreater(len(parts), 1)
        self.assertEqual(sum(parts, []), rows)
        self.assertTrue(all(len(json.dumps(p, separators=(",", ":"))) <= tp.BATCH for p in parts))

    def test_the_target_stays_in_the_region_chunk_by_chunk(self):
        region = (460, 400, 700, 640)
        tp.check_target((480, 416, 624, 556), region)              # chunks 480..640, 416..576
        with self.assertRaises(SystemExit):
            tp.check_target((470, 416, 500, 450), region)          # chunk 448..480 sticks out
        with self.assertRaises(SystemExit):
            tp.check_target((480, 416, 680, 450), region)          # chunk 672..704 sticks out

    def test_the_piece_moves_ore_water_and_cliffs(self):
        t = terrain.Terrain("nauvis", (0, 0, 64, 64), 1, {"iron-ore": {(3, 4): 700, (40, 40): 9}},
                            frozenset({(5, 5), (6, 5)}), frozenset(),
                            [terrain.Cliff("cliff", 10.0, 12.5, "south-to-north",
                                           (9.0, 10.5, 11.0, 14.5))])
        water, res, cliffs = tp.piece(t, (0, 0, 32, 32), (480, 416))
        self.assertEqual(sorted(water), [(485, 421), (486, 421)])
        self.assertEqual(res, {"iron-ore": [[483, 420, 700]]})
        self.assertEqual(cliffs, [["cliff", 490.0, 428.5, "south-to-north"]])

    def test_the_lua_is_safe_and_lab_only(self):
        for lua in (tp.lua_clear((480, 416, 512, 448)), tp.lua_water([[0, 1, 3]]),
                    tp.lua_resources("iron-ore", [[1, 2, 300]]),
                    tp.lua_cliffs([["cliff", 2.0, 2.5, "west-to-east"]]),
                    tp.lua_count((480, 416, 512, 448))):
            link.assert_safe(lua)
            self.assertIn("game.get_surface('lab')", lua)
            self.assertNotIn("nauvis", lua)
            for line in lua.splitlines():
                code = line.strip()
                self.assertFalse("--" in code and not code.startswith("--"), code)


if __name__ == "__main__":
    unittest.main()
