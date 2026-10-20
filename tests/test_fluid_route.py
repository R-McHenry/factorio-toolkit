"""The router's fluid plug-in (fkcore.fluid_route): pipes and pipe-to-ground for fluid nets, on
the test game games/lab-fluids (water -> boilers -> steam engines; water + petroleum gas -> a
chemical plant), judged by fkcore.connect; and that game through its own build script on paper."""
import os
import unittest

from fkcore import codec, connect, expand, fkp, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate, elaborate_file

CAT = Catalog.load()
GAME = os.path.join(os.path.dirname(__file__), "..", "games", "lab-fluids")


def build(text):
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay, notes = expand.expand_factory(flat, CAT)
    assert fkp.invariants(lay, CAT) == [], fkp.invariants(lay, CAT)
    return flat, lay


class FluidRouteTest(unittest.TestCase):
    def route(self, name):
        flat = elaborate_file(os.path.join(GAME, f"{name}.fk"), CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        r = route.route_layout(flat, lay, CAT)
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
        return flat, r, rep

    def test_water_and_steam(self):
        flat, r, rep = self.route("steam")
        self.assertEqual(r.failed, {})
        self.assertEqual(r.lines, [
            "routed    steam: 2 -> 4, 6 pipes, 1 pipe-to-ground pair, 2 direct joins",
            "routed    water: 1 -> 2, 9 pipes, 0 pipe-to-ground pairs"])
        self.assertEqual({n: x.status for n, x in rep.nets.items()},
                         {"steam": "connected", "water": "connected"})
        self.assertEqual(rep.checks, [])                 # no UNROUTED, OPEN or LEAK
        self.assertEqual(fkp.invariants(r.layout, CAT, nets=flat.nets), [])
        for key, e in r.layout.entities.items():
            if key.startswith("~"):
                self.assertEqual((e.net, e.name, key.split("/")[1][0]),
                                 (e.owner[1:], {"p": "pipe", "g": "pipe-to-ground"}[
                                     key.split("/")[1][0]], key.split("/")[1][0]))
        g0, g1 = r.layout.entities["~steam/g0"], r.layout.entities["~steam/g1"]
        self.assertEqual((g0.dir, g1.dir), (4, 12))      # open sides face away from each other

    def test_two_inputs_and_a_crossing(self):
        flat, r, rep = self.route("sulfur")
        self.assertEqual(sorted(r.routed), ["gas", "water"])
        self.assertEqual(rep.checks, [])
        ends = [e for k, e in r.layout.entities.items() if k.startswith("~gas/g")]
        (y,) = {e.y for e in ends}
        xs = sorted(e.x for e in ends)
        under = [e for k, e in r.layout.entities.items() if k.startswith("~water/p")
                 and e.y == y and xs[0] < e.x < xs[1]]
        self.assertEqual(len(under), 1)                  # the gas pair passes under the water

    def test_the_belt_router_keeps_off_the_connection_tiles(self):
        flat, lay = build("""
            water = OffshorePump        @(20, 0)
            chem  = ChemPlant<recipe=sulfur> @(20, 6)
            net w: water -> chem
        """)
        job = route.jobs(flat, lay, CAT)["w"]
        self.assertIsNone(job.skip)
        self.assertIn((20, 5), job.reserved)             # the water input's pipe tile
        self.assertIn((20, 1), job.reserved)             # the pump's outlet
        self.assertTrue({(19, -2), (21, -1)} <= set(job.reserved))   # its water

    def test_a_net_that_cannot_be_tried_is_skipped(self):
        flat, lay = build("""
            gas  = InfinityPipe<fluid=petroleum-gas, rate=30/s> @(0, 0)
            chem = ChemPlant<recipe=plastic-bar>
            net g: gas -> chem
        """)
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.lines, ["skipped   g: chem/m0 is not placed"])

    def test_deterministic(self):
        a = self.route("steam")[1]
        b = self.route("steam")[1]
        self.assertEqual(fkp.dumps(a.layout), fkp.dumps(b.layout))

    def test_the_codec_writes_the_direction(self):
        _flat, r, _rep = self.route("steam")
        rows, _ = codec.read_blueprint(codec.fkp_to_blueprint(r.layout))
        by_key = {row["src"]: row for row in rows}
        self.assertEqual(by_key["~steam/g1"]["direction"], 12)
        self.assertIsNone(by_key["~steam/p0"]["direction"])


if __name__ == "__main__":
    unittest.main()
