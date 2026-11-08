"""3.1 (PLAN-3.1 31-surface; Rory 11-08: "the lab is a surface"): a module built alone on a
slot of a surface (fkcore.alone), the stand-ins the agent asks for by name (fkcore.standin), and
`fk lab`, the alias of both on the lab surface (fkcore.lab). Offline: the workspace, the slots,
the Lua; the game side is checked on a laptop test server (tools/laptop_server.py)."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from fkcore import alone, lab, link, standin
from fkcore import surface as surfacemod

ROOT = os.path.join(os.path.dirname(__file__), "..")
EXAMPLE = os.path.join(ROOT, "agent", "docs", "examples", "smelting.fk")


class AloneBase(unittest.TestCase):
    def setUp(self):
        self.run = tempfile.mkdtemp(prefix="fkalone-")
        self.addCleanup(shutil.rmtree, self.run, True)
        self.game = os.path.join(self.run, "game")
        os.makedirs(self.game)
        shutil.copy(EXAMPLE, os.path.join(self.game, "smelting.fk"))
        self.write("game/nauvis.surface", "surface  nauvis\nterrain  none\ncatalog  base\n\n"
                   "place iron = smelting plot 10,90 26x26\n")
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

    def fake(self, edge="was 2048x2048"):
        said = []

        def lua(text):
            said.append(text)
            if "map_gen_settings" in text:
                return edge
            if "helpers.table_to_json" in text:
                return json.dumps({"power": "1,2", "stocked": {"iron-ore": 400}, "fuel": 0,
                                   "modules": 0, "placed": 0, "blocked": []})
            return "0"
        r = mock.Mock()
        r.lua.side_effect = lua
        return r, said


class AloneTest(AloneBase):
    """fkcore.alone: a module built alone on a slot of a surface."""

    def test_a_workspace_of_its_own_on_a_slot_of_its_own(self):
        ws, (x, y, w, h) = alone.prepare(self.game, "iron")
        self.assertEqual(ws, os.path.join(self.run, "lab", "iron"))          # the lab: <run>/lab/NAME
        self.assertEqual((w, h), (26, 26))                                    # the plot nauvis gives it
        self.assertEqual(sorted(os.listdir(ws)), ["lab.build.fkb", "lab.surface", "smelting.fk"])
        surf = surfacemod.load(os.path.join(ws, "lab.surface"))
        # the lab is a surface file like any other: free, force lab, no mode line
        self.assertEqual((surf.name, surf.free, surf.force_name, surf.notes), ("lab", True, "lab", []))
        self.assertNotIn("mode", self.read(ws, "lab.surface"))
        p = surf.places["iron"]
        self.assertEqual((p.module, p.x, p.y, p.w, p.h), ("smelting", x, y, 26, 26))
        self.assertIn("apply           --scope all", self.read(ws, "lab.build.fkb"))
        self.assertIn("read_surface    lab", self.read(ws, "lab.build.fkb"))
        # the first slot is the middle cell, as 2.0.3's grid had it
        self.assertEqual((x, y), (-100, -100))
        # the same slot each time; another factory, another slot
        self.assertEqual(alone.prepare(self.game, "iron")[1][:2], (x, y))
        self.assertNotEqual(alone.prepare(self.game, "smelting")[1][:2], (x, y))
        self.assertEqual(set(alone.slots(self.game)), {"iron", "smelting"})
        self.assertTrue(os.path.exists(os.path.join(self.run, "lab", "slots.json")))
        # game\ is untouched
        self.assertEqual(sorted(os.listdir(self.game)), ["map.terrain.json", "nauvis.build.fkb",
                                                         "nauvis.fkp", "nauvis.surface",
                                                         "smelting.fk"])

    def test_a_surface_of_the_games_own_gives_its_properties(self):
        # a surface file in game\ for another surface: its properties go into the workspace's,
        # its plots do not; the slots and the workspace are that surface's
        self.write("game/vulcanus.surface", "surface  vulcanus\nforce    player\nterrain  map\n"
                   "catalog  base\nnotify   off\n\nplace x = smelting plot 0,0 30x30\n")
        ws, _plot = alone.prepare(self.game, "iron", surface="vulcanus")
        self.assertEqual(ws, os.path.join(self.run, "vulcanus", "iron"))
        surf = surfacemod.load(os.path.join(ws, "vulcanus.surface"))
        self.assertEqual((surf.name, surf.free, surf.force_name, surf.terrain, surf.notify_mode),
                         ("vulcanus", False, "player", "none", "off"))
        self.assertEqual(list(surf.places), ["iron"])
        self.assertEqual(set(alone.slots(self.game, "vulcanus")), {"iron"})
        self.assertEqual(alone.slots(self.game, "lab"), {})
        self.assertIn("read_surface    vulcanus", self.read(ws, "vulcanus.build.fkb"))
        with self.assertRaises(alone.AloneError):
            alone.prepare(self.game, "iron", surface="gleba")            # no file, no default

    def test_a_build_script_of_the_sources_own(self):
        # 2.1.31: the default flow has no tier or hands step; a <surface>.build.fkb beside the
        # source replaces it, so a design can have express belts and bulk inserters
        ws, _ = alone.prepare(self.game, "iron")
        self.assertEqual(self.read(ws, "lab.build.fkb"), alone.SCRIPT.format(surface="lab"))
        self.write("game/lab.build.fkb", "read_surface lab\ntier maximize --allow blue\n")
        ws, _ = alone.prepare(self.game, "iron")
        self.assertEqual(self.read(ws, "lab.build.fkb"),
                         "read_surface lab\ntier maximize --allow blue\n")

    def test_a_rebuild_keeps_the_last_layout_to_pin(self):
        # 2.1.31: emptying the workspace lost write_layout's MODULE.fkp, so `route --only stale`
        # pinned nothing and every rebuild of a 1300-net loop routed it all again
        ws, _ = alone.prepare(self.game, "iron")
        self.write("lab/iron/smelting.fkp", "fkp 1 module smelting\n")
        self.write("lab/iron/stale.txt", "x")
        self.write("lab/iron/lab.fkp", "fkp 1 surface lab\n")
        ws, _ = alone.prepare(self.game, "iron")
        self.assertEqual(self.read(ws, "smelting.fkp"), "fkp 1 module smelting\n")
        self.assertNotIn("stale.txt", os.listdir(ws))
        self.assertNotIn("lab.fkp", os.listdir(ws))          # the surface's own holds the old slot
        self.write("game/smelting.fkp", "fkp 1 module smelting # game\n")
        ws, _ = alone.prepare(self.game, "iron")
        self.assertIn("# game", self.read(ws, "smelting.fkp"))

    def test_from_a_stage_folder_and_the_refusals(self):
        os.makedirs(os.path.join(self.run, "stages", "3"))
        shutil.copy(EXAMPLE, os.path.join(self.run, "stages", "3", "ore.fk"))
        ws, (_x, _y, w, h) = alone.prepare(self.game, "ore", src="stages/3", size=(40, 30))
        self.assertEqual((w, h), (40, 30))
        self.assertIn("ore.fk", os.listdir(ws))
        self.assertIn("from stages", self.read(ws, "lab.surface"))
        with self.assertRaises(alone.AloneError):
            alone.prepare(self.game, "nope")
        with self.assertRaises(alone.AloneError):
            alone.prepare(self.game, "iron", src="../elsewhere")    # outside the run

    def test_clear_frees_the_slot_and_empties_it_only_where_free(self):
        alone.prepare(self.game, "iron")
        r = mock.Mock()
        r.lua.return_value = "137"
        lines = alone.clear(r, self.game, "iron")
        self.assertIn("emptied (137 entities) and freed", lines[0])
        self.assertEqual(alone.slots(self.game), {})
        self.assertIn("no slot", alone.clear(r, self.game, "iron")[0])
        # not free: the slot is freed, nothing destroyed
        alone.prepare(self.game, "smelting", surface="nauvis", size=(20, 20))
        r.lua.reset_mock()
        lines = alone.clear(r, self.game, "smelting", surface="nauvis")
        self.assertIn("not free", lines[0])
        r.lua.assert_not_called()

    def test_any_size_and_no_last_slot(self):
        # 2.0.12 (Rory, 2026-10-24: "the lab should be allowed to have infinite size")
        self.assertEqual(alone.cells(190, 190), (1, 1))
        self.assertEqual(alone.cells(191, 450), (2, 3))
        alone.prepare(self.game, "iron")
        _ws, (x, y, _w, _h) = alone.prepare(self.game, "iron", size=(450, 300))
        held = alone.slots(self.game)
        self.assertEqual(held["iron"][2:], [600, 400])              # outgrown: a new slot
        self.assertEqual(held["iron"][:2], [x, y])
        for k in range(120):                                       # 81 was 2.0.3's last
            alone.slot_of(self.game, f"f{k}", (150, 150))
        held = alone.slots(self.game)
        boxes = [tuple(v) for v in held.values()]
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                self.assertTrue(alone._free(a, [b]), (a, b))       # no two slots overlap
        self.assertEqual(len(held), 121)

    def test_a_2_0_3_slot_reads_as_one_cell(self):
        self.write("lab/slots.json", json.dumps({"iron": [-900, -900]}))
        self.assertEqual(alone.slots(self.game), {"iron": [-900, -900, 200, 200]})
        self.assertEqual(alone.slot_of(self.game, "iron", (26, 26))[0], (-900, -900, 200, 200))

    def test_a_free_build_empties_the_slot_and_generates_its_chunks(self):
        r, said = self.fake()
        with mock.patch.object(alone.flow, "run", return_value=(1, None)):
            got = alone.build(r, self.game, "iron")
        self.assertEqual((got.free, got.force, got.surface, got.code), (True, "lab", "lab", 1))
        box = alone.box(*alone.slots(self.game)["iron"])
        self.assertIn(alone.lua_clear("lab", box), said)
        self.assertTrue(any("force_generate_chunk_requests" in s for s in said))
        self.assertIn("emptied first", got.lines[1])
        self.assertFalse(any("map_gen_settings" in s for s in said))    # the edge is the lab alias's
        self.assertIn("stopped", got.lines[-1])

    def test_a_build_on_a_surface_that_is_not_free_destroys_nothing(self):
        r, said = self.fake()
        with mock.patch.object(alone.flow, "run", return_value=(0, mock.Mock())):
            got = alone.build(r, self.game, "smelting", surface="nauvis", size=(20, 20))
        self.assertEqual((got.free, got.force), (False, "player"))
        self.assertEqual(said, [])
        self.assertTrue(any("not free" in ln for ln in got.lines))

    def test_a_kept_build_empties_nothing(self):
        # 3.0.2-lab (Rory 11-08): a base in the lab changes a region at a time, its trains, stock
        # and hand-placed things standing
        r, said = self.fake()
        with mock.patch.object(alone.flow, "run", return_value=(1, None)):
            alone.build(r, self.game, "iron")
        box = alone.box(*alone.slots(self.game)["iron"])
        said.clear()
        with mock.patch.object(alone.flow, "run", return_value=(0, mock.Mock())):
            got = alone.build(r, self.game, "iron", keep=True)
        self.assertNotIn(alone.lua_clear("lab", box), said)
        self.assertTrue(any("kept: the slot stands" in ln for ln in got.lines))

    def test_keep_needs_a_slot_that_stands(self):
        r, _said = self.fake()
        with self.assertRaises(alone.AloneError):
            alone.build(r, self.game, "iron", keep=True)

    def test_the_lua_is_safe(self):
        text = alone.lua_clear("lab", (0, 0, 10, 10))
        link.assert_safe("/sc " + text)
        self.assertIn("'lab'", text)


class StandinTest(AloneBase):
    """fkcore.standin: god-mode stand-ins, by name, only where things are free."""

    def test_the_lua_is_safe_and_names_the_surface(self):
        for text in (standin.lua_supply("lab", "lab", (0, 0, 10, 10)), standin.lua_unbounded("lab"),
                     standin.lua_ore_clear("lab", (0, 0, 32, 32)),
                     standin.lua_ore_put("lab", [["iron-ore", 1, 2, 5]])):
            link.assert_safe("/sc " + text)
            self.assertIn("'lab'", text)                         # the surface given, never nauvis
            self.assertNotIn("nauvis", text)

    def test_the_power_carries_a_beaconed_bay(self):
        # 2.1.31: 2 MJ a tick (120 MW) left a PU chain's assemblers on low power
        self.assertIn("ei.power_production = 100000000", standin.lua_supply("lab", "lab", (0, 0, 10, 10)))

    def test_the_feed_takes_the_fastest_loader_and_belt(self):
        # 2.1.31: a yellow loader fed a lab port 15/s and starved a blue-belt line of ore
        text = standin.lua_feed("lab", "lab", [dict(k="loader", at=[0.5, 1], port="m/a", dir="north",
                                                    type="output"),
                                               dict(k="belt", at=[0.5, 0.5], port="m/a", dir="north")])
        link.assert_safe("/sc " + text)
        self.assertIn("'turbo-loader', 'express-loader'", text)
        self.assertIn("'turbo-transport-belt', 'express-transport-belt'", text)
        self.assertNotIn("loader = 'loader'", text)

    def test_a_stand_in_is_refused_where_things_are_not_free(self):
        with self.assertRaises(standin.StandinError):
            standin.require_free(surfacemod.loads("surface nauvis\n"), "standin supply")
        standin.require_free(surfacemod.loads("surface lab\nfree\n"), "standin supply")

    def test_supply_reports_what_it_stood(self):
        r, _said = self.fake()
        line, got = standin.supply(r, "lab", "lab", (0, 0, 10, 10))
        self.assertIn("power an energy interface at 1,2", line)
        self.assertIn("iron-ore 400", line)
        self.assertEqual(got["stocked"], {"iron-ore": 400})


class LabAliasTest(AloneBase):
    """fkcore.lab: `fk lab` is `fk alone --surface lab` plus the lab's usual stand-ins."""

    def test_a_lab_build_takes_the_edge_off_then_supplies_and_feeds(self):
        r, said = self.fake()
        ctx = mock.Mock()
        ctx.flats, ctx.layouts = {}, {}
        with mock.patch.object(alone.flow, "run", return_value=(0, ctx)):
            lines = lab.build(r, self.game, "iron")
        self.assertIn("m.width, m.height = 0, 0", said[0])
        self.assertIn("  the lab has no edge now (it was 2048x2048)", lines)
        self.assertIn("force_generate_chunk_requests", said[1])
        self.assertTrue(any("stand-in supply: power an energy interface" in ln for ln in lines))
        self.assertTrue(any(ln.startswith("  next: let it run") for ln in lines))
        self.assertEqual(lab.slots(self.game), alone.slots(self.game, "lab"))

    def test_a_kept_lab_build_stocks_nothing(self):
        # stock put in by the build would be a dump (Rory: no test dumps)
        r, said = self.fake()
        with mock.patch.object(alone.flow, "run", return_value=(1, None)):
            lab.build(r, self.game, "iron")
        box = alone.box(*lab.slots(self.game)["iron"])
        said.clear()
        with mock.patch.object(alone.flow, "run", return_value=(0, mock.Mock())), \
                mock.patch.object(standin, "feed") as feed:
            lines = lab.build(r, self.game, "iron", keep=True)
        self.assertNotIn(alone.lua_clear("lab", box), said)
        self.assertNotIn(standin.lua_supply("lab", "lab", box), said)
        feed.assert_not_called()
        self.assertTrue(any("kept: no power, stock or fuel" in ln for ln in lines))

    def test_measure_tops_the_requesters_up_first(self):
        r, said = self.fake()
        with mock.patch.object(alone.flow, "run", return_value=(1, None)):
            lab.build(r, self.game, "iron")
        said.clear()
        with mock.patch.object(alone, "measure_alone", return_value=["alone iron on lab (slot 0,0):",
                                                                     "  x"]):
            lines = lab.measure(r, self.game, "iron", 1)
        self.assertEqual(len(said), 1)
        self.assertIn("requester-chest", said[0])
        self.assertIn("requesters topped up first: iron-ore 400", lines[0])
        with self.assertRaises(lab.LabError):
            lab.measure(r, self.game, "nope", 1)

    def test_a_lab_surface_in_game_takes_nothing_over(self):
        # 2.0.3: the first .surface / .build.fkb alphabetically was the codebase's; 3.1: the lab
        # surface file is the natural thing to have in game\, and load_game skips a free surface
        self.write("game/lab.surface", "surface  lab\nfree\nforce    lab\nterrain  none\n")
        self.write("game/lab.build.fkb", "read_surface lab\n")
        self.assertEqual(surfacemod.load_game(self.game).name, "nauvis")
        sys.path.insert(0, os.path.join(ROOT, "agent"))
        import fk
        with mock.patch.object(fk, "GAME", self.game):
            self.assertEqual(fk._script(), "nauvis.build.fkb")
        # and a workspace prepared then copies that file's properties
        ws, _plot = alone.prepare(self.game, "iron")
        self.assertEqual(surfacemod.load(os.path.join(ws, "lab.surface")).force_name, "lab")


if __name__ == "__main__":
    unittest.main()
