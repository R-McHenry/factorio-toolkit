"""PLAN-ORGANIC D5 (2026-11-09): the toolkit measures the hierarchy. The megabelt's flower routed
67 to 118 nets at each of eight levels, took 35 minutes a build, and every report read "all
connected"; nothing said which level took the time, and the designers blamed the router.

- `fk check` says `flat` for a level (the top of a file, or one sealed module) that routes more
  than ``elaborate.LEVEL_NETS`` nets at once; a module instanced many times is named once.
- the route step writes a `level` line per level that searched (nets, failed, seconds, frame),
  and a level past ``route.LEVEL_SECONDS`` or ``LEVEL_NETS`` is the check `flat` in the report.
- `ports-touch`: two fluid ports of different fluids on adjacent tiles of one module side.
- cover power on a sealed unit with no room for a pole says so instead of crashing (3.1.3's
  TypeError in ``cover._why_not``, fk-run2 FRICTION.md).
"""
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from fkcore import cover, flow, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import LEVEL_NETS, elaborate

CAT = Catalog.load()


def nets(n, prefix=""):
    """``n`` chest-to-chest nets, each its own pair of chests."""
    out = []
    for i in range(n):
        out.append(f"{prefix}c{i} = Chest<requester, item=iron-plate, rate=1> @({2 * i}, 0)")
        out.append(f"{prefix}b{i} = Chest<provider> @({2 * i}, 4)")
        out.append(f"net {prefix}n{i}: {prefix}c{i} -> {prefix}b{i}")
    return "\n".join(out) + "\n"


def checks(src, code):
    f = lang.parse(src, "t.fk")
    return [c for c in elaborate(f, dict(f.modules), CAT, "t").checks if c.code == code]


class FlatOnPaperTest(unittest.TestCase):
    def test_a_top_level_past_the_limit_is_flat(self):
        got = checks(nets(LEVEL_NETS + 1), "flat")
        self.assertEqual(len(got), 1, got)
        self.assertEqual(got[0].where, "the top level of t")
        self.assertIn(f"{LEVEL_NETS + 1} nets route at one level (the limit is {LEVEL_NETS})",
                      got[0].msg)
        self.assertIn("Seal a sub-unit", got[0].msg)

    def test_a_level_at_the_limit_is_not(self):
        self.assertEqual(checks(nets(LEVEL_NETS), "flat"), [])

    def test_a_module_instanced_twice_is_named_once(self):
        src = (f"module Many size {2 * (LEVEL_NETS + 1)}x6 {{\n" + nets(LEVEL_NETS + 1) + "}\n"
               "a = Many @(0, 0)\nb = Many @(0, 10)\n")
        got = checks(src, "flat")
        self.assertEqual([c.where for c in got], ["module Many"])
        self.assertIn(f"{LEVEL_NETS + 1} nets route at one level", got[0].msg)

    def test_sealed_sub_units_split_the_count(self):
        # the same nets, three to a sealed cell: no level routes more than three
        cells = "".join(f"u{k} = Cell @(0, {8 * k})\n" for k in range((LEVEL_NETS + 1) // 3 + 1))
        src = "module Cell size 6x6 {\n" + nets(3) + "}\n" + cells
        self.assertEqual(checks(src, "flat"), [])


class PortsTouchTest(unittest.TestCase):
    MOD = """module Chem size 12x8 {{
  port w_in : in water @s{a}
  port g_in : in {g} @s{b}
  m = Machine<entity=chemical-plant, recipe=sulfuric-acid> @(3, 1)
  net w: w_in -> m
  net g: g_in -> m
}}
c = Chem @(0, 0)
"""

    def test_different_fluids_on_adjacent_tiles(self):
        got = checks(self.MOD.format(a=3, b=4, g="petroleum-gas"), "ports-touch")
        self.assertEqual(len(got), 1, got)
        self.assertEqual(got[0].where, "port c/w_in")
        self.assertIn("@s3 (water) and c/g_in @s4 (petroleum-gas)", got[0].msg)
        self.assertIn("their pipes touch", got[0].msg)

    def test_a_tile_between_them_is_fine(self):
        self.assertEqual(checks(self.MOD.format(a=3, b=5, g="petroleum-gas"), "ports-touch"), [])

    def test_the_same_fluid_may_touch(self):
        self.assertEqual(checks(self.MOD.format(a=3, b=4, g="water"), "ports-touch"), [])


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


class LevelLinesTest(unittest.TestCase):
    """The route step's `level` lines on a world of two sealed twins (test_compiled's world)."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fklevels-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.write("t.fk", WORLD)
        self.write("nauvis.surface", "surface nauvis\nterrain none\n"
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

    def build(self):
        code, ctx = flow.run(os.path.join(self.dir, "nauvis.build.fkb"), cat=CAT,
                             echo=lambda _l: None)
        self.assertEqual(code, 0, ctx.log)
        return self.read("out/route.txt"), self.read("out/report_checks.txt"), ctx

    def test_one_line_per_level_that_searched(self):
        rt, rep, ctx = self.build()
        levels = [l.strip() for l in rt.splitlines() if l.strip().startswith("level ")]
        # the first Gears routed its two nets and the twin took them; the top level its two
        self.assertEqual(len(levels), 2, rt)
        self.assertTrue(any(l.startswith("level     a (Gears): 2 nets searched, 0 failed, ")
                            and l.rstrip().endswith("frame 16x8") for l in levels), levels)
        self.assertTrue(any(l.startswith("level     the top level: 2 nets searched, 0 failed, ")
                            for l in levels), levels)
        self.assertNotIn("flat", rep)
        self.assertEqual([c for _s, c in ctx.checks if c.code == "flat"], [])

    def test_a_slow_level_is_flat_in_the_report(self):
        with mock.patch.object(route, "LEVEL_SECONDS", 0.0):
            rt, rep, ctx = self.build()
        self.assertIn("; flat: over 60 nets or 0 s", rt)
        flat = [c for _s, c in ctx.checks if c.code == "flat"]
        self.assertEqual(sorted(c.where for c in flat), ["t a", "t top level"])
        self.assertIn("Gears routes 2 nets at one level in 0 s (16x8 frame; the limit is 60 nets "
                      "or 0 s a level): seal a sub-unit", next(c.msg for c in flat
                                                                if c.where == "t a"))
        self.assertIn("route         flat t a:", rep)


class WhyNotWithoutASizeTest(unittest.TestCase):
    """``cover._why_not`` on a sealed unit's pass: the layout has no size, only the frame."""

    def ground(self):
        return SimpleNamespace(spots_powering=lambda rect, s: [(0, 0), (1, 0)],
                               why=lambda spot: "frame", tiles=lambda spot: [spot], taken={})

    def test_no_size_names_the_frame_and_the_rule(self):
        why = cover._why_not(self.ground(), (2, 2, 3, 3), 2, "medium-electric-pole", None,
                             sealed=True)
        self.assertIn("2 outside the frame; a sealed cell powers only its own frame", why)
        self.assertIn("free a tile inside it for a pole, or move the entity into the parent", why)

    def test_a_size_still_reads_as_before(self):
        why = cover._why_not(self.ground(), (2, 2, 3, 3), 2, "medium-electric-pole", (13, 3))
        self.assertIn("2 outside the 13x3 frame", why)
        self.assertNotIn("sealed cell", why)


if __name__ == "__main__":
    unittest.main()
