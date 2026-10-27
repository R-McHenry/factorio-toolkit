"""2.0.47: CircuitStack, green circuits on both sides of one output belt.

Rory, 2026-10-26: "try and use smelter and green circuit factories that fill both sides of the
output belt". SmelterArray already does it for furnaces; CircuitStack is its counterpart for
assemblers: two columns of circuit assemblers around one output belt, each handed cable directly by
the two cable assemblers above and below it, iron and copper on the lanes of its own feed belts.
"""
import unittest

from fkcore import connect, expand, lang, rates, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate
from fkcore.templates import TemplateError

CAT = Catalog.load()

STACK = """
fe  = Chest<requester, item=iron-plate, rate=8/s> @(2, 40)
cu  = Chest<requester, item=copper-plate, rate=8/s> @(24, 20)
cs  = CircuitStack<n=6> @(4, 0)
box = Chest<provider, limit=48> @(10, 45)
net fen: fe -> cs
net cun: cu -> cs
net out: cs -> box
"""


def build(text):
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay, _ = expand.expand_factory(flat, CAT)
    return flat, lay, route.route_layout(flat, lay, CAT)


class CircuitStackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flat, cls.lay, cls.r = build(STACK)

    def test_its_machines_are_the_circuit_assemblers(self):
        ms = [k for k in self.flat.machines if k.startswith("cs/")]
        self.assertEqual(sorted(ms), [f"cs/m{k}" for k in range(6)])
        m = self.flat.machines["cs/m0"]
        self.assertAlmostEqual(m.makes["electronic-circuit"], 1.0)
        self.assertAlmostEqual(m.needs["iron-plate"], 1.0)
        self.assertAlmostEqual(m.needs["copper-plate"], 1.5)     # 3 cable

    def test_both_sides_of_the_output_belt(self):
        ents = self.lay.entities
        outs = [e for k, e in ents.items() if k.startswith("cs/o") and "inserter" in e.name]
        self.assertEqual(len(outs), 6)
        belt_x = 4 + 6.5
        self.assertEqual(sorted({e.x for e in outs}), [belt_x - 1, belt_x + 1])  # one each side
        self.assertTrue(all(e.attrs.get("net") == "out" for e in outs))
        cable = [e for k, e in ents.items() if k.startswith("cs/k") and e.name.startswith("assembling")]
        self.assertEqual(len(cable), 12)                         # two cable assemblers a circuit
        self.assertTrue(all(e.attrs.get("recipe") == "copper-cable" for e in cable))

    def test_it_routes_and_judges_clean(self):
        self.assertEqual(self.r.failed, {})
        rep = connect.connect(self.r.layout, CAT, connect.endpoints(self.flat))
        self.assertEqual([ln for ln in rep.lines() if "LEAK" in ln], [])

    def test_the_rate_model_feeds_it_iron_and_copper(self):
        model = rates.solve(self.flat)
        # 8 copper/s for 6 circuits that take 1.5 each: the copper binds, 5.33 circuits/s
        self.assertAlmostEqual(model.inst_rate("cs", "electronic-circuit"), 8 / 1.5, places=3)

    def test_too_many_for_one_stack(self):
        with self.assertRaises(Exception) as cm:
            build(STACK.replace("n=6", "n=16"))
        self.assertIn("two stacks", str(cm.exception))


class RelayTest(unittest.TestCase):
    def test_only_a_template_intermediate_maker_is_a_relay(self):
        # a cable assembler of the stack hands its copper on as the cable its circuit assemblers
        # take; an assembler of the same instance whose product the consumer doesn't use is not a
        # relay (test_connect's stray m/b, a transport-belt maker beside a gear consumer)
        flat, lay, r = build(STACK)
        table = {n: ([k for k, _i in net.drivers], [k for k, _i in net.consumers])
                 for n, net in flat.nets.items()}
        g = connect.graph(r.layout, CAT)
        self.assertTrue(connect._relay(g, "cs/k0", ["cun"], table, CAT))
        self.assertFalse(connect._relay(g, "cs/m0", ["cun"], table, CAT))   # a netlist machine
        self.assertFalse(connect._relay(g, "cs/k0", ["out"], table, CAT))   # box takes no cable


if __name__ == "__main__":
    unittest.main()
