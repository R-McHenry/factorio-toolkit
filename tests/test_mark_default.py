"""A sanctioned-space mark with no duration lasts 2h (the surface file's default ``watch sanctioned:
mark``); it expired at its own tick before (worker sense, 2026-10-20)."""
import unittest

from fkcore import sense
from tests.test_sense import AREA, CAT, NETS, TICK, live_as_designed, surface


class MarkDefaultTest(unittest.TestCase):
    def test_a_mark_with_no_duration_lasts_two_hours(self):
        s = surface()
        live = live_as_designed(s)
        belt = {"name": "transport-belt", "type": "transport-belt", "x": 45.5, "y": 3.5,
                "direction": 4, "ghost": False, "force": "player", "last_user": "Rory_618",
                "tiles": [[45, 3]], "items": {}, "ug": None, "recipe": None}
        live = dict(live, things=list(live["things"]) + [belt])
        rep = sense.sense(s, live, CAT, AREA, {"plots": "keep", "sanctioned": "mark"},
                          net_items=NETS)
        (mark,) = rep.marks
        self.assertEqual(mark.until, TICK + 2 * 3600 * 60)
        self.assertIn("marked for 2h", str(next(v for v in rep.verdicts if v.verdict == "MARKED")))


if __name__ == "__main__":
    unittest.main()
