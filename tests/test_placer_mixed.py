"""PLAN-ORGANIC M1 and M2 (3.1): a drill's mining area stays off a second resource, a mixed patch
is placed where the fewest drills touch it (filtered or left out, a ``mixed-patch`` check line),
and ``MinerRow<n=auto> @patch(RES)`` takes its count from the patch. No game."""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from fkcore import codec, expand, fkp, flow, lang, placer, size, terrain
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate
from fkcore.fragments import fragment

CAT = Catalog.load()


def strip(x0, x1, y0, y1, amount=500):
    return {(x, y): amount for x in range(x0, x1) for y in range(y0, y1)}


#: a 30x7 iron strip, long axis E-W: a row of 20 electric drills covers it exactly (3 tiles a pair)
IRON = strip(0, 30, 10, 17)
#: copper along the strip's whole south edge: every south drill's 5x5 area reaches it
COPPER_SOUTH = {(x, 17): 500 for x in range(0, 30)}
#: a copper streak at the west end only: a row of 8 fits east of it, clean
COPPER_WEST = {(x, 17): 500 for x in range(0, 6)}
#: copper along both long edges: whichever way a row turns, every drill's area reaches one (a
#: 4-drill row turned N-S, 7x6, keeps clear of the south edge alone)
COPPER_BOTH = {**COPPER_SOUTH, **{(x, 9): 500 for x in range(0, 30)}}


def ground(ore, box=(0, 0, 60, 60)):
    return terrain.FrameGround(frozenset(), ore, box)


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def make(k):
    return fragment("MinerRow", {"n": k, "resource": "iron-ore"}, [], [["iron-ore"]])


def drills(lay):
    return {k: e for k, e in lay.entities.items() if e.name == "electric-mining-drill"}


def areas_touch(lay, tiles):
    """The drills whose mining area holds a tile of ``tiles``."""
    return sorted(k for k, e in drills(lay).items()
                  if placer.mining_area(e.name, float(e.x), float(e.y)) & set(tiles))


ROW = """
ore = MinerRow<n={n}, resource=iron-ore> @patch(iron-ore)
box = Chest<provider> @(55, 55)
net o: ore -> box
"""


def place(text, ore):
    log, checks = [], []
    lay, notes = expand.expand_factory(flat_of(text), CAT, ground=ground(ore), log=log,
                                       checks=checks)
    return lay, notes, log, checks


