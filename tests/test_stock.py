"""`fk stock` (2.0.18): what the base holds, per item, chests and roboports apart.

Rory, 2026-10-25: "make sure the agent is looking at the items it has, thats how it should tell
things like that it picked up robots and be able to decide on its own a policy for roboports". In
the 0928 run the player needed three Lua probes to find 28 of the kit's 50 logistic robots in a
storage chest, because the base had no command that lists what it holds; its `helpers stock` only
answered about the items it named.
"""
import unittest

from fkcore.freereads import StockRead, stock_lines


def read(chest, port):
    return StockRead("player", "nauvis", 1234, tuple(sorted(chest.items())), tuple(sorted(port.items())))


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


if __name__ == "__main__":
    unittest.main()
