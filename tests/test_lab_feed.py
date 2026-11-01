"""2.2 (Rory, 2026-10-31: "lab: should have infinity fluid source, and infinity chest source using
loaders, loaders should also not be placed on half cells"): a file that only defines a sealed
module is built alone in the lab, and every port no net binds from outside gets its source or sink
at its edge. Offline: the wrap, the feeds and their tiles, the Lua. The game side was tried on the
live lab (LdsBlock, a pair port, a fluid port; 2026-10-31)."""
import os
import shutil
import tempfile
import unittest

from fkcore import flow, lab

MODS = """
module PairT size 8x6 {
  port pin  : in iron-plate | copper-cable @w2
  port cout : out electronic-circuit @e2
  a = Assembler<recipe=electronic-circuit> @(3, 1)
  net p: pin -> a
  net c: a -> cout
}
"""
FLUID = """
module PlasT size 12x10 {
  port gas_in : in petroleum-gas @w4
  port c_in   : in coal @n2
  port p_out  : out plastic-bar @e4
  plas = ChemPlant<recipe=plastic-bar> @(5, 3)
  net g: gas_in -> plas
  net c: c_in -> plas
  net p: plas -> p_out
}
"""


class LabFeedTest(unittest.TestCase):
    def setUp(self):
        self.run = tempfile.mkdtemp(prefix="fklabfeed-")
        self.addCleanup(shutil.rmtree, self.run, True)
        self.game = os.path.join(self.run, "game")
        os.makedirs(self.game)
        for name, text in (("pairt.fk", MODS), ("plast.fk", FLUID)):
            with open(os.path.join(self.game, name), "w", encoding="utf-8") as fh:
                fh.write(text)

    def built(self, name):
        ws, (x, y, w, h) = lab.prepare(self.game, name)
        script = os.path.join(ws, "lab.build.fkb")
        with open(script, encoding="utf-8") as fh:
            text = fh.read()
        with open(script, "w", encoding="utf-8") as fh:      # offline: no apply, no diff
            fh.write("\n".join(ln for ln in text.splitlines()
                               if not ln.startswith(("apply", "diff"))) + "\n")
        code, ctx = flow.run(script, echo=lambda _l: None)
        self.assertEqual(code, 0)
        return ws, (x, y, w, h), ctx

    def test_a_sealed_module_alone_is_wrapped_with_room_round_it(self):
        ws, (x, y, w, h), _ctx = self.built("pairt")
        self.assertEqual((w, h), (8 + 2 * lab.PAD, 6 + 2 * lab.PAD))
        with open(os.path.join(ws, "lab_feed.fk"), encoding="utf-8") as fh:
            wrap = fh.read()
        self.assertIn('import PairT from "pairt.fk"', wrap)
        self.assertIn(f"pairt = PairT @({lab.PAD}, {lab.PAD})", wrap)
        with open(os.path.join(ws, "lab.surface"), encoding="utf-8") as fh:
            self.assertIn("place pairt = lab_feed plot", fh.read())

    def test_a_file_with_instances_is_built_as_it_is(self):
        with open(os.path.join(self.game, "pairlab.fk"), "w", encoding="utf-8") as fh:
            fh.write('import PairT from "pairt.fk"\nt = PairT @(2, 2)\n')
        ws, _plot = lab.prepare(self.game, "pairlab")
        self.assertFalse(os.path.exists(os.path.join(ws, "lab_feed.fk")))

    def test_a_pair_port_gets_a_loader_per_lane_and_every_feed_is_on_whole_tiles(self):
        _ws, (x, y, _w, _h), ctx = self.built("pairt")
        ents, skipped = lab.feeds(ctx.flats["pairt"], ctx.layouts["pairt"], ctx.cat, x, y)
        self.assertEqual(skipped, [])
        pin = [e for e in ents if e["port"] == "pairt/pin"]
        self.assertEqual(sorted(e["k"] for e in pin), ["belt", "chest", "chest", "loader", "loader"])
        chests = sorted(tuple(e["items"]) for e in pin if e["k"] == "chest")
        self.assertEqual(chests, [("copper-cable",), ("iron-plate",)])
        out = [e for e in ents if e["port"] == "pairt/cout"]
        self.assertEqual({e["k"]: e.get("items", e.get("type")) for e in out},
                         {"chest": [], "loader": "input"})
        x0, y0 = x + lab.PAD, y + lab.PAD
        for e in ents:
            ex, ey = e["at"]
            if e["k"] == "loader":
                # 2.1.20: the 2x1 loader on two whole tiles, its centre the edge between them
                along_y = e["dir"] in ("north", "south")
                self.assertEqual((ex % 1, ey % 1), (0.5, 0.0) if along_y else (0.0, 0.5), e)
                tiles = [(ex - 0.5, ey - 1), (ex - 0.5, ey)] if along_y else \
                    [(ex - 1, ey - 0.5), (ex, ey - 0.5)]
            else:
                self.assertEqual((ex % 1, ey % 1), (0.5, 0.5), e)    # a tile's centre
                tiles = [(ex - 0.5, ey - 0.5)]
            for tx, ty in tiles:                                     # outside the frame
                self.assertFalse(x0 <= tx < x0 + 8 and y0 <= ty < y0 + 6, e)

    def test_loaders_face_the_way_the_game_reads_them(self):
        # read from the game (2.0.77): an output loader facing d has its belt half on the d side;
        # an input one its container half there
        _ws, (x, y, _w, _h), ctx = self.built("pairt")
        ents, _skipped = lab.feeds(ctx.flats["pairt"], ctx.layouts["pairt"], ctx.cat, x, y)
        x0, y0 = x + lab.PAD, y + lab.PAD
        out = next(e for e in ents if e["port"] == "pairt/cout" and e["k"] == "loader")
        sink = next(e for e in ents if e["port"] == "pairt/cout" and e["k"] == "chest")
        # cout @e2: the edge tile x0+7, the loader's belt half on x0+8, its box half on x0+9
        self.assertEqual((out["dir"], out["type"], out["at"]), ("east", "input", [x0 + 9, y0 + 2.5]))
        self.assertEqual(sink["at"], [x0 + 10.5, y0 + 2.5])
        pin = sorted((e for e in ents if e["port"] == "pairt/pin" and e["k"] == "loader"),
                     key=lambda e: e["at"][1])
        # pin @w2: the belt on x0-1, a loader above and below it, each facing the belt
        self.assertEqual([(e["dir"], e["type"], e["at"]) for e in pin],
                         [("south", "output", [x0 - 0.5, y0 + 1]),
                          ("north", "output", [x0 - 0.5, y0 + 4])])

    def test_a_fluid_port_gets_an_infinity_pipe(self):
        _ws, (x, y, _w, _h), ctx = self.built("plast")
        ents, _skipped = lab.feeds(ctx.flats["plast"], ctx.layouts["plast"], ctx.cat, x, y)
        pipes = [e for e in ents if e["k"] == "pipe"]
        self.assertEqual([(e["port"], e["fluid"], e["out"]) for e in pipes],
                         [("plast/gas_in", "petroleum-gas", False)])
        self.assertEqual(sorted(e["port"].split("/")[1] for e in ents if e["k"] == "loader"),
                         ["c_in", "p_out"])
        lua = lab.lua_feed(ents)
        self.assertIn("set_infinity_pipe_filter", lua)
        self.assertIn("remove_unfiltered_items = true", lua)
        self.assertIn("type='output'", lua)

    def test_a_port_bound_outside_is_left_alone(self):
        with open(os.path.join(self.game, "half.fk"), "w", encoding="utf-8") as fh:
            fh.write('import PairT from "pairt.fk"\nt = PairT @(4, 4)\n'
                     'box = Chest<plain> @(16, 6)\nnet o: t.cout -> box\n')
        _ws, (x, y, _w, _h), ctx = self.built("half")
        ents, _skipped = lab.feeds(ctx.flats["half"], ctx.layouts["half"], ctx.cat, x, y)
        self.assertEqual({e["port"] for e in ents}, {"t/pin"})


if __name__ == "__main__":
    unittest.main()
