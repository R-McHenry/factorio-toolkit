"""2.0.75: two sealed modules whose frames overlap are a warning (``overlap``), not a stop. Either
module's nets may use the tiles the frames share, and what the other has laid there is in the way.
"""
import unittest

from fkcore import expand, fkp as fkpmod, flow, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

# pa's frame runs x 10..29, pb's x 26..45: they share columns 26..29. pa's output chest stands at
# x 28, so its route must use the shared tiles
TWO = """
module PA size 20x10 {
  c = Chest<requester, item=iron-plate, rate=1> @(1, 1)
  a = Assembler<recipe=iron-gear-wheel> @(8, 1)
  b = Chest<provider> @(18, 5)
  net fe: c -> a
  net g: a -> b
}
module PB size 20x10 {
  c = Chest<requester, item=iron-plate, rate=1> @(6, 5)
  a = Assembler<recipe=iron-gear-wheel> @(10, 5)
  b = Chest<provider> @(16, 5)
  net fe: c -> a
  net g: a -> b
}
pa = PA @(10, 10)
pb = PB @(26, 10)
"""


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def placed(text):
    flat = flat_of(text)
    return flat, expand.expand_factory(flat, CAT)[0]


class OverlapTest(unittest.TestCase):
    def test_the_shared_box_is_found(self):
        flat, lay = placed(TWO)
        # 41-hull: the shared tiles' box and their count (a box overlap's count is its area)
        self.assertEqual(expand.frame_overlaps(flat, lay, CAT), [("pa", "pb", (26, 10, 30, 20), 40)])

    def test_it_is_a_warning_at_place(self):
        flat, lay = placed(TWO)
        checks = flow._overlap_checks("base", flat, lay, CAT)
        self.assertEqual([c.code for c in checks], ["overlap"])
        self.assertIn("pb's share 4x10 tiles at 26,10..29,19", checks[0].msg)
        self.assertNotIn("overlap", flow.Ctx.__dataclass_fields__["stop_on"].default_factory())
        self.assertEqual(fkpmod.invariants(lay, CAT), [])

    def test_both_route_through_the_shared_tiles(self):
        flat, lay = placed(TWO)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})
        self.assertEqual([ln for ln in r.lines if ln.startswith(("crosses-frame", "FRAME"))], [])
        self.assertEqual(route.seal_checks(flat, r.layout, CAT), [])
        shared = [k for k, e in r.layout.entities.items() if e.attrs.get("net") == "pa/g"
                  and k.startswith("~") and 26 <= e.x < 30]
        self.assertTrue(shared)                       # pa's route stands in the shared columns
        self.assertEqual(fkpmod.invariants(r.layout, CAT), [])     # and on none of pb's tiles

    def test_the_other_modules_entities_are_in_the_way(self):
        # pb's chest moved onto the tile beside pa's: pa's route must go round it
        text = TWO.replace("c = Chest<requester, item=iron-plate, rate=1> @(6, 5)",
                           "c = Chest<requester, item=iron-plate, rate=1> @(1, 5)")
        flat, lay = placed(text)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})
        self.assertEqual(fkpmod.invariants(r.layout, CAT), [])
        self.assertNotIn((27, 15), {t for k, e in r.layout.entities.items() if k.startswith("~pa/")
                                    for t in fkpmod.tiles_of(CAT, e)})

    def test_two_entities_on_one_tile_still_stop(self):
        text = TWO.replace("c = Chest<requester, item=iron-plate, rate=1> @(6, 5)",
                           "c = Chest<requester, item=iron-plate, rate=1> @(2, 5)")
        _flat, lay = placed(text)
        problems = fkpmod.invariants(lay, CAT)
        self.assertTrue(any("is already" in p for p in problems), problems)

    def test_a_port_inside_the_other_frame_is_named(self):
        text = """
module PA size 20x10 {
  port gear : out iron-gear-wheel @e5
  c = Chest<requester, item=iron-plate, rate=1> @(1, 1)
  a = Assembler<recipe=iron-gear-wheel> @(8, 1)
  net fe: c -> a
  net g: a -> gear
}
module PB size 20x10 {
  c = Chest<requester, item=iron-plate, rate=1> @(6, 5)
  a = Assembler<recipe=iron-gear-wheel> @(10, 5)
  b = Chest<provider> @(16, 5)
  net fe: c -> a
  net g: a -> b
}
pa = PA @(10, 10)
pb = PB @(26, 10)
box = Chest<provider> @(60, 15)
net out: pa.gear -> box
"""
        flat, lay = placed(text)
        texts = [c.msg for c in flow._overlap_checks("base", flat, lay, CAT)]
        self.assertTrue(any(t.startswith("port gear opens at 30,15, inside pb's frame")
                            for t in texts), texts)

    def test_a_child_inside_its_parent_is_no_overlap(self):
        from tests.test_modules3 import NESTED
        flat, lay = placed(NESTED)
        self.assertEqual(expand.frame_overlaps(flat, lay, CAT), [])


if __name__ == "__main__":
    unittest.main()
