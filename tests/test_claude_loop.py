"""The Claude loop's world line (kickoff/claude_loop.py): what blocks the robots, said plainly."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "kickoff"))
import claude_loop  # noqa: E402


class WorldLineTest(unittest.TestCase):
    def test_short_and_locked_ghosts_block(self):
        line, key = claude_loop.status_line({
            "ghosts": [{"item": "gun-turret", "ghosts": 5, "stock": 0},
                       {"item": "requester-chest", "ghosts": 1, "stock": 0, "locked": True},
                       {"item": "transport-belt", "ghosts": 9, "stock": 900}],
            "research": {"name": "robotics", "pct": 40}})
        self.assertIn("15 ghosts wait for the robots", line)
        self.assertIn("5 gun-turret (SHORT", line)
        self.assertIn("1 requester-chest (LOCKED", line)
        self.assertEqual(key, "gun-turret:short,requester-chest:locked")

    def test_ghosts_no_powered_roboport_reaches(self):
        # the 2005 run, 02:10: 32 ghosts just east of the last roboport's construction area
        line, key = claude_loop.status_line({
            "ghosts": [{"item": "transport-belt", "ghosts": 24, "stock": 1107}],
            "unreached": {"n": 32, "first": {"item": "medium-electric-pole", "x": 85, "y": 101}},
            "research": {"name": "battery", "pct": 3}})
        self.assertIn("UNREACHED: 32 of them stand outside every powered roboport's "
                      "construction area", line)
        self.assertIn("medium-electric-pole at 85,101", line)
        self.assertEqual(key, "unreached")

    def test_all_reached_says_nothing_more(self):
        line, key = claude_loop.status_line({
            "ghosts": [{"item": "transport-belt", "ghosts": 2, "stock": 10}],
            "research": {"name": "battery", "pct": 3}})
        self.assertNotIn("UNREACHED", line)
        self.assertEqual(key, "")


if __name__ == "__main__":
    unittest.main()
