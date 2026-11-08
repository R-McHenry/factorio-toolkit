"""fkcore.robots: roboports over a factory's logistic chests, and the surface's no-robots check."""
import os
import shutil
import tempfile
import unittest

from fkcore import compose, expand, fkp, flow, lang, robots
from fkcore import surface as surfacemod
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()
GEARS = """
inbox = Chest<requester, item=iron-plate, rate=1.25/s> @(2, 2)
gears = AsmRow<n=2, recipe=iron-gear-wheel>           @(6, 2)
box   = Chest<provider>                               @(2, 12)
net plates_in: inbox -> gears
net gear:      gears -> box
"""


def gears_layout():
    f = lang.parse(GEARS, "gears.fk")
    lay, _ = expand.expand_factory(elaborate(f, dict(f.modules), CAT, "gears"), CAT)
    lay.name = "gears"
    return lay


def surface(lay, at, kit=True):
    w, h = lay.size
    text = f"fkp 1 surface nauvis\nplot gears at {at[0]},{at[1]} rot 0 size {w}x{h}\n"
    if kit:
        text += "cover kit robots\ne kit/r0 roboport 8,8\n"
    return compose.compose(fkp.loads(text), {"gears": lay}, CAT)


class RobotsTest(unittest.TestCase):
    def test_one_roboport_covers_the_chests(self):
        lay, rep = robots.apply_robots(gears_layout(), CAT)
        ports = [e for e in lay.entities.values() if e.name == "roboport"]
        self.assertEqual(len(ports), 1)
        self.assertEqual((rep.chests, rep.covered, rep.checks), (2, 2, []))
        self.assertEqual(ports[0].key, "robots/r0")
        self.assertIn("robots", lay.covers)
        self.assertEqual(fkp.invariants(lay, CAT), [])
        again, _ = robots.apply_robots(lay, CAT)                  # a rerun replaces its own
        self.assertEqual(fkp.dumps(again), fkp.dumps(lay))

    def test_a_factory_in_reach_joins_the_kit_network(self):
        lay, _ = robots.apply_robots(gears_layout(), CAT)
        lines, checks = robots.check_surface(surface(lay, (14, -14)), CAT)
        self.assertEqual(checks, [], lines)
        self.assertIn("1 logistic network", lines[0])

    def test_a_factory_out_of_reach_is_reported(self):
        lay, _ = robots.apply_robots(gears_layout(), CAT)
        lines, checks = robots.check_surface(surface(lay, (200, -14)), CAT)
        self.assertTrue(any(c.code == "no-robots" for c in checks), lines)
        self.assertIn("2 logistic networks", lines[0])

    def test_no_kit_roboport_judges_nothing(self):
        lay, _ = robots.apply_robots(gears_layout(), CAT)
        lines, checks = robots.check_surface(surface(lay, (14, -14), kit=False), CAT)
        self.assertEqual(checks, [])
        self.assertIn("nothing to judge against", lines[0])


FAR = ("fkp 1 factory t\nsize 80x12\ninst m Literal at 0,0 rot 0 sig -\n"
       "e m/c0 passive-provider-chest 2.5,2.5\n")


