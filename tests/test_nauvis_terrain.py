"""games/nauvis-terrain on paper: two factories on the test map's real nauvis terrain (read
2026-10-20): drills on iron-ore#2, routes and poles off the pond and the cliff wall."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from fkcore import connect, fkp, flow, terrain
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate_file

CAT = Catalog.load()
GAME = os.path.join(os.path.dirname(__file__), "..", "games", "nauvis-terrain")
SOURCES = ("nauvis.surface", "nauvis.build.fkb", "iron.fk", "gears.fk", "map.terrain.json")
LAB = os.path.join(os.path.dirname(__file__), "..", "games", "lab-terrain")
LAB_SOURCES = ("lab.surface", "lab.build.fkb", "iron.fk", "gears.fk", "lab.terrain.json")


class NauvisTerrainTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="fknauvisterrain-")
        for name in SOURCES:
            shutil.copy(os.path.join(GAME, name), cls.dir)
        cls.code, cls.ctx = flow.run(os.path.join(cls.dir, "nauvis.build.fkb"), cat=CAT,
                                     echo=lambda _l: None)
        cls.t = terrain.load(os.path.join(cls.dir, "map.terrain.json"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def read(self, name):
        with open(os.path.join(self.dir, "out", name), encoding="utf-8") as fh:
            return fh.read()

    def test_the_terrain_numbers(self):
        t = self.t
        self.assertEqual((t.surface, t.area, len(t.water), len(t.cliffs), len(t.cliff_tiles)),
                         ("nauvis", (-176, 56, 216, 288), 644, 6, 42))
        self.assertEqual([(p.n, len(p.tiles), p.amount) for p in t.patches["iron-ore"]],
                         [(1, 874, 450303), (2, 329, 876377)])

    def test_builds_with_only_the_no_power_lines(self):
        self.assertEqual(self.code, 0, self.ctx.log)
        self.assertEqual(sorted((s, c.code, c.where) for s, c in self.ctx.checks),
                         [("floorplan", "NO_POWER", "nauvis gears"),
                          ("floorplan", "NO_POWER", "nauvis iron")])

    def test_every_drill_on_ore_nothing_on_water_or_cliffs(self):
        s = self.ctx.composed
        self.assertEqual([k for k, e in s.entities.items() if set(e.tiles) & self.t.blocked], [])
        ore = self.t.resources["iron-ore"]
        drills = [e for e in s.entities.values() if e.name == "electric-mining-drill"]
        self.assertEqual(len(drills), 6)
        self.assertTrue(all(all(tile in ore for tile in e.tiles) for e in drills))
        self.assertIn("6/6 drills with ore under every tile, 54 ore tiles under them (289.3k)",
                      self.read("floorplan.txt"))
        self.assertIn("placed ore: @patch(iron-ore) at 13,13 rot 0", self.read("place.txt"))

    def test_nets_connect_and_each_factory_is_one_grid(self):
        for factory in ("iron", "gears"):
            lay = self.ctx.layouts[factory]
            flat = elaborate_file(os.path.join(self.dir, f"{factory}.fk"), CAT)
            rep = connect.connect(lay, CAT, connect.endpoints(flat))
            self.assertEqual({r.status for r in rep.nets.values()}, {"connected"}, factory)
            self.assertEqual(rep.leaks, [])
            self.assertEqual(fkp.invariants(lay, CAT, nets=flat.nets), [])
        cover = self.read("cover_power.txt")
        self.assertIn("38/38 electric entities covered; 1 wire component", cover)
        self.assertIn("5/5 electric entities covered; 1 wire component", cover)

    def test_the_gear_plates_tunnel_under_the_cliff_wall(self):
        s = self.ctx.composed
        ugs = sorted((e.x, e.attrs["ug"]) for k, e in s.entities.items()
                     if k.startswith("nauvis:gears/~plates_in/u"))
        self.assertEqual([u for _x, u in ugs], ["in", "out"])
        self.assertLess(ugs[0][0], 181)                      # the wall is x 181..182
        self.assertGreater(ugs[1][0], 183)


class BadPlacementTest(unittest.TestCase):
    def test_smelters_pinned_in_the_pond_give_on_terrain_and_the_flow_goes_on(self):
        folder = tempfile.mkdtemp(prefix="fknauvisbad-")
        try:
            for name in SOURCES:
                shutil.copy(os.path.join(GAME, name), folder)
            path = os.path.join(folder, "iron.fk")
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(src.replace("@(75, 60)", "@(95, 100)"))     # into the pond's body
            code, ctx = flow.run(os.path.join(folder, "nauvis.build.fkb"), cat=CAT,
                                 echo=lambda _l: None)
            self.assertEqual(code, 0, ctx.log)                     # a check, never a gate
            on = [c for _s, c in ctx.checks if c.code == "ON_TERRAIN"]
            smelt = [c for c in on if c.where.startswith("nauvis:iron/smelt/")]
            # 77 of the row's 100 entities; the rest stand on the shore
            self.assertEqual(len(smelt), 77, [str(c) for c in on][:5])
            self.assertIn("stone-furnace at -72,168 stands on 4 water tiles (first -73,167)",
                          [c.msg for c in smelt])
        finally:
            shutil.rmtree(folder, ignore_errors=True)


def _no_robots(text):
    """A layout without its robot cover: play mode (nauvis) gets roboports for its chests, lab
    mode (the transplant) needs none, so only the terrain's part is compared."""
    return "".join(l for l in text.splitlines(True)
                   if not (l.startswith("e robots/") or l.startswith("cover robots ")))


class LabTerrainTest(unittest.TestCase):
    """games/lab-terrain: the same factories on the terrain transplanted to the lab and read
    back from it (2026-10-20); on paper here (the link is off), so diff and apply skip."""

    def test_the_same_factories_give_the_same_layouts(self):
        folder = tempfile.mkdtemp(prefix="fklabterrain-")
        try:
            for name in LAB_SOURCES:
                shutil.copy(os.path.join(LAB, name), folder)
            with mock.patch.dict(os.environ, {"FK_LINK": "off"}):
                code, ctx = flow.run(os.path.join(folder, "lab.build.fkb"), cat=CAT,
                                     echo=lambda _l: None)
            self.assertEqual(code, 0, ctx.log)
            self.assertEqual(sorted(c.code for _s, c in ctx.checks), ["NO_POWER", "NO_POWER"])
            for factory in ("iron", "gears"):
                with open(os.path.join(folder, f"{factory}.fkp"), encoding="utf-8") as fh:
                    lab = _no_robots(fh.read())
                with open(os.path.join(GAME, f"{factory}.fkp"), encoding="utf-8") as fh:
                    self.assertEqual(lab, _no_robots(fh.read()), factory)
            t = ctx.ground
            self.assertEqual((len(t.water), len(t.cliffs), len(t.resources["iron-ore"])),
                             (644, 6, 329))
        finally:
            shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
