"""2.1.3, robots that can't reach (the runs of 10-29 to 10-31), as 3.1 leaves it:

- ``REACH`` in report_bom: the ghosts a paste lays out of every construction area that stands or
  that its own roboports give it (the diff's read, this build only);
- the apply's scaffold: no old roboport is held while the network holds none for the design's.
3.1 (Rory 11-08: the world never feeds a step) took out the rest: ``cover robots`` no longer
chains new roboports from the last diff's read, and a moved roboport of the toolkit's is held
like any other old one (``fk robots`` is where standing roboports are judged, tests/test_robots).
The game side is checked on a laptop server (``tools/laptop_server.py fixes``)."""
import inspect
import types
import unittest

from fkcore import apply as applymod
from fkcore import compose, fkp, flow, robots
from fkcore.catalog import Catalog
from fkcore.sense import Verdict

CAT = Catalog.load()
WIDE = ("fkp 1 factory t\nsize 300x20\ninst m Literal at 0,0 rot 0 sig -\n"
        "e m/c0 passive-provider-chest 250.5,10.5\n")


def ports(lay):
    return sorted((float(e.x), float(e.y)) for e in lay.entities.values() if e.name == "roboport")


class CoverIsPureTest(unittest.TestCase):
    def test_the_roboport_goes_by_the_chest_whatever_stands(self):
        # 3.1: nothing of the world comes in; the design says, and a rerun says the same
        out, rep = robots.apply_robots(fkp.loads(WIDE), CAT)
        self.assertEqual(len(ports(out)), 1)
        self.assertGreater(ports(out)[0][0], 200)             # by the chest, wherever it is
        self.assertEqual((rep.covered, rep.checks), (1, []))
        again, _ = robots.apply_robots(fkp.loads(WIDE), CAT)
        self.assertEqual(fkp.dumps(again), fkp.dumps(out))
        for fn in (robots.cover_robots, robots.apply_robots):
            self.assertNotIn("reach", inspect.signature(fn).parameters)
        self.assertFalse(hasattr(robots, "in_frame"))


class ReachTest(unittest.TestCase):
    STANDING = [(0.0, 0.0, 25.0, 55.0)]

    def test_out_of_every_area(self):
        rows = [("a", "wooden-chest", 50.5, 0.5), ("b", "wooden-chest", 60.5, 0.5)]
        self.assertEqual(robots.reach(rows, self.STANDING, CAT), [rows[1]])

    def test_the_paste_roboport_gives_its_area_when_it_joins(self):
        rows = [("b", "wooden-chest", 90.5, 0.5), ("r", "roboport", 48, 0)]
        self.assertEqual(robots.reach(rows, self.STANDING, CAT), [])

    def test_one_built_out_of_its_network_gives_nothing(self):
        # inside the construction area (robots build it) but 52 away: a network of its own
        rows = [("b", "wooden-chest", 90.5, 0.5), ("r", "roboport", 52, 0)]
        self.assertEqual(robots.reach(rows, self.STANDING, CAT), [rows[0]])

    def test_a_roboport_out_of_reach_comes_first(self):
        rows = [("a", "wooden-chest", 200.5, 0.5), ("z", "roboport", 200, 10)]
        self.assertEqual([r[0] for r in robots.reach(rows, self.STANDING, CAT)], ["z", "a"])


def _ctx(verdicts, roboports, free=False):
    sf = types.SimpleNamespace(name="nauvis", free=free)
    return types.SimpleNamespace(last_diff=types.SimpleNamespace(verdicts=verdicts),
                                 roboports=roboports, surface=sf, cat=CAT)


class ReportBomReachTest(unittest.TestCase):
    def test_a_reach_check_names_them(self):
        vs = [Verdict("not-placed", "wooden-chest", 60.5, 0.5, "nauvis:world/c0"),
              Verdict("ghost", "wooden-chest", 10.5, 0.5, "nauvis:world/c1"),
              Verdict("ok", "wooden-chest", 70.5, 0.5, "nauvis:world/c2")]
        lines, check = flow._reach(_ctx(vs, [(0.0, 0.0, 25.0, 55.0)]))
        self.assertEqual(check.code, "REACH")
        self.assertIn("1 of the 2 ghosts the paste lays", check.msg)
        self.assertIn("world/c0", lines[1])
        self.assertTrue(flow._stopping(types.SimpleNamespace(stop_on={"reach"}), [check]))

    def test_nothing_read_nothing_said(self):
        vs = [Verdict("not-placed", "wooden-chest", 600.5, 0.5, "k")]
        self.assertIsNone(flow._reach(_ctx(vs, None)))
        self.assertIsNone(flow._reach(_ctx(vs, [(0.0, 0.0, 25.0, 55.0)], free=True)))
        self.assertIsNone(flow._reach(_ctx(vs, [(600.0, 0.0, 25.0, 55.0)])))


def _design(text):
    return compose.compose(fkp.loads("fkp 1 surface lab\nplot sa at 0,0 rot 0 size 40x20\n"),
                           {"sa": fkp.loads("fkp 1 factory sa\nsize 40x20\n"
                                            "cover robots robots roboport=roboport\n" + text)},
                           CAT)


class ScaffoldTest(unittest.TestCase):
    """1.7: an old roboport stays up until the design's own stand; 10-29: the scaffold's own
    items were what its replacements waited for. 3.1: a moved roboport of the toolkit's is no
    exception any more (2.1.3 had ordered it out at once)."""
    S = _design("e robots/r0 roboport 18,6\n")
    AREA = (0, 0, 40, 20)

    def before(self, action):
        return types.SimpleNamespace(verdicts=[
            Verdict("not-placed", "roboport", 18, 6, "lab:sa/robots/r0"),
            Verdict("unowned", "roboport", 6, 6, None, "", None, action)])

    def test_the_old_rule_holds_it_moved_or_not(self):
        for action in ("revert", "own"):
            b = self.before(action)
            held = applymod.scaffold(b, self.S, CAT, self.AREA)
            self.assertEqual(held, {("roboport", 6, 6)}, action)
            self.assertEqual(applymod._released(b, self.S, CAT, self.AREA, held), {})
        self.assertNotIn("moved", inspect.signature(applymod.scaffold).parameters)
        self.assertFalse(hasattr(applymod, "MOVED_OUT"))

    def test_no_stock_no_scaffold(self):
        b = self.before("revert")
        held = applymod.scaffold(b, self.S, CAT, self.AREA, {"roboport": 0})
        self.assertEqual(held, set())
        self.assertEqual(applymod._released(b, self.S, CAT, self.AREA, held),
                         {applymod.STOCK_OUT: 1})
        self.assertEqual(applymod.scaffold(b, self.S, CAT, self.AREA, {"roboport": 1}),
                         {("roboport", 6, 6)})


if __name__ == "__main__":
    unittest.main()
