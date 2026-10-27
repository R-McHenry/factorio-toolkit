import os
import tempfile
import unittest

from fkcore import lang
from fkcore.catalog import Catalog
from fkcore.elaborate import ElabError, elaborate, elaborate_file

CAT = Catalog.load()
DATA = os.path.join(os.path.dirname(__file__), "data")


def flat_of(text):
    f = lang.parse(text, "t.fk")
    return elaborate(f, dict(f.modules), CAT, "t")


def codes(flat):
    return [c.code for c in flat.checks]


class EndpointTest(unittest.TestCase):
    def test_a_ref_adds_only_the_nets_items(self):
        flat = flat_of("""
            smelt = SmelterRow<n=2, recipe=iron-plate>
            gears = AsmRow<n=1, recipe=iron-gear-wheel>
            belts = AsmRow<n=1, recipe=transport-belt>
            net iron: smelt -> gears, belts
            net gear: gears -> belts
        """)
        iron, gear = flat.nets["iron"], flat.nets["gear"]
        self.assertEqual(iron.items, ["iron-plate"])
        self.assertEqual(iron.drivers, [("smelt/m0", "iron-plate"), ("smelt/m1", "iron-plate")])
        self.assertEqual(iron.consumers, [("gears/m0", "iron-plate"), ("belts/m0", "iron-plate")])
        self.assertEqual(gear.consumers, [("belts/m0", "iron-gear-wheel")])
        self.assertIn("no-feed", codes(flat))           # the smelters' ore and coal
        self.assertIn("no-taker", codes(flat))      # the belts

    def test_type(self):
        flat = flat_of("""
            smelt = SmelterRow<n=1, recipe=iron-plate>
            red = AsmRow<n=1, recipe=automation-science-pack>
            net iron: smelt -> red
            net x items copper-plate: smelt -> red
        """)
        msgs = [c.msg for c in flat.checks if c.code == "cannot-carry"]
        self.assertIn("consumer red takes no iron-plate", msgs)
        self.assertIn("expects copper-plate but no driver makes it", msgs)

    def test_star_takes_free_endpoints_only(self):
        flat = elaborate_file(os.path.join(DATA, "..", "..", "games", "spm10", "main.fk"), CAT)
        out = flat.nets["mall_out"]
        self.assertEqual(len(out.items), 20)
        for item in ("copper-cable", "iron-stick"):     # made in the mall, used in the mall
            self.assertNotIn(item, out.items)
        self.assertIn(("mall/belts/m0", "transport-belt"), out.drivers)
        self.assertNotIn(("mall/belts_i/m0", "transport-belt"), out.drivers)
        iron = flat.nets["iron_plate"]
        self.assertIn(("mall/ichests/m0", "iron-plate"), iron.consumers)
        self.assertNotIn(("mall/furnaces/m0", "iron-plate"), iron.consumers)

    def test_double(self):
        flat = flat_of("""
            smelt = SmelterRow<n=1, recipe=iron-plate>
            pipes = AsmRow<n=1, recipe=pipe>
            net a: smelt -> pipes
            net b: smelt -> pipes
        """)
        self.assertEqual(codes(flat).count("two-nets"), 2)

    def test_duty_reaches_every_machine_of_a_module(self):
        flat = flat_of("""
            module M { a = AsmRow<n=2, recipe=pipe>  b = Assembler<recipe=iron-chest, duty=0.5> }
            m = M<duty=0.1>
        """)
        self.assertEqual({k: v.duty for k, v in flat.machines.items()},
                         {"m/a/m0": 0.1, "m/a/m1": 0.1, "m/b/m0": 0.1})

    def test_malformed_source_raises(self):
        for text, msg in (("a = AsmRow<n=3, recipe=pipe, pole=small-electric-pole>", "unknown parameter"),
                          ("a = Belt<n=3>", "unknown template Belt"),
                          ("a = AsmRow<n=1, recipe=pipe>\nnet x: a -> nope", "nope names nothing"),
                          ("a = AsmRow<n=1, recipe=pipe>\na = AsmRow<n=1, recipe=pipe>", "twice")):
            with self.assertRaises(ElabError) as cm:
                flat_of(text)
            self.assertIn(msg, str(cm.exception))

    def test_imports(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "lib.fk"), "w") as fh:
                fh.write("module Pair { a = AsmRow<n=2, recipe=pipe> }\n")
            with open(os.path.join(d, "top.fk"), "w") as fh:
                fh.write('import Pair from "lib.fk"\np = Pair\n')
            flat = elaborate_file(os.path.join(d, "top.fk"), CAT)
        self.assertEqual(list(flat.machines), ["p/a/m0", "p/a/m1"])
        self.assertEqual(flat.name, "top")


if __name__ == "__main__":
    unittest.main()
