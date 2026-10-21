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

    def test_labs_that_wait_for_packs(self):
        # the lead world, 10:34: every lab had red and green, none blue
        line, key = claude_loop.status_line({
            "ghosts": [], "research": {"name": "advanced-material-processing-2", "pct": 11},
            "labs": {"n": 6, "short": 6, "lack": {"chemical-science-pack": 6},
                     "makers": {"chemical-science-pack": {"n": 1, "short": 1}}}})
        self.assertIn("RESEARCH STALLED: all 6 labs wait for packs (chemical-science-pack missing "
                      "in 6); 1 of 1 chemical-science-pack makers short of ingredients", line)
        self.assertEqual(key, "labs:stalled")
        # the 2005 run: 8 of 11 wait, research still moves (a fact, not a block)
        line, key = claude_loop.status_line({
            "ghosts": [], "research": {"name": "mining-productivity-2", "pct": 33},
            "labs": {"n": 11, "short": 8, "lack": {"logistic-science-pack": 8},
                     "makers": {"logistic-science-pack": {"n": 4, "short": 4}}}})
        self.assertIn("8 of 11 labs wait for packs (logistic-science-pack missing in 8); 4 of 4 "
                      "logistic-science-pack makers short of ingredients", line)
        self.assertEqual(key, "")
        # every lab busy: nothing to say; Lua's empty tables come back as lists
        line, key = claude_loop.status_line({
            "ghosts": [], "research": {"name": "x", "pct": 1},
            "labs": {"n": 3, "short": 0, "lack": [], "makers": []}})
        self.assertNotIn("labs", line)

    def test_all_reached_says_nothing_more(self):
        line, key = claude_loop.status_line({
            "ghosts": [{"item": "transport-belt", "ghosts": 2, "stock": 10}],
            "research": {"name": "battery", "pct": 3}})
        self.assertNotIn("UNREACHED", line)
        self.assertEqual(key, "")


if __name__ == "__main__":
    unittest.main()
