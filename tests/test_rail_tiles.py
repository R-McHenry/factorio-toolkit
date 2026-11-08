"""2.1.32: a rail piece takes the tiles measured for its direction (fkcore.railtiles). The
catalog's bounding box (curved-rail-b 2x2, north only) let the megaloop's station belts stand on
the next column's curves; the game refused six curves and the stations lost their turns."""
import unittest

from fkcore import railtiles
from fkcore.catalog import Catalog

CAT = Catalog.load()


class RailTilesTest(unittest.TestCase):
    def test_a_curve_takes_its_measured_tiles(self):
        # the megaloop's refused curve: curved-rail-b at 145,35, and the belts laid at y 32.5
        got = CAT.tiles("curved-rail-b", 145.0, 35.0, 14)
        self.assertEqual(len(got), 15)
        self.assertIn((143, 33), got)
        self.assertNotEqual(got, CAT.tiles("curved-rail-b", 145.0, 35.0, 0))
        self.assertEqual(len(CAT.tiles("curved-rail-a", 107.0, 30.0, 8)), 13)

    def test_an_odd_direction_is_the_even_one_below(self):
        for name in ("curved-rail-a", "curved-rail-b", "straight-rail", "half-diagonal-rail"):
            for d in range(0, 16, 2):
                self.assertEqual(CAT.tiles(name, 9.0, 9.0, d + 1), CAT.tiles(name, 9.0, 9.0, d))

    def test_a_straight_rail_is_its_square_and_a_diagonal_is_not(self):
        self.assertEqual(CAT.tiles("straight-rail", 107.0, -9.0, 0),
                         {(106, -10), (107, -10), (106, -9), (107, -9)})
        self.assertEqual(CAT.tiles("straight-rail", 107.0, -9.0, 4),
                         CAT.tiles("straight-rail", 107.0, -9.0, 12))
        self.assertEqual(len(CAT.tiles("straight-rail", 107.0, -9.0, 2)), 8)

    def test_other_entities_keep_their_box(self):
        self.assertIsNone(railtiles.tiles("transport-belt", 0.5, 0.5, 0))
        self.assertEqual(CAT.tiles("assembling-machine-3", 1.5, 1.5, 0),
                         {(x, y) for x in range(3) for y in range(3)})


if __name__ == "__main__":
    unittest.main()
