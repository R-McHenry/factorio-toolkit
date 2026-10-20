"""fkcore.placer and expand's @patch: a MinerRow onto real ore, every drill on it (no game)."""
import unittest

from fkcore import expand, fkp, lang, placer, terrain
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate
from fkcore.fragments import fragment

CAT = Catalog.load()


def ellipse(cx, cy, rx, ry, amount=1000):
    return {(x, y): amount for x in range(cx - rx, cx + rx + 1) for y in range(cy - ry, cy + ry + 1)
            if ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 <= 1}


def ground(ore, blocked=(), box=(0, 0, 60, 60)):
    return terrain.FrameGround(frozenset(blocked), {"iron-ore": ore}, box)


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def drills_on_ore(lay, ore):
    out = []
    for e in lay.entities.values():
        if e.name == "electric-mining-drill":
            out.append(all(t in ore for t in fkp.tiles_of(CAT, e)))
    return out


ROW = """
ore = MinerRow<n={n}, resource=iron-ore> @patch(iron-ore)
box = Chest<provider> @(55, 55)
net o: ore -> box
"""
WITH_SMELTER = """
ore = MinerRow<n={n}, resource=iron-ore> @patch(iron-ore)
smelt = SmelterRow<n=2, recipe=iron-plate> @(30, 30)
box = Chest<provider> @(55, 55)
net ore_: ore -> smelt
net plates: smelt -> box
"""


class PlacerTest(unittest.TestCase):
    def test_every_drill_on_ore_and_nothing_on_water(self):
        ore = ellipse(15, 15, 10, 7)
        water = {(x, y) for x in range(12, 16) for y in range(12, 16)}    # a pond in the patch
        flat = flat_of(WITH_SMELTER.format(n=4))
        log = []
        lay, notes = expand.expand_factory(flat, CAT, ground=ground(
            {t: a for t, a in ore.items() if t not in water}, water), log=log)
        self.assertEqual(notes, [])
        self.assertEqual(drills_on_ore(lay, ore), [True] * 4)
        used = set()
        for k, e in lay.entities.items():
            if k.startswith("ore/"):
                used |= fkp.tiles_of(CAT, e)
        self.assertFalse(used & water)
        self.assertEqual(fkp.invariants(lay, CAT), [])
        (line,) = log
        self.assertRegex(line, r"^ore: @patch\(iron-ore\) at \d+,\d+ rot \d, the row runs (E-W|N-S) "
                               r"\(the iron-ore in the plot spans 20x14, long axis E-W\): 4/4 "
                               r"drills on iron-ore, 36 ore tiles under them \(36\.0k\)")

    def test_deterministic_and_clear_of_pinned_rows(self):
        ore = ellipse(15, 15, 10, 7)
        text = WITH_SMELTER.format(n=4).replace("@(30, 30)", "@(8, 12)")
        a, _ = expand.expand_factory(flat_of(text), CAT, ground=ground(ore))
        b, _ = expand.expand_factory(flat_of(text), CAT, ground=ground(ore))
        self.assertEqual(fkp.dumps(a), fkp.dumps(b))
        self.assertEqual(fkp.invariants(a, CAT), [])            # no tile shared with the smelter
        flat = flat_of(text)
        smelt = expand.frame_of(flat, a, "smelt", CAT)
        ore_box = expand.frame_of(flat, a, "ore", CAT)
        self.assertFalse(smelt[0] < ore_box[2] and ore_box[0] < smelt[2]
                         and smelt[1] < ore_box[3] and ore_box[1] < smelt[3])

    def test_a_long_thin_patch_turns_the_row(self):
        ore = {(x, y): 500 for x in range(10, 17) for y in range(0, 30)}   # 7 wide, 30 tall
        log = []
        lay, notes = expand.expand_factory(flat_of(ROW.format(n=8)), CAT, ground=ground(ore),
                                           log=log)
        self.assertEqual(notes, [])
        self.assertEqual(lay.insts["ore"].rot % 2, 1, log)
        self.assertIn("the row runs N-S", log[0])
        self.assertIn("long axis N-S", log[0])
        self.assertEqual(drills_on_ore(lay, ore), [True] * 8)

    def test_n_is_never_changed_the_report_says_what_fits(self):
        ore = {(x, y): 500 for x in range(10, 17) for y in range(0, 31)}
        lay, notes = expand.expand_factory(flat_of(ROW.format(n=24)), CAT, ground=ground(ore))
        self.assertNotIn("ore", lay.insts)
        (note,) = notes
        self.assertIn("no spot in the plot puts all 24 drills on iron-ore", note)
        self.assertIn("n=20 would fit", note)
        self.assertIn("n stays 24", note)

    def test_without_a_terrain_it_is_unplaced(self):
        lay, notes = expand.expand_factory(flat_of(ROW.format(n=2)), CAT)
        self.assertEqual(notes, ["ore: @patch(iron-ore) needs the terrain (read_terrain <name>) "
                                 "and the factory's plot"])

    def test_more_ore_in_reach_wins(self):
        # two spots fit; the one with ore all round the drills' mining areas wins
        ore = {(x, y): 100 for x in range(0, 6) for y in range(0, 7)}          # just the row
        ore.update({(x, y): 100 for x in range(28, 40) for y in range(20, 33)})  # a wide field
        frag = fragment("MinerRow", {"n": 4, "resource": "iron-ore"}, [], [["iron-ore"]])
        spot = placer.place_on_patch(frag, CAT, ore, frozenset(), set(), (0, 0, 60, 60))
        self.assertTrue(28 <= spot.x and 20 <= spot.y, spot)
        self.assertEqual((spot.drills, spot.under), (4, 36))
        self.assertGreater(spot.reach, 42)

    def test_the_route_start_must_be_free(self):
        # the row's belt leaves east (rot 0): water on that tile pushes the row elsewhere
        frag = fragment("MinerRow", {"n": 2, "resource": "iron-ore"}, [], [["iron-ore"]])
        sh = placer.shape(frag, CAT, 0)
        self.assertEqual(sh.ends, {(3, 3)})                  # east of the last belt tile
        self.assertEqual(len(sh.areas[0]), 25)


if __name__ == "__main__":
    unittest.main()
