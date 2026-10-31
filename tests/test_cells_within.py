"""2.1, cells within cells (PLAN-2.1 "E. Cells within cells"): ``S[k].P``, ``S[-1].P``,
``S[*].P`` in a net, ``net each``, an each net into a list of ports, nesting (a module that holds
a Stack, stacked), the outer ``n=auto``, every refusal, and the rate model serving a short line's
cells in order (the last cell runs short, as on the 20261030 run's lab lines)."""
import os
import unittest

from fkcore import lang, rates
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate, elaborate_file
from fkcore.lang import FkSyntaxError

CAT = Catalog.load()
HERE = os.path.dirname(os.path.abspath(__file__))
NEST = os.path.join(HERE, "nest")
with open(os.path.join(NEST, "cells.fk"), encoding="utf-8") as _fh:
    CELLS = _fh.read()

#: a column of three furnaces with the ore along its foot, and a row of four chests to take what
#: four columns make, a port each
HEAD = CELLS + """
module Boxes size 36x4 {
  port i0 : in iron-plate @n7
  port i1 : in iron-plate @n16
  port i2 : in iron-plate @n25
  port i3 : in iron-plate @n34
  c0 = Chest<provider> @(7, 3)
  c1 = Chest<provider> @(16, 3)
  c2 = Chest<provider> @(25, 3)
  c3 = Chest<provider> @(34, 3)
  net n0: i0 -> c0
  net n1: i1 -> c1
  net n2: i2 -> c2
  net n3: i3 -> c3
}
ore  = Chest<requester, item=iron-ore, rate=15/s> @(0, 4)
cols = Stack<cell=SmeltColumn, n=4, plate=iron-plate, ore=iron-ore> @(4, 0)
net feed: ore -> cols.ore_in
"""


def flat_of(text, path="t.fk"):
    f = lang.parse(text, path)
    return elaborate(f, dict(f.modules), CAT, "t")


def refused(test, text, *msgs, syntax=False):
    with test.assertRaises(FkSyntaxError if syntax else ElabError) as cm:
        flat_of(text)
    for msg in msgs:
        test.assertIn(msg, str(cm.exception))
    return str(cm.exception)


class ParseTest(unittest.TestCase):
    def test_the_ref_forms(self):
        f = lang.parse("net a: cols[2].pl -> x\nnet b: cols[-1].pl, s[*].i[0].p -> y\n"
                       "net each c: cols[*].pl -> box")
        a, b, c = f.body.nets
        self.assertEqual(a.drivers[0].parts, ["cols", "[2]", "pl"])
        self.assertEqual(str(a.drivers[0]), "cols[2].pl")
        self.assertEqual(b.drivers[0].parts, ["cols", "[-1]", "pl"])
        self.assertEqual(str(b.drivers[1]), "s[*].i[0].p")
        self.assertEqual((a.each, c.each, c.name), (False, True, "c"))

    def test_a_net_named_each_is_one_net(self):
        f = lang.parse("net each: a -> b")
        self.assertEqual((f.body.nets[0].name, f.body.nets[0].each), ("each", False))

    def test_a_bad_index_is_refused(self):
        for text in ("net a: cols[x].pl -> b", "net a: cols[1.5].pl -> b", "net a: cols[].pl -> b"):
            with self.subTest(text=text), self.assertRaises(FkSyntaxError) as cm:
                lang.parse(text)
            self.assertIn("a Stack's cell is [k]", str(cm.exception))


