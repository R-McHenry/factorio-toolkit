"""43-hull (PLAN-ORGANIC H5, H6): the achieved hull. After a sealed module is built alone (a compile
unit, routed in its frame), its hull (entities, carriers, the 1-tile closure, its gap, clipped to
the frame it was routed in) is recorded in ``out/frames.json`` beside the design, and the readers
(``own_frame``, ``frame_shape_of``, ``planned_shape``) resolve a module's frame hull, then
territory (``out/territories.json``), then declaration. A no-op rebuild records the same hull and
routes nothing; a changed inside drops the hull; ``fk layout FILE MODULE`` lays the inside out in
the declared or assigned frame, never the hull; a module placed by territory builds with its
territory as its frame; shape.fk's two steps print what EXAMPLES.md quotes."""
import json
import os
import shutil
import tempfile
import unittest

from fkcore import expand, fkp as fkpmod, flow, hull, layout
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate_file
from fkcore.frame import Frame
from tests.test_examples_docs import DOCS, EX, SCRIPT

CAT = Catalog.load()
L_VERTS = [(0, 0), (20, 0), (20, 8), (10, 8), (10, 16), (0, 16)]
ELL = """# ell.fk: an L-shaped module built alone
module Ell shape (0,0) (20,0) (20,8) (10,8) (10,16) (0,16) {
  port fe_in : in iron-plate @w
  port g_out : out iron-gear-wheel @n12
  a = Assembler<recipe=iron-gear-wheel> @(4, 6)
  net fe: fe_in -> a
  net g: a -> g_out
}
ell = Ell @(2, 2)
src = Chest<requester, item=iron-plate, rate=1> @(0, 10)
c = Chest<provider, limit=100> @(16, 14)
net feed: src -> ell.fe_in
net gears: ell.g_out -> c
"""


