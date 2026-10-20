import os
import re
import shutil
import tempfile
import unittest

from fkcore import compose, connect, fkp, flow
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate_file

CAT = Catalog.load()
GAME = os.path.join(os.path.dirname(__file__), "..", "games", "redgreen")
SOURCES = ("main.fk", "nauvis.surface", "nauvis.build.fkb")


class FlowTest(unittest.TestCase):
    """CORE-V1 step 5: the red-green part of main builds through the default script."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkflow-")
        for name in SOURCES:
            shutil.copy(os.path.join(GAME, name), self.dir)
        self.script = os.path.join(self.dir, "nauvis.build.fkb")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def build(self, frm=None, to=None):
        return flow.run(self.script, frm, to, CAT, echo=lambda _line: None)

    def read(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8") as fh:
            return fh.read()

    def test_the_default_script_builds_redgreen(self):
        code, ctx = self.build()
        self.assertEqual(code, 0, ctx.log)
        self.assertEqual(len(ctx.log), 16)
        self.assertEqual(ctx.checks, [])                        # not one check line in the run
        lay = fkp.load(os.path.join(self.dir, "main.fkp"))
        flat = elaborate_file(os.path.join(self.dir, "main.fk"), CAT)
        self.assertEqual(fkp.invariants(lay, CAT, nets=flat.nets), [])
        rep = connect.connect(lay, CAT, connect.endpoints(flat))
        self.assertEqual({r.status for r in rep.nets.values()}, {"connected"})
        self.assertEqual((len(rep.nets), rep.leaks), (12, []))
        self.assertIn("power", lay.covers)
        self.assertIn("185/185 electric entities covered; 1 wire component",
                      self.read("out/cover_power.txt"))
        for step in ("place", "route", "cover_power", "cover_robots", "floorplan"):
            self.assertTrue(os.path.exists(os.path.join(self.dir, "out", step, "main.fkp")), step)
        surface = fkp.load(os.path.join(self.dir, "nauvis.fkp"))
        s = compose.compose(surface, {"main": lay}, CAT)
        self.assertEqual(s.problems, [])
        self.assertIn("target automation-science-pack 10/min: met", self.read("out/report_rates.txt"))

    def test_a_second_build_pins_everything(self):
        self.build()
        first = self.read("main.fkp")
        code, ctx = self.build()
        self.assertEqual(code, 0)
        self.assertEqual(self.read("main.fkp"), first)
        self.assertIn("14 unchanged", self.read("out/place.txt"))
        self.assertIn("0 routed, 12 kept (12 pinned from the committed .fkp)",
                      self.read("out/route.txt"))

    def test_a_moved_row_reroutes_only_what_it_touches(self):
        self.build()
        path = os.path.join(self.dir, "main.fk")
        src = self.read("main.fk").replace("@(16, 45)", "@(16, 47)")       # labs, 2 tiles down
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(src)
        code, ctx = self.build()
        self.assertEqual(code, 0, ctx.log)
        self.assertIn("labs: stale", self.read("out/place.txt"))
        route_txt = self.read("out/route.txt")
        self.assertIn("routed    packs:", route_txt)
        kept = int(re.search(r"(\d+) kept", route_txt).group(1))
        self.assertGreaterEqual(kept, 10)                     # the rest stay where they were
        self.assertIn("12 nets: 12 connected, 0 open, 0 unrouted; 0 LEAK",
                      self.read("out/report_checks.txt"))

    def test_from_and_to_use_the_checkpoints(self):
        self.build(to="route")
        self.assertFalse(os.path.exists(os.path.join(self.dir, "main.fkp")))
        code, ctx = self.build(frm="cover_power", to="report_checks")
        self.assertEqual(code, 0)
        self.assertEqual([l.split("]")[0] for l in ctx.log], ["[ 8/16", "[ 9/16", "[10/16", "[11/16"])
        self.assertIn("12 connected", self.read("out/report_checks.txt"))

    def test_stop_on_stops_on_a_check(self):
        src = self.read("main.fk").replace("net cable:  cable -> circ\n", "")
        with open(os.path.join(self.dir, "main.fk"), "w", encoding="utf-8") as fh:
            fh.write(src)
        code, ctx = self.build()                              # UNFED is a warning by default
        self.assertEqual(code, 0)
        self.assertTrue(any(c.code == "UNFED" for _s, c in ctx.checks))
        with open(self.script, "a", encoding="utf-8") as fh:
            fh.write("stop_on UNFED\n")
        code, ctx = self.build()
        self.assertEqual(code, 1)
        self.assertTrue(ctx.log[-1].startswith("[ 4/17] elaborate"))

    def test_a_malformed_script_is_refused(self):
        with open(self.script, "a", encoding="utf-8") as fh:
            fh.write("synth_design\n")
        with self.assertRaises(flow.FlowError) as cm:
            self.build()
        self.assertIn("unknown step 'synth_design'", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
