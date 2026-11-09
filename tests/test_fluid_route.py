"""The router's fluid plug-in (fkcore.fluid_route): pipes and pipe-to-ground for fluid nets, on
the test game games/lab-fluids (water -> boilers -> steam engines; water + petroleum gas -> a
chemical plant), judged by fkcore.connect; and that game through its own build script on paper."""
import os
import shutil
import tempfile
import unittest

from fkcore import codec, connect, expand, fkp, flow, lang, route
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


class DirectJoinTest(unittest.TestCase):
    def test_boxes_that_join_directly_are_a_pass_through(self):
        # 43-hierarchy (PLAN-ORGANIC D2): a fluid net whose boxes join as they stand lays
        # nothing, so it is counted a pass-through (fen's rx/f5_gas3 was "routed" every build:
        # 0 pipes, 1 direct join, and nothing pinned it)
        flat, lay = build("""
gas  = InfinityPipe<fluid=petroleum-gas, rate=30/s> @(5, 2)
plas = ChemPlant<recipe=plastic-bar> @(5, 3)
cq   = Chest<requester, item=coal, request=20> @(2, 4)
pbx  = Chest<storage> @(9, 4)
net g: gas -> plas
net c: cq -> plas
net p: plas -> pbx
""")
        from fkcore import fluid_route
        self.assertTrue(fluid_route._direct(flat, lay, CAT, "g"))
        r = route.route_layout(flat, lay, CAT)
        self.assertEqual((r.failed, r.passthrough), ({}, ["g"]))
        self.assertIn("routed    g: 1 -> 1, nothing to lay (its boxes join directly)", r.lines)
        self.assertEqual([k for k in r.layout.entities if k.startswith("~g/")], [])
        rep = connect.connect(r.layout, CAT, connect.endpoints(flat))
        self.assertEqual(rep.nets["g"].status, "connected")


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

    def test_a_fluid_net_that_failed_on_this_ground_is_not_searched_again(self):
        # 3.0: as for belts; the fluid router searches its whole box, so the key is all of it
        from unittest import mock
        from fkcore import fluid_route
        real, calls = fluid_route.route, []

        def water_fails(flat, lay, cat, nets, *a, **k):
            calls.append(list(nets))
            added, how, failed = real(flat, lay, cat, nets, *a, **k)
            if "water" in added:
                del added["water"]
                failed["water"] = "fake: no pipe route"
            return added, how, failed
        flat = elaborate_file(os.path.join(GAME, "steam.fk"), CAT)
        lay, _notes = expand.expand_factory(flat, CAT)
        with mock.patch.object(fluid_route, "route", water_fails):
            r = route.route_layout(flat, lay, CAT)
            self.assertEqual((sorted(r.memo), r.failed),
                             (["water"], {"water": "fake: no pipe route"}))
            # the first build's water saw no steam pipes; the next sees them standing
            r = route.route_layout(flat, r.layout, CAT, memo=r.memo)
            self.assertEqual(calls[-1], ["water"])
            again = route.route_layout(flat, r.layout, CAT, memo=r.memo)
            self.assertEqual(len(calls), 2)               # steam stands, water is remembered
            self.assertIn("not searched again", again.failed["water"])
            route.route_layout(flat, r.layout, CAT, memo=r.memo, again=["water"])
            self.assertEqual(calls[-1], ["water"])

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


class LabFluidsFlowTest(unittest.TestCase):
    """games/lab-fluids through its own build script, on paper (no game link)."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="fkfluids-")
        for name in ("steam.fk", "sulfur.fk", "lab.surface", "lab.build.fkb"):
            shutil.copy(os.path.join(GAME, name), cls.dir)
        cls.code, cls.ctx = flow.run(os.path.join(cls.dir, "lab.build.fkb"), cat=CAT,
                                     echo=lambda _l: None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def read(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8") as fh:
            return fh.read()

    def test_it_builds_with_only_the_known_warnings(self):
        self.assertEqual(self.code, 0, self.ctx.log)
        self.assertEqual(sorted((c.code, c.where) for _s, c in self.ctx.checks),
                         [("no-feed", "steam b1"), ("no-feed", "steam b2"),
                          ("no-taker", "sulfur chem")])
        text = self.read("out/report_checks.txt")
        self.assertIn("steam: 2 nets: 2 connected, 0 open, 0 unrouted; 0 SPILL", text)
        self.assertIn("sulfur: 2 nets: 2 connected, 0 open, 0 unrouted; 0 SPILL", text)
        self.assertIn("power: 1 wire network, 1 with generation", self.read("out/floorplan.txt"))

    def test_the_committed_layouts_are_what_the_flow_writes(self):
        for name in ("steam.fkp", "sulfur.fkp", "lab.fkp"):
            with open(os.path.join(GAME, name), encoding="utf-8") as fh:
                self.assertEqual(self.read(name), fh.read(), name)


if __name__ == "__main__":
    unittest.main()
