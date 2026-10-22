"""Burner drills in a MinerRow (Rory, 2026-10-21: the kit stays small, with burner drills added,
so a player that spent its starter plates can still mine). The template took drill= and fuel= before,
but its geometry was the electric drill's 3x3 one, so a burner row failed to expand."""
import os
import shutil
import tempfile
import unittest

from fkcore import connect, expand, fkp, flow, lang, rates, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()

SRC = """
ore   = MinerRow<n=4, resource=iron-ore, drill=burner-mining-drill, fuel=coal> @(4, 2)
coal  = Chest<requester, item=coal, rate=0.5/s> @(0, 2)
smelt = SmelterRow<n=2, recipe=iron-plate> @(4, 12)
box   = Chest<provider, limit=4> @(14, 18)
net ore_: ore -> smelt
net fuel: coal -> ore, smelt
net plates: smelt -> box
"""


class BurnerRowTest(unittest.TestCase):
    def setUp(self):
        f = lang.parse(SRC, "t.fk")
        self.flat = elaborate(f, dict(f.modules), CAT, "t")
        self.lay, _notes = expand.expand_factory(self.flat, CAT)

    def test_it_lays_out_and_routes(self):
        self.assertEqual(fkp.invariants(self.lay, CAT), [])
        drills = [e for e in self.lay.entities.values() if e.name == "burner-mining-drill"]
        self.assertEqual(len(drills), 4)
        self.assertEqual({(e.x, e.y) for e in drills}, {(5, 5), (7, 5), (9, 5), (11, 5)})
        r = route.route_layout(self.flat, self.lay, CAT)
        self.assertEqual(r.failed, {})
        rep = connect.connect(r.layout, CAT, connect.endpoints(self.flat))
        self.assertEqual({n: x.status for n, x in rep.nets.items()},
                         {"fuel": "connected", "ore_": "connected", "plates": "connected"})

    def test_the_rates_count_fuel_and_ore(self):
        m = rates.solve(self.flat)
        # 4 drills at 0.25 ore/s each, 2 stone furnaces take 0.625/s of it
        self.assertAlmostEqual(m.util["ore/m0"], 0.625, places=2)
        coal = self.flat.machines["ore/m0"].takes
        self.assertIn("coal", coal)


LABS = """
sci = Chest<requester, item="automation-science-pack,logistic-science-pack", rate=0.5/s> @(5, 5)
l1  = Lab @(1, 4)
l2  = Lab @(7, 4)
l3  = Lab @(4, 7)
net sci: sci -> l1, l2, l3
"""


class LabsFromAChestTest(unittest.TestCase):
    """1.7 (Rory, 2026-10-21): a lab fed from a multi-item chest by one inserter is valid: the
    inserter only takes what the lab accepts, but only when the source and the sink both touch it.
    The 2005 player laid its purple lab corner by hand for want of it. 2.0: a mixed net's CLOG
    goes in exactly two ways, that route or the net written ``limited``."""

    def build(self, src):
        f = lang.parse(src, "t.fk")
        flat = elaborate(f, dict(f.modules), CAT, "t")
        lay, _notes = expand.expand_factory(flat, CAT)
        return flat, lay

    def test_labs_around_a_requester_take_their_packs_by_one_inserter_each(self):
        flat, lay = self.build(LABS)
        self.assertEqual([(c.code, c.where) for c in flat.checks], [("CLOG", "net sci")])
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.lines, ["routed    sci: 1 -> 3, 3 inserters (direct insertion)"])
        self.assertFalse([k for k, e in r.layout.entities.items()
                          if k.startswith("~") and e.name == "transport-belt"])
        self.assertEqual(connect.one_inserter(r.layout, CAT, connect.endpoints(flat)), {"sci"})

    def test_the_route_step_clears_clog_for_one_inserter_and_keeps_it_for_a_belt(self):
        d = tempfile.mkdtemp(prefix="fkhand-")
        self.addCleanup(shutil.rmtree, d, True)
        far = LABS.replace("@(1, 4)", "@(1, 20)").replace("@(7, 4)", "@(7, 20)").replace(
            "@(4, 7)", "@(13, 20)")
        script = os.path.join(d, "nauvis.build.fkb")
        files = {"nauvis.surface": "surface nauvis\nmode play\nterrain none\n"
                                   "place t = t plot 0,0 30x30\n",
                 "nauvis.build.fkb": "read_surface nauvis\nread_terrain none\nelaborate\n"
                                     "place\nroute\nfloorplan\nreport_checks\n"}
        for src, hand in ((LABS, True), (far, False)):
            for name, text in dict(files, **{"t.fk": src}).items():
                with open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(text)
            code, ctx = flow.run(script, cat=CAT, echo=lambda _l: None)
            self.assertEqual(code, 0, ctx.log)
            clogs = [c.where for _s, c in ctx.checks if c.code == "CLOG"]
            with open(os.path.join(d, "out", "route.txt"), encoding="utf-8") as fh:
                route_txt = fh.read()
            if hand:
                self.assertEqual(clogs, [])
                self.assertIn("one hand  sci: one inserter from its source straight into each "
                              "sink", route_txt)
            else:
                self.assertEqual(clogs, ["t net sci"])          # a belt in between: it stays
                self.assertNotIn("one hand", route_txt)

    def test_a_products_belt_into_one_chest_can_clog(self):
        src = """
            a   = Assembler<recipe=pipe>             @(0, 0)
            b   = Assembler<recipe=iron-gear-wheel>  @(4, 0)
            fe  = Chest<requester, item=iron-plate, rate=2/s> @(3, 5)
            box = Chest<provider, limit=16>          @(12, 2)
            net fe: fe -> a, b
            net products: a, b -> box
        """
        flat, _lay = self.build(src)
        self.assertEqual([c.code for c in flat.checks], ["CLOG", "SUSHI_LIMIT"])
        flat, _lay = self.build(src.replace(", limit=16", "").replace("products:",
                                                                      "products limited:"))
        self.assertEqual([c.code for c in flat.checks], [])

    def test_a_mixed_belt_into_labs_still_can_clog(self):
        flat, _lay = self.build("""
            red   = Assembler<recipe=automation-science-pack> @(0, 0)
            green = Assembler<recipe=logistic-science-pack>   @(0, 6)
            labs  = LabRow<n=2>                               @(10, 0)
            net sci: red, green -> labs
        """)
        self.assertIn("CLOG", [c.code for c in flat.checks])


if __name__ == "__main__":
    unittest.main()
