"""41-hull (PLAN-ORGANIC part H, wave 1: H1 to H4). A frame is a tile set wherever the toolkit reads
one: ``Frame`` (a box, a polygon, a run list, a tile set) turns about the origin as ``compose.turn``
turns a point; ``shape (x,y) ...`` on the module line parses, a self-crossing one is a ``bad-shape``
line and the module is its box; ports land on the shape's boundary (``@n12`` the outermost tile of
column 12, a column the shape does not reach ``port-off-frame`` and moved); a rectangle written as
a shape builds exactly as its ``size``; an L-shaped module builds alone with its machines inside the
polygon, and a parent's net routes through its notch with no ``crosses-frame``; the readers
(``frame_shape_of``, ``frame_overlaps``, ``seal_checks``, ``explain``, ``layout._shapes``,
``build_spec``) see the polygon."""
import unittest

from fkcore import expand, fkp as fkpmod, flow, lang, layout, route
from fkcore.catalog import Catalog
from fkcore.compose import turn
from fkcore.elaborate import elaborate
from fkcore.frame import Frame, ShapeError, shape_problem

CAT = Catalog.load()

L_VERTS = [(0, 0), (20, 0), (20, 8), (10, 8), (10, 16), (0, 16)]      # a 20x16 box less its SE 10x8
HEX_VERTS = [(0, 0), (20, 0), (20, 18), (12, 26), (8, 26), (0, 18)]   # a 20x18 box with a 1:1 foot

