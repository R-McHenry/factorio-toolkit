"""fkcore.pack: a run's mod pack, and water as ground in a pack with landfill (Sea Block)."""
import json
import os
import tempfile
import unittest
from collections import namedtuple
from unittest import mock

from fkcore import link, pack
from fkcore.catalog import Catalog
from fkcore.flow import landfill_tiles
from fkcore.terrain import Terrain

E = namedtuple("E", "name x y dir tiles")
SEABLOCK = os.path.join(pack.DATA, "packs", "seablock", "catalog.json")


def ground():
    return Terrain("nauvis", (0, 0, 10, 10), water=frozenset({(1, 1), (2, 1), (5, 5)}),
                   other=frozenset({(9, 9)}))


class PackTest(unittest.TestCase):
    def test_base_game(self):
        with mock.patch.dict(os.environ, {"FK_PACK": ""}):
            self.assertIsNone(pack.name())
            self.assertIsNone(pack.landfill())
            self.assertEqual(pack.path("catalog.json"), os.path.join(pack.DATA, "catalog.json"))

    def test_seablock(self):
        with mock.patch.dict(os.environ, {"FK_PACK": "seablock"}):
            self.assertEqual(pack.landfill(), "sand-3")           # what a game paste lays
            self.assertEqual(pack.landfill_item(), "landfill-sand")
            self.assertTrue(os.path.exists(pack.path("catalog.json")))

    def test_pack_file_in_the_game_codebase(self):
        env = {k: v for k, v in os.environ.items() if k != "FK_PACK"}
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, env, clear=True):
            here = os.getcwd()
            os.chdir(d)
            try:
                self.assertIsNone(pack.name())
                with open("pack", "w") as fh:
                    fh.write("seablock\n")
                self.assertEqual(pack.name(), "seablock")
                with mock.patch.dict(os.environ, {"FK_PACK": ""}):
                    self.assertIsNone(pack.name())             # the variable wins
            finally:
                os.chdir(here)

    def test_water_blocks_without_landfill(self):
        with mock.patch.dict(os.environ, {"FK_PACK": ""}):
            self.assertEqual(ground().blocked, {(1, 1), (2, 1), (5, 5), (9, 9)})

    def test_water_is_ground_with_landfill(self):
        with mock.patch.dict(os.environ, {"FK_PACK": "seablock"}):
            t = ground()
            self.assertEqual(t.blocked, {(9, 9)})
            self.assertEqual(len(t.water), 3)        # still water, for pumps and reports

    def test_landfill_tiles(self):
        cat = Catalog.load(SEABLOCK)
        t = ground()
        es = [E("small-electric-pole", 1.5, 1.5, 0, ((1, 1),)),
              E("wooden-chest", 3.5, 3.5, 0, ((3, 3),))]
        self.assertEqual(landfill_tiles(es, t, cat), {(1, 1)})

    def test_offshore_pump_keeps_its_water(self):
        cat = Catalog.load(SEABLOCK)
        pump = E("offshore-pump", 5.5, 6.5, 0, ((5, 6), (5, 5)))
        wet = cat.water_tiles(pump.name, pump.x, pump.y, pump.dir)
        self.assertIn((5, 5), wet)                   # the dump has its water_area
        t = Terrain("nauvis", (0, 0, 10, 10), water=frozenset({(5, 5), (5, 6)}))
        self.assertEqual(landfill_tiles([pump], t, cat), {(5, 6)})

    def test_single_ghosts_carry_the_landfill(self):
        for name, want in (("seablock", "sand-3"), ("", None)):
            with mock.patch.dict(os.environ, {"FK_PACK": name}):
                lua = link.lua_ghosts("nauvis", "player", [])
                data = lua.split("helpers.json_to_table(", 1)[1].split(")\n", 1)[0]
                self.assertEqual(json.loads(json.loads(data))["l"], want)


if __name__ == "__main__":
    unittest.main()
