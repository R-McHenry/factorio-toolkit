"""2.1 (PLAN-2.1 A, B and I): ``Machine``, ``Entity``, ``kind`` and the prelude."""
import os
import tempfile
import unittest

from fkcore import lang
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, PRELUDE, elaborate, elaborate_file, prelude_path
from fkcore.lang import FkSyntaxError

CAT = Catalog.load()
ROOT = os.path.join(os.path.dirname(__file__), "..")


def flat_of(text, path="t.fk"):
    f = lang.parse(text, path)
    return elaborate(f, dict(f.modules), CAT, "t")


def refused(test, text, *msgs):
    with test.assertRaises(ElabError) as cm:
        flat_of(text)
    for msg in msgs:
        test.assertIn(msg, str(cm.exception))
    return str(cm.exception)


def write(d, name, text):
    p = os.path.join(d, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


class MachineTest(unittest.TestCase):
    def test_a_centrifuge(self):
        flat = flat_of("c = Machine<entity=centrifuge, recipe=uranium-processing>")
        m = flat.machines["c/m0"]
        self.assertEqual((m.prototype, m.recipe, m.kind), ("centrifuge", "uranium-processing",
                                                           "Machine"))
        self.assertAlmostEqual(m.needs["uranium-ore"], 10 / 12)
        self.assertAlmostEqual(m.makes["uranium-238"], 1 / 12)

    def test_machine_is_a_synonym_for_entity(self):
        a = flat_of("a = Machine<machine=assembling-machine-2, recipe=iron-gear-wheel>")
        b = flat_of("a = Machine<entity=assembling-machine-2, recipe=iron-gear-wheel>")
        self.assertEqual(a.machines["a/m0"].needs, b.machines["a/m0"].needs)
        refused(self, "a = Machine<machine=assembling-machine-2, entity=assembling-machine-3, "
                      "recipe=iron-gear-wheel>", "one parameter")

    def test_a_burner_takes_fuel_and_a_furnace_ore(self):
        flat = flat_of("f = Machine<entity=steel-furnace, ore=copper-ore, fuel=solid-fuel>")
        m = flat.machines["f/m0"]
        self.assertEqual(m.recipe, "copper-plate")
        self.assertIn("solid-fuel", m.needs)
        flat = flat_of("f = Machine<entity=stone-furnace, recipe=iron-plate>")
        self.assertIn("coal", flat.machines["f/m0"].needs)       # the default fuel
        flat = flat_of("f = Machine<entity=electric-furnace, recipe=iron-plate, fuel=coal>")
        self.assertNotIn("coal", flat.machines["f/m0"].needs)    # an electric one burns nothing

    def test_refusals(self):
        refused(self, "a = Machine<entity=no-such-thing, recipe=iron-gear-wheel>",
                "unknown entity no-such-thing")
        refused(self, "a = Machine<entity=assembling-machine-2>", "needs recipe=")
        refused(self, "a = Machine<entity=stone-furnace>", "needs recipe= (or ore=)")
        refused(self, "a = Machine<recipe=iron-gear-wheel>", "needs entity=")
        refused(self, "a = Machine<entity=small-lamp, recipe=iron-gear-wheel>",
                "not a crafting machine", "Entity<name=small-lamp>")
        refused(self, "a = Machine<entity=assembling-machine-2, ore=iron-ore>", "not a furnace")

    def test_no_fluidbox(self):
        msg = refused(self, "a = Assembler<recipe=lubricant>", "no-fluidbox", "assembling-machine-1",
                      "never run")
        self.assertIn("a = Assembler", msg)
        refused(self, "a = Machine<entity=centrifuge, recipe=sulfuric-acid>", "no-fluidbox")
        # the boxes it has: one in and one out on an assembling-machine-2, so not two fluids in
        flat_of("a = Assembler<recipe=lubricant, machine=assembling-machine-2>")
        flat_of("a = ChemPlant<recipe=plastic-bar>")
        refused(self, "a = Assembler<recipe=advanced-oil-processing, machine=assembling-machine-3>",
                "no-fluidbox")


class EntityTest(unittest.TestCase):
    def test_a_lamp_is_placed_and_moves_nothing(self):
        flat = flat_of("lamp = Entity<name=small-lamp>")
        m = flat.machines["lamp/m0"]
        self.assertEqual((m.prototype, m.needs, m.makes, m.sink), ("small-lamp", {}, {}, False))
        self.assertEqual([c.code for c in flat.checks], [])

    def test_refusals(self):
        refused(self, "x = Entity<name=nope>", "unknown entity nope")
        refused(self, "x = Entity<name=centrifuge>", "Machine<entity=centrifuge")
        refused(self, "x = Entity", "needs name=")

    def test_it_is_wireable(self):
        flat = flat_of("lamp = Entity<name=small-lamp>\nc = Constant<signals=\"signal-A=1\">\n"
                       "wire w red: c -> lamp")
        self.assertIn("w", flat.circuit.wires)


class KindTest(unittest.TestCase):
    def test_the_prelude_kinds(self):
        flat = flat_of("a = Assembler<recipe=iron-gear-wheel>\nf = Furnace<ore=iron-ore>\n"
                       "c = ChemPlant<recipe=plastic-bar>\nr = Refinery")
        self.assertEqual({k: m.prototype for k, m in flat.machines.items()},
                         {"a/m0": "assembling-machine-1", "f/m0": "stone-furnace",
                          "c/m0": "chemical-plant", "r/m0": "oil-refinery"})
        self.assertEqual(flat.machines["r/m0"].recipe, "basic-oil-processing")
        self.assertIn("coal", flat.machines["f/m0"].needs)
        a = flat.insts["a"]
        self.assertEqual((a.kind, a.core, a.params), ("Assembler", "Machine",
                                                      {"recipe": "iron-gear-wheel"}))

    def test_instance_params_override_and_machine_overrides_entity(self):
        flat = flat_of("a = Assembler<recipe=iron-gear-wheel, machine=assembling-machine-3>")
        self.assertEqual(flat.machines["a/m0"].prototype, "assembling-machine-3")

    def test_a_kind_of_a_kind_keeps_the_instance_name(self):
        flat = flat_of("""
            kind Asm2 = Assembler<machine=assembling-machine-2>
            kind Gears = Asm2<recipe=iron-gear-wheel>
            g = Gears
            c = Chest<storage>
            net n: g -> c
        """)
        self.assertEqual(list(flat.machines), ["g/m0", "c/c0"])
        m = flat.machines["g/m0"]
        self.assertEqual((m.prototype, m.recipe, m.kind), ("assembling-machine-2",
                                                           "iron-gear-wheel", "Gears"))
        self.assertEqual(flat.nets["n"].drivers, [("g/m0", "iron-gear-wheel")])

    def test_a_cycle_is_refused(self):
        refused(self, "kind A = B<recipe=pipe>\nkind B = A\na = A", "cycle", "A -> B -> A")
        refused(self, "kind A = A\na = A", "names A")      # no layer below has an A

    def test_unknown_targets_are_refused(self):
        refused(self, "kind A = Nothing<recipe=pipe>\na = A", "names Nothing")
        refused(self, "a = Nothing", "unknown template Nothing")
        refused(self, 'kind L = Literal<file="x.json">\nl = L', "written as itself")

    def test_a_kind_may_build_on_the_prelude_kind_of_its_name(self):
        flat = flat_of("kind Furnace = Furnace<fuel=wood>\nf = Furnace<ore=iron-ore>")
        self.assertIn("wood", flat.machines["f/m0"].needs)

    def test_a_kind_of_a_core_kind_and_of_a_row(self):
        flat = flat_of("kind Box = Chest<storage>\nb = Box<item=iron-plate>")
        self.assertEqual(flat.machines["b/c0"].prototype, "storage-chest")
        flat = flat_of("kind Iron = SmelterRow<ore=iron-ore>\nr = Iron<n=auto 2..4>")
        self.assertEqual(len(flat.insts["r"].machines), 2)

    def test_a_kind_of_a_module(self):
        flat = flat_of("module M { a = Assembler<recipe=pipe> }\nkind N = M\nx = N<duty=0.5>")
        self.assertEqual(flat.machines["x/a/m0"].duty, 0.5)
        refused(self, "module M { a = Assembler<recipe=pipe> }\nkind N = M<recipe=pipe>\nx = N",
                "takes only duty=")

    def test_parse_refusals(self):
        with self.assertRaises(FkSyntaxError):
            lang.parse("module M { kind A = Assembler }")
        with self.assertRaises(FkSyntaxError):
            lang.parse("kind A = Assembler\nkind A = Furnace")
        with self.assertRaises(FkSyntaxError):
            lang.parse("kind A = Assembler\nmodule A { }")
        f = lang.parse("kind = Assembler<recipe=pipe>")     # an instance named kind
        self.assertEqual(f.body.insts[0].name, "kind")


class PreludeTest(unittest.TestCase):
    def test_the_toolkit_prelude_and_the_template_copy(self):
        self.assertEqual(prelude_path("<fk>"), PRELUDE)
        with open(PRELUDE, encoding="utf-8") as fh:
            ours = fh.read()
        with open(os.path.join(ROOT, "kickoff", "template", "game", "prelude.fk"),
                  encoding="utf-8") as fh:
            self.assertEqual(fh.read(), ours)

    def test_a_runs_prelude_wins(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "game/prelude.fk", "kind Assembler = Machine<entity=assembling-machine-2>\n")
            top = write(d, "game/world.fk", "a = Assembler<recipe=pipe>\n")
            notes = write(d, "notes/try.fk", "a = Assembler<recipe=pipe>\n")
            self.assertEqual(prelude_path(top), os.path.join(d, "game", "prelude.fk"))
            for p in (top, notes):
                flat = elaborate_file(p, CAT)
                self.assertEqual(flat.machines["a/m0"].prototype, "assembling-machine-2")

    def test_a_files_own_kind_and_module_win(self):
        flat = flat_of("kind Assembler = Machine<entity=assembling-machine-3>\n"
                       "a = Assembler<recipe=pipe>")
        self.assertEqual(flat.machines["a/m0"].prototype, "assembling-machine-3")
        flat = flat_of("module Assembler { x = Machine<entity=centrifuge, "
                       "recipe=uranium-processing> }\na = Assembler")
        self.assertEqual(list(flat.machines), ["a/x/m0"])

    def test_a_kind_comes_with_its_file(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "lib.fk", "kind Gears = Assembler<recipe=iron-gear-wheel>\n"
                               "module Pair { a = Gears  b = Gears }\n")
            top = write(d, "top.fk", 'import Pair, Gears from "lib.fk"\np = Pair\ng = Gears\n')
            flat = elaborate_file(top, CAT)
        self.assertEqual(sorted(flat.machines), ["g/m0", "p/a/m0", "p/b/m0"])

    def test_a_body_imported_as_a_module_brings_its_modules(self):
        # the kickoff template's nauvis.fk places world.fk's body; a module world.fk defines
        # (a mall) used to be unknown there
        with tempfile.TemporaryDirectory() as d:
            write(d, "world.fk", "module Mall { a = Assembler<recipe=pipe> }\nmall = Mall\n")
            top = write(d, "nauvis.fk", 'import World from "world.fk"\nworld = World\n')
            flat = elaborate_file(top, CAT)
        self.assertEqual(list(flat.machines), ["world/mall/a/m0"])

    def test_a_prelude_holds_kinds_only(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "prelude.fk", "a = Assembler<recipe=pipe>\n")
            top = write(d, "x.fk", "b = Machine<entity=assembling-machine-1, recipe=pipe>\n")
            with self.assertRaises(ElabError) as cm:
                elaborate_file(top, CAT)
        self.assertIn("kind lines only", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
