"""A multi-item requester on one net (sushi), 2.0.24.

Rory, 2026-10-25: "see if you can figure out if the sushi net warning is working. It looks like the
agent is investigating red herrings after it broke the smelter iron input by putting iron and coal
into one requester on the same net".

Two answers, one test each:

- the warning works: `CLOG` is in the design's checks and in the run's `out/report_checks.txt`;
- the *rate model* did not: a machine driving two items on one net had each item's grant computed
  from the other's (`potential(k, skip=this item)` included the sibling grant), so the two decayed
  geometrically to 0 over 62 passes. The 1133 smelter read 0.000/min with "coal not taken on feed"
  and "iron-ore short on feed" while it was really a 2.5/s smelter with a CLOG risk.
"""
import unittest

from fkcore import lang, rates
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

MIXED = """
feed  = Chest<requester, item="iron-ore,coal", rate=3/s> @(10, 0)
smelt = SmelterRow<n=8, recipe=iron-plate>               @(10, 2)
p1    = Chest<provider, limit=8>                         @(2, 22)
net feed:   feed -> smelt
net plates: smelt -> p1
"""

SPLIT = """
ore   = Chest<requester, item=iron-ore, rate=3/s> @(2, 0)
coal  = Chest<requester, item=coal, rate=1/s>     @(2, 8)
smelt = SmelterRow<n=8, recipe=iron-plate>        @(10, 2)
p1    = Chest<provider, limit=8>                  @(2, 22)
net ore_:   ore -> smelt
net fuel:   coal -> smelt
net plates: smelt -> p1
"""


def model(src):
    f = lang.parse(src, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    return flat, rates.solve(flat)


class SushiRatesTest(unittest.TestCase):
    def test_the_warning_works(self):
        flat, _m = model(MIXED)
        self.assertIn("CLOG", [c.code for c in flat.checks])

    def test_the_mixed_cell_delivers_like_two_chests(self):
        _flat, mixed = model(MIXED)
        _flat2, split = model(SPLIT)
        for other in (mixed, split):
            self.assertAlmostEqual(other.nets[("plates", "iron-plate")].delivered, 2.5, places=3)
            self.assertAlmostEqual(other.util["smelt/m0"], 1.0, places=3)
        # the sushi source supplies each item at its own rate; the coal appetite must not cap iron
        self.assertAlmostEqual(mixed.nets[("feed", "iron-ore")].supply, 3.0, places=3)
        self.assertAlmostEqual(mixed.nets[("feed", "coal")].supply, 3.0, places=3)
        self.assertAlmostEqual(mixed.nets[("feed", "iron-ore")].delivered, 2.5, places=3)
        self.assertAlmostEqual(mixed.nets[("feed", "coal")].delivered, 0.18, places=3)

    def test_the_report_does_not_say_a_consumed_item_is_unwanted(self):
        _flat, mixed = model(MIXED)
        why = rates._why(mixed, "feed/c0")
        self.assertNotIn("not taken", why)


if __name__ == "__main__":
    unittest.main()
