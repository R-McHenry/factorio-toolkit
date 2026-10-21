"""A sub-module instance's rot turns its whole contents inside the module's frame."""
import math
import os
import unittest

from fkcore import compose, connect, expand, fkp, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()
NAUVIS = os.path.join(os.path.dirname(__file__), "..", "games", "nauvis")

BLOCK = """
module Block {
    ore   = MinerRow<n=2, resource=iron-ore>    @(14, 0, rot 2)
    coal  = MinerRow<n=1, resource=coal>        @(24, 0, rot 2)
    smelt = SmelterRow<n=2, recipe=iron-plate>  @(6, 12)
    gears = AsmRow<n=1, recipe=iron-gear-wheel> @(6, 24)
    net ore_: ore -> smelt
    net fuel: coal -> smelt
    net plate: smelt -> gears
}
"""
X0, Y0 = 4, 4                       # where every test puts the module
ROWS = ("b/ore", "b/coal", "b/smelt", "b/gears")


def build(text, path="t.fk"):
    f = lang.parse(text, path)
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay, notes = expand.expand_factory(flat, CAT)
    return flat, lay, notes


def placed(rot):
    return build(BLOCK + f"b = Block @({X0}, {Y0}, rot {rot})\n")


def turned(x, y, d, rot, size):
    """A point of the rot-0 layout where turning the module ``rot`` puts it."""
    tx, ty, td = compose.turn(float(x) - X0, float(y) - Y0, d, rot, size)
    return tx + X0, ty + Y0, td


def tiles(lay):
    return {t: k for k, e in lay.entities.items() for t in fkp.tiles_of(CAT, e)}


def where(e):
    return e.name, float(e.x), float(e.y), e.dir


class ModuleRotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flat0, cls.lay0, cls.notes0 = placed(0)
        assert all("no net (UNFED/UNCONSUMED)" in n for n in cls.notes0), cls.notes0  # the gears
        # the module's frame: its origin to the far edges of its rows' frames
        boxes = [expand.frame_of(cls.flat0, cls.lay0, p, CAT) for p in ROWS]
        cls.size = (max(b[2] for b in boxes) - X0, max(b[3] for b in boxes) - Y0)

    def test_rot_0_adds_the_hints(self):
        rec = self.lay0.insts["b/ore"]
        self.assertEqual((rec.x, rec.y, rec.rot), (X0 + 14, Y0, 2))
        self.assertEqual(self.size, (27, 31))

    def test_every_entity_lands_where_turning_the_rot_0_layout_puts_it(self):
        for rot in range(4):
            _flat, lay, notes = placed(rot)
            self.assertEqual(notes, self.notes0, rot)
            self.assertEqual(fkp.invariants(lay, CAT), [], rot)
            self.assertEqual(sorted(lay.entities), sorted(self.lay0.entities), rot)
            for key, e in self.lay0.entities.items():
                self.assertEqual(where(lay.entities[key]),
                                 (e.name,) + turned(e.x, e.y, e.dir, rot, self.size), (rot, key))

    def test_tile_by_tile(self):
        before = tiles(self.lay0)
        for rot in range(4):
            _flat, lay, _notes = placed(rot)
            want = {}
            for (tx, ty), key in before.items():
                x, y, _d = turned(tx + 0.5, ty + 0.5, None, rot, self.size)
                want[(math.floor(x), math.floor(y))] = key
            self.assertEqual(tiles(lay), want, rot)

    def test_rows_turn_with_the_module(self):
        for rot in range(4):
            flat, lay, _notes = placed(rot)
            for path in ROWS:
                rec0, rec = self.lay0.insts[path], lay.insts[path]
                self.assertEqual(rec.rot, (rec0.rot + rot) % 4, (rot, path))
                want = [(role, side, net, turned(x, y, d, rot, self.size))
                        for role, side, net, (x, y, d)
                        in expand.attach_points(self.flat0, self.lay0, path, CAT)]
                got = [(role, side, net, (float(x), float(y), d))
                       for role, side, net, (x, y, d) in expand.attach_points(flat, lay, path, CAT)]
                self.assertEqual(got, want, (rot, path))

    def test_nested_modules_compose(self):
        # Outer turns Block a quarter inside its own frame, then is turned a quarter itself
        flat, lay, notes = build(BLOCK + "module Outer {\n    blk = Block @(2, 3, rot 1)\n}\n"
                                 "o = Outer @(10, 5, rot 1)\n")
        self.assertEqual(notes, [n.replace("b/", "o/blk/", 1) for n in self.notes0])
        self.assertEqual(fkp.invariants(lay, CAT), [])
        w, h = self.size
        outer = (2 + h, 3 + w)                  # Block turned a quarter, at 2,3
        for key, e in self.lay0.entities.items():
            x, y, d = compose.turn(float(e.x) - X0, float(e.y) - Y0, e.dir, 1, self.size)
            x, y, d = compose.turn(x + 2, y + 3, d, 1, outer)
            self.assertEqual(where(lay.entities["o/blk/" + key[2:]]), (e.name, x + 10, y + 5, d),
                             key)
        self.assertEqual(lay.insts["o/blk/ore"].rot, 0)        # 2 + 1 + 1

    def test_an_imported_literal_turns_with_its_module(self):
        lit = ('module Plant {\n    r = Literal<file="plant-w3.json", box="-34,-39,-17,-23"> '
               '@(2, 1)\n}\n')
        src = os.path.join(NAUVIS, "t.fk")
        _flat, lay0, _notes = build(lit + f"p = Plant @({X0}, {Y0})\n", src)
        _flat, lay1, _notes = build(lit + f"p = Plant @({X0}, {Y0}, rot 1)\n", src)
        self.assertEqual(lay1.insts["p/r"].rot, 1)
        self.assertTrue(lay0.entities)
        for key, e in lay0.entities.items():
            self.assertEqual(where(lay1.entities[key]),
                             (e.name,) + turned(e.x, e.y, e.dir, 1, (2 + 17, 1 + 16)), key)

    def test_nets_connect_after_routing_in_every_rot(self):
        for rot in range(4):
            flat, lay, _notes = placed(rot)
            r = route.route_layout(flat, lay, CAT)
            self.assertEqual(r.failed, {}, (rot, r.lines))
            self.assertEqual(fkp.invariants(r.layout, CAT, nets=flat.nets), [], rot)
            rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
            self.assertEqual({n: x.status for n, x in rep.nets.items()},
                             {n: "connected" for n in flat.nets}, (rot, rep.lines()))
            self.assertEqual(rep.leaks, [], rot)


if __name__ == "__main__":
    unittest.main()
