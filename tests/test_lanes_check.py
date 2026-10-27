"""`LANES` (2.0.17, widened 2.0.50): a design that feeds one row on two belts gets told that one
belt carries both, one lane each.

Rory, 2026-10-25: the 0928 player's smelter "had two separate belts with one lane each, a big red
flag that the new two lane router didnt land". The router works (pairing the nets takes that smelter
from 74 belts to 61); the design never reached for it and the build said nothing.

Rory, 2026-10-27: "we want the paired runs encouraged but that shouldnt also be related to chest
feeding" - 2.0.17 named only pairs a chest drove, so the runs' lab rows (red packs on one belt,
green packs on another) were never told. The rule is about the nets now: any pair of single-item
nets into the same machines, whoever drives them.
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

# the miners drive these two: no chest in sight, and the same waste
TWO_ROWS = """
ore   = MinerRow<n=2, resource=iron-ore> @(0, 2)
coal  = MinerRow<n=2, resource=coal>     @(0, 12)
smelt = SmelterRow<n=4, recipe=iron-plate> @(10, 2)
net ore_: ore -> smelt
net fuel: coal -> smelt
"""

# the runs' lab rows: red packs on one belt, green packs on another (2.0.50)
LAB_ROWS = """
red   = AsmRow<n=2, recipe=automation-science-pack> @(10, 2)
green = AsmRow<n=2, recipe=logistic-science-pack>   @(10, 12)
labs  = LabRow<n=3>                                 @(10, 26)
net packs:      red -> labs
net greenpacks: green -> labs
"""

# a template that side-loads two nets onto its own feed belts needs them apart
SELF_PAIRED = """
ore   = MinerRow<n=2, resource=iron-ore> @(0, 0)
coal  = MinerRow<n=2, resource=coal>     @(0, 12)
smelt = SmelterArray<n=4, recipe=iron-plate> @(8, 4)
net ore_: ore -> smelt
net fuel: coal -> smelt
"""

# two products into one chest: nothing is fed, and one belt of two products buys nothing
TWO_PRODUCTS = """
a = Assembler<recipe=iron-gear-wheel> @(2, 2)
b = Assembler<recipe=copper-cable>    @(2, 10)
c = Chest<provider, limit=4>          @(20, 2)
net ga: a -> c
net ca: b -> c
"""


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

    def test_machine_feeds_are_named_too(self):
        """2.0.50: two rows into one smelter are the same waste as two chests into it."""
        got = lanes_checks(TWO_ROWS)
        self.assertEqual(len(got), 1, [str(c) for c in got])
        self.assertIn("ore_", got[0].where)

    def test_a_lab_row_fed_two_science_rows_is_named(self):
        """The loose end: the runs' lab rows fed red packs and green packs on two belts."""
        got = lanes_checks(LAB_ROWS)
        self.assertEqual(len(got), 1, [str(c) for c in got])
        self.assertIn("packs", got[0].where)
        self.assertIn("labs", got[0].msg)

    def test_a_side_loading_template_is_left_alone(self):
        """SmelterArray (and CircuitStack) side-load two nets onto their own feed belts: pairing
        them would hand the fragment one belt where it needs two."""
        self.assertEqual(lanes_checks(SELF_PAIRED), [])

    def test_two_products_into_a_chest_is_not_a_run(self):
        self.assertEqual(lanes_checks(TWO_PRODUCTS), [])

    def test_an_unbounded_feed_is_not_named(self):
        """A requester without rate= is unbounded: closing it to one lane would throttle it."""
        src = TWO_BELTS.replace("Chest<requester, item=iron-ore, rate=2.5/s>",
                                "Chest<requester, item=iron-ore>")
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
