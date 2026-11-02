"""3.0, the pipe material (Rory, 2026-11-02: "the ability to choose material for pipes. this run
would benefit from mostly using copper pipes"): ``route --pipe`` names a material or a pipe entity,
and the pack's ``pipe`` is the default (Sea Block: copper). The base game lays iron pipes."""
import os
import shutil
import tempfile
import unittest

from fkcore import flow, fluid_route
from fkcore import pack as packmod
from fkcore.catalog import Catalog

LIQ = """module Liq size 30x12 {
  p  = OffshorePump @(0, 6, rot 3)
  l  = Machine<entity=angels-liquifier, recipe=angels-water-mineralized> @(22, 5, rot 1)
  net w: p -> l
}
h = Liq @(2, 2)
"""


class PipeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkpipe-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        old = os.environ.get("FK_PACK")
        self.addCleanup(lambda: os.environ.pop("FK_PACK", None) if old is None
                        else os.environ.__setitem__("FK_PACK", old))
        os.environ["FK_PACK"] = "seablock"
        for name, text in (("t.fk", LIQ),
                           ("nauvis.surface", "surface nauvis\nmode play\nterrain none\n"
                                              "place t = t plot 0,0 40x30\n")):
            with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)

    @staticmethod
    def cat():
        return Catalog.load(packmod.path("catalog.json"))      # the pack's, whatever was imported

    def route(self, opt=""):
        with open(os.path.join(self.dir, "nauvis.build.fkb"), "w", encoding="utf-8") as fh:
            fh.write("read_surface nauvis\nread_terrain none\nelaborate\nplace --keep pinned\n"
                     f"route --only stale {opt}\nwrite_layout\n")
        code, ctx = flow.run(os.path.join(self.dir, "nauvis.build.fkb"), cat=self.cat(),
                             echo=lambda _l: None)
        self.assertEqual(code, 0, ctx.log)
        return {e.name for e in ctx.layouts["t"].entities.values() if e.owner == "~h/w"}

    def test_sea_block_lays_copper(self):
        names = self.route()
        self.assertTrue(names)
        self.assertLessEqual(names, {"bob-copper-pipe", "bob-copper-pipe-to-ground"})

    def test_a_material_by_name(self):
        self.assertLessEqual(self.route("--pipe stone"), {"sb-stone-pipe",
                                                          "sb-stone-pipe-to-ground"})

    def test_iron_by_name(self):
        # (a second build would keep the first one's pipes: a route that stands keeps them)
        self.assertLessEqual(self.route("--pipe iron"), {"pipe", "pipe-to-ground"})

    def test_material_words(self):
        cat = self.cat()
        self.assertEqual(fluid_route.material("bob-copper-pipe", cat),
                         ("bob-copper-pipe", "bob-copper-pipe-to-ground"))
        self.assertEqual(fluid_route.material("", cat),
                         ("bob-copper-pipe", "bob-copper-pipe-to-ground"))
        with self.assertRaises(ValueError):
            fluid_route.material("cheese", cat)

    def test_the_base_game_lays_iron(self):
        os.environ.pop("FK_PACK", None)
        self.assertEqual(fluid_route.material("", Catalog.load()), ("pipe", "pipe-to-ground"))


if __name__ == "__main__":
    unittest.main()
