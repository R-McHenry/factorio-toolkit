"""2.1, the library: the kickoff template's cells take parameters (plate, ore, recipe, ins, packs),
and each line in tests/library elaborates, rates and routes like the row it replaces. The sushi
gate's `auto` amount comes from the loop's recipes; `fk check` names the cell a new row could be."""
import os
import shutil
import tempfile
import unittest

from fkcore import connect, expand, lang, rates, route
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, advice, elaborate_file
from tests.test_power_domains import Build

CAT = Catalog.load()
ROOT = os.path.join(os.path.dirname(__file__), "..")
CELLS = os.path.join(ROOT, "kickoff", "template", "game", "cells.fk")
LIB = os.path.join(ROOT, "tests", "library")

#: (cell line, row line, its row kind, items a minute both make on paper)
PAIRS = [
    ("cu_pair", "cu_array", "SmelterArray", 150), ("steel_pair", "steel_array", "SmelterArray", 30),
    ("brick_cell", "brick_row", "SmelterRow", 75), ("cu_fcell", "cu_frow", "SmelterRow", 150),
    ("steel_fpair", "steel_frow", "SmelterRow", 30), ("col_bus", "col_row", "SmelterRow", 225),
    ("belt_cell", "belt_row", "AsmRow", 480), ("gear_cell", "gear_row", "AsmRow", 240),
    ("acid_cells", "acid_row", "MinerRow", 45),
    ("lab_cell", "lab_row", "LabRow", None), ("lab_field", "lab_field_row", "LabRow", None),
]
#: the cell `fk check` names for each row line
ROW_CELL = {"cu_array": "SmelterPair", "steel_array": "SmelterPair",
            "brick_row": "StoneFurnaceCell", "cu_frow": "FurnaceCell", "steel_frow": "FurnaceCell",
            "col_row": "FurnaceCell", "belt_row": "AsmCell", "gear_row": "AsmCell1",
            "lab_row": "LabCell", "lab_field_row": "LabCell"}


