"""49-pairleak (Rory, 2026-11-09, the T6 lab field: "the different materials are getting mixed
onto one lane"): two nets that meet at a cell's paired port are one belt wherever they go (the
implied ``lanes A | B``); a net of them that also ends at a one-item belt end is served from that
belt by a splitter with both lanes. The elaborator says so (``pair-leak``); a paired pass-through
draws nothing."""
import unittest

from fkcore import lang
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

CELL = """
module Cell size 3x3 {
  port i : in iron-plate | copper-plate @s1
  port o : out iron-plate | copper-plate @n1
  stack i -> o
  box = Chest<provider> @(1, 1)
  net a items iron-plate: i -> box, o
  net c items copper-plate: i -> box, o
  lanes a | c
}
"""

SPLIT = CELL + """
module Col size 5x8 {
  port a_in  : in  iron-plate @w5
  port a_out : out iron-plate @e5
  port c_in  : in  copper-plate @w6
  port c_out : out copper-plate @e6
  stack a_in -> a_out, c_in -> c_out
  cells = Stack<cell=Cell, n=2> @(1, 0)
  net a: a_in -> cells.i, a_out
  net c: c_in -> cells.i, c_out
}
col = Col @(0, 0)
"""

PAIRED = CELL + """
module Col size 5x8 {
  port ac_in  : in  iron-plate | copper-plate @w5
  port ac_out : out iron-plate | copper-plate @e5
  stack ac_in -> ac_out
  cells = Stack<cell=Cell, n=2> @(1, 0)
  net a items iron-plate:   ac_in -> cells.i, ac_out
  net c items copper-plate: ac_in -> cells.i, ac_out
  lanes a | c
}
col = Col @(0, 0)
"""


def leaks(src):
    f = lang.parse(src)
    flat = elaborate(f, dict(f.modules), CAT, "t")
    return [c for c in flat.checks if c.code == "pair-leak"]


class PairLeakTest(unittest.TestCase):
    def test_one_item_pass_throughs_beside_an_implied_pair_leak(self):
        got = leaks(SPLIT)
        self.assertEqual(sorted(c.where for c in got), ["net col/a", "net col/c"])
        self.assertIn("col.a_out, which takes iron-plate alone", got[0].msg + got[1].msg)
        self.assertIn("copper-plate goes there too", got[0].msg + got[1].msg)

    def test_a_paired_pass_through_draws_nothing(self):
        self.assertEqual(leaks(PAIRED), [])


if __name__ == "__main__":
    unittest.main()
