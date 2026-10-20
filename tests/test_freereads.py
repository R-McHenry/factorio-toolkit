"""fkcore.freereads on fixture reads (no game): production statistics and the chart."""
import unittest

from fkcore import freereads

# the shape link.stats wrote on the game host (2026-10-20, the lab force on the lab surface)
STATS = {"tick": 179996, "force": "lab", "surface": "lab", "window": "1h",
         "items": [{"name": "iron-plate", "made_total": 5505, "used_total": 3852,
                    "made_per_min": 91.75, "used_per_min": 64.2000000000000028, "made": 5505,
                    "used": 3852},
                   {"name": "coal", "made_total": 1379, "used_total": 531,
                    "made_per_min": 22.983333333333334, "used_per_min": 8.85, "made": 1379,
                    "used": 531},
                   {"name": "signal-A", "unknown": True}]}


class FreeReadsTest(unittest.TestCase):
    def test_stats(self):
        st = freereads.stats_from(STATS)
        self.assertEqual([r["name"] for r in st.items], ["coal", "iron-plate", "signal-A"])
        lines = freereads.stats_lines(st)
        self.assertEqual(lines[0], "stats lab: force lab, window 1h, tick 179996: 2 items (a free "
                                   "read: never an alert)")
        self.assertEqual(lines[3].split(), ["iron-plate", "91.75", "64.20", "5505", "3852",
                                            "5505", "3852"])
        self.assertEqual(lines[-1], "  signal-A: not an item")
        empty = freereads.stats_from({"tick": 1, "force": "lab", "surface": "lab",
                                      "window": "1min", "items": {}})
        self.assertEqual(freereads.stats_lines(empty), [
            "stats lab: force lab, window 1min, tick 1: 0 items (a free read: never an alert)"])

    def test_chart(self):
        ch = freereads.chart_from({"tick": 180000, "force": "lab", "surface": "lab",
                                   "charted": 193, "chunks": 576, "box": [0, 3, 32, 20]})
        self.assertEqual(freereads.chart_lines(ch), [
            "chart lab: force lab, tick 180000: 193 of 576 generated chunks charted (a free "
            "read: never an alert)",
            "  chunks x 0..32, y 3..20; tiles 0,96 to 1056,672 (1056x576)"])
        none = freereads.chart_from({"tick": 1, "force": "x", "surface": "lab", "charted": 0,
                                     "chunks": 4})
        self.assertEqual(len(freereads.chart_lines(none)), 1)

    def test_windows_are_the_games_precision_indexes(self):
        self.assertEqual(freereads.WINDOWS["1min"], "one_minute")
        self.assertEqual(freereads.WINDOWS["10min"], "ten_minutes")
        self.assertEqual(freereads.WINDOWS["1h"], "one_hour")


if __name__ == "__main__":
    unittest.main()
