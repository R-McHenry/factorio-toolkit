"""fkcore.terrain: cliff tiles, patches, frames, the file and the block read (no game)."""
import json
import os
import re
import shutil
import tempfile
import unittest

from fkcore import compose, fkp, link, terrain
from fkcore.catalog import Catalog
from fkcore.surface import Place

CAT = Catalog.load()


def block(area, water=(), resources=None, cliffs=(), removable=None, tick=7):
    """One block's dict, as the Lua writes it (empty tables come back as [])."""
    return {"tick": tick, "area": list(area), "water": [list(t) for t in water], "other": [],
            "tiles": {"water": len(water)} if water else [], "resources": resources or [],
            "removable": removable or [], "cliffs": list(cliffs), "enemies": [],
            "ungenerated": []}


CLIFF = {"name": "cliff", "x": 182, "y": 274.5, "orientation": "south-to-north",
         "box": [181, 272.5, 183, 276.5], "box_orientation": 0}


class GeometryTest(unittest.TestCase):
    def test_an_upright_cliff_blocks_the_tiles_its_box_overlaps(self):
        tiles = terrain.cliff_tiles((181, 272.5, 183, 276.5), 0)
        self.assertEqual(tiles, {(x, y) for x in (181, 182) for y in range(272, 277)})

    def test_a_quarter_turn_swaps_the_box(self):
        # a 4x2 box about (2, 1), turned a quarter: 2 wide and 4 tall
        self.assertEqual(terrain.cliff_tiles((0, 0, 4, 2), 0.25),
                         {(x, y) for x in (1, 2) for y in range(-1, 3)})

    def test_an_eighth_turn_is_a_diamond(self):
        # a unit square about the origin turned 45 degrees reaches 0.707 out: the four tiles
        # around the origin, and no further
        self.assertEqual(terrain.cliff_tiles((-0.5, -0.5, 0.5, 0.5), 0.125),
                         {(-1, -1), (0, -1), (-1, 0), (0, 0)})

    def test_a_diagonal_cliff_from_the_game(self):
        # nauvis 2026-10-20: an east-to-none cliff at 178,270.5, its box turned 1/8 (as read):
        # a band along x + y = 450.5, 2.8 long and 0.7 thick
        box = (178.89453125, 269.8359375, 179.6015625, 272.6640625)
        self.assertEqual(terrain.cliff_tiles(box, 0.125),
                         {(178, 272), (178, 271), (179, 271), (179, 270), (180, 270)})
        # with no inset, three more tiles count: the band only grazes them (by 0.002 tiles)
        self.assertEqual(terrain.cliff_tiles(box, 0.125, inset=0) - terrain.cliff_tiles(box, 0.125),
                         {(177, 271), (177, 272), (178, 270)})


class PatchTest(unittest.TestCase):
    def test_components_numbered_by_size(self):
        ore = {(0, 0): 10, (1, 0): 10, (2, 1): 10,          # 8-connected: one patch of 3
               (10, 10): 500, (11, 10): 500}                # a richer but smaller patch
        ps = terrain.patches({"iron-ore": ore})["iron-ore"]
        self.assertEqual([(p.n, len(p.tiles), p.amount, p.box) for p in ps],
                         [(1, 3, 30, (0, 0, 3, 2)), (2, 2, 1000, (10, 10, 12, 11))])
        self.assertEqual(ps[1].name, "iron-ore#2")


class FrameTest(unittest.TestCase):
    def test_to_frame_is_the_inverse_of_compose(self):
        for rot in range(4):
            plot = Place("f", "f", 100, 50, 8, 8, rot)
            size = (5, 3)
            for tile in [(0, 0), (4, 2), (1, 2), (3, 0)]:
                lay = fkp.Layout("factory", "f", size)
                lay.add(fkp.Entity("a/b", "wooden-chest", tile[0] + 0.5, tile[1] + 0.5))
                surf = fkp.loads(f"fkp 1 surface s\nplot f at 100,50 rot {rot} size 8x8\n")
                s = compose.compose(surf, {"f": lay}, CAT)
                (placed,) = s.entities.values()
                (where,) = placed.tiles
                self.assertEqual(terrain.from_frame(tile, plot, size), where, (rot, tile))
                self.assertEqual(terrain.to_frame(where, plot, size), tile, (rot, tile))

    def test_frame_ground_keeps_a_named_patch_only(self):
        t = terrain.Terrain("s", (0, 0, 40, 40), resources={"iron-ore": {
            (2, 2): 5, (3, 2): 5, (4, 2): 5, (20, 20): 9}}, water=frozenset({(1, 1), (39, 39)}))
        plot = Place("f", "f", 0, 0, 30, 30)
        g = terrain.frame_ground(t, plot)
        self.assertEqual(set(g.ore["iron-ore"]), {(2, 2), (3, 2), (4, 2), (20, 20)})
        self.assertEqual(g.blocked, {(1, 1)})                  # 39,39 is beyond the margin
        g2 = terrain.frame_ground(t, plot, patch="iron-ore#2")
        self.assertEqual(set(g2.ore["iron-ore"]), {(20, 20)})
        self.assertEqual(g.box, (0, 0, 30, 30))


