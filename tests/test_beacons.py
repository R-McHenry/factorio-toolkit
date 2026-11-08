"""2.1.33 (lab FRICTION 2): beacons in the rate model. A placed beacon reaches a machine whose box
touches the beacon's box grown by 3 tiles; the machine's speed gains 1.5 x its beacons' module
speed x 1/sqrt(n). ``beacons=N`` (``beacon=MODULE``) sets the count where the layout can't say.
Measured on the lab (FRICTION 16): a prod2 assembler-3 in 3 speed2 beacons made ~0.5 red
circuits/s and 0.33 processing units/s."""
import math
import unittest

from fkcore import lang
from fkcore.catalog import Catalog
from fkcore.elaborate import beacon_bonus, elaborate

CAT = Catalog.load()

KINDS = """
kind Asm3   = Machine<entity=assembling-machine-3, modules=productivity-module-2>
kind Beacon = Entity<name=beacon, modules=speed-module-2>
"""


def flat_of(src):
    f = lang.parse(KINDS + src, "<t>")
    return elaborate(f, dict(f.modules), CAT)


def pu_rate(flat, key):
    return flat.machines[key].makes["processing-unit"]


CELL = """
module Cell size 10x3 {
  b = Beacon @(0, 0)
  u = Asm3<recipe=processing-unit> @(5, 0)
}
"""


class BeaconTest(unittest.TestCase):
    def test_the_bonus_is_the_games(self):
        self.assertAlmostEqual(beacon_bonus([["speed-module-2"] * 2]), 0.9)
        self.assertAlmostEqual(beacon_bonus([["speed-module-2"] * 2] * 3),
                               1.5 * 0.5774 * 1.8, places=6)
        self.assertEqual(beacon_bonus([]), 0.0)

    def test_three_beacons_give_the_measured_rate(self):
        flat = flat_of(CELL + """
module Line size 10x9 {
  c0 = Cell @(0, 0)
  c1 = Cell @(0, 3)
  c2 = Cell @(0, 6)
}
line = Line
""")
        self.assertEqual(flat.beacons["line/c1/u/m0"][0], 3)
        self.assertEqual(flat.beacons["line/c1/u/m0"][2], "counted")
        self.assertEqual(flat.beacons["line/c0/u/m0"][0], 2)
        speed = 1.25 * (0.6 + 1.5 * round(1 / math.sqrt(3), 4) * 1.8)
        self.assertAlmostEqual(pu_rate(flat, "line/c1/u/m0"), speed / 10 * 1.24, places=6)
        self.assertAlmostEqual(pu_rate(flat, "line/c1/u/m0"), 0.335, places=2)   # FRICTION 16

    def test_a_beacon_out_of_reach_counts_nothing(self):
        flat = flat_of("""
module Far size 20x3 {
  b = Beacon @(0, 0)
  u = Asm3<recipe=processing-unit> @(6, 0)
}
far = Far
""")
        self.assertEqual(flat.beacons, {})
        self.assertAlmostEqual(pu_rate(flat, "far/u/m0"), 1.25 * 0.6 / 10 * 1.24, places=6)
        near = flat_of("""
module Near size 20x3 {
  b = Beacon @(0, 0)
  u = Asm3<recipe=processing-unit> @(5, 0)
}
near = Near
""")
        # the beacon reaches 3 tiles past its edge: 2 free tiles between is in, 3 is out
        self.assertEqual(near.beacons["near/u/m0"][0], 1)

    def test_a_turned_module_counts_the_same(self):
        flat = flat_of(CELL + "c = Cell @(10, 10, rot 2)\n")
        self.assertEqual(flat.beacons["c/u/m0"][0], 1)

    def test_beacons_in_another_unplaced_module_are_not_counted(self):
        flat = flat_of(CELL.replace("  b = Beacon @(0, 0)\n", "") + """
module Bs size 3x3 {
  b = Beacon @(0, 0)
}
c = Cell
bs = Bs
""")
        self.assertEqual(flat.beacons, {})

    def test_beacons_set_on_an_instance(self):
        flat = flat_of("""
b = Beacon @(40, 40)
u = Asm3<recipe=processing-unit, beacons=8>
v = Asm3<recipe=processing-unit, beacons=8, beacon=speed-module-3>
""")
        self.assertEqual(flat.beacons["u/m0"], (8, round(1.5 * round(1 / math.sqrt(8), 4) * 4.8,
                                                         4), "set"))
        self.assertEqual(flat.beacons["v/m0"][0], 8)
        self.assertGreater(pu_rate(flat, "v/m0"), pu_rate(flat, "u/m0"))

    def test_beacons_set_with_no_module_to_take_say_so(self):
        flat = flat_of("u = Asm3<recipe=processing-unit, beacons=8>\n")
        self.assertEqual(flat.beacons, {})
        self.assertIn("beacon=speed-module-2", " ".join(c.msg for c in flat.checks
                                                         if c.code == "beacons"))

    def test_a_bad_count_is_a_line(self):
        flat = flat_of("u = Asm3<recipe=processing-unit, beacons=many, beacon=speed-module-2>\n")
        self.assertIn("a count of beacons", " ".join(c.msg for c in flat.checks
                                                     if c.code == "beacons"))


if __name__ == "__main__":
    unittest.main()
