"""The steam chain's kinds (Boiler, SteamEngine) and the lab's InfinityPipe: machines, rates,
and single fluid machines turned by the hint's rot."""
import unittest

from fkcore import expand, fkp, lang, rates
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()


def build(text):
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay, notes = expand.expand_factory(flat, CAT)
    assert fkp.invariants(lay, CAT) == [], fkp.invariants(lay, CAT)
    return flat, lay


class FluidTemplateTest(unittest.TestCase):
    def test_the_steam_chain(self):
        flat, lay = build("""
            pump = OffshorePump @(0, 2, rot 3)
            b    = Boiler<fuel=coal> @(2, 0, rot 1)
            e    = SteamEngine @(6, 0)
            gas  = InfinityPipe<fluid=petroleum-gas, rate=30/s> @(10, 0)
            net water: pump -> b
            net steam: b -> e
        """)
        boiler = lay.entities["b/m0"]
        self.assertEqual((boiler.dir, sorted(fkp.tiles_of(CAT, boiler))),
                         (4, [(2, 0), (2, 1), (2, 2), (3, 0), (3, 1), (3, 2)]))    # 2x3 facing E
        self.assertEqual(lay.entities["pump/m0"].dir, 12)
        self.assertIsNone(lay.entities["gas/m0"].dir)
        m = flat.machines
        self.assertEqual((m["b/m0"].needs, m["b/m0"].makes), ({"water": 60.0, "coal": 0.45},
                                                              {"steam": 60.0}))
        self.assertEqual((m["e/m0"].needs, m["e/m0"].makes), ({"steam": 30.0}, {}))
        self.assertEqual(m["gas/m0"].makes, {"petroleum-gas": 30.0})
        model = rates.solve(flat)
        self.assertAlmostEqual(model.util["e/m0"], 0.0)  # the boiler's coal has no net

    def test_unfold_keeps_the_netlist(self):
        flat, lay = build("""
            b   = Boiler<fuel=coal> @(2, 0)
            e   = SteamEngine @(6, 0)
            gas = InfinityPipe<fluid=water, rate=60/s> @(0, 0)
            net steam: b -> e
            net water: gas -> b
        """)
        text = "\n".join(f"{p} = Literal" for p in ("b", "e", "gas")) + \
            "\nnet steam: b -> e\nnet water: gas -> b\n"
        f = lang.parse(text, "u.fk")
        again = elaborate(f, {}, CAT, "u", layout=lay)
        for key, m in flat.machines.items():
            self.assertEqual((again.machines[key].needs, again.machines[key].makes),
                             (m.needs, m.makes), key)


if __name__ == "__main__":
    unittest.main()
