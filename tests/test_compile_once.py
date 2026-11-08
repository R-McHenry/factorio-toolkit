"""PLAN-3.0 §4, sealed modules compile once: each sealed module routes alone in its frame, a twin
(the same module on the same ground) takes the routes the first one laid, moved to its frame, and
the compiled store keeps them for the next build."""
import json
import os
import tempfile
import unittest

from fkcore import compiled, expand, fkp as fkpmod, lang, route
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

# 2.1.32: gb is ga turned 180 degrees (a `>` bay's chain): one key, its routes ga's turned
TURNED = CELL + """
ga = Gears @(0, 0)
gb = Gears @(20, 22, rot 2)
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

    def test_a_twin_turned_180_takes_the_first_ones_routes_turned(self):
        flat, lay = placed(TURNED)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})
        self.assertIn("1 laid as a twin", compile_line(r))
        # gb's frame is (0, 12)-(20, 22): ga's carriers turned about the frame's centre
        turned = sorted((k, n, 20 - x, 10 - (y - 12), None if d is None else (d + 8) % 16)
                        for k, n, x, y, d in carriers(r.layout, "gb/"))
        self.assertEqual(carriers(r.layout, "ga/"), turned)
        self.assertEqual(fkpmod.invariants(r.layout, CAT), [])
        self.assertEqual(route.seal_checks(flat, r.layout, CAT), [])
        with tempfile.TemporaryDirectory() as store:
            first = route.route_layout(flat, lay, CAT, store=store)
            self.assertEqual(first.failed, {})
            # the next build: both come from the store, ga's unturned and gb's turned back
            again = route.route_layout(flat, lay, CAT, store=store)
            self.assertIn("2 from the compiled store", compile_line(again))
            self.assertEqual(carriers(again.layout, "gb/"), carriers(r.layout, "gb/"))

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
        # 3.1: compiled.ROUTER is the one version; it is in the key, so a stored entry of another
        # router is never found (and one found under the key is checked too)
        with tempfile.TemporaryDirectory() as store:
            flat, lay = placed(CELL + "ga = Gears @(0, 0)\n")
            first = route.route_layout(flat, lay, CAT, store=store)
            self.assertEqual(first.compiled["ga"]["stored"], 1)
            saved = compiled.ROUTER
            compiled.ROUTER = saved + "-next"
            try:
                r = route.route_layout(flat, lay, CAT, store=store)
            finally:
                compiled.ROUTER = saved
            self.assertIn("0 from the compiled store", compile_line(r))
            self.assertNotEqual(r.compiled["ga"]["key"], first.compiled["ga"]["key"])
            self.assertEqual(len(os.listdir(os.path.join(store, "Gears"))) , 3)  # 2 + current
            # the same router again: the first entry is found and laid
            again = route.route_layout(flat, lay, CAT, store=store)
            self.assertEqual(again.compiled["ga"]["from"], "store")

    def test_two_builds_of_an_unchanged_module_reuse_the_entry(self):
        # 3.1: one store, one entry per key; the second build writes nothing and lays from it
        with tempfile.TemporaryDirectory() as store:
            flat, lay = placed(CELL + "ga = Gears @(0, 0)\n")
            first = route.route_layout(flat, lay, CAT, store=store)
            key = first.compiled["ga"]["key"]
            self.assertEqual(first.compiled["ga"]["from"], "routed")
            self.assertEqual(sorted(os.listdir(os.path.join(store, "Gears"))),
                             sorted([f"{key}.json", "current"]))
            with open(os.path.join(store, "Gears", "current"), encoding="utf-8") as fh:
                self.assertEqual(fh.read().strip(), key)
            with open(os.path.join(store, "Gears", f"{key}.json"), encoding="utf-8") as fh:
                entry = json.load(fh)
            self.assertEqual((entry["router"], entry["module"], entry["key"], entry["unit"]),
                             (compiled.ROUTER, "Gears", key, "ga"))
            self.assertEqual(sorted(entry["nets"]), ["fe", "g"])
            self.assertEqual(entry["inputs"]["frame"], [20, 10])
            second = route.route_layout(flat, lay, CAT, store=store)
            self.assertEqual(second.compiled["ga"], dict(first.compiled["ga"], **{
                "from": "store", "stored": 0}))
            self.assertEqual(sorted(os.listdir(os.path.join(store, "Gears"))),
                             sorted([f"{key}.json", "current"]))
            self.assertEqual(carriers(first.layout, "ga/"), carriers(second.layout, "ga/"))
            self.assertIn("1 from the compiled store, 0 stored", compile_line(second))

    def test_an_old_store_is_not_read_and_said_once(self):
        # Rory: old material is reference. The 2.1 router store (flat out/compiled/*.json) and
        # the 3.0 design store (out/design/modules/*/*.fkp) are not read; one line says so
        with tempfile.TemporaryDirectory() as out:
            store = os.path.join(out, "compiled")
            os.makedirs(store)
            with open(os.path.join(store, "abc.json"), "w", encoding="utf-8") as fh:
                fh.write('{"version": "route-3.0.3", "module": "ga", "nets": {}}')
            old = os.path.join(out, "design", "modules", "Gears")
            os.makedirs(old)
            with open(os.path.join(old, "def.fkp"), "w", encoding="utf-8") as fh:
                fh.write("fkp 1 factory @\n")
            self.assertEqual(compiled.old_material(out), (1, 1))
            flat, lay = placed(CELL + "ga = Gears @(0, 0)\n")
            r = route.route_layout(flat, lay, CAT, store=store)
            self.assertEqual(r.compiled["ga"]["from"], "routed")
            old_lines = [ln for ln in r.lines if ln.startswith("compiled  old")]
            self.assertEqual(len(old_lines), 1)
            self.assertIn("1 of the 2.1 router store", old_lines[0])
            self.assertIn("1 of the 3.0 design store", old_lines[0])
            self.assertIn("compiled: 1 module, 1 entry", compiled.status_lines(out)[0])
            self.assertIn("old entries not read", compiled.status_lines(out)[-1])

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
            st = compiled.Store(store)
            self.assertEqual(route._store_save(st, "k", "M", "u", (0, 0, 9, 9, None),
                                               {"u/x|u/y": [e]}), 1)
            self.assertTrue(os.path.exists(os.path.join(store, "M", "k.json")))
            back = route._store_load(st, "k", "M", "w", (5, 5, 14, 14, None))
            self.assertEqual(back["w/x|w/y"][0].attrs["net"], "w/x+w/y")
            self.assertEqual(back["w/x|w/y"][0].key, "~w/x|w/y/i0")


if __name__ == "__main__":
    unittest.main()