class PinnedRoboportsTest(unittest.TestCase):
    """1.7 (Rory, 2026-10-21: pin and patch): a rebuild keeps the roboports that stand, so the
    robot network doesn't move under a factory that only grew."""

    def own(self, lay):
        return {(e.key, e.name, e.x, e.y) for e in lay.entities.values() if e.owner == "robots"}

    def test_a_pinned_roboport_and_its_chest_stay_and_new_ones_only_fill_gaps(self):
        first, _rep = robots.apply_robots(fkp.loads(FAR), CAT, storage="storage-chest")
        self.assertEqual({k for k, *_r in self.own(first)}, {"robots/r0", "robots/s0"})
        grown = fkp.loads(FAR + "e m/c1 passive-provider-chest 70.5,2.5\n")
        pinned = [e for e in first.entities.values() if e.owner == "robots"]
        out, rep = robots.apply_robots(grown, CAT, storage="storage-chest", pinned=pinned)
        self.assertTrue(self.own(first) <= self.own(out))
        self.assertEqual({k for k, *_r in self.own(out)},
                         {"robots/r0", "robots/s0", "robots/r1", "robots/s1"})
        self.assertEqual((rep.pinned, rep.covered, rep.chests), (1, 2, 2))
        self.assertIn("2 roboports (1 kept where they stand), 2 storage chests", rep.summary())
        self.assertEqual(fkp.invariants(out, CAT), [])

    def test_a_pinned_roboport_that_reaches_no_chest_goes(self):
        far = [fkp.Entity("robots/r0", "roboport", 70, 6), fkp.Entity("robots/s0", "storage-chest",
                                                                       67.5, 4.5)]
        out, rep = robots.apply_robots(fkp.loads(FAR), CAT, storage="storage-chest", pinned=far)
        port, = [e for e in out.entities.values() if e.name == "roboport"]
        self.assertLess(port.x, 30)                               # by the chest, laid anew
        self.assertEqual(rep.pinned, 0)
        self.assertNotIn(("robots/s0", "storage-chest", 67.5, 4.5), self.own(out))

    def test_a_pinned_roboport_under_a_new_entity_goes(self):
        first, _rep = robots.apply_robots(fkp.loads(FAR), CAT)
        port, = [e for e in first.entities.values() if e.name == "roboport"]
        over = fkp.loads(FAR + f"e m/a assembling-machine-1 {port.x - 0.5},{port.y - 0.5} "
                               "recipe=iron-gear-wheel\n")
        out, rep = robots.apply_robots(over, CAT, pinned=[port])
        self.assertEqual(rep.pinned, 0)
        self.assertNotIn((port.x, port.y), {(e.x, e.y) for e in out.entities.values()
                                            if e.name == "roboport"})
        self.assertEqual(fkp.invariants(out, CAT), [])


KIT = [fkp.Entity("kit/r0", "roboport", 8, 8)]


def places(at, rot=0, size=(14, 14)):
    return {"gears": surfacemod.Place("gears", "gears", at[0], at[1], size[0], size[1], rot)}