class FileTest(unittest.TestCase):
    def test_merge_two_blocks_and_round_trip(self):
        a = block((0, 0, 4, 8), water=[(0, 0), (1, 0)],
                  resources={"iron-ore": [[2, 5, 300], [3, 5, 200]]}, cliffs=[CLIFF],
                  removable={"tree-01": {"type": "tree", "at": [[1.2, 3.4]]}})
        b = block((4, 0, 8, 8), resources={"iron-ore": [[4, 5, 100]]}, cliffs=[CLIFF],
                  removable={"big-rock": {"type": "rock", "at": [[5.5, 1.5]]}}, tick=9)
        t = terrain.merge("nauvis", (0, 0, 8, 8), [a, b])
        self.assertEqual(len(t.cliffs), 1)                 # seen by both blocks, kept once
        self.assertEqual(t.tick, 9)
        self.assertEqual(t.blocked, {(0, 0), (1, 0)})      # the cliff is outside the area
        self.assertEqual((t.removable_count("tree"), t.removable_count("rock")), (1, 1))
        (p,) = t.patches["iron-ore"]
        self.assertEqual((len(p.tiles), p.amount), (3, 600))
        d = t.to_dict()
        self.assertEqual(terrain.from_dict(json.loads(json.dumps(d))).to_dict(), d)
        self.assertEqual(d["removable"], {"trees": 1, "rocks": 1,
                                          "names": {"big-rock": 1, "tree-01": 1}})
        self.assertEqual(d["patches"]["iron-ore"], [{"n": 1, "tiles": 3, "amount": 600,
                                                     "box": [2, 5, 5, 6]}])
        lines = terrain.summary(t, "map")
        self.assertIn("blocked 2 tiles: water 2, cliffs 1 (0 tiles), other 0", lines[1])
        self.assertIn("iron-ore: 3 tiles, 600, 1 patch; #1 3 tiles 600 at 2,5..4,5", lines[2])

    def test_cliff_tiles_are_cut_to_the_area(self):
        t = terrain.merge("nauvis", (180, 270, 200, 275), [block((180, 270, 200, 275),
                                                                 cliffs=[CLIFF])])
        self.assertEqual(t.cliff_tiles, {(x, y) for x in (181, 182) for y in range(272, 275)})

    def test_save_writes_one_key_per_line(self):
        d = terrain.merge("lab", (0, 0, 4, 4), [block((0, 0, 4, 4), water=[(1, 1)])]).to_dict()
        folder = tempfile.mkdtemp(prefix="fkterrain-")
        try:
            path = os.path.join(folder, "map.terrain.json")
            terrain.save(d, path)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn('\n "blocked": [[1,1]]\n', text)
            self.assertEqual(terrain.load(path).to_dict(), d)
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class FakeRcon:
    """Writes a canned block file where the Lua says, as the game's helpers.write_file does."""

    def __init__(self, out_dir, blocks):
        self.out_dir, self.blocks, self.calls = out_dir, blocks, []

    def lua(self, body):
        link.assert_safe(body)
        self.calls.append(body)
        tag = re.search(r"helpers\.write_file\('fk5/([^']+)\.json'", body).group(1)
        x0, y0, x1, y1 = (int(v) for v in re.search(
            r"local x0, y0, x1, y1 = (-?\d+), (-?\d+), (-?\d+), (-?\d+)", body).groups())
        os.makedirs(os.path.join(self.out_dir, "fk5"), exist_ok=True)
        with open(os.path.join(self.out_dir, "fk5", f"{tag}.json"), "w") as fh:
            json.dump(self.blocks((x0, y0, x1, y1)), fh)
        return "ok 0 0"


class ReadTest(unittest.TestCase):
    def test_a_big_area_is_read_in_blocks(self):
        folder = tempfile.mkdtemp(prefix="fkterrain-out-")
        try:
            def blocks(area):
                return block(area, water=[(area[0], area[1])])
            r = FakeRcon(folder, blocks)
            d = terrain.read(r, "nauvis", (-100, -100, 100, 60), block=128, out_dir=folder)
            self.assertEqual(len(r.calls), 4)                    # 2 x 2 blocks
            self.assertEqual(d["water"], [[-100, -100], [28, -100], [-100, 28], [28, 28]])
            self.assertEqual(d["area"], [-100, -100, 100, 60])
            self.assertEqual(os.listdir(os.path.join(folder, "fk5")), [])   # read back, removed
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_the_lua_only_reads(self):
        lua = terrain.lua_block("nauvis", (0, 0, 128, 128), "t")
        link.assert_safe(lua)
        for word in ("create_entity", "set_tiles", "destroy", "request_to_generate", "chart",
                     "order_deconstruction", "build_blueprint"):
            self.assertNotIn(word, lua)
        for line in lua.splitlines():
            code = line.strip()
            self.assertFalse("--" in code and not code.startswith("--"), code)


if __name__ == "__main__":
    unittest.main()
