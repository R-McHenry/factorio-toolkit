"""2.0.56 (PLAN-CELLS step 3, Rory 2026-10-28: "copy the ore patches from the world into the lab"):
ore on the slot of a module built alone (3.1: a `standin ore`, asked for by name, on the lab or any
free surface): made over an area, copied from a map area of the world, or taken up. Offline:
the Lua and what the calls do with a fake link; the game side was checked on the live lab (the
east iron patch, 668 tiles and 2.37M ore, under a drill row; a rebuild seeds only its gaps)."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from fkcore import alone, link, standin


class LabOreTest(unittest.TestCase):
    def setUp(self):
        self.run = tempfile.mkdtemp(prefix="fklabore-")
        self.addCleanup(shutil.rmtree, self.run, True)
        self.game = os.path.join(self.run, "game")
        os.makedirs(os.path.join(self.run, "lab"))
        os.makedirs(self.game)
        with open(os.path.join(self.run, "lab", "slots.json"), "w", encoding="utf-8") as fh:
            json.dump({"mine": [2000, 800, 200, 200]}, fh)
        os.makedirs(os.path.join(self.run, "lab", "mine"))
        with open(os.path.join(self.run, "lab", "mine", "lab.surface"), "w", encoding="utf-8") as fh:
            fh.write(alone.DEFAULTS["lab"] + "\nplace mine = mine plot 2000,800 20x20\n")

    def fake(self, world=()):
        """A link whose world holds ``world`` [[name, x, y, amount]]; -> (link, the Lua it got)."""
        said = []

        def lua(text):
            said.append(text)
            if "type = 'resource'" in text and "out[#out + 1]" in text:
                inside = [w for w in world if f"'{standin.WORLD}'" in text]
                return json.dumps(inside)
            if "create_entity" in text:
                return str(text.count("],["))       # rows put, near enough for a count
            return "0"
        r = mock.Mock()
        r.lua.side_effect = lua
        return r, said

    def test_the_lua_is_safe_and_writes_only_the_lab(self):
        for text in (standin.lua_ore_clear("lab", (0, 0, 32, 32)),
                     standin.lua_ore_put("lab", [["iron-ore", 1, 2, 5]])):
            link.assert_safe("/sc " + text)
            self.assertIn("'lab'", text)
            self.assertNotIn("nauvis", text)
        read = standin.lua_ore_read("nauvis", (0, 0, 32, 32))
        link.assert_safe("/sc " + read)
        self.assertNotIn("destroy", read)
        self.assertNotIn("create_entity", read)                 # the world is only read

    def test_a_copy_lands_at_the_slot_offset_and_clears_there_first(self):
        world = [["iron-ore", 272, -72, 500], ["iron-ore", 273, -71, 700]]
        r, said = self.fake(world)
        lines = standin.ore(r, self.game, "mine", copy="272,-72,280,-64", to=(4, 2))
        put = [s for s in said if "create_entity" in s]
        self.assertEqual(len(put), 1)
        self.assertIn('["iron-ore",2004,802,500]', put[0])      # slot 2000,800 + to 4,2
        self.assertIn('["iron-ore",2005,803,700]', put[0])
        first_clear = next(i for i, s in enumerate(said) if "e.destroy()" in s)
        self.assertLess(first_clear, said.index(put[0]))
        self.assertIn("iron-ore 2 tiles, 1200 in all", lines[0])

    def test_a_big_area_goes_in_batches(self):
        r, said = self.fake()
        standin.ore(r, self.game, "mine", copy="0,0,100,40")
        reads = [s for s in said if "out[#out + 1]" in s]
        self.assertEqual(len(reads), 4 * 2)                     # 100 x 40 in 32-tile batches

    def test_ore_over_an_area(self):
        r, said = self.fake()
        standin.ore(r, self.game, "mine", resource="copper-ore", area="0,0,3,2", amount=5000)
        put = next(s for s in said if "create_entity" in s)
        self.assertIn('["copper-ore",2000,800,5000]', put)
        self.assertIn('["copper-ore",2002,801,5000]', put)

    def test_refused(self):
        r, _said = self.fake()
        with self.assertRaises(standin.StandinError):
            standin.ore(r, self.game, "other", resource="iron-ore", area="0,0,1,1")   # no slot
        with self.assertRaises(standin.StandinError):
            standin.ore(r, self.game, "mine", copy="0,0,500,10")                     # past the slot
        with self.assertRaises(standin.StandinError):
            standin.ore(r, self.game, "mine", resource="iron-ore", area="5,5,5,9")   # empty

    def test_seeding_keeps_the_ore_there(self):
        text = link.lua_seed("lab", {"iron-ore": [(1, 2)]})
        self.assertIn("count_entities_filtered", text)
        self.assertIn("type = 'resource'", text)


if __name__ == "__main__":
    unittest.main()