class SurfaceNetworkTest(unittest.TestCase):
    """1.2 (the 0534 run): cover robots counts the surface's network, as no-robots does. A factory
    whose chests the kit roboport already reaches got a roboport of its own (the stock held 4),
    so the player turned cover robots off."""

    def test_the_kit_network_serves_a_factory_in_its_square(self):
        lay = gears_layout()
        near = robots.served(places((14, -14)), KIT, {"gears": lay}, "gears", CAT)
        self.assertEqual(near, [(-6.0, 22.0, 25.0)])         # the kit's centre, in gears' frame
        out, rep = robots.apply_robots(lay, CAT, served=near, storage="storage-chest")
        self.assertEqual([e for e in out.entities.values() if e.owner == "robots"], [])
        self.assertEqual((rep.chests, rep.covered, rep.served), (2, 2, 2))
        self.assertIn("0 roboports; 2/2 logistic chests inside a logistic area (2 of them in "
                      "the surface network's)", rep.summary())

    def test_out_of_reach_a_roboport_and_a_storage_chest_beside_it(self):
        lay = gears_layout()
        near = robots.served(places((200, -14)), KIT, {"gears": lay}, "gears", CAT)
        self.assertEqual(near, [])
        out, rep = robots.apply_robots(lay, CAT, served=near, storage="storage-chest")
        port, = [e for e in out.entities.values() if e.name == "roboport"]
        chest, = [e for e in out.entities.values() if e.key == "robots/s0"]
        self.assertEqual(chest.name, "storage-chest")
        ring = {(x, y) for x in range(int(port.x) - 3, int(port.x) + 3)
                for y in range(int(port.y) - 3, int(port.y) + 3)} - fkp.tiles_of(CAT, port)
        self.assertIn((int(chest.x), int(chest.y)), ring)       # beside the roboport
        self.assertEqual(fkp.invariants(out, CAT), [])
        self.assertIn("1 roboports, 1 storage chests beside them", rep.summary())
        again, rep2 = robots.apply_robots(out, CAT, served=near, storage="storage-chest")
        self.assertEqual(fkp.dumps(again), fkp.dumps(out))      # a rerun replaces its own
        self.assertEqual(rep2.chests, 2)                         # its own chest is not a chest to serve

    def test_a_turned_plot_gets_the_square_in_its_own_frame(self):
        lay = gears_layout()
        for rot in range(4):
            (fx, fy, _r), = robots.served(places((14, -14), rot), KIT, {"gears": lay}, "gears",
                                          CAT)
            x, y, _d = compose.turn(fx, fy, None, rot, lay.size)
            self.assertEqual((x + 14, y - 14), (8, 8), rot)

    def test_the_flow_counts_the_kit_roboport_of_the_surface_fkp(self):
        d = tempfile.mkdtemp(prefix="fkrobots-")
        self.addCleanup(shutil.rmtree, d, True)
        files = {"gears.fk": GEARS,
                 "nauvis.surface": "surface nauvis\nmode play\nterrain none\n"
                                   "place gears = gears plot 14,-14 20x16\n",
                 "nauvis.fkp": "fkp 1 surface nauvis\ncover kit robots\ne kit/r0 roboport 8,8\n",
                 "nauvis.build.fkb": "read_surface nauvis\nread_terrain none\nelaborate\n"
                                     "place\nroute\ncover robots\nfloorplan\nreport_checks\n"}
        for name, text in files.items():
            with open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        script = os.path.join(d, "nauvis.build.fkb")

        def cover_txt():
            code, ctx = flow.run(script, cat=CAT, echo=lambda _l: None)
            self.assertEqual(code, 0, ctx.log)
            with open(os.path.join(d, "out", "cover_robots.txt"), encoding="utf-8") as fh:
                return fh.read(), ctx

        text, ctx = cover_txt()
        self.assertIn("0 roboports; 2/2 logistic chests inside a logistic area (2 of them in "
                      "the surface network's)", text)
        self.assertFalse([c for _s, c in ctx.checks if c.code == "no-robots"])
        with open(os.path.join(d, "nauvis.surface"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(files["nauvis.surface"].replace("14,-14", "200,-14"))
        text, ctx = cover_txt()
        self.assertIn("1 roboports; 2/2 logistic chests", text)     # 3.0 (U5): no storage chest
        self.assertNotIn("storage chests beside", text)


def standing(x, y, powered=True):
    return robots.Standing("roboport", x, y, 25.0, 55.0, powered)


class StandingReportTest(unittest.TestCase):
    """3.1 (Rory 11-08): an agent that built too many roboports runs ``fk robots`` and sees how
    few would do. A pure read: the surface's roboports against the design's logistic chests."""
    CHESTS = [("nauvis:a/in/c0", "requester-chest", 10.5, 10.5),
              ("nauvis:a/out/c1", "passive-provider-chest", 40.5, 10.5),
              ("nauvis:b/in/c0", "requester-chest", 90.5, 10.5),
              ("nauvis:far/c0", "requester-chest", 300.5, 10.5)]
    # 20,10 and 30,10 both cover c0 and c1; 50,10 covers c1 only; 80,10 covers b/c0; 120,10
    # covers nothing but bridges 80,10 to 160,10, which covers nothing either; 300,10 has no power
    PORTS = [standing(20, 10), standing(30, 10), standing(50, 10), standing(80, 10),
             standing(120, 10), standing(160, 10), standing(300, 10, powered=False)]

    def test_coverage_redundancy_and_a_minimal_set(self):
        rep = robots.report(self.PORTS, self.CHESTS, CAT)
        self.assertEqual((len(rep.standing), len(rep.powered), len(rep.unpowered)), (7, 6, 1))
        self.assertEqual([c[0] for c in rep.uncovered], ["nauvis:far/c0"])    # no power there
        self.assertEqual(rep.networks, 1)
        # one of 20,10 / 30,10 goes, 50,10 goes (c1 has the other), 160,10 reaches no chest and
        # is a leaf; 120,10 would split nothing once 160,10 is gone, and reaches no chest either
        gone = {p.at for p in rep.redundant}
        self.assertEqual(len(rep.redundant), 4, gone)
        self.assertTrue(gone & {"20,10", "30,10"} and not gone >= {"20,10", "30,10"}, gone)
        self.assertTrue({"50,10", "160,10", "120,10"} <= gone, gone)
        self.assertNotIn("80,10", gone)                      # the only one reaching b/c0
        self.assertEqual(len(rep.minimal), 3)                # c0+c1 together, b/c0, far/c0
        lines = rep.lines("nauvis")
        self.assertIn("robots nauvis: 7 roboports stand (6 with power, 1 network); 4 logistic "
                      "chests in the design", lines[0])
        self.assertIn("covered: 3 of 4 chests inside a powered roboport's logistic square; "
                      "uncovered: far/c0 at 300.5,10.5", lines[1])
        self.assertIn("redundant: 4 of the 6 powered", lines[2])
        self.assertIn("2 of them reach no chest", lines[2])
        self.assertIn("minimal: 3 roboports would cover every chest", lines[3])
        self.assertIn("without power: 1 (they serve nothing): 300,10", lines[4])
        self.assertIn("nothing changed", lines[-1])

    def test_a_bridge_between_covering_roboports_is_not_redundant(self):
        # 20,10 covers c0; 120,10 covers a chest of its own; 70,10 covers nothing but joins them
        chests = [self.CHESTS[0], ("nauvis:b/c", "requester-chest", 130.5, 10.5)]
        rep = robots.report([standing(20, 10), standing(70, 10), standing(120, 10)], chests, CAT)
        self.assertEqual(rep.networks, 1)
        self.assertEqual(rep.redundant, [])
        self.assertEqual(len(rep.minimal), 2)

    def test_an_area_cuts_chests_and_the_roboports_that_serve_it(self):
        rep = robots.report(self.PORTS, self.CHESTS, CAT, area=(0, 0, 60, 20))
        self.assertEqual([c[0] for c in rep.chests], ["nauvis:a/in/c0", "nauvis:a/out/c1"])
        self.assertEqual({p.at for p in rep.standing}, {"20,10", "30,10", "50,10", "80,10"})
        self.assertEqual(rep.uncovered, [])
        self.assertIn("area 0,0,60,20", rep.lines("nauvis")[0])
        empty = robots.report(self.PORTS, self.CHESTS, CAT, area=(500, 0, 600, 20))
        self.assertIn("no logistic chest to cover here", empty.lines("nauvis")[1])
        self.assertEqual(empty.minimal, [])

    def test_the_read_rows_and_the_lua(self):
        rows = [["roboport", 8, 8, 25, 55, True], ["roboport", 60, 8, 0, 0, False], ["x"]]
        got = robots.standing_rows(rows, CAT)
        self.assertEqual([(p.at, p.lr, p.cr, p.powered) for p in got],
                         [("8,8", 25.0, 55.0, True), ("60,8", 25.0, 55.0, False)])  # catalog radii
        from fkcore import link
        lua = robots.lua_standing("nauvis", "player", "t")
        link.assert_safe(lua)
        for word in ("create_entity", "destroy", "order_deconstruction", "build_blueprint"):
            self.assertNotIn(word, lua)
        self.assertNotIn("area =", lua)
        self.assertIn("area = {{0.0, 0.0}, {10.0, 10.0}}",
                      robots.lua_standing("nauvis", "player", "t", (0, 0, 10, 10)))


if __name__ == "__main__":
    unittest.main()
