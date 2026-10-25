"""`fk stock` (2.0.18): what the base holds, per item, chests, roboports and your pack apart.

Rory, 2026-10-25: "make sure the agent is looking at the items it has, thats how it should tell
things like that it picked up robots and be able to decide on its own a policy for roboports". In
the 0928 run the player needed three Lua probes to find 28 of the kit's 50 logistic robots in a
storage chest, because the base had no command that lists what it holds; its `helpers stock` only
answered about the items it named.
"""
import unittest

from fkcore.freereads import StockRead, stock_lines


def read(chest, port, pack=None, flying=None):
    return StockRead("player", "nauvis", 1234, tuple(sorted(chest.items())),
                     tuple(sorted(port.items())), tuple(sorted((pack or {}).items())),
                     tuple(sorted((flying or {}).items())))


class StockLinesTest(unittest.TestCase):
    def test_robots_in_chests_are_named_and_explained(self):
        text = "\n".join(stock_lines(read({"logistic-robot": 28, "iron-plate": 1188},
                                          {"logistic-robot": 22})))
        self.assertIn("logistic-robot", text)
        self.assertIn("22 in roboports, 28 in chests", text)
        self.assertIn("idle", text)
        self.assertIn("iron-plate", text)
        self.assertIn("2 kinds, 1238 items", text)

    def test_no_robot_flying_is_stated(self):
        text = "\n".join(stock_lines(read({"logistic-robot": 50}, {})))
        self.assertIn("no robots in any roboport", text)

    def test_a_full_roboport_fleet_is_quiet(self):
        text = "\n".join(stock_lines(read({}, {"logistic-robot": 50})))
        self.assertNotIn("no robots in any roboport", text)
        self.assertIn("50 in roboports, 0 in chests", text)

    def test_largest_first(self):
        lines = stock_lines(read({"coal": 200, "iron-plate": 1188}, {}))
        self.assertTrue(lines[1].strip().startswith("iron-plate"))
        self.assertTrue(lines[2].strip().startswith("coal"))

    def test_the_pack_is_counted_and_named(self):
        text = "\n".join(stock_lines(read({"iron-plate": 100}, {}, {"iron-plate": 8,
                                                                   "burner-mining-drill": 1})))
        self.assertIn("your pack", text)
        self.assertIn("8 carried", text)
        self.assertIn("burner-mining-drill", text)

    def test_flying_robots_are_not_lost_robots(self):
        """The 1035 player read "4 in roboports" while 46 were in the air and thought they were
        being lost; a flying robot is a working robot."""
        text = "\n".join(stock_lines(read({}, {"logistic-robot": 4}, {},
                                          {"logistic-robot": 46})))
        self.assertIn("46 flying", text)
        self.assertIn("4 in roboports", text)
        self.assertNotIn("no robots in any roboport", text)


if __name__ == "__main__":
    unittest.main()