ELL = """
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

BOX_MOD = """
module M size 20x10 {
  port fe_in : in iron-plate @w
  port g_out : out iron-gear-wheel @n12
  a = Assembler<recipe=iron-gear-wheel> @(8, 3)
  net fe: fe_in -> a
  net g: a -> g_out
}
m = M @(4, 4)
src = Chest<requester, item=iron-plate, rate=1> @(0, 8)
c = Chest<provider, limit=100> @(18, 0)
net feed: src -> m.fe_in
net gears: m.g_out -> c
"""


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def placed(text):
    flat = flat_of(text)
    lay, notes = expand.expand_factory(flat, CAT)
    return flat, lay, notes


def turned_tiles(frame, rot):
    """The frame's tiles turned by ``compose.turn`` (tile centres, then floored)."""
    w, h = frame.box[2], frame.box[3]
    out = set()
    for x, y in frame:
        tx, ty, _d = turn(x + 0.5, y + 0.5, None, rot, (w, h))
        out.add((int(tx // 1), int(ty // 1)))
    return out


class FrameTest(unittest.TestCase):
    def test_box_is_the_fast_path(self):
        b = Frame.from_box(4, 3)
        self.assertTrue(b.is_box)
        self.assertEqual((b.box, b.area, b.size), ((0, 0, 4, 3), 12, (4, 3)))
        self.assertEqual(b.runs(), [(0, 0, 4), (1, 0, 4), (2, 0, 4)])
        self.assertEqual(b.turn(1), Frame.from_box(3, 4))
        self.assertEqual(b.turn(2), b)
        self.assertEqual(Frame.from_box(2, 1, 6, 4).box, (2, 1, 6, 4))

    def test_polygon_rasterises_on_tile_boundaries(self):
        f = Frame.from_polygon(L_VERTS)
        self.assertEqual((f.box, f.area, f.is_box), ((0, 0, 20, 16), 240, False))
        rows = f.rows_text()
        self.assertEqual(rows[0], "#" * 20)
        self.assertEqual(rows[8], "#" * 10 + "." * 10)
        self.assertTrue(f.contains(9, 15) and not f.contains(10, 8) and (19, 7) in f)
        # a box with a tapering foot: both slopes 1:1, so row y below 18 holds the tile centres
        # strictly between x = y - 18 and x = 38 - y: 18, 16, ... 4 tiles (a centre on the edge
        # is outside: the frame is the tiles whose centres the polygon holds)
        hexish = Frame.from_polygon(HEX_VERTS)
        self.assertEqual(hexish.area, 20 * 18 + sum(range(4, 19, 2)))
        self.assertEqual(hexish.rows_text()[18], "." + "#" * 18 + ".")
        self.assertEqual(hexish.rows_text()[25], "." * 8 + "####" + "." * 8)

    def test_turn_is_compose_turn(self):
        for verts in (L_VERTS, HEX_VERTS):
            f = Frame.from_polygon(verts)
            for rot in range(4):
                t = f.turn(rot)
                self.assertEqual(t.tiles(), turned_tiles(f, rot), f"rot {rot}")
                self.assertEqual(t.box[:2], (0, 0))               # the turned frame's corner at the origin
        self.assertEqual(Frame.from_polygon(L_VERTS).turn(1).turn(3), Frame.from_polygon(L_VERTS))

    def test_grow_contains_boundary_and_nearest(self):
        f = Frame.from_polygon(L_VERTS)
        self.assertEqual(f.grow(1).box, (-1, -1, 21, 17))
        # the 22x18 box less what no tile of the L neighbours: the notch's inner 9x7, the east
        # column beside the notch (x 20, y 9..16) and the south row beside it (y 16, x 11..19)
        self.assertEqual(f.grow(1).area, 22 * 18 - 9 * 7 - 8 - 9)
        self.assertEqual(f.boundary("n"), [(x, 0) for x in range(20)])
        self.assertEqual(f.boundary("s"), [(x, 15) for x in range(10)] + [(x, 7) for x in range(10, 20)])
        self.assertEqual(f.boundary("e"), [(19, y) for y in range(8)] + [(9, y) for y in range(8, 16)])
        self.assertEqual(f.boundary("w"), [(0, y) for y in range(16)])
        self.assertEqual(f.boundary_at("s", 15), (15, 7))
        self.assertIsNone(f.boundary_at("n", 25))
        self.assertEqual(f.boundary_near("n", 25), (19, 0))
        self.assertEqual(f.nearest_boundary((15.5, 12.5), "e"), (9, 12))
        self.assertEqual(f.nearest_boundary((15.5, 12.5)), (15, 7))

    def test_overlap_runs_tiles_and_clip(self):
        f = Frame.from_polygon(L_VERTS)
        notch = Frame.from_box(12, 10, 20, 16)
        self.assertEqual(f.overlap(notch).area, 0)
        self.assertFalse(f.overlap(notch))
        arm = Frame.from_box(8, 6, 14, 10)
        self.assertEqual(f.overlap(arm).runs(), [(6, 8, 14), (7, 8, 14), (8, 8, 10), (9, 8, 10)])
        self.assertEqual(Frame.from_runs(f.runs()), f)
        self.assertEqual(Frame.from_tiles(f.tiles()), f)
        self.assertEqual(f.clip((5, 5, 15, 12)).area, 10 * 3 + 5 * 4)    # rows 5..7 full, 8..11 the stem
        self.assertEqual(f.moved(2, 3).box, (2, 3, 22, 19))
        self.assertTrue(f.overlaps_box((9, 9, 11, 11)) and not f.overlaps_box((10, 8, 20, 16)))

    def test_shape_problems(self):
        self.assertIn("crosses", shape_problem([(0, 0), (4, 4), (4, 0), (0, 4)]))
        self.assertIn("three or more", shape_problem([(0, 0), (4, 0)]))
        self.assertIn("behind the origin", shape_problem([(-1, 0), (4, 0), (4, 4), (-1, 4)]))
        self.assertIn("written twice", shape_problem([(0, 0), (4, 0), (4, 4), (4, 0), (0, 4)]))
        self.assertIn("no area", shape_problem([(0, 0), (4, 0), (8, 0)]))
        self.assertIn("fold back", shape_problem([(0, 0), (4, 0), (2, 0), (2, 4)]))
        self.assertIsNone(shape_problem(L_VERTS))
        self.assertIsNone(shape_problem(L_VERTS + [L_VERTS[0]]))          # closed explicitly
        with self.assertRaises(ShapeError):
            Frame.from_polygon([(0, 0), (4, 4), (4, 0), (0, 4)])


class ShapeLineTest(unittest.TestCase):
    def test_shape_parses_with_its_box_as_size(self):
        f = lang.parse(ELL, "t.fk")
        self.assertEqual(f.modules["Ell"].shape, L_VERTS)
        self.assertEqual(f.modules["Ell"].size, (20, 16))
        flat = flat_of(ELL)
        self.assertEqual(flat.insts["ell"].shape, L_VERTS)
        self.assertIn("ell", flat.sealed)
        self.assertEqual(flat.ports["ell/g_out"].shape, L_VERTS)
        self.assertEqual(expand.own_frame(flat.insts["ell"]), Frame.from_polygon(L_VERTS))

    def test_size_and_shape_together_and_too_few_corners_are_syntax(self):
        with self.assertRaises(lang.FkSyntaxError):
            lang.parse("module M shape (0,0) (4,0) (4,4) size 4x4 { }", "t.fk")
        with self.assertRaises(lang.FkSyntaxError):
            lang.parse("module M shape (0,0) (4,0) { }", "t.fk")
        with self.assertRaises(lang.FkSyntaxError):
            lang.parse("module M shape (0,0) (4.5,0) (4,4) { }", "t.fk")

    def test_self_crossing_is_bad_shape_and_the_module_is_its_box(self):
        text = ELL.replace("shape (0,0) (20,0) (20,8) (10,8) (10,16) (0,16)",
                           "shape (0,0) (20,16) (20,0) (0,16)")
        flat, lay, notes = placed(text)
        bad = [c for c in flat.checks if c.code == "bad-shape"]
        self.assertEqual(len(bad), 1, [str(c) for c in flat.checks])
        self.assertIn("crosses", bad[0].msg)
        self.assertIn("20x16 box", bad[0].msg)
        self.assertIsNone(flat.insts["ell"].shape)
        self.assertEqual(expand.frame_shape_of(flat, lay, "ell", CAT), Frame.from_box(2, 2, 22, 18))
        self.assertEqual(notes, [])

    def test_a_rectangle_shape_builds_as_its_size(self):
        as_shape = BOX_MOD.replace("size 20x10", "shape (0,0) (20,0) (20,10) (0,10)")
        fa, la, _ = placed(BOX_MOD)
        fb, lb, _ = placed(as_shape)
        self.assertTrue(expand.own_frame(fb.insts["m"]).is_box)
        self.assertEqual(expand.frame_shape_of(fb, lb, "m", CAT), expand.frame_shape_of(fa, la, "m", CAT))
        self.assertEqual({k: (p.x, p.y) for k, p in lb.ports.items()}, {k: (p.x, p.y) for k, p in la.ports.items()})
        ra, rb = route.route_layout(fa, la, CAT), route.route_layout(fb, lb, CAT)
        self.assertEqual(rb.failed, {})
        self.assertEqual(sorted((e.name, e.x, e.y, e.dir) for e in rb.layout.entities.values()),
                         sorted((e.name, e.x, e.y, e.dir) for e in ra.layout.entities.values()))
        self.assertEqual(route.seal_checks(fb, rb.layout, CAT), route.seal_checks(fa, ra.layout, CAT))
        self.assertNotIn("frame ", expand.explain(fb, rb.layout, "m", CAT))     # a box prints no rows


class PortsOnTheShapeTest(unittest.TestCase):
    def test_pinned_port_is_the_outermost_tile_of_its_column(self):
        flat, lay, notes = placed(ELL)
        self.assertEqual(notes, [])
        self.assertEqual((lay.ports["ell.g_out"].x, lay.ports["ell.g_out"].y), (12, 0))
        # a pin on the arm's north: column 15 of the south side is the notch's edge, y 7
        text = ELL.replace("@n12", "@s15")
        flat, lay, _ = placed(text)
        self.assertEqual((lay.ports["ell.g_out"].x, lay.ports["ell.g_out"].y), (15, 7))
        self.assertEqual([c.code for c in flat.checks if c.code.startswith("port")], [])

    def test_off_frame_pin_is_a_check_line_and_moves(self):
        flat, lay, notes = placed(ELL.replace("@n12", "@n25"))
        off = [c for c in flat.checks if c.code == "port-off-frame"]
        self.assertEqual(len(off), 1, [str(c) for c in flat.checks])
        self.assertIn("does not reach column 25", off[0].msg)
        self.assertIn("19,0", off[0].msg)
        self.assertEqual((lay.ports["ell.g_out"].x, lay.ports["ell.g_out"].y), (19, 0))
        self.assertEqual(notes, [])

    def test_unpinned_port_faces_its_partner_on_the_boundary(self):
        # an out port on the east side with its partner in the notch: the inner edge, x 9
        text = ELL.replace("@n12", "@e")
        flat, lay, _ = placed(text)
        p = lay.ports["ell.g_out"]
        self.assertIn((p.x, p.y), Frame.from_polygon(L_VERTS).boundary("e"))
        self.assertEqual(p.x, 9)
        self.assertGreaterEqual(p.y, 8)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})
        self.assertEqual(route.seal_checks(flat, r.layout, CAT), [])

    def test_a_record_off_the_boundary_is_chosen_again(self):
        flat = flat_of(ELL.replace("@n12", "@e"))
        port = flat.ports["ell/g_out"]
        on = fkpmod.PortRec("ell.g_out", 9, 12, 4, "L", "iron-gear-wheel")
        self.assertIsNone(expand.record_misfit(port, on))
        off = fkpmod.PortRec("ell.g_out", 19, 12, 4, "L", "iron-gear-wheel")      # in the notch
        self.assertIn("boundary of the shape", expand.record_misfit(port, off))
        pinned = flat_of(ELL).ports["ell/g_out"]
        self.assertIn("moves it to 12,0", expand.record_misfit(pinned, off))


class ReadersTest(unittest.TestCase):
    def test_frame_shape_of_turns_about_the_origin(self):
        flat, lay, _ = placed(ELL.replace("ell = Ell @(2, 2)", "ell = Ell @(2, 2, rot 1)"))
        got = expand.frame_shape_of(flat, lay, "ell", CAT)
        rec = lay.insts["ell"]
        self.assertEqual(got, Frame.from_polygon(L_VERTS).turn(1).moved(rec.x, rec.y))
        self.assertEqual(expand.frame_of(flat, lay, "ell", CAT), got.box)
        self.assertEqual(got.size, (16, 20))

    def test_the_notch_is_the_parents_ground(self):
        flat, lay, notes = placed(ELL)
        self.assertEqual(notes, [])
        fr = expand.frame_shape_of(flat, lay, "ell", CAT)
        self.assertEqual(fr.area, 240)
        # the module's own machine stands inside the polygon
        for key, e in lay.entities.items():
            if key.startswith("ell/"):
                self.assertTrue(all(t in fr for t in fkpmod.tiles_of(CAT, e)), key)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})
        self.assertEqual([ln for ln in r.lines if ln.startswith(("crosses-frame", "FRAME"))], [])
        self.assertEqual(route.seal_checks(flat, r.layout, CAT), [])
        self.assertEqual(fkpmod.invariants(r.layout, CAT), [])
        notch = {(x, y) for x in range(12, 22) for y in range(10, 18)}
        through = [k for k, e in r.layout.entities.items()
                   if e.attrs.get("net") == "gears" and (int(e.x), int(e.y)) in notch]
        self.assertTrue(through, "the parent's net routes through the notch")
        # and none of the module's own routes leave the polygon
        for k, e in r.layout.entities.items():
            if e.attrs.get("net", "").startswith("ell/"):
                self.assertTrue(all(t in fr for t in fkpmod.tiles_of(CAT, e)), k)

    def test_overlap_counts_shared_tiles_not_boxes(self):
        text = ELL + """
module Box size 8x6 {
  b = Chest<provider, limit=100> @(3, 2)
  port b_in : in iron-plate @w
  net x: b_in -> b
}
"""
        # a box in the notch: boxes meet, tiles do not
        flat, lay, _ = placed(text.replace("c = Chest<provider, limit=100> @(16, 14)",
                                           "c = Chest<provider, limit=100> @(30, 14)\nbx = Box @(13, 11)"))
        self.assertEqual(expand.frame_overlaps(flat, lay, CAT), [])
        # a box over the arm's inner corner (ell stands at 2,2: its arm is y 2..9, its stem
        # x 2..11): the shared box is 8x6 but only 32 of its 48 tiles are the L's
        flat, lay, _ = placed(text.replace("c = Chest<provider, limit=100> @(16, 14)",
                                           "c = Chest<provider, limit=100> @(30, 14)\nbx = Box @(8, 8)"))
        pairs = expand.frame_overlaps(flat, lay, CAT)
        self.assertEqual(pairs, [("bx", "ell", (8, 8, 16, 14), 32)])
        checks = flow._overlap_checks("t", flat, lay, CAT)
        self.assertIn("share 32 tiles in 8x6 at 8,8..15,13", checks[0].msg)

    def test_explain_prints_the_frame_as_rows(self):
        flat, lay, _ = placed(ELL)
        text = expand.explain(flat, lay, "ell", CAT)
        self.assertIn("size      20x16 (its own frame)", text)
        self.assertIn("frame     240 tiles of the 20x16 box", text)
        rows = [ln.strip() for ln in text.splitlines() if ln.strip().startswith(("#", "."))]
        self.assertEqual(rows, Frame.from_polygon(L_VERTS).rows_text())

    def test_layout_footprint_is_the_frame_per_rotation(self):
        flat = flat_of(ELL)
        frag, _b = expand.fragment_of(flat, "ell", CAT)
        shapes, _meta = layout._shapes(frag, expand.own_frame(flat.insts["ell"]))
        for rot in range(4):
            self.assertEqual(set(shapes[rot][0]), Frame.from_polygon(L_VERTS).turn(rot).tiles(), rot)
        boxed, _m = layout._shapes(frag)
        self.assertEqual(len(boxed[0][0]), 320)

    def test_layout_inside_the_shape_keeps_the_machine_in_the_polygon(self):
        text = ELL.replace("a = Assembler<recipe=iron-gear-wheel> @(4, 6)", "a = Assembler<recipe=iron-gear-wheel>")
        flat = flat_of(text)
        built = layout.build_spec(flat, CAT, module="Ell")
        self.assertEqual(built.spec.box, (0, 0, 20, 16))
        self.assertEqual(set(built.spec.blocked), {(x, y) for x in range(10, 20) for y in range(8, 16)})
        self.assertIn("shape of Ell", built.box_from)
        ports = [si for si, p in zip(built.spec.insts, built.paths) if p is None]    # the fixed terminals
        self.assertEqual({si.name: si.shapes[0][1][0][0] for si in ports},
                         {"ell/fe_in": (0, 8), "ell/g_out": (12, 0)})
        res = layout.place(built.spec)
        i = built.paths.index("ell/a")
        at = res.at[i]
        self.assertIsNotNone(at)
        foot = {(at[0] + dx, at[1] + dy) for dx, dy in built.spec.insts[i].shapes[at[2]][0]}
        self.assertTrue(foot <= Frame.from_polygon(L_VERTS).tiles(), foot)

    def test_hints_turn_about_the_origin_on_the_boxes_frame(self):
        frame = (0, 0, 20, 16)
        self.assertEqual(expand.corner_hint((2, 2, 1), frame), (2 - 16, 2, 1))
        self.assertEqual(expand.origin_hint(expand.corner_hint((2, 2, 1), frame), frame), (2, 2, 1))
        flat, lay, _ = placed(ELL.replace("ell = Ell @(2, 2)", "ell = Ell @(20, 2, rot 1)"))
        self.assertEqual(expand.frame_of(flat, lay, "ell", CAT), (4, 2, 20, 22))


if __name__ == "__main__":
    unittest.main()