class MixedPatchTest(unittest.TestCase):
    def test_the_row_is_placed_off_the_copper(self):
        lay, notes, log, checks = place(ROW.format(n=8), {"iron-ore": IRON,
                                                           "copper-ore": COPPER_WEST})
        self.assertEqual((notes, checks), ([], []))
        self.assertEqual(len(drills(lay)), 8)
        self.assertEqual(areas_touch(lay, COPPER_WEST), [])
        self.assertGreaterEqual(lay.insts["ore"].x, 7)               # east of the streak
        self.assertNotIn("mixed-patch", log[0])
        self.assertIn("8/8 drills on iron-ore", log[0])
        self.assertEqual(fkp.invariants(lay, CAT), [])

    def test_no_clean_spot_leaves_the_touching_drills_out_and_says_so(self):
        # the base game's electric drill has no resource filter (filter_count unset): the drills
        # whose area reaches the copper are left out, n stays 8
        lay, notes, log, checks = place(ROW.format(n=8), {"iron-ore": IRON,
                                                           "copper-ore": COPPER_SOUTH})
        self.assertEqual(notes, [])
        self.assertEqual(sorted(drills(lay)), ["ore/m0", "ore/m1", "ore/m2", "ore/m3"])
        self.assertEqual(areas_touch(lay, COPPER_SOUTH), [])
        self.assertEqual(lay.insts["ore"].params["n"], "8")
        (check,) = checks
        self.assertEqual(check[:2], ("mixed-patch", "ore"))
        self.assertEqual(check[2],
                         "4 of 8 drills' mining areas reach copper-ore (m4, m5, m6, m7) at 1,10 "
                         "rot 0, the spot where the fewest do; electric-mining-drill has no "
                         "resource filter slots in facts.json, so they are left out: 4 of 8 "
                         "drills placed")
        self.assertTrue(log[0].endswith("; 4 left out (mixed-patch)"), log[0])
        self.assertEqual(fkp.invariants(lay, CAT), [])

    def test_a_drill_with_filter_slots_is_filtered_to_the_rows_resource(self):
        with mock.patch.object(placer, "filter_slots", lambda name: 1):
            lay, notes, log, checks = place(ROW.format(n=8), {"iron-ore": IRON,
                                                               "copper-ore": COPPER_SOUTH})
        self.assertEqual(notes, [])
        self.assertEqual(len(drills(lay)), 8)
        for k, e in drills(lay).items():
            touching = k in ("ore/m4", "ore/m5", "ore/m6", "ore/m7")
            self.assertEqual(e.attrs.get("resource_filter"), "iron-ore" if touching else None, k)
        (check,) = checks
        self.assertIn("electric-mining-drill has 1 resource filter slot: theirs is set to "
                      "iron-ore, so they mine nothing else", check[2])
        self.assertTrue(log[0].endswith("; 4 filtered to iron-ore (mixed-patch)"), log[0])
        # the field the codec writes for it stays a guess (43-mines, measured on a 2.1.24 laptop
        # server: no drill of the game has filter slots, so no blueprint ever carries one and the
        # shape cannot be read back; docs/notes-43-mines.md); the .fkp keeps the attr through a
        # round trip
        self.assertEqual(codec.control_behavior(lay.entities["ore/m4"].attrs),
                         {"filter": {"filters": [{"index": 1, "name": "iron-ore"}],
                                     "mode": "whitelist"}})
        back = fkp.loads(fkp.dumps(lay))
        self.assertEqual(back.entities["ore/m4"].attrs.get("resource_filter"), "iron-ore")
        self.assertEqual(fkp.invariants(lay, CAT), [])

    def test_the_spot_with_the_fewest_touching_drills_wins(self):
        # copper under the whole south edge (every south drill touches) and along the north-west
        # (the north drills touch there too): the row goes east, where only the south four do
        copper = dict(COPPER_SOUTH)
        copper.update({(x, 9): 500 for x in range(0, 15)})
        other = placer.others("electric-mining-drill", "iron-ore",
                              {"iron-ore": IRON, "copper-ore": copper})
        spot = placer.place_on_patch(make(8), CAT, IRON, frozenset(), set(), (0, 0, 60, 60), other)
        self.assertEqual([i for i, _r in spot.mixed], [4, 5, 6, 7])
        self.assertEqual({r for _i, r in spot.mixed}, {"copper-ore"})
        self.assertGreaterEqual(spot.x, 13)
        self.assertFalse(spot.clean)
        # without the other resource the same patch is clean wherever the row stands
        self.assertTrue(placer.place_on_patch(make(8), CAT, IRON, frozenset(), set(),
                                              (0, 0, 60, 60)).clean)

    def test_other_resources_are_the_ones_the_drill_mines(self):
        ore = {"iron-ore": IRON, "copper-ore": {(2, 2): 5}, "crude-oil": {(1, 1): 5},
               "stone": {(2, 2): 7}}
        got = placer.others("electric-mining-drill", "iron-ore", ore)
        self.assertEqual(got, {(2, 2): "copper-ore+stone"})      # crude oil is not mined by it
        # 43-mines: measured on a 2.1.24 laptop server, prototypes.entity[d].filter_count is 0 for
        # every drill (electric, burner, big, pumpjack) and set_filter says "Callable only on
        # entities that have filters": the game's drills have no resource filter, so the row's
        # touching drills are left out, never filtered
        for drill in ("electric-mining-drill", "burner-mining-drill", "big-mining-drill",
                      "pumpjack"):
            self.assertEqual(placer.filter_slots(drill), 0, drill)

    def test_the_place_step_prints_the_check_line(self):
        checks = []
        lay, _notes = expand.expand_factory(flat_of(ROW.format(n=8)), CAT,
                                            ground=ground({"iron-ore": IRON,
                                                           "copper-ore": COPPER_SOUTH}),
                                            checks=checks)
        self.assertEqual(len(checks), 1)
        self.assertEqual(len(drills(lay)), 4)
        # a caller that passes no list still gets the layout (the check is for the flow)
        lay2, _notes = expand.expand_factory(flat_of(ROW.format(n=8)), CAT,
                                             ground=ground({"iron-ore": IRON,
                                                            "copper-ore": COPPER_SOUTH}))
        self.assertEqual(fkp.dumps(lay), fkp.dumps(lay2))


