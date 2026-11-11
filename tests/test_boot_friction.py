"""The bootstrap stages' FRICTION.md (lab-session\\fk-boot-w3, 11-11): checks that were missing.

- ``crowded-ends``: six nets ended at one 1x1 chest and two came back ``no-route ... 0 segments``
  with no reason; a 1x1 entity has four side tiles for hands.
- ``report_bom`` says which items nothing built in the design makes (the stages ran on the kit's
  long-handed inserters until they ran out)."""
import json
import os
import shutil
import tempfile
import unittest

from fkcore import flow, lang
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def gears_into_one_chest(n):
    return "box = Chest<provider> @(10, 10)\n" + "".join(
        f"a{i} = Assembler<recipe=iron-gear-wheel> @({i * 5}, 0)\nnet n{i}: a{i} -> box\n"
        for i in range(n))


class CrowdedEndsTest(unittest.TestCase):
    def test_six_nets_into_a_chest_is_said(self):
        got = [str(c) for c in flat_of(gears_into_one_chest(6)).checks
               if c.code == "crowded-ends"]
        self.assertEqual(len(got), 1)
        self.assertIn("6 nets end at this 1x1 passive-provider-chest", got[0])
        self.assertIn("4 side tiles", got[0])
        self.assertIn("Merge nets", got[0])

    def test_four_fit(self):
        self.assertFalse([c for c in flat_of(gears_into_one_chest(4)).checks
                          if c.code == "crowded-ends"])


class NoMakerBomTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkbootfr-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        files = {
            "t.fk": "src = Chest<requester, item=iron-plate, rate=1/s> @(0, 2)\n"
                    "gear = Assembler<recipe=iron-gear-wheel> @(12, 2)\n"
                    "dst = Chest<provider> @(24, 2)\n"
                    "net fe: src -> gear\nnet g: gear -> dst\n",
            "nauvis.surface": "surface nauvis\nterrain none\nplace t = t plot 0,0 34x10\n",
            "stock.json": json.dumps({"transport-belt": 100, "fast-inserter": 1}),
            "nauvis.build.fkb": "read_surface nauvis\nread_terrain none\nelaborate\n"
                                "place --keep pinned\nroute --only stale\nfloorplan\n"
                                "report_bom --stock stock.json\nwrite_layout\n"}
        for name, text in files.items():
            with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)

    def test_the_bill_says_what_nothing_makes(self):
        code, ctx = flow.run(os.path.join(self.dir, "nauvis.build.fkb"), cat=CAT,
                             echo=lambda _l: None)
        self.assertEqual(code, 0, ctx.log)
        with open(os.path.join(self.dir, "out", "report_bom.txt"), encoding="utf-8") as fh:
            bom = fh.read()
        self.assertRegex(bom, r"fast-inserter +\d+  have 1  no maker")
        self.assertIn("items come only from stock or the network", bom)
        short = [str(c) for _s, c in ctx.checks if c.code == "short-stock" and c.where == "fast-inserter"]
        self.assertTrue(short and "nothing built in the design makes it" in short[0])


if __name__ == "__main__":
    unittest.main()
