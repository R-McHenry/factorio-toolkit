"""2.1, the documents: the five examples EXAMPLES.md leads with build on paper (elaborate, rates,
place, route, cover power, report_checks), and agent/docs/examples/cells.fk is the kickoff
template's library, so they build where they stand as well as copied into game\\."""
import os
import unittest

from fkcore.elaborate import advice
from tests.test_power_domains import Build

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, "agent", "docs", "examples")
NEW = ("plastic-cell", "library-lines", "ribbon-bus", "power-shed", "mall-loop")
#: check lines no example should have: a net left unrouted or half-laid, or items astray
BAD = ("no-route", "partly-connected", "SPILL", "WRONG-LANE", "TILE_SHARED", "no-source",
       "power-short", "switch-never", "domain-overlap", "copper", "no-wire", "no-signal",
       "CLOG", "SUSHI_SINK", "short-feed", "no-feed", "no-taker", "cannot-carry")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


class ExamplesTest(unittest.TestCase):
    def test_the_examples_cells_are_the_templates(self):
        self.assertEqual(_read(EX, "cells.fk"),
                         _read(ROOT, "kickoff", "template", "game", "cells.fk"))

    def test_each_example_builds(self):
        files = {"cells.fk": _read(EX, "cells.fk")}
        for name in NEW:
            with self.subTest(example=name):
                b = Build(_read(EX, name + ".fk"), size="200x200", files=files)
                self.addCleanup(b.close)
                self.assertEqual(b.code, 0)
                self.assertEqual([c for c in b.checks if c[0] in BAD], [])
                with open(os.path.join(b.dir, "out", "report_checks.txt"),
                          encoding="utf-8") as fh:
                    self.assertIn(" 0 unrouted", fh.read())

    def test_what_examples_md_says(self):
        files = {"cells.fk": _read(EX, "cells.fk")}
        b = Build(_read(EX, "power-shed.fk"), size="200x200", files=files)
        self.addCleanup(b.close)
        self.assertIn("domain labs: cover power-labs", b.cover)
        self.assertIn("copper feed:", b.cover)
        b = Build(_read(EX, "ribbon-bus.fk"), size="200x200", files=files)
        self.addCleanup(b.close)
        with open(os.path.join(b.dir, "out", "route.txt"), encoding="utf-8") as fh:
            self.assertIn("ribbon    plates: 4 belts side by side", fh.read())
        b = Build(_read(EX, "mall-loop.fk"), size="200x200", files=files)
        self.addCleanup(b.close)
        from fkcore.catalog import Catalog
        from fkcore.elaborate import elaborate_file
        flat = elaborate_file(os.path.join(b.dir, "t.fk"), Catalog.load())
        self.assertEqual({n: g[1] for n, g in flat.gates.items()},
                         {"g1/s": 160, "g2/s": 40, "g3/s": 40})
        self.assertEqual([c.code for c in advice(flat) if c.code != "gate-auto"], [])


if __name__ == "__main__":
    unittest.main()
