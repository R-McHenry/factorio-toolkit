import os
import unittest

from fkcore import connect, expand, fkp, lang, route
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate, elaborate_file

CAT = Catalog.load()
REDGREEN = os.path.join(os.path.dirname(__file__), "..", "games", "redgreen", "main.fk")

BASE = """
ore   = MinerRow<n=2, resource=iron-ore>  @(14, 0, rot 2)
coal  = MinerRow<n=1, resource=coal>      @(24, 0, rot 2)
smelt = SmelterRow<n=2, recipe=iron-plate> @(6, 12)
pipes = AsmRow<n=1, recipe=pipe>           @(6, 24)
net ore_: ore -> smelt
net fuel: coal -> smelt
"""


TWO_SMELTERS = """
ore    = MinerRow<n=2, resource=iron-ore>   @(14, 0, rot 2)
coal   = MinerRow<n=1, resource=coal>       @(24, 0, rot 2)
smelt  = SmelterRow<n=2, recipe=iron-plate> @(6, 12)
smelt2 = SmelterRow<n=2, recipe=iron-plate> @(16, 12)
pipes  = AsmRow<n=1, recipe=pipe>           @(6, 24)
net ore_: ore -> smelt, smelt2
net fuel: coal -> smelt, smelt2
"""


def build(text):
    f = lang.parse(text, "t.fk")
    flat = elaborate(f, dict(f.modules), CAT, "t")
    lay, notes = expand.expand_factory(flat, CAT)
    assert fkp.invariants(lay, CAT) == [], fkp.invariants(lay, CAT)
    return flat, lay


def judged(flat, r):
    rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
    return {n: x.status for n, x in rep.nets.items()}, rep


