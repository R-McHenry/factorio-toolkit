"""The no-rate line (2.0.21) says how much the machines on a rate-less requester take, and points
at `fk stock`.

The 1035 run's smelter was twenty furnaces with four `Chest<requester>` feeds and no `rate=` on any
of them, so every supply read as "unbounded" — which reads as fine — while the base held 144 iron
plates. Rory: "it should be obvious enough for the model to not get it wrong by a factor of ten";
the check now names the demand and the stock read to compare it with, rather than demanding a
target rate.
"""
import unittest

from fkcore import lang
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

SRC = """
ore   = Chest<requester, item=iron-ore> @(0, 2)
coal  = Chest<requester, item=coal>     @(0, 10)
smelt = SmelterRow<n=10, recipe=iron-plate> @(8, 2)
box   = Chest<provider, limit=8>        @(8, 20)
net ore_:   ore -> smelt
net fuel:   coal -> smelt
net plates: smelt -> box
"""


class UnboundedDemandTest(unittest.TestCase):
    def setUp(self):
        f = lang.parse(SRC, "t.fk")
        self.flat = elaborate(f, dict(f.modules), CAT, "t")

    def test_the_line_names_the_demand_and_the_stock_read(self):
        got = [c for c in self.flat.checks if c.code == "no-rate" and c.where == "ore"]
        self.assertEqual(len(got), 1, [str(c) for c in self.flat.checks])
        msg = got[0].msg
        self.assertIn("no rate=", msg)
        self.assertIn("10 machines", msg)
        self.assertIn("3.125/s", msg)          # 10 stone furnaces on 0.3125 ore/s each
        self.assertIn("fk stock", msg)


if __name__ == "__main__":
    unittest.main()
