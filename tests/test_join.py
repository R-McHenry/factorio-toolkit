"""Several iron works and several iron consumers joined by ONE net (Rory's question): the toolkit
elaborates, routes (the producers' belts meet at a hub), hands it and solves it. join-small fits one
yellow lane; join-big asks twice that, and the routed solver's too-thin line says so
(games/v2-bench/join-*.fk, CORE-V2.md). The hands are the build's (``fkcore.hands``: the lowest rung,
raised where the flow needs more), so what binds here is the belt and the hub, not a slow hand."""
import os
import unittest

from fkcore import avail, connect, expand, hands, lang, route, routed, tiers
from fkcore.catalog import Catalog
from fkcore.elaborate import elaborate

CAT = Catalog.load()
BENCH = os.path.join(os.path.dirname(__file__), "..", "games", "v2-bench")


class _Joined:
    """The pipeline once per file, and what holds for both sizes."""
    NAME = None

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(BENCH, f"{cls.NAME}.fk"), encoding="utf-8") as fh:
            f = lang.parse(fh.read(), f"{cls.NAME}.fk")
        cls.flat = elaborate(f, dict(f.modules), CAT, cls.NAME)
        lay, cls.notes = expand.expand_factory(cls.flat, CAT)
        cls.rt = route.route_layout(cls.flat, lay, CAT)
        lay, _lines, _changed = hands.assign(cls.rt.layout, cls.flat, CAT)
        cls.layout = lay
        cls.rep = connect.connect(lay, CAT, connect.endpoints(cls.flat))
        cls.r = routed.solve(cls.flat, lay, CAT)
        cls.lines, cls.checks = routed.report(cls.r, cls.NAME)

    def plates(self):
        """Iron plates/s the iron net's consumer machines get, in all."""
        keys = {k for k, _item in self.flat.nets["iron"].consumers}
        return sum(self.r.res.delivered.get((k, ""), {}).get("iron-plate", 0.0) for k in keys)

    def test_elaborates(self):
        # the consumers' provider chests have no limit=; nothing else (no DOUBLE, CLOG or TYPE).
        # LANES (2.0.50): each iron works' ore and fuel are two miner rows into one smelter row,
        # the pair the check exists for; pairing them is a change to the bench, not to this test
        self.assertEqual({c.code for c in self.flat.checks}, {"no-limit", "could-pair"})

    JOINED = "hub"         # how the iron net's three works meet: one trunk from a hub

    def test_expands_and_routes(self):
        self.assertEqual(self.notes, [])
        self.assertEqual(self.rt.failed, {})
        iron = next(l for l in self.rt.lines if l.split()[1] == "iron:")
        self.assertTrue(iron.startswith("routed    iron: 3 -> 3,"), iron)
        self.assertIn(self.JOINED, iron)

    def test_connects(self):
        self.assertEqual({n: x.status for n, x in self.rep.nets.items()},
                         {n: "connected" for n in self.rep.nets})
        self.assertEqual(self.rep.leaks, [])


class JoinSmallTest(_Joined, unittest.TestCase):
    """Three works of 4 furnaces: 3.75 plates/s, all of it reaches the consumers."""
    NAME = "join-small"

    def test_every_plate_arrives(self):
        self.assertAlmostEqual(self.plates(), 3.75, places=3)
        self.assertNotIn("too-thin", [c.code for c in self.checks])


class JoinBigTest(_Joined, unittest.TestCase):
    """Three works of 16 furnaces: 15 plates/s made and asked, through a trunk of yellow belt.

    2.0.54: more than a lane, so the trunk takes both: the router splits the works in two groups
    (one, and the other two) and side-loads each group onto its own lane at a join. Three equal
    works split 5 against 10, so the two-work lane is asked 10/s and the trunk brings 12.5/s (it
    brought 7.5 on one lane); a work shared by both lanes would bring the last 2.5."""
    NAME = "join-big"
    JOINED = "join"

    def test_the_trunk_binds(self):
        self.assertAlmostEqual(self.plates(), 12.5, places=3)
        # one line for the two-work group's yellow lanes, one for its splitters
        self.assertEqual([(c.code, c.where) for c in self.checks],
                         [("too-thin", "join-big net iron")] * 2)
        lanes_, splitters = sorted((str(c) for c in self.checks), key=lambda s: "splitter" in s)
        self.assertIn("10.00/s required where its yellow lanes carry 7.50/s (ratio 1.33)", lanes_)
        self.assertIn("it delivers 12.50/s of iron-plate to its consumers, 15.00/s nominal", lanes_)
        self.assertIn("required where its yellow splitters (a lane a side) carry 7.50/s", splitters)

    def test_tier_minimize_carries_it(self):
        # the trunk and the hub's splitters go red (15/s a lane): every plate arrives
        new, _lines, changed = tiers.assign(self.flat, self.layout, CAT, "minimize")
        self.assertIn("fast-splitter", {n for _o, n in changed.values()})
        r = routed.solve(self.flat, new, CAT)
        keys = {k for k, _item in self.flat.nets["iron"].consumers}
        got = sum(r.res.delivered.get((k, ""), {}).get("iron-plate", 0.0) for k in keys)
        self.assertAlmostEqual(got, 15.0, places=3)
        self.assertEqual(routed.report(r, self.NAME)[1], [])

    def test_the_plates_ride_both_lanes(self):
        # 2.0.54: each group on its own lane of the trunk
        flow = self.r.res.flow
        carrying = {nid[1] for nid in self.r.nodes_of("iron")
                    if nid[1] and flow.get(nid, {}).get("iron-plate", 0) > 1e-9}
        self.assertEqual(carrying, {"L", "R"})


if __name__ == "__main__":
    unittest.main()