class RefTest(unittest.TestCase):
    def test_one_cell_and_the_last(self):
        flat = flat_of(HEAD + "net a: cols[2].pl -> box.i2\nnet b: cols[-1].pl -> box.i3\n"
                       "box = Boxes @(4, 20)")
        self.assertEqual(flat.nets["a"].drivers, [("cols/2/pl", "iron-plate")])
        self.assertEqual(flat.nets["b"].drivers, [("cols/3/pl", "iron-plate")])

    def test_star_in_an_ordinary_net_is_every_cell(self):
        flat = flat_of(HEAD + "box = Chest<provider> @(4, 20)\nnet p: cols[*].pl -> box")
        self.assertEqual(sorted(k for k, _i in flat.nets["p"].drivers),
                         [f"cols/{k}/pl" for k in range(4)])
        self.assertEqual(flat.each, {})

    def test_a_cell_inside_a_cell(self):
        # the inner Stack's cell, through a module that isn't sealed
        text = CELLS + """
        module Open<plate, ore> {
          s = Stack<cell=FurnaceCell, n=3, plate=$plate, ore=$ore>
        }
        o = Open<plate=iron-plate, ore=iron-ore>
        src = Chest<requester, item=iron-ore, rate=1/s>
        net a: src -> o.s[1].ore_in
        """
        flat = flat_of(text)
        self.assertEqual(flat.nets["a"].consumers, [("o/s/1/ore_in", "iron-ore")])

    def test_index_out_of_range(self):
        refused(self, HEAD + "box = Chest<provider>\nnet a: cols[4].pl -> box",
                "cols[4].pl: cols has 4 cells, [0] to [3]")
        refused(self, HEAD + "box = Chest<provider>\nnet a: cols[-5].pl -> box", "has 4 cells")

    def test_index_on_a_non_stack(self):
        refused(self, HEAD + "box = Chest<provider>\nnet a: box[0] -> ore",
                "box[0]: box is a Chest, not a Stack")
        refused(self, HEAD + "box = Boxes\nnet a: cols[0].pl -> box[1].i1",
                "box[1].i1: box is a module Boxes, not a Stack")
        refused(self, HEAD + "box = Chest<provider>\nnet a: cols[0].s[1].pl_out -> box",
                "cols/0 is a sealed module")

    def test_star_on_a_non_stack(self):
        refused(self, HEAD + "box = Boxes\nnet a: cols[0].pl -> box[*]", "not a Stack")

    def test_star_outside_a_net(self):
        flat = flat_of(HEAD + "box = Chest<provider>\nnet a: cols[0].pl -> box\n"
                       "assert cols[*].rate >= 1/s")
        with self.assertRaises(ElabError) as cm:
            rates.solve(flat)
        self.assertIn("[*] is every cell, which a net names", str(cm.exception))


class EachTest(unittest.TestCase):
    def test_one_net_per_cell_into_a_list_of_ports(self):
        flat = flat_of(HEAD + "box = Boxes @(4, 20)\nnet each plates: cols[*].pl -> box")
        self.assertEqual(flat.each, {"plates": [f"plates_{k}" for k in range(4)]})
        for k in range(4):
            net = flat.nets[f"plates_{k}"]
            self.assertEqual((net.drivers, net.consumers, net.group),
                             ([(f"cols/{k}/pl", "iron-plate")], [(f"box/i{k}", "iron-plate")],
                              "plates"))
        self.assertFalse([c for c in flat.checks if c.code in ("port", "cannot-carry")])

    def test_cell_k_with_cell_k(self):
        text = HEAD + """
        module Sink size 9x3 {
          port i : in iron-plate @n7
          port w : in iron-plate @w1
          port e : out iron-plate @e1
          stack w -> e
          c = Chest<provider> @(7, 2)
          net i: i -> c
        }
        sinks = Stack<cell=Sink, n=4> @(4, 20)
        net each plates: cols[*].pl -> sinks[*].i
        """
        flat = flat_of(text)
        self.assertEqual([flat.nets[n].consumers for n in flat.each["plates"]],
                         [[(f"sinks/{k}/i", "iron-plate")] for k in range(4)])

    def test_count_mismatch(self):
        text = HEAD.replace("i3 : in iron-plate @n34", "i3 : in iron-plate @n34\n"
                            "  port i4 : in iron-plate @n35") + \
            "box = Boxes @(4, 20)\nnet each plates: cols[*].pl -> box"
        refused(self, text, "net each plates: both sides need the same count",
                "cols[*].pl 4 cells", "box 5 ports")

    def test_n_auto_is_refused(self):
        text = HEAD.replace("cols = Stack<cell=SmeltColumn, n=4,",
                            "cols = Stack<cell=SmeltColumn, n=auto 1..4,")
        refused(self, text + "box = Boxes @(4, 20)\nnet each plates: cols[*].pl -> box",
                "cols is n=auto, and an each net needs a fixed count")

    def test_n_auto_is_fine_in_an_ordinary_net(self):
        text = HEAD.replace("cols = Stack<cell=SmeltColumn, n=4,",
                            "cols = Stack<cell=SmeltColumn, n=auto 2..4,")
        flat = flat_of(text + "box = Chest<provider>\nnet p: cols[*].pl -> box")
        self.assertEqual(len(flat.nets["p"].drivers), 2)     # the low bound, unsized

    def test_no_star_is_refused(self):
        refused(self, HEAD + "box = Boxes\nnet each p: cols[*].pl -> box.i0",
                "box.i0 is one endpoint")
        refused(self, HEAD + "box = Boxes\nnet each p: cols.pl -> box",
                "an each net names a Stack's cells with [*]")

    def test_inside_a_sealed_cell_is_refused(self):
        # a Stack's cells are sealed, so a second [*] past one is never reached
        refused(self, HEAD + "box = Boxes\nnet each p: cols[*].s[*].pl_out -> box",
                "cols/0 is a sealed module (SmeltColumn)")

    def test_a_name_taken(self):
        refused(self, HEAD + "box = Boxes\nnet plates_1: ore -> box.i1\n"
                "net each plates: cols[*].pl -> box", "a net plates_1 exists")

    def test_split_and_each(self):
        refused(self, HEAD + "box = Boxes\nnet each p split: cols[*].pl -> box",
                "split and each don't go together")


