"""Beltless cells (2.0.23): the router lays zero belts and direct inserters when the machines are
1-3 tiles apart.

Rory, 2026-10-25: "can you try in lab to make some test factories that dont use any belts? Lets see
if the router can handle either being forced to use zero belts and only route with inserters, and
also just leave only 1 to 3 tile gaps between buildings so that inserters will be able to reach".

Run in the lab (a laptop server, fk-play scenario) before this test existed: at a 1-tile gap the
router laid 4 fast inserters and no belts; at 2 and 3 tiles, fast ones where one fits and
long-handed ones across the rest, still no belts; every net connected, and the red science cell
measured 6.00/min against a 6.00 model (ratio 1.00) at both gaps. This test keeps it that way
offline: no game, just the layout and the router.
"""
import unittest

from fkcore import expand, fkp, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

CELL = """
fe   = Chest<requester, item=iron-plate, request=400>  @(0, 0)
gear = Assembler<recipe=iron-gear-wheel>                @(2, 0)
red  = Assembler<recipe=automation-science-pack>        @({red}, 0)
lab1 = Lab                                              @({lab}, 0)
cu   = Chest<requester, item=copper-plate, request=200> @({red}, {cu})
net fe:    fe -> gear
net gears: gear -> red
net cu:    cu -> red
net packs: red -> lab1
"""

GAPS = {"1 tile": dict(red=6, lab=10, cu=4),
        "2 tiles": dict(red=7, lab=12, cu=5),
        "3 tiles": dict(red=8, lab=14, cu=6)}


def laid(src):
    f = lang.parse(src, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay, _notes = expand.expand_factory(flat, CAT)
    r = route.route_layout(flat, lay, CAT)
    return flat, r


class BeltlessTest(unittest.TestCase):
    def test_no_belt_anywhere_and_every_net_connected(self):
        for label, cell in GAPS.items():
            with self.subTest(gap=label):
                flat, r = laid(CELL.format(**cell))
                self.assertEqual(r.failed, {}, r.lines)
                belts = [e for e in r.layout.entities.values()
                         if "belt" in e.name or "splitter" in e.name]
                self.assertEqual(belts, [], f"{label}: the router laid belts: {[e.name for e in belts]}")
                hands = [e.name for e in r.layout.entities.values() if "inserter" in e.name]
                self.assertEqual(len(hands), 4, f"{label}: {hands}")   # one per net
                self.assertTrue(all(h in ("inserter", "fast-inserter", "long-handed-inserter")
                                    for h in hands), hands)

    def test_a_one_tile_gap_takes_a_short_hand_and_three_tiles_a_long_one(self):
        _flat, r1 = laid(CELL.format(**GAPS["1 tile"]))
        one = [e.name for e in r1.layout.entities.values() if "inserter" in e.name]
        self.assertEqual(set(one), {"fast-inserter"}, one)
        _flat, r3 = laid(CELL.format(**GAPS["3 tiles"]))
        three = [e.name for e in r3.layout.entities.values() if "inserter" in e.name]
        self.assertIn("long-handed-inserter", three, three)

    def test_the_example_is_beltless(self):
        import os
        path = os.path.join(os.path.dirname(__file__), "..", "agent", "docs", "examples",
                            "beltless.fk")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        _flat, r = laid(src)
        self.assertEqual(r.failed, {})
        self.assertEqual([e for e in r.layout.entities.values() if "belt" in e.name], [])


if __name__ == "__main__":
    unittest.main()
