"""`LANES` (2.0.17): a design that feeds one row from two chests on two belts gets told that one
belt carries both, one lane each.

Rory, 2026-10-25: the 0928 player's smelter "had two separate belts with one lane each, a big red
flag that the new two lane router didnt land". The router works (pairing the nets takes that smelter
from 74 belts to 61); the design never reached for it and the build said nothing.
"""
import unittest

from fkcore import expand, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

TWO_BELTS = """
ore    = Chest<requester, item=iron-ore, rate=2.5/s>   @(2, 2)
coal   = Chest<requester, item=coal, rate=1/s>         @(2, 10)
smelt  = SmelterRow<n=8, recipe=iron-plate>            @(8, 2)
plates = Chest<provider, limit=4>                      @(8, 20)
net ore_:   ore -> smelt
net fuel:   coal -> smelt
net plates: smelt -> plates
"""

ONE_BELT = TWO_BELTS + "lanes ore_ | fuel\n"


def lanes_checks(src):
    f = lang.parse(src, "t.fk")
    return [c for c in elaborate(f, dict(f.modules), CAT, "t").checks if c.code == "LANES"]


class LanesCheckTest(unittest.TestCase):
    def test_two_chest_feeds_are_named(self):
        got = lanes_checks(TWO_BELTS)
        self.assertEqual(len(got), 1, [str(c) for c in got])
        self.assertIn("ore_", got[0].where)
        self.assertIn("fuel", got[0].where)
        self.assertIn("lanes", got[0].msg)

    def test_a_paired_design_is_quiet(self):
        self.assertEqual(lanes_checks(ONE_BELT), [])

    def test_product_belts_are_not_advice(self):
        """Two nets of a design's own machines (not chest feeds) stay its business."""
        src = """
ore   = MinerRow<n=2, resource=iron-ore> @(0, 2)
coal  = MinerRow<n=2, resource=coal>     @(0, 12)
smelt = SmelterRow<n=4, recipe=iron-plate> @(10, 2)
net ore_: ore -> smelt
net fuel: coal -> smelt
"""
        self.assertEqual(lanes_checks(src), [])

    def test_pairing_saves_belts_in_the_route(self):
        """The advice is real: the router lays 13 fewer belts on the same smelter."""
        counts = []
        for src in (TWO_BELTS, ONE_BELT):
            f = lang.parse(src, "t.fk")
            flat = elaborate(f, dict(f.modules), CAT, "t")
            lay, _notes = expand.expand_factory(flat, CAT)
            r = route.route_layout(flat, lay, CAT)
            counts.append(sum(1 for e in r.layout.entities.values()
                              if e.name == "transport-belt"))
        self.assertLess(counts[1], counts[0])


if __name__ == "__main__":
    unittest.main()
