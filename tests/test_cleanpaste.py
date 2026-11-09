"""47-cleanpaste (3.2.2): a paste on a free surface lands clean, and comes back clean.

Found pasting the T6 flower on the lab (2026-11-09): a re-routed column's old belts stood on
("kept in the plot until its owner decides"), because the free path of ``apply`` never kept the
record of the toolkit's own entities; and the stand-in mines were requester chests swapped for
infinity chests by Lua after every apply, so every apply put a requester ghost back on them.
"""
import base64
import json
import unittest
import zlib
from unittest import mock

from fkcore import apply as applymod, codec, expand, lang, link, own
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate
from tests.test_apply import FakeRcon, fake_snapshot
from tests.test_sense import surface

CAT = Catalog.load()

SRC = """
ore = Chest<infinity, item=iron-ore, rate=45/s> @(2, 2)
gears = AsmRow<n=2, recipe=iron-gear-wheel>        @(6, 2)
box   = Chest<provider>                            @(2, 12)
net ore_: ore -> gears
net gear: gears -> box
"""


def blueprint_entities(lay):
    text = codec.fkp_to_blueprint(lay, CAT)
    bp = json.loads(zlib.decompress(base64.b64decode(text[1:])))
    return {e["tags"]["src"]: e for e in bp["blueprint"]["entities"]}


class InfinityChestTest(unittest.TestCase):
    def test_an_infinity_chest_is_a_source_with_the_games_settings(self):
        f = lang.parse(SRC, "t.fk")
        flat = elaborate(f, dict(f.modules), CAT, "t")
        lay, _notes = expand.expand_factory(flat, CAT)
        e = lay.entities["ore/c0"]
        self.assertEqual(e.name, "infinity-chest")
        self.assertEqual(e.attrs["item"], "iron-ore")
        self.assertIn("infinity_settings", e.attrs["config"])
        bp = blueprint_entities(lay)["ore/c0"]
        (flt,) = bp["infinity_settings"]["filters"]
        self.assertEqual((flt["name"], flt["mode"], flt["count"]),
                         ("iron-ore", "exactly", expand.INFINITY_COUNT))
        self.assertTrue(bp["infinity_settings"]["remove_unfiltered_items"])


class FreeApplyTest(unittest.TestCase):
    def test_a_free_apply_keeps_the_record_and_destroys_what_the_design_dropped(self):
        s = surface()
        rows = applymod.scope_rows(s, keys=["nauvis:mini/"])
        want = [(r["name"], float(r["x"]), float(r["y"])) for r in rows]
        old = own.Row("nauvis:mini/~old/b0", "transport-belt", 16.5, 1.5, 4, "mini/old")
        rec = own.rows_of(s)
        rec[own.at(old.name, old.x, old.y)] = old
        r = FakeRcon(want)
        with mock.patch.object(link, "snapshot", fake_snapshot(want)):
            rep = applymod.apply(r, s, CAT, keys=["nauvis:mini/"], free=True, own=rec)
        self.assertIsNotNone(rep.own)                             # the record comes back
        self.assertNotIn(own.at(old.name, old.x, old.y), rep.own)  # the dropped belt is gone
        self.assertTrue(set(own.rows_of(s)) <= set(rep.own))      # the design, pasted
        destroys = [c for c in r.calls if "e.destroy()" in c and "transport-belt" in c]
        self.assertEqual(len(destroys), 1)                        # one batch, the old belt
        self.assertIn("16.5", destroys[0])
        self.assertTrue(any("dropped destroyed" in n for n in rep.notes))

    def test_the_destroy_lua_names_each_thing_and_its_ghost(self):
        lua = link.lua_destroy_list("lab", [("transport-belt", 16.5, 1.5), ("pipe", 3.5, 4.5)])
        self.assertIn('{"transport-belt",16.5,1.5}', lua)
        self.assertIn('{"pipe",3.5,4.5}', lua)
        self.assertIn("e.ghost_name == t[1]", lua)
        self.assertIn("rcon.print(n)", lua)


if __name__ == "__main__":
    unittest.main()
