import unittest

from fkcore.steiner import Grid, TapSink, grow


class SplitTapTest(unittest.TestCase):
    """2.0.77: the 10-30 run's Sci0 copper. The trunk runs west in the one free row between red1
    (above) and red2 (below); the search cut a splitter one tile short of them and planned red2's
    inserter on the splitter's second tile, so no inserter was laid and red2 still counted
    reached ("partly-connected" on every build)."""

    def test_no_tap_on_the_splitter_it_cuts(self):
        red1, red2 = (994, 1058, 997, 1061), (994, 1062, 997, 1065)
        free = {(x, 1061) for x in range(992, 1010)}
        free |= {(x, y) for x in (991, 992, 993) for y in range(1058, 1066)}
        inside = {(x, y) for x0, y0, x1, y1 in (red1, red2)
                  for x in range(x0, x1) for y in range(y0, y1)}
        blocked = {(x, y) for x in range(985, 1015) for y in range(1052, 1072)} - free
        sinks = [TapSink("red1", red1), TapSink("red2", red2)]
        res = grow(Grid(blocked | inside), (1009, 1061, 3, 0), sinks)
        self.assertEqual(res["problems"], [], res["log"])
        tree = res["tree"]
        self.assertEqual(sorted(t[3] for t in tree.taps), ["red1", "red2"])
        laid = set(tree.tiles())
        for q, _n, _d, _s in tree.taps:
            self.assertEqual(len(tree.tiles()[q]), 1, f"tap {q} shares its tile")
        self.assertTrue(laid)

    def test_problems_names_a_tap_sink_without_its_tap(self):
        red = (4, 0, 7, 3)
        blocked = {(x, y) for x in range(4, 7) for y in range(0, 3)}
        res = grow(Grid(blocked), (0, 4, 1, 0), [TapSink("red", red)])
        self.assertEqual(res["problems"], [])
        res["tree"].taps = []
        self.assertIn("UNTAPPED red: 0 of 1 inserters", res["tree"].problems([TapSink("red", red)]))


if __name__ == "__main__":
    unittest.main()
