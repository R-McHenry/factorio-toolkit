"""Robot reach without the game (3.4, Rory 2026-11-11: "why wouldn't they just know where all the
roboports are? roboport reach should be easy to do in the toolkit without the game").

read-terrain --entities records every roboport on the surface; floorplan judges every plot's
entities against them (``robots.check_reach``) and ``read_terrain <name> --reach`` blocks the
ground no standing roboport reaches. The bootstrap (FRICTION 11-11) built clean while Sci's feed
belts stood as ghosts past every construction area, and a gated hand outside every logistic area
never fired."""
import os
import shutil
import tempfile
import unittest

from fkcore import compose, flow, robots, terrain
from fkcore.catalog import Catalog
from tests.test_terrain_flow import IRON, SCRIPT, SURFACE, fixture

CAT = Catalog.load()


def _placed(key, name, x, y, attrs=None, plot="f"):
    return compose.Placed(f"nauvis:{plot}/{key}", name, float(x), float(y), 0, dict(attrs or {}),
                          plot, ())


def _surface(*ents):
    s = compose.Surface("nauvis")
    for e in ents:
        s.entities[e.key] = e
    return s


class CheckReachTest(unittest.TestCase):
    STAND = [robots.Standing("roboport", 0.0, 0.0, 25.0, 55.0, True),
             robots.Standing("roboport", -200.0, 0.0, 25.0, 55.0, False)]

    def test_the_designs_own_roboport_joins_and_widens_reach(self):
        s = _surface(_placed("r1", "roboport", 50, 0),
                     _placed("near", "assembling-machine-1", 100.5, 0.5),
                     _placed("far", "assembling-machine-1", 110.5, 0.5))
        lines, checks = robots.check_reach(s, self.STAND, CAT)
        self.assertIn("1 stand with power, 1 without; the design's own add 1", lines[0])
        far = [c for c in checks if c.code == "out-of-reach"]
        self.assertEqual(len(far), 1, [str(c) for c in checks])
        self.assertIn("1 of its 3 entities", far[0].msg)
        self.assertIn("far (assembling-machine-1 110.5,0.5)", far[0].msg)

    def test_an_unpowered_roboport_reaches_nothing(self):
        s = _surface(_placed("a", "assembling-machine-1", -200.5, 0.5))
        _lines, checks = robots.check_reach(s, self.STAND, CAT)
        self.assertEqual([c.code for c in checks], ["out-of-reach"])

    def test_a_gate_or_chest_outside_every_logistic_area(self):
        s = _surface(_placed("box", "passive-provider-chest", 10.5, 0.5),
                     _placed("gate", "inserter", 40.5, 0.5, {"logistic": "construction-robot<20"}),
                     _placed("box2", "requester-chest", 30.5, 0.5))
        _lines, checks = robots.check_reach(s, self.STAND, CAT)
        bad = {c.where.split("/")[-1]: c.msg for c in checks if c.code == "no-robots"}
        self.assertEqual(set(bad), {"gate", "box2"})
        self.assertIn("logistic= gate reads no network", bad["gate"])
        self.assertIn("robots will not serve it", bad["box2"])

    def test_dnp_entities_are_never_judged(self):
        s = _surface(_placed("a", "assembling-machine-1", 300.5, 0.5, {"dnp": "1"}))
        _lines, checks = robots.check_reach(s, self.STAND, CAT)
        self.assertEqual(checks, [])


class ReachFlowTest(unittest.TestCase):
    """The flow on test_terrain_flow's fixture, with roboports in the terrain's entity read."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkreach-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def build(self, ports, script=SCRIPT):
        t = fixture()
        if ports is not None:
            t = terrain.with_entities(t, frozenset(), {"tick": 7, "area": list(t.area),
                                                       "count": 0, "names": {},
                                                       "roboports": ports})
        terrain.save(t, os.path.join(self.dir, "map.terrain.json"))
        for name, text in (("t.surface", SURFACE), ("t.build.fkb", script), ("iron.fk", IRON)):
            with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        _code, ctx = flow.run(os.path.join(self.dir, "t.build.fkb"), cat=CAT,
                              echo=lambda _l: None)
        return ctx

    def read(self, name):
        with open(os.path.join(self.dir, "out", name), encoding="utf-8") as fh:
            return fh.read()

    def test_floorplan_names_the_rows_past_every_roboport(self):
        ctx = self.build([["roboport", 0, 0, 25, 55, True]])
        codes = {(s, c.code) for s, c in ctx.checks}
        self.assertIn(("floorplan", "out-of-reach"), codes)
        far = [c for s, c in ctx.checks if c.code == "out-of-reach"][0]
        self.assertIn("nauvis iron", far.where)
        self.assertIn("iron/out/c0 (passive-provider-chest 72.5,46.5)", far.msg)  # past x 55
        self.assertIn("robots (offline, the roboports read-terrain --entities found at tick 7)",
                      self.read("floorplan.txt"))
        self.assertIn("stop_on out-of-reach", far.msg)

    def test_every_row_in_reach_says_so_and_checks_nothing(self):
        ctx = self.build([["roboport", 40, 40, 25, 55, True]])
        self.assertNotIn("out-of-reach", {c.code for _s, c in ctx.checks})
        self.assertRegex(self.read("floorplan.txt"), r"iron: (\d+)/\1 in a construction area")

    def test_without_a_roboport_read_floorplan_judges_as_before(self):
        ctx = self.build(None)
        self.assertNotIn("out-of-reach", {c.code for _s, c in ctx.checks})
        self.assertIn("robots: no roboport outside the plots", self.read("floorplan.txt"))

    def test_read_terrain_reach_blocks_the_ground_past_every_roboport(self):
        script = SCRIPT.replace("read_terrain    map", "read_terrain    map --reach")
        ctx = self.build([["roboport", 40, 40, 25, 55, True]], script)
        # the area is x -10..110; the roboport builds x -15..95: x 95..109 is blocked, 15 x 100
        self.assertEqual({(x, y) for x in range(95, 110) for y in range(-10, 90)}
                         - set(ctx.ground.blocked), set())
        self.assertNotIn((94, 0), ctx.ground.blocked)
        self.assertIn("--reach: 1500 tiles outside the construction areas of 1 powered "
                      "roboports", self.read("read_terrain.txt"))

    def test_reach_without_roboports_read_blocks_nothing_and_says_so(self):
        script = SCRIPT.replace("read_terrain    map", "read_terrain    map --reach")
        ctx = self.build(None, script)
        self.assertIn(("read_terrain", "no-terrain"), {(s, c.code) for s, c in ctx.checks})



if __name__ == "__main__":
    unittest.main()
