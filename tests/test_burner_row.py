"""Burner drills in a MinerRow (Rory, 2026-10-21: the kit stays small, with burner drills added,
so a player that spent its starter plates can still mine). The template took drill= and fuel= before,
but its geometry was the electric drill's 3x3 one, so a burner row failed to expand."""
import unittest

from fkcore import connect, expand, fkp, lang, rates, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

SRC = """
ore   = MinerRow<n=4, resource=iron-ore, drill=burner-mining-drill, fuel=coal> @(4, 2)
coal  = Chest<requester, item=coal, rate=0.5/s> @(0, 2)
smelt = SmelterRow<n=2, recipe=iron-plate> @(4, 12)
box   = Chest<provider, limit=4> @(14, 18)
net ore_: ore -> smelt
net fuel: coal -> ore, smelt
net plates: smelt -> box
"""


class BurnerRowTest(unittest.TestCase):
    def setUp(self):
        f = lang.parse(SRC, "t.fk")
        self.flat = elaborate(f, dict(f.modules), CAT, "t")
        self.lay, _notes = expand.expand_factory(self.flat, CAT)

    def test_it_lays_out_and_routes(self):
        self.assertEqual(fkp.invariants(self.lay, CAT), [])
        drills = [e for e in self.lay.entities.values() if e.name == "burner-mining-drill"]
        self.assertEqual(len(drills), 4)
        self.assertEqual({(e.x, e.y) for e in drills}, {(5, 5), (7, 5), (9, 5), (11, 5)})
        r = route.route_layout(self.flat, self.lay, CAT)
        self.assertEqual(r.failed, {})
        rep = connect.connect(r.layout, CAT, connect.endpoints(self.flat))
        self.assertEqual({n: x.status for n, x in rep.nets.items()},
                         {"fuel": "connected", "ore_": "connected", "plates": "connected"})

    def test_the_rates_count_fuel_and_ore(self):
        m = rates.solve(self.flat)
        # 4 drills at 0.25 ore/s each, 2 stone furnaces take 0.625/s of it
        self.assertAlmostEqual(m.util["ore/m0"], 0.625, places=2)
        coal = self.flat.machines["ore/m0"].takes
        self.assertIn("coal", coal)


if __name__ == "__main__":
    unittest.main()
