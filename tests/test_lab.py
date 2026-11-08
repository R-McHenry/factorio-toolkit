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

    def test_a_lab_build_script_of_the_sources_own(self):
        # 2.1.31: the default flow has no tier or hands step; a lab.build.fkb beside the source
        # replaces it, so a design can have express belts and bulk inserters on the lab
        ws, _ = lab.prepare(self.game, "iron")
        self.assertEqual(self.read(ws, "lab.build.fkb"), lab.SCRIPT)
        self.write("game/lab.build.fkb", "read_surface lab\ntier maximize --allow blue\n")
        ws, _ = lab.prepare(self.game, "iron")
        self.assertEqual(self.read(ws, "lab.build.fkb"),
                         "read_surface lab\ntier maximize --allow blue\n")

    def test_a_workspace_of_its_own_on_a_slot_of_its_own(self):
        ws, (x, y, w, h) = lab.prepare(self.game, "iron")
        self.assertEqual(ws, os.path.join(self.run, "lab", "iron"))
        self.assertEqual((w, h), (26, 26))                       # the plot nauvis gives it
        self.assertEqual(sorted(os.listdir(ws)), ["lab.build.fkb", "lab.surface", "smelting.fk"])
        # (the first build: nothing to keep)
        surf = surfacemod.load(os.path.join(ws, "lab.surface"))
        self.assertEqual((surf.name, surf.mode), ("lab", "lab"))
        p = surf.places["iron"]
        self.assertEqual((p.module, p.x, p.y, p.w, p.h), ("smelting", x, y, 26, 26))
        self.assertIn("apply           --scope all", self.read(ws, "lab.build.fkb"))
        # the first slot is the middle cell, as 2.0.3's grid had it
        self.assertEqual((x, y), (-100, -100))
        # the same slot each time; another factory, another slot
        self.assertEqual(lab.prepare(self.game, "iron")[1][:2], (x, y))
        self.assertNotEqual(lab.prepare(self.game, "smelting")[1][:2], (x, y))
        self.assertEqual(set(lab.slots(self.game)), {"iron", "smelting"})
        # game\ is untouched
        self.assertEqual(sorted(os.listdir(self.game)), ["map.terrain.json", "nauvis.build.fkb",
                                                         "nauvis.fkp", "nauvis.surface",
                                                         "smelting.fk"])

    def test_a_rebuild_keeps_the_last_layout_to_pin(self):
        # 2.1.31: emptying the workspace lost write_layout's MODULE.fkp, so `route --only stale`
        # pinned nothing and every lab rebuild of a 1300-net loop routed it all again
        ws, _ = lab.prepare(self.game, "iron")
        self.write("lab/iron/smelting.fkp", "fkp 1 module smelting\n")
        self.write("lab/iron/stale.txt", "x")
        self.write("lab/iron/lab.fkp", "fkp 1 surface lab\n")
        ws, _ = lab.prepare(self.game, "iron")
        self.assertEqual(self.read(ws, "smelting.fkp"), "fkp 1 module smelting\n")
        self.assertNotIn("stale.txt", os.listdir(ws))
        # 2.1.32: not the lab surface's own, which holds the old slot
        self.assertNotIn("lab.fkp", os.listdir(ws))
        # a layout the source has of its own wins
        self.write("game/smelting.fkp", "fkp 1 module smelting # game\n")
        ws, _ = lab.prepare(self.game, "iron")
        self.assertIn("# game", self.read(ws, "smelting.fkp"))

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
            lab.prepare(self.game, "iron", src="../elsewhere")    # outside the run

    def test_clear_frees_the_slot(self):
        lab.prepare(self.game, "iron")
        r = mock.Mock()
        r.lua.return_value = "137"
        lines = lab.clear(r, self.game, "iron")
        self.assertIn("emptied (137 entities) and freed", lines[0])
        self.assertEqual(lab.slots(self.game), {})
        self.assertIn("no slot", lab.clear(r, self.game, "iron")[0])

    def test_any_size_and_no_last_slot(self):
        # 2.0.12 (Rory, 2026-10-24: "the lab should be allowed to have infinite size")
        self.assertEqual(lab.cells(190, 190), (1, 1))
        self.assertEqual(lab.cells(191, 450), (2, 3))
        lab.prepare(self.game, "iron")
        _ws, (x, y, _w, _h) = lab.prepare(self.game, "iron", size=(450, 300))
        held = lab.slots(self.game)
        self.assertEqual(held["iron"][2:], [600, 400])              # outgrown: a new slot
        self.assertEqual(held["iron"][:2], [x, y])
        for k in range(120):                                       # 81 was 2.0.3's last
            lab.slot_of(self.game, f"f{k}", (150, 150))
        held = lab.slots(self.game)
        boxes = [tuple(v) for v in held.values()]
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                self.assertTrue(lab._free(a, [b]), (a, b))         # no two slots overlap
        self.assertEqual(len(held), 121)

    def test_a_2_0_3_slot_reads_as_one_cell(self):
        self.write("lab/slots.json", json.dumps({"iron": [-900, -900]}))
        self.assertEqual(lab.slots(self.game), {"iron": [-900, -900, 200, 200]})
        self.assertEqual(lab.slot_of(self.game, "iron", (26, 26))[0], (-900, -900, 200, 200))

    def test_a_build_takes_the_edge_off_and_generates_its_chunks(self):
        said = []

        def lua(text):
            said.append(text)
            return "was 2048x2048" if "map_gen_settings" in text else "0"
        r = mock.Mock()
        r.lua.side_effect = lua
        with mock.patch.object(lab.flow, "run", return_value=(1, None)):
            lines = lab.build(r, self.game, "iron")
        self.assertIn("  the lab has no edge now (it was 2048x2048)", lines)
        self.assertIn("m.width, m.height = 0, 0", said[0])
        self.assertIn("force_generate_chunk_requests", said[1])
        self.assertIn("chunks generated under the slot", lines[2])

    def test_the_lua_is_safe(self):
        for text in (lab.lua_clear((0, 0, 10, 10)), lab.lua_supply((0, 0, 10, 10)),
                     lab.lua_unbounded()):
            link.assert_safe("/sc " + text)
            self.assertIn("'lab'", text)                         # the lab surface, never nauvis

    def test_the_lab_power_carries_a_beaconed_bay(self):
        # 2.1.31: 2 MJ a tick (120 MW) left a PU chain's assemblers on low power
        self.assertIn("ei.power_production = 100000000", lab.lua_supply((0, 0, 10, 10)))

    def test_the_feed_takes_the_fastest_loader_and_belt(self):
        # 2.1.31: a yellow loader fed a lab port 15/s and starved a blue-belt line of ore
        text = lab.lua_feed([dict(k="loader", at=[0.5, 1], port="m/a", dir="north",
                                  type="output"),
                             dict(k="belt", at=[0.5, 0.5], port="m/a", dir="north")])
        link.assert_safe("/sc " + text)
        self.assertIn("'turbo-loader', 'express-loader'", text)
        self.assertIn("'turbo-transport-belt', 'express-transport-belt'", text)
        self.assertNotIn("loader = 'loader'", text)

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
