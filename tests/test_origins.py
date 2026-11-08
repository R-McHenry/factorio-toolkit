"""3.0.1, origins not edges (Rory, 2026-11-08): ``@(x, y, rot r)`` puts an instance's own origin
at (x, y) and turns about it, and a Literal's origin is its file's (0, 0). A turned module or a
blueprint that grows keeps every piece where it was. ``fk migrate-origins`` rewrites a design
written for the corner reading so it lays what it laid before."""
import json
import os
import tempfile
import unittest

from fkcore import expand, lang, origins
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate, elaborate_file

CAT = Catalog.load()

GEARS = """
module Gears size %dx10 {
  c = Chest<requester, item=iron-plate, rate=1> @(1, 1)
  a = Assembler<recipe=iron-gear-wheel> @(8, 1)
  b = Chest<provider> @(18, 5)
}
"""


def laid(text):
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay = expand.expand_factory(flat, CAT)[0]
    return {k: (e.x, e.y) for k, e in lay.entities.items()}


def turned(x, y, rot):
    for _ in range(rot):
        x, y = -y, x
    return x, y


class OriginsTest(unittest.TestCase):
    def test_a_turned_module_turns_about_its_origin(self):
        local = {"ga/c/c0": (1.5, 1.5), "ga/a/m0": (9.5, 2.5), "ga/b/c0": (18.5, 5.5)}
        for rot in range(4):
            got = laid(GEARS % 20 + f"ga = Gears @(40, 40, rot {rot})\n")
            for key, (x, y) in local.items():
                tx, ty = turned(x, y, rot)
                self.assertEqual(got[key], (40 + tx, 40 + ty), (rot, key))

    def test_a_turned_module_that_grows_keeps_its_pieces(self):
        for rot in range(4):
            small = laid(GEARS % 20 + f"ga = Gears @(40, 40, rot {rot})\n")
            big = laid(GEARS % 30 + f"ga = Gears @(40, 40, rot {rot})\n")
            self.assertEqual(small, big, rot)

    def test_nested_turns_compose_about_each_origin(self):
        text = GEARS % 20 + """
module Pair size 40x30 {
  g = Gears @(5, 0, rot 1)
}
p = Pair @(100, 100, rot 2)
"""
        got = laid(text)
        x, y = turned(1.5, 1.5, 1)
        x, y = turned(x + 5, y, 2)
        self.assertEqual(got["p/g/c/c0"], (100 + x, 100 + y))

    def test_a_single_machine_keeps_its_tile(self):
        for rot in range(4):
            got = laid(f"pm = Chest<provider> @(7, 3, rot {rot})\n")
            self.assertEqual(got["pm/c0"], (7.5, 3.5), rot)

    def test_corner_and_origin_hints_are_inverse(self):
        for frame in ((0, 0, 20, 10), (-3, -2, 7, 5)):
            for rot in range(4):
                h = (11, -4, rot)
                self.assertEqual(expand.origin_hint(expand.corner_hint(h, frame), frame), h)

    def test_a_literal_is_placed_by_its_files_origin(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [{"name": "wooden-chest", "x": 5.5, "y": 3.5},
                    {"name": "wooden-chest", "x": 8.5, "y": 3.5}]
            with open(os.path.join(d, "two.json"), "w") as fh:
                json.dump(rows, fh)
            text = 'lit = Literal<file="two.json"> @(100, 100)\n'
            path = os.path.join(d, "main.fk")
            with open(path, "w") as fh:
                fh.write(text)
            flat = elaborate_file(path, CAT)
            lay = expand.expand_factory(flat, CAT)[0]
            got = sorted((e.x, e.y) for e in lay.entities.values())
            self.assertEqual(got, [(105.5, 103.5), (108.5, 103.5)])
            # a chest added west of them moves nothing that stood
            rows.insert(0, {"name": "wooden-chest", "x": 1.5, "y": 3.5})
            with open(os.path.join(d, "two.json"), "w") as fh:
                json.dump(rows, fh)
            flat = elaborate_file(path, CAT)
            lay = expand.expand_factory(flat, CAT)[0]
            got = sorted((e.x, e.y) for e in lay.entities.values())
            self.assertEqual(got, [(101.5, 103.5), (105.5, 103.5), (108.5, 103.5)])

    def test_migrate_keeps_what_a_corner_design_laid(self):
        text = GEARS % 20 + """
module Pair size 40x30 {
  g = Gears @(5, 0, rot 1)
  h = Gears @(5, 12)
}
p = Pair @(100, 100, rot 2)
q = Gears @(0, 50, rot 3)
"""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "main.fk")
            with open(path, "w", newline="\n") as fh:
                fh.write(text)
            expand.ORIGIN_HINTS = False
            try:
                before = laid(text)
            finally:
                expand.ORIGIN_HINTS = True
            texts, _notes = origins.migrate(path, CAT)
            self.assertEqual(list(texts), [os.path.abspath(path)])
            self.assertEqual(laid(texts[os.path.abspath(path)]), before)


if __name__ == "__main__":
    unittest.main()