class CoverTest(unittest.TestCase):
    def test_the_most_clean_drills_on_a_patch_of_known_size(self):
        box = (0, 0, 60, 60)
        k, spot = placer.cover(make, 1, 100, CAT, IRON, frozenset(), set(), box)
        self.assertEqual((k, spot.rot, spot.drills, spot.size), (20, 0, 20, (30, 7)))
        self.assertTrue(spot.clean)
        k, spot = placer.cover(make, 4, 12, CAT, IRON, frozenset(), set(), box)
        self.assertEqual(k, 12)                                    # the written top holds
        other = placer.others("electric-mining-drill", "iron-ore",
                              {"iron-ore": IRON, "copper-ore": COPPER_WEST})
        k, spot = placer.cover(make, 1, 100, CAT, IRON, frozenset(), set(), box, other)
        self.assertEqual(k, 14)                                    # east of the streak, clean
        self.assertTrue(spot.clean and spot.x >= 7, spot)
        other = placer.others("electric-mining-drill", "iron-ore",
                              {"iron-ore": IRON, "copper-ore": COPPER_SOUTH})
        k, spot = placer.cover(make, 1, 100, CAT, IRON, frozenset(), set(), box, other)
        self.assertEqual((k, spot.rot % 2, spot.size, spot.clean), (4, 1, (7, 6), True))
        other = placer.others("electric-mining-drill", "iron-ore",
                              {"iron-ore": IRON, "copper-ore": COPPER_BOTH})
        self.assertEqual(placer.cover(make, 3, 100, CAT, IRON, frozenset(), set(), box, other),
                         (0, None))                    # no clean spot for 3 or more drills
        k, spot = placer.cover(make, 1, 100, CAT, IRON, frozenset(), set(), box, other)
        self.assertEqual((k, spot.size, spot.y), (2, (7, 3), 11))  # two, in the middle row
        self.assertEqual(placer.cover(make, 30, 40, CAT, IRON, frozenset(), set(), box),
                         (0, None))                                # the low bound does not fit

    def test_a_tall_patch_turns_the_row(self):
        tall = strip(10, 17, 0, 30)
        k, spot = placer.cover(make, 1, 100, CAT, tall, frozenset(), set(), (0, 0, 60, 60))
        self.assertEqual((k, spot.rot % 2), (20, 1))


