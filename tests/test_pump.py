"""3.0 pumps in fluid nets (the live run, ~7800k: a 620-tile lubricant line needed pumps and none
could be written). ``Pump<fluid=...>`` is one pump that ends two nets, ``net a: x -> p`` and
``net b: p -> y``; routing.fk's ``InlinePump`` puts one in a chain, ``net N: x -> pp -> y``. And the
``pipe-too-long`` check: in Factorio 2.0 a pipe segment that spreads outside 320x320 tiles carries
nothing until a pump breaks it up."""
import os
import unittest

from fkcore import connect, expand, fkp, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()
ROUTING = os.path.join(os.path.dirname(__file__), "..", "kickoff", "template", "game",
                       "routing.fk")


def routed(text):
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay, _notes = expand.expand_factory(flat, CAT)
    r = route.route_layout(flat, lay, CAT)
    rep = connect.connect(r.layout, CAT, connect.endpoints(flat),
                          expand.port_edges(flat, r.layout, CAT) or None)
    return flat, r, rep


class PumpTest(unittest.TestCase):
    def test_a_pump_ends_two_nets(self):
        for rot in (1, 2):
            with self.subTest(rot=rot):
                flat, r, rep = routed(f"""
op = OffshorePump<rate=1200/s> @(0, 17, rot 3)
pm = Pump<fluid=water>         @(20, 17, rot {rot})
b1 = Boiler<fuel=coal>         @(40, 13)
net w1: op -> pm
net w2: pm -> b1
""")
                self.assertEqual(r.failed, {})
                self.assertEqual({n: x.status for n, x in rep.nets.items()},
                                 {"w1": "connected", "w2": "connected"})
                self.assertEqual(fkp.invariants(r.layout, CAT, nets=flat.nets), [])

    def test_a_pump_in_a_chain(self):
        with open(ROUTING, encoding="utf-8") as fh:
            lib = fh.read()
        flat, r, rep = routed(lib + """
op = OffshorePump<rate=1200/s> @(0, 17, rot 3)
pp = InlinePump<fluid=water>   @(20, 15, rot 3)
b1 = Boiler<fuel=coal>         @(40, 13)
net water: op -> pp -> b1
""")
        self.assertEqual(r.failed, {})
        self.assertEqual(flat.nets["water@pp"].chain, "water")
        self.assertEqual({n: x.status for n, x in rep.nets.items()},
                         {n: "connected" for n in ("water", "water@pp", "pp/a", "pp/b")})

    def test_a_pump_needs_a_fluid(self):
        f = lang.parse("pm = Pump<fluid=iron-plate> @(0, 0)\n", "t.fk")
        with self.assertRaises(Exception) as got:
            elaborate(f, dict(f.modules), CAT, "t")
        self.assertIn("iron-plate is not a fluid", str(got.exception))


class LongPipeTest(unittest.TestCase):
    def pipes(self, n, pump_at=None):
        ents = []
        for x in range(n):
            if pump_at is not None and x in (pump_at, pump_at + 1):
                if x == pump_at:
                    ents.append(fkp.Entity("pm/m0", "pump", x + 1, 0.5, 4, {}))
                continue
            net = "w" if pump_at is None or x < pump_at else "w2"
            ents.append(fkp.Entity(f"~{net}/p{x}", "pipe", x + 0.5, 0.5, 0, {"net": net}))
        return connect.graph(ents, CAT)

    def test_a_segment_past_320_tiles_is_named(self):
        checks = connect.long_pipes(self.pipes(330))
        self.assertEqual([(c.code, c.where) for c in checks], [("pipe-too-long", "net w")])
        self.assertIn("spans 330x1 tiles", checks[0].msg)
        self.assertIn("At least 1 pump in it", checks[0].msg)
        self.assertEqual(connect.long_pipes(self.pipes(320)), [])

    def test_a_pump_breaks_the_segment(self):
        g = self.pipes(330, pump_at=160)
        self.assertEqual(connect.long_pipes(g), [])
        self.assertEqual(sorted(len(keys) for keys, _box, _nets in connect.pipe_runs(g)),
                         [160, 168])


if __name__ == "__main__":
    unittest.main()
