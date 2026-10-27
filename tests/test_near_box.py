"""2.0.45: a net is searched in its own neighbourhood first, then in the whole frame.

Rory, 2026-10-26: "we should be routing a lot of independent small connections so done one at a
time ideally it would be just as fast as what we typically have." The hub search ranked every free
tile of the frame by belt distance from each end, so a short net in a map-sized frame paid for the
whole frame. Now ``_route_one`` tries the box around the net's own ends first and the frame only
when that fails, so bounding never loses a route the frame allowed.
"""
import unittest

from fkcore import expand, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()


def routed(text, blocked=()):
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay, _ = expand.expand_factory(flat, CAT)
    return lay, route.route_layout(flat, lay, CAT, blocked=blocked)


def cell(k, x, y):
    """A requester chest, a gear assembler and a provider chest: two short nets of their own."""
    return (f"q{k} = Chest<requester, item=iron-plate, rate=1> @({x}, {y})\n"
            f"a{k} = Assembler<recipe=iron-gear-wheel> @({x + 6}, {y})\n"
            f"b{k} = Chest<provider> @({x + 14}, {y})\n"
            f"net in{k}: q{k} -> a{k}\nnet out{k}: a{k} -> b{k}\n")


class NearBoxTest(unittest.TestCase):
    def test_the_box_is_the_nets_ends_plus_a_margin_inside_the_frame(self):
        job = route.NetJob("n", starts=[((40, 40), 0)], goals=[((50, 44), 0)])
        m = route._NEAR + 10 // 4
        self.assertEqual(route._near_box(job, (0, 0, 300, 300)),
                         (40 - m, 40 - m, 51 + m, 45 + m))
        self.assertIsNone(route._near_box(job, (35, 35, 60, 50)))     # already the frame

    def test_a_short_net_far_away_is_laid_near_its_ends(self):
        lay, r = routed(cell(0, 0, 0) + cell(1, 200, 160))
        self.assertEqual(r.failed, {})
        self.assertGreater(lay.size[0], 200)
        for k, e in r.layout.entities.items():
            if k.startswith(("~in1/", "~out1/")):
                self.assertTrue(185 <= e.x < 235 and 145 <= e.y < 180, (k, e.x, e.y))

    def test_a_net_walled_off_near_its_ends_falls_back_to_the_frame(self):
        # a wall ten tiles thick (no yellow tunnel spans it) between the chest and the assembler,
        # open only far south, outside the net's own box: the frame-wide search finds the gap
        text = ("q = Chest<requester, item=iron-plate, rate=1> @(4, 40)\n"
                "a = Assembler<recipe=iron-gear-wheel> @(30, 40)\n"
                "far = Chest<provider> @(0, 110)\n"
                "net fe: q -> a\n")
        wall = [(x, y) for x in range(12, 22) for y in range(0, 100)]
        _lay, r = routed(text, blocked=wall)
        self.assertEqual(r.failed, {})
        ys = [e.y for k, e in r.layout.entities.items() if k.startswith("~fe/")]
        self.assertGreater(max(ys), 99)                    # it went round the wall's south end


if __name__ == "__main__":
    unittest.main()