class PatchesTest(unittest.TestCase):
    """M3 (43-mines): ``placer.patches`` reads the terrain the design names; the world placer's
    pins on ore (part T) call it and never read the world."""

    def setUp(self):
        # two iron patches (the strip, and a 4x4 block east of it) and the copper streak
        block = strip(40, 44, 10, 14, amount=100)
        self.t = terrain.Terrain("nauvis", (-10, -10, 110, 90), 1,
                                 {"iron-ore": {**IRON, **block}, "copper-ore": COPPER_WEST},
                                 frozenset(), frozenset(), [], {})

    def test_every_patch_of_a_resource_largest_first_with_its_centroid(self):
        got = placer.patches(self.t, "iron-ore")
        self.assertEqual([(p.name, len(p), p.amount, p.box) for p in got],
                         [("iron-ore#1", 210, 105000, (0, 10, 30, 17)),
                          ("iron-ore#2", 16, 1600, (40, 10, 44, 14))])
        self.assertEqual(got[0].centroid, (15.0, 13.5))
        self.assertEqual(got[1].centroid, (42.0, 12.0))
        self.assertEqual((got[0].size, got[0].resource, got[0].n), ((30, 7), "iron-ore", 1))
        self.assertEqual(got[1].tiles, frozenset(strip(40, 44, 10, 14)))
        # every resource when none is named, sorted by resource then size
        self.assertEqual([p.name for p in placer.patches(self.t)],
                         ["copper-ore#1", "iron-ore#1", "iron-ore#2"])
        self.assertEqual(placer.patches(self.t, "stone"), [])

    def test_the_named_one_the_nearest_one_and_the_terrain_in_any_form(self):
        self.assertEqual(placer.patch(self.t, "iron-ore#2").box, (40, 10, 44, 14))
        self.assertEqual(placer.patch(self.t, "iron-ore").n, 1)
        self.assertIsNone(placer.patch(self.t, "iron-ore#3"))
        self.assertIsNone(placer.patch(self.t, "stone#1"))
        near = placer.nearest_patch(self.t, "iron-ore", (45, 12))
        self.assertEqual(near.name, "iron-ore#2")
        self.assertEqual(placer.nearest_patch(self.t, "iron-ore", (45, 12), need=20).name,
                         "iron-ore#1")
        self.assertIsNone(placer.nearest_patch(self.t, "iron-ore", (0, 0), need=1000))
        # the same from the file the design names, its dict, and a plot's FrameGround
        d = tempfile.mkdtemp(prefix="fkpatch-")
        self.addCleanup(shutil.rmtree, d, True)
        path = os.path.join(d, "map.terrain.json")
        terrain.save(self.t, path)
        self.assertEqual([p.name for p in placer.patches(path, "iron-ore")],
                         ["iron-ore#1", "iron-ore#2"])
        self.assertEqual(placer.patch(self.t.to_dict(), "iron-ore#2").centroid, (42.0, 12.0))
        g = ground({"iron-ore": IRON, "copper-ore": COPPER_WEST})
        self.assertEqual([(p.name, len(p)) for p in placer.patches(g)],
                         [("copper-ore#1", 6), ("iron-ore#1", 210)])


SURFACE = """\
surface  nauvis
mode     play
terrain  map
catalog  base
place iron = iron plot 0,0 60x40
"""
SCRIPT = """\
read_surface    t
read_terrain    map
elaborate
size
place
report_checks
write_layout
"""
AUTO = """\
ore = MinerRow<n=auto 4..30, resource=iron-ore> @patch(iron-ore)
box = Chest<provider>                            @(50, 30)
net o: ore -> box
"""


class SizeFromPatchTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkmixed-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, name, text):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def read(self, name):
        with open(os.path.join(self.dir, "out", name), encoding="utf-8") as fh:
            return fh.read()

    def test_n_auto_takes_its_count_from_the_patch(self):
        self.write("t.fk", AUTO)
        maker = size.maker(os.path.join(self.dir, "t.fk"), CAT, "t")
        sz = size.size({"t": maker}, cat=CAT, grounds={"t": ground({"iron-ore": IRON})})
        (row,) = sz.rows
        self.assertEqual((row.n, row.lo, row.hi, row.covered), (20, 4, 30, True))
        lines, checks = size.report(sz, CAT)
        self.assertEqual(lines[0], "sized: ore n=20 (auto 4..30)")
        self.assertTrue(any("@patch(iron-ore): the iron-ore in the plot spans 30x7, long axis "
                            "E-W; 20 drills stand on it with their mining areas off other "
                            "resources, the row E-W at 0,10 rot 0" in line for line in lines),
                        lines)
        self.assertTrue(any("its patch: what the ore holds" in line for line in lines), lines)
        # the bounds still hold, and the streak keeps the drills off the copper
        sz = size.size({"t": maker}, cat=CAT,
                       grounds={"t": ground({"iron-ore": IRON, "copper-ore": COPPER_WEST})})
        self.assertEqual(sz.rows[0].n, 14)
        self.write("b.fk", AUTO.replace("4..30", "4..12"))
        maker12 = size.maker(os.path.join(self.dir, "b.fk"), CAT, "t")
        sz = size.size({"t": maker12}, cat=CAT, grounds={"t": ground({"iron-ore": IRON})})
        self.assertEqual(sz.rows[0].n, 12)
        # without a ground the row is sized by rates as before: nothing asks, the low bound
        sz = size.size({"t": maker}, cat=CAT)
        self.assertEqual((sz.rows[0].n, sz.rows[0].covered, sz.rows[0].patch), (4, False, None))

    def test_a_patch_that_gives_no_count_says_why_and_sizes_by_rates(self):
        self.write("t.fk", AUTO)
        maker = size.maker(os.path.join(self.dir, "t.fk"), CAT, "t")
        sz = size.size({"t": maker}, cat=CAT,
                       grounds={"t": ground({"iron-ore": IRON, "copper-ore": COPPER_BOTH})})
        (row,) = sz.rows
        self.assertEqual((row.n, row.covered), (4, False))
        self.assertIn("not even n=4 has a spot in the plot with every drill on iron-ore and no "
                      "mining area on another resource", row.patch)
        self.assertIn("n sized by rates", row.patch)

    def test_the_build_writes_what_the_patch_gave(self):
        t = terrain.Terrain("nauvis", (-10, -10, 110, 90), 1,
                            {"iron-ore": IRON, "copper-ore": COPPER_WEST}, frozenset(),
                            frozenset(), [], {})
        terrain.save(t, os.path.join(self.dir, "map.terrain.json"))
        self.write("t.surface", SURFACE)
        self.write("t.build.fkb", SCRIPT)
        self.write("iron.fk", AUTO)
        flow.run(os.path.join(self.dir, "t.build.fkb"), cat=CAT, echo=lambda _l: None)
        sized = self.read("size.txt")
        self.assertIn("sized: ore n=14 (auto 4..30)", sized)
        self.assertIn("14 drills stand on it with their mining areas off other resources", sized)
        self.assertIn("on their ore by place (@patch): ore n=14 (what the patch holds)", sized)
        placed = self.read("place.txt")
        self.assertIn("placed ore: @patch(iron-ore) at", placed)
        self.assertIn("14/14 drills on iron-ore", placed)
        self.assertNotIn("mixed-patch", placed)
        lay = fkp.load(os.path.join(self.dir, "iron.fkp"))
        self.assertEqual(len(drills(lay)), 14)
        self.assertEqual(areas_touch(lay, COPPER_WEST), [])

    def test_the_build_prints_the_mixed_patch_check(self):
        t = terrain.Terrain("nauvis", (-10, -10, 110, 90), 1,
                            {"iron-ore": IRON, "copper-ore": COPPER_SOUTH}, frozenset(),
                            frozenset(), [], {})
        terrain.save(t, os.path.join(self.dir, "map.terrain.json"))
        self.write("t.surface", SURFACE)
        self.write("t.build.fkb", SCRIPT)
        self.write("iron.fk", AUTO.replace("n=auto 4..30", "n=8"))
        flow.run(os.path.join(self.dir, "t.build.fkb"), cat=CAT, echo=lambda _l: None)
        checks = self.read("checks.txt") if os.path.exists(
            os.path.join(self.dir, "out", "checks.txt")) else self.read("report_checks.txt")
        self.assertIn("mixed-patch", checks)
        self.assertIn("4 of 8 drills' mining areas reach copper-ore (m4, m5, m6, m7)", checks)
        self.assertIn("left out: 4 of 8 drills placed", checks)


if __name__ == "__main__":
    unittest.main()
