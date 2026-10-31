"""2.1 (PLAN-2.1 "D. Module parameters"): ``module NAME<p, q=default>``, ``$p`` and ``$p[k]``,
instance arguments, Stack forwarding, ``kind`` for modules, identity in the .fkp, and every
refusal."""
import os
import unittest

from fkcore import connect, expand, lang, rates, route
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate, elaborate_file
from fkcore.lang import FkSyntaxError

CAT = Catalog.load()
HERE = os.path.dirname(os.path.abspath(__file__))
PARAMS = os.path.join(HERE, "params")
with open(os.path.join(PARAMS, "cells.fk"), encoding="utf-8") as _fh:
    CELLS = _fh.read()


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
    def test_the_header_and_the_words(self):
        f = lang.parse(CELLS, "cells.fk")
        fc = f.modules["FurnaceCell"]
        self.assertEqual([(p.name, p.default) for p in fc.params], [("plate", None), ("ore", None)])
        self.assertEqual(fc.size, (7, 3))
        self.assertEqual(fc.ports[0].items, ["$ore"])
        asm = f.modules["AsmCell"]
        self.assertEqual((asm.ports[0].items, asm.ports[0].right), (["$ins[0]"], ["$ins[1]"]))
        self.assertEqual(asm.nets[0].items, ["$ins"])
        self.assertEqual(asm.insts[0].params, {"recipe": "$recipe"})

    def test_defaults(self):
        f = lang.parse('module M<a, b=iron-plate, c=2, d=x|y, e="s t"> size 1x1 { }')
        self.assertEqual([(p.name, p.default) for p in f.modules["M"].params],
                         [("a", None), ("b", "iron-plate"), ("c", 2), ("d", ["x", "y"]),
                          ("e", "s t")])
        self.assertEqual(lang.parse("module M<> { }").modules["M"].params, [])

    def test_a_reserved_name_is_refused(self):
        for name in lang.RESERVED:
            with self.subTest(name=name), self.assertRaises(FkSyntaxError) as cm:
                lang.parse(f"module M<{name}> size 1x1 {{ }}")
            self.assertIn(f"{name} is a parameter every Stack", str(cm.exception))

    def test_a_dollar_where_a_name_belongs_is_refused(self):
        head = "module M<p> size 7x3 {\n"
        for body, word in (("$p = Assembler<recipe=pipe>", "the parameter $p"),
                           ("a = $p", "the parameter $p"),
                           ("net $p: a -> b", "the parameter $p"),
                           ("port $p : in iron-plate @s0", "the parameter $p"),
                           ("port x : in iron-plate @$p", "the parameter $p"),
                           ("a = Assembler<recipe=pipe> @($p, 0)", "the parameter $p"),
                           ("a = Assembler<recipe=pipe> size $p", "size $p"),
                           ("net n: $p -> b", "the parameter $p"),
                           ("stack $p -> b", "the parameter $p"),
                           ("lanes $p | b", "the parameter $p"),
                           ("set $p: filter=x", "the parameter $p"),
                           ("dnp $p", "the parameter $p"),
                           ("wire $p red: a", "the parameter $p"),
                           ("signal $p = signal-A", "the parameter $p"),
                           ("net n: a -> b when $p.x > 1", "the parameter $p"),
                           ("net n: a -> b when w.$p.x > 1", "the parameter $p")):
            with self.subTest(body=body), self.assertRaises(FkSyntaxError) as cm:
                lang.parse(head + body + "\n}")
            self.assertIn(word, str(cm.exception))
        with self.assertRaises(FkSyntaxError) as cm:
            lang.parse("module M<p> size $p { }")
        self.assertIn("size $p", str(cm.exception))

    def test_an_unknown_parameter_in_the_body(self):
        with self.assertRaises(FkSyntaxError) as cm:
            lang.parse("module M<plate> size 7x3 {\n  port x : in $ore @s0\n}")
        self.assertIn("$ore: module M has no parameter ore (its parameters: plate)",
                      str(cm.exception))

    def test_a_dollar_outside_a_module(self):
        for text in ("a = Assembler<recipe=$r>", "kind K = Assembler<recipe=$r>",
                     "net n items $i: a -> b", "module M<a=$b> { }"):
            with self.subTest(text=text), self.assertRaises(FkSyntaxError) as cm:
                lang.parse(text)
            self.assertIn("inside a module that declares it", str(cm.exception))

    def test_an_index_is_a_whole_number(self):
        with self.assertRaises(FkSyntaxError):
            lang.parse("module M<p> size 1x1 {\n  port x : in $p[a] @s0\n}")


