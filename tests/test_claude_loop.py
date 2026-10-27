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
        self.assertIn("1 requester-chest (needs-research", line)
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


def read(**health):
    """A STATUS_LUA read with nothing blocked but ``health`` (the base's health, 2.0.12)."""
    return {"ghosts": [], "research": {"name": "robotics", "pct": 48},
            "robots": {"idle": 15, "all": 15, "logistic": 0}, "health": health}


PLATES = {"iron-plate": {"min": 373, "ever": 90000}, "copper-plate": {"min": 210, "ever": 40000}}


class HealthTest(unittest.TestCase):
    """2.0.12, the solo run: 13:55-16:09 on 2026-10-23 there was no coal, the reactor was out of
    fuel and nothing was made, while the world line spoke of ghosts, robots and research; 5
    logistic robots sat in a storage chest and 500 plastic and 401 sulfur at 14.5,-0.5."""

    def test_the_plates_per_minute(self):
        line, key = claude_loop.status_line(read(plates=PLATES))
        self.assertIn("plates/min: iron 373, copper 210", line)
        self.assertEqual(key, "")
        line, key = claude_loop.status_line(read(plates={
            "iron-plate": {"min": 0, "ever": 0}, "copper-plate": {"min": 0, "ever": 0}}))
        self.assertIn("no plates made yet", line)              # a new map is not a dead base
        self.assertEqual(key, "")

    def test_a_dead_base_leads_the_line_and_blocks(self):
        line, key = claude_loop.status_line(read(
            plates={"iron-plate": {"min": 0, "ever": 90000}, "copper-plate": {"min": 0, "ever": 4e4}},
            fuel={"reactor": {"n": 1, "out": 1}}))
        self.assertTrue(line.startswith("BASE DEAD: no iron or copper plates made in the last "
                                        "minute; REACTOR FUEL OUT; no ghosts wait"), line)
        self.assertEqual(key, "fuel:out,plates:none")
        line, key = claude_loop.status_line(read(plates={
            "iron-plate": {"min": 0, "ever": 9}, "copper-plate": {"min": 12, "ever": 9}}))
        self.assertIn("plates/min: iron 0, copper 12", line)   # one metal still comes
        self.assertEqual(key, "")

    def test_reactor_fuel_low_or_out(self):
        line, key = claude_loop.status_line(read(fuel={"reactor": {"n": 1, "out": 0, "min": 12.4}}))
        self.assertIn("REACTOR FUEL LOW: about 12 min left at full burn", line)
        self.assertEqual(key, "fuel:low")
        line, key = claude_loop.status_line(read(fuel={"reactor": {"n": 1, "out": 0, "min": 140}}))
        self.assertNotIn("FUEL", line)                          # enough: nothing said
        line, key = claude_loop.status_line(read(fuel={"reactor": {"n": 2, "out": 1, "min": 90},
                                                       "boiler": {"n": 10, "out": 3}}))
        self.assertIn("REACTOR FUEL OUT in 1 of 2 reactors", line)
        self.assertIn("3 of 10 boilers without fuel", line)
        self.assertEqual(key, "fuel:out")

    def test_makers_stalled_counted_by_reason(self):
        line, key = claude_loop.status_line(read(makers={"n": 85, "stalled": {
            "item_ingredient_shortage": 10, "full_output": 6, "waiting_for_space_in_destination": 1,
            "no_power": 2, "frozen": 1}}))
        self.assertIn("makers stalled 20 of 85: 10 no ingredients, 7 output full, 2 no power, "
                      "1 frozen", line)
        self.assertEqual(key, "")
        line, _key = claude_loop.status_line(read(makers={"n": 4, "stalled": []}))
        self.assertNotIn("makers", line)

    def test_robots_in_chests(self):
        rb = {"logistic": 5, "construction": 0, "at": {"x": 14, "y": -1}}
        line, key = claude_loop.status_line(read(robots=rb))
        self.assertTrue(line.startswith("ROBOTS IN CHESTS: 5 logistic robots sit in chests, where "
                                        "they do nothing (first at 14,-1), while the network has "
                                        "none of them"), line)
        self.assertEqual(key, "robots:chest")
        st = read(robots=rb)
        st["robots"]["logistic"] = 20                           # spares: a fact, not a block
        line, key = claude_loop.status_line(st)
        self.assertIn("; 5 logistic robots sit in chests, where they do nothing", line)
        self.assertEqual(key, "")

    def test_items_outside_every_logistic_network(self):
        line, key = claude_loop.status_line(read(off={"chests": 2, "items": 901, "top": [
            {"name": "plastic-bar", "n": 500, "x": 14, "y": -1},
            {"name": "sulfur", "n": 401, "x": 14, "y": -1}]}))
        self.assertIn("901 items sit in 2 chests outside every logistic network (500 plastic-bar, "
                      "most at 14,-1; 401 sulfur, most at 14,-1)", line)
        self.assertEqual(key, "")
        line, _key = claude_loop.status_line(read(off={"chests": 0, "items": 0, "top": []}))
        self.assertNotIn("outside", line)

    def test_a_failed_health_read_leaves_the_line_as_before(self):
        before = claude_loop.status_line({"ghosts": [], "research": {"name": "x", "pct": 1}})
        self.assertEqual(claude_loop.status_line(
            {"ghosts": [], "research": {"name": "x", "pct": 1},
             "health": {"error": "attempt to index a nil value"}}), before)
        self.assertEqual(claude_loop.status_line(
            {"ghosts": [], "research": {"name": "x", "pct": 1}, "health": []}), before)

    def test_the_read_runs_its_health_part_in_a_pcall(self):
        lua = claude_loop.STATUS_LUA
        self.assertIn("local ok, health = pcall(function()", lua)
        self.assertIn("health = ok and health or {error = tostring(health)}", lua)


if __name__ == "__main__":
    unittest.main()
