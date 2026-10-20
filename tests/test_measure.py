"""fkcore.measure against fake reads (no game): matched by position, rated per instance, vs the model."""
import unittest
from unittest import mock

from fkcore import compose, expand, fkp, lang, measure, rates
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()
SRC = """
inbox = Chest<requester, item=iron-plate, rate=1.25/s> @(2, 2)
gears = AsmRow<n=2, recipe=iron-gear-wheel>           @(6, 2)
box   = Chest<provider>                               @(2, 12)
net plates_in: inbox -> gears
net gear:      gears -> box
"""


def setup():
    f = lang.parse(SRC, "gears.fk")
    flat = elaborate(f, dict(f.modules), CAT, "gears")
    lay, _ = expand.expand_factory(flat, CAT)
    lay.name = "gears"
    w, h = lay.size
    surface = fkp.loads(f"fkp 1 surface nauvis\nplot gears at 30,-20 rot 0 size {w}x{h}\n")
    s = compose.compose(surface, {"gears": lay}, CAT)
    return s, {"gears": flat}, {"gears": rates.solve(flat)}


class MeasureTest(unittest.TestCase):
    def test_rates_per_instance_against_the_model(self):
        s, flats, models = setup()
        asm = sorted((e for e in s.entities.values() if e.name == "assembling-machine-1"),
                     key=lambda e: e.key)
        a = {"tick": 1000, "machines": [{"n": e.name, "x": e.x, "y": e.y, "pf": 10,
                                          "rc": "iron-gear-wheel"} for e in asm]}
        # 30 s later: each assembler finished 9 more gears, 0.3/s (the model says 0.3125/s each)
        b = {"tick": 2800, "machines": [{"n": e.name, "x": e.x, "y": e.y, "pf": 19,
                                          "rc": "iron-gear-wheel"} for e in asm]
                                       + [{"n": "assembling-machine-1", "x": 0.5, "y": 0.5,
                                           "pf": 3, "rc": "iron-gear-wheel"}]}       # not designed
        with mock.patch.object(measure, "read", side_effect=[a, b]), \
                mock.patch.object(measure.time, "sleep"):
            got = measure.measure(None, s, CAT, (28, -22, 48, -2), flats, models, seconds=30)
        (row,) = got.rows
        self.assertEqual((row["inst"], row["item"], row["machines"]), ("gears/gears",
                                                                        "iron-gear-wheel", 2))
        self.assertAlmostEqual(row["measured"], 0.6)
        self.assertAlmostEqual(row["model"], 0.625)
        self.assertEqual(got.unmatched, 1)
        self.assertIn("gears/gears", "\n".join(got.lines()))


if __name__ == "__main__":
    unittest.main()
