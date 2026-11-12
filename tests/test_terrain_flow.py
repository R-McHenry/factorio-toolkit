"""The flow on a fixture terrain: @patch on ore, routes and poles round water and cliffs, and
on-water-or-cliff on a bad placement (a check, never a gate). No game."""
import os
import shutil
import tempfile
import unittest

from fkcore import connect, cover, fkp, flow, route, terrain
from fkcore.catalog import Catalog
from fkcore.elaborate import ADVICE, elaborate_file
from tests.test_nauvis import CHAIN, GAME as NAUVIS, SOURCES as NAUVIS_SOURCES

CAT = Catalog.load()

SURFACE = """\
surface  nauvis
mode     play
terrain  map
catalog  base
place iron = iron plot 0,0 90x70
"""
SCRIPT = """\
read_surface    t
read_terrain    map
elaborate
report_rates
place
route
cover power     --pole medium-electric-pole
floorplan
report_checks
write_layout
stop_on         invariant
"""
# the ore north-west, a lake (x 30..44, y 25..60) and a cliff wall (x 60..61, y 0..51) between
# the smelters and the chest the plates go to: the plate route and the pole chain must go round
IRON = """\
ore   = MinerRow<n=4, resource=iron-ore>       @patch(iron-ore)
smelt = SmelterRow<n=2, recipe=iron-plate>     @(20, 40)
coal  = Chest<requester, item=coal, rate=0.1/s> @(12, 40)
out   = Chest<provider>                        @(72, 46)
net ore_:   ore -> smelt
net fuel:   coal -> smelt
net plates: smelt -> out
"""


def fixture():
    ore = {(x, y): 1000 for x in range(5, 26) for y in range(8, 23)
           if ((x + 0.5 - 15) / 10) ** 2 + ((y + 0.5 - 15) / 7) ** 2 <= 1}
    water = frozenset((x, y) for x in range(30, 45) for y in range(25, 61))
    cliffs = [terrain.Cliff("cliff", 61.0, c + 0.5, "south-to-north", (60.0, c - 1.5, 62.0, c + 2.5))
              for c in range(1, 50, 4)]
    trees = {"tree-01": {"type": "tree", "at": [(50.5, 10.5), (51.5, 30.5)]}}
    return terrain.Terrain("nauvis", (-10, -10, 110, 90), 1, {"iron-ore": ore}, water,
                           frozenset(), cliffs, trees)


class TerrainFlowTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkterrainflow-")
        self.t = fixture()
        terrain.save(self.t, os.path.join(self.dir, "map.terrain.json"))
        for name, text in (("t.surface", SURFACE), ("t.build.fkb", SCRIPT), ("iron.fk", IRON)):
            with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def build(self):
        return flow.run(os.path.join(self.dir, "t.build.fkb"), cat=CAT, echo=lambda _l: None)

    def read(self, name):
        with open(os.path.join(self.dir, "out", name), encoding="utf-8") as fh:
            return fh.read()

    def test_the_cliff_wall_is_where_the_fixture_says(self):
        self.assertEqual({x for x, _y in self.t.cliff_tiles}, {60, 61})
        self.assertEqual({y for _x, y in self.t.cliff_tiles}, set(range(-1, 52)))

    def test_routes_and_poles_go_round_water_and_cliffs(self):
        code, ctx = self.build()
        self.assertEqual(code, 0, ctx.log)
        # the one check line: a paper factory has no generator (as in the redgreen flow test)
        self.assertEqual([(s, c.code) for s, c in ctx.checks if c.code not in ADVICE],
                         [("floorplan", "NO_POWER")], [str(c) for _s, c in ctx.checks])
        lay = ctx.layouts["iron"]
        blocked = self.t.blocked
        on = {k for k, e in lay.entities.items() if fkp.tiles_of(CAT, e) & blocked}
        self.assertEqual(on, set())
        poles = [e for e in lay.entities.values() if e.name == "medium-electric-pole"]
        self.assertTrue(poles)
        flat = elaborate_file(os.path.join(self.dir, "iron.fk"), CAT)
        rep = connect.connect(lay, CAT, connect.endpoints(flat))
        self.assertEqual({n: r.status for n, r in rep.nets.items()},
                         {"fuel": "connected", "ore_": "connected", "plates": "connected"})
        # the plate route passes north of the lake and tunnels under the 2-wide cliff wall (an
        # underground pair may span blocked ground, as in the game); the poles wire over it
        plates = [e for k, e in lay.entities.items() if k.startswith("~plates/")]
        self.assertTrue(any(30 <= e.x < 45 and e.y < 25 for e in plates))
        ugs = sorted((e.x, e.attrs["ug"]) for e in plates if e.name == "underground-belt")
        self.assertTrue(any(a[1] == "in" and b[1] == "out" and a[0] < 60 and b[0] > 62
                            for a, b in zip(ugs, ugs[1:])), ugs)
        self.assertIn("1 wire component", self.read("cover_power.txt"))
        self.assertIn("placed ore: @patch(iron-ore) at", self.read("place.txt"))
        self.assertIn("4/4 drills on iron-ore", self.read("place.txt"))
        floor = self.read("floorplan.txt")
        self.assertIn("terrain: 0 of", floor)
        self.assertIn("4/4 drills with ore under every tile, 36 ore tiles under them (36.0k)", floor)
        terr = self.read("read_terrain.txt")
        self.assertIn("blocked 646 tiles: water 540, cliffs 13 (106 tiles), other 0", terr)
        self.assertIn("plot iron at 0,0 90x70: 540 water; 104 cliff; 0 other blocked tiles; "
                      "iron-ore #1", terr)
        self.assertIn("2 trees, 0 rocks", terr)

    def test_a_kept_route_on_newly_blocked_ground_is_taken_up(self):
        # FRICTION 11-11 (the bootstrap stages): a roboport entered in the terrain after the route
        # was laid; the committed route stood on it, and the paste put an underground on it
        script = os.path.join(self.dir, "t.build.fkb")
        with open(script, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(SCRIPT.replace("route\n", "route --only stale\n"))
        code, ctx = self.build()
        self.assertEqual(code, 0, ctx.log)
        belts = sorted((e for k, e in ctx.layouts["iron"].entities.items()
                        if k.startswith("~plates/") and e.name == "transport-belt"),
                       key=lambda e: fkp.natural_key(e.key))
        mid = belts[len(belts) // 2]
        rock = frozenset(fkp.tiles_of(CAT, mid))
        import dataclasses
        terrain.save(dataclasses.replace(self.t, entities=self.t.entities | rock, entities_read={
            "tick": 1, "area": [-10, -10, 110, 90], "count": 1, "names": {"roboport": 1}}),
                     os.path.join(self.dir, "map.terrain.json"))
        code, ctx = self.build()
        self.assertEqual(code, 0, ctx.log)
        lay = ctx.layouts["iron"]
        self.assertFalse({k for k, e in lay.entities.items()
                          if k.startswith("~") and fkp.tiles_of(CAT, e) & rock})
        self.assertIn("patched   plates:", self.read("route.txt"))   # main kept b42 on it

    def test_without_the_terrain_the_plate_route_crosses_it(self):
        # the same layout routed blind: the terrain is what keeps the route off the lake
        code, ctx = self.build()
        lay = fkp.load(os.path.join(self.dir, "out", "place", "iron.fkp"))
        flat = elaborate_file(os.path.join(self.dir, "iron.fk"), CAT)
        blind = route.route_layout(flat, lay, CAT)
        used = set()
        for k, e in blind.layout.entities.items():
            if k.startswith("~"):
                used |= fkp.tiles_of(CAT, e)
        self.assertTrue(used & self.t.blocked)

    def test_on_terrain_fires_on_a_bad_placement_and_never_stops_the_flow(self):
        src = IRON.replace("@(20, 40)", "@(32, 30)")           # the smelters in the lake
        with open(os.path.join(self.dir, "iron.fk"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(src)
        code, ctx = self.build()
        self.assertEqual(code, 0, ctx.log)                    # a check, not a gate
        on = [c for _s, c in ctx.checks if c.code == "on-water-or-cliff"]
        self.assertTrue(on)
        self.assertTrue(all(c.where.startswith("nauvis:iron/") for c in on), [str(c) for c in on])
        self.assertIn("stone-furnace at 33,34 stands on 4 water tiles (first 32,33)",
                      [c.msg for c in on])
        self.assertEqual(sum(c.where.startswith("nauvis:iron/smelt/") for c in on), 20)
        self.assertIn("on-water-or-cliff", self.read("report_checks.txt"))

    def test_ground_the_terrain_has_not_read_is_named(self):
        # 2.1.19 (the live run, ~4245k): the terrain stopped at x480 and cu2p ran on over cliffs
        t = self.t
        t.area = (-10, -10, 70, 90)                           # the chest at 72,46 is past it
        terrain.save(t, os.path.join(self.dir, "map.terrain.json"))
        code, ctx = self.build()
        self.assertEqual(code, 0, ctx.log)
        blind = [c for s, c in ctx.checks if c.code == "no-terrain" and s == "floorplan"]
        self.assertEqual(len(blind), 1, [str(c) for _s, c in ctx.checks])
        self.assertIn("stand on ground the terrain has not read", blind[0].msg)
        self.assertIn("nauvis:iron/out", blind[0].msg)
        self.assertIn("fk read-terrain --area 62,", blind[0].msg)

    def test_off_water_fires_for_a_pump_on_dry_ground(self):
        # 1.4.2: the lead world's plant pump stood where world 3 had a lake
        for at, dry in (("@(45, 40, rot 3)", False), ("@(50, 40, rot 3)", True)):
            with open(os.path.join(self.dir, "iron.fk"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(IRON + f"pump = OffshorePump<rate=1200/s> {at}\n")
            code, ctx = self.build()
            self.assertEqual(code, 0, ctx.log)
            off = [c.msg for _s, c in ctx.checks if c.code == "no-water"]
            on = [c.msg for _s, c in ctx.checks if c.code == "on-water-or-cliff"]
            self.assertEqual(on, [])
            if dry:
                self.assertEqual(off, ["offshore-pump at 50.5,40.5: 6 of the 6 tiles it pumps "
                                       "from are not water (first 48,39): it gives no water"])
            else:
                self.assertEqual(off, [])

    def test_off_ore_fires_for_a_pinned_drill_away_from_the_ore(self):
        src = IRON.replace("@patch(iron-ore)", "@(4, 50)")
        with open(os.path.join(self.dir, "iron.fk"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(src)
        code, ctx = self.build()
        self.assertEqual(code, 0, ctx.log)
        off = [c for _s, c in ctx.checks if c.code == "no-ore"]
        self.assertEqual(len(off), 4, [str(c) for c in off])
        self.assertIn("0/4 drills with ore under every tile", self.read("floorplan.txt"))


class BridgeTest(unittest.TestCase):
    """floorplan --bridge-power keeps its shared poles off the terrain too (games/nauvis)."""

    def run_nauvis(self, water=None):
        folder = tempfile.mkdtemp(prefix="fkbridge-")
        self.addCleanup(shutil.rmtree, folder, True)
        for name in NAUVIS_SOURCES:
            shutil.copy(os.path.join(NAUVIS, name), folder)
        with open(os.path.join(folder, "nauvis.fkp"), "w", newline="\n") as fh:
            fh.write(CHAIN)
        if water is not None:
            terrain.save(terrain.Terrain("nauvis", (-60, -60, 100, 100), 1, water=frozenset(water)),
                         os.path.join(folder, "map.terrain.json"))
            for name, old, new in (("nauvis.surface", "terrain  none", "terrain  map"),
                                   ("nauvis.build.fkb", "read_terrain    none",
                                    "read_terrain    map ")):
                path = os.path.join(folder, name)
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                self.assertIn(old, text)
                with open(path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text.replace(old, new))
        code, ctx = flow.run(os.path.join(folder, "nauvis.build.fkb"), cat=CAT,
                             echo=lambda _l: None)
        self.assertEqual(code, 0, ctx.log)
        s = ctx.composed
        return s, {k: set(s.entities[k].tiles) for k in s.entities
                   if k.startswith("nauvis:bridge/p") and int(k[15:]) >= 7}

    def test_bridge_poles_avoid_water(self):
        _s, first = self.run_nauvis()
        wet = set().union(*first.values())
        self.assertEqual(len(first), 3)
        s, again = self.run_nauvis(water=wet)
        self.assertTrue(again)
        self.assertFalse(set().union(*again.values()) & wet)
        nets = cover.networks(list(s.entities.values()), CAT)
        self.assertEqual(len(nets), 1)                    # still one grid with the plant


if __name__ == "__main__":
    unittest.main()
