"""2.0.63 (Rory, 2026-10-29): DNP, do not populate. "You can DNP any part of the design in order
to destruct it and nullify any production, power coverage etc that it provides in the model, but it
is still visible to placement and routing ... It is also a great way to implement a scaling row."
And on taking up what stands: "--confirm makes sense, as long as it's just a flag".

A DNP piece is laid out and routed as ever, makes and takes nothing in the model, and is never
pasted. A ghost of it is cancelled; what stands built on it stays until ``fk build --confirm``."""
import copy
import os
import shutil
import tempfile
import unittest
from unittest import mock

from fkcore import apply as applymod
from fkcore import flow, fkp, link, own, rates, sense, size
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate_file

CAT = Catalog.load()
CELLS = os.path.join(os.path.dirname(__file__), "..", "kickoff", "template", "game", "cells.fk")

SRC = """import FurnaceCell from "cells.fk"
module Gears size 12x8 {
  port fe : in iron-plate @w2
  g1 = Assembler<recipe=iron-gear-wheel> @(2, 1)
  box = Chest<provider, limit=10> @(8, 2)
  net fe: fe -> g1
  net g: g1 -> box
}
ore = Chest<requester, item=iron-ore, rate=5/s> @(0, 2)
fur = Stack<cell=FurnaceCell, n=4, built=2> @(3, 0)
gears = Gears @(30, 0)
net o: ore -> fur.ore_in
net p: fur.pl_out -> gears.fe
dnp gears
"""


class DnpBuildTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="fkdnp-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        shutil.copy(CELLS, self.dir)
        self.write("t.fk", SRC)
        self.write("nauvis.surface", "surface nauvis\nmode play\nterrain none\n"
                                     "place t = t plot 0,0 60x60\n")
        self.write("nauvis.build.fkb", "read_surface nauvis\nread_terrain none\nelaborate\n"
                                       "report_rates\nplace --keep pinned\nroute --only stale\n"
                                       "floorplan\nreport_checks\nreport_bom\nwrite_layout\n")

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return path

    def read(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8") as fh:
            return fh.read()

    def build(self):
        code, ctx = flow.run(os.path.join(self.dir, "nauvis.build.fkb"), cat=CAT,
                             echo=lambda _l: None)
        self.assertEqual(code, 0, ctx.log)
        lay = fkp.load(os.path.join(self.dir, "t.fkp"))
        return ctx, lay

    def test_the_model_has_nothing_of_it(self):
        flat = elaborate_file(os.path.join(self.dir, "t.fk"), CAT)
        self.assertEqual(sorted(p for p in flat.dnp if p.count("/") <= 1),
                         ["fur/2", "fur/3", "gears", "gears/box", "gears/g1"])
        model = rates.solve(flat)
        self.assertEqual(model.util["fur/2/f/m0"], 0.0)
        self.assertEqual(model.util["gears/g1/m0"], 0.0)
        self.assertRegex(rates.report(model, "t"), r"gears/g1 .* dnp: not built")
        # no check about a piece that isn't built (gears/box's no-limit is its own)
        self.assertFalse([c for c in flat.checks if "gears" in c.where])

    def test_laid_out_and_routed_but_not_built(self):
        ctx, lay = self.build()
        dnp = {e.key for e in lay.entities.values() if e.attrs.get("dnp")}
        # the DNP cells and module, and the plate belt that leads only to them
        self.assertIn("fur/2/f/m0", dnp)
        self.assertIn("gears/g1/m0", dnp)
        self.assertTrue(any(k.startswith("~p/") for k in dnp))
        self.assertTrue(any(k.startswith("~fur/3/o/") for k in dnp))
        # the built cells and their ore are live
        self.assertFalse(any(k.startswith(("fur/0/", "fur/1/", "~fur/0/", "~o/")) for k in dnp))
        route_txt = self.read("out/route.txt")
        self.assertIn("entities laid but not built (DNP: fur/2, fur/3, gears)", route_txt)
        self.assertIn("dnp t: fur/2, fur/3, gears: laid out and routed, not built (3 machines; "
                      "at full speed they'd make", self.read("out/report_rates.txt"))
        bom = self.read("out/report_bom.txt")
        self.assertNotIn("assembling-machine", bom)              # the gear module isn't built
        self.assertIn("electric-furnace                 2", bom)  # two of the four cells
        # never pasted
        rows = applymod.scope_rows(ctx.composed)
        self.assertFalse([r for r in rows if r["attrs"].get("dnp")])
        self.assertEqual(len(rows) + len(dnp), len(ctx.composed.entities))

    def test_a_scaling_row_grows_where_it_stands(self):
        _ctx, lay = self.build()
        before = {(e.name, e.x, e.y, e.dir) for e in lay.entities.values()}
        self.write("t.fk", SRC.replace("built=2", "built=3").replace("dnp gears\n", ""))
        _ctx, lay = self.build()
        self.assertEqual({(e.name, e.x, e.y, e.dir) for e in lay.entities.values()}, before)
        self.assertIn("kept (", self.read("out/route.txt"))
        dnp = {e.key for e in lay.entities.values() if e.attrs.get("dnp")}
        self.assertTrue(dnp and all(k.startswith(("fur/3/", "~fur/3/")) for k in dnp))
        self.write("t.fk", SRC.replace("built=2", "built=4").replace("dnp gears\n", ""))
        _ctx, lay = self.build()
        self.assertFalse([e for e in lay.entities.values() if e.attrs.get("dnp")])

    def test_the_refusals(self):
        for bad, said in (("built=5", "built= a whole number of cells from 0 to n=4"),
                          ("built=-1", "built="),):
            self.write("t.fk", SRC.replace("built=2", bad))
            with self.assertRaises(ElabError) as e:
                elaborate_file(os.path.join(self.dir, "t.fk"), CAT)
            self.assertIn(said, str(e.exception))
        self.write("t.fk", SRC.replace("dnp gears", "dnp gears.nope"))
        with self.assertRaises(ElabError) as e:
            elaborate_file(os.path.join(self.dir, "t.fk"), CAT)
        self.assertIn("dnp gears.nope: no such instance", str(e.exception))

    def test_a_flag_on_any_instance_and_a_dotted_line(self):
        self.write("t.fk", SRC.replace("dnp gears", "dnp gears.g1")
                   .replace("box = Chest<provider, limit=10>", "box = Chest<provider, limit=10, dnp>"))
        flat = elaborate_file(os.path.join(self.dir, "t.fk"), CAT)
        self.assertIn("gears/g1", flat.dnp)
        self.assertIn("gears/box", flat.dnp)
        self.assertNotIn("gears", flat.dnp)


class DnpEditTest(unittest.TestCase):
    def test_fk_dnp_writes_the_line(self):
        from fkcore.__main__ import dnp_edit
        text = "a = X @(0, 0)\nb = Y @(5, 0)\n"
        got, changed = dnp_edit(text, ["a", "b.c"])
        self.assertEqual(changed, ["a", "b.c"])
        self.assertIn("\ndnp a, b.c   # do not populate", got)
        got2, changed = dnp_edit(got, ["a", "d"])
        self.assertEqual(changed, ["d"])
        self.assertIn("dnp a, b.c, d   # do not populate", got2)
        got3, changed = dnp_edit(got2, ["a", "b.c", "d"], off=True)
        self.assertEqual(changed, ["a", "b.c", "d"])
        self.assertNotIn("dnp", got3)
        self.assertEqual(got3.rstrip("\n"), text.rstrip("\n"))

    def test_the_command_refuses_a_name_that_matches_nothing(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from fkcore.__main__ import main
        d = tempfile.mkdtemp(prefix="fkdnp-")
        self.addCleanup(shutil.rmtree, d, True)
        shutil.copy(CELLS, d)
        path = os.path.join(d, "t.fk")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(SRC.replace("dnp gears\n", ""))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(["dnp", path, "gears.g1"]), 0)
            self.assertEqual(main(["dnp", path, "nope"]), 2)
        self.assertIn("gears.g1 DNP", out.getvalue())
        self.assertIn("dnp nope: no such instance (the file is as it was)", err.getvalue())
        with open(path, encoding="utf-8") as fh:
            self.assertIn("dnp gears.g1", fh.read())


class DnpCoverTest(unittest.TestCase):
    def test_a_dnp_pole_powers_nothing(self):
        from fkcore.cover import cover_power
        lay = fkp.Layout("factory", "t", size=(12, 8))
        lay.add(fkp.Entity("a/m0", "assembling-machine-1", 2.5, 2.5, 0, {}))
        lay.add(fkp.Entity("p/m0", "medium-electric-pole", 4.5, 2.5, 0, {}))
        poles, _rep = cover_power(lay, CAT)
        self.assertEqual(poles, [])                      # its own pole powers it
        lay.entities["p/m0"].attrs["dnp"] = 1
        poles, _rep = cover_power(lay, CAT)
        self.assertEqual(len(poles), 1)                  # never built: a pole of the cover's


class BuiltAutoTest(unittest.TestCase):
    def test_built_auto_sizes_the_built_cells_inside_a_fixed_n(self):
        d = tempfile.mkdtemp(prefix="fkdnp-")
        self.addCleanup(shutil.rmtree, d, True)
        shutil.copy(CELLS, d)
        path = os.path.join(d, "t.fk")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('import FurnaceCell from "cells.fk"\n'
                     "ore = Chest<requester, item=iron-ore, rate=5/s> @(10, 2)\n"
                     "col = Stack<cell=FurnaceCell, n=12, built=auto> @(10, 8)\n"
                     "gears = Assembler<recipe=iron-gear-wheel, machine=assembling-machine-2> "
                     "@(30, 70)\nbox = Chest<provider> @(40, 80)\n"
                     "net o: ore -> col.ore_in\nnet p: col.pl_out -> gears\nnet g: gears -> box\n")
        sz = size.size({"t": size.maker(path, CAT)})
        row = next(r for r in sz.rows if r.path == "col")
        self.assertEqual(row.n, 5)               # what the gears take, as n=auto would
        flat = elaborate_file(path, CAT, sizes={"col": row.n})
        cells = sorted(int(p.split("/")[1]) for p in flat.insts if p.count("/") == 1
                       and p.startswith("col/"))
        self.assertEqual(cells, list(range(12)))  # all twelve laid out
        self.assertEqual(sorted(int(p.split("/")[1]) for p in flat.dnp if p.count("/") == 1),
                         list(range(5, 12)))      # seven not built


class DnpGameTest(unittest.TestCase):
    """The game side, on test_sense's mini factory: one assembler made DNP."""

    def setUp(self):
        from tests.test_sense import surface, live_as_designed
        self.s = surface()
        self.key = next(k for k, e in sorted(self.s.entities.items())
                        if CAT.kind(e.name) == "assembling-machine")
        self.rec = own.rows_of(self.s)
        self.live = copy.deepcopy(live_as_designed(self.s))
        self.s.entities[self.key].attrs["dnp"] = 1
        self.e = self.s.entities[self.key]

    def thing(self):
        return next(t for t in self.live["things"]
                    if (t["name"], t["x"], t["y"]) == (self.e.name, self.e.x, self.e.y))

    def sense(self, confirm=False):
        from tests.test_sense import AREA, WATCH
        return sense.sense(self.s, self.live, CAT, AREA, WATCH, own=self.rec, confirm=confirm)

    def verdict(self, rep):
        return next(v for v in rep.verdicts if v.key == self.key)

    def test_standing_it_stays_until_confirm(self):
        v = self.verdict(self.sense())
        self.assertEqual(v.verdict, "dnp-standing")
        self.assertIn("fk build --confirm takes it up", str(v))
        v = self.verdict(self.sense(confirm=True))
        self.assertEqual((v.verdict, v.action), ("unowned", "own"))

    def test_a_ghost_of_it_is_cancelled(self):
        self.thing()["ghost"] = True
        v = self.verdict(self.sense())
        self.assertEqual((v.verdict, v.ghost), ("unowned", True))

    def test_not_built_is_as_designed(self):
        self.live["things"].remove(self.thing())
        rep = self.sense()
        self.assertEqual(self.verdict(rep).verdict, "dnp")
        self.assertFalse([line for line in rep.lines()[1:] if self.key in line])

    def test_the_apply_takes_it_up_only_with_confirm(self):
        from tests.test_own import FakeRcon, snapshot_of
        from tests.test_sense import NETS, WATCH
        for confirm in (False, True):
            r = FakeRcon()
            pasted = []
            with mock.patch.object(link, "snapshot", snapshot_of(self.live)), \
                    mock.patch.object(link, "paste", lambda *a, **k: "0"), \
                    mock.patch.object(applymod, "paste_blueprint",
                                      lambda rows, *a, **k: pasted.extend(rows) or "bp"):
                rep = applymod.apply(r, self.s, CAT, None, mode="play", policy=WATCH,
                                     net_items=NETS, own=self.rec, confirm=confirm)
            self.assertNotIn(self.key, [row["src"] for row in pasted])
            took = (self.e.name, float(self.e.x), float(self.e.y)) in \
                {(n, float(x), float(y)) for n, x, y in r.ordered}
            self.assertEqual(took, confirm)
            self.assertEqual((rep.dnp_kept, rep.dnp_taken), (0, 1) if confirm else (1, 0))


if __name__ == "__main__":
    unittest.main()
