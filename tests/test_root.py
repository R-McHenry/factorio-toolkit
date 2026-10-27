"""2.0.43 (PLAN-GLOBAL phase B): the root design - plots are the root's sealed instances.

1. **`design FILE`** in a surface file names the root `.fk`. `place` lines stay readable, and
   `design` wins when both are there.
2. **A factory file's body is a module**: `import Outpost from "outpost.fk"` needs no wrapping,
   and the plot's frame comes from its placement line (`size 84x114`) or a `size` line in the file.
3. **The plot list is derived** from the root's top-level sealed instances: name, file, x, y, rot,
   w, h, `@patch`; `gap N` rides on a placement, `retired`/`temporary` are flags on the instance
   line.
4. **Keys stay**: a plot's layout is its own `.fkp` with keys relative to its instance, so the
   composed surface is the same, key for key.
5. **`fk migrate-surface GAME`** writes the root `.fk` from the place lines and puts `design` in
   the surface file.

The world is `games/nauvis` - plant, boot (temporary) and main, the shape of run 1343's world.
"""
import contextlib
import io
import os
import shutil
import tempfile
import unittest

from fkcore import __main__ as cli, compose, fkp, flow, look, root, surface
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate, load

CAT = Catalog.load()
GAME = os.path.join(os.path.dirname(__file__), "..", "games", "nauvis")
SOURCES = ("main.fk", "plant.fk", "boot.fk", "plant-w3.json", "nauvis.surface",
           "nauvis.build.fkb")
LAYOUTS = ("main.fkp", "plant.fkp", "boot.fkp")
CHAIN = """\
fkp 1 surface nauvis
cover bridge power
e bridge/p0 medium-electric-pole -21.5,-21.5
e bridge/p1 medium-electric-pole -16.5,-16.5
e bridge/p2 medium-electric-pole -11.5,-11.5
e bridge/p3 medium-electric-pole -6.5,-6.5
e bridge/p4 medium-electric-pole -1.5,-1.5
e bridge/p5 medium-electric-pole 3.5,3.5
e bridge/p6 medium-electric-pole 5.5,7.5
"""


def quiet(fn, *a):
    """``fn(*a)`` with what it prints (stdout and stderr) captured: a CLI command's report, which
    a test asserts on."""
    with contextlib.redirect_stdout(io.StringIO()) as out, \
            contextlib.redirect_stderr(io.StringIO()) as err:
        code = fn(*a)
    return code, out.getvalue() + err.getvalue()