class InstanceTest(unittest.TestCase):
    def test_one_instance(self):
        flat = flat_of(CELLS + "c = FurnaceCell<plate=copper-plate, ore=copper-ore>")
        m = flat.machines["c/f/m0"]
        self.assertEqual((m.prototype, m.recipe), ("electric-furnace", "copper-plate"))
        self.assertEqual(flat.ports["c/ore_in"].items, ["copper-ore"])
        self.assertEqual(flat.nets["c/p"].items, ["copper-plate"])
        self.assertEqual(flat.insts["c"].params, {"plate": "copper-plate", "ore": "copper-ore"})

    def test_two_instances_of_one_module_differ(self):
        flat = flat_of(CELLS + "a = FurnaceCell<plate=copper-plate, ore=copper-ore>\n"
                               "b = FurnaceCell<plate=iron-plate, ore=iron-ore>")
        self.assertEqual(flat.machines["a/f/m0"].recipe, "copper-plate")
        self.assertEqual(flat.machines["b/f/m0"].recipe, "iron-plate")

    def test_defaults_and_their_override(self):
        src = ("module M<recipe=iron-gear-wheel> size 5x5 {\n"
               "  a = Assembler<recipe=$recipe> @(1, 1)\n}\n")
        self.assertEqual(flat_of(src + "x = M").machines["x/a/m0"].recipe, "iron-gear-wheel")
        self.assertEqual(flat_of(src + "x = M<recipe=pipe>").machines["x/a/m0"].recipe, "pipe")
        self.assertEqual(flat_of(src + "x = M").insts["x"].params, {"recipe": "iron-gear-wheel"})

    def test_a_list_spreads_and_indexes(self):
        flat = flat_of(CELLS + "c = AsmCell<recipe=electronic-circuit, "
                               "ins=iron-plate|copper-cable, out=electronic-circuit>")
        p = flat.ports["c/i_in"]
        self.assertEqual((p.items, p.right), (["iron-plate"], ["copper-cable"]))
        # `net i items $ins split`: one net per item
        self.assertEqual(flat.nets["c/i_iron_plate"].items, ["iron-plate"])
        self.assertEqual(flat.nets["c/i_copper_cable"].items, ["copper-cable"])
        self.assertEqual(flat.machines["c/a/m0"].recipe, "electronic-circuit")

    def test_a_list_spreads_into_one_lane(self):
        flat = flat_of("module M<ins> size 3x3 {\n  port m : in $ins @s0\n  c = Chest<provider>"
                       " @(1, 1)\n  net n items $ins: m -> c\n}\nx = M<ins=iron-ore|coal>")
        self.assertEqual(flat.ports["x/m"].items, ["iron-ore", "coal"])
        self.assertEqual(flat.nets["x/n"].items, ["iron-ore", "coal"])

    def test_a_value_a_signal_a_set_and_a_string(self):
        flat = flat_of("""
module M<item, sig, k=2> size 9x9 {
  box = Chest<requester, item=$item, rate=$k> @(1, 1)
  signal s = $sig
  set box: filter=$item
  out = Chest<provider, limit=$k> @(5, 5)
  net k: box -> out
}
x = M<item=iron-plate, sig=signal-A, k=3>""")
        self.assertEqual(flat.insts["x/box"].params["item"], "iron-plate")
        self.assertEqual(flat.insts["x/box"].params["rate"], 3)
        sigs = [s for s, _scope in flat.circuit_src["signals"]]
        self.assertEqual(sigs[0].game, "signal-A")
        sets = [s for s, _scope in flat.circuit_src["sets"]]
        self.assertEqual(sets[0].attrs, {"filter": "iron-plate"})
        f = lang.parse('module M<f> size 9x9 {\n  l = Literal<file="$f.json", box="a$f[0]b">\n}')
        from fkcore.elaborate import _Subst
        sub = _Subst(f.modules["M"], {"f": "mine"}, "t.fk").module()
        self.assertEqual(sub.insts[0].params, {"file": "mine.json", "box": "amineb"})

    def test_a_parameter_passed_on_to_an_inner_module(self):
        flat = flat_of(CELLS + "module Two<plate, ore> size 7x6 {\n"
                               "  a = FurnaceCell<plate=$plate, ore=$ore> @(0, 0)\n"
                               "  s = Stack<cell=FurnaceCell, n=1, plate=$plate, ore=$ore> @(0, 3)\n"
                               "}\nt = Two<plate=copper-plate, ore=copper-ore>")
        self.assertEqual(flat.machines["t/a/f/m0"].recipe, "copper-plate")
        self.assertEqual(flat.machines["t/s/0/f/m0"].recipe, "copper-plate")

    def test_a_kind_of_a_module(self):
        flat = flat_of(CELLS + "kind CopperCell = FurnaceCell<plate=copper-plate, ore=copper-ore>\n"
                               "c = CopperCell\nd = CopperCell<plate=iron-plate, ore=iron-ore>")
        self.assertEqual(flat.machines["c/f/m0"].recipe, "copper-plate")
        self.assertEqual(flat.machines["d/f/m0"].recipe, "iron-plate")

    def test_a_module_without_parameters_is_unchanged(self):
        src = "module M size 5x5 {\n  a = Assembler<recipe=pipe> @(1, 1)\n}\nx = M<duty=0.5>"
        flat = flat_of(src)
        self.assertEqual(flat.insts["x"].params, {"duty": 0.5})
        self.assertEqual(flat.machines["x/a/m0"].duty, 0.5)


