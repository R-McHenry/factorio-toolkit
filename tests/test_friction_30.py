"""3.0: the opus run's friction (FRICTION-REVIEW-3.0.md, 2026-11-01).

- U9: a module imported by two paths (world.fk and d5.fk both import FurnacePair from cells.fk)
  was "defined twice"; each file is now parsed once per load."""
import os
import shutil
import tempfile
import unittest

from fkcore import elaborate

CELLS = """module Cell size 3x3 {
  port o : out iron-plate @s1
  f = Assembler<recipe=iron-gear-wheel> @(0, 0)
}
"""

A = """import Cell from "cells.fk"
module A size 10x10 {
  port o : out iron-plate @s0
  c = Cell @(2, 2)
}
"""

TOP = """import Cell from "cells.fk"
import A from "a.fk"
a = A @(0, 0)
c2 = Cell @(20, 2)
"""


class DiamondImport(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        for name, text in (("cells.fk", CELLS), ("a.fk", A), ("top.fk", TOP)):
            with open(os.path.join(self.d, name), "w", encoding="utf-8") as fh:
                fh.write(text)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_one_module_by_two_paths(self):
        _f, modules = elaborate.load(os.path.join(self.d, "top.fk"))
        self.assertIn("Cell", modules)
        self.assertIn("A", modules)


if __name__ == "__main__":
    unittest.main()
