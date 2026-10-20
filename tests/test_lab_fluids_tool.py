"""tools/lab_fluids.py, offline: its lakes cover every offshore pump's water, and every fixture it
touches lies inside the fluids worker's lab region. No game here."""
import importlib.util
import os
import unittest

from fkcore import link
from fkcore.catalog import Catalog

CAT = Catalog.load()
_PATH = os.path.join(os.path.dirname(__file__), "..", "tools", "lab_fluids.py")
_SPEC = importlib.util.spec_from_file_location("lab_fluids", _PATH)
tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tool)


class LabFluidsToolTest(unittest.TestCase):
    def test_the_lakes_are_the_pumps_water(self):
        s = tool.composed(cat=CAT)
        water = {t for ts in tool.lakes().values() for t in ts}
        self.assertTrue(all(tool.inside(x, y) for x, y in water))
        pumps = [e for e in s.entities.values() if e.name == "offshore-pump"]
        self.assertEqual(len(pumps), 2)
        for e in pumps:
            need = CAT.water_tiles(e.name, e.x, e.y, e.dir)
            self.assertTrue(need and need <= water, e.key)
            self.assertNotIn(tuple(e.tiles[0]), water)          # its own tile stays ground
        taken = set(s.tiles)
        self.assertEqual(water & taken, set())                  # nothing designed stands on water

    def test_the_fixtures(self):
        boilers, pipes, machines = tool.fixtures(tool.composed(cat=CAT))
        self.assertEqual(len(boilers), 2)
        self.assertEqual([f for _x, _y, f in pipes], ["petroleum-gas"])
        self.assertEqual(sorted({n for n, _x, _y in machines.values()}),
                         ["boiler", "chemical-plant", "infinity-pipe", "offshore-pump",
                          "steam-engine"])

    def test_its_lua_registers_nothing(self):
        boilers, pipes, machines = tool.fixtures(tool.composed(cat=CAT))
        for lua in (tool.lua_water([(800, 500)]), tool.lua_start(boilers, pipes),
                    tool.lua_sample(machines), tool.lua_empty(machines)):
            link.assert_safe(lua)


if __name__ == "__main__":
    unittest.main()
