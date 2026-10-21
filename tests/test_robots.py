"""fkcore.robots: roboports over a factory's logistic chests, and the surface's NO_ROBOTS check."""
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
        self.assertTrue(any(c.code == "NO_ROBOTS" for c in checks), lines)
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
    """1.2 (the 0534 run): cover robots counts the surface's network, as NO_ROBOTS does. A factory
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
        self.assertFalse([c for _s, c in ctx.checks if c.code == "NO_ROBOTS"])
        with open(os.path.join(d, "nauvis.surface"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(files["nauvis.surface"].replace("14,-14", "200,-14"))
        text, ctx = cover_txt()
        self.assertIn("1 roboports, 1 storage chests beside them", text)


if __name__ == "__main__":
    unittest.main()
