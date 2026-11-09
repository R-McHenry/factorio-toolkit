"""43-hierarchy (PLAN-ORGANIC D3, the lab's rule "ports in line"): `port-not-in-line`, a check
line, never a gate. A pinned pair port (`a | b`) feeds a belt that must run straight for
``lanephys.STEM`` tiles inside the frame (the stem the router's side-load needs); a child of the
module standing in that line is named with its tiles. The run ends where it meets a child's own
port tile (the column it feeds stands in line) or the frame's edge."""
import unittest

from fkcore import lang, lanephys
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

CELL = """
module Cell size 12x6 {
  port f_in : in iron-plate | copper-plate @wPOS
  BLOCK
  g = Machine<entity=assembling-machine-2, recipe=iron-gear-wheel> @(8, 0)
  m = Machine<entity=assembling-machine-2, recipe=copper-cable> @(8, 3)
  net fe items iron-plate: f_in -> g
  net cu items copper-plate: f_in -> m
  lanes fe | cu
}
"""

OUTSIDE = """
fe = Chest<requester, item=iron-plate, request=50> @(30, 0)
cu = Chest<requester, item=copper-plate, request=50> @(30, 4)
net fe_: fe -> TOP.f_in
net cu_: cu -> TOP.f_in
"""

COL = """
module Col size 16x6 {
  port f_in : in iron-plate | copper-plate @w1
  k = Cell @(AT, 0)
  net fe items iron-plate: f_in -> k.f_in
  net cu items copper-plate: f_in -> k.f_in
  lanes fe | cu
}
"""


def elab(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def lines(flat):
    return [(c.where, c.msg) for c in flat.checks if c.code == "port-not-in-line"]


class PortLineTest(unittest.TestCase):
    def test_a_chest_in_the_stem_is_named(self):
        text = CELL.replace("POS", "1").replace(
            "BLOCK", "cq = Chest<requester, item=stone, request=20> @(2, 1)")
        flat = elab(text + "c = Cell @(0, 0)\n" + OUTSIDE.replace("TOP", "c"))
        got = lines(flat)
        self.assertEqual([w for w, _m in got], ["port c/f_in"])
        self.assertIn(f"a pair's belt runs straight for {lanephys.STEM} tiles inside the frame",
                      got[0][1])
        self.assertIn("@w1 (iron-plate | copper-plate)", got[0][1])
        self.assertIn("2,1 (cq) stands in that line", got[0][1])

    def test_a_free_stem_says_nothing(self):
        flat = elab(CELL.replace("POS", "1").replace("BLOCK", "")
                    + "c = Cell @(0, 0)\n" + OUTSIDE.replace("TOP", "c"))
        self.assertEqual(lines(flat), [])

    def test_a_one_lane_port_is_not_checked(self):
        text = CELL.replace("POS", "1").replace(
            "BLOCK", "cq = Chest<requester, item=stone, request=20> @(2, 1)")
        text = text.replace("in iron-plate | copper-plate @w1", "in iron-plate | iron-plate @w1")
        text = text.replace("net cu items copper-plate: f_in -> m", "net cu: f_in -> m")
        text = text.replace("  lanes fe | cu\n", "")
        text = text.replace("recipe=copper-cable", "recipe=iron-stick")
        flat = elab(text + "c = Cell @(0, 0)\n"
                    "fe = Chest<requester, item=iron-plate, request=50> @(30, 0)\n"
                    "net fe_: fe -> c.f_in\n")
        self.assertEqual(lines(flat), [])          # X | X is one net on both lanes, no pair

    def test_a_column_in_line_is_the_point(self):
        # the child's own port tile ends the run: the pair runs straight into the column
        text = CELL.replace("POS", "1").replace("BLOCK", "") + COL.replace("AT", "3")
        flat = elab(text + "col = Col @(0, 0)\n" + OUTSIDE.replace("TOP", "col"))
        self.assertEqual(lines(flat), [])

    def test_a_column_off_the_line_is_named_with_its_tiles(self):
        # the child's port is on row 2, the parent's on row 1: the child's own body stands in
        # the stem, and is the thing to move
        text = CELL.replace("POS", "2").replace("BLOCK", "") + COL.replace("AT", "2")
        flat = elab(text + "col = Col @(0, 0)\n" + OUTSIDE.replace("TOP", "col"))
        got = lines(flat)
        self.assertEqual([w for w, _m in got], ["port col/f_in"])
        self.assertIn("2,1 (k), 3,1 (k) stand in that line", got[0][1])
        self.assertIn("put the port in line with the column it feeds", got[0][1])


if __name__ == "__main__":
    unittest.main()
