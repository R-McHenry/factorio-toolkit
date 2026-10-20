import unittest

from fkcore import lang


class ParseTest(unittest.TestCase):
    def test_statements(self):
        f = lang.parse("""
            import Mall from "mall.fk"
            module Row { a = AsmRow<n=2, recipe=pipe> }
            gears = AsmRow<n=3, recipe=iron-gear-wheel> @(10, -4, rot 1)
            chest = Chest<provider, rate=12/min>
            wells = Pumpjack<rate=30/s> @patch(crude-oil)
            net gear: gears -> red, mall.belts
            net mall_in items iron-plate, iron-gear-wheel: smelt, gears -> mall.*
            power self: cover all, pole=medium-electric-pole
            robots main: cover main, boot
            assert red.rate >= 10/min
        """, "t.fk")
        self.assertEqual(f.imports, [(["Mall"], "mall.fk", 2)])
        self.assertEqual(list(f.modules), ["Row"])
        insts = {i.name: i for i in f.body.insts}
        self.assertEqual(insts["gears"].params, {"n": 3, "recipe": "iron-gear-wheel"})
        self.assertEqual(insts["gears"].hints, {"at": (10, -4, 1)})
        self.assertEqual(insts["chest"].params, {"provider": True, "rate": 0.2})
        self.assertEqual(insts["wells"].hints, {"patch": "crude-oil"})
        gear, mall_in = f.body.nets
        self.assertIsNone(gear.items)
        self.assertEqual([str(r) for r in gear.consumers], ["red", "mall.belts"])
        self.assertEqual(mall_in.items, ["iron-plate", "iron-gear-wheel"])
        self.assertTrue(mall_in.consumers[0].star)
        power, robots = f.body.covers
        self.assertIsNone(power.targets)
        self.assertEqual(power.params, {"pole": "medium-electric-pole"})
        self.assertEqual([str(r) for r in robots.targets], ["main", "boot"])
        (a,) = f.body.asserts
        self.assertEqual((str(a.ref), a.op), ("red", ">="))
        self.assertAlmostEqual(a.rate, 10 / 60)

    def test_errors_carry_the_line(self):
        with self.assertRaises(lang.FkSyntaxError) as cm:
            lang.parse("gears = AsmRow<n=3>\nnet gear: gears ->\n", "t.fk")
        self.assertEqual(cm.exception.line, 3)
        with self.assertRaises(lang.FkSyntaxError) as cm:
            lang.parse("iron-row = AsmRow<n=3>\n", "t.fk")
        self.assertIn("may not contain dashes", str(cm.exception))
        with self.assertRaises(lang.FkSyntaxError):
            lang.parse("assert red >= 10/min\n", "t.fk")
        with self.assertRaises(lang.FkSyntaxError):
            lang.parse("c = Chest<rate=3/day>\n", "t.fk")


if __name__ == "__main__":
    unittest.main()
