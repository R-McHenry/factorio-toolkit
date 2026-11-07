"""2.1.32: a megabase grid's route setup worked out every net's ground from every entity, once
for each net. ``_GroundParts`` works out the shared parts once; its answers must be the old ones."""
import unittest

from fkcore import route


class _Job:
    def __init__(self, ends):
        self._ends = ends

    def ends(self):
        return self._ends


class GroundPartsTest(unittest.TestCase):
    def parts(self):
        g = route._GroundParts.__new__(route._GroundParts)
        g.base = {(1, 1), (2, 2)}
        g.parts = [({(3, 3), (4, 4)}, {"a": {(3, 3)}}), ({(5, 5), (3, 3)}, {"b": {(5, 5), (3, 3)}})]
        g.ends = {(6, 6), (7, 7), (2, 2)}
        g.js = {"a": _Job([(7, 7), (2, 2)]), "b": _Job([])}
        return g

    def test_the_view_and_the_set_agree_tile_by_tile(self):
        g = self.parts()
        for net in ("a", "b"):
            full = route._Bounded(g.of(net), (0, 0, 9, 9))
            view = g.grid(net, (0, 0, 9, 9))
            for x in range(-1, 10):
                for y in range(-1, 10):
                    self.assertEqual(full.blocked((x, y)), view.blocked((x, y)), (net, x, y))

    def test_a_nets_own_tiles_are_free_to_it(self):
        g = self.parts()
        self.assertFalse(g.grid("a", (0, 0, 9, 9)).blocked((2, 2)))     # its own end
        self.assertTrue(g.grid("b", (0, 0, 9, 9)).blocked((2, 2)))
        self.assertTrue(g.grid("a", (0, 0, 9, 9)).blocked((3, 3)))      # b's front there too
        self.assertFalse(g.grid("b", (0, 0, 9, 9)).blocked((5, 5)))


if __name__ == "__main__":
    unittest.main()