class NestTest(unittest.TestCase):
    def test_the_bus_and_the_field(self):
        bus = elaborate_file(os.path.join(NEST, "bus.fk"), CAT)
        self.assertEqual(len(bus.each["plates"]), 8)
        self.assertEqual(bus.stacks["cols"], ("SmeltColumn", 8, None))
        self.assertEqual(bus.stacks["cols/7/s"], ("FurnaceCell", 3, None))
        model = rates.solve(bus)
        self.assertTrue(all(model.util[k] == 1.0 for k, m in bus.machines.items()
                            if m.kind == "Furnace"))
        labs = elaborate_file(os.path.join(NEST, "labs.fk"), CAT)
        self.assertEqual(sum(1 for m in labs.machines.values() if m.prototype == "lab"), 24)
        self.assertEqual([c.code for c in labs.checks], [])

    def test_an_import_brings_what_the_module_is_built_of(self):
        f, path = os.path.join(NEST, "bus.fk"), None
        flat = elaborate_file(f, CAT)
        self.assertIn("cols/0/s/0/f/m0", flat.machines)

    def test_an_inner_n_auto_is_refused(self):
        text = CELLS + """
        module Col<plate, ore> size 9x14 {
          port ore_in  : in  $ore | $ore @w11
          port ore_out : out $ore | $ore @e11
          port pl      : out $plate      @s7
          stack ore_in -> ore_out
          s = Stack<cell=FurnaceCell, n=auto, plate=$plate, ore=$ore> @(1, 0)
          net o: ore_in -> s.ore_in, ore_out
          net p: s.pl_out -> pl
        }
        cols = Stack<cell=Col, n=2, plate=iron-plate, ore=iron-ore>
        """
        refused(self, text, "cols.0.s: n=auto inside a cell of Stack cols")


#: a line of four furnace cells fed at 1.5 ore/s: three cells' worth and a little more
LINE = CELLS + """
ore = Chest<requester, item=iron-ore, rate=%s/s>
col = Stack<cell=FurnaceCell, n=4, plate=iron-plate, ore=iron-ore>
box = Chest<provider>
net o: ore -> col.ore_in
net p: col.pl_out -> box
"""


class LastCellTest(unittest.TestCase):
    def utils(self, text, keys):
        model = rates.solve(flat_of(text))
        return [round(model.util[k + "/m0"], 3) for k in keys]

    def test_a_short_line_starves_its_last_cells(self):
        keys = [f"col/{k}/f" for k in range(4)]
        self.assertEqual(self.utils(LINE % "2.2", keys), [1.0, 1.0, 1.0, 0.52])
        self.assertEqual(self.utils(LINE % "1.5", keys), [1.0, 1.0, 0.4, 0.0])
        self.assertEqual(self.utils(LINE % "3", keys), [1.0] * 4)

    def test_a_short_bus_serves_its_columns_in_order(self):
        text = HEAD.replace("rate=15/s", "rate=4.5/s") + "box = Boxes\n" \
            "net each plates: cols[*].pl -> box"
        model = rates.solve(flat_of(text))
        got = [[round(model.util[f"cols/{c}/s/{k}/f/m0"], 3) for k in range(3)] for c in range(4)]
        self.assertEqual(got, [[1.0] * 3, [1.0] * 3, [1.0, 0.2, 0.0], [0.0] * 3])

    def test_a_plain_net_is_shared_as_before(self):
        text = """
        ore = Chest<requester, item=iron-ore, rate=1/s>
        a = Furnace<recipe=iron-plate, machine=electric-furnace>
        b = Furnace<recipe=iron-plate, machine=electric-furnace>
        box = Chest<provider>
        net o: ore -> a, b
        net p: a, b -> box
        """
        self.assertEqual(self.utils(text, ["a", "b"]), [0.8, 0.8])


if __name__ == "__main__":
    unittest.main()
