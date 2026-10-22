"""2.0.3 (Rory, 2026-10-22: "the lead should be using the lab and planning rather then waiting"):
fk lab builds a design on its own slot of the lab surface. Offline: the workspace, the slots and
the Lua; the game side is checked on a laptop test server (tools/laptop_server.py)."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from fkcore import lab, link
from fkcore import surface as surfacemod

ROOT = os.path.join(os.path.dirname(__file__), "..")
EXAMPLE = os.path.join(ROOT, "agent", "docs", "examples", "smelting.fk")


class LabTest(unittest.TestCase):
    def setUp(self):
        self.run = tempfile.mkdtemp(prefix="fklab-")
        self.addCleanup(shutil.rmtree, self.run, True)
        self.game = os.path.join(self.run, "game")
        os.makedirs(self.game)
        shutil.copy(EXAMPLE, os.path.join(self.game, "smelting.fk"))
        self.write("game/nauvis.surface", "surface  nauvis\nmode     play\nterrain  none\n"
                   "catalog  base\n\nplace iron = smelting plot 10,90 26x26\n")
        self.write("game/nauvis.build.fkb", "read_surface nauvis\n")
        self.write("game/map.terrain.json", "{}")
        self.write("game/nauvis.fkp", "fkp 1 surface nauvis\n")

    def write(self, rel, text):
        path = os.path.join(self.run, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def read(self, *parts):
        with open(os.path.join(*parts), encoding="utf-8") as fh:
            return fh.read()

    def test_a_workspace_of_its_own_on_a_slot_of_its_own(self):
        ws, (x, y, w, h) = lab.prepare(self.game, "iron")
        self.assertEqual(ws, os.path.join(self.run, "lab", "iron"))
        self.assertEqual((w, h), (26, 26))                       # the plot nauvis gives it
        self.assertEqual(sorted(os.listdir(ws)), ["lab.build.fkb", "lab.surface", "smelting.fk"])
        surf = surfacemod.load(os.path.join(ws, "lab.surface"))
        self.assertEqual((surf.name, surf.mode), ("lab", "lab"))
        p = surf.places["iron"]
        self.assertEqual((p.module, p.x, p.y, p.w, p.h), ("smelting", x, y, 26, 26))
        self.assertIn("apply           --scope all", self.read(ws, "lab.build.fkb"))
        # inside the lab's -1024..1024 with the slot's room
        self.assertTrue(-1024 < x and x + lab.SLOT < 1024 and -1024 < y and y + lab.SLOT < 1024)
        # the same slot each time; another factory, another slot
        self.assertEqual(lab.prepare(self.game, "iron")[1][:2], (x, y))
        self.assertNotEqual(lab.prepare(self.game, "smelting")[1][:2], (x, y))
        self.assertEqual(set(lab.slots(self.game)), {"iron", "smelting"})
        # game\ is untouched
        self.assertEqual(sorted(os.listdir(self.game)), ["map.terrain.json", "nauvis.build.fkb",
                                                         "nauvis.fkp", "nauvis.surface",
                                                         "smelting.fk"])

    def test_from_a_stage_folder_and_the_refusals(self):
        os.makedirs(os.path.join(self.run, "stages", "3"))
        shutil.copy(EXAMPLE, os.path.join(self.run, "stages", "3", "ore.fk"))
        ws, (_x, _y, w, h) = lab.prepare(self.game, "ore", src="stages/3", size=(40, 30))
        self.assertEqual((w, h), (40, 30))
        self.assertIn("ore.fk", os.listdir(ws))
        self.assertIn("from stages", self.read(ws, "lab.surface"))
        with self.assertRaises(lab.LabError):
            lab.prepare(self.game, "nope")
        with self.assertRaises(lab.LabError):
            lab.prepare(self.game, "iron", size=(300, 20))         # bigger than a slot
        with self.assertRaises(lab.LabError):
            lab.prepare(self.game, "iron", src="../elsewhere")    # outside the run

    def test_clear_frees_the_slot(self):
        lab.prepare(self.game, "iron")
        r = mock.Mock()
        r.lua.return_value = "137"
        lines = lab.clear(r, self.game, "iron")
        self.assertIn("emptied (137 entities) and freed", lines[0])
        self.assertEqual(lab.slots(self.game), {})
        self.assertIn("no slot", lab.clear(r, self.game, "iron")[0])

    def test_the_lua_is_safe(self):
        for text in (lab.lua_clear((0, 0, 10, 10)), lab.lua_supply((0, 0, 10, 10))):
            link.assert_safe("/sc " + text)
            self.assertIn("'lab'", text)                         # the lab surface, never nauvis

    def test_a_lab_surface_in_game_takes_nothing_over(self):
        # 2.0.3: the first .surface / .build.fkb alphabetically was the codebase's
        self.write("game/lab.surface", "surface  lab\nmode     lab\nterrain  none\ncatalog  base\n")
        self.write("game/lab.build.fkb", "read_surface lab\n")
        self.assertEqual(surfacemod.load_game(self.game).name, "nauvis")
        sys.path.insert(0, os.path.join(ROOT, "agent"))
        import fk
        with mock.patch.object(fk, "GAME", self.game):
            self.assertEqual(fk._script(), "nauvis.build.fkb")


if __name__ == "__main__":
    unittest.main()
