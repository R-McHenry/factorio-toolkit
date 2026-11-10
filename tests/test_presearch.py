"""54-presearch: what a rebuild does before its first search, on the ground around each net.

- ``route._standing`` patches each faulty net on the graph of the ground around it
  (``route._Near``), not of the whole layout: the same patches, held nets and nets routed again as
  with the whole layout's graph (a ``_Near`` that never finds a window falls back to it).
- ``route.seal_checks`` judges each sealed module's entities near its frame, its own and its nets'
  carriers only: the same lines, in the same order, as walking every entity for every module.
"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from fkcore import flow, fkp, route
from fkcore.catalog import Catalog

CAT = Catalog.load()

MODS = """module M size 30x14 {
  port fe_in : in iron-plate @w5
  ga = Assembler<recipe=iron-gear-wheel> @(4, 1)
  box = Chest<provider, limit=4> @(20, 2)
  net fe: fe_in -> ga
  net g: ga -> box
}
src = Chest<requester, item=iron-plate, request=20> @(1, 52)
m = M @(14, 0)
net feed: src -> m.fe_in
"""

ROWS = """ore   = MinerRow<n=4, resource=iron-ore> @(2, 2)
smelt = SmelterRow<n=4, recipe=iron-plate> @(2, 14)
coal  = Chest<requester, item=coal, rate=1/s> @(26, 14)
box   = Chest<provider, limit=4> @(30, 24)
net ore: ore -> smelt
net fuel: coal -> smelt
net plates: smelt -> box
"""


def _seal_checks_whole(flat, lay, cat):
    """``seal_checks`` as it was before 54-presearch: every entity for every sealed module."""
    from fkcore.expand import frame_shape_of
    out, boxes, shapes = [], {}, {}
    for path in lay.insts:
        if path in flat.insts and path in flat.sealed:
            try:
                shape = frame_shape_of(flat, lay, path, cat)
            except Exception:
                continue
            boxes[path], shapes[path] = shape.box, shape

    def shared(path, net, tiles):
        scopes = [p for p in boxes if net.startswith(p + "/")]
        if not scopes:
            return False
        q = max(scopes, key=len)
        return not q.startswith(path + "/") and not path.startswith(q + "/") \
            and all(t in shapes[q] for t in tiles)
    for path, _rec in sorted(lay.insts.items()):
        if path not in boxes:
            continue
        x0, y0, x1, y1 = boxes[path]
        frame = shapes[path]
        where = f"{x0},{y0}..{x1 - 1},{y1 - 1}" if frame.is_box else \
            f"{x0},{y0}..{x1 - 1},{y1 - 1} ({frame.area} tiles of the box: its shape)"
        for key, e in lay.entities.items():
            net = e.attrs.get("net")
            tiles = fkp.tiles_of(cat, e)
            inside = all(t in frame for t in tiles)
            if key.startswith(path + "/") and not inside:
                out.append(f"FRAME     {key} ({e.name}) is part of sealed module {path} but stands "
                           f"outside its frame {where}: grow its size or move it in")
                continue
            if not net:
                continue
            mine = net == path or net.startswith(path + "/")
            if inside and not mine and not shared(path, net, tiles):
                out.append(f"crosses-frame      {key} ({net}) stands inside sealed module {path}: "
                           "a net crosses a sealed frame only at a port's edge")
            elif mine and not inside:
                out.append(f"crosses-frame      {key} ({net}) belongs to sealed module {path} but "
                           "stands outside its frame")
    return out


class PresearchTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fk54-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.write("nauvis.surface", "surface nauvis\nterrain none\n"
                                     "place t = t plot 0,0 60x60\n")
        self.write("nauvis.build.fkb", "read_surface nauvis\nread_terrain none\nelaborate\n"
                                       "place --keep pinned\nroute --only stale\nfloorplan\n"
                                       "report_checks\nwrite_layout\n")

    def write(self, name, text):
        with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def read(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8") as fh:
            return fh.read()

    def build(self):
        code, ctx = flow.run(os.path.join(self.dir, "nauvis.build.fkb"), cat=CAT,
                             echo=lambda _l: None)
        self.assertEqual(code, 0, ctx.log)
        return ctx

    def twice(self, first, second):
        """The rebuild after ``first`` with ``second``, on windowed graphs and on whole ones:
        -> ((route.txt, t.fkp entities) windowed, the same whole)."""
        self.write("t.fk", first)
        self.build()
        committed = self.read("t.fkp")
        out, kept = os.path.join(self.dir, "out"), os.path.join(self.dir, "out.first")
        shutil.copytree(out, kept)
        got = []
        for whole in (False, True):
            self.write("t.fkp", committed)
            shutil.rmtree(out)
            shutil.copytree(kept, out)            # the same out/ (design, store, frames) each time
            self.write("t.fk", second)
            with mock.patch.object(route._Near, "window",
                                   (lambda self, r: None) if whole else route._Near.window):
                self.build()
            text = self.read("out/route.txt")
            lay = fkp.load(os.path.join(self.dir, "t.fkp"))
            got.append((text, sorted((e.key, e.name, e.x, e.y, e.dir)
                                     for e in lay.entities.values())))
        return got

    def test_a_patch_on_the_ground_around_its_net_is_the_whole_layouts(self):
        near, whole = self.twice(MODS, MODS.replace(
            "net feed: src -> m.fe_in", "m2 = M @(14, 20)\nnet feed: src -> m.fe_in, m2.fe_in"))
        self.assertIn("patched   feed:", near[0])
        self.assertEqual(near, whole)

    def test_a_moved_chest_patches_alike(self):
        near, whole = self.twice(ROWS, ROWS.replace("@(30, 24)", "@(31, 24)"))
        self.assertEqual(near, whole)

    def test_seal_checks_are_the_whole_walks(self):
        ctx = self.build_mods()
        flat, lay = ctx.flats["t"], ctx.layouts["t"]
        self.assertEqual(route.seal_checks(flat, lay, CAT), _seal_checks_whole(flat, lay, CAT))
        # a carrier of the parent's net inside the module, the module's own net and machine
        # outside it: a crossing, a carrier out of its frame and a FRAME line
        lay = lay.copy()
        lay.add(fkp.Entity("~feed/zz9", "transport-belt", 20.5, 8.5, 0, {"net": "feed"}))
        lay.add(fkp.Entity("~m/g/zz9", "transport-belt", 5.5, 40.5, 0, {"net": "m/g"}))
        box = next(e for e in lay.entities.values() if e.key.startswith("m/box"))
        lay.entities[box.key] = fkp.Entity(box.key, box.name, 50.5, 50.5, box.dir, dict(box.attrs))
        got = route.seal_checks(flat, lay, CAT)
        self.assertEqual(got, _seal_checks_whole(flat, lay, CAT))
        self.assertTrue(any(ln.startswith("FRAME") for ln in got))
        self.assertTrue(any("stands inside sealed module m" in ln for ln in got))
        self.assertTrue(any("belongs to sealed module m" in ln for ln in got))

    def build_mods(self):
        self.write("t.fk", MODS)             # M declares a port: m is a sealed module
        return self.build()


if __name__ == "__main__":
    unittest.main()
