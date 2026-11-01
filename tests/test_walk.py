"""fkcore.walk, the net walker in world mode (3.0, PLAN-3.0 3f), on reads kept as fixtures."""
import glob
import json
import os
import unittest

from fkcore import walk
from fkcore.catalog import Catalog

CAT = Catalog.load()
DATA = os.path.join(os.path.dirname(__file__), "data", "walk")


def _row(n, t, x, y, d=0, w=1, h=1, **kw):
    row = {"n": n, "t": t, "x": x, "y": y, "d": d,
           "box": [x - w / 2, y - h / 2, x + w / 2, y + h / 2]}
    row.update(kw)
    return row


def line():
    """A stone furnace drops iron plates on a belt going east; an inserter takes them into a gear
    assembler that is short of plates; another puts its gears on a second, empty belt."""
    rows = [_row("stone-furnace", "furnace", 1, -2, w=2, h=2, rc="iron-plate", st="working", u=1),
            _row("inserter", "inserter", 0.5, -0.5, d=0, st="working", u=2, pt=1, dt=10)]
    for i in range(5):
        rows.append(_row("transport-belt", "transport-belt", i + 0.5, 0.5, d=4, u=10 + i,
                         ln=[{"iron-plate": 1}, {}]))
    rows += [_row("inserter", "inserter", 2.5, 1.5, d=0, st="waiting_for_source_items", u=3,
                  pt=12, dt=4),
             _row("assembling-machine-2", "assembling-machine", 2.5, 3.5, w=3, h=3,
                  rc="iron-gear-wheel", st="item_ingredient_shortage", u=4),
             _row("inserter", "inserter", 2.5, 5.5, d=0, st="waiting_for_source_items", u=5,
                  pt=4, dt=22)]
    for i in range(5):
        rows.append(_row("transport-belt", "transport-belt", i + 0.5, 6.5, d=4, u=20 + i,
                         ln=[{}, {}]))
    rows.append(_row("modded-belt", "transport-belt", 9.5, 9.5, d=4, u=30, ln=[{}, {}]))
    return {"tick": 1, "surface": "nauvis", "area": [-1, -4, 12, 12], "rows": rows,
            "protos": {"modded-belt": {"type": "transport-belt", "w": 1, "h": 1}},
            "recipes": {"iron-gear-wheel": {"ing": ["iron-plate"], "prod": ["iron-gear-wheel"]}}}


class TestWorldMode(unittest.TestCase):
    def setUp(self):
        self.w = walk.infer(line(), CAT)

    def test_nets_and_ends(self):
        nets = {n.name: n for n in self.w.nets.values()}
        self.assertEqual(sorted(nets), ["n1", "n2", "n3"])     # plates, gears, the lone modded belt
        plates = self.w.nets[self.w.net_of["belt@0.5,0.5"]]
        self.assertEqual(plates.drivers, ["fur@1,-2"])
        self.assertEqual(plates.consumers, ["asm@2.5,3.5"])
        self.assertEqual(plates.items, {"iron-plate": 5})
        self.assertEqual(plates.lanes, (5, 0))
        gears = self.w.nets[self.w.net_of["belt@0.5,6.5"]]
        self.assertEqual(gears.drivers, ["asm@2.5,3.5"])
        self.assertEqual(gears.made, {"iron-gear-wheel"})

    def test_catalog_gaps_come_from_the_game(self):
        self.assertEqual(self.w.added, ["modded-belt"])
        self.assertFalse(self.w.graph.problems)

    def test_marks(self):
        mk = walk.marks(self.w)
        self.assertTrue(mk["asm@2.5,3.5"].startswith("STARVED"))
        gears = self.w.net_of["belt@0.5,6.5"]
        self.assertEqual(mk[gears], "EMPTY")
        plates = self.w.net_of["belt@0.5,0.5"]
        self.assertEqual(mk[plates], "right lane empty")

    def test_root_and_tree(self):
        root = walk.find_root(self.w, "2,3")
        self.assertEqual(root, "asm@2.5,3.5")
        self.assertEqual(walk.find_root(self.w, "0.5,0.5"), "n1")
        text = "\n".join(walk.tree(self.w, root, up=2, down=1))
        self.assertIn("<- n1 iron-plate", text)
        self.assertIn("<- stone-furnace 1,-2 [iron-plate] working", text)
        self.assertIn("-> n2", text)
        self.assertIn("short of iron-plate", text)      # where the flow stops

    def test_agreement_with_the_game(self):
        self.assertTrue(walk.agreement(self.w).startswith("hands: 6 of 6"), walk.agreement(self.w))

    def test_frame_crossings(self):
        # around the gear assembler, the two belts cut at x=1: two ports, nothing else
        lines = walk.crossings(self.w, (1, 0, 5, 7))
        self.assertIn("2 belt ports", lines[0])
        self.assertTrue(lines[0].endswith("sealable as drawn"), lines[0])
        self.assertIn("port p1 : in iron-plate | iron-plate @w0", lines[1])
        # the assembler alone: its two inserters reach over the edge
        lines = walk.crossings(self.w, (1, 2, 5, 5))
        self.assertIn("2 hands over it", lines[0])
        # a frame through the assembler: it stands across the edge
        self.assertIn("1 entities across it", walk.crossings(self.w, (2, 2, 5, 5))[0])

    def test_space_age_rows(self):
        # a silo's rocket shadow is never built; a frozen or unset machine gets a loud mark
        dump = line()
        dump["rows"].append(_row("rocket-silo-rocket-shadow", "rocket-silo-rocket-shadow",
                                 2.5, 3.5, w=3, h=3, u=40))
        asm = next(r for r in dump["rows"] if r["n"] == "assembling-machine-2")
        asm["st"] = "frozen"
        w = walk.infer(dump, CAT)
        self.assertFalse(w.graph.problems)
        self.assertEqual(walk.marks(w)["asm@2.5,3.5"], "FROZEN")
        asm["st"] = "no_recipe"
        self.assertEqual(walk.marks(walk.infer(dump, CAT))["asm@2.5,3.5"], "NO RECIPE")

    def test_net_root(self):
        text = walk.tree(self.w, "n1", up=1, down=1)
        self.assertTrue(text[0].startswith("net n1 iron-plate"))


class TestKeptReads(unittest.TestCase):
    """Reads kept from real maps on a laptop server (tools/walk_corpus.py): the walk runs on each,
    finds its root, and agrees with the game's own inserter targets almost everywhere."""

    def test_reads(self):
        files = sorted(glob.glob(os.path.join(DATA, "*.json")))
        if not files:
            self.skipTest("no kept reads")
        for path in files:
            with open(path, encoding="utf-8") as fh:
                dump = json.load(fh)
            meta = dump.get("walk") or {}
            with self.subTest(os.path.basename(path)):
                w = walk.infer(dump, CAT)
                root = walk.find_root(w, meta.get("root", ""))
                self.assertIsNotNone(root)
                self.assertTrue(walk.tree(w, root, 3, 1))
                if "nets" in meta:
                    self.assertEqual(len(w.nets), meta["nets"])
                ag = walk.agreement(w)
                if ag:
                    same, total = (int(v) for v in ag.split(":")[1].split(" pickup")[0]
                                   .split(" of "))
                    self.assertGreaterEqual(same / total, meta.get("agree", 0.9), ag)


if __name__ == "__main__":
    unittest.main()