class _Dir(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="fklib-")
        shutil.copy(CELLS, cls.dir)
        for name in os.listdir(LIB):
            shutil.copy(os.path.join(LIB, name), cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def flat(self, name, src=None):
        path = os.path.join(self.dir, f"{name}.fk")
        if src is not None:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(src)
        return elaborate_file(path, CAT)


def made(flat):
    """Items a minute the line's top-level makers make (chests and pipes left out)."""
    m = rates.solve(flat)
    return sum(m.inst_rate(k) * 60 for k, i in flat.insts.items()
               if "/" not in k and i.kind not in ("Chest", "InfinityPipe"))


class LinesTest(_Dir):
    def test_each_cell_rates_as_its_row(self):
        for cell, row, _kind, rate in PAIRS:
            with self.subTest(cell=cell):
                a, b = self.flat(cell), self.flat(row)
                if rate is None:
                    labs = [sum(1 for m in f.machines.values() if m.prototype == "lab")
                            for f in (a, b)]
                    self.assertEqual(labs[0], labs[1])
                    self.assertGreater(labs[0], 0)
                    continue
                self.assertAlmostEqual(made(a), rate, places=3)
                self.assertAlmostEqual(made(b), rate, places=3)

    def test_each_line_routes_and_connects(self):
        for name in sorted(f[:-3] for f in os.listdir(LIB) if f.endswith(".fk")):
            with self.subTest(line=name):
                flat = self.flat(name)
                lay, _notes = expand.expand_factory(flat, CAT)
                r = route.route_layout(flat, lay, CAT)
                self.assertEqual(r.failed, {})
                rep = connect.connect(r.layout, CAT, connect.endpoints(flat), flat._port_edges)
                self.assertEqual({n for n, x in rep.nets.items() if x.status != "connected"},
                                 set())
                self.assertEqual(rep.leaks, [])

    def test_a_new_row_names_its_cell(self):
        for row, cell in ROW_CELL.items():
            with self.subTest(row=row):
                lines = [c.msg for c in advice(self.flat(row)) if c.code == "row-cell"]
                self.assertEqual(len(lines), 1)
                self.assertIn(f"a Stack of the library's {cell} (import it from", lines[0])
        msg = [c.msg for c in advice(self.flat("belt_row")) if c.code == "row-cell"][0]
        self.assertIn("ins=iron-plate|iron-gear-wheel", msg)
        msg = [c.msg for c in advice(self.flat("steel_array")) if c.code == "row-cell"][0]
        self.assertIn("Stack<cell=SmelterPair, n=4, plate=steel-plate, ore=iron-plate>", msg)

    def test_a_cell_line_gets_no_row_line(self):
        for cell, _row, _kind, _rate in PAIRS:
            with self.subTest(cell=cell):
                self.assertEqual([c for c in advice(self.flat(cell))
                                  if c.code in ("row-cell", "limited-why")], [])

    def test_the_parameters_reach_the_machines(self):
        flat = self.flat("steel_pair")
        self.assertEqual({m.recipe for m in flat.machines.values() if m.recipe},
                         {"steel-plate"})
        flat = self.flat("belt_cell")
        self.assertEqual({m.recipe for m in flat.machines.values() if m.recipe},
                         {"transport-belt"})


class MallTest(_Dir):
    def test_auto_gates_come_from_the_recipes(self):
        for name in ("mall", "mall_chest"):
            with self.subTest(mall=name):
                flat = self.flat(name)
                self.assertEqual({n: g[:2] for n, g in flat.gates.items()},
                                 {"g1/s": ("iron-plate", 160), "g2/s": ("copper-plate", 40),
                                  "g3/s": ("iron-gear-wheel", 40)})
                self.assertEqual(flat.gates["g1/s"][3], ["m1/a", "m3/a", "m4/a"])
                self.assertEqual(flat.nets["g1/s"].when[0].right, 160)
                adv = [c.msg for c in advice(flat) if c.code == "gate-auto"]
                self.assertIn("auto holds iron-plate below 160: 40 s of the 4/s its loop's "
                              "machines take (m1/a, m3/a, m4/a), and at least 2 crafts each", adv)

    def test_the_mall_has_no_sink_and_a_steady_buffer(self):
        flat = self.flat("mall")
        self.assertEqual([c for c in flat.checks if c.code in ("SUSHI_SINK", "gate-auto")], [])
        lines = rates.buffer_lines(rates.solve(flat))
        self.assertTrue(lines)
        for ln in lines:
            self.assertIn("steady, its gated sources top up what goes out", ln)

    def test_no_machine_on_the_loop_is_a_gate_auto_line(self):
        src = ('import GateCell, BeltEndBuffer from "cells.fk"\n'
               'g = GateCell<item=iron-plate, items=iron-plate> @(6, 8)\n'
               'e = BeltEndBuffer<items=iron-plate> @(6, 2)\n'
               'net a limited "x": g.s_out -> e.i\n'
               'net b limited "x": e.o -> g.s_in\n')
        flat = self.flat("nomaker", src)
        self.assertEqual([c.where for c in flat.checks if c.code == "gate-auto"], ["net g/s"])
        self.assertEqual(flat.nets["g/s"].when[0].right, 0)

    def test_auto_on_a_machine_is_refused(self):
        src = ('w = Chest<provider> @(0, 0)\n'
               'a = Assembler<recipe=pipe> @(4, 0) when w.iron-plate < auto\n')
        with self.assertRaisesRegex(ElabError, "auto is the amount a loop's recipes need"):
            self.flat("automachine", src)

    def test_an_amount_that_is_no_number_is_refused(self):
        src = ('import GateCell from "cells.fk"\n'
               'g = GateCell<item=iron-plate, items=iron-plate, amount=lots> @(6, 8)\n')
        with self.assertRaisesRegex(ElabError, "a condition compares with a number or auto"):
            self.flat("lots", src)

    def test_a_written_amount_stays(self):
        src = ('import GateCell, MallCell, BeltEndBuffer from "cells.fk"\n'
               'g = GateCell<item=iron-plate, items=iron-plate, amount=75> @(6, 11)\n'
               'm = MallCell<recipe=pipe, items=iron-plate> @(6, 5)\n'
               'e = BeltEndBuffer<items=iron-plate> @(6, 2)\n'
               'net a limited "x": g.s_out -> m.s_in\n'
               'net c limited "x": m.s_out -> e.i\n'
               'net b limited "x": e.o -> g.s_in\n')
        flat = self.flat("written", src)
        self.assertEqual(flat.nets["g/s"].when[0].right, 75)
        self.assertEqual(flat.gates, {})


class TemplateTest(_Dir):
    def test_the_old_names_still_work(self):
        with open(CELLS, encoding="utf-8") as fh:
            mod = lang.parse(fh.read(), "cells.fk")
        names = set(mod.modules) | set(mod.kinds)
        for old in ("FurnaceCell", "FurnacePair", "StoneFurnaceCell", "SmelterPair", "GearCell",
                    "CircuitCell", "LabCell"):
            self.assertIn(old, names)

    def test_a_kind_brings_its_module(self):
        src = ('import GearCell from "cells.fk"\n'
               'pl = Chest<requester, item=iron-plate> @(10, 2)\n'
               'col = Stack<cell=GearCell, n=2> @(10, 8)\n'
               'net p: pl -> col.in_in\n')
        flat = self.flat("gearkind", src)
        self.assertEqual({m.recipe for m in flat.machines.values() if m.recipe},
                         {"iron-gear-wheel"})

    def test_hysteresis_is_named_from_outside(self):
        src = """import Hysteresis from "cells.fk"
signal A = signal-A
signal S = signal-S
power main: cover all
power labs: cover l1
acc = Accumulator<read=A> @(2, 2)
shedder = Hysteresis<in=A, out=S, lo=20, hi=80> @(6, 2)
wire level green: acc -> shedder.latch.in
sw = PowerSwitch @(10, 2) when shedder.hold.S = 0
copper feed: main -> sw.left
copper load: sw.right -> labs
l1 = Lab @(20, 2)
"""
        with open(CELLS, encoding="utf-8") as fh:
            b = Build(src, files={"cells.fk": fh.read()})
        self.addCleanup(b.close)
        self.assertEqual(b.code, 0)
        ws = {(w.net, w.a, w.b) for w in b.lay.wires}
        self.assertIn(("level", "acc/m0", "shedder/latch/m0.in"), ws)
        self.assertIn(("shedder/hold", "shedder/latch/m0.out", "sw/m0"), ws)
        self.assertFalse(b.codes("no-wire") + b.codes("no-signal") + b.codes("switch-never"))


if __name__ == "__main__":
    unittest.main()
