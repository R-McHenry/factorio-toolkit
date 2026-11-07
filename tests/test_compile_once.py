"""PLAN-3.0 §4, sealed modules compile once: each sealed module routes alone in its frame, a twin
(the same module on the same ground) takes the routes the first one laid, moved to its frame, and
the compiled store keeps them for the next build."""
import os
import tempfile
import unittest

from fkcore import expand, fkp as fkpmod, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

CELL = """
module Gears size 20x10 {
  c = Chest<requester, item=iron-plate, rate=1> @(1, 1)
  a = Assembler<recipe=iron-gear-wheel> @(8, 1)
  b = Chest<provider> @(18, 5)
  net fe: c -> a
  net g: a -> b
}
"""

THREE = CELL + """
ga = Gears @(0, 0)
gb = Gears @(0, 12)
gc = Gears @(24, 0)
"""

# gc's chest stands elsewhere: its ground is not the others', so it is laid on its own
ODD = CELL + """
module Gears2 size 20x10 {
  c = Chest<requester, item=iron-plate, rate=1> @(1, 6)
  a = Assembler<recipe=iron-gear-wheel> @(8, 1)
  b = Chest<provider> @(18, 5)
  net fe: c -> a
  net g: a -> b
}
ga = Gears @(0, 0)
gb = Gears2 @(0, 12)
"""

# a parent sealed module holding two twin cells and a net of its own between them
NESTED = CELL + """
module Pair size 50x12 {
  x = Gears @(0, 0)
  y = Gears @(26, 0)
  s = Chest<requester, item=iron-plate, rate=1> @(22, 10)
  t = Chest<provider> @(26, 11)
  net p: s -> t
}
pa = Pair @(0, 0)
pb = Pair @(0, 20)
"""


def placed(text):
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    return flat, expand.expand_factory(flat, CAT)[0]


def carriers(lay, prefix, dx=0, dy=0):
    return sorted((e.key.replace(prefix, "@", 1), e.name, e.x - dx, e.y - dy, e.dir)
                  for k, e in lay.entities.items() if k.startswith("~" + prefix))


def compile_line(r):
    return next(ln for ln in r.lines if ln.startswith("compile"))


