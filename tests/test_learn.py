"""3.0, a player adds a machine (fkcore.learn, fkcore.learned): ``fk catalog learn`` reads a
building from the game into the run's ``learned.json``, and every design step plans with it.

The fixture ``tests/data/learned/foundry.json`` is ``fk catalog learn foundry electromagnetic-plant
recycler biochamber`` on a Space Age laptop server (2.0.77), its recipes cut to the two the tests
use. The vanilla catalog has rows for these (sizes, speeds) but none of their fluid boxes or
built-in effects, so a foundry can't cast without it."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from fkcore import connect, expand, facts, lang, learn, learned, route
from fkcore.catalog import DEFAULT_PATH, Catalog
from fkcore.elaborate import ElabError, elaborate

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "data", "learned", "foundry.json")

#: a foundry wrapped as a Literal (named f), in a cell: molten iron along the foot, gears back
#: along the head; three stacked, fed from an infinity pipe
LINE = """
module FoundryCell size 5x8 {
  port g_in   : in  iron-gear-wheel @w0
  port g_out  : out iron-gear-wheel @e0
  port mi_in  : in  molten-iron     @w7
  port mi_out : out molten-iron     @e7
  stack g_in -> g_out, mi_in -> mi_out
  m = Literal<file="foundry.json"> @(0, 2)
  net mi: mi_in -> m.f, mi_out
  net g: g_in, m.f -> g_out
}
src = InfinityPipe<fluid=molten-iron> @(0, 10)
line = Stack<cell=FoundryCell, n=3> @(4, 3)
box = Chest<provider> @(24, 3)
net molten: src -> line.mi_in
net gears: line.g_out -> box
"""
FOUNDRY = {"entities": [{"name": "foundry", "x": 2.5, "y": 2.5, "direction": 0,
                         "recipe": "casting-iron-gear-wheel"}], "names": {"f": 0}}

#: what the game's Lua writes for one building (lua_entities): Lua's JSON has {} for an empty list
RAW = {"name": "foundry", "type": "assembling-machine", "w": 5, "h": 5,
       "box": [-2.19921875, -2.19921875, 2.19921875, 2.19921875], "placed_by": ["foundry"],
       "energy": {"source": "electric", "priority": "secondary-input", "drain": 1388.8888888889,
                  "usage": 41666.666666667, "max_usage": 41666.666666667},
       "wire_reach": 9, "crafting_speed": 4,
       "crafting_categories": ["metallurgy", "pressing"], "module_slots": 4,
       "allowed_effects": ["consumption", "productivity"], "base_effect": {"productivity": 0.5},
       "boxes": [{"index": 1, "production": "input", "connections": [
           {"at": [[-1, 2], [-2, -1], [1, -2], [2, 1]], "dir": 8, "flow": "input",
            "type": "normal"}]},
                 {"index": 2, "production": "output", "connections": [
           {"at": [[1, -2], [2, 1], [-1, 2], [-2, -1]], "dir": 0, "flow": "output",
            "type": "normal"}]}],
       "resource_categories": {}}


class OverlayTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fklearn-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_off_by_default_here(self):
        with mock.patch.dict(os.environ, {"FK_LEARNED": ""}):
            self.assertIsNone(learned.path())
            self.assertEqual(Catalog.load().fluid_boxes("foundry"), [])
            self.assertIs(facts.load(), facts.load())            # read once, as before

    def test_found_in_the_folder_fkcore_runs_in(self):
        shutil.copy(FIXTURE, os.path.join(self.dir, learned.NAME))
        here = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, here)
        with mock.patch.dict(os.environ):
            os.environ.pop("FK_LEARNED", None)
            self.assertEqual(os.path.normcase(learned.path()),
                             os.path.normcase(os.path.abspath(learned.NAME)))
            self.assertEqual(len(Catalog.load().fluid_boxes("foundry")), 4)

    def test_layered_over_the_catalog_and_the_facts(self):
        with mock.patch.dict(os.environ, {"FK_LEARNED": FIXTURE}):
            cat = Catalog.load()
            self.assertEqual(len(cat.fluid_boxes("foundry")), 4)
            self.assertEqual(cat.entity("foundry")["module_slots"], 4)
            self.assertEqual(facts.entity("foundry")["base_effect"], {"productivity": 0.5})
            self.assertEqual(facts.entity("biochamber")["fuel_categories"], ["nutrients"])
            # the base's other rows stay
            self.assertEqual(cat.size("assembling-machine-2"), (3, 3))
            self.assertIn("iron-ore", facts.load()["resources"])
            # a fixture loaded by path stays the fixture
            self.assertEqual(Catalog.load(DEFAULT_PATH).fluid_boxes("foundry"), [])
            self.assertNotIn("base_effect", facts.load(facts.PATH)["entities"]["foundry"])

    def test_merge_new_wins_old_stays(self):
        old = {"learned": {"a": "x"}, "entities": [{"name": "a", "v": 1}, {"name": "b", "v": 1}],
               "facts": {"entities": {"a": {"v": 1}}}}
        new = {"learned": {"b": "y"}, "entities": [{"name": "b", "v": 2}],
               "facts": {"entities": {"b": {"v": 2}}}, "version": "2.0.77"}
        got = learned.merge(old, new)
        self.assertEqual({r["name"]: r["v"] for r in got["entities"]}, {"a": 1, "b": 2})
        self.assertEqual(got["facts"]["entities"], {"a": {"v": 1}, "b": {"v": 2}})
        self.assertEqual(got["learned"], {"a": "x", "b": "y"})


class RowsTest(unittest.TestCase):
    def test_a_read_as_the_toolkits_rows(self):
        cat, fb, f = learn.rows(RAW, Catalog.load(DEFAULT_PATH))
        self.assertEqual((cat["tile_width"], cat["crafting_speed"], cat["module_slots"]), (5, 4, 4))
        self.assertEqual(cat["energy"], {"source": "electric", "usage_w": 2500000,
                                         "drain_w": 83333.333, "priority": "secondary-input"})
        self.assertEqual(cat["circuit"], {"connectors": [1, 2], "wire_reach": 9})  # by type
        self.assertEqual(cat["resource_categories"], [])          # Lua's {} is a list again
        self.assertEqual(f["base_effect"], {"productivity": 0.5})
        self.assertEqual(f["energy_w"], 2500000)
        self.assertEqual(f["crafting_categories"], ["metallurgy", "pressing"])
        self.assertEqual([b["production"] for b in fb["boxes"]], ["input", "output"])
        self.assertEqual(fb["size"], [5, 5])

    def test_lua_is_one_chunk_each(self):
        for text in (learn.lua_select(["foundry"], tag="t"), learn.lua_entities(["foundry"], "t"),
                     learn.lua_recipes(["metallurgy"], tag="t")):
            self.assertIn("fk5/t.json", text)
            self.assertNotIn("__TAG__", text)
            self.assertIn("rcon.print(#", text)
            # reads only: no entity built, no surface made
            self.assertNotIn("create_entity", text)
            self.assertNotIn("create_surface", text)


class MachineTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fklearn-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        with open(os.path.join(self.dir, "foundry.json"), "w", encoding="utf-8") as fh:
            json.dump(FOUNDRY, fh)

    def elaborate(self, src):
        path = os.path.join(self.dir, "main.fk")
        f = lang.parse(src, path)
        cat = Catalog.load()
        return elaborate(f, dict(f.modules), cat), cat

    def test_a_foundry_needs_its_fluid_boxes(self):
        with mock.patch.dict(os.environ, {"FK_LEARNED": ""}):
            with self.assertRaises(ElabError) as e:
                self.elaborate("f = Machine<entity=foundry, recipe=casting-iron-gear-wheel> @(0, 0)\n")
        self.assertIn("no-fluidbox", str(e.exception))

    def test_a_learned_foundry_casts_with_its_bonus(self):
        with mock.patch.dict(os.environ, {"FK_LEARNED": FIXTURE}):
            flat, _cat = self.elaborate(
                "f = Machine<entity=foundry, recipe=casting-iron-gear-wheel> @(0, 0)\n")
        m = flat.machines["f/m0"]
        # 4 crafts/s at speed 4, +50% built in: 6 gears/s from 40 molten iron/s
        self.assertAlmostEqual(m.makes["iron-gear-wheel"], 6.0)
        self.assertAlmostEqual(m.needs["molten-iron"], 40.0)

    def test_wrong_category_is_a_check(self):
        with mock.patch.dict(os.environ, {"FK_LEARNED": FIXTURE}):
            flat, _cat = self.elaborate(
                "r = Machine<entity=recycler, recipe=iron-gear-wheel> @(0, 0)\n")
        self.assertEqual([c.code for c in flat.checks if c.code == "wrong-category"],
                         ["wrong-category"])

    def test_a_wrapped_foundry_stacks_routes_and_connects(self):
        with mock.patch.dict(os.environ, {"FK_LEARNED": FIXTURE}):
            flat, cat = self.elaborate(LINE)
            lay, _notes = expand.expand_factory(flat, cat)
            r = route.route_layout(flat, lay, cat)
            rep = connect.connect(r.layout, cat, connect.endpoints(flat),
                                  getattr(flat, "_port_edges", None))
        self.assertEqual(r.failed, {})
        self.assertEqual({n.status for n in rep.nets.values()}, {"connected"})
        self.assertEqual((len(rep.nets), rep.leaks), (12, []))
        names = [e.name for e in r.layout.entities.values()]
        self.assertEqual(names.count("foundry"), 3)
        # each foundry's molten iron comes in on its south side, where its input boxes are
        pipes = {(int(e.x), int(e.y)) for e in r.layout.entities.values() if e.name == "pipe"}
        for e in r.layout.entities.values():
            if e.name == "foundry":
                self.assertTrue({(int(e.x) - 1, int(e.y) + 3), (int(e.x) + 1, int(e.y) + 3)}
                                & pipes, (e.x, e.y))


class ShowForgetTest(unittest.TestCase):
    def test_show_and_forget(self):
        d = tempfile.mkdtemp(prefix="fklearn-")
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, learned.NAME)
        shutil.copy(FIXTURE, p)
        with mock.patch.dict(os.environ, {"FK_LEARNED": p}):
            lines = learn.show(None, p)
            self.assertTrue(any(ln.strip().startswith("foundry: assembling-machine, 5x5")
                                for ln in lines), lines)
            one = learn.show("foundry", p)
            self.assertIn("(learned)", one[0])
            self.assertIn("fluid boxes: 4", "\n".join(one))
            self.assertEqual(learn.forget("foundry", p)[0].split(":")[0], "foundry")
            self.assertNotIn("foundry", learned.load(p)["learned"])
            self.assertIn("(the base catalog)", learn.show("foundry", p)[0])
            self.assertIn("(its recipes use fluids: learn it)", "\n".join(learn.show("foundry", p)))


if __name__ == "__main__":
    unittest.main()