class RefusalTest(unittest.TestCase):
    def test_a_missing_parameter(self):
        refused(self, CELLS + "c = FurnaceCell<plate=iron-plate>",
                "c: module FurnaceCell needs ore= (a parameter with no default)")
        refused(self, CELLS + "c = FurnaceCell", "needs plate=, ore= (parameters with no default)")
        refused(self, CELLS + "c = Stack<cell=FurnaceCell, n=2, plate=iron-plate>",
                "c/0: module FurnaceCell needs ore=")

    def test_an_unknown_parameter(self):
        refused(self, CELLS + "c = FurnaceCell<plate=iron-plate, ore=iron-ore, fuel=coal>",
                "module FurnaceCell has no parameter fuel (its parameters: plate, ore;")
        refused(self, "module M size 1x1 { }\nkind N = M<recipe=pipe>\nx = N",
                "module M has no parameter recipe (it takes none;")
        refused(self, CELLS + "c = Stack<cell=FurnaceCell, n=2, plate=iron-plate, ore=iron-ore, "
                              "fuel=coal>", "Stack: takes cell=", "(FurnaceCell: plate, ore), "
                              "not fuel")

    def test_an_index_past_the_end(self):
        refused(self, CELLS + "c = AsmCell<recipe=iron-gear-wheel, ins=iron-plate, "
                              "out=iron-gear-wheel>",
                "$ins[1]: ins is a list of 1 (iron-plate) in this AsmCell, so $ins[0] to $ins[0]")
        refused(self, CELLS + "c = Stack<cell=AsmCell, n=2, recipe=iron-gear-wheel, "
                              "ins=iron-plate, out=iron-gear-wheel>", "ins is a list of 1")

    def test_a_flag_for_a_value(self):
        refused(self, CELLS + "c = FurnaceCell<plate, ore=iron-ore>",
                "FurnaceCell's parameter plate takes a value")

    def test_stack_still_checks_the_ports_after_substitution(self):
        # a cell whose two ends carry different items once substituted
        refused(self, "module M<a, b> size 3x3 {\n  port i : in $a @s1\n  port o : out $b @n1\n"
                      "  stack i -> o\n  c = Chest<provider> @(1, 1)\n  net n: i -> c\n}\n"
                      "s = Stack<cell=M, n=2, a=iron-ore, b=copper-ore>",
                "one port in and one out, carrying the same items")
        flat_of("module M<a, b> size 3x3 {\n  port i : in $a @s1\n  port o : out $b @n1\n"
                "  stack i -> o\n  c = Chest<provider> @(1, 1)\n  net n: i -> c, o\n}\n"
                "s = Stack<cell=M, n=2, a=iron-ore, b=iron-ore>")