class SmallTest(unittest.TestCase):
    def test_paths(self):
        flat, lay = build(BASE + "net plate: smelt -> pipes\n")
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {})
        self.assertEqual(sorted(r.routed), ["fuel", "ore_", "plate"])
        self.assertEqual(fkp.invariants(r.layout, CAT), [])
        status, rep = judged(flat, r)
        self.assertEqual(set(status.values()), {"connected"}, rep.lines())
        self.assertEqual(rep.leaks, [])
        # every route carrier is keyed under its net and carries it
        for key, e in r.layout.entities.items():
            if key.startswith("~"):
                self.assertEqual(e.net, e.owner[1:], key)

    def test_a_split_and_a_merge(self):
        # ore and fuel feed two smelter rows (1 -> 2: a splitter); the two rows feed one pipe row
        # (2 -> 1: grown from the consumer and laid reversed, so its splitter is a merge)
        flat, lay = build(TWO_SMELTERS + "net plate: smelt, smelt2 -> pipes\n")
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual(r.failed, {}, r.lines)
        for net in ("ore_", "fuel", "plate"):
            names = [e.name for k, e in r.layout.entities.items() if k.startswith(f"~{net}/")]
            self.assertEqual(names.count("splitter"), 1, net)
        status, rep = judged(flat, r)
        self.assertEqual(set(status.values()), {"connected"}, rep.lines())
        self.assertEqual(rep.leaks, [])

    def test_several_drivers_and_consumers_are_reported_not_routed(self):
        flat, lay = build(TWO_SMELTERS + """
            sticks = AsmRow<n=1, recipe=iron-stick> @(16, 24)
            net plate: smelt, smelt2 -> pipes, sticks
        """)
        r = route.route_layout(flat, lay, CAT)
        line = next(l for l in r.lines if " plate:" in l)
        self.assertTrue(line.startswith("skipped"), line)
        self.assertIn("2 drivers and 2 consumers", line)

    def test_an_unreachable_net_fails_with_a_reason(self):
        flat, lay = build(BASE + "net plate: smelt -> pipes\n")
        r = route.route_layout(flat, lay, CAT, bounds=(0, 0, 40, 23))   # pipes' head is outside
        self.assertIn("plate", r.failed)
        self.assertTrue(any(l.startswith("FAILED    plate:") for l in r.lines))
        self.assertEqual(sorted(r.routed), ["fuel", "ore_"])

    def test_laid_nets_are_kept(self):
        flat, lay = build(BASE + "net plate: smelt -> pipes\n")
        first = route.route_layout(flat, lay, CAT)
        again = route.route_layout(flat, first.layout, CAT)
        self.assertEqual(again.routed, [])
        self.assertEqual(sorted(again.kept), ["fuel", "ore_", "plate"])
        self.assertEqual(fkp.dumps(again.layout), fkp.dumps(first.layout))

    def test_blocked_ground_is_avoided(self):
        # terrain (water, cliffs) comes in as blocked tiles: the route goes round them
        flat, lay = build(BASE + "net plate: smelt -> pipes\n")
        first = route.route_layout(flat, lay, CAT)
        belts = sorted(k for k, e in first.layout.entities.items()
                       if k.startswith("~plate/b") and e.name == "transport-belt")
        e = first.layout.entities[belts[len(belts) // 2]]
        tile = (int(e.x), int(e.y))
        r = route.route_layout(flat, lay, CAT, blocked=[tile])
        self.assertEqual(r.failed, {}, r.lines)
        used = set()
        for k, x in r.layout.entities.items():
            if k.startswith("~"):
                used |= fkp.tiles_of(CAT, x)
        self.assertNotIn(tile, used)
        status, rep = judged(flat, r)
        self.assertEqual(set(status.values()), {"connected"}, rep.lines())

    def test_a_fluid_net_goes_to_the_fluid_plug_in(self):
        # pipes are not belts: a fluid net is never laid as a belt route by this router
        flat, lay = build(BASE + """
            water = OffshorePump        @(30, 12)
            chem  = ChemPlant<recipe=sulfur> @(30, 20)
            net plate: smelt -> pipes
            net w: water -> chem
        """)
        self.assertEqual(route.fluid_nets(flat, CAT), {"w"})
        r = route.route_layout(flat, lay, CAT)
        self.assertIn("plate", r.routed)
        carriers = {e.name for k, e in r.layout.entities.items() if k.startswith("~w/")}
        self.assertLessEqual(carriers, {"pipe", "pipe-to-ground"})
        if route._fluid_plugin() is None:                  # until fkcore.fluid_route is built
            line = next(l for l in r.lines if " w:" in l)
            self.assertTrue(line.startswith("skipped   w: a fluid net"), line)

    def test_deterministic(self):
        flat, lay = build(BASE + "net plate: smelt -> pipes\n")
        a = route.route_layout(flat, lay, CAT)
        b = route.route_layout(flat, lay, CAT)
        self.assertEqual(fkp.dumps(a.layout), fkp.dumps(b.layout))


class RedgreenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flat = elaborate_file(REDGREEN, CAT)
        lay, cls.notes = expand.expand_factory(cls.flat, CAT)
        cls.r = route.route_layout(cls.flat, lay, CAT)
        cls.rep = connect.connect(cls.r.layout, CAT, connect.endpoints(cls.flat))

    def test_every_net_routes_and_connects_without_leak(self):
        self.assertEqual(self.notes, [])
        self.assertEqual(self.r.failed, {})
        self.assertEqual(len(self.r.routed), 12)
        self.assertEqual(fkp.invariants(self.r.layout, CAT, nets=self.flat.nets), [])
        self.assertEqual({x.status for x in self.rep.nets.values()}, {"connected"})
        self.assertEqual(self.rep.leaks, [])
        self.assertEqual(self.rep.checks, [])          # no UNROUTED, OPEN, LEAK or UG_SIDELOAD

    def test_counts(self):
        routes = [e for k, e in self.r.layout.entities.items() if k.startswith("~")]
        self.assertEqual(len(self.r.layout.entities), 566 + len(routes))
        print(f"\nredgreen routed: {len(routes)} route carriers "
              f"({sum(e.name == 'transport-belt' for e in routes)} belts, "
              f"{sum(e.name == 'underground-belt' for e in routes)} underground ends, "
              f"{sum(e.name == 'splitter' for e in routes)} splitters), "
              f"{self.r.passes} passes; {self.rep.summary()}")


if __name__ == "__main__":
    unittest.main()
