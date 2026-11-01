"""3.0, sealed modules compile once (PLAN-3.0 §4, phase 5, fkcore.compiled): the route step stores
a sealed instance's routed inside, keyed by what it is laid to, and lays it from the store
wherever the instance stands next. A world of two sealed modules routes their insides on the first
build; a second build, and a move of one module, search none of them."""
import os
import re
import shutil
import tempfile
import unittest

from fkcore import compiled, expand, flow, fkp
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
        self.write("nauvis.surface", "surface nauvis\nmode play\nterrain none\n"
                                     "place t = t plot 0,0 60x50\n")
        self.write("nauvis.build.fkb", "read_surface nauvis\nread_terrain none\nelaborate\n"
                                       "place --keep pinned\nroute --only stale\n"
                                       "report_checks\nwrite_layout\n")

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

    def test_insides_route_once(self):
        first, checks = self.build()
        self.assertIn("t: 6 routed, 0 kept", first)
        self.assertIn("compiled  stored the inside of a", first)
        self.assertIn("6 nets: 6 connected", checks)
        store = os.path.join(self.dir, "out", "design", "modules", "Gears")
        self.assertEqual(len(os.listdir(store)), 1)        # both instances: one inside
        # a second build: every inner net stands, nothing searched
        second, checks2 = self.build()
        self.assertIn("t: 0 routed, 6 kept (2 pinned from the committed .fkp, 4 from compiled "
                      "modules)", second)
        self.assertIn("6 nets: 6 connected", checks2)
        # b moves: its inner nets are laid from the store where it stands now
        self.write("t.fk", WORLD.replace("b = Gears @(6, 20)", "b = Gears @(6, 30)"))
        third, checks3 = self.build()
        self.assertIn("compiled  b: 2 inner nets from its stored inside (Gears ", third)
        self.assertIn("t: 0 routed, 4 kept, 2 patched", third)   # the two trunks patched
        self.assertIn("kept      b/g: its carriers are already laid (pinned)", third)
        self.assertEqual(re.findall(r"stale\s+(b/\w+)", third), [])
        self.assertIn("6 nets: 6 connected", checks3)
        lay = fkp.load(os.path.join(self.dir, "t.fkp"))
        ys = sorted({float(e.y) for e in lay.entities.values() if e.owner == "~b/g"})
        self.assertTrue(ys and min(ys) >= 30, ys)

    def test_the_key_is_the_inside_not_the_place(self):
        path = os.path.join(self.dir, "t.fk")
        flat = elaborate_file(path, CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        self.assertEqual(compiled.sealed_roots(flat, lay), ["a", "b"])
        ka, kb = (compiled.inside_key(flat, lay, CAT, p) for p in ("a", "b"))
        self.assertEqual(ka, kb)
        self.write("t.fk", WORLD.replace("gb = Assembler<recipe=iron-gear-wheel> @(9, 3)",
                                         "gb = Assembler<recipe=iron-gear-wheel> @(10, 3)"))
        flat = elaborate_file(path, CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        self.assertNotEqual(compiled.inside_key(flat, lay, CAT, "a"), ka)

    def test_fk_compile_then_the_first_world_build_routes_no_inside(self):
        from fkcore.__main__ import main
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(["compile", os.path.join(self.dir, "nauvis.build.fkb"), "Gears"])
        self.assertEqual(code, 0)
        text = self.read("out/route.txt")
        self.assertIn("t: compile a: 2 inner nets routed and stored (Gears ", text)
        self.assertIn("t: compile b: the same inside as a", text)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "t.fkp")))   # nothing written
        first, checks = self.build()
        self.assertIn("t: 2 routed, 4 kept (0 pinned from the committed .fkp, 4 from compiled "
                      "modules)", first)
        self.assertIn("6 nets: 6 connected", checks)
        _again, _ = self.build()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(["compile", os.path.join(self.dir, "nauvis.build.fkb"), "Gears"])
        self.assertIn("t: compile a: already compiled (Gears ", self.read("out/route.txt"))

    def test_reuse_lab_takes_what_the_lab_routed(self):
        # <run>/game is the build; <run>/lab/gears is a lab build of the module (fkcore.lab)
        game, ws = os.path.join(self.dir, "game"), os.path.join(self.dir, "lab", "gears")
        for d in (game, ws):
            os.makedirs(d)
            for f in ("nauvis.surface", "nauvis.build.fkb"):
                shutil.copy(os.path.join(self.dir, f), d)
        with open(os.path.join(ws, "t.fk"), "w", encoding="utf-8") as fh:
            fh.write(WORLD.replace("b = Gears @(6, 20)", "b = Gears @(30, 30)"))
        code, _ctx = flow.run(os.path.join(ws, "nauvis.build.fkb"), cat=CAT, echo=lambda _l: None)
        self.assertEqual(code, 0)
        shutil.copy(os.path.join(self.dir, "t.fk"), game)
        code, _ctx = flow.run(os.path.join(game, "nauvis.build.fkb"), cat=CAT,
                              echo=lambda _l: None, extra=["route --only stale --reuse-lab"])
        self.assertEqual(code, 0)
        with open(os.path.join(game, "out", "route.txt"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("t: 2 routed, 4 kept (0 pinned from the committed .fkp, 4 from compiled "
                      "modules)", text)

    def test_compiled_no_turns_it_off(self):
        self.build(["route --only stale --compiled no"])
        self.assertFalse(os.path.isdir(os.path.join(self.dir, "out", "design", "modules")))


if __name__ == "__main__":
    unittest.main()