class World(unittest.TestCase):
    """A copy of `games/nauvis` with its committed layouts: composing it needs no build."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkroot-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        for n in SOURCES + LAYOUTS:
            shutil.copy(os.path.join(GAME, n), self.dir)
        with open(os.path.join(self.dir, "nauvis.fkp"), "w", newline="\n") as fh:
            fh.write(CHAIN)
        self.surface_path = os.path.join(self.dir, "nauvis.surface")

    def factories(self, sf):
        out = {}
        for p in sf.places.values():
            lay = fkp.load(os.path.join(self.dir, f"{p.module}.fkp"))
            lay.name = p.factory
            out[p.factory] = lay
        return out

    def composed(self, sf):
        return compose.compose(surface.floorplan(sf), self.factories(sf), CAT)

    def migrate(self):
        return quiet(cli.main, ["migrate-surface", self.dir])

    def design(self):
        return surface.load(self.surface_path)


class MigrateTest(World):
    """Item 5: `fk migrate-surface` writes the root .fk and adds `design`."""

    def test_the_design_composes_to_the_same_layout_key_for_key(self):
        before = self.composed(surface.load_game(self.dir, derive=False))
        code, report = self.migrate()
        self.assertEqual(code, 0, report)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "nauvis.fk")))
        self.assertIn("wrote nauvis.fk (3 plots: boot, main, plant)", report)
        after = self.design()
        self.assertEqual(after.design, "nauvis.fk")
        got = self.composed(after)
        self.assertEqual(got.rows(), before.rows())                    # keys, entities, nets
        self.assertEqual([(n, p.box(), p.params) for n, p in sorted(got.plots.items())],
                         [(n, p.box(), p.params) for n, p in sorted(before.plots.items())])
        self.assertEqual(got.problems, [])
        self.assertEqual(before.problems, [])

    def test_the_design_names_the_same_plots_as_the_place_lines(self):
        was = surface.load_game(self.dir, derive=False).places
        self.migrate()
        places, notes = root.places(os.path.join(self.dir, "nauvis.fk"))
        self.assertEqual(notes, [])
        self.assertEqual(sorted(places), sorted(was))
        for name, p in places.items():
            q = was[name]
            self.assertEqual((p.module, p.x, p.y, p.w, p.h, p.rot, p.gap, p.patch, p.lifecycle),
                             (q.module, q.x, q.y, q.w, q.h, q.rot, q.gap, q.patch, q.lifecycle),
                             name)
        self.assertEqual(places["boot"].lifecycle, "temporary until main.running")

    def test_the_place_lines_stay_as_comments_and_the_design_wins(self):
        with open(self.surface_path, encoding="utf-8") as fh:
            was = fh.read()
        self.migrate()
        with open(self.surface_path, encoding="utf-8") as fh:
            now = fh.read()
        self.assertIn("design   nauvis.fk", now)
        for line in was.splitlines():
            if line.startswith("place"):
                self.assertIn("# " + line, now)          # kept, as the record it was
        self.assertEqual(surface.load(self.surface_path).lines_places, {})   # nothing to win over

    def test_a_place_lines_only_game_still_has_its_plot_list(self):
        sf = surface.load(self.surface_path)                 # no design yet
        self.assertIsNone(sf.design)
        self.assertEqual(sorted(sf.places), ["boot", "main", "plant"])
        self.assertEqual(sf.places["boot"].lifecycle, "temporary until main.running")

    def test_a_design_and_place_lines_together_give_the_design(self):
        # a place line added after the migration: the design wins, the line is not placed
        self.migrate()
        with open(os.path.join(self.dir, "pad.fk"), "w", newline="\n") as fh:
            fh.write("# an empty plot\n")
        with open(self.surface_path, "a", newline="\n") as fh:
            fh.write("place later = pad plot 100,100 6x6\n")
        sf = self.design()
        self.assertEqual(sorted(sf.places), ["boot", "main", "plant"])   # the design wins
        self.assertEqual(sorted(sf.lines_places), ["later"])

    def test_a_migrate_twice_is_refused(self):
        self.assertEqual(self.migrate()[0], 0)
        code, report = self.migrate()
        self.assertEqual(code, 2)
        self.assertIn("already has `design nauvis.fk`", report)

    def test_a_surface_without_place_lines_is_refused(self):
        with open(self.surface_path, "w", newline="\n") as fh:
            fh.write("surface nauvis\nmode play\nterrain none\ncatalog base\n")
        code, report = self.migrate()
        self.assertEqual(code, 2)
        self.assertIn("no place lines to migrate", report)


class FlowTest(World):
    """The migrated world builds the same layout: the flow, the .fkp files and the checks."""

    def build(self):
        code, ctx = flow.run(os.path.join(self.dir, "nauvis.build.fkb"), cat=CAT,
                             echo=lambda _l: None)
        return code, ctx

    def test_the_world_builds_the_same_before_and_after_the_migration(self):
        code, was = self.build()
        self.assertEqual(code, 0, was.log)
        rows = was.composed.rows()
        files = {}
        for n in ("main.fkp", "plant.fkp", "boot.fkp", "nauvis.fkp"):
            with open(os.path.join(self.dir, n), encoding="utf-8") as fh:
                files[n] = fh.read()
        self.migrate()
        code, now = self.build()
        self.assertEqual(code, 0, now.log)
        self.assertEqual(now.composed.rows(), rows)               # the same world, key for key
        self.assertEqual(now.composed.problems, [])
        for name, text in files.items():
            with open(os.path.join(self.dir, name), encoding="utf-8") as fh:
                self.assertEqual(fh.read(), text, name)
        with open(os.path.join(self.dir, "out", "read_surface.txt"), encoding="utf-8") as fh:
            report = fh.read()
        self.assertIn("design nauvis.fk: 3 plots from its top-level sealed instances", report)
        self.assertEqual([(s, c) for s, c in now.checks if c.code == "DESIGN"], [])
        # `fk look` reads the same world: the derived plots, the committed surface .fkp
        sf, _lay, _path, seen = look.composed(self.dir, CAT)
        self.assertEqual(sf.design, "nauvis.fk")
        self.assertEqual(sorted(seen.plots), ["boot", "main", "plant"])
        self.assertEqual(len(seen.entities), len(was.composed.entities))

    def test_the_old_checks_still_fire_from_the_root_design(self):
        self.migrate()
        self.assertEqual(self.build()[0], 0)
        # 1. two plots over each other: the same check the place lines gave
        path = os.path.join(self.dir, "nauvis.fk")
        with open(path, encoding="utf-8") as fh:
            was = fh.read()
        with open(path, "w", newline="\n") as fh:
            fh.write(was.replace("main = Main @(8, 12) size 70x56",
                                 "main = Main @(-30, -35) size 70x56"))
        places, notes = root.places(path)
        self.assertEqual([p.x for p in places.values() if p.factory == "main"], [-30])
        s = self.composed(self.design())
        self.assertIn("plots main and plant overlap", s.problems)
        # 2. a plot's contents past its rectangle: `outside plot`
        with open(path, "w", newline="\n") as fh:
            fh.write(was.replace("main = Main @(8, 12) size 70x56",
                                 "main = Main @(8, 12) size 40x30"))
        s = self.composed(self.design())
        self.assertTrue(any("is outside plot main" in p for p in s.problems), s.problems)


class DeriveTest(World):
    """Items 2 and 3: a file body is a module, its size and the placement's flags."""

    def write(self, name, text):
        with open(os.path.join(self.dir, name), "w", newline="\n") as fh:
            fh.write(text)

    def test_a_file_body_is_a_module_and_its_size_line_is_its_frame(self):
        self.write("gears.fk", """\
size 24x10
g = AsmRow<n=1, recipe=iron-gear-wheel> @(2, 1)
inbox = Chest<requester, item=iron-plate, rate=1/s> @(0, 1)
net fe: inbox -> g
""")
        self.write("root.fk", 'import Gears from "gears.fk"\ngears = Gears @(10, 10)\n')
        f, modules = load(os.path.join(self.dir, "root.fk"))
        self.assertEqual(modules["Gears"].size, (24, 10))
        flat = elaborate(f, modules, CAT, "root")
        self.assertEqual(flat.sealed, {"gears"})
        self.assertEqual(flat.insts["gears"].size, (24, 10))
        places, notes = root.places(os.path.join(self.dir, "root.fk"))
        self.assertEqual(notes, [])
        self.assertEqual((places["gears"].module, places["gears"].w, places["gears"].h),
                         ("gears", 24, 10))

    def test_a_placement_size_is_the_plots_frame_and_seals_it(self):
        self.write("plot.fk", "# nothing yet\n")
        self.write("root.fk", 'import Pad from "plot.fk"\npad = Pad @(4, 5) size 30x20 gap 6\n')
        f, modules = load(os.path.join(self.dir, "root.fk"))
        flat = elaborate(f, modules, CAT, "root")
        self.assertEqual(flat.sealed, {"pad"})            # size alone seals (2.0.40)
        self.assertEqual(flat.insts["pad"].size, (30, 20))
        places, _notes = root.places(os.path.join(self.dir, "root.fk"))
        self.assertEqual((places["pad"].x, places["pad"].y, places["pad"].w, places["pad"].h,
                          places["pad"].gap), (4, 5, 30, 20, 6))

    def test_retired_and_temporary_are_flags_on_the_instance_line(self):
        self.write("root.fk", """\
import A from "a.fk"
import B from "b.fk"
a = A @(0, 0) size 10x10 retired
b = B @(20, 0) size 10x10 temporary until main.running
""")
        self.write("a.fk", "# old plot\n")
        self.write("b.fk", "# boot\n")
        places, _notes = root.places(os.path.join(self.dir, "root.fk"))
        self.assertEqual({n: p.lifecycle for n, p in places.items()},
                         {"a": "retired", "b": "temporary until main.running"})

    def test_a_patch_with_a_number_is_a_quoted_hint(self):
        self.write("root.fk", """\
import I from "i.fk"
i = I @(0, 0) size 10x10 @patch("iron-ore#2")
""")
        self.write("i.fk", "# iron plot\n")
        places, _notes = root.places(os.path.join(self.dir, "root.fk"))
        self.assertEqual(places["i"].patch, "iron-ore#2")

    def test_the_derivation_notes_what_is_not_a_plot(self):
        self.write("root.fk", """\
import A from "a.fk"
import C from "c.fk"
module Inline size 8x8 { c = Chest<provider> @(0, 0) }
a = A @(0, 0) size 10x10
a2 = A @(20, 0) size 10x10
inline = Inline @(40, 0)
noframe = A @(60, 0)
noat = C size 10x10
""")
        self.write("a.fk", "# plot\n")
        self.write("c.fk", "# the second plot file\n")
        places, notes = root.places(os.path.join(self.dir, "root.fk"))
        self.assertEqual(sorted(places), ["a", "a2"])       # 2.0.44: one file, two plots
        joined = " ".join(notes)
        self.assertIn("inline: module Inline is declared in the root file", joined)
        self.assertIn("noframe: no frame", joined)
        self.assertIn("noat: no @(x, y) hint", joined)

    def test_one_file_holds_several_plots(self):
        # 2.0.44: run 20261021-0110 placed relay.fk 14 times; 2.0.43 kept the first and dropped
        # the rest with a DESIGN note, so a migration lost plots
        self.write("relay.fk", "size 6x5\n")
        with open(self.surface_path, "a", newline="\n") as fh:
            fh.write("place relay1 = relay plot 200,0 6x5\n"
                     "place relay2 = relay plot 220,0 6x5 rot 1\n"
                     "place relay3 = relay plot 240,0 6x5\n")
        was = surface.load_game(self.dir, derive=False).places
        code, report = self.migrate()
        self.assertEqual(code, 0, report)
        with open(os.path.join(self.dir, "nauvis.fk"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(text.count('from "relay.fk"'), 1)    # one import per file
        now = self.design().places
        self.assertEqual(sorted(now), sorted(was))
        self.assertEqual([now[n].module for n in ("relay1", "relay2", "relay3")], ["relay"] * 3)
        self.assertEqual(now["relay2"].rot, 1)

    def test_a_migration_that_loses_a_plot_changes_nothing(self):
        # a place line whose plot the design cannot give back: a dash in its name, which an
        # instance name cannot carry, so the root file does not parse; nothing may change
        self.write("pad.fk", "# a pad\n")
        with open(self.surface_path, "a", newline="\n") as fh:
            fh.write("place pad-1 = pad plot 300,0 6x6\n")
        with open(self.surface_path, encoding="utf-8") as fh:
            was = fh.read()
        code, report = self.migrate()
        self.assertEqual(code, 2, report)
        self.assertIn("nothing was changed", report)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "nauvis.fk")))
        with open(self.surface_path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), was)

    def test_the_gap_rides_on_the_plot_line(self):
        code, _out = quiet(cli.main, ["migrate-surface", self.dir])
        self.assertEqual(code, 0)
        path = os.path.join(self.dir, "nauvis.fk")
        with open(path, encoding="utf-8") as fh:
            was = fh.read()
        with open(path, "w", newline="\n") as fh:
            fh.write(was.replace("boot = Boot @(-40, -10) size 20x26",
                                 "boot = Boot @(-40, -10) size 20x26 gap 7"))
        plots = surface.floorplan(self.design()).plots
        self.assertEqual(plots["boot"].params.get("gap"), "7")
        self.assertNotIn("gap", plots["main"].params)
        # a place line's gap reads the same way (an old surface file may carry one)
        old = surface.loads("surface s\nmode lab\nplace a = a plot 0,0 4x4 gap 3\n")
        self.assertEqual(old.places["a"].gap, 3)
        self.assertEqual(surface.floorplan(old).plots["a"].params["gap"], "3")


if __name__ == "__main__":
    unittest.main()
