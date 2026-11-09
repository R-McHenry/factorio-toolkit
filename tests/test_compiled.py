"""3.1, the one compile store (PLAN-3.1 31-store, fkcore.compiled): the route step stores each
sealed unit's routes under one key (what it is laid to, ``route.unit_key``) in
``out/compiled/<module>/<key>.json`` and lays them from there wherever the unit stands next. A
world of two sealed modules routes one inside on the first build (the twin takes it); a second
build keeps everything; a move of one module lays its inside from the store. ``fk compile``,
``route --reuse-lab`` and ``fk status`` use the same store, and a route file the player edits by
hand is an input: it changes the key, and the build reads it."""
import contextlib
import io
import json
import os
import re
import shutil
import tempfile
import unittest

from fkcore import compiled, design, expand, flow, fkp, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate_file

CAT = Catalog.load()

WORLD = """module Gears size 16x8 {
  port fe_in : in iron-plate @w1
  port g_out : out iron-gear-wheel @e6
  ga = Assembler<recipe=iron-gear-wheel> @(3, 3)
  gb = Assembler<recipe=iron-gear-wheel> @(9, 3)
  net fe: fe_in -> ga, gb
  net g: ga, gb -> g_out
}
src = Chest<requester, item=iron-plate, request=20> @(1, 4)
a = Gears @(6, 2)
b = Gears @(6, 20)
box = Chest<provider, limit=10> @(36, 14)
net fa: src -> a.fe_in, b.fe_in
net ga: a.g_out, b.g_out -> box
"""


class CompiledTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkcompiled-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.write("t.fk", WORLD)
        self.write("nauvis.surface", "surface nauvis\nterrain none\n"
                                     "place t = t plot 0,0 60x50\n")
        self.write("nauvis.build.fkb", "read_surface nauvis\nread_terrain none\nelaborate\n"
                                       "place --keep pinned\nroute --only stale\n"
                                       "report_checks\nwrite_layout\n")
        self.out = os.path.join(self.dir, "out")
        self.store = os.path.join(self.out, "compiled", "Gears")

    def write(self, name, text):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def read(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8") as fh:
            return fh.read()

    def build(self, extra=None):
        code, ctx = flow.run(os.path.join(self.dir, "nauvis.build.fkb"), cat=CAT,
                             echo=lambda _l: None, extra=extra)
        self.assertEqual(code, 0, ctx.log)
        return self.read("out/route.txt"), self.read("out/report_checks.txt")

    def entries(self):
        """{key: entry} of the Gears store."""
        got = {}
        for name in os.listdir(self.store):
            if name.endswith(".json"):
                with open(os.path.join(self.store, name), encoding="utf-8") as fh:
                    got[name[:-5]] = json.load(fh)
        return got

    def test_insides_route_once(self):
        first, checks = self.build()
        self.assertIn("t: 6 routed, 0 kept", first)
        self.assertIn("compiled  stored a (out/compiled)", first)
        self.assertIn("laid as a laid it (compiled once", first)          # b is a's twin
        self.assertIn("6 nets: 6 connected", checks)
        self.assertIn("current", os.listdir(self.store))
        self.assertEqual(len(self.entries()), 1)        # both instances: one inside, one entry
        key = next(iter(self.entries()))
        self.assertEqual(self.read("out/compiled/Gears/current").strip(), key)
        # a second build: every net stands, nothing searched, nothing stored
        second, checks2 = self.build()
        self.assertIn("t: 0 routed, 6 kept (6 pinned from the committed .fkp)", second)
        self.assertNotIn("compiled  stored", second)
        self.assertIn("6 nets: 6 connected", checks2)
        # b moves: its inner nets are laid from the store where it stands now
        self.write("t.fk", WORLD.replace("b = Gears @(6, 20)", "b = Gears @(6, 30)"))
        third, checks3 = self.build()
        self.assertIn(f"compiled  b: 2 nets laid from the store (Gears {key})", third)
        self.assertIn("2 laid from the compiled store", third)
        self.assertIn("2 patched", third)                       # the two trunks patched
        self.assertIn("laid as the compiled store laid it", third)
        self.assertEqual(len(self.entries()), 1)
        self.assertIn("6 nets: 6 connected", checks3)
        lay = fkp.load(os.path.join(self.dir, "t.fkp"))
        ys = sorted({float(e.y) for e in lay.entities.values() if e.owner == "~b/g"})
        self.assertTrue(ys and min(ys) >= 30, ys)

    def test_the_key_is_the_inside_not_the_place(self):
        path = os.path.join(self.dir, "t.fk")
        flat = elaborate_file(path, CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(sorted(r.compiled), ["a", "b"])
        ka, kb = (r.compiled[p]["key"] for p in ("a", "b"))
        self.assertEqual(ka, kb)
        self.assertEqual(r.compiled["b"]["from"], "twin a")
        self.assertEqual((r.compiled["a"]["module"], r.compiled["a"]["nets"]),
                         ("Gears", ["a/fe", "a/g"]))
        self.write("t.fk", WORLD.replace("gb = Assembler<recipe=iron-gear-wheel> @(9, 3)",
                                         "gb = Assembler<recipe=iron-gear-wheel> @(10, 3)"))
        flat = elaborate_file(path, CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        self.assertNotEqual(route.route_layout(flat, lay, CAT).compiled["a"]["key"], ka)

    def test_a_seed_is_in_the_key(self):
        # a seed (fk seed) is a player input of the net: with one, the module keys otherwise
        path = os.path.join(self.dir, "t.fk")
        flat = elaborate_file(path, CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        plain = route.route_layout(flat, lay, CAT).compiled["a"]["key"]
        seed = fkp.Entity("~a/g/p0", "transport-belt", 17.5, 8.5, 4, {"net": "a/g"})
        seeded = route.route_layout(flat, lay, CAT, seeds={"a/g": [seed]}).compiled
        self.assertNotEqual(seeded["a"]["key"], plain)
        self.assertEqual(seeded["b"]["key"], plain)       # b has no seed: its key is the plain one

    def test_a_hand_edited_route_file_changes_the_key_and_is_read(self):
        # PLAN-BUILD §2: "a hand-edited route.fkp is an input like any other". The 3.0 route
        # files are out/design/<factory>/nets/<net>.net; the player edits one and holds it
        # (status: held), and the next build lays the module's other nets around what the file
        # says, under a new key
        self.build()
        (key1, entry1), = self.entries().items()
        self.assertEqual(entry1["inputs"]["nets"], ["fe", "g"])
        net_file = design.net_path(self.out, "t", "a/g")
        rec = design.read_net(net_file)
        self.assertEqual(rec["status"], "routed")
        belts = sorted((e for e in rec["ents"] if e.name == "transport-belt"),
                       key=lambda e: fkp.natural_key(e.key))
        self.assertTrue(len(belts) >= 2)
        kept = [e for e in rec["ents"] if e.key != belts[-1].key]      # the player cut one belt
        design.write_net(self.out, "t", "a/g", "held", kept)
        # the module's other net is laid again (fk route a/fe): its unit keys with the file's
        # carriers standing, a new key, and the file's route stands as edited
        text, _checks = self.build(["route --only stale --again a/fe"])
        self.assertIn("held a/g: ", text)
        self.assertNotIn("laid from the store", text)
        self.assertIn("compiled  stored a (out/compiled)", text)
        entries = self.entries()
        self.assertEqual(len(entries), 2)
        (key2, entry2), = ((k, e) for k, e in entries.items() if k != key1)
        self.assertEqual(entry2["inputs"]["nets"], ["fe"])
        lay = fkp.load(os.path.join(self.dir, "t.fkp"))
        mine = sorted(k for k, e in lay.entities.items() if e.owner == "~a/g")
        self.assertEqual(mine, sorted(e.key for e in kept))
        self.assertNotIn(belts[-1].key, lay.entities)
        self.assertEqual(design.read_net(net_file)["status"], "held")
        # the same edit again: the entry is found and laid, nothing stored
        again, _checks = self.build(["route --only stale --again a/fe"])
        self.assertIn(f"compiled  a: 1 nets laid from the store (Gears {key2})", again)
        self.assertEqual(len(self.entries()), 2)
        # the hold lifted: a/fe keys as the first build did, and the first entry is laid
        design.set_status(self.out, "t", "a/g", "routed", "")
        back, _checks = self.build(["route --only stale --again a/fe,a/g"])
        self.assertIn(f"compiled  a: 2 nets laid from the store (Gears {key1})", back)

    def test_fk_compile_then_the_first_world_build_routes_no_inside(self):
        from fkcore.__main__ import main
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["compile", os.path.join(self.dir, "nauvis.build.fkb"), "Gears"])
        self.assertEqual(code, 0)
        text = self.read("out/route.txt")
        self.assertIn("t: compile a: 2 nets routed and stored (Gears ", text)
        self.assertIn("t: compile b: the same inside as a", text)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "t.fkp")))   # nothing written
        self.assertEqual(len(self.entries()), 1)
        first, checks = self.build()
        self.assertIn("t: 6 routed, 0 kept (0 pinned from the committed .fkp, 4 laid from the "
                      "compiled store)", first)
        self.assertIn("6 nets: 6 connected", checks)
        self.assertEqual(len(self.entries()), 1)
        _again, _ = self.build()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["compile", os.path.join(self.dir, "nauvis.build.fkb"), "Gears"])
        self.assertIn("t: compile a: already compiled (Gears ", self.read("out/route.txt"))
        # fk status: the store beside the nets
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["status", self.dir]), 0)
        self.assertIn(f"compiled: 1 module, 1 entry (router {compiled.ROUTER})", out.getvalue())
        self.assertIn("  Gears: 1 entry, current ", out.getvalue())

    def test_reuse_lab_takes_what_the_lab_routed(self):
        # <run>/game is the build; <run>/lab/gears is a lab build of the module (fkcore.lab)
        # built elsewhere, with its own store; --reuse-lab reads the lab stores too
        game, ws = os.path.join(self.dir, "game"), os.path.join(self.dir, "lab", "gears")
        for d in (game, ws):
            os.makedirs(d)
            for f in ("nauvis.surface", "nauvis.build.fkb"):
                shutil.copy(os.path.join(self.dir, f), d)
        with open(os.path.join(ws, "t.fk"), "w", encoding="utf-8") as fh:
            fh.write(WORLD.replace("b = Gears @(6, 20)", "b = Gears @(30, 30)"))
        code, _ctx = flow.run(os.path.join(ws, "nauvis.build.fkb"), cat=CAT, echo=lambda _l: None)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isdir(os.path.join(ws, "out", "compiled", "Gears")))
        shutil.copy(os.path.join(self.dir, "t.fk"), game)
        code, _ctx = flow.run(os.path.join(game, "nauvis.build.fkb"), cat=CAT,
                              echo=lambda _l: None, extra=["route --only stale --reuse-lab"])
        self.assertEqual(code, 0)
        with open(os.path.join(game, "out", "route.txt"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("t: 6 routed, 0 kept (0 pinned from the committed .fkp, 4 laid from the "
                      "compiled store)", text)
        # the game's own store got no entry (the lab's is read only), just the current pointer
        self.assertEqual(os.listdir(os.path.join(game, "out", "compiled", "Gears")), ["current"])

    def test_an_inside_the_force_cannot_build_is_routed_again(self):
        # 2026-11-01, Sea Block: a module compiled on the lab (every research) kept long-handed
        # inserters the run's force had not researched, and robots waited on 5 ghosts
        self.build()
        with open(os.path.join(self.dir, "out", "avail.json"), "w", encoding="utf-8") as fh:
            json.dump({"tick": 1, "force": "player", "surface": "nauvis", "networks": 1,
                       "entities": [{"entity": "fast-inserter", "item": "fast-inserter", "stock": 0,
                                     "known": True, "enabled": False}],
                       "recipes": [], "research": {}}, fh)
        # b moves, so its inside is asked of the store; the entry holds fast inserters
        self.write("t.fk", WORLD.replace("b = Gears @(6, 20)", "b = Gears @(6, 30)"))
        route_txt, _ = self.build()
        self.assertIn("b: its stored entry (Gears) holds fast-inserter, not researched here: routed "
                      "again", route_txt)
        self.assertNotIn("laid from the store", route_txt)

    def test_compiled_no_turns_it_off(self):
        self.build(["route --only stale --compiled no"])
        self.assertFalse(os.path.isdir(os.path.join(self.dir, "out", "compiled")))
        self.build(["route --only stale --store none"])
        self.assertFalse(os.path.isdir(os.path.join(self.dir, "out", "compiled")))

    def test_an_old_store_is_said_once_and_not_read(self):
        old = os.path.join(self.out, "design", "modules", "Gears")
        os.makedirs(old)
        with open(os.path.join(old, "0123456789abcdef.fkp"), "w", encoding="utf-8") as fh:
            fh.write("fkp 1 factory @\n")
        text, _ = self.build()
        lines = [ln for ln in text.splitlines() if "old entries not read" in ln]
        self.assertEqual(len(lines), 1, text)
        self.assertIn("1 of the 3.0 design store (out/design/modules)", lines[0])
        self.assertIn("compiled  stored a (out/compiled)", text)
        self.assertEqual(re.findall(r"compiled  stored (\w+)", text), ["a"])


if __name__ == "__main__":
    unittest.main()