class StackTest(unittest.TestCase):
    def test_forwarding_to_cells(self):
        flat = flat_of(CELLS + "s = Stack<cell=FurnaceCell, n=3, plate=copper-plate, "
                               "ore=copper-ore>")
        self.assertEqual({flat.machines[f"s/{k}/f/m0"].recipe for k in range(3)}, {"copper-plate"})
        self.assertEqual(flat.nets["s/ore_out_1"].items, ["copper-ore"])
        self.assertEqual(flat.insts["s"].params["plate"], "copper-plate")
        self.assertEqual(flat.insts["s/1"].params, {"plate": "copper-plate", "ore": "copper-ore"})

    def test_a_kind_as_the_cell(self):
        flat = flat_of(CELLS + "kind CopperCell = FurnaceCell<plate=copper-plate, ore=copper-ore>\n"
                               "s = Stack<cell=CopperCell, n=2>")
        self.assertEqual(flat.machines["s/1/f/m0"].recipe, "copper-plate")
        self.assertEqual(flat.stacks["s"][0], "FurnaceCell")

    def test_a_kind_of_a_stack(self):
        flat = flat_of(CELLS + "kind Copper = Stack<cell=FurnaceCell, plate=copper-plate, "
                               "ore=copper-ore>\ns = Copper<n=2>")
        self.assertEqual(flat.machines["s/1/f/m0"].recipe, "copper-plate")

    def test_the_head_takes_what_it_declares(self):
        src = CELLS + """
module Head<plate, extra=1> size 7x3 {
  port ore_out : out iron-ore @n0
  port pl_in   : in  $plate @n6
  feed = Chest<requester, item=iron-ore, rate=$extra> @(0, 1)
  box  = Chest<provider> @(6, 1)
  net a: feed -> ore_out
  net b: pl_in -> box
}
s = Stack<cell=FurnaceCell, head=Head, n=2, plate=iron-plate, ore=iron-ore>"""
        flat = flat_of(src)
        self.assertEqual(flat.insts["s/head"].params, {"plate": "iron-plate", "extra": 1})
        self.assertEqual(flat.ports["s/head/pl_in"].items, ["iron-plate"])
        # a parameter the head declares and the cell doesn't goes to the head only
        flat = flat_of(src.replace("n=2,", "n=2, extra=2,"))
        self.assertEqual(flat.insts["s/head"].params["extra"], 2)
        self.assertNotIn("extra", flat.insts["s/0"].params)

    def test_one_choice_per_set_of_values(self):
        src = ("module M<recipe> size 5x5 {\n  a = Assembler<recipe=$recipe, machine=auto>"
               " @(1, 1)\n}\nx = M<recipe=pipe>\ny = M<recipe=lubricant>\nz = M<recipe=pipe>")
        flat = flat_of(src)
        self.assertEqual(sorted(flat.choices), ["M<recipe=lubricant>.a.machine",
                                                "M<recipe=pipe>.a.machine"])
        self.assertEqual(flat.choices["M<recipe=pipe>.a.machine"].paths, ["x/a", "z/a"])
        self.assertNotIn("assembling-machine-1", flat.choices["M<recipe=lubricant>.a.machine"].menu)


class EndToEndTest(unittest.TestCase):
    """The parameterised FurnaceCell stacked for iron and for copper: elaborated, rated, laid out,
    routed and connected (tests/params/smelt.fk, built on the lab for 2.1's module parameters)."""

    @classmethod
    def setUpClass(cls):
        cls.flat = elaborate_file(os.path.join(PARAMS, "smelt.fk"), CAT)

    def test_rates(self):
        model = rates.solve(self.flat)
        made = {}
        for key, m in self.flat.machines.items():
            for item, rate in m.makes.items():
                if m.kind != "Port":
                    made[item] = made.get(item, 0) + rate * model.util.get(key, 0)
        self.assertAlmostEqual(made["iron-plate"], 2.5)
        self.assertAlmostEqual(made["copper-plate"], 2.5)

    def test_routes_and_connects(self):
        lay, notes = expand.expand_factory(self.flat, CAT)
        self.assertEqual(notes, [])
        r = route.route_layout(self.flat, lay, CAT)
        self.assertEqual(r.failed, {})
        rep = connect.connect(r.layout, CAT, connect.endpoints(self.flat), self.flat._port_edges)
        self.assertEqual({n for n, x in rep.nets.items() if x.status != "connected"}, set())
        self.assertEqual(rep.leaks, [])

    def test_identity(self):
        # the values are on each cell's .fkp line, so a changed one changes the line
        lay, _notes = expand.expand_factory(self.flat, CAT)
        self.assertEqual(lay.insts["copper/2"].params, {"plate": "copper-plate",
                                                        "ore": "copper-ore"})
        self.assertEqual(self.flat.insts["iron"].params["plate"], "iron-plate")
        from fkcore import fkp
        self.assertIn("inst iron/0 FurnaceCell ore=iron-ore plate=iron-plate", fkp.dumps(lay))


if __name__ == "__main__":
    unittest.main()