def game(d, name, plot, text=None):
    """A paper game folder: the docs template's script, a surface placing ``name`` on ``plot``."""
    if text is not None:
        with open(os.path.join(d, name + ".fk"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    with open(os.path.join(d, "nauvis.build.fkb"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(SCRIPT)
    with open(os.path.join(d, "nauvis.surface"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"surface nauvis\nterrain none\nplace {name} = {name} plot 0,0 {plot}\n")


def build(d, name):
    """-> (exit code, out/route.txt lines, the summary line, the check codes)."""
    code, ctx = flow.run(os.path.join(d, "nauvis.build.fkb"), cat=CAT, echo=lambda _l: None)
    with open(os.path.join(d, "out", "route.txt"), encoding="utf-8") as fh:
        route = fh.read().splitlines()
    summary = ""
    path = os.path.join(d, "out", "report_checks.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            summary = next((l for l in fh.read().splitlines() if l.startswith(f"{name}: ")), "")
    return code, route, summary, sorted(c.code for _s, c in ctx.checks)


def frames(d):
    with open(os.path.join(d, "out", "frames.json"), encoding="utf-8") as fh:
        return json.load(fh)["hulls"]


def hull_lines(route):
    return [l.strip() for l in route if l.strip().startswith("hull ")]


class FrameInverseTest(unittest.TestCase):
    def test_unturn_is_the_inverse_of_turn_beyond_the_box_too(self):
        poly = Frame.from_polygon(L_VERTS)
        beyond = Frame.from_tiles(list(poly) + [(-3, 2), (-1, -2), (22, 5), (7, 18)])
        for f in (poly, beyond, Frame.from_box(5, 3)):
            for rot in range(4):
                self.assertEqual(f.turn(rot, (20, 16)).unturn(rot, (20, 16)), f, (f, rot))
        # a box at the origin turns by the fast path and unturns the same
        self.assertEqual(Frame.from_box(5, 3).turn(1).unturn(1, (5, 3)), Frame.from_box(5, 3))

    def test_minus(self):
        a, b = Frame.from_box(6, 4), Frame.from_box(2, 1, 4, 3)
        self.assertEqual(a.minus(b).area, 24 - 4)
        self.assertEqual(a.minus(b).overlap(b).area, 0)
        self.assertEqual(a.minus(a).area, 0)


class HullRecordTest(unittest.TestCase):
    """One build of the L: the hull is the closure of what the unit laid, inside the polygon;
    the readers resolve it first; module mode does not."""

    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp(prefix="fkhull-")
        game(cls.d, "ell", "30x30", ELL)
        cls.code, cls.route, cls.summary, cls.checks = build(cls.d, "ell")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d, True)

    def test_the_hull_is_the_closure_of_the_unit_inside_its_frame(self):
        self.assertEqual(self.code, 0)
        self.assertIn(" 0 unrouted", self.summary)
        entry = frames(self.d)["ell"]
        self.assertEqual(entry["module"], "Ell")
        self.assertEqual(entry["frame"]["source"], "declared")
        self.assertEqual((entry["frame"]["area"], entry["declared"]["area"]), (240, 240))
        self.assertEqual(entry["at"], [2, 2, 0])
        got = Frame.from_runs(tuple(r) for r in entry["runs"])
        poly = Frame.from_polygon(L_VERTS)
        self.assertTrue(got.tiles() <= poly.tiles())
        self.assertLess(got.area, poly.area)
        # the same closure from the committed layout: the unit's machines and its nets' carriers
        lay = fkpmod.load(os.path.join(self.d, "ell.fkp"))
        tiles = set()
        for e in lay.entities.values():
            if e.owner.startswith("ell/") or e.owner.startswith("~ell/"):
                tiles |= {(int(x), int(y)) for x, y in fkpmod.tiles_of(CAT, e)}
        want = Frame.from_tiles(tiles).grow(1).overlap(poly.moved(2, 2)).moved(-2, -2)
        self.assertEqual(got, want)
        self.assertEqual(entry["area"], want.area)
        lines = hull_lines(self.route)
        self.assertEqual(lines[0], f"hull      ell: {want.area} of the 240 tiles of its declared "
                                   f"frame ({want.area * 100 // 240} %), {240 - want.area} left free")
        self.assertEqual(lines[1], "hull      1 sealed module in out/frames.json: 1 new or changed")
        self.assertEqual(entry["inside"], hull.inside_sha(
            elaborate_file(os.path.join(self.d, "ell.fk"), CAT), "ell"))

    def test_the_readers_resolve_the_hull_first(self):
        flat = elaborate_file(os.path.join(self.d, "ell.fk"), CAT)
        entry = frames(self.d)["ell"]
        own = Frame.from_runs(tuple(r) for r in entry["runs"])
        self.assertEqual(hull.source(flat, "ell"), "hull")
        self.assertEqual(hull.achieved(flat, "ell"), own)
        self.assertIsNone(hull.assigned(flat, "ell"))
        lay, _notes = expand.expand_factory(flat, CAT)
        self.assertEqual(expand.frame_shape_of(flat, lay, "ell", CAT), own.moved(2, 2))
        self.assertEqual(expand.planned_shape(flat, "ell", CAT), own.moved(2, 2))
        self.assertIsNone(expand.planned_frame(flat, "ell", CAT))       # size.py reads boxes
        self.assertEqual(expand.own_frame(flat.insts["ell"]), own)
        text = expand.explain(flat, lay, "ell", CAT)
        self.assertIn("frame     240 tiles of the 20x16 box", text)
        self.assertIn(f"hull      {own.area} tiles of the 240 (built alone, out/frames.json; "
                      f"{240 - own.area} left free):", text)
        rows = text[text.index("  hull "):].splitlines()[1:]
        rows = [r.strip() for r in rows if r.strip() and r.strip()[0] in "#."]
        self.assertEqual(rows, own.rows_text((0, 0, 20, 16)))
        # the parent's layout places the module by its hull
        hull.laying_out(flat, None)
        built = layout.build_spec(flat, CAT, plot=(30, 30))
        i = built.paths.index("ell")
        self.assertEqual(set(built.spec.insts[i].shapes[0][0]), own.tiles())

    def test_module_mode_lays_out_in_the_declared_frame(self):
        flat = elaborate_file(os.path.join(self.d, "ell.fk"), CAT)
        self.assertEqual(hull.laying_out(flat, "Ell"), "ell")
        self.assertEqual(hull.source(flat, "ell"), "declared")
        built = layout.build_spec(flat, CAT, module="Ell")
        self.assertEqual(set(built.spec.blocked), {(x, y) for x in range(10, 20) for y in range(8, 16)})
        hull.laying_out(flat, None)
        self.assertEqual(hull.source(flat, "ell"), "hull")

    def test_a_turned_instance_records_its_hull_in_its_own_frame(self):
        d = tempfile.mkdtemp(prefix="fkhullr-")
        self.addCleanup(shutil.rmtree, d, True)
        text = ELL.replace("ell = Ell @(2, 2)", "ell = Ell @(20, 2, rot 1)") \
            .replace("c = Chest<provider, limit=100> @(16, 14)", "c = Chest<provider, limit=100> @(26, 10)")
        game(d, "ell", "34x30", text)
        code, route, summary, _c = build(d, "ell")
        self.assertEqual(code, 0, summary)
        entry = frames(d)["ell"]
        self.assertEqual(entry["at"][2], 1)
        own = Frame.from_runs(tuple(r) for r in entry["runs"])
        self.assertTrue(own.tiles() <= Frame.from_polygon(L_VERTS).tiles())
        flat = elaborate_file(os.path.join(d, "ell.fk"), CAT)
        lay, _n = expand.expand_factory(flat, CAT)
        rec = lay.insts["ell"]
        placed = expand.frame_shape_of(flat, lay, "ell", CAT)
        self.assertEqual(placed, own.turn(1, (20, 16)).moved(rec.x, rec.y))
        # the module's own machine stands inside the placed hull
        for key, e in lay.entities.items():
            if key.startswith("ell/"):
                self.assertTrue(all(t in placed for t in fkpmod.tiles_of(CAT, e)), key)


class HullRefinesTest(unittest.TestCase):
    """Build, rebuild, change: a no-op rebuild keeps the hull and routes nothing; a changed inside
    drops the hull (the declared frame is read again) and the next build records a new one."""

    def test_noop_then_change(self):
        d = tempfile.mkdtemp(prefix="fkhull2-")
        self.addCleanup(shutil.rmtree, d, True)
        game(d, "ell", "30x30", ELL)
        code, route, _s, _c = build(d, "ell")
        self.assertEqual(code, 0)
        first = frames(d)["ell"]
        code, route, _s, _c = build(d, "ell")
        self.assertEqual(code, 0)
        summary = next(l for l in route if l.startswith("ell: ") and "routed" in l)
        self.assertIn("0 routed, 4 kept", summary)
        self.assertEqual(hull_lines(route), ["hull      1 sealed module in out/frames.json: unchanged"])
        # the hull is not in the unit's key: what the second build's entry differs in from the
        # first's is `standing` alone (the parent's gears belt through the notch stands inside
        # the L's claimed box: unit_parts filters standing entities by the box, wave 1's rule)
        # and `catalog`, which follows it; never `frame`, `width` or `height`
        store = os.path.join(d, "out", "compiled", "Ell")
        entries = []
        for f in sorted(os.listdir(store)):
            if f.endswith(".json"):
                with open(os.path.join(store, f), encoding="utf-8") as fh:
                    entries.append(json.load(fh)["inputs"]["parts"])
        self.assertLessEqual(len(entries), 2)
        if len(entries) == 2:
            p1, p2 = entries
            differ = sorted(n for n in set(p1) | set(p2) if p1.get(n) != p2.get(n))
            self.assertTrue(set(differ) <= {"standing", "catalog"}, differ)
        self.assertEqual(frames(d)["ell"]["runs"], first["runs"])
        # the inside changes: the hull is not read, and the build records a new one
        with open(os.path.join(d, "ell.fk"), encoding="utf-8") as fh:
            text = fh.read()
        with open(os.path.join(d, "ell.fk"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text.replace("@(4, 6)", "@(4, 4)"))
        flat = elaborate_file(os.path.join(d, "ell.fk"), CAT)
        self.assertEqual(hull.source(flat, "ell"), "declared")
        self.assertNotEqual(hull.inside_sha(flat, "ell"), first["inside"])
        code, route, _s, _c = build(d, "ell")
        self.assertEqual(code, 0)
        self.assertEqual(hull_lines(route)[-1], "hull      1 sealed module in out/frames.json: 1 new or changed")
        again = frames(d)["ell"]
        self.assertEqual(again["frame"]["source"], "declared")
        self.assertNotEqual(again["inside"], first["inside"])
        flat = elaborate_file(os.path.join(d, "ell.fk"), CAT)
        self.assertEqual(hull.source(flat, "ell"), "hull")


class TerritoryFrameTest(unittest.TestCase):
    """territory.fk: `fk layout --write` assigns each module a cell; the build reads the cell as
    the module's frame and records its hull; the next layout places the modules by their hulls."""

    def test_territory_is_the_frame_then_the_hull(self):
        d = tempfile.mkdtemp(prefix="fkhullt-")
        self.addCleanup(shutil.rmtree, d, True)
        shutil.copy(os.path.join(EX, "territory.fk"), d)
        src = os.path.join(d, "territory.fk")
        flat = elaborate_file(src, CAT)
        lines, code = layout.layout_file(src, flat, CAT, write=True, plot=(40, 40), sweeps=6)
        self.assertEqual(code, 0, "\n".join(lines))
        flat = elaborate_file(src, CAT)
        for p in ("a", "b"):
            # 43-territory: the cell is the declared frame plus room (the ground the module's
            # belts may cross), so a declared module's frame stays its declaration and the cell
            # holds it; a module without a declaration would take its cell as its frame
            self.assertEqual(hull.source(flat, p), "declared", p)
            cell = hull.assigned(flat, p)
            self.assertIsNotNone(cell, p)
            self.assertTrue(Frame.from_box(8, 8).tiles() <= cell.tiles(), p)
            self.assertGreaterEqual(cell.area, 64, p)
        game(d, "territory", "40x40")
        code, route, summary, _c = build(d, "territory")
        self.assertEqual(code, 0, summary)
        self.assertIn(" 0 unrouted", summary)
        got = frames(d)
        self.assertEqual(sorted(got), ["a", "b"])
        for p in ("a", "b"):
            self.assertEqual(got[p]["frame"]["source"], "declared", p)
            self.assertEqual(got[p]["frame"]["area"], 64)
            self.assertLessEqual(got[p]["area"], 64)
            self.assertTrue(Frame.from_runs(tuple(r) for r in got[p]["runs"]).tiles()
                            <= Frame.from_box(8, 8).tiles())
        self.assertEqual(hull_lines(route)[-1], "hull      2 sealed modules in out/frames.json: 2 new or changed")
        # the next layout reads the hulls: the modules' footprints are their hulls
        flat = elaborate_file(src, CAT)
        self.assertEqual([hull.source(flat, p) for p in ("a", "b")], ["hull", "hull"])
        hull.laying_out(flat, None)
        built = layout.build_spec(flat, CAT, plot=(40, 40))
        for p in ("a", "b"):
            i = built.paths.index(p)
            self.assertEqual(set(built.spec.insts[i].shapes[0][0]),
                             Frame.from_runs(tuple(r) for r in got[p]["runs"]).tiles(), p)


class ShapeExampleTest(unittest.TestCase):
    """shape.fk in its two steps, as chapter 6 tells it; EXAMPLES.md quotes what it prints."""

    def test_two_steps_and_the_docs_quotes(self):
        d = tempfile.mkdtemp(prefix="fkshape-")
        self.addCleanup(shutil.rmtree, d, True)
        shutil.copy(os.path.join(EX, "shape.fk"), d)
        src = os.path.join(d, "shape.fk")
        with open(os.path.join(DOCS, "EXAMPLES.md"), encoding="utf-8") as fh:
            docs = fh.read()
        flat = elaborate_file(src, CAT)
        lines, code = layout.layout_file(src, flat, CAT, module="Mod", write=True)
        self.assertEqual(code, 0)
        for line in lines:
            if line.startswith(("  took ", "  wrote ")):
                continue
            self.assertIn(line, docs, f"EXAMPLES.md does not quote: {line}")
        with open(src, encoding="utf-8") as fh:
            whole = fh.read()
        cut = whole[:whole.index("# -- step 2")]
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(cut)
        game(d, "shape", "36x30")
        code, route, summary, checks = build(d, "shape")
        self.assertEqual(code, 0, summary)
        self.assertIn(summary, docs)
        for line in hull_lines(route):
            self.assertIn(line, docs, f"EXAMPLES.md does not quote: {line}")
        entry = frames(d)["m"]
        poly = Frame.from_polygon([(0, 0), (24, 0), (24, 12), (16, 20), (8, 20), (0, 12)])
        own = Frame.from_runs(tuple(r) for r in entry["runs"])
        self.assertEqual((poly.area, entry["frame"]["area"]), (408, 408))
        self.assertTrue(own.tiles() <= poly.tiles())
        flat = elaborate_file(src, CAT)
        lay, _n = expand.expand_factory(flat, CAT)
        text = expand.explain(flat, lay, "m", CAT)
        block = text[text.index("  hull "):]
        for line in block.splitlines():
            self.assertIn(line.strip(), docs, f"EXAMPLES.md does not quote: {line}")
        # step 2: the parent puts Side's corner into the free ground and routes gears through it
        with open(src, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(whole)
        code, route, summary, checks = build(d, "shape")
        self.assertEqual(code, 0, summary)
        self.assertIn(" 0 unrouted", summary)
        self.assertIn(summary, docs)
        self.assertNotIn("overlap", checks)
        for line in hull_lines(route):
            self.assertIn(line, docs, f"EXAMPLES.md does not quote: {line}")
        flat = elaborate_file(src, CAT)
        lay, _n = expand.expand_factory(flat, CAT)
        self.assertEqual(expand.frame_overlaps(flat, lay, CAT), [])
        final = fkpmod.load(os.path.join(d, "shape.fkp"))
        placed_poly, placed_hull = poly.moved(2, 2), own.moved(2, 2)
        through = [e for e in final.entities.values() if e.attrs.get("net") == "gears"
                   and (int(e.x), int(e.y)) in placed_poly and (int(e.x), int(e.y)) not in placed_hull]
        self.assertTrue(through, "gears runs through what m left free")
        self.assertEqual(frames(d)["m"]["runs"], entry["runs"])


if __name__ == "__main__":
    unittest.main()