class CompileOnceTest(unittest.TestCase):
    def test_a_twin_takes_the_first_ones_routes(self):
        flat, lay = placed(THREE)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})
        self.assertIn("3 sealed modules", compile_line(r))
        self.assertIn("2 laid as a twin", compile_line(r))
        self.assertEqual(carriers(r.layout, "ga/"), carriers(r.layout, "gb/", 0, 12))
        self.assertEqual(carriers(r.layout, "ga/"), carriers(r.layout, "gc/", 24, 0))
        self.assertTrue(carriers(r.layout, "ga/"))
        self.assertEqual(fkpmod.invariants(r.layout, CAT), [])
        self.assertEqual(route.seal_checks(flat, r.layout, CAT), [])
        self.assertIn("compiled once", next(ln for ln in r.lines if ln.startswith("routed    gb/g")))

    def test_another_ground_is_laid_on_its_own(self):
        flat, lay = placed(ODD)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})
        self.assertIn("0 laid as a twin", compile_line(r))

    def test_nested_twins_and_their_parents(self):
        flat, lay = placed(NESTED)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})
        # four cells (one laid, three twins) and two parents (one laid, one twin)
        self.assertIn("6 sealed modules", compile_line(r))
        self.assertIn("4 laid as a twin", compile_line(r))
        self.assertEqual(carriers(r.layout, "pa/"), carriers(r.layout, "pb/", 0, 20))
        self.assertEqual(fkpmod.invariants(r.layout, CAT), [])
        self.assertEqual(route.seal_checks(flat, r.layout, CAT), [])

    def test_the_store_keeps_a_compiled_module_for_the_next_build(self):
        with tempfile.TemporaryDirectory() as store:
            flat, lay = placed(THREE)
            first = route.route_layout(flat, lay, CAT, store=store)
            self.assertIn("1 stored", compile_line(first))
            self.assertEqual(len(os.listdir(store)), 1)
            # the next build has the module somewhere else: it is laid from the store
            flat, lay = placed(CELL + "gz = Gears @(40, 30)\n")
            r = route.route_layout(flat, lay, CAT, store=store)
            self.assertEqual(r.failed, {})
            self.assertIn("1 from the compiled store", compile_line(r))
            self.assertEqual(carriers(first.layout, "ga/"), carriers(r.layout, "gz/", 40, 30))
            self.assertEqual(fkpmod.invariants(r.layout, CAT), [])

    def test_a_stored_module_of_another_router_version_is_laid_again(self):
        with tempfile.TemporaryDirectory() as store:
            flat, lay = placed(CELL + "ga = Gears @(0, 0)\n")
            route.route_layout(flat, lay, CAT, store=store)
            saved = route.COMPILE_VERSION
            route.COMPILE_VERSION = saved + "-next"
            try:
                r = route.route_layout(flat, lay, CAT, store=store)
            finally:
                route.COMPILE_VERSION = saved
            self.assertIn("0 from the compiled store", compile_line(r))

    def test_a_twin_that_does_not_fit_is_laid_on_its_own(self):
        flat, lay = placed(THREE)
        js = route.jobs(flat, lay, CAT)
        sealed = {}
        for path in ("ga", "gb"):
            x0, y0, x1, y1 = expand.frame_of(flat, lay, path, CAT)
            sealed[path] = (x0, y0, x1, y1, set())
        r = route.route_layout(flat, lay, CAT)
        got = route._moved_routes(
            {n: [e for e in r.layout.entities.values() if e.attrs.get("net") == n]
             for n in ("ga/fe", "ga/g")}, ["ga/fe", "ga/g"], "ga", sealed["ga"], "gb",
            sealed["gb"])
        self.assertEqual(set(got), {"gb/fe", "gb/g"})
        ground = list(lay.entities.values())
        self.assertTrue(route._fits(CAT, got, ground, sealed["gb"], frozenset(), frozenset(), {},
                                    {"gb/fe", "gb/g"}))
        tile = next(iter(fkpmod.tiles_of(CAT, got["gb/g"][0])))
        self.assertFalse(route._fits(CAT, got, ground, sealed["gb"], frozenset(),
                                     frozenset({tile}), {}, {"gb/fe", "gb/g"}))
        self.assertFalse(route._fits(CAT, got, ground, sealed["gb"], frozenset(), frozenset(),
                                     {tile: {"other"}}, {"gb/fe", "gb/g"}))
        self.assertTrue(js)

    def test_unit_and_names(self):
        sealed = {"a": None, "a/b": None}
        self.assertEqual(route._unit("a/b/n", sealed), "a/b")
        self.assertEqual(route._unit("a/n", sealed), "a")
        self.assertEqual(route._unit("n", sealed), "")
        self.assertEqual(route._unit("a/b/x|a/b/y", sealed), "a/b")
        self.assertEqual(route._renamed("a/b/x|a/b/y", "a/b", "c"), "c/x|c/y")
        self.assertEqual(route._renamed("a/b/x+a/b/y", "a/b", ""), "x+y")
        self.assertIsNone(route._renamed("a/b/x|q/y", "a/b", "c"))
        self.assertEqual(route._prefixed("x+y", "c/d"), "c/d/x+c/d/y")

    def test_a_lane_pairs_inserter_keeps_its_plus(self):
        # the megaloop's twins: a lane pair's inserter is written a+b, its job (and key) a|b
        e = fkpmod.Entity("~u/x|u/y/i0", "fast-inserter", 1.5, 2.5, 4, {"net": "u/x+u/y"})
        got = route._moved_entity(e, "u/x|u/y", "v/x|v/y", 10, 0, "u", "v")
        self.assertEqual((got.key, got.attrs["net"], got.x), ("~v/x|v/y/i0", "v/x+v/y", 11.5))
        with tempfile.TemporaryDirectory() as store:
            self.assertEqual(route._store_save(store, "k", "u", (0, 0, 9, 9, None),
                                               {"u/x|u/y": [e]}), 1)
            back = route._store_load(store, "k", "w", (5, 5, 14, 14, None))
            self.assertEqual(back["w/x|w/y"][0].attrs["net"], "w/x+w/y")
            self.assertEqual(back["w/x|w/y"][0].key, "~w/x|w/y/i0")


if __name__ == "__main__":
    unittest.main()
