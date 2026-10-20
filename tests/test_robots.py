"""fkcore.robots: roboports over a factory's logistic chests, and the surface's NO_ROBOTS check."""
import unittest

from fkcore import compose, expand, fkp, lang, robots
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()
GEARS = """
inbox = Chest<requester, item=iron-plate, rate=1.25/s> @(2, 2)
gears = AsmRow<n=2, recipe=iron-gear-wheel>           @(6, 2)
box   = Chest<provider>                               @(2, 12)
net plates_in: inbox -> gears
net gear:      gears -> box
"""


def gears_layout():
    f = lang.parse(GEARS, "gears.fk")
    lay, _ = expand.expand_factory(elaborate(f, dict(f.modules), CAT, "gears"), CAT)
    lay.name = "gears"
    return lay


def surface(lay, at, kit=True):
    w, h = lay.size
    text = f"fkp 1 surface nauvis\nplot gears at {at[0]},{at[1]} rot 0 size {w}x{h}\n"
    if kit:
        text += "cover kit robots\ne kit/r0 roboport 8,8\n"
    return compose.compose(fkp.loads(text), {"gears": lay}, CAT)


class RobotsTest(unittest.TestCase):
    def test_one_roboport_covers_the_chests(self):
        lay, rep = robots.apply_robots(gears_layout(), CAT)
        ports = [e for e in lay.entities.values() if e.name == "roboport"]
        self.assertEqual(len(ports), 1)
        self.assertEqual((rep.chests, rep.covered, rep.checks), (2, 2, []))
        self.assertEqual(ports[0].key, "robots/r0")
        self.assertIn("robots", lay.covers)
        self.assertEqual(fkp.invariants(lay, CAT), [])
        again, _ = robots.apply_robots(lay, CAT)                  # a rerun replaces its own
        self.assertEqual(fkp.dumps(again), fkp.dumps(lay))

    def test_a_factory_in_reach_joins_the_kit_network(self):
        lay, _ = robots.apply_robots(gears_layout(), CAT)
        lines, checks = robots.check_surface(surface(lay, (14, -14)), CAT)
        self.assertEqual(checks, [], lines)
        self.assertIn("1 logistic network", lines[0])

    def test_a_factory_out_of_reach_is_reported(self):
        lay, _ = robots.apply_robots(gears_layout(), CAT)
        lines, checks = robots.check_surface(surface(lay, (200, -14)), CAT)
        self.assertTrue(any(c.code == "NO_ROBOTS" for c in checks), lines)
        self.assertIn("2 logistic networks", lines[0])

    def test_no_kit_roboport_judges_nothing(self):
        lay, _ = robots.apply_robots(gears_layout(), CAT)
        lines, checks = robots.check_surface(surface(lay, (14, -14), kit=False), CAT)
        self.assertEqual(checks, [])
        self.assertIn("nothing to judge against", lines[0])


if __name__ == "__main__":
    unittest.main()
