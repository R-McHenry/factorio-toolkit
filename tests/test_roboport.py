"""A roboport as a machine, with the robot feeder the runs before it hand-wrote as a blueprint.

The 0317 and 0928 players each lost a long detour to the same fixture: the kit's logistic robots
come out of a storage chest only into a roboport, and the language had no roboport and no inserter,
so the task ("a chest and an inserter next to the roboport") became a hand-written blueprint
(``codec.blueprint``) read out of the toolkit's own source. With ``Roboport`` a machine, the router
lays the direct inserter between the chest and the roboport like it does between a chest and a lab.
"""
import unittest

from fkcore import connect, expand, fkp, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

SRC = """
port = Roboport @(0, 0)
botin = Chest<requester, item="logistic-robot", request=50, rate=1/s> @(5, 1)
net load: botin -> port
"""


class RoboportTest(unittest.TestCase):
    def setUp(self):
        f = lang.parse(SRC, "t.fk")
        self.flat = elaborate(f, dict(f.modules), CAT, "t")
        self.lay, _notes = expand.expand_factory(self.flat, CAT)

    def test_the_roboport_stands_4x4(self):
        ports = [e for e in self.lay.entities.values() if e.name == "roboport"]
        self.assertEqual(len(ports), 1)
        self.assertEqual((ports[0].x, ports[0].y), (2, 2))

    def test_the_chest_asks_for_robots(self):
        chest = [e for e in self.lay.entities.values() if e.name == "requester-chest"]
        self.assertEqual(len(chest), 1)
        cfg = chest[0].attrs.get("config", "")
        self.assertIn('"name":"logistic-robot"', cfg)
        self.assertIn('"count":50', cfg)

    def test_the_router_lays_the_inserter(self):
        self.assertEqual(fkp.invariants(self.lay, CAT), [])
        r = route.route_layout(self.flat, self.lay, CAT)
        self.assertEqual(r.failed, {})
        hands = [e for e in r.layout.entities.values() if e.name == "fast-inserter"]
        self.assertEqual(len(hands), 1, f"one direct inserter, got {sorted(e.key for e in r.layout.entities.values())}")
        rep = connect.connect(r.layout, CAT, connect.endpoints(self.flat))
        self.assertEqual(rep.nets["load"].status, "connected")


    def test_a_coverage_roboport_is_not_unfed(self):
        """A roboport with no robot net is a coverage roboport; it is not missing an input."""
        f = lang.parse("port = Roboport @(0, 0)\n", "t.fk")
        flat = elaborate(f, dict(f.modules), CAT, "t")
        self.assertEqual([c for c in flat.checks if c.code == "no-feed"], [])


if __name__ == "__main__":
    unittest.main()
