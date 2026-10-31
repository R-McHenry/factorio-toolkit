"""2.1.2, robots that can't reach (the runs of 10-29 to 10-31):

- ``cover robots`` lays a roboport only where one that stands (or one it lays in reach of them)
  builds it and takes it into its network, chaining toward chests out of reach;
- ``REACH`` in report_bom: the ghosts a paste lays out of every construction area that stands or
  that its own roboports give it;
- the apply's scaffold: a moved roboport of the toolkit's goes, and no old roboport is held while
  the network holds none for the design's.
The game side of each is checked on a laptop server (``tools/laptop_server.py fixes``)."""
import types
import unittest

from fkcore import apply as applymod
from fkcore import compose, fkp, flow, robots
from fkcore import surface as surfacemod
from fkcore.catalog import Catalog
from fkcore.sense import Verdict

CAT = Catalog.load()
WIDE = ("fkp 1 factory t\nsize 300x20\ninst m Literal at 0,0 rot 0 sig -\n"
        "e m/c0 passive-provider-chest 250.5,10.5\n")


def ports(lay):
    return sorted((float(e.x), float(e.y)) for e in lay.entities.values() if e.name == "roboport")


class CoverReachTest(unittest.TestCase):
    def test_without_a_read_nothing_changes(self):
        out, rep = robots.apply_robots(fkp.loads(WIDE), CAT)
        self.assertEqual(len(ports(out)), 1)
        self.assertGreater(ports(out)[0][0], 200)             # by the chest, wherever it is
        again, _ = robots.apply_robots(fkp.loads(WIDE), CAT, reach=None)
        self.assertEqual(fkp.dumps(again), fkp.dumps(out))

    def test_a_chain_from_the_roboport_that_stands(self):
        # the 10-29 run: one laid 52 tiles from the hub made a network with no robots
        standing = [(10.0, 10.0, 25.0, 55.0)]
        out, rep = robots.apply_robots(fkp.loads(WIDE), CAT, reach=standing)
        got = ports(out)
        self.assertGreater(len(got), 1)
        self.assertEqual((rep.covered, rep.checks), (1, []))
        seen = [(10.0, 10.0)]
        for x, y in sorted(got):                               # each joins one before it
            self.assertTrue(any(abs(x - sx) <= 50 and abs(y - sy) <= 50 for sx, sy in seen),
                            (x, y, seen))
            seen.append((x, y))
        self.assertTrue(any(abs(250.5 - x) <= 25 for x, _y in got))
        self.assertEqual(fkp.invariants(out, CAT), [])

    def test_one_in_reach_joins_it(self):
        out, _rep = robots.apply_robots(fkp.loads(WIDE), CAT, reach=[(220.0, 10.0, 25.0, 55.0)])
        (x, y), = ports(out)
        self.assertLessEqual(abs(x - 220), 50)

    def test_nothing_stands_nothing_laid(self):
        out, rep = robots.apply_robots(fkp.loads(WIDE), CAT, reach=[])
        self.assertEqual(ports(out), [])
        self.assertEqual(rep.covered, 0)
        self.assertIn("from a roboport that stands", rep.checks[0].msg)

    def test_the_read_in_the_factory_frame(self):
        lay = fkp.loads(WIDE)
        places = {"t": surfacemod.Place("t", "t", 100, -50, 300, 20, 0)}
        self.assertEqual(robots.in_frame(places, {"t": lay}, "t", [(110, -40, 25, 55)]),
                         [(10.0, 10.0, 25.0, 55.0)])
        self.assertIsNone(robots.in_frame(places, {"t": lay}, "t", None))


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


def _ctx(verdicts, roboports, mode="play"):
    sf = types.SimpleNamespace(name="nauvis", mode=mode)
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
        self.assertIsNone(flow._reach(_ctx(vs, [(0.0, 0.0, 25.0, 55.0)], mode="lab")))
        self.assertIsNone(flow._reach(_ctx(vs, [(600.0, 0.0, 25.0, 55.0)])))


def _design(text):
    return compose.compose(fkp.loads("fkp 1 surface lab\nplot sa at 0,0 rot 0 size 40x20\n"),
                           {"sa": fkp.loads("fkp 1 factory sa\nsize 40x20\n"
                                            "cover robots robots roboport=roboport\n" + text)},
                           CAT)


class ScaffoldTest(unittest.TestCase):
    """10-31: a roboport moved in the design stood after two applies; 10-29: the scaffold's own
    items were what its replacements waited for."""
    S = _design("e robots/r0 roboport 18,6\n")
    AREA = (0, 0, 40, 20)

    def before(self, action):
        return types.SimpleNamespace(verdicts=[
            Verdict("not-placed", "roboport", 18, 6, "lab:sa/robots/r0"),
            Verdict("unowned", "roboport", 6, 6, None, "", None, action)])

    def test_the_old_rule_holds_it(self):
        self.assertEqual(applymod.scaffold(self.before("revert"), self.S, CAT, self.AREA),
                         {("roboport", 6, 6)})
        self.assertEqual(applymod.scaffold(self.before("own"), self.S, CAT, self.AREA,
                                           moved=False), {("roboport", 6, 6)})

    def test_a_moved_roboport_of_the_toolkits_goes(self):
        b = self.before("own")
        held = applymod.scaffold(b, self.S, CAT, self.AREA)
        self.assertEqual(held, set())
        self.assertEqual(applymod._released(b, self.S, CAT, self.AREA, held),
                         {applymod.MOVED_OUT: 1})

    def test_no_stock_no_scaffold(self):
        b = self.before("revert")
        self.assertEqual(applymod.scaffold(b, self.S, CAT, self.AREA, {"roboport": 0}), set())
        self.assertEqual(applymod.scaffold(b, self.S, CAT, self.AREA, {"roboport": 1}),
                         {("roboport", 6, 6)})


if __name__ == "__main__":
    unittest.main()
